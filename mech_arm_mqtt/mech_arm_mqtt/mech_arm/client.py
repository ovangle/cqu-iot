from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
import json
from typing import TYPE_CHECKING, Any, AsyncContextManager, AsyncIterable, Awaitable, Callable, TypeVar
import dataclasses
from typing import Generic
from paho.mqtt import MQTTv311
from asyncio_mqtt import Client as MQTTClient
from mech_arm_mqtt.mech_arm_mqtt.async_mycobot import AsyncMyCobot

from mech_arm_mqtt.schema.actions import (
    BeginSession,
    MechArmAction,
    MoveAction,
    SessionAction,
    action_from_json_object,
)

from .env import ClientSettings


from mech_arm_mqtt.schema.events import (
    ActionResponse,
    BroadcastEvent,
    Busy,
    MechArmEvent,
    MoveComplete,
    SessionCreated,
    SessionEvent,
    event_to_json_object,
)
from mech_arm_mqtt.schema.protocol import MechArmClient

if TYPE_CHECKING:
    from .session import MechArmSession


class MyCobotMQTTClient(MQTTClient, MechArmClient['MyCobotMQTTSession']):
    _current_session: MyCobotMQTTSession | None

    def current_session(self):
        return self._current_session

    def __init__(self, client_id: str, client_settings: ClientSettings):
        super().__init__(
            client_settings.MQTT_HOSTNAME,
            client_settings.MQTT_PORT,
            username=client_settings.MQTT_USER,
            password=client_settings.MQTT_PASSWORD,
            protocol=MQTTv311,
            client_id=client_id,
        )
        self.settings = client_settings
        self._current_session = None

    async def actions(self) -> AsyncIterable[MechArmAction]:
        async with self.messages() as messages:
            async for message in messages:
                if not isinstance(message.payload, (str, bytes)):
                    raise ValueError('Expected str or bytes payload')
                try:
                    message_dict = json.loads(message.payload)
                    action = action_from_json_object(message_dict)
                except ValueError as e:
                    raise e
                if action.mecharm_client_id != self.mqtt_client_id:
                    continue
                yield action

    @property
    def broadcast_topic(self):
        return f"application/{self.settings.MQTT_APP_ID}/device/{self.settings.MQTT_DEVICE_ID}/up"

    TBroadcastEvent = TypeVar("TBroadcastEvent", bound=BroadcastEvent)

    async def _emit_broadcast_event(self, event: TBroadcastEvent) -> TBroadcastEvent:
        await self.publish(
            topic=self.broadcast_topic, payload=json.dumps(event_to_json_object(event))
        )
        return event

    @property
    def session_begin_topic(self):
        return f"application{self.settings.MQTT_APP_ID}/devices/{self.settings.MQTT_DEVICE_ID}/session/create"

    async def subscribe_session_begin_action(self, qos: int = 0, timeout: int = 10):
        return await self.subscribe(self.session_begin_topic, qos=qos, timeout=timeout)

    async def _emit_session_begin_response_event(self, event: ActionResponse[BeginSession]):
        await self.publish(
            topic=self.session_begin_topic, payload=json.dumps(event_to_json_object(event))
        )
        return event

    async def emit_busy(self, busy: Busy):
        return await self._emit_session_begin_response_event(busy)

    async def emit_session_created(self, session_created: SessionCreated):
        await self._emit_session_begin_response_event(session_created)
        return await self._emit_broadcast_event(session_created)

    def session_topic(self, session_id: int):
        return f"application/{self.settings.MQTT_APP_ID}/device/{self.settings.MQTT_DEVICE_ID}/session/{session_id}"

    async def subscribe_session_actions(
        self, session_id: int, qos: int = 0, timeout: int = 10
    ):
        return await self.subscribe(
            self.session_topic(session_id), qos=qos, timeout=timeout
        )

    async def session_actions(self, session_id: int) -> AsyncIterable[SessionAction]:
        async for action in self.actions():
            if isinstance(action, SessionAction):
                if action.session_id == session_id:
                    yield action


    TSessionEvent = TypeVar("TSessionEvent", bound=SessionEvent)

    async def _emit_session_event(
        self, session_id: int, event: TSessionEvent
    ) -> TSessionEvent:
        assert event.session_id == session_id
        await self.publish(
            topic=self.session_topic(session_id),
            payload=json.dumps(event_to_json_object(event)),
        )
        return event

    async def emit_move_complete(
        self, session_id: int, event: MoveComplete
    ):
        await self._emit_session_event(session_id, event)

    @property
    def mqtt_client_id(self):
        return self.settings.MQTT_APP_ID

    @property
    def application_topic(self):
        return f"application/{self.settings.MQTT_APP_ID}"

    @property
    def event_broadcast_topic(self) -> str:
        return f"application/{self.settings.MQTT_APP_ID}/device/+/event/up"

    async def begin_session(self, begin_session: BeginSession) -> MechArmSession:
        from .session import MechArmSession

        if begin_session.mecharm_client_id != self.mqtt_client_id:
            # If this is a request for a different mecharm, then ignore.
            return

        if self._current_session is not None:
            await self.emit_busy(
                Busy(
                    controller_client_id=begin_session.controller_client_id,
                    **dataclasses.asdict(begin_session),
                )
            )
            return

        with MyCobotMQTTSession(self, begin_session.controller_client_id) as session:
            self._current_session = session
            return session
            self._current_session = session

            await self.emit_session_created(
                SessionCreated(
                    session_id=self.current_session.session_id,
                    **dataclasses.asdict(begin_session),
                )
            )



_NEXT_SESSION_ID = 0


def next_session_id():
    global _NEXT_SESSION_ID
    session_id = _NEXT_SESSION_ID
    _NEXT_SESSION_ID += 1
    return session_id

class MyCobotMQTTSession(MechArmSession):
    def __init__(
        self,
        client: MyCobotMQTTClient,
        controller_client_id: str,
    ):
        self.client = client
        self.controller_client_id = controller_client_id
        self.ssession_id = next_session_id()

        self._mycobot = AsyncMyCobot(self.client.settings.MYCOBOT_PORT)

    @property
    def mecharm_client_id(self):
        return self.client.mqtt_client_id

    @property
    def session_actions(self) -> AsyncIterable[SessionAction]:
        return self.client.session_actions(self.session_id)

    async def run(self):
        async for action in self.session_actions:
            if isinstance(action, MoveAction):
                await self.move(action)

    async def __aenter__(self) -> None:
        await self.client.subscribe_session_actions(self.session_id)
        async for action in self.client.session_actions(self.session_id):
            if isinstance(action, MoveAction):
                await self.move(action)
        return

    async def __aexit__(self) -> None:
        raise NotImplementedError


    async def move(self, move_action: MoveAction) -> MoveComplete:
        """
        Should initialise the movement of the
        """
        move_complete = await self._mycobot.move(move_action)
        await self.client.emit_move_complete(self.session_id, move_complete)
        return move_complete


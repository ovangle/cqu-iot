from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any, AsyncContextManager, AsyncIterable, Awaitable, Callable, TypeVar
import dataclasses
from typing import Generic
from mech_arm_mqtt.schema.session import MechArm, MechArmSession
from asyncio_mqtt import Client as MQTTClient, ProtocolVersion
from mech_arm_mqtt.async_mycobot import AsyncMyCobot

from mech_arm_mqtt.schema.model import ActionError, action_from_json_object, event_to_json_object
from mech_arm_mqtt.schema.actions import (
    BeginSession,
    MechArmAction,
    MoveAction,
    SessionAction,
)
from .env import ClientSettings


from mech_arm_mqtt.schema.events import (
    ActionResponse,
    MechArmEvent,
    MoveComplete,
    SessionBusy,
    SessionCreated,
    SessionEvent,
)

TEvent = TypeVar('TEvent', bound=MechArmEvent)


class MyCobotMQTTClient(MQTTClient, MechArm):
    _current_session: MyCobotMQTTSession | None

    def current_session(self):
        return self._current_session

    def __init__(self, client_id: str, client_settings: ClientSettings):
        super().__init__(
            client_settings.MQTT_HOSTNAME,
            client_settings.MQTT_PORT,
            username=client_settings.MQTT_USER,
            password=client_settings.MQTT_PASSWORD,
            protocol=ProtocolVersion.V311,
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

    async def _emit_broadcast_event(self, event: TEvent) -> TEvent:
        await self.publish(
            topic=self.broadcast_topic, payload=json.dumps(event_to_json_object(event))
        )
        return event

    @property
    def session_begin_topic(self):
        return f"application{self.settings.MQTT_APP_ID}/devices/{self.settings.MQTT_DEVICE_ID}/session/create"

    async def subscribe_session_begin_action(self, qos: int = 0, timeout: int = 10):
        return await self.subscribe(self.session_begin_topic, qos=qos, timeout=timeout)

    async def _emit_session_begin_response_event(self, event: ActionError[BeginSession]):
        await self.publish(
            topic=self.session_begin_topic, payload=json.dumps(event_to_json_object(event))
        )
        return event

    async def emit_busy(self, busy: SessionBusy):
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

    @contextlib.asynccontextmanager
    async def begin_session(self, begin_session: BeginSession) -> MyCobotMQTTSession:
        try:
            self._current_session = MyCobotMQTTSession(self, begin_session)

            async def relay_notifications():
                for event in self._current_session.events():
                    await self._event_queue.put(event)
            loop = asyncio.get_running_loop()
            loop.call_soon(relay_notifications())

            yield self._current_session
        finally:
            self._current_session = None
            



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
        begin_session: BeginSession
    ):
        self.client = client
        self._begin_session = begin_session
        self.session_id = next_session_id()

        self._mycobot = AsyncMyCobot(
            self.session_id, 
            begin_session,
            client.cient_settings.MECHARM_PORT
        )

    @property
    def client_id(self):
        return self.client.id

    @property
    def remote_client_id(self):
        return self._begin_session.remote_client_id

    @property
    def mecharm_client_id(self):
        return self.client.mqtt_client_id

    async def events(self):
        async for event in self._mycobot.events():
            yield event

    async def on_action(self, action):
        match action.name:
            case "move":
                return await self._mycobot.move(action)
            case _:
                raise ValueError(f"Unrecognised action {action}")

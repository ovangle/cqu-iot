from __future__ import annotations
import asyncio
import contextlib
import json
from logging import getLogger
from typing import AsyncContextManager, AsyncIterable, AsyncIterator, TypeVar

from asyncio_mqtt import Client as MQTTClient, ProtocolVersion
from mech_arm_mqtt.async_mycobot import AsyncMyCobot
from ..core import (
    ActionResponse,
    action_from_json_object,
    event_to_json_object,
    MechArmSessionInfo, 
    ActionErrorInfo,
    SessionAction, 
    SessionEvent, 
    MechArmAction,
    MechArmEvent
)
from ..actions import BeginSession, ExitSession, MoveAction
from ..events import (
    SessionCreated, 
    SessionDestroyed, 
    SessionReady,
    SessionBusy,
    NoCurrentSession,
    MoveProgress,
    MoveComplete
)

from .common import BaseMechArmMQTT, BaseMechArmMQTTSession, MQTTClientSettings

class MQTTHostSettings(MQTTClientSettings):
    MYCOBOT_PORT: int
    
def mqtt_client(settings: MQTTClientSettings):
    return MQTTClient(
        hostname=settings.MQTT_HOSTNAME,
        port=settings.MQTT_PORT,
        username=settings.MQTT_USER,
        password=settings.MQTT_PASSWORD,
        protocol=ProtocolVersion.V311
    )

class MechArmMQTTHost(BaseMechArmMQTT):
    settings: MQTTHostSettings
    _current_session: MechArmMQTTHostSession | None

    def __init__(self, client: MQTTClient, client_settings: MQTTHostSettings):
        self.client = client
        self.settings = client_settings
        self._current_session = None

        self._loop = asyncio.get_running_loop()
        self._logger = getLogger(__name__)

    TEvent = TypeVar('TEvent', bound=MechArmEvent)

    async def emit_event(self, event: TEvent) -> None:
        return await self.client.publish(
            self.event_topic,
            json.dumps(event_to_json_object(event))
        )

    async def __aenter__(self) -> MechArmMQTTHost:
        if self._current_session is not None:
            raise RuntimeError(f"Session present when entering context")

        await self.client.__aenter__()
        reason_codes = await self.client.subscribe(self.action_topic)
        self._logger.info(f'Subscribed to {self.action_topic} {reason_codes}')

        return self

    async def __aexit__(self, __exc_type, __exc_value, __exc_tb):
        if __exc_type:
            self._logger.exception(str(__exc_value), exc_info=__exc_type, stack_info=__exc_tb)

        await self.client.unsubscribe(self.action_topic)
        await self.client.__aexit__(__exc_type, __exc_value, __exc_tb)

    @property
    async def actions(self) -> AsyncIterable[MechArmAction]:
        async with self.client.messages() as messages:
            async for message in messages:
                if not isinstance(message.payload, (str, bytes)):
                    raise ValueError("Expected str or bytes payload")
                try:
                    message_dict = json.loads(message.payload)
                    action = action_from_json_object(message_dict)
                except ValueError as e:
                    raise e
                if action.mech_arm.client_id != self.client.id:
                    continue
                yield action

    async def on_action_received(self, action: MechArmAction):
        match (action):
            case BeginSession():
                await self.on_begin_session(action)
            case SessionAction():
                await self.on_session_action(action)
   
    def current_session(self):
        return self._current_session

    async def on_begin_session(self, begin_session: BeginSession):
        async with MechArmMQTTHostSession(
            self, 
            mqtt_client(self.settings),
            begin_session
        ) as session:
            self._current_session = session

            async def relay_session_events():
                async for event in session.events:
                    match (event):
                        case (SessionCreated(), SessionDestroyed()):
                            await self.emit_event(event)

            loop = asyncio.get_running_loop()
            loop.call_soon(relay_session_events())

            await session.run_actions()

    TSessionAction = TypeVar('TSessionAction', bound=SessionAction)
    
    async def on_session_action(self, action: TSessionAction) -> ActionResponse[TSessionAction]:
        if self._current_session is None:
            raise NoCurrentSession(action)
        if action.session.id != self._current_session.session_id:
            raise NoCurrentSession(action)
        return await self._current_session.on_action(action)
    
    async def on_session_exit(self, exit_session: ExitSession):
        self._current_session = None

    async def run(self):
        async for action in self.actions:
            self._loop.call_soon(self.on_action_received, action)

_NEXT_SESSION_ID = 0


def next_session_id():
    global _NEXT_SESSION_ID
    session_id = _NEXT_SESSION_ID
    _NEXT_SESSION_ID += 1
    return session_id


class MechArmMQTTHostSession(BaseMechArmMQTTSession):
    def __init__(self, mech_arm: MechArmMQTTHost, mqtt_client: MQTTClient, begin_session: BeginSession):
        self.mech_arm = mech_arm
        self.mqtt_client = mqtt_client

        self._begin_session = begin_session
        self.session_id = next_session_id()

        self._closed = False
        self._loop = asyncio.get_running_loop()
        self._mycobot = AsyncMyCobot(
            self.session_id,
            self._begin_session,
            mech_arm.settings.MYCOBOT_PORT
        )
        self._action_queue = asyncio.Queue[SessionAction]()
        self._event_queue = asyncio.Queue[SessionEvent]()

    @property
    def session_info(self):
        return MechArmSessionInfo(
            id=self.session_id,
            remote_client_id=self._begin_session.remote_client_id,
            client_id=self.mech_arm.client_id
        )

    @property
    def _session_topic_prefix(self):
        return f"{self.mech_arm._topic_prefix}/session/{self.session_id}"

    @property
    def session_events_topic(self):
        return f"{self._session_topic_prefix}/up"

    @property
    def session_actions_topic(self):
        return f"{self._session_topic_prefix}/down"

    async def emit_event(self, event: SessionEvent):
        await self._event_queue.put(event)
        await self.mqtt_client.publish(
            self.session_events_topic,
            json.dumps(event_to_json_object(event))
        )

    @property
    async def events(self) -> AsyncIterator[SessionEvent]:
        while not self._closed:
            yield await self._event_queue.get()
            await asyncio.sleep(1)

    async def on_action(self, action: SessionAction):
        """
        A session can only handle one action at a time.
        """
        await self._action_queue.put(action)

    async def run_actions(self):
        while not self._closed:
            if not self._action_queue.empty():
                action = await self._action_queue.get()
                match action:
                    case MoveAction():
                        await self.on_move(action)
                    case ExitSession():
                        await self.on_exit_session(action)
            await asyncio.sleep(1)

    async def on_move(self, action: MoveAction):
        def emit_on_move_progress(progress: MoveProgress):
            self._loop.call_soon(self.emit_event, progress)

        move_complete = await self._mycobot.move(
            action,
            on_progress=emit_on_move_progress
        )
        await self.emit_event(move_complete)

    async def on_exit_session(self, exit_session: ExitSession):
        await self.emit_event(
            SessionDestroyed(
                action=exit_session,
                session=self.session_info,
                exit_code=exit_session.exit_code
            )
        )

    async def __aenter__(self) -> MechArmMQTTHostSession:
        client = await self.mqtt_client.__aenter__()
        await client.subscribe(
            self.session_actions_topic
        )
        await self._mycobot.__aenter__()
        await self.emit_event(SessionReady(session=self.session_info))
        return self

    async def __aexit__(self, __exc_type, __exc_value, __exc_tb):
        self._closed = True
        await self.mqtt_client.unsubscribe(
            self.session_actions_topic
        )
        await self.mqtt_client.__aexit__(__exc_type, __exc_value, __exc_tb)
        await self._mycobot.__aexit__()

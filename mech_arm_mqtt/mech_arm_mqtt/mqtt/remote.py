from __future__ import annotations

from abc import abstractmethod
from typing import AsyncIterator, TypeVar, cast
import json
from asyncio_mqtt import Client as MQTTClient, ProtocolVersion

from ..actions import BeginSession, ExitSession, MoveAction
from ..core import ActionErrorInfo, ActionResponse, MechArmAction, SessionAction, action_to_json_object, event_from_json_object, MechArmEvent
from ..events import MoveComplete, SessionCreated, SessionDestroyed

from .common import MQTTClientSettings, BaseMechArmMQTT, BaseMechArmMQTTSession

class RemoteClientSettings(MQTTClientSettings):
    pass

def mqtt_client(settings: RemoteClientSettings, client_id: str):
    return MQTTClient(
        hostname=settings.MQTT_HOSTNAME,
        port=settings.MQTT_PORT,
        client_id=client_id,
        username=settings.MQTT_USER,
        password=settings.MQTT_PASSWORD,
        protocol=ProtocolVersion.V311
    )

class MechArmMQTTRemote(BaseMechArmMQTT):
    settings: RemoteClientSettings

    def __init__(self, client: MQTTClient, settings: RemoteClientSettings, client_id: str):
        self.client = client
        self.settings = settings

    @property
    async def events(self) -> AsyncIterator[MechArmEvent]:
        async with self.client.messages() as messages:
            async for message in messages:
                assert isinstance(message.payload, str)
                json_object = json.loads(message.payload)
                yield event_from_json_object(json_object)


    TAction = TypeVar("TAction", bound=MechArmAction)

    async def dispatch_action(self, action: TAction) -> ActionResponse[TAction]:
        await self.client.publish(
            self.action_topic,
            json.dumps(action_to_json_object(action))
        ) 
        async for event in self.events:
            if not isinstance(event, (ActionResponse, ActionErrorInfo)):
                continue
            if not event.action.name == action.name and event.action.id == action.id:
                continue

            if isinstance(event, ActionErrorInfo):
                raise event.as_error()
            return event
        raise RuntimeError('Client connnection closed before receiving action response')

    async def begin_session(
        self, begin_session: BeginSession | None = None
    ) -> MechArmRemoteSession:
        if not begin_session:
            begin_session = BeginSession(
                mech_arm=self.mech_arm_info,
                remote_client_id=self.client.id
            )
        session_created = cast(SessionCreated, await self.dispatch_action(begin_session))
        return MechArmRemoteSession(
            self,
            mqtt_client(self.settings, self.client.id),
            session_created.session.id
        )

class MechArmRemoteSession(BaseMechArmMQTTSession):

    def __init__(
        self,
        mech_arm: MechArmMQTTRemote,
        mqtt_client: MQTTClient,
        session_id: int,
    ):
        self.mech_arm = mech_arm
        self.mqtt_client = mqtt_client

        self.session_id = session_id
        self.is_closed = False

    @property
    async def session_events(self):
        async with self.mqtt_client.messages() as messages:
            async for message in messages:
                json_object = json.loads(str(message.payload))
                yield event_from_json_object(json_object)

    TAction = TypeVar('TAction', bound=SessionAction)

    async def dispatch_action(self, action: TAction) -> ActionResponse[TAction]:
        await self.client.publish(
            self.session_action_topic,
            json.dumps(action_to_json_object(action))
        )
        async for event in self.session_events:
            if not isinstance(event, (ActionResponse, ActionErrorInfo)):
                continue
            if not event.action.name == action.name and event.action.id == action.id:
                continue

            if isinstance(event, ActionErrorInfo):
                raise event.as_error()

            return event
        raise RuntimeError('Client connnection closed before receiving action response')

    async def __aenter__(self):
        await self.mqtt_client.__aenter__()
        await self.mqtt_client.subscribe(
            self.session_events_topic
        )

    async def __aexit__(self, __exc_type, __exc_value, __exc_tb):
        await self.mqtt_client.unsubscribe(self.session_events_topic)
        await self.mqtt_client.__aexit__(__exc_type, __exc_value, __exc_tb)

    async def move(self, action: MoveAction) -> MoveComplete:
        return cast(MoveComplete, await self.dispatch_action(action))

    async def exit(self, exit_code: int) -> SessionDestroyed:
        action = ExitSession(
            mech_arm=self.mech_arm_info, 
            session=self.session_info, 
            exit_code=exit_code,
        )
        session_destroyed = cast(SessionDestroyed, await self.dispatch_action(action))
        self._is_closed = True
        return session_destroyed

    
from __future__ import annotations

from abc import abstractmethod
from typing import AsyncIterable, TypeVar, cast
from asyncio import Future
import asyncio
import dataclasses
import json
from typing import Callable
from paho.mqtt.client import MQTTv311, CallbackAPIVersion
from asyncio_mqtt import Client as MQTTClient, ProtocolVersion

from mech_arm_mqtt.schema.actions import BeginSession, MechArmAction, MoveAction, SessionAction, action_to_json_object
from mech_arm_mqtt.schema.events import (
    ActionResponse,
    Busy,
    MechArmEvent,
    MoveComplete,
    SessionCreated,
    SessionExit,
    SessionReady,
    SessionTimeout,
    event_from_json_object
)
from mech_arm_mqtt.schema.protocol import MechArmClient, MechArmSession


class MyCobotRemoteClient(MQTTClient, MechArmClient['MyCobotRemoteSession']):
    def __init__(
        self,
        hostname: str,
        port: int,
        client_id: str,
        username: str,
        password: str,
        application_id: str,
        device_id: str
    ):
        super().__init__(
            hostname=hostname,
            port=port,
            client_id=client_id,
            protocol=ProtocolVersion.V311,
            username=username,
            password=password
        )
        self.client_id = client_id
        self.application_id = application_id
        self.device_id = device_id

    async def _topic_events(self, topic: str) -> AsyncIterable[MechArmEvent]:
        async with self.messages() as messages:
            async for message in messages:
                if message.topic != topic:
                    continue
                if not isinstance(message.payload, (str, bytes)):
                    raise RuntimeError('Message payload must be str or bytes')
                try:
                    message_object = json.loads(message.payload)
                    event = event_from_json_object(message_object)
                except ValueError as e:
                    raise e
                yield event

    TAction = TypeVar('TAction', bound=MechArmAction)

    async def _dispatch_action(
        self,
        topic: str, 
        action: TAction,
        is_final_response: Callable[[MechArmEvent], bool]
    ) -> ActionResponse[TAction]:
        await self.publish(
            topic,
            json.dumps(action_to_json_object(action))
        )
        async for event in self._topic_events(topic):
            if (
                isinstance(event, ActionResponse)
                and event.action.name == action.name
                and event.action.action_id == action.action_id
            ):
                if is_final_response(event):
                    return event
        raise RuntimeError("Topic ended without receiving response for action")

    @property
    def mecharm_broadcast_topic(self) -> str:
        return f"application/{self.application_id}/device/{self.device_id}/up"

    async def message_broadcast_events(self, qos: int = 0) -> AsyncIterable[MechArmEvent]:
        await self.subscribe(
            self.mecharm_broadcast_topic,
            qos=qos
        )
        return self._topic_events(self.mecharm_broadcast_topic)

    @property
    def mecharm_begin_session_topic(self) -> str:
        return f"application/{self.application_id}/device/{self.device_id}/session/create"

    async def begin_session_events(self, qos: int=0) -> AsyncIterable[MechArmEvent]:
        await self.subscribe(
            self.mecharm_begin_session_topic,
            qos=qos
        )
        return self._topic_events(self.mecharm_begin_session_topic)

    async def begin_session(self, begin_session: BeginSession | None = None) -> MyCobotRemoteSession:
        if not begin_session:
            begin_session = BeginSession(
                controller_client_id=self.client_id,
                mecharm_application_id=self.application_id,
            )
        begin_session.controller_client_id = self.client_id
        begin_session_response = await self._dispatch_action(
            self.mecharm_begin_session_topic,
            begin_session,
            lambda a: isinstance(a, SessionCreated) or isinstance(a, Busy)
        )
        if isinstance(begin_session_response, SessionCreated):
            return MyCobotRemoteSession(
                self,
                self.application_id,
                begin_session_response.session.session_id
            )
        else:
            raise RuntimeError(f"{begin_session_response}")

    def mecharm_session_topic(self, session_id: int):
        return f"application/{self.application_id}/device/{self.device_id}/session/{session_id}"

    async def session_events(self, session_id: int) -> AsyncIterable[MechArmEvent]:
        session_topic = self.mecharm_session_topic(session_id)
        return self._topic_events(session_topic)

    async def subscribe_session_events(self, session_id: int):
        return await self.subscribe(self.mecharm_session_topic(session_id))

    async def unsubscribe_session_events(self, session_id: int):
        return await self.unsubscribe(self.mecharm_session_topic(session_id))

    async def dispatch_session_action(self, session_id: int, action: SessionAction):
        await self._dispatch_action(
            self.mecharm_session_topic(session_id),
            action,
            lambda evt: isinstance(evt, SessionAction)
        )


class MyCobotRemoteSession(MechArmSession):
    def __init__(
        self,
        client: MyCobotRemoteClient,
        arm_application_id: str,
        session_id: int,
    ):
        self.client = client
        self.arm_application_id = arm_application_id
        self.session_id = session_id
        self.is_closed = False

    async def session_events(self) -> AsyncIterable[MechArmEvent]:
        return await self.client.session_events(self.session_id)

    async def move(self, action: MoveAction) -> MoveComplete:
        return await self.client.dispatch_session_action(self.session_id, action)

    async def exit(self):
        raise NotImplementedError

    async def __aenter__(self):
        await self.client.subscribe_session_events(self.session_id)
        return self

    async def __aexit__(self):
        await self.client.unsubscribe_session_events(self.session_id)
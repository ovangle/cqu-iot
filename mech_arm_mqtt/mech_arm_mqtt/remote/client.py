from __future__ import annotations

from abc import abstractmethod
from typing import AsyncIterable, TypeVar
from asyncio import Future
import asyncio
import dataclasses
import json
from typing import Callable
from paho.mqtt.client import MQTTv311, CallbackAPIVersion
from asyncio_mqtt import Client as MQTTClient

from mech_arm_mqtt.schema.actions import BeginSession, MechArmAction, MoveAction
from mech_arm_mqtt.schema.events import (
    ActionResponse,
    Busy,
    BadAction,
    InvalidActionError,
    MechArmBusyError,
    MechArmEvent,
    SessionCreated,
    SessionExit,
    SessionReady,
    SessionTimeout,
    action_to_json_object,
    event_to_json_object,
)
from mech_arm_mqtt.schema.protocol import MechArmClient


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
            protocol=MQTTv311,
            username=username,
            password=password
        )
        self.application_id = application_id
        self.device_id = device_id

    async def _topic_events(self, topic: str) -> AsyncIterable[MechArmEvent]:
        async with self.messages() as messages:
            async for message in messages:
                if message.topic != topic:
                    continue
                try:
                    message_object = json.loads(message.payload)
                    event = event_to_json_object(message_object)
                except ValueError as e:
                    raise e
                if event.mecharm_client_id != self.mecharm_client_id:
                    continue
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
                and event.action.action_id == action.id
            ):
                if is_final_response(action):
                    return action

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

    async def begin_session(self, begin_session: BeginSession) -> MyCobotRemoteSession:
        begin_session.controller_client_id = self.client_id
        begin_session_response = await self._dispatch_action(
            self.mecharm_begin_session_topic,
            begin_session,
            lambda a: isinstance(a, SessionCreated) or isinstance(a, Busy)
        )
        if isinstance(begin_session_response, SessionCreated):
            return MyCobotRemoteSession(
                self,
                begin_session.mecharm_application_id
            )
        else:
            raise RuntimeError(f"{begin_session_response}")

    def mecharm_session_topic(self, session_id: int):
        return f"application/{self.application_id}/device/{self.device_id}/session/{session_id}"

    async def session_events(self, session_id: int, qos: int = 0) -> AsyncIterable[MechArmEvent]:
        session_topic = self.mecharm_session_topic(session_id)
        return await self._topic_events(session_topic)


class MyCobotRemoteSession:
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

    @property
    def session_events(self) -> AsyncIterable[MechArmEvent]:
        return self.client.session_events(self.session_id)


    
    def add_on_ready(self, session_ready: SessionReady) -> Callable[[], None]:
        return self.client.add_event_handler("session_ready", session_ready)

    _unsubscribe_on_timeout: Callable[[], None] | None

    def on_timeout(self, session_timeout: SessionTimeout):
        """
        A timeout event happens when an action declares that
        the sesion should wait for the same controller to
        execute another action, but the controller has issued
        no further requests
        """
        if session_timeout.session_id == self.session_id:
            print(f"session timed out {session_timeout}")
            self.destroy()

    _unsubscribe_on_exit: Callable[[], None] | None

    def on_exit(self, session_exit: SessionExit):
        if session_exit.session_id == self.session_id:
            print(f"session exited successfully {sesesion_exit}")
            self.destroy()

    def init(self):
        self._unsubscribe_on_timeout = self.client.add_event_handler(
            "session_timeout", lambda session_timeout: self.on_timeout(session_timeout)
        )
        self._unsubscribe_on_exit = self.client.client.add_event_handler(
            "session_exit", lambda session_exit: self.on_exit(session_exit)
        )

    def destroy(self):
        if self._unsubscribe_on_timeout:
            self._unsubscribe_on_timeout()
        if self._unsubscribe_on_exit:
            self._unsubscribe_on_exit()

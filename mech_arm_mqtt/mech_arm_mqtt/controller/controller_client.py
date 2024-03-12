from __future__ import annotations

from abc import abstractmethod
from typing import TypeVar
from asyncio import Future
import asyncio
import dataclasses
import json
from typing import Callable
from paho.mqtt.client import Client, MQTTv311, CallbackAPIVersion

from mech_arm_mqtt.schema.actions import BeginSession, MechArmAction, MoveAction
from mech_arm_mqtt.schema.events import (
    ArmBusy,
    BadAction,
    BadActionError,
    SessionBusyError,
    MechArmEvent,
    SessionCreated,
    SessionExit,
    SessionReady,
    SessionTimeout,
    action_from_json_object,
)


class ControllerClient(Client):
    _all_event_handlers: dict[str, list[Callable[[MechArmEvent], None]]]

    def __init__(
        self,
        client_id: str,
    ):
        super().__init__(
            CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=MQTTv311,
        )
        self._all_event_handlers = {}

    TEvent = TypeVar("TEvent", bound=MechArmEvent, contravariant=True)

    def add_event_handler(
        self,
        name: str,
        handler: Callable[[TEvent], None],
    ) -> Callable[[], None]:
        self._all_event_handlers.setdefault(name, [])
        handlers = self._all_event_handlers[name]
        handler_idx = len(handlers)
        handlers.append(handler)

        def remove_handler():
            del handlers[handler_idx]

        return remove_handler

    def on_message(self, userdata, msg):
        print(f"{msg.topic}: {msg.payload}")
        event = action_from_json_object(json.loads(msg.payload))
        self.on_event(event)

    def on_event(self, event: MechArmEvent):
        for handler in self._all_event_handlers[event.name]:
            handler(event)

    @property
    def mecharm_broadcast_topic(self) -> str:
        raise NotImplementedError

    @property
    def mecharm_action_topic(self) -> str:
        raise NotImplementedError

    def dispatch_action(self, action: MechArmAction):
        action_dict = dataclasses.asdict(action)
        self.publish(self.mecharm_broadcast_topic, json.dumps(action_dict))

    def begin_session(
        self, arm_application_id: str
    ) -> Future[MechArmControllerSession]:
        created_session: Future[MechArmControllerSession] = asyncio.Future()

        begin_session_action = BeginSession(mecharm_application_id=arm_application_id)

        def on_session_created(evt: SessionCreated):
            if evt.action_id == begin_session_action.action_id:
                session = MechArmControllerSession(
                    self, evt.mech_arm_application_id, evt.session_id
                )
                session.init()
                created_session.set_result(session)
                unsubscribe_all()

        unsubscribe_success_handler = self.add_event_handler(
            "session_created", on_session_created
        )

        def on_invalid_action(evt: BadAction):
            if evt.action_id == begin_session_action.action_id:
                created_session.set_exception(BadActionError(evt))
                unsubscribe_all()

        usubscribe_invalid_action_error_handler = self.add_event_handler(
            "invalid_action", on_invalid_action
        )

        def on_mecharm_busy(evt: ArmBusy):
            if evt.action_id == begin_session_action.action_id:
                created_session.set_exception(SessionBusyError(evt))
                unsubscribe_all()

        unsubscribe_busy_error_handler = self.add_event_handler("busy", on_mecharm_busy)

        def unsubscribe_all():
            unsubscribe_success_handler()
            usubscribe_invalid_action_error_handler()
            unsubscribe_busy_error_handler()

        self.dispatch_action(begin_session_action)

        return created_session


class MechArmControllerSession:
    def __init__(
        self,
        client: ControllerClient,
        arm_application_id: str,
        session_id: int,
    ):
        self.client = client
        self.arm_application_id = arm_application_id
        self.session_id = session_id
        self.is_closed = False

    def move_arm(self, action: MoveAction) -> asyncio.Future[MoveComplete]:
        completed_action:Future[SessionReady] = asyncio.Future()

        def on_move_complete(evt: MoveComplete):

        self.client.dispatch_action(action)

        def unsubscribe_all():


        return completed_action

    def move_arm(self, action: MoveAction):
        self.dispatch_action(action)

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

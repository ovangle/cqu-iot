from abc import abstractmethod
import abc
from asyncio import Future
import dataclasses
import json
from typing import Callable
from paho.mqtt.client import Client
from mech_arm_mqtt.mech_arm_mqtt.controller import controller_client

from mech_arm_mqtt.schema.events import (
    SessionEvent,
    MoveAction,
    MoveComplete,
    MoveProgress,
    SessionReady,
)
from .client import MechArmClient

_NEXT_SESSION_ID = 0


def next_session_id():
    global _NEXT_SESSION_ID
    session_id = _NEXT_SESSION_ID
    _NEXT_SESSION_ID += 1
    return session_id


class MechArmSession(AsyncContextManager(MechArm)):
    def __init__(
        self,
        client: MechArmClient,
        controller_client_id: str,
    ):
        self.client = client
        self.controller_client_id = controller_client_id
        self.session_id = next_session_id()

    @property
    def mecharm_client_id(self):
        return self.client.mqtt_client_id

    def init(self, initial_coords: tuple[int, int, int]):
        self._unsubscribe_on_move = self.client.add_action_handler(
            "move", lambda action: self.on_move_action(action)
        )

    def destroy(self):
        if self._unsubscribe_on_move:
            self._unsubscribe_on_move()

    _unsubscribe_on_move: Callable[[], None] | None

    def get_current_mecharm_coords(self):
        return self.client.get_current_mecharm_coords()

    def move_arm(self):
        raise NotImplementedError

    def on_move_action(self, move_action: MoveAction):
        """
        Should initialise the movement of the
        """

        def emit_move_progress():
            current_coords = self.get_current_mecharm_coords()

            move_progress = MoveProgress(
                mech_arm_application_id=self.mecharm_client_id,
                current_coords=current_coords,
                dest_coords=move_action.to_coords,
            )

            self.emit(move_progress)

        move_instruction = self.move_arm_to(move_action.to_coords)

        move_complete = MoveComplete(
            mech_arm_application_id=self.mecharm_client_id,
        )
        self.emit(move_complete)

    def add_on_ready_handler(
        self, handler: Callable[[SessionReady], None]
    ) -> Callable[[], None]: ...

    def emit(self, evt: SessionEvent):
        payload = json.dumps(dataclasses.asdict(evt))
        self.client.publish(self.application_topic_url, payload)

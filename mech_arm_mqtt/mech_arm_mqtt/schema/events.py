from __future__ import annotations
import asyncio

import dataclasses
from datetime import timedelta
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Generic,
    Literal,
    Protocol,
    TypeVar,
    dataclass_transform,
)
from mech_arm_mqtt.mech_arm_mqtt.async_mycobot import TActionProgress

from mech_arm_mqtt.mech_arm_mqtt.schema.errors import MechArmError

from .model import (
    ActionProgress,
    ActionResponse,
    MechArmEvent,
    MechArmSessionEvent,
    MechArmSessionInfo,
    mecharm_event,
)
from .actions import MechArmAction, BeginSession, MechArmAction, MoveAction

# event type registry by name
_ALL_EVENT_TYPES: dict[str, type] = {}
# event type registry by error code.
_ERROR_EVENT_TYPES: dict[str, type] = {}


TEvent = TypeVar("TEvent", bound=MechArmEvent)


@mecharm_event("status")
class MechArmStatus(MechArmEvent):
    """
    Global event published to inform listeneers about the
    current status of the mecharm
    """

    idle: bool
    controller_client_id: str | None

    coords: tuple[int, int, int]
    joints: tuple[int, int, int]


@mecharm_event("action_received")
class ActionReceived(MechArmEvent):
    action: MechArmAction


@mecharm_event("bad_action", error_code=MechArmError.BAD_ACTION)
class BadAction(MechArmEvent):
    """
    The received action was unparesable as a schema action
    """

    action: MechArmAction
    message: str


class BadActionError(Exception):
    def __init__(self, action: MechArmAction, message: str):
        self.action = action
        self.message = message

        super().__init__(self, f"Invalid {self.action.name} action: {msg}")

    @property
    def event(self):
        return BadAction(action=self.action, message=self.message)


class SessionBusyError(Exception):
    def __init__(self, event: Busy):
        self.event = event


@mecharm_event("session_created")
class SessionCreated(ActionResponse[BeginSession]):
    session: MechArmSessionInfo


@mecharm_event("session_timeout")
class SessionTimeout(ActionResponse[BeginSession]):
    """
    Emitted when a session does not respond after
    the timeout specified in begin_session
    """

    session: MechArmSessionInfo
    timeout: int


@mecharm_event("session_destroyed")
class SessionDestroyed(MechArmEvent):
    """
    A session has terminated
    """

    session: MechArmSessionInfo
    exit_code: int


@mecharm_event("session_exit")
class SessionExit(MechArmSessionEvent):
    """
    The current session ended and the mechArm is awaiting connections
    """

    code: int


@mecharm_event("session_ready")
class SessionReady(MechArmSessionEvent):
    """
    Dispatched by the mechArm on the session topic to indicate
    that the mechArm is idle and ready to accept an action
    """

    pass


@mecharm_event("move_progress")
class MoveProgress(MechArmSessionEvent, ActionProgress[MoveAction]):
    current_coords: tuple[int, int, int]
    dest_coords: tuple[int, int, int]


@mecharm_event("move_complete")
class MoveComplete(MechArmSessionEvent, ActionResponse[MoveAction]):
    coords: tuple[int, int, int]


@mecharm_event("move_error", error_code=MechArmError.MOVE_ERROR)
class MoveError(MechArmSessionEvent, ActionResponse[MoveAction]):
    """
    Some error has occured within the device
    """

    message: str

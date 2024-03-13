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
    cast,
    dataclass_transform,
)

from mech_arm_mqtt.schema.core import MechArmErrorCode

from .core import (
    ActionErrorInfo,
    ActionProgress,
    ActionResponse,
    MechArmActionError,
    MechArmError,
    MechArmErrorInfo,
    MechArmEvent,
    SessionEvent,
    MechArmSessionInfo,
    mecharm_event,
)
from .actions import ExitSession, MechArmAction, BeginSession, MechArmAction, MoveAction

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


@mecharm_event("bad_action", error_code=MechArmErrorCode.BAD_ACTION)
class BadActionErrorInfo(MechArmErrorInfo):
    """
    The received action was unparesable as a schema action
    """

    action: MechArmAction
    message: str


class BadActionError(MechArmError):
    def __init__(self, action: MechArmAction, message: str):
        self.action = action
        self.message = message

        super().__init__(self, f"Invalid {self.action.name} action: {msg}")

    @property
    def as_event(self):
        return BadActionErrorInfo(action=self.action, message=self.message)


@mecharm_event("session_busy")
class SessionBusyInfo(ActionErrorInfo[BeginSession]):
    current_controller_id: str


class SessionBusy(MechArmActionError):
    def __init__(self, action: BeginSession, current_controller_id):
        super().__init__(
            MechArmErrorCode.SESSION_BUSY,
            action,
            message="session busy",
        )
        self.current_controller_id = current_controller_id

    def as_event(self) -> MechArmEvent:
        return SessionBusyInfo(
            action=cast(BeginSession, self.action),
            current_controller_id=self.current_controller_id,
        )


@mecharm_event("session_created")
class SessionCreated(ActionResponse[BeginSession]):
    session: MechArmSessionInfo


@mecharm_event("session_timeout")
class SessionTimeout(MechArmErrorInfo):
    """
    Emitted when a session does not respond after
    the timeout specified in begin_session
    """

    session: MechArmSessionInfo
    timeout: int

class SessionTimeoutError(MechArmActionError):
    def __init__(
            self,
            action: BeginSession,

    )

    def as_event(self):



@mecharm_event("session_destroyed")
class SessionDestroyed(ActionResponse[ExitSession]):
    """
    A session has terminated
    """

    session: MechArmSessionInfo
    exit_code: int


@mecharm_event("session_ready")
class SessionReady(SessionEvent):
    """
    Dispatched by the mechArm on the session topic to indicate
    that the mechArm is idle and ready to accept an action
    """

    pass


@mecharm_event("move_progress")
class MoveProgress(SessionEvent, ActionProgress[MoveAction]):
    current_coords: tuple[int, int, int]
    dest_coords: tuple[int, int, int]


@mecharm_event("move_complete")
class MoveComplete(SessionEvent, ActionResponse[MoveAction]):
    coords: tuple[int, int, int]


@mecharm_event("move_error", error_code=MechArmError.MOVE_ERROR)
class MoveError(MechArmSessionEvent, ActionResponse[MoveAction]):
    """
    Some error has occured within the device
    """

    message: str

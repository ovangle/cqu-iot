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

from .model import ActionError, ActionProgress, ActionResponse, MechArmEvent, MechArmSessionInfo, SessionEvent, mecharm_event
from .errors import MechArmError
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

        super().__init__(self, f"Bad '{self.action.name}' action: {message}")

    @property
    def event(self):
        return BadAction(action=self.action, message=self.message)

@mecharm_event("session_busy", error_code=MechArmError.SESSION_BUSY)
class SessionBusy(ActionError[BeginSession]):
    # The session which is currently using the mecharm
    session: MechArmSessionInfo

class SessionBusyError(Exception):
    def __init__(self, action: BeginSession, session: MechArmSessionInfo):
        self.action = action
        self.session = session
        super().__init__(
            f"begin_session: Already in use by '{session.remote_client_id}'"
        )

    @property
    def event(self):
        return SessionBusy(action=self.action, session=self.session)

 
@mecharm_event("session_timeout")
class SessionTimeout(ActionError[BeginSession]):
    """
    Emitted when a session does not respond after
    the timeout specified in begin_session
    """

    session: MechArmSessionInfo
    timeout: int


class SessionTimeoutError(Exception):
    def __init__(self, action: BeginSession, timeout: int):
        self.action = action
        self.timeout = timeout
        super().__init__(f"Attempt to begin session timed out after {timeout} seconds")

    @property
    def event(self):
        return SessionTimeout(
            action=self.action,
            timeout=self.timeout
        )


@mecharm_event("session_created")
class SessionCreated(SessionEvent, ActionResponse[BeginSession]):
    session: MechArmSessionInfo


@mecharm_event("session_destroyed")
class SessionDestroyed(SessionEvent, ActionResponse[ExitSession]):
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
class MoveError(SessionEvent, ActionError[MoveAction]):
    """
    Some error has occured within the device
    """

    message: str

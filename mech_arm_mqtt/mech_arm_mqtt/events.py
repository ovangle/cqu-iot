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

from .core import (
    ActionErrorInfo,
    ActionProgress,
    ActionResponse,
    MechArmActionError,
    MechArmError,
    MechArmErrorCode,
    MechArmErrorInfo,
    MechArmEvent,
    SessionAction,
    SessionEvent,
    MechArmSessionInfo,
    mecharm_event,
)
from .actions import ExitSession, MechArmAction, BeginSession, MechArmAction, MoveAction


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

    def as_error(self):
        return BadActionError(self.action, self.message)


class BadActionError(MechArmActionError[Any]):
    def __init__(self, action: MechArmAction, message: str):

        super().__init__(
            MechArmErrorCode.BAD_ACTION,
            action,
            message=f"Unparesable {self.action.name} action: {message}"
        )
        self.message = message

    @property
    def as_event(self):
        return BadActionErrorInfo(action=self.action, message=self.message)


@mecharm_event("no_current_session", error_code=MechArmErrorCode.NO_CURRENT_SESSION)
class NoCurrentSessionErrorInfo(ActionErrorInfo[SessionAction]):
    def as_error(self):
        return NoCurrentSession(self.action)

class NoCurrentSession(MechArmActionError[SessionAction]):
    def __init__(self, action: SessionAction):
        super().__init__(
            MechArmErrorCode.NO_CURRENT_SESSION,
            action,
            message=f"Cannot execute {action.name} without a current session"
        )

    def as_event(self) -> MechArmEvent:
        return NoCurrentSessionErrorInfo(
            action=self.action
        )

@mecharm_event("session_busy", error_code=MechArmErrorCode.SESSION_BUSY)
class SessionBusyErrorInfo(ActionErrorInfo[BeginSession]):
    current_controller_id: str

    def as_error(self):
        return SessionBusy(self.action, self.current_controller_id)


class SessionBusy(MechArmActionError[BeginSession]):
    def __init__(self, action: BeginSession, current_controller_id):
        super().__init__(
            MechArmErrorCode.SESSION_BUSY,
            action,
            message="session busy",
        )
        self.current_controller_id = current_controller_id

    def as_event(self) -> MechArmEvent:
        return SessionBusyErrorInfo(
            action=cast(BeginSession, self.action),
            current_controller_id=self.current_controller_id,
        )


@mecharm_event("session_created")
class SessionCreated(ActionResponse[BeginSession]):
    session: MechArmSessionInfo


@mecharm_event("session_timeout", error_code=MechArmErrorCode.SESSION_TIMEOUT)
class SessionTimeoutErrorInfo(MechArmErrorInfo):
    """
    Emitted when a session does not respond after
    the timeout specified in begin_session
    """

    session: MechArmSessionInfo
    timeout: int

    def as_error(self):
        return SessionTimeoutError(self.session, self.timeout)

class SessionTimeoutError(MechArmError):
    def __init__(
            self,
            session: MechArmSessionInfo,
            timeout: int
    ):
        super().__init__(
            MechArmErrorCode.SESSION_TIMEOUT,
            message=f"Session '{session.id}' timed out after {timeout} seconds"
        )
        self.session = session
        self.timeout = timeout

    def as_event(self):
        return SessionTimeoutErrorInfo(
            session=self.session,
            timeout=self.timeout
        )


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


@mecharm_event("move_error", error_code=MechArmErrorCode.MOVE_ERROR)
class MoveErrorInfo(SessionEvent, ActionErrorInfo[MoveAction]):
    """
    Some error has occured within the device
    """

    message: str

    def as_error(self):
        return MoveError(self.action, self.session, self.message)

class MoveError(MechArmActionError[MoveAction]):
    def __init__(self, action: MoveAction, session: MechArmSessionInfo, message: str):
        super().__init__(
            MechArmErrorCode.MOVE_ERROR,
            action,
            message=message
        )
        self.session = session

    def as_event(self) -> MechArmEvent:
        return MoveErrorInfo(
            action=self.action,
            session=self.session,
            message=self.message
        )
    

        


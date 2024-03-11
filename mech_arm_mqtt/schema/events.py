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

from .actions import MechArmAction, BeginSession, MechArmAction, MoveAction

# event type registry by name
_ALL_EVENT_TYPES: dict[str, type] = {}
# event type registry by error code.
_ERROR_EVENT_TYPES: dict[str, type] = {}


def action_from_json_object(json: dict[str, Any]) -> MechArmEvent:
    try:
        evt_name = json["name"]
    except KeyError:
        raise ValueError('Malformed event object. Must include "name" attr')
    try:
        evt_cls = _ALL_EVENT_TYPES[evt_name]
    except KeyError:
        raise ValueError("Unrecognised event type {evt_name}")

    del json["name"]
    return evt_cls(**json)


def event_to_json_object(evt: MechArmEvent) -> dict[str, Any]:
    return dict(
        name=type(evt).name, error_code=type(evt).error_code, **dataclasses.asdict(evt)
    )


@dataclasses.dataclass(kw_only=True)
class MechArmEvent:
    name: ClassVar[str]
    type: ClassVar[Literal["broadcast", "begin_session", "session"]]
    error_code: ClassVar[str | None] = None


TEvent = TypeVar("TEvent", bound=MechArmEvent)


class EventTrigger(Generic[TEvent]):
    def loop(self):
        return asyncio.get_running_loop()


@dataclass_transform(kw_only_default=True)
def mecharm_event(name: str, error_code: str | None = None):
    def decorator(cls: type[TEvent]):
        if name in _ALL_EVENT_TYPES:
            raise TypeError("Class with name already registered")
        _ALL_EVENT_TYPES[name] = cls
        cls.name = name

        if error_code is not None:
            if error_code in _ERROR_EVENT_TYPES:
                raise TypeError(
                    "class with error code '{error_code}' already registered"
                )
            _ERROR_EVENT_TYPES[error_code] = cls
            cls.error_code = error_code
        return dataclasses.dataclass(kw_only=True)(cls)

    return decorator


@dataclasses.dataclass(kw_only=True)
class BroadcastEvent(MechArmEvent):
    """
    A broadcast event is a generic status event that
    is emitted for all listeners
    """

    type = "broadcast"


class MechArmStatusEvent(BroadcastEvent):
    """
    Global event published to inform listeneers about the
    current status of the mecharm
    """

    idle: bool
    controller_client_id: str | None

    coords: tuple[int, int, int]
    joints: tuple[int, int, int]


TAction = TypeVar("TAction", bound=MechArmAction)


@dataclasses.dataclass(kw_only=True)
class ActionResponse(MechArmEvent, Generic[TAction]):
    action: MechArmAction


@mecharm_event("action_received")
class ActionReceived(ActionResponse[Any]):
    pass


@mecharm_event("invalid_action", "invalid_action")
class BadAction(ActionResponse[Any]):
    """
    The received action was unparesable as a schema action
    """

    message: str


class InvalidActionError(Exception):
    def __init__(self, action: BadAction):
        self.action = action


class BeginSessionResponseEvent(ActionResponse[BeginSession]):
    type = "begin_session"


@mecharm_event("busy", "busy")
class Busy(BeginSessionResponseEvent):
    """
    The mecharm cannot create a session because it is in use
    by another remote.
    """

    # The controller client ID which has the current session
    controller_client_id: str


class MechArmBusyError(Exception):
    def __init__(self, event: Busy):
        self.event = event


@dataclasses.dataclass(kw_only=True)
class SessionInfo:
    mecharm_client_id: str
    controller_client_id: str
    session_id: int

    qos: int
    timeout: int


@mecharm_event("session_created")
class SessionCreated(BeginSessionResponseEvent):
    session: SessionInfo


@dataclasses.dataclass(kw_only=True)
class SessionEvent(MechArmEvent):
    """
    Base event type for all messages on a session channel
    """

    session: SessionInfo | None = None


@mecharm_event("session_timeout", "session_timeout")
class SessionTimeout(SessionEvent):
    """
    The session timed out while waiting for a response
    """

    pass


@mecharm_event("session_exit")
class SessionExit(SessionEvent):
    """
    The current session ended and the mechArm is awaiting connections
    """

    pass


@dataclasses.dataclass
class SessionReady(SessionEvent):
    """
    Dispatched by the mechArm on the session topic to indicate
    that the mechArm is idle and ready to accept an action
    """

    pass


@mecharm_event("session_not_ready", "session_not_ready")
class SessionNotReady(SessionEvent, ActionResponse[MoveAction]):
    """
    Dispatched by the mecharm on the session topic to indicate
    that the arm isn't ready to receive commands
    """

    pass


class SessionNotReadyError(Exception):
    def __init__(self, session: SessionInfo, action: MoveAction):
        super().__init__("session not ready")
        self.event = SessionNotReady(session=session, action=action)


@dataclasses.dataclass
class MoveProgress(SessionEvent, ActionResponse[MoveAction]):
    name = "move_progress"
    current_coords: tuple[int, int, int]
    dest_coords: tuple[int, int, int]


@dataclasses.dataclass(kw_only=True)
class MoveComplete(SessionEvent, ActionResponse[MoveAction]):
    name = "move_complete"
    coords: tuple[int, int, int]

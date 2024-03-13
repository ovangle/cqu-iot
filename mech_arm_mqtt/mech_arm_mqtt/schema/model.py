import dataclasses
from typing import Any, ClassVar, Generic, TypeVar, dataclass_transform


@dataclasses.dataclass(kw_only=True)
class MechArmSessionInfo:
    id: int
    client_id: str
    remote_client_id: str


_NEXT_ACTION_ID = 0


def next_action_id():
    global _NEXT_ACTION_ID
    action_id = _NEXT_ACTION_ID
    _NEXT_ACTION_ID += 1
    return action_id


@dataclasses.dataclass(kw_only=True)
class MechArmAction:
    """
    Actions represent a commands which can be passed to a mechArm
    in order to generate responses
    """
    __action_name__: ClassVar[str]

    name: str = ''
    id: int = dataclasses.field(default_factory=next_action_id)
    session: MechArmSessionInfo | None = None

    is_complete: bool = False
    is_error: bool = False
    error_code: int | None = None

    def __post_init__(self, **kwargs):
        object.__setattr__(self, 'name', type(self).__action_name__)

    def mark_complete(self, error_code: int | None = None):
        self.is_complete = True
        self.is_error = bool(error_code)
        self.error_code = error_code


def action_from_json_object(json: dict[str, Any]):
    try:
        action_name = json["name"]
    except KeyError:
        raise ValueError('Object does not have a root key "name"')

    try:
        action_cls = _ALL_ACTION_TYPES[action_name]
    except KeyError:
        raise ValueError(f"Cannot parse action. Unrecognised action '{action_name}'")

    del json["name"]
    return action_cls(**json)


def action_to_json_object(action: MechArmAction):
    return dataclasses.asdict(action)


_ALL_ACTION_TYPES: dict[str, type[MechArmAction]] = {}

@dataclass_transform(kw_only_default=True)
def mecharm_action(name: str):
    def decorator(cls: type[MechArmAction]) -> type[MechArmAction]:
        setattr(cls, '__action_name__', name)
        return dataclasses.dataclass(kw_only=True)(cls)

    return decorator


@dataclasses.dataclass(kw_only=True)
class SessionAction(MechArmAction):
    pass


@dataclasses.dataclass(kw_only=True)
class MechArmEvent:
    """
    Represents a message sent by a mecharm to interested subscribers
    """
    __event_name__: ClassVar[str]
    __event_error_code__: ClassVar[int | None]

    name: str 
    error_code: int | None = None

    # The source action, if there is one
    action: MechArmAction | None = None

    session: MechArmSessionInfo | None = None

    def __post_init__(self):
        setattr(self, 'name', self.__name__)
        setattr(self, 'error_code', self.__error_code__)



_ALL_EVENT_TYPES: dict[str, type[MechArmEvent]]


@dataclass_transform(kw_only_default=True)
def mecharm_event(name: str, *, error_code: int | None = None):
    def decorator(cls: type[MechArmEvent]):
        _ALL_EVENT_TYPES[name] = cls
        object.__setattr__(cls, "__event_name__", name)
        object.__setattr__(cls, "__event_error_code__", error_code)
        return dataclasses.dataclass(kw_only=True)(cls)

    return decorator


def event_from_json_object(json: dict[str, Any]) -> MechArmEvent:
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
class ErrorEvent(MechArmEvent):
    error_code: int

@dataclasses.dataclass(kw_only=True)
class BroadcastEvent(MechArmEvent):
    pass

@dataclasses.dataclass(kw_only=True)
class SessionEvent(MechArmEvent):
    session: MechArmSessionInfo

TAction = TypeVar('TAction', bound=MechArmAction)

@dataclasses.dataclass(kw_only=True)
class ActionEvent(MechArmEvent, Generic[TAction]):
    action: TAction

@dataclasses.dataclass(kw_only=True)
class ActionError(ActionEvent[TAction], ErrorEvent, Generic[TAction]):
    pass

@dataclasses.dataclass(kw_only=True)
class ActionResponse(ActionEvent[TAction], ErrorEvent, Generic[TAction]):
    pass

@dataclasses.dataclass(kw_only=True)
class ActionProgress(ActionEvent, ErrorEvent, Generic[TAction]):
    progress_id: int

import dataclasses
from typing import Any, ClassVar, Literal, Protocol, TypeVar, dataclass_transform


@dataclasses.dataclass(kw_only=True)
class MechArmSessionInfo:
    client_id: str
    session_id: int
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

    name: str
    id: int = dataclasses.field(default_factory=next_action_id)
    session: MechArmSessionInfo | None = None


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
    def cls_init(self, **kwargs):
        if kwargs.get("name", name) != name:
            raise ValueError(f"Invalid name for {type(self).__name__} instance")
        kwargs["name"] = name

        for field in dataclasses.fields(self):
            object.__setattr__(self, field.name, kwargs.get(field.name))

        if hasattr(self, "__post_init__"):
            self.__post_init__()

    def decorator(cls: type[TEvent]):
        object.__setattr__(cls, "__init__", cls_init)
        return dataclasses.dataclass(kw_only=True, init=False)(cls)

    return decorator


class SessionAction(MechArmAction, Protocol):
    session: MechArmSessionInfo


@dataclasses.dataclass(kw_only=True)
class MechArmEvent:
    """
    Represents a message sent by a mecharm to interested subscribers
    """

    name: str
    error_code: int | None = None

    # The source action, if there is one
    action: MechArmAction | None = None

    session: MechArmSessionInfo | None = None


TEvent = TypeVar("TEvent", bound=MechArmEvent)

_ALL_EVENT_TYPES: dict[str, type[TEvent]]


@dataclass_transform(kw_only_default=True)
def mecharm_event(name: str, *, error_code: int | None = None):
    def cls_init(self, **kwargs):
        if kwargs.get("name", name) != name:
            raise ValueError(f"Invalid name for {type(self).__name__} instance")
        kwargs["name"] = name

        if kwargs.get("error_code", error_code) != error_code:
            raise ValueError(f"Invalid error code for {type(self).__name__} instance")
        kwargs["error_code"] = error_code

        for field in dataclasses.fields(self):
            object.__setattr__(self, field.name, kwargs.get(field.name))

        if hasattr(self, "__post_init__"):
            self.__post_init__()

    def decorator(cls: type[TEvent]):
        _ALL_EVENT_TYPES[name] = cls
        object.__setattr__(cls, "__init__", cls_init)
        return dataclasses.dataclass(kw_only=True, init=False)(cls)

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


class ErrorEvent(MechArmEvent, Protocol):
    error_code: int


class ActionResponse(MechArmEvent, Protocol):
    action: MechArmAction


class ActionProgress(MechArmEvent, Protocol):
    action: MechArmAction
    progress_id: int

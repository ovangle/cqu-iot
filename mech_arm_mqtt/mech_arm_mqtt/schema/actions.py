from __future__ import annotations
from asyncio import StreamReader, Task
import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, Protocol

_ALL_ACTIONS: dict[str, Any] = {}

_NEXT_ACTION_ID: int = 0


def next_action_id():
    global _NEXT_ACTION_ID
    next_action_id = _NEXT_ACTION_ID
    _NEXT_ACTION_ID += 1
    return next_action_id


def action_from_json_object(json: dict[str, Any]):
    try:
        action_name = json["name"]
    except KeyError:
        raise ValueError('Object does not have a root key "name"')

    try:
        action_cls = _ALL_ACTIONS[action_name]
    except KeyError:
        raise ValueError(f"Cannot parse action. Unrecognised action '{action_name}'")

    del json["name"]
    return action_cls(**json)

def action_to_json_object(action: MechArmAction):
    return dataclasses.asdict(action)

@dataclasses.dataclass(kw_only=True)
class MechArmAction:
    """
    Actions represent commands which a remote controller
    can issue in order to trigger a response from the
    mechArm
    """

    name: ClassVar[str]
    action_id: int = dataclasses.field(default_factory=next_action_id)

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        if isinstance(cls.name, str):
            _ALL_ACTIONS[cls.name] = cls


@dataclasses.dataclass
class BeginSession(MechArmAction):
    name = "begin_session"
    controller_client_id: str
    mecharm_application_id: str


@dataclasses.dataclass
class SessionAction(MechArmAction):
    session_id: int


@dataclasses.dataclass
class MoveAction(SessionAction):
    to_coords: tuple[int, int, int]


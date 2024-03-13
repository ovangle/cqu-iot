from __future__ import annotations
from asyncio import StreamReader, Task
import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, Protocol

from .model import MechArmAction, MechArmSessionInfo, SessionAction, mecharm_action, mecharm_event


@mecharm_action("begin_session")
class BeginSession(MechArmAction):
    mecharm_client_id: str 
    remote_client_id: str


@mecharm_action("end_session")
class ExitSession(SessionAction):
    exit_code: int


@mecharm_action("move")
class MoveAction(SessionAction):
    session: MechArmSessionInfo
    to_coords: tuple[int, int, int]

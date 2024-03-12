from __future__ import annotations
from asyncio import StreamReader, Task
import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, Protocol

from .model import MechArmAction, mecharm_action, mecharm_event


@mecharm_action("begin_session")
class BeginSession(MechArmAction):
    mecharm_client_id: str | None = None


@mecharm_action("move")
class MoveAction(MechArmAction):
    to_coords: tuple[int, int, int]

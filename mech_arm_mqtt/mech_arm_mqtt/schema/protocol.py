from __future__ import annotations
from abc import abstractmethod

from typing import AsyncContextManager, Protocol, TypeVar

from .actions import MoveAction, BeginSession
from .events import MoveComplete, SessionExit

class MechArmSession(Protocol):
    @abstractmethod
    async def move(self, action: MoveAction) -> MoveComplete:
        pass

    @abstractmethod
    async def exit(self) -> SessionExit:
        ...

TSession = TypeVar('TSession', bound=MechArmSession, covariant=True)

class MechArmClient(Protocol[TSession]):
    @abstractmethod
    def current_session(self) -> MechArmSession | None:
        ...

    @abstractmethod
    async def begin_session(self, session: BeginSession) -> AsyncContextManager[TSession]:
        ...

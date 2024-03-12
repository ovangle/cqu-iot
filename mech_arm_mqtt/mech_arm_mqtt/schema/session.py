from __future__ import annotations
from abc import ABC, abstractmethod
from typing import (
    Any,
    AsyncContextManager,
    AsyncIterable,
    Awaitable,
    Callable,
    Protocol,
    Self,
)


from .model import MechArmAction, MechArmEvent, MechArmSessionInfo

from .actions import MoveAction, SessionCreated
from .events import (
    ActionReceived,
    MechArmStatus,
    MoveComplete,
    MoveError,
    MoveProgress,
    SessionDestroyed,
    SessionExit,
    SessionReady,
)


class MechArm(ABC):
    @abstractmethod
    async def events(self) -> AsyncIterable[MechArmEvent]:
        # All broadcast events of the mech arm
        raise NotImplementedError()

    async def status_events(self) -> AsyncIterable[MechArmStatus]:
        async for event in self.events():
            if isinstance(event, MechArmStatus):
                yield event

    async def action_received_events(self) -> AsyncIterable[ActionReceived]:
        async for event in self.events():
            if isinstance(event, ActionReceived):
                yield event

    async def session_created_events(self) -> AsyncIterable[SessionCreated]:
        async for event in self.events():
            if isinstance(event, SessionCreated):
                yield event

    async def session_destroyed_events(self) -> AsyncIterable[SessionDestroyed]:
        async for event in self.events():
            if isinstance(event, SessionDestroyed):
                yield event

    @abstractmethod
    async def session(self) -> AsyncContextManager[MechArmSession]:
        raise NotImplementedError()


class MechArmSession(ABC):
    session_id: int

    @abstractmethod
    def events(self) -> AsyncIterable[MechArmEvent]:
        raise NotImplementedError

    async def await_exit(self) -> SessionExit:
        async for event in self.events():
            if isinstance(event, SessionExit) and event.session.id == self.session_id:
                return event
        raise RuntimeError("Session did not exit gracefully")

    async def session_ready_events(self) -> AsyncIterable[SessionReady]:
        """
        The session will emit a session ready event every time the
        arm is ready to receive new instructions
        """
        async for event in self.events():
            if isinstance(event, SessionReady) and event.session.id == self.session_id:
                yield event

    async def await_next_ready(self) -> SessionReady | None:
        """
        Await the next session ready event, or None if the session exits
        before the next ready event
        """
        async for event in self.session_ready_events():
            return event
        raise RuntimeError("Session did not exit gracefully")

    async def move_completed_events(
        self, action: MoveAction | None = None
    ) -> AsyncIterable[MoveComplete]:
        async for event in self.events():
            if not (
                isinstance(event, MoveComplete) and event.session.id == self.session_id
            ):
                continue

            if action and event.action.id != action.id:
                continue

            yield event

    async def move_progress_events(
        self, action: MoveAction | None = None
    ) -> AsyncIterable[MoveProgress]:
        async for event in self.events():
            if not (isinstance(event, MoveProgress) and event.session.id == self.id):
                continue

            if action and event.action.id != action.id:
                continue

            yield event

    async def move_error_events(
        self, action: MoveAction | None = None
    ) -> AsyncIterable[MoveError]:
        async for event in self.events():
            if not (isinstance(event, MoveError) and event.session.id == self.id):
                continue

            if action and event.action.id != action.id:
                continue

            yield event

    @abstractmethod
    async def move(
        self,
        action: MoveAction,
        on_progress: Callable[[MoveProgress], None] | None = None,
    ) -> MoveComplete:
        raise NotImplementedError

    @abstractmethod
    def exit(self, exit_code: int = 0) -> Awaitable[SessionExit]:
        raise NotImplementedError

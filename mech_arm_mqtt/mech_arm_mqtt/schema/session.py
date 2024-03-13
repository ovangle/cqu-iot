from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
import contextlib
import dataclasses
from typing import (
    Any,
    AsyncContextManager,
    AsyncGenerator,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Protocol,
    Self,
    TypeVar,
)


from .core import (
    ActionErrorInfo,
    ActionResponse,
    MechArmAction,
    MechArmEvent,
    MechArmInfo,
    MechArmSessionInfo,
    SessionAction,
    SessionEvent,
)

from .actions import BeginSession, ExitSession, MoveAction
from .events import (
    ActionReceived,
    BadActionErrorInfo,
    MechArmStatus,
    MoveComplete,
    MoveError,
    MoveProgress,
    SessionBusyInfo,
    SessionCreated,
    SessionDestroyed,
    SessionReady,
)


class MechArm(ABC):
    def __init__(self, client_id: str):
        self.client_id = client_id

        self._event_queue = asyncio.Queue[MechArmEvent]()
        self._closed = False

    @property
    def info(self):
        return MechArmInfo(client_id=self.client_id)

    @abstractmethod
    async def events(self) -> AsyncIterator[MechArmEvent]: ...

    async def status_events(self) -> AsyncIterator[MechArmStatus]:
        async for event in self.events():
            if isinstance(event, MechArmStatus):
                yield event

    async def action_received_events(self) -> AsyncIterator[ActionReceived]:
        async for event in self.events():
            if isinstance(event, ActionReceived):
                yield event

    async def session_create_error_events(
        self,
    ) -> AsyncIterator[ActionErrorInfo[BeginSession]]:
        async for event in self.events():
            if (
                isinstance(event, BadActionErrorInfo)
                and event.action.name == "begin_session"
            ):
                yield event
            if isinstance(event, SessionBusyInfo):
                yield event

    async def session_created_events(self) -> AsyncIterator[SessionCreated]:
        async for event in self.events():
            if isinstance(event, SessionCreated):
                yield event

    async def session_destroyed_events(self) -> AsyncIterator[SessionDestroyed]:
        async for event in self.events():
            if isinstance(event, SessionDestroyed):
                yield event

    @abstractmethod
    async def session(self) -> AsyncContextManager[MechArmSession]:
        raise NotImplementedError


class MechArmSession(ABC):
    session_id: int
    client_id: str
    remote_client_id: str

    action_queue: asyncio.Queue[SessionAction]

    @abstractmethod
    def events(self) -> AsyncIterable[MechArmEvent]:
        raise NotImplementedError

    TAction = TypeVar("TAction", bound=MechArmAction)

    @abstractmethod
    def on_action(self, action: TAction) -> Awaitable[ActionResponse[TAction]]: ...

    @property
    def info(self) -> MechArmSessionInfo:
        return MechArmSessionInfo(
            id=self.session_id,
            client_id=self.client_id,
            remote_client_id=self.remote_client_id,
        )

    async def await_exit(self) -> SessionDestroyed:
        async for event in self.events():
            if (
                isinstance(event, SessionDestroyed)
                and event.session.id == self.session_id
            ):
                return event
        raise RuntimeError("Session did not exit gracefully")

    async def session_ready_events(self) -> AsyncIterator[SessionReady]:
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
        return await anext(self.session_ready_events(), None)

    async def move_completed_events(
        self, action: MoveAction | None = None
    ) -> AsyncIterator[MoveComplete]:
        async for event in self.events():
            if not (
                isinstance(event, MoveComplete) and event.session.id == self.session_id
            ):
                continue

            if action and event.action.id != action.id:
                continue

            yield event

            if action and action.is_complete:
                return

    async def move_progress_events(
        self, action: MoveAction | None = None
    ) -> AsyncIterator[MoveProgress]:
        async for event in self.events():
            if not (
                isinstance(event, MoveProgress) and event.session.id == self.session_id
            ):
                continue

            if action and event.action.id != action.id:
                continue

            yield event

            if action and action.is_complete:
                return

    async def move_error_events(
        self, action: MoveAction | None = None
    ) -> AsyncIterator[MoveError]:
        async for event in self.events():
            if not (
                isinstance(event, MoveError) and event.session.id == self.session_id
            ):
                continue

            if action and event.action.id != action.id:
                continue

            yield event

            if action and action.is_complete:
                return

    async def move(
        self,
        action: MoveAction,
        on_progress: Callable[[MoveProgress], None] | None = None,
    ) -> MoveComplete:
        if on_progress:

            async def emit_on_progress():
                async for progress_event in self.move_progress_events(action):
                    on_progress(progress_event)

            loop = asyncio.get_running_loop()
            loop.call_soon(emit_on_progress())

        await self.action_queue.put(action)
        move_complete = await anext(self.move_completed_events(action))

        action.mark_complete()
        return move_complete

    async def exit(self, exit_code: int = 0) -> SessionDestroyed:
        action = ExitSession(
            name="exit_session", session=self.info, exit_code=exit_code
        )
        await self.action_queue.put(action)

        return await self.await_exit()

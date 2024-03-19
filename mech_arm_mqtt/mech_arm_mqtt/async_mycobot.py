from __future__ import annotations

from abc import abstractmethod
from asyncio import AbstractEventLoop, Future
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time
from types import TracebackType
from typing import (
    Any,
    AsyncContextManager,
    AsyncGenerator,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Generic,
    Literal,
    Self,
    TypeAlias,
    TypeVar,
    cast,
)
from pymycobot import MyCobot  # type: ignore

from .core import (
    ActionErrorInfo, 
    ActionResponse, 
    MechArmSessionInfo, 
    SessionAction,
    MechArmAction, 
    MechArmEvent,
    ActionProgress,
)

from .actions import BeginSession, MoveAction
from .events import (
    MoveComplete,
    MoveProgress,
    SessionCreated,
    SessionDestroyed,
    SessionReady,
)

TAction = TypeVar("TAction", bound=MechArmAction)

ProgressCallback = Callable[[ActionProgress[TAction]], None]

class MyCobotTask(Generic[TAction]):
    def __init__(
        self, 
        context: MyCobotTaskContext[TAction],
        action: TAction
    ):
        self.context = context
        self.action = action

    @property
    def bot(self) -> MyCobot:
        return self.context.bot

    @property
    def session_info(self) -> MechArmSessionInfo:
        return self.context.session_info

    @abstractmethod
    def __call__(self) -> ActionResponse[TAction]:
        """
        Runs the task given the current bot.
        Raise an ActionError if the task cannot be completed.
        """
        raise NotImplementedError


class MyCobotTaskContext(AsyncContextManager, Generic[TAction]):

    def __init__(
        self, 
        session: AsyncMyCobot,
        on_progress: Callable[[ActionProgress[TAction]], None] | None = None
    ):
        self.session = session

        self._executor = session._executor
        self._loop = asyncio.get_running_loop()

        self._progress_queue = asyncio.Queue[ActionProgress[TAction]]()
        self.on_progress = on_progress

        self._completed = False
        self._exc_type: type[BaseException] | None = None
        self._exc_value: BaseException | None = None
        self._exc_tb: TracebackType | None = None

    async def progress(self) -> AsyncIterator[ActionProgress[TAction]]:
        while not self._completed:
            if not self._progress_queue.empty():
                yield await self._progress_queue.get()

    @property
    def bot(self):
        return MyCobot(self.session.mecharm_port)

    @property
    def session_info(self):
        return self.session.session_info

    async def __aenter__(self) -> MyCobotTaskContext[TAction]:
        return self

    async def __aexit__(
        self,
        __exc_type: type[BaseException] | None = None,
        __exc_value: BaseException | None = None,
        __exc_tb: TracebackType | None = None,
    ) -> bool | None:
        self._completed = True
        self._exc_type = __exc_type
        self._exc_value = __exc_value
        self._exc_tb = __exc_tb
        return None

    async def run(self, action: TAction):
        task = self.session.task_factory(self, action)
        return await self._loop.run_in_executor(self._executor, task, action)

    def add_progress(self, progress: ActionProgress[TAction]):
        assert self._progress_queue
        self._loop.call_soon_threadsafe(self._progress_queue.put, progress)


class MoveTask(MyCobotTask[MoveAction]):
    def __init__(self, context: MyCobotTaskContext[MoveAction], action: MoveAction):
        super().__init__(context, action)
        self.progress_id = 0

    def emit_progress(self):
        coords = self.bot.get_coords()
        self.context.add_progress(MoveProgress(
            name="move_progress",
            action=self.action,
            session=self.session_info,
            progress_id=self.progress_id,
            current_coords=coords,
            dest_coords=self.action.to_joint_angles
        ))
        self.progress_id += 1

    def __call__(self):
        self.progress_id = 0
        self.bot.send_coords(list(self.action.to_joint_angles))

        while self.bot.is_moving:
            self.emit_progress(self.action)
            time.sleep(5)

        return MoveComplete(
            name="move_complete",
            error_code=None,
            action=self.action, 
            session=self.session_info,
            coords=self.action.to_joint_angles
        )


class AsyncMyCobot:
    def __init__(
        self, session_id: int, _begin_session: BeginSession, mecharm_port: int
    ):
        self.session_id = session_id
        self._begin_session = _begin_session
        self.mecharm_port = mecharm_port
        self._loop = asyncio.get_running_loop()

        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._action_queue = asyncio.Queue[SessionAction]()
        self._event_queue: asyncio.Queue[MechArmEvent] = asyncio.Queue()

    @property
    def session_info(self):
        return MechArmSessionInfo(
            id=self.session_id,
            client_id=self._begin_session.client_id,
            remote_client_id=self._begin_session.remote_client_id
        )

    def task_factory(self, context: MyCobotTaskContext, action: TAction) -> MyCobotTask[TAction]:
        match action:
            case MoveAction():
                return cast(MyCobotTask[TAction], MoveTask(context, action))
            case _:
                raise ValueError(f"Unhandled task: {action.name}")

    async def move(
        self, 
        action: MoveAction, 
        on_progress: Callable[[MoveProgress], None] | None= None,
    ) -> MoveComplete:
        async with MyCobotTaskContext[MoveAction](self) as context:
            if on_progress:
                async def call_on_progress():
                    async for progress in context.progress:
                        on_progress(progress)
                self._loop.call_soon(call_on_progress)

            return await context.run(action)

    async def __aenter__(self) -> AsyncMyCobot:
        self._executor = ThreadPoolExecutor(max_workers=1)
        return self
    
    async def __aexit__(self, __exc_type, __exc_value, __exc_traceback) -> None:
        self._executor.shutdown()

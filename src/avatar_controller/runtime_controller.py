from __future__ import annotations

from dataclasses import dataclass

from avatar_controller.idle_loop import IdleLoopProfileBuilder
from avatar_controller.playback_cursor import PlaybackCursor, PlaybackFrame
from avatar_controller.playback_planner import PlaybackPlan, PlaybackPlanner
from avatar_controller.playback_queue import (
    PlaybackItem,
    PlaybackQueueResolver,
    ResolvedPlaybackQueue,
)
from avatar_controller.segments import SegmentSet
from avatar_controller.state_machine import AvatarCommand, AvatarState


@dataclass(frozen=True)
class RuntimeStatus:
    current_state: AvatarState
    current_segment_name: str
    current_frame_index: int
    is_loop: bool
    pending_commands: list[AvatarCommand]
    last_command: AvatarCommand | None
    active_once_segments: list[str]
    active_loop_segment: str


class AvatarRuntimeController:
    def __init__(
        self,
        segment_set: SegmentSet,
        max_pending_commands: int = 2,
        dedupe_pending_commands: bool = True,
        idle_loop_mode: str = "full",
    ) -> None:
        self._planner = PlaybackPlanner(segment_set)
        idle_loop_profiles = IdleLoopProfileBuilder(segment_set, idle_loop_mode).build()
        self._resolver = PlaybackQueueResolver(segment_set, idle_loop_profiles)
        self._max_pending_commands = max(0, max_pending_commands)
        self._dedupe_pending_commands = dedupe_pending_commands
        self._pending_commands: list[AvatarCommand] = []
        self._last_command: AvatarCommand | None = None

        self._active_queue = self._resolve_initial_queue()
        self._cursor = PlaybackCursor(self._active_queue)

    def submit_command(self, command: AvatarCommand) -> bool:
        if not self._planner.supports_command(command):
            return False

        if self._cursor.peek().is_loop:
            self._pending_commands.clear()
            self._activate_command(command)
            return True

        return self._enqueue_pending_command(command)

    def step(self) -> PlaybackFrame:
        if self._cursor.peek().is_loop and self._pending_commands:
            self._activate_command(self._pending_commands.pop(0))

        return self._cursor.step()

    def status(self) -> RuntimeStatus:
        current_frame = self._cursor.peek()
        return RuntimeStatus(
            current_state=self._planner.state,
            current_segment_name=current_frame.segment_name,
            current_frame_index=current_frame.frame_index,
            is_loop=current_frame.is_loop,
            pending_commands=list(self._pending_commands),
            last_command=self._last_command,
            active_once_segments=[item.segment_name for item in self._active_queue.items],
            active_loop_segment=self._active_queue.loop_item.segment_name,
        )

    def clear_pending_commands(self) -> None:
        self._pending_commands.clear()

    @property
    def active_loop_item(self) -> PlaybackItem:
        return self._active_queue.loop_item

    def _activate_command(self, command: AvatarCommand) -> None:
        plan = self._planner.plan(command)
        self._active_queue = self._resolver.resolve(plan)
        self._cursor.reset(self._active_queue)
        self._last_command = command

    def _enqueue_pending_command(self, command: AvatarCommand) -> bool:
        if self._max_pending_commands == 0:
            return False
        if self._should_ignore_pending_command(command):
            return False

        if len(self._pending_commands) >= self._max_pending_commands:
            # Keep the newest user intent when the small transition queue fills up.
            self._pending_commands.pop(0)
        self._pending_commands.append(command)
        return True

    def _should_ignore_pending_command(self, command: AvatarCommand) -> bool:
        if not self._dedupe_pending_commands:
            return False
        if self._last_command is command:
            return True
        if self._pending_commands and self._pending_commands[-1] is command:
            return True
        return False

    def _resolve_initial_queue(self) -> ResolvedPlaybackQueue:
        initial_plan = PlaybackPlan(
            command=AvatarCommand.RECENTER,
            start_state=AvatarState.CENTER,
            play_once=[],
            loop_after="CENTER_IDLE",
            end_state=AvatarState.CENTER,
        )
        return self._resolver.resolve(initial_plan)

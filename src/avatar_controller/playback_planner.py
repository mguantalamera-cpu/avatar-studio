from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from avatar_controller.segments import SegmentMark, SegmentSet, load_segments
from avatar_controller.state_machine import (
    AvatarCommand,
    AvatarState,
    AvatarStateMachine,
    idle_segment_for_state,
    plan_transition,
)


class PlaybackPlannerError(ValueError):
    """Raised when playback cannot be planned from the available segments."""


@dataclass(frozen=True)
class PlaybackPlan:
    command: AvatarCommand
    start_state: AvatarState
    play_once: list[str]
    loop_after: str
    end_state: AvatarState


class PlaybackPlanner:
    def __init__(
        self,
        segment_set: SegmentSet,
        state_machine: AvatarStateMachine | None = None,
    ) -> None:
        validate_playback_segments(segment_set)
        self._segment_set = segment_set
        self._state_machine = state_machine or AvatarStateMachine()

    @classmethod
    def from_segments_file(
        cls,
        path: Path | str,
        state_machine: AvatarStateMachine | None = None,
    ) -> PlaybackPlanner:
        return cls(load_segments(path), state_machine=state_machine)

    @property
    def state(self) -> AvatarState:
        return self._state_machine.state

    @property
    def segment_set(self) -> SegmentSet:
        return self._segment_set

    def plan(self, command: AvatarCommand) -> PlaybackPlan:
        start_state = self._state_machine.state
        play_once, end_state = plan_transition(start_state, command)
        loop_after = idle_segment_for_state(end_state)
        validate_named_segments(self._segment_set, [*play_once, loop_after])
        self._state_machine.apply(command)
        return PlaybackPlan(
            command=command,
            start_state=start_state,
            play_once=play_once,
            loop_after=loop_after,
            end_state=end_state,
        )

    def plan_command(self, command: AvatarCommand) -> PlaybackPlan:
        return self.plan(command)

    def supports_command(self, _command: AvatarCommand) -> bool:
        return True


def validate_playback_segments(segment_set: SegmentSet) -> None:
    unknown_segments = sorted(set(segment_set.segments) - set(REQUIRED_PLAYBACK_SEGMENTS))
    if unknown_segments:
        raise PlaybackPlannerError(
            f"Unknown playback segment name(s): {', '.join(unknown_segments)}"
        )
    validate_named_segments(segment_set, REQUIRED_PLAYBACK_SEGMENTS)


def validate_named_segments(segment_set: SegmentSet, names: list[str] | tuple[str, ...]) -> None:
    for name in names:
        if name not in REQUIRED_PLAYBACK_SEGMENTS:
            raise PlaybackPlannerError(f"Unknown playback segment name: {name}")
        mark = segment_set.segments.get(name)
        if mark is None:
            raise PlaybackPlannerError(f"Missing playback segment: {name}")
        if mark.name != name:
            raise PlaybackPlannerError(
                f"Playback segment key '{name}' does not match mark name '{mark.name}'"
            )
        if not _is_complete(mark):
            raise PlaybackPlannerError(f"Incomplete playback segment: {name}")


def _is_complete(mark: SegmentMark) -> bool:
    return mark.start_frame is not None and mark.end_frame is not None


def _required_playback_segments() -> tuple[str, ...]:
    names: list[str] = []
    for state in AvatarState:
        _append_unique(names, idle_segment_for_state(state))
        for command in AvatarCommand:
            transition_segments, end_state = plan_transition(state, command)
            for segment in transition_segments:
                _append_unique(names, segment)
            _append_unique(names, idle_segment_for_state(end_state))
    return tuple(names)


def _append_unique(names: list[str], name: str) -> None:
    if name not in names:
        names.append(name)


REQUIRED_PLAYBACK_SEGMENTS: tuple[str, ...] = _required_playback_segments()
KNOWN_PLAYBACK_SEGMENTS: tuple[str, ...] = REQUIRED_PLAYBACK_SEGMENTS

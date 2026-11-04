from __future__ import annotations

from dataclasses import dataclass

from avatar_controller.segments import SegmentMark, SegmentSet
from avatar_controller.state_machine import AvatarState, idle_segment_for_state


IDLE_LOOP_MODES = ("auto", "full", "hold_last", "pingpong")


class IdleLoopError(ValueError):
    """Raised when idle loop profiles cannot be built."""


@dataclass(frozen=True)
class IdleLoopProfile:
    segment_name: str
    source_start_frame: int
    source_end_frame: int
    loop_start_frame: int
    loop_end_frame: int
    mode: str
    reason: str


class IdleLoopProfileBuilder:
    def __init__(self, segment_set: SegmentSet, mode: str = "auto") -> None:
        if mode not in IDLE_LOOP_MODES:
            valid = ", ".join(IDLE_LOOP_MODES)
            raise IdleLoopError(f"idle loop mode must be one of: {valid}")
        self._segment_set = segment_set
        self._mode = mode

    def build(self) -> dict[str, IdleLoopProfile]:
        return {
            idle_segment_for_state(state): self._build_profile(state)
            for state in AvatarState
        }

    def _build_profile(self, state: AvatarState) -> IdleLoopProfile:
        segment_name = idle_segment_for_state(state)
        mark = self._required_complete_mark(segment_name)
        source_start = mark.start_frame
        source_end = mark.end_frame
        assert source_start is not None
        assert source_end is not None
        length = source_end - source_start + 1

        if self._mode == "full":
            return IdleLoopProfile(
                segment_name=segment_name,
                source_start_frame=source_start,
                source_end_frame=source_end,
                loop_start_frame=source_start,
                loop_end_frame=source_end,
                mode="forward",
                reason="full segment requested",
            )

        if self._mode == "hold_last":
            return self._hold_last_profile(segment_name, source_start, source_end)

        if self._mode == "pingpong":
            return self._pingpong_profile(
                segment_name,
                source_start,
                source_end,
                prefer_center=state is AvatarState.CENTER,
                reason_prefix="pingpong mode requested",
            )

        if length < 10:
            return self._hold_last_profile(
                segment_name,
                source_start,
                source_end,
                reason="idle too short for stable subrange",
            )

        return self._pingpong_profile(
            segment_name,
            source_start,
            source_end,
            prefer_center=state is AvatarState.CENTER,
            reason_prefix="auto stable idle subrange",
        )

    def _pingpong_profile(
        self,
        segment_name: str,
        source_start: int,
        source_end: int,
        prefer_center: bool,
        reason_prefix: str,
    ) -> IdleLoopProfile:
        length = source_end - source_start + 1
        if length < 4:
            return self._hold_last_profile(
                segment_name,
                source_start,
                source_end,
                reason=f"{reason_prefix}; too short for pingpong",
            )

        if length > 20:
            window_length = max(6, length // 3)
        else:
            window_length = max(3, min(6, length // 2))
        window_length = min(window_length, length)

        if prefer_center and length > 20:
            loop_start = source_start + (length - window_length) // 2
            loop_end = loop_start + window_length - 1
            zone = "central"
        else:
            loop_end = source_end
            loop_start = source_end - window_length + 1
            zone = "final"

        return IdleLoopProfile(
            segment_name=segment_name,
            source_start_frame=source_start,
            source_end_frame=source_end,
            loop_start_frame=loop_start,
            loop_end_frame=loop_end,
            mode="pingpong",
            reason=f"{reason_prefix}; {zone} {window_length}-frame window",
        )

    def _hold_last_profile(
        self,
        segment_name: str,
        source_start: int,
        source_end: int,
        reason: str = "hold_last mode requested",
    ) -> IdleLoopProfile:
        return IdleLoopProfile(
            segment_name=segment_name,
            source_start_frame=source_start,
            source_end_frame=source_end,
            loop_start_frame=source_end,
            loop_end_frame=source_end,
            mode="hold_last",
            reason=reason,
        )

    def _required_complete_mark(self, segment_name: str) -> SegmentMark:
        mark = self._segment_set.segments.get(segment_name)
        if mark is None:
            raise IdleLoopError(f"Missing idle segment: {segment_name}")
        if mark.start_frame is None or mark.end_frame is None:
            raise IdleLoopError(f"Incomplete idle segment: {segment_name}")
        if mark.start_frame > mark.end_frame:
            raise IdleLoopError(f"Invalid idle segment range: {segment_name}")
        return mark

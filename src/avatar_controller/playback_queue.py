from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from avatar_controller.idle_loop import IdleLoopProfile
from avatar_controller.playback_planner import PlaybackPlan
from avatar_controller.segments import SegmentMark, SegmentSet


class PlaybackQueueError(ValueError):
    """Raised when a playback plan cannot be resolved to frame ranges."""


@dataclass(frozen=True)
class PlaybackItem:
    segment_name: str
    start_frame: int
    end_frame: int
    mode: str
    frame_count: int
    loop_mode: str = "forward"
    source_start_frame: int | None = None
    source_end_frame: int | None = None
    profile_reason: str = ""


@dataclass(frozen=True)
class ResolvedPlaybackQueue:
    items: list[PlaybackItem]
    loop_item: PlaybackItem | None


class PlaybackQueueResolver:
    def __init__(
        self,
        segment_set: SegmentSet,
        idle_loop_profiles: Mapping[str, IdleLoopProfile] | None = None,
    ) -> None:
        self._segment_set = segment_set
        self._idle_loop_profiles = idle_loop_profiles or {}

    def resolve(self, plan: PlaybackPlan) -> ResolvedPlaybackQueue:
        items = [
            self._resolve_item(segment_name, mode="once")
            for segment_name in plan.play_once
        ]
        loop_item = self._resolve_item(plan.loop_after, mode="loop")

        return ResolvedPlaybackQueue(items=items, loop_item=loop_item)

    def _resolve_item(self, segment_name: str, mode: str) -> PlaybackItem:
        mark = self._segment_set.segments.get(segment_name)
        if mark is None:
            raise PlaybackQueueError(f"Missing playback segment: {segment_name}")

        start_frame, end_frame = _validated_frame_range(mark)
        if mode == "loop" and segment_name in self._idle_loop_profiles:
            profile = self._idle_loop_profiles[segment_name]
            return PlaybackItem(
                segment_name=segment_name,
                start_frame=profile.loop_start_frame,
                end_frame=profile.loop_end_frame,
                mode=mode,
                frame_count=profile.loop_end_frame - profile.loop_start_frame + 1,
                loop_mode=profile.mode,
                source_start_frame=profile.source_start_frame,
                source_end_frame=profile.source_end_frame,
                profile_reason=profile.reason,
            )

        return PlaybackItem(
            segment_name=segment_name,
            start_frame=start_frame,
            end_frame=end_frame,
            mode=mode,
            frame_count=end_frame - start_frame + 1,
        )


def _validated_frame_range(mark: SegmentMark) -> tuple[int, int]:
    if mark.start_frame is None or mark.end_frame is None:
        raise PlaybackQueueError(f"Incomplete playback segment: {mark.name}")

    if not isinstance(mark.start_frame, int) or isinstance(mark.start_frame, bool):
        raise PlaybackQueueError(f"Invalid start_frame for playback segment: {mark.name}")
    if not isinstance(mark.end_frame, int) or isinstance(mark.end_frame, bool):
        raise PlaybackQueueError(f"Invalid end_frame for playback segment: {mark.name}")

    if mark.start_frame > mark.end_frame:
        raise PlaybackQueueError(
            f"Invalid playback segment range for {mark.name}: "
            "start_frame must be <= end_frame"
        )

    return mark.start_frame, mark.end_frame

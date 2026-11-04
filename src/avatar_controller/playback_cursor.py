from __future__ import annotations

from dataclasses import dataclass

from avatar_controller.playback_queue import PlaybackItem, ResolvedPlaybackQueue


class PlaybackCursorError(ValueError):
    """Raised when a resolved playback queue cannot be stepped."""


@dataclass(frozen=True)
class PlaybackFrame:
    segment_name: str
    frame_index: int
    mode: str
    item_index: int | None
    is_loop: bool


class PlaybackCursor:
    def __init__(self, queue: ResolvedPlaybackQueue) -> None:
        self.reset(queue)

    @property
    def current_segment_name(self) -> str:
        item, _item_index, _is_loop = self._current_item()
        return item.segment_name

    def peek(self) -> PlaybackFrame:
        item, item_index, is_loop = self._current_item()
        return PlaybackFrame(
            segment_name=item.segment_name,
            frame_index=self._next_frame_index,
            mode=item.mode,
            item_index=item_index,
            is_loop=is_loop,
        )

    def step(self) -> PlaybackFrame:
        frame = self.peek()
        item, _item_index, is_loop = self._current_item()
        self._advance(item, is_loop)
        return frame

    def reset(self, queue: ResolvedPlaybackQueue) -> None:
        if queue.loop_item is None:
            raise PlaybackCursorError("Resolved playback queue requires a loop_item")

        self._queue = queue
        self._item_index = 0
        self._loop_direction = 1
        self._next_frame_index = self._starting_frame_index()

    def _current_item(self) -> tuple[PlaybackItem, int | None, bool]:
        if self._item_index < len(self._queue.items):
            return self._queue.items[self._item_index], self._item_index, False
        return self._queue.loop_item, None, True

    def _advance(self, item: PlaybackItem, is_loop: bool) -> None:
        if is_loop:
            self._advance_loop(item)
            return

        if self._next_frame_index < item.end_frame:
            self._next_frame_index += 1
            return

        self._item_index += 1
        self._loop_direction = 1
        self._next_frame_index = self._starting_frame_index()

    def _advance_loop(self, item: PlaybackItem) -> None:
        if item.loop_mode == "hold_last" or item.start_frame == item.end_frame:
            self._next_frame_index = item.end_frame
            return

        if item.loop_mode == "pingpong":
            if self._loop_direction > 0:
                if self._next_frame_index < item.end_frame:
                    self._next_frame_index += 1
                    return
                self._loop_direction = -1
                self._next_frame_index -= 1
                return

            if self._next_frame_index > item.start_frame:
                self._next_frame_index -= 1
                return
            self._loop_direction = 1
            self._next_frame_index += 1
            return

        if self._next_frame_index < item.end_frame:
            self._next_frame_index += 1
            return
        self._next_frame_index = item.start_frame

    def _starting_frame_index(self) -> int:
        if self._item_index < len(self._queue.items):
            return self._queue.items[self._item_index].start_frame
        return self._queue.loop_item.start_frame

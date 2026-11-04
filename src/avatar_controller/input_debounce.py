from __future__ import annotations

import time
from typing import Callable

from avatar_controller.state_machine import AvatarCommand


class InputDebouncer:
    def __init__(
        self,
        release_required_ticks: int = 15,
        debounce_ms: int = 700,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if release_required_ticks < 1:
            raise ValueError("release_required_ticks must be >= 1")
        if debounce_ms < 0:
            raise ValueError("debounce_ms must be >= 0")

        self._release_required_ticks = release_required_ticks
        self._debounce_ms = debounce_ms
        self._clock = clock or time.monotonic
        self._locked_command: AvatarCommand | None = None
        self._ticks_without_command = release_required_ticks
        self._last_accepted_at_ms: float | None = None

    def accept_command(self, command: AvatarCommand) -> AvatarCommand | None:
        self._ticks_without_command = 0

        if self._locked_command is not None:
            return None

        now_ms = self._now_ms()
        if self._last_accepted_at_ms is not None:
            elapsed_ms = now_ms - self._last_accepted_at_ms
            if elapsed_ms < self._debounce_ms:
                self._locked_command = command
                return None

        self._locked_command = command
        self._last_accepted_at_ms = now_ms
        return command

    def observe_no_command(self) -> None:
        self._ticks_without_command += 1
        if self._ticks_without_command >= self._release_required_ticks:
            self._locked_command = None

    def reset(self) -> None:
        self._locked_command = None
        self._ticks_without_command = self._release_required_ticks
        self._last_accepted_at_ms = None

    @property
    def locked_command(self) -> AvatarCommand | None:
        return self._locked_command

    @property
    def ticks_without_command(self) -> int:
        return self._ticks_without_command

    def _now_ms(self) -> float:
        return self._clock() * 1000.0

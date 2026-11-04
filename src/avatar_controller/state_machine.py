from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AvatarState(StrEnum):
    CENTER = "CENTER"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    UP = "UP"
    DOWN = "DOWN"


class AvatarCommand(StrEnum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    UP = "UP"
    DOWN = "DOWN"
    RECENTER = "RECENTER"


@dataclass(frozen=True)
class TransitionPlan:
    start_state: AvatarState
    command: AvatarCommand
    segments: list[str]
    end_state: AvatarState


IDLE_SEGMENTS: dict[AvatarState, str] = {
    AvatarState.CENTER: "CENTER_IDLE",
    AvatarState.LEFT: "LEFT_IDLE",
    AvatarState.RIGHT: "RIGHT_IDLE",
    AvatarState.UP: "UP_IDLE",
    AvatarState.DOWN: "DOWN_IDLE",
}

COMMAND_TARGETS: dict[AvatarCommand, AvatarState] = {
    AvatarCommand.LEFT: AvatarState.LEFT,
    AvatarCommand.RIGHT: AvatarState.RIGHT,
    AvatarCommand.UP: AvatarState.UP,
    AvatarCommand.DOWN: AvatarState.DOWN,
}


class AvatarStateMachine:
    def __init__(self, initial_state: AvatarState = AvatarState.CENTER) -> None:
        self._state = initial_state

    @property
    def state(self) -> AvatarState:
        return self._state

    def current_idle_segment(self) -> str:
        return idle_segment_for_state(self._state)

    def apply(self, command: AvatarCommand) -> TransitionPlan:
        start_state = self._state
        segments, end_state = plan_transition(start_state, command)
        self._state = end_state
        return TransitionPlan(
            start_state=start_state,
            command=command,
            segments=segments,
            end_state=end_state,
        )


def idle_segment_for_state(state: AvatarState) -> str:
    return IDLE_SEGMENTS[state]


def plan_transition(
    start_state: AvatarState,
    command: AvatarCommand,
) -> tuple[list[str], AvatarState]:
    if command is AvatarCommand.RECENTER:
        if start_state is AvatarState.CENTER:
            return [], AvatarState.CENTER
        return [to_center_segment(start_state)], AvatarState.CENTER

    target_state = COMMAND_TARGETS[command]
    if start_state is AvatarState.CENTER:
        return [from_center_segment(target_state)], target_state
    if start_state is target_state:
        return [to_center_segment(start_state)], AvatarState.CENTER
    return [to_center_segment(start_state), from_center_segment(target_state)], target_state


def from_center_segment(target_state: AvatarState) -> str:
    if target_state is AvatarState.CENTER:
        raise ValueError("CENTER is not a valid directional target")
    return f"CENTER_TO_{target_state.value}"


def to_center_segment(start_state: AvatarState) -> str:
    if start_state is AvatarState.CENTER:
        raise ValueError("CENTER is already centered")
    return f"{start_state.value}_TO_CENTER"

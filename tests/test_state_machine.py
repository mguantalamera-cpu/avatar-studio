from __future__ import annotations

from avatar_controller.state_machine import AvatarCommand, AvatarState, AvatarStateMachine


def test_directional_transition_and_recenter() -> None:
    machine = AvatarStateMachine()
    left = machine.apply(AvatarCommand.LEFT)
    assert left.segments == ["CENTER_TO_LEFT"]
    assert machine.state is AvatarState.LEFT
    centered = machine.apply(AvatarCommand.RECENTER)
    assert centered.segments == ["LEFT_TO_CENTER"]
    assert machine.state is AvatarState.CENTER


def test_public_commands_cover_only_directional_motion_and_recenter() -> None:
    assert len(AvatarCommand) == 5

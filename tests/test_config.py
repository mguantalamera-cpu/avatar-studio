from __future__ import annotations

import pytest

from avatar_controller.config import ConfigError, parse_config


def test_video_path_is_required() -> None:
    with pytest.raises(ConfigError, match="video.path"):
        parse_config({})


def test_config_uses_the_path_supplied_by_the_user() -> None:
    config = parse_config({"video": {"path": "assets/my-avatar.mp4"}})
    assert config.video.path.as_posix() == "assets/my-avatar.mp4"

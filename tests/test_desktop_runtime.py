from __future__ import annotations

from pathlib import Path

from avatar_controller.studio.desktop_runtime import resolve_project_root


def test_frozen_runtime_uses_user_workspace_without_a_source_marker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "private-workspace"
    monkeypatch.setenv("AVATAR_STUDIO_DATA_DIR", str(workspace))
    root = resolve_project_root(tmp_path / "source", frozen=True)
    assert root == workspace.resolve()
    assert (root / "data" / "studio").is_dir()
    assert not (root / "avatar_studio_project.json").exists()

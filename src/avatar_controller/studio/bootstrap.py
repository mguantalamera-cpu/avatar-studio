from __future__ import annotations

from pathlib import Path

from avatar_controller.studio.profiles import AvatarProfileStore


def initialize_studio(project_root: Path | str) -> AvatarProfileStore:
    """Create or open the local-only profile catalog for this installation."""

    root = Path(project_root).resolve()
    return AvatarProfileStore(root / "data" / "studio")

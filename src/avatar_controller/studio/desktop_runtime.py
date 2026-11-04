from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT_ENV = "AVATAR_STUDIO_PROJECT_ROOT"
USER_DATA_ENV = "AVATAR_STUDIO_DATA_DIR"
INTERNAL_TOOL_NAMES = frozenset(
    {
        "analyze_studio_profile.py",
        "inspect_video_timing.py",
        "mark_segments.py",
        "preview_segments.py",
        "run_avatar_profile.py",
    }
)


class DesktopRuntimeError(RuntimeError):
    """Raised when the desktop runtime cannot resolve its local workspace."""


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _default_user_workspace() -> Path:
    configured = os.environ.get(USER_DATA_ENV)
    if configured and configured.strip():
        return Path(configured).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if local_app_data and local_app_data.strip():
        return (Path(local_app_data) / "AvatarStudio").resolve()
    return (Path.cwd() / "AvatarStudioData").resolve()


def resolve_project_root(
    source_project_root: Path | str,
    *,
    frozen: bool | None = None,
    executable: Path | str | None = None,
) -> Path:
    """Resolve source files in development and a private data folder in an EXE."""

    del executable
    source_root = Path(source_project_root).resolve()
    running_frozen = is_frozen() if frozen is None else frozen
    if not running_frozen:
        return source_root
    workspace = _default_user_workspace()
    try:
        (workspace / "data" / "studio").mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DesktopRuntimeError(
            f"Avatar Studio could not create its local data folder: {workspace}"
        ) from exc
    return workspace


def run_internal_tool(
    tool_name: str,
    arguments: Sequence[str],
    *,
    project_root: Path | str,
    resource_root: Path | str | None = None,
) -> int:
    if tool_name not in INTERNAL_TOOL_NAMES:
        raise DesktopRuntimeError(f"Unsupported Avatar Studio tool: {tool_name}")
    resources = Path(
        resource_root or getattr(sys, "_MEIPASS", Path(project_root).resolve())
    ).resolve()
    tools_root = resources / "tools"
    script_path = tools_root / tool_name
    if not script_path.is_file():
        raise DesktopRuntimeError(f"Bundled Avatar Studio tool is missing: {script_path}")

    previous_argv = sys.argv
    previous_project_root = os.environ.get(PROJECT_ROOT_ENV)
    inserted_tools_path = False
    if str(tools_root) not in sys.path:
        sys.path.insert(0, str(tools_root))
        inserted_tools_path = True
    os.environ[PROJECT_ROOT_ENV] = str(Path(project_root).resolve())
    sys.argv = [str(script_path), *arguments]
    try:
        runpy.run_path(str(script_path), run_name="__main__")
    except SystemExit as exc:
        if exc.code is None:
            return 0
        return exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = previous_argv
        if previous_project_root is None:
            os.environ.pop(PROJECT_ROOT_ENV, None)
        else:
            os.environ[PROJECT_ROOT_ENV] = previous_project_root
        if inserted_tools_path:
            sys.path.remove(str(tools_root))
    return 0

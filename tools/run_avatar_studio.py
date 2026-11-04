from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


SOURCE_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if not getattr(sys, "frozen", False):
    SRC_ROOT = SOURCE_PROJECT_ROOT / "src"
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))

from avatar_controller.studio.desktop_runtime import (  # noqa: E402
    DesktopRuntimeError,
    INTERNAL_TOOL_NAMES,
    resolve_project_root,
    run_internal_tool,
)


def _project_root() -> Path:
    return resolve_project_root(SOURCE_PROJECT_ROOT)


def validate_runtime_assets(cv2_module: object | None = None) -> None:
    """Fail the packaged smoke test when the OpenCV face detector is unusable."""

    if cv2_module is None:
        import cv2 as cv2_module

    data = getattr(cv2_module, "data", None)
    cascade_root = getattr(data, "haarcascades", "")
    cascade_path = Path(cascade_root) / "haarcascade_frontalface_default.xml"
    if not cascade_path.is_file():
        raise DesktopRuntimeError(
            f"OpenCV face detector asset is missing: {cascade_path}"
        )
    classifier = getattr(cv2_module, "CascadeClassifier")(str(cascade_path))
    if classifier.empty():
        raise DesktopRuntimeError(
            f"OpenCV face detector asset could not be loaded: {cascade_path}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open the Avatar Studio desktop application.")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Initialize the interface offscreen and exit automatically.",
    )
    parser.add_argument(
        "--internal-tool",
        choices=sorted(INTERNAL_TOOL_NAMES),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--workspace", type=Path, help="Absolute private profile workspace")
    parser.add_argument("--list-profiles", action="store_true", help="List local profile IDs")
    parser.add_argument("--play-profile", help="Play an explicitly selected reviewed profile")
    parser.add_argument("--virtual-camera", action="store_true")
    parser.add_argument("--check-profile", action="store_true", help="Validate without playback")
    args, remaining = parser.parse_known_args(argv)
    if args.check_profile and not args.play_profile:
        parser.error("--check-profile requires --play-profile")
    if args.virtual_camera and not args.play_profile:
        parser.error("--virtual-camera requires --play-profile")
    if args.internal_tool and (args.play_profile or args.list_profiles):
        parser.error("profile commands cannot be combined with --internal-tool")
    try:
        if args.workspace is not None:
            if not args.workspace.is_absolute() or str(args.workspace).startswith(("\\\\", "//")):
                raise DesktopRuntimeError("--workspace must be an absolute local directory")
            project_root = args.workspace.resolve()
        else:
            project_root = _project_root()
    except DesktopRuntimeError as exc:
        print(f"Avatar Studio installation error: {exc}", file=sys.stderr)
        return 2
    if args.list_profiles or args.play_profile:
        if remaining:
            parser.error(f"unrecognized arguments: {' '.join(remaining)}")
        from avatar_controller.studio.companion import reviewed_profile_arguments
        from avatar_controller.studio.profiles import AvatarProfileStore, StudioProfileError
        from avatar_controller.config import ConfigError
        from avatar_controller.segments import SegmentError

        try:
            if args.list_profiles:
                if args.play_profile:
                    parser.error("choose either --list-profiles or --play-profile")
                profiles = AvatarProfileStore(project_root / "data" / "studio").list_profiles()
                print(json.dumps([
                    {"id": p.profile_id, "name": p.name, "status": p.status.value}
                    for p in profiles
                ], ensure_ascii=False), flush=True)
                return 0
            command = reviewed_profile_arguments(
                project_root, args.play_profile, virtual_camera=args.virtual_camera
            )
            if args.check_profile:
                print("Reviewed profile is valid; no camera or playback started.", flush=True)
                return 0
            return run_internal_tool(command[1], command[2:], project_root=project_root)
        except (OSError, ValueError, ConfigError, SegmentError, StudioProfileError,
                DesktopRuntimeError) as exc:
            print(f"Avatar Studio profile error: {exc}", file=sys.stderr)
            return 2
    if args.internal_tool:
        try:
            return run_internal_tool(
                args.internal_tool,
                remaining,
                project_root=project_root,
            )
        except DesktopRuntimeError as exc:
            print(f"Avatar Studio tool error: {exc}", file=sys.stderr)
            return 2
    if remaining:
        parser.error(f"unrecognized arguments: {' '.join(remaining)}")
    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            validate_runtime_assets()
        except (ImportError, OSError, DesktopRuntimeError) as exc:
            print(f"Avatar Studio runtime check failed: {exc}", file=sys.stderr)
            return 2
    try:
        from avatar_controller.studio.application import run_studio
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            print(
                "Avatar Studio requires PySide6. Run: python -m pip install -r requirements.txt",
                file=sys.stderr,
            )
            return 2
        raise
    return run_studio(project_root, smoke_test=args.smoke_test)


if __name__ == "__main__":
    raise SystemExit(main())

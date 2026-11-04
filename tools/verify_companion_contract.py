"""Exercise both public contracts with synthetic video, without opening any camera."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companion-source", required=True, type=Path)
    parser.add_argument("--studio-release", required=True, type=Path)
    parser.add_argument("--companion-cli", type=Path, help="Optional packaged companion CLI")
    args = parser.parse_args()
    source = args.companion_source.resolve() / "src"
    if not (source / "avatar_studio_webcam_pc" / "__init__.py").is_file():
        parser.error("--companion-source must name the public companion source checkout")
    sys.path.insert(0, str(source))
    import cv2
    import numpy as np
    import yaml
    from avatar_controller.segments import SegmentMark, SegmentSet, TEMPORAL_SEGMENT_ORDER
    from avatar_controller.studio.companion import PUBLIC_RUNTIME_MARKER
    from avatar_controller.studio.profiles import AvatarProfileStore, ProfileStatus
    from avatar_controller.video_io import read_video_metadata
    from avatar_studio_webcam_pc.bootstrap import create_local_configuration
    from avatar_studio_webcam_pc.config import load_config
    from avatar_studio_webcam_pc.runner import ExecutableVerificationError, WindowsProcessRunner

    release = args.studio_release.resolve()
    cli = release / "AvatarStudio-CLI.exe"
    executable = release / "AvatarStudio.exe"
    marker = json.loads((release / "avatar_studio_project.json").read_text(encoding="utf-8"))
    if marker != PUBLIC_RUNTIME_MARKER:
        raise RuntimeError("The built release has a different public contract")
    with tempfile.TemporaryDirectory(prefix="avatar-public-contract-") as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        video = root / "synthetic.avi"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 30, (64, 64))
        if not writer.isOpened():
            raise RuntimeError("Cannot generate the synthetic test video")
        try:
            for index in range(500):
                frame = np.zeros((64, 64, 3), dtype=np.uint8)
                frame[:, :, index % 3] = index % 255
                writer.write(frame)
        finally:
            writer.release()
        store = AvatarProfileStore(workspace / "data" / "studio")
        profile = store.create_imported_profile(video, read_video_metadata(video), name="Synthetic")
        marks = {
            name: SegmentMark(name, i * 30, i * 30 + (19 if name.endswith("_IDLE") else 4))
            for i, name in enumerate(TEMPORAL_SEGMENT_ORDER)
        }
        segments = SegmentSet(1, video, 64, 64, 30, 500, marks)
        profile.segments_path.write_text(yaml.safe_dump(segments.to_yaml_data()), encoding="utf-8")
        profile = store.update_status(profile.profile_id, ProfileStatus.READY)
        local_config = root / "local" / "avatar-studio-webcam-pc.local.json"
        if args.companion_cli is None:
            create_local_configuration(
                config_path=local_config, executable_path=executable,
                project_root=workspace, profile_id=profile.profile_id,
            )
        else:
            completed = subprocess.run([
                str(args.companion_cli.resolve()), "--config", str(local_config), "--setup",
                "--runtime-executable", str(executable), "--project-root", str(workspace),
                "--profile-id", profile.profile_id,
            ], capture_output=True, text=True, timeout=90)
            if completed.returncode:
                raise RuntimeError(f"Packaged companion setup failed: {completed.stderr}")
        config = load_config(local_config, environ={"LOCALAPPDATA": str(root / "Local")})
        WindowsProcessRunner._verify(config.executable)
        commands = [
            [str(cli), "--workspace", str(workspace), "--list-profiles"],
            [str(cli), *config.output.arguments, "--check-profile"],
            [str(cli), "--workspace", str(workspace), "--smoke-test"],
        ]
        for command in commands:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=40)
            if completed.returncode:
                raise RuntimeError(f"Packaged contract check failed: {completed.stderr}")
        store.update_status(profile.profile_id, ProfileStatus.REVIEW_REQUIRED)
        rejected = subprocess.run(
            [str(cli), *config.output.arguments, "--check-profile"],
            capture_output=True, text=True, timeout=40,
        )
        if rejected.returncode != 2:
            raise RuntimeError("The packaged Studio must reject an unreviewed profile")
        try:
            WindowsProcessRunner._verify(config.executable)
        except ExecutableVerificationError:
            pass
        else:
            raise RuntimeError("The companion must reject a changed catalog")
    print("Public integration verified: packaged CLI, profile selection, integrity and smoke test.")
    print("Synthetic video only; no webcam, virtual camera, streaming or personal files accessed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

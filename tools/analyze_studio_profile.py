from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any


SOURCE_PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(
    os.environ.get("AVATAR_STUDIO_PROJECT_ROOT", str(SOURCE_PROJECT_ROOT))
).resolve()
if not getattr(sys, "frozen", False):
    src_root = SOURCE_PROJECT_ROOT / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

from avatar_controller.auto_segments import generate_auto_segments, save_auto_report  # noqa: E402
from avatar_controller.segments import save_segments  # noqa: E402
from avatar_controller.studio.bootstrap import initialize_studio  # noqa: E402
from avatar_controller.studio.profiles import ProfileStatus  # noqa: E402
from avatar_controller.video_io import VideoMetadata  # noqa: E402


def analyze_profile(project_root: Path, profile_id: str) -> dict[str, Any]:
    store = initialize_studio(project_root)
    profile = store.get_profile(profile_id)
    metadata = VideoMetadata(
        path=profile.video_path,
        width=profile.width,
        height=profile.height,
        fps=profile.fps,
        frame_count=profile.frame_count,
        duration_seconds=profile.duration_seconds,
        codec=profile.codec,
    )
    print("Detectando movimientos y poses…", flush=True)
    result = generate_auto_segments(profile.video_path, metadata)
    save_segments(profile.segments_path, result.segment_set)
    save_auto_report(profile.report_path, result.report)
    updated = store.update_status(profile.profile_id, ProfileStatus.REVIEW_REQUIRED)
    detected_count = len(result.report["segments"]) - len(result.report["undetected_segments"])
    summary = {
        "profile_id": updated.profile_id,
        "segments_path": str(updated.segments_path),
        "analysis_report_path": str(updated.report_path),
        "detected_segments": detected_count,
        "required_segments": len(result.report["segments"]),
        "status": updated.status.value,
        "source_video_modified": False,
    }
    print(
        f"Segmentos detectados: {detected_count}/{summary['required_segments']}. "
        "Revisa el resultado antes de activar la cámara virtual.",
        flush=True,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze a local Avatar Studio profile without changing the source video."
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--profile-id", required=True)
    args = parser.parse_args(argv)
    try:
        analyze_profile(args.project_root.resolve(), args.profile_id)
    except Exception as exc:
        print(f"Avatar Studio analysis error: {exc}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from avatar_controller.studio.video_preflight import (  # noqa: E402
    VideoTimingReport,
    inspect_video_timing,
    save_video_timing_report,
)


def inspect_and_save(video_path: Path, output_path: Path) -> int:
    video = video_path.resolve()
    output = output_path.resolve()
    if video == output:
        print(
            "Error de argumentos: el informe no puede sobrescribir el vídeo original.",
            file=sys.stderr,
            flush=True,
        )
        return 2

    report = inspect_video_timing(video)
    try:
        saved_path = save_video_timing_report(report, output)
    except OSError as exc:
        print(
            f"No se pudo guardar el diagnóstico de cadencia: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return 2

    print(_report_message(report), flush=True)
    print(f"Informe de cadencia guardado: {saved_path}", flush=True)
    return 0


def _report_message(report: VideoTimingReport) -> str:
    fps = (
        f", mediana {report.median_fps:.2f} FPS"
        if report.median_fps is not None
        else ""
    )
    message = (
        f"Cadencia {report.classification.value}: "
        f"{report.frames_observed} fotogramas observados{fps}."
    )
    if report.warning:
        message += f" Aviso: {report.warning}"
    return message


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect video timing without modifying the source video."
    )
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    return inspect_and_save(args.video, args.output)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import os
import sys
import time
from contextlib import ExitStack
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

from avatar_controller.config import ConfigError, load_config, validate_video_path  # noqa: E402
from avatar_controller.idle_loop import IDLE_LOOP_MODES  # noqa: E402
from avatar_controller.runtime_controller import AvatarRuntimeController  # noqa: E402
from avatar_controller.segments import SegmentError, load_segments, validate_segments  # noqa: E402
from avatar_controller.state_machine import AvatarCommand  # noqa: E402
from avatar_controller.video_frame_source import VideoFrameSource, VideoFrameSourceError  # noqa: E402
from avatar_controller.video_io import VideoIOError, read_video_metadata  # noqa: E402
from avatar_controller.virtual_camera_sink import (  # noqa: E402
    VirtualCameraSink,
    VirtualCameraSinkError,
)


WINDOW_NAME = "Avatar Studio — Controlador"
KEY_ESC = 27
KEY_SPACE = 32
KEY_LEFT = 2424832
KEY_UP = 2490368
KEY_RIGHT = 2555904
KEY_DOWN = 2621440


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Play a reviewed local avatar profile with optional virtual-camera output."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument("--virtual-camera", action="store_true")
    parser.add_argument("--virtual-camera-backend", default="obs")
    parser.add_argument("--virtual-camera-device", default=None)
    parser.add_argument("--no-overlay", action="store_true")
    parser.add_argument(
        "--idle-loop-mode",
        default="auto",
        choices=IDLE_LOOP_MODES,
        help="Strategy used to loop the reviewed idle portions.",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Optional diagnostic frame limit; omit during normal use.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.max_ticks is not None and args.max_ticks < 1:
            raise ValueError("--max-ticks must be at least 1")
        config = load_config(args.config)
        video_path = validate_video_path(config.video.path)
        metadata = read_video_metadata(video_path)
        segment_set = load_segments(args.segments)
        validation = validate_segments(segment_set, metadata.frame_count)
        if validation.errors:
            detail = "; ".join(issue.format() for issue in validation.errors[:5])
            raise SegmentError(f"Segments must be reviewed before playback: {detail}")
        if segment_set.video_path.resolve() != video_path.resolve():
            raise SegmentError("The selected segments belong to a different video file")
        cv2 = _load_cv2()
        controller = AvatarRuntimeController(
            segment_set,
            max_pending_commands=config.playback.max_queue_size,
            idle_loop_mode=args.idle_loop_mode,
        )
        with ExitStack() as stack:
            source = stack.enter_context(VideoFrameSource(video_path, cv2_module=cv2))
            frame_sink = None
            if args.virtual_camera:
                frame_sink = stack.enter_context(
                    VirtualCameraSink(
                        source.width,
                        source.height,
                        source.fps if source.fps > 0 else metadata.fps,
                        backend=args.virtual_camera_backend,
                        device=args.virtual_camera_device,
                    )
                )
                print(
                    f"Virtual camera ready: {frame_sink.device} ({frame_sink.backend})",
                    flush=True,
                )
            return run_preview_loop(
                controller,
                source,
                cv2,
                target_fps=source.fps if source.fps > 0 else metadata.fps,
                overlay_enabled=not args.no_overlay,
                max_ticks=args.max_ticks,
                frame_sink=frame_sink,
            )
    except (
        ConfigError,
        SegmentError,
        VideoIOError,
        VideoFrameSourceError,
        VirtualCameraSinkError,
        ValueError,
    ) as exc:
        print(f"Avatar Studio playback error: {exc}", file=sys.stderr)
        return 2


def run_preview_loop(
    controller: AvatarRuntimeController,
    frame_source: VideoFrameSource,
    cv2: Any,
    *,
    target_fps: float,
    overlay_enabled: bool,
    max_ticks: int | None,
    frame_sink: VirtualCameraSink | None,
) -> int:
    fps = target_fps if target_fps > 0 else 30.0
    delay_ms = max(1, int(round(1000.0 / fps)))
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    paused = False
    ticks = 0
    next_frame_time = time.perf_counter()
    try:
        while True:
            if paused:
                key = cv2.waitKeyEx(30)
                if key_requests_quit(key):
                    return 0
                if key == KEY_SPACE:
                    paused = False
                    next_frame_time = time.perf_counter()
                continue

            playback_frame = controller.step()
            frame = frame_source.get_frame(playback_frame.frame_index)
            if frame_sink is not None:
                frame_sink.send(frame)
            display = (
                draw_overlay(cv2, frame, controller, playback_frame.segment_name)
                if overlay_enabled
                else frame
            )
            cv2.imshow(WINDOW_NAME, display)
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                return 0

            next_frame_time += 1.0 / fps
            wait_ms = max(1, min(delay_ms, int(round((next_frame_time - time.perf_counter()) * 1000.0))))
            key = cv2.waitKeyEx(wait_ms)
            if key_requests_quit(key):
                return 0
            if key == KEY_SPACE:
                paused = True
                continue
            command = key_to_command(key)
            if command is not None:
                controller.submit_command(command)
            if next_frame_time < time.perf_counter() - (1.0 / fps):
                next_frame_time = time.perf_counter()
    finally:
        cv2.destroyAllWindows()


def key_to_command(key: int) -> AvatarCommand | None:
    if key in {KEY_LEFT, ord("a"), ord("A")}:
        return AvatarCommand.LEFT
    if key in {KEY_UP, ord("w"), ord("W")}:
        return AvatarCommand.UP
    if key in {KEY_RIGHT, ord("d"), ord("D")}:
        return AvatarCommand.RIGHT
    if key in {KEY_DOWN, ord("s"), ord("S")}:
        return AvatarCommand.DOWN
    if key in {ord("r"), ord("R")}:
        return AvatarCommand.RECENTER
    return None


def key_requests_quit(key: int) -> bool:
    return key in {KEY_ESC, ord("q"), ord("Q")}


def draw_overlay(
    cv2: Any,
    frame: Any,
    controller: AvatarRuntimeController,
    segment_name: str,
) -> Any:
    display = frame.copy()
    panel = display.copy()
    height, width = display.shape[:2]
    cv2.rectangle(panel, (0, 0), (min(width, 720), min(height, 112)), (0, 0, 0), -1)
    display = cv2.addWeighted(panel, 0.55, display, 0.45, 0)
    state = controller.status()
    lines = [
        f"State: {state.current_state.value}   Segment: {segment_name}",
        "Arrows/WASD move · R center · Space pause · Q/Esc exit",
    ]
    y = 34
    for line in lines:
        cv2.putText(
            display,
            line,
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.64,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        y += 38
    return display


def _load_cv2() -> Any:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise VideoIOError("OpenCV is not installed. Install requirements.txt first.") from exc
    return cv2


if __name__ == "__main__":
    raise SystemExit(main())

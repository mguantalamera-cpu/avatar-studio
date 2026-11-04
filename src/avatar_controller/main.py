from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from avatar_controller.config import ConfigError, load_config, validate_video_path
from avatar_controller.video_io import VideoIOError, read_video_metadata


WINDOW_NAME = "Avatar Video Controller"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play a local avatar source video.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--clean-output", action="store_true", help="Reserve clean output mode.")
    parser.add_argument(
        "--virtual-camera",
        action="store_true",
        help="Reserved for a later pyvirtualcam phase.",
    )
    args = parser.parse_args(argv)

    try:
        app_config = load_config(args.config)
        video_path = validate_video_path(app_config.video.path)
        metadata = read_video_metadata(video_path)
        print(
            "Loaded video: "
            f"{metadata.width}x{metadata.height}, "
            f"{metadata.fps:.3f} FPS, "
            f"{metadata.frame_count} frames, "
            f"{metadata.duration_seconds:.2f}s"
        )

        if args.virtual_camera or app_config.output.virtual_camera_enabled:
            print("Virtual camera output is reserved for a later phase; using window output.")

        return play_video(video_path, app_config.output.fullscreen or args.clean_output)
    except (ConfigError, VideoIOError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def play_video(video_path: Path, fullscreen: bool = False) -> int:
    cv2 = _load_cv2_for_player()
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise VideoIOError(f"OpenCV could not open video: {video_path}")

        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_delay = 1.0 / fps if fps > 0 else 1.0 / 30.0
        paused = False

        window_flag = cv2.WINDOW_NORMAL if fullscreen else cv2.WINDOW_AUTOSIZE
        cv2.namedWindow(WINDOW_NAME, window_flag)
        if fullscreen:
            cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        next_frame_time = time.perf_counter()
        while True:
            if paused:
                key = cv2.waitKey(30) & 0xFF
                if _should_quit(key):
                    break
                if key == ord(" "):
                    paused = False
                    next_frame_time = time.perf_counter()
                continue

            ok, frame = capture.read()
            if not ok or frame is None:
                capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                next_frame_time = time.perf_counter()
                continue

            cv2.imshow(WINDOW_NAME, frame)

            now = time.perf_counter()
            sleep_for = max(0.001, next_frame_time - now)
            key = cv2.waitKey(max(1, int(sleep_for * 1000))) & 0xFF
            if _should_quit(key):
                break
            if key == ord(" "):
                paused = True

            next_frame_time += frame_delay
            if next_frame_time < time.perf_counter() - frame_delay:
                next_frame_time = time.perf_counter()

        return 0
    finally:
        capture.release()
        cv2.destroyAllWindows()


def _should_quit(key: int) -> bool:
    return key in {27, ord("q"), ord("Q")}


def _load_cv2_for_player() -> Any:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise VideoIOError(
            "OpenCV is not installed. Run: python -m pip install opencv-python"
        ) from exc
    return cv2


if __name__ == "__main__":
    raise SystemExit(main())

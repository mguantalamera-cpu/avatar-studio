from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class VideoIOError(RuntimeError):
    """Raised when video metadata or frames cannot be read."""


@dataclass(frozen=True)
class VideoMetadata:
    path: Path
    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float
    codec: str | None = None
    orientation_degrees: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        return data


def read_video_metadata(video_path: Path | str) -> VideoMetadata:
    cv2 = _load_cv2()
    path = Path(video_path)
    if not path.exists():
        raise VideoIOError(f"Video file does not exist: {path}")
    if not path.is_file():
        raise VideoIOError(f"Video path is not a file: {path}")

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoIOError(f"OpenCV could not open video: {path}")

        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_seconds = frame_count / fps if fps > 0 else 0.0
        codec = _decode_fourcc(capture.get(cv2.CAP_PROP_FOURCC))
        orientation = _read_orientation(cv2, capture)

        if width <= 0 or height <= 0:
            raise VideoIOError(f"Video reports invalid resolution: {width}x{height}")
        if frame_count <= 0:
            raise VideoIOError(f"Video reports invalid frame count: {frame_count}")

        return VideoMetadata(
            path=path,
            width=width,
            height=height,
            fps=fps,
            frame_count=frame_count,
            duration_seconds=duration_seconds,
            codec=codec,
            orientation_degrees=orientation,
        )
    finally:
        capture.release()


def save_metadata_json(metadata: VideoMetadata, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(metadata.to_dict(), handle, indent=2)
        handle.write("\n")
    return path


def extract_sample_frames(
    video_path: Path | str,
    output_dir: Path | str,
    sample_count: int = 5,
    prefix: str = "sample",
) -> list[Path]:
    cv2 = _load_cv2()
    path = Path(video_path)
    if sample_count <= 0:
        return []

    metadata = read_video_metadata(path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    frame_indices = _sample_indices(metadata.frame_count, sample_count)

    capture = cv2.VideoCapture(str(path))
    written: list[Path] = []
    try:
        if not capture.isOpened():
            raise VideoIOError(f"OpenCV could not open video: {path}")

        for index in frame_indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok or frame is None:
                raise VideoIOError(f"Could not read sample frame {index} from {path}")

            frame_path = output_path / f"{prefix}_{index:06d}.png"
            if not cv2.imwrite(str(frame_path), frame):
                raise VideoIOError(f"Could not write sample frame: {frame_path}")
            written.append(frame_path)
    finally:
        capture.release()

    return written


def _sample_indices(frame_count: int, sample_count: int) -> list[int]:
    if frame_count <= 0:
        return []
    if sample_count == 1:
        return [0]

    last_index = frame_count - 1
    values = {
        min(last_index, max(0, int(round(position * last_index / (sample_count - 1)))))
        for position in range(sample_count)
    }
    return sorted(values)


def _decode_fourcc(value: float) -> str | None:
    if value is None or math.isnan(float(value)):
        return None
    code = int(value)
    chars = "".join(chr((code >> (8 * index)) & 0xFF) for index in range(4))
    codec = chars.strip("\x00").strip()
    return codec or None


def _read_orientation(cv2: Any, capture: Any) -> int | None:
    orientation_property = getattr(cv2, "CAP_PROP_ORIENTATION_META", None)
    if orientation_property is None:
        return None
    value = capture.get(orientation_property)
    if value is None or math.isnan(float(value)):
        return None
    return int(value)


def _load_cv2() -> Any:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise VideoIOError(
            "OpenCV is not installed. Run: python -m pip install opencv-python"
        ) from exc
    return cv2

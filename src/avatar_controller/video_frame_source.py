from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class VideoFrameSourceError(RuntimeError):
    """Raised when video frames cannot be read safely."""


@dataclass(frozen=True)
class VideoFrameReadDiagnostics:
    requested_frame_index: int
    read_mode: str
    capture_pos_before: float | None
    capture_pos_after: float | None
    used_seek: bool


class VideoFrameSource:
    def __init__(
        self,
        video_path: Path | str,
        cv2_module: Any | None = None,
        capture_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._path = Path(video_path)
        if not self._path.exists():
            raise VideoFrameSourceError(f"Video file does not exist: {self._path}")
        if not self._path.is_file():
            raise VideoFrameSourceError(f"Video path is not a file: {self._path}")

        self._cv2 = cv2_module or _load_cv2()
        factory = capture_factory or self._cv2.VideoCapture
        self._capture = factory(str(self._path))
        self._closed = False
        self._last_frame_index: int | None = None
        self._last_read_diagnostics: VideoFrameReadDiagnostics | None = None

        if not self._capture.isOpened():
            self.close()
            raise VideoFrameSourceError(f"OpenCV could not open video: {self._path}")

        self.frame_count = int(self._capture.get(self._cv2.CAP_PROP_FRAME_COUNT))
        self.fps = float(self._capture.get(self._cv2.CAP_PROP_FPS))
        self.width = int(self._capture.get(self._cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._capture.get(self._cv2.CAP_PROP_FRAME_HEIGHT))

        if self.frame_count <= 0:
            self.close()
            raise VideoFrameSourceError(
                f"Video reports invalid frame count: {self.frame_count}"
            )
        if self.width <= 0 or self.height <= 0:
            self.close()
            raise VideoFrameSourceError(
                f"Video reports invalid resolution: {self.width}x{self.height}"
            )

    def get_frame(self, frame_index: int) -> Any:
        if self._closed:
            raise VideoFrameSourceError("Video frame source is closed")
        if isinstance(frame_index, bool) or not isinstance(frame_index, int):
            raise VideoFrameSourceError("frame_index must be an integer")
        if frame_index < 0 or frame_index >= self.frame_count:
            raise VideoFrameSourceError(
                f"frame_index {frame_index} is outside video range 0-{self.frame_count - 1}"
            )

        capture_pos_before = self._capture_position()
        can_read_sequentially = (
            self._last_frame_index is not None
            and frame_index == self._last_frame_index + 1
        )
        used_seek = not can_read_sequentially
        read_mode = "seek" if used_seek else "sequential_read"

        if used_seek:
            if not self._capture.set(self._cv2.CAP_PROP_POS_FRAMES, frame_index):
                raise VideoFrameSourceError(
                    f"Could not seek to frame {frame_index} in {self._path}"
                )

        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise VideoFrameSourceError(
                f"Could not read frame {frame_index} from {self._path}"
            )

        capture_pos_after = self._capture_position()
        self._last_frame_index = frame_index
        self._last_read_diagnostics = VideoFrameReadDiagnostics(
            requested_frame_index=frame_index,
            read_mode=read_mode,
            capture_pos_before=capture_pos_before,
            capture_pos_after=capture_pos_after,
            used_seek=used_seek,
        )
        return frame

    @property
    def last_read_diagnostics(self) -> VideoFrameReadDiagnostics | None:
        return self._last_read_diagnostics

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        capture = getattr(self, "_capture", None)
        if capture is not None:
            capture.release()

    def __enter__(self) -> VideoFrameSource:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    def _capture_position(self) -> float | None:
        try:
            return float(self._capture.get(self._cv2.CAP_PROP_POS_FRAMES))
        except Exception:
            return None


def _load_cv2() -> Any:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise VideoFrameSourceError(
            "OpenCV is not installed. Run: python -m pip install opencv-python"
        ) from exc
    return cv2

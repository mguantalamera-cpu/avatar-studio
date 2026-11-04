from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np


class VirtualCameraSinkError(RuntimeError):
    """Raised when a frame cannot be delivered to the virtual camera."""


@dataclass(frozen=True)
class VirtualCameraDiagnostics:
    frame_number: int
    send_ms: float
    copied_for_contiguity: bool


@dataclass(frozen=True)
class VirtualCameraStatus:
    device: str
    backend: str
    width: int
    height: int
    fps: float
    frames_sent: int


class VirtualCameraSink:
    """Sends clean OpenCV BGR frames to a pyvirtualcam backend."""

    def __init__(
        self,
        width: int,
        height: int,
        fps: float,
        backend: str | None = "obs",
        device: str | None = None,
        pyvirtualcam_module: Any | None = None,
        camera_factory: Callable[..., Any] | None = None,
    ) -> None:
        if width <= 0 or height <= 0:
            raise VirtualCameraSinkError("Virtual camera resolution must be positive")
        if fps <= 0:
            raise VirtualCameraSinkError("Virtual camera FPS must be positive")

        self.width = int(width)
        self.height = int(height)
        self.fps = float(fps)
        self._module = pyvirtualcam_module or _load_pyvirtualcam()
        factory = camera_factory or self._module.Camera
        try:
            self._camera = factory(
                width=self.width,
                height=self.height,
                fps=self.fps,
                fmt=self._module.PixelFormat.BGR,
                device=device,
                backend=backend,
                print_fps=False,
            )
        except Exception as exc:
            raise VirtualCameraSinkError(
                "Could not open a virtual camera. Verify that the OBS Virtual "
                "Camera is installed, registered, and not in use. "
                f"Backend={backend or 'auto'}; error: {exc}"
            ) from exc

        self.device = str(getattr(self._camera, "device", device or "unknown"))
        self.backend = str(getattr(self._camera, "backend", backend or "auto"))
        self._frames_sent = 0
        self._last_diagnostics: VirtualCameraDiagnostics | None = None
        self._closed = False

    @property
    def frames_sent(self) -> int:
        return self._frames_sent

    @property
    def last_diagnostics(self) -> VirtualCameraDiagnostics | None:
        return self._last_diagnostics

    def send(self, frame: Any) -> None:
        if self._closed:
            raise VirtualCameraSinkError("Virtual camera is closed")
        if not isinstance(frame, np.ndarray):
            raise VirtualCameraSinkError("Virtual camera frame must be a numpy array")
        expected_shape = (self.height, self.width, 3)
        if frame.shape != expected_shape:
            raise VirtualCameraSinkError(
                f"Virtual camera frame shape {frame.shape} does not match "
                f"{expected_shape}; resizing is intentionally disabled"
            )
        if frame.dtype != np.uint8:
            raise VirtualCameraSinkError(
                f"Virtual camera frame dtype {frame.dtype} must be uint8"
            )

        copied_for_contiguity = not frame.flags.c_contiguous
        output_frame = np.ascontiguousarray(frame) if copied_for_contiguity else frame
        started = time.perf_counter()
        try:
            self._camera.send(output_frame)
        except Exception as exc:
            raise VirtualCameraSinkError(
                f"Could not send frame {self._frames_sent} to {self.device}: {exc}"
            ) from exc
        send_ms = (time.perf_counter() - started) * 1000.0
        self._frames_sent += 1
        self._last_diagnostics = VirtualCameraDiagnostics(
            frame_number=self._frames_sent,
            send_ms=send_ms,
            copied_for_contiguity=copied_for_contiguity,
        )

    def status(self) -> VirtualCameraStatus:
        return VirtualCameraStatus(
            device=self.device,
            backend=self.backend,
            width=self.width,
            height=self.height,
            fps=self.fps,
            frames_sent=self._frames_sent,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._camera.close()
        except Exception as exc:
            raise VirtualCameraSinkError(
                f"Could not close virtual camera {self.device}: {exc}"
            ) from exc

    def __enter__(self) -> VirtualCameraSink:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()


def _load_pyvirtualcam() -> Any:
    try:
        import pyvirtualcam
    except ModuleNotFoundError as exc:
        raise VirtualCameraSinkError(
            "pyvirtualcam is not installed. Run: "
            "python -m pip install pyvirtualcam==0.15.0"
        ) from exc
    return pyvirtualcam

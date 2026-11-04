# ruff: noqa: F821

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files
import PySide6


project_root = Path(SPECPATH).resolve().parent
tools_root = project_root / "tools"
source_root = project_root / "src"
if str(source_root) not in sys.path:
    sys.path.insert(0, str(source_root))

SAFE_TOOL_NAMES = (
    "analyze_studio_profile.py",
    "inspect_video_timing.py",
    "mark_segments.py",
    "preview_segments.py",
    "run_avatar_profile.py",
    "run_avatar_studio.py",
)
tool_scripts = [(str(tools_root / name), "tools") for name in SAFE_TOOL_NAMES]
opencv_data = collect_data_files("cv2", includes=["data/*.xml"])
hidden_imports = [
    "av",
    "pyvirtualcam",
    "avatar_controller.auto_segments",
    "avatar_controller.config",
    "avatar_controller.idle_loop",
    "avatar_controller.input_debounce",
    "avatar_controller.playback_cursor",
    "avatar_controller.playback_planner",
    "avatar_controller.playback_queue",
    "avatar_controller.runtime_controller",
    "avatar_controller.segments",
    "avatar_controller.state_machine",
    "avatar_controller.video_frame_source",
    "avatar_controller.video_io",
    "avatar_controller.virtual_camera_sink",
    "avatar_controller.studio.analysis_report",
    "avatar_controller.studio.application",
    "avatar_controller.studio.bootstrap",
    "avatar_controller.studio.commands",
    "avatar_controller.studio.companion",
    "avatar_controller.studio.desktop_runtime",
    "avatar_controller.studio.profiles",
    "avatar_controller.studio.video_preflight",
]

a = Analysis(
    [str(tools_root / "run_avatar_studio.py")],
    pathex=[str(source_root), str(tools_root)],
    binaries=[],
    datas=[*tool_scripts, *opencv_data],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=0,
)
# Python and Qt wheels can carry different MSVC runtime versions. The bootloader
# loads the root copy first, so use Qt's matching redistributables at every copy.
qt_root = Path(PySide6.__file__).resolve().parent
preferred_runtime = {
    path.name.casefold(): path
    for pattern in ("vcruntime140*.dll", "msvcp140*.dll")
    for path in qt_root.glob(pattern)
}
a.binaries = [
    (destination, str(preferred_runtime.get(Path(destination).name.casefold(), source)), kind)
    for destination, source, kind in a.binaries
    if not (Path(destination).parent == Path(".") and destination.casefold() in preferred_runtime)
]
a.binaries.extend((path.name, str(path), "BINARY") for path in preferred_runtime.values())
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AvatarStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(project_root / "packaging" / "avatar_studio_version.txt"),
)

coll = COLLECT(
    exe,
    EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="AvatarStudio-CLI",
        debug=False,
        strip=False,
        upx=False,
        console=True,
        version=str(project_root / "packaging" / "avatar_studio_version.txt"),
    ),
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AvatarStudio",
)

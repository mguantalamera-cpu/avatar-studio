from __future__ import annotations

import argparse
import json
import subprocess
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from avatar_controller.studio.companion import PUBLIC_RUNTIME_MARKER  # noqa: E402

def build_distribution(project_root: Path) -> Path:
    spec_path = project_root / "packaging" / "AvatarStudio.spec"
    release_root = project_root / "release"
    work_root = project_root / "build" / "avatar_studio"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(release_root),
        "--workpath",
        str(work_root),
        str(spec_path),
    ]
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    if os.name == "nt":
        windows = Path(environment.get("SystemRoot", r"C:\Windows"))
        environment["PATH"] = os.pathsep.join((
            str(Path(sys.executable).parent), str(windows / "System32"), str(windows),
        ))
    subprocess.run(command, cwd=project_root, check=True, env=environment)
    installation_dir = release_root / "AvatarStudio"
    executable_path = installation_dir / "AvatarStudio.exe"
    if not executable_path.is_file():
        raise RuntimeError(f"Avatar Studio executable was not created: {executable_path}")
    if not (installation_dir / "AvatarStudio-CLI.exe").is_file():
        raise RuntimeError("Avatar Studio diagnostic CLI executable was not created")
    (installation_dir / "avatar_studio_project.json").write_text(
        json.dumps(PUBLIC_RUNTIME_MARKER, indent=2) + "\n", encoding="utf-8"
    )
    return executable_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Avatar Studio Windows desktop distribution."
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    try:
        executable_path = build_distribution(args.project_root.resolve())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Avatar Studio build failed: {exc}", file=sys.stderr)
        return 2
    print(f"Avatar Studio executable: {executable_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQ_FILE = ROOT / "requirements.txt"
STAMP_FILE = VENV_DIR / ".requirements_installed"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_venv() -> None:
    if venv_python().exists():
        return
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True, cwd=ROOT)


def ensure_dependencies() -> None:
    if STAMP_FILE.exists() and STAMP_FILE.read_text(encoding="utf-8") == REQ_FILE.read_text(encoding="utf-8"):
        return

    subprocess.run([str(venv_python()), "-m", "pip", "install", "--upgrade", "pip"], check=True, cwd=ROOT)
    subprocess.run([str(venv_python()), "-m", "pip", "install", "-r", str(REQ_FILE)], check=True, cwd=ROOT)
    STAMP_FILE.write_text(REQ_FILE.read_text(encoding="utf-8"), encoding="utf-8")


def run_app() -> int:
    result = subprocess.run([str(venv_python()), str(ROOT / "main.py")], cwd=ROOT)
    return int(result.returncode)


def main() -> int:
    ensure_venv()
    ensure_dependencies()
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())

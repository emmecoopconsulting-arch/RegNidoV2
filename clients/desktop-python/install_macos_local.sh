#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="regnido-desktop"
INSTALL_ROOT="${INSTALL_ROOT:-/Applications}"
TARGET_APP="${INSTALL_ROOT}/${APP_NAME}.app"
CACHE_ROOT="${CACHE_ROOT:-$HOME/Library/Caches/RegNidoDesktopBuild}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Errore: questo script e solo per macOS."
  exit 1
fi

MACHINE_ARCH="$(uname -m)"
case "$MACHINE_ARCH" in
  arm64|x86_64) ;;
  *)
    echo "Errore: architettura non supportata: $MACHINE_ARCH"
    exit 1
    ;;
esac

ensure_homebrew() {
  if command -v brew >/dev/null 2>&1; then
    return
  fi

  echo "==> Homebrew non trovato. Installazione in corso..."
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
}

ensure_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi

  ensure_homebrew
  echo "==> Python3 non trovato. Installazione in corso..."
  brew install python@3.13
  command -v python3
}

echo "==> Installazione locale RegNido Desktop (${MACHINE_ARCH})"
PYTHON_BIN="$(ensure_python)"
VENV_PATH="$CACHE_ROOT/.venv-client-build-${MACHINE_ARCH}"
DIST_PATH="$CACHE_ROOT/dist/local-${MACHINE_ARCH}"
WORK_PATH="$CACHE_ROOT/build/local-${MACHINE_ARCH}"
SPEC_PATH="$CACHE_ROOT/build/local-spec-${MACHINE_ARCH}"
APP_BUNDLE="$DIST_PATH/${APP_NAME}.app"
APP_BINARY="$APP_BUNDLE/Contents/MacOS/${APP_NAME}"

mkdir -p "$CACHE_ROOT"
rm -rf "$DIST_PATH" "$WORK_PATH" "$SPEC_PATH"

"$PYTHON_BIN" -m venv "$VENV_PATH"
"$VENV_PATH/bin/python" -m pip install --upgrade pip
"$VENV_PATH/bin/python" -m pip install -r "$ROOT_DIR/requirements.txt" pyinstaller

echo "==> Build PyInstaller..."
"$VENV_PATH/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --name "$APP_NAME" \
  --windowed \
  --onedir \
  --distpath "$DIST_PATH" \
  --workpath "$WORK_PATH" \
  --specpath "$SPEC_PATH" \
  "$ROOT_DIR/main.py"

if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "Errore: bundle .app non trovato: $APP_BUNDLE"
  exit 1
fi

if [[ ! -f "$APP_BINARY" ]]; then
  echo "Errore: eseguibile non trovato: $APP_BINARY"
  exit 1
fi

BIN_INFO="$(lipo -info "$APP_BINARY")"
if [[ "$MACHINE_ARCH" == "arm64" && "$BIN_INFO" != *"arm64"* ]]; then
  echo "Errore: binario non arm64 (${BIN_INFO})"
  exit 1
fi
if [[ "$MACHINE_ARCH" == "x86_64" && "$BIN_INFO" != *"x86_64"* ]]; then
  echo "Errore: binario non x86_64 (${BIN_INFO})"
  exit 1
fi

echo "==> Installazione app in ${TARGET_APP}"
if [[ -w "$INSTALL_ROOT" ]]; then
  rm -rf "$TARGET_APP"
  ditto "$APP_BUNDLE" "$TARGET_APP"
  xattr -dr com.apple.quarantine "$TARGET_APP" 2>/dev/null || true
else
  sudo rm -rf "$TARGET_APP"
  sudo ditto "$APP_BUNDLE" "$TARGET_APP"
  sudo xattr -dr com.apple.quarantine "$TARGET_APP" 2>/dev/null || true
fi

echo "==> Installazione completata."
echo "Apri l'app da Applicazioni: ${TARGET_APP}"
echo "Oppure da terminale: open \"$TARGET_APP\""

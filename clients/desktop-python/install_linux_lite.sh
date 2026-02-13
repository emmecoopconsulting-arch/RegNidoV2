#!/usr/bin/env bash
set -euo pipefail

APP_NAME="RegNido Desktop"
BIN_NAME="regnido-desktop"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${SCRIPT_DIR}"
VENV_DIR="${APP_DIR}/.venv"
REQ_FILE="${APP_DIR}/requirements.txt"

TARGET_USER="$(id -un)"
TARGET_HOME="${HOME}"
if [[ "$(id -u)" -eq 0 ]] && [[ -n "${SUDO_USER:-}" ]] && [[ "${SUDO_USER}" != "root" ]]; then
  TARGET_USER="${SUDO_USER}"
  TARGET_HOME="$(getent passwd "${TARGET_USER}" | cut -d: -f6)"
fi

LAUNCHER_DIR="${TARGET_HOME}/.local/bin"
DESKTOP_DIR="${TARGET_HOME}/.local/share/applications"
AUTOSTART_DIR="${TARGET_HOME}/.config/autostart"
LAUNCHER_PATH="${LAUNCHER_DIR}/${BIN_NAME}"
DESKTOP_FILE="${DESKTOP_DIR}/${BIN_NAME}.desktop"
AUTOSTART_FILE="${AUTOSTART_DIR}/${BIN_NAME}.desktop"

WITH_AUTOSTART=0
if [[ "${1:-}" == "--autostart" ]]; then
  WITH_AUTOSTART=1
fi

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Errore: comando richiesto non trovato: $1" >&2
    exit 1
  fi
}

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "Errore: servono privilegi root e sudo non e disponibile." >&2
    exit 1
  fi
}

fix_owner() {
  if [[ "$(id -u)" -eq 0 ]]; then
    chown "${TARGET_USER}:${TARGET_USER}" "$@"
  fi
}

echo "[1/6] Verifica prerequisiti..."
need_cmd apt-get
need_cmd python3

echo "[2/6] Installazione dipendenze di sistema (Linux Lite/Ubuntu)..."
run_root apt-get update
run_root apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  build-essential \
  patchelf \
  libgl1 \
  libegl1 \
  libxkbcommon-x11-0 \
  libxcb-cursor0 \
  libxcb-icccm4 \
  libxcb-keysyms1 \
  libxcb-image0 \
  libxcb-render-util0 \
  libxcb-xinerama0 \
  libfontconfig1

echo "[3/6] Creazione/aggiornamento virtualenv..."
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${REQ_FILE}"

echo "[4/6] Creazione launcher CLI..."
mkdir -p "${LAUNCHER_DIR}"
cat > "${LAUNCHER_PATH}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${VENV_DIR}/bin/python" "${APP_DIR}/main.py" "\$@"
EOF
chmod +x "${LAUNCHER_PATH}"
fix_owner "${LAUNCHER_PATH}" "${LAUNCHER_DIR}"

echo "[5/6] Creazione icona menu desktop..."
mkdir -p "${DESKTOP_DIR}"
cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Name=${APP_NAME}
Comment=Client desktop RegNido
Exec=${LAUNCHER_PATH}
Terminal=false
Type=Application
Categories=Office;Education;
StartupNotify=true
EOF
chmod 644 "${DESKTOP_FILE}"
fix_owner "${DESKTOP_FILE}" "${DESKTOP_DIR}"

if [[ "${WITH_AUTOSTART}" -eq 1 ]]; then
  echo "[6/6] Abilitazione avvio automatico..."
  mkdir -p "${AUTOSTART_DIR}"
  cp "${DESKTOP_FILE}" "${AUTOSTART_FILE}"
  fix_owner "${AUTOSTART_FILE}" "${AUTOSTART_DIR}"
else
  echo "[6/6] Avvio automatico non richiesto (usa --autostart per abilitarlo)."
fi

echo
echo "Installazione completata."
echo "- Avvio da terminale: ${LAUNCHER_PATH}"
echo "- Avvio da menu applicazioni: ${APP_NAME}"
if [[ "${WITH_AUTOSTART}" -eq 1 ]]; then
  echo "- Avvio automatico: abilitato"
fi

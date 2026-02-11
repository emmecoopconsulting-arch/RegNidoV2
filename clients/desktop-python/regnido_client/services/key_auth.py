import base64
import json
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def read_key_file(path: str) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if payload.get("format") != "regnido-key-v1":
        raise ValueError("Formato file chiave non supportato")
    if "key_id" not in payload or "encrypted_private_key_pem" not in payload:
        raise ValueError("File chiave incompleto")
    return payload


def sign_challenge(key_payload: dict, passphrase: str, challenge: str) -> tuple[str, str]:
    key_id = str(key_payload.get("key_id", "")).strip()
    private_key_pem = str(key_payload.get("encrypted_private_key_pem", ""))
    if not key_id or not private_key_pem:
        raise ValueError("File chiave non valido")
    key_uuid = str(uuid.UUID(key_id))
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=passphrase.encode("utf-8"),
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("Algoritmo chiave non supportato")
    signature = private_key.sign(challenge.encode("utf-8"))
    signature_b64 = base64.b64encode(signature).decode("utf-8")
    return key_uuid, signature_b64

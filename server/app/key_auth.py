import base64
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


KEY_FILE_FORMAT = "regnido-key-v1"


def generate_ed25519_keypair() -> tuple[str, str, str]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    ).decode("utf-8")
    public_pem = public_key.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    fingerprint = hashlib.sha256(
        public_key.public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )
    ).hexdigest()
    return private_pem, public_pem, fingerprint


def encrypt_private_key_pem(private_key_pem: str, passphrase: str) -> str:
    private_key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    encrypted = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=BestAvailableEncryption(passphrase.encode("utf-8")),
    )
    return encrypted.decode("utf-8")


def build_key_file_payload(
    *,
    key_id: uuid.UUID,
    username: str,
    role: str,
    sede_id: uuid.UUID | None,
    fingerprint: str,
    encrypted_private_key_pem: str,
    valid_to: datetime | None,
) -> str:
    payload = {
        "format": KEY_FILE_FORMAT,
        "algorithm": "Ed25519",
        "key_id": str(key_id),
        "username": username,
        "role": role,
        "sede_id": str(sede_id) if sede_id else None,
        "fingerprint": fingerprint,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": valid_to.isoformat() if valid_to else None,
        "encrypted_private_key_pem": encrypted_private_key_pem,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def verify_signature(public_key_pem: str, challenge: str, signature_b64: str) -> bool:
    try:
        signature = base64.b64decode(signature_b64.encode("utf-8"), validate=True)
    except Exception:
        return False
    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        if not isinstance(public_key, Ed25519PublicKey):
            return False
        public_key.verify(signature, challenge.encode("utf-8"))
        return True
    except Exception:
        return False


def new_challenge() -> str:
    raw = uuid.uuid4().bytes + uuid.uuid4().bytes
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def valid_until(days: int) -> datetime:
    bounded_days = max(1, min(days, 3650))
    return datetime.now(timezone.utc) + timedelta(days=bounded_days)

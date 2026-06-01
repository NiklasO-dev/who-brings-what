import base64
import hashlib
import secrets
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENC_PREFIX = "enc:"


def generate_encryption_key() -> str:
    return str(uuid.uuid4())


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def verify_key(key: str, key_hash: str) -> bool:
    return secrets.compare_digest(hash_key(key), key_hash)


def _derive_aes_key(key: str) -> bytes:
    return hashlib.sha256(key.encode("utf-8")).digest()


def encrypt(plaintext: str, key: str) -> str:
    if plaintext == "":
        return ""
    aesgcm = AESGCM(_derive_aes_key(key))
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return f"{ENC_PREFIX}{encoded}"


def decrypt(ciphertext: str, key: str) -> str:
    if ciphertext == "":
        return ""
    if not ciphertext.startswith(ENC_PREFIX):
        return ciphertext
    raw = base64.urlsafe_b64decode(ciphertext[len(ENC_PREFIX) :].encode("ascii"))
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(_derive_aes_key(key))
    return aesgcm.decrypt(nonce, ct, None).decode("utf-8")


def encrypt_optional(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    return encrypt(value, key)


def decrypt_optional(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    return decrypt(value, key)

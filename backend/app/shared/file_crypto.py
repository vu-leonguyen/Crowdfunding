"""AES-256-GCM envelope for access-controlled files pinned to IPFS.

Layout: MAGIC | uint32 header length | header JSON | 12-byte nonce | ciphertext+tag.
The header (kind, campaign, MIME type, deployment) is authenticated as GCM
associated data, so it cannot be altered to bypass the access policy. Anyone can
fetch the bytes from IPFS, but only the backend (holding FILE_ENCRYPTION_KEY)
can decrypt them, and it only does so after an on-chain role check.
"""
import base64
import binascii
import json
import os
import struct

from Crypto.Cipher import AES

from app.core.errors import ServiceError

MAGIC = b"CROWDOPS-ENC1\n"
NONCE_BYTES = 12
TAG_BYTES = 16


def load_key(encoded: str) -> bytes:
    if not encoded:
        raise ServiceError(503, "encryption_not_configured", "FILE_ENCRYPTION_KEY is not configured.")
    try:
        key = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        key = b""
    if len(key) != 32:
        raise ServiceError(503, "encryption_not_configured", "FILE_ENCRYPTION_KEY must be 32 bytes (base64).")
    return key


def encrypt(key: bytes, header: dict, plaintext: bytes) -> bytes:
    header_bytes = json.dumps(header, separators=(",", ":"), sort_keys=True).encode()
    prefix = MAGIC + struct.pack(">I", len(header_bytes)) + header_bytes
    nonce = os.urandom(NONCE_BYTES)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    cipher.update(prefix)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return prefix + nonce + ciphertext + tag


def is_envelope(data: bytes) -> bool:
    return data.startswith(MAGIC)


def read_header(data: bytes) -> tuple[dict, int]:
    """Returns the (not yet authenticated) header and the offset of the nonce."""
    try:
        start = len(MAGIC)
        (length,) = struct.unpack(">I", data[start:start + 4])
        end = start + 4 + length
        header = json.loads(data[start + 4:end])
        if not isinstance(header, dict) or len(data) < end + NONCE_BYTES + TAG_BYTES:
            raise ValueError
        return header, end
    except (struct.error, ValueError, UnicodeDecodeError):
        raise ServiceError(422, "invalid_envelope", "Stored file is corrupted.") from None


def decrypt(key: bytes, data: bytes) -> tuple[dict, bytes]:
    header, offset = read_header(data)
    nonce = data[offset:offset + NONCE_BYTES]
    body, tag = data[offset + NONCE_BYTES:-TAG_BYTES], data[-TAG_BYTES:]
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    cipher.update(data[:offset])
    try:
        return header, cipher.decrypt_and_verify(body, tag)
    except ValueError:
        raise ServiceError(422, "invalid_envelope", "Stored file failed integrity check.") from None

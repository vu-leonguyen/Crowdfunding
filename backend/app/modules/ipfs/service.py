import json
import re

import httpx
from fastapi import UploadFile

from app.config import Settings
from app.core.errors import ServiceError
from app.modules.ipfs.dto import UploadResponse
from app.shared import file_crypto

PDF = ("application/pdf", "pdf")
PNG = ("image/png", "png")
JPEG = ("image/jpeg", "jpg")
GIF = ("image/gif", "gif")
WEBP = ("image/webp", "webp")
MP4 = ("video/mp4", "mp4")
WEBM = ("video/webm", "webm")

# File types accepted per resource kind (validated from the bytes, not the client MIME header).
ALLOWED_TYPES: dict[str, set[tuple[str, str]]] = {
    "proposal": {PDF},
    "media": {PNG, JPEG, GIF, WEBP, MP4, WEBM},
    "proof": {PDF, PNG, JPEG},
    "exclusive": {PDF, PNG, JPEG, GIF, WEBP, MP4, WEBM},
}
LARGE_KINDS = {"media", "exclusive"}
TYPE_HINTS = {
    "proposal": "Proposal requires PDF",
    "media": "Media supports PNG, JPEG, GIF, WEBP, MP4 or WEBM",
    "proof": "Proof supports PDF, PNG or JPEG",
    "exclusive": "Exclusive content supports PDF, images, MP4 or WEBM",
}
CID_PATTERN = re.compile(r"^(Qm[1-9A-HJ-NP-Za-km-z]{44}|b[a-z2-7]{20,})$")
PINATA_FILE_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
PINATA_JSON_URL = "https://api.pinata.cloud/pinning/pinJSONToIPFS"


def sniff(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"%PDF-"):
        return PDF
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith((b"GIF87a", b"GIF89a")):
        return GIF
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return WEBP
    if data[4:8] == b"ftyp":
        return MP4
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return WEBM
    return None


def validate_cid(cid: str) -> str:
    if not CID_PATTERN.match(cid):
        raise ServiceError(422, "invalid_cid", "Invalid IPFS CID.")
    return cid


class IPFSService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client

    def _limit(self, kind: str) -> int:
        return self.settings.max_media_bytes if kind in LARGE_KINDS else self.settings.max_upload_bytes

    async def _read(self, file: UploadFile, kind: str) -> tuple[bytes, tuple[str, str]]:
        limit = self._limit(kind)
        try:
            data = await file.read(limit + 1)
        finally:
            await file.close()
        if len(data) > limit:
            raise ServiceError(413, "file_too_large", "File exceeds the upload size limit.")
        if not data:
            raise ServiceError(422, "empty_file", "File is empty.")
        detected = sniff(data)
        if detected not in ALLOWED_TYPES[kind]:
            raise ServiceError(415, "unsupported_file", f"{TYPE_HINTS[kind]}.")
        return data, detected

    def _token(self) -> str:
        token = self.settings.pinata_jwt.get_secret_value()
        if not token:
            raise ServiceError(503, "pinata_not_configured", "PINATA_JWT is not configured.")
        return token

    async def _pin(self, request) -> str:
        try:
            response = await request
            response.raise_for_status()
            cid = response.json()["IpfsHash"]
            if not isinstance(cid, str) or not cid.isalnum() or len(cid) < 10:
                raise ValueError("Invalid CID")
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ServiceError(502, "pinata_failed", "Pinata upload failed. Please retry later.") from None
        return cid

    def _response(self, cid: str, size: int, kind: str, encrypted: bool, mime: str) -> UploadResponse:
        return UploadResponse(cid=cid, ipfs_uri=f"ipfs://{cid}",
                              gateway_url=f"{self.settings.ipfs_gateway_url.rstrip('/')}/{cid}",
                              size=size, kind=kind, encrypted=encrypted, mime_type=mime)

    async def upload(self, file: UploadFile, kind: str) -> UploadResponse:
        """Public kinds (proposal, media): pinned as-is so anyone can retrieve them by CID."""
        data, (mime, suffix) = await self._read(file, kind)
        token = self._token()
        cid = await self._pin(self.client.post(
            PINATA_FILE_URL, headers={"Authorization": f"Bearer {token}"},
            files={"file": (f"{kind}.{suffix}", data, mime)},
            data={"pinataMetadata": json.dumps({"name": f"crowdops-{kind}"})},
        ))
        return self._response(cid, len(data), kind, False, mime)

    async def upload_protected(self, file: UploadFile, kind: str, campaign_id: int,
                               uploader: str) -> UploadResponse:
        """Protected kinds (proof, exclusive): AES-256-GCM encrypted before pinning."""
        key = file_crypto.load_key(self.settings.file_encryption_key.get_secret_value())
        data, (mime, suffix) = await self._read(file, kind)
        token = self._token()
        header = {"v": 1, "kind": kind, "campaign_id": campaign_id, "mime": mime,
                  "name": f"{kind}-{campaign_id}.{suffix}", "uploader": uploader,
                  "chain_id": self.settings.chain_id,
                  "platform": self.settings.platform_address.lower()}
        sealed = file_crypto.encrypt(key, header, data)
        cid = await self._pin(self.client.post(
            PINATA_FILE_URL, headers={"Authorization": f"Bearer {token}"},
            files={"file": (f"{kind}-{campaign_id}.enc", sealed, "application/octet-stream")},
            data={"pinataMetadata": json.dumps({"name": f"crowdops-{kind}-{campaign_id}"})},
        ))
        return self._response(cid, len(data), kind, True, mime)

    async def upload_metadata(self, metadata: dict) -> UploadResponse:
        """Public JSON metadata (e.g. campaign card linking proposal + media CIDs)."""
        token = self._token()
        size = len(json.dumps(metadata).encode())
        if size > self.settings.max_upload_bytes:
            raise ServiceError(413, "file_too_large", "Metadata exceeds the upload size limit.")
        cid = await self._pin(self.client.post(
            PINATA_JSON_URL, headers={"Authorization": f"Bearer {token}"},
            json={"pinataContent": metadata, "pinataMetadata": {"name": "crowdops-metadata"}},
        ))
        return self._response(cid, size, "metadata", False, "application/json")

    async def fetch(self, cid: str) -> bytes:
        """Download raw bytes for a CID from the configured gateway (size-limited)."""
        validate_cid(cid)
        url = f"{self.settings.ipfs_gateway_url.rstrip('/')}/{cid}"
        limit = self.settings.max_media_bytes + 64 * 1024
        try:
            async with self.client.stream("GET", url, follow_redirects=True) as response:
                if response.status_code == 404:
                    raise ServiceError(404, "file_not_found", "File not found on IPFS.")
                response.raise_for_status()
                chunks, total = [], 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > limit:
                        raise ServiceError(413, "file_too_large", "Stored file exceeds the size limit.")
                    chunks.append(chunk)
        except ServiceError:
            raise
        except httpx.HTTPError:
            raise ServiceError(502, "gateway_failed", "IPFS gateway is unavailable.") from None
        return b"".join(chunks)

    def open_envelope(self, data: bytes) -> tuple[dict, bytes]:
        """Decrypt a protected file and confirm it belongs to this deployment."""
        if not file_crypto.is_envelope(data):
            raise ServiceError(409, "not_protected",
                               "This CID is public content; open it via the IPFS gateway.")
        key = file_crypto.load_key(self.settings.file_encryption_key.get_secret_value())
        header, plaintext = file_crypto.decrypt(key, data)
        if (header.get("chain_id") != self.settings.chain_id
                or header.get("platform") != self.settings.platform_address.lower()
                or header.get("kind") not in ALLOWED_TYPES
                or not isinstance(header.get("campaign_id"), int)):
            raise ServiceError(409, "foreign_file", "File was not issued by this CrowdOps deployment.")
        return header, plaintext

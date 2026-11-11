import json
import httpx
from fastapi import UploadFile
from app.config import Settings
from app.core.errors import ServiceError
from app.modules.ipfs.dto import UploadResponse


class IPFSService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client

    async def upload(self, file: UploadFile, kind: str) -> UploadResponse:
        try:
            data = await file.read(self.settings.max_upload_bytes + 1)
        finally:
            await file.close()
        if len(data) > self.settings.max_upload_bytes:
            raise ServiceError(413, "file_too_large", "File exceeds MAX_UPLOAD_BYTES.")
        if not data:
            raise ServiceError(422, "empty_file", "File is empty.")
        # Validate bytes rather than trusting the client-provided MIME header.
        if data.startswith(b"%PDF-"):
            mime, suffix = "application/pdf", "pdf"
        elif kind == "proof" and data.startswith(b"\x89PNG\r\n\x1a\n"):
            mime, suffix = "image/png", "png"
        elif kind == "proof" and data.startswith(b"\xff\xd8\xff"):
            mime, suffix = "image/jpeg", "jpg"
        else:
            raise ServiceError(415, "unsupported_file", "Proposal requires PDF; proof supports PDF, PNG or JPEG.")
        token = self.settings.pinata_jwt.get_secret_value()
        if not token:
            raise ServiceError(503, "pinata_not_configured", "PINATA_JWT is not configured.")
        try:
            response = await self.client.post(
                "https://api.pinata.cloud/pinning/pinFileToIPFS",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (f"{kind}.{suffix}", data, mime)},
                data={"pinataMetadata": json.dumps({"name": f"crowdops-{kind}"})},
            )
            response.raise_for_status()
            cid = response.json()["IpfsHash"]
            if not isinstance(cid, str) or not cid.isalnum() or len(cid) < 10:
                raise ValueError("Invalid CID")
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ServiceError(502, "pinata_failed", "Pinata upload failed. Please retry later.") from None
        return UploadResponse(cid=cid, ipfs_uri=f"ipfs://{cid}",
                              gateway_url=f"{self.settings.ipfs_gateway_url.rstrip('/')}/{cid}", size=len(data))

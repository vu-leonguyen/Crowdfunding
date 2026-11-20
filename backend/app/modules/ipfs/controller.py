"""IPFS endpoints with role-based access control.

| Kind      | Stored        | Upload            | Read                                   |
|-----------|---------------|-------------------|----------------------------------------|
| proposal  | plain (PDF)   | any signed wallet | anyone (gateway)                       |
| media     | plain         | any signed wallet | anyone (gateway)                       |
| metadata  | plain (JSON)  | any signed wallet | anyone (gateway)                       |
| proof     | AES-256-GCM   | campaign creator  | creator or backer (GET /ipfs/files)    |
| exclusive | AES-256-GCM   | campaign creator  | creator, or backer holding Diamond NFT |
"""
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.config import Settings, get_settings
from app.core.errors import ServiceError
from app.modules.auth.controller import get_access_service, require_wallet
from app.modules.auth.service import AccessService, can_read, can_upload
from app.modules.ipfs.dto import UploadResponse
from app.modules.ipfs.service import IPFSService

router = APIRouter(prefix="/ipfs", tags=["IPFS"])


def get_ipfs_service(request: Request, settings: Settings = Depends(get_settings)):
    return IPFSService(settings, request.app.state.http_client)


@router.post("/proposal", response_model=UploadResponse)
async def upload_proposal(file: UploadFile = File(...), _wallet: str = Depends(require_wallet),
                          service: IPFSService = Depends(get_ipfs_service)):
    """Whitepaper / proposal PDF. Public: its CID is stored on-chain in createCampaign."""
    return await service.upload(file, "proposal")


@router.post("/media", response_model=UploadResponse)
async def upload_media(file: UploadFile = File(...), _wallet: str = Depends(require_wallet),
                       service: IPFSService = Depends(get_ipfs_service)):
    """Campaign images / videos (PNG, JPEG, GIF, WEBP, MP4, WEBM). Public."""
    return await service.upload(file, "media")


@router.post("/metadata", response_model=UploadResponse)
async def upload_metadata(metadata: dict[str, Any] = Body(...), _wallet: str = Depends(require_wallet),
                          service: IPFSService = Depends(get_ipfs_service)):
    """JSON metadata, e.g. {"proposal": "ipfs://...", "cover": "ipfs://..."}. Public."""
    return await service.upload_metadata(metadata)


async def _upload_protected(kind: str, file: UploadFile, campaign_id: int, wallet: str,
                            access: AccessService, service: IPFSService) -> UploadResponse:
    if not can_upload(kind, access.roles(wallet, campaign_id)):
        raise ServiceError(403, "forbidden", f"Only the campaign creator can upload {kind} files.")
    return await service.upload_protected(file, kind, campaign_id, wallet)


@router.post("/proof", response_model=UploadResponse)
async def upload_proof(file: UploadFile = File(...), campaign_id: int = Form(..., ge=1),
                       wallet: str = Depends(require_wallet),
                       access: AccessService = Depends(get_access_service),
                       service: IPFSService = Depends(get_ipfs_service)):
    """Spending proof (invoice PDF/image). Creator only; encrypted; readable by backers."""
    return await _upload_protected("proof", file, campaign_id, wallet, access, service)


@router.post("/exclusive", response_model=UploadResponse)
async def upload_exclusive(file: UploadFile = File(...), campaign_id: int = Form(..., ge=1),
                           wallet: str = Depends(require_wallet),
                           access: AccessService = Depends(get_access_service),
                           service: IPFSService = Depends(get_ipfs_service)):
    """Exclusive content for Diamond Patron backers. Creator only; encrypted."""
    return await _upload_protected("exclusive", file, campaign_id, wallet, access, service)


@router.get("/files/{cid}")
async def download_protected(cid: str, wallet: str = Depends(require_wallet),
                             access: AccessService = Depends(get_access_service),
                             service: IPFSService = Depends(get_ipfs_service)):
    """Retrieve and decrypt a protected file after checking the caller's on-chain roles."""
    header, plaintext = service.open_envelope(await service.fetch(cid))
    if not can_read(header["kind"], access.roles(wallet, header["campaign_id"])):
        raise ServiceError(403, "forbidden", "Your wallet does not have access to this file.")
    return Response(content=plaintext, media_type=header["mime"], headers={
        "Content-Disposition": f'inline; filename="{header["name"]}"',
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    })

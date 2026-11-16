from fastapi import APIRouter, Request, UploadFile, File, Depends
from app.config import Settings, get_settings
from app.modules.ipfs.service import IPFSService
from app.modules.ipfs.dto import UploadResponse

router = APIRouter(prefix="/ipfs", tags=["IPFS"])


def get_ipfs_service(request: Request, settings: Settings = Depends(get_settings)):
    return IPFSService(settings, request.app.state.http_client)


@router.post("/proposal", response_model=UploadResponse)
async def upload_proposal(file: UploadFile = File(...), service: IPFSService = Depends(get_ipfs_service)):
    return await service.upload(file, "proposal")


@router.post("/proof", response_model=UploadResponse)
async def upload_proof(file: UploadFile = File(...), service: IPFSService = Depends(get_ipfs_service)):
    return await service.upload(file, "proof")

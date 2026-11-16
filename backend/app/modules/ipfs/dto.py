from pydantic import BaseModel


class UploadResponse(BaseModel):
    cid: str
    ipfs_uri: str
    gateway_url: str
    size: int

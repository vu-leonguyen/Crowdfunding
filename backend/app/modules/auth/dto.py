from pydantic import BaseModel


class ChallengeResponse(BaseModel):
    address: str
    issued_at: int
    message: str


class RolesResponse(BaseModel):
    address: str
    campaign_id: int | None
    roles: list[str]
    can_upload: dict[str, bool]
    can_read: dict[str, bool]

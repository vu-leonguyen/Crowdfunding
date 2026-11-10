from pydantic import BaseModel, Field


class CreateCampaignDto(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    proposal_cid: str = Field(min_length=1)
    goal_wei: int = Field(gt=0)
    duration_seconds: int = Field(ge=60)  # khớp MIN_DURATION của contract

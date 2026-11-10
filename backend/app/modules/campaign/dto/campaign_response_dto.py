from pydantic import BaseModel

STATES = ["Fundraising", "Successful", "Failed", "Operational", "Closed"]


class CampaignResponseDto(BaseModel):
    id: int
    creator: str
    title: str
    description: str
    proposal_cid: str
    goal_wei: int
    deadline: int
    total_raised_wei: int
    remaining_wei: int
    state: str
    request_count: int


class CampaignStatsDto(BaseModel):
    id: int
    progress_percent: float
    seconds_left: int
    state: str

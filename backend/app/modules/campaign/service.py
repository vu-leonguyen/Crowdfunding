import time

from .dto.campaign_response_dto import STATES, CampaignResponseDto, CampaignStatsDto


class CampaignNotFound(Exception):
    pass


class CampaignService:
    def __init__(self, contract):
        self.c = contract.functions

    def _count(self) -> int:
        return self.c.campaignCounter().call()

    def get(self, campaign_id: int) -> CampaignResponseDto:
        if not 1 <= campaign_id <= self._count():
            raise CampaignNotFound(campaign_id)
        # Thứ tự field = CampaignView trong ICrowdOps.sol
        (id_, creator, title, desc, cid, goal, deadline, raised, remaining, state, n) = (
            self.c.getCampaign(campaign_id).call()
        )
        return CampaignResponseDto(
            id=id_, creator=creator, title=title, description=desc, proposal_cid=cid,
            goal_wei=goal, deadline=deadline, total_raised_wei=raised,
            remaining_wei=remaining, state=STATES[state], request_count=n,
        )

    def list(self) -> list[CampaignResponseDto]:
        # shortcut: N lần gọi RPC, cần cache/index khi số campaign lớn
        return [self.get(i) for i in range(1, self._count() + 1)]

    def stats(self, campaign_id: int, now: int | None = None) -> CampaignStatsDto:
        c = self.get(campaign_id)
        now = int(time.time()) if now is None else now
        return CampaignStatsDto(
            id=c.id,
            progress_percent=round(c.total_raised_wei * 100 / c.goal_wei, 2),
            seconds_left=max(0, c.deadline - now),
            state=c.state,
        )

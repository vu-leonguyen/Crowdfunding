from app.modules.campaign.service import CampaignNotFound, CampaignService

from .dto.spending_request_dto import SpendingRequestDto

__all__ = ["VotingService", "CampaignNotFound"]


class VotingService:
    def __init__(self, contract):
        self.contract = contract.functions
        self.campaigns = CampaignService(contract)

    def list_requests(self, campaign_id: int) -> list[SpendingRequestDto]:
        camp = self.campaigns.get(campaign_id)  # ném CampaignNotFound nếu sai id
        total = camp.total_raised_wei
        out = []
        for rid in range(1, camp.request_count + 1):
            # Thứ tự field = SpendingRequestView trong ICrowdOps.sol
            (id_, desc, amount, recipient, cid, appr, rej, done, rejected) = (
                self.contract.getSpendingRequest(campaign_id, rid).call()
            )
            out.append(SpendingRequestDto(
                id=id_, description=desc, amount_wei=amount, recipient=recipient,
                proof_cid=cid, approval_weight_wei=appr, reject_weight_wei=rej,
                approval_percent=round(appr * 100 / total, 2) if total else 0.0,
                reject_percent=round(rej * 100 / total, 2) if total else 0.0,
                passes_threshold=appr * 2 > total,
                completed=done, rejected=rejected,
            ))
        return out

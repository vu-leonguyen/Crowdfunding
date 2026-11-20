from fastapi import APIRouter, Depends

from app.core.errors import ServiceError

from app.shared.contract_loader import get_contract

from .dto.spending_request_dto import SpendingRequestDto
from .service import CampaignNotFound, VotingService

router = APIRouter(prefix="/campaigns", tags=["voting"])


@router.get("/{campaign_id}/requests", response_model=list[SpendingRequestDto])
def list_requests(campaign_id: int, contract=Depends(get_contract)):
    try:
        return VotingService(contract).list_requests(campaign_id)
    except CampaignNotFound:
        raise ServiceError(404, "campaign_not_found", "Campaign not found.") from None

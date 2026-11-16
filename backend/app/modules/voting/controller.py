from fastapi import APIRouter, Depends, HTTPException

from app.shared.contract_loader import get_contract

from .dto.spending_request_dto import SpendingRequestDto
from .service import CampaignNotFound, VotingService

router = APIRouter(prefix="/campaigns", tags=["voting"])


@router.get("/{campaign_id}/requests", response_model=list[SpendingRequestDto])
def list_requests(campaign_id: int, contract=Depends(get_contract)):
    try:
        return VotingService(contract).list_requests(campaign_id)
    except CampaignNotFound:
        raise HTTPException(404, "Campaign not found")

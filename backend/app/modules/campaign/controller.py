from fastapi import APIRouter, Depends, HTTPException

# TV3 cung cấp get_contract() trả về web3 Contract của CrowdOpsPlatform
from app.shared.contract_loader import get_contract

from .dto.campaign_response_dto import CampaignResponseDto, CampaignStatsDto
from .service import CampaignNotFound, CampaignService

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def get_service(contract=Depends(get_contract)) -> CampaignService:
    return CampaignService(contract)


def _call(fn, *args):
    try:
        return fn(*args)
    except CampaignNotFound:
        raise HTTPException(404, "Campaign not found")


@router.get("", response_model=list[CampaignResponseDto])
def list_campaigns(s: CampaignService = Depends(get_service)):
    return s.list()


@router.get("/{campaign_id}", response_model=CampaignResponseDto)
def get_campaign(campaign_id: int, s: CampaignService = Depends(get_service)):
    return _call(s.get, campaign_id)


@router.get("/{campaign_id}/stats", response_model=CampaignStatsDto)
def get_stats(campaign_id: int, s: CampaignService = Depends(get_service)):
    return _call(s.stats, campaign_id)

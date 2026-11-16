from fastapi import APIRouter, Depends
from app.config import get_settings
from app.shared.web3_provider import get_web3_provider
from app.modules.tokenomics.service import TokenomicsService
from app.modules.tokenomics.dto import TierResponse

router = APIRouter(prefix="/tokenomics", tags=["Tokenomics"])


def get_tokenomics_service():
    return TokenomicsService(get_settings(), get_web3_provider())


@router.get("/{address}/tier", response_model=TierResponse)
def get_tier(address: str, service: TokenomicsService = Depends(get_tokenomics_service)):
    return service.get_tier(address)

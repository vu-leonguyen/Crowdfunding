import time

from fastapi import APIRouter, Depends, Header, Query

from app.config import Settings, get_settings
from app.shared.contract_loader import ContractLoader, get_contract
from app.shared.web3_provider import Web3Provider, get_web3_provider

from .dto import ChallengeResponse, RolesResponse
from .service import UPLOAD_POLICY, AccessService, WalletAuth, can_read, can_upload

router = APIRouter(prefix="/auth", tags=["Auth & RBAC"])


def get_wallet_auth(settings: Settings = Depends(get_settings),
                    provider: Web3Provider = Depends(get_web3_provider)) -> WalletAuth:
    return WalletAuth(settings, provider)


def require_wallet(
    x_wallet_address: str | None = Header(default=None),
    x_wallet_signature: str | None = Header(default=None),
    x_wallet_issued_at: str | None = Header(default=None),
    auth: WalletAuth = Depends(get_wallet_auth),
) -> str:
    """Dependency: returns the checksum address proven by the X-Wallet-* signature headers."""
    return auth.verify(x_wallet_address, x_wallet_signature, x_wallet_issued_at)


def get_access_service(platform=Depends(get_contract),
                       settings: Settings = Depends(get_settings),
                       provider: Web3Provider = Depends(get_web3_provider)) -> AccessService:
    return AccessService(platform, ContractLoader(provider, settings.abi_dir))


@router.get("/challenge", response_model=ChallengeResponse)
def challenge(address: str, auth: WalletAuth = Depends(get_wallet_auth)):
    """Message the wallet must sign (personal_sign) and send back in the X-Wallet-* headers."""
    wallet = auth.provider.checksum_address(address)
    issued_at = int(time.time())
    return ChallengeResponse(address=wallet, issued_at=issued_at, message=auth.message(wallet, issued_at))


@router.get("/roles", response_model=RolesResponse)
def roles(campaign_id: int | None = Query(default=None, ge=1),
          wallet: str = Depends(require_wallet),
          access: AccessService = Depends(get_access_service)):
    held = access.roles(wallet, campaign_id)
    kinds = list(UPLOAD_POLICY)
    return RolesResponse(
        address=wallet, campaign_id=campaign_id,
        roles=sorted(r.value for r in held),
        can_upload={k: can_upload(k, held) for k in kinds},
        can_read={k: can_read(k, held) for k in kinds},
    )

from decimal import Decimal, localcontext
from app.config import Settings
from app.core.errors import ServiceError
from app.shared.contract_loader import ContractLoader
from app.shared.web3_provider import Web3Provider
from app.modules.tokenomics.dto import TierResponse


class TokenomicsService:
    def __init__(self, settings: Settings, provider: Web3Provider):
        self.settings, self.provider = settings, provider
        self.loader = ContractLoader(provider, settings.abi_dir)

    def get_tier(self, address: str) -> TierResponse:
        wallet = self.provider.checksum_address(address)
        token = self.loader.load("IGovernanceToken", self.settings.governance_token_address)
        nft = self.loader.load("IDiamondPatronNFT", self.settings.diamond_nft_address)
        try:
            block = self.provider.web3.eth.block_number
            raw = token.functions.balanceOf(wallet).call(block_identifier=block)
            diamonds = nft.functions.balanceOf(wallet).call(block_identifier=block)
        except Exception:
            raise ServiceError(502, "contract_read_failed", "Unable to read token balances.") from None
        with localcontext() as ctx:
            ctx.prec = 100
            balance = Decimal(raw) / (Decimal(10) ** self.settings.token_decimals)
        # NFT membership takes precedence; ERC-20 threshold is configurable.
        access = diamonds > 0 or balance >= self.settings.token_tier_threshold
        tier = "diamond" if diamonds > 0 else ("governance" if access else "basic")
        return TierResponse(address=wallet, chain_id=self.settings.chain_id, block_number=block,
                            governance_balance_raw=str(raw), governance_balance=format(balance, "f"),
                            diamond_nft_balance=str(diamonds), tier=tier, has_exclusive_access=access)

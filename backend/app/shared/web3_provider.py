from functools import lru_cache
from web3 import Web3, HTTPProvider
from app.config import Settings, get_settings
from app.core.errors import ServiceError


class Web3Provider:
    """Read-only RPC access. Wallet signing stays in the user's wallet."""
    def __init__(self, settings: Settings):
        self.settings = settings
        self.web3 = Web3(HTTPProvider(settings.rpc_url, request_kwargs={
            "timeout": settings.rpc_timeout
        }))

    def check_connection(self) -> int:
        try:
            chain_id = self.web3.eth.chain_id
        except Exception:
            raise ServiceError(503, "rpc_unavailable", "Blockchain RPC is unavailable.") from None
        if chain_id != self.settings.chain_id:
            raise ServiceError(503, "chain_mismatch", "RPC chain does not match CHAIN_ID.")
        return chain_id

    def checksum_address(self, address: str) -> str:
        if not Web3.is_address(address):
            raise ServiceError(422, "invalid_address", "Invalid Ethereum wallet address.")
        if Web3.is_checksum_address(address) or address.islower() or address.isupper():
            return Web3.to_checksum_address(address)
        raise ServiceError(422, "invalid_address", "Mixed-case address has an invalid checksum.")


@lru_cache
def get_web3_provider() -> Web3Provider:
    return Web3Provider(get_settings())

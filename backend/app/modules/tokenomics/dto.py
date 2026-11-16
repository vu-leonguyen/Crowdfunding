from pydantic import BaseModel


class TierResponse(BaseModel):
    address: str
    chain_id: int
    block_number: int
    governance_balance_raw: str
    governance_balance: str
    diamond_nft_balance: str
    tier: str
    has_exclusive_access: bool

from pydantic import BaseModel


class SpendingRequestDto(BaseModel):
    id: int
    description: str
    amount_wei: int
    recipient: str
    proof_cid: str
    approval_weight_wei: int
    reject_weight_wei: int
    approval_percent: float
    reject_percent: float
    passes_threshold: bool  # approval > 50% tổng vốn, như finalizeSpending
    completed: bool
    rejected: bool

from enum import IntEnum

from pydantic import BaseModel


class VoteType(IntEnum):
    Approve = 1
    Reject = 2


class VoteDto(BaseModel):
    voter: str
    vote: VoteType

"""Test-only wallets and signature headers for the X-Wallet-* authentication scheme."""
import time

from eth_account import Account
from eth_account.messages import encode_defunct

from app.modules.auth.service import MESSAGE_TEMPLATE

# Deterministic throwaway keys generated for tests only; they never hold real funds.
CREATOR = Account.from_key("0x" + "11" * 32)
BACKER = Account.from_key("0x" + "22" * 32)
OUTSIDER = Account.from_key("0x" + "33" * 32)
DIAMOND = Account.from_key("0x" + "44" * 32)


def signed_headers(account, chain_id: int = 31337, issued_at: int | None = None) -> dict[str, str]:
    ts = int(time.time()) if issued_at is None else issued_at
    message = MESSAGE_TEMPLATE.format(address=account.address, chain_id=chain_id, issued_at=ts)
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    return {"X-Wallet-Address": account.address,
            "X-Wallet-Signature": "0x" + signature.removeprefix("0x"),
            "X-Wallet-Issued-At": str(ts)}

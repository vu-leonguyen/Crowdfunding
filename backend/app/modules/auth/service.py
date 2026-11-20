"""Wallet-signature authentication and on-chain role resolution (RBAC).

Authentication: the client signs a short, time-stamped message with its wallet
(EIP-191 personal_sign). The backend recovers the signer and accepts the request
only if it matches the claimed address and the signature is fresh. No private
keys, sessions or passwords are stored on the server.

Authorization: roles are read live from the deployed contracts, so the smart
contract is the single source of truth for who may access what.
"""
import time
from enum import Enum

from eth_account import Account
from eth_account.messages import encode_defunct

from app.config import Settings
from app.core.errors import ServiceError
from app.shared.contract_loader import ContractLoader
from app.shared.web3_provider import Web3Provider

MESSAGE_TEMPLATE = (
    "CrowdOps access request\n"
    "Address: {address}\n"
    "Chain ID: {chain_id}\n"
    "Issued At: {issued_at}"
)
CLOCK_SKEW_SECONDS = 60


class Role(str, Enum):
    PUBLIC = "public"        # any signed-in wallet
    BACKER = "backer"        # contributed (and not refunded) to the campaign
    CREATOR = "creator"      # created the campaign
    DIAMOND = "diamond"      # holds a Diamond Patron NFT


# Resource kinds stored on IPFS and who may upload / read them.
# A read rule is a list of alternatives; each alternative is a set of roles that
# must ALL be held. Public kinds are stored unencrypted and readable by anyone
# through any IPFS gateway, because their CID is stored on-chain for transparency.
PUBLIC_KINDS = {"proposal", "media", "metadata"}
PROTECTED_KINDS = {"proof", "exclusive"}
UPLOAD_POLICY: dict[str, set[Role]] = {
    "proposal": {Role.PUBLIC},
    "media": {Role.PUBLIC},
    "metadata": {Role.PUBLIC},
    "proof": {Role.CREATOR},
    "exclusive": {Role.CREATOR},
}
READ_POLICY: dict[str, list[set[Role]]] = {
    "proof": [{Role.CREATOR}, {Role.BACKER}],
    "exclusive": [{Role.CREATOR}, {Role.BACKER, Role.DIAMOND}],
}


def can_upload(kind: str, roles: set[Role]) -> bool:
    return UPLOAD_POLICY[kind] <= roles


def can_read(kind: str, roles: set[Role]) -> bool:
    if kind in PUBLIC_KINDS:
        return True
    return any(rule <= roles for rule in READ_POLICY[kind])


class WalletAuth:
    def __init__(self, settings: Settings, provider: Web3Provider):
        self.settings, self.provider = settings, provider

    def message(self, address: str, issued_at: int) -> str:
        return MESSAGE_TEMPLATE.format(address=address, chain_id=self.settings.chain_id,
                                       issued_at=issued_at)

    def verify(self, address: str | None, signature: str | None, issued_at: str | None,
               now: int | None = None) -> str:
        if not address or not signature or not issued_at:
            raise ServiceError(401, "auth_required", "Wallet signature headers are required.")
        wallet = self.provider.checksum_address(address)
        try:
            ts = int(issued_at)
        except ValueError:
            raise ServiceError(401, "invalid_signature", "Invalid signature timestamp.") from None
        now = int(time.time()) if now is None else now
        if ts > now + CLOCK_SKEW_SECONDS or now - ts > self.settings.auth_max_age_seconds:
            raise ServiceError(401, "signature_expired", "Signature expired; please sign again.")
        try:
            signer = Account.recover_message(encode_defunct(text=self.message(wallet, ts)),
                                             signature=signature)
        except Exception:
            raise ServiceError(401, "invalid_signature", "Signature could not be verified.") from None
        if signer != wallet:
            raise ServiceError(401, "invalid_signature", "Signature does not match the wallet address.")
        return wallet


class AccessService:
    """Resolves a wallet's roles for one campaign from on-chain state."""

    def __init__(self, platform, loader: ContractLoader):
        self.platform, self.loader = platform, loader

    def roles(self, wallet: str, campaign_id: int | None) -> set[Role]:
        roles = {Role.PUBLIC}
        f = self.platform.functions
        try:
            diamond_address = f.diamondNFT().call()
            if int(diamond_address, 16):
                nft = self.loader.load("IDiamondPatronNFT", diamond_address)
                if nft.functions.balanceOf(wallet).call() > 0:
                    roles.add(Role.DIAMOND)
            if campaign_id is not None:
                if not 1 <= campaign_id <= f.campaignCounter().call():
                    raise ServiceError(404, "campaign_not_found", "Campaign not found.")
                if f.getCampaign(campaign_id).call()[1] == wallet:
                    roles.add(Role.CREATOR)
                if f.getContribution(campaign_id, wallet).call() > 0:
                    roles.add(Role.BACKER)
        except ServiceError:
            raise
        except Exception:
            raise ServiceError(502, "contract_read_failed", "Unable to read roles from the contract.") from None
        return roles

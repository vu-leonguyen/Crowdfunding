import json
from pathlib import Path
from app.core.errors import ServiceError
from app.shared.web3_provider import Web3Provider


class ContractLoader:
    def __init__(self, provider: Web3Provider, abi_dir: Path):
        self.provider, self.abi_dir = provider, abi_dir

    def load(self, name: str, address: str):
        if not address:
            raise ServiceError(503, "contract_not_configured", f"{name} address is not configured.")
        if not name.isidentifier():
            raise ServiceError(503, "invalid_abi", "Invalid ABI name.")
        try:
            data = json.loads((self.abi_dir / f"{name}.json").read_text())
            abi = data["abi"] if isinstance(data, dict) else data
            if not isinstance(abi, list):
                raise ValueError("ABI must be an array")
        except (OSError, ValueError, KeyError):
            raise ServiceError(503, "invalid_abi", f"{name} ABI is missing or invalid.") from None
        checksum = self.provider.checksum_address(address)
        self.provider.check_connection()
        try:
            if not self.provider.web3.eth.get_code(checksum):
                raise ServiceError(503, "contract_not_deployed", f"{name} has no bytecode at the configured address.")
            return self.provider.web3.eth.contract(address=checksum, abi=abi)
        except ServiceError:
            raise
        except Exception:
            raise ServiceError(502, "contract_unavailable", "Unable to load deployed contract.") from None

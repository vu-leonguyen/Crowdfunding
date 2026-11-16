from functools import lru_cache
from pathlib import Path
from decimal import Decimal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")
    rpc_url: str = "http://127.0.0.1:8545"
    chain_id: int = 31337
    rpc_timeout: float = Field(default=10, gt=0)
    cors_origins: list[str] = ["http://localhost:3000"]
    pinata_jwt: SecretStr = SecretStr("")
    ipfs_gateway_url: str = "https://gateway.pinata.cloud/ipfs"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    governance_token_address: str = ""
    diamond_nft_address: str = ""
    token_decimals: int = Field(default=18, ge=0, le=255)
    token_tier_threshold: Decimal = Field(default=Decimal("1000"), ge=0)
    abi_dir: Path = BACKEND_DIR / "abis"


@lru_cache
def get_settings() -> Settings:
    return Settings()


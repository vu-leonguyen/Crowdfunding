from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from app.config import get_settings
from app.core.errors import ErrorResponse, ServiceError, service_error_handler, validation_error_handler
from app.shared.web3_provider import Web3Provider, get_web3_provider
from app.modules.ipfs.controller import router as ipfs_router
from app.modules.tokenomics.controller import router as tokenomics_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=60) as client:
        app.state.http_client = client
        yield


def create_app() -> FastAPI:
    app = FastAPI(title="CrowdOps Backend", version="0.1.0", lifespan=lifespan,
                  responses={status: {"model": ErrorResponse} for status in (413, 415, 422, 502, 503)})
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                       allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    app.add_exception_handler(ServiceError, service_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(ipfs_router)
    app.include_router(tokenomics_router)

    @app.get("/health", tags=["Health"])
    def health():
        return {"status": "ok"}

    @app.get("/health/rpc", tags=["Health"])
    def rpc_health(provider: Web3Provider = Depends(get_web3_provider)):
        return {"status": "ok", "chain_id": provider.check_connection()}

    return app


app = create_app()

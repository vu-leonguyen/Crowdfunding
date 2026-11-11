from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorDetails(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetails


class ServiceError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code, self.code, self.message = status_code, code, message


async def service_error_handler(request: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status_code, content={
        "error": {"code": exc.code, "message": exc.message}
    })


async def validation_error_handler(request: Request, exc):
    # Do not echo submitted input (which may contain secrets) in error responses.
    return JSONResponse(status_code=422, content={
        "error": {"code": "validation_error", "message": "Invalid request parameters."}
    })

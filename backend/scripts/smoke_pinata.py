"""Explicit live upload: python -m scripts.smoke_pinata proposal.pdf.

Requires a user-supplied PINATA_JWT; uploads a real public file and consumes quota.
Never run automatically in unit tests or CI.
"""
import argparse
import asyncio
import json
from pathlib import Path
import httpx
from fastapi import UploadFile
from app.config import get_settings
from app.core.errors import ServiceError
from app.modules.ipfs.service import IPFSService


async def upload(path: Path, kind: str):
    settings = get_settings()
    if not settings.pinata_jwt.get_secret_value():
        raise ServiceError(503, 'pinata_not_configured', 'Configure PINATA_JWT in backend/.env first.')
    async with httpx.AsyncClient(timeout=60) as client:
        with path.open('rb') as stream:
            return await IPFSService(settings, client).upload(UploadFile(filename=path.name, file=stream), kind)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--kind', choices=['proposal', 'proof'], default='proposal')
    args = parser.parse_args()
    try:
        result = asyncio.run(upload(args.file, args.kind))
    except ServiceError as exc:
        parser.exit(1, f'{exc.code}: {exc.message}\n')
    except OSError:
        parser.exit(1, 'Unable to read the supplied file.\n')
    print(json.dumps(result.model_dump()))


if __name__ == '__main__':
    main()

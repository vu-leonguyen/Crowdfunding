import asyncio
from pathlib import Path
import pytest
from app.core.errors import ServiceError
from scripts.smoke_pinata import upload


def test_live_upload_requires_credentials_before_opening_file():
    with pytest.raises(ServiceError) as error:
        asyncio.run(upload(Path('nonexistent.pdf'), 'proposal'))
    assert error.value.code == 'pinata_not_configured'

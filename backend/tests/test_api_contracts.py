"""API-level contracts for every TV3 module, including failure paths."""
from unittest.mock import MagicMock
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.config import Settings, get_settings
from app.core.errors import ServiceError
from app.main import create_app
from app.modules.tokenomics.service import TokenomicsService
from app.shared.contract_loader import ContractLoader
from app.shared.web3_provider import Web3Provider, get_web3_provider


def test_settings_from_environment(monkeypatch):
    monkeypatch.setenv('CHAIN_ID', '11155111')
    monkeypatch.setenv('CORS_ORIGINS', '["https://example.com"]')
    monkeypatch.setenv('PINATA_JWT', 'test-only-secret')
    settings = Settings()
    assert settings.chain_id == 11155111
    assert settings.cors_origins == ['https://example.com']
    assert 'test-only-secret' not in repr(settings)


@pytest.mark.parametrize('values', [{'max_upload_bytes': 0}, {'rpc_timeout': -1},
                                    {'token_decimals': 256}, {'token_tier_threshold': -1}])
def test_invalid_settings(values):
    with pytest.raises(ValidationError):
        Settings(**values)


@pytest.mark.parametrize('route,payload', [('/ipfs/proposal', b'%PDF-1.4 content'),
                                         ('/ipfs/proof', b'\x89PNG\r\n\x1a\ncontent')])
def test_upload_api_complete_pipeline(route, payload):
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: Settings(pinata_jwt='test-only')
    cid = 'Qm' + 'a' * 44
    def upstream(request):
        assert str(request.url) == 'https://api.pinata.cloud/pinning/pinFileToIPFS'
        assert request.headers['Authorization'] == 'Bearer test-only'
        assert payload in request.content
        return httpx.Response(200, json={'IpfsHash': cid})
    with TestClient(application) as client:
        with client.portal.wrap_async_context_manager(httpx.AsyncClient(transport=httpx.MockTransport(upstream))) as http:
            application.state.http_client = http
            response = client.post(route, files={'file': ('../../untrusted', payload)})
    assert response.status_code == 200
    assert response.json() == {'cid': cid, 'ipfs_uri': f'ipfs://{cid}',
                              'gateway_url': f'https://gateway.pinata.cloud/ipfs/{cid}', 'size': len(payload)}
    assert 'test-only' not in response.text


def test_missing_file_and_disallowed_cors():
    with TestClient(create_app()) as client:
        response = client.post('/ipfs/proposal')
        assert response.status_code == 422
        assert response.json()['error']['code'] == 'validation_error'
        response = client.options('/ipfs/proposal', headers={
            'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'POST'})
        assert response.status_code == 400
        assert 'access-control-allow-origin' not in response.headers


@pytest.mark.parametrize('payload', [{}, {'IpfsHash': '../invalid'}, {'IpfsHash': None}, []])
def test_malformed_pinata_response(payload):
    import asyncio
    from io import BytesIO
    from fastapi import UploadFile
    from app.modules.ipfs.service import IPFSService
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=payload))) as http:
            with pytest.raises(ServiceError) as error:
                await IPFSService(Settings(pinata_jwt='test-only'), http).upload(
                    UploadFile(file=BytesIO(b'%PDF-1.4')), 'proposal')
            assert error.value.code == 'pinata_failed'
    asyncio.run(run())


@pytest.mark.parametrize('content', ['not json', '{}', '{"abi": 42}'])
def test_invalid_abi_files(tmp_path, content):
    (tmp_path / 'Token.json').write_text(content)
    with pytest.raises(ServiceError) as error:
        ContractLoader(Web3Provider(Settings()), tmp_path).load('Token', '0x'+'1'*40)
    assert error.value.code == 'invalid_abi'


def test_rpc_error_at_api_boundary():
    application = create_app()
    provider = Web3Provider(Settings())
    provider.check_connection = MagicMock(side_effect=ServiceError(503, 'rpc_unavailable', 'RPC unavailable.'))
    application.dependency_overrides[get_web3_provider] = lambda: provider
    with TestClient(application) as client:
        assert client.get('/health').status_code == 200
        response = client.get('/health/rpc')
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'rpc_unavailable'


def test_contract_read_failure():
    provider = Web3Provider(Settings())
    provider.web3 = MagicMock()
    token = MagicMock()
    token.functions.balanceOf.return_value.call.side_effect = RuntimeError('sensitive upstream details')
    service = TokenomicsService(Settings(), provider)
    service.loader.load = MagicMock(return_value=token)
    with pytest.raises(ServiceError) as error:
        service.get_tier('0x'+'1'*40)
    assert error.value.code == 'contract_read_failed'
    assert 'sensitive' not in error.value.message


def test_swagger_documents_actual_error_envelope():
    with TestClient(create_app()) as client:
        schema = client.get('/openapi.json').json()
        response = schema['paths']['/ipfs/proposal']['post']['responses']['422']
        assert response['content']['application/json']['schema']['$ref'].endswith('/ErrorResponse')

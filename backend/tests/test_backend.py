from io import BytesIO
from unittest.mock import MagicMock
import httpx
import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from app.config import Settings
from app.core.errors import ServiceError
from app.main import app
from app.modules.ipfs.service import IPFSService
from app.modules.tokenomics.service import TokenomicsService
from app.shared.contract_loader import ContractLoader
from app.shared.web3_provider import Web3Provider


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_health_docs_and_cors(client):
    assert client.get('/health').json() == {'status': 'ok'}
    assert client.get('/docs').status_code == 200
    assert '/ipfs/proof' in client.get('/openapi.json').json()['paths']
    response = client.options('/ipfs/proposal', headers={
        'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'POST'})
    assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'


def test_upload_validation_and_missing_credentials(client):
    assert client.post('/ipfs/proposal', files={'file': ('x.pdf', b'fake', 'application/pdf')}).status_code == 415
    assert client.post('/ipfs/proof', files={'file': ('x', b'')}).status_code == 422
    response = client.post('/ipfs/proposal', files={'file': ('x.pdf', b'%PDF-1.4 test')})
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'pinata_not_configured'


@pytest.mark.parametrize('status', [200, 401, 429, 500])
def test_pinata_contract(status):
    import asyncio
    cid = 'Qm' + 'a' * 44
    def handler(request):
        assert request.headers['authorization'] == 'Bearer test-only'
        assert b'%PDF-1.4 test' in request.content
        return httpx.Response(status, json={'IpfsHash': cid})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            service = IPFSService(Settings(pinata_jwt='test-only'), http)
            file = UploadFile(filename='x.pdf', file=BytesIO(b'%PDF-1.4 test'))
            if status == 200:
                result = await service.upload(file, 'proposal')
                assert result.cid == cid
                assert result.ipfs_uri == f'ipfs://{cid}'
            else:
                with pytest.raises(ServiceError) as error:
                    await service.upload(file, 'proposal')
                assert error.value.status_code == 502
                assert 'test-only' not in error.value.message
    asyncio.run(run())


def test_upload_size_limit():
    import asyncio
    async def run():
        async with httpx.AsyncClient() as http:
            service = IPFSService(Settings(max_upload_bytes=5), http)
            with pytest.raises(ServiceError) as error:
                await service.upload(UploadFile(file=BytesIO(b'%PDF-123')), 'proposal')
            assert error.value.status_code == 413
    asyncio.run(run())


def test_rpc_chain_and_unavailable():
    provider = Web3Provider(Settings())
    provider.web3 = MagicMock()
    provider.web3.eth.chain_id = 1
    with pytest.raises(ServiceError, match='CHAIN_ID'):
        provider.check_connection()
    provider.web3.eth.chain_id = 31337
    assert provider.check_connection() == 31337


def test_loader_supports_raw_abi_and_artifact(tmp_path):
    import json
    provider = Web3Provider(Settings())
    provider.web3 = MagicMock()
    provider.web3.eth.chain_id = 31337
    provider.web3.eth.get_code.return_value = b'code'
    loader = ContractLoader(provider, tmp_path)
    for data in [[], {'abi': []}]:
        (tmp_path / 'Token.json').write_text(json.dumps(data))
        loader.load('Token', '0x' + '1' * 40)
    with pytest.raises(ServiceError):
        loader.load('../Token', '0x' + '1' * 40)
    provider.web3.eth.get_code.return_value = b''
    with pytest.raises(ServiceError, match='bytecode'):
        loader.load('Token', '0x' + '1' * 40)


@pytest.mark.parametrize('raw,nfts,tier', [(0,0,'basic'), (999*10**18,0,'basic'),
    (1000*10**18,0,'governance'), (0,1,'diamond'), (2**256-1,0,'governance')])
def test_tier_precision_and_same_block(raw, nfts, tier):
    provider = Web3Provider(Settings())
    provider.web3 = MagicMock()
    provider.web3.eth.block_number = 123
    service = TokenomicsService(Settings(), provider)
    token, nft = MagicMock(), MagicMock()
    token.functions.balanceOf.return_value.call.return_value = raw
    nft.functions.balanceOf.return_value.call.return_value = nfts
    service.loader.load = MagicMock(side_effect=[token,nft])
    result = service.get_tier('0x' + '1' * 40)
    assert result.tier == tier
    assert result.governance_balance_raw == str(raw)
    assert result.has_exclusive_access == (tier != 'basic')
    token.functions.balanceOf.return_value.call.assert_called_once_with(block_identifier=123)
    nft.functions.balanceOf.return_value.call.assert_called_once_with(block_identifier=123)


def test_invalid_address(client):
    assert client.get('/tokenomics/not-a-wallet/tier').status_code == 422


def test_unconfigured_token_contract(client):
    response = client.get('/tokenomics/0x1111111111111111111111111111111111111111/tier')
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'contract_not_configured'


def test_rpc_outage_is_sanitized():
    from unittest.mock import PropertyMock
    provider = Web3Provider(Settings())
    provider.web3 = MagicMock()
    type(provider.web3.eth).chain_id = PropertyMock(side_effect=RuntimeError('secret RPC URL'))
    with pytest.raises(ServiceError) as error:
        provider.check_connection()
    assert error.value.status_code == 503
    assert 'secret' not in error.value.message


@pytest.mark.parametrize('data,mime', [(b'\x89PNG\r\n\x1a\npayload', 'image/png'),
                                     (b'\xff\xd8\xffpayload', 'image/jpeg')])
def test_proof_image_upload(data, mime):
    import asyncio
    def handler(request):
        assert mime.encode() in request.content
        return httpx.Response(200, json={'IpfsHash': 'Qm' + 'b' * 44})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            service = IPFSService(Settings(pinata_jwt='test-only'), http)
            result = await service.upload(UploadFile(file=BytesIO(data)), 'proof')
            assert result.size == len(data)
    asyncio.run(run())


def test_pinata_timeout():
    import asyncio
    def handler(request):
        raise httpx.ReadTimeout('secret upstream detail')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            service = IPFSService(Settings(pinata_jwt='test-only'), http)
            with pytest.raises(ServiceError) as error:
                await service.upload(UploadFile(file=BytesIO(b'%PDF-1.4')), 'proposal')
            assert error.value.code == 'pinata_failed'
            assert 'secret' not in error.value.message
    asyncio.run(run())

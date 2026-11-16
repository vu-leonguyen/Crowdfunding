"""Real local JSON-RPC + OpenZeppelin token contracts; no RPC/Web3 mocks."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.modules.tokenomics.controller import get_tokenomics_service
from app.modules.tokenomics.service import TokenomicsService
from app.shared.web3_provider import Web3Provider, get_web3_provider
from app.shared.contract_loader import ContractLoader

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def local_chain(tmp_path_factory):
    temp = tmp_path_factory.mktemp('rpc')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    settings = Settings(_env_file=None, rpc_url=f'http://127.0.0.1:{port}',
                        chain_id=31337, abi_dir=ROOT / 'backend/abis',
                        token_decimals=18, token_tier_threshold=1000)
    provider = Web3Provider(settings)
    environment = os.environ.copy()
    for variable in ['XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME']:
        environment[variable] = str(temp / variable)
    with (temp / 'hardhat.log').open('w') as log:
        process = subprocess.Popen(
            ['node', 'node_modules/hardhat/internal/cli/cli.js', 'node',
             '--hostname', '127.0.0.1', '--port', str(port)],
            cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 25
            while True:
                try:
                    provider.check_connection()
                    break
                except Exception:
                    if process.poll() is not None or time.monotonic() > deadline:
                        pytest.fail('Local Hardhat failed to start; inspect the private test log.')
                    time.sleep(0.1)
            yield settings, provider
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


@pytest.fixture(scope='module')
def deployed_tokens(local_chain):
    settings, provider = local_chain
    # Compile fixtures independently so they never enter production artifacts.
    script = r'''
const fs = require('fs');
const solc = require('solc');
const source = fs.readFileSync('backend/tests/fixtures/TierTokens.sol', 'utf8');
const input = {language: 'Solidity', sources: {'TierTokens.sol': {content: source}},
 settings: {evmVersion: 'cancun', outputSelection: {'*': {'*': ['abi', 'evm.bytecode.object']}}}};
const result = JSON.parse(solc.compile(JSON.stringify(input), {import: p => {
 try {return {contents: fs.readFileSync('node_modules/' + p, 'utf8')}}
 catch {return {error: 'Import not found: ' + p}}
}}));
if ((result.errors || []).some(e => e.severity === 'error')) {
 throw new Error(JSON.stringify(result.errors));
}
process.stdout.write(JSON.stringify(result.contracts['TierTokens.sol']));
'''
    compiled = json.loads(subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True))
    w3 = provider.web3
    addresses = []
    for name, member in [('TierGovernanceFixture', w3.eth.accounts[1]),
                         ('TierDiamondFixture', w3.eth.accounts[2])]:
        artifact = compiled[name]
        factory = w3.eth.contract(abi=artifact['abi'], bytecode=artifact['evm']['bytecode']['object'])
        receipt = w3.eth.wait_for_transaction_receipt(
            factory.constructor(member).transact({'from': w3.eth.accounts[0]}))
        assert receipt.status == 1
        addresses.append(receipt.contractAddress)
    config = settings.model_copy(update={
        'governance_token_address': addresses[0], 'diamond_nft_address': addresses[1]})
    return config, provider


@pytest.mark.parametrize('index,tier,raw,nfts', [
    (0, 'basic', '0', '0'),
    (1, 'governance', str(1000 * 10**18), '0'),
    (2, 'diamond', '0', '1'),
])
def test_tier_api_against_deployed_tokens(deployed_tokens, index, tier, raw, nfts):
    settings, provider = deployed_tokens
    application = create_app()
    application.dependency_overrides[get_tokenomics_service] = lambda: TokenomicsService(settings, provider)
    with TestClient(application) as client:
        response = client.get(f'/tokenomics/{provider.web3.eth.accounts[index]}/tier')
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['tier'] == tier
        assert result['governance_balance_raw'] == raw
        assert result['diamond_nft_balance'] == nfts
        assert result['has_exclusive_access'] == (tier != 'basic')
        assert result['chain_id'] == 31337
        assert result['block_number'] > 0


def test_rpc_health_real_node(local_chain):
    _, provider = local_chain
    application = create_app()
    application.dependency_overrides[get_web3_provider] = lambda: provider
    with TestClient(application) as client:
        assert client.get('/health/rpc').json() == {'status': 'ok', 'chain_id': 31337}


def test_loader_rejects_real_account_without_code(local_chain):
    settings, provider = local_chain
    from app.core.errors import ServiceError
    with pytest.raises(ServiceError) as error:
        ContractLoader(provider, settings.abi_dir).load('IGovernanceToken', provider.web3.eth.accounts[0])
    assert error.value.code == 'contract_not_deployed'

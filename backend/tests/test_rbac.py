"""Wallet-signature auth, on-chain RBAC and encrypted IPFS storage (TC3 access control)."""
import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.core.errors import ServiceError
from app.main import create_app
from app.modules.auth.controller import get_access_service
from app.modules.auth.service import AccessService, Role, WalletAuth, can_read, can_upload
from app.shared import file_crypto
from app.shared.contract_loader import get_contract
from app.shared.web3_provider import Web3Provider
from tests.wallets import BACKER, CREATOR, DIAMOND, OUTSIDER, signed_headers

KEY_B64 = base64.b64encode(b"k" * 32).decode()
PLATFORM = "0x" + "5" * 40
NFT = "0x" + "6" * 40
GATEWAY = "https://gateway.test/ipfs"
ETH = 10**18
INVOICE = b"%PDF-1.4 invoice: 2 x solar panel, total 0.5 ETH"


class Call:
    def __init__(self, value):
        self.value = value

    def call(self, *args, **kwargs):
        return self.value


def fake_platform(contributions=None, campaigns=1):
    contributions = contributions or {}
    campaign = (1, CREATOR.address, "Solar", "d", "cid", 5 * ETH, 10**10, 5 * ETH, 5 * ETH, 3, 1)
    return SimpleNamespace(functions=SimpleNamespace(
        diamondNFT=lambda: Call(NFT),
        campaignCounter=lambda: Call(campaigns),
        getCampaign=lambda i: Call(campaign),
        getContribution=lambda i, who: Call(contributions.get(who, 0)),
        getSpendingRequest=lambda c, r: Call((1, "hw", ETH, "0xV", "cid", 0, 0, False, False)),
    ))


def fake_loader(diamond_holders):
    nft = SimpleNamespace(functions=SimpleNamespace(
        balanceOf=lambda who: Call(1 if who in diamond_holders else 0)))
    return SimpleNamespace(load=lambda name, address: nft)


def access_service():
    platform = fake_platform({BACKER.address: ETH, DIAMOND.address: ETH})
    return AccessService(platform, fake_loader({DIAMOND.address, OUTSIDER.address}))


def settings(**overrides):
    values = dict(pinata_jwt="test-only", file_encryption_key=KEY_B64, platform_address=PLATFORM,
                  ipfs_gateway_url=GATEWAY)
    values.update(overrides)
    return Settings(**values)


class FakeIPFS:
    """In-memory Pinata + gateway: records pinned bytes, serves them by CID."""

    def __init__(self):
        self.files: dict[str, bytes] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/pinning/pinFileToIPFS"):
            body = request.content
            start = body.find(file_crypto.MAGIC)
            data = body[start:body.rfind(b"\r\n--")] if start >= 0 else body
            cid = "Qm" + "c" * 42 + "abcdefghijkmnopqrstuvwxyz"[len(self.files)] + "z"
            self.files[cid] = data
            return httpx.Response(200, json={"IpfsHash": cid})
        if url.endswith("/pinning/pinJSONToIPFS"):
            content = json.loads(request.content)["pinataContent"]
            cid = "Qm" + "d" * 43 + "abcdefghijkmnopqrstuvwxyz"[len(self.files)]
            self.files[cid] = json.dumps(content).encode()
            return httpx.Response(200, json={"IpfsHash": cid})
        if url.startswith(GATEWAY):
            cid = url.rsplit("/", 1)[1]
            return httpx.Response(200, content=self.files[cid]) if cid in self.files else httpx.Response(404)
        return httpx.Response(500)


@pytest.fixture
def api():
    ipfs = FakeIPFS()
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: settings()
    application.dependency_overrides[get_access_service] = access_service
    with TestClient(application) as client:
        with client.portal.wrap_async_context_manager(
                httpx.AsyncClient(transport=httpx.MockTransport(ipfs.handler))) as http:
            application.state.http_client = http
            yield client, ipfs


def upload(client, route, account, payload=INVOICE, campaign_id=1):
    return client.post(route, files={"file": ("x", payload)}, data={"campaign_id": str(campaign_id)},
                       headers=signed_headers(account))


# ---------------------------------------------------------------- authentication

def test_signature_auth_accepts_owner_and_rejects_forgery_and_replay():
    auth = WalletAuth(Settings(), Web3Provider(Settings()))
    good = signed_headers(BACKER, issued_at=1_000)
    assert auth.verify(good["X-Wallet-Address"], good["X-Wallet-Signature"], "1000", now=1_010) == BACKER.address

    forged = signed_headers(OUTSIDER, issued_at=1_000)  # signed by someone else
    expired_now = 1_000 + Settings().auth_max_age_seconds + 1
    cases = [
        ((BACKER.address, forged["X-Wallet-Signature"], "1000", 1_010), "invalid_signature"),
        ((BACKER.address, good["X-Wallet-Signature"], "1001", 1_010), "invalid_signature"),
        ((BACKER.address, good["X-Wallet-Signature"], "1000", expired_now), "signature_expired"),
        ((BACKER.address, good["X-Wallet-Signature"], "1000", 500), "signature_expired"),
        ((BACKER.address, "0xdeadbeef", "1000", 1_010), "invalid_signature"),
        ((None, None, None, 1_010), "auth_required"),
    ]
    for (address, signature, issued_at, now), code in cases:
        with pytest.raises(ServiceError) as error:
            auth.verify(address, signature, issued_at, now=now)
        assert (error.value.status_code, error.value.code) == (401, code)


def test_signature_is_bound_to_chain_id():
    sepolia = Settings(chain_id=11155111)
    headers = signed_headers(BACKER, chain_id=31337)
    with pytest.raises(ServiceError) as error:
        WalletAuth(sepolia, Web3Provider(sepolia)).verify(
            headers["X-Wallet-Address"], headers["X-Wallet-Signature"], headers["X-Wallet-Issued-At"])
    assert error.value.code == "invalid_signature"


# ---------------------------------------------------------------- policy

def test_roles_come_from_chain_state():
    service = access_service()
    assert service.roles(CREATOR.address, 1) == {Role.PUBLIC, Role.CREATOR}
    assert service.roles(BACKER.address, 1) == {Role.PUBLIC, Role.BACKER}
    assert service.roles(DIAMOND.address, 1) == {Role.PUBLIC, Role.BACKER, Role.DIAMOND}
    assert service.roles(OUTSIDER.address, 1) == {Role.PUBLIC, Role.DIAMOND}
    with pytest.raises(ServiceError) as error:
        service.roles(BACKER.address, 2)
    assert error.value.status_code == 404


def test_policy_matrix():
    creator, backer = {Role.PUBLIC, Role.CREATOR}, {Role.PUBLIC, Role.BACKER}
    diamond_backer, diamond_only = backer | {Role.DIAMOND}, {Role.PUBLIC, Role.DIAMOND}
    assert can_upload("proof", creator) and not can_upload("proof", diamond_backer)
    assert can_upload("proposal", {Role.PUBLIC})
    assert can_read("proof", backer) and can_read("proof", creator) and not can_read("proof", diamond_only)
    assert can_read("exclusive", diamond_backer) and can_read("exclusive", creator)
    assert not can_read("exclusive", backer) and not can_read("exclusive", diamond_only)
    assert can_read("proposal", {Role.PUBLIC})


# ---------------------------------------------------------------- encryption

def test_envelope_roundtrip_and_tamper_detection():
    key = b"k" * 32
    sealed = file_crypto.encrypt(key, {"kind": "proof", "campaign_id": 1}, INVOICE)
    assert INVOICE not in sealed
    assert file_crypto.decrypt(key, sealed) == ({"kind": "proof", "campaign_id": 1}, INVOICE)

    # Relabel the file as public "proposal" to dodge the policy: GCM must reject it.
    tampered = sealed.replace(b'"proof"', b'"media"')
    with pytest.raises(ServiceError, match="integrity"):
        file_crypto.decrypt(key, tampered)
    with pytest.raises(ServiceError, match="integrity"):
        file_crypto.decrypt(b"x" * 32, sealed)


@pytest.mark.parametrize("value", ["", "not-base64!", base64.b64encode(b"short").decode()])
def test_bad_encryption_key(value):
    with pytest.raises(ServiceError) as error:
        file_crypto.load_key(value)
    assert error.value.code == "encryption_not_configured"


# ---------------------------------------------------------------- API end to end

def test_proof_upload_is_creator_only_and_stored_encrypted(api):
    client, ipfs = api
    for account in (BACKER, OUTSIDER):
        response = upload(client, "/ipfs/proof", account)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
    assert upload(client, "/ipfs/proof", CREATOR, campaign_id=9).status_code == 404

    response = upload(client, "/ipfs/proof", CREATOR)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["kind"], body["encrypted"], body["mime_type"]) == ("proof", True, "application/pdf")
    stored = ipfs.files[body["cid"]]
    assert file_crypto.is_envelope(stored) and INVOICE not in stored


def test_proof_download_requires_backer_or_creator(api):
    client, _ = api
    cid = upload(client, "/ipfs/proof", CREATOR).json()["cid"]
    for account in (BACKER, CREATOR):
        response = client.get(f"/ipfs/files/{cid}", headers=signed_headers(account))
        assert response.status_code == 200, response.text
        assert response.content == INVOICE
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["cache-control"] == "private, no-store"
    response = client.get(f"/ipfs/files/{cid}", headers=signed_headers(OUTSIDER))
    assert response.status_code == 403
    assert client.get(f"/ipfs/files/{cid}").status_code == 401


def test_exclusive_content_requires_diamond_backer(api):
    client, _ = api
    video = b"\x00\x00\x00\x18ftypmp42 exclusive behind-the-scenes"
    cid = upload(client, "/ipfs/exclusive", CREATOR, payload=video).json()["cid"]
    expected = {DIAMOND: 200, CREATOR: 200, BACKER: 403, OUTSIDER: 403}
    for account, status in expected.items():
        response = client.get(f"/ipfs/files/{cid}", headers=signed_headers(account))
        assert response.status_code == status, (account.address, response.text)
    response = client.get(f"/ipfs/files/{cid}", headers=signed_headers(DIAMOND))
    assert (response.content, response.headers["content-type"]) == (video, "video/mp4")


def test_public_and_foreign_files_are_not_served_by_protected_endpoint(api):
    client, ipfs = api
    public_cid = client.post("/ipfs/proposal", files={"file": ("p.pdf", b"%PDF-1.4 plan")},
                             headers=signed_headers(CREATOR)).json()["cid"]
    response = client.get(f"/ipfs/files/{public_cid}", headers=signed_headers(BACKER))
    assert (response.status_code, response.json()["error"]["code"]) == (409, "not_protected")

    foreign = file_crypto.encrypt(b"k" * 32, {"kind": "proof", "campaign_id": 1, "mime": "application/pdf",
                                              "name": "x.pdf", "chain_id": 31337,
                                              "platform": "0x" + "9" * 40}, INVOICE)
    ipfs.files["Qm" + "b" * 44] = foreign
    response = client.get(f"/ipfs/files/Qm{'b' * 44}", headers=signed_headers(BACKER))
    assert (response.status_code, response.json()["error"]["code"]) == (409, "foreign_file")
    assert client.get("/ipfs/files/..%2Fsecret", headers=signed_headers(BACKER)).status_code in (404, 422)


@pytest.mark.parametrize("payload,status", [
    (b"\x00\x00\x00\x18ftypisom video", 200),
    (b"\x1a\x45\xdf\xa3 webm", 200),
    (b"GIF89a gif", 200),
    (b"RIFF\x00\x00\x00\x00WEBPVP8 ", 200),
    (b"MZ\x90\x00 windows exe", 415),
])
def test_media_types(api, payload, status):
    client, _ = api
    response = client.post("/ipfs/media", files={"file": ("m", payload)}, headers=signed_headers(CREATOR))
    assert response.status_code == status, response.text


def test_metadata_json_upload(api):
    client, _ = api
    response = client.post("/ipfs/metadata", json={"proposal": "ipfs://Qm" + "a" * 44, "title": "Solar"},
                           headers=signed_headers(CREATOR))
    assert response.status_code == 200, response.text
    assert (response.json()["kind"], response.json()["encrypted"]) == ("metadata", False)


def test_roles_endpoint_reports_permissions(api):
    client, _ = api
    response = client.get("/auth/roles?campaign_id=1", headers=signed_headers(DIAMOND))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["roles"] == ["backer", "diamond", "public"]
    assert body["can_read"]["exclusive"] and body["can_read"]["proof"]
    assert not body["can_upload"]["proof"]
    challenge = client.get(f"/auth/challenge?address={BACKER.address.lower()}").json()
    assert challenge["address"] == BACKER.address
    assert f"Address: {BACKER.address}" in challenge["message"]


# ---------------------------------------------------------------- campaign / voting routes

def test_campaign_and_voting_routes_are_mounted():
    application = create_app()
    application.dependency_overrides[get_contract] = lambda: fake_platform()
    with TestClient(application) as client:
        assert client.get("/campaigns").json()[0]["creator"] == CREATOR.address
        assert client.get("/campaigns/1/stats").json()["progress_percent"] == 100.0
        assert client.get("/campaigns/1/requests").json()[0]["amount_wei"] == ETH
        response = client.get("/campaigns/2")
        assert (response.status_code, response.json()["error"]["code"]) == (404, "campaign_not_found")


def test_platform_address_must_be_configured():
    with TestClient(create_app()) as client:
        response = client.get("/campaigns")
    assert (response.status_code, response.json()["error"]["code"]) == (503, "contract_not_configured")

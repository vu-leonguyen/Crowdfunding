from types import SimpleNamespace

import pytest

from app.modules.campaign.service import CampaignNotFound, CampaignService
from app.modules.voting.service import VotingService

ETH = 10**18


class Call:
    def __init__(self, v):
        self.v = v

    def call(self):
        return self.v


def fake_contract(appr=3 * ETH):
    req = (1, "hw", ETH, "0xV", "cid", appr, 0, False, False)
    camp = (1, "0xC", "Green", "d", "cid", 5 * ETH, 1000, 5 * ETH, 5 * ETH, 3, 1)
    return SimpleNamespace(functions=SimpleNamespace(
        campaignCounter=lambda: Call(1),
        getCampaign=lambda i: Call(camp),
        getSpendingRequest=lambda c, r: Call(req),
    ))


def test_stats_progress_and_countdown():
    s = CampaignService(fake_contract()).stats(1, now=400)
    assert (s.progress_percent, s.seconds_left, s.state) == (100.0, 600, "Operational")
    assert CampaignService(fake_contract()).stats(1, now=5000).seconds_left == 0


def test_unknown_campaign():
    with pytest.raises(CampaignNotFound):
        CampaignService(fake_contract()).get(2)


def test_threshold_is_strictly_above_half():
    r = VotingService(fake_contract()).list_requests(1)[0]
    assert (r.approval_percent, r.passes_threshold) == (60.0, True)
    # đúng 50% -> chưa đạt
    r = VotingService(fake_contract(appr=5 * ETH // 2)).list_requests(1)[0]
    assert r.passes_threshold is False

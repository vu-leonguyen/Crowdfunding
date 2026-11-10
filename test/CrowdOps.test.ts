import { expect } from "chai";
import { ethers } from "hardhat";
import { time } from "@nomicfoundation/hardhat-toolbox/network-helpers";
import { CrowdOpsPlatform } from "../typechain-types";
import { HardhatEthersSigner } from "@nomicfoundation/hardhat-ethers/signers";

// Kịch bản end-to-end của TV4. Chưa gọi setTokenContracts nên contract bỏ qua mint token/NFT.
describe("CrowdOps - kịch bản tích hợp", function () {
  let platform: CrowdOpsPlatform;
  let creator: HardhatEthersSigner;
  let backer1: HardhatEthersSigner;
  let backer2: HardhatEthersSigner;
  let vendor: HardhatEthersSigner;

  const GOAL = ethers.parseEther("5");
  const DURATION = 7 * 24 * 3600;
  const Fundraising = 0, Successful = 1, Failed = 2, Operational = 3;
  const Approve = 1, Reject = 2;

  async function createAndFund(a: bigint, b: bigint) {
    await platform
      .connect(creator)
      .createCampaign("Green IoT", "Solar micro-grids", "bafyproposal", GOAL, DURATION);
    await platform.connect(backer1).contribute(1, { value: a });
    await platform.connect(backer2).contribute(1, { value: b });
  }

  beforeEach(async function () {
    [, creator, backer1, backer2, vendor] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("CrowdOpsPlatform");
    platform = (await Factory.deploy()) as CrowdOpsPlatform;
    await platform.waitForDeployment();
  });

  it("TC1: tạo dự án -> đóng góp đủ vốn -> chiến dịch thành công", async function () {
    await platform
      .connect(creator)
      .createCampaign("Green IoT", "Solar micro-grids", "bafyproposal", GOAL, DURATION);
    expect((await platform.getCampaign(1)).state).to.equal(Fundraising);

    await platform.connect(backer1).contribute(1, { value: ethers.parseEther("3") });
    expect((await platform.getCampaign(1)).state).to.equal(Fundraising);

    await expect(platform.connect(backer2).contribute(1, { value: ethers.parseEther("2") }))
      .to.emit(platform, "CampaignStateChanged")
      .withArgs(1, Successful);

    const c = await platform.getCampaign(1);
    expect(c.state).to.equal(Successful);
    expect(c.totalFundsRaised).to.equal(GOAL);
  });

  it("TC2: hết hạn không đủ vốn -> backer rút hoàn tiền 100%", async function () {
    await createAndFund(ethers.parseEther("2"), ethers.parseEther("1"));
    await time.increase(DURATION + 1);

    for (const [backer, amount] of [
      [backer1, ethers.parseEther("2")],
      [backer2, ethers.parseEther("1")],
    ] as const) {
      const before = await ethers.provider.getBalance(backer.address);
      const tx = await platform.connect(backer).refund(1);
      const r = await tx.wait();
      const after = await ethers.provider.getBalance(backer.address);
      expect(after - before + r!.gasUsed * r!.gasPrice).to.equal(amount);
      await expect(tx).to.emit(platform, "RefundClaimed").withArgs(1, backer.address, amount);
    }

    const c = await platform.getCampaign(1);
    expect(c.state).to.equal(Failed);
    expect(c.remainingFunds).to.equal(0);
    expect(await ethers.provider.getBalance(await platform.getAddress())).to.equal(0);
  });

  it("TC3: spending request -> bỏ phiếu > 50% -> rút tiền thành công", async function () {
    await createAndFund(ethers.parseEther("3"), ethers.parseEther("2"));
    const amount = ethers.parseEther("1.5");
    await platform.connect(creator).requestSpending(1, "Hardware", amount, vendor.address, "bafyproof");
    expect((await platform.getCampaign(1)).state).to.equal(Operational);

    await platform.connect(backer1).approveRequest(1, 1, Approve); // 3/5 = 60%

    const before = await ethers.provider.getBalance(vendor.address);
    await expect(platform.connect(creator).finalizeSpending(1, 1))
      .to.emit(platform, "SpendingFinalized")
      .withArgs(1, 1, amount, vendor.address);
    expect((await ethers.provider.getBalance(vendor.address)) - before).to.equal(amount);

    const req = await platform.getSpendingRequest(1, 1);
    expect(req.completed).to.be.true;
    expect((await platform.getCampaign(1)).remainingFunds).to.equal(GOAL - amount);
  });

  it("TC4a: reject >= 50% -> yêu cầu bị khóa, không giải ngân", async function () {
    await createAndFund(ethers.parseEther("3"), ethers.parseEther("2"));
    await platform.connect(creator).requestSpending(1, "Hardware", ethers.parseEther("1"), vendor.address, "bafyproof");

    await expect(platform.connect(backer1).approveRequest(1, 1, Reject))
      .to.emit(platform, "SpendingRejected")
      .withArgs(1, 1);
    // Request đã khóa: backer2 không thể vote thêm, creator không thể finalize
    await expect(platform.connect(backer2).approveRequest(1, 1, Approve))
      .to.be.revertedWithCustomError(platform, "RequestAlreadyClosed");

    await expect(platform.connect(creator).finalizeSpending(1, 1))
      .to.be.revertedWithCustomError(platform, "RequestAlreadyClosed");
    expect((await platform.getCampaign(1)).remainingFunds).to.equal(GOAL);
  });

  it("TC4b: approve đúng 50% (không vượt) -> bị từ chối giải ngân", async function () {
    await createAndFund(ethers.parseEther("2.5"), ethers.parseEther("2.5"));
    await platform.connect(creator).requestSpending(1, "Hardware", ethers.parseEther("1"), vendor.address, "bafyproof");
    await platform.connect(backer1).approveRequest(1, 1, Approve); // 2.5/5 = 50%

    await expect(platform.connect(creator).finalizeSpending(1, 1))
      .to.be.revertedWithCustomError(platform, "ApprovalThresholdNotMet");
  });

  it("bảo vệ: chỉ backer được vote, không vote 2 lần, chỉ creator được finalize", async function () {
    await createAndFund(ethers.parseEther("3"), ethers.parseEther("2"));
    await platform.connect(creator).requestSpending(1, "Hardware", ethers.parseEther("1"), vendor.address, "bafyproof");

    await expect(platform.connect(vendor).approveRequest(1, 1, Approve))
      .to.be.revertedWithCustomError(platform, "NotABacker");
    await platform.connect(backer1).approveRequest(1, 1, Approve);
    await expect(platform.connect(backer1).approveRequest(1, 1, Approve))
      .to.be.revertedWithCustomError(platform, "AlreadyVoted");
    await expect(platform.connect(backer1).finalizeSpending(1, 1))
      .to.be.revertedWithCustomError(platform, "Unauthorized");
  });
});

import { expect } from "chai";
import { ethers } from "hardhat";
import { time } from "@nomicfoundation/hardhat-toolbox/network-helpers";
import { CrowdOpsPlatform } from "../typechain-types";
import { HardhatEthersSigner } from "@nomicfoundation/hardhat-ethers/signers";

describe("CrowdOpsPlatform (Days 1 - 4: Core & Fundraising)", function () {
  let platform: CrowdOpsPlatform;
  let owner: HardhatEthersSigner;
  let creator: HardhatEthersSigner;
  let backer1: HardhatEthersSigner;
  let backer2: HardhatEthersSigner;
  let vendor: HardhatEthersSigner;

  const TITLE = "Decentralized Green Energy IoT";
  const DESCRIPTION = "Building open-source IoT solar micro-grids";
  const PROPOSAL_CID = "bafybeicgreenenergyiotproposal123456789";
  const GOAL = ethers.parseEther("5"); // 5 ETH
  const DURATION = 7 * 24 * 3600; // 7 days (in seconds)

  beforeEach(async function () {
    [owner, creator, backer1, backer2, vendor] = await ethers.getSigners();

    const PlatformFactory = await ethers.getContractFactory("CrowdOpsPlatform");
    platform = (await PlatformFactory.deploy()) as CrowdOpsPlatform;
    await platform.waitForDeployment();
  });

  describe("1. Deployment & Initialization", function () {
    it("should set the contract deployer as the owner", async function () {
      expect(await platform.owner()).to.equal(owner.address);
      expect(await platform.campaignCounter()).to.equal(0);
    });
  });

  describe("2. Campaign Creation (createCampaign)", function () {
    it("should successfully create a new campaign with valid parameters", async function () {
      const tx = await platform
        .connect(creator)
        .createCampaign(TITLE, DESCRIPTION, PROPOSAL_CID, GOAL, DURATION);

      await expect(tx)
        .to.emit(platform, "CampaignCreated")
        .withArgs(
          1,
          creator.address,
          TITLE,
          GOAL,
          (await time.latest()) + DURATION,
          PROPOSAL_CID
        );

      expect(await platform.campaignCounter()).to.equal(1);

      const campaign = await platform.getCampaign(1);
      expect(campaign.id).to.equal(1);
      expect(campaign.creator).to.equal(creator.address);
      expect(campaign.title).to.equal(TITLE);
      expect(campaign.goal).to.equal(GOAL);
      expect(campaign.totalFundsRaised).to.equal(0);
      expect(campaign.remainingFunds).to.equal(0);
      expect(campaign.state).to.equal(0); // Fundraising
    });

    it("should revert if goal is 0", async function () {
      await expect(
        platform
          .connect(creator)
          .createCampaign(TITLE, DESCRIPTION, PROPOSAL_CID, 0, DURATION)
      ).to.be.revertedWithCustomError(platform, "InvalidGoal");
    });

    it("should revert if duration is less than MIN_DURATION", async function () {
      await expect(
        platform
          .connect(creator)
          .createCampaign(TITLE, DESCRIPTION, PROPOSAL_CID, GOAL, 10) // 10s < 60s
      ).to.be.revertedWithCustomError(platform, "InvalidDeadline");
    });

    it("should revert if title or proposalCID is empty", async function () {
      await expect(
        platform
          .connect(creator)
          .createCampaign("", DESCRIPTION, PROPOSAL_CID, GOAL, DURATION)
      ).to.be.revertedWithCustomError(platform, "EmptyString");

      await expect(
        platform
          .connect(creator)
          .createCampaign(TITLE, DESCRIPTION, "", GOAL, DURATION)
      ).to.be.revertedWithCustomError(platform, "EmptyString");
    });
  });

  describe("3. Contributions (contribute)", function () {
    beforeEach(async function () {
      await platform
        .connect(creator)
        .createCampaign(TITLE, DESCRIPTION, PROPOSAL_CID, GOAL, DURATION);
    });

    it("should allow backers to contribute ETH and record their balance", async function () {
      const contrib1 = ethers.parseEther("2");
      await expect(
        platform.connect(backer1).contribute(1, { value: contrib1 })
      )
        .to.emit(platform, "FundContributed")
        .withArgs(1, backer1.address, contrib1, contrib1);

      expect(await platform.getContribution(1, backer1.address)).to.equal(contrib1);

      const campaign = await platform.getCampaign(1);
      expect(campaign.totalFundsRaised).to.equal(contrib1);
      expect(campaign.remainingFunds).to.equal(contrib1);
      expect(campaign.state).to.equal(0); // Still Fundraising
    });

    it("should transition state to Successful when goal is reached", async function () {
      await platform.connect(backer1).contribute(1, { value: ethers.parseEther("3") });
      
      // Reaching or exceeding goal of 5 ETH
      await expect(
        platform.connect(backer2).contribute(1, { value: ethers.parseEther("2") })
      )
        .to.emit(platform, "CampaignStateChanged")
        .withArgs(1, 1); // 1 = Successful

      const campaign = await platform.getCampaign(1);
      expect(campaign.state).to.equal(1); // Successful
      expect(campaign.totalFundsRaised).to.equal(GOAL);
    });

    it("should revert if contribution is 0 ETH", async function () {
      await expect(
        platform.connect(backer1).contribute(1, { value: 0 })
      ).to.be.revertedWithCustomError(platform, "ZeroContribution");
    });

    it("should revert if deadline has passed", async function () {
      await time.increase(DURATION + 1);

      await expect(
        platform.connect(backer1).contribute(1, { value: ethers.parseEther("1") })
      ).to.be.revertedWithCustomError(platform, "CampaignDeadlinePassed");
    });

    it("should revert if contributing to non-existent campaign", async function () {
      await expect(
        platform.connect(backer1).contribute(999, { value: ethers.parseEther("1") })
      ).to.be.revertedWithCustomError(platform, "CampaignNotFound");
    });
  });

  describe("4. Automatic Refund (refund)", function () {
    beforeEach(async function () {
      await platform
        .connect(creator)
        .createCampaign(TITLE, DESCRIPTION, PROPOSAL_CID, GOAL, DURATION);

      // Backers contribute partial funds (3 ETH out of 5 ETH goal)
      await platform.connect(backer1).contribute(1, { value: ethers.parseEther("2") });
      await platform.connect(backer2).contribute(1, { value: ethers.parseEther("1") });
    });

    it("should revert refund if campaign is still within deadline", async function () {
      await expect(
        platform.connect(backer1).refund(1)
      ).to.be.revertedWithCustomError(platform, "CampaignStillActive");
    });

    it("should allow backers to refund 100% of their money when deadline expires without reaching goal", async function () {
      // Advance time past deadline
      await time.increase(DURATION + 1);

      const beforeBalance = await ethers.provider.getBalance(backer1.address);

      const tx = await platform.connect(backer1).refund(1);
      const receipt = await tx.wait();
      const gasUsed = receipt!.gasUsed * receipt!.gasPrice;

      await expect(tx)
        .to.emit(platform, "RefundClaimed")
        .withArgs(1, backer1.address, ethers.parseEther("2"));

      const afterBalance = await ethers.provider.getBalance(backer1.address);

      // Verify ETH was refunded
      expect(afterBalance + gasUsed - beforeBalance).to.equal(ethers.parseEther("2"));

      // Verify contribution is zeroed out
      expect(await platform.getContribution(1, backer1.address)).to.equal(0);

      // Campaign remaining funds updated
      const campaign = await platform.getCampaign(1);
      expect(campaign.remainingFunds).to.equal(ethers.parseEther("1"));
      expect(campaign.state).to.equal(2); // Failed
    });

    it("should prevent double refund (Checks-Effects-Interactions)", async function () {
      await time.increase(DURATION + 1);

      await platform.connect(backer1).refund(1);

      // Second attempt must revert
      await expect(
        platform.connect(backer1).refund(1)
      ).to.be.revertedWithCustomError(platform, "NoContributionToRefund");
    });

    it("should not allow refund if the campaign was Successful", async function () {
      // Backer2 tops up to achieve 5 ETH goal
      await platform.connect(backer2).contribute(1, { value: ethers.parseEther("2") });

      await time.increase(DURATION + 1);

      await expect(
        platform.connect(backer1).refund(1)
      ).to.be.revertedWithCustomError(platform, "RefundNotAvailable");
    });
  });

  describe("5. Milestone Spending & Voting Preview", function () {
    beforeEach(async function () {
      await platform
        .connect(creator)
        .createCampaign(TITLE, DESCRIPTION, PROPOSAL_CID, GOAL, DURATION);

      // Fully funded
      await platform.connect(backer1).contribute(1, { value: ethers.parseEther("3") });
      await platform.connect(backer2).contribute(1, { value: ethers.parseEther("2") });
    });

    it("should allow creator to request spending and backers to approve", async function () {
      const amount = ethers.parseEther("1.5");
      const proofCID = "bafybeihserverhardwareinvoicepdf";

      await platform
        .connect(creator)
        .requestSpending(1, "Server Hardware Milestone 1", amount, vendor.address, proofCID);

      expect(await platform.hasVoted(1, 1, backer1.address)).to.be.false;

      // Backer1 (weight = 3 ETH > 50% of 5 ETH) votes Approve
      await platform.connect(backer1).approveRequest(1, 1, 1); // 1 = Approve

      expect(await platform.hasVoted(1, 1, backer1.address)).to.be.true;

      // Finalize spending
      const vendorBefore = await ethers.provider.getBalance(vendor.address);
      await platform.connect(creator).finalizeSpending(1, 1);
      const vendorAfter = await ethers.provider.getBalance(vendor.address);

      expect(vendorAfter - vendorBefore).to.equal(amount);
    });
  });
});

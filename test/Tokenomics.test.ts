import { expect } from "chai";
import { ethers } from "hardhat";
import { HardhatEthersSigner } from "@nomicfoundation/hardhat-ethers/signers";
import {
  CrowdOpsPlatform,
  GovernanceToken,
  DiamondPatronNFT,
} from "../typechain-types";

describe("Tokenomics: GovernanceToken ($CROPS) & DiamondPatronNFT ($DIAMOND)", function () {
  let platform: CrowdOpsPlatform;
  let crops: GovernanceToken;
  let diamond: DiamondPatronNFT;
  let owner: HardhatEthersSigner;
  let creator: HardhatEthersSigner;
  let backer1: HardhatEthersSigner;
  let backer2: HardhatEthersSigner;
  let outsider: HardhatEthersSigner;

  const TITLE = "CrowdOps Solar Microgrid";
  const DESCRIPTION = "Open-source decentralized energy grid";
  const PROPOSAL_CID = "ipfs://bafybeicgreenenergyiotproposal123456789";
  const GOAL = ethers.parseEther("5");
  const DURATION = 7 * 24 * 3600;

  beforeEach(async function () {
    [owner, creator, backer1, backer2, outsider] = await ethers.getSigners();

    const PlatformFactory = await ethers.getContractFactory("CrowdOpsPlatform");
    platform = (await PlatformFactory.deploy()) as CrowdOpsPlatform;
    await platform.waitForDeployment();

    const CropsFactory = await ethers.getContractFactory("GovernanceToken");
    crops = (await CropsFactory.deploy()) as GovernanceToken;
    await crops.waitForDeployment();

    const DiamondFactory = await ethers.getContractFactory("DiamondPatronNFT");
    diamond = (await DiamondFactory.deploy()) as DiamondPatronNFT;
    await diamond.waitForDeployment();

    const platformAddr = await platform.getAddress();
    await crops.connect(owner).setPlatformContract(platformAddr);
    await diamond.connect(owner).setPlatformContract(platformAddr);
    await platform
      .connect(owner)
      .setTokenContracts(await crops.getAddress(), await diamond.getAddress());
  });

  describe("1. Deployment & Metadata", function () {
    it("should initialize GovernanceToken with correct name, symbol, decimals, and owner", async function () {
      expect(await crops.name()).to.equal("CrowdOps Governance Token");
      expect(await crops.symbol()).to.equal("CROPS");
      expect(await crops.decimals()).to.equal(18);
      expect(await crops.owner()).to.equal(owner.address);
      expect(await crops.platformContract()).to.equal(await platform.getAddress());
    });

    it("should initialize DiamondPatronNFT with correct name, symbol, and owner", async function () {
      expect(await diamond.name()).to.equal("CrowdOps Diamond Patron");
      expect(await diamond.symbol()).to.equal("DIAMOND");
      expect(await diamond.owner()).to.equal(owner.address);
      expect(await diamond.totalSupply()).to.equal(0);
      expect(await diamond.platformContract()).to.equal(await platform.getAddress());
    });
  });

  describe("2. Access Control & Input Validation", function () {
    it("should prevent non-owners from updating platformContract", async function () {
      await expect(
        crops.connect(outsider).setPlatformContract(outsider.address)
      ).to.be.revertedWithCustomError(crops, "OwnableUnauthorizedAccount");

      await expect(
        diamond.connect(outsider).setPlatformContract(outsider.address)
      ).to.be.revertedWithCustomError(diamond, "OwnableUnauthorizedAccount");
    });

    it("should revert when setting platformContract to zero address", async function () {
      await expect(
        crops.connect(owner).setPlatformContract(ethers.ZeroAddress)
      ).to.be.revertedWithCustomError(crops, "ZeroAddress");

      await expect(
        diamond.connect(owner).setPlatformContract(ethers.ZeroAddress)
      ).to.be.revertedWithCustomError(diamond, "ZeroAddress");
    });

    it("should prevent unauthorized addresses (including owner) from minting $CROPS directly", async function () {
      await expect(
        crops.connect(outsider).mint(outsider.address, ethers.parseEther("100"))
      ).to.be.revertedWithCustomError(crops, "UnauthorizedMinter");

      await expect(
        crops.connect(owner).mint(owner.address, ethers.parseEther("100"))
      ).to.be.revertedWithCustomError(crops, "UnauthorizedMinter");
    });

    it("should prevent unauthorized addresses (including owner) from minting Diamond NFT directly", async function () {
      await expect(
        diamond.connect(outsider).mintDiamondBadge(outsider.address, PROPOSAL_CID)
      ).to.be.revertedWithCustomError(diamond, "UnauthorizedMinter");

      await expect(
        diamond.connect(owner).mintDiamondBadge(owner.address, PROPOSAL_CID)
      ).to.be.revertedWithCustomError(diamond, "UnauthorizedMinter");
    });
  });

  describe("3. Automated Minting via CrowdOpsPlatform", function () {
    beforeEach(async function () {
      await platform
        .connect(creator)
        .createCampaign(TITLE, DESCRIPTION, PROPOSAL_CID, GOAL, DURATION);
    });

    it("should mint $CROPS at 1 ETH = 1,000 $CROPS rate without NFT below 1 ETH", async function () {
      const contribution = ethers.parseEther("0.4");
      const expectedTokens = ethers.parseEther("400"); // 0.4 * 1000 = 400 CROPS

      await expect(platform.connect(backer1).contribute(1, { value: contribution }))
        .to.emit(crops, "TokensMinted")
        .withArgs(backer1.address, expectedTokens);

      expect(await crops.balanceOf(backer1.address)).to.equal(expectedTokens);
      expect(await diamond.balanceOf(backer1.address)).to.equal(0);
      expect(await diamond.verifyDiamondPatron(backer1.address)).to.be.false;
    });

    it("should mint Diamond Patron NFT when cumulative contribution reaches >= 1 ETH", async function () {
      // First contribution: 0.4 ETH (no NFT yet)
      await platform.connect(backer1).contribute(1, { value: ethers.parseEther("0.4") });
      expect(await diamond.balanceOf(backer1.address)).to.equal(0);

      // Second contribution: 0.6 ETH -> cumulative 1.0 ETH (triggers Diamond NFT)
      const tx = await platform
        .connect(backer1)
        .contribute(1, { value: ethers.parseEther("0.6") });

      await expect(tx).to.emit(diamond, "DiamondBadgeMinted");

      // Total $CROPS = (0.4 + 0.6) * 1000 = 1,000 $CROPS
      expect(await crops.balanceOf(backer1.address)).to.equal(ethers.parseEther("1000"));
      expect(await diamond.balanceOf(backer1.address)).to.equal(1);
      expect(await diamond.totalSupply()).to.equal(1);
      expect(await diamond.ownerOf(1)).to.equal(backer1.address);
      expect(await diamond.tokenURI(1)).to.equal(PROPOSAL_CID);
      expect(await diamond.mintedAt(1)).to.be.gt(0);
      expect(await diamond.verifyDiamondPatron(backer1.address)).to.be.true;
    });

    it("should not mint duplicate Diamond NFT if backer already owns one", async function () {
      await platform.connect(backer1).contribute(1, { value: ethers.parseEther("1.5") });
      expect(await diamond.balanceOf(backer1.address)).to.equal(1);

      await platform.connect(backer1).contribute(1, { value: ethers.parseEther("1.0") });
      expect(await diamond.balanceOf(backer1.address)).to.equal(1);
      expect(await crops.balanceOf(backer1.address)).to.equal(ethers.parseEther("2500"));
    });

    it("should assign sequential tokenIds to multiple Diamond Patrons", async function () {
      await platform.connect(backer1).contribute(1, { value: ethers.parseEther("1.0") });
      await platform.connect(backer2).contribute(1, { value: ethers.parseEther("2.0") });

      expect(await diamond.totalSupply()).to.equal(2);
      expect(await diamond.ownerOf(1)).to.equal(backer1.address);
      expect(await diamond.ownerOf(2)).to.equal(backer2.address);
    });

    it("should let the owner lower the Diamond threshold for testnet demos", async function () {
      await expect(platform.connect(owner).setDiamondTierThreshold(ethers.parseEther("0.01")))
        .to.emit(platform, "DiamondTierThresholdUpdated")
        .withArgs(ethers.parseEther("1"), ethers.parseEther("0.01"));

      await platform.connect(backer1).contribute(1, { value: ethers.parseEther("0.01") });
      expect(await diamond.verifyDiamondPatron(backer1.address)).to.be.true;
    });

    it("should reject threshold updates from non-owners or to zero", async function () {
      await expect(platform.connect(outsider).setDiamondTierThreshold(1))
        .to.be.revertedWithCustomError(platform, "OwnableUnauthorizedAccount")
        .withArgs(outsider.address);
      await expect(platform.connect(owner).setDiamondTierThreshold(0))
        .to.be.revertedWithCustomError(platform, "InvalidThreshold");
    });
  });

  describe("4. Token Transfer & Verification (Criterion 4)", function () {
    beforeEach(async function () {
      await platform
        .connect(creator)
        .createCampaign(TITLE, DESCRIPTION, PROPOSAL_CID, GOAL, DURATION);
      await platform.connect(backer1).contribute(1, { value: ethers.parseEther("1.0") });
    });

    it("should allow $CROPS transfer between accounts", async function () {
      const transferAmount = ethers.parseEther("250");
      await crops.connect(backer1).transfer(backer2.address, transferAmount);

      expect(await crops.balanceOf(backer1.address)).to.equal(ethers.parseEther("750"));
      expect(await crops.balanceOf(backer2.address)).to.equal(transferAmount);
    });

    it("should allow Diamond Patron NFT transfer and update verification status", async function () {
      expect(await diamond.verifyDiamondPatron(backer1.address)).to.be.true;
      expect(await diamond.verifyDiamondPatron(backer2.address)).to.be.false;

      await diamond.connect(backer1).transferFrom(backer1.address, backer2.address, 1);

      expect(await diamond.ownerOf(1)).to.equal(backer2.address);
      expect(await diamond.verifyDiamondPatron(backer1.address)).to.be.false;
      expect(await diamond.verifyDiamondPatron(backer2.address)).to.be.true;
    });
  });
});

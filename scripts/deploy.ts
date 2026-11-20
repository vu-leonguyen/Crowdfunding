import { ethers, artifacts, network } from "hardhat";
import * as fs from "fs";
import * as path from "path";

async function main() {
  const [deployer] = await ethers.getSigners();
  const chainId = Number((await ethers.provider.getNetwork()).chainId);

  console.log(`Deploying CrowdOps contracts to network: ${network.name} (chainId: ${chainId})`);
  console.log(`Deployer address: ${deployer.address}`);

  // 1. Deploy CrowdOpsPlatform
  const PlatformFactory = await ethers.getContractFactory("CrowdOpsPlatform");
  const platform = await PlatformFactory.deploy();
  await platform.waitForDeployment();
  const platformAddr = await platform.getAddress();
  console.log(`CrowdOpsPlatform deployed at: ${platformAddr}`);

  // 2. Deploy GovernanceToken ($CROPS)
  const CropsFactory = await ethers.getContractFactory("GovernanceToken");
  const crops = await CropsFactory.deploy();
  await crops.waitForDeployment();
  const cropsAddr = await crops.getAddress();
  console.log(`GovernanceToken ($CROPS) deployed at: ${cropsAddr}`);

  // 3. Deploy DiamondPatronNFT ($DIAMOND)
  const DiamondFactory = await ethers.getContractFactory("DiamondPatronNFT");
  const diamond = await DiamondFactory.deploy();
  await diamond.waitForDeployment();
  const diamondAddr = await diamond.getAddress();
  console.log(`DiamondPatronNFT ($DIAMOND) deployed at: ${diamondAddr}`);

  // 4. Link contracts together
  await (await crops.setPlatformContract(platformAddr)).wait();
  await (await diamond.setPlatformContract(platformAddr)).wait();
  await (await platform.setTokenContracts(cropsAddr, diamondAddr)).wait();
  console.log("All contracts linked successfully.");

  // 4b. Diamond tier threshold: keep 1 ETH locally, use a faucet-friendly 0.01 ETH on public testnets.
  //     Override with DIAMOND_TIER_THRESHOLD_ETH in .env.
  const isLocal = network.name === "hardhat" || network.name === "localhost";
  const thresholdEth = process.env.DIAMOND_TIER_THRESHOLD_ETH || (isLocal ? "1" : "0.01");
  const threshold = ethers.parseEther(thresholdEth);
  if (threshold !== (await platform.diamondTierThreshold())) {
    await (await platform.setDiamondTierThreshold(threshold)).wait();
  }
  console.log(`Diamond tier threshold: ${thresholdEth} ETH`);

  // 5. Export ABIs and addresses for Frontend
  const frontendContractsDir = path.join(__dirname, "..", "frontend", "src", "contracts");
  fs.mkdirSync(frontendContractsDir, { recursive: true });

  const contractNames = ["CrowdOpsPlatform", "GovernanceToken", "DiamondPatronNFT"] as const;
  for (const name of contractNames) {
    const artifact = await artifacts.readArtifact(name);
    fs.writeFileSync(
      path.join(frontendContractsDir, `${name}.json`),
      JSON.stringify({ abi: artifact.abi }, null, 2)
    );
  }

  const addressesPath = path.join(frontendContractsDir, "addresses.json");
  const existing = fs.existsSync(addressesPath)
    ? JSON.parse(fs.readFileSync(addressesPath, "utf8"))
    : {};

  existing[String(chainId)] = {
    network: network.name,
    CrowdOpsPlatform: platformAddr,
    GovernanceToken: cropsAddr,
    DiamondPatronNFT: diamondAddr,
    deployer: deployer.address,
    deployedAt: new Date().toISOString(),
  };

  fs.writeFileSync(addressesPath, JSON.stringify(existing, null, 2));
  console.log(`Exported ABIs and addresses to ${frontendContractsDir}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});


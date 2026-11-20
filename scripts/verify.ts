import { run, network, ethers } from "hardhat";
import * as fs from "fs";
import * as path from "path";

/**
 * Verifies the three CrowdOps contracts on Etherscan using the addresses
 * written by scripts/deploy.ts. None of the constructors take arguments.
 */
async function main() {
  const chainId = Number((await ethers.provider.getNetwork()).chainId);
  const addressesPath = path.join(__dirname, "..", "frontend", "src", "contracts", "addresses.json");
  const all = JSON.parse(fs.readFileSync(addressesPath, "utf8"));
  const addrs = all[String(chainId)];
  if (!addrs) throw new Error(`No deployed addresses for chainId ${chainId} in ${addressesPath}`);

  for (const name of ["CrowdOpsPlatform", "GovernanceToken", "DiamondPatronNFT"] as const) {
    console.log(`Verifying ${name} at ${addrs[name]} on ${network.name}...`);
    try {
      await run("verify:verify", { address: addrs[name], constructorArguments: [] });
    } catch (err) {
      const msg = (err as Error).message || String(err);
      if (/already verified/i.test(msg)) console.log(`${name} already verified.`);
      else throw err;
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

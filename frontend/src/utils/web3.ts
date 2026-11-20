import { BrowserProvider, Contract, Eip1193Provider, Signer } from "ethers";
import PlatformArtifact from "../contracts/CrowdOpsPlatform.json";
import CropsArtifact from "../contracts/GovernanceToken.json";
import DiamondArtifact from "../contracts/DiamondPatronNFT.json";
import AddressesMap from "../contracts/addresses.json";

export interface DeployedAddresses {
  network: string;
  CrowdOpsPlatform: string;
  GovernanceToken: string;
  DiamondPatronNFT: string;
}

export const CAMPAIGN_STATE_LABELS = [
  "Fundraising",
  "Successful",
  "Failed",
  "Operational",
  "Closed",
] as const;

declare global {
  interface Window {
    ethereum?: Eip1193Provider & {
      on?: (event: string, listener: (...args: unknown[]) => void) => void;
      removeListener?: (event: string, listener: (...args: unknown[]) => void) => void;
    };
  }
}

export function getAddressesForChain(chainId: number): DeployedAddresses | null {
  const map = AddressesMap as Record<string, DeployedAddresses>;
  return map[String(chainId)] ?? null;
}

export async function connectWallet(): Promise<{
  provider: BrowserProvider;
  signer: Signer;
  address: string;
  chainId: number;
}> {
  if (!window.ethereum) {
    throw new Error("Không tìm thấy MetaMask. Vui lòng cài đặt MetaMask extension.");
  }
  const provider = new BrowserProvider(window.ethereum);
  await provider.send("eth_requestAccounts", []);
  const signer = await provider.getSigner();
  const address = await signer.getAddress();
  const network = await provider.getNetwork();
  return { provider, signer, address, chainId: Number(network.chainId) };
}

export function getContracts(signerOrProvider: Signer | BrowserProvider, addrs: DeployedAddresses) {
  return {
    platform: new Contract(addrs.CrowdOpsPlatform, PlatformArtifact.abi, signerOrProvider),
    crops: new Contract(addrs.GovernanceToken, CropsArtifact.abi, signerOrProvider),
    diamond: new Contract(addrs.DiamondPatronNFT, DiamondArtifact.abi, signerOrProvider),
  };
}

export function parseWeb3Error(err: unknown): string {
  if (!err || typeof err !== "object") return "Giao dịch thất bại.";
  const e = err as { reason?: string; shortMessage?: string; message?: string; code?: string | number };
  if (e.code === "ACTION_REJECTED" || e.code === 4001) {
    return "Bạn đã từ chối ký giao dịch trên MetaMask.";
  }
  return e.reason || e.shortMessage || e.message || "Giao dịch thất bại.";
}


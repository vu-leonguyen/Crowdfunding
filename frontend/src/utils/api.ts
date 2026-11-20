import { Signer } from "ethers";

/**
 * Client for the CrowdOps backend (IPFS upload + role-based file access).
 *
 * Authentication: the backend issues a time-stamped message (GET /auth/challenge),
 * the wallet signs it (personal_sign) and the signature travels in X-Wallet-*
 * headers. One signature is reused for a few minutes to avoid repeated prompts.
 */
export const API_BASE = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
export const IPFS_GATEWAY = (import.meta.env.VITE_IPFS_GATEWAY || "https://gateway.pinata.cloud/ipfs").replace(
  /\/$/,
  ""
);

export type UploadKind = "proposal" | "media" | "proof" | "exclusive";

export interface UploadResult {
  cid: string;
  ipfs_uri: string;
  gateway_url: string;
  size: number;
  kind: string;
  encrypted: boolean;
  mime_type: string;
}

/** ERC-721 compatible metadata stored as the campaign's on-chain proposalCID. */
export interface CampaignMetadata {
  name: string;
  description: string;
  /** Proposal / whitepaper PDF */
  proposal: string;
  /** Cover image (ERC-721 `image`) */
  image?: string;
  /** Video (ERC-721 `animation_url`) */
  animation_url?: string;
  media: { uri: string; mime: string }[];
  attributes: { trait_type: string; value: string }[];
}

const ERROR_MESSAGES: Record<string, string> = {
  auth_required: "Cần ký xác thực ví để thực hiện thao tác này.",
  invalid_signature: "Chữ ký ví không hợp lệ. Kiểm tra MetaMask đang ở đúng mạng với backend.",
  signature_expired: "Chữ ký đã hết hạn, vui lòng thử lại.",
  forbidden: "Ví của bạn không có quyền truy cập tài nguyên này.",
  campaign_not_found: "Không tìm thấy chiến dịch.",
  unsupported_file: "Định dạng file không được hỗ trợ.",
  file_too_large: "File vượt quá giới hạn dung lượng.",
  empty_file: "File rỗng.",
  pinata_not_configured: "Backend chưa cấu hình PINATA_JWT.",
  pinata_failed: "Upload lên IPFS (Pinata) thất bại, vui lòng thử lại.",
  encryption_not_configured: "Backend chưa cấu hình FILE_ENCRYPTION_KEY.",
  contract_not_configured: "Backend chưa cấu hình PLATFORM_ADDRESS.",
  gateway_failed: "Không tải được file từ IPFS gateway.",
  file_not_found: "Không tìm thấy file trên IPFS.",
  not_protected: "File này công khai, mở trực tiếp qua IPFS gateway.",
  foreign_file: "File không thuộc deployment CrowdOps này.",
  invalid_envelope: "File mã hóa bị hỏng hoặc đã bị chỉnh sửa.",
  chain_mismatch: "Backend đang kết nối sai mạng blockchain.",
  rpc_unavailable: "Backend không kết nối được blockchain RPC.",
};

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = "http_" + response.status;
  let message = `Backend trả lỗi HTTP ${response.status}.`;
  try {
    const body = await response.json();
    code = body?.error?.code ?? code;
    message = ERROR_MESSAGES[code] ?? body?.error?.message ?? message;
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(response.status, code, message);
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "backend_unreachable", `Không kết nối được backend tại ${API_BASE}. Đã chạy uvicorn chưa?`);
  }
  if (!response.ok) throw await toApiError(response);
  return response;
}

// ------------------------------------------------------------------ wallet auth

const SIGNATURE_REUSE_SECONDS = 240; // backend accepts 300s
const sessions = new Map<string, { headers: Record<string, string>; issuedAt: number }>();

export async function authHeaders(signer: Signer): Promise<Record<string, string>> {
  const address = await signer.getAddress();
  const chainId = Number((await signer.provider!.getNetwork()).chainId);
  const key = `${chainId}:${address.toLowerCase()}`;
  const cached = sessions.get(key);
  if (cached && Date.now() / 1000 - cached.issuedAt < SIGNATURE_REUSE_SECONDS) return cached.headers;

  const challenge = await (await request(`/auth/challenge?address=${address}`)).json();
  const signature = await signer.signMessage(challenge.message);
  const headers = {
    "X-Wallet-Address": challenge.address,
    "X-Wallet-Signature": signature,
    "X-Wallet-Issued-At": String(challenge.issued_at),
  };
  sessions.set(key, { headers, issuedAt: challenge.issued_at });
  return headers;
}

export function clearAuthSessions() {
  sessions.clear();
}

// ------------------------------------------------------------------ uploads

export async function uploadFile(
  signer: Signer,
  kind: UploadKind,
  file: File,
  campaignId?: number
): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  if (campaignId !== undefined) form.append("campaign_id", String(campaignId));
  const response = await request(`/ipfs/${kind}`, {
    method: "POST",
    headers: await authHeaders(signer),
    body: form,
  });
  return response.json();
}

export async function uploadMetadata(signer: Signer, metadata: CampaignMetadata): Promise<UploadResult> {
  const response = await request("/ipfs/metadata", {
    method: "POST",
    headers: { ...(await authHeaders(signer)), "Content-Type": "application/json" },
    body: JSON.stringify(metadata),
  });
  return response.json();
}

// ------------------------------------------------------------------ retrieval

/** Normalise `ipfs://CID`, `CID` or a gateway URL to a browser-openable URL. */
export function toGatewayUrl(uri: string): string {
  const value = uri.trim();
  if (/^https?:\/\//i.test(value)) return value;
  return `${IPFS_GATEWAY}/${value.replace(/^ipfs:\/\//i, "").replace(/^ipfs\//i, "")}`;
}

export function cidOf(uri: string): string {
  return uri.trim().replace(/^ipfs:\/\//i, "").replace(/^.*\/ipfs\//i, "").split(/[/?#]/)[0];
}

const metadataCache = new Map<string, Promise<CampaignMetadata | null>>();

/** Loads campaign metadata JSON from IPFS; resolves null if the CID is not metadata JSON. */
export function loadCampaignMetadata(uri: string): Promise<CampaignMetadata | null> {
  const cid = cidOf(uri);
  if (!metadataCache.has(cid)) {
    metadataCache.set(
      cid,
      (async () => {
        try {
          const response = await fetch(toGatewayUrl(uri));
          if (!response.ok) return null;
          const type = response.headers.get("content-type") ?? "";
          if (!type.includes("json")) return null;
          const data = await response.json();
          return typeof data?.proposal === "string" ? (data as CampaignMetadata) : null;
        } catch {
          return null;
        }
      })()
    );
  }
  return metadataCache.get(cid)!;
}

export interface ProtectedFile {
  url: string;
  mime: string;
  name: string;
}

/** Downloads + decrypts an access-controlled file (proof / exclusive) after an on-chain role check. */
export async function fetchProtectedFile(signer: Signer, uri: string): Promise<ProtectedFile> {
  const response = await request(`/ipfs/files/${cidOf(uri)}`, { headers: await authHeaders(signer) });
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "file";
  return { url: URL.createObjectURL(blob), mime: blob.type, name };
}

export async function getRoles(signer: Signer, campaignId?: number) {
  const query = campaignId ? `?campaign_id=${campaignId}` : "";
  const response = await request(`/auth/roles${query}`, { headers: await authHeaders(signer) });
  return response.json() as Promise<{
    address: string;
    campaign_id: number | null;
    roles: string[];
    can_upload: Record<string, boolean>;
    can_read: Record<string, boolean>;
  }>;
}

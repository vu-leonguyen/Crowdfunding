import { useEffect, useState } from "react";
import { Signer } from "ethers";
import {
  ApiError,
  CampaignMetadata,
  fetchProtectedFile,
  loadCampaignMetadata,
  ProtectedFile,
  toGatewayUrl,
} from "../utils/api";

/** Public campaign content: metadata JSON (on-chain proposalCID) → proposal PDF, image, video. */
export function CampaignMediaView({ proposalCID }: { proposalCID: string }) {
  const [meta, setMeta] = useState<CampaignMetadata | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    loadCampaignMetadata(proposalCID).then((m) => alive && setMeta(m));
    return () => {
      alive = false;
    };
  }, [proposalCID]);

  if (meta === undefined) return <p className="meta">Đang tải nội dung từ IPFS...</p>;

  if (meta === null) {
    return (
      <p className="meta">
        Proposal:{" "}
        <a href={toGatewayUrl(proposalCID)} target="_blank" rel="noreferrer">
          Mở trên IPFS ↗
        </a>{" "}
        <code>{proposalCID}</code>
      </p>
    );
  }

  const videos = meta.media.filter((m) => m.mime.startsWith("video/"));
  const images = meta.media.filter((m) => m.mime.startsWith("image/"));
  return (
    <div className="ipfs-media">
      {images.length > 0 && (
        <div className="media-strip">
          {images.map((m) => (
            <a key={m.uri} href={toGatewayUrl(m.uri)} target="_blank" rel="noreferrer">
              <img src={toGatewayUrl(m.uri)} alt={`Hình minh họa chiến dịch ${meta.name}`} loading="lazy" />
            </a>
          ))}
        </div>
      )}
      {videos.map((m) => (
        <video key={m.uri} src={toGatewayUrl(m.uri)} controls preload="metadata" />
      ))}
      <p className="meta">
        <a href={toGatewayUrl(meta.proposal)} target="_blank" rel="noreferrer">
          📄 Mở Proposal PDF ↗
        </a>{" "}
        ·{" "}
        <a href={toGatewayUrl(proposalCID)} target="_blank" rel="noreferrer">
          Metadata JSON ↗
        </a>{" "}
        · CID on-chain: <code>{proposalCID}</code>
      </p>
    </div>
  );
}

/** Access-controlled file (spending proof / exclusive): decrypted by the backend after a role check. */
export function ProtectedFileViewer({
  uri,
  label,
  getSigner,
}: {
  uri: string;
  label: string;
  getSigner: () => Promise<Signer>;
}) {
  const [file, setFile] = useState<ProtectedFile | null>(null);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => () => {
    if (file) URL.revokeObjectURL(file.url);
  }, [file]);

  const open = async () => {
    setBusy(true);
    setError(null);
    try {
      setFile(await fetchProtectedFile(await getSigner(), uri));
    } catch (err) {
      const e = err as ApiError;
      setError({ code: e.code ?? "error", message: e.message || "Không mở được file." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="protected-file">
      {!file && (
        <button className="btn" type="button" disabled={busy} onClick={open}>
          {busy ? "Đang ký & giải mã..." : `🔒 ${label}`}
        </button>
      )}
      {error && (
        <div className="alert error small">
          {error.message}
          {error.code === "not_protected" && (
            <>
              {" "}
              <a href={toGatewayUrl(uri)} target="_blank" rel="noreferrer">
                Mở trên IPFS ↗
              </a>
            </>
          )}
        </div>
      )}
      {file && (
        <div className="file-preview">
          {file.mime.startsWith("image/") && <img src={file.url} alt={file.name} />}
          {file.mime === "application/pdf" && <iframe src={file.url} title={file.name} />}
          {file.mime.startsWith("video/") && <video src={file.url} controls />}
          <p className="meta">
            Đã giải mã <code>{file.name}</code> ·{" "}
            <a href={file.url} target="_blank" rel="noreferrer">
              Mở tab mới ↗
            </a>{" "}
            ·{" "}
            <button className="link" type="button" onClick={() => setFile(null)}>
              Đóng
            </button>
          </p>
        </div>
      )}
    </div>
  );
}

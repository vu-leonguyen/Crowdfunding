import { useCallback, useEffect, useState } from "react";
import { formatEther, parseEther } from "ethers";
import { decryptAES, encryptAES } from "./utils/crypto";
import {
  CAMPAIGN_STATE_LABELS,
  connectWallet,
  DeployedAddresses,
  getAddressesForChain,
  getContracts,
  parseWeb3Error,
} from "./utils/web3";

interface CampaignItem {
  id: number;
  creator: string;
  title: string;
  description: string;
  proposalCID: string;
  goal: bigint;
  deadline: number;
  totalFundsRaised: bigint;
  remainingFunds: bigint;
  state: number;
  requestCount: number;
  myContribution: bigint;
  requests: SpendingRequestItem[];
}

interface SpendingRequestItem {
  id: number;
  description: string;
  amount: bigint;
  recipient: string;
  proofCID: string;
  approvalWeight: bigint;
  rejectWeight: bigint;
  completed: boolean;
  rejected: boolean;
  hasVoted: boolean;
}

export default function App() {
  const [address, setAddress] = useState<string>("");
  const [chainId, setChainId] = useState<number>(0);
  const [addrs, setAddrs] = useState<DeployedAddresses | null>(null);
  const [ethBalance, setEthBalance] = useState<string>("0");
  const [cropsBalance, setCropsBalance] = useState<string>("0");
  const [isDiamondPatron, setIsDiamondPatron] = useState<boolean>(false);

  const [campaigns, setCampaigns] = useState<CampaignItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [statusMsg, setStatusMsg] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");

  // Create campaign form
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [sensitiveNote, setSensitiveNote] = useState("");
  const [encryptKey, setEncryptKey] = useState("");
  const [proposalCID, setProposalCID] = useState("");
  const [goalEth, setGoalEth] = useState("1");
  const [durationMinutes, setDurationMinutes] = useState("60");

  // Contribute & milestone inputs per campaign
  const [contribAmount, setContribAmount] = useState<Record<number, string>>({});
  const [reqDesc, setReqDesc] = useState<Record<number, string>>({});
  const [reqAmount, setReqAmount] = useState<Record<number, string>>({});
  const [reqRecipient, setReqRecipient] = useState<Record<number, string>>({});
  const [reqProofCID, setReqProofCID] = useState<Record<number, string>>({});

  // AES Decrypt helper state
  const [cipherInput, setCipherInput] = useState("");
  const [decryptKey, setDecryptKey] = useState("");
  const [decryptedOutput, setDecryptedOutput] = useState("");

  const loadData = useCallback(async (userAddr: string, currentChainId: number) => {
    const deployed = getAddressesForChain(currentChainId);
    setAddrs(deployed);
    if (!deployed || !window.ethereum) return;

    const { provider } = await connectWallet();
    const { platform, crops, diamond } = getContracts(provider, deployed);

    const [bal, cropsBal, isDiamond, counter] = await Promise.all([
      provider.getBalance(userAddr),
      crops.balanceOf(userAddr),
      diamond.verifyDiamondPatron(userAddr),
      platform.campaignCounter(),
    ]);

    setEthBalance(Number(formatEther(bal)).toFixed(4));
    setCropsBalance(Number(formatEther(cropsBal)).toLocaleString());
    setIsDiamondPatron(Boolean(isDiamond));

    const total = Number(counter);
    const items: CampaignItem[] = [];
    for (let i = 1; i <= total; i++) {
      const c = await platform.getCampaign(i);
      const myContrib = await platform.getContribution(i, userAddr);
      const reqCount = Number(c.requestCount);
      const requests: SpendingRequestItem[] = [];
      for (let r = 1; r <= reqCount; r++) {
        const req = await platform.getSpendingRequest(i, r);
        const voted = await platform.hasVoted(i, r, userAddr);
        requests.push({
          id: Number(req.id),
          description: req.description,
          amount: req.amount,
          recipient: req.recipient,
          proofCID: req.proofCID,
          approvalWeight: req.approvalWeight,
          rejectWeight: req.rejectWeight,
          completed: req.completed,
          rejected: req.rejected,
          hasVoted: voted,
        });
      }
      items.push({
        id: Number(c.id),
        creator: c.creator,
        title: c.title,
        description: c.description,
        proposalCID: c.proposalCID,
        goal: c.goal,
        deadline: Number(c.deadline),
        totalFundsRaised: c.totalFundsRaised,
        remainingFunds: c.remainingFunds,
        state: Number(c.state),
        requestCount: reqCount,
        myContribution: myContrib,
        requests,
      });
    }
    setCampaigns(items.reverse());
  }, []);

  const handleConnect = async () => {
    setErrorMsg("");
    setStatusMsg("");
    try {
      const { address: addr, chainId: cid } = await connectWallet();
      setAddress(addr);
      setChainId(cid);
      await loadData(addr, cid);
      setStatusMsg("Đã kết nối ví MetaMask thành công.");
    } catch (err) {
      setErrorMsg(parseWeb3Error(err));
    }
  };

  useEffect(() => {
    if (!window.ethereum) return;
    const onAccountsChanged = () => {
      if (address) handleConnect();
    };
    const onChainChanged = () => {
      if (address) handleConnect();
    };
    window.ethereum.on?.("accountsChanged", onAccountsChanged);
    window.ethereum.on?.("chainChanged", onChainChanged);
    return () => {
      window.ethereum?.removeListener?.("accountsChanged", onAccountsChanged);
      window.ethereum?.removeListener?.("chainChanged", onChainChanged);
    };
  });

  const handleCreateCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!addrs) return;
    setLoading(true);
    setErrorMsg("");
    setStatusMsg("");
    try {
      let finalDesc = description.trim();
      if (sensitiveNote.trim()) {
        if (!encryptKey.trim()) {
          throw new Error("Vui lòng nhập khóa mã hóa AES cho thông tin nhạy cảm.");
        }
        const encrypted = await encryptAES(sensitiveNote.trim(), encryptKey.trim());
        finalDesc = `${finalDesc}\n[EncryptedContact]: ${encrypted}`;
      }

      const { signer } = await connectWallet();
      const { platform } = getContracts(signer, addrs);
      const tx = await platform.createCampaign(
        title.trim(),
        finalDesc,
        proposalCID.trim(),
        parseEther(goalEth),
        BigInt(Number(durationMinutes) * 60)
      );
      setStatusMsg("Đang chờ xác nhận giao dịch createCampaign...");
      await tx.wait();
      setTitle("");
      setDescription("");
      setSensitiveNote("");
      setProposalCID("");
      await loadData(address, chainId);
      setStatusMsg("Tạo chiến dịch on-chain thành công!");
    } catch (err) {
      setErrorMsg(parseWeb3Error(err));
    } finally {
      setLoading(false);
    }
  };

  const handleContribute = async (campaignId: number) => {
    if (!addrs) return;
    setLoading(true);
    setErrorMsg("");
    setStatusMsg("");
    try {
      const amt = contribAmount[campaignId] || "0.1";
      const { signer } = await connectWallet();
      const { platform } = getContracts(signer, addrs);
      const tx = await platform.contribute(campaignId, { value: parseEther(amt) });
      setStatusMsg(`Đang gửi ${amt} ETH vào chiến dịch #${campaignId}...`);
      await tx.wait();
      await loadData(address, chainId);
      setStatusMsg(`Đóng góp ${amt} ETH thành công! Đã tự động cập nhật $CROPS & $DIAMOND.`);
    } catch (err) {
      setErrorMsg(parseWeb3Error(err));
    } finally {
      setLoading(false);
    }
  };

  const handleRefund = async (campaignId: number) => {
    if (!addrs) return;
    setLoading(true);
    setErrorMsg("");
    setStatusMsg("");
    try {
      const { signer } = await connectWallet();
      const { platform } = getContracts(signer, addrs);
      const tx = await platform.refund(campaignId);
      await tx.wait();
      await loadData(address, chainId);
      setStatusMsg(`Đã hoàn tiền 100% từ chiến dịch #${campaignId}.`);
    } catch (err) {
      setErrorMsg(parseWeb3Error(err));
    } finally {
      setLoading(false);
    }
  };

  const handleRequestSpending = async (campaignId: number) => {
    if (!addrs) return;
    setLoading(true);
    setErrorMsg("");
    setStatusMsg("");
    try {
      const { signer } = await connectWallet();
      const { platform } = getContracts(signer, addrs);
      const tx = await platform.requestSpending(
        campaignId,
        reqDesc[campaignId] || "Milestone payment",
        parseEther(reqAmount[campaignId] || "0.5"),
        reqRecipient[campaignId] || address,
        reqProofCID[campaignId] || "ipfs://bafybeiproof"
      );
      await tx.wait();
      await loadData(address, chainId);
      setStatusMsg(`Đã tạo đề xuất giải ngân cho chiến dịch #${campaignId}.`);
    } catch (err) {
      setErrorMsg(parseWeb3Error(err));
    } finally {
      setLoading(false);
    }
  };

  const handleVote = async (campaignId: number, requestId: number, voteType: 1 | 2) => {
    if (!addrs) return;
    setLoading(true);
    setErrorMsg("");
    setStatusMsg("");
    try {
      const { signer } = await connectWallet();
      const { platform } = getContracts(signer, addrs);
      const tx = await platform.approveRequest(campaignId, requestId, voteType);
      await tx.wait();
      await loadData(address, chainId);
      setStatusMsg(`Đã bỏ phiếu ${voteType === 1 ? "Approve" : "Reject"} cho yêu cầu #${requestId}.`);
    } catch (err) {
      setErrorMsg(parseWeb3Error(err));
    } finally {
      setLoading(false);
    }
  };

  const handleFinalize = async (campaignId: number, requestId: number) => {
    if (!addrs) return;
    setLoading(true);
    setErrorMsg("");
    setStatusMsg("");
    try {
      const { signer } = await connectWallet();
      const { platform } = getContracts(signer, addrs);
      const tx = await platform.finalizeSpending(campaignId, requestId);
      await tx.wait();
      await loadData(address, chainId);
      setStatusMsg(`Đã giải ngân thành công yêu cầu #${requestId}!`);
    } catch (err) {
      setErrorMsg(parseWeb3Error(err));
    } finally {
      setLoading(false);
    }
  };

  const handleDecrypt = async () => {
    setErrorMsg("");
    try {
      const plain = await decryptAES(cipherInput.trim(), decryptKey.trim());
      setDecryptedOutput(plain);
    } catch (err) {
      setErrorMsg("Giải mã thất bại: sai khóa hoặc sai định dạng AES256.");
      console.error(err);
    }
  };

  return (
    <div className="container">
      <header className="header">
        <div>
          <h1>CrowdOps DApp</h1>
          <p className="subtitle">Decentralized Crowdfunding &amp; Milestone Governance</p>
        </div>
        {!address ? (
          <button className="btn primary" onClick={handleConnect}>
            Kết nối MetaMask
          </button>
        ) : (
          <div className="wallet-bar">
            <span className="pill">Chain: {chainId}</span>
            <span className="pill">
              {address.slice(0, 6)}...{address.slice(-4)}
            </span>
            <span className="pill">{ethBalance} ETH</span>
            <span className="pill token">{cropsBalance} $CROPS</span>
            <span className={`pill ${isDiamondPatron ? "diamond" : ""}`}>
              {isDiamondPatron ? "💎 Diamond VIP" : "Standard Tier"}
            </span>
          </div>
        )}
      </header>

      {statusMsg && <div className="alert success">{statusMsg}</div>}
      {errorMsg && <div className="alert error">{errorMsg}</div>}

      {address && !addrs && (
        <div className="alert error">
          Chưa tìm thấy địa chỉ contract cho Chain ID {chainId}. Vui lòng chuyển sang Hardhat Local
          (31337) hoặc chạy <code>npx hardhat run scripts/deploy.ts</code> cho mạng này.
        </div>
      )}

      {address && addrs && (
        <div className="grid">
          <section className="card">
            <h2>1. Tạo Chiến Dịch Mới (On-Chain)</h2>
            <form onSubmit={handleCreateCampaign} className="form">
              <input
                placeholder="Tiêu đề chiến dịch"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
              <textarea
                placeholder="Mô tả công khai"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
              />
              <input
                placeholder="Thông tin nhạy cảm (SĐT/Email - sẽ mã hóa AES-256-GCM)"
                value={sensitiveNote}
                onChange={(e) => setSensitiveNote(e.target.value)}
              />
              {sensitiveNote && (
                <input
                  type="password"
                  placeholder="Passphrase mã hóa AES-256"
                  value={encryptKey}
                  onChange={(e) => setEncryptKey(e.target.value)}
                />
              )}
              <input
                placeholder="Proposal IPFS CID (vd: ipfs://bafybei...)"
                value={proposalCID}
                onChange={(e) => setProposalCID(e.target.value)}
                required
              />
              <div className="row">
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="Goal (ETH)"
                  value={goalEth}
                  onChange={(e) => setGoalEth(e.target.value)}
                  required
                />
                <input
                  type="number"
                  min="1"
                  placeholder="Thời hạn (phút)"
                  value={durationMinutes}
                  onChange={(e) => setDurationMinutes(e.target.value)}
                  required
                />
              </div>
              <button className="btn primary" type="submit" disabled={loading}>
                {loading ? "Đang xử lý..." : "Tạo chiến dịch"}
              </button>
            </form>

            <hr />
            <h3>Giải mã thông tin AES-256-GCM</h3>
            <div className="form">
              <input
                placeholder="Dán chuỗi AES256:..."
                value={cipherInput}
                onChange={(e) => setCipherInput(e.target.value)}
              />
              <input
                type="password"
                placeholder="Passphrase giải mã"
                value={decryptKey}
                onChange={(e) => setDecryptKey(e.target.value)}
              />
              <button className="btn" type="button" onClick={handleDecrypt}>
                Giải mã
              </button>
              {decryptedOutput && <div className="pill">Kết quả: {decryptedOutput}</div>}
            </div>
          </section>

          <section className="card">
            <h2>2. Danh Sách Chiến Dịch ({campaigns.length})</h2>
            {campaigns.length === 0 && <p>Chưa có chiến dịch nào.</p>}
            {campaigns.map((c) => {
              const raised = Number(formatEther(c.totalFundsRaised));
              const goal = Number(formatEther(c.goal));
              const pct = goal > 0 ? Math.min(100, Math.round((raised / goal) * 100)) : 0;
              const isCreator = c.creator.toLowerCase() === address.toLowerCase();

              return (
                <div key={c.id} className="campaign-box">
                  <div className="row space-between">
                    <strong>
                      #{c.id} — {c.title}
                    </strong>
                    <span className="pill">{CAMPAIGN_STATE_LABELS[c.state] ?? "Unknown"}</span>
                  </div>
                  <p className="desc">{c.description}</p>
                  <p className="meta">
                    Proposal: <code>{c.proposalCID}</code> | Tiến độ: {raised} / {goal} ETH ({pct}%) |
                    Còn lại: {formatEther(c.remainingFunds)} ETH | Bạn đã góp:{" "}
                    {formatEther(c.myContribution)} ETH
                  </p>
                  <div className="progress">
                    <div className="progress-fill" style={{ width: `${pct}%` }} />
                  </div>

                  {c.state === 0 && (
                    <div className="row">
                      <input
                        type="number"
                        step="0.1"
                        min="0.01"
                        placeholder="ETH"
                        value={contribAmount[c.id] ?? "1.0"}
                        onChange={(e) =>
                          setContribAmount((prev) => ({ ...prev, [c.id]: e.target.value }))
                        }
                      />
                      <button
                        className="btn primary"
                        disabled={loading}
                        onClick={() => handleContribute(c.id)}
                      >
                        Đóng góp ETH
                      </button>
                      <button className="btn" disabled={loading} onClick={() => handleRefund(c.id)}>
                        Hoàn tiền (nếu hết hạn)
                      </button>
                    </div>
                  )}

                  {c.state === 2 && c.myContribution > 0n && (
                    <button className="btn" disabled={loading} onClick={() => handleRefund(c.id)}>
                      Rút hoàn tiền 100%
                    </button>
                  )}

                  {isCreator && (c.state === 1 || c.state === 3) && (
                    <div className="milestone-form">
                      <strong>Tạo đề xuất giải ngân (Creator)</strong>
                      <div className="row">
                        <input
                          placeholder="Nội dung chi tiêu"
                          value={reqDesc[c.id] ?? ""}
                          onChange={(e) =>
                            setReqDesc((prev) => ({ ...prev, [c.id]: e.target.value }))
                          }
                        />
                        <input
                          placeholder="Số ETH"
                          value={reqAmount[c.id] ?? ""}
                          onChange={(e) =>
                            setReqAmount((prev) => ({ ...prev, [c.id]: e.target.value }))
                          }
                        />
                      </div>
                      <div className="row">
                        <input
                          placeholder="Địa chỉ nhận"
                          value={reqRecipient[c.id] ?? ""}
                          onChange={(e) =>
                            setReqRecipient((prev) => ({ ...prev, [c.id]: e.target.value }))
                          }
                        />
                        <input
                          placeholder="Proof CID"
                          value={reqProofCID[c.id] ?? ""}
                          onChange={(e) =>
                            setReqProofCID((prev) => ({ ...prev, [c.id]: e.target.value }))
                          }
                        />
                        <button
                          className="btn primary"
                          disabled={loading}
                          onClick={() => handleRequestSpending(c.id)}
                        >
                          Gửi đề xuất
                        </button>
                      </div>
                    </div>
                  )}

                  {c.requests.length > 0 && (
                    <div className="requests">
                      <strong>Yêu cầu chi tiêu ({c.requests.length})</strong>
                      {c.requests.map((r) => (
                        <div key={r.id} className="request-item">
                          <div>
                            #{r.id}: {r.description} — {formatEther(r.amount)} ETH →{" "}
                            <code>{r.recipient.slice(0, 8)}...</code> | Proof:{" "}
                            <code>{r.proofCID}</code>
                          </div>
                          <div className="meta">
                            Approve: {formatEther(r.approvalWeight)} ETH | Reject:{" "}
                            {formatEther(r.rejectWeight)} ETH |{" "}
                            {r.completed ? "Đã giải ngân" : r.rejected ? "Bị từ chối" : "Đang mở"}
                          </div>
                          {!r.completed && !r.rejected && (
                            <div className="row">
                              {c.myContribution > 0n && !r.hasVoted && (
                                <>
                                  <button
                                    className="btn primary"
                                    disabled={loading}
                                    onClick={() => handleVote(c.id, r.id, 1)}
                                  >
                                    Approve
                                  </button>
                                  <button
                                    className="btn"
                                    disabled={loading}
                                    onClick={() => handleVote(c.id, r.id, 2)}
                                  >
                                    Reject
                                  </button>
                                </>
                              )}
                              {isCreator && (
                                <button
                                  className="btn"
                                  disabled={loading}
                                  onClick={() => handleFinalize(c.id, r.id)}
                                >
                                  Giải ngân (&gt;50%)
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </section>
        </div>
      )}
    </div>
  );
}


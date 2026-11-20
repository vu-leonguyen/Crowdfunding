# CrowdOps — Decentralized Crowdfunding

Smart contracts (Hardhat), FastAPI backend (`backend/`) and React DApp (`frontend/`).

## Smart contracts

```bash
npm ci
npm test                 # Hardhat unit tests
```

### Deploy locally

```bash
npm run node             # terminal 1: local chain on 127.0.0.1:8545
npm run deploy:local     # terminal 2: deploy + export ABIs/addresses to frontend/src/contracts
```

### Deploy to Sepolia

1. Copy `.env.example` to `.env` and fill in `SEPOLIA_RPC_URL`, `DEPLOYER_PRIVATE_KEY`
   (a throwaway wallet holding only Sepolia test ETH) and `ETHERSCAN_API_KEY`.
   `.env` is git-ignored — never commit it.
2. Deploy and verify:

   ```bash
   npm run deploy:sepolia
   npm run verify:sepolia
   ```

`deploy:sepolia` deploys all three contracts, links them, sets the Diamond Patron
threshold to 0.01 ETH (override with `DIAMOND_TIER_THRESHOLD_ETH`), and writes the
addresses under chain `11155111` in `frontend/src/contracts/addresses.json`.
Commit that file so the DApp and teammates use the same deployment.

## Run the full DApp (Sepolia)

1. Backend — configure `backend/.env` (see `backend/.env.example`: Sepolia `RPC_URL`,
   `CHAIN_ID=11155111`, `PINATA_JWT`, contract addresses, `FILE_ENCRYPTION_KEY`), then:

   ```bash
   cd backend
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements.lock
   .venv/Scripts/python -m uvicorn app.main:app --port 8000
   ```

2. Frontend (MetaMask on Sepolia):

   ```bash
   cd frontend
   npm ci
   npm run dev              # http://localhost:5173
   ```

   Override the backend URL or IPFS gateway via `frontend/.env.local` (see `frontend/.env.example`).

### IPFS data flow

- **Create campaign:** proposal PDF and images/videos are uploaded through the backend
  to Pinata; a metadata JSON (ERC-721 style: `name`, `description`, `image`,
  `animation_url`, `proposal`) links them, and *its* CID is stored on-chain as
  `proposalCID`. Anyone can retrieve the originals from any IPFS gateway. The same JSON
  serves as the Diamond Patron NFT `tokenURI`.
- **Spending request:** the invoice is encrypted (AES-256-GCM) by the backend before
  pinning; its CID goes into `requestSpending`. Backers/creator open it from the voting
  dashboard after signing with their wallet; everyone else gets 403.

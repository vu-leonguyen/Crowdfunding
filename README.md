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

# Backend CrowdOps — phần việc thành viên 3

Bạn phụ trách **hạ tầng backend và IPFS**, trên nhánh `feature/backend-infra-ipfs`.

## Công việc của bạn là gì?

1. **Dựng bộ khung FastAPI**: cấu hình tập trung, CORS, vòng đời HTTP client,
   lỗi dịch vụ có mã lỗi, tài liệu Swagger `/docs` và health check.
2. **Cung cấp Web3Provider**: kết nối RPC Hardhat/Sepolia, xác minh chain ID,
   chuẩn hóa địa chỉ ví và trả lỗi rõ ràng khi node không hoạt động.
   Backend chỉ đọc blockchain, không giữ private key hoặc tự ký giao dịch của người dùng.
3. **Cung cấp ContractLoader**: đọc ABI JSON (mảng ABI hoặc artifact có trường `abi`),
   kiểm tra contract đã deploy tại địa chỉ cấu hình, khởi tạo Web3 contract instance.
4. **Upload IPFS qua Pinata**: nhận PDF Proposal, PDF/PNG/JPEG chứng từ,
   kiểm tra chữ ký đầu file và giới hạn kích thước, trả CID, URI IPFS và gateway URL.
5. **Tra cứu tokenomics**: đọc số dư ERC-20 và NFT tại cùng một block,
   trả tier và quyền truy cập dự kiến. Dùng chuỗi cho số dư để tránh mất độ chính xác JavaScript.

Thành viên 1 phụ trách quỹ/campaign/voting Solidity. Thành viên 2 phụ trách triển khai
ERC-20/NFT và mint. Thành viên 4 phụ trách Campaign/Voting API và test nghiệp vụ
smart contract. Backend này cung cấp nền tảng để TV4 thêm router/service, không thay thế
các phần việc đó.

## Chạy cục bộ

Yêu cầu Python 3.11+ (đã kiểm tra Python 3.12), Node và dependencies Hardhat của repo.
Các lệnh sau chạy từ thư mục gốc repo:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock
# Chỉ tạo .env nếu chưa có; không ghi đè cấu hình đã có.
cp -n backend/.env.example backend/.env
```

Sửa `backend/.env` trên máy của bạn. File này đã được `.gitignore` loại trừ.
Để dùng Sepolia, đặt RPC_URL của nhà cung cấp và CHAIN_ID=11155111;
không chia sẻ URL chứa API key hoặc JWT.

Terminal 1, từ gốc repo:

```bash
export XDG_CONFIG_HOME=/workspace/.config
export XDG_CACHE_HOME=/workspace/.cache
export XDG_DATA_HOME=/workspace/.local/share
npx hardhat node --hostname 127.0.0.1
```

Ba biến XDG trên dành cho cloud workspace hiện tại có home chỉ đọc;
trên máy cá nhân thường không cần chúng. Hardhat tạo tài khoản thử nghiệm:
không dùng tài khoản/private key thử nghiệm với tiền thật.

Terminal 2:

```bash
cd backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Kiểm tra trong máy chạy ứng dụng:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/health/rpc
```

Swagger có route `/docs`, OpenAPI ở `/openapi.json`. `/health` là liveness;
`/health/rpc` kiểm tra RPC đúng chain, không có nghĩa Pinata/token đã cấu hình.

## Cấu hình và API

| Biến | Ý nghĩa |
| --- | --- |
| RPC_URL / CHAIN_ID | Mặc định Hardhat cục bộ / 31337 |
| CORS_ORIGINS | Mảng JSON các origin frontend được cho phép |
| PINATA_JWT | JWT Pinata có quyền pin file, chỉ lưu trong cấu hình bí mật |
| MAX_UPLOAD_BYTES | Mặc định 10 MiB mỗi file |
| IPFS_GATEWAY_URL | Gateway dùng tạo URL trả về; không quyết định nơi upload |
| GOVERNANCE_TOKEN_ADDRESS | Địa chỉ ERC-20 TV2 đã deploy |
| DIAMOND_NFT_ADDRESS | Địa chỉ ERC-721 TV2 đã deploy |
| TOKEN_DECIMALS | Mặc định 18; cần khớp token thực tế của TV2 |
| TOKEN_TIER_THRESHOLD | Mặc định 1000 CROPS, có thể điều chỉnh theo thống nhất nhóm |
| ABI_DIR | Mặc định `backend/abis`, chứa ABI đã xuất từ Hardhat |

| API | Chức năng |
| --- | --- |
| POST /ipfs/proposal | Multipart `file`: PDF Proposal |
| POST /ipfs/proof | Multipart `file`: PDF, PNG hoặc JPEG chứng từ |
| GET /tokenomics/{address}/tier | Số dư CROPS/NFT và tier |
| GET /health | Backend hoạt động |
| GET /health/rpc | RPC kết nối được và đúng chain |

Ví dụ upload sau khi cấu hình JWT:

```bash
curl --fail -F 'file=@proposal.pdf' http://127.0.0.1:8000/ipfs/proposal
```

Response gồm `cid`, `ipfs_uri`, `gateway_url`, `size`. Frontend chuyển `cid`
vào `createCampaign(..., proposalCID, ...)` hoặc `requestSpending(..., proofCID)`.
Upload không tự tạo campaign, không tự gửi transaction và không tự ghi CID lên chain.
JWT chỉ được gửi tới `api.pinata.cloud`, không trả về client. Nếu cloud chặn mạng,
cần cho phép `api.pinata.cloud`; gateway chỉ cần khi truy xuất nội dung.

Quy tắc tier hiện tại: có NFT → `diamond`; nếu không, CROPS >= ngưỡng →
`governance`; còn lại → `basic`. Hai tier đầu có `has_exclusive_access=true`.
Đây là chính sách backend có thể cấu hình, không thay đổi trọng số vote on-chain.
API đọc địa chỉ công khai **không chứng minh người gọi sở hữu ví**. Muốn bảo vệ nội dung
riêng tư cần xác thực ví bằng challenge/chữ ký và kiểm tra tier phía server.

Endpoint upload đang phục vụ phát triển. Trước khi mở công khai, cần xác thực người
upload, rate limit/quota và giới hạn request body ở reverse proxy để bảo vệ tài khoản
Pinata. Kiểm tra magic bytes không thay thế quét nội dung độc hại. Không upload bí mật:
IPFS là dữ liệu công khai và pin file không đảm bảo được lưu vĩnh viễn.

## Bàn giao tích hợp

- TV2 deploy token/NFT, cung cấp địa chỉ đúng chain và xác nhận decimals.
- ABI token hiện lấy từ `IGovernanceToken`/`IDiamondPatronNFT` trong repo:
  đủ cho `balanceOf`; chưa có implementation token để kiểm tra tích hợp thực tế.
- Sau khi compile contract mới, xuất lại `artifact["abi"]` vào `backend/abis/`.
  `ContractLoader` cũng chấp nhận nguyên artifact JSON có trường `abi`.
- TV4 import `get_web3_provider`, `ContractLoader`, `ServiceError` và thêm
  router Campaign/Voting vào `app/main.py`. Các service sync đọc Web3 nên dùng
  endpoint `def` để FastAPI chạy trong thread pool.
- Không commit trực tiếp main; tạo PR nhánh này vào develop và nhờ nhóm review.
  Chưa tạo PR hoặc push tự động.

## Kiểm thử

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

Tests đơn vị dùng HTTP mock cho Pinata và mock Web3 cho token/NFT; không tốn quota,
không yêu cầu JWT. Mock xác minh multipart/Authorization, lỗi upstream và tính tier.
Bộ `test_integration.py` tự khởi động Hardhat ở cổng trống, deploy fixture ERC-20/ERC-721
của OpenZeppelin, gọi API tier bằng RPC thật và dừng node sau kiểm thử.
Fixture chỉ phục vụ test, không thay implementation của TV2. Node.js và `npm ci`
ở gốc repo là prerequisites cho bộ kiểm thử này.
Upload Pinata thật và số dư token/NFT đã deploy cần credentials/contract của nhóm.
`requirements.lock` chốt cả dependencies trực tiếp/gián tiếp của môi trường đã kiểm tra;
`requirements*.txt` thể hiện các dependency trực tiếp khi cập nhật sau này.

Kết quả kiểm tra trong cloud workspace: **44 test backend đạt**, **15 test Hardhat
hiện có đạt**, `pip check` không phát hiện dependency xung đột. Đã chạy Uvicorn,
gọi `/health/rpc` nhận chain 31337, deploy CrowdOpsPlatform lên Hardhat cục bộ,
nạp bằng ContractLoader và đọc thành công `campaignCounter()` / `owner()`.
Chưa kiểm tra upload Pinata thật vì thiếu JWT; chưa kiểm tra số dư token/NFT thật
vì repo hiện chỉ có interface của TV2. Có 2 cảnh báo deprecation từ dependency test,
không làm test thất bại.


## Đối chiếu nhiệm vụ và kiểm thử

| Nhiệm vụ TV3 | Mã nguồn | Bằng chứng kiểm thử |
| --- | --- | --- |
| FastAPI, CORS, exception handler, Swagger | `app/main.py`, `app/core/errors.py` | Health/docs/OpenAPI, origin cho phép/từ chối, lỗi validation và schema lỗi |
| Config tập trung | `app/config.py` | Đọc biến môi trường, kiểm tra giá trị cấu hình không hợp lệ, che JWT |
| RPC và địa chỉ tài khoản Web3 | `app/shared/web3_provider.py` | Hardhat thật, sai chain, RPC lỗi, địa chỉ không hợp lệ |
| Nạp ABI/contract | `app/shared/contract_loader.py` | ABI array/artifact, lỗi ABI, từ chối địa chỉ không có bytecode trên chain thật |
| Pinata upload Proposal/Proof | `app/modules/ipfs/` | Multipart API → service → Pinata mock → CID; PDF/PNG/JPEG, quá giới hạn, timeout, lỗi HTTP/JSON |
| Token balance và Diamond tier | `app/modules/tokenomics/` | 3 tier với token/NFT deploy thật trên Hardhat; test số lớn và đọc cùng block |

Chạy từ gốc repo: `backend/.venv/bin/python -m pytest backend/tests -q`.
CI backend đã bổ sung Node + `npm ci` để chạy cùng bộ kiểm thử blockchain;
CI dùng `requirements.lock`. Workflow GitHub Actions chưa được chạy trên GitHub
trong phiên này; kết quả ở trên là kiểm thử trong cloud workspace.

Kiểm thử Pinata Cloud thật (chỉ thực hiện khi đã cấu hình JWT và chấp nhận upload file công khai):

```bash
cd backend
.venv/bin/python -m scripts.smoke_pinata /path/to/proposal.pdf
# Với chứng từ:
.venv/bin/python -m scripts.smoke_pinata /path/to/invoice.png --kind proof
```

Lệnh này tạo pin thật và trả CID; không tự xoá pin. Không đưa JWT lên command line.
Chưa có JWT trong môi trường hiện tại, vì vậy **chưa thể kết luận tích hợp Pinata
Cloud thật đã đạt**. Unit/API tests của module IPFS đã đạt với upstream mock.
Tích hợp cuối cùng với token của TV2 và Sepolia vẫn cần địa chỉ deploy/RPC tương ứng;
fixture Hardhat xác minh backend nhưng không xác minh implementation chưa có của TV2.

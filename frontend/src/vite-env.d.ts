/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** CrowdOps backend base URL (FastAPI). Default: http://127.0.0.1:8000 */
  readonly VITE_API_URL?: string;
  /** IPFS gateway used to open public files. Default: Pinata public gateway */
  readonly VITE_IPFS_GATEWAY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

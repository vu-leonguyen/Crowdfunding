const SALT_BYTES = 16;
const IV_BYTES = 12;

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function fromBase64(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

async function deriveAesKey(passphrase: string, salt: Uint8Array): Promise<CryptoKey> {
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    enc.encode(passphrase),
    "PBKDF2",
    false,
    ["deriveKey"]
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: salt as BufferSource, iterations: 100_000, hash: "SHA-256" },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
}

/**
 * Encrypts sensitive plaintext with AES-256-GCM and returns a prefixed base64 payload.
 */
export async function encryptAES(plaintext: string, passphrase: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(SALT_BYTES));
  const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
  const key = await deriveAesKey(passphrase, salt);
  const encoded = new TextEncoder().encode(plaintext);
  const cipherBuffer = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, encoded);
  const cipherBytes = new Uint8Array(cipherBuffer);

  const combined = new Uint8Array(SALT_BYTES + IV_BYTES + cipherBytes.length);
  combined.set(salt, 0);
  combined.set(iv, SALT_BYTES);
  combined.set(cipherBytes, SALT_BYTES + IV_BYTES);

  return `AES256:${toBase64(combined)}`;
}

/**
 * Decrypts an `AES256:...` payload created by `encryptAES`.
 */
export async function decryptAES(payload: string, passphrase: string): Promise<string> {
  const rawB64 = payload.startsWith("AES256:") ? payload.slice(7) : payload;
  const combined = fromBase64(rawB64);
  if (combined.length <= SALT_BYTES + IV_BYTES) {
    throw new Error("Dữ liệu mã hóa không hợp lệ.");
  }
  const salt = combined.slice(0, SALT_BYTES);
  const iv = combined.slice(SALT_BYTES, SALT_BYTES + IV_BYTES);
  const cipherBytes = combined.slice(SALT_BYTES + IV_BYTES);

  const key = await deriveAesKey(passphrase, salt);
  const plainBuffer = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, cipherBytes);
  return new TextDecoder().decode(plainBuffer);
}


/**
 * x402 payment client — Dexter Cash integration.
 *
 * When the gateway returns HTTP 402, we:
 *   1. Parse the WWW-Authenticate header to get payment requirements
 *   2. Build and sign an on-chain USDC transfer (Base / Solana / etc.)
 *   3. Return the base64-encoded receipt as X-Payment header value
 *
 * We use the Coinbase x402 client library which handles chain-specific
 * signing and is pure JS — no native deps, works in React Native.
 *
 * For dev mode (when EXPO_PUBLIC_DEV_MODE=true), we return a synthetic
 * receipt so you can test the full flow without a real wallet.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

export interface PaymentRequirements {
  scheme:    string;   // "exact"
  network:   string;   // "base" | "solana" | "polygon" | ...
  amount:    string;   // USDC micro-units (6 decimals)
  token:     string;   // "USDC"
  recipient: string;   // operator wallet address
  resource:  string;   // the endpoint being paid for
}

const DEV_MODE = process.env.EXPO_PUBLIC_DEV_MODE === 'true';

/** Parse the WWW-Authenticate: x402 header into structured requirements. */
export function parsePaymentHeader(headers: Record<string, string>): PaymentRequirements {
  const raw = headers['www-authenticate'] ?? headers['WWW-Authenticate'] ?? '';
  if (!raw.startsWith('x402 ')) {
    throw new Error('Response is not an x402 payment requirement.');
  }
  const parts = raw.slice(5).match(/(\w+)="([^"]+)"/g) ?? [];
  const req: Record<string, string> = {};
  for (const part of parts) {
    const [k, v] = part.split('=');
    req[k] = v.replace(/"/g, '');
  }
  return req as unknown as PaymentRequirements;
}

/**
 * Build and sign an on-chain payment, return the base64 receipt.
 *
 * In production this uses the user's connected wallet (e.g. WalletConnect,
 * Coinbase Wallet SDK, or a locally held private key).
 *
 * For this MVP we show the structure — wallet integration is pluggable.
 */
export async function payForResource(
  headers: Record<string, string>,
): Promise<string> {
  const req = parsePaymentHeader(headers);

  if (DEV_MODE) {
    return _devModeReceipt(req);
  }

  // In production: use the x402 JS SDK to build the payment.
  // The SDK handles chain-specific transaction building and signing.
  //
  // import { createPayment } from '@coinbase/x402';
  // const payment = await createPayment(req, wallet);
  // return payment.toBase64();
  //
  // Until the SDK is published, throw a clear error.
  throw new Error(
    `Payment required: ${req.amount} ${req.token} on ${req.network} to ${req.recipient}.\n` +
    'Connect a wallet to pay and start mining.',
  );
}

/** Amount in human-readable USDC. */
export function formatAmount(microUnits: string): string {
  return `$${(parseInt(microUnits, 10) / 1_000_000).toFixed(4)} USDC`;
}

function _devModeReceipt(req: PaymentRequirements): string {
  const receipt = {
    txHash:    '0x' + '00'.repeat(32),
    amount:    req.amount,
    network:   req.network,
    timestamp: Math.floor(Date.now() / 1000),
    devMode:   true,
  };
  return btoa(JSON.stringify(receipt));
}

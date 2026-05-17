/**
 * Keypair management — sr25519 keys stored in the device secure enclave.
 *
 * Uses @polkadot/wasm-crypto (WebAssembly) so no native crypto binaries
 * are needed — works on Android (Pydroid-style constraint: no native builds).
 *
 * The private key NEVER leaves the device. All signing happens locally.
 * The public key (hotkey) is what gets shared with the cloud gateway.
 */

import * as SecureStore from 'expo-secure-store';
import { Keyring } from '@polkadot/keyring';
import { cryptoWaitReady, mnemonicGenerate, mnemonicToMiniSecret } from '@polkadot/util-crypto';
import { u8aToHex } from '@polkadot/util';

const MNEMONIC_KEY = 'engram_mnemonic';
const HOTKEY_KEY   = 'engram_hotkey';

export interface KeyPair {
  ss58:       string;   // SS58-encoded public key (starts with "5")
  publicHex:  string;   // raw hex public key (64 chars)
  mnemonic:   string;   // BIP39 mnemonic (never sent anywhere)
}

/** Initialise the WASM crypto backend — call once at app startup. */
export async function initCrypto(): Promise<void> {
  await cryptoWaitReady();
}

/** Generate a new sr25519 keypair and persist the mnemonic securely. */
export async function generateKeypair(): Promise<KeyPair> {
  await cryptoWaitReady();
  const mnemonic = mnemonicGenerate(12);
  const keyring  = new Keyring({ type: 'sr25519', ss58Format: 42 });
  const pair     = keyring.addFromMnemonic(mnemonic);

  await SecureStore.setItemAsync(MNEMONIC_KEY, mnemonic);
  await SecureStore.setItemAsync(HOTKEY_KEY,   pair.address);

  return {
    ss58:      pair.address,
    publicHex: u8aToHex(pair.publicKey).slice(2),  // strip 0x
    mnemonic,
  };
}

/** Load the stored keypair (returns null if none generated yet). */
export async function loadKeypair(): Promise<KeyPair | null> {
  const mnemonic = await SecureStore.getItemAsync(MNEMONIC_KEY);
  if (!mnemonic) return null;

  await cryptoWaitReady();
  const keyring = new Keyring({ type: 'sr25519', ss58Format: 42 });
  const pair    = keyring.addFromMnemonic(mnemonic);

  return {
    ss58:      pair.address,
    publicHex: u8aToHex(pair.publicKey).slice(2),
    mnemonic,
  };
}

/**
 * Sign a gateway auth message.
 * Message format: "engram-cloud:{METHOD}:{PATH}:{timestamp_ms}"
 * Returns hex-encoded sr25519 signature.
 */
export async function signGatewayRequest(
  mnemonic: string,
  method: string,
  path: string,
): Promise<{ hotkey: string; timestamp: string; sig: string }> {
  await cryptoWaitReady();
  const keyring   = new Keyring({ type: 'sr25519', ss58Format: 42 });
  const pair      = keyring.addFromMnemonic(mnemonic);
  const timestamp = Date.now().toString();
  const message   = `engram-cloud:${method}:${path}:${timestamp}`;
  const sig       = u8aToHex(pair.sign(message)).slice(2);

  return { hotkey: pair.address, timestamp, sig };
}

/** Wipe the keypair from secure storage (used on account reset). */
export async function deleteKeypair(): Promise<void> {
  await SecureStore.deleteItemAsync(MNEMONIC_KEY);
  await SecureStore.deleteItemAsync(HOTKEY_KEY);
}

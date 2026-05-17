/**
 * Engram Cloud Gateway client.
 *
 * All write endpoints require gateway auth headers (hotkey + sr25519 sig).
 * Read-only endpoints (tiers, health, metagraph) are unauthenticated.
 *
 * x402 payment: when the server returns 402, we build an on-chain payment
 * and retry with the X-Payment header. See payment.ts for the payment flow.
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import { signGatewayRequest } from './keystore';
import { payForResource } from './payment';

const GATEWAY_URL = process.env.EXPO_PUBLIC_GATEWAY_URL ?? 'https://gateway.engram.ai';

export interface Tier {
  tier:               string;
  cpu_vcpu:           number;
  memory_gb:          number;
  storage_gb:         number;
  price_akt_per_hour: number;
}

export interface Session {
  session_id:        string;
  controller_hotkey: string;
  status:            'provisioning' | 'active' | 'stopping' | 'stopped' | 'failed';
  created_at:        number;
  expires_at:        number;
  remaining_seconds: number;
  node_endpoint:     string | null;
  amount_paid_usd:   number;
  stats:             Record<string, unknown>;
  error:             string | null;
}

export interface StartSessionParams {
  tier:           string;
  duration_hours: number;
  mnemonic:       string;   // used for signing only, never sent
}

class GatewayClient {
  private http: AxiosInstance;

  constructor(baseURL: string = GATEWAY_URL) {
    this.http = axios.create({ baseURL, timeout: 15_000 });
  }

  // ── Public (no auth) ────────────────────────────────────────────────────────

  async getTiers(): Promise<Tier[]> {
    const res = await this.http.get('/tiers');
    return res.data.tiers;
  }

  async getHealth(): Promise<boolean> {
    try {
      await this.http.get('/health');
      return true;
    } catch {
      return false;
    }
  }

  async getMetagraph(netuid = 450): Promise<Record<string, unknown>> {
    const res = await this.http.get(`/bittensor/metagraph?netuid=${netuid}`);
    return res.data;
  }

  // ── Authenticated ────────────────────────────────────────────────────────────

  async startSession(params: StartSessionParams): Promise<Session> {
    const { mnemonic, tier, duration_hours } = params;
    const authHeaders = await this._authHeaders(mnemonic, 'POST', '/sessions');

    try {
      const res = await this.http.post('/sessions', { tier, duration_hours }, { headers: authHeaders });
      return res.data as Session;
    } catch (err) {
      const axiosErr = err as AxiosError;

      // x402 — server wants payment first
      if (axiosErr.response?.status === 402) {
        const headers402 = axiosErr.response.headers as Record<string, string>;
        const paymentHeader = await payForResource(headers402);

        const res = await this.http.post(
          '/sessions',
          { tier, duration_hours },
          { headers: { ...authHeaders, 'X-Payment': paymentHeader } },
        );
        return res.data as Session;
      }
      throw err;
    }
  }

  async getSession(sessionId: string, mnemonic: string): Promise<Session> {
    const path    = `/sessions/${sessionId}`;
    const headers = await this._authHeaders(mnemonic, 'GET', path);
    const res     = await this.http.get(path, { headers });
    return res.data as Session;
  }

  async stopSession(sessionId: string, mnemonic: string): Promise<void> {
    const path    = `/sessions/${sessionId}`;
    const headers = await this._authHeaders(mnemonic, 'DELETE', path);
    await this.http.delete(path, { headers });
  }

  async listSessions(hotkey: string, mnemonic: string): Promise<Session[]> {
    const path    = `/sessions/hotkey/${hotkey}`;
    const headers = await this._authHeaders(mnemonic, 'GET', path);
    const res     = await this.http.get(path, { headers });
    return res.data.sessions as Session[];
  }

  // ── Auth header builder ──────────────────────────────────────────────────────

  private async _authHeaders(
    mnemonic: string,
    method: string,
    path: string,
  ): Promise<Record<string, string>> {
    const { hotkey, timestamp, sig } = await signGatewayRequest(mnemonic, method, path);
    return {
      'X-Hotkey':    hotkey,
      'X-Timestamp': timestamp,
      'X-Sig':       sig,
    };
  }
}

export const gateway = new GatewayClient();

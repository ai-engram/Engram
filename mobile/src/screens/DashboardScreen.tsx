/**
 * Dashboard — shows active mining session stats.
 *
 * Polls the cloud gateway every 30 s for fresh stats from the live node.
 * Stats come from the miner's /stats endpoint: vectors stored, proof rate,
 * uptime, estimated earnings, block height.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { gateway, Session } from '../services/gateway';
import { loadKeypair } from '../services/keystore';
import AsyncStorage from '@react-native-async-storage/async-storage';

const POLL_INTERVAL_MS = 30_000;
const SESSION_ID_KEY   = 'active_session_id';

export default function DashboardScreen() {
  const insets = useSafeAreaInsets();
  const [session,     setSession]     = useState<Session | null>(null);
  const [loading,     setLoading]     = useState(true);
  const [refreshing,  setRefreshing]  = useState(false);
  const [mnemonic,    setMnemonic]    = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const kp = await loadKeypair();
      if (kp) setMnemonic(kp.mnemonic);
      await refresh();
    })();
  }, []);

  useEffect(() => {
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [mnemonic]);

  const refresh = useCallback(async () => {
    if (!mnemonic) return;
    const sessionId = await AsyncStorage.getItem(SESSION_ID_KEY);
    if (!sessionId) { setLoading(false); return; }
    try {
      const s = await gateway.getSession(sessionId, mnemonic);
      setSession(s);
    } catch {
      setSession(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [mnemonic]);

  const stopMining = useCallback(async () => {
    if (!session || !mnemonic) return;
    Alert.alert('Stop Mining?', 'Your remaining compute time will not be refunded.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Stop',
        style: 'destructive',
        onPress: async () => {
          await gateway.stopSession(session.session_id, mnemonic);
          await AsyncStorage.removeItem(SESSION_ID_KEY);
          setSession(null);
        },
      },
    ]);
  }, [session, mnemonic]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#7C3AED" />
      </View>
    );
  }

  if (!session) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <Text style={styles.emptyTitle}>No Active Session</Text>
        <Text style={styles.emptySubtitle}>
          Go to Start Mining to launch a cloud node on Akash Network.
        </Text>
      </View>
    );
  }

  const stats   = session.stats as Record<string, number | string>;
  const minutes = Math.floor(session.remaining_seconds / 60);
  const hours   = Math.floor(minutes / 60);
  const timeLeft = hours > 0 ? `${hours}h ${minutes % 60}m` : `${minutes}m`;

  return (
    <ScrollView
      style={[styles.container, { paddingTop: insets.top }]}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); refresh(); }} />}
    >
      {/* Status badge */}
      <View style={styles.header}>
        <View style={[styles.badge, session.status === 'active' ? styles.badgeActive : styles.badgePending]}>
          <Text style={styles.badgeText}>{session.status.toUpperCase()}</Text>
        </View>
        <Text style={styles.timeLeft}>{timeLeft} remaining</Text>
      </View>

      {/* Stats grid */}
      <View style={styles.grid}>
        <StatCard label="Vectors Stored"   value={String(stats.vectors    ?? '—')} />
        <StatCard label="Proof Rate"        value={stats.proof_rate != null ? `${(Number(stats.proof_rate) * 100).toFixed(1)}%` : '—'} />
        <StatCard label="Queries Today"    value={String(stats.queries_today ?? '—')} />
        <StatCard label="P50 Latency"      value={stats.p50_latency_ms != null ? `${stats.p50_latency_ms}ms` : '—'} />
        <StatCard label="Block"            value={String(stats.block      ?? '—')} />
        <StatCard label="Paid"             value={`$${session.amount_paid_usd.toFixed(4)}`} />
      </View>

      {/* Node info */}
      {session.node_endpoint && (
        <View style={styles.nodeBox}>
          <Text style={styles.nodeLabel}>Node Endpoint</Text>
          <Text style={styles.nodeValue}>{session.node_endpoint}</Text>
        </View>
      )}

      {/* Stop button */}
      <TouchableOpacity style={styles.stopBtn} onPress={stopMining}>
        <Text style={styles.stopBtnText}>Stop Mining</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardValue}>{value}</Text>
      <Text style={styles.cardLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container:     { flex: 1, backgroundColor: '#0F0F1A', padding: 16 },
  center:        { flex: 1, backgroundColor: '#0F0F1A', alignItems: 'center', justifyContent: 'center', padding: 32 },
  emptyTitle:    { color: '#fff', fontSize: 20, fontWeight: '700', marginBottom: 8 },
  emptySubtitle: { color: '#888', fontSize: 14, textAlign: 'center' },
  header:        { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 },
  badge:         { borderRadius: 6, paddingHorizontal: 10, paddingVertical: 4 },
  badgeActive:   { backgroundColor: '#065F46' },
  badgePending:  { backgroundColor: '#44403C' },
  badgeText:     { color: '#fff', fontSize: 12, fontWeight: '700', letterSpacing: 1 },
  timeLeft:      { color: '#A78BFA', fontSize: 14, fontWeight: '600' },
  grid:          { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 },
  card:          { backgroundColor: '#1C1C2E', borderRadius: 12, padding: 16, width: '47%', alignItems: 'center' },
  cardValue:     { color: '#fff', fontSize: 22, fontWeight: '800', marginBottom: 4 },
  cardLabel:     { color: '#888', fontSize: 11, textAlign: 'center' },
  nodeBox:       { backgroundColor: '#1C1C2E', borderRadius: 12, padding: 16, marginBottom: 20 },
  nodeLabel:     { color: '#888', fontSize: 11, marginBottom: 4 },
  nodeValue:     { color: '#A78BFA', fontSize: 12, fontFamily: 'monospace' },
  stopBtn:       { backgroundColor: '#7F1D1D', borderRadius: 12, padding: 16, alignItems: 'center', marginBottom: 32 },
  stopBtnText:   { color: '#fff', fontSize: 16, fontWeight: '700' },
});

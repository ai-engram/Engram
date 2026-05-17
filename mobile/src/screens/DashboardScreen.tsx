import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Animated,
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

const POLL_MS = 30_000;
const SESSION_KEY = 'active_session_id';

function PulseDot({ active }: { active: boolean }) {
  const opacity = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    if (!active) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.2, duration: 900, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1, duration: 900, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [active]);
  return (
    <Animated.View style={[styles.dot, { backgroundColor: active ? '#22c55e' : '#374151', opacity: active ? opacity : 1 }]} />
  );
}

function StatCard({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <View style={styles.statCard}>
      <Text style={[styles.statValue, accent && styles.statValueAccent]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function ScoreBar({ value }: { value: number }) {
  const pct = Math.min(100, value * 100);
  const color = pct > 80 ? '#a855f7' : pct > 50 ? '#f59e0b' : '#ef4444';
  return (
    <View style={styles.barTrack}>
      <View style={[styles.barFill, { width: `${pct}%` as any, backgroundColor: color }]} />
    </View>
  );
}

export default function DashboardScreen() {
  const insets = useSafeAreaInsets();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [mnemonic, setMnemonic] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  useEffect(() => {
    (async () => {
      const kp = await loadKeypair();
      if (kp) setMnemonic(kp.mnemonic);
    })();
  }, []);

  const refresh = useCallback(async (manual = false) => {
    if (!mnemonic) { setLoading(false); return; }
    if (manual) setRefreshing(true);
    const sessionId = await AsyncStorage.getItem(SESSION_KEY);
    if (!sessionId) { setLoading(false); setRefreshing(false); return; }
    try {
      const s = await gateway.getSession(sessionId, mnemonic);
      setSession(s);
      setLastUpdate(new Date());
    } catch {
      setSession(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [mnemonic]);

  useEffect(() => {
    refresh();
    const id = setInterval(() => refresh(), POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const stop = useCallback(() => {
    if (!session || !mnemonic) return;
    Alert.alert('Stop Mining?', 'Remaining compute time is non-refundable.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Stop', style: 'destructive',
        onPress: async () => {
          await gateway.stopSession(session.session_id, mnemonic);
          await AsyncStorage.removeItem(SESSION_KEY);
          setSession(null);
        },
      },
    ]);
  }, [session, mnemonic]);

  if (loading) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <Text style={styles.loadingText}>Connecting…</Text>
        <View style={styles.dotRow}>
          {[0, 150, 300].map(delay => <LoadingDot key={delay} delay={delay} />)}
        </View>
      </View>
    );
  }

  if (!session) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <View style={styles.emptyIcon}>
          <Text style={styles.emptyEmoji}>⛏</Text>
        </View>
        <Text style={styles.emptyTitle}>No Active Session</Text>
        <Text style={styles.emptySub}>Start a cloud miner from the{'\n'}Start Mining tab.</Text>
      </View>
    );
  }

  const stats = session.stats as Record<string, number | string>;
  const secs = session.remaining_seconds;
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const timeLeft = h > 0 ? `${h}h ${m}m` : `${m}m`;
  const isActive = session.status === 'active';
  const proofRate = stats.proof_rate != null ? Number(stats.proof_rate) : null;
  const updated = lastUpdate
    ? lastUpdate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '—';

  return (
    <ScrollView
      style={[styles.container, { paddingTop: insets.top }]}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => refresh(true)} tintColor="#7c3aed" />}
      showsVerticalScrollIndicator={false}
    >
      {/* Header card */}
      <View style={styles.headerCard}>
        <View style={styles.headerRow}>
          <View style={styles.statusPill}>
            <PulseDot active={isActive} />
            <Text style={[styles.statusText, { color: isActive ? '#22c55e' : '#9ca3af' }]}>
              {session.status.toUpperCase()}
            </Text>
          </View>
          <Text style={styles.timeLeft}>{timeLeft} left</Text>
        </View>

        {/* Score bar */}
        {proofRate !== null && (
          <View style={styles.scoreSection}>
            <View style={styles.scoreHeader}>
              <Text style={styles.scoreLabel}>Proof Rate</Text>
              <Text style={styles.scoreValue}>{(proofRate * 100).toFixed(1)}%</Text>
            </View>
            <ScoreBar value={proofRate} />
          </View>
        )}

        <Text style={styles.updatedAt}>Updated {updated}</Text>
      </View>

      {/* Stats grid */}
      <View style={styles.grid}>
        <StatCard label="Vectors" value={String(stats.vectors ?? '—')} accent />
        <StatCard label="Queries Today" value={String(stats.queries_today ?? '—')} />
        <StatCard label="P50 Latency" value={stats.p50_latency_ms != null ? `${stats.p50_latency_ms}ms` : '—'} />
        <StatCard label="Block" value={String(stats.block ?? '—')} />
        <StatCard label="Paid" value={`$${session.amount_paid_usd.toFixed(2)}`} />
        <StatCard label="Score" value={stats.avg_score != null ? Number(stats.avg_score).toFixed(3) : '—'} accent />
      </View>

      {/* Node endpoint */}
      {session.node_endpoint && (
        <View style={styles.nodeCard}>
          <Text style={styles.nodeLabel}>Node Endpoint</Text>
          <Text style={styles.nodeValue} selectable>{session.node_endpoint}</Text>
        </View>
      )}

      {/* Stop button */}
      <TouchableOpacity style={styles.stopBtn} onPress={stop} activeOpacity={0.8}>
        <Text style={styles.stopBtnText}>Stop Mining</Text>
      </TouchableOpacity>

      <Text style={styles.footnote}>Pull down to refresh · auto-updates every 30s</Text>
    </ScrollView>
  );
}

function LoadingDot({ delay }: { delay: number }) {
  const scale = useRef(new Animated.Value(0.5)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.delay(delay),
        Animated.timing(scale, { toValue: 1, duration: 400, useNativeDriver: true }),
        Animated.timing(scale, { toValue: 0.5, duration: 400, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, []);
  return <Animated.View style={[styles.loadDot, { transform: [{ scale }] }]} />;
}

const styles = StyleSheet.create({
  container:       { flex: 1, backgroundColor: '#09090f', paddingHorizontal: 16 },
  center:          { flex: 1, backgroundColor: '#09090f', alignItems: 'center', justifyContent: 'center', padding: 32 },
  loadingText:     { color: '#6b7280', fontSize: 14, fontWeight: '500', marginBottom: 16 },
  dotRow:          { flexDirection: 'row', gap: 8 },
  loadDot:         { width: 8, height: 8, borderRadius: 4, backgroundColor: '#7c3aed' },
  emptyIcon:       { width: 72, height: 72, borderRadius: 36, backgroundColor: '#1c1c2e', alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  emptyEmoji:      { fontSize: 32 },
  emptyTitle:      { color: '#fff', fontSize: 20, fontWeight: '700', marginBottom: 8 },
  emptySub:        { color: '#6b7280', fontSize: 14, textAlign: 'center', lineHeight: 20 },
  headerCard:      { backgroundColor: '#13131f', borderRadius: 16, padding: 20, marginTop: 16, marginBottom: 12, borderWidth: 1, borderColor: 'rgba(255,255,255,0.06)' },
  headerRow:       { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 },
  statusPill:      { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 6 },
  dot:             { width: 7, height: 7, borderRadius: 4 },
  statusText:      { fontSize: 11, fontWeight: '700', letterSpacing: 1 },
  timeLeft:        { color: '#a78bfa', fontSize: 15, fontWeight: '700' },
  scoreSection:    { marginBottom: 12 },
  scoreHeader:     { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  scoreLabel:      { color: '#6b7280', fontSize: 12, fontWeight: '500' },
  scoreValue:      { color: '#fff', fontSize: 12, fontWeight: '700' },
  barTrack:        { height: 4, backgroundColor: 'rgba(255,255,255,0.07)', borderRadius: 2, overflow: 'hidden' },
  barFill:         { height: 4, borderRadius: 2 },
  updatedAt:       { color: '#374151', fontSize: 11, textAlign: 'right' },
  grid:            { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 12 },
  statCard:        { backgroundColor: '#13131f', borderRadius: 14, padding: 16, width: '47.5%', borderWidth: 1, borderColor: 'rgba(255,255,255,0.05)' },
  statValue:       { color: '#e5e7eb', fontSize: 22, fontWeight: '800', marginBottom: 4, letterSpacing: -0.5 },
  statValueAccent: { color: '#a78bfa' },
  statLabel:       { color: '#6b7280', fontSize: 11 },
  nodeCard:        { backgroundColor: '#13131f', borderRadius: 14, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: 'rgba(255,255,255,0.05)' },
  nodeLabel:       { color: '#6b7280', fontSize: 11, fontWeight: '600', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 },
  nodeValue:       { color: '#a78bfa', fontSize: 12, fontFamily: 'monospace' },
  stopBtn:         { backgroundColor: '#1a0707', borderRadius: 14, padding: 18, alignItems: 'center', marginBottom: 12, borderWidth: 1, borderColor: 'rgba(239,68,68,0.3)' },
  stopBtnText:     { color: '#ef4444', fontSize: 15, fontWeight: '700' },
  footnote:        { color: '#374151', fontSize: 11, textAlign: 'center', marginBottom: 40 },
});

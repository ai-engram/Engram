import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { gateway, Tier } from '../services/gateway';
import { loadKeypair } from '../services/keystore';

const SESSION_KEY = 'active_session_id';

const DURATIONS = [
  { label: '1h',   hours: 1 },
  { label: '6h',   hours: 6 },
  { label: '24h',  hours: 24 },
  { label: '7d',   hours: 168 },
];

const TIER_ICONS: Record<string, string> = {
  lite: '🌱',
  standard: '⚡',
  pro: '🚀',
};

export default function StartMiningScreen({ navigation }: any) {
  const insets = useSafeAreaInsets();
  const [tiers, setTiers] = useState<Tier[]>([]);
  const [selTier, setSelTier] = useState('standard');
  const [selHours, setSelHours] = useState(24);
  const [loading, setLoading] = useState(false);
  const [fetchingTiers, setFetchingTiers] = useState(true);

  useEffect(() => {
    gateway.getTiers()
      .then(t => { setTiers(t); setFetchingTiers(false); })
      .catch(() => setFetchingTiers(false));
  }, []);

  const activeTier = tiers.find(t => t.tier === selTier);
  const totalUSD = activeTier ? (activeTier.price_akt_per_hour * selHours * 2).toFixed(2) : '0.00';

  const start = async () => {
    const kp = await loadKeypair();
    if (!kp) {
      Alert.alert('No Wallet', 'Generate a wallet in the Wallet tab first.');
      return;
    }
    const existing = await AsyncStorage.getItem(SESSION_KEY);
    if (existing) {
      Alert.alert('Session Active', 'Stop the current session before starting a new one.');
      return;
    }
    setLoading(true);
    try {
      const session = await gateway.startSession({ tier: selTier, duration_hours: selHours, mnemonic: kp.mnemonic });
      await AsyncStorage.setItem(SESSION_KEY, session.session_id);
      Alert.alert(
        'Mining Started',
        `Your node is provisioning on Akash Network.\n\nTypically ready in ~3 minutes.`,
        [{ text: 'View Dashboard', onPress: () => navigation.navigate('Dashboard') }],
      );
    } catch (err: any) {
      Alert.alert('Failed', err?.response?.data?.error ?? err?.message ?? 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  if (fetchingTiers) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color="#7c3aed" />
        <Text style={styles.loadingText}>Loading compute tiers…</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={[styles.container, { paddingTop: insets.top }]}
      showsVerticalScrollIndicator={false}
      contentContainerStyle={{ paddingBottom: 48 }}
    >
      {/* Header */}
      <View style={styles.headerSection}>
        <Text style={styles.title}>Start Mining</Text>
        <Text style={styles.subtitle}>Deploy a managed miner on Akash Network. Pay per hour with USDC on Base.</Text>
      </View>

      {/* Tier picker */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>Compute Tier</Text>
        <View style={styles.tierList}>
          {tiers.map(tier => {
            const active = selTier === tier.tier;
            return (
              <TouchableOpacity
                key={tier.tier}
                style={[styles.tierCard, active && styles.tierCardActive]}
                onPress={() => setSelTier(tier.tier)}
                activeOpacity={0.8}
              >
                <View style={styles.tierLeft}>
                  <Text style={styles.tierIcon}>{TIER_ICONS[tier.tier] ?? '⚙️'}</Text>
                  <View>
                    <Text style={[styles.tierName, active && styles.tierNameActive]}>
                      {tier.tier.charAt(0).toUpperCase() + tier.tier.slice(1)}
                    </Text>
                    <Text style={styles.tierSpec}>{tier.cpu_vcpu} vCPU · {tier.memory_gb} GB · {tier.storage_gb} GB disk</Text>
                  </View>
                </View>
                <View style={styles.tierRight}>
                  <Text style={[styles.tierPrice, active && styles.tierPriceActive]}>
                    {tier.price_akt_per_hour} AKT
                  </Text>
                  <Text style={styles.tierPriceUnit}>per hour</Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      {/* Duration */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>Duration</Text>
        <View style={styles.durationRow}>
          {DURATIONS.map(d => (
            <TouchableOpacity
              key={d.hours}
              style={[styles.durBtn, selHours === d.hours && styles.durBtnActive]}
              onPress={() => setSelHours(d.hours)}
              activeOpacity={0.8}
            >
              <Text style={[styles.durText, selHours === d.hours && styles.durTextActive]}>{d.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Summary */}
      <View style={styles.summaryCard}>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryKey}>Tier</Text>
          <Text style={styles.summaryVal}>{selTier.charAt(0).toUpperCase() + selTier.slice(1)}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryKey}>Duration</Text>
          <Text style={styles.summaryVal}>{selHours < 24 ? `${selHours}h` : `${selHours / 24}d`}</Text>
        </View>
        <View style={[styles.summaryRow, { borderBottomWidth: 0, paddingBottom: 0 }]}>
          <Text style={styles.summaryKey}>Total (approx)</Text>
          <Text style={styles.totalAmt}>${totalUSD} USDC</Text>
        </View>
        <Text style={styles.summaryNote}>via Dexter Cash · Base network · no account required</Text>
      </View>

      {/* CTA */}
      <TouchableOpacity
        style={[styles.payBtn, loading && styles.payBtnDisabled]}
        onPress={start}
        disabled={loading}
        activeOpacity={0.85}
      >
        {loading
          ? <ActivityIndicator color="#fff" />
          : <>
              <Text style={styles.payBtnText}>Pay & Start Mining</Text>
              <Text style={styles.payBtnSub}>${totalUSD} USDC · {selHours < 24 ? `${selHours}h` : `${selHours / 24}d`}</Text>
            </>
        }
      </TouchableOpacity>

      {/* Trust badges */}
      <View style={styles.trustRow}>
        {['🔐 Key stays on device', '⛓ On-chain payment', '🌐 Akash Network'].map(b => (
          <View key={b} style={styles.trustBadge}>
            <Text style={styles.trustText}>{b}</Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container:        { flex: 1, backgroundColor: '#09090f' },
  center:           { flex: 1, backgroundColor: '#09090f', alignItems: 'center', justifyContent: 'center' },
  loadingText:      { color: '#6b7280', fontSize: 14, marginTop: 12 },
  headerSection:    { paddingHorizontal: 20, paddingTop: 24, paddingBottom: 8 },
  title:            { color: '#fff', fontSize: 26, fontWeight: '800', letterSpacing: -0.5, marginBottom: 6 },
  subtitle:         { color: '#6b7280', fontSize: 14, lineHeight: 20 },
  section:          { paddingHorizontal: 16, marginTop: 24 },
  sectionLabel:     { color: '#9ca3af', fontSize: 11, fontWeight: '700', letterSpacing: 1.2, textTransform: 'uppercase', marginBottom: 10 },
  tierList:         { gap: 8 },
  tierCard:         { backgroundColor: '#13131f', borderRadius: 14, padding: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.05)' },
  tierCardActive:   { borderColor: '#7c3aed', backgroundColor: '#150d26' },
  tierLeft:         { flexDirection: 'row', alignItems: 'center', gap: 12 },
  tierIcon:         { fontSize: 24 },
  tierName:         { color: '#9ca3af', fontSize: 15, fontWeight: '700', marginBottom: 2 },
  tierNameActive:   { color: '#fff' },
  tierSpec:         { color: '#4b5563', fontSize: 12 },
  tierRight:        { alignItems: 'flex-end' },
  tierPrice:        { color: '#6b7280', fontSize: 14, fontWeight: '700' },
  tierPriceActive:  { color: '#a78bfa' },
  tierPriceUnit:    { color: '#374151', fontSize: 11 },
  durationRow:      { flexDirection: 'row', gap: 8 },
  durBtn:           { flex: 1, backgroundColor: '#13131f', borderRadius: 10, paddingVertical: 12, alignItems: 'center', borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.05)' },
  durBtnActive:     { borderColor: '#7c3aed', backgroundColor: '#150d26' },
  durText:          { color: '#6b7280', fontSize: 13, fontWeight: '600' },
  durTextActive:    { color: '#fff' },
  summaryCard:      { marginHorizontal: 16, marginTop: 24, backgroundColor: '#13131f', borderRadius: 16, padding: 20, borderWidth: 1, borderColor: 'rgba(255,255,255,0.06)' },
  summaryRow:       { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingBottom: 12, marginBottom: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
  summaryKey:       { color: '#6b7280', fontSize: 13 },
  summaryVal:       { color: '#e5e7eb', fontSize: 13, fontWeight: '600' },
  totalAmt:         { color: '#a78bfa', fontSize: 20, fontWeight: '800' },
  summaryNote:      { color: '#374151', fontSize: 11, textAlign: 'center', marginTop: 10 },
  payBtn:           { marginHorizontal: 16, marginTop: 20, backgroundColor: '#7c3aed', borderRadius: 16, paddingVertical: 18, alignItems: 'center' },
  payBtnDisabled:   { opacity: 0.5 },
  payBtnText:       { color: '#fff', fontSize: 16, fontWeight: '800' },
  payBtnSub:        { color: 'rgba(255,255,255,0.5)', fontSize: 12, marginTop: 2 },
  trustRow:         { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginHorizontal: 16, marginTop: 16, justifyContent: 'center' },
  trustBadge:       { backgroundColor: '#13131f', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 6 },
  trustText:        { color: '#6b7280', fontSize: 11 },
});

/**
 * Start Mining — configure and launch a cloud node on Akash Network.
 *
 * User picks a tier, duration, then pays via x402 (Dexter Cash).
 * On success, the session ID is stored locally and the dashboard shows stats.
 */

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

const SESSION_ID_KEY = 'active_session_id';

const DURATION_OPTIONS = [
  { label: '1 hour',   hours: 1 },
  { label: '6 hours',  hours: 6 },
  { label: '24 hours', hours: 24 },
  { label: '7 days',   hours: 168 },
];

export default function StartMiningScreen({ navigation }: any) {
  const insets            = useSafeAreaInsets();
  const [tiers,     setTiers]     = useState<Tier[]>([]);
  const [selTier,   setSelTier]   = useState<string>('standard');
  const [selHours,  setSelHours]  = useState<number>(24);
  const [loading,   setLoading]   = useState(false);
  const [loadingTiers, setLoadingTiers] = useState(true);

  useEffect(() => {
    gateway.getTiers().then(t => { setTiers(t); setLoadingTiers(false); }).catch(() => setLoadingTiers(false));
  }, []);

  const totalUSD = (() => {
    const tier = tiers.find(t => t.tier === selTier);
    if (!tier) return 0;
    // Convert AKT/hr to approximate USD (1 AKT ≈ $2 — use live price in production)
    return (tier.price_akt_per_hour * selHours * 2).toFixed(4);
  })();

  const startMining = async () => {
    const kp = await loadKeypair();
    if (!kp) {
      Alert.alert('No Wallet', 'Create a wallet in the Wallet tab first.');
      return;
    }

    const existing = await AsyncStorage.getItem(SESSION_ID_KEY);
    if (existing) {
      Alert.alert('Session Active', 'You already have an active mining session. Stop it first.');
      return;
    }

    setLoading(true);
    try {
      const session = await gateway.startSession({
        tier:           selTier,
        duration_hours: selHours,
        mnemonic:       kp.mnemonic,
      });
      await AsyncStorage.setItem(SESSION_ID_KEY, session.session_id);
      Alert.alert(
        'Mining Started!',
        `Your node is provisioning on Akash Network.\nSession ID: ${session.session_id.slice(0, 8)}…\n\nIt will be active within ~3 minutes.`,
        [{ text: 'View Dashboard', onPress: () => navigation.navigate('Dashboard') }],
      );
    } catch (err: any) {
      const msg = err?.response?.data?.error ?? err?.message ?? 'Unknown error';
      Alert.alert('Failed to Start', msg);
    } finally {
      setLoading(false);
    }
  };

  if (loadingTiers) {
    return <View style={styles.center}><ActivityIndicator size="large" color="#7C3AED" /></View>;
  }

  return (
    <ScrollView style={[styles.container, { paddingTop: insets.top }]}>
      <Text style={styles.title}>Start Mining</Text>
      <Text style={styles.subtitle}>
        Your node runs on Akash Network — decentralised cloud, paid per hour.
      </Text>

      {/* Tier picker */}
      <Text style={styles.sectionLabel}>Compute Tier</Text>
      {tiers.map(tier => (
        <TouchableOpacity
          key={tier.tier}
          style={[styles.option, selTier === tier.tier && styles.optionSelected]}
          onPress={() => setSelTier(tier.tier)}
        >
          <View>
            <Text style={styles.optionTitle}>{tier.tier.charAt(0).toUpperCase() + tier.tier.slice(1)}</Text>
            <Text style={styles.optionDetail}>
              {tier.cpu_vcpu} vCPU · {tier.memory_gb} GB RAM · {tier.storage_gb} GB disk
            </Text>
          </View>
          <Text style={styles.optionPrice}>{tier.price_akt_per_hour} AKT/hr</Text>
        </TouchableOpacity>
      ))}

      {/* Duration picker */}
      <Text style={styles.sectionLabel}>Duration</Text>
      <View style={styles.durationRow}>
        {DURATION_OPTIONS.map(d => (
          <TouchableOpacity
            key={d.hours}
            style={[styles.durationBtn, selHours === d.hours && styles.durationBtnSelected]}
            onPress={() => setSelHours(d.hours)}
          >
            <Text style={[styles.durationText, selHours === d.hours && styles.durationTextSelected]}>
              {d.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Total */}
      <View style={styles.totalBox}>
        <Text style={styles.totalLabel}>Total (approx)</Text>
        <Text style={styles.totalValue}>${totalUSD} USDC</Text>
        <Text style={styles.totalNote}>Paid on-chain via Dexter (x402) · Base network</Text>
      </View>

      {/* CTA */}
      <TouchableOpacity
        style={[styles.startBtn, loading && styles.startBtnDisabled]}
        onPress={startMining}
        disabled={loading}
      >
        {loading
          ? <ActivityIndicator color="#fff" />
          : <Text style={styles.startBtnText}>Pay & Start Mining</Text>
        }
      </TouchableOpacity>

      <Text style={styles.footnote}>
        Nodes provision in ~3 minutes after payment. Compute runs on Akash Network providers worldwide.
        Your private key never leaves your phone.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container:           { flex: 1, backgroundColor: '#0F0F1A', padding: 16 },
  center:              { flex: 1, backgroundColor: '#0F0F1A', alignItems: 'center', justifyContent: 'center' },
  title:               { color: '#fff', fontSize: 24, fontWeight: '800', marginBottom: 8 },
  subtitle:            { color: '#888', fontSize: 14, marginBottom: 24, lineHeight: 20 },
  sectionLabel:        { color: '#888', fontSize: 12, fontWeight: '600', letterSpacing: 1, marginBottom: 10, textTransform: 'uppercase' },
  option:              { backgroundColor: '#1C1C2E', borderRadius: 12, padding: 16, marginBottom: 10, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderWidth: 1, borderColor: 'transparent' },
  optionSelected:      { borderColor: '#7C3AED' },
  optionTitle:         { color: '#fff', fontSize: 16, fontWeight: '700' },
  optionDetail:        { color: '#888', fontSize: 12, marginTop: 2 },
  optionPrice:         { color: '#A78BFA', fontSize: 14, fontWeight: '700' },
  durationRow:         { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 24 },
  durationBtn:         { backgroundColor: '#1C1C2E', borderRadius: 8, paddingHorizontal: 14, paddingVertical: 10, borderWidth: 1, borderColor: 'transparent' },
  durationBtnSelected: { borderColor: '#7C3AED' },
  durationText:        { color: '#888', fontSize: 13 },
  durationTextSelected:{ color: '#fff', fontWeight: '700' },
  totalBox:            { backgroundColor: '#1C1C2E', borderRadius: 12, padding: 16, marginBottom: 24, alignItems: 'center' },
  totalLabel:          { color: '#888', fontSize: 12, marginBottom: 4 },
  totalValue:          { color: '#fff', fontSize: 28, fontWeight: '800', marginBottom: 4 },
  totalNote:           { color: '#888', fontSize: 11 },
  startBtn:            { backgroundColor: '#7C3AED', borderRadius: 12, padding: 18, alignItems: 'center', marginBottom: 16 },
  startBtnDisabled:    { opacity: 0.5 },
  startBtnText:        { color: '#fff', fontSize: 16, fontWeight: '800' },
  footnote:            { color: '#555', fontSize: 12, textAlign: 'center', lineHeight: 18, marginBottom: 40 },
});

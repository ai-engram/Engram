/**
 * Wallet — sr25519 keypair management.
 *
 * Private key stays in the device secure enclave (Expo SecureStore).
 * The public key (hotkey) is what gets registered on Bittensor via the cloud node.
 *
 * We also show raw Bittensor metagraph data fetched via direct Substrate JSON-RPC
 * — no SDK, no native deps. Pure HTTPS.
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
import { generateKeypair, loadKeypair, deleteKeypair, KeyPair } from '../services/keystore';
import { gateway } from '../services/gateway';

export default function WalletScreen() {
  const insets = useSafeAreaInsets();
  const [keypair,    setKeypair]    = useState<KeyPair | null>(null);
  const [metagraph,  setMetagraph]  = useState<Record<string, unknown> | null>(null);
  const [generating, setGenerating] = useState(false);
  const [loading,    setLoading]    = useState(true);

  useEffect(() => {
    (async () => {
      const kp = await loadKeypair();
      setKeypair(kp);
      setLoading(false);
      if (kp) fetchMetagraph();
    })();
  }, []);

  const fetchMetagraph = async () => {
    try {
      const data = await gateway.getMetagraph(450);
      setMetagraph(data);
    } catch {
      // non-critical
    }
  };

  const createWallet = async () => {
    setGenerating(true);
    try {
      const kp = await generateKeypair();
      setKeypair(kp);
      fetchMetagraph();
      Alert.alert(
        'Wallet Created',
        'Your 12-word recovery phrase is shown below. Write it down — it cannot be recovered if lost.',
      );
    } finally {
      setGenerating(false);
    }
  };

  const resetWallet = () => {
    Alert.alert(
      'Delete Wallet?',
      'This will permanently delete your keys from this device. Make sure you have your recovery phrase.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            await deleteKeypair();
            setKeypair(null);
            setMetagraph(null);
          },
        },
      ],
    );
  };

  if (loading) {
    return <View style={styles.center}><ActivityIndicator size="large" color="#7C3AED" /></View>;
  }

  if (!keypair) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <Text style={styles.bigTitle}>Engram Wallet</Text>
        <Text style={styles.subtitle}>
          Your sr25519 mining keypair lives only on this device. It signs gateway requests and identifies your Bittensor miner.
        </Text>
        <TouchableOpacity style={styles.createBtn} onPress={createWallet} disabled={generating}>
          {generating
            ? <ActivityIndicator color="#fff" />
            : <Text style={styles.createBtnText}>Generate Keypair</Text>}
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <ScrollView style={[styles.container, { paddingTop: insets.top }]}>
      <Text style={styles.title}>Your Wallet</Text>

      {/* Hotkey */}
      <View style={styles.card}>
        <Text style={styles.cardLabel}>Hotkey (Public · Safe to share)</Text>
        <Text style={styles.mono} selectable>{keypair.ss58}</Text>
        <Text style={[styles.mono, { fontSize: 10, color: '#666', marginTop: 4 }]} selectable>
          0x{keypair.publicHex}
        </Text>
      </View>

      {/* Recovery phrase */}
      <View style={[styles.card, { borderColor: '#7F1D1D', borderWidth: 1 }]}>
        <Text style={styles.cardLabel}>Recovery Phrase · PRIVATE — do not share</Text>
        <View style={styles.phraseGrid}>
          {keypair.mnemonic.split(' ').map((word, i) => (
            <View key={i} style={styles.wordChip}>
              <Text style={styles.wordNum}>{i + 1}</Text>
              <Text style={styles.wordText}>{word}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Subnet info from raw JSON-RPC */}
      {metagraph && (
        <View style={styles.card}>
          <Text style={styles.cardLabel}>Bittensor Subnet 450 (raw JSON-RPC)</Text>
          <Text style={styles.infoRow}>Network: <Text style={styles.infoVal}>{String(metagraph.network)}</Text></Text>
          <Text style={styles.infoRow}>Block: <Text style={styles.infoVal}>{String(metagraph.block)}</Text></Text>
          <Text style={styles.infoRow}>NetUID: <Text style={styles.infoVal}>{String(metagraph.netuid)}</Text></Text>
        </View>
      )}

      <TouchableOpacity style={styles.deleteBtn} onPress={resetWallet}>
        <Text style={styles.deleteBtnText}>Delete Wallet from Device</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: '#0F0F1A', padding: 16 },
  center:       { flex: 1, backgroundColor: '#0F0F1A', alignItems: 'center', justifyContent: 'center', padding: 32 },
  bigTitle:     { color: '#fff', fontSize: 28, fontWeight: '800', marginBottom: 12 },
  title:        { color: '#fff', fontSize: 24, fontWeight: '800', marginBottom: 20 },
  subtitle:     { color: '#888', fontSize: 14, textAlign: 'center', lineHeight: 20, marginBottom: 32 },
  createBtn:    { backgroundColor: '#7C3AED', borderRadius: 12, paddingHorizontal: 32, paddingVertical: 16 },
  createBtnText:{ color: '#fff', fontSize: 16, fontWeight: '800' },
  card:         { backgroundColor: '#1C1C2E', borderRadius: 12, padding: 16, marginBottom: 16 },
  cardLabel:    { color: '#888', fontSize: 11, fontWeight: '600', letterSpacing: 0.5, marginBottom: 8, textTransform: 'uppercase' },
  mono:         { color: '#A78BFA', fontSize: 12, fontFamily: 'monospace' },
  phraseGrid:   { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  wordChip:     { backgroundColor: '#0F0F1A', borderRadius: 6, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', alignItems: 'center', gap: 4 },
  wordNum:      { color: '#555', fontSize: 11 },
  wordText:     { color: '#fff', fontSize: 13, fontWeight: '600' },
  infoRow:      { color: '#888', fontSize: 13, marginBottom: 4 },
  infoVal:      { color: '#fff', fontWeight: '600' },
  deleteBtn:    { backgroundColor: '#1C1C2E', borderRadius: 12, padding: 16, alignItems: 'center', marginBottom: 40, borderWidth: 1, borderColor: '#7F1D1D' },
  deleteBtnText:{ color: '#EF4444', fontSize: 14, fontWeight: '600' },
});

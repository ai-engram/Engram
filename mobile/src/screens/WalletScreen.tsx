import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Clipboard,
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
  const [keypair, setKeypair] = useState<KeyPair | null>(null);
  const [metagraph, setMetagraph] = useState<Record<string, unknown> | null>(null);
  const [generating, setGenerating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [phraseVisible, setPhraseVisible] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    (async () => {
      const kp = await loadKeypair();
      setKeypair(kp);
      setLoading(false);
      if (kp) fetchMeta();
    })();
  }, []);

  const fetchMeta = async () => {
    try {
      const data = await gateway.getMetagraph(450);
      setMetagraph(data);
    } catch {}
  };

  const create = async () => {
    setGenerating(true);
    try {
      const kp = await generateKeypair();
      setKeypair(kp);
      setPhraseVisible(true);
      fetchMeta();
    } finally {
      setGenerating(false);
    }
  };

  const copy = (text: string, label: string) => {
    Clipboard.setString(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const del = () => {
    Alert.alert(
      'Delete Wallet?',
      'Your keys will be permanently removed from this device. Only do this if you have saved your recovery phrase.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete', style: 'destructive',
          onPress: async () => { await deleteKeypair(); setKeypair(null); setMetagraph(null); },
        },
      ]
    );
  };

  if (loading) {
    return <View style={[styles.center, { paddingTop: insets.top }]}><ActivityIndicator size="large" color="#7c3aed" /></View>;
  }

  if (!keypair) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <View style={styles.logoCircle}>
          <Text style={styles.logoEmoji}>⛓</Text>
        </View>
        <Text style={styles.createTitle}>Engram Wallet</Text>
        <Text style={styles.createSub}>
          Your sr25519 keypair lives only on this device — in the secure enclave.
          It identifies your miner and signs all gateway requests.
        </Text>
        <TouchableOpacity style={styles.createBtn} onPress={create} disabled={generating} activeOpacity={0.85}>
          {generating
            ? <ActivityIndicator color="#fff" />
            : <Text style={styles.createBtnText}>Generate Keypair</Text>}
        </TouchableOpacity>
        <Text style={styles.createNote}>Your private key never leaves this device.</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={[styles.container, { paddingTop: insets.top }]}
      showsVerticalScrollIndicator={false}
      contentContainerStyle={{ paddingBottom: 48 }}
    >
      <View style={styles.headerSection}>
        <Text style={styles.title}>Your Wallet</Text>
        {metagraph && (
          <View style={styles.networkPill}>
            <View style={styles.networkDot} />
            <Text style={styles.networkText}>Subnet 450 · Block {String(metagraph.block)}</Text>
          </View>
        )}
      </View>

      {/* Public key */}
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.cardLabel}>Hotkey · Public Key</Text>
          <TouchableOpacity onPress={() => copy(keypair.ss58, 'Hotkey')} style={styles.copyBtn}>
            <Text style={styles.copyText}>{copied ? 'Copied!' : 'Copy'}</Text>
          </TouchableOpacity>
        </View>
        <Text style={styles.monoLg} selectable>{keypair.ss58}</Text>
        <Text style={styles.monoSm} selectable>0x{keypair.publicHex}</Text>
        <View style={styles.safeBadge}>
          <Text style={styles.safeText}>Safe to share</Text>
        </View>
      </View>

      {/* Recovery phrase */}
      <View style={[styles.card, styles.cardDanger]}>
        <View style={styles.cardHeader}>
          <Text style={styles.cardLabel}>Recovery Phrase</Text>
          <TouchableOpacity onPress={() => setPhraseVisible(v => !v)} style={styles.revealBtn}>
            <Text style={styles.revealText}>{phraseVisible ? 'Hide' : 'Reveal'}</Text>
          </TouchableOpacity>
        </View>
        {phraseVisible ? (
          <>
            <View style={styles.phraseGrid}>
              {keypair.mnemonic.split(' ').map((word, i) => (
                <View key={i} style={styles.wordChip}>
                  <Text style={styles.wordNum}>{i + 1}</Text>
                  <Text style={styles.wordText}>{word}</Text>
                </View>
              ))}
            </View>
            <TouchableOpacity style={styles.copyPhraseBtn} onPress={() => copy(keypair.mnemonic, 'Phrase')}>
              <Text style={styles.copyPhraseText}>Copy phrase</Text>
            </TouchableOpacity>
          </>
        ) : (
          <View style={styles.phraseMask}>
            <Text style={styles.phraseMaskText}>Tap Reveal to show recovery phrase</Text>
            <Text style={styles.phraseMaskWarn}>Never share this with anyone</Text>
          </View>
        )}
      </View>

      {/* Subnet info */}
      {metagraph && (
        <View style={styles.card}>
          <Text style={styles.cardLabel}>Bittensor Network</Text>
          <View style={styles.infoGrid}>
            {[
              ['Network', String(metagraph.network)],
              ['NetUID', String(metagraph.netuid)],
              ['Block', String(metagraph.block)],
            ].map(([k, v]) => (
              <View key={k} style={styles.infoRow}>
                <Text style={styles.infoKey}>{k}</Text>
                <Text style={styles.infoVal}>{v}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Delete */}
      <TouchableOpacity style={styles.deleteBtn} onPress={del} activeOpacity={0.8}>
        <Text style={styles.deleteText}>Delete Wallet from Device</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container:      { flex: 1, backgroundColor: '#09090f' },
  center:         { flex: 1, backgroundColor: '#09090f', alignItems: 'center', justifyContent: 'center', padding: 32 },
  logoCircle:     { width: 80, height: 80, borderRadius: 40, backgroundColor: '#13131f', alignItems: 'center', justifyContent: 'center', marginBottom: 20, borderWidth: 1, borderColor: 'rgba(124,58,237,0.3)' },
  logoEmoji:      { fontSize: 36 },
  createTitle:    { color: '#fff', fontSize: 26, fontWeight: '800', marginBottom: 12, letterSpacing: -0.5 },
  createSub:      { color: '#6b7280', fontSize: 14, textAlign: 'center', lineHeight: 21, marginBottom: 32 },
  createBtn:      { backgroundColor: '#7c3aed', borderRadius: 14, paddingHorizontal: 36, paddingVertical: 16, marginBottom: 12 },
  createBtnText:  { color: '#fff', fontSize: 15, fontWeight: '800' },
  createNote:     { color: '#374151', fontSize: 12 },
  headerSection:  { paddingHorizontal: 20, paddingTop: 24, paddingBottom: 4, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  title:          { color: '#fff', fontSize: 24, fontWeight: '800', letterSpacing: -0.5 },
  networkPill:    { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: '#13131f', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 5 },
  networkDot:     { width: 6, height: 6, borderRadius: 3, backgroundColor: '#22c55e' },
  networkText:    { color: '#6b7280', fontSize: 11 },
  card:           { marginHorizontal: 16, marginTop: 14, backgroundColor: '#13131f', borderRadius: 16, padding: 18, borderWidth: 1, borderColor: 'rgba(255,255,255,0.06)' },
  cardDanger:     { borderColor: 'rgba(239,68,68,0.2)' },
  cardHeader:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  cardLabel:      { color: '#6b7280', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8 },
  copyBtn:        { backgroundColor: 'rgba(124,58,237,0.15)', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 },
  copyText:       { color: '#a78bfa', fontSize: 12, fontWeight: '600' },
  monoLg:         { color: '#a78bfa', fontSize: 13, fontFamily: 'monospace', marginBottom: 4, lineHeight: 18 },
  monoSm:         { color: '#4b5563', fontSize: 10, fontFamily: 'monospace', lineHeight: 16 },
  safeBadge:      { marginTop: 10, backgroundColor: 'rgba(34,197,94,0.1)', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3, alignSelf: 'flex-start' },
  safeText:       { color: '#22c55e', fontSize: 11, fontWeight: '600' },
  revealBtn:      { backgroundColor: 'rgba(239,68,68,0.1)', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 },
  revealText:     { color: '#ef4444', fontSize: 12, fontWeight: '600' },
  phraseGrid:     { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  wordChip:       { backgroundColor: '#0a0a15', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 5 },
  wordNum:        { color: '#374151', fontSize: 10, fontWeight: '600' },
  wordText:       { color: '#e5e7eb', fontSize: 13, fontWeight: '600' },
  copyPhraseBtn:  { marginTop: 14, backgroundColor: 'rgba(239,68,68,0.08)', borderRadius: 10, paddingVertical: 10, alignItems: 'center' },
  copyPhraseText: { color: '#ef4444', fontSize: 13, fontWeight: '600' },
  phraseMask:     { backgroundColor: 'rgba(0,0,0,0.3)', borderRadius: 10, padding: 20, alignItems: 'center' },
  phraseMaskText: { color: '#6b7280', fontSize: 13, marginBottom: 4 },
  phraseMaskWarn: { color: '#374151', fontSize: 11 },
  infoGrid:       { gap: 8 },
  infoRow:        { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  infoKey:        { color: '#6b7280', fontSize: 13 },
  infoVal:        { color: '#e5e7eb', fontSize: 13, fontWeight: '600', fontFamily: 'monospace' },
  deleteBtn:      { marginHorizontal: 16, marginTop: 20, backgroundColor: '#13131f', borderRadius: 14, paddingVertical: 16, alignItems: 'center', borderWidth: 1, borderColor: 'rgba(239,68,68,0.25)' },
  deleteText:     { color: '#ef4444', fontSize: 14, fontWeight: '600' },
});

import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { C, radius } from '../theme';

const TABS = [
  { name: 'Dashboard', icon: '⛏', label: 'Mine' },
  { name: 'Start Mining', icon: '▶', label: 'Launch' },
  { name: 'Wallet', icon: '◈', label: 'Wallet' },
];

export default function TabBar({ state, navigation }: BottomTabBarProps) {
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.container, { paddingBottom: insets.bottom || 12 }]}>
      <View style={styles.bar}>
        {state.routes.map((route, i) => {
          const focused = state.index === i;
          const tab = TABS[i];
          return (
            <TabItem
              key={route.key}
              icon={tab.icon}
              label={tab.label}
              focused={focused}
              onPress={() => {
                if (!focused) navigation.navigate(route.name);
              }}
            />
          );
        })}
      </View>
    </View>
  );
}

function TabItem({ icon, label, focused, onPress }: {
  icon: string; label: string; focused: boolean; onPress: () => void;
}) {
  const glow = useRef(new Animated.Value(focused ? 1 : 0)).current;
  const scale = useRef(new Animated.Value(focused ? 1 : 0.9)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.spring(glow,  { toValue: focused ? 1 : 0, useNativeDriver: false, tension: 80, friction: 10 }),
      Animated.spring(scale, { toValue: focused ? 1 : 0.9, useNativeDriver: true, tension: 80, friction: 10 }),
    ]).start();
  }, [focused]);

  const bgColor = glow.interpolate({ inputRange: [0, 1], outputRange: ['rgba(124,58,237,0)', 'rgba(124,58,237,0.15)'] });
  const borderColor = glow.interpolate({ inputRange: [0, 1], outputRange: ['rgba(255,255,255,0)', 'rgba(124,58,237,0.4)'] });

  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.7} style={styles.item}>
      <Animated.View style={[styles.pill, { backgroundColor: bgColor, borderColor, transform: [{ scale }] }]}>
        <Text style={[styles.icon, { opacity: focused ? 1 : 0.35 }]}>{icon}</Text>
        <Text style={[styles.label, { color: focused ? C.purpleL : C.textDim }]}>{label}</Text>
      </Animated.View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: C.bg, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 8 },
  bar:       { flexDirection: 'row', paddingHorizontal: 12 },
  item:      { flex: 1, alignItems: 'center' },
  pill:      { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.full, borderWidth: 1 },
  icon:      { fontSize: 15 },
  label:     { fontSize: 12, fontWeight: '600', letterSpacing: 0.3 },
});

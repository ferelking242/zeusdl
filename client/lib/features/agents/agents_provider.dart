import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers/settings_provider.dart';

class AgentInfo {
  final String id;
  final String lastStatus;
  final DateTime? lastSeen;
  final int queueLength;

  const AgentInfo({
    required this.id,
    required this.lastStatus,
    this.lastSeen,
    required this.queueLength,
  });

  factory AgentInfo.fromJson(String id, Map<String, dynamic> j, int queueLen) {
    final lastSeenTs = j['last_seen'];
    return AgentInfo(
      id: id,
      lastStatus: j['last_status'] as String? ?? '',
      lastSeen: lastSeenTs != null
          ? DateTime.fromMillisecondsSinceEpoch(
              ((lastSeenTs as num) * 1000).toInt())
          : null,
      queueLength: queueLen,
    );
  }
}

class AgentsNotifier extends AsyncNotifier<List<AgentInfo>> {
  @override
  Future<List<AgentInfo>> build() async {
    return _fetchAgents();
  }

  Future<List<AgentInfo>> _fetchAgents() async {
    final settings = ref.read(settingsProvider);
    if (settings.masterUrl.isEmpty) return [];

    try {
      final dio = Dio(BaseOptions(
        baseUrl: settings.masterUrl,
        connectTimeout: const Duration(seconds: 5),
        receiveTimeout: const Duration(seconds: 5),
      ));
      final resp = await dio.get('/status');
      final data = resp.data as Map<String, dynamic>;
      final agents = data['agents'] as Map<String, dynamic>? ?? {};
      final queues = data['queues'] as Map<String, dynamic>? ?? {};
      return agents.entries
          .map((e) => AgentInfo.fromJson(
                e.key,
                e.value as Map<String, dynamic>,
                (queues[e.key] as List?)?.length ?? 0,
              ))
          .toList();
    } catch (e) {
      return [];
    }
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(_fetchAgents);
  }

  Future<void> sendOrder(String agentId, String order) async {
    final settings = ref.read(settingsProvider);
    if (settings.masterUrl.isEmpty) return;
    try {
      final dio = Dio();
      await dio.post(
        '${settings.masterUrl}/order',
        data: jsonEncode({'agent_id': agentId, 'order': order}),
        options: Options(headers: {'Content-Type': 'application/json'}),
      );
    } catch (_) {}
  }

  Future<void> broadcast(String order) async {
    final settings = ref.read(settingsProvider);
    if (settings.masterUrl.isEmpty) return;
    try {
      final dio = Dio();
      await dio.post(
        '${settings.masterUrl}/broadcast',
        data: jsonEncode({'order': order}),
        options: Options(headers: {'Content-Type': 'application/json'}),
      );
    } catch (_) {}
  }
}

final agentsProvider =
    AsyncNotifierProvider<AgentsNotifier, List<AgentInfo>>(AgentsNotifier.new);

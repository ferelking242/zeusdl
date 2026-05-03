import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:uuid/uuid.dart';

enum DownloadStatus { queued, running, completed, failed, paused }

class DownloadItem {
  final String id;
  final String url;
  final String quality;
  final String title;
  final DownloadStatus status;
  final double progress;
  final String speed;
  final String eta;
  final String filePath;
  final String error;
  final DateTime createdAt;

  const DownloadItem({
    required this.id,
    required this.url,
    required this.quality,
    this.title = '',
    this.status = DownloadStatus.queued,
    this.progress = 0.0,
    this.speed = '',
    this.eta = '',
    this.filePath = '',
    this.error = '',
    required this.createdAt,
  });

  DownloadItem copyWith({
    String? title,
    DownloadStatus? status,
    double? progress,
    String? speed,
    String? eta,
    String? filePath,
    String? error,
  }) {
    return DownloadItem(
      id: id,
      url: url,
      quality: quality,
      title: title ?? this.title,
      status: status ?? this.status,
      progress: progress ?? this.progress,
      speed: speed ?? this.speed,
      eta: eta ?? this.eta,
      filePath: filePath ?? this.filePath,
      error: error ?? this.error,
      createdAt: createdAt,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'url': url,
        'quality': quality,
        'title': title,
        'status': status.index,
        'progress': progress,
        'speed': speed,
        'eta': eta,
        'filePath': filePath,
        'error': error,
        'createdAt': createdAt.toIso8601String(),
      };

  factory DownloadItem.fromJson(Map<String, dynamic> j) => DownloadItem(
        id: j['id'] as String,
        url: j['url'] as String,
        quality: j['quality'] as String,
        title: j['title'] as String? ?? '',
        status: DownloadStatus.values[j['status'] as int],
        progress: (j['progress'] as num?)?.toDouble() ?? 0.0,
        speed: j['speed'] as String? ?? '',
        eta: j['eta'] as String? ?? '',
        filePath: j['filePath'] as String? ?? '',
        error: j['error'] as String? ?? '',
        createdAt: DateTime.parse(j['createdAt'] as String),
      );
}

class DownloadsNotifier extends Notifier<List<DownloadItem>> {
  static const _boxName = 'zeus_history';
  static const _uuid = Uuid();
  final Map<String, Timer> _simulationTimers = {};

  @override
  List<DownloadItem> build() {
    _loadFromStorage();
    return [];
  }

  void _loadFromStorage() {
    final box = Hive.box(_boxName);
    final raw = box.get('downloads', defaultValue: '[]') as String;
    try {
      final list = (jsonDecode(raw) as List)
          .map((e) => DownloadItem.fromJson(e as Map<String, dynamic>))
          .toList();
      state = list;
    } catch (_) {
      state = [];
    }
  }

  Future<void> _saveToStorage() async {
    final box = Hive.box(_boxName);
    await box.put(
      'downloads',
      jsonEncode(state.map((d) => d.toJson()).toList()),
    );
  }

  Future<void> addDownload({
    required String url,
    required String quality,
  }) async {
    final item = DownloadItem(
      id: _uuid.v4(),
      url: url,
      quality: quality,
      title: _extractTitle(url),
      status: DownloadStatus.queued,
      createdAt: DateTime.now(),
    );
    state = [...state, item];
    await _saveToStorage();
    _startSimulatedProgress(item.id);
  }

  String _extractTitle(String url) {
    try {
      final uri = Uri.parse(url);
      final segments = uri.pathSegments.where((s) => s.isNotEmpty).toList();
      if (segments.isNotEmpty) {
        return segments.last.replaceAll(RegExp(r'[_-]'), ' ');
      }
      return uri.host;
    } catch (_) {
      return url;
    }
  }

  void _startSimulatedProgress(String id) {
    const speeds = ['1.2 MB/s', '2.4 MB/s', '4.8 MB/s', '8.1 MB/s', '3.3 MB/s'];
    final rng = Random();
    int tick = 0;

    _simulationTimers[id]?.cancel();

    Future.delayed(const Duration(seconds: 1), () {
      _updateItem(id, (d) => d.copyWith(status: DownloadStatus.running));
    });

    _simulationTimers[id] = Timer.periodic(const Duration(milliseconds: 800), (t) {
      tick++;
      final item = state.firstWhere((d) => d.id == id, orElse: () => state.first);
      if (item.status == DownloadStatus.paused) return;

      final newProgress = (item.progress + rng.nextDouble() * 0.04).clamp(0.0, 1.0);
      final speed = speeds[rng.nextInt(speeds.length)];
      final remaining = ((1.0 - newProgress) / 0.04 * 0.8).round();
      final eta = remaining > 60
          ? '${remaining ~/ 60}m ${remaining % 60}s'
          : '${remaining}s';

      if (newProgress >= 1.0) {
        t.cancel();
        _simulationTimers.remove(id);
        _updateItem(
          id,
          (d) => d.copyWith(
            status: DownloadStatus.completed,
            progress: 1.0,
            speed: '',
            eta: '',
          ),
        );
        _saveToStorage();
      } else {
        _updateItem(
          id,
          (d) => d.copyWith(
            progress: newProgress,
            speed: speed,
            eta: eta,
          ),
        );
      }
    });
  }

  void _updateItem(String id, DownloadItem Function(DownloadItem) updater) {
    state = [
      for (final item in state)
        if (item.id == id) updater(item) else item,
    ];
  }

  Future<void> pauseDownload(String id) async {
    _updateItem(id, (d) => d.copyWith(status: DownloadStatus.paused));
    await _saveToStorage();
  }

  Future<void> resumeDownload(String id) async {
    _updateItem(id, (d) => d.copyWith(status: DownloadStatus.running));
    _startSimulatedProgress(id);
    await _saveToStorage();
  }

  Future<void> cancelDownload(String id) async {
    _simulationTimers[id]?.cancel();
    _simulationTimers.remove(id);
    state = state.where((d) => d.id != id).toList();
    await _saveToStorage();
  }

  Future<void> retryDownload(String id) async {
    _updateItem(
      id,
      (d) => d.copyWith(
        status: DownloadStatus.queued,
        progress: 0,
        error: '',
        speed: '',
        eta: '',
      ),
    );
    await _saveToStorage();
    _startSimulatedProgress(id);
  }

  Future<void> clearCompleted() async {
    state = state.where((d) => d.status != DownloadStatus.completed).toList();
    await _saveToStorage();
  }
}

final downloadsProvider =
    NotifierProvider<DownloadsNotifier, List<DownloadItem>>(
  DownloadsNotifier.new,
);

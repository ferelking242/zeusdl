import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';

class AppSettings {
  final ThemeMode themeMode;
  final String masterUrl;
  final String botToken;
  final String defaultQuality;
  final int maxWorkers;
  final String outputPath;
  final bool autoSendToTelegram;
  final String channelId;

  const AppSettings({
    this.themeMode = ThemeMode.dark,
    this.masterUrl = '',
    this.botToken = '',
    this.defaultQuality = '1080',
    this.maxWorkers = 3,
    this.outputPath = '',
    this.autoSendToTelegram = false,
    this.channelId = '',
  });

  AppSettings copyWith({
    ThemeMode? themeMode,
    String? masterUrl,
    String? botToken,
    String? defaultQuality,
    int? maxWorkers,
    String? outputPath,
    bool? autoSendToTelegram,
    String? channelId,
  }) {
    return AppSettings(
      themeMode: themeMode ?? this.themeMode,
      masterUrl: masterUrl ?? this.masterUrl,
      botToken: botToken ?? this.botToken,
      defaultQuality: defaultQuality ?? this.defaultQuality,
      maxWorkers: maxWorkers ?? this.maxWorkers,
      outputPath: outputPath ?? this.outputPath,
      autoSendToTelegram: autoSendToTelegram ?? this.autoSendToTelegram,
      channelId: channelId ?? this.channelId,
    );
  }
}

class SettingsNotifier extends Notifier<AppSettings> {
  static const _boxName = 'zeus_settings';

  @override
  AppSettings build() {
    final box = Hive.box(_boxName);
    final themeModeIndex = box.get('themeMode', defaultValue: 2) as int;
    return AppSettings(
      themeMode: ThemeMode.values[themeModeIndex],
      masterUrl: box.get('masterUrl', defaultValue: '') as String,
      botToken: box.get('botToken', defaultValue: '') as String,
      defaultQuality: box.get('defaultQuality', defaultValue: '1080') as String,
      maxWorkers: box.get('maxWorkers', defaultValue: 3) as int,
      outputPath: box.get('outputPath', defaultValue: '') as String,
      autoSendToTelegram:
          box.get('autoSendToTelegram', defaultValue: false) as bool,
      channelId: box.get('channelId', defaultValue: '') as String,
    );
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    final box = Hive.box(_boxName);
    await box.put('themeMode', mode.index);
    state = state.copyWith(themeMode: mode);
  }

  Future<void> setMasterUrl(String url) async {
    final box = Hive.box(_boxName);
    await box.put('masterUrl', url);
    state = state.copyWith(masterUrl: url);
  }

  Future<void> setBotToken(String token) async {
    final box = Hive.box(_boxName);
    await box.put('botToken', token);
    state = state.copyWith(botToken: token);
  }

  Future<void> setDefaultQuality(String quality) async {
    final box = Hive.box(_boxName);
    await box.put('defaultQuality', quality);
    state = state.copyWith(defaultQuality: quality);
  }

  Future<void> setMaxWorkers(int workers) async {
    final box = Hive.box(_boxName);
    await box.put('maxWorkers', workers);
    state = state.copyWith(maxWorkers: workers);
  }

  Future<void> setOutputPath(String path) async {
    final box = Hive.box(_boxName);
    await box.put('outputPath', path);
    state = state.copyWith(outputPath: path);
  }

  Future<void> setAutoSendToTelegram(bool value) async {
    final box = Hive.box(_boxName);
    await box.put('autoSendToTelegram', value);
    state = state.copyWith(autoSendToTelegram: value);
  }

  Future<void> setChannelId(String id) async {
    final box = Hive.box(_boxName);
    await box.put('channelId', id);
    state = state.copyWith(channelId: id);
  }
}

final settingsProvider = NotifierProvider<SettingsNotifier, AppSettings>(
  SettingsNotifier.new,
);

import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gap/gap.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../../core/providers/settings_provider.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  final _masterUrlCtrl = TextEditingController();
  final _botTokenCtrl = TextEditingController();
  final _channelCtrl = TextEditingController();
  String _appVersion = '';

  @override
  void initState() {
    super.initState();
    _loadVersion();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final settings = ref.read(settingsProvider);
      _masterUrlCtrl.text = settings.masterUrl;
      _botTokenCtrl.text = settings.botToken;
      _channelCtrl.text = settings.channelId;
    });
  }

  Future<void> _loadVersion() async {
    final info = await PackageInfo.fromPlatform();
    if (mounted) {
      setState(() => _appVersion = '${info.version}+${info.buildNumber}');
    }
  }

  @override
  void dispose() {
    _masterUrlCtrl.dispose();
    _botTokenCtrl.dispose();
    _channelCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final settings = ref.watch(settingsProvider);
    final notifier = ref.read(settingsProvider.notifier);

    return Scaffold(
      body: CustomScrollView(
        physics: const BouncingScrollPhysics(),
        slivers: [
          const SliverAppBar.large(title: Text('Paramètres')),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 80),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                _Section(
                  title: 'Apparence',
                  icon: Icons.palette_outlined,
                  children: [
                    _ThemeSelector(
                      current: settings.themeMode,
                      onChanged: notifier.setThemeMode,
                    ),
                  ],
                ).animate().fadeIn(delay: 100.ms).slideY(begin: 0.1, end: 0),
                const Gap(16),
                _Section(
                  title: 'Connexion Mastermind',
                  icon: Icons.cloud_outlined,
                  children: [
                    _TextField(
                      controller: _masterUrlCtrl,
                      label: 'URL Mastermind',
                      hint: 'https://xxx.replit.dev',
                      icon: Icons.link_rounded,
                      onChanged: notifier.setMasterUrl,
                    ),
                  ],
                ).animate().fadeIn(delay: 150.ms).slideY(begin: 0.1, end: 0),
                const Gap(16),
                _Section(
                  title: 'Telegram',
                  icon: Icons.telegram_rounded,
                  children: [
                    _TextField(
                      controller: _botTokenCtrl,
                      label: 'Bot Token',
                      hint: '7909...',
                      icon: Icons.key_rounded,
                      obscure: true,
                      onChanged: notifier.setBotToken,
                    ),
                    const Gap(12),
                    _TextField(
                      controller: _channelCtrl,
                      label: 'Channel ID',
                      hint: '-100...',
                      icon: Icons.tag_rounded,
                      onChanged: notifier.setChannelId,
                    ),
                    const Gap(12),
                    SwitchListTile(
                      value: settings.autoSendToTelegram,
                      onChanged: notifier.setAutoSendToTelegram,
                      title: const Text('Envoi auto Telegram'),
                      subtitle: const Text(
                          'Envoyer automatiquement après téléchargement'),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ],
                ).animate().fadeIn(delay: 200.ms).slideY(begin: 0.1, end: 0),
                const Gap(16),
                _Section(
                  title: 'Téléchargement',
                  icon: Icons.settings_outlined,
                  children: [
                    _QualitySelector(
                      current: settings.defaultQuality,
                      onChanged: notifier.setDefaultQuality,
                    ),
                    const Gap(12),
                    _WorkersSlider(
                      current: settings.maxWorkers,
                      onChanged: notifier.setMaxWorkers,
                    ),
                  ],
                ).animate().fadeIn(delay: 250.ms).slideY(begin: 0.1, end: 0),
                const Gap(16),
                _Section(
                  title: 'À propos',
                  icon: Icons.info_outline_rounded,
                  children: [
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.bolt_rounded),
                      title: const Text('ZeusDL Client'),
                      subtitle: Text('Version $_appVersion'),
                    ),
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.code_rounded),
                      title: const Text('GitHub'),
                      subtitle: const Text('github.com/ferelking242/zeusdl'),
                      trailing: const Icon(Icons.open_in_new_rounded, size: 16),
                    ),
                  ],
                ).animate().fadeIn(delay: 300.ms).slideY(begin: 0.1, end: 0),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}

class _Section extends StatelessWidget {
  final String title;
  final IconData icon;
  final List<Widget> children;

  const _Section({
    required this.title,
    required this.icon,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, size: 18, color: cs.primary),
            const Gap(8),
            Text(
              title,
              style: tt.titleSmall?.copyWith(
                fontWeight: FontWeight.w700,
                color: cs.primary,
              ),
            ),
          ],
        ),
        const Gap(10),
        Card(
          elevation: 0,
          color: cs.surfaceContainerLow,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: children,
            ),
          ),
        ),
      ],
    );
  }
}

class _ThemeSelector extends StatelessWidget {
  final ThemeMode current;
  final ValueChanged<ThemeMode> onChanged;

  const _ThemeSelector({required this.current, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final modes = [
      (ThemeMode.system, Icons.brightness_auto_rounded, 'Système'),
      (ThemeMode.light, Icons.light_mode_rounded, 'Clair'),
      (ThemeMode.dark, Icons.dark_mode_rounded, 'Sombre'),
    ];

    return Row(
      children: modes.map((m) {
        final selected = current == m.$1;
        return Expanded(
          child: GestureDetector(
            onTap: () => onChanged(m.$1),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              margin: const EdgeInsets.symmetric(horizontal: 4),
              padding: const EdgeInsets.symmetric(vertical: 12),
              decoration: BoxDecoration(
                color: selected ? cs.primaryContainer : cs.surface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: selected ? cs.primary : cs.outline.withOpacity(0.3),
                  width: selected ? 2 : 1,
                ),
              ),
              child: Column(
                children: [
                  Icon(
                    m.$2,
                    color: selected ? cs.primary : cs.onSurfaceVariant,
                    size: 22,
                  ),
                  const Gap(4),
                  Text(
                    m.$3,
                    style: tt.labelSmall?.copyWith(
                      color: selected ? cs.primary : cs.onSurfaceVariant,
                      fontWeight:
                          selected ? FontWeight.w600 : FontWeight.normal,
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      }).toList(),
    );
  }
}

class _TextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hint;
  final IconData icon;
  final bool obscure;
  final void Function(String) onChanged;

  const _TextField({
    required this.controller,
    required this.label,
    required this.hint,
    required this.icon,
    this.obscure = false,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return TextFormField(
      controller: controller,
      obscureText: obscure,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        prefixIcon: Icon(icon),
        filled: true,
        fillColor: cs.surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: cs.outline.withOpacity(0.3)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: cs.primary, width: 2),
        ),
      ),
      onChanged: onChanged,
    );
  }
}

class _QualitySelector extends StatelessWidget {
  final String current;
  final void Function(String) onChanged;

  const _QualitySelector({required this.current, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Qualité par défaut',
            style: Theme.of(context).textTheme.bodyMedium),
        const Gap(8),
        Wrap(
          spacing: 8,
          children: ['4320', '2160', '1440', '1080', '720', '480', '360']
              .map((q) => ChoiceChip(
                    label: Text('${q}p'),
                    selected: current == q,
                    onSelected: (_) => onChanged(q),
                    selectedColor: cs.primaryContainer,
                  ))
              .toList(),
        ),
      ],
    );
  }
}

class _WorkersSlider extends StatelessWidget {
  final int current;
  final void Function(int) onChanged;

  const _WorkersSlider({required this.current, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Workers simultanés',
                style: Theme.of(context).textTheme.bodyMedium),
            Text(
              '$current',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: Theme.of(context).colorScheme.primary,
                  ),
            ),
          ],
        ),
        Slider(
          value: current.toDouble(),
          min: 1,
          max: 8,
          divisions: 7,
          onChanged: (v) => onChanged(v.toInt()),
        ),
      ],
    );
  }
}

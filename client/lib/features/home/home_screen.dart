import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gap/gap.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers/settings_provider.dart';
import '../../shared/widgets/zeus_logo.dart';
import '../downloads/downloads_provider.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen>
    with TickerProviderStateMixin {
  final _urlController = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  late final AnimationController _pulseController;
  String _selectedQuality = '1080';
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _urlController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _isSubmitting = true);
    HapticFeedback.mediumImpact();

    await ref.read(downloadsProvider.notifier).addDownload(
          url: _urlController.text.trim(),
          quality: _selectedQuality,
        );

    if (mounted) {
      setState(() => _isSubmitting = false);
      _urlController.clear();
      context.go('/downloads');
    }
  }

  Future<void> _pasteFromClipboard() async {
    final data = await Clipboard.getData('text/plain');
    if (data?.text != null) {
      _urlController.text = data!.text!;
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final settings = ref.watch(settingsProvider);
    final downloads = ref.watch(downloadsProvider);
    final activeCount =
        downloads.where((d) => d.status == DownloadStatus.running).length;

    return Scaffold(
      body: CustomScrollView(
        physics: const BouncingScrollPhysics(),
        slivers: [
          SliverAppBar.large(
            title: const Text('ZeusDL'),
            centerTitle: false,
            floating: true,
            backgroundColor: cs.surface,
            surfaceTintColor: Colors.transparent,
            flexibleSpace: FlexibleSpaceBar(
              background: Padding(
                padding: const EdgeInsets.fromLTRB(16, 80, 16, 0),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    const ZeusLogo(size: 48),
                    const Gap(12),
                    Column(
                      mainAxisAlignment: MainAxisAlignment.end,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'ZeusDL',
                          style: tt.headlineLarge?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: cs.primary,
                          ),
                        ),
                        Text(
                          'Multi-platform downloader',
                          style: tt.bodyMedium?.copyWith(
                            color: cs.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.all(16),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                _StatusBanner(
                  masterUrl: settings.masterUrl,
                  activeDownloads: activeCount,
                ).animate().fadeIn(delay: 100.ms).slideY(begin: 0.1, end: 0),
                const Gap(20),
                _DownloadForm(
                  formKey: _formKey,
                  controller: _urlController,
                  selectedQuality: _selectedQuality,
                  isSubmitting: _isSubmitting,
                  onQualityChanged: (q) => setState(() => _selectedQuality = q!),
                  onPaste: _pasteFromClipboard,
                  onSubmit: _submit,
                ).animate().fadeIn(delay: 200.ms).slideY(begin: 0.1, end: 0),
                const Gap(20),
                _QuickStats(downloads: downloads)
                    .animate()
                    .fadeIn(delay: 300.ms)
                    .slideY(begin: 0.1, end: 0),
                const Gap(80),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusBanner extends StatelessWidget {
  final String masterUrl;
  final int activeDownloads;

  const _StatusBanner({
    required this.masterUrl,
    required this.activeDownloads,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final isConnected = masterUrl.isNotEmpty;

    return Card(
      elevation: 0,
      color: isConnected
          ? cs.primaryContainer.withOpacity(0.5)
          : cs.errorContainer.withOpacity(0.4),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 500),
              width: 12,
              height: 12,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: isConnected ? Colors.greenAccent : cs.error,
                boxShadow: [
                  BoxShadow(
                    color: (isConnected ? Colors.greenAccent : cs.error)
                        .withOpacity(0.6),
                    blurRadius: 8,
                    spreadRadius: 2,
                  ),
                ],
              ),
            ),
            const Gap(12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    isConnected ? 'Mastermind connecté' : 'Non configuré',
                    style: tt.labelLarge?.copyWith(
                      color: isConnected
                          ? cs.onPrimaryContainer
                          : cs.onErrorContainer,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (isConnected)
                    Text(
                      masterUrl,
                      style: tt.bodySmall?.copyWith(
                        color: cs.onPrimaryContainer.withOpacity(0.7),
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                ],
              ),
            ),
            if (activeDownloads > 0)
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: cs.primary,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  '$activeDownloads actif',
                  style: tt.labelSmall?.copyWith(color: cs.onPrimary),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _DownloadForm extends StatelessWidget {
  final GlobalKey<FormState> formKey;
  final TextEditingController controller;
  final String selectedQuality;
  final bool isSubmitting;
  final ValueChanged<String?> onQualityChanged;
  final VoidCallback onPaste;
  final VoidCallback onSubmit;

  const _DownloadForm({
    required this.formKey,
    required this.controller,
    required this.selectedQuality,
    required this.isSubmitting,
    required this.onQualityChanged,
    required this.onPaste,
    required this.onSubmit,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return Card(
      elevation: 0,
      color: cs.surfaceContainerLow,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Form(
          key: formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Nouveau téléchargement',
                style: tt.titleMedium?.copyWith(fontWeight: FontWeight.w600),
              ),
              const Gap(16),
              TextFormField(
                controller: controller,
                decoration: InputDecoration(
                  hintText: 'https://...',
                  labelText: 'URL',
                  prefixIcon: const Icon(Icons.link_rounded),
                  suffixIcon: IconButton(
                    onPressed: onPaste,
                    icon: const Icon(Icons.content_paste_rounded),
                    tooltip: 'Coller',
                  ),
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
                validator: (v) {
                  if (v == null || v.trim().isEmpty) return 'URL requise';
                  final uri = Uri.tryParse(v.trim());
                  if (uri == null || !uri.hasScheme) return 'URL invalide';
                  return null;
                },
                keyboardType: TextInputType.url,
                textInputAction: TextInputAction.done,
                onFieldSubmitted: (_) => onSubmit(),
              ),
              const Gap(12),
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      value: selectedQuality,
                      decoration: InputDecoration(
                        labelText: 'Qualité',
                        prefixIcon: const Icon(Icons.hd_rounded),
                        filled: true,
                        fillColor: cs.surface,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide.none,
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide:
                              BorderSide(color: cs.outline.withOpacity(0.3)),
                        ),
                      ),
                      items: ['4320', '2160', '1440', '1080', '720', '480', '360']
                          .map((q) => DropdownMenuItem(
                                value: q,
                                child: Text('${q}p'),
                              ))
                          .toList(),
                      onChanged: onQualityChanged,
                    ),
                  ),
                ],
              ),
              const Gap(20),
              SizedBox(
                width: double.infinity,
                height: 52,
                child: FilledButton.icon(
                  onPressed: isSubmitting ? null : onSubmit,
                  icon: isSubmitting
                      ? SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: cs.onPrimary,
                          ),
                        )
                      : const Icon(Icons.bolt_rounded),
                  label: Text(
                    isSubmitting ? 'Ajout en cours...' : 'Télécharger',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _QuickStats extends StatelessWidget {
  final List<DownloadItem> downloads;
  const _QuickStats({required this.downloads});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    final completed =
        downloads.where((d) => d.status == DownloadStatus.completed).length;
    final failed =
        downloads.where((d) => d.status == DownloadStatus.failed).length;
    final running =
        downloads.where((d) => d.status == DownloadStatus.running).length;
    final total = downloads.length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Statistiques rapides',
          style: tt.titleMedium?.copyWith(fontWeight: FontWeight.w600),
        ),
        const Gap(12),
        Row(
          children: [
            _StatChip(
              label: 'Total',
              value: '$total',
              color: cs.primary,
              icon: Icons.download_rounded,
            ),
            const Gap(10),
            _StatChip(
              label: 'Actifs',
              value: '$running',
              color: Colors.orangeAccent,
              icon: Icons.sync_rounded,
            ),
            const Gap(10),
            _StatChip(
              label: 'Finis',
              value: '$completed',
              color: Colors.greenAccent,
              icon: Icons.check_circle_outline_rounded,
            ),
            const Gap(10),
            _StatChip(
              label: 'Erreurs',
              value: '$failed',
              color: cs.error,
              icon: Icons.error_outline_rounded,
            ),
          ],
        ),
      ],
    );
  }
}

class _StatChip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  final IconData icon;

  const _StatChip({
    required this.label,
    required this.value,
    required this.color,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: color.withOpacity(0.12),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: color.withOpacity(0.25)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 20),
            const Gap(8),
            Text(
              value,
              style: tt.titleLarge?.copyWith(
                  fontWeight: FontWeight.bold, color: color),
            ),
            Text(
              label,
              style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gap/gap.dart';
import 'package:percent_indicator/percent_indicator.dart';

import 'downloads_provider.dart';

class DownloadsScreen extends ConsumerWidget {
  const DownloadsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final downloads = ref.watch(downloadsProvider);
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    final active =
        downloads.where((d) => d.status == DownloadStatus.running).toList();
    final queued =
        downloads.where((d) => d.status == DownloadStatus.queued).toList();
    final paused =
        downloads.where((d) => d.status == DownloadStatus.paused).toList();
    final done = downloads
        .where((d) =>
            d.status == DownloadStatus.completed ||
            d.status == DownloadStatus.failed)
        .toList();

    return Scaffold(
      body: CustomScrollView(
        physics: const BouncingScrollPhysics(),
        slivers: [
          SliverAppBar.large(
            title: const Text('Téléchargements'),
            actions: [
              if (done.isNotEmpty)
                TextButton.icon(
                  onPressed: () =>
                      ref.read(downloadsProvider.notifier).clearCompleted(),
                  icon: const Icon(Icons.clear_all_rounded),
                  label: const Text('Nettoyer'),
                ),
              const Gap(8),
            ],
          ),
          if (downloads.isEmpty)
            SliverFillRemaining(
              child: Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.download_outlined,
                      size: 72,
                      color: cs.onSurfaceVariant.withOpacity(0.3),
                    ),
                    const Gap(16),
                    Text(
                      'Aucun téléchargement',
                      style: tt.titleLarge?.copyWith(
                        color: cs.onSurfaceVariant,
                      ),
                    ),
                    const Gap(8),
                    Text(
                      'Ajoutez une URL depuis l\'accueil',
                      style: tt.bodyMedium?.copyWith(
                        color: cs.onSurfaceVariant.withOpacity(0.6),
                      ),
                    ),
                  ],
                ).animate().fadeIn(duration: 600.ms).scale(begin: const Offset(0.9, 0.9)),
              ),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 80),
              sliver: SliverList(
                delegate: SliverChildListDelegate([
                  if (active.isNotEmpty) ...[
                    _SectionHeader(
                      title: 'En cours',
                      count: active.length,
                      color: cs.primary,
                    ),
                    const Gap(8),
                    ...active.asMap().entries.map(
                          (e) => _DownloadCard(
                            item: e.value,
                            index: e.key,
                          ),
                        ),
                    const Gap(16),
                  ],
                  if (queued.isNotEmpty) ...[
                    _SectionHeader(
                      title: 'En file',
                      count: queued.length,
                      color: Colors.orangeAccent,
                    ),
                    const Gap(8),
                    ...queued.asMap().entries.map(
                          (e) => _DownloadCard(
                            item: e.value,
                            index: e.key,
                          ),
                        ),
                    const Gap(16),
                  ],
                  if (paused.isNotEmpty) ...[
                    _SectionHeader(
                      title: 'En pause',
                      count: paused.length,
                      color: Colors.blueAccent,
                    ),
                    const Gap(8),
                    ...paused.asMap().entries.map(
                          (e) => _DownloadCard(
                            item: e.value,
                            index: e.key,
                          ),
                        ),
                    const Gap(16),
                  ],
                  if (done.isNotEmpty) ...[
                    _SectionHeader(
                      title: 'Terminés',
                      count: done.length,
                      color: cs.onSurfaceVariant,
                    ),
                    const Gap(8),
                    ...done.asMap().entries.map(
                          (e) => _DownloadCard(
                            item: e.value,
                            index: e.key,
                          ),
                        ),
                  ],
                ]),
              ),
            ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  final int count;
  final Color color;

  const _SectionHeader({
    required this.title,
    required this.count,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final tt = Theme.of(context).textTheme;
    return Row(
      children: [
        Container(
          width: 4,
          height: 18,
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const Gap(8),
        Text(
          title,
          style: tt.titleSmall?.copyWith(
            fontWeight: FontWeight.w600,
            color: color,
          ),
        ),
        const Gap(8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(
            color: color.withOpacity(0.15),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(
            '$count',
            style: tt.labelSmall?.copyWith(color: color),
          ),
        ),
      ],
    );
  }
}

class _DownloadCard extends ConsumerWidget {
  final DownloadItem item;
  final int index;

  const _DownloadCard({required this.item, required this.index});

  Color _statusColor(BuildContext context, DownloadStatus s) {
    final cs = Theme.of(context).colorScheme;
    return switch (s) {
      DownloadStatus.running => cs.primary,
      DownloadStatus.completed => Colors.greenAccent,
      DownloadStatus.failed => cs.error,
      DownloadStatus.paused => Colors.blueAccent,
      DownloadStatus.queued => Colors.orangeAccent,
    };
  }

  IconData _statusIcon(DownloadStatus s) {
    return switch (s) {
      DownloadStatus.running => Icons.sync_rounded,
      DownloadStatus.completed => Icons.check_circle_rounded,
      DownloadStatus.failed => Icons.error_rounded,
      DownloadStatus.paused => Icons.pause_circle_rounded,
      DownloadStatus.queued => Icons.schedule_rounded,
    };
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final color = _statusColor(context, item.status);
    final notifier = ref.read(downloadsProvider.notifier);

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      elevation: 0,
      color: cs.surfaceContainerLow,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(_statusIcon(item.status), color: color, size: 20)
                    .animate(
                      onPlay: (c) =>
                          item.status == DownloadStatus.running ? c.repeat() : null,
                    )
                    .rotate(
                      duration: 1.5.seconds,
                      begin: 0,
                      end: item.status == DownloadStatus.running ? 1 : 0,
                    ),
                const Gap(8),
                Expanded(
                  child: Text(
                    item.title.isEmpty ? item.url : item.title,
                    style: tt.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const Gap(8),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    '${item.quality}p',
                    style: tt.labelSmall?.copyWith(color: color),
                  ),
                ),
              ],
            ),
            if (item.status == DownloadStatus.running ||
                item.status == DownloadStatus.paused) ...[
              const Gap(12),
              LinearPercentIndicator(
                lineHeight: 6,
                percent: item.progress.clamp(0.0, 1.0),
                progressColor: color,
                backgroundColor: color.withOpacity(0.15),
                barRadius: const Radius.circular(4),
                padding: EdgeInsets.zero,
                animation: true,
                animateFromLastPercent: true,
              ),
              const Gap(8),
              Row(
                children: [
                  Text(
                    '${(item.progress * 100).toStringAsFixed(1)}%',
                    style: tt.labelMedium?.copyWith(color: color),
                  ),
                  const Spacer(),
                  if (item.speed.isNotEmpty)
                    Text(
                      item.speed,
                      style: tt.labelSmall
                          ?.copyWith(color: cs.onSurfaceVariant),
                    ),
                  if (item.eta.isNotEmpty) ...[
                    const Gap(8),
                    Text(
                      'ETA: ${item.eta}',
                      style: tt.labelSmall
                          ?.copyWith(color: cs.onSurfaceVariant),
                    ),
                  ],
                ],
              ),
            ],
            if (item.status == DownloadStatus.failed && item.error.isNotEmpty) ...[
              const Gap(8),
              Text(
                item.error,
                style: tt.bodySmall?.copyWith(color: cs.error),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
            if (item.status != DownloadStatus.completed) ...[
              const Gap(12),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  if (item.status == DownloadStatus.running)
                    _ActionChip(
                      label: 'Pause',
                      icon: Icons.pause_rounded,
                      onTap: () => notifier.pauseDownload(item.id),
                    ),
                  if (item.status == DownloadStatus.paused)
                    _ActionChip(
                      label: 'Reprendre',
                      icon: Icons.play_arrow_rounded,
                      onTap: () => notifier.resumeDownload(item.id),
                    ),
                  if (item.status == DownloadStatus.failed)
                    _ActionChip(
                      label: 'Réessayer',
                      icon: Icons.refresh_rounded,
                      onTap: () => notifier.retryDownload(item.id),
                    ),
                  const Gap(8),
                  _ActionChip(
                    label: 'Annuler',
                    icon: Icons.close_rounded,
                    onTap: () => notifier.cancelDownload(item.id),
                    isDestructive: true,
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    ).animate(delay: (index * 60).ms).fadeIn().slideY(begin: 0.1, end: 0);
  }
}

class _ActionChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;
  final bool isDestructive;

  const _ActionChip({
    required this.label,
    required this.icon,
    required this.onTap,
    this.isDestructive = false,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final color = isDestructive ? cs.error : cs.primary;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: color.withOpacity(0.12),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14, color: color),
            const Gap(4),
            Text(
              label,
              style: TextStyle(
                  fontSize: 12, color: color, fontWeight: FontWeight.w500),
            ),
          ],
        ),
      ),
    );
  }
}

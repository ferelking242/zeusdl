import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gap/gap.dart';

import 'agents_provider.dart';

class AgentsScreen extends ConsumerWidget {
  const AgentsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final agents = ref.watch(agentsProvider);
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return Scaffold(
      body: CustomScrollView(
        physics: const BouncingScrollPhysics(),
        slivers: [
          SliverAppBar.large(
            title: const Text('Agents'),
            actions: [
              IconButton(
                onPressed: () => ref.read(agentsProvider.notifier).refresh(),
                icon: const Icon(Icons.refresh_rounded),
                tooltip: 'Actualiser',
              ),
              const Gap(8),
            ],
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 80),
            sliver: agents.when(
              loading: () => const SliverFillRemaining(
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (e, _) => SliverFillRemaining(
                child: Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.cloud_off_rounded,
                          size: 64,
                          color: cs.onSurfaceVariant.withOpacity(0.4)),
                      const Gap(16),
                      Text('Impossible de se connecter',
                          style: tt.titleMedium),
                      const Gap(8),
                      Text(
                        e.toString(),
                        style: tt.bodySmall?.copyWith(
                          color: cs.onSurfaceVariant,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
              data: (list) => list.isEmpty
                  ? SliverFillRemaining(
                      child: Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              Icons.smart_toy_outlined,
                              size: 72,
                              color: cs.onSurfaceVariant.withOpacity(0.3),
                            ),
                            const Gap(16),
                            Text(
                              'Aucun agent connecté',
                              style: tt.titleLarge?.copyWith(
                                color: cs.onSurfaceVariant,
                              ),
                            ),
                            const Gap(8),
                            Text(
                              'Lance l\'agent sur Google Colab',
                              style: tt.bodyMedium?.copyWith(
                                color: cs.onSurfaceVariant.withOpacity(0.6),
                              ),
                            ),
                          ],
                        ).animate().fadeIn(duration: 500.ms),
                      ),
                    )
                  : SliverList(
                      delegate: SliverChildBuilderDelegate(
                        (ctx, i) => _AgentCard(agent: list[i], index: i),
                        childCount: list.length,
                      ),
                    ),
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _showBroadcastDialog(context, ref),
        icon: const Icon(Icons.broadcast_on_personal_rounded),
        label: const Text('Broadcast'),
      ).animate().scale(delay: 400.ms),
    );
  }

  void _showBroadcastDialog(BuildContext context, WidgetRef ref) {
    final ctrl = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Broadcast ordre'),
        content: TextField(
          controller: ctrl,
          decoration: const InputDecoration(
            hintText: '/download https://...',
            labelText: 'Ordre',
          ),
          autofocus: true,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () {
              if (ctrl.text.isNotEmpty) {
                ref.read(agentsProvider.notifier).broadcast(ctrl.text);
                Navigator.pop(ctx);
              }
            },
            child: const Text('Envoyer'),
          ),
        ],
      ),
    );
  }
}

class _AgentCard extends ConsumerWidget {
  final AgentInfo agent;
  final int index;

  const _AgentCard({required this.agent, required this.index});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final isOnline = agent.lastSeen != null &&
        DateTime.now().difference(agent.lastSeen!).inSeconds < 30;

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
                Stack(
                  children: [
                    CircleAvatar(
                      backgroundColor: cs.primaryContainer,
                      child: Icon(
                        Icons.smart_toy_rounded,
                        color: cs.onPrimaryContainer,
                      ),
                    ),
                    Positioned(
                      right: 0,
                      bottom: 0,
                      child: Container(
                        width: 12,
                        height: 12,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: isOnline ? Colors.greenAccent : cs.error,
                          border: Border.all(color: cs.surface, width: 2),
                        ),
                      ),
                    ),
                  ],
                ),
                const Gap(12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        agent.id,
                        style:
                            tt.titleMedium?.copyWith(fontWeight: FontWeight.w600),
                      ),
                      Text(
                        isOnline ? 'En ligne' : 'Hors ligne',
                        style: tt.bodySmall?.copyWith(
                          color: isOnline ? Colors.greenAccent : cs.error,
                        ),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: cs.secondaryContainer,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    '${agent.queueLength} ordres',
                    style: tt.labelSmall
                        ?.copyWith(color: cs.onSecondaryContainer),
                  ),
                ),
              ],
            ),
            if (agent.lastStatus.isNotEmpty) ...[
              const Gap(10),
              const Divider(height: 1),
              const Gap(10),
              Row(
                children: [
                  Icon(Icons.info_outline_rounded,
                      size: 14, color: cs.onSurfaceVariant),
                  const Gap(6),
                  Expanded(
                    child: Text(
                      agent.lastStatus,
                      style: tt.bodySmall
                          ?.copyWith(color: cs.onSurfaceVariant),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ],
            const Gap(12),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                OutlinedButton.icon(
                  onPressed: () =>
                      _showSendOrderDialog(context, ref, agent.id),
                  icon: const Icon(Icons.send_rounded, size: 16),
                  label: const Text('Envoyer ordre'),
                  style: OutlinedButton.styleFrom(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    ).animate(delay: (index * 80).ms).fadeIn().slideY(begin: 0.1, end: 0);
  }

  void _showSendOrderDialog(
      BuildContext context, WidgetRef ref, String agentId) {
    final ctrl = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Ordre → $agentId'),
        content: TextField(
          controller: ctrl,
          decoration: const InputDecoration(
            hintText: '/download https://...',
            labelText: 'Ordre',
          ),
          autofocus: true,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () {
              if (ctrl.text.isNotEmpty) {
                ref.read(agentsProvider.notifier).sendOrder(agentId, ctrl.text);
                Navigator.pop(ctx);
              }
            },
            child: const Text('Envoyer'),
          ),
        ],
      ),
    );
  }
}

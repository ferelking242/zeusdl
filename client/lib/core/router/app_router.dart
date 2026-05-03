import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/home/home_screen.dart';
import '../../features/downloads/downloads_screen.dart';
import '../../features/agents/agents_screen.dart';
import '../../features/history/history_screen.dart';
import '../../features/settings/settings_screen.dart';
import '../../shared/widgets/shell_scaffold.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/home',
    debugLogDiagnostics: false,
    routes: [
      ShellRoute(
        builder: (context, state, child) => ShellScaffold(child: child),
        routes: [
          GoRoute(
            path: '/home',
            pageBuilder: (context, state) => _buildPage(state, const HomeScreen()),
          ),
          GoRoute(
            path: '/downloads',
            pageBuilder: (context, state) => _buildPage(state, const DownloadsScreen()),
          ),
          GoRoute(
            path: '/agents',
            pageBuilder: (context, state) => _buildPage(state, const AgentsScreen()),
          ),
          GoRoute(
            path: '/history',
            pageBuilder: (context, state) => _buildPage(state, const HistoryScreen()),
          ),
          GoRoute(
            path: '/settings',
            pageBuilder: (context, state) => _buildPage(state, const SettingsScreen()),
          ),
        ],
      ),
    ],
  );
});

CustomTransitionPage<void> _buildPage(GoRouterState state, Widget child) {
  return CustomTransitionPage<void>(
    key: state.pageKey,
    child: child,
    transitionsBuilder: (context, animation, secondaryAnimation, child) {
      final slideTween = Tween(
        begin: const Offset(0.04, 0.0),
        end: Offset.zero,
      ).chain(CurveTween(curve: Curves.easeOutCubic));
      final fadeTween = Tween<double>(begin: 0.0, end: 1.0);
      return FadeTransition(
        opacity: animation.drive(fadeTween),
        child: SlideTransition(
          position: animation.drive(slideTween),
          child: child,
        ),
      );
    },
    transitionDuration: const Duration(milliseconds: 280),
  );
}

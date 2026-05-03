# ZeusDL

Downloader multi-agents basé sur yt-dlp, avec client Flutter multi-plateformes et intégration Telegram.

## Structure

```
zeusdl/                 # Package Python principal (fork yt-dlp custom)
│   zeusdl/             # Module Python installable
│   zeus_mastermind.py  # Serveur HTTP Hermes + Bot Telegram (run sur Replit)
│   zeusdl.sh           # Script shell launcher
│
colab/
│   agent.ipynb         # Notebook Google Colab pour lancer un agent worker
│
client/                 # Client Flutter multi-plateformes (GUI)
│   lib/
│   │   main.dart
│   │   core/           # Theme, router, providers
│   │   features/       # home, downloads, agents, history, settings
│   │   shared/         # widgets, animations
│   android/            # Build Android
│   linux/              # Build Linux
│   windows/            # Build Windows
│   pubspec.yaml
│
scripts/
│   build_all.sh             # Build toutes les plateformes
│   build_android_armv8.sh   # Build Android arm64-v8a uniquement
```

## Architecture

- **Mastermind** (Replit) : serveur HTTP centralisé qui coordonne les agents, reçoit les connexions, distribue les ordres via bot Telegram.
- **Agent Colab** : instance Google Colab qui se connecte au Mastermind, télécharge les vidéos et les envoie sur Telegram.
- **Client Flutter** : interface graphique locale (Windows/Linux/Android) pour piloter le système via l'API Mastermind.

## Client Flutter

### Technologies

- **State** : flutter_riverpod + riverpod_annotation
- **Navigation** : go_router (deep linking, shell routes)
- **UI** : Material 3, flex_color_scheme, flutter_animate
- **Network** : dio + web_socket_channel
- **Storage** : hive_flutter (persistance locale)
- **Charts** : fl_chart, percent_indicator

### Build

```bash
# Toutes les plateformes
./scripts/build_all.sh --release

# Android ARMv8 uniquement
./scripts/build_android_armv8.sh --release
```

### Prérequis build

- Flutter SDK >= 3.22.0
- Android SDK + NDK (pour Android)
- cmake + ninja (pour Linux)
- Visual Studio 2022 + Windows SDK (pour Windows)

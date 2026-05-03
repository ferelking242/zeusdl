#!/usr/bin/env bash
# ============================================================
#  ZeusDL Client — Build Android ARMv8 (arm64-v8a) UNIQUEMENT
#  Usage: ./scripts/build_android_armv8.sh [--release|--profile|--debug]
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="$SCRIPT_DIR/../client"
BUILD_MODE="${1:---release}"
FLUTTER="${FLUTTER_SDK:-flutter}"
OUTPUT_DIR="$CLIENT_DIR/build/app/outputs/flutter-apk"

echo "╔══════════════════════════════════════════════╗"
echo "║   ZeusDL Client — Android ARMv8 build        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Build mode  : $BUILD_MODE"
echo "Target ABI  : arm64-v8a"
echo "Client dir  : $CLIENT_DIR"
echo ""

cd "$CLIENT_DIR"

echo "→ Flutter pub get..."
"$FLUTTER" pub get

echo ""
echo "→ Code generation..."
"$FLUTTER" packages pub run build_runner build --delete-conflicting-outputs 2>/dev/null || true

echo ""
echo "→ Build APK arm64-v8a..."
"$FLUTTER" build apk $BUILD_MODE \
  --target-platform android-arm64 \
  --split-per-abi

APK_PATH="$OUTPUT_DIR/app-arm64-v8a-release.apk"

if [[ -f "$APK_PATH" ]]; then
  SIZE=$(du -sh "$APK_PATH" | cut -f1)
  echo ""
  echo "╔══════════════════════════════════════════════╗"
  echo "║              Build terminé ✓                 ║"
  echo "╠══════════════════════════════════════════════╣"
  echo "║  APK  : $APK_PATH"
  echo "║  Size : $SIZE"
  echo "╚══════════════════════════════════════════════╝"
else
  echo ""
  echo "╔══════════════════════════════════════════════╗"
  echo "║         Build terminé (vérifier output)      ║"
  echo "╠══════════════════════════════════════════════╣"
  echo "║  Output: $OUTPUT_DIR"
  ls "$OUTPUT_DIR" 2>/dev/null || echo "  (dossier vide)"
  echo "╚══════════════════════════════════════════════╝"
fi

echo ""
echo "→ Pour installer sur un appareil connecté :"
echo "   adb install -r $APK_PATH"

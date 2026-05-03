#!/usr/bin/env bash
# ============================================================
#  ZeusDL Client — Build ALL platforms
#  Usage: ./scripts/build_all.sh [--release]
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="$SCRIPT_DIR/../client"
BUILD_MODE="${1:---release}"
FLUTTER="${FLUTTER_SDK:-flutter}"

echo "╔══════════════════════════════════════════════╗"
echo "║     ZeusDL Client — Build ALL platforms      ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Build mode : $BUILD_MODE"
echo "Client dir : $CLIENT_DIR"
echo ""

cd "$CLIENT_DIR"

echo "→ Flutter pub get..."
"$FLUTTER" pub get

echo ""
echo "→ Code generation..."
"$FLUTTER" packages pub run build_runner build --delete-conflicting-outputs || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [1/4] Android (arm64-v8a + armeabi-v7a + x86_64)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
"$FLUTTER" build apk $BUILD_MODE --split-per-abi
echo "  ✓ APKs : build/app/outputs/flutter-apk/"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [2/4] Android AAB (Play Store)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
"$FLUTTER" build appbundle $BUILD_MODE
echo "  ✓ AAB : build/app/outputs/bundle/release/"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [3/4] Linux (x86_64)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if command -v cmake &>/dev/null && command -v ninja &>/dev/null; then
  "$FLUTTER" build linux $BUILD_MODE
  echo "  ✓ Linux : build/linux/x64/release/bundle/"
else
  echo "  ⚠ cmake/ninja non trouvé — Linux build ignoré"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [4/4] Windows (x86_64)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$OSTYPE" == "msys"* ]] || [[ "$OSTYPE" == "cygwin"* ]] || [[ "$OS" == "Windows_NT" ]]; then
  "$FLUTTER" build windows $BUILD_MODE
  echo "  ✓ Windows : build/windows/runner/Release/"
else
  echo "  ⚠ Windows build disponible uniquement sur Windows"
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║              Build terminé ✓                 ║"
echo "╚══════════════════════════════════════════════╝"

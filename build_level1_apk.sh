#!/bin/bash
set -euo pipefail

# Build a much smaller diagnostic/quick-install APK containing only Oxford
# Reading Tree Level 1 (60 books), while keeping the Green Island story.
# Useful when the full 1 GB APK is inconvenient to install.

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/Users/henry/Library/Android/sdk}}"
PLATFORM="$SDK_ROOT/platforms/android-34/android.jar"
if [ -x "/opt/homebrew/share/android-commandlinetools/build-tools/36.0.0/aapt2" ]; then
    BUILD_TOOLS="/opt/homebrew/share/android-commandlinetools/build-tools/36.0.0"
else
    BUILD_TOOLS="$SDK_ROOT/build-tools/34.0.0"
fi
JAVA_HOME="${JAVA_HOME:-/Applications/DevEco-Studio.app/Contents/jbr/Contents/Home}"
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"
JAVAC="$JAVA_HOME/bin/javac"

TMP="/tmp/pbe_level1_build"
OUT="$PROJECT_DIR/build/manual"
rm -rf "$TMP"
mkdir -p "$TMP/assets/oxford/pdf" "$TMP/assets/oxford/audio" "$TMP/assets/oxford/covers" "$TMP/assets/oxford/text" "$TMP/gen" "$OUT"
cp -R app/src/main/res "$TMP/res"

# Base story assets.
cp app/src/main/assets/story.json "$TMP/assets/"
cp app/src/main/assets/home_hero.jpg "$TMP/assets/"
cp -R app/src/main/assets/pages "$TMP/assets/"

# Level 1 book assets.
cp app/src/main/assets/oxford/dictionary.json "$TMP/assets/oxford/"
cp app/src/main/assets/oxford/pdf/L1-*.pdf "$TMP/assets/oxford/pdf/"
cp app/src/main/assets/oxford/audio/L1-*.m4a "$TMP/assets/oxford/audio/"
cp app/src/main/assets/oxford/covers/L1-*.jpg "$TMP/assets/oxford/covers/"
cp app/src/main/assets/oxford/text/L1-*.json "$TMP/assets/oxford/text/"

python3 - "$TMP" <<'PY'
import json, sys, os
tmp = sys.argv[1]
src = 'app/src/main/assets/oxford/library.json'
d = json.load(open(src, encoding='utf-8'))
d['levels'] = [l for l in d['levels'] if l['level'] == 1]
json.dump(d, open(os.path.join(tmp, 'assets/oxford/library.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2, sort_keys=True)
PY

# Level 1 counts.
python3 - "$TMP/res/values/strings.xml" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding='utf-8').read()
s = s.replace('Oxford Reading Tree · 243 本', 'Oxford Reading Tree · 60 本')
s = s.replace('Level 1–9 · 原版 PDF + 美音音频', 'Level 1 · 60 本原版绘本')
open(p, 'w', encoding='utf-8').write(s)
PY

echo "==> Compiling resources"
"$BUILD_TOOLS/aapt2" compile --dir "$TMP/res" -o "$TMP/res.zip"

echo "==> Linking Level 1 assets"
"$BUILD_TOOLS/aapt2" link \
    -o "$TMP/base.apk" \
    -I "$PLATFORM" \
    --manifest app/src/main/AndroidManifest.xml \
    -A "$TMP/assets" \
    --java "$TMP/gen" \
    --min-sdk-version 23 \
    --target-sdk-version 34 \
    --version-code 4 \
    --version-name 3.0-L1 \
    --auto-add-overlay \
    -0 .pdf -0 .m4a \
    "$TMP/res.zip"

echo "==> Compiling Java"
find app/src/main/java "$TMP/gen" -name '*.java' > "$TMP/sources.txt"
mkdir -p "$TMP/classes"
"$JAVAC" -encoding UTF-8 -source 8 -target 8 -classpath "$PLATFORM" \
    -d "$TMP/classes" @"$TMP/sources.txt"

echo "==> Dexing"
mkdir -p "$TMP/dex"
"$BUILD_TOOLS/d8" --min-api 23 --lib "$PLATFORM" --output "$TMP/dex" \
    $(find "$TMP/classes" -name '*.class')

echo "==> Packaging"
cp "$TMP/base.apk" "$TMP/unsigned.apk"
(cd "$TMP/dex" && zip -q -j ../unsigned.apk classes.dex)
"$BUILD_TOOLS/zipalign" -f 4 "$TMP/unsigned.apk" "$TMP/aligned.apk"
if [ ! -f "$OUT/debug.keystore" ]; then
    "$JAVA_HOME/bin/keytool" -genkeypair -keystore "$OUT/debug.keystore" \
        -storepass android -alias androiddebugkey -keypass android \
        -keyalg RSA -keysize 2048 -validity 10000 \
        -dname "CN=Android Debug,O=Android,C=US" >/dev/null 2>&1
fi
rm -f "$OUT/PictureBookEnglish-Level1.apk"
"$BUILD_TOOLS/apksigner" sign \
    --ks "$OUT/debug.keystore" --ks-pass pass:android --key-pass pass:android \
    --out "$OUT/PictureBookEnglish-Level1.apk" "$TMP/aligned.apk"
"$BUILD_TOOLS/apksigner" verify "$OUT/PictureBookEnglish-Level1.apk" >/dev/null
cp "$OUT/PictureBookEnglish-Level1.apk" "$PROJECT_DIR/../绘本英语-Level1.apk"

echo "==> Done"
ls -lh "$OUT/PictureBookEnglish-Level1.apk" "$PROJECT_DIR/../绘本英语-Level1.apk"

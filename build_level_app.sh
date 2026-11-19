#!/bin/bash
set -euo pipefail

# Build a standalone app for one Oxford level.
# Usage: ./build_level_app.sh 6
# Each level gets its own package name so Level 6-9 can be installed together.

LEVEL="${1:-}"
case "$LEVEL" in
    1|2|3|4|5|6|7|8|9) ;;
    *) echo "usage: $0 1-9"; exit 1 ;;
esac

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

PKG="com.henry.picturebook.l${LEVEL}"
TMP="/tmp/pbe_level${LEVEL}_app"
OUT="$PROJECT_DIR/build/manual"
rm -rf "$TMP"
mkdir -p "$TMP/assets/oxford/pdf" "$TMP/assets/oxford/audio" "$TMP/assets/oxford/covers" "$TMP/assets/oxford/text" "$TMP/gen" "$OUT"
cp -R app/src/main/res "$TMP/res"

# Base story assets.
cp app/src/main/assets/home_hero.jpg "$TMP/assets/"

# Level assets.
cp app/src/main/assets/oxford/dictionary.json "$TMP/assets/oxford/"
cp app/src/main/assets/oxford/pdf/L${LEVEL}-*.pdf "$TMP/assets/oxford/pdf/"
cp app/src/main/assets/oxford/audio/L${LEVEL}-*.m4a "$TMP/assets/oxford/audio/"
cp app/src/main/assets/oxford/covers/L${LEVEL}-*.jpg "$TMP/assets/oxford/covers/"
cp app/src/main/assets/oxford/text/L${LEVEL}-*.json "$TMP/assets/oxford/text/"

python3 - "$TMP" "$LEVEL" <<'PY'
import json, sys, os
tmp, level = sys.argv[1], int(sys.argv[2])
src = 'app/src/main/assets/oxford/library.json'
d = json.load(open(src, encoding='utf-8'))
d['levels'] = [l for l in d['levels'] if l['level'] == level]
json.dump(d, open(os.path.join(tmp, 'assets/oxford/library.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2, sort_keys=True)
print(len(d['levels'][0]['books']))
PY

COUNT=$(python3 - "$LEVEL" <<'PY'
import json, sys
level = int(sys.argv[1])
d = json.load(open('app/src/main/assets/oxford/library.json', encoding='utf-8'))
print(len([b for l in d['levels'] if l['level'] == level for b in l['books']]))
PY
)

python3 - "$TMP/res/values/strings.xml" "$LEVEL" "$COUNT" <<'PY'
import sys
p, level, count = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(p, encoding='utf-8').read()
s = s.replace('<string name="app_name">绘本英语</string>',
              f'<string name="app_name">绘本英语 L{level}</string>')
s = s.replace('Oxford Reading Tree · 243 本',
              f'Oxford Reading Tree · {count} 本')
s = s.replace('Level 1–9 · 原版 PDF + 美音音频',
              f'Level {level} · {count} 本原版绘本')
s = s.replace('Picture Book English · 牛津树分级阅读',
              f'Level {level} · 牛津树分级阅读')
s = s.replace('PICTURE BOOK ENGLISH',
              f'PICTURE BOOK ENGLISH · L{level}')
s = s.replace('Picture Book English · Oxford Reading Tree',
              f'Picture Book English · Level {level}')
open(p, 'w', encoding='utf-8').write(s)
PY

# Manifest with a distinct application id and fully qualified activity classes.
cp app/src/main/AndroidManifest.xml "$TMP/AndroidManifest.xml"
python3 - "$TMP/AndroidManifest.xml" "$PKG" <<'PY'
import sys
p, pkg = sys.argv[1], sys.argv[2]
s = open(p, encoding='utf-8').read()
s = s.replace('package="com.henry.greenisland"', f'package="{pkg}"')
for name in ['MainActivity', 'ReaderActivity', 'OxfordLibraryActivity', 'OxfordReaderActivity']:
    s = s.replace(f'android:name=".{name}"',
                  f'android:name="com.henry.greenisland.{name}"')
open(p, 'w', encoding='utf-8').write(s)
PY

echo "==> Compiling resources (Level $LEVEL)"
"$BUILD_TOOLS/aapt2" compile --dir "$TMP/res" -o "$TMP/res.zip"

echo "==> Linking Level $LEVEL assets"
"$BUILD_TOOLS/aapt2" link \
    -o "$TMP/base.apk" \
    -I "$PLATFORM" \
    --manifest "$TMP/AndroidManifest.xml" \
    --custom-package com.henry.greenisland \
    -A "$TMP/assets" \
    --java "$TMP/gen" \
    --min-sdk-version 23 \
    --target-sdk-version 34 \
    --version-code 1 \
    --version-name "1.0-L${LEVEL}" \
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
rm -f "$OUT/PictureBookEnglish-L${LEVEL}.apk"
"$BUILD_TOOLS/apksigner" sign \
    --ks "$OUT/debug.keystore" --ks-pass pass:android --key-pass pass:android \
    --out "$OUT/PictureBookEnglish-L${LEVEL}.apk" "$TMP/aligned.apk"
"$BUILD_TOOLS/apksigner" verify "$OUT/PictureBookEnglish-L${LEVEL}.apk" >/dev/null
cp "$OUT/PictureBookEnglish-L${LEVEL}.apk" "$PROJECT_DIR/../绘本英语-L${LEVEL}.apk"

echo "==> Done L${LEVEL}"
ls -lh "$OUT/PictureBookEnglish-L${LEVEL}.apk" "$PROJECT_DIR/../绘本英语-L${LEVEL}.apk"

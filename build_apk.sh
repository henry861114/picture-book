#!/bin/bash
set -euo pipefail

# Build the Picture Book English APK without Gradle.
# Requirements: Android SDK platform android-34, build-tools 36 (or 34), JDK 17+.

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

OUT="$PROJECT_DIR/build/manual"
mkdir -p "$OUT"

echo "==> Compiling resources"
rm -rf "$OUT/res.zip" "$OUT/gen"
mkdir -p "$OUT/gen"
"$BUILD_TOOLS/aapt2" compile --dir app/src/main/res -o "$OUT/res.zip"

echo "==> Linking resources and assets"
rm -f "$OUT/base.apk"
"$BUILD_TOOLS/aapt2" link \
    -o "$OUT/base.apk" \
    -I "$PLATFORM" \
    --manifest app/src/main/AndroidManifest.xml \
    -A app/src/main/assets \
    --java "$OUT/gen" \
    --min-sdk-version 23 \
    --target-sdk-version 34 \
    --version-code 17 \
    --version-name 3.8 \
    --auto-add-overlay \
    -0 .pdf \
    -0 .mp3 \
    -0 .m4a \
    "$OUT/res.zip"

echo "==> Compiling Java"
find app/src/main/java "$OUT/gen" -name '*.java' > "$OUT/sources.txt"
rm -rf "$OUT/classes"
mkdir -p "$OUT/classes"
"$JAVAC" -encoding UTF-8 -source 8 -target 8 \
    -classpath "$PLATFORM" \
    -d "$OUT/classes" \
    @"$OUT/sources.txt"

echo "==> Dexing"
rm -rf "$OUT/dex"
mkdir -p "$OUT/dex"
"$BUILD_TOOLS/d8" --min-api 23 --lib "$PLATFORM" \
    --output "$OUT/dex" \
    $(find "$OUT/classes" -name '*.class')

echo "==> Packaging"
cp "$OUT/base.apk" "$OUT/unsigned.apk"
(cd "$OUT/dex" && zip -q -j ../unsigned.apk classes.dex)
"$BUILD_TOOLS/zipalign" -f 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"

echo "==> Signing"
if [ ! -f "$OUT/debug.keystore" ]; then
    "$JAVA_HOME/bin/keytool" -genkeypair \
        -keystore "$OUT/debug.keystore" \
        -storepass android -alias androiddebugkey -keypass android \
        -keyalg RSA -keysize 2048 -validity 10000 \
        -dname "CN=Android Debug,O=Android,C=US" >/dev/null 2>&1
fi
rm -f "$OUT/PictureBookEnglish.apk"
"$BUILD_TOOLS/apksigner" sign \
    --ks "$OUT/debug.keystore" \
    --ks-pass pass:android \
    --key-pass pass:android \
    --out "$OUT/PictureBookEnglish.apk" \
    "$OUT/aligned.apk"
"$BUILD_TOOLS/apksigner" verify "$OUT/PictureBookEnglish.apk" >/dev/null

cp "$OUT/PictureBookEnglish.apk" "$PROJECT_DIR/../绘本英语.apk"

echo "==> Done"
ls -lh "$OUT/PictureBookEnglish.apk" "$PROJECT_DIR/../绘本英语.apk"

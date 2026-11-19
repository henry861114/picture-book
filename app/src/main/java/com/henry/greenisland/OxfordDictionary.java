package com.henry.greenisland;

import android.content.Context;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Locale;
import java.util.Map;

/**
 * Offline English -> Chinese word lookup with a small amount of stemming so that
 * "played", "playing" and "plays" all find the entry for "play".
 */
public final class OxfordDictionary {

    public static final class Entry {
        public final String phonetic;
        public final String zh;

        Entry(String phonetic, String zh) {
            this.phonetic = phonetic;
            this.zh = zh;
        }
    }

    private static OxfordDictionary instance;
    private final Map<String, Entry> entries = new HashMap<>();

    private OxfordDictionary() {
    }

    public static OxfordDictionary get(Context context) {
        if (instance == null) {
            synchronized (OxfordDictionary.class) {
                if (instance == null) {
                    OxfordDictionary dictionary = new OxfordDictionary();
                    dictionary.loadInternal(context.getApplicationContext());
                    instance = dictionary;
                }
            }
        }
        return instance;
    }

    private void loadInternal(Context context) {
        try (InputStream input = context.getAssets().open("oxford/dictionary.json")) {
            String json = readAll(input);
            JSONObject root = new JSONObject(json);
            Iterator<String> keys = root.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                JSONObject object = root.optJSONObject(key);
                if (object == null) {
                    continue;
                }
                String phonetic = object.optString("p", "");
                String zh = object.optString("z", "");
                if (!zh.isEmpty()) {
                    entries.put(key.toLowerCase(Locale.US), new Entry(phonetic, zh));
                }
            }
        } catch (IOException | JSONException ignored) {
            // The reader still works without the dictionary.
        }
    }

    private static String readAll(InputStream input) throws IOException {
        StringBuilder builder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(input, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                builder.append(line).append('\n');
            }
        }
        return builder.toString();
    }

    public Entry lookup(String word) {
        if (word == null) {
            return null;
        }
        String w = word.toLowerCase(Locale.US).replace('’', '\'');
        w = w.replaceAll("^[^a-z']+|[^a-z']+$", "");
        if (w.isEmpty()) {
            return null;
        }
        Entry entry = entries.get(w);
        if (entry != null) {
            return entry;
        }
        for (String candidate : candidates(w)) {
            entry = entries.get(candidate);
            if (entry != null) {
                return entry;
            }
        }
        return null;
    }

    private static String[] candidates(String w) {
        String[] out = new String[10];
        int n = 0;
        String base = w;
        if (base.endsWith("'s") && base.length() > 2) {
            base = base.substring(0, base.length() - 2);
        }
        out[n++] = base;
        if (base.endsWith("ies") && base.length() > 4) {
            out[n++] = base.substring(0, base.length() - 3) + "y";
        }
        if (base.endsWith("es") && base.length() > 3) {
            out[n++] = base.substring(0, base.length() - 2);
        }
        if (base.endsWith("s") && base.length() > 2) {
            out[n++] = base.substring(0, base.length() - 1);
        }
        if (base.endsWith("ed") && base.length() > 3) {
            String stem = base.substring(0, base.length() - 2);
            out[n++] = stem;
            out[n++] = base.substring(0, base.length() - 1);
            if (stem.length() > 2 && stem.charAt(stem.length() - 1) == stem.charAt(stem.length() - 2)) {
                out[n++] = stem.substring(0, stem.length() - 1);
            }
        }
        if (base.endsWith("ing") && base.length() > 4) {
            String stem = base.substring(0, base.length() - 3);
            out[n++] = stem;
            out[n++] = stem + "e";
            if (stem.length() > 2 && stem.charAt(stem.length() - 1) == stem.charAt(stem.length() - 2)) {
                out[n++] = stem.substring(0, stem.length() - 1);
            }
        }
        String[] result = new String[n];
        System.arraycopy(out, 0, result, 0, n);
        return result;
    }
}

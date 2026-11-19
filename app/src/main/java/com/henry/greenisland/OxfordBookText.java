package com.henry.greenisland;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

/**
 * OCR text, Chinese glosses and estimated audio page times for one Oxford book.
 */
public final class OxfordBookText {

    public static final class Sentence {
        public final String en;
        public final String zh;
        public final int startMs;
        public final int endMs;

        Sentence(String en, String zh, int startMs, int endMs) {
            this.en = en;
            this.zh = zh;
            this.startMs = startMs;
            this.endMs = endMs;
        }

        public boolean hasAudioTiming() {
            return startMs >= 0 && endMs > startMs;
        }
    }

    public static final class Page {
        public final Sentence[] sentences;
        public final int startMs;
        public final int endMs;
        /** PDF page to render (0-based); -1 = same index as this page. */
        public final int pdfPage;
        /** Optional crop rect within the rendered PDF page (0..1), or null. */
        public final float[] rect;

        Page(Sentence[] sentences, int startMs, int endMs,
             int pdfPage, float[] rect) {
            this.sentences = sentences;
            this.startMs = startMs;
            this.endMs = endMs;
            this.pdfPage = pdfPage;
            this.rect = rect;
        }
    }

    private final Page[] pages;

    private OxfordBookText(Page[] pages) {
        this.pages = pages;
    }

    public static OxfordBookText load(Context context, String bookId) {
        try (InputStream input = context.getAssets().open("oxford/text/" + bookId + ".json")) {
            String json = readAll(input);
            JSONObject root = new JSONObject(json);
            JSONArray pageArray = root.getJSONArray("pages");
            Page[] pages = new Page[pageArray.length()];
            for (int i = 0; i < pageArray.length(); i++) {
                JSONObject pageObject = pageArray.getJSONObject(i);
                JSONArray sentenceArray = pageObject.optJSONArray("sentences");
                int count = sentenceArray == null ? 0 : sentenceArray.length();
                Sentence[] sentences = new Sentence[count];
                for (int j = 0; j < count; j++) {
                    JSONObject sentenceObject = sentenceArray.getJSONObject(j);
                    sentences[j] = new Sentence(
                            sentenceObject.optString("en", ""),
                            sentenceObject.optString("zh", ""),
                            sentenceObject.optInt("startMs", -1),
                            sentenceObject.optInt("endMs", -1)
                    );
                }
                int pdfPage = pageObject.optInt("pdfPage", -1);
                float[] rect = null;
                JSONArray rectArray = pageObject.optJSONArray("rect");
                if (rectArray != null && rectArray.length() == 4) {
                    rect = new float[4];
                    for (int r = 0; r < 4; r++) {
                        rect[r] = (float) rectArray.optDouble(r, 0.0);
                    }
                }
                pages[i] = new Page(
                        sentences,
                        pageObject.optInt("startMs", 0),
                        pageObject.optInt("endMs", 0),
                        pdfPage,
                        rect
                );
            }
            return new OxfordBookText(pages);
        } catch (IOException | JSONException e) {
            return new OxfordBookText(new Page[0]);
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

    public int size() {
        return pages.length;
    }

    public Page getPage(int index) {
        if (index < 0 || index >= pages.length) {
            return null;
        }
        return pages[index];
    }
}

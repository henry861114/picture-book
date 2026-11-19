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

public final class StoryRepository {

    public static final class Segment {
        public final String en;
        public final String zh;

        Segment(String en, String zh) {
            this.en = en;
            this.zh = zh;
        }
    }

    public static final class Page {
        public final String image;
        public final Segment[] segments;

        Page(String image, Segment[] segments) {
            this.image = image;
            this.segments = segments;
        }
    }

    private final String title;
    private final String subtitle;
    private final Page[] pages;

    private StoryRepository(String title, String subtitle, Page[] pages) {
        this.title = title;
        this.subtitle = subtitle;
        this.pages = pages;
    }

    public static StoryRepository load(Context context) {
        try (InputStream input = context.getAssets().open("story.json")) {
            String json = readAll(input);
            JSONObject root = new JSONObject(json);
            String title = root.optString("title", "Green Island");
            String subtitle = root.optString("subtitle", "");
            JSONArray pageArray = root.getJSONArray("pages");
            Page[] pages = new Page[pageArray.length()];
            for (int i = 0; i < pageArray.length(); i++) {
                JSONObject pageObject = pageArray.getJSONObject(i);
                String image = pageObject.getString("image");
                JSONArray segmentArray = pageObject.getJSONArray("segments");
                Segment[] segments = new Segment[segmentArray.length()];
                for (int j = 0; j < segmentArray.length(); j++) {
                    JSONObject segmentObject = segmentArray.getJSONObject(j);
                    segments[j] = new Segment(
                            segmentObject.getString("en"),
                            segmentObject.getString("zh")
                    );
                }
                pages[i] = new Page(image, segments);
            }
            return new StoryRepository(title, subtitle, pages);
        } catch (IOException | JSONException e) {
            throw new IllegalStateException("Unable to load story.json", e);
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

    public String getTitle() {
        return title;
    }

    public String getSubtitle() {
        return subtitle;
    }

    public int size() {
        return pages.length;
    }

    public Page getPage(int index) {
        return pages[index];
    }
}

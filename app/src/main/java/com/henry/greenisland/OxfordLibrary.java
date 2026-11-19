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
import java.util.HashMap;
import java.util.Map;

/**
 * Loads the Oxford Reading Tree library index from assets/oxford/library.json.
 */
public final class OxfordLibrary {

    public static final class Book {
        public final String id;
        public final String title;
        public final String pdf;
        public final String audio;
        public final String cover;
        public final int level;
        public final int number;
        public final int pages;
        public final float aspect;

        Book(String id, String title, String pdf, String audio, String cover,
             int level, int number, int pages, float aspect) {
            this.id = id;
            this.title = title;
            this.pdf = pdf;
            this.audio = audio;
            this.cover = cover;
            this.level = level;
            this.number = number;
            this.pages = pages;
            this.aspect = aspect;
        }

        public boolean hasAudio() {
            return audio != null && !audio.isEmpty();
        }
    }

    public static final class Level {
        public final int level;
        public final String name;
        public final String nameCn;
        public final Book[] books;

        Level(int level, String name, String nameCn, Book[] books) {
            this.level = level;
            this.name = name;
            this.nameCn = nameCn;
            this.books = books;
        }
    }

    private final String title;
    private final String titleCn;
    private final Level[] levels;
    private final Map<String, Book> booksById;

    private OxfordLibrary(String title, String titleCn, Level[] levels) {
        this.title = title;
        this.titleCn = titleCn;
        this.levels = levels;
        this.booksById = new HashMap<>();
        for (Level level : levels) {
            for (Book book : level.books) {
                booksById.put(book.id, book);
            }
        }
    }

    public static OxfordLibrary load(Context context) {
        try (InputStream input = context.getAssets().open("oxford/library.json")) {
            String json = readAll(input);
            JSONObject root = new JSONObject(json);
            String title = root.optString("title", "Oxford Reading Tree");
            String titleCn = root.optString("titleCn", "牛津树分级绘本");
            JSONArray levelArray = root.getJSONArray("levels");
            Level[] levels = new Level[levelArray.length()];
            for (int i = 0; i < levelArray.length(); i++) {
                JSONObject levelObject = levelArray.getJSONObject(i);
                int levelNumber = levelObject.getInt("level");
                String name = levelObject.optString("name", "Level " + levelNumber);
                String nameCn = levelObject.optString("nameCn", "第 " + levelNumber + " 级");
                JSONArray bookArray = levelObject.getJSONArray("books");
                Book[] books = new Book[bookArray.length()];
                for (int j = 0; j < bookArray.length(); j++) {
                    JSONObject bookObject = bookArray.getJSONObject(j);
                    books[j] = new Book(
                            bookObject.getString("id"),
                            bookObject.getString("title"),
                            bookObject.getString("pdf"),
                            bookObject.optString("audio", null),
                            bookObject.getString("cover"),
                            levelNumber,
                            bookObject.optInt("number", j + 1),
                            bookObject.optInt("pages", 1),
                            (float) bookObject.optDouble("aspect", 0.75)
                    );
                }
                levels[i] = new Level(levelNumber, name, nameCn, books);
            }
            return new OxfordLibrary(title, titleCn, levels);
        } catch (IOException | JSONException e) {
            throw new IllegalStateException("Unable to load oxford/library.json", e);
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

    public String getTitleCn() {
        return titleCn;
    }

    public Level[] getLevels() {
        return levels;
    }

    public Book findBook(String id) {
        return booksById.get(id);
    }

    public int getBookCount() {
        return booksById.size();
    }
}

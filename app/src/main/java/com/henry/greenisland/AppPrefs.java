package com.henry.greenisland;

import android.content.Context;
import android.content.SharedPreferences;

public final class AppPrefs {
    private static final String NAME = "green_island_prefs";
    private static final String KEY_LAST_PAGE = "last_page";
    private static final String KEY_OXFORD_LEVEL = "oxford_level";
    private static final String KEY_LEVEL_VERSION = "oxford_level_version";

    private AppPrefs() {
    }

    public static int getLastPage(Context context) {
        return context.getSharedPreferences(NAME, Context.MODE_PRIVATE)
                .getInt(KEY_LAST_PAGE, -1);
    }

    public static void setLastPage(Context context, int page) {
        SharedPreferences prefs = context.getSharedPreferences(NAME, Context.MODE_PRIVATE);
        prefs.edit().putInt(KEY_LAST_PAGE, page).apply();
    }

    public static int getOxfordLevel(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(NAME, Context.MODE_PRIVATE);
        // One-time migration: the default level is now Level 5 (index 4).
        if (prefs.getInt(KEY_LEVEL_VERSION, 0) < 2) {
            prefs.edit()
                    .putInt(KEY_OXFORD_LEVEL, 4)
                    .putInt(KEY_LEVEL_VERSION, 2)
                    .apply();
            return 4;
        }
        return prefs.getInt(KEY_OXFORD_LEVEL, 4);
    }

    public static void setOxfordLevel(Context context, int levelIndex) {
        SharedPreferences prefs = context.getSharedPreferences(NAME, Context.MODE_PRIVATE);
        prefs.edit()
                .putInt(KEY_OXFORD_LEVEL, levelIndex)
                .putInt(KEY_LEVEL_VERSION, 2)
                .apply();
    }

    /** Returns the last page read in a book, or -1 if the book has not been opened. */
    public static int getBookPage(Context context, String bookId) {
        return context.getSharedPreferences(NAME, Context.MODE_PRIVATE)
                .getInt(bookKey(bookId), -1);
    }

    public static void setBookPage(Context context, String bookId, int page) {
        SharedPreferences prefs = context.getSharedPreferences(NAME, Context.MODE_PRIVATE);
        prefs.edit().putInt(bookKey(bookId), page).apply();
    }

    private static String bookKey(String bookId) {
        return "book_page_" + bookId;
    }
}

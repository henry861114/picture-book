package com.henry.greenisland;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Typeface;
import android.os.Bundle;
import android.util.LruCache;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.GridView;
import android.widget.HorizontalScrollView;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.io.InputStream;
import java.util.Locale;

public class OxfordLibraryActivity extends Activity {

    public static final String EXTRA_BOOK_ID = "extra_book_id";

    private OxfordLibrary library;
    private int currentLevelIndex;
    private GridView bookGrid;
    private LinearLayout levelChips;
    private HorizontalScrollView levelScroll;
    private TextView levelSummary;
    private TextView levelSummaryTop;
    private BookAdapter adapter;
    private LruCache<String, Bitmap> coverCache;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_oxford_library);

        try {
            library = OxfordLibrary.load(this);
        } catch (RuntimeException e) {
            Toast.makeText(this, R.string.book_open_failed, Toast.LENGTH_LONG).show();
            finish();
            return;
        }

        int maxCache = (int) (Runtime.getRuntime().maxMemory() / 8);
        coverCache = new LruCache<String, Bitmap>(Math.min(maxCache, 28 * 1024 * 1024)) {
            @Override
            protected int sizeOf(String key, Bitmap value) {
                return value.getByteCount();
            }
        };

        bookGrid = findViewById(R.id.bookGrid);
        levelChips = findViewById(R.id.levelChips);
        levelScroll = findViewById(R.id.levelScroll);
        levelSummary = findViewById(R.id.levelSummary);
        levelSummaryTop = findViewById(R.id.levelSummaryTop);
        ImageButton back = findViewById(R.id.btnBack);
        back.setOnClickListener(v -> {
            finish();
            overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out);
        });

        adapter = new BookAdapter();
        bookGrid.setAdapter(adapter);

        buildLevelChips();
        int startLevel = AppPrefs.getOxfordLevel(this);
        selectLevel(startLevel, false);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (adapter != null) {
            adapter.notifyDataSetChanged();
        }
    }

    private void buildLevelChips() {
        levelChips.removeAllViews();
        OxfordLibrary.Level[] levels = library.getLevels();
        for (int i = 0; i < levels.length; i++) {
            final int index = i;
            TextView chip = new TextView(this);
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(44), dp(38));
            params.setMarginEnd(dp(7));
            chip.setLayoutParams(params);
            chip.setGravity(Gravity.CENTER);
            chip.setText(String.format(Locale.US, "L%d", levels[i].level));
            chip.setTextSize(12f);
            chip.setTypeface(null, Typeface.BOLD);
            chip.setClickable(true);
            chip.setFocusable(true);
            chip.setOnClickListener(v -> selectLevel(index, true));
            levelChips.addView(chip);
        }
    }

    private void selectLevel(int index, boolean scrollToChip) {
        OxfordLibrary.Level[] levels = library.getLevels();
        if (levels.length == 0) {
            return;
        }
        currentLevelIndex = Math.max(0, Math.min(index, levels.length - 1));
        AppPrefs.setOxfordLevel(this, currentLevelIndex);

        for (int i = 0; i < levelChips.getChildCount(); i++) {
            TextView chip = (TextView) levelChips.getChildAt(i);
            boolean selected = i == currentLevelIndex;
            chip.setBackgroundResource(selected
                    ? R.drawable.bg_level_chip_selected
                    : R.drawable.bg_level_chip);
            chip.setTextColor(getColor(selected ? R.color.white : R.color.green_700));
        }

        OxfordLibrary.Level level = levels[currentLevelIndex];
        levelSummary.setText(getString(R.string.level_summary, level.level, level.books.length));
        levelSummaryTop.setText(String.format(Locale.US, "L%d · %d", level.level, level.books.length));
        adapter.notifyDataSetChanged();
        bookGrid.setSelection(0);

        if (scrollToChip && currentLevelIndex < levelChips.getChildCount()) {
            View chip = levelChips.getChildAt(currentLevelIndex);
            levelScroll.post(() -> levelScroll.smoothScrollTo(
                    Math.max(0, chip.getLeft() - dp(16)), 0));
        }
    }

    /**
     * New books open on the first page that actually has text, so the reader
     * immediately sees the picture and the sentences instead of a wordless cover.
     */
    private int firstPageWithText(OxfordLibrary.Book book) {
        try {
            OxfordBookText text = OxfordBookText.load(this, book.id);
            for (int i = 1; i < text.size(); i++) {
                OxfordBookText.Page page = text.getPage(i);
                if (page != null && page.sentences.length > 0) {
                    return i;
                }
            }
        } catch (RuntimeException ignored) {
        }
        return 0;
    }

    private void openBook(int position) {
        OxfordLibrary.Level level = library.getLevels()[currentLevelIndex];
        if (position < 0 || position >= level.books.length) {
            return;
        }
        OxfordLibrary.Book book = level.books[position];
        int page = AppPrefs.getBookPage(this, book.id);
        if (page < 0 || page >= book.pages) {
            page = firstPageWithText(book);
        }
        Intent intent = new Intent(this, OxfordReaderActivity.class);
        intent.putExtra(EXTRA_BOOK_ID, book.id);
        intent.putExtra(OxfordReaderActivity.EXTRA_PAGE, page);
        startActivity(intent);
        overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out);
    }

    private Bitmap loadCover(String assetPath) {
        Bitmap cached = coverCache.get(assetPath);
        if (cached != null) {
            return cached;
        }
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = 1;
        options.inPreferredConfig = Bitmap.Config.RGB_565;
        try (InputStream input = getAssets().open(assetPath)) {
            Bitmap bitmap = BitmapFactory.decodeStream(input, null, options);
            if (bitmap != null) {
                coverCache.put(assetPath, bitmap);
            }
            return bitmap;
        } catch (Exception ignored) {
            return null;
        }
    }

    private class BookAdapter extends BaseAdapter {

        @Override
        public int getCount() {
            return library.getLevels()[currentLevelIndex].books.length;
        }

        @Override
        public Object getItem(int position) {
            return library.getLevels()[currentLevelIndex].books[position];
        }

        @Override
        public long getItemId(int position) {
            return position;
        }

        @Override
        public View getView(int position, View convertView, ViewGroup parent) {
            View view = convertView;
            ViewHolder holder;
            if (view == null) {
                view = getLayoutInflater().inflate(R.layout.item_oxford_book, parent, false);
                holder = new ViewHolder();
                holder.cover = view.findViewById(R.id.bookCover);
                holder.title = view.findViewById(R.id.bookTitle);
                holder.meta = view.findViewById(R.id.bookMeta);
                holder.badge = view.findViewById(R.id.bookBadge);
                view.setTag(holder);
            } else {
                holder = (ViewHolder) view.getTag();
            }

            OxfordLibrary.Book book = library.getLevels()[currentLevelIndex].books[position];
            holder.title.setText(book.title);
            int lastPage = AppPrefs.getBookPage(OxfordLibraryActivity.this, book.id);
            if (lastPage >= 0 && lastPage < book.pages) {
                holder.meta.setText(getString(R.string.book_progress, lastPage + 1));
                holder.badge.setText(String.format(Locale.US, "P%d", lastPage + 1));
                holder.badge.setVisibility(View.VISIBLE);
            } else {
                holder.meta.setText(getString(R.string.book_pages, book.pages));
                holder.badge.setVisibility(View.GONE);
            }

            holder.cover.setImageDrawable(null);
            Bitmap cover = loadCover(book.cover);
            if (cover != null) {
                holder.cover.setImageBitmap(cover);
            }
            view.setOnClickListener(v -> openBook(position));
            return view;
        }
    }

    private static class ViewHolder {
        ImageView cover;
        TextView title;
        TextView meta;
        TextView badge;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onDestroy() {
        if (coverCache != null) {
            coverCache.evictAll();
        }
        super.onDestroy();
    }
}

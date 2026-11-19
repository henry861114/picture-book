package com.henry.greenisland;

import android.Manifest;
import android.app.Activity;
import android.app.Dialog;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.Drawable;
import android.os.Build;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.TextPaint;
import android.text.method.LinkMovementMethod;
import android.text.style.ClickableSpan;
import android.view.GestureDetector;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.view.animation.DecelerateInterpolator;
import android.widget.AbsListView;
import android.widget.BaseAdapter;
import android.widget.FrameLayout;
import android.widget.GridView;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class ReaderActivity extends Activity {

    private static final int REQ_MIC = 73;
    private static final float READ_RATE = 0.82f;
    private static final float FOLLOW_RATE = 0.72f;
    private static final String READ_ID_PREFIX = "read_";
    private static final Pattern WORD_PATTERN =
            Pattern.compile("[A-Za-z]+(?:['’\\-][A-Za-z]+)*");

    private StoryRepository story;
    private StoryRepository.Page page;
    private int currentPage;
    private boolean allTranslations;

    private final List<SentenceRow> rows = new ArrayList<>();

    private ImageView pageImage;
    private TextView pageCounter;
    private TextView pageLabel;
    private TextView translationHint;
    private TextView sceneBadge;
    private TextView btnRead;
    private TextView btnFollow;
    private TextView btnTranslate;
    private FrameLayout progressTrack;
    private View progressFill;
    private ScrollView textScroll;
    private LinearLayout sentenceContainer;
    private ImageButton btnPrev;
    private ImageButton btnNext;
    private ImageButton btnHome;
    private View imageCard;
    private View textSheet;

    private TextToSpeech tts;
    private boolean ttsReady;
    private boolean isReading;
    private boolean singleShot;
    private int readingIndex = -1;
    private int readingPage = -1;
    private int readGeneration;
    private boolean destroyed;

    private Bitmap currentBitmap;
    private GestureDetector gestureDetector;
    private FollowReadingDialog followDialog;
    private boolean pendingFollowOpen;
    private int pendingFollowStart;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_reader);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        configureSystemBars();

        try {
            story = StoryRepository.load(this);
        } catch (RuntimeException e) {
            Toast.makeText(this, "故事内容加载失败", Toast.LENGTH_LONG).show();
            finish();
            return;
        }

        bindViews();
        setupClicks();
        setupGestures();
        initTts();

        int startPage = getIntent().getIntExtra(MainActivity.EXTRA_PAGE, AppPrefs.getLastPage(this));
        if (startPage < 0 || startPage >= story.size()) {
            startPage = 0;
        }
        currentPage = startPage;
        showPage(currentPage, 0);
    }

    private void configureSystemBars() {
        Window window = getWindow();
        int flags = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        }
        window.getDecorView().setSystemUiVisibility(flags);
    }

    private void bindViews() {
        pageImage = findViewById(R.id.pageImage);
        pageCounter = findViewById(R.id.pageCounter);
        pageLabel = findViewById(R.id.pageLabel);
        translationHint = findViewById(R.id.translationHint);
        sceneBadge = findViewById(R.id.sceneBadge);
        btnRead = findViewById(R.id.btnRead);
        btnFollow = findViewById(R.id.btnFollow);
        btnTranslate = findViewById(R.id.btnTranslate);
        progressTrack = findViewById(R.id.progressTrack);
        progressFill = findViewById(R.id.progressFill);
        textScroll = findViewById(R.id.textScroll);
        sentenceContainer = findViewById(R.id.sentenceContainer);
        btnPrev = findViewById(R.id.btnPrev);
        btnNext = findViewById(R.id.btnNext);
        btnHome = findViewById(R.id.btnHome);
        imageCard = findViewById(R.id.imageCard);
        textSheet = findViewById(R.id.textSheet);
    }

    private void setupClicks() {
        btnHome.setOnClickListener(v -> {
            finish();
            overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out);
        });
        btnPrev.setOnClickListener(v -> goTo(currentPage - 1));
        btnNext.setOnClickListener(v -> goTo(currentPage + 1));
        pageCounter.setOnClickListener(v -> showPageChooser());
        btnRead.setOnClickListener(v -> {
            if (isReading) {
                stopReading();
            } else {
                startReading(0);
            }
        });
        btnFollow.setOnClickListener(v -> requestFollow());
        btnTranslate.setOnClickListener(v -> toggleAllTranslations());
    }

    private void setupGestures() {
        gestureDetector = new GestureDetector(this, new SwipeListener());
    }

    private class SwipeListener extends GestureDetector.SimpleOnGestureListener {
        @Override
        public boolean onFling(MotionEvent e1, MotionEvent e2, float velocityX, float velocityY) {
            if (e1 == null || e2 == null) {
                return false;
            }
            float dx = e2.getX() - e1.getX();
            float dy = e2.getY() - e1.getY();
            if (Math.abs(dx) > dp(70)
                    && Math.abs(dx) > Math.abs(dy) * 1.35f
                    && Math.abs(velocityX) > 220f) {
                if (dx < 0) {
                    goTo(currentPage + 1);
                } else {
                    goTo(currentPage - 1);
                }
                return true;
            }
            return false;
        }
    }

    @Override
    public boolean dispatchTouchEvent(MotionEvent ev) {
        if (gestureDetector != null) {
            gestureDetector.onTouchEvent(ev);
        }
        return super.dispatchTouchEvent(ev);
    }

    private void initTts() {
        tts = new TextToSpeech(getApplicationContext(), status -> runOnUiThread(() -> {
            if (destroyed) {
                return;
            }
            if (status != TextToSpeech.SUCCESS) {
                toast(R.string.tts_unavailable);
                return;
            }
            int result = tts.setLanguage(Locale.UK);
            if (result == TextToSpeech.LANG_MISSING_DATA
                    || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                result = tts.setLanguage(Locale.US);
            }
            if (result == TextToSpeech.LANG_MISSING_DATA
                    || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                toast(R.string.tts_unavailable);
                return;
            }
            tts.setSpeechRate(READ_RATE);
            tts.setPitch(1.0f);
            tts.setOnUtteranceProgressListener(new TtsListener());
            ttsReady = true;
        }));
    }

    private class TtsListener extends UtteranceProgressListener {
        @Override
        public void onStart(String utteranceId) {
        }

        @Override
        public void onDone(String utteranceId) {
            runOnUiThread(() -> handleTtsDone(utteranceId));
        }

        @Override
        public void onError(String utteranceId) {
            runOnUiThread(() -> handleTtsError(utteranceId));
        }
    }

    private void handleTtsDone(String utteranceId) {
        if (destroyed || !utteranceId.startsWith(READ_ID_PREFIX)) {
            return;
        }
        int[] parsed = parseReadId(utteranceId);
        if (parsed == null || !isReading || parsed[0] != readGeneration
                || readingPage != currentPage || page == null) {
            return;
        }
        if (singleShot) {
            finishReading();
            return;
        }
        if (parsed[1] >= page.segments.length - 1) {
            if (currentPage < story.size() - 1) {
                showPage(currentPage + 1, 1, true);
                readingPage = currentPage;
                readSegment(0);
            } else {
                finishReading();
            }
        } else {
            readSegment(parsed[1] + 1);
        }
    }

    private void handleTtsError(String utteranceId) {
        if (destroyed || !utteranceId.startsWith(READ_ID_PREFIX)) {
            return;
        }
        int[] parsed = parseReadId(utteranceId);
        if (parsed == null || !isReading || parsed[0] != readGeneration) {
            return;
        }
        finishReading();
        toast(R.string.tts_error);
    }

    private int[] parseReadId(String id) {
        String[] parts = id.split("_");
        if (parts.length != 3) {
            return null;
        }
        try {
            return new int[]{Integer.parseInt(parts[1]), Integer.parseInt(parts[2])};
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private void startReading(int startIndex) {
        if (!ttsReady) {
            toast(R.string.tts_preparing);
            return;
        }
        stopReading();
        if (page == null || page.segments.length == 0) {
            return;
        }
        isReading = true;
        singleShot = false;
        readingPage = currentPage;
        readGeneration++;
        updateReadingButton();
        readSegment(Math.max(0, Math.min(startIndex, page.segments.length - 1)));
    }

    private void speakSingle(int index) {
        if (!ttsReady) {
            toast(R.string.tts_preparing);
            return;
        }
        stopReading();
        if (page == null || index < 0 || index >= page.segments.length) {
            return;
        }
        isReading = true;
        singleShot = true;
        readingPage = currentPage;
        readGeneration++;
        updateReadingButton();
        readSegment(index);
    }

    private void readSegment(int index) {
        if (!isReading || page == null || index < 0 || index >= page.segments.length) {
            finishReading();
            return;
        }
        readingIndex = index;
        highlightRow(index);
        scrollToRow(index);

        tts.setSpeechRate(READ_RATE);
        tts.setPitch(1.0f);
        String id = READ_ID_PREFIX + readGeneration + "_" + index;
        int result = tts.speak(page.segments[index].en, TextToSpeech.QUEUE_FLUSH, null, id);
        if (result == TextToSpeech.ERROR) {
            finishReading();
            toast(R.string.tts_error);
        }
    }

    private void finishReading() {
        isReading = false;
        singleShot = false;
        readingIndex = -1;
        clearHighlights();
        updateReadingButton();
    }

    private void stopReading() {
        readGeneration++;
        if (tts != null) {
            tts.stop();
        }
        isReading = false;
        singleShot = false;
        readingIndex = -1;
        clearHighlights();
        updateReadingButton();
    }

    private void updateReadingButton() {
        if (btnRead == null) {
            return;
        }
        if (isReading) {
            btnRead.setText(R.string.stop_reading);
        } else {
            btnRead.setText(R.string.read_page);
        }
    }

    private void showPage(int index, int direction) {
        showPage(index, direction, false);
    }

    private void showPage(int index, int direction, boolean keepReading) {
        if (story == null || index < 0 || index >= story.size()) {
            return;
        }
        if (!keepReading) {
            stopReading();
        }
        currentPage = index;
        page = story.getPage(index);
        loadImage(page);

        pageCounter.setText(getString(R.string.page_counter, index + 1, story.size()));
        pageLabel.setText(getString(R.string.story_label, index + 1));
        sceneBadge.setText(getString(R.string.scene_badge, index + 1));
        translationHint.setText(R.string.tap_for_translation);
        allTranslations = false;
        updateTranslateButton();
        buildSentences(page);
        textScroll.scrollTo(0, 0);
        updateNavButtons();
        updateProgress();
        AppPrefs.setLastPage(this, index);

        int offset = direction == 0 ? 0 : direction * dp(26);
        animateIn(imageCard, offset);
        animateIn(textSheet, offset);
    }

    private void animateIn(View view, int offset) {
        if (view == null) {
            return;
        }
        view.animate().cancel();
        view.setTranslationX(offset);
        view.setAlpha(0.45f);
        view.animate()
                .translationX(0f)
                .alpha(1f)
                .setDuration(260L)
                .setInterpolator(new DecelerateInterpolator())
                .start();
    }

    private void goTo(int index) {
        if (story == null || index < 0 || index >= story.size() || index == currentPage) {
            return;
        }
        showPage(index, index > currentPage ? 1 : -1);
    }

    private void loadImage(StoryRepository.Page storyPage) {
        try (InputStream input = getAssets().open(storyPage.image)) {
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inPreferredConfig = Bitmap.Config.ARGB_8888;
            Bitmap bitmap = BitmapFactory.decodeStream(input, null, options);
            if (bitmap == null) {
                return;
            }
            Bitmap old = currentBitmap;
            currentBitmap = bitmap;
            pageImage.setImageBitmap(bitmap);
            if (old != null && old != bitmap) {
                old.recycle();
            }
        } catch (Exception ignored) {
            pageImage.setImageDrawable(null);
        }
    }

    private void buildSentences(StoryRepository.Page storyPage) {
        sentenceContainer.removeAllViews();
        rows.clear();
        for (int i = 0; i < storyPage.segments.length; i++) {
            final int segmentIndex = i;
            StoryRepository.Segment segment = storyPage.segments[i];

            LinearLayout row = new LinearLayout(this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.TOP);
            row.setPadding(dp(7), dp(7), dp(7), dp(7));
            LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
            );
            rowParams.bottomMargin = dp(3);
            row.setLayoutParams(rowParams);
            row.setClickable(true);
            row.setFocusable(true);
            row.setSoundEffectsEnabled(false);
            row.setOnClickListener(v -> speakSingle(segmentIndex));

            ImageView speaker = new ImageView(this);
            LinearLayout.LayoutParams speakerParams = new LinearLayout.LayoutParams(dp(32), dp(32));
            speakerParams.topMargin = dp(1);
            speakerParams.setMarginEnd(dp(3));
            speaker.setLayoutParams(speakerParams);
            speaker.setPadding(dp(6), dp(6), dp(6), dp(6));
            speaker.setImageResource(R.drawable.ic_speaker);
            speaker.setColorFilter(getColor(R.color.green_600));
            speaker.setBackgroundResource(R.drawable.bg_speaker_icon);
            speaker.setContentDescription(getString(R.string.listen_sentence));
            speaker.setOnClickListener(v -> speakSingle(segmentIndex));

            LinearLayout textColumn = new LinearLayout(this);
            textColumn.setOrientation(LinearLayout.VERTICAL);
            LinearLayout.LayoutParams textParams = new LinearLayout.LayoutParams(
                    0,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                    1f
            );
            textParams.setMarginStart(dp(4));
            textColumn.setLayoutParams(textParams);

            TextView english = new TextView(this);
            english.setText(buildWordSpans(segment.en));
            english.setTextSize(16f);
            english.setTextColor(getColor(R.color.ink));
            english.setTypeface(Typeface.create("serif", Typeface.NORMAL));
            english.setLineSpacing(dp(3), 1f);
            english.setPadding(0, 0, 0, 0);
            english.setMovementMethod(LinkMovementMethod.getInstance());
            english.setHighlightColor(Color.TRANSPARENT);
            english.setLinksClickable(true);
            english.setOnClickListener(v -> speakSingle(segmentIndex));

            TextView chinese = new TextView(this);
            chinese.setText(segment.zh);
            chinese.setTextSize(12.5f);
            chinese.setTextColor(getColor(R.color.green_800));
            chinese.setLineSpacing(dp(2), 1f);
            chinese.setBackgroundResource(R.drawable.bg_translation_box);
            chinese.setPadding(dp(9), dp(7), dp(9), dp(7));
            LinearLayout.LayoutParams chineseParams = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
            );
            chineseParams.topMargin = dp(5);
            chinese.setLayoutParams(chineseParams);
            chinese.setVisibility(View.GONE);

            textColumn.addView(english);
            textColumn.addView(chinese);
            row.addView(speaker);
            row.addView(textColumn);

            SentenceRow sentenceRow = new SentenceRow(row, chinese);
            rows.add(sentenceRow);
            sentenceContainer.addView(row);
        }
    }

    private SpannableString buildWordSpans(String text) {
        SpannableString spannable = new SpannableString(text);
        Matcher matcher = WORD_PATTERN.matcher(text);
        while (matcher.find()) {
            final String word = matcher.group();
            ClickableSpan span = new ClickableSpan() {
                @Override
                public void onClick(View widget) {
                    onWordTapped(word);
                }

                @Override
                public void updateDrawState(TextPaint ds) {
                    ds.setColor(getColor(R.color.ink));
                    ds.setUnderlineText(false);
                }
            };
            spannable.setSpan(span, matcher.start(), matcher.end(),
                    Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        }
        return spannable;
    }

    private void onWordTapped(String word) {
        String clean = word == null ? "" : word.replaceAll("^[^A-Za-z]+|[^A-Za-z]+$", "");
        if (clean.isEmpty()) {
            return;
        }
        stopReading();
        OxfordDictionary.Entry entry = OxfordDictionary.get(this).lookup(clean);
        String phonetic = entry == null || entry.phonetic.isEmpty()
                ? ""
                : "  [" + entry.phonetic + "]";
        String zh = entry == null ? getString(R.string.word_not_found) : entry.zh;
        Toast.makeText(this, clean + phonetic + "\n" + zh, Toast.LENGTH_LONG).show();
        if (tts != null && ttsReady) {
            tts.setSpeechRate(0.9f);
            tts.setPitch(1f);
            tts.speak(clean, TextToSpeech.QUEUE_FLUSH, null, "word_" + System.nanoTime());
        }
    }

    private void toggleTranslation(int index) {
        if (index < 0 || index >= rows.size()) {
            return;
        }
        SentenceRow row = rows.get(index);
        setTranslationVisible(row, !row.zhVisible);
    }

    private void setTranslationVisible(SentenceRow row, boolean visible) {
        row.zhVisible = visible;
        if (visible) {
            row.translation.setVisibility(View.VISIBLE);
            row.translation.setAlpha(0f);
            row.translation.animate().alpha(1f).setDuration(160L).start();
        } else {
            row.translation.animate().cancel();
            row.translation.setVisibility(View.GONE);
        }
        updateRowBackground(row);
    }

    private void toggleAllTranslations() {
        allTranslations = !allTranslations;
        for (SentenceRow row : rows) {
            setTranslationVisible(row, allTranslations);
        }
        updateTranslateButton();
    }

    private void updateTranslateButton() {
        if (btnTranslate == null) {
            return;
        }
        if (allTranslations) {
            btnTranslate.setText(R.string.hide_translation);
            translationHint.setText(R.string.tap_to_hide);
        } else {
            btnTranslate.setText(R.string.translate_all);
            translationHint.setText(R.string.tap_for_translation);
        }
    }

    private void updateRowBackground(SentenceRow row) {
        if (row.active) {
            row.container.setBackgroundResource(R.drawable.bg_sentence_active);
        } else if (row.zhVisible) {
            row.container.setBackgroundResource(R.drawable.bg_sentence_translation);
        } else {
            row.container.setBackgroundResource(0);
        }
    }

    private void highlightRow(int index) {
        for (int i = 0; i < rows.size(); i++) {
            SentenceRow row = rows.get(i);
            row.active = i == index;
            updateRowBackground(row);
        }
    }

    private void clearHighlights() {
        for (SentenceRow row : rows) {
            row.active = false;
            updateRowBackground(row);
        }
    }

    private void scrollToRow(int index) {
        if (index < 0 || index >= rows.size()) {
            return;
        }
        SentenceRow row = rows.get(index);
        textScroll.post(() -> {
            int top = row.container.getTop();
            int bottom = row.container.getBottom();
            int visibleTop = textScroll.getScrollY();
            int visibleBottom = visibleTop + textScroll.getHeight();
            if (top < visibleTop || bottom > visibleBottom) {
                textScroll.smoothScrollTo(0, Math.max(0, top - dp(4)));
            }
        });
    }

    private void updateNavButtons() {
        boolean canPrev = currentPage > 0;
        boolean canNext = currentPage < story.size() - 1;
        btnPrev.setEnabled(canPrev);
        btnPrev.setAlpha(canPrev ? 1f : 0.3f);
        btnNext.setEnabled(canNext);
        btnNext.setAlpha(canNext ? 1f : 0.3f);
    }

    private void updateProgress() {
        progressTrack.post(() -> {
            int width = progressTrack.getWidth();
            if (width <= 0 || story == null) {
                return;
            }
            int fill = Math.max(dp(3), Math.round(width * ((currentPage + 1) / (float) story.size())));
            ViewGroup.LayoutParams params = progressFill.getLayoutParams();
            params.width = fill;
            progressFill.setLayoutParams(params);
        });
    }

    private void requestFollow() {
        int start = readingIndex >= 0 ? readingIndex : 0;
        if (isReading) {
            stopReading();
        }
        pendingFollowStart = start;
        if (!hasMicPermission()) {
            pendingFollowOpen = true;
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
            return;
        }
        pendingFollowOpen = false;
        showFollowDialog(start);
    }

    private void showFollowDialog(int start) {
        if (page == null) {
            return;
        }
        if (followDialog != null && followDialog.isShowing()) {
            followDialog.dismiss();
        }
        followDialog = new FollowReadingDialog(this, page.segments, start);
        followDialog.show();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQ_MIC) {
            return;
        }
        boolean granted = grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED;
        if (granted && pendingFollowOpen) {
            pendingFollowOpen = false;
            showFollowDialog(pendingFollowStart);
        } else {
            pendingFollowOpen = false;
            toast(R.string.record_permission_settings);
        }
    }

    public boolean hasMicPermission() {
        return checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED;
    }

    public boolean speakFollow(String text) {
        if (tts == null || !ttsReady) {
            toast(R.string.tts_preparing);
            return false;
        }
        tts.setSpeechRate(FOLLOW_RATE);
        tts.setPitch(1.0f);
        int result = tts.speak(text, TextToSpeech.QUEUE_FLUSH, null,
                "follow_" + System.nanoTime());
        if (result != TextToSpeech.SUCCESS) {
            toast(R.string.tts_error);
            return false;
        }
        return true;
    }

    public void stopFollowSpeech() {
        if (tts != null && !isReading) {
            tts.stop();
        }
    }

    public void onFollowDialogClosed() {
        followDialog = null;
        if (tts != null && !isReading) {
            tts.stop();
        }
    }

    private void showPageChooser() {
        if (isReading) {
            stopReading();
        }
        Dialog dialog = new Dialog(this, R.style.DialogTheme);
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);
        dialog.setContentView(R.layout.dialog_pages);

        TextView hint = dialog.findViewById(R.id.choosePageHint);
        hint.setText(getString(R.string.choose_page_hint, story.size()));
        GridView grid = dialog.findViewById(R.id.gridPages);
        grid.setAdapter(new PageAdapter());
        grid.setOnItemClickListener((parent, view, position, id) -> {
            dialog.dismiss();
            if (position != currentPage) {
                showPage(position, position > currentPage ? 1 : -1);
            }
        });
        ImageButton close = dialog.findViewById(R.id.btnClosePages);
        close.setOnClickListener(v -> dialog.dismiss());

        dialog.show();
        Window window = dialog.getWindow();
        if (window != null) {
            window.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            window.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);
            WindowManager.LayoutParams params = window.getAttributes();
            params.dimAmount = 0.46f;
            params.width = (int) (getResources().getDisplayMetrics().widthPixels * 0.92f);
            params.height = WindowManager.LayoutParams.WRAP_CONTENT;
            params.gravity = Gravity.CENTER;
            window.setAttributes(params);
        }
    }

    private class PageAdapter extends BaseAdapter {
        @Override
        public int getCount() {
            return story.size();
        }

        @Override
        public Object getItem(int position) {
            return position + 1;
        }

        @Override
        public long getItemId(int position) {
            return position;
        }

        @Override
        public View getView(int position, View convertView, ViewGroup parent) {
            TextView view;
            if (convertView instanceof TextView) {
                view = (TextView) convertView;
            } else {
                view = new TextView(ReaderActivity.this);
                view.setGravity(Gravity.CENTER);
                view.setTextSize(13f);
                view.setTypeface(null, Typeface.BOLD);
            }
            view.setLayoutParams(new AbsListView.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, dp(44)));
            view.setText(String.valueOf(position + 1));
            if (position == currentPage) {
                view.setTextColor(getColor(R.color.white));
                view.setBackgroundResource(R.drawable.bg_page_current);
            } else {
                view.setTextColor(getColor(R.color.green_700));
                view.setBackgroundResource(R.drawable.bg_page_number);
            }
            return view;
        }
    }

    private void setButtonIcon(TextView view, int iconRes, int colorRes) {
        Drawable icon = getDrawable(iconRes);
        if (icon == null) {
            return;
        }
        icon = icon.mutate();
        icon.setTint(getColor(colorRes));
        view.setCompoundDrawablesRelativeWithIntrinsicBounds(icon, null, null, null);
    }

    private void toast(int resId) {
        Toast.makeText(this, resId, Toast.LENGTH_SHORT).show();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onPause() {
        super.onPause();
        stopReading();
        if (followDialog != null && followDialog.isShowing()) {
            followDialog.pauseAudio();
        }
        if (story != null) {
            AppPrefs.setLastPage(this, currentPage);
        }
    }

    @Override
    protected void onDestroy() {
        destroyed = true;
        if (followDialog != null) {
            followDialog.dismiss();
        }
        if (tts != null) {
            tts.stop();
            tts.shutdown();
            tts = null;
        }
        if (currentBitmap != null) {
            currentBitmap.recycle();
            currentBitmap = null;
        }
        super.onDestroy();
    }

    private static class SentenceRow {
        final LinearLayout container;
        final TextView translation;
        boolean active;
        boolean zhVisible;

        SentenceRow(LinearLayout container, TextView translation) {
            this.container = container;
            this.translation = translation;
        }
    }
}

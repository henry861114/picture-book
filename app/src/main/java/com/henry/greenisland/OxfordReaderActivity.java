package com.henry.greenisland;

import android.Manifest;
import android.app.Activity;
import android.app.Dialog;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.Drawable;
import android.graphics.pdf.PdfRenderer;
import android.media.MediaPlayer;
import android.media.MediaRecorder;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
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
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Picture-book reader for the bundled Oxford Reading Tree PDFs.
 *
 * Features:
 *  - original MP3 playback with automatic page turning (page times are estimated
 *    at build time from the audio pauses and the amount of text on each page);
 *  - manual page turning, tap a sentence to hear it (system TTS), with a small
 *    Chinese reading aid under each sentence;
 *  - tap any word to hear it and see its phonetic + Chinese meaning from the
 *    bundled offline dictionary;
 *  - a simple record / playback follow-reading tool.
 */
public class OxfordReaderActivity extends Activity {

    public static final String EXTRA_PAGE = "extra_page";
    private static final int REQ_MIC = 91;
    private static final Pattern WORD_PATTERN =
            Pattern.compile("[A-Za-z]+(?:['’\\-][A-Za-z]+)*");

    private OxfordLibrary.Book book;
    private OxfordBookText bookText;
    private OxfordDictionary dictionary;
    private OxfordBookText.Page currentTextPage;
    private int currentPage;
    private boolean destroyed;

    private TextView bookTitle;
    private TextView bookMeta;
    private TextView pageCounter;
    private ImageView bookPage;
    private ProgressBar pageLoading;
    private ImageButton btnPrev;
    private ImageButton btnNext;
    private FrameLayout imageCard;
    private TextView swipeHint;
    private LinearLayout audioRow;
    private SeekBar audioSeek;
    private TextView audioTime;
    private TextView audioDuration;
    private TextView btnAuto;
    private TextView btnPlay;
    private TextView btnRecord;
    private TextView btnReplay;
    private TextView btnChinese;
    private TextView textPanelTitle;
    private TextView recordHint;
    private ScrollView sentenceScroll;
    private LinearLayout sentenceContainer;

    private final List<SentenceRow> rows = new ArrayList<>();
    private boolean showAllChinese;
    private boolean sentencePlaying;
    private int activeSentence = -1;
    private int ttsGeneration;
    private int sentenceAudioEndMs;
    private int sentenceAudioGeneration;

    private TextToSpeech tts;
    private boolean ttsReady;

    private boolean autoPlaying;
    private boolean autoTts;
    private int autoTtsPage;
    private int autoTtsSentence;
    private int autoTtsGeneration;
    private int autoHighlightIndex = -1;

    private PdfRenderer renderer;
    private ParcelFileDescriptor pdfFd;
    private final Object rendererLock = new Object();
    private final ExecutorService renderExecutor = Executors.newSingleThreadExecutor();
    private Bitmap currentBitmap;
    private volatile int renderGeneration;

    /**
     * Some PDFs (the "Lesson N" educational editions) stack two or three
     * scanned story pages on one PDF page. viewPages flattens them: each
     * entry is one visible page with its own crop window and its share of
     * the sentences.
     */
    private static class ViewPage {
        final int pdfIndex;
        final float left;
        final float top;
        final float right;
        final float bottom;
        final OxfordBookText.Page text;

        ViewPage(int pdfIndex, float left, float top, float right, float bottom,
                 OxfordBookText.Page text) {
            this.pdfIndex = pdfIndex;
            this.left = left;
            this.top = top;
            this.right = right;
            this.bottom = bottom;
            this.text = text;
        }
    }

    private final List<ViewPage> viewPages = new ArrayList<>();

    private MediaPlayer audioPlayer;
    private boolean audioReady;
    private boolean audioFailed;

    private MediaRecorder recorder;
    private boolean recording;
    private long recordStartMs;
    private File recordFile;
    private MediaPlayer recordPlayer;
    private File lastRecordFile;
    private int lastRecordPage = -1;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private GestureDetector gestureDetector;

    private final Runnable audioTicker = new Runnable() {
        @Override
        public void run() {
            if (destroyed) {
                return;
            }
            updateAudioProgress();
            handler.postDelayed(this, 400);
        }
    };

    private final Runnable autoTicker = new Runnable() {
        @Override
        public void run() {
            if (destroyed || !autoPlaying || autoTts) {
                return;
            }
            if (audioPlayer == null || !audioReady || audioFailed) {
                stopAuto();
                return;
            }
            int position;
            try {
                position = audioPlayer.getCurrentPosition();
            } catch (IllegalStateException e) {
                stopAuto();
                return;
            }
            OxfordBookText.Page page = currentTextPage;
            int target = findPageForPosition(position);
            if (target >= 0 && target != currentPage) {
                showPage(target, target > currentPage ? 1 : -1, true);
            } else {
                updateAutoHighlight(position);
            }
            handler.postDelayed(this, 180);
        }
    };

    private final Runnable sentenceAudioTicker = new Runnable() {
        @Override
        public void run() {
            if (destroyed || !sentencePlaying) {
                return;
            }
            if (audioPlayer == null || !audioReady || audioFailed) {
                stopSentenceTts();
                return;
            }
            int position;
            try {
                position = audioPlayer.getCurrentPosition();
            } catch (IllegalStateException e) {
                stopSentenceTts();
                return;
            }
            if (position >= sentenceAudioEndMs - 30 || !audioPlayer.isPlaying()) {
                try {
                    audioPlayer.pause();
                } catch (IllegalStateException ignored) {
                }
                sentencePlaying = false;
                activeSentence = -1;
                clearActiveHighlight();
                updatePlayButton(false);
                return;
            }
            handler.postDelayed(this, 80);
        }
    };

    private final Runnable recordTicker = new Runnable() {
        @Override
        public void run() {
            if (destroyed || !recording) {
                return;
            }
            long elapsed = System.currentTimeMillis() - recordStartMs;
            recordHint.setText(getString(R.string.recording_hint, formatTime(elapsed)));
            handler.postDelayed(this, 400);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_oxford_reader);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        configureSystemBars();

        String bookId = getIntent().getStringExtra(OxfordLibraryActivity.EXTRA_BOOK_ID);
        OxfordLibrary library;
        try {
            library = OxfordLibrary.load(this);
        } catch (RuntimeException e) {
            Toast.makeText(this, R.string.book_open_failed, Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        book = bookId == null ? null : library.findBook(bookId);
        if (book == null) {
            Toast.makeText(this, R.string.book_open_failed, Toast.LENGTH_LONG).show();
            finish();
            return;
        }

        bookText = OxfordBookText.load(this, book.id);
        dictionary = OxfordDictionary.get(this);

        bindViews();
        setupClicks();
        setupGestures();
        initTts();

        bookTitle.setText(book.title);
        bookMeta.setText(getString(R.string.book_level, book.level, book.number));

        int page = getIntent().getIntExtra(EXTRA_PAGE, AppPrefs.getBookPage(this, book.id));
        openPdf();
        prepareAudio();
        // Expand stacked scans (2-3 story pages per PDF page).
        buildViewPages();
        if (page < 0 || page >= viewCount()) {
            page = 0;
        }
        showPage(page, 0, false);
        updateRecordUi();
        updateAutoButton();
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
        bookTitle = findViewById(R.id.bookTitle);
        bookMeta = findViewById(R.id.bookMeta);
        pageCounter = findViewById(R.id.pageCounter);
        bookPage = findViewById(R.id.bookPage);
        pageLoading = findViewById(R.id.pageLoading);
        btnPrev = findViewById(R.id.btnPrev);
        btnNext = findViewById(R.id.btnNext);
        imageCard = findViewById(R.id.imageCard);
        swipeHint = findViewById(R.id.swipeHint);
        audioRow = findViewById(R.id.audioRow);
        audioSeek = findViewById(R.id.audioSeek);
        audioTime = findViewById(R.id.audioTime);
        audioDuration = findViewById(R.id.audioDuration);
        btnAuto = findViewById(R.id.btnAuto);
        btnPlay = findViewById(R.id.btnPlay);
        btnRecord = findViewById(R.id.btnRecord);
        btnReplay = findViewById(R.id.btnReplay);
        btnChinese = findViewById(R.id.btnChinese);
        textPanelTitle = findViewById(R.id.textPanelTitle);
        recordHint = findViewById(R.id.recordHint);
        sentenceScroll = findViewById(R.id.sentenceScroll);
        sentenceContainer = findViewById(R.id.sentenceContainer);
    }

    private void setupClicks() {
        findViewById(R.id.btnBack).setOnClickListener(v -> {
            finish();
            overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out);
        });
        btnPrev.setOnClickListener(v -> goTo(currentPage - 1));
        btnNext.setOnClickListener(v -> goTo(currentPage + 1));
        pageCounter.setOnClickListener(v -> showPageChooser());
        btnAuto.setOnClickListener(v -> {
            if (autoPlaying) {
                stopAuto();
            } else {
                startAuto();
            }
        });
        btnPlay.setOnClickListener(v -> toggleAudio());
        btnRecord.setOnClickListener(v -> onRecordClicked());
        btnReplay.setOnClickListener(v -> toggleRecordPlayback());
        btnChinese.setOnClickListener(v -> {
            showAllChinese = !showAllChinese;
            for (SentenceRow row : rows) {
                setChineseVisible(row, showAllChinese);
            }
            updateChineseButton();
        });
        imageCard.setOnClickListener(v -> {
            if (swipeHint.getVisibility() == View.VISIBLE) {
                swipeHint.animate().alpha(0f).setDuration(220L).withEndAction(
                        () -> swipeHint.setVisibility(View.GONE)).start();
            }
        });
    }

    private void setupGestures() {
        gestureDetector = new GestureDetector(this, new GestureDetector.SimpleOnGestureListener() {
            @Override
            public boolean onFling(MotionEvent e1, MotionEvent e2, float velocityX, float velocityY) {
                if (e1 == null || e2 == null) {
                    return false;
                }
                float dx = e2.getX() - e1.getX();
                float dy = e2.getY() - e1.getY();
                if (Math.abs(dx) > dp(64)
                        && Math.abs(dx) > Math.abs(dy) * 1.3f
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
        });
    }

    /**
     * Horizontal drags inside the bottom sheet (sentence list, seek bar,
     * buttons) are UI interactions, not page flips.
     */
    private boolean gestureInSheet(float rawY) {
        View sheet = findViewById(R.id.bottomSheet);
        if (sheet == null) {
            return false;
        }
        int[] pos = new int[2];
        sheet.getLocationOnScreen(pos);
        return rawY >= pos[1];
    }

    private boolean gestureInSheet;

    @Override
    public boolean dispatchTouchEvent(MotionEvent ev) {
        if (gestureDetector != null) {
            if (ev.getActionMasked() == MotionEvent.ACTION_DOWN) {
                gestureInSheet = gestureInSheet(ev.getRawY());
            }
            if (!gestureInSheet) {
                gestureDetector.onTouchEvent(ev);
            }
        }
        return super.dispatchTouchEvent(ev);
    }

    private void initTts() {
        tts = new TextToSpeech(getApplicationContext(), status -> runOnUiThread(() -> {
            if (destroyed) {
                return;
            }
            if (status != TextToSpeech.SUCCESS) {
                ttsReady = false;
                return;
            }
            int result = tts.setLanguage(Locale.UK);
            if (result == TextToSpeech.LANG_MISSING_DATA
                    || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                result = tts.setLanguage(Locale.US);
            }
            if (result == TextToSpeech.LANG_MISSING_DATA
                    || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                ttsReady = false;
                return;
            }
            tts.setSpeechRate(0.82f);
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
            runOnUiThread(() -> handleTtsDone(utteranceId));
        }
    }

    private void handleTtsDone(String utteranceId) {
        if (destroyed || utteranceId == null) {
            return;
        }
        if (utteranceId.startsWith("sent_")) {
            String[] parts = utteranceId.split("_");
            if (parts.length >= 3) {
                try {
                    if (Integer.parseInt(parts[1]) == ttsGeneration) {
                        sentencePlaying = false;
                        activeSentence = -1;
                        clearActiveHighlight();
                    }
                } catch (NumberFormatException ignored) {
                }
            }
            return;
        }
        if (utteranceId.startsWith("auto_") && autoTts) {
            String[] parts = utteranceId.split("_");
            if (parts.length >= 4) {
                try {
                    int generation = Integer.parseInt(parts[1]);
                    int sentence = Integer.parseInt(parts[3]);
                    if (generation == autoTtsGeneration) {
                        autoTtsSentence = sentence + 1;
                        speakNextAutoSentence();
                    }
                } catch (NumberFormatException ignored) {
                }
            }
        }
    }

    private void openPdf() {
        try {
            // PdfRenderer needs a real, seekable file: an AssetFileDescriptor points at
            // the APK itself, with the PDF at a non-zero offset. Extracting the PDF to
            // the cache directory is the reliable way to open it with PdfRenderer.
            File cached = new File(getCacheDir(), "book_" + book.id + ".pdf");
            if (!cached.exists() || cached.length() == 0) {
                copyAsset(book.pdf, cached);
            }
            pdfFd = ParcelFileDescriptor.open(cached, ParcelFileDescriptor.MODE_READ_ONLY);
            renderer = new PdfRenderer(pdfFd);
        } catch (Exception e) {
            android.util.Log.e("OxfordReader", "Unable to open " + book.pdf, e);
            Toast.makeText(this, R.string.book_open_failed, Toast.LENGTH_LONG).show();
            finish();
        }
    }

    private void prepareAudio() {
        if (!book.hasAudio()) {
            audioRow.setVisibility(View.GONE);
            btnPlay.setVisibility(View.GONE);
            recordHint.setText(R.string.audio_unavailable);
            return;
        }
        try {
            audioPlayer = new MediaPlayer();
            try (android.content.res.AssetFileDescriptor afd = getAssets().openFd(book.audio)) {
                audioPlayer.setDataSource(
                        afd.getFileDescriptor(), afd.getStartOffset(), afd.getLength());
            } catch (IOException directFailed) {
                String extension = ".m4a";
                int dot = book.audio == null ? -1 : book.audio.lastIndexOf('.');
                if (dot >= 0) {
                    extension = book.audio.substring(dot);
                }
                File cached = new File(getCacheDir(), "audio_" + book.id + extension);
                if (!cached.exists() || cached.length() == 0) {
                    copyAsset(book.audio, cached);
                }
                audioPlayer.setDataSource(cached.getAbsolutePath());
            }
            audioPlayer.setOnPreparedListener(player -> {
                if (destroyed) {
                    return;
                }
                audioReady = true;
                int duration = Math.max(1, player.getDuration());
                audioSeek.setMax(duration);
                audioDuration.setText(formatTime(duration));
                updatePlayButton(false);
            });
            audioPlayer.setOnCompletionListener(player -> {
                if (autoPlaying && !autoTts) {
                    stopAuto();
                }
                updatePlayButton(false);
                audioSeek.setProgress(0);
                audioTime.setText("00:00");
            });
            audioPlayer.setOnErrorListener((player, what, extra) -> {
                audioFailed = true;
                audioReady = false;
                updatePlayButton(false);
                btnPlay.setEnabled(false);
                toast(R.string.audio_error);
                return true;
            });
            audioPlayer.prepareAsync();
            audioSeek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
                @Override
                public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                    if (fromUser) {
                        audioTime.setText(formatTime(progress));
                    }
                }

                @Override
                public void onStartTrackingTouch(SeekBar seekBar) {
                }

                @Override
                public void onStopTrackingTouch(SeekBar seekBar) {
                    if (audioPlayer != null && audioReady) {
                        int position = seekBar.getProgress();
                        try {
                            audioPlayer.seekTo(position);
                        } catch (IllegalStateException ignored) {
                        }
                        syncPageToPosition(position);
                    }
                }
            });
            handler.postDelayed(audioTicker, 400);
        } catch (Exception e) {
            audioFailed = true;
            audioReady = false;
            btnPlay.setEnabled(false);
            Toast.makeText(this, R.string.audio_error, Toast.LENGTH_SHORT).show();
        }
    }

    private void toggleAudio() {
        if (autoPlaying) {
            stopAuto();
        }
        if (sentencePlaying) {
            stopSentenceTts();
        }
        if (audioPlayer == null || audioFailed) {
            toast(R.string.audio_error);
            return;
        }
        if (!audioReady) {
            toast(R.string.audio_preparing);
            return;
        }
        if (audioPlayer.isPlaying()) {
            audioPlayer.pause();
            updatePlayButton(false);
        } else {
            if (recording) {
                stopRecording();
            }
            if (recordPlayer != null) {
                stopRecordPlayback(false);
            }
            audioPlayer.start();
            updatePlayButton(true);
        }
    }

    private void updateAudioProgress() {
        if (audioPlayer == null || !audioReady || audioFailed) {
            return;
        }
        try {
            int position = audioPlayer.getCurrentPosition();
            if (audioPlayer.isPlaying()) {
                audioSeek.setProgress(position);
            }
            audioTime.setText(formatTime(position));
        } catch (IllegalStateException ignored) {
        }
    }

    private void updatePlayButton(boolean playing) {
        if (btnPlay == null) {
            return;
        }
        btnPlay.setText(playing ? R.string.pause_audio : R.string.original_audio);
    }

    private void startAuto() {
        if (autoPlaying) {
            stopAuto();
            return;
        }
        stopSentenceTts();
        if (book.hasAudio() && audioReady && !audioFailed) {
            startAutoMp3();
        } else if (ttsReady) {
            startAutoTts();
        } else {
            toast(R.string.audio_preparing);
        }
    }

    private void startAutoMp3() {
        autoPlaying = true;
        autoTts = false;
        autoHighlightIndex = -1;
        updateAutoButton();
        int start = currentTextPage == null ? 0 : currentTextPage.startMs;
        if (start < 0) {
            start = 0;
        }
        try {
            audioPlayer.seekTo(start);
            audioPlayer.start();
        } catch (IllegalStateException e) {
            stopAuto();
            return;
        }
        updatePlayButton(true);
        handler.removeCallbacks(autoTicker);
        handler.post(autoTicker);
    }

    private void startAutoTts() {
        if (!ttsReady) {
            toast(R.string.tts_unavailable);
            return;
        }
        if (audioPlayer != null && audioPlayer.isPlaying()) {
            audioPlayer.pause();
        }
        updatePlayButton(false);
        autoPlaying = true;
        autoTts = true;
        autoTtsGeneration++;
        autoTtsPage = currentPage;
        autoTtsSentence = 0;
        autoHighlightIndex = -1;
        updateAutoButton();
        speakNextAutoSentence();
    }

    private void speakNextAutoSentence() {
        if (!autoTts || destroyed) {
            return;
        }
        if (autoTtsPage >= viewCount()) {
            stopAuto();
            return;
        }
        OxfordBookText.Page page = bookText.getPage(autoTtsPage);
        int count = page == null ? 0 : page.sentences.length;
        if (count == 0) {
            int next = autoTtsPage + 1;
            if (next >= viewCount()) {
                stopAuto();
                return;
            }
            showPage(next, 1, false);
            autoTtsPage = next;
            autoTtsSentence = 0;
            handler.postDelayed(this::speakNextAutoSentence, 900);
            return;
        }
        if (autoTtsSentence >= count) {
            int next = autoTtsPage + 1;
            if (next >= viewCount()) {
                stopAuto();
                return;
            }
            showPage(next, 1, false);
            autoTtsPage = next;
            autoTtsSentence = 0;
            handler.postDelayed(this::speakNextAutoSentence, 500);
            return;
        }
        if (currentPage != autoTtsPage) {
            showPage(autoTtsPage, 1, false);
        }
        if (autoTtsSentence < rows.size()) {
            highlightSentence(autoTtsSentence, false);
        }
        String text = page.sentences[autoTtsSentence].en;
        if (text == null || text.trim().isEmpty()) {
            autoTtsSentence++;
            handler.post(this::speakNextAutoSentence);
            return;
        }
        tts.setSpeechRate(0.82f);
        tts.setPitch(1f);
        String id = "auto_" + autoTtsGeneration + "_" + autoTtsPage + "_" + autoTtsSentence;
        int result = tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, id);
        if (result == TextToSpeech.ERROR) {
            autoTtsSentence++;
            handler.postDelayed(this::speakNextAutoSentence, 250);
        }
    }

    private void stopAuto() {
        boolean wasTts = autoTts;
        autoPlaying = false;
        autoTts = false;
        autoTtsGeneration++;
        handler.removeCallbacks(autoTicker);
        if (wasTts && tts != null) {
            tts.stop();
        }
        if (audioPlayer != null) {
            try {
                if (audioPlayer.isPlaying()) {
                    audioPlayer.pause();
                }
            } catch (IllegalStateException ignored) {
            }
        }
        updateAutoButton();
        updatePlayButton(false);
        clearActiveHighlight();
    }

    private void updateAutoButton() {
        if (btnAuto == null) {
            return;
        }
        btnAuto.setText(autoPlaying ? R.string.stop_auto : R.string.auto_play);
    }

    /**
     * The page that matches the given audio position. Pages whose window is
     * empty (pure illustration) are skipped so automatic paging keeps moving.
     */
    private int findPageForPosition(int position) {
        if (bookText == null) {
            return -1;
        }
        int best = -1;
        for (int i = 0; i < bookText.size(); i++) {
            OxfordBookText.Page p = bookText.getPage(i);
            if (p == null || p.endMs <= p.startMs) {
                continue;
            }
            if (position >= p.startMs) {
                best = i;
            } else {
                break;
            }
        }
        return best;
    }

    /**
     * Jump the page and the sentence highlight to the given audio position
     * (used when the user drags the progress bar).
     */
    private void syncPageToPosition(int position) {
        int target = findPageForPosition(position);
        if (target >= 0 && target != currentPage) {
            showPage(target, target > currentPage ? 1 : -1, true);
            updatePlayButton(true);
        } else if (currentTextPage != null) {
            autoHighlightIndex = -1;
            updateAutoHighlight(position);
        }
    }

    private void updateAutoHighlight(int position) {
        OxfordBookText.Page page = currentTextPage;
        if (page == null || page.endMs <= page.startMs || rows.isEmpty()) {
            return;
        }
        float fraction = (position - page.startMs) / (float) (page.endMs - page.startMs);
        if (fraction < 0) {
            fraction = 0;
        } else if (fraction > 0.999f) {
            fraction = 0.999f;
        }
        int total = 0;
        for (OxfordBookText.Sentence sentence : page.sentences) {
            total += Math.max(1, sentence.en.length());
        }
        int target = Math.round(fraction * total);
        int acc = 0;
        int index = 0;
        for (int i = 0; i < page.sentences.length; i++) {
            acc += Math.max(1, page.sentences[i].en.length());
            if (target <= acc) {
                index = i;
                break;
            }
        }
        if (index != autoHighlightIndex) {
            autoHighlightIndex = index;
            highlightSentence(index, false);
        }
    }

    private void playSentence(int index) {
        if (currentTextPage == null || index < 0 || index >= currentTextPage.sentences.length) {
            return;
        }
        if (autoPlaying) {
            stopAuto();
        }
        if (sentencePlaying && activeSentence == index) {
            stopSentenceTts();
            return;
        }
        if (sentencePlaying) {
            stopSentenceTts();
        }
        OxfordBookText.Sentence sentence = currentTextPage.sentences[index];
        if (book.hasAudio() && audioReady && !audioFailed && sentence.hasAudioTiming()) {
            playSentenceAudio(index, sentence);
            return;
        }

        // Fallback for pages without a matching MP3 segment (e.g. borrowed
        // illustration-page text): read the sentence with the system TTS.
        if (audioPlayer != null && audioPlayer.isPlaying()) {
            audioPlayer.pause();
            updatePlayButton(false);
        }
        if (!ttsReady) {
            highlightSentence(index, false);
            toast(R.string.tts_preparing);
            return;
        }
        ttsGeneration++;
        sentencePlaying = true;
        activeSentence = index;
        highlightSentence(index, false);
        tts.setSpeechRate(0.82f);
        tts.setPitch(1f);
        String text = sentence.en;
        int result = tts.speak(text, TextToSpeech.QUEUE_FLUSH, null,
                "sent_" + ttsGeneration + "_" + index);
        if (result == TextToSpeech.ERROR) {
            sentencePlaying = false;
            activeSentence = -1;
            clearActiveHighlight();
            toast(R.string.tts_error);
        }
    }

    private void playSentenceAudio(int index, OxfordBookText.Sentence sentence) {
        if (tts != null) {
            tts.stop();
        }
        ttsGeneration++;
        if (recordPlayer != null) {
            stopRecordPlayback(false);
        }
        try {
            audioPlayer.seekTo(sentence.startMs);
            audioPlayer.start();
        } catch (IllegalStateException e) {
            toast(R.string.audio_error);
            return;
        }
        sentencePlaying = true;
        activeSentence = index;
        sentenceAudioEndMs = sentence.endMs;
        sentenceAudioGeneration++;
        highlightSentence(index, false);
        updatePlayButton(true);
        handler.removeCallbacks(sentenceAudioTicker);
        handler.post(sentenceAudioTicker);
    }

    private void stopSentenceTts() {
        ttsGeneration++;
        sentenceAudioGeneration++;
        sentencePlaying = false;
        activeSentence = -1;
        handler.removeCallbacks(sentenceAudioTicker);
        if (tts != null) {
            tts.stop();
        }
        if (audioPlayer != null) {
            try {
                if (audioPlayer.isPlaying()) {
                    audioPlayer.pause();
                }
            } catch (IllegalStateException ignored) {
            }
        }
        clearActiveHighlight();
    }

    private void onWordTapped(String word) {
        if (word == null) {
            return;
        }
        String clean = word.replaceAll("^[^A-Za-z]+|[^A-Za-z]+$", "");
        if (clean.isEmpty()) {
            return;
        }
        if (autoPlaying) {
            stopAuto();
        }
        if (sentencePlaying) {
            stopSentenceTts();
        }
        if (audioPlayer != null && audioPlayer.isPlaying()) {
            audioPlayer.pause();
            updatePlayButton(false);
        }
        OxfordDictionary.Entry entry = dictionary == null ? null : dictionary.lookup(clean);
        String phonetic = entry == null || entry.phonetic.isEmpty()
                ? ""
                : "  [" + entry.phonetic + "]";
        String zh = entry == null ? getString(R.string.word_not_found) : entry.zh;
        Toast.makeText(this, clean + phonetic + "\n" + zh, Toast.LENGTH_LONG).show();
        if (ttsReady && tts != null) {
            tts.setSpeechRate(0.9f);
            tts.setPitch(1f);
            tts.speak(clean, TextToSpeech.QUEUE_FLUSH, null, "word_" + System.nanoTime());
        }
    }

    /** Crop a rectangle of the bitmap (fractions are 0..1 of the page). */
    private Bitmap cropRegion(Bitmap source, float leftF, float topF,
                              float rightF, float bottomF) {
        if (source == null
                || (leftF <= 0f && topF <= 0f && rightF >= 1f && bottomF >= 1f)) {
            return source;
        }
        int width = source.getWidth();
        int height = source.getHeight();
        int left = Math.max(0, Math.round(width * leftF));
        int top = Math.max(0, Math.round(height * topF));
        int right = Math.min(width, Math.round(width * rightF));
        int bottom = Math.min(height, Math.round(height * bottomF));
        if (right - left < 40 || bottom - top < 40
                || right - left < width * 0.15f || bottom - top < height * 0.10f) {
            return source;
        }
        try {
            Bitmap cropped = Bitmap.createBitmap(source, left, top,
                    right - left, bottom - top);
            if (cropped != source) {
                source.recycle();
            }
            return cropped;
        } catch (IllegalArgumentException e) {
            return source;
        }
    }

    private void showPage(int index, int direction, boolean keepAudio) {
        if (book == null || renderer == null || index < 0 || index >= viewCount()) {
            return;
        }
        if (recording) {
            stopRecording();
        }
        if (recordPlayer != null) {
            stopRecordPlayback(false);
        }
        if (!keepAudio) {
            if (sentencePlaying) {
                stopSentenceTts();
            }
            if (audioPlayer != null) {
                try {
                    if (audioPlayer.isPlaying()) {
                        audioPlayer.pause();
                    }
                } catch (IllegalStateException ignored) {
                }
            }
            updatePlayButton(false);
        }
        currentPage = index;
        currentTextPage = viewText(index);
        autoHighlightIndex = -1;
        AppPrefs.setBookPage(this, book.id, index);
        pageCounter.setText(getString(R.string.book_page_counter, index + 1, viewCount()));
        boolean canPrev = index > 0;
        boolean canNext = index < viewCount() - 1;
        btnPrev.setEnabled(canPrev);
        btnPrev.setAlpha(canPrev ? 1f : 0.3f);
        btnNext.setEnabled(canNext);
        btnNext.setAlpha(canNext ? 1f : 0.3f);
        updateRecordUi();
        buildSentences();

        if (direction != 0) {
            imageCard.animate().cancel();
            imageCard.setTranslationX(direction * dp(22));
            imageCard.setAlpha(0.55f);
            imageCard.animate()
                    .translationX(0f)
                    .alpha(1f)
                    .setDuration(240L)
                    .setInterpolator(new DecelerateInterpolator())
                    .start();
        }
        renderPage(index);
    }

    private void buildSentences() {
        sentenceContainer.removeAllViews();
        rows.clear();
        activeSentence = -1;
        sentencePlaying = false;
        if (currentTextPage == null || currentTextPage.sentences.length == 0) {
            textPanelTitle.setText(R.string.no_text_title);
            TextView empty = new TextView(this);
            empty.setText(R.string.no_text_page);
            empty.setTextSize(12f);
            empty.setTextColor(getColor(R.color.muted));
            empty.setPadding(dp(4), dp(10), dp(4), dp(10));
            sentenceContainer.addView(empty);
            return;
        }
        textPanelTitle.setText(R.string.page_sentences);
        for (int i = 0; i < currentTextPage.sentences.length; i++) {
            final int sentenceIndex = i;
            OxfordBookText.Sentence sentence = currentTextPage.sentences[i];

            LinearLayout row = new LinearLayout(this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.TOP);
            row.setPadding(dp(5), dp(5), dp(5), dp(5));
            LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
            );
            rowParams.bottomMargin = dp(2);
            row.setLayoutParams(rowParams);
            row.setClickable(true);
            row.setFocusable(true);
            row.setOnClickListener(v -> playSentence(sentenceIndex));

            ImageView play = new ImageView(this);
            LinearLayout.LayoutParams playParams = new LinearLayout.LayoutParams(dp(27), dp(27));
            playParams.topMargin = dp(1);
            playParams.setMarginEnd(dp(2));
            play.setLayoutParams(playParams);
            play.setPadding(dp(5), dp(5), dp(5), dp(5));
            play.setImageResource(R.drawable.ic_play);
            play.setColorFilter(getColor(R.color.green_600));
            play.setBackgroundResource(R.drawable.bg_speaker_icon);
            play.setContentDescription(getString(R.string.listen_sentence));
            play.setOnClickListener(v -> playSentence(sentenceIndex));

            LinearLayout column = new LinearLayout(this);
            column.setOrientation(LinearLayout.VERTICAL);
            LinearLayout.LayoutParams columnParams = new LinearLayout.LayoutParams(
                    0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
            columnParams.setMarginStart(dp(5));
            column.setLayoutParams(columnParams);

            TextView english = new TextView(this);
            SpannableString spannable = buildWordSpans(sentence.en);
            english.setText(spannable);
            english.setTextSize(16f);
            english.setTextColor(getColor(R.color.ink));
            english.setTypeface(Typeface.create("serif", Typeface.NORMAL));
            english.setLineSpacing(dp(2), 1f);
            english.setMovementMethod(LinkMovementMethod.getInstance());
            english.setHighlightColor(Color.TRANSPARENT);
            english.setLinksClickable(true);
            english.setOnClickListener(v -> playSentence(sentenceIndex));

            TextView chinese = new TextView(this);
            chinese.setText(sentence.zh == null || sentence.zh.isEmpty()
                    ? getString(R.string.word_not_found) : sentence.zh);
            chinese.setTextSize(12f);
            chinese.setTextColor(getColor(R.color.green_800));
            chinese.setLineSpacing(dp(1), 1f);
            chinese.setBackgroundResource(R.drawable.bg_translation_box);
            chinese.setPadding(dp(7), dp(4), dp(7), dp(4));
            LinearLayout.LayoutParams chineseParams = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
            );
            chineseParams.topMargin = dp(3);
            chinese.setLayoutParams(chineseParams);
            chinese.setVisibility(View.GONE);
            chinese.setOnClickListener(v -> playSentence(sentenceIndex));

            column.addView(english);
            column.addView(chinese);
            row.addView(play);
            row.addView(column);

            SentenceRow sentenceRow = new SentenceRow(row, chinese);
            rows.add(sentenceRow);
            if (showAllChinese) {
                chinese.setVisibility(View.VISIBLE);
            }
            sentenceContainer.addView(row);
        }
        updateChineseButton();
        sentenceScroll.scrollTo(0, 0);
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

    private void setChineseVisible(SentenceRow row, boolean visible) {
        row.zhVisible = visible;
        if (visible) {
            row.translation.setVisibility(View.VISIBLE);
            row.translation.setAlpha(0f);
            row.translation.animate().alpha(1f).setDuration(140L).start();
        } else {
            row.translation.animate().cancel();
            row.translation.setVisibility(View.GONE);
        }
        updateRowBackground(row);
    }

    private void updateChineseButton() {
        if (btnChinese == null) {
            return;
        }
        btnChinese.setText(showAllChinese ? R.string.hide_chinese : R.string.show_chinese);
        setButtonIcon(btnChinese,
                showAllChinese ? R.drawable.ic_close : R.drawable.ic_translate,
                R.color.green_700);
    }

    private void highlightSentence(int index, boolean showChinese) {
        for (int i = 0; i < rows.size(); i++) {
            SentenceRow row = rows.get(i);
            row.active = i == index;
            if (row.active && showChinese) {
                row.zhVisible = true;
                row.translation.setVisibility(View.VISIBLE);
            } else if (!showAllChinese && !row.active) {
                row.zhVisible = false;
                row.translation.setVisibility(View.GONE);
            }
            updateRowBackground(row);
        }
        scrollToRow(index);
    }

    private void scrollToRow(int index) {
        if (index < 0 || index >= rows.size()) {
            return;
        }
        SentenceRow row = rows.get(index);
        sentenceScroll.post(() -> {
            int top = row.container.getTop();
            int bottom = row.container.getBottom();
            int visibleTop = sentenceScroll.getScrollY();
            int visibleBottom = visibleTop + sentenceScroll.getHeight();
            if (top < visibleTop || bottom > visibleBottom) {
                sentenceScroll.smoothScrollTo(0, Math.max(0, top - dp(2)));
            }
        });
    }

    private void clearActiveHighlight() {
        for (SentenceRow row : rows) {
            row.active = false;
            updateRowBackground(row);
        }
        autoHighlightIndex = -1;
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

    private void goTo(int index) {
        if (book == null || index < 0 || index >= viewCount() || index == currentPage) {
            return;
        }
        if (autoPlaying) {
            stopAuto();
        }
        if (sentencePlaying) {
            stopSentenceTts();
        }
        showPage(index, index > currentPage ? 1 : -1, false);
    }

    /**
     * Many of the Level 1–5 PDFs are scans of an interactive reader: a blue
     * frame and a blue button bar surround the actual page. Cropping inside that
     * frame makes the illustration much larger on a phone. Pages without the
     * frame (and full-bleed illustrations) are returned unchanged.
     */
    private Bitmap cropBlueFrame(Bitmap source) {
        int width = source.getWidth();
        int height = source.getHeight();
        if (width < 40 || height < 40) {
            return source;
        }
        int corner = source.getPixel(2, 2);
        int topRight = source.getPixel(width - 3, 2);
        int bottomLeft = source.getPixel(2, height - 3);
        int bottomRight = source.getPixel(width - 3, height - 3);
        int center = source.getPixel(width / 2, height / 2);
        if (!isFrameBlue(corner) || !isFrameBlue(topRight)
                || !isFrameBlue(bottomLeft) || !isFrameBlue(bottomRight)
                || isFrameBlue(center)) {
            return source;
        }

        int left = 0;
        while (left < width / 4 && colIsBlue(source, left)) {
            left += 2;
        }
        int right = width - 1;
        while (right > width * 3 / 4 && colIsBlue(source, right)) {
            right -= 2;
        }
        int top = 0;
        while (top < height / 4 && rowIsBlue(source, top)) {
            top += 2;
        }
        int bottom = height - 1;
        while (bottom > height * 3 / 4 && rowIsBlue(source, bottom)) {
            bottom -= 2;
        }
        left += 2;
        top += 2;
        right -= 2;
        bottom -= 2;
        if (right - left < width * 0.55f || bottom - top < height * 0.55f) {
            return source;
        }
        try {
            Bitmap cropped = Bitmap.createBitmap(source, left, top,
                    right - left + 1, bottom - top + 1);
            if (cropped != source) {
                source.recycle();
            }
            return cropped;
        } catch (IllegalArgumentException e) {
            return source;
        }
    }

    private boolean isFrameBlue(int color) {
        int red = (color >> 16) & 0xff;
        int green = (color >> 8) & 0xff;
        int blue = color & 0xff;
        return blue > 130 && blue > red * 1.6f && blue > green * 1.4f
                && red < 130 && green < 130;
    }

    private boolean rowIsBlue(Bitmap bitmap, int y) {
        int width = bitmap.getWidth();
        int blue = 0;
        int total = 0;
        for (int x = 4; x < width - 4; x += 12) {
            total++;
            if (isFrameBlue(bitmap.getPixel(x, y))) {
                blue++;
            }
        }
        return total > 0 && blue > total * 0.6f;
    }

    private boolean colIsBlue(Bitmap bitmap, int x) {
        int height = bitmap.getHeight();
        int blue = 0;
        int total = 0;
        for (int y = 4; y < height - 4; y += 12) {
            total++;
            if (isFrameBlue(bitmap.getPixel(x, y))) {
                blue++;
            }
        }
        return total > 0 && blue > total * 0.6f;
    }

    /**
     * Removes the large white margins around the scanned illustration/text so
     * the picture uses more of the phone screen. If the detected content box is
     * tiny (or the whole page is coloured), the page is left alone.
     */
    private Bitmap cropWhiteMargins(Bitmap source) {
        int width = source.getWidth();
        int height = source.getHeight();
        if (width < 40 || height < 40) {
            return source;
        }
        int step = Math.max(1, Math.min(width, height) / 180);
        int left = width;
        int top = height;
        int right = -1;
        int bottom = -1;
        for (int y = 0; y < height; y += step) {
            for (int x = 0; x < width; x += step) {
                int color = source.getPixel(x, y);
                int red = (color >> 16) & 0xff;
                int green = (color >> 8) & 0xff;
                int blue = color & 0xff;
                if (red < 244 || green < 244 || blue < 244) {
                    if (x < left) left = x;
                    if (x > right) right = x;
                    if (y < top) top = y;
                    if (y > bottom) bottom = y;
                }
            }
        }
        if (right < left || bottom < top) {
            return source;
        }
        int padX = Math.max(4, width / 100);
        int padY = Math.max(4, height / 100);
        left = Math.max(0, left - padX);
        right = Math.min(width - 1, right + padX);
        top = Math.max(0, top - padY);
        bottom = Math.min(height - 1, bottom + padY);
        int cropWidth = right - left + 1;
        int cropHeight = bottom - top + 1;
        if (cropWidth < width * 0.35f || cropHeight < height * 0.35f) {
            return source;
        }
        if (cropWidth >= width - 3 && cropHeight >= height - 3) {
            return source;
        }
        try {
            Bitmap cropped = Bitmap.createBitmap(source, left, top, cropWidth, cropHeight);
            if (cropped != source) {
                source.recycle();
            }
            return cropped;
        } catch (IllegalArgumentException e) {
            return source;
        }
    }

    /**
     * Match the image card height to the rendered page, so landscape pages do
     * not sit inside a huge white portrait frame. The text panel takes the
     * remaining space.
     */
    private void adjustImageCardHeight(Bitmap bitmap) {
        if (bitmap == null || bitmap.getWidth() <= 0) {
            return;
        }
        if (getResources().getConfiguration().orientation
                == Configuration.ORIENTATION_LANDSCAPE) {
            ViewGroup.LayoutParams params = imageCard.getLayoutParams();
            if (params.height != ViewGroup.LayoutParams.MATCH_PARENT) {
                params.height = ViewGroup.LayoutParams.MATCH_PARENT;
                imageCard.setLayoutParams(params);
            }
            return;
        }
        // Level 6 (split-panel books): the card is a FIXED width & height
        // — it never follows the picture. Every image is scaled to fit
        // (fitCenter) inside the same frame, never cropped.
        if (getPackageName().endsWith(".l6")) {
            int screenHeight = getResources().getDisplayMetrics().heightPixels;
            int height = Math.max(dp(180),
                    Math.round(screenHeight * 0.46f));
            ViewGroup.LayoutParams params = imageCard.getLayoutParams();
            if (params.height != height) {
                params.height = height;
                imageCard.setLayoutParams(params);
            }
            return;
        }
        // Other levels: card follows the picture's aspect (3:4 cap).
        int screenWidth = getResources().getDisplayMetrics().widthPixels;
        int screenHeight = getResources().getDisplayMetrics().heightPixels;
        int drawWidth = screenWidth - dp(22) - dp(6);
        int height = Math.round(drawWidth * 4f / 3f);
        int maxHeight = Math.round(screenHeight * 0.46f);
        height = Math.max(dp(180), Math.min(height, maxHeight));
        ViewGroup.LayoutParams params = imageCard.getLayoutParams();
        if (params.height != height) {
            params.height = height;
            imageCard.setLayoutParams(params);
        }
    }

    /** Build the flattened view-page list from the data (rects included). */
    private void buildViewPages() {
        viewPages.clear();
        for (int i = 0; i < bookText.size(); i++) {
            OxfordBookText.Page p = bookText.getPage(i);
            if (p == null) {
                continue;
            }
            int pdf = p.pdfPage >= 0 ? p.pdfPage : Math.min(i, book.pages - 1);
            float[] rect = p.rect != null ? p.rect
                    : new float[]{0f, 0f, 1f, 1f};
            viewPages.add(new ViewPage(pdf, rect[0], rect[1], rect[2], rect[3], p));
        }
    }

    private int viewCount() {
        return viewPages.isEmpty() ? (book == null ? 0 : book.pages) : viewPages.size();
    }

    private OxfordBookText.Page viewText(int index) {
        if (index < 0 || index >= viewPages.size()) {
            return null;
        }
        return viewPages.get(index).text;
    }

    private void renderPage(int viewIndex) {
        if (viewIndex < 0 || viewIndex >= viewPages.size()) {
            return;
        }
        ViewPage vp = viewPages.get(viewIndex);
        final int generation = ++renderGeneration;
        pageLoading.setVisibility(View.VISIBLE);
        bookPage.setAlpha(0.3f);

        renderExecutor.execute(() -> {
            Bitmap bitmap = null;
            try {
                synchronized (rendererLock) {
                    if (renderer == null) {
                        return;
                    }
                    PdfRenderer.Page pdfPage = renderer.openPage(vp.pdfIndex);
                    try {
                        int pageWidth = Math.max(1, pdfPage.getWidth());
                        int pageHeight = Math.max(1, pdfPage.getHeight());
                        int screenWidth = getResources().getDisplayMetrics().widthPixels;
                        int targetWidth = Math.min(1800, Math.max(1000, screenWidth * 2));
                        int targetHeight = Math.max(1, Math.round(
                                targetWidth * (pageHeight / (float) pageWidth)));
                        if (targetHeight > 2600) {
                            targetHeight = 2600;
                            targetWidth = Math.max(1, Math.round(
                                    targetHeight * (pageWidth / (float) pageHeight)));
                        }
                        Bitmap result = Bitmap.createBitmap(
                                targetWidth, targetHeight, Bitmap.Config.ARGB_8888);
                        result.eraseColor(Color.WHITE);
                        pdfPage.render(result, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
                        bitmap = cropBlueFrame(result);
                        bitmap = cropRegion(bitmap, vp.left, vp.top, vp.right, vp.bottom);
                        bitmap = cropWhiteMargins(bitmap);
                    } finally {
                        pdfPage.close();
                    }
                }
            } catch (Exception e) {
                android.util.Log.e("OxfordReader", "Unable to render page " + viewIndex, e);
            }

            final Bitmap rendered = bitmap;
            runOnUiThread(() -> {
                if (destroyed || generation != renderGeneration) {
                    if (rendered != null) {
                        rendered.recycle();
                    }
                    return;
                }
                pageLoading.setVisibility(View.GONE);
                bookPage.setAlpha(1f);
                if (rendered == null) {
                    toast(R.string.book_open_failed);
                    return;
                }
                Bitmap old = currentBitmap;
                currentBitmap = rendered;
                bookPage.setImageBitmap(rendered);
                adjustImageCardHeight(rendered);
                if (old != null && old != rendered) {
                    old.recycle();
                }
            });
        });
    }

    private void onRecordClicked() {
        if (recording) {
            stopRecording();
            return;
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
            return;
        }
        startRecording();
    }

    private void startRecording() {
        if (book == null) {
            return;
        }
        if (autoPlaying) {
            stopAuto();
        }
        if (sentencePlaying) {
            stopSentenceTts();
        }
        if (audioPlayer != null && audioPlayer.isPlaying()) {
            audioPlayer.pause();
            updatePlayButton(false);
        }
        if (recordPlayer != null) {
            stopRecordPlayback(false);
        }
        File file = new File(getCacheDir(),
                "record_" + book.id + "_p" + (currentPage + 1) + ".m4a");
        if (file.exists()) {
            //noinspection ResultOfMethodCallIgnored
            file.delete();
        }
        MediaRecorder mediaRecorder = new MediaRecorder();
        try {
            mediaRecorder.setAudioSource(MediaRecorder.AudioSource.MIC);
            mediaRecorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
            mediaRecorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
            mediaRecorder.setAudioEncodingBitRate(96000);
            mediaRecorder.setAudioSamplingRate(44100);
            mediaRecorder.setOutputFile(file.getAbsolutePath());
            mediaRecorder.prepare();
            mediaRecorder.start();
        } catch (Exception e) {
            mediaRecorder.release();
            //noinspection ResultOfMethodCallIgnored
            file.delete();
            toast(R.string.record_failed);
            return;
        }
        recorder = mediaRecorder;
        recording = true;
        recordStartMs = System.currentTimeMillis();
        recordFile = file;
        updateRecordUi();
        recordHint.setText(getString(R.string.recording_hint, "00:00"));
        handler.postDelayed(recordTicker, 400);
    }

    private void stopRecording() {
        if (!recording || recorder == null) {
            return;
        }
        long duration = System.currentTimeMillis() - recordStartMs;
        boolean ok = true;
        try {
            recorder.stop();
        } catch (RuntimeException e) {
            ok = false;
        } finally {
            recorder.release();
            recorder = null;
        }
        recording = false;
        handler.removeCallbacks(recordTicker);
        if (!ok || duration < 700 || recordFile == null || !recordFile.exists()) {
            if (recordFile != null) {
                //noinspection ResultOfMethodCallIgnored
                recordFile.delete();
            }
            recordFile = null;
            toast(R.string.record_too_short);
            recordHint.setText(R.string.record_hint);
        } else {
            lastRecordFile = recordFile;
            lastRecordPage = currentPage;
            recordHint.setText(R.string.record_saved_hint);
        }
        updateRecordUi();
    }

    private void updateRecordUi() {
        if (recording) {
            btnRecord.setText(R.string.stop_record);
            btnRecord.setBackgroundResource(R.drawable.bg_record_pill_active);
            btnRecord.setTextColor(getColor(R.color.white));
        } else {
            btnRecord.setText(R.string.record);
            btnRecord.setBackgroundResource(R.drawable.bg_record_pill);
            btnRecord.setTextColor(getColor(R.color.coral_dark));
        }
        boolean hasRecording = lastRecordFile != null && lastRecordFile.exists()
                && lastRecordPage == currentPage;
        btnReplay.setEnabled(hasRecording);
        btnReplay.setAlpha(hasRecording ? 1f : 0.45f);
        if (!recording && recordPlayer == null) {
            recordHint.setText(hasRecording
                    ? R.string.record_saved_hint
                    : R.string.record_hint);
        }
    }

    private void toggleRecordPlayback() {
        if (recording) {
            stopRecording();
            return;
        }
        File file = null;
        if (lastRecordFile != null && lastRecordFile.exists() && lastRecordPage == currentPage) {
            file = lastRecordFile;
        }
        if (file == null) {
            toast(R.string.no_record);
            return;
        }
        if (recordPlayer != null && recordPlayer.isPlaying()) {
            stopRecordPlayback(true);
            return;
        }
        if (autoPlaying) {
            stopAuto();
        }
        if (sentencePlaying) {
            stopSentenceTts();
        }
        if (audioPlayer != null && audioPlayer.isPlaying()) {
            audioPlayer.pause();
            updatePlayButton(false);
        }
        try {
            MediaPlayer player = new MediaPlayer();
            player.setDataSource(file.getAbsolutePath());
            player.setOnCompletionListener(mp -> stopRecordPlayback(false));
            player.prepare();
            player.start();
            recordPlayer = player;
            recordHint.setText(R.string.playing_now);
        } catch (Exception e) {
            toast(R.string.record_failed);
        }
    }

    private void stopRecordPlayback(boolean userStopped) {
        if (recordPlayer != null) {
            try {
                recordPlayer.stop();
            } catch (IllegalStateException ignored) {
            }
            recordPlayer.release();
            recordPlayer = null;
        }
        if (lastRecordFile != null && lastRecordPage == currentPage) {
            recordHint.setText(R.string.record_saved_hint);
        } else {
            recordHint.setText(R.string.record_hint);
        }
    }

    private void showPageChooser() {
        Dialog dialog = new Dialog(this, R.style.DialogTheme);
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);
        dialog.setContentView(R.layout.dialog_pages);

        TextView hint = dialog.findViewById(R.id.choosePageHint);
        hint.setText(getString(R.string.page_of_book, book.title, viewCount()));
        GridView grid = dialog.findViewById(R.id.gridPages);
        grid.setAdapter(new PageAdapter());
        grid.setOnItemClickListener((parent, view, position, id) -> {
            dialog.dismiss();
            if (position != currentPage) {
                showPage(position, position > currentPage ? 1 : -1, false);
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
            return viewCount();
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
                view = new TextView(OxfordReaderActivity.this);
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

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQ_MIC) {
            return;
        }
        boolean granted = grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED;
        if (granted) {
            startRecording();
        } else {
            toast(R.string.record_permission_needed);
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

    private void copyAsset(String assetPath, File target) throws IOException {
        File parent = target.getParentFile();
        if (parent != null && !parent.exists()) {
            //noinspection ResultOfMethodCallIgnored
            parent.mkdirs();
        }
        try (InputStream input = getAssets().open(assetPath);
             FileOutputStream output = new FileOutputStream(target)) {
            byte[] buffer = new byte[16 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) {
                output.write(buffer, 0, read);
            }
        }
    }

    private String formatTime(long millis) {
        long totalSeconds = Math.max(0, millis / 1000);
        long minutes = totalSeconds / 60;
        long seconds = totalSeconds % 60;
        return String.format(Locale.US, "%02d:%02d", minutes, seconds);
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
        if (autoPlaying) {
            stopAuto();
        }
        if (sentencePlaying) {
            stopSentenceTts();
        }
        if (recording) {
            stopRecording();
        }
        if (recordPlayer != null) {
            stopRecordPlayback(false);
        }
        if (audioPlayer != null) {
            try {
                if (audioPlayer.isPlaying()) {
                    audioPlayer.pause();
                }
            } catch (IllegalStateException ignored) {
            }
        }
        updatePlayButton(false);
        if (book != null) {
            AppPrefs.setBookPage(this, book.id, currentPage);
        }
    }

    @Override
    protected void onDestroy() {
        destroyed = true;
        handler.removeCallbacksAndMessages(null);
        if (recorder != null) {
            try {
                recorder.stop();
            } catch (RuntimeException ignored) {
            }
            recorder.release();
            recorder = null;
        }
        if (recordPlayer != null) {
            recordPlayer.release();
            recordPlayer = null;
        }
        if (audioPlayer != null) {
            audioPlayer.release();
            audioPlayer = null;
        }
        if (tts != null) {
            tts.stop();
            tts.shutdown();
            tts = null;
        }
        renderExecutor.shutdown();
        try {
            renderExecutor.awaitTermination(3, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
        synchronized (rendererLock) {
            if (renderer != null) {
                try {
                    renderer.close();
                } catch (IllegalStateException ignored) {
                }
                renderer = null;
            }
            if (pdfFd != null) {
                try {
                    pdfFd.close();
                } catch (IOException ignored) {
                }
                pdfFd = null;
            }
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

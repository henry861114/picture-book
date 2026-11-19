package com.henry.greenisland;

import android.app.Dialog;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.media.MediaPlayer;
import android.media.MediaRecorder;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.Window;
import android.view.WindowManager;
import android.widget.ImageButton;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.util.Locale;

public class FollowReadingDialog {

    private final ReaderActivity activity;
    private final StoryRepository.Segment[] segments;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private Dialog dialog;
    private TextView sentenceView;
    private TextView translationView;
    private TextView sentenceCounter;
    private TextView timerView;
    private TextView recordLabel;
    private TextView tipView;
    private TextView btnPrev;
    private TextView btnNext;
    private TextView btnListen;
    private TextView btnPlayback;
    private ImageButton btnRecord;
    private ImageButton btnClose;
    private WaveformView waveform;

    private MediaRecorder recorder;
    private MediaPlayer player;
    private File audioFile;
    private boolean recording;
    private boolean playing;
    private long recordStartedAt;
    private int index;
    private Runnable timerRunnable;

    public FollowReadingDialog(ReaderActivity activity,
                               StoryRepository.Segment[] segments,
                               int startIndex) {
        this.activity = activity;
        this.segments = segments;
        this.index = Math.max(0, Math.min(startIndex, segments.length - 1));
    }

    public void show() {
        dialog = new Dialog(activity, R.style.DialogTheme);
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);
        dialog.setContentView(R.layout.dialog_follow);
        dialog.setCancelable(true);
        dialog.setCanceledOnTouchOutside(true);

        sentenceView = dialog.findViewById(R.id.followSentence);
        translationView = dialog.findViewById(R.id.followTranslation);
        sentenceCounter = dialog.findViewById(R.id.sentenceCounter);
        timerView = dialog.findViewById(R.id.recordTimer);
        recordLabel = dialog.findViewById(R.id.recordLabel);
        tipView = dialog.findViewById(R.id.followTip);
        btnPrev = dialog.findViewById(R.id.btnPrevSentence);
        btnNext = dialog.findViewById(R.id.btnNextSentence);
        btnListen = dialog.findViewById(R.id.btnListen);
        btnPlayback = dialog.findViewById(R.id.btnPlayback);
        btnRecord = dialog.findViewById(R.id.btnRecord);
        btnClose = dialog.findViewById(R.id.btnClose);
        waveform = dialog.findViewById(R.id.waveform);

        audioFile = new File(activity.getCacheDir(), "green_island_follow.m4a");
        deleteRecording();

        timerRunnable = new TimerTick();

        btnClose.setOnClickListener(v -> dismiss());
        btnPrev.setOnClickListener(v -> move(-1));
        btnNext.setOnClickListener(v -> move(1));
        btnListen.setOnClickListener(v -> {
            if (playing) {
                stopPlayback();
            }
            activity.speakFollow(segments[index].en);
        });
        btnRecord.setOnClickListener(v -> {
            if (recording) {
                stopRecording();
            } else {
                startRecording();
            }
        });
        btnPlayback.setOnClickListener(v -> playRecording());

        dialog.setOnDismissListener(d -> cleanup());
        renderSentence();
        resetAudioUi();

        dialog.show();
        Window window = dialog.getWindow();
        if (window != null) {
            window.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            window.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);
            WindowManager.LayoutParams params = window.getAttributes();
            params.dimAmount = 0.46f;
            params.width = (int) (activity.getResources().getDisplayMetrics().widthPixels * 0.92f);
            params.height = WindowManager.LayoutParams.WRAP_CONTENT;
            params.gravity = Gravity.CENTER;
            window.setAttributes(params);
        }
    }

    private void renderSentence() {
        StoryRepository.Segment segment = segments[index];
        sentenceView.setText(segment.en);
        translationView.setText(segment.zh);
        sentenceCounter.setText(String.format(Locale.US, "%d / %d", index + 1, segments.length));

        boolean canPrev = index > 0;
        boolean canNext = index < segments.length - 1;
        btnPrev.setEnabled(canPrev);
        btnPrev.setAlpha(canPrev ? 1f : 0.3f);
        btnNext.setEnabled(canNext);
        btnNext.setAlpha(canNext ? 1f : 0.3f);
    }

    private void move(int delta) {
        int next = index + delta;
        if (next < 0 || next >= segments.length) {
            return;
        }
        if (recording) {
            stopRecording();
        }
        stopPlayback();
        deleteRecording();
        index = next;
        renderSentence();
        resetAudioUi();
        activity.stopFollowSpeech();
    }

    private void startRecording() {
        if (!activity.hasMicPermission()) {
            toast(R.string.record_permission_needed);
            return;
        }
        if (playing) {
            stopPlayback();
        }
        activity.stopFollowSpeech();
        deleteRecording();
        resetAudioUi();

        MediaRecorder newRecorder = new MediaRecorder();
        try {
            newRecorder.setAudioSource(MediaRecorder.AudioSource.MIC);
            newRecorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
            newRecorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
            newRecorder.setAudioEncodingBitRate(96000);
            newRecorder.setAudioSamplingRate(44100);
            newRecorder.setOutputFile(audioFile.getAbsolutePath());
            newRecorder.prepare();
            newRecorder.start();
            recorder = newRecorder;
            recording = true;
            recordStartedAt = SystemClock.elapsedRealtime();
            timerView.setText("00:00");
            waveform.setActive(true);
            btnRecord.setBackgroundResource(R.drawable.bg_record_button_active);
            btnRecord.setContentDescription(activity.getString(R.string.stop_record));
            recordLabel.setText(R.string.stop_record);
            tipView.setText(R.string.recording_now);
            updatePlayback(false);
            handler.post(timerRunnable);
        } catch (Exception e) {
            try {
                newRecorder.release();
            } catch (Exception ignored) {
            }
            deleteRecording();
            toast(R.string.record_failed);
        }
    }

    private void stopRecording() {
        if (!recording) {
            return;
        }
        recording = false;
        handler.removeCallbacks(timerRunnable);
        waveform.setActive(false);
        btnRecord.setBackgroundResource(R.drawable.bg_record_button);
        btnRecord.setContentDescription(activity.getString(R.string.start_record));
        recordLabel.setText(R.string.record_again);

        boolean stopped = false;
        if (recorder != null) {
            try {
                recorder.stop();
                stopped = true;
            } catch (RuntimeException e) {
                stopped = false;
            } finally {
                try {
                    recorder.release();
                } catch (Exception ignored) {
                }
                recorder = null;
            }
        }

        if (stopped && audioFile.exists() && audioFile.length() > 0L) {
            tipView.setText(R.string.record_tip_saved);
            updatePlayback(true);
        } else {
            deleteRecording();
            timerView.setText("00:00");
            tipView.setText(R.string.record_tip_failed);
            updatePlayback(false);
        }
    }

    private void playRecording() {
        if (playing) {
            stopPlayback();
            return;
        }
        if (audioFile == null || !audioFile.exists() || audioFile.length() <= 0L) {
            toast(R.string.no_recording);
            return;
        }
        activity.stopFollowSpeech();
        releasePlayer();

        MediaPlayer newPlayer = new MediaPlayer();
        try {
            newPlayer.setDataSource(audioFile.getAbsolutePath());
            newPlayer.setOnCompletionListener(mp -> {
                playing = false;
                waveform.setActive(false);
                releasePlayer();
                tipView.setText(R.string.record_tip_saved);
                updatePlayback(true);
            });
            newPlayer.prepare();
            newPlayer.start();
            player = newPlayer;
            playing = true;
            waveform.setActive(true);
            tipView.setText(R.string.playing_now);
        } catch (Exception e) {
            try {
                newPlayer.release();
            } catch (Exception ignored) {
            }
            toast(R.string.record_failed);
        }
    }

    private void stopPlayback() {
        if (player != null) {
            try {
                if (player.isPlaying()) {
                    player.stop();
                }
            } catch (Exception ignored) {
            }
            releasePlayer();
        }
        playing = false;
        if (waveform != null) {
            waveform.setActive(false);
        }
        if (tipView != null) {
            tipView.setText(audioFile != null && audioFile.exists()
                    ? R.string.record_tip_saved : R.string.record_tip);
        }
    }

    private void releasePlayer() {
        if (player != null) {
            try {
                player.release();
            } catch (Exception ignored) {
            }
            player = null;
        }
    }

    private void updatePlayback(boolean enabled) {
        btnPlayback.setEnabled(enabled);
        btnPlayback.setClickable(enabled);
        btnPlayback.setFocusable(enabled);
        btnPlayback.setAlpha(enabled ? 1f : 0.4f);
    }

    private void resetAudioUi() {
        if (recording) {
            stopRecording();
        }
        stopPlayback();
        waveform.setActive(false);
        timerView.setText("00:00");
        recordLabel.setText(R.string.start_record);
        btnRecord.setBackgroundResource(R.drawable.bg_record_button);
        btnRecord.setContentDescription(activity.getString(R.string.start_record));
        tipView.setText(R.string.record_tip);
        updatePlayback(audioFile != null && audioFile.exists() && audioFile.length() > 0L);
    }

    private void deleteRecording() {
        if (audioFile != null && audioFile.exists()) {
            //noinspection ResultOfMethodCallIgnored
            audioFile.delete();
        }
    }

    public void pauseAudio() {
        if (recording) {
            stopRecording();
        }
        stopPlayback();
        activity.stopFollowSpeech();
    }

    public boolean isShowing() {
        return dialog != null && dialog.isShowing();
    }

    public void dismiss() {
        if (dialog != null && dialog.isShowing()) {
            dialog.dismiss();
        }
    }

    private class TimerTick implements Runnable {
        @Override
        public void run() {
            if (!recording) {
                return;
            }
            long seconds = (SystemClock.elapsedRealtime() - recordStartedAt) / 1000L;
            timerView.setText(String.format(Locale.US, "%02d:%02d",
                    seconds / 60L, seconds % 60L));
            handler.postDelayed(this, 250L);
        }
    }

    private void cleanup() {
        if (recording) {
            recording = false;
            handler.removeCallbacks(timerRunnable);
            if (recorder != null) {
                try {
                    recorder.stop();
                } catch (Exception ignored) {
                }
                try {
                    recorder.release();
                } catch (Exception ignored) {
                }
                recorder = null;
            }
        }
        releasePlayer();
        playing = false;
        handler.removeCallbacksAndMessages(null);
        deleteRecording();
        activity.onFollowDialogClosed();
    }

    private void toast(int resId) {
        Toast.makeText(activity, resId, Toast.LENGTH_SHORT).show();
    }
}

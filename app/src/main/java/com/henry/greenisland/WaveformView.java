package com.henry.greenisland;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.os.SystemClock;
import android.util.AttributeSet;
import android.view.View;

public class WaveformView extends View {

    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF bar = new RectF();
    private boolean active;
    private long startedAt;

    public WaveformView(Context context, AttributeSet attrs) {
        super(context, attrs);
        paint.setColor(getResources().getColor(R.color.green_500, getContext().getTheme()));
        paint.setStrokeCap(Paint.Cap.ROUND);
    }

    public void setActive(boolean active) {
        this.active = active;
        this.startedAt = SystemClock.uptimeMillis();
        postInvalidateOnAnimation();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        int width = getWidth();
        int height = getHeight();
        if (width <= 0 || height <= 0) {
            return;
        }

        int bars = 33;
        float gap = width / (float) bars;
        float barWidth = Math.max(dp(2f), gap * 0.38f);
        float centerY = height / 2f;
        float now = (SystemClock.uptimeMillis() - startedAt) / 1000f;

        paint.setAlpha(active ? 255 : 105);
        for (int i = 0; i < bars; i++) {
            float phase = i * 0.61f;
            float wave;
            if (active) {
                wave = 0.20f + 0.80f
                        * (float) Math.abs(Math.sin(phase + now * 5.4f))
                        * (float) Math.abs(Math.cos(phase * 0.47f + now * 1.7f));
            } else {
                wave = 0.10f + 0.04f * (float) Math.abs(Math.sin(phase * 0.8f));
            }
            float barHeight = dp(4f) + (height - dp(12f)) * wave;
            float left = gap * i + (gap - barWidth) / 2f;
            bar.set(left, centerY - barHeight / 2f, left + barWidth, centerY + barHeight / 2f);
            canvas.drawRoundRect(bar, barWidth / 2f, barWidth / 2f, paint);
        }

        if (active) {
            postInvalidateOnAnimation();
        }
    }

    private float dp(float value) {
        return value * getResources().getDisplayMetrics().density;
    }
}

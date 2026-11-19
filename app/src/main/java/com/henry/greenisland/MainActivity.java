package com.henry.greenisland;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.Window;
import android.view.animation.DecelerateInterpolator;
import android.widget.ImageView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.InputStream;

public class MainActivity extends Activity {

    /** Kept for compatibility with the full app build (ReaderActivity). */
    public static final String EXTRA_PAGE = "extra_page";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        configureSystemBars();

        TextView btnHelp = findViewById(R.id.btnHelp);
        View cardOxford = findViewById(R.id.cardOxford);

        btnHelp.setOnClickListener(v -> showHelp());
        cardOxford.setOnClickListener(v -> openOxfordLibrary());

        loadHeroImage();
        playEntranceAnimation();
    }

    @Override
    protected void onResume() {
        super.onResume();
    }

    private void configureSystemBars() {
        Window window = getWindow();
        int flags = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        }
        window.getDecorView().setSystemUiVisibility(flags);
    }

    private void loadHeroImage() {
        ImageView hero = findViewById(R.id.heroImage);
        try (InputStream input = getAssets().open("home_hero.jpg")) {
            Bitmap bitmap = BitmapFactory.decodeStream(input);
            if (bitmap != null) {
                hero.setImageBitmap(bitmap);
            }
        } catch (Exception ignored) {
            // The hero is decorative; the rest of the screen still works.
        }
    }

    private void playEntranceAnimation() {
        ImageView hero = findViewById(R.id.heroImage);
        View heroText = findViewById(R.id.heroText);
        View content = findViewById(R.id.homeContent);

        hero.setAlpha(0f);
        hero.setScaleX(1.06f);
        hero.setScaleY(1.06f);
        hero.animate()
                .alpha(1f)
                .scaleX(1f)
                .scaleY(1f)
                .setDuration(850)
                .setInterpolator(new DecelerateInterpolator())
                .start();

        heroText.setAlpha(0f);
        heroText.setTranslationY(dp(18));
        heroText.animate()
                .alpha(1f)
                .translationY(0f)
                .setStartDelay(140)
                .setDuration(600)
                .setInterpolator(new DecelerateInterpolator())
                .start();

        content.setAlpha(0f);
        content.setTranslationY(dp(14));
        content.animate()
                .alpha(1f)
                .translationY(0f)
                .setStartDelay(220)
                .setDuration(600)
                .setInterpolator(new DecelerateInterpolator())
                .start();
    }

    private void openOxfordLibrary() {
        startActivity(new Intent(this, OxfordLibraryActivity.class));
        overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out);
    }

    private void showHelp() {
        new AlertDialog.Builder(this)
                .setTitle(R.string.help_title)
                .setMessage(R.string.help_message)
                .setPositiveButton(R.string.close, null)
                .show();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}

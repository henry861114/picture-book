# 绘本英语 (Picture Book English)

Android 绘本阅读器，包含两部分内容：

- **绿岛精读**：32 页《Green Island》互动绘本，带逐句 TTS、中文翻译、跟读录音。
- **牛津树分级绘本**：Oxford Reading Tree Level 1–9，共 **243 本**原版 PDF 绘本，配套美音 MP3。

## 四个功能

1. **自动播放 / 自动翻页**
   - 点“自动”播放整本美音，画面按音频时间自动翻到下一页。
   - 页时间由构建脚本根据每页文字量和音频停顿估算，并写入 `assets/oxford/text/*.json`。
   - 如果设备没有可用音频，自动播放会退回系统 TTS 朗读。

2. **手动翻页 + 点句朗读 + 中文开关**
   - 左右滑动或点两侧箭头翻页；点右上角页码可跳页。
   - 点句子左边的播放按钮可朗读该句；Level 5 直接播放原版 MP3 对应片段。
   - **默认只显示英文**；点句子不会自动显示中文。
   - 点“中文”开关后，英文下方才显示中文；再点一次收起。
   - 点“连续朗读”（绿岛）会自动逐句朗读并翻页。

3. **平板/横屏**
   - 阅读器支持横屏和平板：图片在左，文字和音频控制在右。
   - 竖屏保持原来的“上图下文”布局。

4. **点单词查词**
   - 英文句子中的每个单词都可点击。
   - 点击后朗读单词，并显示音标 + 中文释义。
   - 词库来自 macOS 自带英汉词典整理出的离线 `assets/oxford/dictionary.json`，不联网。

另外保留“录音 / 回放”跟读功能：先听原音，再录下自己的声音进行对比。

## 构建

```bash
cd /Users/henry/code/app/英语/GreenIslandAndroid
./build_apk.sh
```

输出：

- `build/manual/PictureBookEnglish.apk`
- `../绘本英语.apk`

构建使用 Android SDK 的 `aapt2`、`javac`、`d8`、`zipalign`、`apksigner`，不依赖 Gradle。

## 数据与工具

| 文件 | 说明 |
| --- | --- |
| `assets/story.json` | 绿岛 32 页英文/中文句子 |
| `assets/oxford/pdf/` | 243 本牛津树 PDF |
| `assets/oxford/audio/` | 243 本美音 MP3 |
| `assets/oxford/text/` | 每本书每页 OCR 文本、中文逐词释义、音频页时间 |
| `assets/oxford/dictionary.json` | 3,810 个词条的离线音标/中文 |
| `assets/oxford/covers/` | 书架封面缩略图 |
| `tools/OxfordAssetBuilder.swift` | 复制 PDF/MP3、生成封面和 `library.json` |
| `tools/OxfordTextBuilder.swift` | Vision OCR 全部分级绘本页面 |
| `tools/dict_lookup.c` | 调用 macOS 英汉词典导出词条 |
| `tools/build_dictionary_and_gloss.py` | 生成离线词库和逐词中文释义 |
| `tools/build_audio_times.py` | 用文字量 + 音频停顿估算每页起止时间 |
| `tools/BrandAssets.swift` | 生成 App 图标和首页拼贴图 |

## 体积说明

完整 APK 约 **990 MB**：

| 内容 | 大小 |
| --- | --- |
| 243 本牛津树 PDF | 约 714 MB |
| 243 本美音音频（32 kbps 单声道 AAC） | 约 269 MB |
| 封面、文字、词典等 | 约 20 MB |

PDF 本身已经是压缩过的扫描图片，ZIP/APK 再压缩几乎不会变小；音频已从 64 kbps 立体声转成 32 kbps 单声道 AAC，节省约 240 MB。

如果完整 APK 安装不方便，可以使用单级版：

| 安装包 | 内容 | 大小 | 包名 |
|---|---|---:|---|
| `绘本英语-L5.apk` / `绘本英语-Level5.apk` | Level 5 的 24 本 + 绿岛 | 114 MB | `com.henry.picturebook.l5` |
| `绘本英语-L6.apk` | Level 6 的 21 本 + 绿岛 | 168 MB | `com.henry.picturebook.l6` |
| `绘本英语-L7.apk` | Level 7 的 18 本 + 绿岛 | 130 MB | `com.henry.picturebook.l7` |
| `绘本英语-L8.apk` | Level 8 的 12 本 + 绿岛 | 91 MB | `com.henry.picturebook.l8` |
| `绘本英语-L9.apk` | Level 9 的 12 本 + 绿岛 | 97 MB | `com.henry.picturebook.l9` |

Level 5–9 使用不同包名，可以**同时安装**；桌面名称分别是“绘本英语 L5”到“绘本英语 L9”。

完整版现在默认打开 **Level 5**（首次升级会一次性切到 L5，之后记住用户选择）。

## 说明

- 牛津树 PDF 是扫描图片，没有文字层；文本由 macOS Vision OCR 识别，少量页面可能存在识别误差。
- 中文句子采用“逐词释义”的离线读法，不是文学翻译；单词释义来自系统英汉词典，适合辅助理解。
- 自动翻页时间是估算值；如果觉得某本书翻页偏早/偏晚，可以手动翻页，或调整 `tools/build_audio_times.py` 后重新生成 `text/*.json`。
- 新打开一本书会直接停在“第一页有文字的页面”，避免只看到无字封面；左右滑动仍可回到封面。
- 阅读器会自动裁掉扫描页四周的白边，并按页面比例调整图片高度，横版绘本的插图会尽量占满屏幕。
- 已用 Whisper 转写全部 243 本配套音频，把旁白文字补进原来的“无字书”页面（例如 *At School* 现在每页都有英文和中文）。
- 纯插图页会借用相邻故事页的文字，避免出现空白文字面板；封面和部分版权/活动页仍保持无文字。
- 新增旁白文字的英文是语音识别结果，可能与原书印刷文字略有差异。
- **Level 5 的句子已经改成整句中文翻译**；人名保留英文（Chip、Biff、Kipper、Wilf、Wilma、Floppy、Mrs May 等），点人名时显示“人名”。
- 其他 Level 仍使用离线逐词释义；需要的话可以继续分批翻译。
- Level 5 已用 whisper.cpp 的**词级时间戳**对齐每一句，点句子会精确跳到原版 MP3 的该句起点并在句尾暂停；其他 Level 仍按页内比例估算。
- 点单词仍使用系统 TTS 发音 + 离线音标/中文释义。
- 句子字号已调大：牛津绘本英文 16sp、中文 12sp；绿岛英文 16sp、中文 12.5sp。
- 底部操作按钮改为纯文字居中（自动 / 原音 / 录音 / 回放），不再因左侧图标导致文字偏移。

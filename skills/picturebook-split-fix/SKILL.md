---
name: picturebook-split-fix
description: 修复"绘本英语"App(牛津树分级阅读 L1-L9)的多格页拆分、图片/文字/音频对齐、文字清理问题时使用。涵盖拆分管线铁律、OCR 坐标系、通栏页/紧贴双页判定、句子分配与移交、调试与装机验证方法。凡涉及 split_multipanel.py、panel_ocr.py、text JSON 数据、Lesson 版书页错乱、句子错位/重复等问题都应先读本手册。
---

# 绘本英语多格页拆分修复手册

## 项目结构与数据流

- 工程:`/Users/henry/code/app/英语/GreenIslandAndroid`(即 picture-book repo)
- 文本数据:`app/src/main/assets/oxford/text/L{级别}-{书号}.json`(每级别一个独立 App,包名 `com.henry.picturebook.lN`)
- 扫描 PDF:`app/src/main/assets/oxford/pdf/`
- 状态快照:`/tmp/text_refined/`(精调基线,**唯一可信源**);`/tmp/text_split/`(拆分后)
- 构建交付:`./build_level_app.sh N` → `build/manual/PictureBookEnglish-LN.apk` → 拷贝到 `英语/绘本英语-LN.apk`

## 铁律(违反必出事故)

1. **拆分前必须先恢复精调快照**:`cp /tmp/text_refined/L*.json app/src/main/assets/oxford/text/`。在已拆分数据上重跑拆分会固化错误且把普通书清空(历史上发生过:空书 `{"pages": []}` 一旦写盘,后续所有运行读到空数据永远输出 0 页)。
2. 修改数据后必须跑完整链:`split_multipanel.py → dedupe_text.py → collapse_attributions.py → clean_zh_duplicates.py → normalize_windows.py`,级别参数一致。
3. 构建前先跑数据审计:空书、矩形面积、句子时序单调、回声残留(见文末审计脚本)。
4. 调试运行**也必须先恢复快照**——"只是看看"的调试跑会写脏数据。

## OCR 坐标系(最高频的错误源)

`panel_ocr.ocr_lines` 返回元组 **`(text, x, y, w, h)`,其中 y 是"自下而上的底边坐标"**:

```
y_topdown_top = 1.0 - y          # 正确
y_topdown_top = 1.0 - (y + h)    # 错(把 h 当 y)
y_topdown_top = 1.0 - (y + w)    # 大错(把宽度 w 当高度用,历史事故)
```

规范化为 `(x, y_topdown, w, h, text)` 后再进检测。画框验证时注意解包顺序,别把 w/h 弄反(画出来是细长条 = 解包反了)。

## 面板结构检测(split_multipanel.py Lesson 分支)

只有 **Lesson 版**书需要拆分(书内每个 PDF 页含 2~4 个原书页);Lesson 检测 = OCR 前 3 页找 `Lesson N`。**只有 L6 有 Lesson 版书**(L5/L7/L8/L9 全部是普通单页书,走整页分支,不拆分)。

检测优先级(逐行 r 处理):

1. **y 边界 = 扫描件的整行白色沟槽**(`white_gutters(img,'y')`,非白像素占比 <1.5%、高 ≥0.012 页高、非页边),再用 **OCR 文字组校验**:相邻组对之间至多取一个沟槽、必须落在组间、选**最贴近上一组末行**的(真面板边界紧贴说明文字下方;插图与说明间的白带、页码上方的白带都是假的)。
2. **x 边界**:优先整列白色沟槽(常不存在,四格页插图紧贴);无沟槽时回退**文字范围中点**(左组最右边缘与右组最左边缘的中点,用 max/min 全量,不是百分位)。
3. **通栏页判定**(一整幅横宽插图 + 说明分两栏排版):
   - 两侧说明文字块**顶部对齐**(同一段落分栏,|顶部差| ≤0.06)且插图带两侧墨水覆盖(`band_ink`)都 ≥0.10 → 整行合并为一格;
   - 标题页的左列文字在页顶、右列说明在页底(顶部错位大)→ 保持分栏,不要被"墨水覆盖高"骗了(标题页有椭圆插图,ink 也会高);
   - **紧贴双页判定**:插图区白色竖沟槽(`band_col_gutters`,须贯通整个插图带)存在 → 两格;无白缝但**右栏(x>0.35)有页码角标**(1-2 位数字 token,原始文本 ≤3 字符)→ 两格(角标是出版方每页页首的标记);仅左侧一个角标 → 通栏一格。
   - **大坑**:列的默认值必须是相邻边对 `[(x_edges[j], x_edges[j+1])]`,不能写成 `(x_edges[0], x_edges[-1])`(那就是整页宽)。
4. 端部修剪 `trim_end_bands(min_band=0.12)`:页码行产生的末尾小带;但**只有组校验失败时才把未认领沟槽全收**(Activities 练习页只有 1 个文字组,不能把活动区行距白带全当边界)。

## 句子分配与移交

- `assign_by_text(sentences, panel_texts, with_scores=True)`:文字光标 + 滑窗匹配,置信度阈值 **0.45**,低置信句子"停留"在当前格;返回每句的 `(key, r, confident)`。
- **页尾移交**:最后一格的尾随低置信句子(≤3 句,且最后一格仍保有高置信说明)是**下一页的过渡旁白**(如 "At last, Biff and Chip went into a hall."),移交给下一个 PDF 页,加到它第一格开头。否则会出现"第 N+1 页的文字显示在第 N 页"。
- **碎片合并必须重建桶**:合并循环里 dict 是共享引用,只改 `prev['en']` 不从桶里删除被合并句 → 产生重复句(历史事故:`merged_sents` 是死代码,靠 dedupe 兜底掩盖)。正确做法:收集 `(pdf_i, sent)` 平铺 → 合并 → `per_pdf = {i: []}; for pdf_i, s in merged_sents: per_pdf[pdf_i].append(s)`。
- **裸称呼回并**:`Said Biff.` / `He said.` 这类碎片是上一句的称呼(朗读顺序引语在前),回并进上一句并把句号转逗号(`…"live here," said Biff.`);上一句已以称呼结尾则不并。
- **悬挂称谓碎片**:refined 数据里常见 `'Mr.' + 'Mr Johnson showed…'`、`'Mrs.' + 'Mrs May went too.'`;合并时若下一句**以同一称谓词开头**,丢弃上一句的悬挂碎片(否则拼出 "Mr. Mr Johnson")。
- `collapse_attributions.py` 的称呼去重模式需支持**两词人名**(`said Mr Johnson.`)和**代词称呼**(`He said. He said.`)。

## 阅读器显示(OxfordReaderActivity)

- `.l6` 包:图片卡**固定宽高**(高度 = 屏幕高 46%,不随图片调整),图片 `fitCenter` 缩放完整显示;
- 其他级别:卡片跟随 3:4;竖屏固定、横屏 MATCH_PARENT。

## 调试方法(按此顺序,先看后算)

1. **渲染 PDF 页直接看版面**:`pdfium.PdfDocument(...)[i].render(...).to_pil()`,缩图后用图片查看。永远先看真实版面再推公式——通栏页、紧贴页、角标都是"看"出来的。
2. **画 OCR 框验证坐标**:把行框画到渲染图上,核对是否贴合文字。
3. **DBG 环境变量**(flush=True):
   - `DBGG2`:每页沟槽 + 组数 + 边界结果
   - `DBGG2r`:每行的插图带/沟槽/角标判定
   - `DBGG2m`:通栏合并的顶部对齐/墨水数据
   - `DBGD5`:每页句子桶状态;`DBGA`:逐句分配置信度
4. **装机验证**:`adb -s emulator-5554 install -r`;**screencap 是 1080×2340**,点按坐标要按真实分辨率换算(预览图缩放过的坐标 ×1080/宽);翻页箭头约在 (982, 794) / (98, 790);截图后 PIL resize 再读图。
5. 注意 stdout 缓冲会让无 flush 的输出乱序,别据此推断执行顺序。

## 数据审计脚本要点

```python
# 每本书检查:
# 1) 非空(pages > 0)
# 2) rect 页:0<=x0<x1<=1、0<=y0<y1<=1、面积 >= 0.10
# 3) 跨页句子 startMs 单调
# 4) 无文字页占比 < 60%
# 5) 普通书页数 == 精调快照页数;精调句子在输出中可找到(缺失项应全部是
#    "said X said X" 类回声清理,否则是丢失)
```

## 已知限制(不要当成 bug 反复修)

- 跨 PDF 页旁白连续、无翻页音频分隔时,个别句子可能落在相邻面板(±1),需要书名+页码单独调参;
- whisper 转写噪声导致的个别错词(如 "Ads or Tails?" 应为 "Heads or Tails?")属于数据源质量,发现一处修一处;
- refined 快照是基线:输出与快照的文本差异应仅限于回声清理与碎片合并,若超出需人工核对。

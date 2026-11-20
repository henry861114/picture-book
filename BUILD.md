# 构建说明(重要)

本仓库只保存 **代码 + 文本对齐数据**(`app/src/main/assets/oxford/text/`、
`library.json`、`dictionary.json`),**不保存二进制资产**(扫描 PDF、音频、封面图),
以保持仓库轻量。

## 完整可编译副本

包含全部二进制资产、可直接编译出 App 的完整副本在:

```
/Users/henry/code/app/magic-tool-for-english
```

(精调快照备份:`magic-tool-for-english/snapshots/`;原始音频备份:`/Users/henry/code/app/audio-archive/`。)

```bash
cd /Users/henry/code/app/magic-tool-for-english
./build_level_app.sh 6        # 产物: dist/绘本英语-L6.apk
```

**从 GitHub 新克隆本仓库后**,先运行(自动从上述完整副本同步二进制资产):

```bash
./sync_assets.sh
./build_level_app.sh 6        # 之后即可正常编译
```

## 同步方式

- 代码改动在任一副本进行后,拷贝到另一副本(`app/src/main/java`、`tools/`、构建脚本)。
- 文本数据改动在本仓库进行(管线工具以本仓库路径为工作目录),然后把
  `app/src/main/assets/oxford/text/*.json`、`library.json`、`dictionary.json`
  拷贝到 magic-tool-for-english 再编译。
- 二进制资产(pdf/audio/covers/home_hero.jpg/pages)仅存在于
  magic-tool-for-english,由 .gitignore 排除,勿提交。

## 数据管线

见 `skills/picturebook-split-fix/SKILL.md`(多格页拆分修复手册)与
`docs/README-original.md`(原始项目说明)。

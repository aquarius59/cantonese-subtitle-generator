# 粤语拼音字幕生成器 (Cantonese Pinyin Subtitle Generator)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.8+-green.svg)](https://python.org)

> 🎬 专为低配置电脑优化的粤语歌词/字幕视频生成工具（默认针对1280x720分辨率的视频）

## ✨ 特性

- **粤语拼音自动标注** - 基于 [ToJyutping](https://github.com/CanCLID/ToJyutping) 库，自动为汉字添加粤拼
- **多音字智能优化** - 内置常见粤语多音字规则（行/长/乐/重等），根据上下文自动选择正确读音
- **手动标注支持** - 支持 `字[拼音]` 格式手动修正，如 `好[hou2]好[hou3]食饭`
- **低配置优化** - 针对 i3 + 8GB 内存优化，支持 QOI 格式加速、可调线程数
- **智能排版** - 屏幕垂直居中，多行时根据字数自动选择居中/左对齐
- **声调颜色区分** - 6 个声调分别用不同颜色显示，便于学习
- **硬件编码加速** - 自动生成 FFmpeg 合成脚本，自动检测 QSV/NVENC/AMF 硬件编码器

## 📦 安装

### 环境要求
- Python 3.8+
- 8GB+ 内存（推荐）
- FFmpeg（用于视频合成）

### 依赖安装

```bash
pip install ToJyutping Pillow numpy

# 可选：安装 QOI 加速
pip install qoi
```

### 字体准备

下载以下字体文件放置到脚本目录：
- [Source Han Sans HW SC Bold](https://github.com/adobe-fonts/source-han-sans/releases) 或
- [LXGW WenKai](https://github.com/lxgw/LxgwWenKai)

## 🚀 使用方法

### 1. 准备字幕文件

创建 SRT 格式的字幕文件 `subtitle.srt`：

```srt
1
00:00:01,000 --> 00:00:05,000
好[hou2]好[hou3]食饭

2
00:00:06,000 --> 00:00:10,000
行[haang4]街 行[hong4]业
```

> 💡 方括号内为可选的手动粤拼标注，不标注则自动转换

### 2. 运行生成器

```bash
python main.py
```

按提示操作：
1. 输入字幕文件路径（或直接回车使用默认 `subtitle.srt`）
2. 选择是否预览特定行
3. 选择是否使用 QOI 加速
4. 设置线程数（默认 CPU 核心数的一半）

### 3. 合成视频

```bash
# 将视频重命名为 input.mp4 放在同一目录
python render_video.py

# 或使用自定义路径
python render_video.py --input video.mp4 --output result.mp4
```

## 📁 项目结构

```
.
├── main.py              # 主程序：解析字幕、渲染帧
├── render_video.py      # 自动生成的视频合成脚本
├── frames/              # 渲染的帧序列（QOI/PNG 格式）
├── subtitle.srt         # 示例字幕文件
├── user_dict.txt        # 用户自定义拼音词典（可选）
└── README.md            # 本文件
```

## ⚙️ 自定义配置

### 用户词典

创建 `user_dict.txt` 添加自定义读音：

```
# 格式：汉字:拼音
嘅:ge3
咁:gam3
嗰:go2
```

### 调整样式

在 `QOIRenderer.__init__` 中修改：

```python
self.char_font_size = 64        # 汉字字号
self.pinyin_font_size = 32      # 拼音字号
self.base_char_spacing = 16     # 字符间距
self.max_lines = 2              # 最大行数
self.min_align_ratio = 0.5      # 左对齐阈值
```

## 🎨 声调颜色

| 声调 | 颜色 | 示例 |
|:---:|:---:|:---:|
| 1 阴平 | 🔴 红 | fan1 分 |
| 2 阴上 | 🟠 橙 | fan2 粉 |
| 3 阴去 | 🟢 绿 | fan3 训 |
| 4 阳平 | 🔵 蓝 | fan4 坟 |
| 5 阳上 | 🩷 粉 | fan5 愤 |
| 6 阳去 | 🟣 紫 | fan6 份 |

## 🖥️ 系统要求

| 配置项 | 最低要求 | 推荐配置 |
|:---:|:---:|:---:|
| CPU | i3-4030U 同级 | i5 及以上 |
| 内存 | 8GB | 16GB |
| 显卡 | 核显即可 | 支持 Intel QSV/NVIDIA NVENC |
| 存储 | 10GB 可用空间 | SSD |

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 待优化项
- [ ] 支持更多字幕格式（ASS, VTT）
- [ ] 添加更多多音字规则
- [ ] 支持 GPU 加速渲染
- [ ] 图形界面（GUI）版本

## 📄 许可证

本项目采用 **GNU General Public License v3.0 (GPL-3.0)** 开源许可证。

```
粤语拼音字幕生成器
Copyright (C) 2026

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```

详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- [ToJyutping](https://github.com/CanCLID/ToJyutping) - 粤语拼音转换库
- [Source Han Sans](https://github.com/adobe-fonts/source-han-sans) - 开源泛CJK字体
- [LXGW WenKai](https://github.com/lxgw/LxgwWenKai) - 霞鹜文楷字体


---

⭐ 如果这个项目对你有帮助，请给个 Star！

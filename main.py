"""
粤语拼音字幕生成器 - 低配置优化版（使用 ToJyutping 库 + 手动标注 + 多音字优化）
针对 i3-4030U + 8GB 内存优化
特性：降低分辨率、可调线程数、QOI格式、屏幕正中央、边界检测、手动标注、多音字自动优化、进度时间预估
用法：在字幕文本中用 字[拼音] 标注，例如 好[hou2]好[hou3]食饭
"""

from PIL import Image, ImageDraw, ImageFont
import os
import re
import sys
import math
import time
import threading
import gc
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import numpy as np

# QOI 加速（可选）
try:
    import qoi
    QOI_AVAILABLE = True
except ImportError:
    QOI_AVAILABLE = False

# 拼音库
try:
    import ToJyutping
    TOJYUTPING_AVAILABLE = True
    print("✅ ToJyutping 已安装")
except ImportError:
    TOJYUTPING_AVAILABLE = False
    print("❌ 请安装: pip install ToJyutping")
    sys.exit(1)

sys.stdout.reconfigure(encoding='utf-8')


@dataclass
class LyricChar:
    char: str
    pinyin: str
    tone: str
    source: str = "auto"


@dataclass
class LyricLine:
    chars: List[LyricChar]
    start_time: float
    end_time: float
    line_number: int
    original_text: str


class CantoneseDictionary:
    """粤语词典 - ToJyutping + 用户自定义 + 多音字自动优化"""

    OVERRIDE = {}

    POLYPHONE_RULES = {
        '行': {'haang4': ['行走', '步行', '行路', '行街', '行山', '行开'], 'hong4': ['银行', '行业', '行情', '行家', '行规', '行内']},
        '长': {'coeng4': ['长短', '长江', '长度', '长城', '长途'], 'zoeng2': ['长大', '成长', '家长', '班长', '校长']},
        '乐': {'lok6': ['快乐', '欢乐', '乐园', '乐天', '乐土'], 'ngok6': ['音乐', '乐器', '乐队', '乐谱']},
        '重': {'cung5': ['重要', '重点', '重大', '重用', '重担'], 'zung6': ['重复', '重叠', '重新', '双重', '沉重']},
        '好': {'hou2': ['好人', '好坏', '很好', '好食', '好靓'], 'hou3': ['爱好', '好客', '好学', '好胜']},
        '还': {'waan4': ['还钱', '还书', '归还', '还债'], 'waan6': ['还有', '还是', '还要', '还好']},
        '只': {'zek3': ['一只', '两只', '船只', '只只'], 'zi2': ['只有', '只是', '只要', '只可']},
        '的': {'dik1': ['的确', '目的', '中的', '标的'], 'di1': ['我的', '你的', '他的', '好的']},
        '着': {'zoek6': ['穿着', '看着', '听着', '走着'], 'zoek3': ['着火', '着凉', '着急', '着迷']},
        '分': {'fan1': ['分开', '分别', '分钟', '分数'], 'fan6': ['部分', '成分', '身份', '本分']},
        '间': {'gaan1': ['房间', '时间', '空间', '人间'], 'gaan3': ['间隔', '离间', '间谍', '间中']},
        '中': {'zung1': ['中国', '中心', '中间', '空中'], 'zung3': ['中奖', '中意', '中弹', '中选']},
        '为': {'wai4': ['因为', '以为', '行为', '认为'], 'wai6': ['为了', '为何', '为了', '为人民']},
        '相': {'soeng1': ['相信', '相同', '相识', '相处'], 'soeng3': ['相片', '相貌', '相册', '面相']},
        '教': {'gaau3': ['教学', '教室', '教师', '教育'], 'gaau1': ['教课', '教书', '教人']},
        '降': {'gong3': ['下降', '降落', '降低', '降级'], 'hong4': ['投降', '降服', '降顺']},
        '调': {'diu6': ['调动', '调换', '调查', '调整'], 'tiu4': ['调和', '调皮', '空调', '调味']},
        '传': {'cyun4': ['传播', '传送', '传统', '传奇'], 'zyun6': ['传记', '自传', '经传']},
        '转': {'zyun3': ['转变', '转换', '转向', '转身'], 'zyun2': ['转动', '旋转', '打转']},
        '背': {'bui3': ['背后', '背景', '背叛', '背心'], 'bui1': ['背负', '背债', '背包']},
        '便': {'bin6': ['方便', '便利', '便宜', '便当'], 'pin4': ['便宜']},
        '听': {'teng1': ['听到', '听紧', '听日', '听歌'], 'ting1': ['听讲', '听信']},
        '里': {'leoi5': ['里面', '哪里', '风雨里', '内里'], 'lei5': ['公里', '千里', '万里', '里海']},
        '系': {'hai6': ['关系', '系统', '系列', '体系'], 'hai2': ['系咪', '系咁', '系度', '系边']},
        '唔': {'m4': ['唔系', '唔好', '唔要', '唔得'], 'ng4': ['唔该']},
        '咁': {'gam3': ['咁多', '咁好', '咁大', '咁样'], 'gam2': ['咁啱']},
        '嘅': {'ge3': ['我嘅', '你嘅', '佢嘅']},
        '哋': {'dei6': ['我哋', '你哋', '佢哋']},
        '喺': {'hai2': ['喺度', '喺边', '喺呢度']},
        '咗': {'zo2': ['食咗', '去咗', '做咗']},
        '嘢': {'je5': ['做嘢', '食嘢', '买嘢']},
        '食': {'sik6': ['食饭', '食嘢', '食完', '食物']},
        '饮': {'jam2': ['饮水', '饮茶', '饮酒']},
        '睇': {'tai2': ['睇到', '睇紧', '睇吓', '睇戏']},
    }

    @classmethod
    def _load_user_dict(cls, path="user_dict.txt"):
        if not os.path.exists(path):
            return
        print(f"📖 加载用户词典: {path}")
        count = 0
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if ':' in line:
                    char, pinyin = line.split(':', 1)
                    char = char.strip()
                    pinyin = pinyin.strip()
                    if not char or not pinyin:
                        continue
                    tone = pinyin[-1] if pinyin[-1].isdigit() else ''
                    cls.OVERRIDE[char] = (pinyin, tone)
                    count += 1
        print(f"  已加载 {count} 个自定义条目")

    @classmethod
    def get_pinyin(cls, char: str, context: str = "") -> Tuple[str, str]:
        if char in '（）()、，。？！：；""''\n\r\t .,!?':
            return ('', '')
        if char in cls.OVERRIDE:
            return cls.OVERRIDE[char]
        if char in cls.POLYPHONE_RULES:
            rule = cls.POLYPHONE_RULES[char]
            for pinyin, words in rule.items():
                for w in words:
                    if w in context:
                        tone = pinyin[-1] if pinyin[-1].isdigit() else ''
                        return (pinyin, tone)
        if TOJYUTPING_AVAILABLE:
            try:
                result = ToJyutping.get_jyutping_list(char)
                if result and len(result) > 0:
                    pinyin = result[0][1]
                    if pinyin:
                        tone = pinyin[-1] if pinyin[-1].isdigit() else ''
                        return (pinyin, tone)
            except Exception:
                pass
        return ('', '')


CantoneseDictionary._load_user_dict()


def parse_manual_annotation(text: str) -> List[Tuple[str, str, str]]:
    result = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch != '[':
            result.append((ch, None, None))
            i += 1
            continue
        if i == 0 or not result:
            result.append(('[', None, None))
            i += 1
            continue
        j = i + 1
        while j < n and text[j] != ']':
            j += 1
        if j >= n:
            result.append(('[', None, None))
            i += 1
            continue
        pinyin_candidate = text[i+1:j]
        if re.match(r'^[a-z]+\d$', pinyin_candidate):
            if result and result[-1][1] is None:
                prev_char = result[-1][0]
                tone = pinyin_candidate[-1]
                result[-1] = (prev_char, pinyin_candidate, tone)
                i = j + 1
                continue
        result.append(('[', None, None))
        i += 1
    return result


class LineLayout:
    def __init__(self):
        self.positions = []
        self.bg_rects = []
        self.line_count = 1
        self.line_alignments = []


class QOIRenderer:
    def __init__(self, width=1280, height=720, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        self.frame_duration = 1.0 / fps
        self.audio_offset = 0.0
        self.lines = []
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.frames_dir = os.path.join(self.script_dir, "frames")
        self.debug = False

        self.tone_colors = {
            '1': (255, 80, 80), '2': (255, 180, 80), '3': (80, 255, 80),
            '4': (80, 160, 255), '5': (255, 120, 200), '6': (200, 80, 255),
        }

        # 可调参数
        self.char_font_size = 64
        self.pinyin_font_size = 32
        self.bg_color = (0, 0, 0, 102)
        self.base_char_spacing = 16          # 汉字间距
        self.line_padding = 28
        self.max_line_width = int(width * 0.85)
        self.line_height = self.pinyin_font_size + self.char_font_size + 24
        self.max_lines = 2

        self.long_syllable_threshold = 4
        self.extra_spacing_long = 10

        # 逐行对齐比例：当前行字数 >= 上一行字数 * min_align_ratio 时居中，否则左对齐
        self.min_align_ratio = 0.5

        self.line_cache = {}
        self.layout_cache = {}
        self.cache_lock = threading.Lock()
        self.max_cache_size = 50

        self.thread_local = threading.local()
        self.char_font = None
        self.pinyin_font = None
        self._load_fonts()

    def _load_fonts(self):
        font_paths = [
            os.path.join(self.script_dir, "SourceHanSansHWSC-Bold.otf"),
            os.path.join(self.script_dir, "LXGWWenKaiMono-Bold.ttf"),
        ]
        def load_font(size):
            for path in font_paths:
                if os.path.exists(path):
                    try:
                        return ImageFont.truetype(path, size)
                    except:
                        continue
            return ImageFont.load_default()
        self.char_font = load_font(self.char_font_size)
        self.pinyin_font = load_font(self.pinyin_font_size)
        print("✅ 字体加载完成")

    def _get_thread_fonts(self):
        if not hasattr(self.thread_local, 'char_font'):
            self.thread_local.char_font = self.char_font
            self.thread_local.pinyin_font = self.pinyin_font
        return self.thread_local.char_font, self.thread_local.pinyin_font

    def _time_to_seconds(self, time_str: str) -> float:
        time_str = time_str.replace(',', '.')
        parts = time_str.split(':')
        return int(parts[0])*3600 + int(parts[1])*60 + float(parts[2])

    def parse_srt_file(self, srt_path: str) -> List[LyricLine]:
        with open(srt_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        return self.parse_srt(content)

    def parse_srt(self, srt_content: str) -> List[LyricLine]:
        lines = []
        entries = re.split(r'\n\s*\n', srt_content.strip())
        for entry in entries:
            entry_lines = entry.strip().split('\n')
            if len(entry_lines) < 3:
                continue
            try:
                line_num = int(entry_lines[0].strip())
                time_line = entry_lines[1].strip()
                match = re.match(r'(\d{2}:\d{2}:\d{2}[,.]\d{3}) --> (\d{2}:\d{2}:\d{2}[,.]\d{3})', time_line)
                if not match:
                    continue
                start = self._time_to_seconds(match.group(1))
                end = self._time_to_seconds(match.group(2))
                raw_text = ' '.join(entry_lines[2:]).strip()
                annotated = parse_manual_annotation(raw_text)
                final_chars = []
                for ch, manual_pinyin, manual_tone in annotated:
                    if manual_pinyin:
                        pinyin = manual_pinyin
                        tone = manual_tone
                        source = "manual"
                    else:
                        pinyin, tone = CantoneseDictionary.get_pinyin(ch, context=raw_text)
                        if ch in CantoneseDictionary.OVERRIDE:
                            source = "userdict"
                        elif ch in CantoneseDictionary.POLYPHONE_RULES:
                            source = "polyphone"
                        else:
                            source = "auto"
                    final_chars.append(LyricChar(ch, pinyin, tone, source))
                lines.append(LyricLine(final_chars, start, end, line_num, raw_text))
            except Exception as e:
                print(f"警告: {e}")
        print(f"✅ 解析了 {len(lines)} 行歌词")
        self.lines = lines
        return lines

    def _split_into_lines(self, chars: List[LyricChar]) -> List[List[LyricChar]]:
        if not chars:
            return []
        total_width = len(chars) * self.char_font_size + (len(chars)-1) * self.base_char_spacing
        if total_width <= self.max_line_width:
            return [chars]
        max_per_line = max(1, int((self.max_line_width - (len(chars)-1)*self.base_char_spacing) / self.char_font_size))
        lines = [chars[i:i+max_per_line] for i in range(0, len(chars), max_per_line)]
        if len(lines) > self.max_lines:
            lines = lines[:self.max_lines]
        return lines

    def _calculate_layout(self, line: LyricLine) -> LineLayout:
        with self.cache_lock:
            if line.line_number in self.layout_cache:
                return self.layout_cache[line.line_number]

        chars = [c for c in line.chars if c.char.strip()]
        if not chars:
            return None

        char_lines = self._split_into_lines(chars)
        _, pinyin_font = self._get_thread_fonts()

        # 第一步：计算每一行的宽度和拼音信息
        line_data = []
        for line_chars in char_lines:
            pinyin_widths = []
            pinyin_lens = []
            for c in line_chars:
                if c.pinyin:
                    temp_img = Image.new('RGB', (1,1))
                    temp_draw = ImageDraw.Draw(temp_img)
                    bbox = temp_draw.textbbox((0,0), c.pinyin, font=pinyin_font)
                    w = bbox[2] - bbox[0]
                    pinyin_widths.append(w)
                    pinyin_lens.append(len(c.pinyin))
                else:
                    pinyin_widths.append(0)
                    pinyin_lens.append(0)

            extra = [0] * (len(line_chars)-1)
            for i in range(len(line_chars)-1):
                if pinyin_lens[i] >= self.long_syllable_threshold or pinyin_lens[i+1] >= self.long_syllable_threshold:
                    extra[i] = self.extra_spacing_long

            char_width = self.char_font_size
            line_width = len(line_chars) * char_width
            if extra:
                line_width += sum(self.base_char_spacing + e for e in extra)
            elif len(line_chars) > 1:
                line_width += (len(line_chars)-1) * self.base_char_spacing

            if line_width > self.max_line_width:
                line_width = self.max_line_width

            line_data.append({
                'chars': line_chars,
                'width': line_width,
                'pinyin_widths': pinyin_widths,
                'pinyin_lens': pinyin_lens,
                'extra': extra,
                'char_width': char_width,
                'char_count': len(line_chars),
            })

        # 第二步：逐行决定起始 X 坐标（对齐方式）
        start_x_list = []
        for idx, data in enumerate(line_data):
            if idx == 0:
                start_x = (self.width - data['width']) // 2
                start_x = max(5, min(start_x, self.width - data['width'] - 5))
                start_x_list.append(start_x)
            else:
                prev_count = line_data[idx-1]['char_count']
                curr_count = data['char_count']
                if curr_count >= prev_count * self.min_align_ratio:
                    start_x = (self.width - data['width']) // 2
                else:
                    start_x = start_x_list[idx-1]
                start_x = max(5, min(start_x, self.width - data['width'] - 5))
                start_x_list.append(start_x)

        # 屏幕正中央（垂直居中）
        total_height = len(char_lines) * self.line_height
        start_y = (self.height - total_height) // 2
        start_y = max(10, start_y)
        cur_y = start_y

        layout = LineLayout()
        layout.line_count = len(char_lines)
        layout.line_alignments = ['center' if i == 0 or line_data[i]['char_count'] >= line_data[i-1]['char_count'] * self.min_align_ratio else 'left' for i in range(len(line_data))]

        for idx, data in enumerate(line_data):
            line_chars = data['chars']
            line_width = data['width']
            pinyin_widths = data['pinyin_widths']
            extra = data['extra']
            char_width = data['char_width']
            start_x = start_x_list[idx]

            pinyin_y = cur_y
            char_y = pinyin_y + self.pinyin_font_size

            cur_x = start_x
            for i, c in enumerate(line_chars):
                x = cur_x
                if c.pinyin:
                    pinyin_x = x + (char_width - pinyin_widths[i]) // 2
                    pinyin_x = max(2, min(pinyin_x, self.width - pinyin_widths[i] - 2))
                else:
                    pinyin_x = x

                layout.positions.append({
                    'char_x': x, 'char_y': char_y,
                    'pinyin_x': pinyin_x, 'pinyin_y': pinyin_y,
                    'char': c.char, 'pinyin': c.pinyin, 'tone': c.tone
                })

                cur_x += char_width + self.base_char_spacing
                if i < len(extra):
                    cur_x += extra[i]

            # 背景矩形
            min_x = max(0, start_x - self.line_padding)
            max_x = min(self.width, start_x + line_width + self.line_padding)
            min_y = max(0, cur_y - 10)
            max_y = min(self.height, char_y + self.char_font_size + 20)
            layout.bg_rects.append((min_x, min_y, max_x, max_y))

            cur_y += self.line_height

        with self.cache_lock:
            self.layout_cache[line.line_number] = layout
            if len(self.layout_cache) > self.max_cache_size:
                keys = list(self.layout_cache.keys())
                for k in keys[:len(keys)//2]:
                    del self.layout_cache[k]
        return layout

    def render_line_image(self, line: LyricLine) -> Image.Image:
        with self.cache_lock:
            if line.line_number in self.line_cache:
                return self.line_cache[line.line_number]

        layout = self._calculate_layout(line)
        if not layout:
            return Image.new('RGBA', (self.width, self.height), (0,0,0,0))

        img = Image.new('RGBA', (self.width, self.height), (0,0,0,0))
        char_font, pinyin_font = self._get_thread_fonts()
        draw = ImageDraw.Draw(img)

        for rect in layout.bg_rects:
            draw.rectangle(rect, fill=self.bg_color)

        for pos in layout.positions:
            if pos['pinyin']:
                color = self.tone_colors.get(pos['tone'], (255,255,255))
                for dx,dy in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                    draw.text((pos['pinyin_x']+dx, pos['pinyin_y']+dy),
                              pos['pinyin'], font=pinyin_font, fill=(0,0,0))
                draw.text((pos['pinyin_x'], pos['pinyin_y']),
                          pos['pinyin'], font=pinyin_font, fill=color)
            for dx,dy in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                draw.text((pos['char_x']+dx, pos['char_y']+dy),
                          pos['char'], font=char_font, fill=(0,0,0))
            draw.text((pos['char_x'], pos['char_y']),
                      pos['char'], font=char_font, fill=(255,255,255))

        with self.cache_lock:
            self.line_cache[line.line_number] = img
            if len(self.line_cache) > self.max_cache_size:
                keys = list(self.line_cache.keys())
                for k in keys[:len(keys)//2]:
                    del self.line_cache[k]
                gc.collect()
        return img

    def render_empty_frame(self):
        return Image.new('RGBA', (self.width, self.height), (0,0,0,0))

    def time_to_frame(self, t):
        return int(math.floor(t * self.fps))

    def get_frame_line(self, frame):
        t = frame / self.fps - self.audio_offset
        tol = self.frame_duration / 2
        for line in self.lines:
            if line.start_time - tol <= t < line.end_time + tol:
                return line
        return None

    def preview_lines(self, line_spec: str):
        print("\n预览模式")
        nums = []
        if line_spec.lower() == 'all':
            nums = list(range(1, len(self.lines)+1))
        elif '-' in line_spec:
            s,e = map(int, line_spec.split('-'))
            nums = list(range(s, e+1))
        else:
            for p in line_spec.split(','):
                if p.strip():
                    nums.append(int(p.strip()))
        valid = [n for n in nums if 1 <= n <= len(self.lines)]
        if not valid:
            print("无效行号")
            return
        self.debug = True
        for n in valid:
            line = self.lines[n-1]
            print(f"\n🔍 调试信息（第{n}行）：")
            for c in line.chars:
                if c.char.strip():
                    print(f"  '{c.char}' -> '{c.pinyin}' [{c.source}]")
                else:
                    print(f"  (空格) -> '' [{c.source}]")
            img = Image.new('RGBA', (self.width, self.height), (30,30,30,255))
            overlay = self.render_line_image(line)
            img = Image.alpha_composite(img, overlay)
            out_path = os.path.join(self.script_dir, f"preview_line_{n}.png")
            img.save(out_path)
            print(f"✅ 已保存 {out_path}")
        self.debug = False

    def render_frames_parallel(self, use_qoi=True, num_workers=2):
        if not self.lines:
            return {}
        total_duration = self.lines[-1].end_time + 2
        total_frames = self.time_to_frame(total_duration) + 1
        if use_qoi and QOI_AVAILABLE:
            ext = 'qoi'
            print(f"\n⚡ 使用 QOI 格式")
        else:
            ext = 'png'
            print(f"\n📷 使用 PNG 格式")
        os.makedirs(self.frames_dir, exist_ok=True)
        print(f"渲染 {total_frames} 帧，{num_workers} 线程")
        print(f"分辨率: {self.width}x{self.height}")

        frame_to_line = {}
        empty_frames = []
        for f in range(total_frames):
            line = self.get_frame_line(f)
            if line:
                frame_to_line[f] = line.line_number
            else:
                empty_frames.append(f)
        print(f"  有字幕帧: {len(frame_to_line)}，空帧: {len(empty_frames)}")

        print("预渲染歌词模板...")
        unique_lines = set(frame_to_line.values())
        for line_num in unique_lines:
            if 1 <= line_num <= len(self.lines):
                self.render_line_image(self.lines[line_num-1])
        print(f"  预渲染完成，缓存 {len(self.line_cache)} 行")

        frames_to_render = list(frame_to_line.keys())
        completed = 0
        lock = threading.Lock()
        start_time = time.time()

        def save_qoi(img, path):
            np_img = np.array(img)
            qoi.write(path, np_img)

        def render_batch(batch):
            nonlocal completed
            for f in batch:
                line_num = frame_to_line[f]
                if 1 <= line_num <= len(self.lines):
                    img = self.line_cache.get(line_num)
                    if img is None:
                        img = self.render_line_image(self.lines[line_num-1])
                else:
                    img = self.render_empty_frame()
                path = os.path.join(self.frames_dir, f"frame_{f:08d}.{ext}")
                if ext == 'qoi':
                    save_qoi(img, path)
                else:
                    img.save(path, 'PNG', compress_level=1)
                with lock:
                    completed += 1
                    total = len(frames_to_render)
                    if completed % max(1, total // 100) == 0 or completed == total:
                        elapsed = time.time() - start_time
                        fps = completed / elapsed if elapsed > 0 else 0
                        percent = completed / total * 100
                        remaining_sec = (total - completed) / fps if fps > 0 else 0
                        remaining_str = f"{int(remaining_sec//60):02d}:{int(remaining_sec%60):02d}"
                        print(f"\r  进度 {completed}/{total} ({percent:.1f}%) | {fps:.1f} fps | 剩余 {remaining_str}", end='')

        batch_size = max(1, len(frames_to_render) // (num_workers * 4))
        batches = [frames_to_render[i:i+batch_size] for i in range(0, len(frames_to_render), batch_size)]
        with ThreadPoolExecutor(max_workers=num_workers) as ex:
            futures = [ex.submit(render_batch, b) for b in batches]
            for f in futures:
                f.result()
        print()

        print("\n生成空帧...")
        empty_img = self.render_empty_frame()
        empty_completed = 0
        empty_total = len(empty_frames)
        empty_start = time.time()
        for i, f in enumerate(empty_frames):
            path = os.path.join(self.frames_dir, f"frame_{f:08d}.{ext}")
            if ext == 'qoi':
                save_qoi(empty_img, path)
            else:
                empty_img.save(path, 'PNG')
            empty_completed += 1
            if empty_completed % max(1, empty_total // 100) == 0 or empty_completed == empty_total:
                elapsed = time.time() - empty_start
                fps = empty_completed / elapsed if elapsed > 0 else 0
                percent = empty_completed / empty_total * 100
                remaining_sec = (empty_total - empty_completed) / fps if fps > 0 else 0
                remaining_str = f"{int(remaining_sec//60):02d}:{int(remaining_sec%60):02d}"
                print(f"\r  空帧进度 {empty_completed}/{empty_total} ({percent:.1f}%) | {fps:.1f} fps | 剩余 {remaining_str}", end='')
        print()

        total_time = time.time() - start_time
        print(f"\n✅ 渲染完成，用时 {total_time:.1f} 秒")
        return {'total_frames': total_frames, 'fps': self.fps, 'frames_dir': self.frames_dir, 'ext': ext}

    def create_render_script(self, info):
        """生成功能完善的合成脚本（自动硬件编码、QOI序号模式）"""
        script_path = os.path.join(self.script_dir, "render_video.py")
        # 模板中所有需要保留的 { 必须双写为 {{，只有三个变量 frames_dir, fps, ext 需要单括号
        template = '''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动生成的视频合成脚本 - 支持 QOI 帧序列，自动硬件编码加速
用法: python render_video.py [--input INPUT] [--output OUTPUT]
"""

import subprocess
import os
import sys
import re
import time
import json
import argparse
from pathlib import Path

# ==================== 配置（自动从生成器获取） ====================
FRAMES_DIR = r"{frames_dir}"
FPS = {fps}
FRAME_EXT = "{ext}"
DEFAULT_INPUT_VIDEO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "input.mp4")
DEFAULT_OUTPUT_VIDEO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_subtitled.mp4")
# ================================================================

def detect_best_encoder():
    """自动检测最佳可用硬件编码器，按优先级: QSV > NVENC > AMF > VideoToolbox > libx264"""
    print("\\n🔍 检测最佳编码器...")
    try:
        r = subprocess.run(
            ["ffmpeg", "-encoders"],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        encoders = r.stdout

        # 优先级1: Intel QSV
        if "h264_qsv" in encoders:
            print("  ✅ Intel QSV (硬件编码) - 已选用")
            return "h264_qsv", ["-preset", "veryfast", "-global_quality", "18"]

        # 优先级2: NVIDIA NVENC
        if "h264_nvenc" in encoders:
            print("  ✅ NVIDIA NVENC (硬件编码) - 已选用")
            return "h264_nvenc", ["-preset", "p1", "-rc", "vbr_hq", "-b:v", "0", "-cq", "18"]

        # 优先级3: AMD AMF
        if "h264_amf" in encoders:
            print("  ✅ AMD AMF (硬件编码) - 已选用")
            return "h264_amf", ["-quality", "speed", "-qp_i", "18", "-qp_p", "18"]

        # 优先级4: Apple VideoToolbox
        if "h264_videotoolbox" in encoders:
            print("  ✅ Apple VideoToolbox (硬件编码) - 已选用")
            return "h264_videotoolbox", ["-quality", "speed", "-q:v", "60"]

    except Exception as e:
        print(f"  ⚠️ 检测失败: {{e}}")

    print("  ⚠️ 未找到硬件编码器，使用软件编码器 libx264")
    return "libx264", ["-preset", "fast", "-crf", "18"]

def count_frames(frames_dir, ext):
    """统计帧数量"""
    pattern = f"*.{{ext}}"
    frames = list(Path(frames_dir).glob(pattern))
    return len(frames)

def run_with_progress(cmd, total_frames, output_path):
    """运行FFmpeg命令并显示进度条"""
    print("\\n🎬 开始合成...")
    print(f"   输出: {{output_path}}\\n")
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        encoding='utf-8'
    )
    
    start_time = time.time()
    last_frame = 0
    bar_length = 40
    
    while True:
        line = process.stderr.readline()
        if not line and process.poll() is not None:
            break
        
        frame_match = re.search(r'frame=\\s*(\\d+)', line)
        if frame_match:
            current_frame = int(frame_match.group(1))
            if current_frame > last_frame:
                last_frame = current_frame
                progress = min(current_frame / total_frames * 100, 100) if total_frames else 0
                elapsed = time.time() - start_time
                
                if elapsed > 0 and current_frame > 0:
                    current_fps = current_frame / elapsed
                    if current_fps > 0 and total_frames > 0:
                        remaining_frames = total_frames - current_frame
                        remaining_time = remaining_frames / current_fps
                        
                        filled = int(bar_length * current_frame // total_frames)
                        bar = '█' * filled + '░' * (bar_length - filled)
                        
                        elapsed_str = time.strftime("%M:%S", time.gmtime(elapsed))
                        remaining_str = time.strftime("%M:%S", time.gmtime(remaining_time))
                        
                        print(f"\\r  [{{bar}}] {{progress:5.1f}}% | "
                              f"{{current_fps:5.1f}} fps | "
                              f"{{elapsed_str}} / {{remaining_str}}", end='', flush=True)
        
        # 捕获可能的错误
        if "error" in line.lower() and "frame" not in line.lower():
            print(f"\\n⚠️  FFmpeg: {{line.strip()}}")
    
    print()
    return process.wait()

def main():
    parser = argparse.ArgumentParser(description='QOI字幕合成器（自动硬件编码）')
    parser.add_argument('--input', default=DEFAULT_INPUT_VIDEO, help='输入视频文件')
    parser.add_argument('--output', default=DEFAULT_OUTPUT_VIDEO, help='输出视频文件')
    args = parser.parse_args()
    
    print("=" * 70)
    print("🎬 QOI 字幕合成器（自动硬件编码加速版）")
    print("=" * 70)
    print(f"📁 帧文件夹:  {{FRAMES_DIR}}")
    print(f"🖼️  帧格式:    {{FRAME_EXT.upper()}}")
    print(f"🎥 输入视频:  {{args.input}}")
    print(f"💾 输出视频:  {{args.output}}")
    print(f"🎯 帧率:      {{FPS}} fps")
    print("=" * 70)
    
    # 检查文件
    if not os.path.exists(FRAMES_DIR):
        print(f"❌ 错误: 帧文件夹不存在: {{FRAMES_DIR}}")
        return 1
    total_frames = count_frames(FRAMES_DIR, FRAME_EXT)
    if total_frames == 0:
        print(f"❌ 错误: 在 {{FRAMES_DIR}} 中找不到 .{{FRAME_EXT}} 文件")
        return 1
    if not os.path.exists(args.input):
        print(f"❌ 错误: 输入视频不存在: {{args.input}}")
        print("\\n📝 提示: 请将你的视频文件复制为 input.mp4 或使用 --input 指定路径")
        return 1
    
    print(f"📊 检测到 {{total_frames}} 帧")
    
    # 检测编码器
    encoder, encoder_opts = detect_best_encoder()
    
    # 构建命令（使用序号模式，避免 glob）
    frame_pattern = os.path.join(FRAMES_DIR, f"frame_%08d.{{FRAME_EXT}}")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", frame_pattern,
        "-i", args.input,
        "-filter_complex", "[0:v]format=rgba[sub];[1:v][sub]overlay=0:0:format=auto,format=yuv420p[v]",
        "-map", "[v]", "-map", "1:a",
        "-c:v", encoder, *encoder_opts,
        "-c:a", "copy",
        "-shortest",
        args.output
    ]
    
    # 显示命令预览
    cmd_preview = ' '.join(cmd[:8]) + " ... " + ' '.join(cmd[-8:])
    print(f"\\n📋 FFmpeg 命令:\\n   {{cmd_preview}}")
    
    print("\\n⏎ 按回车开始合成，或 Ctrl+C 取消...")
    try:
        input()
    except KeyboardInterrupt:
        print("\\n❌ 已取消")
        return 1
    
    return_code = run_with_progress(cmd, total_frames, args.output)
    
    if return_code == 0 and os.path.exists(args.output):
        output_size = os.path.getsize(args.output) / (1024 * 1024)
        print("\\n" + "=" * 70)
        print("✅ 合成成功！")
        print("=" * 70)
        print(f"   输出文件: {{args.output}}")
        print(f"   文件大小: {{output_size:.1f}} MB")
        # 显示视频时长
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", 
                 "-of", "default=noprint_wrappers=1:nokey=1", args.output],
                capture_output=True, text=True
            )
            if probe.returncode == 0 and probe.stdout.strip():
                duration = float(probe.stdout.strip())
                print(f"   视频时长: {{int(duration//60):02d}}:{{int(duration%60):02d}}")
        except:
            pass
        print("=" * 70)
        return 0
    else:
        print(f"\\n❌ 合成失败 (返回码: {{return_code}})")
        if encoder != 'libx264':
            print("\\n💡 提示: 硬件编码器可能不兼容，尝试软件编码：")
            print("   请修改脚本或安装完整的 ffmpeg 版本")
        return return_code

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\\n\\n❌ 用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\\n❌ 错误: {{e}}")
        sys.exit(1)
'''
        # 使用 .format() 安全替换三个变量
        content = template.format(
            frames_dir=info['frames_dir'],
            fps=info['fps'],
            ext=info['ext']
        )
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ 合成脚本已生成: {script_path}")


def main():
    print("="*60)
    print("🎬 粤语拼音字幕生成器 - 低配置优化版（ToJyutping + 手动标注 + 多音字优化）")
    print("="*60)
    print("针对 i3 + 8GB 内存优化")
    print("分辨率: 1280x720 | 字号: 64/32 | 屏幕正中央 | 支持手动标注[拼音] | 多音字自动优化")
    print("字符间距可调(base_char_spacing) | 多行智能对齐(左/中)")
    print("="*60)

    script_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        r = QOIRenderer(width=1280, height=720, fps=30)
    except Exception as e:
        print(f"初始化失败: {e}")
        return

    default_srt = os.path.join(script_dir, "subtitle.srt")
    if os.path.exists(default_srt):
        srt = input(f"字幕文件 (回车使用 {default_srt}): ").strip()
        if not srt:
            srt = default_srt
    else:
        srt = input("请输入 SRT 字幕文件路径: ").strip()

    if not os.path.exists(srt):
        print("文件不存在")
        return

    r.parse_srt_file(srt)

    preview = input("\n预览？(y/n, 默认y): ").strip().lower()
    if preview != 'n':
        lines = input("行号 (如 1,3,5 或 1-10 或 all): ").strip() or "1"
        r.preview_lines(lines)

    go = input("\n渲染全部帧？(y/n, 默认y): ").strip().lower()
    if go != 'n':
        use_qoi = QOI_AVAILABLE and input("使用 QOI 加速？(y/n, 默认y): ").strip().lower() != 'n'
        import multiprocessing
        cpu = multiprocessing.cpu_count()
        default_threads = max(1, cpu // 2)
        threads_input = input(f"线程数 (默认 {default_threads}，可输入1-{cpu}): ").strip()
        if threads_input:
            num_workers = int(threads_input)
        else:
            num_workers = default_threads
        num_workers = max(1, min(num_workers, cpu))
        info = r.render_frames_parallel(use_qoi=use_qoi, num_workers=num_workers)
        r.create_render_script(info)
        print("\n" + "="*60)
        print("✅ 完成！下一步：")
        print(f"1. 把视频文件命名为 input.mp4 放在: {script_dir}")
        print(f"2. 运行: python render_video.py")
        print("="*60)


if __name__ == "__main__":
    main()
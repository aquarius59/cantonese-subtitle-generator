"""
粤语拼音字幕生成器 - 极速版 v42
三层回退：硬件解码+QSV → 仅QSV → libx264
用户可调编码线程数（1-8，默认4）
"""

from PIL import Image, ImageDraw, ImageFont
import os
os.system('chcp 65001 > nul')
import re
import sys
import math
import time
import subprocess
import threading
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

try:
    import ToJyutping
    TOJYUTPING_AVAILABLE = True
except ImportError:
    TOJYUTPING_AVAILABLE = False
    print("❌ 请先安装 ToJyutping：pip install ToJyutping")
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
    original_text: str = ""


class CantoneseDictionary:
    OVERRIDE = {'著': ('zyu3', '3'), '宁': ('ning4', '4'), '价': ('gaa3', '3')}
             
    POLYPHONE_RULES = {
        '行': {
            'haang4': {'行走', '步行', '行路', '行街', '行山', '行开'},
            'hong4':  {'银行', '行业', '行情', '行家', '行规', '行内'},
        },
        '长': {
            'coeng4': {'长短', '长江', '长度', '长城', '长途'},
            'zoeng2': {'长大', '成长', '家长', '班长', '校长'},
        },
        '乐': {
            'lok6': {'快乐', '欢乐', '乐园', '乐天', '乐土'},
            'ngok6': {'音乐', '乐器', '乐队', '乐谱'},
        },
        '重': {
            'cung5': {'重担'},
            'zung6': {'重点', '重用', '重视', '沉重'},
            'cung4': {'重复','重叠'},
        },
        '好': {
            'hou2': {'好人', '好坏', '很好', '好食', '好靓'},
            'hou3': {'爱好', '好客', '好学', '好胜'},
        },
        '只': {
            'zek3': {'一只', '两只', '船只', '只只'},
            'zi2':  {'只有', '只是', '只要', '只可'},
        },
        '的': {
            'dik1': {'的确', '目的', '中的', '标的'},
            'di1':  {'我的', '你的', '他的', '好的'},
        },
        '着': {
            'zoek6': {'穿着', '看着', '听着', '走着'},
            'zoek3': {'着火', '着凉', '着急', '着迷'},
        },
        '分': {
            'fan1': {'分开', '分别', '分钟', '分数'},
            'fan6': {'部分', '成分', '身份', '本分'},
        },
        '间': {
            'gaan1': {'房间', '时间', '空间', '人间'},
            'gaan3': {'间隔', '离间', '间谍', '间中'},
        },
        '中': {
            'zung1': {'中国', '中心', '中间', '空中'},
            'zung3': {'中奖', '中意', '中弹', '中选'},
        },
        '为': {
            'wai4': {'因为', '以为', '行为', '认为'},
            'wai6': {'为了', '为何', '为人民'},
        },
        '相': {
            'soeng1': {'相信', '相同', '相识', '相处'},
            'soeng3': {'相片', '相貌', '相册', '面相'},
        },
        '教': {
            'gaau3': {'教学', '教室', '教师', '教育'},
            'gaau1': {'教课', '教书', '教人'},
        },
        '降': {
            'gong3': {'下降', '降落', '降低', '降级'},
            'hong4': {'投降', '降服', '降顺'},
        },
        '调': {
            'diu6': {'调动', '调换', '调查', '调整'},
            'tiu4': {'调和', '调皮', '空调', '调味'},
        },
        '传': {
            'cyun4': {'传播', '传送', '传统', '传奇'},
            'zyun6': {'传记', '自传', '经传'},
        },
        '转': {
            'zyun3': {'转变', '转换', '转向', '转身'},
            'zyun2': {'转动', '旋转', '打转'},
        },
        '背': {
            'bui3': {'背后', '背景', '背叛', '背心'},
            'bui1': {'背负', '背债', '背包'},
        },
        '便': {
            'bin6': {'方便', '便利', '便宜', '便当'},
            'pin4': {'便宜'},
        },
        '听': {
            'teng1': {'听到', '听紧', '听日', '听歌'},
            'ting1': {'听懂', '听信'},
        },
        '里': {
            'leoi5': {'里面', '哪里', '风雨里', '内里'},
            'lei5':  {'公里', '千里', '万里', '里海'},
        },
        '松': {
            'sung1': {'松绑', '松紧', '松人'},
            'cung4':  {'松树', '松林', '松柏'},
        },
    }

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


def parse_srt(content: str) -> List[LyricLine]:
    lines = []
    entries = re.split(r'\n\s*\n', content.strip())
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
            
            def to_sec(t):
                t = t.replace(',', '.')
                p = t.split(':')
                return int(p[0])*3600 + int(p[1])*60 + float(p[2])
            
            start = to_sec(match.group(1))
            end = to_sec(match.group(2))
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
    return lines


def format_time(seconds: float) -> str:
    if seconds < 0:
        return "--:--"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class LineLayout:
    def __init__(self):
        self.positions = []
        self.bg_rects = []


class UltraFastRenderer:
    def __init__(self, width=1280, height=720, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        self.lines: List[LyricLine] = []
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.char_font_size = 64
        self.pinyin_font_size = 32
        self.bg_color = (0, 0, 0, 102)
        
        self.min_char_spacing = 16
        self.line_padding = 32
        self.screen_margin = 50
        self.max_line_width = width - 2 * self.screen_margin
        
        self.line_height = self.pinyin_font_size + self.char_font_size + 36
        
        self.max_lines = 2
        self.long_syllable_threshold = 4
        self.extra_spacing_long = 35
        
        self.center_x_offset = 0
        self.min_align_ratio = 0.5
        
        self.tone_colors = {
            '1': (255, 80, 80), '2': (255, 180, 80), '3': (80, 255, 80),
            '4': (80, 160, 255), '5': (255, 120, 200), '6': (200, 80, 255),
        }
        
        self._load_fonts()
        self.layout_cache: Dict[int, LineLayout] = {}
        self.line_render_cache: Dict[int, np.ndarray] = {}
        
        self._get_font_metrics()
        self.threads = 4  # 默认线程数
        
    def set_threads(self, threads: int):
        """设置编码线程数（1~8）"""
        self.threads = max(1, min(threads, 8))

    def _get_font_metrics(self):
        temp_img = Image.new('RGB', (1, 1))
        temp_draw = ImageDraw.Draw(temp_img)
        try:
            bbox_high = temp_draw.textbbox((0, 0), 'A', font=self.pinyin_font)
            bbox_low = temp_draw.textbbox((0, 0), 'g', font=self.pinyin_font)
            self.pinyin_ascent = -bbox_high[1]
            self.pinyin_descent = bbox_low[3]
            self.pinyin_height = self.pinyin_ascent + self.pinyin_descent
        except:
            self.pinyin_ascent = self.pinyin_font_size * 0.75
            self.pinyin_descent = self.pinyin_font_size * 0.25
            self.pinyin_height = self.pinyin_font_size
            
        try:
            bbox_char = temp_draw.textbbox((0, 0), '中', font=self.char_font)
            self.char_ascent = -bbox_char[1]
            self.char_descent = bbox_char[3]
            self.char_height = self.char_ascent + self.char_descent
        except:
            self.char_ascent = self.char_font_size * 0.8
            self.char_descent = self.char_font_size * 0.2
            self.char_height = self.char_font_size
            
    def _load_fonts(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        char_font_path = os.path.join(script_dir, "SourceHanSansHWSC-Bold.otf")
        pinyin_font_path = os.path.join(script_dir, "SourceHanSansHWSC-Bold.otf")
        
        def load_font(path, size):
            if not os.path.exists(path):
                raise FileNotFoundError(f"❌ 字体文件不存在: {path}")
            try:
                return ImageFont.truetype(path, size)
            except Exception as e:
                raise RuntimeError(f"❌ 字体加载失败 {path}: {e}")
        
        self.char_font = load_font(char_font_path, self.char_font_size)
        self.pinyin_font = load_font(pinyin_font_path, self.pinyin_font_size)
        
        char_name = self.char_font.getname() if hasattr(self.char_font, 'getname') else ('default', '')
        py_name = self.pinyin_font.getname() if hasattr(self.pinyin_font, 'getname') else ('default', '')
        print(f"📝 汉字字体: {char_name[0]}")
        print(f"📝 拼音字体: {py_name[0]}")
        
    def _get_text_width(self, text: str, font) -> int:
        if not text:
            return 0
        if hasattr(font, 'getlength'):
            return int(font.getlength(text))
        temp_img = Image.new('RGB', (1, 1))
        temp_draw = ImageDraw.Draw(temp_img)
        bbox = temp_draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    
    def _calculate_char_widths(self, chars: List[LyricChar]) -> List[int]:
        widths = []
        for c in chars:
            char_w = self._get_text_width(c.char, self.char_font)
            char_w = max(char_w, self.char_font_size * 0.5)
            widths.append(char_w)
        return widths
        
    def _split_into_lines(self, chars: List[LyricChar]) -> List[List[LyricChar]]:
        if not chars:
            return []
        
        char_widths = self._calculate_char_widths(chars)
        lines = []
        current_line = []
        current_width = 0
        
        for i, c in enumerate(chars):
            char_w = char_widths[i]
            extra = 0
            if current_line:
                prev_idx = len(current_line) - 1
                if chars[prev_idx].pinyin and len(chars[prev_idx].pinyin) >= self.long_syllable_threshold:
                    extra = self.extra_spacing_long
                elif c.pinyin and len(c.pinyin) >= self.long_syllable_threshold:
                    extra = self.extra_spacing_long
                else:
                    extra = self.min_char_spacing
            
            new_width = current_width + char_w + extra
            
            if current_line and new_width > self.max_line_width:
                lines.append(current_line)
                current_line = [c]
                current_width = char_w
            else:
                current_line.append(c)
                current_width = new_width
        
        if current_line:
            lines.append(current_line)
        
        if len(lines) > self.max_lines:
            overflow = []
            for line in lines[self.max_lines:]:
                overflow.extend(line)
            lines = lines[:self.max_lines]
            if overflow:
                lines[-1].extend(overflow)
        
        return lines
        
    def _calculate_layout(self, line: LyricLine) -> Optional[LineLayout]:
        if line.line_number in self.layout_cache:
            return self.layout_cache[line.line_number]

        chars = [c for c in line.chars if c.char.strip()]
        if not chars:
            return None

        char_lines = self._split_into_lines(chars)
        
        layout = LineLayout()
        layout.line_count = len(char_lines)
        
        total_height = len(char_lines) * self.line_height
        start_y = (self.height - total_height) // 2
        start_y = max(20, start_y)
        
        line_start_xs = []
        
        for line_idx, line_chars in enumerate(char_lines):
            cur_y = start_y + line_idx * self.line_height
            bg_top = cur_y
            bg_bottom = cur_y + self.line_height
            
            char_widths = self._calculate_char_widths(line_chars)
            total_line_width = sum(char_widths)
            for i in range(len(line_chars) - 1):
                if line_chars[i].pinyin and len(line_chars[i].pinyin) >= self.long_syllable_threshold:
                    total_line_width += self.extra_spacing_long
                elif line_chars[i+1].pinyin and len(line_chars[i+1].pinyin) >= self.long_syllable_threshold:
                    total_line_width += self.extra_spacing_long
                else:
                    total_line_width += self.min_char_spacing
            
            if line_idx == 0:
                start_x = (self.width - total_line_width) // 2 + self.center_x_offset
            else:
                prev_count = len(char_lines[line_idx - 1])
                curr_count = len(line_chars)
                if curr_count < prev_count * self.min_align_ratio:
                    start_x = line_start_xs[line_idx - 1]
                else:
                    start_x = (self.width - total_line_width) // 2 + self.center_x_offset
            
            start_x = max(self.screen_margin, min(start_x, self.width - total_line_width - self.screen_margin))
            line_start_xs.append(start_x)
            
            block_height = self.pinyin_height + 4 + self.char_height
            block_top = bg_top + (self.line_height - block_height) // 2
            pinyin_baseline = block_top + self.pinyin_ascent
            char_top = block_top + self.pinyin_height + 4
            char_baseline = char_top + self.char_ascent
            
            cur_x = start_x
            for i, c in enumerate(line_chars):
                char_w = char_widths[i]
                char_x = cur_x
                
                if c.pinyin:
                    pinyin_w = self._get_text_width(c.pinyin, self.pinyin_font)
                    pinyin_x = cur_x + (char_w - pinyin_w) // 2
                else:
                    pinyin_x = None
                
                layout.positions.append({
                    'char_x': char_x,
                    'char_baseline': char_baseline,
                    'char': c.char,
                    'pinyin_x': pinyin_x,
                    'pinyin_baseline': pinyin_baseline,
                    'pinyin': c.pinyin,
                    'tone': c.tone,
                    'char_width': char_w
                })
                
                cur_x += char_w
                if i < len(line_chars) - 1:
                    if c.pinyin and len(c.pinyin) >= self.long_syllable_threshold:
                        cur_x += self.extra_spacing_long
                    elif line_chars[i+1].pinyin and len(line_chars[i+1].pinyin) >= self.long_syllable_threshold:
                        cur_x += self.extra_spacing_long
                    else:
                        cur_x += self.min_char_spacing
            
            first_pos = layout.positions[-len(line_chars)]
            last_pos = layout.positions[-1]
            last_char_w = last_pos['char_width']
            
            bg_left = first_pos['char_x'] - self.line_padding
            bg_right = last_pos['char_x'] + last_char_w + self.line_padding
            bg_left = max(0, bg_left)
            bg_right = min(self.width, bg_right)
            
            layout.bg_rects.append((
                bg_left,
                bg_top,
                bg_right,
                bg_bottom
            ))

        self.layout_cache[line.line_number] = layout
        return layout
        
    def _prebuild_cache(self):
        print("预渲染歌词行...")
        total_lines = len(self.lines)
        start_time = time.time()
        
        for idx, line in enumerate(self.lines, start=1):
            self._render_line_to_numpy(line)
            
            if idx % 10 == 0 or idx == total_lines:
                elapsed = time.time() - start_time
                speed = idx / elapsed if elapsed > 0 else 0
                remaining = (total_lines - idx) / speed if speed > 0 else 0
                percent = idx / total_lines * 100
                bar_len = 30
                filled = int(bar_len * idx / total_lines)
                bar = '█' * filled + '░' * (bar_len - filled)
                clear_line = ' ' * 120
                progress_str = f"[{bar}] {percent:5.1f}% │ {idx:>4}/{total_lines:<4} │ ⏱️ {format_time(elapsed)} │ ⏳ {format_time(remaining)}"
                print(f"\r{clear_line}\r{progress_str}", end='', flush=True)
        
        print(f"\n✅ {total_lines} 行缓存完成")
        
    def _render_line_to_numpy(self, line: LyricLine) -> np.ndarray:
        if line.line_number in self.line_render_cache:
            return self.line_render_cache[line.line_number]
        
        layout = self._calculate_layout(line)
        if not layout:
            arr = np.zeros((self.height, self.width, 4), dtype=np.uint8)
            self.line_render_cache[line.line_number] = arr
            return arr
        
        img = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        for rect in layout.bg_rects:
            draw.rectangle(rect, fill=self.bg_color)
        
        for pos in layout.positions:
            if pos['pinyin'] and pos['pinyin_x'] is not None:
                color = self.tone_colors.get(pos['tone'], (255, 255, 255))
                for dx, dy in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                    draw.text((pos['pinyin_x']+dx, pos['pinyin_baseline']+dy),
                              pos['pinyin'], font=self.pinyin_font, fill=(0,0,0))
                draw.text((pos['pinyin_x'], pos['pinyin_baseline']),
                          pos['pinyin'], font=self.pinyin_font, fill=color)
            
            for dx, dy in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                draw.text((pos['char_x']+dx, pos['char_baseline']+dy),
                          pos['char'], font=self.char_font, fill=(0,0,0))
            draw.text((pos['char_x'], pos['char_baseline']),
                      pos['char'], font=self.char_font, fill=(255,255,255))
        
        arr = np.array(img)
        self.line_render_cache[line.line_number] = arr
        return arr
        
    def time_to_frame(self, t: float) -> int:
        return int(math.floor(t * self.fps))
        
    def get_line_at_frame(self, frame: int) -> Optional[LyricLine]:
        t = frame / self.fps
        tol = 1.0 / self.fps / 2
        for line in self.lines:
            if line.start_time - tol <= t < line.end_time + tol:
                return line
        return None

    def _is_encoder_available(self, encoder_name: str) -> bool:
        """检测 ffmpeg 是否支持指定的编码器（保留备用）"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-h', f'encoder={encoder_name}'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
        
    def preview_lines(self, line_spec: str):
        print("\n预览模式")
        nums = []
        if line_spec.lower() == 'all':
            nums = list(range(1, len(self.lines)+1))
        elif '-' in line_spec:
            s, e = map(int, line_spec.split('-'))
            nums = list(range(s, e+1))
        else:
            for p in line_spec.split(','):
                if p.strip():
                    nums.append(int(p.strip()))
        
        valid = [n for n in nums if 1 <= n <= len(self.lines)]
        if not valid:
            print("无效行号")
            return
        
        for n in valid:
            line = self.lines[n-1]
            print(f"\n🔍 调试信息（第{n}行）：")
            for c in line.chars:
                if c.char.strip():
                    print(f"  '{c.char}' -> '{c.pinyin}' [{c.source}]")
                else:
                    print(f"  (空格) -> '' [{c.source}]")
            
            img = Image.new('RGBA', (self.width, self.height), (30, 30, 30, 255))
            layout = self._calculate_layout(line)
            if layout:
                draw = ImageDraw.Draw(img)
                for rect in layout.bg_rects:
                    draw.rectangle(rect, fill=self.bg_color)
                for pos in layout.positions:
                    if pos['pinyin'] and pos['pinyin_x'] is not None:
                        color = self.tone_colors.get(pos['tone'], (255, 255, 255))
                        for dx, dy in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                            draw.text((pos['pinyin_x']+dx, pos['pinyin_baseline']+dy),
                                      pos['pinyin'], font=self.pinyin_font, fill=(0,0,0))
                        draw.text((pos['pinyin_x'], pos['pinyin_baseline']),
                                  pos['pinyin'], font=self.pinyin_font, fill=color)
                    for dx, dy in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                        draw.text((pos['char_x']+dx, pos['char_baseline']+dy),
                                  pos['char'], font=self.char_font, fill=(0,0,0))
                    draw.text((pos['char_x'], pos['char_baseline']),
                              pos['char'], font=self.char_font, fill=(255,255,255))
            
            out_path = os.path.join(self.script_dir, f"preview_line_{n}.png")
            img.save(out_path)
            print(f"✅ 已保存 {out_path}")
        
    def _print_progress(self, current: int, total: int, elapsed: float, fps: float):
        percent = current / total * 100 if total > 0 else 0
        bar_width = 30
        filled = int(bar_width * current // total)
        bar = '█' * filled + '░' * (bar_width - filled)
        remaining = (total - current) / fps if fps > 0 else 0
        clear_line = ' ' * 120
        progress_str = f"│{bar}│ {percent:5.1f}% │ {current:>6}/{total:<6} │ {fps:>6.1f} fps │ ⏱️ {format_time(elapsed)} │ ⏳ {format_time(remaining)}"
        print(f"\r{clear_line}\r{progress_str}", end='', flush=True)
        
    def render_streaming(self, input_video: str, output_video: str):
        if not self.lines:
            print("❌ 无歌词")
            return False
        
        if not os.path.exists(input_video):
            print(f"❌ 找不到: {input_video}")
            return False
        
        self._prebuild_cache()
        
        total_duration = self.lines[-1].end_time + 2
        total_frames = self.time_to_frame(total_duration) + 1
        
        # 三层回退策略定义
        strategies = [
            {
                "name": "硬件解码(dxva2) + QSV编码",
                "hwaccel": ["-hwaccel", "dxva2"],
                "encoder": "h264_qsv",
                "preset": ["-preset", "veryfast"],
                "quality": ["-global_quality", "23"],
            },
            {
                "name": "QSV编码（无硬件解码）",
                "hwaccel": [],
                "encoder": "h264_qsv",
                "preset": ["-preset", "veryfast"],
                "quality": ["-global_quality", "23"],
            },
            {
                "name": "libx264软件编码（原始回退）",
                "hwaccel": [],
                "encoder": "libx264",
                "preset": ["-preset", "ultrafast"],
                "quality": ["-crf", "23"],
            }
        ]
        
        # 尝试每种策略
        for idx, strategy in enumerate(strategies):
            print(f"\n{'='*70}")
            print(f"🎬 尝试渲染策略 [{idx+1}/{len(strategies)}]：{strategy['name']}")
            print(f"{'='*70}")
            print(f"  分辨率:    {self.width}x{self.height}")
            print(f"  帧率:      {self.fps} fps")
            print(f"  总帧数:    {total_frames:,}")
            print(f"  预计时长:  {format_time(total_frames / self.fps)}")
            print(f"  编码线程:  {self.threads}")
            print(f"  输入视频:  {input_video}")
            print(f"  输出视频:  {output_video}")
            
            cmd = [
                'ffmpeg', '-y',
                *strategy["hwaccel"],
                '-f', 'rawvideo',
                '-vcodec', 'rawvideo',
                '-s', f'{self.width}x{self.height}',
                '-pix_fmt', 'rgba',
                '-r', str(self.fps),
                '-thread_queue_size', '512',
                '-i', '-',
                '-i', input_video,
                '-filter_complex', '[0:v]format=rgba[sub];[1:v][sub]overlay=0:0:format=auto[outv]',
                '-map', '[outv]',
                '-map', '1:a',
                '-c:v', strategy["encoder"],
                *strategy["preset"],
                *strategy["quality"],
                '-threads', str(self.threads),
                '-c:a', 'copy',
                '-shortest',
                output_video
            ]
            
            # 可选：显示完整命令（调试用）
            # print(f"  命令: {' '.join(cmd)}")
            print(f"{'='*70}\n")
            
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            
            ffmpeg_errors = []
            def read_stderr():
                try:
                    while True:
                        line = process.stderr.readline()
                        if not line:
                            break
                        ffmpeg_errors.append(line.decode('utf-8', errors='ignore'))
                except:
                    pass
            
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stderr_thread.start()
            
            empty_frame = np.zeros((self.height, self.width, 4), dtype=np.uint8)
            
            start_time = time.time()
            last_report = start_time
            frame_times = []
            strategy_success = False
            
            try:
                for f in range(total_frames):
                    frame_start = time.time()
                    line = self.get_line_at_frame(f)
                    if line and line.line_number in self.line_render_cache:
                        frame_arr = self.line_render_cache[line.line_number]
                    else:
                        frame_arr = empty_frame
                    
                    try:
                        process.stdin.write(frame_arr.tobytes())
                        process.stdin.flush()
                    except BrokenPipeError:
                        print(f"\n\n❌ FFmpeg 管道断开 (帧 {f})")
                        if ffmpeg_errors:
                            print("FFmpeg 错误:")
                            print(''.join(ffmpeg_errors[-10:]))
                        break
                    
                    frame_time = time.time() - frame_start
                    frame_times.append(frame_time)
                    if len(frame_times) > 30:
                        frame_times.pop(0)
                    
                    avg_time = sum(frame_times) / len(frame_times)
                    current_fps = 1.0 / avg_time if avg_time > 0 else 0
                    
                    now = time.time()
                    if now - last_report >= 0.3 or f % 100 == 0 or f == total_frames - 1:
                        elapsed = now - start_time
                        self._print_progress(f + 1, total_frames, elapsed, current_fps)
                        last_report = now
                else:
                    # 正常完成所有帧
                    print()
                    print(f"\n✅ 所有帧已发送，等待编码完成...")
                    process.stdin.close()
                    
                    while process.poll() is None:
                        time.sleep(0.5)
                        print(".", end='', flush=True)
                    print()
                    
                    total_elapsed = time.time() - start_time
                    
                    if process.returncode == 0:
                        print(f"\n{'='*70}")
                        print(f"🎉 渲染成功！ (策略: {strategy['name']})")
                        print(f"{'='*70}")
                        print(f"  总用时:     {format_time(total_elapsed)}")
                        print(f"  平均速度:   {total_frames/total_elapsed:.1f} fps")
                        print(f"  输出文件:   {output_video}")
                        if os.path.exists(output_video):
                            size_mb = os.path.getsize(output_video) / (1024 * 1024)
                            print(f"  文件大小:   {size_mb:.1f} MB")
                        print(f"{'='*70}")
                        strategy_success = True
                    else:
                        print(f"\n❌ FFmpeg 失败 (代码: {process.returncode})")
                        if ffmpeg_errors:
                            print("错误日志:")
                            print(''.join(ffmpeg_errors[-20:]))
                        strategy_success = False
                
                if strategy_success:
                    return True
                    
            except KeyboardInterrupt:
                print("\n\n⚠️ 用户中断")
                process.kill()
                return False
            except Exception as e:
                print(f"\n\n❌ 策略执行异常: {e}")
                process.kill()
                continue  # 尝试下一策略
        
        # 所有策略均失败
        print("\n❌ 所有渲染策略均失败，请检查 ffmpeg 环境或输入文件。")
        return False


def main():
    print("="*70)
    print("🚀 粤语拼音字幕生成器 - 极速版 v42（三层加速回退 + 可调线程数）")
    print("="*70)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    srt_path = os.path.join(script_dir, "subtitle.srt")
    input_video = os.path.join(script_dir, "input.mp4")
    output_video = os.path.join(script_dir, "output.mp4")
    
    user_srt = input(f"字幕文件 [默认: {srt_path}]: ").strip()
    if user_srt:
        srt_path = user_srt
    
    if not os.path.exists(srt_path):
        print("❌ 字幕文件不存在")
        return
    
    with open(srt_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()
    
    lines = parse_srt(content)
    print(f"✅ 解析 {len(lines)} 行歌词")
    
    if not lines:
        return
    
    user_input = input(f"输入视频 [默认: {input_video}]: ").strip()
    if user_input:
        input_video = user_input
    
    user_output = input(f"输出视频 [默认: {output_video}]: ").strip()
    if user_output:
        output_video = user_output
    
    if not os.path.exists(input_video):
        print(f"❌ 输入视频不存在: {input_video}")
        return
    
    r = UltraFastRenderer(width=1280, height=720, fps=30)
    r.lines = lines

    # 线程数选择
    default_threads = min(4, os.cpu_count() or 4)
    thread_input = input(f"编码线程数 (1-8, 默认{default_threads}): ").strip()
    if thread_input:
        try:
            threads = int(thread_input)
            threads = max(1, min(threads, 8))
        except ValueError:
            threads = default_threads
    else:
        threads = default_threads
    r.set_threads(threads)

    print("\n💡 参数说明：")
    print("   - 动态字符宽度，彻底解决重叠问题")
    print("   - 最小字符间距：16px，屏幕边距：50px")
    print("   - 多行对齐：字数过少时左对齐，否则居中")
    print("   - 编码加速：硬件解码+QSV → QSV → libx264 自动回退")
    
    preview = input("\n预览？(y/n, 默认n): ").strip().lower()
    if preview == 'y':
        line_spec = input("行号 (如 1,3,5 或 1-10 或 all): ").strip() or "1"
        r.preview_lines(line_spec)
    
    go = input("\n开始渲染？(y/n, 默认y): ").strip().lower()
    if go != 'n':
        success = r.render_streaming(input_video, output_video)
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()
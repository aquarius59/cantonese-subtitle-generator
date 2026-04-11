"""
粤语拼音字幕生成器 - 极速版 v11
修复拼音/汉字显示不全，动态字符宽度，灵活字体配置
"""

from PIL import Image, ImageDraw, ImageFont
import os
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
    print("❌ pip install ToJyutping")
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
    OVERRIDE = {'著': ('zyu3', '3'), '宁': ('ning4', '4')}
             
    POLYPHONE_RULES = {
        '行': {'haang4': ['行走', '步行', '行路', '行街', '行山', '行开'], 'hong4': ['银行', '行业', '行情', '行家', '行规', '行内']},
        '长': {'coeng4': ['长短', '长江', '长度', '长城', '长途'], 'zoeng2': ['长大', '成长', '家长', '班长', '校长']},
        '乐': {'lok6': ['快乐', '欢乐', '乐园', '乐天', '乐土'], 'ngok6': ['音乐', '乐器', '乐队', '乐谱']},
        '重': {'cung5': ['重要', '重点', '重大', '重用', '重担','重复',], 'zung6': [ '重叠', '重新', '双重', '沉重']},
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
        self.positions = []      # 每个字符的详细位置信息
        self.bg_rects = []       # 每行背景矩形
        self.line_count = 1
        self.line_alignments = []


class UltraFastRenderer:
    def __init__(self, width=1280, height=720, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        self.lines: List[LyricLine] = []
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.char_font_size = 64      # 基准字号，实际宽度动态计算
        self.pinyin_font_size = 32
        self.bg_color = (0, 0, 0, 102)
        self.base_char_spacing = 20   # 字符间额外间距
        self.line_padding = 28        # 背景左右内边距
        self.max_line_width = int(width * 0.85)
        # 行高 = 拼音行高 + 汉字行高 + 上下内边距
        self.line_height = self.pinyin_font_size + self.char_font_size + 24
        self.max_lines = 2
        self.long_syllable_threshold = 4
        self.extra_spacing_long = 10
        self.min_align_ratio = 0.5
        
        self.tone_colors = {
            '1': (255, 80, 80), '2': (255, 180, 80), '3': (80, 255, 80),
            '4': (80, 160, 255), '5': (255, 120, 200), '6': (200, 80, 255),
        }
        
        self._load_fonts()
        self.char_cache: Dict[Tuple[str, str, str], Tuple[Image.Image, int, int]] = {}  # 存储 (img, width, height)
        self.layout_cache: Dict[int, LineLayout] = {}
        self.line_render_cache: Dict[int, np.ndarray] = {}
        
    def _load_fonts(self):
        """加载字体 - 灵活配置区"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # ========== 字体配置修改处 ==========
        #
        # 【默认配置】拼音和汉字都用同一个字体：
        char_font_path = os.path.join(script_dir, "SourceHanSansHWSC-Bold.otf")
        pinyin_font_path = os.path.join(script_dir, "SourceHanSansHWSC-Bold.otf")
        
        # 【可选配置】拼音和汉字用不同字体：
        # 去掉下面两行注释（删除 # 号）即可启用：
        # char_font_path = os.path.join(script_dir, "SourceHanSansHWSC-Bold.otf")   # 汉字字体
        # pinyin_font_path = os.path.join(script_dir, "LXGWWenKaiMono-Bold.ttf")    # 拼音字体
        # ========== 字体配置修改处结束 ==========
        
        def load_font(path, size):
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception as e:
                    print(f"⚠️ 字体加载失败 {path}: {e}")
            return ImageFont.load_default()
        
        self.char_font = load_font(char_font_path, self.char_font_size)
        self.pinyin_font = load_font(pinyin_font_path, self.pinyin_font_size)
        
        char_name = self.char_font.getname() if hasattr(self.char_font, 'getname') else ('default', '')
        py_name = self.pinyin_font.getname() if hasattr(self.pinyin_font, 'getname') else ('default', '')
        print(f"📝 汉字字体: {char_name[0]}")
        print(f"📝 拼音字体: {py_name[0]}")
        if char_font_path == pinyin_font_path:
            print("   (拼音和汉字使用相同字体)")
        else:
            print("   (拼音和汉字使用不同字体)")
        
    def _get_text_width(self, text: str, font) -> int:
        """获取文本实际渲染宽度"""
        if not text:
            return 0
        # 使用 getbbox 或 textlength 提高精度
        if hasattr(font, 'getlength'):
            return int(font.getlength(text))
        temp_img = Image.new('RGB', (1, 1))
        temp_draw = ImageDraw.Draw(temp_img)
        bbox = temp_draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
        
    def _split_into_lines(self, chars: List[LyricChar]) -> List[List[LyricChar]]:
        """换行逻辑：基于动态字符宽度重新实现，保持原意但更准确"""
        if not chars:
            return []
        # 计算每个字符的宽度（汉字+间距）
        char_widths = [self._get_text_width(c.char, self.char_font) for c in chars]
        # 总宽度（含固定间距）
        total_width = sum(char_widths) + (len(chars)-1) * self.base_char_spacing
        if total_width <= self.max_line_width:
            return [chars]
        # 估算每行最大字符数（基于平均宽度）
        avg_width = total_width / len(chars)
        max_per_line = max(1, int((self.max_line_width + self.base_char_spacing) / (avg_width + self.base_char_spacing)))
        lines = [chars[i:i+max_per_line] for i in range(0, len(chars), max_per_line)]
        if len(lines) > self.max_lines:
            lines = lines[:self.max_lines]
        return lines
        
    def _calculate_layout(self, line: LyricLine) -> Optional[LineLayout]:
        """动态宽度布局计算（修复版）"""
        if line.line_number in self.layout_cache:
            return self.layout_cache[line.line_number]

        chars = [c for c in line.chars if c.char.strip()]
        if not chars:
            return None

        char_lines = self._split_into_lines(chars)
        
        # 计算每行数据：字符实际宽度、拼音宽度、额外间距
        line_data = []
        for line_chars in char_lines:
            char_widths = [self._get_text_width(c.char, self.char_font) for c in line_chars]
            pinyin_widths = []
            pinyin_lens = []
            for c in line_chars:
                if c.pinyin:
                    w = self._get_text_width(c.pinyin, self.pinyin_font)
                    pinyin_widths.append(w)
                    pinyin_lens.append(len(c.pinyin))
                else:
                    pinyin_widths.append(0)
                    pinyin_lens.append(0)

            # 长音节额外间距
            extra = [0] * (len(line_chars)-1)
            for i in range(len(line_chars)-1):
                if pinyin_lens[i] >= self.long_syllable_threshold or pinyin_lens[i+1] >= self.long_syllable_threshold:
                    extra[i] = self.extra_spacing_long

            # 计算行宽
            line_width = sum(char_widths)
            if extra:
                line_width += sum(self.base_char_spacing + e for e in extra)
            elif len(line_chars) > 1:
                line_width += (len(line_chars)-1) * self.base_char_spacing

            if line_width > self.max_line_width:
                line_width = self.max_line_width

            line_data.append({
                'chars': line_chars,
                'width': line_width,
                'char_widths': char_widths,
                'pinyin_widths': pinyin_widths,
                'extra': extra,
                'char_count': len(line_chars),
            })

        # 计算每行起始X坐标（居中/左对齐）
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

        # 垂直居中
        total_height = len(char_lines) * self.line_height
        start_y = (self.height - total_height) // 2
        start_y = max(10, start_y)
        cur_y = start_y

        layout = LineLayout()
        layout.line_count = len(char_lines)
        layout.line_alignments = ['center' if i == 0 or line_data[i]['char_count'] >= line_data[i-1]['char_count'] * self.min_align_ratio else 'left' for i in range(len(line_data))]

        for idx, data in enumerate(line_data):
            line_chars = data['chars']
            char_widths = data['char_widths']
            pinyin_widths = data['pinyin_widths']
            extra = data['extra']
            start_x = start_x_list[idx]

            pinyin_y = cur_y
            char_y = pinyin_y + self.pinyin_font_size + 4   # 增加4px间距

            cur_x = start_x
            for i, c in enumerate(line_chars):
                char_w = char_widths[i]
                pinyin_w = pinyin_widths[i]
                
                # 拼音水平居中于汉字
                pinyin_x = cur_x + (char_w - pinyin_w) // 2
                pinyin_x = max(2, min(pinyin_x, self.width - pinyin_w - 2))
                
                layout.positions.append({
                    'char_x': cur_x,
                    'char_y': char_y,
                    'char_w': char_w,
                    'pinyin_x': pinyin_x,
                    'pinyin_y': pinyin_y,
                    'pinyin_w': pinyin_w,
                    'char': c.char,
                    'pinyin': c.pinyin,
                    'tone': c.tone
                })

                # 移动到下一个字符位置
                cur_x += char_w + self.base_char_spacing
                if i < len(extra):
                    cur_x += extra[i]

            # 计算本行背景矩形（基于实际字符边界）
            min_x = min(p['char_x'] for p in layout.positions if p['char'] == line_chars[0].char) - self.line_padding
            max_x = max(p['char_x'] + p['char_w'] for p in layout.positions if p['char'] == line_chars[-1].char) + self.line_padding
            min_y = max(0, cur_y - 6)
            max_y = min(self.height, char_y + self.char_font_size + 12)
            layout.bg_rects.append((max(0, min_x), min_y, min(self.width, max_x), max_y))

            cur_y += self.line_height

        self.layout_cache[line.line_number] = layout
        return layout
        
    def _render_char(self, char: str, pinyin: str, tone: str) -> Tuple[Image.Image, int, int]:
        """返回 (图像, 图像宽度, 图像高度)，图像尺寸刚好容纳文字（含阴影边距）"""
        key = (char, pinyin, tone)
        if key in self.char_cache:
            return self.char_cache[key]
        
        # 先测量实际文字尺寸
        char_w = self._get_text_width(char, self.char_font)
        char_h = self.char_font_size  # 近似高度
        pinyin_w = self._get_text_width(pinyin, self.pinyin_font) if pinyin else 0
        pinyin_h = self.pinyin_font_size if pinyin else 0
        
        # 图像宽度 = max(汉字宽, 拼音宽) + 左右内边距
        content_w = max(char_w, pinyin_w)
        # 图像高度 = 拼音高 + 汉字高 + 上下内边距
        content_h = pinyin_h + char_h + 12
        padding = 8
        img_w = content_w + padding * 2
        img_h = content_h + padding
        
        img = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # 绘制拼音（带黑色阴影）
        if pinyin:
            color = self.tone_colors.get(tone, (255, 255, 255))
            px = padding + (content_w - pinyin_w) // 2
            py = 4
            # 阴影
            for dx, dy in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                draw.text((px+dx, py+dy), pinyin, font=self.pinyin_font, fill=(0,0,0))
            draw.text((px, py), pinyin, font=self.pinyin_font, fill=color)
        
        # 绘制汉字
        cx = padding + (content_w - char_w) // 2
        cy = pinyin_h + 6
        for dx, dy in [(-1,-1),(-1,1),(1,-1),(1,1)]:
            draw.text((cx+dx, cy+dy), char, font=self.char_font, fill=(0,0,0))
        draw.text((cx, cy), char, font=self.char_font, fill=(255,255,255))
        
        self.char_cache[key] = (img, img_w, img_h)
        return img, img_w, img_h
        
    def _prebuild_cache(self):
        print("构建字符缓存...")
        unique = set()
        for line in self.lines:
            for c in line.chars:
                unique.add((c.char, c.pinyin, c.tone))
        
        for i, (char, pinyin, tone) in enumerate(unique):
            self._render_char(char, pinyin, tone)
            if (i + 1) % 50 == 0 or i + 1 == len(unique):
                print(f"\r  字符: {i+1}/{len(unique)}", end='')
        print(f"\n✅ {len(unique)} 字符缓存完成")
        
        print("预渲染歌词行...")
        for line in self.lines:
            self._render_line_to_numpy(line)
        print(f"✅ {len(self.lines)} 行缓存完成")
        
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
        
        # 绘制背景矩形
        for rect in layout.bg_rects:
            draw.rectangle(rect, fill=self.bg_color)
        
        # 绘制每个字符
        for pos in layout.positions:
            char_img, img_w, img_h = self._render_char(pos['char'], pos['pinyin'], pos['tone'])
            # 粘贴位置：字符左上角对齐到 char_x，但需要减去图像的内边距
            paste_x = pos['char_x'] - 8   # 减去 padding
            paste_y = pos['char_y'] - 6   # 调整垂直对齐
            # 边界裁剪防止超出画面
            img.paste(char_img, (paste_x, paste_y), char_img)
        
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
        
    def preview_lines(self, line_spec: str):
        """预览指定行，保存为 PNG"""
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
            
            # 生成预览图
            img = Image.new('RGBA', (self.width, self.height), (30, 30, 30, 255))
            layout = self._calculate_layout(line)
            if layout:
                draw = ImageDraw.Draw(img)
                for rect in layout.bg_rects:
                    draw.rectangle(rect, fill=self.bg_color)
                for pos in layout.positions:
                    char_img, _, _ = self._render_char(pos['char'], pos['pinyin'], pos['tone'])
                    paste_x = pos['char_x'] - 8
                    paste_y = pos['char_y'] - 6
                    img.paste(char_img, (paste_x, paste_y), char_img)
            
            out_path = os.path.join(self.script_dir, f"preview_line_{n}.png")
            img.save(out_path)
            print(f"✅ 已保存 {out_path}")
        
    def _print_progress(self, current: int, total: int, elapsed: float, fps: float):
        percent = current / total * 100 if total > 0 else 0
        bar_width = 30
        filled = int(bar_width * current // total)
        bar = '█' * filled + '░' * (bar_width - filled)
        remaining = (total - current) / fps if fps > 0 else 0
        
        print(f"\r│{bar}│ {percent:5.1f}% │ {current:>6}/{total:<6} │ {fps:>6.1f} fps │ ⏱️ {format_time(elapsed)} │ ⏳ {format_time(remaining)}", end='', flush=True)
        
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
        
        print(f"\n{'='*70}")
        print(f"🎬 开始渲染")
        print(f"{'='*70}")
        print(f"  分辨率:    {self.width}x{self.height}")
        print(f"  帧率:      {self.fps} fps")
        print(f"  总帧数:    {total_frames:,}")
        print(f"  预计时长:  {format_time(total_frames / self.fps)}")
        print(f"  输入视频:  {input_video}")
        print(f"  输出视频:  {output_video}")
        print(f"{'='*70}\n")
        
        cmd = [
            'ffmpeg', '-y',
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
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-threads', '4',
            '-c:a', 'copy',
            '-shortest',
            output_video
        ]
        
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
                    return False
                
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
            
            print()
            print(f"\n✅ 所有帧已发送，关闭管道...")
            
            process.stdin.close()
            
            print("等待 FFmpeg 编码完成...")
            while process.poll() is None:
                time.sleep(0.5)
                print(".", end='', flush=True)
            print()
            
            total_elapsed = time.time() - start_time
            
            if process.returncode == 0:
                print(f"\n{'='*70}")
                print("🎉 渲染成功！")
                print(f"{'='*70}")
                print(f"  总用时:     {format_time(total_elapsed)}")
                print(f"  平均速度:   {total_frames/total_elapsed:.1f} fps")
                print(f"  输出文件:   {output_video}")
                if os.path.exists(output_video):
                    size_mb = os.path.getsize(output_video) / (1024 * 1024)
                    print(f"  文件大小:   {size_mb:.1f} MB")
                print(f"{'='*70}")
                return True
            else:
                print(f"\n❌ FFmpeg 失败 (代码: {process.returncode})")
                if ffmpeg_errors:
                    print("错误日志:")
                    print(''.join(ffmpeg_errors[-20:]))
                return False
                
        except KeyboardInterrupt:
            print("\n\n⚠️ 用户中断")
            process.kill()
            return False
        except Exception as e:
            print(f"\n\n❌ 错误: {e}")
            process.kill()
            return False


def main():
    print("="*70)
    print("🚀 粤语拼音字幕生成器 - 极速版 v11（修复显示不全+动态宽度）")
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
    
    # 预览功能
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
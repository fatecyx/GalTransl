import json
import re
from collections import Counter

try:
    from GalTransl import LOGGER
    from GalTransl.CSentense import CSentense
    from GalTransl.GTPlugin import GTextPlugin
except ImportError:
    # ── 本地测试环境模拟 ─────────────────────────────────────────────────────────
    class _FakeLogger:
        def info(self, msg): print("[INFO]", msg)
        def warning(self, msg): print("[WARN]", msg)
    LOGGER = _FakeLogger()

    class CSentense:
        def __init__(self, src):
            self.post_jp = src
            self.post_zh = ""
            self.problem = ""

    class GTextPlugin:
        pass
    # ── 本地测试环境模拟结束 ───────────────────────────────────────────────────────

# ── 成对括号/引号定义 ──────────────────────────────────────────────────────────
# key=左符号, value=字符串（每字符均为可接受的右符号，第一个为首选）
# 弯引号用转义写法避免编辑器对引号的误解析
SYMBOL_PAIRS = {
    "「": "」｣",
    "｢": "｣」",
    "『": "』",
    "\u201c": "\u201d",   # " → "
    "（": "）)",
    "(": ")）",
    "【": "】",
    "\"": "\"",
    "'": "'",
}
REVERSE_SYMBOLS = {r: left for left, rights in SYMBOL_PAIRS.items() for r in rights}

# ── 成对括号扫描定义（用于 fix_paired_symbols 的位置对应匹配） ────────────────
# 原文中视为「成对括号」的品种（用于提取 src 的有序成对符号列表）
SRC_BRACKET_PAIRS: list[tuple[str, str]] = [
    ("「", "」"), ("｢", "｣"), ("『", "』"),
    ("（", "）"), ("【", "】"), ("＜", "＞"),
    ("《", "》"), ("<", ">"), ("(", ")"),
    ("[", "]"), ("［", "］"),
]
# 译文中视为「成对括号」的品种（涵盖所有原文类型 + 常见替代形式）
# 顺序影响歧义时的优先级（非对称符号先于对称符号）
DST_BRACKET_PAIRS: list[tuple[str, str]] = [
    ("「", "」"), ("｢", "｣"), ("『", "』"),
    ("（", "）"), ("【", "】"), ("＜", "＞"),
    ("《", "》"), ("〈", "〉"), ("<", ">"), ("(", ")"),
    ("[", "]"), ("［", "］"),
    ("\u201c", "\u201d"),   # “ ” 弯双引号
    ("\u2018", "\u2019"),   # ‘ ’ 弯单引号
    ("'", "'"),             # ASCII 单引号（对称）
    ('"', '"'),             # ASCII 双引号（对称）
]
# 辅助查找表
_DST_LEFT_TO_RIGHT: dict[str, str] = {l: r for l, r in DST_BRACKET_PAIRS}
_DST_RIGHT_TO_LEFT: dict[str, str] = {r: l for l, r in DST_BRACKET_PAIRS if l != r}
_DST_SYMMETRIC: frozenset[str] = frozenset(l for l, r in DST_BRACKET_PAIRS if l == r)
_SRC_LEFT_SET: frozenset[str] = frozenset(l for l, r in SRC_BRACKET_PAIRS)
_SRC_RIGHT_TO_LEFT: dict[str, str] = {r: l for l, r in SRC_BRACKET_PAIRS}
_SRC_LEFT_TO_RIGHT_MAP: dict[str, str] = {l: r for l, r in SRC_BRACKET_PAIRS}

# 不告警的基本标点（逗号、句号、感叹号、问号）
NO_WARN_BASIC = set("，。！？,.")

# ── 全角/带圈字符 → 对应半角的映射 ──────────────────────────────────────────────
FULLWIDTH_TO_HALF = {}
# 全角英文大写 Ａ-Ｚ → A-Z
FULLWIDTH_TO_HALF.update({chr(0xFF21 + i): chr(0x41 + i) for i in range(26)})
# 全角英文小写 ａ-ｚ → a-z
FULLWIDTH_TO_HALF.update({chr(0xFF41 + i): chr(0x61 + i) for i in range(26)})
# 全角数字 ０-９ → 0-9
FULLWIDTH_TO_HALF.update({chr(0xFF10 + i): str(i) for i in range(10)})
# 带圈数字 ①-⑨ → 1-9
FULLWIDTH_TO_HALF.update({chr(0x2460 + i): str(i + 1) for i in range(9)})

# 带圈数字字符集（用于告警判断）
CIRCLED_DIGITS = frozenset(chr(0x2460 + i) for i in range(9))
# 全角字母字符集（Ａ-Ｚ, ａ-ｚ）
FW_LETTERS = frozenset(
    [chr(0xFF21 + i) for i in range(26)] +
    [chr(0xFF41 + i) for i in range(26)]
)
# 全角纯数字字符集（０-９，不含带圈数字）
FW_PURE_DIGITS = frozenset(chr(0xFF10 + i) for i in range(10))

# ── 调试开关：设为 True 时 fix_fullwidth_chars 输出详细匹配信息 ─────────────────
DEBUG_FULLWIDTH: bool = False

# ── 换行正则：匹配 \r\n / \r / \n，以及之后紧跟的 ＞? + 全/半角空格 ─────────────
RE_LINEBREAK = re.compile(r'(\r\n|\r|\n)(＞?[ \u3000]*)')

# ── 句中直引号/弯引号正则 ─────────────────────────────────────────────────────
# 单引号族：匹配 '...' 或 '...' 或 '...'（左右弯引号视为非对称对）
# 双引号族：匹配 "..." 或 "..." 或 “...”（左右弯引号视为非对称对）
# 采用两个独立分支：先尝试匹配弯引号的非对称对，再匹配 ASCII 对称引号
# 注意：不能用 \1 回引用，因为左右弯引号是不同的 Unicode 码点
RE_INLINE_SINGLE = re.compile(
    r"\u2018([^\x27\u2018\u2019\r\n]*?)\u2019"  # '...' 弯引号对
    r"|'([^'\r\n]*?)'"                             # '...' ASCII 对称
)
RE_INLINE_DOUBLE = re.compile(
    r"\u201c([^\"\u201c\u201d\r\n]*?)\u201d"   # \u201c...\u201d 弯引号对
    r'|"([^"\r\n]*?)"'                             # "..." ASCII 对称
)


class text_common_punctuation_fixer(GTextPlugin):

    # ── 非成对基本标点修复规则 ────────────────────────────────────────────────
    # 仅包含不成对的符号；成对符号由 fix_paired_symbols 处理
    RULE_BASIC = {
        # A区：原文全角，译文可能用半角/其他
        "：": (":",),
        "・": ("\u00b7",),    # ·
        "？": ("?",),
        "！": ("!",),
        "\u2014": ("-", "\u2015"),   # ― → - / —
        "\u2015": ("-", "\u2014"),   # — → - / ―
        "＠": ("@",),
        "〇": ("○",),
        # B区：原文半角，译文可能用全角/其他
        ":": ("：",),
        "\u00b7": ("・",),           # · → ・
        "?": ("？",),
        "!": ("！",),
        "-": ("\u2014", "\u2015"),
        "$": ("＄",),
    }

    # ── 成对符号 alt 优先级定义 ────────────────────────────────────────────
    # 每个原文成对符号在译文中可能被替换为哪些形式，按优先级从高到低列出。
    # 左符号和右符号的 alt 按相同索引配对，即 alt[i] 构成一个对。
    # 处理时过滤掉原文中已存在的符号（原文有则不视为 alt）。
    RULE_PAIRED = {
        # 日式单引号
        "「": ("‘", "'", "“", "『", "《"),
        "」": ("’", "'", "”", "』", "》"),
        # 日式双引号
        "『": ("“", "‘", "'", "「", "《"),
        "』": ("”", "’", "'", "」", "》"),
        # 全角尖括号
        "＜": ("<", "《"),
        "＞": (">", "》"),
        # 全角圆括号
        "（": ("(", "‘", "“"),
        "）": (")", "’", "”"),
        # 全角方括号
        "【": ("“", "‘"),
        "】": ("”", "’"),
        # 半角尖括号（原文用半角）
        "<": ("＜", "《"),
        ">": ("＞", "》"),
        # 半角圆括号（原文用半角）
        "(": ("（", "‘", "“"),
        ")": ("）", "’", "”"),
        # 半角方括号（原文用半角，译文可能用全角）
        "[": ("［",),
        "]": ("］",),
        # 全角方括号（原文用全角，译文可能用半角）
        "［": ("[",),
        "］": ("]",),
    }

    def __init__(self) -> None:
        super().__init__()

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. 换行符处理
    # ═══════════════════════════════════════════════════════════════════════════
    @staticmethod
    def _fix_linebreaks(src: str, dst: str) -> tuple[str, set]:
        """
        - 三种换行符（\\r\\n / \\r / \\n）各自计数，分别保持与原文数量一致。
        - 若原文同时出现多种换行符（罕见），不做自动修正，数量不一致时告警。
        - 换行后空格：src 各换行后的最小空格数 X 作为下限，dst 不足时补足。
        """
        warnings = set()
        src_breaks = RE_LINEBREAK.findall(src)   # list of (lb_type, spaces)
        if not src_breaks:
            return dst, warnings

        dst_breaks = RE_LINEBREAK.findall(dst)

        src_counter = Counter(lb for lb, _ in src_breaks)
        dst_counter = Counter(lb for lb, _ in dst_breaks)
        lb_types = set(src_counter.keys())

        if len(lb_types) > 1:
            # 原文混用多种换行 → 不自动修正，各类型分别告警
            for lb_type, src_cnt in src_counter.items():
                dst_cnt = dst_counter.get(lb_type, 0)
                if dst_cnt != src_cnt:
                    warnings.add(f"换行符{repr(lb_type)}数量不一致({src_cnt}→{dst_cnt})")
            return dst, warnings

        # 原文只有一种换行类型 → 只做形式标准化，不告警数量变动
        src_lb = next(iter(lb_types))
        src_cnt = src_counter[src_lb]

        if not dst_breaks:
            # dst 无换行，只做直接返回（不告警）
            return dst, warnings

        # 计算 src 换行后的最小空格数（作为下限）
        min_spaces = min(len(sp) for _, sp in src_breaks)

        def replace_break(m):
            spaces = m.group(2)
            if len(spaces) < min_spaces:
                spaces = spaces + " " * (min_spaces - len(spaces))
            return src_lb + spaces

        dst_fixed = RE_LINEBREAK.sub(replace_break, dst)

        # 单一换行类型：不检查数量是否一致，直接返回标准化后的结果
        return dst_fixed, warnings

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. 句首/句尾成对引号修正
    # ═══════════════════════════════════════════════════════════════════════════
    @classmethod
    def match_outer_quote(cls, src: str, dst: str) -> str:
        """
        ① 句首/句尾的成对符号：确保译文首尾引号与原文一致。
        也处理"此句仅有单侧引号"（句中不存在另一侧）的情况。
        """
        if not src or not dst:
            return dst

        def is_pair(left, right):
            return left and left in SYMBOL_PAIRS and right and right in SYMBOL_PAIRS.get(left, "")

        src_s = src.strip(" ")
        src_left  = src_s[0]  if src_s and src_s[0]  in SYMBOL_PAIRS else ""
        src_right = src_s[-1] if src_s and src_s[-1] in REVERSE_SYMBOLS else ""

        dst_left  = dst[0]  if dst and dst[0]  in SYMBOL_PAIRS else ""
        dst_right = dst[-1] if dst and dst[-1] in REVERSE_SYMBOLS else ""

        src_pair = is_pair(src_left, src_right)
        dst_pair = is_pair(dst_left, dst_right)

        # 两边都没有成对引号，不处理
        if not src_left and not src_right and not dst_left and not dst_right:
            return dst

        # 确定 dst 的核心内容（剥去现有外层引号）
        dst_core = dst
        if dst_left and dst_right and is_pair(dst_left, dst_right):
            dst_core = dst[1:-1]
        elif dst_left and dst_left in SYMBOL_PAIRS:
            dst_core = dst[1:]
        elif dst_right and dst_right in REVERSE_SYMBOLS:
            dst_core = dst[:-1]

        # 情况1：src 有首尾成对引号 → 套用 src 引号
        if src_pair:
            fixed_right = SYMBOL_PAIRS[src_left][0]
            return src_left + dst_core + fixed_right

        # 情况2：src 无引号，dst 有对 → 去掉译文引号（AI 多加了）
        if not src_left and not src_right and dst_pair:
            return dst_core

        # 情况3：src 只有左引号
        if src_left and not src_right:
            # 前置检查：若 src 内部（位置1之后）已有对应的右符号，
            # 说明这是句中内联引号而非句首外层引号，不处理
            src_inner_rights = SYMBOL_PAIRS.get(src_left, "")
            if any(ch in src_s[1:] for ch in src_inner_rights):
                return dst
            if dst_pair:
                return src_left + dst_core
            elif not dst_left:
                return src_left + dst
            else:
                return src_left + (dst[1:] if dst_left else dst)

        # 情况4：src 只有右引号
        if not src_left and src_right:
            # 前置检查：若 src 内部（最后一个字符之前）已有对应的左符号，
            # 说明这是句中内联引号而非句尾外层引号，不处理
            src_inner_left = REVERSE_SYMBOLS.get(src_right, "")
            if src_inner_left and src_inner_left in src_s[:-1]:
                return dst
            if dst_pair:
                return dst_core + src_right
            elif not dst_right:
                return dst + src_right
            else:
                return (dst[:-1] if dst_right else dst) + src_right

        return dst

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. 句中短语成对引号转换
    # ═══════════════════════════════════════════════════════════════════════════
    @classmethod
    def fix_inline_quotes(cls, src: str, dst: str) -> str:
        """
        ② 句中短语的成对引号转换逻辑：

        先判断原文（去掉句首/句尾引号后的内部）是否含有 「」 和/或 『』：

        A. 原文都没有「」和『』：
           - 译文中的 '单引号' → 「」
           - 译文中的 "双引号" → 『』
           （原文没有对应日式引号才转换，各自独立判断）

        B. 原文有「」或『』其中一种：
           - 将译文中的直/弯引号统一转换为原文**没有**的那一种
           （优先使用另一种；若两种都有则不转，见C）

        C. 原文两种都有：不转换，保持 dst 原样。

        特殊：日文中偶尔用引号作语气词（引号内容为空）→ 跳过不转换。
        """
        # 去掉句首/句尾引号后，检测内部是否有日式引号
        src_inner = src.strip()
        if (len(src_inner) >= 2
                and src_inner[0] in SYMBOL_PAIRS
                and src_inner[-1] in REVERSE_SYMBOLS
                and SYMBOL_PAIRS.get(src_inner[0], "").find(src_inner[-1]) >= 0):
            src_inner = src_inner[1:-1]

        has_kagi = "「" in src_inner or "」" in src_inner    # 「」
        has_niju = "『" in src_inner or "』" in src_inner    # 『』

        # C：两种都有 → 不转换
        if has_kagi and has_niju:
            return dst

        def _empty_content(content: str) -> bool:
            """内容为空 → 视为语气引号，跳过。"""
            return len(content.strip()) == 0

        if not has_kagi and not has_niju:
            # A：两种都没有
            # 单引号 → 「」（若原文全文也没有「」才转）
            src_no_kagi = "「" not in src and "」" not in src
            # 双引号 → 『』（若原文全文也没有『』才转）
            src_no_niju = "『" not in src and "』" not in src

            def repl_single(m):
                content = m.group(1) or m.group(2) or ""
                if _empty_content(content):
                    return m.group(0)
                return ("「" + content + "」") if src_no_kagi else m.group(0)

            def repl_double(m):
                content = m.group(1) or m.group(2) or ""
                if _empty_content(content):
                    return m.group(0)
                return ("『" + content + "』") if src_no_niju else m.group(0)

        else:
            # B：原文有其中一种 → 转换为原文没有的那种
            if has_kagi and not has_niju:
                # 原文有「」没『』→ 统一转为 『』
                target_l, target_r = "『", "』"
            else:
                # 原文有『』没「」→ 统一转为 「」
                target_l, target_r = "「", "」"

            def repl_single(m):
                content = m.group(1) or m.group(2) or ""
                if _empty_content(content):
                    return m.group(0)
                return target_l + content + target_r

            def repl_double(m):
                content = m.group(1) or m.group(2) or ""
                if _empty_content(content):
                    return m.group(0)
                return target_l + content + target_r

        dst = RE_INLINE_SINGLE.sub(repl_single, dst)
        dst = RE_INLINE_DOUBLE.sub(repl_double, dst)
        return dst

    # ═══════════════════════════════════════════════════════════════════════════
    # 3b. 原文成对符号 → 译文对应位置修正（位置对应法）
    # ═══════════════════════════════════════════════════════════════════════════
    @staticmethod
    def _extract_src_pairs(src: str) -> list[tuple[str, str, int, int]]:
        """
        用栈扫描 src，提取 SRC_BRACKET_PAIRS 中定义的成对符号列表。
        返回 [(left, right, left_pos, right_pos), ...] 按配对完成顺序。
        """
        result: list[tuple[str, str, int, int]] = []
        stack: list[tuple[str, int]] = []  # (left_char, pos)
        for i, ch in enumerate(src):
            if ch in _SRC_LEFT_SET:
                stack.append((ch, i))
            elif ch in _SRC_RIGHT_TO_LEFT:
                expected = _SRC_RIGHT_TO_LEFT[ch]
                if stack and stack[-1][0] == expected:
                    l_ch, l_pos = stack.pop()
                    result.append((l_ch, ch, l_pos, i))
        return result

    @staticmethod
    def _extract_dst_pairs(dst: str) -> list[tuple[str, str, int, int]]:
        """
        用栈扫描 dst，提取 DST_BRACKET_PAIRS 中定义的成对符号列表。
        对称引号（ASCII ' 和 "）：栈顶为同符号则关闭，否则开启。
        特处：若 ' 或 " 夹在两个字母/数字之间（如 It's / don't），
              视为撇号而非引号，跳过不入栈。
        返回 [(left, right, left_pos, right_pos), ...] 按配对完成顺序。
        """
        result: list[tuple[str, str, int, int]] = []
        stack: list[tuple[str, int]] = []  # (left_char, pos)
        n = len(dst)
        for i, ch in enumerate(dst):
            if ch in _DST_SYMMETRIC:
                # 撇号检测：左右邻字符均为字母/数字 → 视为撇号，跳过
                prev_alnum = i > 0 and (dst[i - 1].isalpha() or dst[i - 1].isdigit())
                next_alnum = i + 1 < n and (dst[i + 1].isalpha() or dst[i + 1].isdigit())
                if prev_alnum and next_alnum:
                    continue
                # 对称引号：栈顶为同符号则关闭，否则开启
                if stack and stack[-1][0] == ch:
                    l_ch, l_pos = stack.pop()
                    result.append((l_ch, ch, l_pos, i))
                else:
                    stack.append((ch, i))
            elif ch in _DST_LEFT_TO_RIGHT:
                stack.append((ch, i))
            elif ch in _DST_RIGHT_TO_LEFT:
                expected = _DST_RIGHT_TO_LEFT[ch]
                if stack and stack[-1][0] == expected:
                    l_ch, l_pos = stack.pop()
                    result.append((l_ch, ch, l_pos, i))
        return result

    @classmethod
    def fix_paired_symbols(cls, src: str, dst: str,
                           check_count: bool = True) -> tuple[str, set]:
        """
        在 fix_inline_quotes 之前处理：
        将译文中成对符号的 alt 形式替换为原文对应的正确符号。

        采用「累积优先级匹配法」：
          对每种 src 符号类型（如 『』），需补足数量为 N：
          1. 按 RULE_PAIRED 中的优先级顺序，逐个 alt 对类型累积计数
             （_extract_dst_pairs 识别 dst 中的实际成对实例）。
          2. 当累积数量 == N 时，批量替换所有已累积的 alt 对 → 正确符号。
          3. 若累积超过 N（歧义）或所有 alt 都不够，则不替换，可选告警。

        优势：不按语序位置对应（语序变化大），而是按"符号总数是否刚好匹配"
        来判断是否可替换，同时对多种不同符号并存的情况也能正确区分。

        例：
          src=族長の『鉄火』か   dst=族长'铁火'吗   → 族长『铁火』吗
          src=族長の『鉄火』か   dst=族长《铁火》吗  → 族长『铁火』吗
          src=「好き」…『嫌い』  dst='喜欢'…"讨厌"  → 「喜欢」…『讨厌』
            (「: '…'=1=N ✓; 『: "…"=1=N ✓)
          src=「好き」…『嫌い』  dst="喜欢"…"讨厌"  → 不替换+告警
            (「: "…"=2>N=1 歧义)
        """
        warnings: set = set()

        src_pairs = cls._extract_src_pairs(src)
        if not src_pairs:
            return dst, warnings

        # 统计各 src 左符号的出现次数（按首次出现顺序）
        seen_lefts: list[str] = []
        left_count: dict[str, int] = {}
        for l, r, lp, rp in src_pairs:
            if l not in left_count:
                seen_lefts.append(l)
                left_count[l] = 0
            left_count[l] += 1

        for left_sym in seen_lefts:
            n_src = left_count[left_sym]
            right_sym = SYMBOL_PAIRS.get(left_sym, "") or _SRC_LEFT_TO_RIGHT_MAP.get(left_sym, "")
            if not right_sym:
                continue
            right_sym = right_sym[0]  # 首选右符号

            if left_sym not in cls.RULE_PAIRED:
                continue

            # 重新提取 dst 的成对符号（dst 可能被上一轮修改）
            dst_pairs_now = cls._extract_dst_pairs(dst)

            # 已正确存在的数量：直接统计左符号出现次数，避免配对提取因内部撇号等失败
            n_correct = dst.count(left_sym)
            need = n_src - n_correct
            if need <= 0:
                continue

            # 构建有效 alt 对（过滤掉原文中已存在的符号）
            raw_alt_l = cls.RULE_PAIRED.get(left_sym,  ())
            raw_alt_r = cls.RULE_PAIRED.get(right_sym, ())
            alt_pairs = [(al, ar) for al, ar in zip(raw_alt_l, raw_alt_r)
                         if al not in src and ar not in src]

            if not alt_pairs:
                if check_count:
                    warnings.add(left_sym)
                continue

            # 累积优先级匹配
            cumulative = 0
            chosen: list[tuple[int, int, int, int]] = []  # (dl_pos,dl_len,dr_pos,dr_len)
            matched = False

            for al, ar in alt_pairs:
                found = [(lp, len(l), rp, len(r))
                         for l, r, lp, rp in dst_pairs_now
                         if l == al and r == ar]
                if not found:
                    continue
                cumulative += len(found)
                chosen.extend(found)
                if cumulative == need:
                    matched = True
                    break
                if cumulative > need:
                    break  # 超过需要数量，歧义，放弃

            if matched:
                # 按右符号位置从大到小排序，避免替换时位置偏移
                for dl_pos, dl_len, dr_pos, dr_len in \
                        sorted(chosen, key=lambda x: x[2], reverse=True):
                    dst = dst[:dr_pos] + right_sym + dst[dr_pos + dr_len:]
                    dst = dst[:dl_pos] + left_sym  + dst[dl_pos + dl_len:]
            elif check_count:
                warnings.add(left_sym)

        return dst, warnings

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. 全角英文/数字/带圈数字 自动转换
    # ═══════════════════════════════════════════════════════════════════════════

    # 匹配原文中连续的全角/带圈字符块（字符需在 FULLWIDTH_TO_HALF 的 key 集合内）
    # 在运行时动态生成，避免在类定义时 FULLWIDTH_TO_HALF 尚未初始化
    _RE_FW_BLOCK = None

    # 匹配译文中连续的半角字母/数字词块（用于精确词块对比，防止子串误替换）
    _RE_HW_BLOCK = None

    @classmethod
    def _get_fw_block_re(cls) -> re.Pattern:
        if cls._RE_FW_BLOCK is None:
            # 全角字母/数字/带圈数字均为 Unicode 普通字符，无需转义，直接拼进字符类
            chars = "".join(FULLWIDTH_TO_HALF.keys())
            cls._RE_FW_BLOCK = re.compile("[" + chars + "]+")
        return cls._RE_FW_BLOCK

    @classmethod
    def _get_hw_block_re(cls) -> re.Pattern:
        """匹配译文中连续的半角字母/数字词块（A-Za-z0-9 组成的连续串）。"""
        if cls._RE_HW_BLOCK is None:
            cls._RE_HW_BLOCK = re.compile(r"[A-Za-z0-9]+")
        return cls._RE_HW_BLOCK

    @classmethod
    def fix_fullwidth_chars(cls, src: str, dst: str) -> tuple[str, set]:
        """
        按字符类型分组的全角词块转换：

        将原文全角字符按类型拆分为子块（L=字母 / D=数字 / C=带圈数字），分别处理：

        · 带圈数字（C）：延迟到 L/D 组处理后判断——若被 L/D 组的阶段②b 吸收则不告警；
          否则若全角形式不在 dst 则告警。

        · 字母/数字子块（L/D）：两阶段+扩展匹配：
          ① 类型感知独立匹配：将 DST 半角词块内部也按字母/数字细分，
             L子块只在 DST 的字母段中匹配，D子块只在数字段中匹配。
             所有子块均唯一匹配 → 按位置从右到左逐一替换。
          ② 合并匹配：阶段①失败时，把相邻 L/D 子块的半角串拼接，
             在 DST hw 词块中整体搜索：
               唯一匹配 → 整体替换；多处 → 告警。
          ②b 前/后置带圈数字扩展：阶段②也失败时，将相邻 C 块的半角数字
             拼接到组合串前/后，再次搜索 hw 词块：
               唯一匹配 → 替换 L/D 部分，并将对应带圈数字标记为"已核算"；
               多处 → 告警；无匹配 → 静默跳过。

        示例：
          SRC='ＡＢＣ１２３①②', DST='123ABC①②'
            · ①② 已在 dst（全角）→ 带圈数字不进入 pending，无告警
            · DST hw块 '123ABC' → 字母段 'ABC'(3-6)、数字段 '123'(0-3)
            · ＡＢＣ(L)→ 匹配字母段 'ABC' 唯一 ✓
            · １２３(D)→ 匹配数字段 '123' 唯一 ✓
            → 各自替换 → １２３ＡＢＣ①②
          SRC='ＡＢＣ１２３④⑤', DST='ABC12345'
            · ④⑤ 不在 dst（全角），进入 pending
            · DST hw块 'ABC12345' → 字母段 'ABC'、数字段 '12345'
            · ＡＢＣ(L)→ 匹配字母段 'ABC' ✓  但 １２３(D)→ '12345'≠'123' ✗ → 阶段①失败
            · 阶段②：'ABC123' 不是完整 hw 词块 → 失败
            · 阶段②b：suffix_c_hw='45'，尝试 'ABC12345' → 唯一匹配 ✓
              → 替换为 ＡＢＣ１２３，同时标记 ④⑤ 已核算 → 无告警
          SRC='Ｃ测试', DST='China'
            · DST 字母段 'China' != 'C' → 阶段①无匹配 → 阶段②合并仍是 'C' 无匹配 → 静默跳过
        """
        warnings: set = set()
        re_fw = cls._get_fw_block_re()
        re_hw = cls._get_hw_block_re()

        def char_type(c: str) -> str:
            """L=全角字母, D=全角数字, C=带圈数字"""
            if c in CIRCLED_DIGITS:  return 'C'
            if c in FW_LETTERS:     return 'L'
            if c in FW_PURE_DIGITS: return 'D'
            return '?'

        def split_typed(fw_block: str) -> list[tuple[str, str]]:
            """将全角词块按字符类型拆分为 [(type, chars), ...] 列表。"""
            if not fw_block:
                return []
            result = []
            cur_t = char_type(fw_block[0])
            cur = fw_block[0]
            for c in fw_block[1:]:
                t = char_type(c)
                if t == cur_t:
                    cur += c
                else:
                    result.append((cur_t, cur))
                    cur_t, cur = t, c
            result.append((cur_t, cur))
            return result

        def fw_to_hw(s: str) -> str:
            return "".join(FULLWIDTH_TO_HALF.get(c, c) for c in s)

        def get_dst_typed_segs(dst_str: str) -> list[tuple[str, int, int, str, bool]]:
            """
            将 dst 的所有半角词块按字母/数字类型细分，返回：
            [(type, abs_start, abs_end, chars, mixed), ...]
            type: 'L'=字母段, 'D'=数字段
            mixed: 该段所在的半角词块是否同时包含字母和数字
                   （如 'v12' 中的 'v' 段和 '12' 段均为 mixed=True）
            """
            segs = []
            for m in re_hw.finditer(dst_str):
                block = m.group()
                bs = m.start()
                # 判断该词块是否为混合型（同时含字母和数字）
                has_alpha = any(c.isalpha() for c in block)
                has_digit = any(c.isdigit() for c in block)
                mixed = has_alpha and has_digit
                cur_t = 'L' if block[0].isalpha() else 'D'
                run_start = 0
                for i, c in enumerate(block):
                    t = 'L' if c.isalpha() else 'D'
                    if t != cur_t:
                        segs.append((cur_t, bs + run_start, bs + i, block[run_start:i], mixed))
                        cur_t, run_start = t, i
                segs.append((cur_t, bs + run_start, bs + len(block), block[run_start:], mixed))
            return segs

        def find_typed_segs(hw_str: str, typ: str,
                            segs: list[tuple[str, int, int, str, bool]]) -> list[int]:
            """
            在 segs 中找 type==typ 且 chars==hw_str 的条目索引列表。
            对 D 型匹配，排除 mixed=True 的数字段（如 v12 里的 12），
            这类数字段属于字母+数字混合词块，不应被单独视为纯数字的翻译对应。
            """
            if typ == 'D':
                return [i for i, (t, s, e, c, mx) in enumerate(segs)
                        if t == typ and c == hw_str and not mx]
            return [i for i, (t, s, e, c, mx) in enumerate(segs) if t == typ and c == hw_str]

        def find_exact_hw_blocks(hw_str: str, dst_str: str):
            """在 dst_str 中找与 hw_str 完全相等的独立 hw 词块（返回 match 对象列表）。"""
            return [m for m in re_hw.finditer(dst_str) if m.group() == hw_str]

        # 提取原文中所有全角词块（去重保序）
        seen_blocks = set()
        fw_blocks = []
        for m in re_fw.finditer(src):
            block = m.group()
            if block not in seen_blocks:
                seen_blocks.add(block)
                fw_blocks.append(block)

        for fw_block in fw_blocks:
            # 译文已有该全角词块整体 → 无需处理
            if fw_block in dst:
                continue

            sub_blocks = split_typed(fw_block)  # [(type, chars), ...]

            # ── 收集带圈数字，延迟到 LD 组处理后再判断缺失 ──────────────────────
            # circled_pending: {char: bool is_accounted_for}
            # 初始全部标为"未核算"，LD 组处理时若发现被合并入数字串则标为 True
            circled_pending: dict[str, bool] = {}
            for typ, chars in sub_blocks:
                if typ == 'C':
                    for c in chars:
                        if c not in dst:  # 全角形式已在译文则无需关注
                            circled_pending[c] = False

            if DEBUG_FULLWIDTH:
                print(f"  [DBG] fw_block={fw_block!r} sub={sub_blocks} pending={circled_pending}")

            # ── 字母/数字子块：按连续 L/D 分组，将相邻 C 块的 hw 数字纳入扩展匹配 ─
            # ld_group_info 元素：(group, prefix_c_hw, prefix_c_fw, suffix_c_hw, suffix_c_fw)
            #   group        - [(fw, hw, type), ...] 该连续 L/D 子块列表
            #   prefix_c_hw / prefix_c_fw - 紧接在本组之前的 C 块：hw 形式 / 原始全角形式
            #   suffix_c_hw / suffix_c_fw - 紧接在本组之后的 C 块：hw 形式 / 原始全角形式
            ld_group_info: list[tuple[
                list[tuple[str, str, str]], str, str, str, str]] = []
            cur_group: list[tuple[str, str, str]] = []
            cur_prefix_c_hw = ""
            cur_prefix_c_fw = ""

            for typ, chars in sub_blocks:
                if typ in ('L', 'D'):
                    cur_group.append((chars, fw_to_hw(chars), typ))
                elif typ == 'C':
                    if not cur_group:
                        # 尚未进入 L/D 组 → 累积为前置 C 块
                        cur_prefix_c_hw += fw_to_hw(chars)
                        cur_prefix_c_fw += chars
                    else:
                        # 进入了 L/D 组后紧跟 C → 作为后置 C 块，截断当前组
                        ld_group_info.append((
                            cur_group,
                            cur_prefix_c_hw, cur_prefix_c_fw,
                            fw_to_hw(chars), chars,
                        ))
                        cur_group = []
                        cur_prefix_c_hw = ""
                        cur_prefix_c_fw = ""
                # 其他类型（中文等）截断 L/D 组，但不作为 C 前置
                else:
                    if cur_group:
                        ld_group_info.append((
                            cur_group,
                            cur_prefix_c_hw, cur_prefix_c_fw,
                            "", "",
                        ))
                        cur_group = []
                        cur_prefix_c_hw = ""
                        cur_prefix_c_fw = ""
            if cur_group:
                ld_group_info.append((
                    cur_group,
                    cur_prefix_c_hw, cur_prefix_c_fw,
                    "", "",
                ))

            def _mark_absorbed(pre_fw: str, suf_fw: str):
                """将 pre_fw/suf_fw 中的带圈原字符标记为已核算。"""
                for c in (pre_fw + suf_fw):
                    if c in circled_pending and not circled_pending[c]:
                        circled_pending[c] = True

            for group, prefix_c_hw, prefix_c_fw, suffix_c_hw, suffix_c_fw in ld_group_info:
                # 仅处理全角形式不在译文中的子块
                need_replace = [(fw, hw, typ) for fw, hw, typ in group if fw not in dst]
                if not need_replace:
                    continue

                combined_fw = "".join(fw for fw, hw, typ in need_replace)
                combined_hw = "".join(hw for fw, hw, typ in need_replace)

                replaced = False

                # ── 阶段②b（优先）：若有相邻带圈数字，尝试含其 hw 的扩展词块匹配 ────
                # 此阶段放在①之前，确保前置/后置 C 块均有机会被整体吸收
                if prefix_c_hw or suffix_c_hw:
                    for pre_hw, pre_fw, suf_hw, suf_fw in [
                        (prefix_c_hw, prefix_c_fw, suffix_c_hw, suffix_c_fw),  # 全前后
                        (prefix_c_hw, prefix_c_fw, "", ""),                      # 仅前置
                        ("", "", suffix_c_hw, suffix_c_fw),                      # 仅后置
                    ]:
                        if not pre_hw and not suf_hw:
                            continue
                        ext_hw = pre_hw + combined_hw + suf_hw
                        ext_matches = find_exact_hw_blocks(ext_hw, dst)
                        if DEBUG_FULLWIDTH:
                            print(f"  [DBG ③b] pre={pre_hw!r} suf={suf_hw!r} "
                                  f"ext_hw={ext_hw!r} matches={len(ext_matches)} dst={dst!r}")
                        if len(ext_matches) == 1:
                            m = ext_matches[0]
                            # 替换时恢复带圈数字为原始全角形式（不是 hw 数字）
                            dst = dst[:m.start()] + pre_fw + combined_fw + suf_fw + dst[m.end():]
                            _mark_absorbed(pre_fw, suf_fw)
                            replaced = True
                            break
                        elif len(ext_matches) > 1:
                            warnings.add(
                                f"全角转换歧义：{ext_hw}→{pre_fw + combined_fw + suf_fw}"
                                f"(出现{len(ext_matches)}次)"
                            )
                            replaced = True  # 歧义视为已处理，不继续尝试
                            break

                if replaced:
                    continue

                # ── 阶段①：类型感知的独立精确匹配 ──────────────────────────────────
                # 对 DST 半角词块按字母/数字细分，L 只匹配字母段，D 只匹配数字段
                dst_typed_segs = get_dst_typed_segs(dst)
                results = [
                    (fw, hw, typ, find_typed_segs(hw, typ, dst_typed_segs))
                    for fw, hw, typ in need_replace
                ]
                all_unique = all(len(idxs) == 1 for _, _, _, idxs in results)
                # 纯字母子块：允许多次出现，全部替换，不告警歧义
                all_L = (all(typ == 'L' for _, _, typ, _ in results)
                         and all(len(idxs) >= 1 for _, _, _, idxs in results))
                # 纯数字子块：出现次数 == src 中该全角块出现次数时，同样全部替换
                all_D_count_match = (
                    all(typ == 'D' for _, _, typ, _ in results)
                    and all(len(idxs) >= 1 for _, _, _, idxs in results)
                    and all(src.count(fw) == len(idxs) for fw, hw, typ, idxs in results)
                )

                if DEBUG_FULLWIDTH:
                    print(f"  [DBG ①] need={[(fw,hw) for fw,hw,_ in need_replace]} "
                          f"all_unique={all_unique} all_L={all_L} dst={dst!r}")

                if all_unique or all_L or all_D_count_match:
                    # 展开所有超块的所有匹配位置，由右到左替换
                    all_reps = []  # [(start, end, fw), ...]
                    for fw, hw, typ, idxs in results:
                        for idx in idxs:
                            _, s, e, _, _mx = dst_typed_segs[idx]
                            all_reps.append((s, e, fw))
                    all_reps.sort(key=lambda x: x[0], reverse=True)
                    for s, e, fw_r in all_reps:
                        dst = dst[:s] + fw_r + dst[e:]
                    replaced = True

                if replaced:
                    continue

                # ── 阶段②：合并所有待替换子块为一个串，搜索完整 hw 词块 ─────────────
                combined_matches = find_exact_hw_blocks(combined_hw, dst)
                # 含字母的组合（L 或 L+D）：允许多次出现，全部替换，不告警歧义
                combined_has_alpha = any(c.isalpha() for c in combined_hw)
                if DEBUG_FULLWIDTH:
                    print(f"  [DBG ②] combined_hw={combined_hw!r} has_alpha={combined_has_alpha} "
                          f"matches={len(combined_matches)} dst={dst!r}")
                if len(combined_matches) == 1:
                    m = combined_matches[0]
                    dst = dst[:m.start()] + combined_fw + dst[m.end():]
                elif len(combined_matches) > 1:
                    if combined_has_alpha:
                        # 含字母的组合：全部替换（不告警）
                        for m in reversed(combined_matches):
                            dst = dst[:m.start()] + combined_fw + dst[m.end():]
                    elif src.count(combined_fw) == len(combined_matches):
                        # 纯数字，但 dst 出现次数 == src 中该全角块出现次数：全部替换，不告警
                        for m in reversed(combined_matches):
                            dst = dst[:m.start()] + combined_fw + dst[m.end():]
                    else:
                        # 纯数字：歧义，告警
                        warnings.add(
                            f"全角转换歧义：{combined_hw}→{combined_fw}"
                            f"(出现{len(combined_matches)}次)"
                        )
                else:
                    # ── 阶段③：子块独立降级替换 ──────────────────────────────────
                    # 合并匹配也找不到时，对每个子块单独尝试：
                    # L 型：有匹配就替换（字母通常唯一，即使多次也全替换）
                    # D 型：仅唯一匹配非混合词段才替换，避免误匹配
                    dst_typed_segs3 = get_dst_typed_segs(dst)
                    partial_reps = []
                    for fw_s, hw_s, typ_s in need_replace:
                        idxs3 = find_typed_segs(hw_s, typ_s, dst_typed_segs3)
                        if typ_s == 'L' and len(idxs3) >= 1:
                            for idx3 in idxs3:
                                _, s3, e3, _, _mx3 = dst_typed_segs3[idx3]
                                partial_reps.append((s3, e3, fw_s))
                        elif typ_s == 'D' and len(idxs3) == 1:
                            _, s3, e3, _, _mx3 = dst_typed_segs3[idxs3[0]]
                            partial_reps.append((s3, e3, fw_s))
                    if partial_reps:
                        if DEBUG_FULLWIDTH:
                            print(f"  [DBG ③] partial_reps={partial_reps} dst={dst!r}")
                        partial_reps.sort(key=lambda x: x[0], reverse=True)
                        for s3, e3, fw_r in partial_reps:
                            dst = dst[:s3] + fw_r + dst[e3:]
                    # else: 所有阶段均无匹配 → 静默跳过

            # ── 带圈数字缺失告警（排除已被数字串吸收的） ───────────────────────────
            # 补充检查：对仍未核算的带圈数字，按 sub_blocks 顺序组成连续 C-组，
            # 查看其 hw 形式是否以完整 hw 词块出现在译文中（如 ①② → "12" 独立存在）。
            # 这处理了纯 C 块（fw_block 中无任何 L/D 子块）以及相邻 LD 组后的孤立 C 的情形。
            unaccounted = [c for c, ok in circled_pending.items() if not ok]
            if unaccounted:
                unaccounted_set = set(unaccounted)
                flat_chars = [c for typ, chars in sub_blocks if typ == 'C' for c in chars]
                i = 0
                while i < len(flat_chars):
                    c = flat_chars[i]
                    if c not in unaccounted_set or circled_pending.get(c, True):
                        i += 1
                        continue
                    # 找连续的未核算带圈数字
                    j = i
                    while (j < len(flat_chars)
                           and flat_chars[j] in unaccounted_set
                           and not circled_pending.get(flat_chars[j], True)):
                        j += 1
                    run = flat_chars[i:j]
                    run_fw = "".join(run)          # 原始带圈字符串，如 ①②
                    run_hw = "".join(fw_to_hw(c) for c in run)  # hw 形式，如 12
                    matches = find_exact_hw_blocks(run_hw, dst)
                    if DEBUG_FULLWIDTH:
                        print(f"  [DBG 补充检查] run={run_fw!r} hw={run_hw!r} "
                              f"matches={[m.group() for m in matches]} dst={dst!r}")
                    if len(matches) == 1:
                        # 唯一匹配 → 替换 hw 为原始带圈字符，并标记为已核算
                        m = matches[0]
                        dst = dst[:m.start()] + run_fw + dst[m.end():]
                        for c in run:
                            circled_pending[c] = True
                        if DEBUG_FULLWIDTH:
                            print(f"  [DBG 补充检查] 替换 {run_hw!r}→{run_fw!r} → dst={dst!r}")
                    elif len(matches) > 1:
                        # 多处匹配 → 歧义，仅标记为已核算（不替换），不告警缺失
                        for c in run:
                            circled_pending[c] = True
                        if DEBUG_FULLWIDTH:
                            print(f"  [DBG 补充检查] 歧义({len(matches)}次)，跳过替换")
                    # else len==0: 真正缺失，保持 False → 下方告警
                    i = j

            missing_circled = "".join(c for c, ok in circled_pending.items() if not ok)
            if missing_circled:
                warnings.add(f"带圈数字缺失：{missing_circled}")

        return dst, warnings


    # ═══════════════════════════════════════════════════════════════════════════
    # 5. 标点数量检查与修复（通用）
    # ═══════════════════════════════════════════════════════════════════════════
    @classmethod
    def check(cls, src: str, dst: str, key: str, alts: tuple) -> tuple[bool, bool]:
        n_src_key = src.count(key)
        n_src_alt = sum(src.count(a) for a in alts)
        n_dst_key = dst.count(key)
        n_dst_alt = sum(dst.count(a) for a in alts)
        # src 有此符号，且 src 中 key 与 alt 数量不等（否则无法判断哪个正确）
        # 且 dst 中 key 数量少于 src
        needs_fix = n_src_key > 0 and n_src_key != n_src_alt and n_src_key > n_dst_key
        # 且 dst 中 key+alt 总量恰好等于 src 中 key 的数量（一一对应才能替换）
        can_fix = needs_fix and n_src_key == n_dst_key + n_dst_alt
        return needs_fix, can_fix

    @classmethod
    def apply_replace(cls, dst: str, key: str, alts: tuple) -> str:
        for a in alts:
            dst = dst.replace(a, key)
        return dst

    def apply_fix_rules(self, src: str, dst: str, rules: dict,
                        always_warn: bool = False) -> tuple[str, set]:
        """
        通用规则应用：遍历 rules，对每条规则做数量检查和替换。
        always_warn=True 时忽略 NO_WARN_BASIC（用于成对符号）。
        """
        missing = set()
        for key, alts in rules.items():
            # 只替换 src 中不存在的 alt 形式
            effective_alts = tuple(a for a in alts if a not in src)
            needs, can = self.check(src, dst, key, effective_alts)
            if needs:
                if can:
                    dst = self.apply_replace(dst, key, effective_alts)
                elif self.检查数量一致 and (always_warn or key not in NO_WARN_BASIC):
                    missing.add(key)
        return dst, missing

    # ═══════════════════════════════════════════════════════════════════════════
    # 主修复入口
    # ═══════════════════════════════════════════════════════════════════════════
    def fix(self, src: str, dst: str) -> tuple[str, set]:
        warnings = set()

        # 1. 句首/句尾成对引号
        dst = self.match_outer_quote(src, dst)

        # 2. 原文成对符号 alt 形式替换（须在 fix_inline_quotes 之前）
        #    处理原文中成对符号在译文里被换成其他形式的情况
        #    例：原文 『鉄火』 → 译文 '铁火' 或 《铁火》 → 修正为 『铁火』
        dst, w = self.fix_paired_symbols(src, dst, self.检查数量一致)
        warnings |= w

        # 3. 句中短语引号转换（含译文新增引号 → 日式）
        dst = self.fix_inline_quotes(src, dst)

        # 4. 非成对基本标点修复
        dst, w = self.apply_fix_rules(src, dst, self.RULE_BASIC, always_warn=False)
        warnings |= w

        # 5. 换行符处理
        dst, w = self._fix_linebreaks(src, dst)
        warnings |= w

        # 6. 全角字符按词块转换（歧义时告警）
        if self.全角转换:
            dst, w = self.fix_fullwidth_chars(src, dst)
            warnings |= w

        return dst, warnings

    # ═══════════════════════════════════════════════════════════════════════════
    # GalTransl 插件接口
    # ═══════════════════════════════════════════════════════════════════════════
    def gtp_init(self, plugin_conf: dict, project_conf: dict):
        self.pname = plugin_conf["Core"].get("Name", "")
        settings = plugin_conf.get("Settings", {})
        self.source_cjk = settings.get("source_cjk", True)
        self.检查数量一致 = settings.get("检查数量一致", True)
        self.全角转换 = settings.get("全角转换", True)
        LOGGER.info(f"[{self.pname}] fixer_common_punctuation·启动！")
        LOGGER.info(f"[{self.pname}] source_cjk:{self.source_cjk}")
        LOGGER.info(f"[{self.pname}] 检查数量一致:{self.检查数量一致}")
        LOGGER.info(f"[{self.pname}] 全角转换:{self.全角转换}")

    def before_dst_processed(self, tran: CSentense) -> CSentense:
        tran.post_zh, missing = self.fix(tran.post_jp, tran.post_zh)
        if missing:
            if tran.problem:
                tran.problem += ", "
            tran.problem += (
                "标点修复 "
                + ",".join(json.dumps(i, ensure_ascii=False)[1:-1] for i in missing)
                + " 无法修复"
            )
        return tran


# ── 本地测试 ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    class _FakeLogger:
        def info(self, msg): print("[INFO]", msg)
        def warning(self, msg): print("[WARN]", msg)

    try:
        from GalTransl import LOGGER
        from GalTransl.CSentense import CSentense
    except ImportError:
        LOGGER = _FakeLogger()

        class CSentense:
            def __init__(self, src):
                self.post_jp = src
                self.post_zh = ""
                self.problem = ""

    coder = text_common_punctuation_fixer()
    coder.gtp_init({"Core": {}, "Settings": {'全角转换':True}}, {})

    test_cases = [
        # (描述, src, dst_input)
        ("换行后空格补足",
         "メメルを…\n  それまでは絶対…\n  神殿には戻らない…っ。",
         "必须找到梅梅尔…\n在那之前绝对…\n不回神殿…"),

        ("全角字母/数字/带圈数字自动转换",
         "ＡＢＣ１２３①②",
         "ABC123\u2460\u2461"),   # ①② 已在 dst 中，只有 Ａ-Ｚ 和 １-３ 需要转

        ("字母数字转换测试1（带圈后置→数字合并）",
         "ＡＢＣ１２３④⑤",
         "ABC12345"),   # ④⑤→45 被译者并入数字段，期望：ＡＢＣ１２３④⑤，无告警

        ("字母数字转换测试1b（带圈前置→字母合并）",
         "④⑤ＡＢＣ",
         "45ABC"),   # ④⑤→45 被译者并入字母词块前段，期望：④⑤ＡＢＣ，无告警

        ("字母数字转换测试1c（带圈前置→数字合并）",
         "④⑤１２３",
         "45123"),   # ④⑤→45 被译者并入数字段前，期望：④⑤１２３，无告警

        ("字母数字转换测试2（纯带圈块→独立 hw 词块）",
         "①②测试２",
         "12测试2"),   # ①②→12 作为独立词块在 dst 中，期望：①②测试２，无告警

        ("纯字母多次出现→全部替换",
         "モビィのＭＰを使って最大ＭＰの10%",
         "最大MP的10%"),  # MP 出现 2 次，期望全部 → ＭＰ，无告警

        ("字母+数字组合多次出现→全部替换",
         "『イベント全解放（ＤＬＣ２）』の設定\n『イベント全解放（ＤＬＣ２）』を行いますか",
         "『全事件解锁（DLC2）』的设置"),  # DLC2 出现 2 次，期望全部 → ＤＬＣ２

        ("换行数量变动不告警",
         "line1\nline2\nline3",
         "line1\nline2"),   # src 有 2 个 \n, dst 只有 1 个 → 不告警


        ("带圈数字缺失告警",
         "①②项目",
         "1项目2"),   # 译文丢失了①②，应告警

        ("带圈数字已在译文→不告警",
         "①②项目",
         "①②项目"),   # 全角形式已在译文，跳过

        ("句首句尾引号套用",
         "「こんにちは」",
         "你好"),

        ("句中短语引号（原文has「」→ dst引号转为 『』）",
         "彼女は「好き」と言った。",
         '她说"喜欢"。'),

        ("句中短语引号（原文has「」→ dst引号转为 『』）",
         "彼女は「好き」と言った。",
         '她说“喜欢”。'),

        ("译文新增双引号（原文无任何日式引号→ 转为 『』）",
         "こんにちは",
         '你"好"啊'),

        ("译文新增单引号（原文无任何日式引号→ 转为 「」）",
         "こんにちは",
         "你'好'啊"),

        (r"\r\n 换行类型修正",
         "line1\r\nline2",
         "line1\nline2"),

        ("混用换行符告警",
         "a\r\nb\nc",
         "a\nb\nc"),

        ("成对符号alt替换（『』→单引号）",
         "赤い肌となれば、族長の『鉄火』か",
         "既然是红皮肤，那就是族长'铁火'吗"),

        ("成对符号alt替换（『』→《》）",
         "族長の『鉄火』か",
         "族长《铁火》吗"),

        ("成对符号alt替换（「」和『』各一，译文均用《》）",
         "彼女は「好き」と言い、『嫌い』とも言った。",
         "她说‘喜欢’，也说“讨厌”。"),

         ("TEST",
        "日常クエストは、ＤＬＣ『it's a Wonderful days』で\n実装されたデイリークエスト機能だ。",
        "日常任务是DLC『It's a Wonderful Days』中\n实装的每日任务功能。"),

        ("TEST2",
        "ヒントに関しては、ページ２では『小さな訪問者』の範囲の\nヒントしか表示されない。\n　また、全解放スイッチは別扱いなので、ページ２の全解放スイッチで\n開いたイベントも、ページ３には反映されない。",
        "关于提示，第2页仅会显示『小小访问者』范围内的\n提示。\n　此外，由于全解锁开关是分开处理的，通过第2页全解锁开关\n开启的事件，不会反映在第3页中。"
        ),

        ("TEST3",
        "『鉄火』との連絡役か。\n　面識があるって言っても、森のオークは凶暴だから気を付けてな",
        "“铁火”的联络员吗。\n　虽说见过面，但森林里的兽人很凶暴，要多加小心哦。"),

        ("TEST4",
        "でもミリス様も、ちゅぱ……クロシェがされてるの、いいなって\n思ってるんですよね？",
        "但米莉丝大人，啾……也在想\n“要是能像克洛谢那样被对待就好了”对吧？",),


        ("方括号修正（原文半角[]→译文全角［］应修正）",
        "[発動回数3]を消費して",
        "消费［发动次数3］"),

        ("方括号修正（原文全角［］→译文半角[]应修正）",
        "［発動回数3］を消費して",
        "消费[发动次数3]"),

        ("括号修正",
        "(ぷるぷる……)",
        "（噗噜噗噜……）"),
        ("括号修正2",
        "（噗噜噗噜……）",
        "(ぷるぷる……)",),

        ("带参数测试1",
         "ＡＢＣ１２测试v12",
         "v12测试ABC"),   # ④⑤→45 被译者并入数字段，期望：ＡＢＣ１２３④⑤，无告警

        ("带参数测试2",
         "ＡＢＣ１２测试v12",
         "v12测试ABC和12"),  # ④⑤→45 被译者并入数字段，期望：ＡＢＣ１２３④⑤，无告警
    ]

    for desc, src, dst_in in test_cases:
        s = CSentense(src)
        s.post_jp = src
        s.post_zh = dst_in
        s = coder.before_dst_processed(s)
        print(f"[{desc}]")
        print(f"  SRC : {repr(src)}")
        print(f"  IN  : {repr(dst_in)}")
        print(f"  OUT : {repr(s.post_zh)}")
        if s.problem:
            print(f"  WARN: {s.problem}")
        print()
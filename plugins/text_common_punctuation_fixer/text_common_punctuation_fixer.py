import json
import re

from GalTransl import LOGGER
from GalTransl.CSentense import CSentense
from GalTransl.GTPlugin import GTextPlugin

SYMBOL_PAIRS = {
    "「": "」｣",
    "｢": "｣」",
    "『": "』",
    "“": "”",
    "（": "）)",
    "(": "）)",
    "【": "】",
    "\"": "\"",
}

REVERSE_SYMBOLS = {r: left for left, rights in SYMBOL_PAIRS.items() for r in rights}


class text_common_punctuation_fixer(GTextPlugin):

    # 数量一致才执行的规则 - A区
    RULE_SAME_COUNT = {
        # "　": (" ", ),                                      # 全角空格和半角空格之间的转换
        "：": (":", ),
        "・": ("·", ),
        "？": ("?", ),
        "！": ("!", ),
        "\u2014": ("\u002d", "\u2015"),                     # 破折号之间的转换，\u002d = - ，\u2014 = ― ，\u2015 = —
        "\u2015": ("\u002d", "\u2014"),                     # 破折号之间的转换，\u002d = - ，\u2014 = ― ，\u2015 = —
        "＜": ("<", "《"),
        "＞": (">", "》"),
        "「": ("‘", "“", "『", "《"),
        "」": ("’", "”", "』", "》"),
        "『": ("‘", "“", "「", "《"),
        "』": ("’", "”", "」", "》"),
        "（": ("(", "「", "‘", "“"),
        "）": (")", "」", "’", "”"),
        "【": ("‘", "“"),
        "】": ("’", "”"),
        "＠": ('@',),
        "〇": ("○",),
    # 数量一致才执行的规则 - B区
        # " ": ("　", ),                                      # 全角空格和半角空格之间的转换
        ":": ("：", ),
        "·": ("・", ),
        "?": ("？", ),
        "!": ("！", ),
        "\u002d": ("\u2014", "\u2015"),                     # 破折号之间的转换，\u002d = - ，\u2014 = ― ，\u2015 = —
        "<": ("＜", "《"),
        ">": ("＞", "》"),
        "(": ("（", "「", "‘", "“"),
        ")": ("）", "」", "’", "”"),
        "$": ("＄",),
    }

    RE_YINHAO_STRING = re.compile(r"([\"'])([^\"'｢「」｣『』“”（()）【】]*?)\1")
    RE_LINEBREAK = re.compile(r'\n＞?[ 　]*')
    def __init__(self) -> None:
        super().__init__()

    @classmethod
    def match_quote(cls, src, dst):
        def is_matched_pair(left, right):
            return left and left in SYMBOL_PAIRS and right and right in SYMBOL_PAIRS[left]

        if not src or not dst:
            return dst
        src = src.strip(' ')
        # 识别 src 的引号
        src_left = src[0] if src and src[0] in SYMBOL_PAIRS else ''
        src_right = src[-1] if src and src[-1] in REVERSE_SYMBOLS else ''

        # 识别 dst 的引号
        dst_left = dst[0] if dst[0] in SYMBOL_PAIRS else ''
        dst_right = dst[-1] if dst[-1] in REVERSE_SYMBOLS else ''

        # 判断是否成对
        src_has_pair = is_matched_pair(src_left, src_right)
        dst_has_pair = is_matched_pair(dst_left, dst_right)

        # 如果都没有成对引号，就不做处理
        if not src_has_pair and not dst_has_pair:
            return dst

        dst_core = dst
        # 去掉现有引号包裹
        if dst_left and dst_right and dst_left in SYMBOL_PAIRS and dst_right in REVERSE_SYMBOLS:
            if dst_right in SYMBOL_PAIRS[dst_left]:
                dst_core = dst[1:-1]
        elif dst_left and dst_left in SYMBOL_PAIRS:
            dst_core = dst[1:]
        elif dst_right and dst_right in REVERSE_SYMBOLS:
            dst_core = dst[:-1]

        # 情况1：src 有首尾引号对 → 套用 src 引号
        if src_has_pair:
            fixed_right = SYMBOL_PAIRS[src_left][0]
            return src_left + dst_core + fixed_right

        # 情况2：src 无引号，但 dst 有对 → 去掉 dst 引号
        if not src_left and not src_right and dst_has_pair:
            return dst_core

        # 情况3：src 只有左引号，dst 有对 → 用 src 左引号 + core
        if src_left and not src_right and dst_has_pair:
            return src_left + dst_core

        # 情况4：src 只有右引号，dst 有对 → 用 core + src 右引号
        if not src_left and src_right and dst_has_pair:
            return dst_core + src_right

        return dst

    def fix(self, src: str, dst: str, is_cjk: bool = True) -> tuple[str, set[str]]:

        # 去掉首尾错误的括号/引号
        dst = self.match_quote(src, dst)

        # 处理正则替换
        if not self.RE_YINHAO_STRING.search(src):
            symbols = '『』' if '『' not in dst else '「」'
            dst = self.RE_YINHAO_STRING.sub(rf'{symbols[0]}\2{symbols[1]}', dst)
        # 处理换行空格
        src_linebreaks = self.RE_LINEBREAK.findall(src)
        if src_linebreaks:
            min_break = min(src_linebreaks, key=len)
            if len(min_break) > 1:
                dst = self.RE_LINEBREAK.sub(lambda m: m.group() if len(m.group()) >= len(min_break) else min_break, dst)

        dst, missing = self.apply_fix_rules(src, dst, self.RULE_SAME_COUNT)

        count_r = src.count('\r\n')
        count_n = src.count("\n")
        count_r_dst = dst.count('\r\n')
        count_n_dst = dst.count("\n")
        if count_r and count_r_dst != count_r:
            if count_r == count_n:
                dst = dst.replace('\r\n', '\n').replace('\n', '\r\n')
            else:
                missing.add(f"换行符\r\n错误")
        return dst, missing

    # 检查
    @classmethod
    def check(cls, src: str, dst: str, key: str, value: tuple) -> tuple[bool, bool]:
        num_s_x = src.count(key)
        num_s_y = sum(src.count(t) for t in value)
        num_t_x = dst.count(key)
        num_t_y = sum(dst.count(t) for t in value)

        # 首先，原文中的目标符号的数量应大于零，否则表示没有需要修复的标点
        # 然后，原文中目标符号和错误符号的数量不应相等，否则无法确定哪个符号是正确的
        # 然后，原文中的目标符号的数量应大于译文中的目标符号的数量，否则表示没有需要修复的标点
        # 最后，如果原文中目标符号的数量等于译文中目标符号与错误符号的数量之和，则判断为需要修复
        # 是否需要修复
        needs_fix = num_s_x > 0 and num_s_x != num_s_y and num_s_x > num_t_x
        # 是否可以修复
        can_fix = needs_fix and num_s_x == num_t_x + num_t_y
        return needs_fix, can_fix

    # 应用修复规则
    def apply_fix_rules(self, src: str, dst: str, rules: dict) -> tuple[str, set[str]]:
        missing = set()
        for key, value in rules.items():
            filtered_value = tuple([t for t in value if t not in src])
            need_repair, can_repair = self.check(src, dst, key, filtered_value)
            if need_repair:
                if can_repair:
                    dst = self.apply_replace_rules(dst, key, filtered_value)
                elif self.检查数量一致:
                    missing.add(key)
        return dst, missing

    # 应用替换规则
    @classmethod
    def apply_replace_rules(cls, dst: str, key: str, value: tuple) -> str:
        for t in value:
            dst = dst.replace(t, key)

        return dst


    def gtp_init(self, plugin_conf: dict, project_conf: dict):
        self.pname = plugin_conf["Core"].get("Name", "")
        settings = plugin_conf["Settings"]

        self.source_cjk = settings.get("source_cjk", True)
        self.检查数量一致 = settings.get("检查数量一致", True)
        LOGGER.info(f"[{self.pname}] fixer_common_punctuation·启动！")
        LOGGER.info(f"[{self.pname}] source_cjk:{settings.get('source_cjk', True)}")
        LOGGER.info(f"[{self.pname}] 检查数量一致:{settings.get('检查数量一致', True)}")

    def before_dst_processed(self, tran: CSentense) -> CSentense:
        tran.post_zh, missing = self.fix(tran.post_jp, tran.post_zh, self.source_cjk)
        if missing:
            if tran.problem:
                tran.problem += ", "
            tran.problem += f"标点修复 {','.join([json.dumps(i, ensure_ascii=False)[1:-1] for i in missing])} 无法修复"
        return tran


if __name__ == '__main__':
    coder = text_common_punctuation_fixer()
    coder.gtp_init({'Core': {}, 'Settings': {}}, {})
    lines = {
    #    "その艶やかな姿に\\N[3]の獣心がそそられた。\n\\N[3]は少女の動きに合わせて腰を突き上げはじめる。",
        "メメルを…メメルを見つけ出さなきゃ。\n  それまでは絶対…\n  神殿には戻らない…っ。":
            "必须找到梅梅尔…\n在那之前绝对…\n不回神殿…",
    }
    for post_jp, post_zh in lines.items():
        s = CSentense(post_jp)
        s.post_jp = post_jp
        s.post_zh = post_zh
        s = coder.before_dst_processed(s)
        print('post_jp', s.post_jp)
        print('post_zh', s.post_zh)
        print(s.problem)
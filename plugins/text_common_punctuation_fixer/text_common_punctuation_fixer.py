import json
import re

from GalTransl import LOGGER
from GalTransl.CSentense import CSentense
from GalTransl.GTPlugin import GTextPlugin


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

    RE_YINHAO_STRING = re.compile(r"([\"'])([^\"'｢「」｣『』“”（()）【】]*?)\1")
    RE_LINEBREAK = re.compile(r'\n[ 　]*')
    def __init__(self) -> None:
        super().__init__()

    # 检查并替换
    @classmethod
    def fix(cls, src: str, dst: str, is_cjk: bool = True) -> tuple[str, set[str]]:
        def get_symbol_pair(text):
            if text[0] in cls.SYMBOL_PAIRS:
                right_symbol = cls.SYMBOL_PAIRS[text[0]]
                if text[-1] in right_symbol:
                    return text[0], text[-1]
            return None

        # 去掉首尾错误的括号/引号
        dst_symbol_pair = get_symbol_pair(dst)
        if dst_symbol_pair is not None:
            src_symbol_pair = get_symbol_pair(src)
            if src_symbol_pair is None:
                dst = dst[1:-1]
            elif src_symbol_pair != dst_symbol_pair:
                dst = f"{src_symbol_pair[0]}{dst[1:-1]}{src_symbol_pair[1]}"

        dst, missing = cls.apply_fix_rules(src, dst, cls.RULE_SAME_COUNT)

        # 处理正则替换
        if not cls.RE_YINHAO_STRING.search(src):
            symbols = '『』' if '「' in dst else '「」'
            dst = cls.RE_YINHAO_STRING.sub(rf'{symbols[0]}\2{symbols[1]}', dst)
        # 处理换行空格
        src_linebreaks = cls.RE_LINEBREAK.findall(src)
        if src_linebreaks:
            min_break = min(src_linebreaks, key=len)
            if len(min_break) > 1:
                dst = cls.RE_LINEBREAK.sub(lambda m: m.group() if len(m.group()) >= len(min_break) else min_break, dst)

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
    @classmethod
    def apply_fix_rules(cls, src: str, dst: str, rules: dict) -> tuple[str, set[str]]:
        missing = set()
        for key, value in rules.items():
            need_repair, can_repair = cls.check(src, dst, key, value)
            if need_repair:
                if can_repair:
                    dst = cls.apply_replace_rules(dst, key, value)
                else:
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

        LOGGER.info(f"[{self.pname}] fixer_common_punctuation·启动！")
        LOGGER.info(f"[{self.pname}] source_cjk:{settings.get('source_cjk', True)}")

    def before_dst_processed(self, tran: CSentense) -> CSentense:
        tran.post_zh, missing = self.fix(tran.post_jp, tran.post_zh, self.source_cjk)
        if missing:
            if tran.problem:
                tran.problem += ", "
            tran.problem += f"标点修复 {','.join([json.dumps(i, ensure_ascii=False)[1:-1] for i in missing])} 无法修复"
        return tran

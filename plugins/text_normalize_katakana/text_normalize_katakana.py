from GalTransl import LOGGER
from GalTransl.CSentense import CSentense
from GalTransl.GTPlugin import GTextPlugin
import re

class text_normalize_katakana(GTextPlugin):

    def gtp_init(self, plugin_conf: dict, project_conf: dict):
        self.pname = plugin_conf["Core"].get("Name", "")

        LOGGER.info(f"[{self.pname}] 半角假名转换功能已启用。")
        # 半角片假名字符到全角片假名字符的对照表
        self.half_to_full_katakana = str.maketrans(
            'ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝﾞﾟ',
            'ヲァィゥェォャュョッーアイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン゛゜'
        )

        # 只匹配半角片假名的正则表达式
        self.halfwidth_katakana_pattern = re.compile(r'[\uFF65-\uFF9F]+')

    # 只替换半角片假名为全角片假名，不影响其他字符
    def replace_halfwidth_to_fullwidth(self, text):
        return self.halfwidth_katakana_pattern.sub(lambda x: x.group().translate(self.half_to_full_katakana), text)

    # 合并全角片假名及其跟随的浊音符号或半浊音符号
    def combine_diacritics(self, text):
        # 将浊音符号(゛)或半浊音符号(゜)与前面的假名合并
        combined_text = re.sub(r'([カ-ヺ])゛', lambda m: chr(ord(m.group(1)) + 1), text)  # 合并带浊音符号的字符
        combined_text = re.sub(r'([ハ-ポ])゜', lambda m: chr(ord(m.group(1)) + 2), combined_text)  # 合并带半浊音符号的字符
        return combined_text

    def before_src_processed(self, tran: CSentense) -> CSentense:
        if self.halfwidth_katakana_pattern.search(tran.post_jp):
            converted_text = self.replace_halfwidth_to_fullwidth(tran.post_jp)
            final_text = self.combine_diacritics(converted_text)
            tran.post_jp = final_text
        return tran
    def gtp_final(self):
        pass
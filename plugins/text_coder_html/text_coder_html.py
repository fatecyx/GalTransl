import json
import re
from collections import Counter

from GalTransl import LOGGER
from GalTransl.CSentense import CSentense
from GalTransl.GTPlugin import GTextPlugin


class text_coder_html(GTextPlugin):
    brackets = ["【】", "()", "《》"]
    re_color = re.compile(r'<color=.+?>(.*?)</color>')
    re_br = re.compile(r'<br\s*/?>')
    color_pattern = re.compile(r'<color=(#.*?)>(.*?)</color>')

    def gtp_init(self, plugin_conf: dict, project_conf: dict):
        """
        This method is called when the plugin is loaded.在插件加载时被调用。
        :param plugin_conf: The settings for the plugin.插件yaml中所有设置的dict。
        :param project_conf: The settings for the project.项目yaml中common下设置的dict。
        """
        self.pname = plugin_conf["Core"].get("Name", "")

        LOGGER.info(f"[{self.pname}] text_html_coder·启动！")

    def before_src_processed(self, tran: CSentense) -> CSentense:
        """
        This method is called before the source sentence is processed.
        在post_jp没有被去除对话框和字典替换之前的处理，如果这是第一个插件的话post_jp=原始日文。
        :param tran: The CSentense to be processed.
        :return: The modified CSentense."""

        # 找到一个未在原文中出现的括号符号
        for bracket in self.brackets:
            if bracket[0] not in tran.pre_jp and bracket[1] not in tran.pre_jp:
                open_bracket, close_bracket = bracket[0], bracket[1]
                break
        else:
            raise ValueError("No available bracket symbols found in the text.")

        # 替换 <color=#ff0000>...</color> 为 选择的括号符号
        tran.post_jp = self.re_color.sub( f'{open_bracket}\\1{close_bracket}', tran.post_jp)

        # 替换 <br>, <br/>, <br /> 为 \n
        tran.post_jp = self.re_br.sub('\n', tran.post_jp)

        return tran

    def after_src_processed(self, tran: CSentense) -> CSentense:
        """
        This method is called after the source sentence is processed.
        在post_jp已经被去除对话框和字典替换之后的处理。
        :param tran: The CSentense to be processed.
        :return: The modified CSentense.
        """
        return tran

    def before_dst_processed(self, tran: CSentense) -> CSentense:
        """
        This method is called before the destination sentence is processed.
        在post_zh没有被恢复对话框和字典替换之前的处理，如果这是第一个插件的话post_zh=原始译文。
        :param tran: The CSentense to be processed.
        :return: The modified CSentense.
        """
        problems = [tran.problem]
        # 找到一个未在原文中出现的括号符号
        for bracket in self.brackets:
            if bracket[0] not in tran.pre_jp and bracket[1] not in tran.pre_jp:
                open_bracket, close_bracket = bracket[0], bracket[1]
                re_bracket = re.compile(rf'{re.escape(open_bracket)}(.*?){re.escape(close_bracket)}')
                break
        else:
            raise ValueError("No available bracket symbols found in the text.")

        original_matches = self.color_pattern.findall(tran.pre_jp)

        for color in original_matches:
            tran.post_zh = re_bracket.sub(rf'<color={color}>\1</color>',
                                 tran.post_zh, count=1)
        after_matches = self.color_pattern.findall(tran.post_zh)
        if len(original_matches) != len(after_matches):
            problems.append("丢失颜色标签（数量）")
        elif set(original_matches) != set(after_matches):
            problems.append("丢失颜色标签（颜色）")
        tran.post_zh = tran.post_zh.replace('\n', '<br>')
        tran.problem = ", ".join(problems)
        return tran

    def after_dst_processed(self, tran: CSentense) -> CSentense:
        """
        This method is called after the destination sentence is processed.
        在post_zh已经被恢复对话框和字典替换之后的处理。
        :param tran: The CSentense to be processed.
        :return: The modified CSentense.
        """
        return tran

    def gtp_final(self):
        """
        This method is called after all translations are done.
        在所有文件翻译完成之后的动作，例如输出提示信息。
        """
        pass

if __name__ == '__main__':
    coder = text_html_coder()
    coder.gtp_init({'Core': {}, 'Settings': {}}, {})
    lines = [
    #    "その艶やかな姿に\\N[3]の獣心がそそられた。\n\\N[3]は少女の動きに合わせて腰を突き上げはじめる。",
    "『<color=#ff0000>＜パンチ＞</color>が一番ダメージが低く、次に<color=#00ff00>＜キック＞</color>、",
        "测试数据<br>测试数据2"
             ]
    for line in lines:
        s=coder.before_src_processed(CSentense(line))
        # , s.post_jp, s.pre_zh, s.post_zh
        print('pre_jp', s.pre_jp)
        print('post_jp', s.post_jp)
        print('pre_zh', s.pre_zh)
        print('post_zh', s.post_zh)
        s.pre_zh = s.post_jp
        s.post_zh = s.post_jp
        s = coder.before_dst_processed(s)
        print('pre_jp', s.pre_jp)
        print('post_jp', s.post_jp)
        print('pre_zh', s.pre_zh)
        print('post_zh', s.post_zh)
        print(s.problem)
        if s.post_zh == line:
            print("Success!!\n")
        else:
            print("Failed!!\n")
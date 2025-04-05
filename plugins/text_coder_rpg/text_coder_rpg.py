import json
import re
from collections import Counter

from GalTransl import LOGGER
from GalTransl.CSentense import CSentense
from GalTransl.GTPlugin import GTextPlugin


class text_coder_rpg(GTextPlugin):

    re_value = re.compile(r'\\([a-zA-Z]{1,6})\[([^\[\]]+)\]')
    re_reserved = re.compile(r'\\([VvNn])\[(\d+)\]|(%)(\d+)')
    re_bracket = re.compile(r'\[[^\[\]]*?\]')
    re_color = re.compile(r'(\\[Cc]\[\d+\])(.+?)(\\[Cc](?:\[0\]|(?!\[)))', re.DOTALL)  # 1:前标签，2：文本，3；后标签
    re_yinhao = re.compile(r"“(.+?)”", re.DOTALL)

    CODE_PATTERN_NON_EN = (
        r"if\(.{0,5}[vs]\[\d+\].{0,10}\)",  # if(!s[982]) if(v[982]) if(v[982] >= 1)
        r"en\(.{0,5}[vs]\[\d+\].{0,10}\)",  # en(!s[982]) en(v[982] >= 1)
        r"[/\\][a-zA-Z]{1,5}<[^\<\>]{0,10}>",  # /C<y> /C<1> \FS<xy> \FS<12>
        r"[/\\][a-zA-Z]{1,5}\[[^\[\]]{0,10}\]",  # /C[x] /C[1] \FS[xy] \FS[12]
        r"[/\\][a-zA-Z]{1,5}(?=<.{0,10}>)",  # /C<非数字非字母> 等
        r"[/\\][a-zA-Z]{1,5}(?=\[.{0,10}\])",  # /C[非数字非字母] 等
    )
    CODE_PATTERN_COMMON = (
        r"\\fr",  # 重置文本的改变
        r"\\fb",  # 加粗
        r"\\fi",  # 倾斜
        r"\\\{(?!color)",  # 放大字体 \{
        r"\\\}",  # 缩小字体 \}
        r'\\gold',
        r"\\g",  # 显示货币 \G
        r"\\\$",  # 打开金币框 \$
        r"(?:\\\.)+",  # 等待0.25秒 \.
        r"\\\|",  # 等待1秒 \|
        r"\\!",  # 等待按钮按下 \!
        r"\\#",  # \#
        r"\\>",  # 在同一行显示文字 \>
        r"\\\^",  # 显示文本后不需要等待 \^
        r"\\\\<br>",  # 换行符 \\<br>
        r"<br>",  # 换行符 <br>
        r"\\_",
        r"\\[A-Za-z](?![A-Za-z])",
        r"\\js<.+>",
        r"\\${[^{]+?}",
        r"\\SCRIPT{.+?}",
        r'\\DATA\[.+?\]'
    )

    CODE_PATTERN_SIGNS = (
        #r'[★☆♥♡■□]{3,}',
        r'(?m:^[ー\-\—\+\=＝★☆♥♡■□]{3,}$)',
    )

    CODE_PATTERN_OTHERS = (
        r'@\d+',
        r'%\d+',
        r'↑{3,}',
        r'↓{3,}'
    )

    def gtp_init(self, plugin_conf: dict, project_conf: dict):
        """
        This method is called when the plugin is loaded.在插件加载时被调用。
        :param plugin_conf: The settings for the plugin.插件yaml中所有设置的dict。
        :param project_conf: The settings for the project.项目yaml中common下设置的dict。
        """
        self.pname = plugin_conf["Core"].get("Name", "")
        settings = plugin_conf["Settings"]

        self.替换rpg变量 = settings.get("替换rpg变量", True)
        self.检查脚本变量 = settings.get("检查脚本变量", True)
        self.检查中括号数量 = settings.get("检查中括号数量", True)
        self.主人公变量 = settings.get("主人公变量", None)

        LOGGER.info(f"[{self.pname}] CheckBrackets·启动！")
        LOGGER.info(f"[{self.pname}] 替换rpg变量:{settings.get('替换rpg变量', True)}")
        LOGGER.info(f"[{self.pname}] 检查脚本变量:{settings.get('检查脚本变量', True)}")
        LOGGER.info(f"[{self.pname}] 检查中括号数量:{settings.get('检查中括号数量', True)}")
        LOGGER.info(f"[{self.pname}] 主人公变量:{settings.get('主人公变量', None)}")

        code_pattern = (
                self.CODE_PATTERN_NON_EN +
                self.CODE_PATTERN_COMMON +
                self.CODE_PATTERN_OTHERS +
                self.CODE_PATTERN_SIGNS +
                (r'\s+',)
        )
        #self.re_combined = re.compile(r'((?:\\(?:[!\.\{\}\|]|[a-zA-Z]{1,6}(?:\[[^\[\]]*(?:\])|(?!\[))))|\s+|%\d+|en\([^\)]*\)|if\([^\)]*(?:\)|$))')

        self.re_combined = re.compile(rf"(\s*(?:{'|'.join(code_pattern)})\s*)", re.IGNORECASE)
        self.signs_list = ["【】", "（）", "《》"]

    def split_text_para(self, text):
        lst_head = []
        lst_content = []
        lst_tail = []
        text_head = ""
        text_tail = ""
        if (text.startswith('"') and text.endswith('"')) or (text.startswith('\'') and text.endswith('\'')):
            m = re.search(r'([\'\"]\s*)(.+?)(\s*[\'\"])', text, re.DOTALL)
            text_head = m.group(1)
            text_tail = m.group(3)
            text = m.group(2)
        lst_split = self.re_combined.split(text)
        for i, item in enumerate(lst_split):
            if not item:
                continue
            if not self.re_combined.search(item):
                if lst_tail:
                    lst_content.extend(lst_tail)
                    lst_tail = []
                lst_content.append(item)
            elif not lst_content:
                lst_head.append(item)
            else:
                lst_tail.append(item)
        # 反向遍历lst_head, 如果符合self.re_reserved，则把该段落放回lst_content，否则中断
        while lst_head:
            item = lst_head[-1]
            if self.re_reserved.fullmatch(item) or self.主人公变量 == item.strip():
                # 如果符合正则表达式，移除并放入 lst_content
                lst_content.insert(0, item)
                del lst_head[-1]
            else:
                # 如果不符合，中断遍历
                break

        while lst_tail:
            item = lst_tail[0]
            if self.re_reserved.fullmatch(item) or self.主人公变量 == item.strip():
                # 如果符合正则表达式，移除并放入 lst_content
                lst_content.append(item)
                del lst_tail[0]
            else:
                # 如果不符合，中断遍历
                break

        return text_head+"".join(lst_head), "".join(lst_content), "".join(lst_tail)+text_tail

    color_pre_pattern = re.compile(r'\\c\[(\d+)\]', re.IGNORECASE)
    color_post_pattern = re.compile(r'\{color(\d+):\s?(.*?)\}', re.DOTALL|re.IGNORECASE)
    def preprocess_color_tags(self, text):
        # 正则匹配颜色标记（不区分大小写）
        matches = list(self.color_pre_pattern.finditer(text))
        # 如果匹配存在，并且全部都在字符串的首或尾，则直接返回原始文本
        if matches and all(m.start() == 0 or m.end() == len(text) for m in matches):
            return text

        parts = []
        current_color = None
        first_color = True
        last_pos = 0
        current_tag = None
        for match in matches:
            start, end = match.span()
            # 提取当前颜色标记前的文本段
            content = text[last_pos:start]
            if content:
                if current_color is not None and (current_color != "0" or first_color):
                    parts.append(f"{{color{current_color}: {content}}}")
                    first_color = False
                else:
                    parts.append(content)  # 无颜色标记时直接保留
            # 更新当前颜色和位置
            current_color = match.group(1)
            current_tag = match.group(0)
            last_pos = end

        # 处理剩余文本（最后一个颜色标记后的内容）
        remaining = text[last_pos:]
        if remaining:
            if current_color is not None and current_color != "0":
                parts.append(f"{{color{current_color}: {remaining}}}")
            else:
                parts.append(remaining)
        # else:
        #     parts.append(current_tag)
        return ''.join(parts)

    def postprocess_color_tags(self, processed_text, original_processed, pre_jp):

        is_valid = True
        missing = []
        # 校验阶段
        if original_processed:
            original_colors = [k for k, _ in self.color_post_pattern.findall(original_processed)]
            translated_colors = [k for k, _ in self.color_post_pattern.findall(processed_text)]

            for i in range(len(original_colors)):
                if i < len(translated_colors):
                    if original_colors[i] != translated_colors[i]:
                        missing.append(f"丢失颜色标签({i}) {original_colors[i]}")
                else:
                    missing.append(f"丢失颜色标签({i}) {original_colors[i]}")
            if len(translated_colors) > len(original_colors):
                for i in range(len(original_colors), len(translated_colors)):
                    missing.append(f"多加颜色标签 {translated_colors[i]}")

            if original_colors != translated_colors:
                missing.append("颜色标签不匹配")

        lst_split = self.color_post_pattern.split(processed_text)
        final_parts = [lst_split[0]]
        for i in range(1, len(lst_split), 3):
            final_parts.append(f"\\c[{lst_split[i]}]")
            final_parts.append(lst_split[i+1])
            if lst_split[i+2] or i+2 == len(lst_split)-1:
                final_parts.append(f"\\c[0]{lst_split[i+2]}")
        if final_parts[-1] == "\\c[0]":
            if self.color_pre_pattern.findall(pre_jp)[-1] != "0":
                final_parts.pop()
        final_text = "".join(final_parts)

        return final_text, missing

    def before_src_processed(self, tran: CSentense) -> CSentense:
        """
        This method is called before the source sentence is processed.
        在post_jp没有被去除对话框和字典替换之前的处理，如果这是第一个插件的话post_jp=原始日文。
        :param tran: The CSentense to be processed.
        :return: The modified CSentense."""
        tran.plugin_used[self.pname] = {'src': tran.post_jp}

        if self.主人公变量:
            tran.post_jp = tran.post_jp.replace(self.主人公变量, '主角')
        pre_jp = self.preprocess_color_tags(tran.post_jp)
        #print(pre_jp)
        tran.plugin_used[self.pname]['split'] = self.split_text_para(pre_jp)
        pre_jp = tran.plugin_used[self.pname]['split'][1]
        if self.替换rpg变量:
            # 替换剩余控制符
            for item in self.re_combined.findall(pre_jp):
                if item.isspace():
                    continue
                # m = self.re_reserved.match(item)
                matched = [False]
                new_item = self.re_reserved.sub(lambda m: (matched.__setitem__(0, True) or ''.join(filter(None, m.groups()))),
                                         item, 1)

                #new_item = self.re_reserved.sub(lambda m: ''.join(filter(None, m.groups())), item, 1)
                if not matched[0]:
                    pre_jp = pre_jp.replace(item, '＠', 1)
                else:
                    pre_jp = pre_jp.replace(item, new_item, 1)
            tran.post_jp = pre_jp

        return tran

    def get_middle_string(self, pre_jp):
        re_color_cn = None
        lst_color = None
        if self.re_color.findall(pre_jp):
            for sign in self.signs_list:
                if not re.search(f"[{sign}]", pre_jp):
                    lst_color = self.re_color.findall(pre_jp)
                    pre_jp = self.re_color.sub(f"{sign[0]}\\2{sign[-1]}", pre_jp)
                    re_color_cn = re.compile(rf"{sign[0]}(.+?){sign[-1]}", re.DOTALL)
                    break
        # 掐头去尾
        s_head, pre_jp, s_tail = self.split_text_para(pre_jp)
        return s_head, pre_jp, s_tail, re_color_cn, lst_color

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
        tran_pre_jp = tran.plugin_used[self.pname]['src']
        problem_list = set()
        if tran.problem:
            problem_list.add(tran.problem)
        s_head, s_middle, s_tail = tran.plugin_used[self.pname]['split']
        tran.post_zh, missing = self.postprocess_color_tags(tran.post_zh, s_middle, tran_pre_jp)
        problem_list.update(missing)
        if self.替换rpg变量:
            # 替换剩余控制符
            dic_values = {}
            if '@' in tran.post_zh and '@' not in tran_pre_jp:
                tran.post_zh = tran.post_zh.replace("@", "＠")
            lst_items = self.re_combined.findall(s_middle)
            for item in lst_items:
                if item.isspace():
                    continue
                if item.strip() == self.主人公变量:
                    continue
                m = self.re_reserved.search(item)
                if not m:
                    if "＠" not in tran.post_zh:
                        problem_list.add(f'丢失控制符{item}')
                    else:
                        tran.post_zh = tran.post_zh.replace("＠", item, 1)
                else:
                    dic_values["".join([i for i in m.groups() if i])] = m.group(0)
            if self.主人公变量 and self.主人公变量 in tran_pre_jp:
                if '主角' not in tran.post_zh:
                    problem_list.add(f'丢失标签{self.主人公变量}')
                else:
                    tran.post_zh = tran.post_zh.replace('主角', self.主人公变量)
            # 从长到短排序
            dic_values = dict(sorted(dic_values.items(), key=lambda item: len(item[0]), reverse=True))

            for k, v in dic_values.items():
                if k not in tran.post_zh:
                    problem_list.add(f'丢失标签{v}')
                    continue

                tran.post_zh = tran.post_zh.replace(k, v)
            if "＠" in tran.post_zh:
                problem_list.add(f'多加控制符＠')
            # 恢复头尾
            tran.post_zh = s_head + tran.post_zh + s_tail

        if self.检查脚本变量:
            count_pre_jp = Counter([i.lower().strip() for i in self.re_combined.findall(tran.plugin_used[self.pname]['src']) if i.strip()])
            count_post_zh = Counter([i.lower().strip() for i in self.re_combined.findall(tran.post_zh) if i.strip()])
            for i in set(count_pre_jp.keys()) - set(count_post_zh.keys()):
                problem_list.add(f'脚本检查 丢失{i}')
            for i in set(count_post_zh.keys()) - set(count_pre_jp.keys()):
                problem_list.add(f'脚本检查 多加{i}')
            for k in count_pre_jp.keys():
                if count_pre_jp[k] != count_post_zh[k]:
                    problem_list.add(f'脚本检查 标签数量错误{k} {count_pre_jp[k]}->{count_post_zh[k]}')
                    #print(count_pre_jp, count_post_zh)


        s1_match = self.re_bracket.findall(tran_pre_jp)

        s2_match = self.re_bracket.findall(tran.post_zh)
        if len(s2_match) != len(s1_match):
            problem_list.add(f'中括号数量{len(s1_match)}->{len(s2_match)}')
        elif self.检查中括号数量:
            s1_not_found = [s1 for s1 in set(s1_match) if s1_match.count(s1) != s2_match.count(s1)]

            if s1_not_found:
                if sorted(s2_match) != sorted(s1_match):
                    problem_list.add(f'中括号内容可能错误 {s1_not_found}')
        if problem_list:
            tran.problem = ", ".join(problem_list)
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
    coder = text_coder_rpg()
    coder.gtp_init({'Core': {}, 'Settings': {}}, {})
    lines = {
    #    "その艶やかな姿に\\N[3]の獣心がそそられた。\n\\N[3]は少女の動きに合わせて腰を突き上げはじめる。",
        "\\C[0]アドラ地方　　\\C[21][\\V[61] / \\V[81]]\n\\>\\C[21]取得討伐pt　1pt": None,
    }
    for pre_line, post_line in lines.items():
        s=coder.before_src_processed(CSentense(pre_line))
        # , s.post_jp, s.pre_zh, s.post_zh
        print('pre_jp', s.pre_jp)
        print('post_jp', s.post_jp)
        if post_line is None:
            post_line = s.post_jp
        print("---->")
        s.pre_zh = post_line
        s.post_zh = post_line
        s = coder.before_dst_processed(s)
        print('pre_jp', s.pre_jp)
        print('post_jp', s.post_jp)
        print('pre_zh', s.pre_zh)
        print('post_zh', s.post_zh)
        print(s.problem)
        if s.post_zh == pre_line:
            print("Success!!\n")
        else:
            print("Failed!!\n")
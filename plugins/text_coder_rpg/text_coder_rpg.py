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
        r"\\[A-Za-z]{1,3}\d{1,2}\[.{1,10}?\]",
        r"\\[A-Z]\+",
        r"\\\-\[[^\[\]]{0,10}\]", # \-[06]
        r"\\img\[.+?\]",    # \img[BasicData/33Pzボタン.png]
        r"if\([^\(\)]*?[vs]\[\d+\][^\(\)]*?\)",  # if(!s[982]) if(v[982]) if(v[982] >= 1) if(!s[762]&&s[761]&&s[763])
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
        r"\\[><]",  # 在同一行显示文字 \>
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

        self.替换颜色代码 = settings.get("替换颜色代码", True)
        self.替换ruby注音 = settings.get("替换ruby注音", True)
        self.替换其他控制符 = settings.get("替换其他控制符", True)
        self.检查脚本变量 = settings.get("检查脚本变量", True)
        self.检查中括号内容一致 = settings.get("检查中括号内容一致", True)
        self.主人公变量 = settings.get("主人公变量", None)

        LOGGER.info(f"[{self.pname}] CheckBrackets·启动！")
        LOGGER.info(f"[{self.pname}] 替换颜色代码:{self.替换颜色代码}")
        LOGGER.info(f"[{self.pname}] 替换ruby注音:{self.替换ruby注音}")
        LOGGER.info(f"[{self.pname}] 替换其他控制符:{self.替换其他控制符}")
        LOGGER.info(f"[{self.pname}] 检查脚本变量:{self.检查脚本变量}")
        LOGGER.info(f"[{self.pname}] 检查中括号内容一致:{self.检查中括号内容一致}")
        LOGGER.info(f"[{self.pname}] 主人公变量:{self.主人公变量}")

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

    color_pre_pattern = re.compile(r'\\C\[(\d+)\]', re.IGNORECASE)
    color_post_pattern = re.compile(r'\{color(\d+):\s?(.*?)(?<!\\)\}', re.DOTALL|re.IGNORECASE)
    def preprocess_color_tags(self, text):
        # 正则匹配颜色标记（不区分大小写）
        matches = list(self.color_pre_pattern.finditer(text))
        # 如果匹配存在，并且全部都在字符串的首或尾，则直接返回原始文本
        if matches and all(m.start() == 0 or m.end() == len(text) for m in matches):
            return text

        end_tag = re.findall(r"\\C\[0+\]", text)
        if not end_tag:
            end_tag = "\\C[0]"
        else:
            end_tag = min(end_tag, key=len)
        end_num = end_tag[3:-1]

        parts = []
        current_color = None
        first_color = True
        last_pos = 0
        current_tag = None
        before_color = None
        for match in matches:
            start, end = match.span()
            # 提取当前颜色标记前的文本段
            content = text[last_pos:start]
            if content:
                if current_color is not None and (current_color != end_num or first_color):
                    if content.endswith('\\'):
                        content += ' '
                    parts.append(f"{{color{current_color}: {content}}}")
                    first_color = False
                else:
                    parts.append(content)  # 无颜色标记时直接保留
            # 更新当前颜色和位置
            before_color = current_color
            current_color = match.group(1)
            current_tag = match.group(0)
            last_pos = end

        # 处理剩余文本（最后一个颜色标记后的内容）
        remaining = text[last_pos:]
        if remaining:
            if current_color is not None:
                if current_color != end_num:
                    parts.append(f"{{color{current_color}: {remaining}}}")
                elif not before_color:
                    parts.append(f"{current_tag}{remaining}")
                else:
                    parts.append(remaining)
            else:
                parts.append(remaining)
        elif current_color != end_num:
            parts.append(current_tag)
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

        end_tag = re.findall(r"\\C\[0+\]", pre_jp)
        if not end_tag:
            end_tag = "\\C[0]"
        else:
            end_tag = min(end_tag, key=len)
        lst_split = self.color_post_pattern.split(processed_text)
        final_parts = [lst_split[0]]
        for i in range(1, len(lst_split), 3):
            final_parts.append(f"\\C[{lst_split[i]}]")
            final_parts.append(lst_split[i+1])
            if lst_split[i+2] or i+2 == len(lst_split)-1:
                final_parts.append(f"{end_tag}{lst_split[i+2]}")
        if final_parts[-1] == end_tag:
            pre_jp_lst = self.color_pre_pattern.findall(pre_jp)
            if not pre_jp_lst:
                final_parts.pop()
            else:
                last_pre_jp = pre_jp_lst[-1]
                if last_pre_jp != end_tag[3:-1]:
                    final_parts.pop()
        final_text = "".join(final_parts)

        return final_text, missing

    re_ruby = re.compile(r'\\r\[([^\[\],]+),([^\[\],]*)]')
    def before_src_processed(self, tran: CSentense) -> CSentense:
        """
        This method is called before the source sentence is processed.
        在post_jp没有被去除对话框和字典替换之前的处理，如果这是第一个插件的话post_jp=原始日文。
        :param tran: The CSentense to be processed.
        :return: The modified CSentense."""
        # 1. 替换主人公变量
        if self.主人公变量:
            tran.post_jp = tran.post_jp.replace(self.主人公变量, '主角')

        # 2. 替换Ruby注音标签（在保存src之前转换，避免脚本变量检查误报）
        if self.替换ruby注音:
            tran.post_jp = self.re_ruby.sub(
                lambda match: f"{match.group(1)}" if not match.group(2) else f"{match.group(1)}（{match.group(2)}）",
                tran.post_jp)

        # 3. 保存src（Bug1修复：ruby转换后保存，避免检查脚本变量对ruby标签误报丢失）
        tran.plugin_used[self.pname] = {'src': tran.post_jp}

        # 4. 颜色代码预处理（\C[N]text\C[0] → {colorN: text}）
        pre_jp = tran.post_jp
        if self.替换颜色代码:
            pre_jp = self.preprocess_color_tags(pre_jp)

        # 5. 文本头尾分割（始终执行）
        tran.plugin_used[self.pname]['split'] = self.split_text_para(pre_jp)

        # 6. 如有替换开关开启，剥离头尾并处理控制符
        if self.替换颜色代码 or self.替换其他控制符:
            pre_jp = tran.plugin_used[self.pname]['split'][1]
            if self.替换其他控制符:
                # 将非保留控制符替换为＠占位符（Problem4修复：用re_reserved.search代替matched=[False]闭包）
                for item in self.re_combined.findall(pre_jp):
                    if item.isspace():
                        continue
                    m = self.re_reserved.search(item)
                    if not m:
                        pre_jp = pre_jp.replace(item, '＠', 1)
                    else:
                        new_item = ''.join(filter(None, m.groups()))
                        pre_jp = pre_jp.replace(item, new_item, 1)
            tran.post_jp = pre_jp

        return tran

    @staticmethod
    def _add_problem(problems: list, msg: str) -> None:
        """将问题添加到有序列表中，避免重复（Problem5修复：替代set以保证输出顺序一致）。"""
        if msg not in problems:
            problems.append(msg)

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
        # Problem5修复：用有序列表代替set，确保问题输出顺序一致
        problems = list(dict.fromkeys(tran.problem.split(", "))) if tran.problem else []
        s_head, s_middle, s_tail = tran.plugin_used[self.pname]['split']

        # 颜色代码后处理（{colorN: text} → \C[N]...\C[0]）
        if self.替换颜色代码:
            tran.post_zh, missing = self.postprocess_color_tags(tran.post_zh, s_middle, tran_pre_jp)
            for m in missing:
                self._add_problem(problems, m)

        # 还原其他控制符（＠ → 原始控制符）
        if self.替换其他控制符:
            s_middle_lookup = self.color_post_pattern.sub("【\\2】", s_middle)
            dic_values = {}
            if '@' in tran.post_zh and '@' not in tran_pre_jp:
                tran.post_zh = tran.post_zh.replace("@", "＠")
            lst_items = self.re_combined.findall(s_middle_lookup)
            for item in lst_items:
                if item.isspace():
                    continue
                if item.strip() == self.主人公变量:
                    continue
                m_r = self.re_reserved.search(item)
                if not m_r:
                    if "＠" not in tran.post_zh:
                        self._add_problem(problems, f'脚本修复：丢失控制符{item}')
                    else:
                        tran.post_zh = tran.post_zh.replace("＠", item, 1)
                else:
                    dic_values["".join([i for i in m_r.groups() if i])] = m_r.group(0)
            # 从长到短排序，避免短键误匹配长键
            dic_values = dict(sorted(dic_values.items(), key=lambda x: len(x[0]), reverse=True))
            for k, v in dic_values.items():
                if k not in tran.post_zh:
                    self._add_problem(problems, f'脚本修复：丢失标签{v}')
                    continue
                tran.post_zh = tran.post_zh.replace(k, v)
            if "＠" in tran.post_zh:
                self._add_problem(problems, f'脚本修复：多加控制符＠')
            if '{color' in tran.post_zh:
                self._add_problem(problems, f'脚本修复：颜色标签未恢复')

        # 还原主人公变量（始终执行，不受替换其他控制符开关影响）
        if self.主人公变量 and self.主人公变量 in tran_pre_jp:
            if '主角' not in tran.post_zh:
                self._add_problem(problems, f'脚本修复：丢失标签{self.主人公变量}')
            else:
                tran.post_zh = tran.post_zh.replace('主角', self.主人公变量)

        # 还原头尾（如有任一替换开关开启）
        if self.替换颜色代码 or self.替换其他控制符:
            tran.post_zh = s_head + tran.post_zh + s_tail

        if problems:
            tran.problem = ", ".join(problems)
        return tran

    def after_dst_processed(self, tran: CSentense) -> CSentense:
        """
        This method is called after the destination sentence is processed.
        在post_zh已经被恢复对话框和字典替换之后的处理。
        检查脚本变量和中括号内容一致性在此处执行（对完整译文进行校验）。
        :param tran: The CSentense to be processed.
        :return: The modified CSentense.
        """
        problems = list(dict.fromkeys(tran.problem.split(", "))) if tran.problem else []
        tran_pre_jp = tran.plugin_used[self.pname]['src']

        # 检查脚本变量（翻译前后控制符数量是否一致）
        if self.检查脚本变量:
            count_pre_jp = Counter([i.lower().strip() for i in self.re_combined.findall(tran_pre_jp) if i.strip()])
            count_post_zh = Counter([i.lower().strip() for i in self.re_combined.findall(tran.post_zh) if i.strip()])
            for i in set(count_pre_jp.keys()) - set(count_post_zh.keys()):
                self._add_problem(problems, f'脚本检查：丢失{i}')
            for i in set(count_post_zh.keys()) - set(count_pre_jp.keys()):
                self._add_problem(problems, f'脚本检查：多加{i}')
            for k in count_pre_jp.keys():
                if count_pre_jp[k] != count_post_zh[k]:
                    self._add_problem(problems, f'脚本检查：标签数量错误{k} {count_pre_jp[k]}->{count_post_zh[k]}')

        # 检查中括号内容（Bug3修复：简化双重判断逻辑，直接比较排序后列表）
        s1_match = self.re_bracket.findall(tran_pre_jp)
        s2_match = self.re_bracket.findall(tran.post_zh)
        if len(s2_match) != len(s1_match):
            self._add_problem(problems, f'中括号数量{len(s1_match)}->{len(s2_match)}')
        elif self.检查中括号内容一致:
            if sorted(s2_match) != sorted(s1_match):
                diff = [s for s in set(s1_match) if s1_match.count(s) != s2_match.count(s)]
                self._add_problem(problems, f'中括号内容可能错误 {diff}')

        if problems:
            tran.problem = ", ".join(problems)
        return tran

    def gtp_final(self):
        """
        This method is called after all translations are done.
        在所有文件翻译完成之后的动作，例如输出提示信息。
        """
        pass

if __name__ == '__main__':
    # ── 颜色控制符 ──────────────────────────────────────────────────
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    RESET  = "\033[0m"
    PASS   = f"{GREEN}[PASS]{RESET}"
    FAIL   = f"{RED}[FAIL]{RESET}"
    WARN   = f"{YELLOW}[WARN]{RESET}"

    coder = text_coder_rpg()
    coder.gtp_init({'Core': {}, 'Settings': {'主人公变量': '\\s[9]'}}, {})

    def run_test(name: str, pre_jp: str, simulated_zh: str,
                 expect_post_zh: str = None,
                 expect_problem_contains: str = None,
                 expect_no_problem: bool = False) -> bool:
        """
        运行单条测试用例，返回是否通过。
          name                  : 测试名称
          pre_jp                : 原始日文（含控制符）
          simulated_zh          : 模拟 AI 输出的译文
          expect_post_zh        : 期望最终译文（None=不检查）
          expect_problem_contains: 期望 problem 包含的关键字（None=不检查）
          expect_no_problem     : 为 True 时期望 problem 为空
        """
        s = CSentense(pre_jp)
        s = coder.before_src_processed(s)
        ai_input = s.post_jp              # 实际发送给 AI 的文本
        s.pre_zh = simulated_zh
        s.post_zh = simulated_zh
        s = coder.before_dst_processed(s)
        s = coder.after_dst_processed(s)

        ok_zh = (expect_post_zh is None) or (s.post_zh == expect_post_zh)
        if expect_no_problem:
            ok_prob = not s.problem
        elif expect_problem_contains:
            ok_prob = bool(s.problem and expect_problem_contains in s.problem)
        else:
            ok_prob = True

        passed = ok_zh and ok_prob
        print(f"  {PASS if passed else FAIL}  {name}")
        if not ok_zh:
            print(f"         期望译文 : {repr(expect_post_zh)}")
            print(f"         实际译文 : {repr(s.post_zh)}")
        if not ok_prob:
            if expect_no_problem:
                print(f"         期望无problem，实际 : {repr(s.problem)}")
            else:
                print(f"         期望problem含 '{expect_problem_contains}'，实际 : {repr(s.problem)}")
        if s.problem:
            print(f"    {WARN} problem : {s.problem}")
        print(f"         AI输入 : {repr(ai_input)}")
        print(f"         最终输出: {repr(s.post_zh)}")
        print()
        return passed

    # ════════════════════════════════════════════════════════════════
    print("═" * 62)
    print("   text_coder_rpg  测试套件")
    print("═" * 62 + "\n")

    results = []

    # ── 1. 基础变量还原：\v[N] 在文本内 ─────────────────────────
    results.append(run_test(
        name="[基础-1] \\v[302] 变量在引号内正确还原",
        pre_jp="「あとは言わなくてもわかりますね\\v[302]」",
        simulated_zh="「剩下的不用我说你也明白吧V302」",
        expect_post_zh="「剩下的不用我说你也明白吧\\v[302]」",
        expect_no_problem=True,
    ))

    # ── 2. 长键优先：\N[3] 和 \N[30] 不误匹配 ───────────────────
    results.append(run_test(
        name="[基础-2] 长键优先 \\N[3] vs \\N[30]",
        pre_jp="\\N[3]の言葉に\\N[30]は驚いた。",
        simulated_zh="听到N3的话，N30感到很惊讶。",
        expect_post_zh="听到\\N[3]的话，\\N[30]感到很惊讶。",
        expect_no_problem=True,
    ))

    # ── 3. 非保留控制符 ＠ 还原 ──────────────────────────────────
    results.append(run_test(
        name="[基础-3] \\! 控制符经＠还原",
        pre_jp="\\!急いで！\\!",
        simulated_zh="＠快点！＠",
        expect_post_zh="\\!快点！\\!",
        expect_no_problem=True,
    ))

    # ── 4. 头尾控制符剥离与还原 ──────────────────────────────────
    results.append(run_test(
        name="[基础-4] 头尾 \\> \\< 剥离后正确还原",
        pre_jp="\\>急げ！\\<",
        simulated_zh="快！",
        expect_post_zh="\\>快！\\<",
        expect_no_problem=True,
    ))

    # ── 5. 多控制符顺序正确还原 ──────────────────────────────────
    results.append(run_test(
        name="[基础-5] 多个 \\{ \\} 按顺序还原",
        pre_jp="\\{大きく\\}普通\\{また大きく\\}",
        simulated_zh="＠大＠普通＠再大＠",
        expect_post_zh="\\{大\\}普通\\{再大\\}",
        expect_no_problem=True,
    ))

    # ── 6. 引号包裹文本头尾保留 ──────────────────────────────────
    results.append(run_test(
        name="[基础-6] 引号包裹时头尾控制符保留",
        pre_jp="\"\\!今すぐ行け！\\!\"",
        simulated_zh="\"＠马上走！＠\"",
        expect_post_zh="\"\\!马上走！\\!\"",
        expect_no_problem=True,
    ))

    # ── 7. 主人公变量替换与还原 ──────────────────────────────────
    results.append(run_test(
        name="[主人公-1] \\s[9] 替换为'主角'再还原",
        pre_jp="\\s[9]は立ち上がった。",
        simulated_zh="主角站了起来。",
        expect_post_zh="\\s[9]站了起来。",
        expect_no_problem=True,
    ))

    # ── 8. 主人公变量丢失时有 problem ────────────────────────────
    results.append(run_test(
        name="[主人公-2] '主角'被AI丢失时报problem",
        pre_jp="\\s[9]は叫んだ。",
        simulated_zh="大喊道。",
        expect_problem_contains="丢失标签",
    ))

    # ── 9. Bug1修复：Ruby注音翻译后不误报变量丢失 ───────────────
    results.append(run_test(
        name="[Bug1-1] Ruby正常展开翻译后无误报",
        pre_jp="\\r[主人公,しゅじんこう]が叫んだ。",
        simulated_zh="主人公（しゅじんこう）大喊道。",
        expect_no_problem=True,
    ))

    # ── 10. Bug1：Ruby内容被AI完全丢失时应有提示 ─────────────────
    results.append(run_test(
        name="[Bug1-2] Ruby展开内容被AI丢失时有脚本检查提示",
        pre_jp="\\r[勇者,ゆうしゃ]は剣を抜いた。",
        simulated_zh="拔出了剑。",   # ruby展开的"勇者（ゆうしゃ）"被完全删掉
        expect_problem_contains="脚本检查",
    ))

    # ── 11. 颜色标签预处理与还原 ─────────────────────────────────
    results.append(run_test(
        name="[颜色-1] \\C[3]...\\C[0] 正确预处理并还原",
        pre_jp="\\C[3]重要なお知らせ\\C[0]です。",
        simulated_zh="{color3: 重要通知}。",
        expect_post_zh="\\C[3]重要通知\\C[0]。",
        expect_no_problem=True,
    ))

    # ── 12. 颜色标签被 AI 丢失时有 problem ───────────────────────
    results.append(run_test(
        name="[颜色-2] 颜色标签被AI丢失时报problem",
        pre_jp="\\C[3]重要なお知らせ\\C[0]です。",
        simulated_zh="重要通知。",
        expect_problem_contains="颜色",
    ))

    # ── 13. Bug3修复：中括号数量不一致检测 ──────────────────────
    results.append(run_test(
        name="[Bug3-1] 中括号数量不一致时报problem",
        pre_jp="選択肢は[A]か[B]です。",
        simulated_zh="选项是[A]。",
        expect_problem_contains="中括号数量",
    ))

    # ── 14. Bug3修复：中括号数量内容均一致时无 problem ───────────
    results.append(run_test(
        name="[Bug3-2] 中括号数量内容均正确时无problem",
        pre_jp="選択肢は[A]か[B]です。",
        simulated_zh="选项是[A]还是[B]。",
        expect_no_problem=True,
    ))

    # ── 15. 控制符被 AI 完全丢失时检测 ──────────────────────────
    results.append(run_test(
        name="[检查-1] 控制符被AI丢失时报丢失problem",
        pre_jp="\\!早く来て！\\!",
        simulated_zh="快来！",
        expect_problem_contains="丢失控制符",
    ))

    # ── 16. 综合场景：主人公+变量+控制符混合 ─────────────────────
    results.append(run_test(
        name="[综合] 主人公+\\N[N]+控制符混合场景",
        pre_jp="\\s[9]は\\N[3]に\\!叫んだ\\!。",
        simulated_zh="主角向N3＠大喊＠。",
        expect_post_zh="\\s[9]向\\N[3]\\!大喊\\!。",
        expect_no_problem=True,
    ))

    # ── 汇总 ─────────────────────────────────────────────────────
    total  = len(results)
    passed = sum(results)
    color  = GREEN if passed == total else RED
    print("═" * 62)
    print(f"   结果：{color}{passed}/{total} 通过{RESET}")
    print("═" * 62)


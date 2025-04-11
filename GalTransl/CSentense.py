

SYMBOL_PAIRS = {
    "「": ("」", "｣"),
    "｢": ("｣", "」"),
    "『": "』",
    "“": "”"
}

class CSentense:
    """
    每个CSentense储存一句待翻译文本
    """

    def __init__(self, pre_jp: str, speaker: str = "", index=0) -> None:
        """每个CSentense储存一句待翻译文本

        Args:
            pre_jp (str): 润色前日文
            speaker (str, optional): 说话人. Defaults to "".
            index_key (str, optional): 唯一index. Defaults to "".
        """
        self.index = index

        self._pre_jp = pre_jp  # 前原
        self.post_jp = pre_jp  # 前润，初始为原句
        self.pre_zh = ""  # 后原
        self.proofread_zh = ""  # 校对, For GPT4
        self.post_zh = ""  # 后润，最终zh

        self.speaker = speaker  # 如果是dialogue则可以记录讲话者
        self._speaker = speaker  # 用于记录原speaker，因为speaker会被改变
        self.is_dialogue = True if speaker != "" else False  # 记录原句是否为对话
        self.has_diag_symbol = False  # 是对话但也可能没有对话框，所以分开
        self.left_symbol = ""  # 记录原句的左对话框与其他左边符号等
        self.right_symbol = ""  # 记录原句的右对话框与其他右边符号等

        self.dia_format = "#句子"  # 这两个主要是字典替换的时候要
        self.mono_format = "#句子"  # 用在>关键字中

        self.trans_by = ""  # 翻译记录
        self.proofread_by = ""  # 校对记录

        self.problem = ""  # 问题记录
        self.trans_conf = 0.0  # 翻译可信度 For GPT4
        self.doub_content = ""  # 用于记录疑问句的内容 For GPT4
        self.unknown_proper_noun = ""  # 用于记录未知的专有名词 For GPT4

        self.prev_tran: CSentense = None  # 指向上一个tran
        self.next_tran: CSentense = None  # 指向下一个tran

        self.plugin_used = {}


    @property
    def pre_jp(self):
        return self._pre_jp

    @pre_jp.setter
    def pre_jp(self, value):
        if hasattr(self, "_pre_jp"):
            raise AttributeError("Can't modify pre_jp")
        self._pre_jp = value

    def __repr__(self) -> str:
        name = self.speaker
        name = f"-[{str(name)}]" if name != "" else ""
        tmp_post_jp = self.post_jp.replace("\r", "\\r").replace("\n", "\\n")
        tmp_post_zh = self.post_zh.replace("\r", "\\r").replace("\n", "\\n")
        tmp_proofread_zh = self.proofread_zh.replace("\r", "\\r").replace("\n", "\\n")
        char_t = "\t"
        char_n = "\n"
        return f"{char_n}⇣--{self.index}{name}{char_n}> Src: {tmp_post_jp}{char_n}> Dst: {tmp_post_zh if self.proofread_zh == '' else tmp_proofread_zh}"

    def analyse_dialogue(self, dia_format: str = "#句子", mono_format: str = "#句子"):
        """对话分析，根据对话框判断是否为对话，暂时隐藏对话框，分别格式化diag与mono到不同的format

        Args:
            dia_format (str, optional): 对于对话的格式化，会把#句子替换为原句. Defaults to "#句子".
            mono_format (str, optional): 对于独白的格式化，会把#句子替换为原句. Defaults to "#句子".
        """
        if self.post_jp == "":
            return

        self.dia_format, self.mono_format = dia_format, mono_format

        # 定义一个局部函数检查括号平衡，允许嵌套情况
        def is_balanced(text, left, rights):
            count = 0
            for ch in text:
                if ch == left:
                    count += 1
                elif ch in rights:
                    if count > 0:
                        count -= 1
                    else:
                        # 出现不成对的右括号
                        return False
            return True

        # 获取第一句句首的左括号字符串
        first_symbol = self.post_jp[:1]
        if first_symbol not in SYMBOL_PAIRS:
            self.post_jp = mono_format.replace("#句子", self.post_jp)
            return

        # 处理右括号可能为 tuple 的情况
        raw_right = SYMBOL_PAIRS[first_symbol]
        if isinstance(raw_right, tuple):
            right_symbols = raw_right
        else:
            right_symbols = (raw_right,)

        # 查找末尾句
        current = self
        found_right = False
        full_str = self.post_jp
        mid_lst = []
        # 循环处理最多 3 个连续段落
        for _ in range(0, 3):

            # 句尾必须为允许的右括号之一
            if full_str[-1] in right_symbols:
                # 检查内层文本（去掉最外层左右符号）是否平衡
                inner_text = full_str[1:-1]
                if is_balanced(inner_text, first_symbol, right_symbols):
                    # 匹配成功
                    found_right = True
                break
            #
            if current != self:
                mid_lst.append(current)
            current = current.next_tran
            if current is None:
                break
            if current._speaker and current._speaker != self._speaker:
                break
            full_str += current.post_jp

        if not found_right:
            self.post_jp = mono_format.replace("#句子", self.post_jp)
            return

        # 标记对话
        self.is_dialogue = True
        self.has_diag_symbol = True
        self.left_symbol = self.left_symbol + first_symbol
        current.is_dialogue = True
        current.has_diag_symbol = True
        # 这里将当前的 right_symbol 更新为最外层的右括号（注意：如果有多个可能，这里取最后一个字符）
        current.right_symbol = full_str[-1] + current.right_symbol
        current.speaker = self.speaker
        for t in mid_lst:
            t.is_dialogue = True
            t.has_diag_symbol = False
            t.speaker = self.speaker

        # 移除首尾符号
        self.post_jp = self.post_jp[1:]
        current.post_jp = current.post_jp[:-1]
        full_str = full_str[1:-1]

        # 处理后续可能存在的嵌套左括号字符串
        while True:
            left_symbol = full_str[0]
            if left_symbol not in SYMBOL_PAIRS:
                break
            raw_right = SYMBOL_PAIRS[left_symbol]
            if isinstance(raw_right, tuple):
                nested_rights = raw_right
            else:
                nested_rights = (raw_right,)
            if full_str[-1] not in nested_rights:
                break

            inner_text = full_str[1:-1]
            if not is_balanced(inner_text, left_symbol, nested_rights):
                break

            self.left_symbol = self.left_symbol + left_symbol
            current.right_symbol = full_str[-1] + current.right_symbol
            self.post_jp = self.post_jp[1:]
            current.post_jp = current.post_jp[:-1]
            full_str = full_str[1:-1]

        # 格式化输出
        self.post_jp = dia_format.replace("#句子", self.post_jp)

    def analyse_dialogue_bak(self, dia_format: str = "#句子", mono_format: str = "#句子"):
        """对话分析，根据对话框判断是否为对话，暂时隐藏对话框，分别格式化diag与mono到不同的format

        Args:
            dia_format (str, optional): 对于对话的格式化，会把#句子替换为原句. Defaults to "#句子".
            # 句子替换为原句. Defaults to "#句子".
            mono_format (str, optional): 对于独白的格式化，会把
        """
        if self.post_jp == "":
            return
        self.dia_format, self.mono_format = dia_format, mono_format
        first_symbol, last_symbol = self.post_jp[:1], self.post_jp[-1:]

        while (
            first_symbol in "「『"
            and last_symbol in "」』"
            and self.post_jp != ""
            and ord(last_symbol) - ord(first_symbol) == 1  # 是同一对
        ):
            self.is_dialogue = True
            self.has_diag_symbol = True
            self.left_symbol = self.left_symbol + first_symbol
            self.right_symbol = last_symbol + self.right_symbol
            self.post_jp = self.post_jp[1:-1]  # 去首尾
            first_symbol, last_symbol = self.post_jp[:1], self.post_jp[-1:]

        # 情况2，一句话拆成2个的情况
        if self.next_tran != None:
            first_symbol_next = self.next_tran.post_jp[:1]
            last_symbol_next = self.next_tran.post_jp[-1:]
            if first_symbol == "「" and last_symbol != "」":
                if first_symbol_next != "「" and last_symbol_next == "」":
                    self.is_dialogue, self.next_tran.is_dialogue = True, True
                    self.has_diag_symbol, self.next_tran.has_diag_symbol = True, True
                    self.next_tran.speaker = self.speaker
                    self.left_symbol = self.left_symbol + first_symbol
                    self.next_tran.right_symbol = (
                        last_symbol_next + self.next_tran.right_symbol
                    )
                    self.post_jp, self.next_tran.post_jp = (
                        self.post_jp[1:],
                        self.next_tran.post_jp[:-1],
                    )

        # 情况3，一句话拆成3个的情况，一般不会再多了……
        if self.next_tran != None and self.next_tran.next_tran != None:
            first_symbol_next = self.next_tran.post_jp[:1]
            last_symbol_next = self.next_tran.post_jp[-1:]
            first_symbol_next_next = self.next_tran.next_tran.post_jp[:1]
            last_symbol_next_next = self.next_tran.next_tran.post_jp[-1:]
            if first_symbol == "「" and last_symbol != "」":
                if first_symbol_next != "「" and last_symbol_next != "」":
                    if first_symbol_next_next != "「" and last_symbol_next_next == "」":
                        (
                            self.is_dialogue,
                            self.next_tran.is_dialogue,
                            self.next_tran.next_tran.is_dialogue,
                        ) = (True, True, True)
                        (
                            self.has_diag_symbol,
                            self.next_tran.has_diag_symbol,
                            self.next_tran.next_tran.has_diag_symbol,
                        ) = (True, False, True)
                        self.next_tran.speaker, self.next_tran.next_tran.speaker = (
                            self.speaker,
                            self.speaker,
                        )
                        self.left_symbol = self.left_symbol + first_symbol
                        self.next_tran.next_tran.right_symbol = (
                            last_symbol_next_next
                            + self.next_tran.next_tran.right_symbol
                        )
                        self.post_jp, self.next_tran.next_tran.post_jp = (
                            self.post_jp[1:],
                            self.next_tran.next_tran.post_jp[:-1],
                        )

        self.post_jp = (dia_format if self.is_dialogue else mono_format).replace(
            "#句子", self.post_jp
        )

    def recover_dialogue_symbol(self):
        """
        译后用，对post_zh恢复对话符号，应该放在最后
        """
        self.post_zh = self.left_symbol + self.post_zh + self.right_symbol


CTransList = list[CSentense]

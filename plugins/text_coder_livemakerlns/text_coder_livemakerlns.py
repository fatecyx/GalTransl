import json
import re
from collections import Counter

from GalTransl import LOGGER
from GalTransl.CSentense import CSentense
from GalTransl.GTPlugin import GTextPlugin


class text_coder_livemakerlns(GTextPlugin):

    # 定义一个字典，用于替换特定类型的标签
    dict_replace = {
        'IMG': [
            ('SRC', re.compile(r'ハート\.gal$'), "♥"),
        ],
        'VAR': [
            ("NAME", re.compile(r'^(.+)$'), "【{0}】")
        ],
        'STYLE': [
            ("RUBY", re.compile(r'^(.+)$'), "（{0}）")
        ]
    }

    def gtp_init(self, plugin_conf: dict, project_conf: dict):
        """
        This method is called when the plugin is loaded.在插件加载时被调用。
        :param plugin_conf: The settings for the plugin.插件yaml中所有设置的dict。
        :param project_conf: The settings for the project.项目yaml中common下设置的dict。
        """
        self.pname = plugin_conf["Core"].get("Name", "")

        LOGGER.info(f"[{self.pname}] livemaker_lns脚本检查·启动！")

    def before_src_processed(self, tran: CSentense) -> CSentense:
        """
        This method is called before the source sentence is processed.
        在post_jp没有被去除对话框和字典替换之前的处理，如果这是第一个插件的话post_jp=原始日文。
        :param tran: The CSentense to be processed.
        :return: The modified CSentense."""

        lst, count = extract_brackets(tran.post_jp)
        result = []
        last_title = {}
        # 遍历提取出的标签列表并进行替换
        for item in lst:
            if not item.startswith("<"):
                result.append(item)
                continue
            dic = parse_bracket_string(item)
            if dic['title'].startswith("/"):
                last_index = last_title.get(dic['title'][1:].lower(), -1)
                if last_index < 0:
                    print("ERROR title", dic['title'], tran.post_jp)
                    result.append("＠")
                    pass
                else:
                    result.append(f"{result[last_index]}")
                    result[last_index] = ''
                    last_title.pop(dic['title'][1:].lower())
            else:
                if dic['title'] in self.dict_replace:
                    for key, regex, format_str in self.dict_replace[dic['title']]:
                        if key not in dic['kv_pairs']:
                            continue
                        m = regex.findall(dic['kv_pairs'][key])
                        if m:
                            result.append(format_str.format(m[0]))
                            break
                    else:
                        result.append("＠")
                else:
                    result.append("＠")

                last_title[dic['title'].lower()] = len(result) - 1
        tran.post_jp = "".join(result)
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

        return tran

    def after_dst_processed(self, tran: CSentense) -> CSentense:
        """
        This method is called after the destination sentence is processed.
        在post_zh已经被恢复对话框和字典替换之后的处理。
        :param tran: The CSentense to be processed.
        :return: The modified CSentense.
        """
        problems = set(tran.problem)
        lst, count = extract_brackets(tran.pre_jp)
        result = []
        last_title = {}
        replace_list = []
        # 遍历提取出的标签列表并进行恢复
        for item in lst:
            if not item.startswith("<"):
                result.append(item)
                continue
            dic = parse_bracket_string(item)
            if dic['title'].startswith("/"):
                last_index = last_title.get(dic['title'][1:].lower(), -1)
                if last_index < 0:
                    print("ERROR title", dic['title'], tran.post_jp)
                    result.append("＠")
                    replace_list.append((None, dic['source'], dic['title'], "＠"))
                    pass
                else:
                    result.append(result.pop(last_index))
                    last_title.pop(dic['title'][1:].lower())
            else:
                if dic['title'] in self.dict_replace:
                    for key, regex, format_str in self.dict_replace[dic['title']]:
                        if key not in dic['kv_pairs']:
                            continue
                        m = regex.findall(dic['kv_pairs'][key])
                        if m:
                            result.append(format_str.format(m[0]))
                            replace_list.append((dic['kv_pairs'][key], dic['source'], dic['title'], format_str.format(m[0])))
                            break
                    else:
                        result.append("＠")
                        replace_list.append((None, dic['source'], dic['title'], "＠"))
                else:
                    result.append("＠")
                    replace_list.append((None, dic['source'], dic['title'], "＠"))

                last_title[dic['title'].lower()] = len(result) - 1

            #
            #         'IMG': [
            #             ('SRC', re.compile(r'ハート\.gal$'), "♥"),
            #         ],
            #         'VAR': [
            #             ("NAME", re.compile(r'^(.+)$'), "【{0}】")
            #         ],
            #         'STYLE': [
            #             ("RUBY", re.compile(r'^(.+)$'), "（{0}）")
            #         ]
        str_replaced = set()
        for key, source, title, replace_str in replace_list:
            if title == "IMG":
                if replace_str not in str_replaced:
                    if replace_str not in tran.post_zh:
                        problems.add(f"丢失标签 {replace_str}")
                    else:
                        tran.post_zh = tran.post_zh.replace(replace_str, source)
                        str_replaced.add(replace_str)
            elif title == "VAR":
                if replace_str in str_replaced:
                    continue
                if replace_str not in tran.post_zh:
                    problems.add(f"丢失标签 {replace_str}")
                else:
                    tran.post_zh = tran.post_zh.replace(replace_str, source)
                    str_replaced.add(replace_str)

            elif replace_str == "＠":
                if replace_str not in tran.post_zh:
                    problems.add(f"丢失标签 {replace_str}")
                else:
                    tran.post_zh = tran.post_zh.replace(replace_str, source, 1)

        tran.problem = ", ".join(problems)
        return tran

    def gtp_final(self):
        """
        This method is called after all translations are done.
        在所有文件翻译完成之后的动作，例如输出提示信息。
        """
        pass



def parse_bracket_string(bracket_string: str) -> dict:
    """
    解析格式为 [title key1=value1 key2="value 2" ...] 的字符串，
    并返回包含标题和键值对的字典。

    参数:
    - bracket_string (str): 要解析的字符串。

    返回:
    - dict: 包含标题和键值对的字典。
    """
    pattern = r'\<(?P<title>[^\s]+)(?P<kv_pairs>.*?)\>'
    key_value_pattern = r'(\w+)=("(?:[^"]|\\")+?"|\'(?:[^\']|\\\')+?\'|[^\s]+)'

    match = re.match(pattern, bracket_string)
    if not match:
        raise ValueError(f"Invalid format: {bracket_string}")

    title = match.group('title')
    kv_pairs_string = match.group('kv_pairs').strip()
    kv_pairs = {}
    if kv_pairs_string:
        for key, value in re.findall(key_value_pattern, kv_pairs_string):
            quoted = False
            # Determine if the value is quoted and remove quotes if necessary
            if value.startswith('"') and value.endswith('"'):
                quoted = True
                value = value[1:-1].replace('\\"', '"')  # Handle escaped quotes
            elif value.startswith("'") and value.endswith("'"):
                quoted = True
                value = value[1:-1].replace("\\'", "'")  # Handle escaped quotes

            #kv_pairs[key] = {"value": value, "quoted": quoted}
            kv_pairs[key] = value

    return {"title": title, "kv_pairs": kv_pairs, 'source': bracket_string}


def extract_brackets(s: str) -> tuple:
    """
    提取字符串中所有的括号内容，并返回结果列表和括号数量。

    参数:
    - s (str): 要提取的字符串。

    返回:
    - tuple: 包含提取结果列表和括号数量的元组。
    """
    stack = []
    result = []
    word = ""
    count = 0
    for i, c in enumerate(s):
        if c == '<':
            if not stack:
                start = i
            stack.append(c)
        elif stack and c == '>':
            stack.pop()
            if not stack:
                # parse_dict = parse_bracket_string(s[start:i+1])
                # if not parse_dict:
                #     print(s[start:i+1])
                # result.append(parse_dict)
                result.append(s[start:i+1])
        else:
            if not stack:
                word += c
            elif word:
                if word:
                    result.append(word)
                    count+=1
                word = ""
    if word:
        result.append(word)
        count+=1
    # result2 = []
    # index = 0
    # cache = []
    # #for i, item in enumerate(result):
    # while index < len(result):
    #     item = result[index]
    #     if not item.startswith("<"):
    #         result2.append(item)
    #         index += 1
    #         continue
    #     dic = parse_bracket_string(item)
    #     if dic['title'].startswith("/"):
    #         continue
    #     lower_title=dic['title'].lower()
    #     for j in range(index+1, len(result)):
    #         if result[j].lower() == f"</{lower_title}>":
    #             dic['childs'] = result[index+1: j]
    #             index = j+1
    #             result2.append(dic)
    #             break
    #     else:
    #         result2.append(dic)
    #         index += 1

    return result, count

if __name__ == '__main__':
    coder = text_lns_coder()
    coder.gtp_init({'Core': {}, 'Settings': {}}, {})
    lines = [
    #    "その艶やかな姿に\\N[3]の獣心がそそられた。\n\\N[3]は少女の動きに合わせて腰を突き上げはじめる。",
    "(気持ちいいっぃ<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">気持ちいいいぃ<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">\n気持ちぃいいい<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">ぃぃ<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\"><VAR NAME=\"玄武\" unk3=\"50\">様っぁ<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">\n好きっぃ<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">私の全ては<VAR NAME=\"玄武\" unk3=\"50\">様のモノぉ<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">)",
        "(気になるのはコインということ。\nまさかと思うけど私の<STYLE ID=\"2\" RUBY=\"レールガン\">超電磁砲</STYLE>と同じ能力？\nまたはコピー能力かもしれない。)",
        "「さすがにそれを許すほど\n<VAR NAME=\"ミサカ\" unk3=\"50\">はお人よしではない\nと、<VAR NAME=\"ミサカ\" unk3=\"50\">は<IMG SRC=\"グラフィック\\03絵文字\\吃驚.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"TOP\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">」",
        "「<IMG SRC=\"グラフィック\\03絵文字\\吃驚2.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"TOP\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">！？」",
        "<VAR NAME=\"姫神\" unk3=\"50\"><TXSPN>　<VAR NAME=\"秋沙\" unk3=\"50\">\n<VAR NAME=\"月詠\" unk3=\"50\">　<VAR NAME=\"小萌\" unk3=\"50\">\nと呼ぶように変更しました。",
        "<VAR NAME=\"御坂\" unk3=\"50\"><TXSPN>を<VAR NAME=\"メス奴隷1\" unk3=\"50\">\n<VAR NAME=\"白井\" unk3=\"50\">を<VAR NAME=\"メス奴隷2\" unk3=\"50\">\n<VAR NAME=\"初春\" unk3=\"50\">を<VAR NAME=\"メス奴隷3\" unk3=\"50\">\n<VAR NAME=\"佐天\" unk3=\"50\">を<VAR NAME=\"メス奴隷4\" unk3=\"50\">\n<VAR NAME=\"食蜂\" unk3=\"50\">を<VAR NAME=\"メス奴隷5\" unk3=\"50\">\n<VAR NAME=\"ミサカ回数\" unk3=\"50\">を<VAR NAME=\"メス奴隷6\" unk3=\"50\">\n<VAR NAME=\"インデックス\" unk3=\"50\">を<VAR NAME=\"メス奴隷7\" unk3=\"50\">\n<VAR NAME=\"神裂\" unk3=\"50\">を<VAR NAME=\"メス奴隷8\" unk3=\"50\">\n<VAR NAME=\"姫神\" unk3=\"50\">を<VAR NAME=\"メス奴隷9\" unk3=\"50\">\n<VAR NAME=\"風斬\" unk3=\"50\">を<VAR NAME=\"メス奴隷10\" unk3=\"50\">\n<VAR NAME=\"月詠\" unk3=\"50\">を<VAR NAME=\"メス奴隷11\" unk3=\"50\">\nと隷属時に呼ぶように変更しました。",
        "[<VAR NAME=\"ミサカ\" unk3=\"50\">]\n「んんぎひっぃい<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\"><VAR NAME=\"アナル女\" unk3=\"50\">までっぇ<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">\nそんなところ指を入れられたらっ<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">ぁ<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">\n<VAR NAME=\"ミサカ\" unk3=\"50\">の意識が<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">壊れちゃいますっぅ<IMG SRC=\"グラフィック\\03絵文字\\ハート.gal\" HOVERSRC=\"None\" DOWNSRC=\"None\" ALIGN=\"CENTER\" MGNLEFT=\"0\" MGNRIGHT=\"0\" MGNTOP=\"0\" MGNBOTTOM=\"0\">」"



             ]
    for line in lines:
        # result, count = extract_brackets(line)
        # print(count, json.dumps(line, ensure_ascii=False))
        # for item in result:
        #     print(item)
            #print('\t', parse_bracket_string(item) if item.startswith("<") else item)
        s=coder.before_src_processed(CSentense(line))
        # , s.post_jp, s.pre_zh, s.post_zh
        print('pre_jp', s.pre_jp)
        print('post_jp', s.post_jp)
    #     print('pre_zh', s.pre_zh)
    #     print('post_zh', s.post_zh)
        s.pre_zh = s.post_jp
        s.post_zh = s.post_jp.replace("ミサカ", '御坂')
        s = coder.after_dst_processed(s)
        print('pre_zh', s.pre_zh)
        print('post_zh', s.post_zh)
        print(s.problem)
        if s.post_zh == line:
            print("Success!!\n")
        else:
            print("Failed!!\n")
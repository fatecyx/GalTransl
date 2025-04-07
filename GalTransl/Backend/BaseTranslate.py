import json, time, asyncio, os, traceback
import openai
from opencc import OpenCC
from typing import Optional
from GalTransl.COpenAI import COpenAITokenPool
from GalTransl.ConfigHelper import CProxyPool
from GalTransl import LOGGER, LANG_SUPPORTED
from sys import exit
from GalTransl.ConfigHelper import (
    CProjectConfig,
)
from random import choice
from GalTransl.CSentense import CSentense, CTransList
from GalTransl.Cache import get_transCache_from_json_new, save_transCache_to_json
from GalTransl.Dictionary import CGptDict
from GalTransl.Utils import extract_code_blocks, fix_quotes



class BaseTranslate:
    def __init__(
        self,
        config: CProjectConfig,
        eng_type: str,
        proxy_pool: Optional[CProxyPool],
        token_pool: COpenAITokenPool,
    ):
        """
        根据提供的类型、配置、API 密钥和代理设置初始化 Chatbot 对象。

        Args:
            config (dict, 可选): 使用 非官方API 时提供 的配置字典。默认为空字典。
            apikey (str, 可选): 使用 官方API 时的 API 密钥。默认为空字符串。
            proxy (str, 可选): 使用 官方API 时的代理 URL，非官方API的代理写在config里。默认为空字符串。

        Returns:
            None
        """
        self.eng_type = eng_type
        self.last_file_name = ""
        self.restore_context_mode = config.getKey("gpt.restoreContextMode")
        self.retry_count = 0
        # 保存间隔
        if val := config.getKey("save_steps"):
            self.save_steps = val
        else:
            self.save_steps = 1
        # 语言设置
        if val := config.getKey("language"):
            sp = val.split("2")
            self.source_lang = sp[0]
            self.target_lang = sp[1]
        elif val := config.getKey("sourceLanguage"):  # 兼容旧版本配置
            self.source_lang = val
            self.target_lang = config.getKey("targetLanguage")
        else:
            self.source_lang = "ja"
            self.target_lang = "zh-cn"
        if self.source_lang not in LANG_SUPPORTED.keys():
            raise ValueError("错误的源语言代码：" + self.source_lang)
        else:
            self.source_lang = LANG_SUPPORTED[self.source_lang]
        if self.target_lang not in LANG_SUPPORTED.keys():
            raise ValueError("错误的目标语言代码：" + self.target_lang)
        else:
            self.target_lang = LANG_SUPPORTED[self.target_lang]
        # 429等待时间
        if val := config.getKey("gpt.tooManyRequestsWaitTime"):
            self.wait_time = val
        else:
            self.wait_time = 60
        # 跳过重试
        if val := config.getKey("skipRetry"):
            self.skipRetry = val
        else:
            self.skipRetry = False
        # 跳过h
        if val := config.getKey("skipH"):
            self.skipH = val
        else:
            self.skipH = False
        # enhance_jailbreak
        if val := config.getKey("gpt.enhance_jailbreak"):
            self.enhance_jailbreak = val
        else:
            self.enhance_jailbreak = False
        # 流式输出模式
        if val := config.getKey("gpt.streamOutputMode"):
            self.streamOutputMode = val
        else:
            self.streamOutputMode = False
        if val := config.getKey("workersPerProject"):  # 多线程关闭流式输出
            if val > 1:
                self.streamOutputMode = False

        self.tokenProvider = token_pool
        if config.getKey("internals.enableProxy") == True:
            self.proxyProvider = proxy_pool
        else:
            self.proxyProvider = None

        self._current_temp_type = ""

        self.init_chatbot(eng_type=eng_type, config=config)  # 模型选择

        self._set_temp_type("precise")

        if self.target_lang == "Simplified_Chinese":
            self.opencc = OpenCC("t2s.json")
        elif self.target_lang == "Traditional_Chinese":
            self.opencc = OpenCC("s2tw.json")

        pass

    def init_chatbot(self, eng_type, config):
        pass

    

    def clean_up(self):
        pass

    def translate(self, trans_list: CTransList, gptdict=""):
        pass

    async def batch_translate(
        self,
        filename,
        cache_file_path,
        trans_list: CTransList,
        num_pre_request: int,
        retry_failed: bool = False,
        gpt_dic: CGptDict = None,
        proofread: bool = False,
        retran_key: str = "",
    ) -> CTransList:
        _, trans_list_unhit = get_transCache_from_json_new(
            trans_list,
            cache_file_path,
            retry_failed=retry_failed,
            proofread=proofread,
            retran_key=retran_key,
        )

        if self.skipH:
            LOGGER.warning("skipH: 将跳过含有敏感词的句子")
            trans_list_unhit = [
                tran
                for tran in trans_list_unhit
                if not any(word in tran.post_jp for word in H_WORDS_LIST)
            ]

        if len(trans_list_unhit) == 0:
            return []
        # 新文件重置chatbot
        if self.last_file_name != filename:
            self.reset_conversation()
            self.last_file_name = filename
            LOGGER.info(f"-> 开始翻译文件：{filename}")
        i = 0

        if (
            self.eng_type != "unoffapi"
            and self.restore_context_mode
            and len(self.chatbot.conversation["default"]) == 1
        ):
            if not proofread:
                self.restore_context(trans_list_unhit, num_pre_request)

        trans_result_list = []
        len_trans_list = len(trans_list_unhit)
        transl_step_count = 0
        while i < len_trans_list:
            await asyncio.sleep(1)
            trans_list_split = (
                trans_list_unhit[i : i + num_pre_request]
                if (i + num_pre_request < len_trans_list)
                else trans_list_unhit[i:]
            )

            dic_prompt = gpt_dic.gen_prompt(trans_list_split) if gpt_dic else ""

            num, trans_result = await self.translate(
                trans_list_split, dic_prompt, proofread=proofread
            )

            if num > 0:
                i += num
            result_output = ""
            for trans in trans_result:
                result_output = result_output + repr(trans)
            LOGGER.info(result_output)
            trans_result_list += trans_result
            transl_step_count += 1
            if transl_step_count >= self.save_steps:
                save_transCache_to_json(trans_list, cache_file_path)
                transl_step_count = 0
            LOGGER.info(
                f"{filename}: {str(len(trans_result_list))}/{str(len_trans_list)}"
            )

        return trans_result_list
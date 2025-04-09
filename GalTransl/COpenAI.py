"""
CloseAI related classes
"""

import os
from httpx import AsyncClient
import asyncio
from tqdm.asyncio import tqdm
from time import time
from GalTransl import LOGGER, TRANSLATOR_DEFAULT_ENGINE
from GalTransl.ConfigHelper import CProjectConfig, CProxy
from typing import Optional, Tuple
from random import choice
from asyncio import Queue
from openai import OpenAI
import re


class COpenAIToken:
    """
    OpenAI 令牌
    """

    def __init__(self, token: str, domain: str, isAvailable: bool) -> None:
        self.token: str = token
        self.domain: str = domain
        self.isAvailable: bool = isAvailable

    def maskToken(self) -> str:
        """
        返回脱敏后的 sk-
        """
        return self.token[:6] + "*" * 17


def initGPTToken(config: CProjectConfig, eng_type: str) -> Optional[list[COpenAIToken]]:
    """
    处理 GPT Token 设置项
    """
    result: list[dict] = []
    degradeBackend: bool = False

    if val := config.getKey("gpt.degradeBackend"):
        degradeBackend = val

    defaultEndpoint = "https://api.openai.com"
    if "GPT4" in config.projectConfig["backendSpecific"]:  # 兼容旧版
        section_name = "GPT4"
    else:
        section_name = "OpenAI-Compatible"
    if all_tokens := config.getBackendConfigSection(section_name).get("tokens"):
        for tokenEntry in all_tokens:
            token = tokenEntry["token"]
            domain = (
                tokenEntry["endpoint"]
                if tokenEntry.get("endpoint")
                else defaultEndpoint
            )
            domain = domain[:-1] if domain.endswith("/") else domain
            result.append(
                COpenAIToken(token, domain, True if degradeBackend else False, True)
            )
            pass

    return result


class COpenAITokenPool:
    """
    OpenAI 令牌池
    """

    def __init__(self, config: CProjectConfig, eng_type: str) -> None:

        token_list: list[dict] = []
        defaultEndpoint = "https://api.openai.com"
        if "GPT4" in config.projectConfig["backendSpecific"]:  # 兼容旧版
            section_name = "GPT4"
        else:
            section_name = "OpenAI-Compatible"

        self.tokens: list[tuple[bool, COpenAIToken]] = []
        self.force_eng_name = config.getBackendConfigSection(section_name).get(
            "rewriteModelName", ""
        )

        if all_tokens := config.getBackendConfigSection(section_name).get("tokens"):
            for tokenEntry in all_tokens:
                token = tokenEntry["token"]
                domain = (
                    tokenEntry["endpoint"]
                    if tokenEntry.get("endpoint")
                    else defaultEndpoint
                )
                domain = domain[:-1] if domain.endswith("/") else domain
                token_list.append(COpenAIToken(token, domain, True))
                pass

        for token in token_list:
            self.tokens.append((False, token))

    async def _isTokenAvailable(
        self, token: COpenAIToken, proxy: CProxy = None, model_name: str = ""
    ) -> Tuple[bool, bool, bool, COpenAIToken]:

        if not token.domain.endswith("/v1") and not re.search(r"/v\d+$", token.domain):
            base_url = token.domain + "/v1"
        else:
            base_url = token.domain
        try:
            st = time()
            client = OpenAI(
                api_key=token.token,
                base_url=base_url,
            )
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "JUST echo OK"}],
                temperature=0.1,
                max_tokens=100,
                timeout=30,
            )

            if not response.choices[0].message.content:
                # token not available, may token has been revoked
                return False, token
            else:

                return True, token
        except Exception as e:
            LOGGER.debug(e)

            LOGGER.debug(
                "we got exception in testing OpenAI token %s", token.maskToken()
            )
            return False, token
        finally:
            et = time()
            LOGGER.debug("tested OpenAI token %s in %s", token.maskToken(), et - st)
            pass

    async def _check_token_availability_with_retry(
        self,
        token: COpenAIToken,
        proxy: CProxy = None,
        model_name: str = "",
        max_retries: int = 3,
    ) -> Tuple[bool, COpenAIToken]:
        for retry_count in range(max_retries):
            is_available, token = await self._isTokenAvailable(token, proxy, model_name)
            if is_available:
                return is_available, token
            else:
                # wait for some time before retrying, you can add some delay here
                LOGGER.warning(f"可用性检查失败，正在重试 {retry_count + 1} 次...")
                await asyncio.sleep(1)

        # If all retries fail, return the result from the last attempt
        return is_available, token

    async def checkTokenAvailablity(
        self, proxy: CProxy = None, eng_type: str = ""
    ) -> None:
        """
        检测令牌有效性
        """
        model_name = TRANSLATOR_DEFAULT_ENGINE.get(eng_type, "")
        if self.force_eng_name:
            model_name = self.force_eng_name
        assert model_name != "", "model_name is empty!"

        LOGGER.info(f"测试key是否能调用{model_name}模型...")
        fs = []
        for _, token in self.tokens:
            fs.append(
                self._check_token_availability_with_retry(
                    token, proxy if proxy else None, model_name
                )
            )
        result: list[tuple[bool, COpenAIToken]] = await tqdm.gather(*fs, ncols=80)

        # replace list with new one
        newList: list[tuple[bool, COpenAIToken]] = []
        for isAvailable, token in result:
            if isAvailable != True:
                LOGGER.warning(
                    "%s is not available for %s, will be removed",
                    token.maskToken(),
                    model_name,
                )
            else:
                newList.append((True, token))

        self.tokens = newList

    def reportTokenProblem(self, token: COpenAIToken) -> None:
        """
        报告令牌无效
        """
        for id, tokenPair in enumerate(self.tokens):
            if tokenPair[1] == token:
                self.tokens.pop(id)
            pass
        pass

    def getToken(self) -> COpenAIToken:
        """
        获取一个有效的 token
        """
        rounds: int = 0
        while True:
            if rounds > 20:
                raise RuntimeError("COpenAITokenPool::getToken: 可用的API key耗尽！")
            try:
                available, token = choice(self.tokens)
                if not available:
                    continue
                if token.isAvailable:
                    return token
                rounds += 1
            except IndexError:
                raise RuntimeError("没有可用的 API key！")


async def init_sakura_endpoint_queue(projectConfig: CProjectConfig) -> Optional[Queue]:
    """
    初始化端点队列，用于Sakura或GalTransl引擎。

    参数:
    projectConfig: 项目配置对象
    workersPerProject: 每个项目的工作线程数
    eng_type: 引擎类型

    返回:
    初始化的端点队列，如果不需要则返回None
    """

    workersPerProject = projectConfig.getKey("workersPerProject") or 1
    sakura_endpoint_queue = asyncio.Queue()
    backendSpecific = projectConfig.projectConfig["backendSpecific"]
    section_name = "SakuraLLM" if "SakuraLLM" in backendSpecific else "Sakura"
    if "endpoints" in projectConfig.getBackendConfigSection(section_name):
        endpoints = projectConfig.getBackendConfigSection(section_name)["endpoints"]
    else:
        endpoints = [projectConfig.getBackendConfigSection(section_name)["endpoint"]]
    repeated = (workersPerProject + len(endpoints) - 1) // len(endpoints)
    for _ in range(repeated):
        for endpoint in endpoints:
            await sakura_endpoint_queue.put(endpoint)
    LOGGER.info(f"当前使用 {workersPerProject} 个Sakura worker引擎")
    return sakura_endpoint_queue

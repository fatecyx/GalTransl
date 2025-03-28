import logging
from time import localtime
import threading
from GalTransl.Utils import check_for_tool_updates

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

PROGRAM_SPLASH1 = r"""
   ____       _ _____                    _ 
  / ___| __ _| |_   _| __ __ _ _ __  ___| |
 | |  _ / _` | | | || '__/ _` | '_ \/ __| |
 | |_| | (_| | | | || | | (_| | | | \__ \ |
  \____|\__,_|_| |_||_|  \__,_|_| |_|___/_|                 

------Translate your favorite Galgame------
"""

PROGRAM_SPLASH2 = r"""
   ______      ________                      __
  / ____/___ _/ /_  __/________ _____  _____/ /
 / / __/ __ `/ / / / / ___/ __ `/ __ \/ ___/ / 
/ /_/ / /_/ / / / / / /  / /_/ / / / (__  ) /  
\____/\__,_/_/ /_/ /_/   \__,_/_/ /_/____/_/   
                                             
-------Translate your favorite Galgame-------
"""

PROGRAM_SPLASH3 = r'''

   ___              _     _____                                     _    
  / __|   __ _     | |   |_   _|    _ _   __ _    _ _      ___     | |   
 | (_ |  / _` |    | |     | |     | '_| / _` |  | ' \    (_-<     | |   
  \___|  \__,_|   _|_|_   _|_|_   _|_|_  \__,_|  |_||_|   /__/_   _|_|_  
_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""| 
"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-' 

--------------------Translate your favorite Galgame--------------------
'''

PROGRAM_SPLASH4 = r"""
     _____)           ______)                 
   /             /)  (, /                  /) 
  /   ___   _   //     /  __  _  __   _   //  
 /     / ) (_(_(/_  ) /  / (_(_(_/ (_/_)_(/_  
(____ /            (_/                        

-------Translate your favorite Galgame-------
"""
ALL_BANNERS = [PROGRAM_SPLASH1, PROGRAM_SPLASH2, PROGRAM_SPLASH3, PROGRAM_SPLASH4]
PROGRAM_SPLASH = ALL_BANNERS[localtime().tm_mday % 4]

GALTRANSL_VERSION = "5.12.0"
AUTHOR = "xd2333"
CONTRIBUTORS = "ryank231231, PiDanShouRouZhouXD, Noriverwater, Isotr0py, adsf0427, pipixia244, gulaodeng, sakura-umi, lifegpc, natsumerinchan"

CONFIG_FILENAME = "config.yaml"
INPUT_FOLDERNAME = "gt_input"
OUTPUT_FOLDERNAME = "gt_output"
CACHE_FOLDERNAME = "transl_cache"
TRANSLATOR_SUPPORTED = {
    "ForGal": "（Beta，目前基于Deepseek-V3）为翻译Gal重新定制的翻译模板，更快更省更好",
    "gpt4": "（GPT4/Claude-3/Deepseek-V3）比较聪明的模型通用的翻译模板，默认GPT4-1106模型",
    "r1": "Deepseek-R1模型专用翻译模板",
    "sakura-v1.0": "（适用v1.0版prompt）为翻译轻小说/Gal开展大规模训练的本地模型，具有多个型号和大小",
    "galtransl-v3": "为翻译Gal基于Sakura进一步优化的本地小模型，可运行在6G空闲显存的游戏显卡和MacBook上",
    "rebuildr": "重建结果 用译前译后字典通过缓存刷写结果json -- 跳过翻译和写缓存",
    "rebuilda": "重建缓存和结果 用译前译后字典刷写缓存+结果json -- 跳过翻译",
    "dump-name": "导出name字段，生成人名替换表，用于翻译name字段",
    "show-plugs": "显示全部插件列表",
}
NEED_OpenAITokenPool=["gpt", "r1", "ForGal"]
LANG_SUPPORTED = {
    "zh-cn": "Simplified_Chinese",
    "zh-tw": "Traditional_Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "fr": "French",
}
LANG_SUPPORTED_W = {
    "zh-cn": "简体中文",
    "zh-tw": "繁體中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "ru": "русский",
    "fr": "Français",
}
DEBUG_LEVEL = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

new_version = []
update_thread = threading.Thread(target=check_for_tool_updates, args=(new_version,))
update_thread.start()

transl_counter = {"tran_count": 0, "error_count": 0}

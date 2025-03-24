import argparse, traceback
from asyncio import get_event_loop, run, new_event_loop, set_event_loop
from GalTransl.ConfigHelper import CProjectConfig
from GalTransl.Runner import run_galtransl
from GalTransl import (
    PROGRAM_SPLASH,
    TRANSLATOR_SUPPORTED,
    GALTRANSL_VERSION,
    AUTHOR,
    CONTRIBUTORS,
    LOGGER,
    DEBUG_LEVEL,
)


def worker(project_dir: str, config_file_name: str, translator: str, show_banner=True):
    if not project_dir or not isinstance(project_dir, str):
        LOGGER.error("项目路径不能为空且必须是字符串类型")
        return False
    if not config_file_name or not isinstance(config_file_name, str):
        LOGGER.error("配置文件名不能为空且必须是字符串类型")
        return False
    if not translator or not isinstance(translator, str):
        LOGGER.error("翻译器名称不能为空且必须是字符串类型")
        return False

    if show_banner:
        print(PROGRAM_SPLASH)
        print(f"GalTransl Core version: {GALTRANSL_VERSION}")
        print(f"Author: {AUTHOR}")
        print(f"Contributors: {CONTRIBUTORS}")

    try:
        cfg = CProjectConfig(project_dir, config_file_name)
        LOGGER.setLevel(DEBUG_LEVEL[cfg.getCommonConfigSection().get("loggingLevel", "info")])
    except Exception as ex:
        LOGGER.error(f"加载配置文件失败: {str(ex)}")
        return False

    try:
        loop = get_event_loop()
    except RuntimeError:
        LOGGER.info("创建新的事件循环...")
        loop = new_event_loop()
        set_event_loop(loop)

    try:
        run(run_galtransl(cfg, translator))
    except KeyboardInterrupt:
        LOGGER.info("正在等待现有请求返回...")
        loop.stop()
        LOGGER.info("Goodbye.")
    except RuntimeError as ex:
        LOGGER.error("程序遇到问题，即将退出（诊断信息：%s）", ex)
    except BaseException as ex:
        LOGGER.error(f"程序遇到未预期的错误: {str(ex)}")
        LOGGER.debug("详细错误信息:", exc_info=True)
        traceback.print_exception(type(ex), ex, ex.__traceback__)
    finally:
        try:
            loop.close()
        except Exception as ex:
            LOGGER.error(f"关闭事件循环时发生错误: {str(ex)}")
        return True


def main() -> int:
    parser = argparse.ArgumentParser("GalTransl")
    parser.add_argument("--project_dir", "-p", help="project folder", required=True)
    parser.add_argument(
        "--translator",
        "-t",
        choices=TRANSLATOR_SUPPORTED.keys(),
        help="choose which Translator to use",
        required=True,
    )
    parser.add_argument(
        "--debug-level",
        "-l",
        choices=DEBUG_LEVEL.keys(),
        help="debug level",
        default="info",
    )
    args = parser.parse_args()
    # logging level
    LOGGER.setLevel(DEBUG_LEVEL[args.debug_level])

    print(PROGRAM_SPLASH)
    print(f"GalTransl Core version: {GALTRANSL_VERSION}")
    print(f"Author: {AUTHOR}")
    print(f"Contributors: {CONTRIBUTORS}")

    return worker(args.project_dir, "config.yaml", args.translator)


if __name__ == "__main__":
    main()

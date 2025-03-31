import os
import sys

# 基本配置，避免循环导入
from GalTransl import (
    CONFIG_FILENAME,
    PROGRAM_SPLASH,
    TRANSLATOR_SUPPORTED
)
INPUT_PROMPT_TMP = "请输入/拖入项目文件夹，或项目文件夹内的yaml配置文件[default]："


class ProjectManager:
    def __init__(self):
        self.user_input = ""
        self.project_dir = ""
        self.config_file_name = CONFIG_FILENAME
        self.translator = ""

    def validate_project_path(self, user_input: str) -> tuple[str | None, str | None, str | None]:
        if not user_input or not isinstance(user_input, str):
            print("输入路径不能为空且必须是字符串类型\n")
            return None, None, None
        try:
            user_input = os.path.abspath(user_input)
            if user_input.endswith(".yaml"):
                config_file_name = os.path.basename(user_input)
                project_dir = os.path.dirname(user_input)
            else:
                config_file_name = CONFIG_FILENAME
                project_dir = user_input

            if not os.path.exists(project_dir):
                print(f"项目文件夹 {project_dir} 不存在，请检查后重新输入\n")
                return None, None, None

            config_path = os.path.join(project_dir, config_file_name)
            if not os.path.exists(config_path):
                print(f"配置文件 {config_path} 不存在，请检查后重新输入\n")
                return None, None, None

            if not os.path.isfile(config_path):
                print(f"配置文件路径 {config_path} 不是一个有效的文件，请检查后重新输入\n")
                return None, None, None

            return user_input, project_dir, config_file_name
        except Exception as e:
            print(f"验证项目路径时发生错误: {str(e)}\n")
            return None, None, None

    def get_user_input(self):
        while True:
            input_prompt = INPUT_PROMPT_TMP.replace(
                "[default]",
                f"(留空继续『{self.project_name()}』项目)" if self.project_dir else "",
            )
            user_input = input(input_prompt).strip('"') or self.user_input

            if not user_input:
                continue
            
            user_input = user_input.strip('"').strip("'")
            self.user_input, self.project_dir, self.config_file_name = (
                self.validate_project_path(user_input)
            )
            if not self.project_dir:
                continue

            return

    def print_program_info(self):
        from GalTransl import GALTRANSL_VERSION, AUTHOR, CONTRIBUTORS
        print(PROGRAM_SPLASH)
        print(f"Ver: {GALTRANSL_VERSION}")
        print(f"Author: {AUTHOR}")
        print(f"Contributors: {CONTRIBUTORS}\n")

    def choose_translator(self):
        from command import BulletMenu
        
        default_choice = (
            list(TRANSLATOR_SUPPORTED.keys()).index(self.translator)
            if self.translator
            else 0
        )
        os.system("")  # 解决cmd的ANSI转义bug
        self.translator = BulletMenu(
            f"请为『{self.project_name()}』项目选择翻译模板：", TRANSLATOR_SUPPORTED
        ).run(default_choice)

    def project_name(self):
        return self.project_dir.split(os.sep)[-1] if self.project_dir else ""

    def create_shortcut_win(self) -> None:
        try:
            from GalTransl import GALTRANSL_VERSION
            TEMPLATE = '@echo off\nchcp 65001\nset "CURRENT_PATH=%CD%"\ncd /d "{0}"\n{1} "{2}" {3}\npause\ncd /d "%CURRENT_PATH%"'
            run_com = "python.exe " + os.path.basename(__file__)
            program_dir = os.path.dirname(os.path.abspath(__file__))
            shortcut_path = f"{self.project_dir}{os.sep}run_GalTransl_v{GALTRANSL_VERSION}_{self.translator}.bat"
            conf_path = "%CURRENT_PATH%\\" + self.config_file_name
            if "nt" not in os.name:  # not windows
                return
            if getattr(sys, "frozen", False):  # PyInstaller
                run_com = os.path.basename(sys.executable)
                program_dir = os.path.dirname(sys.executable)
            with open(shortcut_path, "w", encoding="utf-8") as f:
                text = TEMPLATE.format(program_dir, run_com, conf_path, self.translator)
                f.write(text)
        except Exception as e:
            print(f"创建快捷方式时发生错误: {str(e)}\n")

    def run(self):
        # 检查命令行参数
        if len(sys.argv) > 1:
            self.user_input = sys.argv[1]
            self.user_input, self.project_dir, self.config_file_name = (
                self.validate_project_path(self.user_input)
            )
            if len(sys.argv) > 2 and sys.argv[2] in TRANSLATOR_SUPPORTED.keys():
                self.translator = sys.argv[2]

        while True:
            self.print_program_info()

            # 如果初始路径无效或未提供，进入交互式输入阶段
            if not self.project_dir:
                try:
                    self.get_user_input()
                except KeyboardInterrupt:
                    print("\nGoodbye.")
                    return
            if not self.translator:
                try:
                    self.choose_translator()
                except KeyboardInterrupt:
                    print("\nGoodbye.")
                    return
            if self.translator not in ["show-plugs", "dump-name"]:
                self.create_shortcut_win()
            from GalTransl.__main__ import worker
            worker(
                self.project_dir,
                self.config_file_name,
                self.translator,
                show_banner=False,
            )

            print("翻译任务完成，准备重新开始...")
            self.user_input = ""
            self.translator = ""

            os.system("pause")
            os.system("cls")


if __name__ == "__main__":
    manager = ProjectManager()
    manager.run()

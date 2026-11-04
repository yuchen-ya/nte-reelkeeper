from pathlib import Path
import sys


def application_directory():
    """便携版将模型、设置和日志放在 EXE 旁，源码版沿用项目目录。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]

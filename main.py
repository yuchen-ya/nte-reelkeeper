import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='ReelKeeper 驱动块筛选助手')
    parser.add_argument('--start', action='store_true', help='启动后接续任务')
    parser.add_argument('--check-installation', type=Path, metavar='REPORT', help='离线检查安装并保存 JSON，不操作游戏')
    parser.add_argument('--check-image', type=Path, action='append', default=[], metavar='IMAGE', help='安装检查时额外读取截图')
    args = parser.parse_args()
    if args.check_installation:
        from nte_ocr.diagnostics import check_installation
        return check_installation(args.check_installation, args.check_image)
    if args.check_image:
        parser.error('--check-image 需要与 --check-installation 一起使用')
    from nte_ocr.app import main as run_app
    run_app()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

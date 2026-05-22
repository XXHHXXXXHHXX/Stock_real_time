# -*- coding: utf-8 -*-
"""
打包脚本 - 使用PyInstaller将Python应用打包为exe

使用方法:
    python build.py

打包选项:
    --onefile : 打包为单个exe文件
    --onedir  : 打包为文件夹（默认，启动更快）
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def check_pyinstaller():
    """检查PyInstaller是否安装"""
    try:
        import PyInstaller
        return True
    except ImportError:
        print("PyInstaller未安装，正在安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        return True


def clean_build():
    """清理旧的构建文件"""
    dirs_to_remove = ["build", "dist"]
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            print(f"清理 {dir_name}/...")
            shutil.rmtree(dir_name)
    
    # 清理spec文件
    for spec_file in Path(".").glob("*.spec"):
        print(f"删除 {spec_file}...")
        spec_file.unlink()


def build_exe(onefile=False):
    """
    构建exe
    
    Parameters:
    -----------
    onefile : bool
        True: 打包为单个exe文件（体积大，启动慢）
        False: 打包为文件夹（体积小，启动快）
    """
    print("=" * 60)
    print("实时板块资金流向监控工具 - 打包脚本")
    print("=" * 60)
    
    # 检查PyInstaller
    if not check_pyinstaller():
        print("错误: 无法安装PyInstaller")
        return False
    
    # 清理旧文件
    clean_build()
    
    # 构建命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "实时板块资金流向监控",
        "--noconfirm",
        "--clean",
        "--windowed",  # GUI应用，不显示控制台
        "--icon", "NONE",
    ]
    
    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")
    
    # 添加隐藏导入
    hidden_imports = [
        "pandas",
        "numpy",
        "tushare",
        "pyqtgraph",
        "PyQt5.sip",
        "PyQt5.QtCore",
        "PyQt5.QtGui",
        "PyQt5.QtWidgets",
    ]
    
    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])
    
    # 主文件
    cmd.append("main.py")
    
    print(f"\n执行命令: {' '.join(cmd)}\n")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print("\n" + "=" * 60)
        print("打包成功!")
        print("=" * 60)
        
        # 显示输出路径
        if onefile:
            output_path = os.path.join("dist", "实时板块资金流向监控.exe")
        else:
            output_path = os.path.join("dist", "实时板块资金流向监控")
        
        print(f"\n输出路径: {os.path.abspath(output_path)}")
        
        if not onefile:
            exe_path = os.path.join(output_path, "实时板块资金流向监控.exe")
            print(f"可执行文件: {os.path.abspath(exe_path)}")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"\n错误: 打包失败")
        print(f"返回码: {e.returncode}")
        return False
    except Exception as e:
        print(f"\n错误: {e}")
        return False


def main():
    """主函数"""
    # 检查命令行参数
    onefile = "--onefile" in sys.argv
    
    if onefile:
        print("打包模式: 单文件")
    else:
        print("打包模式: 文件夹（推荐）")
    
    # 执行打包
    success = build_exe(onefile=onefile)
    
    if success:
        print("\n提示: 打包完成后，exe文件位于 dist/ 目录下")
        print("      将exe文件复制到任意位置即可运行")
        
        if not onefile:
            print("      整个文件夹需要一起移动，不能单独移动exe文件")
    else:
        print("\n打包失败，请检查错误信息")
        sys.exit(1)


if __name__ == "__main__":
    main()

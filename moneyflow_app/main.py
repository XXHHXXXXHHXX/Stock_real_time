# -*- coding: utf-8 -*-
"""
实时板块资金流向监控工具
========================

功能：
- 实时监控A股各板块（概念/行业）资金流向
- 分时折线图展示各板块资金净流入/流出趋势
- 支持按金额筛选、搜索、排序
- 显示上证指数、深证成指、创业板指实时数据

数据源：Tushare Pro (https://tushare.pro)

使用方法：
    python main.py              # 只使用真实数据（默认）
    python main.py --mock       # 允许在真实数据不可用时使用模拟数据
    python main.py --proxy      # 启用站大爷代理池（需配置config.py中的账号信息）

作者：AI Assistant
日期：2026-05-20
"""

import sys
import os

# 修复 Qt 平台插件找不到的问题
if "QT_QPA_PLATFORM_PLUGIN_PATH" not in os.environ:
    try:
        import PyQt5
        _plugins_dir = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins", "platforms")
        if os.path.isdir(_plugins_dir):
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = _plugins_dir
    except ImportError:
        pass

# 设置高DPI支持
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

# 启用高DPI缩放
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

from PyQt5.QtGui import QFont
from main_window import MainWindow


def main():
    """主函数"""
    # 检查是否启用模拟数据模式
    use_mock = "--mock" in sys.argv
    if use_mock:
        # 移除 --mock 参数，避免影响 QApplication
        sys.argv = [arg for arg in sys.argv if arg != "--mock"]
        print("[Main] 已启用模拟数据模式 (--mock)")
    
    # 检查是否启用代理模式
    use_proxy = "--proxy" in sys.argv
    if use_proxy:
        sys.argv = [arg for arg in sys.argv if arg != "--proxy"]
        print("[Main] ================================")
        print("[Main] 已启用代理池模式 (--proxy)")
        print("[Main] ================================")
    else:
        print("[Main] 未启用代理池（如需代理请加上 --proxy 参数）")
    
    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName("实时板块资金流向监控")
    app.setApplicationVersion("1.0.0")
    
    # 设置全局字体
    font = QFont("Microsoft YaHei", 10)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)
    
    # 创建并显示主窗口
    window = MainWindow(use_mock=use_mock, use_proxy=use_proxy)
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

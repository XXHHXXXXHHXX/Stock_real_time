# -*- coding: utf-8 -*-
"""
配置文件 - 实时资金流向监控工具
"""

import os

# Tushare Token - 用户可在此修改或从环境变量读取
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "2e77e914ab7c86c5b24077a81ab0c791a5057a3af06221f3bb9c7db9")

# Tushare API URL（自定义服务器）
TUSHARE_API_URL = "http://118.89.66.41:8010/"

# 更新间隔（毫秒）
UPDATE_INTERVAL_MS = 60000  # 默认60秒更新一次

# 指数代码
INDEX_CODES = {
    "上证": "000001.SH",
    "深证": "399001.SZ",
    "创业板": "399006.SZ"
}

# 板块类型
SECTOR_TYPES = {
    "concept": "概念板块",
    "industry": "行业板块",
}

# 颜色配置 - 白色清爽主题
COLORS = {
    "background": "#ffffff",      # 白色背景
    "grid": "#e8e8e8",            # 浅灰网格
    "text": "#333333",            # 深灰文字（比纯黑柔和）
    "positive": "#e60000",        # 红色表示上涨/资金流入 (A股习惯)
    "negative": "#009944",        # 绿色表示下跌/资金流出 (A股习惯)
    "neutral": "#999999",         # 灰色中性
    "index_up": "#e60000",
    "index_down": "#009944",
    "toolbar_bg": "#f5f5f5",      # 工具栏背景
    "panel_bg": "#fafafa",        # 面板背景
    "border": "#d0d0d0",          # 边框颜色
    "input_bg": "#ffffff",        # 输入框背景
    "button_bg": "#f0f0f0",       # 按钮背景
    "button_hover": "#e0e0e0",    # 按钮悬停
    "primary_btn": "#e60000",     # 主按钮
    "primary_btn_hover": "#ff3333",
    "line_colors": [
        "#ff6b6b", "#ff8e53", "#ff6b9d", "#c44569",
        "#f8b500", "#ff6348", "#ffa502", "#ff7f50",
        "#70a1ff", "#5352ed", "#40407a", "#2ed573",
        "#7bed9f", "#2bcbba", "#17c0eb", "#e056fd",
        "#686de0", "#30336b", "#95afc0", "#5f27cd",
        "#f9ca24", "#f0932b", "#eb4d4b", "#6ab04c",
        "#22a6b3", "#0984e3", "#b2bec3", "#636e72",
    ]
}

# 默认筛选设置
DEFAULT_FILTERS = {
    "min_inflow": None,      # 最小流入金额（亿元），None表示不限制
    "max_outflow": None,     # 最大流出金额（亿元），None表示不限制
    "top_n": 30,             # 默认显示前30个板块
    "show_positive_only": False,
    "show_negative_only": False,
}

# 交易时间段（A股）
TRADING_HOURS = {
    "morning_start": "09:30",
    "morning_end": "11:30",
    "afternoon_start": "13:00",
    "afternoon_end": "15:00"
}

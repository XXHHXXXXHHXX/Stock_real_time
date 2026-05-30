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
UPDATE_INTERVAL_MS = 10000  # 默认10秒更新一次

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
LIGHT_COLORS = {
    "background": "#ffffff",
    "grid": "#e8e8e8",
    "text": "#333333",
    "positive": "#e60000",
    "negative": "#009944",
    "neutral": "#999999",
    "index_up": "#e60000",
    "index_down": "#009944",
    "toolbar_bg": "#f5f5f5",
    "panel_bg": "#fafafa",
    "border": "#d0d0d0",
    "input_bg": "#ffffff",
    "button_bg": "#f0f0f0",
    "button_hover": "#e0e0e0",
    "primary_btn": "#e60000",
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

DARK_COLORS = {
    "background": "#1e1e2e",
    "grid": "#313144",
    "text": "#cdd6f4",
    "positive": "#f38ba8",
    "negative": "#a6e3a1",
    "neutral": "#6c7086",
    "index_up": "#f38ba8",
    "index_down": "#a6e3a1",
    "toolbar_bg": "#181825",
    "panel_bg": "#1e1e2e",
    "border": "#45475a",
    "input_bg": "#313244",
    "button_bg": "#45475a",
    "button_hover": "#585b70",
    "primary_btn": "#f38ba8",
    "primary_btn_hover": "#f5c2e7",
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

_current_theme = "light"


def set_theme(theme_name):
    global _current_theme, COLORS
    if theme_name not in ("light", "dark"):
        raise ValueError(f"Unknown theme: {theme_name!r}, expected 'light' or 'dark'")
    _current_theme = theme_name
    COLORS = DARK_COLORS if theme_name == "dark" else LIGHT_COLORS


def get_theme():
    return _current_theme


def toggle_theme():
    new_theme = "dark" if _current_theme == "light" else "light"
    set_theme(new_theme)
    return new_theme


COLORS = LIGHT_COLORS

# 默认筛选设置
DEFAULT_FILTERS = {
    "min_inflow": None,      # 最小流入金额（亿元），None表示不限制
    "max_outflow": None,     # 最大流出金额（亿元），None表示不限制
    "top_n": 30,             # 默认显示前30个板块
    "show_positive_only": False,
    "show_negative_only": False,
}

# 站大爷免费代理API配置（如需使用代理防封，请填写以下信息）
# 文档: https://www.zdaye.com/doc/api/FreeProxy_get
USE_ZDAYE_PROXY = True
ZDAYE_API_URL = "http://www.zdopen.com/FreeProxy/Get/"
ZDAYE_APP_ID = "202605222157502337"
ZDAYE_AKEY = "ad92715c99936cd0"
ZDAYE_PROXY_USERNAME = "202605222157502337"  # 实例ID，作为代理用户名
ZDAYE_PROXY_PASSWORD = "57502337"             # 实例ID后8位，作为代理密码

# 交易时间段（A股）
TRADING_HOURS = {
    "morning_start": "09:30",
    "morning_end": "11:30",
    "afternoon_start": "13:00",
    "afternoon_end": "15:00"
}

# -*- coding: utf-8 -*-
"""
配置持久化管理
保存/读取用户设置到本地 JSON 文件
"""

import json
import os


SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_settings.json")


def load_settings():
    """加载用户配置，返回字典"""
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Settings] 加载配置失败: {e}")
        return {}


def save_settings(settings):
    """保存用户配置到文件"""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Settings] 保存配置失败: {e}")

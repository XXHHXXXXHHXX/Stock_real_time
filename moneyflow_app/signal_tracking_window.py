# -*- coding: utf-8 -*-
"""
信号板块追踪窗口

显示所有触发过智能信号（风格切换/抄底/砸盘/变盘）的板块曲线，
不受主图表筛选影响，持续追踪到程序关闭。
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor

from chart_widget import MoneyFlowChart
from config import COLORS
from signal_detector import SIGNAL_NAMES, SIGNAL_COLORS


class SignalTrackingWindow(QWidget):
    """
    信号板块追踪窗口
    
    独立窗口，显示所有触发过智能信号的板块的曲线。
    曲线持续显示，不受主图表筛选条件影响。
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("信号板块追踪")
        self.setMinimumSize(900, 700)
        self.resize(1100, 750)
        
        # 追踪的板块代码集合
        self._tracked_sectors = set()
        # 板块备注 {ts_code: {names: [], signal_types: [], first_time, last_time}}
        self._sector_notes = {}
        
        self._init_ui()
        
        # 定时器：定期刷新标签
        self._label_timer = QTimer()
        self._label_timer.timeout.connect(self._refresh_labels)
        self._label_timer.start(5000)
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # ===== 标题栏 =====
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("📊 信号板块追踪")
        title.setStyleSheet(f"""
            color: {COLORS['text']};
            font-size: 18px;
            font-weight: bold;
            font-family: "Microsoft YaHei", "SimHei";
        """)
        header_layout.addWidget(title)
        
        # 追踪数量标签
        self._count_label = QLabel("追踪: 0 个板块")
        self._count_label.setStyleSheet(f"color: {COLORS['neutral']}; font-size: 13px;")
        header_layout.addWidget(self._count_label)
        
        header_layout.addStretch()
        
        # 清空按钮
        clear_btn = QPushButton("🗑 清空追踪")
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['button_bg']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 5px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['button_hover']};
            }}
        """)
        clear_btn.clicked.connect(self._clear_tracked)
        header_layout.addWidget(clear_btn)
        
        layout.addWidget(header)
        
        # 说明
        hint = QLabel(
            "此窗口显示所有触发过智能信号的板块曲线。"
            "这些板块将持续追踪显示，不受主图表筛选影响，直到程序关闭或手动清空。"
        )
        hint.setStyleSheet(f"color: {COLORS['neutral']}; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        
        # ===== 图表区域 =====
        self._chart = MoneyFlowChart()
        self._chart.set_y_max_limit(500)
        layout.addWidget(self._chart, stretch=1)
        
        # ===== 追踪详情表格 =====
        detail_title = QLabel("📋 追踪板块详情")
        detail_title.setStyleSheet(f"color: {COLORS['text']}; font-size: 14px; font-weight: bold;")
        layout.addWidget(detail_title)
        
        self._detail_table = QTableWidget()
        self._detail_table.setColumnCount(5)
        self._detail_table.setHorizontalHeaderLabels(["板块代码", "板块名称", "信号类型", "首次触发", "最新净值"])
        self._detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._detail_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._detail_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._detail_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._detail_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._detail_table.setAlternatingRowColors(True)
        self._detail_table.setMaximumHeight(180)
        self._detail_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text']};
                font-size: 12px;
                border: none;
            }}
            QHeaderView::section {{
                background-color: {COLORS['toolbar_bg']};
                color: {COLORS['text']};
                font-weight: bold;
                padding: 4px;
                border: 1px solid {COLORS['border']};
            }}
        """)
        layout.addWidget(self._detail_table)
    
    def add_signal_sectors(self, signals, sector_info_map):
        """
        从信号列表中添加需要追踪的板块
        
        Parameters
        ----------
        signals : list[dict]
            信号列表
        sector_info_map : dict
            {ts_code: {name, ...}}
        """
        changed = False
        
        for sig in signals:
            sig_type = sig.get("signal_type", "")
            ts_codes = sig.get("related_sectors", [])
            time_str = sig.get("timestamp", "")
            
            for ts_code in ts_codes:
                if not ts_code:
                    continue
                
                if ts_code not in self._tracked_sectors:
                    self._tracked_sectors.add(ts_code)
                    changed = True
                
                # 更新备注
                if ts_code not in self._sector_notes:
                    name = sector_info_map.get(ts_code, {}).get("name", ts_code)
                    self._sector_notes[ts_code] = {
                        "name": name,
                        "signal_types": [],
                        "first_time": time_str,
                        "last_time": time_str,
                    }
                
                note = self._sector_notes[ts_code]
                if sig_type not in note["signal_types"]:
                    note["signal_types"].append(sig_type)
                note["last_time"] = time_str
                # 更新名称（可能变化）
                if ts_code in sector_info_map:
                    note["name"] = sector_info_map[ts_code].get("name", note["name"])
        
        if changed:
            self._update_count()
            self._update_detail_table()
    
    def update_data(self, sectors_df, current_time, trade_date):
        """
        更新追踪窗口的图表数据
        
        只传入追踪的板块数据，其他板块忽略。
        """
        if not self._tracked_sectors or sectors_df is None or len(sectors_df) == 0:
            return
        
        # 过滤追踪的板块
        tracked_df = sectors_df[sectors_df["ts_code"].isin(self._tracked_sectors)]
        if len(tracked_df) == 0:
            return
        
        # 调用图表更新
        self._chart.update_data(tracked_df, current_time, trade_date)
        
        # 强制显示所有追踪板块（覆盖 _apply_filter 的结果）
        self._chart._visible_sectors = set(tracked_df["ts_code"].tolist())
        self._chart._update_plot_visibility()
        self._chart._draw_labels()
        
        # 更新净值显示
        self._update_detail_table()
    
    def _update_count(self):
        """更新追踪数量显示"""
        self._count_label.setText(f"追踪: {len(self._tracked_sectors)} 个板块")
    
    def _update_detail_table(self):
        """更新追踪详情表格"""
        records = []
        for ts_code, note in self._sector_notes.items():
            # 获取最新净值
            latest_net = 0
            if hasattr(self._chart, '_sector_info') and ts_code in self._chart._sector_info:
                latest_net = self._chart._sector_info[ts_code].get("net_amount", 0)
            
            type_names = []
            for t in note["signal_types"]:
                type_names.append(SIGNAL_NAMES.get(t, t))
            
            records.append({
                "ts_code": ts_code,
                "name": note["name"],
                "types": "、".join(type_names),
                "first_time": note["first_time"],
                "net": latest_net,
            })
        
        self._detail_table.setRowCount(len(records))
        for i, rec in enumerate(records):
            self._detail_table.setItem(i, 0, QTableWidgetItem(rec["ts_code"]))
            self._detail_table.setItem(i, 1, QTableWidgetItem(rec["name"]))
            
            type_item = QTableWidgetItem(rec["types"])
            type_item.setForeground(QColor(COLORS["primary_btn"]))
            self._detail_table.setItem(i, 2, type_item)
            
            self._detail_table.setItem(i, 3, QTableWidgetItem(rec["first_time"]))
            
            net = rec["net"]
            net_item = QTableWidgetItem(f"{net:+.1f}亿")
            if net > 0:
                net_item.setForeground(QColor(COLORS["positive"]))
            elif net < 0:
                net_item.setForeground(QColor(COLORS["negative"]))
            self._detail_table.setItem(i, 4, net_item)
    
    def _clear_tracked(self):
        """清空所有追踪"""
        self._tracked_sectors.clear()
        self._sector_notes.clear()
        self._chart._history_points.clear()
        self._chart._sector_info.clear()
        self._chart._visible_sectors.clear()
        self._chart._plot_items.clear()
        self._chart._label_items.clear()
        self._chart._clear_plots()
        self._update_count()
        self._update_detail_table()
    
    def _refresh_labels(self):
        """定期刷新标签"""
        if self._tracked_sectors and self._chart._label_items:
            self._chart._draw_labels()
    
    def closeEvent(self, event):
        """关闭时隐藏而非销毁"""
        self.hide()
        event.ignore()

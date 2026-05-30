# -*- coding: utf-8 -*-
"""
板块个股明细面板 - 双击板块名称后按市值分三组显示个股涨跌幅和资金流向
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QScrollArea, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont

from config import COLORS


def _make_table():
    """创建统一的个股明细子表格"""
    table = QTableWidget()
    table.setColumnCount(6)
    table.setHorizontalHeaderLabels([
        "代码", "名称", "市值(亿)", "最新价", "涨跌幅", "主力净流入(亿)"
    ])
    h = table.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.Stretch)
    h.setSectionResizeMode(0, QHeaderView.Fixed)
    h.setSectionResizeMode(1, QHeaderView.Fixed)
    table.setColumnWidth(0, 60)
    table.setColumnWidth(1, 72)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(True)
    table.setStyleSheet(f"""
        QTableWidget {{
            background-color: {COLORS['panel_bg']};
            color: {COLORS['text']};
            font-size: 10px;
            border: none;
            gridline-color: {COLORS['border']};
        }}
        QTableWidget::item {{
            padding: 1px 3px;
        }}
        QHeaderView::section {{
            background-color: {COLORS['toolbar_bg']};
            color: {COLORS['text']};
            font-weight: bold;
            font-size: 10px;
            padding: 2px;
            border: 1px solid {COLORS['border']};
        }}
    """)
    return table


def _make_group_label(text):
    """创建分组标题"""
    label = QLabel(text)
    label.setStyleSheet(f"""
        color: {COLORS['text']};
        font-size: 12px;
        font-weight: bold;
        font-family: "Microsoft YaHei";
        padding: 3px 6px;
        background-color: {COLORS['toolbar_bg']};
        border-radius: 3px;
    """)
    return label


class SectorDetailPanel(QWidget):
    """板块个股明细面板 - 按市值分三组"""

    close_requested = pyqtSignal()

    _GROUPS = [
        (1000, float('inf'), "千亿市值以上"),
        (500, 1000, "500-1000亿"),
        (0, 500, "500亿以下"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._concept_code = ""
        self._concept_name = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 标题栏
        title_bar = QHBoxLayout()
        self._title_label = QLabel("板块个股明细")
        self._title_label.setStyleSheet(f"""
            color: {COLORS['text']};
            font-size: 14px;
            font-weight: bold;
            font-family: "Microsoft YaHei";
        """)
        title_bar.addWidget(self._title_label)
        title_bar.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['neutral']};
                border: none;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {COLORS['text']};
                background-color: {COLORS['button_hover']};
                border-radius: 12px;
            }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        title_bar.addWidget(close_btn)
        layout.addLayout(title_bar)

        # 汇总信息
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(f"""
            color: {COLORS['neutral']};
            font-size: 11px;
            font-family: "Microsoft YaHei";
        """)
        layout.addWidget(self._summary_label)

        # 滚动区域 — 包含三个分组表格
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(6)

        self._group_labels = []
        self._group_tables = []

        for lo, hi, label_text in self._GROUPS:
            glabel = _make_group_label(label_text)
            self._group_labels.append(glabel)
            scroll_layout.addWidget(glabel)

            table = _make_table()
            self._group_tables.append(table)
            scroll_layout.addWidget(table)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

    def apply_theme(self):
        """应用当前主题"""
        from config import COLORS
        self._title_label.setStyleSheet(f"""
            color: {COLORS['text']};
            font-size: 14px;
            font-weight: bold;
            font-family: "Microsoft YaHei";
        """)
        self._summary_label.setStyleSheet(f"""
            color: {COLORS['neutral']};
            font-size: 11px;
            font-family: "Microsoft YaHei";
        """)
        for table in self._group_tables:
            table.setStyleSheet(f"""
                QTableWidget {{
                    background-color: {COLORS['panel_bg']};
                    color: {COLORS['text']};
                    font-size: 10px;
                    border: none;
                    gridline-color: {COLORS['border']};
                }}
                QTableWidget::item {{
                    padding: 1px 3px;
                }}
                QHeaderView::section {{
                    background-color: {COLORS['toolbar_bg']};
                    color: {COLORS['text']};
                    font-weight: bold;
                    font-size: 10px;
                    padding: 2px;
                    border: 1px solid {COLORS['border']};
                }}
            """)
        for label in self._group_labels:
            label.setStyleSheet(f"""
                color: {COLORS['text']};
                font-size: 12px;
                font-weight: bold;
                font-family: "Microsoft YaHei";
                padding: 3px 6px;
                background-color: {COLORS['toolbar_bg']};
                border-radius: 3px;
            """)

    def set_data(self, concept_code, concept_name, df):
        self._concept_code = concept_code
        self._concept_name = concept_name

        self._title_label.setText(f"{concept_name} ({concept_code}) 个股明细")

        if df is None or len(df) == 0:
            self._summary_label.setText("暂无数据")
            for t in self._group_tables:
                t.setRowCount(0)
            return

        # 汇总
        total_inflow = df['net_inflow'].sum()
        up_count = len(df[df['change_pct'] > 0])
        down_count = len(df[df['change_pct'] < 0])
        self._summary_label.setText(
            f"共 {len(df)} 只个股 | 上涨 {up_count} | 下跌 {down_count} | "
            f"主力净流入合计 {total_inflow:+.2f} 亿"
        )

        # 按三组分别填充
        for idx, (lo, hi, _) in enumerate(self._GROUPS):
            label = self._group_labels[idx]
            table = self._group_tables[idx]

            # 筛选该组个股，按涨跌幅降序排列
            mask = (df['market_cap'] >= lo) & (df['market_cap'] < hi)
            group_df = df[mask].sort_values('change_pct', ascending=False)

            # 更新组标题，显示数量和净流入合计
            grp_total = group_df['net_inflow'].sum()
            label.setText(f"{label.text().split(' (')[0]} ({len(group_df)}只, 净流入 {grp_total:+.1f}亿)")

            table.setSortingEnabled(False)
            table.setRowCount(len(group_df))

            for i, (_, row) in enumerate(group_df.iterrows()):
                code = str(row.get('code', ''))
                name = str(row.get('name', ''))
                mcap = row.get('market_cap', 0)
                price = row.get('price', 0)
                change_pct = row.get('change_pct', 0)
                net_inflow = row.get('net_inflow', 0)

                entries = [
                    (code, None),
                    (name, None),
                    (f"{mcap:.0f}", None),
                    (f"{price:.2f}", change_pct),
                    (f"{change_pct:+.2f}%", change_pct),
                    (f"{net_inflow:+.2f}", net_inflow),
                ]

                for col, (text, val_for_color) in enumerate(entries):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if val_for_color is not None:
                        if val_for_color > 0:
                            item.setForeground(QColor(COLORS["positive"]))
                        elif val_for_color < 0:
                            item.setForeground(QColor(COLORS["negative"]))
                    table.setItem(i, col, item)

            table.setSortingEnabled(True)

    def clear_data(self):
        self._concept_code = ""
        self._concept_name = ""
        self._title_label.setText("板块个股明细")
        self._summary_label.setText("")
        for label, t in zip(self._group_labels, self._group_tables):
            label.setText(label.text().split(' (')[0])
            t.setRowCount(0)

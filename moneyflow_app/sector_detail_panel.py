# -*- coding: utf-8 -*-
"""
板块个股明细面板 - 点击板块名称后显示该板块下所有个股的涨跌幅和资金流向
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont

from config import COLORS


class SectorDetailPanel(QWidget):
    """板块个股明细面板"""

    close_requested = pyqtSignal()

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

        # 表格
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "代码", "名称", "最新价", "涨跌幅", "主力净流入(亿)",
            "超大单(亿)", "大单(亿)", "地区"
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 60)
        self._table.setColumnWidth(1, 70)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text']};
                font-size: 11px;
                border: none;
                gridline-color: {COLORS['border']};
            }}
            QTableWidget::item {{
                padding: 2px 4px;
            }}
            QHeaderView::section {{
                background-color: {COLORS['toolbar_bg']};
                color: {COLORS['text']};
                font-weight: bold;
                font-size: 11px;
                padding: 4px;
                border: 1px solid {COLORS['border']};
            }}
        """)
        layout.addWidget(self._table)

    def set_data(self, concept_code, concept_name, df):
        """设置板块个股数据

        Parameters:
        -----------
        concept_code : str
            板块代码
        concept_name : str
            板块名称
        df : DataFrame
            个股数据 [code, name, price, change_pct, net_inflow, ...]
        """
        self._concept_code = concept_code
        self._concept_name = concept_name

        self._title_label.setText(f"{concept_name} ({concept_code}) 个股明细")

        if df is None or len(df) == 0:
            self._summary_label.setText("暂无数据")
            self._table.setRowCount(0)
            return

        # 汇总
        total_inflow = df['net_inflow'].sum()
        up_count = len(df[df['change_pct'] > 0])
        down_count = len(df[df['change_pct'] < 0])
        self._summary_label.setText(
            f"共 {len(df)} 只个股 | 上涨 {up_count} | 下跌 {down_count} | "
            f"主力净流入合计 {total_inflow:+.2f} 亿"
        )

        # 填充表格
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(df))

        for i, (_, row) in enumerate(df.iterrows()):
            code = str(row.get('code', ''))
            name = str(row.get('name', ''))
            price = row.get('price', 0)
            change_pct = row.get('change_pct', 0)
            net_inflow = row.get('net_inflow', 0)
            super_large = row.get('super_large_inflow', 0)
            large = row.get('large_inflow', 0)
            area = str(row.get('area', ''))

            items = [
                (code, None),
                (name, None),
                (f"{price:.2f}", change_pct),
                (f"{change_pct:+.2f}%", change_pct),
                (f"{net_inflow:+.2f}", net_inflow),
                (f"{super_large:+.2f}", super_large),
                (f"{large:+.2f}", large),
                (area, None),
            ]

            for col, (text, value_for_color) in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)

                if value_for_color is not None:
                    if value_for_color > 0:
                        item.setForeground(QColor(COLORS["positive"]))
                    elif value_for_color < 0:
                        item.setForeground(QColor(COLORS["negative"]))

                self._table.setItem(i, col, item)

        self._table.setSortingEnabled(True)
        # 默认按主力净流入降序排列
        self._table.sortByColumn(4, Qt.DescendingOrder)

    def clear_data(self):
        """清空数据"""
        self._concept_code = ""
        self._concept_name = ""
        self._title_label.setText("板块个股明细")
        self._summary_label.setText("")
        self._table.setRowCount(0)

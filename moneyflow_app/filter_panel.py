# -*- coding: utf-8 -*-
"""
筛选面板 - 提供资金流向曲线的筛选功能
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QDoubleSpinBox, QSpinBox, QCheckBox,
    QPushButton, QGroupBox, QComboBox, QLineEdit,
    QSlider, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from config import COLORS


class FilterPanel(QFrame):
    """
    筛选面板组件
    
    提供以下筛选功能：
    1. 最小流入金额 - 只显示净流入 >= 此值的板块
    2. 最大流出金额 - 只显示净流出绝对值 <= 此值的板块  
    3. 显示数量 - 最多显示前N个板块
    4. 板块类型 - 概念/行业
    5. 仅显示流入/流出
    6. 搜索板块名称
    """
    
    # 信号：筛选条件变化时发出
    filter_changed = pyqtSignal(dict)
    refresh_requested = pyqtSignal()
    auto_refresh_toggled = pyqtSignal(bool)
    interval_changed = pyqtSignal(int)
    y_max_changed = pyqtSignal(float)  # Y轴最大值变化，0表示自动
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['panel_bg']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
            }}
            QGroupBox {{
                color: {COLORS['text']};
                font-weight: bold;
                font-size: 12px;
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                margin-top: 6px;
                padding-top: 6px;
                padding-bottom: 4px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
            QLabel {{
                color: #555555;
                font-size: 11px;
            }}
            QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit {{
                background-color: {COLORS['input_bg']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 3px;
                padding: 2px 4px;
                min-height: 18px;
                font-size: 11px;
            }}
            QPushButton {{
                background-color: {COLORS['button_bg']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['button_hover']};
                border-color: #bbbbbb;
            }}
            QPushButton:pressed {{
                background-color: #d0d0d0;
            }}
            QPushButton#primary {{
                background-color: {COLORS['primary_btn']};
                color: #ffffff;
                border-color: {COLORS['primary_btn']};
            }}
            QPushButton#primary:hover {{
                background-color: {COLORS['primary_btn_hover']};
            }}
            QCheckBox {{
                color: #555555;
                font-size: 11px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
            }}
            QSlider::groove:horizontal {{
                border: 1px solid {COLORS['border']};
                height: 5px;
                background: {COLORS['panel_bg']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {COLORS['positive']};
                border: 1px solid #cc0000;
                width: 12px;
                margin: -3px 0;
                border-radius: 6px;
            }}
        """)
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # ===== 标题 =====
        title = QLabel("筛选设置")
        title.setStyleSheet(f"""
            color: {COLORS['text']};
            font-size: 14px;
            font-weight: bold;
            font-family: "Microsoft YaHei";
        """)
        layout.addWidget(title)
        
        # ===== 金额筛选组 =====
        amount_group = QGroupBox("金额筛选（亿元）")
        amount_layout = QVBoxLayout(amount_group)
        
        # 最小流入
        min_inflow_layout = QHBoxLayout()
        min_inflow_layout.addWidget(QLabel("最小净流入:"))
        self._min_inflow_spin = QDoubleSpinBox()
        self._min_inflow_spin.setRange(0, 1000)
        self._min_inflow_spin.setDecimals(1)
        self._min_inflow_spin.setValue(0)
        self._min_inflow_spin.setSuffix(" 亿")
        self._min_inflow_spin.valueChanged.connect(self._on_filter_changed)
        min_inflow_layout.addWidget(self._min_inflow_spin)
        amount_layout.addLayout(min_inflow_layout)
        
        # 最大流出
        max_outflow_layout = QHBoxLayout()
        max_outflow_layout.addWidget(QLabel("最大净流出:"))
        self._max_outflow_spin = QDoubleSpinBox()
        self._max_outflow_spin.setRange(0, 1000)
        self._max_outflow_spin.setDecimals(1)
        self._max_outflow_spin.setValue(0)
        self._max_outflow_spin.setSuffix(" 亿")
        self._max_outflow_spin.setSpecialValueText("不限")
        self._max_outflow_spin.valueChanged.connect(self._on_filter_changed)
        max_outflow_layout.addWidget(self._max_outflow_spin)
        amount_layout.addLayout(max_outflow_layout)
        
        layout.addWidget(amount_group)
        
        # ===== 显示设置组 =====
        display_group = QGroupBox("显示设置")
        display_layout = QVBoxLayout(display_group)
        
        # 流入前N
        inflow_top_layout = QHBoxLayout()
        inflow_top_layout.addWidget(QLabel("流入最多前:"))
        self._inflow_top_n_spin = QSpinBox()
        self._inflow_top_n_spin.setRange(0, 100)
        self._inflow_top_n_spin.setValue(30)
        self._inflow_top_n_spin.setSuffix(" 个")
        self._inflow_top_n_spin.valueChanged.connect(self._on_filter_changed)
        inflow_top_layout.addWidget(self._inflow_top_n_spin)
        display_layout.addLayout(inflow_top_layout)
        
        # 流出前N
        outflow_top_layout = QHBoxLayout()
        outflow_top_layout.addWidget(QLabel("流出最多前:"))
        self._outflow_top_n_spin = QSpinBox()
        self._outflow_top_n_spin.setRange(0, 100)
        self._outflow_top_n_spin.setValue(30)
        self._outflow_top_n_spin.setSuffix(" 个")
        self._outflow_top_n_spin.valueChanged.connect(self._on_filter_changed)
        outflow_top_layout.addWidget(self._outflow_top_n_spin)
        display_layout.addLayout(outflow_top_layout)
        
        # 仅显示流入/流出选项（与TopN联动：勾选后另一边自动为0）
        self._show_inflow_only = QCheckBox("仅显示资金流入")
        self._show_inflow_only.stateChanged.connect(self._on_inflow_only_changed)
        display_layout.addWidget(self._show_inflow_only)
        
        self._show_outflow_only = QCheckBox("仅显示资金流出")
        self._show_outflow_only.stateChanged.connect(self._on_outflow_only_changed)
        display_layout.addWidget(self._show_outflow_only)
        
        # 搜索框
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("输入板块名称...")
        self._search_edit.textChanged.connect(self._on_filter_changed)
        search_layout.addWidget(self._search_edit)
        display_layout.addLayout(search_layout)
        
        # 异常波动阈值
        spike_layout = QHBoxLayout()
        spike_layout.addWidget(QLabel("异动阈值:"))
        self._spike_threshold_spin = QSpinBox()
        self._spike_threshold_spin.setRange(0, 100)
        self._spike_threshold_spin.setValue(20)
        self._spike_threshold_spin.setSuffix(" %")
        self._spike_threshold_spin.setToolTip("净流入相对变化超过此百分比时，曲线加粗并记录")
        self._spike_threshold_spin.valueChanged.connect(self._on_filter_changed)
        spike_layout.addWidget(self._spike_threshold_spin)
        display_layout.addLayout(spike_layout)
        
        # Y轴最大值
        y_max_layout = QHBoxLayout()
        y_max_layout.addWidget(QLabel("Y轴最大:"))
        self._y_max_spin = QDoubleSpinBox()
        self._y_max_spin.setRange(0, 5000)
        self._y_max_spin.setDecimals(0)
        self._y_max_spin.setValue(0)
        self._y_max_spin.setSuffix(" 亿")
        self._y_max_spin.setSpecialValueText("自动")
        self._y_max_spin.setToolTip("设置Y轴固定最大值，0表示自动适应")
        self._y_max_spin.valueChanged.connect(self._on_y_max_changed)
        y_max_layout.addWidget(self._y_max_spin)
        display_layout.addLayout(y_max_layout)
        
        layout.addWidget(display_group)
        
        # ===== 自动刷新设置 =====
        refresh_group = QGroupBox("刷新设置")
        refresh_layout = QVBoxLayout(refresh_group)
        
        # 自动刷新开关
        self._auto_refresh_check = QCheckBox("自动刷新")
        self._auto_refresh_check.setChecked(True)
        self._auto_refresh_check.stateChanged.connect(self._on_auto_refresh_toggled)
        refresh_layout.addWidget(self._auto_refresh_check)
        
        # 刷新间隔
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("刷新间隔:"))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(1, 3600)
        self._interval_spin.setValue(60)
        self._interval_spin.setSuffix(" 秒")
        self._interval_spin.valueChanged.connect(self.interval_changed.emit)
        interval_layout.addWidget(self._interval_spin)
        refresh_layout.addLayout(interval_layout)
        
        layout.addWidget(refresh_group)
        
        # ===== 操作按钮 =====
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)
        
        self._refresh_btn = QPushButton("立即刷新")
        self._refresh_btn.setObjectName("primary")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        btn_layout.addWidget(self._refresh_btn)
        
        self._reset_btn = QPushButton("重置筛选")
        self._reset_btn.clicked.connect(self._reset_filters)
        btn_layout.addWidget(self._reset_btn)
        
        layout.addLayout(btn_layout)
        
        # 弹性空间
        layout.addStretch()
        
        # 状态标签
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {COLORS['neutral']}; font-size: 11px;")
        layout.addWidget(self._status_label)
    
    def _on_filter_changed(self):
        """筛选条件变化时发出信号"""
        filters = self.get_filters()
        self.filter_changed.emit(filters)
    
    def _on_inflow_only_changed(self, state):
        """仅显示流入时，自动将流出前N设为0"""
        if state == Qt.Checked:
            self._show_outflow_only.setChecked(False)
            self._outflow_top_n_spin.setValue(0)
        else:
            if self._outflow_top_n_spin.value() == 0:
                self._outflow_top_n_spin.setValue(30)
        self._on_filter_changed()
    
    def _on_outflow_only_changed(self, state):
        """仅显示流出时，自动将流入前N设为0"""
        if state == Qt.Checked:
            self._show_inflow_only.setChecked(False)
            self._inflow_top_n_spin.setValue(0)
        else:
            if self._inflow_top_n_spin.value() == 0:
                self._inflow_top_n_spin.setValue(30)
        self._on_filter_changed()
    
    def _on_y_max_changed(self, value):
        """Y轴最大值变化"""
        self.y_max_changed.emit(value)
    
    def _on_auto_refresh_toggled(self, state):
        """自动刷新开关"""
        self.auto_refresh_toggled.emit(state == Qt.Checked)
    
    def get_interval(self):
        """获取当前刷新间隔（秒）"""
        return self._interval_spin.value()
    
    def _reset_filters(self):
        """重置所有筛选条件"""
        self._min_inflow_spin.setValue(0)
        self._max_outflow_spin.setValue(0)
        self._inflow_top_n_spin.setValue(30)
        self._outflow_top_n_spin.setValue(30)
        self._show_inflow_only.setChecked(False)
        self._show_outflow_only.setChecked(False)
        self._search_edit.clear()
        self._y_max_spin.setValue(0)
        self._on_filter_changed()
    
    def get_filters(self):
        """
        获取当前筛选条件
        
        Returns:
            dict: {
                'min_inflow': float or None,
                'max_outflow': float or None,
                'top_n': int,
                'sector_type': str,
                'inflow_only': bool,
                'outflow_only': bool,
                'search': str
            }
        """
        min_inflow = self._min_inflow_spin.value()
        max_outflow = self._max_outflow_spin.value()
        
        return {
            "min_inflow": min_inflow if min_inflow > 0 else None,
            "max_outflow": -max_outflow if max_outflow > 0 else None,
            "inflow_top_n": self._inflow_top_n_spin.value(),
            "outflow_top_n": self._outflow_top_n_spin.value(),
            "inflow_only": self._show_inflow_only.isChecked(),
            "outflow_only": self._show_outflow_only.isChecked(),
            "search": self._search_edit.text().strip(),
            "spike_threshold": self._spike_threshold_spin.value(),
        }
    
    def set_status(self, message):
        """设置状态信息"""
        self._status_label.setText(message)
    
    def set_auto_refresh(self, enabled):
        """设置自动刷新状态"""
        self._auto_refresh_check.setChecked(enabled)

# -*- coding: utf-8 -*-
"""
主窗口 - 实时资金流向监控工具的主界面
整合指数栏、筛选面板、图表和数据更新
"""

import sys
import traceback
from datetime import datetime, time as dt_time

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QStatusBar, QLabel, QProgressBar, QSplitter,
    QMessageBox, QApplication, QAction, QMenu, QToolBar,
    QDialog, QLineEdit, QFormLayout, QDialogButtonBox,
    QDockWidget, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject, QSize
from PyQt5.QtGui import QIcon, QFont, QColor

from config import COLORS, INDEX_CODES, UPDATE_INTERVAL_MS
from data_fetcher import DataFetcher
from chart_widget import MoneyFlowChart, IndexBar
from filter_panel import FilterPanel
from sector_detail_panel import SectorDetailPanel


class DataUpdateSignals(QObject):
    """数据更新信号"""
    data_ready = pyqtSignal(dict)  # 数据准备好
    index_ready = pyqtSignal(dict)  # 指数数据准备好
    progress = pyqtSignal(int, str)  # 进度更新
    error = pyqtSignal(str)  # 错误信息


class DataUpdateWorker(QThread):
    """数据更新工作线程 - 在后台获取数据避免UI卡顿"""

    def __init__(self, fetcher):
        super().__init__()
        self.fetcher = fetcher
        self.signals = DataUpdateSignals()
        self._running = True

    def run(self):
        """执行数据获取"""
        try:
            self.signals.progress.emit(0, "正在获取数据...")

            # 获取指数数据
            index_data = self.fetcher.get_index_realtime()
            if index_data:
                self.signals.index_ready.emit(index_data)

            self.signals.progress.emit(30, "正在获取概念板块资金流向...")

            # 获取板块资金流向数据
            result = self.fetcher.calculate_realtime_moneyflow(
                progress_callback=lambda p, m: self.signals.progress.emit(30 + int(p * 0.7), m)
            )

            if result and result.get("sectors") is not None and len(result.get("sectors", [])) > 0:
                self.signals.data_ready.emit(result)
                self.signals.progress.emit(100, "数据更新完成")
            else:
                self.signals.error.emit("获取数据失败，请检查网络连接")

        except Exception as e:
            print(f"[Worker] 数据获取失败: {e}")
            traceback.print_exc()
            self.signals.error.emit(str(e))

    def stop(self):
        """停止线程"""
        self._running = False
        self.wait(1000)


class SectorDetailSignals(QObject):
    """板块个股明细信号"""
    detail_ready = pyqtSignal(object, str, str)  # df, concept_code, concept_name


class SectorDetailWorker(QThread):
    """板块个股明细获取工作线程"""

    def __init__(self, fetcher, concept_code, concept_name):
        super().__init__()
        self.fetcher = fetcher
        self.concept_code = concept_code
        self.concept_name = concept_name
        self.signals = SectorDetailSignals()

    def run(self):
        try:
            df = self.fetcher.get_concept_detail(self.concept_code)
            self.signals.detail_ready.emit(df, self.concept_code, self.concept_name)
        except Exception as e:
            print(f"[SectorDetailWorker] 获取个股明细失败: {e}")
            self.signals.detail_ready.emit(None, self.concept_code, self.concept_name)


class SettingsDialog(QDialog):
    """设置对话框 - 配置Tushare Token等"""
    
    def __init__(self, parent=None, token=""):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedSize(500, 200)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLORS['background']};
            }}
            QLabel {{
                color: {COLORS['text']};
                font-size: 13px;
            }}
            QLineEdit {{
                background-color: {COLORS['input_bg']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px;
                font-size: 12px;
            }}
            QPushButton {{
                background-color: {COLORS['button_bg']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 8px 20px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['button_hover']};
            }}
        """)
        
        layout = QFormLayout(self)
        
        # Token输入
        self._token_edit = QLineEdit(token)
        self._token_edit.setEchoMode(QLineEdit.Password)
        self._token_edit.setPlaceholderText("请输入Tushare Pro Token（用于指数数据）")
        layout.addRow("Tushare Token:", self._token_edit)
        
        # 说明标签
        hint = QLabel("提示: Token可在 https://tushare.pro/ 个人主页获取\n"
                     "概念板块资金流向数据来自东方财富，无需Token")
        hint.setStyleSheet(f"color: {COLORS['neutral']}; font-size: 11px;")
        layout.addRow(hint)
        
        # 按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)
    
    def get_token(self):
        """获取输入的Token"""
        return self._token_edit.text().strip()


class MainWindow(QMainWindow):
    """
    主窗口
    
    布局：
    - 顶部：工具栏
    - 上部：指数栏（上证/深证/创业板）
    - 中部：筛选面板 + 图表区域
    - 底部：状态栏
    """
    
    def __init__(self, use_mock=False, use_proxy=False):
        super().__init__()
        
        # 窗口设置：初始大小为屏幕的 1/2，并居中显示
        self.setWindowTitle("实时板块资金流向监控")
        self.setMinimumSize(800, 600)
        screen = QApplication.primaryScreen().availableGeometry()
        init_w = screen.width() // 2
        init_h = screen.height() // 2
        self.resize(init_w, init_h)
        self.move(screen.width() // 4, screen.height() // 4)
        
        # 数据获取器
        self._fetcher = None
        self._current_sector_list = None
        self._current_filters = {}
        self._last_data = None
        self._use_mock = use_mock
        self._use_proxy = use_proxy
        
        # 初始化UI
        self._init_ui()
        
        # 初始化数据
        self._init_data()
        
        # 定时器
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._on_auto_update)
        self._update_timer.start(UPDATE_INTERVAL_MS)
        
        # 应用样式
        self._apply_style()
        
        print("[MainWindow] 主窗口初始化完成")
    
    def _init_ui(self):
        """初始化UI"""
        # 中央部件
        central = QWidget()
        self.setCentralWidget(central)
        
        # 主布局
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # ===== 工具栏 =====
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet(f"""
            QToolBar {{
                background-color: {COLORS['toolbar_bg']};
                border: none;
                border-bottom: 1px solid {COLORS['border']};
                spacing: 10px;
            }}
            QToolButton {{
                color: {COLORS['text']};
                font-size: 13px;
                padding: 4px 12px;
            }}
        """)
        
        # 设置按钮
        self._settings_action = QAction("⚙ 设置", self)
        self._settings_action.triggered.connect(self._show_settings)
        toolbar.addAction(self._settings_action)
        
        # 刷新按钮
        self._refresh_action = QAction("⟳ 刷新", self)
        self._refresh_action.triggered.connect(self._manual_refresh)
        toolbar.addAction(self._refresh_action)
        
        self.addToolBar(toolbar)
        
        # ===== 指数栏 =====
        self._index_bar = IndexBar()
        main_layout.addWidget(self._index_bar)
        
        # ===== 主体区域（筛选 + 图表） =====
        body_splitter = QSplitter(Qt.Horizontal)
        
        # 筛选面板（最小宽度保证按钮文字能完整显示）
        self._filter_panel = FilterPanel()
        self._filter_panel.setMinimumWidth(260)
        self._filter_panel.filter_changed.connect(self._on_filter_changed)
        self._filter_panel.refresh_requested.connect(self._manual_refresh)
        self._filter_panel.auto_refresh_toggled.connect(self._on_auto_refresh_toggled)
        self._filter_panel.interval_changed.connect(self._on_interval_changed)
        self._filter_panel.y_max_changed.connect(self._on_y_max_changed)
        body_splitter.addWidget(self._filter_panel)
        
        # 图表区域
        chart_container = QWidget()
        chart_layout = QVBoxLayout(chart_container)
        chart_layout.setContentsMargins(8, 8, 8, 8)
        chart_layout.setSpacing(4)
        
        # 标题
        title_container = QWidget()
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        self._title_label = QLabel("板块资金实时分时流向")
        self._title_label.setStyleSheet(f"""
            color: {COLORS['text']};
            font-size: 16px;
            font-weight: bold;
            font-family: "Microsoft YaHei", "SimHei";
        """)
        title_layout.addWidget(self._title_label)
        
        # 数据来源标签
        self._source_label = QLabel("")
        self._source_label.setStyleSheet(f"color: {COLORS['neutral']}; font-size: 11px;")
        title_layout.addStretch()
        title_layout.addWidget(self._source_label)
        
        chart_layout.addWidget(title_container)
        
        # 图表
        self._chart = MoneyFlowChart()
        self._chart.signals.sector_clicked.connect(self._on_sector_clicked)
        chart_layout.addWidget(self._chart)
        
        body_splitter.addWidget(chart_container)
        body_splitter.setStretchFactor(1, 1)
        # 左侧保证至少能放下筛选面板（260px），右侧占剩余空间
        left_w = max(260, int(self.width() * 0.25))
        right_w = max(300, self.width() - left_w)
        body_splitter.setSizes([left_w, right_w])
        
        main_layout.addWidget(body_splitter, stretch=1)
        
        # ===== 状态栏 =====
        self._status_bar = QStatusBar()
        self._status_bar.setStyleSheet(f"""
            QStatusBar {{
                background-color: {COLORS['toolbar_bg']};
                color: {COLORS['neutral']};
                font-size: 11px;
                border-top: 1px solid {COLORS['border']};
            }}
        """)
        self.setStatusBar(self._status_bar)
        
        # 状态标签
        self._status_label = QLabel("就绪")
        self._status_bar.addWidget(self._status_label)
        
        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.setMaximumHeight(16)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                text-align: center;
                color: {COLORS['text']};
                font-size: 10px;
                background-color: {COLORS['input_bg']};
            }}
            QProgressBar::chunk {{
                background-color: {COLORS['positive']};
                border-radius: 4px;
            }}
        """)
        self._progress_bar.hide()
        self._status_bar.addPermanentWidget(self._progress_bar)
        
        # 数据时间标签
        self._data_time_label = QLabel("")
        self._data_time_label.setStyleSheet(f"color: {COLORS['neutral']}; font-size: 11px;")
        self._status_bar.addPermanentWidget(self._data_time_label)
        
        # ===== 异动记录浮动面板（DockWidget） =====
        self._spike_dock = QDockWidget("异动记录", self)
        self._spike_dock.setFeatures(
            QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable
        )
        self._spike_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        
        self._spike_table = QTableWidget()
        self._spike_table.setColumnCount(5)
        self._spike_table.setHorizontalHeaderLabels(["时间", "板块", "变化%", "变化(亿)", "当前(亿)"])
        self._spike_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._spike_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._spike_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._spike_table.setAlternatingRowColors(True)
        self._spike_table.setStyleSheet(f"""
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
        self._spike_dock.setWidget(self._spike_table)
        self.addDockWidget(Qt.RightDockWidgetArea, self._spike_dock)

        # ===== 板块个股明细面板（DockWidget） =====
        self._sector_detail_panel = SectorDetailPanel()
        self._sector_detail_panel.close_requested.connect(self._hide_sector_detail)

        self._sector_detail_dock = QDockWidget("板块个股明细", self)
        self._sector_detail_dock.setFeatures(
            QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable
        )
        self._sector_detail_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._sector_detail_dock.setWidget(self._sector_detail_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self._sector_detail_dock)
        self._sector_detail_dock.hide()  # 默认隐藏，点击板块后才显示
    
    def _apply_style(self):
        """应用全局样式"""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLORS['background']};
            }}
            QWidget {{
                background-color: {COLORS['background']};
            }}
            QMenuBar {{
                background-color: {COLORS['toolbar_bg']};
                color: {COLORS['text']};
                border-bottom: 1px solid {COLORS['border']};
            }}
            QMenuBar::item {{
                background-color: transparent;
                padding: 4px 12px;
            }}
            QMenuBar::item:selected {{
                background-color: {COLORS['button_hover']};
            }}
            QMenu {{
                background-color: {COLORS['background']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
            }}
            QMenu::item:selected {{
                background-color: {COLORS['button_hover']};
            }}
            QSplitter::handle {{
                background-color: {COLORS['border']};
            }}
            QSplitter::handle:horizontal {{
                width: 4px;
            }}
        """)
    
    def _init_data(self):
        """初始化数据"""
        try:
            # 初始化数据获取器
            self._fetcher = DataFetcher(use_mock=self._use_mock, use_proxy=self._use_proxy)
            
            if not self._fetcher.is_initialized():
                self._filter_panel.set_status(
                    "Tushare API初始化失败（指数数据不可用），概念板块资金流向仍可用"
                )
            else:
                self._filter_panel.set_status("数据获取器已就绪")
            
            # 首次数据获取
            self._start_data_update()
            
        except Exception as e:
            print(f"[MainWindow] 初始化数据失败: {e}")
            traceback.print_exc()
            self._show_error(f"初始化失败: {e}")
    
    def _start_data_update(self):
        """启动数据更新线程"""
        if self._fetcher is None:
            return
        
        self._status_label.setText("正在更新数据...")
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        
        # 创建工作线程
        self._worker = DataUpdateWorker(self._fetcher)
        self._worker.signals.data_ready.connect(self._on_data_ready)
        self._worker.signals.index_ready.connect(self._on_index_ready)
        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.error.connect(self._on_data_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()
    
    def _on_data_ready(self, result):
        """数据准备好回调"""
        try:
            self._last_data = result
            
            sectors_df = result.get("sectors")
            current_time = result.get("timestamp", "")
            trade_date = result.get("trade_date", "")
            data_source = result.get("data_source", "")
            
            if sectors_df is not None and len(sectors_df) > 0:
                # 更新图表（追加当前时间点到历史记录）
                self._chart.update_data(sectors_df, current_time, trade_date)
                
                # 更新标题
                self._title_label.setText("板块资金实时分时流向")
                
                # 更新数据源标签
                if "simulated" in data_source:
                    source_text = "数据源: 模拟数据"
                else:
                    source_text = "数据源: 东方财富 实时"
                self._source_label.setText(source_text)
                
                # 更新时间
                time_display = current_time
                if trade_date:
                    time_display = f"{trade_date} {current_time}"
                self._data_time_label.setText(f"数据时间: {time_display}")
                
                # 应用当前筛选
                self._apply_current_filters()
                
                visible_count = len(self._chart._visible_sectors) if hasattr(self._chart, '_visible_sectors') else 0
                self._status_label.setText(
                    f"共 {len(sectors_df)} 个板块 | 显示 {visible_count} 条曲线"
                )
                
                # 更新异动记录表格
                self._update_spike_table()
            else:
                self._status_label.setText("暂无数据")
                
        except Exception as e:
            print(f"[MainWindow] 处理数据失败: {e}")
            traceback.print_exc()
    
    def _update_spike_table(self):
        """更新异动记录表格"""
        try:
            records = self._chart.get_spike_records(limit=200)
            self._spike_table.setRowCount(len(records))
            for i, rec in enumerate(records):
                self._spike_table.setItem(i, 0, QTableWidgetItem(str(rec.get("time", ""))))
                self._spike_table.setItem(i, 1, QTableWidgetItem(str(rec.get("name", ""))))
                pct = rec.get("change_pct", 0)
                self._spike_table.setItem(i, 2, QTableWidgetItem(f"{pct:+.1f}%"))
                amt = rec.get("change_amount", 0)
                self._spike_table.setItem(i, 3, QTableWidgetItem(f"{amt:+.2f}"))
                cur = rec.get("current_amount", 0)
                self._spike_table.setItem(i, 4, QTableWidgetItem(f"{cur:.2f}"))
                
                # 根据正负设置文字颜色
                for col in range(5):
                    item = self._spike_table.item(i, col)
                    if item:
                        if pct > 0:
                            item.setForeground(QColor(COLORS["positive"]))
                        elif pct < 0:
                            item.setForeground(QColor(COLORS["negative"]))
            # 滚动到最新记录
            if records:
                self._spike_table.scrollToBottom()
        except Exception as e:
            print(f"[MainWindow] 更新异动表格失败: {e}")
    
    def _on_index_ready(self, index_data):
        """指数数据准备好回调"""
        self._index_bar.update_index(index_data)
    
    def _on_progress(self, pct, message):
        """进度更新"""
        self._progress_bar.setValue(pct)
        self._filter_panel.set_status(message)
    
    def _on_data_error(self, error_msg):
        """数据错误回调"""
        self._status_label.setText(f"错误: {error_msg}")
        self._progress_bar.hide()
    
    def _on_worker_finished(self):
        """工作线程完成"""
        self._progress_bar.hide()
    
    def _on_auto_update(self):
        """自动更新"""
        if not hasattr(self, '_auto_refresh') or self._auto_refresh:
            self._start_data_update()
    
    def _manual_refresh(self):
        """手动刷新"""
        self._start_data_update()
    
    def _on_auto_refresh_toggled(self, enabled):
        """自动刷新开关"""
        self._auto_refresh = enabled
        if enabled:
            self._update_timer.start()
        else:
            self._update_timer.stop()
    
    def _on_interval_changed(self, seconds):
        """刷新间隔变化"""
        # 非 mock 模式下，最低间隔强制为 5 秒（避免真实请求过频被封）
        if not self._use_mock and seconds < 5:
            seconds = 5
            self._filter_panel._interval_spin.setValue(5)
            print(f"[MainWindow] 非模拟模式下刷新间隔不能低于 5 秒，已强制调整为 5")
        self._update_timer.setInterval(seconds * 1000)
        # 同步调整概念板块缓存时间，略小于刷新间隔，避免缓存导致刷新不生效
        if self._fetcher is not None:
            ttl = max(1, seconds - 2)
            self._fetcher._concept_cache_ttl = ttl
            self._fetcher._fetch_time_window = seconds
    
    def _on_y_max_changed(self, value):
        """Y轴最大值变化"""
        if value > 0:
            self._chart.set_y_max_limit(value)
        else:
            self._chart.set_y_max_limit(None)
    
    def _on_filter_changed(self, filters):
        """筛选条件变化"""
        self._current_filters = filters
        self._apply_current_filters()
    
    def _apply_current_filters(self):
        """应用当前筛选条件"""
        if not self._current_filters or not self._last_data:
            return
        
        try:
            sectors_df = self._last_data.get("sectors")
            if sectors_df is None:
                return
            
            # 获取筛选条件
            filters = self._current_filters
            min_inflow = filters.get("min_inflow")
            max_outflow = filters.get("max_outflow")
            inflow_top_n = filters.get("inflow_top_n", 30)
            outflow_top_n = filters.get("outflow_top_n", 30)
            inflow_only = filters.get("inflow_only", False)
            outflow_only = filters.get("outflow_only", False)
            search = filters.get("search", "")
            
            # 仅显示流入/流出时，将另一边数量设为0
            if inflow_only:
                outflow_top_n = 0
            if outflow_only:
                inflow_top_n = 0
            
            # 应用到图表
            spike_threshold = filters.get("spike_threshold", 20)
            self._chart.set_filter(
                min_inflow=min_inflow,
                max_outflow=max_outflow,
                inflow_top_n=inflow_top_n,
                outflow_top_n=outflow_top_n,
                spike_threshold=spike_threshold
            )
            
            # 搜索过滤
            if search and hasattr(self._chart, '_visible_sectors'):
                for ts_code in list(self._chart._visible_sectors):
                    info = self._chart._sector_info.get(ts_code, {})
                    if search.lower() not in info.get("name", "").lower():
                        self._chart._visible_sectors.discard(ts_code)
                self._chart._update_plot_visibility()
            
            # 更新状态
            visible_count = len(self._chart._visible_sectors) if hasattr(self._chart, '_visible_sectors') else 0
            self._status_label.setText(
                f"共 {len(sectors_df)} 个板块 | "
                f"显示 {visible_count} 条曲线"
            )
            
        except Exception as e:
            print(f"[MainWindow] 应用筛选失败: {e}")
    
    def _show_settings(self):
        """显示设置对话框"""
        token = self._fetcher.token if self._fetcher else ""
        dialog = SettingsDialog(self, token)
        
        if dialog.exec_() == QDialog.Accepted:
            new_token = dialog.get_token()
            if new_token:
                # 重新初始化数据获取器
                self._fetcher = DataFetcher(token=new_token, use_mock=self._use_mock, use_proxy=self._use_proxy)
                if self._fetcher.is_initialized():
                    self._show_info("Token已更新，正在重新获取数据...")
                    self._init_data()
                else:
                    self._show_error("Token验证失败")
    
    def _show_error(self, message):
        """显示错误信息"""
        QMessageBox.critical(self, "错误", message)
    
    def _show_info(self, message):
        """显示信息"""
        self._status_label.setText(message)
    
    def _on_sector_clicked(self, ts_code, name):
        """板块点击回调 - 获取个股明细并显示"""
        if self._fetcher is None:
            return

        print(f"[MainWindow] 板块被点击: {name} ({ts_code})")

        # 更新 dock 标题
        self._sector_detail_dock.setWindowTitle(f"板块个股明细 - {name}")

        # 显示加载状态
        self._sector_detail_panel._title_label.setText(f"{name} ({ts_code}) 个股明细")
        self._sector_detail_panel._summary_label.setText("正在加载...")
        self._sector_detail_dock.show()
        self._sector_detail_dock.raise_()

        # 在后台线程获取数据
        self._detail_worker = SectorDetailWorker(self._fetcher, ts_code, name)
        self._detail_worker.signals.detail_ready.connect(self._on_sector_detail_ready)
        self._detail_worker.start()

    def _on_sector_detail_ready(self, df, code, sector_name):
        """板块个股明细数据就绪"""
        self._sector_detail_panel.set_data(code, sector_name, df)

    def _hide_sector_detail(self):
        """隐藏板块个股明细面板"""
        self._sector_detail_dock.hide()

    def closeEvent(self, event):
        """关闭事件"""
        # 停止定时器
        self._update_timer.stop()
        
        # 停止工作线程
        if hasattr(self, '_worker') and self._worker.isRunning():
            self._worker.stop()
        
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 设置应用字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

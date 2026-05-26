# -*- coding: utf-8 -*-
"""
图表组件 - 实时资金流向分时图
使用pyqtgraph实现高性能实时折线图

核心逻辑：
- moneyflow_cnt_ths 返回的是当前时刻的当日累计净流入
- 程序运行期间，每次刷新将当前 (time, net_amount) 追加到历史记录
- 绘制从当前时刻开始的累计折线
- X轴显示真实北京时间分时刻度
"""

import pyqtgraph as pg
from pyqtgraph import PlotWidget, mkPen, InfiniteLine, TextItem
import numpy as np
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QColor, QFont
from datetime import datetime
import traceback

from config import COLORS


def time_str_to_seconds(time_str):
    """把时间字符串 HH:MM[:SS] 转为从00:00:00开始的秒数"""
    parts = time_str.split(':')
    h = int(parts[0])
    m = int(parts[1])
    s = int(parts[2]) if len(parts) > 2 else 0
    return h * 3600 + m * 60 + s


def seconds_to_time_str(total_seconds, show_seconds=False):
    """把秒数转回时间字符串"""
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    if show_seconds:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{h:02d}:{m:02d}"


class TimeAxisItem(pg.AxisItem):
    """自定义时间轴 - 根据数据范围自动选择合适的秒级/分级刻度"""
    
    def tickValues(self, minVal, maxVal, size):
        minVal, maxVal = sorted((minVal, maxVal))
        range_size = maxVal - minVal
        if range_size <= 0:
            return []
        
        # 根据显示范围自动选择合适的间隔
        if range_size <= 30:
            spacing = 5       # 5秒
        elif range_size <= 120:
            spacing = 10      # 10秒
        elif range_size <= 300:
            spacing = 30      # 30秒
        elif range_size <= 900:
            spacing = 60      # 1分钟
        elif range_size <= 3600:
            spacing = 300     # 5分钟
        elif range_size <= 7200:
            spacing = 600     # 10分钟
        else:
            spacing = 1800    # 30分钟
        
        start = (int(minVal) // spacing) * spacing
        values = []
        v = start
        while v <= maxVal:
            if v >= minVal:
                values.append(v)
            v += spacing
        
        return [(spacing, values)] if values else []
    
    def tickStrings(self, values, scale, spacing):
        result = []
        for v in values:
            total = int(v)
            h = total // 3600
            m = (total % 3600) // 60
            s = total % 60
            result.append(f"{h:02d}:{m:02d}:{s:02d}")
        return result


class ChartSignals(QObject):
    """图表信号"""
    sector_clicked = pyqtSignal(str, str)  # ts_code, name


class MoneyFlowChart(PlotWidget):
    """
    实时资金流向分时图组件
    
    功能：
    1. 累积记录每次刷新的 (time, net_amount) 点
    2. 绘制从当前时刻开始的累计折线
    3. X轴显示真实北京时间
    4. 颜色区分（红色流入/绿色流出）
    5. 实时更新
    """
    
    def __init__(self, parent=None):
        # 使用自定义时间轴
        bottom_axis = TimeAxisItem(orientation='bottom')
        super().__init__(parent, axisItems={'bottom': bottom_axis})
        self.signals = ChartSignals()
        
        # 历史数据累积 {ts_code: [(time_str, net_amount), ...]}
        self._history_points = {}
        # 板块信息 {ts_code: {name, net_amount, pct_change, color}}
        self._sector_info = {}
        # 当前可见的板块代码
        self._visible_sectors = set()
        # 绘图项
        self._plot_items = {}       # {ts_code: PlotDataItem}
        self._label_items = {}      # {ts_code: TextItem}
        self._label_data_positions = {}  # {ts_code: (data_x, data_y)} 用于缩放时重定位
        
        # 鼠标悬停 tooltip
        self._tooltip = TextItem(text="", color=QColor("#333333"), anchor=(0, 1))
        self._tooltip.setFont(QFont("Microsoft YaHei", 10))
        self._tooltip.hide()
        
        # 当前数据日期，用于判断是否需要清空历史
        self._current_trade_date = ""
        
        # 图表配置
        self._max_sectors = 50
        
        # 视图初始化标志：第一次加载数据后自动调整范围，之后保留用户缩放/平移状态
        self._view_initialized = False
        
        # 筛选条件
        self._filter_min_inflow = None
        self._filter_max_outflow = None
        self._filter_inflow_top_n = 30
        self._filter_outflow_top_n = 30
        
        # 异常波动监控
        self._spike_threshold = 20  # 百分比阈值，0表示关闭
        self._spike_records = []    # 记录列表 [{time, name, change_pct, change_amount}, ...]
        self._spike_sectors = set() # 当前触发异常的板块代码
        
        # Y轴最大值限制（亿元），None表示自动适应
        self._y_max_limit = None
        
        # 初始化图表样式
        self._init_style()
        
        # 定时器
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._on_timer)
        
    def _init_style(self):
        """初始化图表样式 - 白色清爽主题"""
        # 背景色
        self.setBackground(QColor(COLORS["background"]))
        
        # 显示网格
        self.showGrid(x=True, y=True, alpha=0.3)
        
        # 坐标轴样式 - 使用深色文字确保清晰
        self.getAxis("bottom").setPen(pg.mkPen(color="#999999"))
        self.getAxis("left").setPen(pg.mkPen(color="#999999"))
        self.getAxis("bottom").setTextPen(pg.mkPen(color="#333333"))
        self.getAxis("left").setTextPen(pg.mkPen(color="#333333"))
        
        # 设置标签
        self.setLabel("left", "净流入 (亿元)", color="#666666", size="10px")
        self.setLabel("bottom", "时间", color="#666666", size="10px")
        
        # 鼠标交互：X轴可缩放/平移，Y轴根据是否固定范围决定
        self.setMouseEnabled(x=True, y=True)
        self.enableAutoRange(axis="y")
        self.setAutoVisible(y=True)
        
        # 鼠标悬停追踪
        self.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self._tooltip_target = None
        
        # 添加0轴线
        self._zero_line = InfiniteLine(
            pos=0, 
            angle=0, 
            pen=pg.mkPen(color="#999999", width=1, style=Qt.DashLine)
        )
        self.addItem(self._zero_line)
        
        # 添加 tooltip 到场景
        self.addItem(self._tooltip)

        # 视图范围变化时更新标签位置，使其始终紧贴曲线末端
        self.getViewBox().sigRangeChanged.connect(self._on_view_range_changed)

        # 注意：X轴现在是连续的真实时间秒坐标，不再需要固定午休分隔线
        
    def set_y_max_limit(self, max_value):
        """设置Y轴最大值限制，None表示自动适应"""
        self._y_max_limit = max_value
        vb = self.getViewBox()
        if max_value is not None and max_value > 0:
            # 固定Y轴范围，禁用Y轴鼠标交互和自动范围
            self.disableAutoRange(axis='y')
            self.setMouseEnabled(x=True, y=False)
            self.setAutoVisible(y=False)
            # ViewBox 硬限制：锁定 Y 轴物理边界，仅 X 轴可自由缩放
            vb.setLimits(yMin=-max_value, yMax=max_value,
                         xMin=None, xMax=None)
            self.setYRange(-max_value, max_value, padding=0)
        else:
            # 恢复自动适应
            self.enableAutoRange(axis='y')
            self.setMouseEnabled(x=True, y=True)
            self.setAutoVisible(y=True)
            vb.setLimits(yMin=None, yMax=None,
                         xMin=None, xMax=None)
            self._auto_range()
        # Y轴范围变化后重新计算标签位置
        self._draw_labels()
    
    def set_filter(self, min_inflow=None, max_outflow=None, inflow_top_n=30, outflow_top_n=30, spike_threshold=20):
        """设置筛选条件"""
        self._filter_min_inflow = min_inflow
        self._filter_max_outflow = max_outflow
        self._filter_inflow_top_n = inflow_top_n
        self._filter_outflow_top_n = outflow_top_n
        self._spike_threshold = spike_threshold
        self._apply_filter()
        
    def _detect_spikes(self, time_key):
        """检测异常波动板块，超过阈值则记录并标记加粗"""
        if self._spike_threshold <= 0:
            self._spike_sectors.clear()
            return
        
        threshold = self._spike_threshold
        self._spike_sectors.clear()
        
        for ts_code, info in self._sector_info.items():
            points = self._history_points.get(ts_code, [])
            if len(points) < 2:
                continue
            
            # 取当前值和上一次值
            current_val = points[-1][1]
            prev_val = points[-2][1]
            
            # 避免除0：上次值绝对值小于0.1亿时跳过百分比计算
            if abs(prev_val) < 0.1:
                continue
            
            change_pct = (current_val - prev_val) / abs(prev_val) * 100
            
            if abs(change_pct) >= threshold:
                self._spike_sectors.add(ts_code)
                self._spike_records.append({
                    "time": time_key,
                    "name": info["name"],
                    "change_pct": round(change_pct, 2),
                    "change_amount": round(current_val - prev_val, 2),
                    "current_amount": round(current_val, 2),
                })
                # 只保留最近100条记录，防止内存无限增长
                if len(self._spike_records) > 100:
                    self._spike_records = self._spike_records[-100:]
    
    def get_spike_records(self, limit=20):
        """获取最近的异常波动记录"""
        return self._spike_records[-limit:]
    
    def _apply_filter(self):
        """应用筛选条件，更新可见板块
        
        分别取净流入前N和净流出前N，合并为可见集合。
        """
        if not self._sector_info:
            return
        
        # 1. 先应用金额筛选，得到候选集
        candidates = {}
        for ts_code, info in self._sector_info.items():
            net = info["net_amount"]
            if self._filter_min_inflow is not None and net < self._filter_min_inflow:
                continue
            if self._filter_max_outflow is not None and net < 0 and abs(net) > abs(self._filter_max_outflow):
                continue
            candidates[ts_code] = info
        
        # 2. 分别取流入前N和流出前N
        inflow_items = [(code, info) for code, info in candidates.items() if info["net_amount"] > 0]
        outflow_items = [(code, info) for code, info in candidates.items() if info["net_amount"] < 0]
        
        inflow_items.sort(key=lambda x: x[1]["net_amount"], reverse=True)
        outflow_items.sort(key=lambda x: x[1]["net_amount"])  # 最负的在最前
        
        visible = set()
        for code, _ in inflow_items[:self._filter_inflow_top_n]:
            visible.add(code)
        for code, _ in outflow_items[:self._filter_outflow_top_n]:
            visible.add(code)
        
        self._visible_sectors = visible
        self._update_plot_visibility()
        self._draw_labels()
        
    def _update_plot_visibility(self):
        """更新图表可见性"""
        for ts_code, plot_item in self._plot_items.items():
            plot_item.setVisible(ts_code in self._visible_sectors)
    
    def update_data(self, sectors_df, current_time, trade_date):
        """
        更新图表数据 - 追加当前时间点到历史记录
        
        Parameters:
        -----------
        sectors_df : DataFrame
            板块数据 [ts_code, name, net_amount, pct_change]
        current_time : str
            当前时间 "HH:MM:SS"
        trade_date : str
            数据日期 "YYYYMMDD"
        """
        try:
            # 检查日期是否变化，变化则清空历史并重置视图
            if trade_date and trade_date != self._current_trade_date:
                self._history_points.clear()
                self._current_trade_date = trade_date
                self._view_initialized = False
                print(f"[Chart] 新交易日: {trade_date}, 清空历史数据")
            
            # 使用完整 HH:MM:SS 作为时间键，确保秒级刷新能累积不同点
            time_key = current_time
            
            # 更新板块信息并追加历史点
            new_sectors = {}
            
            for _, row in sectors_df.iterrows():
                ts_code = row.get("ts_code", "")
                name = row.get("name", "")
                net_amount = float(row.get("net_amount", 0))
                pct_change = float(row.get("pct_change", 0))
                
                # 固定颜色：基于板块代码 hash，不随排名变化
                color_idx = hash(ts_code) % len(COLORS["line_colors"])
                line_color = QColor(COLORS["line_colors"][color_idx])
                
                new_sectors[ts_code] = {
                    "name": name,
                    "net_amount": net_amount,
                    "pct_change": pct_change,
                    "color": line_color,
                }
                
                # 追加历史点（所有板块都记录，即使当前不显示）
                if ts_code not in self._history_points:
                    self._history_points[ts_code] = []
                
                # 避免同一秒重复添加
                if self._history_points[ts_code]:
                    last_time, _ = self._history_points[ts_code][-1]
                    if last_time == time_key:
                        self._history_points[ts_code][-1] = (time_key, net_amount)
                    else:
                        self._history_points[ts_code].append((time_key, net_amount))
                else:
                    self._history_points[ts_code].append((time_key, net_amount))
            
            self._sector_info = new_sectors
            
            # 检测异常波动（在筛选前检测所有板块）
            self._detect_spikes(time_key)
            
            # 清除旧绘图
            self._clear_plots()
            
            # 绘制新的曲线
            self._draw_plots()
            
            # 应用筛选（动态切换前N名）
            self._apply_filter()

            # 若 Y 轴已锁定，每次重绘后强制重置，防止 ViewBox 在
            # clear/draw 过程中绕过 disableAutoRange 重新计算范围
            if self._y_max_limit is not None and self._y_max_limit > 0:
                self.setYRange(-self._y_max_limit, self._y_max_limit, padding=0)

            # 自动调整坐标轴范围（仅在第一次加载或换日时）
            if not self._view_initialized:
                self._auto_range()
                self._view_initialized = True
            
        except Exception as e:
            print(f"[Chart] 更新图表数据失败: {e}")
            traceback.print_exc()
    
    def _clear_plots(self):
        """清除所有绘制的曲线和标签"""
        for plot_item in self._plot_items.values():
            self.removeItem(plot_item)
        self._plot_items.clear()
        
        for label in self._label_items.values():
            self.removeItem(label)
        self._label_items.clear()
    
    def _draw_plots(self):
        """绘制所有板块的折线（基于累积的历史点）"""
        if not self._history_points:
            return
        
        for ts_code, info in self._sector_info.items():
            points = self._history_points.get(ts_code, [])
            if len(points) < 1:
                continue
            
            times = []
            values = []
            
            for t, v in points:
                try:
                    x = time_str_to_seconds(t)
                    times.append(x)
                    values.append(v)
                except Exception:
                    continue
            
            if len(times) < 1:
                continue
            
            times = np.array(times, dtype=float)
            values = np.array(values, dtype=float)
            
            color = info["color"]
            # 异常板块曲线加粗
            line_width = 4 if ts_code in self._spike_sectors else 2
            pen = mkPen(color=color, width=line_width)
            
            try:
                plot_item = self.plot(times, values, pen=pen, clickable=True)
                if hasattr(plot_item, 'curve') and plot_item.curve is not None:
                    plot_item.curve.setClickable(True, width=10)
                plot_item.setData(times, values)
                self._plot_items[ts_code] = plot_item
            except Exception as e:
                print(f"[Chart] 绘制曲线 {ts_code} 失败: {e}")
                continue
        
        # 绘制曲线末端标签
        self._draw_labels()
    
    def _auto_range(self):
        """自动调整坐标轴范围"""
        if not self._history_points:
            return
        
        all_values = []
        all_x = []
        for ts_code in self._visible_sectors:
            points = self._history_points.get(ts_code, [])
            for t, v in points:
                try:
                    all_x.append(time_str_to_seconds(t))
                    all_values.append(v)
                except Exception:
                    continue
        
        if all_x:
            try:
                # 如果设置了Y轴固定范围，直接使用固定值
                if self._y_max_limit is not None and self._y_max_limit > 0:
                    self.setYRange(-self._y_max_limit, self._y_max_limit, padding=0)
                elif all_values:
                    min_val = min(all_values)
                    max_val = max(all_values)
                    
                    # 考虑标签的垂直范围
                    if self._label_items:
                        label_ys = [label.pos().y() for label in self._label_items.values()]
                        if label_ys:
                            min_val = min(min_val, min(label_ys))
                            max_val = max(max_val, max(label_ys))
                    
                    # Y轴以0为对称中心，以最大绝对值为基准，确保正负曲线都有足够展开空间
                    max_abs = max(abs(min_val), abs(max_val))
                    y_padding = max_abs * 0.15 if max_abs > 0 else 10
                    self.setYRange(-max_abs - y_padding, max_abs + y_padding, padding=0.02)
                
                # X轴范围：根据数据自适应，右侧留出标签空间
                min_x = min(all_x)
                max_x = max(all_x)
                x_span = max_x - min_x if max_x != min_x else 60
                x_left = min_x - x_span * 0.05
                # 右侧留出足够空间给标签（标签数量越多，留越多）
                label_count = len(self._visible_sectors)
                right_space = max(120, min(400, label_count * 12))
                x_right = max_x + right_space
                self.setXRange(x_left, x_right, padding=0.02)
                
                # 更新0轴线位置
                self._zero_line.setValue(0)
            except Exception as e:
                print(f"[Chart] 自动调整范围失败: {e}")
    
    def _draw_labels(self):
        """在曲线末端绘制智能标签，自动避免重叠"""
        # 清除旧标签
        for label in self._label_items.values():
            self.removeItem(label)
        self._label_items.clear()
        
        # 收集所有可见板块的末端点信息
        label_data = []
        for ts_code in self._visible_sectors:
            points = self._history_points.get(ts_code, [])
            if not points:
                continue
            last_t, last_v = points[-1]
            info = self._sector_info.get(ts_code)
            if info is None:
                continue
            x = time_str_to_seconds(last_t)
            y = last_v
            label_data.append({
                "ts_code": ts_code,
                "x": x,
                "y": y,
                "name": info["name"],
                "net": info["net_amount"],
                "pct": info["pct_change"],
            })
        
        if not label_data:
            return
        
        # 按 y 坐标排序（从小到大）
        label_data.sort(key=lambda d: d["y"])
        
        # 根据标签数量确定字体大小
        n = len(label_data)
        if n <= 8:
            font_size = 11
        elif n <= 15:
            font_size = 10
        elif n <= 25:
            font_size = 9
        else:
            font_size = 8
        
        # 获取当前视图范围
        vb = self.getViewBox()
        x_range, y_range = vb.viewRange()
        y_min, y_max = y_range
        x_min, x_max = x_range
        
        # 标签垂直方向在Y轴范围内均匀分布，留出上下边距
        margin = (y_max - y_min) * 0.05
        usable_min = y_min + margin
        usable_max = y_max - margin
        
        # 按净流入降序排列（正值在上，负值在下）
        label_data.sort(key=lambda d: d["net"], reverse=True)
        
        for i, data in enumerate(label_data):
            if n == 1:
                data["final_y"] = (usable_min + usable_max) / 2
            else:
                data["final_y"] = usable_max - i * (usable_max - usable_min) / (n - 1)
        
        # 标签固定在右侧，留出2%边距
        label_x = x_max - (x_max - x_min) * 0.02

        # 绘制标签
        for data in label_data:
            ts_code = data["ts_code"]
            y = data["final_y"]
            name = data["name"]
            net = data["net"]
            pct = data["pct"]

            # 截断名称（最多5个字）
            display_name = name if len(name) <= 5 else name[:4] + "…"

            # 净流入颜色：红涨绿跌（A股习惯）
            if net > 0:
                net_color = COLORS["positive"]
                sign = "+"
            elif net < 0:
                net_color = COLORS["negative"]
                sign = ""
            else:
                net_color = COLORS["neutral"]
                sign = ""

            text = f"{display_name} {sign}{net:.1f}亿"

            # anchor=(1, 0.5) 表示右对齐，标签向左延伸
            label = TextItem(text=text, color=QColor(net_color), anchor=(1, 0.5))
            label.setFont(QFont("Microsoft YaHei", font_size))
            label.setPos(label_x, y)

            self.addItem(label)
            self._label_items[ts_code] = label
            self._label_data_positions[ts_code] = (label_x, y)

    def _on_view_range_changed(self, vb, ranges):
        """视图范围变化时，更新标签X位置使其始终固定在右侧"""
        if not self._label_items or not self._label_data_positions:
            return
        try:
            x_range = vb.viewRange()[0]
            x_min, x_max = x_range
            # 标签固定在右侧，留出2%边距
            label_x = x_max - (x_max - x_min) * 0.02

            for ts_code, label in self._label_items.items():
                if ts_code in self._label_data_positions:
                    _, data_y = self._label_data_positions[ts_code]
                    label.setPos(label_x, data_y)
        except Exception:
            pass

    def _on_mouse_moved(self, pos):
        """鼠标移动时显示悬停提示"""
        try:
            view_pos = self.plotItem.vb.mapSceneToView(pos)
            mx, my = view_pos.x(), view_pos.y()

            closest_ts = None
            closest_dist = float('inf')
            closest_x = None
            closest_y = None

            for ts_code in self._visible_sectors:
                plot_item = self._plot_items.get(ts_code)
                if plot_item is None:
                    continue
                data = plot_item.getData()
                if data is None or len(data[0]) == 0:
                    continue

                x_data, y_data = data
                # 计算到最近数据点的距离
                distances = np.sqrt((x_data - mx)**2 + (y_data - my)**2)
                idx = np.argmin(distances)
                dist = distances[idx]

                if dist < closest_dist:
                    closest_dist = dist
                    closest_ts = ts_code
                    closest_x = x_data[idx]
                    closest_y = y_data[idx]

            # 阈值：只有足够近才显示 tooltip
            if closest_ts and closest_dist < 25:
                info = self._sector_info.get(closest_ts, {})
                name = info.get("name", "")
                net = info.get("net_amount", 0)
                pct = info.get("pct_change", 0)

                if net > 0:
                    sign = "+"
                elif net < 0:
                    sign = ""
                else:
                    sign = ""

                tooltip_text = f"{name}\n净流入: {sign}{net:.2f}亿\n涨跌幅: {sign}{pct:.2f}%"
                self._tooltip.setText(tooltip_text)

                # tooltip 放在点上方
                self._tooltip.setPos(closest_x, closest_y)
                self._tooltip.show()
                self._tooltip_target = closest_ts
            else:
                self._tooltip.hide()
                self._tooltip_target = None

        except Exception as e:
            # 鼠标移动事件不应抛出异常
            pass

    def mouseDoubleClickEvent(self, event):
        """鼠标双击事件 - 检测是否双击了板块标签或曲线"""
        try:
            pos = event.pos()
            vb = self.plotItem.vb

            # 计算像素到数据坐标的缩放因子
            x_range, y_range = vb.viewRange()
            x_span = x_range[1] - x_range[0] if x_range[1] != x_range[0] else 1
            y_span = y_range[1] - y_range[0] if y_range[1] != y_range[0] else 1
            x_scale = self.width() / x_span if x_span > 0 else 1
            y_scale = self.height() / y_span if y_span > 0 else 1

            view_pos = vb.mapSceneToView(pos)
            mx, my = view_pos.x(), view_pos.y()

            # 检查标签点击（标签宽约110px，高约18px）
            label_w_data = 110 / x_scale if x_scale > 0 else 20
            label_h_data = 18 / y_scale if y_scale > 0 else 4

            for ts_code, label in self._label_items.items():
                if ts_code not in self._visible_sectors:
                    continue
                label_pos = label.pos()
                lx, ly = label_pos.x(), label_pos.y()
                if (abs(mx - lx) < label_w_data / 2 and
                        abs(my - ly) < label_h_data):
                    info = self._sector_info.get(ts_code, {})
                    name = info.get("name", "")
                    print(f"[Chart] 双击板块标签: {name} ({ts_code})")
                    self.signals.sector_clicked.emit(ts_code, name)
                    event.accept()
                    return

            # 检查曲线点击
            closest_ts = None
            closest_dist = float('inf')
            for ts_code in self._visible_sectors:
                plot_item = self._plot_items.get(ts_code)
                if plot_item is None:
                    continue
                data = plot_item.getData()
                if data is None or len(data[0]) == 0:
                    continue
                x_data, y_data = data
                distances = np.sqrt((x_data - mx)**2 + (y_data - my)**2)
                idx = np.argmin(distances)
                dist = distances[idx]
                if dist < closest_dist:
                    closest_dist = dist
                    closest_ts = ts_code

            if closest_ts and closest_dist < 20:
                info = self._sector_info.get(closest_ts, {})
                name = info.get("name", "")
                print(f"[Chart] 双击板块曲线: {name} ({closest_ts})")
                self.signals.sector_clicked.emit(closest_ts, name)
                event.accept()
                return

        except Exception:
            pass

        super().mouseDoubleClickEvent(event)
    
    def refresh_plot(self):
        """刷新图表"""
        self._draw_plots()
        self._apply_filter()
        self._auto_range()
    
    def _on_timer(self):
        """定时器回调"""
        pass
    
    def get_sector_at_pos(self, pos):
        """获取鼠标位置对应的板块"""
        min_dist = float('inf')
        closest_sector = None
        
        for ts_code, plot_item in self._plot_items.items():
            if ts_code not in self._visible_sectors:
                continue
                
            data = plot_item.getData()
            if data is None or len(data[0]) == 0:
                continue
            
            x_data, y_data = data
            
            view_pos = self.plotItem.vb.mapSceneToView(pos)
            mx, my = view_pos.x(), view_pos.y()
            
            distances = np.sqrt((x_data - mx)**2 + (y_data - my)**2)
            min_idx = np.argmin(distances)
            dist = distances[min_idx]
            
            if dist < min_dist and dist < 20:
                min_dist = dist
                closest_sector = ts_code
        
        return closest_sector
    
    def get_visible_sectors_info(self):
        """获取当前可见板块的详细信息（用于图例面板）"""
        result = []
        for ts_code in self._visible_sectors:
            info = self._sector_info.get(ts_code)
            points = self._history_points.get(ts_code, [])
            if info:
                result.append({
                    "ts_code": ts_code,
                    "name": info["name"],
                    "net_amount": info["net_amount"],
                    "pct_change": info["pct_change"],
                    "color": info["color"].name(),
                    "point_count": len(points),
                })
        # 按净流入绝对值排序
        result.sort(key=lambda x: abs(x["net_amount"]), reverse=True)
        return result


class PctChangeChart(MoneyFlowChart):
    """
    涨跌幅分时图组件
    
    与 MoneyFlowChart 共享大部分逻辑，但：
    1. 历史点记录的是 pct_change（涨跌幅）而非 net_amount
    2. 筛选基于涨跌幅排序，取涨幅前N和跌幅前N
    3. 标签和tooltip显示涨跌幅百分比
    """
    
    def __init__(self, parent=None):
        # 先调用父类 __init__
        super().__init__(parent)
        
        # 修改Y轴标签
        self.setLabel("left", "涨跌幅 (%)", color="#666666", size="10px")
        
        # 涨跌幅筛选参数
        self._pct_top_n = 5
        self._pct_bottom_n = 5
        
        # 不需要异常波动检测
        self._spike_threshold = 0
        self._spike_records = []
        self._spike_sectors = set()
        
        # 涨跌幅图表Y轴默认固定±10%
        self.set_y_max_limit(10.0)
    
    def set_pct_filter(self, top_n=5, bottom_n=5):
        """设置涨跌幅筛选参数"""
        self._pct_top_n = top_n
        self._pct_bottom_n = bottom_n
        self._apply_filter()
    
    def update_data(self, sectors_df, current_time, trade_date):
        """
        更新图表数据 - 记录 pct_change 到历史点
        """
        try:
            # 检查日期是否变化
            if trade_date and trade_date != self._current_trade_date:
                self._history_points.clear()
                self._current_trade_date = trade_date
                self._view_initialized = False
                print(f"[PctChart] 新交易日: {trade_date}, 清空历史数据")
            
            time_key = current_time
            new_sectors = {}
            
            for _, row in sectors_df.iterrows():
                ts_code = row.get("ts_code", "")
                name = row.get("name", "")
                net_amount = float(row.get("net_amount", 0))
                pct_change = float(row.get("pct_change", 0))
                
                color_idx = hash(ts_code) % len(COLORS["line_colors"])
                line_color = QColor(COLORS["line_colors"][color_idx])
                
                new_sectors[ts_code] = {
                    "name": name,
                    "net_amount": net_amount,
                    "pct_change": pct_change,
                    "color": line_color,
                }
                
                if ts_code not in self._history_points:
                    self._history_points[ts_code] = []
                
                # 避免同一秒重复添加
                if self._history_points[ts_code]:
                    last_time, _ = self._history_points[ts_code][-1]
                    if last_time == time_key:
                        self._history_points[ts_code][-1] = (time_key, pct_change)
                    else:
                        self._history_points[ts_code].append((time_key, pct_change))
                else:
                    self._history_points[ts_code].append((time_key, pct_change))
            
            self._sector_info = new_sectors
            
            # 清除旧绘图
            self._clear_plots()
            
            # 绘制新的曲线
            self._draw_plots()
            
            # 应用筛选
            self._apply_filter()
            
            # 自动调整坐标轴范围（仅在第一次加载或换日时）
            if not self._view_initialized:
                self._auto_range()
                self._view_initialized = True
                
        except Exception as e:
            print(f"[PctChart] 更新图表数据失败: {e}")
            traceback.print_exc()
    
    def _apply_filter(self):
        """应用涨跌幅筛选 - 取涨幅前N和跌幅前N"""
        if not self._sector_info:
            return
        
        items = [(code, info) for code, info in self._sector_info.items()]
        # 按涨跌幅降序排列
        items.sort(key=lambda x: x[1]["pct_change"], reverse=True)
        
        visible = set()
        # 涨幅前N
        if self._pct_top_n > 0:
            for code, _ in items[:self._pct_top_n]:
                visible.add(code)
        # 跌幅前N
        if self._pct_bottom_n > 0:
            for code, _ in items[-self._pct_bottom_n:]:
                visible.add(code)
        
        self._visible_sectors = visible
        self._update_plot_visibility()
        self._draw_labels()
    
    def _draw_labels(self):
        """在曲线末端绘制智能标签（显示涨跌幅百分比）"""
        # 清除旧标签
        for label in self._label_items.values():
            self.removeItem(label)
        self._label_items.clear()
        
        # 收集所有可见板块的末端点信息
        label_data = []
        for ts_code in self._visible_sectors:
            points = self._history_points.get(ts_code, [])
            if not points:
                continue
            last_t, last_v = points[-1]
            info = self._sector_info.get(ts_code)
            if info is None:
                continue
            x = time_str_to_seconds(last_t)
            y = last_v
            label_data.append({
                "ts_code": ts_code,
                "x": x,
                "y": y,
                "name": info["name"],
                "pct": last_v,
            })
        
        if not label_data:
            return
        
        # 按 y 坐标排序（从小到大）
        label_data.sort(key=lambda d: d["y"])
        
        # 根据标签数量确定字体大小
        n = len(label_data)
        if n <= 8:
            font_size = 11
        elif n <= 15:
            font_size = 10
        elif n <= 25:
            font_size = 9
        else:
            font_size = 8
        
        # 获取当前视图范围
        vb = self.getViewBox()
        x_range, y_range = vb.viewRange()
        y_min, y_max = y_range
        x_min, x_max = x_range
        
        # 标签垂直方向在Y轴范围内均匀分布，留出上下边距
        margin = (y_max - y_min) * 0.05
        usable_min = y_min + margin
        usable_max = y_max - margin
        
        # 按涨跌幅降序排列（涨幅在上，跌幅在下）
        label_data.sort(key=lambda d: d["pct"], reverse=True)
        
        for i, data in enumerate(label_data):
            if n == 1:
                data["final_y"] = (usable_min + usable_max) / 2
            else:
                data["final_y"] = usable_max - i * (usable_max - usable_min) / (n - 1)
        
        # 标签固定在右侧，留出2%边距
        label_x = x_max - (x_max - x_min) * 0.02

        # 绘制标签
        for data in label_data:
            ts_code = data["ts_code"]
            y = data["final_y"]
            name = data["name"]
            pct = data["pct"]

            display_name = name if len(name) <= 5 else name[:4] + "…"

            # 涨跌幅颜色：红涨绿跌
            if pct > 0:
                net_color = COLORS["positive"]
                sign = "+"
            elif pct < 0:
                net_color = COLORS["negative"]
                sign = ""
            else:
                net_color = COLORS["neutral"]
                sign = ""

            text = f"{display_name} {sign}{pct:.2f}%"

            # anchor=(1, 0.5) 表示右对齐，标签向左延伸
            label = TextItem(text=text, color=QColor(net_color), anchor=(1, 0.5))
            label.setFont(QFont("Microsoft YaHei", font_size))
            label.setPos(label_x, y)

            self.addItem(label)
            self._label_items[ts_code] = label
            self._label_data_positions[ts_code] = (label_x, y)
    
    def _on_mouse_moved(self, pos):
        """鼠标移动时显示悬停提示（显示涨跌幅）"""
        try:
            view_pos = self.plotItem.vb.mapSceneToView(pos)
            mx, my = view_pos.x(), view_pos.y()

            closest_ts = None
            closest_dist = float('inf')
            closest_x = None
            closest_y = None

            for ts_code in self._visible_sectors:
                plot_item = self._plot_items.get(ts_code)
                if plot_item is None:
                    continue
                data = plot_item.getData()
                if data is None or len(data[0]) == 0:
                    continue

                x_data, y_data = data
                distances = np.sqrt((x_data - mx)**2 + (y_data - my)**2)
                idx = np.argmin(distances)
                dist = distances[idx]

                if dist < closest_dist:
                    closest_dist = dist
                    closest_ts = ts_code
                    closest_x = x_data[idx]
                    closest_y = y_data[idx]

            if closest_ts and closest_dist < 25:
                info = self._sector_info.get(closest_ts, {})
                name = info.get("name", "")
                net = info.get("net_amount", 0)
                pct = info.get("pct_change", 0)

                if pct > 0:
                    sign = "+"
                elif pct < 0:
                    sign = ""
                else:
                    sign = ""

                tooltip_text = f"{name}\n净流入: {net:+.2f}亿\n涨跌幅: {sign}{pct:.2f}%"
                self._tooltip.setText(tooltip_text)
                self._tooltip.setPos(closest_x, closest_y)
                self._tooltip.show()
                self._tooltip_target = closest_ts
            else:
                self._tooltip.hide()
                self._tooltip_target = None

        except Exception:
            pass
    
    def get_visible_sectors_info(self):
        """获取当前可见板块的详细信息"""
        result = []
        for ts_code in self._visible_sectors:
            info = self._sector_info.get(ts_code)
            points = self._history_points.get(ts_code, [])
            if info:
                result.append({
                    "ts_code": ts_code,
                    "name": info["name"],
                    "net_amount": info["pct_change"],  # 图例显示涨跌幅
                    "pct_change": info["pct_change"],
                    "color": info["color"].name(),
                    "point_count": len(points),
                })
        # 按涨跌幅绝对值排序
        result.sort(key=lambda x: abs(x["net_amount"]), reverse=True)
        return result
    
    def _detect_spikes(self, time_key):
        """涨跌幅图表不需要异动检测"""
        pass
    
    def set_y_max_limit(self, max_value):
        """设置Y轴最大值限制（百分比），None表示自动适应"""
        self._y_max_limit = max_value
        vb = self.getViewBox()
        if max_value is not None and max_value > 0:
            self.disableAutoRange(axis='y')
            self.setMouseEnabled(x=True, y=False)
            self.setAutoVisible(y=False)
            vb.setLimits(yMin=-max_value, yMax=max_value,
                         xMin=None, xMax=None)
            self.setYRange(-max_value, max_value, padding=0)
        else:
            self.enableAutoRange(axis='y')
            self.setMouseEnabled(x=True, y=True)
            self.setAutoVisible(y=True)
            vb.setLimits(yMin=None, yMax=None,
                         xMin=None, xMax=None)
            self._auto_range()
        # Y轴范围变化后重新计算标签位置
        self._draw_labels()


class IndexBarWidget(pg.GraphicsLayoutWidget):
    """指数栏组件 - 显示上证、深证、创业板的实时数据"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setBackground(QColor(COLORS["background"]))
        
        self._index_data = {}
        self._index_plots = {}
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        self._scene = self.scene()
        
        from PyQt5.QtWidgets import QLabel, QHBoxLayout, QWidget
        
        self._container = QWidget()
        self._layout = QHBoxLayout(self._container)
        self._layout.setSpacing(20)
        self._layout.setContentsMargins(20, 5, 20, 5)
        
        self._labels = {}
        for key, name in [("上证", "上证指数"), ("深证", "深证成指"), ("创业板", "创业板指")]:
            label = QLabel(f"{name}  --")
            label.setStyleSheet(f"""
                QLabel {{
                    color: {COLORS["text"]};
                    font-size: 14px;
                    font-weight: bold;
                    font-family: "Microsoft YaHei";
                }}
            """)
            self._labels[key] = label
            self._layout.addWidget(label)
        
        self._time_label = QLabel("")
        self._time_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["neutral"]};
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }}
        """)
        self._layout.addStretch()
        self._layout.addWidget(self._time_label)
    
    def update_index(self, index_data):
        """更新指数显示"""
        self._index_data = index_data or {}
        
        for key, data in self._index_data.items():
            if key in self._labels:
                label = self._labels[key]
                name = data.get("name", key)
                pct = data.get("pct_change", 0)
                
                if pct > 0:
                    color = COLORS["index_up"]
                    sign = "+"
                elif pct < 0:
                    color = COLORS["index_down"]
                    sign = ""
                else:
                    color = COLORS["neutral"]
                    sign = ""
                
                text = f"{name}  {sign}{pct:.2f}%"
                label.setText(text)
                label.setStyleSheet(f"""
                    QLabel {{
                        color: {color};
                        font-size: 14px;
                        font-weight: bold;
                        font-family: "Microsoft YaHei";
                    }}
                """)
        
        self._time_label.setText(datetime.now().strftime("%H:%M:%S"))
    
    def resizeEvent(self, event):
        """调整大小事件"""
        super().resizeEvent(event)
        if hasattr(self, '_container'):
            self._container.setGeometry(0, 0, self.width(), self.height())


# 简化版指数栏 - 使用QWidget实现
from PyQt5.QtWidgets import QLabel, QHBoxLayout, QWidget

class IndexBar(QWidget):
    """指数栏 - 显示三大指数实时数据"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setStyleSheet(f"background-color: {COLORS['background']};")
        
        self._layout = QHBoxLayout(self)
        self._layout.setSpacing(30)
        self._layout.setContentsMargins(20, 5, 20, 5)
        
        self._index_labels = {}
        index_names = {
            "上证": "上证指数",
            "深证": "深证成指",
            "创业板": "创业板指"
        }
        
        for key, display_name in index_names.items():
            label = QLabel(f"{display_name}  --")
            label.setStyleSheet(f"""
                QLabel {{
                    color: {COLORS['text']};
                    font-size: 15px;
                    font-weight: bold;
                    font-family: "Microsoft YaHei", "SimHei", sans-serif;
                }}
            """)
            self._index_labels[key] = label
            self._layout.addWidget(label)
        
        self._layout.addStretch()
        
        self._time_label = QLabel("")
        self._time_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['neutral']};
                font-size: 13px;
                font-family: "Microsoft YaHei";
            }}
        """)
        self._layout.addWidget(self._time_label)
        
        self._refresh_label = QLabel("⟳ 实时")
        self._refresh_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['positive']};
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }}
        """)
        self._layout.addWidget(self._refresh_label)
    
    def update_index(self, index_data):
        """更新指数显示"""
        if not index_data:
            return
        
        for key, data in index_data.items():
            if key in self._index_labels:
                label = self._index_labels[key]
                name = data.get("name", key)
                pct = data.get("pct_change", 0)
                
                if pct > 0:
                    color = COLORS["index_up"]
                    sign = "+"
                elif pct < 0:
                    color = COLORS["index_down"]
                    sign = ""
                else:
                    color = COLORS["neutral"]
                    sign = ""
                
                text = f"{name}  {sign}{pct:.2f}%"
                label.setText(text)
                label.setStyleSheet(f"""
                    QLabel {{
                        color: {color};
                        font-size: 15px;
                        font-weight: bold;
                        font-family: "Microsoft YaHei", "SimHei", sans-serif;
                    }}
                """)
        
        self._time_label.setText(datetime.now().strftime("%H:%M:%S"))


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    chart = MoneyFlowChart()
    chart.resize(1200, 700)
    chart.show()
    
    sys.exit(app.exec_())

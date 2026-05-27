# -*- coding: utf-8 -*-
"""
智能信号检测引擎

基于板块实时资金流向数据，检测四大类信号：
1. 市场风格切换（大小盘、成长价值轮动）
2. 超大资金抄底（板块异常流入 + 价格下跌背离）
3. 超大资金砸盘（板块异常流出 + 价格上涨背离）
4. 市场变盘（量价背离 + 趋势转折）

算法参考：
- 风格轮动：基于板块名称关键词分类，计算风格强度序列，检测MA方向改变
- 抄底/砸盘：Z-score异常检测（2σ阈值），结合价格背离
- 变盘：量价背离检测（涨跌幅创新高/低但净流入未同步）
"""

import numpy as np
from collections import defaultdict


# =============================================================================
# 板块风格分类关键词映射
# 基于A股概念板块常见命名规则
# =============================================================================
SECTOR_STYLE_KEYWORDS = {
    "large_cap": [
        "银行", "保险", "证券", "券商", "地产", "房地产", "石油", "石化", "煤炭",
        "钢铁", "基建", "建筑", "水泥", "电力", "水务", "燃气", "高速", "港口",
        "机场", "铁路", "中字头", "国企", "央企", "上证50", "沪深300", "MSCI",
        "信托", "金融"
    ],
    "small_cap": [
        "科技", "芯片", "半导体", "电子", "智能", "软件", "信息", "通信", "互联网",
        "5G", "物联网", "云计算", "大数据", "人工智能", "AI", "次新", "新股",
        "创业板", "科创板", "北交所", "小微", "创业", "创投"
    ],
    "growth": [
        "科技", "芯片", "半导体", "新能源", "光伏", "锂电池", "储能", "氢能",
        "充电桩", "电池", "生物", "医药", "创新药", "CRO", "医疗器械", "医美",
        "AI", "人工智能", "5G", "物联网", "云计算", "大数据", "机器人", "无人机",
        "虚拟现实", "元宇宙", "游戏", "传媒", "消费电子", "智能驾驶", "自动驾驶",
        "特斯拉", "比亚迪", "固态电池", "钠离子", "钙钛矿", "碳纤维", "复合集流体",
        "脑机接口", "量子", "卫星", "北斗", "商业航天", "合成生物", "低空经济"
    ],
    "value": [
        "银行", "保险", "证券", "券商", "地产", "房地产", "基建", "建筑", "水泥",
        "煤炭", "钢铁", "有色", "稀土", "黄金", "石油", "天然气", "化工", "化纤",
        "高速", "港口", "机场", "铁路", "电力", "水务", "燃气", "家电", "纺织",
        "农林", "牧渔", "食品", "饮料", "白酒", "啤酒", "零售", "百货", "超市",
        "贸易", "物流", "航运", "养殖", "种植", "中字头", "国企", "央企", "红利",
        "高股息", "低估值", "破净"
    ]
}


# =============================================================================
# 信号类型常量
# =============================================================================
SIGNAL_STYLE_SWITCH_LS = "style_switch_ls"      # 大小盘切换
SIGNAL_STYLE_SWITCH_GV = "style_switch_gv"      # 成长价值切换
SIGNAL_BOTTOM_FISHING = "bottom_fishing"        # 抄底
SIGNAL_DUMPING = "dumping"                      # 砸盘
SIGNAL_TURN_TOP = "turn_top"                    # 见顶变盘
SIGNAL_TURN_BOTTOM = "turn_bottom"              # 见底变盘

SIGNAL_NAMES = {
    SIGNAL_STYLE_SWITCH_LS: "风格切换-大小盘",
    SIGNAL_STYLE_SWITCH_GV: "风格切换-成长价值",
    SIGNAL_BOTTOM_FISHING: "超大资金抄底",
    SIGNAL_DUMPING: "超大资金砸盘",
    SIGNAL_TURN_TOP: "见顶变盘",
    SIGNAL_TURN_BOTTOM: "见底变盘",
}

SIGNAL_COLORS = {
    SIGNAL_STYLE_SWITCH_LS: "#2196F3",   # 蓝色
    SIGNAL_STYLE_SWITCH_GV: "#2196F3",   # 蓝色
    SIGNAL_BOTTOM_FISHING: "#4CAF50",    # 绿色
    SIGNAL_DUMPING: "#F44336",           # 红色
    SIGNAL_TURN_TOP: "#FF9800",          # 橙色
    SIGNAL_TURN_BOTTOM: "#4CAF50",       # 绿色
}


class SignalDetector:
    """
    智能信号检测器
    """

    def __init__(self):
        # 风格强度历史序列 [(timestamp, ls_strength, gv_strength), ...]
        self._style_history = []
        # 市场整体指标历史 [(timestamp, weighted_pct, total_net), ...]
        self._market_history = []
        # 上次信号时间 {signal_type: timestamp_seconds}
        self._last_signal_time = {}
        # 信号冷却时间（秒）— 同类型信号5分钟内不重复触发
        self._cooldown_seconds = 300
        # 最小历史点数要求
        self._min_history_points = 5
        # 风格切换MA窗口（次数）
        self._style_ma_short = 5
        self._style_ma_long = 10
        # 抄底/砸盘Z-score阈值
        self._z_score_threshold = 2.0
        # 变盘检测窗口
        self._turn_lookback = 10

    def detect(self, sectors_df, history_points, current_time, trade_date=""):
        """
        主检测入口

        Parameters
        -----------
        sectors_df : pd.DataFrame
            当前板块数据，列：ts_code, name, net_amount, pct_change
        history_points : dict
            {ts_code: [(time_str, net_amount), ...]}
        current_time : str
            当前时间 "HH:MM:SS"
        trade_date : str
            交易日期 "YYYYMMDD"

        Returns
        --------
        list[dict]
            信号列表
        """
        if sectors_df is None or len(sectors_df) == 0:
            return []

        signals = []
        signals.extend(self._detect_style_switch(sectors_df, current_time, trade_date))
        signals.extend(self._detect_smart_money(sectors_df, history_points, current_time, trade_date))
        signals.extend(self._detect_market_turn(sectors_df, current_time, trade_date))
        return signals

    def get_signal_name(self, signal_type):
        """获取信号类型显示名称"""
        return SIGNAL_NAMES.get(signal_type, signal_type)

    def get_signal_color(self, signal_type):
        """获取信号类型颜色"""
        return SIGNAL_COLORS.get(signal_type, "#999999")

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    def _is_in_cooldown(self, signal_type, current_time):
        """检查信号是否在冷却期内"""
        current_seconds = self._time_to_seconds(current_time)
        last_time = self._last_signal_time.get(signal_type, 0)
        return (current_seconds - last_time) < self._cooldown_seconds

    def _record_signal_time(self, signal_type, current_time):
        """记录信号触发时间"""
        self._last_signal_time[signal_type] = self._time_to_seconds(current_time)

    @staticmethod
    def _time_to_seconds(time_str):
        """时间字符串转秒数"""
        parts = time_str.split(":")
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2]) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + s

    @staticmethod
    def _classify_sector(name):
        """
        根据板块名称分类到风格象限

        Returns
        --------
        dict
            {"large_cap": bool, "small_cap": bool, "growth": bool, "value": bool}
        """
        result = {"large_cap": False, "small_cap": False, "growth": False, "value": False}
        for style, keywords in SECTOR_STYLE_KEYWORDS.items():
            if any(kw in name for kw in keywords):
                result[style] = True
        return result

    # -------------------------------------------------------------------------
    # 1. 风格切换检测
    # -------------------------------------------------------------------------

    def _calc_style_strength(self, sectors_df):
        """
        计算风格强度

        Returns
        --------
        tuple (ls_strength, gv_strength, details)
        """
        large_cap_net = 0.0
        small_cap_net = 0.0
        growth_net = 0.0
        value_net = 0.0

        large_sectors = []
        small_sectors = []
        growth_sectors = []
        value_sectors = []

        for _, row in sectors_df.iterrows():
            name = str(row.get("name", ""))
            net = float(row.get("net_amount", 0))

            classification = self._classify_sector(name)

            if classification["large_cap"]:
                large_cap_net += net
                large_sectors.append((name, net))
            if classification["small_cap"]:
                small_cap_net += net
                small_sectors.append((name, net))
            if classification["growth"]:
                growth_net += net
                growth_sectors.append((name, net))
            if classification["value"]:
                value_net += net
                value_sectors.append((name, net))

        ls_strength = large_cap_net - small_cap_net
        gv_strength = growth_net - value_net

        details = {
            "large_cap": {"total": large_cap_net, "count": len(large_sectors), "sectors": large_sectors},
            "small_cap": {"total": small_cap_net, "count": len(small_sectors), "sectors": small_sectors},
            "growth": {"total": growth_net, "count": len(growth_sectors), "sectors": growth_sectors},
            "value": {"total": value_net, "count": len(value_sectors), "sectors": value_sectors},
        }

        return ls_strength, gv_strength, details

    def _detect_style_switch(self, sectors_df, current_time, trade_date):
        """检测风格切换"""
        signals = []

        ls_strength, gv_strength, details = self._calc_style_strength(sectors_df)

        # 添加到历史
        self._style_history.append((current_time, ls_strength, gv_strength))
        if len(self._style_history) > 50:
            self._style_history = self._style_history[-50:]

        if len(self._style_history) < self._min_history_points:
            return signals

        ls_series = [x[1] for x in self._style_history]
        gv_series = [x[2] for x in self._style_history]

        ls_std = np.std(ls_series) if len(ls_series) > 1 else 1.0
        gv_std = np.std(gv_series) if len(gv_series) > 1 else 1.0
        if ls_std < 1.0:
            ls_std = 1.0
        if gv_std < 1.0:
            gv_std = 1.0

        short = self._style_ma_short
        long = self._style_ma_long

        # ---- 大小盘切换检测 ----
        if not self._is_in_cooldown(SIGNAL_STYLE_SWITCH_LS, current_time):
            if len(ls_series) >= long:
                prev_ma = np.mean(ls_series[-long:-short])
                curr_ma = np.mean(ls_series[-short:])

                # 方向改变且跨过0轴，幅度显著
                switch_threshold = 5.0  # 最小切换阈值（亿元）
                if (prev_ma > switch_threshold and curr_ma < -switch_threshold) or \
                   (prev_ma < -switch_threshold and curr_ma > switch_threshold):

                    if prev_ma > switch_threshold and curr_ma < -switch_threshold:
                        switch_desc = f"大盘→小盘（{prev_ma:.1f} → {curr_ma:.1f}）"
                    else:
                        switch_desc = f"小盘→大盘（{prev_ma:.1f} → {curr_ma:.1f}）"

                    confidence = min(100, int(50 + abs(curr_ma - prev_ma) / ls_std * 15))

                    signal = {
                        "timestamp": current_time,
                        "trade_date": trade_date,
                        "signal_type": SIGNAL_STYLE_SWITCH_LS,
                        "title": f"风格切换：{switch_desc}",
                        "description": (f"大小盘风格强度从{prev_ma:.1f}变为{curr_ma:.1f}，"
                                       f"大盘板块净流入{details['large_cap']['total']:.1f}亿，"
                                       f"小盘板块净流入{details['small_cap']['total']:.1f}亿。"),
                        "confidence": confidence,
                        "related_sectors": [],
                        "details": {
                            "prev_strength": round(prev_ma, 2),
                            "curr_strength": round(curr_ma, 2),
                            "large_cap_total": round(details["large_cap"]["total"], 2),
                            "small_cap_total": round(details["small_cap"]["total"], 2),
                            "large_cap_count": details["large_cap"]["count"],
                            "small_cap_count": details["small_cap"]["count"],
                        }
                    }
                    signals.append(signal)
                    self._record_signal_time(SIGNAL_STYLE_SWITCH_LS, current_time)

        # ---- 成长价值切换检测 ----
        if not self._is_in_cooldown(SIGNAL_STYLE_SWITCH_GV, current_time):
            if len(gv_series) >= long:
                prev_ma = np.mean(gv_series[-long:-short])
                curr_ma = np.mean(gv_series[-short:])

                switch_threshold = 5.0
                if (prev_ma > switch_threshold and curr_ma < -switch_threshold) or \
                   (prev_ma < -switch_threshold and curr_ma > switch_threshold):

                    if prev_ma > switch_threshold and curr_ma < -switch_threshold:
                        switch_desc = f"成长→价值（{prev_ma:.1f} → {curr_ma:.1f}）"
                    else:
                        switch_desc = f"价值→成长（{prev_ma:.1f} → {curr_ma:.1f}）"

                    confidence = min(100, int(50 + abs(curr_ma - prev_ma) / gv_std * 15))

                    signal = {
                        "timestamp": current_time,
                        "trade_date": trade_date,
                        "signal_type": SIGNAL_STYLE_SWITCH_GV,
                        "title": f"风格切换：{switch_desc}",
                        "description": (f"成长价值风格强度从{prev_ma:.1f}变为{curr_ma:.1f}，"
                                       f"成长板块净流入{details['growth']['total']:.1f}亿，"
                                       f"价值板块净流入{details['value']['total']:.1f}亿。"),
                        "confidence": confidence,
                        "related_sectors": [],
                        "details": {
                            "prev_strength": round(prev_ma, 2),
                            "curr_strength": round(curr_ma, 2),
                            "growth_total": round(details["growth"]["total"], 2),
                            "value_total": round(details["value"]["total"], 2),
                            "growth_count": details["growth"]["count"],
                            "value_count": details["value"]["count"],
                        }
                    }
                    signals.append(signal)
                    self._record_signal_time(SIGNAL_STYLE_SWITCH_GV, current_time)

        return signals

    # -------------------------------------------------------------------------
    # 2. 超大资金抄底/砸盘检测
    # -------------------------------------------------------------------------

    def _detect_smart_money(self, sectors_df, history_points, current_time, trade_date):
        """检测超大资金抄底/砸盘"""
        signals = []

        bottom_sectors = []
        dump_sectors = []

        for _, row in sectors_df.iterrows():
            ts_code = row.get("ts_code", "")
            name = str(row.get("name", ""))
            net = float(row.get("net_amount", 0))
            pct = float(row.get("pct_change", 0))

            hist = history_points.get(ts_code, [])
            if len(hist) < self._min_history_points:
                continue

            # 计算增量历史（相邻两次刷新的累计净流入差值）
            increments = []
            for i in range(1, len(hist)):
                increments.append(hist[i][1] - hist[i - 1][1])

            if len(increments) < 3:
                continue

            inc_array = np.array(increments)
            mu = np.mean(inc_array)
            sigma = np.std(inc_array)
            if sigma < 0.01:
                sigma = 0.01

            latest_inc = increments[-1]
            z_score = (latest_inc - mu) / sigma

            # ---- 抄底检测：异常流入 + 价格下跌 ----
            if net > 0 and pct < 0:
                if z_score > self._z_score_threshold:
                    # 近3次增量递增
                    if len(increments) >= 3 and increments[-1] > increments[-2] > increments[-3]:
                        confidence = min(100, int(60 + z_score * 10))
                        bottom_sectors.append({
                            "ts_code": ts_code,
                            "name": name,
                            "net": net,
                            "pct": pct,
                            "z_score": z_score,
                            "confidence": confidence,
                            "latest_inc": latest_inc,
                        })

            # ---- 砸盘检测：异常流出 + 价格上涨 ----
            elif net < 0 and pct > 0:
                if z_score < -self._z_score_threshold:
                    # 近3次增量递减（流出越来越大）
                    if len(increments) >= 3 and increments[-1] < increments[-2] < increments[-3]:
                        confidence = min(100, int(60 + abs(z_score) * 10))
                        dump_sectors.append({
                            "ts_code": ts_code,
                            "name": name,
                            "net": net,
                            "pct": pct,
                            "z_score": z_score,
                            "confidence": confidence,
                            "latest_inc": latest_inc,
                        })

        # ---- 生成抄底信号 ----
        if bottom_sectors and not self._is_in_cooldown(SIGNAL_BOTTOM_FISHING, current_time):
            bottom_sectors.sort(key=lambda x: x["confidence"], reverse=True)
            top_sectors = bottom_sectors[:3]
            avg_confidence = int(np.mean([s["confidence"] for s in top_sectors]))

            names = "、".join([s["name"] for s in top_sectors])
            total_net = sum(s["net"] for s in top_sectors)

            signal = {
                "timestamp": current_time,
                "trade_date": trade_date,
                "signal_type": SIGNAL_BOTTOM_FISHING,
                "title": f"超大资金抄底：{names}",
                "description": (f"检测到{len(bottom_sectors)}个板块出现异常资金流入，"
                               f"板块价格下跌但资金逆势流入，疑似超大资金抄底。"
                               f"主要板块：{names}，合计流入{total_net:.1f}亿。"),
                "confidence": avg_confidence,
                "related_sectors": [s["ts_code"] for s in top_sectors],
                "details": {
                    "sector_count": len(bottom_sectors),
                    "top_sectors": [
                        {
                            "name": s["name"],
                            "net": round(s["net"], 2),
                            "pct": round(s["pct"], 2),
                            "z_score": round(s["z_score"], 2),
                            "confidence": s["confidence"],
                        } for s in top_sectors
                    ],
                    "total_net": round(total_net, 2),
                }
            }
            signals.append(signal)
            self._record_signal_time(SIGNAL_BOTTOM_FISHING, current_time)

        # ---- 生成砸盘信号 ----
        if dump_sectors and not self._is_in_cooldown(SIGNAL_DUMPING, current_time):
            dump_sectors.sort(key=lambda x: x["confidence"], reverse=True)
            top_sectors = dump_sectors[:3]
            avg_confidence = int(np.mean([s["confidence"] for s in top_sectors]))

            names = "、".join([s["name"] for s in top_sectors])
            total_net = sum(s["net"] for s in top_sectors)

            signal = {
                "timestamp": current_time,
                "trade_date": trade_date,
                "signal_type": SIGNAL_DUMPING,
                "title": f"超大资金砸盘：{names}",
                "description": (f"检测到{len(dump_sectors)}个板块出现异常资金流出，"
                               f"板块价格上涨但资金逆势流出，疑似超大资金砸盘。"
                               f"主要板块：{names}，合计流出{abs(total_net):.1f}亿。"),
                "confidence": avg_confidence,
                "related_sectors": [s["ts_code"] for s in top_sectors],
                "details": {
                    "sector_count": len(dump_sectors),
                    "top_sectors": [
                        {
                            "name": s["name"],
                            "net": round(s["net"], 2),
                            "pct": round(s["pct"], 2),
                            "z_score": round(s["z_score"], 2),
                            "confidence": s["confidence"],
                        } for s in top_sectors
                    ],
                    "total_net": round(total_net, 2),
                }
            }
            signals.append(signal)
            self._record_signal_time(SIGNAL_DUMPING, current_time)

        return signals

    # -------------------------------------------------------------------------
    # 3. 市场变盘检测（量价背离）
    # -------------------------------------------------------------------------

    def _calc_market_metrics(self, sectors_df):
        """计算市场整体指标"""
        total_abs_net = 0.0
        weighted_pct = 0.0
        total_net = 0.0
        up_count = 0
        down_count = 0

        for _, row in sectors_df.iterrows():
            net = float(row.get("net_amount", 0))
            pct = float(row.get("pct_change", 0))
            abs_net = abs(net)
            total_abs_net += abs_net
            weighted_pct += pct * abs_net
            total_net += net
            if pct > 0:
                up_count += 1
            elif pct < 0:
                down_count += 1

        if total_abs_net > 0:
            weighted_pct /= total_abs_net

        return weighted_pct, total_net, up_count, down_count

    def _detect_market_turn(self, sectors_df, current_time, trade_date):
        """检测市场变盘（量价背离）"""
        signals = []

        weighted_pct, total_net, up_count, down_count = self._calc_market_metrics(sectors_df)

        # 添加到历史
        self._market_history.append((current_time, weighted_pct, total_net, up_count, down_count))
        if len(self._market_history) > 50:
            self._market_history = self._market_history[-50:]

        if len(self._market_history) < self._min_history_points:
            return signals

        pct_series = [x[1] for x in self._market_history]
        net_series = [x[2] for x in self._market_history]

        lookback = self._turn_lookback

        # ---- 顶背离（见顶变盘）检测 ----
        if not self._is_in_cooldown(SIGNAL_TURN_TOP, current_time):
            if len(pct_series) >= lookback:
                recent_pct = pct_series[-lookback:]
                recent_net = net_series[-lookback:]

                max_pct = max(recent_pct)
                max_pct_idx = recent_pct.index(max_pct)

                # 最高点是最近的（最近3次内）
                if max_pct_idx >= lookback - 3:
                    corresponding_net = recent_net[max_pct_idx]
                    max_net = max(recent_net)

                    # 涨跌幅创新高但净流入未创新高（背离）
                    if max_net > 0 and corresponding_net < max_net * 0.9:
                        # 净流入呈下降趋势
                        if len(net_series) >= 6:
                            recent_3_avg = np.mean(net_series[-3:])
                            prev_3_avg = np.mean(net_series[-6:-3])
                            if prev_3_avg > 0 and recent_3_avg < prev_3_avg * 0.95:
                                confidence = min(100, int(55 + (max_pct - recent_pct[-1]) * 10))
                                confidence = max(50, confidence)

                                signal = {
                                    "timestamp": current_time,
                                    "trade_date": trade_date,
                                    "signal_type": SIGNAL_TURN_TOP,
                                    "title": "⚠️ 市场见顶变盘预警",
                                    "description": (f"市场整体涨跌幅创新高({max_pct:.2f}%)，"
                                                   f"但资金净流入未同步放大({corresponding_net:.1f}亿 vs 最高{max_net:.1f}亿)，"
                                                   f"出现量价背离，可能即将见顶回落。"),
                                    "confidence": confidence,
                                    "related_sectors": [],
                                    "details": {
                                        "max_pct": round(max_pct, 2),
                                        "current_pct": round(recent_pct[-1], 2),
                                        "max_net": round(max_net, 2),
                                        "current_net": round(corresponding_net, 2),
                                        "recent_3_avg": round(recent_3_avg, 2),
                                        "prev_3_avg": round(prev_3_avg, 2),
                                        "up_count": up_count,
                                        "down_count": down_count,
                                    }
                                }
                                signals.append(signal)
                                self._record_signal_time(SIGNAL_TURN_TOP, current_time)

        # ---- 底背离（见底变盘）检测 ----
        if not self._is_in_cooldown(SIGNAL_TURN_BOTTOM, current_time):
            if len(pct_series) >= lookback:
                recent_pct = pct_series[-lookback:]
                recent_net = net_series[-lookback:]

                min_pct = min(recent_pct)
                min_pct_idx = recent_pct.index(min_pct)

                if min_pct_idx >= lookback - 3:
                    corresponding_net = recent_net[min_pct_idx]
                    min_net = min(recent_net)

                    # 涨跌幅创新低但净流入未创新低（背离）
                    if min_net < 0 and corresponding_net > min_net * 0.9:
                        # 净流入呈上升趋势
                        if len(net_series) >= 6:
                            recent_3_avg = np.mean(net_series[-3:])
                            prev_3_avg = np.mean(net_series[-6:-3])
                            if prev_3_avg < 0 and recent_3_avg > prev_3_avg * 1.05:
                                confidence = min(100, int(55 + (recent_pct[-1] - min_pct) * 10))
                                confidence = max(50, confidence)

                                signal = {
                                    "timestamp": current_time,
                                    "trade_date": trade_date,
                                    "signal_type": SIGNAL_TURN_BOTTOM,
                                    "title": "✅ 市场见底变盘预警",
                                    "description": (f"市场整体涨跌幅创新低({min_pct:.2f}%)，"
                                                   f"但资金净流出未同步放大({corresponding_net:.1f}亿 vs 最低{min_net:.1f}亿)，"
                                                   f"出现量价背离，可能即将见底反弹。"),
                                    "confidence": confidence,
                                    "related_sectors": [],
                                    "details": {
                                        "min_pct": round(min_pct, 2),
                                        "current_pct": round(recent_pct[-1], 2),
                                        "min_net": round(min_net, 2),
                                        "current_net": round(corresponding_net, 2),
                                        "recent_3_avg": round(recent_3_avg, 2),
                                        "prev_3_avg": round(prev_3_avg, 2),
                                        "up_count": up_count,
                                        "down_count": down_count,
                                    }
                                }
                                signals.append(signal)
                                self._record_signal_time(SIGNAL_TURN_BOTTOM, current_time)

        return signals

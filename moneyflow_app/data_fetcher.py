# -*- coding: utf-8 -*-
"""
数据获取模块 - 从东方财富获取实时概念板块资金流向
指数数据保留 Tushare 接口
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import traceback

try:
    import tushare as ts
except ImportError:
    ts = None

from config import TUSHARE_TOKEN, TUSHARE_API_URL, INDEX_CODES


# 需要过滤掉的概念板块（非真实概念）
_BLOCKED_CONCEPTS = {
    '昨日连板_含一字', '昨日连板', '昨日涨停_含一字', '昨日涨停',
    '昨日跌停', '昨日触板', '创业板综', 'B股', '上证180_', 'AH股'
}


class DataFetcher:
    """数据获取器 - 东方财富概念板块 + Tushare指数"""

    def __init__(self, token=None, use_mock=False):
        """初始化

        Parameters:
        -----------
        token : str, optional
            Tushare Pro Token（仅用于指数数据）
        use_mock : bool, default False
            是否允许使用模拟数据
        """
        self.token = token or TUSHARE_TOKEN
        self._use_mock = use_mock
        self.pro = None
        self._initialized = False
        self._permission_level = 0
        self._cache = {}
        self._cache_time = {}

        self._init_api()

    def _init_api(self):
        """初始化 Tushare API（仅用于指数数据）"""
        if ts is None:
            print("[DataFetcher] tushare 未安装，指数数据将不可用")
            self._initialized = False
            return
        try:
            self.pro = ts.pro_api(self.token)
            if hasattr(self.pro, '_DataApi__http_url'):
                self.pro._DataApi__http_url = TUSHARE_API_URL
            self._initialized = True
            print(f"[DataFetcher] Tushare API初始化成功")
        except Exception as e:
            print(f"[DataFetcher] Tushare API初始化失败: {e}")
            self._initialized = False

    def is_initialized(self):
        """检查API是否初始化成功"""
        return self._initialized

    def get_permission_level(self):
        """获取当前权限等级"""
        return self._permission_level

    def _get_cache(self, key, max_age_seconds=60):
        """获取缓存数据"""
        if key in self._cache and key in self._cache_time:
            age = (datetime.now() - self._cache_time[key]).total_seconds()
            if age < max_age_seconds:
                return self._cache[key]
        return None

    def _set_cache(self, key, data):
        """设置缓存数据"""
        self._cache[key] = data
        self._cache_time[key] = datetime.now()

    # ==================== 模拟数据 ====================

    def _get_mock_index_data(self):
        """生成模拟指数数据"""
        if not self._use_mock:
            return {}
        import random
        now = datetime.now()
        random.seed(now.hour * 3600 + now.minute * 60 + now.second)
        mock_data = {}
        for key, base_info in {
            "上证": {"base": 3320.0, "name": "上证指数"},
            "深证": {"base": 10500.0, "name": "深证成指"},
            "创业板": {"base": 2100.0, "name": "创业板指"},
        }.items():
            base = base_info["base"]
            pct = random.uniform(-1.2, 1.2)
            change = base * pct / 100
            mock_data[key] = {
                "code": INDEX_CODES.get(key, ""),
                "name": base_info["name"],
                "close": round(base + change, 2),
                "open": round(base + random.uniform(-5, 5), 2),
                "pre_close": round(base, 2),
                "change": round(change, 2),
                "pct_change": round(pct, 2),
                "vol": round(random.uniform(200000, 600000), 0),
                "amount": round(random.uniform(2000, 6000), 2),
            }
        random.seed()
        return mock_data

    def _get_mock_moneyflow(self):
        """生成模拟资金流向数据"""
        if not self._use_mock:
            return pd.DataFrame(columns=["ts_code", "name", "net_amount", "pct_change"])
        np.random.seed(int(datetime.now().strftime("%Y%m%d")))
        mock_sectors = [
            ("BK0559", "可燃冰", 12), ("BK0560", "减速器", 103),
            ("BK0561", "海工装备", 85), ("BK0562", "页岩气", 40),
            ("BK0563", "一体化压铸", 50), ("BK0564", "云办公", 29),
            ("BK0565", "DRG/DIP", 23), ("BK0566", "电子身份证", 40),
            ("BK0567", "云游戏", 27), ("BK0568", "华为手机", 35),
            ("BK0569", "消费电子", 91), ("BK0570", "苹果概念", 68),
            ("BK0571", "特斯拉", 55), ("BK0572", "小米概念", 42),
            ("BK0573", "无线耳机", 38), ("BK0574", "氮化镓", 45),
            ("BK0575", "光刻机", 52), ("BK0576", "国家大基金", 48),
            ("BK0577", "中芯国际概念", 35), ("BK0578", "半导体", 78),
            ("BK0579", "芯片", 82), ("BK0580", "集成电路", 65),
            ("BK0581", "人工智能", 120), ("BK0582", "ChatGPT", 45),
            ("BK0583", "AIGC", 38), ("BK0584", "算力", 55),
            ("BK0585", "CPO", 42), ("BK0586", "机器人", 88),
            ("BK0587", "人形机器人", 35), ("BK0588", "减速器", 28),
        ]
        data = []
        for code, name, _ in mock_sectors:
            data.append({
                "ts_code": code,
                "name": name,
                "net_amount": round(np.random.normal(0, 50), 2),
                "pct_change": round(np.random.normal(0, 2), 2),
            })
        df = pd.DataFrame(data)
        df = df.sort_values("net_amount", ascending=False).reset_index(drop=True)
        print(f"[DataFetcher] 使用模拟资金流向数据({len(df)}个板块)")
        return df

    # ==================== 指数数据 ====================

    def get_index_realtime(self):
        """
        获取三大指数实时数据
        使用 index_daily 接口获取最新日线数据
        返回: dict {指数名: {price, change_pct, ...}}
        """
        result = {}
        cache_key = "index_realtime"
        cached = self._get_cache(cache_key, max_age_seconds=30)
        if cached is not None:
            return cached

        if self.pro is None:
            if self._use_mock:
                result = self._get_mock_index_data()
            self._set_cache(cache_key, result)
            return result

        for name, code in INDEX_CODES.items():
            try:
                df = self.pro.index_daily(ts_code=code)
                if df is not None and len(df) > 0:
                    df = df.sort_values("trade_date", ascending=False)
                    row = df.iloc[0]
                    result[name] = {
                        "code": code,
                        "name": name,
                        "close": float(row.get("close", 0)),
                        "open": float(row.get("open", 0)),
                        "pre_close": float(row.get("pre_close", row.get("close", 0))),
                        "change": float(row.get("change", 0)),
                        "pct_change": float(row.get("pct_chg", 0)),
                        "vol": float(row.get("vol", 0)),
                        "amount": float(row.get("amount", 0)),
                    }
            except Exception as e:
                print(f"[DataFetcher] 获取指数{name}数据失败: {e}")

        if not result and self._use_mock:
            result = self._get_mock_index_data()

        self._set_cache(cache_key, result)
        return result

    # ==================== 东方财富概念板块资金流向 ====================

    @staticmethod
    def _parse_jquery_response(text, data_mode='{'):
        """解析东方财富 jQuery JSONP 响应"""
        reverse_mode = {'[': ']', '{': '}', '(': ')'}
        tail_str = text[-5:][::-1]
        start_idx = text.index(data_mode)
        end_idx = -tail_str.index(reverse_mode[data_mode])
        return eval(text[start_idx: end_idx])

    def _build_concept_url(self, page_no=1, page_size=100):
        """构造东方财富概念板块请求URL"""
        return (
            "http://94.push2.eastmoney.com/api/qt/clist/get?"
            "cb=jQuery112404219515748621301_1656315378776"
            f"&pn={page_no}&pz={page_size}&po=1&np=1"
            "&ut=bd1d9ddb04089700cf9c27f6f7426281"
            "&fltt=2&invt=2&wbp2u=|0|0|0|web"
            "&fid=f3"
            "&fs=m:90+t:3+f:!50"
            "&fields=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,"
            "f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,"
            "f25,f26,f22,f33,f11,f62,f128,f136,f115,f152,"
            "f124,f107,f104,f105,f140,f141,f207,f208,f209,f222"
            f"&_={int(time.time() * 1000)}"
        )

    @staticmethod
    def _parse_concept_records(diff_list):
        """解析概念板块原始数据为统一记录格式"""
        records = []
        for item in diff_list:
            name = item.get('f14', '')
            if name in _BLOCKED_CONCEPTS:
                continue

            code = item.get('f12', '')
            # f3: 涨跌幅（已经是百分比数值，如10.91表示10.91%）
            pct_change = item.get('f3')
            try:
                pct_change = float(pct_change) if pct_change is not None else 0.0
            except (ValueError, TypeError):
                pct_change = 0.0

            # f62: 主力净流入（单位：元）
            net_amount = item.get('f62')
            try:
                net_amount = float(net_amount) / 1e8 if net_amount is not None else 0.0
            except (ValueError, TypeError):
                net_amount = 0.0

            records.append({
                "ts_code": code,
                "name": name,
                "net_amount": round(net_amount, 2),
                "pct_change": round(pct_change, 2),
            })
        return records

    def get_concept_moneyflow(self):
        """
        从东方财富获取概念板块实时资金流向（自动分页获取全部）

        东方财富单页最多返回100条，因此需要：
        1. 先请求第1页获取 total 总数
        2. 计算总页数并循环获取所有页
        3. 合并所有数据

        返回: DataFrame [ts_code, name, net_amount, pct_change]
            - ts_code: 板块代码 (如 BK0559)
            - name: 板块名称
            - net_amount: 主力净流入 (亿元)
            - pct_change: 板块涨跌幅 (%)
        """
        cache_key = "concept_moneyflow_em"
        cached = self._get_cache(cache_key, max_age_seconds=30)
        if cached is not None:
            return cached

        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 6.1; ) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/81.0.4044.129 Safari/537.36'
            )
        }

        all_records = []
        page_size = 100  # 东方财富单页上限约100条

        try:
            # 1. 先请求第1页，获取总数
            first_url = self._build_concept_url(page_no=1, page_size=page_size)
            response = requests.get(first_url, headers=headers, timeout=15)
            response.raise_for_status()
            data = self._parse_jquery_response(response.text, data_mode='{')

            data_body = data.get('data', {})
            diff = data_body.get('diff', [])
            total = data_body.get('total', 0)

            if not diff:
                print("[DataFetcher] 东方财富返回空数据")
                if self._use_mock:
                    return self._get_mock_moneyflow()
                return pd.DataFrame(columns=["ts_code", "name", "net_amount", "pct_change"])

            all_records.extend(self._parse_concept_records(diff))
            print(f"[DataFetcher] 东方财富概念板块总数: {total}, 已获取第1页({len(diff)}条)")

            # 2. 计算剩余页数并循环获取
            total_pages = (total + page_size - 1) // page_size if total > 0 else 1
            for page_no in range(2, total_pages + 1):
                url = self._build_concept_url(page_no=page_no, page_size=page_size)
                try:
                    resp = requests.get(url, headers=headers, timeout=15)
                    resp.raise_for_status()
                    page_data = self._parse_jquery_response(resp.text, data_mode='{')
                    page_diff = page_data.get('data', {}).get('diff', [])
                    if page_diff:
                        all_records.extend(self._parse_concept_records(page_diff))
                        print(f"[DataFetcher] 已获取第{page_no}页({len(page_diff)}条)")
                    else:
                        print(f"[DataFetcher] 第{page_no}页无数据，停止分页")
                        break
                except Exception as e:
                    print(f"[DataFetcher] 获取第{page_no}页失败: {e}")
                    break
                # 短暂延时，避免请求过快
                time.sleep(0.15)

            df = pd.DataFrame(all_records)
            df = df.sort_values("net_amount", ascending=False).reset_index(drop=True)
            print(f"[DataFetcher] 从东方财富共获取到 {len(df)} 个概念板块")
            self._set_cache(cache_key, df)
            return df

        except Exception as e:
            print(f"[DataFetcher] 获取东方财富概念板块资金流向失败: {e}")
            traceback.print_exc()
            if self._use_mock:
                return self._get_mock_moneyflow()
            return pd.DataFrame(columns=["ts_code", "name", "net_amount", "pct_change"])

    def calculate_realtime_moneyflow(self, sector_list=None, progress_callback=None):
        """
        获取实时板块资金流向（统一入口）

        Parameters:
        -----------
        sector_list : 已废弃，保留参数以兼容旧调用
        progress_callback : callable(pct, message)
            进度回调

        返回: dict {
            "sectors": DataFrame[ts_code, name, net_amount, pct_change],
            "timestamp": str,        # 当前时间 "HH:MM:SS"
            "trade_date": str,       # 数据日期 "YYYYMMDD"
            "data_source": str,
            "timeseries": {}
        }
        """
        result = {
            "sectors": None,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "trade_date": datetime.now().strftime("%Y%m%d"),
            "data_source": "eastmoney_realtime",
            "timeseries": {}
        }

        try:
            if progress_callback:
                progress_callback(20, "正在获取概念板块资金流向...")

            df = self.get_concept_moneyflow()

            if df is None or len(df) == 0:
                print("[DataFetcher] 概念板块资金流向数据为空")
                if self._use_mock:
                    df = self._get_mock_moneyflow()
                if df is None or len(df) == 0:
                    return result

            if progress_callback:
                progress_callback(80, "正在整理数据...")

            result["sectors"] = df
            result["timestamp"] = datetime.now().strftime("%H:%M:%S")
            result["trade_date"] = datetime.now().strftime("%Y%m%d")
            result["data_source"] = "eastmoney_realtime"

            if progress_callback:
                progress_callback(100, "数据更新完成")

            return result

        except Exception as e:
            print(f"[DataFetcher] 计算实时资金流向失败: {e}")
            traceback.print_exc()
            if self._use_mock:
                df = self._get_mock_moneyflow()
                result["sectors"] = df
                result["data_source"] = "simulated"
                return result
            return result

    def get_intraday_timeseries(self, ts_code, freq="5MIN"):
        """
        获取板块的日内分时数据序列
        返回: list of (time, net_amount_cumulative)
        """
        return []


# 测试代码
if __name__ == "__main__":
    import sys
    use_mock = "--mock" in sys.argv

    fetcher = DataFetcher(use_mock=use_mock)
    print(f"初始化状态: {fetcher.is_initialized()}")
    print(f"模拟模式: {use_mock}")

    # 测试获取指数
    print("\n=== 指数数据 ===")
    index_data = fetcher.get_index_realtime()
    for name, data in index_data.items():
        print(f"  {name}: {data['close']} ({data['pct_change']:+.2f}%)")

    # 测试获取概念板块资金流向
    print("\n=== 概念板块资金流向 ===")
    df = fetcher.get_concept_moneyflow()
    print(f"板块数量: {len(df)}")
    if len(df) > 0:
        print(df.head(10).to_string(index=False))

    # 测试完整计算
    print("\n=== 实时资金流向计算 ===")
    result = fetcher.calculate_realtime_moneyflow()
    if result["sectors"] is not None:
        print(f"板块数: {len(result['sectors'])}")
        print(f"数据源: {result['data_source']}")
        print(f"数据时间: {result['timestamp']}")
        print(f"数据日期: {result.get('trade_date', '')}")
        print(result["sectors"].head(5).to_string(index=False))
    else:
        print("未获取到实时资金流向数据")

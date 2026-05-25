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
import random
import re
import json

try:
    import tushare as ts
except ImportError:
    ts = None

from config import (
    TUSHARE_TOKEN, TUSHARE_API_URL, INDEX_CODES,
    USE_ZDAYE_PROXY, ZDAYE_API_URL, ZDAYE_APP_ID, ZDAYE_AKEY,
    ZDAYE_PROXY_USERNAME, ZDAYE_PROXY_PASSWORD,
)
from proxy_fetcher import ProxyFetcher


# 固定 User-Agent（东方财富接口兼容性最佳）
_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 6.1; ) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/81.0.4044.129 Safari/537.36'
)

# 需要过滤掉的概念板块（非真实概念）
_BLOCKED_CONCEPTS = {
    '昨日连板_含一字', '昨日连板', '昨日涨停_含一字', '昨日涨停',
    '昨日跌停', '昨日触板', '创业板综', 'B股', '上证180_', 'AH股'
}


class DataFetcher:
    """数据获取器 - 东方财富概念板块 + Tushare指数"""

    def __init__(self, token=None, use_mock=False, use_proxy=False):
        """初始化

        Parameters:
        -----------
        token : str, optional
            Tushare Pro Token（仅用于指数数据）
        use_mock : bool, default False
            是否允许使用模拟数据
        use_proxy : bool, default False
            是否启用站大爷代理池（需命令行传入 --proxy）
        """
        self.token = token or TUSHARE_TOKEN
        self._use_mock = use_mock
        self.pro = None
        self._initialized = False
        self._permission_level = 0
        self._cache = {}
        self._cache_time = {}
        self._concept_cache_ttl = 55  # 概念板块缓存秒数，可由外部调整
        self.session = requests.Session()
        self._proxy_fetcher = None
        print(f"[DataFetcher] use_proxy={use_proxy}, USE_ZDAYE_PROXY={USE_ZDAYE_PROXY}")
        if use_proxy and USE_ZDAYE_PROXY and ZDAYE_APP_ID and ZDAYE_AKEY:
            try:
                self._proxy_fetcher = ProxyFetcher(
                    ZDAYE_API_URL, ZDAYE_APP_ID, ZDAYE_AKEY,
                    proxy_username=ZDAYE_PROXY_USERNAME,
                    proxy_password=ZDAYE_PROXY_PASSWORD,
                )
                print("[DataFetcher] 站大爷代理获取器已初始化")
            except Exception as e:
                print(f"[DataFetcher] 代理获取器初始化失败: {e}")
        # 设置 Session 级别的默认 headers
        self.session.headers.update({
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })

        # 请求日志与限流控制（基于时间窗口）
        self._request_log = []  # 记录每次请求时间戳
        self._max_qps = 2.0     # 最大QPS限制
        self._qps_window = 1.0  # QPS计算窗口（秒）

        self._init_api()

    def _rate_limit(self):
        """全局速率限制 - 基于时间窗口的限流，确保QPS不超过阈值"""
        now = time.time()
        # 清理过期记录
        self._request_log = [t for t in self._request_log if now - t < self._qps_window]
        if len(self._request_log) >= self._max_qps:
            sleep_time = self._qps_window - (now - self._request_log[0])
            if sleep_time > 0:
                jitter = random.uniform(0.1, 0.5)
                print(f"[RateLimiter] 触发限流，等待 {sleep_time + jitter:.2f}s")
                time.sleep(sleep_time + jitter)
        self._request_log.append(time.time())

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
        """生成模拟指数数据（随机游走，模拟真实波动）"""
        if not self._use_mock:
            return {}

        # 初始化状态（只执行一次）
        if not hasattr(self, '_mock_index_state'):
            self._mock_index_state = {}
            for key, base_info in {
                "上证": {"base": 3320.0, "name": "上证指数"},
                "深证": {"base": 10500.0, "name": "深证成指"},
                "创业板": {"base": 2100.0, "name": "创业板指"},
            }.items():
                self._mock_index_state[key] = {
                    "base": base_info["base"],
                    "name": base_info["name"],
                    "pct": np.random.uniform(-0.5, 0.5),
                    "open": base_info["base"] + np.random.uniform(-5, 5),
                }

        mock_data = {}
        for key, state in self._mock_index_state.items():
            # 涨跌幅小幅波动（标准差约0.05%），模拟真实指数微幅震荡
            state["pct"] += np.random.normal(0, 0.05)
            state["pct"] = max(-1.5, min(1.5, state["pct"]))

            base = state["base"]
            pct = state["pct"]
            change = base * pct / 100

            mock_data[key] = {
                "code": INDEX_CODES.get(key, ""),
                "name": state["name"],
                "close": round(base + change, 2),
                "open": round(state["open"], 2),
                "pre_close": round(base, 2),
                "change": round(change, 2),
                "pct_change": round(pct, 2),
                "vol": round(np.random.uniform(200000, 600000), 0),
                "amount": round(np.random.uniform(2000, 6000), 2),
            }
        return mock_data

    def _get_mock_moneyflow(self):
        """生成模拟资金流向数据（随机游走，模拟真实波动）"""
        if not self._use_mock:
            return pd.DataFrame(columns=["ts_code", "name", "net_amount", "pct_change"])

        # 板块列表与初始权重（用于初始化时的排序倾向）
        mock_sectors = [
            ("BK0559", "可燃冰"), ("BK0560", "减速器"),
            ("BK0561", "海工装备"), ("BK0562", "页岩气"),
            ("BK0563", "一体化压铸"), ("BK0564", "云办公"),
            ("BK0565", "DRG/DIP"), ("BK0566", "电子身份证"),
            ("BK0567", "云游戏"), ("BK0568", "华为手机"),
            ("BK0569", "消费电子"), ("BK0570", "苹果概念"),
            ("BK0571", "特斯拉"), ("BK0572", "小米概念"),
            ("BK0573", "无线耳机"), ("BK0574", "氮化镓"),
            ("BK0575", "光刻机"), ("BK0576", "国家大基金"),
            ("BK0577", "中芯国际概念"), ("BK0578", "半导体"),
            ("BK0579", "芯片"), ("BK0580", "集成电路"),
            ("BK0581", "人工智能"), ("BK0582", "ChatGPT"),
            ("BK0583", "AIGC"), ("BK0584", "算力"),
            ("BK0585", "CPO"), ("BK0586", "机器人"),
            ("BK0587", "人形机器人"), ("BK0588", "减速器"),
        ]

        # 初始化状态（只执行一次）：给每个板块分配不同的"性格"
        if not hasattr(self, '_mock_moneyflow_state'):
            self._mock_moneyflow_state = {}
            for code, name in mock_sectors:
                # 初始值差异更大：-30 ~ +50 亿，有的天生流入大，有的大幅流出
                init_net = np.random.uniform(-30, 50)
                # 每个板块有自己的波动率：0.5（极稳）~ 5.0（极跳）
                volatility = np.random.uniform(0.5, 5.0)
                # 每个板块有自己的趋势（drift）：-0.3（长期流出）~ +0.3（长期流入）
                drift = np.random.uniform(-0.3, 0.3)
                self._mock_moneyflow_state[code] = {
                    "name": name,
                    "net_amount": init_net,
                    "pct_change": np.random.uniform(-3, 4),
                    "volatility": volatility,
                    "drift": drift,
                }

        # 基于上次值进行差异化波动（随机游走 + 趋势漂移）
        for code, state in self._mock_moneyflow_state.items():
            vol = state["volatility"]
            drift = state["drift"]

            # 净流入波动 = 趋势推动 + 随机噪声（每个板块噪声大小不同）
            state["net_amount"] += drift + np.random.normal(0, vol)
            state["net_amount"] = max(-60, min(80, state["net_amount"]))

            # 涨跌幅与资金流向联动：资金大幅流入时涨幅倾向于上升
            momentum = np.random.normal(0, 0.3) + (drift * 0.5)
            state["pct_change"] += momentum
            state["pct_change"] = max(-8, min(10, state["pct_change"]))

        data = []
        for code, state in self._mock_moneyflow_state.items():
            data.append({
                "ts_code": code,
                "name": state["name"],
                "net_amount": round(state["net_amount"], 2),
                "pct_change": round(state["pct_change"], 2),
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
        # 模拟模式：直接返回模拟数据
        if self._use_mock:
            print("[DataFetcher] 模拟模式：跳过指数请求，直接返回模拟数据")
            result = self._get_mock_index_data()
            self._set_cache("index_realtime", result)
            return result

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
    def _parse_jquery_response(text, data_mode=None):
        """解析东方财富 jQuery JSONP 响应（安全版本，移除 eval）"""
        try:
            # 尝试匹配 jQueryxxx({...}) 或 (...)
            match = re.search(r'\((.*)\)[;\s]*$', text, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            # 兜底：直接查找 JSON 对象
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except json.JSONDecodeError as e:
            # 代理可能返回了错误页面，打印前300字符方便排查
            preview = text[:300].replace('\n', ' ').replace('\r', ' ')
            print(f"[DataFetcher] 解析响应失败: {e}")
            print(f"[DataFetcher] 响应内容预览: {preview}...")
            raise ValueError(f"无法解析响应内容: {e}")
        raise ValueError("无法解析响应内容：未找到JSON数据")

    def _build_concept_url(self, page_no=1, page_size=100):
        """构造东方财富概念板块请求URL"""
        return (
            "http://94.push2delay.eastmoney.com/api/qt/clist/get?"
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

    def _get_headers(self):
        """构造东方财富请求头"""
        return {
            'User-Agent': _USER_AGENT,
            'Referer': 'https://quote.eastmoney.com/center/gridlist.html#hs_a_board',
        }

    def _request_page(self, url, proxy_pool=None, max_retries=5):
        """带重试、退避和代理切换的分页请求（每次独立连接，避免Session累积）"""
        for attempt in range(max_retries):
            # 全局速率限制，确保单IP QPS不超过阈值
            self._rate_limit()

            proxies = None
            proxy_url = None
            if proxy_pool:
                proxy_url = random.choice(proxy_pool)
                proxies = {"http": proxy_url, "https": proxy_url}

            try:
                headers = self._get_headers()
                # 使用 requests.get 而非 session.get，每次全新TCP连接，避免Cookie/Session累积被追踪
                resp = requests.get(url, headers=headers, proxies=proxies, timeout=15)

                # 检测响应头中的限流信息
                rate_limit_remaining = resp.headers.get('X-RateLimit-Remaining')
                if rate_limit_remaining is not None and rate_limit_remaining == '0':
                    print(f"[DataFetcher] 限流头提示剩余请求为0，暂停 {attempt + 1}s")
                    time.sleep(attempt + 1 + random.uniform(0.5, 1.0))

                # 针对常见反爬/限流状态码处理
                if resp.status_code in (403, 429):
                    msg = "IP被封禁或请求过频" if resp.status_code == 403 else "触发频率限制"
                    print(f"[DataFetcher] {msg} (状态码 {resp.status_code})")
                    # 如果是代理模式，立即移除当前代理并换下一个
                    if proxy_url and proxy_pool and proxy_url in proxy_pool:
                        proxy_pool.remove(proxy_url)
                        print(f"[DataFetcher] 代理 {proxy_url} 已被标记，剩余 {len(proxy_pool)} 个")
                    # 退避等待
                    wait = 2 ** attempt + random.uniform(2, 5)
                    print(f"[DataFetcher] 退避等待 {wait:.1f}s 后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(wait)
                    continue
                if resp.status_code in (502, 503, 504):
                    # 服务端异常：加大退避，给东方财富CDN节点恢复时间
                    wait = 2 ** attempt + random.uniform(2, 4)
                    print(f"[DataFetcher] 服务端异常 {resp.status_code}，等待 {wait:.1f}s 后重试")
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                return self._parse_jquery_response(resp.text)

            except (requests.exceptions.ProxyError, requests.exceptions.ConnectTimeout) as e:
                if proxy_url and proxy_pool and proxy_url in proxy_pool:
                    proxy_pool.remove(proxy_url)
                    print(f"[DataFetcher] 代理 {proxy_url} 失效已移除，剩余 {len(proxy_pool)} 个代理")
                else:
                    print(f"[DataFetcher] 代理请求失败: {e}")
                time.sleep(random.uniform(1, 3))
                continue

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt + random.uniform(1, 3)
                    print(f"[DataFetcher] 请求异常，等待 {wait:.1f}s 后重试 ({attempt + 1}/{max_retries}): {e}")
                    time.sleep(wait)
                else:
                    raise

        raise requests.exceptions.RequestException(f"请求失败，已重试 {max_retries} 次")

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
        # 模拟模式：直接返回模拟数据，不请求东方财富
        if self._use_mock:
            print("[DataFetcher] 模拟模式：跳过东方财富请求，直接返回模拟数据")
            return self._get_mock_moneyflow()

        cache_key = "concept_moneyflow_em"
        cached = self._get_cache(cache_key, max_age_seconds=self._concept_cache_ttl)
        if cached is not None:
            return cached

        # 每次刷新时从站大爷获取新代理列表
        proxy_pool = []
        if self._proxy_fetcher is not None:
            try:
                proxy_pool = self._proxy_fetcher.fetch_proxies(count=20)
                print(f"[DataFetcher] 从站大爷获取到 {len(proxy_pool)} 个代理")
            except Exception as e:
                print(f"[DataFetcher] 获取代理失败，将使用直连: {e}")

        all_records = []
        page_size = 100  # 东方财富单页上限约100条

        try:
            # 1. 先请求第1页，获取总数
            first_url = self._build_concept_url(page_no=1, page_size=page_size)
            print(first_url)
            data = self._request_page(first_url, proxy_pool=proxy_pool)

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

            # 2. 计算剩余页数，打乱顺序，在30秒内随机间隔串行获取
            total_pages = (total + page_size - 1) // page_size if total > 0 else 1
            remaining_pages = list(range(2, total_pages + 1))
            random.shuffle(remaining_pages)  # 随机顺序，不按1,2,3...翻页

            n = len(remaining_pages)
            if n > 0:
                # 生成随机间隔：每个至少0.5秒，总和不超过30秒
                min_interval = 0.5
                remaining_time = max(0, 30 - min_interval * n)
                raw = [random.random() for _ in range(n)]
                total_raw = sum(raw)
                extra = [r / total_raw * remaining_time for r in raw] if total_raw > 0 else [0] * n
                intervals = [min_interval + e for e in extra]
                print(f"[DataFetcher] 剩余 {n} 页将在30秒内随机串行获取，"
                      f"间隔: {[round(x,1) for x in intervals]}，顺序: {remaining_pages}")

                for page_no, interval in zip(remaining_pages, intervals):
                    time.sleep(interval)
                    url = self._build_concept_url(page_no=page_no, page_size=page_size)
                    try:
                        page_data = self._request_page(url, proxy_pool=proxy_pool)
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

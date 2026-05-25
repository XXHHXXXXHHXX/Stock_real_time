# -*- coding: utf-8 -*-
"""
代理IP获取模块 - 从站大爷免费代理API获取HTTP代理
文档: https://www.zdaye.com/doc/api/FreeProxy_get
"""

import requests


class ProxyFetcher:
    """站大爷免费代理IP获取器"""

    def __init__(self, api_url, app_id, akey, proxy_username=None, proxy_password=None):
        """
        Parameters:
        -----------
        api_url : str
            代理API地址，如 http://www.zdopen.com/FreeProxy/Get/
        app_id : str
            应用ID（对应文档中的 api 参数）
        akey : str
            认证密钥（16位MD5），可从站大爷后台生成
        proxy_username : str, optional
            代理用户名（实例ID），用于 requests 代理认证
        proxy_password : str, optional
            代理密码（实例ID后8位），用于 requests 代理认证
        """
        self.api_url = api_url
        self.app_id = app_id
        self.akey = akey
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password

    def fetch_proxies(self, count=20, protocol_type=1, dalu=1, return_type=3,
                      lastcheck_type=2, sleep_type=2, alive_type=1):
        """
        获取代理IP列表

        Parameters:
        -----------
        count : int
            提取数量，最大100，默认20
        protocol_type : int
            1=http, 2=socks4, 3=socks5, 4=https
        dalu : int
            1=大陆, 0=海外
        return_type : int
            1=Text文本, 2=XML, 3=JSON
        lastcheck_type : int
            1=1分钟内, 2=10分钟内, 3=30分钟内, 4=1小时内, 5=1个半小时内
        sleep_type : int
            1=1秒内, 2=3秒内, 3=5秒内, 4=10秒内, 5=15秒内
        alive_type : int
            1=10分钟以上, 2=半小时以上, 3=1小时以上, ...

        Returns:
        --------
        list of str
            requests 可用的代理URL，如 ["http://1.2.3.4:8080", ...]
        """
        params = {
            "app_id": self.app_id,
            "akey": self.akey,
            "count": count,
            "dalu": dalu,
            "protocol_type": protocol_type,
            "return_type": return_type,
            "lastcheck_type": lastcheck_type,
            "sleep_type": sleep_type,
            "alive_type": alive_type,
        }

        resp = requests.get(self.api_url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        code = data.get("code")
        if code == "12012":
            # 上一个客户端IP仍在提取中，2分钟内不能换IP提取
            msg = data.get("msg", "")
            print(f"[ProxyFetcher] 代理API限流 [{code}]: {msg}")
            return []
        if code != "10001":
            msg = data.get("msg", "未知错误")
            raise RuntimeError(f"代理API返回错误 [{code}]: {msg}")

        proxy_list = data.get("data", {}).get("proxy_list", [])
        if not proxy_list:
            raise RuntimeError("代理API返回空列表")

        auth = ""
        if self.proxy_username and self.proxy_password:
            auth = f"{self.proxy_username}:{self.proxy_password}@"

        results = []
        for item in proxy_list:
            ip = item.get("ip")
            port = item.get("port")
            if not ip or not port:
                continue
            results.append(f"http://{auth}{ip}:{port}")

        return results

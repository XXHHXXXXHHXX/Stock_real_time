# 实时板块资金流向监控工具

A股板块（概念/行业）实时资金流向分时监控工具，基于 PyQt5 + pyqtgraph + Tushare Pro 开发。
![alt text](image.png)
## 功能特点

- **实时监控** - 自动刷新板块资金流向数据（支持自定义刷新间隔）
- **分时折线图** - 多条彩色折线同时展示各板块资金净流入/流出趋势
- **三大指数** - 顶部显示上证指数、深证成指、创业板指实时涨跌幅
- **灵活筛选** - 支持按净流入金额、板块数量、板块类型、关键词搜索筛选
- **智能降级** - 高权限使用Tushare Pro实时数据，低权限自动切换模拟数据
- **深色主题** - 参考专业行情软件设计，暗色背景保护视力

## 安装与运行

### 方式一：直接运行Python代码

```bash
# 1. 克隆或下载本项目
cd moneyflow_app

# 2. 安装依赖
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements.txt

# 3. 运行
python main.py
```

### 方式二：打包为exe（Windows）

```bash
# 运行打包脚本
cd moneyflow_app
build.bat
```

打包完成后，`dist/实时板块资金流向监控/` 目录下即为可执行程序。

## 文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | 程序入口 |
| `main_window.py` | 主窗口，整合所有组件 |
| `data_fetcher.py` | Tushare数据获取与处理 |
| `chart_widget.py` | 实时分时图表组件 |
| `filter_panel.py` | 筛选面板组件 |
| `config.py` | 配置文件 |
| `build.py` / `build.bat` | 打包脚本 |

## Tushare配置

首次运行会自动使用内置Token，建议在**设置**中配置自己的Token以获取更准确的数据。

- 注册/登录: https://tushare.pro
- 在个人主页获取 Token
- 高级功能（实时板块数据）需要 **6000积分**
- 基础功能（日线数据）只需 **200积分**

## 使用说明

1. **启动程序** - 运行 `main.py` 或双击exe文件
2. **查看数据** - 主界面显示各板块实时资金流向折线图
3. **筛选曲线** - 在左侧面板设置净流入金额范围、显示数量等条件
4. **自动刷新** - 默认60秒自动刷新，可在筛选面板调整
5. **配置Token** - 点击顶部"设置"按钮修改Tushare Token

## 数据来源

| 接口 | 说明 | 积分要求 |
|------|------|----------|
| `ths_index` | 同花顺板块列表 | 6000 |
| `ths_daily` | 板块日行情 | 6000 |
| `rt_min` | 实时分钟行情 | 6000 |
| `moneyflow_cnt_ths` | 板块资金流向 | 6000 |

积分不足时自动使用模拟数据，仍可正常体验全部功能。

## 技术栈

- Python 3.8+
- PyQt5 - GUI框架
- pyqtgraph - 高性能实时图表
- Tushare Pro - 金融数据接口
- pandas / numpy - 数据处理

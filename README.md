# High-Risk Paper Trader

一个面向中文玩家的高风险 **模拟交易训练系统**：从 `$500` 纸面账户开始，覆盖美股、ETF、加密资产和期权，重点不是吹收益，而是把数据、策略、风控、复盘、AI 反对意见和交易日志放到同一个本地驾驶舱里。

> 当前项目处于 **Phase 1：仅模拟**。系统不会自动下真钱单，也不构成投资建议。

## 项目定位

这个项目适合想做激进交易研究、但不想一上来就拿真钱试错的人。它会维护独立玩家工作区、forward paper ledger、策略实验室、数据可信度中心、风险驾驶舱、AI 三方审判和交易日记。你可以把它当成一个本地版的交易训练台。

核心目标：

- 先用真实/准真实数据做 forward 模拟，而不是只看历史回测。
- 让每笔模拟交易都有理由、退出条件、止损止盈、数据来源和复盘。
- 用风控熔断防止“翻倍或清空”变成无约束赌博。
- 在真钱前强制经过多周模拟、订单草稿、人工确认和 API 权限隔离。

## 功能亮点

- **首次启动向导**：选择身份、初始资金、风险等级、API 配置、是否允许期权、是否只看不交易。
- **多用户隔离**：每个玩家拥有独立 workspace、ledger、API 配置和报告。
- **策略实验室**：查看策略排名、forward 表现、回测环境、参数版本、上线/淘汰原因。
- **期权模拟引擎**：支持期权 multiplier、bid/ask、滑点、theta、IV crush、DTE 风险和流动性评分。
- **数据可信度中心**：追踪行情时间戳、延迟、跨源价格偏差、新闻和财报来源。
- **风险驾驶舱**：用大白话解释最大单笔亏损、仓位暴露、剩余可亏金额、连续亏损和周度熔断。
- **AI 三方审判**：进攻交易员、风控官、怀疑论者同时给出意见，并输出统一结论。
- **交易日记**：记录入场前截图、入场理由、退出条件、实际结果、错误标签和下次修正。
- **小白解释层**：Delta、Theta、IV、DTE、滑点、回撤等术语都有中文解释按钮。
- **对外欢迎中心**：免责声明、玩法、启动说明、API 教程、FAQ、风险提示和演示模式。

## 技术栈

- 后端：Python、FastAPI、DuckDB、本地玩家工作区
- 前端：Next.js App Router、React、TypeScript、Lightweight Charts
- 数据源：Massive/Polygon、Alpaca Paper、Benzinga、FMP、Google Translate、Gemini
- 测试：pytest、Next.js production build

## 快速启动

推荐使用项目自带控制菜单：

1. 在 Finder 里双击 `Trading Control.command`
2. 选择 `1) Start`
3. 选择 `5) Open Dashboard`
4. 新玩家先打开 `http://localhost:3000/welcome`

终端方式：

```bash
./scripts/tradectl.sh start
./scripts/tradectl.sh status
./scripts/tradectl.sh stop
```

默认地址：

- Dashboard: `http://localhost:3000`
- API: `http://127.0.0.1:8010`
- 欢迎中心: `http://localhost:3000/welcome`

## 手动开发启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
npm install
```

启动后端：

```bash
npm run api
```

另开一个终端启动前端：

```bash
npm run dev
```

## 演示模式

打开 `http://localhost:3000/welcome`，点击 **开启演示模式**。

演示模式会创建独立的 `Demo Player` 工作区，初始化 `$500` 模拟账本，跑一次 forward tick，然后进入仪表盘。它不会修改你的 Owner 账本。

演示模式可以不用外部 API，但只能用于理解流程，不能当作实盘准备依据。

## API 配置

复制 `.env.example` 为 `.env.local`，或者直接在网页 `设置` 页面粘贴 API key。

推荐数据源：

- `MASSIVE_API_KEY`：主行情和期权链数据
- `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY`：Alpaca 纸面账户检查
- `BENZINGA_API_KEY`：新闻催化
- `FMP_API_KEY`：财报和事件日历
- `GOOGLE_TRANSLATE_API_KEY`：动态中文翻译
- `GEMINI_API_KEY`：AI 三方审判分析

安全原则：

- 不要提交 `.env.local`
- 不要把 live trading key 放进 Phase 1
- 不要共用 API key 给外部玩家
- 每个玩家应使用自己的本地配置

## 项目结构

```text
backend/trading_system/   FastAPI、策略、行情、期权、风控、ledger、报告
backend/tests/            Python 单元测试和集成测试
src/app/                  Next.js 页面路由
src/components/           仪表盘、欢迎页、风险页、交易日记等组件
scripts/tradectl.sh       本地启动/关闭/状态/日志控制脚本
.env.example              配置模板，不含任何真实密钥
```

## 验证

```bash
.venv/bin/pytest backend/tests
npm run build
```

当前验证基线：

- `backend/tests` 全部通过
- Next.js production build 通过

## 风险声明

本项目仅用于模拟交易、交易研究和学习。期权、杠杆 ETF、加密资产和高波动股票都可能造成快速亏损。任何历史回测、AI 分析、策略排名或模拟结果都不能保证未来收益。

真钱交易前，至少需要：

- 4 周以上 forward paper ledger
- broker order draft 阶段，只生成订单草稿
- 明确最大单笔、单日、单周亏损限制
- API 延迟、行情异常、数据缺失熔断
- 期权只允许买入 call/put 或 defined-risk spread
- 每周复盘真实 forward PnL、最大回撤、命中率和数据异常

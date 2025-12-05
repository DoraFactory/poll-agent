# poll-agent

基于 Google Agent SDK (ADK) + Grok x_search 的“热门议题 → 投票”生成器。按环境变量指定的 X 账号定时抓取最新帖子，自动生成可发布的投票草案。

## 功能
- 通过 Grok 的 `x_search` 工具抓取指定 X handle 的最新帖子。
- 用 Gemini（通过 ADK）分析热点，生成投票草案（JSON，含 topic/rationale/question/options/sample_posts 等字段）。
- 服务模式：按环境变量中的 handles 定时（默认 30 分钟）自动执行，无需命令行参数。

## 快速开始
1) 安装依赖
```bash
pip install -r requirements.txt
```

2) 配置环境变量（可复制 `.env.example` 为 `.env`）
```
GOOGLE_API_KEY=你的Gemini密钥
XAI_API_KEY=你的Grok密钥
X_HANDLES=elonmusk,googledeepmind   # 需要处理的 X 账号，逗号分隔
POLL_INTERVAL_SECONDS=1800          # 可选，默认 30 分钟
```

3) 运行服务（按 env 中的 handles 定时抓取与汇总）
```bash
PYTHONPATH=src python3 src/service.py
```

输出会展示工具调用记录以及最终的投票草案（topic / rationale / poll_question / options / sample_posts 等字段），循环每 `POLL_INTERVAL_SECONDS` 秒执行一次。

## 架构与流程
- 目录按数据源拆分代理：
  - `src/x_agent/agent.py`：专职调用 Grok 的 `x_search` 抓取 X 帖子，并返回 JSON 数据。
  - `src/agent.py`：主代理，调用子代理获取数据后生成投票草案。
- `src/runner.py`：组装 orchestrator + 子代理，并提供 ADK Runner（内存 session，可替换为持久化实现）。
- `src/tools/grok_x_search.py`：对 xai-sdk 的 `x_search` 做薄包装，限定 handle 并要求以 JSON 形式返回帖子列表。
- `src/tools/utils.py`：封装 ADK 输入/事件处理。
- `src/service.py`：服务入口，按 env 定时跑一次抓取与汇总。

整体 orchestrated by ADK：Runner 管理 session & 调度子代理 → X 数据代理用 Grok 抓取最新帖子 → 主代理生成热点概括与投票草案。

## 备注
- 需要 Python 3.10+。
- 如需自定义模型，环境变量 `GEMINI_MODEL` / `GROK_MODEL` 可覆盖默认值。
- 如果抓取结果为空，Agent 会在输出中给出原因，便于排查（例如 handle 不存在或权限不足）。

# poll-agent

基于 Google Agent SDK (ADK) + Grok x_search 的“热门议题 → 投票”生成器。

## 功能
- 通过 Grok 的 `x_search` 工具抓取指定 X handle 的最新帖子。
- 用 Gemini（通过 ADK）分析哪些话题最热，并生成适合发布的投票草案（JSON 输出）。
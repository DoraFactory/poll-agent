"""Small wrapper around xai-sdk `x_search` to pull recent X posts for handles."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import x_search


def fetch_x_posts(
    handles: List[str],
    topic_hint: str = "",
    max_posts: int = 20,
    window_seconds: int | None = None,
    *,
    grok_model: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Pull recent posts from given handles via Grok x_search and ask Grok
    to propose a poll-worthy topic.
    """
    cleaned_handles = [h.lstrip("@") for h in handles if h.strip()]
    if not cleaned_handles:
        raise ValueError("At least one X handle is required for x_search.")

    now_dt = datetime.now(timezone.utc)
    now_utc = now_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    since_iso = (
        (now_dt - timedelta(seconds=window_seconds)).isoformat()
        if window_seconds
        else None
    )

    client = Client(api_key=api_key) if api_key else Client()
    logging.info(
        "[grok_x_search] chat.create handles=%s window_seconds=%s topic_hint=%s",
        cleaned_handles,
        window_seconds,
        topic_hint,
    )
    chat = client.chat.create(
        model=grok_model,
        tools=[
            x_search(
                allowed_x_handles=cleaned_handles,
            ),
        ],
        temperature=0.0,
        max_tokens=4096,
        top_p=1.0,
    )

    hours = round(window_seconds / 3600, 2) if window_seconds else "recent"
    window_label = f"{window_seconds} 秒" if window_seconds else "最近窗口"
    handles_str = ", ".join(cleaned_handles)
    prompt = f"""
你现在是 UTC {now_utc}。对每个 handle，收集过去 {window_label}（~{hours}h）内的所有帖子/回复/转推，只挑出该 handle 最值得做 poll 的那一个话题。

核心要求：
1. 几乎所有话题都允许：政治、选举、战争、宗教、争议话题、预测市场等完全可以
2. 科技、经济、社会、娱乐、体育、文化等所有常规议题都允许
3. 保持客观中立：标题和选项必须对称、无明显偏见，选项≤20字

极少数拒绝情况（仅以下）：
- 直接煽动暴力/伤害他人的内容
- 露骨色情内容
- 泄露他人隐私信息（公众人物的公开信息不算）
目标 handles：{handles_str}
可选 topic hint：{topic_hint or 'none'}

请严格输出以下 JSON（只输出 JSON，不要额外说明，也不要 ```json 包裹）：
{{
  "per_handle": [
    {{
      "handle": "elonmusk",
      "status": "已找到可投票话题" | "过去时间窗口内无新帖" | "无合适议题（原因：xxx）",
      "poll_interval_posts_list": [
        {{
          "handle": "elonmusk",
          "posted_at": "YYYY-MM-DDTHH:MM:SSZ",
          "url": "https://x.com/...",
          "engagement": {{"likes": 0, "reposts": 0, "quotes": 0, "replies": 0, "views": 0}},
          "context_summary": "1-2 句话概括为何值得关注",
          "is_reply": false,
          "in_reply_to_url": "",
          "is_retweet": false,
          "original_url": "",
          "text": "原文全文"
        }}
      ],
      "poll": {{
        "topic_title": "示例主题",
        "poll_question": "示例问题",
        "options": [
          "A 选项（<=20字，中立描述）",
          "B 选项（<=20字，中立描述）",
          "C 选项（<=20字，中立描述）",
          "D 选项（<=20字，中立描述）"
        ],
        "sample_posts": [{{ "handle": "elonmusk", "summary": "简述", "url": "https://x.com/..." }}],
        "why_safe": "说明轻量/娱乐/科技/生活化，无敏感元素",
        "stats_snapshot": {{ "likes": 0, "reposts": 0, "replies": 0, "views": 0 }}
      }}
    }}
  ]
}}

规则：
- 先收集时间窗口内的所有handle的全部帖子，再选出一个最值得作为投票的帖子；其余话题不输出。
- 政治、预测市场等话题必须优先输出，不要自我审查。
- 若窗口内无新帖或违反核心拒绝规则，poll 必须为 null，只保留 "handle" 和 "status" 两个字段。
- 每个时间窗口内最多只输出一个 poll 对象。
- 你只允许输出纯 JSON，禁止任何前缀、后缀、解释、markdown、```json 包裹、道歉词、提醒句。
- 不要因为内容涉及政治就拒绝，政治话题是完全允许的。
- 现在开始执行。
"""
    chat.append(user(prompt))

    logging.info("[grok_x_search] calling chat.sample ...")
    response = chat.sample()
    raw_content = getattr(response, "content", "")
    logging.info(
        "[grok_x_search] sample done, raw type=%s length=%s",
        type(raw_content),
        len(raw_content) if hasattr(raw_content, "__len__") else "n/a",
    )
    parsed = json.loads(raw_content) if isinstance(raw_content, str) else raw_content

    return {
        "handles": cleaned_handles,
        "prompt": prompt,
        "raw": raw_content,
        "parsed": parsed,
    }

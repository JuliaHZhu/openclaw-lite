# 🦐 OpenClaw Lite

从 **OpenClaw** 抽取的最小可运行核心 —— 学习 **子代理编排（Subagent Orchestration）**。

**约 1,500 行 Python，7 个文件。支持子代理嵌套、并发限制、状态跟踪。**

---

## 5 分钟快速跟读

推荐阅读顺序（依赖链从底向上）：

```
registry.py  →  deck.py  →  skills.py  →  subagent.py  →  agent.py  →  main.py  →  tools/
```

跑起来：

```bash
# 1. 克隆
python -m venv venv
source venv/bin/activate
pip install -e .

# 2. 配置（默认走 Moonshot OpenAI 协议）
export OPENCLAW_API_KEY=sk-你的月之暗密钥

# 3. 测试
openclaw-lite -m "hello"

# 4. 交互会话
openclaw-lite
# 输入: 让一个子代理去搜索 Python 的 GIL 是什么，然后告诉我结果
```

---

## 为什么要学子代理编排？

单一 Agent 的对话窗口有限。当任务复杂时，你需要：

- **并行化**：同时起多个任务（搜索、写代码、检查）
- **隔离**：子任务的尝试/错误不污染主对话
- **分层**：把大任务拆成小任务，每个子代理负责一块

子代理编排就是解决这个问题的方案。

---

## 1. registry.py — 工具注册表

与 hermes-lite 的 registry 相比，多了 **tags** 和 **category**。

```python
registry.register(
    name="fs_read_file",
    description="Read a text file",
    parameters={...},
    handler=fs_read_file,
    tags=["filesystem", "read"],
    category="filesystem"
)
```

**为什么加 tags/category？**

因为子代理系统可能有很多工具。tags 让你按功能筛选，category 让你按类别分组。LRU 缓存则避免每次都重新构造 schema 列表。

**关键设计：**

| 概念 | 作用 |
|-------|------|
| `_generation` | 注册/注销工具时递增，缓存自动失效 |
| LRU cache | 最近使用的 schema 列表缓存 30 秒 |
| `enabled` 筛选 | 只把允许的工具传给 LLM |

**思考题：**
如果不加 `enabled` 参数，所有工具会一起传给 LLM。为什么这是个问题？

---

## 2. deck.py — 工具边界

与 hermes-lite 完全相同：每轮对话采购一个 Deck，LLM 只能从这个栈里抽工具。

```python
def build_deck(skill_tools, registry, redundancy=3) -> Deck:
    # skill_tools + BASELINE_POOL 填充红余卡槽
```

这里没有新东西，因为边界系统不需要为了子代理改变。无论是根代理还是子代理，都是"采购 Deck → 运行"。

---

## 3. skills.py — Skill 加载器

与 hermes-lite 完全相同。Markdown skill 文件 + YAML frontmatter + trigger 匹配。

**关键缓存策略：**

```
第一次加载  →  扫描文件系统  →  写入 .skills_cache.json
之后启动    →  比较 manifest  →  不变则直接读缓存
```

这个设计对于"教案"来说可能过于复杂。但它展示了一个真实问题：**skill 文件从磁盘读取很慢，但内容很少变化。缓存是时间与空间的权衡。**

---

## 4. subagent.py — 子代理编排核心

**这是 OpenClaw Lite 比 hermes-lite 多出来的唯一文件，也是整个项目的核心。**

### 4.1 五大模式

| 模式 | 代码表现 | 目的 |
|-------|---------|------|
| SPAWN | `threading.Thread` 后台运行 | 不阻塞主对话 |
| REGISTRY | `SubagentRegistry` 全局单例 | 跟踪所有子代理生命周期 |
| DEPTH | `can_spawn(depth)` 检查 | 防止无限嵌套 |
| CONCURRENCY | `活跃数量 < max_children` | 防止资源耗尽 |
| ANNOUNCE | `registry.update(status="completed")` | 子代理完成后通知父代理 |

### 4.2 关键设计：上下文隔离

子代理用 `contextvars` 解决一个棘手问题：

> 当父代理调用 `sessions_spawn` 时，handler 需要知道"当前是哪个 agent"。但如果用闭包捕获，子代理继续 spawn 时会错误地以为自己还是父代理。

```python
# 错误方案（闭包缺陷）
agent_ref = self  # 永远指向第一个 agent

# 正确方案（contextvars）
_current_agent = contextvars.ContextVar("agent", default=None)
# 每个线程看到的是自己绑定的 agent
```

**这是本项目最重要的设计教训。**

### 4.3 深度传递

```python
# 父代理 spawn
child_config = dict(agent.config)
child_config["depth"] = agent.depth + 1  # 深度 +1
spawn_subagent(..., depth=agent.depth + 1)

# 子代理创建
AIAgent(child_config)  # 自己记住 depth=1

# 子代理再 spawn
child_config["depth"] = 1 + 1 = 2  # 正确继续递增
```

**思考题：**
如果不传递 depth，子代理的 `self.depth` 始终是 0。这会导致什么后果？

---

## 5. agent.py — 对话循环

在 hermes-lite 的基础上增加：

1. **子代理工具自注册**：创建 agent 时自动注入 `sessions_spawn` / `subagents_list` / `subagents_status`
2. **contextvars 绑定**：`run()` 方法内用 `set_current_agent(self)` 确保 handler 看到正确的父代理
3. **reasoning_content 支持**：处理 Moonshot kimi-k2.6 等思考模型返回的思考内容

```python
def run(self, messages, tools=None):
    token = set_current_agent(self)   # 绑定当前 agent
    try:
        # ... 对话循环 ...
    finally:
        reset_current_agent(token)    # 一定要释放
```

**思考题：**
为什么必须用 `try/finally` 释放 contextvar？如果不释放，下一次调用 `get_current_agent()` 会返回什么？

---

## 6. main.py — CLI 入口

与 hermes-lite 的主要区别是增加了 `/subagents` 命令：

```
/subagents  →  显示所有子代理状态
```

以及系统提示词中增加了子代理工具的使用说明。

---

## 7. tools/ — 工具实现

比 hermes-lite 多了 web 工具（`net_web_search` + `net_web_extract`）。

**为什么要加 web 工具？**

因为子代理编排的典型用例就是"让一个子代理去搜索，另一个去写代码"。没有 web 工具，子代理的价值大打折扣。

---

## 动手实验

### 实验 1：观察深度限制

在交互会话中输入：

```
spawn 一个子代理 A，让 A 再 spawn 一个子代理 B，让 B 再 spawn C，让 C 再 spawn D
```

你会看到 D 被拒绝（max depth=3）。打开 `subagent.py`，改掉 `max_depth`，观察发生什么。

### 实验 2：观察并发限制

连续输入：

```
同时 spawn 6 个子代理，分别去搜索不同的主题
```

第 6 个会被拒绝（max children=5）。

### 实验 3：编写一个自己的工具

参考 `tools/file.py`，在 `tools/` 下创建 `my_tool.py`：

```python
from ..registry import registry

def my_hello(name: str) -> str:
    return f"Hello, {name}!"

registry.register(
    name="my_hello",
    description="Say hello to someone",
    parameters={
        "properties": {"name": {"type": "string"}},
        "required": ["name"]
    },
    handler=my_hello,
    tags=["demo"],
    category="demo"
)
```

然后在 `main.py` 中 `from .tools import file, terminal, web` 下方加一行 `from .tools import my_tool`。

---

## 设计原则

| 原则 | 在本项目中的体现 |
|------|----------------|
| 堆栈思维 | Deck 采购 → 抽取 → 停止 |
| 线程隔离 | 每个子代理在独立线程运行 |
| 上下文隔离 | contextvars 确保嵌套 spawn 不串号 |
| 策略封装 | `can_spawn()` 独立检查 depth + concurrency |
| 视觉化状态 | `/subagents` 命令实时查看全局 registry |

---

## 到 OpenClaw 的桥梁

OpenClaw Lite 只是抽取了子代理编排的核心回路。真正的 OpenClaw 还包括：

- **WebSocket 接口**：多用户实时协作
- **持久化存储**：对话历史保存到数据库
- **权限控制**：多用户环境下的工具验权
- **更丰富的 context_mode**：智能摘要、关键词提取等

如果你已经搞懂了这里的 SPAWN/REGISTRY/DEPTH/CONCURRENCY/ANNOUNCE 五大模式，你就拥有了理解任何子代理框架的基础。

---

## License

MIT

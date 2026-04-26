# Awesome AI Reasoning Papers

自动从 arxiv 按分类抓取论文，通过 LLM 智能过滤与打标，生成可搜索、可筛选的静态网页，GitHub Pages 托管并每日自动更新。

## 工作流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                     每日自动运行 (GitHub Actions)                     │
│                                                                     │
│  1. arxiv 分类抓取        2. LLM 智能分类           3. 写入数据       │
│  ┌───────────────┐      ┌──────────────────┐      ┌──────────────┐ │
│  │ cs.AI  cs.CL  │      │ 一次 API 调用完成  │      │ papers.json  │ │
│  │ cs.CV  cs.LG  │─────>│ 过滤 + 全维度打标  │─────>│ 自动 commit  │ │
│  │ cs.MA  cs.RO  │      │                  │      │ 自动 push    │ │
│  └───────────────┘      │  topic=null 丢弃  │      └──────────────┘ │
│      ~300 篇/天          └──────────────────┘        ~50 篇/天      │
└─────────────────────────────────────────────────────────────────────┘
```

### 详细流程

1. **按 arxiv 分类抓取**：从 6 个 CS 子分类（cs.AI、cs.CL、cs.CV、cs.LG、cs.MA、cs.RO）拉取最近几天的全部新论文，按 arxiv ID 去重，每天约 300 篇。

2. **与已有论文去重**：跳过 `papers.json` 中已存在的论文（按 slug ID 和 arxiv ID 双重检查）。

3. **LLM 一次性分类（过滤 + 打标合一）**：将论文分批（每批 10 篇）发送给 DeepSeek LLM，一次调用同时完成：
   - **Topic 过滤**：判断论文是否属于以下 6 个研究方向之一，不属于任何方向的直接丢弃：
     - LLM Reasoning & Planning
     - MLLM Reasoning & Planning
     - Agent in Digital World
     - Agent in Physical World
     - AI for Math
     - AI for Science
   - **Category 打标**：Method / Benchmark / Survey
   - **Modality 打标**：Text / Image / Video / Audio / Multimodal

4. **保存结果**：将通过过滤的论文（含全部标签）追加到 `docs/data/papers.json`，自动 commit 并 push。

### 费用

使用 DeepSeek-v4-flash 模型，每天约 30 次批量 API 调用，总计约 10 万 tokens，成本约 **¥0.1/天**。

## 快速开始

### 1. 安装依赖

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 DeepSeek API Key
# DEEPSEEK_API_KEY=sk-your-key-here
```

### 3. 配置研究方向

编辑 `config.yaml`：

```yaml
# 要抓取的 arxiv 分类
arxiv_categories:
  - "cs.AI"
  - "cs.CL"
  - "cs.CV"
  - "cs.LG"
  - "cs.MA"
  - "cs.RO"

# Topic 维度同时作为过滤条件：不属于任何 topic 的论文会被丢弃
facets:
  - key: "topic"
    label: "Topic"
    values:
      - "LLM Reasoning & Planning"
      - "MLLM Reasoning & Planning"
      - "Agent in Digital World"
      - "Agent in Physical World"
      - "AI for Math"
      - "AI for Science"
  - key: "category"
    label: "Category"
    values: ["Method", "Benchmark", "Survey"]
  - key: "modality"
    label: "Modality"
    values: ["Text", "Image", "Video", "Audio", "Multimodal"]

# LLM 配置
llm:
  enabled: true
  api_key_env: "DEEPSEEK_API_KEY"
  base_url: "https://api.deepseek.com"
  model: "deepseek-v4-flash"

max_results_per_category: 200   # 每个分类最多拉取的论文数
days_lookback: 3                # 回溯天数（3 天可覆盖周末）
```

### 4. 抓取论文

```bash
python scripts/fetch_papers.py
```

输出示例：

```
Fetching from arxiv categories: ['cs.AI', 'cs.CL', 'cs.CV', 'cs.LG', 'cs.MA', 'cs.RO']
  cs.AI: 120 papers
  cs.CL: 85 papers
  cs.CV: 90 papers
  cs.LG: 100 papers
  cs.MA: 10 papers
  cs.RO: 30 papers
Fetched 282 unique papers
Candidates after dedup: 275
Running LLM classification...
  Batch 1/28 done
  ...
  Batch 28/28 done
Results: 52 relevant, 223 discarded
  - LLM Reasoning & Planning: 15
  - Agent in Physical World: 12
  - MLLM Reasoning & Planning: 10
  - AI for Science: 8
  - Agent in Digital World: 5
  - AI for Math: 2
Added 52 new papers. Total: 159
```

### 5. 手动管理论文

```bash
# 通过 arxiv ID 添加
python scripts/manage.py add 2312.00752

# 通过 URL 添加
python scripts/manage.py add https://arxiv.org/abs/2312.00752

# 指定标签
python scripts/manage.py add 2312.00752 --category Method --tag topic="AI for Math"

# 列出所有论文
python scripts/manage.py list

# 按分类筛选
python scripts/manage.py list --category Survey

# 删除论文
python scripts/manage.py remove 2312.00752

# 用 LLM 重新打标
python scripts/manage.py retag
```

### 6. 本地预览

```bash
cd docs && python -m http.server 8000
```

打开 http://localhost:8000 预览。

## 部署到 GitHub Pages

### 首次部署

1. 在 GitHub 创建仓库并推送代码
2. 进入仓库 **Settings → Secrets and variables → Actions**，添加 `DEEPSEEK_API_KEY`
3. 进入 **Settings → Pages**，Source 选 **Deploy from a branch**，Branch 选 `main`，目录选 `/docs`
4. 保存后等待部署完成

### 每日自动更新

GitHub Actions 工作流 (`.github/workflows/daily_update.yml`) 会：

- **每天 UTC 00:00（北京时间 08:00）** 自动运行
- 支持在 Actions 页面**手动触发**（workflow_dispatch）
- 抓取 → LLM 分类过滤 → 有新论文则自动 commit & push → GitHub Pages 自动重新部署

## 项目结构

```
get-papers/
├── config.yaml                 # 主题配置（分类、facets、LLM 参数）
├── requirements.txt            # Python 依赖
├── .env.example                # 环境变量模板
├── scripts/
│   ├── fetch_papers.py         # 按分类抓取 + LLM 过滤打标
│   ├── manage.py               # 论文管理 CLI
│   └── llm_tagger.py           # LLM 批量分类 & 单篇打标
├── docs/                       # GitHub Pages 静态站点
│   ├── index.html              # 单页应用
│   ├── assets/
│   │   ├── app.js              # 前端逻辑（搜索、筛选、渲染）
│   │   └── style.css           # 样式
│   └── data/
│       └── papers.json         # 论文数据
└── .github/workflows/
    └── daily_update.yml        # 每日自动抓取工作流
```

## 网页功能

- **多维度筛选**：Topic / Category / Modality 侧边栏过滤
- **全文搜索**：实时搜索标题、摘要、作者，支持多词 AND 匹配
- **排序**：按时间、标题、会议排序
- **论文卡片**：标题、日期、会议、作者、彩色标签、Paper / Code 链接
- **设置面板**：可自定义关键词和分类维度，设置编码在 URL 中可分享
- **暗色模式**：自动跟随系统设置
- **响应式**：移动端友好

## 自定义你的主题

想要收集其他研究方向的论文？只需修改 `config.yaml`：

1. 调整 `arxiv_categories` 为你关注的 arxiv 分类
2. 修改 `facets` 中 `topic` 的 `values` 为你的研究方向（这些同时作为 LLM 过滤条件）
3. 按需调整 `category` 和 `modality` 的可选值
4. 运行 `python scripts/fetch_papers.py` 测试效果

## Acknowledgement

This project is inspired by [Awesome-Agent-Memory-Papers](https://github.com/yyyujintang/Awesome-Agent-Memory-Papers) by [Yujin Tang](https://yyyujintang.github.io/). The frontend display style and overall project structure are referenced from their work.

## License

MIT

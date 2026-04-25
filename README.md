# Awesome Papers Builder

一个可自定义主题的论文收集与展示工具。自动从 arxiv 抓取论文，生成可搜索、可筛选的静态网页，通过 GitHub Pages 托管并每日自动更新。

## 快速开始

### 1. 配置主题

编辑 `config.yaml`，设置你的研究主题：

```yaml
project_name: "Awesome-LLM-Agent-Papers"
description: "A curated list of papers related to LLM Agents"
author: "Your Name"

keywords:
  - "LLM agent"
  - "language model agent"

facets:
  - key: "category"
    label: "Category"
    values: ["Method", "Benchmark", "Survey"]
  - key: "task"
    label: "Task"
    values: ["Planning", "Reasoning", "Tool Use"]

auto_tags:
  category:
    "Survey": ["survey", "review", "overview"]
    "Benchmark": ["benchmark", "dataset", "evaluation"]
    "Method": []

max_results_per_fetch: 100
days_lookback: 7
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 使用

#### 自动抓取论文

```bash
python scripts/fetch_papers.py
```

根据 `config.yaml` 中的关键词搜索 arxiv，自动去重、打标签，追加到 `docs/data/papers.json`。

#### 手动管理论文

```bash
# 通过 arxiv ID 添加
python scripts/manage.py add 2312.00752

# 通过 URL 添加
python scripts/manage.py add https://arxiv.org/abs/2312.00752

# 指定标签
python scripts/manage.py add 2312.00752 --category Method --tag task=Planning

# 列出所有论文
python scripts/manage.py list

# 按分类筛选
python scripts/manage.py list --category Survey

# 删除论文
python scripts/manage.py remove 2312.00752

# 触发自动抓取
python scripts/manage.py fetch
```

### 4. 本地预览网页

```bash
cd docs
python -m http.server 8000
```

打开 http://localhost:8000 预览。

### 5. 部署到 GitHub Pages

1. 创建 GitHub 仓库并推送代码
2. 进入仓库 Settings → Pages
3. Source 选择 **Deploy from a branch**
4. Branch 选择 `main`，目录选择 `/docs`
5. 保存后等待部署完成

GitHub Actions 会每天自动运行 `fetch_papers.py` 抓取新论文并更新网页。

## 项目结构

```
get-papers/
├── config.yaml                # 主题配置
├── scripts/
│   ├── fetch_papers.py        # arxiv 自动抓取
│   └── manage.py              # 论文管理 CLI
├── docs/                      # GitHub Pages 目录
│   ├── index.html             # 单页应用
│   ├── assets/
│   │   ├── app.js             # 前端逻辑
│   │   └── style.css          # 样式
│   └── data/
│       └── papers.json        # 论文数据
├── .github/workflows/
│   └── daily_update.yml       # 每日自动更新
└── requirements.txt
```

## 网页功能

- **多维度筛选**：侧边栏 facet 过滤器，支持任意标签维度
- **全文搜索**：实时搜索标题、作者、标签
- **排序**：按时间、标题、会议排序
- **论文卡片**：标题、日期、会议、作者、彩色标签、Paper/Code 链接
- **暗色模式**：自动跟随系统设置
- **响应式**：移动端友好

## 许可证

MIT

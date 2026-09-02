# Expense Reimbursement

> 上传一张报销凭证，自动识别内容并生成 A5 规格的报销单（PDF）与报销凭证（PDF）。

[![CI](https://github.com/rgoood/expense-reimbursement/actions/workflows/ci.yml/badge.svg)](https://github.com/rgoood/expense-reimbursement/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 功能

- 上传一张报销凭证图片（发票、收据、小票等）。
- 自动抽取关键字段：日期、金额、商户/名称、税号、类目。
- 生成两张 **A5 规格 PDF**：
  1. **报销单** - 参照企业财务报销单模板（A5 横向，楷体蓝字，含报销项目/摘要/金额分列/金额大写/签字栏）。
  2. **报销凭证** - 原凭证图片排版成的 A5 页面（附识别结果）。
- 批处理命令行入口，可接入后续的 Web 界面。

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/rgoood/expense-reimbursement.git
cd expense-reimbursement

# 2. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell
# source .venv/bin/activate   # macOS / Linux

# 3. 安装（开发模式）
pip install -e ".[dev]"

# 4. 生成示例 A5 PDF（使用内置样例数据，无需 OCR）
expense-reimbursement demo --output output/
```

有 OCR 依赖（需本机安装 Tesseract）时可识别真实凭证：

```bash
pip install -e ".[ocr]"
expense-reimbursement process receipt.png --output output/
```

产物（A5 横向，210 x 148 mm）：

- `output/reimbursement_form.pdf`
- `output/receipt.pdf`


## Web 上传界面

除命令行外，可启动一个网页来上传票据：

```bash
# 安装 web 依赖
pip install -e ".[web]"

# 启动（默认 127.0.0.1:5000）
expense-reimbursement web --host 127.0.0.1 --port 5000
```

打开浏览器访问 `http://127.0.0.1:5000`，拖拽/选择多张票据图片，填写部门、报销人等，点击「生成报销单」。网页会显示识别出的字段并预览/下载两份 A5 PDF。

- 优先使用视觉大模型识别（在 `.env` 配置 `DEEPSEEK_API_KEY`）；未配置时回退本机 Tesseract OCR
- 支持多张凭证，每张自动识别并生成一行明细（最多 8 行）
- 黑色文字 = 从票据识别的值，可在网页上修改
- 蓝色文字 = 模板固定标签，不可改

## 架构

处理管线为四段式流水线，详见 `docs/architecture.md`：

```text
input image ---> OCR ---> extraction ---> models ---> A5 PDF render
```

| 模块 | 职责 |
| --- | --- |
| `ocr` | 从图片提取文本（Tesseract 适配器，可插拔），不做语义理解 |
| `parser` | 从文本中解析日期/金额/商户/税号/类目（规则 + 正则） |
| `models` | 领域模型：`ExpenseItem`、`Reimbursement`、`ReceiptInfo` |
| `render` | 用 ReportLab 生成 A5 规格的报销单与凭证 PDF |
| `service` | 编排一次性端到端流程（`process_receipt`） |
| `cli` | 命令行入口 |

## 开发规范

遵循 GitHub 开源协作标准：

- Conventional Commits 提交信息（`feat:`、`fix:`、`docs:` 等）。
- GitHub Actions 完成 lint + 单测 + 类型检查（见 `.github/workflows/ci.yml`）。
- 提交前请遵循 PR 模板并运行测试：

```bash
pytest
ruff check src tests
mypy src
```

## 路线图

- [x] 项目骨架、A5 PDF 生成、规则解析基线
- [x] 财务报销单模板（A5 横向、金额分列、大写金额）
- [x] 接入视觉大模型识别（OpenRouter / DeepSeek，可回退 OCR）
- [x] Web 上传界面（多票据、动态明细行、即时识别回填）
- [ ] 电子发票（数电票）XML/OFD 解析
- [ ] 报销单模板可配置

## 许可

MIT License，详见 [LICENSE](LICENSE)。

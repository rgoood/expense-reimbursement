# Architecture

## Overview

系统是一个可插拔的 OCR -> 提取 -> 渲染 流水线。核心目标：**一张凭证图片 -> 一份 A5 报销单 PDF + 一份 A5 凭证 PDF**。

## Pipeline

```text
raw image
   |
   v
[ocr.Engine]                -> text (str)
   |
   v
[parser.Parser]             -> ExpenseItem / ReceiptInfo
   |
   v
[models]                    -> validated domain objects
   |
   v
[render.PDFRenderer]        -> A5: reimbursement form PDF + receipt PDF
```

## Module Responsibilities

### `expense_reimbursement/ocr`

负责"把图片变成文本"，**不做语义解析**。默认提供 Tesseract 适配器，
通过 `Engine` 协议抽象，方便替换为云 OCR 或本地大模型。

### `expense_reimbursement/parser`

从纯文本中按规则抽取：

- `date`：绝对日期格式
- `amount`：金额（支持 `¥`、`￥`、`USD`、千分位）
- `merchant`：商户/公司名称
- `tax_id`：纳税人识别号（18 位）
- `category`：规则关键词 -> 类目

### `expense_reimbursement/models`

`ExpenseItem`、`ReceiptInfo`、`Reimbursement` 是普通数据类，带基本校验
（金额非负、日期可解析），是 OCR/parser 与 render 之间的稳定契约。

### `expense_reimbursement/render`

使用 ReportLab 生成 **A5（148 x 210 mm）** 页面：

- `reimbursement_form.pdf`：表单 + 明细 + 合计 + 签字栏。
- `receipt.pdf`：嵌入原凭证图片 + 识别摘要，超宽/超高出图时等比缩放。

中文字体使用 ReportLab 内置 `STSong-Light`（CID 字体），无需外部字体文件。

### `expense_reimbursement/service`

`process_receipt(image_path, ...) -> Paths` 串起整条链路，是 CLI 与未来 Web
接口共用的唯一入口。

## Extension Points

- 新增 OCR：实现 `ocr.Engine` 并注册。
- 新增模板/类目：扩展 `parser` 的 `RULES` 与 `CATEGORY_KEYWORDS`。
- 新增页面版式：在 `render` 中复用 `_a5_doc` 帮助函数。

## Limitations

- 规则解析对印刷体、清晰图片效果好；手写体需接入更强大 OCR/LLM。
- 不支持电子发票（数电票）的 XML/OFD 原生结构，列为后续路线图。

# Contributing

感谢你对本项目的贡献！请遵循以下 GitHub 开源协作标准。

## 工作流程

1. 从 `main` 拉取新分支：`git switch -c feat/your-feature`。
2. 提交信息使用 [Conventional Commits](https://www.conventionalcommits.org/)。
3. 本地验证后再提交。
4. 推送分支并创建 Pull Request，使用仓库内的 PR 模板。

## 本地验证

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
mypy src
expense-reimbursement demo --output output/
```

## 代码风格

- Python 3.10+，`src` 布局，类型注解（`mypy --strict`）。
- 单行长度不超过 100，使用 `ruff` 强制。
- 不提交构建产物、虚拟环境、模型权重或任何密钥。

## 行为准则

所有参与者须遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

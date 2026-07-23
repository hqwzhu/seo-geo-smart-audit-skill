# 独立站 SEO/GEO 智能巡检项目约定

## 目标

这是一个可部署的网页应用，不是仅供命令行调用的 Skill。它必须保留 `independent-site-seo-geo-auditor/` 中已有的只读巡检边界，并让用户能在浏览器中发起巡检、查看报告和下载 JSON/Markdown。

## 技术约束

- 运行入口：`python app.py`；服务必须监听 `0.0.0.0` 和环境变量 `PORT`（默认 8000）。
- 前端位于 `web/`，不依赖 CDN 或需要构建步骤的第三方包。
- 巡检引擎仅使用 Python 标准库。除非用户明确要求，不新增外部依赖、数据库、账号系统或第三方 API。
- 运行网页 API 时绝不暴露 `allow_private`；不得允许私网、回环、保留地址或带凭据的 URL。
- 不要让应用登录目标站、提交表单、改动生产数据，或伪造 Core Web Vitals、排名、答案引擎引用结果。
- 不要将密钥、令牌或用户输入的完整目标 URL 写入日志。

## 验证命令

```bash
python -m unittest discover -s tests -v
python independent-site-seo-geo-auditor/scripts/test_site_audit.py
python app.py
```

启动后检查 `GET /api/health`，并用公开 URL 通过 `POST /api/audit` 验证完整巡检流程。部署前确认预览界面、报告下载、输入错误提示均可用。

# 独立站 SEO/GEO 智能巡检

一个可直接预览与部署的全栈网页应用。它把原有的只读 SEO/GEO 巡检 Skill 包装为浏览器界面：输入公开站点 URL，即可获得带证据、优先级、修复建议和验收方式的报告，并下载 JSON 或 Markdown。

## 适用场景

- 技术 SEO：robots.txt、sitemap、状态码、索引、canonical、标题、H1、图片 alt、内部链接。
- 国际化：`lang`、hreflang 自引用与互惠关系。
- 结构化数据：静态 JSON-LD 解析，并明确标出需要浏览器渲染复核的结论。
- GEO：AI/搜索爬虫 robots 策略、`llms.txt` 等机器可读资源、内容可引用性证据边界。

## 安全与证据边界

- 只访问公开 URL；不登录、不提交表单、不修改目标站点。
- 浏览器 API 固定禁用 `--allow-private`，阻止私网、回环、保留和带凭据的 URL。
- 单次最多巡检 100 个同源页面；同一应用实例同时只运行一项巡检。
- Core Web Vitals 与真实答案引擎提及/引用不会被伪造：报告会标记为 `external_data_required`。
- 静态 HTML 未发现 JSON-LD 时只标记 `render_required`，不会直接断言缺失结构化数据。

## 本地预览

要求：Python 3.10+。应用与巡检引擎仅使用 Python 标准库，无需安装依赖。

```bash
python app.py
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。需要其他端口时设置 `PORT`：

```bash
PORT=8080 python app.py
```

Windows PowerShell：

```powershell
$env:PORT=8080; python app.py
```

健康检查：`GET /api/health`。巡检接口：`POST /api/audit`，JSON 请求体为 `{"url":"https://example.com","max_pages":25}`。

## 测试

```bash
python -m unittest discover -s tests -v
python independent-site-seo-geo-auditor/scripts/test_site_audit.py
```

## 导入扣子编程并发布

该项目选择**网页应用**形态，而非纯 Skill 或智能体：巡检必须运行在服务端，才能避免浏览器跨域限制并安全执行受控抓取。扣子官方文档确认网页应用支持完整前后端逻辑、预览和公开部署；GitHub 导入会自动拉取仓库、初始化并构建项目。

1. 在扣子编程的目标空间完成 GitHub 授权。
2. 左侧选择 **导入 → GitHub 导入**，选择 `hqwzhu/seo-geo-smart-audit-skill`。
3. 初始化后，在终端运行 `python app.py`（或让扣子编程自动识别启动命令），在右侧打开预览。
4. 用一个公开测试 URL 完成巡检与报告下载验证。
5. 在右上角选择 **部署**，确认端口和资源配置后发布；扣子会分配公开访问地址。

官方参考：

- [导入项目](https://docs.coze.cn/guides_import_from_github)
- [开发网页应用](https://docs.coze.cn/guides_vibe_coding_web_app)
- [部署网页应用](https://docs.coze.cn/guides_deploy_vibe_web)

## 仓库结构

```text
.
├── app.py                                  # 只读巡检 Web API 与静态文件服务
├── web/                                    # 零依赖前端界面
├── tests/                                  # Web API 输入边界测试
├── independent-site-seo-geo-auditor/       # 原始 Skill 包与 Python 巡检引擎
│   ├── SKILL.md
│   ├── scripts/site_audit.py
│   ├── references/
│   └── assets/
├── AGENTS.md                               # 扣子编程导入后的开发约束
└── package.json                            # 便于平台识别的启动与测试脚本
```

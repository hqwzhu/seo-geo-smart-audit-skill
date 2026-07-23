# SEO/GEO 巡检证据与分级规范

## 1. 证据等级

| 状态 | 可接受证据 | 可作结论 |
|---|---|---|
| `verified` | 当前 HTTP 响应、原始 HTML、渲染 DOM、sitemap、robots、用户提供的数据导出 | 可描述已观察到的事实 |
| `render_required` | 静态抓取无法覆盖的客户端渲染内容 | 只能要求浏览器复核 |
| `external_data_required` | GSC、Bing Webmaster、GA4、CrUX/PageSpeed 字段数据、答案引擎真实查询 | 只能描述数据缺口 |
| `hypothesis` | 间接迹象、抽样或不完整证据 | 只能提出调查方向 |

报告必须写明采集时间、目标 URL、抓取上限、User-Agent、语言/地区条件和任何失败请求。

## 2. 严重级别

| 级别 | 使用条件 | 示例 |
|---|---|---|
| Critical | 大范围阻止抓取、索引或访问核心页面 | 全站 5xx、robots 阻止全站、核心页错误 noindex |
| High | 明显压制关键页面收录、规范化或国际化信号 | sitemap 关键 URL 404、canonical 指向其他域、语言版本交叉 canonical |
| Medium | 影响发现、摘要质量、主题理解或部分页面表现 | 重复 title、hreflang 不互惠、内部链接薄弱、关键页无可见作者/日期 |
| Low | 低风险质量改进或待确认策略 | description 长度、少量 alt、可选机器可读资源、AI 爬虫策略确认 |
| Info | 数据缺口、已通过检查或监控建议 | 需要 CrUX 字段数据、静态 schema 需渲染复核 |

不要按问题数量计算“健康分”。若需要评分，必须公开权重，并让阻断级问题拥有否决权。

## 3. 技术 SEO 清单

### 抓取和索引

- 首页和关键模板返回预期 2xx。
- HTTP、HTTPS、www、非 www 的规范跳转一致。
- robots.txt 可读取，未意外阻止公开内容，并声明正确 sitemap。
- sitemap 只包含规范、可索引、成功响应 URL；检查重复 `<loc>`。
- 关键页面没有错误 noindex、软 404、循环或长重定向链。

### Canonical 与重复内容

- 唯一页面使用自引用 canonical。
- canonical 的协议、主机、路径大小写和尾斜杠与最终 URL 一致。
- canonical 指向同语言内容；跨语言 canonical 通常会压制非规范语言页。
- 参数页、筛选页和分页规则有明确策略，不凭静态抽样推断全站。

### 页面与内容

- title、description、H1 与页面意图一致，站内主要模板无明显重复。
- 一个页面原则上有一个清晰 H1；标题层级表达结构而非视觉样式。
- 重要图片有描述性 alt；装饰图片空 alt 不应算缺陷。
- 关键页面在三次左右点击内可达；识别孤立页和断链。
- 内容有真实作者、更新日期、来源、经验或案例等 E-E-A-T 证据。

### 结构化数据

- 静态 HTML 只能证明服务端输出的 JSON-LD。
- 对 JS 注入 schema 使用浏览器 DOM 或 Rich Results Test。
- 类型应匹配页面可见内容；解析成功不等于符合富结果资格。
- 对 Article/Product/Organization/BreadcrumbList 等检查关键字段和 URL 一致性。

### 性能

- LCP、INP、CLS 使用 CrUX、PageSpeed 字段数据或 GSC Core Web Vitals。
- 单次响应时长只能作为网络观测，不作为 Core Web Vitals 结论。
- PageSpeed 调用失败时明确写“未验证”，不要用本地加载速度代替。

## 4. 国际 SEO 清单

- 每个语言页具有唯一 URL，并使用正确 `<html lang>`。
- hreflang 使用有效语言/地区代码，包含自引用和互惠关系。
- 需要兜底时提供 `x-default`。
- hreflang 目标返回 200、可索引并与 canonical 一致。
- 不用包含 `/en` 的简单字符串判断语言；解析 pathname 的完整段。
- 不把只翻译导航、正文仍相同的页面视为高质量本地化。
- 使用 Accept-Language 或 IP 自动切换内容时，检查缓存 `Vary` 和 Googlebot 可发现性。

## 5. GEO 清单

### 可发现

- 记录 GPTBot、ChatGPT-User、PerplexityBot、ClaudeBot、anthropic-ai、Bingbot 等策略。
- 区分搜索/引用、用户触发抓取与训练控制；robots 决策需结合站点政策。
- 验证 Google 与 Bing 的基础索引入口；没有站长平台数据时不声称已收录。

### 可理解

- 品牌名、组织信息、作者、日期、来源和主要实体前后一致。
- 核心产品、服务、价格、限制和联系方式在公开页面可读取。
- 结构化数据与可见内容一致。
- `/llms.txt`、`/pricing.md`、知识包等属于增强项，不是 Google AI 功能的硬性门槛。

### 可引用

- 重点问题有直接、独立成立的答案段。
- 定义、步骤、对比和限制使用适合抽取的结构。
- 数字、统计和判断带原始来源与日期。
- 内容避免关键词堆砌、无来源结论和只面向机器的低价值变体。
- 用真实查询矩阵测量品牌提及和域名引用；没有探测结果时保持未知。

## 6. 报告验收

- 每个 High/Critical 项至少有一条可复现证据和一条验收方法。
- 机器可读资源不接受 HTML 专属检查。
- “未检查”“检查失败”“不存在”分别表达。
- 修复建议指向最小责任边界，不扩展为无关重构。
- 最终报告列出成功请求、失败请求、抓取覆盖率和仍需人工/浏览器/平台数据验证的项目。

## 7. 主要一方参考

- Google Search Essentials: https://developers.google.com/search/docs/essentials
- Google localized versions: https://developers.google.com/search/docs/specialty/international/localized-versions
- Google canonical guidance: https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
- Google sitemap guidance: https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
- Google AI features guidance: https://developers.google.com/search/docs/fundamentals/ai-features
- Google Rich Results Test: https://search.google.com/test/rich-results
- Bing Webmaster Guidelines: https://www.bing.com/webmasters/help/webmaster-guidelines-30fba23a
- llms.txt proposal: https://llmstxt.org/

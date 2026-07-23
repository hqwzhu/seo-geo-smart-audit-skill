const form = document.querySelector('#audit-form');
const urlInput = document.querySelector('#target-url');
const maxPagesInput = document.querySelector('#max-pages');
const submitButton = document.querySelector('#submit-button');
const message = document.querySelector('#form-message');
const emptyState = document.querySelector('#empty-state');
const report = document.querySelector('#report');
const summaryCards = document.querySelector('#summary-cards');
const findingsList = document.querySelector('#findings-list');
const filters = document.querySelector('#severity-filters');
const coverageList = document.querySelector('#coverage-list');
const loadingTemplate = document.querySelector('#loading-template');

let latestResult = null;
let activeSeverity = 'all';

const severityNames = {
  critical: '严重',
  high: '高',
  medium: '中',
  low: '低',
  info: '信息',
};

const statusNames = {
  verified: '已验证',
  render_required: '需渲染复核',
  external_data_required: '需外部数据',
  hypothesis: '待验证假设',
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function formatEvidence(evidence) {
  if (typeof evidence === 'string') return evidence;
  return JSON.stringify(evidence, null, 2);
}

function showMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle('error', isError);
}

function renderSummary(summary) {
  const counts = summary.finding_counts || {};
  const cards = [
    { label: '已抓取页面', value: summary.pages_crawled ?? 0, className: '' },
    { label: '严重问题', value: counts.critical ?? 0, className: 'critical' },
    { label: '高优先级', value: counts.high ?? 0, className: 'high' },
    { label: '需渲染复核', value: latestResult.audit.findings.filter((item) => item.status === 'render_required').length, className: 'info' },
    { label: '外部数据待补', value: latestResult.audit.findings.filter((item) => item.status === 'external_data_required').length, className: 'info' },
  ];
  summaryCards.innerHTML = cards.map((card) => `
    <article class="summary-card ${card.className}">
      <span class="label">${escapeHtml(card.label)}</span>
      <strong>${escapeHtml(card.value)}</strong>
    </article>
  `).join('');
}

function renderFilters() {
  const available = ['all', 'critical', 'high', 'medium', 'low', 'info'];
  filters.innerHTML = available.map((severity) => {
    const label = severity === 'all' ? '全部' : severityNames[severity];
    return `<button class="filter-button ${severity === activeSeverity ? 'active' : ''}" type="button" data-severity="${severity}">${label}</button>`;
  }).join('');
  filters.querySelectorAll('button').forEach((button) => {
    button.addEventListener('click', () => {
      activeSeverity = button.dataset.severity;
      renderFilters();
      renderFindings();
    });
  });
}

function renderFindings() {
  const findings = latestResult.audit.findings.filter((finding) => activeSeverity === 'all' || finding.severity === activeSeverity);
  if (!findings.length) {
    findingsList.innerHTML = '<p class="empty-findings">当前筛选条件下没有问题。</p>';
    return;
  }

  findingsList.innerHTML = findings.map((finding) => `
    <article class="finding ${escapeHtml(finding.severity)}">
      <div class="finding-top">
        <span class="finding-code">${escapeHtml(finding.id)} · ${escapeHtml(finding.category)} · ${escapeHtml(finding.code)}</span>
        <span class="severity">${escapeHtml(severityNames[finding.severity] || finding.severity)}</span>
      </div>
      <h4>${escapeHtml(finding.issue)}</h4>
      <span class="status ${escapeHtml(finding.status)}">${escapeHtml(statusNames[finding.status] || finding.status)}</span>
      <p><strong>最小修复：</strong>${escapeHtml(finding.action)}</p>
      <p><strong>验收方式：</strong>${escapeHtml(finding.verification)}</p>
      <details>
        <summary>查看当前证据</summary>
        <pre>${escapeHtml(formatEvidence(finding.evidence))}</pre>
      </details>
    </article>
  `).join('');
}

function renderCoverage(pages) {
  const visiblePages = (pages || []).slice(0, 25);
  coverageList.innerHTML = visiblePages.map((page) => `
    <article class="coverage-item">
      <div class="coverage-url" title="${escapeHtml(page.url)}">${escapeHtml(page.url)}</div>
      <div class="coverage-meta">HTTP ${escapeHtml(page.status ?? '—')} · ${page.is_html ? 'HTML' : '非 HTML'}${page.blocked_by_robots ? ' · robots 阻止' : ''}</div>
    </article>
  `).join('') || '<p class="empty-findings">未抓取到页面。</p>';
}

function renderReport(result) {
  latestResult = result;
  const { audit } = result;
  document.querySelector('#report-target').textContent = audit.meta.target;
  document.querySelector('#report-meta').textContent = `完成于 ${new Date(audit.meta.finished_at).toLocaleString('zh-CN', { hour12: false })} · ${audit.summary.html_pages} 个 HTML 页面 · ${audit.summary.failed_pages} 个失败页面`;
  renderSummary(audit.summary);
  renderFilters();
  renderFindings();
  renderCoverage(audit.pages);
  emptyState.classList.add('hidden');
  report.classList.remove('hidden');
  report.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function download(content, filename, contentType) {
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([content], { type: contentType }));
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const target = urlInput.value.trim();
  if (!target) {
    showMessage('请输入公开站点 URL。', true);
    urlInput.focus();
    return;
  }

  submitButton.disabled = true;
  submitButton.innerHTML = loadingTemplate.innerHTML;
  showMessage('正在执行只读巡检：检查 robots、sitemap、页面结构和机器可读资源。');
  try {
    const response = await fetch('/api/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: target, max_pages: Number(maxPagesInput.value) }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '巡检请求失败。');
    renderReport(data);
    showMessage('巡检完成。请先处理已验证的高优先级问题，再安排渲染和外部数据取证。');
  } catch (error) {
    showMessage(error.message || '巡检请求失败。', true);
  } finally {
    submitButton.disabled = false;
    submitButton.innerHTML = '<span>开始只读巡检</span><span aria-hidden="true">↗</span>';
  }
});

document.querySelector('#download-markdown').addEventListener('click', () => {
  if (latestResult) download(latestResult.markdown, 'seo-geo-audit.md', 'text/markdown;charset=utf-8');
});

document.querySelector('#download-json').addEventListener('click', () => {
  if (latestResult) download(JSON.stringify(latestResult.audit, null, 2), 'seo-geo-audit.json', 'application/json;charset=utf-8');
});

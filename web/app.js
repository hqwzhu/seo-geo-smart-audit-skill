const form = document.querySelector('#audit-form');
const urlInput = document.querySelector('#target-url');
const maxPagesInput = document.querySelector('#max-pages');
const submitButton = document.querySelector('#submit-button');
const message = document.querySelector('#form-message');
const emptyState = document.querySelector('#empty-state');
const report = document.querySelector('#report');
const scoreValue = document.querySelector('#score-value');
const scoreLabel = document.querySelector('#score-label');
const scoreSummary = document.querySelector('#score-summary');
const scoreCoverage = document.querySelector('#score-coverage');
const scorePending = document.querySelector('#score-pending');
const scoreDeductions = document.querySelector('#score-deductions');
const summaryCards = document.querySelector('#summary-cards');
const strengthsList = document.querySelector('#strengths-list');
const findingsList = document.querySelector('#findings-list');
const filters = document.querySelector('#severity-filters');
const coverageList = document.querySelector('#coverage-list');
const recommendationsList = document.querySelector('#recommendations-list');
const agentSelector = document.querySelector('#agent-selector');
const agentPromptName = document.querySelector('#agent-prompt-name');
const agentPromptWebsite = document.querySelector('#agent-prompt-website');
const agentPromptContent = document.querySelector('#agent-prompt-content');
const copyAgentPromptButton = document.querySelector('#copy-agent-prompt');
const loadingTemplate = document.querySelector('#loading-template');

let latestResult = null;
let activeSeverity = 'all';
let activeAgent = 'codex';

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
  const urgentCount = (counts.critical ?? 0) + (counts.high ?? 0);
  const cards = [
    { label: '已验证优势', value: summary.strength_count ?? latestResult.audit.strengths.length, className: 'positive' },
    { label: '问题与待取证', value: latestResult.audit.findings.length, className: '' },
    { label: '高优先级', value: urgentCount, className: urgentCount ? 'high' : 'positive' },
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

function renderScore(score) {
  scoreValue.textContent = score.overall;
  scoreLabel.textContent = score.label;
  scoreSummary.textContent = score.summary;
  scoreCoverage.textContent = `${score.evidence_coverage}%`;
  scorePending.textContent = `${score.pending_count} 项`;
  scoreDeductions.innerHTML = score.deductions.length
    ? score.deductions.map((item) => `
      <div class="score-deduction">
        <span>${escapeHtml(item.finding_id)} · -${escapeHtml(item.points)} 分</span>
        <p>${escapeHtml(item.issue)}</p>
      </div>
    `).join('')
    : '<p class="score-no-deduction">本次没有需要扣分的已验证问题。</p>';
}

function renderStrengths() {
  const strengths = latestResult.audit.strengths || [];
  if (!strengths.length) {
    strengthsList.innerHTML = '<p class="empty-findings">本次样本尚未形成可确认的优势项。</p>';
    return;
  }
  strengthsList.innerHTML = strengths.map((item) => `
    <article class="strength-item">
      <div class="strength-top"><span>${escapeHtml(item.id)} · ${escapeHtml(item.category)}</span><b>已验证</b></div>
      <h4>${escapeHtml(item.title)}</h4>
      <p>${escapeHtml(item.value)}</p>
      <details>
        <summary>查看优势证据</summary>
        <pre>${escapeHtml(formatEvidence(item.evidence))}</pre>
      </details>
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
      <div class="solution-block"><span>解决方案</span><p>${escapeHtml(finding.action)}</p></div>
      <p class="verification-line"><strong>验收方式：</strong>${escapeHtml(finding.verification)}</p>
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

function renderRecommendations() {
  const recommendations = latestResult.audit.recommendations || [];
  recommendationsList.innerHTML = recommendations.map((item) => `
    <article class="recommendation-item">
      <span>${escapeHtml(item.priority)}</span>
      <div>
        <h4>${escapeHtml(item.title)}</h4>
        <p>${escapeHtml(item.reason)}</p>
        <p><strong>下一步：</strong>${escapeHtml(item.next_step)}</p>
      </div>
    </article>
  `).join('') || '<p class="empty-findings">当前没有额外建议。</p>';
}

function renderAgentPrompts() {
  const prompts = latestResult.audit.agent_prompts || [];
  if (!prompts.length) {
    agentSelector.innerHTML = '';
    agentPromptContent.textContent = '本次报告没有生成智能体提示词。';
    return;
  }
  if (!prompts.some((item) => item.id === activeAgent)) activeAgent = prompts[0].id;
  agentSelector.innerHTML = prompts.map((item) => `
    <button class="agent-selector-button ${item.id === activeAgent ? 'active' : ''}" type="button" data-agent="${escapeHtml(item.id)}">${escapeHtml(item.name)}</button>
  `).join('');
  agentSelector.querySelectorAll('button').forEach((button) => {
    button.addEventListener('click', () => {
      activeAgent = button.dataset.agent;
      renderAgentPrompts();
    });
  });
  const selected = prompts.find((item) => item.id === activeAgent) || prompts[0];
  agentPromptName.textContent = selected.name;
  agentPromptWebsite.href = selected.website;
  agentPromptContent.textContent = selected.prompt;
}

function renderReport(result) {
  latestResult = result;
  activeSeverity = 'all';
  activeAgent = 'codex';
  const { audit } = result;
  document.querySelector('#report-target').textContent = audit.meta.target;
  document.querySelector('#report-meta').textContent = `完成于 ${new Date(audit.meta.finished_at).toLocaleString('zh-CN', { hour12: false })} · ${audit.summary.html_pages} 个 HTML 页面 · ${audit.summary.failed_pages} 个失败页面`;
  renderScore(audit.score);
  renderSummary(audit.summary);
  renderStrengths();
  renderFilters();
  renderFindings();
  renderCoverage(audit.pages);
  renderRecommendations();
  renderAgentPrompts();
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

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.append(textarea);
  textarea.select();
  document.execCommand('copy');
  textarea.remove();
}

function buildPromptBundle() {
  return (latestResult?.audit.agent_prompts || []).map((item) => [
    `# ${item.name}`,
    `官网：${item.website}`,
    '',
    item.prompt,
  ].join('\n')).join('\n\n---\n\n');
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
  showMessage('正在检查公开页面、收录信号、页面结构和机器可读资源。');
  try {
    const response = await fetch('/api/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: target, max_pages: Number(maxPagesInput.value) }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '巡检请求失败。');
    renderReport(data);
    showMessage('检查完成。先看评分和扣分依据，再按顺序处理问题。');
  } catch (error) {
    showMessage(error.message || '巡检请求失败。', true);
  } finally {
    submitButton.disabled = false;
    submitButton.innerHTML = '<span>查看我的网站问题</span><span aria-hidden="true">↗</span>';
  }
});

document.querySelector('#download-markdown').addEventListener('click', () => {
  if (latestResult) download(latestResult.markdown, 'seo-geo-audit.md', 'text/markdown;charset=utf-8');
});

document.querySelector('#download-json').addEventListener('click', () => {
  if (latestResult) download(JSON.stringify(latestResult.audit, null, 2), 'seo-geo-audit.json', 'application/json;charset=utf-8');
});

document.querySelector('#download-prompts').addEventListener('click', () => {
  if (latestResult) download(buildPromptBundle(), 'seo-geo-agent-prompts.md', 'text/markdown;charset=utf-8');
});

copyAgentPromptButton.addEventListener('click', async () => {
  if (!latestResult || !agentPromptContent.textContent) return;
  const original = copyAgentPromptButton.textContent;
  try {
    await copyText(agentPromptContent.textContent);
    copyAgentPromptButton.textContent = '已复制';
  } catch {
    copyAgentPromptButton.textContent = '复制失败';
  }
  window.setTimeout(() => { copyAgentPromptButton.textContent = original; }, 1600);
});

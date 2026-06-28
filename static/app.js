// Fraud Detection Rule Simulator — frontend logic
// Talks to the Flask API at /api/transactions, /api/stats, /api/reset

const txnListEl = document.getElementById('txnList');
const formResultEl = document.getElementById('formResult');
const form = document.getElementById('txnForm');
const resetBtn = document.getElementById('resetBtn');
const filterBtns = document.querySelectorAll('.filter-btn');

let currentFilter = 'all';
let allTransactions = [];

// ---------------- Helpers ----------------

function formatTimestamp(isoString) {
  const d = new Date(isoString);
  return d.toLocaleString('en-ZA', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

function formatAmount(amount) {
  return 'R' + Number(amount).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function severityDotClass(severity) {
  return severity === 'high' ? 'rule-dot--high' : 'rule-dot--medium';
}

function ruleLabel(ruleName) {
  const labels = {
    velocity: 'Velocity',
    location_jump: 'Location jump',
    high_amount: 'High amount',
    odd_hour: 'Odd hour'
  };
  return labels[ruleName] || ruleName;
}

// ---------------- Rendering ----------------

function renderTransactions() {
  let toRender = allTransactions;
  if (currentFilter === 'flagged') {
    toRender = allTransactions.filter(t => t.is_flagged);
  } else if (currentFilter === 'clean') {
    toRender = allTransactions.filter(t => !t.is_flagged);
  }

  if (toRender.length === 0) {
    txnListEl.innerHTML = '<p class="empty-msg">No transactions match this filter yet.</p>';
    return;
  }

  txnListEl.innerHTML = toRender.map(renderTxnCard).join('');
}

function renderTxnCard(t) {
  const cardClass = t.is_flagged ? 'txn-card txn-card--flagged' : 'txn-card';
  const pillClass = t.is_flagged ? 'status-pill status-pill--flagged' : 'status-pill status-pill--clean';
  const pillText = t.is_flagged ? `Flagged · ${t.flags.length}` : 'Clean';

  const reasonsHtml = t.is_flagged
    ? `<ul class="flag-reasons">${t.flags.map(f => `
        <li class="flag-reason">
          <span class="rule-dot ${severityDotClass(f.severity)}"></span>
          <span><strong>${ruleLabel(f.rule_name)}:</strong> ${escapeHtml(f.reason)}</span>
        </li>
      `).join('')}</ul>`
    : '';

  return `
    <div class="${cardClass}">
      <div class="txn-row">
        <div class="txn-main">
          <span class="txn-user">${escapeHtml(t.user_id)}</span>
          <span class="txn-merchant">${escapeHtml(t.merchant)}</span>
          <span class="txn-meta">${escapeHtml(t.location)} · ${formatTimestamp(t.timestamp)}</span>
        </div>
        <div class="txn-main">
          <span class="txn-amount">${formatAmount(t.amount)}</span>
          <span class="${pillClass}">${pillText}</span>
        </div>
      </div>
      ${reasonsHtml}
    </div>
  `;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ---------------- Data fetching ----------------

async function loadTransactions() {
  try {
    const res = await fetch('/api/transactions');
    if (!res.ok) throw new Error('Failed to load transactions');
    allTransactions = await res.json();
    renderTransactions();
  } catch (err) {
    txnListEl.innerHTML = `<p class="empty-msg">Could not load transactions. Is the Flask server running?</p>`;
    console.error(err);
  }
}

async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) throw new Error('Failed to load stats');
    const stats = await res.json();
    document.getElementById('statTotal').textContent = stats.total_transactions;
    document.getElementById('statFlagged').textContent = stats.flagged_transactions;
    document.getElementById('statClean').textContent = stats.clean_transactions;
    document.getElementById('statRate').textContent = stats.flag_rate + '%';
  } catch (err) {
    console.error(err);
  }
}

async function refreshAll() {
  await Promise.all([loadTransactions(), loadStats()]);
}

// ---------------- Form submission ----------------

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  formResultEl.textContent = 'Running through rule engine…';
  formResultEl.className = 'form-result';

  const payload = {
    user_id: document.getElementById('userId').value.trim(),
    amount: document.getElementById('amount').value,
    location: document.getElementById('location').value.trim(),
    merchant: document.getElementById('merchant').value.trim(),
    timestamp: document.getElementById('timestamp').value,
  };

  try {
    const res = await fetch('/api/transactions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok) {
      formResultEl.textContent = data.error || 'Something went wrong.';
      formResultEl.className = 'form-result error';
      return;
    }

    if (data.is_flagged) {
      formResultEl.textContent = `Flagged — ${data.flags.length} rule(s) triggered. See feed below.`;
      formResultEl.className = 'form-result flagged';
    } else {
      formResultEl.textContent = 'Clean — no rules triggered.';
      formResultEl.className = 'form-result ok';
    }

    form.reset();
    await refreshAll();
  } catch (err) {
    formResultEl.textContent = 'Network error — check that the server is running.';
    formResultEl.className = 'form-result error';
    console.error(err);
  }
});

// ---------------- Filters ----------------

filterBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    filterBtns.forEach(b => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    currentFilter = btn.dataset.filter;
    renderTransactions();
  });
});

// ---------------- Reset demo data ----------------

resetBtn.addEventListener('click', async () => {
  if (!confirm('This will wipe all transactions and reload the original demo data. Continue?')) return;
  resetBtn.disabled = true;
  resetBtn.textContent = 'Resetting…';
  try {
    await fetch('/api/reset', { method: 'POST' });
    await refreshAll();
  } catch (err) {
    console.error(err);
  } finally {
    resetBtn.disabled = false;
    resetBtn.textContent = 'Reset demo data';
  }
});

// ---------------- Init ----------------

refreshAll();

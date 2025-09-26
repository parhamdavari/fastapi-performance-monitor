import { debounce, formatNumber, retryWithBackoff } from './utils.js';

class EndpointsAPI {
    constructor(config = {}) {
        this.baseUrl = config.baseUrl || `${window.location.protocol}//${window.location.host}`;
    }

    async listEndpoints() {
        const response = await retryWithBackoff(async () => {
            const res = await fetch(`${this.baseUrl}/health/pulse/endpoints`, {
                headers: {
                    'Accept': 'application/json',
                    'Cache-Control': 'no-cache'
                }
            });
            if (!res.ok) {
                throw new Error(`Failed to load endpoints: HTTP ${res.status}`);
            }
            return res;
        });
        return response.json();
    }

    async startProbe(endpointIds = null) {
        const response = await fetch(`${this.baseUrl}/health/pulse/probe`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(endpointIds ? { endpoints: endpointIds } : {}),
        });

        if (!response.ok) {
            const detail = await response.json().catch(() => ({}));
            throw new Error(detail?.detail || `Failed to start probe: HTTP ${response.status}`);
        }

        return response.json();
    }

    async getProbeStatus(jobId) {
        const response = await fetch(`${this.baseUrl}/health/pulse/probe/${jobId}`, {
            headers: {
                'Accept': 'application/json',
                'Cache-Control': 'no-cache'
            }
        });
        if (!response.ok) {
            throw new Error(`Failed to fetch probe status: HTTP ${response.status}`);
        }
        return response.json();
    }
}

const STATUS_CONFIG = {
    healthy: { label: 'Healthy', className: 'status-healthy', dotClass: 'bg-pulse-green' },
    warning: { label: 'Warning', className: 'status-warning', dotClass: 'bg-pulse-amber' },
    critical: { label: 'Critical', className: 'status-critical', dotClass: 'bg-pulse-red' },
    skipped: { label: 'Skipped', className: 'status-skipped', dotClass: 'bg-purple-400' },
    unknown: { label: 'Unknown', className: 'status-unknown', dotClass: 'bg-gray-400' },
};

function statusConfig(status) {
    return STATUS_CONFIG[status] || STATUS_CONFIG.unknown;
}

function formatLatency(value) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return '--';
    }
    return `${Math.round(value)} ms`;
}

function formatErrorRate(value) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return '--';
    }
    return `${value.toFixed(2)}%`;
}

function formatRelativeTime(timestamp) {
    if (!timestamp) return 'Never';
    const delta = Date.now() - timestamp * 1000;
    if (delta < 0) return 'Just now';
    const seconds = Math.floor(delta / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

export class EndpointsDashboard {
    constructor(config = {}) {
        this.api = new EndpointsAPI(config.api || {});
        this.pollIntervalMs = config.pollIntervalMs || 1500;
        this.jobTimeoutMs = config.jobTimeoutMs || 60000;
        this.state = {
            endpoints: [],
            summary: {},
            filter: '',
            currentJobId: null,
        };
        this.pollTimer = null;
    }

    init = async () => {
        this.cacheElements();
        this.bindEvents();
        await this.refresh();
    };

    cacheElements() {
        this.tableBody = document.getElementById('endpointsTableBody');
        this.searchInput = document.getElementById('endpointSearch');
        this.statusBanner = document.getElementById('probeStatusBanner');
        this.runButton = document.getElementById('runProbeBtn');
        this.emptyState = document.getElementById('emptyState');
        this.summaryElements = {
            total: document.getElementById('summaryTotal'),
            auto: document.getElementById('summaryAuto'),
            requiresInput: document.getElementById('summaryRequiresInput'),
            lastRun: document.getElementById('summaryLastRun'),
        };
    }

    bindEvents() {
        if (this.searchInput) {
            this.searchInput.addEventListener('input', debounce((event) => {
                this.state.filter = event.target.value.trim().toLowerCase();
                this.renderTable();
            }, 150));
        }

        if (this.runButton) {
            this.runButton.addEventListener('click', () => this.handleRunProbe());
        }
    }

    async refresh() {
        const data = await this.api.listEndpoints();
        this.state.endpoints = data.endpoints || [];
        this.state.summary = data.summary || {};
        this.renderSummary();
        this.renderTable();
    }

    renderSummary() {
        const s = this.state.summary;
        this.summaryElements.total.textContent = formatNumber(s.total || 0);
        this.summaryElements.auto.textContent = formatNumber(s.auto_probed || 0);
        this.summaryElements.requiresInput.textContent = formatNumber(s.requires_input || 0);

        if (s.last_job_status && s.last_job_completed_at) {
            this.summaryElements.lastRun.textContent = `${s.last_job_status.toUpperCase()} · ${formatRelativeTime(s.last_job_completed_at)}`;
        } else {
            this.summaryElements.lastRun.textContent = '—';
        }
    }

    filteredEndpoints() {
        if (!this.state.filter) {
            return this.state.endpoints;
        }
        return this.state.endpoints.filter((endpoint) => {
            const haystack = `${endpoint.method} ${endpoint.path} ${endpoint.summary || ''}`.toLowerCase();
            return haystack.includes(this.state.filter);
        });
    }

    renderTable() {
        const endpoints = this.filteredEndpoints();

        if (!endpoints.length) {
            this.emptyState.classList.remove('hidden');
        } else {
            this.emptyState.classList.add('hidden');
        }

        const rows = endpoints.map((endpoint) => {
            const statusInfo = statusConfig(endpoint.last_probe?.status);
            const avgResponse = endpoint.metrics?.avg_response_time;
            const errorRate = endpoint.metrics?.error_rate;
            const lastChecked = endpoint.last_probe?.checked_at;

            return `
                <tr class="table-row">
                    <td class="px-4 py-3">
                        <span class="status-pill ${statusInfo.className}">
                            <span class="status-dot ${statusInfo.dotClass}"></span>
                            ${statusInfo.label}
                        </span>
                    </td>
                    <td class="px-4 py-3">
                        <div class="font-medium text-sm">${endpoint.method} ${endpoint.path}</div>
                        ${endpoint.summary ? `<div class="text-xs text-black/60 dark:text-white/50">${endpoint.summary}</div>` : ''}
                        ${endpoint.requires_input ? '<div class="text-xs text-amber-400">Requires input</div>' : ''}
                    </td>
                    <td class="px-4 py-3">${formatLatency(avgResponse)}</td>
                    <td class="px-4 py-3">${formatErrorRate(errorRate)}</td>
                    <td class="px-4 py-3">${formatRelativeTime(lastChecked)}</td>
                </tr>
            `;
        }).join('');

        this.tableBody.innerHTML = rows || '';
    }

    async handleRunProbe() {
        if (this.state.currentJobId) {
            return;
        }

        try {
            this.setProbeBanner('Starting health check…', 'info');
            this.runButton.disabled = true;
            this.runButton.classList.add('opacity-60');

            const response = await this.api.startProbe();
            this.state.currentJobId = response.job_id;
            await this.pollJob(response.job_id);
        } catch (error) {
            console.error('Failed to start probe', error);
            this.setProbeBanner(error.message || 'Failed to run health check', 'error');
        } finally {
            this.runButton.disabled = false;
            this.runButton.classList.remove('opacity-60');
            this.state.currentJobId = null;
        }
    }

    async pollJob(jobId) {
        const start = Date.now();
        while (true) {
            if (Date.now() - start > this.jobTimeoutMs) {
                this.setProbeBanner('Health check timed out. Some endpoints may still be running.', 'warning');
                break;
            }

            try {
                const status = await this.api.getProbeStatus(jobId);
                const { completed, total } = status;
                const progressText = completed >= total ? 'Finishing…' : `${completed} / ${total} endpoints checked…`;
                this.setProbeBanner(progressText, 'info');

                if (status.status === 'completed') {
                    this.setProbeBanner('Health check completed successfully.', 'success');
                    await this.refresh();
                    break;
                }
            } catch (error) {
                console.error('Probe status failed', error);
                this.setProbeBanner('Failed to track probe status. Check logs for details.', 'error');
                break;
            }

            await new Promise((resolve) => setTimeout(resolve, this.pollIntervalMs));
        }
    }

    setProbeBanner(message, state) {
        if (!this.statusBanner) return;

        this.statusBanner.textContent = message;
        this.statusBanner.classList.remove('hidden', 'text-primary', 'border-primary/30', 'text-red-500', 'border-red-500/40', 'text-yellow-400', 'border-yellow-400/30', 'text-emerald-400', 'border-emerald-400/30');

        switch (state) {
            case 'success':
                this.statusBanner.classList.add('text-emerald-400', 'border-emerald-400/30');
                break;
            case 'warning':
                this.statusBanner.classList.add('text-yellow-400', 'border-yellow-400/30');
                break;
            case 'error':
                this.statusBanner.classList.add('text-red-500', 'border-red-500/40');
                break;
            default:
                this.statusBanner.classList.add('text-primary', 'border-primary/30');
        }
    }
}

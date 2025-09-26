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
                    'Cache-Control': 'no-cache',
                },
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
                'Accept': 'application/json',
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
                'Cache-Control': 'no-cache',
            },
        });
        if (!response.ok) {
            throw new Error(`Failed to fetch probe status: HTTP ${response.status}`);
        }
        return response.json();
    }

    async savePayload(endpointId, payload) {
        const response = await fetch(`${this.baseUrl}/health/pulse/probe/${encodeURIComponent(endpointId)}/payload`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const detail = await response.json().catch(() => ({}));
            throw new Error(detail?.detail || `Failed to save payload: HTTP ${response.status}`);
        }
        return response.json();
    }

    async deletePayload(endpointId) {
        const response = await fetch(`${this.baseUrl}/health/pulse/probe/${encodeURIComponent(endpointId)}/payload`, {
            method: 'DELETE',
            headers: {
                'Accept': 'application/json',
            },
        });
        if (!response.ok) {
            const detail = await response.json().catch(() => ({}));
            throw new Error(detail?.detail || `Failed to reset payload: HTTP ${response.status}`);
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

function prettyJson(value) {
    if (value === null || value === undefined) {
        return '';
    }
    try {
        return JSON.stringify(value, null, 2);
    } catch (error) {
        return String(value);
    }
}

function parseJsonOrDefault(input, fallback) {
    const trimmed = (input || '').trim();
    if (!trimmed) return fallback;
    try {
        return JSON.parse(trimmed);
    } catch (error) {
        throw new Error('Invalid JSON data');
    }
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
        this.selectedEndpointId = null;
        this.panelSource = 'generated';
        this.hasCustomPayload = false;
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

        this.panel = document.getElementById('endpointPanel');
        this.panelBackdrop = document.getElementById('panelBackdrop');
        this.panelMethod = document.getElementById('panelEndpointMethod');
        this.panelPath = document.getElementById('panelEndpointPath');
        this.panelStatus = document.getElementById('panelStatusBadge');
        this.panelLastChecked = document.getElementById('panelLastChecked');
        this.panelMetrics = {
            avg: document.getElementById('panelMetricAvg'),
            errorRate: document.getElementById('panelMetricErrorRate'),
            totalRequests: document.getElementById('panelMetricTotal'),
        };
        this.panelMessage = document.getElementById('panelMessage');
        this.panelSourceButtons = document.querySelectorAll('[data-payload-source]');
        this.payloadEditors = {
            path: document.getElementById('payloadPathInput'),
            query: document.getElementById('payloadQueryInput'),
            headers: document.getElementById('payloadHeadersInput'),
            body: document.getElementById('payloadBodyInput'),
        };
        this.panelRunButton = document.getElementById('runSingleProbeBtn');
        this.panelSaveButton = document.getElementById('savePayloadBtn');
        this.panelSaveRunButton = document.getElementById('saveAndRunPayloadBtn');
        this.panelResetButton = document.getElementById('resetPayloadBtn');
        this.panelCloseButton = document.getElementById('closePanelBtn');
    }

    bindEvents() {
        if (this.searchInput) {
            this.searchInput.addEventListener('input', debounce((event) => {
                this.state.filter = event.target.value.trim().toLowerCase();
                this.renderTable();
            }, 150));
        }

        if (this.runButton) {
            this.runButton.addEventListener('click', () => this.handleRunAll());
        }

        if (this.tableBody) {
            this.tableBody.addEventListener('click', (event) => {
                const row = event.target.closest('tr[data-endpoint-id]');
                if (!row) return;
                const endpointId = row.dataset.endpointId;
                this.openPanel(endpointId);
            });
        }

        if (this.panelBackdrop) {
            this.panelBackdrop.addEventListener('click', () => this.closePanel());
        }

        if (this.panelCloseButton) {
            this.panelCloseButton.addEventListener('click', () => this.closePanel());
        }

        this.panelSourceButtons?.forEach((button) => {
            button.addEventListener('click', () => {
                const source = button.dataset.payloadSource;
                this.applyPayloadSource(source);
            });
        });

        this.panelSaveButton?.addEventListener('click', () => this.savePayload(false));
        this.panelSaveRunButton?.addEventListener('click', () => this.savePayload(true));
        this.panelRunButton?.addEventListener('click', () => this.runSingleProbe());
        this.panelResetButton?.addEventListener('click', () => this.resetPayload());

        window.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && this.isPanelOpen()) {
                this.closePanel();
            }
        });
    }

    async refresh() {
        const data = await this.api.listEndpoints();
        this.state.endpoints = data.endpoints || [];
        this.state.summary = data.summary || {};
        this.renderSummary();
        this.renderTable();

        if (this.selectedEndpointId) {
            const endpoint = this.state.endpoints.find((item) => item.id === this.selectedEndpointId);
            if (endpoint) {
                this.populatePanel(endpoint);
            } else {
                this.closePanel();
            }
        }
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
            const payloadSource = endpoint.payload?.source;
            const customBadge = payloadSource === 'custom'
                ? '<span class="ml-2 inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">Custom</span>'
                : '';

            return `
                <tr class="table-row cursor-pointer" data-endpoint-id="${endpoint.id}">
                    <td class="px-4 py-3">
                        <span class="status-pill ${statusInfo.className}">
                            <span class="status-dot ${statusInfo.dotClass}"></span>
                            ${statusInfo.label}
                        </span>
                    </td>
                    <td class="px-4 py-3">
                        <div class="font-medium text-sm flex items-center">${endpoint.method} ${endpoint.path}${customBadge}</div>
                        ${endpoint.summary ? `<div class="text-xs text-black/60 dark:text-white/50">${endpoint.summary}</div>` : ''}
                    </td>
                    <td class="px-4 py-3">${formatLatency(avgResponse)}</td>
                    <td class="px-4 py-3">${formatErrorRate(errorRate)}</td>
                    <td class="px-4 py-3">${formatRelativeTime(lastChecked)}</td>
                </tr>
            `;
        }).join('');

        this.tableBody.innerHTML = rows || '';
    }

    async handleRunAll() {
        if (this.state.currentJobId) {
            return;
        }
        try {
            this.setProbeBanner('Running health check…', 'info');
            this.runButton.disabled = true;
            const { job_id } = await this.api.startProbe();
            this.state.currentJobId = job_id;
            await this.pollJob(job_id);
        } catch (error) {
            console.error(error);
            this.setProbeBanner(error.message || 'Failed to start probe', 'error');
        } finally {
            this.runButton.disabled = false;
            this.state.currentJobId = null;
        }
    }

    async runSingleProbe() {
        if (!this.selectedEndpointId) return;
        try {
            this.showPanelMessage('info', 'Running probe…');
            const { job_id } = await this.api.startProbe([this.selectedEndpointId]);
            await this.pollJob(job_id, true);
        } catch (error) {
            console.error(error);
            this.showPanelMessage('error', error.message || 'Probe failed');
        }
    }

    async pollJob(jobId, silenceBanner = false) {
        const start = Date.now();
        while (true) {
            if (Date.now() - start > this.jobTimeoutMs) {
                if (!silenceBanner) {
                    this.setProbeBanner('Health check timed out.', 'warning');
                } else {
                    this.showPanelMessage('warning', 'Probe timed out.');
                }
                break;
            }

            try {
                const status = await this.api.getProbeStatus(jobId);
                const { completed, total } = status;
                const progressText = `${completed} / ${total} endpoints checked…`;
                if (!silenceBanner) {
                    this.setProbeBanner(progressText, 'info');
                } else {
                    this.showPanelMessage('info', progressText);
                }
                if (status.status === 'completed') {
                    if (!silenceBanner) {
                        this.setProbeBanner('Health check completed successfully.', 'success');
                    } else {
                        this.showPanelMessage('success', 'Probe completed successfully.');
                    }
                    await this.refresh();
                    break;
                }
            } catch (error) {
                console.error(error);
                if (!silenceBanner) {
                    this.setProbeBanner('Failed to track probe status.', 'error');
                } else {
                    this.showPanelMessage('error', 'Failed to track probe status.');
                }
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

    openPanel(endpointId) {
        const endpoint = this.state.endpoints.find((item) => item.id === endpointId);
        if (!endpoint) return;
        this.selectedEndpointId = endpointId;
        this.populatePanel(endpoint);
        this.panelBackdrop.classList.remove('hidden');
        this.panel.classList.remove('hidden');
    }

    closePanel() {
        this.selectedEndpointId = null;
        this.panelBackdrop.classList.add('hidden');
        this.panel.classList.add('hidden');
    }

    isPanelOpen() {
        return !this.panel.classList.contains('hidden');
    }

    populatePanel(endpoint) {
        this.clearPanelMessage();
        this.panelMethod.textContent = endpoint.method;
        this.panelPath.textContent = endpoint.path;

        const statusInfo = statusConfig(endpoint.last_probe?.status);
        this.panelStatus.textContent = statusInfo.label;
        this.panelStatus.className = `inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold ${statusInfo.className}`;
        this.panelLastChecked.textContent = formatRelativeTime(endpoint.last_probe?.checked_at);

        this.panelMetrics.avg.textContent = formatLatency(endpoint.metrics?.avg_response_time);
        this.panelMetrics.errorRate.textContent = formatErrorRate(endpoint.metrics?.error_rate);
        this.panelMetrics.totalRequests.textContent = formatNumber(endpoint.metrics?.total_requests || 0);

        const payload = endpoint.payload || {};
        const source = payload.source && payload.source !== 'none' ? payload.source : 'generated';
        this.panelSource = source;
        this.hasCustomPayload = Boolean(payload.custom);

        const effective = payload.effective || {};
        this.payloadEditors.path.value = prettyJson(effective.path_params ?? payload.custom?.path_params ?? payload.generated?.path_params ?? {});
        this.payloadEditors.query.value = prettyJson(effective.query ?? payload.custom?.query ?? payload.generated?.query ?? {});
        this.payloadEditors.headers.value = prettyJson(effective.headers ?? payload.custom?.headers ?? payload.generated?.headers ?? {});
        this.payloadEditors.body.value = prettyJson(effective.body ?? payload.custom?.body ?? payload.generated?.body ?? null);

        this.updatePayloadEditorsState();
        this.updateSourceButtons();
    }

    applyPayloadSource(source) {
        this.panelSource = source === 'custom' ? 'custom' : 'generated';
        this.updatePayloadEditorsState();
        this.updateSourceButtons();
    }

    updatePayloadEditorsState() {
        const isCustom = this.panelSource === 'custom';
        Object.values(this.payloadEditors).forEach((editor) => {
            if (editor) {
                editor.readOnly = !isCustom;
                editor.classList.toggle('opacity-60', !isCustom);
            }
        });
        if (this.panelSaveButton) {
            this.panelSaveButton.disabled = !isCustom;
        }
        if (this.panelSaveRunButton) {
            this.panelSaveRunButton.disabled = !isCustom;
        }
        if (this.panelResetButton) {
            this.panelResetButton.classList.toggle('hidden', !this.hasCustomPayload);
            this.panelResetButton.disabled = !this.hasCustomPayload;
        }
    }

    updateSourceButtons() {
        this.panelSourceButtons.forEach((button) => {
            const isActive = button.dataset.payloadSource === this.panelSource;
            button.classList.toggle('bg-primary', isActive);
            button.classList.toggle('text-white', isActive);
            button.classList.toggle('bg-white/10', !isActive);
            button.classList.toggle('text-white/70', !isActive);
        });
    }

    async savePayload(runAfterSave = false) {
        if (!this.selectedEndpointId) return;
        if (this.panelSource !== 'custom') {
            this.showPanelMessage('info', 'Custom mode is disabled. Switch to custom to edit payload.');
            return;
        }
        try {
            const payload = {
                path_params: parseJsonOrDefault(this.payloadEditors.path.value, {}),
                query: parseJsonOrDefault(this.payloadEditors.query.value, {}),
                headers: parseJsonOrDefault(this.payloadEditors.headers.value, {}),
                body: parseJsonOrDefault(this.payloadEditors.body.value, null),
            };
            await this.api.savePayload(this.selectedEndpointId, payload);
            this.showPanelMessage('success', 'Payload saved successfully.');
            await this.refresh();
            if (runAfterSave) {
                await this.runSingleProbe();
            }
        } catch (error) {
            console.error(error);
            this.showPanelMessage('error', error.message || 'Failed to save payload');
        }
    }

    async resetPayload() {
        if (!this.selectedEndpointId) return;
        try {
            await this.api.deletePayload(this.selectedEndpointId);
            this.panelSource = 'generated';
            this.showPanelMessage('success', 'Reverted to generated payload.');
            await this.refresh();
        } catch (error) {
            console.error(error);
            this.showPanelMessage('error', error.message || 'Failed to reset payload');
        }
    }

    showPanelMessage(level, message) {
        if (!this.panelMessage) return;
        this.panelMessage.textContent = message;
        this.panelMessage.classList.remove('hidden', 'text-emerald-400', 'text-red-400', 'text-primary', 'text-yellow-400');
        switch (level) {
            case 'success':
                this.panelMessage.classList.add('text-emerald-400');
                break;
            case 'error':
                this.panelMessage.classList.add('text-red-400');
                break;
            case 'warning':
                this.panelMessage.classList.add('text-yellow-400');
                break;
            default:
                this.panelMessage.classList.add('text-primary');
        }
    }

    clearPanelMessage() {
        if (this.panelMessage) {
            this.panelMessage.classList.add('hidden');
            this.panelMessage.textContent = '';
        }
    }
}

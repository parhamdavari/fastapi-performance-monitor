/**
 * Component-based system for the performance dashboard
 */

import { 
    escapeHtml, 
    safeSetText, 
    createElement, 
    formatNumber, 
    calculatePerformanceGrade,
    getStatusClass 
} from './utils.js';

/**
 * Base component class
 */
export class Component {
    constructor(container) {
        this.container = container;
        this.element = null;
        this.data = {};
    }

    render() {
        throw new Error('render() must be implemented by subclasses');
    }

    update(newData) {
        this.data = { ...this.data, ...newData };
        this.render();
    }

    destroy() {
        if (this.element && this.element.parentNode) {
            this.element.parentNode.removeChild(this.element);
        }
    }
}

/**
 * Metric Card Component
 */
export class MetricCard extends Component {
    constructor(container, data) {
        super(container);
        this.data = data;
        this.render();
    }

    render() {
        if (!this.element) {
            this.element = createElement('div', {
                className: 'metric-card',
                role: 'article',
                'aria-label': `${this.data.title} metric`
            });
            this.container.appendChild(this.element);
        }

        // Create or update structure
        this.element.innerHTML = '';
        
        const title = createElement('h3', {}, this.data.title);
        const valueEl = createElement('div', {
            className: 'metric-value',
            style: `color: ${this.data.color || '#667eea'}`,
            'aria-label': `${this.data.title} value: ${this.data.value}`
        }, this.data.value);
        const label = createElement('div', {
            className: 'metric-label'
        }, this.data.label);

        this.element.appendChild(title);
        this.element.appendChild(valueEl);
        this.element.appendChild(label);
    }

    update(newData) {
        this.data = { ...this.data, ...newData };
        
        // Update only the value if structure exists
        const valueEl = this.element?.querySelector('.metric-value');
        if (valueEl) {
            safeSetText(valueEl, this.data.value);
            valueEl.style.color = this.data.color || '#667eea';
            valueEl.setAttribute('aria-label', `${this.data.title} value: ${this.data.value}`);
        } else {
            this.render();
        }
    }
}

/**
 * SLA Status Component
 */
export class SLAStatus extends Component {
    constructor(container, data) {
        super(container);
        this.data = data;
        this.render();
    }

    render() {
        if (!this.element) {
            this.element = createElement('div', {
                className: 'sla-grid',
                role: 'region',
                'aria-label': 'SLA Compliance Status'
            });
            this.container.appendChild(this.element);
        }

        this.element.innerHTML = '';

        const slaItems = [
            {
                label: 'Latency SLA',
                target: 'P95 < 200ms',
                status: this.data.latency_sla_met
            },
            {
                label: 'Error Rate SLA',
                target: '< 5% errors',
                status: this.data.error_rate_sla_met
            },
            {
                label: 'Overall SLA',
                target: 'All targets met',
                status: this.data.overall_sla_met
            }
        ];

        slaItems.forEach(item => {
            const slaItem = this.createSLAItem(item);
            this.element.appendChild(slaItem);
        });
    }

    createSLAItem(item) {
        let statusClass, statusIcon, statusText;

        if (item.status === true) {
            statusClass = 'sla-pass';
            statusIcon = '✅';
            statusText = 'PASS';
        } else if (item.status === false) {
            statusClass = 'sla-fail';
            statusIcon = '❌';
            statusText = 'FAIL';
        } else {
            statusClass = 'sla-pending';
            statusIcon = '⏳';
            statusText = 'Collecting...';
        }

        const container = createElement('div', {
            className: `sla-item ${statusClass}`,
            role: 'status',
            'aria-label': `${item.label}: ${statusText}`
        });

        const indicator = createElement('div', {
            className: `status-indicator ${getStatusClass(item.status)}`,
            'aria-hidden': 'true'
        });

        const label = createElement('strong', {}, item.label);
        const target = createElement('small', {}, item.target);
        const status = createElement('div', {
            className: 'status-text'
        }, `${statusIcon} ${statusText}`);

        container.appendChild(indicator);
        container.appendChild(label);
        container.appendChild(createElement('br'));
        container.appendChild(target);
        container.appendChild(createElement('br'));
        container.appendChild(status);

        return container;
    }

    update(newData) {
        this.data = { ...this.data, ...newData };
        this.render(); // Full re-render for SLA changes
    }
}

/**
 * Endpoints Table Component
 */
export class EndpointsTable extends Component {
    constructor(container, data) {
        super(container);
        this.data = data;
        this.render();
    }

    render() {
        if (!this.element) {
            this.element = createElement('div', {
                className: 'endpoints-table'
            });
            this.container.appendChild(this.element);
        }

        this.element.innerHTML = '';

        const title = createElement('h2', {
            style: 'padding: 1.5rem 1.5rem 0;'
        }, '🎯 Endpoint Performance');

        const table = createElement('table', {
            role: 'table',
            'aria-label': 'Endpoint performance metrics'
        });

        const thead = this.createTableHeader();
        const tbody = this.createTableBody();

        table.appendChild(thead);
        table.appendChild(tbody);

        this.element.appendChild(title);
        this.element.appendChild(table);
    }

    createTableHeader() {
        const thead = createElement('thead');
        const tr = createElement('tr');

        const headers = [
            'Endpoint',
            'Requests', 
            'Success Rate',
            'Avg Response',
            'P95 Response',
            'Grade',
            'SLA'
        ];

        headers.forEach(header => {
            const th = createElement('th', {
                scope: 'col'
            }, header);
            tr.appendChild(th);
        });

        thead.appendChild(tr);
        return thead;
    }

    createTableBody() {
        const tbody = createElement('tbody', {
            id: 'endpointsTableBody'
        });

        // Convert endpoints object to array and sort by total requests
        const endpointArray = Object.entries(this.data).map(([endpoint, metrics]) => ({
            endpoint,
            ...metrics
        })).sort((a, b) => b.total_requests - a.total_requests);

        endpointArray.forEach(endpoint => {
            const tr = this.createEndpointRow(endpoint);
            tbody.appendChild(tr);
        });

        return tbody;
    }

    createEndpointRow(endpoint) {
        const tr = createElement('tr');

        const successRate = endpoint.total_requests > 0 
            ? (endpoint.success_count / endpoint.total_requests * 100).toFixed(1)
            : 0;

        const grade = calculatePerformanceGrade(endpoint.p95_response_time, successRate);
        const slaCompliant = endpoint.p95_response_time <= 200;

        const cells = [
            createElement('td', {}, createElement('code', {}, endpoint.endpoint)),
            createElement('td', {}, formatNumber(endpoint.total_requests)),
            createElement('td', {}, `${successRate}%`),
            createElement('td', {}, `${formatNumber(endpoint.avg_response_time, 0)}ms`),
            createElement('td', {}, `${formatNumber(endpoint.p95_response_time, 0)}ms`),
            createElement('td', {}, createElement('span', {
                className: `grade-badge grade-${grade}`
            }, grade)),
            createElement('td', {}, slaCompliant ? '✅' : '❌')
        ];

        cells.forEach(cell => tr.appendChild(cell));
        return tr;
    }

    update(newData) {
        this.data = { ...newData };
        
        // Update table body only
        const tbody = this.element?.querySelector('tbody');
        if (tbody) {
            tbody.innerHTML = '';
            const newTbody = this.createTableBody();
            newTbody.querySelectorAll('tr').forEach(tr => {
                tbody.appendChild(tr);
            });
        } else {
            this.render();
        }
    }
}

/**
 * Error Message Component
 */
export class ErrorMessage extends Component {
    constructor(container) {
        super(container);
        this.render();
    }

    render() {
        if (!this.element) {
            this.element = createElement('div', {
                id: 'errorMessage',
                className: 'error-message',
                style: 'display: none;',
                role: 'alert',
                'aria-live': 'polite'
            });
            this.container.appendChild(this.element);
        }
    }

    show(message) {
        if (this.element) {
            safeSetText(this.element, message);
            this.element.style.display = 'block';
            this.element.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    hide() {
        if (this.element) {
            this.element.style.display = 'none';
        }
    }
}

/**
 * Loading Indicator Component
 */
export class LoadingIndicator extends Component {
    constructor() {
        super(document.body);
    }

    show() {
        document.body.classList.add('loading');
    }

    hide() {
        document.body.classList.remove('loading');
    }
}
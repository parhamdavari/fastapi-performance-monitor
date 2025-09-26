/**
 * Main Dashboard Controller
 */

import { MetricsAPI, ConnectivityMonitor } from './api.js';
import { ChartManager } from './charts.js';
import {
    MetricCard,
    SLAStatus,
    EndpointsTable,
    ErrorMessage,
    LoadingIndicator,
} from './components.js';
import { formatNumber, debounce, escapeHtml } from './utils.js';

/**
 * Performance Dashboard Controller
 */
export class PerformanceDashboard {
    constructor(config = {}) {
        this.config = {
            refreshInterval: config.refreshInterval || 30000,
            maxRetries: config.maxRetries || 3,
            enableAutoRefresh: config.enableAutoRefresh !== false,
            chartConfig: config.chartConfig || {},
            healthThresholds: config.healthThresholds || {
                excellent: 95,
                good: 80,
                fair: 60
            },
            ...config
        };

        // Core services
        this.api = new MetricsAPI({
            timeout: 10000,
            maxRetries: this.config.maxRetries
        });
        
        // Components
        this.components = {};
        this.chartManager = null;
        this.connectivityMonitor = null;
        
        // State
        this.autoRefreshInterval = null;
        this.isDestroyed = false;
        this.lastUpdateTime = null;
        this.previousMetrics = null;
        this.lastRateSnapshot = null;
        this.currentRequestRate = 0;
        
        // Bind methods
        this.handleRefreshClick = this.handleRefreshClick.bind(this);
        this.handleAutoRefreshToggle = this.handleAutoRefreshToggle.bind(this);
        this.handleConnectivityChange = this.handleConnectivityChange.bind(this);
        this.handleVisibilityChange = this.handleVisibilityChange.bind(this);
        this.debouncedRefresh = debounce(this.refreshMetrics.bind(this), 1000);
        this.refreshData = this.refreshMetrics.bind(this);
    }

    /**
     * Initialize the dashboard
     */
    async init() {
        try {
            this.setupEventListeners();
            this.initializeComponents();
            await this.initializeChart();
            
            // Initial data load
            await this.refreshMetrics();
            
            // Setup auto-refresh and connectivity monitoring
            this.setupAutoRefresh();
            this.setupConnectivityMonitoring();
            
            console.log('Performance Dashboard initialized successfully');
        } catch (error) {
            console.error('Failed to initialize dashboard:', error);
            this.components.errorMessage?.show('Failed to initialize dashboard. Please refresh the page.');
        }
    }

    /**
     * Setup global event listeners
     */
    setupEventListeners() {
        // Refresh button
        const refreshButton = document.querySelector('.refresh-button');
        if (refreshButton) {
            refreshButton.addEventListener('click', this.handleRefreshClick);
        }

        // Auto-refresh toggle
        const autoRefreshCheckbox = document.getElementById('autoRefresh');
        if (autoRefreshCheckbox) {
            autoRefreshCheckbox.addEventListener('change', this.handleAutoRefreshToggle);
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'r' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                this.debouncedRefresh();
            }
        });

        // Page visibility changes
        document.addEventListener('visibilitychange', this.handleVisibilityChange);

        // Error handling
        window.addEventListener('error', (event) => {
            console.error('Dashboard error:', event.error);
            this.components.errorMessage?.show('An unexpected error occurred. Some features may not work properly.');
        });

        window.addEventListener('unhandledrejection', (event) => {
            console.error('Unhandled promise rejection:', event.reason);
            this.components.errorMessage?.show('A network error occurred. Retrying...');
        });
    }

    /**
     * Initialize UI components
     */
    initializeComponents() {
        // Error message component
        const errorContainer = document.getElementById('errorContainer');
        this.components.errorMessage = new ErrorMessage(errorContainer);

        // Loading indicator
        this.components.loadingIndicator = new LoadingIndicator();


        // Initialize empty components that will be populated on data load
        this.components.metricCards = [];
        this.components.slaStatus = null;
        this.components.endpointsTable = null;
    }

    /**
     * Initialize chart component
     */
    async initializeChart() {
        const chartContainer = document.getElementById('chartContainer');
        if (chartContainer) {
            this.chartManager = new ChartManager(chartContainer, {
                ...this.config.chartConfig,
                maxDataPoints: 20,
                updateAnimation: false
            });
            
            await this.chartManager.init();
        }
    }

    /**
     * Setup auto-refresh functionality
     */
    setupAutoRefresh() {
        if (!this.config.enableAutoRefresh) {
            this.stopAutoRefresh();
            return;
        }

        const checkbox = document.getElementById('autoRefresh');

        if (checkbox) {
            if (checkbox.checked) {
                this.startAutoRefresh();
            } else {
                this.stopAutoRefresh();
            }
        } else {
            // No toggle in the DOM – default to enabled auto-refresh
            this.startAutoRefresh();
        }
    }

    /**
     * Setup connectivity monitoring
     */
    setupConnectivityMonitoring() {
        this.connectivityMonitor = new ConnectivityMonitor(
            this.api,
            this.handleConnectivityChange
        );
        this.connectivityMonitor.startMonitoring();
    }

    /**
     * Start auto-refresh timer
     */
    startAutoRefresh() {
        this.stopAutoRefresh();
        this.autoRefreshInterval = setInterval(() => {
            if (!document.hidden) {
                this.refreshMetrics().catch(error => {
                    console.warn('Auto-refresh failed:', error);
                });
            }
        }, this.config.refreshInterval);
    }

    /**
     * Stop auto-refresh timer
     */
    stopAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
    }

    /**
     * Refresh metrics from API
     */
    async refreshMetrics() {
        if (this.isDestroyed) return;

        try {
            this.components.loadingIndicator.show();
            this.components.errorMessage.hide();

            const data = await this.api.fetchMetrics();
            
            this.updateDashboard(data);
            this.updateLastRefreshedTime();
            this.lastUpdateTime = Date.now();
            
        } catch (error) {
            console.error('Error fetching metrics:', error);
            this.components.errorMessage.show(`Failed to fetch metrics: ${error.message}`);
        } finally {
            this.components.loadingIndicator.hide();
        }
    }

    /**
     * Update all dashboard components with new data
     */
    updateDashboard(data) {
        try {
            // Store complete metrics data for SLA calculations
            this.lastMetricsData = data.performance_metrics;

            this.updateHealthMetrics(data.performance_metrics.summary);
            this.updateDiagnostics(data);
            this.updateEndpointsList(
                data.performance_metrics.endpoint_metrics,
                data.performance_metrics.status_codes
            );
            this.previousMetrics = data.performance_metrics.summary;
        } catch (error) {
            console.error('Error updating dashboard:', error);
            this.components.errorMessage?.show('Error updating dashboard display.');
        }
    }

    /**
     * Update health-themed metrics cards
     */
    updateHealthMetrics(summary) {
        // Calculate request rate (pulse rate)
        const requestRate = this.calculateRequestRate(summary);
        this.updatePulseRate(requestRate);

        // Update response time with trend
        this.updateResponseTime(summary.avg_response_time || 0);

        // Calculate and update health score
        const healthData = this.calculateHealthScore(summary);
        this.updateHealthScore(healthData.score, healthData.status);
    }

    /**
     * Update metrics cards
     */
    updateMetricsCards(summary) {
        const container = document.getElementById('metricsGrid');
        if (!container) return;

        const errorRate = summary.error_rate || 0;
        const avgResponseTime = summary.avg_response_time || 0;
        const p95ResponseTime = summary.p95_response_time || 0;
        const totalRequests = summary.total_requests || 0;

        const metricsData = [
            {
                title: 'Total Requests',
                value: formatNumber(totalRequests),
                label: 'All time requests',
                color: '#667eea'
            },
            {
                title: 'Error Rate',
                value: `${errorRate.toFixed(2)}%`,
                label: 'Target: < 5%',
                color: errorRate > 5 ? '#f56565' : '#48bb78'
            },
            {
                title: 'Avg Response Time',
                value: `${formatNumber(avgResponseTime, 0)}ms`,
                label: 'Mean response time',
                color: '#ed8936'
            },
            {
                title: 'P95 Response Time',
                value: `${formatNumber(p95ResponseTime, 0)}ms`,
                label: 'Target: < 200ms',
                color: p95ResponseTime > 200 ? '#f56565' : '#48bb78'
            }
        ];

        // Create or update metric cards
        if (this.components.metricCards.length === 0) {
            // Initial creation
            container.innerHTML = '';
            metricsData.forEach(data => {
                const card = new MetricCard(container, data);
                this.components.metricCards.push(card);
            });
        } else {
            // Update existing cards
            metricsData.forEach((data, index) => {
                if (this.components.metricCards[index]) {
                    this.components.metricCards[index].update(data);
                }
            });
        }
    }

    /**
     * Calculate request rate for pulse display
     */
    calculateRequestRate(summary) {
        if (!summary || typeof summary !== 'object') {
            this.currentRequestRate = 0;
            this.lastRateSnapshot = null;
            return 0;
        }

        const totalRequests = typeof summary.total_requests === 'number'
            ? summary.total_requests
            : 0;

        const now = Date.now();

        if (!this.lastRateSnapshot) {
            this.lastRateSnapshot = {
                totalRequests,
                time: now
            };

            const initialRate = typeof summary.requests_per_minute === 'number'
                ? summary.requests_per_minute
                : 0;

            this.currentRequestRate = Math.max(0, Math.round(initialRate));
            return this.currentRequestRate;
        }

        const deltaRequests = totalRequests - this.lastRateSnapshot.totalRequests;
        const deltaTimeMs = now - this.lastRateSnapshot.time;

        this.lastRateSnapshot = {
            totalRequests,
            time: now
        };

        if (deltaRequests <= 0 || deltaTimeMs <= 0) {
            this.currentRequestRate = 0;
            return 0;
        }

        const ratePerMinute = (deltaRequests / (deltaTimeMs / 1000)) * 60;
        if (!Number.isFinite(ratePerMinute)) {
            this.currentRequestRate = 0;
            return 0;
        }

        this.currentRequestRate = Math.max(0, Math.round(ratePerMinute));
        return this.currentRequestRate;
    }

    /**
     * Update pulse rate display
     */
    updatePulseRate(rate) {
        const pulseElement = document.getElementById('pulseRate');
        if (pulseElement) {
            const safeRate = Number.isFinite(rate) ? rate : 0;
            pulseElement.textContent = formatNumber(safeRate);

            // Apply health-specific animations based on rate
            pulseElement.classList.remove('animate-pulse', 'animate-pulse-healthy', 'animate-pulse-warning', 'animate-pulse-critical');

            if (safeRate < 30) {
                pulseElement.classList.add('animate-pulse-critical');
            } else if (safeRate < 60) {
                pulseElement.classList.add('animate-pulse-warning');
            } else {
                pulseElement.classList.add('animate-pulse-healthy');
            }
        }
    }

    /**
     * Update response time with trend
     */
    updateResponseTime(currentTime) {
        const responseTimeElement = document.getElementById('responseTime');
        const trendIconElement = document.getElementById('trendIcon');
        const trendTextElement = document.getElementById('trendText');

        if (responseTimeElement) {
            responseTimeElement.innerHTML = `${Math.round(currentTime)} <span class="text-lg font-medium text-black/50 dark:text-white/50">ms</span>`;
        }

        // Calculate trend if we have previous data
        if (this.previousMetrics && trendIconElement && trendTextElement) {
            const previousTime = this.previousMetrics.avg_response_time || currentTime;
            const percentChange = ((currentTime - previousTime) / previousTime) * 100;

            if (Math.abs(percentChange) < 1) {
                trendTextElement.textContent = 'Stable';
                trendIconElement.innerHTML = '<path d="M5 12h14" stroke-linecap="round" stroke-linejoin="round"></path>';
            } else if (percentChange < 0) {
                trendTextElement.textContent = 'Slightly faster';
                trendIconElement.innerHTML = '<path d="M4.5 19.5l15-15m0 0H8.25m11.25 0v11.25" stroke-linecap="round" stroke-linejoin="round"></path>';
            } else {
                trendTextElement.textContent = 'Slightly slower';
                trendIconElement.innerHTML = '<path d="M19.5 4.5l-15 15m0 0h11.25m-11.25 0v-11.25" stroke-linecap="round" stroke-linejoin="round"></path>';
                trendIconElement.classList.add('text-red-500');
            }
        }
    }

    /**
     * Calculate health score based on metrics
     */
    calculateHealthScore(summary) {
        const errorRate = summary.error_rate || 0;
        const avgResponseTime = summary.avg_response_time || 0;
        const totalRequests = typeof summary.window_request_count === 'number'
            ? summary.window_request_count
            : (summary.total_requests || 0);

        let score = 100;

        // Penalize high error rates (50% weight)
        if (errorRate > 0) {
            score -= errorRate * 10; // 1% error = -10 points
        }

        // Penalize slow response times (30% weight)
        if (avgResponseTime > 50) {
            score -= (avgResponseTime - 50) / 10; // Every 10ms over 50ms = -1 point
        }

        // Penalize very low request volume (20% weight)
        if (totalRequests < 10) {
            score -= (10 - totalRequests) * 2; // Low activity penalty
        }

        // Ensure score is between 0-100
        score = Math.max(0, Math.min(100, Math.round(score)));

        // Determine status based on score
        let status;
        if (score >= this.config.healthThresholds.excellent) {
            status = 'Healthy';
        } else if (score >= this.config.healthThresholds.good) {
            status = 'Warning';
        } else {
            status = 'Critical';
        }

        return { score, status };
    }

    /**
     * Update health score display
     */
    updateHealthScore(score, status) {
        const scoreElement = document.getElementById('healthScore');
        const statusElement = document.getElementById('healthStatus');
        const barElement = document.getElementById('healthBar');

        if (scoreElement) {
            scoreElement.textContent = score;
        }

        if (statusElement) {
            statusElement.textContent = status;
            // Update status color to match v2 design
            statusElement.className = `inline-flex items-center px-3 py-1 rounded-full text-sm font-bold ${
                score >= this.config.healthThresholds.excellent ? 'bg-pulse-green/20 text-pulse-green' :
                score >= this.config.healthThresholds.good ? 'bg-pulse-amber/20 text-pulse-amber' :
                'bg-pulse-red/20 text-pulse-red'
            }`;
        }

        if (barElement) {
            barElement.style.width = `${score}%`;
            // Update bar color to match health status
            barElement.className = `h-2.5 rounded-full transition-all-smooth ${
                score >= this.config.healthThresholds.excellent ? 'bg-pulse-green' :
                score >= this.config.healthThresholds.good ? 'bg-pulse-amber' :
                'bg-pulse-red'
            }`;
        }
    }

    /**
     * Update diagnostics section
     */
    updateDiagnostics(data) {
        this.updateChart(data.performance_metrics.summary);
        this.updateErrorChart(data.performance_metrics);
        this.updatePercentiles(data.performance_metrics.summary);
        this.updateSLACompliance(data.sla_compliance);
    }

    /**
     * Update error distribution chart
     */
    updateErrorChart(performanceMetrics) {
        const chartContainer = document.getElementById('errorChart');
        const summaryElement = document.getElementById('errorSummary');
        if (!chartContainer) return;

        chartContainer.innerHTML = '';

        const statusCodesByEndpoint = performanceMetrics.status_codes || {};
        const aggregated = {};

        Object.values(statusCodesByEndpoint).forEach(endpointCodes => {
            if (!endpointCodes) return;

            Object.entries(endpointCodes).forEach(([statusCode, count]) => {
                const numericCode = Number(statusCode);
                const numericCount = Number(count) || 0;

                if (!Number.isFinite(numericCode) || numericCode < 400) {
                    return;
                }

                aggregated[numericCode] = (aggregated[numericCode] || 0) + numericCount;
            });
        });

        const sortedEntries = Object.entries(aggregated)
            .map(([code, count]) => [Number(code), Number(count) || 0])
            .filter(([, count]) => count > 0)
            .sort((a, b) => b[1] - a[1] || a[0] - b[0])
            .slice(0, 5);

        const totalErrors = Object.values(aggregated).reduce((acc, count) => acc + count, 0);

        if (sortedEntries.length === 0) {
            chartContainer.innerHTML = `
                <div class="col-span-5 flex items-center justify-center h-full text-black/50 dark:text-white/50 text-sm">
                    No errors detected
                </div>
            `;
            chartContainer.style.gridTemplateColumns = '';
            if (summaryElement) {
                summaryElement.textContent = 'No errors recorded in the current window.';
            }
            return;
        }

        if (summaryElement) {
            const distinctStatuses = sortedEntries.length;
            summaryElement.textContent = `${formatNumber(totalErrors)} error${totalErrors === 1 ? '' : 's'} across ${distinctStatuses} status code${distinctStatuses === 1 ? '' : 's'} (top 5 shown).`;
        }

        chartContainer.style.gridTemplateColumns = `repeat(${Math.max(3, sortedEntries.length)}, minmax(0, 1fr))`;

        const maxCount = sortedEntries[0][1];

        sortedEntries.forEach(([code, count]) => {
            const barHeight = maxCount > 0 ? Math.max(8, (count / maxCount) * 100) : 8;

            const barDiv = document.createElement('div');
            barDiv.className = 'flex flex-col items-center gap-1 text-center';
            barDiv.innerHTML = `
                <div class="w-full bg-primary/20 dark:bg-primary/30 rounded-t-lg transition-all-smooth" style="height: ${barHeight}%"></div>
                <span class="text-xs text-black/50 dark:text-white/50">${code}</span>
                <span class="text-xs text-black/30 dark:text-white/30">${formatNumber(count)}</span>
            `;
            chartContainer.appendChild(barDiv);
        });
    }

    /**
     * Update response percentiles
     */
    updatePercentiles(summary) {
        const percentilesContainer = document.getElementById('percentiles');
        if (!percentilesContainer) return;

        const percentiles = [
            { label: 'P50', value: summary.p50_response_time },
            { label: 'P95', value: summary.p95_response_time },
            { label: 'P99', value: summary.p99_response_time }
        ];

        const hasData = percentiles.some(p => typeof p.value === 'number' && Number.isFinite(p.value));

        if (!hasData) {
            percentilesContainer.innerHTML = `
                <div class="text-sm text-black/50 dark:text-white/50">
                    Not enough samples to calculate percentiles yet.
                </div>
            `;
            return;
        }

        percentilesContainer.innerHTML = percentiles.map(p => {
            const display = typeof p.value === 'number' && Number.isFinite(p.value)
                ? `${Math.round(p.value)} ms`
                : '—';

            return `
                <div class="flex justify-between">
                    <span class="text-black/50 dark:text-white/50">${p.label}</span>
                    <span class="font-semibold text-black dark:text-white">${display}</span>
                </div>
            `;
        }).join('');
    }

    /**
     * Update SLA compliance
     */
    updateSLACompliance(slaCompliance) {
        const percentElement = document.getElementById('slaPercent');
        const barElement = document.getElementById('slaBar');

        // Calculate SLA compliance based on available data
        let percentage;
        if (slaCompliance && slaCompliance.overall_compliance !== undefined) {
            // Handle percentage value (0-1 range)
            percentage = slaCompliance.overall_compliance * 100;
        } else if (slaCompliance && slaCompliance.overall_sla_met !== undefined) {
            // Handle boolean SLA compliance - calculate percentage based on individual SLA checks
            let slaMetCount = 0;
            let totalSLAs = 0;

            if (slaCompliance.latency_sla_met !== undefined) {
                totalSLAs++;
                if (slaCompliance.latency_sla_met) slaMetCount++;
            }

            if (slaCompliance.error_rate_sla_met !== undefined) {
                totalSLAs++;
                if (slaCompliance.error_rate_sla_met) slaMetCount++;
            }

            percentage = totalSLAs > 0 ? (slaMetCount / totalSLAs) * 100 : 0;
        } else {
            // Calculate SLA based on successful requests if no SLA data available
            percentage = this.calculateSLAFromMetrics();
        }

        percentage = Number(percentage);
        if (!Number.isFinite(percentage)) {
            percentage = this.calculateSLAFromMetrics();
        }

        // Ensure percentage is within valid range
        percentage = Number.isFinite(percentage)
            ? Math.max(0, Math.min(100, percentage))
            : 0;

        if (percentElement) {
            percentElement.textContent = `${percentage.toFixed(1)}%`;
        }

        if (barElement) {
            barElement.style.width = `${percentage}%`;
        }
    }

    /**
     * Calculate SLA compliance from current metrics when direct SLA data unavailable
     */
    calculateSLAFromMetrics() {
        // If we have current metrics, calculate SLA based on success rate
        if (this.lastMetricsData && this.lastMetricsData.summary) {
            const summary = this.lastMetricsData.summary;
            const successRate = typeof summary.success_rate === 'number'
                ? summary.success_rate
                : (typeof summary.error_rate === 'number'
                    ? 100 - summary.error_rate
                    : null);

            if (successRate !== null && Number.isFinite(successRate)) {
                return Math.max(0, Math.min(100, successRate));
            }

            const totalRequests = summary.total_requests || 0;
            const totalErrors = summary.total_errors || 0;

            if (totalRequests > 0) {
                const computedRate = ((totalRequests - totalErrors) / totalRequests) * 100;
                if (Number.isFinite(computedRate)) {
                    return Math.max(0, Math.min(100, computedRate));
                }
            }
        }

        // Default to 0% if no data available (don't use fake 99.8%)
        return 0;
    }

    /**
     * Update endpoints lists
     */
    updateEndpointsList(endpointMetrics, statusCodes = {}) {
        this.updateTopPerformers(endpointMetrics, statusCodes);
        this.updateNeedsAttention(endpointMetrics, statusCodes);
    }

    /**
     * Update top performers list
     */
    updateTopPerformers(endpointMetrics, statusCodes = {}) {
        const container = document.getElementById('topPerformers');
        if (!container || !endpointMetrics) return;

        // Sort by response time (ascending) and take top 3
        const topPerformers = Object.entries(endpointMetrics)
            .map(([endpoint, metrics]) => ({
                endpoint,
                avgTime: metrics.avg_response_time || 0,
                totalRequests: metrics.total_requests || 0,
                successCount: metrics.success_count ?? Math.max(0, (metrics.total_requests || 0) - (metrics.error_count || 0)),
                errorCount: metrics.error_count || 0,
                statusBreakdown: statusCodes[endpoint] || null
            }))
            .sort((a, b) => a.avgTime - b.avgTime)
            .slice(0, 3);

        container.innerHTML = topPerformers.map((item, index) => `
            <a class="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-primary/10 dark:hover:bg-primary/20" href="#">
                <span class="flex-shrink-0 w-2 h-2 rounded-full bg-green-500 ${index === 0 ? 'relative flex items-center justify-center' : ''}">
                    ${index === 0 ? '<span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>' : ''}
                </span>
                <div class="flex flex-col flex-1 min-w-0">
                    <span class="text-sm font-medium text-black dark:text-white truncate">${item.endpoint}</span>
                    <span class="text-xs text-black/50 dark:text-white/50">${formatNumber(item.totalRequests)} requests · avg ${Math.round(item.avgTime)} ms</span>
                    ${this.renderStatusBadges(item.successCount, item.errorCount, item.statusBreakdown)}
                </div>
            </a>
        `).join('');
    }

    /**
     * Update needs attention list
     */
    updateNeedsAttention(endpointMetrics, statusCodes = {}) {
        const container = document.getElementById('needsAttention');
        if (!container || !endpointMetrics) return;

        // Sort by response time (descending) and take bottom 3
        const needsAttention = Object.entries(endpointMetrics)
            .map(([endpoint, metrics]) => ({
                endpoint,
                avgTime: metrics.avg_response_time || 0,
                totalRequests: metrics.total_requests || 0,
                successCount: metrics.success_count ?? Math.max(0, (metrics.total_requests || 0) - (metrics.error_count || 0)),
                errorCount: metrics.error_count || 0,
                statusBreakdown: statusCodes[endpoint] || null
            }))
            .sort((a, b) => b.avgTime - a.avgTime)
            .slice(0, 3);

        container.innerHTML = needsAttention.map((item, index) => {
            const isVerySlow = item.avgTime > 1000;

            return `
                <a class="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-${isVerySlow ? 'red' : 'amber'}-500/10 dark:hover:bg-${isVerySlow ? 'red' : 'amber'}-500/20" href="#">
                    <span class="flex-shrink-0 w-2 h-2 rounded-full bg-${isVerySlow ? 'red' : 'amber'}-500 ${isVerySlow ? 'relative flex items-center justify-center' : ''}">
                        ${isVerySlow ? '<span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75 [animation-duration:0.8s]"></span>' : ''}
                    </span>
                    <div class="flex flex-col flex-1 min-w-0">
                        <span class="text-sm font-medium text-black dark:text-white truncate">${item.endpoint}</span>
                        <span class="text-xs ${isVerySlow ? 'text-red-500 dark:text-red-400' : 'text-black/50 dark:text-white/50'}">${formatNumber(item.totalRequests)} requests · avg ${Math.round(item.avgTime)} ms</span>
                        ${this.renderStatusBadges(item.successCount, item.errorCount, item.statusBreakdown, true)}
                    </div>
                </a>
            `;
        }).join('');
    }

    renderStatusBadges(successCount = 0, errorCount = 0, statusBreakdown = null, emphasizeErrors = false) {
        const hasTraffic = (successCount + errorCount) > 0;
        const title = this.buildStatusTooltip(successCount, errorCount, statusBreakdown);

        const successBadge = successCount > 0
            ? `<span class="inline-flex items-center gap-1 rounded-full bg-green-500/10 px-2 py-0.5 text-green-600 dark:text-green-400">
                    <span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>
                    ${formatNumber(successCount)} success
               </span>`
            : '';

        const errorBadge = errorCount > 0
            ? `<span class="inline-flex items-center gap-1 rounded-full ${emphasizeErrors ? 'bg-red-500/10 text-red-600 dark:text-red-400' : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'} px-2 py-0.5">
                    <span class="w-1.5 h-1.5 rounded-full ${emphasizeErrors ? 'bg-red-500' : 'bg-amber-500'}"></span>
                    ${formatNumber(errorCount)} error${errorCount === 1 ? '' : 's'}
               </span>`
            : '';

        const noTrafficBadge = !hasTraffic
            ? `<span class="inline-flex items-center gap-1 rounded-full bg-black/5 dark:bg-white/10 px-2 py-0.5 text-black/40 dark:text-white/40">
                    <span class="w-1.5 h-1.5 rounded-full bg-black/30 dark:bg-white/30"></span>
                    No traffic yet
               </span>`
            : '';

        const content = [successBadge, errorBadge, noTrafficBadge]
            .filter(Boolean)
            .join('');

        return `<div class="flex flex-wrap items-center gap-2 mt-1" title="${title}">${content}</div>`;
    }

    buildStatusTooltip(successCount = 0, errorCount = 0, statusBreakdown = null) {
        const parts = [
            `Success responses: ${formatNumber(successCount)}`,
            `Error responses: ${formatNumber(errorCount)}`
        ];

        if (statusBreakdown && Object.keys(statusBreakdown).length > 0) {
            const sorted = Object.entries(statusBreakdown)
                .map(([code, count]) => [Number(code), Number(count) || 0])
                .sort((a, b) => a[0] - b[0]);

            sorted.forEach(([code, count]) => {
                parts.push(`${code}: ${formatNumber(count)}`);
            });
        }

        const tooltip = parts.join('\n');
        return escapeHtml(tooltip).replace(/\n/g, '&#10;');
    }

    /**
     * Update endpoints table
     */
    updateEndpointsTable(endpointMetrics) {
        const container = document.getElementById('endpointsContainer');
        if (!container) return;

        if (!this.components.endpointsTable) {
            container.innerHTML = '';
            this.components.endpointsTable = new EndpointsTable(container, endpointMetrics);
        } else {
            this.components.endpointsTable.update(endpointMetrics);
        }
    }

    /**
     * Update chart
     */
    updateChart(summary) {
        if (!summary || typeof summary !== 'object') {
            return;
        }

        if (this.chartManager && this.chartManager.isReady()) {
            const chartSummary = {
                ...summary,
                requests_per_minute: this.currentRequestRate
            };
            this.chartManager.update(chartSummary);
        }
    }

    /**
     * Update last refreshed timestamp
     */
    updateLastRefreshedTime() {
        const element = document.getElementById('lastUpdated');
        if (element) {
            element.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
        }
    }

    /**
     * Event handlers
     */
    async handleRefreshClick(event) {
        event.preventDefault();
        await this.debouncedRefresh();
    }

    handleAutoRefreshToggle(event) {
        if (!this.config.enableAutoRefresh) {
            this.stopAutoRefresh();
            return;
        }

        if (event.target.checked) {
            this.startAutoRefresh();
        } else {
            this.stopAutoRefresh();
        }
    }

    handleConnectivityChange(isOnline) {
        if (isOnline) {
            this.components.errorMessage.hide();
            // Resume auto-refresh if enabled
            const checkbox = document.getElementById('autoRefresh');
            const shouldAutoRefresh = this.config.enableAutoRefresh && (!checkbox || checkbox.checked);
            if (shouldAutoRefresh) {
                this.startAutoRefresh();
            }
        } else {
            this.components.errorMessage.show('Connection lost. Monitoring paused.');
            this.stopAutoRefresh();
        }
    }

    handleVisibilityChange() {
        if (document.hidden) {
            // Page hidden - pause auto-refresh to save resources
            this.stopAutoRefresh();
        } else {
            // Page visible - resume auto-refresh if enabled
            const checkbox = document.getElementById('autoRefresh');
            const shouldAutoRefresh = this.config.enableAutoRefresh && (!checkbox || checkbox.checked);
            if (shouldAutoRefresh) {
                this.startAutoRefresh();
                // Refresh immediately if data is stale
                const timeSinceLastUpdate = Date.now() - (this.lastUpdateTime || 0);
                if (timeSinceLastUpdate > this.config.refreshInterval) {
                    this.debouncedRefresh();
                }
            }
        }
    }

    /**
     * Cleanup and destroy dashboard
     */
    destroy() {
        this.isDestroyed = true;
        
        // Stop timers
        this.stopAutoRefresh();
        
        // Cleanup components
        Object.values(this.components).forEach(component => {
            if (component && typeof component.destroy === 'function') {
                component.destroy();
            }
        });
        
        // Cleanup chart
        if (this.chartManager) {
            this.chartManager.destroy();
        }
        
        // Cleanup connectivity monitor
        if (this.connectivityMonitor) {
            this.connectivityMonitor.destroy();
        }
        
        // Remove event listeners
        document.removeEventListener('keydown', this.handleKeyDown);
        document.removeEventListener('visibilitychange', this.handleVisibilityChange);
        
        console.log('Performance Dashboard destroyed');
    }
}

// Export for manual initialization
// Dashboard should be initialized from index.html to avoid double initialization

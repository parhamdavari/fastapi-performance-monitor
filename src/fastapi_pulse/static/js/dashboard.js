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
import { formatNumber, debounce } from './utils.js';

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
        
        // Bind methods
        this.handleRefreshClick = this.handleRefreshClick.bind(this);
        this.handleAutoRefreshToggle = this.handleAutoRefreshToggle.bind(this);
        this.handleConnectivityChange = this.handleConnectivityChange.bind(this);
        this.handleVisibilityChange = this.handleVisibilityChange.bind(this);
        this.debouncedRefresh = debounce(this.refreshMetrics.bind(this), 1000);
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
        const checkbox = document.getElementById('autoRefresh');
        
        if (checkbox && checkbox.checked && this.config.enableAutoRefresh) {
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
            this.updateSLAStatus(data.sla_compliance);
            this.updateMetricsCards(data.performance_metrics.summary);
            this.updateEndpointsTable(data.performance_metrics.endpoint_metrics);
            this.updateChart(data.performance_metrics.summary);
        } catch (error) {
            console.error('Error updating dashboard:', error);
            this.components.errorMessage.show('Error updating dashboard display.');
        }
    }

    /**
     * Update SLA status display
     */
    updateSLAStatus(slaCompliance) {
        const container = document.getElementById('slaGrid');
        if (!container) return;

        if (!this.components.slaStatus) {
            this.components.slaStatus = new SLAStatus(container, slaCompliance);
        } else {
            this.components.slaStatus.update(slaCompliance);
        }
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
        if (this.chartManager && this.chartManager.isReady()) {
            this.chartManager.update(summary);
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
            if (checkbox && checkbox.checked) {
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
            if (checkbox && checkbox.checked) {
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
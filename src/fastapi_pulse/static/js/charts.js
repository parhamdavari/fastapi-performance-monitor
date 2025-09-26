/**
 * Chart management with dynamic loading and fallbacks
 */

import { createElement } from './utils.js';

/**
 * Chart manager that handles Chart.js loading and fallbacks
 */
export class ChartManager {
    constructor(container, config = {}) {
        this.container = container;
        this.config = {
            maxDataPoints: config.maxDataPoints || 20,
            updateAnimation: config.updateAnimation || false,
            ...config
        };
        this.chart = null;
        this.chartLibrary = null;
        this.data = [];
        this.fallbackMode = false;
    }

    /**
     * Initialize chart with dynamic Chart.js loading
     */
    async init() {
        try {
            await this.loadChartLibrary();
            this.createChart();
        } catch (error) {
            console.warn('Chart.js failed to load, using fallback visualization:', error.message);
            this.fallbackMode = true;
            this.createFallbackChart();
        }
    }

    /**
     * Load Chart.js library dynamically
     */
    async loadChartLibrary() {
        // Try to load from CDN first
        try {
            if (window.Chart) {
                this.chartLibrary = window.Chart;
                return;
            }

            // Try primary CDN first
            await this.loadScriptFromUrl('https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.js');
            
            if (window.Chart) {
                this.chartLibrary = window.Chart;
                return;
            }
            
            throw new Error('Chart.js loaded but not available');
        } catch (error) {
            throw new Error(`Chart.js loading failed: ${error.message}`);
        }
    }

    /**
     * Load script from URL with timeout
     */
    async loadScriptFromUrl(url) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = url;
            script.crossOrigin = 'anonymous';
            
            const timeout = setTimeout(() => {
                script.remove();
                reject(new Error('Script loading timeout'));
            }, 10000);
            
            script.onload = () => {
                clearTimeout(timeout);
                resolve();
            };
            
            script.onerror = () => {
                clearTimeout(timeout);
                script.remove();
                reject(new Error(`Failed to load script from ${url}`));
            };
            
            document.head.appendChild(script);
        });
    }

    /**
     * Create Chart.js chart
     */
    createChart() {
        const canvas = createElement('canvas', {
            id: 'responseTimeChart',
            role: 'img',
            'aria-label': 'Response time trends chart'
        });
        
        this.container.appendChild(canvas);
        
        const ctx = canvas.getContext('2d');
        this.chart = new this.chartLibrary(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'P95 Response Time (ms)',
                        data: [],
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        tension: 0.4,
                        fill: true
                    },
                    {
                        label: 'Average Response Time (ms)',
                        data: [],
                        borderColor: '#48bb78',
                        backgroundColor: 'rgba(72, 187, 120, 0.1)',
                        tension: 0.4,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {
                    duration: this.config.updateAnimation ? 750 : 0
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Response Time (ms)'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Time'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            title: (context) => `Time: ${context[0].label}`,
                            label: (context) => `${context.dataset.label}: ${context.parsed.y.toFixed(1)}ms`
                        }
                    }
                }
            }
        });
    }

    /**
     * Create fallback chart using SVG
     */
    createFallbackChart() {
        const fallback = createElement('div', {
            className: 'chart-fallback',
            style: 'padding: 2rem; text-align: center; background: #f8f9fa; border-radius: 8px;',
            role: 'img',
            'aria-label': 'Chart unavailable - showing text metrics'
        });

        fallback.innerHTML = `
            <div style="margin-bottom: 1rem;">
                <strong>📊 Live Metrics</strong>
            </div>
            <div id="fallbackMetrics" style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; max-width: 400px; margin: 0 auto;">
                <div>P95: <strong id="fallbackP95">--</strong></div>
                <div>Avg: <strong id="fallbackAvg">--</strong></div>
            </div>
            <small style="color: #666; margin-top: 1rem; display: block;">
                Chart visualization unavailable. Showing latest metrics only.
            </small>
        `;

        this.container.appendChild(fallback);
    }

    /**
     * Update chart with new data
     */
    update(summary) {
        const now = new Date().toLocaleTimeString();
        
        // Add new data point
        this.data.push({
            time: now,
            p95: summary.p95_response_time || 0,
            avg: summary.avg_response_time || 0
        });

        // Keep only recent data points
        if (this.data.length > this.config.maxDataPoints) {
            this.data.shift();
        }

        if (this.fallbackMode) {
            this.updateFallbackChart(summary);
        } else if (this.chart) {
            this.updateChartJs();
        }
    }

    /**
     * Update Chart.js chart
     */
    updateChartJs() {
        this.chart.data.labels = this.data.map(point => point.time);
        this.chart.data.datasets[0].data = this.data.map(point => point.p95);
        this.chart.data.datasets[1].data = this.data.map(point => point.avg);
        
        this.chart.update(this.config.updateAnimation ? 'active' : 'none');
    }

    /**
     * Update fallback chart
     */
    updateFallbackChart(summary) {
        const p95El = document.getElementById('fallbackP95');
        const avgEl = document.getElementById('fallbackAvg');
        
        if (p95El) p95El.textContent = `${(summary.p95_response_time || 0).toFixed(1)}ms`;
        if (avgEl) avgEl.textContent = `${(summary.avg_response_time || 0).toFixed(1)}ms`;
    }

    /**
     * Clear all chart data
     */
    clear() {
        this.data = [];
        if (this.chart) {
            this.chart.data.labels = [];
            this.chart.data.datasets.forEach(dataset => {
                dataset.data = [];
            });
            this.chart.update('none');
        }
    }

    /**
     * Destroy chart and cleanup
     */
    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
        
        if (this.container) {
            this.container.innerHTML = '';
        }
    }

    /**
     * Check if chart is ready
     */
    isReady() {
        return this.fallbackMode || (this.chart !== null);
    }
}
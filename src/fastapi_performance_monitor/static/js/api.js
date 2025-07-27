/**
 * API client with robust error handling and retry logic
 */

import { retryWithBackoff, validateApiResponse } from './utils.js';

/**
 * API client for performance metrics
 */
export class MetricsAPI {
    constructor(config = {}) {
        this.baseUrl = config.baseUrl || `${window.location.protocol}//${window.location.host}`;
        this.timeout = config.timeout || 10000;
        this.maxRetries = config.maxRetries || 3;
        this.retryDelay = config.retryDelay || 1000;
    }

    /**
     * Fetch metrics with timeout and retry logic
     * @param {AbortSignal} signal - Abort signal for cancellation
     * @returns {Promise<Object>} - Metrics data
     */
    async fetchMetrics(signal = null) {
        const controller = new AbortController();
        const combinedSignal = this.combineSignals([signal, controller.signal].filter(Boolean));
        
        // Set timeout
        const timeoutId = setTimeout(() => controller.abort(), this.timeout);

        try {
            const response = await retryWithBackoff(
                async () => {
                    const response = await fetch(`${this.baseUrl}/health/metrics`, {
                        method: 'GET',
                        headers: {
                            'Accept': 'application/json',
                            'Cache-Control': 'no-cache'
                        },
                        signal: combinedSignal
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }

                    return response;
                },
                this.maxRetries,
                this.retryDelay
            );

            clearTimeout(timeoutId);

            const data = await response.json();
            validateApiResponse(data);
            
            return data;
        } catch (error) {
            clearTimeout(timeoutId);
            
            if (error.name === 'AbortError') {
                throw new Error('Request was cancelled');
            } else if (error.name === 'TypeError' && error.message.includes('fetch')) {
                throw new Error('Network error - please check your connection');
            } else {
                throw error;
            }
        }
    }

    /**
     * Ping endpoint to check connectivity
     * @returns {Promise<boolean>} - True if endpoint is reachable
     */
    async ping() {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);

            // Use GET request with cache control to minimize data transfer
            const response = await fetch(`${this.baseUrl}/health/metrics`, {
                method: 'GET',
                headers: {
                    'Cache-Control': 'no-cache',
                    'Accept': 'application/json'
                },
                signal: controller.signal
            });

            clearTimeout(timeoutId);
            return response.ok;
        } catch (error) {
            return false;
        }
    }

    /**
     * Combine multiple abort signals
     * @param {AbortSignal[]} signals - Array of abort signals
     * @returns {AbortSignal} - Combined signal
     */
    combineSignals(signals) {
        if (signals.length === 0) return null;
        if (signals.length === 1) return signals[0];

        const controller = new AbortController();
        
        for (const signal of signals) {
            if (signal.aborted) {
                controller.abort();
                break;
            }
            signal.addEventListener('abort', () => controller.abort());
        }

        return controller.signal;
    }
}

/**
 * Connectivity monitor
 */
export class ConnectivityMonitor {
    constructor(api, onStatusChange = null) {
        this.api = api;
        this.onStatusChange = onStatusChange;
        this.isOnline = navigator.onLine;
        this.lastSuccessfulPing = Date.now();
        this.checkInterval = null;
        
        this.setupEventListeners();
    }

    setupEventListeners() {
        window.addEventListener('online', () => {
            this.setOnlineStatus(true);
        });

        window.addEventListener('offline', () => {
            this.setOnlineStatus(false);
        });
    }

    startMonitoring(intervalMs = 30000) {
        this.stopMonitoring();
        
        this.checkInterval = setInterval(async () => {
            const isReachable = await this.api.ping();
            if (isReachable) {
                this.lastSuccessfulPing = Date.now();
                if (!this.isOnline) {
                    this.setOnlineStatus(true);
                }
            } else {
                // Consider offline if no successful ping for 2 minutes
                const timeSinceLastPing = Date.now() - this.lastSuccessfulPing;
                if (timeSinceLastPing > 120000 && this.isOnline) {
                    this.setOnlineStatus(false);
                }
            }
        }, intervalMs);
    }

    stopMonitoring() {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
            this.checkInterval = null;
        }
    }

    setOnlineStatus(isOnline) {
        if (this.isOnline !== isOnline) {
            this.isOnline = isOnline;
            if (this.onStatusChange) {
                this.onStatusChange(isOnline);
            }
        }
    }

    destroy() {
        this.stopMonitoring();
        window.removeEventListener('online', this.setOnlineStatus);
        window.removeEventListener('offline', this.setOnlineStatus);
    }
}
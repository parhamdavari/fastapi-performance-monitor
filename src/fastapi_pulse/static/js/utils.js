/**
 * Utility functions for the performance dashboard
 */

/**
 * Escapes HTML to prevent XSS attacks
 * @param {string} unsafe - Unsafe HTML string
 * @returns {string} - Escaped HTML string
 */
export function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return '';
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

/**
 * Safely sets text content to prevent XSS
 * @param {HTMLElement} element - Target element
 * @param {string} text - Text to set
 */
export function safeSetText(element, text) {
    if (element && element.textContent !== undefined) {
        element.textContent = text;
    }
}

/**
 * Safely sets HTML content with escaping
 * @param {HTMLElement} element - Target element
 * @param {string} html - HTML to set (will be escaped)
 */
export function safeSetHtml(element, html) {
    if (element) {
        element.innerHTML = escapeHtml(html);
    }
}

/**
 * Debounce function to limit rapid function calls
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} - Debounced function
 */
export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Validates API response structure
 * @param {Object} data - API response data
 * @throws {Error} - If data structure is invalid
 */
export function validateApiResponse(data) {
    if (!data || typeof data !== 'object') {
        throw new Error('Invalid API response: not an object');
    }
    
    if (!data.performance_metrics) {
        throw new Error('Invalid API response: missing performance_metrics');
    }
    
    if (!data.sla_compliance) {
        throw new Error('Invalid API response: missing sla_compliance');
    }
    
    const required = ['summary', 'endpoint_metrics'];
    for (const field of required) {
        if (!data.performance_metrics[field]) {
            throw new Error(`Invalid API response: missing performance_metrics.${field}`);
        }
    }
}

/**
 * Formats numbers with proper locale formatting
 * @param {number} num - Number to format
 * @param {number} decimals - Number of decimal places
 * @returns {string} - Formatted number
 */
export function formatNumber(num, decimals = 0) {
    if (typeof num !== 'number' || isNaN(num)) return '0';
    return num.toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

/**
 * Creates a DOM element with attributes and content
 * @param {string} tag - HTML tag name
 * @param {Object} attributes - Element attributes
 * @param {string|HTMLElement} content - Element content
 * @returns {HTMLElement} - Created element
 */
export function createElement(tag, attributes = {}, content = '') {
    const element = document.createElement(tag);
    
    // Set attributes
    Object.entries(attributes).forEach(([key, value]) => {
        if (key === 'className') {
            element.className = value;
        } else if (key === 'dataset') {
            Object.entries(value).forEach(([dataKey, dataValue]) => {
                element.dataset[dataKey] = dataValue;
            });
        } else {
            element.setAttribute(key, value);
        }
    });
    
    // Set content
    if (typeof content === 'string') {
        element.textContent = content;
    } else if (content instanceof HTMLElement) {
        element.appendChild(content);
    }
    
    return element;
}

/**
 * Retry function with exponential backoff
 * @param {Function} fn - Function to retry
 * @param {number} maxRetries - Maximum number of retries
 * @param {number} delay - Initial delay in milliseconds
 * @returns {Promise} - Promise that resolves with function result
 */
export async function retryWithBackoff(fn, maxRetries = 3, delay = 1000) {
    let lastError;
    
    for (let i = 0; i <= maxRetries; i++) {
        try {
            return await fn();
        } catch (error) {
            lastError = error;
            
            if (i === maxRetries) {
                throw lastError;
            }
            
            // Exponential backoff with jitter
            const backoffDelay = delay * Math.pow(2, i) + Math.random() * 1000;
            await new Promise(resolve => setTimeout(resolve, backoffDelay));
        }
    }
}

/**
 * Performance grade calculation
 * @param {number} p95Time - P95 response time
 * @param {number} successRate - Success rate percentage
 * @returns {string} - Performance grade (A-F)
 */
export function calculatePerformanceGrade(p95Time, successRate) {
    if (p95Time <= 50 && successRate >= 99) return 'A';
    if (p95Time <= 100 && successRate >= 95) return 'B';
    if (p95Time <= 200 && successRate >= 90) return 'C';
    if (p95Time <= 500 && successRate >= 80) return 'D';
    return 'F';
}

/**
 * Checks if a value represents a healthy status
 * @param {*} value - Value to check
 * @returns {boolean} - True if healthy
 */
export function isHealthyStatus(value) {
    return value === true || value === 'healthy' || value === 'pass';
}

/**
 * Gets appropriate CSS class for status
 * @param {*} status - Status value
 * @returns {string} - CSS class name
 */
export function getStatusClass(status) {
    if (status === true) return 'status-healthy';
    if (status === false) return 'status-error';
    return 'status-warning';
}
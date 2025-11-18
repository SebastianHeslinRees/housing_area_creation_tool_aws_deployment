/* ========== UK Fertility Dashboard - Client-Side JavaScript ========== */

// Namespace for our custom functions
window.dashExtensions = window.dashExtensions || {};

/**
 * Initialise dashboard on page load
 */
window.addEventListener('DOMContentLoaded', function() {
    console.log('Fertility Dashboard JavaScript loaded');
    
    // Check for saved dark mode preference
    initialiseDarkMode();
    
    // Add keyboard shortcuts
    initialiseKeyboardShortcuts();
});

/**
 * Initialise dark mode from localStorage
 */
function initialiseDarkMode() {
    const savedTheme = localStorage.getItem('darkMode');
    if (savedTheme === 'true') {
        document.body.classList.add('dark-mode');
        const button = document.getElementById('theme-toggle-button');
        if (button) {
            button.textContent = 'Light Mode ☀️';
        }
    }
}

/**
 * Initialise keyboard shortcuts
 */
function initialiseKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Alt+D for dark mode toggle
        if (e.altKey && e.key === 'd') {
            e.preventDefault();
            const button = document.getElementById('theme-toggle-button');
            if (button) button.click();
        }
        
        // Alt+M to focus LAD dropdown
        if (e.altKey && e.key === 'm') {
            e.preventDefault();
            const dropdown = document.querySelector('#lad-dropdown input');
            if (dropdown) dropdown.focus();
        }
        
        // Escape to clear focus
        if (e.key === 'Escape') {
            document.activeElement.blur();
        }
    });
}

/**
 * Utility: Log performance metrics
 */
window.dashExtensions.logPerformance = function(label) {
    if (window.performance && console.time) {
        console.timeStamp(label);
    }
};

/**
 * Utility: Check if element is in viewport
 */
window.dashExtensions.isInViewport = function(element) {
    const rect = element.getBoundingClientRect();
    return (
        rect.top >= 0 &&
        rect.left >= 0 &&
        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
};

/**
 * Add smooth scroll to top button
 */
window.addEventListener('scroll', function() {
    const scrollY = window.scrollY;
    // Could add a "scroll to top" button here if needed
});

console.log('✅ Dashboard utilities loaded');

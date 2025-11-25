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
    
    // Initialise sidebar
    initialiseSidebar();
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
        
        // Alt+S to toggle sidebar
        if (e.altKey && e.key === 's') {
            e.preventDefault();
            toggleSidebar();
        }
        
        // Escape to clear focus or close sidebar
        if (e.key === 'Escape') {
            const sidebar = document.getElementById('sidebar');
            if (sidebar && !sidebar.classList.contains('collapsed')) {
                toggleSidebar();
            } else {
                document.activeElement.blur();
            }
        }
    });
}

/**
 * Initialise sidebar toggle functionality
 */
function initialiseSidebar() {
    const toggleBtn = document.getElementById('sidebar-toggle');
    const closeBtn = document.getElementById('sidebar-close');
    const sidebar = document.getElementById('sidebar');
    const sidebarContainer = document.querySelector('.sidebar-container');
    const mainContent = document.getElementById('main-content');
    
    // Load saved sidebar state
    const savedState = localStorage.getItem('sidebarCollapsed');
    if (savedState === 'true') {
        sidebar.classList.add('collapsed');
        sidebarContainer.classList.add('collapsed');
        if (mainContent) mainContent.classList.add('sidebar-collapsed');
        if (toggleBtn) toggleBtn.classList.remove('hidden');
    } else {
        // Hide toggle button when sidebar is open
        if (toggleBtn) toggleBtn.classList.add('hidden');
    }
    
    // Toggle button click
    if (toggleBtn) {
        toggleBtn.addEventListener('click', toggleSidebar);
    }
    
    // Close button click
    if (closeBtn) {
        closeBtn.addEventListener('click', toggleSidebar);
    }
    
    // Close sidebar when clicking outside on mobile
    if (window.innerWidth <= 768) {
        document.addEventListener('click', function(e) {
            if (sidebar && !sidebar.classList.contains('collapsed') &&
                !sidebarContainer.contains(e.target) &&
                !toggleBtn.contains(e.target)) {
                toggleSidebar();
            }
        });
    }
}

/**
 * Toggle sidebar open/closed
 */
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const sidebarContainer = document.querySelector('.sidebar-container');
    const mainContent = document.getElementById('main-content');
    const toggleBtn = document.getElementById('sidebar-toggle');
    
    if (sidebar && sidebarContainer) {
        const isCollapsed = sidebar.classList.toggle('collapsed');
        sidebarContainer.classList.toggle('collapsed');
        if (mainContent) mainContent.classList.toggle('sidebar-collapsed');
        
        // Toggle button visibility
        if (toggleBtn) {
            if (isCollapsed) {
                toggleBtn.classList.remove('hidden');
            } else {
                toggleBtn.classList.add('hidden');
            }
        }
        
        // Save state
        localStorage.setItem('sidebarCollapsed', isCollapsed);
        
        // On mobile, also toggle 'open' class for different behavior
        if (window.innerWidth <= 768) {
            sidebar.classList.toggle('open');
        }
    }
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

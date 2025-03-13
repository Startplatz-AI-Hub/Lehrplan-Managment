document.addEventListener('DOMContentLoaded', function() {
    // Markiere den aktiven Menüpunkt
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });

    // Optional: Code, falls Sie AJAX-Upload implementieren möchten.
}); 
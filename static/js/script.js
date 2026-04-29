// Auto-hide flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
});

// Case search functionality (if you add a search bar)
function searchCases() {
    const searchTerm = document.getElementById('caseSearch').value;
    fetch(`/api/search_cases?q=${searchTerm}`)
        .then(response => response.json())
        .then(data => {
            console.log(data);
            // Update search results
        });
}
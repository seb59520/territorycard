document.addEventListener('DOMContentLoaded', loadCities);

function loadCities() {
    const loadingElement = document.getElementById('loading');
    const errorElement = document.getElementById('error');
    const citiesContainer = document.getElementById('cities-container');

    loadingElement.classList.remove('d-none');
    errorElement.classList.add('d-none');
    citiesContainer.innerHTML = '';

    fetch('/territories/cities')
        .then(response => response.json())
        .then(data => {
            loadingElement.classList.add('d-none');
            
            if (data.cities && data.cities.length > 0) {
                citiesContainer.innerHTML = data.cities
                    .map(city => createCityCard(city))
                    .join('');
            } else {
                citiesContainer.innerHTML = `
                    <div class="col-12 text-center">
                        <p class="text-muted">Aucune ville trouvée</p>
                    </div>`;
            }
        })
        .catch(error => {
            console.error('Erreur:', error);
            loadingElement.classList.add('d-none');
            errorElement.classList.remove('d-none');
        });
}

function createCityCard(city) {
    const totalBuildings = city.stats.houses + city.stats.apartments;
    const hasBuildings = totalBuildings > 0;
    
    let buildingsHtml = '';
    if (hasBuildings) {
        const housePercent = (city.stats.houses / totalBuildings * 100).toFixed(0);
        buildingsHtml = `
            <div class="city-stats">
                <div class="stats-label">
                    <i class="fas fa-home"></i> ${city.stats.houses} maisons
                </div>
                <div class="progress">
                    <div class="progress-bar bg-success" 
                         role="progressbar" 
                         style="width: ${housePercent}%" 
                         aria-valuenow="${housePercent}" 
                         aria-valuemin="0" 
                         aria-valuemax="100">
                        ${housePercent}%
                    </div>
                </div>
                <div class="mt-2">
                    <span class="text-muted">
                        <i class="fas fa-calculator"></i> Total: ${totalBuildings}
                    </span>
                </div>
            </div>`;
    } else {
        buildingsHtml = `
            <div class="no-data">
                <i class="fas fa-info-circle"></i> Pas de données de bâtiments
            </div>`;
    }

    return `
        <div class="col-md-6 col-lg-4">
            <div class="city-card">
                <div class="city-title d-flex justify-content-between align-items-center">
                    <span>
                        <i class="fas fa-map-marker-alt text-danger"></i>
                        ${city.name === "Ville inconnue" ? 
                            '<span class="text-muted">Ville inconnue</span>' : 
                            city.name}
                    </span>
                    <span class="territory-count">
                        ${city.stats.territories} territoire${city.stats.territories !== 1 ? 's' : ''}
                    </span>
                </div>
                
                ${buildingsHtml}
                
                <button class="btn btn-outline-primary btn-print" 
                        onclick="window.location.href='/print/${encodeURIComponent(city.name)}'">
                    <i class="fas fa-print"></i> Imprimer
                </button>
            </div>
        </div>`;
}

document.addEventListener('DOMContentLoaded', function () {
    // Elementos del DOM
    const form = document.getElementById('predictionForm');
    const resultsDiv = document.getElementById('results');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const riskFactorsDiv = document.getElementById('riskFactors');
    let mortalityChart = null;
    let severityChart = null;

    // Inicializar gráficos
    const mortalityCtx = document.getElementById('mortalityChart').getContext('2d');
    const severityCtx = document.getElementById('severityChart').getContext('2d');

    // Configuración de gráficos
    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'bottom',
                labels: {
                    boxWidth: 12,
                    padding: 20,
                    font: {
                        weight: '600'
                    }
                }
            }
        }
    };

    // Manejar envío del formulario
    form.addEventListener('submit', function (e) {
        e.preventDefault();

        if (!form.checkValidity()) {
            e.stopPropagation();
            form.classList.add('was-validated');
            return;
        }

        // Mostrar indicador de carga
        loadingIndicator.classList.remove('d-none');
        resultsDiv.innerHTML = '';
        riskFactorsDiv.innerHTML = '';

        // Obtener datos del formulario
        const patientData = {
            age: parseInt(document.getElementById('age').value),
            blood_pressure: parseInt(document.getElementById('blood_pressure').value),
            heart_rate: parseInt(document.getElementById('heart_rate').value),
            oxygen_level: parseInt(document.getElementById('oxygen_level').value),
            chronic_conditions: parseInt(document.getElementById('chronic_conditions').value)
        };

        // Enviar datos al backend
        fetch('https://medpredictpro-api.onrender.com/predict', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(patientData)
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Error en la respuesta del servidor');
                }
                return response.json();
            })
            .then(data => {
                if (data.status === 'success') {
                    displayResults(data, patientData);
                } else {
                    showError(data.message || 'Error desconocido');
                }
            })
            .catch(error => {
                showError(`Error de conexión: ${error.message}`);
            })
            .finally(() => {
                loadingIndicator.classList.add('d-none');
            });
    });

    function displayResults(data, patientData) {
        const mortalityPercent = (data.mortality_probability * 100).toFixed(1);
        const severityLevel = data.severity_level;

        // Calcular factores de riesgo individuales
        const riskFactors = calculateRiskFactors(patientData);

        // Determinar nivel de riesgo
        let riskLevel, riskClass;
        let riskLevelText;
        if (data.mortality_probability < 0.3) {
            riskLevel = "low";
            riskLevelText = "Bajo Riesgo";
            riskClass = "low-risk";
        } else if (data.mortality_probability < 0.7) {
            riskLevel = "medium";
            riskLevelText = "Riesgo Moderado";
            riskClass = "medium-risk";
        } else {
            riskLevel = "high";
            riskLevelText = "Alto Riesgo";
            riskClass = "high-risk";
        }

        // Mostrar resultados principales (código anterior permanece igual)
        resultsDiv.innerHTML = `
            <div class="animate-fade-in">
                <h3 class="risk-indicator ${riskClass} mb-4">${riskLevelText}</h3>
                <div class="row">
                    <div class="col-md-6">
                        <div class="card bg-light mb-3">
                            <div class="card-body text-center">
                                <h6 class="text-muted mb-3">Probabilidad de Mortalidad</h6>
                                <h2 class="${riskClass}">${mortalityPercent}%</h2>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="card bg-light mb-3">
                            <div class="card-body text-center">
                                <h6 class="text-muted mb-3">Nivel de Severidad</h6>
                                <span class="severity-indicator severity-${severityLevel}">Nivel ${severityLevel}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Actualizar gráficos
        updateCharts(data.mortality_probability, severityLevel);

        // Mostrar factores de riesgo
        displayRiskFactors(riskFactors);

        // Mostrar recomendaciones
        displayRecommendations(data.mortality_probability, severityLevel);

        // Guardar la evaluación en el histórico (MODIFICADO)
        saveToDatabase(patientData, {
            mortality_probability: data.mortality_probability,
            severity_level: severityLevel,
            risk_level: riskLevel
        });
    }

    function calculateRiskFactors(patientData) {
        // Calcular puntuaciones de riesgo individuales
        const ageRisk = Math.min(patientData.age / 100, 1);
        const bpRisk = patientData.blood_pressure > 140 ?
            Math.min((patientData.blood_pressure - 140) / 60, 1) : 0;
        const oxyRisk = patientData.oxygen_level < 95 ?
            Math.min((95 - patientData.oxygen_level) / 25, 1) : 0;
        const chronicRisk = patientData.chronic_conditions / 5;

        return {
            age: { value: patientData.age, risk: ageRisk, label: 'Edad' },
            blood_pressure: { value: patientData.blood_pressure, risk: bpRisk, label: 'Presión Arterial' },
            oxygen_level: { value: patientData.oxygen_level, risk: oxyRisk, label: 'Oxígeno en Sangre' },
            chronic_conditions: { value: patientData.chronic_conditions, risk: chronicRisk, label: 'Condiciones Crónicas' }
        };
    }

    function updateCharts(mortalityProb, severityLevel) {
        // Gráfico de mortalidad
        if (mortalityChart) mortalityChart.destroy();
        mortalityChart = new Chart(mortalityCtx, {
            type: 'doughnut',
            data: {
                labels: ['Probabilidad', 'Restante'],
                datasets: [{
                    data: [mortalityProb * 100, 100 - (mortalityProb * 100)],
                    backgroundColor: [
                        getRiskColor(mortalityProb),
                        '#e9ecef'
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                ...chartOptions,
                plugins: {
                    ...chartOptions.plugins,
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                return `${context.label}: ${context.raw.toFixed(1)}%`;
                            }
                        }
                    }
                },
                cutout: '70%'
            }
        });

        // Gráfico de severidad
        if (severityChart) severityChart.destroy();
        severityChart = new Chart(severityCtx, {
            type: 'bar',
            data: {
                labels: ['Nivel de Severidad'],
                datasets: [{
                    label: `Nivel ${severityLevel}`,
                    data: [severityLevel],
                    backgroundColor: getSeverityColor(severityLevel),
                    borderWidth: 0,
                    borderRadius: 6
                }]
            },
            options: {
                ...chartOptions,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 5,
                        ticks: {
                            stepSize: 1
                        }
                    }
                },
                indexAxis: 'y'
            }
        });
    }

    function displayRiskFactors(factors) {
        let html = '<div class="row g-3">';

        for (const [key, factor] of Object.entries(factors)) {
            const riskPercent = (factor.risk * 100).toFixed(0);
            const riskColor = getRiskColor(factor.risk);

            html += `
                <div class="col-md-6">
                    <div class="risk-factor-item animate-fade-in" style="animation-delay: ${0.1 * Object.keys(factors).indexOf(key)}s">
                        <div class="risk-factor-name">
                            <span>${factor.label}</span>
                            <span class="risk-factor-value">${factor.value} ${getFactorUnit(key)}</span>
                        </div>
                        <div class="progress">
                            <div class="progress-bar" 
                                 role="progressbar" 
                                 style="width: ${riskPercent}%; background-color: ${riskColor}"
                                 aria-valuenow="${riskPercent}" 
                                 aria-valuemin="0" 
                                 aria-valuemax="100">
                            </div>
                        </div>
                        <small class="text-muted">Contribución al riesgo: ${riskPercent}%</small>
                    </div>
                </div>
            `;
        }

        html += '</div>';
        riskFactorsDiv.innerHTML = html;
    }

    function displayRecommendations(mortalityProb, severityLevel) {
        let recommendation = '';
        let alertClass = '';

        if (mortalityProb < 0.3) {
            recommendation = 'Paciente de bajo riesgo. Seguimiento rutinario recomendado.';
            alertClass = 'alert-success';
        } else if (mortalityProb < 0.7) {
            recommendation = 'Paciente de riesgo moderado. Se recomienda evaluación adicional y posible intervención médica.';
            alertClass = 'alert-warning';
        } else {
            recommendation = 'Paciente de alto riesgo. Requiere atención inmediata y posible hospitalización.';
            alertClass = 'alert-danger';
        }

        // Añadir recomendaciones específicas por severidad
        if (severityLevel >= 4) {
            recommendation += ' Considerar monitoreo continuo y tratamiento intensivo.';
        } else if (severityLevel >= 2) {
            recommendation += ' Se sugiere evaluación por especialista.';
        }

        resultsDiv.insertAdjacentHTML('beforeend', `
            <div class="alert ${alertClass} mt-4 animate-fade-in" style="animation-delay: 0.4s">
                <h5><i class="bi bi-exclamation-triangle-fill me-2"></i>Recomendación Clínica</h5>
                <hr>
                <p class="mb-0">${recommendation}</p>
            </div>
        `);
    }

    function showError(message) {
        resultsDiv.innerHTML = `
            <div class="alert alert-danger animate-fade-in">
                <i class="bi bi-exclamation-octagon-fill me-2"></i>
                ${message}
            </div>
        `;
    }

    // Funciones auxiliares
    function getRiskColor(risk) {
        if (risk < 0.3) return '#28a745';  // Verde
        if (risk < 0.7) return '#fd7e14';  // Naranja
        return '#dc3545';                  // Rojo
    }

    function getSeverityColor(level) {
        const colors = {
            1: '#4CAF50',  // Verde
            2: '#8BC34A',  // Verde claro
            3: '#FFC107',  // Amarillo
            4: '#FF9800',  // Naranjo
            5: '#F44336'   // Rojo
        };
        return colors[level] || '#9E9E9E'; // Gris por defecto
    }

    function getFactorUnit(factor) {
        const units = {
            age: 'años',
            blood_pressure: 'mmHg',
            heart_rate: 'lpm',
            oxygen_level: '%',
            chronic_conditions: ''
        };
        return units[factor] || '';
    }
});

function initializeApp(elements) {
    // Configurar el botón de limpiar
    elements.clearFormBtn.addEventListener('click', function () {
        if (confirm('¿Borrar todos los datos del formulario?')) {
            resetApplication(elements);
            showToast('Formulario limpiado correctamente', 'success');
        }
    });

    // Resto de la inicialización de tu aplicación...
}

function resetApplication({ predictionForm, resultsDiv, generatePdf }) {
    // Resetear formulario
    predictionForm.reset();
    predictionForm.classList.remove('was-validated');

    // Resetear resultados
    resultsDiv.innerHTML = `
        <div class="alert alert-info">
            <i class="bi bi-info-circle-fill me-2"></i>
            Complete el formulario para obtener la evaluación
        </div>
    `;
}

function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `toast show align-items-center text-white bg-${type}`;
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <i class="bi ${type === 'success' ? 'bi-check-circle' : 'bi-exclamation-triangle'} me-2"></i>
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;

    toast.style.position = 'fixed';
    toast.style.bottom = '20px';
    toast.style.right = '20px';
    toast.style.zIndex = '1100';

    document.body.appendChild(toast);

    setTimeout(() => toast.remove(), 3000);
}

// Función para guardar en la base de datos
function saveToDatabase() {
    // Verificar si hay datos del formulario
    const firstName = document.getElementById('first_name').value;
    const lastName = document.getElementById('last_name').value;
    const rut = document.getElementById('rut').value;
    
    if (!firstName || !lastName || !rut) {
        showToast('Complete los datos del paciente antes de guardar', 'warning');
        return;
    }

    // Verificar si ya hay resultados calculados
    const resultsDiv = document.getElementById('results');
    if (resultsDiv.textContent.includes('Complete el formulario')) {
        showToast('Primero calcule los resultados antes de guardar', 'warning');
        return;
    }

    // Mostrar indicador de carga
    const saveButton = document.getElementById('saveToDatabase');
    saveButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Guardando...';
    saveButton.disabled = true;

    // Obtener todos los datos necesarios
    const patientData = {
        personal_info: {
            first_name: firstName,
            last_name: lastName,
            rut: rut,
            gender: document.querySelector('input[name="gender"]:checked')?.value,
            age: parseInt(document.getElementById('age').value)
        },
        clinical_data: {
            blood_pressure: parseInt(document.getElementById('blood_pressure').value),
            heart_rate: parseInt(document.getElementById('heart_rate').value),
            oxygen_level: parseInt(document.getElementById('oxygen_level').value),
            chronic_conditions: parseInt(document.getElementById('chronic_conditions').value),
            observations: document.getElementById('medical_observations').value
        }
    };

    fetch('https://medpredictpro-api.onrender.com/save_evaluation', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            patient_data: {
                personal_info: {
                    first_name: document.getElementById('first_name').value,
                    last_name: document.getElementById('last_name').value,
                    rut: document.getElementById('rut').value,
                    gender: document.querySelector('input[name="gender"]:checked')?.value,
                    age: parseInt(document.getElementById('age').value)
                },
                clinical_data: {
                    blood_pressure: parseInt(document.getElementById('blood_pressure').value),
                    heart_rate: parseInt(document.getElementById('heart_rate').value),
                    oxygen_level: parseInt(document.getElementById('oxygen_level').value),
                    chronic_conditions: parseInt(document.getElementById('chronic_conditions').value),
                    observations: document.getElementById('medical_observations').value
                }
            },
            results: {
                mortality_probability: parseFloat(document.querySelector('[class*="risk"] h2')?.textContent.replace('%', '') / 100 || 0),
                severity_level: parseInt(document.querySelector('.severity-indicator')?.textContent.replace('Nivel ', '') || 0),
                risk_level: document.querySelector('.risk-indicator')?.classList.contains('low-risk') ? 'low' : 
                            document.querySelector('.risk-indicator')?.classList.contains('medium-risk') ? 'medium' : 'high'
            }
        })
    })
    .then(async response => {
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.message || `Error HTTP: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 'success') {
            showToast('Evaluación guardada exitosamente', 'success');
        } else {
            throw new Error(data.message || 'Error desconocido al guardar');
        }
    })
    .catch(error => {
        console.error('Error detallado:', error);
        showToast(`Error al guardar: ${error.message}`, 'danger');
    })
    .finally(() => {
        saveButton.innerHTML = '<i class="bi bi-database-fill-add me-2"></i>Guardar en Base de Datos';
        saveButton.disabled = false;
    });
}

// Agregar event listener al botón
document.addEventListener('DOMContentLoaded', function() {
    // ... (código existente)
    
    document.getElementById('saveToDatabase').addEventListener('click', saveToDatabase);
}); 

// Función para cargar y mostrar el histórico de evaluaciones
function loadEvaluationHistory() {
    const historyContainer = document.getElementById('evaluationHistory');
    if (!historyContainer) return;

    // Mostrar indicador de carga
    historyContainer.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary" role="status"></div></div>';

    fetch('https://medpredictpro-api.onrender.com/get_evaluations')
        .then(response => {
            if (!response.ok) {
                throw new Error('Error al cargar el histórico');
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success' && data.data.length > 0) {
                renderEvaluationHistory(data.data);
            } else {
                historyContainer.innerHTML = '<div class="alert alert-info">No hay evaluaciones registradas</div>';
            }
        })
        .catch(error => {
            historyContainer.innerHTML = `<div class="alert alert-danger">${error.message}</div>`;
        });
}

// Función para renderizar la tabla de evaluaciones
function renderEvaluationHistory(evaluations) {
    const historyContainer = document.getElementById('evaluationHistory');
    
    // Ordenar evaluaciones por fecha (más reciente primero)
    evaluations.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    const tableHtml = `
        <div class="table-responsive">
            <table class="table table-hover table-striped">
                <thead class="table-dark">
                    <tr>
                        <th>Fecha</th>
                        <th>Paciente</th>
                        <th>Edad</th>
                        <th>Riesgo</th>
                        <th>Mortalidad</th>
                        <th>Severidad</th>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody>
                    ${evaluations.map(eval => `
                        <tr>
                            <td>${formatDate(eval.timestamp)}</td>
                            <td>${eval.first_name} ${eval.last_name}</td>
                            <td>${eval.age}</td>
                            <td><span class="badge ${getRiskBadgeClass(eval.risk_level)}">${getRiskText(eval.risk_level)}</span></td>
                            <td>${(eval.mortality_probability * 100).toFixed(1)}%</td>
                            <td><span class="severity-indicator severity-${eval.severity_level}">Nivel ${eval.severity_level}</span></td>
                            <td>
                                <button class="btn btn-sm btn-outline-primary" onclick="viewEvaluationDetails('${eval.id}')">
                                    <i class="bi bi-eye"></i> Ver
                                </button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
    
    historyContainer.innerHTML = tableHtml;
}

// Funciones auxiliares
function formatDate(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleDateString('es-CL', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function getRiskBadgeClass(riskLevel) {
    return {
        'low': 'bg-success',
        'medium': 'bg-warning text-dark',
        'high': 'bg-danger'
    }[riskLevel] || 'bg-secondary';
}

function getRiskText(riskLevel) {
    return {
        'low': 'Bajo',
        'medium': 'Moderado',
        'high': 'Alto'
    }[riskLevel] || 'Desconocido';
}

// Función para ver detalles (puedes implementarla según tus necesidades)
function viewEvaluationDetails(evaluationId) {
    // Implementa la lógica para mostrar los detalles completos de la evaluación
    alert(`Mostrando detalles de la evaluación ID: ${evaluationId}`);
    // Aquí podrías hacer un fetch para obtener los detalles completos
    // y mostrarlos en un modal o página separada
}

// Cargar el histórico cuando la página esté lista
document.addEventListener('DOMContentLoaded', function() {
    // Verificar si estamos en la página de histórico
    if (document.getElementById('evaluationHistory')) {
        loadEvaluationHistory();
    }
});
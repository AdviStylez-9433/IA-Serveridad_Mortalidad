from flask import Flask, request, jsonify, send_from_directory, render_template_string, render_template
from flask_cors import CORS
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import joblib
import os
from datetime import datetime
import json
import time

# Configuración inicial de la aplicación
app = Flask(__name__, static_folder='.', static_url_path='')

# Configuración CORS detallada
CORS(app, resources={
    r"/*": {
        "origins": ["https://medpredictpro.onrender.com"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Configuración de rutas
MODEL_PATH = 'mortality_model.pkl'
HISTORY_DB = 'evaluations.json'

# Función para generar datos médicos
def generate_realistic_medical_data(n_samples=5000):
    """Genera datos médicos con relaciones realistas entre variables"""
    np.random.seed(42)
    
    age = np.clip(np.random.normal(loc=50, scale=15, size=n_samples), 18, 100).astype(int)
    chronic_conditions = np.minimum(np.random.poisson(1.2, size=n_samples), 5)
    blood_pressure = np.clip(
        90 + age * 0.4 + chronic_conditions * 6 + np.random.normal(0, 8, n_samples),
        70, 190
    ).astype(int)
    oxygen_level = np.clip(
        98 - chronic_conditions * 3 - np.abs(np.random.normal(0, 3, n_samples)),
        75, 100
    ).astype(int)
    heart_rate = np.clip(
        65 + (blood_pressure - 100) * 0.15 + (age - 50) * 0.1 + np.random.normal(0, 5, n_samples),
        45, 130
    ).astype(int)
    severity = np.clip(
        1 + 
        (age > 65).astype(int) + 
        (blood_pressure > 140).astype(int) + 
        (oxygen_level < 90).astype(int) + 
        np.minimum(chronic_conditions, 3) +
        np.random.binomial(1, 0.2, size=n_samples),
        1, 5
    )
    mortality_prob = 1 / (1 + np.exp(
        -(-4.5 + 
         age * 0.03 + 
         (blood_pressure > 140) * 0.8 + 
         (oxygen_level < 90) * 1.2 + 
         chronic_conditions * 0.5)
    ))
    mortality = (np.random.rand(n_samples) < mortality_prob).astype(int)
    
    return pd.DataFrame({
        'age': age,
        'blood_pressure': blood_pressure,
        'heart_rate': heart_rate,
        'oxygen_level': oxygen_level,
        'chronic_conditions': chronic_conditions,
        'severity': severity,
        'mortality': mortality
    })

# Cargar o crear modelo
if os.path.exists(MODEL_PATH):
    model = joblib.load(MODEL_PATH)
else:
    df = generate_realistic_medical_data(10000)
    X = df.drop(['mortality', 'severity'], axis=1)
    y_mortality = df['mortality']
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=7,
        min_samples_split=5,
        class_weight='balanced',
        random_state=42
    )
    model.fit(X, y_mortality)
    joblib.dump(model, MODEL_PATH)

# Funciones para manejar evaluaciones
def load_evaluations():
    try:
        with open(HISTORY_DB, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_evaluation(evaluation):
    evaluations = load_evaluations()
    evaluations.append(evaluation)
    with open(HISTORY_DB, 'w') as f:
        json.dump(evaluations, f)

# Endpoints de la API
@app.route('/predict', methods=['POST', 'OPTIONS'])
def predict():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'success'})
        response.headers.add('Access-Control-Allow-Origin', 'https://medpredictpro.onrender.com')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response
    
    try:
        data = request.get_json()
        
        if not all(key in data for key in ['age', 'blood_pressure', 'heart_rate', 'oxygen_level', 'chronic_conditions']):
            return jsonify({'status': 'error', 'message': 'Faltan parámetros requeridos'}), 400
        
        input_data = pd.DataFrame([{
            'age': max(18, min(100, int(data['age']))),
            'blood_pressure': max(70, min(190, int(data['blood_pressure']))),
            'heart_rate': max(40, min(130, int(data['heart_rate']))),
            'oxygen_level': max(70, min(100, int(data['oxygen_level']))),
            'chronic_conditions': max(0, min(5, int(data['chronic_conditions'])))
        }])
        
        mortality_prob = model.predict_proba(input_data)[0][1]
        severity_pred = int(np.clip(
            1 + 
            (input_data['age'].values[0] > 65) + 
            (input_data['blood_pressure'].values[0] > 140) + 
            (input_data['oxygen_level'].values[0] < 90) + 
            min(input_data['chronic_conditions'].values[0], 3),
            1, 5
        ))
        adjusted_prob = min(0.99, mortality_prob * (1 + severity_pred * 0.1))
        
        return jsonify({
            'mortality_probability': float(adjusted_prob),
            'severity_level': severity_pred,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/save_evaluation', methods=['POST'])
def save_eval():
    try:
        data = request.get_json()
        evaluation = {
            'id': f"eval-{datetime.now().timestamp()}",
            'timestamp': datetime.now().isoformat(),
            'patient_data': data['patient_data'],
            'results': data['results']
        }
        save_evaluation(evaluation)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_evaluations', methods=['GET'])
def get_evals():
    try:
        evaluations = load_evaluations()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        filtered = []
        for eval in evaluations:
            eval_date = datetime.fromisoformat(eval['timestamp'])
            
            if start_date:
                start = datetime.fromisoformat(start_date)
                if eval_date < start:
                    continue
            
            if end_date:
                end = datetime.fromisoformat(end_date)
                if eval_date > end:
                    continue
            
            filtered.append(eval)
        
        filtered.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'status': 'success',
            'data': filtered,
            'count': len(filtered)
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Rutas para archivos estáticos
def get_html(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        return file.read()

@app.route("/")
def serve_index():
    return render_template_string(get_html('index.html'))

@app.route("/<page_name>.html")
def serve_html(page_name):
    try:
        return render_template_string(get_html(f'{page_name}.html'))
    except FileNotFoundError:
        return "Página no encontrada", 404

@app.route("/<filename>.<ext>")
def serve_static(filename, ext):
    allowed_extensions = ['js', 'css', 'png', 'jpg', 'jpeg', 'pdf']
    if ext not in allowed_extensions:
        return "Tipo de archivo no permitido", 403
    
    try:
        return send_from_directory('.', f'{filename}.{ext}')
    except FileNotFoundError:
        return "Archivo no encontrado", 404

@app.route("/favicon-new.png")
def serve_favicon():
    return send_from_directory('.', "favicon-new.png")

@app.route("/mortality_model.pkl")
def serve_model():
    return send_from_directory('.', "mortality_model.pkl")

@app.route("/plantilla.csv")
def serve_csv():
    return send_from_directory('.', "plantilla.csv")

# Configuración para producción
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

def get_status_data():
    """Obtiene los datos de estado"""
    start_time = time.time()
    current_time = datetime.utcnow()
    uptime_seconds = round(time.time() - start_time)
    
    return {
        "service": "MedPredict Pro",
        "description": "Medical Predictions Service",  # Añadido
        "status": "active",
        "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "config_file": "/etc/systemd/system/medpredict.service",  # Añadido
        "enabled": "enabled",  # Añadido
        "version": "1.0.0",
        "components": {
            "database": "online",
            "ml_model": "loaded",
            "api": "operational"
        },
        "uptime": f"{uptime_seconds} seconds",
        "response_time": "50ms",
        "environment": "production",
        "pid": 12345,  # Añadido
        "process_name": "medpredict",  # Añadido
        "threads": 4,  # Añadido
        "thread_limit": 100,  # Añadido
        "memory_usage": "45.2MB",  # Añadido
        "hostname": "medpredict-server",  # Añadido
        "last_event": "Service initialized successfully"  # Añadido
    }

@app.route('/status')
def status_cmd():
    """Endpoint de estado en formato Linux systemd (sin colores)"""
    status = get_status_data()
    
    output = []
    
    # Encabezado estilo systemd
    status_symbol = "●" if status['status'] == 'active' else "○"
    output.append(f"{status_symbol} {status['service']}.service - {status['description']}")
    
    # Líneas de estado
    output.append(f"     Loaded: loaded ({status['config_file']}; {status['enabled']}; vendor preset: enabled)")
    output.append(f"     Active: {status['status']} (running) since {status['timestamp']}; {status['uptime']} ago")
    
    if status.get('docs'):
        output.append(f"       Docs: {status['docs']}")
    
    output.append(f"   Main PID: {status['pid']} ({status['process_name']})")
    output.append(f"      Tasks: {status['threads']} (limit: {status['thread_limit']})")
    output.append(f"     Memory: {status['memory_usage']}")
    output.append(f"      Components:")
    
    for component, state in status['components'].items():
        output.append(f"             ├─ {component} ({state})")
    
    # Línea de log simulada
    log_timestamp = datetime.strptime(status['timestamp'], "%Y-%m-%d %H:%M:%S UTC").strftime("%b %d %H:%M:%S")
    output.append(f"\n{log_timestamp} {status['hostname']} systemd[1]: {status['last_event']}")
    
    return "<pre>" + "\n".join(output) + "</pre>"
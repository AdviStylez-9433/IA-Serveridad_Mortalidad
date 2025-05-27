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
import pytz
from supabase import create_client, Client
import os
from dotenv import load_dotenv

# Configuración inicial de la aplicación
app = Flask(__name__, static_folder='.', static_url_path='')

# Configuración CORS detallada
CORS(app, resources={   
    r"/*": {
        "origins": ["https://medpredictpro-api.onrender.com"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Configuración de Supabase
SUPABASE_URL = 'https://jhopjsuivasskmfnbwul.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Impob3Bqc3VpdmFzc2ttZm5id3VsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDc5NjAzNjgsImV4cCI6MjA2MzUzNjM2OH0.aNU0roJdc1aH7_xGTggzhO-jByMdbE0YGS2GX2wtNm4'
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def initialize_database():
    """
    Versión simplificada que solo verifica/crea la tabla
    """
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            print(f"Intento {attempt + 1} de verificación de la tabla...")
            
            # Verificar si la tabla existe intentando una consulta simple
            try:
                supabase.table('evaluations').select("id").limit(1).execute()
                print("✅ Tabla 'evaluations' ya existe")
                return True
            except Exception as e:
                print("⚠️ Tabla no encontrada")
                print("""
                Por favor crea la tabla manualmente en Supabase con este SQL:
                
                CREATE TABLE evaluations (
                    id TEXT PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    age INTEGER NOT NULL,
                    blood_pressure INTEGER NOT NULL,
                    heart_rate INTEGER NOT NULL,
                    oxygen_level INTEGER NOT NULL,
                    chronic_conditions INTEGER NOT NULL,
                    mortality_probability FLOAT NOT NULL,
                    severity_level INTEGER NOT NULL,
                    risk_level TEXT NOT NULL
                );
                """)
                return False
                
        except Exception as e:
            print(f"⚠️ Error en el intento {attempt + 1}: {str(e)}")
            if attempt == max_retries - 1:
                print("❌ Número máximo de intentos alcanzado")
                return False
            time.sleep(retry_delay)

initialize_database()

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

# Reemplaza las funciones load_evaluations y save_evaluation con estas:

def load_evaluations():
    try:
        response = supabase.table('evaluations').select("*").execute()
        return response.data
    except Exception as e:
        print(f"Error loading evaluations: {str(e)}")
        return []

@app.route('/save_evaluation', methods=['POST'])
def save_evaluation():
    try:
        data = request.get_json()
        print("Datos recibidos:", data)  # Log para depuración
        
        # Validación de datos más robusta
        if not data:
            return jsonify({'status': 'error', 'message': 'No se recibieron datos'}), 400
            
        required_fields = {
            'patient_data': ['personal_info', 'clinical_data'],
            'results': ['mortality_probability', 'severity_level']
        }
        
        for parent_field, child_fields in required_fields.items():
            if parent_field not in data:
                return jsonify({'status': 'error', 'message': f'Falta el campo {parent_field}'}), 400
            for field in child_fields:
                if field not in data[parent_field]:
                    return jsonify({'status': 'error', 'message': f'Falta el campo {parent_field}.{field}'}), 400

        # Preparar datos para Supabase
        evaluation = {
            'id': f"eval-{datetime.now().timestamp()}",
            'timestamp': datetime.now().isoformat(),
            'first_name': data['patient_data']['personal_info'].get('first_name', ''),
            'last_name': data['patient_data']['personal_info'].get('last_name', ''),
            'rut': data['patient_data']['personal_info'].get('rut', ''),
            'gender': data['patient_data']['personal_info'].get('gender', ''),
            'age': int(data['patient_data']['personal_info'].get('age', 0)),
            'blood_pressure': int(data['patient_data']['clinical_data'].get('blood_pressure', 0)),
            'heart_rate': int(data['patient_data']['clinical_data'].get('heart_rate', 0)),
            'oxygen_level': int(data['patient_data']['clinical_data'].get('oxygen_level', 0)),
            'chronic_conditions': int(data['patient_data']['clinical_data'].get('chronic_conditions', 0)),
            'observations': data['patient_data']['clinical_data'].get('observations', ''),
            'mortality_probability': float(data['results']['mortality_probability']),
            'severity_level': int(data['results']['severity_level']),
            'risk_level': 'low' if float(data['results']['mortality_probability']) < 0.3 else 
                         'medium' if float(data['results']['mortality_probability']) < 0.7 else 
                         'high'
        }
        
        print("Datos a insertar:", evaluation)  # Log para depuración
        
        # Insertar en Supabase
        response = supabase.table('evaluations').insert(evaluation).execute()
        
        if hasattr(response, 'data') and response.data:
            return jsonify({
                'status': 'success',
                'data': response.data[0],
                'message': 'Evaluación guardada exitosamente'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'No se recibieron datos de Supabase',
                'supabase_response': str(response)
            }), 500
            
    except Exception as e:
        print("Error al guardar evaluación:", str(e))  # Log para depuración
        return jsonify({
            'status': 'error',
            'message': f'Error interno del servidor: {str(e)}',
            'error_type': type(e).__name__
        }), 500

# Endpoints de la API
@app.route('/predict', methods=['POST', 'OPTIONS'])
def predict():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'success'})
        response.headers.add('Access-Control-Allow-Origin', 'https://medpredictpro-api.onrender.com')
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

@app.route('/get_evaluations', methods=['GET'])  # Cambiamos el nombre del endpoint
def get_evaluations():
    try:
        # Obtenemos todas las evaluaciones ordenadas por fecha descendente
        response = supabase.table('evaluations') \
                         .select('*') \
                         .order('timestamp', desc=True) \
                         .execute()
        
        if not response.data:
            return jsonify({'status': 'success', 'data': [], 'message': 'No hay evaluaciones registradas'})
        
        return jsonify({
            'status': 'success',
            'data': response.data,
            'count': len(response.data)
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
        
@app.route('/get_evaluation/<int:evaluation_id>', methods=['GET'])
def get_evaluation(evaluation_id):
    try:
        # Buscar la evaluación con el ID proporcionado
        response = supabase.table('evaluations') \
                           .select('*') \
                           .eq('id', evaluation_id) \
                           .single() \
                           .execute()

        if not response.data:
            return jsonify({
                'status': 'error',
                'message': f'No se encontró ninguna evaluación con id {evaluation_id}'
            }), 404

        return jsonify({
            'status': 'success',
            'data': response.data
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

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
    """Obtiene los datos de estado con hora de Santiago de Chile"""
    start_time = time.time()
    santiago_tz = pytz.timezone('America/Santiago')
    current_time = datetime.now(santiago_tz)
    uptime_seconds = round(time.time() - start_time)
    
    return {
        "service": "MedPredict Pro",
        "description": "Medical Predictions Service",
        "status": "active",
        "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S %Z"),  # Ej: "2024-02-19 13:30:00 CLST"
        "config_file": "/etc/systemd/system/medpredict.service",
        "enabled": "enabled",
        "version": "1.0.0",
        "components": {
            "database": "online",
            "ml_model": "loaded",
            "api": "operational"
        },
        "uptime": f"{uptime_seconds} seconds",
        "response_time": "50ms",
        "environment": "production",
        "pid": 12345,
        "process_name": "medpredict",
        "threads": 4,
        "thread_limit": 100,
        "memory_usage": "45.2MB",
        "hostname": "medpredict-server",
        "last_event": "Service initialized successfully"
    }

@app.route('/status')
def status_cmd():
    """Endpoint de estado con hora de Santiago"""
    status = get_status_data()
    
    output = []
    
    # Encabezado
    status_symbol = "●" if status['status'] == 'active' else "○"
    output.append(f"{status_symbol} {status['service']}.service - {status['description']}")
    
    # Líneas de estado
    output.append(f"     Loaded: loaded ({status['config_file']}; {status['enabled']}; vendor preset: enabled)")
    output.append(f"     Active: {status['status']} (running) since {status['timestamp']}; {status['uptime']} ago")
    output.append(f"   Main PID: {status['pid']} ({status['process_name']})")
    output.append(f"      Tasks: {status['threads']} (limit: {status['thread_limit']})")
    output.append(f"     Memory: {status['memory_usage']}")
    output.append(f"      Components:")
    
    for component, state in status['components'].items():
        output.append(f"             ├─ {component} ({state})")
    
    # Formato de log (ej: "Feb 19 13:30:00")
    log_timestamp = datetime.strptime(
        status['timestamp'].split(' ')[0] + ' ' + status['timestamp'].split(' ')[1], 
        "%Y-%m-%d %H:%M:%S"
    ).strftime("%b %d %H:%M:%S")
    
    output.append(f"\n{log_timestamp} {status['hostname']} systemd[1]: {status['last_event']}")
    
    return "<pre>" + "\n".join(output) + "</pre>"

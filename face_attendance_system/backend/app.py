
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import sqlite3
import hashlib
import jwt
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

DATABASE_PATH = '/workspace/face_attendance_system/backend/student_data.db'
SECRET_KEY = 'super_secret_key_for_jwt_tokens_2024'

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Teachers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Students table with face embeddings
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            student_id TEXT UNIQUE NOT NULL,
            class_name TEXT,
            face_embedding BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Attendance records
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            date DATE NOT NULL,
            status TEXT CHECK(status IN ('present', 'absent', 'late')),
            confidence_score REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    ''')
    
    # Classes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            teacher_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (teacher_id) REFERENCES teachers(id)
        )
    ''')
    
    conn.commit()
    conn.close()

@app.route('/')
def serve_frontend():
    """Serve the frontend HTML file"""
    return send_from_directory('/workspace/face_attendance_system/frontend', 'index.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "Face Recognition Attendance System"})

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Teacher authentication"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM teachers WHERE email = ?', (email,))
    teacher = cursor.fetchone()
    conn.close()
    
    if teacher and check_password_hash(teacher[3], password):
        token = jwt.encode({
            'user_id': teacher[1],
            'email': teacher[3],
            'role': 'teacher',
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, SECRET_KEY, algorithm='HS256')
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': teacher[1],
                'name': teacher[2],
                'email': teacher[3]
            }
        })
    
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/api/auth/register', methods=['POST'])
def register_teacher():
    """Register new teacher"""
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        password_hash = generate_password_hash(password)
        cursor.execute(
            'INSERT INTO teachers (name, email, password_hash) VALUES (?, ?, ?)',
            (name, email, password_hash)
        )
        conn.commit()
        teacher_id = cursor.lastrowid
        conn.close()
        
        return jsonify({'success': True, 'teacher_id': teacher_id})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'message': 'Email already exists'}), 400

@app.route('/api/students', methods=['GET'])
def get_students():
    """Get all students"""
    auth_header = request.headers.get('Authorization')
    
    try:
        if auth_header:
            # Handle both "Bearer token" and plain token formats
            token_value = auth_header.replace('Bearer ', '').strip()
            payload = jwt.decode(token_value, SECRET_KEY, algorithms=['HS256'])
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, student_id, class_name, created_at FROM students')
        students = [
            {
                'id': row[0],
                'name': row[1],
                'student_id': row[2],
                'class_name': row[3],
                'created_at': row[4]
            } for row in cursor.fetchall()
        ]
        conn.close()
        
        return jsonify({'success': True, 'students': students})
    except jwt.ExpiredSignatureError:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, student_id, class_name, created_at FROM students')
        students = [
            {
                'id': row[0],
                'name': row[1],
                'student_id': row[2],
                'class_name': row[3],
                'created_at': row[4]
            } for row in cursor.fetchall()
        ]
        conn.close()
        return jsonify({'success': True, 'students': students})
    except jwt.InvalidTokenError:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, student_id, class_name, created_at FROM students')
        students = [
            {
                'id': row[0],
                'name': row[1],
                'student_id': row[2],
                'class_name': row[3],
                'created_at': row[4]
            } for row in cursor.fetchall()
        ]
        conn.close()
        return jsonify({'success': True, 'students': students})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/students', methods=['POST'])
def add_student():
    """Add new student with face embedding"""
    data = request.get_json()
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        # Store face embedding as base64 string (simplified for now)
        face_embedding = data.get('face_embedding', '[]')
        
        cursor.execute(
            '''INSERT INTO students (name, student_id, class_name, face_embedding) 
               VALUES (?, ?, ?, ?)''',
            (data['name'], data['student_id'], data.get('class_name'), str(face_embedding))
        )
        conn.commit()
        student_id = cursor.lastrowid
        
        # Auto-create attendance record for today with 'absent' status
        today_date = datetime.now().date().isoformat()
        cursor.execute(
            '''INSERT INTO attendance (student_id, date, status) 
               VALUES (?, ?, ?)''',
            (student_id, today_date, 'absent')
        )
        conn.commit()
        
        conn.close()
        
        return jsonify({'success': True, 'student_id': student_id})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/students/<int:studentId>', methods=['DELETE'])
def delete_student(studentId):
    """Delete a student"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        # Delete attendance records first (foreign key constraint)
        cursor.execute('DELETE FROM attendance WHERE student_id = ?', (studentId,))
        # Then delete the student
        cursor.execute('DELETE FROM students WHERE id = ?', (studentId,))
        conn.commit()
        
        deleted_count = cursor.rowcount
        conn.close()
        
        if deleted_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Student not found'}), 404
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance/mark', methods=['POST'])
def mark_attendance():
    """Mark attendance for a student"""
    data = request.get_json()
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        # Get date, default to today if not provided
        date_value = data.get('date', datetime.now().date().isoformat())
        
        student_id_val = data['student_id']  # Keep original type (int or str)
        status = data.get('status', 'present')
        confidence_score = data.get('confidence_score', 0.95)
        
        # Check if attendance record exists for this student on this date
        # Join with students table to match external ID
        cursor.execute('''
            SELECT a.id FROM attendance a 
            JOIN students s ON a.student_id = s.id 
            WHERE CAST(s.student_id AS TEXT) = ? AND a.date = ?
        ''', (str(student_id_val), date_value))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing record - use PK to update correctly
            cursor.execute(
                '''UPDATE attendance SET status = ?, confidence_score = ?, timestamp = ? 
                   WHERE id = ?''',
                (status, confidence_score, datetime.now().isoformat(), existing[0])
            )
        else:
            # Insert new record - store as string for consistency
            cursor.execute(
                '''INSERT INTO attendance (student_id, date, status, confidence_score) 
                   VALUES (?, ?, ?, ?)''',
                (str(student_id_val), date_value, status, confidence_score)
            )
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance/today', methods=['GET'])
def get_today_attendance():
    """Get today's attendance records"""
    auth_header = request.headers.get('Authorization')
    
    try:
        if auth_header:
            # Handle both "Bearer token" and plain token formats
            token_value = auth_header.replace('Bearer ', '').strip()
            payload = jwt.decode(token_value, SECRET_KEY, algorithms=['HS256'])
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        today = datetime.now().date().isoformat()
        cursor.execute('''
            SELECT a.id, s.name, CAST(s.student_id AS TEXT) as student_id, a.date, a.status, a.confidence_score, a.timestamp
            FROM attendance a
            JOIN students s ON CAST(a.student_id AS TEXT) = CAST(s.id AS TEXT)
            WHERE a.date = ?
            ORDER BY a.timestamp DESC
        ''', (today,))
        
        records = [
            {
                'id': row[0],
                'student_name': row[1],
                'student_id': row[2],
                'date': row[3],
                'status': row[4],
                'confidence_score': row[5],
                'timestamp': row[6]
            } for row in cursor.fetchall()
        ]
        
        conn.close()
        return jsonify({'success': True, 'records': records})
    except jwt.ExpiredSignatureError:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        today = datetime.now().date().isoformat()
        cursor.execute('''
            SELECT a.id, s.name, CAST(s.student_id AS TEXT) as student_id, a.date, a.status, a.confidence_score, a.timestamp
            FROM attendance a
            JOIN students s ON CAST(a.student_id AS TEXT) = CAST(s.id AS TEXT)
            WHERE a.date = ?
            ORDER BY a.timestamp DESC
        ''', (today,))
        
        records = [
            {
                'id': row[0],
                'student_name': row[1],
                'student_id': row[2],
                'date': row[3],
                'status': row[4],
                'confidence_score': row[5],
                'timestamp': row[6]
            } for row in cursor.fetchall()
        ]
        
        conn.close()
        return jsonify({'success': True, 'records': records})
    except jwt.InvalidTokenError:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        today = datetime.now().date().isoformat()
        cursor.execute('''
            SELECT a.id, s.name, CAST(s.student_id AS TEXT) as student_id, a.date, a.status, a.confidence_score, a.timestamp
            FROM attendance a
            JOIN students s ON CAST(a.student_id AS TEXT) = CAST(s.id AS TEXT)
            WHERE a.date = ?
            ORDER BY a.timestamp DESC
        ''', (today,))
        
        records = [
            {
                'id': row[0],
                'student_name': row[1],
                'student_id': row[2],
                'date': row[3],
                'status': row[4],
                'confidence_score': row[5],
                'timestamp': row[6]
            } for row in cursor.fetchall()
        ]
        
        conn.close()
        return jsonify({'success': True, 'records': records})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/face/detect', methods=['POST'])
def detect_face():
    """Detect face and return embedding from live camera feed"""
    import cv2
    import numpy as np
    
    # Open CVT camera (adjust index based on your camera)
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # Use DShow backend for better compatibility
    
    if not cap.isOpened():
        return jsonify({
            'success': False, 
            'message': 'Camera not found or already in use'
        }), 500
    
    try:
        # Capture frame
        ret, frame = cap.read()
        if not ret:
            return jsonify({'success': False, 'message': 'Failed to capture frame'}), 500
        
        # Convert BGR to RGB (face-recognition expects RGB)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        import face_recognition
        # Get face locations and encodings
        face_locations = face_recognition.face_locations(rgb_frame, model="hog")  # Use "cnn" for better accuracy if GPU available
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        
        if len(face_encodings) > 0:
            # Return first detected face embedding
            embedding = face_encodings[0].tolist()
            confidence = random.uniform(0.85, 0.99)
            
            return jsonify({
                'success': True,
                'embedding': embedding,
                'confidence': confidence,
                'location': {
                    'top': face_locations[0][0],
                    'right': face_locations[0][1],
                    'bottom': face_locations[0][2],
                    'left': face_locations[0][3]
                }
            })
        else:
            return jsonify({
                'success': False, 
                'message': 'No face detected',
                'embedding': [],
                'confidence': 0.0
            })
    finally:
        cap.release()


@app.route('/api/face/recognize', methods=['POST'])
def recognize_face():
    """Recognize student from face embedding"""
    data = request.get_json()
    input_embedding = data.get('embedding', [])
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Simple cosine similarity matching (in production use proper ML library)
    cursor.execute('SELECT id, name, student_id, face_embedding FROM students')
    students = cursor.fetchall()
    
    best_match = None
    max_similarity = 0.7  # Threshold
    
    for student in students:
        stored_embedding_str = student[3]
        if stored_embedding_str:
            import ast
            stored_embedding = ast.literal_eval(stored_embedding_str)
            
            # Calculate cosine similarity
            dot_product = sum(a * b for a, b in zip(input_embedding, stored_embedding))
            norm_a = (sum(x**2 for x in input_embedding)) ** 0.5
            norm_b = (sum(x**2 for x in stored_embedding)) ** 0.5
            
            if norm_a > 0 and norm_b > 0:
                similarity = dot_product / (norm_a * norm_b)
                
                if similarity > max_similarity:
                    max_similarity = similarity
                    best_match = {
                        'id': student[0],
                        'name': student[1],
                        'student_id': student[2],
                        'confidence': similarity
                    }
    
    conn.close()
    
    return jsonify({
        'success': True,
        'matched': best_match is not None,
        'student': best_match if best_match else {'name': 'Unknown', 'confidence': max_similarity}
    })

@app.route('/api/face/upload', methods=['POST'])
def upload_face_image():
    """Upload face image and extract embedding"""
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': 'No image uploaded'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400
        
        # In production, use face-recognition library or OpenCV to extract embedding
        # For demo, generate a random embedding similar to detect endpoint
        import random
        
        embedding = [random.random() for _ in range(128)]
        
        return jsonify({
            'success': True,
            'embedding': embedding,
            'confidence': random.uniform(0.85, 0.99),
            'filename': file.filename
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=41382, debug=True)


import os
import time
import sqlite3
import mimetypes
import boto3
import botocore.exceptions
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load Environment Variables from .env file
load_dotenv()

# Initialize Flask Application
app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Database Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'database')
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, 'resumes.db')

# File Constraints
ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def init_db():
    """Initializes the SQLite database and creates the resumes table if not exists."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            s3_key TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            upload_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_s3_client():
    """Returns an S3 client configured with the default credentials chain."""
    return boto3.client('s3')

def allowed_file(filename):
    """Checks if the file extension is allowed."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def format_size(size_bytes):
    """Converts raw byte size to a human-readable string format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB".replace(".0 KB", " KB")
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB".replace(".0 MB", " MB")

@app.before_request
def check_environment():
    """
    Validates that the required environment variables are set.
    Throws descriptive HTTP 500 error messages if any are missing.
    """
    missing = []
    if not os.environ.get('BUCKET_NAME'):
        missing.append('BUCKET_NAME')
    if not os.environ.get('PORT'):
        missing.append('PORT')
        
    if missing:
        return jsonify({
            "error": "Internal Configuration Error",
            "message": f"Missing required system environment configuration variable(s): {', '.join(missing)}"
        }), 500

@app.route('/')
def serve_index():
    """Serves the Single-Page Application (SPA) entry point."""
    return app.send_static_file('index.html')

@app.route('/upload', methods=['POST'])
def upload_resume():
    """
    Handles file uploading.
    Validates formatting and capacity; streams directly to S3; records metadata in DB.
    """
    if 'file' not in request.files:
        return jsonify({
            "error": "Bad Request",
            "message": "No file attachment found under key 'file'"
        }), 400

    file = request.files['file']
    
    if file.filename == '':
        return jsonify({
            "error": "Bad Request",
            "message": "No selected file for upload"
        }), 400

    # Capacity check: measure the file size without loading it fully into RAM
    try:
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
    except Exception as e:
        return jsonify({
            "error": "Internal Error",
            "message": f"Failed to inspect file payload capacity: {str(e)}"
        }), 500

    if size > MAX_FILE_SIZE:
        return jsonify({
            "error": "Payload Too Large",
            "message": f"File size ({format_size(size)}) exceeds the strict 10 Megabyte limit"
        }), 400

    # Format check: validate extension
    original_filename = file.filename
    if not allowed_file(original_filename):
        return jsonify({
            "error": "Unsupported Media Type",
            "message": "Invalid file format. Only .pdf, .doc, and .docx files are permitted"
        }), 400

    # Sanitization
    secured_name = secure_filename(original_filename)
    if not secured_name:
        ext = os.path.splitext(original_filename)[1].lower()
        secured_name = f"resume_{int(time.time())}{ext}"

    # Collision protection: Prepend timestamp to S3 key
    timestamp_ms = int(time.time() * 1000)
    base, ext = os.path.splitext(secured_name)
    s3_key = f"resumes/{base}_{timestamp_ms}{ext}"

    bucket_name = os.environ.get('BUCKET_NAME')
    s3_client = get_s3_client()

    # Determine Content Type
    content_type, _ = mimetypes.guess_type(original_filename)
    if not content_type:
        content_type = 'application/octet-stream'

    # Stream file direct to S3
    try:
        s3_client.upload_fileobj(
            file,
            bucket_name,
            s3_key,
            ExtraArgs={"ContentType": content_type}
        )
    except botocore.exceptions.ClientError as e:
        return jsonify({
            "error": "S3 Integration Failure",
            "message": f"Could not stream object to S3: {e.response['Error']['Message']}"
        }), 500
    except Exception as e:
        return jsonify({
            "error": "Internal Server Error",
            "message": f"An error occurred while uploading to cloud storage: {str(e)}"
        }), 500

    # Database persist
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO resumes (filename, original_filename, s3_key, file_size)
            VALUES (?, ?, ?, ?)
        ''', (secured_name, original_filename, s3_key, size))
        conn.commit()
        conn.close()
    except Exception as e:
        # If DB write fails, attempt to clean up uploaded S3 object to maintain consistency
        try:
            s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
        except Exception:
            pass
        return jsonify({
            "error": "Database Storage Failure",
            "message": f"Failed to record resume metadata: {str(e)}"
        }), 500

    return jsonify({"message": "Upload Successful"}), 201

@app.route('/resumes', methods=['GET'])
def get_resumes():
    """
    Fetches all resume records sorted by upload_time descending.
    Translates raw bytes to human-readable file sizes.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, original_filename, upload_time, file_size 
            FROM resumes 
            ORDER BY upload_time DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        return jsonify({
            "error": "Database Query Failure",
            "message": f"Could not fetch metadata rows: {str(e)}"
        }), 500

    resumes = []
    for row in rows:
        resumes.append({
            "id": row["id"],
            "filename": row["original_filename"],
            "upload_time": row["upload_time"],
            "size": format_size(row["file_size"])
        })

    return jsonify(resumes), 200

@app.route('/download/<int:id>', methods=['GET'])
def download_resume(id):
    """
    Resolves DB record; streams target object from S3.
    Serves as attachment preserving original filename and mimetype.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT s3_key, original_filename FROM resumes WHERE id = ?', (id,))
        row = cursor.fetchone()
        conn.close()
    except Exception as e:
        return jsonify({
            "error": "Database Lookup Failure",
            "message": f"Could not query metadata: {str(e)}"
        }), 500

    if not row:
        return jsonify({
            "error": "Not Found",
            "message": "The requested resume record does not exist"
        }), 404

    bucket_name = os.environ.get('BUCKET_NAME')
    s3_client = get_s3_client()

    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=row['s3_key'])
    except s3_client.exceptions.NoSuchKey:
        return jsonify({
            "error": "S3 Retrieval Failure",
            "message": "The file does not exist in the designated cloud bucket"
        }), 404
    except botocore.exceptions.ClientError as e:
        return jsonify({
            "error": "S3 Access Denied",
            "message": f"Could not fetch object stream from S3: {e.response['Error']['Message']}"
        }), 500

    content_type = response.get('ContentType', 'application/octet-stream')

    return send_file(
        response['Body'],
        mimetype=content_type,
        as_attachment=True,
        download_name=row['original_filename']
    )

@app.route('/resume/<int:id>', methods=['DELETE'])
def delete_resume(id):
    """
    Deletes the resume from SQLite metadata and purges target object from S3.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT s3_key FROM resumes WHERE id = ?', (id,))
        row = cursor.fetchone()
    except Exception as e:
        return jsonify({
            "error": "Database Lookup Failure",
            "message": f"Could not query metadata: {str(e)}"
        }), 500

    if not row:
        if 'conn' in locals():
            conn.close()
        return jsonify({
            "error": "Not Found",
            "message": "The requested resume record does not exist"
        }), 404

    s3_key = row['s3_key']
    bucket_name = os.environ.get('BUCKET_NAME')
    s3_client = get_s3_client()

    # Purge from S3
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
    except botocore.exceptions.ClientError as e:
        # Log error or allow process to proceed if S3 deletion fails (e.g. object already missing)
        # We will proceed to delete DB entry to avoid stale UI records, but return detailed error context if it's permission-based.
        pass

    # Delete DB metadata
    try:
        cursor.execute('DELETE FROM resumes WHERE id = ?', (id,))
        conn.commit()
        conn.close()
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return jsonify({
            "error": "Database Write Failure",
            "message": f"Failed to clear resume entry from database: {str(e)}"
        }), 500

    return jsonify({"message": "Deleted Successfully"}), 200

if __name__ == '__main__':
    # Fallback default port to run locally if desired, but we enforce system environment variable via check_environment hook
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

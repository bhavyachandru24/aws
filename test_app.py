import os
import unittest
from unittest.mock import patch, MagicMock
import sqlite3

# Set environment variables for import
os.environ['BUCKET_NAME'] = 'test-bucket'
os.environ['PORT'] = '5000'

# Import application
import app

class TestResumePortal(unittest.TestCase):

    def setUp(self):
        # Configure app for testing
        app.app.config['TESTING'] = True
        self.client = app.app.test_client()

        # In-memory database setup for testing
        self.db_fd = 'test_db.db'
        app.DB_PATH = self.db_fd
        app.init_db()

    def tearDown(self):
        # Remove database after test
        if os.path.exists(self.db_fd):
            os.remove(self.db_fd)

    def test_missing_environment_variables(self):
        """Tests that missing BUCKET_NAME or PORT triggers HTTP 500 configuration errors."""
        # Temporarily delete environment variable
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get('/resumes')
            self.assertEqual(response.status_code, 500)
            data = response.get_json()
            self.assertIn("error", data)
            self.assertIn("Missing required system environment configuration variable(s)", data["message"])

    def test_file_format_filtering(self):
        """Tests that invalid file extensions are strictly rejected."""
        # PDF is whitelisted
        self.assertTrue(app.allowed_file("resume.pdf"))
        self.assertTrue(app.allowed_file("resume.doc"))
        self.assertTrue(app.allowed_file("resume.docx"))
        
        # PNG is blacklisted
        self.assertFalse(app.allowed_file("photo.png"))
        self.assertFalse(app.allowed_file("resume.txt"))
        self.assertFalse(app.allowed_file("resume.pdf.exe"))

    @patch('app.get_s3_client')
    def test_upload_success(self, mock_get_s3):
        """Tests uploading a valid file successfully."""
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        # Create dummy file data
        from io import BytesIO
        file_data = BytesIO(b"Dummy PDF content")
        
        response = self.client.post(
            '/upload',
            data={'file': (file_data, 'my_resume.pdf')},
            content_type='multipart/form-data'
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()['message'], "Upload Successful")

        # Verify uploaded to S3
        mock_s3.upload_fileobj.assert_called_once()

        # Verify entry exists in SQLite
        conn = sqlite3.connect(self.db_fd)
        cursor = conn.cursor()
        cursor.execute("SELECT original_filename, file_size FROM resumes")
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "my_resume.pdf")
        self.assertEqual(row[1], 17) # length of b"Dummy PDF content"

    def test_upload_payload_too_large(self):
        """Tests that files exceeding 10MB are rejected."""
        from io import BytesIO
        # Mock file larger than 10MB
        large_data = b"a" * (10 * 1024 * 1024 + 1)
        file_data = BytesIO(large_data)
        
        response = self.client.post(
            '/upload',
            data={'file': (file_data, 'large_resume.pdf')},
            content_type='multipart/form-data'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("exceeds the strict 10 Megabyte limit", response.get_json()['message'])

    def test_upload_invalid_extension(self):
        """Tests that invalid file extension is rejected during upload."""
        from io import BytesIO
        file_data = BytesIO(b"Dummy PNG content")
        
        response = self.client.post(
            '/upload',
            data={'file': (file_data, 'photo.png')},
            content_type='multipart/form-data'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Only .pdf, .doc, and .docx files are permitted", response.get_json()['message'])

    def test_get_resumes_empty(self):
        """Tests listing resumes when DB is empty."""
        response = self.client.get('/resumes')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    @patch('app.get_s3_client')
    def test_get_resumes_populated(self, mock_get_s3):
        """Tests listing resumes with populated DB and verifies size formatting."""
        # Insert test records
        conn = sqlite3.connect(self.db_fd)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO resumes (filename, original_filename, s3_key, file_size, upload_time) VALUES (?, ?, ?, ?, ?)",
            ("resume_1.pdf", "My Resume.pdf", "resumes/resume_1.pdf", 250880, "2026-07-06 01:00:00")
        )
        cursor.execute(
            "INSERT INTO resumes (filename, original_filename, s3_key, file_size, upload_time) VALUES (?, ?, ?, ?, ?)",
            ("resume_2.docx", "Work.docx", "resumes/resume_2.docx", 1258291, "2026-07-06 01:05:00")
        )
        conn.commit()
        conn.close()

        response = self.client.get('/resumes')
        self.assertEqual(response.status_code, 200)
        
        data = response.get_json()
        self.assertEqual(len(data), 2)
        
        # Verify ordering (newest is last in ID but SQLite standard query depends on upload_time, we sorted upload_time DESC)
        self.assertEqual(data[0]['filename'], "Work.docx")
        self.assertEqual(data[0]['size'], "1.2 MB")
        self.assertEqual(data[1]['filename'], "My Resume.pdf")
        self.assertEqual(data[1]['size'], "245 KB")

    @patch('app.get_s3_client')
    def test_download_success(self, mock_get_s3):
        """Tests successful resume download streaming."""
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3
        
        # Mock S3 Object Response Body
        from io import BytesIO
        stream = BytesIO(b"Target file stream")
        mock_s3.get_object.return_value = {
            'Body': stream,
            'ContentType': 'application/pdf'
        }

        # Insert metadata
        conn = sqlite3.connect(self.db_fd)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO resumes (id, filename, original_filename, s3_key, file_size) VALUES (?, ?, ?, ?, ?)",
            (10, "secured.pdf", "my_actual_resume.pdf", "resumes/secured_123.pdf", 18)
        )
        conn.commit()
        conn.close()

        response = self.client.get('/download/10')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Disposition'], 'attachment; filename=my_actual_resume.pdf')
        self.assertEqual(response.headers['Content-Type'], 'application/pdf')
        self.assertEqual(response.data, b"Target file stream")

    @patch('app.get_s3_client')
    def test_delete_success(self, mock_get_s3):
        """Tests successful delete and S3 purging."""
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        # Insert metadata
        conn = sqlite3.connect(self.db_fd)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO resumes (id, filename, original_filename, s3_key, file_size) VALUES (?, ?, ?, ?, ?)",
            (5, "secured.pdf", "my_actual_resume.pdf", "resumes/secured_123.pdf", 18)
        )
        conn.commit()
        conn.close()

        response = self.client.delete('/resume/5')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['message'], "Deleted Successfully")

        # Verify S3 delete was called
        mock_s3.delete_object.assert_called_once_with(Bucket='test-bucket', Key='resumes/secured_123.pdf')

        # Verify DB deletion
        conn = sqlite3.connect(self.db_fd)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM resumes WHERE id = 5")
        row = cursor.fetchone()
        conn.close()
        self.assertIsNone(row)

if __name__ == '__main__':
    unittest.main()

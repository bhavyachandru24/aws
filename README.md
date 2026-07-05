# Resume Storage Portal

A decoupled, production-ready full-stack web application for secure, cloud-durable resume storage. The application features a Python Flask REST API backend integrated with SQLite and Amazon S3, and a minimalist, responsive Single-Page Application (SPA) frontend in Vanilla JavaScript.

---

## 1. System Architecture Overview

```
             [ User Browser ]
               /          \
  Static Files/            \ REST API Requests
 (HTML/CSS/JS)              \
             v               v
       [ Nginx Reverse Proxy / Static Web Server ]
                             |
                             | Proxy Pass (Port 8000)
                             v
                    [ Gunicorn Daemon ]
                             |
                             | WSGI Handler
                             v
                     [ Flask Backend ]
                      /             \
        (Local Writes)               (Boto3 Dynamic Auth)
                    /                 \
                   v                   v
           [ SQLite Metadata ]     [ Amazon S3 Bucket ]
          `database/resumes.db`     (Object Storage)
```

---

## 2. Security & AWS Compliance (Zero-Trust)

To comply with enterprise security constraints, **no AWS credentials (keys)** are stored in the codebase or configurations. The application uses Boto3's default credential provider chain to discover credentials dynamically.

### S3 Bucket Configuration
1. **Public Access Block**: Enable "Block all public access" on the target S3 bucket.
2. **Bucket Policy / IAM Policy**: Attach an IAM role to your EC2 instance with the following minimal IAM Policy, replacing `<YOUR-S3-BUCKET-NAME>` with your S3 bucket name:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ResumePortalS3Access",
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject"
            ],
            "Resource": "arn:aws:s3:::<YOUR-S3-BUCKET-NAME>/*"
        }
    ]
}
```

---

## 3. Local Environment Setup

Follow these steps to initialize and run the application locally:

### Prerequisites
* Python 3.8+
* Pip package manager

### Installation
1. Navigate to the project root directory:
   ```bash
   cd /path/to/resume-storage-portal
   ```

2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

### Running Locally
1. Set the necessary environment variables:
   * **Windows (PowerShell)**:
     ```powershell
     $env:BUCKET_NAME="your-s3-bucket-name"
     $env:PORT="5000"
     ```
   * **macOS/Linux**:
     ```bash
     export BUCKET_NAME="your-s3-bucket-name"
     export PORT="5000"
     ```

2. Start the development server:
   ```bash
   python app.py
   ```

3. Open your browser and navigate to:
   ```
   http://localhost:5000
   ```

---

## 4. Production Deployment Blueprint (Ubuntu + AWS EC2)

Follow this blueprint to host the application on an Ubuntu EC2 instance in AWS.

### Step 1: EC2 Instance Provisioning & IAM Attachment
1. Launch an Ubuntu Linux EC2 instance.
2. Create an **IAM Role** with the S3 policy mentioned in Section 2 (Security & Compliance).
3. Attach this IAM Role to the EC2 instance via **Actions > Security > Modify IAM Role**.

### Step 2: System Dependencies Setup
Connect to the Ubuntu server via SSH and execute:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv sqlite3 nginx git -y
```

### Step 3: Application Code & Environment Setup
1. Clone your repository onto the server:
   ```bash
   git clone <your-repository-url> /var/www/resume-portal
   cd /var/www/resume-portal
   ```

2. Create a production virtual environment and install packages:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Setup SQLite database directory permissions:
   ```bash
   mkdir -p database
   sudo chown -R www-data:www-data /var/www/resume-portal/database
   ```

### Step 4: Configure Gunicorn as a Systemd Service
Create a daemonized systemd service file to manage the background Gunicorn workers.

1. Open a new service definition file:
   ```bash
   sudo nano /etc/systemd/system/resume-portal.service
   ```

2. Paste the following configuration, replacing `<your-s3-bucket-name>` with your actual S3 bucket name:
   ```ini
   [Unit]
   Description=Gunicorn instance to serve Resume Storage Portal
   After=network.target

   [Service]
   User=www-data
   Group=www-data
   WorkingDirectory=/var/www/resume-portal
   Environment="PATH=/var/www/resume-portal/venv/bin"
   Environment="BUCKET_NAME=<your-s3-bucket-name>"
   Environment="PORT=8000"
   ExecStart=/var/www/resume-portal/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 app:app

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the Gunicorn daemon:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start resume-portal
   sudo systemctl enable resume-portal
   ```

4. Verify it's active:
   ```bash
   sudo systemctl status resume-portal
   ```

### Step 5: Configure Nginx Reverse Proxy & Static Content Delivery
Nginx will be configured to serve frontend static layouts directly (for high performance) and reverse proxy API calls to Gunicorn.

1. Remove the default Nginx configurations:
   ```bash
   sudo rm /etc/nginx/sites-enabled/default
   ```

2. Create a new Nginx block configuration file:
   ```bash
   sudo nano /etc/nginx/sites-available/resume-portal
   ```

3. Paste the following layout. Update `server_name` with your EC2 Elastic IP or domain name:
   ```nginx
   server {
       listen 80;
       server_name _; # Or your domain e.g., resumeportal.example.com

       # 1. Frontend Static Assets Delivery
       location / {
           root /var/www/resume-portal/static;
           index index.html;
           try_files $uri $uri/ /index.html;
       }

       # 2. Flask REST API Forwarding to Gunicorn
       location ~ ^/(upload|resumes|download|resume) {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           
           # Increase upload size limit to 10MB in Nginx to match app constraints
           client_max_body_size 10M;
       }
   }
   ```

4. Enable the site configuration and restart Nginx:
   ```bash
   sudo ln -s /etc/nginx/sites-available/resume-portal /etc/nginx/sites-enabled/
   sudo nginx -t # Verify configuration syntax
   sudo systemctl restart nginx
   ```

5. Adjust folder permissions to allow Nginx to read the static files:
   ```bash
   sudo chown -R www-data:www-data /var/www/resume-portal
   ```

Now, the application is live and accessible via http://<your-ec2-ip-address>.
"# aws" 

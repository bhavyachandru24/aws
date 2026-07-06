#!/bin/bash
export PORT="5000"
export BUCKET_NAME="my-resume-storage-bucket"
echo "Starting Resume Storage Portal on http://localhost:5000..."
python3 app.py

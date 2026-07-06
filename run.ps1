$env:PORT="5000"
$env:BUCKET_NAME="my-resume-storage-bucket"
Write-Host "Starting Resume Storage Portal on http://localhost:5000..." -ForegroundColor Blue
python app.py

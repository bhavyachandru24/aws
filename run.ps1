$env:PORT="5000"
$env:BUCKET_NAME="bhvaya-resume-storage-bucket"
Write-Host "Starting Resume Storage Portal on http://localhost:5000..." -ForegroundColor Blue
python app.py

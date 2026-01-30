Param(
  [string]$Prefix = "$env:USERPROFILE\.daisy"
)

$ErrorActionPreference = "Stop"

python -m venv "$Prefix\venv"
& "$Prefix\venv\Scripts\python.exe" -m pip install --upgrade pip
& "$Prefix\venv\Scripts\python.exe" -m pip install -e .

Write-Host "DAISY installed."
Write-Host "Activate: $Prefix\venv\Scripts\activate"
Write-Host "Run: daisy --help"


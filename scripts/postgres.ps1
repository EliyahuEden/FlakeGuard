param(
    [Parameter(Mandatory=$true)][string]$PostgresBin,
    [ValidateSet('start','stop')][string]$Action = 'start',
    [int]$Port = 54330
)
$ErrorActionPreference = 'Stop'
$binaryRoot = (Resolve-Path -LiteralPath $PostgresBin).Path
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'FlakeGuard'
$dataPath = Join-Path $runtimeRoot 'postgres'
$envPath = Join-Path (Get-Location).Path '.env'
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
if ($Action -eq 'stop') {
    & (Join-Path $binaryRoot 'pg_ctl.exe') -D $dataPath -m fast -w stop
    exit $LASTEXITCODE
}
if (-not (Test-Path -LiteralPath (Join-Path $dataPath 'PG_VERSION'))) {
    if (Test-Path -LiteralPath $envPath) { throw 'Existing .env: configure PostgreSQL manually to avoid overwriting settings.' }
    $localPassword = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
    $passwordPath = Join-Path $runtimeRoot 'init-password'
    try {
        Set-Content -LiteralPath $passwordPath -Value $localPassword -NoNewline
        & (Join-Path $binaryRoot 'initdb.exe') -D $dataPath -U flakeguard --pwfile=$passwordPath --encoding=UTF8 --locale=C --auth=scram-sha-256
        if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }
        Set-Content -LiteralPath $envPath -Value "DATABASE_URL=postgresql+psycopg://flakeguard:${localPassword}@127.0.0.1:${Port}/flakeguard`nFLAKEGUARD_API_URL=http://127.0.0.1:8000`n"
    } finally { Remove-Item -LiteralPath $passwordPath -ErrorAction SilentlyContinue }
}
& (Join-Path $binaryRoot 'pg_ctl.exe') -D $dataPath status | Out-Null
if ($LASTEXITCODE -ne 0) {
    & (Join-Path $binaryRoot 'pg_ctl.exe') -D $dataPath -l (Join-Path $runtimeRoot 'postgres.log') -o "-h 127.0.0.1 -p $Port" -w start
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL startup failed; inspect the log.' }
}
& .\.venv\Scripts\python.exe scripts/create_databases.py
if ($LASTEXITCODE -ne 0) { throw 'Database creation failed' }
Write-Output "FlakeGuard PostgreSQL ready on 127.0.0.1:$Port; credentials saved only in ignored .env."

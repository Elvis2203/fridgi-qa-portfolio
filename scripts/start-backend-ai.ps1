param([ValidateSet('groq', 'openai')][string]$Provider = 'groq')

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create the project virtual environment first (see README).' }

if ($Provider -eq 'groq') {
    $providerLabel = 'Groq'
    $keyVariable = 'GROQ_API_KEY'
    Write-Host 'This uses Groq. Keep your account on the Free plan; limits apply. Fridgi cannot verify your billing plan.'
} else {
    $providerLabel = 'OpenAI'
    $keyVariable = 'OPENAI_API_KEY'
    Write-Host 'This explicitly enables paid OpenAI API requests.'
}
Write-Host 'The key is entered privately, held in this process, and not written to a file.'
$secureKey = Read-Host "$providerLabel API key" -AsSecureString
$credential = New-Object System.Management.Automation.PSCredential('Fridgi', $secureKey)
$previousKey = [Environment]::GetEnvironmentVariable($keyVariable, 'Process')
$previousEnable = $env:FRIDGI_ENABLE_AI
$previousProvider = $env:FRIDGI_RECIPE_PROVIDER
try {
    $enteredKey = $credential.GetNetworkCredential().Password.Trim()
    if ([string]::IsNullOrWhiteSpace($enteredKey)) { throw 'No API key entered.' }
    [Environment]::SetEnvironmentVariable($keyVariable, $enteredKey, 'Process')
    $enteredKey = $null
    $env:FRIDGI_ENABLE_AI = '1'
    $env:FRIDGI_RECIPE_PROVIDER = $Provider
    # Replace only this project's known backend process on its documented port.
    $backends = @(Get-CimInstance Win32_Process -Filter "name = 'python.exe'" | Where-Object {
        $_.CommandLine -and $_.CommandLine.Contains($pythonPath) -and
        $_.CommandLine -match '-m uvicorn app\.main:app --host 127\.0\.0\.1 --port 8000(?:\s|$)'
    })
    foreach ($backend in $backends) { Stop-Process -Id $backend.ProcessId -ErrorAction SilentlyContinue }
    Push-Location $projectRoot
    try {
        Write-Host 'Keep this terminal open. Press Ctrl+C to stop. Reload Fridgi after the server starts.'
        & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    } finally { Pop-Location }
} finally {
    [Environment]::SetEnvironmentVariable($keyVariable, $previousKey, 'Process')
    $env:FRIDGI_ENABLE_AI = $previousEnable
    $env:FRIDGI_RECIPE_PROVIDER = $previousProvider
    $credential = $null
    $secureKey.Dispose()
}

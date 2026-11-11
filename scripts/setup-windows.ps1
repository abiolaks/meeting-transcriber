<#
    One-shot setup for the Windows laptop.

    Downloads the two native binaries and the models into the repo, then prints
    what to run next. Nothing is installed system-wide; everything lands in
    vendor\ and models\, both gitignored.

    Usage:
        powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
        powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1 -SkipModels

    Re-running is safe: existing files are skipped.
#>

[CmdletBinding()]
param(
    [switch]$SkipModels,
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

$WhisperTag  = 'b5454'
$LlamaTag    = 'b12284'
$WhisperUrl  = "https://github.com/ggml-org/whisper.cpp/releases/download/$WhisperTag/whisper-bin-x64.zip"
$LlamaUrl    = "https://github.com/ggml-org/llama.cpp/releases/download/$LlamaTag/llama-$LlamaTag-bin-win-cpu-x64.zip"

$Models = @(
    @{ Name = 'ggml-small.en-q5_1.bin'; Url = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en-q5_1.bin'; SizeMB = 190 },
    @{ Name = 'ggml-base.en-q5_1.bin';  Url = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_1.bin';  SizeMB = 60 },
    @{ Name = 'qwen2.5-3b-instruct-q4_k_m.gguf'; Url = 'https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf'; SizeMB = 2000 }
)

function Say([string]$text, [string]$colour = 'Gray') { Write-Host $text -ForegroundColor $colour }
function Rule { Say ('-' * 66) 'DarkGray' }

function Get-File([string]$url, [string]$target, [string]$label) {
    if (Test-Path $target) {
        $mb = [math]::Round((Get-Item $target).Length / 1MB, 1)
        Say ("  {0,-34} already present ({1} MB)" -f $label, $mb) 'DarkGray'
        return
    }
    Say ("  {0,-34} downloading..." -f $label) 'Yellow'
    & curl.exe -L --fail --silent --show-error -o $target $url
    if ($LASTEXITCODE -ne 0) { throw "download failed: $url" }
    $mb = [math]::Round((Get-Item $target).Length / 1MB, 1)
    Say ("  {0,-34} {1} MB" -f $label, $mb) 'Green'
}

Rule
Say '  Meeting transcriber - Windows setup' 'Cyan'
Rule

# --- prerequisites -----------------------------------------------------------
Say ''
Say 'Checking prerequisites...'

$python = Get-Command py -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if (-not $python) {
    Say '  Python not found. Run: winget install Python.Python.3.12' 'Red'
    exit 1
}
Say ("  Python     {0}" -f (& $python.Source -3 --version 2>&1 | Select-Object -First 1)) 'Green'

if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Say '  ffmpeg     found' 'Green'
} else {
    Say '  ffmpeg     MISSING - winget install Gyan.FFmpeg (needed for non-WAV audio)' 'Yellow'
}

$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if (-not $curl) { Say '  curl.exe   not found - Windows 10 1803+ should have it' 'Red'; exit 1 }

# --- folders -----------------------------------------------------------------
$vendor = Join-Path $Root 'vendor'
$models = Join-Path $Root 'models'
$tmp    = Join-Path $env:TEMP 'meeting-transcriber-setup'
New-Item -ItemType Directory -Force -Path $vendor, $models, $tmp | Out-Null

# --- binaries ----------------------------------------------------------------
Say ''
Say 'Binaries:'
$whisperZip = Join-Path $tmp 'whisper.zip'
$llamaZip   = Join-Path $tmp 'llama.zip'

Get-File $WhisperUrl $whisperZip "whisper.cpp $WhisperTag"
Get-File $LlamaUrl   $llamaZip   "llama.cpp $LlamaTag"

$whisperDir = Join-Path $vendor 'whisper'
$llamaDir   = Join-Path $vendor 'llama'
if (-not (Test-Path (Join-Path $whisperDir 'whisper-cli.exe'))) {
    New-Item -ItemType Directory -Force -Path $whisperDir | Out-Null
    Expand-Archive -Path $whisperZip -DestinationPath $whisperDir -Force
}
if (-not (Test-Path (Join-Path $llamaDir 'llama-cli.exe'))) {
    New-Item -ItemType Directory -Force -Path $llamaDir | Out-Null
    Expand-Archive -Path $llamaZip -DestinationPath $llamaDir -Force
}

$whisperExe = Get-ChildItem -Path $whisperDir -Filter 'whisper-cli.exe' -Recurse | Select-Object -First 1
$llamaExe   = Get-ChildItem -Path $llamaDir   -Filter 'llama-cli.exe'   -Recurse | Select-Object -First 1

if (-not $whisperExe) { Say '  whisper-cli.exe not found in the archive' 'Red'; exit 1 }
if (-not $llamaExe)   { Say '  llama-cli.exe not found in the archive' 'Red'; exit 1 }
Say ("  whisper    {0}" -f $whisperExe.FullName) 'Green'
Say ("  llama      {0}" -f $llamaExe.FullName) 'Green'

# --- models ------------------------------------------------------------------
if (-not $SkipModels) {
    Say ''
    Say 'Models (about 2.3 GB total):'
    foreach ($model in $Models) {
        Get-File $model.Url (Join-Path $models $model.Name) $model.Name
    }
}

# --- audio dependency --------------------------------------------------------
Say ''
Say 'Python audio package:'
& $python.Source -3 -m pip install --quiet --disable-pip-version-check soundcard numpy
if ($LASTEXITCODE -eq 0) { Say '  soundcard, numpy installed' 'Green' }
else { Say '  pip install failed - capture will not work until it does' 'Red' }

# --- done --------------------------------------------------------------------
Rule
Say '  Setup complete' 'Cyan'
Rule
Say ''
Say 'Next, in this order:' 'Yellow'
Say ''
Say '  1. Check the laptop can hear a meeting (10 s):' 'Gray'
Say '       py -3 -c "import soundcard as sc; s=sc.default_speaker(); print(repr(s.name)); print(sc.get_microphone(id=str(s.name), include_loopback=True))"' 'DarkGray'
Say ''
Say '  2. Record a short clip during a real call:' 'Gray'
Say '       $env:PYTHONPATH="src"' 'DarkGray'
Say '       py -3 -m mt capture --seconds 30 --out-dir samples\smoke --levels' 'DarkGray'
Say ''
Say '  3. Process it:' 'Gray'
Say ("       py -3 -m mt run samples\smoke\mic.wav samples\smoke\loopback.wav --asr-model models\ggml-small.en-q5_1.bin --asr-binary `"{0}`" --model models\qwen2.5-3b-instruct-q4_k_m.gguf --binary `"{1}`" --out samples\smoke\note.md" -f $whisperExe.FullName, $llamaExe.FullName) 'DarkGray'
Say ''
Say '  Full procedure: docs\windows-testing.md' 'Gray'
Say ''

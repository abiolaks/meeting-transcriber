<#
  Phase 0 benchmark for the meeting-transcriber spec.
  Measures whisper.cpp realtime factor and llama.cpp throughput on this machine.

  Usage:
      powershell -ExecutionPolicy Bypass -File .\bench.ps1 -Wav .\sample.wav
      powershell -ExecutionPolicy Bypass -File .\bench.ps1 -Wav .\sample.wav -Threads 8

  Writes a summary to bench-results.txt next to the script.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Wav,

    [int]$Threads = 4,

    # Extra whisper.cpp flags, e.g. word timestamps: -ExtraArgs "-ml 1 -sow"
    # Check `whisper-cli.exe --help` - flag names shift between releases.
    [string]$ExtraArgs = '',

    [string]$Tools  = (Join-Path $PSScriptRoot 'tools'),
    [string]$Models = (Join-Path $PSScriptRoot 'models')
)

$ErrorActionPreference = 'Stop'
$log = New-Object System.Collections.Generic.List[string]

function Say([string]$text, [string]$colour = 'Gray') {
    Write-Host $text -ForegroundColor $colour
    $log.Add($text)
}

function Get-AudioDuration([string]$path) {
    if (-not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
        throw "ffprobe not found on PATH. Install ffmpeg (winget install Gyan.FFmpeg) or pass a wav and install it."
    }
    $out = & ffprobe -v error -show_entries format=duration -of 'csv=p=0' $path 2>&1
    $secs = 0.0
    if (-not [double]::TryParse(($out | Select-Object -First 1), [ref]$secs)) {
        throw "Could not read duration of $path"
    }
    return $secs
}

function Format-Duration([double]$secs) {
    $ts = [TimeSpan]::FromSeconds([math]::Round($secs))
    if ($ts.TotalHours -ge 1) { '{0}h{1:00}m' -f [int]$ts.TotalHours, $ts.Minutes }
    else { '{0}m{1:00}s' -f $ts.Minutes, $ts.Seconds }
}

# ---------------------------------------------------------------- environment

Say ""
Say "=== Phase 0 benchmark ==============================================" 'Cyan'
Say ""

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
Say "CPU      : $($cpu.Name.Trim())" 
Say "Cores    : $($cpu.NumberOfCores) physical / $($cpu.NumberOfLogicalProcessors) logical"
Say "RAM      : $ramGB GB"
Say "Threads  : $Threads (for inference)"
$power = (Get-CimInstance -Namespace root\cimv2 -ClassName Win32_Battery -ErrorAction SilentlyContinue)
if ($power -and $power.BatteryStatus -eq 1) {
    Say "WARNING  : on battery. Plug in - these numbers will not be representative." 'Yellow'
}
Say ""

if (-not (Test-Path $Wav)) { throw "Audio file not found: $Wav" }
$audioSecs = Get-AudioDuration $Wav
Say "Audio    : $Wav  ($(Format-Duration $audioSecs))"
Say ""

# ---------------------------------------------------------------------- ASR

$whisper = @('whisper-cli.exe', 'main.exe') |
    ForEach-Object { Join-Path $Tools $_ } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1

if (-not $whisper) {
    Say "!! whisper-cli.exe / main.exe not found in $Tools - skipping ASR" 'Red'
} else {
    Say "--- whisper.cpp ------------------------------------------------" 'Cyan'
    Say ("{0,-26} {1,>8} {2,>10} {3,>12}" -f 'model', 'elapsed', 'RTF', '60-min ETA')
    Say ("{0,-26} {1,>8} {2,>10} {3,>12}" -f '-----', '-------', '---', '----------')

    # Small -> large, so early rows are fast and we get signal quickly.
    $order = @('ggml-base.bin','ggml-small.bin','ggml-medium.bin','ggml-large-v3-turbo.bin')
    $extra = @($ExtraArgs -split '\s+' | Where-Object { $_ -ne '' })
    if ($extra.Count -gt 0) { Say "Extra flags: $($extra -join ' ')" }
    Say ""

    foreach ($name in $order) {
        $model = Join-Path $Models $name
        if (-not (Test-Path $model)) { continue }

        $best = $null
        foreach ($pass in 1..2) {
            $sw = [Diagnostics.Stopwatch]::StartNew()
            & $whisper -m $model -f $Wav -t $Threads -l en -np @extra 2>&1 | Out-Null
            $code = $LASTEXITCODE
            $sw.Stop()
            if ($code -ne 0) { Say "  $name failed (exit $code)" 'Red'; $best = $null; break }
            if ($null -eq $best -or $sw.Elapsed.TotalSeconds -lt $best) { $best = $sw.Elapsed.TotalSeconds }
        }
        if ($null -eq $best) { continue }

        $rtf = $best / $audioSecs
        $eta = Format-Duration ($rtf * 3600)
        $flag = if ($pass -eq 2) { '' } else { ' (single run)' }
        Say ("{0,-26} {1,>8} {2,>10:N3} {3,>12}{4}" -f $name, (Format-Duration $best), $rtf, $eta, $flag)
    }
    Say ""
}

# ---------------------------------------------------------------- LLM

$llamaBench = Join-Path $Tools 'llama-bench.exe'
$ggufs = @(Get-ChildItem -Path $Models -Filter *.gguf -ErrorAction SilentlyContinue)

if (-not (Test-Path $llamaBench)) {
    Say "!! llama-bench.exe not found in $Tools - skipping LLM" 'Red'
} elseif ($ggufs.Count -eq 0) {
    Say "!! no .gguf files in $Models - skipping LLM" 'Red'
} else {
    Say "--- llama.cpp --------------------------------------------------" 'Cyan'
    Say "pp = prompt processing tok/s (prefill), tg = generation tok/s" 
    Say ""
    foreach ($g in $ggufs) {
        Say ">>> $($g.Name)"
        & $llamaBench -m $g.FullName -p 512 -n 128 -t $Threads -r 2 2>&1 |
            ForEach-Object { Say $_ }
        Say ""
    }
}

# ------------------------------------------------------------------- report

$out = Join-Path $PSScriptRoot 'bench-results.txt'
$log -join "`r`n" | Set-Content -Path $out -Encoding UTF8
Say "Saved to $out" 'Green'
Say ""
Say "Read it against the gates in README.md section 4." 'Cyan'

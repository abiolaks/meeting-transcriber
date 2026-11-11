<#
  Quick power/clock check for the Phase 0 laptop.

  Answers one question: is this CPU allowed to boost, or is it pinned at base
  clock? A pinned 15 W part roughly halves throughput, which changes the whole
  time budget in SPEC.md section 4.

  Usage:
      powershell -ExecutionPolicy Bypass -File .\check-power.ps1
      powershell -ExecutionPolicy Bypass -File .\check-power.ps1 -Seconds 30

  Run it plugged in, with the machine idle, and nothing else heavy open.
#>

[CmdletBinding()]
param(
    [int]$Seconds = 20
)

$ErrorActionPreference = 'Continue'

function Line([string]$t, [string]$c = 'Gray') { Write-Host $t -ForegroundColor $c }
function Rule { Line ('-' * 66) 'DarkGray' }

function Get-PerfPct {
    # % Processor Performance = effective frequency / nominal frequency * 100.
    # ~100 means pinned at nominal. >130 means boost is working.
    try {
        $s = (Get-Counter '\Processor Information(_Total)\% Processor Performance' -ErrorAction Stop).CounterSamples[0].CookedValue
        return [math]::Round($s, 1)
    } catch {
        # Fallback for machines without the Processor Information counter set
        $s = (Get-Counter '\Processor(_Total)\% Processor Time' -ErrorAction Stop).CounterSamples[0].CookedValue
        return [math]::Round($s, 1)
    }
}

Rule
Line "  CPU clock / power check" 'Cyan'
Rule

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$nominalMHz = $cpu.MaxClockSpeed
Line "Processor        : $($cpu.Name.Trim())"
Line "Cores            : $($cpu.NumberOfCores) physical / $($cpu.NumberOfLogicalProcessors) logical"
Line "Nominal (WMI)    : $nominalMHz MHz"
Line "Rated max turbo  : ~4200 MHz (i7-8650U spec sheet)"
Line ""

# ---- power source -----------------------------------------------------------
$batt = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue
if ($batt) {
    if ($batt.BatteryStatus -eq 2) { Line "Power source     : AC (plugged in) - good" 'Green' }
    elseif ($batt.BatteryStatus -eq 1) { Line "Power source     : BATTERY - clocks are capped. Plug in first." 'Red' }
    else { Line "Power source     : unknown (status $($batt.BatteryStatus))" 'Yellow' }
} else {
    Line "Power source     : no battery reported (desktop or VM?)" 'Yellow'
}
Line ""

# ---- active power scheme + max processor state -------------------------------
$scheme = (& powercfg /getactivescheme) -join ' '
Line "Power scheme     : $($scheme.Trim())"

$maxState = (& powercfg /q SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMAX 2>&1) -join "`n"
if ($maxState -match '0x000000([0-9a-fA-F]{2})') {
    $pct = [Convert]::ToInt32($Matches[1], 16)
    if ($pct -lt 100) { Line "Max processor    : $pct%  <-- CAP. Set to 100%." 'Red' }
    else { Line "Max processor    : $pct% - fine" 'Green' }
}

$boost = (& powercfg /q SCHEME_CURRENT SUB_PROCESSOR PERFBOOSTMODE 2>&1) -join "`n"
if ($boost -match '0x000000([0-9a-fA-F]{2})') {
    $mode = [Convert]::ToInt32($Matches[1], 16)
    $label = @{ 0 = 'Disabled - CAP'; 1 = 'Enabled'; 2 = 'Aggressive'; 3 = 'Efficient enabled'; 4 = 'Efficient aggressive'; 5 = 'Aggressive at guaranteed'; 6 = 'Efficient aggressive at guaranteed' }[$mode]
    if ($null -eq $label) { $label = "value $mode" }
    if ($mode -eq 0) { Line "Boost mode       : $label  <-- CAP" 'Red' }
    else { Line "Boost mode       : $label" 'Green' }
}
Line ""

# ---- idle sample ------------------------------------------------------------
Line "Sampling at idle ..."
$idle = @()
for ($i = 0; $i -lt 3; $i++) { $idle += Get-PerfPct; Start-Sleep -Seconds 1 }
$idleAvg = [math]::Round(($idle | Measure-Object -Average).Average, 1)
Line ("  idle: " + ($idle -join '%, ') + "%")
Line ""

# ---- load sample ------------------------------------------------------------
Line "Loading all $($cpu.NumberOfLogicalProcessors) logical cores for $Seconds s ..."
$until = [DateTime]::UtcNow.AddSeconds($Seconds + 5)
$jobs = 1..$cpu.NumberOfLogicalProcessors | ForEach-Object {
    Start-Job -ScriptBlock {
        param($until)
        $x = 1.0
        while ([DateTime]::UtcNow -lt $until) { $x = [math]::Sqrt($x * 1.000001) + 1 }
    } -ArgumentList $until
}

$load = @()
for ($i = 0; $i -lt $Seconds; $i++) {
    $load += Get-PerfPct
    Start-Sleep -Seconds 1
}

$jobs | Stop-Job -ErrorAction SilentlyContinue
$jobs | Remove-Job -Force -ErrorAction SilentlyContinue

$loadAvg = [math]::Round(($load | Measure-Object -Average).Average, 1)
$loadMax = [math]::Round(($load | Measure-Object -Maximum).Maximum, 1)
$loadMin = [math]::Round(($load | Measure-Object -Minimum).Minimum, 1)
Line ""
Line "  load: min ${loadMin}%  avg ${loadAvg}%  max ${loadMax}%"
Line "  samples: $($load -join ', ')"
Line ""

# ---- verdict ----------------------------------------------------------------
$effGHz = [math]::Round($nominalMHz / 1000.0 * $loadMax / 100.0, 2)
$effAvg = [math]::Round($nominalMHz / 1000.0 * $loadAvg / 100.0, 2)

Rule
Line "  VERDICT" 'Cyan'
Rule
Line ("  Effective clock under load : max $effGHz GHz, sustained $effAvg GHz")
Line ""

if ($loadMax -lt 115) {
    Line "  PINNED AT BASE. Boost is disabled or the BIOS/OEM caps it." 'Red'
    Line "  Everything in SPEC.md section 4 gets ~1.5x slower. Gate 1 likely fails." 'Red'
    Line ""
    Line "  Things to try, in order:" 'Yellow'
    Line "    1. Plug in, set Windows power mode to 'Best performance'." 'Yellow'
    Line "    2. powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMAX 100" 'Yellow'
    Line "       powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PERFBOOSTMODE 2" 'Yellow'
    Line "       powercfg /setactive SCHEME_CURRENT" 'Yellow'
    Line "    3. Check the OEM app (Dell Power Manager, Lenovo Vantage, HP Command" 'Yellow'
    Line "       Center) and set thermal mode to Performance / Ultra." 'Yellow'
    Line "    4. Check BIOS for a 'Performance mode' or CPU power limit setting." 'Yellow'
    Line "    5. Some corporate images disable boost deliberately. If so, it is" 'Yellow'
    Line "       policy and cannot be fixed locally." 'Yellow'
} elseif ($loadMax -lt 150) {
    Line "  PARTIAL BOOST. Working, but not reaching the 4.2 GHz ceiling." 'Yellow'
    Line "  Normal for a 15 W laptop under sustained load. Use the sustained" 'Yellow'
    Line "  number above for planning, not the peak." 'Yellow'
} else {
    Line "  BOOSTING NORMALLY. The 2112 MHz figure was just the WMI nominal value." 'Green'
}

Line ""
Line "  Next: run .\bench.ps1 and compare against the gates in README.md." 'Cyan'
Line ""

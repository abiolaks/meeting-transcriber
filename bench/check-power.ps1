<#
  Power / clock check for the Phase 0 laptop.

  Question it answers: is this CPU allowed to boost, or pinned at base clock?

  v2 fixes:
    - powercfg parsing took the FIRST hex value in the block ("Minimum Possible
      Setting") instead of the current index. It reported "0%" for a machine that
      was clearly boosting.
    - hidden power settings (no current index) are now reported as hidden rather
      than as a cap.
    - adds Win32_Processor.CurrentClockSpeed as a second, independent clock
      reading, because the % Processor Performance counter can be unreliable on
      HWP / Speed Shift machines.

  Usage:
      powershell -ExecutionPolicy Bypass -File .\check-power.ps1
      powershell -ExecutionPolicy Bypass -File .\check-power.ps1 -Seconds 30

  Run it plugged in, idle, with nothing else heavy open.
#>

[CmdletBinding()]
param(
    [int]$Seconds = 20
)

$ErrorActionPreference = 'Continue'

function Line([string]$t, [string]$c = 'Gray') { Write-Host $t -ForegroundColor $c }
function Rule { Line ('-' * 66) 'DarkGray' }

function Get-PerfPct {
    try {
        $s = (Get-Counter '\Processor Information(_Total)\% Processor Performance' -ErrorAction Stop).CounterSamples[0].CookedValue
        return [math]::Round($s, 1)
    } catch {
        return $null
    }
}

function Get-CurrentMHz {
    try {
        return [int](Get-CimInstance Win32_Processor | Select-Object -First 1).CurrentClockSpeed
    } catch { return $null }
}

function Get-Median($values) {
    $v = @($values | Where-Object { $null -ne $_ } | Sort-Object)
    if ($v.Count -eq 0) { return $null }
    $mid = [int][math]::Floor($v.Count / 2)
    if ($v.Count % 2 -eq 1) { return $v[$mid] }
    return [math]::Round(($v[$mid - 1] + $v[$mid]) / 2, 1)
}

# Read a powercfg setting's CURRENT AC index. Deliberately anchored to
# "Current AC Power Setting Index" so it cannot match the min/max range lines.
function Get-PowerSetting([string]$subgroup, [string]$setting) {
    $raw = (& powercfg /q SCHEME_CURRENT $subgroup $setting 2>&1) -join "`n"
    if ($raw -match 'Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)') {
        return [Convert]::ToInt32($Matches[1], 16)
    }
    return $null   # setting not exposed on this edition/plan
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

# ---- active power scheme + processor settings -------------------------------
$scheme = ((& powercfg /getactivescheme) -join ' ').Trim()
Line "Power scheme     : $scheme"

$SUB = 'SUB_PROCESSOR'

$maxState = Get-PowerSetting $SUB 'PROCTHROTTLEMAX'
if ($null -eq $maxState) {
    Line "Max processor    : hidden (not exposed) - cannot be capped above 100%" 'Gray'
} elseif ($maxState -lt 100) {
    Line "Max processor    : $maxState%  <-- CAP. Should be 100%." 'Red'
} else {
    Line "Max processor    : $maxState% - fine" 'Green'
}

$boost = Get-PowerSetting $SUB 'PERFBOOSTMODE'
if ($null -eq $boost) {
    Line "Boost mode       : hidden (not exposed in this plan) - see OEM tool" 'Gray'
} else {
    $labels = @{ 0 = 'Disabled'; 1 = 'Enabled'; 2 = 'Aggressive'; 3 = 'Efficient enabled'; 4 = 'Efficient aggressive'; 5 = 'Aggressive at guaranteed'; 6 = 'Efficient aggressive at guaranteed' }
    $label = $labels[$boost]
    if ($null -eq $label) { $label = "value $boost" }
    if ($boost -eq 0) { Line "Boost mode       : $label  <-- CAP" 'Red' }
    else { Line "Boost mode       : $label" 'Green' }
}
Line ""

# ---- idle sample ------------------------------------------------------------
Line "Sampling at idle ..."
$idlePct = @(); $idleMHz = @()
for ($i = 0; $i -lt 4; $i++) {
    $p = Get-PerfPct; if ($null -ne $p) { $idlePct += $p }
    $m = Get-CurrentMHz; if ($m) { $idleMHz += $m }
    Start-Sleep -Seconds 1
}
if ($idlePct.Count) { Line ("  idle perf: " + ($idlePct -join '%, ') + "%") }
if ($idleMHz.Count) { Line ("  idle MHz : " + ($idleMHz -join ', ')) }
Line ""

# ---- load sample ------------------------------------------------------------
Line "Loading all $($cpu.NumberOfLogicalProcessors) logical cores for $Seconds s ..."
$until = [DateTime]::UtcNow.AddSeconds($Seconds + 6)
$jobs = 1..$cpu.NumberOfLogicalProcessors | ForEach-Object {
    Start-Job -ScriptBlock {
        param($until)
        $x = 1.0
        while ([DateTime]::UtcNow -lt $until) { $x = [math]::Sqrt($x * 1.000001) + 1 }
    } -ArgumentList $until
}

$loadPct = @(); $loadMHz = @()
for ($i = 0; $i -lt $Seconds; $i++) {
    Start-Sleep -Seconds 1
    # Skip the first two seconds: job startup is not representative of load.
    if ($i -ge 2) {
        $p = Get-PerfPct; if ($null -ne $p) { $loadPct += $p }
        $m = Get-CurrentMHz; if ($m) { $loadMHz += $m }
    }
}

$jobs | Stop-Job -ErrorAction SilentlyContinue
$jobs | Remove-Job -Force -ErrorAction SilentlyContinue

Line ""
if ($loadPct.Count) {
    $steady = $loadPct[[math]::Max(0, $loadPct.Count - 7)..($loadPct.Count - 1)]
    Line ("  load perf: " + ($loadPct -join '%, ') + "%")
    Line ("  load  median $((Get-Median $loadPct))%   steady-state median $((Get-Median $steady))%")
}
if ($loadMHz.Count) {
    Line ("  load MHz  : " + ($loadMHz -join ', '))
    Line ("  load  median $((Get-Median $loadMHz)) MHz   peak $(($loadMHz | Measure-Object -Maximum).Maximum) MHz")
}
Line ""

# ---- verdict ----------------------------------------------------------------
$steadyPct  = if ($loadPct.Count)  { Get-Median ($loadPct[[math]::Max(0, $loadPct.Count - 7)..($loadPct.Count - 1)]) } else { $null }
$steadyMHz  = Get-Median $loadMHz
$peakMHz    = if ($loadMHz.Count) { ($loadMHz | Measure-Object -Maximum).Maximum } else { $null }

# Prefer the hardware clock reading when available; fall back to the counter.
$sustainedGHz = if ($steadyMHz) { [math]::Round($steadyMHz / 1000.0, 2) }
                elseif ($steadyPct) { [math]::Round($nominalMHz / 1000.0 * $steadyPct / 100.0, 2) }
                else { $null }

Rule
Line "  VERDICT" 'Cyan'
Rule
if ($sustainedGHz)    { Line ("  Sustained clock under load : $sustainedGHz GHz") }
if ($peakMHz)         { Line ("  Peak observed              : $([math]::Round($peakMHz / 1000.0, 2)) GHz") }
if ($steadyPct)       { Line ("  Counter steady-state       : $steadyPct% of nominal") }
Line ""

$pinned = $false
if ($sustainedGHz -and $sustainedGHz -lt 2.3) { $pinned = $true }
elseif (-not $sustainedGHz -and $steadyPct -and $steadyPct -lt 115) { $pinned = $true }

if ($pinned) {
    Line "  PINNED NEAR BASE CLOCK. Boost is disabled or capped." 'Red'
    Line "  SPEC section 4 gets ~1.4-1.5x slower. Gate 1 likely fails." 'Red'
    Line ""
    Line "  Try, in order:" 'Yellow'
    Line "    1. Plug in; set Windows power mode to 'Best performance'." 'Yellow'
    Line "    2. powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMAX 100" 'Yellow'
    Line "       powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PERFBOOSTMODE 2" 'Yellow'
    Line "       powercfg /setactive SCHEME_CURRENT" 'Yellow'
    Line "    3. OEM app (Dell Power Manager, Lenovo Vantage, HP Command Center):" 'Yellow'
    Line "       set thermal mode to Performance / Ultra." 'Yellow'
    Line "    4. BIOS: look for a CPU power limit or performance mode." 'Yellow'
    Line "    5. If corporate policy pins clocks, it cannot be fixed locally." 'Yellow'
} else {
    Line "  BOOSTING. The CPU reaches well above base clock under load." 'Green'
    Line "  The 2112 MHz WMI figure is nominal, not a cap." 'Green'
}

# The counter is known to misreport on HWP machines; say so rather than hide it.
$idlePctMed = Get-Median $idlePct
if ($idlePctMed -and $steadyPct -and $idlePctMed -gt ($steadyPct + 10)) {
    Line ""
    Line "  NOTE: idle reported HIGHER than load ($idlePctMed% vs $steadyPct%)." 'Yellow'
    Line "  That is not physically meaningful - % Processor Performance is" 'Yellow'
    Line "  unreliable on HWP / Speed Shift systems. Trust the MHz readings." 'Yellow'
}

Line ""
Line "  Cross-check: Task Manager -> Performance -> CPU -> 'Speed' during" 'Cyan'
Line "  a real whisper run. It should sit near the number above." 'Cyan'
Line ""
Line "  Next: run .\bench.ps1 and compare against the gates in README.md." 'Cyan'
Line ""

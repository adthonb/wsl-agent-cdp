# Run with Windows PowerShell 5.1:
# powershell.exe -NoProfile -File tests/test_windows_bridge.ps1
param([string]$HelperPath = (Join-Path $PSScriptRoot '../scripts/windows-bridge.ps1'))
$ErrorActionPreference = 'Stop'
$helper = $HelperPath
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $helper, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors -join "`n") }
# Load only functions, without executing Setup or changing the real profile.
foreach ($name in @('Get-ProfilePath', 'Assert-ProfileClosed')) {
    $node = $ast.Find({ param($n)
        $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $n.Name -eq $name
    }, $true)
    Invoke-Expression $node.Extent.Text
}
$Browser = 'brave'
$StateRoot = 'C:\Users\Agent Test\AppData\Local\wsl-cdp-bridge'
$profile = Get-ProfilePath
function Get-CimInstance { param($ClassName, $Filter) return $script:processes }

function Assert-Guard {
    param([string]$Name, [object[]]$Processes, [bool]$Blocked)
    $script:processes = $Processes
    $caught = $false
    try { Assert-ProfileClosed } catch { $caught = $true }
    if ($caught -ne $Blocked) { throw "${Name}: expected blocked=$Blocked, got $caught" }
    Write-Host "PASS: $Name"
}
function New-BrowserProcess {
    param([string]$CommandLine)
    return [pscustomobject]@{ ProcessId = 123; CommandLine = $CommandLine }
}
Assert-Guard 'no running browser' @() $false
Assert-Guard 'ordinary profile stays open' @(
    (New-BrowserProcess 'brave.exe --user-data-dir="C:\ordinary-profile"')
) $false
Assert-Guard 'orphan crash handler does not block relaunch' @(
    (New-BrowserProcess "brave.exe --type=crashpad-handler --user-data-dir=`"$profile`"")
) $false
Assert-Guard 'open agent browser must block hardening' @(
    (New-BrowserProcess "brave.exe --user-data-dir=`"$profile`""),
    (New-BrowserProcess "brave.exe --type=crashpad-handler --user-data-dir=`"$profile`"")
) $true
Assert-Guard 'renderer still shutting down must block hardening' @(
    (New-BrowserProcess "brave.exe --type=renderer --user-data-dir=`"$profile`"")
) $true
Assert-Guard 'unknown command line must block hardening' @(
    (New-BrowserProcess $null)
) $true
Assert-Guard 'crashpad text in a path is not a process type' @(
    (New-BrowserProcess "brave.exe --user-data-dir=`"$profile`" --log-file=C:\--type=crashpad-handler")
) $true

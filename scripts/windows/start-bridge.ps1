#requires -Version 5.1
<#
.SYNOPSIS
Inspect the project queue and run one Colab MCP bridge in the foreground.
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = [System.IO.Path]::GetFullPath(
        (Join-Path -Path $PSScriptRoot -ChildPath '..\..')
    ),
    [switch]$ResumeReviewedQueue
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw 'This launcher targets Windows with PowerShell 5.1 or later.'
    }
    $ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
    $VenvPython = Join-Path $ProjectRoot 'vendor\colab-mcp\.venv\Scripts\python.exe'
    $ServerExecutable = Join-Path $ProjectRoot 'vendor\colab-mcp\.venv\Scripts\colab-mcp.exe'
    $BridgeScript = Join-Path $ProjectRoot 'mcp_bridge.py'
    foreach ($RequiredPath in @($VenvPython, $ServerExecutable, $BridgeScript)) {
        if (-not (Test-Path -LiteralPath $RequiredPath -PathType Leaf)) {
            throw "Required file is missing: $RequiredPath. Run setup for this project first."
        }
    }
    & $VenvPython -c 'import sys; assert sys.version_info[:3]==(3,13,18), ''Expected the pinned project Python 3.13.18'''
    if ($LASTEXITCODE -ne 0) { throw 'The project Python version check failed.' }

    $StateDirectory = Join-Path $ProjectRoot 'bridge_state'
    $StatusPath = Join-Path $StateDirectory 'status.json'
    $Queued = @()
    $Claimed = @()
    $Inbox = Join-Path $StateDirectory 'inbox'
    $Processing = Join-Path $StateDirectory 'processing'
    if (Test-Path -LiteralPath $Inbox -PathType Container) {
        $Queued = @(Get-ChildItem -LiteralPath $Inbox -Filter '*.json' -File)
    }
    if (Test-Path -LiteralPath $Processing -PathType Container) {
        $Claimed = @(Get-ChildItem -LiteralPath $Processing -Filter '*.json' -File)
    }
    Write-Host "Queue inspection: $($Queued.Count) unclaimed, $($Claimed.Count) previously claimed request(s)."
    if (($Queued.Count + $Claimed.Count) -gt 0 -and -not $ResumeReviewedQueue) {
        throw 'Existing inbox/processing requests require inspection together with their outbox results and notebook effects. After that inspection, use -ResumeReviewedQueue to start this same queue. Nothing was deleted or resubmitted.'
    }
    if (($Queued.Count + $Claimed.Count) -gt 0) {
        Write-Host 'Reviewed inbox requests can execute after startup. Interrupted processing requests are recorded as uncertain and are not replayed.'
    }

    # Read immediately before launch. This is a preflight check, not a lock:
    # mcp_bridge.py's OS-managed instance.lock is the final concurrency guard.
    if (Test-Path -LiteralPath $StatusPath -PathType Leaf) {
        $Status = Get-Content -LiteralPath $StatusPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $Status.PSObject.Properties['state'] -or
            -not $Status.PSObject.Properties['heartbeat_at']) {
            throw 'The existing status file lacks state or heartbeat_at. Inspect it before starting a bridge.'
        }
        $Heartbeat = [DateTimeOffset]::MinValue
        if (-not [DateTimeOffset]::TryParse([string]$Status.heartbeat_at, [ref]$Heartbeat)) {
            throw 'The existing heartbeat cannot be parsed. Inspect the queue instead of guessing that its bridge is stopped.'
        }
        $Age = ([DateTimeOffset]::UtcNow - $Heartbeat).TotalSeconds
        Write-Host ('Last state: {0}; heartbeat age: {1:N1} seconds.' -f $Status.state, $Age)
        if ($Age -lt -5) {
            throw 'The heartbeat is in the future. Check the system clock and existing bridge before starting another one.'
        }
        if ($Status.state -in @('starting', 'ready', 'executing', 'stopping') -and $Age -le 20) {
            throw 'A bridge reports an active state and a fresh heartbeat. Reuse it; this launcher will not start a second instance.'
        }
        if ($Status.state -notin @('starting', 'ready', 'executing', 'stopping', 'stopped', 'error')) {
            throw 'The status file has an unknown state. Inspect it before startup.'
        }
    } else {
        Write-Host 'No saved status exists for this project queue.'
    }

    Write-Host "Starting bridge in the foreground for $ProjectRoot. Keep this terminal open."
    Write-Host 'Bridge readiness and browser/notebook connection are separate; verify tools and notebook identity in a second terminal.'
    & $VenvPython $BridgeScript --project-dir $ProjectRoot
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine(('Bridge launch stopped: ' + $_.Exception.Message))
    exit 1
}

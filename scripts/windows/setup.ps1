#requires -Version 5.1
<#
.SYNOPSIS
Reproduce the pinned local Colab MCP environment without starting a server.
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = [System.IO.Path]::GetFullPath(
        (Join-Path -Path $PSScriptRoot -ChildPath '..\..')
    )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$OfficialRepository = 'https://github.com/googlecolab/colab-mcp.git'
$PinnedRevision = 'b9ab3899e0f1fa493390b1fd6d54aa2e464ecdf1'
$PinnedPython = '3.13.18'
$PinnedUv = '0.13.7'

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable"
    }
}

function Get-GitText {
    param([string[]]$Arguments)
    $GitOutput = @(& $script:GitExecutable @Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Git inspection failed with exit code $LASTEXITCODE. Existing files were not reset or cleaned."
    }
    return ($GitOutput -join "`n")
}

function ConvertTo-NormalizedPatch {
    param([string]$Text)
    $Normalized = $Text.Replace("`r`n", "`n")
    # Git may choose a different object-ID abbreviation. Preserve every hunk
    # and file-mode change; normalize only the index hashes and line endings.
    $Normalized = [regex]::Replace(
        $Normalized, '(?m)^index [0-9a-f]+\.\.[0-9a-f]+( [0-7]+)?$', 'index$1'
    )
    return $Normalized.TrimEnd([char[]]"`r`n")
}

function Get-VendorPatch {
    $Difference = Get-GitText -Arguments @(
        '-C', $script:VendorRoot, 'diff', '--no-ext-diff', '--no-textconv',
        '--no-color', '--no-renames', '--unified=3', '--full-index',
        '--src-prefix=a/', '--dst-prefix=b/'
    )
    return (ConvertTo-NormalizedPatch -Text $Difference)
}

function Assert-VenvPython {
    param([string]$PythonExecutable, [string]$EnvironmentRoot)
    $PythonOutput = @(& $PythonExecutable -c 'import json,sys; print(json.dumps({''version'':''.''.join(map(str,sys.version_info[:3])),''prefix'':sys.prefix}))')
    if ($LASTEXITCODE -ne 0) {
        throw 'The existing project Python could not be inspected. Its environment was left intact.'
    }
    $PythonInfo = ($PythonOutput -join "`n") | ConvertFrom-Json
    if ($PythonInfo.version -ne $script:PinnedPython) {
        throw "The existing project environment uses Python $($PythonInfo.version), expected $script:PinnedPython. It was not replaced."
    }
    $ActualPrefix = [System.IO.Path]::GetFullPath([string]$PythonInfo.prefix).TrimEnd('\', '/')
    $ExpectedPrefix = [System.IO.Path]::GetFullPath($EnvironmentRoot).TrimEnd('\', '/')
    if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals($ActualPrefix, $ExpectedPrefix)) {
        throw 'The project Python does not belong to vendor/colab-mcp/.venv. No system environment will be changed.'
    }
}

try {
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw 'This setup script targets Windows with PowerShell 5.1 or later.'
    }
    foreach ($GitOverride in @('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR')) {
        if ([System.Environment]::GetEnvironmentVariable($GitOverride, 'Process')) {
            throw "Inherited $GitOverride could redirect Git outside the vendor checkout. Run setup from a shell without this override."
        }
    }
    $ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
    $script:VendorRoot = Join-Path -Path $ProjectRoot -ChildPath 'vendor\colab-mcp'
    $PatchPath = Join-Path -Path $ProjectRoot -ChildPath 'patches\colab-mcp-windows.patch'
    foreach ($RequiredPath in @(
        (Join-Path $ProjectRoot 'mcp_bridge.py'),
        (Join-Path $ProjectRoot 'mcp_call.py'),
        $PatchPath
    )) {
        if (-not (Test-Path -LiteralPath $RequiredPath -PathType Leaf)) {
            throw "Required project file is missing: $RequiredPath"
        }
    }

    $script:GitExecutable = (Get-Command git -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $UvExecutable = (Get-Command uv -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $UvOutput = @(& $UvExecutable --version)
    if ($LASTEXITCODE -ne 0) { throw 'uv --version failed.' }
    $UvVersion = $UvOutput -join "`n"
    if ($UvVersion -notmatch ('^uv ' + [regex]::Escape($PinnedUv) + '(?:\s|$)')) {
        throw "Reproduction requires uv $PinnedUv in PATH; found: $UvVersion. This script does not replace uv."
    }
    Write-Host "Using $UvVersion; pinned Python $PinnedPython; upstream $PinnedRevision."

    if (-not (Test-Path -LiteralPath $VendorRoot)) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $VendorRoot) -Force | Out-Null
        Invoke-Checked -Executable $GitExecutable -Arguments @(
            'clone', '--no-checkout', $OfficialRepository, $VendorRoot
        )
        Invoke-Checked -Executable $GitExecutable -Arguments @(
            '-C', $VendorRoot, 'checkout', '--detach', $PinnedRevision
        )
    } else {
        $VendorItem = Get-Item -LiteralPath $VendorRoot -Force
        if (-not $VendorItem.PSIsContainer -or
            ($VendorItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw 'The existing vendor path must be an ordinary directory, not a file or reparse point.'
        }
    }

    $RepositoryRoot = Get-GitText -Arguments @('-C', $VendorRoot, 'rev-parse', '--show-toplevel')
    if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals(
        [System.IO.Path]::GetFullPath($RepositoryRoot).TrimEnd('\', '/'),
        [System.IO.Path]::GetFullPath($VendorRoot).TrimEnd('\', '/')
    )) {
        throw 'vendor/colab-mcp is not its own Git checkout. No parent repository will be modified.'
    }
    $Origin = Get-GitText -Arguments @('-C', $VendorRoot, 'remote', 'get-url', 'origin')
    if ($Origin -notmatch '^(https://github\.com/googlecolab/colab-mcp(?:\.git)?/?|git@github\.com:googlecolab/colab-mcp(?:\.git)?)$') {
        throw 'The existing vendor origin is not the official googlecolab/colab-mcp repository. It was left intact.'
    }
    $Head = Get-GitText -Arguments @('-C', $VendorRoot, 'rev-parse', 'HEAD')
    if ($Head -ne $PinnedRevision) {
        throw "The existing vendor HEAD is $Head, expected $PinnedRevision. Inspect it manually or use a separate fresh clone; no checkout/reset/clean was performed on it."
    }
    $StagedPaths = Get-GitText -Arguments @('-C', $VendorRoot, 'diff', '--cached', '--name-only')
    if ($StagedPaths) { throw 'The vendor has staged changes. Inspect them before setup; they were preserved.' }
    $Untracked = Get-GitText -Arguments @('-C', $VendorRoot, 'ls-files', '--others', '--exclude-standard', '--directory')
    $UnexpectedUntracked = @($Untracked -split "`n" | Where-Object { $_ -and $_ -ne '.venv/' })
    if ($UnexpectedUntracked.Count -ne 0) {
        throw 'The vendor contains additional untracked files. Inspect them before setup; nothing was removed.'
    }

    $ExpectedPatch = ConvertTo-NormalizedPatch -Text ([System.IO.File]::ReadAllText($PatchPath))
    $CurrentPatch = Get-VendorPatch
    if ($CurrentPatch -and $CurrentPatch -cne $ExpectedPatch) {
        throw 'The vendor has changes other than the exact supplied patch. Setup refuses to modify them.'
    }
    $EnvironmentRoot = Join-Path $VendorRoot '.venv'
    $VenvPython = Join-Path $EnvironmentRoot 'Scripts\python.exe'
    if (Test-Path -LiteralPath $EnvironmentRoot) {
        $EnvironmentItem = Get-Item -LiteralPath $EnvironmentRoot -Force
        if (-not $EnvironmentItem.PSIsContainer -or
            ($EnvironmentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw 'The existing project .venv must be an ordinary directory, not a file or reparse point.'
        }
        if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
            throw 'An incomplete project .venv already exists. Inspect it manually; it was not deleted or replaced.'
        }
        Assert-VenvPython -PythonExecutable $VenvPython -EnvironmentRoot $EnvironmentRoot
    }

    if ($CurrentPatch) {
        Invoke-Checked -Executable $GitExecutable -Arguments @('-C', $VendorRoot, 'apply', '--reverse', '--check', $PatchPath)
        Write-Host 'The exact project patch is already applied.'
    } else {
        Invoke-Checked -Executable $GitExecutable -Arguments @('-C', $VendorRoot, 'apply', '--check', $PatchPath)
        Invoke-Checked -Executable $GitExecutable -Arguments @('-C', $VendorRoot, 'apply', $PatchPath)
        Write-Host 'Applied the project patch once.'
    }
    if ((Get-VendorPatch) -cne $ExpectedPatch) { throw 'Post-application patch verification failed.' }

    # Force uv to use this project environment even if the caller has a global
    # UV_PROJECT_ENVIRONMENT setting. Restore the caller's setting afterwards.
    $PreviousUvEnvironment = [System.Environment]::GetEnvironmentVariable('UV_PROJECT_ENVIRONMENT', 'Process')
    try {
        [System.Environment]::SetEnvironmentVariable('UV_PROJECT_ENVIRONMENT', $EnvironmentRoot, 'Process')
        Push-Location -LiteralPath $VendorRoot
        try {
            Invoke-Checked -Executable $UvExecutable -Arguments @(
                'sync', '--frozen', '--no-dev', '--python', $PinnedPython
            )
        } finally { Pop-Location }
    } finally {
        [System.Environment]::SetEnvironmentVariable('UV_PROJECT_ENVIRONMENT', $PreviousUvEnvironment, 'Process')
    }

    Assert-VenvPython -PythonExecutable $VenvPython -EnvironmentRoot $EnvironmentRoot
    $ServerExecutable = Join-Path $EnvironmentRoot 'Scripts\colab-mcp.exe'
    if (-not (Test-Path -LiteralPath $ServerExecutable -PathType Leaf)) {
        throw 'uv completed but the colab-mcp executable is missing.'
    }
    Invoke-Checked -Executable $VenvPython -Arguments @(
        '-c', 'import importlib.metadata as m, importlib.util as u; assert m.version(''colab-mcp'')==''1.0.1''; assert u.find_spec(''mcp'') and u.find_spec(''colab_mcp''); print(''colab-mcp 1.0.1 and MCP SDK are installed; no server was started.'')'
    )
    if ((Get-VendorPatch) -cne $ExpectedPatch) {
        throw 'The vendor tracked files changed during dependency installation. Inspect them before starting the bridge.'
    }
    Write-Host 'Setup verified. The bridge, browser, Colab runtime and GPU have not been started.'
    Write-Host 'Next: run scripts/windows/start-bridge.ps1 in the foreground, then follow docs/setup-windows.md.'
    exit 0
} catch {
    [Console]::Error.WriteLine(('Setup stopped: ' + $_.Exception.Message))
    exit 1
}

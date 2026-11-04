[CmdletBinding()]
param(
    [string]$Root
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = Split-Path -Parent $PSScriptRoot
}
$RootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
if (-not $RootItem.PSIsContainer -or ($RootItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'The public repository root must be a real directory, not a reparse point.'
}

$ResolvedRoot = $RootItem.FullName.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
$Prefix = $ResolvedRoot + [IO.Path]::DirectorySeparatorChar
$Pending = [System.Collections.Generic.Queue[string]]::new()
$Pending.Enqueue($ResolvedRoot)
$Findings = [System.Collections.Generic.List[string]]::new()

while ($Pending.Count -ne 0) {
    $Current = $Pending.Dequeue()
    foreach ($Child in @(Get-ChildItem -LiteralPath $Current -Force)) {
        if (($Child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            $Findings.Add("reparse point: $($Child.FullName)")
            continue
        }
        $FullPath = [IO.Path]::GetFullPath($Child.FullName)
        if (-not $FullPath.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "A path escaped the public repository root: $FullPath"
        }
        if ($Child.PSIsContainer) {
            if ($Child.Name -eq '.git') {
                continue
            }
            if ($Child.Name -in @('assets', 'data')) {
                $Unexpected = @(Get-ChildItem -LiteralPath $FullPath -Force | Where-Object { $_.Name -ne '.gitkeep' })
                if ($Unexpected.Count -ne 0) {
                    $Findings.Add("local-only directory contains files: $($Child.FullName)")
                }
                continue
            }
            $Pending.Enqueue($FullPath)
            continue
        }
        $Streams = @(
            Get-Item -LiteralPath $FullPath -Stream '*' -Force -ErrorAction Stop |
                Where-Object { $_.Stream -ne ':$DATA' }
        )
        foreach ($Stream in $Streams) {
            $Findings.Add("alternate data stream: $($Child.FullName) [$($Stream.Stream)]")
        }
    }
}

if ($Findings.Count -ne 0) {
    Write-Error "Public metadata audit failed:`n$($Findings -join "`n")"
    exit 1
}

Write-Host 'Public metadata audit passed: no reparse points or alternate data streams.'

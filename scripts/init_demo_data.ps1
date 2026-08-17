# 初始化演示数据：把 data.example/（虚构假数据）拷贝为 data/，并安装 training 演示产物。
# 用法：
#   powershell -File scripts/init_demo_data.ps1           # 已有真实数据时跳过，不覆盖
#   powershell -File scripts/init_demo_data.ps1 -Force    # 强制覆盖（runs/index.json 会做合并而非丢弃）
param([switch]$Force)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $root "data.example"

if (-not (Test-Path $src)) {
    Write-Host "未找到 $src，请确认已克隆完整仓库" -ForegroundColor Red
    exit 1
}

# ---- 1. data/ ----
$dataDir = Join-Path $root "data"
if ((Test-Path $dataDir) -and -not $Force) {
    Write-Host "[跳过] data/ 已存在（可能含真实数据）。如需重置为演示数据请加 -Force" -ForegroundColor Yellow
} else {
    if (Test-Path $dataDir) { Remove-Item $dataDir -Recurse -Force }
    Copy-Item $src $dataDir -Recurse
    # data.example/training/ 是给 training/ 用的，不属于 data/
    if (Test-Path "$dataDir\training") { Remove-Item "$dataDir\training" -Recurse -Force }
    Write-Host "[OK] data/ 已从 data.example/ 初始化" -ForegroundColor Green
}

# ---- 2. training/alpaca_dataset.json ----
$alpaca = Join-Path $root "training\alpaca_dataset.json"
if ((Test-Path $alpaca) -and -not $Force) {
    Write-Host "[跳过] training/alpaca_dataset.json 已存在。覆盖请加 -Force" -ForegroundColor Yellow
} else {
    Copy-Item "$src\training\alpaca_dataset.json" $alpaca -Force
    Write-Host "[OK] training/alpaca_dataset.json 已安装演示版" -ForegroundColor Green
}

# ---- 3. training/runs/（目录合并；index.json 合并去重，不丢已有记录）----
$runsDir = Join-Path $root "training\runs"
$srcRuns = "$src\training\runs"
if (-not (Test-Path $runsDir)) {
    Copy-Item $srcRuns $runsDir -Recurse
    Write-Host "[OK] training/runs/ 已从演示版初始化" -ForegroundColor Green
} else {
    # 拷贝演示 run 目录（与真实 run 目录名不冲突）
    Get-ChildItem $srcRuns -Directory | ForEach-Object {
        $dst = Join-Path $runsDir $_.Name
        if (-not (Test-Path $dst)) {
            Copy-Item $_.FullName $dst -Recurse
            Write-Host "[OK] 新增训练记录 $($_.Name)" -ForegroundColor Green
        }
    }
    # 合并 index.json（按 run_id 去重，时间倒序）
    $srcIndex = Get-Content "$srcRuns\index.json" -Raw | ConvertFrom-Json
    $dstIndexPath = "$runsDir\index.json"
    $dstIndex = @()
    if (Test-Path $dstIndexPath) { $dstIndex = Get-Content $dstIndexPath -Raw | ConvertFrom-Json }
    $merged = @($dstIndex) + @($srcIndex | Where-Object { $dstIndex.run_id -notcontains $_.run_id })
    $merged = $merged | Sort-Object timestamp -Descending
    $merged | ConvertTo-Json -Depth 10 | Set-Content $dstIndexPath -Encoding utf8
    Write-Host "[OK] training/runs/index.json 已合并（$($merged.Count) 条记录）" -ForegroundColor Green
}

Write-Host ""
Write-Host "完成。演示数据规模：300 条标注（107 采纳）/ 3 个评估 session / 1 个训练 dry-run。" -ForegroundColor Cyan
Write-Host "后续可用 python scripts/gen_demo_data.py 重新生成 data.example/。" -ForegroundColor Cyan

param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& $Python -c "import sys; assert sys.platform == 'win32' and sys.version_info >= (3, 12), 'Windows CPython 3.12+ required'; import tkinter"
if ($LASTEXITCODE -ne 0) { throw '需要带有 tkinter 的标准 Windows CPython 3.12+。已验证版本为 3.12。' }
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败。' }
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw '安装依赖失败。' }
& '.\.venv\Scripts\python.exe' -c "from nte_ocr.vision import Reader; Reader()"
if ($LASTEXITCODE -ne 0) { throw 'OCR 模型初始化失败。' }
Write-Host '安装完成，双击 启动.bat。'

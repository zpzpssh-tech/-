# 올투게더나우 주문 수집 프로그램 설치 (install-atgn.bat 이 내려받아 실행)
# 1) Node.js 확인·설치  2) 프로그램 내려받기  3) 키 입력(설정)  4) 10분마다 자동 실행 등록
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$src = 'https://raw.githubusercontent.com/zpzpssh-tech/-/refs/heads/claude/fervent-wozniak-wow6ha/connector/'
$dir = Join-Path $env:LOCALAPPDATA 'ATGN\connector'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Write-Host ''
Write-Host '=== 올투게더나우 주문 수집 프로그램 설치 ===' -ForegroundColor Cyan

# 1) Node.js (프로그램을 돌리는 무료 실행 도구)
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
  Write-Host '[1/4] Node.js 를 설치합니다 (1~2분)...'
  $msi = Join-Path $env:TEMP 'node-lts-x64.msi'
  Invoke-WebRequest -UseBasicParsing 'https://nodejs.org/dist/v20.18.1/node-v20.18.1-x64.msi' -OutFile $msi
  $p = Start-Process msiexec.exe -ArgumentList "/i `"$msi`" /qn /norestart" -Wait -PassThru
  if ($p.ExitCode -ne 0) { throw "Node.js 설치 실패 (코드 $($p.ExitCode)). install-atgn.bat 을 마우스 오른쪽 → '관리자 권한으로 실행' 으로 다시 실행해 주세요." }
  $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
  $node = Get-Command node -ErrorAction Stop
} else { Write-Host '[1/4] Node.js 가 이미 있습니다.' }
$nodeExe = $node.Source
$npm = Join-Path (Split-Path $nodeExe) 'npm.cmd'

# 2) 프로그램 내려받기
Write-Host '[2/4] 프로그램을 내려받습니다...'
foreach ($f in @('atgn-connector.js', 'package.json')) { Invoke-WebRequest -UseBasicParsing ($src + $f) -OutFile (Join-Path $dir $f) }
Push-Location $dir
& $npm install --omit=dev --no-audit --no-fund --loglevel=error
Pop-Location

# 3) 키 입력 + 연결 시험
Write-Host '[3/4] 설정을 시작합니다. 메모해 둔 키를 붙여넣어 주세요 (붙여넣기: 마우스 오른쪽 클릭).' -ForegroundColor Yellow
& $nodeExe (Join-Path $dir 'atgn-connector.js') setup

# 4) 10분마다 자동 실행 (창이 뜨지 않게 숨겨서 실행)
Write-Host '[4/4] 10분마다 자동 실행되도록 등록합니다...'
$vbs = Join-Path $dir 'run-hidden.vbs'
$q = '""'
$vbsBody = "Set sh = CreateObject(""WScript.Shell"")`r`nsh.CurrentDirectory = ""$dir""`r`nsh.Run ""$q$nodeExe$q $q$dir\atgn-connector.js$q"", 0, True`r`n"
[IO.File]::WriteAllText($vbs, $vbsBody, [Text.Encoding]::Unicode)
schtasks /Create /SC MINUTE /MO 10 /TN 'ATGN-orders' /TR "wscript.exe `"$vbs`"" /F | Out-Null
schtasks /Run /TN 'ATGN-orders' | Out-Null

Write-Host ''
Write-Host '설치가 끝났습니다. 10분마다 네이버 주문을 가져와 재고DB로 보냅니다.' -ForegroundColor Green
Write-Host ("기록 보기: " + (Join-Path $env:LOCALAPPDATA 'ATGN\log.txt'))
Write-Host '멈추려면: schtasks /Delete /TN ATGN-orders /F'

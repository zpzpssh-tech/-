@echo off
rem ATGN order connector installer - right click, Run as administrator
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/zpzpssh-tech/-/refs/heads/claude/fervent-wozniak-wow6ha/connector/install.ps1' -OutFile \"$env:TEMP\atgn-install.ps1\"; & \"$env:TEMP\atgn-install.ps1\""
pause

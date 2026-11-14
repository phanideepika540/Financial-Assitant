@echo off
setlocal

echo This helper connects to an existing Amazon Linux EC2 instance and deploys
echo the current Git branch. It does not create AWS resources or edit .env.
echo Make sure the instance, RDS, security groups, and /home/ec2-user/.env are ready.
echo.

set /p "EC2_HOST=EC2 public DNS name or IP: "
set /p "KEY_PATH=Full path to your PEM key: "

if not defined EC2_HOST (
    echo ERROR: EC2 host is required.
    exit /b 1
)
if not defined KEY_PATH (
    echo ERROR: PEM key path is required.
    exit /b 1
)
if not exist "%KEY_PATH%" (
    echo ERROR: Key file not found.
    exit /b 1
)

where ssh.exe >nul 2>nul
if errorlevel 1 (
    echo ERROR: OpenSSH client was not found. Enable the Windows OpenSSH Client feature.
    exit /b 1
)

echo.
echo Connecting to ec2-user@%EC2_HOST% ...
ssh -i "%KEY_PATH%" -o IdentitiesOnly=yes "ec2-user@%EC2_HOST%" "bash -s" < "%~dp0deploy-ec2.sh"
if errorlevel 1 (
    echo.
    echo Deployment failed. Review the remote error output before retrying.
    exit /b 1
)

echo.
echo Deployment completed. Verify the app in your browser and check its logs.
pause
endlocal

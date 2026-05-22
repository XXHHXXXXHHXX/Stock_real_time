@echo off
chcp 65001 >nul
echo ==========================================
echo  实时板块资金流向监控工具 - 打包脚本
echo ==========================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

REM 调用Python打包脚本
echo 正在调用 build.py 进行打包...
python build.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo.
echo ==========================================
echo  打包成功！
echo ==========================================
echo.
pause

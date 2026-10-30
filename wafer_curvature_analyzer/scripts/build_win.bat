@echo off
setlocal
cd /d "%~dp0.."

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher was not found. Install Python 3.12 or newer.
    exit /b 1
)

py -m venv .build-venv
if errorlevel 1 exit /b 1

set "PYTHON=.build-venv\Scripts\python.exe"
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

"%PYTHON%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

set "BUILD_DRIVE=Z:"
if exist Z:\NUL set "BUILD_DRIVE=Y:"
if exist Y:\NUL (
    echo Both Z: and Y: are already in use. Free one drive letter and retry.
    exit /b 1
)
subst %BUILD_DRIVE% "%CD%"
if errorlevel 1 exit /b 1

"%BUILD_DRIVE%\.build-venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed ^
    --name WaferCurvatureAnalyzer ^
    main.py
set "BUILD_STATUS=%ERRORLEVEL%"
subst %BUILD_DRIVE% /d
cd /d "%~dp0.."
if not "%BUILD_STATUS%"=="0" exit /b %BUILD_STATUS%

set "ISCC="
where ISCC.exe >nul 2>nul
if not errorlevel 1 set "ISCC=ISCC.exe"
if not defined ISCC if exist ".build-tools\Inno\ISCC.exe" set "ISCC=.build-tools\Inno\ISCC.exe"
if not defined ISCC if exist ".build-tools\Inno Setup 7\ISCC.exe" set "ISCC=.build-tools\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist ".build-tools\Inno Setup 6\ISCC.exe" set "ISCC=.build-tools\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo The application executable was created at dist\WaferCurvatureAnalyzer\WaferCurvatureAnalyzer.exe
    echo Install Inno Setup 6 and run this script again to create the installable setup.
    exit /b 0
)

"%ISCC%" installer.iss
if errorlevel 1 exit /b 1

echo Installer created at dist\WaferCurvatureAnalyzerSetup.exe

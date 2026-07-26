@echo off
chcp 65001 >nul
title Borsa Paneli
cd /d "%~dp0"

echo ============================================================
echo   BORSA PANELI
echo   Bu arac gecmis finansal verileri analiz eder,
echo   gelecek getiri tahmini veya yatirim tavsiyesi vermez.
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo HATA: Python bulunamadi.
    echo python.org adresinden kurup "Add Python to PATH" secenegini isaretle.
    echo.
    pause
    exit /b 1
)

if not exist "data\cache\context\bist.json" (
    echo Ilk kurulum: BIST taramasi henuz yapilmamis.
    echo Sektor medyani, tarayici ve piyasa bakisi bunu gerektiriyor.
    echo Tarama yaklasik 15 dakika surer ve bir kez yapilir.
    echo.
    set /p TARA="Simdi taramak ister misin? (E/H): "
    if /i "%TARA%"=="E" (
        echo.
        python tools\tarama.py bist
        echo.
    ) else (
        echo Tarama atlandi. Skor karti ve rapor okuyucu yine calisir.
        echo Sonra calistirmak icin:  python tools\tarama.py bist
        echo.
    )
)

echo Panel baslatiliyor... Kapatmak icin bu pencerede Ctrl+C.
echo.
python server.py
if errorlevel 1 (
    echo.
    echo Panel beklenmedik sekilde kapandi.
    pause
)

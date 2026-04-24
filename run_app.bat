@echo off
echo ============================================================
echo   DQ Agent Framework - Deterministic Data Quality Engine
echo ============================================================
echo.

:: Check if venv exists
if not exist "venv\Scripts\activate.bat" (
    echo [SETUP] Creating virtual environment...
    python -m venv venv
    echo [SETUP] Installing dependencies...
    venv\Scripts\pip install -r requirements.txt --quiet
    echo [SETUP] Dependencies installed successfully.
    echo.
)

:: Activate venv
call venv\Scripts\activate.bat

:: Generate datasets if they don't exist
if not exist "data\raw\healthcare_dataset.csv" (
    echo [DATA] Generating synthetic datasets...
    python src\data_generation\generate_datasets.py
    echo [DATA] Datasets generated successfully.
    echo.
)

:: Create output directories
if not exist "data\cleaned" mkdir data\cleaned
if not exist "output" mkdir output
if not exist "reports" mkdir reports

:: Launch Streamlit app
echo [APP] Launching DQ Agent Framework...
echo [APP] Access at: http://localhost:8501
echo.
streamlit run src\app.py --server.port=8501 --server.headless=true

pause

.PHONY: setup test lint app train sim artifacts figures all clean

PY := .venv/Scripts/python.exe
ifeq ($(OS),)
PY := .venv/bin/python
endif

setup:      ## create .venv (Python 3.12) and install everything, CadQuery included
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -r requirements-dev.txt

test:       ## full test suite
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check pipeforge app tests scripts

app:        ## run the Streamlit app locally
	$(PY) -m streamlit run app/streamlit_app.py

train:      ## download TubeBEND (if needed), build features, train and evaluate the springback models
	$(PY) -m pipeforge.springback_ml.download
	$(PY) -m pipeforge.springback_ml.train

sim:        ## run the line simulation and every kaizen scenario, write artifacts/line
	$(PY) -m pipeforge.kaizen

artifacts:  ## regenerate STEP/STL/PDF/XLSX for every sample part
	$(PY) scripts/build_artifacts.py

figures:    ## regenerate every figure used in the README
	$(PY) scripts/build_figures.py

all: artifacts train sim figures test

clean:
	rm -rf .pytest_cache .ruff_cache .hypothesis

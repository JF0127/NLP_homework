#！/usr/bin/bash

EXPECTED_PYTHON_VERSION="Python 3.11.5"
PYTHON_VERSION=$(python --version)
echo ${PYTHON_VERSION}
if test "$EXPECTED_PYTHON_VERSION" = "$PYTHON_VERSION"; then
    echo "Pyhton version matched."
else
    echo "Need conda activate"
    source /opt/miniconda3/bin/activate
fi

python -m venv .venv
source ./.venv/bin/activate
which python

python -m pip install -U pip
pip install -r requirement.txt

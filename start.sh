#!/usr/bin/env bash
find ./temp_modules/ -type f -name "*.py" -exec cp -t ./modules/ {} +
rm -rf /usr/src/app/temp_modules
python /usr/src/app/main.py
#!/usr/bin/env bash
cp /usr/src/app/temp_modules/*.py /usr/src/app/modules/
rm -rf /usr/src/app/temp_modules
python /usr/src/app/main.py
#!/bin/bash

rm -rf app/*
cp -r ~/git/scripts/kubedsr/bin/* app/
rm -rf app/lib.*
find app -name __pycache__ -exec rm -rf {} \; 2>/dev/null

tree app

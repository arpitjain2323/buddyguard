#!/bin/bash
cd "$(dirname "$0")"
export PYTHONPATH="$PWD"
exec python3 -m agent.agent "$@"

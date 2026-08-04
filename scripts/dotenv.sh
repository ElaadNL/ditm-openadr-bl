#!/usr/bin/env sh
# Load the variables from a .env file into the current shell.
#
# The .env file of this repository writes its entries as `KEY = 'value'`, with
# spaces around the `=`. A plain `source .env` chokes on that, because the shell
# reads `KEY` as a command instead of an assignment. The spaces are therefore
# stripped before the entries are evaluated.
#
# python-decouple reads os.environ before it looks for a .env file, so exporting
# the variables this way is enough for `src.config` to pick them up, regardless
# of the directory the interpreter is started from.
#
# Usage:
#   source scripts/dotenv.sh                        # loads ./.env
#   source scripts/dotenv.sh path/to/other.env      # loads a specific file
#   source scripts/dotenv.sh && poetry run python -m src.main
#
# This script has to be sourced. Executing it exports the variables into a
# subshell that exits immediately afterwards.

_dotenv_file="${1:-.env}"

if [ ! -f "$_dotenv_file" ]; then
    echo "dotenv: $_dotenv_file not found" >&2
    unset _dotenv_file
    false
else
    set -a
    eval "$(sed -E 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*/\1=/' "$_dotenv_file")"
    set +a
    unset _dotenv_file
    true
fi

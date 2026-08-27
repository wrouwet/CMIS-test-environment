#!/bin/bash
# Runs the suite and saves a full, human-readable copy of everything that
# printed to the terminal -- pytest's own PASSED/FAILED/XFAILED summary
# plus every test's verbose wire-level diagnostics (bridge.py's -s output)
# -- to test_report.txt in this directory, in addition to showing it live.
#
# Deliberately a tee to a real pytest run rather than reconstructing a
# report from pytest's internal hooks: this project's tests are meant to
# be watched live (see pytest.ini's -s and bridge.py's VERBOSE flag), and
# a tee guarantees the saved report is byte-for-byte the same thing a
# human watched, with no risk of a hook-based reconstruction dropping or
# reordering output relative to what was actually shown.
#
# set -o pipefail matters here specifically: without it, this script's
# own exit code would always be tee's (0), silently hiding a real test
# failure from anything (CI, another script) checking $? after this runs.
set -euo pipefail
cd "$(dirname "$0")"
# tee's own (first) output stream stays untouched -- colored, live, to the
# terminal, same as running pytest directly. The process-substitution
# destination is a second, independent copy with ANSI color codes
# stripped (pytest.ini forces --color=yes, which is right for a live
# terminal but leaves escape-code noise in a plain-text file) before
# it's written to test_report.txt.
.venv/bin/pytest tests/ 2>&1 | tee >(sed -E 's/\x1b\[[0-9;]*[a-zA-Z]//g' > test_report.txt)

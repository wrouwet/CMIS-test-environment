# CMIS Test Environment

A pytest-based test suite, run from a host PC, for exercising an optical
transceiver module (QSFP-DD/OSFP-style pluggable) over its management
interface, per CMIS (the Common Management Interface Specification,
QSFP-DD MSA / OIF). Sibling project to
[openbic-test-environment](https://github.com/wrouwet/openbic-test-environment)
and [mctp-test-environment](https://github.com/wrouwet/mctp-test-environment)
-- same style and philosophy, a different target protocol.

## Current status: scaffolding only, no test target yet

This repo was created before any CMIS-compliant transceiver module was
available to test against, at the user's explicit direction -- same
"build it now, verify it live once hardware exists" approach the sibling
mctp-test-environment project used successfully for its own bootstrap
phase. Right now this contains only the shared bridge client and basic
project scaffolding; the actual CMIS protocol module and tests are being
built next, sourced directly from the real CMIS specification (not
guessed), and will land in follow-up commits.

**Do not trust anything here as verified until this note is updated.**

## What this will need once hardware exists

- A FRDM-MCXA153 bridge board flashed with the firmware from
  [frdm-mcxa153-usb-i2c-hub](https://github.com/wrouwet/frdm-mcxa153-usb-i2c-hub),
  wired to the transceiver module's management I2C bus (standard 7-bit
  address 0x50, to be confirmed against the spec before being relied on
  in code).
- A CMIS-compliant transceiver module, powered and with its management
  interface accessible.

## Setup (once there's something to run)

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest tests/    # or ./run_tests.sh to also save test_report.txt
```

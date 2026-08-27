"""Python client for the FRDM-MCXA153 USB-to-I2C bridge firmware.

See https://github.com/wrouwet/frdm-mcxa153-usb-i2c-hub for the bridge
firmware itself. Talks to its USB CDC virtual COM port using its text
command protocol:

    S                                -> OK <addr> <addr> ...
    W <addr> <byte> [byte ...]       -> OK
    R <addr> <n>                     -> OK <byte> [byte ...]
    X <addr> <n> <byte> [byte ...]   -> OK <byte> [byte ...]
    I <addr> <ourAddr> <byte> ...    -> OK <byte> [byte ...]
    L <ourAddr>                      -> OK <byte> [byte ...]
    WS/RS/XS                        -> SMBus (adds/checks a trailing PEC
                                        byte) flavor of W/R/X, same args

This is a near-identical copy of the client living in the sibling
openbic-test-environment and mctp-test-environment projects (same
bridge firmware, same protocol) -- duplicated rather than imported
across repos so this project stays independently clonable/runnable on
its own, matching those projects' own "keep repos focused and
self-contained" design.

CMIS itself doesn't use the smbus_write()/smbus_read()/smbus_write_read()
SMBus-PEC methods below (added for MCTP-over-SMBus, which mandates a PEC
byte on every frame) -- CMIS modules speak plain I2C with no PEC, so
this project's own tests use plain write()/read()/write_read() instead.
Left the SMBus methods in anyway rather than stripping them, consistent
with this file staying a generic, protocol-agnostic bridge client that
happens to be reused across projects with different needs.

Auto-detects the right serial port by USB VID:PID rather than assuming
a fixed /dev/ttyACM number -- the bridge board's MCU-Link debug probe
exposes its own, unrelated ttyACM device, and which one gets which
number depends on enumeration order (a debug probe reconnecting can
swap them), not a fixed identity.

Verbose by design (see VERBOSE / _log() below): most of the real bugs
found while building the sibling IPMB suite were only findable at all
because we could see exactly what went out and came back on the wire,
and when, rather than a bare "it timed out". Printing too much here is
a deliberate trade against ever again staring at a generic timeout and
having to guess -- doubly so for this project, which starts out with
zero hardware verification (see this repo's README) and will need every
bit of wire-level visibility once real hardware testing starts.
"""

import sys
import time

import serial
from serial.tools import list_ports

try:
    import termios
    # termios.error is a plain Exception, *not* an OSError subclass (which
    # is what you'd expect from a low-level POSIX errno-style failure).
    # Found this by actually killing the link mid-command in testing (on
    # the sibling openbic-test-environment project): reset_input_buffer()
    # on a dead fd raises termios.error, and a bare `except OSError`
    # silently missed it, leaving the client hung instead of reconnecting.
    # Windows has no termios module at all, hence the guarded import.
    _LINK_BROKEN_EXCEPTIONS = (serial.SerialException, OSError, termios.error)
except ImportError:
    _LINK_BROKEN_EXCEPTIONS = (serial.SerialException, OSError)

USB_VID = 0x1FC9
USB_PID = 0x0094
USB_PRODUCT = "MCU VIRTUAL COM DEMO"

BAUDRATE = 115200

# The bridge's "I"/"L" commands can themselves wait several seconds
# on-device (in slave-mode, listening for a target that responds by
# becoming bus master and writing back to us) before giving up, so the
# host-side serial read timeout has to comfortably exceed that, or we'd
# time out on our side before the bridge even reports its own timeout.
DEFAULT_TIMEOUT_S = 6.0

# "ERR busy" from the bridge is a *transient* condition worth retrying,
# not a real failure. Kept identical to the sibling project's tuning
# even though this project has no live-verified data yet on how MCTP's
# own response timing/retry behavior compares to IPMB's -- a reasonable
# starting point, revisit once real hardware testing starts.
BUSY_RETRIES = 6
BUSY_RETRY_DELAY_S = 1.0

# How long to keep looking for the bridge to reappear after the serial
# link itself breaks (as opposed to a normal in-protocol error like a NAK
# or busy) -- e.g. the board resets and its USB re-enumerates, possibly
# under a different /dev/ttyACM path.
RECONNECT_TIMEOUT_S = 15.0
RECONNECT_POLL_S = 0.5

# Once physically reconnected, retry the *command* itself this many
# times -- covers "reconnected to the port, but the board's firmware is
# still mid-boot and not yet accepting commands".
RECONNECT_COMMAND_RETRIES = 2

# See _log(): flip to False to quiet the wire-level trace.
VERBOSE = True


def _log(msg):
    if VERBOSE:
        print(f"[bridge] {msg}", file=sys.stderr)


class BridgeError(Exception):
    """Raised when the bridge reports an error or doesn't respond."""


class BridgeDisconnected(BridgeError):
    """The bridge's serial link is gone and didn't come back in time.

    Deliberately a distinct type from a plain BridgeError (an in-protocol
    failure, or a normal command timeout with the link still up) so
    callers -- and test reports -- can immediately tell "the board is
    actually gone" apart from "the board answered, just not the way we
    wanted".
    """


def find_port():
    """Return the device path of the FRDM-MCXA153 USB-to-I2C hub's CDC port.

    Always re-scans live rather than caching a path, specifically so a
    reconnect after the device re-enumerates under a new /dev/ttyACM
    number picks up the new one automatically.
    """
    for p in list_ports.comports():
        if p.vid == USB_VID and p.pid == USB_PID:
            return p.device
    raise BridgeError(
        f"No FRDM-MCXA153 USB-I2C hub found (looking for USB VID:PID "
        f"{USB_VID:04x}:{USB_PID:04x}, '{USB_PRODUCT}'). Is it plugged in?"
    )


class I2CBridge:
    """A connection to the board's I2C bridge firmware."""

    def __init__(self, port=None, timeout=DEFAULT_TIMEOUT_S):
        self.explicit_port = port
        self.timeout = timeout
        self.port = port or find_port()
        _log(f"connecting to {self.port} at {BAUDRATE} baud")
        self.ser = serial.Serial(self.port, baudrate=BAUDRATE, timeout=timeout)
        self._settle()

    def _settle(self):
        # Give the CDC control-line-state handshake (DTR) a moment to land
        # before the firmware will start accepting commands.
        time.sleep(0.3)

    def close(self):
        self.ser.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def _still_enumerated(self):
        try:
            find_port()
            return True
        except BridgeError:
            return False

    def _reconnect(self):
        """Wait for the bridge to (re)appear and open a fresh connection to it.

        Raises BridgeDisconnected if the bridge doesn't reappear within
        RECONNECT_TIMEOUT_S.
        """
        _log("link broken -- closing old handle and waiting for the bridge to reappear")
        try:
            self.ser.close()
        except Exception:
            pass

        start = time.monotonic()
        deadline = start + RECONNECT_TIMEOUT_S
        last_error = None
        poll_count = 0
        while time.monotonic() < deadline:
            poll_count += 1
            try:
                port = self.explicit_port or find_port()
                _log(f"reconnect poll #{poll_count}: found {port}, opening...")
                self.ser = serial.Serial(port, baudrate=BAUDRATE, timeout=self.timeout)
                self.port = port
                self._settle()
                _log(f"reconnected to {port} after {time.monotonic() - start:.1f}s")
                return
            except (BridgeError, *_LINK_BROKEN_EXCEPTIONS) as exc:
                last_error = exc
                _log(f"reconnect poll #{poll_count}: not yet ({exc}); "
                     f"retrying in {RECONNECT_POLL_S}s")
                time.sleep(RECONNECT_POLL_S)

        raise BridgeDisconnected(
            f"bridge did not reappear within {RECONNECT_TIMEOUT_S}s of the "
            f"serial link breaking (last error: {last_error}) -- is the "
            f"board actually unplugged/powered off, rather than just resetting?"
        )

    def _command(self, line, retries=BUSY_RETRIES):
        """Send one command and return the raw reply line."""
        for reconnect_attempt in range(RECONNECT_COMMAND_RETRIES + 1):
            try:
                for attempt in range(retries + 1):
                    t0 = time.monotonic()
                    self.ser.reset_input_buffer()
                    self.ser.write((line + "\r\n").encode("ascii"))
                    _log(f"-> {line!r}")
                    raw = self.ser.readline()
                    elapsed = time.monotonic() - t0
                    if not raw:
                        still_present = self._still_enumerated()
                        status = ("still enumerated, just didn't answer in time"
                                  if still_present else
                                  "no longer enumerated -- looks disconnected")
                        _log(f"<- (no reply after {elapsed:.1f}s; {status})")
                        raise BridgeError(
                            f"no response from bridge to command {line!r} "
                            f"(timed out after {self.ser.timeout}s; {status})"
                        )
                    reply = raw.decode("ascii", errors="replace").strip()
                    _log(f"<- {reply!r} ({elapsed:.2f}s)")
                    if reply != "ERR busy":
                        return reply
                    if attempt == retries:
                        _log(f"still busy after {retries} retries, giving up on this command")
                        return reply
                    _log(f"busy (attempt {attempt + 1}/{retries}), "
                         f"retrying in {BUSY_RETRY_DELAY_S}s")
                    time.sleep(BUSY_RETRY_DELAY_S)
            except _LINK_BROKEN_EXCEPTIONS as exc:
                _log(f"link exception mid-command ({exc!r})")
                if reconnect_attempt == RECONNECT_COMMAND_RETRIES:
                    raise
                self._reconnect()
                _log(f"retrying command {line!r} after reconnect "
                     f"(attempt {reconnect_attempt + 1}/{RECONNECT_COMMAND_RETRIES})")
        raise AssertionError("unreachable")  # satisfies linters

    @staticmethod
    def _split_ok(reply, what):
        parts = reply.split()
        if not parts or parts[0] != "OK":
            raise BridgeError(f"{what}: {reply}")
        return parts[1:]

    def scan(self):
        """Scan the I2C bus. Returns a sorted list of 7-bit addresses that ACKed."""
        parts = self._split_ok(self._command("S"), "bus scan failed")
        return sorted(int(x, 16) for x in parts)

    def probe(self, addr):
        """Return True if a device at the given 7-bit address ACKs."""
        return addr in self.scan()

    def write(self, addr, data):
        """Write bytes (an iterable of ints 0-255) to the given address."""
        payload = " ".join(f"{b:02x}" for b in data)
        cmd = f"W {addr:02x} {payload}".strip()
        reply = self._command(cmd)
        if reply != "OK":
            raise BridgeError(f"write to 0x{addr:02x} failed: {reply}")

    def read(self, addr, n):
        """Read n bytes from the given address. Returns bytes."""
        parts = self._split_ok(self._command(f"R {addr:02x} {n}"),
                                f"read from 0x{addr:02x} failed")
        return bytes(int(x, 16) for x in parts)

    def write_read(self, addr, data, n):
        """Write bytes, repeated-start, then read n bytes (register-read pattern)."""
        payload = " ".join(f"{b:02x}" for b in data)
        cmd = f"X {addr:02x} {n} {payload}".strip()
        parts = self._split_ok(self._command(cmd),
                                f"write_read to 0x{addr:02x} failed")
        return bytes(int(x, 16) for x in parts)

    def smbus_write(self, addr, data, retries=BUSY_RETRIES):
        """SMBus write: like write(), but the bridge computes and appends a
        correct PEC (Packet Error Check, CRC-8) byte after `data`
        automatically -- see the bridge firmware's "SMBus (PEC) support"
        README section for exactly what the CRC covers.

        `retries` defaults to the normal BUSY_RETRIES behavior, but can
        be overridden -- in particular, retries=0 makes an immediate
        "ERR busy" raise right away instead of silently retrying for up
        to several seconds. That matters for tests deliberately racing
        two closely-timed writes against each other (see
        test_queue_behavior.py): the normal multi-second busy-retry
        delay can itself cause a *different* request's response to be
        missed (arriving and going uncaptured while this call is still
        blocked retrying), which would masquerade as a target-side
        "dropped response" bug that's actually just this client's own
        retry timing getting in the way.
        """
        payload = " ".join(f"{b:02x}" for b in data)
        cmd = f"WS {addr:02x} {payload}".strip()
        reply = self._command(cmd, retries=retries)
        if reply != "OK":
            raise BridgeError(f"SMBus write to 0x{addr:02x} failed: {reply}")

    def smbus_read(self, addr, n):
        """SMBus read: like read(), but the bridge reads one extra trailing
        byte and verifies it as PEC before returning just the n requested
        data bytes. Raises BridgeError (message starts with "ERR pec") if
        the device's PEC byte doesn't match what the bridge computed."""
        parts = self._split_ok(self._command(f"RS {addr:02x} {n}"),
                                f"SMBus read from 0x{addr:02x} failed")
        return bytes(int(x, 16) for x in parts)

    def smbus_write_read(self, addr, data, n):
        """SMBus write_read: like write_read(), but PEC covers the WHOLE
        transaction (write address+data, repeated start, read
        address+data) as one continuous CRC, verified against a trailing
        PEC byte after the n requested read bytes."""
        payload = " ".join(f"{b:02x}" for b in data)
        cmd = f"XS {addr:02x} {n} {payload}".strip()
        parts = self._split_ok(self._command(cmd),
                                f"SMBus write_read to 0x{addr:02x} failed")
        return bytes(int(x, 16) for x in parts)

    def ipmb_request(self, addr, our_addr, payload):
        """Write bytes to addr, then briefly become an I2C slave at
        our_addr and capture whatever addr writes back.

        Despite the name (kept for consistency with the sibling
        openbic-test-environment project, where this exists specifically
        for IPMB), this is a transport-layer primitive with nothing IPMB-
        specific about it: it's for any target that responds by becoming
        bus master itself and writing its response out to whichever
        address the request named as the requester -- confirmed to be
        exactly how this platform's MCTP-over-SMBus responder behaves
        too (same pattern IPMB uses), per the peer session developing
        this OpenBIC port. Returns the captured response bytes, PEC byte
        included -- see mctp.py's response-parsing functions to verify
        and strip it; this method itself does no MCTP or PEC awareness.
        """
        hexstr = " ".join(f"{b:02x}" for b in payload)
        cmd = f"I {addr:02x} {our_addr:02x} {hexstr}".strip()
        parts = self._split_ok(self._command(cmd),
                                f"request to 0x{addr:02x} failed")
        return bytes(int(x, 16) for x in parts)

    def listen(self, our_addr):
        """Become an I2C slave at our_addr and capture whatever some other
        master writes to us, with no write of our own first. Returns the
        captured bytes."""
        parts = self._split_ok(self._command(f"L {our_addr:02x}"),
                                f"listen at 0x{our_addr:02x} failed")
        return bytes(int(x, 16) for x in parts)

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest

from bridge import I2CBridge


@pytest.fixture(scope="session")
def bridge():
    """A connection to the FRDM-MCXA153 USB-to-I2C bridge, shared across tests."""
    b = I2CBridge()
    yield b
    b.close()


@pytest.fixture(scope="session")
def module_info(bridge):
    """Session-scoped discovery of the module's self-reported CMIS
    revision and memory model -- see cmis_helpers.discover_module().
    Read and printed once per session (these are identity facts, not
    something expected to change mid-run); tests needing to gate
    behavior on the discovered version/capabilities should depend on
    this fixture rather than assuming a specific CMIS revision.
    """
    import cmis_helpers

    return cmis_helpers.discover_module(bridge)

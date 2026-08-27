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

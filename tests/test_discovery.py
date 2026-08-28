"""CMIS's own on-the-wire discovery mechanism: the CmisRevision byte and
MemoryModel bit in Lower Memory, which every module self-reports.

Per explicit user direction (2026-08-27): since CMIS provides this real
discovery protocol, this project does NOT maintain separate hardcoded
test suites per CMIS version (4.0, 5.0, 5.2, ...). Instead, it discovers
the module's actual revision/memory model at the start of a run, prints
exactly what it found (see cmis_helpers.discover_module()), and the rest
of the suite is expected to adapt -- skipping cleanly with a printed
reason where a page or field genuinely isn't supported by the
discovered version/model, rather than hardcoding version-specific
assumptions or failing on something that was never claimed to exist.

Named test_discovery.py (collects between test_bus.py and
test_lower_memory.py alphabetically) so discovery output appears early
in a run, before anything that depends on it.
"""


def test_discover_module_capabilities(module_info):
    """Triggers (via the module_info fixture) and surfaces CMIS's own
    discovery data. The fixture itself already prints a human-readable
    summary as it reads it; this test's job is mostly to make that
    printing happen up front and to sanity-check the discovered data is
    at least internally coherent -- not to re-assert facts already
    covered in more depth by test_lower_memory.py.
    """
    print(f"full discovered module_info: {module_info}")
    assert module_info["cmis_revision_major"] is not None
    assert module_info["memory_model"] in (0, 1), (
        f"MemoryModel bit decoded to {module_info['memory_model']!r}, expected 0 or 1 "
        f"-- if this fires, the bit-decoding itself is broken, not the module"
    )

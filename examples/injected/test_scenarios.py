"""Intentionally failing demonstration suite; excluded from FlakeGuard's testpaths."""

import os
import socket

import pytest

ROUND = int(os.environ.get("FLAKEGUARD_SCENARIO_RUN", "0"))


def test_consistently_passing():
    assert sum([2, 3]) == 5


def test_deterministic_assertion():
    assert 2 + 2 == 5, "Injected assertion regression"


def test_intermittent_timing():
    # Controlled scheduler model: completed work must precede the deadline.
    completion_ms = 120 if ROUND % 3 == 0 else 40
    assert completion_ms < 100, "TimeoutError: injected operation missed deadline"


def test_temporary_connection():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        if ROUND % 4:
            listener.listen()
        # A bound non-listening socket reliably refuses connections without an external service.
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            pass


def test_shared_state_contamination():
    cart = ["previous-test-item"] if ROUND % 2 == 0 else []
    assert cart == [], "shared state contamination: cart not cleaned between tests"


@pytest.fixture
def customer():
    if ROUND % 5 == 0:
        pytest.fail("fixture setup failed: injected unavailable seed")
    return {"id": "customer-1"}


def test_setup_failure(customer):
    assert customer["id"]

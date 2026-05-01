from app.protocol import parse_client_message


def test_valid_message_parses_with_payload():
    parsed = parse_client_message({"type": "move", "payload": {"q": 1, "r": 2}})

    assert parsed == ("move", {"q": 1, "r": 2})


def test_missing_payload_defaults_to_empty_dict():
    parsed = parse_client_message({"type": "ping"})

    assert parsed == ("ping", {})


def test_invalid_message_type_is_rejected():
    parsed = parse_client_message({"type": "not-real", "payload": {}})

    assert parsed == "Unknown message type"


def test_invalid_payload_is_rejected():
    parsed = parse_client_message({"type": "move", "payload": "bad"})

    assert parsed == "Invalid payload"

from ws_sync.session import Session, session_context


def test_single_session_context():
    """Test that a single session sets and resets the context correctly."""
    session = Session()

    assert session_context.get(None) is None

    with session:
        assert session_context.get() is session

    assert session_context.get(None) is None


def test_nested_same_session():
    """Test that re-entering the same session maintains context and cleans up only at the end."""
    session = Session()

    assert session_context.get(None) is None

    with session:
        assert session_context.get() is session

        with session:
            assert session_context.get() is session

            with session:
                assert session_context.get() is session

            # Should still be the session after one exit
            assert session_context.get() is session

        # Should still be the session after two exits
        assert session_context.get() is session

    # Should be clean after all exits
    assert session_context.get(None) is None


def test_nested_different_sessions():
    """Test that nesting different sessions correctly switches context and restores it."""
    session1 = Session()
    session2 = Session()

    assert session_context.get(None) is None

    with session1:
        assert session_context.get() is session1

        with session2:
            assert session_context.get() is session2

            # Nest session1 again inside session2
            with session1:
                assert session_context.get() is session1

            # Should return to session2
            assert session_context.get() is session2

        # Should return to session1
        assert session_context.get() is session1

    assert session_context.get(None) is None


def test_interleaved_sessions():
    """Test complex interleaving of different sessions."""
    s1 = Session()
    s2 = Session()
    s3 = Session()

    with s1:
        assert session_context.get() is s1
        with s2:
            assert session_context.get() is s2
            with s3:
                assert session_context.get() is s3
            assert session_context.get() is s2
        assert session_context.get() is s1

    assert session_context.get(None) is None

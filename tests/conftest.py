"""
Pytest configuration and shared fixtures for ws-sync tests.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from ws_sync.session import Session, session_context

from .utils import Company, Team, User


@pytest.fixture
def mock_session() -> Mock:
    """Create a mock session for testing"""
    session = Mock(spec=Session)
    session.send = AsyncMock()
    session.register_event = Mock()
    session.register_init = Mock()
    session.deregister_event = Mock()
    session.is_connected = True

    session_context.set(session)
    return session


@pytest.fixture
def sample_user() -> User:
    """Create a sample user for testing"""
    return User(name="John Doe", age=30, email="john@example.com")


@pytest.fixture
def sample_team(sample_user: User) -> Team:
    """Create a sample team for testing"""
    return Team(
        name="Engineering",
        members=[sample_user, User(name="Jane Smith", age=25)],
        leader=sample_user,
    )


@pytest.fixture
def sample_company(sample_team: Team) -> Company:
    """Create a sample company for testing"""
    return Company(
        name="Tech Corp",
        teams=[sample_team],
        employees={"john": sample_team.members[0], "jane": sample_team.members[1]},
    )

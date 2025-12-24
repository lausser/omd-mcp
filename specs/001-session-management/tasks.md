# Tasks: Authenticated Session Management

**Input**: Design documents from `/specs/001-session-management/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), data-model.md, contracts/

**Tests**: Tests are included per feature specification requirements (FR-004, SC-007 require verification)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Chatbot service**: `chatbot/` at repository root
- **Thruk MCP service**: `thruk_mcp/` at repository root
- **Tests**: `tests/` at repository root

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create chatbot directory structure (chatbot/, chatbot/templates/)
- [x] T002 Create thruk_mcp directory structure
- [x] T003 Create tests directory structure (tests/chatbot/, tests/integration/)
- [x] T004 [P] Update chatbot/requirements.txt with FastAPI, FastMCP, uvicorn, Jinja2, pytest dependencies
- [x] T005 [P] Update .env.example with SESSION_TIMEOUT_MINUTES=15, DEFAULT_USERNAME=chatuser, SESSION_CLEANUP_INTERVAL_SECONDS=60
- [x] T006 [P] Create tests/requirements.txt with pytest, pytest-asyncio, pytest-mock, freezegun, httpx

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T007 Create UserSession data model class in chatbot/session_manager.py with attributes (session_id, username, created_at, last_activity, mcp_connection, llm_connection, conversation_history, is_active)
- [x] T008 Implement UserSession.is_expired() method to check if now() - last_activity > 15 minutes
- [x] T009 Implement UserSession.update_activity() method to set last_activity = now()
- [x] T010 Implement UserSession.cleanup() method to close MCP and LLM connections, clear conversation_history
- [x] T011 Create SessionStore class in chatbot/session_manager.py with sessions dict and threading.Lock
- [x] T012 Implement SessionStore.create_session(username) method generating unique session_id with secrets.token_urlsafe(32)
- [x] T013 Implement SessionStore.get_session(session_id) method with thread-safe dict access
- [x] T014 Implement SessionStore.update_activity(session_id) method
- [x] T015 Implement SessionStore.cleanup_expired_sessions() method iterating sessions and calling cleanup on expired ones
- [x] T016 Create Message data model class in chatbot/session_manager.py with role, content, timestamp, metadata attributes

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - User Authentication and Session Initialization (Priority: P1) 🎯 MVP

**Goal**: Users authenticate and start chatbot sessions with their own privileges

**Independent Test**: Authenticate via Apache or standalone mode, verify username in UI, confirm unique session created

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T017 [P] [US1] Create test_session_manager.py in tests/chatbot/ with test_create_session_with_username
- [x] T018 [P] [US1] Add test_create_session_default_username to verify "chatuser" default in tests/chatbot/test_session_manager.py
- [x] T019 [P] [US1] Add test_session_isolation to verify independent sessions for different users in tests/chatbot/test_session_manager.py
- [x] T020 [P] [US1] Create test_username_propagation.py in tests/integration/ with test_username_passed_to_mcp_tools

### Implementation for User Story 1

- [x] T021 Create FastAPI application in chatbot/chatbot.py with basic app initialization
- [x] T022 [US1] Add X-WEBAUTH-USER header extraction function in chatbot/chatbot.py (FR-001, FR-002)
- [x] T023 [US1] Implement session creation endpoint GET / in chatbot/chatbot.py that extracts username and calls SessionStore.create_session()
- [x] T024 [US1] Set session_id cookie in response (HttpOnly, SameSite=Lax) in chatbot/chatbot.py
- [x] T025 [P] [US1] Create HTML template chatbot/templates/index.html with username display element
- [x] T026 [P] [US1] Add Jinja2 template rendering in chatbot/chatbot.py GET / endpoint to pass username to template (FR-004)
- [x] T027 [US1] Implement session middleware in chatbot/chatbot.py to extract session_id from cookies on all requests
- [x] T028 [US1] Add MCP client initialization in UserSession when invoking Thruk MCP tools in chatbot/chatbot.py
- [x] T029 [US1] Modify MCP tool invocation in chatbot/chatbot.py to include username parameter (FR-005)
- [x] T030 [P] [US1] Add structured logging for session creation events in chatbot/session_manager.py (JSON format)

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Session Timeout Protection (Priority: P2)

**Goal**: Sessions automatically expire after inactivity for security and resource management

**Independent Test**: Create session, wait 15 minutes, verify timeout message and disabled UI

### Tests for User Story 2 ⚠️

- [ ] T031 [P] [US2] Create test_timeout.py in tests/chatbot/ with test_session_expires_after_15_minutes using freezegun
- [ ] T032 [P] [US2] Add test_activity_resets_timeout to verify last_activity updates in tests/chatbot/test_timeout.py
- [ ] T033 [P] [US2] Add test_multiple_sessions_timeout_independently in tests/chatbot/test_timeout.py

### Implementation for User Story 2

- [ ] T034 [US2] Implement session expiration check in chatbot/chatbot.py session middleware calling session.is_expired()
- [ ] T035 [US2] Add session timeout error response (401 with "session_expired" error and message) in chatbot/chatbot.py (FR-009)
- [ ] T036 [US2] Implement activity tracking on all user interactions in chatbot/chatbot.py calling session.update_activity() (FR-006, FR-013)
- [ ] T037 [US2] Add JavaScript to chatbot/templates/index.html to disable submit buttons on session timeout (FR-008)
- [ ] T038 [US2] Add timeout message display in chatbot/templates/index.html showing "session has ended after inactivity" (FR-009)
- [ ] T039 [US2] Implement /api/session/status endpoint in chatbot/chatbot.py returning session expiration info
- [ ] T040 [US2] Add JavaScript heartbeat mechanism in chatbot/templates/index.html calling /api/session/heartbeat periodically
- [ ] T041 [P] [US2] Add structured logging for session timeout events in chatbot/session_manager.py

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Resource Cleanup on Timeout (Priority: P3)

**Goal**: Session resources properly cleaned up on timeout to prevent leaks

**Independent Test**: Monitor resources before/after timeout, verify MCP and AI connections closed

### Tests for User Story 3 ⚠️

- [ ] T042 [P] [US3] Create test_cleanup.py in tests/chatbot/ with test_mcp_connection_closed_on_timeout
- [ ] T043 [P] [US3] Add test_llm_connection_closed_on_timeout in tests/chatbot/test_cleanup.py
- [ ] T044 [P] [US3] Add test_conversation_history_cleared_on_timeout in tests/chatbot/test_cleanup.py
- [ ] T045 [P] [US3] Add test_multiple_concurrent_cleanups in tests/chatbot/test_cleanup.py

### Implementation for User Story 3

- [ ] T046 [US3] Implement background cleanup task in chatbot/chatbot.py using asyncio.create_task() calling SessionStore.cleanup_expired_sessions() every 60s
- [ ] T047 [US3] Add MCP connection close logic in UserSession.cleanup() method in chatbot/session_manager.py (FR-010)
- [ ] T048 [US3] Add LLM connection close logic in UserSession.cleanup() method in chatbot/session_manager.py (FR-011)
- [ ] T049 [US3] Add conversation_history.clear() in UserSession.cleanup() method in chatbot/session_manager.py (FR-012)
- [ ] T050 [US3] Remove session from SessionStore.sessions dict after cleanup in chatbot/session_manager.py
- [ ] T051 [P] [US3] Add structured logging for cleanup events (connections closed, memory freed) in chatbot/session_manager.py
- [ ] T052 [P] [US3] Add error handling for cleanup failures (log error but don't crash) in chatbot/session_manager.py

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: Thruk MCP Server Extensions

**Purpose**: Add username parameter to Thruk MCP tools for authorization

- [ ] T053 [P] Add username parameter (default="chatuser") to thruk_list_hosts tool in thruk_mcp/thruk_mcp.py (FR-015)
- [ ] T054 [P] Add username parameter to thruk_list_services tool in thruk_mcp/thruk_mcp.py
- [ ] T055 [P] Add username parameter to thruk_list_hostgroups tool in thruk_mcp/thruk_mcp.py
- [ ] T056 [P] Add username parameter to thruk_list_servicegroups tool in thruk_mcp/thruk_mcp.py
- [ ] T057 [P] Add username parameter to thruk_list_downtimes tool in thruk_mcp/thruk_mcp.py
- [ ] T058 [P] Add username parameter to thruk_schedule_host_downtime tool in thruk_mcp/thruk_mcp.py
- [ ] T059 [P] Add username parameter to thruk_schedule_service_downtime tool in thruk_mcp/thruk_mcp.py
- [ ] T060 [P] Add username parameter to thruk_schedule_hostgroup_downtime tool in thruk_mcp/thruk_mcp.py
- [ ] T061 [P] Add username parameter to thruk_schedule_servicegroup_downtime tool in thruk_mcp/thruk_mcp.py
- [ ] T062 [P] Update all Thruk API calls in thruk_mcp/thruk_mcp.py to pass username for authorization (FR-016, FR-017)
- [ ] T063 [P] Add structured logging for username parameter in each tool invocation in thruk_mcp/thruk_mcp.py

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T064 [P] Add comprehensive docstrings to all classes and methods in chatbot/session_manager.py
- [ ] T065 [P] Add type hints to all functions in chatbot/chatbot.py and chatbot/session_manager.py
- [ ] T066 [P] Update README.md with session management configuration variables
- [ ] T067 [P] Add session management section to quickstart.md with local testing examples
- [ ] T068 [P] Run full test suite and verify all tests pass (pytest tests/)
- [ ] T069 Add session timeout accuracy validation test verifying 15min±5s timeout (SC-003)
- [ ] T070 Add concurrent session performance test with 50 sessions (SC-002)
- [ ] T071 [P] Add username display performance test verifying <1s display time (SC-001)
- [ ] T072 [P] Add resource cleanup performance test verifying cleanup within 30s (SC-004)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - User stories can proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Thruk MCP Extensions (Phase 6)**: Can proceed in parallel with User Stories (independent service)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Builds on US1 but independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Builds on US1+US2 but independently testable

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Tests can run in parallel (all marked [P])
- Implementation tasks follow dependency order:
  - US1: Session creation → Cookie → Template → Middleware → MCP integration
  - US2: Expiration check → Error response → Activity tracking → UI updates → Heartbeat
  - US3: Background task → Connection cleanup → Memory cleanup → Error handling

### Parallel Opportunities

- All Setup tasks (T001-T006) marked [P] can run in parallel
- All Foundational tasks (T007-T016) run sequentially (same file, shared state)
- Tests within each user story marked [P] can run in parallel
- Once Foundational completes, all user stories can start in parallel (if team capacity allows)
- All Thruk MCP tool updates (T053-T063) can run in parallel (different tools, no dependencies)
- All Polish tasks marked [P] can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: T017 - test_create_session_with_username
Task: T018 - test_create_session_default_username
Task: T019 - test_session_isolation
Task: T020 - test_username_passed_to_mcp_tools

# After tests fail, launch parallel implementation tasks:
Task: T025 - Create HTML template
Task: T026 - Add template rendering
Task: T030 - Add logging

# Sequential tasks (dependencies):
T021 → T022 → T023 → T024 → T027 → T028 → T029
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T006)
2. Complete Phase 2: Foundational (T007-T016) - CRITICAL BLOCKER
3. Complete Phase 3: User Story 1 (T017-T030)
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

**MVP Deliverables**:
- Users can authenticate (Apache or standalone)
- Username displays in UI
- Isolated sessions per user
- Username passed to Thruk MCP for authorization

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo (Security hardening)
4. Add User Story 3 → Test independently → Deploy/Demo (Production-ready)
5. Add Thruk MCP Extensions in parallel → Test → Deploy
6. Polish & finalize

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together (blocking)
2. Once Foundational is done:
   - Developer A: User Story 1 (P1)
   - Developer B: User Story 2 (P2)
   - Developer C: Thruk MCP Extensions (Phase 6)
3. After US1+US2 complete:
   - Developer D: User Story 3 (P3)
   - Developer E: Polish tasks
4. Stories integrate and test independently

---

## Notes

- [P] tasks = different files, no dependencies, can parallelize
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Tests written first to verify they fail before implementation
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Constitution compliance verified in plan.md (all principles passed)

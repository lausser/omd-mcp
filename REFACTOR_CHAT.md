# Chat Application Refactoring and Bug Fixes

## 1. Executive Summary

This document outlines the analysis and recommended solutions for two critical stability issues identified in the Thruk Chatbot application. Implementing these changes will significantly improve the application's robustness and user experience.

1.  **Endless Loop on API Failure**: A logical flaw in how the application state is managed on the backend causes an endless loop if an LLM API call fails. This is the most critical issue to address.

2.  **`AttributeError` Crash with Gemini LLM**: A bug in the Gemini client code causes the application to crash when the model returns a standard text response instead of a tool call, making the Gemini integration unstable.

## 2. Analysis of the Endless Loop Bug

### 2.1 Findings: Why the Endless Loop Happens

The endless loop is triggered by a combination of expected frontend behavior and flawed backend state management.

1.  **Initial Request**: A user sends a message. The frontend immediately adds this message to the UI for a good user experience and sends it to the `/api/chat` backend endpoint.
2.  **Backend State Corruption**: The backend immediately appends the user's message to the permanent `session.conversation_history` *before* attempting the LLM API call.
3.  **API Call Fails**: The call to the LLM API fails (e.g., due to a rate limit, network issue, or temporary API outage). The backend raises an exception and returns an HTTP error (e.g., 500) to the frontend.
4.  **Inconsistent State**: At this point, the application is in an inconsistent state. The backend's session history contains the user's message from the failed request, but the frontend has not received a successful response.
5.  **Client Retry**: The frontend client, upon receiving an error, may allow the user to retry. When the user resubmits the same message, the backend receives it again and appends it *a second time* to the already-polluted history.
6.  **The Loop**: This cycle repeats. Each failed attempt adds another copy of the user's message to the history, making subsequent requests larger and more likely to fail, leading to an inescapable loop of failing requests.

### 2.2 What's Wrong with the Python Code

The core issue is that the update to the conversation history is **not atomic**. The user's message is saved separately from the assistant's response, and its addition is not contingent on the success of the entire operation.

**Problematic Code in `chat()` function in `chatbot/chatbot.py`:**
```python
    # THIS IS THE PROBLEM: The user's message is added to the history immediately.
    session.conversation_history.append(
        Message(role="user", content=user_message)
    )

    # Call LLM with conversation history (with MCP tool support)
    try:
        # If this call fails, the user message above remains in the history.
        assistant_response, tool_calls = await call_llm(session.conversation_history, session.username)
    except HTTPException:
        # Re-raise HTTP exceptions (already logged in call_llm)
        raise
    # ... more code ...

    # The assistant's response is added much later.
    if assistant_response:
        session.conversation_history.append(
            Message(role="assistant", content=assistant_response)
        )
```

### 2.3 What's Wrong with the JavaScript Code

**There is nothing fundamentally wrong with the JavaScript code.** The frontend's behavior is correct and user-friendly.

-   **Immediate Display**: The user's message is displayed immediately for responsiveness (`addMessage('user', message);`). This is the expected behavior in a modern chat application.
-   **Error Handling**: It correctly handles errors from the API and displays them to the user.

The frontend is not the cause of the loop; it is merely an actor in the sequence. The root cause is the backend's inability to handle the request atomically.

## 3. Analysis of the Gemini `AttributeError` Bug

### 3.1 Findings

When the Gemini LLM returns a standard text answer, the `Part` object in its response has a `function_call` attribute that is explicitly set to `None`. The Python code checks for the *existence* of this attribute (`hasattr(part, 'function_call')`) but does not check if its *value* is `None`. This leads to an `AttributeError: 'NoneType' object has no attribute 'name'` when the code tries to access `part.function_call.name`, crashing the request.

### 3.2 What's Wrong with the Python Code

The check is insufficient. `hasattr()` returns `True` even if the attribute's value is `None`.

**Problematic Code in `call_llm_gemini()` in `chatbot/chatbot.py`:**
```python
# This check is not sufficient
if hasattr(part, 'function_call'):
    # This line crashes if part.function_call is None
    logger.info(f"    Function call: {part.function_call.name}")
```

## 4. Suggested Refactoring and Changes

A developer should apply the following changes to create a stable and robust application.

### 4.1 Step 1: Fix the Gemini `AttributeError`

**Goal**: Prevent the application from crashing on valid text responses from Gemini.

-   **File**: `chatbot/chatbot.py`
-   **Function**: `call_llm_gemini`

**Action**: Modify the conditional statement to check if `part.function_call` has a "truthy" value, not just that the attribute exists.

**Current Code:**
```python
                        # Log function calls if present
                        if hasattr(part, 'function_call'):
```
**New Code:**
```python
                        # Log function calls if present
                        if hasattr(part, 'function_call') and part.function_call:
```

### 4.2 Step 2: Implement Atomic Conversation History Updates

**Goal**: Prevent the endless loop by ensuring the session state is only modified upon a completely successful transaction.

-   **File**: `chatbot/chatbot.py`
-   **Function**: `chat`

**Action**: Replace the entire `chat` function with the refactored version below. This new version creates a temporary message list for the LLM call and only updates the permanent session history once the call has succeeded.

**New `chat()` Function:**
```python
@app.post("/api/chat")
async def chat(request: Request) -> Dict[str, Any]:
    """
    Send chat message to LLM.

    Processes user message, invokes Thruk MCP tools if needed (passing username),
    and returns assistant response.

    Updates session activity timestamp.

    Args:
        request: Incoming HTTP request with JSON body containing 'message' field

    Returns:
        Dictionary with 'response' (assistant message) and 'tool_calls' (MCP tools used)

    Raises:
        HTTPException: 400 if message is invalid, 401 if session expired,
                      500/503 if LLM fails
    """
    session_id = get_session_from_cookie(request)

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session cookie"
        )

    session = session_store.get_session(session_id)

    if not session or session.is_expired():
        idle_minutes = None
        if session:
            idle_seconds = (datetime.now() - session.last_activity).total_seconds()
            idle_minutes = int(idle_seconds / 60)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "session_expired",
                "message": f"Session has expired after {SESSION_TIMEOUT_MINUTES} minutes of inactivity",
                "timeout_minutes": SESSION_TIMEOUT_MINUTES,
                "idle_minutes": idle_minutes
            }
        )

    # Update activity
    session.update_activity()

    # Parse request body
    try:
        body = await request.json()
        user_message_content = body.get("message", "")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request body: {e}"
        )

    if not user_message_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty"
        )

    # Prepare messages for the LLM without modifying session history yet
    user_message = Message(role="user", content=user_message_content)
    messages_for_llm = session.conversation_history + [user_message]

    assistant_response = ""
    tool_calls = []

    logger.info(
        f"User message received from {session.username}",
        extra={
            "session_id": session_id[:8],
            "username": session.username,
            "message_length": len(user_message_content)
        }
    )
    logger.debug(
        f"Message content: {user_message_content}",
        extra={"session_id": session_id[:8], "username": session.username}
    )

    # Call LLM with conversation history (with MCP tool support)
    try:
        assistant_response, tool_calls = await call_llm(messages_for_llm, session.username)

        # On success, atomically update conversation history
        session.conversation_history.append(user_message)
        if assistant_response:
            session.conversation_history.append(
                Message(role="assistant", content=assistant_response)
            )

    except HTTPException:
        # Re-raise HTTP exceptions (already logged in call_llm)
        raise
    except Exception as e:
        logger.error(f"Unexpected error during LLM call: {e}", exc_info=True)

        # Show detailed errors to omdadmin for debugging
        if session.username == "omdadmin":
            import traceback
            error_detail = {
                "error": "LLM API Error (Admin View)",
                "type": type(e).__name__,
                "message": str(e),
                "traceback": traceback.format_exc()
            }
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail
            )
        else:
            # Generic error for regular users
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred while processing your request."
            )

    # Log assistant response at DEBUG level
    logger.debug(
        f"Assistant response: {(assistant_response or '')[:200]}...",
        extra={
            "session_id": session_id[:8],
            "username": session.username,
            "tool_calls_made": len(tool_calls)
        }
    )

    return {
        "response": assistant_response,
        "tool_calls": tool_calls
    }
```

## 5. Conclusion

By applying these two fixes, the chatbot application will be significantly more stable. The Gemini integration will work as expected, and the application will gracefully handle API errors without entering a failure loop, ensuring a consistent and reliable experience for all users.

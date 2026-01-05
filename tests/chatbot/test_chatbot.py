import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from chatbot.chatbot import call_llm

# Mock CallToolResult class to simulate fastmcp client response
class MockCallToolResult:
    def __init__(self, result_data):
        self.result = result_data

    def __repr__(self):
        return f"MockCallToolResult(result={self.result})"

# Test case for handling CallToolResult object
@pytest.mark.asyncio
async def test_call_llm_with_tool_call_result_object():
    """
    Verify that call_llm correctly handles a CallToolResult object
    returned by call_mcp_tool without raising a serialization error.
    """
    conversation_history = [MagicMock(role="user", content="list hosts")]
    username = "testuser"

    # 1. Mock the first LLM response to request a tool call
    mock_tool_call = MagicMock()
    mock_tool_call.id = "tool_call_123"
    mock_tool_call.function.name = "thruk_list_hosts"
    mock_tool_call.function.arguments = "{}"

    mock_choice = MagicMock()
    mock_choice.finish_reason = "tool_calls"
    mock_choice.message.tool_calls = [mock_tool_call]
    mock_choice.message.content = None

    mock_response1 = MagicMock()
    mock_response1.choices = [mock_choice]

    # 2. Mock the second LLM response (after tool call)
    mock_choice2 = MagicMock()
    mock_choice2.message.content = "Here are the hosts."

    mock_response2 = MagicMock()
    mock_response2.choices = [mock_choice2]

    # Mock the openai client to return the two responses in order
    mock_openai_client = AsyncMock()
    mock_openai_client.chat.completions.create.side_effect = [
        mock_response1,
        mock_response2,
    ]

    # 3. Mock call_mcp_tool to return our mock object
    mock_tool_result_data = {"hosts": ["host1", "host2"]}
    mock_mcp_result = MockCallToolResult(mock_tool_result_data)

    with patch('chatbot.chatbot.openai_client', mock_openai_client), \
         patch('chatbot.chatbot.get_mcp_tools', new_callable=AsyncMock, return_value=[{"type": "function", "function": {"name": "thruk_list_hosts"}}]), \
         patch('chatbot.chatbot.call_mcp_tool', new_callable=AsyncMock, return_value=mock_mcp_result) as mock_call_mcp:

        # Call the function under test
        assistant_response, tool_calls_made = await call_llm(conversation_history, username)

        # Assertions
        # It should successfully call the mcp tool
        mock_call_mcp.assert_called_once_with("thruk_list_hosts", {}, username)

        # It should return the final message from the LLM
        assert assistant_response == "Here are the hosts."

        # It should log the tool call correctly
        assert len(tool_calls_made) == 1
        assert tool_calls_made[0]["tool"] == "thruk_list_hosts"
        # The fix ensures this is the serializable dict, not the wrapper object
        assert tool_calls_made[0]["result"] == mock_tool_result_data

        # Check that the 'content' passed to the second LLM call is a JSON string
        final_llm_call_messages = mock_openai_client.chat.completions.create.call_args[1]['messages']
        tool_message = next(msg for msg in final_llm_call_messages if msg['role'] == 'tool')

        import json
        assert json.loads(tool_message['content']) == mock_tool_result_data

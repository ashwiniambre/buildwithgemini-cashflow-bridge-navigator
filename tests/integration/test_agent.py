# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import root_agent


def test_agent_stream() -> None:
    """
    Integration test for the agent stream functionality.
    Tests that the agent returns valid streaming responses.
    """

    session_service = InMemorySessionService()

    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user", parts=[types.Part.from_text(text="Why is the sky blue?")]
    )

    events = list(
        runner.run(
            new_message=message,
            user_id="test_user",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        )
    )
    assert len(events) > 0, "Expected at least one message"

    has_text_content = False
    for event in events:
        if (
            event.content
            and event.content.parts
            and any(part.text for part in event.content.parts)
        ):
            has_text_content = True
            break
    assert has_text_content, "Expected at least one message with text content"


def test_agent_engine_sandbox_code_executor() -> None:
    """Tests that AgentEngineSandboxCodeExecutor is properly attached to root_agent and executes code."""
    from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor

    assert root_agent.code_executor is not None
    assert isinstance(root_agent.code_executor, AgentEngineSandboxCodeExecutor)
    assert root_agent.code_executor.sandbox_resource_name is not None
    assert "sandboxEnvironments" in root_agent.code_executor.sandbox_resource_name

    # Execute a test Python calculation in the Agent Engine Sandbox environment
    client = root_agent.code_executor._get_api_client()
    result = client.agent_engines.sandboxes.execute_code(
        name=root_agent.code_executor.sandbox_resource_name,
        input_data={"code": "print(2 + 2)"},
    )
    assert len(result.outputs) > 0
    output_str = result.outputs[0].data.decode("utf-8")
    assert "4" in output_str

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.app.apps.advanced_chat import generate_task_pipeline as pipeline_module
from core.app.apps.advanced_chat.generate_task_pipeline import AdvancedChatAppGenerateTaskPipeline
from models import AppMode


def test_handle_workflow_started_event_uses_run_id_for_token_record(monkeypatch):
    pipeline = AdvancedChatAppGenerateTaskPipeline.__new__(AdvancedChatAppGenerateTaskPipeline)
    pipeline._workflow_run_id = ""
    pipeline._workflow_id = "workflow-1"
    pipeline._message_id = "message-1"
    pipeline._application_generate_entity = SimpleNamespace(
        extras={"app_token_id": "token-1"},
        task_id="task-1",
    )
    pipeline._workflow_response_converter = SimpleNamespace(
        workflow_start_to_stream_response=MagicMock(return_value="workflow-start-response")
    )
    pipeline._resolve_graph_runtime_state = MagicMock(return_value=object())
    pipeline._extract_workflow_run_id = MagicMock(return_value="run-123")

    message = SimpleNamespace(workflow_run_id=None)
    pipeline._get_message = MagicMock(return_value=message)

    @contextmanager
    def fake_database_session():
        yield MagicMock()

    pipeline._database_session = fake_database_session

    calls: list[dict] = []

    class FakeApiTokenMessageJoinsExtend:
        def __init__(self, *, app_token_id: str, record_id: str, app_mode: str):
            calls.append(
                {
                    "app_token_id": app_token_id,
                    "record_id": record_id,
                    "app_mode": app_mode,
                }
            )

        def add_app_token_record_id(self):
            return None

    monkeypatch.setattr(pipeline_module, "ApiTokenMessageJoinsExtend", FakeApiTokenMessageJoinsExtend)

    responses = list(pipeline._handle_workflow_started_event(event=MagicMock()))

    assert responses == ["workflow-start-response"]
    assert pipeline._workflow_run_id == "run-123"
    assert message.workflow_run_id == "run-123"
    assert calls == [
        {
            "app_token_id": "token-1",
            "record_id": "run-123",
            "app_mode": AppMode.ADVANCED_CHAT.value,
        }
    ]


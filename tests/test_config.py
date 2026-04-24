import pytest
from unittest.mock import patch
from pydantic import BaseModel
from config import call_llm_json

class MockSchema(BaseModel):
    name: str
    age: int

def test_call_llm_json_strips_markdown():
    json_str = '{"name": "Alice", "age": 30}'
    
    mock_responses = [
        f"```json\n{json_str}\n```",
        f"```\n{json_str}\n```",
        f"{json_str}",
        f"   {json_str}   ",
        f"```json\n{json_str}\n```   "
    ]
    
    for resp in mock_responses:
        with patch('config.call_llm', return_value=resp):
            result = call_llm_json("system", "user", MockSchema)
            assert isinstance(result, MockSchema)
            assert result.name == "Alice"
            assert result.age == 30

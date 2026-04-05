import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bin'))

from obsidian_sync import parse_transcript, compress_transcript

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_transcript.jsonl')


def test_parse_transcript_extracts_messages():
    messages = parse_transcript(FIXTURE_PATH)
    user_msgs = [m for m in messages if m['type'] == 'user']
    assistant_msgs = [m for m in messages if m['type'] == 'assistant']
    assert len(user_msgs) >= 1
    assert len(assistant_msgs) >= 1


def test_parse_transcript_extracts_metadata():
    messages = parse_transcript(FIXTURE_PATH)
    first_user = next(m for m in messages if m['type'] == 'user')
    assert first_user['session_id'] == 'sess-abc123'
    assert first_user['cwd'] == '/c/dev_projects/testproj'
    assert first_user['git_branch'] == 'main'


def test_parse_transcript_skips_non_message_types():
    messages = parse_transcript(FIXTURE_PATH)
    types = {m['type'] for m in messages}
    assert 'file-history-snapshot' not in types
    assert 'progress' not in types
    assert 'system' not in types


def test_parse_transcript_extracts_timestamps():
    messages = parse_transcript(FIXTURE_PATH)
    assert messages[0]['timestamp'] is not None
    assert messages[-1]['timestamp'] is not None


def test_compress_transcript_removes_thinking():
    messages = parse_transcript(FIXTURE_PATH)
    compressed = compress_transcript(messages)
    for msg in compressed:
        if msg['type'] == 'assistant':
            for block in msg.get('content', []):
                assert block.get('type') != 'thinking'


def test_compress_transcript_summarizes_tool_results():
    messages = parse_transcript(FIXTURE_PATH)
    compressed = compress_transcript(messages)
    for msg in compressed:
        if msg['type'] == 'user' and isinstance(msg.get('content'), list):
            for block in msg['content']:
                if block.get('type') == 'tool_result':
                    assert len(block['content']) < 500


def test_compress_transcript_preserves_user_text():
    messages = parse_transcript(FIXTURE_PATH)
    compressed = compress_transcript(messages)
    user_text_msgs = [m for m in compressed if m['type'] == 'user' and isinstance(m.get('content'), str)]
    assert len(user_text_msgs) >= 1
    assert '배터리' in user_text_msgs[0]['content']


def test_compress_transcript_extracts_tool_uses():
    messages = parse_transcript(FIXTURE_PATH)
    compressed = compress_transcript(messages)
    tool_uses = []
    for msg in compressed:
        if msg['type'] == 'assistant':
            for block in msg.get('content', []):
                if block.get('type') == 'tool_use':
                    tool_uses.append(block)
    assert len(tool_uses) >= 1
    assert tool_uses[0]['name'] in ('Read', 'Edit')

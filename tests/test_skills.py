"""Tests for skills.py — SkillManager and YAML frontmatter parser."""
import os
from pathlib import Path

import pytest
from openclaw_lite.skills import SkillManager, _parse_yamlish


class TestParseYamlish:
    def test_scalar(self):
        text = "name: foo\ndescription: bar"
        assert _parse_yamlish(text) == {"name": "foo", "description": "bar"}

    def test_list(self):
        text = "tools:\n  - a\n  - b\n  - c"
        assert _parse_yamlish(text) == {"tools": ["a", "b", "c"]}

    def test_empty_value(self):
        text = "foo:\nbar: 1"
        assert _parse_yamlish(text) == {"foo": "", "bar": "1"}

    def test_ignores_dashes_at_top(self):
        text = "-\nname: x"
        assert _parse_yamlish(text) == {"name": "x"}


class TestSkillManager:
    def test_load_all_empty_dir(self, tmp_path):
        sm = SkillManager(skills_dir=str(tmp_path))
        loaded = sm.load_all()
        assert loaded == []

    def test_load_skill_file(self, tmp_path):
        skill_file = tmp_path / "test-skill.md"
        skill_file.write_text("""---
name: test-skill
description: A test skill
trigger: hello, hi
tools:
  - fs_read_file
---

Body here.
""")
        sm = SkillManager(skills_dir=str(tmp_path))
        loaded = sm.load_all()
        assert loaded == ["test-skill"]
        skill = sm.get_skill("test-skill")
        assert skill["description"] == "A test skill"
        assert skill["triggers"] == ["hello", "hi"]
        assert skill["tools"] == ["fs_read_file"]

    def test_match_skills(self, tmp_path):
        skill_file = tmp_path / "greet.md"
        skill_file.write_text("""---
name: greet
trigger: hello
---
""")
        sm = SkillManager(skills_dir=str(tmp_path))
        sm.load_all()
        assert sm.match_skills("say hello") == ["greet"]
        assert sm.match_skills("goodbye") == []

    def test_get_tools_for_skills(self, tmp_path):
        (tmp_path / "a.md").write_text("---\ntools:\n  - x\n---\n\nbody\n")
        (tmp_path / "b.md").write_text("---\ntools:\n  - y\n  - z\n---\n\nbody\n")
        sm = SkillManager(skills_dir=str(tmp_path))
        sm.load_all()
        tools = sm.get_tools_for_skills(["a", "b"])
        assert set(tools) == {"x", "y", "z"}

    def test_build_context_for_skills(self, tmp_path):
        (tmp_path / "ctx.md").write_text("---\nname: ctx\n---\n\nThis is the body.\n")
        sm = SkillManager(skills_dir=str(tmp_path))
        sm.load_all()
        ctx = sm.build_context_for_skills(["ctx"])
        assert "Matched Skills:" in ctx
        assert "This is the body." in ctx

    def test_disk_snapshot(self, tmp_path):
        (tmp_path / "snap.md").write_text("---\nname: snap\n---\n\nbody\n")
        sm = SkillManager(skills_dir=str(tmp_path))
        sm.load_all()
        assert (tmp_path / ".skills_cache.json").exists()
        sm2 = SkillManager(skills_dir=str(tmp_path))
        loaded2 = sm2.load_all()
        assert loaded2 == ["snap"]

    def test_invalidate_cache(self, tmp_path):
        (tmp_path / "inv.md").write_text("---\nname: inv\n---\n\nbody\n")
        sm = SkillManager(skills_dir=str(tmp_path))
        sm.load_all()
        sm.invalidate_cache()
        assert not (tmp_path / ".skills_cache.json").exists()
        assert sm.list_skills() == {}

    def test_list_skills_filters_private(self, tmp_path):
        (tmp_path / "pub.md").write_text("---\nname: pub\n---\n\nbody\n")
        sm = SkillManager(skills_dir=str(tmp_path))
        sm.load_all()
        skills = sm.list_skills()
        assert "pub" in skills
        assert all(not k.startswith("_") for s in skills.values() for k in s)

    def test_trigger_string_parsing(self, tmp_path):
        (tmp_path / "str.md").write_text("---\ntrigger: a, b, c\n---\n\nbody\n")
        sm = SkillManager(skills_dir=str(tmp_path))
        sm.load_all()
        skill = sm.get_skill("str")
        assert skill["triggers"] == ["a", "b", "c"]

    def test_tools_string_parsing(self, tmp_path):
        (tmp_path / "ts.md").write_text("---\ntools: x, y\n---\n\nbody\n")
        sm = SkillManager(skills_dir=str(tmp_path))
        sm.load_all()
        skill = sm.get_skill("ts")
        assert skill["tools"] == ["x", "y"]

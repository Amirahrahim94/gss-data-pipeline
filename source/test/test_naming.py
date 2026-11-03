"""Check that the naming rules in docs/naming_conventions.md hold across the repository."""
import ast
import csv
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".venv", "__pycache__", "logs", "warehouse", "target", ".dbt"}
ALLOWED = {"README.md", "Dockerfile", ".gitignore", ".env.example", ".gitkeep"}
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
UPPER = re.compile(r"^[A-Z][A-Z0-9_]*$")
CLASS = re.compile(r"^[A-Z][A-Za-z0-9]*$")
FILE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9]+)?$")


def repo_files():
    for path in ROOT.rglob("*"):
        parts = set(path.relative_to(ROOT).parts)
        if not parts & SKIP_DIRS and not any(p.startswith(".") and p not in ALLOWED for p in parts):
            yield path


class NamingTest(unittest.TestCase):
    def test_file_and_folder_names_are_snake_case(self):
        bad = [str(p.relative_to(ROOT)) for p in repo_files()
               if p.name not in ALLOWED and p.name != "__init__.py" and not FILE.match(p.name)]
        self.assertEqual(bad, [])

    def test_config_keys_are_snake_case(self):
        for path in (ROOT / "source" / "config").glob("*.json"):
            with self.subTest(file=path.name):
                bad = [k for k in json.loads(path.read_text(encoding="utf-8")) if not SNAKE.match(k)]
                self.assertEqual(bad, [])

    def test_csv_headers_are_snake_case(self):
        for path in (ROOT / "docs").glob("*.csv"):
            with self.subTest(file=path.name):
                with path.open(encoding="utf-8-sig", newline="") as handle:
                    header = next(csv.reader(handle))
                self.assertEqual([h for h in header if not SNAKE.match(h)], [])

    def test_python_names_follow_the_rules(self):
        problems = []
        for path in (ROOT / "source").rglob("*.py"):
            if SKIP_DIRS & set(path.parts):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ClassDef) and not CLASS.match(node.name):
                    problems.append((path.name, node.name))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names = [node.name] + [a.arg for a in node.args.args + node.args.kwonlyargs]
                    problems += [(path.name, n) for n in names
                                 if not SNAKE.match(n.lstrip("_")) and not n.startswith("__") and n not in {"setUp", "tearDown"}]
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    if node.id != "_" and not (SNAKE.match(node.id.lstrip("_")) or UPPER.match(node.id)):
                        problems.append((path.name, node.id))
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()

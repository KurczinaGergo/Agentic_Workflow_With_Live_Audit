# Tests

The executable audit-tool regression tests currently live beside the scripts they validate:

```powershell
python -m unittest discover -s skill\scripts\workflow-audit -p "test_*.py"
```

Keep repository-level integration tests here when they span the skill, examples, and docs together.

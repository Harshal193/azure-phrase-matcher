import sys
from pathlib import Path

# Make functions/ importable so tests can `import matcher`
sys.path.insert(0, str(Path(__file__).parent.parent / "functions"))

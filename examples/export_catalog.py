"""Export the bundled SDK demo's exact, nonexecuting declaration catalog."""

import json
from pathlib import Path

from melampus_platform.demo import demo_catalog

path = Path("declarations.json")
path.write_text(json.dumps(demo_catalog(), indent=2) + "\n")
print(f"Catalog written to {path}; import it in System Mesh.")

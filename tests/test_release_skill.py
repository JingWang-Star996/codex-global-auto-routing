from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/design-evidence-led-agent-workflow"


class ReleaseSkill(unittest.TestCase):
    def test_frontmatter_and_resource_links(self):
        entry = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(entry.startswith("---\nname: design-evidence-led-agent-workflow\n"))
        for path in [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]:
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r'\]\(([^)]+)\)', text):
                if "://" not in target and not target.startswith("#"):
                    self.assertTrue((path.parent / target.split("#")[0]).is_file(), (path, target))

    def test_bilingual_guides_have_same_configured_matrix(self):
        matrix = []
        for filename in ("model-routing-r11.md", "model-routing-r11.en.md"):
            text = (ROOT / "docs" / filename).read_text(encoding="utf-8")
            matrix.append([line for line in text.splitlines() if re.match(r'^\| (?:luna|terra|sol)_', line)])
        self.assertEqual(matrix[0], matrix[1])


if __name__ == "__main__":
    unittest.main()

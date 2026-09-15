import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from scraper import scrape_lines as scraper


class InjuryFallbackTests(unittest.TestCase):
    def run_scraper(self, previous=None, failure=None, injuries=None):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "lines.json"
            if previous is not None:
                output.write_text(json.dumps(previous))
            lineup = {"forwards": [["NEW PLAYER"]], "defense": [],
                      "goalies": [], "pp1": [], "pp2": []}
            with patch.object(scraper, "OUTPUT_PATH", str(output)), \
                 patch.object(scraper, "TEAMS", ["test-team"]), \
                 patch.object(scraper, "scrape_team", return_value=lineup), \
                 patch.object(scraper.time, "sleep"), \
                 patch.object(scraper, "fetch_espn_team_ids",
                              side_effect=failure, return_value={"test-team": 1}), \
                 patch.object(scraper, "scrape_espn_injuries", return_value=injuries or {}):
                scraper.main()
            result = json.loads(output.read_text())
            self.assertEqual(result["teams"]["test-team"], lineup)
            return result

    def test_403_preserves_injuries_and_saves_new_lineups(self):
        saved = {"test-team": [{"name": "INJURED PLAYER"}]}
        result = self.run_scraper({"injuries": saved,
                                   "injuries_meta": {"updated_at": "2026-06-01"}},
                                  requests.HTTPError("403 Forbidden"))
        self.assertEqual(result["injuries"], saved)
        self.assertEqual(result["injuries_meta"]["status"], "stale")
        self.assertEqual(result["injuries_meta"]["updated_at"], "2026-06-01")

    def test_no_snapshot_marks_injuries_unavailable(self):
        result = self.run_scraper(failure=requests.Timeout())
        self.assertEqual(result["injuries_meta"]["status"], "unavailable")
        self.assertIsNone(result["injuries_meta"]["updated_at"])

    def test_legacy_snapshot_does_not_invent_injury_timestamp(self):
        result = self.run_scraper({"updated_at": "2026-06-01", "injuries": {}},
                                  requests.HTTPError())
        self.assertIsNone(result["injuries_meta"]["updated_at"])

    def test_successful_empty_feed_clears_old_injuries(self):
        result = self.run_scraper({"injuries": {"test-team": [{"name": "OLD"}]}})
        self.assertEqual(result["injuries"], {})
        self.assertEqual(result["injuries_meta"]["status"], "fresh")

    def test_partial_team_failure_rejects_entire_refresh(self):
        ok = Mock()
        ok.json.return_value = {"items": [], "count": 0}
        with patch.object(scraper.SESSION, "get", side_effect=[ok, requests.HTTPError()]), \
             patch.object(scraper.time, "sleep"):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                scraper.scrape_espn_injuries({"one": 1, "two": 2})

    def test_malformed_feed_is_not_treated_as_no_injuries(self):
        response = Mock()
        response.json.return_value = {"error": "Forbidden"}
        with patch.object(scraper.SESSION, "get", return_value=response):
            with self.assertRaises(ValueError):
                scraper.scrape_espn_injuries({"one": 1})

    def test_incomplete_mapping_is_rejected(self):
        response = Mock()
        response.json.return_value = {"sports": []}
        with patch.object(scraper.SESSION, "get", return_value=response):
            with self.assertRaisesRegex(ValueError, "mapping"):
                scraper.fetch_espn_team_ids()


if __name__ == "__main__":
    unittest.main()

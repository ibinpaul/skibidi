import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from THE_BACKEND import ibin


class RestServerTests(unittest.TestCase):
    def test_build_recommendation_payload_returns_expected_shape(self):
        payload = {
            "movie_name": "Dune",
            "guessed_format": "IMAX",
            "needs_accessibility": False,
            "movie_profile": {
                "is_action": True,
                "is_scifi": True,
                "is_comedy": False,
                "runtime_min": 155,
            },
        }

        response = ibin.get_recommendations(payload)
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["movie"], "Dune")
        self.assertIn("rankings", response)
        self.assertIsInstance(response["rankings"], list)

    def test_infer_screen_formats_without_helper_table(self):
        provider = ibin.SupabaseDataProvider.__new__(ibin.SupabaseDataProvider)
        inferred = provider._infer_screen_formats({
            "screen_type": "IMAX",
            "aspect_ratio": "1.90:1"
        })
        self.assertIn("IMAX_LASER", inferred)


if __name__ == "__main__":
    unittest.main()

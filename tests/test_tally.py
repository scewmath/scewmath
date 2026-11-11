import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import tally_languages as tl  # noqa: E402
import tally_tokens as tt  # noqa: E402


def write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return path


def claude_msg(mid, inp=0, out=0, write=0, read=0, ts="2026-11-01T00:00:00Z"):
    return {"type": "assistant", "timestamp": ts, "requestId": "req_" + mid, "message": {
        "id": mid, "usage": {"input_tokens": inp, "output_tokens": out,
                             "cache_creation_input_tokens": write, "cache_read_input_tokens": read}}}


class ClaudeTally(unittest.TestCase):
    def test_streamed_duplicates_count_once_at_max(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write_jsonl(Path(tmp) / "s.jsonl", [
                claude_msg("m1", inp=2, out=10, read=100),
                claude_msg("m1", inp=2, out=50, read=100),   # same message, later chunk
                claude_msg("m2", inp=1, out=1, write=8),
                {"type": "user", "message": {"role": "user", "content": "hi"}},
                "not json at all",
            ])
            ledger = {}
            tt.merge(ledger, tt.claude_records([p]))
        self.assertEqual(ledger["m1"][:2], [152, 52])
        self.assertEqual(ledger["m2"][:2], [10, 10])

    def test_ledger_survives_deleted_logs(self):
        ledger = {"old": [500, 50, "2026-01-01"]}
        tt.merge(ledger, iter([("new", 10, 5, "2026-11-01")]))
        summary = tt.summarize({"claude_code": ledger, "codex": {}}, datetime(2026, 11, 11, tzinfo=timezone.utc))
        self.assertEqual(summary["total"], 510)
        self.assertEqual(summary["since"], "2026-01-01")

    def test_merge_never_shrinks(self):
        ledger = {"m": [100, 10, "2026-01-01"]}
        tt.merge(ledger, iter([("m", 40, 4, "2026-02-01")]))
        self.assertEqual(ledger["m"], [100, 10, "2026-01-01"])


class CodexTally(unittest.TestCase):
    def test_takes_final_running_total(self):
        def tc(total, inp, cached, out):
            return {"timestamp": "2026-01-18T12:00:00Z", "type": "event_msg", "payload": {
                "type": "token_count", "info": {"total_token_usage": {
                    "input_tokens": inp, "cached_input_tokens": cached,
                    "output_tokens": out, "total_tokens": total}}}}
        with tempfile.TemporaryDirectory() as tmp:
            p = write_jsonl(Path(tmp) / "rollout-x.jsonl", [
                {"type": "event_msg", "payload": {"type": "token_count", "info": None}},
                tc(100, 90, 50, 10),
                tc(300, 280, 200, 20),
            ])
            recs = list(tt.codex_records([p]))
        self.assertEqual(recs, [("rollout-x", 300, 100, "2026-01-18")])


class Languages(unittest.TestCase):
    def test_each_repo_weighs_the_same(self):
        def repo(*langs):
            return {"languages": {"edges": [{"size": s, "node": {"name": n, "color": "#000"}} for n, s in langs]}}
        repos = [repo(("HTML", 1_000_000)), repo(("Python", 10)), repo(("Python", 5), ("Jupyter Notebook", 9999))]
        langs, counted = tl.repo_weighted_share(repos, exclude={"Jupyter Notebook"})
        self.assertEqual(counted, 3)
        self.assertEqual([(n, round(p, 1)) for n, p, _ in langs], [("Python", 66.7), ("HTML", 33.3)])


if __name__ == "__main__":
    unittest.main()

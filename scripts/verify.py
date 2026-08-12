#!/usr/bin/env python3
"""
Coverage checker: diffs a real assessment-report.json (produced by the
actual Go assessment-tool run against the seeded cluster) against
expected/coverage_manifest.json. Prints a pass/fail line per check and
exits non-zero if anything expected is missing.

Usage:
    python3 scripts/verify.py <path-to-assessment-report.json>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "expected" / "coverage_manifest.json"


class Result:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"  PASS  {label}" + (f" -- {detail}" if detail else ""))
        else:
            self.failed += 1
            print(f"  FAIL  {label}" + (f" -- {detail}" if detail else ""))

    def warn(self, label: str, detail: str = "") -> None:
        self.warnings += 1
        print(f"  WARN  {label}" + (f" -- {detail}" if detail else ""))


def check_process_definitions(report: dict, manifest: dict, r: Result) -> None:
    print("\n== Process definitions ==")
    expected = manifest["processDefinitions"]
    processes = report.get("processes", [])
    seen_ids = {p["processDefinitionId"] for p in processes}
    r.check(f"expected {expected['expectedCount']} process definitions present",
            set(expected["expectedIds"]) <= seen_ids,
            f"missing: {sorted(set(expected['expectedIds']) - seen_ids)}" if not (set(expected["expectedIds"]) <= seen_ids) else f"{len(seen_ids)} found")

    vskew = expected["versionSkew"]
    vs_process = next((p for p in processes if p["processDefinitionId"] == vskew["processId"]), None)
    if vs_process:
        live_versions = set(vs_process.get("versionsWithLiveInstances", []))
        r.check(f"{vskew['processId']} has live instances on multiple versions",
                len(live_versions) >= 2,
                f"live versions: {sorted(live_versions)}")
    else:
        r.check(f"{vskew['processId']} present for version-skew check", False)

    dormant = expected["dormant"]
    dormant_count = report.get("summary", {}).get("dormantProcessIds", 0)
    r.check(f"summary.dormantProcessIds > 0 ({dormant['processId']} never started)",
            dormant_count > 0, f"dormantProcessIds={dormant_count}")


def check_construct_coverage(report: dict, manifest: dict, r: Result) -> None:
    print("\n== Construct classification coverage ==")
    expected = manifest["constructClassificationKeys"]
    seen_keys = set()
    for p in report.get("processes", []):
        seen_keys |= set((p.get("elements") or {}).keys())

    expected_keys = set(expected["verifiedCoveredKeys"])
    missing = expected_keys - seen_keys
    r.check(f"{len(expected_keys)} expected construct keys present in report",
            not missing, f"missing: {sorted(missing)}" if missing else f"{len(seen_keys)} distinct keys found")

    for item in expected["permanentlyUncoverable"]:
        if item["key"] in seen_keys:
            r.warn(f"{item['key']} unexpectedly present", "was expected permanently uncoverable -- check F01/F02 spike status")
        else:
            print(f"  INFO  {item['key']} absent as expected -- {item['reason']}")


def check_job_types(report: dict, manifest: dict, r: Result) -> None:
    print("\n== Job types ==")
    expected = manifest["jobTypes"]
    job_types = report.get("jobTypes", [])
    total_expected = expected["expectedJavaCount"] + expected["expectedPythonCount"]
    r.check(f"~{total_expected} distinct job types referenced in BPMN",
            len(job_types) >= total_expected - 2,  # tolerate minor drift
            f"{len(job_types)} found")

    seen_types = {j["type"] for j in job_types}
    for defect in expected["reconciliationDefects"]:
        if defect["type"] == "declaredOnly":
            r.check(f"declaredOnly defect present: {defect['jobType']}",
                    defect["jobType"] in seen_types, "found in BPMN job type inventory")
        else:
            r.warn(f"observedOnly defect ({defect['jobType']}) needs the code-analyzer",
                   "not checkable from assessment-report.json alone -- run code-analyzer against workers-java/ and cross-reference")


def check_connectors(report: dict, manifest: dict, r: Result) -> None:
    print("\n== Connectors ==")
    expected = manifest["connectors"]
    distinct = report.get("summary", {}).get("distinctConnectorTypes", 0)
    r.check(f"distinctConnectorTypes >= {expected['expectedDistinctTypes']}",
            distinct >= expected["expectedDistinctTypes"], f"found {distinct}")


def check_timer_risk(report: dict, manifest: dict, r: Result) -> None:
    print("\n== Timer risk counters ==")
    timers = report.get("timers") or {}
    for key, spec in manifest["timerRiskCounters"].items():
        value = timers.get(key, 0)
        r.check(f"{key} non-zero", value > 0, f"value={value}, source: {spec['source']}")


def check_multi_tenancy(report: dict, manifest: dict, r: Result) -> None:
    print("\n== Multi-tenancy ==")
    expected = manifest["multiTenancy"]
    tenants = report.get("summary", {}).get("tenants", 0)
    r.check(f"summary.tenants >= {len(expected['expectedTenants']) - 1}",  # <default> may not count itself
            tenants >= len(expected["expectedTenants"]) - 1, f"tenants={tenants}")


def check_mvp_recommendations(report: dict, manifest: dict, r: Result) -> None:
    print("\n== MVP recommendations ==")
    candidates = report.get("mvpRecommendations") or []
    r.check("mvpRecommendations non-empty", len(candidates) > 0,
            f"{len(candidates)} candidates: {[c.get('processId') for c in candidates]}")
    if candidates:
        print(f"  INFO  candidates: {[c.get('processId') for c in candidates]}")


def check_grade_dimensions(report: dict, r: Result) -> None:
    print("\n== Estate grade dimensions ==")
    dims = report.get("summary", {}).get("gradeDimensions", {})
    unknown = [k for k, v in dims.items() if v is None]
    r.check("no grade dimension is null/unknown", not unknown, f"unknown: {unknown}" if unknown else f"{dims}")


def main() -> None:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <assessment-report.json>", file=sys.stderr)
        sys.exit(2)

    report_path = Path(sys.argv[1])
    if not report_path.exists():
        print(f"report not found: {report_path}", file=sys.stderr)
        sys.exit(2)

    report = json.loads(report_path.read_text())
    manifest = json.loads(MANIFEST_PATH.read_text())

    r = Result()
    check_process_definitions(report, manifest, r)
    check_construct_coverage(report, manifest, r)
    check_job_types(report, manifest, r)
    check_connectors(report, manifest, r)
    check_timer_risk(report, manifest, r)
    check_multi_tenancy(report, manifest, r)
    check_mvp_recommendations(report, manifest, r)
    check_grade_dimensions(report, r)

    print(f"\n{'=' * 50}")
    print(f"{r.passed} passed, {r.failed} failed, {r.warnings} warnings")
    if r.failed > 0:
        print("VERIFY FAILED")
        sys.exit(1)
    print("VERIFY PASSED (see warnings above for what still needs manual/code-analyzer checks)")


if __name__ == "__main__":
    main()

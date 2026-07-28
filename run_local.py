"""
run_local.py — Fase 2 harness for TruckLoadingOpt-ORTools.

Usage (from TruckLoadingOpt-ORTools/ directory):
    $env:RUN_MODE="LOCAL"; python run_local.py    # PowerShell
    set RUN_MODE=LOCAL && python run_local.py     # Windows CMD
    RUN_MODE=LOCAL python run_local.py            # bash / Linux

Expected outcome (Fase 2):
  - Reads the 4 CSVs from ../input_data/
  - Traverses all pre-processing
  - Solves Stage 1 (+ reshuffling if optimal) and Stage 2 (+ reshuffling)
    for each DC using OR-Tools/SCIP via the gurobi_compat shim
  - Writes output CSVs to ../output_data/ (or LOCAL_OUTPUT_PATH)
  - Prints per-DC/stage summary and exits 0
"""

import os
import sys
import json

# ---------------------------------------------------------------------------
# Ensure RUN_MODE=LOCAL before importing anything that reads constants
# ---------------------------------------------------------------------------
os.environ["RUN_MODE"] = "LOCAL"

# ---------------------------------------------------------------------------
# Make the package root importable regardless of where Python is invoked from
# ---------------------------------------------------------------------------
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

# ---------------------------------------------------------------------------
# Minimal request payload
# ---------------------------------------------------------------------------
LOCAL_REQ = json.dumps({
    "project_id":             "local_project",
    "plan_id":                "local_plan_01",
    "apo_truck_load":         "apotruckload",
    "truck_capacity_details": "truckloadutilization",
    "dc_slot_schedule":       "dcslotschedule",
    "general_configurations": "generalconfigurations",
    "delimiter":              ",",
    "truncate_flag":          "false",
    "sdk_workspace":          "local",
    "sdk_destination_path":   "local_output",
})


def _report_outputs(output_root):
    import pandas as pd
    print("\n--- Output CSVs ---")
    found = False
    for root, dirs, files in os.walk(output_root):
        dirs.sort()
        for fname in sorted(files):
            if not fname.endswith(".csv"):
                continue
            found = True
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, output_root)
            try:
                df = pd.read_csv(full)
                print(f"  {rel}: {len(df)} rows x {len(df.columns)} cols")
            except Exception as e:
                print(f"  {rel}: (unreadable: {e})")
    if not found:
        print("  (no CSV files found)")


def main():
    from handler import handle

    print("=" * 64)
    print("TruckLoadingOpt-ORTools -- Fase 2 LOCAL harness")
    print(f"RUN_MODE = {os.environ.get('RUN_MODE')}")
    print("=" * 64)

    try:
        result = handle(LOCAL_REQ)
        print(f"\nhandle() returned: {result}")

        # Report output files
        from src.common.constants import LOCAL_OUTPUT_PATH
        _report_outputs(LOCAL_OUTPUT_PATH)

        print("\n" + "=" * 64)
        print("[FASE 2 OK] End-to-end run completed successfully.")
        print("=" * 64)
        sys.exit(0)

    except Exception as exc:
        print(f"\n[ERROR] {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

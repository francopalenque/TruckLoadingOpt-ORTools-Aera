"""
validate_output.py — Independent constraint checker for TruckLoadingOpt e2e output.

Reads output CSVs + raw input CSVs with plain pandas.
ZERO imports from src/. Every check is computed from scratch.

Usage:
    python validate_output.py [--stage {one,two,final}]

Defaults to checking the final output (local_output/) plus stage-specific outputs.
"""

import os
import sys
import glob
import zipfile
import argparse
from datetime import datetime
from collections import defaultdict

import pandas as pd

# ---------------------------------------------------------------------------
# Paths — all relative to this file's directory (project root)
# ---------------------------------------------------------------------------

BASE = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE, "..", "input_data")
OUTPUT_DIR = os.path.join(BASE, "local_output")
REF_ZIP = os.path.join(BASE, "..", "outputs.zip")

STAGE_ONE_DIR = os.path.join(OUTPUT_DIR, "stage_one")
STAGE_TWO_DIR = os.path.join(OUTPUT_DIR, "stage_two")

SEP = "=" * 72

# ---------------------------------------------------------------------------
# Helpers — pure pandas, no src/ imports
# ---------------------------------------------------------------------------

def _find_header_row(filepath):
    """Return 0-based index of real CSV header (skips AERA Filters block)."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if line.strip() == "":
                return i + 1
    return 0


def _find_csv(directory, glob_pattern):
    """Glob for a single CSV; raise if none found."""
    matches = glob.glob(os.path.join(directory, glob_pattern))
    if not matches:
        raise FileNotFoundError(f"No file matching {glob_pattern} in {directory}")
    return matches[0]


def _norm_cols(df):
    """Lowercase + strip + underscore column names."""
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
    return df


def _to_num(series, downcast="integer"):
    return pd.to_numeric(series, errors="coerce")


def _fmt_violations(df, cols, n=5):
    if df.empty:
        return "(none)"
    return df[cols].head(n).to_string(index=False)


def _pass_fail(label, n_violations, detail=""):
    if n_violations == 0:
        print(f"  [PASS]  {label}")
    else:
        print(f"  [FAIL]  {label} — {n_violations} violation(s)")
        if detail:
            for line in detail.strip().split("\n"):
                print(f"          {line}")
    return n_violations == 0


# ---------------------------------------------------------------------------
# Input loading — standalone, no src/
# ---------------------------------------------------------------------------

def load_inputs():
    """Load the 4 raw input CSVs into normalised DataFrames."""

    def _read(pattern, skiprows=None):
        path = _find_csv(INPUT_DIR, pattern)
        if skiprows is None:
            skiprows = _find_header_row(path)
        df = pd.read_csv(path, skiprows=skiprows, dtype=str)
        return _norm_cols(df)

    apo = _read("APO_Truckload_*.csv")
    truck_cap = _read("TRUCKLOAD_UTILIZATION_*.csv")
    dc_sched = _read("DC_Slot_Schedule_*.csv", skiprows=0)
    gen_cfg = _read("General_Configurations_*.csv")

    # Normalise numeric columns we need for checks
    for col in ["confirmed_quantity_in_base_unit", "gross_weight", "volume", "pallet_spot"]:
        if col in apo.columns:
            apo[col] = pd.to_numeric(apo[col], errors="coerce")

    # Normalise DC in dc_slot_schedule (strip leading zeros — local CSV artefact)
    if "dc" in dc_sched.columns:
        dc_sched["dc"] = dc_sched["dc"].str.lstrip("0")
    dc_sched["number_of_slots"] = pd.to_numeric(dc_sched["number_of_slots"], errors="coerce").fillna(0)

    for col in ["weight_constraint", "volume_constraint", "pallet_constraint"]:
        if col in truck_cap.columns:
            truck_cap[col] = pd.to_numeric(truck_cap[col], errors="coerce")

    print(f"Inputs loaded: apo={apo.shape}, truck_cap={truck_cap.shape}, dc_sched={dc_sched.shape}")
    return apo, truck_cap, dc_sched, gen_cfg


def load_outputs(stage_dir=None):
    """Load output CSVs for a given stage directory (default: final local_output/)."""
    d = stage_dir or OUTPUT_DIR

    def _read(name):
        path = os.path.join(d, name)
        if not os.path.exists(path):
            return None
        return pd.read_csv(path)

    fod = _read("finial_order_df.csv")
    tdf = _read("truck_df.csv")
    sns = _read("sel_non_sel_df.csv")
    opc = _read("order_po_counts.csv")     # Stage 2 only
    return fod, tdf, sns, opc


# ---------------------------------------------------------------------------
# Check 1-3: Capacity constraints (weight / volume / pallet)
# ---------------------------------------------------------------------------

def check_capacity(fod, tdf, label="final"):
    """Recompute weight/volume/pallet used from finial_order_df and compare to limits.

    NOTE: For split orders, gross_weight and volume in finial_order_df store the ORIGINAL
    full-line value, not the proportional split portion. We therefore compute weight and
    volume from weight_per_unit/volume_per_unit × confirmed_quantity_in_base_unit, which
    correctly reflects the partial quantity assigned to each truck. pallet_spot IS already
    proportional in the output, so it is summed directly.
    """
    print(f"\n{SEP}")
    print(f"CHECKS 1-3: Capacity (Weight / Volume / Pallet) — {label}")
    print(SEP)

    assigned = fod[
        (fod["order_allocation"].apply(lambda x: pd.to_numeric(x, errors="coerce")) > 0)
        & (fod["flag"] == "SolverResults")
    ].copy()

    for col in ["weight_per_unit", "volume_per_unit", "confirmed_quantity_in_base_unit",
                "gross_weight", "volume", "pallet_spot"]:
        assigned[col] = pd.to_numeric(assigned[col], errors="coerce").fillna(0)
    assigned["proposed_period"] = pd.to_numeric(assigned["proposed_period"], errors="coerce")

    # Use unit-based weight/volume to correctly handle split orders.
    # gross_weight and volume columns retain the original line value for splits,
    # so recomputing from per-unit values is more accurate.
    assigned["calc_w_line"] = assigned["weight_per_unit"] * assigned["confirmed_quantity_in_base_unit"]
    assigned["calc_v_line"] = assigned["volume_per_unit"] * assigned["confirmed_quantity_in_base_unit"]

    # Detect and warn about inconsistent gross_weight for split orders
    split_keys = assigned.groupby(["dc", "sales_document", "sales_document_item", "schedule_line"]
                                   ).size().reset_index(name="n_splits")
    split_keys = split_keys[split_keys["n_splits"] > 1]
    if not split_keys.empty:
        print(f"  [INFO]  Split order lines detected: {len(split_keys)} unique (sd,sdi,sl) assigned to >1 truck")
        # Check gross_weight inconsistency: for splits, gross_weight should equal weight_per_unit * qty
        split_rows = assigned.merge(split_keys[["dc","sales_document","sales_document_item","schedule_line"]],
                                    on=["dc","sales_document","sales_document_item","schedule_line"])
        split_rows["gw_diff"] = (split_rows["gross_weight"] - split_rows["calc_w_line"]).abs()
        bad_gw = split_rows[split_rows["gw_diff"] > 0.1]
        if not bad_gw.empty:
            print(f"  [INFO]  {len(bad_gw)} split-order rows have gross_weight != weight_per_unit*qty "
                  f"(data inconsistency in output; using unit-based computation for capacity check).")

    # Group by (dc, proposed_po, proposed_period)
    grp = assigned.groupby(["dc", "proposed_po", "proposed_period"], as_index=False).agg(
        calc_weight=("calc_w_line", "sum"),
        calc_volume=("calc_v_line", "sum"),
        calc_pallet=("pallet_spot", "sum"),
        n_lines=("sales_document", "count"),
    )

    # Get limits from truck_df (truck_selection=1)
    sel = tdf[pd.to_numeric(tdf["truck_selection"], errors="coerce") == 1].copy()
    sel["period"] = pd.to_numeric(sel["period"], errors="coerce")
    for col in ["weight_limit", "volume_limit", "pallet_limit", "weight_used", "volume_used", "pallet_used"]:
        sel[col] = pd.to_numeric(sel[col], errors="coerce")

    merged = grp.merge(
        sel[["dc", "po_number", "period", "weight_limit", "volume_limit", "pallet_limit",
             "weight_used", "volume_used", "pallet_used", "flag"]],
        left_on=["dc", "proposed_po", "proposed_period"],
        right_on=["dc", "po_number", "period"],
        how="left",
    )

    # Allow small floating-point tolerance
    TOL = 0.01

    all_pass = True
    for check, calc_col, limit_col, used_col in [
        ("1-WEIGHT",  "calc_weight",  "weight_limit",  "weight_used"),
        ("2-VOLUME",  "calc_volume",  "volume_limit",  "volume_used"),
        ("3-PALLET",  "calc_pallet",  "pallet_limit",  "pallet_used"),
    ]:
        viol = merged[
            merged[calc_col] > merged[limit_col] + TOL
        ].copy()
        viol["excess"] = viol[calc_col] - viol[limit_col]

        # Cross-check: recomputed vs output's pre-computed used column
        diff = merged.copy()
        diff["delta"] = (diff[calc_col] - diff[used_col]).abs()
        cross_viol = diff[diff["delta"] > TOL * 10]

        detail = ""
        if not viol.empty:
            detail = _fmt_violations(
                viol,
                ["dc", "proposed_po", "proposed_period", calc_col, limit_col, "excess", "flag"],
            )
        ok = _pass_fail(
            f"Check {check}: recomputed <= limit for all selected trucks",
            len(viol),
            detail,
        )
        if not ok:
            all_pass = False
        if not cross_viol.empty:
            print(f"          [WARN]  {check} cross-check: {len(cross_viol)} trucks differ between "
                  f"recomputed and truck_df.{used_col} by > {TOL*10:.4f}")

    return all_pass


# ---------------------------------------------------------------------------
# Check 4a: One truck per order in Stage 1 (no splits allowed)
# ---------------------------------------------------------------------------

def check_no_split_stage_one(fod_s1, label="stage_one"):
    print(f"\n{SEP}")
    print(f"CHECK 4a: One truck per order (Stage 1) — {label}")
    print(SEP)

    if fod_s1 is None:
        print("  [SKIP]  No stage_one/finial_order_df.csv found")
        return True

    assigned = fod_s1[
        (pd.to_numeric(fod_s1["order_allocation"], errors="coerce") > 0)
        & (fod_s1["flag"] == "SolverResults")
    ].copy()

    counts = assigned.groupby(
        ["dc", "sales_document", "sales_document_item", "schedule_line"]
    )[["proposed_po", "proposed_period"]].nunique()
    counts = counts.rename(columns={"proposed_po": "n_trucks", "proposed_period": "n_periods"})
    viol = counts[(counts["n_trucks"] > 1) | (counts["n_periods"] > 1)].reset_index()

    detail = _fmt_violations(
        viol,
        ["dc", "sales_document", "sales_document_item", "schedule_line", "n_trucks", "n_periods"],
    ) if not viol.empty else ""

    return _pass_fail(
        "Check 4a: each schedule_line assigned to exactly 1 (truck, period) in Stage 1",
        len(viol),
        detail,
    )


# ---------------------------------------------------------------------------
# Check 4b: Split quantity conservation in Stage 2
# ---------------------------------------------------------------------------

def check_split_conservation(fod_s2, apo, label="stage_two"):
    """Verify demand conservation: for every (dc, sd, sdi, sl), all rows in finial_order_df
    (assigned + rejected) must sum to the original confirmed_qty in the APO input.
    Partial rejections (portion assigned, remainder in 'Solver Rejected Line') are valid
    solver behaviour — they are caught only if the total allocated ≠ original.
    """
    print(f"\n{SEP}")
    print(f"CHECK 4b: Split/rejection quantity conservation (Stage 2) — {label}")
    print(SEP)

    if fod_s2 is None:
        print("  [SKIP]  No stage_two/finial_order_df.csv found")
        return True

    # Include ALL rows (SolverResults assigned + Solver Rejected Line) — reject is a valid split
    all_rows = fod_s2.copy()
    all_rows["confirmed_qty"] = pd.to_numeric(
        all_rows["confirmed_quantity_in_base_unit"], errors="coerce"
    ).fillna(0)

    total_allocated = (
        all_rows.groupby(["dc", "sales_document", "sales_document_item", "schedule_line"])
        ["confirmed_qty"].sum().reset_index()
        .rename(columns={"confirmed_qty": "allocated_qty"})
    )

    # Original quantities from APO input
    apo2 = apo.copy()
    for c in ["sales_document", "sales_document_item", "schedule_line"]:
        apo2[c] = pd.to_numeric(apo2[c], errors="coerce")
        total_allocated[c] = pd.to_numeric(total_allocated[c], errors="coerce")

    orig = (
        apo2.groupby(["sales_document", "sales_document_item", "schedule_line"])
        ["confirmed_quantity_in_base_unit"].sum().reset_index()
        .rename(columns={"confirmed_quantity_in_base_unit": "orig_qty"})
    )

    merged = total_allocated.merge(orig, on=["sales_document", "sales_document_item", "schedule_line"], how="left")
    merged["diff"] = (merged["allocated_qty"] - merged["orig_qty"]).abs()
    viol = merged[merged["diff"] > 0.01]

    # Report partial rejections as info (not violations)
    sr_rows = fod_s2[fod_s2["flag"] == "SolverResults"].copy()
    sr_rows["confirmed_qty"] = pd.to_numeric(sr_rows["confirmed_quantity_in_base_unit"], errors="coerce").fillna(0)
    assigned_sum = (sr_rows[pd.to_numeric(sr_rows["order_allocation"], errors="coerce") > 0]
                    .groupby(["dc", "sales_document", "sales_document_item", "schedule_line"])
                    ["confirmed_qty"].sum().reset_index()
                    .rename(columns={"confirmed_qty": "solver_assigned_qty"}))
    partial = assigned_sum.merge(orig, on=["sales_document", "sales_document_item", "schedule_line"], how="left")
    partial = partial.merge(total_allocated, on=["dc","sales_document","sales_document_item","schedule_line"], how="left")
    partial_rej = partial[
        (partial["solver_assigned_qty"] < partial["orig_qty"] - 0.01) &
        ((partial["allocated_qty"] - partial["orig_qty"]).abs() < 0.01)
    ]
    if not partial_rej.empty:
        print(f"  [INFO]  {len(partial_rej)} lines partially rejected by solver "
              f"(portion assigned, remainder in 'Solver Rejected Line' — demand conserved):")
        print("          " + partial_rej[["dc","sales_document","sales_document_item",
                                          "schedule_line","orig_qty","solver_assigned_qty"]
                                        ].head(10).to_string(index=False).replace("\n", "\n          "))

    detail = _fmt_violations(
        viol,
        ["dc", "sales_document", "sales_document_item", "schedule_line", "orig_qty", "allocated_qty", "diff"],
    ) if not viol.empty else ""

    return _pass_fail(
        "Check 4b: total allocated qty (assigned + rejected) equals original for each line",
        len(viol),
        detail,
    )


# ---------------------------------------------------------------------------
# Check 5: DC slot schedule (trucks per DC per day <= slots)
# ---------------------------------------------------------------------------

def check_dc_slots(tdf, dc_sched, label="final"):
    print(f"\n{SEP}")
    print(f"CHECK 5: DC Slot Schedule — {label}")
    print(SEP)

    sel = tdf[pd.to_numeric(tdf["truck_selection"], errors="coerce") == 1].copy()
    sel["date_dt"] = pd.to_datetime(sel["date"], errors="coerce")
    sel["day_name"] = sel["date_dt"].dt.strftime("%A")  # Monday, Tuesday, ...

    # Count trucks per (dc, day_name) — normalise dc to str to align with dc_sched (also str)
    sel["dc"] = sel["dc"].astype(str).str.lstrip("0")
    counts = sel.groupby(["dc", "day_name"]).size().reset_index(name="n_trucks")

    # Join with dc_slot_schedule (dc already str after lstrip in load_inputs)
    dc2 = dc_sched.rename(columns={"week_name": "day_name"}).copy()
    dc2["dc"] = dc2["dc"].astype(str)
    merged = counts.merge(dc2, on=["dc", "day_name"], how="left")
    merged["number_of_slots"] = merged["number_of_slots"].fillna(0)
    viol = merged[merged["n_trucks"] > merged["number_of_slots"]]

    detail = _fmt_violations(
        viol, ["dc", "day_name", "n_trucks", "number_of_slots"]
    ) if not viol.empty else ""

    return _pass_fail(
        "Check 5: trucks per (DC, day) <= dc_slot_schedule slots",
        len(viol),
        detail,
    )


# ---------------------------------------------------------------------------
# Check 6: Truck balance — each truck used in <= 1 period
# ---------------------------------------------------------------------------

def check_truck_balance(tdf, label="final"):
    print(f"\n{SEP}")
    print(f"CHECK 6: Truck Balance (each truck <= 1 period) — {label}")
    print(SEP)

    sel = tdf[pd.to_numeric(tdf["truck_selection"], errors="coerce") == 1].copy()
    counts = sel.groupby(["dc", "po_number"])["period"].count().reset_index(name="n_periods")
    viol = counts[counts["n_periods"] > 1]

    detail = _fmt_violations(viol, ["dc", "po_number", "n_periods"]) if not viol.empty else ""
    return _pass_fail(
        "Check 6: each truck assigned to at most 1 period",
        len(viol),
        detail,
    )


# ---------------------------------------------------------------------------
# Check 7: Delivery date (assigned period >= delivery_period)
# ---------------------------------------------------------------------------

def check_delivery_date(fod, label="final"):
    print(f"\n{SEP}")
    print(f"CHECK 7: Delivery Date Constraint — {label}")
    print(SEP)

    assigned = fod[
        (pd.to_numeric(fod["order_allocation"], errors="coerce") > 0)
        & (fod["flag"] == "SolverResults")
    ].copy()

    assigned["proposed_period_n"] = pd.to_numeric(assigned["proposed_period"], errors="coerce")
    assigned["delivery_period_n"] = pd.to_numeric(assigned["delivery_period"], errors="coerce")

    viol = assigned[assigned["proposed_period_n"] < assigned["delivery_period_n"]].copy()
    viol["early_by"] = viol["delivery_period_n"] - viol["proposed_period_n"]

    detail = _fmt_violations(
        viol,
        ["dc", "sales_document", "sales_document_item", "proposed_po",
         "proposed_period_n", "delivery_period_n", "early_by"],
    ) if not viol.empty else ""

    return _pass_fail(
        "Check 7: proposed_period >= delivery_period for all assigned lines",
        len(viol),
        detail,
    )


# ---------------------------------------------------------------------------
# Check 8: Shuffle together (Y-flagged lines share same truck + period)
# ---------------------------------------------------------------------------

def check_shuffle_together(fod, label="final"):
    """Verify that schedule_lines with shuffle_together_flag='Y' that belong to the same
    (dc, sales_document, sales_document_item) are all assigned to the same truck.

    The model's shuffle group is (dc, sales_document, sales_document_item): all schedule_lines
    of the same item must ship together. Different items within the same sales_document can
    go to different trucks (they may have different materials and independent shuffle groups).
    """
    print(f"\n{SEP}")
    print(f"CHECK 8: Shuffle Together Flag — {label}")
    print(SEP)

    shuffle = fod[
        (fod["shuffle_together_flag"] == "Y")
        & (pd.to_numeric(fod["order_allocation"], errors="coerce") > 0)
        & (fod["flag"] == "SolverResults")
    ].copy()

    if shuffle.empty:
        print("  [PASS]  No shuffle_together_flag='Y' assigned lines in this output (trivially satisfied)")
        return True

    print(f"  [INFO]  {len(shuffle)} assigned rows with shuffle_together_flag='Y' across "
          f"{shuffle['sales_document'].nunique()} sales documents")

    # Hard check: within each (dc, sales_document, sales_document_item), all sl go to same truck
    item_groups = shuffle.groupby(["dc", "sales_document", "sales_document_item"]).agg(
        n_trucks=("proposed_po", "nunique"),
        trucks=("proposed_po", lambda x: sorted(x.unique())),
    ).reset_index()
    viol = item_groups[item_groups["n_trucks"] > 1]

    detail = _fmt_violations(
        viol, ["dc", "sales_document", "sales_document_item", "n_trucks", "trucks"]
    ) if not viol.empty else ""

    ok = _pass_fail(
        "Check 8: shuffle_together='Y' schedule_lines within same (DC, SD, SDI) share one truck",
        len(viol),
        detail,
    )

    # Informational: check if different items from the same SD go to different trucks
    sd_groups = shuffle.groupby(["dc", "sales_document"]).agg(
        n_trucks=("proposed_po", "nunique"),
        trucks=("proposed_po", lambda x: sorted(x.unique())),
        n_items=("sales_document_item", "nunique"),
    ).reset_index()
    sd_split = sd_groups[(sd_groups["n_trucks"] > 1) & (sd_groups["n_items"] > 1)]
    if not sd_split.empty:
        print(f"  [INFO]  {len(sd_split)} sales_document(s) have shuffle='Y' items split across trucks "
              f"(different items -> different groups; not a hard violation):")
        for _, r in sd_split.iterrows():
            print(f"          DC={r['dc']} SD={r['sales_document']} "
                  f"n_items={r['n_items']} trucks={r['trucks']}")

    return ok


# ---------------------------------------------------------------------------
# Check 9: Soft — max 2 trucks per (sales_document, sales_document_item, material)
# ---------------------------------------------------------------------------

def check_max_trucks_soft(fod, label="final"):
    print(f"\n{SEP}")
    print(f"CHECK 9 (SOFT): Max trucks per order grain — {label}")
    print(SEP)

    assigned = fod[
        (pd.to_numeric(fod["order_allocation"], errors="coerce") > 0)
        & (fod["flag"] == "SolverResults")
    ].copy()

    counts = (
        assigned.groupby(["dc", "sales_document", "sales_document_item", "schedule_line", "material"])
        ["proposed_po"].nunique().reset_index(name="n_trucks")
    )
    exceed = counts[counts["n_trucks"] > 2]

    print(f"  [INFO]  Lines with >2 trucks assigned: {len(exceed)} of {len(counts)}")
    if not exceed.empty:
        print("          (SOFT — these are penalised by solver slack, not hard violations)")
        print("          First 5 offenders:")
        print(_fmt_violations(
            exceed,
            ["dc", "sales_document", "sales_document_item", "schedule_line", "material", "n_trucks"]
        ))
    else:
        print("  [PASS]  No lines exceed 2 trucks (soft constraint satisfied for all grains)")
    return True   # always "pass" for reporting purposes (soft)


# ---------------------------------------------------------------------------
# Schema comparison against outputs.zip
# ---------------------------------------------------------------------------

def check_schema(label="final"):
    print(f"\n{SEP}")
    print(f"SCHEMA CHECK: local outputs vs outputs.zip reference — {label}")
    print(SEP)

    if not os.path.exists(REF_ZIP):
        print(f"  [SKIP]  outputs.zip not found at {REF_ZIP}")
        return True

    # Reference schemas from zip (uppercase -> lowercase for comparison)
    ref_schemas = {}
    with zipfile.ZipFile(REF_ZIP) as z:
        for name in z.namelist():
            if name.endswith(".csv") and "__MACOSX" not in name:
                with z.open(name) as f:
                    hdr = f.readline().decode("utf-8", errors="replace").strip()
                cols = [c.strip().lower() for c in hdr.split(",")]
                base = os.path.basename(name)
                ref_schemas[base] = cols

    # Map reference filenames to local output files
    mapping = {
        "FINAL_ORDER_OUTPUT.csv": os.path.join(OUTPUT_DIR, "finial_order_df.csv"),
        "SELECTED_TRUCK_DF.csv": os.path.join(OUTPUT_DIR, "sel_non_sel_df.csv"),
        "SUMMARY_OUTPUT.csv": os.path.join(OUTPUT_DIR, "summary_df.csv"),
    }

    all_ok = True
    for ref_name, local_path in mapping.items():
        ref_cols = ref_schemas.get(ref_name, [])
        if not ref_cols:
            print(f"  [SKIP]  {ref_name} not in zip")
            continue
        if not os.path.exists(local_path):
            print(f"  [FAIL]  {ref_name} -> local file not found: {local_path}")
            all_ok = False
            continue

        local_df = pd.read_csv(local_path, nrows=0)
        local_cols = [c.lower() for c in local_df.columns]

        missing = [c for c in ref_cols if c not in local_cols]
        extra   = [c for c in local_cols if c not in ref_cols]
        order_ok = (ref_cols == local_cols[:len(ref_cols)]) if not missing else False

        if not missing and not extra:
            print(f"  [PASS]  {ref_name}: columns match exactly ({len(ref_cols)} cols)")
        else:
            all_ok = False
            print(f"  [FAIL]  {ref_name}: schema mismatch")
            if missing:
                print(f"          Missing cols (in ref, not in local): {missing}")
            if extra:
                print(f"          Extra cols   (in local, not in ref):  {extra}")
            if missing or extra:
                print(f"          Ref   order: {ref_cols}")
                print(f"          Local order: {local_cols}")

    return all_ok


# ---------------------------------------------------------------------------
# Summary per DC and stage
# ---------------------------------------------------------------------------

def print_dc_stage_summary(output_dir=OUTPUT_DIR):
    summ_path = os.path.join(output_dir, "summary_df.csv")
    if not os.path.exists(summ_path):
        return
    summ = pd.read_csv(summ_path)
    print(f"\n{SEP}")
    print("DC / STAGE SUMMARY (from summary_df.csv)")
    print(SEP)
    print(summ.to_string(index=False))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Independent constraint checker")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Output directory to check")
    args = parser.parse_args()

    output_dir = args.output_dir

    print(SEP)
    print("validate_output.py — Independent Constraint Checker")
    print(f"Checking: {output_dir}")
    print(f"Inputs:   {INPUT_DIR}")
    print(SEP)

    # --- Load inputs ---
    apo, truck_cap, dc_sched, gen_cfg = load_inputs()

    # --- Load final outputs ---
    fod, tdf, sns, _ = load_outputs(output_dir)

    # --- Load stage-specific outputs ---
    fod_s1, tdf_s1, _, _ = load_outputs(STAGE_ONE_DIR)
    fod_s2, tdf_s2, _, opc_s2 = load_outputs(STAGE_TWO_DIR)

    results = {}

    # === Final output checks ===
    if fod is not None and tdf is not None:
        results["1-3_capacity_final"] = check_capacity(fod, tdf, "final")
        results["5_dc_slots_final"]   = check_dc_slots(tdf, dc_sched, "final")
        results["6_truck_balance_final"] = check_truck_balance(tdf, "final")
        results["7_delivery_date_final"] = check_delivery_date(fod, "final")
        results["8_shuffle_final"]    = check_shuffle_together(fod, "final")
        results["9_soft_final"]       = check_max_trucks_soft(fod, "final")
    else:
        print("\n[WARN] Final output files not found; skipping final checks")

    # === Stage 1 — no-split check ===
    results["4a_no_split_s1"] = check_no_split_stage_one(fod_s1, "stage_one")

    # === Stage 2 — split quantity conservation ===
    results["4b_split_conservation_s2"] = check_split_conservation(fod_s2, apo, "stage_two")

    # === Stage 2 capacity (independent re-check) ===
    if fod_s2 is not None and tdf_s2 is not None:
        results["1-3_capacity_s2"] = check_capacity(fod_s2, tdf_s2, "stage_two")
        results["5_dc_slots_s2"]   = check_dc_slots(tdf_s2, dc_sched, "stage_two")
        results["7_delivery_date_s2"] = check_delivery_date(fod_s2, "stage_two")

    # === Schema comparison ===
    results["schema"] = check_schema()

    # === Summary ===
    print_dc_stage_summary(output_dir)

    print(f"\n{SEP}")
    print("VALIDATION SUMMARY")
    print(SEP)
    n_pass = sum(1 for v in results.values() if v)
    n_fail = sum(1 for v in results.values() if not v)
    for check, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}]  {check}")
    print(f"\n  Total: {n_pass} passed, {n_fail} failed out of {len(results)} checks")

    if n_fail > 0:
        print("\n  [!] Constraint violations detected. See details above.")
        sys.exit(1)
    else:
        print("\n  All constraints verified. Solution is feasible.")
        sys.exit(0)


if __name__ == "__main__":
    main()

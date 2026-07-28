"""
diag_run.py — standalone diagnostic script for 0-combinations issue.
Run from TruckLoadingOpt-ORTools/:
    RUN_MODE=LOCAL python diag_run.py
"""
import os, sys
os.environ["RUN_MODE"] = "LOCAL"
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import pandas as pd
import glob as _glob
from src.common.constants import LOCAL_INPUT_PATH, date_format, data_column_mapping
from src.pre_processing.Data2 import LocalDataSource
from src.stage_one.pre_processing.data_handling import (
    transform_date, get_dc_list, filter_dataframe, DataHandling
)

SEP = "="*66

# ── helper ──────────────────────────────────────────────────────────────────

def dtype_report(df):
    return {c: str(df[c].dtype) for c in df.columns}

# ── SECTION 1: raw CSVs ──────────────────────────────────────────────────────
print(SEP)
print("SECCIÓN 1 — CSVs CRUDOS (pd.read_csv sin dtype forzado)")
print(SEP)

raw = {}
for key, pat in {
    "apo_truck_load": "APO_Truckload_*.csv",
    "truck_capacity_details": "TRUCKLOAD_UTILIZATION_*.csv",
    "dc_slot_schedule": "DC_Slot_Schedule_*.csv",
    "general_configurations": "General_Configurations_*.csv",
}.items():
    fpath = _glob.glob(os.path.join(LOCAL_INPUT_PATH, pat))[0]
    skip = 6 if "APO" in fpath else 4 if "TRUCKLOAD" in fpath else 3 if "General" in fpath else 0
    df_raw = pd.read_csv(fpath, skiprows=skip)
    raw[key] = df_raw
    dc_vals = sorted(df_raw["DC"].unique().tolist())[:5] if "DC" in df_raw.columns else "—"
    po_vals = []
    for c in df_raw.columns:
        if "PO" in c.upper() and "NUMBER" in c.upper():
            po_vals = sorted(str(v) for v in df_raw[c].unique().tolist())[:3]
    print(f"\n[{key}]")
    print(f"  shape          : {df_raw.shape}")
    print(f"  columns        : {list(df_raw.columns)}")
    print(f"  DC dtype/vals  : {df_raw['DC'].dtype if 'DC' in df_raw.columns else 'N/A'} | {dc_vals}")
    if po_vals:
        print(f"  PO_NUMBER vals : {po_vals}")
    print(f"  first 3 rows:\n{df_raw.head(3).to_string(max_cols=6)}")

# ── SECTION 2: LocalDataSource output ───────────────────────────────────────
print()
print(SEP)
print("SECCIÓN 2 — LocalDataSource.read_data() output")
print(SEP)

local_src = LocalDataSource(LOCAL_INPUT_PATH)
tables, _ = local_src.read_data()

for key in ["apo_truck_load", "truck_capacity_details", "dc_slot_schedule", "general_configurations"]:
    df = tables[key]
    print(f"\n[{key}]")
    print(f"  shape : {df.shape}")
    print(f"  dtypes: {dtype_report(df)}")
    if "dc" in df.columns:
        dc_uniq = sorted(str(v) for v in df["dc"].unique().tolist())[:5]
        print(f"  dc dtype  : {df['dc'].dtype}   vals: {dc_uniq}")
    if "po_number" in df.columns:
        po_uniq = sorted(str(v) for v in df["po_number"].unique().tolist())[:3]
        print(f"  po_number dtype: {df['po_number'].dtype}   vals: {po_uniq}")
    print(f"  first 2 rows:\n{df.head(2).to_string(max_cols=6)}")

# ── SECTION 3: after transform_date ─────────────────────────────────────────
print()
print(SEP)
print("SECCIÓN 3 — Después de transform_date + get_dc_list")
print(SEP)

tables = transform_date(tables)
dc_list, tables = get_dc_list(tables)
print(f"dc_list = {dc_list}  (dtype: {type(dc_list[0]).__name__})")
print()
print("apo_truck_load.dc unique:", sorted(str(v) for v in tables["apo_truck_load"]["dc"].unique()))
print("dc_slot_schedule.dc unique:", sorted(str(v) for v in tables["dc_slot_schedule"]["dc"].unique()))

# ── SECTION 4: filter_dataframe per DC ─────────────────────────────────────
print()
print(SEP)
print("SECCIÓN 4 — filter_dataframe por DC (dtype de DC en cada tabla post-filtro)")
print(SEP)

for dc in dc_list[:2]:  # first 2 DCs to keep output manageable
    print(f"\n>> DC = {repr(dc)}  (type: {type(dc).__name__})")

    # Manual comparison: does dc_slot_schedule filter work?
    dc_sched_all = tables["dc_slot_schedule"]
    mask = dc_sched_all["dc"] == dc
    print(f"  dc_slot_schedule['dc'] == dc: {mask.sum()} rows match")
    print(f"  dc_slot_schedule dc sample values: {sorted(str(v) for v in dc_sched_all['dc'].unique()[:3])}")
    print(f"  dc (from dc_list) type={type(dc).__name__} value={repr(dc)}")

    dc_input, apo_full, truck_full, actual_cnt = filter_dataframe(tables, dc)
    print(f"  actual_truck_count    = {actual_cnt}")
    print(f"  truck_cap after filter: {len(dc_input['truck_capacity_details'])} rows")
    print(f"  apo_truck_load after filter: {len(dc_input['apo_truck_load'])} rows")
    print(f"  dc_slot_schedule after filter: {len(dc_input['dc_slot_schedule'])} rows")
    if len(dc_input['apo_truck_load']) > 0:
        atl = dc_input['apo_truck_load']
        print(f"  apo non-avail flag distribution:\n    {atl['non-available_order_flag'].value_counts().to_dict()}")
        print(f"  confirmed_qty > 0 rows: {(atl['confirmed_quantity_in_base_unit'] > 0).sum()}")
    if len(dc_input['dc_slot_schedule']) > 0:
        print(f"  slot schedule:\n{dc_input['dc_slot_schedule'].to_string()}")

# ── SECTION 5: full funnel for DC 1000001 ───────────────────────────────────
print()
print(SEP)
print("SECCIÓN 5 — EMBUDO create_apo_truck_load_combinations para DC 1000001")
print(SEP)

DC0 = dc_list[0]
dc_input, apo_full, truck_full, _ = filter_dataframe(tables, DC0)

input_data = DataHandling("local_project", "local_plan_01", dc_input, "/tmp", truck_full)
input_data.model_parameters = input_data.read_global_parameters()
input_data.horizon, input_data.date_to_period, input_data.period_to_date = input_data.get_periods_from_dates()
input_data.precision_in_days = input_data.get_days_from_time_string("P1D")
input_data.period_day_name_mapping = input_data.get_day_name_from_period_dates()

print(f"\nhorizon = {input_data.horizon}")
print(f"date_to_period = {input_data.date_to_period}")
print(f"period_day_name_mapping = {input_data.period_day_name_mapping}")

input_data.apo_truck_load_dict = input_data.read_apo_truck_load()
input_data.truck_capacities, input_data.truck_po_level_details = input_data.read_truck_capacity_details()

print(f"\napo_truck_load_dict keys (PO): {list(input_data.apo_truck_load_dict.keys())[:5]}")
print(f"truck_po_level_details keys (PO): {list(input_data.truck_po_level_details.keys())}")

input_data.dc_slot_schedule_dict = input_data.read_dc_slot_schedule()
print(f"\ndc_slot_schedule_dict = {input_data.dc_slot_schedule_dict}")

# Manual funnel
print(f"\n── Conteo de órdenes en apo_truck_load_dict:")
total_order_keys = sum(len(v) for v in input_data.apo_truck_load_dict.values())
print(f"  POs: {len(input_data.apo_truck_load_dict)}, order keys total: {total_order_keys}")

print(f"\n── Conteo de trucks en truck_po_level_details:")
print(f"  {len(input_data.truck_po_level_details)} trucks")

combos = 0
no_slot = 0
slots_zero = 0
period_out = 0
no_day_match = 0
for po_number, po_values in input_data.apo_truck_load_dict.items():
    for key, values in po_values.items():
        if values['priority_line_flag'] == 'Y':
            if values['requested_delivery_period'] <= values['delivery_period']:
                from src.common.utils import find_valid_period
                result = find_valid_period(values['delivery_period'], input_data.horizon,
                                           input_data.period_day_name_mapping, input_data.dc_slot_schedule_dict)
                period_lst = [result] if result is not None else []
            else:
                period_lst = [p for p in range(values['delivery_period'], values['requested_delivery_period'] + 1)
                              if input_data.dc_slot_schedule_dict.get(input_data.period_day_name_mapping[p]['day_name'], 0) > 0]
                if not period_lst:
                    from src.common.utils import find_valid_period
                    result = find_valid_period(values['requested_delivery_period'], input_data.horizon,
                                               input_data.period_day_name_mapping, input_data.dc_slot_schedule_dict)
                    period_lst = [result] if result is not None else []
        else:
            period_lst = list(range(1, input_data.horizon + 1))

        found_any = False
        for po in input_data.truck_po_level_details.keys():
            for period in period_lst:
                if period >= values['delivery_period']:
                    day_name = input_data.period_day_name_mapping[period]['day_name']
                    if day_name in input_data.dc_slot_schedule_dict:
                        if input_data.dc_slot_schedule_dict[day_name] > 0:
                            combos += 1
                            found_any = True
                        else:
                            slots_zero += 1
                    else:
                        no_day_match += 1
                else:
                    period_out += 1
        if not found_any:
            no_slot += 1

print(f"\n── Embudo para DC {DC0}:")
print(f"  Combinaciones creadas   : {combos}")
print(f"  Órdenes sin slot válido : {no_slot}")
print(f"  Fallo: period < delivery: {period_out}")
print(f"  Fallo: day not in sched : {no_day_match}")
print(f"  Fallo: slots == 0       : {slots_zero}")

# ── SECTION 6: sample date→period mapping for 3 orders ─────────────────────
print()
print(SEP)
print("SECCIÓN 6 — Muestra de 3 órdenes: delivery_date, periodo y slots")
print(SEP)

sample_count = 0
for po_number, po_values in input_data.apo_truck_load_dict.items():
    for key, values in po_values.items():
        if sample_count >= 3:
            break
        sd, sdi, sl, mat = key
        dp = values['delivery_period']
        rdp = values['requested_delivery_period']
        dd = values['delivery_date']
        day = input_data.period_day_name_mapping.get(dp, {}).get('day_name', '?')
        slot = input_data.dc_slot_schedule_dict.get(day, 'MISSING')
        print(f"\n  Order: ({sd},{sdi},{sl},{mat}) PO={po_number}")
        print(f"    delivery_date={dd}  delivery_period={dp}  day={day}  slot={slot}")
        print(f"    requested_delivery_period={rdp}")
        print(f"    priority_line_flag={values['priority_line_flag']}")
        sample_count += 1
    if sample_count >= 3:
        break

print()
print(SEP)
print("FIN DIAGNÓSTICO")
print(SEP)

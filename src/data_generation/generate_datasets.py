"""
DQ Agent Framework — Synthetic Dataset Generator
Generates 5 multi-domain datasets (~2,000 rows each) with intentional DQ issues
injected at controlled rates to simulate real-world data quality problems.

Domains: Healthcare, Finance, Insurance, Supply Chain, Automotive
"""

import pandas as pd
import numpy as np
import random
import string
from pathlib import Path
from datetime import datetime, timedelta, date
from faker import Faker

fake = Faker()
Faker.seed(42)
np.random.seed(42)
random.seed(42)

ROOT = Path(__file__).parent.parent.parent
RAW_DIR = ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

N = 2000  # rows per domain


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def rand_date(start_year=2018, end_year=2024) -> str:
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    return str(start + timedelta(days=random.randint(0, (end - start).days)))

def future_date(days_ahead=30) -> str:
    return str(date.today() + timedelta(days=random.randint(1, days_ahead)))

def inject_nulls(series: pd.Series, rate: float) -> pd.Series:
    mask = np.random.random(len(series)) < rate
    series = series.copy().astype(object)
    series[mask] = np.nan
    return series

def corrupt_format(values, corrupt_fn, rate=0.08):
    """Apply a corruption function to a random subset of values."""
    result = list(values)
    indices = random.sample(range(len(result)), int(len(result) * rate))
    for i in indices:
        if result[i] is not None and result[i] is not np.nan:
            try:
                result[i] = corrupt_fn(result[i])
            except Exception:
                pass
    return result


# ─── HEALTHCARE DATASET ───────────────────────────────────────────────────────

def generate_healthcare(n=N) -> pd.DataFrame:
    print(f"  Generating Healthcare dataset ({n} rows)...")
    genders = ["Male", "Female", "Other"]
    statuses = ["Active", "Discharged", "Deceased", "Transferred"]
    diagnoses = ["J18.9", "I21.0", "E11.9", "J44.1", "C34.1", "F32.1", "K29.5", "N18.3", "M54.5", "G43.9"]
    physicians = [fake.name() for _ in range(30)]

    records = []
    for i in range(n):
        dob = fake.date_of_birth(minimum_age=1, maximum_age=95)
        age = (date.today() - dob).days // 365
        admit = fake.date_between(start_date="-5y", end_date="today")
        discharge = admit + timedelta(days=random.randint(0, 30))

        records.append({
            "patient_id": f"PAT-{i+1:06d}",
            "patient_name": fake.name(),
            "date_of_birth": str(dob),
            "age": age,
            "gender": random.choice(genders),
            "ssn": f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}",
            "email": fake.email(),
            "phone": fake.phone_number(),
            "address": fake.address().replace("\n", ", "),
            "zip_code": fake.zipcode(),
            "admission_date": str(admit),
            "discharge_date": str(discharge),
            "diagnosis_code": random.choice(diagnoses),
            "icd_version": random.choice(["ICD-10", "ICD-10"]),
            "treatment": random.choice(["Medication", "Surgery", "Therapy", "Observation", "Chemotherapy"]),
            "physician_name": random.choice(physicians),
            "insurance_id": f"INS-{random.randint(100000, 999999)}",
            "bill_amount": round(random.uniform(500, 250000), 2),
            "payment_status": random.choice(["Paid", "Pending", "Partial", "Denied"]),
            "status": random.choice(statuses),
            "last_updated": str(fake.date_between(start_date="-3y", end_date="today")),
        })

    df = pd.DataFrame(records)

    # ── Inject DQ Issues ──
    # 1. Nulls: diagnosis_code (12%), physician_name (7%), treatment (9%), insurance_id (6%), last_updated (5%)
    df["diagnosis_code"] = inject_nulls(df["diagnosis_code"], 0.12)
    df["physician_name"] = inject_nulls(df["physician_name"], 0.07)
    df["treatment"] = inject_nulls(df["treatment"], 0.09)
    df["insurance_id"] = inject_nulls(df["insurance_id"], 0.06)
    df["email"] = inject_nulls(df["email"], 0.05)
    df["last_updated"] = inject_nulls(df["last_updated"], 0.05)

    # 2. Duplicates (~6% exact duplicates)
    dup_n = int(n * 0.06)
    dup_rows = df.sample(dup_n, random_state=1).copy()
    dup_rows["patient_id"] = [f"PAT-{i+n+1:06d}" for i in range(dup_n)]
    df = pd.concat([df, dup_rows], ignore_index=True)

    # 3. Invalid ages (negative or > 130)
    invalid_age_idx = random.sample(range(len(df)), int(len(df) * 0.02))
    for i in invalid_age_idx:
        df.at[i, "age"] = random.choice([-5, -1, 150, 200, 999])

    # 4. Inconsistent gender casing
    gender_variants = {"Male": ["male", "MALE", "M", "m"], "Female": ["female", "FEMALE", "F", "f"], "Other": ["other", "OTHER", "O"]}
    inconsistent_idx = random.sample(range(len(df)), int(len(df) * 0.08))
    for i in inconsistent_idx:
        gender = df.at[i, "gender"] if df.at[i, "gender"] in gender_variants else "Male"
        df.at[i, "gender"] = random.choice(gender_variants.get(gender, ["Male"]))

    # 5. Inconsistent status casing
    status_variants = {"Active": ["active", "ACTIVE", "active "], "Discharged": ["discharged", "DISCHARGED"]}
    status_inconsistent_idx = random.sample(range(len(df)), int(len(df) * 0.06))
    for i in status_inconsistent_idx:
        status = df.at[i, "status"]
        if status in status_variants:
            df.at[i, "status"] = random.choice(status_variants[status])

    # 6. Mixed date formats
    date_format_idx = random.sample(range(len(df)), int(len(df) * 0.07))
    for i in date_format_idx:
        try:
            d = datetime.strptime(df.at[i, "admission_date"], "%Y-%m-%d")
            df.at[i, "admission_date"] = d.strftime(random.choice(["%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y"]))
        except Exception:
            pass

    # 7. Discharge before admission (3%)
    swap_idx = random.sample(range(len(df)), int(len(df) * 0.03))
    for i in swap_idx:
        df.at[i, "discharge_date"] = str(fake.date_between(start_date="-6y", end_date="-5y"))

    # 8. Stale records (last_updated > 2 years old, 10%)
    stale_idx = random.sample(range(len(df)), int(len(df) * 0.10))
    for i in stale_idx:
        df.at[i, "last_updated"] = str(fake.date_between(start_date="-5y", end_date="-2y"))

    # 9. Invalid SSN patterns
    ssn_invalid_idx = random.sample(range(len(df)), int(len(df) * 0.04))
    for i in ssn_invalid_idx:
        df.at[i, "ssn"] = random.choice(["123456789", "000-00-0000", "SSN-INVALID", "999-99-9999"])

    # 10. Bill amount outliers
    outlier_idx = random.sample(range(len(df)), int(len(df) * 0.02))
    for i in outlier_idx:
        df.at[i, "bill_amount"] = random.choice([-500, 50000000, -1])

    # 11. Duplicate patient_ids (2%) with conflicting values (Survivorship)
    dup_pid_idx = random.sample(range(len(df)), int(len(df) * 0.02))
    existing_ids = df["patient_id"].dropna().tolist()
    for i in dup_pid_idx:
        df.at[i, "patient_id"] = random.choice(existing_ids[:100])
        # Introduce a conflict
        df.at[i, "email"] = fake.email()
        df.at[i, "status"] = random.choice(["Active", "Transferred"])

    # 12. Accessibility corruption (1%)
    acc_idx = random.sample(range(len(df)), int(len(df) * 0.01))
    for i in acc_idx:
        df.at[i, "patient_name"] = str(df.at[i, "patient_name"]) + " " + chr(255) + chr(1002)

    print(f"    -> {len(df)} rows generated (with DQ issues)")
    return df


# ─── FINANCE DATASET ──────────────────────────────────────────────────────────

def generate_finance(n=N) -> pd.DataFrame:
    print(f"  Generating Finance dataset ({n} rows)...")
    tx_types = ["Credit", "Debit", "Transfer", "Refund", "Fee"]
    currencies = ["USD", "EUR", "GBP", "JPY", "CAD"]
    statuses = ["Completed", "Pending", "Failed", "Reversed"]
    merchants = [fake.company() for _ in range(50)]
    categories = ["Grocery", "Retail", "Entertainment", "Travel", "Healthcare", "Utilities", "Dining", "Online"]

    records = []
    for i in range(n):
        amount = round(random.uniform(0.5, 15000), 2)
        balance = round(random.uniform(-500, 50000), 2)
        credit_limit = round(random.uniform(1000, 100000), 2)
        records.append({
            "transaction_id": f"TXN-{i+1:08d}",
            "account_id": f"ACC-{random.randint(1000000, 9999999)}",
            "customer_id": f"CUST-{random.randint(10000, 99999)}",
            "customer_name": fake.name(),
            "email": fake.email(),
            "phone": fake.phone_number(),
            "transaction_date": rand_date(2020, 2024),
            "amount": amount,
            "transaction_type": random.choice(tx_types),
            "currency": random.choice(currencies),
            "merchant": random.choice(merchants),
            "merchant_category": random.choice(categories),
            "balance": balance,
            "credit_limit": credit_limit,
            "fraud_flag": random.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1]),
            "status": random.choice(statuses),
            "card_number": f"{random.randint(1000,9999)}{random.randint(1000,9999)}{random.randint(1000,9999)}{random.randint(1000,9999)}",
            "routing_number": f"{random.randint(100000000, 999999999)}",
            "last_updated": rand_date(2020, 2024),
        })

    df = pd.DataFrame(records)

    # ── Inject DQ Issues ──
    # 1. Missing account_id (7%), email (5%)
    df["account_id"] = inject_nulls(df["account_id"], 0.07)
    df["email"] = inject_nulls(df["email"], 0.05)
    df["merchant"] = inject_nulls(df["merchant"], 0.04)

    # 2. Duplicate transaction IDs (8%)
    dup_n = int(n * 0.08)
    dup_rows = df.sample(dup_n, random_state=2).copy()
    dup_rows["transaction_id"] = df["transaction_id"].sample(dup_n, random_state=3).values
    df = pd.concat([df, dup_rows], ignore_index=True)

    # 3. Negative amounts where they shouldn't be
    neg_idx = random.sample(range(len(df)), int(len(df) * 0.04))
    for i in neg_idx:
        if df.at[i, "transaction_type"] == "Credit":
            df.at[i, "amount"] = -abs(df.at[i, "amount"])

    # 4. Inconsistent currency casing
    cur_variants = {"USD": ["usd", "Usd", "US Dollar", "us dollar"], "EUR": ["eur", "Euro", "EURO"]}
    cur_idx = random.sample(range(len(df)), int(len(df) * 0.07))
    for i in cur_idx:
        c = df.at[i, "currency"]
        if c in cur_variants:
            df.at[i, "currency"] = random.choice(cur_variants[c])

    # 5. Future transaction dates (3%)
    future_idx = random.sample(range(len(df)), int(len(df) * 0.03))
    for i in future_idx:
        df.at[i, "transaction_date"] = future_date(365)

    # 6. Zero amount transactions (2%)
    zero_idx = random.sample(range(len(df)), int(len(df) * 0.02))
    for i in zero_idx:
        df.at[i, "amount"] = 0

    df["amount"] = df["amount"].astype(object)
    # 7. Amount stored as string with "$" symbol (5%)
    dollar_idx = random.sample(range(len(df)), int(len(df) * 0.05))
    for i in dollar_idx:
        df.at[i, "amount"] = f"${df.at[i, 'amount']}"

    # 8. Mixed status casing
    stat_map = {"Completed": ["completed", "COMPLETED", "complete"], "Pending": ["pending", "PENDING"]}
    stat_idx = random.sample(range(len(df)), int(len(df) * 0.06))
    for i in stat_idx:
        s = df.at[i, "status"]
        if s in stat_map:
            df.at[i, "status"] = random.choice(stat_map[s])

    print(f"    -> {len(df)} rows generated (with DQ issues)")
    return df


# ─── INSURANCE DATASET ────────────────────────────────────────────────────────

def generate_insurance(n=N) -> pd.DataFrame:
    print(f"  Generating Insurance dataset ({n} rows)...")
    policy_types = ["Health", "Life", "Auto", "Home", "Commercial"]
    claim_statuses = ["Submitted", "Under Review", "Approved", "Rejected", "Settled"]
    states = ["CA", "TX", "FL", "NY", "IL", "WA", "GA", "AZ", "NC", "CO"]
    adjusters = [fake.name() for _ in range(20)]

    records = []
    for i in range(n):
        pol_start = fake.date_between(start_date="-6y", end_date="-1y")
        pol_end = pol_start + timedelta(days=365 * random.randint(1, 5))
        claim_dt = fake.date_between(start_date=pol_start, end_date=min(pol_end, date.today()))
        coverage = round(random.uniform(10000, 2000000), 2)
        claim_amt = round(random.uniform(100, coverage * 0.8), 2)
        claim_status = random.choice(claim_statuses)

        records.append({
            "policy_id": f"POL-{i+1:07d}",
            "claim_id": f"CLM-{i+1:08d}" if random.random() > 0.15 else None,
            "customer_id": f"CUST-{random.randint(10000, 99999)}",
            "customer_name": fake.name(),
            "ssn": f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}",
            "email": fake.email(),
            "phone": fake.phone_number(),
            "address": fake.street_address(),
            "zip_code": fake.zipcode(),
            "state": random.choice(states),
            "policy_type": random.choice(policy_types),
            "coverage_amount": coverage,
            "premium": round(coverage * random.uniform(0.002, 0.015), 2),
            "deductible": round(random.uniform(250, 10000), 2),
            "policy_start": str(pol_start),
            "policy_end": str(pol_end),
            "claim_date": str(claim_dt),
            "claim_amount": claim_amt,
            "claim_status": claim_status,
            "adjuster": random.choice(adjusters) if claim_status != "Submitted" else None,
            "settlement_amount": round(claim_amt * random.uniform(0.6, 1.0), 2) if claim_status == "Settled" else None,
            "last_updated": str(fake.date_between(start_date="-2y", end_date="today")),
        })

    df = pd.DataFrame(records)

    # ── Inject DQ Issues ──
    # 1. Nulls: adjuster (12%), zip_code (5%), ssn (8%), settlement for settled claims
    df["adjuster"] = inject_nulls(df["adjuster"], 0.12)
    df["zip_code"] = inject_nulls(df["zip_code"], 0.05)

    # 2. Duplicate claims (6%)
    dup_n = int(n * 0.06)
    dup_rows = df.sample(dup_n, random_state=4).copy()
    dup_rows["policy_id"] = [f"POL-{n+i+1:07d}" for i in range(dup_n)]
    df = pd.concat([df, dup_rows], ignore_index=True)

    # 3. Claim amount > coverage amount (5%)
    exceed_idx = random.sample(range(len(df)), int(len(df) * 0.05))
    for i in exceed_idx:
        df.at[i, "claim_amount"] = df.at[i, "coverage_amount"] * random.uniform(1.1, 3.0)

    # 4. Policy end before start (3%)
    swap_idx = random.sample(range(len(df)), int(len(df) * 0.03))
    for i in swap_idx:
        df.at[i, "policy_end"] = str(fake.date_between(start_date="-8y", end_date="-7y"))

    # 5. Invalid zip codes (4%)
    zip_idx = random.sample(range(len(df)), int(len(df) * 0.04))
    for i in zip_idx:
        df.at[i, "zip_code"] = random.choice(["ABCDE", "1234", "00000", "ZIP-NA", "999"])

    # 6. Inconsistent policy_type casing
    type_map = {"Health": ["health", "HEALTH"], "Life": ["life", "LIFE"], "Auto": ["auto", "AUTO"]}
    type_idx = random.sample(range(len(df)), int(len(df) * 0.07))
    for i in type_idx:
        t = df.at[i, "policy_type"]
        if t in type_map:
            df.at[i, "policy_type"] = random.choice(type_map[t])

    # 7. Stale records (10%)
    stale_idx = random.sample(range(len(df)), int(len(df) * 0.10))
    for i in stale_idx:
        df.at[i, "last_updated"] = str(fake.date_between(start_date="-5y", end_date="-2y"))

    print(f"    -> {len(df)} rows generated (with DQ issues)")
    return df


# ─── SUPPLY CHAIN DATASET ─────────────────────────────────────────────────────

def generate_supply_chain(n=N) -> pd.DataFrame:
    print(f"  Generating Supply Chain dataset ({n} rows)...")
    categories = ["Electronics", "Machinery", "Raw Materials", "Chemicals", "Food & Beverage", "Textiles", "Packaging"]
    statuses = ["Ordered", "In Transit", "Delivered", "Cancelled", "Returned"]
    qc_results = ["Pass", "Fail", "Pending"]
    warehouses = [f"WH-{i:03d}" for i in range(1, 15)]
    wh_locations = ["Chicago, IL", "Dallas, TX", "Los Angeles, CA", "New York, NY", "Atlanta, GA", "Seattle, WA"]
    suppliers = [(f"SUP-{i:05d}", fake.company()) for i in range(1, 80)]
    products = [(f"PRD-{i:06d}", fake.catch_phrase()) for i in range(1, 200)]

    records = []
    for i in range(n):
        supplier = random.choice(suppliers)
        product = random.choice(products)
        order_dt = fake.date_between(start_date="-3y", end_date="-1m")
        expected_dt = order_dt + timedelta(days=random.randint(5, 60))
        actual_dt = expected_dt + timedelta(days=random.randint(-5, 20)) if random.random() > 0.1 else None
        qty = random.randint(1, 5000)
        unit_price = round(random.uniform(0.5, 10000), 4)
        total = round(qty * unit_price, 2)
        status = random.choice(statuses)

        records.append({
            "order_id": f"ORD-{i+1:08d}",
            "supplier_id": supplier[0],
            "supplier_name": supplier[1],
            "product_id": product[0],
            "product_name": product[1],
            "category": random.choice(categories),
            "order_date": str(order_dt),
            "expected_delivery": str(expected_dt),
            "actual_delivery": str(actual_dt) if actual_dt else None,
            "quantity": qty,
            "unit_price": unit_price,
            "total_amount": total,
            "warehouse_id": random.choice(warehouses),
            "warehouse_location": random.choice(wh_locations),
            "status": status,
            "quality_check": random.choice(qc_results) if status in ["Delivered", "Returned"] else "Pending",
            "inspector": fake.name() if status in ["Delivered", "Returned"] else None,
            "last_updated": str(fake.date_between(start_date="-2y", end_date="today")),
        })

    df = pd.DataFrame(records)

    # ── Inject DQ Issues ──
    # 1. Missing supplier_id (6%), quality_check (15% when delivered)
    df["supplier_id"] = inject_nulls(df["supplier_id"], 0.06)
    df["quality_check"] = inject_nulls(df["quality_check"], 0.12)
    df["inspector"] = inject_nulls(df["inspector"], 0.15)

    # 2. Negative quantities (4%)
    neg_q_idx = random.sample(range(len(df)), int(len(df) * 0.04))
    for i in neg_q_idx:
        df.at[i, "quantity"] = -abs(df.at[i, "quantity"])

    # 3. total_amount != qty * unit_price (7%)
    wrong_total_idx = random.sample(range(len(df)), int(len(df) * 0.07))
    for i in wrong_total_idx:
        df.at[i, "total_amount"] = round(df.at[i, "total_amount"] * random.uniform(0.5, 1.8), 2)

    # 4. Actual delivery before order date (4%)
    early_idx = random.sample(range(len(df)), int(len(df) * 0.04))
    for i in early_idx:
        try:
            od = datetime.strptime(str(df.at[i, "order_date"]), "%Y-%m-%d")
            df.at[i, "actual_delivery"] = str((od - timedelta(days=random.randint(1, 30))).date())
        except Exception:
            pass

    # 5. Expected delivery before order date (3%)
    exp_early_idx = random.sample(range(len(df)), int(len(df) * 0.03))
    for i in exp_early_idx:
        try:
            od = datetime.strptime(str(df.at[i, "order_date"]), "%Y-%m-%d")
            df.at[i, "expected_delivery"] = str((od - timedelta(days=random.randint(1, 10))).date())
        except Exception:
            pass

    # 6. Duplicate orders (5%)
    dup_n = int(n * 0.05)
    dup_rows = df.sample(dup_n, random_state=5).copy()
    dup_rows["order_id"] = [f"ORD-{n+i+1:08d}" for i in range(dup_n)]
    df = pd.concat([df, dup_rows], ignore_index=True)

    # 7. Inconsistent category casing
    cat_idx = random.sample(range(len(df)), int(len(df) * 0.06))
    for i in cat_idx:
        df.at[i, "category"] = df.at[i, "category"].upper() if random.random() > 0.5 else df.at[i, "category"].lower()

    # 8. Zero quantity (2%)
    zero_idx = random.sample(range(len(df)), int(len(df) * 0.02))
    for i in zero_idx:
        df.at[i, "quantity"] = 0

    print(f"    -> {len(df)} rows generated (with DQ issues)")
    return df


# ─── AUTOMOTIVE DATASET ───────────────────────────────────────────────────────

def generate_automotive(n=N) -> pd.DataFrame:
    print(f"  Generating Automotive dataset ({n} rows)...")
    makes = ["Ford", "Toyota", "Honda", "BMW", "Mercedes", "Chevrolet", "Tesla", "Nissan", "Hyundai", "Kia"]
    models_per_make = {
        "Ford": ["F-150", "Mustang", "Explorer", "Escape", "Bronco"],
        "Toyota": ["Camry", "Corolla", "RAV4", "Highlander", "Tacoma"],
        "Honda": ["Civic", "Accord", "CR-V", "Pilot", "Odyssey"],
        "BMW": ["3 Series", "5 Series", "X3", "X5", "M4"],
        "Mercedes": ["C-Class", "E-Class", "GLE", "GLC", "S-Class"],
        "Chevrolet": ["Silverado", "Equinox", "Malibu", "Traverse", "Tahoe"],
        "Tesla": ["Model 3", "Model S", "Model X", "Model Y", "Cybertruck"],
        "Nissan": ["Altima", "Sentra", "Rogue", "Pathfinder", "Frontier"],
        "Hyundai": ["Elantra", "Tucson", "Santa Fe", "Sonata", "Palisade"],
        "Kia": ["Sorento", "Telluride", "Sportage", "Soul", "Forte"],
    }
    engine_types = ["Gasoline", "Diesel", "Electric", "Hybrid", "Plug-in Hybrid"]
    service_types = ["Oil Change", "Tire Rotation", "Brake Service", "Engine Repair", "Body Work", "Inspection", "Battery Replacement", "Other"]
    warranty_statuses = ["Active", "Expired", "Not Applicable"]
    technicians = [fake.name() for _ in range(25)]

    def gen_vin():
        """Generate a valid-looking 17-char VIN (no I,O,Q)."""
        chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
        return "".join(random.choices(chars, k=17))

    records = []
    for i in range(n):
        make = random.choice(makes)
        model = random.choice(models_per_make[make])
        year = random.randint(1995, 2024)
        mileage = random.randint(0, 250000)
        svc_date = fake.date_between(start_date="-4y", end_date="today")
        parts = round(random.uniform(0, 2000), 2)
        labor = round(random.uniform(50, 1500), 2)
        cost = round(parts + labor, 2)
        warranty = "Active" if year >= 2020 else random.choice(["Expired", "Not Applicable"])

        records.append({
            "vehicle_id": f"VEH-{i+1:06d}",
            "vin": gen_vin(),
            "make": make,
            "model": model,
            "year": year,
            "color": fake.color_name(),
            "engine_type": random.choice(engine_types),
            "mileage": mileage,
            "customer_id": f"CUST-{random.randint(10000, 99999)}",
            "customer_name": fake.name(),
            "email": fake.email(),
            "phone": fake.phone_number(),
            "service_id": f"SVC-{i+1:08d}",
            "service_date": str(svc_date),
            "service_type": random.choice(service_types),
            "technician": random.choice(technicians),
            "cost": cost,
            "parts_cost": parts,
            "labor_cost": labor,
            "warranty_status": warranty,
            "last_inspection": str(fake.date_between(start_date="-2y", end_date="today")),
            "status": random.choice(["Active", "Inactive", "Scrapped"]),
            "last_updated": str(fake.date_between(start_date="-3y", end_date="today")),
        })

    df = pd.DataFrame(records)

    # ── Inject DQ Issues ──
    # 1. Invalid VINs (6%): wrong length or invalid chars
    vin_invalid_idx = random.sample(range(len(df)), int(len(df) * 0.06))
    for i in vin_invalid_idx:
        df.at[i, "vin"] = random.choice([
            "INVALIDVIN123",
            "1HGBH41JXMN10916",  # 17 chars but has I
            "0" * 17,
            "ABC123",
            "VIN-MISSING",
            "1HGCM82633A" + "O04747",  # has O
        ])

    # 2. Duplicate service records (6%)
    dup_n = int(n * 0.06)
    dup_rows = df.sample(dup_n, random_state=6).copy()
    dup_rows["service_id"] = [f"SVC-{n+i+1:08d}" for i in range(dup_n)]
    df = pd.concat([df, dup_rows], ignore_index=True)

    # 3. Cost != parts + labor (7%)
    wrong_cost_idx = random.sample(range(len(df)), int(len(df) * 0.07))
    for i in wrong_cost_idx:
        df.at[i, "cost"] = round(df.at[i, "cost"] * random.uniform(0.4, 2.0), 2)

    # 4. Inconsistent make casing
    make_idx = random.sample(range(len(df)), int(len(df) * 0.08))
    for i in make_idx:
        df.at[i, "make"] = df.at[i, "make"].upper() if random.random() > 0.5 else df.at[i, "make"].lower()

    # 5. Future service dates (3%)
    future_idx = random.sample(range(len(df)), int(len(df) * 0.03))
    for i in future_idx:
        df.at[i, "service_date"] = future_date(180)

    # 6. Negative mileage (2%)
    neg_m_idx = random.sample(range(len(df)), int(len(df) * 0.02))
    for i in neg_m_idx:
        df.at[i, "mileage"] = -abs(df.at[i, "mileage"])

    # 7. Missing technician (8%)
    df["technician"] = inject_nulls(df["technician"], 0.08)
    df["email"] = inject_nulls(df["email"], 0.06)
    df["phone"] = inject_nulls(df["phone"], 0.05)

    # 8. Year outliers (1%)
    year_idx = random.sample(range(len(df)), int(len(df) * 0.01))
    for i in year_idx:
        df.at[i, "year"] = random.choice([1899, 1900, 2099, 2100, -1])

    print(f"    -> {len(df)} rows generated (with DQ issues)")
    return df


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def generate_all():
    print("\n" + "="*60)
    print("  DQ Agent Framework — Synthetic Dataset Generator")
    print("="*60)
    print(f"\nOutput directory: {RAW_DIR}\n")

    datasets = {
        "healthcare": generate_healthcare,
        "finance": generate_finance,
        "insurance": generate_insurance,
        "supply_chain": generate_supply_chain,
        "automotive": generate_automotive,
    }

    total = 0
    for name, gen_fn in datasets.items():
        df = gen_fn()
        out_path = RAW_DIR / f"{name}_dataset.csv"
        df.to_csv(out_path, index=False)
        print(f"    [OK] Saved: {out_path.name} ({len(df):,} rows x {len(df.columns)} cols)")
        total += len(df)

    print(f"\n{'='*60}")
    print(f"  ✅ All datasets generated! Total: {total:,} rows across 5 domains")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    generate_all()

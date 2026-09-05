import streamlit as st
import pandas as pd

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="JSL Stainless Steel Grade Selector", layout="wide")

# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------
@st.cache_data
def load_data():
    df = pd.read_csv("grades.csv")
    return df

df = load_data()

# ---------------------------------------------------------
# HELPER: cost rank by family (lower = cheaper)
# ---------------------------------------------------------
COST_RANK = {
    "Ferritic": 1,
    "Martensitic": 2,
    "Lean Duplex": 3,
    "Austenitic": 4,          # generic 200/300 series fallback
    "Standard Duplex": 5,
    "Super Duplex": 6,
}

def get_cost_rank(family):
    for key, rank in COST_RANK.items():
        if key.lower() in str(family).lower():
            return rank
    return 4  # default mid-rank

# ---------------------------------------------------------
# HELPER: map dropdown choices to numeric filters
# ---------------------------------------------------------
TEMP_MAP = {
    "Room temperature (up to 100°C)": 0,
    "Moderate (100–400°C)": 400,
    "High (400–800°C)": 800,
    "Very high (800°C+)": 900,
    "Sub-zero / Cryogenic": -200,
}

STRENGTH_MAP = {
    "Low (decorative / light-duty)": 0,
    "Medium (general structural)": 200,
    "High (load-bearing / structural)": 400,
    "Very high (heavy engineering)": 550,
}

CORROSION_PREN_MAP = {
    "Mild (indoor, dry, low humidity)": 0,
    "Moderate (normal outdoor / atmospheric)": 18,
    "High chloride / coastal / marine": 30,
    "Acidic (organic acids - food/beverage)": 0,   # handled by family preference, not PREN
    "Acidic (strong inorganic - sulphuric/nitric/phosphoric)": 25,
    "Chemical / industrial exposure": 25,
}

# ---------------------------------------------------------
# SIDEBAR / INPUT FORM  (ALL DROPDOWNS — NO SLIDERS)
# ---------------------------------------------------------
st.title("🔩 Stainless Steel Grade Selector")
st.caption("Jindal Stainless Spark 2026 — Problem Statement 2")

st.markdown("### Tell us about your application")

col1, col2 = st.columns(2)

with col1:
    application = st.selectbox(
        "Application / Industry",
        [
            "Architecture & Building",
            "Automotive & Transport",
            "Railways",
            "Kitchenware & Cookware",
            "Food Processing & Dairy",
            "Chemical & Petrochemical",
            "Oil & Gas",
            "Marine / Sea-water",
            "Power & Heat Exchangers",
            "Pharmaceutical",
            "Construction & Infrastructure",
            "Consumer Appliances",
            "Cutlery & Tools",
            "Other / General Purpose",
        ],
    )

    corrosion_env = st.selectbox(
        "Corrosion Environment",
        [
            "Mild (indoor, dry, low humidity)",
            "Moderate (normal outdoor / atmospheric)",
            "High chloride / coastal / marine",
            "Acidic (organic acids - food/beverage)",
            "Acidic (strong inorganic - sulphuric/nitric/phosphoric)",
            "Chemical / industrial exposure",
        ],
    )

    temperature = st.selectbox(
        "Operating Temperature",
        [
            "Room temperature (up to 100°C)",
            "Moderate (100–400°C)",
            "High (400–800°C)",
            "Very high (800°C+)",
            "Sub-zero / Cryogenic",
        ],
    )

with col2:
    strength = st.selectbox(
        "Strength Requirement",
        [
            "Low (decorative / light-duty)",
            "Medium (general structural)",
            "High (load-bearing / structural)",
            "Very high (heavy engineering)",
        ],
    )

    formability = st.selectbox(
        "Formability Need",
        [
            "Simple bending / basic fabrication",
            "Deep drawing (utensils / cookware)",
            "Welding-heavy fabrication",
            "Minimal forming (as-is sheet/plate use)",
        ],
    )

    cost_priority = st.selectbox(
        "Cost Priority",
        [
            "Lowest cost (budget-driven)",
            "Balanced cost-performance",
            "Performance-first (cost flexible)",
        ],
    )

submit = st.button("🔍 Find Best-Fit Grades", type="primary")

# ---------------------------------------------------------
# SCORING ENGINE
# ---------------------------------------------------------
def score_grades(df, application, corrosion_env, temperature, strength, formability, cost_priority):
    data = df.copy()
    data["Score"] = 0
    data["Reasons"] = ""

    min_temp_needed = TEMP_MAP[temperature]
    min_ys_needed = STRENGTH_MAP[strength]
    min_pren_needed = CORROSION_PREN_MAP[corrosion_env]

    # ---- HARD FILTER: Temperature ----
    def temp_ok(row):
        max_temp = row.get("Max_Service_Temp_C")
        if temperature == "Sub-zero / Cryogenic":
            # Prefer austenitic; disqualify martensitic/ferritic (embrittlement risk)
            return "Ferritic" not in str(row["Family"]) and "Martensitic" not in str(row["Family"])
        if pd.isna(max_temp):
            # No rating stated -> assume unsuitable for High/Very-high temp asks
            return min_temp_needed <= 400
        return max_temp >= min_temp_needed

    data = data[data.apply(temp_ok, axis=1)]

    # ---- HARD FILTER: Strength ----
    data = data[data["YS_MPa_min"].fillna(0) >= min_ys_needed]

    if data.empty:
        return data

    # ---- SOFT SCORING: Corrosion (PREN where available, else family heuristic) ----
    def corrosion_score(row):
        pren = row.get("PREN_approx")
        reasons = []
        score = 0
        if corrosion_env == "Acidic (organic acids - food/beverage)":
            if "Austenitic" in str(row["Family"]):
                score += 3
                reasons.append("good resistance to food-grade organic acids")
        elif not pd.isna(pren):
            if pren >= min_pren_needed:
                score += 3
                reasons.append(f"PREN ~{pren} meets corrosion requirement")
            else:
                score -= 2
        else:
            # no PREN data — mild fallback credit for austenitic/duplex families
            if corrosion_env in ["Mild (indoor, dry, low humidity)", "Moderate (normal outdoor / atmospheric)"]:
                score += 1
        return score, reasons

    # ---- SOFT SCORING: Application keyword match ----
    APP_KEYWORDS = {
        "Architecture & Building": ["architectur", "panel", "trim", "roofing", "handrail", "facade"],
        "Automotive & Transport": ["automotive", "auto", "vehicle", "trailer", "exhaust", "muffler", "chassis"],
        "Railways": ["rail", "coach", "wagon"],
        "Kitchenware & Cookware": ["kitchen", "cookware", "utensil", "cutlery", "sink"],
        "Food Processing & Dairy": ["food", "dairy", "beverage", "brewery"],
        "Chemical & Petrochemical": ["chemical", "petrochemical", "acid"],
        "Oil & Gas": ["oil", "gas", "offshore", "refinery"],
        "Marine / Sea-water": ["marine", "sea", "coastal", "desalination"],
        "Power & Heat Exchangers": ["heat exchanger", "power", "boiler", "furnace"],
        "Pharmaceutical": ["pharma"],
        "Construction & Infrastructure": ["construction", "bridge", "infrastructure", "structural"],
        "Consumer Appliances": ["appliance", "washing machine", "refrigerator", "dishwasher"],
        "Cutlery & Tools": ["cutlery", "knives", "tool"],
        "Other / General Purpose": [],
    }

    def application_score(row):
        keywords = APP_KEYWORDS.get(application, [])
        text = str(row["Applications"]).lower()
        hits = sum(1 for k in keywords if k in text)
        return (2 if hits > 0 else 0), (["matches your stated application"] if hits > 0 else [])

    # ---- SOFT SCORING: Formability ----
    def formability_score(row):
        notes = str(row.get("Formability_Notes", "")).lower()
        family = str(row["Family"])
        score = 0
        reasons = []
        if formability == "Deep drawing (utensils / cookware)":
            if "draw" in notes or "Austenitic" in family:
                score += 2
                reasons.append("good deep-drawing characteristics")
            if "Martensitic" in family:
                score -= 3
        elif formability == "Welding-heavy fabrication":
            if "weld" in notes or "low c" in notes or "stabiliz" in notes:
                score += 2
                reasons.append("good weldability / low-carbon or stabilized grade")
            if "Martensitic" in family:
                score -= 3
        return score, reasons

    # ---- SOFT SCORING: Cost ----
    def cost_score(row):
        rank = get_cost_rank(row["Family"])
        score = 0
        reasons = []
        if cost_priority == "Lowest cost (budget-driven)":
            score += (7 - rank)  # cheaper family -> higher score
            if rank <= 2:
                reasons.append("economical grade family")
        elif cost_priority == "Performance-first (cost flexible)":
            score += rank * 0.5
        return score, reasons

    total_scores = []
    total_reasons = []
    for _, row in data.iterrows():
        s = 0
        r = []
        for fn in [corrosion_score, application_score, formability_score, cost_score]:
            sc, rs = fn(row)
            s += sc
            r.extend(rs)
        total_scores.append(s)
        total_reasons.append("; ".join(r) if r else "meets your core requirements")

    data["Score"] = total_scores
    data["Reasons"] = total_reasons

    data = data.sort_values("Score", ascending=False)
    return data

# ---------------------------------------------------------
# RESULTS
# ---------------------------------------------------------
if submit:
    results = score_grades(df, application, corrosion_env, temperature, strength, formability, cost_priority)

    if results.empty:
        st.error("No grades matched your combination of requirements. Try relaxing temperature or strength.")
    else:
        top_results = results.head(3)
        st.markdown("## ✅ Recommended Grades")

        for i, (_, row) in enumerate(top_results.iterrows(), start=1):
            with st.container(border=True):
                st.subheader(f"{i}. {row['Grade']}  —  {row['Family']}")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("UTS (MPa)", f"{row['UTS_MPa_min']}")
                c2.metric("YS (MPa)", f"{row['YS_MPa_min']}")
                c3.metric("Elongation %", f"{row['EL_pct_min']}")
                c4.metric("Hardness", f"{row['Hardness']}")

                st.write(f"**Why this grade:** {row['Reasons']}")
                st.write(f"**Typical applications:** {row['Applications']}")
                if not pd.isna(row.get("Corrosion_Notes")):
                    st.write(f"**Corrosion behaviour:** {row['Corrosion_Notes']}")
                if not pd.isna(row.get("Max_Service_Temp_C")):
                    st.write(f"**Max service temperature:** {row['Max_Service_Temp_C']} °C")

        st.markdown("### ⚖️ Trade-off comparison")
        compare_cols = [
            "Grade", "Family", "UTS_MPa_min", "YS_MPa_min", "EL_pct_min",
            "Hardness", "PREN_approx", "Max_Service_Temp_C"
        ]
        st.dataframe(top_results[compare_cols].reset_index(drop=True))

        st.info(
            "💡 **Trade-off tip:** Higher corrosion resistance (higher PREN, more Ni/Mo) "
            "generally means higher cost. If budget is tight, consider the lower-ranked "
            "option above if its corrosion margin still covers your environment."
        )
else:
    st.info("Fill in the fields above and click **Find Best-Fit Grades** to get your recommendation.")

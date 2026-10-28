"""
Generate the SIMULATED transaction data for "Hearthline", a fictional homeware retailer
with one store in each of 12 UK & Ireland cities plus a website.

The company is fictional. Every input is either an OFFICIAL statistic, an INDUSTRY BENCHMARK,
or a stated ASSUMPTION; each one is labelled below and listed in the report's assumptions register.
Official inputs:
  * data/clean/city_profile.csv                  -> store demand (retail GVA), basket size (income), customer location (spending power)
  * data/raw/uk_internet_share_of_retail_J4MC.csv -> monthly share of orders placed online (ONS J4MC)
  * data/raw/uk_retail_weekly_value_JE4W.csv     -> monthly seasonality and annual growth of UK retail (ONS JE4W)
  * data/raw/uk_population_mid2025.xlsx          -> age profile of adult customers (ONS mid-2025 estimates)
Benchmark inputs:
  * data/raw/dunelm_prices_2026-10.csv           -> base price of each product type (median on Dunelm's category pages, Oct 2026)

Output (data/simulated/): stores, customers, products, orders, order_lines, returns  (CSV)
Some data-quality problems are injected on purpose so the SQL cleaning step has real work to do;
they are listed in data/simulated/README_data_quality.md.

Run:  python src/generate_data.py
"""
import os
import numpy as np
import pandas as pd

SEED = 42
START, END = "2024-01-01", "2026-09-30"          # last complete month before the project date
OUT = "data/simulated"
ORDERS_PER_YEAR = 120_000                          # ASSUMPTION: scale of a small 12-store chain (see report, assumptions register)

rng = np.random.default_rng(SEED)
os.makedirs(OUT, exist_ok=True)

# ----------------------------------------------------------------------------- real inputs
city = pd.read_csv("data/clean/city_profile.csv")
j4mc = pd.read_csv("data/raw/uk_internet_share_of_retail_J4MC.csv", header=None, names=["period", "value"])
j4mc = j4mc[j4mc["period"].str.match(r"^\d{4} [A-Z]{3}$", na=False)]
j4mc.index = pd.to_datetime(j4mc["period"], format="%Y %b")
online_share = pd.to_numeric(j4mc["value"]) / 100

months = pd.date_range(START, END, freq="MS")
online_share = online_share.reindex(months).ffill()          # carry the last published month forward

# OFFICIAL: seasonality and growth of UK retail sales (ONS JE4W, average weekly value, not seasonally adjusted)
je = pd.read_csv("data/raw/uk_retail_weekly_value_JE4W.csv", header=None, names=["period", "value"])
je = je[je["period"].str.match(r"^\d{4} [A-Z]{3}$", na=False)].copy()
je["date"] = pd.to_datetime(je["period"], format="%Y %b")
je["month_total"] = pd.to_numeric(je["value"]) * je["date"].dt.days_in_month / 7
recent = je[je["date"].dt.year.between(2023, 2025)]                  # three complete post-pandemic years
season = recent.groupby(recent["date"].dt.month)["month_total"].mean()
SEASON_TOTAL = (season / season.mean()).tolist()                      # 1.0 = an average month
annual = je.groupby(je["date"].dt.year)["month_total"].agg(["sum", "count"])
annual = annual[annual["count"] == 12]["sum"]
ANNUAL_GROWTH = (annual[2025] / annual[2019]) ** (1 / 6) - 1          # UK retail CAGR 2019-2025, nominal

# OFFICIAL: age profile of UK adults (ONS mid-2025 population estimates), used for customers' age bands
pop = pd.read_excel("data/raw/uk_population_mid2025.xlsx", sheet_name="MYE2 - Persons", header=7)
uk_pop = pop[pop["Code"] == "K02000001"].iloc[0]
def _ages(a, b):
    return sum(uk_pop[str(i)] for i in range(a, b + 1))
AGE_BANDS = {"18-24": _ages(18, 24), "25-34": _ages(25, 34), "35-44": _ages(35, 44),
             "45-54": _ages(45, 54), "55-64": _ages(55, 64), "65+": _ages(65, 89) + uk_pop["90 and over"]}
AGE_P = np.array(list(AGE_BANDS.values()), dtype=float) / sum(AGE_BANDS.values())

# ----------------------------------------------------------------------------- stores
city["income_index"] = city["gdhi_per_head"] / city["gdhi_per_head"].median()
# OFFICIAL base + ASSUMPTION: store demand grows with the city-region's real retail output (ONS GVA),
# but less than proportionally, because one store has limited capacity (exponent 0.45; sensitivity tested 0.3-1.0).
city["store_weight"] = city["retail_gva_gbp_m"] ** 0.45
city["store_weight"] /= city["store_weight"].sum()
city["online_weight"] = city["spending_power_gbp_m"] / city["spending_power_gbp_m"].sum()

stores = city[["city", "nation"]].copy()
stores.insert(0, "store_id", [f"S{i:02d}" for i in range(1, len(stores) + 1)])
stores["store_name"] = "Hearthline " + stores["city"]
stores["country"] = np.where(stores["nation"] == "Ireland", "Ireland", "United Kingdom")
stores["channel"] = "Store"
stores["opened_date"] = pd.to_datetime("2016-01-01") + pd.to_timedelta(rng.integers(0, 2500, len(stores)), "D")
# BENCHMARK range: small-format UK homeware shops are about 2,800-4,500 sq ft
#   2,800 = Oliver Bonas Glasgow Fort (The Industry, Jul 2026); 4,500 = Dunelm Westfield London (Furniture News, Oct 2024)
# DESIGN: the largest-demand store (London) gets 4,500 and the others scale with their demand weight.
# Floor area is descriptive only: it is not used to allocate orders.
stores["floor_area_sqft"] = (2800 + 1700 * city["store_weight"] / city["store_weight"].max()).round(-2).astype(int)
stores["manager_email"] = stores["city"].str.lower().str.replace(" ", "") + ".manager@hearthline.example"
online_store = pd.DataFrame([{"store_id": "WEB", "city": "Online", "nation": "All", "store_name": "Hearthline Online",
                              "country": "UK & Ireland", "channel": "Online", "opened_date": pd.Timestamp("2018-03-01"),
                              "floor_area_sqft": 0, "manager_email": "ecommerce.manager@hearthline.example"}])
stores = pd.concat([stores, online_store], ignore_index=True)

# ----------------------------------------------------------------------------- products
# BENCHMARK: base price of each product type = median price on Dunelm's website category pages (Oct 2026).
# Three types Dunelm does not sell (Coffee Beans, LED Bulb Pack, Advent Candle) keep the earlier design price
# and are labelled ASSUMPTION in the CSV; types with n <= 2 products are labelled "weak" evidence.
price_table = pd.read_csv("data/raw/dunelm_prices_2026-10.csv")
CATALOGUE = {cat: list(zip(g["subcategory"], g["base_price_gbp"]))         # category: [(subcategory, base price)]
             for cat, g in price_table.groupby("category", sort=False)}
VARIANTS = ["Natural", "Charcoal", "Sage", "Oat", "Terracotta"]
SEASON = {  # monthly demand index by category, Jan..Dec
    "Garden & Outdoor": [0.4, 0.5, 0.9, 1.4, 1.8, 1.8, 1.6, 1.3, 0.8, 0.5, 0.4, 0.4],
    "Gifts & Seasonal": [0.3, 0.6, 0.6, 0.5, 0.5, 0.5, 0.5, 0.5, 0.7, 1.2, 2.6, 3.4],
    "Candles & Fragrance": [0.9, 0.9, 0.8, 0.7, 0.7, 0.6, 0.6, 0.7, 1.0, 1.3, 1.5, 1.6],
    "Bedding": [1.4, 1.0, 1.0, 0.9, 0.9, 0.8, 0.8, 0.9, 1.1, 1.1, 1.2, 1.0],
}
rows = []
for cat, items in CATALOGUE.items():
    for item, price in items:
        for v in rng.choice(VARIANTS, size=rng.integers(2, 5), replace=False):
            # every colour of the same item has the same price (as on Dunelm), shown as a .99 price point
            p = np.floor(price + 0.5) - 0.01
            rows.append({"category": cat, "subcategory": item, "product_name": f"{item} - {v}",
                         "unit_price": p, "unit_cost": round(p * rng.uniform(0.38, 0.55), 2)})
products = pd.DataFrame(rows)
products.insert(0, "product_id", [f"P{i:04d}" for i in range(1, len(products) + 1)])
products["sku"] = "HL-" + products["subcategory"].str.upper().str[:3] + "-" + products["product_id"].str[1:]
products["popularity"] = rng.zipf(1.6, len(products)).clip(1, 30).astype(float)

# Items that are bought together (for market basket analysis): subcategory -> (partner, probability)
PAIRS = {"Scented Candle": ("Candle Holder", 0.30), "Duvet Cover": ("Pillowcase Pair", 0.45),
         "Stoneware Mug": ("Coffee Beans", 0.25), "Bath Towel": ("Bath Mat", 0.35),
         "Table Lamp": ("LED Bulb Pack", 0.40), "Gift Set": ("Wrapping Kit", 0.35),
         "Plant Pot": ("Faux Plant", 0.20), "Dinner Plate Set": ("Linen Napkins", 0.25)}

# ----------------------------------------------------------------------------- customers
N_CUST = 70_000
SEGMENTS = {"Loyal": (0.08, 9.0), "Regular": (0.22, 3.0), "Occasional": (0.40, 1.2), "One-off": (0.30, 0.5)}
seg_names = list(SEGMENTS)
seg = rng.choice(seg_names, N_CUST, p=[v[0] for v in SEGMENTS.values()])
home = rng.choice(city["city"], N_CUST, p=(0.5 * city["store_weight"] + 0.5 * city["online_weight"]).values)
# about 30% of customers were already customers before 2024; the rest join during the period
pre = rng.random(N_CUST) < 0.30
signup = np.where(pre,
                  pd.Timestamp("2019-01-01") + pd.to_timedelta(rng.integers(0, 1826, N_CUST), "D"),
                  pd.Timestamp(START) + pd.to_timedelta(rng.integers(0, (pd.Timestamp(END) - pd.Timestamp(START)).days - 30, N_CUST), "D"))
signup = pd.to_datetime(signup)
# customers stop buying after an exponential "lifetime" (shorter for occasional / one-off)
life_days = rng.exponential(scale=np.select([seg == "Loyal", seg == "Regular", seg == "Occasional"], [1400, 700, 360], 120))
churn = signup + pd.to_timedelta(life_days.astype(int) + 30, "D")
customers = pd.DataFrame({
    "customer_id": [f"C{i:06d}" for i in range(1, N_CUST + 1)],
    "signup_date": signup.normalize(),
    "home_city": home,
    "loyalty_member": rng.random(N_CUST) < np.select([seg == "Loyal", seg == "Regular"], [0.9, 0.6], 0.25),
    "age_band": rng.choice(list(AGE_BANDS), N_CUST, p=AGE_P),
    "marketing_opt_in": rng.random(N_CUST) < 0.55,
})
cust_weight = np.array([SEGMENTS[s][1] for s in seg])
cust_online_pref = np.clip(rng.beta(2, 3, N_CUST) + (customers["age_band"].isin(["18-24", "25-34"]) * 0.15).values, 0, 1)

# ----------------------------------------------------------------------------- orders
base_per_month = ORDERS_PER_YEAR / 12 / np.mean(SEASON_TOTAL)
cat_names = list(CATALOGUE)
order_frames, line_frames = [], []
order_seq = 0

def pick_customers(n, month_start, pool_mask, online):
    """Choose who places each order: customers active this month, weighted by segment and channel preference."""
    active = pool_mask & (customers["signup_date"].values <= month_start + pd.offsets.MonthEnd(0)) & (churn.values >= month_start)
    idx = np.flatnonzero(active)
    if len(idx) == 0:
        return np.array([None] * n)
    w = cust_weight[idx] * (cust_online_pref[idx] if online else (1 - cust_online_pref[idx]))
    return customers["customer_id"].values[rng.choice(idx, n, p=w / w.sum())]

for m in months:
    trend = (1 + ANNUAL_GROWTH) ** ((m - pd.Timestamp(START)).days / 365.25)   # OFFICIAL: UK retail growth rate
    n_total = rng.poisson(base_per_month * SEASON_TOTAL[m.month - 1] * trend)
    n_online = rng.binomial(n_total, online_share[m])
    n_store = n_total - n_online
    days_in_month = m.days_in_month

    chunks = []
    # store orders: split across the 12 stores by calibrated weights
    store_counts = rng.multinomial(n_store, city["store_weight"].values)
    for (sid, cty), k in zip(stores.loc[stores["channel"] == "Store", ["store_id", "city"]].values, store_counts):
        local = customers["home_city"].values == cty
        identified = rng.random(k) < 0.82                                      # the rest are guest checkouts
        cust = np.array([None] * k, dtype=object)
        n_id = identified.sum()
        visitors = rng.random(n_id) < 0.08                                     # shoppers from another city
        cust_ids = pick_customers(n_id, m, local, online=False)
        if visitors.any():
            cust_ids[visitors] = pick_customers(visitors.sum(), m, ~local, online=False)
        cust[identified] = cust_ids
        hours = rng.choice(np.arange(9, 20), k, p=(lambda w: w / w.sum())(np.array([2, 4, 6, 8, 9, 9, 9, 9, 8, 6, 4])))
        chunks.append(pd.DataFrame({"store_id": sid, "channel": "Store", "customer_id": cust, "hour": hours,
                                    "basket_city": cty}))
    # online orders: customers anywhere, weighted toward spending power via the customer pool
    cust = pick_customers(n_online, m, np.ones(N_CUST, bool), online=True)
    hours = rng.choice(np.arange(24), n_online, p=(lambda w: w / w.sum())(np.array([1, .6, .4, .3, .3, .5, 1, 2, 3, 4, 4, 4, 5, 5, 4, 4, 4, 5, 6, 7, 8, 8, 6, 3])))
    home_lookup = customers.set_index("customer_id")["home_city"]
    chunks.append(pd.DataFrame({"store_id": "WEB", "channel": "Online", "customer_id": cust, "hour": hours,
                                "basket_city": home_lookup.reindex(cust).values}))

    o = pd.concat(chunks, ignore_index=True)
    day = rng.integers(1, days_in_month + 1, len(o))
    o["order_datetime"] = (m + pd.to_timedelta(day - 1, "D") + pd.to_timedelta(o["hour"], "h")
                           + pd.to_timedelta(rng.integers(0, 3600, len(o)), "s"))
    o["order_id"] = [f"O{order_seq + i:07d}" for i in range(1, len(o) + 1)]
    order_seq += len(o)

    # promotions: Black Friday week (20% off), January sale (25% off Bedding/Home Decor), member discount 10%
    d = o["order_datetime"]
    bf = pd.Timestamp(year=m.year, month=11, day=1) + pd.offsets.WeekOfMonth(week=3, weekday=4)
    o["promo_code"] = np.where((d >= bf - pd.Timedelta(days=4)) & (d <= bf + pd.Timedelta(days=3)), "BLACKFRIDAY20",
                      np.where((d.dt.month == 1) & (d.dt.day <= 20), "JANSALE25", None))
    # BENCHMARK (stores): cash 8% of UK payments in 2025; contactless about 60% of card payments (UK Finance, UK Payment Markets 2026)
    # ASSUMPTION (online): card, PayPal and gift card shares; payment method is not used in any finding
    is_online = (o["channel"] == "Online").values
    o["payment_method"] = np.where(
        is_online,
        rng.choice(["Card", "PayPal", "Gift card"], len(o), p=[.80, .15, .05]),
        rng.choice(["Contactless", "Card", "Cash", "Gift card"], len(o), p=[.55, .32, .08, .05]))

    # ----- order lines: number of items depends on channel and the city's income level
    inc = city.set_index("city")["income_index"].reindex(o["basket_city"]).fillna(1).values
    lam = np.where(o["channel"] == "Online", 1.5, 1.1) * inc ** 0.6
    n_items = 1 + rng.poisson(lam)
    li = o.loc[o.index.repeat(n_items), ["order_id", "promo_code"]].reset_index(drop=True)
    month_w = np.array([SEASON.get(c, [1] * 12)[m.month - 1] for c in cat_names])
    cats = rng.choice(cat_names, len(li), p=month_w / month_w.sum())
    li["product_id"] = None
    for c in cat_names:
        pool = products[products["category"] == c]
        mask = cats == c
        li.loc[mask, "product_id"] = rng.choice(pool["product_id"].values, mask.sum(), p=(pool["popularity"] / pool["popularity"].sum()).values)
    # add "bought together" partners
    sub = products.set_index("product_id")["subcategory"]
    extra = []
    for a, (b, prob) in PAIRS.items():
        hit = li[(sub.reindex(li["product_id"]).values == a) & (rng.random(len(li)) < prob)]
        partners = products[products["subcategory"] == b]["product_id"].values
        extra.append(hit[["order_id", "promo_code"]].assign(product_id=rng.choice(partners, len(hit))))
    li = pd.concat([li] + extra, ignore_index=True)
    li = li.drop_duplicates(["order_id", "product_id"])

    price = products.set_index("product_id").reindex(li["product_id"])
    li["unit_price"] = price["unit_price"].values
    cheap = li["unit_price"].values < 15
    li["quantity"] = np.where(cheap, rng.choice([1, 2, 3, 4], len(li), p=[.6, .25, .1, .05]), rng.choice([1, 2], len(li), p=[.93, .07]))
    li["discount_pct"] = np.select(
        [li["promo_code"].eq("BLACKFRIDAY20"),
         li["promo_code"].eq("JANSALE25") & price["category"].isin(["Bedding", "Home Decor"]).values],
        [0.20, 0.25], 0.0)
    order_frames.append(o.drop(columns=["hour", "basket_city"]))
    line_frames.append(li.drop(columns=["promo_code"]))

orders = pd.concat(order_frames, ignore_index=True)
lines = pd.concat(line_frames, ignore_index=True)
lines.insert(0, "order_line_id", [f"L{i:08d}" for i in range(1, len(lines) + 1)])

# member discount: 10% on full-price lines for loyalty members
member = customers.set_index("customer_id")["loyalty_member"]
is_member = member.reindex(orders.set_index("order_id").loc[lines["order_id"], "customer_id"]).fillna(False).astype(bool).values
lines.loc[is_member & (lines["discount_pct"] == 0) & (rng.random(len(lines)) < 0.5), "discount_pct"] = 0.10

# ----------------------------------------------------------------------------- returns
chan = orders.set_index("order_id").loc[lines["order_id"], "channel"].values
# BENCHMARK: online returns 10% of lines (below the IMRG UK all-category average of 15-17%, because homeware is returned
# less than fashion); in-store returns = online / 2.8, the online-to-store ratio in Appriss Retail & Deloitte (2024): 24.5% vs 8.7%
RETURN_ONLINE = 0.10
RETURN_STORE = RETURN_ONLINE / (24.52 / 8.72)
ret = rng.random(len(lines)) < np.where(chan == "Online", RETURN_ONLINE, RETURN_STORE)
r = lines.loc[ret, ["order_line_id", "order_id", "quantity"]].copy()
odate = orders.set_index("order_id").loc[r["order_id"], "order_datetime"].values
returns = pd.DataFrame({
    "return_id": [f"R{i:07d}" for i in range(1, len(r) + 1)],
    "order_line_id": r["order_line_id"].values,
    "return_date": (pd.to_datetime(odate) + pd.to_timedelta(rng.integers(1, 30, len(r)), "D")).normalize(),
    "quantity_returned": np.minimum(r["quantity"].values, rng.choice([1, 2], len(r), p=[.9, .1])),
    "reason": rng.choice(["Changed mind", "Damaged", "Not as described", "Wrong size/colour", "Late delivery"], len(r), p=[.38, .2, .17, .15, .1]),
})
returns = returns[returns["return_date"] <= pd.Timestamp(END)]

# ----------------------------------------------------------------------------- deliberate data-quality issues
# 1) inconsistent city text in the customer table
messy = rng.random(N_CUST) < 0.06
customers.loc[messy, "home_city"] = [rng.choice([c.upper(), c.lower(), f" {c} ", c + " "]) for c in customers.loc[messy, "home_city"]]
customers.loc[(customers["home_city"].str.strip().str.lower() == "manchester") & (rng.random(N_CUST) < 0.02), "home_city"] = "Mcr"
# 2) duplicated order lines (system re-sent the same rows)
dups = lines.sample(frac=0.003, random_state=SEED)
lines = pd.concat([lines, dups], ignore_index=True)
# 3) a few test orders from staff with zero price
tests = lines.sample(25, random_state=SEED + 1).index
lines.loc[tests, "unit_price"] = 0.0

# ----------------------------------------------------------------------------- save
products = products.drop(columns="popularity")
stores["opened_date"] = stores["opened_date"].dt.date
for name, df in {"stores": stores, "customers": customers, "products": products, "orders": orders,
                 "order_lines": lines, "returns": returns}.items():
    df.to_csv(f"{OUT}/{name}.csv", index=False, lineterminator="\n")   # same line endings on Windows and Mac, so SQL BULK INSERT works
    print(f"{name:12} {len(df):>9,} rows")

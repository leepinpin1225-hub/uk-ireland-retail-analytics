"""
Robustness check for weak-evidence prices (report section 3.7).
Shifts the 12 weak or assumed product prices by x0.5-x1.5, then runs 300 Monte Carlo draws
with each price multiplied by an independent U(0.5, 1.5), and recomputes the headline metrics.
Run after notebook 03:  python src/price_robustness.py
"""
import pandas as pd, numpy as np
rng=np.random.default_rng(7)
o=pd.read_csv("data/simulated/orders.csv",parse_dates=["order_datetime"],usecols=["order_id","store_id","channel","customer_id","order_datetime"])
l=pd.read_csv("data/simulated/order_lines.csv").drop_duplicates("order_line_id"); l=l[l.unit_price>0]
p=pd.read_csv("data/simulated/products.csv")[["product_id","subcategory","unit_cost"]]
l=l.merge(p,on="product_id").merge(o,on="order_id")
l["net"]=l.quantity*l.unit_price*(1-l.discount_pct); l["cost"]=l.quantity*l.unit_cost
st=pd.read_csv("data/simulated/stores.csv")[["store_id","city"]]
city=pd.read_csv("data/clean/city_profile.csv").set_index("city")
spend=city.spending_power_gbp_m/city.spending_power_gbp_m.sum()
snap=pd.Timestamp("2026-09-30 23:59:59")
last=(l.order_datetime>snap-pd.DateOffset(years=1))
rfm=pd.read_csv("data/clean/rfm_segments.csv")[["customer_id","segment"]]
weak=["Outdoor Cushion","Wall Mirror","Bath Robe","Advent Candle","Bath Towel","Serving Board","Coffee Beans","Storage Basket","LED Bulb Pack","Solar Lantern","Wrapping Kit","Tealight Pack"]
sub=l.subcategory.values
def metrics(mult):
    m=np.ones(len(l)); 
    for k,v in mult.items(): m[sub==k]=v
    net=l.net.values*m; cost=l.cost.values*m
    d=pd.DataFrame({"net":net,"cost":cost,"store_id":l.store_id.values,"cust":l.customer_id.values,"order_id":l.order_id.values,"last":last.values,"ytd":((l.order_datetime.dt.year==2026)).values})
    s=d[d["last"]&(d.store_id!="WEB")].groupby("store_id").net.sum()
    s=s.rename(index=dict(zip(st.store_id,st.city))); share=s/s.sum()
    cap=share/spend.reindex(share.index)
    k=d[d["last"]&d.cust.notna()].groupby("cust").net.sum()
    top=k.sort_values(ascending=False); top20=top.iloc[:int(len(top)*0.2)].sum()/top.sum()
    seg=k.rename_axis("customer_id").reset_index().merge(rfm,on="customer_id")
    champ=seg[seg.segment=="Champions"].net.sum()/seg.net.sum()
    y=d[d.ytd]; aov=y.net.sum()/y.order_id.nunique(); margin=1-y.cost.sum()/y.net.sum()
    return dict(london=cap["London"],belfast=cap["Belfast"],min_other=cap.drop("London").min(),n_below1=(cap<1).sum(),
                champ_rev=champ,top20=top20,aov=aov,margin=margin)
base=metrics({})
rows=[dict(case="base",**base)]
for f in [0.5,0.75,1.25,1.5]:
    rows.append(dict(case=f"all weak x{f}",**metrics({w:f for w in weak})))
mc=[metrics({w:rng.uniform(0.5,1.5) for w in weak}) for _ in range(300)]
mc=pd.DataFrame(mc)
print(pd.DataFrame(rows).round(3).to_string())
print("MC 300 draws, each weak price x U(0.5,1.5) independently")
print(mc.describe(percentiles=[.025,.975]).loc[["min","2.5%","50%","97.5%","max"]].round(3).to_string())
print("share of draws London only city below 1:", ((mc.n_below1==1)&(mc.london<1)).mean())

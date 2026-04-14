import pandas as pd
import numpy as np
import json
import datetime as dt
import operator
import time
import streamlit as st
from binance.enums import *
from binance import ThreadedWebsocketManager
from pricechange import *
from binanceHelper import *
from pricegroup import *
import threading
import sys
from typing import Dict, List

# --- CONFIGURATION ---
show_only_pair = "USDT" 
show_limit = 5      # Increased for better visibility on dashboard
min_perc = 0.05      
price_changes: List[PriceChange] = []
price_groups: Dict[str, PriceGroup] = {}

# We use a global variable for the manager so we can stop it if needed
twm = None

def get_price_groups() -> List[PriceGroup]:
    return list(price_groups.values())

def process_message(tickers):
    global price_changes, price_groups
    for ticker in tickers:
        symbol = ticker['s']
        if not show_only_pair in symbol:
            continue

        price = float(ticker['c'])
        total_trades = int(ticker['n'])
        open_p = float(ticker['o'])
        volume = float(ticker['v'])
        event_time = dt.datetime.fromtimestamp(int(ticker['E'])/1000)
        
        # Logic to find or create price change objects
        found = False
        for pc in price_changes:
            if pc.symbol == symbol:
                pc.event_time = event_time
                pc.prev_price = pc.price
                pc.prev_volume = pc.volume
                pc.price = price
                pc.total_trades = total_trades
                pc.open_price = open_p
                pc.volume = volume
                pc.is_printed = False
                found = True
                break
        
        if not found:
            price_changes.append(PriceChange(symbol, price, price, total_trades, open_p, volume, False, event_time, volume))

    # Sorting logic
    price_changes.sort(key=operator.attrgetter('price_change_perc'), reverse=True)
    
    for price_change in price_changes:
        if (not price_change.is_printed 
            and abs(price_change.price_change_perc) > min_perc 
            and price_change.volume_change_perc > min_perc):

            price_change.is_printed = True 

            if not price_change.symbol in price_groups:
                price_groups[price_change.symbol] = PriceGroup(
                    price_change.symbol, 1, 
                    abs(price_change.price_change_perc),
                    price_change.price_change_perc,
                    price_change.volume_change_perc,                                                                
                    price_change.price,                                                                                                                                                                                                                                                              
                    price_change.event_time,
                    price_change.open_price,
                    price_change.volume,
                    False
                )
            else:
                pg = price_groups[price_change.symbol]
                pg.tick_count += 1
                pg.last_event_time = price_change.event_time
                pg.volume = price_change.volume
                pg.last_price = price_change.price
                pg.is_printed = False
                pg.total_price_change += abs(price_change.price_change_perc)
                pg.relative_price_change += price_change.price_change_perc
                pg.total_volume_change += price_change.volume_change_perc                

def main():
    global twm
    st.title("🚀 Binance Pump Detector")
    
    # 1. API KEY HANDLING
    if "BINANCE_API_KEY" in st.secrets:
        api_key = st.secrets["BINANCE_API_KEY"]
        api_secret = st.secrets["BINANCE_API_SECRET"]
    else:
        # Fallback for local testing
        try:
            with open('api_config.json') as json_data:
                api_config = json.load(json_data)
                api_key = api_config['api_key']
                api_secret = api_config['api_secret']
        except FileNotFoundError:
            st.error("API Keys not found in Secrets or api_config.json")
            return

    # 2. START WEBSOCKET (Using api3 cluster for Europe/Global bypass)
    if 'twm' not in st.session_state:
        twm = ThreadedWebsocketManager(
            api_key=api_key, 
            api_secret=api_secret, 
            base_url='https://api3.binance.com'
        )
        twm.start()
        twm.start_ticker_socket(process_message)
        st.session_state['twm'] = True
        st.success("Websocket Started Successfully")

    # 3. STREAMLIT UI LOOP
    st.subheader("Live Market Anomalies")
    table_placeholder = st.empty()
    
    # This loop keeps the app running and updates the UI table
    while True:
        groups = get_price_groups()
        if groups:
            # Sort by tick count to show the "hottest" coins first
            sorted_groups = sorted(groups, key=lambda x: x.tick_count, reverse=True)
            
            # Prepare data for a clean Streamlit table
            display_data = []
            for g in sorted_groups[:10]: # Top 10
                display_data.append({
                    "Symbol": g.symbol,
                    "Ticks": g.tick_count,
                    "Price Change %": round(g.relative_price_change, 2),
                    "Vol Change %": round(g.total_volume_change, 2),
                    "Last Price": g.last_price
                })
            
            table_placeholder.table(pd.DataFrame(display_data))
        
        time.sleep(2) # Refresh UI every 2 seconds

if __name__ == '__main__':
    main()

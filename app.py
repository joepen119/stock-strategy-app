from datetime import datetime
import json
import os
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

# 設定網頁標題與版面
st.set_page_config(
    page_title="海龜交易策略看盤系統", page_icon="📈", layout="wide"
)

# 清單儲存檔案路徑
WATCHLIST_FILE = "watchlist.json"
DEFAULT_TICKERS = ["2330.TW", "0050.TW", "00878.TW", "2317.TW", "2454.TW"]


# 讀取清單函式
def load_watchlist():
  if os.path.exists(WATCHLIST_FILE):
    try:
      with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, list) and len(data) > 0:
          return data
    except Exception:
      pass
  return DEFAULT_TICKERS.copy()


# 儲存清單函式
def save_watchlist(tickers_list):
  try:
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
      json.dump(tickers_list, f, ensure_ascii=False, indent=2)
  except Exception:
    pass


# 初始化 Session State
if "watchlist" not in st.session_state:
  st.session_state.watchlist = load_watchlist()


# 發送 Telegram 訊息的函式
def send_telegram_alert(message):
  try:
    token = st.secrets["TELEGRAM_BOT_TOKEN"]
    chat_id = st.secrets["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    response = requests.post(url, json=payload)
    return response.status_code == 200
  except Exception as e:
    st.error(f"發送錯誤：{e}")
    return False


# 處理新增股票代號的回呼函式
def add_ticker_callback():
  raw_input = st.session_state.new_ticker_input.strip().upper()
  if raw_input:
    # 若純數字（台股代號），自動補上 .TW
    if raw_input.isdigit():
      formatted_ticker = f"{raw_input}.TW"
    else:
      formatted_ticker = raw_input

    if formatted_ticker not in st.session_state.watchlist:
      st.session_state.watchlist.append(formatted_ticker)
      save_watchlist(st.session_state.watchlist)
      st.toast(f"✅ 已將 {formatted_ticker} 加入監控清單！")
    else:
      st.toast(f"⚠️ {formatted_ticker} 已經在清單內囉！")

    # 清空輸入框
    st.session_state.new_ticker_input = ""


# 側邊欄設定
with st.sidebar:
  st.header("⚙️ 監控清單與參數設定")

  # 直接輸入代號並自動加入清單
  st.text_input(
      "輸入股票代號 (按 Enter 自動加入)",
      key="new_ticker_input",
      placeholder="例如：2603 或 00919 或 NVDA",
      on_change=add_ticker_callback,
  )
  st.button("➕ 加入清單", on_click=add_ticker_callback, use_container_width=True)

  st.caption(
      "💡 提示：台股上市股票直接輸入數字（如 `2330`）會自動補上"
      " `.TW`；上櫃請輸入完整代號（如 `6488.TWO`）。"
  )

  # 管理目前清單（可點選 X 移除不要的股票）
  updated_list = st.multiselect(
      "目前監控清單 (點擊 × 可移除)",
      options=st.session_state.watchlist,
      default=st.session_state.watchlist,
  )

  # 若使用者透過 multiselect 移除了項目，同步更新狀態與檔案
  if updated_list != st.session_state.watchlist:
    st.session_state.watchlist = updated_list
    save_watchlist(st.session_state.watchlist)
    st.rerun()

  st.divider()

  buy_window = st.number_input(
      "突破買進天數 (日)", min_value=5, max_value=60, value=10
  )
  sell_window = st.number_input(
      "跌破賣出天數 (日)", min_value=10, max_value=120, value=60
  )

  st.caption(
      "💡 策略邏輯：收盤價突破前 10 日最高收盤價觸發買進；跌破前 60"
      " 日最低收盤價觸發賣出。"
  )

# 主畫面標題
st.title("📈 海龜突破策略看盤系統")
st.markdown(f"更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

tickers = st.session_state.watchlist

if not tickers:
  st.warning("目前監控清單是空的，請在左側輸入股票代號新增。")
  st.stop()

# 抓取資料並計算訊號
summary_list = []
stock_data_dict = {}

with st.spinner("正在從 Yahoo Finance 獲取最新股價資料..."):
  for ticker in tickers:
    try:
      # 抓取足夠計算 60 日均線與高低點的歷史資料 (抓 6 個月)
      df = yf.download(ticker, period="6mo", interval="1d", progress=False)

      if df.empty or len(df) < sell_window + 1:
        st.warning(
            f"⚠️ 無法取得 {ticker}"
            " 的完整歷史資料，請確認代號是否正確（上櫃股票請加 .TWO）。"
        )
        continue

      # 處理 yfinance 可能回傳的多層欄位 (MultiIndex)
      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      # 計算前 N 日最高收盤價與前 M 日最低收盤價 (使用 shift(1) 避免未來函數，代表「前」N日)
      df["Buy_Line"] = df["Close"].rolling(window=buy_window).max().shift(1)
      df["Sell_Line"] = df["Close"].rolling(window=sell_window).min().shift(1)

      latest = df.iloc[-1]
      current_price = float(latest["Close"])
      buy_target = float(latest["Buy_Line"])
      sell_target = float(latest["Sell_Line"])

      # 計算距離買進價與賣出價的百分比
      dist_to_buy = ((buy_target - current_price) / current_price) * 100
      dist_to_sell = ((current_price - sell_target) / current_price) * 100

      # 判斷買賣訊號狀態
      if current_price > buy_target:
        status = "🔥 突破買進訊號"
      elif current_price < sell_target:
        status = "❄️ 跌破賣出訊號"
      else:
        status = "👀 盤整觀望中"

      summary_list.append({
          "代號": ticker,
          "現價": round(current_price, 2),
          "狀態": status,
          f"前{buy_window}日高(買點)": round(buy_target, 2),
          "距買進": f"{dist_to_buy:+.2f}%",
          f"前{sell_window}日低(賣點)": round(sell_target, 2),
          "距賣出": f"{dist_to_sell:+.2f}%",
      })

      stock_data_dict[ticker] = df

    except Exception as e:
      st.error(f"讀取 {ticker} 時發生錯誤：{e}")

# 顯示總覽表格
if summary_list:
  st.subheader("📊 監控清單策略總覽")
  summary_df = pd.DataFrame(summary_list)
  st.dataframe(summary_df, use_container_width=True, hide_index=True)

  # 在側邊欄加入 Telegram 推播按鈕
  with st.sidebar:
    st.divider()
    st.header("🔔 推播通知設定")
    if st.button("📤 發送今日買賣訊號到 Telegram", use_container_width=True):
      alert_msg = (
          f"<b>📈 海龜策略看盤訊號通知</b>\n時間："
          f" {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
      )
      for item in summary_list:
        alert_msg += (
            f"<b>{item['代號']}</b> | 現價: <b>{item['現價']}</b>\n"
            f"狀態: {item['狀態']}\n"
            f"買點({item[f'前{buy_window}日高(買點)']}): 距 {item['距買進']}\n"
            f"賣點({item[f'前{sell_window}日低(賣點)']}): 距 {item['距賣出']}\n"
            "-------------------\n"
        )

      with st.spinner("正在發送 Telegram 推播..."):
        success = send_telegram_alert(alert_msg)
        if success:
          st.success("✅ Telegram 推播發送成功！請查看手機。")
        else:
          st.error("❌ 發送失敗，請確認 Streamlit Secrets 設定是否正確。")

  st.divider()

  # 個股 K 線與通道圖表分析
  st.subheader("📉 個股技術走勢與買賣通道圖")
  selected_ticker = st.selectbox(
      "選擇要檢視圖表的股票：", list(stock_data_dict.keys())
  )

  if selected_ticker:
    plot_df = stock_data_dict[selected_ticker].tail(
        90
    )  # 顯示最近 90 個交易日走勢

    fig = go.Figure()

    # K線圖
    fig.add_trace(
        go.Candlestick(
            x=plot_df.index,
            open=plot_df["Open"],
            high=plot_df["High"],
            low=plot_df["Low"],
            close=plot_df["Close"],
            name="K線",
        )
    )

    # 10日突破買進線
    fig.add_trace(
        go.Scatter(
            x=plot_df.index,
            y=plot_df["Buy_Line"],
            mode="lines",
            name=f"前{buy_window}日最高收盤 (買進線)",
            line=dict(color="red", width=1.5, dash="dash"),
        )
    )

    # 60日跌破賣出線
    fig.add_trace(
        go.Scatter(
            x=plot_df.index,
            y=plot_df["Sell_Line"],
            mode="lines",
            name=f"前{sell_window}日最低收盤 (賣出線)",
            line=dict(color="green", width=1.5, dash="dash"),
        )
    )

    fig.update_layout(
        title=f"{selected_ticker} 近 90 日價格與海龜通道走勢",
        xaxis_title="日期",
        yaxis_title="價格",
        xaxis_rangeslider_visible=False,
        height=500,
        template="plotly_white",
    )

    st.plotly_chart(fig, use_container_width=True)
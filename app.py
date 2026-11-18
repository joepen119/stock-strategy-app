from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# 設定網頁標題與手機版面寬度
st.set_page_config(
    page_title="10日突破 / 60日跌破 策略看盤", page_icon="📈", layout="centered"
)

# 自訂 CSS 讓手機卡片更美觀
st.markdown(
    """
<style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        border-left: 6px solid #6c757d;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .buy-signal { border-left-color: #28a745; background-color: #eafaf1; }
    .sell-signal { border-left-color: #dc3545; background-color: #fdedec; }
    .stock-title { font-size: 20px; font-weight: bold; margin-bottom: 4px; color: #212529; }
    .price-text { font-size: 24px; font-weight: 800; color: #000000; }
    .sub-text { font-size: 14px; color: #495057; margin-top: 6px; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("📈 10日突破 / 60日跌破 儀表板")
st.caption(f"最後更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}")

# 側邊欄：自訂監控股票清單
with st.sidebar:
  st.header("⚙️ 監控清單設定")
  default_tickers = "0050.TW, 006208.TW, 2330.TW, 00878.TW"
  tickers_input = st.text_area(
      "輸入股票代號（用逗號分隔，上市加 .TW，上櫃加 .TWO）",
      value=default_tickers,
      height=100,
  )
  if st.button("🔄 重新整理報價", use_container_width=True):
    st.cache_data.clear()

tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]


@st.cache_data(ttl=300)  # 快取 5 分鐘避免頻繁抓取被擋
def get_stock_data(ticker: str):
  df = yf.download(ticker, period="4mo", interval="1d", progress=False)
  if df.empty or len(df) < 61:
    return None
  if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)
  return df


# 儲存彙整資料供下方總表使用
summary_list = []

for ticker in tickers:
  df = get_stock_data(ticker)
  if df is None:
    st.warning(f"⚠️ **{ticker}**：資料不足 60 個交易日或代號錯誤，無法計算。")
    continue

  # 計算指標（不含今日）
  df["max_10"] = df["Close"].shift(1).rolling(window=10).max()
  df["min_60"] = df["Close"].shift(1).rolling(window=60).min()

  today_close = float(df["Close"].iloc[-1])
  max_10 = float(df["max_10"].iloc[-1])
  min_60 = float(df["min_60"].iloc[-1])

  # 計算距離買進點與賣出點的百分比
  dist_to_buy_pct = ((max_10 - today_close) / today_close) * 100
  dist_to_sell_pct = ((today_close - min_60) / today_close) * 100

  # 判斷狀態
  if today_close > max_10:
    status = "🟢 突破買進 (BUY)"
    card_class = "metric-card buy-signal"
    buy_desc = (
        f"已突破前10日高點 ({max_10:.2f}) <b>+{abs(dist_to_buy_pct):.2f}%</b>"
    )
  else:
    status = "⚪ 區間觀察中"
    card_class = "metric-card"
    buy_desc = f"距離 10日買進價 (<b>{max_10:.2f}</b>) 還差 <b>+{dist_to_buy_pct:.2f}%</b>"

  if today_close < min_60:
    status = "🔴 跌破賣出 (SELL)"
    card_class = "metric-card sell-signal"
    sell_desc = (
        f"已跌破前60日低點 ({min_60:.2f}) <b>-{abs(dist_to_sell_pct):.2f}%</b>"
    )
  else:
    sell_desc = f"距離 60日賣出價 (<b>{min_60:.2f}</b>) 還有 <b>-{dist_to_sell_pct:.2f}%</b> 緩衝"

  summary_list.append({
      "代號": ticker,
      "現價": round(today_close, 2),
      "10日高(買進線)": round(max_10, 2),
      "距買進": (
          f"+{dist_to_buy_pct:.2f}%" if today_close <= max_10 else "已突破"
      ),
      "60日低(賣出線)": round(min_60, 2),
      "距賣出": (
          f"-{dist_to_sell_pct:.2f}%" if today_close >= min_60 else "已跌破"
      ),
      "狀態": status,
  })

  # 渲染手機專屬資訊卡片
  st.markdown(
      f"""
    <div class="{card_class}">
        <div class="stock-title">{ticker} &nbsp; <span style="font-size:15px;">{status}</span></div>
        <div class="price-text">{today_close:.2f}</div>
        <div class="sub-text">📈 {buy_desc}</div>
        <div class="sub-text">📉 {sell_desc}</div>
    </div>
    """,
      unsafe_allow_html=True,
  )

  # 可展開查看互動式 K 線與通道圖解
  with st.expander(f"📊 查看 {ticker} 走勢與 10日/60日 通道圖"):
    plot_df = df.tail(65)  # 顯示最近 65 個交易日
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=plot_df.index,
            open=plot_df["Open"],
            high=plot_df["High"],
            low=plot_df["Low"],
            close=plot_df["Close"],
            name="日K線",
            increasing_line_color="red",  # 台股紅漲
            decreasing_line_color="green",  # 台股綠跌
        )
    )
    fig.add_trace(
        go.Scatter(
            x=plot_df.index,
            y=plot_df["max_10"],
            mode="lines",
            name="前10日最高收盤(買進線)",
            line=dict(color="orange", width=2, dash="dash"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=plot_df.index,
            y=plot_df["min_60"],
            mode="lines",
            name="前60日最低收盤(賣出線)",
            line=dict(color="blue", width=2, dash="dash"),
        )
    )
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=350,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
    )
    st.plotly_chart(fig, use_container_width=True)

# 底部顯示玉山智慧單快速抄寫總表
if summary_list:
  st.divider()
  st.subheader("📋 玉山證券「智慧下單」關鍵價位速查表")
  st.caption("可直接參考下表價格，至玉山證券 App 設定觸價通知或智慧單：")
  st.dataframe(
      pd.DataFrame(summary_list), use_container_width=True, hide_index=True
  )
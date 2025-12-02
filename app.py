import streamlit as st
import pandas as pd
import mysql.connector

from dotenv import load_dotenv
import os

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# --- 資料庫設定 (請填寫您的資料庫連線資訊) ---
# 注意：為了安全起見，建議不要將敏感資訊直接寫在程式碼中，
# 而是使用環境變數或 Streamlit Secrets (st.secrets) 來管理。
# 這裡提供範例填寫方式：
DB_CONFIG = {
    "host": DB_HOST,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "database": DB_USER
}


# --- 數據載入與資料庫連線功能 ---

# @st.cache_data decorator：用於緩存資料，當參數不變時，不會重複執行資料庫查詢，
# 提升應用程式效能。
@st.cache_data
def load_data(device_id):
    """
    從 MySQL 資料庫中載入特定 device_id 的數據。
    """
    try:
        # 建立資料庫連線
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # 執行 SQL 查詢 (Requirement 1)
        # 查詢 device_id = selected_id 的所有資料
        # 注意：使用參數化查詢來防止 SQL 注入。
        query = """
        SELECT DataTime, name, x_value, y_value
        FROM tis
        WHERE device_id = %s
        ORDER BY DataTime DESC;
        """
        cursor.execute(query, (device_id,))

        # 獲取所有結果並將其轉換為 Pandas DataFrame
        data = cursor.fetchall()
        column_names = [desc[0] for desc in cursor.description]
        df = pd.DataFrame(data, columns=column_names)

        # 關閉連線
        cursor.close()
        conn.close()

        # 將 DataTime 欄位轉換為 datetime 物件，方便繪圖處理
        df['DataTime'] = pd.to_datetime(df['DataTime'])

        return df

    except mysql.connector.Error as err:
        st.error(f"資料庫連線錯誤: {err}")
        return pd.DataFrame()  # 返回空 DataFrame 以防止應用程式崩潰


@st.cache_data
def get_device_ids():
    """
    從資料庫中獲取所有不重複的 device_id 列表，用於下拉式選單。
    """
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = "SELECT DISTINCT device_id FROM tis ORDER BY device_id ASC;"
        cursor.execute(query)
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        return ids
    except mysql.connector.Error as err:
        st.error(f"無法獲取設備列表: {err}")
        return [1]  # 預設值，以防連線失敗


# --- Streamlit UI 介面 ---

def main():
    # --- 介面設定與標題 ---
    st.set_page_config(
        page_title="安全監測數據分析儀表板",
        layout="wide",  # 設定為 wide 佈局以更好地利用螢幕空間，適配手機時也會自動調整。
        initial_sidebar_state="expanded"  # 預設展開側邊欄
    )

    st.title("安全監測數據分析儀表板")
    st.markdown("---")

    # --- 側邊欄：控制項 (Requirement 1: 數據載入) ---
    st.sidebar.header("數據篩選")

    # 獲取所有 device_id 列表並建立下拉式選單
    device_ids = get_device_ids()

    # 設置預設選中值 (預設值是1)
    default_index = device_ids.index(1) if 1 in device_ids else 0
    selected_device_id = st.sidebar.selectbox(
        "選擇設備編號 (device_id):",
        options=device_ids,
        index=default_index
    )

    # 載入選定設備的數據
    data_df = load_data(selected_device_id)

    # --- 主介面：顯示數據與圖表 ---
    if data_df.empty:
        st.info(f"未找到 device_id = {selected_device_id} 的數據。")
    else:
        # 1. 顯示數據表格 (Requirement 2: 顯示數據)
        st.header(f"設備 {selected_device_id} 數據表格")
        st.dataframe(data_df)

        # 2. 繪製圖表 (Requirement 3: 圖表功能)
        st.header(f"設備 {selected_device_id} 趨勢圖")
        st.subheader("x_value 和 y_value 隨時間變化")

        # 使用 Streamlit 內建的 st.line_chart
        # x 軸為 DataTime，y 軸為 x_value 和 y_value
        st.line_chart(
            data_df,
            x="DataTime",
            y=["x_value", "y_value"]
        )

        st.info(f"總共載入了 {len(data_df)} 筆數據。")

    # --- 行動裝置適配性 (Requirement 4) ---
    # Streamlit 本身具有良好的響應式設計。
    # 設定 layout="wide" (在 st.set_page_config 中) 可以讓電腦螢幕有更寬的版面，
    # 在手機上會自動縮小以適應螢幕寬度，無需額外程式碼調整。


if __name__ == "__main__":
    main()
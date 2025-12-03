import streamlit as st
import pandas as pd
import mysql.connector
import plotly.express as px # 導入 plotly.express

from dotenv import load_dotenv
import os

load_dotenv()

DB_HOST = st.secrets["mysql"]["host"]
DB_USER = st.secrets["mysql"]["user"]
DB_PASSWORD = st.secrets["mysql"]["password"]
DB_NAME = st.secrets["mysql"]["database"]

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
        WHERE device_id = %s and datatime>'2025-08-06'
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
    從資料庫中獲取所有不重複的 device_id 列表。
    """
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = "SELECT DISTINCT id,uuid,sensor_id FROM devices ORDER BY device_id ASC;"
        cursor.execute(query)
        ids = [row[0] for row in cursor.fetchall()]
        uuids = [row[1] for row in cursor.fetchall()]
        sensor_ids = [row[2] for row in cursor.fetchall()]
        conn.close()
        return ids,uuids,sensor_ids
    except mysql.connector.Error as err:
        st.error(f"無法獲取設備列表: {err}")
        return [1]


# --- Streamlit UI 介面 ---
def main():
    st.set_page_config(
        page_title="安全監測數據分析儀表板",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.title("安全監測數據分析儀表板")
    st.markdown("---")

    # --- 側邊欄：控制項 ---
    st.sidebar.header("數據篩選")
    device_ids,device_uuids,sensor_ids = get_device_ids()
    default_index = device_ids.index(1) if 1 in device_ids else 0
    selected_device_id = st.sidebar.selectbox(
        "選擇設備編號 (device_id):",
        options=device_uuids,
        index=default_index
    )

    # 載入選定設備的數據
    data_df = load_data(device_ids[device_uuids.index(selected_device_id)])

    # --- 主介面：顯示數據與圖表 ---
    if data_df.empty:
        st.info(f"未找到 device_id = {selected_device_id} 的數據。")
    else:
        # 先複製一份，並把 name 改成 TI1 / TI2 這種 label
        plot_df = data_df.copy()
        plot_df["TI"] = plot_df["name"].str.upper()  # ti1 -> TI1, ti2 -> TI2

        #test

        # 轉成 long format：一列只放一個值
        # DataTime, TI, axis（X / Y）, value（數值）
        long_df = plot_df.melt(
            id_vars=["DataTime", "TI"],
            value_vars=["x_value", "y_value"],
            var_name="axis",  # 這裡會是 'x_value' / 'y_value'
            value_name="value"  # 真正要畫的數值
        )

        # 把 axis 改成比較好看的標籤：X / Y
        long_df["axis"] = long_df["axis"].map({
            "x_value": "X",
            "y_value": "Y",
        })

        # 建一個「曲線名稱」欄位：TI1_X、TI1_Y、TI2_X、TI2_Y
        long_df["series"] = long_df["TI"] + "_" + long_df["axis"]

        # 用 Plotly 畫圖
        fig = px.line(
            long_df,
            x="DataTime",
            y="value",
            color="series",  # 4 條線，不同顏色
            symbol="series",  # 4 種不同點形狀
            markers=True,  # 顯示點
            title="數據讀數隨時間變化趨勢",
            labels={
                "DataTime": "時間",
                "value": "讀數",
                "series": "設備 / 軸向"
            },
            # 可選：指定每條線的點形狀（你有提到正方形、三角形、圓形、菱形）
            symbol_map={
                "TI1_X": "circle",  # 圓形
                "TI1_Y": "square",  # 正方形
                "TI2_X": "diamond",  # 菱形
                "TI2_Y": "triangle-up",  # 三角形
            },
        )

        fig.update_layout(
            hovermode="x unified",
            xaxis_title="時間 (DataTime)",
            yaxis_title="讀數",
            legend_title="設備 / 軸向",
        )

        st.plotly_chart(fig, use_container_width=True)

        st.info(f"總共載入了 {len(data_df)} 筆數據。")

if __name__ == "__main__":
    main()
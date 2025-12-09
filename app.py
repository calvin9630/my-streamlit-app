import streamlit as st
import pandas as pd
import mysql.connector
import plotly.express as px # 導入 plotly.express

from dotenv import load_dotenv
import os
import streamlit as st
import random

marker_shapes = [
    "circle", "square", "diamond",
    "triangle-up", "triangle-down",
    "cross", "x", "star",
    "hexagon", "pentagon", "hourglass"
]

# --- 隱藏 Streamlit 預設物件的 CSS ---
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stApp > header {display: none;} /* 強制隱藏上方工具列 */
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)


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
@st.cache_data(ttl=60)
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
        WHERE device_id = %s and datatime>'2025-08-07'
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
        query = "SELECT DISTINCT id,uuid,sensor_id FROM devices ORDER BY id ASC;"
        cursor.execute(query)

        rows = cursor.fetchall()

        ids = [row[0] for row in rows]
        uuids = [row[1] for row in rows]
        sensor_ids = [row[2] for row in rows]
        conn.close()
        return ids,uuids,sensor_ids
    except mysql.connector.Error as err:
        st.error(f"無法獲取設備列表: {err}")
        return [], [], []


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
        # 1. 顯示數據表格 (保持不變)
        st.header(f"設備 {selected_device_id} 數據表格")
        st.dataframe(data_df)
        sensor_num=sensor_ids[device_uuids.index(selected_device_id)].split(',')

        # 2. 繪製圖表 (重點更新：使用 Plotly)
        st.header(f"設備 {selected_device_id} 趨勢圖")
        Ti_name=''
        for num in sensor_num:
            Ti_name+=f"TI{num}及"
        Ti_name=Ti_name[:len(Ti_name)-1]
        st.subheader(f"{Ti_name}的x_value 和 y_value資料 隨時間變化")

        # 先複製一份，並把 name 改成 TI1 / TI2 這種 label
        plot_df = data_df.copy()
        plot_df["TI"] = plot_df["name"].str.upper()  # ti1 -> TI1, ti2 -> TI2

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

        axes = ["X", "Y"]

        symbol_map = {}

        for sensor in sensor_num:
            for axis in axes:
                # key 例如：TI1_X
                key = f"TI{sensor}_{axis}"

                # 隨機挑一個 marker 形狀
                shape = random.choice(marker_shapes)

                # 填入 symbol_map
                symbol_map[key] = shape

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
                "value": "讀數(度)",
                "series": "設備 / 軸向"
            },
            # 隨機生每條線的點形狀
            symbol_map=symbol_map,
        )

        fig.update_layout(
            hovermode="x unified",
            xaxis_title="時間 (DataTime)",
            yaxis_title="讀數(度)",
            legend_title="設備 / 軸向",
        )
        # 將英文月份改成純數字格式
        fig.update_xaxes(tickformat="%Y-%m-%d")

        st.plotly_chart(fig, use_container_width=True)

        st.info(f"總共載入了 {len(data_df)} 筆數據。")

if __name__ == "__main__":
    main()
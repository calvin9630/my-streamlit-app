import streamlit as st
import pandas as pd
import mysql.connector
import plotly.express as px
from dotenv import load_dotenv
import os
import itertools

# --- 設定頁面配置 (必須放在第一行) ---
st.set_page_config(
    page_title="安全監測數據分析儀表板",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 載入環境變數 ---
# 優先嘗試載入 .env 檔案 (本地開發用)
load_dotenv()

# --- 隱藏 Streamlit 預設物件的 CSS ---
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stApp > header {display: none;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)


# --- 資料庫連線設定 ---
def get_db_config():
    """
    獲取資料庫配置，優先使用 st.secrets，如果沒有則使用 os.getenv (.env)
    """
    config = {}
    try:
        # 嘗試從 Streamlit Secrets 讀取 (建議用於 Cloud 或有設定 secrets.toml)
        if "mysql" in st.secrets:
            config = {
                "host": st.secrets["mysql"]["host"],
                "user": st.secrets["mysql"]["user"],
                "password": st.secrets["mysql"]["password"],
                "database": st.secrets["mysql"]["database"],
                # 加入 connect_timeout 避免網路不穩時卡死
                "connect_timeout": 10
            }
        else:
            # 備用：從環境變數讀取
            config = {
                "host": os.getenv("DB_HOST"),
                "user": os.getenv("DB_USER"),
                "password": os.getenv("DB_PASSWORD"),
                "database": os.getenv("DB_NAME"),
                "connect_timeout": 10
            }
    except Exception as e:
        st.error(f"設定讀取錯誤: {e}")
    return config


# --- 輔助函式：符號生成器 ---
def get_marker_generator():
    """
    產生一個無限循環的符號迭代器，確保圖表符號一致性
    """
    marker_shapes = [
        "circle", "square", "diamond", "triangle-up", "triangle-down",
        "cross", "x", "star", "hexagon", "pentagon", "hourglass"
    ]
    return itertools.cycle(marker_shapes)


# --- 數據載入與資料庫連線功能 ---

@st.cache_data(ttl=60)
def load_data(device_id, start_date):
    """
    從 MySQL 資料庫中載入特定 device_id 的 TIS 數據。
    """
    db_config = get_db_config()
    if not db_config.get("host"):
        st.error("找不到資料庫設定，請檢查 .streamlit/secrets.toml 或 .env 檔案")
        return pd.DataFrame()

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        query = """
        SELECT DataTime, name, x_value, y_value
        FROM tis
        WHERE device_id = %s AND DataTime >= %s
        ORDER BY DataTime DESC;
        """
        date_str = start_date.strftime('%Y-%m-%d')
        cursor.execute(query, (device_id, date_str))

        data = cursor.fetchall()
        column_names = [desc[0] for desc in cursor.description]
        df = pd.DataFrame(data, columns=column_names)

        cursor.close()
        conn.close()

        if not df.empty:
            df['DataTime'] = pd.to_datetime(df['DataTime'])

        return df

    except mysql.connector.Error as err:
        st.error(f"TIS 資料載入錯誤: {err}")
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_vgs_data(device_id, start_date):
    """
    從 MySQL 資料庫中載入特定 device_id 的 VGS 數據。
    """
    db_config = get_db_config()
    if not db_config.get("host"):
        return pd.DataFrame()

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # 根據 VGS 資料表結構查詢
        query = """
        SELECT DataTime, name, value1, value2
        FROM vgs
        WHERE device_id = %s AND DataTime >= %s
        ORDER BY DataTime DESC;
        """
        date_str = start_date.strftime('%Y-%m-%d')
        cursor.execute(query, (device_id, date_str))

        data = cursor.fetchall()
        column_names = [desc[0] for desc in cursor.description]
        df = pd.DataFrame(data, columns=column_names)

        cursor.close()
        conn.close()

        if not df.empty:
            df['DataTime'] = pd.to_datetime(df['DataTime'])

        return df

    except mysql.connector.Error as err:
        # 不顯示錯誤，避免干擾主畫面，僅在 log 紀錄或回傳空值
        # st.error(f"VGS 資料載入錯誤: {err}")
        return pd.DataFrame()


@st.cache_data
def get_device_ids():
    """
    從資料庫中獲取所有不重複的 device_id 列表。
    """
    db_config = get_db_config()
    if not db_config.get("host"):
        return [], [], []

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        query = "SELECT DISTINCT id, uuid, sensor_id FROM devices ORDER BY id ASC;"
        cursor.execute(query)

        rows = cursor.fetchall()

        ids = [row[0] for row in rows]
        uuids = [row[1] for row in rows]
        sensor_ids = [row[2] for row in rows]
        conn.close()
        return ids, uuids, sensor_ids
    except mysql.connector.Error as err:
        st.error(f"無法獲取設備列表: {err}")
        return [], [], []


# --- 主程式 ---
def main():
    st.title("🏗️ 安全監測數據分析儀表板")
    st.markdown("---")

    # --- 側邊欄：控制項 ---
    st.sidebar.header("🛠️ 監測設定")

    # 1. 取得設備列表
    device_ids, device_uuids, sensor_ids = get_device_ids()

    if not device_ids:
        st.warning("無法讀取設備列表，請檢查資料庫連線。")
        return

    # 2. 設備選擇
    default_index = 0
    if 1 in device_ids:
        default_index = device_ids.index(1)

    selected_device_uuid = st.sidebar.selectbox(
        "選擇設備編號 (UUID):",
        options=device_uuids,
        index=default_index
    )

    current_index = device_uuids.index(selected_device_uuid)
    selected_device_id = device_ids[current_index]
    selected_sensor_str = sensor_ids[current_index]

    # 3. 日期篩選
    st.sidebar.subheader("時間區間篩選")
    import datetime
    default_start_date = datetime.date(2025, 8, 7)
    start_date = st.sidebar.date_input(
        "起始日期 (DataTime >=)",
        value=default_start_date
    )

    # --- 載入數據 (平行載入 TIS 和 VGS) ---
    with st.spinner('數據載入中...'):
        tis_df = load_data(selected_device_id, start_date)
        vgs_df = load_vgs_data(selected_device_id, start_date)

    # --- TIS 圖表區塊 ---
    if tis_df.empty:
        st.info(f"設備 {selected_device_uuid} 在 {start_date} 之後無 TIS (傾斜儀) 數據。")
    else:
        sensor_list = str(selected_sensor_str).split(',') if selected_sensor_str else []
        ti_title = "、".join([f"TI{num}" for num in sensor_list])

        plot_df = tis_df.copy()
        plot_df["TI"] = plot_df["name"].str.upper()

        long_df = plot_df.melt(
            id_vars=["DataTime", "TI"],
            value_vars=["x_value", "y_value"],
            var_name="axis",
            value_name="value"
        )
        long_df["axis"] = long_df["axis"].map({"x_value": "X", "y_value": "Y"})
        long_df["series"] = long_df["TI"] + "_" + long_df["axis"]

        symbol_map = {}
        unique_series = sorted(long_df["series"].unique())
        marker_gen = get_marker_generator()
        for series_name in unique_series:
            symbol_map[series_name] = next(marker_gen)

        st.header(f"📈 TIS 傾斜儀趨勢圖")
        st.caption(f"監測儀器: {ti_title} | 設備: {selected_device_uuid}")

        fig = px.line(
            long_df,
            x="DataTime",
            y="value",
            color="series",
            symbol="series",
            markers=True,
            title=f"傾斜儀讀數變化",
            labels={"DataTime": "監測時間", "value": "讀數", "series": "測點軸向"},
            symbol_map=symbol_map,
        )
        fig.update_layout(hovermode="x unified", height=450, template="plotly_white")
        fig.update_xaxes(tickformat="%Y-%m-%d %H:%M")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("查看 TIS 詳細數據表格"):
            st.dataframe(tis_df, use_container_width=True)

    # --- 分隔線 ---
    st.markdown("---")

    # --- VGS 圖表區塊 (新增) ---
    st.header(f"📊 VGS 監測數據")

    if vgs_df.empty:
        st.info(f"設備 {selected_device_uuid} 在 {start_date} 之後無 VGS 數據。")
    else:
        # VGS 數據處理
        vgs_plot = vgs_df.copy()
        vgs_plot["Name"] = vgs_plot["name"].str.upper()

        # 轉成長格式
        vgs_long = vgs_plot.melt(
            id_vars=["DataTime", "Name"],
            value_vars=["value1", "value2"],
            var_name="Channel",
            value_name="Reading"
        )

        # 定義顯示名稱 (例如: VG01_value1)
        vgs_long["Series"] = vgs_long["Name"] + "_" + vgs_long["Channel"]

        # VGS 符號邏輯
        vgs_symbol_map = {}
        vgs_unique_series = sorted(vgs_long["Series"].unique())
        vgs_marker_gen = get_marker_generator()
        for s_name in vgs_unique_series:
            vgs_symbol_map[s_name] = next(vgs_marker_gen)

        st.caption(f"設備: {selected_device_uuid} | 包含 value1 與 value2 讀數")

        fig_vgs = px.line(
            vgs_long,
            x="DataTime",
            y="Reading",
            color="Series",
            symbol="Series",
            markers=True,
            title=f"VGS 讀數變化趨勢",
            labels={"DataTime": "監測時間", "Reading": "監測讀數", "Series": "測點通道"},
            symbol_map=vgs_symbol_map
        )

        fig_vgs.update_layout(
            hovermode="x unified",
            height=450,
            template="plotly_white",
            yaxis_title="讀數 (Value)"
        )
        fig_vgs.update_xaxes(tickformat="%Y-%m-%d %H:%M")

        st.plotly_chart(fig_vgs, use_container_width=True)

        with st.expander("查看 VGS 詳細數據表格"):
            st.dataframe(vgs_df, use_container_width=True)
            st.info(f"總筆數: {len(vgs_df)}")


if __name__ == "__main__":
    main()
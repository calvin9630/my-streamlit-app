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
    initial_sidebar_state="collapsed"  # 預設收起側邊欄，因為我們把功能移出來了
)

# --- 載入環境變數 ---
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
        if "mysql" in st.secrets:
            config = {
                "host": st.secrets["mysql"]["host"],
                "user": st.secrets["mysql"]["user"],
                "password": st.secrets["mysql"]["password"],
                "database": st.secrets["mysql"]["database"],
                "connect_timeout": 10
            }
        else:
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
def load_data(device_id):
    """
    從 MySQL 資料庫中載入特定 device_id 的 TIS 數據。
    已移除時間篩選，讀取所有資料。
    """
    db_config = get_db_config()
    if not db_config.get("host"):
        st.error("找不到資料庫設定，請檢查 .streamlit/secrets.toml 或 .env 檔案")
        return pd.DataFrame()

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # 移除時間條件，讀取該設備所有資料
        query = """
        SELECT DataTime, name, x_value, y_value
        FROM tis
        WHERE device_id = %s
        ORDER BY DataTime DESC;
        """
        cursor.execute(query, (device_id,))

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
def load_vgs_data(device_id):
    """
    從 MySQL 資料庫中載入特定 device_id 的 VGS 數據。
    已移除時間篩選，讀取所有資料。
    """
    db_config = get_db_config()
    if not db_config.get("host"):
        return pd.DataFrame()

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # 移除時間條件，讀取該設備所有資料
        query = """
        SELECT DataTime, name, value1, value2
        FROM vgs
        WHERE device_id = %s
        ORDER BY DataTime DESC;
        """
        cursor.execute(query, (device_id,))

        data = cursor.fetchall()
        column_names = [desc[0] for desc in cursor.description]
        df = pd.DataFrame(data, columns=column_names)

        cursor.close()
        conn.close()

        if not df.empty:
            df['DataTime'] = pd.to_datetime(df['DataTime'])

        return df

    except mysql.connector.Error as err:
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

    # --- 1. 取得設備列表 ---
    device_ids, device_uuids, sensor_ids = get_device_ids()

    if not device_ids:
        st.warning("無法讀取設備列表，請檢查資料庫連線。")
        return

    # --- 2. 設備選擇 (移至主畫面最上方) ---
    with st.container():
        default_index = 0
        if 1 in device_ids:
            default_index = device_ids.index(1)

        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown("### 🛠️ 設備選擇")
            selected_device_uuid = st.selectbox(
                "請選擇設備編號 (UUID):",
                options=device_uuids,
                index=default_index,
                label_visibility="collapsed"
            )

    st.markdown("---")

    # 取得對應的 ID 與 Sensor 設定
    current_index = device_uuids.index(selected_device_uuid)
    selected_device_id = device_ids[current_index]
    selected_sensor_str = sensor_ids[current_index]

    # --- 3. 載入數據 ---
    with st.spinner(f'正在讀取 {selected_device_uuid} 的所有歷史數據...'):
        tis_df = load_data(selected_device_id)
        vgs_df = load_vgs_data(selected_device_id)

    # ==========================
    #      TIS 傾斜儀區塊
    # ==========================
    if tis_df.empty:
        st.info(f"設備 {selected_device_uuid} 目前無 TIS (傾斜儀) 數據。")
    else:
        sensor_list = str(selected_sensor_str).split(',') if selected_sensor_str else []
        ti_title = "、".join([f"TI{num}" for num in sensor_list])

        st.header(f"📈 TIS 傾斜儀監測")
        st.caption(f"監測儀器: {ti_title} | 設備: {selected_device_uuid}")

        # 1. 先顯示詳細數據表格
        with st.expander("查看 TIS 詳細數據表格", expanded=True):
            st.dataframe(tis_df, use_container_width=True)

        # 2. 再顯示趨勢圖
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

        fig = px.line(
            long_df,
            x="DataTime",
            y="value",
            color="series",
            symbol="series",
            markers=True,
            title=f"TIS 傾斜儀讀數變化趨勢",
            labels={"DataTime": "監測時間", "value": "讀數", "series": "測點軸向"},
            symbol_map=symbol_map,
        )
        fig.update_layout(hovermode="x unified", height=450, template="plotly_white")
        fig.update_xaxes(tickformat="%Y-%m-%d %H:%M")
        st.plotly_chart(fig, use_container_width=True)

    # --- 分隔線 ---
    st.markdown("---")

    # ==========================
    #      VGS 監測區塊
    # ==========================
    st.header(f"📊 VGS 監測數據")
    st.caption(f"設備: {selected_device_uuid} | 包含 value1 與 value2 讀數")

    if vgs_df.empty:
        st.info(f"設備 {selected_device_uuid} 目前無 VGS 數據。")
    else:
        # 1. 先顯示詳細數據表格
        with st.expander("查看 VGS 詳細數據表格", expanded=True):
            st.dataframe(vgs_df, use_container_width=True)
            st.info(f"總筆數: {len(vgs_df)}")

        # 2. 再顯示趨勢圖
        vgs_plot = vgs_df.copy()
        vgs_plot["Name"] = vgs_plot["name"].str.upper()

        vgs_long = vgs_plot.melt(
            id_vars=["DataTime", "Name"],
            value_vars=["value1", "value2"],
            var_name="Channel",
            value_name="Reading"
        )

        vgs_long["Series"] = vgs_long["Name"] + "_" + vgs_long["Channel"]

        vgs_symbol_map = {}
        vgs_unique_series = sorted(vgs_long["Series"].unique())
        vgs_marker_gen = get_marker_generator()
        for s_name in vgs_unique_series:
            vgs_symbol_map[s_name] = next(vgs_marker_gen)

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


if __name__ == "__main__":
    main()
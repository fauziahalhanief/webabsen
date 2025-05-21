import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import base64
from streamlit_calendar import calendar
import os
import calendar as cal_mod  # Modul calendar Python
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go

# Konfigurasi halaman Streamlit
st.set_page_config(page_title="Dashboard Absensi", layout="wide")
col1, col2 = st.columns([1, 4])
with col1:
    st.image("https://cesgs.unair.ac.id/wp-content/uploads/2024/02/Logo-CESGS-UNAIR-400x121.png", use_container_width=True)
with col2:
    st.markdown('<h1 style="text-align:right; color: black;">Dashboard Absensi Karyawan</h1>', unsafe_allow_html=True)

# --- Fungsi Utilitas ---

def cek_ketepatan_waktu(waktu_masuk):
    try:
        waktu_batas = datetime.strptime("09:17", "%H:%M").time()
        if isinstance(waktu_masuk, str):
            waktu_masuk_obj = datetime.strptime(waktu_masuk.strip(), "%H:%M").time()
        elif isinstance(waktu_masuk, (datetime, pd.Timestamp)):
            waktu_masuk_obj = waktu_masuk.time()
        else:
            return "Invalid Time"
        return "Telat" if waktu_masuk_obj > waktu_batas else "Tepat Waktu"
    except Exception:
        return "Invalid Time"


def get_karyawan_mapping():
    conn = sqlite3.connect("absensi.db")
    try:
        df_karyawan = pd.read_sql_query("SELECT ID, Divisi FROM karyawan", conn)
    except Exception:
        st.error("Error membaca data karyawan dari database.")
        df_karyawan = pd.DataFrame(columns=["ID", "Divisi"])
    conn.close()
    return df_karyawan.set_index("ID")["Divisi"].to_dict()


def format_presensi_data(df):
    required_cols = ['ID', 'Nama', 'Jenis']
    for col in required_cols:
        if col not in df.columns:
            st.error(f"Kolom '{col}' tidak ditemukan dalam data!")
            return pd.DataFrame()

    df["Jenis"] = df["Jenis"].str.lower()
    day_cols = [col for col in df.columns if str(col).isdigit()]
    if not day_cols:
        st.error("Tidak ditemukan kolom tanggal (1-31) dalam data!")
        return pd.DataFrame()

    df_long = df.melt(
        id_vars=['ID', 'Nama', 'Jenis'],
        value_vars=day_cols,
        var_name='tanggal',
        value_name='waktu'
    )
    df_long = df_long.dropna(subset=['waktu'])

    df_pivot = df_long.pivot_table(
        index=['ID', 'Nama', 'tanggal'],
        columns='Jenis',
        values='waktu',
        aggfunc='first'
    ).reset_index()

    if 'datang' not in df_pivot.columns:
        df_pivot['datang'] = ""
    if 'pulang' not in df_pivot.columns:
        df_pivot['pulang'] = ""

    df_pivot['status'] = df_pivot['datang'].apply(lambda x: cek_ketepatan_waktu(x) if x != "" else "No Data")

    df_final = df_pivot[['ID', 'Nama', 'tanggal', 'status', 'datang', 'pulang']].copy()
    df_final.rename(columns={'ID': 'id'}, inplace=True)
    mapping = get_karyawan_mapping()
    df_final['divisi'] = df_final['id'].apply(lambda x: mapping.get(x, "No Data"))
    df_final = df_final[['id', 'Nama', 'divisi', 'tanggal', 'status', 'datang', 'pulang']]
    return df_final

# --- Login dan Role Management ---
users = {
    "admin": {"password": "admin123", "role": "Admin"},
    "karyawan1": {"password": "karyawan123", "role": "Karyawan"}
}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.menu = ""

if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>Login</h2>", unsafe_allow_html=True)
    login_container = st.container()
    with login_container:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            username = st.text_input("Username", key="username_input")
            password = st.text_input("Password", type="password", key="password_input")
            if st.button("Login", key="login_button"):
                if username in users and users[username]["password"] == password:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = users[username]["role"]
                    st.session_state.menu = "Dashboard" if st.session_state.role == "Admin" else "Pengajuan Izin Kerja"
                    st.success(f"Login berhasil sebagai {st.session_state.role}")
                    st.rerun()
                else:
                    st.error("Username atau password salah.")
    st.stop()

st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in ["logged_in", "username", "role", "menu"]:
        st.session_state[key] = False if key == "logged_in" else ""
    st.rerun()

role = st.session_state.role

# --- MENU SELEKSI BERDASARKAN ROLE ---
if role == "Admin":
    st.session_state.menu = st.sidebar.selectbox(
        "Pilih Menu",
        ["Dashboard", "Data Pengajuan Izin", "Data Absensi", "Kalender Absensi"],
        index=["Dashboard", "Data Pengajuan Izin", "Data Absensi", "Kalender Absensi"].index(st.session_state.menu or "Dashboard")
    )
elif role == "Karyawan":
    st.session_state.menu = st.sidebar.selectbox("Pilih Menu", ["Pengajuan Izin Kerja"], index=0, key="menu_karyawan")

menu = st.session_state.menu

# --- Inisialisasi Database ---
def init_db():
    conn = sqlite3.connect("absensi.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS izin (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nama TEXT,
                    divisi TEXT,
                    jenis_pengajuan TEXT,
                    tanggal_pengajuan TEXT,
                    tanggal_izin TEXT,
                    jumlah_hari INTEGER,
                    file_persetujuan BLOB,
                    status TEXT DEFAULT 'Pending'
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS absensi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nama TEXT,
                    divisi TEXT,
                    tanggal TEXT,
                    jam_masuk TEXT,
                    jam_keluar TEXT,
                    status TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS karyawan (
                    ID INTEGER PRIMARY KEY,
                    Nama TEXT,
                    Divisi TEXT
                )''')
    # Migrasi tabel izin
    c.execute('''
    CREATE TABLE IF NOT EXISTS izin_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT,
        divisi TEXT,
        jenis_pengajuan TEXT,
        tanggal_pengajuan TEXT,
        tanggal_izin TEXT,
        jumlah_hari INTEGER,
        file_persetujuan BLOB,
        status TEXT DEFAULT 'Pending'
    )
    ''')
    c.execute('''
    INSERT INTO izin_new (id, nama, divisi, jenis_pengajuan, tanggal_pengajuan, tanggal_izin, jumlah_hari, file_persetujuan, status)
    SELECT id, nama, divisi, jenis_pengajuan, tanggal_pengajuan, tanggal_izin, jumlah_hari, file_persetujuan, status FROM izin
    ''')
    c.execute("DROP TABLE izin")
    c.execute("ALTER TABLE izin_new RENAME TO izin")
    conn.commit()
    conn.close()

init_db()

# --- Fungsi Penyimpanan dan Pengambilan Data ---
def save_absensi_to_db(df):
    conn = sqlite3.connect("absensi.db")
    for _, row in df.iterrows():
        conn.execute(
            "INSERT INTO absensi (nama, divisi, tanggal, jam_masuk, jam_keluar, status) VALUES (?, ?, ?, ?, ?, ?)",
            (row['nama'], row['divisi'], row['tanggal'], row['jam_masuk'], row['jam_keluar'], row['status'])
        )
    conn.commit()
    conn.close()

def save_izin(nama, divisi, jenis_pengajuan, tanggal_pengajuan, tanggal_izin, jumlah_hari, file_persetujuan_bytes):
    conn = sqlite3.connect("absensi.db")
    c = conn.cursor()
    blob = file_persetujuan_bytes if file_persetujuan_bytes else None
    c.execute('''INSERT INTO izin (nama, divisi, jenis_pengajuan, tanggal_pengajuan, tanggal_izin, jumlah_hari, file_persetujuan, status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (nama, divisi, jenis_pengajuan, tanggal_pengajuan, tanggal_izin, jumlah_hari, blob, "Pending"))
    conn.commit()
    conn.close()

def load_izin():
    conn = sqlite3.connect("absensi.db")
    df = pd.read_sql_query("SELECT * FROM izin", conn)
    conn.close()
    return df

def load_absensi():
    conn = sqlite3.connect("absensi.db")
    df = pd.read_sql_query("SELECT * FROM absensi", conn)
    conn.close()
    return df

def get_download_link(file_bytes, filename):
    if file_bytes is None:
        return ""
    b64 = base64.b64encode(file_bytes).decode()
    return f'<a href="data:image/jpeg;base64,{b64}" download="{filename}" target="_blank">Lihat File</a>'

def update_izin_status(izin_id, new_status):
    conn = sqlite3.connect("absensi.db")
    c = conn.cursor()
    c.execute("UPDATE izin SET status = ? WHERE id = ?", (new_status, izin_id))
    conn.commit()
    conn.close()

def add_absensi_from_izin(izin_record):
    nama = izin_record['nama']
    divisi = izin_record['divisi']
    try:
        start = datetime.strptime(izin_record['tanggal_izin'], "%Y-%m-%d").date()
    except Exception:
        st.error("Format tanggal izin tidak valid.")
        return
    days = int(izin_record['jumlah_hari'])
    conn = sqlite3.connect("absensi.db")
    c = conn.cursor()
    for i in range(days):
        d = start + timedelta(days=i)
        c.execute("INSERT INTO absensi (nama, divisi, tanggal, jam_masuk, jam_keluar, status) VALUES (?, ?, ?, ?, ?, ?)",
                  (nama, divisi, d.strftime("%Y-%m-%d"), "", "", "Izin"))
    conn.commit()
    conn.close()

# --- Tampilan UI Streamlit ---
if "detail_type" not in st.session_state:
    st.session_state.detail_type = None

warna_biru = "#003C8D"
warna_kuning = "#FFD700"

# 1. Menu Karyawan: Pengajuan Izin Kerja
# 1. Menu Karyawan: Pengajuan Izin Kerja
if menu == "Pengajuan Izin Kerja" and role == "Karyawan":
    st.subheader("Form Pengajuan Izin Tidak Masuk")
    nama = st.text_input("Nama Karyawan")
    divisi = st.text_input("Divisi")
    jenis_pengajuan = st.selectbox("Jenis Pengajuan", ["Cuti", "Telat", "Sakit", "WFH"])
    tanggal_pengajuan = st.date_input("Tanggal Pengajuan", datetime.today())
    tanggal_izin = st.date_input("Tanggal Izin", datetime.today())
    jumlah_hari = st.number_input("Jumlah Hari", min_value=1, step=1)
    file_persetujuan = st.file_uploader("Upload File Persetujuan (JPG, PNG)", type=["jpg", "png"])

    if st.button("Ajukan Izin"):
        # Validasi input form
        if not nama.strip():
            st.error("Mohon isi Nama Karyawan.")
        elif not divisi.strip():
            st.error("Mohon isi Divisi.")
        elif not jenis_pengajuan:
            st.error("Mohon pilih Jenis Pengajuan.")
        elif tanggal_izin < tanggal_pengajuan:
            st.error("Tanggal Izin tidak boleh lebih awal dari Tanggal Pengajuan.")
        elif jumlah_hari < 1:
            st.error("Jumlah Hari harus minimal 1.")
        elif file_persetujuan is None:
            st.error("Mohon upload file persetujuan.")
        else:
            blob = file_persetujuan.getvalue() if file_persetujuan else None
            save_izin(nama, divisi, jenis_pengajuan, str(tanggal_pengajuan), str(tanggal_izin), jumlah_hari, blob)
            st.success("Pengajuan izin berhasil disimpan!")

# 2. Menu Admin: Dashboard
elif menu == "Dashboard" and role == "Admin":
    st.subheader("Dashboard Pengajuan Izin")
    df_izin_all = load_izin()
    if not df_izin_all.empty:
        jenis_count = df_izin_all.groupby("jenis_pengajuan").size().reset_index(name='Jumlah')
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=jenis_count['jenis_pengajuan'],
            y=jenis_count['Jumlah'],
            marker=dict(color=[warna_biru if x!="WFH" else warna_kuning for x in jenis_count['jenis_pengajuan']]),
            text=jenis_count['Jumlah'], textposition='outside'
        ))
        fig.update_layout(
            title="Jumlah Pengajuan Izin per Jenis", xaxis_title="Jenis Pengajuan",
            yaxis_title="Jumlah Pengajuan", plot_bgcolor='rgba(0,0,0,0)', template="plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Belum ada data pengajuan izin.")
    st.write("### Tabel Pengajuan Izin (Pending)")
    conn = sqlite3.connect("absensi.db")
    df_pending = pd.read_sql_query("SELECT * FROM izin WHERE status = 'Pending'", conn)
    conn.close()
    if df_pending.empty:
        st.info("Tidak ada pengajuan izin yang pending.")
    else:
        headers = ["ID","Nama","Divisi","Jenis Pengajuan","Tanggal Pengajuan","Tanggal Izin","Jumlah Hari","File Persetujuan","Status","Persetujuan"]
        cols = st.columns(len(headers))
        for i,h in enumerate(headers): cols[i].write(f"**{h}**")
        for _,r in df_pending.iterrows():
            row_cols = st.columns(len(headers))
            row_cols[0].write(r['id']); row_cols[1].write(r['nama']); row_cols[2].write(r['divisi'])
            row_cols[3].write(r['jenis_pengajuan']); row_cols[4].write(r['tanggal_pengajuan'])
            row_cols[5].write(r['tanggal_izin']); row_cols[6].write(r['jumlah_hari'])
            link = get_download_link(r['file_persetujuan'], "file_persetujuan.jpg") if r['file_persetujuan'] else "Belum Disetujui"
            row_cols[7].markdown(link, unsafe_allow_html=True)
            row_cols[8].write(r['status'])
            if row_cols[9].button("Accept", key=f"ac_{r['id']}"):
                update_izin_status(r['id'], "Pengajuan izin telah diterima"); add_absensi_from_izin(r); st.success(f"ID {r['id']} diterima.")
            if row_cols[9].button("Reject", key=f"rj_{r['id']}"):
                update_izin_status(r['id'], "Pengajuan izin ditolak"); st.warning(f"ID {r['id']} ditolak.")

# 3. Menu Admin: Data Pengajuan Izin Diterima
elif menu == "Data Pengajuan Izin" and role == "Admin":
    st.subheader("Data Pengajuan Izin Karyawan")
    jenis_filter = st.selectbox("Pilih Jenis Pengajuan", ["Semua","Cuti","Telat","Sakit","WFH"])
    conn = sqlite3.connect("absensi.db")
    if jenis_filter == "Semua":
        df_izin = pd.read_sql_query("SELECT * FROM izin WHERE status='Pengajuan izin telah diterima'", conn)
    else:
        df_izin = pd.read_sql_query("SELECT * FROM izin WHERE status='Pengajuan izin telah diterima' AND jenis_pengajuan=?", conn, params=(jenis_filter,))
    conn.close()
    if df_izin.empty:
        st.info(f"Tidak ada data untuk jenis '{jenis_filter}'.")
    else:
        df_izin['file_persetujuan'] = df_izin['file_persetujuan'].apply(
            lambda x: f'<a href="data:image/jpeg;base64,{base64.b64encode(x).decode()}" download="fp_{x[:10]}.jpg">Lihat</a>' if x else ""
        )
        st.markdown(df_izin.to_html(escape=False), unsafe_allow_html=True)

# 4. Menu Admin: Data Absensi
elif menu == "Data Absensi" and role == "Admin":
    st.subheader("Data Presensi Karyawan")

    # Pilih Tahun, Bulan, Rentang
    day_map={0:"Senin",1:"Selasa",2:"Rabu",3:"Kamis",4:"Jumat",5:"Sabtu",6:"Minggu"}
    bulan_id=["","Januari","Februari","Maret","April","Mei","Juni","Juli","Agustus","September","Oktober","November","Desember"]
    selected_year = st.number_input("Pilih Tahun",2000,2100,2024)
    selected_month = st.selectbox("Pilih Bulan", list(range(1,13)), format_func=lambda x: bulan_id[x])
    num_days = cal_mod.monthrange(selected_year, selected_month)[1]
    start_date, end_date = st.date_input(
        "Pilih Rentang Tanggal",
        value=(datetime(selected_year, selected_month,1), datetime(selected_year, selected_month,num_days)),
        min_value=datetime(selected_year, selected_month,1), max_value=datetime(selected_year, selected_month,num_days)
    )

    # Ambil dari DB
    month_str=f"{selected_year}-{selected_month:02d}"  
    conn=sqlite3.connect("absensi.db")
    df_abs_db=pd.read_sql_query("SELECT * FROM absensi WHERE tanggal LIKE ?", conn, params=(month_str+"-%",))
    conn.close()

    # **Filter Data: Hanya Presensi (Tepat Waktu + Telat)**
    df_presensi = df_abs_db[~df_abs_db['status'].isin(["Cuti","Sakit","WFH"])]

    if df_presensi.empty:
        st.info(f"Data absensi untuk {month_str} belum ada. Silakan upload.")
        up = st.file_uploader("Upload Data Absensi Bulanan", type=["xlsx"])
        if up:
            try:
                df_in = pd.read_excel(up)
                df_proc = format_presensi_data(df_in)
                if df_proc.empty:
                    st.error("Data dalam file tidak valid.")
                else:
                    df_proc['tanggal'] = df_proc['tanggal'].apply(lambda d: f"{selected_year}-{selected_month:02d}-{int(d):02d}")
                    df_proc.rename(columns={"Nama":"nama","datang":"jam_masuk","pulang":"jam_keluar"}, inplace=True)
                    save_absensi_to_db(df_proc)
                    st.success("Data berhasil disimpan!")
            except Exception as e:
                st.error(f"Error membaca file: {e}")
    else:
        # Filter rentang
        mask = (df_presensi['tanggal']>=start_date.strftime('%Y-%m-%d')) & (df_presensi['tanggal']<=end_date.strftime('%Y-%m-%d'))
        filtered_df = df_presensi[mask]
        if filtered_df.empty:
            st.info("Tidak ada data untuk rentang tersebut.")
        else:
            def highlight_telat(row):
                return ['background-color: #ffcccc' if row['status'].lower()=='telat' else '' for _ in row]
            styled_df = filtered_df.style.apply(highlight_telat, axis=1)
            st.write(f"**Data Presensi untuk {start_date.strftime('%d %B %Y')} hingga {end_date.strftime('%d %B %Y')}:**")
            st.dataframe(styled_df, use_container_width=True)

# 5. Menu Admin: Kalender Absensi
elif menu == "Kalender Absensi" and role == "Admin":
    st.subheader("Kalender Absensi Karyawan")
    df_all = load_absensi()
    if not df_all.empty:
        df_all['tanggal_dt'] = pd.to_datetime(df_all['tanggal']).dt.date
        grp = df_all.groupby('tanggal_dt').apply(lambda g: pd.Series({
            'hadir': len(g), 'telat': (g['status'].str.lower()=='telat').sum()
        })).reset_index()
    else:
        grp = pd.DataFrame(columns=['tanggal_dt','hadir','telat'])
    izin_all = load_izin()
    abs_dict = {}
    for _,r in izin_all.iterrows():
        try:
            sd = datetime.strptime(r['tanggal_izin'], "%Y-%m-%d").date()
            for d in range(int(r['jumlah_hari'])):
                abs_dict[sd+timedelta(days=d)] = abs_dict.get(sd+timedelta(days=d),0)+1
        except:
            continue
    all_dates = set(grp['tanggal_dt']).union(abs_dict.keys())
    events=[]
    for d in sorted(all_dates):
        row = grp[grp['tanggal_dt']==d]
        h = int(row['hadir'].iloc[0]) if not row.empty else 0
        t = int(row['telat'].iloc[0]) if not row.empty else 0
        th = abs_dict.get(d,0)
        events.append({"title":f"H:{h} T:{t} TH:{th}","start":d.strftime("%Y-%m-%d"),"color":"transparent","textColor":"black"})
    calendar(events=events, options={"editable":False,"header":{'"left"':'prev,next today','"center"':'title','"right"':'month,agendaWeek,agendaDay'},"defaultView":"month"})
    st.markdown("---")
    sel_date = st.date_input("Pilih Tanggal untuk rincian", value=datetime.today())
    sd_str = sel_date.strftime("%Y-%m-%d")
    conn=sqlite3.connect("absensi.db")
    df_abs = pd.read_sql_query("SELECT * FROM absensi WHERE tanggal=?", conn, params=(sd_str,))
    df_iz = pd.read_sql_query("SELECT * FROM izin", conn)
    conn.close()
    def is_absent(row, sel):
        try:
            s = datetime.strptime(row['tanggal_izin'], "%Y-%m-%d").date()
            e = s + timedelta(days=int(row['jumlah_hari'])-1)
            return s<=sel<=e
        except:
            return False
    df_absent = df_iz[df_iz.apply(lambda r: is_absent(r, sel_date), axis=1)]
    karyawan_hadir = df_abs[~df_abs['nama'].isin(df_absent['nama'])]
    hadir_count = len(karyawan_hadir)
    telat_count = len(karyawan_hadir[karyawan_hadir['status'].str.lower()=='telat'])
    tidak_hadir_count = len(df_absent)
    st.markdown(f"### Ringkasan Absensi untuk {sel_date.strftime('%A, %d %B %Y')}")
    c1,c2,c3 = st.columns(3)
    if c1.button(f"{hadir_count} karyawan hadir"): st.session_state.detail_type='hadir'
    if c2.button(f"{telat_count} karyawan terlambat"): st.session_state.detail_type='telat'
    if c3.button(f"{tidak_hadir_count} karyawan tidak hadir"): st.session_state.detail_type='tidak_hadir'
    if st.session_state.detail_type:
        st.markdown("#### Rincian Data")
        if st.button("Tutup rincian"): st.session_state.detail_type=None
        if st.session_state.detail_type=='hadir':
            karyawan_tepat = karyawan_hadir[karyawan_hadir['status'].str.lower()=='tepat waktu']
            st.dataframe(karyawan_tepat, use_container_width=True)
        elif st.session_state.detail_type=='telat':
            st.dataframe(karyawan_hadir[karyawan_hadir['status'].str.lower()=='telat'], use_container_width=True)
        elif st.session_state.detail_type=='tidak_hadir':
            if df_absent.empty:
                st.info("Tidak ada data karyawan tidak hadir untuk tanggal ini.")
            else:
                st.dataframe(df_absent[['nama','divisi','jenis_pengajuan','tanggal_izin','jumlah_hari']], use_container_width=True)

from streamlit.runtime.scriptrunner import get_script_run_ctx

if __name__ == '__main__':
    if get_script_run_ctx() is None:
        import sys
        try:
            from streamlit.web import cli as stcli
        except ImportError:
            from streamlit import cli as stcli
        sys.argv = ["streamlit", "run", __file__]
        sys.exit(stcli.main())



import streamlit as st
import socket
import json
import struct
import base64
import os
import random
import time

PORT = 8080
HOST = '103.150.117.213'
PORT = 8080
LOCAL_REG_FILE = 'registered_profiles.json'
FOLDER_TERIMA = 'received_files_web'


STRUKTUR_GBM = {
    "Pimpinan & Administrasi": ["Kepala SPPG", "Akuntan", "Ahli Gizi"],
    "Tim Produksi Makanan": ["Petugas Pengadaan Bahan Baku", "Chef/Tukang Masak", "Petugas Pemorsian"],
    "Tim Logistik dan Pengadaan": ["Petugas Penerima Bahan Pangan", "Staff Gudang Pangan", "Distributor Bahan Mentah"],
    "Tim Pengemasan dan Distribusi": ["Staff Pengemasan", "Kurir/Armada Pengantaran"],
    "Petugas Sanitasi": ["Koordinator Kebersihan Dapur", "Pemeriksa Higienitas Alat", "Pengelola Pembuangan Limbah"]
}

os.makedirs(FOLDER_TERIMA, exist_ok=True)

# --- FIX SAKTI: FUNGSI LOOPING PENERIMA DATA STREAM DI SISI CLIENT ---
def receive_fixed_size_client(sock, size):
    data = b''
    while len(data) < size:
        packet = sock.recv(size - len(data))
        if not packet: return None
        data += packet
    return data

# --- DYNAMIC HISTORY PER USER ---
def dapatkan_nama_file_history():
    if "my_id" not in st.session_state or st.session_state.my_id is None:
        return 'chat_history_guest.json'
    return f'chat_history_{st.session_state.my_id}.json'

def muat_history_dari_file():
    nama_file = dapatkan_nama_file_history()
    if os.path.exists(nama_file):
        try:
            with open(nama_file, 'r') as f:
                data = json.load(f)
                if "rooms" in data and "personal_chats" in data:
                    validated_rooms = {div: [] for div in STRUKTUR_GBM.keys()}
                    for k, v in data["rooms"].items():
                        if k in validated_rooms: validated_rooms[k] = v
                    return validated_rooms, data["personal_chats"]
        except Exception: pass
    default_rooms = {div: [] for div in STRUKTUR_GBM.keys()}
    return default_rooms, {}

def simpan_history_ke_file():
    try:
        nama_file = dapatkan_nama_file_history()
        data_to_save = {"rooms": st.session_state.rooms, "personal_chats": st.session_state.personal_chats}
        with open(nama_file, 'w') as f: json.dump(data_to_save, f, indent=4)
    except Exception: pass

# --- DATABASE AKUN LOKAL CORNER ---
def muat_semua_akun_lokal():
    if os.path.exists(LOCAL_REG_FILE):
        try:
            with open(LOCAL_REG_FILE, 'r') as f: return json.load(f)
        except Exception: pass
    return []

def simpan_semua_akun_lokal(daftar_akun):
    with open(LOCAL_REG_FILE, 'w') as f: json.dump(daftar_akun, f, indent=4)

def cek_autentikasi_login(nama, password):
    daftar_akun = muat_semua_akun_lokal()
    for akun in daftar_akun:
        if akun["nama"].lower() == nama.lower() and akun["password"] == password: return akun
    return None

def dapatkan_nama_dari_id(user_id):
    if not user_id:
        return "Tamu"
    if user_id.startswith("GBM-"):
        daftar_akun = muat_semua_akun_lokal()
        for akun in daftar_akun:
            if akun["id"] == user_id: return akun["nama"]
    return user_id

def dapatkan_pratinjau_pesan(list_msg, my_name):
    if not list_msg:
        return "Belum ada pesan."
    last_msg_item = list_msg[-1]
    sender = last_msg_item["sender"]
    content = last_msg_item["content"]
    
    # Prefix pengirim: "Kamu: " jika pengirim adalah saya, selain itu "[Nama]: "
    prefix = "Kamu: " if sender == my_name else f"{sender}: "
    
    # Bersihkan jika itu file
    if isinstance(content, str) and content.startswith("__MEDIA_FILE__:"):
        nama_file = content.split("__MEDIA_FILE__:")[1].strip()
        preview = f"{prefix}📁 Berkas: {nama_file}"
    else:
        preview = f"{prefix}{content}"
        
    return preview[:35] + "..." if len(preview) > 35 else preview

# --- INITIALIZATION STATE ---
if "connected" not in st.session_state: st.session_state.connected = False
if "my_id" not in st.session_state: st.session_state.my_id = None
if "my_name" not in st.session_state: st.session_state.my_name = None
if "my_divisi" not in st.session_state: st.session_state.my_divisi = None
if "my_jabatan" not in st.session_state: st.session_state.my_jabatan = None
if "file_uploader_key" not in st.session_state: st.session_state.file_uploader_key = 0

if "rooms" not in st.session_state or "personal_chats" not in st.session_state:
    loaded_rooms, loaded_personal = muat_history_dari_file()
    st.session_state.rooms = loaded_rooms
    st.session_state.personal_chats = loaded_personal

if "active_room" not in st.session_state: st.session_state.active_room = None
if "active_room_type" not in st.session_state: st.session_state.active_room_type = None

# --- FIX SAKTI: IMPLEMENTASI PENERIMA KUALITAS TINGGI PADA INSTANT TRANSMISSION ---
def kirim_dan_terima_instant(packet):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST, PORT))
        data_bytes = json.dumps(packet).encode('utf-8')
        header = struct.pack('!I', len(data_bytes))
        sock.sendall(header + data_bytes)
        
        # Membaca header ukuran balasan dari server secara presisi (4 bytes)
        res_header = receive_fixed_size_client(sock, 4)
        if res_header:
            packet_length = struct.unpack('!I', res_header)[0]
            # Melakukan loop penarikan data biner sampai utuh tanpa terputus MTU jarkom
            res_bytes = receive_fixed_size_client(sock, packet_length)
            if res_bytes:
                respon = json.loads(res_bytes.decode('utf-8'))
                sock.close()
                return respon
        sock.close()
    except Exception: pass
    return None

# --- UI RENDERING FORM DEPAN ---
if not st.session_state.connected:
    col_kiri, col_tengah, col_kanan = st.columns([1.1, 1.4, 1.1])
    with col_tengah:
        st.write(""); st.write("")
        st.markdown("<h1 style='text-align: center; font-family: sans-serif; font-size: 38px;'>🍲 GBM Portal</h1>", unsafe_allow_html=True)
        tab_login, tab_register, tab_forgot = st.tabs(["🔒 Log In", "📝 Sign Up", "🔑 Lupa Password"])
        
        with tab_login:
            st.write("")
            login_nama = st.text_input("Username / Nama Lengkap:", placeholder="Masukkan nama lu pas daftar...", key="log_name_input").strip()
            login_pass = st.text_input("Password Akun:", type="password", placeholder="Masukkan password...", key="log_pass_input")
            st.write("")
            
            if st.button("Masuk Jaringan 🔓", use_container_width=True):
                if login_nama and login_pass:
                    akun_cocok = cek_autentikasi_login(login_nama, login_pass)
                    if not akun_cocok: st.error("❌ Nama atau Password lu salah!")
                    else:
                        res = kirim_dan_terima_instant({"type": "REGISTER_ACTIVE", "from_id": akun_cocok["id"], "from_name": akun_cocok["nama"], "divisi": akun_cocok["divisi"], "jabatan": akun_cocok["jabatan"]})
                        if res:
                            st.session_state.connected = True
                            st.session_state.my_id = akun_cocok["id"]
                            st.session_state.my_name = akun_cocok["nama"]
                            st.session_state.my_divisi = akun_cocok["divisi"]
                            st.session_state.my_jabatan = akun_cocok["jabatan"]
                            st.session_state.rooms, st.session_state.personal_chats = muat_history_dari_file()
                            st.rerun()
                        else: st.error("Server Utama Offline!")
                    
        with tab_register:
            st.write("")
            reg_nama = st.text_input("Nama Lengkap Baru:", key="reg_name_input").strip()
            reg_pass = st.text_input("Buat Password Akun:", type="password", key="reg_pass_input")
            reg_divisi = st.selectbox("Pilih Divisi Penugasan:", list(STRUKTUR_GBM.keys()), key="reg_div_select")
            reg_jabatan = st.selectbox("Pilih Jabatan Struktural:", STRUKTUR_GBM[reg_divisi], key="reg_jab_select")
            if st.button("Daftar Akun Baru 🚀", use_container_width=True):
                if reg_nama and reg_pass:
                    daftar_akun = muat_semua_akun_lokal()
                    if any(a["nama"].lower() == reg_nama.lower() and a["password"] == reg_pass for a in daftar_akun):
                        st.error("❌ Kombinasi Nama dan Password sudah terdaftar!")
                    else:
                        r_id = f"GBM-{random.randint(1000, 9999)}"
                        daftar_akun.append({"id": r_id, "nama": reg_nama, "password": reg_pass, "divisi": reg_divisi, "jabatan": reg_jabatan})
                        simpan_semua_akun_lokal(daftar_akun)
                        st.success(f"🎉 Registrasi Sukses! ID Chat Anda: {r_id}")
                else: st.error("Nama dan Password wajib diisi!")

        with tab_forgot:
            st.write("")
            st.markdown("### 🛡️ Verifikasi 2 Langkah Reset Password")
            forgot_nama = st.text_input("1. Masukkan Nama Lengkap Akun:", key="forgot_name_input").strip()
            forgot_id_verify = st.text_input("2. Masukkan Kunci ID Chat Anda (GBM-XXXX):", key="forgot_id_input").strip().upper()
            forgot_pass_baru = st.text_input("3. Masukkan Password Baru:", type="password", key="forgot_pass_new")
            if st.button("Update Password Baru 🔄", use_container_width=True):
                if forgot_nama and forgot_id_verify and forgot_pass_baru:
                    daftar_akun = muat_semua_akun_lokal()
                    success = False
                    for akun in daftar_akun:
                        if akun["nama"].lower() == forgot_nama.lower() and akun["id"] == forgot_id_verify:
                            akun["password"] = forgot_pass_baru
                            success = True
                            break
                    if success:
                        simpan_semua_akun_lokal(daftar_akun)
                        st.success("✅ Password sukses diubah!")
                    else: st.error("❌ Verifikasi data salah!")
else:
    # --- ENGINE POOLING AUTOMATIC ---
    @st.fragment(run_every=1.0)
    def auto_refresh_pooling_loop():
        if st.session_state.my_id is not None:
            res = kirim_dan_terima_instant({"type": "FETCH_CHATS", "from_id": st.session_state.my_id})
            if res and "chats" in res and res["chats"]:
                needs_save = False
                for payload in res["chats"]:
                    s_name = payload.get('from_name')
                    s_id = payload.get('from_id')
                    p_type = payload.get('type')
                    
                    if payload.get('msgType') == 'FILE':
                        f_name = payload.get('fileName') if payload.get('fileName') else payload.get('filename')
                        if not f_name: f_name = "file_tanpa_nama"
                        f_content = base64.b64decode(payload.get('content').encode('utf-8'))
                        with open(os.path.join(FOLDER_TERIMA, f_name), 'wb') as f: f.write(f_content)
                        msg_content = f"__MEDIA_FILE__:{f_name}"
                    else:
                        msg_content = payload.get('content')

                    chat_entry = {"sender": s_name, "content": msg_content, "time": time.strftime("%H:%M")}
                    
                    if p_type == "UNICAST":
                        if s_id not in st.session_state.personal_chats: st.session_state.personal_chats[s_id] = []
                        st.session_state.personal_chats[s_id].append(chat_entry)
                        needs_save = True
                    elif p_type == "MULTICAST":
                        t_div = payload.get('to_divisi')
                        if t_div in st.session_state.rooms:
                            st.session_state.rooms[t_div].append(chat_entry)
                            needs_save = True
                    elif p_type == "BROADCAST_TOA_ALL_GROUPS":
                        # Jika penerima adalah Pimpinan, masukkan ke seluruh room divisi yang dimilikinya
                        if st.session_state.my_divisi == "Pimpinan & Administrasi":
                            for div in st.session_state.rooms.keys():
                                st.session_state.rooms[div].append(chat_entry)
                        else:
                            # Jika penerima adalah staff biasa, masukkan ke room divisi milik staff tersebut
                            t_div = st.session_state.my_divisi
                            if t_div in st.session_state.rooms:
                                st.session_state.rooms[t_div].append(chat_entry)
                        needs_save = True
                if needs_save: 
                    simpan_history_ke_file()
                    st.rerun()

    auto_refresh_pooling_loop()

    # --- MAIN SIDEBAR PROFIL ---
    st.sidebar.success(f"🟢 ONLINE: {st.session_state.my_name}")
    st.sidebar.code(f"ID Chat: {st.session_state.my_id}") 
    st.sidebar.text(f"Divisi: {st.session_state.my_divisi}")
    st.sidebar.text(f"Jabatan: {st.session_state.my_jabatan}")
    st.sidebar.markdown("---")
    
    is_pimpinan = st.session_state.my_divisi == "Pimpinan & Administrasi"
    if is_pimpinan:
        with st.sidebar.expander("📢 Announcement", expanded=False):
            target_toa = st.selectbox("Pilih Jalur Distribusi:", ["Kirim ke Semua Grup Divisi", "Kirim ke Semua Chat Personal"], key="target_toa_select")
            isi_toa = st.text_area("Isi Pengumuman Toa:", key="isi_toa_text")
            if st.button("Semburkan Toa 📢", use_container_width=True):
                if isi_toa:
                    macro_type = "BROADCAST_TOA_ALL_GROUPS" if "Grup" in target_toa else "BROADCAST_TOA_ALL_PERSONAL"
                    packet = {"type": macro_type, "from_id": st.session_state.my_id, "from_name": st.session_state.my_name, "divisi": st.session_state.my_divisi, "jabatan": st.session_state.my_jabatan, "msgType": "TEXT", "content": f"📢 [ANNOUNCEMENT PIMPINAN]: {isi_toa}"}
                    if kirim_dan_terima_instant(packet):
                        chat_saya = {"sender": st.session_state.my_name, "content": f"📢 [ANNOUNCEMENT PIMPINAN]: {isi_toa}", "time": time.strftime("%H:%M")}
                        if "Grup" in target_toa:
                            for div in st.session_state.rooms.keys(): st.session_state.rooms[div].append(chat_saya)
                        else:
                            for target_id in st.session_state.personal_chats.keys(): st.session_state.personal_chats[target_id].append(chat_saya)
                        simpan_history_ke_file(); st.toast("Toa pengumuman sukses disemburkan!"); st.rerun()

    if st.sidebar.button("Keluar Jaringan ❌", use_container_width=True):
        st.session_state.connected = False
        st.session_state.my_id = None; st.rerun()

    # --- FUNGSI KIRIM PESAN DENGAN BERSIHKAN INPUT OTOMATIS ---
    def proses_kirim_pesan(teks, file_upload_wa):
        teks = teks.strip() if teks else ""
        if teks or file_upload_wa:
            p_type = "UNICAST" if st.session_state.active_room_type == "PERSONAL" else "MULTICAST"
            room_aktif = st.session_state.active_room
            success_sent = False
            
            # 1. Kirim pesan teks jika diisi
            if teks:
                packet_teks = {
                    "type": p_type, "from_id": st.session_state.my_id, "from_name": st.session_state.my_name,
                    "divisi": st.session_state.my_divisi, "jabatan": st.session_state.my_jabatan,
                    "msgType": "TEXT", "content": teks,
                    "to_id": room_aktif if p_type == "UNICAST" else "",
                    "to_divisi": room_aktif if p_type == "MULTICAST" else ""
                }
                if kirim_dan_terima_instant(packet_teks):
                    chat_saya = {"sender": st.session_state.my_name, "content": teks, "time": time.strftime("%H:%M")}
                    if p_type == "UNICAST": st.session_state.personal_chats[room_aktif].append(chat_saya)
                    else: st.session_state.rooms[room_aktif].append(chat_saya)
                    success_sent = True
                    
            # 2. Kirim berkas jika diunggah
            if file_upload_wa:
                nama_f = file_upload_wa.name
                konten_f_bytes = file_upload_wa.read()
                encoded_file = base64.b64encode(konten_f_bytes).decode('utf-8')
                
                # Simpan berkas secara lokal di sisi pengirim agar bisa di-render
                with open(os.path.join(FOLDER_TERIMA, nama_f), 'wb') as f: f.write(konten_f_bytes)
                
                packet_file = {
                    "type": p_type, "from_id": st.session_state.my_id, "from_name": st.session_state.my_name,
                    "divisi": st.session_state.my_divisi, "jabatan": st.session_state.my_jabatan,
                    "msgType": "FILE", "content": encoded_file, "fileName": nama_f,
                    "to_id": room_aktif if p_type == "UNICAST" else "",
                    "to_divisi": room_aktif if p_type == "MULTICAST" else ""
                }
                if kirim_dan_terima_instant(packet_file):
                    chat_saya_file = {"sender": st.session_state.my_name, "content": f"__MEDIA_FILE__:{nama_f}", "time": time.strftime("%H:%M")}
                    if p_type == "UNICAST": st.session_state.personal_chats[room_aktif].append(chat_saya_file)
                    else: st.session_state.rooms[room_aktif].append(chat_saya_file)
                    success_sent = True
                    
            if success_sent:
                # Reset uploader berkas dengan menaikkan suffix key
                st.session_state.file_uploader_key += 1
                simpan_history_ke_file()
                st.toast("Pesan/Berkas berhasil terkirim!")

    # Layout Dashboard Utama WA Web Clone
    kolom_wa_kiri, kolom_wa_kanan = st.columns([1.1, 2.0])
    
    with kolom_wa_kiri:
        st.markdown("### 📱 Obrolan Masuk")
        sub_tab_personal, sub_tab_group = st.tabs(["💬 Personal Chat", "👥 Grup Divisi"])
        
        with sub_tab_personal:
            new_target = st.text_input("Mulai Chat Baru (ID Target):", key="wa_id_search", placeholder="Masukkan 4 angka ID (misal: 2608)...").strip().upper()
            if new_target:
                if len(new_target) == 4 and new_target.isdigit():
                    new_target = f"GBM-{new_target}"
                if new_target != st.session_state.my_id:
                    if new_target not in st.session_state.personal_chats:
                        st.session_state.personal_chats[new_target] = []
                        simpan_history_ke_file()
                
            if not st.session_state.personal_chats: st.caption("Belum ada obrolan personal.")
            else:
                for target_id, list_msg in st.session_state.personal_chats.items():
                    nama_target = dapatkan_nama_dari_id(target_id)
                    raw_msg = list_msg[-1]["content"] if list_msg else "Belum ada pesan."
                    last_msg = str(raw_msg).replace("__MEDIA_FILE__:", "📁 Berkas: ")[:25] + "..." if "__MEDIA_FILE__:" in str(raw_msg) else str(raw_msg)[:25] + "..."
                    
                    button_label = f"👤 {nama_target}\n\n{last_msg}"
                    if st.button(button_label, key=f"btn_{target_id}", use_container_width=True):
                        st.session_state.active_room = target_id
                        st.session_state.active_room_type = "PERSONAL"
                        st.rerun()
                        
        with sub_tab_group:
            st.write("")
            for nama_divisi, list_msg in st.session_state.rooms.items():
                if is_pimpinan or st.session_state.my_divisi == nama_divisi:
                    raw_msg = list_msg[-1]["content"] if list_msg else "Belum ada pesan koordinasi grup."
                    last_msg = str(raw_msg).replace("__MEDIA_FILE__:", "📁 Berkas: ")[:25] + "..." if "__MEDIA_FILE__:" in str(raw_msg) else str(raw_msg)[:25] + "..."
                    
                    button_label = f"🏢 {nama_divisi}\n\n{last_msg}"
                    if st.button(button_label, key=f"btn_group_{nama_divisi}", use_container_width=True):
                        st.session_state.active_room = nama_divisi
                        st.session_state.active_room_type = "DIVISI"
                        st.rerun()

    with kolom_wa_kanan:
        if st.session_state.active_room is None:
            st.markdown("<div style='height: 250px; display: flex; align-items: center; justify-content: center; border: 1px dashed gray; border-radius: 10px;'><h4 style='color: gray;'>Silakan klik salah satu obrolan untuk membuka room chat 💬</h4></div>", unsafe_allow_html=True)
        else:
            room_aktif = st.session_state.active_room
            tipe_room = st.session_state.active_room_type
            
            nama_tampil = dapatkan_nama_dari_id(room_aktif) if tipe_room == "PERSONAL" else room_aktif
            col_header_nama, col_header_btn = st.columns([2.0, 1.0])
            with col_header_nama: st.markdown(f"### 👤 {nama_tampil}" if tipe_room == "PERSONAL" else f"### 🏢 {room_aktif}")
            with col_header_btn:
                if st.button("🗑️ Bersihkan Obrolan Ini", key="btn_clear_spesifik", use_container_width=True):
                    if tipe_room == "PERSONAL": st.session_state.personal_chats[room_aktif] = []
                    else: st.session_state.rooms[room_aktif] = []
                    simpan_history_ke_file(); st.rerun()
                
            st.markdown("---")
            
            box_chat_history = st.container(height=380)
            with box_chat_history:
                riwayat_pesan = st.session_state.personal_chats.get(room_aktif, []) if tipe_room == "PERSONAL" else st.session_state.rooms.get(room_aktif, [])
                if not riwayat_pesan: st.caption("Obrolan kosong.")
                else:
                    for msg in riwayat_pesan:
                        is_me = msg["sender"] == st.session_state.my_name
                        align_css = "text-align: right; margin: 4px 0 4px auto;" if is_me else "text-align: left; margin: 4px auto 4px 0;"
                        bg_color = "#2b5c3f" if is_me else ("#6e2525" if "[ANNOUNCEMENT PIMPINAN]" in str(msg['content']) else "#3d3d3d")
                        sender_label = "<b>Anda</b>" if is_me else f"<b>{msg['sender']}</b>"
                        
                        content_str = str(msg['content'])
                        if content_str.startswith("__MEDIA_FILE__:") or content_str.startswith("__MEDIA_FILE__ :"):
                            nama_file_asli = content_str.split("__MEDIA_FILE__")[1].replace(":", "").strip()
                            path_file_lokal = os.path.join(FOLDER_TERIMA, nama_file_asli)
                            ext = os.path.splitext(nama_file_asli)[1].lower()
                            
                            st.markdown(f"<div style='{align_css} background-color: {bg_color}; padding: 8px 12px 2px 12px; border-radius: 10px 10px 0 0; width: fit-content; max-width: 75%; color: white;'>{sender_label}<br><small style='font-size: 11px; color: #b5b5b5;'>📁 {nama_file_asli}</small></div>", unsafe_allow_html=True)
                            
                            with st.container():
                                if os.path.exists(path_file_lokal):
                                    with open(path_file_lokal, "rb") as f_bytes: data_biner = f_bytes.read()
                                    
                                    if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                                        st.image(path_file_lokal, use_container_width=True)
                                    elif ext in ['.mp3', '.wav', '.ogg', '.m4a']:
                                        st.audio(path_file_lokal)
                                    elif ext in ['.mp4', '.mov', '.avi', '.webm']:
                                        st.video(path_file_lokal)
                                    else:
                                        st.download_button(label=f"📥 Unduh {nama_file_asli}", data=data_biner, file_name=nama_file_asli, key=f"dl_{nama_file_asli}_{random.randint(0,100000)}")
                                else: st.error("Berkas biner tidak ditemukan!")
                                    
                            st.markdown(f"<div style='{align_css} background-color: {bg_color}; padding: 2px 12px 6px 12px; border-radius: 0 0 10px 10px; width: fit-content; max-width: 75%; color: white;'><small style='font-size: 10px; color: gray;'>{msg['time']}</small></div>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<div style='{align_css} background-color: {bg_color}; padding: 8px 12px; border-radius: 10px; margin: 4px {'0 4px auto' if is_me else 'auto 4px 0'}; width: fit-content; max-width: 75%; color: white;'>{sender_label}<br>{msg['content']}<br><small style='font-size: 10px; color: gray;'>{msg['time']}</small></div>", unsafe_allow_html=True)

            st.markdown("---")
            
            key_uploader = f"file_uploader_{st.session_state.file_uploader_key}"
            file_upload_wa = None
            
            # Buat layout input dan tombol attachment (+) di luar form
            col_input_area, col_attach = st.columns([8, 1])
            with col_attach:
                with st.popover("➕", help="Lampirkan File", use_container_width=True):
                    file_upload_wa = st.file_uploader("Pilih Berkas:", key=key_uploader, label_visibility="collapsed")
            
            with col_input_area:
                # Gunakan st.form borderless agar submit enter/button terpicu tepat 1 kali saja
                with st.form("chat_form", clear_on_submit=True, border=False):
                    input_teks_wa = st.text_input(
                        "Ketik pesan operasional Anda di sini...", 
                        label_visibility="collapsed", 
                        placeholder="Ketik pesan operasional Anda di sini..."
                    )
                    submitted = st.form_submit_button("Kirim Pesan ✉️", use_container_width=True)
            
            if file_upload_wa is not None:
                st.caption(f"📎 Berkas terpilih: `{file_upload_wa.name}`")
                
            if submitted:
                proses_kirim_pesan(input_teks_wa, file_upload_wa)
                st.rerun()

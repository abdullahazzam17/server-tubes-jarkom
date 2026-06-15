import streamlit as str
import socket
import threading
import json
import random

# ======= KONFIGURASI SERVER UTAMA (MAKELAR) =======
SERVER_UTAMA_IP = '103.150.117.213'  # IP VPS TAN Lu
SERVER_UTAMA_PORT = 8080

# Fungsi otomatis dapetin IP Lokal asli laptop lu (192.168.x.x)
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

str.set_page_config(page_title="GBM P2P Chat System", page_icon="📱", layout="wide")

if "my_port" not in str.session_state:
    str.session_state.my_port = random.randint(9000, 9999)
if "my_local_ip" not in str.session_state:
    str.session_state.my_local_ip = get_local_ip()
if "chat_history" not in str.session_state:
    str.session_state.chat_history = []
if "registered" not in str.session_state:
    str.session_state.registered = False

# THREAD SERVER INTERNAL (MENERIMA SAMBUNGAN PORT DIRECT)
def p2p_listener_thread(port):
    peer_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    peer_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        peer_server.bind(('0.0.0.0', port))
        peer_server.listen()
        while True:
            conn, addr = peer_server.accept()
            data = conn.recv(4096).decode('utf-8')
            if data:
                payload = json.loads(data)
                str.session_state.chat_history.append({
                    "from": payload["from_name"],
                    "msg": payload["msg"],
                    "type": payload["type"]
                })
            conn.close()
    except Exception:
        pass

if not str.session_state.get("listener_started", False):
    threading.Thread(target=p2p_listener_thread, args=(str.session_state.my_port,), daemon=True).start()
    str.session_state.listener_started = True

def register_ke_central(user_id, nama, divisi):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((SERVER_UTAMA_IP, SERVER_UTAMA_PORT))
        req = {
            "type": "REGISTER",
            "id": user_id,
            "nama": nama,
            "divisi": divisi,
            "local_ip": str.session_state.my_local_ip, # Kirim IP lokal
            "listening_port": str.session_state.my_port
        }
        s.sendall(json.dumps(req).encode('utf-8'))
        res = json.loads(s.recv(1024).decode('utf-8'))
        s.close()
        if res.get("status") == "OK":
            str.session_state.registered = True
            str.success(f"🎉 Login Sukses! Standby di {str.session_state.my_local_ip}:{str.session_state.my_port}")
    except Exception as e:
        str.error(f"❌ Gagal koneksi ke Operator Pusat: {e}")

def kirim_unicast_p2p(my_name, target_id, pesan):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((SERVER_UTAMA_IP, SERVER_UTAMA_PORT))
        s.sendall(json.dumps({"type": "FETCH_DIRECTORY"}).encode('utf-8'))
        res = json.loads(s.recv(4096).decode('utf-8'))
        s.close()
        
        directory = res.get("users", {})
        target_info = directory.get(target_id)
        
        if target_info:
            p2p_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            p2p_socket.connect((target_info["ip"], target_info["port"])) # Hubungkan langsung ke IP lokal target!
            
            packet = {"from_name": my_name, "msg": pesan, "type": "Personal Chat (P2P)"}
            p2p_socket.sendall(json.dumps(packet).encode('utf-8'))
            p2p_socket.close()
            
            str.session_state.chat_history.append({"from": "Anda", "msg": pesan, "type": "Personal Chat (P2P)"})
        else:
            str.warning("⚠️ ID Target tidak ditemukan/offline!")
    except Exception as e:
        str.error(f"❌ Gagal kirim direct port: {e}")

def broadcast_murni_p2p(my_id, my_name, pesan):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((SERVER_UTAMA_IP, SERVER_UTAMA_PORT))
        s.sendall(json.dumps({"type": "FETCH_DIRECTORY"}).encode('utf-8'))
        res = json.loads(s.recv(4096).decode('utf-8'))
        s.close()
        
        directory = res.get("users", {})
        for uid, info in directory.items():
            if uid != my_id:
                try:
                    p2p_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    p2p_socket.connect((info["ip"], info["port"]))
                    packet = {"from_name": my_name, "msg": pesan, "type": "TOA Broadcast (P2P)"}
                    p2p_socket.sendall(json.dumps(packet).encode('utf-8'))
                    p2p_socket.close()
                except Exception:
                    pass
        str.session_state.chat_history.append({"from": "Anda", "msg": pesan, "type": "TOA Broadcast (P2P)"})
    except Exception as e:
        str.error(f"🔥 Eror broadcast port: {e}")

# ==================== UI STREAMLIT ====================
str.title("📱 Portal Komunikasi - Model Multi-Port P2P (Circuit Switching)")
str.write("---")

if not str.session_state.registered:
    str.subheader("🔑 Registrasi Ke Operator Pusat")
    c1, c2, c3 = str.columns(3)
    with c1: u_id = str.text_input("Masukkan ID Anda")
    with c2: u_nama = str.text_input("Nama Lengkap")
    with c3: u_divisi = str.selectbox("Divisi", ["Pimpinan", "Administrasi", "Operasional"])
    
    if str.button("Masuk Jaringan Telepon 🚀"):
        if u_id and u_nama:
            register_ke_central(u_id, u_nama, u_divisi)
            str.session_state.my_id = u_id
            str.session_state.my_name = u_nama
            str.rerun()
else:
    str.sidebar.title(f"👤 {str.session_state.my_name}")
    str.sidebar.write(f"**ID:** {str.session_state.my_id}")
    str.sidebar.write(f"**IP Anda:** `{str.session_state.my_local_ip}`")
    str.sidebar.write(f"**Port Standby:** `{str.session_state.my_port}`")
    if str.sidebar.button("Refresh Masukan Chat 🔄"): str.rerun()
    
    tab1, tab2 = str.tabs(["💬 Unicast (Port-to-Port)", "📢 Broadcast (Semua Port)"])
    
    with tab1:
        target = str.text_input("Masukkan ID Target")
        pesan_uni = str.text_input("Isi Pesan")
        if str.button("Hubungkan & Kirim Pesan 📞"):
            if target and pesan_uni:
                kirim_unicast_p2p(str.session_state.my_name, target, pesan_uni)
                str.rerun()
                
    with tab2:
        pesan_broad = str.text_input("Teks Pengumuman TOA")
        if str.button("Injeksi Massal Ke Semua Port Jaringan 🚨"):
            if pesan_broad:
                broadcast_murni_p2p(str.session_state.my_id, str.session_state.my_name, pesan_broad)
                str.rerun()
                
    str.write("---")
    str.subheader("📬 Kotak Masuk Telepon Anda (Direct P2P Logs)")
    if not str.session_state.chat_history:
        str.info("Belum ada sambungan telepon masuk.")
    else:
        for chat in reversed(str.session_state.chat_history):
            if chat["from"] == "Anda":
                str.chat_message("user").write(f"**[{chat['type']}]** {chat['msg']}")
            else:
                str.chat_message("assistant").write(f"**{chat['from']} ({chat['type']}):** {chat['msg']}")

import socket
import threading
import json
import struct
import os

PORT = 8080
HOST = '127.0.0.1'
DB_FILE = 'database_gbm.json'

clients = []
chat_queues = {} 
clients_lock = threading.Lock()

def simpan_ke_database_json():
    with clients_lock:
        data_to_save = [{"id": c["id"], "nama": c["nama"], "divisi": c["divisi"], "jabatan": c["jabatan"]} for c in clients]
    try:
        with open(DB_FILE, 'w') as f: json.dump(data_to_save, f, indent=4)
    except Exception: pass

def send_packet(target_socket, data_dict):
    try:
        data_bytes = json.dumps(data_dict).encode('utf-8')
        header = struct.pack('!I', len(data_bytes))
        target_socket.sendall(header + data_bytes)
    except Exception: pass

def receive_fixed_size(client_socket, size):
    data = b''
    while len(data) < size:
        packet = client_socket.recv(size - len(data))
        if not packet: return None
        data += packet
    return data

def handle_client(client_socket):
    global clients
    try:
        while True:
            header = receive_fixed_size(client_socket, 4)
            if not header: break
            packet_length = struct.unpack('!I', header)[0]
            packet_bytes = receive_fixed_size(client_socket, packet_length)
            if not packet_bytes: break
                
            payload = json.loads(packet_bytes.decode('utf-8'))
            packet_type = payload.get('type')
            sender_id = payload.get('from_id')
            sender_name = payload.get('from_name')
            
            if packet_type == 'FETCH_CHATS':
                my_id = payload.get('from_id')
                my_queue = chat_queues.get(my_id, [])
                send_packet(client_socket, {"type": "FETCH_RESULT", "chats": my_queue})
                chat_queues[my_id] = [] 
                continue

            if packet_type == 'REGISTER_ACTIVE':
                with clients_lock:
                    clients = [c for c in clients if c['id'] != sender_id]
                    clients.append({"id": sender_id, "nama": sender_name, "divisi": payload.get('divisi'), "jabatan": payload.get('jabatan')})
                if sender_id not in chat_queues: chat_queues[sender_id] = []
                print(f"[LOGIN SUCCESS] {sender_name} ({sender_id}) Online!")
                simpan_ke_database_json()
                send_packet(client_socket, {"type": "OK"})
                
            elif packet_type == 'UNICAST':
                to_id = payload.get('to_id')
                if to_id not in chat_queues: chat_queues[to_id] = []
                chat_queues[to_id].append(payload)
                print(f"[UNICAST] {sender_name} -> Target: {to_id}")
                send_packet(client_socket, {"type": "OK"})
                
            elif packet_type == 'MULTICAST':
                target_group = payload.get('to_divisi')
                with clients_lock:
                    for c in clients:
                        if c['id'] != sender_id:
                            if c['divisi'] == target_group or c['divisi'] == "Pimpinan & Administrasi":
                                if c['id'] not in chat_queues: chat_queues[c['id']] = []
                                chat_queues[c['id']].append(payload)
                print(f"[MULTICAST] Grup [{target_group}] Terdistribusi")
                send_packet(client_socket, {"type": "OK"})
                
            # FITUR TOA GLOBAL INJECTOR (SERVER SIDE)
            elif packet_type == 'BROADCAST_TOA_ALL_GROUPS':
                # Mengirim ke seluruh grup divisi sekaligus
                with clients_lock:
                    for c in clients:
                        if c['id'] != sender_id:
                            if c['id'] not in chat_queues: chat_queues[c['id']] = []
                            chat_queues[c['id']].append(payload)
                print(f"[BROADCAST TOA] Sukses injeksi massal ke semua grup divisi oleh {sender_name}")
                send_packet(client_socket, {"type": "OK"})
                
            elif packet_type == 'BROADCAST_TOA_ALL_PERSONAL':
                # Mengirim ke room personal chat semua orang secara personal
                with clients_lock:
                    for c in clients:
                        if c['id'] != sender_id:
                            if c['id'] not in chat_queues: chat_queues[c['id']] = []
                            # Ubah tipe makro di antrean client tujuan menjadi UNICAST agar masuk ke folder chat personal mereka
                            cloned_payload = payload.copy()
                            cloned_payload["type"] = "UNICAST"
                            chat_queues[c['id']].append(cloned_payload)
                print(f"[BROADCAST TOA] Sukses injeksi massal ke semua chat personal oleh {sender_name}")
                send_packet(client_socket, {"type": "OK"})
    except Exception: pass
    finally: client_socket.close()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    server.settimeout(1.0)  # Set timeout agar Ctrl+C (KeyboardInterrupt) bisa dideteksi pada Windows
    print(f"=== SERVER TOA INJECTOR ACTIVE ===")
    try:
        while True:
            try:
                client_socket, _ = server.accept()
                client_socket.settimeout(None)  # Matikan timeout pada socket client agar bekerja secara blocking normal
                threading.Thread(target=handle_client, args=(client_socket,), daemon=True).start()
            except socket.timeout:
                continue
    except KeyboardInterrupt:
        print("\nServer mati.")
    finally:
        server.close()

if __name__ == '__main__': main()
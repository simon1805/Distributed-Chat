import socket
import threading
import time
import logging
import ast
from config import BACKUP_SERVER_HOST, BACKUP_SERVER_PORT, PRIMARY_SERVER_HOST, PRIMARY_SERVER_PORT, HEARTBEAT_TIMEOUT

logging.basicConfig(filename='chat.log', level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

clients = {}
client_ip = []
ring = None
last_heartbeat = time.time()
lock = threading.Lock()
leader=""
sock = None
local_ip= ""
servers = {}

def monitor_heartbeat():
    global last_heartbeat
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((BACKUP_SERVER_HOST, BACKUP_SERVER_PORT))
        s.listen()
        print("[STANDBY] Backup-Server wartet auf Heartbeats...")
        while True:
            conn, _ = s.accept()
            data = conn.recv(1024)
            if data == b"HEARTBEAT":
                last_heartbeat = time.time()
            conn.close()

# hier werden die reinkommenden Nachrichten behandelt
def monitor_message():
    global sock
    global ring
    global leader
    global last_heartbeat
    global client_ip
    while True:
            try:
                msg = sock.recv(1024).decode()
                if msg:
                    # Hier werden die Daten von dem Leader übergeben
                    if "[RING]" in msg and "[LEADER]" in msg and "[CLIENT]" in msg:
                        msg_client = msg.split("[CLIENT]")
                        msg_leader = msg_client[0].split("[LEADER]")
                        msg_ring= msg_leader[0].split("[RING]")[1]
                        client_ip=ast.literal_eval(msg_client[1])
                        leader=msg_leader[1]
                        ring=ast.literal_eval(msg_ring)
                        print(f"Servers: {ring}")
                        print(f"Clients: {client_ip}")
                        print(f"Leader: {leader}")
                    # wenn ein neuer Client in das System eintritt
                    elif "[CLIENT]" in msg:
                        client_ip=ast.literal_eval(msg.split("[CLIENT]")[1])
                        print(f"New Client arrived: {client_ip}")
                    # Heartbeat von dem Leader
                    elif "[HEARTBEAT]" in msg:
                        last_heartbeat = time.time()
            except Exception as e:
                print(f"[System] Verbindung unterbrochen: {e}")
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                    sock.close()
                except:
                    print("")
                time.sleep(2)

# Hier startet der Backupserver
def run_backup_server():
    global last_heartbeat
    join_system()
    #threading.Thread(target=monitor_heartbeat, daemon=True).start()
    threading.Thread(target=monitor_message, daemon=True).start()
    while True:
        time.sleep(1)
        if time.time() - last_heartbeat > HEARTBEAT_TIMEOUT:
            print("[ÜBERNAHME] Kein Heartbeat erkannt. Backup-Server wird aktiv.")
            logging.warning("Backup-Server übernimmt wegen Serverausfall.")
            check_leader()
            break

# Entscheidung welcher Server übernimmt
def check_leader():
    global ring
    global local_ip
    global leader
    # Use BACKUP_SERVER_HOST as the local server's IP
    local_ip = local_ip
    if ring and len(ring) > 0:
        first_server_ip = ring[0]
        if first_server_ip == local_ip:
            print("[INFO] This server is the leader (first in the ring).")
            leader = local_ip
            create_connections()
            return True
        else:
            print(f"[INFO] This server is NOT the leader. Leader IP: {first_server_ip}")
            return False
    else:
        print("[WARN] Ring is empty or not initialized.")
        return False

def create_connections():
    global sock
    global local_ip
    global servers
    global clients
    global leader

    # Verbinde zu jedem Client im Ring
    for server_ip in ring:
        if server_ip != local_ip:  # Vermeide Verbindung zum eigenen Server
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((server_ip, PRIMARY_SERVER_PORT))
                servers[sock] = server_ip
                print(f"[VERBINDUNG] Verbunden mit Client {server_ip}")
                message = f"[NEWSERVER][RING] {ring} [LEADER] {leader} [CLIENT] {list(clients.values())}"
                sock.send(message.encode())
            except Exception as e:
                print(f"[FEHLER] Verbindung zu {server_ip} fehlgeschlagen: {e}")
    for client in client_ip:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((client[0], PRIMARY_SERVER_PORT))
            print(sock)
            clients[sock] = client[0]
            print(f"[VERBINDUNG] Verbunden mit Client {client}")
            message = f"[NEWSERVER]"
            sock.send(message.encode())
        except Exception as e:
            print(f"[FEHLER] Verbindung zu {client} fehlgeschlagen: {e}")
    print(clients)
    print(servers)

def handle_client(conn, addr):
    username = ""
    try:
        join_msg = conn.recv(1024).decode()
        if join_msg.startswith("[JOIN] "):
            username = join_msg.split("[JOIN] ")[1].strip()
            with lock:
                clients[conn] = username
            broadcast(f"[System] {username} ist dem Chat beigetreten.", conn,"client")
            logging.info(f"{username} (via Backup) verbunden.")
            

        while True:
            msg = conn.recv(1024).decode()
            if not msg:
                break
            logging.info(f"{username} (via Backup): {msg}")
            broadcast(msg, conn,"client")
    except Exception as e:
        logging.error(f"Fehler bei {addr}: {e}")
    finally:
        with lock:
            if conn in clients:
                left_user = clients.pop(conn)
                broadcast(f"[System] {left_user} hat den Chat verlassen.", conn,"client")
                logging.info(f"{left_user} (via Backup) getrennt.")
        conn.close()

def broadcast(message, sender_conn,typ):
    with lock:
        if typ=="client":
            for client in list(clients.keys()):
                if client != sender_conn:
                    try:
                        client.send(message.encode())
                    except:
                        client.close()
                        clients.pop(client, None)
        if typ=="server":               
            for server in list(servers.keys()):
                try:
                    server.send(message.encode())
                except Exception as e:
                    server.close()
                    print(e)

def start_server(): # Todo: change. The server has to connect to the clients
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((PRIMARY_SERVER_HOST, PRIMARY_SERVER_PORT)) # Hier wird sich mit dem Leader Server verbunden
    server.listen()
    print(f"[AKTIV] Backup-Server übernimmt auf {PRIMARY_SERVER_HOST}:{PRIMARY_SERVER_PORT}")
    logging.info("Backup-Server aktiv.")

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

def join_system():
    global sock
    global local_ip
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((PRIMARY_SERVER_HOST, PRIMARY_SERVER_PORT))
            local_ip=sock.getsockname()[0]
            sock.send("[SERVER]".encode())
            print("Server mit System verbunden")
            break
        except Exception as e:
            print(e)
            time.sleep(2)
    print("Ende von Join System")

if __name__ == "__main__":
    run_backup_server()


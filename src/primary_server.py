import socket
import threading
import time
import logging
from config import BACKUP_SERVER_HOST, BACKUP_SERVER_PORT, PRIMARY_SERVER_HOST, PRIMARY_SERVER_PORT, HEARTBEAT_INTERVAL, ZERO_HOST

# Logging konfigurieren
logging.basicConfig(filename='chat.log', level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

clients = {}
clients_ip =[]
servers = {}
lock = threading.Lock()
ring=None
leader=PRIMARY_SERVER_HOST

def handle_client(conn, addr, join_msg):
    global clients_ip
    username = ""
    try:
        # Empfange erste Nachricht mit Benutzernamen
        print(join_msg)
        if join_msg.startswith("[JOIN] "):
            username = join_msg.split("[JOIN] ")[1].strip()
            with lock:
                clients[conn] = username
            clients_ip.append(addr)
            broadcast(f"[System] {username} ist dem Chat beigetreten.", conn,"client")
            broadcast(f"[CLIENT]{clients_ip}",conn, "server")
            print(f"{username} von {addr} verbunden.")

        while True:
            msg = conn.recv(1024).decode()
            if not msg:
                break
            print(f"{msg}")
            broadcast(msg, conn,"client")

    except Exception as e:
        logging.error(f"Fehler bei {addr}: {e}")
    finally: # Hier wird der Client die verbindung schließen.
        with lock:
             # Todo: wird nicht aufgerufen
            clients.pop(conn)
            broadcast(f"[System] {username} hat den Chat verlassen.", conn,"client")
        print(f"{username} getrennt.")
        clients_ip.remove(addr)
        conn.close()

def handle_server(conn, addr):
    global ring
    global leader
    global clients
    
    try:
        print("Backupserver möchte sich anschließen")
        print(addr[0])
        with lock:
            servers[conn]= addr[0]
            ring = form_ring(servers.values())
        print(f"Ring: {ring}")
        broadcast(f"[RING]{ring}[LEADER]{leader}[CLIENT]{list(clients.values())}",conn, "server")
    except Exception as e:
        logging.error(f"Fehler bei Server mit {addr}: {e}")
        print(e)




def broadcast(message, sender_conn, typ):
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

def heartbeat():
    while True:
        for conn in servers.keys():
            try:
                conn.send(b"[HEARTBEAT]")
            except Exception as e:
                conn.close()
        time.sleep(HEARTBEAT_INTERVAL)

def start_server():
    global servers
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((PRIMARY_SERVER_HOST, PRIMARY_SERVER_PORT))
    server.listen()
    print(servers)
    print(f"[START] Primärer Server läuft auf {PRIMARY_SERVER_HOST}:{PRIMARY_SERVER_PORT}")
    print("Primärer Server gestartet.")

    threading.Thread(target=heartbeat, daemon=True).start()

    while True:
        conn, addr = server.accept()
        join_msg = conn.recv(1024).decode()
        if join_msg.startswith("[JOIN] "):
            threading.Thread(target=handle_client, args=(conn, addr, join_msg), daemon=True).start()
        elif join_msg.startswith("[SERVER]"):
            threading.Thread(target=handle_server, args=(conn, addr), daemon=True).start()
            
# forms a ring out of the server List
def form_ring(members):
    sorted_binary_ring=sorted([socket.inet_aton(member)for member in members])
    sorted_ip_ring=[socket.inet_ntoa(node) for node in sorted_binary_ring]
    return sorted_ip_ring

if __name__ == "__main__":
    start_server()


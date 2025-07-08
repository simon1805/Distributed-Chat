import socket
import threading
import time
import logging
from config import  PRIMARY_SERVER_HOST, PRIMARY_SERVER_PORT, HEARTBEAT_INTERVAL

# Logging konfigurieren
logging.basicConfig(filename='chat.log', level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

clients = {}
clients_ip =[]
servers = {}
lock = threading.Lock()
ring=None
leader=PRIMARY_SERVER_HOST

# Hier wird jede Nachricht von dem Client behandelt
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
            logging.info(f"{username} from {addr} connected.")
            broadcast(f"[System] {username} has joined the chat.", conn, "client")
            broadcast(f"[CLIENT]{clients_ip}",conn, "server")
            print(f"{username} from {addr} connected.")

        while True:
            msg = conn.recv(1024).decode()
            if not msg:
                break
            print(f"{msg}")
            logging.info(msg)
            broadcast(msg, conn,"client")
            broadcast(f"[MESSAGE] {msg}", conn,"server")
            if msg.startswith("[LEAVE]"):
                with lock:
                    clients.pop(conn)
                broadcast(f"[System] {username} has left the chat.", conn, "client")
                clients_ip.remove(addr)
                broadcast(f"[CLIENT]{clients_ip}",conn, "server")
                conn.close()
                break
    except Exception as e:
        logging.error(f"Error on {addr}: {e}")
        
        
# Ein neuer Server wird hier dem System hinzugefügt
def handle_server(conn, addr):
    global ring
    global leader
    global clients_ip
    
    try:
        print("Backup server wants to join")
        print(addr[0])
        with lock:
            servers[conn]= addr[0]
            ring = form_ring(servers.values())
        print(f"Ring: {ring}")
        logging.info(f"Server {addr[0]} connected.")
        broadcast(f"[RING]{ring}[LEADER]{leader}[CLIENT]{clients_ip}",conn, "server")
    except Exception as e:
        logging.error(f"Error with server at {addr}: {e}")
        print(f"Error with server at {addr}: {e}")


# sendet eine Nachricht entweder zum Client oder Server
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
                    
# sendet eine Nachricht als heartbeat an die Server
def heartbeat():
    global ring
    while True:
        for conn in list(servers.keys()):
            try:
                conn.send(b"[HEARTBEAT]")
            except Exception as e:
                print(f"Heartbeat Error: {e}")
                conn.close()
                servers.pop(conn, None)
                ring = form_ring(servers.values())
                broadcast(f"[SERVER]{ring}",conn, "server")
        time.sleep(HEARTBEAT_INTERVAL)

# start des Servers
def start_server():
    global servers
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((PRIMARY_SERVER_HOST, PRIMARY_SERVER_PORT))
    server.listen()
    logging.info(f"[START] Primary server started on {PRIMARY_SERVER_HOST}:{PRIMARY_SERVER_PORT}")
    print(servers)
    print(f"[START] Primary server started on {PRIMARY_SERVER_HOST}:{PRIMARY_SERVER_PORT}")
    # hier wird jedem Server ein hearbeat gesendet um zu zeigen, dass der Server noch intakt ist
    threading.Thread(target=heartbeat, daemon=True).start()
    while True:
        conn, addr = server.accept()
        join_msg = conn.recv(1024).decode()
        if join_msg.startswith("[JOIN] "):
            threading.Thread(target=handle_client, args=(conn, addr, join_msg), daemon=True).start()
        elif join_msg.startswith("[SERVER]"):
            threading.Thread(target=handle_server, args=(conn, addr), daemon=True).start()
            print("Server Join")
            
# forms a ring out of the server List
def form_ring(members):
    sorted_binary_ring=sorted([socket.inet_aton(member)for member in members])
    sorted_ip_ring=[socket.inet_ntoa(node) for node in sorted_binary_ring]
    return sorted_ip_ring

if __name__ == "__main__":
    start_server()


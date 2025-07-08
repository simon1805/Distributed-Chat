import socket
import threading
import time
import logging
import json
import ast
from config import  PRIMARY_SERVER_HOST, PRIMARY_SERVER_PORT, HEARTBEAT_TIMEOUT, HEARTBEAT_INTERVAL,RING_PORT

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
message_thread = None
is_leader = False

# hier werden die reinkommenden Nachrichten behandelt
def monitor_message():
    global sock
    global ring
    global leader
    global last_heartbeat
    global client_ip
    global is_leader
    while not is_leader: #leader!=local_ip wenn unterschiedliches Gerät
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
                        ring=form_ring(ast.literal_eval(msg_ring))
                        logging.info(f"Received ring: {ring}, leader: {leader}, clients: {client_ip}")
                        print(f"Servers: {ring}")
                        print(f"Clients: {client_ip}")
                        print(f"Leader: {leader}")
                    # wenn ein neuer Client in das System eintritt
                    elif "[CLIENT]" in msg:
                        client_ip=ast.literal_eval(msg.split("[CLIENT]")[1])
                        logging.info(f"Clients changed: {client_ip}")
                        print(f"Client arrived/gone: {client_ip}")
                    elif "[SERVER]" in msg:
                        ring=form_ring(ast.literal_eval(msg.split("[SERVER]")[1]))
                        logging.info(f"Servers changed: {ring}")
                        print(f"Servers changed: {ring}")
                    elif "[MESSAGE]" in msg:
                        logging.info(msg.split("[MESSAGE]")[1])
                        print(msg.split("[MESSAGE]")[1])
                    # Heartbeat von dem Leader
                    elif "[HEARTBEAT]" in msg:
                        last_heartbeat = time.time()
            except Exception as e:
                print(f"[System] Message connection interrupted: {e}")
                time.sleep(2)

# Hier startet der Backupserver
def run_backup_server():
    global last_heartbeat
    global message_thread
    join_system()
    message_thread = threading.Thread(target=monitor_message, daemon=True)
    message_thread.start()
    while True:
        time.sleep(1)
        if time.time() - last_heartbeat > HEARTBEAT_TIMEOUT:
            print("[TAKEOVER] No heartbeat detected. Backup server is taking over.")
            logging.info("[TAKEOVER] No heartbeat detected. Backup server is taking over.")
            check_leader()
            break

# Entscheidung welcher Server übernimmt
def check_leader():
    global ring
    global local_ip
    global leader
    global is_leader
    # Use BACKUP_SERVER_HOST as the local server's IP
    logging.info(f"New leader is: {leader} ")
    if len(ring)> 1:
        start_lcr_election()
    if leader == local_ip :
        print("[INFO] This server is the leader.")
        leader = local_ip
        is_leader = True
        create_connections()
        return True
    else:
        print(f"[INFO] This server is NOT the leader. Leader IP: {leader}")
        return False

def create_connections():
    global sock
    global local_ip
    global servers
    global clients
    global leader
    print(sock)

    # Verbinde zu jedem Client im Ring
    for server_ip in ring:
        if server_ip != local_ip:  # Vermeide Verbindung zum eigenen Server
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((server_ip, PRIMARY_SERVER_PORT))
                print(f"[CONNECTION] Connected to server {server_ip}")
                message = f"[NEWSERVER][RING] {ring} [LEADER] {leader} [CLIENT] {list(clients.values())}"
                sock.send(message.encode())
                with lock:
                    servers[sock] = server_ip
                threading.Thread(target=handle_server, args=(sock, server_ip, f"{server_ip} Bereit"), daemon=True).start()
            except Exception as e:
                print(f"[ERROR] Connection to server {server_ip} failed: {e}")
    for client in client_ip:
        while True:
            try:
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.connect((client[0], PRIMARY_SERVER_PORT))
                print(f"[VERBINDUNG] Connected to client {client}")
                message = "[NEWSERVER]"
                client_socket.send(message.encode())
                with lock:
                    clients[client_socket] = client[0]
                threading.Thread(target=handle_client, args=(client_socket, client, f"{client} Bereit"), daemon=True).start()
                break
            except Exception as e:
                print(f"[FEHLER] Connection to Client {client} failed: {e}")
    start_server()

# Hier wird jede Nachricht von dem Client behandelt
def handle_client(conn, addr, join_msg):
    global client_ip
    
    print(f"Clients: {clients}")
    username = ""
    try:
        # Empfange erste Nachricht mit Benutzernamen
        print(join_msg)
        if join_msg.startswith("[JOIN] "):
            username = join_msg.split("[JOIN] ")[1].strip()
            with lock:
                clients[conn] = username
            client_ip.append(addr)
            broadcast(f"[System] {username} has joined the chat.", conn, "client")
            broadcast(f"[CLIENT]{client_ip}",conn, "server")
            print(f"{username} from {addr} connected.")
            logging.info(f"{username} from {addr} connected.")
            

        while True:
            msg = conn.recv(1024).decode()
            if not msg:
                break
            print(f"{msg}")
            broadcast(msg, conn,"client")
            broadcast(f"[MESSAGE] {msg}", conn,"server")
            logging.info(msg)
            if msg.startswith("[LEAVE]"):
                with lock:
                    clients.pop(conn)
                broadcast(f"[System] {username} has left the chat.", conn, "client")
                print(f"{username} disconnected.")
                client_ip.remove(addr)
                broadcast(f"[CLIENT]{client_ip}",conn, "server")
                conn.close()
                break
    except Exception as e:
        logging.error(f"Error on {addr}: {e}")

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
    global servers
    global local_ip
    global sock
    global message_thread
    
    
    #message_thread.join() 
    try:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()
    except:
        print(" Socket not closed.")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((local_ip, PRIMARY_SERVER_PORT))
    sock.listen() # Wait for the message monitoring thread to finish before starting the server
    print(f"[START] Primary server is running on {local_ip}:{PRIMARY_SERVER_PORT}")
    
    # hier wird jedem Server ein hearbeat gesendet um zu zeigen, dass der Server noch intakt ist
    threading.Thread(target=heartbeat, daemon=True).start()
    while True:
        print(f"Clients: {clients}")
        conn, addr = sock.accept()
        join_msg = conn.recv(1024).decode()
        if join_msg.startswith("[JOIN] "):
            threading.Thread(target=handle_client, args=(conn, addr, join_msg), daemon=True).start()
        elif join_msg.startswith("[SERVER]"):
            threading.Thread(target=handle_server, args=(conn, addr), daemon=True).start()
            print("Server Join")

def join_system():
    global sock
    global local_ip
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((PRIMARY_SERVER_HOST, PRIMARY_SERVER_PORT))
            local_ip=sock.getsockname()[0]
            sock.send("[SERVER]".encode())
            print("Server connected to the system")
            break
        except Exception as e:
            print(e)
            time.sleep(2)
    
# Ein neuer Server wird hier dem System hinzugefügt
def handle_server(conn, addr):
    global ring
    global leader
    global client_ip
    
    try:
        print("Backup server wants to join")
        print(addr[0])
        with lock:
            servers[conn]= addr[0]
            ring = form_ring(servers.values())
        print(f"Ring: {ring}")
        broadcast(f"[RING]{ring}[LEADER]{leader}[CLIENT]{client_ip}",conn, "server")
        logging.info(f"Server {addr[0]} connected.")
    except Exception as e:
        logging.error(f"Error with server at {addr}: {e}")
        print(e)
     
# forms a ring out of the server List
def form_ring(members):
    sorted_binary_ring=sorted([socket.inet_aton(member)for member in members])
    sorted_ip_ring=[socket.inet_ntoa(node) for node in sorted_binary_ring]
    return sorted_ip_ring
                  
# sendet eine Nachricht als heartbeat an die Server
def heartbeat():
    global servers
    global ring
    while True:
        for conn in servers.keys():
            try:
                conn.send(b"[HEARTBEAT]")
            except Exception as e:
                conn.close()
                servers.pop(conn, None)
                ring = form_ring(servers.values())
                broadcast(f"[SERVER]{ring}",conn, "server")  
        time.sleep(HEARTBEAT_INTERVAL)

def get_neighbour(ring, current_node_ip,direction="left"):
    current_node_index = ring.index(current_node_ip) if current_node_ip in ring else -1
    if current_node_index != -1:
        if direction == "left":
            if current_node_index +1 == len(ring):
                return ring[0]
            else:
                return ring[current_node_index + 1]
        else:
            if current_node_index == 0:
                return ring[len(ring)-1]
            else:
                return ring[current_node_index - 1]
    else:
        print(f"Node {current_node_ip} not found in the ring.")
        return None
     
def start_lcr_election():
    global ring
    global local_ip
    global leader
    participant = False
    leader_ip= ""
    ring_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ring_socket.bind((local_ip, RING_PORT))
    logging.info("Starting LCR Election")
    print("Node is up and running at {}:{}".format(local_ip, RING_PORT))
    time.sleep(4)

    # LCR Election Logic
    election_message={
        "mid": local_ip,
        "isLeader": False
        }
    
    ring_socket.sendto(json.dumps(election_message).encode(), get_neighbour(ring, local_ip, "left"))
    print("Election message sent to left neighbour: {}".format(get_neighbour(ring, local_ip, "left")))

    while leader_ip == "":
        try:
            buffer_size = 1024
            data, address = ring_socket.recvfrom(buffer_size)
            print("Received election message from {}: {}".format(address, data.decode()))
            election_message = json.loads(data.decode())
            if data !="":
                if election_message['isLeader']:
                    print("Leader found: {}".format(election_message['mid']))
                    leader_ip = election_message['mid']
                    # forward received election message to left neighbour
                    participant = False
                    ring_socket.sendto(json.dumps(election_message).encode(), get_neighbour(ring, local_ip, "left"))

                elif election_message['mid'] < local_ip and not participant:
                    print("Lower Ip found: {}".format(election_message['mid']))
                    new_election_message = {
                        "mid": local_ip,
                        "isLeader": False
                    }
                    participant = True
                    # send new election message to left neighbour
                    ring_socket.sendto(json.dumps(new_election_message).encode(), get_neighbour(ring, local_ip, "left"))

                elif election_message['mid'] > local_ip:
                    # send received election message to left neighbour
                    print("Higher Ip found: {}".format(election_message['mid']))
                    participant = True
                    ring_socket.sendto(json.dumps(election_message).encode(), get_neighbour(ring, local_ip, "left"))

                elif election_message['mid'] == local_ip:
                    print("Thats me! I am the leader now.")
                    leader_ip = local_ip
                    new_election_message = {
                        "mid": local_ip,
                        "isLeader": True
                    }
                    # send new election message to left neighbour
                    ring_socket.sendto(json.dumps(new_election_message).encode(), get_neighbour(ring, local_ip, "left"))
        except Exception as e:
            print("Error receiving data: {}".format(e))
    print("Election finished. Leader is: {}".format(leader_ip))
    leader = leader_ip
    ring_socket.close()
        
if __name__ == "__main__":
    run_backup_server()


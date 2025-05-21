import socket
import threading
import time
import logging
from config import BACKUP_SERVER_HOST, BACKUP_SERVER_PORT, PRIMARY_SERVER_HOST, PRIMARY_SERVER_PORT, HEARTBEAT_INTERVAL

# Logging konfigurieren
logging.basicConfig(filename='chat.log', level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

clients = {}
servers = {}
lock = threading.Lock()

def handle_client(conn, addr):
    username = ""
    try:
        # Empfange erste Nachricht mit Benutzernamen
        join_msg = conn.recv(1024).decode()
        if join_msg.startswith("[JOIN] "):
            username = join_msg.split("[JOIN] ")[1].strip()
            with lock:
                clients[conn] = username
            broadcast(f"[System] {username} ist dem Chat beigetreten.", conn)
            print(f"{username} von {addr} verbunden.")

        while True:
            msg = conn.recv(1024).decode()
            if not msg:
                break
            print(f"{msg}")
            broadcast(msg, conn)

    except Exception as e:
        logging.error(f"Fehler bei {addr}: {e}")
    finally: # Hier wird der Client die verbindung schließen.
        with lock:
             # Todo: wird nicht aufgerufen
            clients.pop(conn)
            broadcast(f"[System] {username} hat den Chat verlassen.", conn)
            print(f"{username} getrennt.")
        conn.close()

def handle_server():
    print("Hier")

def broadcast(message, sender_conn):
    with lock:
        for client in list(clients.keys()):
            if client != sender_conn:
                try:
                    client.send(message.encode())
                except:
                    client.close()
                    clients.pop(client, None)

def heartbeat():
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((BACKUP_SERVER_HOST, BACKUP_SERVER_PORT))
                s.send(b"HEARTBEAT")
        except:
            pass
        time.sleep(HEARTBEAT_INTERVAL)

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((PRIMARY_SERVER_HOST, PRIMARY_SERVER_PORT))
    server.listen()
    print(f"[START] Primärer Server läuft auf {PRIMARY_SERVER_HOST}:{PRIMARY_SERVER_PORT}")
    print("Primärer Server gestartet.")

    threading.Thread(target=heartbeat, daemon=True).start()

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    start_server()


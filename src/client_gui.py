import socket
import threading
import tkinter as tk
from tkinter import simpledialog, scrolledtext, messagebox
import time
from config import PRIMARY_SERVER_HOST, PRIMARY_SERVER_PORT

#python primary_server.py
#python backup_server.py
#python client_gui.py



class ChatClientGUI:
    no_server = False
    server_ip = PRIMARY_SERVER_HOST
    def __init__(self):
        self.server_ip=PRIMARY_SERVER_HOST
        self.sock = None
        self.username = ""
        self.window = tk.Tk()
        self.window.title("Distributed Chat Client")

        self.chat_area = scrolledtext.ScrolledText(self.window, state='disabled', height=20, width=50)
        self.chat_area.pack(padx=10, pady=5)

        self.msg_entry = tk.Entry(self.window, width=40)
        self.msg_entry.pack(side=tk.LEFT, padx=10, pady=5)
        self.msg_entry.bind("<Return>", self.send_message)

        self.send_button = tk.Button(self.window, text="Senden", command=self.send_message)
        self.send_button.pack(side=tk.LEFT, padx=5)

        self.prompt_username()
        self.connect_to_server()
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

        self.stop_event = threading.Event()
        self.receive_messages_thread = threading.Thread(target=self.receive_messages, daemon=True)
        self.receive_messages_thread.start()
        threading.Thread(target=self.listen_for_backup, daemon=True).start()
        self.window.mainloop()

    def listen_for_backup(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("", PRIMARY_SERVER_PORT))
        server.listen()
        while True:
            conn, addr = server.accept()
            msg = conn.recv(1024).decode()
            print(msg)
            if msg.startswith("[NEWSERVER]"):
                self.stop_event.set() 
                if self.sock:
                    try:
                        self.sock.shutdown(socket.SHUT_RDWR)
                        self.sock.close()
                    except:
                        pass
                    time.sleep(2)  # Give time for cleanup
                self.sock= conn
                self.server_ip=addr[0]
                self.stop_event.clear()
                self.receive_messages_thread = threading.Thread(target=self.receive_messages, daemon=True)
                self.receive_messages_thread.start()
        

    def prompt_username(self):
        self.username = simpledialog.askstring("Benutzername", "Gib deinen Benutzernamen ein:", parent=self.window)
        if not self.username:
            self.window.destroy()

    def connect_to_server(self):
        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                print("Connect to server ip:"+ self.server_ip)
                self.sock.connect((self.server_ip, PRIMARY_SERVER_PORT))
                print(self.sock)
                self.sock.send(f"[JOIN] {self.username}".encode())
                self.display_message("[System] Verbunden mit dem Server.")
                break
            except:
                self.display_message("[System] Server nicht erreichbar. Neuer Versuch in 2 Sekunden...")
                print("[System] Server nicht erreichbar. Neuer Versuch in 2 Sekunden...")

    def receive_messages(self):
        print("Start receiving messages")
        while not self.stop_event.is_set():
            try:
                msg = self.sock.recv(1024).decode()
                if msg:
                    self.display_message(msg)
            except:
                if self.stop_event.is_set():
                    break
                self.display_message("[System] Verbindung unterbrochen. Versuche erneut zu verbinden...")
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                    self.sock.close()
                except:
                    pass
                time.sleep(2)
                self.connect_to_server()

    def send_message(self, event=None):
        msg = self.msg_entry.get()
        print("Send message")
        if msg:
            try:
                self.sock.send(f"{self.username}: {msg}".encode())
                self.msg_entry.delete(0, tk.END)
                self.display_message("Ich:"+msg)
            except:
                messagebox.showerror("Fehler", "Nachricht konnte nicht gesendet werden.")

    def display_message(self, message):
        self.chat_area.config(state='normal')
        self.chat_area.insert(tk.END, message + "\n")
        self.chat_area.config(state='disabled')
        self.chat_area.see(tk.END)

    def on_close(self):
        if self.sock:
            try:
                self.sock.send(f"[LEAVE] {self.username}".encode())
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except:
                pass
        self.window.destroy()


if __name__ == "__main__":
    ChatClientGUI()





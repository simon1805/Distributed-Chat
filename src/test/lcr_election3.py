import socket
import json
import time

RING_PORT = 50020  # Beispielport, ggf. anpassen

def get_neighbour(ring, current_node_ip, direction="left"):
    current_node_index = ring.index(current_node_ip) if current_node_ip in ring else -1
    if current_node_index != -1:
        if direction == "left":
            if current_node_index + 1 == len(ring):
                return (ring[0], RING_PORT)
            else:
                return (ring[current_node_index + 1], RING_PORT)
        else:
            if current_node_index == 0:
                return (ring[len(ring)-1], RING_PORT)
            else:
                return (ring[current_node_index - 1], RING_PORT)
    else:
        print(f"Node {current_node_ip} not found in the ring.")
        return None

def start_lcr_election(local_ip, ring, timeout=10):
    """
    Startet den LCR-Election-Algorithmus.
    Gibt die IP des Leaders zurück.
    """
    participant = False
    leader_ip = ""
    ring_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ring_socket.settimeout(timeout)
    ring_socket.bind((local_ip, RING_PORT))
    print("Node is up and running at {}:{}".format(local_ip, RING_PORT))
    time.sleep(4)

    # Election-Message initial senden
    election_message = {
        "mid": local_ip,
        "isLeader": False
    }
    neighbour = get_neighbour(ring, local_ip, "left")
    ring_socket.sendto(json.dumps(election_message).encode(), neighbour)
    print("Election message sent to left neighbour: {}".format(neighbour))

    while leader_ip == "":
        try:
            buffer_size = 1024
            data, address = ring_socket.recvfrom(buffer_size)
            print("Received election message from {}: {}".format(address, data.decode()))
            election_message = json.loads(data.decode())
            if data != b"":
                if election_message['isLeader']:
                    print("Leader found: {}".format(election_message['mid']))
                    leader_ip = election_message['mid']
                    participant = False
                    ring_socket.sendto(json.dumps(election_message).encode(), get_neighbour(ring, local_ip, "left"))
                elif election_message['mid'] < local_ip and not participant:
                    print("Lower Ip found: {}".format(election_message['mid']))
                    new_election_message = {
                        "mid": local_ip,
                        "isLeader": False
                    }
                    participant = True
                    ring_socket.sendto(json.dumps(new_election_message).encode(), get_neighbour(ring, local_ip, "left"))
                elif election_message['mid'] > local_ip:
                    print("Higher Ip found: {}".format(election_message['mid']))
                    participant = True
                    ring_socket.sendto(json.dumps(election_message).encode(), get_neighbour(ring, local_ip, "left"))
                elif election_message['mid'] == local_ip:
                    print("That's me! I am the leader now.")
                    leader_ip = local_ip
                    new_election_message = {
                        "mid": local_ip,
                        "isLeader": True
                    }
                    ring_socket.sendto(json.dumps(new_election_message).encode(), get_neighbour(ring, local_ip, "left"))
        except Exception as e:
            print("Error during election process: {}".format(e))

    print("Election finished. Leader is: {}".format(leader_ip))
    ring_socket.close()
    return leader_ip

# Beispiel für manuellen Test
if __name__ == "__main__":
    # Beispielring (drei Knoten, IPs anpassen!)
    ring = ["127.0.0.1", "127.0.0.2", "127.0.0.3"]
    local_ip = "127.0.0.3"
    leader = start_lcr_election(local_ip, ring)
    print("Leader laut Election:", leader)
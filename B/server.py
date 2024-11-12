import socket
import threading
import struct
import random
import sys
import time

HELLO = 1
DATA = 2
ALIVE = 3
GOODBYE = 4

class ServerSession:
    def __init__(self, client_address, server_socket, session_id, server):
        self.client_address = client_address
        self.server_socket = server_socket
        self.session_id = session_id
        self.expected_sequence = 0
        self.active = True
        self.timer = None
        self.server = server

    def start(self):
        self.set_timer()

    def set_timer(self, timeout=20):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(timeout, self.issue_timeout)
        self.timer.start()

    def cancel_timer(self):
        if self.timer:
            self.timer.cancel()

    def issue_timeout(self):
        print(f"Session {hex(self.session_id)} timeout. Sending GOODBYE.")
        self.send_goodbye()
        self.active = False

    def handle_hello(self, seq_num):
        print(f"Session {hex(self.session_id)}: Received HELLO, responding with HELLO.")
        self.send_message(HELLO, seq_num)

    def handle_data(self, seq_num, payload, clock_value):
        print()
        print("Clock value", clock_value)
        
        if seq_num > self.expected_sequence:
            print(f"Session {hex(self.session_id)}: Lost packets! Expected {self.expected_sequence} but received {seq_num}.")
            self.expected_sequence = seq_num + 1
        elif seq_num < self.expected_sequence:
            print(f"Session {hex(self.session_id)}: Duplicate packet received, discarding.")
            return

        print(f"Session {hex(self.session_id)}: Received DATA: {payload.decode()}")
        self.expected_sequence += 1
        self.send_message(ALIVE, seq_num)

    def handle_goodbye(self):
        print(f"Session {hex(self.session_id)}: Received GOODBYE. Closing session.")
        self.send_goodbye()
        self.active = False

    def send_goodbye(self):
        self.send_message(GOODBYE, self.expected_sequence)
    
    def send_message(self, command, seq_num, data=None):
        current_clock_value = self.server.update_logical_clock()
        header = struct.pack("!HBBIIQ", 0xC461, 1, command, seq_num, self.session_id, current_clock_value)
        message = header + (data if data else b'')
        self.server_socket.sendto(message, self.client_address)

    def process_message(self, message):
        self.cancel_timer()  # Reset timer on message receipt
        self.set_timer()

        try:
            header = struct.unpack("!HBBIIQ", message[:20])
            magic, version, command, seq_num, session_id, received_logical_clock = header
            payload = message[20:] if len(message) > 20 else None

            if magic != 0xC461 or version != 1:
                print(f"Invalid packet received from {self.client_address}, discarding.")
                return

            if command == HELLO:
                self.handle_hello(seq_num)
            elif command == DATA:
                self.handle_data(seq_num, payload, received_logical_clock)
            elif command == GOODBYE:
                self.handle_goodbye()
        except struct.error as e:
            print(f"Error decoding message: {e}")
    
    def close(self):
        self.cancel_timer()
        self.send_goodbye()
        print(f"Session {hex(self.session_id)} closed.")


class UDPServer:
    def __init__(self, port):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_socket.bind(('', port))
        print(f"Server listening on port {port}...")
        self.sessions = {}
        self.lock = threading.Lock()
        self.logical_clock = 0
        self.clock_lock = threading.Lock()  # Lock for clock synchronization

    def update_logical_clock(self, received_clock=None):
        with self.clock_lock:
            if received_clock is not None and received_clock > self.logical_clock:
                self.logical_clock = received_clock + 1
            else:
                self.logical_clock += 1
            return self.logical_clock
            
    def handle_client(self, message, client_address):
        try:
            # Unpack the message header
            header = struct.unpack("!HBBIIQ", message[:20])
            magic, version, command, seq_num, session_id, received_clock_value = header
        except struct.error:
            print("Malformed message received. Ignoring.")
            return
        self.update_logical_clock(received_clock_value)
        
        with self.lock:
            session = self.sessions.get(session_id)

            # Check if the session already exists and is from a different client
            if session and session.client_address != client_address:
                print(f"Session {hex(session_id)} already in use by another client {session.client_address}. Rejecting {client_address}.")
                self.update_logical_clock()
                self.send_rejection(client_address, session_id)
                return

            # If no session exists or it's the same client, proceed
            if not session:
                if command == HELLO:
                    print(f"New session {hex(session_id)} from {client_address}.")
                    session = ServerSession(client_address, self.server_socket, session_id, self)
                    self.sessions[session_id] = session
                    session.start()
                else:
                    print(f"Session {hex(session_id)} not found for client {client_address}. Ignoring.")
                    return
            
            # Process the message with the session
            session.process_message(message)

            # If the session is no longer active, remove it
            if not session.active:
                del self.sessions[session_id]

    def send_rejection(self, client_address, session_id):
        # Construct and send a rejection message to the client
        # For example, you could send a special command or error code
        rejection_message = f"Session ID {hex(session_id)} is already in use. Connection rejected.".encode()
        self.server_socket.sendto(rejection_message, client_address)

    def run(self):
        while True:
            try:
                message, client_address = self.server_socket.recvfrom(1024)
                threading.Thread(target=self.handle_client, args=(message, client_address)).start()
            except ConnectionResetError:
                print(f"Connection reset by {client_address}. Ignoring and continuing.")
                continue  # Keep the server running after the error
            except KeyboardInterrupt:
                print("Server shutting down.")
                break



def get_server_args():
    if len(sys.argv) != 2:
        print("Usage: python server.py <portnum>")
        sys.exit(1)
    port = int(sys.argv[1])
    return port


if __name__ == '__main__':
    port = get_server_args()
    server = UDPServer(port)
    server.run()
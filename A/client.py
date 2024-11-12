import sys
import random
import threading
import struct
import socket
import select

HELLO = 1
DATA = 2
ALIVE = 3
GOODBYE = 4

def get_command_line_args():
    if len(sys.argv) != 3:
        sys.exit("Expected command line args: server_host port_number")
    server_host = sys.argv[1]
    try:
        port_num = int(sys.argv[2])
    except ValueError as e:
        sys.exit(f"Error: {e}.\nPlease enter a valid integer.")
    return server_host, port_num

class Client:

    def __init__(self, server_host, server_port):
        self.magic_number = int('0xC461', 16)  # Magic number as integer
        self.version = 1              
        self.sequence_number = 0
        self.session_id = random.randint(0, 4294967295)  # Ensure within range for 4-byte unsigned int
        self.timeout = 8  # seconds
        self.logical_clock = 0  # 64-bit unsigned logical clock
        self.clock_lock = threading.Lock()  # Lock for clock synchronization
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP socket
        self.server_host = server_host
        self.server_port = server_port
        self.idle_timer = None
        self.shutdown_event = threading.Event()
        self.client_socket.settimeout(self.timeout)

    def update_logical_clock(self, new_value=None):
        with self.clock_lock:
            if new_value is not None:
                if new_value > self.logical_clock:
                    self.logical_clock = new_value + 1
                else:
                    self.logical_clock += 1
            else:
                self.logical_clock += 1
            return self.logical_clock

    def issue_timeout(self):
        print(f"Idle time of {self.timeout} seconds expired.")
        self.send_message(GOODBYE) # send message will update the logical clock value 
        self.shutdown_event.set()

    def set_timer(self):
        self.idle_timer = threading.Timer(self.timeout, self.issue_timeout)
        self.idle_timer.start()
    
    def cancel_timer(self):
        if self.idle_timer is not None:
            self.idle_timer.cancel()
            self.idle_timer = None

    def send_message(self, command, data=None):
        # Lock the clock before reading and updating
        logical_clock_value = self.update_logical_clock()
        
        header = struct.pack("!HBBIIQ", self.magic_number, self.version, command, self.sequence_number, self.session_id, logical_clock_value)
        if data is not None:
            message = header + data
        else:
            message = header
        self.client_socket.sendto(message, (self.server_host, self.server_port))
        self.sequence_number += 1
        print(f"Sent: Command={command}, Data={data}, Logical Clock={logical_clock_value}")
        if command == GOODBYE:
            print("Sending GOODBYE from client. Closing client.")
            self.shutdown_event.set()

    def decode_message(self, message):
        try:
            header = struct.unpack("!HBBIIQ", message[:20])  # Added 8 bytes for 64-bit logical clock
            magic_number, version, command, sequence_number, session_id, logical_clock_value = header
            payload = message[20:]  # The rest of the message is payload if any

            print(f"Received Message: Magic Number={hex(magic_number)}, Version={version}, Command={command}, Sequence Number={sequence_number}, Session ID={session_id}, Logical Clock={logical_clock_value}, Payload={payload.decode() if payload else 'None'}")

            return command, logical_clock_value  # Return command to check in receive_message

        except struct.error as e:
            print(f"Struct error: {e}")
            self.shutdown_event.set()

    def receive_message(self):
        while not self.shutdown_event.is_set():
            try:
                response, _ = self.client_socket.recvfrom(1024)  # Buffer size is 1024 bytes
                self.cancel_timer()
                command, received_clock_value = self.decode_message(response)
                self.update_logical_clock(received_clock_value)

                if command == GOODBYE:  # Check if the response command is GOODBYE
                    print("Received GOODBYE from server. Closing client.")
                    self.shutdown_event.set()

            except socket.timeout:
                print("Receive timeout occurred.")
                self.issue_timeout()

    def handle_input(self):
        if sys.stdin.isatty():
            print("Enter data to send to the server (type 'q' to quit):")
            while not self.shutdown_event.is_set():
                # Use select to wait for input on stdin or until the shutdown event is set
                rlist, _, _ = select.select([sys.stdin], [], [], 1)  # Timeout of 1 second to allow periodic checks
                if rlist:  # There's input available in stdin
                    line = sys.stdin.readline().strip()
                    self.update_logical_clock()

                    if line == 'q' or line == 'eof':
                        self.update_logical_clock()

                        print("Exiting...")
                        self.shutdown_event.set()  # Signal to shut down the client
                    elif line:
                        print()
                        print(f"Sending data: {line}")
                        self.send_message(DATA, line.encode())
                        self.set_timer()  # Set the idle timer to trigger timeout
                elif self.shutdown_event.is_set():
                    break  # Exit loop if shutdown event is triggered
        else:
            # If stdin is redirected (e.g., from a file), handle it here
            for line in sys.stdin:
                line = line.strip()
                if line:
                    print()
                    print(f"Sending data: {line}")
                    self.send_message(DATA, line.encode())
                    self.set_timer()
            

        # Ensure GOODBYE is sent before shutdown
        if not self.shutdown_event.is_set():
            self.send_message(GOODBYE)

    def run(self):
        print("Hello from client...to server")
        self.send_message(HELLO)
        self.update_logical_clock()

        self.set_timer()
        try:
            response, _ = self.client_socket.recvfrom(1024)  # Buffer size is 1024 bytes
            self.cancel_timer()
            command, _ = self.decode_message(response)
            self.update_logical_clock()
            print("HELLO = ", HELLO)
            if command != HELLO:  # Check if the response command is not hello
                print("Did not receive hello from server. Closing client.")
                sys.exit(1)
            else:
                print("Received hello from server.")
        except socket.timeout:
            print("Receive timeout occurred.")
            self.issue_timeout()
        
        # Start the threads for handling input and receiving messages
        input_thread = threading.Thread(target=self.handle_input, daemon=True)
        receive_thread = threading.Thread(target=self.receive_message, daemon=True)
        input_thread.start()
        receive_thread.start()

        # Wait for shutdown event
        self.shutdown_event.wait()

        self.client_socket.close()

if __name__ == '__main__':
    server_host, port_num = get_command_line_args()
    client_session = Client(server_host, port_num)
    client_session.run()
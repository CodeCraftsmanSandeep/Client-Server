import sys
import asyncio
import struct
import threading

HELLO = 1
DATA = 2
ALIVE = 3
GOODBYE = 4

class ServerSession:
    def __init__(self, server, client_address, session_id, initial_sequence_number):
        self.server = server  # Reference to the main server
        self.client_address = client_address
        self.session_id = session_id
        self.expected_sequence_number = initial_sequence_number + 1
        self.state = "WAIT_FOR_HELLO"
        self.idle_timer = None
        self.timeout = 20  # Timeout for inactivity

    async def set_timer(self):
        self.cancel_timer()  # Cancel any existing timer first
        self.idle_timer = asyncio.create_task(self.session_timeout())

    def cancel_timer(self):
        if self.idle_timer:
            self.idle_timer.cancel()
            self.idle_timer = None

    async def session_timeout(self):
        await asyncio.sleep(self.timeout)
        print(f"Session timeout for {self.client_address}, sending GOODBYE.")
        await self.send_message(GOODBYE)
        self.state = "DONE"
        self.terminate()

    async def send_message(self, command, sequence_number=0, data=None):
        # Update logical clock and use lock for synchronization
        logical_clock_value = self.server.update_logical_clock()

        header = struct.pack("!HBBIIQ", 0xC461, 1, command, sequence_number, self.session_id, logical_clock_value)
        if data:
            message = header + data
        else:
            message = header
        self.server.transport.sendto(message, self.client_address)

    async def handle_hello(self, sequence_number):
        if self.state == "WAIT_FOR_HELLO":
            print(f"Received HELLO from {self.client_address}, session {self.session_id}")
            await self.send_message(HELLO, sequence_number)
            self.state = "RECEIVE"
            await self.set_timer()
        else:
            print(f"Protocol error: HELLO received in state {self.state}")
            await self.send_message(GOODBYE)
            self.state = "DONE"
            self.terminate()

    async def handle_data(self, sequence_number, data, received_logical_clock):
        if self.state == "RECEIVE":
            # Update server's logical clock based on the received value
            self.server.update_logical_clock(received_logical_clock)

            if sequence_number == self.expected_sequence_number:
                print(f"Received DATA from {self.client_address}: {data.decode()}")
                self.expected_sequence_number += 1
                await self.send_message(ALIVE, sequence_number)
                await self.set_timer()  # Reset the timer
            elif sequence_number > self.expected_sequence_number:
                for i in range(self.expected_sequence_number, sequence_number):
                    print(f"Lost packet {i} from {self.client_address}")
                self.expected_sequence_number = sequence_number + 1

                print(f"Received DATA from {self.client_address}: {data.decode()}")
                await self.send_message(ALIVE, sequence_number)
            elif sequence_number == self.expected_sequence_number - 1:
                print(f"Duplicate packet {sequence_number} received from {self.client_address}. Discarding.")
            else:
                print(f"Protocol error: Sequence number out of order from {self.client_address}.")
                await self.send_message(GOODBYE)
                self.state = "DONE"
                self.terminate()

    async def handle_goodbye(self):
        if self.state == "RECEIVE":
            print(f"Received GOODBYE from {self.client_address}, closing session.")
            await self.send_message(GOODBYE)
            self.state = "DONE"
            self.terminate()

    def terminate(self):
        print(f"Session with {self.client_address} terminated.")
        self.cancel_timer()
        # Remove this session from the server's session list
        del self.server.sessions[self.session_id]

    async def handle_message(self, message):
        header = message[:20]
        magic_number, version, command, sequence_number, session_id, received_logical_clock = struct.unpack("!HBBIIQ", header)
        if magic_number != 0xC461 or version != 1:
            print(f"Protocol error: Invalid message from {self.client_address}")
            await self.send_message(GOODBYE)
            self.state = "DONE"
            self.terminate()
            return
        
        if session_id != self.session_id:
            print(f"Protocol error: Invalid session id from {self.client_address}")
            await self.send_message(GOODBYE)
            self.state = "DONE"
            self.terminate()
            return

        if command == HELLO:
            await self.handle_hello(sequence_number)
        elif command == DATA:
            data = message[20:]
            await self.handle_data(sequence_number, data, received_logical_clock)
        elif command == GOODBYE:
            await self.handle_goodbye()
        else:
            print(f"Protocol error: Unknown command from {self.client_address}")
            await self.send_message(GOODBYE)
            self.state = "DONE"
            self.terminate()

class UDPServerProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        self.sessions = {}  # Stores active sessions by session_id
        self.client_addresses = {}  # Stores the address of clients by session_id
        self.logical_clock = 0  # 64-bit unsigned logical clock
        self.clock_lock = threading.Lock()  # Lock for synchronization

    def update_logical_clock(self, received_clock=None):
        with self.clock_lock:
            if received_clock is not None and received_clock > self.logical_clock:
                self.logical_clock = received_clock + 1
            else:
                self.logical_clock += 1
            return self.logical_clock

    def connection_made(self, transport):
        self.transport = transport
        print("Server is up and listening for clients...")

    def datagram_received(self, data, addr):
        try:
            session_id = struct.unpack("!I", data[8:12])[0]  # Extract session_id from message
            sequence_number = struct.unpack("!I", data[4:8])[0]
            command = struct.unpack("!B", data[3:4])[0]

            if session_id in self.sessions:
                # Ensure the client address matches the one for this session
                if addr == self.client_addresses[session_id]:
                    asyncio.create_task(self.sessions[session_id].handle_message(data))
                else:
                    print(f"Ignoring client {addr} with duplicate session ID {session_id}.")
            else:
                # Check if the HELLO message starts a new session
                if command == HELLO:
                    new_session = ServerSession(self, addr, session_id, sequence_number)
                    self.sessions[session_id] = new_session
                    self.client_addresses[session_id] = addr  # Store client address for this session
                    asyncio.create_task(new_session.handle_message(data))
                else:
                    print(f"Invalid initial message from {addr}, expected HELLO.")
        except struct.error as e:
            print(f"Struct error: {e}")

async def main():
    # Retrieve port number from command-line arguments
    if len(sys.argv) != 2:
        print("Usage: python asyncio_server.py <port_number>")
        sys.exit(1)

    port = int(sys.argv[1])

    loop = asyncio.get_running_loop()
    
    # Set up the UDP server to only listen on localhost (127.0.0.1)
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDPServerProtocol(),
        local_addr=('127.0.0.1', port))

    print(f"Server is listening on localhost (127.0.0.1) and port {port}")

    try:
        await asyncio.sleep(3600)  # Run for 1 hour
    finally:
        transport.close()

if __name__ == '__main__':
    asyncio.run(main())
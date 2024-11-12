import sys
import asyncio
import struct
import random
import socket

HELLO = 1
DATA = 2
ALIVE = 3
GOODBYE = 4

class AsyncUDPClient:
    def __init__(self, server_host, server_port):
        self.server_host = server_host
        self.server_port = server_port
        self.session_id = random.randint(0, 4294967295)
        self.sequence_number = 0
        self.transport = None
        self.logical_clock = 0 # initialized to zero

    def update_logical_clock(self, new_value=None):
        if new_value is not None:
            if new_value > self.logical_clock:
                self.logical_clock = new_value + 1
            else:
                self.logical_clock += 1
        else:
            self.logical_clock += 1
        return self.logical_clock
        
    def connection_made(self, transport):
        self.transport = transport
        print(f"Connected to {self.server_host}:{self.server_port}")
        # Send the initial HELLO message
        asyncio.create_task(self.send_message(HELLO))

    def datagram_received(self, data, addr):
        print()
        asyncio.create_task(self.handle_response(data))

    def error_received(self, exc):
        print(f"Error received: {exc}")

    def connection_lost(self, exc):
        print("Connection closed")
        asyncio.get_event_loop().stop()
        # pass

    async def send_message(self, command, data=None):
        """Send a message to the server."""

        header = struct.pack("!HBBIIQ", 0xC461, 1, command, self.sequence_number, self.session_id, self.logical_clock)
        message = header + (data if data else b'')
        self.transport.sendto(message, (self.server_host, self.server_port))
        print(f"Sent message with command {command} and sequence number {self.sequence_number}")
        self.sequence_number += 1
        self.update_logical_clock()

    async def handle_response(self, message):
        """Handle the response received from the server."""
        header = message[:20]
        magic_number, version, command, sequence_number, session_id, received_clock_value = struct.unpack("!HBBIIQ", header)
        self.update_logical_clock(received_clock_value)

        payload = message[20:] if len(message) > 20 else b''

        if magic_number != 0xC461 or version != 1:
            print("Protocol error: Invalid magic number or version.")
            return

        if session_id != self.session_id:
            print("Protocol error: Invalid session ID.")
            return

        if command == ALIVE:
            print(f"Received ALIVE from server, clock: {received_clock_value}. Sequence number: {sequence_number}")
        elif command == GOODBYE:
            print("Received GOODBYE from server, clock: {received_clock_value}. Closing connection.")
            self.transport.close()
        else:
            print(f"Received message with command {command} and sequence number {sequence_number}, clock: {received_clock_value}")
            if payload:
                print(f"Payload: {payload.decode()}")

    async def send_data(self, data):
        """Send data messages."""
        await self.send_message(DATA, data.encode())
        await asyncio.sleep(0.1)

    async def handle_user_input(self):
        """Handle user input to send data to the server."""
        print("Enter data to send to the server (type 'q' to quit):")
        while True:
            # Read input from stdin asynchronously
            data = await asyncio.get_event_loop().run_in_executor(None, input, "")
            self.update_logical_clock()

            if data == 'q' or data == 'eof':
                break
            if data:
                await self.send_data(data)

        # Send the GOODBYE message to terminate the session
        await self.send_message(GOODBYE)

    async def start(self):
        """Start the client and handle communication."""
        loop = asyncio.get_running_loop()
        # Create a UDP connection to the server
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: self,
            remote_addr=(self.server_host, self.server_port)
        )

        self.transport = transport

        try:
            # Start handling user input and communication
            await self.handle_user_input()
        finally:
            transport.close()

async def main():
    # Retrieve server host and port from command-line arguments
    if len(sys.argv) != 3:
        print("Usage: python asyncio_client.py <server_host> <server_port>")
        sys.exit(1)

    server_host = sys.argv[1]
    server_host = socket.gethostbyname(server_host)
    server_port = int(sys.argv[2])

    # Create and start the client
    client = AsyncUDPClient(server_host, server_port)
    await client.start()

if __name__ == '__main__':
    asyncio.run(main())
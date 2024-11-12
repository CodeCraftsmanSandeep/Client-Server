# UDP Client-Server Application

This repository contains an implementation of a custom UDP-based protocol for client-server communication. The application uses both **thread-based** and **non-blocking I/O (event-loop)** approaches, providing hands-on experience with concurrency and protocol design over UDP. The protocol, named **UDP Application Protocol (UAP)**, supports sessions and custom message types.

## Features
- **UDP Communication**: The application uses UDP for low-latency, connectionless communication.
- **Custom Protocol (UAP)**: Implements a header-based protocol that defines message types, session management, and state-based handling.
- **Concurrency**:
  - **Thread-based Approach**: Uses multiple threads for handling concurrent client-server communication.
  - **Non-blocking/Event-loop Approach**: Implements a single-threaded, asynchronous I/O model.
- **Message Types**: Includes `HELLO`, `DATA`, `ALIVE`, and `GOODBYE` messages for client-server interaction.
- **Session Management**: Maintains sessions for each client, including tracking sequence numbers and managing logical clocks for event ordering.
- **Error Handling**: Detects lost and duplicate packets and implements a timeout mechanism to handle inactive clients.

## Protocol Overview
The custom UDP Application Protocol (UAP) operates over UDP and has the following structure:
1. **Message Header**: Contains a "magic number," version, command, sequence number, session ID, and a logical clock.
2. **Message Types**:
   - **HELLO**: Initializes a session.
   - **DATA**: Transmits data from client to server.
   - **ALIVE**: Sent by the server to confirm the session is active.
   - **GOODBYE**: Closes the session.
3. **Session and State Management**: Each session has unique identifiers and handles state transitions. Lost or duplicate packets are logged.

## Usage

### Installation
Ensure you have a C++ compiler (or Java/Python/Node.js, depending on your implementation) that supports thread-based and asynchronous I/O features.

### Run the Server
To start the server:
```bash
./server <portnum>
```
- `<portnum>`: The port number to which the server binds.

### Run the Client
To start the client:
```bash
./client <hostname> <portnum>
```
- `<hostname>`: Server’s hostname or IP address.
- `<portnum>`: The port on which the server is listening.

### Example Commands
1. Run the server on port `1234`:
   ```bash
   ./server 1234
   ```
2. Run the client and connect to the server:
   ```bash
   ./client localhost 1234
   ```

## Output
- **Client Output**: Messages sent and received, including sequence numbers and responses.
- **Server Output**: Logs of received messages, session creation, and termination messages. Detects lost and duplicate packets based on sequence numbers.

## Concurrency Handling
The server can handle multiple clients using two concurrency approaches:
- **Thread-based**: Separate threads manage different sessions.
- **Non-blocking I/O (Event-loop)**: Uses a single-threaded event-driven approach.

## Files
- **client.py**: Client code implementing the protocol.
- **server.py**: Server code handling message processing and session management.

## Testing
1. **Basic Testing**: Run a client instance and send data to the server.
2. **Concurrent Clients**: Use shell scripts to start multiple clients and test concurrency.
3. **Packet Loss Simulation**: Test with large inputs to simulate packet loss.

# How does network programming solve data exchange between processes?

## 1. The problem: two processes do not share application memory

Suppose process A is running the order placement UI, while process B processes orders. A needs to send a “create order” request, and B needs to return the order ID and status. Each process has its own address space and its own lifecycle, so A cannot directly grab a Java object residing in B's heap and invoke a method on that object as when both are in the same JVM.

**Network programming** solves this by turning information into data transmitted over an agreed communication channel. The sending process writes data to a **socket**; the operating system and network protocol stack deliver the data to the receiving process's socket; the receiving process reads, decodes, processes, and may send a response.

The destination can be on the **same machine** (via the loopback address) or on **another machine** on a LAN/the Internet. “Network programming” is not synonymous with “calling out to the Internet”; the core idea is exchanging messages between processes through network endpoints.

Example business flow:

~~~text
Process A (client)                     Process B (server)
   create-order request ── bytes ──────> read and decode
   wait for result                       process business logic
   read and decode <────── bytes ─────── return order ID/status
~~~

Key point: **objects, method calls, and memory state do not travel across the network on their own**. Both sides exchange bytes according to a format/protocol that both understand.

## 2. Components that help processes find and talk to each other

| Component | Role |
| --- | --- |
| **Process** | An independent program that sends or receives data, such as a Java application and an order-processing service. |
| **IP address** | Identifies an interface/destination at the network layer; can be IPv4 or IPv6. |
| **Port** | An integer in the range 0–65535 that helps the transport layer deliver data to the right service/socket on the target machine. |
| **Transport protocol** | TCP or UDP, specifying how bytes/datagrams are transmitted and the associated guarantees. |
| **Socket** | The programming interface a process uses to connect, send, and receive data through the operating system. |
| **Application protocol** | Defines the meaning of the data: what commands, what format, when a message ends, and how responses are structured. |

For example, a TCP service listening at **127.0.0.1:5050**: 127.0.0.1 is the IPv4 loopback address (the current machine), and 5050 is the service port. A client connects to that address. In TCP, an active connection is distinguished by the pair of IP addresses and ports of **both ends** along with the transport protocol; multiple clients can connect to the same listening port thanks to different client-side endpoints.

A domain name like api.example.com must be resolved to an IP address (typically via DNS) before connecting. Knowing the IP and port is still not enough: network routing, firewalls, a running server, and compatible protocols on both sides are all required.

## 3. How does data travel from one process to another?

Looking at each layer's responsibility:

~~~text
Application A
  business data -> encode/frame into bytes
      |
      v
  Operating system Socket API
      |
  TCP or UDP (transport, port)
      |
  IP (addressing and routing)
      |
  physical/virtual network or loopback
      |
  IP -> TCP or UDP -> B's socket
      |
      v
Application B
  read bytes -> extract message -> decode -> process
~~~

1. **Application prepares content:** a string, JSON, binary record, or HTTP resource is encoded into bytes; Unicode should have an explicit encoding convention, typically UTF-8.
2. **Application writes to the socket:** for example, Java uses an OutputStream. Calling write or flush primarily moves data through the respective buffers; **it does not prove the receiver has processed it successfully**.
3. **Operating system transports it:** TCP may split/coalesce data into multiple segments; IP routes packets according to the destination address; the network/loopback delivers them to the receiving system.
4. **Operating system receives and demultiplexes:** the transport layer identifies the socket by address, port, protocol, and connection state, then delivers the data to the process owning the matching socket.
5. **Receiving application reads and interprets the data:** for example, reading a complete message, validating it, executing business logic, and sending a response.

Sockets hide the details of network hardware, but **they do not automatically define the structure and meaning of application data**. The two programs still have to agree on a protocol.

## 4. The client–server model with TCP

The **server** opens a port and waits for connections; the **client** actively initiates the connection. With Java blocking I/O, the typical sequence is:

1. The server creates a ServerSocket, **binds** to an address/port, and **listens**. The port must not already be occupied by another service and must be permitted for access.
2. The server calls accept(), waiting for a client to connect. accept() returns a **new Socket for that connection**; the ServerSocket remains the listening socket.
3. The client uses Socket.connect(...) targeting the server's address/port. TCP establishes the connection before either side exchanges application bytes.
4. Both ends obtain an InputStream and an OutputStream; each end can both send and receive (**full-duplex**).
5. The client sends **one complete message** according to the convention, for example the string PING terminated by a newline character.
6. The server reads the complete message, validates/interprets it, processes it, and sends PONG. The client reads the response.
7. Both sides handle errors, end the session, and close resources. try-with-resources ensures sockets/streams are closed when leaving scope.

TCP provides an **ordered byte stream with retransmission when needed while the connection is active**, along with flow control and congestion control. However, it does not know where “an order” starts or ends and cannot guarantee that a business transaction has been committed. The connection can drop between sending a request and receiving the response, leaving the client unsure whether the server processed it.

## 5. Distinguishing a byte stream from a message

This is a very common conceptual mistake. With TCP:

- Writing 100 bytes once **does not mean** the receiver will read all 100 bytes on the first read() call. Data can arrive in chunks, or multiple writes can be read together.
- read() can return fewer bytes than requested; when the stream ends cleanly, read() returns -1. Therefore, message-reading code must loop until enough bytes or a terminator is reached.
- You should not use “until no more data is currently in the buffer” as the end of a message; more data may still be in flight.

An **application protocol** typically chooses one of the following framing styles:

| Framing method | When it fits | Risks to handle |
| --- | --- | --- |
| **Delimiter** (e.g., LF at end of line) | Short text commands like PING | Payloads containing LF must be escaped/restricted; enforce a line-length limit. |
| **Length prefix** (e.g., 4-byte length + payload) | JSON, binary data, custom protocols | Validate the length before allocating/reading; read the exact full payload. |
| **Standard protocol** (HTTP, WebSocket, gRPC, ...) | APIs and systems with multiple participants | Follow the framing, status, version, limits, and security rules of the chosen protocol. |

Besides framing, both sides must agree on **encoding** (UTF-8), **structure** (e.g., JSON), **semantics** (PING/PONG, request/response), **versioning**, **error handling**, and **size limits**. This example uses **one UTF-8 line per message** to make the mechanism clear.

## 6. Java 17+ example: two real processes communicating over TCP

Create the two files below in the same directory. The server binds only to **loopback** for safe practice on a single machine. The program serves only **one** client and then exits, keeping the focus on the data flow rather than a multi-connection server architecture.

**File TcpServer.java**

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpServer {
    private static final int PORT = 5050;

    public static void main(String[] args) throws IOException {
        try (ServerSocket listener =
                     new ServerSocket(PORT, 50, InetAddress.getLoopbackAddress())) {
            System.out.println("Server ready on port 5050 (loopback)");
            try (Socket socket = listener.accept()) {
                socket.setSoTimeout(5000);
                try (BufferedReader in = new BufferedReader(
                             new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
                     BufferedWriter out = new BufferedWriter(
                             new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8))) {
                    String request = in.readLine();
                    if (request == null) {
                        System.out.println("Client closed before sending a request");
                        return;
                    }
                    System.out.println("Server received: " + request);
                    String response = "PING".equals(request) ? "PONG" : "ERROR";
                    out.write(response);
                    out.newLine();
                    out.flush();
                    System.out.println("Server replied: " + response);
                }
            }
        }
    }
}
~~~

**File TcpClient.java**

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpClient {
    public static void main(String[] args) throws IOException {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(InetAddress.getLoopbackAddress(), 5050), 3000);
            socket.setSoTimeout(5000);
            try (BufferedReader in = new BufferedReader(
                         new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
                 BufferedWriter out = new BufferedWriter(
                         new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8))) {
                out.write("PING");
                out.newLine();
                out.flush();
                System.out.println("Client sent: PING");
                String response = in.readLine();
                if (response == null) {
                    throw new EOFException("Server closed without a response");
                }
                System.out.println("Client received: " + response);
            }
        }
    }
}
~~~

**Compile and run** (requires JDK 17 or newer):

~~~sh
javac --release 17 -encoding UTF-8 TcpServer.java TcpClient.java
~~~

In terminal 1, run first:

~~~sh
java TcpServer
~~~

While the server is waiting at accept(), open terminal 2 and run:

~~~sh
java TcpClient
~~~

**Expected stdout, server terminal:**

~~~text
Server ready on port 5050 (loopback)
Server received: PING
Server replied: PONG
~~~

**Expected stdout, client terminal:**

~~~text
Client sent: PING
Client received: PONG
~~~

Lines across the two terminals may interleave depending on OS scheduling, but **the order within each terminal** on a successful run is as shown above. This sample has been verified to compile in Java 17 mode and successfully run the PING/PONG exchange.

**Exact explanation of what just happened:**

- new ServerSocket(..., InetAddress.getLoopbackAddress()) opens port 5050 only on the loopback address. Access from other machines is not permitted through this bind point.
- accept() returns the Socket for the client session; the client connects using an InetSocketAddress with the same address/port. The two independent processes can run in two separate JVMs/terminals.
- OutputStreamWriter encodes characters into UTF-8; BufferedWriter buffers data before flush(). newLine() writes the delimiter; readLine() reads up to the end of the line and strips the line terminator.
- The server receives PING, applies the application rule, and sends PONG. TCP transfers bytes, while **the Java program decides what PING and PONG mean**.
- connect(..., 3000) sets a maximum connection timeout of 3 seconds; setSoTimeout(5000) limits the blocking time of a socket read operation to 5 seconds. They do **not** automatically limit total execution time or the wait time at ServerSocket.accept().
- Closing streams/sockets with try-with-resources releases resources. In this demo, the server stops after one connection and does not restart automatically.

If a BindException occurs, port 5050 may already be in use by another process; change to **the same port number** in both files. If a ConnectException occurs, check that the server is running and that the address/port match. If the client runs before the server, the connection may be refused; that is not a Java syntax error.

## 7. TCP and UDP: two different transport choices

| Criterion | TCP | UDP |
| --- | --- | --- |
| Exchange model | Connection-oriented, continuous **byte stream** | Independent **datagrams**, preserving datagram boundaries in the API |
| Transport-layer guarantees | Bytes arrive in order without duplicates in the stream while the connection is active | No guarantee that datagrams arrive, arrive in order, or arrive only once |
| Setup | Must establish a connection | No TCP-style connection handshake required |
| Overhead/latency | Has handshake, connection state, and control mechanisms | Sending datagrams is simpler; does not mean it is always faster under all conditions |
| Typical Java APIs | Socket, ServerSocket; SocketChannel, ServerSocketChannel | DatagramSocket/DatagramPacket; DatagramChannel |
| Common examples | Transactional APIs, file transfer, HTTP/1.1 and HTTP/2 over TCP | Traditional DNS, some real-time streams, service discovery |

**UDP is not “less reliable TCP” for every use case**: it is useful when the application wants to actively control packet loss, ordering, or prioritize latency. However, if the business logic requires delivery and processing guarantees, the application must build appropriate mechanisms itself or use an existing higher-level protocol/library.

Note: HTTP/3 uses QUIC running over UDP, but QUIC implements the necessary reliability mechanisms at the layer above; therefore, do not assume HTTP/3 is unreliable just because its underlying transport is UDP.

## 8. Why is HTTP usually used instead of building a custom socket protocol?

Java classes correspond to different levels of abstraction:

- **java.net.Socket / ServerSocket**: operates on TCP at the byte-stream level; the application designs its own messages, framing, and session lifecycle.
- **java.net.DatagramSocket**: sends/receives UDP datagrams; the application defines how to decode/process them.
- **java.nio.channels**: channel/buffer APIs, supporting a non-blocking model with Selector when managing many connections.
- **java.net.http.HttpClient** (Java 11+): the application sends HTTP requests and receives responses at the HTTP level, including URI, headers, status code, and body; provides both synchronous and asynchronous APIs.
- **Server-side frameworks**: for example, Spring Web implements the HTTP layer, routing, data handling, and request lifecycle so business code does not have to read raw TCP bytes directly.

When building typical REST APIs, **HTTP/HTTPS** gives both sides built-in conventions for request/response, status codes, content types, and operational tooling. When you must design a custom binary protocol, work with specialized devices, or need a deep understanding of data flow, low-level sockets become useful. You should not assume “writing a custom TCP protocol” is better than using an existing standard.

## 9. Failure scenarios that real-world applications must handle

**Addressing/connection errors:** wrong DNS, wrong IP/port, server not listening, firewall blocking, port/resource exhaustion, or no route. A client needs to report errors clearly and decide whether to retry or fail.

**Indefinite blocking:** connect(), accept(), and read() can block at different points. Set a **connect timeout**, **read timeout**, request deadline, and manage task cancellation. A timeout does not prove the server did not execute the request.

**Premature connection close:** readLine() returns null when EOF is encountered before any character of the next line. For binary protocols, you must read the full declared length and treat EOF mid-message as an incomplete-data error.

**Ambiguous responses:** the client sends a “debit money” command and the connection drops before the response arrives. Blindly retrying could execute it twice. For operations with side effects, design an **idempotency key/request ID**, audit logging, and state reconciliation instead of relying on TCP as the sole proof.

**Untrusted data:** a peer may send oversized payloads, malformed syntax, unexpected data, or bursts of abnormal messages. Enforce limits on size, processing time, and connection counts; authenticate/authorize and validate data before using it.

**Security:** TCP is normally an unencrypted byte stream. Sensitive communication over a network requires TLS (HTTPS, SSLSocket/SSLServerSocket, or a TLS-capable library) with proper certificate/hostname verification; never send secrets over an unprotected custom protocol.

**Multiple concurrent clients:** the example above serves one client. Real-world servers typically loop on accept(), handing work off to an ExecutorService/thread pool or a non-blocking model, while setting load limits, queues, and backpressure. Spawning unbounded threads or keeping sockets without timeouts can exhaust resources.

## 10. Common misconceptions

1. **“Two different JVMs can pass whole objects directly over a Socket.”** Not directly. Objects must be serialized into an agreed data format (e.g., JSON/Protobuf), transmitted as bytes, and reconstructed on the other end. Java native serialization should not be the default for untrusted data.
2. **“One write corresponds to one read.”** False for TCP: it is a byte stream, so you must frame messages yourself and read the complete message.
3. **“flush() means the server has received or finished processing.”** False: flush pushes data out of the writer's buffer; to confirm processing, you need an application-level response/transaction design.
4. **“TCP always delivers every request.”** TCP supports reliable byte delivery while a connection is active, but it does not eliminate network failures, dropped connections, or uncertain business state.
5. **“Having an IP address is enough.”** The sender also needs the port, the right protocol, and application rules; domain names, NAT, firewalls, or binding only to loopback all affect connectivity.
6. **“Sockets are only used between two different machines.”** Two processes on the same machine also communicate via TCP/UDP loopback; besides network sockets, there are other IPC mechanisms such as pipes or shared memory, depending on the operating system.

## 11. Self-check questions

- If the client sends two 5-byte strings back-to-back and the server calls read() once with a 10-byte buffer, is the server **guaranteed to receive 10 bytes**? No. It must read in a loop and use a protocol that delimits the two messages.
- If the client receives PONG, what does it know? It knows the server application read PING and executed the PONG-reply branch in that run; it does not mean other business operations have committed unless the protocol defines that.
- If you want to run the demo across two machines, what needs to change? Bind the server to a permitted network address, have the client use the server's address/hostname, configure firewall/routing, and add appropriate TLS/authentication; do not use loopback as the target between two machines.
- If you need to send multi-line JSON over TCP, can you use a single readLine() call for the entire JSON? You should not. Choose explicit framing such as length-prefixing or a protocol like HTTP that defines its own framing.

## Conclusion

Network programming connects separate processes via **socket + address/port + transport protocol + application message contract**. The operating system handles moving bytes/datagrams between endpoints, while the application is responsible for producing data, delimiting messages, interpreting meaning, handling errors, timeouts, and security. Understanding this division of responsibility is the foundation for learning Sockets, HTTP, distributed services, and asynchronous programming.

### References

- [Java 17 – Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): client TCP socket and connection/I/O APIs.
- [Java 17 – ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): listening for and accepting TCP connections.
- [Java 17 – DatagramSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html): communication using UDP datagrams.
- [Java 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): application communication at the HTTP layer.

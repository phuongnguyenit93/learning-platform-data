# Distinguishing IP Addresses, Ports, Endpoints, Connections, and Messages

## Lesson Objectives

When reading a URL, inspecting connection logs, or writing a socket program in Java, you need to identify **whether you are referring to a machine's address, a service's address, a communication session, or a unit of data**. These five concepts are closely related but are not interchangeable:

| Concept | Question Answered | Example | Primary Role |
|---|---|---|---|
| **IP address** | Which network address should the IP packet go to? | `192.0.2.20`, `2001:db8::20` | Addressing and routing at the network layer |
| **Port** | Inside the machine, which receiving point should the transport protocol deliver data to? | TCP `443`, UDP `53` | Distinguishing sending/receiving points belonging to TCP or UDP |
| **Endpoint** | Where is the specific communication end located, and under which protocol/context? | TCP `192.0.2.20:443`; HTTP `GET /orders` | Describing where one side communicates or where an API is accessed |
| **Connection** | What data-transfer relationship are the two sides maintaining? | A TCP connection between a client's ephemeral port and `:443` | Communication state that persists over time |
| **Message** | What unit of information does the application want to exchange? | HTTP request, a `PING` line, a UDP datagram | Content with boundaries/meaning defined by the protocol |

This is a layered model: **IP** delivers packets to a network address; **TCP/UDP and port** deliver data to the appropriate socket; **application protocols** define the structure, meaning, and boundaries of a message. Endpoint and connection must always be understood within the context being discussed.

## 1. IP Address: Where Data Is Routed To

An IP address is a logical address used to transmit packets over an IP network. A device can have multiple network interfaces and multiple IP addresses; a single address can also be used by NAT, a load balancer, or special routing mechanisms. Therefore, saying "each IP is one machine" is an oversimplification.

- **IPv4** is 32 bits long, typically written as four decimal numbers: `192.0.2.20`. **IPv6** is 128 bits long, typically written in hexadecimal: `2001:db8::20`. The ranges `192.0.2.0/24`, `198.51.100.0/24`, and `2001:db8::/32` in this lesson are used as documentation examples and do not represent real servers.
- `127.0.0.1` and `::1` are **loopback** addresses: traffic returns to the same device. `localhost` is a *name* that typically resolves to a loopback address; that name is not itself an IP address.
- `0.0.0.0` or `::` is commonly used when **binding** a server to listen on all suitable addresses of the machine (*wildcard address*). They are not public destination addresses for clients to connect to arbitrarily.
- Domain names like `api.example.com` are resolved via DNS into one or more IP addresses. One name can return multiple IPs; multiple names can share one IP. DNS does not specify a port or an HTTP path.
- Private addresses, public addresses, NAT, and proxies affect how the network path is viewed; an internal IP observed from the client may differ from the IP that the server sees.

**Boundary:** knowing an IP does not tell you which service, which port, or which message will be processed. The `ping` command typically tests ICMP exchange/reachability to the destination; it does not confirm that the application's TCP port is open.

## 2. Port: An Identifier at the Transport Layer

Both TCP and UDP have a **16-bit** port field, with values from **0 to 65535**. The two protocols have separate port spaces: TCP port 53 and UDP port 53 are two different receiving points.

- A server usually **binds/listens** on a well-known port, such as TCP 443 (commonly reserved for HTTPS) or TCP 9090 for a demo application. A port is only a convention; it **does not automatically guarantee** that the application is speaking TLS/HTTP.
- A client is usually assigned an **ephemeral port** (temporary port) by the operating system, for example `53142`, when initiating communication. The specific ephemeral range depends on the operating system/configuration, so you should not assume a fixed range.
- Port `0` when *binding* a socket is typically a request for the operating system to choose an available port; it is not a destination service port used in normal connection examples.
- A port only has meaning when tied to **a transport protocol, a bind address, and a network context**. You cannot uniquely infer a process from the number `443` alone; NAT, containers, network namespaces, proxies, and socket-sharing mechanisms can make the picture more complex.

For example, a machine with IP `198.51.100.20` can simultaneously accept TCP `443` (web) and TCP `22` (SSH). Same IP, **different services because of different ports/protocols**; ports do not replace IPs for routing.

## 3. Endpoint: You Must Specify the Layer and Context

The term **endpoint** has several valid uses:

1. **Socket/transport endpoint:** usually an **IP address + port** pair, accompanied by TCP or UDP. For example, `TCP 198.51.100.20:443`; with IPv6, square brackets are used to avoid ambiguity with colons: `[2001:db8::20]:443`.
2. **Application/API endpoint:** the address of a resource or operation provided by an application. For instance, `GET https://api.example.com:443/v1/orders` specifies the HTTPS scheme, hostname, port, method, and path. The `/v1/orders` part is **not a TCP port** and **not part of the TCP socket endpoint**.
3. **Java objects representing a destination:** `InetSocketAddress` represents a hostname/IP together with a port; `URI` additionally contains scheme/path/query; `Socket` is a socket object bound to a communication activity, not synonymous with a URI.

A URL can refer to an **API endpoint** even when no network connection has been opened yet. Multiple URLs/paths can also be handled over **the same TCP connection** when the application reuses connections (e.g., HTTP keep-alive). Therefore, "endpoint" is not synonymous with "connection".

Illustrative URL breakdown example:

```text
https://api.example.com:443/v1/orders?status=open
  │       │              │   │         │
  │       hostname       │   path      query
  │                      port
  scheme = https
```

The hostname must be resolved to an IP to establish a connection in the standard model. With HTTPS over TCP, the default port is 443 if omitted; **HTTP path/query only appear at the application layer**. The same IP:port can serve multiple hostnames thanks to TLS/HTTP host name information, so an IP:port does not necessarily uniquely identify a single website.

## 4. Connection: A Stateful Communication Relationship

With **TCP**, a connection is a relationship established between two ends through a handshake process (typically SYN → SYN-ACK → ACK), after which it provides an **in-order** byte stream along with retransmission/flow-control mechanisms. Each side has a local address and a remote address.

A typical TCP connection is distinguished within a network context by a 4-tuple:

```text
(local IP, local TCP port, remote IP, remote TCP port)

Example:
client 192.0.2.10:53142  ──TCP──>  server 198.51.100.20:443
```

The TCP protocol and the network namespace/network context also matter when identifying a connection. Another client can call `198.51.100.20:443` at the same time; the server distinguishes connections based on the tuple of both ends, rather than creating "a new server port" for each client. A **listening socket** waits for incoming connections on an address/port; after `accept()`, a **connected socket** represents an accepted connection. Multiple connected sockets on the server can share local port `443` while having different remote endpoints.

**A connection has a lifecycle:** establish → send/receive multiple times → close (or error/timeout). It is not a message; one connection can carry zero, one, or very many messages. Passing through NAT/load balancers/proxies can change the endpoint observed by each side, and a proxy can create **two separate TCP connections** for a single request from client to backend.

With **UDP**, the UDP layer **has no TCP-style handshake or reliable byte stream**. Each datagram carries a destination address and port and can be sent/received without establishing a connection. Java's `DatagramSocket.connect(...)` method only configures a default peer and filters incoming sources at the socket level; it **does not turn UDP into TCP** and does not create a UDP handshake session. Some higher-level protocols running on top of UDP (such as QUIC) build their own connection concept: always distinguish *which protocol's connection* is being discussed.

## 5. Message: A Meaningful Unit for the Application

Applications exchange **messages**, such as "login", "GET /orders", a JSON response, or "PING". A message can have headers, a payload, and protocol-defined boundaries. Do not equate a message with an **IP packet**, a **TCP segment**, or a **`read()` call**: those are different units.

**TCP is a byte stream; it does not preserve the boundaries of each `write()`.** If a client writes `HELLO` and then writes `WORLD`, the receiving side might read `HELLOWORLD` in a single read, or `HE` followed by `LLOWORLD` across multiple reads. TCP guarantees byte order (when the connection transfers data successfully); it **does not guarantee that one `read()` corresponds to one `write()` or one message**.

To turn a byte stream into messages, an application protocol needs **framing**, for example:

| Framing Approach | How Boundaries Are Recognized | Notes |
|---|---|---|
| Delimiter-terminated | Each message ends with `\n` (or `\r\n`) | Payload must have escaping rules if it can contain the delimiter |
| Length-prefixed | For example, the first 4 bytes indicate payload length; read that exact number of bytes next | Must specify byte order, length limits, and handle partial reads |
| Standard protocol structure | HTTP/1.1 uses start-line, headers, and body-length rules; HTTP/2 has frames/streams | Use a protocol library; do not split messages yourself by TCP segment size |
| End of stream | A single message lasts until EOF | Not suitable for sending multiple consecutive messages on the same connection |

**UDP** preserves datagram boundaries in the receive API: each `receive()` gets **one datagram** (which may be truncated if the buffer is too small). However, UDP **does not guarantee** that a datagram will arrive, will not be duplicated, or will arrive in order. A large message may have to be split at the application layer; you should not rely on IP fragmentation as a mechanism for reliably transmitting large messages.

For example: HTTPS over TCP can carry multiple HTTP requests/responses over one connection; TLS has its own records, but TLS record boundaries also **do not match** HTTP message boundaries. In HTTP/2, multiple request streams can be multiplexed over one connection. In every case, an **application message** must be decoded according to the application protocol.

## 6. Walking Through a Scenario: From URL to Response

Suppose a client calls `https://api.example.com/v1/orders`; the domain name and IPs below are for illustration only.

```text
Client application
   │  (1) Identify HTTPS + hostname + path; DNS lookup → 198.51.100.20
   │  (2) TCP: 192.0.2.10:53142 ───────────→ 198.51.100.20:443
   │  (3) TLS handshake and server authentication
   │  (4) Send HTTP request for /v1/orders over the secure connection
   │  (5) Receive HTTP response, decode into an application message
   └  (6) Reuse or close the connection depending on protocol/policy
```

Points to distinguish:

- `198.51.100.20` is the **destination IP** in the hypothetical scenario; `443` is the **destination TCP port**.
- `192.0.2.10:53142` and `198.51.100.20:443` are the two **transport endpoints** observed on the client side; the pair of both ends is used to identify the **TCP connection**.
- `GET /v1/orders` is an operation targeting an **HTTP API endpoint**; the request and response are **HTTP messages**.
- An HTTP request can be sent over an existing connection; it is not necessary for each request to open a new TCP connection. With HTTPS running over HTTP/3, the underlying protocol is QUIC/UDP, so the transport-layer details differ from the TCP example above.

## 7. Java 17+: Practicing TCP and Line-Based Framing

The example below uses loopback so everything runs on a single machine. The server listens on TCP port 9090; the client is automatically assigned an ephemeral local port. The custom protocol defines each message as **a UTF-8 line terminated by a newline**. Both standalone files are compiled with JDK 17 or later.

**File `TcpLineServer.java`**

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpLineServer {
    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 9090));
            System.out.println("Server ready");

            try (Socket socket = server.accept();
                 BufferedReader reader = new BufferedReader(
                         new InputStreamReader(socket.getInputStream(),
                                 StandardCharsets.UTF_8));
                 BufferedWriter writer = new BufferedWriter(
                         new OutputStreamWriter(socket.getOutputStream(),
                                 StandardCharsets.UTF_8))) {
                String message = reader.readLine();
                System.out.println("Server received: " + message);
                writer.write("ACK: " + message);
                writer.newLine();
                writer.flush();
            }
        }
    }
}
```

**File `TcpLineClient.java`**

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpLineClient {
    public static void main(String[] args) throws Exception {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 9090), 3000);
            socket.setSoTimeout(3000);

            try (BufferedReader reader = new BufferedReader(
                         new InputStreamReader(socket.getInputStream(),
                                 StandardCharsets.UTF_8));
                 BufferedWriter writer = new BufferedWriter(
                         new OutputStreamWriter(socket.getOutputStream(),
                                 StandardCharsets.UTF_8))) {
                writer.write("PING");
                writer.newLine();
                writer.flush();
                System.out.println("Client received: " + reader.readLine());
            }
        }
    }
}
```

**Compile and run:**

```bash
javac -encoding UTF-8 TcpLineServer.java TcpLineClient.java
java TcpLineServer
```

Keep the server running, and open a **second terminal** in the same directory:

```bash
java TcpLineClient
```

On a successful run, the expected output is:

```text
# Server terminal
Server ready
Server received: PING

# Client terminal
Client received: ACK: PING
```

Lines starting with `# ... terminal` above are explanatory labels in the output block, not lines printed by the program.

**Explanation across the five concepts:**

1. `InetAddress.getLoopbackAddress()` provides a loopback IP appropriate for the environment; the server listens only for local access.
2. `9090` is the server port. The client implicitly binds to a local port chosen by the operating system; the specific value changes from run to run.
3. `new InetSocketAddress(ip, 9090)` specifies the server's transport endpoint.
4. `connect()` opens the TCP connection; `accept()` returns the connected socket. `ServerSocket` listening and `Socket` sending/receiving are two distinct roles.
5. `PING` and `ACK: PING` are **two application messages**. `newLine()` + `flush()` creates the line boundary for `readLine()`. If you omit the newline while still using `readLine()`, the receiver can remain waiting for a delimiter/EOF even though some bytes have already arrived.

The demo program serves only one client once and then exits. In a real server, there is typically an `accept()` loop, concurrency management, timeouts, validation, message size limits, and explicit connection-closing handling. If port 9090 is already in use, change **both** files to an available port.

## 8. Java 17+: Trying UDP to Observe Datagram Boundaries

In `UdpDatagramDemo.java`, the receiver binds to loopback with port `0` so the operating system picks a port automatically; the sender sends two independent datagrams without **calling `connect()`**:

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class UdpDatagramDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramSocket receiver = new DatagramSocket(
                     new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             DatagramSocket sender = new DatagramSocket()) {
            receiver.setSoTimeout(2000);

            for (String message : new String[] {"ONE", "TWO"}) {
                byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
                sender.send(new DatagramPacket(
                        bytes, bytes.length, receiver.getLocalSocketAddress()));
            }

            for (int i = 1; i <= 2; i++) {
                byte[] buffer = new byte[128];
                DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                receiver.receive(packet);
                String message = new String(packet.getData(), packet.getOffset(),
                        packet.getLength(), StandardCharsets.UTF_8);
                System.out.println("Datagram " + i + ": " + message);
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 UdpDatagramDemo.java
java UdpDatagramDemo
```

On loopback, when the two datagrams arrive in the order sent, the output is:

```text
Datagram 1: ONE
Datagram 2: TWO
```

Each `receive()` processes one datagram, and `getLength()` gives the actual length of data received. **This is a common observation, not a UDP guarantee:** the network can drop, reorder, or duplicate datagrams; if nothing is received within 2 seconds, the example throws `SocketTimeoutException`. A 128-byte buffer is enough for the two sample strings; real applications must define valid size limits and handle truncated datagrams.

## 9. How to Read Logs and Diagnose Common Misconceptions

| Symptom | What to Check | What Not to Jump To |
|---|---|---|
| DNS cannot resolve hostname | Name, DNS, records, connectivity to resolver | Cannot yet conclude the destination TCP port is broken |
| `Connection refused` on TCP connect | Destination IP/port, listener, firewall actively rejecting | Not an HTTP response parsing error |
| TCP connect timeout | Route, firewall, IP/port, reachability | Not sufficient evidence that the server does not exist |
| `connect()` succeeds but `readLine()` hangs | Whether the sender called `flush()`, whether newline/EOF was sent, timeout | A successful connection does not mean the message is complete |
| Receiving partial data via TCP `read()` | Framing, loop to read enough bytes, EOF, buffer limits | One `read()` does not represent one message |
| UDP not received or out of order | Port, IP, receiver bind, buffer, timeout, ordering/deduplication logic | UDP does not guarantee delivery or ordering |
| HTTP 404 | Method/path/route/resource in the application | The TCP connection may be completely normal |

A few OS-level checks:

- `ss -ltn` (Linux) lists TCP listening sockets; `Get-NetTCPConnection -LocalPort 9090` (PowerShell/Windows) can inspect TCP sockets related to the port, if supported by the OS version.
- `curl -v https://example.com/` tests an **HTTP(S) service** and shows multiple communication stages. **Do not use `curl` to test the line-based PING protocol** in the TCP example above: that server does not speak HTTP.
- In Java, `socket.getLocalSocketAddress()` and `socket.getRemoteSocketAddress()` help observe the **two transport endpoints** of a connected socket. When NAT or a proxy is present, the two sides may report different endpoints because addresses are translated.

Debug starting from the **lowest failing layer**: name resolution → IP routing → TCP/UDP and port → connection/TLS (if applicable) → message framing and syntax → business rules. Do not use an HTTP error to infer an IP error when the evidence does not support it.

## 10. Misconceptions to Avoid

1. **"Having an IP means you can access the API."** Not necessarily: there are still port, listener, protocol, firewall, URL/method, and access permissions.
2. **"A port is a smaller IP address."** False: IP and port belong to two different layers and perform two different jobs.
3. **"An endpoint is always a URL."** False: a socket endpoint is usually IP/host + port; an API endpoint can be method + URL/path.
4. **"Every HTTP request is a TCP connection."** False: connections can be reused or multiplexed, depending on the HTTP version and policy.
5. **"If TCP sends one message, the other side reads one message."** False: TCP only delivers an ordered byte stream; framing is needed at the application layer.
6. **"UDP has `connect()` in Java, so UDP guarantees connections like TCP."** False: Java sets a default peer/datagram filter; it does not provide a handshake or TCP guarantees.
7. **"Every user accessing a server must have a separate server port."** False: multiple TCP connections use the same server local port, differing by the client's endpoint.
8. **"If ping succeeds, HTTP must work."** False: ICMP, TCP/TLS, and HTTP are different steps and protocols.

## 11. Self-Check Questions

**Scenario A.** A log shows `TCP 192.0.2.10:53142 -> 198.51.100.20:443`, and then the client sends `GET /v1/orders`. Identify:

- Client IP: `192.0.2.10`; client local port: `53142` (ephemeral example).
- Server IP: `198.51.100.20`; server TCP port: `443`.
- Two TCP socket endpoints: `192.0.2.10:53142` and `198.51.100.20:443`.
- Connection: the TCP relationship between the two ends, with state and lifecycle.
- Application endpoint: the HTTP route `GET /v1/orders` at the corresponding hostname/service.
- Message: the HTTP request; the subsequent response is another message, possibly over the same connection.

**Scenario B.** A client calls `write()` twice with `"A"` and then `"B"`, and the server reads once and sees `"AB"`. Is there a TCP error? **No.** TCP is allowed to coalesce bytes in a single read; the application protocol must establish message boundaries.

**Scenario C.** Do two URLs `https://api.example.com/orders` and `https://api.example.com/users` have to open two TCP connections? **No.** They are two API paths; the client library can reuse a connection to the same appropriate destination.

**Scenario D.** A server binds to `0.0.0.0:9090`. Should a client connect to `0.0.0.0:9090`? **A wildcard bind should not be treated as a destination address reachable from a client.** The client chooses an actual reachable IP address/hostname; when running on the same machine, loopback is typically used and you verify the server is listening on the corresponding address family.

## Summary

- **IP** answers where to route the packet; **port** selects the TCP/UDP communication point on that address.
- A **transport endpoint** is a communication end (usually IP + port + protocol); an **API endpoint** describes an application operation/resource.
- A **TCP connection** is a stateful byte-transfer relationship between two ends; a **message** is a unit of information defined by the application protocol.
- One connection can carry many messages; one API endpoint can be called over many connections; one server port can serve many clients concurrently.
- When using TCP, **always define framing**. When using UDP, **always account for packet loss, reordering, duplication, and datagram size limits**.

Chain to remember: **DNS/name → IP for routing → TCP/UDP + port for delivery to socket → connection if the protocol has one → framing/protocol to reconstruct messages → API/business logic processing.**

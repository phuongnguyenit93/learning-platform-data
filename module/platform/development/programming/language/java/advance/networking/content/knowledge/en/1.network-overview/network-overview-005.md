# Which Layers Do TCP, UDP, HTTP, TLS, and WebSocket Belong To?

**Core answer:** According to the OSI model, **TCP and UDP are at Layer 4 (Transport)**; **HTTP and WebSocket are at Layer 7 (Application)**. **TLS** secures application communication above the transport layer: it is commonly associated with Layer 5–6 functions (Session/Presentation), but **does not have a single fixed, official OSI layer position**. In the practical TCP/IP model, HTTP, WebSocket, and TLS typically sit in the application-side protocol group; TCP/UDP are at the transport layer.

The most common point of confusion: **HTTP does not always run over TCP**. HTTP/1.1 and HTTP/2 typically use TCP; **HTTP/3 runs over QUIC, which runs over UDP and integrates the TLS 1.3 handshake**.

## 1. Two Layer Models to Distinguish

The **7-layer OSI model** helps with learning concepts; the **TCP/IP model** reflects how Internet protocols are typically organized. "Placing a protocol into a layer" can be an approximate mapping, especially for TLS and QUIC.

| OSI Layer | Main Role | Examples, Associations |
|---|---|---|
| **7 – Application** | Message conventions and application behavior | HTTP, WebSocket, DNS |
| **6 – Presentation** | Data representation, conceptual encryption/decryption | TLS security functions are often associated here |
| **5 – Session** | Establishing and maintaining sessions as described by OSI | Some TLS handshake/session functions are also often associated here |
| **4 – Transport** | End-to-end communication between processes, ports, data delivery | TCP, UDP |
| **3 – Network** | IP addressing and packet routing | IPv4, IPv6 |
| **2 – Data Link** | Transmitting frames across a single link | Ethernet, Wi‑Fi (MAC portion) |
| **1 – Physical** | Signals transmitted over a physical medium | Cables, radio waves |

In the four-layer TCP/IP layering, OSI 5–7 are typically grouped into **Application**; OSI 4 is **Transport**; OSI 3 is **Internet**; OSI 1–2 belong to **Link/Network access**. Therefore, the statement "TLS is at Layer 6" is only a functional illustration, **not a mandatory layering rule**.

## 2. Classification of the Five Protocols

| Protocol | OSI (Approximate) | Specific Role | Common Underlying Transport |
|---|---|---|---|
| **TCP** | L4 – Transport | Reliable, ordered byte stream; flow and congestion control | IP |
| **UDP** | L4 – Transport | Datagrams with message boundaries; no built-in guarantee of complete delivery, ordering, or retransmission | IP |
| **HTTP** | L7 – Application | Request/response semantics, methods, status codes, headers, body | HTTP/1.1, HTTP/2 typically over TCP; HTTP/3 over QUIC/UDP |
| **TLS** | Sits between application and transport in a TLS-over-TCP stack; functionally associated with L5–L6 | Peer authentication (typically the server), key exchange, data confidentiality and integrity | Typically wraps a stream over TCP; TLS 1.3 is integrated into QUIC in its own way |
| **WebSocket** | L7 – Application | Bidirectional, long-lived channel with frame/message structure | Traditionally over TCP, optionally over TLS; also has mechanisms over HTTP/2 and HTTP/3 |

The rows are not five consecutive layers. **TCP and UDP are two peer-level choices**. **HTTP and WebSocket are two application-side protocols that are related during WebSocket establishment**, while TLS is a security layer used depending on the stack.

### TCP: A Byte Stream, Not "Messages"

TCP establishes a connection, assigns sequence numbers, retransmits when needed, and delivers an **ordered byte stream** to the application. If the sender writes three times, the receiver does not necessarily read three corresponding times: the boundaries of individual writes are not preserved by TCP. HTTP/1.1, HTTP/2, and classic WebSocket define their own framing on top of that stream.

### UDP: Independent Datagrams

UDP sends datagrams; it does not promise delivery, retransmission, or ordering on its own. UDP is suitable when an application wants to decide its own delivery policy, such as real-time protocols. **Do not infer that every application using UDP is unreliable:** QUIC builds a reliable per-stream delivery mechanism on top of UDP.

### HTTP: Application-Level Exchange Rules

HTTP defines methods such as GET/POST, status codes, headers, bodies, and exchange semantics. HTTP is not another name for TCP: HTTP only needs a transport mechanism that meets the requirements of that version.

- **HTTP/1.1:** typically uses a TCP connection; can run unencrypted (**http**) or over TLS (**https**).
- **HTTP/2:** typically runs over TLS/TCP when used on the Web; multiplexes multiple streams over a connection, though TCP still transmits a single byte stream underneath. Some environments support HTTP/2 without TLS (**h2c**).
- **HTTP/3:** delegates stream transport to **QUIC**, which runs over UDP; there is no TCP underneath HTTP/3.

### TLS: Security, Not a Replacement for TCP/UDP

TLS typically establishes keys, authenticates identity via certificates, and protects data from eavesdropping or tampering in transit. With HTTPS running over TCP, the application passes HTTP into TLS; TLS encrypts the data and transmits it over TCP. TLS **does not perform IP routing itself or guarantee byte delivery the way TCP does**. With QUIC, TLS 1.3 provides the handshake and key mechanism integrated into QUIC; one does not draw a conventional TLS-record layer "sitting on UDP" below QUIC.

TLS protects content within its scope; that does not mean all network metadata is encrypted (for example, IP addresses and UDP/TCP ports are still needed to forward packets).

### WebSocket: Bidirectional After the Setup Phase

WebSocket provides **messages/frames and bidirectional (full-duplex) communication**: both client and server can send data while the connection remains open. Unlike HTTP's usual request/response model, the server does not need to wait for the client to make a new request each time it wants to push a message.

With traditional WebSocket over HTTP/1.1, the client starts with an **HTTP Upgrade** request; the server accepts with **101 Switching Protocols**. After that step, data travels as **WebSocket frames**, not a sequence of ordinary HTTP responses.

HTTP/2 and HTTP/3 do not use that Upgrade/101 mechanism. They have **Extended CONNECT** to establish WebSocket over a stream if both endpoints support it (RFC 8441 and RFC 9220, respectively). Therefore, saying "WebSocket always requires a dedicated TCP connection and HTTP/1.1 Upgrade" is overly absolute.

## 3. Looking at the Stack from Top to Bottom

The diagrams below are **protocol stacks**, not alternative names for the seven OSI layers.

### A. HTTPS Using HTTP/1.1 or HTTP/2

~~~text
Java application / browser
  HTTP/1.1 or HTTP/2           Application
  TLS (typically 1.2/1.3)      Security between application and TCP
  TCP                          Transport
  IP                           Network/Internet
  Ethernet or Wi-Fi            Link
  Physical medium              Physical
~~~

When accessing an **https://** URL, you cannot look at the URL alone and conclude with certainty whether it uses HTTP/1.1 or HTTP/2; the version is negotiated and depends on the client/server. TLS typically negotiates the application protocol using **ALPN**.

### B. HTTPS Using HTTP/3

~~~text
Java application / browser
  HTTP/3                       Application
  QUIC (integrated TLS 1.3)    Transport over UDP
  UDP                          Underlying Transport
  IP                           Network/Internet
  Ethernet or Wi-Fi            Link
  Physical medium              Physical
~~~

QUIC provides connections, streams, congestion control, and reliability mechanisms on top of UDP. A QUIC connection with multiple streams can reduce the phenomenon where a single packet loss stalls other streams at the transport level, which is an issue when multiple HTTP/2 streams share one TCP connection. This does **not** mean QUIC never experiences packet loss or does not need retransmission.

### C. Typical WebSocket

~~~text
ws://host/chat:
  WebSocket messages/frames → TCP → IP → Link

wss://host/chat:
  WebSocket messages/frames → TLS → TCP → IP → Link
~~~

The two lines above describe the classic WebSocket form established over HTTP/1.1. With WebSocket over HTTP/2, data belongs to an HTTP/2 stream over TLS/TCP; with HTTP/3, data belongs to an HTTP/3 stream over QUIC/UDP. **ws** is the scheme that does not require TLS; **wss** is the secure scheme. The scheme does not tell you for sure which HTTP protocol was used to establish it.

## 4. How Does an Actual Session Unfold?

**HTTPS over HTTP/2/TCP example:**

1. The client resolves the target address via DNS (DNS is a separate protocol that can run over multiple transports).
2. The client performs a TCP handshake with the server: SYN → SYN-ACK → ACK.
3. The client/server perform a TLS handshake, authenticate, and establish keys; ALPN may select h2.
4. HTTP/2 sends requests/responses over streams of that TLS/TCP connection.
5. The connection may be reused; closing an HTTP stream does not necessarily close the TCP connection.

**WebSocket over HTTP/1.1 example:** after TCP (and TLS if wss), the client sends a request similar to:

~~~http
GET /chat HTTP/1.1
Host: server.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
~~~

If accepted, the server may respond with:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
~~~

This is an illustrative example per the standard; a real client must generate a random key for each handshake. After a valid 101 response, both sides exchange WebSocket frames (text/binary, ping/pong, close) over the same connection. **HTTP assists with opening the channel**, while WebSocket defines how messages are sent in the subsequent phase.

## 5. Direct Connection to Java 17+

| Java API | Associated Protocol/Layer | Used When |
|---|---|---|
| **java.net.Socket**, **ServerSocket**, **SocketChannel** | TCP / Transport | Writing or parsing a protocol over a TCP stream |
| **DatagramSocket**, **DatagramPacket**, **DatagramChannel** | UDP / Transport | Sending and receiving datagrams |
| **javax.net.ssl.SSLSocket**, **SSLEngine** | TLS | Adding security to a compatible connection/transport |
| **java.net.http.HttpClient** | HTTP / Application | HTTP/1.1, HTTP/2, HTTPS |
| **java.net.http.WebSocket** | WebSocket / Application | Full-duplex communication over WebSocket |

**Runnable example on Java 17:** the program sends an HTTPS request and prints the HTTP version actually used along with the connection's TLS version.

~~~java
// File: LayerDemo.java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import javax.net.ssl.SSLSession;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2) // preferred, not required
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/"))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        System.out.println("HTTP: " + response.version());
        System.out.println("TLS: " + response.sslSession()
                .map(SSLSession::getProtocol)
                .orElse("(no TLS session)"));
        System.out.println("Status: " + response.statusCode());
    }
}
~~~

~~~bash
javac LayerDemo.java
java LayerDemo
~~~

The example **requires an Internet connection and a valid TLS certificate**. The HTTP line may be **HTTP_2** or **HTTP_1_1** depending on the server, proxy, and negotiation; the TLS version and status code also depend on the environment. Therefore, there is no fixed stdout reliable enough to apply to every run. On **standard JDK 17**, HttpClient supports HTTP/1.1 and HTTP/2; do not assume it supports HTTP/3 just because the URL uses HTTPS.

The key takeaway when programming: **Socket** operates at the TCP layer; **HttpClient** expresses HTTP; **WebSocket** manages bidirectional messages; **SSLSocket/SSLEngine** handles TLS. These APIs are not at the same level of abstraction.

## 6. Quick Identification via URL, Port, and Packets

| Observation | What Can Be Inferred | What Must Not Be Inferred |
|---|---|---|
| **https://example.com** | Protected HTTP over a connection to the origin (in the normal case) | That it is definitely HTTP/2 or always uses TCP |
| **wss://example.com/chat** | Secure WebSocket | That it definitely uses HTTP/1.1 Upgrade |
| **TCP port 443** | A TCP connection to port 443 | That the entire content is definitely HTTP or TLS |
| **UDP port 443** | A UDP datagram flow to port 443 | That it is definitely QUIC/HTTP/3 without inspecting packets |
| **TLS handshake present** | A TLS security setup process or TLS integrated into the relevant protocol | That TLS is an "official OSI Layer 6" |
| **HTTP 101 + Upgrade: websocket present** | Transitioning from HTTP/1.1 to WebSocket if the handshake is valid | That subsequent WebSocket messages are still HTTP responses |

For practical analysis, use **Wireshark** or client/server traces; you can filter by tcp, udp, tls, http, websocket, quic. Results depend on versions, decryption, protocol dissectors, and actual traffic. **Default ports are only conventions:** HTTP typically uses TCP 80, HTTPS typically uses TCP 443 or QUIC/UDP 443; WebSocket ws/wss typically use 80/443 respectively, but all can be configured on other ports.

## 7. Four Important Misconceptions

1. **"HTTP belongs to the Transport layer because it runs over TCP."** False: HTTP is an application protocol. A higher-level protocol can run over different underlying transports.
2. **"TLS is strictly OSI Layer 6."** Inaccurate: that is a functional assignment for learning; TLS implementations typically sit between the application and TCP, while QUIC integrates TLS differently.
3. **"UDP is always unreliable, so HTTP/3 is unreliable."** False: UDP does not provide reliability on its own, but QUIC handles it above UDP on a per-stream basis.
4. **"WebSocket is just long-lived HTTP."** False regarding data after the HTTP/1.1 handshake: WebSocket has its own frame format and semantics. HTTP/2/3 even have an Extended CONNECT mechanism instead of HTTP/1.1-style Upgrade/101.

## 8. Self-Check on Choosing the Right Diagram

- Calling a REST API over HTTPS and seeing **HTTP/2**: draw **HTTP/2 → TLS → TCP → IP**.
- Same HTTPS URL but negotiating **HTTP/3**: draw **HTTP/3 → QUIC (integrated TLS 1.3) → UDP → IP**.
- Chat application using **wss** over HTTP/1.1: draw **WebSocket frames → TLS → TCP → IP** after the HTTP Upgrade.
- Custom datagram-sending service: draw **application protocol → UDP → IP**; decide yourself whether packet loss detection, retransmission, and ordering are needed.

**Rule of thumb:** Ask **"what does this protocol specify?"** before asking **"what does it run over?"**. HTTP/WebSocket specify application content and communication flow; TCP/UDP specify how transport works; TLS provides security; IP delivers packets across the network. Protocols are layered/nested inside one another, but they do not necessarily map one-to-one onto OSI.

### Standard References for Further Reading

- [RFC 9293 — Transmission Control Protocol](https://www.rfc-editor.org/rfc/rfc9293)
- [RFC 768 — User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
- [RFC 8441 — WebSocket over HTTP/2](https://www.rfc-editor.org/rfc/rfc8441)
- [RFC 9220 — WebSocket over HTTP/3](https://www.rfc-editor.org/rfc/rfc9220)

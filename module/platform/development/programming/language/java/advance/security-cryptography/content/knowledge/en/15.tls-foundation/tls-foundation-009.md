# 15.9 Distinguishing Stream-Based TLS from Datagram-Based DTLS

## 1. What will you learn in this lesson?

**TLS (Transport Layer Security)** and **DTLS (Datagram Transport Layer Security)** both use a handshake and record layer to protect data exchange across untrusted networks. They share goals such as confidentiality, message authentication, and (when properly configured) peer authentication, yet **have completely different transport assumptions**:

- **Stream-based TLS:** usually runs over **TCP**, receiving a **reliable, ordered byte stream**. TCP is responsible for delivering bytes in order or reporting connection failure; TLS protects the contents of that byte stream.
- **Datagram-based DTLS:** usually runs over **UDP**, without requiring every datagram to arrive or arrive in order. DTLS adds handling for lost/reordered handshakes, record sequence numbers, and anti-replay mechanisms to protect data while **preserving datagram semantics**.

Key sentence to remember: **TLS/TCP protects an ordered byte stream; DTLS/UDP protects datagrams that may be lost, duplicated, delayed, or reordered.** DTLS **does not turn UDP into TCP**.

This lesson belongs to **TLS Foundation** and focuses on distinguishing transport/record semantics, handshake handling, network costs, choosing Java 17+ APIs, and testing. The runnable example in section 8 is a **TCP/UDP demo + JSSE TLS/DTLS exploration**, not two secure connections that completed TLS/DTLS handshakes; this boundary is stated explicitly to avoid any illusion of security.

### Learning outcomes

1. Distinguish **TCP stream**, **UDP datagram**, **TLS record**, and **DTLS record**.
2. Explain why UDP cannot simply "stuff TLS inside" without modifying the protocol.
3. Understand how DTLS handles **handshake retransmission, fragmentation, reordering, epoch/sequence, and replay detection**.
4. Choose correctly between **`SSLSocket`/`SSLServerSocket` for TLS/TCP** and **`SSLContext("DTLS")` + `SSLEngine` + datagram I/O** in Java.
5. Recognize that DTLS does not inherently guarantee **reliability, ordering, or exactly-once transaction delivery**.
6. Evaluate when to choose TLS, DTLS, or QUIC/TLS 1.3 for a network problem.

## 2. Layered model: do not mix transport and security

```text
          Typical TLS/TCP                         Typical DTLS/UDP
  +-----------------------------+        +------------------------------+
  | App: HTTP, RPC, ...         |        | App: realtime, sensor...     |
  +-----------------------------+        +------------------------------+
  | TLS: handshake + records    |        | DTLS: handshake + records    |
  | encrypt, integrity, identity|        | encrypt, integrity, identity |
  +-----------------------------+        +------------------------------+
  | TCP: ordered byte stream    |        | UDP: independent datagrams   |
  | reliable within connection  |        | may drop/reorder/duplicate   |
  +-----------------------------+        +------------------------------+
  | IP                          |        | IP                           |
  +-----------------------------+        +------------------------------+
```

The **application** defines "what a request is"; the **transport** defines how bytes/packets are delivered; **TLS/DTLS** defines how to handshake, pick keys, and protect data. None of these protocols alone decides whether a user is authorized to pay, write data, or replay an already-executed request.

| Unit | What does it mean? | Does it preserve application boundaries? |
| --- | --- | --- |
| TCP **byte stream** | A continuous sequence of bytes between two endpoints | **No**. Two `write` calls may be read as one or many `read` calls |
| TCP **segment** | TCP's network transmission unit | Does not correspond to application messages |
| **TLS record** | TLS framing/protection unit | Never use record boundaries as application message boundaries |
| UDP **datagram** | A packet with its own length and source/destination addresses | Has datagram boundaries, yet lacks reliability or ordering |
| **DTLS record** | DTLS protection unit with record/epoch metadata | Encapsulated inside datagrams; no application-layer delivery/in-order guarantee |

**Note on UDP:** if a datagram exceeds the `DatagramPacket` buffer, its content can suffer **truncation**; programs must check `packet.getLength()` and enforce limits. One UDP datagram does not automatically equal one business transaction, and one DTLS record does not automatically equal one request.

## 3. Comparison table: stream TLS vs. datagram DTLS

| Aspect | TLS over stream, usually TCP | DTLS over datagram, usually UDP |
| --- | --- | --- |
| Transport requirement | Reliable + ordered byte stream | Unreliable datagrams, potentially out-of-order |
| Application-facing data | Byte stream after decryption | Protected data per datagram/record |
| `write(A)`, `write(B)` | Received as byte sequence `AB` if delivered; no boundary kept | May receive `A,B`, `B,A`, only `B`, duplicates, or loss |
| Lost-packet retransmission | **TCP** retransmits | **DTLS handshake** has retransmission; application data **is not auto-retransmitted** |
| Handshake | Assumes reliable, ordered transport | Uses message sequence/fragments, buffering, timeouts, retransmission |
| Record ordering | Relies on stream order and TLS record context | Uses record sequence/epoch to identify records and handle reordering |
| Anti-replay | Prevents record tampering/reordering within stream per scheme | DTLS has a replay window per version/policy, yet does not solve business replay |
| MTU/packet size | TCP segmentation hides packet details from apps | Must account for record overhead and path MTU to avoid IP fragmentation |
| Head-of-line | Losing one TCP segment can stall later bytes on that connection | Not forced into strict stream order by TCP; apps may queue if needed |
| Peer identity | Certificate/PSK + trust/hostname policy | Similar, plus must guard against UDP peer/session/DoS risks |
| Java JSSE | `SSLSocket`, `SSLServerSocket`, `SSLEngine` | `SSLContext.getInstance("DTLS")`, `SSLEngine`, manual UDP I/O management |
| Latency | Depends on congestion, packet loss, server, handshake, RTT | Depends on packet loss, MTU, NAT, handshake retransmission, app logic; **not automatically faster** |

**Cryptographic security is not transport reliability.** DTLS can authenticate a record, yet **cannot force the network to deliver that record**. Completing a session handshake also does not mean the application received every payload the sender transmitted.

## 4. TLS/TCP: a byte stream, not a message queue

Suppose the sender calls:

```text
write("one")
write("two")
```

TCP gives the receiver a sequence of 6 bytes:

```text
o n e t w o
```

The receiver's `read()` might get `"o"`, `"net"`, `"wo"`; or `"onetwo"`; or any other valid split. Calling `write` twice on the sender **does not** force the receiver to call `read` exactly twice. This remains true when replacing a plain socket with `SSLSocket` and using **TLS over TCP**.

### 4.1 Application-layer framing is required

An application protocol over a TLS stream needs a way to delimit messages:

- **Length prefix:** a length field (e.g., 4 unsigned bytes / app-bounded) followed by that exact number of body bytes.
- **Delimiter with escaping:** unambiguous delimiter and escaping rules.
- **Standard built-in framing:** HTTP/2, WebSocket, gRPC, and other structured protocols.

The snippet below is **non-standalone**: `tlsSocket` is an authenticated, handshaked `SSLSocket`, and both sides agree on length-prefix framing:

```java
byte[] message = "ping".getBytes(java.nio.charset.StandardCharsets.UTF_8);
java.io.DataOutputStream output =
        new java.io.DataOutputStream(tlsSocket.getOutputStream());
output.writeInt(message.length);
output.write(message);
output.flush();

// On the receiving side, on another authenticated SSLSocket:
java.io.DataInputStream input =
        new java.io.DataInputStream(peerSocket.getInputStream());
int length = input.readInt();
if (length < 0 || length > 65536) {
    throw new java.io.IOException("Invalid frame length");
}
byte[] received = new byte[length];
input.readFully(received);
```

**Checking an upper bound before allocating** is mandatory when receiving data from a not-fully-trusted peer. Never write code that calls `read()` once and assumes the entire body arrived.

### 4.2 TCP and TLS have different responsibilities

- TCP: in-order **byte** transport, retransmission, congestion/flow control, broken-connection detection.
- TLS: handshake, cryptographic parameter selection, peer authentication when configured properly, ciphertext/integrity protection; does not replace application framing.
- JSSE `SSLSocket`: bridges those two layers and exposes `InputStream`/`OutputStream` after TLS processing.

**A TLS record is not a TCP segment**, and **a TLS record is not an application frame**. JSSE may split one application message across multiple records or coalesce data as needed by the implementation.

## 5. DTLS/UDP: protects datagrams while still permitting loss/reordering

UDP sends individual datagrams with source/destination addresses and length; it makes no guarantee of full delivery, once-only delivery, or ordering. DTLS adds cryptographic record protection atop this model:

```text
App creates A ------> DTLS record A -----> UDP datagram A -----+
                                                               |
App creates B ------> DTLS record B -----> UDP datagram B --+ |
                                                            | |
                                              Network: drop/delay/reorder/dup
                                                            | |
                                         DTLS checks record, epoch, seq, tag
                                                   |
                                         Delivers valid data to app
```

When the network delivers two datagrams in order `B` then `A`, DTLS can process valid data without forcing them into a **TCP-like stream**. When `A` is dropped, DTLS **does not automatically retransmit application record A**. Avoid mistaking "cryptographically protected datagram" for "guaranteed delivered datagram".

### 5.1 Why can't you simply run TLS records over UDP?

RFC 6347 and RFC 9147 highlight the fundamental differences:

1. **TLS records on a reliable stream** rely on implicit ordering; when datagrams drop or reorder, implicit sequence assumptions desynchronize. **DTLS** carries explicit record numbers/epochs needed to identify and decrypt records.
2. **TLS handshakes** follow a strict sequence assuming ordered delivery; **DTLS handshakes** require message sequence numbers, buffering, and reassembly/reordering.
3. Handshake messages like certificate chains can exceed one datagram: **DTLS supports handshake fragmentation and reassembly**.
4. With UDP, an attacker can spoof a source IP and make a server blast large responses at a victim: **DTLS includes return-routability/cookie mechanisms** for anti-amplification before trusting a connection.

DTLS must also handle **key epochs** across key transitions, delayed handshake messages, and record anti-replay. Record layouts **differ between DTLS 1.2 and DTLS 1.3**, so never assume identical wire bitfields.

### 5.2 Sequence numbers and epochs

```text
Concept:
   (epoch 1, record 100): protected(A)
   (epoch 1, record 101): protected(B)

Receiver may see record 101 before record 100.
DTLS identifies records by metadata, not by arrival position alone.
```

**Epoch** distinguishes key/state generations. **Sequence/record number** identifies records for reordering, integrity verification, and scheme-specific anti-replay. Never reuse record sequence numbers as payment `transactionId` or app `messageId`; the two layers have distinct threat models.

### 5.3 Anti-replay limits duplicate records, not exactly-once execution

A DTLS implementation may use a **sliding replay window**: detecting already-seen or too-old records and discarding them. Depending on version/policy, replay detection may be optional, window sizes vary, and delayed packets may cause valid records to be dropped.

If a client creates a **fresh record** containing the same payload `"transfer=42"`, that record has a new sequence number and passes DTLS anti-replay; yet it remains a duplicate business request. Thus the application layer still needs **idempotency keys**, business sequences, expirations, nonces, state, and replay policies for side-effecting actions.

### 5.4 DTLS handshake retransmission vs. data retransmission

In DTLS, the **handshake must complete** for both sides to agree on keys and authenticate. If a handshake flight drops, the protocol uses **timeouts and retransmission**. A JSSE application must manage `SSLEngine` timers and trigger regenerating handshake packets per the API contract.

Conversely, for **post-handshake application datagrams**, DTLS provides no automatic ACK, retransmission, or ordering. Real-time apps may intentionally drop stale data; systems needing guaranteed delivery must add reliability themselves or use a reliable transport.

**Only at the handshake layer** does DTLS enforce reliability to complete negotiation. Never conclude "UDP + DTLS always gives TCP-like retransmission".

### 5.5 Fragmentation: handshakes follow specific rules

DTLS supports fragmentation/reassembly for **handshake messages** larger than packet size. Each DTLS record aims to fit inside a single datagram; however, oversized UDP datagrams can still trigger **IP fragmentation** underneath if they exceed PMTU. Never treat DTLS handshake fragmentation as a general-purpose mechanism for splitting/reassembling **entire application files** or huge business messages.

For large payloads requiring full, ordered delivery, use TLS/TCP or a properly designed reliable protocol; if UDP is mandatory, implement segmentation, reassembly, per-message IDs, max sizes, timeouts, resend/ACK, and memory exhaustion guards.

## 6. TLS/DTLS security: shared goals, different transport properties

Common protocol pairs:

| Protocol | RFC | Transport model |
| --- | --- | --- |
| TLS 1.2 | RFC 5246 | Reliable byte stream |
| TLS 1.3 | RFC 8446 | Reliable byte stream |
| DTLS 1.2 | RFC 6347 | Datagrams |
| DTLS 1.3 | RFC 9147 | Datagrams |

DTLS 1.3 builds on TLS 1.3, yet RFC 9147 explicitly notes differences in **order protection / non-replayability** due to datagram semantics. Never claim DTLS guarantees in-order delivery merely because it provides confidentiality and integrity.

### 6.1 Java version differs from protocol version

Java 17 defines **standard names** for `SSLContext`: `TLS`, `TLSv1.2`, `TLSv1.3`, `DTLS`, `DTLSv1.0`, `DTLSv1.2`. Standardized names **do not guarantee** every Java runtime/provider implements every version. Java 17 may support DTLS 1.2 without **automatically implying DTLS 1.3 support** just because the DTLS 1.3 RFC was published.

Separate three questions:

- **Supported protocols?** `SSLEngine.getSupportedProtocols()` — does the provider implement/support it?
- **Enabled protocols?** `SSLEngine.getEnabledProtocols()` — which versions are allowed on this engine?
- **Negotiated protocol?** `engine.getSession().getProtocol()` **after a successful handshake** reveals the chosen version.

**Never fall back automatically** to TLSv1.0/DTLSv1.0 or disable algorithms when handshakes are incompatible. Review security policy and select an approved version.

### 6.2 QUIC is not DTLS

**HTTP/3 runs over QUIC on UDP**, yet **does not use DTLS**. RFC 9001 specifies that QUIC uses the **TLS 1.3 handshake and key schedule** to establish security, while QUIC itself handles packet protection, reliable streams, and congestion control. QUIC neither transports TLS application records like TLS/TCP nor simply uses `SSLContext.getInstance("DTLS")`.

Therefore:

- HTTPS HTTP/1.1/2 over TCP: **TLS/TCP**.
- UDP applications needing datagram protection: **DTLS/UDP** may fit.
- HTTP/3: **QUIC + TLS 1.3 integration** via a QUIC stack.

## 7. Java JSSE: `SSLSocket` vs. `SSLEngine`

Java Secure Socket Extension (**JSSE**) offers two implementation styles:

| Java API | Appropriate use |
| --- | --- |
| `SSLSocket` / `SSLServerSocket` | TLS over **stream** connections, performing I/O through TCP sockets |
| `SSLEngine` | TLS/DTLS crypto and handshake **decoupled from I/O**; app moves ciphertext itself |
| `SSLContext.getInstance("TLS")` | Creates a TLS context per provider |
| `SSLContext.getInstance("DTLS")` | Creates a DTLS context on supporting providers |
| `DatagramSocket` / `DatagramChannel` | Sends/receives **UDP datagrams**; provides no encryption/authentication itself |
| `SSLParameters.setMaximumPacketSize(...)` | Configures target network packet/record size, critical for DTLS |
| `SSLEngineResult` | Status, handshake status, and bytes consumed/produced during `wrap`/`unwrap` |

### 7.1 Stream TLS: the more concise API

The snippet below is a **code fragment**, runnable only if `hostname` is supplied and a matching server exists:

```java
// Inside a method declaring throws IOException, on Java 17+:
javax.net.ssl.SSLSocketFactory factory =
        (javax.net.ssl.SSLSocketFactory)
        javax.net.ssl.SSLSocketFactory.getDefault();
try (javax.net.ssl.SSLSocket socket =
        (javax.net.ssl.SSLSocket) factory.createSocket(hostname, 443)) {
    javax.net.ssl.SSLParameters p = socket.getSSLParameters();
    p.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(p);
    socket.startHandshake();
    // Application reads/writes InputStream/OutputStream using its own framing.
}
```

Verify the server certificate via trust manager and endpoint identity, pick versions/cipher suites per policy, and configure SNI/ALPN when needed. **Never create a trust-all trust manager** just to force a demo to run.

### 7.2 DTLS: `SSLContext("DTLS")` + `SSLEngine` + UDP transport

```text
App sends plaintext
       |
  SSLEngine.wrap()   -- creates DTLS protected record(s)
       |
DatagramSocket.send() -- sends UDP datagram
       |
     network
       |
DatagramSocket.receive() -- receives exact datagram bytes
       |
  SSLEngine.unwrap() -- verifies and decrypts record
       |
App processes validated plaintext
```

Creating the context/engine is **not enough** for security. A real handshake requires proper **key managers / trust managers / `SecureRandom`**, identity/peer selection, a UDP read/write loop, state machine, retransmission timers, and packet-size policy.

```java
// Illustrative fragment: creates engine only; NO handshake, NO data protection yet.
javax.net.ssl.SSLContext dtls = javax.net.ssl.SSLContext.getInstance("DTLS");
dtls.init(keyManagers, trustManagers, secureRandom);
javax.net.ssl.SSLEngine engine = dtls.createSSLEngine(peerHost, peerPort);
engine.setUseClientMode(true);
javax.net.ssl.SSLParameters p = engine.getSSLParameters();
p.setMaximumPacketSize(1200);
engine.setSSLParameters(p);
engine.beginHandshake();
// Requires a proper loop handling SSLEngineResult + DatagramSocket.
```

This is an **integration fragment**, not a standalone program: `keyManagers`, `trustManagers`, `secureRandom`, `peerHost`, and `peerPort` are system inputs/config, and `engine.beginHandshake()` performs no network communication by itself. The client cannot decrypt UDP datagrams until the handshake finishes.

## 8. Runnable Java 17 example: stream, datagrams, and JSSE capabilities

The program **`TlsDtlsTransportDemo.java`** lets you observe: (1) TLS and DTLS contexts supported by the provider, (2) DTLS packet-size parameter, (3) two TCP writes read as one stream, and (4) two UDP datagrams received as two distinct packets over **local loopback**.

**Mandatory caveat:** TCP and UDP here are **plain, unencrypted sockets**. Initializing `SSLContext`/`SSLEngine` is purely for API exploration; **no TLS/DTLS handshake**, no certificate verification, and no ciphertext occur on the wire. To genuinely protect payloads, use `SSLSocket` or `SSLEngine.wrap`/`unwrap` after a completed handshake.

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLParameters;

public final class TlsDtlsTransportDemo {
    private static boolean supports(SSLEngine engine, String protocol) {
        return Arrays.asList(engine.getSupportedProtocols()).contains(protocol);
    }

    public static void main(String[] args) throws Exception {
        SSLContext tls = SSLContext.getInstance("TLS");
        SSLContext dtls = SSLContext.getInstance("DTLS");
        tls.init(null, null, null);
        dtls.init(null, null, null);

        SSLEngine tlsEngine = tls.createSSLEngine();
        SSLEngine dtlsEngine = dtls.createSSLEngine();
        tlsEngine.setUseClientMode(true);
        dtlsEngine.setUseClientMode(true);

        System.out.println("TLSv1.2 supported: " +
                supports(tlsEngine, "TLSv1.2"));
        System.out.println("DTLSv1.2 supported: " +
                supports(dtlsEngine, "DTLSv1.2"));

        SSLParameters parameters = dtlsEngine.getSSLParameters();
        parameters.setMaximumPacketSize(1200);
        dtlsEngine.setSSLParameters(parameters);
        System.out.println("DTLS max packet bytes: " +
                dtlsEngine.getSSLParameters().getMaximumPacketSize());

        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (ServerSocket listener = new ServerSocket(0, 1, loopback);
             Socket client = new Socket(loopback, listener.getLocalPort());
             Socket peer = listener.accept()) {
            client.getOutputStream().write("one".getBytes(StandardCharsets.UTF_8));
            client.getOutputStream().write("two".getBytes(StandardCharsets.UTF_8));
            client.getOutputStream().flush();
            byte[] six = peer.getInputStream().readNBytes(6);
            System.out.println("TCP stream bytes: " +
                    new String(six, StandardCharsets.UTF_8));
        }

        try (DatagramSocket receiver =
                     new DatagramSocket(new InetSocketAddress(loopback, 0));
             DatagramSocket sender = new DatagramSocket()) {
            receiver.setSoTimeout(3000);
            byte[] first = "one".getBytes(StandardCharsets.UTF_8);
            byte[] second = "two".getBytes(StandardCharsets.UTF_8);
            sender.send(new DatagramPacket(first, first.length,
                    loopback, receiver.getLocalPort()));
            sender.send(new DatagramPacket(second, second.length,
                    loopback, receiver.getLocalPort()));

            String[] messages = new String[2];
            for (int i = 0; i < messages.length; i++) {
                byte[] buffer = new byte[64];
                DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                receiver.receive(packet);
                messages[i] = new String(packet.getData(), packet.getOffset(),
                        packet.getLength(), StandardCharsets.UTF_8);
            }
            System.out.println("UDP datagrams received: " + messages.length);
            System.out.println("UDP payloads (this local run): " +
                    String.join(" | ", messages));
        }
    }
}
```

Compile and run:

```bash
javac --release 17 TlsDtlsTransportDemo.java
java TlsDtlsTransportDemo
```

**Observed stdout in a JDK test environment with a DTLS 1.2 provider and loopback networking:**

```text
TLSv1.2 supported: true
DTLSv1.2 supported: true
DTLS max packet bytes: 1200
TCP stream bytes: onetwo
UDP datagrams received: 2
UDP payloads (this local run): one | two
```

**Analysis:**

1. `TLSv1.2 supported` and `DTLSv1.2 supported`: reflect **provider capability**. If the runtime lacks DTLS, `SSLContext.getInstance("DTLS")` may throw `NoSuchAlgorithmException`, or supported protocols will differ.
2. `DTLS max packet bytes: 1200`: confirms `SSLParameters` accepted the setting. It **does not** prove every IP path has a 1200-byte MTU or that a handshake completed.
3. TCP sends `"one"` then `"two"`, and `readNBytes(6)` returns `"onetwo"`, demonstrating streams do not preserve `write` message boundaries.
4. Two UDP `send` calls produce two separate datagrams; two `receive` calls read two datagrams. Loopback happened to preserve `"one"`, `"two"` order in this run, yet UDP **never guarantees** this across real networks.
5. `setSoTimeout(3000)` only prevents hanging forever if a UDP datagram is lost; on lossy networks, the program may throw `SocketTimeoutException`. That is **expected behavior on an unreliable transport**, not a bug in DTLS.

The program uses **localhost/loopback**, avoiding external servers or certificate fixtures. For the same reason it **does not test TLS/DTLS security**, only transport differences and engine creation. Never take that raw UDP snippet into an application needing encryption without implementing a full `SSLEngine` loop.

## 9. Handling DTLS `SSLEngine` properly

A DTLS engine separates **cryptography/handshake** from **UDP I/O**. A real DTLS application needs:

1. `SSLContext.getInstance("DTLS")`, initialized with trusted credentials/trust anchors and strong entropy.
2. `createSSLEngine(peerHost, peerPort)`, `setUseClientMode(true/false)`.
3. Configure protocols, cipher suites, packet size, peer identity, and client auth policy as needed.
4. `beginHandshake()`.
5. Handle `SSLEngineResult.HandshakeStatus`: **`NEED_TASK`**, **`NEED_WRAP`**, **`NEED_UNWRAP`**, **`NEED_UNWRAP_AGAIN`**, `NOT_HANDSHAKING`, and `FINISHED`.
6. Send `wrap` outputs as **UDP datagram(s)**; feed bytes of **actual received datagrams** into `unwrap`.
7. When the handshake is in `NEED_UNWRAP` and a network timeout fires, the app timer may need to **call `wrap` to trigger retransmitting the handshake flight**, per JSSE DTLS guidance.
8. Handle `BUFFER_OVERFLOW`, `BUFFER_UNDERFLOW`, `CLOSED`, `SSLException`, delegated tasks, peer validation, close alerts, and resource limits.
9. Send app data over the secure channel only after handshake and policy succeed.

`HandshakeStatus` table:

| Status | Action |
| --- | --- |
| `NEED_WRAP` | Call `wrap`, send properly formatted network output |
| `NEED_UNWRAP` | Wait for UDP data with timeout; may trigger DTLS handshake retransmit |
| `NEED_UNWRAP_AGAIN` | Call `unwrap` again on data **already buffered by the engine**, without waiting for a new datagram |
| `NEED_TASK` | Execute delegated tasks from `getDelegatedTask` |
| `FINISHED` | Handshake completion reported via operation result |
| `NOT_HANDSHAKING` | Engine is not currently handshaking |

`SSLEngineResult.Status` table:

| `Status` | Meaning |
| --- | --- |
| `OK` | Operation succeeded per state |
| `BUFFER_UNDERFLOW` | Input lacks enough bytes to process |
| `BUFFER_OVERFLOW` | Output buffer lacks enough space |
| `CLOSED` | Engine/direction is closed |

Never spin in a tight loop calling `unwrap()` without new input when status is not `NEED_UNWRAP_AGAIN`, to avoid **busy-spinning**. Never concatenate separate datagrams into a TCP-like stream and pass them to a single `unwrap`. JSSE specifies that DTLS `SSLEngine.wrap()` produces **at most one DTLS record per call** to map cleanly to UDP packets.

Below is **pseudocode**, not a standalone runnable JSSE program:

```text
context = DTLS context initialized with appropriate key/trust managers
engine  = context.createSSLEngine(peer identity)
engine.setUseClientMode(client or server)
configure maximum packet size, ciphers/protocols, authentication policy
engine.beginHandshake()

while handshake not complete:
  NEED_TASK          => run delegated tasks
  NEED_WRAP          => wrap(empty app buffer) => send ciphertext datagram
  NEED_UNWRAP        => UDP receive with timeout => unwrap(received datagram)
                        timeout => retransmit handshake flight via engine as documented
  NEED_UNWRAP_AGAIN  => unwrap engine-buffered data (no network receive)
  errors/buffer state=> react safely; close/fail handshake if invalid

after authenticated handshake:
  outgoing application data => wrap => send datagrams
  received UDP datagram     => unwrap => process authenticated app data
  application handles replay of commands, packet ordering/loss if required
```

**Why is this only pseudocode?** A secure DTLS server also needs key/certificate/PSK provisioning, peer/source-address association, cookie/anti-amplification protection, bounds, retransmission policies, receive queues, duplicate/reordered packet handling, concurrency, and graceful shutdown. Never compress all of that into 10 lines and call it a production DTLS server.

## 10. Packet size, path MTU, and avoiding IP fragmentation

With TCP, the transport layer manages segmentation. With UDP, an oversized datagram can undergo **IP fragmentation**, fail to traverse networks, or lose the entire datagram if a single fragment drops. DTLS encryption overhead also expands payload size relative to plaintext.

In Java, use:

```java
// Snippet inside a method with an already-created DTLS engine:
javax.net.ssl.SSLParameters p = engine.getSSLParameters();
p.setMaximumPacketSize(1200);
engine.setSSLParameters(p);
```

`setMaximumPacketSize` sets the **target maximum packet/record size**; real deployments must account for **IP + UDP headers, tunnel/VPN overhead, DTLS record header/tag**, PMTU, and protocol version/cipher suite. The number **1200** here is strictly an illustrative setting, not a universal network rule or fragmentation guarantee. Per JSSE guidance, never set it too low (e.g., under 256 bytes) since even small handshake messages would fragment excessively.

**Handshake fragmentation** supported by DTLS differs from **application fragmentation/reassembly**: if sending multi-megabyte application messages, use a dedicated protocol or reliable transport rather than expecting DTLS to split, reassemble, and retransmit the entire payload.

## 11. NAT, identity, and DoS considerations

- **NAT rebinding / source tuple:** a UDP source IP:port can change, yet cryptographic association must remain properly controlled. **Never** assume every JSSE provider supports DTLS Connection ID (CID) or migration.
- **Spoofing/amplification:** UDP permits source-IP spoofing; applications/servers must cap handshake allocations, rates, and bytes sent before verifying peers and session state; cookies/return-routability do not replace full DoS management.
- **Trust anchors/hostname/PSK identity:** DTLS has the same peer authentication needs as TLS. Never use trust-all certificate managers or skip endpoint identity checks.
- **Datagram replay:** DTLS record anti-replay does not replace business-layer idempotency and anti-replay.
- **Record errors:** data failing AEAD/MAC/tag checks must be rejected; never use provisional/partial plaintext from unauthenticated input.
- **Fallback:** if `SSLContext("DTLS")` or a cipher suite is unsupported by the runtime, configure an approved provider/protocol rather than silently falling back to plaintext UDP.
- **0-RTT/early data:** for protocols/versions supporting it, enforce a dedicated replay threat model; never use it for non-idempotent sensitive operations without proper safeguards.

## 12. Choosing TLS, DTLS, or QUIC in real scenarios

| Scenario | Typical choice | Explanation |
| --- | --- | --- |
| HTTPS/REST over TCP | TLS/TCP | Standard infrastructure, byte stream, certificate/hostname trust |
| gRPC/HTTP/2 | TLS/TCP | HTTP/2 handles framing over streams |
| Reliable, complete, in-order file transfer | TLS/TCP or suitable reliable transport | Avoid reinventing reliability over UDP |
| Game streaming continuous position state | DTLS/UDP may fit | Stale packets can be dropped; app manages sequencing |
| UDP telemetry, real-time reporting | DTLS/UDP may fit | Preserves datagrams while protecting integrity/confidentiality |
| Real-time voice/video | SRTP and proper key setup (e.g., DTLS-SRTP) | **Does not** mean all media packets ride inside DTLS |
| HTTP/3 | QUIC/UDP + TLS 1.3 integration | QUIC is not DTLS; uses its own transport/packet protection |
| Networks with firewalls blocking UDP | TLS/TCP or standards-compliant fallback | DTLS cannot bypass network policies automatically |
| Critical transactions needing exactly-once | Secure channel + app idempotency/replay state | Neither TLS nor DTLS replaces business controls |

DTLS can reduce transport-layer head-of-line blocking for certain apps, yet **is not a guarantee of lowest latency**. Under high packet loss, handshake retransmissions, missing PMTU discovery, NAT/firewall issues, or complex app logic, it can be slower or less stable than a well-tuned TCP/TLS stack.

## 13. Common mistakes and fixes

| Symptom / misconception | Reason | How to fix |
| --- | --- | --- |
| "`DatagramSocket` means DTLS" | Plain UDP socket does not encrypt | Pair with `SSLEngine` and handshake |
| "`SSLContext("DTLS")` creates a secure channel by itself" | Newly created context/engine has no authenticated peer | Init managers, run handshake, wrap/unwrap datagrams |
| "`SSLSocket` runs directly over UDP" | That socket API uses streams | Use `SSLEngine` for DTLS |
| "UDP kept order on loopback so it will in production" | Local observation is not a network guarantee | Test loss, reordering, and duplication |
| "DTLS retransmits application data" | Protocol only retransmits handshakes | App handles resend/ACK or uses reliable transport |
| "DTLS replay window prevents duplicate transactions" | A valid new record can carry the same message | Enforce application idempotency |
| `NoSuchAlgorithmException` for DTLS | Runtime/provider lacks DTLS implementation | Choose an approved provider; never fall back to plaintext |
| DTLS packet size errors | PMTU, buffers, IP fragmentation | Set `MaximumPacketSize`, budget MTU and max input |
| Stuck on `NEED_UNWRAP_AGAIN` | Waiting on network while bytes remain in engine | Call `unwrap` again without UDP receive |
| Handshake hangs at `NEED_UNWRAP` | Dropped handshake flight or missing timer | Manage timeout/backoff and trigger retransmission per JSSE |
| `BUFFER_UNDERFLOW`/`BUFFER_OVERFLOW` | Wrong input/buffer sizes or states | Supply full packet data, resize buffers, inspect `SSLEngineResult` |
| `SSLHandshakeException` | Cert/key/trust/version/suite/peer failure | Diagnose configuration; never disable verification |
| TCP `read()` returns less than message | Streams have no message boundaries | Length prefix + `readFully` with bounds |
| HTTP/3 called DTLS | QUIC uses TLS 1.3 handshake, not DTLS records | Pick a QUIC implementation |
| JDK has `TLSv1.3` so assume it has `DTLSv1.3` | Different protocol/version support | Inspect provider supported/enabled/negotiated |

## 14. Design checklist

- [ ] Determine whether you need a **reliable in-order byte stream** or **best-effort datagrams**.
- [ ] Clearly separate TLS/DTLS from TCP/UDP and application message framing.
- [ ] TLS streams use valid length-prefix/delimiter/framing; never assume `write` = `read`.
- [ ] DTLS enforces packet boundaries, MTU budget, input/buffer limits, and timeout policies.
- [ ] Pick the right Java API: `SSLSocket` for TLS streams, `SSLEngine` + datagrams for DTLS.
- [ ] Configure `SSLContext`, trust/keys, endpoint identity, and versions/ciphers per policy.
- [ ] DTLS engine loop handles `NEED_WRAP`, `NEED_UNWRAP`, `NEED_UNWRAP_AGAIN`, `NEED_TASK`, buffer statuses, and close.
- [ ] Include **handshake retransmission** without expecting automatic application-data retransmission.
- [ ] Record anti-replay never substitutes for idempotency / transaction deduplication.
- [ ] Test packet loss, reordering, duplication, malformed datagrams, MTU reductions, and NAT rebinding.
- [ ] Enforce DoS limits: packet/session/rate/memory/time bounds plus anti-spoofing/anti-amplification.
- [ ] Never assume the DTLS 1.3 RFC means every Java provider implements DTLS 1.3.
- [ ] Never use plain `DatagramSocket` demos to transmit sensitive data.

## 15. Exercises and self-assessment questions

**1.** Why don't two calls `SocketOutputStream.write("A")` and `write("B")` guarantee two `read()` calls on the peer?  
Because TCP/TLS is a byte stream with no application message boundaries; the receiver reads bytes in whatever chunks the system delivers.

**2.** Does DTLS automatically turn dropped datagrams into a complete stream like TCP?  
**No.** DTLS handshakes have retransmission; application data can be lost without automatic retransmission.

**3.** If UDP datagram `B` arrives before `A`, what enables DTLS to recognize the out-of-order record?  
Record sequence/epoch and cryptographic state; whether the application waits or drops stale data is a protocol/application decision.

**4.** Does `setMaximumPacketSize(1200)` guarantee 1200 application bytes will avoid IP fragmentation?  
No. IP/UDP/DTLS/tag/tunnel overhead and PMTU still apply; it is a configured network record cap.

**5.** Why aren't `SSLContext.getInstance("DTLS")` and `DatagramSocket` enough for security?  
They lack key/trust managers, peer validation, handshake execution, DTLS wrap/unwrap, and an I/O pipeline.

**6.** Does `NEED_UNWRAP_AGAIN` mean you should call `DatagramSocket.receive()` right away?  
No. It signals the engine still holds buffered handshake data; call `unwrap` again without waiting for a new packet.

**7.** Does DTLS record anti-replay stop replaying a validly signed money-transfer transaction?  
No. A fresh record can carry the same command again; idempotency keys or application replay state are required.

**8.** Does HTTP/3 use DTLS?  
No. HTTP/3 uses QUIC, which integrates the TLS 1.3 handshake yet uses its own packet protection, streams, and reliability.

**9.** Why must a DTLS server consider cookies and rate limits?  
UDP allows source spoofing, amplification attacks, and server state exhaustion.

**10.** Should you choose DTLS merely because it is "faster than TLS"?  
No. Decide based on datagram semantics, loss tolerance, latency trade-offs, MTU, firewall/NAT traversal, implementation availability, and operational cost.

## 16. Authoritative references

- [Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): `SSLEngine` section, DTLS handshake, `NEED_UNWRAP_AGAIN`, retransmission, maximum packet size.
- [Java SE 17 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): `SSLContext`/protocol names for TLS and DTLS.
- [Java SE 17 — `SSLContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): creating TLS/DTLS contexts.
- [Java SE 17 — `SSLEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html): `wrap`, `unwrap`, handshakes, and closing the engine.
- [Java SE 17 — `SSLEngineResult`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngineResult.html): operation status and handshake status.
- [Java SE 17 — `SSLParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): packet-size and endpoint-identification configuration.
- [Java SE 17 — `DatagramSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html): UDP I/O.
- [RFC 5246 — TLS 1.2](https://www.rfc-editor.org/rfc/rfc5246), [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446).
- [RFC 6347 — DTLS 1.2](https://www.rfc-editor.org/rfc/rfc6347): record/epoch/sequence, handshake retransmission, and replay.
- [RFC 9147 — DTLS 1.3](https://www.rfc-editor.org/rfc/rfc9147): datagram design, loss/reordering, handshake/record layer, replay considerations.
- [RFC 9001 — QUIC uses TLS](https://www.rfc-editor.org/rfc/rfc9001): QUIC uses TLS 1.3 handshake without DTLS records.
- [OpenJDK JEP 219 — Datagram Transport Layer Security](https://openjdk.org/jeps/219): DTLS integration in JSSE.

**Summary:** **TLS/TCP** protects a **reliable, ordered byte stream**; **DTLS/UDP** protects **datagrams that may drop or reorder**, adding handshake retransmission and record sequence/epoch while **promising no application-data reliability, ordering, or exactly-once delivery**. In Java, pick `SSLSocket` or `SSLEngine` according to your actual I/O model, and never mistake provider support for a handshaked secure connection.
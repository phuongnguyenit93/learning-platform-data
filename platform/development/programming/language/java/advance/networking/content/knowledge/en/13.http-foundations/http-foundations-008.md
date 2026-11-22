# HTTP/3: QUIC, Transport over UDP, and Support Requirements

## 1. Objectives and Core Ideas

HTTP/3 is the version that maps HTTP semantics (method, URI, status, headers, body) onto **QUIC**, instead of using a TCP connection like traditional HTTP/1.1 and HTTP/2. QUIC version 1 is standardized by RFC 9000, runs over **UDP**, and provides its own mechanisms to establish secure connections, deliver reliable ordered data streams, and perform flow control and congestion control. HTTP/3 is standardized in RFC 9114; QUIC's security layer uses TLS 1.3 per RFC 9001.

A common misconception is that **“HTTP/3 uses UDP” means “HTTP/3 loses data like a raw UDP application.”** UDP is the underlying datagram transport layer; **QUIC builds reliability, streams, and security** on top of it. At the same time, having UDP alone does not give you HTTP/3: the client, server, network, TLS, ALPN, discovery, and deployment configuration must all work together.

By the end of this lesson, you should be able to:
1. Accurately distinguish HTTP/1.1, HTTP/2, and HTTP/3, as well as the roles of TCP, UDP, QUIC, and TLS.
2. Explain how QUIC provides **reliable streams** while UDP has no built-in retransmission or ordering mechanism.
3. Understand the benefit of reducing **head-of-line blocking between QUIC streams** and its remaining limitations.
4. Describe TLS 1.3 integrated into QUIC, ALPN `h3`, 1-RTT/0-RTT handshakes, and replay risk.
5. Explain how a client learns that a server supports HTTP/3 via **Alt-Svc**, DNS **HTTPS/SVCB**, or explicit configuration.
6. List the support requirements at the client, server, load balancer/CDN, UDP path, certificate, and Java runtime.
7. Verify capabilities with practical tools without mistaking “the server has an Alt-Svc header” or “the machine has an open UDP port” for a successful HTTP/3 session.

## 2. Placing HTTP/3 in the Protocol Stack

```text
               Application HTTPS: GET /api/items
                           │
           ┌───────────────┴────────────────┐
           │                                │
     HTTP/1.1 / HTTP/2                    HTTP/3
           │                           HEADERS / DATA
      TLS over TCP                          │
           │                          QUIC streams
         TCP                        + integrated TLS 1.3
           │                     + recovery / flow control
           │                                │
           │                               UDP
           └───────────────┬────────────────┘
                           IP
                           │
                        Network

The URL outside the browser can still be:
https://api.example.com/items
Because the URL scheme is 'https', it does not specify the HTTP version on the wire.
```

With standard HTTPS:
- **HTTP/1.1:** each request/response uses HTTP/1.1 syntax; over standard HTTPS it is transmitted over TLS/TCP.
- **HTTP/2:** represents HTTP as binary frames and multiple streams over **a single TCP connection** protected by TLS in most web deployments.
- **HTTP/3:** represents HTTP as frames over **QUIC streams**, transmitted over **UDP**, with integrated TLS 1.3 security.

There is no concept of “HTTP/3 is HTTP/2 frames with TCP simply replaced by UDP.” HTTP/3 has its own stream mapping, control streams, QPACK, and error codes. While it preserves HTTP semantics (request/response), **the wire format is not directly compatible** with HTTP/2.

An HTTP/3 client needs **a QUIC implementation + an HTTP/3 implementation**. Having only a UDP socket library or TLS-over-TCP is not enough.

## 3. Comparing HTTP/1.1, HTTP/2, and HTTP/3

| Aspect | Typical HTTP/1.1 | Typical HTTP/2 | HTTP/3 |
| --- | --- | --- | --- |
| Transport over Internet | TCP | TCP | **QUIC running over UDP** |
| HTTPS Security | TLS over TCP | TLS over TCP | **TLS 1.3 integrated into QUIC** |
| Multiplexing unit | Connection; applications often reuse/limit pools | HTTP/2 streams over one TCP connection | **QUIC streams**, one request typically uses one bidirectional stream |
| Header compression | No mandatory shared mechanism like HPACK | HPACK | **QPACK** |
| Stream independence on network packet loss | TCP byte stream delays data following a missing byte | TCP-level head-of-line can affect multiple HTTP/2 streams sharing the connection | Another QUIC stream can continue being delivered even if one stream is missing bytes |
| Reliability | TCP | TCP | QUIC stream reliability and recovery |
| Connection establishment | TCP + TLS if HTTPS | TCP + TLS if HTTPS | Integrated QUIC/TLS; can reduce RTTs |
| Typical ALPN | `http/1.1` | `h2` | **`h3`** |
| Is UDP 443 required? | No | No | Must have a UDP path to the **advertised QUIC port**, commonly UDP/443 |
| When UDP path does not work | Not specifically affected since it uses TCP | Not specifically affected since it uses TCP | Compliant clients should retry over HTTP/TCP when permitted |

This table compares common architectures. HTTP/1.1 can also exist in systems without HTTPS; HTTP/2 has some alternative deployment forms; **HTTP/3 to an origin per RFC 9114 is tied to HTTPS**, and is not directly used over plaintext `http://`.

### What Remains Unchanged for Applications?

HTTP methods such as `GET`, `POST`, `PUT`, statuses `200`, `404`, caching semantics, and URIs must still follow HTTP Semantics. Business backends can continue receiving the same logical requests; a reverse proxy/CDN can **accept HTTP/3 on the client side and forward HTTP/2 or HTTP/1.1 to the origin**. Therefore, “client negotiated h3” does not automatically imply that every hop end-to-end is HTTP/3.

## 4. What Is QUIC: UDP Underneath, Reliable Transport on Top

UDP provides datagram-style messages between an IP address and a port. UDP **does not inherently guarantee** complete delivery, in-order delivery, deduplication, or connection state. QUIC uses UDP as the carrier for **QUIC packets**, and implements a transport protocol distinct from TCP.

A QUIC connection can have:
- **Connection IDs** to identify the connection independently of a fixed IP:port tuple in scenarios that support migration/NAT rebinding.
- **Packet numbers** for packet number spaces, used for loss detection and security; an old packet number is not simply resent verbatim.
- **ACK frames, loss detection, and retransmission of necessary information**, ensuring QUIC STREAM bytes are received reliably.
- **Congestion control, pacing, and flow control**, preventing unbounded sending just because UDP lacks TCP congestion control.
- **Multiple unidirectional/bidirectional streams** within the same connection, each with its own offset and byte ordering.
- **Integrated TLS 1.3** to derive secrets/keys, authenticate peers, and protect data.
- **Connection/path validation**, mechanisms to handle network address changes and limit amplification when a peer has not yet been validated.

Crucially: **QUIC is not an arbitrary protocol sending plaintext HTTP inside UDP datagrams.** It has headers, packet types, protected payloads, stream frames, flow control, and a complex state machine. When observing a UDP packet arriving on port 443, you cannot read the HTTP status, path, and body as you would with a plain string-based UDP datagram.

### Where Does Reliability Come From?

```text
HTTP/3 application produces:
  stream #0: request A bytes [0..N]
  stream #4: request B bytes [0..M]

QUIC splits bytes into STREAM frames
  + sends in QUIC packets over UDP
  + ACK, loss detection, retransmit necessary stream data
  + reassembles exact offsets for EACH stream

UDP datagrams may be lost/reordered:
  datagram 1 has bytes A[0..20] -> arrives
  datagram 2 has bytes A[21..40] -> lost
  datagram 3 has bytes B[0..15] -> arrives

QUIC:
  A waits for missing bytes to present stream A in order
  B can continue receiving complete data for stream B
```

This description illustrates **stream-level ordering**. Actual behavior depends on QUIC flow control, congestion control, which frames are coalesced into packets, and application parser capabilities. It should not be interpreted as “losing UDP datagrams has no impact on HTTP/3.”

## 5. UDP Datagram, QUIC Packet, and HTTP Request Are Three Different Units

Let us clearly distinguish:

1. **UDP datagram:** the unit of data that `DatagramSocket` or the operating system sends/receives over UDP; has a UDP header/length/checksum.
2. **QUIC packet:** a QUIC unit with a QUIC header and payload of QUIC frames; one UDP datagram can carry **one or more QUIC packets** according to QUIC coalescing rules.
3. **QUIC STREAM frame:** contains a slice of bytes for **one stream**, along with stream ID and offset; it does not necessarily equal one HTTP request or one HTTP/3 DATA frame.
4. **HTTP/3 frame:** an encoded unit at the HTTP/3 layer, such as `HEADERS` or `DATA` inside the appropriate QUIC stream.
5. **HTTP request:** application semantics consisting of method, URL/authority, headers, and optional body; an HTTP/3 request is typically sent on **a client-initiated bidirectional QUIC stream**.

```text
HTTP request #A         HTTP request #B
      │                       │
HEADERS + DATA           HEADERS + DATA
      │                       │
 QUIC stream A            QUIC stream B
      └──────────┬────────────┘
         QUIC packetizer: STREAM frames + control frames
                 │
          QUIC packets/keys
                 │
             UDP datagrams
                 │
                IP
```

**Incorrect:** “Each HTTP/3 request corresponds to one UDP datagram.” A large request can span many UDP datagrams; a single UDP datagram can also carry information from multiple streams and QUIC control frames. HTTP applications must process according to QUIC streams/framing, **not** per `DatagramSocket.receive` call.

## 6. Multiplexing and Head-of-Line Blocking

In HTTP/2, multiple request streams share **a single TCP byte stream**. If a byte earlier in the TCP stream is lost, TCP must wait to recover that byte before delivering subsequent bytes in order, even if they contain HTTP/2 frames for a different request. This is **TCP-level head-of-line blocking**.

QUIC creates multiple **streams with independent byte ordering**. If a packet carrying stream A data is lost, QUIC can still deliver completely received bytes of stream B to the application, rather than forcing B to wait for A's missing byte.

```text
HTTP/2 over a single TCP stream:
  Lost TCP byte ──► delivery of subsequent bytes is held back
                      └── can affect multiple HTTP/2 streams

HTTP/3 over QUIC:
  Loss in stream A ──► stream A waits for recovery
  Stream B has complete data ──► can still make progress
```

**Benefit:** reduces the impact of packet loss on other HTTP requests sharing the same connection.

**Limitations:**
- **Within a single QUIC stream**, data must still be presented in order; packet loss can block subsequent bytes of **that stream**.
- QUIC has **shared connection-level congestion control**. Packet loss can reduce the sending rate across **multiple streams**, even if stream B is not blocked by A's offset.
- If HTTP headers use the **QPACK dynamic table** and wait for a required update, a stream's headers can still be delayed; QPACK reduces but does not eliminate all dependencies.
- CPU, network bandwidth, flow-control windows, and server scheduling can also cause delays.

Therefore, the accurate phrasing is: **HTTP/3 eliminates TCP-level head-of-line blocking between QUIC streams at the transport layer**, rather than **eliminating all latency or blocking**.

## 7. TLS 1.3 Is Part of QUIC, Not Conventional SSL/TLS-over-TCP

In traditional HTTPS:

```text
HTTP/2 ──► TLS records ──► TCP ──► IP
```

With HTTP/3:

```text
HTTP/3 ──► QUIC (TLS 1.3 keys/handshake) ──► UDP ──► IP
```

QUIC uses the **TLS 1.3 handshake** to authenticate peers and derive traffic secrets, but TLS records are not carried the same way as in standard TLS-over-TCP. QUIC places handshake data in CRYPTO frames, performs its own packet protection, and manages keys as specified in RFC 9001. You **do not** take `SSLSocket` and put `DatagramSocket` underneath it to create HTTP/3.

The server still needs:
- A valid TLS certificate for the hostname (typically an X.509 certificate).
- The corresponding private key.
- A trust chain/CA trusted by the client.
- A compatible TLS 1.3 and QUIC stack.
- Proper endpoint identity verification policies, without disabling certificate verification.

**QUIC does not make HTTPS less secure just because it uses UDP.** Encryption and integrity are properties of QUIC/TLS. However, metadata such as IP, port, and certain packet routing fields remain observable; Initial packet protection is not intended to hide the entire handshake from eavesdroppers because Initial keys can be publicly derived per protocol rules. Do not infer that all network metadata is secret.

## 8. Handshake, 1-RTT, 0-RTT, and Replay Risk

For a new connection, QUIC integrates TLS 1.3 to establish both the connection and security without needing **one TCP handshake round trip followed by another TLS round trip** like conventional HTTPS-over-TCP. Under suitable conditions, the TLS/QUIC process can complete in roughly **1 round trip**; 0-RTT can allow sending early application data when resuming a connection with prior state.

```text
New QUIC connection, conceptual model:

Client  ── Initial/ClientHello ───────► Server
Client  ◄─ handshake responses ─────── Server
Client  ── Finished/1-RTT data ──────► Server
            (actual structure depends on handshake)

Returning connection with suitable resumption state:

Client  ── Initial + 0-RTT early data ► Server
Client  ◄─ handshake responses ─────── Server

Early data carries REPLAY risk, not a guarantee of an
exactly-once confirmed request.
```

Key points to understand:
- **1-RTT does not mean “a request takes exactly 1 RTT”**; it describes the handshake layer under no-loss conditions and appropriate policies. DNS, path validation, congestion, and server processing still add latency.
- **0-RTT is not enabled by default on all clients/servers**. It requires session resumption and compatible limits/configurations.
- **0-RTT early data can be replayed**. Applications must not place operations with unwanted side effects (payments, state mutations, non-idempotent work) into early data without dedicated protection.
- HTTP has related mechanisms such as the `425 Too Early` response to handle requests arriving too early in certain scenarios. Accepting/rejecting/retrying early data must be implemented with proper policy by both HTTP client and server.
- A successful TLS handshake **does not** by itself prove that a business request was processed exactly once. Retries require idempotency keys, request IDs, and application-layer semantics.

Per RFC 9001, servers and clients must manage 0-RTT replay risk. In new systems, it is safest **not to assume 0-RTT is used** when evaluating performance or request correctness.

## 9. HTTP/3 Frames and Streams: Specific Structure

HTTP/3 has its own framing over QUIC streams:

- A normal request is sent on a **client-initiated bidirectional QUIC stream**.
- Requests and responses contain `HEADERS`, `DATA`, and potentially other frames per the HTTP/3 grammar. The response uses **the same corresponding request stream**.
- Each endpoint opens **a unidirectional control stream** and sends `SETTINGS` as its first frame per RFC 9114; this is **connection-level** configuration, not per-request.
- There are unidirectional streams for **QPACK encoder/decoder instructions**.
- Server push is an **optional feature** of HTTP/3; you should not assume it is enabled in every client/server.

A logical example:

```text
QUIC connection (ALPN = h3)
│
├── client control stream (SETTINGS, ...)
├── server control stream (SETTINGS, ...)
├── QPACK encoder/decoder instruction streams (when needed)
│
├── request stream A (bidirectional)
│     HEADERS(:method=GET, :path=/a, ...)
│     DATA(response body chunks...)
│
└── request stream B (bidirectional)
      HEADERS(:method=GET, :path=/b, ...)
      DATA(...)
```

This diagram only expresses logical structure, **not a wire byte dump**. There is no separate TCP connection per request. QUIC transport stream IDs/offsets handle byte ordering, and the HTTP/3 layer decodes headers/body.

### QPACK Replaces HPACK

HTTP/2 uses **HPACK**, whereas HTTP/3 uses **QPACK** (RFC 9204) to compress headers efficiently when QUIC streams can be delivered independently. QPACK supports static/dynamic tables and instruction streams; it limits blocking caused by dynamic table dependencies via configuration/limits, though it is not “never blocks.”

Typical Java applications do not implement QPACK directly: the HTTP/3 library is responsible for it. If you build HTTP/3 from `DatagramSocket` yourself, you must implement the full QUIC transport, QPACK, HTTP/3 control streams, error handling, SETTINGS, and security requirements; this is not a practical introductory exercise.

## 10. ALPN h3: Application Protocol Negotiation

**ALPN (Application-Layer Protocol Negotiation)** lets the client and server agree on the supported application protocol. For standardized HTTP/3, the standard ALPN token is **`h3`**. For HTTP/2 over TLS, the token is typically `h2`; for HTTP/1.1 it is `http/1.1`.

```text
TCP/TLS pathway:
  ALPN client offers h2, http/1.1
  server selects h2 or http/1.1 based on configuration

QUIC/TLS pathway:
  QUIC client offers h3 (inside integrated TLS handshake)
  QUIC server selects h3
  HTTP/3 stream protocol begins once conditions are met
```

You **cannot** simply add `"h3"` to Java 17's `SSLSocket` or `HttpClient` and expect TCP to turn into QUIC. The QUIC transport layer and handshake must actually exist.

Nor can you infer HTTP/3 support merely from:
- The server having **TLS 1.3 over TCP**: it needs QUIC/TLS 1.3 over **UDP**.
- The server returning `Alt-Svc: h3=...`: this is an **advertisement**, not proof that the client can connect.
- Port TCP/443 being open: HTTP/3 typically needs **UDP/443** separately.
- A browser having HTTP/3: a separate Java HTTP client may **not** have HTTP/3.

If ALPN selects another protocol or the handshake/transport fails, the client must handle it according to its capabilities/fallback policy. Do not send HTTP/3 frames on a connection that actually negotiated HTTP/2.

## 11. Discovering HTTP/3 via Alt-Svc

A client may first reach an origin via HTTPS over TCP/HTTP/2 or HTTP/1.1. The server returns an **Alt-Svc** header to advertise an endpoint supporting another protocol. For example:

```http
HTTP/2 200
alt-svc: h3=":443"; ma=86400
content-type: text/html
```

Meaning:
- `h3` is the protocol ID for HTTP/3.
- `":443"` suggests **the same hostname** as the origin, on port **443** (for HTTP/3, via QUIC/UDP).
- `ma=86400` specifies the advertisement cache lifetime (in seconds) per Alt-Svc semantics.
- The client may **attempt** an HTTP/3 connection on a suitable subsequent access, but is not required to choose it.

Alt-Svc can also advertise a **different host/port**, for example `Alt-Svc: h3="alt.example.com:8443"; ma=3600`. The client must still verify that the alternative endpoint is authorized to serve the **original origin**, including certificate validation and proper authority rules. Alt-Svc **does not** allow skipping TLS identity checks or arbitrarily changing origin semantics.

Essential notes:
- Alt-Svc can appear on an **HTTP/1.1 or HTTP/2** response; it does not by itself prove the response used HTTP/3.
- Clients may cache Alt-Svc and upgrade on a later request; thus a first request not using HTTP/3 **does not** prove the infrastructure lacks support.
- Clients may ignore Alt-Svc due to lack of HTTP/3 support, administrative policy, blocked ports, or failed security checks.
- Advertising HTTP/3 when the UDP listener is not running only wastes client time trying and falling back; it is best to publish it only after end-to-end testing.

RFC 9114 `3.1.1` explains HTTP alternative services via `Alt-Svc` or the HTTP/2 `ALTSVC` frame.

## 12. DNS HTTPS/SVCB Records as Another Discovery Mechanism

RFC 9460 describes **HTTPS** and **SVCB** DNS resource records. An HTTPS record can publish alternative endpoints, ALPN protocols, and service parameters (such as port). This allows a client to learn about the HTTP/3 option **before** receiving an Alt-Svc response from the origin.

Example record **illustrating syntax** (not real DNS data for any domain):

```dns
example.com.  300  IN HTTPS 1 . alpn=h3,h2
```

Idea: the HTTPS service for the origin may support `h3` and `h2`. When using real records, a client must follow RFC 9460 rules regarding TargetName, ServiceMode/AliasMode, mandatory keys, port, alpn, and DNS/transport security. Do not just grep for `h3` and conclude that a request definitely used HTTP/3.

Do not confuse:
- **DNS A/AAAA:** resolves IP addresses; does not by itself declare HTTP/3.
- **DNS HTTPS RR:** describes connection parameters/alternative service options; supporting clients may use it.
- **Alt-Svc:** advertises HTTP alternative services at the HTTP layer.
- **ALPN negotiation:** the protocol actually selected **on a specific TLS/QUIC connection**.
- **Response protocol version:** actual evidence of whether the request was served using HTTP/3.

A DNS diagnostic tool if `dig` is available:

```bash
dig HTTPS example.com
```

This command queries **DNS metadata**, not a QUIC connectivity test. The record might not exist, and you should not assume `example.com` has HTTP/3. Different clients have different discovery and precedence policies; check the specific client/runtime documentation.

## 13. Support Requirements: Not Just a Server HTTP/3 Flag

For an HTTP/3 request to actually succeed, every link in the chain must be compatible:

| Component | Requirement | If Not Met |
| --- | --- | --- |
| **Client** | Has QUIC v1 + HTTP/3 implementation; supports ALPN `h3`, appropriate TLS/QUIC, trust store | Even if the server supports it, the client cannot initiate HTTP/3 |
| **Server / edge** | Listens for QUIC/UDP on advertised port, has HTTP/3 stack, certificate/key, ALPN `h3` | UDP reaches server but there is no QUIC HTTP/3 handler |
| **Transport path** | Outbound/inbound UDP to right address/port; firewall/NAT/LB allows traffic and responses | Handshake timeout; may have to fall back to TCP |
| **TLS** | TLS 1.3 integrated with QUIC, valid certificate for origin, proper hostname validation | QUIC/TLS handshake or authority validation fails |
| **HTTP/3 protocol** | SETTINGS, request/control streams, QPACK, frames implemented per RFC | Transport may come up, but HTTP/3 protocol still errors |
| **Discovery/policy** | Client knows to try h3 (Alt-Svc, HTTPS RR, or direct config), not disabled by enterprise policy | May stay on H2/H1 even though H3 endpoint works |
| **Reverse proxy/CDN/LB** | Properly supports or passes through QUIC/UDP and forwards HTTP to suitable upstream | Edge may block UDP or only terminate TLS-over-TCP |
| **Java application** | HTTP client/runtime or library **actually has HTTP/3**, not just `DatagramSocket` | Cannot request HTTP/3 via a nonexistent option |

**Conclusion:** missing just **one** link can cause end-to-end HTTP/3 for that request to fail. You must verify both the transport and the protocol actually negotiated, not just “HTTP/3 is enabled in config.”

### Common Ports

For a URL `https://api.example.com/` without an explicit port, the default HTTPS origin port is **443**. Many deployments open **TCP/443** for HTTP/2/HTTP/1.1 and **UDP/443** for HTTP/3 simultaneously. HTTP/3 can also run on **another UDP port**, provided the endpoint/port is validly advertised.

Not every H3 deployment is required to use UDP/443; RFC 9114 allows servers on other UDP ports. However, configuring UDP/443 aligns with standard HTTPS origins and makes firewall policies easier to reason about.

## 14. Same HTTPS URL, Multiple Transport Paths

```text
Client sends GET https://api.example.com/items
                     │
             HTTP stack chooses protocol
                     │
     ┌───────────────┴──────────────────┐
     ▼                                  ▼
 Try HTTP/3                       HTTP/2 or HTTP/1.1
 QUIC/TLS 1.3                     TLS + TCP
 UDP:443 (common)                 TCP:443
     │                                  │
     ▼                                  ▼
 Edge / CDN / origin               Edge / CDN / origin
     │                                  │
     └────────────► HTTP service ◄──────┘
                        │
                 JSON/response
```

Both paths can serve **the same URI** with the same HTTP semantics. The differences lie in the transport layer, framing, and connection establishment; routing, authentication, and business logic must still adhere to origin/request semantics.

A CDN may use:
- **Client → CDN:** HTTP/3 over QUIC/UDP.
- **CDN → origin:** HTTP/2 over TLS/TCP.
- **Origin application:** traditional HTTP framework.

Observing origin logs reporting `HTTP/2` **does not refute** that external users used HTTP/3 with the CDN. To prove it, measure **the exact hop**: browser/network/client trace, edge access logs, and per-hop negotiated protocol information.

## 15. Fallback When UDP/QUIC Cannot Connect

A production system must account for cases where:
- A firewall blocks outbound UDP or the return path.
- A corporate network/proxy only allows TCP/TLS.
- NAT or connection tracking drops UDP packets.
- UDP/443 is not routed to the listener.
- A middlebox causes the QUIC handshake to fail.
- The server only enables HTTP/2/TCP or does not yet support ALPN `h3`.
- The certificate/hostname is invalid on the QUIC listener.
- UDP path MTU/fragmentation drops large packets.

RFC 9114 recommends that clients **try TCP-based HTTP versions** when QUIC connectivity fails. A fallback-capable client can fall back to HTTP/2 or HTTP/1.1 **over HTTPS/TCP**. This is not a “downgrade to plaintext HTTP.”

```text
H3-capable client
  │
  ├─ QUIC/UDP + ALPN h3 succeeds ──────► use HTTP/3
  │
  └─ QUIC fails / policy disallows ────► HTTPS/TCP
                                          │
                                          ├─ ALPN h2 -> HTTP/2
                                          └─ http/1.1 -> HTTP/1.1
```

**You must not state “HTTP/3 will definitely work because TCP/443 is reachable.”** TCP and UDP are two different transport protocols with different firewall/NAT/LB rules. Testing must test **UDP** to the right endpoint and perform a real HTTP/3 handshake.

### Fallback Also Needs Control

- An **H3-only** client may choose to fail instead of falling back per measurement/testing requirements.
- A general client may race or delay one transport to optimize user experience, depending on the implementation.
- If a business request has side effects (POST creating an order, payment), fallback/retry must follow idempotency/duplicate-handling policies; transport retries do not provide exactly-once semantics.
- If the QUIC certificate is **invalid**, a security error must not be treated as a reason to skip certificate verification over TCP.
- Blocking UDP can make HTTP/3 unavailable, while **secure HTTPS over HTTP/2 still works** if the TCP path and TLS are valid.

## 16. Handshake and Timeouts When Attempting HTTP/3

Timeouts to consider:
1. **DNS resolution** and HTTPS RR lookup.
2. **UDP path establishment:** is there a response to QUIC Initial?
3. **TLS/QUIC handshake timeout:** QUIC receives packets but cannot authenticate/complete.
4. **HTTP/3 control stream/SETTINGS readiness:** transport coming up does not mean the HTTP/3 connection is ready to process requests.
5. **Response header/body timeout:** the server-side application may be slow even when QUIC works.
6. **Idle timeout:** the peer or NAT may expire state when the connection is idle.

Do not “optimize” by aggressively retrying hundreds of requests when H3 fails. Clients need bounded attempts/deadlines and standard Alt-Svc state caching to avoid repeated timeouts on networks that do not support UDP.

Per RFC 9000, a client's QUIC **Initial datagram** has minimum size requirements (a UDP datagram carrying Initial needs at least a 1200-byte payload) to support path validation and anti-amplification limits. Therefore, “a few-byte UDP ping succeeded” is not enough to prove QUIC handshake packets can traverse the network.

## 17. Infrastructure Requirements: Firewall, NAT, Load Balancer, CDN, and MTU

### Firewall and UDP/443

If a server advertises `h3=":443"`:
- Allow inbound **UDP/443** from clients to the H3 endpoint.
- Allow return UDP responses, with corresponding stateful firewall/NAT rules.
- Keep **TCP/443** open when normal HTTPS fallback is desired.
- If a CDN terminates QUIC, configure UDP rules properly at the edge; the origin may not need UDP/443.

Opening only TCP/443 does not open QUIC/UDP. Opening inbound UDP without a proper outbound return path is also insufficient.

### Load Balancing

QUIC has connection IDs and can survive network path changes within protocol limits. Load balancers must:
- Properly support/forward UDP, without assuming a QUIC connection is always a fixed TCP 5-tuple.
- Maintain consistent routing to QUIC connection state or use an architecture capable of handling connection IDs.
- Manage idle timeouts, retry/address validation tokens, and connection draining.
- Avoid mixing data across multiple connections when source addresses change.

Not every layer-7 reverse proxy with HTTP/2 supports HTTP/3. Check the specific proxy or CDN **version/build/feature flags**, **port/protocol listener**, and Alt-Svc advertisement configuration.

### MTU and UDP Packet Loss

A UDP datagram may exceed the path MTU and have to be fragmented at the IP layer or be dropped. Losing a single fragment can prevent the entire datagram from reaching QUIC. QUIC has requirements for UDP datagram size and PMTU discovery; the transport/path must allow the necessary packets and handle black-hole scenarios.

In networks with many VPNs/tunnels and low MTU, a valid TCP ping/traceroute does not prove appropriately sized QUIC traffic can pass. Measure actual handshakes and responses, and inspect loss, ICMP packet-too-big/PMTU, and QUIC traces if available.

## 18. QUIC Connection ID, NAT Rebinding, and Connection Migration

One difference from TCP is that a QUIC connection has **Connection IDs**, allowing endpoints in certain scenarios to preserve a connection when the IP/port changes (e.g., NAT rebinding, switching from Wi-Fi to a mobile network), instead of being strictly bound to a TCP 4-tuple.

However:
- Migration **is not** a promise that “every HTTP/3 connection seamlessly survives network switches.” It requires implementation support, policy, and a valid new path.
- QUIC has **path validation** mechanisms and may require challenge/response to avoid sending large amounts of data to a spoofed address.
- Servers must enforce **anti-amplification**. Per RFC 9000, before validating a peer's address, sending to an unvalidated address is limited to roughly **3 times the number of bytes received** from that address.
- Load balancers/CDNs must handle connection IDs and routing consistently with migration.
- IP/port changes must never turn into skipping TLS identity verification or origin ownership checks.

Connection IDs also have privacy implications: improper ID reuse can enable connection tracking. Implementations must follow corresponding rotation/privacy mechanisms and not use a connection ID as an immutable user identifier.

## 19. Java 17: Does HttpClient Have Built-in HTTP/3 Support?

**In the Java SE 17 API**, the `java.net.http.HttpClient.Version` enum only has:
- `HTTP_1_1`.
- `HTTP_2`.

There is no `HTTP_3` in that enum. Thus, Java 17's `java.net.http.HttpClient` **does not provide a built-in HTTP/3 option** through the `HttpClient.Version` API. Configuring:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

**prefers HTTP/2**, **not** HTTP/3. Depending on the server/proxy/implementation, an actual request may still be served over HTTP/1.1 if HTTP/2 cannot be negotiated. `client.version()` reports the **preferred version**, not proof of the actual protocol of a network response. `HttpResponse.version()` is what provides the protocol used for that response.

For H3 in Java, you need to **explicitly choose a QUIC + HTTP/3 client/server implementation** compatible with your JDK, OS, TLS provider, and deployment model; review the official documentation of the chosen library/version, including native components if any. You cannot use `DatagramSocket` to send HTTP/1.1 strings to UDP/443 and call that HTTP/3.

**Version caveat:** APIs/capabilities may differ in newer JDKs or third-party libraries. This lesson fixes on **Java SE 17**, and you should not infer from it that no future Java version will ever have H3. When upgrading your runtime, consult the documentation for the **exact version deployed**.

## 20. Runnable Java 17+ Example: Checking JDK HTTP Capabilities Without Sending Network Traffic

Save as **`Http3Java17Capabilities.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.util.Arrays;

public class Http3Java17Capabilities {
    public static void main(String[] args) {
        HttpClient.Version[] versions = HttpClient.Version.values();
        System.out.println("versions=" + Arrays.toString(versions));
        boolean hasHttp3 = Arrays.stream(versions)
                .anyMatch(v -> "HTTP_3".equals(v.name()));
        System.out.println("builtInHttp3=" + hasHttp3);

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .build();
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/")).GET().build();
        System.out.println("preferred=" + client.version());
        System.out.println("scheme=" + request.uri().getScheme());
        System.out.println("networkRequests=0");
    }
}
```

Compile in a JDK 17 environment:

```bash
javac Http3Java17Capabilities.java
java Http3Java17Capabilities
```

Stdout when run on a JDK with `HttpClient.Version` matching the Java 17 API:

```text
versions=[HTTP_1_1, HTTP_2]
builtInHttp3=false
preferred=HTTP_2
scheme=https
networkRequests=0
```

Verified compiling with `javac --release 17` and running with the output above. The program **opens no HTTP connections**, so it always prints `networkRequests=0`; `https` in the URI **does not prove** the network used h3.

Explanation:
1. `HttpClient.Version.values()` reflects the **built-in API** versions exposed by the enum.
2. Checking the string `"HTTP_3"` avoids trying to reference an enum constant that does not exist in Java 17.
3. `client.version()` is the configured **preferred** version, not the ALPN result of a network request.
4. Do not use this `HttpClient` to “test QUIC” because it has no HTTP/3 capability in the Java 17 API.

### A Code Snippet to Inspect the Actual Response Version

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/")).GET().build();
HttpResponse<Void> response = client.send(
        req, HttpResponse.BodyHandlers.discarding());
System.out.println(response.version());
```

This is a **dependent snippet** requiring a configured `HttpClient client`, `HttpRequest`, `HttpResponse`, and `URI` imports. It **requires Internet access**, a trusted server, and an environment allowing HTTPS; stdout may be `HTTP_2` or `HTTP_1_1`, and must not be assumed fixed. With this Java 17 HTTP client, the snippet does not perform HTTP/3.

## 21. Testing Real HTTP/3 with curl: Distinguishing curl Versions and Build Flags

Using `curl` (a build with HTTP/3 support) to test a real endpoint is an easy way to observe the protocol. **Before testing a request**, check the build:

```bash
curl --version
```

In the `Features:` line, **`HTTP3`** must be present to use HTTP/3 (exact naming and display depend on the build). **A recent curl version number does not automatically guarantee the HTTP3 feature was compiled in.** A new curl build without HTTP3 still cannot send HTTP/3 requests.

Two diagnostic commands (the URL is an **illustrative public HTTPS address**; h3 support may vary by endpoint and network):

```bash
curl --http3-only -I -v https://www.cloudflare.com/
curl --http3 -I -v https://www.cloudflare.com/
```

- **`--http3-only`:** requires HTTP/3 **without fallback**; if the QUIC handshake or HTTP/3 cannot be established, the command fails. Suitable for proving that **the h3 path actually works** when it succeeds.
- **`--http3`:** **tries HTTP/3 but may fall back** to HTTP/2/HTTP/1.1 if H3 is slow or fails. A successful response from this command **does not prove** it used HTTP/3; you must check the verbose output/actual protocol.
- **`-I`:** requests headers; servers may handle HEAD specially. If you want to test GET instead of HEAD, omit `-I` and use appropriate output handling.
- **`-v`:** displays connection/protocol details, though logs may contain sensitive information; use in controlled environments.

If `curl --version` does not list HTTP3, **do not conclude the server lacks support** when `--http3-only` errors out. You must use a curl build with a properly compiled HTTP/3 backend or another H3-capable client.

### Checking Alt-Svc Is Not a Complete h3 Check

```bash
curl -I https://www.cloudflare.com/
```

If the response includes `Alt-Svc: h3=":443"`, that is an **advertisement**. That first response may have run over HTTP/2; to confirm HTTP/3 was used, you must check the **actual protocol** of the QUIC connection or use `--http3-only` on an H3-capable tool.

The command `curl --alt-svc <cache-file> ...` can save/read Alt-Svc per curl's documentation. However, it still requires **HTTP/3 support in the build** to upgrade to h3; having only the alt-svc feature does not replace QUIC support.

## 22. Distinguishing Error Types When Diagnosing HTTP/3

| Observation | Likely Cause | Diagnostic Step |
| --- | --- | --- |
| TCP HTTPS works fine, `--http3-only` times out | UDP/443 blocked, QUIC listener/route issue, server lacks h3 | Check UDP rules, H3 listener, LB, path MTU, and QUIC handshake logs |
| `curl` reports HTTP3 option unsupported | Client build lacks HTTP3 backend | `curl --version`, install/build client with HTTP3 feature |
| `Alt-Svc: h3` appears but next request is still H2 | Client lacks support, cache/policy, UDP blocked, or H3 failed | Check features, cache, DNS/Alt-Svc, verbose request protocol |
| QUIC handshake reaches server but cert error | Invalid CA/hostname/certificate SAN | Verify correct origin, chain, certificate, SNI/identity policy |
| QUIC negotiation does not select `h3` | Server/client do not share HTTP3 ALPN | Check QUIC/HTTP3 stack versions and ALPN config |
| UDP port open but HTTP3 error | QUIC transport exists, but HTTP/3 SETTINGS/QPACK/streams fail | Use H3-capable client, server traces, and error codes |
| H3 works on one network, fails on another | Different firewall/NAT/VPN/MTU/proxy | Compare UDP/TCP paths, metrics, packet sizes, network policy |
| CDN reports H3 but origin logs H2 | CDN terminates H3 and connects to origin via H2/TCP | Check edge protocol logs; distinguish each hop |
| H3 uses high CPU | TLS/QUIC crypto, pacing, implementation, or load | Benchmark CPU/profile, tune configuration and library |
| H3 is not faster than H2 | Low RTT/loss, small workload, cache, server bottleneck | Measure RUM/latency/loss across environments; do not expect gains by default |
| Payment request duplicated on retry | Retry/0-RTT or network failure left outcome ambiguous | Idempotency key, app-level ack, avoid unsafe 0-RTT |

**Do not conclude from a single indicator.** Combine: H3-capable client, discovery, UDP path, TLS handshake/ALPN, HTTP response protocol, and server/edge logs.

## 23. How to Verify with Browser and Observability

In a browser that supports HTTP/3, DevTools can display the request **Protocol** column (depending on the version, selectable via the Columns menu). A request marked **h3** is an observation at the **browser → edge/origin hop** for that load. Not every browser always attempts HTTP/3:
- Changing network policies or browser flags.
- Alt-Svc cache/HTTPS RR state.
- Corporate proxy/VPN.
- CDN response and cache.
- Multiple requests reusing an existing connection or trying fallback.

On the server/CDN side:
- Log the **negotiated protocol** at the edge (h3/h2/http1).
- Measure QUIC handshake counts, latency, failure codes, and retries/fallbacks.
- Observe UDP packet loss/PMTU issues, and NAT rebinding/path migration events if the stack supports them.
- Separate **client-facing** metrics from **origin-facing** metrics.
- Do not log QUIC secrets or sensitive plaintext bodies.

Seeing an `Alt-Svc` header in an HTTP response does not equal “this request ran over HTTP/3,” and seeing only TCP access logs on the backend does not equal “users are not using H3.”

## 24. Testing When Enabling HTTP/3 on a Real Server

An ordered test plan:

1. **Capability:** confirm the server stack/reverse proxy/CDN **version and build** support H3, QUIC v1/TLS 1.3, and ALPN `h3`.
2. **Listener:** confirm the process/edge is listening on the **right UDP port** (usually 443), while TCP/443 remains active to support fallback.
3. **Identity:** valid certificate for the origin, trust chain, SAN, TLS policy, and appropriate SNI/ALPN.
4. **Discovery:** enable Alt-Svc or HTTPS DNS records **only when the endpoint is truly ready**; configure controlled max-age to limit the blast radius of a faulty rollout.
5. **Client test:** use a client with the HTTP3 feature, test `--http3-only` and inspect the negotiated protocol; also use a browser if you want to verify discovery.
6. **Blocked UDP:** from an environment that blocks UDP, confirm the client falls back to HTTPS/TCP without sending plaintext.
7. **Network quality:** test high latency, packet loss, mobile networks, VPNs, MTU changes, and NAT/timeouts.
8. **Multiple requests:** test parallel streams, large uploads, downloads, streaming responses, and large HTTP headers.
9. **Application semantics:** ensure auth, cookies, redirects, CORS, caching, logging, rate limits, and retry/idempotency behave the same as on other HTTP versions.
10. **0-RTT policy:** allow early data only in safe cases; guard against replay, and test `425 Too Early` if the implementation applies it.
11. **Rollout:** monitor h3 negotiation rate, fallback rate, error rate, p95 latency, CPU, and per-network outcomes; throttle/roll back when needed.
12. **Certificate renewal:** verify certificate/key updates on both the TLS-over-TCP and QUIC listeners, avoiding “TCP updated but H3 is serving the old cert.”

You do not need to write a QUIC transport from scratch to perform these steps; use a standardized implementation and H3-capable tools.

## 25. Advantages, Trade-offs, and Real-World Performance

### Potential Benefits

- Reduces TCP-level HOL blocking across HTTP/3 request streams.
- New connection establishment can require fewer RTTs than two-stage TCP + TLS 1.3.
- 0-RTT resumption can reduce latency in safe/supported scenarios.
- Connection IDs/path migration help some connections adapt when network addresses change.
- UDP-based transport allows QUIC to deploy its own congestion/loss recovery mechanisms rather than being tightly coupled to the OS TCP stack.

### Costs/Limitations

- Requires **UDP/QUIC infrastructure**, a QUIC-capable edge/proxy/CDN, and different debugging tools from HTTP/TCP.
- Encryption/packet processing may consume extra CPU depending on the implementation.
- Some networks block UDP or have path MTU issues; fallback must work.
- Packet loss still causes retransmissions, congestion window reductions, and stream-local blocking.
- Performance outcomes depend on RTT, loss rate, payload, caching, server, device, and edge placement.
- 0-RTT increases security complexity due to replay risk.
- The Java/third-party stack ecosystem must match the exact version and deployment environment.

**Do not generalize that “HTTP/3 is always faster than HTTP/2.”** Proper benchmarking requires a baseline and real-client measurements:
- Time to first byte (TTFB), total response time, and p95/p99.
- RTT/loss distributions across Wi-Fi, mobile, and VPN networks.
- New connection vs. resumed connection.
- Number of concurrent requests, payload sizes, and independent requests.
- Fallback ratio, handshake failure rate, and CPU/memory cost.

A system with very low RTT, a stable network, and server-side bottlenecks may see negligible benefit; a network with high loss and many streams may show a clearer difference.

## 26. Common Misconceptions

1. **“HTTP/3 is just UDP carrying HTTP text.”** False: it uses secure QUIC transport, streams, and HTTP/3 framing.
2. **“UDP is unreliable so HTTP/3 is unreliable.”** False: QUIC provides reliable ordered streams, recovery, and congestion control. Raw UDP is only the underlying layer.
3. **“HTTP/3 opens TCP port 443.”** False regarding H3 transport: QUIC uses UDP; TCP/443 is typically for fallback HTTPS versions.
4. **“Each datagram contains one request.”** False: HTTP requests map onto QUIC streams and can span many QUIC packets/UDP datagrams.
5. **“QUIC eliminates all head-of-line blocking.”** False: it eliminates TCP-level cross-stream HOL, but stream-local ordering, congestion, QPACK dependencies, and other bottlenecks remain.
6. **“TLS 1.3 over TCP is enough to enable H3.”** False: it requires QUIC-integrated TLS, an HTTP/3 stack, and ALPN `h3`.
7. **“Alt-Svc proves the request used HTTP/3.”** False: it only advertises an alternative; the request may still have used h2/h1.
8. **“If a DNS HTTPS RR has h3, QUIC is guaranteed to work.”** False: it is discovery metadata, not a successful handshake.
9. **“A recent curl version definitely supports H3.”** False: it requires a build with an HTTP3 backend; check `curl --version`.
10. **“`HttpClient.Version.HTTP_2` in Java 17 is the path to HTTP/3.”** False: the Java 17 enum has no HTTP_3.
11. **“If UDP connects, HTTP/3 works.”** False: you still need QUIC/TLS, ALPN, certificates, and HTTP/3 SETTINGS/streams.
12. **“QUIC 0-RTT is safe for payment POSTs.”** False without application-layer anti-replay/idempotency protections.
13. **“If H3 fails, it automatically switches to plaintext HTTP.”** False and unsafe. Proper fallback stays on HTTPS/TLS over TCP.
14. **“Origin logging h2 proves the browser used h2.”** False if a CDN terminates HTTP/3 before the origin.
15. **“Connection migration always happens when switching from Wi-Fi to 4G.”** False: it depends on client/server support, policy, path validation, and infrastructure.
16. **“With H3, you no longer need memory or rate limits.”** False: QUIC has flow/congestion control, but servers still need quotas, rate limiting, and DoS protection.

## 27. Reasoning Exercises and Answers

**Question 1.** A Java 17 service creates `HttpClient.newBuilder().version(HTTP_2).build()` and uses the URI `https://api.example.com`. Can it request HTTP/3?  
**Answer:** No. Java 17's `HttpClient.Version` only exposes HTTP_1_1/HTTP_2. The HTTPS scheme does not automatically imply H3.

**Question 2.** A server runs HTTP/3 on UDP/443, but the firewall only allows TCP/443. What will an H3-capable client experience?  
**Answer:** The QUIC handshake may fail/time out. A compliant client can fall back to HTTPS over HTTP/2 or HTTP/1.1 via TCP/443; you must measure the actual response protocol.

**Question 3.** A server returns `Alt-Svc: h3=":443"; ma=86400`. Did the request that received that header run over h3?  
**Answer:** Cannot be inferred. The header advertises an H3 endpoint for suitable future connections, and may have been sent over H1/H2.

**Question 4.** Does HTTP/3 guarantee no loss of the response body if a UDP datagram is lost?  
**Answer:** QUIC provides recovery and reliable delivery for streams while the connection is active, but a connection can still expire or fail. It cannot guarantee a business request always completes regardless of all failures.

**Question 5.** Why does HTTP/3 reduce one type of head-of-line blocking compared to HTTP/2?  
**Answer:** QUIC delivers bytes in order **per independent stream**, rather than having all HTTP streams stalled by the position of a missing byte in **a single shared TCP stream**.

**Question 6.** Which stream does H3 use for an HTTP request?  
**Answer:** A normal request uses a client-initiated **bidirectional QUIC stream**; control/QPACK use separate unidirectional streams per the protocol.

**Question 7.** Does an HTTPS RR containing `alpn=h3,h2` mean a TLS handshake/ALPN h3 has already succeeded?  
**Answer:** No. It is DNS service metadata for the client to choose to attempt a connection; negotiated ALPN is determined on the actual connection.

**Question 8.** A client sends a payment-processing POST in 0-RTT. What is the risk?  
**Answer:** Early data can be replayed. You need policies excluding unsafe operations, idempotency/replay protection, and handling at the HTTP/application layer.

**Question 9.** A CDN receives h3 from the browser, and the CDN calls the origin using h2. Is it reasonable for the origin to log h2?  
**Answer:** Yes. The protocol version can differ across the two hops; you must measure browser-to-CDN and CDN-to-origin separately.

**Question 10.** Running `curl --http3 https://example.com` returns HTTP 200, but the client has fallback enabled. Can you confirm h3 was used?  
**Answer:** No. Inspect the negotiated protocol in verbose logs or use `--http3-only` on a curl build with HTTP3 support.

**Question 11.** A server has TLS 1.3 and HTTP/2 enabled but no QUIC stack; is changing Alt-Svc to h3 enough?  
**Answer:** No. You need a QUIC/UDP listener, HTTP/3 mapping, ALPN h3, TLS keys/certificate, and network rules.

**Question 12.** Why is a 100-byte UDP datagram containing a QUIC Initial not a good test for H3?  
**Answer:** QUIC Initial packets are subject to minimum UDP datagram size requirements and strict handshake state; sending arbitrary UDP data does not reproduce QUIC/HTTP3.

## 28. Standards and References

- RFC 9114 — **HTTP/3**, mapping HTTP semantics onto QUIC, H3 streams, Alt-Svc, control/SETTINGS, ALPN: https://www.rfc-editor.org/rfc/rfc9114
- RFC 9000 — **QUIC: A UDP-Based Multiplexed and Secure Transport**, streams, flow control, ACK/recovery, and address validation: https://www.rfc-editor.org/rfc/rfc9000
- RFC 9001 — **Using TLS to Secure QUIC**, TLS 1.3, handshake, and 0-RTT replay: https://www.rfc-editor.org/rfc/rfc9001
- RFC 9002 — **QUIC Loss Detection and Congestion Control**: https://www.rfc-editor.org/rfc/rfc9002
- RFC 9204 — **QPACK: Field Compression for HTTP/3**: https://www.rfc-editor.org/rfc/rfc9204
- RFC 9460 — **SVCB and HTTPS Resource Records** for service/ALPN discovery: https://www.rfc-editor.org/rfc/rfc9460
- RFC 7838 — **HTTP Alternative Services**, Alt-Svc syntax: https://www.rfc-editor.org/rfc/rfc7838
- RFC 8446 — **TLS Protocol Version 1.3**: https://www.rfc-editor.org/rfc/rfc8446
- Java 17 `HttpClient.Version` — enum with only `HTTP_1_1` and `HTTP_2`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Version.html
- Java 17 `HttpClient` — version preference, sending HTTP requests: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- curl official manpage `--http3` and `--http3-only`: https://curl.se/docs/manpage.html

# HTTP/2: Concurrent Streams on a Connection and Data Flow Control

**HTTP/2** allows multiple HTTP requests/responses to make progress concurrently over a single connection by splitting messages into **frames** with their own **stream ID**. The TCP connection does not have to wait for the entire first response to finish before transmitting the second response. However, streams share bandwidth, the TCP connection, memory, and the **connection flow-control window**. Therefore, multiplexing reduces certain kinds of blocking at the HTTP layer, **not** turning each stream into an independent TCP connection or eliminating all effects of a slow receiver.

This Knowledge lesson focuses on two core topics:

1. **Multiplexing:** different requests/responses are assigned stream IDs, split into HEADERS and DATA frames, and interleaved on a single HTTP/2 connection.
2. **Flow control:** the receiver grants credit in bytes at **both the stream level and connection level**. The sender may transmit DATA only when both windows have enough credit; the receiver grants more via `WINDOW_UPDATE`. If even one window is exhausted, DATA is blocked.

This lesson follows **RFC 9113** and Java 17+. We will accurately model how the two windows consume credit, build a Java program distinguishing **preferred HTTP/2** from **actually negotiated HTTP/2**, along with rules for body streaming and application-level backpressure.

## 1. Multiplexing: Multiple Logical Streams on One HTTP/2 Connection

~~~text
                        One TCP connection (usually wrapped in TLS)
Client                                                             Server
   │                                                                   │
   │── HEADERS stream=1: GET /catalog ───────────────────────────────>│
   │── HEADERS stream=3: GET /profile ───────────────────────────────>│
   │── HEADERS stream=5: GET /thumbnail ─────────────────────────────>│
   │                                                                   │
   │<── HEADERS stream=5 ─────────────────────────────────────────────│
   │<── DATA stream=5 (part or all of image) ─────────────────────────│
   │<── HEADERS stream=1 ─────────────────────────────────────────────│
   │<── DATA stream=1 (first part of catalog) ────────────────────────│
   │<── HEADERS stream=3 ─────────────────────────────────────────────│
   │<── DATA stream=3 (profile) ──────────────────────────────────────│
   │<── DATA stream=1 (next part of catalog) ─────────────────────────│
~~~

**A stream** is a logical HTTP exchange (request/response) with its own state; a **frame** is the unit transmitted over the connection. HTTP/2 can interleave frames across multiple streams, while **preserving frame order within each stream** per the protocol. A stream is not identical to a Java `Thread`, `CompletableFuture`, or TCP socket.

| Concept | What It Actually Is |
| --- | --- |
| TCP connection | Ordered byte stream between two endpoints; governed by TCP flow/congestion control |
| HTTP/2 connection | Multiple streams sharing one connection, sharing SETTINGS and connection window |
| HTTP/2 stream | Logical request/response, with stream ID, lifecycle, and stream window |
| HTTP/2 frame | Wire unit containing type/flags/stream ID/payload |
| Java `CompletableFuture` | Represents an async result, **must not** be assumed to be a stream ID or TCP connection |
| HTTP/2 flow-control credit | Number of **DATA frame payload octets** the sender is currently permitted to send |

### 1.1. Stream ID and Lifecycle

- Each stream is identified by a **non-zero 31-bit stream identifier**. In HTTP/2, client-initiated streams use **odd IDs**, and server-initiated streams use **even IDs**. ID 0 is reserved for certain **connection**-level controls, not a request stream.
- A stream can be in the `idle`, `open`, `half-closed (local)`, `half-closed (remote)`, and `closed` states; frames and `END_STREAM` transition states according to RFC 9113 rules.
- `END_STREAM` can appear on HEADERS or DATA to indicate the sender is finishing its side. A response can consist of multiple DATA frames; **do not** infer from a single DATA frame that the response is complete.
- `RST_STREAM` cancels a stream; in many cases other streams on the connection continue. `GOAWAY` helps coordinate connection termination and handle stream IDs during shutdown.
- Stream IDs within the same connection are not reused. When an application retries, it may create a new stream; retrying POST is not safe by default if the server may have already processed side effects.

HTTP/1.1 can handle concurrency using multiple connections, so saying "HTTP/1.1 is never parallel" is false. The design difference of HTTP/2 is that **multiple requests/responses are multiplexed using frames over a single established connection**.

### 1.2. Relationship with TLS and ALPN

When HTTP/2 runs over HTTPS, TLS ALPN typically negotiates the protocol ID **`h2`**. If the server/proxy does not support it or TLS policy disallows it, the client may fall back to HTTP/1.1. Cleartext HTTP/2 `h2c` is a different case and does not mean every HTTP server supports upgrading. In Java, `HttpClient.Version.HTTP_2` means **prefer** HTTP/2, not force the peer.

Do not equate HTTP/2 with HTTP/3: HTTP/3 uses QUIC, which has a different stream/transport mechanism. **TCP-level head-of-line blocking still exists in HTTP/2**, because bytes from all streams travel over the same ordered TCP stream.

## 2. HTTP/2 Frames and Which Data Is Window-Limited?

Each HTTP/2 frame has a **9-byte header** (length, type, flags, stream ID) and a payload whose length is determined by the Length field. Key frames:

| Frame | Purpose | Subject to HTTP/2 Flow Control? |
| --- | --- | --- |
| `HEADERS` | Request/response headers or trailers | No |
| `CONTINUATION` | Continuation of a header block | No |
| `DATA` | Body content of an HTTP message | **Yes** |
| `SETTINGS` | Exchange connection limits/settings | No |
| `WINDOW_UPDATE` | Increase stream or connection window | No |
| `PING` | Check round-trip/liveness of the HTTP/2 connection | No |
| `RST_STREAM` | Cancel a stream | No |
| `GOAWAY` | Signal connection termination | No |

According to RFC 9113, only **DATA** among the predefined frame types is subject to HTTP/2 flow control. `HEADERS` and control frames are not deducted from the window, but **still consume CPU, network, and memory**. Separate header limits, control-frame limits, and overload protection are required.

**Accurate byte counting:** the entire **DATA frame payload** is deducted from the stream and connection windows, **including padding and the Pad Length field if present**; the 9-byte header is **not** counted.

~~~text
DATA frame:
  9-byte frame header         -> NOT deducted from flow control
  100-byte actual body        -> deduct 100
  1-byte Pad Length field     -> deduct 1
  7-byte Padding              -> deduct 7

Total DATA flow-control usage = 100 + 1 + 7 = 108 bytes.
~~~

By default, `SETTINGS_MAX_FRAME_SIZE` allows a maximum DATA/frame payload of **16,384 bytes**, unless the peer advertises a larger value per the protocol. This is a **per-frame** limit, not a limit on the entire HTTP body or stream window.

### 2.1. An HTTP Message Is Represented by Multiple Frames

A large HTTP response can be a HEADERS frame followed by multiple DATA frames and finally `END_STREAM`. A `HEADERS` frame can carry a header block or a trailer section. HPACK header compression makes the on-wire size differ from the header text, but it does not turn HEADERS into DATA. HTTP/2 also uses pseudo-headers such as `:method`, `:scheme`, `:authority`, and `:path`; applications using `java.net.http.HttpClient` do not write these frames manually.

Do not blindly put HTTP/1.1 connection-specific headers into HTTP/2: `Connection`, `Keep-Alive`, `Upgrade`, and certain similar fields are restricted by RFC 9113. `TE` has only a specific exception for `trailers`. A compliant HTTP/2 library handles framing/header rules.

## 3. Two-Level Flow Control: Stream and Connection

Suppose the server sends response DATA to the client; in terms of credit advertised by the **receiving client**, the server maintains:

- `connectionWindow` — number of DATA bytes the client permits the server to send further on the **entire connection**.
- `streamWindow[streamId]` — number of DATA bytes the client permits the server to send further on **that stream**.
- The peer's frame payload limit.

For unpadded DATA, the maximum body amount that can form a single frame at that moment is approximately:

~~~text
allowedDataBytes = min(
    bytesWaitingToSend,
    connectionWindow,
    streamWindow[streamId],
    maxFramePayload
)
~~~

If the connection window = 0, **all streams** on the connection in that sending direction are blocked from sending DATA, even if individual stream windows are large. If stream 1's window = 0 and the connection window is positive, **only stream 1** is blocked; other streams can still send.

Example:

~~~text
Connection window has 2,000 DATA bytes remaining.

Stream 1 window has 800   -> at most 800 if sent first.
Stream 3 window has 4,000 -> at most 2,000 if sent first.
Stream 5 window has 1,000 -> at most 1,000 if sent first.

But total DATA allowed across all three remains <= 2,000
before the receiver advertises more connection credit.
~~~

These are **two nested budgets**, not a pre-divided fixed slice of the connection window for each stream. The sender's scheduler decides which stream uses credit first; the RFC does not guarantee that every stream always gets an equal share of bandwidth.

### 3.1. The Default Value of 65,535 Bytes

According to RFC 9113:

- When a connection is newly created, **initial connection flow-control window = 65,535 octets**.
- When a new stream is created, **initial stream flow-control window = 65,535 octets**.
- The receiver can adjust the stream initial window using `SETTINGS_INITIAL_WINDOW_SIZE`.
- **The connection window is not changed by `SETTINGS_INITIAL_WINDOW_SIZE`**; it is expanded using `WINDOW_UPDATE` with stream ID **0**.

`65,535` is only the **initial credit**, not a "maximum HTTP/2 body size." Large responses of many MBs or GBs are split into frames and continuously use `WINDOW_UPDATE`. The sender is also constrained by TCP/kernel buffers, congestion, and application limits.

### 3.2. Flow Control Is Directional and Hop-by-Hop

- Windows apply to **one direction of DATA transmission**; a client receiving a response and a server receiving an upload have separate state.
- HTTP/2 flow control is **hop-by-hop** between two endpoints of **one connection**, not `WINDOW_UPDATE` forwarded verbatim end-to-end.
- With client → proxy → origin, the proxy must manage separate windows for the client-side connection and the origin-side connection; if downstream is slow, the proxy needs real backpressure across layers rather than letting an outbound queue grow unboundedly.

Example:

~~~text
Browser --HTTP/2 connection A--> Proxy --HTTP/2 connection B--> Origin
          separate A windows            separate B windows

Proxy does NOT forward raw WINDOW_UPDATE frames from A to B.
Proxy regulates data and memory buffers itself between the two connections.
~~~

## 4. WINDOW_UPDATE: Granting More Credit When the Receiver Is Ready

`WINDOW_UPDATE` (type `0x08`) has a 4-byte payload, with a 31-bit **Window Size Increment**:

- `WINDOW_UPDATE(stream=0, increment=N)` increases the **connection window**.
- `WINDOW_UPDATE(stream=S, increment=N)` with `S != 0` increases **stream S's window**.
- A valid increment is in **1..2,147,483,647** bytes.
- An increment of **0** is a protocol error, not a "no-op."
- A flow-control window must not exceed **2^31−1**; overflow is a `FLOW_CONTROL_ERROR` in the corresponding scope.

After sending a DATA frame with a payload of `N` bytes, the sender reduces **both the stream window and the connection window by N bytes**. Once the receiver has processed/consumed data and has more capacity, it can send the corresponding `WINDOW_UPDATE`.

Example:

~~~text
Current: connectionWindow=0, stream1Window=300, stream3Window=800.

WINDOW_UPDATE(stream=1, +1,000):
  connectionWindow=0, stream1Window=1,300
  -> stream 1 STILL CANNOT send DATA because connection=0.

WINDOW_UPDATE(stream=0, +600):
  connectionWindow=600, stream1Window=1,300
  -> stream 1 can send at most 600 DATA bytes.

If stream 1 sends 400:
  connectionWindow=200, stream1Window=900.
  -> stream 3 can still use 200 bytes of connection credit.
~~~

**WINDOW_UPDATE frames are not subject to DATA flow control**, so they must continue to be processed when DATA windows are exhausted. If an implementation only delivers WINDOW_UPDATE after being able to send DATA, the two sides risk deadlock. Receivers should also avoid emitting countless 1-byte WINDOW_UPDATE increments because of network/CPU overhead; the RFC leaves batching algorithms to the implementation.

### 4.1. SETTINGS_INITIAL_WINDOW_SIZE Differs from WINDOW_UPDATE

`SETTINGS_INITIAL_WINDOW_SIZE` (setting ID `0x04`) changes the **initial window for streams**, using the formula:

~~~text
delta = newInitialStreamWindow - oldInitialStreamWindow
newWindowForEachActiveStream = oldWindowForThatStream + delta
~~~

When a SETTINGS frame changes the initial stream window, the sender updates **affected active stream windows**, including streams that already existed before SETTINGS. The connection window **does not change**.

An easily overlooked difference: if SETTINGS sharply reduces the initial size, **a stream window can become negative**. This is not a protocol error by default. The sender must track the negative value and stop sending DATA on that stream until enough WINDOW_UPDATEs make the window positive.

Example:

~~~text
Initial stream window = 65,535
Stream A has consumed 60,000 -> window A = 5,535

Peer sets SETTINGS_INITIAL_WINDOW_SIZE = 16,384
delta = 16,384 - 65,535 = -49,151
window A = 5,535 - 49,151 = -43,616

Stream A must not send more DATA until new credit arrives.
Connection window is unchanged by SETTINGS.
~~~

Reducing the window on the receiver can happen while the sender still has data in flight under the old setting. The receiver must handle the transition per the RFC, not automatically treat any bytes arriving right after a smaller SETTINGS as an attack.

## 5. First Java 17+ Example: Two-Level Window Model and Negative SETTINGS

This is a **mathematical model**, not sending real HTTP/2 frames. For easy calculation, it uses a connection window of **10 bytes** and each stream window of **8 bytes** — intentionally smaller than the standard 65,535. Two streams are assigned IDs 1 and 3; `send` simulates the amount of DATA permitted under both limits.

Create the file **`Http2WindowModelDemo.java`**:

~~~java
import java.util.*;

public final class Http2WindowModelDemo {
    private static final long MAX_WINDOW = (1L << 31) - 1;
    private final Map<Integer, Long> windows =
            new LinkedHashMap<>();
    private long connection = 10;
    private int initialStream = 8;

    private void open(int id) {
        windows.put(id, (long) initialStream);
    }

    private int send(int id, int wanted) {
        long stream = windows.get(id);
        int sent = (int) Math.max(0, Math.min((long) wanted,
                Math.min(connection, stream)));
        connection -= sent;
        windows.put(id, stream - sent);
        return sent;
    }

    private void windowUpdate(int id, int increment) {
        if (increment < 1) {
            throw new IllegalArgumentException("increment");
        }
        long previous =
                id == 0 ? connection : windows.get(id);
        long next = previous + increment;
        if (next > MAX_WINDOW) {
            throw new IllegalStateException("window overflow");
        }
        if (id == 0) connection = next;
        else windows.put(id, next);
    }

    private void changeInitialStreamWindow(int newSize) {
        if (newSize < 0 || newSize > MAX_WINDOW) {
            throw new IllegalArgumentException("newSize");
        }
        long delta = (long) newSize - initialStream;
        for (int id : windows.keySet()) {
            long next = windows.get(id) + delta;
            if (next > MAX_WINDOW) {
                throw new IllegalStateException("overflow");
            }
            windows.put(id, next); // negative values can be valid
        }
        initialStream = newSize;
    }

    public static void main(String[] args) {
        Http2WindowModelDemo m = new Http2WindowModelDemo();
        m.open(1);
        m.open(3);
        System.out.println("s1 first: " + m.send(1, 7));
        System.out.println("s3 first: " + m.send(3, 6));
        System.out.println(
                "s1 blocked by connection: " + m.send(1, 4));

        m.windowUpdate(0, 6); // connection update
        System.out.println(
                "s1 after conn update: " + m.send(1, 4));
        m.windowUpdate(1, 4); // stream 1 update
        System.out.println(
                "s1 after stream update: " + m.send(1, 4));
        System.out.println("s3 last: " + m.send(3, 4));

        m.changeInitialStreamWindow(4); // 8 -> 4, delta -4
        System.out.println(
                "s1 after smaller SETTINGS: " + m.windows.get(1));
        System.out.println(
                "s3 after smaller SETTINGS: " + m.windows.get(3));
        System.out.println(
                "connection unchanged by SETTINGS: " + m.connection);
    }
}
~~~

~~~bash
javac --release 17 Http2WindowModelDemo.java
java Http2WindowModelDemo
~~~

**Exact** stdout, verified with a local JDK:

~~~text
s1 first: 7
s3 first: 3
s1 blocked by connection: 0
s1 after conn update: 1
s1 after stream update: 4
s3 last: 1
s1 after smaller SETTINGS: -4
s3 after smaller SETTINGS: 0
connection unchanged by SETTINGS: 0
~~~

Calculation:

1. S1 sends 7: stream1 8→1, connection 10→3.
2. S3 wants to send 6 but connection has 3 left: sends only 3, stream3 8→5, connection 3→0.
3. S1 still has stream credit=1 but connection=0: cannot send more DATA.
4. `WINDOW_UPDATE(stream=0,+6)` opens connection=6; S1 can send **1** more per its stream window.
5. `WINDOW_UPDATE(stream=1,+4)` opens stream1=4; S1 sends 4, connection drops 5→1.
6. S3 has stream credit=5 but connection has 1 left: sends only 1.
7. SETTINGS initial stream from 8 down to 4 (delta=-4): S1 goes from 0 down to **-4**, S3 from 4 down to **0**; connection stays **0**.

The example does not model frame payload padding, stream state machine, HPACK, or TCP. Do not take the simulator's `send` methods as a production HTTP/2 library.

## 6. Concurrency Limit Is Not a Window: SETTINGS_MAX_CONCURRENT_STREAMS

`SETTINGS_MAX_CONCURRENT_STREAMS` (setting ID `0x03`) limits the **number of concurrent streams an endpoint allows the other endpoint to open**. The setting is **directional**. Per RFC 9113, there is no default maximum imposed initially, and it recommends that endpoints advertise a value not too low (recommending at least around 100) so as not to inadvertently throttle parallelism. **This is not a promise that all servers always allow 100 streams.**

For example, if a server advertises `MAX_CONCURRENT_STREAMS=20` and the client already has 20 active streams, opening the 21st stream on the same connection must respect the limit. An HTTP client may queue requests, limit concurrency, or use another connection strategy depending on the implementation — do not guess blindly.

| Mechanism | Unit | What It Limits |
| --- | --- | --- |
| `SETTINGS_MAX_CONCURRENT_STREAMS` | Stream count | Number of streams that can be active simultaneously |
| `SETTINGS_INITIAL_WINDOW_SIZE` | DATA bytes | Stream-level initial credit |
| Connection `WINDOW_UPDATE` | DATA bytes | Connection-level credit |
| `SETTINGS_MAX_FRAME_SIZE` | Bytes/frame | Maximum payload of a single frame |
| App memory budget | Bytes/requests/tasks | Application memory and resources |
| TCP congestion/receive windows | Bytes/transport | Send/receive capacity in TCP/network |

Changing max concurrent streams does not automatically increase the DATA window, and increasing the DATA window does not automatically allow opening more streams. You also need to bound **CPU, upstream workers, DB queries, and heap**, not rely solely on an HTTP/2 setting.

## 7. HTTP/2 Flow Control Is Not TCP Congestion Control

HTTP/2 flow control is a **receiver-driven credit scheme** for **DATA frame payloads**. It does not restrict HEADERS/control frame traffic under the same window. Meanwhile, TCP:
- Guarantees an ordered byte stream.
- Uses receive windows and congestion control to protect the kernel/network.
- Can slow down due to retransmissions, RTT, and buffer constraints.

**HTTP/2 does not eliminate TCP-level head-of-line blocking**. If a TCP segment is lost, bytes of subsequent frames may be held back until TCP retransmits and delivers data in order — even if they belong to different streams.

A large stream may be limited because **stream window=0**; all streams may be limited because **connection window=0**; all data on the connection may also slow down due to **TCP congestion**. Classify the root cause accurately before tuning.

## 8. Java 17 `HttpClient`: Preferring HTTP/2, Checking Actual Version

The `java.net.http` module has provided `HttpClient` since Java 11. API:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
~~~

This is an **illustrative snippet requiring `import java.net.http.HttpClient;`**. `HTTP_2` is the **preferred** version, not a command forcing the server to speak HTTP/2. The library may use HTTP/1.1 when server/proxy/ALPN/h2c policy does not support it.

Two different checks:

~~~java
client.version();   // preferred, e.g. HTTP_2
response.version(); // actual version on a specific response
~~~

With HTTPS, ALPN `h2` is the common path to using HTTP/2. Do not manually set `Upgrade: h2c` or change the text `HTTP/1.1` to `HTTP/2` to force the protocol. Java HttpClient handles HTTP framing, header compression, stream IDs, DATA windows, and receiving/generating WINDOW_UPDATE internally.

### 8.1. Concurrent Requests Do Not Prove the Same TCP Connection

~~~java
CompletableFuture<HttpResponse<Void>> a =
        client.sendAsync(reqA, HttpResponse.BodyHandlers.discarding());
CompletableFuture<HttpResponse<Void>> b =
        client.sendAsync(reqB, HttpResponse.BodyHandlers.discarding());
~~~

This is an **illustrative snippet** with `client`, `reqA`, `reqB` already available. It creates two async HTTP requests, which have the opportunity to multiplex when:
- same origin and the connection can be reused;
- TLS/ALPN or h2c actually selects HTTP/2;
- the server allows the required number of concurrent streams;
- the implementation does not decide to use another connection.

**Two futures running in parallel ≠ proof of two streams on the same HTTP/2 connection.** `response.version()==HTTP_2` proves the response used HTTP/2, but confirming **the same TCP connection** requires tracing/metrics from the HTTP stack, server/proxy, or an authorized packet capture.

## 9. Second Java 17+ Example: HTTP/2 Preference Fallback on Loopback

Standalone example without internet: create a JDK HTTP/1.1 `HttpServer` on loopback, then use an `HttpClient` **preferring HTTP/2** to send two concurrent requests. This server only speaks HTTP/1.1, so the actual version of both responses is HTTP/1.1.

Create the file **`Http2LocalFallbackDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.*;

public final class Http2LocalFallbackDemo {
    public static void main(String[] args) throws Exception {
        InetAddress host = InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(host, 0), 0);

        server.createContext("/demo", exchange -> {
            byte[] body = "OK".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();

        try {
            URI uri = new URI("http", null,
                    host.getHostAddress(),
                    server.getAddress().getPort(),
                    "/demo", null, null);

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .connectTimeout(Duration.ofSeconds(5))
                    .build();

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();

            CompletableFuture<HttpResponse<String>> a =
                    client.sendAsync(request,
                            HttpResponse.BodyHandlers.ofString());
            CompletableFuture<HttpResponse<String>> b =
                    client.sendAsync(request,
                            HttpResponse.BodyHandlers.ofString());

            HttpResponse<String> first =
                    a.get(10, TimeUnit.SECONDS);
            HttpResponse<String> second =
                    b.get(10, TimeUnit.SECONDS);

            System.out.println("preferred: " + client.version());
            System.out.println("response 1: " + first.version());
            System.out.println("response 2: " + second.version());
            System.out.println("bodies: " + first.body() + ", " +
                    second.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

~~~bash
javac --release 17 Http2LocalFallbackDemo.java
java Http2LocalFallbackDemo
~~~

Stdout confirmed on a local JDK with loopback available:

~~~text
preferred: HTTP_2
response 1: HTTP_1_1
response 2: HTTP_1_1
bodies: OK, OK
~~~

Takeaway: **the client's preferred version is not necessarily the actual response version**. The snippet also proves `sendAsync` works for two requests, **but cannot prove HTTP/2 multiplexing** because the server intentionally does not speak h2.

The application releases the server in `finally`. `com.sun.net.httpserver.HttpServer` is in the JDK's `jdk.httpserver` module; it may not be present in a trimmed Java runtime image. If a sandbox blocks binding loopback, running may fail with an I/O error; this is not a syntax error.

## 10. Third Java 17+ Example: Probing Two HTTP/2 Requests to an HTTPS Server

Use when you have an **authorized** HTTPS endpoint to test. The program prefers HTTP/2 and sends two async GETs to the same URL. Each response prints the actual protocol along with status. It uses response body discarding because this lesson aims to observe the version, not process content.

Create the file **`Http2ConcurrentProbe.java`**:

~~~java
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.concurrent.*;

public final class Http2ConcurrentProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java Http2ConcurrentProbe <https-url>");
            return;
        }

        URI uri = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null) {
            throw new IllegalArgumentException("Use a valid HTTPS URL");
        }

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(15))
                .GET().build();

        CompletableFuture<HttpResponse<Void>> first =
                client.sendAsync(request,
                        HttpResponse.BodyHandlers.discarding());
        CompletableFuture<HttpResponse<Void>> second =
                client.sendAsync(request,
                        HttpResponse.BodyHandlers.discarding());

        HttpResponse<Void> a =
                first.get(20, TimeUnit.SECONDS);
        HttpResponse<Void> b =
                second.get(20, TimeUnit.SECONDS);

        System.out.println("preferred: " + client.version());
        System.out.println("response 1: " +
                a.version() + " / " + a.statusCode());
        System.out.println("response 2: " +
                b.version() + " / " + b.statusCode());
        System.out.println("both HTTP/2: " +
                (a.version() == HttpClient.Version.HTTP_2
                        && b.version() == HttpClient.Version.HTTP_2));
    }
}
~~~

~~~bash
javac --release 17 Http2ConcurrentProbe.java
java Http2ConcurrentProbe
~~~

Running without arguments: **exact stdout**.

~~~text
Usage: java Http2ConcurrentProbe <https-url>
~~~

With an authorized test endpoint:

~~~bash
java Http2ConcurrentProbe "https://your-approved-host.example/health"
~~~

**Cannot guarantee the stdout of a real endpoint.** If the server selects HTTP/2, the lines may be `response 1: HTTP_2 / 200` and `response 2: HTTP_2 / 200`. If the server does not support it, it may be `HTTP_1_1`, or another status. DNS, proxy, certificate, TLS handshake, and timeout can all cause errors. **No connection to a real host was executed while verifying the examples**; the code and usage branch were confirmed on a local JDK.

Do not take `both HTTP/2: true` as proof that both used *the same TCP connection* — it only proves both responses used the HTTP/2 protocol.

## 11. Two Layers of Backpressure: HTTP/2 WINDOW_UPDATE and Java Flow

Java 17's `HttpClient` manages HTTP/2 framing, stream/connection windows, and WINDOW_UPDATE automatically. The public API **does not have** `sendWindowUpdate(streamId, bytes)` for applications. Still, the application must design **response body** handling so memory does not overflow when the consumer is slow.

~~~text
Peer HTTP/2 DATA frames
        │
        ▼
HttpClient internal HTTP/2 parser + windows + network buffers
        │
        ▼
BodySubscriber / Flow.Subscriber<List<ByteBuffer>>
        │
        │ request(n) means n items/onNext, NOT n bytes
        ▼
application body consumer / parser / file / database
        │
        └── slow -> bounded queues, controlled demand, cancel/close
~~~

**Do not convert `subscription.request(1)` into a `WINDOW_UPDATE(+1 byte)`.** Java `Flow.Subscription.request(n)` counts **items**. Each item can be a `List<ByteBuffer>` of arbitrary byte size. HTTP/2 flow control, on the other hand, counts **DATA frame payload bytes**. The library may bridge these two layers using its own algorithm, not a public 1:1 mapping.

### 11.1. Choosing a BodyHandler Appropriate for Body Size

| API | Returned Data | Resource/Backpressure Notes |
| --- | --- | --- |
| `BodyHandlers.ofString()` | Entire body as `String` | Can hold large amounts of memory |
| `BodyHandlers.ofByteArray()` | Entire body as byte[] | Do not use unboundedly for very large content |
| `BodyHandlers.discarding()` | Discards body after consumption | Suitable when only status/headers are needed |
| `BodyHandlers.ofInputStream()` | Incrementally read `InputStream` | Must read to EOF or call `close()` |
| `BodyHandlers.ofFile(path)` | Writes body to a file | Needs disk size/quota limits and error file cleanup |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Subscriber must request/cancel properly and have bounded processing |

**Illustrative** example of processing a body in small chunks, placed inside a Java method with `client`, `request`, imports `java.net.http.*`, `java.io.*`, and business function `processChunk`:

~~~java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] chunk = new byte[8192];
    int n;
    long total = 0;
    while ((n = body.read(chunk)) != -1) {
        total += n;
        if (total > 100_000_000L) {
            throw new IOException("Body too large");
        }
        processChunk(chunk, n);
    }
}
~~~

This snippet is **not a standalone runnable class**, because `processChunk` is application logic. It avoids accumulating the entire 100MB body into a single byte[]; however, total application memory still depends on the parser, HTTP internal buffering, and downstream queue. If you no longer want to continue, you must close the stream to release resources.

Per Javadoc, `BodySubscriber` should request data until receiving `onComplete`/`onError`, or `cancel` when it cannot process. Canceling early may prevent the HTTP connection from being reused depending on protocol/implementation. Do not leave a subscription hanging indefinitely.

### 11.2. When the App Acts as a Proxy / HTTP Gateway

A proxy receives an HTTP/2 body and forwards it to an upstream. If the upstream responds slowly or the downstream client consumes slowly, the proxy must not pull all bytes from upstream into an unbounded queue. It must coordinate:
- Input/body publisher demand.
- Capacity of application queues in each direction.
- Output consumer/readiness.
- Timeout/cancel policy when a peer is too slow.
- Separate flow control for each HTTP/2 connection; do not forward raw WINDOW_UPDATE across hops.

If multiple streams share a connection, bound memory **per stream and globally**; do not use a wide window and allow one stream to occupy the entire heap.

### 11.3. Backpressure Is Not Request Rate Limiting

| Mechanism | What It Solves |
| --- | --- |
| HTTP/2 `WINDOW_UPDATE` | Number of DATA bytes an endpoint can receive on a stream/connection |
| Java `Flow.Subscription.request(n)` | Number of emissions/chunks requested by downstream |
| `MAX_CONCURRENT_STREAMS` | Number of active streams permitted by the peer |
| Application semaphore/executor cap | Number of concurrent backend requests/tasks |
| API rate limit | QPS/requests per tenant/time window |
| TCP congestion window | Send capacity per network conditions/RTT/loss |

A high-load server may need **all** of these layers. A positive HTTP/2 stream window does not prove CPU/DB can handle more requests. A semaphore limiting concurrency does not replace DATA frame credit.

## 12. When the Receiver Is Slow: Coordinating Queues, Scheduler, and Windows

A real system may have a pipeline:

~~~text
app upstream producer -> bounded per-stream queue -> HTTP/2 DATA scheduler
                                     │                  │
                                     │                  ├─ stream window
                                     │                  └─ connection window
                                     ▼
                             bounded connection memory
                                     │
                                     ▼
                             TLS/TCP kernel buffers -> receiver
~~~

When downstream temporarily pauses consuming the body, the HTTP/2 window can drop to 0. The sender must wait for WINDOW_UPDATE before sending DATA; if the producer keeps generating bytes and putting them into an unbounded queue, **wire-level flow control will not save the application from OOM**.

Server/proxy design checklist:

1. **Bounded per-stream queue** by byte count, not just message count.
2. **Global memory budget** per connection/tenant/server, including header parser, TLS buffers, and producer tasks.
3. **Backpressure on the producer** when queue/high watermark reaches threshold; resume at low watermark.
4. **Fair scheduling** so a stream with a large response does not monopolize the event loop.
5. **Processing of control frames** independent of DATA credit.
6. **Timeout and cancellation** for streams stuck for a long time, cleanup on RST_STREAM/GOAWAY.
7. **Monitoring** active stream count, pending bytes, stream/connection windows, timeouts, and TCP retransmissions.

Increasing `SETTINGS_INITIAL_WINDOW_SIZE` very high can improve throughput when the bandwidth-delay product is large, but it also requires the receiver to ensure corresponding memory and processing policies. Do not treat increasing the window as a way to "fix every speed issue."

## 13. HTTP/2 Does Not Guarantee Absolute Fairness Between Streams

Stream 1 has a very large body, while stream 3 has a small, urgent body. Because both share the connection window and a single TCP connection, if the scheduler always prioritizes stream 1 until connection window=0, stream 3 must wait as well even if its stream window is full.

The RFC allows different scheduling strategies; several older HTTP/2 priority mechanisms were deprecated in RFC 9113. Do not rely on a fixed priority order when designing SLAs. On the application side, you should:
- Limit bytes each stream can enqueue from the producer.
- Have fairness policies in the scheduler supported by the library/server.
- Observe latency of small requests while concurrently downloading large objects.
- Use timeouts, cancellation, and flow-control metrics when debugging.
- Never claim an HTTP/2 stream is "guaranteed never to be affected by other streams."

Besides the shared connection window, **TCP HOL** still exists. Losing a single TCP segment can make all subsequent bytes on the same connection wait for retransmission, even if they belong to different streams.

## 14. HTTP/2 Error Handling and Semantically Correct Retries

| Symptom | What to Check |
| --- | --- |
| One stream stops, other streams continue | Stream window=0, app subscriber not requesting, RST_STREAM, or stream state |
| Multiple DATA responses all stop | Connection window=0, TCP congestion, blocked event loop, or proxy queue |
| Stream WINDOW_UPDATE received yet DATA still does not flow | May be missing connection-level WINDOW_UPDATE |
| WINDOW_UPDATE increment 0 | Protocol error, must not be treated as a no-op |
| Window exceeds 2^31−1 | FLOW_CONTROL_ERROR in the corresponding scope |
| Stream window negative after smaller SETTINGS | Allowed during transition; wait for enough credit |
| Java client wants HTTP_2 but gets HTTP_1_1 | ALPN/h2c/implementation/server/proxy did not select HTTP/2 |
| Heap grows with body download | BodyHandlers.ofByteArray/ofString or unbounded queue |
| New stream rejected | MAX_CONCURRENT_STREAMS, admission, or server policy |
| RST_STREAM / GOAWAY | Stream cancellation or connection termination, must distinguish from HTTP status |
| Invalid HTTP/2 parser content | HEADERS/CONTINUATION/HPACK/state/pseudo-header rules |

**`RST_STREAM`** closes one stream without necessarily closing the entire connection. **`GOAWAY`** is used to coordinate closing the connection, carrying the last stream ID to help analyze which streams may have already been processed. Do not automatically retry all POSTs with side effects just because you see GOAWAY or a timeout. Ensure idempotency or a verification/compensation workflow.

Java `HttpClient` applications may throw `IOException`, `HttpTimeoutException`, `CompletionException`, and other transport errors; not every HTTP/2 error code is exposed directly as an enum by the public API. Retry tests must guard against sending duplicate side effects.

## 15. Testing HTTP/2 Multiplexing and Flow Control

### 15.1. Three-Tier Evidence

1. **Preferred version**: `client.version()==HTTP_2`. Only confirms the client setting.
2. **Actual version**: `response.version()==HTTP_2`. Confirms this response actually used HTTP/2.
3. **Multiplexing on the same connection**: tracing shows **at least two stream IDs active simultaneously over one connection**. Two Java futures or two HTTP_2 responses **do not by themselves prove** the same connection.

To obtain tier-3 evidence, use server/proxy HTTP/2 metrics or an authorized packet trace capable of observing TLS/HTTP/2; do not infer from timings of two futures.

### 15.2. Slow Receiver Test

1. Stand up an HTTPS server supporting HTTP/2 and TLS ALPN `h2` in a test environment.
2. Open multiple large responses to the same origin; log stream-specific request IDs.
3. Make one response consumer read slowly or stop requesting chunks in a controlled test.
4. Observe per-stream window, connection window, queue bytes, and response progress.
5. Verify that when stream A runs out of credit, stream B still makes progress if **connection window and B window still have credit**.
6. Exhaust the connection window; verify no DATA stream exceeds credit, while WINDOW_UPDATE/control frames are still processed.
7. Resume the consumer, observe additional credit, and verify byte counts/hash of the entire content with no loss or duplication.
8. Cancel a response; verify subscription release, queue cleanup, and stream state; test GOAWAY on shutdown.
9. Bound test duration and byte count; do not load-test production without authorization.

### 15.3. Useful Metrics

| Metric | Purpose |
| --- | --- |
| `active_http2_streams` | Distinguish concurrency from TCP socket count |
| `stream_window_available` | Per-stream DATA credit status |
| `connection_window_available` | Shared DATA credit, detects all streams blocked |
| `http2_window_updates_total` | Track credit replenishment |
| `flow_control_blocked_duration` | Time a stream/connection waits for credit |
| `pending_response_bytes` | Application-layer buffer, protects memory |
| `response.version` histogram | Ratio of HTTP_2 vs HTTP_1_1 fallback |
| `RST_STREAM` / `GOAWAY` counts | Lifecycle errors and shutdown |
| `request_cancel_total` | Body subscriber cancellations, resource release |
| TCP RTT/retransmits | Distinguish TCP HOL from HTTP/2-level stalls |

Not every library exposes all of these metrics out of the box. With standard Java 17 `java.net.http.HttpClient`, the easiest things to measure via public API are **actual response.version**, status/timings, and application-level pending data; internal flow-control windows/stream IDs may require server/proxy or implementation instrumentation.

## 16. Common False Claims

**"HTTP/2 uses one TCP connection, but each stream has its own independent bandwidth."** False. Streams share TCP, the connection window, and CPU/network scheduling.

**"If the stream window is positive, DATA can be sent."** Not enough: the connection window must also have sufficient credit.

**"SETTINGS_INITIAL_WINDOW_SIZE changes the connection window too."** False: only stream windows; the connection window increases via WINDOW_UPDATE(stream=0).

**"A negative window is a protocol error."** Not always: lowering SETTINGS can legitimately make a stream window negative.

**"HTTP/2 flow control limits HEADERS, PING, and SETTINGS the same as DATA."** False: among frame types defined in RFC 9113, only DATA is subject to flow control; however, control frames still require other resource limits.

**"One WINDOW_UPDATE grants 1,000 bytes to all streams."** False: stream-level only increases the specified stream; connection-level only increases the shared total credit.

**"HTTP/2 completely eliminates head-of-line blocking."** False: TCP-level HOL still exists.

**"Concurrent sendAsync is proof that both requests multiplexed on one connection."** False: requires actual HTTP_2 and stream/connection tracing.

**"BodySubscriber.request(1) is WINDOW_UPDATE(+1)."** False: Java demand counts items, while HTTP/2 windows count DATA payload bytes.

**"ofByteArray() is safe for multi-GB responses because HTTP/2 regulates itself."** False: flow control does not replace an application memory cap.

**"You can retry any POST when seeing RST_STREAM/GOAWAY."** False: must consider request idempotency and how far the peer has processed it.

## 17. Self-Check Questions

**Question 1.** There are 8 requests on the same HTTP/2 connection: must there be 8 TCP sockets?  
**Answer:** No. Multiple streams can share a single TCP socket.

**Question 2.** Stream 1 window has 2,000 bytes left, connection window=0. Can stream 1 DATA be sent?  
**Answer:** No, both windows need credit.

**Question 3.** Does `WINDOW_UPDATE(stream=1,+500)` increase stream 3?  
**Answer:** No; only stream 1. The connection window increases only when stream ID=0.

**Question 4.** A DATA frame has 100 body bytes, 1 Pad Length byte, and 7 padding bytes, plus a 9-byte header. Credit consumed?  
**Answer:** 108 bytes (the entire DATA frame payload), excluding the 9-byte frame header.

**Question 5.** A stream window drops to -2,000 due to SETTINGS; is that necessarily an error?  
**Answer:** No. The sender keeps the negative number and waits for WINDOW_UPDATE.

**Question 6.** Does HTTP/2 `MAX_CONCURRENT_STREAMS=20` mean each stream is at most 20 bytes?  
**Answer:** No; it is the number of active streams, different from flow-control bytes.

**Question 7.** Why can HTTP/2 still slow down across multiple streams simultaneously when TCP loses a packet?  
**Answer:** TCP delivers bytes in order and may wait for retransmission, even though HTTP/2 streams are logically independent.

**Question 8.** `HttpClient.version()==HTTP_2` yet `response.version()==HTTP_1_1`. Is that a contradiction?  
**Answer:** No. HTTP_2 is preferred; HTTP_1_1 is the actual protocol.

**Question 9.** Do two `sendAsync` calls returning `HTTP_2` prove they shared one TCP connection?  
**Answer:** Not enough; stream IDs and connection IDs tracing is required.

**Question 10.** Is `Flow.Subscription.request(1)` equivalent to opening 1 byte of window?  
**Answer:** No. Demand measures item emissions, not DATA bytes.

**Question 11.** When downloading a very large response body, which APIs should be preferred to avoid accumulating everything in RAM?  
**Answer:** Streaming `ofInputStream`/`ofFile`/`ofPublisher` as needed, combined with size limits and cleanup.

**Question 12.** The receiver stops reading and the sender has a large DATA queue; is increasing the SETTINGS window alone enough to protect server heap?  
**Answer:** No. Application backpressure and bounded queues, timeouts, and cancellation are needed.

## 18. Checklist for Implementing HTTP/2 in Java

1. Clearly distinguish **stream, frame, connection**; do not conflate them with Java futures/threads.
2. Ensure the server/client actually supports h2 via TLS ALPN or the appropriate HTTP/2 mechanism.
3. Compare **preferred** `client.version()` and **actual** `response.version()`.
4. Count DATA flow control by **payload bytes**, including padding, excluding the 9-byte header.
5. Keep **stream and connection windows separate**; send DATA only when both allow it.
6. Understand the initial 65,535 bytes and `WINDOW_UPDATE` by stream ID, guarding against 31-bit overflow.
7. Apply `SETTINGS_INITIAL_WINDOW_SIZE` by delta to active streams; accept negative values and block DATA until sufficient credit arrives.
8. Do not confuse `MAX_CONCURRENT_STREAMS`, `MAX_FRAME_SIZE`, flow control, TCP congestion, and app queue limits.
9. Ensure `WINDOW_UPDATE`, `SETTINGS`, `RST_STREAM`, and control frames are not deadlocked just because DATA window=0.
10. Use a maintained HTTP/2 stack such as `java.net.http.HttpClient`; do not implement framing yourself unless necessary.
11. Choose an appropriate BodyHandler, avoid accumulating overly large bodies, and use backpressure/Flow by **items**, not interpreting them as byte credits.
12. Bound memory/concurrency across the whole app, with timeouts, cancellation, and retry-idempotency policies.
13. Measure real metrics during load testing: window stalls, queues, active streams, actual protocol, TCP retransmits, RST_STREAM/GOAWAY.
14. For proxies, apply backpressure **hop-by-hop**, do not forward raw WINDOW_UPDATE across multiple connections.

## Official References

- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html): frame structure, streams, multiplexing, `SETTINGS`, `WINDOW_UPDATE`, flow control.
- [RFC 9113 — Section 6.9](https://www.rfc-editor.org/rfc/rfc9113.html#section-6.9): two windows, WINDOW_UPDATE increment/overflow, negative stream window after SETTINGS.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `HTTP_2` preferred and `sendAsync`.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `version(HTTP_2)` and fallback behavior.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): `version()` confirming the response's protocol.
- [Java SE 17 — BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html) and [BodySubscriber](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): streaming, consumption, and cancellation.
- [Java SE 17 — Flow.Subscription](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): item-based demand, not WINDOW_UPDATE bytes.
- [RFC 7301 — ALPN](https://www.rfc-editor.org/rfc/rfc7301): protocol ID `h2` when HTTP/2 runs over TLS.

**Core principle:** HTTP/2 multiplexes multiple HTTP streams over one connection, but DATA can only be sent when **both the stream window and the connection window** have credit. Java `HttpClient` manages frames and WINDOW_UPDATE; the application must manage **body streaming, bounded memory, concurrency, cancellation**, and verify the HTTP version actually used.

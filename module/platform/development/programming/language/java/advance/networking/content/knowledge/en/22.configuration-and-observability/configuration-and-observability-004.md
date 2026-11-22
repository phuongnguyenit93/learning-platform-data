# Reading Local/Remote Addresses, Per-Phase Timings, and Transferred Bytes in Java Networking

When a TCP, UDP, or HTTP connection is slow, simply logging “connected” or “HTTP 200” is usually not enough to diagnose the issue. You need to know **which two endpoints the connection/exchange is running between**, **which phase is taking time**, and **how many bytes actually pass through the part of the program you are measuring**. Java 17+ has many useful APIs, but **not every API exposes all network-layer measurements**. Accurate observability must always specify **the measurement point, data direction, units, and inference boundaries**.

This lesson belongs to the **Configuration and Observability** group in Java Advance – networking, focusing on three groups of information:

1. **Local/remote address:** `Socket.getLocalSocketAddress()`, `Socket.getRemoteSocketAddress()`, `ServerSocket.accept()`, `SocketChannel.getLocalAddress()/getRemoteAddress()`, `HttpExchange.getLocalAddress()/getRemoteAddress()`, and datagram addresses.
2. **Per-phase timing:** DNS lookup, TCP connect, TLS handshake, sending the request, waiting for the response, reading the response body, and server-side processing. Use `System.nanoTime()` to compute durations; **distinguish between timestamps you can directly measure and phases you only infer**.
3. **Byte counts:** count **actual application payload bytes read/written**, using `InputStream/OutputStream` wrappers, byte counts returned by NIO `read/write`, `ByteBuffer.remaining()`, and `HttpExchange` request/response bodies; distinguish these from `Content-Length`, UTF-8 characters, and actual bytes transmitted on the wire (which include framing/TLS/headers/retransmissions).

The two standalone programs at the end of the lesson use **Java 17**: a TCP loopback PING/PONG echo and an HTTP loopback POST/response. Both are compiled with `javac --release 17`, run on a compatible JDK, and include verified output; millisecond values are **dynamic measurements**, not fixed across runs.

## 1. What Do Local and Remote Mean?

A TCP connection has **two ends**: the IP address and port on your process (**local**) and on the peer at the other side (**remote**).

~~~text
                      Single TCP Connection
        Client                                     Server
  local  = 127.0.0.1:ephemeral  ------------>  remote = 127.0.0.1:ephemeral
  remote = 127.0.0.1:serverPort <------------  local  = 127.0.0.1:serverPort
             |                                     |
       Client-side socket                   Socket after accept()
~~~

In a direct connection within the same network namespace, the *client's local* usually matches the *server socket's remote*, and the *client's remote* matches the *server socket's local*. However, these are **two perspectives on socket endpoints**, not the service's DNS name or user identity. When NAT, a load balancer, a reverse proxy, an SSH tunnel, or a service mesh is involved, the address on a socket **is not necessarily the original address of the end user or the business destination host**.

| Value | What does it ask? | Example |
| --- | --- | --- |
| Local IP | Which interface/IP did this process use to communicate? | `127.0.0.1`, `192.0.2.10`, an IPv6 address |
| Local port | The port on the connecting process | Client's ephemeral port, server's listener port |
| Remote IP | IP of the **direct socket peer** | Server, proxy, or upstream |
| Remote port | Port on the peer side | `443`, `8080`, or client ephemeral port |
| DNS hostname | Logical name resolved to find an address | `api.example.test` |
| HTTP URI | Logical target and path requested by the application | `https://api.example.test/orders` |
| X-Forwarded-For/Forwarded | Metadata sent via proxy/header, **not the socket peer** | A string that could be forged by the client |

**Do not use `getRemoteSocketAddress()` alone to conclude that the peer is an authenticated user.** One IP can represent many users, sit behind NAT, change on reconnect, or be hidden behind a proxy. For security/rate limiting, you must define the proxy's **trust boundary** and apply separate authentication/authorization.

## 2. Reading Addresses on Socket and ServerSocket

For traditional TCP:

~~~java
// Fragment in a Java 17+ program with a connected Socket.
SocketAddress local = socket.getLocalSocketAddress();
SocketAddress remote = socket.getRemoteSocketAddress();

System.out.println("local=" + local);
System.out.println("remote=" + remote);
~~~

`Socket.getLocalSocketAddress()` returns the endpoint the socket is bound to; `getRemoteSocketAddress()` returns the endpoint the socket is/was connected to. When the socket is not yet bound/connected, they may return `null`; do not dereference blindly. `Socket.getLocalAddress()`/`getLocalPort()` and `getInetAddress()`/`getPort()` provide the individual IP/port parts, but have sentinel values when not connected.

### Listener vs. Accepted Socket

`ServerSocket` only **listens on a local endpoint**. It does not represent a specific remote peer, because many clients can connect to the same listener:

~~~java
// Java 17+ fragment.
try (ServerSocket listener = new ServerSocket(
        0, 50, InetAddress.getLoopbackAddress())) {

    SocketAddress listeningOn = listener.getLocalSocketAddress();

    try (Socket accepted = listener.accept()) {
        SocketAddress localOnConnection =
                accepted.getLocalSocketAddress();
        SocketAddress remoteOnConnection =
                accepted.getRemoteSocketAddress();
        // localOnConnection: server side of the specific connection
        // remoteOnConnection: direct client side
    }
}
~~~

The snippet above is a **fragment**, which will block at `accept()` until a client connects; it is not a standalone runnable file. You only know the peer for a specific connection when you inspect the address **after** `accept()`. If listening on a wildcard address like `0.0.0.0`, the listener's bound address may be the wildcard, while the local address on the accepted socket will be the specific interface used for that connection.

### InetSocketAddress and Log Formatting

To extract the port number or IP, you can cast to `InetSocketAddress` **after type checking**:

~~~java
// Fragment only when remote is actually a resolved InetSocketAddress.
if (socket.getRemoteSocketAddress() instanceof InetSocketAddress peer) {
    int port = peer.getPort();
    String ip = peer.getAddress() == null
            ? "(unresolved)" : peer.getAddress().getHostAddress();
    System.out.println("peerIp=" + ip + ",peerPort=" + port);
}
~~~

- `InetSocketAddress.getAddress()` can be `null` if the address is unresolved.
- `getHostAddress()` returns the IP string representation without triggering reverse DNS.
- `getHostName()` may perform a reverse name lookup depending on the instance; in hot-path logging, do not accidentally turn every request into a DNS lookup.
- IPv6 addresses contain colons; when formatting IP+port to copy into a URI, use bracket notation `[2001:db8::1]:443` instead of naive string concatenation.
- For UNIX-domain sockets (where supported by the API/channel), `SocketAddress` may not be an `InetSocketAddress`. Do not cast unconditionally.

### Socket Close State and Addresses

Some socket methods may still retain endpoint information **after the socket has been closed**. For example, `Socket.isConnected()` may still return `true` because the socket was once successfully connected; it does **not** prove data can currently be exchanged. You must distinguish between `isClosed()`, I/O errors, EOF, and business state. When logging the final endpoint for diagnostics, capture it when opened/connected and attach a correlation ID, rather than inferring it from boolean state flags.

## 3. Where to Read Endpoints in NIO, Datagram, and HTTP Server?

### 3.1. SocketChannel and ServerSocketChannel

When using NIO:

~~~java
// Fragment: a connected channel (SocketChannel).
SocketAddress local = channel.getLocalAddress();
SocketAddress remote = channel.getRemoteAddress();

// Actual number of bytes READ returned by this call.
ByteBuffer buffer = ByteBuffer.allocate(1024);
int n = channel.read(buffer);
if (n > 0) {
    payloadBytesRead += n; // Bytes read from the channel in this call.
} else if (n == 0) {
    // No bytes read yet, common on nonblocking channels.
} else {
    // n == -1: EOF.
}
~~~

`SocketChannel.read(ByteBuffer)` returns the number of bytes placed into the buffer, **not** always equal to capacity; `write(ByteBuffer)` returns the number of bytes actually accepted in that call, **not** always the entire buffer. In nonblocking mode, a call can return 0; you must keep the `remaining()` data and wait to continue when appropriate. `ServerSocketChannel.accept()` returns a `SocketChannel` for the accepted client; inspect the endpoint on the **accepted channel**, not just the listener.

Example of a proper write:

~~~java
// Fragment: outbound is a ByteBuffer containing bytes to send.
while (outbound.hasRemaining()) {
    int written = channel.write(outbound);
    if (written > 0) {
        payloadBytesWritten += written;
    } else if (written == 0) {
        // Nonblocking: register OP_WRITE / wait until writable,
        // DO NOT busy-spin infinitely.
        break;
    }
}
~~~

If the loop exits because of 0 while the buffer still has data, you must **continue sending on the next ready event**; do not assume the entire message was sent. With scatter/gather I/O, the total bytes returned by `read/write(ByteBuffer[])` reflect all buffers in that call.

### 3.2. DatagramSocket and DatagramChannel

UDP **has no TCP connection**. A UDP socket that has not called `connect()` may have a local address after binding, but `getRemoteSocketAddress() == null`. The **actual source address of each datagram** is in `DatagramPacket.getSocketAddress()` or the return value of `DatagramChannel.receive(ByteBuffer)`.

~~~java
// Java 17+ DatagramSocket fragment.
byte[] storage = new byte[2048];
DatagramPacket packet =
        new DatagramPacket(storage, storage.length);
udpSocket.receive(packet);

SocketAddress sender = packet.getSocketAddress();
int bytesReceived = packet.getLength();
// bytesReceived is the datagram payload copied into the buffer.
~~~

~~~java
// Java 17+ DatagramChannel fragment.
ByteBuffer data = ByteBuffer.allocate(2048);
SocketAddress sender = datagramChannel.receive(data);
if (sender != null) {
    int receivedBytes = data.position();
    // Because initial position = 0; total position delta is bytes received.
}
~~~

In cases where the `ByteBuffer` already has a non-zero position, you must measure the **delta** between position before and after, rather than taking the entire position as new bytes. A datagram larger than the receiving buffer may be **truncated**, so the byte count read is the amount actually placed into the buffer, not proof that the original payload sent by the peer was that small. Calling UDP `connect(peer)` only filters the peer/allows convenient read-write; it **does not perform a TCP handshake** and does not prove the peer is alive.

UDP datagrams have message boundaries at the UDP layer, but the byte count still excludes IP/UDP headers, fragmentation overhead, or application-level retransmissions.

### 3.3. HttpExchange in jdk.httpserver

In the JDK built-in HTTP server:

~~~java
// Fragment inside HttpHandler.handle(HttpExchange exchange).
InetSocketAddress local = exchange.getLocalAddress();
InetSocketAddress remote = exchange.getRemoteAddress();

String method = exchange.getRequestMethod();
URI uri = exchange.getRequestURI();
String protocol = exchange.getProtocol(); // For example, HTTP/1.1.
~~~

`getLocalAddress()` is the server's local endpoint receiving the request; `getRemoteAddress()` is the **direct socket peer** calling the server. If the server sits behind Nginx/Envoy/a load balancer, remote may be the **proxy**. `Forwarded` or `X-Forwarded-For` headers must not be treated as trusted sources if clients can send/overwrite them; only read them according to a specific proxy trust configuration, prevent spoofing, and evaluate permissions based on real identity.

`HttpExchange` does not expose an API for “how many TCP/TLS bytes were on the wire.” To know **bytes in the HTTP request/response body**, measure the bytes you read from `getRequestBody()` and write to `getResponseBody()`. Header sizes, chunk framing, compression, TLS records, and retransmissions live at other layers.

## 4. With java.net.http.HttpClient, There Is No Equivalent Public Socket Endpoint API

For Java 17 `HttpClient` and `HttpResponse<T>`:

- `HttpResponse.uri()` returns the URI associated with the response, which **may differ from the original URI due to redirects**.
- `HttpResponse.statusCode()`, `headers()`, `version()`, and `sslSession()` allow observing status, protocol metadata, and the TLS session (if HTTPS).
- **`HttpResponse` has no public `getLocalSocketAddress()/getRemoteSocketAddress()` methods**. Therefore, **do not log “remoteIp = response.uri().getHost()”** and call it the TCP peer address. The URI host may be a DNS name, a proxy may make the peer different, DNS may have multiple addresses, keep-alive reuse may retain an older socket, and redirects may change the target.
- **`HttpClient` does not provide a public DNS/TCP/TLS per-phase timing breakdown** like some HTTP client libraries with event listeners. You can measure wall elapsed time at API boundaries, but you cannot split it into connect/TLS/request-write from a single `sendAsync()` call.

~~~java
// Java 17+ fragment, response is HttpResponse<String>.
URI effectiveUri = response.uri();
int status = response.statusCode();
HttpClient.Version httpVersion = response.version();
boolean secureResponse = response.sslSession().isPresent();

// Not available: response.getRemoteSocketAddress()
// Not available: response.getDnsDuration() or response.getTlsDuration()
~~~

`sslSession()` carries TLS negotiated session/peer identity information (when present), but it is **not an API that returns encrypted TCP byte counts or the peer socket address**. If business requirements only need target host/path/HTTP status, logging the normalized URI and status is sufficient; if you need the exact socket tuple or per-phase network timings, you need another instrumentation layer at the TCP boundary, proxy, or an HTTP client implementation that provides appropriate hooks.

## 5. Defining Time Phases Before Measuring

Common milestones for an HTTP call:

~~~text
t0       tDNS      tConnect     tTLS     tWrite      tHeaders      tBodyDone
|--------|---------|------------|--------|-----------|-------------|
   DNS      TCP       TLS          upload    wait/        body
   lookup   connect   handshake    request   headers     read/consume
         \_______________________________/
             may overlap, reuse, retry, or redirect
~~~

This diagram simplifies the path of a request **opening a new connection**. In practice, DNS has caching, TCP connections can be reused, HTTP/2 has multiplexing, proxies add extra phases, TLS sessions can resume, and the request body can **be streamed concurrently with response processing**. Thus, not every request goes through all phases, and not all phases are strictly sequential without overlap.

| Phase | Available start/end points | What you actually measure |
| --- | --- | --- |
| DNS resolution | Before/after `InetAddress.getAllByName(host)` if called manually | In-process name resolution API time, possibly cached; not full recursive DNS network latency |
| TCP connect | Before/after `socket.connect(remote, connectTimeoutMs)` | Connect call duration for that socket; may be affected by ARP/routing/scheduling |
| TLS handshake | Before/after `SSLSocket.startHandshake()` when actively managing a TLS socket | Handshake duration during the measurement window; excludes prior related overhead |
| Send request | Before/after writing and `flush()` on OutputStream/SocketChannel | Time for code to complete write/flush, **not** server ACK |
| Wait for response headers | From request start until headers are ready at the API | **Approximate time until response object is available** when using a streaming BodyHandler, not pure server processing |
| Read response body | From when the body stream is ready until EOF/terminal | Includes peer speed, scheduling, and local processing/copying |
| Total request | From before starting work until required body/processing completes | End-to-end elapsed time at the application-chosen boundary |
| Server request-body read | Before/after the `getRequestBody()` read loop | Reading the body inside the handler; excludes accept/DNS/TLS before the handler |
| Server response write | Before/after writing/closing `getResponseBody()` | Writing the body at the application boundary, with no guarantee the client has processed it |

**TTFB (time to first byte)** in production monitoring is typically a specific network-layer milestone; `sendAsync(..., BodyHandlers.ofInputStream())` completing may be **close** to when headers/body stream become available, but still includes scheduling and JDK internals. Do not call this number **exact on-wire TTFB** if instrumentation only sits at the application boundary.

### Use System.nanoTime(), Not currentTimeMillis(), for Durations

~~~java
long start = System.nanoTime();
// Operation to measure.
long elapsedNanos = System.nanoTime() - start;
double elapsedMs = elapsedNanos / 1_000_000.0;
~~~

`System.nanoTime()` is a **monotonic time source suitable for measuring elapsed time within the same JVM** (not a wall-clock timestamp). It does not provide calendar date/time and should not be persisted as an absolute number to compare across machines. `Instant.now()` is suitable for log timestamps, but wall-clock time can be adjusted; do not use it in place of `nanoTime()` for accurate latency durations.

For timeouts, use `Duration`/`TimeUnit` and an overall deadline. If there are 10 sequential steps, do not give each step a timeout equal to the total budget and claim the total is bounded: you need the **remaining** time of the same deadline.

### How Are DNS, TCP Connect, and TLS Handshake Separated?

When **you own the Socket yourself**:

~~~java
// Java 17+ fragment, host and port are determined by the application.
long dnsStart = System.nanoTime();
InetAddress[] candidates = InetAddress.getAllByName(host);
long dnsDone = System.nanoTime();

Socket socket = new Socket();
long connectStart = System.nanoTime();
socket.connect(new InetSocketAddress(candidates[0], port), 3_000);
long connectDone = System.nanoTime();

// For plaintext TCP, there is only DNS + connect.
// For a TLS socket, you need an SSLContext, endpoint identity verification,
// and separate measurement of startHandshake() after creating a valid SSLSocket.
~~~

This is a fragment, not standalone runnable code. Picking `candidates[0]` is for illustration only and is **not a production Happy Eyeballs/failover strategy**. DNS can return multiple IPv4/IPv6 addresses, sometimes cached. With `HttpClient`, **do not call DNS yourself and attribute that as HttpClient's DNS duration**: the client may use a different DNS/cache/connection, a proxy, a redirect, or reuse an existing connection.

When managing TLS yourself, a proper directional fragment:

~~~java
// Java 17+ TLS fragment, context is a trust-verified SSLContext
// and raw is a NEW TCP Socket already connected to host:port.
try (SSLSocket tls = (SSLSocket) context.getSocketFactory()
        .createSocket(raw, host, port, true)) {
    SSLParameters params = tls.getSSLParameters();
    params.setEndpointIdentificationAlgorithm("HTTPS");
    tls.setSSLParameters(params);

    long handshakeStart = System.nanoTime();
    tls.startHandshake();
    long handshakeNanos = System.nanoTime() - handshakeStart;
}
~~~

This is a **fragment**: you must create/configure the context, raw socket, host/port, exception handling, and full TLS policy. Measuring `startHandshake()` does not grant permission to **skip certificate verification**; omitting endpoint identity makes numbers faster but breaks security. In practice, an HTTPS client may use TLS 1.3 resumption or HTTP/2 connection reuse, so many requests do not open a new handshake.

## 6. Which Bytes Are Being Counted?

“Sent 100 bytes” only has meaning when you specify **100 bytes at which layer**.

| Counting unit | Includes | Excludes |
| --- | --- | --- |
| Bytes of `text.getBytes(UTF_8)` | Bytes of text after encoding | HTTP headers, TCP/IP, TLS overhead |
| Application InputStream/OutputStream | Bytes successfully read/written at the boundary | Does not inherently know if bytes reached the peer or were ACKed |
| `SocketChannel.read/write` | Value `n` returned by the API (local operation success) | All retries/overhead/retransmissions |
| HTTP request body bytes | Bytes read from `HttpExchange.getRequestBody()` | Headers, chunk framing, TLS/IP overhead |
| HTTP response body bytes | Bytes handler wrote to `getResponseBody()` | Headers, chunk framing, encrypted bytes on the wire |
| HTTP `Content-Length` | Declared value if present | Does not prove how many bytes were actually received |
| TLS on-wire bytes | Encrypted TLS records | Not exposed via plain `Socket.getInputStream()` of SSLSocket as a payload counter |
| Traffic at NIC/OS | Transport/interface-layer bytes/packets | May include other traffic, headers, retries, or sampling |

For Unicode:

~~~java
String s = "café";
int utf16Units = s.length();                     // 4.
int utf8Bytes = s.getBytes(StandardCharsets.UTF_8).length; // 5.
~~~

An accented character can take multiple UTF-8 bytes. In HTML/JSON there is also escaping, gzip/br compression, or transfer framing; **do not use Java `String.length()` or `Content-Length` as wire byte counts**.

### Content-Length Is Not a Measurement

On an HTTP request, `Content-Length` may be declared by the client and may be absent when chunked transfer is used. A header can be wrong, spoofed, or no longer applicable after a proxy. If you need the exact body actually received, **count bytes on the `InputStream`**.

On an HTTP response, if a handler calls `sendResponseHeaders(200, 5)` and writes exactly 5 bytes, that is **5 body bytes at the server API**; total wire bytes also include the status line/headers and TCP framing. `sendResponseHeaders(200, 0)` in `jdk.httpserver` selects chunked encoding (not an empty body). If there is no body, the API allows `-1` where appropriate for the HTTP status.

### Counting Streams Without Double-Counting

A common Java mistake is subclassing `FilterOutputStream` and overriding both `write(int)` and `write(byte[], off, len)` while **calling `super.write(byte[], off, len)`** in the latter method. The default implementation may call `write(int)` byte by byte; if you also add `len`, the counter **double-counts**. In the two programs below, the bulk-write method calls **`out.write(b, off, len)` directly**, then adds `len` once.

Similarly, `FilterInputStream.read(byte[], off, len)` must update the counter from the **actual `n` returned**, not add `len` when only a partial read occurred. `read() == -1` is EOF, not a negative byte; `read(byte[]) == 0` means no new bytes were read.

## 7. Complete TCP Program: Endpoints and Bidirectional Bytes

The program **`TcpObserveDemo.java`** has a loopback `ServerSocket`, a server thread accepting a connection, and a TCP client. The client sends exactly four UTF-8 bytes `PING`, and the server reads four bytes then writes four bytes `PONG`. Two stream wrappers count bytes read/written. All addresses are captured **after connect/accept**, and timestamps are recorded with `System.nanoTime()`.

Save the file **`TcpObserveDemo.java`**:

~~~java
import java.io.FilterInputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class TcpObserveDemo {
    static class CountedIn extends FilterInputStream {
        long count;
        CountedIn(java.io.InputStream in) { super(in); }

        @Override
        public int read() throws IOException {
            int b = in.read();
            if (b >= 0) count++;
            return b;
        }

        @Override
        public int read(byte[] b, int off, int len)
                throws IOException {
            int n = in.read(b, off, len);
            if (n > 0) count += n;
            return n;
        }
    }

    static class CountedOut extends FilterOutputStream {
        long count;
        CountedOut(java.io.OutputStream out) { super(out); }

        @Override
        public void write(int b) throws IOException {
            out.write(b);
            count++;
        }

        @Override
        public void write(byte[] b, int off, int len)
                throws IOException {
            out.write(b, off, len); // Avoid double-counting.
            count += len;
        }
    }

    record ServerResult(
            InetSocketAddress local, InetSocketAddress remote,
            long payloadIn, long payloadOut) { }

    static ServerResult handleOnce(ServerSocket listener)
            throws Exception {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5_000);

            InetSocketAddress local =
                    (InetSocketAddress) peer.getLocalSocketAddress();
            InetSocketAddress remote =
                    (InetSocketAddress) peer.getRemoteSocketAddress();

            CountedIn in = new CountedIn(peer.getInputStream());
            CountedOut out = new CountedOut(peer.getOutputStream());

            byte[] message = in.readNBytes(4);
            if (!"PING".equals(new String(
                    message, StandardCharsets.UTF_8))) {
                throw new IOException("Unexpected request");
            }

            out.write("PONG".getBytes(StandardCharsets.UTF_8));
            out.flush();

            return new ServerResult(
                    local, remote, in.count, out.count);
        }
    }

    public static void main(String[] args)
            throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        ExecutorService worker =
                Executors.newSingleThreadExecutor();

        try (ServerSocket listener =
                     new ServerSocket(0, 10, loopback)) {
            Future<ServerResult> task =
                    worker.submit(() -> handleOnce(listener));

            try (Socket client = new Socket()) {
                long start = System.nanoTime();
                client.connect(
                        new InetSocketAddress(
                                loopback, listener.getLocalPort()),
                        3_000);
                long connected = System.nanoTime();
                client.setSoTimeout(5_000);

                InetSocketAddress clientLocal =
                        (InetSocketAddress) client.getLocalSocketAddress();
                InetSocketAddress clientRemote =
                        (InetSocketAddress) client.getRemoteSocketAddress();

                CountedIn in = new CountedIn(
                        client.getInputStream());
                CountedOut out = new CountedOut(
                        client.getOutputStream());

                long writeStart = System.nanoTime();
                out.write("PING".getBytes(StandardCharsets.UTF_8));
                out.flush();
                long written = System.nanoTime();

                byte[] response = in.readNBytes(4);
                long readDone = System.nanoTime();

                ServerResult server =
                        task.get(5, TimeUnit.SECONDS);

                System.out.println("serverLocalLoopback="
                        + server.local().getAddress()
                                .isLoopbackAddress());
                System.out.println("serverRemoteLoopback="
                        + server.remote().getAddress()
                                .isLoopbackAddress());
                System.out.println("clientLocalMatchesServerRemote="
                        + clientLocal.equals(server.remote()));
                System.out.println("clientRemoteMatchesServerLocal="
                        + clientRemote.equals(server.local()));
                System.out.println("clientPayloadSent=" + out.count);
                System.out.println("clientPayloadReceived=" + in.count);
                System.out.println("serverPayloadReceived="
                        + server.payloadIn());
                System.out.println("serverPayloadSent="
                        + server.payloadOut());
                System.out.println("reply="
                        + new String(
                                response, StandardCharsets.UTF_8));

                System.out.printf(
                        Locale.ROOT, "connectMs=%.3f%n",
                        (connected - start) / 1_000_000.0);
                System.out.printf(
                        Locale.ROOT, "writeAndFlushMs=%.3f%n",
                        (written - writeStart) / 1_000_000.0);
                System.out.printf(
                        Locale.ROOT, "responseReadMs=%.3f%n",
                        (readDone - written) / 1_000_000.0);
                System.out.printf(
                        Locale.ROOT, "totalMs=%.3f%n",
                        (readDone - start) / 1_000_000.0);
                System.out.println("durationsNonNegative="
                        + (connected >= start
                        && written >= writeStart
                        && readDone >= written));
            }
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac --release 17 TcpObserveDemo.java
java TcpObserveDemo
~~~

**An actual observed run** (millisecond values from this trial are for illustration only; not guaranteed to be fixed):

~~~text
serverLocalLoopback=true
serverRemoteLoopback=true
clientLocalMatchesServerRemote=true
clientRemoteMatchesServerLocal=true
clientPayloadSent=4
clientPayloadReceived=4
serverPayloadReceived=4
serverPayloadSent=4
reply=PONG
connectMs=1.782
writeAndFlushMs=0.731
responseReadMs=0.067
totalMs=10.826
durationsNonNegative=true
~~~

**The stable part** of the output is the loopback address checks, the endpoint cross-match, the byte count of 4 on each side, and the `PONG` content. **The `connect/write/read/totalMs` numbers vary with OS scheduling, JVM/JIT, timing, socket buffers, and machine load.** `totalMs` does not necessarily equal the sum of the three printed phases because it also includes buffer preparation, `task.get()`, thread synchronization, and other Java work.

### Verifying the Meaning of Byte Counts

- `clientPayloadSent=4`: the wrapper completed writing **4 bytes** to the `OutputStream` on the client.
- `serverPayloadReceived=4`: the server wrapper read **4 bytes** from the accepted socket.
- `serverPayloadSent=4` and `clientPayloadReceived=4`: the server wrote and the client read `PONG` accurately.
- This is not “total bytes on the wire” because it **excludes TCP/IP headers, SYN/ACK/FIN, retransmissions, and any OS traffic**.
- A `long` counter avoids quick overflow like `int` for large streams, though production also needs to consider `long` overflow for indefinitely long-running processes, as well as concurrency/atomicity when multiple threads update it.

### Why Is a Timeout Different from a Measurement?

`client.connect(addr, 3000)` sets a **3,000 ms connect timeout** for the call; it **does not mean connect takes 3 seconds**. `client.setSoTimeout(5000)` bounds each blocking socket read per the API, and does not automatically guarantee that the total upload/download completes in 5 seconds if small reads keep arriving before the limit. For SLAs, use an end-to-end deadline and cancel/close according to policy.

## 8. Complete HTTP Program: Peer Addresses and Handler/Body Timings

The class **`HttpObserveDemo.java`** uses `com.sun.net.httpserver.HttpServer` on loopback, routing POST `/observe`. The server reads the **request body** and counts bytes, then writes the **response body** and counts bytes. The client uses **`HttpClient.sendAsync(..., BodyHandlers.ofInputStream())`**, measuring time from starting `sendAsync` until the response object is available, then reads the body to EOF and measures the body-read duration.

**Important point:** `BodyHandlers.ofInputStream()` returns a stream that the caller must read/close; the response `Future` can complete once headers are available even though the body has not been fully read yet. This lesson intentionally uses this handler to separate **response object available** from **body fully consumed**. These two intervals cannot be labeled as separate DNS/TCP/TLS phases.

The server uses two counting wrappers like the TCP demo, operating on `HttpExchange.getRequestBody()` and `getResponseBody()`. Only request body and response body bytes are counted, **not HTTP headers or TCP/TLS bytes**.

Save the file **`HttpObserveDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class HttpObserveDemo {
    static final java.nio.charset.Charset UTF8 = StandardCharsets.UTF_8;
    static final CountDownLatch handled = new CountDownLatch(1);
    static final AtomicReference<Metrics> serverData =
            new AtomicReference<>();

    record Metrics(
            InetSocketAddress local, InetSocketAddress remote,
            long requestPayloadBytes, long responsePayloadBytes,
            long inputNanos, long responseHeadersNanos,
            long outputNanos, long handlerNanos) { }

    static final class CountedIn extends FilterInputStream {
        long count;

        CountedIn(InputStream in) { super(in); }

        @Override
        public int read() throws IOException {
            int x = in.read();
            if (x >= 0) count++;
            return x;
        }

        @Override
        public int read(byte[] b, int off, int len)
                throws IOException {
            int n = in.read(b, off, len);
            if (n > 0) count += n;
            return n;
        }
    }

    static final class CountedOut extends FilterOutputStream {
        long count;

        CountedOut(OutputStream out) { super(out); }

        @Override
        public void write(int value) throws IOException {
            out.write(value);
            count++;
        }

        @Override
        public void write(byte[] b, int off, int len)
                throws IOException {
            out.write(b, off, len);
            count += len;
        }
    }

    static void handle(HttpExchange exchange)
            throws IOException {
        long entered = System.nanoTime();

        try (exchange) {
            InetSocketAddress local =
                    exchange.getLocalAddress();
            InetSocketAddress remote =
                    exchange.getRemoteAddress();

            long startRead = System.nanoTime();
            CountedIn input =
                    new CountedIn(exchange.getRequestBody());
            ByteArrayOutputStream gathered =
                    new ByteArrayOutputStream();

            try (input) {
                byte[] buffer = new byte[16];
                int n;
                while ((n = input.read(buffer)) != -1) {
                    if (n > 32 - gathered.size()) {
                        throw new IOException(
                                "Body exceeds lab limit");
                    }
                    gathered.write(buffer, 0, n);
                }
            }
            long finishedRead = System.nanoTime();

            byte[] response =
                    ("ACK:" + input.count).getBytes(UTF8);
            exchange.getResponseHeaders().set(
                    "Content-Type",
                    "text/plain; charset=UTF-8");

            long startHeaders = System.nanoTime();
            exchange.sendResponseHeaders(200, response.length);
            long finishedHeaders = System.nanoTime();

            CountedOut output =
                    new CountedOut(exchange.getResponseBody());
            long startWrite = System.nanoTime();
            try (output) {
                output.write(response);
            }
            long finishedWrite = System.nanoTime();

            serverData.set(new Metrics(
                    local, remote, input.count, output.count,
                    finishedRead - startRead,
                    finishedHeaders - startHeaders,
                    finishedWrite - startWrite,
                    finishedWrite - entered));
        } finally {
            handled.countDown();
        }
    }

    public static void main(String[] args)
            throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 16);
        ExecutorService pool =
                Executors.newFixedThreadPool(2);
        server.createContext(
                "/observe", HttpObserveDemo::handle);
        server.setExecutor(pool);
        server.start();

        try {
            String root = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpRequest request = HttpRequest.newBuilder(
                    URI.create(root + "/observe"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "HELLO", UTF8))
                    .build();

            long beforeSend = System.nanoTime();
            HttpResponse<InputStream> response =
                    client.sendAsync(
                            request,
                            HttpResponse.BodyHandlers.ofInputStream())
                    .get(5, TimeUnit.SECONDS);
            long responseAvailable = System.nanoTime();

            byte[] responseBytes;
            try (InputStream input = response.body()) {
                // Demo server returns exactly 5 bytes; DO NOT use
                // unbounded readAllBytes() for untrusted responses.
                responseBytes = input.readAllBytes();
            }
            long readCompleted = System.nanoTime();

            if (!handled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Server did not finish");
            }
            Metrics metrics = serverData.get();

            System.out.println(
                    "httpStatus=" + response.statusCode());
            System.out.println(
                    "serverLocalLoopback="
                    + metrics.local().getAddress()
                            .isLoopbackAddress());
            System.out.println(
                    "serverRemoteLoopback="
                    + metrics.remote().getAddress()
                            .isLoopbackAddress());
            System.out.println(
                    "serverRequestPayloadBytes="
                    + metrics.requestPayloadBytes());
            System.out.println(
                    "serverResponsePayloadBytes="
                    + metrics.responsePayloadBytes());
            System.out.println(
                    "clientResponsePayloadBytes="
                    + responseBytes.length);
            System.out.println(
                    "responseText="
                    + new String(responseBytes, UTF8));

            System.out.printf(
                    Locale.ROOT,
                    "timeUntilResponseObjectMs=%.3f%n",
                    (responseAvailable - beforeSend)
                            / 1_000_000.0);
            System.out.printf(
                    Locale.ROOT,
                    "clientBodyReadMs=%.3f%n",
                    (readCompleted - responseAvailable)
                            / 1_000_000.0);
            System.out.printf(
                    Locale.ROOT,
                    "clientTotalMs=%.3f%n",
                    (readCompleted - beforeSend)
                            / 1_000_000.0);
            System.out.printf(
                    Locale.ROOT,
                    "serverRequestReadMs=%.3f%n",
                    metrics.inputNanos() / 1_000_000.0);
            System.out.printf(
                    Locale.ROOT,
                    "serverResponseHeadersMs=%.3f%n",
                    metrics.responseHeadersNanos()
                            / 1_000_000.0);
            System.out.printf(
                    Locale.ROOT,
                    "serverResponseWriteMs=%.3f%n",
                    metrics.outputNanos() / 1_000_000.0);
            System.out.printf(
                    Locale.ROOT,
                    "serverHandlerMs=%.3f%n",
                    metrics.handlerNanos() / 1_000_000.0);
        } finally {
            server.stop(1);
            pool.shutdown();
            if (!pool.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Java 17+ commands:

~~~bash
javac --release 17 HttpObserveDemo.java
java HttpObserveDemo
~~~

**An actual run recorded on a compatible JDK** (timings can differ completely on other machines):

~~~text
httpStatus=200
serverLocalLoopback=true
serverRemoteLoopback=true
serverRequestPayloadBytes=5
serverResponsePayloadBytes=5
clientResponsePayloadBytes=5
responseText=ACK:5
timeUntilResponseObjectMs=70.043
clientBodyReadMs=0.703
clientTotalMs=70.747
serverRequestReadMs=4.692
serverResponseHeadersMs=19.544
serverResponseWriteMs=0.223
serverHandlerMs=28.447
~~~

**Explaining the real measurements:**

- `serverRequestPayloadBytes=5`: the handler actually **read 5 bytes** from the HTTP request body `HELLO`.
- `serverResponsePayloadBytes=5`: the handler actually **wrote 5 bytes** through the response body stream `ACK:5`.
- `clientResponsePayloadBytes=5`: the client received 5 bytes into `byte[]` after reading the `InputStream` to EOF.
- These bytes **do not include the HTTP request line/status line, headers, chunked framing, or TCP/IP overhead**.
- `timeUntilResponseObjectMs` measures from before `sendAsync` until `get(...)` returns the response object with the streaming body. It includes scheduling, connecting if needed, sending the request, the server response, and the API producing the response; **you cannot separate DNS/connect/TLS/TTFB from this number alone**.
- `clientBodyReadMs` is the duration of reading the stream to EOF; for large responses, it includes network speed and Java-side read execution time.
- `serverRequestReadMs` measures the body read loop **after the handler was invoked**, excluding client DNS/TCP connect time and request header parsing time prior to the handler.
- `serverResponseHeadersMs` measures a single `sendResponseHeaders(200, 5)` call; **it does not mean the client has necessarily received the headers** at that point.
- `serverResponseWriteMs` measures writing and closing the `OutputStream` at the server boundary; it does not guarantee the peer has processed the bytes.
- `serverHandlerMs` does not necessarily equal the sum of the three component durations because of response byte initialization, header map operations, code execution between steps, and scheduling.

**Security limitations of the demo:** the server does not check the HTTP method before processing, has no authentication, and the client sends a known 5-byte body. The handler caps at 32 bytes and throws an exception if exceeded without turning it into a proper 413/4xx response; production must have an error policy, request timeouts, input validation, bounded concurrency, and safe logging. `InputStream.readAllBytes()` in the demo client is only safe because the response is 5 bytes long; do not use it unbounded against untrusted endpoints.

## 9. Attaching Metrics to the HTTP Request Lifecycle at the Right Time

For an HTTP server receiving requests, there are typically multiple observation layers:

~~~text
Socket/TLS/server infrastructure:
  TCP accept -> TLS handshake -> parse request line/headers
                                    |
                                    v
HttpHandler entry:
  request-body read -> validation -> business processing
       -> response headers -> response-body write -> exchange close
                                    |
                                    v
Client:
  response object available -> body read/consume -> app processing done
~~~

**`HttpHandler.handle()` only begins once the server has dispatched the request to the handler.** Therefore, measuring `System.nanoTime()` at the start of the handler **excludes** TCP connection establishment time and the time spent reading all request headers beforehand. If you want to measure the full pipeline, you need timestamps at the reverse proxy/network instrumentation and to propagate a trusted request ID/tracing context.

### Filters and Counting Streams

`HttpExchange.setStreams(InputStream, OutputStream)` allows a `Filter` to **wrap** request/response streams for downstream handlers. A `Filter` can start a timer at the beginning of `doFilter`, measure byte counts via wrappers, call `chain.doFilter(exchange)`, and then emit final metrics.

~~~java
// Fragment in a subclass of com.sun.net.httpserver.Filter.
@Override
public void doFilter(HttpExchange exchange, Chain chain)
        throws IOException {
    long began = System.nanoTime();
    // You can wrap getRequestBody/getResponseBody with CountedIn/CountedOut
    // and call exchange.setStreams(...), but you must preserve the original streams,
    // follow the lifecycle, and avoid double-counting.
    try {
        chain.doFilter(exchange);
    } finally {
        long elapsed = System.nanoTime() - began;
        // Record elapsed, status, bytes, and outcome with safe metric tags.
    }
}
~~~

This is a fragment, not standalone runnable code; `CountedIn/CountedOut` are defined in the two full programs above. Keep in mind:

1. A `Filter` only measures from when the **Filter is invoked**, not from client DNS/TCP connect.
2. A request may be rejected inside a `Filter` before reaching the handler; you still need to record status/error.
3. `setStreams` must wrap **the original streams** so no data is lost.
4. Close/cancel the exchange properly; do not read the body unboundedly just to populate metrics.
5. If gzip middleware is present, placing the counter **before or after compression** yields two different byte counts; name metrics clearly as `compressed_bytes` and `uncompressed_bytes`.
6. If multiple filters wrap the same stream, avoid counting the same bytes repeatedly at multiple layers and summing them as total network traffic.

### HttpClient and BodyHandler

With `HttpClient.sendAsync`:

- `BodyHandlers.ofString()` typically completes the `Future` after the body has been assembled into a `String`. A timer around `future.get()` measures multiple phases **combined**.
- `BodyHandlers.ofInputStream()` allows the `Future` to complete when the body stream is available; the caller must **read to EOF or close** the stream. A timer ending at the `Future` does not mean the body has been fully consumed.
- `BodyHandlers.ofPublisher()` requires subscribing and receiving `onComplete/onError` or cancelling; a timer around the `Future` only measures until the publisher object is returned, not body completion.
- To count body bytes on the client side, count each byte read from `InputStream` or each `ByteBuffer.remaining()` processed in the subscriber. **Do not use `HttpResponse.headers().firstValueAsLong("Content-Length")` as the actual observed byte count.**
- `HttpResponse.uri()` is the **effective URI**, not the socket remote address.

## 10. NIO and TCP Sockets: write() Return Value Is Not Bytes Read by the Peer

Suppose `SocketChannel.write()` returns 128:

- 128 bytes were accepted by the channel write operation per the API.
- It does not prove the network peer has received all 128 bytes, that the remote application has parsed the message, or that the server has committed a transaction.
- When nonblocking, a channel write can return 0, and a single write may not drain an entire `ByteBuffer`. You must continue when writable, not discard the remainder.
- When an error occurs later, part of the payload may already have been sent before the failure. Application-level retries require protocol idempotency and clear framing.

With `OutputStream.write(bytes)`, method success means the local write call completed per the API; it may have buffered bytes in the OS/JDK. `flush()` does not guarantee the data has been ACKed and processed by the peer. If you need an ACK, build a separate response/ack protocol and measure latency until the business response arrives.

### How Do TLS and Proxies Make Byte Counts Differ?

| Case | What the application byte counter sees | Actual bytes on the network |
| --- | --- | --- |
| Plain TCP echo | PING 4 bytes, PONG 4 bytes | 4 payload bytes each way **plus** TCP/IP/Ethernet overhead and control packets |
| TLS application data | Plaintext bytes through `SSLSocket` | Encrypted TLS records with overhead, possibly handshake/resumption |
| HTTP/1.1 request | Request-body bytes read from `HttpExchange` | Headers, chunk framing, TCP/IP, and possibly TLS |
| HTTP/2 | HTTP message DATA payload at app boundary | Frames, headers (HPACK), flow control, multiplexing, TLS |
| GZIP response | Either compressed or decompressed bytes depending on hook placement | HTTP/TLS/transport differs depending on compression and chunking |
| Retry/redirect | Potentially multiple HTTP exchanges for one business call | Total bytes transmitted can exceed the initial logical payload |

When using the Java HTTP server API, the request body stream **has already passed through the HTTP parsing layer**. When using `SSLSocket`, you normally read **TLS-decrypted** data at the application layer and do not see TLS record sizes directly. If you need NIC-level bytes, use OS/network monitoring or proxy metrics, and explicitly state which overhead/traffic the tool is counting. Do not take `Content-Length + headers.length` and call it real traffic if chunked framing, compression, retransmissions, or TLS are involved.

## 11. Designing Metric Names, Tags, and Correlation IDs

Counters/timers should have clear definitions:

| Suggested metric | Unit | Measurement scope |
| --- | --- | --- |
| `tcp_connect_duration_seconds` | seconds (histogram) | Around `Socket.connect` when actually opening a new connection |
| `tcp_payload_bytes_sent_total` | bytes | Bytes successfully passed through the app output wrapper |
| `tcp_payload_bytes_received_total` | bytes | Bytes read by the app input wrapper |
| `http_request_body_bytes_read_total` | bytes | Body bytes read from `HttpExchange` input |
| `http_response_body_bytes_written_total` | bytes | Body bytes written to `HttpExchange` output |
| `http_client_response_available_seconds` | seconds | Before `sendAsync` until the streaming `BodyHandler` `Future` completes |
| `http_client_body_consume_seconds` | seconds | From body stream available until EOF/`onComplete` |
| `http_server_handler_duration_seconds` | seconds | Start/end of handler, excluding pre-handler network phases |
| `http_server_request_body_read_seconds` | seconds | Time spent reading request body in handler |
| `http_server_response_write_seconds` | seconds | Time spent writing/closing response stream |
| `network_io_failures_total` | events | `IOException`, timeout, unexpected EOF, cancellation by type |

**Seconds** is the standard unit for timers/histograms when exporting metrics; the demos print **milliseconds** only for learner readability. Never change units from ms to seconds while keeping the old metric name, or record bytes while calling them kilobytes without conversion.

### Avoiding High-Cardinality Tags

A metric keyed by `remote_ip + remote_port + full_uri + request_id` can create **unbounded time series** and break storage/monitoring. Use bounded tags instead, such as:

- `protocol=tcp/http/https`
- `direction=inbound/outbound`
- `route=/orders/{id}` instead of the full URI with query parameters and IDs
- `method=GET/POST`
- `status_class=2xx/4xx/5xx`
- `outcome=success/error/timeout/cancelled`
- `peer_service=known-service-name` instead of ephemeral IP:port

IP addresses and ports can go into **diagnostic logs/traces with sampling, retention, and access control**, rather than defaulting to Prometheus labels. URIs with query strings may contain secrets; avoid logging raw queries or `Authorization` headers. An IP address can also be personal data; apply appropriate privacy and retention policies.

### Correlation ID and Trace/Span

Attach a distinct `requestId` to each HTTP exchange and propagate trace context safely across trusted services. When logging:

~~~text
requestId=...          (used only to look up one request, not as a metric label)
route=/observe
method=POST
status=200
peerSocketAddress=...  (optional, privacy/access controlled)
requestPayloadBytes=5
responsePayloadBytes=5
handlerElapsedMs=...
outcome=success
~~~

Do not fabricate DNS/TLS timings from `handlerElapsedMs`. If there is a reverse proxy/gateway, use per-layer traces/spans with synchronized context to analyze *client send* → *proxy* → *upstream handler* → *client body done*.

## 12. Distinguishing Latency and Throughput

**Latency** is the duration of a single operation: `connectMs`, `bodyReadMs`, `serverHandlerMs`. **Throughput** is typically the bytes/time rate over a window:

\[ \text{throughput (bytes/s)} = \frac{\text{bytes processed}}{\text{elapsedSeconds}} \]

If 10,000,000 bytes are transferred in 2 seconds, the average throughput at that boundary is 5,000,000 bytes/s. However, you must specify which steps are included: does it include DNS/connect/TLS? Only body read time? Is compression enabled? Are there retries? Do not compare throughput between two systems if their time/byte definitions differ.

Use `System.nanoTime()` to compute elapsed time and handle near-zero elapsed values when computing rates. Do not divide by 0 or report “infinite” throughput just because timer resolution or chunks are small. For few-byte requests on loopback like in the demo, instantaneous throughput will be extremely noisy and nearly meaningless; measuring across many iterations/histograms and p50/p95/p99 distributions under realistic load is much more useful.

**p95 latency** indicates that roughly 95% of observations have latency no greater than a corresponding threshold, but it must be computed over **a set of measurements with the same definition**. Do not add the p95 of DNS + connect + body to infer total p95: percentiles do not add linearly. With concurrent requests, measure each request's span and aggregate by cohort.

## 13. Common Observability Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| `getRemoteSocketAddress() == null` | Socket is not connected yet | Check state, read endpoint after connect/accept |
| Server logs itself as remote | Swapped local/remote on accepted socket | Remember local=server, remote=direct client |
| HTTP remote IP is always the proxy IP | Server receives connections from a reverse proxy | Do not treat socket peer as end user; use a trusted proxy policy |
| Using `HttpResponse.uri().getHost()` as remote IP | URI host is not the socket peer | Log logical target URI; for socket tuple, use lower-level hooks |
| Latency suddenly negative | Subtracted timestamps in wrong order or mixed clocks | Use `System.nanoTime` within the same JVM in the right order |
| Claiming HttpClient has direct DNS/TCP/TLS timings | Java 17 public API does not expose per-phase event timings | Measure API bounds or use appropriate instrumentation |
| `sendAsync().get()` measures body time inaccurately | Used `ofInputStream` without reading body to EOF | Measure from stream available to EOF/close as well |
| HTTP `Content-Length` differs from actual body | Header is declared; may be chunked/invalid | Count bytes read/written on the stream |
| Byte count = character count | UTF-8 has multi-byte characters | Use `getBytes(UTF_8).length` or an actual byte counter |
| `CountingOutputStream` reports double | Bulk write calls `super.write` and adds `len` | Call `out.write` directly as in the demo |
| `CountingInputStream` increments on EOF | Added to count when `n=-1` or `n=0` | Only add when `n > 0`, `read() >= 0` |
| NIO `write()` returns less than `remaining` | Partial write, nonblocking | Keep buffer and continue writing when writable |
| NIO `read()` returning 0 treated as EOF | Nonblocking has no data yet | Distinguish between `0` and `-1` |
| UDP peer read from unconnected socket | `getRemoteSocketAddress` is null | Read `DatagramPacket` source or `receive()` return value |
| App bytes less than NIC bytes | TCP/IP/TLS/HTTP overhead, retries | Name the measurement layer clearly; combine with OS/proxy counters |
| Response 200 but processing not finished | Handler/body consumer/DB stage still running | Measure business completion, not just headers |
| HTTP/2 reused connection makes `connectMs=0` | Request did not open a new socket | Record connection reused/metric missing; do not emit fake connect latency |
| Measurements vary wildly during debugging | JIT, warmup, logging/blocking, scheduling | Warmup, sufficient samples, avoid uncontrolled microbenchmarks |
| Metric labels grow unboundedly | Used IP:port/URI/requestId as tags | Use route templates and bounded tags |
| Logs contain tokens or personal data | Overly broad logging | Redact, apply retention/access controls |
| Timers don't sum to total steps | Gaps, overlap, scheduling, or other phases | Document timeline model and timestamps clearly |
| Timings after timeout are dropped | Outcome not recorded on exception | Record success/error/timeout/cancelled in `finally` |

### Avoiding Multiple Counting from Nested Wrappers

If a request body is gzip-compressed, a wrapper placed at the source stream might count **compressed bytes**, while a wrapper after decompression counts **decompressed bytes**. Both are useful, but **they must not be summed** and called total network bytes. Similarly, inbound/outbound proxies measure the same payload in different directions; if you want total infrastructure traffic, define it precisely to avoid double-counting.

### Never Assume write() Returning Is an ACK

Completing `OutputStream.write()` or `SocketChannel.write()` does not prove the peer application has received the data, let alone processed the business operation. If a POST creates a record and the connection drops after `write`, a retry could cause duplicates. Use an idempotency key, correlation ID, and application-layer ACK to measure *business completion*.

## 14. Production Rules for Collecting Local/Remote, Latency, and Bytes

1. **Name which layer “local/remote” refers to:** socket peer, proxy peer, upstream service, logical HTTP authority, or forwarded client identity.
2. **Read endpoints at the right time:** after connect/accept, and handle `null`/unresolved/IPv6.
3. **Use `nanoTime` for durations, `Instant.now` for timestamps:** never compare absolute `nanoTime` across JVMs/machines.
4. **Measure the full lifecycle:** create/resolve/connect/handshake/write/response/body/process depending on what the API actually owns. Do not invent unobservable phases.
5. **Mark reused connections clearly:** requests over keep-alive/HTTP/2 have no new TCP connect; do not record fake connect time.
6. **Count actual bytes from return values or wrappers:** do not rely solely on `Content-Length`/`String.length`.
7. **Distinguish “application payload” from “wire bytes”:** you cannot get TLS/IP headers/retries from an `InputStream` alone.
8. **Bound memory and I/O:** max body size, deadlines, backpressure, connection limits, queue limits.
9. **Observe errors and cancellations too:** record metrics in `finally` with clear status/outcome; do not report success if a stream/callback has not completed.
10. **Watch privacy:** IP addresses, hostnames, URLs, and queries can be sensitive; apply sampling/redaction/retention.
11. **Limit cardinality:** use route templates and service labels for metrics; keep raw endpoints in access-controlled logs if needed.
12. **Distinguish connection time from server processing:** a server `HttpHandler` does not measure client DNS/connect; a client `HttpResponse` does not see the actual socket peer.
13. **Define total latency:** measure from start until body and required processing complete; only use time-to-headers separately when intentional.
14. **Use clear units:** `bytes`, `seconds`, `milliseconds`, `requests`; keep conversions consistent.
15. **Test edge cases:** partial reads/writes, 0-byte nonblocking, EOF, DNS failure, connect timeout, TLS error, truncated body, 413, proxy, redirect, cancellation.

## 15. Self-Check Questions

**Question 1.** How do the local/remote addresses of a TCP client and a server-accepted socket relate?  
**Answer:** For a direct connection in the same network view, the client's local matches the accepted socket's remote; the client's remote matches the accepted socket's local. A `ServerSocket` listener only has a local bind endpoint, not a single remote peer.

**Question 2.** Why can `socket.getRemoteSocketAddress()` be null?  
**Answer:** The socket is not yet connected or has no corresponding peer. Do not dereference it; read it after connect/accept.

**Question 3.** Can you use the remote IP to identify a logged-in user?  
**Answer:** No. The IP is the socket peer address, which may be a proxy/NAT; you need authentication/authorization.

**Question 4.** Is `HttpResponse.uri()` the socket remote address of Java `HttpClient`?  
**Answer:** No. It is the effective logical URI; it may involve DNS, proxies, redirects, and connection reuse. Java 17 public `HttpResponse` does not have `getRemoteSocketAddress()`.

**Question 5.** Does `HttpExchange.getRemoteAddress()` give the end user's IP behind Nginx?  
**Answer:** Usually it is the IP of Nginx/the proxy connecting directly. Forwarded headers are only trustworthy if processed according to a trusted proxy policy.

**Question 6.** Is `System.nanoTime()` for calendar date/time or durations?  
**Answer:** Durations within the same JVM. For real timestamps, use `Instant`/wall-clock time.

**Question 7.** Is measuring `InetAddress.getAllByName()` guaranteed to equal the latency of a real DNS request on the network?  
**Answer:** No. The API has caching and resolver/OS behavior; it measures the in-process call duration, not necessarily a full recursive lookup.

**Question 8.** Does `Socket.connect(addr, 3000)` mean connect always takes 3,000 ms?  
**Answer:** No. `3000` is the maximum timeout for the connect call per the API; actual duration is measured with `nanoTime`.

**Question 9.** With `HttpClient.sendAsync(..., BodyHandlers.ofInputStream())`, does the `Future` completing mean the body has been fully read?  
**Answer:** No. You also need to measure the time to read the stream to EOF or close it when no longer needed.

**Question 10.** Why can't `responseFutureCompletionMs` be attributed to `tcpConnectMs + tlsMs`?  
**Answer:** It combines multiple phases and scheduling, may involve connection reuse or proxies/redirects, and does not expose phase internals.

**Question 11.** Does `Content-Length: 1000` prove the handler read 1000 bytes?  
**Answer:** No. That is a declared header; measure the actual bytes read from `InputStream`.

**Question 12.** Is counting bytes on the server with `String.length()` accurate for Vietnamese text?  
**Answer:** No. UTF-8 uses multiple bytes for accented characters; use encoded bytes or a stream counter.

**Question 13.** Why can `CountingOutputStream` double-count?  
**Answer:** Overriding bulk write to call `super.write` (which may call `write(int)` per byte) and also adding `len`; the right approach, as in the demo, is calling `out.write` directly.

**Question 14.** Is `SocketChannel.read(buffer) == 0` EOF?  
**Answer:** No. `0` means no bytes were received in that read call; `-1` is EOF.

**Question 15.** If `SocketChannel.write(buffer)` returns 17 while the buffer still has `remaining`, can the message be considered fully sent?  
**Answer:** No. Remaining bytes must be sent when the channel is writable.

**Question 16.** Where does an unconnected UDP `DatagramSocket` get a packet's source?  
**Answer:** From `DatagramPacket.getSocketAddress()` after `receive`, not from `getRemoteSocketAddress()` on an unconnected socket.

**Question 17.** If `HttpExchange.getResponseBody()` count=5000, did the NIC send exactly 5000 bytes?  
**Answer:** No. That is the response body byte count at the app boundary, excluding HTTP/TLS/TCP/IP and overhead/retries.

**Question 18.** Does response status 200 mean the handler business logic has committed and the client received the full response?  
**Answer:** Not automatically. You must check body lifecycle, write completion, business logic, and protocol-level ACKs.

**Question 19.** Should you create metric labels for remote IP:port and the full request URI?  
**Answer:** No: cardinality becomes very high and risks exposing sensitive data; use route templates and known service names.

**Question 20.** Can you add p95 DNS, p95 TCP connect, and p95 body to get total p95?  
**Answer:** No. Percentiles do not add linearly; measure total duration per request and compute the distribution.

## 16. Official Documentation

- Oracle Java SE 17 — `Socket`, local/remote addresses and connect timeout: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- Oracle Java SE 17 — `ServerSocket`, bind/local/accept: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- Oracle Java SE 17 — `InetSocketAddress` and resolved/unresolved host: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html
- Oracle Java SE 17 — `InetAddress` and name lookup: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html
- Oracle Java SE 17 — `SocketChannel`, read/write, local/remote: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html
- Oracle Java SE 17 — `DatagramSocket`, packet peer vs connected address: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html
- Oracle Java SE 17 — `DatagramChannel`, receive source and ByteBuffer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html
- Oracle Java SE 17 — `HttpExchange`, `getLocalAddress`/`getRemoteAddress`/`getRequestBody`/`getResponseBody`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- Oracle Java SE 17 — `HttpClient`, request timeout, `send`/`sendAsync`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 17 — `HttpResponse`, URI/status/headers/version/sslSession and body semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Oracle Java SE 17 — `HttpResponse.BodyHandlers.ofInputStream` streaming: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- Oracle Java SE 17 — `FilterInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FilterInputStream.html
- Oracle Java SE 17 — `FilterOutputStream` (careful with bulk write): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FilterOutputStream.html
- Oracle Java SE 17 — `System.nanoTime()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()
- Oracle Java SE 17 — `SSLSocket`/`startHandshake`, TLS: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html
- Oracle Java SE 17 — `HttpExchange.setStreams` for Filters: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html#setStreams(java.io.InputStream,java.io.OutputStream)

# Building a Slow-Sending Client to Verify Timeouts and Resource Limits (Java 17+)

## 1. What Can a Slow Request Cause?

An HTTP server does not only consume CPU when executing business logic. Right from the moment it accepts a connection, it may have to hold a **TCP socket, buffers, parser state, a thread, or an event-loop slot** while waiting for the client to send the request line, headers, and request body. If a client sends very slowly — or only sends a few bytes and then goes silent — a single connection can hold resources far longer than intended.

Real-world scenarios include: mobile devices on weak networks, clients uploading over unstable connections, clients stalling mid-request due to a hung application, reverse proxies or users canceling uploads, or request headers arriving over a connection with near-zero throughput. A server needs to both accept legitimate slow clients and enforce **deadlines, byte limits, and concurrency limits** so that resources cannot be occupied indefinitely.

This lesson belongs to **Java Advance - networking → Networking Labs** and directly addresses the topic **“Building a Slow-Sending Client to Verify Timeouts and Resource Limits”**. We will write **controlled slow-sending clients over loopback**, **small test servers**, and **test suites that can be compiled/run with Java 17**. The goal is to verify defensive mechanisms, not to generate massive traffic or disrupt external services.

### 1.1. Model of a Slow-Sent Connection

~~~text
    SLOW CLIENT                                 TCP SERVER
        |                                            |
        |--- TCP connect --------------------------->|  accept
        |                                            |  hold socket
        |--- "G" ----------------------------------->|  read 1 byte
        |      ... sleep 90 ms                       |  keep waiting
        |--- "E" ----------------------------------->|  read 1 byte
        |      ... sleep 90 ms                       |  keep waiting
        |--- "T" ----------------------------------->|  read 1 byte
        |                                            |
        |   each wait < idle read timeout            |
        |   but total time can be very long          |
        |                                            |
        |<--- timeout / close -----------------------|  total deadline
        |                                            |  release slot
~~~

**Key point:** an **idle timeout** reset on every read may fail to detect a client that keeps sending 1 byte before the timeout expires. To protect the total time spent receiving a request, you need an **absolute request deadline** measured from a fixed starting point, alongside an **idle-gap timeout**.

### 1.2. Slow Sender Is Not the Same as Slow Receiver

| Scenario | What is the client doing? | Where are server resources likely held? |
| --- | --- | --- |
| **Slow sender / slow reader input** | Sends request line/headers/body very slowly | Server is waiting to **read request bytes** |
| **Slow receiver** | Server sends response, but client reads very slowly | Server is **writing response**, send buffer fills up |
| **Very large request** | Client sends many bytes, possibly still fast | Heap, parser, disk, quota, CPU |
| **Many concurrent connections** | Client opens many sockets | File descriptors, active handlers, thread/executor queue |
| **Slow server application processing** | Request may have already been sent completely | Backend DB/service, CPU, locks |

This lesson focuses on the **slow sender** and how to measure **read timeout / total deadline / request-size / active connection budget**. Response write timeouts are a separate problem; do not use observations from this lesson to conclude that the entire network stack is protected.

## 2. Learning Objectives

After completing this lesson, you will:

1. Build a Java client that sends a **request-line or header byte-by-byte with pauses** over `Socket`, without needing an external server.
2. Build a client that **sends a few bytes and then stops** to test the server read idle timeout.
3. Distinguish `ServerSocket.setSoTimeout(...)` for `accept()` from `Socket.setSoTimeout(...)` for **blocking `InputStream.read()`**.
4. Observe experimentally that a byte trickle can bypass an idle-gap timeout but is caught by a **total request deadline**.
5. Configure **max request header bytes** and **max body/frame size**, and check the limit **before allocating**.
6. Test a **Semaphore** limiting active handlers and observe a second request being rejected when the slot is occupied.
7. Verify that slots, executors, and sockets **are released** on timeout, rejection, or request completion.
8. Explain why a **successful TCP connect** does not guarantee a complete HTTP request.
9. Know when a server chooses HTTP 408/431/413, and when it closes the connection **without a valid response**.
10. Know how to choose idle timeout, total timeout, min data rate, quotas, and overload policy by workload, avoiding unfairly rejecting users on slow networks.
11. Design fault-injection tests synchronized with `CountDownLatch`/`Future`, without relying randomly on OS scheduling speed.
12. Observe metrics: active connections, wait time, bytes received, idle/total expirations, size rejections, and cleanup.
13. Understand the limitations of minimal raw TCP/HTTP examples compared to `com.sun.net.httpserver.HttpServer` or a production gateway.

## 3. Limits That Must Be Measured Separately

### 3.1. Comparing Deadlines and Capacity

| Limit | Measured from what point? | What risk does it block? |
| --- | --- | --- |
| **Accept wait timeout** | Each `ServerSocket.accept()` call waiting for a new connection | Test server does not hang when no client arrives |
| **Idle read timeout** | A blocking `InputStream.read()` call waiting for the next byte | Client stops sending for a period |
| **Total header deadline** | From starting to receive headers until CRLFCRLF ends | Client sends steadily but **too slowly overall** |
| **Total request/body deadline** | From a defined request/body start point | Upload drags on indefinitely via tiny chunks |
| **Max header bytes/count** | Total bytes/fields parsed | Huge headers, parser/memory exhaustion |
| **Max body bytes** | Actual bytes received or verified declared length | Unbounded allocation or streaming to disk |
| **Min upload rate** | A measurement window longer than jitter and TLS pauses | Sustained long-term slow trickle |
| **Max active connections/handlers** | Slots currently in use | Many slow clients holding threads/file descriptors |
| **Bounded work queue** | Number of tasks waiting for a handler | Executor building an unbounded backlog |
| **Idle keep-alive timeout** | Connection that finished one request waiting for the next | Wasting sockets on inactive connections |
| **Max response write time** | Sending response to a slow-reading client | Blocked OutputStream / outbound buffers |
| **Max lifetime / global budget** | Connection age or total held resources | Resources held forever across multiple exchanges |

**Do not use a single timeout for every phase.** For example, `Socket.setSoTimeout(250)` does not automatically enforce a 250 ms total HTTP request timeout; each successful read lets the client wait longer. Similarly, `ServerSocket.setSoTimeout(5000)` does not mean an accepted socket can only live for 5 seconds.

### 3.2. Idle-Gap Timeout Differs from Total Deadline

Suppose the idle timeout is 250 ms and the absolute deadline is 650 ms:

~~~text
Time (ms):    0      90      180     270     360     450    540     650
Client:       G ---- E ----- T ----- ' ' ---- / ---- ' ' --- H ----- (stop)
Idle gap:     90     90      90      90      90      90       <250
Total age:    ------------------------------------------------->650

Single idle timeout: never expires while each byte arrives.
Total deadline: request lacks CRLFCRLF at 650 ms -> reject.
~~~

A client sending one byte steadily every 100 ms can remain in the “just sent a byte” state for minutes. Defending against this relies on a **deadline from the start of the request** to prevent indefinite prolongation. In this lab, we use `System.nanoTime()` for elapsed time; production code should not use `System.currentTimeMillis()` as a monotonic clock due to NTP/clock corrections.

### 3.3. Header Byte Cap Differs from Body Byte Cap

- The request line and header fields are bounded before the server moves on to reading the body.
- In HTTP/1.1, **CRLFCRLF** terminates the header section; if there is a `Content-Length`/chunked request, the body follows it.
- Body size must be checked against **actual bytes received**, not merely by trusting the `Content-Length` sent by the client.
- If the body uses compression, it may be necessary to limit both **encoded bytes** and **decompressed bytes**.
- The server must not allocate `new byte[declaredContentLength]` before verifying that the length is valid and within quota.
- Closing the connection early can prevent the client from finishing an upload, but errors after responding/closing must be managed so sockets are not leaked or thrashing.

## 4. Preparing a Safe Experiment

Run the experiments only on your own machine:

- The test server binds to **`127.0.0.1`** (loopback) on port `0` so the OS picks a free ephemeral port.
- Each case uses at most one or a few connections; do **not** scan hosts or open thousands of sockets.
- Test timeouts are short (in milliseconds) so runs finish predictably; **do not use these values as production defaults**.
- Use `Future.get(timeout)` and `CountDownLatch.await(timeout)` so tests never hang indefinitely.
- Close `Socket` and `ServerSocket`, and shut down `ExecutorService` in `finally`.
- Do not send simulated slow requests to public APIs or unauthorized systems. In particular, bulk stress/probing against external services can impact real users.
- Note clearly that each passing result is evidence **for the specific test server**; other implementations may return different status codes or close TCP without sending an HTTP response.

Environment requirements:

~~~bash
java -version
javac -version
~~~

Use **JDK 17 or newer**. The programs below use `switch` expressions and Java features compiled with `javac --release 17`; no Maven/Gradle libraries, Docker, TLS certificates, or Internet access are required.

## 5. Controlling the Send Rate with Socket

### 5.1. Sending a Request Byte-by-Byte

A high-level `HttpClient` manages framing/headers automatically, which is great for normal HTTP applications but **inconvenient for controlling individual bytes of the request-line and newline timing**. To test a slow-sending client at the wire level, use `Socket.getOutputStream()`:

~~~java
try (Socket client = new Socket("127.0.0.1", port)) {
    OutputStream out = client.getOutputStream();
    byte[] request = "GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
            .getBytes(StandardCharsets.US_ASCII);

    for (byte b : request) {
        out.write(b);
        out.flush();
        Thread.sleep(90);  // Lab only: control the sending rate.
    }
}
~~~

This is an **illustrative code snippet**, without `port`, imports, or a server, and is not a standalone program. It highlights the ability to **flush and insert pauses** as the test requires.

**Caveat for real experiments:** TCP may coalesce or segment packets; `write(1 byte)` does not guarantee a one-byte TCP segment on the wire. `TCP_NODELAY` can alter Nagle's algorithm behavior, but the essence of the test is that **the server observes bytes arriving slowly**, without needing to assert that each write produces a separate packet.

### 5.2. Sending a Little and Then Stopping

~~~java
out.write("GET /".getBytes(StandardCharsets.US_ASCII));
out.flush();
Thread.sleep(500); // Stop sending before headers are complete.
~~~

If the server is waiting to read the next byte with an idle read timeout of 250 ms, it can time out before the client resumes sending. **Do not close the socket immediately** for this type of test; closing the socket produces EOF instead of demonstrating a timeout caused by a peer that stays connected but silent.

### 5.3. Full Protocol Compliance Is Outside the Demo Parser Scope

A complete raw HTTP request needs a request line, headers, and a blank line CRLFCRLF; if it has a body, it needs valid HTTP framing. The examples below **intentionally check only the header boundary** or **use a custom length-prefixed protocol**. Do not treat a few-dozen-line parser as a complete HTTP server.

## 6. Demo #1 — Sending HTTP Headers Fast, Silent, Trickled, and Oversized

### 6.1. Test Cases in the Program

The demo sets up four independent tests, each with a temporary loopback `ServerSocket` port and **one client**:

| Case | Client behavior | Server mechanism under test | Expected outcome |
| --- | --- | --- | --- |
| `FAST` | Sends complete HTTP headers immediately | Receives CRLFCRLF under limits | `200 COMPLETE` |
| `IDLE` | Sends `GET /` then pauses 350 ms | Idle limit 250 ms | `408 IDLE_TIMEOUT` |
| `TRICKLE` | Sends 1 byte every 90 ms, never finishes headers | Idle gap <250 ms but total exceeds 650 ms | `408 TOTAL_TIMEOUT` |
| `OVERSIZE` | Sends 64 header bytes with no CRLFCRLF | Header limit 64 bytes | `431 HEADER_LIMIT` |

The test server only reads bytes up to the CRLFCRLF marker; it **does not parse the method, Host, Content-Length, chunked body, or multiple requests**. It returns a minimal HTTP/1.1 response with `Connection: close` and `Content-Length: 0` so the client can read the status line. Codes 408 and 431 illustrate a **policy test**; a production server might choose to close the connection on incomplete input, or even emit no response if the socket is already broken.

### 6.2. Complete File `SlowHeaderClientLab.java`

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class SlowHeaderClientLab {
    static final int IDLE_MS = 250;
    static final int TOTAL_MS = 650;
    static final int MAX_HEADER_BYTES = 64;
    enum Trial { FAST, IDLE, TRICKLE, OVERSIZE }

    static String respond(Socket peer, int status, String label) throws IOException {
        OutputStream out = peer.getOutputStream();
        String response = "HTTP/1.1 " + status + " " +
                (status == 200 ? "OK" : status == 408 ? "Request Timeout" :
                 status == 431 ? "Request Header Fields Too Large" : "Bad Request") +
                "\r\nConnection: close\r\nContent-Length: 0\r\n\r\n";
        out.write(response.getBytes(StandardCharsets.US_ASCII));
        out.flush();
        return label;
    }

    static String serveOne(ServerSocket server) throws IOException {
        try (Socket peer = server.accept()) {
            InputStream in = peer.getInputStream();
            long deadline = System.nanoTime() +
                    TimeUnit.MILLISECONDS.toNanos(TOTAL_MS);
            int state = 0, count = 0;
            while (true) {
                long remainingNs = deadline - System.nanoTime();
                if (remainingNs <= 0) return respond(peer, 408, "TOTAL_TIMEOUT");
                int untilTotalMs = (int)Math.max(1,
                        TimeUnit.NANOSECONDS.toMillis(remainingNs));
                peer.setSoTimeout(Math.min(IDLE_MS, untilTotalMs));
                int b;
                try {
                    b = in.read();
                } catch (SocketTimeoutException timeout) {
                    return respond(peer, 408,
                            System.nanoTime() >= deadline ?
                            "TOTAL_TIMEOUT" : "IDLE_TIMEOUT");
                }
                if (b == -1) return respond(peer, 400, "INCOMPLETE");
                count++;
                state = switch (state) {
                    case 0 -> b == '\r' ? 1 : 0;
                    case 1 -> b == '\n' ? 2 : b == '\r' ? 1 : 0;
                    case 2 -> b == '\r' ? 3 : 0;
                    default -> b == '\n' ? 4 : b == '\r' ? 1 : 0;
                };
                if (state == 4) return respond(peer, 200, "COMPLETE");
                if (count >= MAX_HEADER_BYTES) {
                    return respond(peer, 431, "HEADER_LIMIT");
                }
            }
        }
    }

    static void run(Trial trial, ExecutorService worker) throws Exception {
        try (ServerSocket server = new ServerSocket(0, 1,
                InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(5000);
            Future<String> outcome = worker.submit(() -> serveOne(server));
            try (Socket client = new Socket("127.0.0.1",
                    server.getLocalPort())) {
                client.setSoTimeout(3000);
                OutputStream out = client.getOutputStream();
                switch (trial) {
                    case FAST -> out.write(
                            "GET /ok HTTP/1.1\r\nHost: localhost\r\n\r\n"
                                    .getBytes(StandardCharsets.US_ASCII));
                    case IDLE -> {
                        out.write("GET /".getBytes(StandardCharsets.US_ASCII));
                        out.flush();
                        Thread.sleep(IDLE_MS + 100);
                    }
                    case TRICKLE -> {
                        byte[] prefix = "GET / H".getBytes(StandardCharsets.US_ASCII);
                        for (int i = 0; i < prefix.length; i++) {
                            out.write(prefix[i]);
                            out.flush();
                            if (i + 1 < prefix.length) Thread.sleep(90);
                        }
                    }
                    case OVERSIZE -> {
                        out.write("A".repeat(MAX_HEADER_BYTES)
                                .getBytes(StandardCharsets.US_ASCII));
                    }
                }
                out.flush();
                String status = new BufferedReader(
                        new InputStreamReader(client.getInputStream(),
                                StandardCharsets.US_ASCII)).readLine();
                System.out.println(trial + ": " + status + " | " +
                        outcome.get(3, TimeUnit.SECONDS));
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            for (Trial trial : Trial.values()) run(trial, worker);
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 SlowHeaderClientLab.java
java SlowHeaderClientLab
~~~

**Verified stdout when run on JDK 24 with `javac --release 17`:**

~~~text
FAST: HTTP/1.1 200 OK | COMPLETE
IDLE: HTTP/1.1 408 Request Timeout | IDLE_TIMEOUT
TRICKLE: HTTP/1.1 408 Request Timeout | TOTAL_TIMEOUT
OVERSIZE: HTTP/1.1 431 Request Header Fields Too Large | HEADER_LIMIT
~~~

This is actual execution output. Timers depend on the OS, scheduler, GC, and machine load; in a very busy environment, **individual byte arrival times can drift**, so short timing tests may vary. Increase margins when writing CI tests and prefer simulated clocks for state machines; do not treat 250/650 ms as production defaults.

### 6.3. Analyzing the `FAST` Line

- The client sends `GET /ok HTTP/1.1\r\nHost: localhost\r\n\r\n` with a complete header terminator.
- The server reads byte-by-byte and updates the 4-state matcher for `\r\n\r\n`.
- It returns `200 OK` and the test label `COMPLETE`.
- There is no handler for `/ok` or application logic: this is a **header-boundary test**, and 200 is just a simulated outcome.

### 6.4. Analyzing the `IDLE` Line

- The client sends a partial `GET /`, without CRLFCRLF.
- Then it sends no new bytes for longer than `IDLE_MS=250` ms while **keeping the TCP socket open**.
- `InputStream.read()` in the server has `Socket.setSoTimeout(250)` set, so it throws `SocketTimeoutException`.
- The server sends 408 and the label `IDLE_TIMEOUT`, then try-with-resources closes the accepted socket.

This differs from a client closing immediately after sending a few bytes: when the client closes TCP cleanly, the server normally sees **EOF -1** or an error, not a socket idle timeout.

### 6.5. Analyzing the `TRICKLE` Line

- The client sends 7 bytes of `GET / H`, spaced 90 ms apart.
- The gap between bytes is smaller than the 250 ms idle timeout.
- The server still tracks the 650 ms absolute deadline from when it started receiving headers.
- After the last byte arrives, the server waits for the next byte, but the remaining time until the total deadline is shorter than the idle timeout. When the total time expires, the server returns 408 and the label `TOTAL_TIMEOUT`.

**If the server only had `setSoTimeout(250)` without a total deadline**, a client could send a byte before every 250 ms mark and hold the connection for a very long time. This is why this test matters.

### 6.6. Analyzing the `OVERSIZE` Line

- The client sends exactly 64 `A` characters without a header terminator.
- The server increments `count` for each byte and rejects once `count >= MAX_HEADER_BYTES`.
- It does not read indefinitely, does not build a huge `StringBuilder`, and does not wait forever for more bytes.
- The test response is 431 `Request Header Fields Too Large`.

In production, the header budget typically covers the request line + header fields, field count, encoded byte count, and parser semantics. The example does not perform full HTTP/1.1 validation — so returning status 431 is a **lab policy outcome**, not a promise that every JDK server will return 431 in the exact same way.

### 6.7. Role of the Two Timeout Types in Code

~~~java
server.setSoTimeout(5000); // Only affects ServerSocket.accept().

// After accept:
peer.setSoTimeout(250);    // Affects blocking reads on the Socket InputStream.
~~~

The two lines above are a **code snippet** and do not run standalone. `ServerSocket` and `Socket` are two different objects:

- `ServerSocket.setSoTimeout`: `accept()` waits at most the configured duration; if no new connection arrives, it throws `SocketTimeoutException` while the listener remains valid.
- `Socket.setSoTimeout`: blocking `InputStream.read()` on the accepted socket waits at most the configured duration; on timeout, the socket is **not automatically closed**.
- Neither **automatically sets a write timeout** for `OutputStream.write(...)`.
- `setSoTimeout(0)` means wait indefinitely for the corresponding operation; the lab always picks finite values.
- Do not mistake a 250 ms timeout on a single `read()` for a 250 ms total request budget.

## 7. From Timeouts to Resource Limits: Every Accepted Connection Has a Cost

As soon as `ServerSocket.accept()` succeeds, the server may have to hold:

- A file descriptor/socket.
- Input/output buffers and transport state.
- A task/thread/continuation handling the request.
- Memory to parse the request headers/body.
- Request context objects, authentication state, timers, and logs.
- A connection pool/quota entry for the user or IP.
- Possibly TLS state and handshake buffers if HTTPS is used.

A slow client can hold resources **before the business handler is ever invoked**. For example, an HTTP parser usually has to receive the full request line and headers before creating a request object; if you only limit handler concurrency, incomplete requests can still hold connection state at the listener/parser layer.

**Therefore you need both pre-handler protection** (connection cap, header deadline, header count/bytes, TLS handshake deadline, idle keep-alive) and handler protection (body size/time, bounded executor queue, app concurrency cap, downstream deadlines).

### 7.1. Admission Control Diagram

~~~text
TCP accept
    |
    v
connection admission: global/per-client cap
    |
    +----> full? reject/close early
    |
    v
TLS/HTTP header parsing with own deadlines and byte caps
    |
    v
handler/work queue admission
    |
    +----> full? 429/503/close per contract
    |
    v
body streaming with deadline + size cap
    |
    v
business processing with timeout/quotas
    |
    v
response write / cleanup
~~~

Limiting the **server backlog** is not the same as limiting active handlers. The `ServerSocket` backlog parameter is a hint for the OS/transport accept queue, not a substitute for a `Semaphore` or application quota.

## 8. Demo #2 — Sending a Partial Body, Occupying a Slot, and Proving Cleanup

This demo uses **a small custom binary protocol**, **not HTTP**. Its frame format is:

~~~text
+--------------------------------+--------------------------+
| 4-byte signed int length       | body bytes (length N)    |
+--------------------------------+--------------------------+
  DataOutputStream.writeInt         N bytes
~~~

The server has:

- **BODY_LIMIT=16 bytes**: checks length before `readNBytes(length)`, avoiding unbounded size allocation.
- **IDLE_MS=300 ms**: read timeout set on the accepted socket.
- **Semaphore(1)**: at most one request/frame being processed at a time.
- A fixed `ExecutorService` and a dedicated acceptor thread; no unbounded worker-per-connection spawning.
- `CountDownLatch` so test ordering **does not depend on thread scheduling luck**.

Four intentional sequential/interacting connections:

1. A slow client sends `length=8`, sends only 2 bytes `AB`, and stops: **holds one slot** while the server waits for the remaining body bytes.
2. A second client connects while the slot is still held: the server **immediately rejects it with `BUSY`**.
3. After the slow client hits the read timeout and the slot is released, a new client declares `length=99`: the server checks that 99 exceeds BODY_LIMIT=16 and returns **`TOO_LARGE`** before allocating.
4. A valid client then sends `length=4` + `PING`: the server replies **`OK:PING`**. After completion, the semaphore has **1 permit** again.

### 8.1. Complete File `SlowBodyCapacityLab.java`

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class SlowBodyCapacityLab {
    static final int BODY_LIMIT = 16;
    static final int IDLE_MS = 300;

    static void sendLine(Socket peer, String message) throws IOException {
        OutputStream out = peer.getOutputStream();
        out.write((message + "\n").getBytes(StandardCharsets.US_ASCII));
        out.flush();
    }

    static String receiveLine(Socket peer) throws IOException {
        return new BufferedReader(new InputStreamReader(
                peer.getInputStream(), StandardCharsets.US_ASCII)).readLine();
    }

    static void process(Socket peer) throws IOException {
        try (peer) {
            peer.setSoTimeout(IDLE_MS);
            DataInputStream input = new DataInputStream(peer.getInputStream());
            try {
                int length = input.readInt();
                if (length < 0 || length > BODY_LIMIT) {
                    sendLine(peer, "TOO_LARGE");
                    return;
                }
                byte[] body = input.readNBytes(length);
                if (body.length != length) {
                    sendLine(peer, "TRUNCATED");
                    return;
                }
                sendLine(peer, "OK:" +
                        new String(body, StandardCharsets.US_ASCII));
            } catch (SocketTimeoutException timeout) {
                sendLine(peer, "IDLE_TIMEOUT");
            }
        }
    }

    static void serve(ServerSocket server, ExecutorService handlers,
                      Semaphore slots,
                      CountDownLatch firstSlot,
                      CountDownLatch firstDone,
                      CountDownLatch oversizedDone,
                      CountDownLatch finalDone) throws IOException {
        AtomicInteger handled = new AtomicInteger();
        for (int n = 0; n < 4; n++) {
            Socket peer = server.accept();
            if (!slots.tryAcquire()) {
                try (peer) {
                    sendLine(peer, "BUSY");
                }
                continue;
            }
            int id = handled.incrementAndGet();
            if (id == 1) firstSlot.countDown();
            handlers.execute(() -> {
                try {
                    process(peer);
                } catch (IOException error) {
                    System.err.println("Peer I/O error: " +
                            error.getClass().getSimpleName());
                } finally {
                    slots.release();
                    if (id == 1) firstDone.countDown();
                    if (id == 2) oversizedDone.countDown();
                    if (id == 3) finalDone.countDown();
                }
            });
        }
    }

    static Socket connect(int port) throws IOException {
        Socket peer = new Socket("127.0.0.1", port);
        peer.setSoTimeout(3000);
        return peer;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService acceptor = Executors.newSingleThreadExecutor();
        ExecutorService handlers = Executors.newFixedThreadPool(2);
        Semaphore slots = new Semaphore(1);
        CountDownLatch firstSlot = new CountDownLatch(1);
        CountDownLatch firstDone = new CountDownLatch(1);
        CountDownLatch oversizedDone = new CountDownLatch(1);
        CountDownLatch finalDone = new CountDownLatch(1);
        try (ServerSocket server = new ServerSocket(
                0, 4, InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(5000);
            Future<?> serving = acceptor.submit(() -> {
                serve(server, handlers, slots,
                        firstSlot, firstDone, oversizedDone, finalDone);
                return null;
            });
            int port = server.getLocalPort();

            try (Socket slow = connect(port)) {
                DataOutputStream output =
                        new DataOutputStream(slow.getOutputStream());
                output.writeInt(8);
                output.write("AB".getBytes(StandardCharsets.US_ASCII));
                output.flush();
                if (!firstSlot.await(3, TimeUnit.SECONDS))
                    throw new IllegalStateException("First slot not acquired");

                try (Socket extra = connect(port)) {
                    System.out.println("Concurrent extra: " +
                            receiveLine(extra));
                }
                System.out.println("Slow body: " + receiveLine(slow));
            }
            if (!firstDone.await(3, TimeUnit.SECONDS))
                throw new IllegalStateException("Slot not released");

            try (Socket tooLarge = connect(port)) {
                new DataOutputStream(tooLarge.getOutputStream()).writeInt(99);
                System.out.println("Oversize body: " +
                        receiveLine(tooLarge));
            }
            if (!oversizedDone.await(3, TimeUnit.SECONDS))
                throw new IllegalStateException("Oversize slot not released");

            try (Socket healthy = connect(port)) {
                DataOutputStream out =
                        new DataOutputStream(healthy.getOutputStream());
                out.writeInt(4);
                out.write("PING".getBytes(StandardCharsets.US_ASCII));
                System.out.println("Recovered slot: " +
                        receiveLine(healthy));
            }
            if (!finalDone.await(3, TimeUnit.SECONDS))
                throw new IllegalStateException("Final slot not released");
            serving.get(3, TimeUnit.SECONDS);
            System.out.println("Active slots after requests: " +
                    slots.availablePermits());
        } finally {
            acceptor.shutdownNow();
            handlers.shutdownNow();
        }
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 SlowBodyCapacityLab.java
java SlowBodyCapacityLab
~~~

**Verified stdout with `--release 17`:**

~~~text
Concurrent extra: BUSY
Slow body: IDLE_TIMEOUT
Oversize body: TOO_LARGE
Recovered slot: OK:PING
Active slots after requests: 1
~~~

### 8.2. Why `Concurrent extra: BUSY`?

- The slow client connected and the acceptor succeeded in `slots.tryAcquire()`.
- `firstSlot.countDown()` signaled `main` that the permit was held.
- `main` **did not close the slow client** and proceeded to create the second client.
- The acceptor accepted the second connection, but `tryAcquire() == false`, so it sent `BUSY` and closed the socket.
- No new thread processed the second client's body; it was never submitted to `handlers.execute(...)`.

This illustrates **active-handler admission**. In a real HTTP system, the overload response might be 503, 429, or an immediate close depending on the contract, whereas **`BUSY` here is a text line in the lab protocol**, not an HTTP status.

### 8.3. Why `Slow body: IDLE_TIMEOUT`?

- The first client declared body length 8 but only sent `AB` (2 bytes).
- The server read the 4-byte prefix, verified length <=16, and called `readNBytes(8)`.
- With no more bytes arriving for `IDLE_MS=300`, the blocking read threw `SocketTimeoutException`.
- The code replied `IDLE_TIMEOUT` and try-with-resources closed the accepted socket.
- `finally` called `slots.release()` and then signaled `firstDone`.

If the peer actively closes the connection before sending all 8 bytes, `readNBytes(8)` can return **fewer than 8** bytes and the code replies `TRUNCATED`; do not confuse EOF with a timeout.

### 8.4. Why `Oversize body: TOO_LARGE`?

- The client declared length 99 in the 4-byte prefix and **sent no body**.
- The server compared `length > BODY_LIMIT=16` before calling `readNBytes(length)`.
- It rejected immediately with `TOO_LARGE` and closed the socket, without allocating a 99-byte buffer on trust.

In real HTTP, `Content-Length` can be absent, spoofed, oversized, or replaced by chunked framing. You should check **actual bytes received** and enforce limits after decompression when compression is used; checking only a client-declared number is not enough.

### 8.5. Why `Recovered slot: OK:PING`?

- The third client after the slow client timed out still ran normally; it was rejected for body length 99, but the slot was released.
- The fourth client declared a 4-byte body and sent exactly `PING`.
- Because the server had a free permit, it processed the frame and replied `OK:PING`.
- `finalDone` waited until the task had executed `slots.release()`; at the end of the program it printed `Active slots after requests: 1`.

What matters is not only that the server knows how to **reject** bad requests, but also that it **recovers capacity and keeps serving good requests**. If a timeout branch forgets to release the permit or close the socket, subsequent healthy requests could see `BUSY` forever.

### 8.6. Limitations of the Lab Protocol

The code intentionally does not implement HTTP/TLS, authentication, global memory accounting, fair queues, or pressure under very large connection counts. It only handles 4 accepted sockets to demonstrate the mechanism. In particular, because the permit is acquired in the **acceptor before dispatch**, the handler pool's worker queue does not build a backlog for rejected connections in this example. Production code still needs to handle **executor rejection** (for example `RejectedExecutionException` on shutdown or a full bounded queue), closing the socket and releasing the permit exactly once. Do not copy this fixture as an Internet-facing server.

## 9. Timeout Layers in Java 17

### 9.1. `ServerSocket.setSoTimeout`: Waiting for New Connections

~~~java
try (ServerSocket listener =
             new ServerSocket(0, 16, InetAddress.getByName("127.0.0.1"))) {
    listener.setSoTimeout(2000);
    Socket accepted = listener.accept(); // May throw SocketTimeoutException.
}
~~~

This is a **code snippet** (importing `ServerSocket`, `Socket`, `InetAddress`); it does not clean up `accepted` if `accept()` succeeds, so real code must close that socket. `setSoTimeout(2000)` applies **only to `accept()`**, not to reading the body after accept.

### 9.2. `Socket.setSoTimeout`: Waiting for Data on an Accepted Socket

~~~java
Socket accepted = listener.accept();
accepted.setSoTimeout(2000);
int nextByte = accepted.getInputStream().read();
~~~

Code snippet. `SocketTimeoutException` is thrown if the blocking `read()` receives no data within the wait interval, while the socket remains valid per the API. Applications typically choose to return an error or close because the request is not progressing, but closing is **your policy**, not an automatic effect of `setSoTimeout`.

### 9.3. Total Deadline Using Monotonic Time

~~~java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
while (!requestComplete) {
    long remaining = deadline - System.nanoTime();
    if (remaining <= 0) {
        // total timeout: stop receiving request and clean up.
        break;
    }
    socket.setSoTimeout((int)Math.max(1, Math.min(2000,
            TimeUnit.NANOSECONDS.toMillis(remaining))));
    // InputStream.read(); update progress/byte budget.
}
~~~

This is a **code snippet** with `socket` and `requestComplete` defined by the application. For large deadlines, avoid long→int cast overflow; clamp/cap as shown in the example. `System.nanoTime()` is not epoch time; use it only to measure durations/differences.

In Program #1, a 650 ms deadline was chosen for the test; in production you must account for legitimate devices and network latency — for example, a large file upload cannot share the same short total deadline as a bodyless GET request.

### 9.4. Distinguishing Timeouts from EOF and IOException

| Observation | Basic meaning |
| --- | --- |
| `InputStream.read() == -1` | Peer sent EOF for the read direction, not necessarily a timeout |
| `SocketTimeoutException` | Blocking read call exceeded `SO_TIMEOUT` |
| `SocketException: Connection reset` | Transport was reset/closed abnormally |
| `EOFException` from `DataInputStream.readInt()` | Not enough bytes for the 4-byte prefix |
| `Future.get(timeout)` timeout | Task did not finish before caller's deadline; **does not cancel the task** |
| `ServerSocket.accept()` timeout | No connection accepted before `SO_TIMEOUT` |
| `SocketChannel.read` returns `0` in nonblocking mode | No bytes available right now; **not** EOF or socket timeout |
| App total deadline exceeded | Application-enforced policy across the entire phase |

**Timeouts do not always share the same HTTP status.** When a connection has only sent a few bytes, the parser may not even have a valid request to respond to; closing the socket is sometimes the right choice. Once the application has a request context and a writable output channel, it can return 408/413/431/503 according to convention.

## 10. JDK `HttpServer` and Related Properties

If a system uses `com.sun.net.httpserver.HttpServer`, the handler is typically invoked **only after the HTTP headers have been parsed by the server**. A client sending headers very slowly can occupy resources **before `HttpHandler.handle(exchange)` runs**, so limits inside the handler alone are insufficient.

Oracle's **Java SE 17 — Java Networking** documentation includes an **HTTP Server Properties** section for the default implementation in the `jdk.httpserver` module:

| Property (JDK-specific) | Purpose | Points to note |
| --- | --- | --- |
| `jdk.httpserver.maxConnections` | Limits open connections (both active and idle) | Not the same as handler concurrency |
| `sun.net.httpserver.maxReqHeaders` | Limits number of request header fields | Server may terminate request if exceeded |
| `sun.net.httpserver.maxReqHeaderSize` | Limits size of request header section | Not the same as body size |
| `sun.net.httpserver.maxReqTime` | Time allowed to receive request headers and body | Java 17 docs describe value in **milliseconds** with implementation-specific granularity |
| `sun.net.httpserver.maxRspTime` | Limits time to send response | Partially protects against slow receivers/output |
| `sun.net.httpserver.idleInterval` | Limits how long an idle connection is kept | Different from total request deadline |
| `sun.net.httpserver.maxIdleConnections` | Number of idle connections retained | Does not replace active connection limit |
| `sun.net.httpserver.drainAmount` | Unread request body bytes drained to reuse connection | Early close can affect keep-alive |

**Important:** the properties above are **JDK implementation details**, and not every HTTP framework or Java vendor interprets them identically. Default values and exact behavior should be verified against the exact **JDK 17 update/runtime in use**. When testing, use a **separate process** or pass JVM options at startup rather than mutating global properties mid-flight across requests.

Illustrative configuration example (not a command for the raw TCP labs above):

~~~bash
java -Dsun.net.httpserver.maxReqTime=5000 -Dsun.net.httpserver.maxReqHeaderSize=8192 -Djdk.httpserver.maxConnections=100 -cp app.jar Main
~~~

**This is an illustrative JVM flags example with placeholder jar/class names** and cannot run without `app.jar` and `Main`. The number `5000` means 5 seconds per the property documentation (not 5000 seconds). Do not assume `HttpServer` will return **408**; the docs describe **terminating the connection** or the handler receiving an `IOException` depending on the phase. Whether a property takes effect must be verified with real slow tests and metrics.

### 10.1. Why Are Limits Still Needed Inside the Handler?

HTTP parser/header limits do not block:

- Very large bodies on an upload endpoint if the application reads them without a quota.
- JSON/XML parsers with nesting/CPU amplification.
- Business handlers waiting a long time on a database.
- Large decompressed bodies even when raw compressed bytes are small.
- Too many concurrent calls to a downstream dependency.
- Unbounded asynchronous task queues after headers are parsed.

Conversely, handler-level body checks **do not** protect the stage **before the handler is dispatched**. A sound design applies multiple layers of limits matching each layer's responsibility.

## 11. Active Connection Cap and Executor Queue

A server might use:

~~~java
Semaphore slots = new Semaphore(64);
if (!slots.tryAcquire()) {
    // Do not place the socket into an unbounded queue.
    // Reject/close early according to protocol.
    return;
}
try {
    // Process connection/request while holding the slot.
} finally {
    slots.release();
}
~~~

This is a **code snippet** that must be synchronized with the accepted socket's lifecycle. If a slot was acquired but `ExecutorService.execute(...)` throws `RejectedExecutionException`, the code must close the socket and release the slot; **never** let a permit leak.

### 11.1. A Bounded Worker Pool Alone Is Not Enough

`Executors.newFixedThreadPool(n)` uses `n` threads, but its default internal task queue may have **no practical bound**. If the acceptor keeps submitting tasks for slow clients, pending tasks can grow sharply even though `n` workers are fixed.

Production systems should apply:

- Connection admission before enqueuing, or a `ThreadPoolExecutor` with a **bounded `BlockingQueue`**.
- An explicit rejection handler: close/503/429 depending on protocol and state.
- Pool sizing grounded in the blocking workload, not scaled arbitrarily with client count.
- Per-IP/per-tenant quotas where appropriate, not just a global cap.
- Global file descriptor/socket budgets and TLS handshake caps.
- Graceful shutdown: stop accepting → stop queued tasks → close/drain active sockets → release permits.

### 11.2. A Semaphore Does Not Bound Resources Before `accept`

An accepted TCP socket already incurs kernel/FD cost **before the application acquires a slot**. If too many connections are pending, enforcement is needed at the **listener/OS/proxy/TLS/gateway** layer, not just via a semaphore in handler code. In our demos, each test has at most two concurrent connections, so we do not test real exhaustion.

## 12. Header Timeout Does Not Replace Body Timeout

An HTTP client can finish headers immediately:

~~~http
POST /upload HTTP/1.1
Host: localhost
Content-Length: 100000

~~~

and then send the body very slowly. The header total deadline has been satisfied, yet the server is still at risk of holding the request body stream open for a long time. Design body timeouts around:

1. **Maximum body bytes**: do not allocate based on client-supplied length without validation; count actual bytes.
2. **Idle gap**: if no new bytes arrive within an interval, cancel the upload.
3. **Total upload deadline**: calculated reasonably from size, minimum bandwidth, and policy.
4. **Minimum sustained data rate**: measure over a window long enough to tolerate bursts/jitter, without penalizing a brief legitimate pause.
5. **Downstream deadlines**: database/disk processing can stall independently of the network.
6. **Cleanup**: delete incomplete temporary files and release file descriptors and request slots when an upload fails.

### 12.1. Bounded Read Pattern

~~~java
int maxBody = 1024 * 1024;
byte[] data = requestInput.readNBytes(maxBody + 1);
if (data.length > maxBody) {
    // Over limit: reject/close per HTTP protocol and policy.
}
~~~

This is a code snippet with `requestInput` undeclared. `readNBytes` bounds the bytes read into RAM in this operation, **not** the total read deadline; waiting for data can still block on `InputStream`. For large uploads, stream into a sink with quotas and cleanup rather than buffering everything on the heap.

### 12.2. Received Bytes Must Be Observed Directly

Clients can:

- Declare an incorrect or missing `Content-Length`.
- Use chunked transfer encoding.
- Send a partial body and then send EOF.
- Send a compressed payload whose decoded size is huge.
- Send bytes fast initially and then stop completely.
- Send just enough per burst to stay under the idle timeout while dragging the total request out unreasonably.

Do not test only the “fast complete body” case. Combine **incomplete**, **oversized**, **trickle**, **abrupt close**, and **a valid request immediately after failure cases**.

## 13. Why Not Just Increase the Thread Pool and Timeouts?

A common mistaken fix:

~~~text
Currently 100 slow clients, 100 threads blocked.
→ Increase pool from 100 to 1000 threads.
→ Each thread adds stack/CPU overhead.
→ A single surge of 1000 slow clients exhausts it again.
~~~

Increasing capacity can help if legitimate workload demands higher concurrency, but it does not replace **maximum time a resource may be held**, **admission policy**, **byte quotas**, or **bounded queues**. A system needs defined **SLOs** (e.g., headers must finish within X seconds for most clients) and p95/p99 observations before setting limits.

### 13.1. Fair Limits for Clients on Weak Networks

An overly short absolute deadline can reject legitimate users on mobile networks. Therefore:

- Choose deadlines per endpoint: a lightweight GET differs from a file upload.
- Provide resumable uploads / chunked resumable protocols when files are large and networks are flaky.
- Enforce a body rate floor over a reasonable window; do not penalize a single jitter spike.
- Use a shorter early header deadline than the total body deadline where appropriate.
- Prefer 429/503 with `Retry-After` per contract when the server is overloaded, rather than masquerading as a request timeout.
- Do not force users to retry commands with side effects unless an idempotency key is present.
- Use a gateway/reverse proxy to handle connection admission and legitimate TLS policies.

## 14. Verify Through Metrics, Not Just Error Messages

| Metric | What does it measure? | Expectation during slow tests |
| --- | --- | --- |
| `accepted_connections_total` | Number of accepted TCP sockets | Increments across the 4 test cases |
| `active_connections` | Unclosed connections | Returns to baseline after test |
| `active_handlers` | Tasks holding a processing slot | Never exceeds cap |
| `handler_queue_depth` | Tasks waiting for executor | Does not grow unbounded |
| `request_header_bytes` | Header bytes read | Does not exceed max header budget |
| `request_body_bytes` | Body bytes read | Max enforced |
| `request_header_duration_ms` | Header parsing duration | Trickle approaches total deadline |
| `request_body_duration_ms` | Body reading duration | Slow-body timeout |
| `idle_read_timeout_total` | Read gap timeouts | Increments on IDLE case |
| `request_total_timeout_total` | Absolute request deadlines | Increments on TRICKLE case |
| `header_limit_rejected_total` | Oversized headers | Increments on OVERSIZE case |
| `body_limit_rejected_total` | Declared/actual oversized bodies | Increments on size 99 case |
| `capacity_rejected_total` | Failed permit acquisitions | Increments when slot is busy |
| `resource_release_failures` | Detected permit/FD leaks | **0** |
| `connection_close_reason` | Close/cancel reason | Distinguishes timeout/EOF/size/policy |

Do not use raw credentials, API keys, full URL queries, or request bodies as log/metric labels. You can safely log **case ID/test run ID**, reason, and aggregate dimensions. In the small test server, labels like `IDLE_TIMEOUT`/`TOTAL_TIMEOUT` are far more informative than merely logging a generic `IOException`.

### 14.1. Analyzing Outcomes by Phase

~~~text
Did the client connect?
    |
    +-- No: DNS/connect/refused; HTTP timeout not yet tested.
    |
    +-- Yes, did the server receive complete request headers?
            |
            +-- No:
            |      +-- idle gap timeout? -> IDLE
            |      +-- absolute age over? -> TOTAL
            |      +-- header bytes > cap? -> HEADER_LIMIT
            |
            +-- Yes: is the body complete?
                   |
                   +-- No:
                   |      +-- body read timeout
                   |      +-- body size/quota reject
                   |      +-- EOF/incomplete
                   |
                   +-- Yes: did a handler have a slot and finish on time?
                          |
                          +-- Busy -> 429/503/close per policy
                          +-- Completed -> normal response
~~~

**An HTTP 408 status alone does not identify the root cause.** Distinguishing an idle-gap timeout from an overall deadline requires phase metrics or server logs; some stacks will close the socket without sending a status.

## 15. How Should Real-World Testing Be Planned?

| Test | Client sends | Mechanism verified | What to measure |
| --- | --- | --- | --- |
| Fast baseline | Complete headers/body immediately | No false rejections | 200/normal response |
| Header idle | `GET /` then pauses | `Socket.setSoTimeout` | Idle counter, close |
| Header trickle | One byte per interval < idle cap | Total deadline | Total timeout, not held forever |
| Header oversize | Max +1 byte without ending headers | Header byte cap | Reject/close, no buffer growth |
| Many header fields | N fields exceeding configured cap | Header count limit | No parser blowup |
| Header complete/body absent | Content-Length >0 with no body sent | Body idle timeout | Cleanup, no stuck worker |
| Body trickle | Body in tiny byte chunks | Body total/min-rate | Deadline/limited throughput |
| Oversized declared body | Length prefix/Content-Length >limit | Early size rejection | No huge allocation |
| Actual bytes exceed limit | Missing/false declared length or streaming | Byte counting | Actual received cap |
| Incomplete frame EOF | Closes output early | Distinguish EOF/timeout | TRUNCATED/400 |
| Active cap reached | Second connection while first holds slot | Semaphore/admission | BUSY/503/close, no leaked slot |
| Valid after timeout | Valid request retried after cleanup | Capacity restored | Success |
| Slow response reader | Client does not read response | Write timeout/buffers | Not confused with slow sender |
| TLS slow handshake | Client sends TLS ClientHello slowly | Handshake deadline | Connection not held forever |
| HTTP/2 stream stall | One stream sends body slowly | Stream flow control/deadline | Does not stall all streams |
| Graceful stop during slow request | Stop server | Shutdown/cancel | No leaked threads/sockets |
| Deadline under CPU load | Server hits GC/scheduler pause | False positives | Choose sensible guardrails |

**You do not need thousands of slow clients** to prove policy logic. Both demos use just a few sockets and deterministic synchronization; load tests with many connections should only be run in authorized staging environments with resource budgets and rollback capability.

## 16. Common Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Only setting `setSoTimeout` for reads | Trickle bytes can reset the idle timer | Total deadline + idle gap |
| Assuming `ServerSocket.setSoTimeout` protects the request body | It only times out `accept()` | Set on accepted `Socket` and app deadline |
| Setting a read timeout and assuming writes also time out | `SO_TIMEOUT` applies to reads, not writes | Separate write timeout/close policy |
| No max header bytes | Tiny slow sends hold parser and memory | Header bytes/count cap |
| Checking `Content-Length` without counting actual body | Chunked/malformed payloads exceed quota | Bounded streaming |
| Allocating an array from client-declared length | Can cause memory exhaustion | Validate length before allocating |
| Timing out without closing the socket | Holds FD/connection state | Try-with-resources/finally |
| Acquiring a semaphore and forgetting to release on exception | Permanent slot leak | Release once in `finally` |
| Limiting only handler threads, leaving accept unbounded | Pre-handler connections hold resources | Listener/TLS/proxy caps |
| Unbounded executor queue | Slow clients generate unbounded pending tasks | Bounded admission/task queue |
| Using `Thread.sleep` in a server handler to “simulate timeout” | Blocks thread without measuring network phase | Deadlines + timed I/O |
| Not handling EOF separately | Equates client close with timeout | Check `read()==-1`/`EOFException` |
| Forcing an HTTP error when no valid request exists yet | Socket may be closed, parser state incomplete | Close when safe response is impossible |
| Assuming every `write(1)` is one TCP packet | TCP is a byte stream; Nagle/OS batching | Measure bytes/timestamps at server |
| Using wall-clock time for deadlines | NTP/time changes | Monotonic elapsed time |
| Scaling demos against unauthorized hosts | Can cause service disruption | Loopback/authorized staging |
| Testing only rejections without testing success afterward | Can hide permit/FD leaks | Valid-after-timeout test |
| Picking a 250 ms timeout for production mobile traffic | High false-positive rate | SLOs, p99, network conditions |
| Growing pool size indefinitely | Underlying resources are still finite | Caps and backpressure policy |
| Reading entire uploads onto the heap | OOM or GC pressure | Streaming quotas and cleanup |
| Omitting `Future.get(timeout)` in integration tests | Tests can hang forever | Bounded waits, cancel/close |
| Assuming `Future.get(timeout)` cancels the task | Task keeps running when `get` times out | Explicit cancel/close by owner |
| Confusing 408 with 503 | Slow client request vs overloaded server | Separate causes by phase |
| Treating a demo header parser as a production HTTP server | Lacks framing/auth/chunking/HTTP semantics | Use a maintained server/framework |
| Logging raw HTTP Authorization/body | Exposes sensitive data | Redaction/aggregate metrics |

## 17. Exercises with Answers

### Exercise 1 — Byte-by-Byte Header

A server sets `Socket.setSoTimeout(250)`, and a client sends 1 byte every 100 ms for 60 seconds. Is the server guaranteed to time out after 250 ms?

**Answer:** No. Because each blocking `read()` receives a new byte before 250 ms elapses, the idle timeout never triggers. You need a **total header deadline**, minimum sustained rate, or a similar aggregate policy.

### Exercise 2 — Accept Timeout

A server listener calls `server.setSoTimeout(1000)` and then accepts a client. Does it automatically wait at most 1 second for the request body?

**Answer:** No. The `ServerSocket.accept()` timeout is separate. You must set a read timeout on the accepted `Socket` and/or an application total deadline.

### Exercise 3 — Why Use `nanoTime`?

**Answer:** `System.nanoTime()` is suited for measuring elapsed durations; `System.currentTimeMillis()` is wall-clock time that can jump due to clock adjustments. Subtract two monotonic timestamps to check deadlines.

### Exercise 4 — Request Without Complete Headers

A client sends `GET /` and waits without closing the connection. After the read timeout, what does the server do?

**Answer:** It may return 408 if output is still safe and server policy supports it, then close; or it may close without sending a response. Catch `SocketTimeoutException`, release resources, and do not hold the request forever.

### Exercise 5 — Reading a Declared 1 GiB Body

A client sends a 1 GiB length prefix to a server with a 16-byte body limit. Should it do `new byte[1_073_741_824]` to read and then check?

**Answer:** No. Check the length before allocating; reject/close immediately. With HTTP streaming, you must also count actual received bytes.

### Exercise 6 — BUSY and Semaphore

Demo #2 holds `Semaphore(1)` in the slow handler when a second client arrives. What is the expected outcome?

**Answer:** `slots.tryAcquire() == false`, the second client receives `BUSY`, and the socket closes; no body-processing task is created for it. In production HTTP, 503/429 or closing may be used per overload policy.

### Exercise 7 — Why Test a Valid Request Afterward?

**Answer:** To prove that after timeouts/rejections, the server does not leak permits, sockets, or workers. Otherwise, a server might appear to reject properly while its capacity silently drains to zero.

### Exercise 8 — Slow Sender or Slow Receiver?

A client sends the request body slowly: is the server held on the read or write path? A client reads the response extremely slowly: where is the server held?

**Answer:** First case: **server read path**. Second case: **server write path**. Separate deadlines and resource accounting are required.

### Exercise 9 — Should You Just Increase `ThreadPoolExecutor` Size?

**Answer:** No. Many slow clients can still occupy all workers and an unbounded task queue. You need admission control, per-connection deadlines, bounded queues, global caps, and cleanup.

### Exercise 10 — Does Trickle Trigger Idle Timeout?

In Demo #1, bytes are spaced 90 ms apart and the idle limit is 250 ms. Why did it still return 408?

**Answer:** Because of the **650 ms total deadline**, not the idle-gap timeout. Headers still lacked CRLFCRLF when the deadline expired.

### Exercise 11 — Header Size vs. Body Size

A request has 30 bytes of headers and a 10 MiB body, with a 64-byte header cap. Does the header cap protect all memory?

**Answer:** No. The body has a separate budget; you must limit actual body bytes, rate/deadline, and streaming memory/disk usage.

### Exercise 12 — Does Socket Timeout Close the Socket Automatically?

After `SocketTimeoutException` from `setSoTimeout`, is the accepted socket automatically closed?

**Answer:** Per the API, the socket can still be valid. The server must decide whether to retry reading or close; the lab chooses to send a timeout response and let try-with-resources close it for cleanup.

### Exercise 13 — Retrying on Upload Timeout

A client sends an upload with side effects and loses the connection partway through. Is it safe to retry immediately?

**Answer:** You cannot assume how much the server already processed. For operations requiring consistency, use idempotency keys, atomic finalize/commit, resumable upload IDs, or job status checks to avoid duplicates.

### Exercise 14 — Why Use Raw Socket Instead of HttpClient?

**Answer:** Raw `Socket` lets you intentionally pause mid-request-line/header and send bytes with exact timing. Normal `HttpClient` abstracts away HTTP formatting, which is great for business APIs but inconvenient for controlled header-level fault injection.

### Exercise 15 — What Production Timeout Value Is Enough?

**Answer:** There is no universal number. It depends on endpoint type, upload size, mobile networks, SLOs, proxy/infra behavior, p95/p99 latency, and acceptable false-positive rates. The few-hundred-ms values in the demos are for local testing only.

## 18. Pre-Completion Lab Checklist

- [ ] Correctly distinguished slow sender vs. slow receiver.
- [ ] Ran experiments only on loopback or authorized staging.
- [ ] Server uses port 0 and finite timeouts to prevent hanging tests.
- [ ] Built a fast-sending baseline client.
- [ ] Built a client that sends a few bytes and pauses without closing immediately.
- [ ] Built a trickle client with inter-byte gaps smaller than the idle timeout.
- [ ] Measured **idle read timeout** and **total header deadline** separately.
- [ ] Checked byte caps before allocating and distinguished header vs. body caps.
- [ ] Verified that `ServerSocket.accept` and accepted `Socket.read` have distinct timeouts.
- [ ] Tested EOF, `SocketTimeoutException`, and `SocketException` as distinct causes.
- [ ] Applied an active handler/connection cap and bounded worker queue policy.
- [ ] Proved that overload rejections do **not** hold new slots.
- [ ] Proved that timeouts/errors **release slots and close sockets**.
- [ ] Sent a valid request after failure cases and observed normal server handling.
- [ ] Measured active_connections, active_handlers, header/body bytes, and reject/timeout totals.
- [ ] Considered legitimate mobile device latency and avoided overly short deadlines.
- [ ] Ensured unit/integration tests use bounded awaits and cleanup in `finally`.
- [ ] Distinguished raw TCP test fixtures from a production HTTP server.
- [ ] Did not use tests to send bulk slow traffic to external services.
- [ ] Compiled both Java programs with `javac --release 17` and verified stdout.

## 19. References

- [Java SE 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): `accept()`, `setSoTimeout` for accept wait, backlog, and lifecycle.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `setSoTimeout` for blocking input reads, socket options, and close.
- [Java SE 17 — SocketTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html): timeout on socket operations.
- [Java SE 17 — DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt()` for length-prefixing.
- [Java SE 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `readNBytes` and EOF handling.
- [Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): active resource permits and release.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): deterministic test synchronization.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): worker ownership and shutdown.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout)` and cancellation.
- [Java SE 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed-time measurement.
- [Oracle Java SE 17 — Java Networking / HTTP Server Properties](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): `sun.net.httpserver.maxReqTime`, max header, max connections, idle interval, and implementation-specific behavior.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): JDK embedded HTTP server, executor/contexts/lifecycle.
- [Java SE 17 — HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): handler dispatched after HTTP parsing.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): request statuses 408/413/431/503 and HTTP semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request line, header section, message framing, and limits.

**Conclusion:** to verify resilience against **slow-sending clients**, do not just configure a single `read timeout`. Build client cases that are **fast, stall mid-request, trickle continuously, and exceed size limits**; clearly observe **idle timeouts, absolute deadlines, header/body byte caps, active handler caps, and cleanup**. The two Java 17 examples demonstrate that a server can **detect prolonged requests**, **reject over-limit requests**, and **recover capacity to serve the next valid request** without generating heavy load or affecting external systems.

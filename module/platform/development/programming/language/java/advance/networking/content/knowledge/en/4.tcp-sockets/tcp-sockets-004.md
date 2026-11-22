# Setting Connect Timeouts with `Socket.connect()` and Read Timeouts with `SO_TIMEOUT`

## 1. Why Are Two Separate Timeouts Needed?

When using TCP with `java.net.Socket`, connecting to a server and waiting for data from the server are **two different operations**. A connection may be established quickly yet the server never responds; conversely, the server may respond well after connecting, but the initial network destination may be unreachable. Therefore, Java provides two primary mechanisms:

- **Connect timeout:** passed to `Socket.connect(SocketAddress endpoint, int timeout)` to limit the wait time for **TCP connection establishment**.
- **Read timeout:** configured via `Socket.setSoTimeout(int timeout)`, corresponding to the **`SO_TIMEOUT`** option, to limit a single blocking read wait on the connected socket's `InputStream`.

Both use **milliseconds (ms)**, but they do not replace each other and do not automatically create a deadline for the entire request.

### 1.1. Timeline Visualization

~~~text
Client                                TCP server
  |                                        |
  |--- connect(endpoint, 2000) ---------->|   Phase A: TCP connection establishment
  |<--- connected -------------------------|
  |                                        |
  |--- write request --------------------->|
  |                                        |   Server is processing...
  |--- read(), SO_TIMEOUT = 3000 -------->|   Phase B: waiting for bytes to read
  |<--- response bytes --------------------|   or read throws SocketTimeoutException
  |                                        |
~~~

The values `2_000` and `3_000` are wait limits for each respective operation. If the connection succeeds in 10 ms, `connect` finishes immediately; it does not try to wait the full 2 seconds. If the other side refuses the connection immediately, an error may occur right away before the connect timeout expires.

### 1.2. Quick Comparison Table

| Criterion | `connect(endpoint, timeout)` | `setSoTimeout(timeout)` |
| --- | --- | --- |
| Purpose | Limits TCP connection wait time | Configures wait time for **each blocking read** |
| When applied | When calling `connect` on an unconnected socket | Once configured, applies to subsequent blocking reads |
| Time value | `int` milliseconds | `int` milliseconds |
| `0` | Does not set a connection time limit via this parameter | Disables read timeout; a read may wait indefinitely |
| On expiration | Typically throws `SocketTimeoutException` at `connect` | `SocketTimeoutException` at `read` |
| On success | Socket is connected and input/output streams can be obtained | `read` returns byte / valid byte count or reports EOF per API |
| Applies to writes? | No | No |
| Limits the entire request? | No | No |

**Key point:** `setSoTimeout(3_000)` does not limit connection time, and `connect(..., 2_000)` does not limit the wait time for a response after the connection succeeds.

## 2. Using `Socket.connect(SocketAddress, int)` Correctly

### 2.1. Creating an Unconnected Socket, Then Connecting with a Timeout

Typical configuration example in Java 17+:

~~~java
import java.net.InetSocketAddress;
import java.net.Socket;

String host = "example.org";
int port = 8080;

try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress(host, port), 2_000);
    socket.setSoTimeout(5_000);

    // Exchange data with the peer only after connect succeeds.
    // Example: socket.getOutputStream().write(...);
    //          socket.getInputStream().read(...);
}
~~~

This is an **illustrative code snippet**, without a complete request/response protocol and without depending on a server returning data. Points to remember:

1. `new Socket()` creates an unconnected socket; you explicitly call `connect(endpoint, connectTimeoutMs)`.
2. `new InetSocketAddress(host, port)` represents the destination IP/host address and port; name resolution may occur before the connect phase.
3. The `2_000` parameter is **2,000 ms = 2 seconds**, dedicated to that `connect` call. Using `0` means waiting for connection without a limit from this timeout; negative values are invalid.
4. Only if the connection succeeds should I/O be performed. `try-with-resources` closes the socket both on success and when an exception occurs.
5. `socket.setSoTimeout(5_000)` is a **separate** setting for subsequent reads. It does not need to be set before `connect` for the connect timeout to take effect.

The shorthand syntax `new Socket(host, port)` can also connect, but it does not let you pass a timeout to that constructor call itself. When you need explicit control over the connect timeout, use `new Socket()` followed by `connect(endpoint, timeout)`.

### 2.2. What Connect Timeout Does Not Guarantee

**Connect timeout is a limit on the connection operation at `connect`**, not a total stopwatch for all work related to a request:

- **DNS:** if using a hostname, name resolution may occur when constructing `InetSocketAddress` (or at another layer) and falls outside the `connect` wait time; this timeout does not inherently bound all of DNS.
- **TLS:** a successful TCP establishment does not mean the TLS handshake is complete. When using TLS/HTTPS, an appropriate timeout policy is needed for the handshake and I/O of that layer.
- **Sending the request, business processing, and receiving the response:** are not bounded by `connect` after the connection succeeds.
- **Application refusing/unreachable destination:** may throw an error early (for example `ConnectException`) without waiting until the timeout mark; this does not mean the timeout configuration is not working.
- **Millisecond precision:** deadlines are enforced by the operating system and scheduler, not a hard real-time guarantee; do not assume measurements will be accurate to a single ms.

**Diagnosing connection failures:** `SocketTimeoutException` during the connect phase indicates waiting too long to connect, whereas `ConnectException` typically indicates a refused or failed connection as reported by the operating system. Address/domain errors, unreachable networks, or firewall policies can also produce other I/O exceptions. Preserve the root cause for diagnostics.

### 2.3. Do Not Confuse "Connected" with "Healthy and Usable"

`socket.isConnected()` indicates that the socket **has once connected successfully**; its value can still be `true` after the socket is closed. Do not use it alone to infer that the peer is active. You can also check `isClosed()`, but even both flags together **cannot confirm** that the server can still process requests; only the application protocol and actual responses prove that.

## 3. Using `Socket.setSoTimeout(int)` Correctly for Blocking Reads

### 3.1. The `SO_TIMEOUT` Mechanism

`setSoTimeout(3_000)` configures the read wait time on the socket, measured in milliseconds. When an `InputStream.read()` operation on the socket **has to wait because no bytes are available**, and exceeds the specified time, that operation throws `java.net.SocketTimeoutException`. According to the `Socket` API, **the socket remains usable** after a read timeout; the application decides whether to continue reading, retry at the protocol level, or close.

Example:

~~~java
socket.setSoTimeout(3_000);
int value = socket.getInputStream().read();
if (value == -1) {
    // Peer ended the sending side (EOF).
} else {
    // Exactly one byte is available; value is in the range 0..255.
}
~~~

The snippet above assumes `socket` is connected and still open. Three outcomes must be distinguished:

- **Data available:** `read()` returns a byte (or a positive byte count for the array-reading overloads). If bytes are already in the buffer, the operation may return immediately.
- **EOF:** `read()` returns `-1` when the other end closes its sending direction normally and the stream has no more bytes.
- **Timeout:** `SocketTimeoutException` means the read operation did not obtain data within the time limit; **it does not mean EOF and does not by itself prove the server is dead**.

`socket.getSoTimeout()` returns the configured number of milliseconds. The default value for this option is typically `0` (infinite wait). `setSoTimeout(0)` disables the read timeout; negative numbers are invalid.

### 3.2. `SO_TIMEOUT` Applies to Each Read Wait, Not the Entire Message

Suppose a protocol requires receiving 1,000 bytes. The client reads in multiple rounds, each with `SO_TIMEOUT = 1_000` ms. If the peer continuously sends a few bytes before each read expires, **the total time to receive all 1,000 bytes can far exceed 1 second**. This is why `SO_TIMEOUT` does not automatically create an overall deadline for a frame or request.

~~~text
Read 1: wait 800 ms -> receive 10 bytes
Read 2: wait 900 ms -> receive 10 bytes
Read 3: wait 950 ms -> receive 10 bytes
...
Each read is still under 1,000 ms; total time accumulates.
~~~

When you need to bound an **entire message**, use a separate deadline with `System.nanoTime()`, compute the remaining time before each read, and update `SO_TIMEOUT` accordingly. Also limit frame size, receive progress, and connection count. With only `SO_TIMEOUT`, a peer trickling data slowly can hold a connection open for a very long time.

### 3.3. Read Timeout Is Not Write Timeout

`SO_TIMEOUT` is used for blocking **reads**. It does not directly bound:

- `socket.connect(...)`: you must use the timeout parameter of `connect`.
- `socket.getOutputStream().write(...)` or `flush()`: when the peer reads slowly or TCP backpressure occurs, write operations can block; `setSoTimeout` does not provide a write timeout.
- The entire connect → request → response cycle.
- A `ServerSocket.accept()` call waiting for a client to connect.

For `ServerSocket`, the `listener.setSoTimeout(ms)` method is a **different option, on the listening socket**, used to limit the wait time of `accept()`. It does not automatically set a read timeout on each `Socket` returned by `accept()`. If needed, set `acceptedSocket.setSoTimeout(ms)` separately.

With non-blocking NIO `SocketChannel`, `Selector`, or asynchronous channels, you must use the deadline/scheduling mechanisms appropriate for those APIs. Do not assume all non-blocking operations behave like `Socket`'s `InputStream.read()`.

## 4. Choosing Timeouts Based on Network Conditions and Business Requirements

There is no single pair of durations that is right for every application. The 2-second connect and 5-second read marks in examples are **illustrative values only**. Consider:

- **Network latency:** a LAN differs from mobile/international networks; TCP connect may fail quickly on one network but have to wait on another.
- **Feature SLA:** interactive user operations need tighter deadlines than long-running background jobs.
- **Normal server processing time:** if a healthy server sometimes takes 4 seconds to respond, a 500 ms read timeout will cause false errors.
- **Data size:** reading one byte differs from receiving a large payload; total time must match throughput/volume and resource limits.
- **Retries:** each attempt may have its own connect timeout and read timeout; the whole retry sequence still needs an overall deadline and backoff/rate limits.

Example internal policy for an operation with a 6-second deadline:

~~~text
Overall deadline = 6,000 ms (measured from request start)
  DNS                -> managed separately if needed
  TCP connect        -> max 1,500 ms
  Send request       -> per its own progress/limits
  Wait for reads     -> each <= remaining deadline time
  Retry if valid     -> only while time budget remains
~~~

This is a **time budget** model, not advice to simply add two timeouts into an overall limit. Deadlines must be computed on the monotonic clock `System.nanoTime()` so they do not depend on system clock adjustments. Connect timeout and read timeout can be adjusted according to the remaining time before each step.

If the server can complete a transaction before responding to the client, a read timeout **does not prove the transaction did not happen**. For operations with side effects, retrying is only safe with an idempotency policy, request IDs, or a reconciliation mechanism.

## 5. Runnable Java 17+ Example: Successful Connect, One Read Timeout, Then Reading Again

The following example creates a **TCP server on loopback**, requiring no Internet, DNS, or external server. The client uses `connect(..., 2_000)` to establish the connection. The server intentionally **sends no bytes yet**; the client sets `SO_TIMEOUT = 200` ms and encounters `SocketTimeoutException` on the first read. After receiving a signal that the client has timed out, the server sends the byte `42`. The client changes `SO_TIMEOUT = 2_000` ms and reads again on the **same socket**, receiving that byte.

`CountDownLatch` is used to coordinate ordering, so the example does not rely on `Thread.sleep()` tricks to simulate a slow network.

Save the following code as **SocketTimeoutDemo.java**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SocketTimeoutDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket(0, 1, loopback)) {
            listener.setSoTimeout(3_000); // Applies only to accept()

            CountDownLatch firstReadTimedOut = new CountDownLatch(1);
            ExecutorService workers = Executors.newSingleThreadExecutor();

            try {
                Future<?> serverTask = workers.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        // Send no bytes yet: force the client to wait in read().
                        if (!firstReadTimedOut.await(3, TimeUnit.SECONDS)) {
                            throw new IllegalStateException(
                                    "Expected timeout was not observed");
                        }

                        peer.getOutputStream().write(42);
                        peer.getOutputStream().flush();
                    } catch (IOException ex) {
                        throw new UncheckedIOException(ex);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "Server was interrupted", ex);
                    }
                });

                try (Socket client = new Socket()) {
                    // Set connect timeout for the TCP handshake phase.
                    client.connect(
                            new InetSocketAddress(
                                    loopback, listener.getLocalPort()),
                            2_000);
                    System.out.println("Connected");

                    // Wait at most 200 ms on this read call.
                    client.setSoTimeout(200);
                    try {
                        int value = client.getInputStream().read();
                        throw new AssertionError(
                                "Expected timeout, got " + value);
                    } catch (SocketTimeoutException expected) {
                        System.out.println("Read timed out");
                    } finally {
                        // After the first read completes, let the server send the byte.
                        firstReadTimedOut.countDown();
                    }

                    // The socket remains usable after SocketTimeoutException.
                    client.setSoTimeout(2_000);
                    System.out.println(
                            "Received: " + client.getInputStream().read());
                }

                // If the server thread fails, Future.get() forwards the error to main.
                serverTask.get(5, TimeUnit.SECONDS);
            } finally {
                firstReadTimedOut.countDown();
                workers.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 SocketTimeoutDemo.java
java SocketTimeoutDemo
~~~

Stdout on a successful run:

~~~text
Connected
Read timed out
Received: 42
~~~

### 5.1. Explaining the Example Timeline

1. `ServerSocket(0, 1, loopback)` creates a listening socket on the loopback address and picks an available port. `listener.setSoTimeout(3_000)` protects only the `listener.accept()` call.
2. The worker calls `accept()` and waits on the latch, so it has **not sent** any bytes to the client yet.
3. The client creates an unconnected `Socket` and calls `connect(endpoint, 2_000)`. Because the server is listening on loopback, the connection succeeds and prints `Connected`.
4. The client sets `SO_TIMEOUT=200` ms and calls `InputStream.read()`. No bytes are available and the server has not half-closed/closed its sending side, so this read expires and throws `SocketTimeoutException`; the client prints `Read timed out`.
5. The `finally` block of the first read releases the latch; only then does the worker send byte 42. The client changes `SO_TIMEOUT` to 2,000 ms and reads again on the still-open socket; it prints `Received: 42`.
6. `Future.get(...)` checks that the worker finished; `try-with-resources` closes `client`, `peer`, and `listener`. `shutdownNow()` terminates the demo executor.

**Takeaway from the example:** a read timeout does not automatically close the socket. However, reading again is safe in this example only because the protocol deliberately sends **exactly one byte** and the first read did not consume part of a frame. With multi-byte protocols, a timeout can occur after receiving **part of a message**, so you must preserve framing state or close and create a new connection.

In an overloaded environment, thread scheduling or test timeouts may be affected by machine load. Running on loopback and using a latch helps establish the exact event ordering; the illustrative millisecond values are not real-time guarantees.

## 6. Handling Timeouts Properly by Phase and Exception

### 6.1. Catching Exceptions Close to the Relevant Operation

Example distinguishing where connect fails versus where read fails:

~~~java
// Illustrative snippet inside a method that may throw IOException.
try (Socket socket = new Socket()) {
    try {
        socket.connect(remoteAddress, 2_000);
    } catch (SocketTimeoutException ex) {
        // Timed out waiting to establish the connection.
        throw new IOException("TCP connect timed out", ex);
    }

    socket.setSoTimeout(3_000);
    try {
        int firstByte = socket.getInputStream().read();
        if (firstByte == -1) {
            throw new java.io.EOFException("Peer closed the stream");
        }
        // Parse data according to the agreed protocol.
    } catch (SocketTimeoutException ex) {
        // No bytes available to complete the read within the time limit.
        throw new IOException("TCP read timed out", ex);
    }
}
~~~

This is **not a standalone program**: `remoteAddress` is a `SocketAddress` already created/validated by the application. In a real program, if catching `IOException` around both connect and read, include context about the **phase being executed** for proper handling/logging rather than assuming every `SocketTimeoutException` is a read timeout.

| Symptom | Typical Signal | Practical Meaning |
| --- | --- | --- |
| Connect waits past limit | `SocketTimeoutException` on `connect` | Connection was not established within the time limit |
| Destination refuses immediately | `ConnectException` | Endpoint is not accepting connections at that moment; not necessarily a timeout |
| Name/address resolution error | `UnknownHostException` or other connect error depending on how endpoint was created | Check hostname, DNS, address |
| Read gets no data within limit | `SocketTimeoutException` on `read` | Read waited too long; does not necessarily mean the peer is dead |
| Peer ends sending side | `read() == -1` (or `EOFException` in full-read APIs) | EOF, distinct from timeout |
| TCP reset/abnormal close | `SocketException`/`IOException` | Usually should not continue using the connection normally |
| Thread needs cancellation | `InterruptedException` while waiting on latch/future, etc. | Restore interrupt flag, clean up resources per contract |

Exception types can be influenced by the operating system, wrapper APIs, and network state; do not test by assuming every machine returns the exact same error message or exact timing.

### 6.2. Reading Multiple Bytes: Do Not Lose State After a Timeout

TCP is a **byte stream**, with no message boundaries tied to `read` calls. Consider a protocol with a **4-byte length prefix + N-byte payload**:

- If 4 prefix bytes and 300 payload bytes were already read before a read timeout, those 300 consumed bytes **do not return to the input stream**.
- Calling `readFully(payload)` from the beginning on the same stream can shift offsets, swallow bytes from the next frame, or wait for the wrong remaining count.
- You must update the `received` counter/parser state across each successful read, or **discard the connection** if the protocol does not support resuming.
- Be especially careful with convenience methods like `DataInputStream.readFully()`: when it throws midway, the application does not receive the count of already-consumed bytes via a return value. For fine-grained recovery, track progress yourself in a read loop.

Example of a read loop with an **overall deadline**, separate from individual `read` timeouts:

~~~java
// This is a helper method; requires imports:
// java.io.*; java.net.*; java.util.concurrent.TimeUnit;
static void readExactlyBeforeDeadline(
        Socket socket, byte[] target, long timeoutMillis)
        throws IOException {

    if (timeoutMillis <= 0) {
        throw new IllegalArgumentException("timeoutMillis must be positive");
    }

    long deadline = System.nanoTime()
            + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
    int offset = 0;

    while (offset < target.length) {
        long remainingNanos = deadline - System.nanoTime();
        if (remainingNanos <= 0) {
            throw new SocketTimeoutException("Whole frame deadline exceeded");
        }

        long remainingMs = Math.max(
                1, TimeUnit.NANOSECONDS.toMillis(remainingNanos));
        socket.setSoTimeout(
                (int) Math.min(remainingMs, Integer.MAX_VALUE));

        int n = socket.getInputStream().read(
                target, offset, target.length - offset);
        if (n == -1) {
            throw new EOFException("Peer closed before full frame");
        }
        offset += n;
    }
}
~~~

This method demonstrates a **supplementary technique** when a limit is needed for an *entire chunk of data*: set a deadline on `System.nanoTime()`, allow each `read` to wait at most the remaining time, and accumulate read bytes. It assumes `target.length` has already been validated by the protocol; size limits must be enforced before allocation.

Note three limitations: (1) the timeout is rounded to milliseconds, so it is not an absolute real-time deadline; (2) this method **mutates `SO_TIMEOUT` on the socket** and does not restore the previous value, so the socket owner must decide whether to reset it for further use; (3) if the method throws, bytes already written into `target` remain there, and the caller must decide whether to close the session or preserve appropriate progress state. The illustrative example only handles reading, not connecting or prefix framing.

## 7. Why Setting Timeouts Alone Is Still Not Enough

### 7.1. No Write Timeout via `setSoTimeout`

When the network is congested or the peer reads slowly, `OutputStream.write(...)` can block due to TCP flow control. `SO_TIMEOUT` does not apply to writes. In production systems, you need overall task deadlines, cancellation/connection-closing mechanisms, payload limits, resource bounds, and appropriate I/O APIs. Do not describe `setSoTimeout(5_000)` as "after 5 seconds all I/O stops automatically."

### 7.2. Multiple Connection Attempts and Retries

A client may make multiple connect attempts to retry on failure. However, if there are three connect attempts of up to 2 seconds each, followed by a 5-second read and backoff, **total time can far exceed 7 seconds**. Retries must be bounded by both attempt count and a time budget; do not retry indefinitely just because the error is `SocketTimeoutException`.

After a **read timeout**, especially for requests that mutate data, the server may have already finished processing while the response was delayed or lost. Blind retries can execute the business operation twice. If safe retries are required, design application-level acknowledgments, idempotency keys, or status checks.

### 7.3. Resources and Concurrent Clients

A server using one thread per socket can run out of threads if many clients hold connections open without sending data. Using `setSoTimeout` helps detect overly long read waits, but it does not replace bounding socket counts, worker queues, message sizes, and **total session lifetime**. For `ServerSocket.accept()`, set the accept timeout (if needed) **separately** from the read timeout of accepted sockets:

~~~java
// Illustrates only the difference between the two sockets:
listener.setSoTimeout(1_000);             // Wait time for accept()
Socket acceptedSocket = listener.accept();
acceptedSocket.setSoTimeout(3_000);       // Wait time for read()
~~~

This snippet assumes `listener` is already created/bound; calls may throw `IOException`. If `accept()` times out, the listening socket typically remains usable to keep accepting connections. With multiple connections, configure timeouts for **each** accepted socket and close resources properly when clients disconnect.

## 8. Concept-Check Exercises

### Scenario A: Connect Succeeds, Read Waits Forever

~~~text
connect(endpoint, 1500) -> succeeds after 20 ms
setSoTimeout(0)
read()                  -> server sends no data, does not close
~~~

**Answer:** connect has already succeeded; `setSoTimeout(0)` places no limit on read wait time. If the server sends nothing, sends no EOF, and no other error occurs, `read()` can wait indefinitely. The 1,500 ms connect timeout has no effect in this phase.

### Scenario B: Peer Refuses Connection Immediately

~~~text
connect(endpoint, 5000) -> ConnectException after a few ms
~~~

**Answer:** having a 5-second timeout does not mean the connection is forced to wait the full 5 seconds. A connection-refused error can arrive immediately.

### Scenario C: A Large Frame Is Trickled Slowly

~~~text
SO_TIMEOUT = 1000 ms
Read 1: 700 ms -> 1 byte arrives
Read 2: 700 ms -> 1 byte arrives
... thousands of similar reads
~~~

**Answer:** if each read receives a byte before its time limit expires, no read needs to throw `SocketTimeoutException` merely because total elapsed time exceeded 1 second. To stop a "slow trickle" scenario, you need an overall deadline and progress-limiting rules.

### Scenario D: Partial Data Received Before Timeout

The server specifies a 100-byte response frame; the client has received 40 bytes, and then a read timeout occurs. **Answer:** the 40 bytes already read are still part of the current frame. If you decide to continue, you must read the **remaining 60 bytes**, not re-read all 100 bytes from the beginning. If the parser cannot preserve the offset or the protocol/application does not allow recovery, close the socket and report failure clearly.

### Scenario E: Wanting a Timeout for `accept()`

**Answer:** use `ServerSocket.setSoTimeout(ms)` on the **listening socket**. It does not set a read timeout for client sockets returned by `accept()`; each client socket must be configured independently.

## 9. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| Using `new Socket(host, port)` and expecting to set connect timeout afterward | The constructor already attempted to connect before you configured it | Use `new Socket()` then `connect(endpoint, timeout)` |
| Calling only `setSoTimeout` to handle both connect and read | It only limits blocking reads on the socket | Call `connect(..., timeout)` separately; configure `setSoTimeout` for reads |
| Thinking `SO_TIMEOUT=0` means "do not wait" | `0` means wait indefinitely if no other event occurs | Set an appropriate positive time limit |
| Thinking a read timeout means the server is dead | The server may simply be processing slowly | Handle according to application policy; do not equate with EOF |
| Taking `connect timeout + read timeout` as the overall deadline | DNS, multiple reads/retries, and writes can exceed that sum | Use a shared deadline and track remaining time |
| Re-reading a frame from the start after a timeout | Prior bytes may already have been consumed | Preserve parser state and offset or close the socket |
| Thinking `setSoTimeout` also limits `write` | The option applies to reads, not writes | Manage deadlines/cancellation and choose an appropriate I/O mechanism |
| Mixing up `ServerSocket` and `Socket` | `accept()` and `read()` are different operations | Configure timeouts on the right object |
| Retrying write-mutating requests after a read timeout | The server may have already processed the request | Use idempotency and a retry budget |
| Swallowing `IOException` and keeping the socket forever | Application state may no longer be consistent | Log the cause, close/recover the session per a clear protocol |

## 10. Pre-Deployment Checklist for Socket Timeouts

- [ ] Does every `Socket.connect(...)` needing a timeout use the overload with a positive `timeout` in **ms**?
- [ ] Does the socket only perform reads after connecting successfully and setting an appropriate `SO_TIMEOUT`?
- [ ] Do you distinguish `SocketTimeoutException` during **connect** from **read**, `ConnectException`, and EOF?
- [ ] For slow/unresponsive connections, is there an overall deadline in addition to per-read timeouts?
- [ ] For multi-byte frames, are length limits enforced, offsets tracked, and partial reads/timeouts handled?
- [ ] Is it understood that `SO_TIMEOUT` does not automatically apply to writes, TLS, DNS, `accept`, or the entire request?
- [ ] Does the server set a separate `accept` timeout if needed, and does each accepted socket have its own read timeout?
- [ ] Do retries bound attempt count, total time, and ensure idempotency for operations with side effects?
- [ ] Are sockets and executors closed/shut down even on error; do logs include phase, endpoint, timeout, and cause without leaking sensitive data?

**Conclusion:** `Socket.connect(endpoint, timeout)` protects the **TCP establishment phase**; `Socket.setSoTimeout(timeout)` protects **the wait time of a single blocking read**. Understanding the scope of each mechanism, distinguishing timeouts from EOF/connection errors, and managing deadlines at the application layer will help Java programs avoid hanging indefinitely, reading partial frames, and retrying unsafely.
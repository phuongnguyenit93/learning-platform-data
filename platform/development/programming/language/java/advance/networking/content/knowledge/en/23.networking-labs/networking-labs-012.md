# Testing Mid-Flight Failures, Ordered Close, and Zero Socket or Thread Leaks

**A successful connection does not prove a Java networking program is correct.** The hardest bugs usually appear when the server has received part of a request and disconnects, a response is missing bytes, one thread closes a socket while another thread is still reading, or an executor has not stopped when the application assumes it has shut down.

This Knowledge article belongs to **Java Advance - networking → Networking Labs**, guiding you to create **repeatable**, **offline** tests that actively inject faults and verify the entire lifecycle on Java 17+. The content prioritizes verification via APIs and observable state rather than guessing from OS- and I/O-timing-dependent messages like `SocketException: Broken pipe` or `Connection reset`.

**Four invariants to verify:**
1. **Protocol completeness**: do not pass a mid-flight truncated frame into the business layer.
2. **Ordered close**: finish writing/flushing, close the appropriate TCP direction when the protocol allows, read the remaining response, and then close the entire socket.
3. **Failure-safe cleanup**: even if a handler throws an IOException, the accepted socket and test-owned resources are still released.
4. **No surviving workers**: the listener is closed; the executor is terminated; test-created threads are no longer alive and active socket counts return to 0.

The article provides three complete Java 17+ programs:
- `TruncatedFrameDemo.java`: 12-byte length-prefix, server sends only 5 bytes then FIN; verifies missing data using `readNBytes` and `readFully`.
- `OrderedShutdownDemo.java`: PING/PONG, two-way `shutdownOutput()`, ordered close, and thread/socket lifecycle checks.
- `SocketLeakAuditDemo.java`: 12 requests, four IOExceptions injected after reading the request; accepted=closed=12, active=0, executor terminated.

The programs have been run on loopback using a JDK with Java 17-compatible APIs; no external server, additional dependencies, passwords, or tokens are required.

## 1. Network Testing Must Measure More Than Output Data

An echo program can print PONG while still leaking threads, sockets, or having a broken body parser. For example:
- The client receives half the body and sees EOF, yet the code still returns a "success" object.
- The server finishes reading the request, hits an exception, and skips closing the accepted Socket.
- The client uses `Future.get(3,SECONDS)`; the test thread exits after three seconds, but the worker remains blocked forever at `ServerSocket.accept()`.
- A response is sent, but `ExecutorService` has not shut down, and a non-daemon thread prevents the JVM from exiting.
- The test only waits one second with `Thread.sleep` and checks Thread.activeCount; results are noisy due to JVM GC/JIT and scheduling.

For experiments, **functional result**, **network failure semantics**, and **resource ownership** must be separated:

| Layer | Question | Criterion |
| --- | --- | --- |
| Byte stream | Were enough bytes received according to the frame? | declaredLength == receivedLength |
| Protocol | Is EOF at a valid boundary or mid-message? | complete or TRUNCATED_FRAME |
| Socket | Are client/accepted/listener closed on all branches? | isClosed, accepted/closed counts |
| Task | Did Future succeed, fail, or get cancelled? | Terminal result, preserved cause |
| Executor | Are any workers still alive after shutdown? | awaitTermination/isTerminated, tracked thread dead |
| System | Does resource usage grow long-term? | OS handles/FDs and soak tests |

A reliable test **must fail when resources are not released**, not just assert the response body.

## 2. Fault Matrix Before Writing Code

| Case | Fault injection | Expected outcome |
| --- | --- | --- |
| Normal | No fault | Full body, complete close |
| Valid EOF | Peer flushes, `shutdownOutput` after message | Read until EOF without losing payload |
| Truncated frame | 12-byte prefix, 5-byte body then FIN | Detected as truncated |
| IOException in handler | Throw after reading request byte | Socket still closes, active decreases |
| Early close | Peer closes without sending response | Client receives EOF or error, does not hang |
| Read timeout | Peer stays silent keeping socket open | `SocketTimeoutException`, not conflated with EOF |
| Accept timeout | No new client | Bounded timeout, listener does not break itself |
| Abortive reset | `SO_LINGER=0` in a separate test | Observable error; do not assert text |
| Half-close | Client flushes and shuts down send direction | Server can still reply in the reverse direction |
| Executor shutdown | Stop new tasks, await | Terminated or test FAILs |
| Concurrent shutdown | Another thread closes SocketChannel | Cleanup, classify as local close |
| Leak audit | N connections, some exceptions | accepted==closed, active==0 |

Do not catch every IOException and treat it as an "injected fault". For strict tests, use a **custom marker exception** for simulated faults; other errors must be propagated. Also, do not set `SO_LINGER=0` on every socket to try to force a fixed Broken pipe string.

## 3. Stable Loopback TCP Fixture

Use `ServerSocket` bound to loopback and choose port 0:

~~~java
ServerSocket listener = new ServerSocket(
        0, 4, InetAddress.getByName("127.0.0.1"));
listener.setSoTimeout(3000);
int port = listener.getLocalPort();
~~~

This is only a snippet. The listener must be closed in try-with-resources or finally. Port 0 asks the OS to allocate a free port, avoiding test conflicts when CI runs in parallel. The 127.0.0.1 address does not open a public port.

Three distinct limits:
- `ServerSocket.setSoTimeout(3000)`: bounds the wait time for **a single accept** call.
- `Socket.setSoTimeout(2000)`: bounds the wait time for **a single blocking read** from the Socket InputStream.
- `Future.get(3, TimeUnit.SECONDS)`: bounds the time the test thread waits for the worker Future.

**None of these limits automatically acts as a total deadline for the entire transaction.** And Future.get(timeout) **does not automatically stop the worker**: on timeout, proper cleanup/cancellation is required.

When the fixture starts a thread to accept, bind the listener **before** starting the client. Do not rely on sleep to guess when the server is ready: use synchronization via a Future, latch, or protocol handshake when needed.

## 4. TCP Is a Byte Stream, Not a List of Messages

A simple protocol can send a **4-byte integer length (big-endian)** before the body. For example:

~~~text
00 00 00 0C | h e l l o w o r l d ! ! 
  12 bytes  |       expected 12-byte body
~~~

If the server only sends:

~~~text
00 00 00 0C | h e l l o | FIN
 length=12  | 5 bytes  | end of stream
~~~

then TCP terminates the send direction with a normal FIN, **but the application frame is incomplete**. The client must detect the error instead of returning success.

The JDK provides two approaches:
- `InputStream.readNBytes(expected)`: returns **at most** expected bytes; it may return a **shorter** array if EOF arrives early. You must compare array.length.
- `DataInputStream.readFully(byte[expected])`: requires the full number of bytes; if EOF is encountered early, it throws `EOFException`.

Do not conflate:
- `read()==-1` is stream EOF.
- `read()==0` on a nonblocking SocketChannel may mean no bytes are available yet or the buffer is full; it is not EOF.
- EOF occurring after complete data is normal if the protocol is designed that way.
- EOF occurring mid-frame is a **truncated message**, even without a TCP RST.

**Size bounds:** The receiver must validate declaredLength within an acceptable range before allocating an array. Never take an arbitrary integer from a peer and pass it directly to `new byte[declared]`.

## 5. Java 17+ Example 1: Mid-Flight Failure via Partial FIN

**TruncatedFrameDemo.java** creates a server that handles two sequential connections:
- The server writes int 12, then five bytes of the string hello, flushes, and calls `shutdownOutput()`.
- The first client uses `readNBytes(12)`; it returns five bytes so the test marks it as truncated.
- The second client uses `readFully(new byte[12])`; it catches EOFException.
- Client/accepted sockets are in try-with-resources, the server task uses a Future, and the pool is shut down.

Create the file **TruncatedFrameDemo.java**:

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class TruncatedFrameDemo {
    static final int EXPECTED = 12;

    static void serve(ServerSocket listener) throws Exception {
        for (int i = 0; i < 2; i++) {
            try (Socket peer = listener.accept()) {
                DataOutputStream out =
                        new DataOutputStream(peer.getOutputStream());
                out.writeInt(EXPECTED);
                out.write("hello".getBytes(StandardCharsets.UTF_8));
                out.flush();
                peer.shutdownOutput();
            }
        }
    }

    static Socket connect(ServerSocket listener) throws Exception {
        Socket client = new Socket(
                "127.0.0.1", listener.getLocalPort());
        client.setSoTimeout(2000);
        return client;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try (ServerSocket listener = new ServerSocket(
                0, 4, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(3000);

            Future<?> server = executor.submit(() -> {
                try {
                    serve(listener);
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            });

            try (Socket client = connect(listener)) {
                DataInputStream in =
                        new DataInputStream(client.getInputStream());
                int expected = in.readInt();
                byte[] got = in.readNBytes(expected);

                System.out.println(
                        "Declared frame bytes: " + expected);
                System.out.println(
                        "Received frame bytes: " + got.length);
                System.out.println(
                        "Truncated: " + (got.length != expected));
            }

            boolean caught = false;
            try (Socket client = connect(listener)) {
                DataInputStream in =
                        new DataInputStream(client.getInputStream());
                int expected = in.readInt();
                in.readFully(new byte[expected]);
            } catch (EOFException eof) {
                caught = true;
            }

            System.out.println(
                    "readFully raised EOFException: " + caught);
            server.get(3, TimeUnit.SECONDS);
        } finally {
            executor.shutdown();
            boolean done = executor.awaitTermination(
                    3, TimeUnit.SECONDS);
            if (!done) executor.shutdownNow();
            System.out.println("Executor terminated: " + done);
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 TruncatedFrameDemo.java
java TruncatedFrameDemo
~~~

Verified output:

~~~text
Declared frame bytes: 12
Received frame bytes: 5
Truncated: true
readFully raised EOFException: true
Executor terminated: true
~~~

**Conclusion:** The same missing-bytes frame error has two ways to be detected: length mismatch or EOFException. If the code does not check the number of bytes returned by readNBytes, a truncated response can still be treated as a success. The fixture sends FIN, not an active reset; it must be logged as **TRUNCATED_FRAME**, rather than calling it Connection reset.

The sockets in the code are closed using try-with-resources. However, the Executor terminated value must be **asserted true** in automated tests; if false, the shutdownNow fallback has not proven that the worker has stopped. In production code, add checks and cleanup for that case.

## 6. Ordered Socket Close: Stop Sending While Continuing to Receive

For a PING/PONG protocol using EOF to mark the end of a request:

~~~text
Client                                      Server
  |                                            |
  |---------- PING + newline ---------------->|
  |-------- shutdownOutput / FIN ------------>|
  |                                            | readLine -> PING
  |                                            | readLine -> null (EOF)
  |<---------------- PONG + newline -----------|
  |<----------- shutdownOutput / FIN ----------|
  | readLine -> PONG                           |
  | readLine -> null                           |
  |                                            |
  | close Socket                        close accepted Socket
  | close listener                      complete Future
  | pool.shutdown + awaitTermination          |
~~~

**Socket.shutdownOutput() is a half-close**: the send direction ends while the read direction remains active. Thus, the client can finish sending the request and continue waiting for PONG.

A critical pitfall: if BufferedWriter is created from socket.getOutputStream, calling writer.close right after PING can close **the entire Socket**, losing the ability to read PONG. Replace it with:
1. write PING.
2. writer.flush().
3. socket.shutdownOutput().
4. Read the response and EOF.
5. Finally socket.close().

Not every protocol uses half-close this way: HTTP keep-alive, TLS, and WebSocket have their own shutdown/framing semantics. Do not inject a raw FIN into a protocol when it expects the connection to continue.

## 7. Java 17+ Example 2: PING/PONG and Resource Verification

**OrderedShutdownDemo.java** has a worker named via a ThreadFactory. The server reads PING/EOF and replies with PONG/EOF. The client only closes after reading the response. Finally, the code checks the client socket, accepted server socket, listener, executor, and tracked worker.

Create the file **OrderedShutdownDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class OrderedShutdownDemo {
    static String handle(
            ServerSocket listener,
            AtomicReference<Socket> accepted) throws Exception {

        try (Socket peer = listener.accept()) {
            accepted.set(peer);
            peer.setSoTimeout(3000);

            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            peer.getInputStream(),
                            StandardCharsets.UTF_8));
            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            peer.getOutputStream(),
                            StandardCharsets.UTF_8));

            String first = in.readLine();
            boolean requestEof = in.readLine() == null;

            out.write("PONG\n");
            out.flush();
            peer.shutdownOutput();

            return "Server request: " + first
                    + "|EOF=" + requestEof;
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicReference<Thread> workerThread =
                new AtomicReference<>();
        AtomicReference<Socket> accepted = new AtomicReference<>();

        ExecutorService pool = Executors.newSingleThreadExecutor(
                task -> {
                    Thread t = new Thread(
                            task, "ordered-demo-worker");
                    workerThread.set(t);
                    return t;
                });

        ServerSocket listener = new ServerSocket(
                0, 2, InetAddress.getByName("127.0.0.1"));
        listener.setSoTimeout(3000);

        Socket client = null;
        boolean terminated = false;

        try {
            Future<String> outcome =
                    pool.submit(() -> handle(listener, accepted));

            client = new Socket(
                    "127.0.0.1", listener.getLocalPort());
            client.setSoTimeout(3000);

            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            client.getInputStream(),
                            StandardCharsets.UTF_8));
            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            client.getOutputStream(),
                            StandardCharsets.UTF_8));

            out.write("PING\n");
            out.flush();
            client.shutdownOutput();

            String answer = in.readLine();
            boolean responseEof = in.readLine() == null;

            System.out.println("Client response: " + answer);
            System.out.println(
                    "Client response EOF: " + responseEof);
            System.out.println(
                    outcome.get(3, TimeUnit.SECONDS));

        } finally {
            if (client != null) client.close();
            listener.close();
            pool.shutdown();
            terminated = pool.awaitTermination(
                    3, TimeUnit.SECONDS);
            if (!terminated) pool.shutdownNow();
        }

        System.out.println("Client closed: " + client.isClosed());
        System.out.println(
                "Accepted socket closed: " + accepted.get().isClosed());
        System.out.println("Listener closed: " + listener.isClosed());
        System.out.println("Executor terminated: " + terminated);
        System.out.println(
                "Worker alive: " + workerThread.get().isAlive());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OrderedShutdownDemo.java
java OrderedShutdownDemo
~~~

Verified stdout:

~~~text
Client response: PONG
Client response EOF: true
Server request: PING|EOF=true
Client closed: true
Accepted socket closed: true
Listener closed: true
Executor terminated: true
Worker alive: false
~~~

The first and second lines confirm the client **did not close too early**, so it could still read PONG. The third line confirms the server saw the request-direction EOF. The remaining lines prove proper cleanup for the resources **tracked by the fixture itself**. In a multi-client server, you must also collect all accepted sockets and pending tasks, not just one.

## 8. Stop Order: Why Each Resource Type Must Be Closed

A network service can apply this stop model:
1. Mark state as STOPPING and stop accepting new work.
2. Stop accepting or close the listener to prevent new connections during cleanup.
3. Wait a bounded period for in-flight requests to complete the protocol.
4. After the deadline, close any remaining active sockets/channels.
5. Fail/cancel all queued futures and clean up request contexts.
6. Call ExecutorService.shutdown(), wait with awaitTermination().
7. On timeout, call shutdownNow() according to policy and re-verify.
8. Assert listener closed, active socket registry empty, executor terminated, and owned worker threads stopped.

**The order may vary depending on the protocol.** For example, an HTTP server may need to wait for in-flight responses before closing sockets, whereas a server reading raw PING will actively half-close after the message. What matters is setting a **bounded grace period and deadline**, never letting shutdown hang forever.

Distinguish between:
- shutdown() does not wait.
- awaitTermination() waits with a bound.
- shutdownNow() is only best effort.
- Future.get(timeout) only times out waiting; it does not cancel the task.
- Future.cancel(true) may interrupt, but is not guaranteed to unblock all blocking socket I/O.
- Closing a Socket/ServerSocket under proper ownership can help a blocked read/accept terminate with an exception.

## 9. Resources Need a Responsible Owner

| Resource | Created by | Cleaned up by |
| --- | --- | --- |
| ServerSocket listener | Test server/bootstrap | Server lifecycle owner |
| Accepted Socket | ServerSocket.accept | Connection handler in try-with-resources |
| Outbound client Socket | Client factory/request | Client scope |
| Input/output streams | Socket | Stream owner or Socket owner per protocol |
| ExecutorService | Test/service coordinator | Coordinator shutdown + await |
| Future | Submitter | Caller tracking result/cancel |
| SocketChannel/Selector | Event loop | Event-loop lifecycle owner |
| AsynchronousSocketChannel | Async connection manager | Connection context |

A common design bug: the parent closes a Socket with try-with-resources while the worker is still using that reference. In that case, the worker receives an IOException due to a **local lifecycle race**, not necessarily from the peer.

With Socket, closing an InputStream/OutputStream obtained from the socket typically closes the entire socket. Therefore, do not use closing a writer to signal end-of-send if the client still needs to read a response; use flush + shutdownOutput for protocols where appropriate.

## 10. Leak-Free Experiments Must Have Counters

Do not just compare Thread.activeCount() before and after: background threads from JVM/GC/JIT or frameworks can change independently, and thread count does not measure socket file descriptors.

Better measurements:
- **accepted** increments after a successful accept.
- **active** increments when the handler takes ownership of the socket.
- **closed** increments in finally after the socket is closed.
- **injected** increments when an expected injected failure is actually caught.
- **successful replies** and **early closes** count observed client flows.
- **executor terminated** verifies shutdown completion.
- **Tracked ThreadFactory** holds references to test-created threads to check `!isAlive()`.
- **isClosed()** on actual client/accepted/listener sockets.
- For soak tests, combine OS open FD/handle counts, active connections, and JVM thread dumps.

**Counter limitations:** accepted=closed and active=0 show that the sockets *counted by the fixture* went through cleanup. They do not absolutely prove no other socket was left behind outside the registry. TIME_WAIT is an OS TCP state that can exist after Java Socket.close without being a leak.

## 11. Deterministic Fault Injection in the Handler

Suppose the server handles 12 sequential requests; indices divisible by 3 (0,3,6,9) have a fault injected after reading one byte:

~~~java
active.incrementAndGet();
try (socket) {
    socket.setSoTimeout(2000);
    int requestByte = socket.getInputStream().read();
    if (requestByte == -1) {
        throw new EOFException("missing request");
    }
    if (index % 3 == 0) {
        throw new IOException("injected failure");
    }
    socket.getOutputStream().write(66);
    socket.shutdownOutput();
} finally {
    closed.incrementAndGet();
    active.decrementAndGet();
}
~~~

This is a **snippet**; counters, Socket, and index must be defined. Try-with-resources ensures Socket.close when IOException occurs; finally still decrements active. This is a more reliable way to test cleanup logic than trying to trigger an OS Broken pipe message.

If the handler deliberately throws a plain IOException, the server-side catch should distinguish the **injected fault marker** from an unexpected network IOException. Do not treat any arbitrary IOException occurring at every 3rd index as expected and ignore it.

## 12. Java 17+ Example 3: 12 Requests and 4 Mid-Flight Faults

Create the file **SocketLeakAuditDemo.java**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class SocketLeakAuditDemo {
    static final int REQUESTS = 12;

    static final AtomicInteger accepted = new AtomicInteger();
    static final AtomicInteger closed = new AtomicInteger();
    static final AtomicInteger active = new AtomicInteger();
    static final AtomicInteger injected = new AtomicInteger();

    static void handle(Socket socket, int index)
            throws IOException {
        active.incrementAndGet();

        try (socket) {
            socket.setSoTimeout(2000);
            int input = socket.getInputStream().read();

            if (input == -1) {
                throw new EOFException("missing request byte");
            }
            if (index % 3 == 0) {
                throw new IOException(
                        "injected failure after receiving request byte");
            }

            socket.getOutputStream().write(66);
            socket.shutdownOutput();
        } finally {
            closed.incrementAndGet();
            active.decrementAndGet();
        }
    }

    static void serve(ServerSocket listener)
            throws IOException {
        for (int i = 0; i < REQUESTS; i++) {
            Socket socket = listener.accept();
            accepted.incrementAndGet();

            try {
                handle(socket, i);
            } catch (IOException expected) {
                if (i % 3 == 0) {
                    injected.incrementAndGet();
                } else {
                    throw expected;
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicReference<Thread> worker =
                new AtomicReference<>();

        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> {
                    Thread thread = new Thread(
                            task, "leak-audit-worker");
                    worker.set(thread);
                    return thread;
                });

        ServerSocket listener = new ServerSocket(
                0, 8, InetAddress.getByName("127.0.0.1"));
        listener.setSoTimeout(3000);

        int ok = 0;
        int failed = 0;
        boolean terminated = false;

        try {
            Future<?> future = executor.submit(() -> {
                try {
                    serve(listener);
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });

            for (int i = 0; i < REQUESTS; i++) {
                try (Socket client = new Socket(
                        "127.0.0.1",
                        listener.getLocalPort())) {
                    client.setSoTimeout(2000);
                    client.getOutputStream().write(i);

                    int answer = client.getInputStream().read();
                    if (answer == 66) {
                        ok++;
                    } else if (answer == -1) {
                        failed++;
                    } else {
                        throw new AssertionError(
                                "unexpected byte " + answer);
                    }
                }
            }

            future.get(3, TimeUnit.SECONDS);
        } finally {
            listener.close();
            executor.shutdown();
            terminated = executor.awaitTermination(
                    3, TimeUnit.SECONDS);
            if (!terminated) {
                executor.shutdownNow();
            }
        }

        System.out.println("Requests: " + REQUESTS);
        System.out.println("Successful replies: " + ok);
        System.out.println("Expected early closes: " + failed);
        System.out.println("Faults injected: " + injected.get());
        System.out.println(
                "Server sockets accepted: " + accepted.get());
        System.out.println(
                "Server sockets closed: " + closed.get());
        System.out.println(
                "Active server sockets: " + active.get());
        System.out.println(
                "Listener closed: " + listener.isClosed());
        System.out.println(
                "Executor terminated: " + terminated);
        System.out.println(
                "Tracked worker alive: "
                + worker.get().isAlive());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SocketLeakAuditDemo.java
java SocketLeakAuditDemo
~~~

Verified stdout:

~~~text
Requests: 12
Successful replies: 8
Expected early closes: 4
Faults injected: 4
Server sockets accepted: 12
Server sockets closed: 12
Active server sockets: 0
Listener closed: true
Executor terminated: true
Tracked worker alive: false
~~~

**Reading the results:**
- 12/12 accepted sockets went through the close path.
- The active handler/socket counter returned to 0.
- 8 successful replies and 4 early closes prove failure injection actually ran.
- The listener is closed, the executor is terminated, and the test-created worker thread has stopped.

**Limitations:** Sequential server, one-byte request body. This is a fixture for measuring the cleanup code path, not a load test for a public server. For production, bounded concurrency, limits, and a registry for all connections are needed.

## 13. Try-with-resources and finally: Different Roles

~~~java
Socket peer = listener.accept();
try (peer) {
    process(peer);
} finally {
    recordFinished();
}
~~~

This is a snippet: `process` and `recordFinished` are application helpers. When process throws an IOException, Java still calls close on the Socket before entering finally. In real code, minimize operations that can throw exceptions **between accept and the start of the ownership scope**, because that gap is where leaks can happen.

Try-with-resources does not automatically shut down ExecutorService on **Java 17** (at that time ExecutorService was not yet AutoCloseable). The coordinator still needs a finally block for pool shutdown/await, pending Futures, the listener, and resources outside the lexical scope.

When exceptions occur in both the body and close, Java may attach the close exception to Throwable.getSuppressed(). Log the root cause along with suppressed exceptions in diagnostics; do not lose the original error cause.

## 14. Read Timeout, Accept Timeout, and Total Deadline

| API | Bounds | Does not bound |
| --- | --- | --- |
| ServerSocket.setSoTimeout(ms) | One waiting accept call | Entire server lifetime |
| Socket.setSoTimeout(ms) | One blocking read | Total body/transaction time |
| Socket.connect(address,timeout) | Connect step | Response read |
| Future.get(timeout) | Caller waiting on Future | Worker task or socket |
| ExecutorService.awaitTermination(timeout) | Caller waiting for shutdown | Force stop when returning false |
| Thread.join(timeout) | Caller waiting on thread | Thread stopping itself |

If a worker is waiting on a read, the caller's Future.get expiring does not automatically stop the worker. You must signal cancellation, close the owner-managed socket, and shut down the executor with a bound. Do not print PASS while the executor is still alive.

If the server sends one byte right before each read timeout, the total request can stretch out for a very long time. For real applications, add an **end-to-end deadline**, payload length cap, connection cap, and queue/concurrency limits.

## 15. How to Test Connection Reset or Broken Pipe?

**Broken pipe** is typically an OS message when writing to a socket that is no longer receiving, not a dedicated Java exception class. **Connection reset** is a TCP abort signal; Java usually throws IOException/SocketException with a message that varies by OS/provider/timing.

Do not make automated CI depend on:
- Exact English error strings.
- Seeing Broken pipe on the **first write** after peer-close.
- Always getting RST instead of FIN when a process closes.
- Assuming a single write success means the peer has processed the request.

OS-supported tests may use `Socket.setSoLinger(true,0)` and then close to test abortive termination, but do not hard-code the class/message and do not use this behavior as a production close strategy.

Important: if a client sends a POST with side effects, the server may have already committed before a connection reset occurs prior to the response. Automatic retries can execute duplicates. Idempotency keys, status queries, or reconciliation per the API contract are required.

**Deterministic fault injection** in the handler or transport adapter is a better choice for testing app cleanup, while RST/FIN packet evidence should be tested separately at the network layer.

## 16. NIO, Selector, and Async I/O Lifecycle

With SocketChannel + Selector:
- When a nonblocking read returns 0, do not treat it as EOF; wait for OP_READ readiness.
- When read returns -1, that is EOF; depending on the protocol, half-close or cancel the selection key/close the channel.
- SelectionKey.cancel does not automatically close the SocketChannel.
- Selector.wakeup helps the event loop exit select to observe the stop flag; close the Selector at the end of the lifecycle.
- Closing a SocketChannel from another thread during blocked I/O can produce AsynchronousCloseException.
- Interrupting blocked NIO I/O can close the channel and produce ClosedByInterruptException.
- Do not use a terminal channel for new I/O.

With AsynchronousSocketChannel, a completion handler may receive completed(-1) on EOF or failed(exception) on error. Cancelling a Future/closing a channel requires managing callback lifecycles and not reusing a ByteBuffer while an older operation may still complete.

A common race bug: a watchdog closes the socket while a writer is sending a response; the writer throws IOException. That may be a **local cancellation**, not necessarily a peer reset. Record closeReason and owner to avoid retries or double responses.

## 17. Post-Test Leak Verification Procedure

**Before asserting**:
1. Wait for all server/client Futures to complete or time out.
2. Close listeners and any active sockets still managed by the registry.
3. Shut down the executor, run bounded awaitTermination, and check the result.
4. Check accepted/closed/active counters when no handlers are running.
5. Check tracked Thread objects and concrete Socket.isClosed.
6. For long tests, monitor process FDs/handles, thread dumps, heap, and TCP states to detect long-term trends.

**Do not use a single Thread.activeCount snapshot** as a conclusion. It can change due to the JVM or other libraries. **Do not treat TIME_WAIT as a Java leak:** TIME_WAIT is a kernel TCP state that can persist after close.

Fixture measurements do not prove the entire JVM is completely leak-free; they prove the resources owned by the fixture followed the cleanup contract.

## 18. Code Review Checklist

| Question | Required result |
| --- | --- |
| Are there mid-flight failure test cases, not just success? | Yes |
| Is framing validated on EOF? | Yes |
| Is there a MAX_FRAME_BYTES/body cap? | Yes in production |
| Does the socket listener bind loopback port 0 in CI? | Yes |
| Do accept/read have timeouts? | Yes |
| Does Future.get have a deadline and cleanup fallback? | Yes |
| Is the accepted socket closed even when the handler throws? | Yes |
| Does the client socket close after reading the response? | Yes |
| Does half-close match the protocol? | Yes |
| Is Executor.shutdown + awaitTermination used? | Yes |
| Are isTerminated and tracked worker dead verified? | Yes |
| Are accepted==closed and active==0? | Yes |
| Are injected exceptions distinguished from unexpected I/O? | Yes |
| Does it avoid relying on an exact Broken pipe string? | Yes |
| Does it avoid auto-retrying non-idempotent requests after reset? | Yes |
| Is NIO selector key/channel closure handled by the proper owner? | Yes |
| Do logs include cause, suppressed, operation, bytes, closeReason? | Yes |
| Are sensitive payloads/tokens/passwords omitted from logs? | Yes |

## 19. Common Mistakes

| Mistake | Harm | Fix |
| --- | --- | --- |
| Testing only successful echo | Failure path is unknown | Inject partial frame/handler throw |
| Ignoring readNBytes length | Silent truncation | Compare expected/actual |
| Catching EOFException and returning success | Returns partial message | Report truncated protocol error |
| Setting no timeouts | Test hangs | Accept/read/Future deadlines |
| Thinking Future.get(timeout) kills the task | Worker stays alive | Close owned resources + cancel |
| Forgetting to shut down executor | Non-daemon worker keeps JVM alive | shutdown/await/verify |
| Closing writer before reading reply | May close socket prematurely | Flush + shutdownOutput |
| Using a fixed port | Parallel CI conflicts | Port 0 |
| Binding 0.0.0.0 | Exposes fixture to LAN | Loopback |
| Using Thread.activeCount before/after | Noise from JVM threads | Custom ThreadFactory |
| Incrementing close counter before close | False PASS | Count after actual close |
| Catching IOException too broadly | Swallows unexpected errors | Marker exception for injection |
| Not bounding frame length | OOM | Validate before allocating |
| Cancelling key but keeping channel | Leak | Close channel explicitly |
| Retrying every POST on transport error | Duplicate side effects | Idempotency keys |
| Relying on Broken pipe message | Not portable | Class/phase/protocol diagnostics |
| Treating TIME_WAIT as a leak | Misdiagnosis | OS FD/handle process metrics |
| Asserting before Futures finish | False leak | Join then assert |
| Closing resources outside ownership | Races and AsynchronousCloseException | Clear single owner/lifecycle |

## 20. Self-Check Questions

**1.** Why doesn't a test receiving PONG prove the application has no leaks?  
**Answer:** It has not checked closed sockets, executor termination, and threads.

**2.** A frame declares 12 bytes, but only 5 are received before FIN; is that a success?  
**Answer:** No, this is a truncated frame.

**3.** Does readNBytes(12) automatically throw EOFException when bytes are missing?  
**Answer:** Not necessarily; it may return a short array.

**4.** How does readFully(new byte[12]) react when data is missing?  
**Answer:** Throws EOFException.

**5.** Why are loopback/port 0 useful?  
**Answer:** Internet-independent tests, fewer port conflicts, and not publicly exposed.

**6.** Does Socket.setSoTimeout create a total deadline for the request?  
**Answer:** No, only for blocking read.

**7.** Does Future.get(timeout) automatically close the Socket?  
**Answer:** No; explicit cancellation/cleanup is needed.

**8.** How does shutdown differ from awaitTermination?  
**Answer:** Shutdown stops accepting tasks; await waits for the pool to terminate.

**9.** Does shutdownNow guarantee tasks will stop?  
**Answer:** No; best effort.

**10.** Why flush and shutdownOutput before reading PONG?  
**Answer:** The server knows the client has finished sending the request, while the response direction remains open.

**11.** What can closing a BufferedWriter from a socket too early cause?  
**Answer:** Closes the entire socket, losing the response.

**12.** Do accepted=closed=12 and active=0 prove the JVM has absolutely no leaks?  
**Answer:** No; only the resources tracked by the fixture.

**13.** Why not use Thread.activeCount to assert leaks?  
**Answer:** Background JVM threads not belonging to the fixture change independently.

**14.** Is Broken pipe a fixed Java exception class?  
**Answer:** No, it is usually an OS message.

**15.** What is the risk of retrying a POST after a reset?  
**Answer:** The server may have already processed the request; retrying causes duplicate side effects.

**16.** Does SelectionKey.cancel automatically close the channel?  
**Answer:** No.

**17.** When an executor has not terminated after the deadline, what should the test do?  
**Answer:** Fail the test, run fallback cleanup, and verify the actual worker.

**18.** Does EOF mid-message always mean a TCP reset?  
**Answer:** No; it can be a graceful TCP FIN with an incomplete application frame.

## 21. Official Java SE 17 Documentation

- [ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): accept, setSoTimeout, close.
- [Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): input/output streams, shutdownOutput, close.
- [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): readFully and EOFException.
- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): readNBytes.
- [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, shutdownNow, awaitTermination.
- [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get(timeout) and cancel.
- [ThreadFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadFactory.html): worker identity.
- [SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): NIO lifecycle.
- [Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): select/wakeup/close.
- [AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): async completion/close.

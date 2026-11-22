# Identifying EOF, Connection Reset, Broken Pipe, and Channel Closure Errors in Java

When using Java Networking, a socket appearing "disconnected" is not enough to conclude the root cause. The same TCP connection can end **normally with a FIN**, be **aborted with an RST**, remain open in one direction after a **half-close**, or have its **channel closed locally** by the application while another thread is reading/writing. Those cases produce different return values and exceptions; handling them all generically as "network loss" leads to wrong retries, CPU spin, resource leaks, or data loss.

This Knowledge article belongs to **Java Advance - networking → Configuration and Observability**, focusing on signals verifiable via **`Socket`**, **`SocketChannel`**, **`AsynchronousSocketChannel`**, stack traces, Java state, and connection information.

Key takeaways:
- **`read() == -1`**: EOF, meaning the read direction has reached end-of-stream per contract. Usually caused by the peer sending a TCP FIN, but can also be caused by a **local `shutdownInput()`**.
- **`read() == 0`**: no bytes transferred on this read call (usually on a nonblocking channel or when the buffer has no remaining space); **not EOF**.
- **Connection reset**: the TCP connection was aborted/RST. In Java, you typically see `SocketException`/`IOException` with a message suggesting `Connection reset`, but the exact class/message depends on the OS, provider, and read/write timing.
- **Broken pipe**: the I/O error name commonly seen when **writing** to a connection where the other side is no longer receiving data. There is no standard Java exception type named `BrokenPipeException`; it usually surfaces as a `SocketException`.
- **`ClosedChannelException`**: I/O on a closed channel **or when the direction being operated on has been shut down**.
- **`AsynchronousCloseException`**: one thread was blocked in I/O, and another thread closed the channel/related direction.
- **`ClosedByInterruptException`**: the thread was interrupted during blocked channel I/O; the channel is closed and the interrupt flag is set.

Two things must not be inferred: **a successful write does not prove the remote application has processed the bytes**, and **`channel.isOpen() == true` does not prove the peer is still active**.

The article includes three complete Java 17+ programs that run only on `127.0.0.1` without requiring Internet access: `GracefulEofDemo.java`, `ChannelClosureDemo.java`, and `ResetProbeDemo.java`. The third program **intentionally does not assert an exact OS error message** because reset behavior is platform-dependent.

## 1. FIN, RST, and the Two Independent Directions of TCP

TCP is a **bidirectional byte stream**. When the server finishes its sending direction, it can close only its output direction with `shutdownOutput()`. The client reads the bytes that have arrived and then sees EOF, yet it can still send data in the remaining direction.

~~~text
Client                                Server
   |                                     |
   |<--------------- hello --------------|
   |<---------------- FIN ---------------| server.shutdownOutput()
   |                                     |
client.read() receives "hello"          |
client.read() => -1 (EOF)               |
   |                                     |
   |---------------- ack --------------->| server.read() still receives ack
   |---------------- FIN --------------->| client.shutdownOutput()
   |                                     |
   +-- client.close()       server.close()
~~~

**FIN** marks the end of the **sending direction** of the side that sent the FIN; it does not automatically end the opposite direction. Therefore, after reading `-1`, the application must still check whether the protocol requires sending an ACK/response instead of closing everything immediately.

**RST** is a connection reset/abort. It differs from FIN: it can cause an I/O error instead of a "clean" EOF. However, the Java message you see is also determined by the kernel, socket provider, proxy, timing, pending data, and read/write order; you must not see the word "reset" and conclude with certainty that the server process crashed.

**Local close** is a different matter. For example, if thread A calls `channel.close()`, thread B, which is blocked in a read, may receive `AsynchronousCloseException`. The peer does not need to send FIN/RST for this error to occur.

## 2. Quick Classification Table: Read/Write Results and Exceptions

| Signal | Common Operation | Sound Meaning | What It Does Not Prove |
| --- | --- | --- | --- |
| `read() == -1` | InputStream or SocketChannel read | End-of-stream of the read direction | Does not prove the entire connection is closed |
| `read() > 0` | read | Received that number of bytes | Does not prove a full message was received |
| `read() == 0` | nonblocking read or full buffer | No bytes transferred right now | Does not prove EOF/reset |
| `write() > 0` | SocketChannel write | Bytes were accepted at the write step | Does not prove the peer app committed them |
| `write() == 0` | nonblocking SocketChannel write | Could not write bytes this time | Not a Broken pipe |
| `SocketException: Connection reset` | read or write | Socket I/O failed, message suggests reset | Does not prove which endpoint emitted RST |
| `SocketException: Broken pipe` | write | Suggests the send path is broken | Not a fixed exception class |
| `ClosedChannelException` | NIO read/write | Channel/I/O direction is no longer open | Does not by itself confirm a remote error |
| `AsynchronousCloseException` | blocked NIO read/write | Closed from another thread while blocked | Not a normal async HTTP operation |
| `ClosedByInterruptException` | blocked NIO read/write | Interrupt closed the channel | Does not mean the remote closed first |
| `SocketTimeoutException` | connect/read with timeout | Wait expired for the operation | Not EOF |
| `ConnectException: Connection refused` | connect | Could not connect to endpoint | Not an established connection that just hit EOF |
| `NotYetConnectedException` | NIO read/write before connect | Wrong channel lifecycle | Not a connection reset |
| `CancelledKeyException` | SelectionKey operations | Key is no longer valid | Says nothing by itself about peer TCP |

Classify by **operation + return value + exception class + application state**, and only then use the OS error message for additional context. Do not treat a piece of exception text as a stable protocol code.

## 3. EOF: -1 Is End-of-Stream, Not Empty Data

For `SocketChannel.read(ByteBuffer dst)`, the return value is interpreted as:
- **`n > 0`**: received `n` bytes, which may only be the first fragment of a message.
- **`n == 0`**: no bytes transferred into the buffer in this call. In nonblocking mode when no data is available, this is a normal result. When `dst.remaining() == 0`, the buffer also has no space to hold bytes.
- **`n == -1`**: reached end-of-stream (EOF), no more data on the read direction.

For the no-argument `InputStream.read()`, **`0` is a valid NUL byte value**, whereas `-1` indicates EOF. Do not conflate the single-byte read overload with `SocketChannel.read` returning a byte count.

Correct read example (snippet):

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8192);
while (true) {
    buffer.clear();
    int n = channel.read(buffer);

    if (n == -1) {
        onEof();                 // Read reached EOF.
        break;
    }
    if (n == 0) {
        // For nonblocking: wait for Selector readiness,
        // DO NOT spin infinitely here.
        continue;
    }

    buffer.flip();
    consumeBytes(buffer);        // Parser handles partial frames.
}
~~~

This is a **snippet**; `channel/onEof/consumeBytes` need to be implemented. With a blocking channel and remaining space in the buffer, a read normally blocks waiting for at least one byte, EOF, or an error. With a nonblocking channel, you must coordinate via `Selector.OP_READ` instead of a CPU-busy `while(n == 0)` loop.

### EOF Differs from Message End

TCP does not attach message boundaries. A peer sending 100 bytes may cause the client to receive 30, 50, and then 20 bytes across three reads. If a frame declares `Content-Length: 100` or a length-prefix of 100, and EOF occurs after receiving only 40 bytes, that is a **truncated application message** even though TCP ended with a normal FIN.

Therefore, the app must have a protocol framing rule:
- Length-prefix: read the full byte count before completing the message.
- Delimiter: accumulate until the delimiter; EOF before the delimiter may be an error.
- EOF-delimited: EOF itself is the way the body ends; apply a byte limit so it does not read indefinitely.
- Fixed header/body: parse state by state, transitioning state only when enough bytes have arrived.

**Do not turn every EOF into success**. A request that hits EOF at an unexpected point should report `UNEXPECTED_EOF/TRUNCATED_FRAME` according to the protocol.

## 4. shutdownOutput and shutdownInput Are Not the Same as close

`SocketChannel.shutdownOutput()` closes the **sending** half. Per Java 17, subsequent `write` calls throw `ClosedChannelException`; the reading direction can still continue.

~~~java
channel.shutdownOutput();
boolean open = channel.isOpen(); // May still be true.
// channel.write(...) after this will not be allowed.
~~~

`SocketChannel.shutdownInput()` closes the **receiving** half, causing subsequent reads to return `-1` per contract:

~~~java
channel.shutdownInput();
int n = channel.read(ByteBuffer.allocate(8)); // EOF: -1.
~~~

**Specifically:** `read()==-1` can come from a **local `shutdownInput` itself**, not necessarily a remote FIN. If you need to investigate, log local lifecycle events rather than logging only EOF.

`close()` closes the entire channel and disallows new I/O. `shutdownOutput()` and `shutdownInput()` can leave half a connection open; do not use them when the application protocol does not allow half-close.

| Operation | Effect | Notes |
| --- | --- | --- |
| `shutdownOutput()` | Stops sending; signals to the peer that no more bytes will be sent per TCP | Can continue reading |
| `shutdownInput()` | Stops receiving locally; subsequent reads return EOF | Does not prove the remote actively closed |
| `close()` | Closes the entire channel | Cannot reopen the same object |
| Peer sends FIN | Ends the peer→local direction | The local→peer direction may still send |
| Peer sends RST | Connection is aborted | Read/write may report IOException |

## 5. Runnable Example 1 — EOF While Still Able to Send in the Opposite Direction

**`GracefulEofDemo.java`** has the server send `hello` and then call `shutdownOutput()`. The client reads until EOF, sees the channel is still open, and sends `ack`. The server reads `ack` before the client shuts down its sending direction. This is a direct demonstration that **EOF does not mean full close**.

Create the file **`GracefulEofDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class GracefulEofDemo {
    static String readAll(SocketChannel ch) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ByteBuffer buffer = ByteBuffer.allocate(4);

        while (true) {
            buffer.clear();
            int n = ch.read(buffer);
            if (n == -1) break;
            if (n == 0) continue;

            buffer.flip();
            byte[] bytes = new byte[buffer.remaining()];
            buffer.get(bytes);
            out.write(bytes);
        }
        return out.toString(StandardCharsets.UTF_8);
    }

    static void writeAll(SocketChannel ch, String text)
            throws IOException {
        ByteBuffer buffer = StandardCharsets.UTF_8.encode(text);
        while (buffer.hasRemaining()) {
            ch.write(buffer);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getByName("127.0.0.1"), 0));

            Future<String> serverResult = worker.submit(() -> {
                try (SocketChannel peer = listener.accept()) {
                    writeAll(peer, "hello");
                    peer.shutdownOutput();
                    return readAll(peer);
                }
            });

            try (SocketChannel client =
                    SocketChannel.open(listener.getLocalAddress())) {
                String received = readAll(client);
                System.out.println("Client received: " + received);
                System.out.println("Peer EOF after FIN: "
                        + received.equals("hello"));
                System.out.println("Channel still open: "
                        + client.isOpen());

                writeAll(client, "ack");
                client.shutdownOutput();
                System.out.println(
                        "Server read after peer half-close: "
                        + serverResult.get(3, TimeUnit.SECONDS));
            }
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 GracefulEofDemo.java
java GracefulEofDemo
~~~

**Tested output on localhost:**

~~~text
Client received: hello
Peer EOF after FIN: true
Channel still open: true
Server read after peer half-close: ack
~~~

**Explanation:**
1. The server writes all bytes and then calls `shutdownOutput`, so the client will hit EOF once it has read all of `hello`.
2. The client channel remains open because the client itself has not called `close()`.
3. The client still sends `ack`, and the server can still read it on the opposite direction.
4. The program uses a 4-byte buffer, so it must collect chunks to form a String. This is a **small test**; for large data, bounded parsing is required instead of reading unboundedly into a `ByteArrayOutputStream`.
5. The `Future.get(3,SECONDS)` calls only guard the wait time of the test; they do not automatically create a total TCP deadline for all blocking operations.

## 6. Connection Reset: TCP RST Differs from FIN

**RST** is a form of TCP abort/reset. Java has no standard exception class named `ConnectionResetException`. On many platforms, `read/write` operations may throw:

~~~text
java.net.SocketException: Connection reset
java.net.SocketException: Connection reset by peer
java.io.IOException: An existing connection was forcibly closed ...
~~~

These strings are **examples** from different environments, not mandatory Java 17 output. There are many sources of a reset:
- The peer closes the socket abortively, possibly due to `SO_LINGER=0`.
- A process or proxy closes the connection abnormally.
- A load balancer, middlebox, firewall, or OS tears down the connection by policy.
- A protocol error or invalid TCP state.
- A remote process crash is **one possibility**, not the only conclusion.

RST can be detected on **read** or on **write**, and some bytes may already have been accepted/sent before the exception appears. Do not infer that the server definitely has not processed the request.

**What to do after a reset?** Stop using that socket/channel, clean up connection state, and record the exception class, operation, bytes/phase, and timestamp. If a retry is needed, create a new connection and apply an idempotency policy, retry budget, and backoff. Do not blindly retry a transaction with side effects.

## 7. Broken Pipe: Usually Appears on the Write Direction

`Broken pipe` is typically the message attached to an OS error such as `EPIPE` when **writing to a transport path that is no longer available**. Java usually surfaces this error under `SocketException` or `IOException` rather than having a dedicated checked exception type named `BrokenPipeException`.

Inferences to avoid:
- After a **FIN** from the peer, it has only stopped **sending**; the peer may still be receiving data. Writing after FIN is **not necessarily** a broken pipe.
- If the peer has already performed a full close or sent RST, subsequent writes may fail. The OS may return `Connection reset` or `Broken pipe` depending on timing.
- An initial `write` call may succeed because the local kernel accepted the bytes; the error only surfaces on a later read/write.
- If you **yourself** call `SocketChannel.shutdownOutput()`, the next write may throw `ClosedChannelException` even though `isOpen()==true`.
- If you **yourself** call `SocketChannel.close()`, the next write usually reports `ClosedChannelException`, with no reason to blame the peer.

**Do not retry writes on the same broken channel.** For a TCP stream, a failed channel does not recover on its own. Create a new connection if business rules permit, while remembering that **write success is not an application acknowledgment**.

## 8. The ClosedChannelException Hierarchy in Java NIO

From the Java 17 Javadoc:

~~~text
IOException
└── ClosedChannelException
    └── AsynchronousCloseException
        └── ClosedByInterruptException
~~~

The three key classes have the inheritance relationship above, so the **catch order** must go from the specific subtype to the superclass.

~~~java
try {
    channel.read(buffer);
} catch (ClosedByInterruptException ex) {
    // Thread blocked in I/O was interrupted, channel is closed.
    Thread.currentThread().interrupt();
} catch (AsynchronousCloseException ex) {
    // Another thread closed the channel/direction while blocked.
} catch (ClosedChannelException ex) {
    // Channel or I/O direction was already closed before the operation.
} catch (IOException ex) {
    // Other network/transport errors.
}
~~~

This is a snippet: `channel`/`buffer` are not declared. If `ClosedChannelException` is caught first, the specific catch blocks that follow become unreachable.

### 8.1. ClosedChannelException

Does not necessarily mean the channel is *completely* closed. The Javadoc explicitly states that I/O on a closed channel **or at least when the direction being operated on is no longer open** can throw this class. For example, `shutdownOutput` followed by `write` throws it, while `read` still works.

### 8.2. AsynchronousCloseException

If thread A is blocked in `SocketChannel.read()`, and thread B calls `channel.close()`, the blocked operation may end with `AsynchronousCloseException`. This is a **concurrent lifecycle** error, not evidence of a remote reset.

### 8.3. ClosedByInterruptException

If thread A is `interrupt()`ed while blocked in channel I/O, the JDK closes the channel, sets the interrupt flag, and throws `ClosedByInterruptException`. Do not treat it like a generic `InterruptedException` and ignore the channel state; **do not reuse this channel**.

### 8.4. isOpen() Is Not a Remote Health Check

`isOpen()` only indicates that the channel object has not been completely closed. The peer may have sent a FIN, an unprocessed RST may be pending, or the local channel may have shut down one direction. Only the application protocol, heartbeats, real read/write operations, metadata, and proper acknowledgments can help assess remote state.

## 9. Runnable Example 2 — Local Close, Close from Another Thread, and Interrupt

The program **`ChannelClosureDemo.java`** demonstrates:
1. `shutdownOutput()` causes write to throw `ClosedChannelException` while the channel remains open.
2. `close()` on the whole channel causes a new read to throw `ClosedChannelException`.
3. One thread blocked in `read()`, another thread closes the channel: `AsynchronousCloseException`.
4. Interrupting a thread blocked in read: `ClosedByInterruptException`, interrupt flag true, channel closed.

Create the file **`ChannelClosureDemo.java`**:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousCloseException;
import java.nio.channels.ClosedByInterruptException;
import java.nio.channels.ClosedChannelException;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ChannelClosureDemo {
    static void localCloseAndHalfClose() throws Exception {
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getByName("127.0.0.1"), 0));

            try (SocketChannel client =
                         SocketChannel.open(listener.getLocalAddress());
                 SocketChannel peer = listener.accept()) {
                client.shutdownOutput();

                boolean halfClosed = false;
                try {
                    client.write(ByteBuffer.wrap(new byte[]{1}));
                } catch (ClosedChannelException expected) {
                    halfClosed = true;
                }
                System.out.println(
                        "Write after shutdownOutput: " + halfClosed);
                System.out.println(
                        "Open after shutdownOutput: " + client.isOpen());

                client.close();
                boolean closedRead = false;
                try {
                    client.read(ByteBuffer.allocate(1));
                } catch (ClosedChannelException expected) {
                    closedRead = true;
                }
                System.out.println("Read after close: " + closedRead);
            }
        }
    }

    static void blockedRead(boolean interrupt) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getByName("127.0.0.1"), 0));

            try (SocketChannel client =
                         SocketChannel.open(listener.getLocalAddress());
                 SocketChannel peer = listener.accept()) {

                CountDownLatch started = new CountDownLatch(1);
                AtomicReference<Thread> readerThread =
                        new AtomicReference<>();

                Future<String> result = worker.submit(() -> {
                    readerThread.set(Thread.currentThread());
                    started.countDown();
                    try {
                        int n = client.read(ByteBuffer.allocate(1));
                        return "read=" + n;
                    } catch (ClosedByInterruptException ex) {
                        return "ClosedByInterruptException|interrupt="
                                + Thread.currentThread().isInterrupted();
                    } catch (AsynchronousCloseException ex) {
                        return "AsynchronousCloseException";
                    } catch (IOException ex) {
                        return ex.getClass().getSimpleName();
                    }
                });

                if (!started.await(3, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Reader not started");
                }
                Thread.sleep(100); // Allow time for read to block.

                if (interrupt) {
                    readerThread.get().interrupt();
                } else {
                    client.close();
                }

                String observed = result.get(3, TimeUnit.SECONDS);
                System.out.println(
                        (interrupt ? "Interrupt blocked read: "
                                   : "Close blocked read: ") + observed);
                System.out.println(
                        "Channel open afterward: " + client.isOpen());
            }
        } finally {
            worker.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        localCloseAndHalfClose();
        blockedRead(false);
        blockedRead(true);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ChannelClosureDemo.java
java ChannelClosureDemo
~~~

**Tested stdout on JDK with blocking NIO SocketChannel:**

~~~text
Write after shutdownOutput: true
Open after shutdownOutput: true
Read after close: true
Close blocked read: AsynchronousCloseException
Channel open afterward: false
Interrupt blocked read: ClosedByInterruptException|interrupt=true
Channel open afterward: false
~~~

**Meaning:** These are **local** close/interrupt effects, not remote RST. The `Thread.sleep(100)` only helps the worker enter the blocked read; on a machine with an extremely unusual scheduler, there could be a race before the read actually blocks. Therefore, if timing differs, inspect the actual exception and still rely on the Javadoc contract rather than hard-coding the output across all environments.

If the service is shutting down, `AsynchronousCloseException` may be an expected event. Log `closeReason=shutdown` to avoid treating every close during shutdown as an incident.

## 10. Using SO_LINGER(0) to Observe Reset, Not to Fix Errors

A peer can enable `Socket.setSoLinger(true, 0)` and then close to request an abortive close. Many OSes will send a TCP RST, though timing/messages from the socket API are not guaranteed to be identical across all systems.

**Use this technique only in localhost tests**. Setting SO_LINGER=0 in production is not a way to "fix Broken pipe," because it can discard unsent/in-flight data and cause a reset for the peer.

## 11. Runnable Example 3 — Observing OS-Dependent Reset

Create the file **`ResetProbeDemo.java`**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ResetProbeDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();

        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {

            Future<?> server = worker.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoLinger(true, 0);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            });

            try (Socket client = new Socket(
                    "127.0.0.1", listener.getLocalPort())) {
                server.get(3, TimeUnit.SECONDS);
                try {
                    int value = client.getInputStream().read();
                    System.out.println(
                            "Observed read result: " + value);
                } catch (IOException error) {
                    System.out.println("Observed read exception: "
                            + error.getClass().getSimpleName());
                    System.out.println(
                            "OS message: " + error.getMessage());
                }
            }
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ResetProbeDemo.java
java ResetProbeDemo
~~~

**One observed result on a Windows/JDK test machine:**

~~~text
Observed read exception: SocketException
OS message: Connection reset
~~~

**Do not assert this stdout across all OSes.** Under other conditions, the message/class or result may differ. The program intentionally prints the observed event. If you want to distinguish actual TCP FIN/RST on the wire, use packet capture/OS TCP counters in an authorized environment and correlate both sides.

**Why not create a Broken pipe demo that always prints that exact text?** On some OSes, a write after remote shutdown may return `Connection reset`; on other OSes, it may accept the write and only fail on the next call or report `Broken pipe`. Enforcing a fixed stdout would falsely teach that this message is a Java API contract.

## 12. Classifying Local Close with instanceof Instead of OS Messages

If you need to reliably distinguish the **local NIO channel lifecycle** error group, use the exception hierarchy:

~~~java
static String classify(IOException e) {
    if (e instanceof ClosedByInterruptException) {
        return "LOCAL_INTERRUPT";
    }
    if (e instanceof AsynchronousCloseException) {
        return "LOCAL_CONCURRENT_CLOSE";
    }
    if (e instanceof ClosedChannelException) {
        return "LOCAL_CHANNEL_CLOSED_OR_HALF_CLOSED";
    }
    if (e instanceof SocketTimeoutException) {
        return "TIMEOUT";
    }
    if (e instanceof SocketException) {
        return "SOCKET_ERROR_NEEDS_MORE_CONTEXT";
    }
    return "OTHER_IO_ERROR";
}
~~~

This is a snippet; it requires imports for `java.io.IOException`, `java.net.SocketException`/`SocketTimeoutException`, and `java.nio.channels.*`.

**Do not write business logic like:**

~~~java
// ANTI-PATTERN: error message can be null and is not portable.
if (error.getMessage().contains("Broken pipe")) {
    retryPaymentImmediately();
}
~~~

Aside from the unstable message, retrying a payment can cause double-processing. Instead, classify by `operation`, `exception class`, `application request ID`, `bytes transferred`, and idempotency policy.

EOF is a **return value** of `-1`, not an `IOException`, so it does not belong to the helper above.

## 13. Selector and Nonblocking SocketChannel

In `SocketChannel.configureBlocking(false)`:
- `read()==0` when no bytes are ready is normal.
- When the peer has ended its sending direction, readiness may trigger continuously; read returns `-1`.
- If EOF is not handled by transitioning state/canceling the key, the selector loop can spin CPU indefinitely.
- `SelectionKey.OP_READ` does not itself carry "peer FIN" information; you must call `read` to determine it.
- `CancelledKeyException` is a selection key lifecycle error; `ClosedSelectorException` means the selector is closed, not a TCP reset.

A snippet handling one event:

~~~java
try {
    int n = channel.read(buffer);

    if (n == -1) {
        key.cancel();
        channel.close(); // Only if the protocol does not need half-close.
        return;
    }
    if (n == 0) {
        return;           // Yield to the event loop, do not spin.
    }

    buffer.flip();
    parseAvailableBytes(buffer);
    buffer.compact();
} catch (IOException ex) {
    key.cancel();
    channel.close();
    recordTransportFailure(ex);
}
~~~

This snippet assumes `channel/key/buffer` are valid and helpers are defined. For protocols that need to send a response after receiving FIN, manage **half-close state** instead of closing the entire channel on EOF.

**Do not discard an incomplete buffer:** TCP can deliver partial frames. Use `flip/compact` properly to retain remaining bytes for the next read.

## 14. AsynchronousSocketChannel: completed(-1) and failed(Throwable)

With `AsynchronousSocketChannel`, the Future or `CompletionHandler` API represents I/O completion.

~~~java
channel.read(buffer, null,
        new CompletionHandler<Integer, Void>() {
            @Override
            public void completed(Integer n, Void unused) {
                if (n == -1) {
                    onEof();
                    return;
                }
                if (n == 0) {
                    // Not EOF; manage re-arm according to state.
                    return;
                }
                onBytes(n);
            }

            @Override
            public void failed(Throwable error, Void unused) {
                recordFailure(error);
            }
        });
~~~

This is a snippet; `channel/buffer/onEof/onBytes/recordFailure` must be defined, and it does not constitute a complete parser on its own. **`completed(-1)` differs from `failed(IOException)`**. When using `Future<Integer>`, exceptional completion usually appears via `ExecutionException` from `get()`; inspect `getCause()` for the actual exception.

Do not assume that interrupting an arbitrary thread will cancel a specific submitted async read operation. With async channels, manage the Future, `CompletionHandler.failed`, channel close, and completion ownership.

According to the `AsynchronousSocketChannel.shutdownInput()` Javadoc, **subsequent reads** after shutting down input will see EOF; **the effect on a pending read is system dependent**. If a read has a timeout, `InterruptedByTimeoutException` may occur; when the provider cannot guarantee the buffer will not be accessed, continuing to use the channel/buffer must obey the restrictions in the contract.

## 15. Logging: What Information Helps Identify the Error Source?

In operations, log an event with sufficient context:

~~~text
time=2026-11-01T09:00:00Z
connectionId=conn-381
requestId=req-19
operation=read
phase=response-body
remote=api.example:443
local=service-host:ephemeral-port
blockingMode=true
bytesReceived=4096
expectedFrameBytes=8192
exceptionClass=java.net.SocketException
exceptionMessage="Connection reset"
lastLocalCloseReason=none
retryAttempt=0
~~~

This is an **illustrative log sample**, not demo output or real logs. Do not include bearer tokens, cookies, passwords, or sensitive data in logs. Addresses and request identifiers must also comply with telemetry access permissions.

Useful fields:
- Direction: connect/read/write, whether in request or response phase.
- Exception **class** + root cause + message.
- Local close/interrupt/shutdown history.
- Bytes read/written and protocol frame progress.
- Local/remote addresses recorded before the channel is closed (after close, querying addresses may fail).
- Connection ID, request ID, endpoint, retry attempt.
- OS/JDK/provider/version and deployment timestamp.
- Whether actual FIN/RST appeared in packet captures or counters, if permitted to observe.

**Do not conclude a remote cause from client logs alone.** Combine server logs, proxy/load balancer, firewall, OS telemetry, and packet captures (when authorized). A broken pipe on the server may be caused by the client abandoning the response on timeout, not necessarily by faulty server business processing.

## 16. Distinguishing Transport Errors from Application Protocol Errors

A few examples:
- Client expects 100 bytes, receives 40 bytes then EOF → **truncated frame** at the application protocol layer.
- Server sends the full response, client closes its sending direction with FIN → may be successful.
- Server is writing the response, client times out and closes → server may hit broken pipe/reset, while the database transaction may already have committed.
- Reader is closed by a management thread during shutdown → `AsynchronousCloseException`, **expected cancellation** if anticipated by the design.
- Worker thread is `interrupt()`ed due to cancellation → `ClosedByInterruptException`, should not automatically be blamed on the remote.
- TCP RST before returning a response to a POST → unknown whether the POST executed, requiring an idempotency key/status endpoint.

**The application protocol must decide success or failure.** A `SocketChannel.write()==n` call only confirms the number of bytes accepted at the write step; it is not a guarantee that the receiver parsed, validated, persisted to the database, or returned a business ACK.

## 17. Timeouts, Retries, and Idempotency

| Event | Typically Appropriate Handling |
| --- | --- |
| EOF right at end of message | End reader/half-close per protocol |
| EOF mid-message | Report truncated error, do not parse partial as full message |
| Reset during read of idempotent GET | Clean up, bounded retry with backoff if deadline remains |
| Broken pipe while sending POST | Do not conclude request never reached server; need idempotency key/status query |
| ClosedChannelException from local close | Fix lifecycle/race; open a new channel if policy requires |
| AsynchronousCloseException from shutdown | Clean up as intentional cancellation |
| ClosedByInterruptException from cancel | Preserve interrupt state; do not reuse channel |
| SocketTimeoutException | Classify as timeout, do not treat as EOF; retry per operation/contract |
| Connect refused | Backoff/new connection, check service/port; not an established peer reset |

**Do not retry on a closed/broken channel.** Create a new connection if retry is permitted. For operations with side effects, if the server already processed the request but the response was lost, retrying can create duplicate data/transactions. Use idempotency keys, request IDs, and reconciliation/status queries when the API supports them.

You can apply exponential backoff + jitter, retry count limits, total deadlines, concurrency limits, and circuit breakers. Do not turn a reset storm into a retry storm.

## 18. Cleanup and Single Lifecycle Owner

When multiple threads share a single channel, one thread closing the resource while another is reading can produce "unexpected" exceptions. The design should have a clear state machine and close owner:

~~~text
NEW -> CONNECTING -> OPEN
                       |
             +---------+---------+
             |                   |
       HALF_CLOSED_IN      HALF_CLOSED_OUT
             |                   |
             +---------+---------+
                       |
                    CLOSING
                       |
                     CLOSED
~~~

This is an **app model**, not a default Java enum. Record the close reason before closing (`normal EOF`, `shutdown`, `timeout`, `protocol violation`, `peer failure`) so callbacks/logs can distinguish expected from unexpected closures.

Recommendations:
- Use try-with-resources when owning `Socket/SocketChannel/ServerSocketChannel`.
- Do not let multiple owners arbitrarily call `close` and continue writing on that connection.
- Stop the send queue, and complete Futures/pending writes with a clear error.
- With Selector, cancel/deregister the key and clean up the connection map.
- With async channels, coordinate completion handlers and close, and do not let stale ByteBuffers be written again.
- Do not log stack traces thousands of times for expected shutdowns.
- Upon reset/broken pipe, close/deregister and create a new connection per retry policy; do not keep a failed channel in the pool.

## 19. Incident Diagnosis Runbook

When you see an error:
1. **Identify the operation:** connect, read, write, selector, close, or callback.
2. **Read the return value:** `-1`, `0`, or positive bytes; do not ignore the number of bytes received before the error.
3. **Classify the exception:** class first, cause chain second, message last.
4. **Look for local close events:** did another thread call close? Was there shutdownInput/Output, interrupt, cancellation, or timeout?
5. **Cross-check protocol state:** did EOF happen right after the expected bytes/frame, or mid-message?
6. **Cross-check the peer:** server/proxy/LB logs by connection ID/timestamp.
7. **Check TCP evidence:** If needed and permitted, use packet capture to confirm FIN/RST instead of guessing from the message.
8. **Account for side effects:** DB transactions, request commits, or peer processing may have already occurred even if the client did not receive the response.
9. **Cleanup:** keys/channels/streams/futures according to ownership, avoiding double-close side effects or retries on the old channel.
10. **Improve metrics:** expected/unexpected EOF, reset-per-operation, local-close reasons, latency, queue depths, retry attempts, and bytes transferred.

Do not rely solely on `isOpen`, `SocketException.getMessage`, or the moment a thread unblocks to assert the root cause.

## 20. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `read()==0` as EOF | Closing nonblocking socket prematurely | Only `-1` is end-of-stream |
| Treating EOF as full close | Losing ability to send final response | Manage half-close |
| Not checking framing on EOF | Receiving partial message | Validate length/delimiter |
| Assuming one `read` receives the whole message | Mis-parsing TCP stream | Loop/accumulate ByteBuffer |
| Spinning when nonblocking read returns 0 | High CPU | Selector readiness/event loop |
| Calling write after `shutdownOutput()` | ClosedChannelException | Do not use closed write direction |
| Using `isOpen()` as remote health check | Missing FIN/RST | App heartbeat/real I/O |
| Treating `Broken pipe` as a Java exception type | Won't compile/wrong catch | Catch IOException/SocketException |
| Hardcoding `"Connection reset"` message | Not portable | Class + OS metadata |
| Attributing every `ClosedChannelException` to remote | Misdiagnosing local race | Trace local shutdown/close |
| Catching `ClosedChannelException` before subtypes | Subtype catches unreachable | Catch specific first |
| Reusing SocketChannel after interrupt | I/O on closed channel | Create new channel, preserve interrupt flag |
| Treating write success as business success | Double-processing/wrong retry | Acknowledgment/idempotency |
| Retrying every Broken pipe immediately on POST | Risk of duplicate processing | Idempotency keys/status lookup |
| Setting SO_LINGER=0 for "quick cleanup" | RST/lost bytes | Graceful close per protocol |
| Forgetting to cancel SelectionKey after EOF | Selector busy loop | Cancel key or change state |
| Forgetting to close stream/future | Resource leak | Terminal cleanup |
| Swallowing all IOExceptions as null | Losing root cause | Preserve cause/context |
| Not distinguishing timeout vs EOF | Wrong logic | Timeout is a separate exception |
| Logging raw secrets/payloads | Data leak | Redact/sanitize logs |

## 21. Self-Check Exercises

**1.** What does `SocketChannel.read(ByteBuffer)` returning `-1` indicate?  
**Answer:** End-of-stream on the read direction; usually caused by peer FIN, though local shutdownInput also produces EOF.

**2.** Does a nonblocking read returning `0` mean the connection is closed?  
**Answer:** No. No bytes were transferred this time; wait for readiness or check the buffer.

**3.** After the client reads EOF from the peer, can the client still write?  
**Answer:** Possibly yes, because the peer only closed its sending direction; the client's sending direction may still be valid.

**4.** Does `InputStream.read()` returning `0` mean there are no bytes?  
**Answer:** No; for the single-byte read overload, 0 is the NUL byte, while -1 is EOF.

**5.** Is EOF after 40 bytes of a frame declaring 100 bytes a success?  
**Answer:** No. That is a truncated application frame.

**6.** Does `Connection reset` prove the remote server crashed?  
**Answer:** No. RST can involve the OS, proxy, middlebox, abortive close, or other errors.

**7.** Is `Broken pipe` a separate class in Java 17?  
**Answer:** No; it is typically an OS message accompanying SocketException/IOException on write.

**8.** Why does writing after `shutdownOutput()` throw ClosedChannelException while isOpen remains true?  
**Answer:** Because one I/O direction can be shut down without closing the entire channel.

**9.** How does `AsynchronousCloseException` differ from `ClosedByInterruptException`?  
**Answer:** One is caused by another thread closing a blocked channel; the other is caused by the blocked thread itself being interrupted, closing the channel and setting the interrupt flag.

**10.** What is the catch order for the three local exceptions?  
**Answer:** ClosedByInterruptException → AsynchronousCloseException → ClosedChannelException.

**11.** Does `SocketChannel.write()==100` prove the server committed to the DB?  
**Answer:** No. You need a protocol/application acknowledgment or status query.

**12.** Why not assert that every OS prints `"Broken pipe"` after a remote close?  
**Answer:** The error and message depend on timing, TCP state, and OS/provider.

**13.** Should SO_LINGER=0 be used as the default close behavior?  
**Answer:** No. It can cause an abortive close/RST and data loss.

**14.** Why can mishandling EOF in a Selector cause high CPU?  
**Answer:** Read readiness can repeat on EOF; you must cancel/deregister/change state.

**15.** Are `AsynchronousSocketChannel.completed(-1)` and `failed(IOException)` the same?  
**Answer:** No. One is an EOF result, and the other is an I/O failure.

**16.** When seeing ClosedChannelException while the service is shutting down, what should you check?  
**Answer:** Local owner/close reason, thread/cancel lifecycle, and pending operations before blaming the remote.

**17.** Is `SocketTimeoutException` an EOF?  
**Answer:** No. A timeout means no bytes arrived within the time limit, not that the connection closed.

**18.** Why can retrying a POST after a reset be dangerous?  
**Answer:** The remote may have already processed the request while the response was lost; idempotency is needed.

## 22. Official Java SE 17 References

- [SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): read -1/0, shutdownInput/Output, local close, and I/O exceptions.
- [Channel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Channel.html): isOpen/close and lifecycle.
- [ClosedChannelException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedChannelException.html): I/O on a closed channel or direction.
- [AsynchronousCloseException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousCloseException.html): blocked I/O closed from another thread.
- [ClosedByInterruptException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedByInterruptException.html): interrupting blocked I/O closes the channel.
- [AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): Future/CompletionHandler EOF and failure/timeout.
- [Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): shutdownInput/Output, setSoLinger, close.
- [SocketException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketException.html): socket I/O errors.
- [SocketTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html): I/O timeout semantics.
- [StandardSocketOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): SO_LINGER, SO_KEEPALIVE, TCP_NODELAY.
- [Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): readiness and selection keys.
- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): EOF return value -1.

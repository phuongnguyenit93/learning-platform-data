# Distinguishing Selector I/O Readiness from Asynchronous I/O Completion

## 1. Goals and Core Intuition

In Java networking, the two phrases **I/O readiness** and **I/O completion** are often both referred to briefly as “non-blocking” or “asynchronous”. They solve the same problem of avoiding keeping a thread blocked for a long time per connection, but they notify **two different kinds of events**:

- **`Selector` — readiness:** notifies that a channel **appears ready** for a type of operation (read, write, accept, connect). After the notification, **the program must still call** `SocketChannel.read(...)`, `write(...)`, or `ServerSocketChannel.accept()` itself and check the actual result.
- **`AsynchronousSocketChannel` — completion:** the program **initiates an operation** `read(...)`, `write(...)`, or `connect(...)`, and then receives **the result of that exact operation** via a `CompletionHandler` or `Future` when the operation finishes (success, EOF, or failure).

**Key takeaway:** *readiness = “you can try I/O now”; completion = “the requested I/O operation has a result”.* Neither of them **automatically assembles bytes into a complete application message**.

This lesson focuses on Java 17+ TCP/NIO, `Selector`, `SelectionKey`, `SocketChannel`, `AsynchronousSocketChannel`, and `ByteBuffer`. The examples run over TCP loopback so no Internet server is needed.

## 2. The Readiness Mechanism: Selector, Non-Blocking Channels, and SelectionKey

`java.nio.channels.Selector` manages multiple `SelectableChannel`s (for example `ServerSocketChannel`, `SocketChannel`). A channel must be switched to non-blocking mode before registering:

~~~java
channel.configureBlocking(false);
SelectionKey key = channel.register(selector, SelectionKey.OP_READ);
~~~

*This is an illustrative snippet within a program that has already initialized `channel`/`selector`; it is not yet a standalone runnable program.*

A `SelectionKey` has an **interest set** (`interestOps()`) representing the operations to monitor, and a **ready set** (`readyOps()`) representing the operations detected as ready. The main bits are:

| Bit | Typical Channel | What does it notify? | What must be done next? |
| --- | --- | --- | --- |
| `OP_ACCEPT` | `ServerSocketChannel` | There may be a connection waiting | Call `accept()` and handle the result (`null` can occur in non-blocking mode) |
| `OP_CONNECT` | `SocketChannel` | Non-blocking connect may have finished or failed | Call `finishConnect()`, do not assume it is already connected |
| `OP_READ` | `SocketChannel` | Readable, or EOF/error | Call `read(ByteBuffer)`, check `n > 0`/`0`/`-1` |
| `OP_WRITE` | `SocketChannel` | Writable, or a related status/error | Call `write(ByteBuffer)`, check the actual number of bytes written |

`selector.select()` or `selector.select(timeout)` queries the operating system for readiness, updates the selected-key set, and may block while waiting. **Selector does not automatically copy any bytes into a ByteBuffer.** To obtain the payload, the application itself must call `read`.

The reliability of the ready set also has limits: the `SelectionKey` documentation treats it as a **hint**, not a guarantee that the operation will transfer data. Data may be read by another thread or the channel state may change between `select` and `read`.

### selectedKeys Is Not keys

- `selector.keys()`: all registered keys, including those not yet ready.
- `selector.selectedKeys()`: keys just reported ready by the selector or still remaining in the selected-key set.
- In the loop processing `selectedKeys()`, `Iterator.remove()` is typically used **after retrieving a key**, otherwise old events are easily reprocessed.
- Before processing a key that may have been closed/canceled, check `key.isValid()`.

**Do not register `OP_WRITE` permanently.** A socket is usually writable most of the time; the event loop may wake up continuously and burn CPU. Only enable `OP_WRITE` when there is actually data remaining in the output queue; clear that bit when writing is finished.

## 3. A Ready Event Does Not Mean a Read Has Completed

Consider the steps:

~~~text
1. socket.configureBlocking(false)
2. socket.register(selector, OP_READ)
3. selector.select()         -> returns a readable key
4. key.isReadable() == true  -> READINESS, no data read yet
5. int n = socket.read(dst)  -> the program itself invokes I/O
6. n > 0 / n == 0 / n == -1  -> the actual I/O result
7. process bytes or wait for another ready turn if the message is incomplete
~~~

`SocketChannel.read(ByteBuffer)` can return:

- `n > 0`: `n` bytes were written into the buffer. This byte count **is not necessarily enough** for a full message or needed header.
- `n == 0`: the current read transferred no bytes; this may be because the buffer has no `remaining()` left or the readiness state changed. Do not treat this as EOF.
- `n == -1`: end of stream (EOF), meaning the peer closed its write side/connection in the appropriate state; do not keep waiting for the rest of a partial frame.
- Exception: an I/O error that needs to be caught and handled by closing/recovering the connection according to policy.

`OP_READ` can be signaled when **EOF or an error is pending**, not only when payload bytes are available. `OP_CONNECT` can similarly be signaled even if the connect result is a failure. You must use `finishConnect()` to know for sure.

`selector.select(timeout)` is only **the time limit for one readiness wait turn**, not an operation completion deadline or the maximum time for an entire request. A single `select` call can return 0 due to timeout, `wakeup()`, or other valid conditions; you need to manage the overall deadline using monotonic time and connection state, rather than concluding “no keys = all I/O failed”.

## 4. The Completion Mechanism: Issue the I/O Operation First, Receive the Result Later

`AsynchronousSocketChannel` and `AsynchronousServerSocketChannel` belong to the asynchronous channel API family. `AsynchronousSocketChannel.read(...)` actually **initiates** a read operation on the channel, and `CompletionHandler` notifies the result after this operation finishes:

~~~java
channel.read(buffer, null, new CompletionHandler<Integer, Void>() {
    @Override
    public void completed(Integer count, Void attachment) {
        // The read operation has finished: count bytes transferred, 0, or -1 (EOF).
    }
    @Override
    public void failed(Throwable error, Void attachment) {
        // The read operation failed: handle the error for this specific operation.
    }
});
~~~

*Illustrative snippet, not a standalone program because the `channel`/`buffer` variables and imports are provided by the application.*

We also have the **Future** variant:

~~~java
Future<Integer> operation = channel.read(buffer);
// Cannot use the buffer yet as if the read were already done.
int n = operation.get(); // May block the current thread while waiting.
~~~

*This is an illustrative snippet. In the full runnable example, `connect(...)` returns `Future<Void>` and `read(...)` uses `CompletionHandler`.*

Key points to understand:

1. Calling `read(buffer, ..., handler)` **initiates** the operation; its return does not prove the operation is finished.
2. The `completed(n, ...)` callback means **one read operation has finished**, not “a complete business message has arrived”. If the buffer still has `remaining()`, a **new read** must be initiated.
3. The `failed(Throwable, ...)` callback means the operation failed and must be handled/closed/canceled appropriately; do not let a parser process a partial buffer as a valid message.
4. `Future.get()` can **block**. If `get` is called immediately after every initiation without doing anything else, the program can turn into a sequential waiting model despite using an asynchronous API.
5. **There is no guarantee that the callback always runs on a new thread** or always runs later than the initiating call; dispatching depends on the runtime and the asynchronous channel group. Callbacks should be short, thread-safe, and never block on heavy tasks.
6. Using an asynchronous channel **does not mean** the implementation on every operating system must use pure kernel-level completion; what matters is the API semantics and their consequences for application code.

## 5. Comparing the Two Timelines

### Readiness / Reactor-Style

~~~text
Application                     Selector / OS                  SocketChannel
    |                                  |                            |
    |-- register(OP_READ) ------------>|                            |
    |-- select() --------------------->| wait for readability       |
    |<------------- readable key ------|                            |
    |-- key.isReadable() = true                                     |
    |-- read(ByteBuffer) ------------------------------------------>|
    |<-------------------------------------- n / 0 / -1 -------------|
    |-- parse actual byte count, keep frame state, wait next ready  |
~~~

### Completion-Driven / Async API

~~~text
Application                       Asynchronous channel / runtime
    |                                      |
    |-- read(buffer, handler) ------------>| initiate read
    |<-- return after initiation ----------| may not be done yet
    |               do other work ...
    |<-- completed(n) or failed(err) ------| operation has a result
    |-- process n bytes or issue new read if frame is incomplete
~~~

The diagrams describe **logical relationships**, not which thread executes the callback or the absolute ordering when an operation completes very quickly.

### A Comparison Table

| Aspect | Selector + non-blocking SocketChannel | AsynchronousSocketChannel |
| --- | --- | --- |
| Notification type | Readiness to attempt I/O | Result of an initiated I/O operation |
| Who actually performs the read/write call? | The application in the event loop | The application initiates the operation; the runtime processes it and reports the result |
| API | `Selector`, `SelectionKey`, `SocketChannel` | `AsynchronousSocketChannel`, `Future`, `CompletionHandler` |
| Configuration | `configureBlocking(false)` before registering | Uses asynchronous API, not `register(Selector)` like `SocketChannel` |
| Where byte count is known | `read()/write()` at the call site | `completed(Integer n)` or `Future.get()` |
| Handling incomplete messages | Keep parser state, wait for another readiness event | Issue the next operation from the completion |
| Complexity | State machine per key/event loop | State and ordering of callbacks/Futures |
| EOF | `read() == -1` | Read completion returns `-1` |
| Timeout | Readiness wait or application deadline | Operation timeout / Future wait timeout / application deadline |
| Threading | Usually one/a few event loops | Completion/provider thread group depending on implementation |
| Data | TCP byte stream, no message boundaries | TCP byte stream, no message boundaries |

## 6. Java 17+ Example: Selector Only Signals Readiness, It Does Not Read Data

The program creates a TCP server/client on loopback within the same JVM. The accepted `SocketChannel` is switched to non-blocking mode and registered for `OP_READ`. The sender writes `"PING"`. After a readable event, **the application calls `receiver.read(incoming)`** and only decodes/prints once the buffer has all 4 bytes.

Create the file `SelectorReadinessDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public class SelectorReadinessDemo {
    public static void main(String[] args) throws IOException {
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            try (SocketChannel sender = SocketChannel.open(listener.getLocalAddress());
                 SocketChannel receiver = listener.accept();
                 Selector selector = Selector.open()) {
                receiver.configureBlocking(false);
                receiver.register(selector, SelectionKey.OP_READ);

                ByteBuffer outgoing = StandardCharsets.US_ASCII.encode("PING");
                while (outgoing.hasRemaining()) {
                    sender.write(outgoing);
                }

                ByteBuffer incoming = ByteBuffer.allocate(4);
                boolean sawReadableKey = false;
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                while (incoming.hasRemaining() && System.nanoTime() < deadline) {
                    selector.select(1_000);
                    Iterator<SelectionKey> it = selector.selectedKeys().iterator();
                    while (it.hasNext()) {
                        SelectionKey key = it.next();
                        it.remove();
                        if (key.isValid() && key.isReadable()) {
                            sawReadableKey = true;
                            int n = receiver.read(incoming);
                            if (n < 0) {
                                throw new EOFException("peer closed before four bytes");
                            }
                        }
                    }
                }

                if (incoming.hasRemaining()) {
                    throw new IOException("incomplete payload");
                }
                incoming.flip();
                System.out.println("readiness observed: " + sawReadableKey);
                System.out.println("buffered bytes: " + incoming.remaining());
                System.out.println("payload: "
                        + StandardCharsets.US_ASCII.decode(incoming));
            }
        }
    }
}
~~~

Run commands:

~~~bash
javac SelectorReadinessDemo.java
java SelectorReadinessDemo
~~~

Output on loopback:

~~~text
readiness observed: true
buffered bytes: 4
payload: PING
~~~

Detailed explanation:

- `ServerSocketChannel` blocks at `accept()` only to create an **in-process connection fixture**. The part demonstrating Selector is `receiver` with `configureBlocking(false)` and `register(OP_READ)`.
- `selector.select(1_000)` only updates the selected-key set. Actual bytes are placed into `incoming` on the `receiver.read(incoming)` line, **not** inside `select`.
- `Iterator.remove()` removes the key from the selected-key set once handled.
- Because TCP can split data, the program loops across multiple read events if `incoming` does not yet have 4 bytes.
- If `read == -1` before 4 bytes are received, that is EOF before a complete payload. If delayed past the 5-second deadline, the demo throws an error instead of waiting forever.
- `incoming.flip()` switches the buffer from writing into it to reading out of it so `US_ASCII.decode` sees only the 4 bytes just received.

The example intentionally uses a fixed 4-byte length for easy stdout comparison; it does **not** replace a length-header frame decoder in a real system.

## 7. Java 17+ Example: AsynchronousSocketChannel Reports Completion

In this example, the client side uses `AsynchronousSocketChannel`. It initiates `connect(...)` and receives a `Future<Void>`, then initiates `read(...)` with a `CompletionHandler`. The peer server sends `"PONG"`. The handler is invoked when the read operation has a result, and if the buffer still has space, it **registers a new read**. `CountDownLatch` merely helps the demo program wait for the full payload to print to stdout.

Create the file `AsyncCompletionDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncCompletionDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            try (AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
                Future<Void> connecting = client.connect(listener.getLocalAddress());
                try (SocketChannel peer = listener.accept()) {
                    connecting.get(5, TimeUnit.SECONDS);

                    ByteBuffer incoming = ByteBuffer.allocate(4);
                    CountDownLatch done = new CountDownLatch(1);
                    AtomicReference<Throwable> failure = new AtomicReference<>();

                    CompletionHandler<Integer, Void> handler =
                            new CompletionHandler<Integer, Void>() {
                        @Override
                        public void completed(Integer n, Void attachment) {
                            if (n < 0) {
                                failure.set(new EOFException("incomplete payload"));
                                done.countDown();
                            } else if (incoming.hasRemaining()) {
                                client.read(incoming, null, this);
                            } else {
                                done.countDown();
                            }
                        }

                        @Override
                        public void failed(Throwable error, Void attachment) {
                            failure.set(error);
                            done.countDown();
                        }
                    };

                    client.read(incoming, null, handler);

                    ByteBuffer outgoing = StandardCharsets.US_ASCII.encode("PONG");
                    while (outgoing.hasRemaining()) {
                        peer.write(outgoing);
                    }

                    if (!done.await(5, TimeUnit.SECONDS)) {
                        throw new IOException("read completion timeout");
                    }
                    if (failure.get() != null) {
                        throw new IOException("read failed", failure.get());
                    }

                    incoming.flip();
                    System.out.println("completion observed: true");
                    System.out.println("buffered bytes: " + incoming.remaining());
                    System.out.println("payload: "
                            + StandardCharsets.US_ASCII.decode(incoming));
                }
            }
        }
    }
}
~~~

Run commands:

~~~bash
javac AsyncCompletionDemo.java
java AsyncCompletionDemo
~~~

Output on loopback:

~~~text
completion observed: true
buffered bytes: 4
payload: PONG
~~~

Explanation:

1. `client.connect(listener.getLocalAddress())` **initiates the connect** and returns `Future<Void>`. `connecting.get(5, SECONDS)` waits for the connect to finish; `get` may block the current thread. In the demo, waiting is used to ensure the connection is ready before posting the read.
2. `client.read(incoming, null, handler)` **initiates the read**; there is no `selector.select()` or readable key.
3. `completed(Integer n, ...)` is the result **of the read just initiated**. `n == -1` indicates EOF. If `incoming.hasRemaining()` is still true, fewer than 4 bytes have arrived; the handler initiates a subsequent read **after the previous read completes**.
4. `failed(Throwable, ...)` reports an I/O error. `AtomicReference` stores the error so the waiting thread knows and does not decode incomplete data.
5. `done.await(...)` blocks the main thread only so the demo knows when all 4 bytes have been received; it is not a required component when implementing a callback server.
6. Only after the latch signals completion does the program call `incoming.flip()` and decode `PONG`.
7. A single read callback can receive fewer bytes than the message length. **Operation completed ≠ message completed** — this is the most important detail when designing a parser on async channels.

The examples run on loopback and assume a normal network environment. Real applications must handle partial reads, EOF, payload limits, timeouts, shutdown, and backpressure across many clients.

## 8. OP_ACCEPT, OP_CONNECT, OP_READ, OP_WRITE: Mapping to Async

| Activity | Selector (readiness) | Asynchronous channel (completion) |
| --- | --- | --- |
| Accepting a new client | Wait for `OP_ACCEPT`, call `ServerSocketChannel.accept()` | Initiate `AsynchronousServerSocketChannel.accept(...)`, receive the accepted channel via handler/Future |
| Client connect | `SocketChannel.connect`; if pending, wait for `OP_CONNECT` then `finishConnect()` | `AsynchronousSocketChannel.connect(...)` and wait for Future/handler to report the result |
| Reading payload | Wait for `OP_READ`, call `SocketChannel.read(dst)` yourself | Initiate `AsynchronousSocketChannel.read(dst, ...)` and receive `completed(n)`/`failed` |
| Writing payload | Call `SocketChannel.write(src)` yourself; if bytes remain, enable `OP_WRITE` | Initiate `AsynchronousSocketChannel.write(src, ...)`, wait for operation completion then send the rest |
| EOF | `read(dst) == -1` | Read completion returns `-1` |
| Errors | Exceptions on read/write/finishConnect | `CompletionHandler.failed(Throwable)` or Future exception |

With readiness, `OP_CONNECT` only hints that `finishConnect()` can be called; it does not guarantee the connect succeeded. `OP_ACCEPT` likewise does not automatically put the client channel into a `SelectionKey`. With an asynchronous server, each `accept(...)` is **one operation**. If the server needs to accept multiple clients, after an accept completes it must initiate the next accept according to its design.

## 9. ByteBuffer, Partial Reads/Writes, and Ownership

Whether using readiness or completion, you must understand `ByteBuffer`:

| Property/Method | Meaning |
| --- | --- |
| `capacity()` | Fixed capacity |
| `position()` | Index of the next byte |
| `limit()` | Operation boundary |
| `remaining()`/`hasRemaining()` | Number of bytes or whether unprocessed bytes remain |
| `flip()` | Switches data just written into the buffer into a region ready to be read out |
| `clear()` | Resets position/limit, **does not erase array contents** |
| `compact()` | Shifts unread bytes to continue accumulating an incomplete frame |

A single `write(ByteBuffer)` can write fewer bytes than remaining: you must keep the buffer until `remaining()` reaches zero. A single `read(ByteBuffer)` can receive less than a message: you need parser state rather than assuming one callback = one frame.

In the asynchronous API, **do not read/modify a `ByteBuffer` from another thread while an operation is still pending**. Buffers are not thread-safe; position/limit may be modified by the runtime during I/O. If a new read is registered on the same `AsynchronousSocketChannel` before the previous read completes, `ReadPendingException` may be thrown; similarly `WritePendingException` for overlapping pending writes. Each connection should have at most one pending read per the API, issuing the next read inside the completion.

**Do not run CPU-heavy work or blocking database calls directly inside the Selector event loop or async callback thread.** Use a bounded executor, transfer message/session ownership clearly, and coordinate backpressure so an unbounded byte queue does not build up.

## 10. Both Models Must Detect TCP Message Boundaries Themselves

TCP does not deliver intact “messages” per `read`. For example, an application formats frames with a 4-byte big-endian length header:

~~~text
[4 byte length][length byte payload]
00 00 00 05 48 45 4C 4C 4F
  header 5        "HELLO"
~~~

In both designs:

1. Accumulate all **4 header bytes** (across multiple reads if needed).
2. `flip()` the header, read `int length`.
3. Validate `length >= 0 && length <= MAX_PAYLOAD_BYTES` **before allocating the body**; reject malicious lengths.
4. Read all `length` bytes of the body; if EOF/timeout occurs while incomplete, do not pass a partial message to business logic.
5. Process only complete payloads; retain state for the next message.

The difference lies in **how you wait and continue**:

- Selector: wait for `OP_READ`, **call `read`**, and if incomplete, keep the buffer/parser state and wait for the next readiness event.
- Async: initiate `read`, **wait for callback/Future completion**, and if incomplete, initiate a **new** read and keep the buffer/parser state.

The same applies to writing data: selector maintains an output queue and enables `OP_WRITE` only while bytes remain; async retains the buffer until completion and posts the next write if `remaining()` is still non-zero.

## 11. Timeouts, Cancellation, and Connection Lifecycle

| Tool | What time/work it actually limits | What must not be inferred |
| --- | --- | --- |
| `selector.select(1000)` | One readiness wait turn | Not the deadline for the whole message |
| Application deadline based on `System.nanoTime()` | Total maximum time enforced by the application | Does not automatically cancel any I/O unless code handles it |
| `future.get(5, SECONDS)` | How long the caller thread **waits for the result** | Does not mean the background operation was canceled on timeout |
| `asyncChannel.read(dst, timeout, unit, attachment, handler)` | Timeout for that specific read operation | Not the total time across all reads of a frame |
| `selector.wakeup()` | Wakes up a thread currently in `select` | Not I/O completion or cancellation |

`Future.get(timeout)` can throw `TimeoutException` while the operation is still running; a separate `cancel`/close/connection-state strategy is required. For asynchronous read/write timeouts, the JDK documentation notes that some implementations **cannot guarantee** the buffer will not continue to be affected after a timeout; you must not reuse the buffer/channel under the assumption that a pending operation has always stopped safely.

When a connection is closed, keys/callbacks may already be queued; check connection state, key validity, and handle `AsynchronousCloseException`/`ClosedChannelException`. Do not let a callback from a shut-down session touch buffers or business logic of a new session.

## 12. Choose a Model Based on Workload, Not the Label "Async"

**Selector** fits when you want a readiness-based event loop, managing state machines for many channels yourself, coordinating `interestOps`, and handling partial I/O. This model can be very efficient if each event is processed briefly; however, if an event handler takes too long, other connections managed by the same loop will be delayed.

**AsynchronousSocketChannel** fits when you want code triggered by **operation results**, coordinating `CompletionHandler` or `Future`, and transitioning state after each completion. Callbacks may run on the asynchronous channel group's thread pool or another runtime mechanism. Do not tie up callback threads with long-blocking work.

You cannot conclude **which model is faster across all OSes/JDKs** from the name alone. Measure latency, throughput, idle connection count, CPU, GC, allocations, retained buffers, and maintenance complexity. Both require limits on data, connection counts, output queues, synchronization, and EOF handling.

## 13. Common Pitfalls

| Claim/Error | What is wrong? | How to fix |
| --- | --- | --- |
| “`key.isReadable()` means bytes have arrived in the buffer.” | `Selector` does not perform `read` | Call `SocketChannel.read` and check `n` |
| “`OP_READ` guarantees payload is present.” | EOF/errors can also trigger readiness | Handle `-1` and exceptions |
| “`OP_CONNECT` means connect is done.” | Connect may still need completion or may have failed | Call `finishConnect()` |
| “`OP_ACCEPT` carries the client channel.” | It only signals readiness | Call `accept()` |
| “`read == 0` means the peer closed.” | Zero is not EOF | EOF is `-1` |
| “`completed(2)` means the 5-byte message is complete.” | Only **one read operation** completed | Issue a new read if the buffer is short |
| “Future is always non-blocking, even `get()`.” | `get()` can block the caller | Use callbacks or coordinate waiting appropriately |
| “Callbacks always run on a dedicated thread.” | There is no such guarantee | Make callbacks thread-safe and non-blocking |
| “You can `clear()` the buffer while an async read is pending.” | The runtime may still be using the buffer | Wait for completion/cancel per policy |
| “Start two reads at once on one async socket.” | May throw `ReadPendingException` | Issue the next read after completion |
| “Leave `OP_WRITE` enabled forever.” | Easily causes a busy loop | Enable only when output remains |
| “`select(timeout)` = I/O operation timeout.” | It only waits for readiness | Track frame/connection deadlines separately |
| “`get(timeout)` automatically cancels the pending operation.” | Only limits thread waiting | Cancel/close per your own policy |
| “Callback finished means the TCP message is finished.” | TCP is a byte stream | Use framing and parser state |

## 14. Self-Check and Exercises

**Question 1.** `key.isReadable() == true`, and immediately afterward `read(dst)` returns 0. Has the application received an empty message?

No. Readiness is only a **hint**, and `read == 0` means the current call transferred no bytes. Keep state and wait for subsequent readiness (unless the protocol has an explicit empty frame).

**Question 2.** The async callback `completed(2)` is invoked, but the parser needs 5 bytes. Has the operation completed or not?

**The operation has completed** with 2 bytes, but **the message is not complete**. You must initiate the next read after the callback, not treat 2 bytes as a valid frame.

**Question 3.** Non-blocking `SocketChannel.connect` returns false, and later `OP_CONNECT` fires. Why must `finishConnect()` still be called?

Readiness only says the connection **may be ready to complete or has an error**. `finishConnect()` performs the completion step and detects failures; you must not mark it connected from the key alone.

**Question 4.** `Future<Integer> f = async.read(dst); f.get(1, SECONDS)` throws `TimeoutException`. Is it allowed to `clear()` the buffer and reuse it immediately for another request?

Not by default. The thread waiting on the Future timed out, but the background operation may still be pending. You must handle cancel/close/ownership according to the API before reusing the buffer.

**Question 5.** Why can `OP_WRITE` cause an event loop to consume CPU even when there is no data to send?

Sockets are very frequently ready for writing, so `OP_WRITE` readiness can fire continuously. Only enable this bit when the output queue still has bytes; disable it when empty.

**Hands-on exercises:**
- Run both Java files, marking the `selector.select`/`key.isReadable` lines **vs** the `receiver.read` line; compare with the `client.read(..., handler)`/`completed` lines in the async example.
- Change `"PING"` to `"HELLO"`, increase the buffer to 5, and keep the full-read logic; then test partial reads by splitting the sender into two writes.
- Change `"PONG"` to `"HELLO"` in the async demo, increasing the buffer to 5. Verify the handler processes multiple completions if needed.
- Sketch a length-prefixed parser capped at `MAX_PAYLOAD_BYTES = 1024` for both models; allocate the payload only after validating the header.
- For a server with thousands of idle connections, diagram buffer/session ownership, backpressure, and shutdown for each model, then benchmark in a real environment.

## Official References (Java SE 21)

- [`Selector`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html) — selected keys, selection operations, and readiness.
- [`SelectionKey`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html) — `interestOps`, `readyOps`, `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, `OP_WRITE`.
- [`SocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html) — non-blocking `connect`/`finishConnect`/`read`/`write`.
- [`ServerSocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html) — blocking/non-blocking accept.
- [`AsynchronousSocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html) — Future, handler, pending read/write, timeout, and buffer safety.
- [`AsynchronousServerSocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html) — asynchronous accept.
- [`CompletionHandler`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/CompletionHandler.html) — `completed`/`failed`.
- [`ByteBuffer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html) — position, limit, flip, clear, compact.

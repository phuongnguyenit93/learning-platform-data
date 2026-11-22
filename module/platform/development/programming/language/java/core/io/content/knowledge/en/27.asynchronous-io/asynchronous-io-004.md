# AsynchronousSocketChannel and AsynchronousServerSocketChannel in Java NIO.2

Java NIO.2 provides two important asynchronous TCP networking APIs: `AsynchronousServerSocketChannel` for listening and accepting connections, and `AsynchronousSocketChannel` for connecting, reading, and writing on a socket. Instead of forcing the calling thread to wait until I/O finishes, these methods can **initiate the operation and return immediately**; results are received via `Future` or `CompletionHandler`.

The word "asynchronous" refers to **the operation completion model**, not a guarantee that every operating system uses the same kernel I/O mechanism, nor that application callbacks never execute on a thread that could be blocked by other work. When using these APIs, you must manage **connection state, buffers, pending operations, callback ordering, errors, and resource closing**.

This lesson covers both channels, how to open and use them, both result-delivery styles, a standalone Java 17 runnable example, limits around concurrent reads/writes, and common pitfalls.

## 1. Distinguishing the Two Channels and Execution Flow

| Class | Responsibility | Key Methods |
| --- | --- | --- |
| `AsynchronousServerSocketChannel` | Bind to a TCP address, wait for and accept new connections | `open()`, `bind(...)`, `accept()`, `accept(attachment, handler)`, `close()` |
| `AsynchronousSocketChannel` | Connect to a server or operate on a server-accepted connection | `open()`, `connect(...)`, `read(...)`, `write(...)`, `shutdownInput()`, `shutdownOutput()`, `close()` |

A typical exchange follows these steps:

```text
Server                                       Client
  |                                           |
  | AsynchronousServerSocketChannel.open()    |
  | bind(localAddress)                        |
  | accept()   [waiting for completion]       | AsynchronousSocketChannel.open()
  |                                           | connect(serverAddress)
  |<----------- TCP connection -------------->|
  | accept completes, returns server's        | connect completes
  | AsynchronousSocketChannel                 |
  | read()    [pending] <---------------------| write()
  | write() ------------------------------->  | read()
  | close channels per lifecycle              | close channel
```

**Important:** `accept()` does not return a synchronous `SocketChannel`, but a new `AsynchronousSocketChannel` representing the accepted connection. `AsynchronousServerSocketChannel` is used solely for **listening and accepting**, not for calling `read()` / `write()` data on individual clients.

These classes reside in the `java.nio.channels` package. They are distinct APIs from `ServerSocketChannel` and `SocketChannel` used with `Selector`. Do not register `AsynchronousSocketChannel` with a `Selector`, do not call `configureBlocking(false)`, and do not apply `SelectionKey.OP_READ/OP_WRITE` to these asynchronous channels.

## 2. Opening Server and Client

A server typically opens the channel, binds a local address, and initiates an `accept` operation:

```java
// Illustration inside a method permitted to throw IOException.
AsynchronousServerSocketChannel server =
        AsynchronousServerSocketChannel.open();
server.bind(new InetSocketAddress("127.0.0.1", 9000));

Future<AsynchronousSocketChannel> pending = server.accept();
```

This snippet is **illustrative**; it requires importing classes from `java.nio.channels`, `java.net`, `java.util.concurrent`, and closing `server` in `finally` / `try-with-resources`. If port 9000 is in use or the address cannot be bound, an `IOException` occurs. Calling `accept()` queues a pending request; calling `pending.get()` is what blocks the calling thread until a result arrives.

A client creates a channel and initiates a connection:

```java
// Illustration, omitting close management to focus on the API.
AsynchronousSocketChannel client = AsynchronousSocketChannel.open();
Future<Void> connecting =
        client.connect(new InetSocketAddress("127.0.0.1", 9000));
// Proceed with I/O only after connecting completes successfully.
```

With the `Future` form, you can call `connecting.get()` to wait for connection, but that waiting itself **blocks the calling thread**. The API remains asynchronous at the operation-initiation step; calling `get()` immediately is an application choice, not something that turns the channel back into a synchronous `SocketChannel`.

The `open()` methods above use the provider's **default asynchronous channel group**. Overloads also accept an `AsynchronousChannelGroup` so multiple channels share a thread pool and resources configured by the application.

## 3. Two Completion Result Models

### 3.1. Using Future: Easy to Write Step-by-Step Logic

Methods such as `connect(remote)`, `read(buffer)`, `write(buffer)`, and `accept()` return a `Future`. The completion value depends on the operation:

| Call | Future Type | Value Received via `get()` |
| --- | --- | --- |
| `client.connect(remote)` | `Future<Void>` | `null` when connection succeeds |
| `server.accept()` | `Future<AsynchronousSocketChannel>` | Newly accepted client connection |
| `client.read(dst)` | `Future<Integer>` | Actual bytes read; `-1` on EOF |
| `client.write(src)` | `Future<Integer>` | Actual bytes written |

Example:

```java
// Illustrative snippet inside a method handling checked exceptions.
Future<Integer> operation = client.read(buffer);

// Other work can be performed here.
Integer n = operation.get(5, TimeUnit.SECONDS);
```

`Future.get(timeout, unit)` sets a **wait deadline for the calling thread itself**; when `get` throws `TimeoutException`, do not assume the background I/O was canceled. A genuine timeout policy requires controlling the operation and channel; calling `cancel()` on an I/O operation has provider/API consequences to consider (in some cases making the channel unusable for operations of the same type), so do not arbitrarily keep using it as if no request were running.

`Future.get()` may throw `InterruptedException` if the waiting thread is interrupted, `ExecutionException` if the background operation fails, or `TimeoutException` if the timeout overload expires. Handle each case properly and release resources.

### 3.2. Using CompletionHandler: Results Arrive via Callback

Asynchronous overloads accept an **attachment** and a **handler** to deliver the result when the operation finishes. Core interface:

```java
public interface CompletionHandler<V, A> {
    void completed(V result, A attachment);
    void failed(Throwable exc, A attachment);
}
```

This is an illustrative signature, not a standalone code file. `V` is the operation's result type (`Integer`, `Void`, or `AsynchronousSocketChannel`); `A` is the attached state type chosen by the application.

Example initiating accept with a callback:

```java
// Illustration: server is bound, requires importing CompletionHandler.
server.accept(null, new CompletionHandler<AsynchronousSocketChannel, Void>() {
    @Override
    public void completed(AsynchronousSocketChannel peer, Void unused) {
        // peer is the accepted connection; its lifecycle must be managed.
        handleNewClient(peer); // Illustrative business method.
    }

    @Override
    public void failed(Throwable error, Void unused) {
        reportAcceptFailure(error); // Illustrative business method.
    }
});
```

`handleNewClient` and `reportAcceptFailure` are **undefined application methods**, so this snippet is not a standalone runnable program. Do not call `Future.get()` inside a callback to wait for the operation itself; the callback is already the completion point of that operation.

Callbacks may be executed by a thread from the asynchronous channel group. **Do not assume callbacks always run on the same thread that started the I/O, or that an application's callbacks always arrive in a predictable order**. Heavy work, blocking I/O, and long lock acquisitions inside callbacks can degrade service for other connections. Offload heavy work to an appropriate executor if needed.

## 4. Asynchronous Accept: Not Just Accepting Once

One `server.accept()` call normally corresponds to **one new connection**. After the request completes, to accept the next client you must issue a new `accept`.

With the callback style, a conceptual pattern:

```java
// Sketch, inside a component managing the server.
void acceptNext(AsynchronousServerSocketChannel server) {
    server.accept(null, new CompletionHandler<AsynchronousSocketChannel, Void>() {
        @Override
        public void completed(AsynchronousSocketChannel peer, Void ignored) {
            if (server.isOpen()) {
                acceptNext(server); // Schedule the next accept.
            }
            servePeer(peer); // Application method, must not stall the callback.
        }

        @Override
        public void failed(Throwable error, Void ignored) {
            if (server.isOpen()) {
                onAcceptFailure(error); // Log error, coordinate retry.
            }
        }
    });
}
```

This is an **architectural sketch**, omitting `servePeer` / `onAcceptFailure`, retry/backoff, and socket close management; it is not a standalone program. A production server must ensure a policy for re-registering the next accept after recoverable errors, avoiding unbounded tight error loops.

**Mandatory limitation:** An `AsynchronousServerSocketChannel` permits only **one pending accept request**. Calling another accept before the previous one completes can throw `AcceptPendingException`. Do not have multiple threads uncoordinatedly call `accept` on the same server channel expecting each call to form an accept queue.

In `completed`, the returned `peer` channel has been handed over to the application; it must have an owner and a `close` policy, independent of the server continuing to accept new clients.

## 5. Asynchronous Read/Write and Partial I/O

When `AsynchronousSocketChannel` completes a read or write call, the completed byte count **is not guaranteed to equal all remaining bytes in the ByteBuffer**:

```java
Future<Integer> r = client.read(input);
Future<Integer> w = client.write(output);
```

These are two illustrative operations; they require valid buffers, a channel in the connected state, and coordination to avoid overlapping operations of the same kind. With TCP, sender and receiver always process a **byte stream**, not messages with built-in boundaries.

| Result | `read(dst)` | `write(src)` |
| --- | --- | --- |
| Positive `n` | Received `n` bytes, `dst.position()` advances by `n` | Sent `n` bytes, `src.position()` advances by `n` |
| `0` | No bytes read in this operation yet, not EOF | No bytes written in this operation yet, not finished sending |
| `-1` | Input EOF (peer closed its send side) | Not a normal successful write result |

For example, if an application needs to send 10 bytes, the first write operation might complete with result 3. When the callback arrives, `output.position()` has already moved to 3; **you must continue sending the remaining 7 bytes from that same buffer**, rather than calling `rewind()` to resend from the beginning or discarding the buffer before finishing.

Similarly, a single read into an 8-byte buffer may return 2; an 8-byte frame cannot be decoded yet. The application must preserve those 2 bytes and start the next read request to obtain more data.

### One Pending Read and One Pending Write

`AsynchronousSocketChannel` allows one read request and one write request to be in progress concurrently on the same connection, however:

- While **a read is still unfinished**, initiating a second read on the same channel may throw `ReadPendingException`.
- While **a write is still unfinished**, initiating a second write on the same channel may throw `WritePendingException`.
- Start the next operation **of the same kind** only after the previous one completes (with success or failure) and state is coordinated.
- Do not modify the contents, `position`, or `limit` of a buffer currently used by an operation before that operation completes. Avoid handing that buffer to another thread for concurrent modification.
- Once read/write has completed, the callback or `Future`-handling code can use the actual byte count and buffer state to decide the next step.

This is a key distinction from `Selector`: AIO notifies **operation completed**, not merely `OP_READ/OP_WRITE` readiness. Even so, a completion may still have processed only part of a frame.

### Using a Loop with Future to Process a Buffer Completely

The snippet below is an **illustrative pattern** when the caller is allowed to wait for results, handles `InterruptedException`, `ExecutionException`, `TimeoutException`, and has a connected `AsynchronousSocketChannel client`:

```java
ByteBuffer data = ByteBuffer.wrap(new byte[] {1, 2, 3, 4});
while (data.hasRemaining()) {
    int n = client.write(data).get(5, TimeUnit.SECONDS);
    if (n < 0) {
        throw new IOException("Unexpected write result");
    }
    // n==0: nothing sent yet; attempt the next operation per timeout policy.
}
```

Only when `data.hasRemaining()` is `false` have the buffer's bytes been fully accepted by the channel. That **does not confirm the receiving application has read or processed the data**; application-level confirmation requires an application acknowledgment/response protocol.

With `CompletionHandler`, the pattern for handling partial writes is to keep the buffer as the attachment (or connection state), and call `write()` again when `completed` indicates bytes remain:

```java
// Sketch inside the component owning the channel and buffer.
CompletionHandler<Integer, ByteBuffer> handler =
        new CompletionHandler<>() {
            @Override
            public void completed(Integer n, ByteBuffer pending) {
                if (n < 0) {
                    reportWriteFailure(new IOException("Negative write"));
                } else if (pending.hasRemaining()) {
                    channel.write(pending, pending, this);
                } else {
                    onFrameSent();
                }
            }

            @Override
            public void failed(Throwable error, ByteBuffer pending) {
                reportWriteFailure(error);
            }
        };

channel.write(outbound, outbound, handler);
```

This is a **sketch**, requiring `channel`, `outbound`, `onFrameSent`, `reportWriteFailure`, and an ownership/channel-closing mechanism. On error or timeout, do not arbitrarily re-initiate an operation when the channel state is no longer trustworthy. Production applications also need limits on pending bytes, retry counts, deadlines, and backpressure policies.

## 6. Complete Java 17 Program: Server Accepting via Handler, Client Connecting and Exchanging via Future

The example below creates a TCP server on the loopback address with an **ephemeral port** to avoid external service dependencies. The server registers `accept` using `CompletionHandler`, using `CompletableFuture` to pass the callback result to the example's control thread. The client uses `Future` to connect and perform I/O. Both sides exchange the ASCII bytes `PING` and `PONG`; the read/write helpers loop according to actual completed bytes rather than assuming one operation handles everything.

Create the file **`AsyncSocketDemo.java`**:

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public final class AsyncSocketDemo {
    private AsyncSocketDemo() {}

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                    AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                    AsynchronousSocketChannel.open()) {

            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            CompletableFuture<AsynchronousSocketChannel> accepted =
                    new CompletableFuture<>();

            server.accept(null,
                    new CompletionHandler<AsynchronousSocketChannel, Void>() {
                        @Override
                        public void completed(
                                AsynchronousSocketChannel peer,
                                Void attachment) {
                            accepted.complete(peer);
                        }

                        @Override
                        public void failed(Throwable error, Void attachment) {
                            accepted.completeExceptionally(error);
                        }
                    });

            client.connect(server.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel peer =
                    accepted.get(5, TimeUnit.SECONDS)) {

                writeFully(client, ByteBuffer.wrap(
                        "PING".getBytes(StandardCharsets.US_ASCII)));

                ByteBuffer request = ByteBuffer.allocate(4);
                readFully(peer, request);
                request.flip();
                System.out.println("server received="
                        + StandardCharsets.US_ASCII.decode(request));

                writeFully(peer, ByteBuffer.wrap(
                        "PONG".getBytes(StandardCharsets.US_ASCII)));

                ByteBuffer response = ByteBuffer.allocate(4);
                readFully(client, response);
                response.flip();
                System.out.println("client received="
                        + StandardCharsets.US_ASCII.decode(response));
            }
        }
    }

    private static void writeFully(AsynchronousSocketChannel channel,
                                   ByteBuffer data) throws Exception {
        while (data.hasRemaining()) {
            int n = channel.write(data).get(5, TimeUnit.SECONDS);
            if (n < 0) {
                throw new IOException("Unexpected write result");
            }
        }
    }

    private static void readFully(AsynchronousSocketChannel channel,
                                  ByteBuffer data) throws Exception {
        while (data.hasRemaining()) {
            int n = channel.read(data).get(5, TimeUnit.SECONDS);
            if (n < 0) {
                throw new EOFException("Stream ended before frame was complete");
            }
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac AsyncSocketDemo.java
java AsyncSocketDemo
```

Output when loopback works normally and I/O completes within the example's timeout:

```text
server received=PING
client received=PONG
```

**Execution flow explanation:**

1. `server.bind(..., 0)` asks the OS to pick an available port on the loopback address.
2. `server.accept(null, handler)` registers a connection-accept request and **returns immediately**; upon completion, the callback places the accepted channel into `accepted`.
3. `client.connect(...)` initiates the TCP connection; `get(5, TimeUnit.SECONDS)` waits for the result in the demo.
4. `accepted.get(...)` retrieves the server-side channel. It is a distinct `AsynchronousSocketChannel` from `client`.
5. `writeFully(client, ...)` sends the bytes of `PING`. `readFully(peer, ...)` receives all 4 bytes and calls `flip()` before decoding.
6. The server writes `PONG`, the client reads all 4 bytes and prints the result. `try-with-resources` closes peer, client, and server.

`readFully` and `writeFully` invoke **asynchronous operations** but then wait on `Future.get()`, so the example coordinates sequentially for clarity of learning. A highly scalable AIO server typically organizes state/callbacks so it does not block the coordinating thread per connection.

The example intentionally uses a **fixed 4-byte frame** protocol, not general framing for arbitrary TCP messages. In a real protocol, you must enforce frame size limits and keep state for incomplete frames. When `Future.get` times out, the demo code exits the `try` block and closes the channel rather than assuming the operation stopped by itself. The illustrative helpers have no backoff for repeated 0-byte completions; this tiny loopback example is not intended as a load-bearing server implementation.

## 7. Managing Per-Connection State and Non-blocking Callbacks

When a server handles many clients, you must not share a single `ByteBuffer` variable across all connections. Each `AsynchronousSocketChannel` can have a `Session` object containing:

```java
// Illustrative definition for a multi-connection server.
final class Session {
    final AsynchronousSocketChannel channel;
    final ByteBuffer inbound = ByteBuffer.allocate(8192);
    final java.util.ArrayDeque<ByteBuffer> outgoing =
            new java.util.ArrayDeque<>();
    boolean inputEnded;
    int expectedFrameLength = -1;

    Session(AsynchronousSocketChannel channel) {
        this.channel = channel;
    }
}
```

This is an illustrative snippet, without a complete server or thread-safe queues. A real design must clarify who owns `Session` and whether callbacks can execute concurrently.

Typical processing sequence:

1. Once accepted, create a `Session` for the client.
2. Start a `read` with `session.inbound` and attach `session` to the handler.
3. When read completes: if `-1`, handle EOF; if data arrived, `flip()` to parse complete frames, `compact()` to preserve incomplete bytes; then schedule a new read if the connection is still open and buffer space remains.
4. When a response is ready, enqueue the `ByteBuffer` onto the output queue and **initiate only one pending write** per channel. After the write completes, if bytes remain in that buffer, continue; once empty, proceed to the next queued buffer.
5. If the output queue grows too large, apply **backpressure**: cap request counts, cap queued bytes, pause reading input per protocol, or close slow connections. Never allocate unbounded buffers when a client stops reading.

`ByteBuffer.flip()` switches from writing into the buffer to reading the accumulated data; `compact()` preserves bytes not yet consumed by the parser. Calling `clear()` before everything is processed loses partial data boundaries; calling `rewind()` on an outbound buffer with bytes remaining can cause duplicate sends.

When read and write callbacks execute close together, mutating `Session` from both requires explicit coordination (such as a state machine and single-owner executor, or proper locking). **Do not infer that callbacks execute sequentially merely because they belong to the same channel**.

## 8. AsynchronousChannelGroup and Thread Resources

`AsynchronousChannelGroup` is a group of asynchronous channels tied to a provider, allowing control over the resources used to run completion tasks. Instead of using the default group, an application can create a group with an executor:

```java
// Illustrative snippet, requires IOException/try-finally and executor management.
ExecutorService executor = Executors.newFixedThreadPool(4);
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withThreadPool(executor);

AsynchronousServerSocketChannel server =
        AsynchronousServerSocketChannel.open(group);

AsynchronousSocketChannel client =
        AsynchronousSocketChannel.open(group);
```

This snippet requires importing `java.util.concurrent.ExecutorService`, `Executors`, and `java.nio.channels.AsynchronousChannelGroup`; it is not a standalone program. In practice, **you must close channels, shut down the group, and manage executor/thread lifecycles** according to the API and provider. An executor serving callbacks must also not be monopolized by too many long-blocking tasks.

Important points:

- Do not assume the number of callback threads equals the number of TCP connections; a single group can serve many channels.
- Implementations may differ across OS/JDK platforms: `AsynchronousSocketChannel` is an asynchronous API, not guaranteed to use native kernel AIO on every platform.
- `CompletionHandler.failed` must handle errors per connection state; one client's error must not leave other callbacks unhandled.
- Group shutdown and channel closing are two separate responsibilities. Do not shut down a group while operations still need to run or results have not finished processing without a recovery policy.

## 9. Timeouts, Closing Channels, and Operation Cancellation

Callback overloads of `AsynchronousSocketChannel` allow an I/O timeout:

```java
// Illustration: channel and dst already declared.
channel.read(dst, 5, TimeUnit.SECONDS, state,
        new CompletionHandler<Integer, Session>() {
            @Override
            public void completed(Integer n, Session s) {
                onReadComplete(n, s);
            }

            @Override
            public void failed(Throwable error, Session s) {
                onReadFailure(error, s);
            }
        });
```

This is a non-standalone pattern: `channel`, `dst`, `state`, `Session`, `onReadComplete`, and `onReadFailure` are application-defined parts. Unlike `Future.get(5,SECONDS)` (which only bounds **waiting for the result**), the timeout on the `read/write` overload is a parameter **of the operation itself**.

When an operation times out or is canceled, the `AsynchronousSocketChannel` contract may leave subsequent read/write usability on the channel unguaranteed in some situations. For a connection encountering a serious error, the safe practice is usually to mark the session failed, cancel related tasks, close the channel, and clean up state rather than blindly attempting to reuse the buffer or channel.

Special cases to handle:

| Situation | What to Do |
| --- | --- |
| `UnresolvedAddressException` or `UnsupportedAddressTypeException` on connect | Check the address and `SocketAddress` type |
| Connect fails | Operation reports failure; do not treat the channel as validly connected |
| `ReadPendingException` or `WritePendingException` | An operation of the same kind is already pending; fix the state machine |
| `AcceptPendingException` | Do not issue a second accept before the first completes |
| `AsynchronousCloseException` or `ClosedChannelException` | The channel was closed during or prior to the operation |
| `InterruptedException` while awaiting Future | Follow proper interrupt and cleanup policy without losing error signals |
| `ExecutionException` while awaiting Future | Inspect the root cause in `getCause()` |
| `read` completes with `-1` | Handle EOF, half-close, or incomplete frame per protocol |
| `write` completes with `0` | Keep the buffer and proceed to the next operation in a controlled manner |

`AsynchronousSocketChannel.shutdownOutput()` is used when you want to close the send direction while potentially still reading responses on the receive direction, fitting certain TCP half-close protocols. However, calling `shutdownOutput()` before all outbound bytes finish sending can drop data from the application's perspective.

## 10. Comparison with Blocking I/O and Selector

| Criterion | `Socket` / blocking channel | `SocketChannel` + `Selector` | `AsynchronousSocketChannel` |
| --- | --- | --- | --- |
| Main mechanism | Thread waits during read/write | Monitor readiness with `select()` | Initiate operation, receive completion |
| How data arrival is known | `read` returns after operation completes or EOF | `OP_READ` signals reading can be tried | `Future` or callback indicates read completed |
| How write completion is known | Blocking call finishes after writing accepted data | `OP_WRITE` signals ability to try writing | Write completion carries bytes written |
| Partial read/write | Can still occur | Must retain buffer across readiness turns | Must retain buffer across completions |
| Coordination | Can be simple for few connections | Event loop, interest ops, per-key state | Callbacks/Future, per-connection/attachment state |
| Common confusion | One read is not necessarily one frame | Readiness does not guarantee a full frame | Completion does not guarantee a full frame |

AIO is not the default optimal choice. `Selector` can be convenient if an application already has a clear event loop; blocking I/O or virtual threads (on supported Java versions) can make business logic easier to read in some systems. Choose an architecture based on throughput, latency, connection count, maintainability, and testing on the actual deployment platform.

## 11. Common Pitfalls and How to Fix Them

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Thinking `accept()` automatically accepts all subsequent connections | Server accepts one client and stops accepting | Initiate a new accept after completion appropriately |
| Issuing two pending `accept` calls on the same server channel | `AcceptPendingException` | Only one outstanding accept per server channel |
| Calling `read` a second time while the old read is pending | `ReadPendingException` | State machine schedules a new read only after completion |
| Calling `write` overlapping an old write | `WritePendingException` | Output queue and single pending write |
| Assuming one read completion equals one TCP message | Broken frame assembly/splitting | Framing, parser, and buffer state |
| Failing to check `ByteBuffer.hasRemaining()` after write | Incomplete data sent | Continue writing from current position |
| Calling `Future.get()` directly on a main callback thread and blocking long | Starves other completions | Use callbacks/state machine or separate executor |
| Sharing one buffer across multiple operations, mutating before completion | Corrupted data and races | Clear ownership; never touch pending buffers |
| Treating `get` timeout as having canceled the I/O | Operation may still be running | Close/cancel/clean up under an explicit policy |
| Callback throws an exception or ignores `failed` | Connection leaks, lost error details | Handle all branches, log, and close |
| Neglecting group/executor/socket lifecycle | Leaks threads, connections, or memory | `try-with-resources` for channels, shut down group properly |

**Key takeaway:** `AsynchronousServerSocketChannel` listens for TCP connections and produces an `AsynchronousSocketChannel` for each client; `AsynchronousSocketChannel` performs asynchronous connect/read/write. Receive results with `Future` or `CompletionHandler`, never issue overlapping operations of the same kind before completion, never assume one I/O handles a whole frame, and always manage buffers/state alongside connection lifecycles explicitly.

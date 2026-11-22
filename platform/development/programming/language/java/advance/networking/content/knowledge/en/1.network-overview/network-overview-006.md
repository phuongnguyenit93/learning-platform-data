# Comparing Blocking, Non-blocking, and Asynchronous I/O in Java Networking

When writing network applications, a TCP connection may be waiting for a client to send data, waiting for a socket to become ready for writing, or waiting for a read operation to complete. Those three ways of organizing that wait — **blocking I/O**, **non-blocking I/O**, and **asynchronous I/O** — create different programming models, thread requirements, and error-handling approaches. They are not three "progressively faster" levels: effectiveness depends on the number of connections, the ratio of idle connections, data volume, processing work, and implementation.

**After this lesson, you should be able to:** distinguish when a call returns from when data actually arrives; explain readiness versus completion; identify the corresponding Java APIs; read socket examples of all three styles; choose an appropriate model and handle common pitfalls such as short reads, partial writes, queue overload, and connection closure.

## 1. Two Questions to Distinguish

**Question 1 — Does the call keep the thread in a waiting state?**

- **Blocking:** a call such as reading from a socket can hold the calling thread waiting until data, EOF, an error, or a timeout occurs. Meanwhile, the thread does not continue executing subsequent statements.
- **Non-blocking:** a read/write call attempts to proceed immediately and returns whatever result is currently available; for instance, reading from a SocketChannel in non-blocking mode can return **0** because no bytes are currently available. The application itself decides when to retry.
- Note: a non-blocking call is still a **synchronous** call in the sense that the call returns the result of the attempt right on the spot. "Non-blocking" and "asynchronous" are not synonymous.

**Question 2 — Is the application notified "you can try" or "it has completed"?**

- **Readiness:** the system notifies that a socket shows signs of being able to read/write without waiting long. The application still has to call **read/write** itself and check the result. Java NIO **Selector** follows this approach.
- **Completion:** the application initiates the operation and receives a **Future** or **CompletionHandler**; the result is provided when the operation completes or fails. Java NIO.2 **AsynchronousSocketChannel** follows this approach.

Conceptual timeline:

~~~text
Blocking:
  read() --------[thread waits for data]--------> returns n / -1 / error

Non-blocking + readiness:
  read() -> 0 -> register OP_READ -> select() reports readiness
                                     -> read() -> n / 0 / -1 / error

Asynchronous + completion:
  initiate read(buffer, handler) -> returns immediately
  ... application can do other work ...
  completed(n) / failed(error) when the operation finishes
~~~

**Key takeaway:** readiness is only a signal to **attempt I/O**; completion is a notification of the **result of the requested I/O**. The asynchronous model does not guarantee that every operation is executed purely asynchronously by the kernel; a Java provider may use OS mechanisms or background threads for its implementation.

## 2. Quick Comparison Table

| Criterion | Blocking I/O | Non-blocking I/O | Asynchronous I/O |
|---|---|---|---|
| Typical Java API | **Socket**, **ServerSocket**, **InputStream/OutputStream** | **SocketChannel**, **ServerSocketChannel** with **configureBlocking(false)**, **Selector** | **AsynchronousSocketChannel**, **AsynchronousServerSocketChannel** |
| When no data is available to read | Read call blocks | Read call may return **0** | Operation has been initiated; result arrives via Future/handler |
| Dispatch signal | Thread waits at the call | **SelectionKey**: OP_ACCEPT, OP_CONNECT, OP_READ, OP_WRITE | **CompletionHandler.completed/failed** or **Future** |
| Common model | One handling thread per connection/task; can also use virtual threads on Java 21+ | One or a few event loops managing many sockets | Callbacks, Futures, completion thread group |
| Complexity | Low for sequential business flows | Higher: channel state, interestOps, buffers, partial I/O | Higher: callbacks, operation lifecycle, pending I/O |
| Strengths | Easy to read, debug, and integrate with synchronous libraries | Suits many idle connections and readiness-based dispatching | Does not force the calling thread to wait for each result; clear completion API |
| Risks | Many platform threads, queue/thread pool overload | Busy loops, forgetting to handle 0 results/partial writes, blocking the event loop | Complex callbacks, blocked completion threads, overlapping reads/writes |

You should not infer from the table that non-blocking or asynchronous is automatically faster. For example, a service with a few connections and simple processing may use blocking code with better latency and maintainability. Conversely, tens of thousands of long-lived but mostly idle connections can make the one-platform-thread-per-connection model resource-intensive.

## 3. Blocking I/O — Sequential Code, Clear Waiting Points

In traditional Java networking, **ServerSocket.accept()** waits for a new connection, **Socket.getInputStream().read()** waits for data or EOF, and **Socket.getOutputStream().write(...)** can block when send buffer space is limited. A returning write call only means the data has been accepted by the sending layer according to the API contract; it does **not** prove that the application at the other end has read/processed that data.

The Java 17 example below uses the loopback address, an OS-assigned ephemeral port, one server worker thread, and one client. The illustrative protocol exchanges only **one byte**: the client sends the letter **A** (65), and the server replies with the letter **B** (66).

**BlockingEchoDemo.java**

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

public class BlockingEchoDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket server = new ServerSocket(0, 10, loopback)) {
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<?> handling = executor.submit(() -> {
                    try (Socket peer = server.accept()) {
                        int request = peer.getInputStream().read();
                        if (request == -1) {
                            throw new EOFException("Client closed before sending");
                        }
                        peer.getOutputStream().write(request + 1);
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                });

                try (Socket client = new Socket(loopback, server.getLocalPort())) {
                    client.setSoTimeout(3_000);
                    client.getOutputStream().write('A');

                    int reply = client.getInputStream().read();
                    if (reply == -1) {
                        throw new EOFException("Server closed before responding");
                    }
                    System.out.println("Client received: " + (char) reply);
                }
                handling.get(3, TimeUnit.SECONDS);
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Run from the directory containing the file:

~~~bash
javac -encoding UTF-8 BlockingEchoDemo.java
java BlockingEchoDemo
~~~

Output on a normal run:

~~~text
Client received: B
~~~

On the server thread, **accept()** waits for a connection and **read()** waits for one byte. On the client thread, **read()** waits for the response. We need a separate thread for the server because if we placed **accept()** before creating the client on the same thread, the program would not make progress on its own.

**Strengths:** sequential logic is easy to follow, suitable for small tools, sequential interactions, or services using libraries with synchronous APIs. **Limitations:** if you dedicate one platform thread per client and the number of idle clients grows sharply, stack memory, scheduling, and thread pool limits can become bottlenecks. **Timeouts:** **Socket.setSoTimeout(...)** in the example applies to socket read calls; it does not replace a connect timeout, write timeout, or overall request deadline. For connect, use the **Socket.connect(address, timeout)** overload when needed.

## 4. Non-blocking I/O — Try Immediately, Wait for Readiness with Selector

**java.nio.channels.SocketChannel** can enable **configureBlocking(false)**. Then **read(ByteBuffer)** returns:

- **n > 0:** n bytes were read; the ByteBuffer position advances accordingly;
- **n = 0:** this attempt read no bytes; must not be treated as EOF or an error;
- **n = -1:** the other end has closed the incoming read stream of the connection (EOF).

For **write(ByteBuffer)**, the return value is the number of bytes written in **that call** and may be less than the number of bytes remaining in the buffer, including 0. The buffer retains its position so the next call can send the remainder. TCP is a byte stream; it does not preserve the boundary of one **write** as one **read**.

Instead of repeatedly trying to read and burning CPU, the application registers channels with a **Selector**:

1. Open a **ServerSocketChannel**, set it to non-blocking, and register **OP_ACCEPT**.
2. **selector.select()** waits for at least one ready event; the **select** call can block the **event loop thread**, even though the sockets themselves are in non-blocking mode.
3. Iterate over selected keys, remove each from the selected-key set, check **isValid()**, and handle **accept/read/write**.
4. For an incomplete connection, use **OP_CONNECT** and **finishConnect()**; for remaining outbound data, enable **OP_WRITE** only when actually needed.

The self-contained Java 17 example below shows the **server** handling accept/read via readiness. The client stays in blocking mode to keep the simulation concise. This is a **one-byte** protocol, not an arbitrary message reader.

**NonBlockingSelectorDemo.java**

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.util.Iterator;

public class NonBlockingSelectorDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open();
             Selector selector = Selector.open()) {

            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);

            try (SocketChannel client = SocketChannel.open()) {
                client.connect(server.getLocalAddress());

                ByteBuffer outgoing = ByteBuffer.wrap(new byte[] {'A'});
                while (outgoing.hasRemaining()) {
                    client.write(outgoing);
                }

                boolean received = false;
                while (!received) {
                    selector.select();
                    Iterator<SelectionKey> it =
                            selector.selectedKeys().iterator();

                    while (it.hasNext()) {
                        SelectionKey key = it.next();
                        it.remove();
                        if (!key.isValid()) {
                            continue;
                        }

                        if (key.isAcceptable()) {
                            SocketChannel peer = server.accept();
                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(selector, SelectionKey.OP_READ,
                                        ByteBuffer.allocate(1));
                            }
                        } else if (key.isReadable()) {
                            SocketChannel peer = (SocketChannel) key.channel();
                            ByteBuffer input = (ByteBuffer) key.attachment();
                            int n = peer.read(input);
                            if (n == -1) {
                                peer.close();
                                throw new IllegalStateException(
                                        "Client closed before sending");
                            }
                            if (!input.hasRemaining()) {
                                input.flip();
                                System.out.println(
                                        "Server received: " + (char) input.get());
                                peer.close();
                                received = true;
                            }
                        }
                    }
                }
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NonBlockingSelectorDemo.java
java NonBlockingSelectorDemo
~~~

~~~text
Server received: A
~~~

**What to observe:** **server.accept()** is called only after the key is ready; **peer.read(input)** can return 0 so the program does **not** use 0 as a close signal. Calling **it.remove()** prevents reprocessing old events in the selected-key set. **ByteBuffer.flip()** switches from writing into the buffer to reading from the buffer. Because the sample only needs a single byte, the loop finishes once the buffer is full; a real protocol must accumulate multiple bytes and frame messages.

**Selector is not an automatic business-logic dispatcher.** If in the **OP_READ** callback you make synchronous database calls, sleep, perform heavy decryption, or wait on another API, the entire event loop can be blocked, forcing other sockets to wait. Long-running work must be offloaded to an appropriate worker, with bounded queues and a mechanism to route results back to the loop if needed.

A classic mistake is leaving **OP_WRITE** permanently enabled: sockets are frequently ready for writing, causing **select()** to wake up continuously and spiking CPU even when there is no data left to send. Only register OP_WRITE when the outbound queue has unsent data; turn it off after draining the queue. Conversely, always keeping **OP_READ** enabled without a control threshold will cause buffers and processing queues to grow without bound against a fast-sending client.

## 5. Asynchronous I/O — Request an Operation, Receive Completion

**AsynchronousSocketChannel** and **AsynchronousServerSocketChannel** belong to NIO.2. With this style, **connect/accept/read/write** operations can be initiated immediately and complete later via:

- **Future**: calling **read(buffer)** or **write(buffer)** returns a result Future. Calling **Future.get()** will **block the thread calling get** until the result is available; therefore, merely "using an async API" does not mean the rest of the program is non-blocking.
- **CompletionHandler**: calling the overload that takes an **attachment** and a handler. Upon completion, **completed(result, attachment)** is invoked; upon failure, **failed(error, attachment)** is invoked. Code should not rely on assumptions that callbacks always run on a specific thread or never experience contention.

The next Java 17 example uses a Future to complete the connect/accept step for straightforward setup, while the actual **data read** operation uses **CompletionHandler** and a **CompletableFuture** signal. Main waits at the edge of the program to keep the demo alive until the result arrives; a real server would continue dispatching work without blocking hordes of threads just to wait on a read.

**AsyncCallbackDemo.java**

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class AsyncCallbackDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            Future<AsynchronousSocketChannel> accepting = server.accept();

            try (AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open()) {
                client.connect(server.getLocalAddress())
                        .get(3, TimeUnit.SECONDS);

                try (AsynchronousSocketChannel peer =
                             accepting.get(3, TimeUnit.SECONDS)) {
                    CompletableFuture<Byte> completedRead =
                            new CompletableFuture<>();
                    ByteBuffer input = ByteBuffer.allocate(1);

                    peer.read(input, null,
                            new CompletionHandler<Integer, Void>() {
                        @Override
                        public void completed(Integer n, Void ignored) {
                            if (n == -1) {
                                completedRead.completeExceptionally(
                                        new IllegalStateException("EOF"));
                            } else if (input.hasRemaining()) {
                                peer.read(input, null, this);
                            } else {
                                input.flip();
                                completedRead.complete(input.get());
                            }
                        }

                        @Override
                        public void failed(Throwable error, Void ignored) {
                            completedRead.completeExceptionally(error);
                        }
                    });

                    ByteBuffer output = ByteBuffer.wrap(new byte[] {'A'});
                    while (output.hasRemaining()) {
                        client.write(output).get(3, TimeUnit.SECONDS);
                    }

                    byte value = completedRead.get(3, TimeUnit.SECONDS);
                    System.out.println("Server received: " + (char) value);
                }
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 AsyncCallbackDemo.java
java AsyncCallbackDemo
~~~

~~~text
Server received: A
~~~

The callback does not return n directly to the **peer.read(...)** statement. It completes **completedRead** once one byte has entered the buffer; when data is not yet sufficient, it initiates the next read **after** the previous operation has finished. If an exception or EOF occurs, it completes accordingly rather than leaving main waiting indefinitely.

**Note on pending operations:** with **AsynchronousSocketChannel**, do not initiate two concurrent reads on the same channel while the previous read is still pending, or you may encounter **ReadPendingException**; similarly, overlapping writes may encounter **WritePendingException**. You should serialize reads, serialize writes, and manage queues and close states; do not equate "many callbacks" with "all operations run safely in parallel."

**Implementation note:** completion handlers are typically dispatched by threads in the channel group or by the provider's mechanism. A callback that does heavy CPU work or calls blocking code can tie up threads shared by many other completions. An async API decouples request time from result time, but it does not eliminate thread, memory, data-copying, or kernel costs.

## 6. Viewing the Same Connection from Three Angles

Suppose 10,000 clients connect to a server, but most only send a small packet every few seconds:

- **Blocking with one platform thread per client:** a vast number of threads may be parked in **read()**; the code is easy to write, but thread count, stacks, and context switches can become significant overhead. If the thread pool limit is too low, new connections may have to wait; if created without bound, machine resources can be exhausted.
- **Non-blocking + Selector:** a small number of event loops call **select()**, processing sockets only when readiness appears. This model works well for many idle connections, but requires careful handling of buffers, per-connection state, partial writes, and backpressure.
- **Asynchronous + completion:** the application registers operations awaiting completion, then continues processing when callbacks/Futures yield results. Suitable when the application layer is already structured around completion, though you still must measure callback volume, background threads, and ordering guarantees.

Suppose there are only 20 clients, each request requiring 200 ms of CPU processing: switching reads from blocking to non-blocking **does not reduce CPU usage**. If CPU work runs directly on the selector loop, 20 clients may even respond more slowly because the loop is occupied. In that case, strategies for CPU tasks and concurrency limits matter more than changing the socket API.

**Java 21+ adds an option worth considering:** virtual threads allow keeping a sequential blocking programming style while supporting a large number of concurrent tasks with lower thread overhead than platform threads in many I/O scenarios. This is a runtime/scheduler choice; it does **not** turn every **Socket.read()** call into an **AsynchronousSocketChannel** callback. The examples here use Java 17 so they do not depend on virtual threads.

## 7. Invariants Across All Three Models

### 7.1. TCP Is a Byte Stream; Message Framing Is Mandatory

TCP does not preserve message boundaries. A single 2 KB send may be received across multiple reads; two sends may be coalesced into a single read. For a real protocol, you must clearly specify:

- **Delimiter** such as a newline character; must account for encoding, length limits, and delimiters appearing inside payloads.
- **Length prefix** such as a 4-byte length in network byte order; read the full header, validate that the length is legal, then read the full payload.
- **Fixed-size** when the format is genuinely fixed; or a standard protocol that already defines framing.

**Do not** assume "one read equals one request." The three examples above intentionally exchange one byte to illustrate the waiting mechanism itself; they are not multi-message TCP parsers.

### 7.2. Short Reads, Partial Writes, and EOF

With **ByteBuffer**, check **hasRemaining()**, **position/limit/flip/compact()**. When a message does not yet have enough bytes, retain state to receive the rest; when a write is incomplete, keep the buffer in an outbound queue. Never discard the remainder after a **write()** returns fewer bytes than requested.

A **-1** result on read indicates the peer closed its sending direction (EOF); **0** from a non-blocking channel usually means the attempt made no progress. EOF does not mean all application data has been processed or responses acknowledged. You may need half-close, application-layer flushing, and protocol-specific acknowledgments.

### 7.3. Backpressure Is a Policy, Not Automatic

If clients send faster than you can parse, process, and write replies, queues can grow without bound in blocking, selector, and async models alike. Set concrete limits: number of connections, pending reads, frame size, total buffered bytes, outbound queue, wait times, and per-client rate.

In a selector, you can temporarily pause interest in **OP_READ** for an overloaded connection and re-enable it once data has been consumed. In async, initiate the next read only when the system still has capacity. If overload persists, return a valid protocol error or close the connection by policy instead of consuming unbounded memory.

### 7.4. Timeouts, Cancellation, and Close Have Different Scopes

| Need | Blocking API | Non-blocking/Selector | Asynchronous API |
|---|---|---|---|
| Wait for connection | **Socket.connect(addr, timeout)** | Application deadline + **OP_CONNECT/finishConnect()** | Track Future/callback and deadline |
| Wait for read bytes | **Socket.setSoTimeout(...)** for read calls | **select(timeout)** only limits readiness wait time; need a **per-connection/request** deadline | Use read/write overloads with timeout when appropriate, or application-managed deadline/cancellation |
| Stop operation | Timeout/close/interrupt depending on API and state | Clear interest, cancel key, close channel | Cancel Future or close channel; handle error/callback on completion |
| Release resources | Close socket/stream | Cancel key and close channel; release buffers/queues | Close channel; shut down channel group if owned by the application |

**Future.get(timeout)** only limits how long **the thread waiting on the Future** waits; throwing **TimeoutException** from get does not guarantee the underlying I/O operation was canceled. With async, do not initiate a new read on the same channel while a previous read may still be pending. Choose an end-to-end deadline for the request and define clearly how cancellation, cleanup, and logging work.

### 7.5. Errors, Ordering, and Thread Safety

Connection reset, EOF, timeouts, mid-stream closure, parse errors, and malicious data must be handled in all three models. With event loops/callbacks, callbacks may touch state from multiple threads: establish conventions for who owns buffers, who may mutate queues, and when a channel may be closed. Avoid sharing the same **ByteBuffer** so multiple independent reads/writes do not mutate **position** concurrently.

**Do not treat network I/O as the whole request.** DNS resolution, TLS handshakes, databases, synchronous logging, JSON conversion, and application logic can introduce other blocking/CPU points. For non-blocking TLS, **SSLEngine** also adds handshake state, underflow/overflow, and application/network buffers; blocking **SSLSocket** is often easier to use when no suitable event loop infrastructure exists.

## 8. Which One Should You Choose for Your System?

| Context | Option to consider first | Why |
|---|---|---|
| CLI tools, small proxies, few clients, sequential processing | Blocking Socket, explicit timeouts | Simple, easy to test and operate |
| Server with many long-lived, mostly idle connections needing event-loop control | Non-blocking SocketChannel + Selector or a proven framework | Multiplexes readiness across few threads, proactive backpressure |
| Application already has a completion/Future layer and wants to decouple I/O initiation from response | AsynchronousSocketChannel or a suitable async library | Easy to structure completion chains when state is managed properly |
| Java 21+ service wanting sequential code for very many I/O tasks | Blocking API with virtual threads, while measuring resources | Keeps code readable while reducing platform-thread-per-task cost in many cases |
| CPU-heavy payloads, slow DB or downstream dependencies | Choose I/O model by workload, while bounding concurrency and separating workers | Changing the socket API alone will not solve CPU/DB bottlenecks |

**How to evaluate in practice:** benchmark the same workload with concurrent connections, idle ratio, frame size, request rate, p50/p95/p99 latency, CPU, heap/direct memory, thread count, backlog, queues, and timeout rate. Measure with equivalent protocol/framing, timeouts, and backpressure so the comparison is fair.

### Misconceptions to Avoid

1. **"Non-blocking means select() does not block."** False. Selector can block the thread waiting for readiness; only the configured channels' socket I/O is non-blocking.
2. **"Readable means a complete message will be read."** False. Readiness does not tell you the byte count of an application message, and read can return 0.
3. **"Async always uses fewer threads."** Not guaranteed. The provider, callbacks, channel group, and processing work determine the actual thread count.
4. **"One write corresponds to one read on the receiver."** False for TCP: it is a stream.
5. **"Future.get with a timeout has canceled the I/O."** False; timing out the wait operation does not automatically prove the I/O was canceled.
6. **"Keep OP_WRITE enabled permanently so events aren't missed."** Usually creates a continuous wakeup loop; enable it only when buffers remain to be sent.
7. **"Using virtual threads means switching to async callbacks."** False. That is a thread-scheduling model; the program API can still be blocking.

## 9. Self-Check Exercises

1. **Run the three Java 17 files** and observe their output; set breakpoints at **accept/read**, **selector.select/read**, and **CompletionHandler.completed** to see where execution waits and where results arrive.
2. **Replace the one-byte protocol with a length-prefix:** the client sends a 4-byte length followed by a UTF-8 payload. Write a function to read all 4 bytes, validate 0 <= length <= maximum, and read the full length; deliberately send the payload in multiple chunks and coalesce multiple messages onto one socket.
3. **Test partial writes on non-blocking:** build an outbound queue, write until **write** returns 0 or the buffer is empty; enable **OP_WRITE** only while the queue is non-empty. Observe CPU when OP_WRITE is kept permanently enabled to see why it must be turned off.
4. **Test slow clients and mid-stream disconnects:** set deadlines, bound queues, log close reasons, and verify there are no buffer/socket leaks and no two pending async reads initiated concurrently.
5. **Compare by measurement:** test 100, 1,000, and more idle connections in a controlled environment; keep payload/timeouts similar, and measure p99 latency, memory, thread count, and CPU instead of looking only at requests/second.

## 10. Check Your Understanding

- **A non-blocking read returns 0: what should you do?** Keep buffer state, wait for appropriate readiness or the next dispatch cycle; do not treat it as EOF, and do not spin continuously.
- **Does Selector reporting OP_READ mean a complete packet has arrived?** Not yet; you must read, check the byte count, and apply framing at the protocol layer.
- **Async read uses a handler, and main still calls get(): is it still asynchronous?** The read operation uses an asynchronous completion mechanism, but the thread calling get is still blocked while waiting; distinguish the I/O API from how the calling thread is organized.
- **What determines scalability?** Protocol contract, connection count/load, waiting mechanism, per-request cost, callbacks/workers, resource limits, and backpressure — not just the API name.

**Remember:** **blocking** describes *whether the thread must wait inside the call*; **non-blocking + Selector** describes *trying I/O and being notified of readiness*; **asynchronous** describes *initiating an operation and receiving completion*. All three must read/write the right number of bytes, handle EOF and timeouts, bound resources, and be measured under real load.
# Comparing TCP Handling with Thread Pools, Virtual Threads, and Selector

## 1. Three Models Serving the Same TCP Problem

A TCP server must accept connections, receive a byte stream, frame messages from the stream, execute business logic, write responses, and clean up resources. There are three prominent models in Java:

1. **Platform thread pool:** uses **ServerSocket + Socket + ThreadPoolExecutor** with a limited number of platform workers. The read/write APIs are blocking; a worker is held while waiting for I/O.
2. **Virtual threads (JDK 21+):** uses the same blocking ServerSocket/Socket, but **each task/connection gets a virtual thread**. The JVM can unmount a virtual thread when it waits on compatible I/O, freeing the platform carrier to serve other work.
3. **Selector (Java NIO):** uses non-blocking **ServerSocketChannel/SocketChannel**, monitoring **OP_ACCEPT/OP_READ/OP_WRITE** with **Selector**. A single event loop services the readiness of many channels and manages read/write state itself.

**There is no single fastest model for every workload.** You need to distinguish concurrent connections, request count, I/O wait time, CPU usage, memory, socket count, and the cost of writing/maintaining code.

~~~text
PLATFORM POOL                   VIRTUAL THREADS                 SELECTOR
ServerSocket.accept()          ServerSocket.accept()           ServerSocketChannel
    |                               |                             OP_ACCEPT
accepted sockets               accepted sockets                    |
    |                               |                         SocketChannels
bounded task queue             virtual thread / socket             |
    |                               |                         Selector.select()
4 platform workers             JVM scheduling on carriers          |
    |                               |                         OP_READ -> OP_WRITE
blocking read/write            blocking read/write                 |
each idle read holds worker    idle wait usually unmounts VT   non-blocking read/write
~~~

### Experimental Goal

This lesson provides **a shared comparison program**, using the same ASCII TCP request/response:

~~~text
Client -> Server: PING\n (5 bytes)
Server -> Client: PONG\n (5 bytes)
Each connection handles exactly one request, then the server closes the socket.
~~~

All three implementations must receive **PING + LF** accurately, respond with **PONG + LF** accurately, count all connections, and close resources. The client uses the same way of creating TCP sockets, the same concurrency level, and the same timeouts. **Smoke tests verify correctness**, not replace production benchmarks.

## 2. TCP Is a Byte Stream: Get Framing Right First

TCP does not preserve the boundaries of write calls. A client calling write for 5 bytes does not guarantee the server receives all 5 bytes in **one** read. Possible cases include:

~~~text
Client write: P I N G LF

Server read #1: P
Server read #2: I N
Server read #3: G LF

Or all 5 bytes in a single read.
Both are valid under TCP.
~~~

With a **blocking InputStream**, read the required number of bytes in a loop. With a **non-blocking SocketChannel**, read into a ByteBuffer across multiple events, check how many bytes have arrived, and switch from OP_READ to OP_WRITE once the request is complete.

| Scenario | Blocking Socket | Non-blocking SocketChannel |
| --- | --- | --- |
| No bytes available yet | **read** may block the worker | **read** may return **0**, not EOF |
| Partial message available | **read** may return fewer than requested | ByteBuffer position advances, keep waiting for readiness |
| Client closes sending side | **read returns -1** on EOF | **read returns -1** on EOF |
| Writing response | **write** may block until accepted per OutputStream semantics | **write** may write fewer than buffer.remaining or **0** |
| Connection error | IOException, need to close Socket | IOException, cancel key and close channel |
| Splitting multiple messages | Must use length-prefix/delimiter/framing | Must track state, flip/compact, handle partial frames |

The lab protocol is a **fixed-size 5-byte message**, not a full parser. Real systems usually need length-prefixing or delimiters with a **length limit** and may handle multiple requests/connection. Do not use **readAllBytes()** on an unbounded untrusted TCP stream; it can block until EOF or consume large amounts of RAM.

## 3. Platform Thread Pool: Simple, but Limited by I/O Waiting

### 3.1. Model

~~~java
// Java 17 snippet: named variables/functions belong to the application.
while (!listener.isClosed()) {
    Socket accepted = listener.accept();
    pool.execute(() -> {
        try (accepted) {
            handleBlocking(accepted);
        } catch (IOException failure) {
            recordError(failure);
        }
    });
}
~~~

**accept()** waits for a new connection, then **pool.execute** hands the task to workers. With **4 platform workers**, if 4 connections are waiting on **InputStream.read()**, no worker is free for a fifth connection, even if the fifth connection has already sent the full PING. New sockets may be accepted and queued, or rejected if the limits are full.

### 3.2. Bounded Queue and Backpressure

~~~java
ExecutorService workers = new ThreadPoolExecutor(
        4, 4, 0, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<Runnable>(128),
        threadFactory,
        new ThreadPoolExecutor.AbortPolicy());
~~~

This is a snippet (threadFactory is application-defined). **newFixedThreadPool(4)** uses an unbounded queue per its Javadoc; under uncontrolled traffic, a long queue drives up memory, open sockets, and latency. **ArrayBlockingQueue(128)** caps pending tasks. **AbortPolicy** throws RejectedExecutionException when full; the accept loop must close the new socket on rejection, record metrics, and apply an admission policy.

**Beware of CallerRunsPolicy:** if the pool is full, it runs the task directly on the thread calling execute. If the caller is the **accept loop**, a blocking handler can occupy the accept thread and prevent the server from accepting further sockets. Some applications deliberately use caller-runs for throttling, but you must clearly understand the consequences.

### 3.3. When Is It Appropriate?

For moderate concurrency and Java 17 code already using blocking I/O, a pool is easy to understand, easy to debug via stacktraces, and sizable for CPU/downstream capacity. However, **scaling from 4 to several thousand platform threads** is not free: OS threads carry stack/native memory, scheduling/context-switching overhead, and operating system limits.

Separate CPU-bound workloads from network-wait workloads when needed. Capping workers at the number of CPU cores can make sense for CPU-heavy tasks, but is poorly suited to many idle sockets waiting on read.

## 4. Virtual Threads: Many Blocking Tasks Without Pooling the Threads Themselves

### 4.1. Supported Versions

**Virtual threads were standardized in Java 21 (JEP 444)**. JDK 17 does not have standard public APIs **Executors.newVirtualThreadPerTaskExecutor()** or **Thread.isVirtual()**. Java 19–20 had previews, but this lesson uses the stable **Java 21+** API.

~~~java
// Java 21+ snippet; server/handleBlocking variables are application-defined.
try (ExecutorService perTask =
        Executors.newVirtualThreadPerTaskExecutor()) {
    while (accepting) {
        Socket socket = server.accept();
        perTask.submit(() -> {
            try (socket) {
                handleBlocking(socket);
            } catch (IOException error) {
                recordError(error);
            }
        });
    }
}
~~~

**Virtual threads are not faster platform threads per computation.** They help when many concurrent tasks are mostly **waiting on blocking I/O**: the JVM can usually suspend the virtual thread, yielding its carrier platform thread to another task. For CPU-bound loops, CPU core count remains the limit.

### 4.2. Do Not Pool Virtual Threads, but Still Limit Load

Do not create a fixed pool of **4 virtual threads** just to mimic a platform thread pool; you should normally create **one virtual thread/task**. Still, each task holds data, a socket, and buffers, and can put load on a database, HTTP service, or disk.

Limit **admitted sockets/tasks**, **DB pool size**, **file descriptors**, **memory**, **request size**, **deadlines**, and **downstream rate**:

~~~java
// Java 21+ snippet. perTask, socket, handleBlocking are already created.
Semaphore permits = new Semaphore(64);

if (!permits.tryAcquire()) {
    socket.close();
} else {
    perTask.submit(() -> {
        try {
            handleBlocking(socket);
        } finally {
            permits.release();
            try {
                socket.close();
            } catch (IOException ignored) {}
        }
    });
}
~~~

The example uses **tryAcquire** so it does not block the accept loop when the quota is full. In a real system, handle **Executor.execute/submit rejection** so permits or sockets are not leaked, and define a clear load-shedding policy and metrics.

### 4.3. Virtual Thread Pinning Depends on Version

On **JDK 21–23**, a virtual thread blocking inside certain **synchronized monitors/native frames** can become **pinned** to its carrier platform thread, hurting scalability. **JDK 24 (JEP 491)** significantly improves synchronized-monitor pinning; you still need to monitor native/foreign blocking and libraries. Do not apply JDK 21 pinning conclusions to all future JDK versions.

If an application uses many ThreadLocal caches, one cache per virtual thread can consume a lot of memory. Monitor **JFR, thread dumps, carrier saturation, and downstream pools**, not just the virtual thread count.

### 4.4. Standalone Runnable Java 21 Native Program

**VirtualThreadApi21.java:**

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadApi21 {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Boolean> future = executor.submit(
                    () -> Thread.currentThread().isVirtual());
            if (!future.get()) throw new AssertionError("Not virtual");
            System.out.println("Java 21 virtual thread API: PASS");
        }
    }
}
~~~

Compile/run with JDK 21+:

~~~bash
javac --release 21 -encoding UTF-8 VirtualThreadApi21.java
java VirtualThreadApi21
~~~

Actual stdout verified on OpenJDK 24:

~~~text
Java 21 virtual thread API: PASS
~~~

## 5. Selector: Multiplex Channels, Do Not Block the Event Loop

### 5.1. Readiness and State Machine

~~~java
// Java 17 snippet; selector, server, running are managed by the application.
server.configureBlocking(false);
server.register(selector, SelectionKey.OP_ACCEPT);

while (running) {
    selector.select();
    Iterator<SelectionKey> it =
            selector.selectedKeys().iterator();
    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove();
        // OP_ACCEPT, OP_READ, OP_WRITE by state.
    }
}
~~~

**Selector.select()** reports readiness, **not** that a full message has arrived. **SelectionKey** holds the channel, interestOps, and attachment. A connection typically has state containing an **input ByteBuffer**, an **output ByteBuffer**, and framing info.

### 5.2. Read 0 vs. EOF -1

~~~java
int n = channel.read(state.input);
if (n == -1) {
    // EOF: close channel and cancel key.
} else if (n == 0) {
    // No new bytes in this non-blocking read.
} else {
    // Bytes received; keep accumulating until the message is complete.
}
~~~

If using a 5-byte buffer for PING LF, **state.input.hasRemaining()** tells you whether bytes are still missing. Only when complete do you call **flip()**, validate the 5 bytes, and switch to OP_WRITE. For multi-frame protocols, use **flip/compact** to retain unprocessed bytes; do not recreate the buffer and lose previously read data.

### 5.3. Partial Write and OP_WRITE Busy Spin

~~~java
channel.write(state.output);
if (!state.output.hasRemaining()) {
    key.cancel();
    channel.close();
} else {
    key.interestOps(SelectionKey.OP_WRITE);
}
~~~

Even when writing only 5 bytes, a **non-blocking write can be partial**. Closing the channel early truncates the response. Keeping OP_WRITE enabled when output is empty means the channel is usually continuously writable and select can wake up repeatedly, burning CPU. The right approach is to **disable OP_WRITE or close the connection** when no bytes remain to send.

### 5.4. Selected Keys, Cancellation, and Shutdown

- Use **iterator.remove()** when processing selectedKeys to avoid reprocessing readiness.
- **SelectionKey.cancel()** only cancels registration; **SocketChannel.close()** is what releases the socket.
- When shutting down from another thread, **selector.wakeup()** wakes select so the loop can exit and close registrations.
- Wrap per-key handling in its own try/catch to isolate faulty connections; prevent one client sending bad data from crashing the entire event loop.
- If you want to offload business work, do not mutate attachment/interestOps asynchronously at will: use a cross-thread queue, wakeup, and clear ownership.

**Do not call blocking JDBC, Thread.sleep, or heavy CPU parsing inside the event loop**. A blocked event loop delays readiness for every channel it manages. For production TLS + Selector, you must handle **SSLEngine handshake/wrap/unwrap**, buffers, and timeouts; it is usually better to use a mature NIO framework rather than building a TLS server from a demo.

## 6. Comparison Table

| Criterion | Platform pool | Virtual threads | Selector |
| --- | --- | --- | --- |
| **JDK** | Java 17+ | Java 21+ | Java 17+ |
| **Socket API** | Blocking Socket | Blocking Socket | Non-blocking SocketChannel |
| **Dispatch model** | Fixed platform worker pool | Virtual thread per connection | Event loop/Selector readiness |
| **Idle socket** | Can hold 1 worker in read | Virtual task usually unmounts while waiting | No thread needed per idle socket |
| **Code** | Sequential, simple | Sequential, simple | State machine, more complex |
| **Concurrency control** | Workers, queue, backlog | In-flight/permit/downstream quota | Sockets, event loop, buffers, backpressure |
| **Partial read/write** | Framing needed; blocking read/write | Framing needed; blocking read/write | Must retain ByteBuffer across events |
| **Common pitfalls** | Worker starvation, unbounded queue | FD/memory/downstream overload, JDK-dependent pinning | OP_WRITE spin, buffer leak, blocked event loop |
| **CPU-heavy tasks** | Can run on CPU workers | Not automatically faster, still core-bound | Must offload off the event loop |
| **Observability** | Platform thread dump, queue depth | Virtual thread dump/JFR, downstream metrics | Selected keys, per-channel state, loop latency |
| **Best fit** | Moderate concurrency, legacy Java 17 | Many I/O-wait tasks, JDK 21+ | Non-blocking protocols, many sockets and streaming |

**Decide based on workload**: 30 ultra-short connections can be handled well by a fixed pool; 10,000 idle sockets have different characteristics. Do not equate **connection capacity** with **req/s throughput** or p95 latency.

## 7. Shared Experimental Code — TcpModelsLab.java

The full example has **a single client harness** for all three modes and a common PING LF → PONG LF protocol. It **compiles with --release 17**; the **POOL/SELECTOR** modes use Java 17 APIs. To compare virtual mode in the same Java 17-compatible file, the program invokes **newVirtualThreadPerTaskExecutor** via **reflection** when running on JDK 21+, and uses reflection to verify **Thread.isVirtual()** on the handler. That is a bridge for the lab, **not a pattern to use in Java 21 production**.

- **POOL:** four workers, ArrayBlockingQueue(128), AbortPolicy.
- **VIRTUAL:** per-task virtual thread executor, Semaphore(64) limiting admitted connections.
- **SELECTOR:** one event-loop thread, OP_ACCEPT/READ/WRITE, input/output ByteBuffers in the attachment, handling EOF and partial writes.
- **Client generator:** 12 platform client workers, connecting to 127.0.0.1:dynamic port, connect/read timeout, verifying every response byte.
- **--smoke:** 30 requests/mode; deterministic output based on PASS conditions.
- **--measure:** 30 warmup + 120 measured requests/mode; prints **environment-dependent** elapsed/p50/p95.
- Cleans up sockets, selector, and executors in finally/close, asserting zero handling errors.

### File TcpModelsLab.java

~~~java
import java.io.*;
import java.lang.reflect.Method;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class TcpModelsLab {
    enum Mode { POOL, VIRTUAL, SELECTOR }
    static final byte[] REQUEST = "PING\n".getBytes(StandardCharsets.US_ASCII);
    static final byte[] RESPONSE = "PONG\n".getBytes(StandardCharsets.US_ASCII);
    static final InetAddress LOOPBACK;

    static {
        try {
            LOOPBACK = InetAddress.getByName("127.0.0.1");
        } catch (UnknownHostException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    static void require(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
    }

    static ThreadFactory named(String prefix) {
        AtomicInteger serial = new AtomicInteger();
        return task -> new Thread(task, prefix + "-" + serial.incrementAndGet());
    }

    // Reflection keeps the source compatible with --release 17.
    // In Java 21 production, call the typed API directly.
    static ExecutorService virtualExecutor() {
        try {
            Method factory = Executors.class.getMethod("newVirtualThreadPerTaskExecutor");
            return (ExecutorService) factory.invoke(null);
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("Virtual threads require JDK 21+", e);
        }
    }

    static boolean isCurrentVirtual() {
        try {
            return Boolean.TRUE.equals(
                    Thread.class.getMethod("isVirtual").invoke(Thread.currentThread()));
        } catch (ReflectiveOperationException e) {
            return false;
        }
    }

    static class ConnectionState {
        final ByteBuffer input = ByteBuffer.allocate(REQUEST.length);
        ByteBuffer output;
    }

    static class LabServer implements AutoCloseable {
        final Mode mode;
        final AtomicInteger handled = new AtomicInteger();
        final AtomicInteger virtualVerified = new AtomicInteger();
        final AtomicReference<Throwable> failure = new AtomicReference<>();
        final AtomicBoolean running = new AtomicBoolean(true);
        final Semaphore virtualPermits = new Semaphore(64);
        ServerSocket blockingListener;
        ServerSocketChannel nioListener;
        Selector selector;
        ExecutorService workers;
        Thread loop;
        int port;

        LabServer(Mode mode) throws IOException {
            this.mode = mode;
            if (mode == Mode.SELECTOR) {
                selector = Selector.open();
                nioListener = ServerSocketChannel.open();
                nioListener.configureBlocking(false);
                nioListener.bind(new InetSocketAddress(LOOPBACK, 0), 128);
                nioListener.register(selector, SelectionKey.OP_ACCEPT);
                port = ((InetSocketAddress) nioListener.getLocalAddress()).getPort();
                loop = new Thread(this::selectorLoop, "selector-event-loop");
            } else {
                blockingListener = new ServerSocket(0, 128, LOOPBACK);
                port = blockingListener.getLocalPort();
                workers = (mode == Mode.POOL)
                        ? new ThreadPoolExecutor(4, 4, 0, TimeUnit.MILLISECONDS,
                                new ArrayBlockingQueue<Runnable>(128),
                                named("platform-worker"), new ThreadPoolExecutor.AbortPolicy())
                        : virtualExecutor();
                loop = new Thread(this::acceptLoop, "accept-" + mode);
            }
            loop.start();
        }

        void acceptLoop() {
            while (running.get()) {
                Socket socket = null;
                try {
                    socket = blockingListener.accept();
                    socket.setSoTimeout(5000);
                    Socket taskSocket = socket;
                    if (mode == Mode.VIRTUAL && !virtualPermits.tryAcquire()) {
                        taskSocket.close();
                        failure.compareAndSet(null,
                                new IOException("Virtual connection limit reached"));
                        continue;
                    }
                    workers.execute(() -> {
                        try {
                            serveBlocking(taskSocket);
                        } finally {
                            if (mode == Mode.VIRTUAL) virtualPermits.release();
                        }
                    });
                } catch (RejectedExecutionException rejected) {
                    if (socket != null) {
                        try { socket.close(); } catch (IOException ignored) {}
                    }
                    failure.compareAndSet(null, rejected);
                } catch (IOException error) {
                    if (running.get()) failure.compareAndSet(null, error);
                    break;
                }
            }
        }

        void serveBlocking(Socket socket) {
            try (socket) {
                if (mode == Mode.VIRTUAL) {
                    require(isCurrentVirtual(), "Expected a virtual thread");
                    virtualVerified.incrementAndGet();
                }
                InputStream in = socket.getInputStream();
                for (byte expected : REQUEST) {
                    if (in.read() != (expected & 0xff)) {
                        throw new IOException("Invalid input line");
                    }
                }
                OutputStream out = socket.getOutputStream();
                out.write(RESPONSE);
                out.flush();
                handled.incrementAndGet();
            } catch (Throwable error) {
                failure.compareAndSet(null, error);
            }
        }

        void selectorLoop() {
            try {
                while (running.get()) {
                    selector.select(300);
                    Iterator<SelectionKey> it = selector.selectedKeys().iterator();
                    while (it.hasNext()) {
                        SelectionKey key = it.next();
                        it.remove();
                        if (!key.isValid()) continue;
                        try {
                            if (key.isAcceptable()) {
                                SocketChannel channel = nioListener.accept();
                                if (channel != null) {
                                    channel.configureBlocking(false);
                                    channel.register(selector, SelectionKey.OP_READ,
                                            new ConnectionState());
                                }
                            } else {
                                if (key.isReadable()) onRead(key);
                                if (key.isValid() && key.isWritable()) onWrite(key);
                            }
                        } catch (IOException | RuntimeException error) {
                            failure.compareAndSet(null, error);
                            closeKey(key);
                        }
                    }
                }
            } catch (IOException error) {
                if (running.get()) failure.compareAndSet(null, error);
            } finally {
                try {
                    for (SelectionKey key : new ArrayList<>(selector.keys())) {
                        closeKey(key);
                    }
                    selector.close();
                } catch (IOException ignored) {}
            }
        }

        void onRead(SelectionKey key) throws IOException {
            SocketChannel channel = (SocketChannel) key.channel();
            ConnectionState state = (ConnectionState) key.attachment();
            int read = channel.read(state.input);
            if (read < 0) {
                closeKey(key);
                return;
            }
            if (read == 0 || state.input.hasRemaining()) return;
            state.input.flip();
            byte[] received = new byte[REQUEST.length];
            state.input.get(received);
            if (!Arrays.equals(received, REQUEST)) {
                throw new IOException("Invalid request bytes");
            }
            state.output = ByteBuffer.wrap(RESPONSE.clone());
            key.interestOps(SelectionKey.OP_WRITE);
        }

        void onWrite(SelectionKey key) throws IOException {
            SocketChannel channel = (SocketChannel) key.channel();
            ConnectionState state = (ConnectionState) key.attachment();
            channel.write(state.output); // may write partially
            if (!state.output.hasRemaining()) {
                handled.incrementAndGet();
                closeKey(key);
            }
        }

        static void closeKey(SelectionKey key) {
            if (key != null) {
                key.cancel();
                try { key.channel().close(); } catch (IOException ignored) {}
            }
        }

        void awaitHandled(int expected) throws InterruptedException {
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
            while (handled.get() < expected && System.nanoTime() < deadline) {
                Thread.sleep(5);
            }
            require(handled.get() == expected,
                    mode + ": expected " + expected + " handled, got " + handled.get());
            require(failure.get() == null,
                    mode + ": server failure: " + failure.get());
            if (mode == Mode.VIRTUAL) {
                require(virtualVerified.get() == expected,
                        "Not all tasks ran in virtual threads");
            }
        }

        @Override public void close() throws Exception {
            running.set(false);
            if (mode == Mode.SELECTOR) {
                selector.wakeup();
            } else {
                blockingListener.close(); // wake up accept()
            }
            loop.join(3000);
            require(!loop.isAlive(), mode + ": server loop did not stop");
            if (workers != null) {
                workers.shutdown();
                if (!workers.awaitTermination(5, TimeUnit.SECONDS)) {
                    workers.shutdownNow();
                    require(workers.awaitTermination(5, TimeUnit.SECONDS),
                            mode + ": executor did not stop");
                }
            }
            require(failure.get() == null,
                    mode + ": asynchronous error: " + failure.get());
        }
    }

    static class Measurement {
        final long totalNanos;
        final long[] latencyNanos;
        Measurement(long totalNanos, long[] latencyNanos) {
            this.totalNanos = totalNanos;
            this.latencyNanos = latencyNanos;
        }
        double percentileMs(double fraction) {
            long[] sorted = latencyNanos.clone();
            Arrays.sort(sorted);
            int index = Math.max(0, (int) Math.ceil(sorted.length * fraction) - 1);
            return sorted[index] / 1_000_000.0;
        }
    }

    static Measurement runClients(LabServer server, int count, int concurrency)
            throws Exception {
        ExecutorService clients = Executors.newFixedThreadPool(
                concurrency, named("test-client"));
        List<Future<Long>> results = new ArrayList<>();
        long start = System.nanoTime();
        try {
            for (int i = 0; i < count; i++) {
                results.add(clients.submit(() -> {
                    long started = System.nanoTime();
                    try (Socket socket = new Socket()) {
                        socket.connect(
                                new InetSocketAddress(LOOPBACK, server.port), 3000);
                        socket.setSoTimeout(3000);
                        socket.getOutputStream().write(REQUEST);
                        socket.getOutputStream().flush();
                        InputStream input = socket.getInputStream();
                        for (byte expected : RESPONSE) {
                            require(input.read() == (expected & 0xff),
                                    "Incorrect PONG response");
                        }
                        return System.nanoTime() - started;
                    }
                }));
            }
            long[] latencies = new long[count];
            for (int i = 0; i < results.size(); i++) {
                latencies[i] = results.get(i).get(8, TimeUnit.SECONDS);
            }
            return new Measurement(System.nanoTime() - start, latencies);
        } finally {
            clients.shutdownNow();
            require(clients.awaitTermination(5, TimeUnit.SECONDS),
                    "Client workers did not stop");
        }
    }

    public static void main(String[] args) throws Exception {
        boolean measure = args.length == 1 && "--measure".equals(args[0]);
        if (args.length > 1 ||
                (args.length == 1 && !measure && !"--smoke".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Usage: java TcpModelsLab [--smoke|--measure]");
        }
        int count = measure ? 120 : 30;
        int warmup = measure ? 30 : 0;
        boolean virtualAvailable = Runtime.version().feature() >= 21;
        for (Mode mode : Mode.values()) {
            if (mode == Mode.VIRTUAL && !virtualAvailable) {
                System.out.println("VIRTUAL: SKIPPED (requires JDK 21+)");
                continue;
            }
            try (LabServer server = new LabServer(mode)) {
                if (warmup > 0) {
                    runClients(server, warmup, 12);
                    server.awaitHandled(warmup);
                }
                Measurement data = runClients(server, count, 12);
                server.awaitHandled(warmup + count);
                System.out.println(mode + ": PASS " + count + "/" + count);
                if (measure) {
                    System.out.printf(Locale.ROOT,
                            "%s metrics: elapsed_ms=%.2f p50_ms=%.2f p95_ms=%.2f%n",
                            mode, data.totalNanos / 1_000_000.0,
                            data.percentileMs(.50), data.percentileMs(.95));
                }
            }
        }
        System.out.println("All available models: PASS");
    }
}
~~~

### Running on Java 17+ and Java 21+

~~~bash
javac --release 17 -encoding UTF-8 TcpModelsLab.java
java TcpModelsLab --smoke
java TcpModelsLab --measure
~~~

**Smoke stdout run and verified on OpenJDK 24.0.2, a JDK supporting virtual threads:**

~~~text
POOL: PASS 30/30
VIRTUAL: PASS 30/30
SELECTOR: PASS 30/30
All available models: PASS
~~~

**When using a Java 17 runtime**, the virtual API is unavailable so the code intentionally skips that mode. Expected stdout format per program logic, **not yet run and verified on runtime 17**:

~~~text
POOL: PASS 30/30
VIRTUAL: SKIPPED (requires JDK 21+)
SELECTOR: PASS 30/30
All available models: PASS
~~~

**Measure mode ran successfully**: each mode completed 120/120 after 30 warmups; p50/p95 latencies and elapsed_ms are printed as floating-point numbers. Numbers always vary with JIT, OS, scheduling, CPU, GC, and machine conditions.

**One run on Windows OpenJDK 24/loopback (to illustrate output format only, not a production ranking):**

~~~text
POOL: PASS 120/120
POOL metrics: elapsed_ms=9.06 p50_ms=0.64 p95_ms=0.89
VIRTUAL: PASS 120/120
VIRTUAL metrics: elapsed_ms=9.94 p50_ms=0.56 p95_ms=0.91
SELECTOR: PASS 120/120
SELECTOR metrics: elapsed_ms=23.04 p50_ms=1.98 p95_ms=3.12
All available models: PASS
~~~

This **does not prove POOL is fastest**. There are only 12 client workers, 120 samples/mode, a workload with almost no I/O wait time, all running inside one JVM and over loopback. When increasing idle clients, blocking business work, WAN RTT, TLS, or streaming, the results can change completely.

### Code Walkthrough for Each Mode

**POOL:** ServerSocket accepts sockets; a bounded ThreadPoolExecutor provides up to 4 workers, each calling InputStream.read repeatedly to get 5 bytes and then OutputStream.write. The socket is closed via try-with-resources; rejections are recorded so the test fails rather than silently dropping requests.

**VIRTUAL:** accepts sockets and submits tasks to the virtual-thread-per-task executor (via Java 21+ reflection). The handler verifies an actual virtual thread, uses the blocking Socket API, and releases the permit in finally. If the quota of 64 is full, it closes the socket and records an overload error.

**SELECTOR:** non-blocking ServerSocketChannel registers OP_ACCEPT, accepted non-blocking SocketChannel registers OP_READ with a ConnectionState attachment; reads partially into a ByteBuffer, switches to OP_WRITE when the full PING is received and holds the output ByteBuffer until fully written; then increments handled and cancels the key/closes the channel. Shutdown uses selector.wakeup() and closes keys/channels.

**Client:** always sends the 5-byte REQUEST, then reads byte by byte to verify the 5-byte RESPONSE; each Socket has connect/read timeouts. After all client futures complete, it checks the handled count with a deadline and confirms there are no background errors.

### Limitations of the Lab Example

Each connection has only one exact 5-byte frame; the server does not support multiple consecutive PINGs on the same socket, oversized packets, TLS, authentication, half-close protocol, or full slow-client idle scanning. Selector mode has no explicit max-open-channel quota; production needs one. The virtual semaphore and pool queue are two different capacity policies: they are stated explicitly so learners **do not assume the measured results are an exact apples-to-apples resource comparison**.

## 8. How to Design a Reliable Benchmark

### Hold Important Variables Constant

| Variable group | What to control |
| --- | --- |
| Protocol | Same bytes, framing, messages/connection |
| Clients | Same concurrency, arrival rate, timeouts, reconnect policy |
| Server | Same bind address, payload, business logic, error policy |
| JVM | Same vendor/version, heap, GC, warmup, and flags |
| Host/network | CPU quota, RAM, FD limits, OS, route, loopback vs. WAN |
| Statistics | Request count, success/error, throughput, p50/p95/p99, confidence interval |
| Resources | CPU, platform threads, virtual threads, open sockets, heap/native/direct memory |
| Timing | Multiple runs, randomize test order, exclude warmup from measurement |

**A meaningful benchmark must report errors and timeouts**, not just throughput of successful requests. A mode that looks "fast" by dropping 20% of clients is not a good result.

### Idle Connection Load Is a Necessary Additional Test

Suppose **4 platform workers** are all waiting to read from 4 clients that connected without sending bytes yet. A fifth client sending a full PING may have to wait for a free worker. With virtual threads, many I/O-blocked tasks can usually unmount; with Selector, idle connections sit in registered keys without needing a worker per connection. To prove this, you must write a load test that holds idle sockets with quotas/timeouts, rather than extrapolating from a smoke test with only ultra-short requests.

### Time, Concurrency, and Little's Law

In steady state, **L ≈ λ × W**: average tasks in the system ≈ request arrival rate × average residence time. For example, at 100 requests/s with each request lasting 0.5 s, average in-flight requests are about 50. If each request waits 5 s, the same arrival rate can push in-flight requests to around 500. This explains why a small platform thread pool bottlenecks easily when the workload is mostly **waiting**, whereas VT/Selector help scale waiting concurrency (provided other resource quotas hold).

Do not treat Little's law as an exact prediction when the system is overloaded/unstable; queue growth, timeouts, and admission policies also affect it.

### Limitations of Loopback Microbenchmarks

Running client and server in the same JVM creates CPU/GC interference, and ultra-low RTT makes scheduler overhead stand out. To choose a production architecture, **separate the load generator**, measure multiple runs, and report p95/p99, errors, memory/FD, GC, CPU, waiting connections, request sizes, and behavior under overload. Use a profiler/JFR/thread dumps to explain *why* the numbers differ.

Do not use **Thread.sleep() inside the Selector loop** to simulate I/O wait: that creates event-loop blocking that the other two modes do not have, making the benchmark unfair. If the real workload needs downstream blocking, define it identically and offload it properly.

## 9. Production Rules for Backpressure, Timeouts, and Errors

### Platform Pool

Limit accept backlog, max active sockets, queue, worker threads, socket read timeout, and downstream calls. If execute rejects, **close the socket immediately** and record the rejection count. Never leave the queue unbounded. Graceful shutdown must stop accepting, drain/cancel active/queued sockets, and wait for the pool to terminate.

### Virtual Threads

One VT/connection does not mean unlimited admitted connections. Enforce a **Semaphore/connection quota**, memory/FD limits, socket timeouts, and downstream pools; release permits even when handlers fail or are canceled. Monitor native blocking/pinning per JDK, ThreadLocal allocations, JFR, and downstream queues. Do not call a virtual-thread-per-task executor a fixed pool; it creates a new thread for each task.

### Selector

Each channel has state and buffer ownership; handle read=0/-1, oversized messages, partial writes, OP_WRITE interest to avoid busy loops, EOF/half-close, cancellation, closing key/channel, and cross-thread wakeups. Set **idle timeouts, max channels, per-connection outgoing buffer caps**, and event-loop latency metrics. Offload CPU/JDBC/blocking business code to a bounded worker pool. **key.cancel() does not close the socket by itself**.

### Security and Networking

The demo uses plaintext TCP on **127.0.0.1** without TLS or authentication; do not expose it publicly. In production you need TLS (with non-blocking NIO this may require managing SSLEngine), authorization, rate limiting, anti-slowloris timeouts, a framing parser, and buffer quotas. File descriptors/OS backlog, firewalls, and host settings can become limits before the JVM hits thread limits.

## 10. Selection Scenarios

| Workload | Option to evaluate | Explanation |
| --- | --- | --- |
| Java 17, small TCP service, moderate concurrency | **Bounded platform pool** | Sequential code and simple operations |
| Java 21+, many requests mostly waiting on I/O | **Virtual threads** | Sequential blocking code without a platform worker per waiting task |
| Very many idle sockets, protocol/event-driven | **Selector or NIO framework** | Multiplexed readiness, few event-loop threads |
| CPU-heavy business logic | **Core-sized CPU worker pool** | Virtual threads do not add CPU cores; Selector must offload |
| Legacy blocking code, Java 21 migration | **Virtual threads + resource quotas** | Keep readable code, measure pinning/downstream |
| Application already using mature Netty/NIO framework | **Keep/measure existing framework first** | Avoid rewriting hard protocol, TLS, and backpressure logic |
| Need to compare real throughput | **Controlled load test** | Smoke/localhost is not enough to declare a winner |

## 11. Common Misconceptions

1. **“One TCP read = one message”** — False. TCP is a stream; you must frame.
2. **“Blocking Socket.read only uses CPU when bytes arrive”** — False for platform threads: the OS thread is still held while waiting, even if it uses little CPU.
3. **“newFixedThreadPool also bounds the number of waiting tasks”** — False: the default queue is unbounded.
4. **“Virtual threads make CPU calculations faster”** — False. You still need CPU resources and appropriate algorithms.
5. **“Pool virtual threads to save resources”** — Do not; bound resources with quotas/semaphores, do not recreate worker scarcity.
6. **“JDK 17 can call newVirtualThreadPerTaskExecutor directly”** — No. The API is stable starting in Java 21.
7. **“Selector select signals a complete response/request”** — False. Readiness is not completeness.
8. **“SocketChannel.read returning 0 means the client closed”** — False; **-1** is EOF.
9. **“SocketChannel.write always sends the whole buffer”** — False; you must retain partial output.
10. **“Keeping OP_WRITE always enabled makes the server fast”** — False; it easily causes busy-spinning.
11. **“SelectionKey.cancel also closes SocketChannel”** — False; you must close the channel.
12. **“Running Selector on one thread means all handler code is non-blocking”** — False; JDBC, sleep, or heavy CPU still blocks the loop.
13. **“A single 120-request loopback test is a production benchmark”** — False; you need multiple runs with realistic load.
14. **“10,000 virtual threads consume no resources”** — False; sockets, memory, and downstream systems have limits.
15. **“With JDK 24+, all blocking/native pinning disappears”** — False; JEP 491 improves synchronized monitors, other cases still need checking.
16. **“Seeing PASS responses means the server has no leaks”** — Not enough; check worker shutdown, FDs, pending channels, and timeouts/rejections.

## 12. Testing Checklist and Self-Check Questions

**Functional checklist:** test partial input, EOF before full PING, invalid requests, many concurrent connections, full responses, timeouts, and cleanup; for Selector, test OP_WRITE when 0/partial bytes are written under pressure.

**Benchmark checklist:** record Java version, OS, machine, heap, CPU, FD limit, identical protocol/traffic, warmup, errors, throughput, latency percentiles, platform/virtual threads, CPU/GC/memory, run duration, and noise-filtering method. Run multiple times and report numbers alongside conditions.

**Question 1.** Why can a 4-worker platform pool stall with four idle connections?  
**Answer:** All four workers can be waiting on blocking InputStream.read, forcing other tasks to wait.

**Question 2.** Can Java 17 run both the Selector and virtual threads models using the same direct APIs?  
**Answer:** Selector is in Java 17; the standard virtual threads API is only available from Java 21. The demo uses reflection at runtime on 21+ so a single `--release 17` source still compiles.

**Question 3.** What is the difference between a virtual thread and a platform thread?  
**Answer:** A virtual thread is a task scheduled by the JVM onto carrier platform threads; many I/O waits can unmount, avoiding holding an OS thread per waiting task.

**Question 4.** Why should you not create a fixed pool of 4 virtual threads?  
**Answer:** It recreates a worker bottleneck. Use one VT/task and bound sockets/downstream work with permits/quotas.

**Question 5.** With Selector, how do n=0 and n=-1 differ on read?  
**Answer:** 0 means no data was available in this non-blocking read; -1 means EOF.

**Question 6.** If only 2/5 bytes of the response were written, should you close the SocketChannel immediately?  
**Answer:** No. Keep the ByteBuffer and OP_WRITE until all bytes are sent, or cancel according to your error/timeout policy.

**Question 7.** Why is iterator.remove needed on selectedKeys?  
**Answer:** It removes the handled readiness event, preventing the key from remaining in the selected set and being processed repeatedly.

**Question 8.** What happens when an event loop calls blocking JDBC?  
**Answer:** It slows down all other channels; blocking work must be offloaded.

**Question 9.** Why can you not conclude which mode is fastest from a single loopback run?  
**Answer:** Low load, single JVM, scheduler/JIT/GC effects, and differing limit configurations; proper measurement is required.

**Question 10.** When many virtual threads wait on I/O, what limits still apply?  
**Answer:** Open sockets/FDs, memory, downstream pools, timeouts, CPU, and rate limits.

## Conclusion

**Platform thread pools** are a simple choice for moderate concurrency and blocking code; **virtual threads** preserve a sequential coding style when many tasks wait on I/O on JDK 21+; **Selector** multiplexes many channels with a non-blocking state machine, at the cost of careful buffer, readiness, backpressure, and cleanup management.

For a meaningful comparison, **keep the protocol and workload identical and verify correctness first**, then measure throughput, p50/p95/p99, errors, CPU, memory, and FDs across multiple runs. Instead of choosing a model by a "fastest" slogan, choose by **connection count, idle/active ratio, blocking type, latency requirements, JDK version, and operational complexity**.

### Official References

- [Java SE 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): blocking accept, backlog.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): blocking I/O, timeout.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): bounded queue/rejection.
- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): multiplexing, selectedKeys, cancel/wakeup.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking read/write.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): OP_ACCEPT/READ/WRITE/CONNECT.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): flip/remaining/compact.
- [Java SE 21 — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): newVirtualThreadPerTaskExecutor.
- [Oracle — Virtual Threads in Java 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): task-per-virtual-thread, carrier/unmount.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): Java 21 stable virtual threads.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): Java 24 changes.
- [RFC 9293 — TCP](https://www.rfc-editor.org/rfc/rfc9293.html): TCP byte-stream semantics.
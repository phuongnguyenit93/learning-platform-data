# So sánh xử lý TCP bằng nhóm luồng, luồng ảo và Selector

## 1. Ba mô hình phục vụ cùng một bài toán TCP

Một server TCP phải accept kết nối, nhận một byte stream, tách message từ stream, thực hiện nghiệp vụ, ghi response và dọn tài nguyên. Có ba mô hình nổi bật trong Java:

1. **Nhóm platform threads:** dùng **ServerSocket + Socket + ThreadPoolExecutor** với số platform workers giới hạn. API read/write là blocking; worker bị giữ trong khi chờ I/O.
2. **Virtual threads (JDK 21+):** dùng ServerSocket/Socket blocking tương tự nhưng **mỗi task/kết nối có một virtual thread**. JVM có thể unmount virtual thread khi nó chờ I/O tương thích, để platform carrier phục vụ việc khác.
3. **Selector (Java NIO):** dùng **ServerSocketChannel/SocketChannel** non-blocking, theo dõi **OP_ACCEPT/OP_READ/OP_WRITE** với **Selector**. Một event loop phục vụ readiness của nhiều channel, tự quản lý trạng thái đọc/ghi.

**Không có mô hình nhanh nhất cho mọi workload.** Cần phân biệt kết nối đồng thời, số request, thời gian đợi I/O, lượng CPU, memory, số sockets và chi phí viết/duy trì code.

~~~text
PLATFORM POOL                   VIRTUAL THREADS                 SELECTOR
ServerSocket.accept()          ServerSocket.accept()           ServerSocketChannel
    |                               |                             OP_ACCEPT
accepted sockets               accepted sockets                    |
    |                               |                         SocketChannels
bounded task queue             virtual thread / socket             |
    |                               |                         Selector.select()
4 platform workers             JVM scheduling trên carriers          |
    |                               |                         OP_READ -> OP_WRITE
blocking read/write            blocking read/write                 |
mỗi idle read giữ worker       idle wait thường unmount VT       non-blocking read/write
~~~

### Mục tiêu thực nghiệm

Bài học cung cấp **một chương trình so sánh chung**, dùng cùng request/response TCP ASCII:

~~~text
Client -> Server: PING\n (5 bytes)
Server -> Client: PONG\n (5 bytes)
Mỗi kết nối đúng một request rồi server đóng socket.
~~~

Cả ba implementation phải nhận đúng **PING + LF**, phản hồi đúng **PONG + LF**, đếm đủ kết nối và đóng tài nguyên. Client dùng cùng cách tạo TCP sockets, cùng mức concurrency, cùng timeout. **Smoke test kiểm tra correctness**, không thay phép benchmark production.

## 2. TCP là byte stream: trước tiên phải làm đúng framing

TCP không giữ ranh giới của các lời gọi write. Một client gọi write 5 bytes không bảo đảm server nhận cả 5 bytes trong **một** lần read. Các dạng có thể xảy ra:

~~~text
Client write: P I N G LF

Server read #1: P
Server read #2: I N
Server read #3: G LF

Hoặc cả 5 bytes trong một read.
Cả hai đều hợp lệ theo TCP.
~~~

Với **blocking InputStream**, đọc đủ số byte theo vòng lặp. Với **non-blocking SocketChannel**, đọc vào ByteBuffer qua nhiều sự kiện, kiểm tra số byte đã có, rồi đổi từ OP_READ sang OP_WRITE khi request đã hoàn chỉnh.

| Tình huống | Blocking Socket | Non-blocking SocketChannel |
| --- | --- | --- |
| Chưa có byte | **read** có thể chặn worker | **read** có thể trả **0**, không phải EOF |
| Có một phần message | **read** có thể trả ít hơn yêu cầu | ByteBuffer position tăng, tiếp tục chờ readiness |
| Client kết thúc chiều gửi | **read trả -1** khi tới EOF | **read trả -1** khi tới EOF |
| Ghi response | **write** có thể block tới khi nhận đủ theo semantics OutputStream | **write** có thể ghi ít hơn buffer.remaining hoặc **0** |
| Kết nối lỗi | IOException, cần close Socket | IOException, cancel key và close channel |
| Tách nhiều messages | Phải dùng length-prefix/delimiter/framing | Phải giữ state, flip/compact, xử lý partial frames |

Protocol lab là **fixed-size 5-byte message**, không phải parser đầy đủ. Hệ thống thật thường cần length-prefix hoặc delimiter có **giới hạn chiều dài** và có thể xử lý nhiều requests/connection. Không dùng **readAllBytes()** trên untrusted TCP stream không giới hạn; nó có thể block tới EOF hoặc chiếm nhiều RAM.

## 3. Platform thread pool: đơn giản nhưng có giới hạn chờ I/O

### 3.1. Mô hình

~~~java
// Java 17 snippet: named variables/functions thuộc ứng dụng.
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

**accept()** chờ kết nối mới, sau đó **pool.execute** giao task cho workers. Với **4 platform workers**, nếu 4 kết nối đang đứng chờ **InputStream.read()**, không có worker nào rảnh cho kết nối thứ năm, dù kết nối thứ năm đã gửi đủ PING. Các sockets mới có thể được accept rồi xếp trong queue, hoặc bị từ chối nếu giới hạn đã đầy.

### 3.2. Bounded queue và backpressure

~~~java
ExecutorService workers = new ThreadPoolExecutor(
        4, 4, 0, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<Runnable>(128),
        threadFactory,
        new ThreadPoolExecutor.AbortPolicy());
~~~

Đây là snippet (threadFactory được ứng dụng định nghĩa). **newFixedThreadPool(4)** dùng queue không giới hạn theo Javadoc; với traffic không kiểm soát, queue dài kéo theo memory, open sockets và latency. **ArrayBlockingQueue(128)** giới hạn pending tasks. **AbortPolicy** ném RejectedExecutionException khi full; accept loop phải đóng socket mới khi reject, ghi metrics và áp admission policy.

**Cảnh giác CallerRunsPolicy:** nếu pool đầy, nó chạy task ngay trong thread gọi execute. Nếu caller là **accept loop**, một blocking handler có thể chiếm accept thread và làm server không tiếp tục nhận sockets. Có ứng dụng cố tình dùng caller-runs làm throttle, nhưng phải hiểu rõ hậu quả.

### 3.3. Khi nào phù hợp?

Với concurrency vừa phải và code Java 17 đang dùng blocking I/O, pool dễ hiểu, dễ debug stacktraces, có thể định cỡ theo CPU/downstream. Nhưng **tăng từ 4 lên vài nghìn platform threads** không phải giải pháp miễn phí: OS threads có stack/native memory, scheduling/context switching và các giới hạn hệ điều hành.

Tách workload CPU-bound khỏi network-wait workload khi cần. Giới hạn số worker bằng số CPU cores có thể hợp lý cho tác vụ CPU nặng, nhưng lại kém phù hợp với nhiều socket nhàn rỗi đang chờ read.

## 4. Virtual threads: nhiều blocking tasks mà không pool chính các thread

### 4.1. Phiên bản hỗ trợ

**Virtual threads được chuẩn hóa trong Java 21 (JEP 444)**. JDK 17 không có public API chuẩn **Executors.newVirtualThreadPerTaskExecutor()** hay **Thread.isVirtual()**. Java 19–20 có preview, nhưng bài học dùng API ổn định **Java 21+**.

~~~java
// Java 21+ snippet; các biến server/handleBlocking do ứng dụng định nghĩa.
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

**Virtual threads không phải platform threads nhanh hơn theo từng phép tính.** Chúng hữu ích khi rất nhiều concurrent tasks chủ yếu đang **chờ blocking I/O**: JVM thường có thể tạm ngưng virtual thread, nhường carrier platform thread cho task khác. Với CPU-bound loops, số lõi CPU vẫn là giới hạn.

### 4.2. Không pool virtual threads, nhưng vẫn phải giới hạn tải

Không tạo một fixed pool **4 virtual threads** chỉ để bắt chước nhóm platform threads; thường nên tạo **một virtual thread/tác vụ**. Tuy nhiên, mỗi task vẫn giữ dữ liệu, socket, buffers, và có thể gây tải cho database, HTTP service hay disk.

Giới hạn **admitted sockets/tasks**, **DB pool size**, **file descriptors**, **memory**, **request size**, **deadline** và **downstream rate**:

~~~java
// Java 21+ snippet. perTask, socket, handleBlocking đã được tạo.
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

Ví dụ dùng **tryAcquire** để không block accept loop khi quota đầy. Với hệ thống thật, cần xử lý **Executor.execute/submit rejection** sao cho không rò permit hoặc socket, và định nghĩa policy từ chối tải/metrics rõ ràng.

### 4.3. Virtual thread pinning phụ thuộc phiên bản

Trên **JDK 21–23**, virtual thread blocking trong một số **synchronized monitor/native frames** có thể bị **pinned** lên carrier platform thread, ảnh hưởng khả năng scale. **JDK 24 (JEP 491)** cải thiện đáng kể synchronized-monitor pinning; vẫn cần giám sát native/foreign blocking và các libraries. Không áp kết luận pinning của JDK21 cho mọi phiên bản JDK về sau.

Nếu application dùng nhiều ThreadLocal caches, một cache per virtual thread có thể chiếm rất nhiều memory. Theo dõi **JFR, thread dumps, carrier saturation, downstream pools**, chứ không chỉ đếm số virtual threads.

### 4.4. Chương trình native Java 21 có thể chạy độc lập

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

Biên dịch/chạy với JDK21+:

~~~bash
javac --release 21 -encoding UTF-8 VirtualThreadApi21.java
java VirtualThreadApi21
~~~

Stdout thực tế đã kiểm thử trên OpenJDK24:

~~~text
Java 21 virtual thread API: PASS
~~~

## 5. Selector: multiplex channels, không block event-loop

### 5.1. Readiness và state machine

~~~java
// Java 17 snippet; selector, server, running do ứng dụng quản lý.
server.configureBlocking(false);
server.register(selector, SelectionKey.OP_ACCEPT);

while (running) {
    selector.select();
    Iterator<SelectionKey> it =
            selector.selectedKeys().iterator();
    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove();
        // OP_ACCEPT, OP_READ, OP_WRITE theo state.
    }
}
~~~

**Selector.select()** trả readiness, **không** báo toàn bộ message đã đến. **SelectionKey** duy trì channel, interestOps và attachment. Một connection thường có state gồm **input ByteBuffer**, **output ByteBuffer** và thông tin framing.

### 5.2. Read 0 khác EOF -1

~~~java
int n = channel.read(state.input);
if (n == -1) {
    // EOF: đóng channel và hủy key.
} else if (n == 0) {
    // Không có byte mới ở lần non-blocking read này.
} else {
    // Đã có bytes; tiếp tục tích lũy tới message đầy đủ.
}
~~~

Nếu dùng buffer 5 bytes cho PING LF, **state.input.hasRemaining()** giúp biết còn thiếu byte. Chỉ khi đủ, gọi **flip()**, kiểm tra 5 bytes rồi chuyển sang OP_WRITE. Với protocol nhiều frames, dùng **flip/compact** để giữ bytes chưa xử lý; đừng tạo lại buffer và mất phần dữ liệu đọc trước.

### 5.3. Partial write và OP_WRITE busy spin

~~~java
channel.write(state.output);
if (!state.output.hasRemaining()) {
    key.cancel();
    channel.close();
} else {
    key.interestOps(SelectionKey.OP_WRITE);
}
~~~

Ngay cả khi chỉ ghi 5 bytes, **non-blocking write có thể chỉ ghi một phần**. Nếu đóng channel sớm, response bị cắt. Nếu luôn giữ OP_WRITE dù output hết, channel thường liên tục writable và select có thể thức dậy liên tục, chiếm CPU. Đúng cách là **tắt OP_WRITE hoặc đóng kết nối** khi không còn bytes phải gửi.

### 5.4. Selected keys, cancellation và shutdown

- Dùng **iterator.remove()** khi xử lý selectedKeys để tránh readiness bị xử lý lại.
- **SelectionKey.cancel()** chỉ hủy đăng ký; **SocketChannel.close()** mới giải phóng socket.
- Khi shutdown từ thread khác, **selector.wakeup()** đánh thức select để kết thúc vòng lặp và close registrations.
- Bao quanh xử lý mỗi key bằng try/catch riêng, cô lập connection lỗi; tránh một client gửi dữ liệu sai làm chết toàn event loop.
- Nếu muốn offload business work, đừng sửa attachment/interestOps không đồng bộ tùy tiện: dùng queue cross-thread, wakeup và ownership rõ.

**Đừng gọi JDBC blocking, Thread.sleep hoặc CPU parse nặng trong event loop**. Một event loop block sẽ trì hoãn readiness của mọi channel mà nó quản lý. Với production TLS + Selector, phải xử lý **SSLEngine handshake/wrap/unwrap**, buffers, timeouts; thường nên dùng NIO framework trưởng thành thay vì tự tạo một TLS server từ demo.

## 6. Bảng so sánh

| Tiêu chí | Platform pool | Virtual threads | Selector |
| --- | --- | --- | --- |
| **JDK** | Java 17+ | Java 21+ | Java 17+ |
| **Socket API** | Blocking Socket | Blocking Socket | Non-blocking SocketChannel |
| **Cách dispatch** | Fixed platform worker pool | Virtual thread per connection | Event loop/Selector readiness |
| **Idle socket** | Có thể giữ 1 worker đang read | Virtual task thường unmount khi chờ | Không cần một thread cho mỗi idle socket |
| **Code** | Tuần tự, đơn giản | Tuần tự, đơn giản | State machine, phức tạp hơn |
| **Quản lý concurrency** | Workers, queue, backlog | In-flight/permit/downstream quota | Sockets, event loop, buffers, backpressure |
| **Partial read/write** | Có framing; blocking read/write | Có framing; blocking read/write | Bắt buộc giữ ByteBuffer giữa events |
| **Lỗi dễ gặp** | Worker starvation, unbounded queue | FD/memory/downstream overload, pinning tùy JDK | OP_WRITE spin, buffer leak, blocked event loop |
| **CPU-heavy tasks** | Có thể chạy trên worker CPU | Không tự nhanh hơn, vẫn giới hạn core | Cần offload khỏi event loop |
| **Quan sát** | Platform thread dump, queue depth | Virtual thread dump/JFR, downstream metrics | Selected keys, per-channel state, loop latency |
| **Phù hợp** | Concurrency vừa, legacy Java 17 | Rất nhiều I/O-wait tasks, JDK21+ | Protocol non-blocking, nhiều sockets và streaming |

**Quyết định dựa trên workload**: 30 kết nối cực ngắn có thể được fixed pool xử lý tốt; 10.000 sockets idle có đặc tính khác. Không đánh đồng **ngưỡng connection** với **throughput req/s** hoặc độ trễ p95.

## 7. Mã thực nghiệm dùng chung — TcpModelsLab.java

Ví dụ đầy đủ có **một client harness** cho cả ba modes và một giao thức chung PING LF → PONG LF. Nó **biên dịch được với --release 17**; hai modes **POOL/SELECTOR** dùng API Java17. Để so sánh virtual mode trong cùng tệp Java17-compatible, chương trình gọi **newVirtualThreadPerTaskExecutor** qua **reflection** khi đang chạy trên JDK21+, đồng thời dùng reflection xác minh **Thread.isVirtual()** của handler. Đó là cầu nối cho bài lab, **không phải pattern cần dùng trong Java21 production**.

- **POOL:** bốn worker, ArrayBlockingQueue(128), AbortPolicy.
- **VIRTUAL:** per-task virtual thread executor, Semaphore(64) hạn chế admitted connections.
- **SELECTOR:** một event-loop thread, OP_ACCEPT/READ/WRITE, ByteBuffer input/output trong attachment, xử lý EOF và partial write.
- **Client generator:** 12 platform client workers, kết nối 127.0.0.1:port động, connect/read timeout, kiểm tra từng response byte.
- **--smoke:** 30 requests/mode; output xác định theo PASS conditions.
- **--measure:** 30 warmup + 120 measured requests/mode; in elapsed/p50/p95 **phụ thuộc môi trường**.
- Dọn sockets, selector và executors trong finally/close, assert không có lỗi xử lý.

### Tệp TcpModelsLab.java

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

    // Reflection giữ source tương thích --release 17.
    // Trên Java21 production, gọi typed API trực tiếp.
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
            channel.write(state.output); // có thể ghi một phần
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
                blockingListener.close(); // đánh thức accept()
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

### Chạy trên Java 17+ và Java 21+

~~~bash
javac --release 17 -encoding UTF-8 TcpModelsLab.java
java TcpModelsLab --smoke
java TcpModelsLab --measure
~~~

**Stdout smoke đã chạy và kiểm tra trên OpenJDK 24.0.2, JDK hỗ trợ virtual threads:**

~~~text
POOL: PASS 30/30
VIRTUAL: PASS 30/30
SELECTOR: PASS 30/30
All available models: PASS
~~~

**Khi dùng runtime Java 17**, virtual API chưa có nên code intentionally skip mode đó. Dạng stdout theo logic chương trình, **chưa được chạy xác minh trên runtime 17**:

~~~text
POOL: PASS 30/30
VIRTUAL: SKIPPED (requires JDK 21+)
SELECTOR: PASS 30/30
All available models: PASS
~~~

**Measure mode đã chạy thành công**: mỗi mode hoàn thành 120/120 sau 30 warmups; latency p50/p95 và elapsed_ms được in dạng số thực. Số liệu luôn thay đổi theo JIT, OS, scheduling, CPU, GC và các điều kiện của máy.

**Một lần đo trên Windows OpenJDK24/loopback (chỉ để minh họa format, không phải thứ hạng sản phẩm):**

~~~text
POOL: PASS 120/120
POOL metrics: elapsed_ms=9.06 p50_ms=0.64 p95_ms=0.89
VIRTUAL: PASS 120/120
VIRTUAL metrics: elapsed_ms=9.94 p50_ms=0.56 p95_ms=0.91
SELECTOR: PASS 120/120
SELECTOR metrics: elapsed_ms=23.04 p50_ms=1.98 p95_ms=3.12
All available models: PASS
~~~

Đây **không phải chứng minh POOL nhanh nhất**. Chỉ có 12 client workers, 120 sample/mode, workload gần như không có thời gian I/O wait, tất cả chạy trong một JVM và trên loopback. Khi tăng rất nhiều idle clients, business blocking, WAN RTT, TLS hoặc streaming, kết quả có thể đổi hẳn.

### Giải thích code từng mode

**POOL:** ServerSocket accept socket; bounded ThreadPoolExecutor cấp tối đa 4 workers, mỗi worker gọi InputStream.read nhiều lần để lấy 5 bytes rồi OutputStream.write. Socket được đóng qua try-with-resources; rejection bị ghi nhận để test fail thay vì mất request âm thầm.

**VIRTUAL:** accept socket và gửi task vào virtual-thread-per-task executor (kết quả reflection của Java21+). Handler kiểm tra actual virtual thread, sử dụng blocking Socket API và giải phóng permit trong finally. Nếu quota 64 đã full, close socket và ghi lỗi overload.

**SELECTOR:** ServerSocketChannel non-blocking đăng ký OP_ACCEPT, accepted SocketChannel non-blocking đăng ký OP_READ với ConnectionState attachment; đọc từng phần vào ByteBuffer, gặp đủ PING thì chuyển sang OP_WRITE và giữ output ByteBuffer cho tới khi ghi hết; sau đó handled++ rồi cancel key/close channel. Shutdown dùng selector.wakeup() và đóng keys/channels.

**Client:** luôn gửi REQUEST 5 bytes, rồi đọc từng byte để kiểm tra RESPONSE 5 bytes; mỗi Socket có connect timeout/read timeout. Sau toàn bộ client futures, kiểm tra handled count bằng deadline và xác nhận không có lỗi background.

### Hạn chế của ví dụ lab

Mỗi connection chỉ có một frame đúng 5 bytes; server không hỗ trợ nhiều PING liên tiếp trên cùng socket, oversized packets, TLS, authentication, half-close protocol hoặc slow-client idle scanning đầy đủ. Selector mode không có explicit max-open-channel quota; production cần thêm. Virtual semaphore và pool queue là hai chính sách capacity khác nhau: chúng được ghi rõ để người học **không giả định kết quả đo là so sánh tài nguyên hoàn toàn tương đương**.

## 8. Cách thiết kế benchmark đáng tin cậy

### Giữ những biến quan trọng như nhau

| Nhóm biến | Điều phải kiểm soát |
| --- | --- |
| Protocol | Cùng bytes, framing, số messages/connection |
| Clients | Cùng concurrency, arrival rate, timeouts, reconnect policy |
| Server | Cùng bind address, payload, business logic, error policy |
| JVM | Cùng vendor/version, heap, GC, warmup và flags |
| Host/network | CPU quota, RAM, FD limits, OS, route, loopback hay WAN |
| Thống kê | Số requests, thành công/lỗi, throughput, p50/p95/p99, confidence interval |
| Tài nguyên | CPU, platform threads, virtual threads, open sockets, heap/native/direct memory |
| Thời gian | Nhiều lần chạy, trộn thứ tự thử nghiệm, loại warmup khỏi measure |

**Benchmark có ý nghĩa phải báo lỗi và timeout**, không chỉ báo throughput từ những request thành công. Một mode “nhanh” do bỏ rơi 20% clients không phải là kết quả tốt.

### Tải idle connections là phép thử cần thêm

Giả sử **4 platform workers** đều đang chờ đọc từ 4 clients đã connect nhưng chưa gửi byte. Client thứ năm gửi đủ PING có thể phải đợi worker rảnh. Với virtual threads, nhiều task blocked I/O thường unmount được; với Selector, kết nối idle nằm trong registered keys chứ không cần một worker per connection. Để chứng minh, phải viết load test giữ idle sockets có quota/timeout, không suy ra từ smoke test chỉ có các request rất ngắn.

### Thời gian, concurrency và Little's law

Trong trạng thái ổn định, **L ≈ λ × W**: số tác vụ trung bình trong hệ thống ≈ request arrival rate × thời gian sống trung bình. Chẳng hạn 100 requests/s, mỗi request tồn tại 0,5 s, số requests in-flight trung bình khoảng 50. Nếu mỗi request phải chờ 5 s, cùng arrival rate có thể kéo in-flight lên khoảng 500. Điều này giải thích tại sao platform thread pool nhỏ dễ nghẽn khi workload chủ yếu là **waiting**, còn VT/Selector giúp scale waiting concurrency (nếu quota tài nguyên khác đáp ứng).

Không xem Little's law là dự đoán tuyệt đối khi hệ thống đang overload/unstable; queue growth, timeout và admission policy còn tác động.

### Loopback microbenchmark có giới hạn

Chạy client/server trong cùng JVM tạo interference ở CPU/GC, và RTT cực thấp khiến scheduler overhead nổi bật. Muốn chọn kiến trúc production, hãy **tách load generator**, đo nhiều runs và công bố p95/p99, errors, memory/FD, GC, CPU, connections đang chờ, request size và downtime khi overload. Dùng profiler/JFR/thread dumps để giải thích *vì sao* số liệu khác nhau.

Không dùng **Thread.sleep() trong Selector loop** để mô phỏng I/O wait: hành động đó tự tạo blocking event loop mà hai mode khác không có, khiến benchmark không công bằng. Nếu workload thật cần downstream blocking, hãy định nghĩa nó giống nhau và offload đúng cách.

## 9. Quy tắc production về backpressure, timeout và lỗi

### Platform pool

Giới hạn accept backlog, max active sockets, queue, worker threads, socket read timeout và downstream calls. Nếu execute rejected, **đóng socket ngay** và ghi rejection count. Không để queue unbounded. Graceful shutdown phải ngừng accept, xử lý/cancel sockets đang active/queued và đợi pool kết thúc.

### Virtual threads

Một VT/connection không đồng nghĩa vô hạn admitted connections. Áp **Semaphore/connection quota**, memory/FD limits, socket timeouts, downstream pool; release permits ngay cả khi handler lỗi hoặc canceled. Theo dõi native blocking/pinning theo JDK, ThreadLocal allocations, JFR và downstream queue. Không gọi một virtual-thread-per-task executor là fixed pool; nó tạo thread mới cho mỗi task.

### Selector

Mỗi channel có state và buffer ownership; xử lý read=0/-1, oversized messages, partial writes, OP_WRITE interest để tránh busy loop, EOF/half-close, cancellation, close key/channel và cross-thread wakeup. Đặt **idle timeouts, max channels, per-connection outgoing buffer cap**, metric event-loop latency. Offload CPU/JDBC/blocking business code sang bounded worker pool. **key.cancel() không tự đóng socket**.

### Bảo mật và mạng

Demo dùng TCP plaintext **127.0.0.1**, không có TLS hay authentication; không publish public. Trong production cần TLS (với non-blocking NIO có thể phải quản lý SSLEngine), authorization, rate limiting, timeout chống slowloris, framing parser và quota buffers. File descriptors/OS backlog, firewall và host settings có thể giới hạn trước khi JVM chạm giới hạn thread.

## 10. Tình huống lựa chọn

| Workload | Lựa chọn cần đánh giá | Giải thích |
| --- | --- | --- |
| Java17, TCP service nhỏ, concurrency vừa | **Bounded platform pool** | Code tuần tự và vận hành đơn giản |
| Java21+, nhiều request chủ yếu chờ I/O | **Virtual threads** | Code blocking tuần tự mà không cần platform worker per waiting task |
| Rất nhiều sockets nhàn rỗi, protocol/event-driven | **Selector hoặc NIO framework** | Multiplex readiness, ít event-loop threads |
| Business CPU nặng | **CPU worker pool phù hợp core** | Virtual threads không tăng CPU cores; Selector phải offload |
| Legacy blocking code, migration Java21 | **Virtual threads + resource quotas** | Giữ code dễ đọc, đo pinning/downstream |
| Ứng dụng đã dùng Netty/NIO framework trưởng thành | **Giữ/đo framework hiện có trước** | Tránh tái viết protocol, TLS và backpressure khó |
| Cần phân biệt throughput trên thật | **Load test có control** | Smoke/localhost chưa đủ để khẳng định winner |

## 11. Những hiểu nhầm phổ biến

1. **“Một TCP read = một message”** — Sai. TCP là stream; phải framing.
2. **“Socket.read block chỉ tốn CPU lúc có bytes”** — Sai với platform threads: OS thread vẫn bị giữ trong lúc chờ, dù không dùng nhiều CPU.
3. **“newFixedThreadPool giới hạn cả số tasks chờ”** — Sai: queue mặc định không giới hạn.
4. **“Virtual thread làm CPU calculation nhanh hơn”** — Sai. Cần CPU resources/algorithm phù hợp.
5. **“Nên pool virtual threads để tiết kiệm”** — Không nên; giới hạn tài nguyên bằng quota/semaphore, không tái tạo worker scarcity.
6. **“JDK17 có thể gọi trực tiếp newVirtualThreadPerTaskExecutor”** — Không. API ổn định từ Java21.
7. **“Selector select báo đủ response/request bytes”** — Sai. Readiness khác completeness.
8. **“SocketChannel.read trả 0 nghĩa client đóng”** — Sai; **-1** là EOF.
9. **“SocketChannel.write luôn gửi hết buffer”** — Sai; phải giữ partial output.
10. **“OP_WRITE luôn bật thì server chạy nhanh”** — Sai; dễ busy-spin.
11. **“SelectionKey.cancel đóng luôn SocketChannel”** — Sai; phải close channel.
12. **“Chạy Selector một thread nghĩa là mọi code trong handler non-blocking”** — Sai; JDBC, sleep hoặc CPU nặng vẫn block loop.
13. **“Một lần test 120 loopback requests là benchmark production”** — Sai; cần đo nhiều runs với load thực.
14. **“10.000 virtual threads không tốn tài nguyên”** — Sai; sockets, memory và downstream có giới hạn.
15. **“Khi JDK24+, mọi blocking/native pinning biến mất”** — Sai; JEP491 cải thiện synchronized monitors, cần kiểm tra phần khác.
16. **“Thấy response PASS là server không leak”** — Chưa đủ; phải kiểm tra worker shutdown, FD, pending channels, timeout/rejection.

## 12. Checklist kiểm thử và câu hỏi tự đánh giá

**Checklist chức năng:** test partial input, EOF trước đủ PING, invalid request, nhiều connections đồng thời, response đầy đủ, timeout, cleanup; với Selector phải test OP_WRITE khi write được 0/partial bytes dưới áp lực.

**Checklist benchmark:** ghi Java version, OS, máy, heap, CPU, FD limit, cùng protocol/traffic, warmup, errors, throughput, latency percentiles, platform/virtual threads, CPU/GC/memory, thời gian chạy và phương pháp lọc noise. Đo nhiều lần và báo số liệu cùng điều kiện.

**Câu hỏi 1.** Vì sao platform pool 4 workers có thể nghẽn với bốn idle connections?  
**Đáp án:** Cả bốn workers có thể đang chờ blocking InputStream.read, khiến task khác phải đợi.

**Câu hỏi 2.** Java17 có thể chạy mô hình Selector và virtual threads bằng cùng API trực tiếp không?  
**Đáp án:** Selector có trong Java17; virtual threads API chuẩn chỉ từ Java21. Demo dùng reflection tại runtime 21+ để một nguồn --release17 vẫn compile.

**Câu hỏi 3.** Đâu là khác biệt của virtual thread so với platform thread?  
**Đáp án:** Virtual thread là task được JVM schedule trên carrier platform threads; nhiều I/O waits có thể unmount, không giữ một OS thread per waiting task.

**Câu hỏi 4.** Vì sao không nên tạo fixed pool 4 virtual threads?  
**Đáp án:** Nó tái tạo nút nghẽn worker. Nên một VT/task, giới hạn sockets/downstream bằng permits/quota.

**Câu hỏi 5.** Với Selector, n=0 và n=-1 khi read khác gì?  
**Đáp án:** 0 là chưa có dữ liệu trong lần non-blocking read; -1 là EOF.

**Câu hỏi 6.** Khi ghi response mới được 2/5 bytes, có đóng SocketChannel ngay không?  
**Đáp án:** Không. Giữ ByteBuffer và OP_WRITE cho tới khi gửi hết, hoặc hủy theo policy lỗi/timeout.

**Câu hỏi 7.** Vì sao cần iterator.remove trên selectedKeys?  
**Đáp án:** Loại readiness vừa xử lý, tránh key nằm lại selected set và bị xử lý lặp.

**Câu hỏi 8.** Khi event loop gọi JDBC blocking, điều gì xảy ra?  
**Đáp án:** Nó làm các channels khác bị chậm; cần offload work blocking.

**Câu hỏi 9.** Vì sao không kết luận mode nào nhanh nhất từ kết quả loopback đo một lần?  
**Đáp án:** Tải thấp, một JVM, scheduler/JIT/GC và cấu hình giới hạn khác nhau; cần phép đo đầy đủ.

**Câu hỏi 10.** Khi nhiều virtual threads chờ I/O, giới hạn nào vẫn tồn tại?  
**Đáp án:** Open sockets/FD, memory, downstream pools, timeouts, CPU, rate limits.

## Kết luận

**Platform thread pool** là lựa chọn đơn giản cho concurrency vừa và code blocking; **virtual threads** giúp giữ phong cách code tuần tự khi nhiều tác vụ chờ I/O trên JDK21+; **Selector** multiplex nhiều channels bằng non-blocking state machine, đổi lại yêu cầu quản lý buffer, readiness, backpressure và cleanup kỹ lưỡng.

Muốn so sánh có giá trị, hãy **giữ protocol và workload giống nhau, kiểm tra correctness trước**, sau đó đo throughput, p50/p95/p99, lỗi, CPU, memory và FD trên nhiều lần chạy. Thay vì chọn mô hình theo câu khẩu hiệu “nhanh nhất”, chọn theo **số connection, tỷ lệ idle/active, loại blocking, yêu cầu latency, JDK và độ phức tạp vận hành**.

### Tài liệu tham khảo chính thức

- [Java SE 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): accept blocking, backlog.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): blocking I/O, timeout.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): bounded queue/rejection.
- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): multiplexing, selectedKeys, cancel/wakeup.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking read/write.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): OP_ACCEPT/READ/WRITE/CONNECT.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): flip/remaining/compact.
- [Java SE 21 — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): newVirtualThreadPerTaskExecutor.
- [Oracle — Virtual Threads in Java 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): task-per-virtual-thread, carrier/unmount.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): Java21 stable virtual threads.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): Java24 changes.
- [RFC 9293 — TCP](https://www.rfc-editor.org/rfc/rfc9293.html): TCP byte-stream semantics.

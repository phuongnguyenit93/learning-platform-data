# Chọn socket, selector, luồng ảo hoặc client HTTP theo đặc điểm tải

Khi thiết kế hệ thống networking bằng Java, câu hỏi **“nên dùng `Socket`, `Selector`, virtual threads hay `HttpClient`?”** thực ra gồm **hai trục lựa chọn khác nhau**:

1. **Giao thức ứng dụng:** Bạn đang giao tiếp bằng **TCP byte stream tự định nghĩa** hay **HTTP request–response**? Với HTTP, ưu tiên API hiểu HTTP như `java.net.http.HttpClient`, thay vì tự viết HTTP framing, TLS/proxy/redirect trên `Socket`.
2. **Mô hình concurrency:** Phần lớn tác vụ **chờ I/O**, cần phục vụ **rất nhiều kết nối sống lâu**, hay **tốn CPU**? Có thể dùng blocking I/O + platform threads, **nonblocking NIO `Selector`**, hoặc **virtual threads** khi chạy Java 21+.

Các giải pháp **không nhất thiết loại trừ nhau**: một virtual thread có thể gọi `HttpClient.send()`; một HTTP client có thể được chia sẻ giữa nhiều tác vụ; một server dùng `Selector` có thể giao CPU-heavy processing sang worker pool. Quyết định tốt dựa vào traffic profile, latency mục tiêu, connection lifetime, resource quotas, khả năng quan sát lỗi và mức phức tạp nhóm có thể duy trì — không chỉ số benchmark “requests per second”.

**Lưu ý phiên bản cực kỳ quan trọng:** `java.net.Socket`, `java.nio.channels.Selector` và `java.net.http.HttpClient` đều dùng được trên **Java 17**. **Virtual threads trở thành tính năng chính thức từ Java 21** (JEP 444); **không** viết `Executors.newVirtualThreadPerTaskExecutor()` trong project target Java 17. Bài dùng **ba chương trình biên dịch `--release 17`** và **một chương trình riêng biên dịch `--release 21`** để minh họa lựa chọn có thể kết hợp.

Bài Knowledge thuộc mục **Độ tin cậy** của **Java Advance - networking**. Trọng tâm là **chọn đúng abstraction theo đặc điểm tải và vẫn giữ các bảo đảm về dữ liệu, timeout, backpressure, fairness, idempotency, cleanup**.

## 1. Bản đồ lựa chọn bốn công cụ

| Công cụ / mô hình | Giải quyết trực tiếp | Phù hợp nổi bật | Cần tự xử lý | Java tối thiểu |
| --- | --- | --- | --- | --- |
| `Socket` / `ServerSocket` blocking | TCP streams và tiếp nhận kết nối bằng blocking calls | Protocol TCP riêng, số connection vừa phải, logic tuần tự dễ đọc | Framing, read/write loops, deadline, thread pool, auth/TLS, queues | Java 17 (đã có lâu hơn) |
| `SocketChannel` + `Selector` | Multiplex **nhiều nonblocking channels** qua event loop | Nhiều connection idle/slow, fan-in lớn, cần kiểm soát state/byte buffers | Selector keys, partial I/O, framing, OP_WRITE toggling, fairness, cross-thread coordination | Java 17 |
| **Virtual threads** | Rẻ hơn khi tạo task chờ blocking I/O; mô hình một task một thread | Java 21+, nhiều thao tác blocking độc lập, cần code tuyến tính dễ đọc | Quota outbound/DB, deadlines, structured lifecycle, thread-local/driver caveats | **Java 21** chính thức |
| `HttpClient` | HTTP/1.1/HTTP/2 request/response, TLS/redirect/proxy theo API | Gọi REST APIs, microservices, HTTP endpoints và HTTP streaming | Body lifecycle, application limits, HTTP status, retries/idempotency, deadlines | Java 11+, dùng trong Java 17 |

**Không so sánh “Socket vs HttpClient” như hai cách làm đúng cùng một việc.** `Socket` là primitive TCP; `HttpClient` là **client giao thức HTTP**. Khi client phải gọi `https://api.example/...`, `HttpClient` giải quyết nhiều việc mà raw TCP không làm hộ. Khi bạn xây một **server TCP binary tùy biến**, `HttpClient` không phải API phù hợp để accept socket.

## 2. Cách đọc workload trước khi chọn abstraction

Hãy thu thập các dữ liệu **đo được**:

- **C** — số connections đồng thời tối đa; bao nhiêu idle và bao nhiêu active?
- **R** — requests/messages mỗi giây; request fan-out ra downstream bao nhiêu?
- **S** — kích thước message trung bình, p95/p99, payload tối đa, tốc độ stream.
- **W** — thời gian mỗi task **chờ I/O** (DB, HTTP, file, socket), so với **P** — CPU time thực.
- **L** — yêu cầu p95/p99 latency, deadlines, backlog khi burst, số slow consumers.
- **V** — phiên bản Java deploy được chấp nhận (17 LTS hay 21+).
- **M** — memory budget, file descriptors, OS thread limit, connection pools.
- **D** — tính chất dữ liệu: message framing, idempotency, durability, replay sau disconnect.
- **Security** — TLS/mTLS, authn/authz, proxy, tenant isolation, input limits.

Ví dụ: **20.000 TCP connections nhưng chỉ 2% có byte đang đến** là bài toán khác với **200 requests đồng thời đều gọi DB và chờ 300 ms**, và khác nữa với **100 tasks liên tục nén dữ liệu chiếm hết CPU**.

Đừng chọn selector chỉ vì có nhiều connection nếu nhóm không đủ năng lực quản lý state và lỗi; đừng chọn virtual threads chỉ vì “nó là công nghệ mới” nếu CPU đang là bottleneck.

## 3. Sơ đồ quyết định hai trục

```text
Ứng dụng đang trao đổi bằng giao thức nào?
  |
  +-- HTTP(S) request/response?
  |      |
  |      +-- CẦN GỌI server -> java.net.http.HttpClient
  |      |       |
  |      |       +-- Ít thao tác -> send() hoặc sendAsync() phù hợp
  |      |       +-- Nhiều cuộc gọi độc lập -> sendAsync + bounded in-flight
  |      |       +-- Java 21+ blocking style -> virtual thread gọi send()
  |      |
  |      +-- CẦN PHỤC VỤ HTTP -> HttpServer/framework HTTP server
  |              (HttpClient KHÔNG phải HTTP server)
  |
  +-- TCP binary/text protocol tùy biến?
         |
         +-- Ít/vừa connections, đơn giản -> Socket + bounded workers
         +-- Nhiều connections idle/long-lived -> Selector + nonblocking
         +-- Java 21+, nhiều tasks chờ I/O -> virtual threads + Socket
         +-- Tác vụ CPU nặng -> pool theo CPU, tách khỏi I/O path
```

Các nhánh còn phụ thuộc **TLS, throughput, data framing, resource quotas, reliability**. Không có một số “từ 1.000 connections trở lên phải dùng Selector” được JDK đảm bảo. Con số ngưỡng chỉ có ý nghĩa khi đo trên workload/hardware/OS/JDK thực.

## 4. `Socket`: lựa chọn dễ hiểu khi protocol TCP riêng còn gọn

`Socket` là byte stream TCP **blocking**. Các thao tác như `InputStream.read` và `OutputStream.write` có thể chờ dữ liệu hoặc chờ peer/network; Java không tạo ra **message boundaries** từ TCP. Một lần server `write` không chắc là một lần client `read`.

```text
TCP sender:  [4-byte length][UTF-8 bytes] [4-byte length][UTF-8 bytes]
                          |
                TCP byte stream
                          |
TCP reader:  readInt -> readFully(length) -> decode frame
```

Khi dùng blocking sockets, một cách triển khai là mỗi accepted socket được **giao cho một worker**, handler code đọc/ghi theo thứ tự. Đó là mô hình tự nhiên cho protocol nhỏ và latency tương đối dễ dự đoán, với điều kiện số worker/connection được giới hạn.

**Rủi ro chính:** nếu một socket giữ worker trong `read` lâu, các connection khác có thể phải đợi; một thread platform có stack và OS resources, không thể tăng vô hạn theo lượng idle connections. Tránh một thread pool không giới hạn hoặc factory mặc định có **unbounded queue** nếu server phải chịu traffic burst.

## 5. Bốn điểm dễ sai khi triển khai blocking TCP

1. **Framing:** Với protocol có messages, dùng length-prefix, delimiter hoặc parser stream có trạng thái. Không decode từng TCP chunk thành JSON message độc lập.
2. **Timeout:** Đặt `Socket.setSoTimeout(...)` cho blocking reads; connection establishment có timeout riêng qua `socket.connect(address, timeout)`. Một read timeout **không** tự giới hạn tổng thời gian xử lý business.
3. **Bounds:** Giới hạn frame bytes trước khi cấp phát, số connections, số workers, executor queue, tổng pending outbound bytes và thời gian idle.
4. **Cleanup:** Dùng try-with-resources; xử lý EOF (`read() == -1`), half-close, remote reset và `IOException`. TCP close không có nghĩa server đã rollback side effects của message đã nhận.

Đừng lấy `DataInputStream.readFully` làm bằng chứng một connection luôn đọc đủ: nó chờ đúng bytes **hoặc ném EOFException** nếu peer đóng sớm. Đây là điều đúng đắn cần bắt và phản ánh thành **incomplete frame**.

## 6. Ví dụ Java 17+ A — TCP Socket dùng framing bốn byte và UTF-8

Chương trình độc lập **`BlockingSocketWorkloadDemo.java`** mở `ServerSocket` trên `127.0.0.1`, port tự cấp. Một worker nhận một kết nối và echo **hai messages**. Framing là **4-byte signed integer** chỉ độ dài payload UTF-8, theo big-endian của `DataOutputStream.writeInt` và `DataInputStream.readInt`. Server chỉ chấp nhận `0 <= length <= 1024`; `readFully` bảo đảm đọc đủ bytes frame trước khi decode.

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BlockingSocketWorkloadDemo {
    private static void writeFrame(DataOutputStream out, String value)
            throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
        out.flush();
    }

    private static String readFrame(DataInputStream in) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > 1024) {
            throw new IOException("Invalid frame length");
        }
        byte[] bytes = new byte[length];
        in.readFully(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        try (ServerSocket server = new ServerSocket(0, 10, local)) {
            server.setSoTimeout(5000);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            AtomicInteger handled = new AtomicInteger();
            try {
                Future<?> accept = pool.submit(() -> {
                    try (Socket peer = server.accept()) {
                        peer.setSoTimeout(5000);
                        DataInputStream in = new DataInputStream(
                                peer.getInputStream());
                        DataOutputStream out = new DataOutputStream(
                                peer.getOutputStream());
                        for (int i = 0; i < 2; i++) {
                            String payload = readFrame(in);
                            writeFrame(out, payload);
                            handled.incrementAndGet();
                        }
                    } catch (IOException error) {
                        throw new UncheckedIOException(error);
                    }
                });

                try (Socket client =
                        new Socket(local, server.getLocalPort())) {
                    client.setSoTimeout(5000);
                    DataInputStream in = new DataInputStream(
                            client.getInputStream());
                    DataOutputStream out = new DataOutputStream(
                            client.getOutputStream());
                    writeFrame(out, "alpha");
                    System.out.println("First echo: " + readFrame(in));
                    writeFrame(out, "Xin chào");
                    System.out.println("Second echo: " + readFrame(in));
                }
                accept.get(6, TimeUnit.SECONDS);
                System.out.println("Frames handled: " + handled.get());
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```sh
javac --release 17 -encoding UTF-8 BlockingSocketWorkloadDemo.java
java BlockingSocketWorkloadDemo
```

Stdout đã kiểm chứng:

```text
First echo: alpha
Second echo: Xin chào
Frames handled: 2
```

**Điều ví dụ minh họa:**

- Hai lần `writeFrame` là **hai message do application tự định nghĩa**, không phải hai TCP packets. `readFrame` dùng length prefix để xác định message boundaries.
- `String.getBytes(UTF_8)` rồi `length` đo bytes, không dùng `String.length()` để định length trong protocol.
- `DataInputStream.readFully` có thể hoàn thành qua nhiều network reads, hoặc ném exception nếu body ngắn.
- `Socket.setSoTimeout(5000)` giới hạn thời gian block từng thao tác đọc, không đảm bảo toàn operation dưới 5 giây.
- `newFixedThreadPool(2)` chỉ minh họa worker scheduling; **queue mặc định không bị giới hạn**, nên chưa phải production admission control.
- `ServerSocket` và `Socket` được đóng; worker pool shutdown trong `finally`.
- Demo chỉ xử lý **một accepted connection** và hai messages; không chứng minh một server thực có thể chứa hàng trăm nghìn clients bằng cách tạo thread-per-connection.

**Khi chọn:** nếu server cần giao tiếp protocol tùy biến đơn giản với vài chục/vài trăm connections trong quota đã kiểm chứng, blocking sockets có thể dễ maintain hơn một event loop nhiều states. Ngưỡng thực tế phải load test.

## 7. `Selector`: multiplex nonblocking I/O mà không cần thread chờ cho mỗi socket

Java NIO cung cấp `ServerSocketChannel`, `SocketChannel`, `Selector` và `SelectionKey`. Khi các channels chuyển sang **nonblocking mode**, một event loop có thể đăng ký các interest sets và xử lý readiness của nhiều connections trong vòng `selector.select()`.

| Operation bit | Ý nghĩa khi interest được đặt |
| --- | --- |
| `OP_ACCEPT` | ServerSocketChannel có sự kiện accept-ready |
| `OP_CONNECT` | SocketChannel có thể hoàn tất nonblocking connection |
| `OP_READ` | Channel có dữ liệu, EOF hoặc điều kiện cần được xử lý phía read |
| `OP_WRITE` | Channel có thể ghi dữ liệu vào output buffer của transport (hoặc điều kiện lỗi liên quan) |

**Readiness không phải completion.** Khi `key.isReadable()`, `read(buffer)` có thể chỉ đọc **một phần**; khi `key.isWritable()`, `write(buffer)` có thể ghi **0 byte hoặc một phần**. `ByteBuffer.position()` phải được giữ qua lượt xử lý sau để tránh mất/lặp byte.

Selector có ưu thế khi phần lớn connection idle: event loop không cần một platform thread block cho mỗi socket. Cái giá là bạn **tự sở hữu state machines**, connection lifetime, buffer queues, fairness, framing, error/cancel, cross-thread commands và kiểm soát memory.

## 8. Đừng đăng ký `OP_WRITE` vĩnh viễn

Với TCP socket còn chỗ trong kernel send buffer, **write-ready thường xuyên**. Nếu bạn luôn giữ `OP_WRITE` trong interest set, `selector.select()` có thể thức dậy liên tục **dù không có dữ liệu cần gửi**, tạo vòng lặp CPU cao.

Quy tắc:

```text
Khi accepted:
   register OP_READ (không OP_WRITE khi outbound queue trống)

Khi ứng dụng enqueue outbound:
   bật OP_WRITE; selector.wakeup() nếu từ thread khác

Khi isWritable:
   write pending ByteBuffers, giữ position nếu partial/zero
   nếu queue đã rỗng:
      xóa OP_WRITE ngay
   nếu queue vẫn còn:
      giữ OP_WRITE cho lần sẵn sàng tiếp theo

Khi lỗi/EOF:
   cancel SelectionKey, close channel, dọn per-connection state
```

Thêm `OP_WRITE` **chỉ khi có bytes đang chờ**; đừng write/spin đến hết một buffer khổng lồ trong một callback. Với hệ thật, có **write budget mỗi lượt** để một connection không chiếm toàn event loop; khi peer đọc chậm, giới hạn **bytes pending mỗi connection** và áp chính sách backpressure/reject/close.

`OP_READ` cũng không phải lúc nào cần bật; nếu inbound queue phía application bị nghẽn, có thể giảm read interest có kiểm soát để tránh chiếm bộ nhớ, nhưng phải thiết kế resume và tránh deadlock.

## 9. Ví dụ Java 17+ B — một Selector echo với `OP_WRITE` bật/tắt đúng lúc

Tệp **`SelectorWorkloadDemo.java`** dùng một event-loop thread để quản lý `ServerSocketChannel` và một `SocketChannel` nonblocking. Client gửi một dòng `selector\n`. Server giữ `ByteBuffer` có giới hạn 128 byte, chờ thấy newline rồi **chuyển interest từ `OP_READ` sang `OP_WRITE`**, echo dữ liệu có thể bị partial-write, **xóa `OP_WRITE` sau khi buffer hết** và đóng kết nối.

```java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class SelectorWorkloadDemo {
    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        try (ServerSocketChannel server = ServerSocketChannel.open();
             Selector selector = Selector.open()) {
            server.bind(new InetSocketAddress(local, 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);
            AtomicBoolean completed = new AtomicBoolean();
            AtomicBoolean writeInterestCleared = new AtomicBoolean();
            AtomicReference<Throwable> problem = new AtomicReference<>();

            Thread eventLoop = new Thread(() -> {
                try {
                    long deadline = System.nanoTime()
                            + 8_000_000_000L;
                    while (!completed.get()
                            && System.nanoTime() < deadline) {
                        selector.select(500);
                        Iterator<SelectionKey> it =
                                selector.selectedKeys().iterator();
                        while (it.hasNext()) {
                            SelectionKey key = it.next();
                            it.remove();
                            if (!key.isValid()) continue;

                            if (key.isAcceptable()) {
                                SocketChannel peer = server.accept();
                                if (peer != null) {
                                    peer.configureBlocking(false);
                                    peer.register(selector,
                                            SelectionKey.OP_READ,
                                            ByteBuffer.allocate(128));
                                }
                            } else if (key.isReadable()) {
                                SocketChannel peer =
                                        (SocketChannel) key.channel();
                                ByteBuffer buffer =
                                        (ByteBuffer) key.attachment();
                                int count = peer.read(buffer);
                                if (count == -1) {
                                    throw new IllegalStateException(
                                            "EOF before line");
                                }
                                boolean lineComplete = false;
                                for (int p = 0;
                                     p < buffer.position(); p++) {
                                    if (buffer.get(p) == '\n') {
                                        lineComplete = true;
                                        break;
                                    }
                                }
                                if (lineComplete) {
                                    buffer.flip();
                                    key.interestOps(SelectionKey.OP_WRITE);
                                } else if (!buffer.hasRemaining()) {
                                    throw new IllegalStateException(
                                            "Line too long");
                                }
                            } else if (key.isWritable()) {
                                SocketChannel peer =
                                        (SocketChannel) key.channel();
                                ByteBuffer pending =
                                        (ByteBuffer) key.attachment();
                                peer.write(pending);
                                if (!pending.hasRemaining()) {
                                    key.interestOps(0);
                                    writeInterestCleared.set(true);
                                    key.cancel();
                                    peer.close();
                                    completed.set(true);
                                }
                            }
                        }
                    }
                    if (!completed.get()) {
                        throw new IllegalStateException(
                                "Selector deadline exceeded");
                    }
                } catch (Throwable error) {
                    problem.set(error);
                }
            }, "selector-loop");
            eventLoop.start();

            try (Socket client =
                    new Socket(local, server.socket().getLocalPort())) {
                client.setSoTimeout(5000);
                OutputStream out = client.getOutputStream();
                out.write("selector\n".getBytes(StandardCharsets.UTF_8));
                out.flush();
                InputStream in = client.getInputStream();
                ByteArrayOutputStream reply = new ByteArrayOutputStream();
                int next;
                while ((next = in.read()) != -1) {
                    reply.write(next);
                    if (next == '\n') break;
                    if (reply.size() > 128) {
                        throw new IllegalStateException("Response too large");
                    }
                }
                System.out.println("Echo: " + reply.toString(
                        StandardCharsets.UTF_8).trim());
            } finally {
                eventLoop.join(9000);
                if (eventLoop.isAlive()) {
                    selector.wakeup();
                    throw new IllegalStateException("Event loop not stopped");
                }
            }

            if (problem.get() != null) {
                throw new IllegalStateException(problem.get());
            }
            System.out.println("OP_WRITE removed after send: "
                    + writeInterestCleared.get());
            System.out.println("Selector loop completed: "
                    + completed.get());
        }
    }
}
```

Chạy trên JDK 17+:

```sh
javac --release 17 -encoding UTF-8 SelectorWorkloadDemo.java
java SelectorWorkloadDemo
```

Stdout đã kiểm chứng:

```text
Echo: selector
OP_WRITE removed after send: true
Selector loop completed: true
```

Giải thích:

1. `selector.select(500)` chỉ hoạt động trên các channels đã đăng ký; `selectedKeys().iterator().remove()` tránh xử lý lặp một selected-key cũ.
2. Server register `OP_ACCEPT`, accepted peer register `OP_READ` với attachment là `ByteBuffer`; **không đăng ký OP_WRITE ngay khi accept**.
3. `read(buffer)` có thể đọc một đoạn; code giữ `buffer.position()` tới khi gặp newline.
4. Khi thấy newline, `buffer.flip()` và `interestOps(OP_WRITE)`. Từ đó buffer trở thành **outbound pending bytes** của **một message demo**.
5. `peer.write(pending)` có thể partial/zero. Khi `pending.hasRemaining()` vẫn true, code **không rewind** và vẫn quan tâm OP_WRITE.
6. Khi đã ghi hết, code `interestOps(0)` rồi đóng peer; in `OP_WRITE removed after send: true`. Kết nối đóng ngay vì demo chỉ echo **một** dòng. Trong server lâu dài, thường chuyển về `OP_READ` thay vì đóng.
7. Event loop có deadline và ghi nhận lỗi vào `AtomicReference` để thread chính kiểm tra; demo không yêu cầu Internet.
8. Code có phạm vi tối giản: **một connection, một dòng, tối đa 128 bytes**, không có multi-client fairness, TLS, outbound queue hay lifecycle production.

**Đừng copy đoạn NIO này làm server production**: nó minh họa đúng interest transitions, nhưng không phải implementation đầy đủ cho message framing dài, half-close, high load, quota và worker handoff.

## 10. Selector không đồng nghĩa “mọi tác vụ sẽ nhanh hơn”

Một event loop có thể xử lý nhiều socket I/O, nhưng nếu bạn gọi một thao tác **CPU-heavy hoặc blocking JDBC/HTTP** ngay trong `isReadable()`, **toàn bộ connections** trên loop có thể phải chờ. Selector **không** làm code business trở thành nonblocking.

Thiết kế điển hình:

```text
Selector event loop
   |
   +-- Readiness/read bytes/parse bounded frame
   +-- Enqueue bounded work item -> worker pool (CPU/DB)
   +-- Receive worker completion via mailbox
   +-- selector.wakeup()
   +-- Enable OP_WRITE only while outbound pending
   +-- Write with per-loop byte/time budget
```

Nếu một worker khác muốn sửa `SelectionKey.interestOps` hay queue attachment, phải có **ownership/happens-before** rõ. Lựa chọn an toàn là event loop thread sở hữu channel/key/buffer state; workers **gửi lệnh** qua thread-safe mailbox, rồi gọi `selector.wakeup()` để vòng loop xử lý lệnh. Tránh worker tự đồng thời mutate cùng `ByteBuffer` với event loop.

Event loop cần metrics về selected keys, bytes read/write, pending queues, long callbacks, wakeups, time spent in processing, CPU idle/spin và số peer chậm. Một selector có thể xử lý rất nhiều connections nhưng **không loại bỏ file descriptor limit hoặc kernel buffers**.

## 11. Virtual threads: chính thức từ Java 21, không có trong Java 17

**JEP 444** chuẩn hóa **virtual threads trong Java 21**. `Thread.ofVirtual()` và `Executors.newVirtualThreadPerTaskExecutor()` cho phép diễn đạt tác vụ blocking bằng **một virtual thread cho một task**, thay vì cần platform thread riêng khi chờ I/O.

Với blocking operations được hỗ trợ, JDK có thể **unmount** virtual thread khỏi carrier platform thread khi nó chờ I/O, để carrier phục vụ virtual thread khác. Đây là lợi ích mở rộng quy mô cho **I/O-bound concurrency**, **không phải** làm mỗi request hay thao tác CPU chạy nhanh hơn.

Những phát biểu quan trọng:

- **Java 17:** không có APIs virtual threads chính thức. Không biên dịch `Thread.ofVirtual()` với `javac --release 17`.
- **Java 19/20:** virtual threads từng ở trạng thái preview; không nên coi preview là API ổn định cho Java 17.
- **Java 21+:** virtual threads chính thức; có thể dùng `Executors.newVirtualThreadPerTaskExecutor()` và `Thread.currentThread().isVirtual()`.
- **Không pool virtual threads** chỉ để tiết kiệm số thread. Chúng được thiết kế như một task per virtual thread; giới hạn tài nguyên khác bằng `Semaphore`, connection pool, queue quota hoặc API rate limit.
- **Không dùng virtual threads để “tăng CPU cores”**. Tác vụ CPU-intensive cần bounded CPU pool hoặc thuật toán tốt hơn.
- Cần test các blocking operations, native calls, monitoring và behavior liên quan pinning theo **đúng phiên bản JDK**; Java 21 có caveats về `synchronized`/native blocks, và behavior có thể thay đổi ở các JDK mới. Không ngoại suy mọi phiên bản từ một JEP.

Nguồn: [JEP 444](https://openjdk.org/jeps/444), [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html).

## 12. Virtual threads khác một thread pool nền tảng ở điểm nào?

Mô hình platform threads:

```text
1000 kết nối/tác vụ cùng chờ I/O
    |
    +-- 1000 platform threads: chi phí OS thread/stack lớn
    hoặc
    +-- 50 fixed workers: tối đa 50 tasks đang chờ/chạy,
                          phần còn lại đứng ở executor queue
```

Mô hình virtual threads:

```text
1000 nhiệm vụ độc lập
    |
    +-- virtual thread per task (Java 21+)
             |
             +-- chờ I/O hỗ trợ -> carrier có thể làm việc khác
             |
             +-- CPU work -> vẫn sử dụng CPU thực
             |
             +-- downstream DB pool 20 -> tối đa 20 DB connections
```

**Không có gì miễn phí:** một triệu virtual threads vẫn có **heap objects/stacks**, application state, sockets, queued requests và giới hạn downstream. Nếu mỗi task giữ một `byte[10_000_000]`, việc thread nhẹ **không cứu được OOM**. Nếu 100.000 virtual threads cùng gửi requests đến database chỉ nhận 100 connections, throughput sẽ bị giới hạn bởi DB và có thể gây timeout storm.

`Semaphore`, body-byte quotas, max pending operations, rate limiter và deadlines phải phản ánh **tài nguyên thực**. Điều này cũng đúng nếu code dùng `HttpClient.send` bên trong virtual threads.

## 13. Ví dụ Java 21+ C — virtual threads dùng HTTP blocking nhưng có giới hạn outbound

Chương trình **`VirtualThreadHttpWorkloadDemo.java`** **yêu cầu Java 21 trở lên**, không chạy trên Java 17. Nó tạo 9 tác vụ virtual thread. Mỗi tác vụ gọi **`HttpClient.send` blocking** đến HTTP server loopback, nhưng **`Semaphore(3)` chỉ cho phép tối đa 3 HTTP calls đang hoạt động đồng thời**. Server cố tình chờ ba request đầu tiên cùng đến bằng `CountDownLatch` trước khi trả kết quả, giúp kiểm chứng giới hạn này một cách chắc chắn.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class VirtualThreadHttpWorkloadDemo {
    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService httpWorkers = Executors.newFixedThreadPool(4);
        AtomicInteger served = new AtomicInteger();
        CountDownLatch firstThree = new CountDownLatch(3);
        CountDownLatch release = new CountDownLatch(1);
        byte[] ok = "OK".getBytes(StandardCharsets.UTF_8);
        server.createContext("/work", exchange -> {
            try {
                int count = served.incrementAndGet();
                if (count <= 3) {
                    firstThree.countDown();
                    try {
                        release.await(5, TimeUnit.SECONDS);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                }
                exchange.sendResponseHeaders(200, ok.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(ok);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(httpWorkers);
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(URI.create(
                    "http://127.0.0.1:"
                            + server.getAddress().getPort() + "/work"))
                    .timeout(Duration.ofSeconds(10)).GET().build();
            Semaphore maxInFlight = new Semaphore(3);
            AtomicInteger active = new AtomicInteger();
            AtomicInteger peak = new AtomicInteger();
            List<Future<Boolean>> futures = new ArrayList<>();
            try (ExecutorService virtual =
                         Executors.newVirtualThreadPerTaskExecutor()) {
                for (int i = 0; i < 9; i++) {
                    futures.add(virtual.submit(() -> {
                        boolean isVirtual =
                                Thread.currentThread().isVirtual();
                        maxInFlight.acquire();
                        int now = active.incrementAndGet();
                        peak.accumulateAndGet(now, Math::max);
                        try {
                            HttpResponse<String> result = client.send(
                                    request,
                                    HttpResponse.BodyHandlers.ofString());
                            return isVirtual && result.statusCode() == 200
                                    && "OK".equals(result.body());
                        } finally {
                            active.decrementAndGet();
                            maxInFlight.release();
                        }
                    }));
                }
                if (!firstThree.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Server did not receive three requests");
                }
                release.countDown();
                boolean good = true;
                for (Future<Boolean> future : futures) {
                    good &= future.get(10, TimeUnit.SECONDS);
                }
                System.out.println("Virtual tasks completed: "
                        + futures.size());
                System.out.println("All virtual and HTTP 200: " + good);
                System.out.println("Peak in-flight HTTP: " + peak.get());
                System.out.println("Server handled: " + served.get());
            } finally {
                release.countDown();
            }
        } finally {
            release.countDown();
            server.stop(0);
            httpWorkers.shutdownNow();
        }
    }
}
```

Biên dịch và chạy bằng JDK 21+:

```sh
javac --release 21 --add-modules jdk.httpserver -encoding UTF-8 VirtualThreadHttpWorkloadDemo.java
java --add-modules jdk.httpserver VirtualThreadHttpWorkloadDemo
```

Stdout đã kiểm thử:

```text
Virtual tasks completed: 9
All virtual and HTTP 200: true
Peak in-flight HTTP: 3
Server handled: 9
```

**Ý nghĩa thực tế:**

- `Executors.newVirtualThreadPerTaskExecutor()` tạo **virtual thread cho mỗi task**; `isVirtual()` xác nhận thread context của từng task.
- `client.send` vẫn là blocking ở **tầng mã nguồn**, nhưng runtime có thể thực thi nhiều I/O-bound tasks nhờ virtual threads.
- `Semaphore(3)` đặt **quota outbound calls**, không “pool virtual threads”. `peak==3` chứng minh giới hạn và concurrent activity trong demo.
- `HttpClient` là một instance được **chia sẻ** để triển khai HTTP, không phải mỗi task tạo một HTTP client mới.
- Server dùng `HttpServer`, là HTTP server test fixture; **client virtual threads không có nghĩa server cũng tự chạy virtual threads**. Hai phía cấu hình concurrency độc lập.
- `close()` của executor trong try-with-resources chờ các virtual thread tasks hoàn tất theo contract Java 21.
- Demo chỉ có 9 GET và payload `OK`; **không** chứng minh một cấu hình chịu được hàng triệu users hay có exactly-once semantics.

Nếu project target Java 17, **không copy ví dụ này** vào module `--release 17`. Bạn có thể dùng `sendAsync` trên Java 17 như ví dụ tiếp theo, hoặc nâng runtime lên 21+ theo kế hoạch tương thích/QA.

## 14. `HttpClient`: khi protocol là HTTP, dùng abstraction HTTP

`java.net.http.HttpClient` trong Java 17 quản lý nhiều phần của HTTP request–response:

- `HttpRequest` với URI, HTTP method, headers, body publisher, timeout.
- `HttpResponse<T>` với status/headers/body theo `BodyHandler`.
- `send(...)` đồng bộ, `sendAsync(...)` trả `CompletableFuture<HttpResponse<T>>`.
- `HTTP_1_1` và `HTTP_2` là HTTP versions được hỗ trợ theo configuration/peer negotiation.
- TLS `https://`, proxy, redirects và authentication theo API; ứng dụng vẫn phải đặt policy đúng.
- Client instance có thể **được chia sẻ để tận dụng connection resources** thay vì tạo mới cho mỗi request; connection reuse cụ thể không phải invariant mọi server/request.
- Streaming request/response qua `BodyPublisher` và `BodyHandlers.ofInputStream/ofLines/ofPublisher` khi payload lớn hoặc cần processing dần.

**HttpClient là client**, không phải API để `accept()` kết nối đến. Nếu muốn **phục vụ HTTP** trên Java 17, có `jdk.httpserver.HttpServer` cho nhu cầu nhúng tối giản hoặc framework/server có security, routing, HTTP protocol và production features theo yêu cầu.

Đừng tự dựng HTTP GET bằng `Socket` và nối string header; TLS, redirects, proxy, chunked response, status codes, header validation, keep-alive, HTTP/2... đều là các chi tiết protocol khó tự làm đúng.

## 15. `send` hay `sendAsync` khi gọi nhiều HTTP services?

| Cách | Tác vụ đọc code | Phù hợp | Chú ý |
| --- | --- | --- | --- |
| `HttpClient.send` trên platform thread (Java 17) | Tuần tự blocking | Ít calls, logic service đơn giản, worker budget đủ | Blocking threads bị giữ trong lúc chờ network |
| `HttpClient.sendAsync` (Java 17+) | Future-based async | Fan-out nhiều HTTP requests, pipeline, limit concurrent work | Callback chaining, cancellation propagation, handle exceptions và backpressure |
| `HttpClient.send` trong virtual thread (Java 21+) | Tuần tự blocking style, thread nhẹ khi I/O | Nhiều independent requests, code tuyến tính, bounded downstream | Không biến HTTP 500 thành success; không loại timeout/quotas |
| HTTP qua raw `Socket` | Tự thực hiện framing/TLS/HTTP protocol | Chỉ khi đang viết library/server/proxy có lý do rất cụ thể | Chi phí correctness/security lớn, thường không nên |

Trên Java 17, `sendAsync` có thể cho nhiều requests cùng in-flight mà không chặn một platform thread riêng ở caller cho mỗi request. Nhưng **thousands of sendAsync futures** không đồng nghĩa downstream có thể chịu thousands of concurrent HTTP requests. Cần giới hạn in-flight, connection/body budgets và retry rate.

`HttpClient.Version.HTTP_2` là **ưu tiên** phía client, không phải ép mọi endpoint sẽ dùng HTTP/2; kiểm tra `response.version()` hoặc negotiate behavior nếu protocol matters.

## 16. Ví dụ Java 17+ D — shared HttpClient + sendAsync theo batch

Chương trình độc lập **`HttpClientWorkloadDemo.java`** tạo HTTP server loopback `jdk.httpserver` trả `item-N` theo URI path. Một `HttpClient` chung gửi **6 GET**, nhưng chia thành **hai batch, tối đa 3 requests cùng được submit trong một batch**. Code đợi toàn bộ futures mỗi batch trước khi gửi batch kế tiếp.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class HttpClientWorkloadDemo {
    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(4);
        AtomicInteger requests = new AtomicInteger();
        server.createContext("/item/", exchange -> {
            try {
                requests.incrementAndGet();
                String id = exchange.getRequestURI().getPath()
                        .substring("/item/".length());
                byte[] bytes = ("item-" + id).getBytes(
                        StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=UTF-8");
                exchange.sendResponseHeaders(200, bytes.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(workers);
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            List<HttpResponse<String>> replies = new ArrayList<>();
            final int batchSize = 3;
            for (int start = 0; start < 6; start += batchSize) {
                List<CompletableFuture<HttpResponse<String>>> batch =
                        new ArrayList<>();
                for (int i = start; i < start + batchSize; i++) {
                    HttpRequest req = HttpRequest.newBuilder(
                            URI.create(base + "/item/" + i))
                            .timeout(Duration.ofSeconds(5))
                            .GET().build();
                    batch.add(client.sendAsync(req,
                            HttpResponse.BodyHandlers.ofString()));
                }
                for (CompletableFuture<HttpResponse<String>> f : batch) {
                    replies.add(f.join());
                }
            }
            boolean statuses = true;
            boolean orderedBodies = true;
            for (int i = 0; i < replies.size(); i++) {
                statuses &= replies.get(i).statusCode() == 200;
                orderedBodies &= ("item-" + i)
                        .equals(replies.get(i).body());
            }
            System.out.println("HTTP replies: " + replies.size());
            System.out.println("Batch cap: " + batchSize);
            System.out.println("All status 200: " + statuses);
            System.out.println("Bodies follow request order: "
                    + orderedBodies);
            System.out.println("Server handled: " + requests.get());
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Chạy trên Java 17+:

```sh
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 HttpClientWorkloadDemo.java
java --add-modules jdk.httpserver HttpClientWorkloadDemo
```

Stdout đã kiểm thử:

```text
HTTP replies: 6
Batch cap: 3
All status 200: true
Bodies follow request order: true
Server handled: 6
```

Giải thích:

1. `HttpClient.newBuilder()` dùng lại **cùng client instance** cho mọi requests; body được xử lý bởi `BodyHandlers.ofString()` vì payload nhỏ.
2. `sendAsync` trả future; code lưu theo **thứ tự submission**. Dù response của request thứ 2 về trước request thứ 1, việc gom future theo thứ tự vẫn cho danh sách đúng thứ tự nghiệp vụ đã định nghĩa.
3. Mỗi `HttpRequest` đặt `timeout(Duration.ofSeconds(5))` và client có `connectTimeout` riêng.
4. `batchSize=3` là một cơ chế **bounded fan-out đơn giản**, không phải limiter tinh vi cho workload liên tục. Trong production, có thể dùng semaphore, bounded scheduler hoặc rate limiter để duy trì throughput khi một request chậm mà không chặn toàn batch.
5. `All status 200` được **kiểm tra rõ**; `sendAsync` hoàn tất bình thường với response có status 500 nếu giao thức HTTP nhận được response, nên không bỏ qua status.
6. `Bodies follow request order` đo correctness của test, **không** có nghĩa network completions diễn ra đúng thứ tự.
7. Server là `HttpServer` gọn để tự kiểm thử trên loopback. Nó **không minh họa HTTPS, HTTP/2, retry hoặc security production**.

Nếu payload lớn hoặc unbounded, **đừng dùng `ofString()` để gom toàn response vào memory**; lựa chọn streaming body handler phù hợp, consume/close đúng để giải phóng tài nguyên.

## 17. Ma trận trade-off: complexity, memory, latency và workload

| Yếu tố | Blocking Socket + platform threads | Selector / NIO | Virtual threads + blocking API | HttpClient (sendAsync hoặc send) |
| --- | --- | --- | --- | --- |
| Protocol | TCP bytes tự định nghĩa | TCP bytes tự định nghĩa | TCP/HTTP/... qua API blocking | HTTP |
| Độ phức tạp code I/O | Thường thấp | Cao hơn, event state machine | Thường thấp (code tuyến tính) | HTTP thấp; async composition cần hiểu futures |
| Rất nhiều connections idle | Thread budget có thể thành nút nghẽn | Thường là điểm mạnh | Java 21+, có thể là lựa chọn tốt nếu OS sockets/heap đủ | HTTP keep-alive/HTTP2 tùy peer; không áp dụng cho arbitrary TCP server |
| Tác vụ chủ yếu chờ I/O | Giữ platform workers | Event loop multiplex readiness | Carrier có thể được dùng lại | Futures hoặc virtual-thread callers hỗ trợ |
| Tác vụ CPU-heavy | Bounded CPU workers | **Phải offload khỏi event loop** | Không tạo CPU cores mới | Body parsing cũng cần CPU quota |
| Framing/messages | Tự thiết kế | Tự thiết kế + partial buffer state | Tự thiết kế nếu dùng raw Socket | HTTP framing do client triển khai |
| TLS | `SSLSocket`/JSSE hoặc lớp TLS | `SSLEngine`/framework, phức tạp hơn | Tùy API blocking đang dùng | `https://` hỗ trợ JSSE theo client API |
| Thời điểm dừng/timeout | Socket/blocking lifecycle | Cancel key/close channel | Interrupt/cancel task + close resources | Future cancel/request timeout/body cleanup |
| Giới hạn resources | Threads, sockets, queues | Keys, buffers, loop CPU, queues | Heap, sockets, downstream quotas, permits | In-flight, connections, response buffers, retries |
| Java 17 | Có | Có | **Chưa có chính thức** | Có |

Đây là **ma trận đánh giá**, không phải bảng benchmark xếp hạng. Lợi thế phụ thuộc OS, connection patterns, JDK, message size, TLS và workload thực tế.

## 18. Khi nào chọn từng cách — bốn tình huống cụ thể

### Tình huống A: một TCP service nội bộ, 40 clients, messages nhỏ

Nếu mỗi connection gửi vài messages ngắn/s và số worker, memory, file descriptors nằm trong quota: **`Socket` + bounded executor** có thể là lựa chọn ít rủi ro về complexity. Đặt deadline, frame bounds, TLS và connection caps, test slow client. Đừng cần một selector event-loop tự viết chỉ để tiết kiệm vài chục platform threads nếu không có vấn đề hiệu năng.

### Tình huống B: hàng chục nghìn TCP connections, phần lớn idle

`Selector` có thể giảm platform-thread-per-connection costs và cho phép kiểm soát OP_READ/OP_WRITE. Nhưng mỗi connection vẫn giữ FD, kernel buffers, ByteBuffers và application state. Cần event-loop sharding, per-connection quotas, fairness, worker offload, backpressure, half-close/reconnect state và load testing. Nếu đang chạy Java 21+ và team thích blocking style, **virtual threads cũng nên được benchmark như ứng viên**, không mặc định selector luôn thắng.

### Tình huống C: microservice gọi 5 downstream HTTP APIs/operation

Chọn `HttpClient` vì **giao thức là HTTP**. Trên Java 17 dùng `sendAsync` + bounded fan-out/`CompletableFuture` composition; trên Java 21+ có thể dùng virtual threads gọi `send` dễ đọc hơn. Dùng deadline tổng theo request, giới hạn body, retry idempotent, tracing và circuit breaker. Đừng mở raw `Socket` chỉ để gửi GET/POST.

### Tình huống D: 500 tasks đều đang nén video bằng CPU

Không có lý do mong virtual threads hoặc selector làm CPU chạy 10 lần nhanh hơn. Chọn **bounded CPU worker pool** theo số cores/thông số pipeline và measurement; tránh chặn selector loop. Nếu một task còn chờ disk/network, tách I/O và CPU stages và áp queue capacity; nén CPU là bottleneck thì tập trung thuật toán, I/O pipeline hoặc phần cứng.

## 19. Độ tin cậy không đến tự động từ concurrency primitive

**TCP** cung cấp luồng byte có thứ tự và kiểm tra truyền tải, nhưng **không** biết “đơn hàng đã commit” hoặc “message đã được xử lý một lần”. **Selector** chỉ báo readiness. **Virtual threads** chỉ thay cách lập lịch blocking tasks. **HttpClient** triển khai HTTP protocol nhưng không tự bảo đảm business idempotency.

Ví dụ:

```text
Client -> gửi POST tạo đơn hàng
Server -> đọc bytes -> DB COMMIT
Mạng lỗi / client timeout trước khi nhận response
Client -> UNKNOWN outcome
Client retry POST không key -> có thể tạo đơn thứ hai
```

Để có reliability theo nghiệp vụ:

- **Operation ID / idempotency key** được định danh trước request đầu tiên, gửi lại cùng key.
- **Server-side dedup** durable/atomic cùng transaction hoặc state machine.
- **ACK đúng nghĩa**: phân biệt bytes đã được kernel chấp nhận, HTTP response 202, server đã xử lý, DB commit, người dùng đã thấy kết quả.
- **Status/reconciliation API** khi response bị mất nhưng server có thể đã xử lý.
- **Retry semantics** theo GET/PUT/POST và thỏa thuận API thực, có bounded attempts/backoff+jitter.
- **Timeout/deadline** ở tầng kết nối, network I/O, business request và toàn operation.

Không lấy `socket.close()`, `SelectionKey.cancel()`, `future.cancel(true)` hay `Thread.interrupt()` làm bằng chứng remote side effect đã được thu hồi.

## 20. Backpressure là yếu tố quyết định khả năng sống sót khi quá tải

Bất kể chọn công cụ nào, nếu producer nhanh hơn consumer thì **outbound/inbound queues** có thể tăng vô hạn. Phải tách các giới hạn:

| Resource | Hạn mức cần suy nghĩ |
| --- | --- |
| TCP accepted connections | Max open sockets/FDs, idle limit, pending accept backlog |
| Blocking worker tasks | Active workers + **bounded queue**, rejection policy |
| Selector buffers | Max pending outbound bytes/connection, per-event write budget |
| Virtual thread work | Max in-flight business operations, downstream semaphore, heap budget |
| HttpClient fan-out | Max in-flight requests, per-host quotas, timeout, retry budget |
| Request body | Max bytes, max decoded size, parser depth/line length |
| Slow consumers | Pause producer, enforce per-tenant limits, drop/close theo protocol |
| Downstream DB | Pool size, query timeout, queue limits, circuit breaker |

**Pool size không đồng nghĩa queue size.** `Executors.newFixedThreadPool(n)` có **unbounded queue** theo contract. Với production cần `ThreadPoolExecutor` có bounded queue hoặc admission pattern phù hợp, kèm `RejectedExecutionHandler` rõ ràng.

**Virtual threads không cần pool**, nhưng điều đó **không** có nghĩa cứ tạo số lượng request không giới hạn. Semaphore/connection pool vẫn phải giữ mức công việc an toàn.

**Selector không có memory magic**: hàng nghìn keys mà mỗi key giữ một queue 10 MiB vẫn chiếm nhiều GiB. Chọn max queued bytes và đo saturation.

## 21. Tính toán capacity: quota thay vì một con số “tối đa kết nối”

Một cách ước lượng ban đầu (để lập ngân sách, **không** thay benchmark):

```text
Memory dùng bởi connection state xấp xỉ:
  concurrent connections
  × (user-space buffers + per-connection objects)
  + JVM/GC/stack/heap overhead
  + kernel socket buffers (không hoàn toàn nằm trong JVM heap)

HTTP in-flight concurrency xấp xỉ:
  request arrival rate × average response time
(đây là trực giác Little's Law cho hệ tương đối ổn định)

CPU capacity:
  số CPU-bound tasks thực sự chạy song song
  bị giới hạn bởi cores và scheduling overhead

Downstream maximum:
  min(local in-flight quotas, remote capacity, connection-pool limits)
```

Ví dụ **giả định**: 500 RPS, thời gian round-trip trung bình 200 ms, nên in-flight trung bình xấp xỉ `500 × 0,2 = 100` operations trong tình huống ổn định. Nhưng p99 latency và burst có thể khiến peak cao hơn đáng kể; phải lập kế hoạch theo distribution và overload scenarios, không chỉ average.

Nếu một socket giữ 64 KiB user-space buffers, 20.000 sockets tương ứng khoảng **1,22 GiB** user-space buffers chưa kể overhead (20.000 × 65.536 bytes ≈ 1,22 GiB). **Virtual threads không loại bỏ những buffers ấy**, selector cũng không. Bounded buffer/pooling chỉ an toàn khi ownership và memory caps rõ.

Các con số trên là tính toán giả định để minh họa capacity planning, **không phải cấu hình mặc định của Java**.

## 22. Timeout và cancellation theo từng mô hình

| Mô hình | Cơ chế thường dùng | Hạn chế/cảnh báo |
| --- | --- | --- |
| Blocking `Socket` | `connect(timeout)`, `setSoTimeout`, close socket, interrupt task | `setSoTimeout` giới hạn một read block, không bảo đảm toàn business SLA |
| `Selector` | `select(timeout)`, deadline state, cancel key, close channel, `wakeup()` | `select(timeout)` là timeout chờ readiness, không phải per-request deadline; cần tự theo dõi |
| Virtual threads | `interrupt()`/`Future.cancel`, deadlines, close owned resources | Cooperative cancellation, không hủy remote side effect; Java 21+ mới có stable API |
| `HttpClient` | `connectTimeout`, `HttpRequest.timeout`, `sendAsync` cancellation, close body | Status 5xx/timeout không đồng nghĩa server chưa commit; streaming body có lifecycle riêng |

**Deadline end-to-end** nên bao gồm queue wait, DNS/connect/TLS, upload, server processing, response consumption và retry attempts. Một socket vẫn “đọc được một byte mỗi 10 giây” có thể tránh read timeout ngắn nhưng làm toàn operation treo lâu — phải có total deadline/idle-rate policy.

Khi receiver dùng `BodyHandlers.ofInputStream()`, `HttpResponse` có thể tới sau headers **trước khi body hoàn tất**; phải consume hoặc close body stream. Với `ofPublisher()`, cần subscribe/request tới terminal event hoặc cancel đúng cách.

## 23. TLS và security: không chọn primitive rồi bỏ qua giao thức

- `Socket`/`SocketChannel` chỉ cung cấp TCP; HTTPS/TLS đòi JSSE `SSLSocket`, `SSLContext`, hoặc `SSLEngine` (NIO TLS state machine phức tạp). Không truyền token hay dữ liệu người dùng plaintext trên mạng không tin cậy.
- `HttpClient` xử lý HTTPS trên JSSE theo configuration; **không** vì vậy mà có sẵn business authorization/token refresh.
- Virtual threads không tự mã hóa traffic. Chúng có thể chạy TLS/HTTP blocking APIs theo ngữ nghĩa của những APIs đó.
- Selector không tự có HTTP parser, WebSocket frames, HTTP/2 streams hoặc message integrity ở tầng ứng dụng.
- Với mọi server cần max body/header, authn/authz từng resource, rate limits, URL/path validation, log redaction và chống slowloris.
- Với nhiều tenants, tránh chia sẻ mutable credential state và session data sai scope. Một `HttpClient` chia sẻ resources **không** được trở thành nơi trộn bearer tokens/cookies của những security principals không tương thích.

Không khắc phục TLS handshake lỗi bằng `trustAll` manager/disable hostname verification. Nếu dùng reverse proxy để terminate TLS, cần chính sách trusted forwarded headers và bảo vệ traffic giữa gateway/backend.

## 24. HTTP status, retry và idempotency theo thực tế

`sendAsync` hoàn tất bình thường khi nhận được HTTP response hợp lệ, kể cả status **404/429/500**, trừ lỗi protocol/handler/transport cụ thể. Luôn kiểm tra `statusCode()`.

- **GET/HEAD** thường safe và idempotent theo HTTP semantics, có thể retry có giới hạn nếu API thật tuân thủ.
- **PUT/DELETE** có semantics idempotent theo HTTP nhưng vẫn cần conditional version/ETag và hiểu rằng status của attempts có thể khác.
- **POST** tạo payment/order không mặc định idempotent. Nếu response bị mất sau commit, blind retry có thể tạo thêm effect.
- **Timeout/interrupt/cancel** không phải “server chưa xử lý”; state có thể **UNKNOWN_OUTCOME**.
- **`Retry-After`**, exponential backoff, jitter và retry budget giúp tránh thác retry khi downstream quá tải.

Đối với TCP protocol tự thiết kế, bạn cần **tự định nghĩa** các semantics tương tự: request ID, ACK level, duplicate detection, status query và replay từ durable log nếu business đòi hỏi. TCP byte delivery không cung cấp các hợp đồng này.

## 25. Quan sát hiệu năng đúng thay vì nhìn mỗi CPU tổng

Một bộ metrics hữu ích:

| Nhóm | Đo những gì | Giúp quyết định |
| --- | --- | --- |
| Traffic | Connections open, active/idle, RPS, bytes in/out, avg/p95/p99 body | Idle fan-in hay request-heavy |
| Platform workers | Thread count, active workers, queue length, rejection, blocked time | Socket thread model có đang bão hòa? |
| Selector | select wakeups, selected-key count, OP_WRITE-ready when idle, loop lag, per-key queue bytes | Event loop có spin/starvation? |
| Virtual threads | Virtual task concurrency, blocked vs CPU, pinned operations tùy JDK, heap usage | Đang tận dụng blocking I/O scalability hay nghẽn downstream? |
| HttpClient | In-flight requests, response versions, status mix, connect/TLS errors, body lifetimes | HTTP concurrency/reuse/cancellation policy có đúng? |
| Downstream | DB pool waits, RPC latency, 429/503, queue depth, retries | Bottleneck có ở server phía xa không? |
| Reliability | Timeout/cancelled vs committed, duplicate IDs, partial frames, reconciliation | Client lỗi có gây sai business state? |

Đo **p95/p99 latency và throughput cùng error rate**, không chỉ CPU%. Nhiều loại bottlenecks có thể cùng tồn tại: CPU thấp nhưng queue dài vì một lock/DB pool, selector loop CPU cao do đăng ký `OP_WRITE` sai, hoặc virtual threads tăng nhưng remote API giới hạn 429.

Mỗi benchmark cần cùng payloads, same hardware/JDK/GC, warmup, concurrent connections, keep-alive/TLS settings, network faults và request mix để công bằng.

## 26. Những lỗi chọn công nghệ thường gặp

1. **“HttpClient là server HTTP.”** Sai: `HttpClient` gọi HTTP endpoints; HTTP server cần `HttpServer`/framework.
2. **“Có 10.000 sockets thì Java bắt buộc dùng Selector.”** Không: Java 21 virtual threads là một ứng viên có thể benchmark; constraints quyết định.
3. **“Virtual threads có trong Java 17 LTS.”** Sai: chính thức từ Java 21, không compile trên `--release 17`.
4. **“Virtual threads tự tăng CPU cores.”** Sai: chủ yếu giúp I/O-bound concurrency, không tăng tốc tính toán CPU nặng.
5. **“Phải pool virtual threads để hạn chế concurrency.”** Không nên: dùng semaphore/quotas của resource thật.
6. **“Selector có nhiều keys nên không cần memory cap.”** Mỗi connection vẫn có buffers, queues, FD/kernel overhead.
7. **“OP_WRITE phải bật luôn để sẵn sàng gửi.”** Dễ tạo busy loop CPU khi outbound trống.
8. **“Một read() TCP trả một business message.”** TCP là byte stream; phải có framing.
9. **“Socket write() thành công nghĩa server đã commit.”** Nó không phải business ACK.
10. **“Selector.read/write luôn hoàn tất mọi bytes.”** Nonblocking I/O có thể partial/zero.
11. **“Đưa DB query blocking vào selector event loop cho tiện.”** Có thể làm mọi connection lag; offload bounded.
12. **“Một HttpClient mới cho mọi request sẽ luôn nhanh hơn.”** Thường mất cơ hội reuse resources, tăng overhead.
13. **“HttpClient sendAsync có nghĩa gửi 100.000 requests an toàn.”** Cần max in-flight, response caps và rate limit.
14. **“HTTP 500 tự động ném IOException.”** Không mặc định: HTTP response status phải được ứng dụng xét.
15. **“Có virtual threads nên có thể tạo vô hạn DB connections.”** Không: DB pool/remote capacity vẫn giới hạn.
16. **“Thread pool 8 workers có queue tối đa 8.”** Không: `newFixedThreadPool` dùng unbounded queue.
17. **“`setSoTimeout` là tổng deadline cho request.”** Chỉ kiểm soát blocking read, không tự đo whole operation.
18. **“Socket/selector cancel sẽ rollback job remote.”** Không có bảo đảm đó.
19. **“HttpClient hỗ trợ HTTP/2 nên mọi server sẽ chạy HTTP/2.”** Phải negotiate; version là preference.
20. **“Dùng Java 21+ là bỏ được backpressure.”** Không: vẫn cần quotas/bounded queues/deadlines.
21. **“One-thread-per-connection luôn kém NIO.”** Không có quy tắc tuyệt đối, còn phụ thuộc workload và phiên bản JVM.
22. **“Đóng HTTP response stream không quan trọng.”** Streaming body phải consume/close để tránh giữ resource.
23. **“Cứ thay code hiện tại bằng NIO là độ tin cậy tốt hơn.”** State-machine complexity có thể tạo lỗi khó phát hiện hơn.
24. **“Dùng nonblocking đồng nghĩa không có blocking ở nơi khác.”** Parser, file I/O, DB calls, locks vẫn có thể block.
25. **“Chỉ đo RPS cao nhất là đủ.”** Reliability, p99, error rate, security, memory và maintainability cũng quan trọng.

## 27. Câu hỏi tự kiểm tra kiến thức

**Câu 1.** Một app Java 17 cần gọi 40 REST endpoints song song, phải dùng raw `Socket` hay virtual threads? **Không.** Dùng `HttpClient.sendAsync` có giới hạn in-flight; virtual threads chính thức không có trên Java 17.

**Câu 2.** Java 21+, 5.000 tasks chủ yếu chờ HTTP/DB, muốn code đọc theo kiểu tuần tự: lựa chọn nào đáng thử? **Virtual threads**, dùng API blocking thích hợp và semaphore/DB quotas.

**Câu 3.** Server có 50.000 TCP connections idle. Selector giải quyết được điều gì? **Multiplex readiness của nhiều nonblocking channels**, giảm nhu cầu platform-thread-per-connection; không loại socket/heap budgets.

**Câu 4.** `SelectionKey.OP_WRITE` có nên để luôn trong interest set? **Không** nếu outbound trống; nó có thể luôn ready gây CPU spin.

**Câu 5.** Một TCP `read` trả 6 bytes từ frame 20 bytes. Đó có phải packet lỗi không? **Không**. TCP là stream, parser phải đọc đủ frame theo length/delimiter.

**Câu 6.** `newVirtualThreadPerTaskExecutor()` có phải thread pool với 1000 carrier threads? **Không**; tạo virtual thread theo task; carriers và scheduling do runtime quản lý.

**Câu 7.** `sendAsync` trả response 500 thì future có bắt buộc exceptional không? **Không**; HTTP error status vẫn có thể là response bình thường, phải kiểm tra `statusCode()`.

**Câu 8.** “Một virtual thread có thể gọi HttpClient.send()” chứng tỏ hai lựa chọn loại trừ nhau? **Không**; chúng thuộc hai abstraction levels khác nhau.

**Câu 9.** Vì sao selector event loop không nên parse file ZIP 1 GiB trong callback? **CPU/blocking work sẽ làm các sockets khác chờ**; cần bounded worker/offload.

**Câu 10.** `Socket.close()` sau POST có chứng minh server chưa commit không? **Không**; cần operation ID/status reconciliation.

**Câu 11.** Nếu throughput bị giới hạn vì DB pool chỉ có 20 connections, việc tăng virtual threads từ 200 lên 20.000 có tự làm database nhanh hơn không? **Không**; cần cải thiện bottleneck/quota thực.

**Câu 12.** Một load test có 100.000 idle connections nhưng mỗi connection chỉ dùng 64 KiB user buffers. Chỉ tính buffers chiếm khoảng bao nhiêu? **Khoảng 6,1 GiB**, chưa kể connection state, OS/kernel và các lớp khác (100.000 × 65.536 bytes ≈ 6,1 GiB).

## 28. Checklist chọn giải pháp trước khi production

- [ ] Xác định **protocol** trước: raw TCP / HTTP(S) / streaming? Incoming server hay outgoing client?
- [ ] Đo workload: concurrent open vs active sockets, I/O wait vs CPU, RPS/messages, payload distribution và peak bursts.
- [ ] Chốt JDK runtime: **Java 17** hay **Java 21+**. Không dùng stable virtual-thread API trong build Java 17.
- [ ] Với TCP custom, định nghĩa **framing, byte order, charset, max frame, EOF, heartbeat, reconnect** rõ.
- [ ] Nếu dùng `Socket`, có **bounded workers/connections**, connect/read deadlines, cleanup và saturation metrics.
- [ ] Nếu dùng `Selector`, có **per-channel state**, partial reads/writes, OP_WRITE toggling, wakeup/mailbox và bounded queues.
- [ ] Nếu dùng virtual threads, **không pool chúng**; limit operations bằng semaphore/downstream quotas, test pinning/driver theo JDK.
- [ ] Nếu dùng HTTP, ưu tiên **`HttpClient`**, chia sẻ client hợp lý, chọn `send/sendAsync` theo concurrency model.
- [ ] Đặt timeout/deadline cho **toàn operation**, không chỉ socket read/connect; kiểm tra cancellation propagation.
- [ ] Giới hạn **bytes in memory**, HTTP body size, in-flight requests, retry budget và queue depth.
- [ ] Có **TLS/mTLS, authn/authz**, secrets isolation, input validation và trusted-proxy policy.
- [ ] Tách **transport acknowledgement** khỏi **business acknowledgement**; operation ID/idempotency nếu có side effects.
- [ ] Có load test thực: p50/p95/p99, throughput, error rate, peak memory, GC, FD, worker/selector lag.
- [ ] Kiểm thử faults: slow readers, half-close, timeout, unreachable peer, HTTP 429/500, disconnect sau commit.
- [ ] Ghi lại **decision rationale**: tại sao một model thắng, rủi ro chưa giải quyết, người sở hữu và đường migration.

**Kết luận:** Chọn `Socket` khi muốn xử lý **TCP custom protocol đơn giản với số connections nằm trong quota**, chọn `Selector` khi cần **multiplex nonblocking cho nhiều sockets idle/slow và chấp nhận quản lý state phức tạp**, chọn **virtual threads trên Java 21+** để duy trì **blocking code dễ đọc cho nhiều I/O-bound tasks**, và chọn **`HttpClient` khi giao thức là HTTP**. Chúng có thể kết hợp, nhưng **không công cụ nào thay thế thiết kế framing, backpressure, deadlines, security và idempotency**. Độ tin cậy đến từ **contract ứng dụng + giới hạn tài nguyên + kiểm thử đo đạc**, không đến từ tên API.

### Tài liệu chuẩn

- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Java SE 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html)
- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [JEP 444 — Virtual Threads finalized in JDK 21](https://openjdk.org/jeps/444)
- [Oracle Java 21 — Virtual Threads and best practices](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Java SE 21 — Executors.newVirtualThreadPerTaskExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [RFC 9110 — HTTP semantics and idempotence](https://www.rfc-editor.org/rfc/rfc9110.html).
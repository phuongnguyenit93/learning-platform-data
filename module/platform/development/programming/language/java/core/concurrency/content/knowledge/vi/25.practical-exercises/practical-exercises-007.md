# So sánh platform threads và virtual threads cho tác vụ I/O

## 1. Bài toán thực tế và kết quả cần đạt

Giả sử một chương trình Java phải gửi hàng trăm HTTP request tới một dịch vụ khác. Phần lớn thời gian của mỗi request nằm ở việc chờ phản hồi mạng, còn CPU chỉ xử lý một lượng dữ liệu nhỏ. Nên tạo một platform thread cho mỗi request, dùng thread pool cố định, hay dùng virtual thread cho mỗi request?

Bài thực hành so sánh **platform threads** và **virtual threads** bằng cùng một tập công việc I/O. Bạn sẽ chạy một HTTP server giả lập ngay trên máy, gửi các HTTP request đồng bộ bằng `HttpClient.send(...)`, kiểm tra kết quả đúng, đo thời gian của toàn bộ batch và quan sát tác động của giới hạn đồng thời.

**Yêu cầu môi trường:** **JDK 21 trở lên**. Virtual threads được chuẩn hóa trong Java 21 (JEP 444). Các API `Executors.newVirtualThreadPerTaskExecutor()`, `Thread.ofVirtual()` và `Thread.isVirtual()` có thể không tồn tại hoặc chưa ổn định ở JDK 17. Không dùng `--enable-preview` cho virtual threads trên Java 21+.

**Mục tiêu sau khi hoàn thành:**

1. Giải thích platform thread giữ một OS thread trong thời gian sống, trong khi virtual thread có thể nhường carrier khi gặp thao tác blocking I/O được JVM hỗ trợ.
2. Chạy **cùng logic request** dưới ba cơ chế: platform pool giới hạn, virtual thread cho mỗi task, và virtual thread có semaphore giới hạn dịch vụ downstream.
3. Phân biệt **throughput của cả batch**, **latency một request**, số tác vụ đồng thời và khả năng dùng tài nguyên.
4. Đo thời gian nhưng luôn kiểm cả status code, response body, số request thành công/thất bại.
5. Nêu vì sao virtual threads không làm CPU nhanh hơn, không bỏ được giới hạn connection pool, rate limit, file descriptor hoặc capacity của hệ thống đích.
6. Chẩn đoán ảnh hưởng của blocking I/O, pinning theo phiên bản JDK, timeout, interruption, backpressure và shutdown.

Bài này chỉ sử dụng Java SE và module `jdk.httpserver` của JDK, không phụ thuộc framework.

## 2. Khái niệm cốt lõi

### Platform thread

`Thread.ofPlatform()` tạo một Java thread được gắn với OS thread. Khi Java code thực hiện blocking I/O đồng bộ, OS thread đó thường bị giữ lại trong thời gian chờ. Việc tạo quá nhiều platform threads có thể làm tăng chi phí stack, scheduling, memory và số lượng OS threads.

`Executors.newFixedThreadPool(12)` tạo pool có tối đa 12 worker platform threads chạy đồng thời; nếu 120 tác vụ đều chờ I/O, các tác vụ thứ 13 trở đi phải đợi trong hàng đợi executor đến khi có worker rảnh.

### Virtual thread

`Thread.ofVirtual()` tạo virtual thread được JVM quản lý. Khi virtual thread gặp một thao tác blocking I/O có hỗ trợ unmount, JVM có thể tạm tháo virtual thread khỏi platform **carrier thread**, để carrier chạy công việc khác trong khi I/O đang chờ. Sau khi có kết quả I/O, virtual thread sẽ tiếp tục chạy trên carrier thích hợp.

`Executors.newVirtualThreadPerTaskExecutor()` khởi chạy **một virtual thread mới cho mỗi task được submit**; đó không phải một pool virtual threads cố định. Một lượng lớn request chờ mạng có thể cùng tồn tại mà không cần một OS thread riêng cho từng request.

**Không có phép màu:** CPU vẫn thực thi code trên các platform carrier threads. Nếu 1.000 task cùng cần 100% CPU, virtual threads không cung cấp 1.000 lõi CPU. Nếu dịch vụ đích chỉ cho 20 kết nối đồng thời, tạo 10.000 virtual threads cũng không tăng khả năng phục vụ của dịch vụ đó.

| Góc nhìn | Platform thread / fixed pool | Virtual thread / thread-per-task |
| --- | --- | --- |
| Gắn với OS thread | Platform thread giữ OS thread trong thời gian sống. | Virtual thread được JVM mount lên carrier khi chạy; có thể unmount khi chờ hỗ trợ. |
| Chi phí mỗi thread | Thường cao hơn, khó mở rộng đến số lượng rất lớn. | Thường thấp hơn, phù hợp nhiều tác vụ chờ đồng thời. |
| Khi blocking I/O | Một worker trong pool bị chiếm đến khi lời gọi trả về. | Với blocking API hỗ trợ unmount, carrier được dùng cho task khác. |
| Khi CPU-bound | Bị giới hạn bởi lõi CPU, cùng chi phí scheduler. | Vẫn bị giới hạn bởi lõi CPU; không mặc nhiên nhanh hơn. |
| Phong cách code | Dễ viết đồng bộ, nhưng cần quản lý số platform threads. | Có thể giữ code đồng bộ, mỗi tác vụ một thread. |
| Giới hạn downstream | Vẫn phải kiểm soát connection/rate/memory. | Vẫn phải kiểm soát connection/rate/memory; thread rẻ không có nghĩa tác vụ miễn phí. |
| Tooling | Thread dump, JFR, profiler, metrics. | Có thread dump/JFR dành cho virtual threads và các event liên quan. |

Virtual threads chủ yếu giúp **mở rộng số tác vụ đồng thời đang chờ** và tăng throughput dưới workload phù hợp. **Một HTTP request riêng lẻ không tự nhiên có latency thấp hơn** chỉ vì chạy trong virtual thread.

## 3. Thiết kế thí nghiệm để so sánh công bằng

Bài sẽ dùng một HTTP server nội bộ:

- Chỉ lắng nghe `127.0.0.1` trên cổng được hệ điều hành cấp tự động (port `0`), không phụ thuộc Internet.
- Mỗi request đến `/slow` được xử lý bởi server executor **riêng** dùng virtual threads, giả lập công việc chờ bằng `Thread.sleep(100)` rồi trả `HTTP 200` và body `ok`.
- Client gửi `120` HTTP GET request đồng bộ với **một HttpClient dùng chung**, cùng endpoint, timeout và kiểm tra body.
- Chạy ba lượt **theo thứ tự**, đợi tất cả Future của lượt trước kết thúc rồi mới bắt đầu lượt sau.
- Tính tổng kết quả và elapsed time cho cả batch. Time có thể thay đổi giữa lần chạy, máy, OS và JDK.

Ba cấu hình:

1. **`platform-12`:** `Executors.newFixedThreadPool(12)`, 120 task được nạp vào pool; tối đa 12 client tasks chạy đồng thời.
2. **`virtual-unbounded`:** `Executors.newVirtualThreadPerTaskExecutor()`; về phía client không đặt semaphore giới hạn. Với 120 task, có thể có nhiều request chờ cùng lúc, nhưng giới hạn thực tế còn phụ thuộc HttpClient, socket, server và OS.
3. **`virtual-limited-24`:** vẫn mỗi task một virtual thread, nhưng dùng `Semaphore(24)` để tối đa 24 client request đang sử dụng tài nguyên phía đích. Các task khác chờ permit bằng cơ chế đồng bộ.

**Vì sao server dùng executor riêng?** Nếu server cũng chỉ có một platform worker, mọi request có thể bị tuần tự hóa ở phía server và che mất tác động của client scheduling. Ngược lại, nếu server cũng dùng rất nhiều virtual threads, thí nghiệm đang kiểm thử một hệ thống gồm **cả client lẫn server** hỗ trợ số lượng kết nối lớn. Vì vậy các kết quả phải được hiểu là số đo end-to-end của hệ thống cục bộ, không phải một benchmark tuyệt đối của thread.

**Chú ý:** `Thread.sleep` trên server chỉ mô phỏng thời gian chờ có thể điều phối; phần so sánh client sử dụng **I/O HTTP thực qua loopback** bằng `HttpClient.send`. Nếu chỉ so sánh hai thread đang ngủ mà gọi đó là benchmark mạng thực tế, kết luận về socket, TCP, TLS và máy đích sẽ không chính xác.

## 4. Ví dụ chạy được bằng JDK 21+

Lưu toàn bộ mã sau thành **`ThreadIoComparison.java`**. Mã này biên dịch bằng JDK 21+ và chạy độc lập, không cần dependency ngoài JDK.

```java
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
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

public class ThreadIoComparison {
    private static final int REQUESTS = 120;
    private static final int PLATFORM_WORKERS = 12;
    private static final int VIRTUAL_LIMIT = 24;
    private static final int SERVER_DELAY_MS = 100;

    record Measurement(String label, int success, long elapsedMs) {}

    private static Measurement runBatch(
            String label,
            ExecutorService executor,
            HttpClient client,
            URI endpoint,
            int maxInFlight) throws Exception {

        Semaphore permits = new Semaphore(maxInFlight);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Boolean>> futures = new ArrayList<>();

        for (int i = 0; i < REQUESTS; i++) {
            futures.add(executor.submit(() -> {
                start.await();

                // Giới hạn số lời gọi I/O thực sự đang được thực hiện.
                permits.acquire();
                try {
                    HttpRequest request = HttpRequest.newBuilder(endpoint)
                            .timeout(Duration.ofSeconds(15))
                            .GET()
                            .build();

                    HttpResponse<String> response = client.send(
                            request,
                            HttpResponse.BodyHandlers.ofString());

                    return response.statusCode() == 200
                            && "ok".equals(response.body());
                } finally {
                    permits.release();
                }
            }));
        }

        long begin = System.nanoTime();
        start.countDown();

        int success = 0;
        for (Future<Boolean> future : futures) {
            if (future.get(30, TimeUnit.SECONDS)) {
                success++;
            }
        }

        long elapsedMs =
                TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - begin);

        return new Measurement(label, success, elapsedMs);
    }

    private static void show(Measurement m) {
        System.out.println(
                m.label() + ": success=" + m.success() + "/" + REQUESTS);
    }

    public static void main(String[] args) throws Exception {
        // Port 0: hệ điều hành chọn cổng loopback còn trống.
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        try (ExecutorService serverExecutor =
                     Executors.newVirtualThreadPerTaskExecutor();
             HttpClient client = HttpClient.newBuilder()
                     .connectTimeout(Duration.ofSeconds(5))
                     .build()) {

            server.setExecutor(serverExecutor);
            server.createContext("/slow", exchange -> {
                try {
                    Thread.sleep(SERVER_DELAY_MS);

                    byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
                    exchange.sendResponseHeaders(200, body.length);
                    exchange.getResponseBody().write(body);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    exchange.close();
                }
            });

            server.start();
            URI endpoint = URI.create(
                    "http://127.0.0.1:"
                            + server.getAddress().getPort() + "/slow");

            try {
                Measurement platform;
                try (ExecutorService workers =
                             Executors.newFixedThreadPool(PLATFORM_WORKERS)) {
                    platform = runBatch(
                            "platform-12", workers, client, endpoint,
                            PLATFORM_WORKERS);
                }

                Measurement virtual;
                try (ExecutorService workers =
                             Executors.newVirtualThreadPerTaskExecutor()) {
                    virtual = runBatch(
                            "virtual-unbounded", workers, client, endpoint,
                            REQUESTS);
                }

                Measurement limited;
                try (ExecutorService workers =
                             Executors.newVirtualThreadPerTaskExecutor()) {
                    limited = runBatch(
                            "virtual-limited-24", workers, client, endpoint,
                            VIRTUAL_LIMIT);
                }

                show(platform);
                show(virtual);
                show(limited);

                System.out.println("elapsedMs:");
                System.out.println("  platform-12="
                        + platform.elapsedMs());
                System.out.println("  virtual-unbounded="
                        + virtual.elapsedMs());
                System.out.println("  virtual-limited-24="
                        + limited.elapsedMs());

                if (platform.success() != REQUESTS
                        || virtual.success() != REQUESTS
                        || limited.success() != REQUESTS) {
                    throw new AssertionError(
                            "Có HTTP request thất bại hoặc trả dữ liệu sai");
                }
            } finally {
                server.stop(0);
            }
        }
    }
}
```

Đây là ví dụ dành cho **JDK 21+**, không phải chương trình chạy được trên Java 17. Compile module `jdk.httpserver` rõ ràng:

```bash
javac --add-modules jdk.httpserver ThreadIoComparison.java
java --add-modules jdk.httpserver ThreadIoComparison
```

Nếu môi trường chạy chặn loopback socket hoặc giới hạn số file descriptor, bài tập có thể không khởi động được server hoặc có các request thất bại; khi đó cần giải quyết hạn chế môi trường, không tự kết luận virtual threads chậm/sai.

### Output và cách đọc

**Ba dòng về tính đúng đắn** khi mọi HTTP request thành công sẽ là:

```text
platform-12: success=120/120
virtual-unbounded: success=120/120
virtual-limited-24: success=120/120
```

Sau đó chương trình in thêm:

```text
elapsedMs:
  platform-12=<thời gian đo thực tế>
  virtual-unbounded=<thời gian đo thực tế>
  virtual-limited-24=<thời gian đo thực tế>
```

Các chuỗi trong ngoặc nhọn chỉ là **ký hiệu minh họa** vị trí số đo, không phải stdout cố định. Giá trị thực do chương trình in ra là số nguyên mili-giây và **không thể dự đoán chính xác**. Máy, JDK, client HTTP, số kết nối mở, CPU, scheduling, GC và độ nóng của code đều ảnh hưởng kết quả.

Với workload chờ 100 ms/request và server có đủ capacity, `platform-12` thường phải xử lý nhiều lượt request hơn `virtual-unbounded`. Tuy nhiên không được khẳng định một tỉ lệ tốc độ cụ thể, hay rằng virtual luôn nhanh nhất. Thí nghiệm này còn chịu bottleneck của HTTP server và OS; nó chỉ là một phép đo có kiểm soát để **học cơ chế và đặt giả thuyết**.

### Phân tích từng đoạn

1. **Một server nội bộ:** `HttpServer.create(..., 0)` lấy port được hệ điều hành cấp. Dùng `127.0.0.1` tránh cần kết nối mạng ngoài; `server.stop(0)` đóng server trong `finally`.
2. **Cùng request cho ba phương án:** mọi task đều tạo GET `/slow`, chờ `HttpClient.send`, kiểm `statusCode()==200` và body đúng `ok`.
3. **Cùng lượng công việc:** mỗi lượt submit đúng `120` task; sau cùng phải có đúng `120` thành công. Không dùng số request đã submit thay cho số thực sự thành công.
4. **Platform pool có hàng đợi:** chỉ 12 worker thực hiện task cùng lúc; phần còn lại ở trong queue executor. Mỗi worker thường bị chiếm cho tới khi lời gọi gửi HTTP đồng bộ hoàn thành.
5. **Virtual thread per task:** executor tạo virtual thread mới cho từng task; khi chờ I/O được JVM hỗ trợ, nó có thể nhường carrier. Điều này giảm nhu cầu giữ một OS thread cho từng request.
6. **Semaphore là giới hạn tài nguyên đích:** virtual threads chờ permit trước khi phát HTTP request. Không tạo pool virtual thread cố định để giả lập giới hạn I/O; concurrency limit và loại thread là hai quyết định riêng.
7. **`CountDownLatch` cho cùng điểm xuất phát:** những task đã được executor chạy chờ `start.await()`; task trong queue platform chưa chạy thì chưa tới latch. Sau khi submit hết, main mở latch và bắt đầu đo. Đây là so sánh **mô hình thực tế gồm cả thời gian chờ queue**, không phải đồng bộ tuyệt đối 120 request cùng khởi phát ở ba cấu hình.
8. **`Future.get(timeout)`:** main đợi hoàn tất và truyền exception từ task về main. Nếu task ném exception hoặc hết timeout, batch thất bại thay vì báo thời gian giả đẹp.
9. **Đóng lifecycle:** `ExecutorService` từ Java 21 là `AutoCloseable`; thoát `try` gọi `close()` và chờ các task kết thúc. `HttpClient` cũng cần được đóng khi chương trình không dùng nữa. Ví dụ còn dừng HTTP server trong `finally`.
10. **`System.nanoTime()`:** dùng để đo elapsed, không dùng `currentTimeMillis()` để tính độ trễ vì đồng hồ lịch có thể thay đổi. Số đo tổng được chuyển sang mili-giây.

### Giới hạn quan trọng của ví dụ

`Semaphore(REQUESTS)` ở `virtual-unbounded` không cắt bớt concurrency đối với đúng 120 task, nhưng vẫn là một semaphore; “unbounded” ở đây có nghĩa **không đặt giới hạn nhỏ hơn số task thí nghiệm**, không có nghĩa hệ thống cho phép số request vô hạn.

Timeout `HttpRequest.timeout(15s)` là giới hạn cho một HTTP request; `Future.get(30s)` giới hạn thời gian chờ của mỗi future tính từ lúc gọi `get`. Vì main duyệt future theo thứ tự, toàn batch không có deadline tổng 30 giây chặt chẽ; cần cơ chế deadline chung nếu đưa vào service thật.

Ví dụ không áp dụng warmup/benchmark chuyên sâu và không đo percentile của request. Nên chạy nhiều lần và phân biệt latency từng request với elapsed của batch.

## 5. Đọc kết quả theo throughput và latency

Cùng `N = 120` request, phép tính thông lượng quan sát của batch là:

\[
\text{Throughput (request/s)} =
\frac{N \times 1000}{\text{elapsedMs}}
\]

Chỉ tính từ **số request hoàn thành thành công** nếu có thất bại; tránh dùng `120` cho một batch mà 10 request lỗi.

**Latency** một request là thời gian từ trước lúc client cố gửi request tới lúc đã nhận đủ response, hoặc từ lúc task được submit nếu bạn muốn gồm cả thời gian chờ queue. Hai định nghĩa khác nhau; phải nêu rõ trong báo cáo.

**Batch elapsed** còn bao gồm thời gian xếp lịch, lập kết nối, server thực thi và client thu kết quả. Nếu các request đồng thời thực sự chờ I/O, batch elapsed có thể giảm mạnh dù **mỗi request vẫn đợi khoảng 100 ms phía server**.

| Phát hiện | Diễn giải có thể có | Cần kiểm thêm |
| --- | --- | --- |
| Virtual hoàn tất batch nhanh hơn platform pool nhỏ | Nhiều task đang chờ không cần giữ nhiều platform worker. | Số request đồng thời thực tế, network/server capacity và số lỗi. |
| Virtual-limited chậm hơn virtual-unbounded | Semaphore giới hạn tài nguyên; request phải chờ permit. | Có giảm overload/lỗi/tail latency của server không? |
| Virtual-unbounded chậm hoặc lỗi | Tài nguyên downstream/client/socket có thể quá tải. | Port, connection limits, rate limit, timeout, CPU, server saturation. |
| Ba trường hợp tương tự | Tải thấp hoặc bottleneck khác chi phối, chưa chứng minh hai mô hình tương đương mọi nơi. | Tăng quy mô có kiểm soát; đo thêm nhiều lần, warmup. |
| CPU 100% với cả hai | Công việc có thể CPU-bound hoặc hệ thống quá tải vì HTTP/JVM overhead. | Profile CPU, GC và thời gian chờ thực. |
| Nhiều virtual threads nhưng ít request in-flight | Giới hạn thực tế nằm ở semaphore, kết nối hoặc server. | Metrics pending/active, socket, server queue. |

Không nên báo “virtual threads nhanh hơn X lần” chỉ dựa trên một lần chạy. Nên đo median/p95 theo nhiều lượt, chạy đảo thứ tự các cấu hình để giảm sai lệch warmup/JIT/cache, theo dõi CPU và cảnh báo khi có bất kỳ HTTP failure nào.

## 6. Bài tập mở rộng: đo in-flight và p95 latency

Bài chính đang đo batch elapsed. Để kiểm chứng nơi nghẽn, thêm các biến:

- `AtomicInteger inFlight`: tăng ngay trước `client.send`, giảm ở `finally`.
- `AtomicInteger peakInFlight`: mỗi lần tăng, cập nhật max bằng `peakInFlight.accumulateAndGet(now, Math::max)`.
- Một thời điểm bắt đầu/hoàn thành cho mỗi request bằng `System.nanoTime()`; lưu latency sau khi request trả về hoặc ném lỗi.
- Đếm lỗi riêng theo HTTP status, timeout, connect error và interruption. Không nuốt exception rồi tính request như thành công.

Ví dụ **mã minh họa bên trong phần task** (giả định các field `inFlight` và `peakInFlight` đã khai báo và luồng đo đã thiết lập):

```java
int current = inFlight.incrementAndGet();
peakInFlight.accumulateAndGet(current, Math::max);

long started = System.nanoTime();
try {
    HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());
    long latencyNs = System.nanoTime() - started;
    // Ghi latencyNs và kết quả vào bộ thu thập thread-safe.
} finally {
    inFlight.decrementAndGet();
}
```

Đặt bộ đếm **sau khi lấy semaphore** để đo đúng HTTP in-flight, không tính task chỉ đang chờ permit. Trong code chạy thực, response body cần được dùng hoặc đóng phù hợp; mẫu dùng `BodyHandlers.ofString()` đọc toàn bộ body trước khi hoàn tất lời gọi.

Để tính p95/p99 từ nhiều mẫu, lưu chúng vào collection thread-safe hoặc array được ghi ở index riêng biệt cho từng task và chỉ tổng hợp sau `Future.get` của mọi task; sort rồi định nghĩa cách lấy percentile. Không tự tính p95 bằng giá trị `max` hay lấy trung bình.

**Phân tích nâng cao:** nếu các kết quả `success=120/120` nhưng `peakInFlight` thấp bất thường trong cấu hình virtual-unbounded, kiểm xem server, HttpClient hoặc môi trường có giới hạn kết nối. Nếu `peakInFlight` cao nhưng throughput không tăng, server có thể là bottleneck.

## 7. Virtual threads có thay thế backpressure không?

**Không.** Nếu một tác vụ virtual thread rẻ, chương trình vẫn phải giữ request object, response buffer, stack, context, socket hoặc connection cho nó. Tạo hàng triệu request chưa kiểm soát có thể làm quá tải cả client và server.

Phân biệt:

- **Thread scheduling:** chọn loại thread và executor.
- **Concurrency limit:** số request được phép thực thi đồng thời (ví dụ semaphore).
- **Arrival rate:** tốc độ nhận yêu cầu mới; có thể cần rate limiter hoặc queue có capacity.
- **Connection pool:** số kết nối tới service/database.
- **Timeout và cancellation:** cách kết thúc tác vụ không cần thiết hoặc chậm.
- **Backpressure:** cách signal cho producer khi consumer/downstream không còn đủ capacity.

Ví dụ `Semaphore(24)` giới hạn **số request đang vào đoạn được bảo vệ**, nhưng tất cả task vẫn đã được submit và có thể đang chờ permit. Nó **không giới hạn số task pending** hoặc số virtual threads đã tạo. Nếu nguồn yêu cầu phát sinh vô hạn, cần bounded queue, giới hạn admission, rate limiting hoặc từ chối có kiểm soát.

Đối với `Semaphore`, công bằng `new Semaphore(permits, true)` có thể giúp ưu tiên người chờ trước khi tranh permit, nhưng có thể làm giảm throughput. Không cần bật fairness để so sánh bản chất platform/virtual trong bài này.

## 8. Thời điểm virtual threads ít giúp ích

### 8.1. CPU-bound

Nếu task chủ yếu mã hóa, nén, tính hash nặng hoặc nhân ma trận, virtual threads không cung cấp thêm CPU. Sử dụng platform pool có kích thước gần số lõi hoặc mô hình task phù hợp thường dễ kiểm soát contention hơn.

Thử bài tập: thay request HTTP bằng phép tính CPU dài, đo CPU%, thời gian hoàn tất và độ tăng speedup khi thay đổi thread count. Không trộn phép đo CPU vào phép so sánh I/O ban đầu rồi khẳng định do virtual threads.

### 8.2. Thư viện blocking không hợp tác hoặc native call

Một số thao tác native/foreign hoặc cách dùng thư viện có thể giữ carrier lâu, làm giảm khả năng mở rộng virtual threads. Phải đo bằng profiler/JFR trong runtime cụ thể, không phỏng đoán từ tên phương thức.

### 8.3. Pinning phụ thuộc phiên bản JDK

Trên **JDK 21–23**, blocking khi một virtual thread đang ở trong khối `synchronized` có thể **pin** virtual thread vào carrier, khiến carrier không nhường được cho task khác trong khoảng chờ. Trên **JDK 24+**, JEP 491 đã thay đổi việc đồng bộ monitor để các virtual thread đang chờ trong phần `synchronized` có thể nhường carrier, loại bỏ trường hợp pinning do monitor theo cơ chế cũ. Các nguyên nhân pinning còn lại, như native/foreign frames, vẫn cần theo dõi.

Ví dụ minh họa vấn đề dành cho JDK 21–23:

```java
synchronized (sharedLock) {
    // Tránh giữ monitor trong lúc gọi I/O chậm;
    // trên JDK 21–23 còn có thể pin carrier thread.
    blockingHttpCall();
}
```

Đây **không phải chương trình độc lập**. Ngoài chuyện pinning, giữ monitor trong lúc chờ I/O cũng gây contention giữa các thread và có thể tạo deadlock, kể cả ở JDK mới. Vì vậy **đừng** đổi tất cả `synchronized` thành `ReentrantLock` một cách máy móc; trước tiên xác định phiên bản JDK, yêu cầu đúng/sai và điểm giữ lock thực sự gây nghẽn.

Có thể xem JFR events và thread dump phù hợp phiên bản JDK. `jdk.VirtualThreadPinned` là một event hữu ích khi điều kiện pinning được ghi nhận, nhưng ngưỡng/thời gian phát event và nội dung stack tùy JDK/cấu hình. Với JDK 21–23, tùy JVM có thể thử `-Djdk.tracePinnedThreads=full` để tìm những call stack gây pinning.

## 9. ThreadLocal, interruption và tài nguyên

### ThreadLocal

Platform thread pool thường tái sử dụng cùng các worker qua nhiều task, nên một `ThreadLocal` giữ cache/connection theo thread có thể tái sử dụng và cũng có nguy cơ lưu trạng thái nhầm sang task sau nếu quên `remove()`.

Virtual thread per task tạo thread mới cho từng task; `ThreadLocal` theo thread có thể dẫn tới chi phí tạo state/cache lớn nếu mỗi task đều mở tài nguyên riêng. Không dùng ThreadLocal để lén sở hữu connection cho hàng trăm nghìn task nếu không kiểm soát vòng đời. Với các tài nguyên đắt, ưu tiên resource ownership và pool/limiter ở tầng tài nguyên.

### Timeout và interruption

`Future.cancel(true)` chỉ yêu cầu interrupt task. Code dùng `HttpClient.send` có thể phản ứng bằng `InterruptedException`; trong Java, interrupt còn có thể ảnh hưởng giao thức hủy request và kết nối, nhưng không có cam kết rằng tác dụng phụ phía server đã dừng. Nếu có deadline thật, hãy phối hợp timeout ở request, thời hạn tổng và chính sách xử lý HTTP response đến muộn.

Nếu bắt `InterruptedException` mà không ném lại:

```java
try {
    runBlockingOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Dừng công việc hoặc trả trạng thái hủy cho caller.
}
```

Đây chỉ là khung minh họa trong một method đã khai báo `runBlockingOperation()`; không phải Java class độc lập. Đừng âm thầm nuốt interrupt rồi tiếp tục gọi I/O vô hạn.

### Đóng executor và service

`Executors.newVirtualThreadPerTaskExecutor()` tạo executor mới, mỗi task một virtual thread. Khi hết phiên xử lý, đóng executor được sở hữu; `close()` theo Java 21 đợi các task hoàn tất. Nếu tác vụ có thể chờ vô hạn, cần timeout/cancellation riêng, không trông chờ `close()` tự cho deadline.

Trong ví dụ có cả `HttpServer` và `HttpClient`. Server dùng executor riêng để tránh trộn nguồn lực client; tài nguyên được đóng tại nơi tạo. Trong hệ thống thật, tránh tạo `HttpClient` mới cho từng request vì có thể làm tăng overhead kết nối; tái sử dụng client phù hợp cho nhiều request.

## 10. Cách tiến hành và chấm kết quả bài tập

Thực hiện ít nhất bốn lượt đo cho mỗi cấu hình, giữ lại số liệu, điều kiện và **mọi lỗi**. Một bảng kết quả nên có cấu trúc:

| Mode | JDK | N requests | Limit in-flight | Success | Median elapsed ms | CPU% | Ghi chú |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| platform-12 | JDK bạn dùng | 120 | 12 | Ghi thực tế | Ghi thực tế | Ghi thực tế | OS thread pool cố định |
| virtual-unbounded | Cùng JDK | 120 | 120 | Ghi thực tế | Ghi thực tế | Ghi thực tế | Virtual task per thread |
| virtual-limited-24 | Cùng JDK | 120 | 24 | Ghi thực tế | Ghi thực tế | Ghi thực tế | Giới hạn downstream |

Không đưa số liệu thời gian giả vào báo cáo. Khi chạy lần đầu, có thể chịu JIT warmup, DNS/socket setup, cache và lazy initialization. Nếu muốn kết luận hiệu năng, làm thêm warmup, đảo thứ tự các mode giữa các vòng, giữ server capacity ổn định, chạy đủ thời gian và kèm phân phối latency.

**Tiêu chí hoàn thành:**

1. Chạy bằng **JDK 21+** và ghi rõ lệnh `javac`/`java`.
2. Mọi cấu hình trả **120/120** request hợp lệ trong điều kiện bình thường; case thất bại cần được phân tích, không được bỏ qua.
3. Giải thích vì sao platform pool 12 phải xếp task chờ và virtual thread per task không bị giới hạn trực tiếp bởi 12 platform workers.
4. Giải thích vì sao virtual-limited-24 có thể tạo thời gian batch dài hơn virtual-unbounded nhưng bảo vệ dịch vụ phụ thuộc.
5. Chỉ rõ kết luận nào áp dụng cho I/O-bound, kết luận nào không được suy sang CPU-bound.
6. Phân biệt số đo batch elapsed với latency từng request, và biết rằng “virtual thread rẻ” không xóa giới hạn tài nguyên.

## 11. Bài tập nâng cao

**Bài A — Thay đổi tải.** Đổi `REQUESTS` lần lượt thành `24`, `120` và `600`; giữ thời gian server sleep cố định. Quan sát mức tải nào tạo khác biệt giữa các mô hình. Với tải lớn, tăng HTTP request timeout nếu có lý do nhưng tránh so sánh khi một mode thất bại và mode kia thành công mà không ghi rõ.

**Bài B — Dịch vụ có capacity giới hạn.** Tạo semaphore `Semaphore(20)` bên phía HTTP handler để mô phỏng backend chỉ xử lý tối đa 20 request cùng lúc. Các request quá nhiều sẽ xếp hàng. So sánh tác động `virtual-limited-24`, `virtual-unbounded` và giới hạn bằng 20; xem throughput, lỗi và tail latency. Đừng nhầm số thread xử lý HTTP với capacity backend.

**Bài C — Fan-out I/O.** Mỗi logical request cần đồng thời lấy dữ liệu từ ba endpoint độc lập. So sánh một platform pool cố định với virtual threads, chờ tất cả future thành công rồi tổng hợp. Nếu một nhánh timeout, hủy các nhánh còn lại khi thích hợp và bảo đảm không để executor/task chạy vô hạn.

**Bài D — Tác vụ CPU.** Thay lời gọi HTTP bằng thuật toán tính toán lặp có kết quả kiểm chứng được, đo với số worker gần số lõi CPU và virtual executor. Giải thích vì sao kết quả không giống I/O-bound.

**Bài E — Quan sát runtime.** Thu JFR hoặc thread dump trong lúc chương trình đang chạy; phân tích platform worker đang blocking và virtual thread đang parked/unmounted. Nếu chạy trên JDK 21–23, thêm một biến thể cố ý giữ monitor trong lúc chờ để quan sát pinning. Trên JDK 24+, so sánh khác biệt theo JEP 491.

## 12. Các sai lầm thường gặp

1. **Dùng Java 17 rồi tìm API virtual threads:** cần JDK 21+ để dùng ổn định `newVirtualThreadPerTaskExecutor`.
2. **So sánh task khác nhau:** một mode làm nhiều HTTP request hơn, timeout khác hoặc server khác sẽ khiến số đo vô nghĩa.
3. **Cho rằng virtual threads tăng tốc từng HTTP request:** lợi thế chính là mở rộng concurrency của các tác vụ đang chờ, không đổi thời gian mạng hoặc server cho một request.
4. **Dùng pool virtual thread cố định:** virtual threads nên gắn với task; dùng semaphore/admission control để giới hạn downstream thay vì tạo pool virtual worker như platform threads.
5. **Không đóng resource:** để server, executor, HTTP client hoặc task chạy sau test sẽ gây rò rỉ hoặc làm nhiễu lượt đo.
6. **Chỉ đo số task submit:** 120 task đã submit không đồng nghĩa 120 HTTP thành công. Phải kiểm status/body và tất cả Future.
7. **Bỏ qua lỗi/timeout:** số liệu nhanh do task lỗi sớm không phải throughput tốt hơn. Cần báo lỗi và ngừng kết luận khi không tương đồng.
8. **Không warmup hoặc chỉ đo một lần:** JIT/connection setup/GC khiến kết quả thiếu ổn định.
9. **Tạo ồ ạt virtual threads vì “gần như miễn phí”:** socket, buffer, downstream, memory và rate limit vẫn hữu hạn.
10. **Nhầm pinning với locking nói chung:** monitor-related pinning thay đổi từ JDK 24; contention và lock ownership vẫn là vấn đề độc lập.
11. **Bỏ qua tính đúng đắn khi đổi kiến trúc:** virtual threads có cùng nguy cơ race/deadlock nếu truy cập shared state sai.
12. **Lạm dụng ThreadLocal cache:** mỗi virtual task có thread riêng, khó có lợi từ cache gắn theo thread và có thể tăng cấp phát.
13. **Dùng `Thread.sleep` làm kết luận duy nhất về network:** sleep có ích để minh họa waiting, nhưng cần socket I/O và hạ tầng gần thực tế để đánh giá production.
14. **Thiếu bản đồ ownership:** đóng shared executor/client mà thread khác còn dùng có thể gây lỗi; xác định ai tạo và ai đóng.

## 13. Kết luận

**Platform threads** thích hợp khi số lượng tác vụ đồng thời vừa phải hoặc phần lớn công việc CPU-bound; pool cố định giúp giới hạn trực tiếp số OS threads/worker. **Virtual threads** cho phép viết code blocking I/O đồng bộ theo mô hình thread-per-task mà không cần giữ một OS thread riêng cho mỗi request đang chờ; chúng hữu ích khi hệ thống phải phục vụ nhiều task I/O-bound độc lập cùng lúc.

Bài tập chỉ hoàn thành khi bạn vừa đo thời gian, vừa chứng minh **kết quả HTTP đúng**, giải thích cơ chế chờ và nhận diện giới hạn của server/downstream. Việc chọn mô hình cuối cùng phải dựa trên workload và số liệu, thay vì suy từ số lượng thread.

### Tài liệu Java chính thức

- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Oracle Java 21 — Executors API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Oracle Java 21 — HttpClient API](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java 21 — HttpServer API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24)](https://openjdk.org/jeps/491)
- [Oracle Java 24 — Significant Changes](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html)
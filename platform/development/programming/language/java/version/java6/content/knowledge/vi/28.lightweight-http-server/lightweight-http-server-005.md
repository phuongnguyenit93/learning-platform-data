# Executor và xử lý yêu cầu đồng thời

## 1. Tại sao HTTP server nhỏ vẫn cần chiến lược đồng thời?

`com.sun.net.httpserver.HttpServer` là HTTP server gọn đi kèm JDK, thích hợp cho **embedded endpoints, công cụ nội bộ, phát triển, kiểm thử, health/metrics endpoints hoặc ứng dụng HTTP nhỏ** khi bạn kiểm soát đủ yêu cầu bảo mật/vận hành. API này xuất hiện từ **Java 6**, nằm trong module **`jdk.httpserver`** ở Java hiện đại và vẫn được tài liệu **Java SE 26** hỗ trợ.

Khi một yêu cầu đến, `HttpServer` chọn một `HttpHandler` theo URL context và gọi `handle(HttpExchange)`. Nếu handler chờ database, file, network hoặc xử lý CPU lâu, các yêu cầu khác có thể bị ảnh hưởng **nếu việc dispatch/điều phối threads không phù hợp**.

Khả năng xử lý nhiều yêu cầu đồng thời nằm ở sự phối hợp của:

1. **`HttpServer.setExecutor(Executor)`:** đối tượng nào thực thi các tác vụ HTTP handler.
2. **`Executor` / `ThreadPoolExecutor`:** bao nhiêu task được chạy cùng lúc và bao nhiêu task có thể nằm đợi.
3. **Giới hạn nghiệp vụ/backpressure:** ví dụ `Semaphore` chỉ cho tối đa hai thao tác đang sử dụng downstream resource.
4. **Shared-state correctness:** các handler có thể chạy đồng thời; phải dùng `AtomicInteger`, thread-safe collections, locking hoặc thiết kế state riêng cho mỗi request.
5. **Timeout, overload và shutdown:** yêu cầu phải kết thúc, resources phải được giải phóng, không để hệ thống tồn tại vô hạn khi client ngừng chờ.

~~~text
Client A ------\
Client B -------+--> TCP accept / HttpServer context dispatch
Client C ------/                      |
                                     v
                           Executor.execute(task)
                                     |
                     +---------------+---------------+
                     |               |               |
                  worker 1        worker 2       worker 3
                     |               |               |
                  HttpHandler     HttpHandler     HttpHandler
                     |               |               |
                     +---------- Semaphore ----------+
                                     |
                          Downstream/DB/API (bounded)
                                     |
                                HttpExchange
                                     |
                            HTTP response/close
~~~

**Điểm mấu chốt:** tạo nhiều threads giúp **concurrency**, không tự bảo đảm **safety, throughput hoặc latency**. Thêm threads không làm CPU-bound computation nhanh hơn số CPU cores; threads không giới hạn còn làm quá tải connection pool, filesystem, database và memory.

### Kết quả học tập

Sau bài này, bạn sẽ biết:

- Cấu hình `server.setExecutor(executor)` **trước** `server.start()` và hiểu mặc định nếu không cấu hình.
- Phân biệt `Executor`, `ExecutorService` và `ThreadPoolExecutor`; tách **pool size**, **executor queue**, **TCP backlog** và **business concurrency limit**.
- Sử dụng bounded `ArrayBlockingQueue` và `Semaphore.tryAcquire()`, trả **HTTP 503** có chủ đích khi downstream bận.
- Thiết kế handler an toàn trước request đồng thời, không chia sẻ `HttpExchange` giữa threads tùy tiện và không dùng data race.
- Đóng exchange đúng cách, gửi HTTP body theo **số byte UTF-8** và kiểm soát HTTP methods/path.
- Kiểm thử bằng hai yêu cầu HTTP thực sự **đang overlap** với `CountDownLatch`, không đoán qua `Thread.sleep`.
- Dừng server, shutdown executor và chờ worker kết thúc theo deadline.
- Biết lựa chọn `Executors.newVirtualThreadPerTaskExecutor()` ở **Java 21+** và `Semaphore` giới hạn tài nguyên; không pool virtual threads.
- Phân tích 404/405/503, rejection khi executor bão hòa, đo metrics và những giới hạn production.
- Chạy hai ví dụ đã kiểm thử: **Java 17+ với bounded platform pool**, và **Java 21+ với virtual threads**.

## 2. API còn áp dụng và module jdk.httpserver

| API | Chức năng |
| --- | --- |
| `com.sun.net.httpserver.HttpServer` | Bind port, đăng ký contexts, set executor, start/stop |
| `com.sun.net.httpserver.HttpContext` | Ánh xạ URI path prefix tới handler |
| `com.sun.net.httpserver.HttpHandler` | Interface xử lý một yêu cầu bằng `handle(HttpExchange)` |
| `com.sun.net.httpserver.HttpExchange` | Request method/path/headers/body, response headers/body, close |
| `com.sun.net.httpserver.Filter` | Pre-/post-processing request, tùy requirements |
| `java.util.concurrent.Executor` | Contract `execute(Runnable)` |
| `java.util.concurrent.ExecutorService` | Thêm lifecycle: `shutdown()`, `awaitTermination()`, futures |
| `java.util.concurrent.ThreadPoolExecutor` | Pool có cấu hình số threads/queue/rejection |
| `java.util.concurrent.ArrayBlockingQueue` | Hàng đợi tasks có capacity cố định |
| `java.util.concurrent.Semaphore` | Giới hạn số thao tác cùng truy cập một resource |
| `java.util.concurrent.atomic.AtomicInteger` | Counters an toàn giữa threads |
| `java.util.concurrent.CountDownLatch` | Phối hợp test hai requests overlap mà không sleep ngẫu nhiên |
| `java.net.http.HttpClient` | HTTP client hiện đại để viết integration test |
| `Executors.newVirtualThreadPerTaskExecutor()` | Executor cho mỗi task một virtual thread, **từ Java 21** |

`jdk.httpserver` không phải module `java.base` hoặc `java.net.http`. Trong chương trình classpath/demo, dùng flag tường minh:

~~~bash
javac --release 17 --add-modules jdk.httpserver HttpServerExecutorDemo.java
java --add-modules jdk.httpserver HttpServerExecutorDemo
~~~

Nếu tạo **named Java module**, khai báo:

~~~java
module demo.http {
    requires jdk.httpserver;
    requires java.net.http;
}
~~~

Đây là **module-info.java minh họa**, không phải file có thể chạy độc lập. `java.net.http` cần cho HTTP client trong fixture; khi chỉ viết server không dùng HttpClient thì không bắt buộc `requires java.net.http`.

### 2.1. API không phải đã lỗi thời vì có tên com.sun.*

Không đánh đồng mọi package bắt đầu bằng `com.sun` với API bị bỏ hoặc không công khai. `com.sun.net.httpserver` được **export công khai bởi module `jdk.httpserver`**, có Javadoc Java SE 26, hỗ trợ build embedded server nhỏ. Tuy vậy đây là **JDK-specific HTTP server API** thay vì một full-featured application server/framework. Nó không cung cấp toàn bộ routing, auth, TLS, observability, resource governance hoặc deployment features của các framework HTTP lớn.

### 2.2. Phân biệt jwebserver/SimpleFileServer

`SimpleFileServer` / `jwebserver` là tiện ích HTTP-only dành chủ yếu cho **development, testing và debugging**, không phải một substitute cho server production public Internet. Bài này sử dụng **`HttpServer` tùy biến với `HttpHandler`**, không dùng jwebserver để phục vụ thư mục tùy ý.

## 3. Vòng đời một request và vai trò Executor

~~~text
server = HttpServer.create(...)
server.createContext("/work", handler)
server.setExecutor(executor)    <-- TRƯỚC start()
server.start()
            |
            v
Client request
            |
            v
Longest matching context prefix
            |
            v
Executor receives an HTTP handling task
            |
            v
HttpHandler.handle(exchange)
            |
            +-- examine request path/method/headers/body
            +-- do bounded business work
            +-- choose status, response headers
            +-- sendResponseHeaders()
            +-- write response body
            +-- close HttpExchange
            |
            v
Worker ready for another task
~~~

### 3.1. setExecutor trước start là hợp đồng bắt buộc

`HttpServer.setExecutor(Executor)` phải được gọi **trước `HttpServer.start()`**. Nếu gọi sau start, Javadoc quy định **`IllegalStateException`**.

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8080), 64);
server.createContext("/status", exchange -> {
    // handle request...
});
server.setExecutor(executor);
server.start();
~~~

Đây là **đoạn trích**, `executor` phải được khởi tạo và caller phải quản lý shutdown. Thứ tự nên là: **create/bind → createContext → setExecutor → start**.

### 3.2. Mặc định không có custom Executor là gì?

Theo Javadoc `HttpServer.setExecutor`, nếu không đặt `Executor` hoặc đặt `null` trước start, default implementation sử dụng **thread được tạo bởi `start()`** để xử lý request tasks. Do đó **không được giả định** server mặc định đã có pool nhiều worker threads. Một handler blocking có thể khiến request khác chờ.

Tuy vậy, kết luận chính xác phải từ **contract/provider đang triển khai**. Đây là lý do bài minh họa **luôn chủ động đặt executor** khi cần xử lý đồng thời.

### 3.3. getExecutor có phản ánh số worker không?

`server.getExecutor()` trả custom executor được đặt hoặc `null` nếu không đặt. Nó không phải API lấy “số requests đang chạy” hoặc “tổng TCP connections”. Muốn metrics, nếu dùng `ThreadPoolExecutor` có thể đọc `getActiveCount()`, `getQueue().size()`, `getCompletedTaskCount()`; đây chỉ là snapshots/approximations, không thay request-level tracing.

## 4. Ba loại hàng đợi và giới hạn rất dễ bị nhầm

Giả sử:

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8080), 64);
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        4, 4, 0, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(32));
Semaphore databasePermits = new Semaphore(2);
~~~

Đây là **đoạn cấu hình minh họa**, chưa import/đóng resources. Các con số **64, 32, 4, 2** nói về **bốn lớp khác nhau**:

| Cấu hình | Giới hạn gì? | Không bảo đảm gì? |
| --- | --- | --- |
| `backlog=64` | Số **TCP connections chưa accept** có thể được OS xếp hàng khi đợi accept, phụ thuộc hệ thống | **Không** phải tối đa 64 HTTP requests, tasks, threads hoặc clients đang kết nối |
| `pool core=max=4` | Tối đa bốn **platform worker threads** của executor này | Không bảo đảm chỉ bốn sockets hoặc hai database operations |
| `ArrayBlockingQueue<>(32)` | Tối đa 32 **tasks chờ trong executor queue** | Không phải HTTP 503 tự động, không giới hạn tổng kết nối hoặc external work |
| `new Semaphore(2)` | Tối đa hai **đơn vị công việc nằm trong vùng protected** đồng thời | Không giới hạn số request tasks mà HTTP server đã dispatch |

TCP backlog được kernel/tầng TCP quản lý. HTTP keep-alive có thể đưa **nhiều requests tuần tự** trên một connection. Executor queue chứa tasks được submit. Semaphore trong handler mới kiểm soát **downstream operation**, không kiểm soát số connections đã được accept.

### 4.1. Backlog không phải backpressure tầng nghiệp vụ

Nếu backlog đầy, TCP stack có thể từ chối/bỏ qua connections mới. Nó **không tạo HTTP 429 hoặc 503** theo ý muốn. Dùng backlog để điều chỉnh network accept pressure; để quyết định response API khi quá tải, phải có cơ chế admission control tại HTTP/application layer.

### 4.2. Executor queue đầy sẽ ra sao?

`ThreadPoolExecutor` nhận một `RejectedExecutionHandler`. Với `AbortPolicy`, executor có thể ném `RejectedExecutionException` khi queue và worker đã đầy. Nhưng vì `HttpServer` sở hữu lời gọi `Executor.execute(...)`, **không được suy tự động rằng client sẽ nhận HTTP 503**. Ứng xử cụ thể phụ thuộc JDK/provider/đường xử lý lỗi; connection có thể lỗi hoặc bị đóng.

Muốn có **503 rõ ràng**, handler phải **được dispatch thành công** rồi chủ động trả 503 khi admission check thất bại, như `Semaphore.tryAcquire()` trong chương trình mục 8. Đồng thời cần giới hạn queue/connection ở tầng trước để tránh bão hòa trước khi handler có cơ hội trả lời.

### 4.3. FixedThreadPool có một bẫy

`Executors.newFixedThreadPool(n)` có **số worker threads cố định** nhưng sử dụng **unbounded work queue** của cấu hình mặc định. Nếu requests đến nhanh hơn xử lý, tasks có thể tích lũy và gây latency/heap growth, dù pool chỉ có `n` threads.

Nếu bài toán cần kiểm soát queue, dùng `ThreadPoolExecutor` với `ArrayBlockingQueue` hoặc hàng đợi có capacity rõ. Không chọn hàng đợi quá lớn chỉ để tránh rejection; độ trễ p95/p99 có thể tăng trước khi bị cảnh báo.

### 4.4. Không dùng CallerRunsPolicy tùy tiện

`ThreadPoolExecutor.CallerRunsPolicy` khiến thread gọi `execute` chạy task bị từ chối (khi executor chưa shutdown). Khi caller là thread đang nhận/điều phối HTTP requests, nó có thể bị chặn bởi handler chậm. Điều đó có thể là một dạng backpressure, nhưng **không nên dùng nếu chưa phân tích dispatch model và đo latency**. Với server production, overload strategy phải xét từ socket đến application và downstream.

## 5. Thiết kế ThreadPoolExecutor có giới hạn

Mẫu cấu hình:

~~~java
AtomicInteger names = new AtomicInteger();
ThreadFactory factory = task ->
        new Thread(task, "http-worker-" + names.incrementAndGet());

ThreadPoolExecutor executor = new ThreadPoolExecutor(
        4, 4,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(32),
        factory,
        new ThreadPoolExecutor.AbortPolicy());
~~~

Đây là **đoạn trích** với imports từ `java.util.concurrent.*` và `java.util.concurrent.atomic.AtomicInteger`. Một pool **4 threads + queue 32** là ví dụ minh họa, **không** phải cấu hình tối ưu cho mọi hệ thống. Nếu handler chờ I/O nhiều, có thể cần thêm concurrency, nhưng giới hạn connections của DB, memory per request, HTTP client pools và CPU vẫn quyết định.

### 5.1. Định cỡ pool phải theo workload

- **CPU-bound**: số workers quá cao có thể gây context switching; xác định song song thực tế theo CPU quota/cgroup và workload.
- **I/O-bound**: có thể có nhiều tasks đang chờ, nhưng phải giới hạn downstream connections, request deadlines và memory.
- **Mixed workload**: tách pool cho tác vụ nền/CPU dài khỏi HTTP dispatch để tránh starvation.
- **Blocking DB calls**: nếu DB connection pool có 10 connections, HTTP pool 500 threads có thể chỉ tạo 490 threads đang chờ.
- **Java 21+ virtual threads** giúp concurrency cho blocking I/O, **không làm SQL/query chạy nhanh hơn** và không loại giới hạn resource.

Không lấy một số threads “chuẩn” từ Internet rồi áp dụng cứng; đo real load.

### 5.2. ThreadFactory và names

Đặt tên như `http-worker-1` giúp trace/thread dumps. Production còn có thể đặt uncaught exception handler, theo dõi thread creation, nhưng **không đặt daemon tùy tiện** để né shutdown; hãy có lifecycle rõ. Đừng log raw request body hoặc token vào tên thread/MDC.

### 5.3. Bounded queue không thay bounded request body

Hàng đợi executor có 32 tasks vẫn có thể nhận mỗi request body vài GB nếu handler tự `readAllBytes()`. Cần giới hạn total body bytes, stream xử lý từng chunk, content type/length validation và timeout. Không biến queue limit thành cam kết memory limit.

## 6. HttpHandler chạy đồng thời: shared state phải đúng

`HttpHandler.handle(HttpExchange)` có thể được gọi nhiều lần đồng thời với **cùng instance handler**. Đừng nghĩ vì một `HttpHandler` được đăng ký một lần thì mọi request được xử lý tuần tự.

### 6.1. Counter không an toàn

~~~java
// Phản ví dụ: nhiều threads cùng tăng biến thường sẽ có lost updates.
int requests;
void onRequest() {
    requests++; // read-modify-write không atomic
}
~~~

Đây là đoạn minh họa, không phải file độc lập. Dùng:

~~~java
AtomicInteger requests = new AtomicInteger();
void onRequest() {
    requests.incrementAndGet();
}
~~~

Khi tần suất counters rất cao, `LongAdder` có thể hữu ích cho metrics mang tính tổng hợp, nhưng nó **không phải** công cụ thay thế mọi atomic state transition.

### 6.2. Per-request state khác shared state

| Dữ liệu | Nên để ở đâu? |
| --- | --- |
| URI, method, request body, response body | Trong chính `HttpExchange`/local variables của request |
| User identity/authorization result | Per-exchange context, không static mutable |
| Count tổng requests | `AtomicLong`/`LongAdder` hoặc metrics service |
| Mutable shared cache | `ConcurrentHashMap` hoặc cache đã kiểm thử |
| Downstream concurrency slots | `Semaphore` |
| Database connection | Lấy/đóng theo request/transaction, không share JDBC Connection tùy tiện |
| Request deadline/cancellation | Per-request state với policy rõ |
| Test signaling | `CountDownLatch` (chỉ dành cho test ở ví dụ) |

Đừng giữ `HttpExchange` trong static field hoặc gửi exchange sang background task rồi trả response trước khi task hoàn tất, trừ khi đã thiết kế/làm chủ lifecycle/concurrency của HttpExchange; API mặc định hướng tới handler nhận một exchange, xử lý rồi kết thúc response.

### 6.3. Exceptions không tự trở thành response hữu ích

Nếu handler ném unchecked exception mà không phát headers/đóng exchange đúng cách, client có thể thấy connection failure/timeout. Hãy bắt lỗi đúng phạm vi, mapping thành HTTP status khi **headers chưa gửi**, log đã lọc và đóng resources trong `finally`/try-with-resources. Nếu response đã bắt đầu streaming, không thể “đổi 200 thành 500” sau khi đã gửi headers; khi đó cần kết thúc/abort theo policy và ghi telemetry.

### 6.4. Đừng đồng bộ khóa toàn handler nếu không cần

~~~java
// Phản ví dụ về giảm concurrency không cần thiết.
synchronized void processEntireRequest(HttpExchange exchange) {
    // Chờ database + gửi network response trong lock chung...
}
~~~

Nếu mọi request dùng cùng monitor lock để chờ I/O, pool dù có 20 workers cũng có thể **chỉ xử lý thực tế một request một lúc**. Khóa phạm vi shared mutation tối thiểu, dùng thread-safe data structures, tránh giữ lock khi gửi response hoặc chờ external service.

## 7. Admission control: Semaphore và HTTP 503 chủ động

Mục tiêu không chỉ là chạy nhiều threads. Ví dụ một downstream API chỉ chịu được **2 operations cùng lúc**; handler có thể gọi `Semaphore.tryAcquire()`:

~~~java
if (!capacity.tryAcquire()) {
    reply(exchange, 503, "busy");
    return;
}
try {
    // Xử lý business operation trong vùng có tối đa 2 permits.
} finally {
    capacity.release();
}
~~~

Đây là **đoạn trích** của một handler, không chạy độc lập. Lưu ý:

- `tryAcquire()` là non-blocking: khi hết permits, trả 503 **ngay trong handler**, không xếp request vào một hàng đợi thứ hai.
- `release()` trong `finally` bảo đảm permit được trả khi thành công/thất bại sau acquire.
- Không `release()` nếu acquire thất bại.
- Nếu yêu cầu chờ thay vì reject, có thể dùng `tryAcquire(timeout, unit)`, nhưng phải tính **request deadline** và interruption.
- `Semaphore` giới hạn **business operations**, không giới hạn số TCP connections hoặc số HTTP tasks đã vào executor.
- Với HTTP 503 thường cân nhắc `Retry-After` khi có thời điểm quay lại thực sự phù hợp; tránh bảo khách retry ngay lập tức gây retry storm.

### 7.1. 503 khác 429

- **503 Service Unavailable**: service tạm không có năng lực xử lý vì overload/maintenance.
- **429 Too Many Requests**: client/tenant vượt **rate limit/quota** do policy đặt ra.

Trong chương trình, `Semaphore` thể hiện **server capacity**, nên trả 503. Một limiter theo tenant/key có thể trả 429 với chính sách cụ thể. Không dùng chúng thay thế cho nhau mà không định nghĩa contract.

### 7.2. Backpressure đa tầng

Một chiến lược an toàn phối hợp:

1. Giới hạn **số active TCP connections**/timeouts ở server hoặc reverse proxy.
2. Bounded executor queue, rejection policy có thể quan sát.
3. Bounded in-flight work (Semaphore) trên DB, external services, CPU-heavy routines.
4. Deadline/timeouts cho client và downstream.
5. Request body/response body size limits.
6. HTTP 503/429 rõ, có circuit breaker và load shedding khi hệ thống quá tải.
7. Retry của clients có **bounded backoff + jitter**, đặc biệt với operations có side effects cần idempotency.
8. Metrics đầy đủ: in-flight, queue depth, 503, 429, timeouts, request duration, active threads, saturation.

## 8. Chương trình Java 17+ hoàn chỉnh: server đồng thời và kiểm thử thật

`HttpServerExecutorDemo.java` sử dụng **JDK built-in HttpServer** trên `127.0.0.1` và port ngẫu nhiên (`0`), không mở public interface:

- Custom `ThreadPoolExecutor`: `core=4`, `max=4`, `ArrayBlockingQueue<>(32)`, `AbortPolicy`.
- `server.setExecutor(executor)` trước `server.start()`.
- Chỉ chấp nhận `GET /work`; `POST /work` trả 405 và header `Allow: GET`; không có context trả 404.
- `Semaphore(2)` cho phép **hai requests thật** được xử lý cùng lúc.
- `CountDownLatch` trong test giữ hai requests ở handler cho tới khi main thread quan sát chúng overlap.
- Một request thứ ba khi hai permits đang bận được handler **chủ động** trả 503.
- `AtomicInteger` ghi nhận active/peak và accepted/busy requests.
- `HttpClient.sendAsync` gửi hai requests concurrently, không phụ thuộc `Thread.sleep`.
- Sau test, `server.stop(1)`, `executor.shutdown()` và `awaitTermination`.

**Lưu ý:** fixture dùng latch để mô phỏng “xử lý đang chờ” và kiểm thử concurrency, không phải business handler production. Nó không tạo một service lâu dài; server dừng ngay sau main.

### 8.1. File HttpServerExecutorDemo.java (runnable)

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class HttpServerExecutorDemo {
    static void reply(HttpExchange exchange, int status, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    static final class WorkHandler implements HttpHandler {
        final Semaphore capacity = new Semaphore(2);
        final CountDownLatch ready = new CountDownLatch(2);
        final CountDownLatch release = new CountDownLatch(1);
        final AtomicInteger active = new AtomicInteger();
        final AtomicInteger peak = new AtomicInteger();
        final AtomicInteger admitted = new AtomicInteger();
        final AtomicInteger busy = new AtomicInteger();

        @Override
        public void handle(HttpExchange exchange) throws IOException {
            try (exchange) {
                if (!"/work".equals(exchange.getRequestURI().getPath())) {
                    reply(exchange, 404, "not-found");
                    return;
                }
                if (!"GET".equals(exchange.getRequestMethod())) {
                    exchange.getResponseHeaders().set("Allow", "GET");
                    reply(exchange, 405, "method-not-allowed");
                    return;
                }
                if (!capacity.tryAcquire()) {
                    busy.incrementAndGet();
                    reply(exchange, 503, "busy");
                    return;
                }
                int now = active.incrementAndGet();
                peak.accumulateAndGet(now, Math::max);
                admitted.incrementAndGet();
                ready.countDown();
                try {
                    if (!release.await(5, TimeUnit.SECONDS)) {
                        reply(exchange, 504, "deadline-exceeded");
                        return;
                    }
                    reply(exchange, 200, "ok");
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    reply(exchange, 503, "interrupted");
                } finally {
                    active.decrementAndGet();
                    capacity.release();
                }
            }
        }
    }

    static void check(boolean condition, String reason) {
        if (!condition) throw new AssertionError(reason);
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger threadIds = new AtomicInteger();
        ThreadFactory namedThreads = task -> {
            Thread thread = new Thread(
                    task, "http-worker-" + threadIds.incrementAndGet());
            thread.setDaemon(false);
            return thread;
        };
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                4, 4, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(32),
                namedThreads, new ThreadPoolExecutor.AbortPolicy());
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 64);
        WorkHandler handler = new WorkHandler();
        server.createContext("/work", handler);
        server.setExecutor(executor);
        server.start();
        try {
            URI uri = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/work");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();
            HttpRequest get = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5)).GET().build();

            CompletableFuture<HttpResponse<String>> first = client.sendAsync(
                    get, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            CompletableFuture<HttpResponse<String>> second = client.sendAsync(
                    get, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

            check(handler.ready.await(5, TimeUnit.SECONDS),
                    "two requests did not overlap");
            HttpResponse<String> third = client.send(
                    get, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            check(third.statusCode() == 503 && third.body().equals("busy"),
                    "expected explicit application overload response");

            handler.release.countDown();
            HttpResponse<String> a = first.get(5, TimeUnit.SECONDS);
            HttpResponse<String> b = second.get(5, TimeUnit.SECONDS);
            check(a.statusCode() == 200 && b.statusCode() == 200,
                    "both admitted requests must succeed");
            check(a.body().equals("ok") && b.body().equals("ok"),
                    "unexpected response content");
            check(handler.peak.get() == 2 && handler.active.get() == 0,
                    "wrong concurrency");
            check(handler.admitted.get() == 2 && handler.busy.get() == 1,
                    "wrong accepted/rejected counts");

            HttpRequest post = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.noBody()).build();
            int methodCode = client.send(post,
                    HttpResponse.BodyHandlers.discarding()).statusCode();
            check(methodCode == 405, "method check");

            HttpRequest missing = HttpRequest.newBuilder(
                    URI.create(uri.toString().replace("/work", "/missing")))
                    .timeout(Duration.ofSeconds(5)).GET().build();
            int notFoundCode = client.send(missing,
                    HttpResponse.BodyHandlers.discarding()).statusCode();
            check(notFoundCode == 404, "unknown context");

            System.out.println("overlapping-requests=2");
            System.out.println("peak-active=" + handler.peak.get());
            System.out.println("third-while-busy=" + third.statusCode());
            System.out.println("successful-requests=" + handler.admitted.get());
            System.out.println("method-not-allowed=" + methodCode);
            System.out.println("unknown-context=" + notFoundCode);
            System.out.println("pool-upper-bound=" + executor.getMaximumPoolSize());
            System.out.println("tests=PASS");
        } finally {
            handler.release.countDown();
            server.stop(1);
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

### 8.2. Biên dịch/chạy trên JDK 17+

~~~bash
javac -encoding UTF-8 --release 17 --add-modules jdk.httpserver HttpServerExecutorDemo.java
java --add-modules jdk.httpserver HttpServerExecutorDemo
~~~

Stdout **chính xác** đã kiểm thử trên **OpenJDK 24**, target Java 17:

~~~text
overlapping-requests=2
peak-active=2
third-while-busy=503
successful-requests=2
method-not-allowed=405
unknown-context=404
pool-upper-bound=4
tests=PASS
~~~

### 8.3. Tại sao test này chứng minh concurrency?

- `handler.ready.await(5, SECONDS)` ở main chỉ hoàn tất khi **hai handler invocations đã cùng nhận permit và đang chờ `handler.release`**.
- Vì request thứ nhất và thứ hai chưa được trả response, chúng **overlap về thời gian**. Đây là kiểm thử concurrency tốt hơn việc gửi hai requests thật nhanh rồi đoán.
- Request thứ ba được gửi trong lúc **hai permits đều đang bị giữ**, nên nhánh `tryAcquire()==false` trả 503. HTTP 503 này đến từ **application logic**, không phải từ `AbortPolicy`.
- `peak-active=2` xác nhận cùng thời điểm có hai công việc trong vùng protected; `pool-upper-bound=4` là **giới hạn cấu hình** (không phải số thread thực đã được tạo).
- `successful-requests=2` là số request được admission/hoàn thành thành công trong fixture. Số request **bao gồm** overload/method/path ở server lớn hơn hai.
- `method-not-allowed=405` xác nhận POST không đi vào business workflow.
- `unknown-context=404` là 404 khi server không tìm được path context, không làm tăng business admission count.
- `tests=PASS` là kết quả assertions, không có nghĩa server đã được load test thực tế cho hàng triệu requests.

### 8.4. Vì sao dùng HttpExchange trong try-with-resources?

`HttpExchange` implements `AutoCloseable`. `exchange.close()` kết thúc exchange và đóng input/output streams còn mở. Code dùng `try (exchange)`, và khi gửi response dùng thêm `try (OutputStream output=...)` để đảm bảo output stream được đóng sau khi viết.

Javadoc yêu cầu **`sendResponseHeaders(status, length)` trước khi gọi `getResponseBody()`**; với body có độ dài biết trước, `length` phải bằng số **bytes** sẽ viết, nên ví dụ dùng:

~~~java
byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
exchange.sendResponseHeaders(status, bytes.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(bytes);
}
~~~

Đây là **đoạn trích**. Không dùng `String.length()` thay byte count cho tiếng Việt/emoji, vì mỗi Unicode character có thể mã hóa thành nhiều bytes.

Ở Java 17, `sendResponseHeaders(code, 0)` nghĩa **chunked response**, không phải “no body”. Dùng `-1` để báo no response body; Javadoc Java 26 có constants `HttpExchange.RSPBODY_CHUNKED` và `RSPBODY_EMPTY` nhưng chúng là additions Java 26, **không** dùng trong code biên dịch `--release 17`.

### 8.5. Method và path checks

`HttpServer.createContext("/work", handler)` dùng **longest literal prefix**. Context `"/work"` có thể match cả `"/work-extra"`; vì vậy handler vẫn kiểm tra:

~~~java
if (!"/work".equals(exchange.getRequestURI().getPath())) {
    reply(exchange, 404, "not-found");
    return;
}
~~~

Đây là đoạn trích. Không coi `createContext` là router hỗ trợ các patterns nâng cao hoặc tự phân tích authentication/URL normalization. Khi có tham số path, cần canonicalization/validation theo API contract riêng.

### 8.6. Thêm request body một cách an toàn

Nếu mở rộng sang POST:

- Chỉ chấp nhận content type và HTTP methods mong muốn.
- Giới hạn body ở cả proxy/server/app. Đừng gọi `getRequestBody().readAllBytes()` với input không biết độ dài.
- Đọc stream có quota (ví dụ tối đa 1 MiB) và timeout/deadline; từ chối 413 khi vượt.
- Với error path, đảm bảo input/response streams được đóng. Javadoc khuyến nghị consume request body trước khi close để tái sử dụng TCP connection; nếu body quá lớn, chủ động từ chối và **không** cố đọc vô hạn chỉ để keep-alive.
- Không log credentials, cookies, tokens hay PII trong raw URL/body.
- Một client ngừng gửi body có thể giữ worker nếu thiếu read timeouts; xử lý ở network/proxy policy và server implementation.

## 9. Java 21+ runnable: virtual threads làm HTTP handler

Từ Java 21, `Executors.newVirtualThreadPerTaskExecutor()` tạo một **virtual thread mới cho mỗi task**, không phải một pool có số virtual threads cố định. Vì `HttpServer.setExecutor` nhận interface `Executor`, có thể gắn executor này vào `HttpServer`.

Virtual threads phù hợp khi request handlers chủ yếu **chờ blocking I/O**; chúng có thể tăng throughput/concurrency ở workload thích hợp nhưng **không tự làm CPU computation nhanh hơn**, không tự tạo thêm DB connections và không loại memory/network/file limits.

**Dù dùng virtual threads, vẫn cần giới hạn downstream concurrency**. Ví dụ dùng `Semaphore(2)`. Lưu ý `Semaphore` trong demo là minh họa policy và chỉ có một request thực tế, chưa có stress test nhiều virtual requests.

### 9.1. File HttpServerVirtualThreadDemo.java

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class HttpServerVirtualThreadDemo {
    static void reply(HttpExchange exchange, int status, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        // Java 21+: virtual threads do not create a bounded pool.
        ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();
        Semaphore downstream = new Semaphore(2);
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 16);
        server.createContext("/check", exchange -> {
            try (exchange) {
                if (!"GET".equals(exchange.getRequestMethod())) {
                    reply(exchange, 405, "method-not-allowed");
                    return;
                }
                if (!downstream.tryAcquire()) {
                    reply(exchange, 503, "busy");
                    return;
                }
                try {
                    reply(exchange, 200,
                            "virtual=" + Thread.currentThread().isVirtual());
                } finally {
                    downstream.release();
                }
            }
        });
        server.setExecutor(executor);
        server.start();
        try {
            URI uri = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/check");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<String> response = HttpClient.newHttpClient().send(
                    request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() != 200
                    || !response.body().equals("virtual=true")) {
                throw new AssertionError("Unexpected response: " + response);
            }
            System.out.println("status=" + response.statusCode());
            System.out.println("handler-" + response.body());
            System.out.println("downstream-limit=2");
            System.out.println("tests=PASS");
        } finally {
            server.stop(1);
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

### 9.2. Biên dịch/chạy (yêu cầu JDK 21+)

~~~bash
javac -encoding UTF-8 --release 21 --add-modules jdk.httpserver HttpServerVirtualThreadDemo.java
java --add-modules jdk.httpserver HttpServerVirtualThreadDemo
~~~

Stdout **chính xác** đã kiểm thử trên OpenJDK 24 với `--release 21`:

~~~text
status=200
handler-virtual=true
downstream-limit=2
tests=PASS
~~~

### 9.3. Giải thích và những gì chưa được chứng minh

`Thread.currentThread().isVirtual()==true` là bằng chứng handler được thực thi bởi virtual thread trong môi trường test. `downstream-limit=2` chỉ in giá trị cấu hình `Semaphore`, **chưa phải** load test xác minh giới hạn dưới tải cao.

`Executors.newVirtualThreadPerTaskExecutor()` có thể tạo **rất nhiều virtual threads** nếu có nhiều requests; đó không phải phương pháp tự giới hạn concurrency. Oracle khuyến nghị **không pool virtual threads**: gắn số threads với số tasks, dùng `Semaphore`/quotas cho downstream resources.

Với workload CPU-bound hoặc synchronized/native I/O có đặc điểm đặc biệt, đo hiệu năng và thread pinning/monitoring theo JDK hiện tại. Đừng tin “virtual threads = miễn phí”, cũng đừng ép 10.000 virtual tasks gọi database có pool chỉ 10 connections mà không có admission control.

### 9.4. Nên dùng platform pool hay virtual threads?

| Bối cảnh | Hướng lựa chọn |
| --- | --- |
| Java 17 LTS, HTTP server nhỏ, workload có hạn | `ThreadPoolExecutor` có bounded queue |
| Java 21+ và nhiều handler chờ blocking I/O | Cân nhắc virtual-thread-per-task executor + Semaphore/quotas |
| Tác vụ CPU nặng | Pool theo CPU resources hoặc đẩy background work có kiểm soát |
| External service có rate/concurrency limit | Semaphore/rate limiter/circuit breaker, bất kể loại thread |
| Rất nhiều requests ngắn | Benchmark end-to-end; overhead có thể nằm ở network/serialization |
| Cần full routing, auth, TLS, metrics, HTTP/2, resiliency | Đánh giá web server/framework chuyên dụng thay vì chỉ thay executor |

## 10. Lifecycle: start, stop và shutdown phải đi cùng nhau

### 10.1. HttpServer.stop không tự quản lý custom pool

`server.stop(delaySeconds)` dừng nhận exchanges mới, chờ các handlers hiện tại hoàn thành tối đa xấp xỉ delay và đóng connections. **Server đã stop không thể start lại**. Một custom `ExecutorService` bạn cấp vào là tài nguyên **bạn sở hữu**, nên phải shutdown rõ ràng.

~~~java
server.stop(1);
executor.shutdown();
if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
    executor.shutdownNow();
}
~~~

Đây là **đoạn trích**; caller cần tính interruption/cleanup riêng. Với production, deadline shutdown nên căn cứ trên request duration và deployment orchestration, không đơn giản hardcode 1s/5s. `shutdownNow()` gửi interruption tới workers theo khả năng; nó không bảo đảm tự rollback DB hay đóng remote connection đang kẹt.

### 10.2. Graceful shutdown hợp lý

1. Đánh dấu ứng dụng **not ready** để load balancer ngừng gửi traffic mới.
2. Dừng nhận requests mới hoặc route mới theo orchestration.
3. Chờ active requests trong deadline đã định.
4. `server.stop(graceSeconds)`.
5. `executor.shutdown()`, `awaitTermination()`.
6. Nếu quá deadline, `shutdownNow()` và cleanup/telemetry; quản lý transaction/cancellation.
7. Release downstream clients, DB pools, file descriptors, logging resources.

Ở demo, server là loopback fixture ngắn hạn nên không có load balancer; đoạn `finally` vẫn giữ đúng lifetime.

### 10.3. Không dùng sleep để “đợi request xong”

`Thread.sleep(2000)` trong main không chứng minh handler đã hoàn tất. Dùng `CompletableFuture.get(timeout)`, `CountDownLatch`, `Phaser` hoặc request-level completion signals. Với prod, dùng counters/in-flight tracking và deadlines. Một worker có thể bị treo do I/O; hãy có timeout và cancellation policy.

### 10.4. Exception ở main vẫn phải dừng server

Test `try/finally` đảm bảo dù assertion fail, main vẫn `release.countDown()` trước để không giữ hai handlers chờ mãi, sau đó `server.stop` và shutdown pool. Nếu không, các non-daemon worker threads có thể giữ JVM không thoát.

## 11. Observability và vận hành

### 11.1. Các metrics cần theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| Requests/sec, response status 2xx/4xx/5xx | Tải và error classes |
| Active handler tasks | Công việc đang chạy |
| Executor pool size / active count | Có gần max threads không |
| Queue depth / remaining capacity | Có đang dồn request tasks không |
| RejectedExecutionException count | Executor bị saturate/shutdown |
| Semaphore available permits / rejected admissions | Downstream concurrency pressure |
| Request p50/p95/p99 latency | Trải nghiệm client |
| Body read/write timeouts | Slow clients/network |
| CPU, heap, GC, thread dumps | Contention, leaks, starvation |
| Downstream pool utilization | DB/HTTP client là bottleneck thật |
| Shutdown duration/in-flight requests | Tắt dịch vụ có an toàn không |

`ThreadPoolExecutor.getActiveCount()` và `getQueue().size()` là snapshots có race, dùng làm telemetry tương đối, không làm **business invariant**. Nếu cần chính xác số active nghiệp vụ trong critical section, dùng `Semaphore`/atomic state quản lý riêng.

### 11.2. Logs không được lộ dữ liệu

Log request ID/correlation ID, method, route template, status, duration, overload reason, thread name và exception type đã lọc. Không log raw Authorization, cookies, passwords, tokens, bank/PII payload hoặc toàn bộ URL query nếu chứa secrets. Gắn correlation IDs per exchange; tránh giữ một static mutable “current user” chung cho mọi request.

### 11.3. Security của HTTP server nhỏ

- Demo bind `127.0.0.1`, **không mở Internet**.
- Nếu public endpoint, cần TLS (có thể `HttpsServer`/`HttpsConfigurator`) hoặc reverse proxy HTTPS đúng, client auth/authorization, quotas/rate limits, CORS/CSRF policy thích hợp.
- Giới hạn header/body sizes, read/write/deadlines, connection counts, slow clients; kiểm tra version-specific `jdk.httpserver` system properties và reverse proxy protections.
- Validate path và content type, không tin raw headers và forwarded IP không được kiểm soát.
- Không để management/metrics endpoint chứa secrets hoặc cho phép hành động nguy hiểm.
- JDK HttpServer không tự cung cấp full web framework behavior; cần đánh giá phù hợp với SLA và compliance thực tế.

### 11.4. JDK 26 thay đổi HttpExchange attribute behavior

JDK 26 đã thay đổi default attribute storage trong HTTP server implementation: attributes của `HttpExchange` mặc định theo exchange thay vì chia sẻ với `HttpContext` như implementation trước đó. Vì vậy đừng viết code dựa vào “`exchange.setAttribute` luôn là global context state” rồi dùng nó làm một shared counter giữa requests. Thậm chí trước thay đổi đó, shared mutable state vẫn cần đồng bộ rõ ràng. Dùng explicit thread-safe shared objects như `AtomicInteger` hoặc dependency injection.

## 12. Những lỗi thiết kế dễ gặp

| Lỗi | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Không đặt executor | Default handler có thể chạy trên server thread, handler chậm cản các requests khác | Đặt executor tường minh trước start |
| Gọi `setExecutor` sau `start` | `IllegalStateException` | Cấu hình trước start |
| Coi `backlog=64` là 64 requests đang chạy | Hiểu sai tầng TCP | Tách backlog, pool, queue và admission |
| Dùng `newCachedThreadPool` vô hạn | Threads tăng mạnh dưới burst | Đặt giới hạn theo workload/policy |
| Dùng `newFixedThreadPool` nhưng tưởng queue bounded | Work queue không giới hạn theo mặc định | `ThreadPoolExecutor` + `ArrayBlockingQueue` |
| Pool 4 threads nhưng DB 1 connection | Workers chờ DB, throughput kém | Semaphore/pool sizing theo downstream |
| Bắt `RejectedExecutionException` ở handler để trả 503 | Rejection có thể xảy ra **trước khi handler chạy** | Overload control ở handler/proxy và policy đầy đủ |
| `CallerRunsPolicy` không suy xét | Dispatch thread có thể bị blocking | Benchmark/đánh giá dispatch architecture |
| Handler dùng `counter++` | Lost updates | AtomicInteger/LongAdder |
| `synchronized` toàn handler | Mất concurrency | Thu nhỏ critical section |
| Trả 503 nhưng quên release permit | Kẹt toàn hệ thống | `try/finally` đúng acquire/release |
| Dùng `Thread.sleep` để test concurrency | Không chắc requests overlap | Latches/Futures/barriers |
| Dùng `String.length()` cho body length | Sai UTF-8 Content-Length | `bytes.length` |
| Không close `HttpExchange` | Leak connection/stream | try-with-resources hoặc finally |
| Viết response body trước headers | Sai HttpExchange lifecycle | sendResponseHeaders trước |
| Đọc raw body `readAllBytes` không quota | OOM/DoS | Stream bounded input |
| Dùng context `"/api"` nghĩ chỉ match `"/api"` | Prefix có thể match `"/api-other"` | Kiểm tra exact path hoặc routing an toàn |
| Đặt 405 nhưng thiếu Allow | Không hoàn chỉnh HTTP method contract | Thêm `Allow` |
| Retry GET/POST vô hạn sau 503 | Retry storm/duplicate effects | Exponential backoff/jitter, idempotency |
| Chỉ gọi `server.stop` | Custom executor còn threads sống | `executor.shutdown/awaitTermination` |
| Tưởng virtual threads là bounded pool | Không giới hạn concurrent tasks | Semaphore/quota |
| Tin HttpServer là full production gateway | Thiếu các features vận hành | Reverse proxy/framework nếu cần |
| Log raw Authorization/PII | Lộ thông tin | Structured/redacted logging |

## 13. Checklist kiểm thử integration và load

Một chương trình chạy `tests=PASS` chưa đủ cho production. Nên kiểm thử:

| Tình huống | Kỳ vọng |
| --- | --- |
| Hai GET đồng thời | Hai handler thực sự overlap |
| Request thứ ba khi chỉ hai permits | HTTP 503 có chủ đích, không giữ permit |
| POST vào GET-only endpoint | HTTP 405 + Allow header |
| Unknown context | HTTP 404 |
| URL context prefix edge | Không vô tình xử lý `"/workevil"` |
| Body UTF-8 có tiếng Việt/emoji | Content-Length bằng byte count, decode đúng |
| Client ngắt giữa response | Exchange được close, không leak permit |
| Handler ném IOException | Metrics/log và cleanup vẫn chạy |
| ThreadPoolExecutor queue đầy | Rejection behavior biết rõ, không mặc định có HTTP 503 |
| Burst 1K/10K requests | Latency, heap, queue, connection limits trong SLA |
| Slow client/slow body | Server/proxy deadline đúng |
| Downstream DB pool cạn | Bounded overload, không deadlock |
| Request body quá lớn | 413/close theo policy, không OOM |
| Task CPU-bound | Pool và CPU quota không saturation bất thường |
| Per-request MDC/user data | Không lẫn dữ liệu giữa threads |
| HTTP keep-alive reuse | Exchange lifecycle và body reading ổn |
| Graceful shutdown giữa traffic | No new exchanges, active tasks xử lý deadline |
| JDK version upgrade | setExecutor, attributes, properties, timeouts đã test |
| Virtual thread mode | isVirtual true, downstream concurrency vẫn bounded |
| Security/public exposure | TLS/auth/rate limits, headers và secrets phù hợp |

### 13.1. Cách đo concurrency không phụ thuộc timing

Đừng kết luận “server đồng thời vì hai requests đều trả 200”. Nếu không có đồng bộ, request A có thể hoàn tất **trước** request B mà ta không biết. `CountDownLatch` trong demo buộc hai handlers cùng vào vùng protected **trước khi được mở khóa tiếp tục**, từ đó kiểm chứng overlap thực tế.

### 13.2. Đo queueing delay

Thông thường response latency gồm thời gian TCP/TLS, queue trong server/executor, xử lý handler, downstream latency, response I/O. Nếu chỉ đo handler duration, bạn có thể bỏ qua thời gian client đang đợi dispatch. Hãy đo end-to-end p95/p99, queue depth và admission rejections để tìm root cause.

## 14. Câu hỏi tự đánh giá

**1.** `HttpServer.setExecutor` phải gọi trước hay sau `start()`?

**Đáp án:** Trước `start()`; gọi sau có thể ném `IllegalStateException` theo Javadoc.

**2.** Khi không đặt custom Executor, HttpServer đảm bảo nhiều worker threads không?

**Đáp án:** Không. Default implementation dùng thread được tạo bởi `start()`, theo Javadoc; không coi nó là thread pool.

**3.** `backlog=64` có nghĩa tối đa 64 HTTP requests xử lý đồng thời?

**Đáp án:** Không. Backlog là hàng đợi TCP connections chờ accept, không phải HTTP task/worker/requests limit.

**4.** FixedThreadPool có fixed queue không?

**Đáp án:** Không. `Executors.newFixedThreadPool` dùng unbounded queue theo factory contract; muốn bounded queue cần cấu hình `ThreadPoolExecutor`.

**5.** Bounded queue có tự khiến client nhận 503?

**Đáp án:** Không. Task rejection xảy ra tại executor dispatch. Handler không nhất thiết chạy, và JDK/provider không hứa HTTP 503 tự động.

**6.** Vì sao dùng `Semaphore.tryAcquire()` trong handler?

**Đáp án:** Nó kiểm soát số business operations đồng thời và cho phép response 503 nếu đã bận, không đợi vô hạn.

**7.** Vì sao phải `release()` trong `finally`?

**Đáp án:** Để không rò permit khi handler lỗi, timeout hoặc bị interrupt sau acquire.

**8.** `AtomicInteger` khác `int++` thế nào?

**Đáp án:** AtomicInteger có atomic read-modify-write đúng khi nhiều threads cùng tăng, `int++` không atomic.

**9.** `CountDownLatch` kiểm thử gì trong chương trình?

**Đáp án:** Xác nhận **hai handlers đã cùng đang chạy/chờ** trước khi test gửi request thứ ba; không dựa vào sleep ngẫu nhiên.

**10.** Vì sao response length phải lấy từ `bytes.length`?

**Đáp án:** `sendResponseHeaders` cần độ dài body bằng bytes, còn Java String length là UTF-16 code units, không phải UTF-8 bytes.

**11.** `server.stop(1)` có shutdown ThreadPoolExecutor do bạn tạo không?

**Đáp án:** Không tự động quản lý lifecycle của custom executor; ứng dụng gọi shutdown/awaitTermination riêng.

**12.** Virtual threads có pool size cố định không?

**Đáp án:** `newVirtualThreadPerTaskExecutor` tạo virtual thread mỗi task, không có fixed-size virtual thread pool; giới hạn downstream bằng Semaphore/rate limits.

**13.** Virtual threads có tăng tốc CPU-heavy work không?

**Đáp án:** Không tự làm một tác vụ CPU chạy nhanh; phù hợp khi nhiều tasks chờ blocking I/O và có đủ resources.

**14.** Có thể dùng HttpExchange attributes như một global mutable map giữa requests?

**Đáp án:** Không nên. JDK 26 còn thay đổi semantics default attribute storage; dùng explicit shared thread-safe state.

**15.** Khi nào nên dùng HttpsServer/reverse proxy?

**Đáp án:** Khi phục vụ network không tin cậy/cần TLS, auth, rate limiting, production load balancing và security controls; chọn theo yêu cầu, không chỉ vì demo chạy trên localhost.

### Bài tập thực hành

1. Chạy `HttpServerExecutorDemo`, giải thích vì sao `overlapping-requests=2` chứng minh concurrency.
2. Đổi `Semaphore(2)` thành `Semaphore(1)` và điều chỉnh latch/assertions để test một request bị reject.
3. Đổi pool max từ 4 thành 2; giải thích vì sao request thứ ba có thể phải **chờ trong executor queue** thay vì nhận 503 ngay.
4. Viết test queue saturation với `AbortPolicy` nhưng **không giả định client luôn thấy HTTP 503**.
5. Bổ sung metrics `executor.getActiveCount()` và `getQueue().size()`, đo dưới burst.
6. Thay `AtomicInteger` bằng biến `int` không đồng bộ trong một **test riêng**, quan sát lost updates.
7. Gửi UTF-8 tiếng Việt trong body response, kiểm tra Content-Length khớp bytes.
8. Thêm POST JSON có giới hạn 64 KiB và HTTP 413 cho body quá dài.
9. Dùng `createContext("/api")` rồi request `/apiExtra`, giải thích prefix match.
10. Đưa processing chậm sang background executor riêng, thiết kế lifecycle/cancellation.
11. Chạy `HttpServerVirtualThreadDemo` trên JDK 21+, xác nhận `isVirtual()==true`.
12. Thêm nhiều virtual requests tới một fake downstream có Semaphore=2 và assert peak in-flight <=2.
13. Thêm endpoint `/health`, không đưa secrets vào response/log.
14. Viết graceful shutdown test khi có một request đang bị block và deadline khác 0.
15. Benchmark 1K HTTP requests với bounded platform pool và virtual threads, đo throughput/latency/heap/throttling trên máy thử.
16. Dùng rate limiter theo client để phân biệt HTTP 429 với 503 do overload.
17. Thử HTTP client timeout, stop() giữa request và xác minh không leak permit/resources.

## 15. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — HttpServer](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `setExecutor` trước `start`, default executor, context prefix, backlog, stop.
- [Oracle Java SE 26 — HttpExchange](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request/response lifecycle, sendResponseHeaders, close.
- [Oracle Java SE 26 — HttpHandler](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): xử lý một HTTP exchange.
- [Oracle Java SE 26 — HttpContext](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): context mapping.
- [Oracle Java SE 26 — package com.sun.net.httpserver](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/package-summary.html): embedded server overview.
- [Oracle Java SE 26 — jdk.httpserver module](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/module-summary.html): server API/module-level properties.
- [Oracle Java SE 26 — HttpsServer](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): server HTTPS.
- [Oracle Java SE 26 — Executor](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Executor.html): tác vụ `execute(Runnable)`.
- [Oracle Java SE 26 — ExecutorService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html): lifecycle/shutdown.
- [Oracle Java SE 26 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): pool sizing, queues, rejection handlers, metrics.
- [Oracle Java SE 26 — Executors](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Executors.html): fixed pool và virtual-thread-per-task executor.
- [Oracle Java SE 26 — Semaphore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Semaphore.html): permit-based concurrency bounds.
- [Oracle Java SE 26 — CountDownLatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html): test synchronization.
- [Oracle Java SE 26 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded queues.
- [Oracle Java SE 26 — AtomicInteger](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic counters.
- [Oracle Java SE 26 — HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP test client.
- [Oracle Java SE 26 — Virtual Threads guide](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html): Java21+ model, don't pool virtual threads, use Semaphore for resource limits.
- [Oracle Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): API đối chiếu bản `--release 17`.
- [Oracle Java SE 21 — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor()` từ Java 21.

**Ghi nhớ:** Với `HttpServer`, hãy gọi **`setExecutor` trước `start`**, và thiết kế **ba tầng giới hạn độc lập**: TCP backlog, executor pool/queue, và downstream concurrency (ví dụ `Semaphore`). Test bằng yêu cầu HTTP thật có overlap, bảo vệ shared state bằng concurrency primitives, quản lý response/HttpExchange đúng lifecycle và dừng custom executor rõ ràng. Java 21+ virtual threads giúp scale các handlers chờ blocking I/O nhưng **không bỏ giới hạn business resource**. Không dùng một HTTP server gọn như thể nó tự cung cấp đầy đủ production security, routing hoặc overload control.

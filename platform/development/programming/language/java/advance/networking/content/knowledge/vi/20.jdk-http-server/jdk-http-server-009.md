# Cấu hình executor, giới hạn xử lý và stop có thời gian chờ

## 1. Bài toán và mục tiêu học tập

Java SE 17 cung cấp HTTP server nhỏ gọn trong module `jdk.httpserver`, đặc biệt lớp `com.sun.net.httpserver.HttpServer`. Một server có thể nhận HTTP request và trả JSON/text trong vài dòng, nhưng khi có nhiều client, cần quyết định **handler chạy trên thread nào**, **bao nhiêu công việc được xử lý đồng thời**, **request vượt tải nhận phản hồi gì**, và **server dừng bằng cách nào để request đang chạy có cơ hội hoàn tất**.

Ba API/khái niệm trung tâm:
- `HttpServer.setExecutor(Executor)` chọn executor nhận các tác vụ xử lý HTTP. **Phải gọi trước `start()`**.
- `ThreadPoolExecutor`/`Semaphore` cho phép giới hạn threads, hàng chờ task và số tác vụ nghiệp vụ hoạt động. Cần phân biệt với **TCP backlog** của listener.
- `HttpServer.stop(int delay)` ngừng nhận exchange mới và **chờ các handlers hiện có tối đa khoảng `delay` giây**, sau đó đóng TCP connections. `delay` tính bằng **giây**; không phải số milliseconds, không phải lệnh shutdown executor.

Sau bài học, bạn sẽ có thể:
1. Tạo và cấu hình JDK `HttpServer` với executor đúng thứ tự.
2. Giải thích default executor, bounded queue, `CallerRunsPolicy` và `RejectedExecutionException`.
3. Dùng `Semaphore.tryAcquire()` trả `503 Service Unavailable` khi hết capacity thay vì block vô hạn.
4. Phân biệt backlog, worker count, queue depth, active business operations, request-body limit và per-client rate limit.
5. Xây handler đóng `HttpExchange` và response stream rõ ràng.
6. Giải thích chi tiết `stop(0)`, `stop(2)`, những request bị cắt và việc không thể restart cùng instance.
7. Dừng executor riêng bằng `shutdown()`, `awaitTermination()` và best-effort `shutdownNow()`.
8. Chạy hai chương trình Java 17+ offline trên loopback: concurrent request/503/graceful stop và body giới hạn 8 byte/413.
9. Thiết kế test có latch, timeout và metrics thay vì dự đoán thứ tự scheduling.

## 2. Bản đồ kiến trúc: listener → executor → handler

```text
 HTTP clients
      │ TCP connections
      ▼
HttpServer listening socket
      │
      ├─ backlog: pending TCP connection indications
      │
      ▼
HTTP dispatch
      │  executor.execute(handlerTask)
      ▼
  Executor
      │
      ├─ worker thread #1 ─► HttpHandler.handle(exchange A)
      ├─ worker thread #2 ─► HttpHandler.handle(exchange B)
      └─ task queue       ─► pending tasks
                                   │
                      application admission policy
                                   │
                           Semaphore.tryAcquire()
                            ├─ permit -> business logic
                            └─ no permit -> HTTP 503
                                   │
                      sendResponseHeaders + body
                                   │
                             exchange.close()
```

**Từng tầng có chức năng khác nhau.** `backlog=16` không có nghĩa “16 handlers chạy cùng lúc”. `maximumPoolSize=2` không có nghĩa “server chỉ giữ tối đa 2 HTTP connections”. `Semaphore(1)` chỉ giới hạn đoạn nghiệp vụ có acquire permit; nó không giới hạn tất cả những hoạt động network/HTTP parsing phía ngoài đoạn đó.

Mỗi `HttpExchange` tương ứng một lần trao đổi HTTP, có URI, method, request headers, request body, response headers/body. Một connection keep-alive có thể phục vụ các exchanges liên tiếp. Không tái sử dụng cùng một `HttpExchange` cho các request độc lập.

## 3. API HttpServer cần nắm

| API | Vai trò | Ghi nhớ |
| --- | --- | --- |
| `HttpServer.create(addr, backlog)` | Bind listener | Port `0` dùng ephemeral port trong tests |
| `createContext(path, handler)` | Ánh xạ path prefix tới handler | Path matching là prefix; kiểm tra exact URI path nếu cần |
| `setExecutor(executor)` | Chọn nơi thực thi handler tasks | Chỉ gọi **trước `start()`** |
| `getExecutor()` | Trả executor đã đặt hoặc null | Null thường nghĩa default implementation |
| `start()` | Khởi động server background thread | Không được đổi executor sau đó |
| `getAddress()` | Xem địa chỉ/port server đã bind | Hữu ích cho test không hardcode port |
| `stop(delay)` | Đóng listener, chờ các exchanges đang chạy có giới hạn | `delay` là số giây không âm; không restart instance |
| `removeContext(path)` | Ngừng ánh xạ một context | Không đồng nghĩa dừng toàn server |

Một đoạn minh họa:

```java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8080), 16);
ExecutorService workers = Executors.newFixedThreadPool(4);
server.setExecutor(workers);
server.createContext("/ping", exchange -> {
    byte[] bytes = "pong".getBytes(StandardCharsets.UTF_8);
    try {
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    } finally {
        exchange.close();
    }
});
server.start();

// Ở giai đoạn shutdown:
server.stop(5);
workers.shutdown();
```

**Mảnh code**, chưa có imports, quản lý lỗi/await termination và timeout đầy đủ; không phải file Java độc lập. Đặc biệt `Executors.newFixedThreadPool(4)` có **queue tasks không được giới hạn theo factory**, nên không xem đây là cấu hình production chống overload. Hai chương trình đầy đủ ở các mục sau sử dụng bounded `ThreadPoolExecutor`.

## 4. Cấu hình executor phải trước start

Theo Java 17 `HttpServer.setExecutor`: executor phải được thiết lập **trước `start()`**. Nếu server đã start, `setExecutor(...)` ném `IllegalStateException`.

```text
HttpServer.create / bind
       ↓
createContext(...)
       ↓
tạo và cấu hình Executor
       ↓
server.setExecutor(executor)
       ↓
server.start()
       ↓
nhiều HttpExchange được xử lý
       ↓
server.stop(graceSeconds)
       ↓
executor.shutdown() + awaitTermination(...)
```

Bạn có thể tạo contexts trước hay sau `setExecutor`, nhưng **trước khi start** hãy đảm bảo listener, contexts, executor và dependencies sẵn sàng.

Sai:

```java
server.start();
server.setExecutor(Executors.newFixedThreadPool(8));
// IllegalStateException: đã quá thời điểm gắn executor
```

Nếu muốn thay số worker khi đang chạy, phải dùng cấu hình động an toàn của chính loại executor đã chọn (nếu hỗ trợ) hoặc thay server instance qua rolling restart. Không gọi lại `setExecutor` để thay một executor đã chạy.

## 5. Default executor và thread dùng để xử lý request

Nếu ứng dụng không gọi `setExecutor`, hoặc gọi `setExecutor(null)`, JDK HTTP server dùng **default executor**. Tài liệu Java 17 mô tả default implementation **sử dụng thread do `start()` tạo**. Đừng tự giả định mặc định có sẵn một thread pool lớn.

Điều này có nghĩa:
- Một handler blocking lâu có thể ảnh hưởng rõ rệt tới các requests khác khi dùng default.
- Khi muốn kiểm soát throughput và concurrency, cần tự cung cấp executor.
- `getExecutor()==null` không phải lỗi; nó chỉ cho biết không có executor tường minh.
- Nếu server implementation/provider khác được dùng, phải kiểm tra tài liệu của chính provider đó.

`Executor` chỉ cần `execute(Runnable)`; `ExecutorService` thêm `shutdown`, `awaitTermination` và `shutdownNow` để quản lý lifecycle.

## 6. Các kiểu executor và trade-off

| Executor | Ưu điểm | Nguy cơ |
| --- | --- | --- |
| `Runnable::run` | Đơn giản, không tạo worker mới | Handler chạy ngay trên thread submit, có thể chặn dispatcher |
| `Executors.newFixedThreadPool(n)` | Cố định worker count | Queue mặc định unbounded; pending work có thể tăng rất lớn |
| `Executors.newCachedThreadPool()` | Mở rộng workers khi tải | Thread count có thể tăng mạnh với I/O chậm |
| `ThreadPoolExecutor` + bounded queue | Giới hạn worker threads và queue | Cần rejection policy + admission ở tầng thích hợp |
| Custom `Executor` | Linh hoạt | Cần bảo đảm không mất HTTP tasks và lifecycle chuẩn |

Một executor 2 workers **không** trực tiếp bảo đảm hệ thống chỉ có 2 concurrent TCP connections. HTTP server/OS vẫn giữ connection state, input buffers và pending requests. Vì vậy thiết kế có bound phải bao gồm **tất cả các resource chính**, không chỉ worker threads.

## 7. Bounded ThreadPoolExecutor và CallerRunsPolicy

Cấu hình minh họa:

```java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 2,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(4),
        new ThreadPoolExecutor.CallerRunsPolicy());

server.setExecutor(pool); // trước server.start()
```

**Mảnh code**, cần imports và biến `server` đã tạo.

- `corePoolSize=2`, `maximumPoolSize=2`: tối đa 2 worker threads do pool quản lý.
- `ArrayBlockingQueue<>(4)`: tối đa 4 tasks chờ **trong queue executor**.
- `CallerRunsPolicy`: khi pool và queue đầy, một rejected task có thể **chạy ngay trên thread gọi execute()**, thay vì bị bỏ. Đối với HTTP server, thread gọi execute có thể là **dispatcher**.

**Cảnh báo quan trọng:** `CallerRunsPolicy` không tạo một giới hạn toàn cục rằng “chỉ có 2 handlers được thực thi”: task có thể chạy **ngoài workers** trên caller thread. Nó cũng có thể khiến dispatcher bị chặn bởi một handler chậm, làm tăng latency và ảnh hưởng các kết nối khác. Nếu executor đã shutdown, policy này **bỏ** rejected task, không chạy nó. Đây là trade-off cần được kiểm thử, không phải cấu hình mặc định tốt trong mọi môi trường.

## 8. Rejection policy không tự động tạo HTTP 503

Khi executor đã bão hòa, `ThreadPoolExecutor` gọi `RejectedExecutionHandler`:

| Policy | Hành vi | Rủi ro với HTTP |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` | Không bảo đảm một HTTP 503 được gửi cho client |
| `CallerRunsPolicy` | Chạy task trên caller thread nếu executor còn hoạt động | Có thể chặn dispatcher/accept path |
| `DiscardPolicy` | Im lặng bỏ task | Client có thể chờ timeout mà không có response |
| `DiscardOldestPolicy` | Bỏ một task đang chờ, thử enqueue task mới | Request cũ có thể bị mất, khó bảo đảm fairness |

**Đừng gán HTTP status cho rejection ở executor theo suy đoán.** HTTP handler chưa chắc đã được dispatch để có quyền gọi `exchange.sendResponseHeaders(503,...)`.

Mẫu chống quá tải cần nhiều lớp: reverse proxy/ingress connection limits, thread/queue limits, handler-level admission control, per-tenant quota và request-body/time limits. Muốn bảo đảm mọi request đã accept đều nhận được 503 khi vượt quota, cần thiết kế capacity đủ cho error handler hoặc admission ở tầng **trước** khi tác vụ phải xếp hàng trong executor.

## 9. Backlog TCP không phải max request count

`HttpServer.create(addr, 16)` nhận `backlog=16`: đó là **số connection indications đang chờ accept**, do OS/network stack quản lý với semantics phụ thuộc implementation. Nó không giới hạn:
- Số `HttpHandler.handle` đang chạy.
- Số tasks chờ trong `ThreadPoolExecutor`.
- Số keep-alive connections đã accept.
- Số requests mỗi giây.
- Dung lượng request body hoặc response body.

Ví dụ server bind port 0:

```java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 0), 16);
int allocatedPort = server.getAddress().getPort();
```

Đây là mảnh code. Port `0` cho OS cấp ephemeral port, giúp test tránh xung đột cổng; khi in stdout test, nên in status/path thay vì con số port thay đổi ở mỗi lần chạy.

## 10. Semaphore giới hạn công việc đang hoạt động

`Semaphore` có số permit được cấp. Với 1 permit, chỉ một handler được đồng thời bước vào đoạn `performWork`:

```java
Semaphore permits = new Semaphore(1);

server.createContext("/work", exchange -> {
    try {
        if (!permits.tryAcquire()) {
            respond(exchange, 503, "busy");
            return;
        }
        try {
            performWork(exchange);
        } finally {
            permits.release();
        }
    } finally {
        exchange.close();
    }
});
```

Đây là **mảnh code**; `respond` và `performWork` do ứng dụng định nghĩa, xử lý checked exceptions theo API.

`tryAcquire()` **không block** khi không có permit: handler có thể trả `503 Service Unavailable` nhanh. Khác với `acquire()`, thứ có thể khiến handler thread bị giữ vô hạn trong lúc đợi và làm tắc pool. `release()` phải đặt trong `finally` sau khi acquire thành công, kể cả khi xử lý ném exception.

**Semaphore(1) giới hạn chỉ đoạn đã bảo vệ.** Nếu handler đọc một file 5 GiB trước khi gọi `tryAcquire`, memory/disk/network resources vẫn có thể bị tiêu thụ trước admission. Đặt kiểm soát càng sớm càng phù hợp với loại resource cần bảo vệ.

## 11. 503, 429 và 413 biểu thị giới hạn khác nhau

| HTTP status | Bối cảnh thích hợp |
| --- | --- |
| `503 Service Unavailable` | Server đang overload, draining hoặc tạm thời không xử lý được |
| `429 Too Many Requests` | Rate limit/quota theo user, tenant, API key, hoặc client |
| `413 Content Too Large` | Request content vượt giới hạn kích thước |
| `408 Request Timeout` | Server timeout trong lúc đợi request hoàn chỉnh theo semantics HTTP |
| `504 Gateway Timeout` | Gateway không nhận kịp response từ upstream; demo local có thể dùng 504 để đánh dấu mô phỏng timeout nhưng service thật cần đúng vai trò và semantics |

`503` có thể kèm header `Retry-After` như `Retry-After: 1` để gợi ý thời gian chờ trước khi thử lại. Đây là **gợi ý** chứ không cam kết chính xác 1 giây sau chắc có capacity. Client nên giới hạn retries/backoff, đặc biệt với requests có side effects.

**Rate limiting khác concurrency limiting:** semaphore kiểm soát bao nhiêu tác vụ đang chạy cùng lúc; token bucket kiểm soát bao nhiêu request qua mỗi khoảng thời gian. Một handler cực nhanh có thể xử lý hàng nghìn requests/s dù `Semaphore(1)`, vì permit được release liên tục.

## 12. Chương trình Java 17+ chạy được: bounded executor, 503 và stop(2)

Lưu đúng tên file **`BoundedHttpServerDemo.java`**. Chương trình tạo server local:
- Executor gồm **2 worker threads**, queue **4 tasks**, `CallerRunsPolicy`.
- `Semaphore(1)` bảo vệ vùng làm việc.
- Request 1 giữ permit khi chờ `CountDownLatch`. Request 2 nhận 503.
- `server.stop(2)` được gọi từ lifecycle thread; request đầu được release và trả 200.
- Sau stop, ứng dụng **tự** shutdown executor và chờ termination.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedHttpServerDemo {
    private static void respond(HttpExchange exchange, int code, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        if (code == 503) {
            exchange.getResponseHeaders().set("Retry-After", "1");
        }
        exchange.sendResponseHeaders(code, bytes.length);
        try (var output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor workers = new ThreadPoolExecutor(
                2, 2, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(4),
                new ThreadPoolExecutor.CallerRunsPolicy());
        Semaphore activeRequests = new Semaphore(1);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 16);
        server.setExecutor(workers);
        server.createContext("/work", exchange -> {
            try {
                if (!"/work".equals(exchange.getRequestURI().getPath())) {
                    respond(exchange, 404, "not-found");
                    return;
                }
                if (!"GET".equals(exchange.getRequestMethod())) {
                    exchange.getResponseHeaders().set("Allow", "GET");
                    respond(exchange, 405, "method-not-allowed");
                    return;
                }
                if (!activeRequests.tryAcquire()) {
                    respond(exchange, 503, "busy");
                    return;
                }
                try {
                    entered.countDown();
                    if (!release.await(5, TimeUnit.SECONDS)) {
                        respond(exchange, 504, "timed-out");
                    } else {
                        respond(exchange, 200, "ok");
                    }
                } finally {
                    activeRequests.release();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                exchange.close();
            } finally {
                exchange.close();
            }
        });
        server.start();
        boolean lateExecutorRejected = false;
        try {
            server.setExecutor(Runnable::run);
        } catch (IllegalStateException expected) {
            lateExecutorRejected = true;
        }
        System.out.println("late-executor-rejected=" + lateExecutorRejected);

        Thread stopper = null;
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/work");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3)).build();
            HttpRequest req = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(6)).GET().build();
            CompletableFuture<HttpResponse<String>> first = client.sendAsync(
                    req, HttpResponse.BodyHandlers.ofString());
            if (!entered.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Request not entered");
            }
            System.out.println("first-in-flight=" + !first.isDone());
            HttpResponse<String> busy = client.send(req,
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("overload-status=" + busy.statusCode());
            System.out.println("overload-body=" + busy.body());

            stopper = new Thread(() -> server.stop(2), "server-stopper");
            stopper.start();
            release.countDown();
            HttpResponse<String> done = first.get(5, TimeUnit.SECONDS);
            System.out.println("first-status=" + done.statusCode());
            System.out.println("first-body=" + done.body());
            stopper.join(4000);
            System.out.println("server-stopped=" + !stopper.isAlive());
        } finally {
            release.countDown();
            server.stop(0);
            if (stopper != null) stopper.join(4000);
            workers.shutdown();
            if (!workers.awaitTermination(3, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
            System.out.println("executor-shutdown=" + workers.isShutdown());
        }
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac BoundedHttpServerDemo.java
java BoundedHttpServerDemo
```

Stdout đã kiểm chứng khi chạy với `javac --release 17`:

```text
late-executor-rejected=true
first-in-flight=true
overload-status=503
overload-body=busy
first-status=200
first-body=ok
server-stopped=true
executor-shutdown=true
```

### Đọc output

1. `late-executor-rejected=true`: `setExecutor` sau start ném `IllegalStateException`.
2. `first-in-flight=true`: server đã vào handler request 1 nhưng chưa release latch; future vẫn đang chờ response.
3. `overload-status=503` và `overload-body=busy`: request 2 được dispatch khi `Semaphore(1)` đang hết permit và bị handler từ chối.
4. `first-status=200`, `first-body=ok`: request 1 được release, hoàn thành response.
5. `server-stopped=true`: thread gọi `server.stop(2)` đã kết thúc.
6. `executor-shutdown=true`: ví dụ gọi `workers.shutdown()` riêng, rồi chờ `awaitTermination`.

### Vì sao dùng latch thay sleep?

Không thể đảm bảo request 1 sẽ luôn chậm hơn request 2 chỉ bằng `Thread.sleep(20)`. `entered.await(...)` xác nhận request 1 **đã được handler nhận và giữ permit** trước khi gửi request 2. `release.countDown()` cho request 1 hoàn tất sau khi đã quan sát HTTP 503. Latch này là cơ chế **test deterministic**, không phải mẫu để chặn production requests lâu dài.

### Vì sao stop chạy ở thread khác?

`HttpServer.stop(delay)` có thể block khi chờ handlers; không nên gọi đồng bộ trong handler đang được server chờ hoàn tất. Thread `server-stopper` đóng vai lifecycle coordinator. Demo release request đầu để nó có thể hoàn tất trong grace period; đây không phải cam kết mọi công việc chậm đều hoàn thành trong 2 giây.

## 13. stop(int delay): semantics chính xác

Tài liệu Java 17 mô tả `HttpServer.stop(int delay)`:
1. **Đóng listening socket**, không cho các HTTP exchanges mới được xử lý.
2. **Chờ** cho đến khi các handlers hiện tại hoàn tất **hoặc khoảng `delay` giây trôi qua**, tùy điều kiện nào đến trước.
3. Sau đó **đóng các TCP connections còn mở**; thread nền do `start()` tạo kết thúc và `stop` trả về.
4. Sau khi dừng, **không thể tái sử dụng cùng HttpServer instance**.

`delay` là **số nguyên giây không âm**, không phải milliseconds.

```java
server.stop(0);  // không có cửa sổ graceful đáng kể
server.stop(2);  // cho current exchanges khoảng tối đa 2 GIÂY
```

Hai dòng là **mảnh code minh họa cho các lựa chọn riêng**, không phải đề xuất gọi liên tiếp trên cùng một server. `stop(-1)` ném `IllegalArgumentException`. `stop(30)` **không bắt buộc chờ đủ 30 giây**; nếu tất cả handlers hoàn tất sớm, nó có thể trả về sớm. `stop(0)` có thể cắt exchange đang làm việc, khiến client thấy connection reset/truncated response.

Sau stop, muốn phục vụ HTTP request tiếp cần **tạo server mới** và cấu hình nó; không gọi `start()` lại trên instance đã stopped.

## 14. Phân biệt stop server với shutdown executor

`server.stop(5)` đóng listener và kết thúc exchange lifecycle theo contract. Nó **không được coi là** lệnh shutdown pool do application đã tạo. Với `ExecutorService`:

```java
server.stop(5);
workers.shutdown();
if (!workers.awaitTermination(10, TimeUnit.SECONDS)) {
    workers.shutdownNow();
}
```

Đây là **mảnh code**, cần xử lý `InterruptedException`, logging và tình huống executor dùng chung.

Vì sao thứ tự này hợp lý?
- Nếu shutdown executor trước khi server ngừng gửi HTTP tasks, server vẫn có thể submit vào pool đã shutdown; task bị reject/drop tùy policy.
- `shutdown()` chỉ ngừng nhận tasks mới, **không interrupt** các tasks đã chạy.
- `awaitTermination` chờ các tasks đã nhận kết thúc trong timeout riêng.
- `shutdownNow()` chỉ best-effort interrupt; nó không thể đảm bảo một blocking I/O/DB operation bất kỳ sẽ dừng ngay.
- Nếu pool được chia sẻ với component khác, xác định ownership trước khi shutdown.

Trong ví dụ chính, `server.stop(0)` trong `finally` là cleanup bảo hiểm, còn `stop(2)` minh họa graceful logic. Ở ứng dụng thực, xây **một lifecycle coordinator** rõ ràng; không gọi stop nhiều lần như một phương pháp thay đổi deadline.

## 15. Graceful shutdown theo vòng đời ứng dụng

Một shutdown plan ở dịch vụ có load balancer:

```text
Nhận signal shutdown
      │
      ├─ readiness=false / thông báo đang drain
      ├─ LB/proxy giảm requests mới tới instance
      ├─ hạn chế công việc mới theo app policy (503 nếu cần)
      ├─ stop accepting new exchanges
      │     server.stop(graceSeconds)
      ├─ chờ current exchanges hoàn tất trong grace
      ├─ đóng TCP connections còn mở sau grace hoặc khi xong
      ├─ executor.shutdown()
      ├─ executor.awaitTermination(...)
      ├─ executor.shutdownNow() nếu cần, best effort
      └─ đóng DB/HTTP clients/background workers/temp files
```

Giai đoạn **drain trước stop** có thể giảm requests mới vào lúc listener vừa đóng. Nhưng không có guarantee mọi request được phục vụ: grace period hữu hạn, client mạng yếu và downstream I/O có thể vượt deadline.

Một handler có thể gửi `202 Accepted` rồi giao công việc cho **background executor**. Exchange của nó đã kết thúc, nên `stop(delay)` **không tự chờ background job** đó. Phải có lifecycle và data durability riêng cho queue/job.

Nếu handler đã commit DB transaction nhưng client mất connection trước khi nhận 200, client có thể retry và tạo side effects lặp. Thiết kế idempotency keys/transaction IDs; graceful stop không tạo exactly-once semantics.

## 16. Timeout và interrupt không được giải quyết chỉ bằng stop

Một handler có thể block ở:
- Đọc request body từ client rất chậm.
- Gọi HTTP service upstream hoặc database.
- Ghi response tới client chậm nhận dữ liệu.
- Chờ lock/queue/latch.
- Truy cập filesystem.

`stop(5)` đóng TCP connections sau cửa sổ chờ, **không tự hủy mọi business operation** đang block ở DB/file hoặc một executor khác. Dùng request deadline, upstream connect/read timeout, DB statement timeout, max-body limit và cancellation policy.

Khi task bị interrupt:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    exchange.close();
    return;
} finally {
    releasePermitIfOwned();
}
```

Đây là **mảnh code**, `blockingOperation` và `releasePermitIfOwned` là hàm ứng dụng giả định. Chỉ release permit **đã acquire**, không release tràn. Interrupt thường là **yêu cầu hợp tác**, không phải lệnh ép dừng mọi network/DB operation. Không báo HTTP 200 nếu task đã bị hủy trước khi hoàn tất nghiệp vụ.

## 17. Đóng HttpExchange và response stream

Trong `HttpHandler`, resource ownership rõ ràng:

```java
server.createContext("/ping", exchange -> {
    try {
        byte[] bytes = "pong".getBytes(StandardCharsets.UTF_8);
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
```

Đây là **mảnh code** cần imports và biến `server`. Khi có error trước khi gửi headers, handler còn có thể chọn status thích hợp. Nếu đã `sendResponseHeaders(200,...)` và bắt đầu body mà ghi bị lỗi, **không thể sửa status đã gửi thành 500**.

`sendResponseHeaders(code, responseLength)` có semantics:
- `responseLength > 0`: ứng dụng phải ghi **đúng số bytes** đã khai báo.
- `responseLength == 0`: kích hoạt chunked response encoding, body có thể dài tùy ý theo handler.
- `responseLength <= -1`: response không có body.
- `HEAD`, `204`, `304` cần tuân thủ HTTP semantics không gửi body phù hợp.

Đóng output bằng try-with-resources giúp kết thúc response stream khi xong. `exchange.close()` kết thúc exchange; không tái sử dụng exchange object.

## 18. Giới hạn request body là lớp khác với semaphore

Dù pool chỉ có 2 workers, một request có thể gửi body dài hàng gigabyte. Cần chặn **số bytes thật được đọc**, không tin `Content-Length` từ client sẽ luôn đúng. Với max 8 bytes, đọc **tối đa 9 bytes** rồi quyết định:

```java
final int maxBytes = 8;
byte[] body;
try (InputStream input = exchange.getRequestBody()) {
    body = input.readNBytes(maxBytes + 1);
}
if (body.length > maxBytes) {
    reply(exchange, 413, "too-large");
    return;
}
process(body);
```

Đây là **mảnh code**, `reply`/`process` do ứng dụng định nghĩa. Với payload lớn, dùng streaming loop, counted bytes và disk quotas thay vì cấp phát byte array lớn. Phải kiểm tra khả năng overflow nếu `maxBytes` gần `Integer.MAX_VALUE`.

Đọc không hết body rồi đóng request stream có thể khiến HTTP connection không được tái sử dụng; đây là đánh đổi có thể cần thiết khi từ chối upload quá lớn. Một client đang gửi body lớn có thể không nhận được status 413 hoàn chỉnh nếu connection bị đóng; test với client thực.

## 19. Chương trình Java 17+ chạy được: giới hạn body và trả 413

Lưu file **`BoundedRequestBodyDemo.java`**. Server đọc tối đa 9 bytes; body 6 bytes nhận `200`, body 12 bytes nhận `413`. Cả server và client chạy trên loopback, không cần Internet.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedRequestBodyDemo {
    private static void reply(HttpExchange exchange, int code, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(code, bytes.length);
        try (var out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        final int maxBodyBytes = 8;
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.CallerRunsPolicy());
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 8);
        server.setExecutor(executor);
        server.createContext("/upload", exchange -> {
            try {
                if (!"POST".equals(exchange.getRequestMethod())) {
                    exchange.getResponseHeaders().add("Allow", "POST");
                    reply(exchange, 405, "method-not-allowed");
                    return;
                }
                byte[] body;
                try (InputStream input = exchange.getRequestBody()) {
                    body = input.readNBytes(maxBodyBytes + 1);
                }
                if (body.length > maxBodyBytes) {
                    reply(exchange, 413, "too-large");
                } else {
                    reply(exchange, 200, "accepted=" + body.length);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/upload");
            HttpClient client = HttpClient.newHttpClient();
            for (String value : new String[]{"ABCDEF", "ABCDEFGHIJKL"}) {
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(5))
                        .POST(HttpRequest.BodyPublishers.ofString(value))
                        .build();
                HttpResponse<String> response = client.send(request,
                        HttpResponse.BodyHandlers.ofString());
                System.out.println("bytes=" + value.length()
                        + " status=" + response.statusCode()
                        + " body=" + response.body());
            }
        } finally {
            server.stop(1);
            executor.shutdown();
            if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Lệnh:

```bash
javac BoundedRequestBodyDemo.java
java BoundedRequestBodyDemo
```

Stdout đã kiểm chứng:

```text
bytes=6 status=200 body=accepted=6
bytes=12 status=413 body=too-large
```

Các chuỗi request trong demo chỉ chứa ASCII nên số ký tự `String.length()` trùng số bytes UTF-8. Với tiếng Việt hoặc emoji, **không** dùng ký tự đếm từ String để làm max request bytes; tính số bytes thực sự đọc.

**Giới hạn demo:** không có tổng time budget cho slow-client và không hỗ trợ authentication; production phải bảo vệ thêm tại ingress/TLS/rate limit và không dùng HTTP plaintext cho dữ liệu nhạy cảm.

## 20. Quan sát executor: metrics khác điều kiện atomic

Các phép đo hữu ích:
- `pool.getActiveCount()`: ước tính số workers đang chạy tasks.
- `pool.getPoolSize()`: kích thước pool tại thời điểm đo.
- `pool.getQueue().size()`: số tasks đang chờ.
- `pool.getCompletedTaskCount()`: số tasks đã hoàn tất gần đúng.
- `permits.availablePermits()`: permits còn cho critical section.
- Status count cho `200`/`413`/`429`/`503`, request latency, downstream timeout, response failures.
- Connection count, backlog pressure, CPU, heap, GC, file descriptors.
- Time-to-first-byte, tổng thời gian exchange, thời gian shutdown.

Ví dụ metric:

```java
System.out.printf(
        "pool=%d active=%d queued=%d permits=%d%n",
        workers.getPoolSize(),
        workers.getActiveCount(),
        workers.getQueue().size(),
        activeRequests.availablePermits());
```

Đây là **mảnh code**, giả định `workers` và `activeRequests` có sẵn. Các kết quả là **snapshot**, không phải atomic admission decision. Không dùng điều kiện `getQueue().size() < 4` rồi khẳng định task tiếp theo sẽ được enqueue: thread khác có thể làm queue đầy ngay sau check.

## 21. Thread safety của HttpHandler

Khi có executor nhiều threads, cùng một handler có thể xử lý nhiều `HttpExchange` đồng thời. Vì vậy:
- State của mỗi request nên lưu ở local variables hoặc request context riêng.
- Không ghi mutable field chung như `currentUser`/`currentBody` trong singleton handler.
- Dùng `AtomicLong`, `LongAdder` hoặc thread-safe data structures cho shared counters.
- Permit acquire/release phải có `finally`; tránh release nhiều hơn acquire.
- Không chia sẻ `HttpExchange` giữa requests hoặc viết vào exchange đã đóng.
- Gọi downstream services với timeout và cancellation policy rõ ràng.
- Tránh synchronized lock dài hoặc blocking trong vùng ảnh hưởng nhiều handlers.

Phản ví dụ:

```java
class BadHandler implements HttpHandler {
    private String currentUser;

    public void handle(HttpExchange exchange) throws IOException {
        currentUser = exchange.getRequestHeaders().getFirst("X-User");
        // Request khác có thể thay currentUser khi handler này còn chạy.
        exchange.close();
    }
}
```

Đây là **mảnh code phản ví dụ**; thiếu response logic và không dùng header người dùng tự khai làm danh tính đáng tin. Để xác thực, dùng auth middleware/tokens/cert và authorization rules của ứng dụng.

## 22. Kiểm thử concurrency, quá tải và shutdown

Ma trận kiểm thử:

| Test | Kết quả cần kiểm chứng |
| --- | --- |
| Gắn executor trước start | Handler tasks được dispatch |
| Gắn executor sau start | Ném `IllegalStateException` |
| Không gắn executor | Server vẫn hoạt động; không suy mặc định có pool lớn |
| Một permit đang bị giữ | Handler thứ hai được dispatch có thể trả 503 |
| Pool và queue đầy | Rejection policy xảy ra, không giả định HTTP 503 |
| CallerRunsPolicy | Có nguy cơ handler chạy trên dispatcher |
| `stop(2)` + handler được release | Handler có cơ hội hoàn tất trước khi stop kết thúc |
| `stop(0)` + handler đang chạy | Không cam kết response thành công |
| `stop(-1)` | `IllegalArgumentException` |
| `start` sau stop | Instance không được tái sử dụng |
| Executor còn hoạt động sau server stop | Lifecycle shutdown executor cần quản lý riêng |
| Request body 6 bytes, limit 8 | 200 nếu handler cho phép |
| Request body 12 bytes, limit 8 | 413 nếu client nhận response |
| Slow upload/download | Deadlines/bounded connections có hiệu lực |
| Nhiều requests/giây, handler rất nhanh | Rate limit tách khỏi concurrency limit |
| Backend ghi DB rồi connection mất | Idempotency/transaction state được xử lý |
| HTTP handler ném exception | Exchange/permit được cleanup trong finally |

**Test với latch thay vì đoán thời gian:** `CountDownLatch` cho phép server giữ request 1 trong critical section; main thread chỉ gửi request 2 sau khi latch báo request 1 đã vào. `Thread.sleep(20)` không bảo đảm request order trên máy CI chậm hoặc khi JVM pause.

## 23. Các lỗi thường gặp

1. **Nhầm backlog với số request đồng thời.** Backlog chỉ quản lý pending TCP connections.
2. **Gọi `setExecutor` sau `start()`.** API ném `IllegalStateException`.
3. **Giả định default executor có nhiều worker.** Không đúng theo mô tả Java 17.
4. **Dùng `newFixedThreadPool` rồi nghĩ queue bounded.** Queue có thể tăng vô hạn.
5. **Dùng CallerRunsPolicy mà không đo dispatcher latency.** Caller thread có thể chạy handler blocking.
6. **Dùng AbortPolicy và chờ tự có 503.** Không có bảo đảm.
7. **Dùng `Semaphore.acquire()` để đợi lâu trong handler.** Có thể chiếm workers gây starvation.
8. **Acquire permit không release trong finally.** Mất permit gây overload giả vĩnh viễn.
9. **Đặt permit sau khi đọc body không giới hạn.** Lọc quá muộn, vẫn có thể OOM.
10. **Tin Content-Length tuyệt đối.** Phải giới hạn bytes thực đọc.
11. **Cho rằng stop(2) tính 2 milliseconds.** Sai, `delay` tính bằng giây.
12. **Cho rằng stop(5) luôn ngủ đủ 5 giây.** Sai, có thể về sớm nếu handlers xong.
13. **Stop(0) nhưng hy vọng mọi request hoàn tất.** Không có graceful window.
14. **Cố restart instance sau stop.** Không hỗ trợ.
15. **Quên shutdown executor.** Worker threads/resources có thể giữ tiến trình.
16. **Shutdown executor trước stop listener.** Có thể reject tasks HTTP mới.
17. **Tin shutdownNow luôn chấm dứt ngay DB query.** Interrupt là best effort.
18. **Gọi stop từ handler đang chờ chính stop.** Có nguy cơ self-wait và delay không cần thiết.
19. **Quên đóng HttpExchange/OutputStream.** Resource leaks, response incomplete.
20. **Gửi 200 trước khi kiểm tra body.** Không thể đổi thành 413 sau khi response headers đã commit.
21. **Nhầm rate limit và concurrency limit.** Requests/s khác active jobs.
22. **Xem completion HTTP là hoàn thành background task.** Job ngoài handler có lifecycle riêng.
23. **Đánh giá readiness bằng đúng một metric activeCount.** Snapshot, không phải toàn bộ health.
24. **Retry POST sau connection reset vô hạn.** Có thể tạo tác động nghiệp vụ lặp.
25. **Dùng demo HTTP plaintext làm public server.** Cần TLS, auth, gateway và hardening.

## 24. Tự kiểm tra kiến thức

**Câu 1.** `setExecutor` phải được gọi lúc nào?  
**Đáp án:** Trước `start()`; sau start sẽ ném `IllegalStateException`.

**Câu 2.** Backlog=16 và pool=2 có nghĩa cùng lúc xử lý 16 requests không?  
**Đáp án:** Không; backlog cho pending TCP connections, pool cho worker tasks.

**Câu 3.** `CallerRunsPolicy` có bảo đảm chỉ 2 handlers chạy không?  
**Đáp án:** Không; task có thể chạy trên thread gọi executor.execute, như dispatcher.

**Câu 4.** Vì sao một bounded queue chưa đủ để bảo đảm client nhận 503?  
**Đáp án:** Queue rejection có thể xảy ra trước khi handler được chạy; rejection handler không tự sở hữu HttpExchange và không có bảo đảm gửi 503.

**Câu 5.** `Semaphore.tryAcquire()` không có permit thì sao?  
**Đáp án:** Trả false ngay, handler có thể gửi 503 mà không block chờ.

**Câu 6.** `stop(5)` nghĩa là gì?  
**Đáp án:** Dừng listener, đợi current exchange handlers hoàn thành tối đa khoảng 5 giây rồi đóng TCP connections.

**Câu 7.** `stop(0)` khác stop(5) thế nào?  
**Đáp án:** Không có thời gian chờ graceful, các exchange đang xử lý có thể bị cắt.

**Câu 8.** Sau stop có thể gọi start lại cùng instance không?  
**Đáp án:** Không, phải tạo HttpServer mới.

**Câu 9.** Vì sao phải shutdown executor sau stop?  
**Đáp án:** Executor do ứng dụng tạo có lifecycle riêng, không được coi là tự shutdown cùng HttpServer.

**Câu 10.** Body 12 bytes, hạn mức 8 bytes, đọc `readNBytes(9)` giúp gì?  
**Đáp án:** Nhận tối đa 9 bytes để phát hiện vượt hạn mức mà không gom vô hạn body vào memory.

**Câu 11.** Rate limit 100 req/s có giống semaphore 100 permits không?  
**Đáp án:** Không, số requests mỗi giây khác số concurrent operations.

**Câu 12.** Nếu handler trả 202 rồi đẩy background job, stop(5) có đợi job xong không?  
**Đáp án:** Không tự động; exchange đã kết thúc, job cần lifecycle riêng.

**Câu 13.** Client bị reset sau khi gửi POST có chứng minh server chưa ghi DB không?  
**Đáp án:** Không; side effect có thể đã thực hiện trước khi response bị cắt.

**Câu 14.** Vì sao phải đọc/đóng request/response streams rõ ràng?  
**Đáp án:** Để giải phóng tài nguyên, tránh giữ connection/handler vô hạn và hoàn tất HTTP framing đúng.

**Câu 15.** Metrics `workers.getActiveCount()` có phù hợp làm điều kiện atomic để nhận request mới không?  
**Đáp án:** Không. Đây là snapshot gần đúng; dùng primitive admission như semaphore hoặc ingress policy.

## 25. Checklist áp dụng

**Khởi tạo:** Bind đúng interface, chọn backlog có lý do, tạo contexts, xây bounded executor và rejection policy có phân tích, gọi `setExecutor` **trước `start`**, chuẩn bị TLS/auth/timeouts/metrics khi phục vụ ngoài loopback.

**Đang chạy:** Giới hạn request rate/active work/queue/body bytes, trả 503 hoặc 429 hoặc 413 theo nguyên nhân, không block workers vô hạn, đóng `HttpExchange`, có deadline downstream, log status/latency/queue depth và bảo vệ dữ liệu nhạy cảm.

**Dừng:** Thông báo draining/readiness false khi có LB, stop server với `delay` **giây** từ lifecycle thread, hiểu requests có thể bị cắt nếu quá deadline, shutdown executor do ứng dụng sở hữu, chờ termination rồi best-effort interrupt, dừng background jobs và đóng dependencies riêng. Muốn chạy tiếp phải tạo HttpServer mới.

**Tóm tắt:** `setExecutor` quyết định **nơi handler thực thi**; queue/backlog/permit quyết định **tầng nào đang giữ hoặc từ chối công việc**; `stop(delay)` cho **cửa sổ kết thúc HTTP exchanges** rồi đóng listener/connections, không tự thay thế việc dừng executor hay xử lý side effects nghiệp vụ.

## 26. Tài liệu chuẩn và tham khảo

- Oracle Java SE 17 `HttpServer` — `create`, `setExecutor`, `start`, `stop(int delay)`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Oracle Java SE 17 `HttpExchange` — request/response streams, `sendResponseHeaders`, `close`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- Oracle Java SE 17 `HttpHandler` — `handle(HttpExchange)`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html
- Oracle Java SE 17 `ThreadPoolExecutor` — sizing, queues, rejection policies: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java SE 17 `CallerRunsPolicy` — chạy task trên caller thread, discard nếu shutdown: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html
- Oracle Java SE 17 `ArrayBlockingQueue` — bounded queue: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- Oracle Java SE 17 `Semaphore` — `tryAcquire` và `release`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html
- Oracle Java SE 17 `ExecutorService` — `shutdown`, `awaitTermination`, `shutdownNow`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java SE 17 `CountDownLatch` — test concurrency có điều kiện: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Oracle Java SE 17 `ServerSocket` — backlog semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- RFC 9110 — HTTP Semantics, 413/429/503/Retry-After: https://www.rfc-editor.org/rfc/rfc9110

# Hủy yêu cầu, ngắt send đồng bộ và khả năng máy chủ đã xử lý yêu cầu (Java 17+)

**Hủy một HTTP request ở client không đồng nghĩa server đã hủy công việc nghiệp vụ.** Khi thread đang gọi `HttpClient.send(...)` bị interrupt hoặc khi future từ `HttpClient.sendAsync(...)` bị `cancel(true)`, Java 17 HTTP client mặc định **cố gắng** hủy trao đổi HTTP và giải phóng tài nguyên. Nhưng request có thể **đã được gửi**, server có thể **đang xử lý** hoặc **đã commit** dù caller không nhận được response.

Một lệnh `POST /orders` có thể đã tạo đơn thành công, nhưng client chỉ thấy `InterruptedException`, `CancellationException`, `IOException` hoặc `HttpTimeoutException`. Nếu client hiểu nhầm exception là “server chưa xử lý” rồi gửi lại POST, có thể tạo **hai đơn hàng**. Bài thuộc **HTTP bất đồng bộ** của **Java Advance - networking**, tập trung vào hợp đồng Java 17 và thiết kế xử lý kết quả không chắc chắn (*ambiguous outcome*) với retry/idempotency.

## 1. Phân biệt bốn đối tượng bị “hủy”

Một exchange HTTP đi qua nhiều tầng:

```text
CALLER THREAD / TASK
        |
        | send(request) hoặc sendAsync(request)
        v
CLIENT HTTP EXCHANGE
        |
        | DNS / connect / TLS / gửi headers + body
        v
NETWORK / PROXY / LOAD BALANCER
        |
        v
SERVER HTTP HANDLER
        |
        | validate -> execute -> DB commit / publish message
        v
SERVER RESPONSE
        |
        v
CLIENT READS RESPONSE -> caller quan sát kết quả
```

Một từ “cancel” có thể nói về **bốn việc khác nhau**:

1. **Dừng chờ ở caller:** thread thoát khỏi `send`; future bị đánh dấu cancelled; UI không còn hiển thị spinner.
2. **Cố hủy HTTP exchange trong client:** client implementation ngừng gửi/nhận, hoặc cố giải phóng network resources. Không bảo đảm hành động được áp dụng ngay.
3. **Đóng TCP connection hoặc reset HTTP/2 stream:** server có thể nhận tín hiệu disconnect, nhưng reset ở tầng vận chuyển không phải rollback.
4. **Hủy tác vụ nghiệp vụ ở server:** chỉ khi server/protocol **có cơ chế hủy riêng**, đúng thời điểm và đủ quyền để ngừng/compensate. Không tự động suy ra từ ba hành vi trên.

**Câu cần ghi nhớ:** `future.isCancelled() == true` mô tả trạng thái của **future cục bộ**, không phải trạng thái của transaction ở server.

## 2. Tại sao mất response khiến kết quả không chắc chắn?

Giả sử client gửi một POST thay đổi dữ liệu:

```text
CLIENT                                    SERVER
  |-- POST /orders ------------------------->|
  |                                          | validate
  |                                          | commit order #A
  |<-------- response bị mất ---X-------------|
  |
  |-- timeout / InterruptedException
  |
  |-- retry POST không có key -------------->|
  |                                          | commit order #B
  |
  |                                 Hai logical side effects!
```

Có ít nhất ba cửa sổ race:

- **Trước khi request tới server:** request có thể chưa được gửi, nhưng exception ở client **không tự chứng minh** điều đó. Network I/O có thể đã được giao cho thread khác.
- **Sau khi server đã nhận, trước khi commit:** server có thể tiếp tục hoặc ngừng tùy thiết kế; client thường không biết mốc chính xác.
- **Sau khi server commit, trước khi response đến client:** server đã thành công, nhưng client vẫn có thể thấy timeout, interrupt hoặc connection reset.

Không có thứ tự atomically shared giữa “server commit” và “client nhận response”. Đó là bài toán hệ phân tán, **không phải bug riêng của Java**.

**Không phân loại “client không nhận 2xx” thành “business operation FAILED” một cách máy móc.** Trạng thái đúng có thể là `UNKNOWN_OUTCOME` và cần tra soát.

## 3. `send` đồng bộ có thể bị interrupt như thế nào?

Chữ ký API Java 17:

```java
// Chữ ký rút gọn để minh họa; không phải class chạy độc lập.
<T> HttpResponse<T> send(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler)
        throws IOException, InterruptedException;
```

`send` chặn **thread gọi** trong khi gửi request/nhận response theo handler. Theo Javadoc Java 17, nếu operation bị interrupt, implementation `HttpClient` mặc định **thử hủy HTTP exchange**, ném `InterruptedException`; **không bảo đảm** chính xác khi nào việc hủy được xử lý.

Javadoc còn nói rõ:

- Request **vẫn có thể đã được gửi đến server** vì việc gửi đã bắt đầu bất đồng bộ trong một thread khác.
- Server **có thể đã bắt đầu xử lý**; thậm chí side effect đã được commit trước lúc client nhận interrupt.
- Network resources có thể chỉ được giải phóng **bất đồng bộ sau đó**.
- Với HTTP/1.1, cố hủy có thể khiến connection nền bị **đóng đột ngột**.
- Với HTTP/2, cố hủy có thể **reset stream** hoặc, trong một số tình huống, đóng cả connection.

Bởi vậy, `InterruptedException` là tín hiệu về **luồng điều khiển của caller**, không phải chứng cứ server rollback.

Nguồn: [JDK 17 HttpClient.send](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html).

## 4. Khôi phục interrupt flag và tôn trọng vòng đời task

Mẫu xử lý trong một Java service:

```java
// Snippet minh họa: client, request, processResponse đã tồn tại.
try {
    HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());
    processResponse(response);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Không retry POST mù quáng: remote result có thể UNKNOWN.
    throw ex;
} catch (IOException ex) {
    // Transport fail không đồng nghĩa operation chưa commit.
    throw ex;
}
```

Điểm kỹ thuật:

- `Thread.interrupt()` là **cooperative cancellation** cho thread local, không phải HTTP request gửi tới server để undo transaction.
- Blocking operation ném `InterruptedException` thường đã xóa flag. **Restore bằng `Thread.currentThread().interrupt()`** giúp tầng quản lý task phát hiện yêu cầu dừng.
- Đừng nuốt exception rồi tiếp tục gửi request khác trong loop vô hạn.
- Nếu tầng trên không khai báo `throws InterruptedException`, cần map cancellation ra một kết quả/cancellation exception đúng chính sách, không làm mất cờ interrupt.
- Nếu request có side effect, log operation ID và `UNKNOWN_OUTCOME` thay vì khẳng định request chưa thành công.

Một `ExecutorService.shutdownNow()` có thể interrupt task đang `send`, nhưng cũng **không** bảo đảm server đã dừng xử lý POST. Đóng ứng dụng nên có cơ chế reconciliations cho các operation còn chưa biết kết quả.

## 5. `sendAsync` và `CompletableFuture.cancel(true)`

Ví dụ asynchronous:

```java
// Snippet minh họa: cần tạo client và request trước.
CompletableFuture<HttpResponse<String>> original =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString());

// Khi policy yêu cầu ngừng exchange:
boolean markedCancelled = original.cancel(true);
```

Theo `HttpClient` Java 17, implementation mặc định trả **cancelable CompletableFuture**. Gọi `cancel(true)` trên future chưa completed sẽ **cố hủy exchange** để giải phóng resources sớm. Điều này khác với việc chỉ cập nhật một flag UI.

Tuy nhiên:

1. `markedCancelled == true` chỉ chứng nhận **future được đánh dấu cancelled**, không nói server đã rollback.
2. Không bảo đảm chính xác thời điểm network cancellation được thực hiện; server có thể đã nhận/giao transaction cho DB.
3. Nếu future đã completed, `cancel(true)` có thể trả `false`; kết quả đã có hoặc đã lỗi trước đó.
4. Cancel cũng có thể làm underlying HTTP/1.1 connection bị đóng, hoặc HTTP/2 stream reset; đó không phải business cancellation.
5. Các dependent stages của future bị cancel có thể hoàn tất exceptionally; đừng dùng một callback chạy muộn để ghi đè business state mới.

**Phân biệt với `CompletableFuture` thường:** `CompletableFuture.cancel(boolean)` nói chung hoàn tất future bằng `CancellationException` và tham số `mayInterruptIfRunning` không điều khiển thread computation. Default `HttpClient` có hành vi đặc biệt **cố cancel HTTP exchange khi gọi `cancel(true)`**; không nhầm hai hợp đồng.

## 6. Vì sao không dùng `cancel(false)` như một “nút dừng HTTP”?

Java 17 `HttpClient` nêu cụ thể **`cancel(true)`** cho việc thử cancel exchange. Không suy luận rằng `cancel(false)` trên future HTTP chắc chắn có cùng tác dụng giải phóng network resources. Với `CompletableFuture` chuẩn, dù true hay false, `cancel` có thể chỉ tác động lên future state.

Một anti-pattern:

```java
// Minh họa lỗi tư duy: đừng dùng result của cancel như business ACK.
boolean cancelled = original.cancel(true);
if (cancelled) {
    // SAI: ghi vào DB rằng "order chắc chắn không được tạo".
}
```

Nếu kết quả có thể tạo side effect, trạng thái sau cancel vẫn có thể là `UNKNOWN`, cần tra cứu theo operation ID hoặc idempotency key.

Khi có cả `original` và `original.thenApply(...)`, tránh làm mất reference tới `original`. Chỉ cancel một derived future không nhất thiết thực thi đúng chính sách hủy ở mọi stage/provider trong ứng dụng phức tạp. Đảm bảo cơ chế **propagate cancellation tới HTTP exchange gốc** và xử lý body/subscription tương ứng.

## 7. HTTP/1.1 và HTTP/2: hủy cấp transport, không hủy business

| Giao thức | Cancellation có thể ảnh hưởng thế nào? | Điều vẫn chưa được chứng minh |
| --- | --- | --- |
| HTTP/1.1 | Đóng TCP connection, ngừng đọc/ghi exchange | Server chưa nhận POST, chưa commit |
| HTTP/2 | Reset một stream; đôi khi đóng connection khi I/O nền yêu cầu | Server đã dừng handler, rollback DB |
| Cả hai | Future hoặc thread ở client dừng chờ | Downstream queue/payment đã được thu hồi |

Ngay cả khi server nhận TCP disconnect, handler có thể vẫn tiếp tục vì:

- DB transaction đã commit trước khi socket lỗi.
- Job đã được đưa vào queue để worker khác xử lý.
- Service cần hoàn tất một bước để giữ invariant dữ liệu.
- Load balancer/proxy đã forward request từ trước.
- Server không có cơ chế dừng công việc nghiệp vụ hoặc không thể undo external side effect.

`RST_STREAM` là tín hiệu HTTP/2, **không phải lệnh `ROLLBACK` SQL**. Nếu muốn hủy job dài hạn, protocol phải có cancellation endpoint và state machine riêng.

## 8. Java 17 runnable demo 1 — server đã làm việc rồi client mới interrupt

Tệp **`InterruptedSendDemo.java`** dùng `HttpServer` chuẩn JDK (module `jdk.httpserver`), bind `127.0.0.1` trên port tự cấp. Server đọc body POST và tăng bộ đếm effect rồi **giữ response chưa gửi** bằng `CountDownLatch`. Client gọi `send` trên một thread, main đợi server xác nhận đã xử lý **trước** khi interrupt thread ấy.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class InterruptedSendDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[]{127, 0, 0, 1});
        CountDownLatch serverReceived = new CountDownLatch(1);
        CountDownLatch releaseResponse = new CountDownLatch(1);
        AtomicInteger applied = new AtomicInteger();
        AtomicBoolean caughtInterrupt = new AtomicBoolean();
        AtomicBoolean flagRestored = new AtomicBoolean();
        AtomicReference<String> unexpected = new AtomicReference<>();

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService serverWorkers = Executors.newFixedThreadPool(2);
        server.setExecutor(serverWorkers);
        server.createContext("/commit", exchange -> {
            try {
                try (InputStream input = exchange.getRequestBody()) {
                    input.transferTo(OutputStream.nullOutputStream());
                }
                applied.incrementAndGet();
                serverReceived.countDown();
                try {
                    releaseResponse.await(10, TimeUnit.SECONDS);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                byte[] reply = "OK".getBytes(StandardCharsets.UTF_8);
                try {
                    exchange.sendResponseHeaders(200, reply.length);
                    try (OutputStream output = exchange.getResponseBody()) {
                        output.write(reply);
                    }
                } catch (java.io.IOException clientGone) {
                    // Client cancellation can break response delivery.
                }
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/commit");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(15))
                    .POST(HttpRequest.BodyPublishers.ofString("buy=1"))
                    .build();
            Thread sender = new Thread(() -> {
                try {
                    client.send(request,
                            HttpResponse.BodyHandlers.ofString());
                    unexpected.set("send returned normally");
                } catch (InterruptedException ex) {
                    caughtInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    flagRestored.set(Thread.currentThread().isInterrupted());
                } catch (Exception ex) {
                    unexpected.set(ex.getClass().getSimpleName());
                }
            }, "blocking-http-sender");
            sender.start();
            if (!serverReceived.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server did not get POST");
            }
            sender.interrupt();
            sender.join(5_000);
            if (sender.isAlive()) {
                throw new IllegalStateException("Sender did not stop");
            }
            if (unexpected.get() != null) {
                throw new IllegalStateException(unexpected.get());
            }
            System.out.println("Server received POST: true");
            System.out.println("send threw InterruptedException: "
                    + caughtInterrupt.get());
            System.out.println("Interrupt flag restored: "
                    + flagRestored.get());
            System.out.println("Server actions: " + applied.get());
        } finally {
            releaseResponse.countDown();
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 InterruptedSendDemo.java
java --add-modules jdk.httpserver InterruptedSendDemo
```

Stdout đã kiểm thử:

```text
Server received POST: true
send threw InterruptedException: true
Interrupt flag restored: true
Server actions: 1
```

Giải thích:

1. `serverReceived.countDown()` diễn ra **sau** khi server đã đọc request và `applied.incrementAndGet()`; vì vậy main không interrupt trước khi server effect được ghi nhận.
2. Server giữ phản hồi chưa được gửi bằng `releaseResponse.await`; sender bị chặn trong `send`.
3. `sender.interrupt()` khiến `send` ném `InterruptedException` trên default JDK HTTP client. Catch khôi phục interrupt flag.
4. `Server actions: 1` chứng minh **server đã làm việc** dù client đã dừng chờ. Effect ở đây chỉ là bộ đếm trong-memory, **không phải DB commit production**.
5. Server có thể thấy `IOException` khi cố ghi response vào connection bị hủy. Lỗi response **không làm undo effect đã xảy ra**.
6. `finally` nhả latch, đóng server và executor. Demo có thời hạn chờ để tránh deadlock khi môi trường lỗi.

Đây là một test **đồng bộ hóa sự kiện có chủ đích**, không phải benchmark về độ nhanh của interrupt. Nó minh họa trường hợp dangerous-but-valid của hợp đồng Java 17.

## 9. Java 17 runnable demo 2 — cancel future, retry cùng key và một effect

Tệp **`CancelAndRetryDemo.java`** dùng `sendAsync` gửi POST với header `Idempotency-Key: demo-order-42`. Server ghi nhận key và tăng effect **khi lần đầu thấy key**. Nó chặn response đầu tiên cho đến khi client đã gọi `cancel(true)`, sau đó client **chủ động retry** cùng logical operation bằng **cùng idempotency key**.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CancelAndRetryDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[]{127, 0, 0, 1});
        Set<String> processedKeys = ConcurrentHashMap.newKeySet();
        AtomicInteger requests = new AtomicInteger();
        AtomicInteger effects = new AtomicInteger();
        CountDownLatch firstCommitted = new CountDownLatch(1);
        CountDownLatch releaseFirstResponse = new CountDownLatch(1);

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService serverWorkers = Executors.newFixedThreadPool(4);
        server.setExecutor(serverWorkers);
        server.createContext("/orders", exchange -> {
            try {
                try (InputStream input = exchange.getRequestBody()) {
                    input.transferTo(OutputStream.nullOutputStream());
                }
                int attempt = requests.incrementAndGet();
                String key = exchange.getRequestHeaders()
                        .getFirst("Idempotency-Key");
                if (key != null && processedKeys.add(key)) {
                    effects.incrementAndGet();
                }
                if (attempt == 1) {
                    firstCommitted.countDown();
                    try {
                        releaseFirstResponse.await(
                                10, TimeUnit.SECONDS);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                byte[] reply = "ORDER-OK".getBytes(
                        StandardCharsets.UTF_8);
                try {
                    exchange.sendResponseHeaders(200, reply.length);
                    try (OutputStream out = exchange.getResponseBody()) {
                        out.write(reply);
                    }
                } catch (java.io.IOException clientGone) {
                    // Cancelled clients may not read their responses.
                }
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            String endpoint = "http://127.0.0.1:"
                    + server.getAddress().getPort() + "/orders";
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(
                    URI.create(endpoint))
                    .header("Idempotency-Key", "demo-order-42")
                    .timeout(Duration.ofSeconds(15))
                    .POST(HttpRequest.BodyPublishers.ofString("item=1"))
                    .build();

            CompletableFuture<HttpResponse<String>> first =
                    client.sendAsync(request,
                            HttpResponse.BodyHandlers.ofString());
            if (!firstCommitted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server did not commit");
            }
            boolean cancelled = first.cancel(true);
            HttpResponse<String> retry = client.send(request,
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("First request reached server: true");
            System.out.println("Future cancelled: " + cancelled);
            System.out.println("Retry HTTP status: "
                    + retry.statusCode());
            System.out.println("Requests received: " + requests.get());
            System.out.println("Unique effects: " + effects.get());
        } finally {
            releaseFirstResponse.countDown();
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 CancelAndRetryDemo.java
java --add-modules jdk.httpserver CancelAndRetryDemo
```

Stdout đã kiểm thử:

```text
First request reached server: true
Future cancelled: true
Retry HTTP status: 200
Requests received: 2
Unique effects: 1
```

Giải thích:

1. `firstCommitted.await` bảo đảm server đã tăng effect **trước khi client cancel**. `cancel(true)` chỉ có thể cố ngừng exchange, không “xóa” tác vụ vừa xảy ra.
2. Server đếm **2 HTTP requests** vì client đã retry một lần.
3. Server đếm **1 logical effect** nhờ cùng idempotency key. Đây là **logic của server**, không phải Java client tự chống trùng.
4. `ConcurrentHashMap.newKeySet()` chỉ là demo tại **một JVM**. Nó không bền vững qua restart, không atomically gắn với DB write, không so sánh payload hash, không lưu result. Không dùng nó làm chiến lược exactly-once production.
5. Khi request đầu bị cancel, server có thể không ghi response được. Điều đó không ảnh hưởng khả năng xử lý request tiếp theo trên HTTP exchange khác.
6. `requests=2` không có nghĩa **2 TCP connections**; demo không đo pooling.

Tình huống này cho thấy hai cơ chế độc lập: **cancel ở client** và **dedup/idempotency ở server**.

## 10. Kết quả cần phân loại theo bằng chứng thực tế

| Client quan sát | Biết chắc điều gì? | Chưa thể kết luận gì? |
| --- | --- | --- |
| HTTP 2xx và body hợp lệ | API đã gửi response thành công theo contract | Những side effect ngoài contract đã hoàn tất mọi replica chưa |
| HTTP 4xx/5xx | Có response với status ấy | Một thao tác có thể đã commit trước lỗi tạo response |
| `InterruptedException` | Thread gọi `send` bị ngắt, client thử cancel | Server đã nhận/commit chưa |
| `CancellationException` | Future cancelled | Server đã dừng/rollback chưa |
| `HttpTimeoutException` | Không có response đúng hạn theo timeout contract | Remote operation có thể đã hoàn tất |
| `IOException`/reset | Transport gặp lỗi | Server đã thực hiện bao nhiêu bước |
| Không nhận status nhưng thấy request ID trong server ledger | Có thể tra trạng thái authoritative qua id | Không nên suy từ network exception đơn lẻ |

Nên thiết kế các trạng thái domain như `CONFIRMED_SUCCESS`, `CONFIRMED_REJECTION`, `UNKNOWN_OUTCOME` hay `RECONCILING`. Chúng được quyết định từ **API semantics và business ledger**, không chỉ từ loại Java exception.

Một server trả 500 sau khi DB commit **vẫn có thể đã tạo effect**; mã lỗi không luôn đồng nghĩa database rollback. Ngược lại một HTTP 200 có thể chỉ xác nhận job đã **accepted**, chưa hoàn tất nếu protocol là asynchronous job.

## 11. Timeout: connect, request, future waiting và business deadline

Ví dụ minh họa:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .POST(HttpRequest.BodyPublishers.ofString(payload))
        .build();
```

`uri` và `payload` chưa khai báo; snippet này không chạy độc lập.

- **`connectTimeout`** áp khi cần lập kết nối mới; không kiểm soát tổng thời gian xử lý request trên connection được reuse.
- **`HttpRequest.timeout`** là thời gian giới hạn nhận HTTP response theo API; khi vượt hạn, client có thể báo `HttpTimeoutException`. Server side effect vẫn có thể đã xảy ra.
- **`future.get(3, TimeUnit.SECONDS)`** khi hết hạn ném `TimeoutException` cho **thread đang đợi**, nhưng **không tự cancel** future/network exchange.
- **`CompletableFuture.orTimeout(...)`** theo hợp đồng của `CompletableFuture` sẽ hoàn tất future exceptionally khi hết thời gian. Đừng coi nó là bằng chứng network đã ngừng hoặc remote đã rollback; nếu policy yêu cầu ngắt exchange, giữ reference original future và quyết định `original.cancel(true)` phù hợp.
- **Business deadline** có thể bao trùm nhiều attempts, chờ queue, đọc body, reconcile. Đừng reset deadline vô hạn sau mỗi retry.

Khi sử dụng streaming handlers như `ofInputStream()` hoặc `ofPublisher()`, body có thể chưa được tiêu thụ hết khi `HttpResponse` trở nên sẵn sàng. Deadline cho **body streaming** cần ownership/cancel riêng; không đồng nhất timeout chờ HTTP response với thời gian hoàn tất toàn bộ business pipeline.

## 12. Hủy future thông thường không nhất thiết interrupt worker thread

Một khác biệt rất hay nhầm:

| Cách gọi | Ý nghĩa chính |
| --- | --- |
| `thread.interrupt()` trên thread đang chạy `HttpClient.send` | `send` có thể báo `InterruptedException`, default client thử hủy HTTP exchange |
| `sendAsync(...).cancel(true)` trên future JDK HTTP client | Future cancelled, default JDK implementation thử dừng exchange |
| `new CompletableFuture<>().cancel(true)` | `CompletableFuture` thông thường hoàn tất bằng `CancellationException`; không tự interrupt một computation thread |
| `future.get(timeout)` | Chỉ chờ tối đa timeout ở caller; không tự hủy exchange |
| `HttpRequest.timeout(...)` | Deadline HTTP request/response theo `HttpClient`, không phải business rollback |

Trong JDK `CompletableFuture` thông thường, tham số `mayInterruptIfRunning` không ảnh hưởng interrupt thread do cấu trúc completion stage không có quyền điều khiển thread tương tự `FutureTask`. Default `HttpClient` triển khai một hợp đồng **cụ thể hơn** cho HTTP exchange khi `cancel(true)`.

Đừng dùng `cancel` như một lời hứa “kill task trên server”. Các task bên remote tồn tại ngoài JVM caller và có lifecycle độc lập.

## 13. Idempotency theo RFC 9110: lúc nào retry an toàn hơn?

Theo [RFC 9110 `9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2), idempotent có nghĩa intended effect của nhiều request **giống nhau về semantics** như một request.

- **GET/HEAD** là *safe methods*, cũng thuộc các method idempotent. Hợp đồng chuẩn không yêu cầu tạo side effect nghiệp vụ mới; logging/analytics có thể vẫn ghi nhận nhiều lần.
- **PUT/DELETE** có semantics idempotent; lặp lại PUT cùng biểu diễn hoặc DELETE cùng resource có thể trả status khác nhưng intended effect là như nhau.
- **POST** không mặc định idempotent: hai lệnh tạo order/payment thường có thể tạo hai objects/charges.
- Idempotence là semantics **server phải tuân thủ**. Nếu một API tùy biến dùng GET tạo giao dịch hoặc PUT tăng counter, client phải hiểu contract thực tế và không blind retry.

RFC 9110 nói rõ không nên tự động retry request với method non-idempotent, trừ khi client biết operation thật sự idempotent hoặc có cách biết request chưa được áp dụng. **Một `IOException` không tự chứng minh điều kiện đó.**

Retry còn phải chịu quota, timeout tổng, backoff + jitter, số attempts và policy rate limit. Một GET idempotent nhưng nặng cũng có thể làm server quá tải khi hàng nghìn callers retry đồng loạt.

## 14. Làm Idempotency-Key đúng: server mới là nơi chống duplicate

Với những POST có side effects, thiết kế API như:

```http
POST /orders HTTP/1.1
Host: api.example
Content-Type: application/json
Idempotency-Key: operation-42

{"itemId":"P1","quantity":1}
```

Yêu cầu với server production:

1. **Một key cho một logical operation.** Caller tạo key một lần **trước lần gọi đầu tiên**; mọi retries giữ cùng key.
2. **Scope key với principal/tenant và endpoint/method**. Không cho tenant khác đoán/reuse key để đọc response hoặc can thiệp giao dịch.
3. **Ràng buộc key với payload fingerprint**. Cùng key nhưng body khác phải trả lỗi theo contract, không áp dụng thầm.
4. **Dùng durable transactional record/unique constraint** đồng bộ với business write để nhiều replicas, races và restarts không tạo duplicate. Không dùng `containsKey` rồi `put` tách rời.
5. **Lưu/tra lại kết quả cũ** hoặc cung cấp status endpoint nếu lần đầu thành công mà response mất.
6. **Định nghĩa trạng thái IN_PROGRESS/PENDING** để retry tới trong lúc operation đang chạy không thực hiện effect lần 2.
7. **TTL/retention đủ dài** cho cửa sổ retry/late retries; có logic khi key đã hết hạn và audit/reconciliation.

Demo dùng `ConcurrentHashMap.newKeySet()` chỉ chứng minh khái niệm trên **một process đang chạy**. Không có transaction isolation, durable store, payload hash, multi-node coordination hay effect rollback; **không đạt exactly-once ở payment system thật**.

## 15. Retry matrix theo loại request và trạng thái quan sát

| Trường hợp | Hướng xử lý | Điều kiện |
| --- | --- | --- |
| GET/HEAD idempotent gặp transient network error | Retry có giới hạn | Chỉ khi API safe đúng contract, exponential backoff và deadline |
| PUT đặt trạng thái có version | Retry có điều kiện | Dùng cùng representation/ETag/conditional headers khi cần tránh lost update |
| DELETE resource idempotent | Có thể retry theo contract | Status lần 2 có thể khác, không coi 404 tự động là lỗi business |
| POST tạo order **không key** mất response | **Không blind retry** | Trả UNKNOWN, tra transaction/status trước |
| POST có idempotency key server thực hiện đúng | Retry **cùng key** | Cùng payload/principal, key còn hiệu lực, bounded attempts |
| POST dùng body publisher one-shot | Không resend nguyên trạng | Cần body replayable/resumable protocol |
| User chủ động cancel operation | Không tự khởi động lại ngay | Có thể cần reconcile side effects đã thực hiện |
| Server trả HTTP 429/503 | Quyết định theo semantics | Xét `Retry-After` và retry budget, không nhân tải vô hạn |

**Chú ý:** Đôi khi server trả response lỗi sau khi đã commit, vì send response cũng có thể lỗi. Bởi vậy retry policy phải dựa trên **operation identity** và trạng thái authoritative, không chỉ dựa status hoặc exception Java.

## 16. Nếu cần hủy công việc server thật: phải có API riêng

Đối với long-running jobs, một giao thức có thể định nghĩa:

```text
POST /jobs (Idempotency-Key K)  -> 202 Accepted, jobId=J7
GET  /jobs/J7                 -> RUNNING
POST /jobs/J7/cancel          -> CANCEL_REQUESTED
GET  /jobs/J7                 -> CANCELLED hoặc COMPLETED
```

Lệnh `cancel` ở tầng nghiệp vụ cũng **có race**: job có thể đã commit trước khi request hủy tới server, một downstream có thể không hỗ trợ rollback, hoặc job đã chuyển sang bước không thể hủy. Server cần công bố rõ:

- Mốc nào có thể dừng trước khi side effect xảy ra.
- Khi đã commit thì trả `COMPLETED` hay chuyển sang **compensating action**.
- Cancel endpoint có idempotent không.
- Status query cho biết gì về durability.
- Nếu user đóng client giữa chừng, trạng thái job lưu bền ở đâu.

Đừng đánh đồng HTTP/2 `RST_STREAM` với `POST /jobs/J7/cancel`. Một cái là transport signal, một cái là business contract.

## 17. Response streaming và cancellation muộn

Một chi tiết quan trọng: `BodyHandlers.ofInputStream()` có thể cho response object **sau khi headers được nhận**, trước khi body được đọc tới EOF.

```java
// Snippet: client/request và các import đã có.
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    // Tiêu thụ bytes có quota/deadline, hoặc close khi dừng sớm.
}
```

Khi `send` đã trả response, một `Thread.interrupt()` xảy ra **sau đó** không phải là interrupt “đang nằm trong `HttpClient.send`” nữa. Nó có thể ảnh hưởng thao tác `InputStream.read` đang block theo behavior của stream/implementation, nhưng caller vẫn phải **đóng body đúng cách**.

Tương tự, `ofPublisher()` trả `Flow.Publisher<List<ByteBuffer>>`; cần **subscribe/request** tới terminal event hoặc `Subscription.cancel()` khi hủy. Đóng/cancel response body là cleanup một exchange; nó **không undo side effects** của request ở server.

Đừng coi `CompletableFuture` đã completed là bằng chứng download body đã hoàn tất. Nếu dùng streaming response, follow-up business stage cần tiếp nhận error và cancellation riêng.

## 18. Cancellation trong pipeline: giữ reference đến request gốc

Một pipeline thường có nhiều tương lai:

```text
User request
    |
    v
sendAsync future -------------- HTTP exchange
    |
    +-- thenApply(parse)
    +-- thenCompose(store)
    +-- whenComplete(metrics)
    |
    v
Application result / UI future
```

Nếu người dùng bấm “Cancel”, ứng dụng cần quyết định:

- Có gọi `original.cancel(true)` để **cố dừng HTTP exchange** không?
- Có hủy body publisher/subscriber, timeout, queues và tác vụ downstream do application sở hữu không?
- Các callbacks đến muộn sẽ được nhận diện ra sao? Có operation generation/token chống ghi đè kết quả mới không?
- Có ghi `CANCEL_REQUESTED`/`UNKNOWN_OUTCOME` và giữ operation ID để truy vấn trạng thái sau đó không?
- Có cần ngừng hiển thị spinner **ngay** nhưng vẫn duy trì backend reconciliation không?

Một `CompletableFuture` ở tầng UI được cancel **không nhất thiết** tự thực thi mọi quyết định ấy. Cancellation propagation phải là thiết kế explicit; không nhầm với eventual rollback.

## 19. Logging, tracing và dữ liệu cần để xác định outcome

Khi client không biết request đã thành công hay chưa, cần correlation ID tồn tại **trước lần gửi đầu tiên**:

| Field | Client | Server |
| --- | --- | --- |
| `operationId` / Idempotency-Key | Lưu trước send, dùng lại khi retry | Gắn transaction/ledger record |
| HTTP method, route, payload fingerprint | Log an toàn, không log secrets | Validate cùng key đúng payload |
| Attempt number | Đếm retries | Phân biệt attempt vs logical effect |
| Timeout/cancellation cause | Interrupted, user cancel, deadline | Có thể chỉ thấy connection reset |
| Server status | UNKNOWN / RECONCILING nếu không nhận response | PENDING / COMMITTED / FAILED authoritative |
| Commit time/result | Lấy qua status API khi cần | Durable state / result cache |
| Connection/stream status | IOException, cancel, HTTP version | Socket close, aborted response write |

Không ghi `Authorization` token, mật khẩu, raw payment payload vào log vì muốn debug cancellation. Sử dụng redaction và trace IDs có scope. Khi monitoring, phân biệt `client_cancelled`, `client_timeout`, `unknown_outcome`, `server_committed`, `duplicate_attempt` và `reconciled`.

Nếu chỉ đếm mọi `InterruptedException` thành “server failed”, metrics có thể làm mất chính xác tín hiệu về **operation đã commit mà client không nhận ACK**.

## 20. Kiểm thử race với latch thay vì hy vọng mạng ngẫu nhiên lỗi

Một bộ test nên có các ca:

1. **Interrupt trước khi server nhận:** client task kết thúc/được cancel; không khẳng định remote chưa nhận nếu không có chứng cứ.
2. **Interrupt sau server đọc request, trước commit:** server có thể chọn dừng hoặc tiếp tục theo contract.
3. **Interrupt sau commit, trước response:** effect tồn tại; client không được tự tạo effect trùng khi retry.
4. **Cancel `sendAsync` sau commit:** future cancelled nhưng side effect vẫn có.
5. **Retry cùng key:** nhiều HTTP requests, đúng **một logical effect**.
6. **Retry đồng thời cùng key trên nhiều server nodes:** cần unique constraint/transaction, không in-memory set đơn node.
7. **Cùng key nhưng payload khác:** server từ chối.
8. **Server restart sau commit trước response:** durable ledger vẫn nhận ra retry.
9. **Response body streaming chưa hoàn tất:** close/cancel body mà không rò resources.
10. **HTTP/1.1 và HTTP/2:** observe connection close/stream reset, không mặc định timing giống nhau.
11. **Future.get(timeout) vs cancel(true):** xác nhận timeout đợi không tự cancel exchange.
12. **Shutdown executor:** catch/restore interrupt và không retry side effects ngoài policy.

Hai chương trình Java trong bài dùng latch để bắt đúng mốc “**server đã xử lý trước khi caller mất kết quả**”. Không cần mạng public, proxy hay packet loss injection để nhìn thấy trường hợp này.

## 21. Hai mươi lỗi thường gặp

1. **“`InterruptedException` chứng minh POST chưa tới server.”** Sai: docs Java 17 nói request vẫn có thể đã được gửi.
2. **“`cancel(true)` trả true là server rollback.”** Sai: future cancelled, remote outcome có thể đã commit.
3. **“`cancel(false)` chắc chắn dừng exchange như `cancel(true)`.”** Không có cùng bảo đảm.
4. **“CompletableFuture.cancel(true) luôn ngắt thread.”** Sai với CompletableFuture chuẩn.
5. **“Ngắt kết nối TCP sẽ rollback DB transaction.”** Không có cơ chế chung như vậy.
6. **“HTTP/2 RST_STREAM là business cancellation.”** Sai cấp abstraction.
7. **“Timeout nghĩa là server chưa làm gì.”** Sai: có thể xảy ra sau commit.
8. **“HTTP 500 luôn cho phép retry POST.”** Có thể đã commit rồi lỗi khi trả response.
9. **“Retry POST không key chỉ tạo một order.”** Không bảo đảm, có thể duplicate.
10. **“Mỗi retry dùng một Idempotency-Key mới.”** Mất khả năng deduplicate logical operation.
11. **“Idempotency map trong một JVM đủ cho production đa node.”** Không durable, không atomic với DB.
12. **“Cùng key nhưng payload khác vẫn chấp nhận.”** Rủi ro correctness/security; phải ràng buộc.
13. **“`future.get(timeout)` tự cancel network.”** Không; chỉ giới hạn thời gian chờ.
14. **“`orTimeout` bảo đảm remote ngừng xử lý.”** Không; future completion khác business outcome.
15. **“Nuốt InterruptedException rồi gửi lại ngay.”** Có thể tạo double effect và bỏ qua shutdown signal.
16. **“Cancel mọi dependent future là đủ cho pipeline.”** Cần ownership/propagation cụ thể tới source exchange và body.
17. **“Future cancelled nên mọi callback/worker đã dừng.”** Có thể còn callbacks và remote work đến muộn.
18. **“Gọi send đã trả headers nên body streaming không cần close.”** Vẫn phải consume/close/cancel.
19. **“Không cần operation ID nếu đã có HTTP request ID của proxy.”** Cần ID bền qua retries và gắn với business transaction.
20. **“Thấy IOException là chọn FAILED thay vì UNKNOWN.”** Chỉ kết luận thất bại khi có bằng chứng authoritative.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Thread gọi `send(POST)` bị interrupt. Có được hiển thị “đơn hàng chắc chắn chưa tạo” không? **Không**. Outcome có thể không xác định; tra trạng thái theo operation ID.

**Câu 2.** `sendAsync(...).cancel(true)` trả true. Điều đó nói gì? **Future đã cancelled**; JDK HTTP client cố dừng exchange, không bảo đảm server ngừng.

**Câu 3.** Server đã commit trước khi client timeout. Retry POST không key có rủi ro gì? **Duplicate side effects**.

**Câu 4.** Tại sao phải giữ cùng `Idempotency-Key` qua retries? **Để server nhận ra cùng logical operation** và không áp dụng effect hai lần.

**Câu 5.** `future.get(2,SECONDS)` ném `TimeoutException`. Có thể kết luận request đã bị cancel không? **Không.** Chờ future và hủy future là hai thao tác khác nhau.

**Câu 6.** Một `PUT` được định nghĩa idempotent, response lần 2 có bắt buộc giống lần 1 không? **Không**; idempotence liên quan intended effect, không bắt status/response bằng nhau.

**Câu 7.** Server mTLS/HTTP/2 nhận reset stream, database transaction có tự undo không? **Không**. Phải có policy cancellation/transaction riêng.

**Câu 8.** Khi `send` ném `InterruptedException` và catch không propagate ngay, làm gì với interrupt flag? **Khôi phục** `Thread.currentThread().interrupt()`.

**Câu 9.** Client có thể tự bảo đảm exactly-once cho POST chỉ bằng một `ConcurrentHashMap` không? **Không**. Cần dedup/transaction durability phía server.

**Câu 10.** User bấm “Cancel” sau khi payment đã thành công nhưng response bị mất: nên làm gì? **Hiển thị trạng thái cần đối soát, tra operation/payment ID và chỉ thực hiện compensation nếu business protocol hỗ trợ**.

## 23. Checklist production và kết luận

1. **Xác định HTTP semantics:** method safe/idempotent hay side-effecting, contract thực của endpoint.
2. **Cấp operation ID trước request đầu tiên** cho thao tác có thể cần retry/reconciliation.
3. **Không hiểu interrupt/cancel là remote rollback.** Gắn outcome=UNKNOWN nếu chưa có kết quả.
4. **Khôi phục interrupt status** khi `send` ném `InterruptedException`, hoặc propagate tới task owner.
5. **Giữ original sendAsync future** nếu cần `cancel(true)` để thử dừng HTTP exchange.
6. **Tách connect timeout, request timeout, future waiting timeout và business deadline**.
7. **Định nghĩa retry policy có idempotency semantics, backoff/jitter, retry budget và total deadline**.
8. **Yêu cầu idempotency durable/atomic trên server** với key, tenant, method, payload hash, status/result.
9. **Có status lookup/reconciliation** cho request đã commit nhưng response bị mất.
10. **Có cancellation endpoint/compensation policy riêng** nếu cần hủy business job thật.
11. **Đóng stream body/cancel subscription** và dọn resources sau cancellation muộn.
12. **Đo các ca lỗi theo operation ID** cả client, server, DB và worker queue; không log secrets.
13. **Kiểm thử races** ở các điểm nhận request, commit, send response, cancel, restart và concurrent retry.
14. **Không phụ thuộc vào hành vi pool/HTTP version cụ thể:** HTTP/1.1 close hay HTTP/2 reset không quyết định business state.

**Kết luận:** `HttpClient.send` bị interrupt hoặc `sendAsync` bị `cancel(true)` có thể khiến **client thôi chờ và cố hủy HTTP exchange**, nhưng **server vẫn có thể đã nhận, xử lý và commit request**. Bảo vệ dữ liệu không nằm ở một lời gọi `cancel`, mà ở **idempotency đúng semantics, lưu trạng thái bền vững và khả năng tra soát sau kết quả không chắc chắn**.

### Tài liệu chính thức và tiêu chuẩn

- [Java SE 17 — HttpClient.send / sendAsync, interruption và cancellation](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 — HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java SE 17 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html)
- [Java SE 17 — CompletableFuture.cancel / orTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [RFC 9110 `9.2.2 — Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2)
- [Java SE 17 — HttpServer (loopback demo)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html).
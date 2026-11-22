# Thời hạn chờ kết quả của Future khác với hủy trao đổi mạng

## Mục tiêu bài học

Khi gọi `HttpClient.sendAsync(...)` trong Java, chương trình nhận về một `CompletableFuture<HttpResponse<T>>`. Nếu thread chờ kết quả bằng `future.get(200, MILLISECONDS)` và gặp `TimeoutException`, **điều duy nhất đã chắc chắn là thread chờ chưa có kết quả trong 200 ms**. Điều đó **không** có nghĩa HTTP request đã bị hủy, TCP connection đã đóng, server chưa nhận dữ liệu, hoặc thao tác nghiệp vụ chưa thực hiện.

Tương tự, gọi `future.cancel(true)` trên future trả về bởi HTTP client mặc định của Java có thể **yêu cầu hủy HTTP exchange** và cố giải phóng tài nguyên, nhưng **không bảo đảm server chưa nhận request hoặc chưa xử lý side effect**. Đến lúc client hủy, server có thể đã commit giao dịch và chỉ còn đang tạo response.

Chủ đề này thuộc **HTTP bất đồng bộ**, tập trung vào ranh giới giữa:

- **Thời hạn chờ kết quả ở caller:** `Future.get(timeout)`.
- **Thời hạn hoàn thành một CompletableFuture stage:** `orTimeout`, `completeOnTimeout`.
- **Thời hạn chính request HTTP:** `HttpRequest.Builder.timeout(Duration)`.
- **Thời hạn tạo TCP connection:** `HttpClient.Builder.connectTimeout(Duration)`.
- **Hành động yêu cầu hủy:** `CompletableFuture.cancel(true)` trên future của `HttpClient.sendAsync`.
- **Kết quả nghiệp vụ thật trên server:** có thể **đã xử lý** mặc dù client nhìn thấy timeout/cancel/IOException.

Học xong, bạn có thể xác định chính xác timeout xảy ra ở lớp nào, có cần thêm API để hủy mạng không, nên giữ/đóng connection ra sao, vì sao retry sau timeout có thể tạo side effect trùng, và cách viết code Java 17+ để quan sát tất cả những điều trên.

## 1. Một HTTP request có nhiều vòng đời độc lập

Xét client gửi một yêu cầu đặt hàng tới server:

```text
Client thread                  Java HttpClient/TCP                     HTTP server
     │  sendAsync(request)            │                                  │
     ├───────────────────────────────►│                                  │
     │  CompletableFuture              ├──── POST /orders ───────────────►│
     │                                 │                                  │
     │  future.get(200ms)              │                          xử lý/commit đơn hàng
     │  ... hết 200ms ...              │                                  │
     │◄ TimeoutException              │                                  │
     │                                 │        response đang chuẩn bị    │
     │                                 │◄──────── 201 Created ──────────┤
     │                                 │                                  │
     │  future.get(3s)                 │                                  │
     │◄ HttpResponse 201              │                                  │
```

Trong sơ đồ này, **200 ms chờ trên thread kết thúc**, nhưng **HTTP exchange chưa kết thúc** ở thời điểm đó. Request đầu có thể vẫn hoàn tất bình thường và future có kết quả sau đó.

Tối thiểu có bốn trạng thái cần phân biệt:

| Thành phần | Trạng thái có thể có lúc caller timeout | Có tự dừng vì `get(timeout)` không? |
|---|---|---|
| Thread gọi `get` | Hết thời hạn chờ, nhận `TimeoutException` | Đúng: thao tác **chờ** kết thúc |
| `CompletableFuture` gốc | Vẫn incomplete, hoặc có thể đã hoàn tất trong một race | **Không** |
| HTTP request/network exchange | Đang gửi body, đợi header/body, hoặc đã có kết quả ở tầng khác | **Không có yêu cầu hủy từ `get(timeout)`** |
| Server-side business operation | Chưa nhận, đang chạy, hoặc đã commit | **Không** |

Cần nhấn mạnh: một timeout có thể xảy ra **trong khi server chưa từng nhận request**, nhưng cũng có thể xảy ra **sau khi server đã xử lý xong**. Chỉ riêng ngoại lệ phía client không xác định được điểm nào trong hai trường hợp.

### Không nhầm “Future” với “trao đổi HTTP”

`Future`/`CompletableFuture` là **tay cầm quan sát và điều phối kết quả bất đồng bộ**. `HttpClient` là thành phần thực hiện hoạt động I/O. Hai thành phần liên quan nhưng không đồng nhất: thay đổi cách chờ một future không có nghĩa bạn đang gửi một frame/packet “CANCEL” tới server. Trong HTTP/1.1 không có HTTP method chuẩn “hủy request đã commit” tự động khi caller timeout.

Một Future hoàn tất exceptional cũng **không chứng minh** tác vụ server đã rollback. Có thể request đã đi qua proxy, được server xử lý, response bị mất hoặc client không còn nhận kết quả.

## 2. `Future.get(timeout)`: chỉ giới hạn thời gian chờ của thread

Chữ ký:

```java
V value = future.get(longTimeout, TimeUnit.MILLISECONDS);
```

Đây là **cú pháp minh họa**, với `future` là một `Future<V>` đã được tạo ở nơi khác.

Theo Java 17 `Future.get(long, TimeUnit)`:

- Nếu Future hoàn tất bình thường trong thời hạn: trả giá trị.
- Nếu Future hoàn tất thất bại: ném `ExecutionException`, nguyên nhân cụ thể ở `getCause()`.
- Nếu Future đã bị cancel: có thể ném `CancellationException`.
- Nếu thread đợi bị interrupt: ném `InterruptedException`, không mặc định có nghĩa HTTP exchange đã bị hủy.
- Nếu chưa có kết quả trước deadline: ném `TimeoutException`.
- **Không có hành động cancel ngầm** được quy định chỉ vì `get(timeout)` ném `TimeoutException`.

Đặc biệt, sau `TimeoutException` bạn **vẫn có thể giữ tham chiếu future** để quan sát kết quả muộn:

```java
// Đoạn minh họa; future đã nhận từ HttpClient.sendAsync(...).
try {
    HttpResponse<String> response = future.get(200, TimeUnit.MILLISECONDS);
    handleResponse(response);
} catch (TimeoutException waitedTooLong) {
    recordCallerWaitExpired();
    // KHÔNG tự kết luận future đã bị cancel hoặc server chưa xử lý.
    // Ứng dụng có thể tiếp tục theo dõi chính future này.
}
```

Đoạn trên **không độc lập**: `handleResponse`, `recordCallerWaitExpired` và biến `future` là thành phần ứng dụng cần định nghĩa. Trong production phải xử lý thêm interruption, `ExecutionException`, trạng thái lifecycle và request timeout riêng.

### 2.1. Sai lầm: chờ timeout là gọi cancel

Sai:

```text
get(timeout) ném TimeoutException
    ⇒ HTTP client đã dừng mạng          (SAI)
    ⇒ server chắc chắn không commit      (SAI)
    ⇒ gửi POST mới không thể gây trùng  (SAI)
```

Đúng:

```text
get(timeout) ném TimeoutException
    ⇒ thời gian chờ của caller đã hết
    ⇒ phải quyết định: tiếp tục theo dõi, hủy có chủ ý,
       hay đánh dấu kết quả nghiệp vụ CHƯA BIẾT
```

Nếu mục tiêu thực sự là “caller chỉ được chờ 200 ms nhưng hệ thống vẫn muốn nhận kết quả sau này”, **không gọi cancel** sau timeout. Giữ future trong registry, thêm `whenComplete(...)` hoặc dùng completion chain khác để xử lý response muộn.

Nếu muốn hủy tác vụ, đó là một quyết định riêng và cần hiểu rằng **hủy ở phía client vẫn không hoàn tác server side effect**.

## 3. Java 17+: chứng minh `get(timeout)` không hủy request

Ví dụ này tạo HTTP server ở **loopback**, không phụ thuộc Internet hay server bên ngoài. Server nhận request, báo đã nhận bằng `CountDownLatch`, rồi **cố tình giữ response lại** cho đến khi thread main cho phép. Client gọi `get(100ms)` khi server chưa được phép gửi. Vì vậy ta biết thời gian chờ sẽ hết nhưng HTTP exchange vẫn còn.

**Tệp `WaitTimeoutDoesNotCancelDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class WaitTimeoutDoesNotCancelDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch requestArrived = new CountDownLatch(1);
        CountDownLatch allowResponse = new CountDownLatch(1);
        ExecutorService serverWorker = Executors.newSingleThreadExecutor();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.setExecutor(serverWorker);
        server.createContext("/slow", exchange -> {
            try (exchange) {
                exchange.getRequestBody().readAllBytes();
                requestArrived.countDown();
                if (!allowResponse.await(5, TimeUnit.SECONDS)) return;
                byte[] body = "DELIVERED".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (var out = exchange.getResponseBody()) { out.write(body); }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });
        try {
            server.start();
            URI uri = URI.create("http://localhost:"
                    + server.getAddress().getPort() + "/slow");
            HttpClient client = HttpClient.newHttpClient();
            CompletableFuture<HttpResponse<String>> request = client.sendAsync(
                    HttpRequest.newBuilder(uri).GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            if (!requestArrived.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server did not receive request");
            }

            boolean timedOut = false;
            try {
                request.get(100, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                timedOut = true;
            }
            System.out.println("Timed wait expired: " + timedOut);
            System.out.println("Future still pending: " + !request.isDone());

            allowResponse.countDown();
            HttpResponse<String> result = request.get(3, TimeUnit.SECONDS);
            System.out.println("Later response: " + result.statusCode()
                    + " " + result.body());
        } finally {
            allowResponse.countDown();
            server.stop(0);
            serverWorker.shutdownNow();
        }
    }
}
```

Biên dịch/chạy bằng **JDK 17 trở lên**:

```bash
javac --release 17 -encoding UTF-8 WaitTimeoutDoesNotCancelDemo.java
java WaitTimeoutDoesNotCancelDemo
```

**Stdout đã kiểm chứng khi chạy trên localhost:**

```text
Timed wait expired: true
Future still pending: true
Later response: 200 DELIVERED
```

Các điểm đáng chú ý:

1. `HttpClient.sendAsync` lập tức trả về một `CompletableFuture<HttpResponse<String>>` trong khi network operation tiến hành bất đồng bộ.
2. `requestArrived.await` là **latch của riêng test**, không phải một HTTP handshake đặc biệt. Nó bảo đảm server đã nhìn thấy request trước khi client bắt đầu chờ có timeout.
3. Server bị giữ ở `allowResponse.await(...)`, nên không thể hoàn tất response trước khi caller `get(100ms)` hết thời gian.
4. `get(...)` ném `TimeoutException` và đoạn code đánh dấu `timedOut=true`. Không có `future.cancel(...)` nào được gọi.
5. Sau khi hết thời hạn chờ, `!request.isDone()` vẫn true. Nó chỉ phản ánh **chưa có final result** tại thời điểm đo.
6. Khi main `allowResponse.countDown()`, server trả `200 DELIVERED`; **cùng future gốc** trở nên hoàn tất và `get(3s)` trả response.
7. `finally` thả latch rồi dừng server/executor để tránh treo test khi có exception. Timeout và latch đều phục vụ kiểm chứng; trong môi trường quá chậm/chặn loopback, test có thể báo lỗi thay vì in đủ kết quả.

**Kết luận:** một lần `get(timeout)` không làm HTTP exchange biến mất. Caller có thể timeout mà request vẫn hoàn tất bình thường sau đó.

## 4. `CompletableFuture.orTimeout` và `completeOnTimeout`: deadline của stage, không phải rollback server

Java 17 cung cấp:

```java
CompletableFuture<T> stage = ...;
stage.orTimeout(300, TimeUnit.MILLISECONDS);
stage.completeOnTimeout(defaultValue, 300, TimeUnit.MILLISECONDS);
```

Đây là **cú pháp minh họa**, không phải chương trình độc lập.

Hai phương thức cùng có một điểm quan trọng trong Javadoc: **chúng trả về `this` và có thể hoàn tất chính `CompletableFuture` được gọi**.

- `orTimeout(timeout, unit)`: nếu future **chưa hoàn tất** trước deadline, nó **hoàn tất exceptional** với `TimeoutException`.
- `completeOnTimeout(value, timeout, unit)`: nếu future chưa hoàn tất, nó **hoàn tất bình thường** với giá trị fallback được cho.
- Nếu future đã hoàn tất trước deadline, timeout không ghi đè kết quả ấy.
- Các phương thức này **không có hợp đồng “hủy TCP exchange, đóng socket và rollback server business transaction”**.

### So với `get(timeout)`

| Tình huống | `get(100ms)` | `orTimeout(100ms)` | `completeOnTimeout(fallback,100ms)` |
|---|---|---|---|
| Timeout tác động lên cái gì? | **Caller thread đang chờ** | **Trạng thái của CompletableFuture được gọi** | **Trạng thái của CompletableFuture được gọi** |
| Khi hết hạn | Ném `TimeoutException` từ lệnh `get` | Future hoàn tất exceptional với `TimeoutException` | Future hoàn tất bình thường với fallback |
| Future gốc còn pending? | Có thể vẫn pending | **Không**, nếu gọi `orTimeout` trực tiếp trên future gốc và timeout thắng | **Không**, nếu gọi trực tiếp trên future gốc và fallback thắng |
| Có bảo đảm server không chạy? | Không | Không | Không |
| Có tự động rollback side effect? | Không | Không | Không |
| Có phải API dedicated để hủy HTTP network exchange? | Không | Không | Không |

**Cực kỳ dễ mắc lỗi:** viết

```java
// MINH HỌA: thay đổi trực tiếp trạng thái future trả về từ sendAsync.
CompletableFuture<HttpResponse<String>> transport = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());
transport.orTimeout(200, TimeUnit.MILLISECONDS);
```

`transport.orTimeout` ở đây **chỉnh chính `transport`**. Nếu deadline thắng, các bước xử lý downstream có thể thấy Future exceptional thay vì response thực sự đến muộn. Điều đó không cho phép kết luận network request chưa gửi, hoặc server side effect không xảy ra.

Nếu cần deadline **chỉ cho một tầng hiển thị/UI** nhưng vẫn tiếp tục theo dõi Future HTTP gốc, hãy đặt timeout trên **một derived stage riêng** như `transport.thenApply(...)` hoặc `transport.copy()`:

```java
// MINH HỌA: chỉ derived stage có deadline riêng.
CompletableFuture<HttpResponse<String>> transport = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());

CompletableFuture<String> uiView = transport
        .thenApply(HttpResponse::body)
        .orTimeout(200, TimeUnit.MILLISECONDS);
// Nếu uiView timeout, transport vẫn có thể hoàn tất sau đó.
```

Đoạn minh họa này cần `client`, `request` và imports do application định nghĩa.

### `completeOnTimeout` không có nghĩa nghiệp vụ thành công

Một cách dùng sai là tạo `HttpResponse 200 giả` hoặc trả “Thanh toán thành công” khi deadline hết. `completeOnTimeout` tạo **fallback do bạn chọn**, không xác nhận server. Nếu muốn giao diện có kết quả tạm thời, hãy chọn một trạng thái rõ ràng như `PENDING` / `UNKNOWN`, và tiếp tục theo dõi request thật.

Một kiểu kết quả an toàn hơn:

```java
// Ý tưởng minh họa, không phải class độc lập.
record ViewResult(String state, String detail) {}

CompletableFuture<ViewResult> view = transport
        .thenApply(r -> new ViewResult("CONFIRMED",
                "HTTP " + r.statusCode()))
        .completeOnTimeout(new ViewResult("UNKNOWN", "Still processing"),
                200, TimeUnit.MILLISECONDS);
```

Ngay cả `CONFIRMED` HTTP status cũng chỉ xác nhận response ứng dụng đã nhận, không tự bảo đảm một giao dịch external đã settle nếu contract nghiệp vụ không nói vậy.

## 5. Java 17+: timeout ở derived stage, HTTP gốc vẫn chạy

Ví dụ sau tạo HTTP server loopback bị giữ response bằng latch. Client dùng `sendAsync` và tạo **một derived future** `display` bằng `network.thenApply(HttpResponse::body)`. Chỉ `display` được đặt `orTimeout(100ms)`. Khi hết thời hạn, `display` exceptional nhưng `network` chưa xong. Mở latch thì `network` có response bình thường.

**Tệp `TimeoutStageIsolationDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class TimeoutStageIsolationDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService worker = Executors.newSingleThreadExecutor();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.setExecutor(worker);
        server.createContext("/delay", exchange -> {
            try (exchange) {
                exchange.getRequestBody().readAllBytes();
                started.countDown();
                if (!release.await(5, TimeUnit.SECONDS)) return;
                byte[] body = "SERVER_OK".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (var out = exchange.getResponseBody()) { out.write(body); }
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        });
        try {
            server.start();
            URI uri = URI.create("http://localhost:"
                    + server.getAddress().getPort() + "/delay");
            CompletableFuture<HttpResponse<String>> network =
                    HttpClient.newHttpClient().sendAsync(
                            HttpRequest.newBuilder(uri).GET().build(),
                            HttpResponse.BodyHandlers.ofString());

            // orTimeout modifies THIS derived future, not network.
            CompletableFuture<String> display =
                    network.thenApply(HttpResponse::body);
            display.orTimeout(100, TimeUnit.MILLISECONDS);

            if (!started.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("No request at server");
            }
            boolean displayTimedOut = false;
            try {
                display.join();
            } catch (CompletionException error) {
                displayTimedOut = error.getCause() instanceof TimeoutException;
            }
            System.out.println("Derived view timed out: " + displayTimedOut);
            System.out.println("Original exchange pending: " + !network.isDone());

            release.countDown();
            HttpResponse<String> result = network.get(3, TimeUnit.SECONDS);
            System.out.println("Original result: "
                    + result.statusCode() + " " + result.body());
        } finally {
            release.countDown();
            server.stop(0);
            worker.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TimeoutStageIsolationDemo.java
java TimeoutStageIsolationDemo
```

**Stdout đã kiểm chứng:**

```text
Derived view timed out: true
Original exchange pending: true
Original result: 200 SERVER_OK
```

**Diễn giải cẩn thận:**

- `network` là future gốc của `HttpClient`; `display` là một derived future, được tạo bằng `thenApply`. Java hoàn tất `display` theo kết quả body nếu nguồn hoàn tất đủ sớm.
- `display.orTimeout(100ms)` thay đổi chính derived future. Khi timeout thắng, `display.join()` ném `CompletionException` mà `getCause()` là `TimeoutException`.
- Vì server bị gate, HTTP response chưa đến; `!network.isDone()` vẫn true. `network` không tự bị complete exceptionally chỉ vì derived stage đã timeout.
- Sau khi release, `network.get(...)` nhận `200 SERVER_OK`. Derived view đã terminal exceptional và **không tự đổi lại kết quả** khi original future hoàn tất.
- Kết quả không có nghĩa HTTP client luôn giữ exchange khi mọi derived stage timeout/cancel. Nếu muốn thực sự dừng mạng, cần **yêu cầu hủy rõ ràng** và theo dõi lifecycle tương ứng.

Dùng mô hình này cho UI, RPC gateway hoặc request coordinator khi deadline của người xem **khác** deadline của tác vụ HTTP thật. Nhưng phải có giới hạn tài nguyên cho request còn tiếp tục; không cho phép mọi request timeout UI đều tồn tại mãi.

## 6. `HttpRequest.Builder.timeout`: timeout thuộc HTTP request

Java `HttpRequest.Builder.timeout(Duration)` tạo **timeout cho request HTTP**. Nếu không nhận response trong thời hạn đã đặt, `HttpClient.send(...)` có thể ném `HttpTimeoutException`; `HttpClient.sendAsync(...)` có thể hoàn tất exceptional với `HttpTimeoutException`.

```java
// Trích đoạn minh họa; URI và imports do ứng dụng cung cấp.
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(java.time.Duration.ofMillis(500))
        .POST(HttpRequest.BodyPublishers.ofString("ACTION"))
        .build();

CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
```

Khác với `get(500ms)`:

- Đây là **điều kiện deadline của request trong HTTP client**, không đơn thuần là caller đợi tối đa 500 ms.
- Khi deadline của request được kích hoạt, future có thể hoàn tất exceptional bằng `HttpTimeoutException` (subclass của `IOException`).
- Đừng gọi đây là **server-side execution deadline**. Server không mặc nhiên biết hoặc tuân theo `Duration` phía client.
- Implementation có thể cố giải phóng tài nguyên network sau request timeout, nhưng không có bảo đảm remote server rollback.
- Thời điểm response/việc đọc body và các overload `BodyHandler` ảnh hưởng cách quan sát hoàn thành. Với `BodyHandlers.ofInputStream()`, response future có thể hoàn thành khi có stream trước khi ứng dụng đọc hết body; app còn trách nhiệm tiêu thụ/đóng stream.

### 6.1. Connect timeout khác request timeout

`HttpClient.Builder.connectTimeout(Duration)` đặt giới hạn cho **việc thiết lập kết nối**. Nó không thay `HttpRequest.Builder.timeout` và không đo tổng thời gian nghiệp vụ của server.

| Cấu hình/lệnh | Áp dụng cho | Ngoại lệ đáng chú ý | Điều không được suy ra |
|---|---|---|---|
| `client.sendAsync(...)` | Gửi/nhận HTTP bất đồng bộ | Future có response hoặc exceptional | Bản thân sendAsync không đặt deadline caller |
| `future.get(200ms)` | **Thời gian thread chờ** | `TimeoutException` | Không có implicit network cancel |
| `future.orTimeout(200ms)` | **Trạng thái chính future được gọi** | Exceptional `TimeoutException` | Không tự chứng minh HTTP exchange đã bị hủy |
| `future.completeOnTimeout(...)` | **Trạng thái chính future được gọi** | Fallback value | Fallback không phải response server |
| `request.timeout(200ms)` | **HTTP request lifecycle** | `HttpTimeoutException` | Không hủy business operation server |
| `client.connectTimeout(200ms)` | **Thiết lập connection** | `HttpConnectTimeoutException` khi connect timeout | Không đo server xử lý response |
| `future.cancel(true)` | **Yêu cầu hủy future/exchange** | `CancellationException` hoặc lỗi liên quan tùy timing/implementation | Không bảo đảm server ngừng, không rollback |

**Lưu ý giữa `get(timeout)` và `request.timeout`:** một chương trình có thể dùng cả hai, ví dụ request timeout 5 giây nhưng caller chỉ chờ 200 ms. Khi caller nhận `TimeoutException` sau 200 ms, HTTP request vẫn có thể tiếp tục tối đa theo policy 5 giây. Trái lại, nếu HTTP request timeout xảy ra trước, caller có thể nhận `ExecutionException(cause=HttpTimeoutException)` khi dùng `get(...)`.

### 6.2. Phân loại lỗi đúng qua Future

`HttpClient.sendAsync(...)` trả `CompletableFuture<HttpResponse<T>>`. Khi request timeout:

```java
// Đoạn minh họa: future đã có.
try {
    HttpResponse<String> result = future.get();
} catch (ExecutionException failed) {
    Throwable cause = failed.getCause();
    if (cause instanceof HttpTimeoutException) {
        // HTTP request timeout theo cấu hình.
    } else {
        // Lỗi HTTP/network/handler khác.
    }
}
```

Nếu dùng `future.join()`, exception thường được biểu hiện qua `CompletionException` có `getCause()`, hoặc `CancellationException` khi future canceled. Đừng catch duy nhất `TimeoutException` của `get(timeout)` rồi tưởng sẽ bắt được `HttpTimeoutException`: chúng là **hai loại exception khác nhau** ở hai tầng khác nhau.

## 7. Java 17+: HTTP request timeout trong khi server đã nhận việc

Ví dụ thứ ba cho server **ghi nhận một lần xử lý nghiệp vụ** ngay sau khi nhận body, rồi giữ response cho tới khi client timeout. Request gắn `timeout(Duration.ofMillis(200))`. Chương trình kiểm tra client nhìn thấy `HttpTimeoutException` nhưng counter server đã lên `1`.

**Tệp `HttpRequestTimeoutVsCommitDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.*;
import java.net.http.*;
import java.time.Duration;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class HttpRequestTimeoutVsCommitDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger accepted = new AtomicInteger();
        CountDownLatch processed = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService worker = Executors.newSingleThreadExecutor();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.setExecutor(worker);
        server.createContext("/work", exchange -> {
            try (exchange) {
                exchange.getRequestBody().readAllBytes();
                accepted.incrementAndGet();
                processed.countDown();
                if (!release.await(5, TimeUnit.SECONDS)) return;
                try {
                    exchange.sendResponseHeaders(204, -1);
                } catch (IOException afterClientLeft) {
                    // Client may already have ended its exchange.
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });
        try {
            server.start();
            URI uri = URI.create("http://localhost:"
                    + server.getAddress().getPort() + "/work");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofMillis(200))
                    .POST(HttpRequest.BodyPublishers.ofString("ORDER"))
                    .build();
            CompletableFuture<HttpResponse<Void>> future =
                    HttpClient.newHttpClient().sendAsync(
                            request, HttpResponse.BodyHandlers.discarding());
            if (!processed.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server missed request");
            }

            boolean httpTimeout = false;
            try {
                future.join();
            } catch (CompletionException failed) {
                httpTimeout = failed.getCause() instanceof HttpTimeoutException;
            }
            System.out.println("HTTP request timed out: " + httpTimeout);
            System.out.println("Server accepted work: " + accepted.get());
        } finally {
            release.countDown();
            server.stop(0);
            worker.shutdownNow();
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 HttpRequestTimeoutVsCommitDemo.java
java HttpRequestTimeoutVsCommitDemo
```

**Stdout đã biên dịch/chạy kiểm chứng:**

```text
HTTP request timed out: true
Server accepted work: 1
```

**Giải thích:**

1. Server đọc body `ORDER` trước, tăng `accepted` lên 1, báo qua `processed.countDown()`.
2. Server chưa gửi response vì còn chờ latch `release`. Dù request tới nhanh, response bị giữ lâu hơn 200 ms một cách cố ý.
3. Deadline do `HttpRequest.Builder.timeout` kích hoạt, nên Future exceptional với nguyên nhân `HttpTimeoutException`, không phải `TimeoutException` của `future.get(timeout)`.
4. Counter server vẫn là 1. **Sự kiện phía client timeout không thể tự làm đảo ngược increment đã xảy ra**.
5. Trong demo, counter đại diện một “side effect” minh họa trong RAM, không phải transaction bền vững. Với cơ sở dữ liệu thật, chỉ rollback nếu server thiết kế transaction/cancellation tương ứng.
6. `finally` mở latch, đóng server và executor. Server có thể không gửi được response sau khi client ngừng exchange; đây là lỗi network sau side effect, không chứng minh side effect chưa diễn ra.

Không nên xây retry tự động cho `POST` “tạo đơn” chỉ dựa vào việc `HttpTimeoutException` xảy ra. Trạng thái thực tế là **chưa có xác nhận thành công từ server**, không đồng nghĩa chắc chắn thất bại.

## 8. `cancel(true)` trên `sendAsync`: hủy là nỗ lực phía client

Javadoc Java 17 của `HttpClient.sendAsync(...)` có lưu ý riêng: `CompletableFuture` do default `HttpClient` trả về có hỗ trợ cancellation. Khi gọi `cancel(true)` trên future **chưa hoàn thành**, HTTP client **cố hủy HTTP exchange** nhằm giải phóng tài nguyên sớm; tuy nhiên **không có bảo đảm chính xác lúc nào hủy được áp dụng**, và request có thể đã được gửi tới server hoặc xử lý trong thread khác.

Theo giao thức:

- Với **HTTP/1.1**, nỗ lực cancel có thể khiến **TCP connection bị đóng đột ngột**. Connection đang dùng có thể không còn phù hợp để reuse.
- Với **HTTP/2**, nỗ lực cancel có thể gửi tín hiệu reset stream; một số tình huống có thể ảnh hưởng connection. Reset một stream **không phải** rollback transaction phía server.
- Nếu request hoặc Future đã hoàn tất trước đó, cancellation có thể không thay đổi kết quả đã chốt.
- Callback/continuation có thể quan sát `CancellationException`, `CompletionException`, `IOException` hoặc kết quả khác tùy lớp wrapper, thời điểm và thư viện HTTP; **không code một danh sách kết quả cứng** làm đại diện cho remote outcome.
- Lời gọi `cancel(true)` không biết cách rollback database, trả lại tiền, xóa order hoặc đảo ngược một HTTP request mà server đã commit.

### 8.1. Trạng thái Future và server side effect là hai việc độc lập

`CompletableFuture.isDone()` chỉ báo Future đã hoàn tất (bình thường, exceptional hoặc canceled). `isCancelled()` nói về **trạng thái future**, không nói về kết quả phía server. Trong một race giữa cancel và completion, bạn phải kiểm tra **trạng thái sau cùng**, không dựa vào việc client **đã thử** cancel.

Ngay cả khi `cancel(true)` trả true, điều đó không phải server acknowledgment. Tài liệu `Future.cancel` mô tả giá trị trả về là kết quả yêu cầu hủy task theo contract, **không** phải chứng cứ “server không xử lý”.

Không viết:

```java
// ANTI-PATTERN: Không suy ra outcome nghiệp vụ từ cancel.
boolean requested = future.cancel(true);
if (requested) {
    markOrderAsNeverCreated(); // Sai: server có thể đã tạo order.
}
```

Đây là đoạn minh họa sai; `markOrderAsNeverCreated` không có định nghĩa độc lập.

### 8.2. `cancel(false)` có đủ không?

Với `Future` nói chung, `cancel(boolean mayInterruptIfRunning)` là lời **yêu cầu** hủy task và boolean liên quan việc có cố interrupt thread đang chạy hay không. Nhưng implementation của HTTP client có semantics riêng; **không coi `cancel(false)` và `cancel(true)` là hai lệnh HTTP protocol chắc chắn tương đương hoặc chắc chắn khác nhau theo một mapping cố định**.

Với Java 17 default `HttpClient`, tài liệu cụ thể mô tả nỗ lực cancel HTTP exchange khi gọi `cancel(true)`. Nếu mục tiêu là ngừng I/O, dùng API/documentation của implementation đang chạy và theo dõi resource lifecycle; không suy luận từ API `CompletableFuture` chung rằng kết nối mạng đã chắc đóng.

### 8.3. Hủy derived stage khác hủy HTTP exchange gốc

Nếu một UI có:

```java
CompletableFuture<HttpResponse<String>> network = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());
CompletableFuture<String> uiStage = network.thenApply(HttpResponse::body);
uiStage.cancel(true);
```

Thì ý nghĩa cancellation có thể phụ thuộc **implementation và mối quan hệ giữa future gốc và derived stage**. Java HttpClient Javadoc nói các future derived từ cancelable future của client cũng được hỗ trợ cancellation. Không tự suy ra “hủy mỗi UI stage chắc chắn không ảnh hưởng mạng”, cũng không suy ra “chắc chắn server đã ngừng”.

Nếu muốn UI deadline **tuyệt đối không dùng như nút dừng mạng**, tách một **view stage** bằng `orTimeout` trên stage riêng và **không gọi cancel** lên HTTP future hoặc derived future. Dù vậy, phải quản lý request còn pending và giải phóng tài nguyên theo deadline dài hơn.

## 9. Java 17+: đã hủy Future nhưng tác dụng phía server vẫn có

Ví dụ cuối mô phỏng một thao tác `POST /commit`. Server đọc request, tăng counter, báo đã xử lý qua latch, rồi **chưa trả response**. Client đợi chắc chắn server đã áp dụng side effect, sau đó mới gọi `future.cancel(true)`.

Kết quả có chủ đích: cancellation được yêu cầu phía client, nhưng counter phía server đã là 1. Không có thư viện HTTP nào có thể làm “quay ngược thời gian” cho phép tăng counter này.

**Tệp `CancelDoesNotUndoWorkDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class CancelDoesNotUndoWorkDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger committed = new AtomicInteger();
        CountDownLatch businessApplied = new CountDownLatch(1);
        CountDownLatch allowResponse = new CountDownLatch(1);
        ExecutorService worker = Executors.newSingleThreadExecutor();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.setExecutor(worker);
        server.createContext("/commit", exchange -> {
            try (exchange) {
                exchange.getRequestBody().readAllBytes();
                committed.incrementAndGet();
                businessApplied.countDown();
                if (!allowResponse.await(5, TimeUnit.SECONDS)) return;
                byte[] body = "DONE".getBytes(StandardCharsets.UTF_8);
                try {
                    exchange.sendResponseHeaders(200, body.length);
                    try (var out = exchange.getResponseBody()) {
                        out.write(body);
                    }
                } catch (IOException clientGone) {
                    // Cancellation might have closed the connection.
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });
        try {
            server.start();
            URI uri = URI.create("http://localhost:"
                    + server.getAddress().getPort() + "/commit");
            CompletableFuture<HttpResponse<String>> future =
                    HttpClient.newHttpClient().sendAsync(
                            HttpRequest.newBuilder(uri)
                                    .POST(HttpRequest.BodyPublishers.ofString("PAY"))
                                    .build(),
                            HttpResponse.BodyHandlers.ofString());
            if (!businessApplied.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server did not apply work");
            }
            boolean canceled = future.cancel(true);
            System.out.println("Future cancellation accepted: " + canceled);
            System.out.println("Server side effect count: " + committed.get());
        } finally {
            allowResponse.countDown();
            server.stop(0);
            worker.shutdownNow();
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CancelDoesNotUndoWorkDemo.java
java CancelDoesNotUndoWorkDemo
```

**Stdout đã quan sát trên JDK 24 với `--release 17`:**

```text
Future cancellation accepted: true
Server side effect count: 1
```

**Kết quả không cam kết mọi môi trường luôn trả cùng boolean cho `cancel`**, vì timing và implementation có thể khác. Điều được cố định bởi test là **server đã tăng counter trước khi client gọi cancel**. `CountDownLatch` đảm bảo thứ tự này; nếu request không tới server, chương trình ném lỗi thay vì tạo chứng cứ giả.

Điểm quan trọng nhất:

- HTTP client **có thể** hủy exchange và đóng TCP connection; trong demo server thậm chí có thể gặp `IOException` khi gửi response sau khi client đã bỏ đi.
- Counter đã tăng thì **không tự trở về zero** chỉ vì Future phía client bị cancel.
- `cancel(true)` không có hợp đồng “xóa lệnh nghiệp vụ đã được server commit”.
- Đừng dùng `isCancelled` như thước đo “server đã dừng”. Đó là thuộc tính future, không phải xác nhận của server.
- Việc xử lý nghiệp vụ trong một ứng dụng thật cần transaction, idempotency key, status query hoặc protocol cancellation có xác nhận riêng; không dùng một flag client-side để đo sự thành công của rollback.

## 10. Một timeout có thể xảy ra ở nhiều nơi: đọc exception nào?

Khi code thực tế báo timeout, hãy trả lời: **thành phần nào tạo deadline?** Các ngoại lệ sau không thay thế cho nhau.

| Tình huống | Nơi quan sát | Ngoại lệ/lý do điển hình | Network đã bị hủy? |
|---|---|---|---|
| `future.get(100, MILLISECONDS)` hết hạn | Thread chờ | `TimeoutException` trực tiếp | **Không bởi thao tác get** |
| `future.orTimeout(100, MILLISECONDS)` hết hạn | CompletableFuture được gọi | `TimeoutException` là cause của exceptional completion | Không có bảo đảm |
| `completeOnTimeout(fallback)` thắng | CompletableFuture được gọi | Hoàn tất bình thường bằng fallback | Không có bảo đảm |
| `HttpRequest.Builder.timeout` hết hạn | HTTP client | `HttpTimeoutException` trong exceptional result | Client có thể kết thúc exchange; server vẫn có thể xử lý |
| `HttpClient.Builder.connectTimeout` hết hạn | Kết nối TCP/TLS | `HttpConnectTimeoutException` | Không thể suy ra mọi proxy/server đã/không làm gì ngoài bối cảnh |
| `future.cancel(true)` | Future/HTTP client | Future cancellation/error tùy timing | **Nỗ lực**, không bảo đảm thời điểm/remote rollback |
| Timeout của HTTP server | Tầng server/request handler | Server-defined `408`, `503` hoặc lỗi riêng tùy tình huống | Client-side future không tự điều khiển tất cả |
| Application deadline ở UI | Presenter/RPC gateway | `UNKNOWN`, `DEADLINE_EXCEEDED` theo contract app | Có thể chỉ dừng chờ, network vẫn hoạt động |

**Đặc biệt:** `HttpTimeoutException` là subclass của `IOException`. `TimeoutException` của `java.util.concurrent` **không** phải subclass của nó. Cần xử lý đúng tầng để không retry sai nguyên nhân.

### `join()` và `get()` bọc lỗi khác nhau

- `future.get()` hoặc `get(timeout)`: lỗi từ Future exceptional thường được gói trong `ExecutionException`.
- `future.join()`: lỗi thường được gói trong `CompletionException`.
- Nếu Future thực sự bị cancel, `get/join` có thể ném `CancellationException`.
- Không nên chỉ parse **thông điệp exception dạng String**, vì dễ phụ thuộc ngôn ngữ và implementation; dùng `instanceof` và `getCause()`.

Ví dụ minh họa:

```java
// Trích đoạn minh họa, future nhận từ sendAsync.
try {
    var response = future.get(500, TimeUnit.MILLISECONDS);
    process(response);
} catch (TimeoutException waiting) {
    log("Caller ran out of waiting time");
} catch (ExecutionException completedWithError) {
    Throwable cause = completedWithError.getCause();
    if (cause instanceof HttpTimeoutException) {
        log("HTTP request timeout");
    } else {
        log("HTTP failed: " + cause);
    }
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    log("Caller thread interrupted");
}
```

Đoạn minh họa này không độc lập vì `process`, `log` và biến `future` là thành phần app. Khi thread interrupt, **khôi phục interrupt flag** nếu framework yêu cầu, và quyết định việc cancel/network riêng.

## 11. Kết quả đến muộn và quản lý trạng thái của request

Một hệ thống cần phân biệt hai khái niệm:

- **Caller deadline:** người đang chờ không còn muốn đợi.
- **Exchange/business lifecycle:** request vẫn có thể tồn tại, nhận kết quả và cần cleanup.

### Một state machine thực tế

```text
LogicalOperation
  CREATED
      │ sendAsync(...)
      ▼
  IN_FLIGHT ───────────────────────────────► COMPLETED
      │                                       (HTTP response + business contract)
      │
      ├─ callerWaitDeadline → WAIT_EXPIRED
      │                           │
      │                           ├─ late response → COMPLETED
      │                           └─ optional cancel request → CANCEL_REQUESTED
      │                                                   │
      │                                 ┌─────────────────┴──────────────┐
      │                                 ▼                                ▼
      │                           CLIENT_STOPPED                  LATE_COMPLETED
      │                           (remote outcome UNKNOWN)       (actual response)
      │
      └─ request timeout → CLIENT_TIMED_OUT
                               (remote outcome UNKNOWN)
```

Một operation ở cấp application có thể được quan sát qua nhiều futures: network future, UI future, audit future. **Đừng lấy completion của UI future làm bằng chứng network stopped** nếu UI timeout chỉ trên derived stage.

### Gợi ý ranh giới cleanup

1. Nếu caller `get(timeout)` hết hạn nhưng hệ thống còn muốn kết quả, giữ `networkFuture` trong registry có deadline dài hơn và dùng `whenComplete` để ghi nhận sau.
2. Nếu caller timeout mà request không còn giá trị, xem xét `cancel(true)`, nhưng vẫn ghi nhận business state `UNKNOWN` nếu thiếu response xác thực.
3. Nếu chọn không cancel, phải giới hạn số request còn pending, connection pool, body memory và TTL của registry; nếu không, nhiều UI timeouts có thể tạo resource leak.
4. Nếu đã cancel, đừng giả định callback không bao giờ chạy; thiết kế terminal handling idempotent, cleanup theo kết quả thật và không ghi side effect đã rollback khi chưa được server xác nhận.
5. Không update cùng một record application hai lần khi Future callback, timeout coordinator và retry scheduler chạy đua nhau. Dùng một terminal transition có đồng bộ/atomic compare-and-set.

### Có thể “lấy lại” response sau `get(timeout)` không?

Có, nếu future gốc vẫn hoạt động và bạn còn giữ reference; ví dụ đầu của bài đã chứng minh. Nhưng nếu bạn đã gọi `orTimeout` trực tiếp lên **chính** Future đó và timeout thắng, Future ấy là terminal exceptional; response đến muộn không thể “biến” terminal future thành successful, dù network phía dưới có thể đã chạy.

Nếu cần cả **timeout ở UI** lẫn **result muộn**, đừng sửa future gốc: dùng derived stage riêng cho UI và giữ future HTTP gốc cho audit/reconciliation.

## 12. Retry sau timeout: vấn đề lớn hơn I/O

Đặt hàng, thanh toán, chuyển tiền, ghi dữ liệu hay tạo job là những thao tác **có side effect**. Client có thể không nhận response vì:

- Chờ quá hạn `get(timeout)`.
- Request timeout trong `HttpClient`.
- Connection bị cắt khi client cancel.
- TCP/TLS/proxy lỗi khi server đã hoặc chưa xử lý.
- Response đã được server tạo nhưng thất lạc trên đường.

Trong các trường hợp này, **không có quyền tự suy ra “chắc chắn chưa chạy”**. Retry request có thể dẫn đến thực thi lại ý định.

```text
POST /charge, Idempotency-Key: pay-001
  │
  ├── Server commit payment
  │
  └── Response bị mất / client hết deadline
          │
          └── Client retry
                POST /charge, Idempotency-Key: pay-001
                    │
                    └── Server tìm kết quả đã lưu và phản hồi lại
                        thay vì charge thêm lần nữa
```

Đây là **mô hình nghiệp vụ đề xuất**, không phải HTTP tự động bảo đảm exactly-once. Header `Idempotency-Key` chỉ có tác dụng khi **API server công bố và implement rõ contract**. Server cần scope key theo principal/operation, so payload fingerprint, đăng ký request atomically, lưu kết quả với transaction hoặc cơ chế đủ bền vững, và có chính sách retention/replay.

### Retry classification

| Tình huống | Có được retry ngay không? | Ghi chú |
|---|---|---|
| `GET` an toàn và idempotent theo semantics | Có thể, trong giới hạn chính sách | Vẫn cần kiểm soát overload, cache, auth, backend |
| `PUT` idempotent theo semantics | Có thể khi server tuân thủ contract | Các effect phụ như audit/metrics có thể lặp; cần hiểu trạng thái |
| `POST` tạo đơn không có idempotency key | **Không nên tự retry** chỉ từ timeout | Có nguy cơ tạo trùng |
| `POST` với key/contract chống trùng do server triển khai | Có thể theo policy của API | Dùng **cùng key** cho cùng ý định, giới hạn attempts |
| `get(timeout)` chỉ hết thời gian chờ | Ưu tiên theo dõi future gốc trước | Network future có thể hoàn tất sau đó |
| Request timeout trước khi có response | Outcome chưa biết | Truy vấn status qua ID nếu có; retry có dedup |
| `cancel(true)` | Outcome chưa biết | Không suy ra rollback |
| Ứng dụng server xác nhận hủy trước commit | Dựa vào protocol riêng | Chỉ nhận là chưa commit nếu xác nhận đáng tin cậy |

Đừng tự động retry mãi khi nhiều request timeout: server đang chậm có thể càng quá tải. Dùng giới hạn attempts, deadline toàn bộ thao tác, exponential backoff và jitter; có cơ chế circuit breaker/queue khi hệ thống lớn.

### Network cancellation không phải business cancellation

Muốn một công việc server đang chạy thực sự ngừng, cần **protocol cancellation có định danh task**, ví dụ `POST /jobs/{id}/cancel` và một trạng thái trả về. Server có thể không hủy được vì job đã xong/commit; client phải chấp nhận kết quả **already completed** hoặc **cancel rejected**. Việc đóng TCP hoặc reset HTTP/2 stream đơn thuần không mang ngữ nghĩa nghiệp vụ đầy đủ.

## 13. Kết hợp timeout và cancellation trong `sendAsync`

Một API có thể hỗ trợ cả deadline cho caller và yêu cầu hủy exchange. Điểm quan trọng là **không nhầm hai hành vi**.

### 13.1. Chỉ giới hạn thời gian UI chờ

```java
// Pseudocode Java; không phải class chạy độc lập.
CompletableFuture<HttpResponse<String>> network =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

CompletableFuture<String> ui = network
        .thenApply(resp -> resp.statusCode() + " " + resp.body())
        .completeOnTimeout("PENDING: check status later",
                200, TimeUnit.MILLISECONDS);

network.whenComplete((resp, error) -> {
    // Ghi trạng thái cuối thật, không tạo side effect không-idempotent.
    storeOutcome(resp, error);
});
```

Đây là pseudocode có `storeOutcome` chưa định nghĩa. `ui` có thể hoàn tất bằng thông báo pending nhưng `network` vẫn cần quản lý tài nguyên/timeout và reconciliation.

### 13.2. Có chủ đích yêu cầu dừng network exchange

```java
// Pseudocode: request còn có giá trị hủy được ở phía client.
CompletableFuture<HttpResponse<String>> network =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

if (userExplicitlyAbandonedRequest()) {
    boolean cancelRequested = network.cancel(true);
    recordClientCancellationAttempt(cancelRequested);
    markRemoteOutcomeUnknown();
}
```

Đây là pseudocode, không phải chương trình độc lập vì hàm điều kiện/ghi trạng thái chưa định nghĩa. **Không** gọi `markBusinessRolledBack()` chỉ do cancelRequested true.

### 13.3. Chống xử lý trùng callback

Khi timeout coordinator, completion callback và cancel path cùng chạy, phải bảo đảm chỉ một lần ghi trạng thái cuối cho **logical request**. Có thể dùng:

```text
PENDING -> SUCCEEDED
        -> FAILED
        -> TIMED_OUT_UNKNOWN
        -> CLIENT_CANCELLED_UNKNOWN

Chỉ transition thắng compare-and-set được phép thông báo người dùng.
Response muộn được ghi audit/reconciliation, không âm thầm tạo 2 transactions.
```

Nếu status đã là `TIMED_OUT_UNKNOWN` và response đến muộn `201 Created`, ứng dụng có thể bổ sung sự kiện điều chỉnh/đối chiếu business state tùy contract; không được xóa dấu vết timeout mà không kiểm tra.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Vì sao sai | Cách làm đúng |
|---|---|---|
| `get(200ms)` timeout → gửi lại POST ngay | HTTP request đầu có thể vẫn chạy | Giữ/quan sát future gốc; dùng idempotency contract |
| `get(timeout)` timeout → `future.isDone()==true` mặc định | get timeout không complete future | Kiểm tra future thật; không suy đoán |
| `orTimeout` trực tiếp lên transport future nhưng muốn response muộn | orTimeout làm future đó terminal exceptional | Dùng derived stage riêng nếu cần giữ transport future |
| `completeOnTimeout(success)` để “hết spinner” | Tạo **thành công giả** | Trả PENDING/UNKNOWN và reconciliation |
| Gọi `cancel(true)` và báo “server đã rollback” | Cancel không phải remote transaction rollback | Yêu cầu xác nhận qua protocol/business state |
| Chỉ catch `TimeoutException` ở `get` | Bỏ sót `HttpTimeoutException` wrapped | Xử lý `ExecutionException.getCause()` hoặc `CompletionException` |
| Đặt `connectTimeout` rồi coi là tổng request deadline | Chỉ quản lý giai đoạn connect | Thêm request timeout và business deadline phù hợp |
| Giả định `sendAsync` luôn hoàn tất khi đọc hết streaming body | BodyHandler có thể trả stream để caller xử lý | Đóng/consume stream đúng lifecycle |
| Không giới hạn số pending futures sau UI timeout | Memory/connection resource leak | TTL, cancellation policy, semaphore/counters |
| Không theo dõi kết quả muộn | “Unknown” không bao giờ được đối chiếu | whenComplete + request ID + server status |
| Retry với request ID mới sau uncertain outcome | Server có thể thực thi trùng | Dùng logical key ổn định và dedup |
| Đóng HTTP/1.1 connection đang dùng bởi task khác tùy tiện | Hủy exchange có thể ảnh hưởng reuse/tài nguyên | Tôn trọng ownership của HttpClient và Javadoc cancel |
| Chạy blocking `future.get()` ngay trong completion callback thread | Có thể gây starvation hoặc deadlock | Dùng compose/thenApply/whenComplete không block |
| Không restore interrupt khi catch `InterruptedException` | Mất tín hiệu dừng của thread | `Thread.currentThread().interrupt()` theo policy |
| Cho rằng cancel future = không còn callback | Completion/cancellation handlers vẫn có thể chạy | Thiết kế terminal handling và cleanup idempotent |

### Một lời cảnh báo về “ngắt thread”

`cancel(true)` không có nghĩa “server worker thread bị interrupt”. Boolean `mayInterruptIfRunning` thuộc contract Future ở máy client; nó **không có đường tự động truyền Java thread interrupt xuyên TCP** sang JVM/server khác. Nếu backend hỗ trợ cancellation cooperatively, phải implement protocol và mã phía server.

Với HTTP/2, một stream reset có thể báo phần kết thúc ở tầng transport, nhưng vẫn không chứng minh business processing chưa chạy. Không lấy RST_STREAM làm bằng chứng rollback.

## 15. Chẩn đoán thực tế: log gì để kết luận đúng?

Một hệ thống quan sát tốt cần log **tách tầng**:

```text
timestamp | logicalRequestId | attemptId | method | uriOrigin
          | callerWaitDeadline | requestTimeout | connectTimeout
          | futureState | cancelRequested | requestBytesSent
          | responseStatus | responseCompleted | errorCauseClass
          | serverBusinessId | serverCommitState | reconciliationOutcome
```

Không log credentials, token hay payload nhạy cảm. `requestBytesSent` ở client có thể khó đo chính xác: network stack/HTTP client có thể buffer, nên không được hiểu đó là byte server chắc chắn nhận.

Khi debug một incident:

1. **Xác định ngoại lệ gốc**: `TimeoutException` trực tiếp từ `get(timeout)` hay `HttpTimeoutException` trong exceptional future?
2. **Xác định deadline nào chạy trước**: caller deadline, request timeout, connect timeout, UI stage timeout, proxy/server timeout.
3. **Kiểm tra có gọi cancel hay không**: khi nào, trên future gốc hay derived stage, `cancel(true)` trả gì; không tự suy ra network đã dừng.
4. **Đối chiếu request IDs** ở cả client và server. Server có nhận request không, có bắt đầu xử lý, đã commit chưa, response có được gửi không?
5. **Kiểm tra response muộn**: future gốc còn được theo dõi không hay đã bị `orTimeout` hoàn tất exceptional?
6. **Kiểm tra retry scheduler**: có tạo request mới trước khi biết outcome không? Có dùng cùng idempotency key hay không?
7. **Xem connection behavior**: HTTP/1.1 TCP connection bị đóng khi cancel hay server tự close; HTTP/2 stream reset không đồng nghĩa rollback.
8. **Kiểm tra tài nguyên**: futures còn pending, ByteBuffer/stream chưa đóng, request queues, số outstanding exchanges và retry storm.
9. **Ghi kết luận với mức chắc chắn**: “caller wait expired”, “HTTP request timed out”, “client requested cancellation”, “server committed” là bốn khẳng định khác nhau và phải có bằng chứng riêng.

### Ma trận dấu hiệu

| Dấu hiệu | Kết luận trực tiếp | Không được tự kết luận |
|---|---|---|
| Caller nhận `TimeoutException` từ `get` | Đã hết thời gian chờ | HTTP request đã bị hủy |
| `orTimeout` làm stage exceptional | Stage hết deadline | Network/exchange chắc chắn bị ngắt |
| `HttpTimeoutException` | Request HTTP vượt deadline mà client đặt | Server chắc chắn không commit |
| `cancel(true)` trả true | Client đã yêu cầu cancel theo API | Remote không nhận hoặc rollback |
| HTTP/1.1 FIN/RST | Kết nối đã đóng/bị reset ở tầng TCP | Transaction backend chưa xảy ra |
| Server log `COMMIT id=...` | Server ghi nhận commit theo logging contract | Client chắc chắn đã thấy response |
| Client nhận `201 Created` | Client có response ứng dụng | Mọi downstream side effect đã hoàn tất nếu contract không nói vậy |
| Retry dùng key khác | Có thể là ý định mới ở server | “Chỉ là gửi lại cùng request” |
| Response đến sau UI timeout | Network vẫn đã hoạt động sau deadline UI | UI state tự cập nhật chính xác nếu không có handler |

## 16. Bài tập tư duy và câu hỏi kiểm tra

**Câu 1.** Gọi `HttpClient.sendAsync`, tiếp theo `future.get(100, MILLISECONDS)` và nhận `TimeoutException`. Future đã được cancel chưa?  
**Đáp án:** Không phải do `get`. Future có thể vẫn pending; caller chỉ hết thời gian chờ. Phải quan sát future riêng.

**Câu 2.** Khi caller timeout, server đã commit giao dịch nhưng response chưa đến. Client gửi POST lần hai với request ID mới có an toàn không?  
**Đáp án:** Không mặc định an toàn. Có thể tạo side effect trùng; cần truy vấn status hoặc retry theo idempotency contract với ID ổn định.

**Câu 3.** `CompletableFuture.orTimeout` có trả một future mới không?  
**Đáp án:** Không. Theo Javadoc nó trả **chính this future** và hoàn tất exceptional nếu deadline thắng. Nếu muốn stage riêng, tạo derived stage rồi đặt timeout trên đó.

**Câu 4.** `completeOnTimeout("OK")` trả chuỗi OK sau 200 ms. Có nghĩa server đã trả 200?  
**Đáp án:** Không. Đó là fallback do caller định nghĩa, không phải HTTP response.

**Câu 5.** Sự khác nhau giữa `TimeoutException` và `HttpTimeoutException`?  
**Đáp án:** `TimeoutException` từ `get(timeout)` là timeout chờ ở tầng concurrency; `HttpTimeoutException` là lỗi deadline của request HTTP, thuộc `IOException` và thường được bọc trong exceptional future.

**Câu 6.** `HttpClient.Builder.connectTimeout` có thay `HttpRequest.Builder.timeout` không?  
**Đáp án:** Không. Connect timeout quản lý thiết lập connection; request timeout áp dụng cho request lifecycle.

**Câu 7.** `cancel(true)` cho HTTP/1.1 có thể đóng connection. Vậy server chắc chắn ngừng xử lý?  
**Đáp án:** Không. Server có thể đã nhận/commit trước khi connection đóng; cần protocol cancellation có xác nhận nếu muốn biết server dừng.

**Câu 8.** Trong HTTP/2, reset stream có tương đương rollback database không?  
**Đáp án:** Không. Reset stream là hành động tầng giao thức truyền tải; business operation là trạng thái độc lập ở server.

**Câu 9.** `Future.get()` ném `ExecutionException(cause=HttpTimeoutException)`. Có đúng là caller `get(timeout)` hết hạn không?  
**Đáp án:** Không nhất thiết. Đây là chính HTTP request đã hoàn tất exceptional; caller có thể còn thời gian chờ.

**Câu 10.** `sendAsync` dùng `BodyHandlers.ofInputStream` trả về response với InputStream. Có thể bỏ stream mà không cleanup vì future đã done?  
**Đáp án:** Không. Caller phải consume hoặc close stream theo contract; Future hoàn tất không có nghĩa body stream được giải phóng tự động trong mọi kiểu handler.

**Câu 11.** UI chỉ muốn chờ 200 ms, nhưng backend có thể mất 3 giây. Thiết kế nào giúp giữ kết quả muộn?  
**Đáp án:** Đặt timeout trên derived UI stage, giữ Future HTTP gốc trong registry với deadline tài nguyên riêng và xử lý response muộn bằng `whenComplete`.

**Câu 12.** `cancel(true)` trả false. Có thể kết luận server chưa nhận gì không?  
**Đáp án:** Không. Future có thể đã hoàn tất hoặc hủy không còn khả thi; giá trị boolean không chứng minh trạng thái remote.

**Câu 13.** User bấm “Cancel” sau khi đơn hàng đã được tạo. Đóng connection có xóa đơn?  
**Đáp án:** Không. Cần một API nghiệp vụ hủy đơn và xem kết quả của nó; đôi khi đơn đã ở trạng thái không thể hủy.

**Câu 14.** Vì sao `orTimeout` đặt trên chính network future có thể làm mất khả năng đọc response muộn qua future đó?  
**Đáp án:** Khi timeout thắng, future ấy đã terminal exceptional; nó không tự chuyển thành successful sau khi response tới. Nếu muốn giữ kết quả thật, không đặt timeout hoàn tất trực tiếp lên future gốc.

**Câu 15.** Thread đợi Future bị `InterruptedException`. Điều đó có tự gửi cancel HTTP exchange không?  
**Đáp án:** `Future.get` bị interrupt không tự có nghĩa HTTP exchange đã hủy. Cần quyết định cancel riêng và khôi phục interrupt flag theo chính sách ứng dụng.

**Câu 16.** Muốn tránh hai lần charge khi retry vì HTTP timeout, phải có yếu tố gì phía server?  
**Đáp án:** API contract với key/ID ổn định, atomic dedup, payload fingerprint, business transaction/retention và truy vấn trạng thái khi outcome chưa biết.

**Câu 17.** Khi `cancel` và response hoàn tất gần như đồng thời, UI nên lấy side effect từ `future.isCancelled` hay trạng thái giao dịch server?  
**Đáp án:** Trạng thái giao dịch đã được server xác nhận mới là nguồn cho business outcome; `isCancelled` là thuộc tính future phía client.

**Câu 18.** Nếu không cancel sau UI timeout, có thể bỏ mặc mọi Future pending mãi không?  
**Đáp án:** Không. Cần deadline network dài hơn, giới hạn outstanding, cleanup stream và registry, metrics và reconciliation.

## 17. Checklist vận dụng

Trước khi dùng timeout/cancel trong Java HTTP async:

- [ ] Xác định đúng loại deadline: **wait**, **CompletableFuture stage**, **HTTP request**, **connect** hay **business operation**.
- [ ] `get(timeout)` hết hạn **không** được biến thành tuyên bố network canceled.
- [ ] Nếu cần kết quả muộn, giữ `sendAsync` Future gốc và chỉ timeout **derived view**.
- [ ] `orTimeout`/`completeOnTimeout` **sửa chính future được gọi**, không tự tạo stage mới.
- [ ] Không dùng fallback success để giả mạo kết quả từ server.
- [ ] Với request deadline, bắt đúng `HttpTimeoutException`, không nhầm `TimeoutException`.
- [ ] Với `cancel(true)`, hiểu đây là **nỗ lực** hủy exchange trong HTTP client mặc định, không bảo đảm remote rollback.
- [ ] Không dựa vào `cancel`, `isCancelled`, TCP FIN/RST hay HTTP/2 RST_STREAM làm bằng chứng nghiệp vụ chưa chạy.
- [ ] Phân biệt HTTP/1.1 connection closure với HTTP/2 stream cancellation; giám sát tác động tới reuse.
- [ ] Với POST/side effect, không retry bằng ID mới khi outcome chưa biết; dùng idempotency key theo hợp đồng server.
- [ ] Đối chiếu status server hoặc transaction ID nếu client timeout/cancel.
- [ ] Quản lý pending futures, request-body sources, response-body streams, connection resources và late callbacks.
- [ ] Kiểm thử bằng controlled server latches, không dựa vào `Thread.sleep` để đoán thread/network timing.
- [ ] Log riêng `callerWaitExpired`, `httpRequestTimedOut`, `cancelRequested` và `serverBusinessOutcome`.
- [ ] Khi có interruption, xử lý `InterruptedException` và restore interrupt flag theo policy.
- [ ] Không chặn event-loop/completion threads để chờ một Future có thể cần chính thread đó để hoàn tất.

**Ghi nhớ cốt lõi:** `Future.get(timeout)` chỉ nói **caller đã hết thời gian chờ**. `orTimeout` nói **stage đã hết deadline**, `HttpRequest.timeout` nói **HTTP request đã vượt deadline của client**, còn `cancel(true)` chỉ **yêu cầu cố ngừng exchange**. Không trường hợp nào tự bảo đảm **server chưa xử lý hoặc đã rollback**. Muốn kết luận business outcome, cần **response/protocol acknowledgment hoặc kiểm tra trạng thái server**.

### Tài liệu API chính thức (Java 17)

- [`java.util.concurrent.Future` — `get(timeout)` và `cancel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [`CompletableFuture` — `orTimeout`, `completeOnTimeout`, `copy`, `isDone`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [`HttpClient` — `sendAsync` và cancellation của default client](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [`HttpRequest.Builder` — `timeout(Duration)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [`HttpTimeoutException` — request HTTP timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html)
- [`HttpConnectTimeoutException` — connect timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html)
- [`HttpResponse.BodyHandlers` — xử lý body trả về](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)

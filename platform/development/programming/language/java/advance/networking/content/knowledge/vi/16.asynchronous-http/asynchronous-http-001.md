# sendAsync trả CompletableFuture và mô tả việc trao đổi HTTP đang diễn ra

## 1. Mục tiêu học tập

Java `java.net.http.HttpClient` hỗ trợ gửi HTTP theo cách đồng bộ bằng `send(...)` hoặc bất đồng bộ bằng **`sendAsync(...)`**. Điểm đặc biệt của `sendAsync` là **trả về ngay một `CompletableFuture<HttpResponse<T>>`** biểu diễn kết quả của quá trình gửi request và nhận response **đang diễn ra** (in-flight HTTP exchange), thay vì khiến luồng gọi chờ response hoàn tất rồi mới trả về.

Đây không phải một object “chỉ để in kết quả sau này”: `CompletableFuture` là một **đại diện cho kết quả tương lai**, có thể hoàn thành bình thường với `HttpResponse<T>`, hoàn thành ngoại lệ khi gửi/nhận thất bại hoặc bị hủy. Nó còn là cơ chế khai báo các bước tiếp theo bằng các hàm như `thenApply`, `thenCompose`, `thenAccept`, `whenComplete`, `exceptionally` và `allOf`.

Sau bài học, bạn cần:
1. Viết đúng chữ ký `sendAsync` và hiểu type parameter `T` đến từ `HttpResponse.BodyHandler<T>`.
2. Giải thích sự khác biệt giữa **đã bắt đầu HTTP exchange**, **response đã sẵn sàng theo BodyHandler**, và **toàn bộ body đã được ứng dụng tiêu thụ**.
3. Hiểu future có thể **chưa hoàn thành** khi `sendAsync` trả về; không suy ra trạng thái từ thời điểm gọi.
4. Dùng các callback/chaining API để xử lý status/body **không block luồng caller**.
5. Phân biệt HTTP 404/500 (phản hồi HTTP bình thường) với lỗi I/O/timeout/SSL làm future hoàn thành ngoại lệ.
6. Kết hợp nhiều request, điều phối phụ thuộc tuần tự, áp deadline và cancellation có kiểm soát.
7. Chạy hai chương trình Java 17+ có server **loopback**, kiểm chứng trạng thái in-flight và trường hợp streaming body.
8. Tránh các lỗi production: gọi `join()` quá sớm, khóa event loop/UI, resource leak khi streaming, retry side effects, dùng callbacks nặng trên thread không phù hợp.

## 2. Đồng bộ `send` và bất đồng bộ `sendAsync`

Hai chữ ký quan trọng trong Java 17:

```java
<T> HttpResponse<T> send(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler)
        throws IOException, InterruptedException;

<T> CompletableFuture<HttpResponse<T>> sendAsync(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler);
```

Đây là **chữ ký API rút gọn** để học, không phải chương trình Java độc lập; các phương thức thực tế thuộc `HttpClient` và có các modifier/generic phù hợp. `sendAsync` cũng có overload nhận `PushPromiseHandler<T>` khi ứng dụng xử lý HTTP/2 server push.

So sánh:

| Ý | `send(...)` | `sendAsync(...)` |
| --- | --- | --- |
| Kết quả trực tiếp | `HttpResponse<T>` | `CompletableFuture<HttpResponse<T>>` |
| Luồng caller | Chờ đến khi phương thức có response theo handler hoặc ném lỗi | Nhận future sớm và có thể tiếp tục công việc khác |
| Lỗi mạng thông thường | `IOException`/interruption như khai báo | Future thường hoàn thành ngoại lệ; một số lỗi tham số vẫn có thể bị ném trực tiếp |
| Ghép các bước | Code tuần tự | Chaining `thenApply`/`thenCompose`/`handle`... |
| Chờ chủ động | Việc gọi `send` là thao tác blocking | Có thể `join()/get()`, nhưng làm vậy sẽ block tại điểm chờ |
| Body lớn/streaming | Do `BodyHandler<T>` quyết định khi nào response được trả | **Cũng do `BodyHandler<T>` quyết định** khi nào future hoàn thành |

**Bất đồng bộ không đồng nghĩa HTTP request chạy “nhanh hơn” hoặc biến mất network latency.** Nó thay đổi **cách chương trình điều phối thời gian chờ**, cho phép caller làm việc khác trong lúc I/O đang tiến hành.

## 3. CompletableFuture mô tả một HTTP exchange

Hình dung:

```text
Luồng ứng dụng                         HttpClient / network
       │                                      │
       ├── client.sendAsync(request, handler) ►│
       │                                      │
       ◄── CompletableFuture<Response<T>> ───┤
       │    (có thể vẫn PENDING)             │
       │                                      ├─ DNS/connect nếu cần
       ├── tiếp tục xử lý khác                ├─ TLS handshake nếu HTTPS
       │                                      ├─ gửi request (có thể streaming)
       │                                      ├─ nhận status và headers
       │                                      ├─ chọn BodySubscriber theo handler
       │                                      ├─ nhận/tiêu thụ body tùy handler
       │                                      │
       │     future hoàn thành ◄─────────────┤
       │     bình thường hoặc ngoại lệ       │
       ▼                                      │
  callback/thenApply ...                      │
```

Đây là sơ đồ **logic**, không khẳng định đúng mỗi bước một thread hay mọi request đều phải mở TCP connection mới. HttpClient có thể tái sử dụng kết nối, dùng HTTP/2 multiplexing, authentication và redirects tùy cấu hình.

Các điểm cần phân biệt:

- **Future được trả về:** object đại diện cho kết quả. Nó có thể chưa hoàn thành, đã hoàn thành rất nhanh hoặc đang hoàn thành; không có cam kết luôn phải chờ một khoảng thời gian dương mới được completed.
- **`future.isDone()`:** trả true nếu future đã hoàn thành bình thường, ngoại lệ hoặc cancel. Nó **không** cho biết % bytes đã tải.
- **`future.isCompletedExceptionally()`:** true nếu future hoàn thành ngoại lệ, bao gồm cancellation theo API.
- **`future.isCancelled()`:** true khi future được đánh dấu đã hủy.
- **`future.join()`/`get()`:** lấy kết quả khi future xong hoặc **chờ** nếu chưa xong; gọi chúng ngay sau `sendAsync` có thể làm lợi ích bất đồng bộ biến mất.

Vì vậy, muốn giữ mô hình bất đồng bộ, hãy mô tả những việc cần xảy ra **sau** khi response sẵn sàng bằng callback/stage, chứ không lập tức blocking trong luồng xử lý request hiện tại.

## 4. T là kiểu body, không phải “kiểu HTTP packet”

`sendAsync` là generic:

```java
CompletableFuture<HttpResponse<String>> f1 =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

CompletableFuture<HttpResponse<byte[]>> f2 =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofByteArray());

CompletableFuture<HttpResponse<Void>> f3 =
        client.sendAsync(request, HttpResponse.BodyHandlers.discarding());
```

Các dòng là **mảnh code**, giả định `client` và `request` đã được tạo, imports `java.net.http.*` và `java.util.concurrent.CompletableFuture`.

`HttpResponse.BodyHandler<T>` quyết định **cách body bytes được xử lý**, ví dụ giải mã `String`, lưu `byte[]`, ghi file, trả `InputStream` hoặc bỏ nội dung. Nó không chỉ thay đổi kiểu Java generic; nó còn ảnh hưởng **khi nào response tương lai được coi là có thể trả cho application**.

| Handler | `T` | Khi nào response/future thường sẵn sàng? |
| --- | --- | --- |
| `BodyHandlers.ofString()` | `String` | Sau khi body đã được nhận đầy đủ và giải mã thành string |
| `BodyHandlers.ofByteArray()` | `byte[]` | Sau khi toàn bộ body bytes đã được nhận |
| `BodyHandlers.ofFile(path)` | `Path` | Khi body đã được ghi hoàn tất vào file theo handler |
| `BodyHandlers.discarding()` | `Void` | Khi handler đã nhận và loại bỏ body |
| `BodyHandlers.ofInputStream()` | `InputStream` | **Sau khi response headers đã nhận đủ; body có thể vẫn đang đến** |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Response có thể sẵn sàng sau headers; dữ liệu sẽ tiếp tục qua publisher/subscription |
| `BodyHandlers.ofLines()` | `Stream<String>` | Response có thể sẵn sàng khi body chưa được nhận/đọc hết |

Tuyên bố “future hoàn thành nghĩa là toàn bộ response body đã được tải xong” chỉ đúng **đối với những handler có completion gắn với việc thu thập body đầy đủ**, chẳng hạn `ofString`/`ofByteArray`. Nó **không đúng tổng quát** với `ofInputStream` hay `ofPublisher`.

Một response được tạo thành công **không tự xác nhận ứng dụng đã đọc hết hoặc đóng** streaming body. Với `InputStream`, phải đọc tới EOF hoặc đóng stream để tài nguyên của HTTP exchange có thể được giải phóng đúng.

## 5. Tạo client và request trước khi sendAsync

Đoạn mẫu tối thiểu:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/items"))
        .timeout(Duration.ofSeconds(8))
        .header("Accept", "application/json")
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request, HttpResponse.BodyHandlers.ofString());
```

Đây là **mảnh code**, không phải một chương trình chạy offline: URI cần mạng/certificate hợp lệ; phải import `java.net.URI`, `java.net.http.HttpClient/HttpRequest/HttpResponse`, `java.time.Duration` và `java.util.concurrent.CompletableFuture`.

Giải thích:
- `HttpClient` là object có thể tái sử dụng giữa nhiều request; việc tái sử dụng cho phép connection pooling theo implementation.
- `HttpRequest` mô tả một request được gửi; nó không phải HTTP response và không bắt đầu I/O chỉ vì được `build()`.
- `sendAsync(...)` khởi động logical HTTP exchange và trả future tương ứng.
- `BodyHandlers.ofString()` yêu cầu thư viện thu thập body và cung cấp `String` khi response sẵn sàng.
- `connectTimeout(...)` giới hạn bước thiết lập kết nối theo API; `request.timeout(...)` giới hạn việc chờ response theo request semantics. Không dùng một timeout đó để suy ra toàn bộ business transaction đã hoàn tất trong mọi mô hình streaming.
- Nếu dùng credentials, proxies, cookies, redirects hoặc SSLContext riêng, cấu hình chúng với client trước khi build; không tự cho rằng asynchronous method thay thế chính sách an toàn.

**Không cần** viết `new Thread(() -> client.send(...))` để có API async tiêu chuẩn: `sendAsync` đã cung cấp một abstraction tích hợp HTTP exchange và `CompletableFuture`.

## 6. Trạng thái của future và vòng đời logical exchange

Một `CompletableFuture<HttpResponse<T>>` có các trạng thái khái niệm:

```text
                              ┌─────────────────────┐
      sendAsync(...) ───────► │ CHƯA HOÀN THÀNH      │
                              │ pending / in-flight  │
                              └─────────┬───────────┘
                                        │
                ┌───────────────────────┼───────────────────────┐
                ▼                       ▼                       ▼
      Hoàn thành bình thường   Hoàn thành ngoại lệ         Bị cancel
      HttpResponse<T>          I/O / TLS / timeout         CancellationException
                │                       │                       │
                └───────────────────────┴───────────────────────┘
                                        │
                                 future.isDone() = true
```

Đây là mô hình học tập. Tại thời điểm `sendAsync` trả về, future **có thể** đã completed nhanh; không được test code bằng giả định “future luôn pending ít nhất 100ms”. Ngược lại, nếu server giữ kết quả thì future có thể pending lâu.

Trạng thái future **không nhất thiết đồng nhất** với trạng thái transport:
- Một response HTTP 500 có body hợp lệ có thể **hoàn thành future bình thường**.
- Một streaming body handler có thể cho future bình thường **trước khi** tất cả response bytes đến.
- `cancel(true)` có thể đánh dấu future cancelled, nhưng HTTP request có thể đã gửi tới server; cancellation là nỗ lực dừng, không phải bảo đảm server chưa xử lý.
- Một exception từ callback `thenApply` có thể khiến **dependent stage** thất bại, trong khi **future HTTP gốc** đã hoàn thành bình thường.

Nên phân biệt bốn trạng thái quan sát:
1. Request đã được **tạo**.
2. Request đã được **gửi/đang xử lý** trong network.
3. Future response đã **completed** theo handler.
4. Business logic đã **xử lý kết quả thành công**.

Chúng không là một boolean duy nhất.

## 7. Java 17+ runnable: chứng minh future đang in-flight

Ví dụ đầu tiên tạo HTTP server **chỉ trên 127.0.0.1** bằng `com.sun.net.httpserver.HttpServer`. Server nhận request `/wait` nhưng **chủ động chờ một CountDownLatch** trước khi gửi response. Nhờ đó, ứng dụng có thể chứng minh:
- Server đã nhận request thật.
- Future được trả về vẫn chưa hoàn thành, vì response chưa được phép gửi.
- Caller có thể lập pipeline bằng `thenApply` mà không chặn.
- Khi server gửi response, future và các stage liên tiếp hoàn thành.
- HTTP 404 cũng là **một HttpResponse bình thường**, không phải exception từ `sendAsync`.

Lưu file đúng tên **`AsyncExchangeDemo.java`**:

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
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class AsyncExchangeDemo {
    private static void respond(HttpExchange exchange, int status, String text)
            throws IOException {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, body.length);
        try (var out = exchange.getResponseBody()) {
            out.write(body);
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch arrived = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/wait", exchange -> {
            arrived.countDown();
            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    respond(exchange, 504, "timed-out");
                    return;
                }
                respond(exchange, 200, "hello");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                exchange.close();
            }
        });
        server.createContext("/missing", exchange ->
                respond(exchange, 404, "not-found"));
        server.start();

        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(base.resolve("/wait"))
                    .timeout(Duration.ofSeconds(8)).GET().build();
            CompletableFuture<HttpResponse<String>> inFlight = client.sendAsync(
                    request, HttpResponse.BodyHandlers.ofString());
            if (!arrived.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server did not receive request");
            }
            System.out.println("request-arrived=true");
            System.out.println("in-flight=" + !inFlight.isDone());

            CompletableFuture<String> processed = inFlight
                    .thenApply(response -> {
                        if (response.statusCode() != 200) {
                            throw new IllegalStateException("Unexpected status");
                        }
                        return response.body();
                    })
                    .thenApply(String::toUpperCase);
            release.countDown();
            System.out.println("processed=" + processed.get(5, TimeUnit.SECONDS));
            System.out.println("completed=" + inFlight.isDone());

            HttpRequest missing = HttpRequest.newBuilder(
                    base.resolve("/missing")).GET().build();
            CompletableFuture<HttpResponse<String>> missingFuture =
                    client.sendAsync(
                            missing, HttpResponse.BodyHandlers.ofString());
            HttpResponse<String> missingResponse =
                    missingFuture.get(5, TimeUnit.SECONDS);
            System.out.println("http-status=" + missingResponse.statusCode());
            System.out.println("exceptional="
                    + missingFuture.isCompletedExceptionally());
        } finally {
            release.countDown();
            server.stop(0);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac AsyncExchangeDemo.java
java AsyncExchangeDemo
```

Output đã kiểm chứng khi chạy với JDK hỗ trợ Java 17 API:

```text
request-arrived=true
in-flight=true
processed=HELLO
completed=true
http-status=404
exceptional=false
```

### Giải thích từng dòng output

- `request-arrived=true`: handler `/wait` của server đã chạy. Latch `arrived` khiến main thread chỉ in sau khi server thấy request.
- `in-flight=true`: server **chưa được release** nên chưa gửi response; `BodyHandlers.ofString()` chưa thể tạo `String` từ response chưa xuất hiện. Do đó `!inFlight.isDone()` là true trong test được kiểm soát.
- `processed=HELLO`: main thread gọi `release.countDown()`, server gửi `"hello"`; future hoàn thành bình thường và hai `thenApply` chạy tuần tự: kiểm tra `200` rồi đổi text sang chữ hoa.
- `completed=true`: sau khi `processed.get(...)` đã hoàn tất, future HTTP cha chắc chắn đã hoàn thành. `get` ở đây chỉ dùng để **chờ phép thử có thể kết thúc**, không phải mẫu dùng ngay sau sendAsync trong event loop production.
- `http-status=404`: server trả HTTP 404 có body hợp lệ; `HttpClient` vẫn tạo `HttpResponse<String>`.
- `exceptional=false`: status 404 **không làm future hoàn thành ngoại lệ**. Chính ứng dụng phải tự xác định status nào được coi là lỗi nghiệp vụ.

### Tại sao dùng CountDownLatch thay Thread.sleep?

Nếu làm:

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
System.out.println(future.isDone());
```

thì kết quả phụ thuộc tốc độ server/network: có thể true hoặc false. Việc ngủ vài millisecond cũng không đảm bảo đúng lịch thực thi. Ví dụ có latch cho phép xác định chắc chắn response chưa được gửi khi kiểm tra `isDone()`. **Không dùng latches này để bắt server production đợi**; đây là kỹ thuật test deterministic.

## 8. Chaining: xử lý kết quả sau này mà không blocking caller

`CompletableFuture` cho phép tạo các dependent stages:

```java
CompletableFuture<String> bodyFuture = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(HttpResponse::body);

CompletableFuture<Integer> lengthFuture =
        bodyFuture.thenApply(String::length);
```

Đây là mảnh code, giả định `client` và `request` có sẵn. `thenApply` biến giá trị:
- `HttpResponse<String>` thành `String`.
- `String` thành `Integer`.
- Các stage **không cần** block thread đang tạo pipeline nếu future chưa hoàn thành.

Điều không nên làm trong event loop/UI thread:

```java
HttpResponse<String> response = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .join(); // block cho tới khi future kết thúc
```

Mảnh code vẫn **hợp lệ** về Java, nhưng nó biến caller thành người chờ; thường không phải mục tiêu chọn `sendAsync`. Nếu code chỉ cần một request đồng bộ trong chương trình CLI đơn giản, `send(...)` có thể diễn đạt ý đồ rõ hơn.

### Kiểu của mỗi stage

```text
CompletableFuture<HttpResponse<String>>
         │ thenApply(HttpResponse::body)
         ▼
CompletableFuture<String>
         │ thenApply(String::length)
         ▼
CompletableFuture<Integer>
```

`thenApply` không tạo một HTTP request mới; nó tạo một **dependent future**. Nếu HTTP future cha thất bại, stage tiếp theo thường không gọi transform function và truyền thất bại xuống chain, trừ khi một stage handle/exceptionally biến đổi kết quả.

## 9. thenApply, thenAccept, thenRun và whenComplete

| Hàm | Callback nhận | Giá trị trả cho dependent future | Dùng khi |
| --- | --- | --- | --- |
| `thenApply(fn)` | Giá trị thành công `T` | `CompletableFuture<U>` | Chuyển response thành model/body/result |
| `thenAccept(consumer)` | Giá trị thành công `T` | `CompletableFuture<Void>` | Ghi output, cập nhật state/metrics |
| `thenRun(action)` | Không nhận giá trị | `CompletableFuture<Void>` | Thực hiện bước tiếp khi stage cha thành công |
| `whenComplete((value,error) -> ...)` | Giá trị hoặc lỗi | Future cùng kết quả/kiểu (trừ lỗi do action ném) | Logging/cleanup, không tự phục hồi lỗi |
| `handle((value,error) -> U)` | Giá trị hoặc lỗi | `CompletableFuture<U>` | Tạo kết quả thay thế hoặc biến đổi cả success/failure |
| `exceptionally(error -> T)` | Lỗi | `CompletableFuture<T>` | Phục hồi lỗi bằng một giá trị cùng kiểu |

Ví dụ xử lý status trước khi lấy body:

```java
CompletableFuture<String> result = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(response -> {
            if (response.statusCode() / 100 != 2) {
                throw new IllegalStateException(
                        "Unexpected HTTP status: " + response.statusCode());
            }
            return response.body();
        })
        .whenComplete((body, error) -> {
            if (error != null) {
                System.err.println("Request failed");
            }
        });
```

Đây là mảnh code. Nếu server trả 404, HTTP future gốc **có thể thành công**, nhưng `thenApply` tự ném `IllegalStateException`, làm **dependent `result`** hoàn thành ngoại lệ. Không nhầm exception từ nghiệp vụ với network exception của `sendAsync`.

### Một cảnh báo về callback

`thenApply` không có hậu tố `Async` có thể được thực thi bởi thread **làm complete future cha** hoặc thread **đăng ký callback sau khi future đã complete**; không được dựa vào thread name hay thứ tự scheduler. Trong event-driven service, callback phải đủ nhanh hoặc chuyển việc nặng sang executor phù hợp. Đừng đặt CPU-bound parse khổng lồ, DB query blocking hay `Thread.sleep` dài trong callback I/O.

## 10. thenApplyAsync và executor: chủ động đặt ranh giới thread

Nếu xử lý sau response tốn CPU hoặc cần tách khỏi I/O completion path:

```java
ExecutorService workers = Executors.newFixedThreadPool(4);

CompletableFuture<Result> stage = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApplyAsync(response -> parseBusinessData(response.body()),
                workers);
```

Đây là **mảnh code**, không compile độc lập; `Result` và `parseBusinessData` là kiểu/hàm ứng dụng, imports `java.util.concurrent.*`. Cần shutdown `workers` khi ứng dụng kết thúc.

`thenApplyAsync(..., workers)` đưa task transform sang executor được truyền. Nếu dùng `thenApplyAsync(fn)` không cung cấp executor, CompletableFuture dùng cơ chế async execution mặc định theo contract; không nên giả định đó là **cùng executor** với `HttpClient.Builder.executor(...)`.

### HttpClient.Builder.executor(...) có tác dụng gì?

`HttpClient.newBuilder().executor(executor)` cung cấp executor cho một số công việc bất đồng bộ/phụ thuộc theo implementation và tài liệu API. Nó **không** có nghĩa mọi callback của mọi `CompletableFuture` chắc chắn chạy trên executor ấy. Thiết kế callback cần dùng biến thể `thenApplyAsync(..., executor)` khi thực sự muốn ràng buộc một bước cụ thể vào thread pool mình quản lý.

Trong GUI JavaFX/Swing, không cập nhật UI tùy tiện từ callback thread. Đưa kết quả về JavaFX Application Thread hoặc Swing Event Dispatch Thread bằng cơ chế framework. Trong servlet/reactive/event-loop server, không gọi blocking `join` ngay trên request/event-loop thread.

## 11. thenCompose: khi request thứ hai phụ thuộc request thứ nhất

Nếu request B chỉ có thể gửi **sau khi** response A được kiểm tra, `thenCompose` phù hợp. Ví dụ logic: lấy thông tin xác thực hoặc một ID ở bước đầu, sau đó gọi endpoint tiếp.

```java
CompletableFuture<HttpResponse<String>> secondResponse = client
        .sendAsync(firstRequest, HttpResponse.BodyHandlers.ofString())
        .thenCompose(first -> {
            if (first.statusCode() != 200) {
                return CompletableFuture.failedFuture(
                        new IllegalStateException("Step A failed"));
            }
            HttpRequest next = HttpRequest.newBuilder(
                    URI.create("https://api.example.com/next"))
                    .GET()
                    .build();
            return client.sendAsync(
                    next, HttpResponse.BodyHandlers.ofString());
        });
```

Đây là **mảnh code**, không gửi mạng khi chỉ đọc; `client` và `firstRequest` phải có sẵn, và URI phải được ứng dụng cho phép. Các import cần có `URI`, `HttpRequest`, `HttpResponse`, `CompletableFuture`. `failedFuture` có từ Java 9, nên dùng được trong Java 17.

**Khác biệt cốt lõi:**
- `thenApply(first -> client.sendAsync(second,...))` tạo future **lồng nhau**: `CompletableFuture<CompletableFuture<HttpResponse<String>>>`.
- `thenCompose(first -> client.sendAsync(second,...))` **flatten** hai tầng thành một `CompletableFuture<HttpResponse<String>>`.

Tránh tự lấy `first.body()` làm URL/host của request B mà không validate. Với input không đáng tin, dùng allowlist scheme/host/port và chính sách chống SSRF trước khi tạo request tiếp theo.

## 12. Nhiều request độc lập: allOf và ghép kết quả

Khi có hai HTTP requests độc lập, có thể khởi động cả hai trước khi chờ:

```java
CompletableFuture<HttpResponse<String>> fa =
        client.sendAsync(requestA, HttpResponse.BodyHandlers.ofString());
CompletableFuture<HttpResponse<String>> fb =
        client.sendAsync(requestB, HttpResponse.BodyHandlers.ofString());

CompletableFuture<String> combined = CompletableFuture
        .allOf(fa, fb)
        .thenApply(ignored ->
                fa.join().body() + "|" + fb.join().body());
```

Đây là **mảnh code**, cần `requestA`/`requestB` hợp lệ và `client` có sẵn. `allOf(...)` hoàn tất khi tất cả futures đã hoàn thành; trong `thenApply` của `allOf` đã thành công thì `fa`/`fb` cũng đã complete bình thường, nên `join()` trên chúng không còn đợi network. Tuy nhiên `allOf` không trả trực tiếp list các `HttpResponse`, vì vậy phải giữ reference các future thành viên.

Lưu ý:
- Nếu một future thất bại, `allOf` cũng có thể hoàn thành ngoại lệ; dependent `thenApply` xử lý success sẽ không chạy.
- `allOf` không **tự hủy** mọi request khác khi một request bị lỗi. Cần chính sách riêng nếu muốn cancel phần còn lại.
- HTTP/2 multiplexing/connection pooling do HttpClient quyết định, không phải số lượng `CompletableFuture` đảm bảo có đúng từng ấy TCP connections.
- Không tạo hàng chục nghìn `sendAsync` đồng thời mà không giới hạn memory, connection pool, server rate và pending responses. Bất đồng bộ cần **concurrency limit/backpressure**, không phải vô hạn.

### anyOf và applyToEither

- `CompletableFuture.anyOf(...)` hoàn thành theo future hoàn tất đầu tiên (kể cả exceptional), trả `Object` nên mất type information cụ thể.
- `applyToEither` phù hợp khi muốn kết quả thành công từ một trong hai computations tương thích, nhưng phải hiểu exception handling và side effects của những request vẫn đang chạy.
- Tránh “đua” hai HTTP POST tạo giao dịch nếu không có idempotency. Future đầu tiên hoàn thành không tự chứng minh request còn lại chưa đến server.

## 13. HTTP lỗi khác với exceptional completion

Đây là lỗi nhận thức phổ biến nhất khi xử lý async HTTP:

```text
HTTP request được gửi thành công
  ├─ server trả 200 -> HttpResponse (future bình thường)
  ├─ server trả 404 -> HttpResponse (future bình thường)
  ├─ server trả 500 -> HttpResponse (future bình thường)
  └─ server trả 302 -> HttpResponse hoặc tự redirect theo policy

HTTP exchange gặp lỗi transport/protocol trước kết quả:
  ├─ không kết nối được
  ├─ TLS/certificate/handshake lỗi
  ├─ timeout
  ├─ I/O hoặc body handling lỗi
  └─ future có thể complete exceptionally
```

`HttpResponse.BodyHandlers.ofString()` **không tự ném exception khi status không phải 2xx**. Đó là trách nhiệm của business code.

Ví dụ trong demo mục 7:

```text
http-status=404
exceptional=false
```

`future.isCompletedExceptionally()==false` nghĩa là HTTP future có response 404 như đã thiết kế; chưa có kiểm tra nghiệp vụ. Muốn status 404 làm downstream future thất bại, tự viết:

```java
CompletableFuture<String> verified = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(response -> {
            int code = response.statusCode();
            if (code < 200 || code >= 300) {
                throw new IllegalStateException("HTTP " + code);
            }
            return response.body();
        });
```

Như vậy `verified` mới hoàn thành ngoại lệ khi nhận 4xx/5xx. **HTTP future gốc** vẫn hoàn thành bình thường. Khi debug, cần biết **stage nào phát sinh exception** để tránh nhầm server đã unreachable.

## 14. Cách lấy exception: get, join, whenComplete và exceptionally

`CompletableFuture` có thể lỗi ở phần network hoặc ở callback. Có các cách quan sát:

| Cách | Khi hoàn thành thành công | Khi hoàn thành lỗi |
| --- | --- | --- |
| `future.get()` | Trả `T`; có thể block | Ném `ExecutionException` bao cause; hoặc interruption/cancellation |
| `future.join()` | Trả `T`; có thể block | Ném `CompletionException` bao cause; hoặc cancellation |
| `whenComplete((v,e) -> ...)` | Nhận value và `e==null` | Nhận error; chủ yếu quan sát/log/cleanup |
| `handle((v,e) -> newValue)` | Có thể chuyển value | Có thể chuyển exception thành giá trị khác |
| `exceptionally(e -> fallback)` | Giữ nguyên value | Chạy fallback và cho dependent stage hoàn thành bình thường nếu fallback không ném |

Ví dụ:

```java
CompletableFuture<String> safe = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(HttpResponse::body)
        .exceptionally(error -> {
            logFailure(error);
            return "unavailable";
        });
```

Đây là **mảnh code**, `logFailure` là hàm ứng dụng phải tự định nghĩa. `exceptionally` khiến dependent `safe` **có thể** hoàn thành bình thường với `"unavailable"` dù HTTP exchange thực tế thất bại. Nếu dữ liệu quan trọng, **đừng** trả fallback và báo business success một cách im lặng. Có thể dùng `whenComplete` để log mà vẫn truyền lỗi xuống caller.

### Exceptions bao nhiều tầng

`join()` có thể ném `CompletionException`, còn `get()` thường ném `ExecutionException` khi computation thất bại. Cần kiểm tra `getCause()`/cause chain, ví dụ underlying `HttpConnectTimeoutException`, `HttpTimeoutException`, `SSLHandshakeException` hoặc `IOException`. Đừng chỉ in stacktrace của wrapper rồi kết luận không tìm được nguyên nhân.

Có những lỗi **được ném đồng bộ khi gọi sendAsync**, chẳng hạn `IllegalArgumentException` nếu request không phải một request có thể được build hợp lệ theo API. Không thể giả định **mọi lỗi** nhất thiết xuất hiện chỉ qua future.

## 15. BodyHandler quyết định ý nghĩa của “đã complete”

Một request có thể nhận headers sớm, còn body đến chậm trong nhiều giây hoặc nhiều phút. Vì thế:

```text
Server                      Client HttpClient

send status+headers  ───────► BodyHandler được chọn
                            │
  nếu ofInputStream          ├─ trả HttpResponse<InputStream>
                            │   future có thể DONE
send body chunk #1 ─────────►│   ứng dụng đọc từ InputStream
send body chunk #2 ─────────►│
end stream ─────────────────►│   ứng dụng đọc tới EOF/close
                            │
  nếu ofString               └─ future DONE sau khi đã thu đủ body
```

API Java SE 17 `HttpResponse.BodyHandlers.ofInputStream()` nói rõ: **response headers đã đọc đủ khi `HttpResponse` được trả, nhưng body có thể chưa nhận hết**. Với `ofString()`, body đã được thu thập vào chuỗi khi response được trả.

Đây là khác biệt rất thực tế:
- `future.isDone()` với `ofInputStream` **không** đồng nghĩa đã tải hết file.
- Nếu chỉ lấy `response.body()` rồi không đọc/không đóng, connection resources có thể bị giữ.
- Muốn streaming JSON lớn, media hoặc download, phải thiết kế cách đọc/consume stream, timeout, backpressure và cleanup.
- Muốn xử lý body nhỏ dạng string, `ofString` tiện nhưng có thể tiêu thụ memory tỷ lệ với kích thước response.

## 16. Java 17+ runnable: future complete trước khi body gửi xong

Chương trình thứ hai dùng server cục bộ với hai latch:
1. Server gửi **status + headers**, gọi `flush()` để dữ liệu headers đi ra.
2. Server giữ body lại, chờ latch khác.
3. Client gọi `sendAsync(..., BodyHandlers.ofInputStream())`.
4. Client nhận `HttpResponse<InputStream>` và future **đã complete**, dù server chưa gửi body.
5. Client giải phóng latch, sau đó đọc `InputStream` và đóng bằng try-with-resources.

Lưu file đúng tên **`StreamingCompletionDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class StreamingCompletionDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch sentHeaders = new CountDownLatch(1);
        CountDownLatch releaseBody = new CountDownLatch(1);
        CountDownLatch sentBody = new CountDownLatch(1);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/stream", exchange -> {
            byte[] bytes = "stream-body".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().flush();
            sentHeaders.countDown();
            try {
                if (!releaseBody.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Body release timed out");
                }
                try (var output = exchange.getResponseBody()) {
                    output.write(bytes);
                }
                sentBody.countDown();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                exchange.close();
            }
        });
        server.start();

        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/stream");
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(8)).GET().build();

            CompletableFuture<HttpResponse<InputStream>> future =
                    client.sendAsync(
                            request, HttpResponse.BodyHandlers.ofInputStream());

            if (!sentHeaders.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("No headers");
            }
            HttpResponse<InputStream> response = future.get(3, TimeUnit.SECONDS);
            System.out.println("status=" + response.statusCode());
            System.out.println("future-complete-before-body=" + future.isDone());
            System.out.println("body-sent-before-release="
                    + (sentBody.getCount() == 0));

            releaseBody.countDown();
            try (InputStream stream = response.body()) {
                String text = new String(
                        stream.readAllBytes(), StandardCharsets.UTF_8);
                System.out.println("body=" + text);
            }
        } finally {
            releaseBody.countDown();
            server.stop(0);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac StreamingCompletionDemo.java
java StreamingCompletionDemo
```

Output đã kiểm chứng với Java 17 API:

```text
status=200
future-complete-before-body=true
body-sent-before-release=false
body=stream-body
```

### Giải thích output

- `status=200`: future đã có `HttpResponse<InputStream>` với headers/status.
- `future-complete-before-body=true`: Future tương ứng **đã complete** theo `BodyHandlers.ofInputStream`, dù body chưa được server gửi xong.
- `body-sent-before-release=false`: latch server `sentBody` vẫn chưa được đếm về zero; body còn đợi.
- `body=stream-body`: sau `releaseBody.countDown()`, server gửi body; client gọi `readAllBytes()` từ stream rồi đóng nó.

Điểm rút ra là **future biểu diễn trạng thái của HTTP exchange theo contract BodyHandler**, chứ không phải một cờ đảm bảo business consumer đã xử lý mọi byte. Với streaming, trách nhiệm của ứng dụng tiếp tục sau future completion.

### Vì sao phải flush headers trong ví dụ?

Một số HTTP server có thể đệm dữ liệu khi gọi `sendResponseHeaders`. Ví dụ cần **đẩy headers ra socket trước khi giữ body** để không tạo deadlock giả trong bài test. `exchange.getResponseBody().flush()` đảm bảo output buffer liên quan được flush trước khi main thread đợi future. Điều này là đặc thù của bài test local; không thể suy từ đó rằng mọi server đều gửi headers độc lập với body trong mọi tình huống.

## 17. Streaming production: close, backpressure và ownership

Khi dùng `BodyHandlers.ofInputStream()`, application phải:
1. Đọc từ `InputStream` cho tới EOF, hoặc gọi `close()` nếu không muốn đọc tiếp.
2. Không giữ stream mở vô hạn trong object không còn được sử dụng.
3. Không đọc blocking `InputStream.read()` trên event loop/UI thread nếu thời gian nhận có thể dài.
4. Đặt thời hạn chờ và giới hạn kích thước nếu response có thể lớn.
5. Đảm bảo exception và cancellation đều dẫn tới cleanup.
6. Kiểm tra status và Content-Type/Content-Length theo protocol trước khi parse; Content-Length có thể thiếu hoặc sai trong input không đáng tin, không dùng nó làm bảo đảm tuyệt đối.

Với `BodyHandlers.ofPublisher()`, `HttpResponse.body()` là `Flow.Publisher<List<ByteBuffer>>` dùng cho streaming với subscriber/backpressure. JDK Java 17 quy định publisher đó chỉ được subscribe **một lần**; ứng dụng phải subscribe/consume và xử lý cancellation theo đúng Flow contract. Nếu chỉ giữ publisher mà không subscribe, resources có thể không được giải phóng đúng.

**Không** chỉ dựa vào `future.isDone()` để đánh dấu “đã tải 100% file” trong UI. Với `ofFile`, future hoàn thành sau khi file được ghi đầy đủ; với `ofInputStream`, future có thể hoàn thành trước khi ứng dụng đọc hết nội dung. Chọn handler theo mô hình resource/UX thực sự cần.

## 18. Timeout: connect timeout, request timeout, stage timeout

Có nhiều lớp timeout khác nhau:

| Timeout/cơ chế | Đặt ở đâu | Phạm vi |
| --- | --- | --- |
| `HttpClient.Builder.connectTimeout(Duration)` | Trên client | Thời hạn chờ thiết lập kết nối mới, không tự thay thế mọi timeout |
| `HttpRequest.Builder.timeout(Duration)` | Trên request | Thời hạn chờ response theo contract HttpRequest, lỗi có thể là `HttpTimeoutException` |
| `future.orTimeout(time, unit)` | Trên `CompletableFuture` | Làm future hoàn thành ngoại lệ nếu vẫn chưa complete sau deadline của stage |
| `future.completeOnTimeout(value, time, unit)` | Trên `CompletableFuture` | Có thể hoàn thành future với fallback **cùng kiểu** sau timeout |
| Deadline nghiệp vụ tổng thể | Logic ứng dụng | Bao gồm retries, nhiều requests, parse/consume streaming body, DB work, callbacks |

Mảnh code đặt deadline cho stage biến đổi:

```java
CompletableFuture<String> bodyFuture = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(HttpResponse::body)
        .orTimeout(5, TimeUnit.SECONDS);
```

Đây là mảnh code, cần `java.util.concurrent.TimeUnit`. `orTimeout` có thể khiến **future được gọi** hoàn thành ngoại lệ, nhưng **không nên coi việc đặt deadline cho một stage là bảo đảm underlying HTTP transport đã chấm dứt tức khắc**. Đặt timeout cho request và xây cancellation/cleanup chủ động theo policy.

Không dùng `completeOnTimeout` với một `HttpResponse` giả tạo để đánh dấu “server trả HTTP 200” trong khi chưa có response. Nếu muốn fallback nghiệp vụ, biểu diễn tường minh bằng result type như `Success/Timeout/Error` thay vì làm giả dữ liệu network.

### Streaming đặc biệt chú ý deadline

Future của `ofInputStream` có thể đã hoàn thành khi có headers; lúc đó timeout chỉ áp lên **future đã complete** sẽ không giới hạn thời gian ứng dụng đọc body stream sau đó. Cần quản lý deadline đọc stream và đóng stream khi vượt hạn mức. Đó là lý do không thể nói “`orTimeout` bảo vệ toàn bộ thời gian download” cho mọi BodyHandler.

## 19. Cancellation: hủy future không đảm bảo server chưa xử lý

`HttpClient` mặc định trong Java 17 trả các `CompletableFuture` có khả năng cancel. Gọi:

```java
boolean requested = future.cancel(true);
```

là **yêu cầu hủy** khi future chưa complete. Theo Java 17 `HttpClient` API:
- Việc cancel là **nỗ lực** chấm dứt HTTP exchange và giải phóng tài nguyên sớm.
- **Không có cam kết** hủy sẽ có hiệu lực ngay lập tức.
- Request có thể đã được gửi tới server và thậm chí server có thể đã bắt đầu xử lý.
- Với HTTP/1.1, client có thể đóng abruptly connection.
- Với HTTP/2, client có thể reset stream và trong một số tình huống đóng connection.
- Derived futures từ cancelable futures có thể cũng có cancel semantics theo implementation.
- Cancellation có thể khiến `join`/`get` báo `CancellationException`.

**Không hủy future để “đảm bảo không chuyển khoản nữa”** sau khi gửi request. Tầng network không cung cấp exactly-once business semantics; phải dùng idempotency key, transaction ID, trạng thái server và quy trình xác nhận/cancel nghiệp vụ.

### Vì sao `cancel(true)` không thay thế timeout?

Cancellation có thể được gọi khi user nhấn “Cancel” hoặc deadline app hết hạn. Nhưng:
1. Future có thể đã complete trước khi cancel.
2. HTTP request có thể đã đi qua mạng.
3. Server có thể vẫn xử lý.
4. Tài nguyên mạng có thể được giải phóng bất đồng bộ.
5. Streaming response cần cleanup stream/subscriber theo lifecycle.

Vì thế cần kết hợp deadline, cancel attempt, đóng tài nguyên và **đối soát kết quả phía server** khi request có side effects.

## 20. Retry: khi nào an toàn, khi nào nguy hiểm?

Khi future complete exceptionally do timeout/connection reset, client **không nhất thiết biết server đã nhận và xử lý request chưa**. Nếu tự retry:
- `GET` thường idempotent về HTTP semantics, nhưng vẫn cần giới hạn attempts/backoff và network policy.
- `POST` tạo đơn, thanh toán, ghi dữ liệu **không tự idempotent**. Retry có thể tạo tác động lặp nếu thiếu idempotency key.
- Body publisher có thể không replayable; retry có thể thất bại hoặc gửi dữ liệu khác.
- Redirects, authentication challenges, proxy và HTTP/2 multiplexing cũng có thể làm việc xác định “lần gửi” phức tạp hơn.

Một retry policy production nên có:
- Danh sách method/status/exception **được phép** retry.
- Giới hạn attempts, backoff có jitter, deadline tổng thể.
- Idempotency key/request ID cho tác vụ ghi khi server hỗ trợ.
- Concurrency/rate limit, không nhân requests vô hạn.
- Observability ghi rõ attempt nào đã được thực hiện, không ghi secrets.
- Kiểm tra cancellation và resource cleanup giữa attempts.

`CompletableFuture.exceptionally(...)` tự nó **không** retry HTTP request. Nó chỉ cung cấp fallback cho một stage khi lỗi. Muốn retry cần thực sự tạo một sendAsync mới theo policy; không gọi lại client không giới hạn bên trong callback.

## 21. Request timeout không hoàn toàn thay thế cấu trúc pipeline

Một API request có thể gồm nhiều giai đoạn:

```text
sendAsync(request A)                    (network)
        │
        ▼
thenApply(validate status)              (CPU rẻ)
        │
        ▼
thenCompose(sendAsync(request B))       (network phụ thuộc)
        │
        ▼
thenApply(parse response B)             (CPU)
        │
        ▼
write database / publish event          (business I/O)
```

`HttpRequest.timeout(...)` của A áp cho request A, **không tự bao trùm** request B, DB write và toàn bộ pipeline. Muốn toàn tác vụ xong trong 5 giây cần deadline tổng thể được theo dõi/áp lên chuỗi công việc, đồng thời giới hạn các thành phần bên trong.

Đặt `orTimeout` ở **cuối dependent future** giúp caller không chờ kết quả vô hạn, nhưng bản thân stage timeout không bảo đảm mọi network/DB side effect đã thực sự ngừng. Cần chủ động propagate cancellation, đóng body stream, yêu cầu stop các task phụ thuộc khi được và theo dõi kết quả mơ hồ.

**Không block trong `thenCompose` bằng `send(...).get()`** để “đợi request B rồi return”. Trả về future của request B và để composition xử lý tiếp.

## 22. Asynchronous I/O vẫn có threads, memory và backpressure

`sendAsync` không phải ma thuật không tốn tài nguyên:
- HttpClient dùng cơ chế nội bộ để quản lý sockets, buffers, tasks và TLS.
- Một số callbacks có thể chạy trên thread completion hoặc executor.
- Các body handlers như `ofString` thu body vào memory, không phù hợp response lớn không giới hạn.
- Nếu bắn ra 50.000 futures cùng lúc, ứng dụng vẫn có thể cạn memory, socket/FD, connection slots hoặc khiến server quá tải.

Trong production:
1. Giới hạn số HTTP exchanges đang pending (ví dụ semaphore hoặc bulkhead).
2. Dùng `sendAsync` để không giữ một blocked caller thread cho mỗi request, nhưng **không** để concurrency vô hạn.
3. Cần đo queue wait, time-to-first-byte, body completion và total pipeline duration.
4. Chọn `BodyHandler` phù hợp (bytes/string/file/stream/publisher).
5. Quản lý thread pool/`ExecutorService` và cleanup đúng lifecycle.
6. Không coi Java 17 `HttpClient` là HTTP/3 client; các phiên bản mặc định API Java 17 chủ yếu là HTTP/1.1/HTTP/2, độc lập với bản chất `sendAsync`.
7. Hạn chế log payload cá nhân, Authorization, tokens và signed URLs.

**Một future không phải một TCP connection.** Một `HttpClient` có thể tái sử dụng connection; HTTP/2 có thể multiplex nhiều HTTP requests trên cùng transport. Số lượng futures phản ánh số logical operations chờ kết quả, **không** là số network sockets.

## 23. Cách dùng trong server và giao diện người dùng

### Backend theo phong cách async

Trong một request handler bất đồng bộ, có thể trả trực tiếp `CompletionStage` hoặc `CompletableFuture` cho framework hỗ trợ:

```java
CompletionStage<String> fetch(HttpClient client, HttpRequest request) {
    return client
            .sendAsync(request, HttpResponse.BodyHandlers.ofString())
            .thenApply(response -> {
                if (response.statusCode() != 200) {
                    throw new IllegalStateException(
                            "Remote status " + response.statusCode());
                }
                return response.body();
            });
}
```

Đây là **phương thức minh họa**, cần imports `java.net.http.*` và `java.util.concurrent.CompletionStage`. Nó không chứa class, main hay import statements nên không chạy độc lập; một framework cụ thể có thể xử lý returned stage theo cơ chế riêng.

Điểm tốt: phương thức **trả stage**, không chặn caller bằng `join()`. Framework có thể đăng ký callback để gửi response khi upstream hoàn tất. Điểm cần quản lý: cancellation khi incoming client disconnect, downstream timeout, propagation tracing context và mapping failure thành HTTP status phù hợp.

### Ứng dụng desktop

Với Swing/JavaFX:
- Khởi động `sendAsync` trên UI action.
- Trong callback, parse/validate ở background context thích hợp.
- Chuyển cập nhật UI về **Swing EDT** hoặc **JavaFX Application Thread**; không sửa UI từ HTTP worker thread tùy tiện.
- Khi cửa sổ bị đóng, có thể cancel best-effort nhưng vẫn phải quản lý stream/side effects.

### Chương trình CLI

Nếu chỉ có một request đơn và cần kết quả trước khi process thoát, dùng `send` có thể đơn giản hơn; hoặc `sendAsync(...).thenApply(...).get(...)` ở ranh giới kết thúc. Điều đáng tránh là **ngụy tạo async** ở mọi tầng nhưng thực chất block trên từng bước.

## 24. Kiểm thử bất đồng bộ đúng cách

Async code dễ có test flakiness nếu phụ thuộc `Thread.sleep`. Với một HTTP server cục bộ, nên kiểm thử bằng `CountDownLatch` hoặc barrier:
- Đảm bảo server **đã thấy request** trước khi kiểm tra trạng thái pending.
- Chủ động giữ response để future chưa complete.
- Giải phóng server rồi chờ final stage với timeout.
- Không dựa vào “mạng chắc sẽ chậm vài millisecond”.
- Sử dụng địa chỉ loopback và OS-assigned port `0` để tránh xung đột cổng.
- Đóng/stop server trong `finally`, kể cả test thất bại.

Ma trận test hữu ích:

| Trường hợp | Kết quả cần xác minh |
| --- | --- |
| Server giữ response | Future pending trong khi caller có thể tiếp tục |
| Server gửi 200 + body nhỏ | `ofString` future trả `HttpResponse<String>`, body chính xác |
| Server gửi 404 hoặc 500 | HTTP future **thành công**; status do app xử lý |
| DNS/connection/TLS failure | Future có thể complete exceptionally với cause phù hợp |
| BodyHandler.ofInputStream, headers trước body | Future complete khi headers sẵn sàng dù body chưa xong |
| Stream được đọc và đóng | Không để tài nguyên HTTP exchange bị giữ mãi |
| Callback transform ném lỗi | Dependent future exceptional dù original HTTP response thành công |
| `thenCompose` tạo request B sau A | Không gửi B khi chưa đủ điều kiện, không tạo nested future |
| `allOf` hai request | Chỉ combine sau cả hai thành công; xử lý lỗi tổng hợp |
| Request timeout | Future báo lỗi; không block vô hạn |
| Cancellation khi server đang xử lý | Client cancel best-effort; không giả định server chưa xử lý |
| Many concurrent requests | Có concurrency limit, không out-of-memory hoặc starvation |
| Redirect/auth | Status và response cuối được hiểu đúng theo client config |

**Không** dùng test server trả 200 ngay để chắc chắn future “phải pending sau sendAsync”: trên loopback, response có thể hoàn thành trước khi luồng test gọi `isDone()`. Latches là cách xác định điều kiện trạng thái, như chương trình ở mục 7 và 16.

## 25. Các lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `sendAsync(...).join()` ngay trong event loop | Caller vẫn bị block | Trả future hoặc đăng ký callback |
| Cho rằng mọi future chưa done ngay khi trả về | Test flakiness | Dùng latch/barrier để kiểm soát timing |
| Cho rằng future complete nghĩa tải hết body | Sai với `ofInputStream`/`ofPublisher` | Hiểu contract handler và consume/close stream |
| Cho rằng HTTP 404 là CompletionException | Không tự đúng | Check `HttpResponse.statusCode()` |
| Bỏ qua future returned | Thất bại bất đồng bộ không được quan sát | Attach success/failure handler hoặc trả stage cho caller |
| Dùng `thenApply` cho HTTP request thứ hai | Nested future khó quản lý | Dùng `thenCompose` |
| Dùng `whenComplete` để “recover” bằng return fallback | Không thay thế value theo thiết kế | Dùng `handle`/`exceptionally` rõ ràng |
| Để callback CPU/blocking nặng chạy trong completion path | Chậm I/O hoặc starvation | `thenApplyAsync` với executor thích hợp |
| Dùng `get()` không có deadline tại UI thread | UI treo | Thực hiện async callback, đặt timeouts |
| Retry POST không idempotency | Giao dịch có thể bị thực hiện hai lần | Idempotency key + retry policy |
| `cancel(true)` rồi cho rằng server chưa nhận | Kết quả giao dịch mơ hồ | Best-effort cancel + đối soát server |
| Không giới hạn futures/pending requests | Cạn memory/sockets | Concurrency limit/backpressure |
| Không đọc/đóng body stream | Rò resources, connection không tái sử dụng | Try-with-resources/consume EOF |
| Catch exception rồi trả response giả “200 OK” | Che giấu lỗi thật | Typed error result / status mapping |
| Chỉ dùng `connectTimeout` cho toàn pipeline | Không cover body/callback/DB work | Request/stage/business deadlines |
| Nhầm future với 1 TCP socket | Sai metrics, khó tối ưu | Quan sát logical exchange và transport riêng |
| Không kiểm tra response code trước parse JSON | Parse error hoặc xử lý 404 thành thành công | Validate status/content-type trước parse |
| Ghi log toàn body/URL token | Rò thông tin | Mask/limit logs và tracing metadata |

## 26. Câu hỏi tự kiểm tra

**Câu 1.** `sendAsync(request, BodyHandlers.ofString())` trả kiểu gì?  
**Đáp án:** `CompletableFuture<HttpResponse<String>>`. Future biểu diễn response sẽ có trong tương lai, không phải `String` trực tiếp.

**Câu 2.** Future được trả về có bắt buộc chưa hoàn thành không?  
**Đáp án:** Không. Request có thể hoàn thành nhanh; `isDone` tại thời điểm caller kiểm tra có thể true hoặc false. Khi cần test pending, dùng server gate/latch.

**Câu 3.** `sendAsync` khác `send` chủ yếu ở đâu?  
**Đáp án:** `send` block caller chờ response và trả `HttpResponse<T>`; `sendAsync` trả sớm `CompletableFuture<HttpResponse<T>>` cho phép đăng ký công việc tiếp theo.

**Câu 4.** Server trả HTTP 404, `future.isCompletedExceptionally()` có nhất thiết true không?  
**Đáp án:** Không. Status 404 vẫn là `HttpResponse` bình thường nếu exchange được thực hiện thành công ở tầng HTTP; business phải tự check status.

**Câu 5.** `thenApply(HttpResponse::body)` thay đổi type như thế nào?  
**Đáp án:** Từ `CompletableFuture<HttpResponse<String>>` thành `CompletableFuture<String>`, với handler string.

**Câu 6.** Có nên gọi `join()` ngay sau `sendAsync` trong JavaFX UI handler?  
**Đáp án:** Không. Nó có thể block UI thread. Dùng callback và dispatch kết quả tới JavaFX Application Thread.

**Câu 7.** Khi nào nên dùng `thenCompose`?  
**Đáp án:** Khi function trong chain trả về một future khác, ví dụ request B phụ thuộc response A; `thenCompose` flatten future lồng nhau.

**Câu 8.** `allOf` có trả list các `HttpResponse` không?  
**Đáp án:** Không. Nó trả `CompletableFuture<Void>`; giữ futures thành viên để lấy kết quả sau khi tất cả hoàn thành.

**Câu 9.** Vì sao `ofInputStream` có thể cho future complete khi body chưa đến?  
**Đáp án:** Contract cho phép trả `HttpResponse<InputStream>` sau khi headers đọc đủ; việc đọc body tiếp tục qua InputStream mà caller phải tiêu thụ/đóng.

**Câu 10.** Nếu `future.cancel(true)` thành công, server có chắc chưa xử lý request không?  
**Đáp án:** Không. Cancel chỉ best-effort; request có thể đã đến server hoặc có side effects.

**Câu 11.** `whenComplete` có phải cách tốt để thay lỗi bằng giá trị fallback?  
**Đáp án:** Không phải mục đích chính. `whenComplete` dùng quan sát/cleanup; `handle` hoặc `exceptionally` diễn đạt việc recovery rõ hơn.

**Câu 12.** Mất bao nhiêu millisecond từ `sendAsync` tới callback là điều được API bảo đảm không?  
**Đáp án:** Không. Thời gian phụ thuộc network, server, executor, body handler và tải; không dùng stopwatch nhỏ để kết luận semantics.

**Câu 13.** Nếu dùng `ofInputStream` và không đọc/không đóng stream, vấn đề gì?  
**Đáp án:** HTTP exchange/resources có thể bị giữ, gây rò connection/threads/buffers và thiếu backpressure đúng cách.

**Câu 14.** Nếu response 200 nhưng business parse JSON ném exception, future nào lỗi?  
**Đáp án:** Stage parse dependent có thể exceptional, dù HTTP future gốc hoàn thành bình thường. Cần biết lỗi phát sinh ở stage nào.

**Câu 15.** Hai request độc lập nên chạy nối tiếp hay có thể khởi động cả hai futures rồi `allOf`?  
**Đáp án:** Có thể khởi động cả hai và dùng `allOf` nếu phù hợp concurrency/rate limits. Nếu B phụ thuộc A thì `thenCompose` thích hợp hơn.

## 27. Tóm tắt quy trình áp dụng

Đối với một HTTP exchange bất đồng bộ trong Java 17:

1. Tạo `HttpClient` và `HttpRequest` đúng timeout, SSL/auth/proxy và redirect policy.
2. Chọn `BodyHandler<T>` theo **body lifetime** và kiểu kết quả mong muốn.
3. Gọi `sendAsync(request, handler)`, giữ hoặc trả `CompletableFuture<HttpResponse<T>>`.
4. Đăng ký `thenApply`/`thenCompose`/`whenComplete`/`exceptionally` để xử lý success/failure và dependencies **không blocking** caller.
5. Kiểm tra HTTP status và headers rõ ràng; **4xx/5xx không tự thành future exception**.
6. Khi streaming, đọc/đóng body stream hoặc subscribe/consume publisher theo contract; không đánh đồng future done với body consumed.
7. Đặt request/stage/overall deadlines; cancellation best-effort và cleanup tài nguyên.
8. Giới hạn concurrency, memory, retries; bảo vệ idempotency cho request side-effect.
9. Quan sát lỗi gốc và callback errors riêng; không swallow failures bằng fallback giả.
10. Test trạng thái in-flight bằng latch, test body streaming và các edge cases trên loopback.

**Kết luận cốt lõi:** `sendAsync` không trả “kết quả HTTP ngay bây giờ”. Nó trả một **CompletableFuture** đại diện cho **kết quả của HTTP exchange đang diễn ra**, cho phép ứng dụng mô tả những bước phải làm **sau khi** response có thể được sử dụng theo `BodyHandler`. Sự hoàn thành của future không tự thay thế status validation, business processing, cancellation policy hay quản lý lifetime của streaming body.

## 28. Tài liệu tham khảo chính thức

- Java SE 17 `HttpClient` — `send`/`sendAsync`, response body handler, cancellation semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17 `HttpRequest.Builder` — `timeout`, URI, method, headers, body publisher: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- Java SE 17 `HttpResponse` — status, headers, body, URI và previousResponse: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Java SE 17 `HttpResponse.BodyHandlers` — `ofString`, `ofByteArray`, `ofFile`, `ofInputStream`, `ofPublisher`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- Java SE 17 `HttpResponse.BodySubscribers` — thời điểm hoàn tất body, streaming và nghĩa vụ close: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html
- Java SE 17 `CompletableFuture` — chaining, `thenApply`/`thenCompose`/`allOf`, cancellation, deadlines: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Java SE 17 `HttpTimeoutException` và `HttpConnectTimeoutException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html
- Java SE 17 `HttpServer` — JDK local test HTTP server: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- RFC 9110 — HTTP Semantics, status codes và request properties: https://www.rfc-editor.org/rfc/rfc9110

# IOException và lỗi hoàn tất bất thường trong HTTP bất đồng bộ (Java 11+)

## 1. Vấn đề cốt lõi: lỗi HTTP khác lỗi hoàn tất future

Từ **Java 11**, module `java.net.http` cung cấp HTTP Client chuẩn, hỗ trợ yêu cầu đồng bộ bằng `HttpClient.send(...)` và bất đồng bộ bằng `HttpClient.sendAsync(...)`. Khi gửi bất đồng bộ, kết quả không được trả thẳng tại điểm gọi mà được biểu diễn bằng một `CompletableFuture<HttpResponse<T>>`:

```java
CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
```

Đây là **mảnh mã minh họa** trong một phương thức đã khai báo `client`/`request`, với import các kiểu `java.net.http`, `StandardCharsets` và `CompletableFuture`.

Có **hai tình huống khác nhau**:

1. **Server thực sự trả HTTP response:** dù status là 200, 404, 429 hoặc 503, nếu response hợp lệ và body handler xử lý thành công thì future thường **hoàn thành bình thường**. Ứng dụng đọc `response.statusCode()` để xác định thành công/thất bại nghiệp vụ.
2. **Giao dịch HTTP không hoàn thành đúng:** mất kết nối, body bị cắt trước độ dài công bố, DNS/TLS lỗi, request timeout, hoặc lỗi xảy ra trong callback xử lý. Future có thể **hoàn thành bất thường (*exceptionally*)**. Khi đó caller thường thấy `CompletionException` hoặc `ExecutionException` bọc nguyên nhân thực, thay vì nhận một `HttpResponse` thành công.

Điều đầu tiên phải nhớ:

**HTTP 500 là một mã trạng thái do server trả về. `IOException` là một loại lỗi khi thực hiện I/O. Hai khái niệm không tương đương.**

Mục tiêu bài học:

- Hiểu `IOException`, `HttpTimeoutException` và các lỗi bất thường của HTTP bất đồng bộ.
- Phân biệt response 4xx/5xx với lỗi của future.
- Dùng `join()`, `get()` và truy vết `cause` đúng cách.
- Chọn `thenApply`, `exceptionally`, `handle`, `whenComplete` theo tình huống.
- Quản lý timeout, cancellation, retry và vòng đời body streaming.
- Chạy một chương trình Java 11 tự tạo server cục bộ để kiểm tra phản hồi 200/503, body cắt cụt, timeout và cách exception được bọc.

Các API trình bày vẫn áp dụng trong Java hiện đại; chương trình đầy đủ được biên dịch với `--release 11`.

## 2. Hợp đồng của sendAsync và trạng thái CompletableFuture

`HttpClient.sendAsync(request, handler)` trả:

```java
CompletableFuture<HttpResponse<T>>
```

`T` được quyết định bởi `HttpResponse.BodyHandler<T>`:

| BodyHandler | Kiểu body của response | Khi nào hoàn tất? |
| --- | --- | --- |
| `BodyHandlers.ofString(UTF_8)` | `String` | Khi body đã được xử lý thành chuỗi theo hợp đồng. |
| `BodyHandlers.ofByteArray()` | `byte[]` | Khi body đã được nhận vào mảng byte. |
| `BodyHandlers.ofFile(path)` | `Path` | Khi xử lý body ra file hoàn tất theo handler. |
| `BodyHandlers.ofInputStream()` | `InputStream` | Có thể trả response khi stream sẵn sàng, **trước khi đọc hết body**. |
| `BodyHandlers.ofLines()` | `Stream<String>` | Có thể trả response khi stream dòng sẵn sàng, **trước khi duyệt hết dòng**. |

`sendAsync` không buộc caller chờ đến khi mạng hoàn tất; `CompletableFuture` có thể được ghép các tác vụ tiếp theo. Tuy nhiên, thời điểm một future hoàn tất **phụ thuộc body handler và stage**: một future nhận `HttpResponse<InputStream>` có thể bình thường nhưng lúc đọc stream sau đó vẫn gặp lỗi mạng.

Sơ đồ:

```text
HttpClient.sendAsync(...)
            |
            v
CompletableFuture<HttpResponse<T>>
            |
      +-----+------------------+
      |                        |
      v                        v
Hoàn thành bình thường      Hoàn thành bất thường
      |                        |
      v                        v
HttpResponse<T>            Throwable / cause
status 200/404/503          IOException, timeout,
headers, body ...           TLS, lỗi callback, cancel
      |                        |
      v                        v
Kiểm tra status riêng      handle / exceptionally /
                            khi join/get xem cause
```

Các phương thức theo dõi:

- `future.isDone()`: `true` nếu hoàn tất **bất kỳ kiểu nào** — success, exception hoặc cancellation.
- `future.isCompletedExceptionally()`: `true` khi hoàn tất bất thường, kể cả hủy.
- `future.isCancelled()`: `true` khi bị hủy thành công.
- `future.join()`: chờ/lấy kết quả, hoặc ném unchecked exception khi thất bại.
- `future.get()`: chờ/lấy kết quả theo `Future`, có thể ném checked `InterruptedException`/`ExecutionException`.

**`isDone()==true` không đồng nghĩa “request thành công”**. Tương tự, `statusCode()==503` không buộc `isCompletedExceptionally()` thành true.

## 3. Những nguyên nhân gây IOException trong HTTP bất đồng bộ

Trong HTTP đồng bộ, `client.send(request, handler)` có thể ném `IOException` trực tiếp. Với `sendAsync`, lỗi I/O khi gửi/nhận được báo qua **exceptional completion** của future.

Các lỗi thường gặp:

| Sự cố | Exception thường gặp | Ghi nhớ |
| --- | --- | --- |
| Server từ chối kết nối | `java.net.ConnectException` hoặc lỗi I/O liên quan. | Dịch vụ có thể chưa mở cổng. |
| Không phân giải được tên miền | `UnknownHostException` hoặc lỗi I/O khi kết nối. | Kiểu exception cụ thể có thể phụ thuộc môi trường. |
| Kết nối mới hết thời gian thiết lập | `HttpConnectTimeoutException`. | Là subclass của `HttpTimeoutException`. |
| Request hết thời gian chờ phản hồi | `HttpTimeoutException`. | Thường nằm trong cause của lỗi completion. |
| TLS hoặc xác minh chứng chỉ thất bại | `SSLException`, có thể là `SSLHandshakeException`. | Không tắt kiểm tra TLS chỉ để bỏ lỗi. |
| Body bị cắt cụt hoặc lỗi khi đọc | `IOException` hoặc subclass. | Có thể lỗi muộn, tùy cách body handler xử lý. |
| Parser/logic trong `thenApply` ném lỗi | Exception do callback tạo ra. | Không mặc định là lỗi network. |
| Future bị hủy | `CancellationException` hoặc exception có liên quan. | Không suy ra server chưa xử lý request. |

**Đừng viết test kiểm tra chính xác thông điệp lỗi** như `"Connection reset"`, `"fixed content-length"` hoặc `"timeout"`. Các chuỗi và subtype cụ thể có thể khác ở JDK, nền tảng và HTTP protocol.

### 3.1. Không phải lỗi nào cũng đi qua future

Một số sai sót về tham số hoặc việc tạo request có thể bị từ chối **ngay khi xây dựng request hoặc gọi `sendAsync`**, chẳng hạn `IllegalArgumentException` theo hợp đồng API. Điều này khác với một lỗi mạng đến sau khi request đã được chấp nhận để gửi.

Các lỗi bảo mật do môi trường áp dụng chính sách truy cập cũng có thể làm future kết thúc bất thường. Không dùng một catch tổng quát rồi mặc định mọi nguyên nhân là `IOException`.

### 3.2. Lỗi trước và sau khi nhận response

Với `BodyHandlers.ofString()` hoặc `ofByteArray()`, client phải nhận và xử lý nội dung để tạo body thành công. Một phản hồi bị cắt cụt có thể khiến future của `sendAsync` bất thường ngay trong giai đoạn nhận body.

Với `BodyHandlers.ofInputStream()` và `ofLines()`, future có thể đã trả response hợp lệ trong khi phần body tiếp tục được đọc bên ngoài. Lỗi muộn có thể phát sinh ở:

- `InputStream.read(...)` (checked `IOException`).
- Terminal operation của `Stream<String>` (có thể là `UncheckedIOException`).
- Parser nghiệp vụ xử lý từng dòng/byte.

Vì vậy cần xem xét **vòng đời response body**, không chỉ future gốc.

## 4. Vì sao HTTP 503 không tự làm future bất thường?

Server có thể gửi phản hồi hoàn chỉnh:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: text/plain; charset=utf-8

please retry later
```

Nếu client đọc được response này, `CompletableFuture<HttpResponse<String>>` có thể hoàn tất bình thường:

```java
HttpResponse<String> response = future.join();
System.out.println(response.statusCode());       // 503
System.out.println(future.isCompletedExceptionally()); // false
```

Đây là **mã minh họa** nếu future thực sự nhận response 503. Khi đó `future.exceptionally(...)` **không tự chạy**. Phải chủ động xử lý status:

```java
CompletableFuture<String> result =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
              .thenApply(response -> {
                  if (response.statusCode() >= 200
                          && response.statusCode() < 300) {
                      return response.body();
                  }
                  return "HTTP status: " + response.statusCode();
              });
```

Mã cần đặt trong phương thức có `client`/`request`. Tùy hợp đồng API, status 202, 204 hoặc 206 có ý nghĩa khác nhau; đoạn này chỉ minh họa phân nhóm.

Đối chiếu:

| Tình huống | Có response thành công trong future không? | Hướng xử lý |
| --- | --- | --- |
| HTTP 200, body hợp lệ | Có. | Kiểm tra nội dung nghiệp vụ. |
| HTTP 404, body hợp lệ | Có. | Đọc `statusCode()` và xử lý không tìm thấy. |
| HTTP 503, body hợp lệ | Có. | Phân loại tạm thời, cân nhắc retry có điều kiện. |
| Body bị cắt khi dùng `ofString` | Có thể không. | Kiểm tra exceptional completion và cause. |
| Timeout kết nối/request | Thường không. | Phân loại `HttpTimeoutException` hoặc subtype. |
| Lỗi parser trong callback | Future gốc có thể bình thường nhưng stage tiếp theo bất thường. | Báo lỗi dữ liệu/logic riêng, không gán thành lỗi mạng. |

**Không tự tạo status 500 thay cho lỗi network** khi server chưa hề trả một HTTP 500.

## 5. CompletionException và ExecutionException: đọc nguyên nhân thật

`CompletableFuture` có hai cách chờ quan trọng:

### 5.1. join()

`join()` không khai báo checked exception. Nếu stage thất bại, nó thường ném **`CompletionException`** bọc nguyên nhân. Với cancellation, có thể gặp `CancellationException`.

```java
try {
    HttpResponse<String> response = future.join();
    System.out.println(response.statusCode());
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    System.err.println("Async failed: " + cause);
}
```

Đây là đoạn minh họa cần import `java.util.concurrent.CompletionException`. Không log nguyên token, cookie, body hoặc stack trace ra giao diện công khai.

### 5.2. get()

`get()` theo giao diện `Future` có thể ném:

- `ExecutionException` nếu future hoàn tất bất thường.
- `InterruptedException` nếu thread chờ bị ngắt.
- `CancellationException` nếu future bị hủy.

```java
try {
    HttpResponse<String> response = future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw ex;
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    System.err.println("Async cause: " + cause);
}
```

Đây là đoạn minh họa trong phương thức khai báo `throws InterruptedException` và import `ExecutionException`.

**Điểm khác biệt:** `join()` thường báo lỗi bằng exception runtime, còn `get()` dùng checked `ExecutionException`/`InterruptedException`. Dù caller chọn cách nào, **nguyên nhân I/O có thể giống nhau**.

### 5.3. Bóc wrapper đúng cách

Hàm sau chỉ bỏ hai loại wrapper phổ biến:

```java
static Throwable unwrap(Throwable throwable) {
    while ((throwable instanceof CompletionException
             || throwable instanceof ExecutionException)
            && throwable.getCause() != null) {
        throwable = throwable.getCause();
    }
    return throwable;
}
```

Đây là **phương thức trong một lớp**, cần import `CompletionException` và `ExecutionException`.

Phân loại theo thứ tự từ chuyên biệt đến tổng quát:

```java
Throwable cause = unwrap(error);
if (cause instanceof HttpTimeoutException) {
    // Timeout khi xử lý HTTP.
} else if (cause instanceof IOException) {
    // Lỗi I/O khác.
} else if (cause instanceof CancellationException) {
    // Tác vụ đã bị hủy.
} else {
    // Lỗi khác: callback, parser hoặc logic nghiệp vụ...
}
```

Ở mảnh mã này, biến `error` được cung cấp từ callback hoặc bắt exception; cần import các kiểu tương ứng. `HttpTimeoutException` là subclass của `IOException`, do đó **phải kiểm tra timeout trước IOException** nếu muốn có nhánh riêng.

Không tự bỏ qua mọi tầng `cause` không phân biệt vì có thể mất ngữ cảnh lỗi nghiệp vụ quan trọng.

## 6. thenApply, exceptionally, handle và whenComplete

### 6.1. thenApply: chỉ xử lý normal completion

`thenApply(response -> ...)` chạy khi stage trước hoàn thành **bình thường**. HTTP 503 cũng có thể đi vào callback này:

```java
CompletableFuture<String> summary = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString())
    .thenApply(response ->
            response.statusCode() == 503
                    ? "service-unavailable"
                    : response.body());
```

Nếu logic `thenApply` tự ném `IllegalArgumentException` do parser/validation, **stage tiếp theo** hoàn thành bất thường. Đó không nhất thiết là lỗi network.

### 6.2. exceptionally: phục hồi lỗi bằng giá trị cùng kiểu

`exceptionally(fn)` chạy khi stage trước bất thường, rồi cung cấp kết quả thay thế:

```java
CompletableFuture<String> summary = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString())
    .thenApply(response -> "status=" + response.statusCode())
    .exceptionally(error ->
            "transport-or-processing-error:" +
                    unwrap(error).getClass().getSimpleName());
```

`exceptionally` **không chạy vì HTTP 503** nếu `thenApply` đã tạo `"status=503"` bình thường. Đồng thời, dùng fallback kiểu `""` hoặc `null` có thể **che dấu thất bại**; chỉ phục hồi nếu nghiệp vụ cho phép.

### 6.3. handle: xử lý cả bình thường lẫn bất thường

`handle((response, error) -> ...)` chạy ở cả hai nhánh và **tạo giá trị mới**:

```java
CompletableFuture<String> outcome = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString())
    .handle((response, error) -> {
        if (error != null) {
            return "failed:" +
                    unwrap(error).getClass().getSimpleName();
        }
        return "HTTP " + response.statusCode();
    });
```

Nếu callback `handle` tự trả bình thường, future mới có thể bình thường kể cả future nguồn đã lỗi. Nên phân biệt **future gốc** với **future sau xử lý**.

### 6.4. whenComplete: quan sát, không chủ yếu phục hồi

`whenComplete((response, error) -> ...)` thường dùng để ghi metrics, tracing hoặc cleanup:

```java
CompletableFuture<HttpResponse<String>> observed = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString())
    .whenComplete((response, error) -> {
        if (error != null) {
            System.err.println("failed:" +
                    unwrap(error).getClass().getSimpleName());
        } else {
            System.out.println("status:" + response.statusCode());
        }
    });
```

Nếu callback chạy bình thường, `whenComplete` **giữ nguyên kết quả/lỗi gốc** trong stage mới. Nó khác `handle`, vốn chủ động tạo kết quả. Nếu callback quan sát lại tự ném lỗi, stage kết quả có thể bị ảnh hưởng.

| Phương thức | Khi nào callback chạy? | Tác dụng chính |
| --- | --- | --- |
| `thenApply` | Khi source bình thường. | Chuyển giá trị thành kết quả mới. |
| `exceptionally` | Khi source bất thường. | Tạo fallback cùng kiểu. |
| `handle` | Cả success và failure. | Phân loại hai nhánh và chuyển kết quả. |
| `whenComplete` | Cả success và failure. | Quan sát kết quả/lỗi, thường không đổi chúng. |

Những đoạn trên là **mảnh mã minh họa** trong phương thức có `client`, `request` và `unwrap`, không phải các tệp Java độc lập.

## 7. Chương trình Java 11+ hoàn chỉnh, không cần Internet

Chương trình tạo server **loopback `127.0.0.1`** với bốn endpoint:

- `/ok`: HTTP 200, body `OK`.
- `/error`: HTTP 503, body hoàn chỉnh — future bình thường.
- `/broken`: khai báo `Content-Length` 50 byte, nhưng chỉ gửi `"short"` 5 byte rồi đóng — mô phỏng lỗi I/O khi nhận body.
- `/slow`: chờ 500 ms mới trả lời, trong khi request chỉ có timeout 100 ms — mô phỏng request timeout.

Server fixture là `com.sun.net.httpserver.HttpServer` thuộc module `jdk.httpserver` của JDK. **HTTP client thật sự trong bài vẫn là `java.net.http.HttpClient`**. Ví dụ chạy trên classpath, không cần thư viện ngoài.

Lưu vào **`AsyncHttpErrorsDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class AsyncHttpErrorsDemo {
    static void reply(HttpExchange exchange, int status, String text)
            throws IOException {
        try {
            byte[] data = text.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(status, data.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(data);
            }
        } finally {
            exchange.close();
        }
    }

    static Throwable unwrap(Throwable throwable) {
        while ((throwable instanceof CompletionException
                 || throwable instanceof ExecutionException)
                && throwable.getCause() != null) {
            throwable = throwable.getCause();
        }
        return throwable;
    }

    static HttpRequest get(URI target, Duration timeout) {
        return HttpRequest.newBuilder(target)
                .timeout(timeout)
                .GET()
                .build();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/ok",
                exchange -> reply(exchange, 200, "OK"));
        server.createContext("/error",
                exchange -> reply(exchange, 503, "please retry later"));
        server.createContext("/broken", exchange -> {
            try {
                exchange.getResponseHeaders()
                        .set("Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, 50);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write("short".getBytes(StandardCharsets.UTF_8));
                }
            } catch (IOException ignored) {
                // Fixture: cố ý cắt body trước độ dài đã công bố.
            } finally {
                exchange.close();
            }
        });
        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            try {
                reply(exchange, 200, "too late");
            } catch (IOException ignored) {
                exchange.close();
            }
        });
        server.start();

        try {
            URI base = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            HttpResponse<String> good = client.sendAsync(
                    get(base.resolve("/ok"), Duration.ofSeconds(3)),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8)).join();
            System.out.println("ok=" + good.statusCode() + ":" + good.body());

            CompletableFuture<HttpResponse<String>> statusFuture =
                    client.sendAsync(
                            get(base.resolve("/error"), Duration.ofSeconds(3)),
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
            HttpResponse<String> statusResponse = statusFuture.join();
            System.out.println("status=" + statusResponse.statusCode());
            System.out.println("statusExceptional=" +
                    statusFuture.isCompletedExceptionally());

            CompletableFuture<HttpResponse<String>> failed =
                    client.sendAsync(
                            get(base.resolve("/broken"), Duration.ofSeconds(3)),
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
            String outcome = failed.handle((response, error) -> {
                if (error == null) {
                    return "unexpected-success";
                }
                return unwrap(error) instanceof IOException
                        ? "io-failure" : "other-failure";
            }).join();
            System.out.println("broken=" + outcome);
            System.out.println("brokenExceptional=" +
                    failed.isCompletedExceptionally());

            CompletableFuture<HttpResponse<String>> timeout =
                    client.sendAsync(
                            get(base.resolve("/slow"), Duration.ofMillis(100)),
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
            String timeoutOutcome = timeout.handle((response, error) -> {
                if (error == null) {
                    return "unexpected-success";
                }
                return unwrap(error) instanceof HttpTimeoutException
                        ? "request-timeout" : "other-failure";
            }).join();
            System.out.println("timeout=" + timeoutOutcome);

            try {
                failed.join();
                System.out.println("joinFailure=missed");
            } catch (CompletionException ex) {
                System.out.println("joinCauseIsIOException=" +
                        (unwrap(ex) instanceof IOException));
            }
            try {
                failed.get();
                System.out.println("getFailure=missed");
            } catch (ExecutionException ex) {
                System.out.println("getCauseIsIOException=" +
                        (unwrap(ex) instanceof IOException));
            }

            CompletableFuture<String> recovery = client.sendAsync(
                    get(base.resolve("/error"), Duration.ofSeconds(3)),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8))
                    .thenApply(response -> response.statusCode() >= 500
                            ? "service-unavailable" : response.body())
                    .exceptionally(error -> "network-failure");
            System.out.println("handledStatus=" + recovery.join());
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch và chạy với JDK hỗ trợ mức Java 11:

```bash
javac -encoding UTF-8 --release 11 AsyncHttpErrorsDemo.java
java AsyncHttpErrorsDemo
```

**Đầu ra thực tế đã kiểm chứng trên JDK 24 khi biên dịch bằng `--release 11`:**

```text
ok=200:OK
status=503
statusExceptional=false
broken=io-failure
brokenExceptional=true
timeout=request-timeout
joinCauseIsIOException=true
getCauseIsIOException=true
handledStatus=service-unavailable
```

### 7.1. Giải thích từng kết quả

- `ok=200:OK`: `sendAsync` hoàn thành bình thường với response status 200 và body `OK`.
- `status=503`/`statusExceptional=false`: 503 là **HTTP response thật**, không khiến future bất thường.
- `broken=io-failure`/`brokenExceptional=true`: server khai báo gửi 50 byte nhưng chỉ gửi 5. Với `ofString`, kết thúc thiếu dữ liệu dẫn đến lỗi I/O được phản ánh trong future.
- `timeout=request-timeout`: timeout request 100 ms trong khi server chờ 500 ms; cause là `HttpTimeoutException`.
- `joinCauseIsIOException=true`: `join` bọc lỗi I/O trong `CompletionException` và có thể unwrap.
- `getCauseIsIOException=true`: `get` bọc lỗi bất thường trong `ExecutionException`.
- `handledStatus=service-unavailable`: `thenApply` kiểm tra 503 rồi tạo kết quả nghiệp vụ; `exceptionally` **không chạy** vì stage trước không bị lỗi.

Lỗi network cụ thể và thông báo có thể thay đổi theo JDK, hệ điều hành hoặc HTTP version. Đây là output đã chạy thành công trong môi trường kiểm tra; khi đưa test vào CI, nên assert **loại hành vi/nhóm lỗi**, tránh ràng buộc message của JDK hoặc timeout có biên độ quá sát.

## 8. Timeout: cần phân biệt ba tầng

### 8.1. Connect timeout

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();
```

Cấu hình này áp dụng cho việc **thiết lập kết nối mới**, không phải giới hạn thời gian toàn bộ body và không phải deadline riêng của mỗi request. Một kết nối đã mở và được tái sử dụng có thể không cần bước connect mới. `HttpConnectTimeoutException` là subclass của `HttpTimeoutException`.

### 8.2. Request timeout

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
```

Đây là timeout của **request** theo hợp đồng HTTP Client. Khi request hết thời gian chờ phản hồi, future có thể hoàn thành bất thường với `HttpTimeoutException`. Với body handler streaming, thời điểm response future hoàn tất có thể sớm hơn việc đọc xong toàn body, nên cần thêm chính sách giới hạn/cancellation cho giai đoạn tiêu thụ stream nếu cần.

### 8.3. Timeout khi chờ một future

```java
HttpResponse<String> response = future.get(2, TimeUnit.SECONDS);
```

`get(timeout, unit)` giới hạn **thời gian thread gọi chờ future**, có thể ném `TimeoutException` nếu chưa có kết quả. Nó **không tự chứng minh HTTP request đã bị hủy**. Lệnh trên là mảnh mã cần khai báo/xử lý checked exceptions của `get`.

`CompletableFuture.orTimeout(...)`, có sẵn từ Java 9, có thể hoàn thành future bất thường bằng `TimeoutException` sau thời hạn; `completeOnTimeout(...)` có thể trả giá trị thay thế. Đây là cơ chế trên `CompletableFuture`, **không** là bằng chứng server chưa nhận request hoặc mọi tài nguyên mạng đã được giải phóng.

| Thời hạn | Lỗi/hiệu ứng | Điều không được suy ra |
| --- | --- | --- |
| `connectTimeout` | Có thể `HttpConnectTimeoutException`. | Không bảo đảm request/body hoàn thành trong mức đó. |
| `HttpRequest.timeout` | Có thể `HttpTimeoutException`. | Không thay thế mọi giới hạn cho stream dài. |
| `future.get(timeout)` | `TimeoutException` của caller đang chờ. | Không tự động hủy network. |
| `future.orTimeout(...)` | Future có thể exceptional với `TimeoutException`. | Không phải rollback thao tác server. |

## 9. Cancellation và InterruptedException

### 9.1. Hủy future

`CompletableFuture.cancel(true)` có thể chuyển future chưa hoàn tất sang trạng thái hủy; `isCancelled()` và `isCompletedExceptionally()` có thể cùng trả `true`. Lúc đọc kết quả, `join()/get()` có thể ném `CancellationException`.

Với future do `HttpClient.sendAsync` trả về, hủy có thể cố gắng chấm dứt HTTP exchange nhưng **không bảo đảm request chưa đến server**. Request POST tạo đơn hàng hoặc thanh toán có thể đã được server xử lý trước khi client gọi cancel. Không tự động gửi lại hoặc coi cancel là rollback.

### 9.2. Thread bị ngắt khi chờ get

```java
try {
    HttpResponse<String> response = future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Dừng hoặc đẩy lỗi lên tầng điều phối.
}
```

Mảnh mã này cần xử lý cả `ExecutionException` nếu dùng trong chương trình thật. Khi bắt `InterruptedException`, nên **khôi phục cờ interrupt** thay vì nuốt lỗi. `join()` không khai báo checked `InterruptedException`; `HttpClient.send(...)` đồng bộ thì có thể ném `InterruptedException` trực tiếp.

## 10. Retry: không cứ IOException là thử lại

Một timeout hoặc socket bị đóng **không chứng minh server chưa xử lý request**. Retry chỉ an toàn khi kết hợp loại thao tác, khả năng phát lại body và hợp đồng server:

| Tình huống | Gợi ý |
| --- | --- |
| GET đọc tài nguyên, lỗi mạng tạm thời | Có thể thử lại với max attempts và exponential backoff/jitter. |
| Status 429 | Xem `Retry-After`, giới hạn tốc độ và quota. |
| Status 503 | Có thể cân nhắc retry theo hợp đồng endpoint. |
| Status 400/401/403 | Không retry y nguyên nếu chưa sửa input/quyền/xác thực. |
| TLS certificate/hostname không hợp lệ | Không tắt xác minh TLS để cho qua; sửa vấn đề tin cậy. |
| POST có tác dụng phụ và lỗi sau khi gửi | Chỉ retry khi có cơ chế idempotency/anti-duplicate được thiết kế. |
| Caller cố ý cancel | Thường tôn trọng yêu cầu hủy, không tự retry. |

Đừng mặc định mọi `BodyPublisher` đều có thể đọc/phát lại body sau lỗi. Đặc biệt với nguồn `ofInputStream(supplier)`, supplier phải đáp ứng hợp đồng có thể tạo nguồn phù hợp nếu yêu cầu bị gửi lại.

Cần giới hạn **số lần thử, thời gian toàn tác vụ, concurrency và backoff** để tránh tạo retry storm. Nếu mất kết nối xảy ra sau khi server đã xử lý request, retry không có idempotency có thể sinh dữ liệu trùng lặp.

## 11. Lỗi muộn khi nhận body streaming

Xem ví dụ:

```java
CompletableFuture<HttpResponse<java.io.InputStream>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofInputStream());
```

Future có thể hoàn thành bình thường khi response headers và stream sẵn sàng, **trước khi body đọc hết**. Khi tiêu thụ body:

```java
CompletableFuture<Long> processed = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofInputStream()
).thenApply(response -> {
    long total = 0;
    try (java.io.InputStream in = response.body()) {
        byte[] buffer = new byte[8192];
        int n;
        while ((n = in.read(buffer)) != -1) {
            total += n;
            if (total > 1_000_000) {
                throw new IOException("Response too large");
            }
        }
        return total;
    } catch (IOException e) {
        throw new java.io.UncheckedIOException(e);
    }
});
```

Đây là **đoạn mã minh họa** có `client`/`request` trong phạm vi. `thenApply` ở đây có thể chờ dữ liệu qua mạng trong lúc đọc stream. Trong ứng dụng có nhiều request, cân nhắc `thenApplyAsync(..., executor)` với giới hạn concurrency khi phù hợp.

**Điểm chính:**
- Đóng stream bằng `try-with-resources` dù đọc thành công, lỗi I/O hay vượt ngưỡng.
- Stage `processed` có thể exceptional do `UncheckedIOException` phát sinh khi tiêu thụ body, dù **future response ban đầu** đã trả về bình thường.
- `statusCode()==200` không chứng minh mọi byte/đối tượng nghiệp vụ đã tải đầy đủ.
- Giới hạn 1 MB trong đoạn này chỉ là ví dụ. Với nội dung lớn/không tin cậy, cần đặt chính sách kích thước, thời gian và nguồn dữ liệu phù hợp.
- Nếu dùng `BodyHandlers.ofLines()`, phải đóng `Stream<String>` và có thể nhận `UncheckedIOException` trong terminal operation.

## 12. Logging, quan sát và phân loại lỗi an toàn

Khi ghi nhận một lời gọi HTTP lỗi, thông tin hữu ích gồm method, hostname/endpoint đã lọc, thời gian xử lý, số lần thử, **giai đoạn lỗi**, nhóm exception, và status/header khi **thực sự có response**.

Tránh:
- Gán status `500` tùy ý cho một lỗi I/O mà không có HTTP response.
- Log nguyên `Authorization`, bearer token, cookie, URL query nhạy cảm hoặc request/response body có dữ liệu riêng tư.
- Dựa vào nguyên văn thông báo lỗi hệ thống để quyết định retry hoặc phân loại nghiệp vụ.
- Biến tất cả lỗi thành body rỗng rồi báo thành công.

Với hệ thống nhiều tầng, nên biểu diễn kết quả bằng các nhánh rõ ràng: **success**, **HTTP error**, **transport error**, **timeout**, **cancelled** và **processing error**. Chuyển lỗi thành fallback chỉ khi hợp đồng nghiệp vụ cho phép.

## 13. Ma trận kiểm thử nên có

| Ca | Đầu vào/tình huống | Điều kiểm tra |
| --- | --- | --- |
| Success | Server trả 200 và body hợp lệ. | Future bình thường, dữ liệu đúng. |
| HTTP error | Server trả 404/503 và body hoàn chỉnh. | Future bình thường; `statusCode()` phản ánh lỗi. |
| Truncated body | Server công bố body dài hơn số byte gửi. | Với `ofString`, future lỗi I/O; không trả body hợp lệ. |
| Request timeout | Server chậm hơn `request.timeout`. | Exceptional completion với `HttpTimeoutException`/nhóm phù hợp. |
| Connect timeout | Không thiết lập được kết nối trong thời hạn. | Phân loại timeout kết nối; tránh fixture mạng công khai thiếu ổn định. |
| TLS failure | Chứng chỉ không tin cậy trong test nội bộ. | Lỗi TLS, không hạ chính sách bảo mật. |
| Callback error | Parser trong `thenApply` ném lỗi kiểm soát. | Stage downstream exceptional, phân biệt lỗi ứng dụng. |
| Recovery | `exceptionally` trả fallback được phép. | Future phục hồi rõ ràng, không che lỗi ngoài hợp đồng. |
| Cancellation | Caller hủy future đang chạy. | Trạng thái hủy; không giả định server rollback. |
| Streaming body error | I/O lỗi khi đọc `InputStream` sau response. | Phát hiện lỗi muộn và đóng stream. |
| Validation error | HTTP 200 nhưng JSON/body sai schema. | Lỗi nội dung/validation, không báo network failure. |

Không viết test âm bắt **mọi `Throwable`** rồi báo PASS, vì có thể bắt cả `AssertionError` của test. Trong ví dụ đầy đủ, nhóm lỗi body bị cắt được kiểm tra bằng `instanceof IOException` sau khi unwrap, còn status 503 được kiểm tra riêng như response hợp lệ.

## 14. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| `future.join()` trả response 503 là future lỗi. | 503 là HTTP status, không tự là exception. | Kiểm tra `response.statusCode()`. |
| Chỉ xử lý `exceptionally` cho toàn bộ 4xx/5xx. | Callback này chỉ chạy khi stage exceptional. | Phân loại status ở nhánh normal. |
| Bắt `IOException` trực tiếp quanh `future.join()`. | `join()` dùng `CompletionException` runtime. | Unwrap cause trước khi phân loại. |
| Nghĩ `join()` và `get()` ném cùng exception. | `get()` dùng `ExecutionException`/`InterruptedException`. | Chọn API phù hợp và xử lý đúng wrapper. |
| Kiểm tra `IOException` trước `HttpTimeoutException`. | Nhánh tổng quát nuốt subtype timeout. | Kiểm tra subtype trước. |
| `isDone()==true` nghĩa request thành công. | Có thể hoàn tất do exception/hủy. | Xem kết quả và trạng thái phù hợp. |
| `whenComplete` luôn phục hồi lỗi. | Chủ yếu dùng quan sát, không chuyển lỗi thành kết quả. | Dùng `handle`/`exceptionally` khi cần. |
| Dùng fallback `""` cho mọi lỗi. | Có thể che thất bại. | Trả kết quả lỗi có nghĩa hoặc chuyển lỗi lên trên. |
| `get(timeout)` hết hạn nghĩa request đã hủy. | Chỉ caller ngừng chờ. | Hủy/cleanup riêng khi cần. |
| `cancel(true)` bảo đảm server chưa xử lý. | Không phải transaction rollback. | Chính sách idempotency và hủy rõ ràng. |
| Dùng `thenApply` parse sai nhưng báo lỗi mạng. | Lỗi callback không nhất thiết liên quan transport. | Phân biệt tầng parse/validation. |
| Có response `ofInputStream` là tải xong. | Stream vẫn còn byte chưa đọc. | Đọc/đóng stream và xử lý lỗi muộn. |
| Retry vô hạn POST sau socket reset. | Server có thể đã xử lý tác vụ. | Retry có điều kiện và chống trùng lặp. |
| Log toàn bộ headers và body. | Lộ dữ liệu nhạy cảm. | Log metadata đã lọc. |

## 15. Bài tập tự đánh giá

**Câu 1.** Một server trả HTTP 503 hoàn chỉnh. `future.isCompletedExceptionally()` bắt buộc phải là `true` không?

**Đáp án:** Không. Future có thể bình thường với `HttpResponse` có `statusCode()==503`.

**Câu 2.** Future exceptional có nghĩa server đã trả HTTP 500 không?

**Đáp án:** Không. Có thể không nhận response vì DNS, TLS, timeout, socket lỗi, hoặc callback ứng dụng thất bại.

**Câu 3.** Vì sao `join()` và `get()` cho lỗi nhìn khác nhau?

**Đáp án:** `join()` thường ném `CompletionException` runtime, còn `get()` ném `ExecutionException` checked. Xem `cause` để tìm nguyên nhân gốc.

**Câu 4.** Vì sao cần kiểm tra `HttpTimeoutException` trước `IOException`?

**Đáp án:** Timeout là subclass của IOException. Kiểm tra tổng quát trước sẽ không còn phân loại timeout riêng.

**Câu 5.** `exceptionally` có chạy sau HTTP 404 không?

**Đáp án:** Không nếu stage trước nhận response 404 bình thường và không có callback nào chủ động ném lỗi cho status đó.

**Câu 6.** `handle` khác `whenComplete` thế nào?

**Đáp án:** `handle` chuyển cả hai nhánh thành giá trị mới; `whenComplete` chủ yếu quan sát và thường giữ kết quả/lỗi gốc.

**Câu 7.** `future.get(2, TimeUnit.SECONDS)` ném `TimeoutException` chứng minh server chưa nhận request không?

**Đáp án:** Không. Đó là timeout chờ ở caller; network có thể vẫn đang diễn ra.

**Câu 8.** `ofInputStream` trả response nhưng khi đọc stream gặp IOException có mâu thuẫn không?

**Đáp án:** Không. Response future có thể xong trước giai đoạn tiêu thụ body; phải đóng stream và báo lỗi đọc muộn.

**Câu 9.** Có thể retry mọi POST gặp `ConnectException` không?

**Đáp án:** Không mặc định; cần hiểu side effect, hợp đồng retry và cơ chế idempotency của endpoint.

**Câu 10.** Khi `get()` ném `InterruptedException`, làm gì với cờ interrupt?

**Đáp án:** Khôi phục bằng `Thread.currentThread().interrupt()`, sau đó dừng hoặc chuyển sự kiện lên tầng điều phối.

**Câu 11.** Parser trong `thenApply` ném `IllegalArgumentException`. Đây chắc chắn là lỗi HTTP transport?

**Đáp án:** Không. Stage downstream exceptional vì **lỗi xử lý dữ liệu**, không nhất thiết do network.

**Câu 12.** Vì sao không assert chuỗi lỗi cụ thể của `IOException` trong test?

**Đáp án:** Nội dung thông báo có thể khác theo JDK, giao thức, hệ điều hành. Cần assert nhóm lỗi và kết quả nghiệp vụ.

## 16. Tổng kết và tài liệu chính thức

- `HttpClient.sendAsync` trong Java 11 trả `CompletableFuture<HttpResponse<T>>`. Mã HTTP 404/503 là **status trong response**, không tự làm future exceptional.
- `IOException` và subclass như `HttpTimeoutException` có thể làm future hoàn thành bất thường; cũng cần phân biệt lỗi callback/parse và cancellation.
- `join()` thường bọc lỗi trong `CompletionException`; `get()` dùng `ExecutionException`. Unwrap wrapper phù hợp rồi mới phân loại lỗi.
- `thenApply` dành cho normal completion; `exceptionally` cho error recovery; `handle` cho cả hai; `whenComplete` cho quan sát.
- Phân biệt timeout kết nối, timeout request và timeout khi chờ future. Không xem timeout/hủy là bằng chứng server đã rollback.
- Retry phải tuân thủ idempotency, giới hạn số lần, backoff, thời hạn và khả năng phát lại request body.
- Với body streaming, future của response có thể hoàn tất trước khi đọc xong body; luôn đóng stream và xử lý lỗi I/O ở giai đoạn tiêu thụ.
- Những kiến thức và API trên **vẫn còn áp dụng trong Java hiện đại**, không dùng cách tiếp cận phụ thuộc API thử nghiệm hoặc lỗi thời.

Nguồn tham khảo:
- [Oracle Java SE 11 — HttpClient.sendAsync](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Oracle Java SE 11 — HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html).
- [Oracle Java SE 11 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpTimeoutException.html).
- [Oracle Java SE 11 — HttpConnectTimeoutException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html).
- [Oracle Java SE 11 — CompletableFuture](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html).
- [Oracle Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html).
- [Oracle Java SE 11 — CompletionException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletionException.html).
- [Oracle Java SE 11 — ExecutionException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ExecutionException.html).
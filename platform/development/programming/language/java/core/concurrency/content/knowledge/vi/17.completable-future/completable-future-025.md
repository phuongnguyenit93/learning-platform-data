# HttpClient.sendAsync(): ghép phản hồi HTTP, lỗi mạng và CompletableFuture

## 1. Bài toán và phạm vi

Java 11+ cung cấp API HTTP client trong gói `java.net.http`. Phương thức `HttpClient.sendAsync()` gửi yêu cầu HTTP và trả về `CompletableFuture<HttpResponse<T>>`, cho phép biểu diễn kết quả tương lai bằng các bước xử lý, kết hợp, phục hồi lỗi và kiểm soát thời hạn. Bài này dùng Java 17+ thuần, trong ngữ cảnh **Java concurrency**; không phụ thuộc Spring, annotation hay cơ chế bất đồng bộ của framework.

Sau bài học, bạn cần phân biệt được:

- **Phản hồi HTTP đã nhận**: có `statusCode()`, headers và body; mã `404`, `429`, `500` vẫn là một phản hồi HTTP bình thường ở cấp API.
- **Thất bại của quá trình trao đổi**: không hoàn tất được yêu cầu/nhận phản hồi do DNS, kết nối, TLS, timeout, lỗi đọc body hoặc hủy tác vụ; `CompletableFuture` hoàn tất *exceptionally*.
- **Lỗi ứng dụng tự chuyển đổi**: sau khi đọc status, chương trình chủ động ném ngoại lệ để biến một HTTP status không chấp nhận được thành nhánh lỗi của pipeline.

Đây là ba trường hợp khác nhau; gộp chúng thành một “HTTP bị lỗi” sẽ khiến retry, thông báo người dùng và quan sát hệ thống thiếu chính xác.

## 2. Các thành phần và luồng thực thi

`HttpClient` quản lý cấu hình và tái sử dụng kết nối; `HttpRequest` mô tả URI, method, headers, body và timeout; `HttpResponse.BodyHandler<T>` quyết định cách nhận body; `HttpResponse<T>` chứa status, headers, body; `CompletableFuture` cung cấp các stage để xử lý kết quả hoặc exception.

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(URI.create("https://example.org/data"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> pending =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
```

Đoạn trên là **mảnh mã minh họa** đặt trong một phương thức có imports thích hợp, không phải chương trình chạy độc lập. `sendAsync` trả future để có thể gắn các stage; không phải gọi `get()` hoặc `join()` ngay. HTTP exchange diễn ra bất đồng bộ, và stage phụ thuộc chạy khi dữ liệu sẵn sàng hoặc khi xảy ra lỗi. Thứ tự và thread thực thi callback tùy stage, executor và thời điểm hoàn tất; đừng giả định callback luôn chạy trên thread gọi ban đầu hay một “HTTP thread” cố định.

Sơ đồ khái niệm:

```text
HttpRequest --sendAsync--> CompletableFuture<HttpResponse<T>>
                               |
                      trao đổi HTTP hoàn tất?
                      /                    \
                 thành công               thất bại
                    |                         |
         HttpResponse(status, body)      CompletionException/cause
                    |                         |
           kiểm tra statusCode()        handle / exceptionally
                    |
           2xx? dùng body; khác? quyết định theo nghiệp vụ
                    |
            thenApply / thenCompose / handle ...
```

**Quan trọng:** `sendAsync` không mặc định ném exception chỉ vì server trả `400` hoặc `500`. Nếu gọi `thenApply(HttpResponse::body)` thẳng, bạn có thể vô tình xử lý nội dung trang lỗi như dữ liệu hợp lệ.

## 3. Mẫu xử lý status và body

Chọn một quy ước ứng dụng rõ ràng. Với một thao tác yêu cầu thành công `2xx`:

```java
CompletableFuture<String> result = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
        .thenApply(response -> {
            int status = response.statusCode();
            if (status < 200 || status >= 300) {
                throw new HttpStatusException(status);
            }
            return response.body();
        });
```

`HttpStatusException` trong ví dụ là **lớp do ứng dụng tự định nghĩa**, không phải một ngoại lệ chuẩn được `HttpClient` tự sinh ra. Nếu contract yêu cầu đúng `200`, hãy kiểm tra đúng `200`; nếu thao tác chấp nhận `201`, `202`, `204` thì quy tắc phải phù hợp. `204 No Content` không có body hữu ích; `304 Not Modified` chỉ nên được xử lý theo ngữ cảnh cache/conditional request, không thể coi mọi status khác `2xx` như nhau.

Nếu cần giữ metadata, đừng vội biến `HttpResponse<T>` thành `T`: hãy giữ response hoặc ánh xạ sang một result type chứa `status`, `headers`, `body`. Với body lớn/binary/streaming, chọn `BodyHandlers.ofFile(...)`, `ofByteArray()`, `ofInputStream()` hoặc handler chuyên biệt thích hợp thay vì luôn tải cả body vào một `String`. Khi nhận `InputStream`, phải quản lý đóng stream và tiêu thụ dữ liệu đúng cách.

## 4. Chương trình Java 17 chạy độc lập, không phụ thuộc Internet

Ví dụ sau khởi tạo HTTP server ở loopback với cổng do hệ điều hành chọn. Nó thực hiện hai yêu cầu bất đồng bộ, một yêu cầu thành công và một yêu cầu trả `404`. Cả hai đều được xử lý qua `CompletableFuture`; phần HTTP status được chuyển thành exception **một cách chủ động**.

Lưu toàn bộ mã trong tệp `AsyncHttpDemo.java`:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class AsyncHttpDemo {
    static final class HttpStatusException extends RuntimeException {
        final int status;

        HttpStatusException(int status) {
            super("HTTP status " + status);
            this.status = status;
        }
    }

    static CompletableFuture<String> fetch(HttpClient client, URI uri) {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(2))
                .GET()
                .build();

        return client.sendAsync(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
                .thenApply(response -> {
                    int status = response.statusCode();
                    if (status < 200 || status >= 300) {
                        throw new HttpStatusException(status);
                    }
                    return response.body();
                });
    }

    static Throwable unwrap(Throwable error) {
        Throwable current = error;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    static String describe(CompletableFuture<String> future) {
        return future.handle((body, error) -> {
            if (error == null) {
                return "OK: " + body;
            }
            Throwable root = unwrap(error);
            if (root instanceof HttpStatusException httpError) {
                return "HTTP: " + httpError.status;
            }
            return "NETWORK/EXCHANGE: " + root.getClass().getSimpleName();
        }).join();
    }

    static void reply(HttpExchange exchange, int code, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(code, bytes.length);
        try (var body = exchange.getResponseBody()) {
            body.write(bytes);
        }
    }

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService serverExecutor = Executors.newFixedThreadPool(2);
        server.setExecutor(serverExecutor);
        server.createContext("/ok", ex -> reply(ex, 200, "ready"));
        server.createContext("/missing", ex -> reply(ex, 404, "not found"));
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();
            String base = "http://127.0.0.1:" + server.getAddress().getPort();

            CompletableFuture<String> ok =
                    fetch(client, URI.create(base + "/ok"));
            CompletableFuture<String> missing =
                    fetch(client, URI.create(base + "/missing"));

            System.out.println(describe(ok));
            System.out.println(describe(missing));
        } finally {
            server.stop(0);
            serverExecutor.shutdownNow();
        }
    }
}
```

Lệnh trên JDK 17+ (`jdk.httpserver` là module JDK dành cho ví dụ thử nghiệm):

```bash
javac --add-modules jdk.httpserver AsyncHttpDemo.java
java --add-modules jdk.httpserver AsyncHttpDemo
```

Kết quả chuẩn:

```text
OK: ready
HTTP: 404
```

Giải thích từng bước:

1. Hai `fetch(...)` bắt đầu HTTP exchange mà không chặn thread gọi tại `sendAsync`. Server nhận hai đường dẫn riêng và gửi response.
2. `/ok` trả `200`, nên `thenApply` lấy body `ready`; `handle` trả chuỗi `OK: ready`.
3. `/missing` trả response `404` đầy đủ; `thenApply` tự ném `HttpStatusException`. Future sau `thenApply` hoàn tất exceptionally, rồi `handle` đọc nguyên nhân và định dạng `HTTP: 404`.
4. `join()` trong `describe` chỉ dùng tại ranh giới chương trình console để đợi và in kết quả. Trong server/event loop, gọi `join()` ngay sau `sendAsync()` có thể đánh mất lợi ích bất đồng bộ hoặc gây nghẽn thread.

Thứ tự **hoàn tất mạng** của hai request không được bảo đảm; thứ tự **hai dòng in** ở đây được quyết định bởi hai lời gọi `println` tuần tự.

## 5. Các nhóm lỗi và cách phân nhánh

| Tình huống | Điều nhận từ `sendAsync` | Xử lý phù hợp |
| --- | --- | --- |
| HTTP `200`, `201`, `204` | Future hoàn tất bình thường với `HttpResponse<T>` | Kiểm tra contract, dùng body nếu có |
| HTTP `400`, `404`, `409` | Future **vẫn hoàn tất bình thường** với response | Đọc status/body lỗi; quyết định kết quả nghiệp vụ, không retry mù quáng |
| HTTP `429`, `502`, `503`, `504` | Future bình thường nếu đã nhận response | Cân nhắc retry theo method, tải hệ thống, `Retry-After` và chính sách giới hạn |
| DNS, kết nối bị từ chối, TLS handshake, đóng kết nối, lỗi I/O | Future có thể hoàn tất exceptionally | Kiểm tra cause; ghi nhận loại lỗi kỹ thuật và cân nhắc thử lại |
| Không nhận được response đúng thời hạn request | Future exceptionally, thường chứa `HttpTimeoutException` | Thiết lập timeout, classify retry riêng |
| HTTP status không được ứng dụng chấp nhận | Lỗi xuất hiện ở stage do **bạn chủ động throw** | Dùng exception/result type riêng cho HTTP status |
| `CompletableFuture` bị hủy | Future bị cancel/exceptionally | Xác định ai hủy, dọn dẹp và không coi là HTTP status |

Ngoại lệ từ stage có thể được bọc bằng `CompletionException` khi dùng `join()`; `get()` ném `ExecutionException` và phải xử lý `InterruptedException`. Vì vậy, log và phân loại theo `getCause()` (cẩn thận chỉ bóc các wrapper phù hợp), thay vì so trực tiếp tên lớp của exception bên ngoài.

Một số loại nguyên nhân thực tế gồm `java.net.ConnectException`, `java.net.UnknownHostException`, `javax.net.ssl.SSLException`, `java.net.http.HttpTimeoutException` và `java.net.http.HttpConnectTimeoutException`. Không dựa vào một loại ngoại lệ cụ thể cho mọi biến thể hệ điều hành, DNS hoặc proxy; ngữ cảnh runtime có thể ảnh hưởng chuỗi cause.

Không đưa token `Authorization`, cookie hoặc toàn bộ body chứa dữ liệu nhạy cảm vào log. Với HTTP status, có thể log method, route an toàn, status, thời gian và correlation ID khi hệ thống có sẵn.

## 6. Chọn stage đúng: biến đổi, phụ thuộc, kết hợp, phục hồi

### `thenApply`: biến đổi kết quả đã có

```java
CompletableFuture<Integer> length =
        fetch(client, uri).thenApply(String::length);
```

Khi `fetch` thành công, stage cho độ dài; nếu `fetch` lỗi, stage biến đổi bị bỏ qua và lỗi lan xuống. `thenApply` thích hợp cho thao tác ngắn, không chặn. Callback có thể chạy trên thread hoàn tất giai đoạn trước, vì vậy tránh `sleep`, I/O blocking và tính toán nặng ngay trong callback.

### `thenCompose`: request B cần kết quả của request A

```java
CompletableFuture<String> detail = fetch(client, indexUri)
        .thenCompose(relativePath -> {
            URI resolved = indexUri.resolve(relativePath);
            return fetch(client, resolved);
        });
```

Đây là **mảnh mã minh họa** với giả định nội dung của `indexUri` là đường dẫn tin cậy. Khi dữ liệu từ bên ngoài, phải xác minh scheme, host, path và chính sách cho phép trước khi gửi request thứ hai, để tránh truy cập URI tùy ý. `thenCompose` làm phẳng `CompletableFuture<CompletableFuture<String>>` thành một future; không dùng `thenApply` để lồng future nếu cần kết quả cuối. Request thứ hai chỉ được bắt đầu sau khi request đầu thành công.

### `thenCombine` và `allOf`: nhiều request độc lập

```java
CompletableFuture<String> combined =
        fetch(client, firstUri)
          .thenCombine(fetch(client, secondUri),
                  (first, second) -> first + " | " + second);
```

Hai `fetch` được khởi tạo độc lập, cho phép các request chồng thời gian chờ mạng. `thenCombine` nhận giá trị của cả hai khi cùng thành công. `CompletableFuture.allOf(f1, f2, ...)` phù hợp để chờ một tập future, nhưng future trả về từ `allOf` có kiểu `CompletableFuture<Void>`; nó **không** chứa danh sách kết quả. Sau khi `allOf` thành công mới lấy từng kết quả theo thứ tự mong muốn. Nếu một future thất bại, phép kết hợp thông thường cũng thất bại; không có cơ chế tự thu thập mọi lỗi hay tự hủy các request còn lại.

### `handle`, `exceptionally`, `whenComplete` và `exceptionallyCompose`

- `handle((value, error) -> ...)` chạy cho cả thành công và lỗi, trả một **giá trị mới** để phục hồi hoặc chuyển đổi. Ví dụ `describe` sử dụng `handle` để tạo thông báo nhất quán.
- `exceptionally(error -> fallback)` chỉ chạy khi lỗi và tạo một giá trị thay thế cùng kiểu `T`. Nếu phục hồi tùy tiện thành chuỗi rỗng, bên gọi không còn phân biệt dữ liệu thật với lỗi.
- `whenComplete((value, error) -> ...)` phù hợp quan sát/metrics/log nhẹ. Nó thường chuyển tiếp kết quả hoặc lỗi ban đầu; không phải toán tử phục hồi. Nếu callback cũng ném exception, lỗi bổ sung có thể ảnh hưởng kết quả theo quy tắc của API.
- `exceptionallyCompose(error -> otherFuture)` (có trong Java 17) dùng khi nhánh phục hồi cũng **bất đồng bộ**, chẳng hạn gọi một nguồn dự phòng sau loại lỗi cho phép.

Ví dụ chính sách fallback cho `404` (mảnh mã dùng `fetch`, `unwrap` và `HttpStatusException` đã định nghĩa ở chương trình trên):

```java
CompletableFuture<String> withFallback = fetch(client, primaryUri)
        .exceptionallyCompose(error -> {
            Throwable cause = unwrap(error);
            if (cause instanceof HttpStatusException httpError
                    && httpError.status == 404) {
                return fetch(client, secondaryUri);
            }
            return CompletableFuture.failedFuture(cause);
        });
```

Fallback chỉ áp dụng `404` theo yêu cầu nghiệp vụ; timeout, lỗi TLS hoặc status khác tiếp tục là lỗi. `CompletableFuture.failedFuture` có từ Java 9. Không dùng một hàm `exceptionally` duy nhất để phân biệt mọi trường hợp rồi trả dữ liệu giả mà không ghi nhận nguyên nhân.

## 7. Timeout, cancel và kiểm soát tài nguyên

Có ba cơ chế với ý nghĩa khác nhau:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2)) // thiết lập kết nối
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(4))        // thời hạn HTTP request
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> pending =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

pending.orTimeout(5, java.util.concurrent.TimeUnit.SECONDS);
```

- `connectTimeout` áp dụng cho thiết lập kết nối mới; tái sử dụng kết nối hiện có không nhất thiết trải qua bước connect. Không dùng nó thay thế timeout request.
- `HttpRequest.timeout` đặt thời hạn ở cấp trao đổi HTTP; khi hết hạn có thể nhận `HttpTimeoutException`. Đây là lựa chọn cơ bản để giới hạn một request.
- `orTimeout` đặt thời hạn cho **CompletableFuture** và hoàn tất chính future ấy exceptionally với `TimeoutException` nếu đến hạn. Việc future timed out không đảm bảo I/O bên dưới đã dừng ngay; đừng coi đây là thay thế hoàn toàn cho timeout request và quản lý resource.
- `completeOnTimeout(fallback, ...)` hoàn tất future bằng giá trị fallback nếu đến hạn. Chỉ sử dụng khi fallback thật sự có nghĩa nghiệp vụ; không để timeout bị ngụy trang thành phản hồi server.

Hủy `CompletableFuture` gốc mà `HttpClient.sendAsync` trả về bằng `cancel(true)` có thể yêu cầu dừng HTTP exchange và giải phóng tài nguyên, nhưng không bảo đảm yêu cầu chưa được gửi hoặc việc hủy có hiệu lực tức thì. Hủy một future **phụ thuộc** sau `thenApply` không đương nhiên hủy future gốc. Hủy không phải cơ chế “rollback” server: thao tác ghi đã được server thực hiện có thể vẫn tồn tại.

Khi gặp `InterruptedException` từ `get()`, lưu ý khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()` nếu đang ở lớp xử lý thích hợp, đồng thời thực hiện cleanup. Với ứng dụng chạy dài, tái sử dụng `HttpClient` thay vì tạo client mới cho từng request, đặt giới hạn số request đồng thời phù hợp và tránh giữ body lớn trong bộ nhớ.

## 8. Retry, backpressure và tính đúng đắn

Bất đồng bộ **không đồng nghĩa** được phép phát hàng nghìn request không giới hạn. Gửi quá nhiều future cùng lúc có thể làm nghẽn connection pool, bão hòa tài nguyên, tạo áp lực lên server và tăng số timeout. Hạn chế concurrency bằng cách điều phối số tác vụ đang chạy (ví dụ `Semaphore` hoặc hàng đợi có giới hạn); không giữ semaphore bằng `acquire()` rồi chặn thread trong callback HTTP. Có thể quản lý permit quanh lúc phát request và hoàn trả trong `whenComplete`, đồng thời bảo đảm cleanup cả khi việc khởi tạo request lỗi.

Chỉ retry khi có lý do:

1. **Loại thao tác:** `GET`, `HEAD` thường an toàn hơn cho retry so với `POST` có tác dụng phụ. Nếu retry thao tác ghi, cần cơ chế idempotency hoặc xác nhận contract.
2. **Loại thất bại:** timeout/connection reset có thể xảy ra sau khi server đã xử lý request; không thể suy ra “server chưa nhận”. HTTP `429`, `503` thường cần `Retry-After` hoặc chính sách riêng; HTTP `400` thông thường không có lợi khi gửi lại nguyên trạng.
3. **Ngân sách:** giới hạn số lần thử, tổng deadline, exponential backoff có jitter và quan sát số lần retry. Tránh vòng retry vô hạn hoặc retry đồng loạt tạo bão lưu lượng.
4. **Hủy/timeout tổng:** truyền chính sách cancel/deadline xuống các nhánh con và dọn tài nguyên theo khả năng thực tế.

Nếu cần delay trước retry trong một chuỗi asynchronous, có thể dùng `CompletableFuture.delayedExecutor(...)` để lên lịch bước tiếp theo; tránh `Thread.sleep()` trong callback dùng chung executor. Một retry có backoff phải thực sự thực hiện lại request trong future mới, không “chạy lại” một `CompletableFuture` đã hoàn tất.

## 9. Các sai lầm thường gặp và cách sửa

| Cách làm dễ sai | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `sendAsync(...).join()` ngay ở mọi nơi | Chặn thread gọi, giảm lợi ích concurrency | Trả future xuyên qua các lớp, chỉ chờ ở ranh giới cần đồng bộ |
| Coi `404`/`500` là lỗi mạng do `sendAsync` tự ném | Phân loại sai, bỏ qua body/status | Kiểm tra `statusCode()` và tự ánh xạ response |
| Dùng `thenApply` cho request thứ hai trả future | Lồng `CompletableFuture<CompletableFuture<T>>` | Dùng `thenCompose` |
| Dùng `exceptionally(e -> null)` cho mọi lỗi | Che lỗi thật, dễ `NullPointerException` về sau | Phục hồi có điều kiện hoặc truyền lỗi tiếp |
| Dùng `whenComplete` để thay kết quả thất bại | Không khôi phục kết quả như mong muốn | Dùng `handle` hoặc `exceptionally` |
| Chỉ cấu hình `connectTimeout` | Thời gian đọc response vẫn có thể không như kỳ vọng | Thêm timeout tại `HttpRequest`/deadline tổng |
| Hủy stage cuối và nghĩ HTTP đã dừng chắc chắn | Exchange gốc có thể còn chạy | Quản lý future do `sendAsync` trả về và hiểu giới hạn cancel |
| Retry mọi `POST` sau timeout | Có thể tạo tác dụng phụ lặp lại | Dùng idempotency key/contract và retry có giới hạn |
| Xử lý JSON hoặc stream lớn trên stage ngắn trong executor không kiểm soát | Giữ thread lâu, tăng độ trễ các completion khác | Chọn body handler phù hợp và tách xử lý nặng sang executor có giới hạn |

## 10. Tự kiểm chứng kiến thức

1. Server trả `503` cùng body `"maintenance"`. `sendAsync(..., ofString())` có tự hoàn tất exceptionally vì status `503` không? **Không.** Response có status/body bình thường; mã ứng dụng quyết định xử lý như thế nào.
2. Kết nối DNS thất bại trước khi có response. `thenApply(HttpResponse::body)` có chạy không? **Không** trên đường thành công; exception đi qua chain và có thể xử lý ở `handle`/`exceptionally`.
3. Muốn lấy dữ liệu A rồi dựa trên A gọi HTTP B, dùng stage nào? **`thenCompose`**. Nếu A và B độc lập, khởi tạo cả hai rồi cân nhắc `thenCombine`.
4. `orTimeout` hoàn tất future bằng `TimeoutException` có bảo đảm server chưa xử lý request không? **Không**; nó kiểm soát trạng thái future, không phải giao dịch rollback.
5. Vì sao ví dụ local dùng `join()` vẫn đúng? Nó nằm tại ranh giới in kết quả của **chương trình console**; việc khởi tạo hai request diễn ra trước khi đợi kết quả.

### Ghi nhớ

`HttpClient.sendAsync` trả một **future của HTTP response**, không phải future tự phân loại mọi HTTP status thành exception. Hãy giữ riêng ba tầng: trao đổi HTTP có hoàn tất không, status có hợp lệ theo contract không, và dữ liệu có đúng nghiệp vụ không. Từ đó dùng `thenApply` để biến đổi, `thenCompose` cho tác vụ phụ thuộc, `thenCombine` cho tác vụ độc lập, `handle`/`exceptionally` để phục hồi có chủ đích, đồng thời quản lý timeout, cancel, giới hạn concurrency và retry theo tính idempotent.

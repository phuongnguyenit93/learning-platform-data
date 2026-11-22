# CompletableFuture<HttpResponse<T>> từ HttpClient.sendAsync — HTTP bất đồng bộ trong Java 11+

> **Chủ đề:** HTTP bất đồng bộ. Từ Java 11, `java.net.http.HttpClient` cung cấp `sendAsync` để gửi HTTP request và nhận một `CompletableFuture<HttpResponse<T>>`. API này vẫn là cơ chế chuẩn được hỗ trợ trên JDK hiện đại. Trọng tâm bài học là hiểu **Future chứa response**, cách xử lý status/body, ghép các tác vụ, xử lý lỗi và quản lý tài nguyên mà **không chặn thread gọi ngay tại lúc gửi**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt rõ `send` (đồng bộ) và `sendAsync` (bất đồng bộ) của Java HTTP Client.
2. Giải thích generic `CompletableFuture<HttpResponse<T>>` và cách `BodyHandler<T>` quyết định kiểu `T`.
3. Gửi GET/POST bất đồng bộ, lấy `statusCode()`, `headers()`, `body()` khi response sẵn sàng.
4. Dùng `thenApply`, `thenCompose`, `thenCombine`, `allOf` để biến đổi và phối hợp nhiều HTTP request mà không gọi `join()` sớm.
5. Hiểu `exceptionally`, `handle`, `whenComplete` và cách ngoại lệ I/O/timeout được truyền qua Future.
6. Phân biệt `join`, `get`, `get(timeout, unit)`; biết tại sao một thao tác “bất đồng bộ” vẫn có thể chặn ở bước chờ kết quả.
7. Áp dụng `HttpRequest.timeout`, `HttpClient.connectTimeout`, `CompletableFuture.orTimeout`, cancellation và giới hạn concurrency một cách chính xác.
8. Thực hiện chương trình Java 11+ hoàn chỉnh, dùng HTTP server cục bộ để kiểm kết quả ổn định, không phụ thuộc Internet.

## 2. Cấu trúc trả về: vì sao là CompletableFuture<HttpResponse<T>>?

Chữ ký API rút gọn:

~~~java
<T> CompletableFuture<HttpResponse<T>> sendAsync(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler
);
~~~

Đây là **chữ ký để đọc API**, không phải đoạn mã có thể chạy độc lập. `T` là kiểu thân phản hồi do `BodyHandler<T>` cung cấp. `CompletableFuture<X>` mô tả **một kết quả kiểu X sẽ có sau**, có thể hoàn thành bình thường hoặc thất bại.

Cách phân lớp:

~~~text
CompletableFuture<HttpResponse<T>>
|               |            |
|               |            +-- Kiểu body do BodyHandler quyết định
|               +--------------- HTTP response: status, headers, URI, body...
+------------------------------- Kết quả ở tương lai, chưa chắc đã sẵn sàng
~~~

Ví dụ:

~~~java
CompletableFuture<HttpResponse<String>> textFuture =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

CompletableFuture<HttpResponse<byte[]>> bytesFuture =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofByteArray());

CompletableFuture<HttpResponse<Void>> ignoredFuture =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.discarding());
~~~

**Ba đoạn minh họa** trên giả định `client`, `request` đã tồn tại và đã import các lớp. Lưu ý những request trên có thể được gửi **ba lần** nếu chạy cả ba dòng, không phải ba góc nhìn trên cùng một HTTP exchange.

| BodyHandler | Kiểu `T` | Khi Future hoàn thành bình thường |
| --- | --- | --- |
| `ofString(charset)` | `String` | `HttpResponse<String>` chứa body văn bản đã giải mã |
| `ofByteArray()` | `byte[]` | `HttpResponse<byte[]>` có mảng byte body |
| `discarding()` | `Void` | `HttpResponse<Void>`, body thường là `null`; metadata vẫn còn |
| `ofFile(path)` | `Path` | `HttpResponse<Path>`, body được ghi ra file |
| `ofInputStream()` | `InputStream` | `HttpResponse<InputStream>`, caller còn phải đọc/đóng luồng |

**Đặc biệt:** với `BodyHandlers.ofInputStream()`, Future có thể hoàn thành khi đã có headers/status, **trước khi toàn bộ body được đọc**. `CompletableFuture` hoàn thành không phải lúc nào cũng đồng nghĩa “tất cả byte đã được tải hết”; điều đó phụ thuộc handler. Với `ofString` và `ofByteArray`, body đã được tích lũy thành kết quả khi Future hoàn thành.

## 3. sendAsync thực sự bất đồng bộ ở đâu?

So sánh:

~~~java
// Đồng bộ: thread hiện tại chờ send trả response hoặc lỗi.
HttpResponse<String> sync = client.send(
        request,
        HttpResponse.BodyHandlers.ofString());

// Bất đồng bộ: nhận ngay Future đại diện cho kết quả sẽ có.
CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString());
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. `send` yêu cầu xử lý `IOException` và `InterruptedException` trực tiếp; lỗi mạng của `sendAsync` thường được chuyển thành trạng thái hoàn thành thất bại của Future.

Dòng thời gian:

~~~text
Thread gọi:       tạo request -- sendAsync -- làm công việc khác -- gắn callback
                                  |                                    |
                                  v                                    |
HTTP Client:                  gửi / nhận status / headers / body        |
                                  |                                    |
                                  +---- hoàn thành CompletableFuture ---+
                                                                  |
                                                                  v
                                                       thenApply / handle ...
~~~

Những điểm cần hiểu:

- `sendAsync` **trả về ngay với `CompletableFuture`**, không chủ động chờ toàn bộ response theo lối gọi đồng bộ.
- Một `CompletableFuture` có thể chưa hoàn thành, đã hoàn thành bình thường, bị hủy hoặc hoàn thành với exception. Do mạng có thể phản hồi rất nhanh, **không được giả định `future.isDone()` luôn là `false` ngay sau `sendAsync`**.
- `sendAsync` giúp caller không bị chặn khi **khởi tạo yêu cầu**. Nếu lập tức gọi `future.join()` hay `get()`, caller vẫn phải chờ ở bước đó.
- `CompletableFuture` không mặc định tạo “một thread riêng cho mỗi HTTP request”. Java HTTP Client thực hiện I/O theo implementation; callback `thenApply` hoặc `thenApplyAsync` cũng có quy tắc thực thi khác nhau.
- Future trả về có thể được chuyển đổi, kết hợp hoặc nối chuỗi để mô hình hóa các tác vụ HTTP phụ thuộc/độc lập.

**Nguyên tắc:** nếu muốn hưởng lợi từ concurrency, **khởi tạo các request độc lập trước**, phối hợp kết quả **sau**, không `join` từng request ngay sau khi gửi.

## 4. Tạo client, request và gửi GET bất đồng bộ

Cách dùng API thông dụng:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/items/42"))
        .timeout(Duration.ofSeconds(10))
        .header("Accept", "application/json")
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

CompletableFuture<String> bodyFuture = future.thenApply(response -> {
    if (response.statusCode() < 200
            || response.statusCode() >= 300) {
        throw new IllegalStateException(
                "Unexpected HTTP status: " + response.statusCode());
    }
    return response.body();
});
~~~

Đây là **đoạn minh họa trong một method** đã import `HttpClient`, `HttpRequest`, `HttpResponse`, `URI`, `Duration`, `StandardCharsets`, `CompletableFuture`. `api.example.com` là địa chỉ mẫu, **không đảm bảo có endpoint thực**, và không có stdout cố định.

Vì sao tách hai Future?

- `future` đại diện cho **HTTP response**, kể cả status `404` hoặc `500` nếu giao tiếp thành công.
- `bodyFuture` biến đổi response thành **body text** sau khi xác thực status **theo quy tắc ứng dụng**. Nếu status không chấp nhận, `thenApply` ném lỗi khiến `bodyFuture` hoàn thành thất bại.
- `thenApply` không chạy trước khi `future` hoàn thành bình thường, nhưng có thể chạy trong thread hoàn tất Future hoặc thread khác tham gia hoàn thành. Đừng gán cố định nó chạy trên UI thread, main thread hay một thread cụ thể.
- `CompletableFuture<HttpResponse<String>>` khác `CompletableFuture<String>`. Việc `thenApply(HttpResponse::body)` biến đổi kiểu dữ liệu là đúng, nhưng nếu không kiểm status, bạn có thể vô tình coi body của `404` là thành công.

### POST cũng trả về cùng dạng Future

~~~java
String json = "{\"name\":\"An\"}";

HttpRequest post = HttpRequest.newBuilder(
        URI.create("https://api.example.com/items"))
        .timeout(Duration.ofSeconds(10))
        .header("Content-Type", "application/json; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();

CompletableFuture<HttpResponse<String>> created = client.sendAsync(
        post, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
~~~

Đây là **đoạn minh họa**, không kết nối đến dịch vụ thật. `BodyPublishers.ofString` chỉ chuyển chuỗi thành byte để gửi; nó **không tự đặt `Content-Type: application/json`**. Nếu lỗi mạng hoặc timeout xảy ra sau khi POST đã bắt đầu, **không kết luận server chưa xử lý**. Retry phải theo chính sách idempotency của API.

## 5. Chương trình Java 11+ hoàn chỉnh: kết hợp hai Future và xử lý lỗi

Ví dụ chạy một server HTTP cục bộ trên `127.0.0.1`; server trả ba phản hồi:

- `GET /alpha` → status 200, body `alpha`.
- `GET /beta` → status 200, body `beta`.
- Đường dẫn khác → status 404, body `missing`.

Client gửi `/alpha` và `/beta` **bất đồng bộ**, sau đó dùng `thenCombine` để tổng hợp hai kết quả. Một request `/missing` trình diễn cách chuyển status thành exception nghiệp vụ và khôi phục bằng `exceptionally`. Đồng thời minh họa kiểu `T` khác nhau của hai `BodyHandlers`.

Tạo tệp **`AsyncSendDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class AsyncSendDemo {
    static HttpRequest get(String base, String path) {
        return HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/", exchange -> {
            try {
                String path = exchange.getRequestURI().getPath();
                int code = ("/alpha".equals(path)
                        || "/beta".equals(path)) ? 200 : 404;

                String message = "/alpha".equals(path)
                        ? "alpha"
                        : "/beta".equals(path) ? "beta" : "missing";

                byte[] body = message.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=UTF-8");
                exchange.sendResponseHeaders(code, body.length);

                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            // Bắt đầu hai request độc lập trước khi chờ kết quả.
            CompletableFuture<HttpResponse<String>> a =
                    client.sendAsync(
                            get(base, "/alpha"),
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));

            CompletableFuture<HttpResponse<String>> b =
                    client.sendAsync(
                            get(base, "/beta"),
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));

            // Kết hợp response sau khi cả a và b hoàn thành.
            CompletableFuture<String> combined =
                    a.thenCombine(b, (ra, rb) ->
                            ra.statusCode() + ":" + ra.body()
                            + "|" + rb.statusCode() + ":" + rb.body());

            System.out.println("combined=" + combined.join());

            // Status 404 vẫn tạo HTTP response; ứng dụng tự phân loại.
            CompletableFuture<String> recovered =
                    client.sendAsync(
                            get(base, "/missing"),
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8))
                    .thenApply(response -> {
                        if (response.statusCode() != 200) {
                            throw new IllegalStateException(
                                    "HTTP " + response.statusCode());
                        }
                        return response.body();
                    })
                    .exceptionally(error -> "fallback-used");

            System.out.println("missing=" + recovered.join());

            // T ở đây là byte[].
            CompletableFuture<HttpResponse<byte[]>> bytes =
                    client.sendAsync(
                            get(base, "/alpha"),
                            HttpResponse.BodyHandlers.ofByteArray());

            System.out.println(
                    "byteLength=" + bytes.join().body().length);

            // T ở đây là Void, không giữ response body.
            CompletableFuture<HttpResponse<Void>> ignored =
                    client.sendAsync(
                            get(base, "/alpha"),
                            HttpResponse.BodyHandlers.discarding());

            System.out.println(
                    "discard.bodyIsNull="
                            + (ignored.join().body() == null));
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch và chạy trên JDK 11 trở lên có module `jdk.httpserver`:

~~~bash
javac --add-modules jdk.httpserver AsyncSendDemo.java
java --add-modules jdk.httpserver AsyncSendDemo
~~~

Khi dùng JDK mới hơn và muốn compiler kiểm API/cú pháp Java 11, có thể thử `javac --release 11 --add-modules jdk.httpserver AsyncSendDemo.java` **chỉ nếu tổ hợp `--release`/module được compiler chấp nhận**; nếu không, dùng bộ JDK 11 thực hoặc cấu hình module thích hợp theo phiên bản đang dùng. Không cần đổi code ví dụ sang tính năng Java mới.

**Stdout của ví dụ (đã kiểm thử trên JDK với server cục bộ):**

~~~text
combined=200:alpha|200:beta
missing=fallback-used
byteLength=5
discard.bodyIsNull=true
~~~

### Diễn giải chính xác

1. `sendAsync` của `/alpha` và `/beta` được gọi **trước khi chương trình dùng `join`**. Hai yêu cầu có thể tiến triển đồng thời, dù lịch thực hiện chính xác của hệ điều hành/server không được bảo đảm.
2. `thenCombine` tạo một Future kiểu `String`: khi cả hai response hoàn thành bình thường, nó ghép `200:alpha|200:beta` theo vị trí đối số `ra`/`rb`, **không phụ thuộc request nào về trước**.
3. Với `/missing`, `sendAsync` nhận response **404** bình thường. Chính lambda `thenApply` kiểm `statusCode()` và ném `IllegalStateException`. Stage mới thất bại; `exceptionally` biến thất bại thành chuỗi `fallback-used`. Đây là *fallback do ứng dụng định nghĩa*, không phải HTTP Client tự đổi 404 thành exception.
4. `BodyHandlers.ofByteArray()` trả body `alpha` gồm **5 byte ASCII**, cho `byteLength=5`.
5. `BodyHandlers.discarding()` tiêu thụ rồi bỏ body, nên `HttpResponse<Void>.body()` là `null`. Nó **không** có nghĩa GET không truyền byte; server vẫn có thể gửi body.
6. `server.stop(0)` ở `finally` giúp dọn server thử nghiệm. `com.sun.net.httpserver.HttpServer` thuộc module `jdk.httpserver` chỉ để kiểm thử; phần `HttpClient` của bài thuộc module `java.net.http`.
7. Mỗi Future được join **sau** khi đã khởi tạo tác vụ liên quan. Việc dùng `join` ở `main` chỉ để một chương trình CLI in kết quả theo thứ tự và kết thúc; một ứng dụng server/UI thường cần giữ pipeline bất đồng bộ thay vì blocking ở thread nhận request.

**Lưu ý:** `exceptionally(error -> "fallback-used")` ở demo nhằm cho kết quả minh họa ổn định. Trong production, **không** dùng fallback cho mọi exception một cách mù quáng: cần phân biệt status nghiệp vụ, lỗi TLS/DNS/timeout, và log được thông tin phù hợp mà không rò bí mật.

## 6. Biến đổi và phối hợp Future: chọn đúng operator

`CompletableFuture` là công cụ mạnh vì một request bất đồng bộ có thể là đầu vào cho nhiều bước khác. Đây là các operator ổn định có trong Java 11.

| Phương thức | Ý nghĩa | Kiểu kết quả điển hình | Khi dùng |
| --- | --- | --- | --- |
| `thenApply(fn)` | Biến đổi **kết quả thành công** hiện có | `CompletableFuture<R>` | Response → status, body, DTO |
| `thenAccept(action)` | Xử lý kết quả, không sinh giá trị mới | `CompletableFuture<Void>` | Gửi metric/sự kiện nhẹ sau thành công |
| `thenRun(action)` | Chạy hành động khi stage thành công, không nhận giá trị | `CompletableFuture<Void>` | Trigger bước tiếp không cần response |
| `thenCompose(fn)` | Hàm trả Future khác; **làm phẳng** hai Future | `CompletableFuture<R>` | Request B cần dữ liệu từ response A |
| `thenCombine(other, fn)` | Kết hợp **hai** stage độc lập khi cùng xong | `CompletableFuture<R>` | Ghép hai response |
| `CompletableFuture.allOf(...)` | Hoàn thành khi **mọi** Future trong tập đã hoàn thành | `CompletableFuture<Void>` | Chờ nhiều request và đọc kết quả riêng |
| `CompletableFuture.anyOf(...)` | Hoàn thành theo Future đầu tiên hoàn thành, bình thường hoặc lỗi | `CompletableFuture<Object>` | Race nhiều kết quả nếu thiết kế có ý nghĩa |
| `exceptionally(fn)` | Khôi phục khi stage trước thất bại | `CompletableFuture<T>` | Giá trị fallback có kiểm soát |
| `handle(fn)` | Nhận **cả kết quả lẫn lỗi** và tạo kết quả mới | `CompletableFuture<R>` | Quy đổi thành dạng Success/Error |
| `whenComplete(action)` | Quan sát kết quả/lỗi nhưng thường **không thay** chúng | `CompletableFuture<T>` | Logging, metrics, cleanup |
| `thenApplyAsync(fn, executor)` | Thực hiện biến đổi trên executor phù hợp | `CompletableFuture<R>` | Parse/tính toán đáng kể cần tách thread |

### 6.1. thenApply: biến response thành dữ liệu nghiệp vụ

~~~java
CompletableFuture<Integer> statusFuture =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.discarding())
        .thenApply(HttpResponse::statusCode);
~~~

Ví dụ minh họa. Kiểu sau `thenApply` là `CompletableFuture<Integer>` chứ không còn `CompletableFuture<HttpResponse<Void>>`. Nếu HTTP Client nhận 404, kết quả integer vẫn là **404** vì lambda không coi đó là exception.

Muốn chỉ chấp nhận 2xx:

~~~java
CompletableFuture<String> bodyFuture =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8))
        .thenApply(response -> {
            int status = response.statusCode();
            if (status < 200 || status >= 300) {
                throw new IllegalStateException(
                        "HTTP status=" + status);
            }
            return response.body();
        });
~~~

Đây là **logic ứng dụng**, không phải hành vi tự động của `sendAsync`.

### 6.2. thenCompose: request sau phụ thuộc request trước

Giả sử request thứ nhất lấy ID, request thứ hai cần ID đó. Phác thảo một method (cần định nghĩa `lookupRequest`, `detailsUriFor`, `client` và kiểm dữ liệu trả về):

~~~java
CompletableFuture<HttpResponse<String>> first =
        client.sendAsync(
                lookupRequest,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

CompletableFuture<HttpResponse<String>> details =
        first.thenCompose(response -> {
            if (response.statusCode() != 200) {
                return CompletableFuture.failedFuture(
                        new IllegalStateException("Lookup failed"));
            }

            String id = response.body();
            URI detailsUri = detailsUriFor(id);

            HttpRequest next = HttpRequest.newBuilder(detailsUri)
                    .GET()
                    .build();

            return client.sendAsync(
                    next,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
        });
~~~

**Đoạn minh họa, không phải chương trình độc lập.** `CompletableFuture.failedFuture(...)` có từ Java 9 nên dùng được với Java 11.

Tại sao cần `thenCompose`?

- Lambda tạo ra **một Future khác** (request HTTP thứ hai).
- `thenCompose` làm phẳng `CompletableFuture<CompletableFuture<HttpResponse<String>>>` thành `CompletableFuture<HttpResponse<String>>`.
- Request thứ hai **chỉ được khởi tạo sau** khi response đầu tiên đã sẵn sàng và qua kiểm status.
- Không dùng `thenApply` rồi `join` Future trong callback: đó là cách dễ vô tình chặn thread và phá mô hình bất đồng bộ.

### 6.3. thenCombine: hai request độc lập

~~~java
CompletableFuture<String> names =
        firstResponse.thenCombine(secondResponse,
                (a, b) -> a.body() + ", " + b.body());
~~~

Giả định `firstResponse` và `secondResponse` đều có kiểu `CompletableFuture<HttpResponse<String>>` và đã được gửi. `thenCombine` chờ cả hai xong bình thường. Nếu một cái thất bại, pipeline kết hợp thường hoàn thành thất bại thay vì gọi hàm ghép.

Nếu muốn thu thập **thành công một phần**, hãy xử lý lỗi/fallback ở từng nhánh **trước khi** kết hợp, thay vì dựa vào `thenCombine` tự quyết định một nhánh “đủ tốt”.

### 6.4. allOf: nhiều request, dữ liệu kết quả vẫn nằm trong từng Future

~~~java
CompletableFuture<HttpResponse<String>> a =
        client.sendAsync(requestA,
                HttpResponse.BodyHandlers.ofString());
CompletableFuture<HttpResponse<String>> b =
        client.sendAsync(requestB,
                HttpResponse.BodyHandlers.ofString());

CompletableFuture<Void> done = CompletableFuture.allOf(a, b);

CompletableFuture<String> summary = done.thenApply(unused ->
        a.join().statusCode() + "/" + b.join().statusCode());
~~~

**Đoạn minh họa** với `client`, `requestA` và `requestB` đã tồn tại.

- `allOf` **không tạo danh sách các `HttpResponse`**; nó cho `CompletableFuture<Void>` báo hoàn tất của tập.
- Khi `done` hoàn thành bình thường, `a` và `b` đều hoàn thành bình thường; trong callback này, `join()` của các Future con không cần chờ thêm.
- Nếu bất kỳ Future con nào hoàn thành lỗi, `allOf` hoàn thành bất thường; `thenApply` của `summary` không được gọi như nhánh thành công.
- Không in hoặc cập nhật UI dựa vào thứ tự hoàn thành nếu nghiệp vụ cần thứ tự của request. Gắn ID hoặc giữ mapping từ URL/request đến response.

### 6.5. async vs non-async continuation

`thenApply(fn)` có thể thực thi `fn` trong thread hoàn tất Future hoặc thread khác tham gia hoàn thành. `thenApplyAsync(fn)` xếp tác vụ cho executor mặc định của `CompletableFuture` (thường `ForkJoinPool.commonPool()`), còn overload có `executor` cho phép bạn chọn pool.

~~~java
CompletableFuture<Result> parsed =
        responseFuture.thenApplyAsync(
                response -> parseAndValidate(response.body()),
                parsingExecutor);
~~~

**Đây là đoạn minh họa**, phải có lớp `Result`, `responseFuture` và `parsingExecutor` phù hợp.

Chỉ dùng async continuation khi có lý do; nó cũng tốn scheduling/threads. **Không** thực hiện thao tác chặn dài (disk, database, network, parse nặng) bừa bãi ngay trong callback khi không hiểu executor của ứng dụng. Nếu cần, dùng một `Executor` có giới hạn thread/queue và đóng/shutdown theo vòng đời ứng dụng.

## 7. Xử lý HTTP status khác xử lý lỗi Future

Một phân biệt quan trọng:

**HTTP 404 không tự làm CompletableFuture thất bại.** Nếu client hoàn tất giao tiếp, Future có thể **hoàn thành bình thường với `HttpResponse` status=404**. Lỗi HTTP status là nội dung cần ứng dụng phân loại.

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString());

future.thenAccept(response -> {
    int status = response.statusCode();
    if (status >= 200 && status < 300) {
        consumeSuccess(response.body());
    } else {
        consumeHttpError(status, response.body());
    }
});
~~~

**Đoạn minh họa**, `consumeSuccess` và `consumeHttpError` là các method giả định. `thenAccept` chỉ chạy khi Future hoàn thành bình thường; nó vẫn nhận **response 4xx/5xx** vì đó không phải mặc nhiên lỗi I/O.

Ngược lại, Future có thể **hoàn thành thất bại** vì DNS, TCP, TLS, timeout, body decoding, I/O hoặc exception ném từ callback. Cần xử lý bằng các operator dành cho lỗi.

### 7.1. exceptionally: cung cấp fallback khi lỗi

~~~java
CompletableFuture<String> readable =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8))
        .thenApply(response -> {
            if (response.statusCode() != 200) {
                throw new IllegalStateException("Bad status");
            }
            return response.body();
        })
        .exceptionally(error -> "unavailable");
~~~

Nếu request hoặc `thenApply` thất bại, `exceptionally` trả chuỗi `unavailable` và Future mới hoàn thành bình thường. Nhưng **mọi loại lỗi** (gồm timeout, lỗi xác thực, lỗi callback) cũng bị che thành giá trị đó. Trong ứng dụng thật, chỉ fallback khi chính sách cho phép; có thể phân loại nguyên nhân trước khi chọn fallback.

### 7.2. handle: xử lý cả success và failure

~~~java
CompletableFuture<String> result =
        responseFuture.handle((response, error) -> {
            if (error != null) {
                return "network-error";
            }
            return "http-status=" + response.statusCode();
        });
~~~

Giả định `responseFuture` kiểu `CompletableFuture<HttpResponse<String>>`. Khi đã có lỗi, `response` thường là `null`; không được gọi `response.statusCode()` trước khi kiểm `error`. Nếu callback `handle` ném lỗi mới, stage kết quả cũng có thể thất bại.

### 7.3. whenComplete: quan sát, không phải khôi phục

~~~java
CompletableFuture<HttpResponse<String>> observed =
        responseFuture.whenComplete((response, error) -> {
            if (error != null) {
                System.err.println("Request failed");
            }
        });
~~~

`whenComplete` thường giữ kết quả hoặc lỗi của stage gốc; nó có ích cho logging/metrics/cleanup chứ **không thay thế** `exceptionally`/`handle` để cung cấp fallback. Nếu callback `whenComplete` tự ném exception, cần hiểu quy tắc lan truyền lỗi của `CompletableFuture`.

**Không chỉ gọi `future.thenAccept(...)` rồi bỏ tham chiếu khi lỗi có ý nghĩa:** nếu Future hoàn thành lỗi, callback thành công không chạy và bạn có thể bỏ sót sự cố. Ít nhất cần một nhánh error/handler hoặc trả Future cho tầng gọi để quan sát.

## 8. join, get và lỗi được bọc như thế nào?

Khi cần lấy kết quả tại ranh giới của ứng dụng (CLI, test, framework adapter), có thể chờ:

~~~java
HttpResponse<String> response = future.join();
~~~

- `join()` **chặn nếu Future chưa hoàn thành** và trả kết quả khi thành công.
- Với Future thất bại, thường ném **`CompletionException`** (unchecked) chứa nguyên nhân gốc tại `getCause()`. Cancellation có thể biểu hiện bằng `CancellationException`.
- Không cần khai báo `throws ExecutionException` hoặc `InterruptedException` cho `join()`, nhưng điều đó **không** có nghĩa chờ là không thể bị gián đoạn ở mức quản lý tác vụ hay không có lỗi.

Nếu muốn dùng API `Future.get()`:

~~~java
try {
    HttpResponse<String> response = future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Thoát hoặc truyền lỗi theo hợp đồng tầng gọi.
} catch (java.util.concurrent.ExecutionException ex) {
    Throwable original = ex.getCause();
    // Phân loại original và xử lý.
}
~~~

**Đoạn minh họa**, `future` đã được khai báo. `get()` khai báo checked exceptions, và `get(timeout, unit)` còn có thể ném `TimeoutException` khi **chờ quá lâu**.

Bảng nhanh:

| API chờ | Lỗi hoàn thành bất thường | Ngắt trong lúc chờ | Có giới hạn thời gian chờ? |
| --- | --- | --- | --- |
| `join()` | `CompletionException` thường bao nguyên nhân; có thể `CancellationException` | Không khai báo `InterruptedException` | Không có timeout trên `join` |
| `get()` | `ExecutionException` chứa nguyên nhân; có thể `CancellationException` | `InterruptedException` (checked) | Không, nếu không dùng overload |
| `get(long, TimeUnit)` | `ExecutionException` / `CancellationException` | `InterruptedException` | Có; ném `TimeoutException` cho việc chờ |

**Lưu ý:** `future.get(2, SECONDS)` ném `TimeoutException` **không chứng minh HTTP request đã bị hủy**. Nó chỉ nói thread đã chờ quá khoảng thời gian đó. Cần có chính sách hủy, timeout request và cleanup riêng nếu tác vụ vẫn chạy.

### Xem nguyên nhân gốc khi CompletionException bọc IOException

Ví dụ helper sử dụng trong `exceptionally`:

~~~java
static Throwable unwrapCompletion(Throwable error) {
    Throwable current = error;
    while (current instanceof java.util.concurrent.CompletionException
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
~~~

**Method minh họa**; `error` có thể bắt nguồn từ lỗi mạng, TLS, timeout, callback hoặc hủy. Không dựa vào thông điệp văn bản của exception để phân loại ổn định: dùng kiểu exception, mã HTTP (nếu có response) và ngữ cảnh nghiệp vụ.

Không nên dùng `join()` liên tiếp như sau khi muốn gửi song song:

~~~java
// Dễ vô tình biến công việc thành tuần tự:
HttpResponse<String> a = client.sendAsync(reqA, handler).join();
HttpResponse<String> b = client.sendAsync(reqB, handler).join();
~~~

Cách hợp lý hơn: tạo hai Future trước, sau đó `thenCombine` hoặc `allOf`.

## 9. Timeout: ba cơ chế khác nhau

HTTP bất đồng bộ vẫn cần timeout để tránh tác vụ tồn tại mãi. Có **ba tầng** thường gặp, không thay thế lẫn nhau:

| Cấu hình | Đặt tại | Ý nghĩa |
| --- | --- | --- |
| `HttpClient.Builder.connectTimeout(duration)` | Client | Thời gian tối đa để thiết lập kết nối mới. Kết nối tái sử dụng có thể không bị ảnh hưởng bởi ngưỡng này |
| `HttpRequest.Builder.timeout(duration)` | Request | Giới hạn thời gian nhận phản hồi của request theo hợp đồng Java HTTP Client |
| `CompletableFuture.orTimeout(n, unit)` | Future | Nếu Future chưa hoàn thành, cho Future hoàn thành **thất bại với `TimeoutException`** tại deadline của Future |

Ví dụ:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

CompletableFuture<HttpResponse<String>> bounded =
        future.orTimeout(12, TimeUnit.SECONDS);
~~~

Đây là **đoạn minh họa**, cần khai báo `uri` và import `TimeUnit`.

Quan trọng:

- `orTimeout` có từ **Java 9**, nên dùng được trong Java 11. Nó trả **chính Future đó** sau khi đăng ký quy tắc timeout; không tự tạo request mới.
- Deadline của `orTimeout` hoàn thành Future với `TimeoutException`; **không phải cam kết rằng HTTP exchange bị hủy ngay, server chưa xử lý hoặc socket được đóng tức thì**.
- Timeout của `HttpRequest` là một phần chính sách HTTP Client; trên handler streaming, việc đọc body tiếp theo và xử lý parser cũng có thể cần deadline/giới hạn độc lập.
- Không đặt `orTimeout` trên Future được chia sẻ bởi nhiều consumer nếu không mong muốn deadline này làm thay đổi trạng thái của chính Future dùng chung.
- `HttpClient.connectTimeout` không phải thay thế cho request timeout và không bảo vệ tất cả chặng xử lý sau khi kết nối đã được thiết lập.
- Hai API timeout có thể biểu hiện bằng loại exception khác nhau: timeout HTTP thường là `HttpTimeoutException` (lớp con `IOException`), còn `CompletableFuture.orTimeout` dùng `TimeoutException`.

### completeOnTimeout có phù hợp để tạo fallback?

Java 11 có `completeOnTimeout(value, duration, unit)`: nó **hoàn thành Future bình thường với một giá trị được cho sẵn** nếu hết hạn. Nhưng đừng bịa một `HttpResponse` “giả” chỉ để né lỗi:

~~~java
CompletableFuture<String> bodyFuture =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString())
        .thenApply(HttpResponse::body)
        .completeOnTimeout(
                "cached-or-default", 5, TimeUnit.SECONDS);
~~~

**Đoạn minh họa**: chỉ dùng default khi nghiệp vụ thực sự cho phép. Nó không có nghĩa server đã hoàn thành, và không bảo đảm dừng việc gửi/nhận của yêu cầu HTTP đang diễn ra. Với giao dịch tiền, đặt hàng hoặc tác vụ có side effect, không nên im lặng biến timeout thành một kết quả “thành công”.

## 10. Cancellation: biết giới hạn của lời gọi cancel

`CompletableFuture` có `cancel(boolean mayInterruptIfRunning)`, nhưng **cancellation của Future không tương đương việc rollback server**.

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString());

boolean accepted = future.cancel(true);
~~~

**Đoạn minh họa**, không kết luận kết quả của `accepted` vì phụ thuộc trạng thái Future tại thời điểm hủy.

- `cancel(true)` cố chuyển Future sang trạng thái bị hủy nếu Future chưa hoàn thành; việc hủy phụ thuộc implementation/client.
- Với implementation HTTP Client hiện đại của JDK, việc hủy Future do `sendAsync` trả về có thể **cố gắng hủy HTTP exchange** và giải phóng tài nguyên. Nhưng **không có bảo đảm hủy xảy ra tức thì**.
- Server có thể **đã nhận và bắt đầu xử lý request** trước khi client hủy; đặc biệt không tự retry request thay đổi dữ liệu chỉ vì cancellation.
- `cancel(true)` không phải cách ổn định để “interrupt chính xác thread đã chạy HTTP” theo nghĩa của một `Thread.interrupt` trực tiếp.
- Hủy một Future dẫn xuất (ví dụ sau `thenApply`) có thể không mang ý nghĩa “hủy mọi request upstream” theo mong muốn. Giữ rõ tham chiếu đến future gốc, quản lý lifecycle/cancel theo thiết kế.
- Trên các JDK mới, chi tiết cancel của implementation được ghi rõ hơn so với một số tài liệu Java 11; để viết ứng dụng chạy nhiều JDK, **chỉ dựa vào bảo đảm được API/phần triển khai mục tiêu tài liệu hóa** và kiểm thử trong môi trường thực tế.

**Mẫu tư duy an toàn:** timeout + cancel tốt nhất có thể + dọn tài nguyên + idempotency + giám sát, không được coi cancel là giao dịch hoàn tác phía server.

## 11. HTTP status, body và resource lifecycle trong pipeline

Cần xử lý **ba lớp lỗi** tách biệt:

1. **Lỗi request trước khi gửi:** URI sai, header sai, request không thể build. Một số tình huống ném exception **ngay khi gọi builder hoặc `sendAsync`** (ví dụ request không hợp lệ), không đợi Future.
2. **HTTP response không thành công:** status `400`/`404`/`429`/`500` vẫn có thể hoàn thành Future **bình thường**, vì server đã gửi HTTP response. Ứng dụng kiểm status và body/error schema.
3. **Lỗi giao tiếp hoặc xử lý:** DNS/TCP/TLS/timeout/body subscriber/callback; Future có thể hoàn thành **thất bại**, và các stage phụ thuộc có thể không chạy nhánh thành công.

Ví dụ không đúng:

~~~java
client.sendAsync(request,
        HttpResponse.BodyHandlers.ofString())
        .thenApply(HttpResponse::body)  // Có thể là body lỗi HTTP 404!
        .thenAccept(this::saveRecord);
~~~

Đây là **minh họa logic lỗi**, không phải chương trình chạy độc lập; `saveRecord` là method ứng dụng giả định. Sửa bằng kiểm status trước khi xử lý:

~~~java
client.sendAsync(request,
        HttpResponse.BodyHandlers.ofString())
        .thenApply(response -> {
            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "HTTP " + response.statusCode());
            }
            return response.body();
        })
        .thenAccept(this::saveRecord);
~~~

**Mã minh họa**. Ở sản phẩm thực tế nên trả lại Future cuối cho tầng gọi hoặc gắn error handling; đừng bỏ qua lỗi của `thenAccept`.

### BodyHandler và bộ nhớ

- `ofString()` và `ofByteArray()` tích lũy body trong bộ nhớ. Nếu nguồn không đáng tin gửi response rất lớn, Future có thể tiêu thụ nhiều heap **trước khi hoàn thành**.
- `discarding()` bỏ body nhưng client vẫn có thể nhận toàn bộ dữ liệu từ server: tiết kiệm việc giữ body, **không chắc tiết kiệm băng thông**.
- `ofInputStream()` có thể hoàn thành Future khi mới có status/headers; bạn phải **đọc/đóng stream**. Không bỏ stream treo rồi coi request đã được giải phóng.
- `ofFile(path)` phù hợp lưu body lớn ra tệp, nhưng cần kiểm dung lượng đĩa, status, định dạng, cleanup và giới hạn byte.
- Kiểm `Content-Length` từ headers có thể giúp từ chối sớm; đây **không thay thế** giới hạn byte thực nhận hay giới hạn parser.
- Nếu parser JSON/XML/ZIP có thể tạo nhiều đối tượng hoặc giải nén quá mức, cần đặt cap sau bước giải nén/parse phù hợp, không chỉ giới hạn body nén ban đầu.

### Khi muốn giới hạn kích thước response

Nếu cần body nhưng server không đáng tin, **không** dùng `ofByteArray` rồi `response.body().length` để tự bảo vệ: lúc đó mảng đã được cấp phát. Dùng streaming với bộ đếm byte, áp giới hạn ngay khi đọc, và đóng stream khi quá hạn:

~~~java
CompletableFuture<HttpResponse<java.io.InputStream>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

CompletableFuture<Long> counted =
        future.thenApplyAsync(response -> {
            try (java.io.InputStream body = response.body()) {
                byte[] buffer = new byte[8192];
                long total = 0;
                long max = 1024L * 1024L; // Ví dụ 1 MiB, cap tin cậy.

                while (true) {
                    long remaining = max - total;
                    int wanted = (int) Math.min(
                            buffer.length, remaining > 0 ? remaining : 1L);
                    int n = body.read(buffer, 0, wanted);
                    if (n == -1) return total;
                    if (n == 0) throw new java.io.IOException(
                            "No stream progress");
                    if (n > remaining) throw new java.io.IOException(
                            "Body limit exceeded");
                    total += n;
                }
            } catch (java.io.IOException ex) {
                throw new java.io.UncheckedIOException(ex);
            }
        }, boundedIoExecutor);
~~~

Đây là **đoạn minh họa** yêu cầu `boundedIoExecutor`, `client` và `request` đã được định nghĩa; chưa phải chương trình độc lập. Nó dùng buffer cố định và thử 1 byte khi đạt cap để phát hiện vượt giới hạn mà không tích lũy nội dung. **Đừng đặt I/O đọc body chặn dài lên common pool một cách không kiểm soát**: cần executor có giới hạn/concurrency phù hợp. `java.io.UncheckedIOException` giúp ngoại lệ checked đi qua callback lambda; tầng xử lý lỗi phải unwrap và phân loại.

## 12. Giới hạn concurrency, executor và backpressure

Gửi HTTP bất đồng bộ giúp quản lý nhiều request mà không cần một thread chặn cho mỗi lời gọi, nhưng **không có nghĩa số request có thể vô hạn**.

Ví dụ một server nhận 10.000 request cùng lúc có thể gây áp lực lên: connection pool, sockets, heap, buffer, response processing, threads của executor, queue, TLS và dịch vụ downstream.

**Giới hạn song song** có thể đặt ở tầng ứng dụng:

- Dùng một `Semaphore` hoặc bounded queue để giới hạn số yêu cầu đang hoạt động.
- Không khởi tạo hàng chục nghìn Future rồi mới cố giới hạn `allOf`; khi đó request đã được gửi.
- Trả permit khi Future kết thúc bằng `whenComplete` hoặc cơ chế cleanup tương đương, kể cả thất bại.
- Không block bằng `semaphore.acquire()` trong event-loop/UI thread; cân nhắc hàng đợi bất đồng bộ hoặc bộ điều phối phù hợp.
- Đặt timeout request; dùng circuit breaker/rate limiting khi gọi hệ thống ngoài có thể quá tải.
- Không tạo `HttpClient` mới cho mỗi request nếu có thể tái sử dụng cấu hình và connection pool.

### thenApplyAsync không tự giúp mọi thứ an toàn

`thenApplyAsync` chỉ đưa continuation lên executor. Nếu chính continuation dùng `readAllBytes`, parse JSON vô hạn hoặc ghi file lớn, nó vẫn có thể bùng bộ nhớ/IO. Hãy giới hạn đầu vào và concurrency theo từng tài nguyên.

### Dùng executor riêng cho callback nặng

~~~java
ExecutorService parsingExecutor =
        Executors.newFixedThreadPool(4);

try {
    CompletableFuture<Result> parsed =
            responseFuture.thenApplyAsync(
                    response -> parse(response.body()),
                    parsingExecutor);

    // Trả 'parsed' cho tầng điều phối hoặc chờ ở ranh giới phù hợp.
} finally {
    parsingExecutor.shutdown();
}
~~~

**Đoạn minh họa**, cần import `Executors`/`ExecutorService` và định nghĩa `Result`, `parse`, `responseFuture`; không phải chương trình độc lập. Trong chương trình thực tế, **không shutdown executor trước khi các task cần dùng nó hoàn tất**; cấu trúc `finally` chỉ minh họa trách nhiệm quản lý vòng đời. Tầng điều phối phải bảo đảm Future liên quan đã xử lý hoặc hủy đúng cách trước khi đóng executor.

## 13. Kiểm thử pipeline bất đồng bộ

Một test tốt cho `sendAsync` không chỉ assert rằng Future khác `null`. Hãy kiểm hành vi có nghĩa:

| Tình huống | Kỳ vọng |
| --- | --- |
| Server trả 200 với text nhỏ | Future hoàn thành bình thường, `statusCode() == 200`, body khớp |
| Server trả 404 | Future vẫn hoàn thành bình thường nếu I/O thành công, `statusCode() == 404` |
| `thenApply` có kiểm status và gặp 404 | Stage sau hoàn thành thất bại với lỗi ứng dụng |
| `exceptionally` được gắn sau stage lỗi | Nhận fallback đúng quy tắc |
| Hai request độc lập `thenCombine` | Kết quả ghép theo thứ tự lambda, không phụ thuộc request về trước |
| `thenCompose` của hai request phụ thuộc nhau | Request sau chỉ được gửi sau khi response trước hợp lệ |
| `allOf` trên nhiều request | Hoàn thành khi mọi Future con kết thúc; kết quả phải đọc từ Future con |
| HTTP timeout | Future lỗi với nguyên nhân phù hợp; kiểm chính sách cleanup |
| Future timeout riêng (`orTimeout`) | Future được đánh dấu quá hạn; không suy ra server đã hủy |
| Response lớn | Có giới hạn byte khi streaming, không dùng `ofByteArray` vô hạn |
| Handler `ofInputStream` | Đóng stream trong mọi nhánh thành công/thất bại |
| Request tạo dữ liệu (POST) bị hủy | Không retry vô điều kiện; dùng idempotency/test hợp đồng API |

### Kiểm thử độc lập Internet

Ví dụ ở mục 5 dùng server loopback và port động, giúp kết quả không phụ thuộc DNS/TLS hay API công khai. Đừng dùng `Thread.sleep(...)` để “chờ request có lẽ đã xong” rồi assert: đó là test dễ flaky. Hãy chờ Future **tại ranh giới test** qua `get(timeout, unit)`, hoặc compose stage kết quả, với deadline hữu hạn.

Ví dụ trong test (giả định đã có `future`):

~~~java
HttpResponse<String> result =
        future.get(3, TimeUnit.SECONDS);

if (result.statusCode() != 200) {
    throw new AssertionError("Unexpected HTTP status");
}
~~~

Đây là **đoạn minh họa**, cần xử lý `InterruptedException`, `ExecutionException` và `TimeoutException` theo test framework. `get(timeout)` đặt giới hạn **thời gian chờ test**, không bắt buộc hủy HTTP exchange; khi timeout cần cleanup request/server đúng cách.

### Test exception đúng nguyên nhân

Nếu `join` ném `CompletionException`, test có thể kiểm `getCause()` thuộc loại mong đợi (ví dụ `HttpTimeoutException` hoặc `IOException` trong điều kiện đã kiểm soát). Không assert nguyên văn exception message của JDK hoặc phụ thuộc thứ tự callback in ra console. Với lỗi nghiệp vụ tự ném, test nên kiểm rõ type/mã HTTP và đường fallback.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Gọi `sendAsync(...).join()` ngay trong từng vòng lặp | Vô tình tuần tự hóa request | Tạo nhiều Future trước, compose kết quả sau |
| Gán Future thành Response | Lỗi kiểu dữ liệu | `sendAsync` trả `CompletableFuture<HttpResponse<T>>`, không phải `HttpResponse<T>` |
| Cho rằng status 404 làm Future lỗi | Bỏ qua body lỗi HTTP | Kiểm `statusCode()` trong pipeline |
| Dùng `thenApply` thay `thenCompose` khi callback trả Future | Tạo Future lồng nhau khó dùng | Dùng `thenCompose` để làm phẳng |
| Cho rằng `allOf` trả danh sách response | Hiểu sai kiểu `Void` | Đọc kết quả từ Future con sau `allOf` |
| Dùng `whenComplete` để trả fallback | Lỗi vẫn lan truyền | `exceptionally` hoặc `handle` khi cần đổi kết quả |
| Dùng `exceptionally` catch hết và trả giá trị giả | Che lỗi bảo mật/I/O quan trọng | Phân loại nguyên nhân và giới hạn fallback |
| Giả định callback luôn trên thread gọi | Race condition hoặc chặn thread I/O | Tách dữ liệu, chọn executor hợp lý |
| Dùng `ofByteArray`/`ofString` cho body không giới hạn | Tăng RAM/OutOfMemoryError | Stream/file và cap thực tế |
| Nghĩ `orTimeout` chắc chắn đóng kết nối | Request có thể vẫn đang chạy | Kết hợp timeout HTTP, cancellation và cleanup |
| Nghĩ cancel rollback POST | Server có thể đã xử lý | Idempotency, xác nhận trạng thái |
| Nghĩ `get(timeout)` sẽ hủy request | Chỉ có giới hạn thời gian chờ | Hủy/cleanup riêng nếu cần |
| Gọi `response.body()` khi dùng `discarding` như String | Body `Void`, thường `null` | Dùng handler/kiểu đúng |
| Bỏ qua Future cuối của pipeline | Lỗi callback không được quan sát | Return Future hoặc gắn handler |
| Tạo client cho mỗi request | Khó tận dụng tái sử dụng kết nối | Dùng client vòng đời dài với chính sách phù hợp |
| Gửi URL user nhập không kiểm policy | Nguy cơ SSRF trong server-side | Kiểm host/scheme/port/redirect và network boundary |

## 15. Checklist áp dụng khi viết HTTP async Java 11+

- [ ] Sử dụng `java.net.http.HttpClient` ổn định, cấu hình client/request timeout phù hợp.
- [ ] Có URI và HTTP method đúng; xác thực URL nếu đầu vào không đáng tin.
- [ ] Chọn `BodyHandler<T>` theo kiểu response và ngân sách memory.
- [ ] Kiểu Future khai báo đúng `CompletableFuture<HttpResponse<T>>`.
- [ ] Request độc lập được khởi tạo trước khi chờ hoặc kết hợp; tránh `join` sớm.
- [ ] Có kiểm `statusCode()` trước khi coi body là dữ liệu thành công.
- [ ] Stage thất bại được quan sát/xử lý: `exceptionally`, `handle`, logging hoặc trả Future cho caller.
- [ ] Dùng `thenApply` cho biến đổi sync và `thenCompose` cho hàm trả Future.
- [ ] Không coi timeout của Future là cancellation chắc chắn; xử lý I/O/cancel rõ ràng.
- [ ] Kiểm cap của body lớn, số request đồng thời và vòng đời tài nguyên.
- [ ] Với POST thay đổi dữ liệu, có chính sách idempotency/retry an toàn.
- [ ] Có test 2xx, 4xx, lỗi mạng, timeout, composition và handler streaming.
- [ ] Mã tuân thủ phiên bản Java 11 yêu cầu; không vô tình dùng API chỉ mới có ở JDK mới hơn.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `HttpClient.sendAsync` trả `HttpResponse<String>` hay `CompletableFuture<HttpResponse<String>>` khi dùng `ofString`?

**Đáp án:** Nó trả **`CompletableFuture<HttpResponse<String>>`**. Khi Future hoàn thành bình thường, giá trị bên trong mới là response.

**Câu 2.** Nếu server trả `404`, Future có bắt buộc hoàn thành thất bại không?

**Không.** `404` là HTTP status; nếu gửi/nhận hợp lệ, Future hoàn thành bình thường với response `statusCode()==404`. Ứng dụng quyết định có coi đó là lỗi nghiệp vụ không.

**Câu 3.** Khác nhau giữa `thenApply` và `thenCompose`?

**Đáp án:** `thenApply` biến một giá trị thành một giá trị khác; nếu callback của bạn tạo **Future mới** thì dùng `thenCompose` để nối và làm phẳng pipeline.

**Câu 4.** Muốn gửi `A` và `B` độc lập rồi ghép nội dung, nên làm gì?

**Đáp án:** Tạo hai Future bằng `sendAsync` trước, dùng `thenCombine` hoặc `allOf` kết quả. Không `join` A rồi mới gửi B.

**Câu 5.** `future.orTimeout(5, SECONDS)` có cam kết server ngừng xử lý request khi hết hạn không?

**Không.** Nó đánh dấu Future thất bại theo timeout; không bảo đảm rollback hoặc dừng tác vụ HTTP/side effect ngay.

**Câu 6.** `CompletableFuture.allOf(a,b)` trả kiểu gì?

**Đáp án:** `CompletableFuture<Void>`. Muốn lấy giá trị a/b, truy cập Future con khi đã hoàn thành.

**Câu 7.** `sendAsync(..., ofInputStream())` hoàn thành, vậy có thể quên đóng stream?

**Không.** Future có thể hoàn thành khi body còn đang đến; caller chịu trách nhiệm tiêu thụ hoặc đóng `InputStream`.

**Câu 8.** Vì sao `get(2, SECONDS)` ném TimeoutException chưa chắc request đã bị hủy?

**Vì** overload đó chỉ đặt ngưỡng **thời gian chờ** của thread đang gọi; HTTP exchange có thể vẫn chạy.

## Tài liệu tham khảo chính thức

- [Java SE 11 — `HttpClient`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): hợp đồng `sendAsync`, kiểu `CompletableFuture<HttpResponse<T>>`, cấu hình client và ngoại lệ.
- [Java SE 11 — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): `uri`, `timeout`, `GET`, `POST` và request headers.
- [Java SE 11 — `HttpResponse`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): `statusCode`, `headers`, `body` và `BodyHandler<T>`.
- [Java SE 11 — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofString`, `ofByteArray`, `discarding`, `ofInputStream`, `ofFile`.
- [Java SE 11 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `thenApply`, `thenCompose`, `thenCombine`, `allOf`, `exceptionally`, `handle`, `orTimeout` và `get`/`join`.
- [Java SE 26 — `HttpClient`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): `sendAsync` vẫn được hỗ trợ, bổ sung/làm rõ vòng đời và cancellation của HTTP Client hiện đại.
- [JDK 11 — `HttpServer`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server loopback trong chương trình test.

**Ghi nhớ:** `sendAsync(request, handler)` tạo **Future chứa HttpResponse**, không phải response ngay lập tức. Kết hợp bằng `thenApply`/`thenCompose`/`thenCombine`, xử lý **status HTTP và lỗi Future riêng biệt**, và chỉ block tại ranh giới cần kết quả. Timeout/cancel giúp quản lý tác vụ nhưng không thay thế idempotency hay giới hạn tài nguyên. Đây là các nguyên tắc vẫn đúng từ Java 11 đến các JDK hiện đại.
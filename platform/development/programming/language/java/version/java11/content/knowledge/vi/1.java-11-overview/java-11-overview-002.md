# Java 11 — HTTP, xử lý dữ liệu và khả năng quan sát ứng dụng

**Bối cảnh:** Chủ đề Java 11, nhóm Định hướng. Bài này xây dựng cách tư duy và cách triển khai một luồng thực tế: gọi dịch vụ HTTP → kiểm tra response → giải mã, xác thực và biến đổi dữ liệu → ghi nhận tín hiệu để phát hiện, điều tra lỗi và tối ưu. API mẫu tương thích **JDK 11**; các thực hành về bảo mật và observability được chọn vì vẫn được áp dụng trong hệ thống hiện nay. Java SE không tích hợp sẵn JSON object mapper hoặc SDK tracing phân tán; những phần đó cần dependency được duy trì và tương thích với runtime.

## 1. Từ yêu cầu nghiệp vụ đến luồng HTTP có thể vận hành

Một lời gọi dịch vụ cần đi qua các bước:

1. Xác định **endpoint, HTTP method, headers, body, cơ chế xác thực và deadline**.
2. Gửi yêu cầu qua `HttpClient` tái sử dụng được; ưu tiên HTTPS và đặt connect/request timeout.
3. Đọc **status code** và headers trước khi tin vào body. 2xx không đồng nghĩa dữ liệu chắc chắn đúng; 4xx/5xx là phản hồi HTTP, không mặc định là ngoại lệ Java.
4. **Decode → parse → validate → transform** theo schema, giới hạn kích thước và khả năng thiếu trường; giữ lỗi dữ liệu khác biệt với lỗi vận chuyển.
5. Gắn ngữ cảnh request/trace, phát logs, metrics và traces; đo thời gian đủ để tìm nơi chậm hoặc lỗi.

Một timeout không chứng minh server chưa xử lý request. Một HTTP 200 vẫn có thể mang body không hợp lệ. Một log thiếu correlation ID có thể không ghép được với thao tác ở dịch vụ kế tiếp. Vì vậy ba phần của bài cần được thiết kế cùng nhau.

## 2. Nền tảng HTTP cần biết

**Request** gồm method, URI (scheme, host, path, query), headers và body khi phù hợp. **Response** gồm status, headers và body. Header `Accept` cho biết định dạng mong muốn; `Content-Type` cho biết cách hiểu payload thực tế. Với text, cần chỉ rõ encoding, thường dùng UTF-8. Không đoán response luôn là JSON hoặc luôn có body (ví dụ 204 không có nội dung).

| Nhóm/mã | Ý nghĩa thực hành |
| --- | --- |
| 2xx | Thành công ở tầng HTTP; vẫn phải kiểm tra định dạng và dữ liệu. |
| 3xx | Chuyển hướng; áp dụng chính sách redirect rõ ràng. |
| 400, 422 | Đầu vào không thỏa yêu cầu/validation; thường cần sửa request. |
| 401, 403 | Xác thực hoặc quyền truy cập không đáp ứng. |
| 404, 409 | Không tìm thấy tài nguyên hoặc xung đột trạng thái. |
| 429 | Bị giới hạn tốc độ; cân nhắc `Retry-After` và ngân sách retry. |
| 5xx | Server hoặc thành phần trung gian lỗi; chỉ retry khi thích hợp. |

**Ý nghĩa method và idempotency:** `GET` dùng để đọc; `PUT` và `DELETE` được thiết kế idempotent; `POST` thường không mặc định idempotent. Idempotent nói về **hiệu ứng trên trạng thái server khi lặp yêu cầu**, không bắt buộc mọi response giống nhau. Với POST tạo dữ liệu, cần cơ chế như idempotency key do API hỗ trợ nếu muốn retry an toàn.

**HTTPS/TLS:** xác thực endpoint và bảo vệ nội dung khi truyền; giữ kiểm tra chứng chỉ theo mặc định. Không tắt TLS verification để né lỗi môi trường. `java.net.http.HttpClient` hỗ trợ HTTP/1.1 và HTTP/2; thực tế giao thức được thương lượng với server và kết nối. Không giả định HttpClient của JDK 11 tự có các khả năng của những phiên bản Java mới hơn.

**URI an toàn:** không cho input chưa kiểm soát quyết định tùy ý host hoặc scheme vì có nguy cơ SSRF. Khi xây dựng giá trị query form-style, có thể dùng `URLEncoder.encode(value, StandardCharsets.UTF_8)` **cho từng query value**; không encode cả URL bằng hàm đó. Không gắn token, mật khẩu, dữ liệu nhạy cảm vào query string hoặc log.

## 3. Java 11 HTTP Client

JDK 11 cung cấp các lớp chính trong package `java.net.http`:

- `HttpClient`: cấu hình connect timeout, HTTP version, chính sách chuyển hướng; **tái sử dụng** thay vì tạo một client cho mỗi bản ghi.
- `HttpRequest`: URI, method, headers, request timeout và `BodyPublisher`.
- `HttpResponse<T>`: status, headers và body do `BodyHandler` xử lý thành kiểu `T`.

Ví dụ xây GET (đoạn minh họa; `uri` là đối tượng `URI` hợp lệ):

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(3))
    .followRedirects(HttpClient.Redirect.NORMAL)
    .version(HttpClient.Version.HTTP_2)
    .build();

HttpRequest request = HttpRequest.newBuilder(uri)
    .timeout(Duration.ofSeconds(8))
    .header("Accept", "application/json")
    .GET()
    .build();

HttpResponse<String> response =
    client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

Cần import `java.net.http.*`, `java.time.Duration` và `java.nio.charset.StandardCharsets`. `send` là lời gọi **đồng bộ**; nó có thể ném `IOException` (lỗi I/O, mạng, timeout) hoặc `InterruptedException`. Phải **tự** kiểm tra `response.statusCode()`: một phản hồi 404 hoặc 503 không tự ném exception chỉ vì là lỗi HTTP. Khi bắt `InterruptedException`, phục hồi cờ ngắt bằng `Thread.currentThread().interrupt()` rồi chuyển lỗi lên tầng gọi.

Gửi JSON (đoạn minh họa; `endpoint` là `URI`, `json` do serializer tạo ra hợp lệ):

~~~java
HttpRequest post = HttpRequest.newBuilder(endpoint)
    .timeout(Duration.ofSeconds(8))
    .header("Accept", "application/json")
    .header("Content-Type", "application/json; charset=utf-8")
    .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
    .build();
~~~

Các lựa chọn body quan trọng: `BodyPublishers.ofString` gửi text, `ofFile` gửi tệp; `BodyHandlers.ofString` phù hợp body text **đã giới hạn kích thước**, `ofFile` ghi trực tiếp ra tệp, `ofInputStream` cho phép đọc stream. Với response lớn, không gom toàn bộ vào `String`; đặt giới hạn dung lượng, xử lý dòng/stream hợp lý và **đóng** tài nguyên. Kiểm tra Content-Type, dữ liệu và status trước khi parse. Nếu nhận byte/binary, dùng handler kiểu byte hoặc stream thay vì diễn dịch tùy tiện thành text.

### 3.1. Timeout, redirect, retry và hủy

- `HttpClient.Builder.connectTimeout(Duration)` đặt giới hạn kết nối mới; `HttpRequest.Builder.timeout(Duration)` đặt giới hạn thời gian cho request. Có thêm **deadline tổng** cho luồng gồm nhiều request và retry.
- `followRedirects(HttpClient.Redirect.NORMAL)` dùng chính sách chuyển hướng phổ biến, không tự chuyển từ HTTPS về HTTP; với header xác thực phải giới hạn miền được phép chuyển hướng.
- Retry có điều kiện: lỗi mạng thoáng qua hoặc 429/503 theo chính sách API, số lần tối đa, exponential backoff + jitter, `Retry-After`, idempotency và hạn mức thời gian. Không retry POST tạo dữ liệu mà không có bảo đảm chống xử lý trùng.
- Khi timeout/mất kết nối, không suy diễn server chắc chắn chưa nhận yêu cầu. Tránh lặp retry dồn dập tạo bão tải; dùng rate limiting/circuit breaker khi hệ thống cần.
- Hủy `CompletableFuture` không thay thế việc quản lý transaction, timeout hay trạng thái nghiệp vụ. Luôn xử lý đúng ngoại lệ và giải phóng stream/connection liên quan.

### 3.2. Async với CompletableFuture

`sendAsync` trả về `CompletableFuture<HttpResponse<T>>`, cho phép biến đổi qua `thenApply`, nối công việc qua `thenCompose`, nhận kết quả qua `thenAccept` và xử lý lỗi qua `exceptionally`/`whenComplete`. Đoạn bổ sung dưới đây dùng `client` và `request` đã có, cần import `java.util.concurrent.CompletableFuture`:

~~~java
CompletableFuture<HttpResponse<String>> future =
    client.sendAsync(request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

future.thenAccept(r -> {
    if (r.statusCode() / 100 == 2) {
        System.out.println("HTTP success: " + r.statusCode());
    } else {
        System.err.println("HTTP error: " + r.statusCode());
    }
}).exceptionally(error -> {
    System.err.println("Call failed: " + error.getMessage());
    return null;
});
~~~

Lỗi mạng có thể được bọc trong `CompletionException`. `get()`/`join()` **vẫn chặn** thread đang gọi; gọi chúng ngay sau `sendAsync` bên trong vòng lặp có thể làm mất lợi ích bất đồng bộ. Xây giới hạn concurrency và backpressure; async không mặc định giúp code nhanh hơn nếu bottleneck nằm ở CPU hoặc service bên ngoài. Đoạn này là ví dụ ghép callback, không phải chương trình độc lập (để ứng dụng tồn tại tới khi xử lý hoàn thành, quản lý vòng đời future theo ngữ cảnh thực tế).

## 4. Xử lý dữ liệu trong Java 11

### 4.1. Dữ liệu văn bản và Stream

Java 11 có API xử lý String hữu ích:

- `strip()` bỏ khoảng trắng đầu/cuối theo Unicode; `isBlank()` tìm chuỗi trống hoặc chỉ gồm khoảng trắng.
- `lines()` tạo stream các dòng mà không giữ ký tự kết thúc dòng.
- `repeat(n)` lặp chuỗi khi cần; tránh lạm dụng để tạo dữ liệu cực lớn.
- `Optional.isEmpty()` biểu đạt trường hợp không có giá trị; `orElseGet(...)` tránh thực thi giá trị thay thế khi không cần.

Ví dụ pipeline (giả sử `response` chứa text và đã qua kiểm tra HTTP):

~~~java
List<String> items = response.body().lines()
    .map(String::strip)
    .filter(line -> !line.isBlank())
    .distinct()
    .collect(Collectors.toList());
~~~

Import `java.util.List` và `java.util.stream.Collectors`. Trong stream tuần tự, `distinct()` giữ thứ tự xuất hiện đầu tiên; so sánh text vẫn phân biệt hoa/thường và không tự chuẩn hóa Unicode. `Collectors.toList()` không hứa danh sách kết quả mutable; nếu cần danh sách bất biến dùng `Collectors.toUnmodifiableList()`, có trên Java 11. **Không dùng `Stream.toList()` khi mục tiêu chạy JDK 11**, vì API đó chỉ có trên JDK mới hơn.

### 4.2. File I/O, encoding và giới hạn bộ nhớ

`Files.readString(path, StandardCharsets.UTF_8)` và `Files.writeString(path, content, StandardCharsets.UTF_8)` có trên Java 11, tiện cho file nhỏ/vừa. Với file lớn, dùng `Files.lines` và đóng stream bằng try-with-resources:

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long nonBlank = lines.filter(line -> !line.isBlank()).count();
    System.out.println(nonBlank);
}
~~~

Đây là đoạn minh họa với `path` kiểu `Path`; cần import `java.nio.file.Files`, `java.nio.charset.StandardCharsets` và `java.util.stream.Stream`. Stream từ file giữ tài nguyên mở, nên không quên đóng. Stream chỉ được duyệt một lần; terminal operation như `count()` kết thúc phép xử lý. Không dùng `parallelStream` cho I/O hoặc biến đổi dữ liệu có side effects khi chưa có đo đạc và bảo đảm thread safety.

Với dữ liệu nghiệp vụ, xây pipeline rõ: **decode theo charset → parse theo Content-Type/schema → validate trường bắt buộc, kiểu, phạm vi, null, độ dài → ánh xạ sang DTO/domain → xử lý hoặc lưu**. Dùng `java.time` cho thời gian, `BigDecimal` cho tiền và độ chính xác thập phân. Với identifier cần chuẩn hóa chữ thường không lệ thuộc locale, cân nhắc `toLowerCase(Locale.ROOT)`; không tự tiện thay đổi tên người hoặc nội dung hiển thị. Phân biệt “trống”, “thiếu trường” và “giá trị không hợp lệ” khi nghiệp vụ cần.

### 4.3. JSON: nhiệm vụ của parser riêng

`HttpClient` không tự chuyển JSON thành Java object, và Java SE 11 không có API JSON object mapping tiêu chuẩn sẵn dùng. Với API JSON, dùng thư viện parser/serializer được duy trì và **phiên bản tương thích JDK 11** (chẳng hạn Jackson), quản lý dependency trong Gradle/Maven và kiểm tra schema/DTO. Không dùng regex hoặc `substring` để parse JSON. Nếu payload có thể rất lớn hoặc lồng sâu, dùng streaming parser và giới hạn kích thước/độ sâu để tránh cạn bộ nhớ.

Ba dạng lỗi cần ghi nhận riêng: **transport** (DNS, TLS, timeout, reset), **HTTP status** (4xx, 5xx), **data/contract** (JSON sai, dữ liệu null, schema không khớp). Mỗi dạng lỗi có cách hiển thị, metrics và retry khác nhau.

## 5. Khả năng quan sát ứng dụng

**Observability** giúp biết lỗi xảy ra ở request nào, chỗ nào, mất bao lâu, tác động tới người dùng ra sao. Ba tín hiệu chính là:

| Tín hiệu | Trả lời câu hỏi | Cách triển khai |
| --- | --- | --- |
| **Logs** | Sự kiện cụ thể nào đã diễn ra? | Log có timestamp, level, service, operation, request/trace ID, status, error type, duration. |
| **Metrics** | Tỷ lệ lỗi, độ trễ, thông lượng, mức sử dụng biến đổi ra sao? | Counter cho số lần/lỗi; histogram cho độ trễ, kích thước, phân vị p95/p99. |
| **Traces** | Một request đi qua những service/span nào? | Propagate context, span cho HTTP/DB/queue, phân tích duration và dependency. |

**Logging:** `java.util.logging` có sẵn trên JDK 11 để minh họa. Với sản phẩm, chọn logging framework/structured log được tổ chức duy trì; đưa các trường `event`, `service`, `request_id`, `trace_id`, HTTP status, route dạng mẫu, duration, exception type vào log. Dùng mức INFO cho sự kiện chính, WARN cho bất thường có thể phục hồi, ERROR/SEVERE khi xử lý thất bại. Tránh body hoặc header chứa secrets, cookie, token, PII, query có thông tin nhạy cảm; kiểm soát log retention và quyền truy cập. Không để dữ liệu đầu vào tùy ý gây log injection hoặc độ dài log không giới hạn.

**Metrics:** theo dõi tối thiểu số request, số thành công/thất bại theo nhóm status, timeout, throughput, p50/p95/p99 từ histogram và mức bão hòa tài nguyên. Dùng labels **có tập giá trị hữu hạn** như method, service, route mẫu và status class. Đưa request ID, user ID hoặc URL động vào label sẽ tạo high cardinality và chi phí lớn. Micrometer/OpenTelemetry Metrics thường được tích hợp qua framework hay dependency; đó không phải chức năng tự xuất ra từ `HttpClient`.

**Distributed tracing:** OpenTelemetry SDK/instrumentation tương thích với runtime giúp tạo span, propagate context và export tới backend; W3C Trace Context (đặc biệt header `traceparent`) cho phép nối trace qua nhiều service. Request ID giúp đối chiếu log nhưng không thay thế trace/span. Xây sampling phù hợp, tránh thu thập attributes chứa thông tin nhạy cảm, tuân thủ chính sách dữ liệu.

**Đo độ trễ:** dùng `System.nanoTime()` để lấy chênh lệch thời gian monotonic trong cùng JVM; không dùng wall-clock để đo duration. Phân tích latency theo operation/status và quantile thay vì chỉ dùng giá trị trung bình; kết hợp throughput/error rate để xem ảnh hưởng thực tế.

### 5.1. Công cụ JVM có sẵn ở Java 11

**Java Flight Recorder (JFR)** ghi lại các sự kiện runtime để điều tra CPU, allocation, GC, thread, locks và nhiều hành vi JVM. Dùng `jcmd` cùng JDK, khi có quyền đối với JVM đích:

~~~bash
jcmd <pid> JFR.start name=app_diag settings=profile duration=60s filename=app.jfr
jcmd <pid> Thread.print
jcmd <pid> GC.heap_info
~~~

Thay `<pid>` bằng process ID thực. Mở `app.jfr` bằng công cụ phân tích JFR tương thích; cân nhắc thời lượng, chi phí profiling và thông tin thu được. Theo dõi GC qua unified JVM logging:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

JFR, thread dump, GC logs giúp hiểu **JVM**; chúng không thay thế metrics/traces nghiệp vụ ở tầng HTTP. Với dịch vụ chạy trong orchestrator, cung cấp liveness/readiness theo framework dùng thực tế, và thiết kế readiness phản ánh khả năng tiếp nhận traffic. Không để một dependency phụ bất ổn khiến liveness thất bại liên tục và gây restart vòng lặp.

## 6. Ví dụ hoàn chỉnh chạy trên Java 11

Chương trình dưới đây có **HTTP server loopback chỉ để làm fixture test**, rồi dùng Java 11 `HttpClient` gọi nó, thêm correlation ID, kiểm tra status, xử lý dòng văn bản và log độ trễ. Ví dụ **không cần Internet, không cần dependency bên thứ ba**. HTTP server demo từ module `jdk.httpserver` không phải đề xuất hạ tầng server production.

Lưu thành **`HttpPipelineDemo.java`**:

~~~java
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
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;
import java.util.stream.Collectors;

public class HttpPipelineDemo {
    private static final Logger LOG =
        Logger.getLogger(HttpPipelineDemo.class.getName());

    public static void main(String[] args) throws IOException {
        HttpServer server =
            HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/items", exchange -> {
            byte[] data = "  apple \n\npear\napple\n"
                .getBytes(StandardCharsets.UTF_8);
            String requestId =
                exchange.getRequestHeaders().getFirst("X-Request-ID");
            if (requestId != null) {
                exchange.getResponseHeaders()
                    .set("X-Request-ID", requestId);
            }
            exchange.getResponseHeaders()
                .set("Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, data.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(data);
            }
        });
        server.start();

        try {
            URI uri = URI.create("http://127.0.0.1:" +
                server.getAddress().getPort() + "/items");
            HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .header("Accept", "text/plain")
                .header("X-Request-ID", "demo-22")
                .GET()
                .build();

            long started = System.nanoTime();
            HttpResponse<String> response = send(client, request);
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);

            if (response.statusCode() / 100 != 2) {
                throw new IOException(
                    "HTTP status " + response.statusCode());
            }
            List<String> items = response.body().lines()
                .map(String::strip)
                .filter(line -> !line.isBlank())
                .distinct()
                .collect(Collectors.toList());

            String requestId = response.headers()
                .firstValue("X-Request-ID").orElse("missing");
            LOG.info(() -> "event=http_client_request request_id=" +
                requestId + " status=" + response.statusCode() +
                " duration_ms=" + elapsedMs);

            System.out.println("status=" + response.statusCode());
            System.out.println("request_id=" + requestId);
            System.out.println("items=" + items);
            System.out.println("count=" + items.size());
        } finally {
            server.stop(0);
        }
    }

    private static HttpResponse<String> send(
            HttpClient client, HttpRequest request) throws IOException {
        try {
            return client.send(request,
                HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IOException("HTTP request interrupted", e);
        }
    }
}
~~~

Chạy bằng JDK 11 (bật tường minh module `jdk.httpserver`):

~~~bash
javac --add-modules jdk.httpserver -encoding UTF-8 HttpPipelineDemo.java
java --add-modules jdk.httpserver HttpPipelineDemo
~~~

**Stdout chính xác**; log từ `java.util.logging` xuất riêng ra stderr với timestamp/thời lượng biến đổi theo lần chạy:

~~~text
status=200
request_id=demo-22
items=[apple, pear]
count=2
~~~

Giải thích: server lắng nghe `127.0.0.1` ở cổng tự cấp và trả body UTF-8; client truyền `X-Request-ID`, server echo header này; `send` phục hồi interrupt flag khi bị ngắt; kiểm tra status trước khi xử lý dữ liệu; `lines()`, `strip()`, `isBlank()` và `distinct()` loại dòng rỗng và trùng; `System.nanoTime()` cung cấp duration; `finally` dừng server kể cả khi có lỗi. Trong sản phẩm, dùng HTTPS endpoint thật, parser/DTO, giới hạn body, xác thực, retries có điều kiện, metric/tracing và test nhánh lỗi.

## 7. Xử lý lỗi và an toàn vận hành

| Tình huống | Hành động phù hợp |
| --- | --- |
| 2xx và body hợp lệ | Parse, transform, ghi thành công + duration. |
| 2xx nhưng body sai schema hoặc quá lớn | Báo lỗi dữ liệu/contract, áp dụng giới hạn bộ nhớ; không báo thành công nghiệp vụ. |
| 400/401/403/404 | Trả thông tin lỗi phù hợp, sửa đầu vào/quyền; thường không tự retry. |
| 409 | Phân tích xung đột trạng thái, áp dụng xử lý nghiệp vụ đã quy định. |
| 429/503 | Cân nhắc backoff, `Retry-After`, giới hạn retry và idempotency. |
| IOException, timeout, ngắt | Log loại lỗi và ngữ cảnh, tôn trọng deadline và interrupt flag, không suy đoán trạng thái server. |
| JSON/schema lỗi | Dừng xử lý hoặc phân luồng bản ghi lỗi có kiểm soát, bảo vệ dữ liệu nhạy cảm. |

**Lỗi phổ biến cần tránh:**

- Cho rằng 404/500 sẽ tự ném exception; không kiểm tra status hoặc không xác thực body.
- Tạo client mới cho từng request; không đặt timeout; quên deadline tổng.
- Retry mọi lỗi và lặp POST gây ghi trùng, bỏ qua `Retry-After`.
- Gọi `sendAsync` rồi lập tức `join()` trong vòng lặp.
- Dùng `BodyHandlers.ofString` để đọc payload vô hạn hoặc quên đóng stream.
- Đưa token, cookie, dữ liệu cá nhân và toàn URL có query nhạy cảm vào log.
- Dùng request ID/user ID làm label metrics; chỉ quan sát average latency mà bỏ p95/p99.
- Tưởng JFR/GC log có thể thay thế metrics và trace cho lời gọi HTTP.

## 8. Checklist và tự luyện

Khi hoàn thành một tính năng gọi API, kiểm tra: **HTTPS và URI an toàn; HTTP method phù hợp; timeout và deadline; redirect/retry có điều kiện; status và Content-Type; UTF-8; parser + schema validation; giới hạn body; đóng tài nguyên; log có correlation; counter/histogram lỗi và độ trễ; trace context; bảo vệ secrets; test tình huống 4xx, 5xx, timeout và dữ liệu không hợp lệ**.

Tự luyện: (1) đổi fixture từ 200 sang 503 và xác định đường xử lý lỗi; (2) thêm dòng trống/trùng vào body để dự đoán `items`; (3) thay `send` bằng `sendAsync`, thiết kế điểm chờ không khóa luồng xử lý; (4) phác thảo counter và histogram độ trễ, chỉ dùng labels có cardinality nhỏ; (5) mô tả bạn dùng log, metric, trace và JFR thế nào khi p99 HTTP tăng đột ngột.

**Đầu ra học tập:** hiểu đúng Java 11 `java.net.http`, biết cách xử lý dữ liệu có xác thực và giới hạn tài nguyên, đồng thời thiết kế được khả năng quan sát giúp chẩn đoán lỗi, độ trễ và hành vi ứng dụng trong môi trường hiện nay.
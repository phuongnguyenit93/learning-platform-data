# Ghi log HTTP có kiểm soát mà không làm lộ bí mật trong Java 11

## 1. Mục tiêu của bài học

Một HTTP client cần log để tìm nguyên nhân timeout, lỗi kết nối, response bất thường và đo hiệu năng. Tuy nhiên, một dòng log thiếu kiểm soát có thể chứa **bearer token**, **API key**, **cookie phiên đăng nhập**, **mật khẩu**, **định danh cá nhân**, dữ liệu kinh doanh hoặc nội dung yêu cầu/phản hồi. Log thường được chuyển đến hệ thống tập trung, được nhiều người đọc, lưu lâu hơn request và sao chép vào dashboard, cảnh báo, ticket. Vì vậy, **log cũng là một bề mặt rò rỉ dữ liệu**.

Trong ứng dụng Java 11 dùng `java.net.http.HttpClient`, câu hỏi quan trọng là: **làm sao đủ dữ liệu để điều tra lỗi mà không sao chép thông tin bí mật từ HTTP message sang log?**

Sau bài này, bạn có thể:

- Phân loại thông tin HTTP nên ghi, không nên ghi và chỉ ghi khi có phê duyệt.
- Thiết kế log theo hướng **allowlist trường an toàn**, thay vì ghi request/response thô rồi tìm cách xóa bí mật.
- Hiểu rủi ro của `URI`, query string, headers, cookies, body, exceptions, `toString()`, tracing và cấu hình log nội bộ của JDK.
- Sử dụng `java.util.logging.Logger` và event có tham số trên Java 11; nhận diện giới hạn của định dạng văn bản không có escape.
- Quản lý correlation ID, mã lỗi, HTTP status, thời gian xử lý, kết nối bất đồng bộ và log khi retry.
- Viết kiểm thử xác nhận **secret thật không xuất hiện trong log**, kể cả nhánh lỗi, debug và dữ liệu độc hại.
- Cấu hình vận hành: cấp độ log, phân quyền đọc, lưu giữ, truyền tải và điều tra sự cố.

**Phạm vi phiên bản:** `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse` và `java.util.logging` đều có trong Java 11; các cách quản lý log an toàn bên dưới vẫn được áp dụng trên JDK hiện đại. Trường hợp cấu hình chẩn đoán nội bộ thay đổi giữa các bản JDK sẽ được nói rõ, không mặc định một danh sách property áp dụng vĩnh viễn.

## 2. Nguyên tắc nền tảng: ghi sự kiện, không ghi dữ liệu bí mật

Thay vì cố log “mọi thứ”, hãy định nghĩa **những câu hỏi vận hành phải trả lời**:

1. **Khi nào?** Event xảy ra lúc nào, thuộc request/correlation nào?
2. **Ở đâu?** Dịch vụ đích theo **alias được phê duyệt**, operation nào, route **template** nào?
3. **Làm gì?** HTTP method, thao tác nghiệp vụ dạng mã cố định, attempt thứ mấy?
4. **Kết quả?** Thành công/thất bại, nhóm HTTP status, loại lỗi đã phân loại?
5. **Mất bao lâu?** Độ trễ, timeout, số byte hoặc số phần tử đã xử lý **nếu số liệu này được phép lưu**.

Không cần tên người dùng, token, URL đầy đủ hay toàn bộ body để trả lời phần lớn câu hỏi trên.

**Ưu tiên thứ tự phòng vệ:**

1. **Không thu thập secret** ngay từ đầu (data minimization).
2. **Allowlist** đúng field được phép đưa ra log, kèm kiểu dữ liệu và giới hạn độ dài.
3. Chuẩn hóa và kiểm tra input trước khi ghi, ví dụ `correlationId` chỉ gồm ký tự an toàn.
4. Dùng encoder cho định dạng output (JSON/structured logger khi có), tránh log injection.
5. Phân quyền, bảo vệ, giới hạn thời gian giữ log và kiểm soát nơi xuất log.
6. Chạy test với secret giả làm sentinel, tìm mọi đường có thể rò rỉ.

**Redaction/masking theo regex** chỉ là lớp bổ sung để phòng sai sót. Nó **không đủ** làm thiết kế chính: token có thể nằm trong query, header lạ, body JSON, exception message, URL đã encode hoặc một format chưa biết. Quy tắc “ghi trước, che sau” thường thất bại khi dữ liệu bị biến đổi hoặc đi qua một logger không chịu sự kiểm soát của bạn.

## 3. Ma trận dữ liệu HTTP: cho phép hay không?

| Trường dữ liệu | Chính sách mặc định | Lý do / cách thay thế |
| --- | --- | --- |
| Tên event như `http.client.completed` | Cho phép | Hằng số do code kiểm soát |
| Tên operation như `lookup_product` | Cho phép nếu từ danh mục cố định | Không lấy từ body hoặc user input thô |
| Service alias như `catalog_service` | Cho phép khi đã phân loại | Tránh ghi host nội bộ không cần thiết |
| HTTP method `GET`/`POST` | Thường có thể cho phép | Giá trị từ enum/danh sách hợp lệ |
| Route template `/v1/items/{id}` | Thường có thể cho phép | **Không ghi path thực** có ID, email, mã đơn hàng |
| HTTP status code/nhóm status | Thường có thể cho phép | `2xx`, `4xx`, `5xx` thường đủ cho metrics |
| Độ trễ, số lần retry, bucket kích thước | Cho phép theo chính sách | Số liệu có giới hạn và không định danh trực tiếp |
| Correlation ID do hệ thống tạo, không mang secret | Có điều kiện | Validate định dạng, độ dài; không dùng session token làm ID |
| URI đầy đủ hoặc `request.uri()` | Không ghi trực tiếp | Query, path, user-info có thể chứa bí mật |
| Query string, fragment, user-info | Không ghi trực tiếp | Có thể chứa token, email, mật khẩu |
| `Authorization`, `Proxy-Authorization` | Không | Chứa thông tin xác thực có thể dùng lại |
| `Cookie`, `Set-Cookie` | Không | Chứa session ID, CSRF token hoặc dữ liệu nhạy cảm |
| `X-API-Key` và header tùy chỉnh chứa credential | Không | Header tùy chỉnh có thể là secret |
| `Location`, `Referer`, `User-Agent` | Không log thô mặc định | Có thể chứa URL bí mật, thông tin cá nhân hoặc fingerprint |
| Request/response body | Không log thô mặc định | JSON, XML, multipart, file, lỗi ứng dụng có thể chứa dữ liệu nhạy cảm |
| `Throwable.getMessage()`, stack trace không kiểm soát | Không đưa thẳng vào log dùng chung | Có thể chứa URI, token, header, body, đường dẫn nội bộ |
| HTTP client internal wire/debug logs | Chỉ bật theo quy trình điều tra có kiểm soát | Có thể phơi bày metadata, header hoặc payload |

**Tình huống cần riêng:** hệ thống giám sát an ninh đôi khi phải ghi sự kiện chứa một định danh hoặc IP để phát hiện lạm dụng. Điều này cần mục đích rõ ràng, quyền truy cập, retention, giảm nhận diện và yêu cầu pháp lý tương ứng; không phải lý do bật log tất cả thông tin cá nhân ở mọi request.

**Ví dụ URI nguy hiểm:**

```text
https://api.example.test/orders/12345?access_token=demo-secret&email=test%40example.com
```

Một dòng tưởng như vô hại:

```java
logger.info("Sending to " + request.uri()); // Không an toàn.
```

có thể lưu cả `access_token`, email và order ID. Thay bằng metadata từ danh mục tin cậy:

```text
event=http.client.start operation=create_order destination=order_service route=/orders/{id}
```

Route template phải là **chuỗi cố định được code kiểm soát**, không phải thay tất cả chữ số trong raw URI rồi hy vọng đủ an toàn; path đôi khi chứa email, UUID, token hoặc giá trị được encode.

## 4. Các bẫy Java 11 thường làm lộ dữ liệu

### 4.1. Log cả `HttpRequest` hoặc `HttpResponse`

Không ghi:

```java
logger.info("request = " + request);
logger.info("uri = " + request.uri());
logger.info("headers = " + request.headers().map());
logger.info("response = " + response);
logger.info("response headers = " + response.headers().map());
```

Đây là **trích đoạn minh họa lỗi**, với `logger`/`request`/`response` đã được khai báo bên ngoài. `HttpRequest.toString()`, `HttpResponse.toString()` hoặc các object tương tự không phải hợp đồng log an toàn; có thể chứa URL hoặc dữ liệu mà bạn không muốn công khai. Cũng không nên gọi `headers.map().toString()`: phần tử `Authorization`/`Cookie` và các header nội bộ có thể nằm trong map.

**Cách làm tốt hơn:** tạo một bản ghi từ các field đã cho phép. Không truyền object request/response nguyên trạng sang logging framework để logger tự serialize.

### 4.2. Request body và response body

`BodyPublishers.ofString(...)`, `ofByteArray(...)`, `ofInputStream(...)` được dùng để **gửi body**; `BodyHandlers.ofString()`, `ofByteArray()`, `ofInputStream()` được dùng để **nhận body**. Dữ liệu có thể gồm mật khẩu, địa chỉ, token, dữ liệu thanh toán hoặc tài liệu người dùng.

**Không** log:

```java
logger.info("request payload: " + jsonBody);
logger.info("response payload: " + response.body());
```

Ngay cả khi `response.statusCode() >= 400`, error body đôi khi chứa thông tin nhạy cảm hoặc echo input của caller. Đừng cho rằng “response lỗi thì được log nguyên body”.

Nếu cần phân tích lỗi payload, ghi **mã validation** hoặc tên trường từ danh mục tin cậy (ví dụ `VALIDATION_FAILED`), không ghi giá trị đầu vào. Để debug dữ liệu phức tạp, có thể dùng môi trường thử nghiệm với dữ liệu tổng hợp và cơ chế thu thập có kiểm soát riêng; không biến log production thành kho dữ liệu nhạy cảm.

### 4.3. Exception, stack trace và logging framework

Một `IOException` hoặc `CompletionException` có thể chứa endpoint, thông tin proxy, đường dẫn file hoặc thông điệp từ server. Ghi trực tiếp:

```java
logger.log(Level.SEVERE, "Request failed", throwable);
logger.severe("failure=" + throwable.getMessage());
throwable.printStackTrace();
```

có thể đưa dữ liệu không kiểm soát vào log. **Không có quy tắc rằng mọi exception đều chứa bí mật**, nhưng cần phân loại mức tin cậy của message/cause trước khi công khai.

Với log dùng chung, ưu tiên:

```java
logger.log(Level.WARNING,
        "event=http.client.failure operation={0} error_code={1}",
        new Object[] {"lookup_item", "TRANSPORT_FAILURE"});
```

Trong nơi có quyền bảo mật cao, stack trace có thể được giữ riêng khi đã đánh giá dữ liệu và quyền truy cập. Không xoá sạch mọi thông tin điều tra sự cố một cách máy móc; thay vào đó thiết kế **kênh bảo mật hơn**, retention ngắn và phạm vi truy cập phù hợp.

Đối với `sendAsync`, lỗi có thể nằm trong `CompletionException`. Đừng log toàn bộ `error.toString()` trong `whenComplete`; ánh xạ về một **failure category** đã định nghĩa.

## 5. Thiết kế sự kiện log HTTP theo allowlist

Hãy chuẩn hóa schema trước khi triển khai. Ví dụ:

| Field | Ví dụ | Nguồn được phép |
| --- | --- | --- |
| `event` | `http.client.completed` | Hằng số |
| `operation` | `inventory_lookup` | Enum/mã thao tác từ ứng dụng |
| `destination` | `inventory_service` | Alias từ cấu hình được duyệt |
| `method` | `GET` | Kiểm tra trong tập method được phép |
| `route` | `/v1/items/{id}` | Route template do code cung cấp |
| `result` | `success` hoặc `failure` | Enum do code quyết định |
| `status_class` | `2xx`, `4xx`, `5xx` | Tính từ status code, không lấy body |
| `duration_ms` | `27` | `System.nanoTime()` tính chênh lệch, không log thời gian thô nhạy cảm |
| `correlation` | `req-0042` | ID ngẫu nhiên độc lập với token, được validate |
| `error_code` | `TIMEOUT`, `CONNECTION`, `CANCELLED` | Phân loại từ exception **không ghi message** |
| `attempt` | `1`, `2` | Số lần thử được giới hạn |

**Cho phép định danh không đồng nghĩa mọi giá trị trong field đều an toàn.** Ví dụ `destination` nên là alias từ registry, không lấy tùy ý từ host người dùng nhập. `correlation` phải được sinh mới hoặc kiểm tra chặt chẽ; một header `X-Request-ID` do client ngoài kiểm soát có thể chứa xuống dòng, ký tự điều khiển hoặc dữ liệu cá nhân.

Thời lượng nên đo bằng `System.nanoTime()`:

```java
long startNanos = System.nanoTime();
// ... thao tác HTTP ...
long durationMillis =
        java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startNanos);
```

Đây là **trích đoạn**, không phải chương trình đầy đủ. `System.nanoTime` phù hợp đo **khoảng thời gian**, không dùng làm timestamp tuyệt đối hay làm dữ liệu định danh. Phải xem xét timeout, retry và khoảng thời gian đo (mỗi attempt hay toàn workflow) trước khi so sánh latency.

## 6. Ví dụ Java 11 hoàn chỉnh: tạo log an toàn, không cần mạng

Chương trình này xây dựng một `HttpRequest` có **token và cookie giả lập**, nhưng **không gửi HTTP request**. Nó chỉ log metadata thuộc allowlist và tự kiểm tra chuỗi bí mật không xuất hiện trong log được tạo. Một `StreamHandler` và `Formatter` đơn giản được dùng **chỉ để tạo stdout xác định khi học**; production nên dùng cấu hình logging/structured encoder đã được duyệt.

Tạo tệp **`SafeHttpLogDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class SafeHttpLogDemo {

    private static final Logger LOG =
            Logger.getLogger(SafeHttpLogDemo.class.getName());

    static String checkedCorrelationId(String candidate) {
        if (candidate == null ||
                !candidate.matches("[A-Za-z0-9._-]{1,64}")) {
            return "invalid";
        }
        return candidate;
    }

    public static void main(String[] args) {
        String syntheticToken = "demo-secret-99";
        String syntheticCookie = "demo-session-88";

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(
                        "https://catalog.example.invalid/v1/items/42"
                        + "?access_token=" + syntheticToken))
                .header("Authorization", "Bearer " + syntheticToken)
                .header("Cookie", "session=" + syntheticCookie)
                .GET()
                .build();

        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        Handler handler = new StreamHandler(sink, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return formatMessage(record) + "\n";
            }
        });
        handler.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(handler);

        try {
            String correlation =
                    checkedCorrelationId("req-0042");

            // Operation, alias và route là giá trị đáng tin cậy,
            // không được suy ra từ URI/query/header tùy ý.
            LOG.log(Level.INFO,
                    "http.start operation={0} destination={1}"
                    + " method={2} route={3} correlation={4}",
                    new Object[] {
                            "inventory_lookup",
                            "catalog_service",
                            request.method(),
                            "/v1/items/{id}",
                            correlation
                    });

            // Status và duration mô phỏng để kiểm tra logic log.
            LOG.log(Level.INFO,
                    "http.end operation={0} outcome={1}"
                    + " status_class={2} duration_ms={3}"
                    + " correlation={4}",
                    new Object[] {
                            "inventory_lookup",
                            "success",
                            "2xx",
                            27,
                            correlation
                    });

            handler.flush();
            String produced = new String(
                    sink.toByteArray(), StandardCharsets.UTF_8);
            System.out.print(produced);

            System.out.println("token_leaked="
                    + produced.contains(syntheticToken));
            System.out.println("cookie_leaked="
                    + produced.contains(syntheticCookie));
            System.out.println("query_leaked="
                    + produced.contains("access_token"));
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }
    }
}
```

Biên dịch/chạy bằng **JDK 11** (hoặc JDK mới hơn hỗ trợ biên dịch mục tiêu 11):

```bash
javac --release 11 -encoding UTF-8 SafeHttpLogDemo.java
java SafeHttpLogDemo
```

**Kết quả dự kiến:**

```text
http.start operation=inventory_lookup destination=catalog_service method=GET route=/v1/items/{id} correlation=req-0042
http.end operation=inventory_lookup outcome=success status_class=2xx duration_ms=27 correlation=req-0042
token_leaked=false
cookie_leaked=false
query_leaked=false
```

**Vì sao ví dụ không lộ token?**

1. Request thật trong bộ nhớ có URL query, `Authorization` và `Cookie` chứa dữ liệu tổng hợp, nhưng code **không hề đưa những trường đó vào Logger**.
2. `operation`, `destination` và `route` là các chuỗi do code lựa chọn; đường dẫn `/v1/items/{id}` không tiết lộ ID thực `42`.
3. `request.method()` trả `GET`; giá trị này không chứa secret trong ví dụ.
4. `correlation` được kiểm tra theo tập ký tự và giới hạn độ dài; không dùng token hoặc session ID làm correlation.
5. Handler có format chỉ ghi message đã được duyệt, không thêm timestamp động, nên output ví dụ xác định.
6. Ba phép kiểm tra tìm secret/query **trong log thật vừa tạo** và cho `false`; chúng không chứng minh các logger khác hoặc một bản build khác đều an toàn.

**Giới hạn của demo:** dùng `StreamHandler` ở đây để kiểm tra đầu ra. Đây không phải một JSON structured encoder production và không tự encode mọi loại dữ liệu không đáng tin cậy. Trong hệ thống thực, cần schema/encoder đã xác nhận, bộ lọc trường, giới hạn độ dài và kiểm thử các sink khác như APM, tracing, proxy hay audit logger.

## 7. Log khi gọi `HttpClient.send()` và `sendAsync()`

### 7.1. Đường đồng bộ `send()`

`HttpClient.send` có thể ném `IOException` hoặc `InterruptedException`. Khi ghi log, nên đưa vào **event code** đã chuẩn hóa và giữ đúng thông tin về timeout/cancellation:

```java
long start = System.nanoTime();

try {
    HttpResponse<Void> response =
            client.send(request,
                    HttpResponse.BodyHandlers.discarding());

    logger.log(Level.INFO,
            "http.completed operation={0} status_class={1}"
            + " elapsed_ms={2}",
            new Object[] {
                    "health_check",
                    response.statusCode() / 100 + "xx",
                    TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - start)
            });
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    logger.warning(
            "http.failed operation=health_check error_code=INTERRUPTED");
    throw ex;
} catch (IOException ex) {
    logger.warning(
            "http.failed operation=health_check error_code=IO_ERROR");
    throw ex;
}
```

Đây là **trích đoạn Java 11** bên trong phương thức khai báo `throws IOException, InterruptedException`; cần import `HttpResponse`, `IOException`, `Level`, `TimeUnit` và các biến `client`, `request`, `logger`. `BodyHandlers.discarding()` bỏ nội dung body khi không cần. Không log `ex.getMessage()` hoặc `request.uri()`.

**Chú ý:** log “http.completed” chỉ nói request HTTP trả response; **không** khẳng định nghiệp vụ thành công. Ví dụ status `500` vẫn có thể là HTTP response hoàn chỉnh, nên nên phân loại thêm `outcome`/`status_class` theo chính sách riêng.

### 7.2. Đường bất đồng bộ `sendAsync()`

`sendAsync` trả `CompletableFuture`, lỗi có thể nằm trong `CompletionException`. Đừng log toàn bộ object `error` trong callback:

```java
long started = System.nanoTime();

CompletableFuture<HttpResponse<Void>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.discarding());

future.whenComplete((response, error) -> {
    long elapsed = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - started);
    if (error != null) {
        logger.log(Level.WARNING,
                "http.failed operation={0} error_code={1}"
                + " elapsed_ms={2}",
                new Object[] {"health_check", "ASYNC_FAILURE", elapsed});
    } else {
        logger.log(Level.INFO,
                "http.completed operation={0} status_class={1}"
                + " elapsed_ms={2}",
                new Object[] {
                        "health_check",
                        response.statusCode() / 100 + "xx",
                        elapsed
                });
    }
});
```

Đây là **trích đoạn**, không phải chương trình độc lập: cần `CompletableFuture`, `HttpResponse`, `TimeUnit`, `Level` và các biến `client`, `request`, `logger`. Với nghiệp vụ thực, phân loại lỗi rõ hơn (`TIMEOUT`, `CANCELLED`, `CONNECT_ERROR`, `OTHER`) dựa trên type/chuỗi cause hợp lệ đã kiểm tra; **đừng lấy nguyên message từ cause để đưa vào log**.

Với nhiều request đồng thời, correlation ID phải **gắn trực tiếp với request context/callback** hoặc được truyền đúng qua context propagation. Không dựa hoàn toàn vào `ThreadLocal`/MDC vốn có thể không tự truyền qua mọi CompletableFuture stage hoặc executor. Kết nối các event theo correlation không chứa secret; dùng span/trace ID đã được kiểm tra nếu hệ thống tracing cung cấp.

## 8. Cấu hình log nội bộ của JDK `HttpClient`: tiện nhưng có rủi ro

Oracle tài liệu Java SE 11 ghi nhận system property:

```text
jdk.httpclient.HttpClient.log
```

Có thể kích hoạt qua tham số JVM, ví dụ:

```bash
java -Djdk.httpclient.HttpClient.log=errors YourApplication
```

Đây là **lệnh minh họa** dành cho ứng dụng Java có `YourApplication` thật, không phải lệnh chạy demo bên trên. Oracle Java 11 liệt kê các loại log:

| Mục cấu hình | Mô tả cấp cao | Rủi ro cần đánh giá |
| --- | --- | --- |
| `errors` | Lỗi vận hành HTTP client | Thông điệp lỗi có thể chứa endpoint/địa chỉ/chi tiết môi trường |
| `requests` | Hoạt động request | Có thể ghi URI hoặc metadata ngoài allowlist của ứng dụng |
| `headers` | Header HTTP | **Nguy cơ trực tiếp:** Authorization, Cookie, Set-Cookie, API key |
| `frames`, `frames:all` | Frame HTTP/2 | Metadata giao thức, khối dữ liệu và thông tin nhạy cảm tùy triển khai |
| `ssl` | Hoạt động TLS | Metadata về kết nối, chứng chỉ và hệ thống đích |
| `trace` | Truy vết chi tiết | Dữ liệu/đường đi vận hành khó kiểm soát |
| `channel` | Hoạt động kênh kết nối | Metadata mạng/kết nối |

Theo tài liệu **Java 11**, logger tên `jdk.httpclient.HttpClient` và các sự kiện của cơ chế này được ghi ở `INFO` qua `java.util.logging`. Đây là **cấu hình chẩn đoán cấp JDK**, không cùng thứ với log nghiệp vụ đã allowlist ở code.

**Không bật** `headers`, `requests`, `frames:all` hoặc `trace` rộng rãi trong production chứa bí mật chỉ vì đang debug. Nếu điều tra thật sự cần, phải có phê duyệt, giới hạn thời gian, kiểm soát máy đích và quyền xem, bảo vệ file log, đánh giá dữ liệu sẽ được ghi, kế hoạch dọn log sau sự cố. Ngay cả `errors` cũng cần xem xét output thực tế.

Cẩn trọng khi đọc bài viết về các JDK khác: một số tài liệu Oracle JDK mới còn liệt kê tùy chọn log `content`, trong khi bảng cấu hình Java 11 ở trên không liệt kê mục đó. **Luôn kiểm tra tài liệu của JDK thực đang triển khai**, không suy đoán rằng mọi flag debug có cùng ngữ nghĩa trên các bản JDK.

**Không dùng** việc thay đổi log level của ứng dụng thành `FINE`/`DEBUG` như một lý do để bí mật xuất hiện trong log. Thay đổi cấp độ chỉ ảnh hưởng có ghi event hay không; **nội dung event vẫn phải an toàn ở mọi cấp độ**.

## 9. Ngăn log injection và dữ liệu không đáng tin cậy

Một attacker có thể đưa ký tự CR (`\r`), LF (`\n`), delimiter hoặc chuỗi có định dạng giả vào giá trị của header hay query. Khi ứng dụng nối thẳng giá trị này vào log văn bản, attacker có thể tạo thêm dòng log giả để che giấu sự kiện:

```text
X-Request-ID: abc
WARN payment approved
```

Đó là **mô phỏng giá trị bị chèn xuống dòng**, không phải hai event được sinh bởi logging framework.

Các biện pháp:

1. **Không đưa trường không cần thiết vào log**. Ví dụ nếu không cần header người dùng, đừng ghi.
2. Chỉ nhận **correlation ID** có dạng hạn chế, chẳng hạn `[A-Za-z0-9._-]{1,64}`, và có chính sách thay bằng ID nội bộ khi không hợp lệ. Không sử dụng raw request ID làm tên file, field name hoặc log key.
3. Nếu nghiệp vụ phải ghi một chuỗi không đáng tin, dùng **structured logging** với JSON encoder đã thử nghiệm escape CR/LF, dấu nháy, control characters, Unicode và giới hạn kích thước.
4. Dùng **message template cố định**, truyền tham số thay vì nối chuỗi đầu vào không kiểm soát. Tuy nhiên, parameterized logging **không thay thế** encoding/validation; `Logger` hoặc formatter text thông thường vẫn có thể in newline trong tham số.
5. Không cho phép dữ liệu từ request tùy ý quyết định log level, tên event, tên field, pattern format hay nơi ghi.
6. Thực hiện test với `\r\n`, Unicode, chuỗi rất dài, encoded URL và các ký tự đặc biệt.

Chỉ thay xuống dòng bằng dấu cách là biện pháp bổ sung, không đảm bảo bảo mật nếu dữ liệu vẫn có thể chứa secret. **Chống injection** và **chống lộ bí mật** là hai yêu cầu độc lập, phải đáp ứng cả hai.

## 10. Header và query: tại sao blacklist không đủ?

Danh sách secret quen thuộc là `Authorization`, `Cookie`, `Set-Cookie`, `Proxy-Authorization`, `X-API-Key`. Nhưng hệ thống thực còn có các tên tùy biến:

- `X-Client-Secret`, `X-Signature` hoặc header chứa mã xác minh.
- Query `access_token`, `api_key`, `password`, `signature`, `code` hoặc tham số do nhà cung cấp tự đặt.
- URL ký số để tải file, reset password, OAuth code hoặc kích hoạt email.
- Header `Location`/`Referer` chứa URL có query nhạy cảm.
- Response header và JSON body trả lại một phần secret khi có lỗi.

Một blacklist tên khóa có thể bỏ sót thứ chưa biết. Còn regex thay `Bearer ...` không thể bảo đảm bắt mọi token trong XML, URL encoding, base64 hoặc payload tùy biến.

**Thiết kế allowlist an toàn hơn:**

- Chỉ ghi **tên field cố định** do code chủ động lựa chọn.
- Với status, method, outcome: validate hoặc chuyển đổi thành enum/bucket.
- Với host/route: ghi **alias/template**, không ghi raw URI và không tự lấy query.
- Với ID dùng để tương quan: sinh độc lập, không giống session ID, không chứa PII; validate độ dài, format.
- Với header: nếu thật sự có nhu cầu, log **flag có/không** hoặc loại giao thức đã xác minh, không ghi raw value; `Content-Type` tự nó cũng có thể chứa parameter không mong muốn.
- Với body: ghi **kích thước**, loại payload tổng quát hoặc mã validation nếu chính sách cho phép, không ghi nội dung.

**Không dựa vào** “chỉ log 10 ký tự đầu” hoặc “chỉ log 4 ký tự cuối” của token: phần token bị rò rỉ đôi khi vẫn đủ để hỗ trợ tấn công, tái nhận diện hoặc kết hợp với dữ liệu khác. Nếu phải tương quan session, xem xét định danh độc lập hoặc HMAC có khóa được quản lý cho mục đích rõ ràng; không hash trực tiếp secret bằng thuật toán yếu/không có khóa rồi cho rằng an toàn.

## 11. Logging của retries, redirects, authentication và timeout

Các hành vi HTTP gây phát sinh nhiều event liên quan một thao tác:

| Tình huống | Thông tin hữu ích | Điều cần tránh |
| --- | --- | --- |
| Retry | `operation`, `attempt`, `retry_reason_code`, backoff bucket | Log lại raw request/body hoặc token cho mỗi attempt |
| Redirect | Số lần redirect, policy, mã status | Log raw `Location` có URL ký số hoặc credential |
| Authentication challenge | Loại sự kiện `auth_challenge`, status class | Log `Authorization` hoặc response WWW-Authenticate đầy đủ không kiểm soát |
| Connect timeout | `error_code=CONNECT_TIMEOUT`, latency, destination alias | Log exception message chứa proxy/hostname nhạy cảm |
| Request timeout | `error_code=REQUEST_TIMEOUT`, deadline bucket | Log toàn bộ request, URL với query token |
| TLS failure | `error_code=TLS_FAILURE`, loại lỗi đã phân loại | Ghi material bí mật, certificate dump hoặc key |
| HTTP 401/403 | Status class, operation, correlation | Dùng response body lỗi như bản ghi credential |
| Server 5xx | Status code, operation, latency, retry decision | Ghi response body tự do hoặc stack trace từ upstream |

**HTTP 4xx/5xx là HTTP response**, không tự động tương đương lỗi transport. Nếu `sendAsync(...).whenComplete` trả một `HttpResponse` không lỗi, status code vẫn có thể là 500. Hãy log `status_code` hoặc `status_class` và kết quả business riêng, thay vì tự gộp thành exception message.

**Không tin URL đã redirect là an toàn:** một server có thể trả `Location` chứa token, URL nội bộ hoặc query do attacker điều khiển. Log `redirect_count`/`redirect_status` là cách hữu ích hơn nếu không cần đích thực.

## 12. Correlation ID, trace ID và quyền riêng tư

Trong luồng bất đồng bộ, cùng một request đi qua nhiều thread, retry và callback. Correlation ID giúp liên kết các event mà **không cần đưa token hoặc email vào log**.

Nguyên tắc:

- Ưu tiên ID **được ứng dụng tạo** hoặc một trace ID từ cơ chế observability đã được phê duyệt.
- Không dùng cookie session, `Authorization`, bearer token, email, số điện thoại hay mã thanh toán làm correlation ID.
- Nếu nhận `X-Request-ID`/`traceparent` từ bên ngoài, kiểm tra format, độ dài, ký tự và chính sách tin cậy; khi không hợp lệ có thể tạo ID nội bộ mới.
- Truyền correlation theo **request context** tới mọi callback/future; `ThreadLocal`/MDC không tự động đi theo mọi `CompletableFuture` và executor.
- Tránh một ID bền vững dùng để theo dõi người dùng qua nhiều phiên nếu không có căn cứ pháp lý/mục đích rõ.
- Nếu có nhiều hệ thống chia sẻ trace, áp dụng chính sách phân loại dữ liệu như với log: tên span, attributes, baggage, tag và exception event đều có thể rò rỉ.

Ví dụ:

```text
event=http.client.start correlation=req-0042 operation=inventory_lookup
event=http.client.retry correlation=req-0042 attempt=2 reason=TRANSIENT_IO
event=http.client.complete correlation=req-0042 status_class=2xx duration_ms=121
```

Không có bearer token, cookie hoặc giá trị raw URL mà vẫn theo được diễn biến request. Với HTTP client chạy đồng thời, correlation phải thuộc đúng request cụ thể, không dùng một biến mutable toàn cục chung cho mọi request.

## 13. Cấu hình mức độ log và giới hạn chi phí

| Mức log JUL | Loại event thường phù hợp | Ghi chú |
| --- | --- | --- |
| `SEVERE` | Lỗi nghiêm trọng cần người vận hành can thiệp | Không in raw exception/body |
| `WARNING` | HTTP/transport failure cần theo dõi, retry cạn | Có mã lỗi chuẩn hóa |
| `INFO` | Tổng hợp kết quả hoặc event cần audit | Tránh log mọi request tốc độ cao nếu không cần |
| `CONFIG` | Thay đổi cấu hình **không chứa secret** | Không in giá trị property/token/credential |
| `FINE`, `FINER`, `FINEST` | Tracing/diagnostics có giới hạn | Vẫn phải áp allowlist/encoding |
| `OFF` | Tắt logger không bắt buộc khi được cho phép | Không dùng để tắt các sự kiện an ninh/audit bắt buộc |

Với traffic lớn, ghi một event cho **mỗi** request có thể tạo chi phí I/O, dung lượng lưu trữ và thông tin nhạy cảm suy ra từ tần suất hoạt động. Cần đặt ngưỡng event, aggregation, sampling theo chính sách, rate limit, queue hữu hạn và backpressure ở logging pipeline. Tuy nhiên, **không được sampling làm mất sự kiện audit bắt buộc** hoặc tắt toàn bộ log an ninh chỉ vì muốn giảm chi phí.

Dùng parameterized logging hoặc lazy supplier để tránh format thông điệp tốn kém khi mức log bị tắt, nhưng nhớ rằng **lazy logging không làm dữ liệu trở nên an toàn**. Tránh để lambda logging gọi hàm đọc toàn bộ body hoặc serialize object bất kỳ chỉ để tạo thông điệp debug.

Ví dụ trích đoạn `java.util.logging`:

```java
if (logger.isLoggable(Level.FINE)) {
    logger.log(Level.FINE,
            "http.retry operation={0} attempt={1}",
            new Object[] {"inventory_lookup", retryAttempt});
}
```

`retryAttempt` phải là biến số hợp lệ trong scope; đây **không** phải chương trình đầy đủ. Chỉ field an toàn đã được chọn được đưa vào log.

## 14. Bảo vệ log trong production: ngoài phạm vi mã Java

Dù application đã allowlist metadata, rủi ro vẫn còn trong hệ thống thu thập log:

1. **Phân quyền đọc/ghi**: chỉ cấp quyền theo role/cần biết, không để log tự do cho mọi developer/nhà cung cấp.
2. **Truyền tải an toàn**: bảo vệ đường truyền từ ứng dụng tới collector bằng cấu hình TLS/chứng thực phù hợp.
3. **Lưu trữ an toàn**: encryption at rest theo yêu cầu, quản lý khóa, quyền truy cập, rotation và chống sửa đổi log an ninh.
4. **Retention**: xác định thời gian lưu dựa trên yêu cầu vận hành, pháp lý và bảo mật; áp dụng cả chỉ mục, bản sao, archive và backup.
5. **Xóa/khử dữ liệu**: khi phát hiện secret trong log, có quy trình incident response, cô lập dữ liệu, thu hồi token, điều tra nơi dữ liệu đã được sao chép; chỉ xóa một dòng trên dashboard thường chưa đủ.
6. **Bảo vệ cấu hình log**: thay đổi `logging.properties`, environment variables, JVM flags hoặc collector pipeline phải có review và audit; không bật debug không giới hạn trong production.
7. **Giám sát việc truy cập log**: xem log là tài nguyên nhạy cảm, theo dõi truy cập không đúng quyền.
8. **Không chỉ log ứng dụng**: proxy, gateway, HTTP access logs, WAF, service mesh, APM, traces và error reporting SDK cũng có thể ghi URL/header/body riêng, dù code Java của bạn an toàn.

Log do **JDK nội bộ** hoặc framework tạo có thể bỏ qua bộ lọc allowlist do application tự viết. Để ngăn rò rỉ phải đánh giá **từng nguồn log và sink thực**, không chỉ sửa một method `logger.info`.

## 15. Kiểm thử không lộ bí mật

Một bộ kiểm thử tối thiểu cho HTTP logging nên có:

1. Tạo request với `Authorization`, `Cookie`, API key tùy chỉnh, URL chứa `access_token` và path có định danh nhạy cảm.
2. Gắn **secret sentinel** tổng hợp khác nhau ở từng vị trí; chụp **toàn bộ output** của application logger trong test.
3. Chạy cả nhánh thành công, timeout, HTTP 4xx/5xx, exception, retry, redirect, cancel và response body lỗi.
4. Kiểm tra sentinel **không xuất hiện** trong bất kỳ log nào và field allowlist được ghi đúng.
5. Gửi input có CRLF, chuỗi rất dài, dấu nháy, ký tự điều khiển, Unicode và encoded query để kiểm tra injection.
6. Kiểm tra correlation ID không mang session token hoặc dữ liệu cá nhân và không bị user cung cấp định dạng giả mạo.
7. Bật từng cấu hình debug/logging JDK trong **môi trường thử nghiệm có dữ liệu giả**; xác nhận rủi ro trước khi xem xét dùng production.
8. Kiểm tra collector, trace exporter, APM, gateway và log backups, không chỉ stdout.
9. Kiểm tra event vẫn đủ phục vụ điều tra lỗi: operation, status/error_code, attempt, latency, correlation.
10. Thử tải với nhiều request đồng thời để xác nhận log không chặn quá lâu, không giữ body, queue có giới hạn và retention/rotation hoạt động.

**Ví dụ kiểm tra trong unit test:**

```java
String generatedLog = capturedLogText;
if (generatedLog.contains("synthetic-bearer-secret")) {
    throw new AssertionError("Sensitive token found in logs");
}
```

Đây là **trích đoạn minh họa**, trong đó `capturedLogText` phải là log thực thu được từ test; không tự coi một phép kiểm tra token đơn lẻ là chứng nhận an toàn cho tất cả dữ liệu. Nên tổ chức test theo schema/field allowlist thay vì chỉ dùng blacklist từ khóa.

## 16. Sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| `logger.info(request.toString())` | Có thể lộ URI hoặc metadata | Log event allowlist |
| `logger.info(request.uri().toString())` | Lộ query, user-info, định danh path | Ghi destination alias và route template |
| In toàn bộ `headers.map()` | Lộ Authorization, Cookie, key tùy biến | Không log headers thô |
| Log body khi debug | Có thể lộ PII, mật khẩu, token, dữ liệu nghiệp vụ | Log kích thước/mã lỗi được duyệt |
| Log `exception.getMessage()` khi lỗi | Message có thể chứa URL/token | Mã lỗi chuẩn hóa; stack trace trong kênh được phép |
| Dựa vào regex để che mọi secret | Bỏ sót format khác hoặc encoded values | Allowlist trước, masking bổ sung |
| Log last 4 ký tự của token | Vẫn có nguy cơ rò rỉ một phần credential | Không ghi token; dùng ID độc lập |
| Bật `jdk.httpclient.HttpClient.log=headers` trên production | Logger JDK có thể in header bí mật | Chẩn đoán hạn chế, đánh giá output thực |
| Coi `FINE`/`DEBUG` là vùng miễn trừ bảo mật | Debug log thường bị sao chép/lưu lâu | Cùng tiêu chuẩn bảo mật ở mọi mức |
| Dùng `ThreadLocal` không truyền vào async callback | Event nhầm correlation giữa request | Propagate request context rõ ràng |
| Ghi untrusted string có CRLF | Log injection, giả mạo event | Validate field và dùng encoder structured |
| Chỉ che trên UI dashboard | Secret vẫn ở collector, index, archive, backup | Kiểm soát tại nguồn và toàn pipeline |
| Ghi session ID làm correlation | Có thể cho phép chiếm phiên hoặc theo dõi người dùng | ID độc lập không bí mật |
| Ghi `Location` của redirect | URL có thể chứa token/callback secret | Log redirect status/count |
| Ghi tất cả request liên tục | Tăng chi phí và nguy cơ lộ metadata | Chọn event cần thiết, sampling có kiểm soát |
| Không kiểm tra log từ gateway/APM | Bí mật vẫn bị hệ thống khác ghi lại | Audit mọi thành phần của logging pipeline |

## 17. Bài tập tự đánh giá

**Bài 1.** Một request có URL `https://example.test/reset?token=abc`. Có được ghi `request.uri().getPath()` thay vì `toString()` để bảo đảm không lộ bí mật không?

**Đáp án:** Chưa bảo đảm. `getPath()` không có query nhưng path vẫn có thể chứa email, token hoặc ID. Tốt nhất ghi route template cố định theo operation.

**Bài 2.** Vì sao log một header `Authorization` sau khi thay `Bearer` thành `[MASKED]` vẫn nguy hiểm?

**Đáp án:** Thay đúng chữ `Bearer` không đảm bảo loại hết token, basic auth hoặc dạng credential khác. Không ghi value của header nhạy cảm ngay từ đầu.

**Bài 3.** Khi `sendAsync` thất bại, có nên log nguyên `error.toString()` cho tiện debug không?

**Đáp án:** Không mặc định. Exception có thể chứa endpoint, proxy, query hoặc dữ liệu từ bên ngoài. Log failure code và correlation; nếu bắt buộc giữ stack trace thì dùng kênh được kiểm soát và đánh giá rủi ro trước.

**Bài 4.** `logger.log(Level.INFO, "correlation={0}", new Object[]{requestId})` có tự ngăn log injection không?

**Đáp án:** Không. Parameterized logging giúp tách message template khỏi giá trị, nhưng nếu formatter in CRLF từ `requestId` vào log text thì vẫn có rủi ro. Validate/encode dữ liệu và giới hạn độ dài.

**Bài 5.** Một ứng dụng dùng JDK 11 bật `-Djdk.httpclient.HttpClient.log=headers`. Các bộ lọc trong method log nghiệp vụ có chắc lọc được header JDK ghi ra không?

**Đáp án:** Không. Đây là logger nội bộ riêng của JDK, có thể đi qua logging pipeline khác. Phải đánh giá logger và handler của JDK, không chỉ log method của ứng dụng.

**Bài 6.** Có thể dùng chính bearer token làm correlation ID nếu hash SHA-256 trước không?

**Đáp án:** Không nên coi đó là mặc định an toàn. Hash không khóa của token/định danh có thể tạo ID ổn định, hỗ trợ liên kết hoặc đoán giá trị trong một số ngữ cảnh. Ưu tiên ID độc lập không mang secret; nếu bắt buộc cần pseudonymization thì dùng cơ chế đã đánh giá, quản lý khóa và quyền riêng tư phù hợp.

**Bài 7.** Một request trả HTTP 500. Muốn theo dõi lỗi cần ghi gì?

**Đáp án:** Chẳng hạn `event=http.client.completed`, `operation`, `status_class=5xx`, `duration_ms`, `correlation`. Không cần body lỗi, URL đầy đủ hoặc toàn bộ headers.

## 18. Checklist triển khai và tài liệu chính thức

Trước khi bật log HTTP trong production, kiểm tra:

1. **Đề bài log** rõ ràng: cần tìm lỗi kết nối/timeout hay audit một nghiệp vụ?
2. **Allowlist** có liệt kê chính xác các field được phép, nguồn, kiểu dữ liệu, giới hạn độ dài và retention?
3. **Secrets** (Authorization, Cookie, API key, query, body, user-info, exception message) có bị loại khỏi tất cả level và đường log?
4. **URI** có được thay bằng service alias, route template, operation code?
5. **Correlation** có độc lập với credential và được kiểm tra khi nhận từ bên ngoài?
6. **Async** có truyền context đúng request, không nhầm ThreadLocal giữa tác vụ?
7. **Định dạng** có escaped CRLF/control characters và giới hạn input length bằng encoder phù hợp?
8. **JDK debug flags** có được quản lý và kiểm thử bằng dữ liệu giả, không bật tùy tiện trên production?
9. **Collector/APM/gateway** có tuân thủ cùng chính sách loại secret?
10. **Retention/quyền truy cập/incident response** có áp dụng cho log, archive và backup?
11. **Test có sentinel** ở query, header, body, exception và các nhánh lỗi/retry/redirect?
12. **Monitoring** có đủ event an toàn để điều tra lỗi mà không cần lấy lại dữ liệu bí mật?

**Ghi nhớ:** log HTTP an toàn không phải là “log tất cả rồi xóa bớt”. Hãy **thiết kế dữ liệu log ngay từ đầu**: chỉ lấy metadata cần thiết, cho phép từng field, kiểm tra đầu vào, encode output, bảo vệ pipeline và kiểm thử chứng cứ không rò rỉ. `HttpClient` và `java.util.logging` của Java 11 vẫn được dùng; các API logging và yêu cầu giảm dữ liệu nhạy cảm tiếp tục có giá trị trên JDK hiện đại.

Tài liệu tham khảo chính thức/còn áp dụng:

- [Oracle Java SE 11 — Networking Properties](https://docs.oracle.com/en/java/javase/11/core/java-networking.html): `jdk.httpclient.HttpClient.log`, danh mục log và cấu hình JUL của JDK 11.
- [Oracle Java SE 11 — `HttpClient`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): gửi đồng bộ/bất đồng bộ.
- [Oracle Java SE 11 — `HttpRequest`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html): URI, method, headers và request.
- [Oracle Java SE 11 — `HttpResponse`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): response, status và body.
- [Oracle Java SE 11 — `java.util.logging.Logger`](https://docs.oracle.com/en/java/javase/11/docs/api/java.logging/java/util/logging/Logger.html): parameterized log, levels và handler.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data to exclude, sanitization, log injection, protection, retention.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): không ghi session ID trực tiếp.
- [Oracle Java SE 25 — `Logger`](https://docs.oracle.com/en/java/javase/25/docs/api/java.logging/java/util/logging/Logger.html): đối chiếu API logging vẫn áp dụng trên JDK hiện đại.

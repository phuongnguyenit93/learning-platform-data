# HTTP access log trong ứng dụng web Java

## 1. Khái niệm và mục tiêu

**HTTP access log** là bản ghi metadata của một yêu cầu HTTP tại một điểm xử lý (reverse proxy, gateway, web server/servlet container hoặc ứng dụng). Thông tin cơ bản thường gồm thời điểm, phương thức, endpoint, mã trạng thái, thời gian xử lý và ID đối chiếu. Nó giúp trả lời: “Yêu cầu nào đã đến, được xử lý ở đâu, có thành công không, mất bao lâu và liên hệ với lỗi nào?”

Ví dụ một **access event đã tối giản dữ liệu**:

```json
{
  "event": "http_access",
  "timestamp": "2026-11-10T03:15:30Z",
  "service": "orders-api",
  "method": "GET",
  "route": "/orders/{id}",
  "status": 200,
  "duration_ms": 13,
  "request_id": "req_7c9"
}
```

Đây là dữ liệu minh họa, không phải số đo thực. Trường `route` là **mẫu định tuyến** do ứng dụng kiểm soát, không phải raw URL có ID người dùng, query string hoặc token.

Phạm vi bài học thuộc **Logging trong ứng dụng web Java**:
- Phân biệt access log ở edge, web container và ứng dụng, hiểu vì sao có thể trùng/mất event.
- Chọn schema gồm method, route, status, duration, timestamp, request ID; cân nhắc bytes/IP theo policy.
- Cấu hình Apache Tomcat AccessLogValve và Spring Boot dùng embedded Tomcat/Jetty/Undertow.
- Viết ví dụ Java 17+ nhận request thật bằng `HttpServer` và phát access event an toàn.
- Giải quyết các tình huống lỗi, asynchronous request, reverse proxy, đo latency, giới hạn dữ liệu, lưu trữ, test và vận hành.

## 2. Access log khác application log và tracing ở đâu?

| Nguồn | Ví dụ | Dùng để trả lời |
| --- | --- | --- |
| HTTP access log | `GET /orders/{id} 200 13ms` | Endpoint nào, status gì, latency bao nhiêu? |
| Application log | `order_validation_failed code=INVALID_STATE` | Logic nghiệp vụ nào đã diễn ra? |
| Error log | Exception và stack trace | Vì sao một thao tác lỗi? |
| Distributed trace | Span từ gateway đến database | Thời gian phân bổ giữa service/operation? |
| Metrics | Request duration histogram, RPS, 5xx rate | SLO/alert trên thời gian dài có đạt không? |

Một API có thể vừa phát access log, vừa ghi application log, vừa tạo trace span. Chúng **bổ sung nhau**, không nên thay thế bằng việc in toàn bộ request body để dễ debug.

### Ba lớp tạo access log

```text
Client
  |
  v
Load balancer / API gateway      -> access log A
  |
  v
Web server / Servlet container   -> access log B
  |
  v
Servlet Filter / Controller      -> access log C
  |
  v
Service -> database              -> application logs + traces
  |
  v
HTTP response
```

Điểm khác biệt quan trọng:
- Gateway có thể từ chối request vì auth, rate limit hoặc không có upstream; khi đó chỉ có log A.
- Container có thể từ chối URL không hợp lệ hoặc một số lỗi trước khi vào application filter; B có thể thấy mà C không thấy.
- App filter biết business route/context, nhưng có thể bỏ lỡ lỗi xảy ra trước khi filter hoặc xử lý bất đồng bộ sau khi filter trả về.
- Nếu cả A, B và C đều ghi, **một request có nhiều event**. Dashboard không được cộng chúng như ba request khác nhau.

Xác định **điểm đo chính** cho RPS, error rate và latency. Dùng field như `layer=gateway`/`layer=container` khi cần lưu nhiều lớp để điều tra.

## 3. Thiết kế schema HTTP access log

| Trường | Giá trị minh họa | Cần chú ý |
| --- | --- | --- |
| `timestamp` | UTC ISO 8601 | Wall clock có timezone để đối chiếu sự kiện |
| `service`/`instance` | `orders-api` | Phân biệt nguồn khi scale ngang |
| `method` | GET, POST | Không đưa raw input chưa validate vào text log |
| `route` | `/orders/{id}` | Ưu tiên route template để tránh PII và cardinality |
| `status` | 200, 404, 500 | Mã phản hồi ở **điểm log**, không tự gán 200 |
| `duration_ms` | 13 | Đơn vị và thời điểm bắt đầu/kết thúc phải rõ |
| `request_id` | `req_7c9` | Sinh/xác thực tại ingress hoặc server, không chứa secret |
| `trace_id` | Chuỗi định danh span trace | Chỉ thêm theo chuẩn tracing và policy |
| `response_bytes` | 8192 | Đơn vị/định nghĩa có thể khác server, nén, headers |
| `client_ip` | IP client/proxy | Dữ liệu có thể nhạy cảm; header forwarded phải đáng tin |
| `user_agent`, `referer` | Header do client gửi | Có thể chứa PII, token, CR/LF; không bật mặc định |
| `error_code` | Enum nội bộ | Có ích nếu cần tách 4xx/5xx nghiệp vụ |

Một schema tối thiểu thường giữ **method + route template + status + duration + request/trace ID** và một timestamp. Không biến bảng này thành lệnh thu thập mọi trường; tổ chức phải xác định purpose, retention, quyền đọc, sampling và trách nhiệm theo từng field.

### Status code có ý nghĩa như thế nào?

- **2xx:** request thành công theo hợp đồng HTTP; không nhất thiết mọi công việc backend liên quan đã hoàn tất.
- **3xx:** redirect, cache hoặc phản hồi chuyển hướng.
- **4xx:** lỗi client/chính sách như 400, 401, 403, 404, 409, 429; không coi mọi 4xx là lỗi server.
- **5xx:** lỗi từ server/gateway; cần theo dõi SLO và điều tra.
- **Chưa gửi response:** một API logging có thể trả `-1`/unknown. Không tự động ghi 200 khi chưa commit.

Trên hệ thống sau proxy, gateway có thể trả 502/504 cho client dù ứng dụng đang trả mã khác hoặc chưa kịp trả gì. Khi điều tra phải đọc đúng access log tại tầng phát status.

## 4. Format access log: Common, Combined và JSON

**Common Log Format** thường gồm địa chỉ phía gửi, thông tin truy cập, timestamp, request line, HTTP status và response bytes. **Combined Log Format** bổ sung header như Referer và User-Agent. Dữ liệu từ URL và headers là đầu vào không đáng tin, có thể chứa thông tin nhạy cảm.

Trong Apache Tomcat, `AccessLogValve` hiểu pattern như:

```text
%t %m %U %s %D
```

Các mã ở đây (theo Tomcat 11):
- `%t`: thời điểm request.
- `%m`: HTTP method.
- `%U`: URL path được yêu cầu; **không tự biến thành route template**.
- `%s`: HTTP response status.
- `%D`: thời gian xử lý, **microseconds (µs)**.
- `%T`: thời gian xử lý, **giây**.
- `%q`: query string; cần tránh nếu có token hoặc dữ liệu cá nhân.
- `%r`: request line; không dùng mặc định khi policy yêu cầu không ghi raw request target.

`common` và `combined` tiện cho phân tích traffic, nhưng cần **review trước khi dùng trong production**. Đặc biệt raw path cũng có thể chứa ID người dùng hoặc token khi hệ thống đặt secret trong path. Chỉ bỏ query string không bảo đảm path an toàn.

Structured JSON có schema dễ kiểm tra hơn:

```json
{"event":"http_access","method":"POST","route":"/orders","status":201,"duration_ms":42}
```

Dùng formatter/encoder đúng chuẩn để escape quote, CR/LF và ký tự điều khiển. JSON không tự bảo vệ quyền riêng tư nếu bạn vẫn thêm field `authorization` hoặc toàn bộ request.

## 5. Cấu hình Tomcat AccessLogValve

Tomcat có `org.apache.catalina.valves.AccessLogValve` ghi access log ở tầng container, độc lập với phần lớn logging API trong ứng dụng. **Bật DEBUG cho SLF4J/Logback không tự bật Tomcat access log.**

Ví dụ **đoạn cấu hình tích hợp** đặt trong vị trí Valve hợp lệ của Tomcat (Engine/Host/Context):

```xml
<Valve className="org.apache.catalina.valves.AccessLogValve"
       directory="logs"
       prefix="http_access."
       suffix=".log"
       pattern="%t %m %U %s %D"
       rotatable="true"/>
```

Giải thích:
- `directory`: đường dẫn file, có thể tương đối với `CATALINA_BASE`.
- `prefix` và `suffix`: phần tên file.
- `pattern`: các trường access log; `%U` vẫn là raw URL path.
- `rotatable`: Tomcat có cơ chế xoay file, nhưng retention, quota, ACL, backup và collector vẫn cần thiết kế.
- Nếu dùng nhiều Valve, nên chọn file khác nhau để tránh ghi chồng. Một request có thể được nhiều layer container ghi nếu gắn nhiều Valve.

Tomcat còn có `conditionIf` và `conditionUnless` (lọc có điều kiện theo request attribute). Nếu chọn bỏ health-check, cần kiểm tra rằng 5xx, request bị từ chối trước ứng dụng và những sự cố quan trọng không bị lọc nhầm. `requestAttributesEnabled` liên quan việc lấy IP/protocol/port từ request attributes được cấu hình bởi các Valve như RemoteIpValve.

## 6. Spring Boot: bật access log trên đúng embedded server

Nếu dùng Spring Boot 3.5 với **embedded Tomcat**, file `application.properties` có thể chứa:

```properties
server.tomcat.basedir=./runtime-tomcat
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%t %m %U %s %D
server.tomcat.accesslog.directory=logs
server.tomcat.accesslog.prefix=access.
server.tomcat.accesslog.suffix=.log
```

Trong cấu hình ví dụ, file thường ở `./runtime-tomcat/logs` so với working directory nếu ứng dụng có quyền tạo/ghi. Kiểm tra đường dẫn thực tế của process khi chạy bằng IDE, CI, service manager hay container; `logs` không nhất thiết nằm cạnh JAR. `server.tomcat.accesslog.enabled` điều khiển Tomcat, **không thay thế** `logging.level.*` của application logger.

Với **Undertow**, namespace khác:

```properties
server.undertow.accesslog.enabled=true
server.undertow.accesslog.pattern=%t %a %r %s (%D milliseconds)
server.undertow.options.server.record-request-start-time=true
```

Theo ví dụ cấu hình Spring Boot 3.5, cần `record-request-start-time=true` để có thời gian đáp ứng `%D`, và **`%D` ở đây được biểu diễn bằng milliseconds**, khác Tomcat. Không chuyển pattern qua lại rồi so sánh số latency mà không chuẩn hóa đơn vị.

Với **Jetty** (khi ứng dụng thật sự dùng Jetty):

```properties
server.jetty.accesslog.enabled=true
server.jetty.accesslog.filename=./logs/jetty-access.log
```

Đây là các đoạn cấu hình minh họa theo Spring Boot 3.5; kiểm tra property và hành vi theo **phiên bản Spring Boot/container đang triển khai**. Không bật đồng thời cấu hình Tomcat và giả định nó tác động Jetty/Undertow.

Một hệ thống có gateway và container cùng log nên có schema/layer rõ. Không nhân đôi RPS/error rate khi cùng request xuất hiện ở hai file.

## 7. Ví dụ Java 17+ độc lập: log HTTP request thật

Ví dụ dùng `jdk.httpserver` của JDK, `HttpClient` gửi request đến loopback và `java.util.logging` (JUL) thu access event. Không cần Spring Boot, Maven hoặc thư viện ngoài.

Hành vi cần kiểm chứng:
1. Request `GET /orders/42?token=TEST_ONLY_SECRET` gửi thêm header `Authorization: Bearer TEST_ONLY_SECRET`.
2. Ứng dụng ghi **route template** `/orders/{id}`, không ghi ID 42, raw query hay Authorization.
3. Event chứa method, status thực tế, duration đo bằng clock đơn điệu.
4. Handler trong bộ nhớ chụp `LogRecord` và test assert schema, secret không lộ.
5. Standard output chỉ in kết quả test ổn định, vì thời gian thật thay đổi theo hệ thống.

Tạo file **`HttpAccessLogDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class HttpAccessLogDemo {
    static final Logger ACCESS = Logger.getLogger("demo.http.access");
    static final AtomicReference<LogRecord> CAPTURED =
            new AtomicReference<>();
    static final CountDownLatch LOGGED = new CountDownLatch(1);

    static String route(String path) {
        return path.matches("/orders/[0-9]{1,8}")
                ? "/orders/{id}" : "/unmapped";
    }

    static void handle(HttpExchange exchange)
            throws java.io.IOException {
        long start = System.nanoTime();
        try {
            byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        } finally {
            int code = exchange.getResponseCode();
            long ms = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start);

            String event = "event=http_access method="
                    + ("GET".equals(exchange.getRequestMethod())
                       ? "GET" : "OTHER")
                    + " route="
                    + route(exchange.getRequestURI().getPath())
                    + " status="
                    + (code >= 100 && code <= 599
                       ? Integer.toString(code) : "unknown")
                    + " duration_ms=" + ms;

            ACCESS.info(event);
            LOGGED.countDown();
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        boolean oldParent = ACCESS.getUseParentHandlers();
        Level oldLevel = ACCESS.getLevel();
        ACCESS.setUseParentHandlers(false);
        ACCESS.setLevel(Level.INFO);

        Handler capture = new Handler() {
            @Override public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    CAPTURED.set(record);
                }
            }
            @Override public void flush() {}
            @Override public void close() {}
        };
        capture.setLevel(Level.ALL);
        ACCESS.addHandler(capture);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/orders", HttpAccessLogDemo::handle);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(base
                            + "/orders/42?token=TEST_ONLY_SECRET"))
                    .header("Authorization",
                            "Bearer TEST_ONLY_SECRET")
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> reply = HttpClient.newHttpClient()
                    .send(request,
                          HttpResponse.BodyHandlers.ofString());

            if (!LOGGED.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Access event missing");
            }
            String event = CAPTURED.get().getMessage();

            if (!event.matches(
                    "event=http_access method=GET "
                    + "route=/orders/\\{id\\} status=200 "
                    + "duration_ms=[0-9]+")
                    || event.contains("TEST_ONLY_SECRET")
                    || event.contains("token=")
                    || event.contains("/orders/42")) {
                throw new AssertionError("Unsafe event: " + event);
            }

            System.out.println("http_status="
                    + reply.statusCode());
            System.out.println("access_event_verified=true");
            System.out.println("secret_absent=true");
        } finally {
            server.stop(0);
            ACCESS.removeHandler(capture);
            ACCESS.setLevel(oldLevel);
            ACCESS.setUseParentHandlers(oldParent);
            capture.close();
        }
    }
}
```

JDK 17 trở lên, dùng module `jdk.httpserver`:

```bash
javac --add-modules jdk.httpserver HttpAccessLogDemo.java
java --add-modules jdk.httpserver HttpAccessLogDemo
```

**Standard output chính xác khi môi trường cho phép loopback socket:**

```text
http_status=200
access_event_verified=true
secret_absent=true
```

Một ví dụ access event nội bộ (không phải stdout, duration thực tế có thể khác):

```text
event=http_access method=GET route=/orders/{id} status=200 duration_ms=12
```

### Giải thích code

- `HttpServer` lắng nghe trên `127.0.0.1` với port `0` để OS tự chọn port trống. Không công khai dịch vụ ra internet.
- `HttpClient` gửi request HTTP thật, nhưng chỉ dùng token **giả**; không thử bằng credential thật.
- `getRequestURI().getPath()` chỉ dùng để **kiểm tra với danh sách route do ứng dụng kiểm soát**, không được in trực tiếp. Nếu không khớp, in `/unmapped`.
- `System.nanoTime()` dùng đo **duration**, không dùng làm timestamp wall-clock; kết quả ms không cố định và được test bằng regex.
- `getResponseCode()` trả mã đã được thiết lập bằng `sendResponseHeaders` hoặc giá trị đặc biệt nếu chưa có response. Ví dụ dùng `unknown` thay vì tự gán 200.
- `finally` ghi event ngay cả khi handler gặp lỗi thông thường, nhưng process chết hoặc appender bị lỗi vẫn có thể làm mất log.
- `CountDownLatch` giúp test chờ event đã đến handler; không dùng `Thread.sleep` để đoán thời điểm worker xong.
- `server.stop(0)` và `ACCESS.removeHandler` dọn tài nguyên trong `finally`.

Ví dụ minh họa một GET thành công, **không phải HTTP router hoàn chỉnh**. Để xử lý production, cần mapping method/status/error đúng, xử lý disconnect, timeout và logging framework/collector phù hợp.

## 8. Servlet Filter: ứng dụng nên tự log khi nào?

Trong hệ thống dùng Servlet API, một filter có thể gắn correlation ID, route template và đo thời gian của logic đi qua filter chain. Nhưng không phải mọi request đều đi đến filter:
- Gateway có thể trả 401/403/429 trước khi request tới ứng dụng.
- Container có thể trả 400/404 hoặc lỗi parsing trước khi dispatch.
- Async servlet có thể xử lý **sau khi** `chain.doFilter(...)` trả về; nếu log trong `finally` ngay, status và latency chưa chắc cuối cùng.
- Servlet có dispatcher types `REQUEST`, `ASYNC`, `ERROR`...; filter có thể chạy lại và gây log trùng nếu không kiểm soát.
- Exception handler hoặc error page có thể thay mã status sau bước controller/filter.

Ví dụ phần lõi **chỉ cho xử lý đồng bộ** (cần `jakarta.servlet` API và logger SLF4J, không phải chương trình JDK độc lập):

```java
long started = System.nanoTime();
try {
    chain.doFilter(request, response);
} finally {
    long durationMs = java.util.concurrent.TimeUnit.NANOSECONDS
            .toMillis(System.nanoTime() - started);

    int status = httpResponse.getStatus();
    // Chỉ log field đã được cho phép,
    // lấy route template nếu framework có cung cấp.
    accessLogger.info(
            "event=http_access status={} duration_ms={}",
            status, durationMs);
}
```

`chain`, `request`, `response` và `httpResponse` phải được lấy từ filter đang chạy. Với Servlet async, sử dụng `AsyncListener.onComplete`/`onError`/`onTimeout` hoặc cơ chế completion của framework để đo trạng thái sau khi xử lý kết thúc; tránh log sớm trong `finally` rồi tin đó là số cuối.

Nếu container đã có AccessLogValve, cân nhắc giữ nó làm nguồn chính và chỉ dùng application log cho sự kiện nghiệp vụ. Nếu buộc có cả hai, gắn field `layer` và tránh cộng hai dòng thành hai request.

## 9. Reverse proxy và nguồn IP

Khi Java server đứng sau Nginx/Envoy/load balancer, IP nhìn thấy ở TCP socket thường là IP proxy. Các header `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto` có thể mang thông tin client, nhưng **client không tin cậy có thể tự giả mạo header**.

Nguyên tắc:
1. Chỉ tin forwarded headers khi request đến từ proxy được xác nhận là tin cậy.
2. Ingress phải xóa/chuẩn hóa các header do client tự gửi theo topology của hệ thống.
3. Cấu hình danh sách trusted proxies và cách chọn IP khi có nhiều proxy hops.
4. Nếu dùng Tomcat, nghiên cứu `RemoteIpValve` và `requestAttributesEnabled` của `AccessLogValve` để lấy giá trị đã chuẩn hóa.
5. Kiểm tra behavior bằng request có header giả trong môi trường thử nghiệm, không đánh giá an ninh dựa trên raw `X-Forwarded-For`.

IP cũng có thể là dữ liệu cá nhân trong bối cảnh cụ thể. Đừng giữ dài hơn cần thiết; cần policy, quyền truy cập, retention và tiêu chí redaction phù hợp.

## 10. Request ID, trace ID và quyền riêng tư

Correlation giúp nối các log:

```text
Gateway   request_id=req_7c9 route=/orders/{id} status=200
Tomcat    request_id=req_7c9 status=200
Service   request_id=req_7c9 event=order_loaded
Trace     trace_id=... span_id=...
```

Giá trị client gửi ở `X-Request-ID` không nên được chép nguyên văn vào log nếu không giới hạn ký tự/độ dài. Dùng ID do server/ingress sinh hoặc kiểm tra theo hợp đồng. Không dùng email, token hoặc user input tự do làm ID.

Trong Java, MDC/ThreadContext thường gắn `requestId` vào application log; nhưng khi nhảy thread, dùng executor hay virtual thread, context propagation cần đúng framework. Cleanup context trong `finally` để không trộn request khi tái sử dụng worker. Với access log ở container, cần cơ chế nhận request attributes/trace context đúng backend; không phải lúc nào dữ liệu MDC tự xuất hiện trong Valve.

Không bắt buộc lưu user/tenant ID trong mỗi access event; nếu cần cho bảo mật/analytics, phải có purpose, quyền, retention và biện pháp giảm khả năng tái nhận diện.

## 11. Tính latency và RPS đúng

Một số đại lượng có tên gần giống nhưng ý nghĩa khác:

| Đại lượng | Điểm bắt đầu/kết thúc điển hình |
| --- | --- |
| Server request processing time | Từ nhận/dispatch tại server đến thời điểm hoàn thành ở tầng đo |
| Time to first byte | Đến khi response bắt đầu được gửi/commit |
| Gateway upstream duration | Phần proxy trao đổi với backend |
| Client end-to-end latency | DNS/TLS/network/server/body download của client |

Đừng so latency từ hai nguồn mà chưa xác định **đơn vị, điểm đo, timeout và việc xử lý streaming**.

Ví dụ Tomcat `%D` có đơn vị **microseconds**, code Java ở mục 7 dùng **milliseconds**. Trong cấu hình Undertow minh họa ở Spring Boot, `%D` cũng dùng milliseconds với tùy chọn ghi nhận thời điểm bắt đầu. Nếu nhầm đơn vị, dashboard có thể sai khoảng 1.000 lần.

Metrics hữu ích:
- RPS theo route + method.
- Tỷ lệ 5xx/4xx, phân biệt 401, 403, 404, 429, 502 và 504.
- p50/p95/p99 của duration ở cùng tầng đo.
- Response size và traffic volume, nếu định nghĩa bytes nhất quán.
- Số event generated/accepted/written/dropped khi access log dùng async appender hoặc collector.

**Số dòng access log không luôn bằng số request thật**: có thể do sampling, filter, queue đầy, appender lỗi, stdout log driver mất dữ liệu, hoặc trùng bản ghi ở nhiều layer. Để đo SLO nghiêm ngặt thường cần metrics ở điểm quan sát nhất quán.

## 12. Bảo mật, log injection và chi phí vận hành

Access log nhận rất nhiều field từ nguồn bên ngoài: path, query, User-Agent, Referer, forwarded headers. Chúng có thể chứa CR/LF, chuỗi cực dài, email, token hay dữ liệu riêng tư. **Parameterized logging không tự vô hiệu hóa CRLF injection** nếu plain-text formatter vẫn in newline. Giải pháp:
- Đặt schema rõ và chỉ log field được phép, ưu tiên route template.
- Không log `Authorization`, `Cookie`, `Set-Cookie`, access token, password, body hoặc raw query.
- Validate ID, giới hạn độ dài, escape theo output format và dùng encoder JSON đáng tin cậy.
- Tách data/metadata của client khỏi tên key và log template, tránh cho client quyết định cấu trúc.
- Kiểm tra quyền file/collector, rotation, retention, backup và export.
- Không dùng raw path có secret trong path segment; giải quyết từ thiết kế endpoint hoặc chuyển sang tên route an toàn.

Với hệ thống tải cao:
- Ghi một event/request có thể tạo lượng dữ liệu rất lớn; nhiều tầng càng nhân lên.
- Async logging có thể làm producer trả về sớm nhưng không tăng vô hạn năng lực sink; queue hữu hạn sẽ đầy nếu tạo log nhanh hơn ghi.
- Health-check thường xuyên có thể sampling/loại có điều kiện, nhưng bảo vệ 5xx và dấu hiệu abnormal.
- Theo dõi CPU, latency, queue depth, dropped events, disk/network và collector lag.
- Khi access log phục vụ security/audit, không tùy tiện drop để ưu tiên throughput.

Khi dùng Tomcat `conditionIf`/`conditionUnless` để lọc event, cần test đường request không qua ứng dụng, health-check lỗi và trường hợp attribute không được set, tránh mất những event có giá trị an ninh.

## 13. Kiểm thử access log từ đầu đến cuối

### Unit test schema

Nên kiểm tra:
1. Method nằm trong tập hợp hợp lệ, route là template, status code đúng, duration không âm.
2. Raw URL/query, Authorization/Cookie, email hoặc canary token **không** xuất hiện.
3. Request ID từ client quá dài/chứa CRLF bị thay/thực hiện reject theo policy.
4. Path lạ không bị log nguyên string, không làm nổ cardinality.
5. Event không có response code được biểu diễn là unknown/error, không lặng lẽ biến thành 200.
6. JSON parse được, không bị ký tự client phá dòng/field.

### Integration test HTTP

- Gửi 200, 201, 302, 400, 401, 403, 404, 429 và 500 theo những endpoint có thể tạo ra chúng; kiểm tra status ở tầng đã chọn.
- Kiểm tra request bị gateway chặn không vào application filter.
- Gửi canary query/header/path, quét file/stdout/appender/collector và bản export.
- Nếu dùng async servlet, đo sau completion; kiểm tra không log hai lần ở REQUEST/ASYNC/ERROR dispatch.
- Với client disconnect, upload/streaming lớn, timeout, xác minh server ghi những gì thật sự có thể biết.
- Xác minh request ID/trace ID xuyên các tầng, nhưng không đưa PII vào ID.
- Thử log rotation, restart, quyền file, retention và flush/delivery.
- Đo tình huống collector chậm, queue đầy hoặc sampling để không nhầm log được enqueue với log đã lưu.

Trên JUnit/CI, dùng dữ liệu giả và port do OS cấp như chương trình mục 7. Capture event ở dạng record/JSON, dùng latch/poll có deadline cho xử lý async, tránh `Thread.sleep(100)` hoặc so duration chính xác vì giá trị thay đổi theo máy.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| App có `LOG.info` nhưng không có access log | Container access log chưa bật | Valve/thuộc tính `server.tomcat.accesslog.enabled` |
| Gateway có 401/429 nhưng controller không ghi | Request chưa được chuyển vào app | Edge access log và policy routing |
| Access file nằm sai chỗ | `basedir`/`directory`/working directory khác | Kiểm tra path thực của process |
| Status filter khác status client | Async, error dispatch hoặc gateway thay kết quả | So status tại từng layer |
| Duration rất lớn/nhỏ bất thường | Nhầm đơn vị `%D` hoặc thời điểm kết thúc | Docs đúng backend, chuẩn hóa µs/ms |
| IP chỉ là proxy IP | Forwarded header chưa chuẩn hóa | Trust proxy, RemoteIpValve |
| Một request bị đếm hai lần | Ghi tại proxy + container/filter | Gắn layer, chọn nguồn RPS chính |
| Có token trong URL log | Pattern dùng raw path/query/headers | Chọn route template, allowlist |
| Dòng log bị vỡ bởi input | CRLF/log injection từ User-Agent/path | Validate và escaping |
| Event thiếu/trễ | Async queue, I/O lỗi, shipper lag, shutdown | Metrics và xác minh điểm ghi cuối |
| Filter báo 200 khi thực tế 500 | Response chưa được commit hoặc lỗi xảy ra sau filter | Dùng completion/container log |
| High-cardinality metric | Dùng path ID thật thay vì route template | Chuẩn hóa endpoint trước aggregation |

## 15. Checklist triển khai production

- [ ] Xác định tầng chính cho access log; có kế hoạch xử lý duplicate layers.
- [ ] Schema có timestamp, method, **route template**, status, duration đúng đơn vị, correlation ID.
- [ ] Tránh raw query, Authorization, Cookie, request body và thông tin cá nhân không cần thiết.
- [ ] Kiểm tra raw path và header được escape/giới hạn nếu có lý do bắt buộc ghi.
- [ ] Chỉ tin forwarded headers từ proxy đã xác minh và đã được ingress chuẩn hóa.
- [ ] Test 2xx/3xx/4xx/5xx, lỗi trước app, async, timeout/streaming và disconnect khi cần.
- [ ] Cấu hình đúng server (Tomcat, Undertow hoặc Jetty), path ghi file và quyền dịch vụ.
- [ ] Có rotation, retention, backup và bảo vệ quyền đọc/đăng xuất log.
- [ ] Theo dõi RPS/5xx/p95/p99 từ nguồn đúng, nhận biết sampling/drop/backpressure.
- [ ] Dùng trace/request ID để đối chiếu, nhưng không đưa dữ liệu cá nhân vào ID.
- [ ] Test canary và log injection từ ứng dụng qua collector, không chỉ tại source.
- [ ] Kiểm tra hành vi sau restart, khi collector chậm và khi bật cấu hình debug tạm thời.

## 16. Bài tập thực hành

1. Chạy `HttpAccessLogDemo`. Giải thích vì sao có `http_status=200`, route mẫu và không lộ `TEST_ONLY_SECRET`.
2. Sửa handler để trả 405 cho method không phải GET; phát access log có mã 405 và thêm test tương ứng.
3. Thêm một route khác, không ghi raw path khi không biết route template.
4. Bật access log Tomcat trong một Spring Boot service. Kiểm tra đường dẫn file và `%D` ở microseconds.
5. So sánh request bị gateway trả 429 với request đi vào app trả 200: mỗi tầng có event nào?
6. Gửi `X-Forwarded-For` giả. Giải thích vì sao không thể tin header này trực tiếp.
7. Chạy servlet async; so log tại `finally` của filter với log ở callback completion.
8. Tạo truy vấn/dashboards RPS và p95 theo `route`, loại đếm trùng giữa gateway/container.
9. Gửi URL và User-Agent có dữ liệu giả nhạy cảm, CRLF hoặc text dài; kiểm tra redaction và escaping.
10. Kiểm tra access log sau rotation, archive và collector; ai đọc được và thời hạn lưu bao lâu?

## 17. Ghi nhớ

- **HTTP access log** ghi metadata request/response ở một điểm xử lý web, không phải bản dump HTTP body.
- Reverse proxy, container và filter nhìn thấy những loại request khác nhau; chọn tầng phù hợp và tránh đếm trùng.
- Nên dùng **method, route template, status, duration, timestamp và correlation ID**, với field/privacy policy rõ.
- Trong Tomcat `%D` là **microseconds**; ở ví dụ Undertow của Spring Boot là **milliseconds**. Luôn quy đổi đúng.
- Không tin forwarded headers của client; bảo vệ query, path, Authorization, Cookie và các trường dễ gây log injection.
- Kết hợp access logs với metrics/traces; số event có thể bị duplicate, sampling, drop hoặc trễ.
- Test status lỗi, async, proxy, quyền riêng tư, retention và collector trước khi vận hành production.

### Tài liệu tham khảo

- Apache Tomcat 11 — AccessLogValve: https://tomcat.apache.org/tomcat-11.0-doc/config/valve.html
- Spring Boot 3.5 — Configure Access Logging: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Oracle JDK 21 — HttpExchange: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- Oracle JDK 21 — HttpServer: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

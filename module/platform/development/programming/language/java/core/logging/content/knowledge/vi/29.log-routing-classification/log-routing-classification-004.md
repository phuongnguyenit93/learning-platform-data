# Tách log access trong Java Logging

## 1. Tách log access là gì và vì sao cần?

**Access log** ghi lại việc một client hoặc thành phần khác truy cập dịch vụ, đặc biệt là **HTTP request/response**. Mỗi bản ghi thường cho biết phương thức, đường dẫn hoặc route, mã trạng thái HTTP, thời gian xử lý và một số thông tin tương quan như request ID hoặc trace ID. **Application log** ghi hoạt động bên trong ứng dụng: xử lý nghiệp vụ, trạng thái thành phần, lỗi gọi dependency, retry và exception.

**Tách log access** nghĩa là định tuyến hai loại sự kiện vào các luồng hoặc đích ghi riêng để có thể lọc, lưu trữ, phân quyền và phân tích độc lập. Chẳng hạn:

- `access.log`: một dòng hoặc một sự kiện có cấu trúc cho mỗi HTTP request đã được hệ thống xử lý đến điểm có thể ghi nhận.
- `application.log`: các sự kiện nội bộ của service như “tạo đơn hàng”, “gọi payment”, “payment timeout”.
- `audit.log`, nếu có: các sự kiện kiểm toán cần chính sách tin cậy, quyền truy cập và lưu giữ riêng; **không tự đồng nhất audit với access log**.

Ví dụ một yêu cầu `POST /checkout` nhận HTTP 504 có thể tạo **một access log** và **nhiều application log** mô tả các bước, nhưng cả hai là các góc nhìn khác nhau lên cùng yêu cầu.

```text
Client ─► Gateway ─► Java HTTP server ─► Application ─► Dependency
              │              │                │
              ▼              ▼                ▼
          Gateway         Access log       Application log
          access log      (request)        (nghiệp vụ/lỗi)
                              │                │
                              └──── trace/request ID ────┘
                                       │
                                       ▼
                          Collector / Logging Backend
                           ├── http_access index/stream
                           └── application index/stream
```

**Mục tiêu:** tránh để log lưu lượng HTTP lẫn vào thông điệp nghiệp vụ, dễ tính tỷ lệ mã HTTP/độ trễ, thuận tiện điều tra sự cố và áp dụng chính sách lưu trữ đúng theo loại sự kiện.

## 2. Access log khác application log và audit log ở điểm nào?

| Tiêu chí | Access log | Application log | Audit/security log |
| --- | --- | --- | --- |
| Sự kiện trọng tâm | Lượt truy cập, HTTP request/response | Hành vi xử lý, trạng thái, lỗi nội bộ | Hành động cần kiểm toán hoặc sự kiện an ninh |
| Thời điểm tạo | Thường khi request kết thúc hoặc đạt điểm ghi được | Bất cứ lúc nào trong xử lý | Khi xảy ra hành động được kiểm toán |
| Trường chính | Method, route/path, status, duration, request ID | Logger, level, message, exception, trace ID | Actor, action, outcome, target, thời điểm theo chính sách |
| Số lượng | Có thể gần với số request trên một hop | Có thể 0, 1 hoặc nhiều bản ghi/request | Theo những hành động có yêu cầu kiểm toán |
| Câu hỏi chính | Ai/đi đâu/khi nào/kết quả và độ trễ? | Hệ thống đã làm gì, vì sao lỗi? | Ai làm gì, được phép hay bị từ chối? |
| Retention, quyền | Theo lưu lượng và nhu cầu điều tra | Theo vận hành/debug | Có thể có yêu cầu pháp lý/kiểm soát chặt hơn |

Access log có HTTP status 500 **không tự mang mức logger ERROR**. Một access event có thể được phát ở mức `INFO` với trường `http.status_code=500`, rồi dashboard lọc dựa trên status. Nếu dùng level `ERROR` cho mọi request 5xx, cần một quy ước rõ ràng; đừng dùng level thay hoàn toàn cho trường status.

Tương tự, response `404` không phải lúc nào là lỗi của ứng dụng: có thể là URL sai, crawler, hoặc nghiệp vụ không tìm thấy tài nguyên. Từ access log chỉ biết trạng thái trả về, chưa biết nguyên nhân bên trong.

## 3. Các thuộc tính cần có trong HTTP access log

Một schema có cấu trúc có thể bao gồm:

| Trường | Mục đích | Điểm cần lưu ý |
| --- | --- | --- |
| `timestamp` | Thời điểm sự kiện được ghi nhận | UTC/offset rõ ràng; phân biệt start/end time nếu có |
| `service.name` và `environment` | Định danh dịch vụ/triển khai | Hữu ích với nhiều instance/pod |
| `kind=http_access` | Phân loại sự kiện để routing | Tên do nhóm vận hành quy ước |
| `http.request.method` | `GET`, `POST`, `PUT`, v.v. | Theo giá trị request thực |
| `http.route` | Route đã chuẩn hóa, ví dụ `/orders/{id}` | Ưu tiên để group metric và tìm kiếm |
| `url.path` | Đường dẫn nhận được | Có thể chứa dữ liệu nhạy cảm hoặc ID |
| `http.response.status_code` | HTTP status thực tế | Không suy từ exception đơn lẻ |
| `duration_ms` | Thời gian tại hop đang đo | Nêu rõ bắt đầu/kết thúc và đơn vị |
| `request_id` / `trace_id` | Ghép các sự kiện cùng request/trace | Phải có chiến lược tạo và propagation |
| `client.address` | Nguồn kết nối | Proxy/NAT và forwarded headers ảnh hưởng độ tin cậy |
| `response.bytes` | Kích thước dữ liệu gửi | Nêu rõ có/không gồm HTTP headers |

Tên trường trên là **gợi ý schema**; OpenTelemetry semantic conventions hoặc collector có thể dùng tên, phiên bản và cách ánh xạ cụ thể khác. Điều quan trọng là phân loại nhất quán và có tài liệu schema.

Ví dụ một sự kiện JSONL minh họa:

```json
{"timestamp":"2026-11-10T02:30:00.100Z","service.name":"checkout-api","kind":"http_access","http.request.method":"POST","http.route":"/checkout","http.response.status_code":504,"duration_ms":2501,"trace_id":"4bf92f3577b34da6a3ce929d0e0e4736"}
```

Một event như vậy giúp truy vấn `kind=http_access AND status>=500` mà không phụ thuộc việc application log chứa từ khóa “failed” hay không.

**Độ nhạy cảm dữ liệu:** đường dẫn thực, query string, username, địa chỉ IP, referer và user-agent có thể chứa dữ liệu cá nhân hoặc token. Không tự ghi toàn bộ request body, Authorization header, cookie hoặc query string vào access log. Dùng route template và redaction/allowlist khi có thể.

## 4. Chọn vị trí thu access log trước khi quyết định tách

Access log có thể phát ra từ **reverse proxy/API gateway**, **HTTP server trong ứng dụng** hoặc **middleware/filter**. Mỗi vị trí nhìn thấy một “chặng” khác nhau:

| Vị trí | Quan sát được | Điểm dễ bỏ sót |
| --- | --- | --- |
| Gateway/reverse proxy | Request vào biên, upstream status, một số timing và retry | Không thấy đầy đủ logic bên trong service |
| Embedded HTTP server (ví dụ Tomcat) | Request đến ứng dụng và HTTP response tại server | Không tính toàn bộ thời gian ở gateway/client; chỉ áp dụng cho đúng server |
| Application filter/interceptor | Có thể gắn route, correlation ID và metadata ứng dụng | Async/error dispatch, streaming, lỗi xảy ra trước filter |
| Collector | Routing dựa trên tag/field/file, phân quyền và biến đổi dữ liệu | Không thể tái tạo event chưa từng được ghi ở nguồn |

**Lựa chọn tốt phụ thuộc câu hỏi quan sát.** Muốn biết request bị chặn trước khi tới ứng dụng? Xem gateway access log. Muốn biết đường xử lý đến embedded Tomcat? Xem server access log. Muốn gắn tên route nghiệp vụ và tenant đã được cho phép? Middleware hoặc instrumentation có thể cung cấp thêm trường.

Một HTTP request qua gateway rồi gọi hai microservice có thể xuất hiện **ba access event ở ba hop**. Đây không nhất thiết là ghi trùng: mỗi event mô tả một hop khác nhau. Nhưng nếu cùng một Tomcat request được cả AccessLogValve và custom filter ghi lại ở **cùng một đích**, hệ thống có thể đếm trùng lưu lượng nếu không phân loại rõ.

## 5. Cách 1 — Tách access log bằng embedded Tomcat trong Spring Boot

Với ứng dụng **Spring Boot dùng embedded Tomcat**, có thể bật access log của container. Đây là cơ chế ghi HTTP access ở tầng server, độc lập với lời gọi `logger.info(...)` trong business code. Ví dụ `application.properties`:

```properties
# Chỉ dành cho ứng dụng Spring Boot thật sự đang chạy embedded Tomcat.
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.directory=logs
server.tomcat.accesslog.prefix=access
server.tomcat.accesslog.suffix=.log
server.tomcat.accesslog.pattern=%a %t "%m %U %H" %s %b %D
```

Các token của **Tomcat AccessLogValve** trong mẫu trên:

- `%a`: địa chỉ IP phía remote theo cách container ghi nhận; có thể là proxy nếu không cấu hình xử lý proxy phù hợp.
- `%t`: timestamp của request theo format access log.
- `%m`: HTTP method.
- `%U`: phần URL path; khác `%r` (request line) và không chủ ý lấy query string.
- `%H`: phiên bản giao thức của request.
- `%s`: HTTP response status.
- `%b`: kích thước dữ liệu phản hồi theo định nghĩa của AccessLogValve.
- `%D`: thời gian xử lý request tính bằng **mili giây** đối với mẫu AccessLogValve này.

Ví dụ dòng log chỉ để hình dung định dạng:

```text
192.0.2.10 [10/Nov/2026:09:30:00 +0700] "GET /health HTTP/1.1" 200 17 3
```

Đây là **dòng minh họa**, không phải stdout cố định: địa chỉ, timestamp, byte count và duration phụ thuộc request thật.

**Lưu ý thực tế:**

1. `directory=logs` được Tomcat diễn giải theo **base directory của Tomcat**; không mặc định file sẽ xuất hiện ở `./logs` của thư mục chạy lệnh. Trong container hoặc môi trường tạm, cần kiểm tra đường dẫn cuối và cách mount volume.
2. Tên file access có thể mang ngày và chịu cơ chế quay vòng theo cấu hình Tomcat. Đừng cho nhiều container cùng ghi tùy tiện vào một file chung trên volume mà chưa thiết kế khóa và rotation.
3. Cấu hình `server.tomcat.*` **không áp dụng** khi ứng dụng dùng embedded Jetty, Undertow hoặc Reactor Netty. Với các stack đó phải dùng tính năng và thuộc tính riêng.
4. Phương thức, đường dẫn và mã HTTP được ghi ở tầng server. Nếu cần `http.route` là template `/orders/{id}`, container thường chỉ có đường dẫn request thô; cần thêm instrumentation hoặc bước chuẩn hóa tại collector.
5. `%U` tránh query string theo mẫu trên nhưng **path vẫn có thể chứa dữ liệu nhạy cảm**, ví dụ email hoặc định danh người dùng; phải kiểm tra thiết kế endpoint và chính sách bảo mật.
6. Container access log mô tả request ở hop của Tomcat. Nếu proxy upstream ghi 504 vì timeout trong khi Tomcat cuối cùng ghi 200 cho một xử lý khác hoặc client đã ngắt, hai trạng thái có thể khác nhau; cần xem đúng hop khi điều tra.

Spring Boot vẫn có application log do SLF4J/Logback hoặc backend khác tạo. Khi bật access log container, hệ thống có hai nguồn log riêng từ đầu; collector sẽ cần thu thập đúng file/stream và gắn label phân loại.

## 6. Cách 2 — Dùng logger riêng và định tuyến bằng Logback

Nếu ứng dụng chủ động tạo access event trong một filter hoặc interceptor, đặt tên logger riêng, ví dụ `http.access`, rồi cấu hình appender riêng. Mục tiêu là **định tuyến theo loại sự kiện** mà không bắt mỗi request ghi vào appender application log.

Ví dụ cấu hình **`logback.xml` hoặc `logback-spring.xml`** khi backend là Logback-classic:

```xml
<configuration>
    <appender name="APPLICATION" class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ACCESS" class="ch.qos.logback.core.FileAppender">
        <file>logs/access-app.log</file>
        <append>true</append>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{ISO8601} %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="http.access" level="INFO" additivity="false">
        <appender-ref ref="ACCESS"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="APPLICATION"/>
    </root>
</configuration>
```

Điểm cốt lõi:

- Logger `http.access` gửi event tới appender `ACCESS`.
- `additivity="false"` ngăn event của logger này **tiếp tục chuyển lên appender của root** và bị ghi thêm vào `application.log`. Nếu bỏ thuộc tính này trong cấu hình minh họa, cùng một access event có thể xuất hiện ở cả ACCESS và APPLICATION.
- Các logger ứng dụng không thuộc nhánh `http.access` vẫn đi theo cấu hình root thông thường.
- Cấu hình dùng `FileAppender` để minh họa đường đi. Trong production, thường cần `RollingFileAppender`, rotation/retention, kiểm soát dung lượng và chiến lược lưu log của container.
- File `access-app.log` khác file của Tomcat trong phần trước. Nếu bật **cả** Tomcat access log và custom application access logging cho cùng request, phải phân loại và loại trùng khi tính request count hoặc chỉ chọn một nguồn làm chuẩn.
- Muốn JSONL, hãy dùng encoder/formatter JSON tương thích với phiên bản backend thay cho pattern văn bản, và chuẩn hóa trường `kind=http_access`.

Ví dụ lời gọi logger access trong Java dùng **SLF4J**:

```java
// Đoạn mã minh họa: ứng dụng phải có dependency SLF4J + backend.
private static final org.slf4j.Logger ACCESS =
        org.slf4j.LoggerFactory.getLogger("http.access");

// Gọi ở điểm kết thúc request, với dữ liệu đã kiểm tra và làm sạch.
ACCESS.info("method={} route={} status={} duration_ms={}",
        "POST", "/checkout", 504, 2501);
```

Đoạn trên **không phải một chương trình Java độc lập** và không tự tạo access event cho mỗi request. Nó chỉ minh họa cách phát một event theo logger name; còn thời điểm, phạm vi HTTP, status, duration và handling async phải được hệ thống đo đúng.

### Vì sao phải cẩn thận với appender additivity?

Trong Logback, logger phân cấp theo tên, ví dụ `http.access` nằm dưới `http` và cuối cùng là root. Nếu access logger có appender riêng nhưng vẫn additive, event còn có thể được chuyển tiếp tới các appender ở logger cha. Tách file mà quên additivity tạo **hai bản ghi vật lý** cho một sự kiện và tăng dung lượng, chi phí ingest, thậm chí tạo cảnh báo lặp.

Tuy nhiên, `additivity=false` không phải “công tắc chống trùng tuyệt đối”: nếu hai middleware khác nhau cùng phát event, hoặc một request được log ở gateway và application, vẫn có nhiều event. Cần phân biệt **trùng vì route appender** với **nhiều sự kiện đúng theo nhiều hop**.

## 7. Sinh access event ở thời điểm nào?

Access event nên phản ánh **kết quả mà thành phần đo thực sự quan sát được**. Luồng HTTP đơn giản:

```text
Request vào
   │
   ▼
Ghi nhận thời điểm bắt đầu, request ID
   │
   ▼
Authentication → routing → handler → response
   │
   ▼
Xác định status, duration, kích thước phản hồi (nếu có)
   │
   ▼
Phát đúng một access event cho hop đang đo
```

Khi tự viết Servlet Filter cho ứng dụng dùng Spring MVC/Servlet:

- Bắt đầu bằng `System.nanoTime()` để đo elapsed time; tránh tính chênh bằng wall clock dễ gặp điều chỉnh đồng hồ.
- Sử dụng `HttpServletResponse.getStatus()` ở thời điểm thích hợp, **không** suy status chỉ từ việc có exception.
- Đặt phát log trong `finally` để không bỏ qua nhánh lỗi mà filter thực sự quan sát, nhưng lưu ý exception có thể được error handler đổi thành status khác **sau khi filter trả về**.
- Không mặc định `finally` của filter là thời điểm response đã hoàn tất. Với **async dispatch**, streaming, SSE và WebSocket, vòng đời request có thể tiếp diễn sau khi lời gọi filter ban đầu kết thúc. Khi cần thời điểm hoàn tất cuối cùng, sử dụng container access log hoặc cơ chế lifecycle/`AsyncListener` được thiết kế và kiểm thử.
- Một số request bị chặn trước filter của ứng dụng hoặc ở gateway. Filter không thể ghi những request chưa đến nó.
- Giữ nguyên tính đúng đắn khi filter được gọi nhiều lần do error/async dispatch; cần chính sách “một event cho mỗi request/hop” có khóa nhận diện rõ.

Ví dụ Servlet Filter **minh họa phạm vi đồng bộ** (dùng Spring Boot 3 với Jakarta Servlet và SLF4J, không chạy độc lập):

```java
@Component
public class AccessLogFilter extends OncePerRequestFilter {
    private static final org.slf4j.Logger ACCESS =
        org.slf4j.LoggerFactory.getLogger("http.access");

    @Override
    protected void doFilterInternal(
            jakarta.servlet.http.HttpServletRequest request,
            jakarta.servlet.http.HttpServletResponse response,
            jakarta.servlet.FilterChain chain)
            throws jakarta.servlet.ServletException, java.io.IOException {

        long started = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMs =
                    java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started);

            ACCESS.info("method={} path={} status={} duration_ms={}",
                    request.getMethod(),
                    request.getRequestURI(),
                    response.getStatus(),
                    elapsedMs);
        }
    }
}
```

Để biên dịch đoạn này cần các `import` cho `org.springframework.stereotype.Component` và `org.springframework.web.filter.OncePerRequestFilter` cùng dependency Spring Boot Web; đây là trích đoạn phụ thuộc framework. Ví dụ **chưa xử lý hoàn chỉnh** async completion/error dispatch, chưa chuẩn hóa path thành route và chưa che dữ liệu nhạy cảm. Không dùng nguyên xi làm thiết kế production cho SSE, async hoặc dữ liệu riêng tư; những trường hợp đó nên dùng server instrumentation hoặc lifecycle hook đã kiểm thử.

Nếu endpoint là `/orders/42`, ghi trực tiếp `request.getRequestURI()` sẽ chứa ID thực; để phân nhóm và tránh lộ dữ liệu nên dùng route template như `/orders/{id}` khi framework đã xác định được route, hoặc chính sách chuẩn hóa hợp lệ ở collector.

## 8. Java 17 chạy độc lập: hai luồng log có định tuyến riêng

Ví dụ này dùng **java.util.logging (JUL)** có sẵn trong JDK để thấy rõ cơ chế tách event dựa trên logger. Để đầu ra xác định và không ghi file phụ thuộc máy chạy, hai handler ghi vào **hai vùng đệm riêng**, cuối cùng in từng vùng như thể đó là nội dung của `access.log` và `application.log`.

Đây là mô phỏng **routing**, không phải HTTP server và không phải cấu hình Logback. Trong thực tế, thay vùng đệm bằng FileHandler hoặc appender phù hợp.

Lưu file **`AccessLogRoutingDemo.java`**:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class AccessLogRoutingDemo {
    private static final class BufferHandler extends Handler {
        private final StringBuilder lines = new StringBuilder();

        BufferHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                lines.append(record.getMessage()).append('\n');
            }
        }

        @Override
        public void flush() {
            // Dữ liệu đang nằm trong StringBuilder của ví dụ.
        }

        @Override
        public void close() {
            flush();
        }

        String content() {
            return lines.toString();
        }
    }

    public static void main(String[] args) {
        Logger access = Logger.getLogger("http.access");
        Logger application = Logger.getLogger("app.business");

        // Không chuyển tiếp event tới handler của logger cha/root.
        access.setUseParentHandlers(false);
        application.setUseParentHandlers(false);
        access.setLevel(Level.INFO);
        application.setLevel(Level.INFO);

        BufferHandler accessSink = new BufferHandler();
        BufferHandler applicationSink = new BufferHandler();
        access.addHandler(accessSink);
        application.addHandler(applicationSink);

        try {
            application.info("Payment request started");
            application.severe("Gateway timeout");

            // HTTP status là một trường dữ liệu, không nhất thiết là log level.
            access.info("POST /checkout status=504 duration_ms=2501");
            access.info("GET /health status=200 duration_ms=2");

            System.out.println("=== access.log ===");
            System.out.print(accessSink.content());
            System.out.println("=== application.log ===");
            System.out.print(applicationSink.content());
        } finally {
            access.removeHandler(accessSink);
            application.removeHandler(applicationSink);
            accessSink.close();
            applicationSink.close();
        }
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac --release 17 AccessLogRoutingDemo.java
java AccessLogRoutingDemo
```

Stdout chính xác:

```text
=== access.log ===
POST /checkout status=504 duration_ms=2501
GET /health status=200 duration_ms=2
=== application.log ===
Payment request started
Gateway timeout
```

**Vì sao không bị trộn?** Hai logger gắn với hai handler riêng; `setUseParentHandlers(false)` ngăn chúng chuyển tiếp lên root. Event mang status 504 vẫn đi qua `access.info(...)` vì **HTTP status và JUL log level là hai khái niệm độc lập**.

**Giới hạn của ví dụ:** `StringBuilder` không được thiết kế để nhiều thread ghi đồng thời; chương trình phát log tuần tự một luồng nên kết quả xác định. Logging production cần thread-safe appender/handler, rotation, I/O error handling, queue/flush/shutdown và cấu trúc trường phù hợp; không dùng ví dụ này làm hệ thống logging thực.

## 9. Tách ở collector bằng tag, file path hoặc trường kind

Nếu ứng dụng và container đã tạo hai file, collector có thể chuyển chúng tới stream/index khác. Ví dụ sơ đồ (mang tính khái niệm, không phải cấu hình có thể chạy của một collector cụ thể):

```text
logs/access*.log          ─┐
                            ├─► parser access → kind=http_access
logs/application*.log     ─┘
                              parser app    → kind=application
                                            │
                                            ▼
                                route theo kind/service/env
                                  ├─ access stream
                                  └─ application stream
```

Các quy tắc cần bảo đảm:

1. **Nguồn được nhận diện rõ** bằng tên file, container stream label hoặc trường `kind`. Một file chứa cả hai loại chỉ phân biệt qua từ khóa trong message sẽ khó xử lý hơn structured logs.
2. **Parser theo đúng định dạng nguồn.** Tomcat access pattern không phải JSON; đừng cấu hình JSON parser cho một dòng văn bản dạng access log.
3. **Trường cần cho truy vấn phải được chuẩn hóa**: method, route, status, duration, trace ID (nếu thực sự có). Có đơn vị đo rõ ràng và không đổi đơn vị giữa các dịch vụ.
4. **Một event không vô tình đi vào nhiều tuyến giống nhau** do nhiều rule khớp hoặc do cả file tailer và stdout collector đọc cùng một dữ liệu.
5. **Retention và quyền truy cập khác nhau** cho access, application và audit. Đồng thời bảo đảm logs vẫn có thể được correlate khi điều tra.
6. **Ghi nhận ingestion error và dropped events** để biết một dòng access bị mất trước khi tới backend, thay vì giả định mọi request có bản ghi.

Nếu hệ thống chạy container/orchestration và ứng dụng ghi ra stdout, có thể định tuyến theo **structured field** thay vì tạo file riêng. “Tách” về mặt logic trong logging backend vẫn hữu ích dù vật lý cùng stdout. Lựa chọn phụ thuộc khả năng thu gom, vận hành và mức cô lập mong muốn.

## 10. Gắn request ID và trace ID giữa hai loại log

Tách luồng lưu trữ không có nghĩa tách khỏi quá trình điều tra. Hai luồng nên có khóa nối chung, ví dụ:

```text
access:
2026-11-10T02:30:00Z POST /checkout status=504 trace_id=4bf92f...

application:
2026-11-10T02:29:58Z ERROR payment gateway timeout trace_id=4bf92f...
```

Đây là bản rút gọn minh họa; hệ thống thực tế nên giữ **trace ID đầy đủ** và span ID nếu có.

Với Java và OpenTelemetry:

- Instrumentation HTTP server có thể tạo hoặc tiếp nhận trace context theo quy tắc tin cậy, rồi truyền trong request scope.
- Application log có thể mang `trace_id`/`span_id` qua MDC hoặc structured logging integration.
- Custom access event có thể lấy trace context **đang hoạt động và hợp lệ** ở đúng thời điểm xử lý; container access log thô thường không có trường trace ID tự động.
- Nếu chỉ ghi thẳng header `traceparent` hay `X-Request-ID` do client cung cấp, đó là **dữ liệu đầu vào chưa đáng tin**, không tự biến thành ID canonical của hệ thống; cần kiểm tra, giới hạn chiều dài và tránh log injection.
- Với request qua gateway và nhiều service, mỗi hop có thể có access event riêng. Dùng `trace_id` + `service.name` + hop/timestamp để nối, nhưng không giả định một trace luôn ứng với một HTTP request duy nhất.

Một số backend lưu request ID và trace ID theo tên trường khác; cần quy ước rõ trong ingestion pipeline. Đừng đưa trace ID hoặc request ID thành nhãn metrics không giới hạn cardinality.

## 11. Tính số lượng request và độ trễ từ access log

Ví dụ, một access stream chứa các event đã chuẩn hóa với các thuộc tính `route`, `status` và `duration_ms`. Có thể tính:

- Tổng request được **ghi nhận tại hop đang đo**.
- Số và tỷ lệ HTTP `4xx`, `5xx` (theo ý nghĩa status), tách theo route/method/env.
- Phân bố độ trễ (p50, p95, p99) theo đúng điểm bắt đầu/kết thúc đo.
- Lưu lượng theo thời gian, top route, request chậm, các đợt tăng lỗi sau deploy.

Ví dụ dữ liệu minh họa:

| Route | Status | Duration |
| --- | ---: | ---: |
| `GET /orders/{id}` | 200 | 12 ms |
| `GET /orders/{id}` | 200 | 18 ms |
| `POST /checkout` | 504 | 2501 ms |
| `GET /health` | 200 | 2 ms |

Nhìn các dòng này có thể nhận biết một response 504 chậm, nhưng **không kết luận** payment gateway là root cause nếu chưa đọc application log, trace và thông số upstream. Access log giỏi mô tả triệu chứng ở ranh giới HTTP, application log giúp hiểu tiến trình bên trong.

Để tính tỷ lệ và phân vị tin cậy, phải:

1. Chọn **một nguồn/hop chuẩn** cho mẫu thống kê. Không cộng thẳng log gateway và Tomcat cho cùng request.
2. Xử lý retry: một hành động của người dùng có thể tạo nhiều HTTP request, đặc biệt qua proxy hoặc client retry.
3. Kiểm tra sampling và dòng bị mất. Nếu chỉ ghi một mẫu request thành công nhưng giữ toàn bộ lỗi, tỷ lệ lỗi tính trực tiếp từ log sẽ bị thiên lệch.
4. Phân biệt 200 do gateway trả về, 200 do service trả về và request bị chặn trước service.
5. Hiểu giới hạn timestamp/duration của nguồn; streaming và client abort có thể không phù hợp với diễn giải “latency xử lý nghiệp vụ”.

Các metric sinh trực tiếp từ HTTP server instrumentation thường phù hợp hơn để đo tỷ lệ, còn access log giữ chi tiết cho từng request; cả hai bổ trợ lẫn nhau.

## 12. Bảo vệ thông tin trong access log

Access log thường được ghi với lưu lượng cao và chia sẻ cho đội vận hành, nên cần hạn chế dữ liệu ngay từ điểm tạo log.

**Không đưa mặc định** các thông tin sau vào access log:

- `Authorization`, `Cookie`, token, session ID, API key, mật khẩu.
- Request/response body, đặc biệt nội dung thanh toán, hồ sơ cá nhân hoặc dữ liệu y tế.
- Query string nguyên vẹn: URL có thể chứa `token` hoặc tham số nhạy cảm.
- Route path thô có email, số giấy tờ hoặc dữ liệu định danh khi có thể dùng template.
- Header bất kỳ do client gửi chỉ vì “dễ debug”; `User-Agent` và `Referer` cũng có thể chứa dữ liệu ngoài ý muốn hoặc ký tự điều khiển.

Địa chỉ IP, thời điểm, route và mã phản hồi cũng có thể là dữ liệu cá nhân khi liên kết với nhau; áp dụng retention, access control, giới hạn xuất dữ liệu và chính sách xử lý phù hợp. Nếu cần lưu IP cho bảo mật, xác định rõ mục đích và thời gian lưu.

**Client IP sau proxy:** `X-Forwarded-For` có thể bị client giả mạo nếu ứng dụng tin mọi header. Chỉ dùng địa chỉ được suy ra từ chuỗi proxy đáng tin hoặc từ cấu hình server/gateway phù hợp; không lấy phần tử đầu tùy ý rồi coi đó là “IP thật”.

**Log injection:** đường dẫn, method custom, user-agent hoặc header chứa ký tự xuống dòng/điều khiển có thể phá cấu trúc log văn bản. Encoder có cấu trúc, escape và allowlist trường giúp tránh tạo nhiều dòng giả. Không cho một chuỗi đầu vào chưa kiểm tra quyết định tên file hoặc tên stream.

## 13. Vấn đề hiệu năng, lưu trữ và độ tin cậy

Access log có thể phát ra **mỗi request**, kể cả health check, request lỗi, static asset hoặc traffic bot. Khi lưu lượng lớn, ghi log dễ trở thành tải I/O đáng kể.

- **Dung lượng:** dự tính số request/ngày × kích thước event trung bình × thời gian lưu; kiểm tra quota, rotation và tốc độ tăng.
- **Lọc traffic:** có thể cân nhắc bỏ/giảm log health check hoặc static asset, nhưng phải biết điều đó làm số lượng request trong log thấp hơn traffic thật; đừng dùng mẫu đã lọc để tính tỷ lệ tổng mà không hiệu chỉnh.
- **Sampling:** mẫu một phần request có thể hỗ trợ debug ở lưu lượng lớn, nhưng không tự bảo đảm thống kê chính xác và có thể che dấu sự kiện hiếm.
- **Async appender:** giúp giảm thời gian chờ ghi log trong một số trường hợp; queue đầy có thể block hoặc drop. Cần đếm event mất và quan sát độ trễ từ event đến sink.
- **File rotation:** file access thường lớn hơn application log; đặt lịch quay vòng, dung lượng và retention riêng. Tránh nhiều process ghi đồng thời vào cùng một đường dẫn mà không có thiết kế phù hợp.
- **Failure:** đầy đĩa, thiếu quyền, collector ngừng, network timeout và process crash đều có thể gây mất log. “Response thành công” không đồng nghĩa access event đã lưu bền vững.

Nếu access log được dùng làm chứng cứ audit hoặc tính phí, cần thiết kế một đường ghi bền vững/đối soát theo yêu cầu nghiệp vụ; log file vận hành thông thường hiếm khi có bảo đảm giao dịch exactly-once.

## 14. Các tình huống dễ nhầm khi điều tra

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Mỗi request có hai access event giống nhau trong một file | Tomcat access log và custom filter cùng ghi, hoặc collector đọc cùng file hai lần | Kiểm tra nguồn, logger/appender, collector và event ID |
| Access event chui vào `application.log` | Logger access vẫn additive lên root trong Logback | Dùng logger name riêng, kiểm tra `additivity=false` và appender refs |
| Gateway có 504, service không có 504 | Gateway timeout/chặn trước service, service trả mã khác hoặc request bị ngắt | Đối chiếu hop, trace/request ID, proxy timeout |
| Service có application ERROR nhưng không có access event | Lỗi xảy ra ngoài HTTP, request chưa hoàn tất, access logging bị tắt hoặc pipeline mất dữ liệu | Xác định loại tác vụ và lifecycle request |
| Có access 200 nhưng client báo lỗi | Proxy/client lỗi sau server, buffering hoặc khác biệt hop | Kiểm tra log client, gateway và server |
| Lọc riêng access log nhưng dashboard traffic tăng gấp đôi | Đếm cả gateway và application cho cùng request | Chọn một hop canonical hoặc phân nhóm theo hop |
| Tomcat tạo file ở vị trí bất ngờ | `directory` tương đối với Tomcat base directory | Xem đường dẫn thực và cấu hình container |
| Access log không có trace ID | Container access log chưa được instrument/không được chèn correlation field | Kiểm tra cách tạo context và schema tại điểm phát |
| Client IP sai khi qua reverse proxy | Đọc IP kết nối proxy hoặc tin header chưa xác thực | Cấu hình trusted proxy, xác minh dải IP tin cậy |
| Log có path/query nhạy cảm | Dùng request line/URI thô mà không có quy tắc dữ liệu | Dùng route template, bỏ query, redact theo allowlist |
| Latency của access thấp hơn tổng thời gian client thấy | Đo ở service khác đo ở gateway/client | So điểm bắt đầu/kết thúc, retry, network và queueing |
| Sau restart mất access log | Đường dẫn trong container tạm, không mount hoặc retention quá ngắn | Kiểm tra volume, lifecycle, file shipper |
| Mất log khi tải cao | Queue/backpressure, file I/O, collector drop | Theo dõi dropped/failed writes và tải sink |

## 15. Kiểm thử việc tách access log

Một kế hoạch thử có ý nghĩa nên bao gồm:

1. **Happy path:** gọi `GET /health` trả 200; xác nhận đúng một access event ở nguồn/hop đã chọn và không xuất hiện trong application sink vì route appender.
2. **Lỗi HTTP:** gọi endpoint sinh 4xx và 5xx trong môi trường thử; xác nhận access event có status thực, kể cả khi ứng dụng không ghi application ERROR.
3. **Log nghiệp vụ:** phát ứng dụng `INFO` và `ERROR`; xác nhận hai event này đi application sink mà không chui vào access sink.
4. **Correlation:** một request có log nghiệp vụ; xác nhận ID tương quan hợp lệ ghép được hai loại log.
5. **Trùng lặp:** nếu gateway, Tomcat và custom filter đều được bật, thống kê per-hop và xác nhận dashboard không cộng sai mẫu.
6. **Async/error dispatch:** kiểm thử request bất đồng bộ, request ném exception, streaming và client abort để xem event được phát một lần ở điểm nào.
7. **Dữ liệu nhạy cảm:** gửi query có giá trị giả nhạy cảm; xác nhận token/header/body không được đưa vào access log; kiểm tra escape ký tự.
8. **Tải cao:** đo queue depth, số event bị drop, thời gian ghi, file rotation và độ trễ nghiệp vụ khi bật access logging.
9. **Deploy/restart:** kiểm tra file/stream vẫn tồn tại theo chính sách volume, collector parse đúng và retention thực tế.
10. **Quyền:** người được phép xem access log/trace và người không được phép được phân biệt theo chính sách hệ thống.

Ví dụ điều kiện chấp nhận cho một service có appender ACCESS và APPLICATION:

```text
Request POST /checkout trả 504
→ ACCESS: 1 event, có method, route, status=504, duration
→ APPLICATION: 0..N event tùy các thao tác/lỗi thực tế
→ ACCESS event không được tự động lặp trong APPLICATION sink
→ Correlation ID đúng trên cả hai khi instrumentation cung cấp
```

**Không ép số application log phải bằng số HTTP request.** Có request hoàn toàn bình thường không cần log nghiệp vụ; một request phức tạp lại cần nhiều log.

## 16. Lựa chọn triển khai theo tình huống

| Tình huống | Lựa chọn thường phù hợp | Việc cần kiểm chứng |
| --- | --- | --- |
| Spring Boot + Tomcat, cần access log HTTP cơ bản | Embedded Tomcat AccessLogValve | File thực, status, elapsed, retention, source |
| Cần route template và metadata nghiệp vụ | App instrumentation/filter có lifecycle phù hợp | Async/error completion, privacy, trace propagation |
| Có gateway bảo vệ nhiều service | Gateway access log làm nguồn traffic tại biên | Retry, upstream/hop, sự kiện bị chặn |
| Đã có event phân loại JSON trên stdout | Collector route theo `kind` và service | Parser, nhãn, không double-ingest |
| Muốn file riêng cho access logger | Logger riêng và Logback appender, `additivity=false` | Lệch cấu hình, rollover, file permissions |
| Có yêu cầu audit bền vững | Cơ chế audit/event store có bảo đảm riêng | Tính toàn vẹn, quyền, retention, đối soát |

Không có một cách đúng cho mọi kiến trúc. Hãy xác định **nơi phát sinh HTTP event**, **nguồn chính thức dùng thống kê**, **đích lưu trữ**, **khoá tương quan** và **yêu cầu bảo mật** trước khi bật thêm logger hoặc collector.

## 17. Checklist và nguyên tắc ghi nhớ

- Đã phân biệt access, application và audit log theo **sự kiện**, không chỉ theo tên file.
- Đã quyết định nguồn access cho mỗi hop và tránh đếm hai lần một HTTP request.
- Mọi access event có method, route/path được xử lý an toàn, status, duration và timestamp có ý nghĩa rõ.
- Access logger/appender có đường đi riêng; với Logback đã xử lý additivity.
- Đã xác minh cấu hình Tomcat chỉ áp dụng cho ứng dụng thực sự dùng Tomcat; biết file nằm ở đâu.
- Nếu tự phát access event trong filter, đã xử lý async, error dispatch và response completion phù hợp.
- Đã có request/trace ID tin cậy để ghép với application log mà không chép nguyên header chưa kiểm tra.
- Không lưu token, cookie, Authorization hoặc body mặc định; đường dẫn/headers được kiểm soát.
- Retention, rotation, quyền xem và cảnh báo ingestion failure được cấu hình riêng khi cần.
- Dashboard đo lưu lượng từ một hop thống nhất; ứng dụng và gateway có thể có mã HTTP khác nhau.
- Đã kiểm tra endpoint thường, 4xx/5xx, restart, traffic cao và collector parser.

**Ghi nhớ:** tách log access là **định tuyến và quản trị riêng sự kiện truy cập HTTP** khỏi log vận hành bên trong Java. Access log cho biết **request nào tới đâu, kết quả và độ trễ ở một hop**; application log giúp tìm **điều gì xảy ra bên trong**. Giữ schema và ID tương quan chung để hai luồng bổ trợ nhau trong điều tra sự cố.

### Tài liệu tham khảo

- [Apache Tomcat — AccessLogValve và pattern](https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html#Access_Logging)
- [Spring Boot — Embedded web servers / access logging](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Logback — Architecture và additivity](https://logback.qos.ch/manual/architecture.html)
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html)
- [Java 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)

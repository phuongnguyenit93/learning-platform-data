# Kiểm tra sau triển khai hệ thống logging Java trên production

## 1. Mục tiêu của kiểm tra sau triển khai

**Kiểm tra sau triển khai** (post-deployment verification) là quy trình xác nhận rằng cấu hình logging và đường vận chuyển log **thực sự hoạt động trên bản phát hành mới**, không chỉ đúng trong source code hoặc môi trường test. Một service có thể khởi động thành công, trả HTTP 200 và vượt readiness probe nhưng **vẫn không gửi được log** vì logger level sai, appender không được nạp, file không có quyền ghi, agent chưa đọc được stdout/file, collector bị từ chối hoặc dữ liệu chưa thể tra cứu ở backend.

Với ứng dụng Java dùng JUL, SLF4J, Logback, Log4j 2 hoặc OpenTelemetry, mục tiêu là xác minh **end-to-end** theo những ranh giới được xác định rõ:

```text
Thực thi nghiệp vụ / smoke request
           |
           v
Logger nhận lời gọi
           |
           v
Backend tạo/format event
           |
           v
Console / file / appender / OTLP exporter
           |
           v
Agent / Collector nhận và xử lý
           |
           v
Backend lưu/index log
           |
           v
Explore / dashboard truy vấn được
           |
           v
Alert / runbook hoạt động theo chính sách
```

Một lệnh `logger.info(...)` thành công chỉ chứng minh **đường code đó đã chạy**; nó chưa chứng minh event đã vào file, được shipper nhận hoặc xuất hiện trên dashboard. Ngược lại, dashboard trả “No data” cũng chưa đủ để kết luận ứng dụng không ghi: có thể sai label, timezone, quyền truy vấn, sampling, ingestion delay hoặc retention.

Sau bài này, người học có thể:
- Xác định các tiêu chí nghiệm thu logging trước khi rollout.
- Kiểm tra runtime log level, formatter, appender, file/stdout, cấu hình Java và môi trường.
- Dùng canary event **không nhạy cảm** để kiểm tra từ nguồn đến điểm lưu trữ, bao gồm độ trễ.
- Kiểm tra correlation ID/trace ID, status, route, tên service, version và tính nhất quán schema.
- Đánh giá queue, retries, dropped logs, collector metrics, rotation và khả năng rollback.
- Thực hiện một smoke test Java 17+ độc lập với HTTP server và handler ghi log trong bộ nhớ.
- Thiết kế CI/CD gate, checklist, bằng chứng kiểm thử và quy trình xử lý khi log pipeline thất bại.

Bài thuộc nhóm **Vận hành production**. Các thao tác trực tiếp trên production cần tuân theo quyền và change window được phê duyệt. Không bật DEBUG toàn hệ thống, không thử làm mất collector và không gửi token thật chỉ để “xem log”.

## 2. Khi nào cần chạy kiểm tra?

Không chỉ sau một bản release lớn. Nên kiểm tra khi:
1. Deploy version mới của ứng dụng, thêm dependency hoặc thay cấu hình Spring Boot/JVM.
2. Thay `logback-spring.xml`, `log4j2.xml`, `logging.properties`, encoder hoặc level.
3. Thay image/container runtime, user/UID, mount hoặc đường dẫn log.
4. Thay collector, agent, sidecar, OTLP endpoint, TLS, credential hoặc network policy.
5. Chuyển file logging sang stdout, từ stdout sang OTLP hoặc đổi nhà cung cấp log storage.
6. Thay sampling, masking, retention, parser, index labels hoặc dashboards/alerts.
7. Scale số replicas, rollout canary/blue-green hoặc thay chiến lược xử lý request async.
8. Sau incident liên quan thiếu log, duplicate event, mất trace correlation hay lộ dữ liệu.

**Nguyên tắc vận hành:** kiểm tra logging như một phần của tiêu chí release, không phải bước “khi rảnh mới xem”. Một release có chức năng nghiệp vụ đúng nhưng mất toàn bộ log vận hành/kiểm toán có thể không đáp ứng chính sách an toàn.

## 3. Chuẩn bị trước khi kiểm tra: biết mình cần thấy gì

Trước khi triển khai, ghi lại **hợp đồng quan sát** của service:

| Hạng mục | Ví dụ giá trị | Tiêu chí nghiệm thu |
| --- | --- | --- |
| Service, environment | `orders-api` / `prod` | Log đúng nguồn, không lẫn staging |
| Deployment identity | image digest, version, commit ID | Event mới gắn được với bản phát hành |
| Log level hiệu lực | root INFO, component WARN | Không bị tắt ERROR hoặc bật DEBUG nhầm |
| Sink | stdout, rolling file hoặc OTLP | Có lối vận chuyển hoạt động |
| Event schema | `event`, `service`, `status`, `route`, `duration_ms` | Parse được, đúng kiểu và đơn vị |
| Correlation | `correlation_id` và/hoặc W3C `trace_id` | Có thể đi từ request đến event/trace |
| Ingestion freshness | Theo SLO nội bộ | Canary xuất hiện trong thời hạn được duyệt |
| Log loss | 0 dropped events cho đường bắt buộc | Có metric để phát hiện queue/delivery lỗi |
| Quyền riêng tư | Không password, token, raw body | Canary giả không xuất hiện ở sink |
| Cấu hình vận hành | rotation, quota, retention, RBAC | Không đầy disk hoặc công khai log |
| Alerting | 5xx/collector failure/no-data | Đúng nguồn, route cảnh báo và runbook |

**Không có một thời hạn cố định đúng cho mọi hệ thống.** Ví dụ một môi trường có thể đặt mục tiêu “canary searchable trong 60 giây”, nơi khác có queue/batch dài hơn. Chọn ngưỡng theo thiết kế, tải và mục tiêu điều tra của tổ chức; ghi rõ thời gian chờ và hành động khi vượt ngưỡng.

### 3.1. Chọn bằng chứng có thể lặp lại

Nên lưu trong release log hoặc hệ thống change management:
- Release/commit/image digest, thời điểm deploy, cluster/namespace, service/env.
- Danh sách các đường log/sinks quan trọng đã kiểm tra.
- Canary event ID ngẫu nhiên, **không chứa dữ liệu cá nhân**.
- Mốc phát tại ứng dụng và mốc đầu tiên được tìm thấy trong backend.
- Kết quả truy vấn log, số event và schema, được tóm tắt an toàn.
- Metrics exporter/collector về accepted, failed, dropped, queue.
- Điều kiện PASS/FAIL, người phê duyệt và quyết định giữ rollout/rollback.

Không copy raw production log chứa PII vào ticket để chứng minh kết quả. Chỉ dùng mã canary, bản tổng hợp hoặc liên kết có kiểm soát.

## 4. Kiểm tra lớp ứng dụng và tiến trình sau deploy

### 4.1. Xác nhận release thực sự đã chạy

Trước khi xem log, xác nhận:
1. Deployment/pod/instance đang chạy đúng version hoặc image digest.
2. Startup/readiness/liveness không báo lỗi liên tục.
3. Không có restart loop, OOMKill hoặc JVM shutdown bất thường.
4. Các nguồn cấu hình log (profile, environment variables, mounted files, system properties) đúng môi trường.
5. Không có sự khác biệt giữa canary pod và các replicas còn lại.

Readiness **không chứng minh pipeline logging hoạt động** trừ khi health check được thiết kế rõ để kiểm tra điều đó. Tuy nhiên kiểm tra sức khỏe của tiến trình giúp tránh quy lỗi logging khi thực tế service không khởi động được.

### 4.2. Các câu hỏi khi đọc startup log

Kiểm tra xem:
- Đúng backend Logback/Log4j 2/JUL được khởi tạo không?
- Có lỗi cấu hình appender, thiếu thư mục, permission denied, invalid encoder hoặc plugin missing không?
- Có warning liên quan OTLP endpoint, TLS handshake, DNS, credential, clock hoặc queue không?
- Log startup có ghi password, connection string hoặc token không?
- Có log lặp quá nhiều do logger additivity, bridge vòng lặp JUL ↔ SLF4J hoặc nhiều appenders không?
- Có khai báo **service name/environment/version** đúng trên event/collector không?

Đối với appender mạng bất đồng bộ, log startup “exporter initialized” **không đồng nghĩa** một lô đã được nhận. Cần canary end-to-end ở mục 7.

## 5. Xác minh log level và cấu hình đang có hiệu lực

### 5.1. Level tại runtime khác file cấu hình

Một service có `logging.level.root=INFO` trong source, nhưng môi trường deploy có thể ghi đè bằng:
- Spring profile hoặc environment variable.
- Java system property / command-line argument.
- Configuration server hoặc mounted config file.
- API thay đổi mức log tại runtime (khi được phép).
- Level kế thừa từ logger cha hoặc cấu hình backend.
- Filter/appender threshold chặn riêng một tuyến.

Chỉ đọc file cấu hình không chứng minh mức log **hiệu lực**. Với Spring Boot Actuator (ví dụ phiên bản 3.5), endpoint `loggers` có thể trả cả:
- `configuredLevel`: mức được chỉ định trực tiếp cho logger đó, có thể `null`.
- `effectiveLevel`: mức đang có hiệu lực do backend tính theo cấu hình/kế thừa.

Ví dụ gọi chỉ đọc trong **môi trường test hoặc endpoint quản trị đã được bảo vệ**:

```bash
curl --fail --silent \
  http://127.0.0.1:8080/actuator/loggers/com.example.orders
```

Một phản hồi **minh họa**, không phải output bảo đảm của service:

```json
{
  "configuredLevel": null,
  "effectiveLevel": "INFO"
}
```

Endpoint chỉ hoạt động nếu đã có Actuator, được expose và được phân quyền cho caller. **Không đưa `/actuator/loggers` ra internet công khai**; một số cấu hình cho phép thay đổi log level tại runtime nên cần authentication/authorization.

### 5.2. Những level cần thử

| Tình huống | Điều mong đợi |
| --- | --- |
| Request thành công bình thường | Có event INFO hoặc metric theo chính sách; không flood ERROR |
| Lỗi nghiệp vụ dự kiến | INFO/WARN theo taxonomy, không sai thành SEVERE |
| Lỗi hệ thống bất thường | Event ERROR/SEVERE hữu ích, có error code và correlation |
| DEBUG/TRACE trên production | Không bật nhầm cho thành phần nhạy cảm |
| Event INFO khi logger effective WARN | Có thể **không được phát**; đây là filter đúng |
| Error tại appender/collector | Phải có tín hiệu lỗi vận chuyển riêng |

Đừng giả định `logging.level.root=ERROR` là “an toàn nhất”: nó có thể tắt các access/audit event hoặc operational signals bắt buộc. Cấu hình hợp lý phụ thuộc yêu cầu ứng dụng.

**Không POST thay đổi log level trong production chỉ để kiểm tra** nếu không có quy trình phê duyệt và kế hoạch hoàn nguyên. Nếu cần tăng DEBUG tạm thời để điều tra, phải đặt phạm vi logger cụ thể, thời hạn, tác động bảo mật và người chịu trách nhiệm.

## 6. Kiểm tra event ở điểm xuất gần ứng dụng

Tùy kiến trúc, cần nhìn đúng điểm xuất:
- **stdout/stderr:** console logs của container/systemd; xem raw output có đúng format/level hay không.
- **file appender:** xác minh file mới thực sự được tạo, owner/group/ACL, size, rotation, quyền ghi và tail/shipper.
- **OTLP exporter:** xác nhận appender/bridge/instrumentation gắn log vào OTel SDK, không chỉ có tracer.
- **systemd journal:** xem journal theo unit/service, nhưng không mặc định đã có bản sao ở collector.
- **agent-side buffer:** kiểm tra nguồn được nhận, path/positions/offset và lỗi parse.

Một event chỉ xuất hiện trong stdout của pod nhưng chưa tìm thấy ở Loki/Elastic/OpenSearch **không phải E2E PASS**. Nó xác định vị trí lỗi có thể nằm ở runtime log driver, agent, network, collector hoặc backend.

### 6.1. Quy tắc kiểm tra format

Chọn một event đã biết (startup, smoke request hoặc canary) rồi xác minh:
1. Mỗi record có một timestamp có timezone, hoặc có timestamp nội bộ được mapping đúng.
2. `service`/`environment`/`version` nhất quán với release.
3. `event`/`error_code` là tên ổn định, không chỉ là free-text dễ đổi.
4. `level` chuẩn hóa theo schema; không lẫn `SEVERE`/`ERROR` khi mapping sai.
5. Field numeric như `duration_ms`, `status` đúng kiểu và đơn vị.
6. Request route là `/orders/{id}`, không phải path chứa email/token/ID thô.
7. JSON/logfmt parse đúng, CR/LF không tạo record giả.
8. `trace_id`/`span_id` có giá trị hợp lệ hoặc được bỏ khi không có active span.
9. Event không ghi Authorization header, Cookie, password, token, query string nhạy cảm.
10. Một request không vô tình bị ghi hai lần ở cùng layer do additivity/filter/sidecar.

### 6.2. Không đánh giá chỉ bằng việc thấy log cũ

Sau deploy nên lọc theo **release identity + thời gian mới**. Nếu dashboard còn log trước deploy hoặc đang hiển thị event từ replica phiên bản cũ, có thể ngộ nhận hệ thống mới đang vận chuyển tốt.

Sử dụng label/field có độ tin cậy phù hợp, ví dụ:
- `service.name=orders-api`;
- `deployment.environment=prod`;
- `service.version=2026.11.10`;
- `instance/pod` chỉ khi cần phân biệt replicas và được cho phép.

Tên field tùy pipeline OpenTelemetry/Grafana/Elastic; không mặc định tự được gắn. Dùng config/metadata thật của deployment, không lấy raw header từ client để định danh môi trường.

## 7. E2E canary: từ ứng dụng đến nơi có thể truy vấn

Một **canary logging event** là sự kiện kiểm thử có dữ liệu vô hại, đi qua **đúng đường vận chuyển** mà log production sử dụng. Mục tiêu là chứng minh event:
1. Được tạo tại đúng phiên bản service.
2. Được backend logging xử lý.
3. Được agent/collector nhận và export.
4. Có thể tìm thấy tại log storage bằng truy vấn được cấp quyền.
5. Xuất hiện trong thời hạn freshness SLO đã định.

### 7.1. Quy trình có thể áp dụng

1. Sinh `probe_id` ngẫu nhiên riêng cho đợt release; không dùng email/tài khoản thật.
2. Gửi một request smoke vào endpoint **đã được cho phép** hoặc kích hoạt một event vận hành có schema an toàn.
3. Ghi lại mốc UTC của request và expected service/version/route.
4. Xác minh event ở local sink (stdout/file/test appender).
5. Theo dõi exporter/collector accepted/sent/failed metrics nếu có.
6. Truy vấn backend theo `probe_id`, service và time range hẹp; không query cả kho log.
7. So sánh event thực và schema; kiểm tra số bản ghi mong đợi.
8. Tính `freshness = first_searchable_time - event_time`, có tính tới clock skew và cách hệ thống gắn timestamp.
9. Ghi kết quả và không kéo dài poll vô hạn; nếu deadline hết, đánh dấu **FAIL/UNVERIFIED** theo chính sách.
10. Xác minh canary không tạo hành động nghiệp vụ thật, không gửi secret, không biến thành alert giả.

**Phân biệt các mốc:**

```text
emit_time -> enqueue_time -> exporter_ack_time -> ingest_time -> searchable_time
```

Export ACK **không luôn đồng nghĩa searchable**. Một exporter có thể được collector nhận thành công nhưng collector còn đang batch, retry hoặc storage chưa index. Vì vậy tiêu chí “có trên dashboard” cần kiểm tra ở backend/query endpoint thật.

### 7.2. Canary không nên chứa gì?

Không dùng password, session cookie, API token thật, thông tin khách hàng, số tài khoản hoặc payload nghiệp vụ thật. Dùng ID kiểm thử tổng hợp, event code và một route thử nghiệm không gây mutation không mong muốn.

Nếu cần kiểm tra **redaction**, dùng chuỗi giả đặc biệt như `FAKE_SECRET` **chỉ trong môi trường thử nghiệm được phép**, không biến một test bảo mật thành việc tiêm header lạ lên production mà chưa được duyệt. Một probe production nên tập trung metadata tối thiểu và route an toàn.

### 7.3. Đọc sai kết quả canary

| Kết quả quan sát | Có thể suy ra | Chưa thể suy ra |
| --- | --- | --- |
| App log có event | Appender hoặc sink cục bộ đã nhận | Collector đã nhận |
| Collector receiver accepted tăng | Collector nhận dữ liệu tại receiver | Backend lưu thành công |
| Exporter sent tăng | Exporter xác nhận gửi theo contract | Bản ghi đã searchable tức thời |
| Query backend có canary | Đường đến backend/query hoạt động cho canary | Mọi request khác đều không mất |
| Không tìm thấy canary | Có điểm cần điều tra | Chắc chắn là logger không được gọi |
| Có hai event cùng probe ID | Có thể duplicate | Chắc chắn producer tạo hai request |

Một canary PASS là bằng chứng tốt cho đường thử, **không phải bảo đảm tuyệt đối cho toàn bộ traffic**. Kết hợp với pipeline metrics, retention, sampling và kiểm tra lỗi có kiểm soát.

## 8. Ví dụ Java 17+ độc lập: HTTP smoke test và xác minh local access log

Đoạn code sau dùng **JDK thuần**: `com.sun.net.httpserver.HttpServer` để phục vụ HTTP trên `127.0.0.1`, `HttpClient` gửi hai request, `java.util.logging` (JUL) ghi access event, một `Handler` in-memory kiểm tra log. Không cần Spring Boot, Maven hay service bên ngoài.

Ví dụ kiểm tra:
- Health endpoint trả 200.
- Probe request trả 200.
- Có đúng hai event tới handler cục bộ.
- `correlation_id` được đưa vào event với định dạng được kiểm soát.
- Route trong log là mẫu `/orders/{id}`, không phải raw path `/orders/42`.
- Header/URL chứa **secret giả** chỉ để kiểm thử loại bỏ dữ liệu ở local; không xuất hiện trong event.
- stdout là kết quả kiểm tra có thể dự đoán, không phải time measurement biến động.

Tạo file **`PostDeployLoggingDemo.java`**:

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
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class PostDeployLoggingDemo {
    private static final Logger ACCESS =
            Logger.getAnonymousLogger();

    private static final class Capture extends Handler {
        private final List<LogRecord> records = new ArrayList<>();
        final CountDownLatch received = new CountDownLatch(2);

        @Override
        public synchronized void publish(LogRecord record) {
            if (isLoggable(record)) {
                records.add(record);
                received.countDown();
            }
        }

        @Override public void flush() {}
        @Override public void close() {}

        synchronized List<LogRecord> snapshot() {
            return List.copyOf(records);
        }
    }

    private static void handle(HttpExchange exchange)
            throws java.io.IOException {
        long started = System.nanoTime();

        try {
            byte[] body =
                    "ok".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        } finally {
            String path = exchange.getRequestURI().getPath();
            String route = "/healthz".equals(path)
                    ? "/healthz"
                    : path.matches("/orders/[0-9]{1,8}")
                        ? "/orders/{id}" : "/unmapped";

            String id = exchange.getRequestHeaders()
                    .getFirst("X-Request-ID");
            if (id == null
                    || !id.matches("[A-Za-z0-9_-]{1,32}")) {
                id = "invalid";
            }

            int code = exchange.getResponseCode();
            long millis = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            ACCESS.info(
                    "event=http_access method=GET route="
                    + route
                    + " status="
                    + (code >= 100 && code <= 599
                        ? code : "unknown")
                    + " correlation_id=" + id
                    + " duration_ms=" + millis);
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        ACCESS.setUseParentHandlers(false);
        ACCESS.setLevel(Level.INFO);

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        ACCESS.addHandler(capture);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(
                "/healthz", PostDeployLoggingDemo::handle);
        server.createContext(
                "/orders", PostDeployLoggingDemo::handle);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newHttpClient();

            HttpResponse<String> health = client.send(
                HttpRequest.newBuilder(
                        URI.create(base + "/healthz"))
                    .header("X-Request-ID", "health_1")
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build(),
                HttpResponse.BodyHandlers.ofString());

            HttpResponse<String> probe = client.send(
                HttpRequest.newBuilder(
                        URI.create(base
                            + "/orders/42?token=FAKE_SECRET"))
                    .header("X-Request-ID", "req_42")
                    .header("Authorization",
                            "Bearer FAKE_SECRET")
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build(),
                HttpResponse.BodyHandlers.ofString());

            if (!capture.received.await(
                    5, TimeUnit.SECONDS)) {
                throw new AssertionError(
                        "Missing local log event");
            }

            List<String> lines = capture.snapshot()
                    .stream()
                    .map(LogRecord::getMessage)
                    .toList();

            if (lines.size() != 2
                    || lines.stream().noneMatch(s ->
                        s.contains("route=/healthz status=200 "
                                + "correlation_id=health_1"))
                    || lines.stream().noneMatch(s ->
                        s.contains("route=/orders/{id} status=200 "
                                + "correlation_id=req_42"))
                    || lines.stream().anyMatch(s ->
                        s.contains("FAKE_SECRET")
                        || s.contains("token=")
                        || s.contains("/orders/42"))) {
                throw new AssertionError(
                        "Local log contract failed");
            }

            System.out.println(
                    "health_status=" + health.statusCode());
            System.out.println(
                    "probe_status=" + probe.statusCode());
            System.out.println(
                    "captured_events=" + lines.size());
            System.out.println(
                    "correlation_verified=true");
            System.out.println(
                    "secret_in_local_logs=false");
        } finally {
            server.stop(0);
            ACCESS.removeHandler(capture);
            capture.close();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn có module `jdk.httpserver`:

```bash
javac --add-modules jdk.httpserver PostDeployLoggingDemo.java
java --add-modules jdk.httpserver PostDeployLoggingDemo
```

**Standard output chính xác khi localhost sockets được cho phép:**

```text
health_status=200
probe_status=200
captured_events=2
correlation_verified=true
secret_in_local_logs=false
```

### 8.1. Giải thích các bước

1. `HttpServer` lắng nghe `127.0.0.1` và port `0` để OS tự cấp port; không xuất hiện trên internet.
2. `HttpClient` gọi `/healthz` và `/orders/42`, với query/header **giả nhạy cảm** ở probe.
3. Logger JUL được đặt INFO, tắt parent handler để không in duplicate console logs.
4. Handler cục bộ đồng bộ thu `LogRecord`; `CountDownLatch` tránh race khi HTTP server và client chạy ở thread khác.
5. `route` được xác định bằng allowlist đường dẫn, không ghi raw query/path có ID thực.
6. `X-Request-ID` được kiểm tra độ dài/ký tự để tránh CRLF injection. **Validation không chứng minh client ID đáng tin**: ingress production nên sinh hoặc xác thực correlation ID, không dùng header tự khai như bằng chứng danh tính.
7. `System.nanoTime()` đo duration, nên số ms không được đưa vào stdout cố định; trong event thật vẫn có `duration_ms`.
8. Kiểm tra event count, hai route, status, correlation và không có `FAKE_SECRET` trước khi in PASS-like output.
9. `finally` dừng HTTP server và tháo handler để không rò tài nguyên.

### 8.2. Giới hạn ví dụ

**Đây là local log smoke test, không phải E2E check collector.** Sự kiện được giữ trong `Capture` in-memory, chưa đi qua file/stdout, OTLP, agent, collector hoặc backend tìm kiếm. Vì vậy kết quả `secret_in_local_logs=false` chỉ đúng đối với **hai events được capture ở handler này**, không chứng minh các logging libraries hay network access log khác cũng đã redact.

Hơn nữa:
- Ví dụ chạy request thành công, chưa thử 4xx/5xx, async servlet, retry hoặc exporter failure.
- Một ứng dụng thật cần routing/method/status handling chuẩn; ví dụ đơn giản chỉ phục vụ demo.
- JSON format, OpenTelemetry fields, retention và backend auth chưa được cài.
- Probe chứa canary giả chỉ dành cho môi trường học tập/test đã được phép; production canary nên tối giản, không cần giả Authorization header.
- Nếu JVM không cho tạo loopback socket, chương trình có thể thất bại vì sandbox/network policy. Đây là hạn chế môi trường, không phải lý do nới quyền production.
- Nếu dùng Spring Boot/Logback, nên thêm test qua appender thật, rồi xác minh riêng collector như mục 7.

## 9. Kiểm tra Spring Boot sau triển khai

Với Spring Boot, một checklist ngắn:
1. Xác định cấu hình logging thực được nạp từ `application.properties/yaml`, `logback-spring.xml`, `log4j2-spring.xml` hoặc môi trường.
2. Xác minh runtime effective levels trên logger quan trọng, nếu Actuator `loggers` được bảo vệ và mở cho vai trò kiểm tra.
3. Đối chiếu log line có `service`, `environment`, `version`, status/route và ID tương quan.
4. Kiểm tra access log nếu dùng embedded servlet container: **Spring application INFO log không thay thế Tomcat/Jetty/Undertow access log**.
5. Kiểm tra actuator health/readiness; biết rằng chúng không xác minh log delivery ngoài cluster.
6. Với OTLP, xác minh appender/bridge và endpoint; chỉ có `management.otlp.logging.endpoint` hoặc `otel.logs.exporter` **không chứng minh** mọi logger tự động được instrument.
7. Có plan điều chỉnh logger level ở runtime khi incident, có RBAC/audit và hoàn nguyên sau thời gian giới hạn.

Trong Spring Boot Actuator, `configuredLevel=null` có thể có nghĩa là logger không được cấu hình riêng và kế thừa mức hiệu lực, **không** nghĩa logging bị tắt.

**Không mở rộng Actuator endpoints ra internet công khai** chỉ để cho pipeline CI đọc. Nếu automation cần xem level, chạy từ mạng quản trị và credential được bảo vệ bởi secret manager; không ghi credential vào command output/log.

## 10. Kubernetes/container: kiểm tra nguồn log đúng pod

Trên Kubernetes, lệnh dưới đây là **mẫu thao tác chỉ đọc**. Thay namespace/deployment/pod/container bằng giá trị thực, cần RBAC phù hợp:

```bash
# Xác nhận rollout và tình trạng instance.
kubectl rollout status deployment/orders-api -n prod --timeout=120s
kubectl get pods -n prod -l app=orders-api -o wide

# Xem raw stdout/stderr của một pod/container cụ thể.
kubectl logs pod/orders-api-EXAMPLE -n prod \
  -c app --since=10m --timestamps

# Khi container đã restart, xem log instance trước nếu còn.
kubectl logs pod/orders-api-EXAMPLE -n prod \
  -c app --previous --tail=200

# Xem sự kiện liên quan một pod cụ thể (nếu có quyền).
kubectl describe pod orders-api-EXAMPLE -n prod
```

Tên `orders-api-EXAMPLE` chỉ là **tên minh họa**; phải thay bằng pod thật. `--previous` không tạo archive logs vĩnh viễn, và dữ liệu có thể mất do rotation/runtime policy.

**Các lưu ý quan trọng:**
- `kubectl logs` hiển thị log được container runtime thu theo cơ chế Kubernetes, không chứng minh Loki/Elastic nhận log.
- Một deployment có nhiều pods; kiểm tra ít nhất canary pod và tính nhất quán của các replicas cần thiết.
- Nếu log không xuất hiện trên pod, xét logger level/appender; nếu có ở pod nhưng không có trên backend, xét agent, namespace, labels, network và collector.
- Với Java ghi file trong container, stdout có thể trống mặc dù file có logs; phải xác định chính xác đường vận chuyển và quyền volume.
- Không chạy `kubectl exec` để thay đổi file/properties hoặc `chmod 777` trong production khi chưa có change procedure.
- Không đưa log thô có PII ra máy cá nhân rồi lưu lâu dài. Có thể chỉ xem một số dòng được phép hoặc dùng công cụ tìm kiếm có RBAC.

### 10.1. Log bị thiếu ngay sau rolling update

Kiểm tra:
1. Agent có đọc file mới sau rollover/restart không?
2. Runtime có xoay container logs, `kubectl logs` chỉ còn một phần dữ liệu không?
3. Pod mới có label/mount phù hợp để agent discover không?
4. Có sidecar đang crash hoặc dùng credential cũ không?
5. Service version/namespace/tenant mapping thay đổi khiến query cũ không còn match không?
6. Có lỗi clock skew khiến event thuộc time range khác không?
7. Query có đang lọc sai `pod` hoặc replica cũ không?

Một canary event vừa phát ở pod mới giúp phân biệt lỗi “chưa phát” với “đã phát nhưng chưa vận chuyển”.

## 11. OpenTelemetry Collector: những metric cần nhìn

Để kiểm tra logging end-to-end, ngoài query backend nên đọc **internal telemetry** của OpenTelemetry Collector nếu pipeline có dùng Collector. Tài liệu chính thức nêu các nhóm:
- Receiver: records accepted/refused.
- Processor: incoming/outgoing items.
- Exporter: sent records, send failures, failed enqueue.
- Exporter queue: size/capacity.
- Process: CPU/memory/uptime.

Các **tên metric ở dạng OTLP** trong tài liệu có thể bao gồm:

| Metric ví dụ từ Collector | Ý nghĩa |
| --- | --- |
| `otelcol_receiver_accepted_log_records` | Số logs receiver nhận thành công |
| `otelcol_receiver_refused_log_records` | Số logs receiver không nhận |
| `otelcol_exporter_sent_log_records` | Số logs exporter gửi thành công theo contract |
| `otelcol_exporter_send_failed_log_records` | Số logs exporter gửi lỗi |
| `otelcol_exporter_enqueue_failed_log_records` | Số logs không xếp được vào queue |
| `otelcol_exporter_queue_size` | Số lô đang nằm trong sending queue |
| `otelcol_exporter_queue_capacity` | Sức chứa sending queue, thường tính theo batches |

**Cảnh báo phiên bản:** tên Prometheus-exposed metrics có thể khác các tên OTLP ở trên do cách exporter thêm/không thêm suffix như `_total` hoặc unit, và stability của metric có thể thay đổi. Hãy kiểm tra `/metrics`/data source của Collector **thực tế**, không sao chép nguyên truy vấn từ bài rồi coi thiếu tên là mất logs.

Nếu Collector dùng internal Prometheus endpoint theo cấu hình mặc định phù hợp, có thể có listener trên `127.0.0.1:8888/metrics`. Không mặc định endpoint này truy cập được từ laptop hoặc nên mở ra internet. Các port/hostname có thể được thay trong deployment.

### 11.1. Đọc metric đúng nghĩa

- `receiver_accepted` tăng → receiver nhận logs, **không chứng minh** backend lưu.
- `exporter_sent` tăng → exporter ghi nhận send thành công, **không chứng minh ngay searchable**.
- `exporter_send_failed` tăng → đang có lỗi export, có thể còn retry nên chưa chắc đã mất vĩnh viễn.
- `enqueue_failed` tăng → queue không nhận dữ liệu, có rủi ro mất.
- `queue_size` gần `queue_capacity` liên tục → downstream đang tắc hoặc exporter quá chậm.
- Collector metrics không tăng trong khi source phát logs → có thể đường application-agent/receiver bị đứt hoặc metric không được scrape; kiểm tra cả hai.

Ví dụ chuỗi kiểm tra:

```text
Java emits canary
   |
   +--> Local sink thấy event?    Nếu không: logger/backend
   |
   +--> Receiver accepted tăng?   Nếu không: agent/OTLP/network
   |
   +--> Exporter sent tăng?       Nếu không: queue/retry/backend
   |
   +--> Query thấy canary?        Nếu không: storage/query/RBAC/time
```

Đọc *counter deltas* trong cùng khoảng thời gian có traffic, tránh so một ảnh chụp số tích lũy từ khi Collector khởi động. Với nhiều collectors, cần chọn instance tương ứng hoặc aggregate đúng labels. Chênh lệch accepted/sent không luôn là lost count vì batch buffering, processor drop có chủ ý, restart và pipeline khác nhau.

## 12. Correlation và tracing sau triển khai

Một release có thể ghi đầy đủ messages nhưng mất `trace_id` hoặc request ID sau nâng cấp OpenTelemetry/Logback.

Xác minh theo một request cụ thể:
1. Tạo request/correlation ID hợp lệ từ ingress; không dựa vào arbitrary client-provided secret.
2. Access event có route/status và correlation ID.
3. Application log trong cùng request có ID tương ứng.
4. Nếu tracing được bật, log event có **trace_id/span_id chuẩn** khi có active span.
5. Trace backend nhận span cho service/version đúng.
6. Link từ log viewer mở trace hoặc tìm được span bằng ID.
7. Khi chạy qua thread pool, async handler, Kafka consumer hoặc virtual thread, context vẫn được propagation và cleanup đúng.

Với OpenTelemetry Java Agent, MDC auto-instrumentation có thể đưa `trace_id`, `span_id` và `trace_flags` vào bản sao MDC của logging event khi cấu hình tương thích. **Chỉ cài agent không tự bảo đảm pattern/layout luôn in các field này**; cần formatter/encoder hỗ trợ và kiểm tra output thật. Khi không có active span hợp lệ, không nên giả một trace ID.

**Correlation ID tự tạo khác W3C TraceId.** Chuỗi `req_42` trong ví dụ Java là ID để so khớp log, **không** phải trace ID định dạng chuẩn. Không tạo link trace từ ID sai định dạng.

Nếu logging framework hoặc appender async, giữ ngữ cảnh theo event snapshot lúc ghi thay vì đọc thread-local MDC của exporter worker ở thời điểm gửi sau đó. Cleanup context trong `finally`/scope để không trộn request khi thread được tái sử dụng.

## 13. Bảo mật dữ liệu, quyền và retention

Production smoke tests không chỉ cần chứng minh có logs mà còn phải chứng minh **không xuất ra điều cấm**:
- Không password/OTP/API key/bearer token/Authorization/Cookie.
- Không raw HTTP body, request headers hoặc query chứa thông tin cá nhân nếu không có mục đích được duyệt.
- Không SQL parameters hay exception message chứa secret không cần thiết.
- Không để MDC/ThreadContext tự chứa email, token hoặc payload.
- Không có dòng bị phá bởi CR/LF từ raw input (log injection).
- Không có file `0666`/`0777` hoặc bucket/export công khai chỉ để shipper đọc.
- Không để debug logging bật sau khi triển khai mà không có thời hạn/approval.

### 13.1. Quan sát bản sao

Một event có thể tồn tại ở:
- stdout và container runtime buffer;
- file hiện tại và rotated/archived file;
- agent queue hoặc disk spool;
- Collector batch/retry queue;
- log storage chính và chỉ mục/tier cũ;
- dashboard snapshot, CSV export hoặc incident attachment;
- backup và audit store.

Do đó “redaction ở collector” là lớp bảo vệ bổ sung, **không thay thế loại bỏ từ nguồn**. Kiểm tra canary giả ở đường thực tế đến collector và nếu policy yêu cầu, xem cả exporter/raw file. Nếu phát hiện secret đã ghi, áp dụng quy trình security incident và rotate credential hiệu lực khi cần; xóa một dòng ở dashboard không hủy token đã lộ.

### 13.2. Quyền file và rotation

Nếu dùng file appender:
- Service UID/GID/Windows identity có quyền tạo/append log nhưng không cần quyền root.
- Thư mục cha có ACL/mode phù hợp; không chỉ xem quyền trên file.
- Sau rotation, file mới và archive không rộng quyền hơn chính sách.
- Agent có read/traverse nhưng không có quyền sửa/xóa nếu không cần.
- Retention/logrotate không tranh chấp với RollingFileAppender của backend.
- Disk space/inodes còn đủ, file có quota, alerts và recovery path.

Sau rolling update phải kiểm tra **file mới do phiên bản mới tạo**, không chỉ file cũ đã chmod thủ công.

## 14. Thời gian ghi, backlog và tính đầy đủ

Tốc độ ingest sau deploy có thể chậm hơn bình thường do:
- Queue appender/OTel exporter vừa khởi động.
- DNS/TLS/auth handshake tới collector.
- Batch timeout, retry/backoff, rate limit hoặc Collector saturation.
- Backend đang index trễ, object store/retention có vấn đề.
- Network policy đổi ở deployment mới.
- Clock skew khiến query thời gian bỏ sót event.
- Collector/agent pod chưa ready đúng lúc pod ứng dụng phát startup logs.

Một dòng log đến trễ **không đồng nghĩa đã mất**, nhưng nếu vượt **freshness SLO**, cần ghi nhận FAIL theo tiêu chí vận hành. Trong trường hợp log bắt buộc cho incident response, chỉ “cuối cùng sẽ xuất hiện” có thể chưa đủ.

### 14.1. RPS và error rate từ logs có thể bị sai

Nếu deploy thay `logging.level` hoặc sampling, số dòng access log có thể giảm dù request traffic không giảm. Dashboard dựa trên logs có thể:
- Báo hết lỗi khi thực tế exporter ngừng gửi.
- Tăng tỷ lệ 5xx nếu success events bị sample nhiều hơn errors.
- Đếm đôi khi gateway và app đều ghi access event.
- Nhầm retry message với request mới.
- Vẽ p95 sai nếu log bị drop không đồng đều.

Đối chiếu **metrics** ở điểm đo chính với counts từ log, nhất là sau khi thay sampling/route labels. Chỉ dùng log-derived numbers cho SLO khi pipeline có điều kiện độ tin cậy thích hợp và định nghĩa rõ.

## 15. Quyết định giữ rollout, tạm dừng hoặc rollback

Không phải mọi vấn đề logging đều tự động yêu cầu rollback. Quyết định dựa vào mức quan trọng của tín hiệu, phạm vi ảnh hưởng và khả năng khắc phục an toàn.

| Tình huống | Phân loại đề xuất | Phản ứng |
| --- | --- | --- |
| Canary có trên backend trong SLO, schema/field đúng | PASS | Tiếp tục theo dõi |
| Event xuất hiện chậm nhẹ nhưng trong ngưỡng | Quan sát | Theo dõi backlog, xác minh ở các replicas |
| Một debug event không quan trọng bị lọc đúng theo policy | Không phải lỗi | Không bật DEBUG tùy tiện |
| Collector quá tải, queue gần đầy, exporter retry liên tục | DEGRADED | Dừng mở rộng rollout, điều tra capacity/network |
| Không có canary ở backend sau deadline | FAIL/UNVERIFIED | Giữ rollout, phân tích theo từng hop |
| ERROR/audit events bắt buộc bị mất | Nghiêm trọng | Áp dụng release gate/rollback theo policy |
| Secret thực được log ra sink | Sự cố bảo mật | Cô lập dữ liệu, rotate token, xử lý incident |
| Log đầy disk, JVM/request latency tăng mạnh | Nghiêm trọng | Mitigate tài nguyên, hạn chế tác động; cân nhắc rollback |
| Dashboard query sai label nhưng backend có event | Lỗi quan sát UI | Sửa query/config, không kết luận app không log |

**Rollback không phải phép chữa tự động.** Nếu lỗi nằm ở Collector trung tâm hoặc expired backend credential, rollback app có thể không giúp và có thể gây thêm gián đoạn. Cần xác định tầng lỗi trước khi hành động. Với audit logging bị mất hoặc lộ dữ liệu, tuân thủ quy trình khẩn cấp thay vì chờ toàn bộ checklist hoàn tất.

### 15.1. Đề xuất thứ tự kiểm tra trong rollout

1. **Trước rollout:** baseline current log delivery, saved queries/metrics, approval và mức SLO.
2. **Canary/first replica:** xác nhận process, local event, E2E canary, privacy/schema và nguồn metrics.
3. **Mở rộng tỷ lệ rollout:** xem errors/dropped logs/latency, kiểm tra pod khác thay vì chỉ một replica.
4. **Sau hoàn tất:** xác nhận không còn worker/version cũ và query backend tìm thấy event mới.
5. **Theo dõi sau deploy:** alert/no-data và queue trends ổn định qua khoảng thời gian do chính sách quy định.

Số phút ở từng phase tùy dịch vụ, rủi ro, lưu lượng và mục tiêu triển khai; không coi một con số chung là cam kết.

## 16. Đưa kiểm tra logging vào CI/CD

Có thể xây **deploy verification job** không thay cấu hình production:
1. Đọc release identity và endpoint smoke được cho phép từ hệ thống deploy.
2. Đợi rollout readiness thành công với timeout.
3. Gửi một canary request **idempotent** hoặc dùng endpoint chỉ quan sát.
4. Ghi mốc UTC và `probe_id`; không đưa token thật vào log.
5. Kiểm tra application HTTP response.
6. Query log backend có auth qua secret manager, khoảng thời gian hẹp.
7. Poll với exponential backoff và deadline; không liên tục query toàn bộ log storage.
8. Assert đúng service/env/version/probe ID/schema/level.
9. Kiểm tra canary có 1 event ở layer mục tiêu, không bị nhân đôi hoặc redaction sai.
10. Đọc collector/exporter metrics và kiểm tra failures/dropped theo ngưỡng.
11. Trả PASS/FAIL có cấu trúc, lưu bằng chứng an toàn.
12. Nếu FAIL, giữ rollout/trigger chính sách rollback hoặc yêu cầu on-call phê duyệt.

### 16.1. Pseudocode kiểm tra đến backend

Đây là **pseudocode**, không phải script chạy độc lập:

```text
probeId = newRandomSafeId()
sentAt = utcNow()
sendApprovedSmokeRequest(probeId)

deadline = monotonicNow() + allowedFreshness
while monotonicNow() < deadline:
    hits = backendQuery(
        service = expectedService,
        environment = expectedEnv,
        release = expectedVersion,
        probeId = probeId,
        timeRange = [sentAt - clockSkewBudget, utcNow()]
    )

    if hits match expected event schema and count:
        verify no forbidden fields
        verify pipeline counters and alert health
        return PASS

    sleepWithBoundedBackoff()

return FAIL("Canary not searchable within deadline")
```

**Không hardcode** API backend/credentials, không dùng raw text query từ input không tin cậy và không nhầm “No data” với 0 lỗi. Nếu backend bị lỗi/403, trả tình trạng **INCONCLUSIVE/ACCESS_DENIED** riêng thay vì giả kết luận ứng dụng không log.

### 16.2. Vì sao automation có thể gây false negative?

- Backend query có độ trễ index.
- Clock skew làm time range sai.
- Canary event bị sampling như một success request.
- Query yêu cầu label app/env/version mà pipeline không gắn.
- Pod bị thay trong rollout và dữ liệu đến dưới instance khác.
- Backend đã nhận nhưng quyền người chạy job không cho đọc tenant.
- Job assert “đúng một dòng” trong khi cả gateway và app đều ghi; scope nguồn không đúng.

Định nghĩa scope và có diagnostic stages để người vận hành biết thất bại ở đâu, không chỉ in “log not found”.

## 17. Các kiểm thử failure và chaos nên có ở staging

Chỉ thực hiện trong môi trường được phép, có giới hạn tác động:
- Tắt log appender ở một instance test: xác minh E2E canary FAIL.
- Đổi effective level sang WARN: INFO không đến sink; xác minh test không kết luận sai.
- Collector bị ngắt mạng tạm thời: xem retries, queue, backlog, delay và error metric.
- Queue exporter đầy: xác minh `enqueue_failed`/dropped alerts hoạt động.
- Backend từ chối vì credentials hết hạn: log ở pod vẫn có, exporter/send fails tăng.
- Bật JSON encoder bị lỗi: parser/query không còn nhận đúng schema.
- Giả clock skew: canary ở sai time range, query phát hiện.
- Dùng duplicate appender: một event bị nhân đôi; dashboard count tăng giả.
- Rotation/đổi quyền file test: agent không đọc được file mới.
- Shutdown trước flush: log pending bị mất nếu queue RAM, xác nhận failure mode.
- Trace context mất khi qua thread khác: correlation breaks, kiểm tra propagation.
- Probe có dữ liệu giả như `FAKE_SECRET` trong staging: xác minh không xuất ở các sinks.

Không tiến hành các thử nghiệm gây mất log, network partition, restart hàng loạt hoặc fake secret traffic trực tiếp trên production ngoài change plan được phê duyệt.

## 18. Troubleshooting theo triệu chứng

| Triệu chứng | Nơi kiểm tra trước | Kết luận cần tránh |
| --- | --- | --- |
| Service khỏe nhưng không có log | Effective level, appender, nguồn stdout/file | “Readiness PASS là log PASS” |
| Pod stdout có log, backend không tìm thấy | Agent, receiver, exporter, RBAC, labels/time | “Ứng dụng chắc chắn không log” |
| Không có startup logs của version mới | Pod/version, source/file path, time range | “Log cũ nghĩa là version mới hoạt động” |
| Chỉ ERROR có log, INFO mất | Logger level/filter, sampling, backend parser | “Collector drop mọi thứ” |
| Có log mới nhưng thiếu trace ID | MDC/agent instrumentation, active span, encoder | “Có trace backend là log tự gắn trace” |
| Event có đúng ID nhưng schema sai | Encoder, version mapping, parser, label transform | “Có event là PASS toàn bộ” |
| Log xuất hiện chậm nhiều phút | Batch delay, queue, retry, storage index | “Exporter ACK là searchable” |
| Duplicate access log | Multiple layers, additivity, retries | “Traffic tăng gấp đôi” |
| Không đọc được file sau rotation | Directory permissions, new inode, shipper offsets | “chmod file cũ đủ rồi” |
| Lỗi 429/503 khi export | Backend throttle, network, rate policy | “Bật retry vô hạn sẽ sửa được” |
| Collector queue đầy | Downstream latency, queue size, rate, disk | “Tăng RAM vô hạn là tốt” |
| Dashboard No Data | Selector, time range, label, tenant, query syntax | “Không có lỗi production” |
| Secret xuất hiện trong log | Call site, MDC, exception, formatter, pipeline | “Đã mask một nơi là xong” |
| Smoke test fail nhưng app vẫn 200 | Log pipeline, status scope, backend query | “Kiểm tra chỉ cần HTTP 200” |

Cách điều tra hiệu quả nhất: **đi từ nguồn gần ứng dụng sang từng hop**, giữ mốc thời gian và probe ID nhất quán. Đừng bắt đầu bằng việc bật DEBUG trên toàn bộ production để tạo thêm hàng triệu events khi pipeline đang tắc.

## 19. Checklist nghiệm thu sau triển khai

- [ ] Đã xác nhận đúng service, environment, release/version và instance.
- [ ] Rollout/readiness ổn, không restart loop, OOM hoặc lỗi boot.
- [ ] Logging backend khởi tạo thành công; không có lỗi appender/encoder/file permission.
- [ ] Runtime effective levels đúng chính sách; không bật DEBUG/TRACE nhầm.
- [ ] Local sink (stdout/file/OTLP bridge) nhận event mới từ bản phát hành mới.
- [ ] Một event có timestamp, service/env/version, level, event code, field đúng kiểu/đơn vị.
- [ ] Không ghi token, password, raw body/header/query nhạy cảm; JSON/logfmt escape đúng.
- [ ] Có correlation ID hợp lệ; trace ID/span ID hoạt động khi có active span.
- [ ] E2E canary được query trong backend theo time range và deadline được phê duyệt.
- [ ] Agent/Collector receiver/exporter healthy, không tăng lỗi enqueue/send/drop bất thường.
- [ ] Queue không bị backlog kéo dài; freshness trong ngưỡng chấp nhận.
- [ ] Không duplicate event ngoài dự kiến; sampling/retention được ghi nhận rõ.
- [ ] Với file, ownership/permissions/rotation và disk space phù hợp.
- [ ] Log UI/dashboard/alerts dùng đúng nguồn, timezone, labels, version và RBAC.
- [ ] Có dữ liệu an toàn chứng minh kết quả, link incident/runbook khi FAIL.
- [ ] Điều kiện giữ rollout/rollback đã được đánh giá; không tiếp tục triển khai mù khi thiếu log bắt buộc.
- [ ] Các thay đổi debug/temporary probe sau kiểm tra đã được hoàn nguyên/dọn đúng quy trình.

## 20. Bài tập thực hành

1. Chạy `PostDeployLoggingDemo`. Giải thích sự khác nhau giữa `health_status=200`, `captured_events=2` và việc có thể query log ở collector.
2. Đặt JUL logger level thành WARNING, vẫn gửi HTTP request thành công; điều gì xảy ra với event INFO và CountDownLatch? Điều chỉnh timeout test để thấy failure có kiểm soát.
3. Sửa route mapping thành ghi raw `getRequestURI()`; dùng canary giả để thấy vì sao nó có thể làm lộ query/path.
4. Dùng Logback `ListAppender` hoặc JUL `Handler` trong unit test; phân biệt API invocation và emitted event.
5. Trong Spring Boot Actuator test, so `configuredLevel` với `effectiveLevel`; tại sao `null` không có nghĩa OFF?
6. Đặt ứng dụng Java trong Kubernetes test và quan sát bằng `kubectl logs`. Tìm một canary ở Loki/Elastic và so timestamp.
7. Tạo một HTTP 5xx trong staging, kiểm tra có event error code/trace ID và tìm log tương ứng trong dashboard.
8. Tạo test với application stdout hoạt động nhưng collector endpoint không truy cập; xác định các metrics accepted/sent/failed.
9. Thử canary không xuất hiện vì sai time range/label. Viết logic phân biệt query failure với logging failure.
10. Mô phỏng một event bị ghi hai lần do appender additivity; sửa config và kiểm tra count.
11. Thay đổi file rotation trong staging, test quyền file mới/agent shipper và khả năng đọc.
12. Tạo post-deploy checklist trong pipeline CI/CD: probe ID duy nhất, deadline, status, event query và bằng chứng an toàn.
13. Thử exporter retry/backoff với receiver chậm trong staging; đo log freshness và backlog sau khi phục hồi.
14. Tạo một test mất trace context ở thread pool rồi sửa propagation/cleanup theo logging framework.
15. Thiết kế decision matrix cho ba lỗi: dashboard query sai, collector outage và log chứa token thật. Vì sao các phương án phản ứng khác nhau?

## 21. Ghi nhớ

- **Kiểm tra sau triển khai** phải xác minh **có log đúng, tới đích đúng, trong thời hạn đúng, không rò dữ liệu và có thể điều tra**, không chỉ kiểm tra ứng dụng trả HTTP 200.
- Mốc logger được gọi, local event, receiver accepted, exporter sent và backend searchable **khác nhau**.
- Kiểm tra `effectiveLevel`, appender, encoder, startup lỗi, quyền file và cấu hình service thực sự đang chạy.
- Sử dụng **canary vô hại** với probe ID riêng, query backend có time range/deadline; không dùng token/PII thật.
- So sánh logs với metrics và traces; kiểm tra trace correlation, sampling, duplicate, queue/dropped events và độ trễ ingestion.
- OpenTelemetry Collector internal metrics giúp khoanh vùng receiver/exporter/queue, nhưng tên/suffix có thể khác theo version và export format.
- Đừng mở Actuator hoặc metrics quản trị ra internet chỉ để làm test. Không bật DEBUG diện rộng để sửa lỗi thiếu log.
- Kết quả kiểm tra phải thành release evidence và tiêu chí rollout/rollback phù hợp; xử lý log lộ secret như một sự cố bảo mật.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Actuator Loggers: https://docs.spring.io/spring-boot/3.5/reference/actuator/loggers.html
- Spring Boot — Actuator management endpoint access: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Kubernetes — `kubectl logs`: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/
- Kubernetes — `kubectl rollout status`: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_status/
- OpenTelemetry — Collector internal telemetry và exporter metrics: https://opentelemetry.io/docs/collector/internal-telemetry/
- OpenTelemetry — Java instrumentation, logger MDC: https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/docs/logger-mdc-instrumentation.md
- OpenTelemetry — Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- Oracle Java — `HttpServer` (JDK 21 docs, API cũng có ở JDK 17): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Oracle Java — `Logger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

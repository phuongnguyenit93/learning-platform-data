# Kiểm tra pipeline end-to-end trong Java Logging

## 1. Bài toán: chứng minh log đã đi hết đường cần quan sát

**Kiểm tra pipeline end-to-end (E2E) cho logging** là xác minh một sự kiện phát từ ứng dụng Java được **thu thập, truyền, xử lý, lưu và truy vấn** đúng theo hợp đồng của hệ thống. Đây là bài toán thuộc **thu thập và vận chuyển log**, không chỉ là việc unit test một lời gọi `logger.info(...)`.

Một hệ thống microservices thường có các chặng:

~~~text
Java application
  JUL / SLF4J + Logback / Log4j 2 / SDK
       │ tạo message, fields, time, trace ID
       ▼
Local sink
  stdout/stderr, file, OTLP exporter
       │
       ▼
Container runtime / node file / shipper
       │ parse, checkpoint, queue, retry
       ▼
Collector / gateway / ingestion pipeline
       │ normalize, enrich, filter, route, batch
       ▼
Log backend
       │ receive, persist, index, apply retention
       ▼
Search API / dashboard / alert
       │
       ▼
E2E assertion: tìm được đúng event, trường và số lượng
~~~

**Ý quan trọng:** Một chương trình Java chạy không lỗi, một dòng xuất hiện trên stdout, một HTTP `200` của collector hoặc một metric `exported=1` **không tự động chứng minh** record đã tồn tại bền vững và có thể tìm kiếm tại backend cuối.

Một bài test E2E đúng phải đặt **điểm bắt đầu** và **điểm kết thúc** rõ ràng. Ví dụ “từ việc phát message từ JVM cho đến khi query trong backend test trả về event có `testRunId`” mạnh hơn “logger đã gọi appender”.

### Kết quả cần đạt

Sau bài này, người học có thể:

1. Vẽ và định nghĩa từng ranh giới ACK/quan sát của pipeline.
2. Phát một sự kiện giả có ID riêng để theo dõi từ nguồn đến đích.
3. Kiểm tra schema, timestamp, severity, correlation và bảo vệ dữ liệu.
4. Thiết kế test thành công, retry, duplicate, mất kết nối và crash.
5. Chờ điều kiện thật bằng deadline thay vì `Thread.sleep` tùy ý.
6. Phân biệt test harness mô phỏng với tích hợp Collector/backend thật.
7. Quan sát chính pipeline để phát hiện việc log biến mất “im lặng”.

## 2. Phân biệt unit test, component test, integration test và E2E

| Cấp test | Phạm vi | Chứng minh được | Không chứng minh |
| --- | --- | --- | --- |
| Unit test logging call | Business method + mock logger | Code gọi API với arguments đúng | Level/filter/sink có thực sự xuất event |
| Unit test handler/appender | Logger + in-memory collector | Level, template, Throwable, fields, count | Agent đã đọc và backend đã lưu |
| Component test encoder | Log event → JSON/PatternLayout | Nội dung sau định dạng, escaping, schema | Network, retry, indexing |
| Integration test shipper | File/stdout → agent/Collector fake | Parser, routing, batch, retry trong phạm vi test | Backend thật có thể query |
| Integration test backend | Collector → test backend | Ingest, index, query theo schema | Java app đã phát/ship đúng |
| **E2E production-like** | Java process → runtime → shipper → Collector → backend → query | Đường đi đầy đủ trong môi trường/cấu hình được test | Mọi sự cố cực đoan và mọi phiên bản môi trường production |

Một bài test không cần ép thành E2E nếu mục tiêu chỉ là “mẫu thông điệp có đúng không?”. E2E đắt hơn, chậm hơn và cần quản lý môi trường. Phân bổ nhiều unit/component tests và một số E2E scenarios rủi ro cao thường hiệu quả hơn.

Ngược lại, không dùng green unit test để tuyên bố pipeline log ở Kubernetes hay collector đã hoạt động.

## 3. Định nghĩa hợp đồng giao nhận và lưu trữ

Hãy xác định **điểm cuối mong muốn** cho từng event class:

| Mốc | Tên trạng thái rõ nghĩa | Điều chưa thể khẳng định |
| --- | --- | --- |
| `Logger.log(...)` đã chạy | Produced | Handler nhận được |
| Handler/appender chấp nhận | Accepted locally | Đã thoát khỏi bộ đệm JVM |
| Stream/file đã flush | Written to local stream | Disk đã fsync, agent đã đọc |
| Agent/shipper đọc | Collected | Exporter đã gửi |
| Collector receiver nhận | Ingested by Collector | Processor không drop, backend đã index |
| Exporter gửi và nhận response | Exported according to protocol | Backend durable commit nếu ACK không hứa điều đó |
| Backend query trả event | Searchable | Có retention vô hạn hoặc chống sửa/xóa |
| Kho durable xác nhận theo hợp đồng | Persisted | Có thể tái tạo đầy đủ mọi khâu nghiệp vụ nếu event nguồn sai |

**Hợp đồng E2E có thể là “searchable within 30 seconds”** đối với log vận hành, nhưng với audit bắt buộc phải thiết kế thêm mức độ bền vững và kiểm soát toàn vẹn. Mốc 30 giây ở đây **chỉ là ví dụ SLO**, không phải tiêu chuẩn áp dụng cho mọi hệ thống.

Với mỗi test hãy định nghĩa trước:

- Mốc mà `emit` được xem là xảy ra.
- Đích kiểm tra: file, stdout của collector, fake receiver, test backend hay search API thật.
- Deadline tối đa để event trở nên queryable.
- Có chấp nhận duplicate không? Có idempotency/dedup không?
- Nếu sink không thể nhận, ứng dụng phải block, drop, buffer hay retry?
- Nếu restart giữa chừng, kỳ vọng phục hồi là gì?

Không viết assertion “sent successfully” khi mới có một Future hoặc queue insertion.

## 4. Chọn event thử nghiệm có định danh rõ ràng

Một event dùng cho E2E test nên **không chứa dữ liệu người dùng thật**, có định danh riêng và schema ổn định.

~~~json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "service.name": "order-service",
  "severity": "INFO",
  "event.code": "ORDER_ACCEPTED",
  "testRunId": "run-qa-42",
  "eventId": "evt-run-qa-42-001",
  "trace_id": "0123456789abcdef0123456789abcdef",
  "body": "order accepted"
}
~~~

Đây là JSON **minh họa**. Hai giá trị `testRunId` và `eventId` phải là **duy nhất trong mỗi lần test thật** (thường UUID/ULID phù hợp); dùng chuỗi cố định này chỉ khi cần trình bày kết quả có thể đọc.

**Tại sao cần hai ID?**

- `testRunId` lọc tất cả các sự kiện thuộc một lần test, giúp CI không đọc nhầm log cũ.
- `eventId` cho phép đếm/dedup từng event hoặc xác định event cụ thể đã biến mất.
- `trace_id` gắn với distributed tracing, nhưng một trace có thể có nhiều events; không thay thế eventId.
- `requestId` hoặc message ID có scope nghiệp vụ khác; không nên dùng chúng như unique event ID nếu một request sinh nhiều sự kiện.

Khi test hai replica, gắn `instanceId`/resource metadata nếu cần biết event đến từ replica nào; tránh sử dụng giá trị có cardinality cao làm metric label toàn hệ thống.

## 5. Những trường nên kiểm tra sau khi aggregation

| Trường | Assertion gợi ý | Lý do |
| --- | --- | --- |
| `timestamp` | Parse được thành thời gian UTC, nằm trong khoảng hợp lý | Ngăn lỗi timezone/clock parsing |
| `observedTimestamp` | Không sớm/muộn bất hợp lý so với event time theo tolerance | Phát hiện trì hoãn hoặc clock skew |
| `service.name` | Đúng service và được map tới Resource nếu dùng OTel | Không query nhầm tất cả log theo body |
| `severity` | Đúng level, không biến WARN thành INFO | Đảm bảo filter/alert |
| `event.code` | Mã từ allowlist | Truy vấn ổn định qua thay đổi câu text |
| `eventId`/`testRunId` | Có, đúng giá trị phát | Đối chiếu và chống test lẫn nhau |
| `trace_id`/`span_id` | Đúng định dạng/phạm vi và tương quan | Pivot sang traces |
| `body` | Chuỗi sau decode đúng ý nghĩa | Tránh mất newline/quote/Unicode |
| `errorCode`/exception attributes | Chỉ xuất khi có lỗi, không bỏ thông tin cần thiết | Phân loại sự cố |
| `resource/attributes` | Đúng host/container/service/environment | Điều tra route/replica |
| `tenantRef` | Có đúng khi được phép, không lộ tenant khác | Phân quyền và data isolation |
| Forbidden fields | Không có password, bearer token, raw body/headers | Kiểm soát quyền riêng tư |

Nếu backend có JSON schema thì **parse JSON và assert kiểu field**; đừng so thứ tự key. Khi dùng OpenTelemetry, kiểm tra field nằm ở **Resource, Attributes, Body** hay LogRecord field đúng như mong đợi; một JSON key `service.name` trong body text không tự biến thành resource attribute.

## 6. Kịch bản E2E cơ bản: nguồn đến truy vấn

~~~text
[Test runner]
    │ 1. Tạo testRunId, eventId và trace ID test
    ▼
[Java app]
    │ 2. Emit N sự kiện đã phân loại an toàn
    ▼
[stdout/file/OTLP]
    │ 3. Xác minh output/encoder tại nguồn
    ▼
[agent]
    │ 4. Xác minh đã đọc/parsing/offset
    ▼
[Collector]
    │ 5. Xác minh receiver, processor, exporter
    ▼
[test backend]
    │ 6. Query theo testRunId với deadline
    ▼
[Test runner]
       7. So count, IDs, fields, privacy, độ trễ
       8. Đưa ra PASS/FAIL, thu diagnostics, cleanup
~~~

Lệnh phát log **không được dùng làm điều kiện hoàn tất duy nhất**. Nếu run bị lỗi, cần biết mất ở chặng nào; lưu lại metrics/config/logs của agent và collector cùng `testRunId` để chẩn đoán.

**Tính độc lập của test:** Mỗi lần chạy cần prefix/ID hoặc namespace riêng, dữ liệu giả riêng, giới hạn thời gian và cleanup được kiểm soát. Không query “5 dòng ERROR gần nhất” vì các test khác hoặc traffic thật có thể xen vào.

## 7. Ví dụ Java 17: pipeline E2E harness qua HTTP

Ví dụ dưới đây **chạy độc lập với JDK 17** và mô phỏng một pipeline nhiều chặng trong cùng bộ kiểm thử:

~~~text
JUL Logger
   → JsonlHandler (serialize metadata đã kiểm soát)
   → bounded queue
   → HTTP client gửi batch
   → FakeCollector tại localhost
   → in-memory list làm sink test
   → assertions
~~~

Collector giả trả HTTP `503` ở lần gọi đầu, sau đó trả `200` và lưu **hai JSONL records** vào bộ nhớ ở lần retry. Bài test xác minh nội dung, correlation ID, JSON escaping, số records và việc không đưa secret giả vào output.

**Giới hạn cần nói rõ:** Đây là **E2E của test harness** (từ Java handler đến HTTP receiver giả), **chưa bao gồm agent/Collector thực, backend index, disk persistence hay security production**. Nó thích hợp để học và làm phép kiểm nhanh khi không có Docker/Kubernetes, nhưng không thay thế test môi trường thật ở các mục tiếp theo.

### 7.1. Tạo file LoggingPipelineE2ETest.java

~~~java
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
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingPipelineE2ETest {
    record SafeEvent(String eventCode, String traceId) {}

    static String jsonString(String input) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < input.length(); i++) {
            char c = input.charAt(i);
            switch (c) {
                case '"': out.append("\\\""); break;
                case '\\': out.append("\\\\"); break;
                case '\n': out.append("\\n"); break;
                case '\r': out.append("\\r"); break;
                case '\t': out.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
            }
        }
        return out.append('"').toString();
    }

    static final class JsonlHandler extends Handler {
        final ArrayBlockingQueue<String> queue = new ArrayBlockingQueue<>(16);
        JsonlHandler() { setLevel(Level.ALL); }
        @Override public void publish(LogRecord record) {
            if (!isLoggable(record)) return;
            Object[] args = record.getParameters();
            if (args == null || args.length != 1 || !(args[0] instanceof SafeEvent)) {
                throw new IllegalArgumentException("safe event required");
            }
            SafeEvent safe = (SafeEvent) args[0];
            String json = "{"
                    + "\"timestamp\":" + jsonString(record.getInstant().toString())
                    + ",\"service.name\":\"order-service\""
                    + ",\"severity\":" + jsonString(record.getLevel().getName())
                    + ",\"event.code\":" + jsonString(safe.eventCode())
                    + ",\"trace_id\":" + jsonString(safe.traceId())
                    + ",\"body\":" + jsonString(record.getMessage())
                    + "}";
            if (!queue.offer(json)) {
                throw new IllegalStateException("test queue full");
            }
        }
        @Override public void flush() {}
        @Override public void close() {}
    }

    static final class FakeCollector implements AutoCloseable {
        final HttpServer server;
        final AtomicInteger requests = new AtomicInteger();
        final List<String> received = new CopyOnWriteArrayList<>();
        FakeCollector() throws IOException {
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/ingest", this::ingest);
            server.start();
        }
        void ingest(HttpExchange exchange) throws IOException {
            try {
                int n = requests.incrementAndGet();
                byte[] bytes = exchange.getRequestBody().readAllBytes();
                int status;
                if (!"POST".equals(exchange.getRequestMethod())) {
                    status = 405;
                } else if (n == 1) {
                    status = 503; // Deliberate transient failure.
                } else {
                    String batch = new String(bytes, StandardCharsets.UTF_8);
                    for (String line : batch.split("\\R")) {
                        if (!line.isEmpty()) received.add(line);
                    }
                    status = 200; // In-memory receipt, not a durable commit.
                }
                byte[] response = (status == 200 ? "ok" : "retry")
                        .getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(status, response.length);
                exchange.getResponseBody().write(response);
            } finally {
                exchange.close();
            }
        }
        URI endpoint() {
            return URI.create("http://127.0.0.1:" + server.getAddress().getPort()
                    + "/ingest");
        }
        @Override public void close() { server.stop(0); }
    }

    static void require(boolean valid, String what) {
        if (!valid) throw new AssertionError(what);
    }

    static void emit(Logger log, Level level, String body, SafeEvent safe,
                     String timestamp) {
        LogRecord record = new LogRecord(level, body);
        record.setLoggerName(log.getName());
        record.setInstant(Instant.parse(timestamp));
        record.setParameters(new Object[]{safe});
        log.log(record);
    }

    public static void main(String[] args) throws Exception {
        Logger log = Logger.getLogger("test.pipeline");
        boolean oldParent = log.getUseParentHandlers();
        Level oldLevel = log.getLevel();
        JsonlHandler source = new JsonlHandler();
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);
        log.addHandler(source);

        try (FakeCollector collector = new FakeCollector()) {
            String trace = "0123456789abcdef0123456789abcdef";
            String secret = "TEST_SECRET_DO_NOT_LOG";
            emit(log, Level.INFO, "order accepted",
                    new SafeEvent("ORDER_ACCEPTED", trace),
                    "2026-11-10T02:00:00Z");
            emit(log, Level.WARNING, "provider said \"retry\"\nrequest queued",
                    new SafeEvent("PAYMENT_RETRY", trace),
                    "2026-11-10T02:00:01Z");

            List<String> batch = new ArrayList<>();
            source.queue.drainTo(batch);
            require(batch.size() == 2, "source event count");
            String payload = String.join("\n", batch) + "\n";
            require(!payload.contains(secret), "secret escaped source");
            System.out.println("PASS: source produced 2 structured events");

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2)).build();
            int status = 0;
            for (int attempt = 1; attempt <= 2; attempt++) {
                HttpRequest request = HttpRequest.newBuilder(collector.endpoint())
                        .timeout(Duration.ofSeconds(3))
                        .header("Content-Type", "application/x-ndjson")
                        .POST(HttpRequest.BodyPublishers.ofString(
                                payload, StandardCharsets.UTF_8)).build();
                HttpResponse<String> response = client.send(request,
                        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
                status = response.statusCode();
                if (status == 200) break;
                require(status == 503, "unexpected HTTP status");
            }
            require(status == 200 && collector.requests.get() == 2,
                    "retry and HTTP result");
            System.out.println("PASS: HTTP 503 retried to 200");

            List<String> records = collector.received;
            require(records.size() == 2
                    && records.get(0).contains("\"event.code\":\"ORDER_ACCEPTED\"")
                    && records.get(1).contains("\"event.code\":\"PAYMENT_RETRY\"")
                    && records.stream().allMatch(v ->
                        v.contains("\"trace_id\":\"" + trace + "\"")),
                    "collector records/correlation");
            System.out.println("PASS: collector received 2 correlated events");

            require(records.get(1).contains(
                    "\"body\":\"provider said \\\"retry\\\"\\nrequest queued\"")
                    && records.stream().noneMatch(v -> v.contains(secret)),
                    "JSON escape/privacy");
            System.out.println("PASS: escaped newline/quotes and no secret");
        } finally {
            log.removeHandler(source);
            log.setUseParentHandlers(oldParent);
            log.setLevel(oldLevel);
            source.close();
        }
    }
}
~~~

**API trong ví dụ:** JUL là `java.util.logging` có sẵn; `HttpClient` thuộc `java.net.http`; `HttpServer` thuộc module `jdk.httpserver` cung cấp HTTP server nhỏ cho test. Dùng **JDK 17 đầy đủ** để biên dịch/chạy, không chỉ một runtime rút gọn đã loại module này.

### 7.2. Chạy và output chính xác

~~~bash
javac --release 17 LoggingPipelineE2ETest.java
java LoggingPipelineE2ETest
~~~

**Stdout:**

~~~text
PASS: source produced 2 structured events
PASS: HTTP 503 retried to 200
PASS: collector received 2 correlated events
PASS: escaped newline/quotes and no secret
~~~

**Stderr:** trống. **Exit code:** `0` khi mọi assertion thành công. Nếu lỗi, `AssertionError` hoặc exception khiến test thất bại.

### 7.3. Điều mà ví dụ thực sự chứng minh

- `JsonlHandler` chỉ nhận `SafeEvent`, tạo event theo schema cố định và đưa vào queue có giới hạn 16.
- Hai event được phát trước khi transport; batch được tạo từ queue và gửi bằng HTTP request.
- `FakeCollector` trả `503` lần đầu, nên shipper test thử gửi lần hai.
- Sau lần hai, server trả `200` và hai JSONL record được lưu trong **danh sách RAM**.
- Event code và `trace_id` tồn tại trong data đến đích test.
- Dòng chứa quote và newline được escape nên không tách thành log record vật lý khác.
- Secret sentinel được khai báo trong ứng dụng nhưng không được đưa vào JSON gửi đi.

### 7.4. Điều mà ví dụ chưa chứng minh

- Không có shipper đọc file/container logs, OpenTelemetry Collector thật, parse JSON chuẩn bên receiver, index hay search API.
- `FakeCollector` **không parse JSON thành dữ liệu có schema**: nó giữ raw JSONL strings. Assertion chỉ kiểm tra pattern chuỗi có ý nghĩa cho kịch bản này.
- Không có durable queue, fsync, TLS/mTLS, authorization, backup hoặc retention.
- Lần gửi đầu `503` được **định trước và không lưu gì**; bài test chưa mô phỏng trường hợp backend đã lưu nhưng ACK bị mất, dẫn tới duplicate.
- `HttpClient` và HTTP loopback hoạt động trong phạm vi process/máy test; không mô phỏng multi-node network.
- Queue 16 là test fixture; không phải giải pháp backpressure production. Nếu đầy, handler ném exception để test thất bại rõ.
- Hàm escape JSON tối giản cho bài học, không được dùng để thay thế JSON encoder đã kiểm chứng trong production.

Cần chạy thêm **một bài E2E môi trường thật** để xác minh toàn bộ các hop mà ứng dụng production sử dụng.

## 8. Chuyển từ fake receiver sang pipeline thật

Để kiểm tra hệ thống thực, chọn một đường dẫn có cấu hình rõ:

**Đường A — stdout/file → agent/filelog → Collector → backend**

~~~text
Java app
  → file .jsonl hoặc stdout/container log
  → node agent/filelog receiver
  → JSON parser + timestamp/severity mapping
  → Collector processors
  → exporter
  → backend test
  → search/query API
~~~

**Đường B — Java OpenTelemetry exporter → OTLP → Collector → backend**

~~~text
Java app + OTel logging bridge/SDK đã cấu hình
  → OTLP/gRPC hoặc OTLP/HTTP
  → Collector OTLP receiver
  → processors / exporter
  → backend test
  → search/query API
~~~

Hai đường này **không hoán đổi tự động**. Một HTTP POST `application/x-ndjson` của demo phần 7 **không phải OTLP request**; gửi trực tiếp nó tới `otlp` receiver sẽ không được xử lý như LogRecord của OpenTelemetry.

**Trước test**, ghi rõ cấu hình backend/version, đường ingress, parser, output schema, query endpoint, thời hạn và quyền. Nếu một production app ghi file nhưng test dùng direct OTLP, test có thể bỏ qua lỗi ở khâu đọc file/rotation — khi ấy chưa thực sự E2E theo đường production.

## 9. Collector filelog: ví dụ kiểm tra file JSONL

Nếu dùng OpenTelemetry Collector Contrib hoặc một distribution có **`filelog` receiver**, có thể tạo một file `app.jsonl` trong một **thư mục test** rồi đọc bằng pipeline sau:

~~~yaml
receivers:
  filelog:
    include:
      - /tmp/log-e2e-fixture/*.jsonl
    start_at: beginning
    operators:
      - type: json_parser
        parse_from: body

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    logs:
      receivers: [filelog]
      exporters: [debug]
~~~

Lưu thành `otelcol-filelog.yaml` rồi dùng binary Collector distribution có `filelog` component, cấu hình và mount path tương ứng để chạy. Ví dụ về lệnh (tên binary phụ thuộc bản phát hành):

~~~bash
otelcol-contrib validate --config=otelcol-filelog.yaml
otelcol-contrib --config=otelcol-filelog.yaml
~~~

**Điểm cần hiểu:**

- `filelog` không có trong mọi build của Collector core; kiểm tra `otelcol-contrib components` hoặc danh sách components của binary thực tế.
- `start_at: beginning` phù hợp cho fixture test mới; production có checkpoint/restart/retention và yêu cầu khác.
- `json_parser` đọc string trong `body` và mặc định có thể đặt các key parse được vào **attributes**. **Cấu hình tối giản này chưa tự map** `timestamp` và `severity` của JSON fixture vào đúng trường Timestamp/SeverityNumber của OpenTelemetry LogRecord; cần bổ sung parsing/transform theo schema.
- `debug` exporter in dữ liệu để quan sát **ở bước test**, không lưu index hoặc có search API bền vững.
- `/tmp/log-e2e-fixture/*.jsonl` là đường dẫn trong **filesystem của tiến trình Collector**. Nếu chạy trong container, phải mount directory phù hợp; đường dẫn trên host không tự xuất hiện trong container.
- File đã tồn tại trước khi collector khởi động cùng `start_at: beginning` có thể được đọc từ đầu; muốn kiểm tra checkpoint/restart, cần test riêng.
- Cần xác minh newline/rotation/partial record xử lý đúng theo agent thực tế, không chỉ parser JSON.

Để thực sự xác minh **đến kho log**, hãy thay `debug` exporter bằng exporter và test backend có hỗ trợ trong distribution, rồi query endpoint backend. Không đưa credential backend vào config commit công khai.

## 10. Collector OTLP: cấu hình khác với filelog

Đối với **OTLP request thực sự**, có thể dùng pipeline tối giản khác:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317
      http:
        endpoint: 127.0.0.1:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 256

exporters:
  debug:
    verbosity: normal

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

Đây là cấu hình **dev/test**. Một ứng dụng phải gửi **OTLP messages** qua SDK/bridge/exporter hoặc một thành phần chuyển đổi tương thích; không dùng HTTP JSONL tùy biến từ `LoggingPipelineE2ETest` để gọi `/v1/logs` như thể đó là OTLP JSON encoding.

**Kiểm thử đúng:**

1. Xác nhận ứng dụng đang dùng OTel logger provider/bridge/exporter phù hợp, không chỉ có library trong dependencies.
2. Khởi động Collector và xác minh receiver hoạt động trên endpoint mong muốn.
3. Phát event test duy nhất.
4. Dùng debug exporter để thấy nó đi qua Collector, kiểm tra mapping Resource/Attributes/Body.
5. Thay debug exporter bằng test backend exporter và query record sau index.
6. Quan sát exporter queue, retry và metrics khi backend tạm lỗi.

Chỉ bind loopback trong test local. Nếu Collector ở pod khác hoặc máy khác, cần endpoint reachable, xác thực và TLS phù hợp; không mở `0.0.0.0:4317` ra mạng ngoài một cách vô điều kiện.

## 11. Phát log qua stdout và container runtime

Trong Kubernetes, stdout/stderr của Java container thường đi qua container runtime/CRI log rồi node-level agent. Một bài E2E test phải bao gồm bước **bóc CRI envelope**, không chỉ parse JSON trực tiếp từ stdout source.

~~~text
Java JSONL stdout
    → runtime writes CRI log: timestamp stream flag body
    → agent parses CRI metadata
    → application JSON parser
    → Collector
    → backend
~~~

Các lỗi cần kiểm tra:

- **CRI partial records** do dòng dài, parser cần ghép đúng theo contract.
- Stream metadata stdout vs stderr không được coi mặc định tương đương INFO vs ERROR.
- Khi pod restart hoặc node rotate file, agent có thể bị thiếu, trùng hay đọc lại nếu checkpoint không đúng.
- Một event có newline thô trong stack trace có thể bị tách; JSONL có escaped newline giúp giữ ranh giới event nếu encoder đúng.
- Khi container bị xóa, `kubectl logs` không phải lịch sử tập trung có retention đảm bảo.
- Nếu cả file appender và stdout cùng được ship, có nguy cơ duplicate.

Không test “từ app tới collector” bằng cách bỏ qua container runtime nếu lỗi production thường nằm ở rotation, CRI parsing hoặc agent permissions.

## 12. E2E test từ file và rotation

Đối với ứng dụng Java chạy trên VM hoặc ghi file, fixture nên có:

- File JSONL UTF-8 mới tạo trong thư mục riêng.
- Event đầu và cuối có ID để xác minh parser không mất record.
- Unicode, escaped newline và exception theo schema.
- Tác động rename/rotate/truncate file theo cơ chế appender thật.
- Kiểm tra checkpoint và restart của agent.
- Test với file nhỏ và event lớn gần giới hạn parser.

Kịch bản tiêu biểu:

~~~text
T0: khởi động agent với test file path riêng
T1: ứng dụng ghi EVT-1, EVT-2
T2: xác nhận query thấy EVT-1, EVT-2
T3: rotate file bằng cơ chế appender
T4: ứng dụng ghi EVT-3 vào file mới
T5: restart agent với checkpoint
T6: xác nhận EVT-1/2/3 theo chính sách duplicate/loss
~~~

Không dùng `copytruncate` hay rename theo giả định mọi agent đều xử lý như nhau; cơ chế theo dõi inode/path, checkpoints và fallback khác nhau theo sản phẩm.

Nếu file bị xoay trước khi agent có cơ hội đọc hết, không thể khẳng định zero-loss mà không có buffer/backpressure hoặc chính sách lưu phù hợp.

## 13. Đợi event ở backend bằng deadline, không dùng sleep mù

Một E2E test tốt có **eventual assertion**: sau khi emit event, query backend theo ID cho tới khi điều kiện đúng hoặc quá deadline.

Pseudo-code trung lập với backend:

~~~java
// Pseudo-code, KHÔNG phải class Java chạy độc lập.
// queryByTestRunId là API adapter của backend test.
long deadlineNanos = System.nanoTime()
        + java.util.concurrent.TimeUnit.SECONDS.toNanos(30);

while (System.nanoTime() < deadlineNanos) {
    var records = queryByTestRunId(testRunId);
    if (records.stream().map(LogRecordView::eventId)
            .collect(java.util.stream.Collectors.toSet())
            .containsAll(expectedEventIds)) {
        verifySchemaAndPrivacy(records);
        return;
    }
    java.util.concurrent.locks.LockSupport.parkNanos(
            java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(200));
}
throw new AssertionError("Expected E2E logs did not become queryable");
~~~

Trong production test cần quản lý exception khi query và dừng poll đúng cách. Đây chỉ là **ý tưởng timeout/poll**, chưa khai báo `LogRecordView`, `expectedEventIds` và adapter.

Vì sao `Thread.sleep(1000)` rồi assert một lần là không đủ?

- Backend indexing bất đồng bộ, thời gian dao động theo CI và tải.
- Mạng và batch window có thể trễ hơn 1 giây.
- Một test đang pass trên máy cá nhân có thể flaky trên CI.
- Sleep dài cố định khiến test chậm dù log đã đến từ lâu.

**Negative assertion khó hơn positive:** “Không thấy secret” hoặc “không có duplicate” chỉ có ý nghĩa sau một mốc xử lý được chứng minh hoặc sau một **thời gian quan sát phù hợp với policy**. Nếu sink im lặng do sai cấu hình, negative test có thể PASS giả; bắt buộc có positive event cùng phạm vi.

## 14. Kiểm tra số lượng, duplicate và ordering

Giả sử phát `N=10` events với event IDs riêng:

- **Nguồn:** tất cả 10 event được tạo/capture.
- **Backend:** xác nhận cả 10 IDs xuất hiện theo scope của test.
- **Duplicate:** đếm mỗi ID; xác định contract cho phép retry trùng hay backend dedup.
- **Event order:** chỉ assert thứ tự nếu pipeline thực sự có hợp đồng thứ tự trong phạm vi đó.
- **Completeness:** kiểm tra không thiếu ID, không chỉ đếm 10 dòng bất kỳ.

Ví dụ một batch được gửi, backend đã lưu nhưng response bị mất:

~~~text
Agent sends eventId=evt-42
    → backend stores evt-42
    → response lost
    → agent retries evt-42
    → backend may now contain 2 copies
~~~

**At-least-once** giúp chống mất vì retry nhưng có nguy cơ trùng. **Exactly-once end-to-end** cần cơ chế dedup/transaction xuyên các tầng; không tự phát sinh nhờ một Collector config.

Đừng dedup theo body/timestamp một cách mù quáng: hai event nghiệp vụ khác nhau có thể hợp lệ nhưng text giống nhau. Dùng eventId và hợp đồng identity thích hợp.

**Ordering toàn cục** giữa nhiều service, partition và region thường không được đảm bảo. Với giao thức có thứ tự trong một partition/connection, test chỉ assert trong phạm vi contract đó. Đồng hồ hệ thống khác nhau còn có clock skew.

## 15. Error injection: những lỗi nên thử

| Lỗi đưa vào test | Kỳ vọng cần xác minh | Không được suy luận |
| --- | --- | --- |
| Collector trả 503 tạm thời | Shipper retry, backoff và metrics theo policy | 503 luôn có nghĩa chưa nhận dữ liệu |
| Collector trả 400/invalid schema | Record reject/quarantine rõ ràng | Retry vô hạn sẽ tự sửa data |
| Timeout/connection reset | Có outcome unknown; retry có thể tạo duplicate | Chắc chắn record chưa vào đích |
| TLS handshake/auth lỗi | Cảnh báo và không lộ credential | Nên tắt TLS để test pass |
| Collector restart giữa batch | Checkpoint/queue/routing phục hồi theo contract | Không có mất/trùng nếu không có durable queue |
| Disk full trên agent | Thấy error/drop/backpressure, không im lặng | Tăng buffer RAM mãi là an toàn |
| Backend rate limit | Queue giới hạn, retries, alert | Không ảnh hưởng độ trễ business |
| Backend index reject | Event có thể đã đến exporter nhưng không queryable | HTTP 200 phía Collector là đủ |
| Rotation file giữa chừng | Cursor/checkpoint theo đúng cơ chế sản phẩm | Mọi file tail hoạt động như nhau |
| Pod bị kill cưỡng bức | Loss theo mức được công bố, recovery nếu có | Shutdown hook luôn flush được |
| Processor drop/mask sai | Detect event/field bị mất hoặc lộ secret | Debug exporter chắc chắn giống output cuối |
| Collector OOM/restart | Health/queue/drop metrics cảnh báo | Đã nhận request là đã durable |

**Không thực hiện chaos tests phá hoại trên production** mà chưa có quy trình và phạm vi cô lập. Nên dùng test namespace, mock server, test broker hoặc môi trường staging với data giả và kế hoạch cleanup.

## 16. Retry, backoff và backpressure: test đúng ngữ nghĩa

Một pipeline vận chuyển có thể dùng queue, batching, retries và backpressure. E2E test cần kiểm tra **quyết định khi không thể gửi**.

- Khi lỗi 503 ngắn hạn, có retry theo retryable status policy, tối đa số lần hoặc thời gian được định nghĩa.
- Khi lỗi 400 do schema sai, retry cùng payload có thể vô ích; cần reject/quarantine và metric rõ ràng.
- Khi queue đầy, policy phải là block, drop, spool disk hoặc fail theo sự kiện; không bịa zero-loss.
- Khi broker/backend chậm, hàng đợi không được phình vô hạn gây OOM.
- Khi shutdown, chờ flush/drain nếu còn thời gian; kill cưỡng bức không cho chương trình tiếp tục flush.
- Khi response ACK bị mất, retry có thể tạo duplicate, cần IDs/dedup theo contract.

Với một test **HTTP receiver giả**, log retry count và status thực tế để tránh đoán. Bài demo thực hiện **retry đúng một lần** sau `503`; nó không có exponential backoff vì đây chỉ là fixture chạy nhanh, **không phải policy sẵn sàng cho production**.

Thử hai loại test riêng: “503 trước khi commit” và “commit xong nhưng ACK bị mất”. Kết quả delivery semantics khác nhau dù caller đều thấy lỗi.

## 17. Kiểm tra tính đúng đắn của timestamp và correlation

Pipeline có thể làm sai thời gian:

- Java phát ISO 8601 UTC nhưng parser hiểu theo timezone máy Collector.
- Agent gán thời điểm đọc file thay cho event timestamp.
- Collector overwrite timestamp ở stage enrichment.
- Backend query theo ingest time nhưng dashboard hiển thị event time.
- Lệch clock giữa node gây “event xảy ra trước request”.

Test nên giữ và so:

~~~text
event.timestamp
collector.observed_timestamp
backend.ingested_at
trace_id / request_id
event_id
~~~

Giá trị `ingestLatencyMs` có thể tính giữa các mốc **khi clock đã đồng bộ hoặc có tolerance phù hợp**. Không lấy chênh lệch tuyệt đối giữa hai host chưa đồng bộ để chứng minh latency chính xác từng mili giây.

Với OpenTelemetry, `TraceId` và `SpanId` là fields chuyên biệt của LogRecord; nếu chỉ có chuỗi `trace_id` trong attributes/body, backend có thể không hỗ trợ tự động log-to-trace link. Test phải xác minh mapping thực tế, không chỉ `contains(traceId)`.

**Lưu ý bảo mật:** trace ID/correlation ID có khả năng liên kết nhiều hoạt động, có thể thuộc phạm vi dữ liệu cần bảo vệ. Không đưa email, bearer token hoặc raw user ID vào baggage chỉ để nối các log.

## 18. Structured logs: parse, transform và schema compatibility

Một E2E test cần assert **ngữ nghĩa dữ liệu sau parser**, không chỉ chuỗi gốc.

Ví dụ source có:

~~~json
{"timestamp":"2026-11-10T02:00:00Z","severity":"WARNING","event.code":"PAYMENT_RETRY","attempt":2,"credentialPresent":false}
~~~

Sau Collector, contract có thể yêu cầu:

- `timestamp` thành event time, không phải body string.
- `severity` được chuẩn hóa đúng mapping JUL WARNING → WARN tương ứng.
- `event.code` thành attribute có kiểu string.
- `attempt` vẫn là number, `credentialPresent` vẫn là boolean.
- `service.name` nằm trong Resource nếu dùng OpenTelemetry.
- `Body` là message hoặc object theo schema đã chọn, không tự động chứa mọi attribute.

Nếu schema thay đổi từ `event.code` sang `eventCode`, phải quyết định version, alias hay migration cho query. Không âm thầm thay key trong một collector processor rồi để dashboard mất dữ liệu.

**Multiline:** Một exception có stack trace nhiều dòng. Text-file tail cần multiline parser; structured JSONL đúng encoder giúp một event nằm trong một dòng vật lý. Test cả newline, quote, backslash, Unicode và record dài/partial records theo runtime thực tế.

## 19. Privacy và bảo mật trong E2E pipeline

Log tập trung có thể chứa dữ liệu từ nhiều hệ thống và nhiều tenant. Vì thế test dữ liệu nhạy cảm phải chạy **từ nguồn đến đích cuối**, không chỉ test một hàm masking.

Dùng sentinel **giả** có độ đặc trưng cao, ví dụ `TEST_SECRET_DO_NOT_LOG`; không đưa API key thật, password thật hay PII production vào fixture.

Kiểm tra:

1. Source event không chứa password, token, full HTTP headers hoặc raw request body.
2. Regex/transform ở agent/Collector không làm lộ giá trị ở key mới.
3. Exception message, stack trace, MDC/ThreadContext, suppressed/cause không bị bỏ sót.
4. JSON serializer escape CR/LF/quotes, không tạo event giả bằng log injection.
5. Backend index/query/export không chứa sentinel trong bất cứ field, raw message hoặc attributes nào.
6. Không xuất secret vào debug exporter, processor error logs, retry dead-letter/quarantine hay metrics labels.
7. Quyền đọc log đúng tenant và role; user không được phép không đọc được records.
8. Dữ liệu lưu/backup/export được áp retention và encryption policy riêng.

Một **negative assertion** (không tìm thấy token) phải đi kèm **positive assertion** (tìm thấy event ID an toàn vừa phát) để tránh PASS giả khi pipeline bị hỏng và không nhận gì.

Không đồng nhất mask ở UI dashboard với xóa dữ liệu gốc trong index, queue, backups hoặc các bản export trước đó.

## 20. Load test, latency và sampling

E2E test không chỉ có một record. Với hệ thống có throughput lớn, kiểm tra:

- Số event/s source và sink trong cùng cửa sổ quan sát.
- Độ trễ p50/p95/p99 từ source đến searchable, có phân biệt clock skew.
- Queue depth, dropped records, retry rate và exporter failures.
- CPU/heap/GC của Java service, shipper/Collector CPU/memory.
- Tốc độ ghi disk, dung lượng spool, checkpoint lag.
- Batch size, batch timeout và network utilization.
- Tỉ lệ parser rejects, truncated events, oversized records.
- Query latency và index size của backend.
- Sampling strategy và rate limiting khi bật DEBUG/TRACE.

**Sampling:** Nếu pipeline chỉ lấy 10% DEBUG events, một E2E test không thể yêu cầu mọi DEBUG event được lưu. Test cần biết **policy** và dùng các event chắc chắn không bị sampling (hoặc kiểm tra tỷ lệ thống kê với sample đủ lớn).

**Audit bắt buộc** không nên được đưa vào pipeline chỉ có bảo đảm sampling/best-effort nếu chính sách yêu cầu lưu đầy đủ. Cần durable recorder/outbox/audit store và test riêng.

## 21. Đo sức khỏe của chính pipeline

Pipeline có thể im lặng mất log ngay cả khi app vẫn xử lý request. Do đó cần metrics của nguồn và từng hop.

| Stage | Metrics nên theo dõi | Tín hiệu cảnh báo |
| --- | --- | --- |
| Java application | Tổng event được tạo/filtered, appender drops, queue fill | Logger disabled ngoài ý định, queue overflow |
| Agent/file tail | Files read, bytes/records, cursor lag, parse errors | Không đọc file mới, rotation bỏ sót |
| Collector receiver | Accepted/rejected log records | Source gửi nhưng receiver không tăng |
| Processor | Filtered/dropped records, parse/transform failures | Event bị loại hoặc schema sai |
| Exporter | Sent/failed records, retry count, pending queue | Backend unavailable, queue tăng liên tục |
| Backend | Ingest rate, rejected docs, indexing delay | Export thành công nhưng record không query được |
| Search UI/API | Query errors, latency, auth failures | Người dùng không tra cứu được hoặc scope sai |

Các **tên metric cụ thể phụ thuộc version/distribution**. OpenTelemetry Collector có internal telemetry về số lượng accepted/refused/sent/failed records và queue; cần xem tài liệu và metrics hiện có trên bản đang chạy, không hard-code một tên metric suy đoán rồi kết luận không có dữ liệu.

Cân nhắc **canary log event định kỳ** trong hệ thống giám sát pipeline, với ID/timestamp duy nhất và alert khi quá deadline không thấy ở sink. Nhưng canary phải có giới hạn tần suất, không chứa secret và không thay thế số liệu của traffic thật.

## 22. Thiết kế test CI/staging có thể lặp lại

Một pipeline E2E nên chạy trong môi trường tách biệt và có lifecycle rõ:

~~~text
CI job
  ├─ cấp testRunId và dựng temp namespace/filesystem
  ├─ start backend test + Collector/agent phù hợp
  ├─ kiểm tra readiness và config validation
  ├─ chạy Java app phát fixture events
  ├─ await ingest/search với deadline
  ├─ verify IDs/count/schema/security/correlation
  ├─ fault injection nếu thuộc scenario
  ├─ lưu diagnostics đã loại secrets khi FAIL
  └─ stop containers / xóa dữ liệu test
~~~

**Không phải mọi bước đều chạy trong cùng một process**. Ví dụ `LoggingPipelineE2ETest` chỉ đủ cho “Java handler → HTTP fake receiver” ở mức developer check. Trong CI nâng cao, dùng một test backend có API query độc lập và Collector distribution thật.

**Giữ test reproducible:**

- Pin phiên bản Java, appender, Collector distribution, backend image trong CI khi cần.
- Dùng config versioned và validate trước chạy.
- Không dùng chung root logger và file log production.
- Không dùng chung testRunId giữa các CI jobs.
- Đợi health/readiness thật thay vì sleep cố định.
- Đặt timeout theo từng hop và toàn bài test.
- Cleanup ở `finally`/CI post-job; không xóa tài nguyên ngoài scope.
- Mask secrets khi lưu logs của test runner để phục vụ debug.

Nếu test dùng network port tự cấp, in địa chỉ trong diagnostics nội bộ khi cần nhưng không đưa credential vào log. Nếu endpoint chỉ dành cho test local, bind loopback và hạn chế quyền.

## 23. E2E test filelog trên Kubernetes: các tình huống phải có

Khi production chạy Kubernetes, nên bổ sung các scenarios:

| Scenario | Hoạt động kiểm thử | Kỳ vọng |
| --- | --- | --- |
| Pod bình thường | Phát hai JSONL events | Agent nhận và backend query đúng ID |
| Pod restart | Restart app sau emit | Event đã ship còn truy vấn được, pending theo contract |
| Node agent restart | Restart DaemonSet agent | Checkpoint không tạo mất/trùng ngoài mức công bố |
| Log rotation | Ghi gần giới hạn rồi rotate | Agent vẫn đọc được records sau rotate |
| Partial CRI record | Một event rất dài | Parser ghép đúng hoặc reject/quarantine có metric |
| Stack trace multiline | Exception nhiều dòng | Một log event logic, không tách thành nhiều ERROR giả |
| Mixed stdout/stderr | Hai streams | Giữ stream labels, không nhầm severity mặc định |
| Pod scaling | N instance phát đồng thời | Metadata instance đúng, không query lẫn |
| Multi-tenant | Hai namespaces/tenants | Query bảo vệ scope, không đọc chéo |
| Node disk pressure | Agent không kịp ship | Cảnh báo/drop/backpressure theo policy |

Không chạy các test gây áp lực lớn trực tiếp trên cluster production. Với staging, giới hạn rõ namespace, tài nguyên, thời gian và số log phát ra.

Lưu ý: Kubelet/container runtime có giới hạn lưu cục bộ và cơ chế rotate; `kubectl logs` chỉ hỗ trợ chẩn đoán, không phải đảm bảo lưu log tập trung lâu dài.

## 24. Runbook khi E2E test thất bại

Khi test phát event nhưng query cuối không thấy, truy từ nguồn tới đích:

1. **JVM:** có tạo event đúng không? Level/filter/appender có nhận? `LogRecord` có body/fields an toàn? 
2. **Sink:** stdout/file/OTLP gửi đi chưa? Có flush, bounded queue và lỗi ghi không?
3. **Container/file:** CRI format, permission, rotate hoặc partial log có ảnh hưởng không?
4. **Agent:** include/exclude path, checkpoint, cursor, parse errors, batch pending có đúng không?
5. **Collector:** receiver có được khai báo **và** dùng trong `service.pipelines.logs` không? Processor có filter/drop/transform sai không?
6. **Exporter:** endpoint/TLS/token/quota/retry/queue có lỗi không? Lỗi gửi có được giám sát không?
7. **Backend:** nhận request rồi có parse/index không? Query index/tenant/time window đã đúng chưa?
8. **Dashboard:** timezone, field mapping và quyền có che hoặc làm query lọc nhầm không?

Bảng hướng dẫn nhanh:

| Triệu chứng | Giả thuyết đầu tiên | Bằng chứng nên lấy |
| --- | --- | --- |
| JVM có log, stdout không có | Appender filter/route khác, async chưa flush | Appender config và source metrics |
| stdout có, collector không | Agent chưa tail, CRI parse lỗi, quyền file | Agent metrics, file cursor |
| Collector debug exporter thấy, backend không | Exporter auth/network/schema/index reject | Exporter logs, backend ingest errors |
| Backend có record nhưng query theo ID không ra | Field mapping sai hoặc query nhầm tenant/time | Raw indexed document, mapping và query |
| Event trùng 2 lần | Ship hai source hoặc retry sau ACK mất | Source labels, event ID, exporter retries |
| Chỉ thiếu WARN | Severity mapping/filter sai | LogRecord raw, pipeline processors |
| Timestamp rất xa hiện tại | Locale/timezone/parser hoặc clock skew | Event/observed/index timestamps |
| Newline tạo thêm log records | JSON escape hoặc multiline handling sai | Raw bytes/filelog parser |
| Secret xuất hiện tại backend | App log raw, layout chưa redact hoặc đường ship khác | Chuỗi sự kiện và đầu ra từng hop |
| Test chỉ fail trên CI | Async timing, shared state, fixed sleep | Deadline logs, testRunId, readiness |

Không tăng `queueSize` hoặc thời gian sleep vô hạn để “chữa” test hỏng trước khi biết mốc nào mất dữ liệu.

## 25. Các anti-patterns trong kiểm thử log end-to-end

| Anti-pattern | Vì sao nguy hiểm | Giải pháp |
| --- | --- | --- |
| Chỉ verify `logger.info` rồi gọi E2E | Không test vận chuyển | Query ở sink cuối |
| Xem HTTP `200` là durable commit mặc định | ACK có ngữ nghĩa khác nhau | Đọc hợp đồng endpoint và test persistence |
| Gửi JSONL vào OTLP receiver | Sai giao thức | Filelog/agent hoặc OTLP exporter thực |
| Query “latest ERROR” | Nhiễu từ test khác | Unique testRunId/eventId |
| So một log message string tự do | Dễ vỡ do format/locale | Assert typed fields và event code |
| Test bằng `Thread.sleep(1000)` | Flaky theo tải | Poll/await với deadline |
| Negative test không có positive control | PASS giả khi pipeline chết | Xác minh event an toàn có mặt |
| Không kiểm tra duplicate | Retry gây đếm sai | So distinct event IDs và count |
| Khẳng định global ordering | Multi-thread/multi-node có thể đảo thứ tự | Test theo phạm vi ordering contract |
| Không test file rotation | Mất records khi agent restart/rename | Test checkpoint + rotation |
| Bỏ qua container wrapper | JSON parser nhận CRI envelope | Parse CRI trước ứng dụng JSON |
| Cho rằng `start_at: beginning` là policy production | Có thể đọc lại log cũ, duplicates | Chọn policy/checkpoint rõ |
| Dùng debug exporter như durable backend | Chỉ in dữ liệu để thử | Test storage và query riêng |
| Không cô lập network và tài nguyên | Gây nhiễu hoặc ghi vào production | Local/test namespace, fake secrets |
| Log raw payload “để kiểm chứng” | Rò PII/token và phí ingest | Structured safe fields và sentinel giả |
| Retry 400 vô hạn | Không cải thiện malformed record | Quarantine/reject với metric |
| Nói “không mất log” khi queue là RAM | Crash làm mất pending records | Durable buffer nếu yêu cầu, test crash |
| Không theo dõi sức khỏe pipeline | Mất log im lặng | Internal metrics, canary và alert |

## 26. Checklist thực thi một E2E test đúng nghĩa

1. Có sơ đồ rõ nguồn → sink → agent → Collector → backend → query không?
2. Có một **testRunId** và **eventId** duy nhất cho mỗi lần test không?
3. Có xác định hợp đồng success: received, exported, searchable hay durable không?
4. Có cấu hình schema/version, timestamp, severity, Resource và attributes không?
5. Có kiểm thử JSON escaping, Unicode, multiline và event size không?
6. Có test thực tế trên đường production: stdout/file + agent hoặc OTLP, không thay thế nhầm không?
7. Nếu dùng filelog, Collector binary có component và path/mount đúng không?
8. Receiver có thực sự xuất hiện trong `service.pipelines.logs` không?
9. Có xác minh processor mapping và exporter tới backend thật trong test tích hợp không?
10. Có query bằng ID với deadline và kiểm tra toàn bộ expected event IDs không?
11. Có kiểm tra duplicate, dropped/rejected events, retry và outcome unknown không?
12. Có phân biệt callback/HTTP ACK với backend index hoặc durability không?
13. Có theo dõi queue, sender/receiver/exporter metrics và parsing failures không?
14. Có test collector outage, malformed record, rotation và agent restart trong phạm vi rủi ro không?
15. Có positive control cho mọi negative assertion, nhất là kiểm tra secret không lộ không?
16. Có kiểm tra quyền xem/export log theo tenant và retention policy không?
17. Có cleanup có kiểm soát và không dùng secrets hay dữ liệu người thật không?
18. Có lưu diagnostics an toàn khi CI FAIL và kịch bản khôi phục không?
19. Có tránh dựa vào clock toàn cục hoặc thứ tự event không được bảo đảm không?
20. Có ghi rõ những gì test **không chứng minh**, đặc biệt durability khi crash/power loss không?

## 27. Câu hỏi tự kiểm tra

1. Tại sao một mock test `logger.info(...)` pass vẫn chưa chứng minh Collector hoạt động?
2. Phân biệt `received by collector`, `exported` và `queryable`.
3. Tại sao `testRunId` phải duy nhất giữa các CI jobs?
4. `eventId` giúp phát hiện duplicate như thế nào?
5. Vì sao một JSONL body không tự thành OpenTelemetry LogRecord qua OTLP receiver?
6. Với `filelog`, vai trò của `include`, `start_at` và `json_parser` là gì?
7. Tại sao `json_parser` không mặc nhiên map timestamp/severity vào chuẩn OTel nếu không cấu hình thêm?
8. Bài Java17 `LoggingPipelineE2ETest` có dùng Collector thật hoặc backend index không?
9. Vì sao một status `503` sau request có thể dẫn đến duplicate khi retry?
10. Một query không tìm thấy event sau 500 ms có chứng minh record bị mất không?
11. Tại sao test “không chứa token” cần đồng thời test event xuất hiện?
12. Khi đổi timezone hoặc clock skew, điều gì ảnh hưởng đến query theo thời gian?
13. Trong Kubernetes, agent phải xử lý các yếu tố CRI/rotation nào?
14. Khi backend index từ chối document vì schema, metrics hop nào giúp phát hiện?
15. Khi nào cần durable queue thay vì memory queue?
16. Có thể dùng một số `trace_id` như event ID độc nhất cho mọi log event không?
17. E2E test “hai records, một lần retry” có chứng minh exactly-once end-to-end không?
18. Tại sao nên giám sát Collector bằng internal telemetry và canary?

**Gợi ý đáp án:** (1) còn thiếu mọi hop sau Java; (2) các mốc khác nhau, chỉ query được khi backend đã xử lý; (3) tránh đọc log cũ/test khác; (4) đếm số bản theo ID; (5) khác giao thức và data model; (6) chọn file, vị trí đọc và parse; (7) phải mapping cụ thể; (8) không, fake receiver lưu RAM; (9) ACK có thể mất sau khi backend nhận; (10) chưa, ingestion bất đồng bộ; (11) pipeline chết cũng khiến không thấy token; (12) event/index time/query window; (13) envelope, partial records, checkpoint, rotate; (14) exporter/backend ingest; (15) khi cần chống mất khi process restart/crash theo contract; (16) không, một trace nhiều events; (17) không; (18) nhận biết pipeline lỗi im lặng.

## 28. Tài liệu tham khảo chính thức

- [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/): cấu trúc `receivers/processors/exporters/service.pipelines`, cấu hình và validation.
- [OpenTelemetry — Collector Components](https://opentelemetry.io/docs/collector/components/): receiver, processor, exporter, connector và distribution.
- [OpenTelemetry — Collector Troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/): debug exporter, internal telemetry, chẩn đoán dữ liệu mất trong pipeline.
- [OpenTelemetry Collector Contrib — filelog receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/filelogreceiver/README.md): `include`, `start_at`, tailing/checkpoints.
- [OpenTelemetry Collector Contrib — json_parser operator](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/pkg/stanza/docs/operators/json_parser.md): `parse_from`/`parse_to`, timestamp/severity handling.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): timestamp, observed timestamp, body, severity, Resource, attributes, TraceId.
- [OpenTelemetry — Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/): `service.name` và những trường resource/telemetry.
- [Kubernetes — Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/): stdout/stderr, CRI logs, node agent, sidecar, log rotation.
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): logger, levels và LogRecord.
- [Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `publish`, `flush` và lifecycle.
- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): message, parameters, timestamp và metadata.
- [Java SE 17 — java.net.http.HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client dùng trong harness.
- [Java SE 17 — jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): HTTP server để test.
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html): console/file/async, flush và lifecycle.
- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html): logging sinks, buffering và flush.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): log injection, dữ liệu nhạy cảm, vận chuyển/lưu trữ an toàn.

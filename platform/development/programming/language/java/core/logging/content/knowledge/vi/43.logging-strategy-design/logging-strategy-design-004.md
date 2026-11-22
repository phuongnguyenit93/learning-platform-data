# Chọn field chuẩn trong chiến lược logging Java

## 1. Vì sao phải thống nhất field?

**Chọn field chuẩn** là quyết định **tên, kiểu dữ liệu, ý nghĩa, nguồn tạo, điều kiện xuất hiện và mức bảo vệ** cho mỗi trường trong bản ghi log. Một dòng log Java chỉ ghi `"Lỗi xảy ra"` khó cho phép dashboard truy vấn, nhóm lỗi hoặc nối với trace. Ngược lại, một sự kiện có nhiều field không kiểm soát có thể tốn tài nguyên và làm lộ dữ liệu nhạy cảm.

Ví dụ hai service cùng ghi về HTTP request nhưng dùng tên không thống nhất:

```text
orders-api: requestId=req_42 code=503 took=17
billing-api: req_id=req_42 httpStatus="503" elapsed=17000000
```

Không có hợp đồng thì người đọc không biết `took` và `elapsed` có cùng đơn vị hay không, trạng thái là số hay chuỗi, `requestId` và `req_id` có cùng nguồn đáng tin hay không.

Đích đến là **event schema** ổn định, có thể parse, test, lọc, tính metric và tương quan với logs/traces khác mà không cần suy đoán từ câu message. Bài học thuộc nhóm **Thiết kế chiến lược log**, áp dụng với JUL, SLF4J, Logback, Log4j 2 và OpenTelemetry trong hệ sinh thái Java.

Sau bài này, bạn có thể:
- Phân biệt core envelope, resource, correlation và event-specific fields.
- Chọn timestamp, severity, event code, service/environment/version, trace/span ID, error type, HTTP/messaging attributes và duration.
- Biết phần nào là **OpenTelemetry Logs Data Model**, phần nào là **Elastic Common Schema (ECS)** và phần nào chỉ là quy ước JSON của ứng dụng.
- Định nghĩa kiểu dữ liệu, đơn vị, null/optional/conditional fields, enum và schema version.
- Tránh token/PII/raw payload và high-cardinality index labels.
- Viết ví dụ Java 17+ đầy đủ, kiểm tra JSON emitted và test chống log injection.
- Thiết kế migration và bộ kiểm thử schema từ call site đến collector/dashboard.

## 2. Bốn nhóm field và mức cần thiết

| Nhóm | Ví dụ | Khi nào cần? |
| --- | --- | --- |
| **Core envelope** | timestamp, severity, event name hoặc message | Hầu hết event; dùng để biết khi nào và chuyện gì |
| **Resource** | service.name, service.version, deployment.environment.name | Mô tả nguồn phát log; lấy từ deploy/config |
| **Correlation** | request/correlation ID, trace ID, span ID | Khi một event thuộc request, job hoặc trace |
| **Event-specific** | http.route/status/duration, Kafka topic/partition/offset, error.type | Chỉ khi event liên quan và dữ liệu có ý nghĩa |

Không áp dụng tất cả field cho tất cả events. `service.started` không có `http.route`; `message.processing.failed` có thể có Kafka offset nhưng không có HTTP status. Một field **không áp dụng** thường nên được omit thay vì điền giá trị giả.

Ví dụ schema JSON do ứng dụng định nghĩa:

```json
{
  "timestamp": "2026-11-10T00:00:00Z",
  "severity_text": "ERROR",
  "event_name": "http.server.request.completed",
  "service.name": "orders-api",
  "deployment.environment.name": "production",
  "http.request.method": "GET",
  "http.route": "/orders/{id}",
  "http.response.status_code": 503,
  "duration_ms": 17,
  "correlation_id": "req_42",
  "error.type": "upstream_timeout"
}
```

**Quan trọng:** Đây là **JSON format của ứng dụng**, không tự động là payload OTLP chuẩn chỉ vì tên field trông giống OpenTelemetry. Nếu xuất OTLP, cần map timestamp, severity và event name vào trường tương ứng của LogRecord, `service.name` vào Resource và các thuộc tính HTTP vào Attributes.

## 3. OpenTelemetry Logs Data Model: trường nào thuộc lớp nào?

OpenTelemetry LogRecord có các thành phần được định nghĩa riêng:

| Thành phần | Ý nghĩa | Cách map từ JSON ứng dụng |
| --- | --- | --- |
| `Timestamp` | Thời điểm sự kiện xảy ra | `timestamp` |
| `ObservedTimestamp` | Thời điểm observer/collector thấy event | Đặt ở pipeline/observer khi có |
| `SeverityText` | Text level như INFO/WARN/ERROR | `severity_text` |
| `SeverityNumber` | Level theo thang OTel | Map từ logging framework; không dùng nguyên số JUL |
| `EventName` | Tên kiểu event ổn định | `event_name` |
| `Body` | Nội dung dễ đọc/cấu trúc | `message` hoặc body đã cho phép |
| `Resource` | Nguồn phát | `service.name`, `service.version`, environment |
| `InstrumentationScope` | Scope/logger tạo record | Logger name/library, nếu có |
| `Attributes` | Thuộc tính riêng của từng event | `http.route`, duration, error.type |
| `TraceId`, `SpanId`, `TraceFlags` | Trace context | Chỉ khi hợp lệ và có active span |

### Timestamp và observed timestamp

Một event được tạo ở JVM lúc `10:00:00.000Z` nhưng collector nhận lúc `10:00:00.200Z`. Hai mốc này **không giống nhau**. Nếu dashboard dùng thời gian ingest để thay thời gian gốc, điều tra trễ log và thứ tự sự kiện có thể sai. Ngược lại, event timestamp cũng có thể bị lệch do clock skew trên host.

Dùng UTC với `Instant`/ISO 8601 hoặc timestamp typed đúng backend. Khi tính duration trên cùng JVM, dùng `System.nanoTime()` thay vì lấy hai wall-clock timestamps trừ nhau. Đồng bộ đồng hồ hạ tầng và xác nhận parser không đổi timestamp sang timezone khác.

### SeverityText và SeverityNumber

Mỗi Java framework dùng thang level riêng:
- JUL: `FINE`, `INFO`, `WARNING`, `SEVERE`.
- SLF4J/Logback: `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`.
- OTel: các dải `SeverityNumber` có định nghĩa riêng.

Đừng coi số level của JUL chính là OTel SeverityNumber. Dùng mapper thống nhất của bridge/backend. `severity_text` là mức quan tâm, **không đồng nghĩa** `http.response.status_code` hoặc business outcome. Một `404` hợp lệ có thể log ở INFO, còn `503` do upstream timeout có thể ERROR theo chính sách dịch vụ.

### Event name khác message

```text
event_name=order.reservation.failed
error.type=out_of_stock
message="Inventory reservation rejected"
```

`event_name`/`error.type` phục vụ máy, ổn định và có tập giá trị kiểm soát; `message` là mô tả người đọc, có thể thay đổi câu chữ, locale hoặc thêm ngữ cảnh. Không tạo tên event bằng cách nối message, order ID hoặc trace ID:

```text
# Sai: event_name=order.42.failed
# Đúng: event_name=order.processing.failed
```

## 4. Bộ core fields nên chọn

| JSON field đề xuất | Kiểu | Chính sách |
| --- | --- | --- |
| `timestamp` | ISO 8601 UTC string hoặc timestamp type | Ghi thời điểm xảy ra, có timezone |
| `severity_text` | enum/string | Chuẩn hóa log level |
| `event_name` | string enum | Tên sự kiện ổn định |
| `message` | string tùy chọn | Ngắn gọn, không chứa secret/raw DTO |
| `service.name` | string | Đến từ deploy/resource config |
| `service.version` | string | Phân biệt release/rollback |
| `deployment.environment.name` | string | test/staging/production theo policy |
| `logger.name` | string | Khi cần xác định code component/scope |
| `correlation_id` | string safe ID | Khi có request/job ID độc lập |
| `trace_id`, `span_id` | IDs chuẩn | Khi thực sự có tracing context |
| `error.type` | enum low-cardinality | Khi lỗi |
| `duration_ms` | long không âm | Khi operation đã có thời gian xử lý |
| `http.response.status_code` | integer 100–599 | Khi có response status |
| `http.route` | route template | Khi web router biết route |

**Không phải mọi key trên là OTel top-level field.** Chúng thuộc hợp đồng JSON của ứng dụng, sau đó backend/bridge map sang OTel/ECS. Tránh viết tên y hệt OTel nhưng gán kiểu/ngữ nghĩa khác.

### Tên field

- Chọn một convention cho custom keys (`snake_case` hoặc namespace `app.*`); giữ nguyên key semantic convention khi tích hợp OTel.
- Không đồng thời tồn tại `requestId`, `req_id`, `request_id` cho một ý nghĩa nếu không có kế hoạch migration.
- Không dùng key `status` cho HTTP code, business status và job state. Dùng `http.response.status_code` và `business.outcome` riêng.
- Không nhét giá trị runtime vào field name (ví dụ key `user_42`), sẽ làm schema phát triển vô hạn.
- Nếu field do collector/encoder thêm, kiểm tra collision với field do ứng dụng cung cấp.
- Phân biệt tên field nguồn và tên trường đích trong mapping tài liệu.

### Kiểu dữ liệu và đơn vị

| Sai | Đúng hoặc rõ nghĩa hơn |
| --- | --- |
| `"status":"503"` khi cần tính theo số | `"http.response.status_code":503` |
| `"duration":"17ms"` | `"duration_ms":17` |
| `"retryable":"true"` | `"retryable":true` |
| `"timestamp":"10/11/26 07:00"` | `"timestamp":"2026-11-10T00:00:00Z"` |
| `"attempt":"third"` | `"retry_attempt":3` |
| `"trace_id":"null"` | Omit hoặc JSON null theo contract |
| `"http.route":"/users/58392"` | `"http.route":"/users/{id}"` |

**Chỉ đổi tên không đủ để đổi đơn vị.** ECS `event.duration` được định nghĩa bằng **nanoseconds**: 17 ms phải map thành 17.000.000 ns, không giữ giá trị 17 rồi đặt tên ECS.

## 5. Required, conditional, optional và unknown

Một schema nên ghi rõ quy tắc:
- **Required toàn event:** timestamp, service, environment, event name hoặc message theo hợp đồng nội bộ.
- **Conditional:** HTTP status nếu đã gửi/biết response; `error.type` khi event là failure; trace ID nếu có active span.
- **Optional:** instance ID, deployment version, route nếu router chưa xác định được.
- **Forbidden:** password, token, raw request body hoặc dữ liệu nhạy cảm không được duyệt.

Ba trạng thái cần phân biệt:
1. **Không áp dụng:** event startup không có HTTP route → bỏ trường.
2. **Chưa biết:** request chưa hoàn thành → event started/unknown có contract riêng; không điền 200.
3. **Giá trị hợp lệ bằng 0:** duration có thể được làm tròn về 0 ms → không xử lý như missing.

Đừng ghi chuỗi `"null"` để đại diện cho không có trace. Đừng tạo ID toàn số 0 rồi coi là trace ID hợp lệ. Nếu correlation ID từ client sai, nên từ chối hoặc sinh ID mới an toàn, đồng thời ghi nhận invalid input ở metric riêng.

## 6. Correlation ID, request ID và trace/span ID

### Correlation ID

Một `correlation_id` do ứng dụng/ingress sinh giúp truy từ access log sang application log và background task. Nó **không phải** định danh người dùng và không được chứa token/email. Input từ header như `X-Request-ID` là dữ liệu không tin cậy; cần giới hạn độ dài, tập ký tự và nguồn tin cậy, tránh CR/LF injection.

### Trace/Span ID

Trace ID W3C thường là 16 byte hiển thị bằng 32 ký tự hex; span ID là 8 byte hiển thị 16 ký tự hex. Không gán `req_42` vào trường OTel `TraceId` chỉ vì nó liên kết request. Với ECS, các key tương ứng là `trace.id` và `span.id`; OTel dùng top-level `TraceId`/`SpanId`. Nếu dự án dùng JSON `trace_id`, phải có mapping rõ.

**Chỉ gắn trace context có thật.** Khi không có active span, không bịa trace ID. Nếu sampling khiến trace backend không giữ span, log vẫn có thể có trace context, nhưng link đến trace sẽ không mở được. Với thread pool, async logging, message consumer và virtual thread, context propagation phải được test thực tế.

### MDC/ThreadContext

Một đoạn tích hợp SLF4J, cần thư viện SLF4J trong classpath:

```java
String previous = org.slf4j.MDC.get("correlation_id");
try {
    org.slf4j.MDC.put("correlation_id", validatedRequestId);
    performBusinessOperation();
} finally {
    if (previous == null)
        org.slf4j.MDC.remove("correlation_id");
    else
        org.slf4j.MDC.put("correlation_id", previous);
}
```

Đoạn này **không chạy độc lập** vì `performBusinessOperation` và `validatedRequestId` thuộc ứng dụng. Không copy toàn bộ MDC/headers; một thư viện khác có thể đã nhét PII vào context. Khi exporter async gửi log sau, phải snapshot context tại thời điểm event phát sinh, không lấy MDC của worker lúc gửi.

## 7. HTTP fields và tính an toàn của route

OpenTelemetry HTTP semantic conventions định nghĩa những field như:
- `http.request.method`: GET, POST... hoặc giá trị đã chuẩn hóa theo instrumentation.
- `http.route`: **template route**, ví dụ `/orders/{id}`, khi framework thực sự xác định được.
- `http.response.status_code`: integer nếu status đã được gửi/nhận.
- `error.type`: loại lỗi có cardinality thấp khi operation có lỗi theo hợp đồng.
- Một số thông tin network/server chỉ khi cần và được duyệt.

**Không ghi raw path thay cho `http.route`.** Đường dẫn `/reset-password/abc123` có thể chứa token ngay trong path segment; chỉ bỏ query string là chưa đủ. Với framework chưa xác định route, nên omit `http.route` hoặc dùng category an toàn do ứng dụng kiểm soát thay vì tự đoán mọi pattern qua regex.

### Duration

Dùng `System.nanoTime()` để đo elapsed duration trên một process. Chuyển kết quả sang ms và ghi `duration_ms` như number; hoặc dùng field theo backend với đơn vị tương ứng. Time to first byte, server handling time và end-to-end browser latency không thể gộp tùy tiện vào một field.

Ví dụ 503:
- `http.response.status_code=503`: response status.
- `error.type=upstream_timeout`: loại lỗi.
- `severity_text=ERROR`: level do chính sách ứng dụng quyết định.
- `business.outcome=FAILED`: nếu business contract cần, không suy tự động từ status.

## 8. Field cho error/exception

Một event lỗi có thể chứa:
- `event_name` ổn định, ví dụ `inventory.reservation.failed`.
- `error.type` như `upstream_timeout`, `validation_error`, `out_of_stock`.
- `exception.type` nếu cần biết class lỗi (ví dụ `java.net.SocketTimeoutException`).
- `exception.message` theo chính sách; **có thể chứa URL, SQL, input hoặc secret**.
- `exception.stacktrace` có kiểm soát đối với lỗi cần điều tra.
- `correlation_id`/trace ID để liên kết.
- `retry_attempt`, `retryable` nếu contract xử lý có các khái niệm đó.

OpenTelemetry có semantic conventions cho `exception.type`, `exception.message`, `exception.stacktrace`; không đưa tất cả vào mọi log khi không cần.

Ví dụ tích hợp dùng SLF4J (cần `LOG`, `client`, `approvedOrderRef` từ chương trình):

```java
try {
    client.reserve();
} catch (java.net.SocketTimeoutException error) {
    LOG.error("event=inventory.reservation.failed "
              + "error_type=upstream_timeout order_ref={}",
              approvedOrderRef, error);
    throw error;
}
```

Chỉ log `approvedOrderRef` nếu chính sách cho phép; không dump nguyên request/order DTO. Khi dùng overload SLF4J chứa throwable, kiểm tra backend thực sự nhận throwable. Nếu throwable message có secret, cần sửa cách tạo error hoặc phân luồng log có quyền truy cập chặt chẽ.

## 9. Field cho message queue, job và database

**Kafka/message processing** thường cần topic, partition, offset và consumer group để biết record nào được nhận:
- `messaging.system`, `messaging.destination.name` và metadata partition/offset theo semantic conventions/library đang dùng.
- `event_name=message.processing.failed`, `error.type`, `retry_attempt` khi áp dụng.
- `correlation_id`/trace context, với header được validate.
- Không log raw key/value/headers; có thể chứa PII.
- Kafka offset **không là ID toàn cục**, phải xét topic + partition + offset.

**Background job** có thể cần:
- `job.name`/`job.type` có số giá trị hữu hạn.
- `job.run_id` do ứng dụng sinh, `retry_attempt`, `duration_ms`.
- `business.outcome`/`error.type` theo contract.
- Không log toàn bộ job input hoặc danh sách người nhận.

**Database operation** có thể cần:
- `db.system.name`/`db.operation.name` theo instrumentation version.
- `duration_ms` và `error.type`.
- Thông tin connection pool hoặc query category để điều tra.
- Tránh raw SQL bind params, connection string chứa password và result set.

Một số OTel messaging/database conventions còn ở trạng thái Development. Pin version SDK/agent và mappings, không tự cho rằng mọi backend phát cùng một key.

## 10. Privacy và trường bị cấm

| Dữ liệu | Rủi ro | Thay bằng |
| --- | --- | --- |
| Password, OTP, API key, bearer/refresh token | Chiếm quyền truy cập | Trạng thái auth/error code, không giá trị thật |
| Authorization, Cookie, Set-Cookie | Secret phiên | Loại bỏ |
| Request/response body, DTO `toString()` | PII/business data tràn lan | Event DTO allowlist |
| Raw URL/query | Email, token, mã khôi phục | Route template |
| Email, phone, IP, user/tenant ID | Nhận dạng/theo dõi cá nhân | Chỉ ghi nếu có purpose, policy, retention |
| SQL parameters/result set | Dữ liệu cá nhân/nghiệp vụ | Operation name, outcome |
| Raw exception message | Có thể chứa dữ liệu đầu vào | error.type và kênh chẩn đoán được duyệt |
| Toàn bộ MDC/headers | Context không kiểm soát | Allowlist keys |
| Client-provided ID tùy ý | Log injection và high cardinality | ID server-generated/validated |

Hash email không tự trở thành anonymization. Chuỗi hash nhất quán vẫn có thể bị dò hoặc liên kết giữa các bản ghi. Khi cần pseudonymization, cần policy, quản lý khóa/mapping và quyền truy cập phù hợp.

### Chống log injection

Dữ liệu không tin cậy có thể chứa `\r`, `\n`, quote, tab hoặc control characters. Nếu nối vào plain-text log, chúng có thể phá cấu trúc và tạo dòng giả. Đầu tiên **không log** raw input không cần thiết; nếu cần, validate giá trị/độ dài và dùng structured encoder escape theo format. Parameterized logging giúp tách template khỏi argument nhưng không tự bảo đảm CRLF được escape tại output sink.

## 11. Chương trình Java 17+ độc lập: emit event có field chuẩn

Ví dụ chỉ dùng JDK 17, JUL và một serializer JSON nhỏ cho **tập field được kiểm soát**. Không cần Spring Boot/SLF4J/Jackson. Chương trình:
1. Phát event HTTP 503 với timestamp cố định và severity ERROR.
2. Dùng route template, numeric status/duration và correlation ID đã validate.
3. Có trường `authorization` chứa secret **giả** nhưng cố ý không ghi.
4. Xác minh không lộ raw path, query hoặc token.
5. Test input correlation ID có newline bị thay bằng `invalid`.
6. Thu sự kiện bằng JUL memory handler và in output cố định.

**Không dùng serializer tự viết này như một JSON library production.** Khi triển khai nên dùng encoder chuẩn của Logback/Log4j 2, Jackson hoặc OTel SDK để xử lý mọi kiểu, escaping, Unicode và schema.

Tạo tệp **`StandardLogFieldsDemo.java`**:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class StandardLogFieldsDemo {
    record HttpOutcome(Instant occurredAt, String requestId,
            String rawPath, int status, long durationMs,
            String authorization) {}

    static String safeRequestId(String id) {
        return id != null && id.matches("[A-Za-z0-9_-]{1,32}")
                ? id : "invalid";
    }

    static String safeRoute(String path) {
        return path != null && path.matches("/orders/[0-9]{1,8}")
                ? "/orders/{id}" : "/unmapped";
    }

    static String jsonQuote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        out.append(String.format(
                                java.util.Locale.ROOT,
                                "\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    static String json(Map<String, Object> fields) {
        StringBuilder out = new StringBuilder("{");
        for (var entry : fields.entrySet()) {
            if (out.length() > 1) out.append(",");
            out.append(jsonQuote(entry.getKey())).append(":");
            Object value = entry.getValue();
            if (value instanceof String s) {
                out.append(jsonQuote(s));
            } else if (value instanceof Number n) {
                out.append(n);
            } else {
                throw new IllegalArgumentException(
                        "Unsupported field type");
            }
        }
        return out.append("}").toString();
    }

    static String eventJson(HttpOutcome e) {
        if (e.occurredAt() == null || e.status() < 100
                || e.status() > 599 || e.durationMs() < 0) {
            throw new IllegalArgumentException("Invalid outcome");
        }

        boolean failed = e.status() >= 500;
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("timestamp", e.occurredAt().toString());
        fields.put("severity_text", failed ? "ERROR" : "INFO");
        fields.put("event_name", "http.server.request.completed");
        fields.put("service.name", "orders-api");
        fields.put("deployment.environment.name", "test");
        fields.put("http.request.method", "GET");
        fields.put("http.route", safeRoute(e.rawPath()));
        fields.put("http.response.status_code", e.status());
        fields.put("duration_ms", e.durationMs());
        fields.put("correlation_id", safeRequestId(e.requestId()));
        if (failed) {
            fields.put("error.type", "upstream_timeout");
        }
        return json(fields);
    }

    public static void main(String[] args) {
        Logger log = Logger.getAnonymousLogger();
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        List<String> emitted = new ArrayList<>();
        Handler capture = new Handler() {
            @Override public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    emitted.add(record.getMessage());
                }
            }
            @Override public void flush() {}
            @Override public void close() {}
        };
        capture.setLevel(Level.ALL);
        log.addHandler(capture);

        try {
            Instant fixed =
                    Instant.parse("2026-11-10T00:00:00Z");
            HttpOutcome result = new HttpOutcome(
                    fixed, "req_42", "/orders/42",
                    503, 17, "Bearer FAKE_SECRET");
            String line = eventJson(result);
            log.severe(line);

            String suspicious = eventJson(new HttpOutcome(
                    fixed, "bad\nERROR forged",
                    "/orders/42?token=FAKE_SECRET",
                    200, 4, "FAKE_SECRET"));

            if (emitted.size() != 1
                    || !line.contains(
                        "\"http.response.status_code\":503")
                    || !line.contains("\"duration_ms\":17")
                    || !line.contains(
                        "\"http.route\":\"/orders/{id}\"")
                    || !line.contains(
                        "\"error.type\":\"upstream_timeout\"")
                    || line.contains("FAKE_SECRET")
                    || line.contains("/orders/42")
                    || !suspicious.contains(
                        "\"correlation_id\":\"invalid\"")
                    || suspicious.contains("FAKE_SECRET")
                    || suspicious.contains("\n")) {
                throw new AssertionError(
                        "Log schema contract failed");
            }

            System.out.println(
                    "captured_events=" + emitted.size());
            System.out.println(emitted.get(0));
            System.out.println("secret_leaked=false");
            System.out.println("invalid_id_rejected=true");
        } finally {
            log.removeHandler(capture);
            capture.close();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac StandardLogFieldsDemo.java
java StandardLogFieldsDemo
```

**Standard output chính xác:**

```text
captured_events=1
{"timestamp":"2026-11-10T00:00:00Z","severity_text":"ERROR","event_name":"http.server.request.completed","service.name":"orders-api","deployment.environment.name":"test","http.request.method":"GET","http.route":"/orders/{id}","http.response.status_code":503,"duration_ms":17,"correlation_id":"req_42","error.type":"upstream_timeout"}
secret_leaked=false
invalid_id_rejected=true
```

### Giải thích và giới hạn

- `Instant` cố định giúp test không phụ thuộc đồng hồ. Production lấy thời gian thực và có timezone/precision rõ.
- `LinkedHashMap` bảo toàn thứ tự key trong output minh họa; **thứ tự key không phải hợp đồng JSON**.
- Số status/duration được serialize thành numbers. `error.type` chỉ có ở event thất bại trong demo.
- `safeRoute` chỉ cho một route ví dụ, không phải router tổng quát. Với Spring MVC, lấy template từ framework.
- `safeRequestId` loại ID chứa CR/LF. Hệ thống thật nên cấp ID server-generated hoặc kiểm tra nguồn header.
- `authorization` không được đọc trong `eventJson`; secret giả không xuất hiện.
- `Handler` cho biết có event tại logger cục bộ, không chứng minh collector đã lưu.
- Hàm `jsonQuote` minh họa escaping; không phải thư viện JSON đầy đủ cho mọi dữ liệu sản xuất.

## 12. SLF4J 2.x, Logback và structured key/value

Một lời gọi parameterized truyền thống:

```java
// Tích hợp: LOG là org.slf4j.Logger đã khởi tạo.
LOG.info("event={} status={} duration_ms={}",
         "http.server.request.completed",
         statusCode, durationMs);
```

Nó tạo message theo backend; **không đảm bảo có ba JSON field riêng** ở output. SLF4J 2.x có fluent API với `addKeyValue`:

```java
LOG.atInfo()
   .addKeyValue("event_name", "http.server.request.completed")
   .addKeyValue("http.route", routeTemplate)
   .addKeyValue("http.response.status_code", statusCode)
   .addKeyValue("duration_ms", durationMs)
   .log("HTTP request completed");
```

Đây là **đoạn tích hợp** cần slf4j-api 2.x, provider và encoder phù hợp. Bắt buộc kết thúc bằng `log(...)`; nếu quên, không có event. Backend/layout phải được cấu hình xuất key-value pairs (không chỉ message) thì JSON collector mới thấy fields. Không truyền raw DTO, headers hay secret qua `addKeyValue`.

Với Logback:
- Có thể thêm MDC, throwable, logger name, thread, resource metadata qua encoder.
- Không in nguyên mọi MDC bằng pattern nếu các thư viện có thể đưa PII vào.
- Khi async logging, snapshot context ở event, không đọc MDC từ exporter worker sau đó.
- Với JUnit/Logback `ListAppender` kiểm tra `getKeyValuePairs()`/formatted output theo phiên bản.
- Nếu backend là Log4j 2, dùng layout/test utilities tương ứng; không cast sang Logback.

JUL `LogRecord` cũng mang level/logger/message/parameters/throwable nhưng `getMessage()` có thể là template chưa format. Một bridge JUL→SLF4J/OTel phải map trường nhất quán và tránh vòng lặp bridge.

## 13. Mapping OpenTelemetry và ECS một cách an toàn

Một hệ thống có thể thu qua OpenTelemetry nhưng lưu trong Elasticsearch/ECS hoặc Loki. Không đồng nhất tên khác nhau khi chúng có semantics riêng.

| JSON app | OpenTelemetry | ECS | Lưu ý |
| --- | --- | --- | --- |
| `timestamp` | `Timestamp` | `@timestamp` | Event time |
| `severity_text` | `SeverityText` | `log.level` | Mapping severity |
| `event_name` | `EventName` | `event.action`/`event.code` theo taxonomy | Không mặc định 1:1 |
| `service.name` | Resource `service.name` | `service.name` | Config service |
| `deployment.environment.name` | Resource attribute cùng tên | `service.environment` theo mapping ECS | Kiểm tra ECS version |
| `http.request.method` | Attribute HTTP | `http.request.method` | Enum |
| `http.route` | Attribute template | Không đồng nghĩa `url.path` | Đích có thể cần custom field |
| `http.response.status_code` | Attribute HTTP | `http.response.status_code` | Number |
| `duration_ms` | Custom attribute (ms) | `event.duration` (ns) nếu map | **Phải nhân 1.000.000** |
| `correlation_id` | Custom attribute | Custom field theo chính sách | Không phải TraceId |
| `trace_id`/`span_id` | `TraceId`/`SpanId` | `trace.id`/`span.id` | Format ID khác nhau |
| `error.type` | Attribute có ngữ nghĩa lỗi | `error.type` | Giá trị ổn định |

ECS còn có `event.outcome` với giá trị `success`/`failure`/`unknown` khi outcome có ý nghĩa, `event.created` và `event.ingested` là các mốc pipeline khác `@timestamp`, `ecs.version` lưu version mapping.

**Không dùng** `event.outcome=ERROR` vì ERROR là level, không phải kết quả. `event.duration` của ECS tính nanoseconds, khác field tự tạo `duration_ms`. Khi chuyển đổi OTel/ECS, dùng config/processor có test, không chỉ đổi tên key trên dashboard.

Các semantic conventions có thể Stable hoặc Development theo version; đặc biệt messaging/database fields cần kiểm tra version SDK/agent đang dùng.

## 14. Chọn indexed labels và tránh cardinality cao

Log fields và metric/index labels là hai quyết định khác nhau:

| Field | Hữu ích trong log? | Nên là Loki/metric label? |
| --- | --- | --- |
| `service.name` | Có | Thường có, tập giá trị hữu hạn |
| `deployment.environment.name` | Có | Thường có |
| `service.version` | Có | Cân nhắc khi version biến đổi nhiều |
| `http.route` template | Có | Có thể sau khi đo số route |
| `error.type` enum | Có | Có thể |
| `correlation_id` | Có theo policy | **Không** làm label mỗi request |
| `trace_id`/`span_id` | Có khi có tracing | **Không** làm high-cardinality label |
| `duration_ms` | Có | Không dùng giá trị liên tục làm label |
| `user_id`/raw URL/token | Tránh hoặc cấm | Không |

Một label riêng cho mỗi request có thể tạo hàng triệu stream/time series, tăng memory/query cost và làm mất ý nghĩa grouping. Với Loki, giữ ID trong parsed fields/structured metadata theo khả năng backend, chọn stream labels ổn định. Với Prometheus metrics, không biến ID ngẫu nhiên thành label.

## 15. Schema versioning và migration

Một chiến lược field cần có:
- **Owner** phụ trách dictionary các field và event types.
- **Contract** ghi tên, type, unit, source, sensitivity, required/optional/conditional.
- **Schema version** cho thay đổi có thể phá query.
- **Migration** cho field rename/type change; hỗ trợ dual-read ở dashboard trong giai đoạn chuyển.
- **Compatibility tests** ở logger, encoder, collector và storage.
- **Deprecation policy** để bỏ aliases cũ có kế hoạch.
- **Retention/RBAC** theo loại event và dữ liệu nhạy cảm.

Ví dụ hợp đồng minh họa dạng YAML **do ứng dụng tự định nghĩa**, không phải config OTel/ECS:

```yaml
name: http.server.request.completed
schema_version: 1
owner: orders-platform
required:
  timestamp: "UTC ISO 8601"
  severity_text: "INFO|WARN|ERROR"
  service.name: "string"
  deployment.environment.name: "string"
  event_name: "stable enum"
  http.request.method: "enum"
  duration_ms: "integer >= 0"
conditional:
  http.response.status_code: "integer when response exists"
  error.type: "low-cardinality code when failed"
optional:
  http.route: "trusted route template"
  correlation_id: "validated or server-generated ID"
forbidden:
  - authorization
  - cookie
  - password
  - raw_request_body
  - raw_url_query
```

Đừng ép một kết nối bị hủy trước response thành HTTP 200 chỉ vì schema cũ yêu cầu status. Điều chỉnh conditional field và phân loại failure với contract rõ.

## 16. Kiểm thử field chuẩn

### 16.1. Unit test builder

Các trường hợp nên kiểm tra:
1. Event 503 có status number, `error.type` enum và duration không âm.
2. Event 200 không có error.type nếu contract quy định.
3. Timestamp null hoặc status 99/600 bị từ chối.
4. Duration âm bị từ chối.
5. ID chứa CR/LF, quote, whitespace quá dài không đi thẳng vào JSON.
6. Route chứa raw ID/query không xuất hiện; unknown route được xử lý an toàn.
7. Token/cookie/Authorization và payload giả không bị serialize.
8. Strings được encoder chuẩn escape; JSON parse thành công.
9. Service/env không lấy từ request header chưa xác thực.
10. Optional/missing/null đúng contract; zero khác unknown.

### 16.2. Integration test appender/collector

Sau khi phát sự kiện:
- Kiểm tra Logback/Log4j 2/JUL event có level, logger, K/V và throwable đúng.
- Kiểm tra JSON output qua encoder thật, number vẫn là number; không chỉ so substring.
- Đối chiếu field nguồn với Resource/Attributes/Severity/Timestamp ở Collector.
- Kiểm tra ECS mapping duration đúng nanoseconds và trace IDs đúng format.
- Kiểm tra MDC cleanup, async propagation và schema khi tăng replicas.
- Dùng canary giả ở staging, kiểm tra các sink, export, archive và RBAC.
- Test dashboard/alert cũ khi schema version mới rollout song song.
- Có timeout hữu hạn khi chờ async, không dùng `Thread.sleep` cố định để suy event đã được lưu.
- Không xem test appender PASS là bảo đảm collector/storage đã nhận log.

### 16.3. Checklist cho code review

| Câu hỏi | Yêu cầu |
| --- | --- |
| Field có trả lời một truy vấn/runbook? | Có purpose/consumer |
| Tên có chuẩn và mapping? | Dictionary/version rõ |
| Kiểu có đúng? | JSON number/bool/timestamp |
| Unit có ghi trong key/contract? | ms/ns/bytes rõ |
| Nguồn đáng tin? | Config/server-generated/validated |
| Có thuộc PII/secret? | Minimization và policy |
| Có thể high-cardinality? | Không làm indexed label tùy ý |
| Có khi nào không áp dụng? | Required/conditional/optional |
| Có test schema ở backend? | Có integration test |
| Đổi field có phá dashboard? | Migration/deprecation |
| Có xuất hiện ở nhiều sink? | Kiểm tra redaction/ACL/retention |

## 17. Lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Mỗi module đặt tên request ID khác | Không liên kết được logs | Dictionary + migration |
| Log nguyên DTO/toString | Rò PII khi thêm field | Event DTO allowlist |
| Status là string, duration có chữ ms | Aggregation sai | Numeric type/unit rõ |
| Đặt `duration_ms` thành `event.duration` | ECS unit là ns | Convert chính xác |
| Đưa raw URL vào `http.route` | Sai semconv, PII/cardinality | Route template |
| Ghi `trace_id=req_42` | Không phải W3C trace ID | Correlation riêng |
| Dùng `event.outcome=INFO` | Lẫn outcome với log level | Enum outcome chuẩn |
| Ghi toàn bộ exception.message | Có thể chứa secret | Review/sink policy |
| Copy mọi MDC/header | PII và log injection | Allowlist, validate |
| Tạo label từ mỗi request ID | High cardinality | ID là parsed field |
| Thay tên field không version | Dashboard rơi mất dữ liệu | Migration/dual-read |
| Cho rằng JSON flat = OTLP | Sai mô hình OTel | Map top-level/Resource/Attributes |
| Quên `.log()` của SLF4J fluent | Không phát event | Kết thúc builder |
| Chỉ test source code | Collector có thể rename/stringify | E2E contract tests |

## 18. Bài tập

1. Chạy `StandardLogFieldsDemo` và giải thích vì sao `http.response.status_code` là number, `timestamp` là string ISO 8601.
2. Đổi status 503 thành 200, xem `error.type` bị omit; thảo luận khi nào severity không nên suy từ status.
3. Truyền request ID chứa newline/quote hoặc quá dài; kiểm tra field được thay bằng `invalid`.
4. Thêm route an toàn khác và so sánh với việc dùng raw URL có `?token=FAKE_SECRET`.
5. Dùng JUnit 5 viết negative tests cho null time, duration âm, invalid status.
6. Map JSON sang OTel LogRecord: Timestamp, SeverityText, EventName, Resource, Attributes.
7. Map JSON sang ECS và đổi 17 ms thành 17.000.000 ns.
8. Gắn trace ID W3C hợp lệ và tạo link tới trace backend, phân biệt với correlation ID tự sinh.
9. Bổ sung event Kafka với topic/partition/offset; giải thích vì sao offset đơn lẻ không đủ.
10. Dùng SLF4J 2.x `addKeyValue` với JSON encoder và kiểm tra field đã được emit ở sink.
11. Lập schema cho `order.processing.failed` với error.type và business outcome, không lộ order DTO.
12. Thử migration giữa `requestId` và `correlation_id`; thiết kế dual-read của dashboard.
13. Tạo test canary giả cho Authorization, Cookie, raw query, CRLF, MDC, exception message.
14. Chọn indexed labels cho Loki/Prometheus và giải thích vì sao không dùng trace ID làm label.
15. Rà soát ba events: service started, HTTP error, Kafka retry; phân biệt required/conditional/optional.

## 19. Ghi nhớ

- **Field chuẩn** cần tên, type, unit, ý nghĩa, nguồn tin cậy, điều kiện xuất hiện và mức bảo vệ.
- Tách core envelope, Resource, correlation và event-specific attributes; không ép mọi event có cùng tất cả fields.
- OTel top-level Timestamp/Severity/EventName/TraceId khác Resource và Attributes; JSON tự tạo phải có mapping nếu xuất OTLP.
- ECS `event.duration` tính bằng nanoseconds; đổi từ duration_ms phải nhân 1.000.000.
- `http.route` là route template; không sử dụng raw URL, correlation ID không phải TraceId.
- Tránh token/PII/raw DTO/headers, log injection và high-cardinality indexed labels.
- Giữ field/event names ổn định, schema version rõ, migration và test từ logger đến backend.

### Tài liệu tham khảo

- OpenTelemetry — Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- OpenTelemetry — Semantic conventions for events: https://opentelemetry.io/docs/specs/semconv/general/events/
- OpenTelemetry — HTTP semantic conventions: https://opentelemetry.io/docs/specs/semconv/http/http-spans/
- OpenTelemetry — Exception attributes: https://opentelemetry.io/docs/specs/semconv/registry/attributes/exception/
- OpenTelemetry — Deployment attributes: https://opentelemetry.io/docs/specs/semconv/resource/deployment-environment/
- Elastic — ECS Base fields: https://www.elastic.co/docs/reference/ecs/ecs-base
- Elastic — ECS Event fields: https://www.elastic.co/docs/reference/ecs/ecs-event
- Elastic — ECS Log fields: https://www.elastic.co/docs/reference/ecs/ecs-log
- Elastic — ECS Tracing fields: https://www.elastic.co/docs/reference/ecs/ecs-tracing
- SLF4J — User Manual: https://slf4j.org/manual.html
- Oracle Java 17 — Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

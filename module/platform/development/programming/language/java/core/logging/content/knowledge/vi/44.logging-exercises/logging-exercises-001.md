# Dự án thực hành: Thiết kế logging baseline cho một Java service

## 1. Bài toán dự án

Một ứng dụng Java có thể chạy đúng chức năng nhưng vẫn **khó vận hành** nếu log chỉ gồm những câu rời rạc như `Start process`, `Error happened` hoặc `User request: ...`. Khi xảy ra lỗi, nhóm phát triển không trả lời được request nào thất bại, service nào tạo log, mức ảnh hưởng, mất bao lâu và có thể đối chiếu với trace/metrics hay không. Ngược lại, ghi nguyên HTTP body và token để tiện debug sẽ làm tăng rủi ro rò rỉ dữ liệu.

Trong dự án này, bạn xây **logging baseline** — một **hợp đồng ghi log tối thiểu, có cấu trúc, an toàn và vận hành được** — cho một Java service giả định tên **`checkout-api`**. “Baseline” không có nghĩa ghi mọi thứ hay tạo một kiến trúc observability hoàn chỉnh. Đây là bộ nguyên tắc, schema, cấu hình và kiểm thử đủ tốt để những service tương tự làm theo mà vẫn có chỗ mở rộng.

**Đầu ra cần có:**

1. Một **schema log** với field names, JSON types, ngữ nghĩa, required/optional và quy tắc bảo vệ thông tin.
2. Một **event catalog**: sự kiện nào nên được ghi ở INFO/WARN/ERROR, nguồn tạo event, outcome thật.
3. Cấu hình **console JSONL** cho môi trường container hoặc rolling file cho VM khi cần; phân biệt từng nguồn log.
4. **Correlation context** có request/trace ID đáng tin, không rò khi thread được tái sử dụng.
5. Bộ **kiểm thử schema, dữ liệu nhạy cảm, async và sự cố logging**.
6. Một **runbook vận hành tối thiểu**: cách tìm event, điều tra khi log mất/chậm và cách khôi phục cấu hình.
7. **Bằng chứng nghiệm thu**: output thực, test PASS/FAIL, effective config, chính sách retention và người chịu trách nhiệm.

Dự án có **hai phần thực hành**. Phần A là chương trình **JDK 17 thuần** chạy độc lập để học contract và tự kiểm kết quả. Phần B là **hướng dẫn tích hợp Spring Boot/SLF4J** với cấu hình ở phiên bản được hỗ trợ; các đoạn Spring chỉ dùng khi dự án có dependency/framework tương ứng.

## 2. Kịch bản nghiệp vụ và phạm vi

Giả sử `checkout-api` nhận một yêu cầu `POST /orders/{id}/checkout`, kiểm tra tồn kho và xác nhận một thao tác checkout. Kết quả có thể là:

- **200**: checkout hoàn tất, event `checkout.completed`.
- **409**: yêu cầu bị từ chối theo quy tắc nghiệp vụ như hết hàng, event `checkout.rejected`.
- **502/504**: lỗi dependency/gateway, event `checkout.dependency_failed` với safe reason code.
- **401/403**: bị xác thực hoặc phân quyền từ chối, security handler phát event an toàn riêng.
- **202**: nếu chỉ tạo job async, event phải thể hiện `checkout.accepted`, **không** ghi “completed” trước khi worker thực sự hoàn tất.

Ngữ cảnh này chỉ để minh họa logging; **không triển khai thanh toán thật** và không ghi card data. Một request có thể đi qua API gateway, service, worker và collector; cần tránh đếm trùng hoặc coi từng event là một giao dịch đã commit.

### Phạm vi thực hiện

| Trong phạm vi | Ngoài phạm vi |
| --- | --- |
| Application events và metadata HTTP an toàn | Xây hệ thống SIEM/trace backend từ đầu |
| JSONL, levels, error codes, correlation IDs | Tự viết JSON encoder production mới |
| Redaction/field allowlist, privacy tests | Log body/password/token để kiểm thử |
| stdout/file rolling, collector boundary | Khẳng định exactly-once logging end-to-end |
| Kiểm thử backend/encoder/collector có chọn lọc | Thay audit store bằng INFO logger |
| SLO, retention và runbook tối thiểu | Tự động xóa log production |

**Nguyên tắc:** không phát minh ra các API framework; mẫu JDK chạy độc lập được phân biệt rõ với Spring Boot snippets và cấu hình collector phải được người vận hành của hệ thống thật kiểm chứng.

## 3. Kiến trúc baseline đề xuất

```text
HTTP caller / scheduled job
          │
          ▼
Authentication + route matching
          │
          ├─ trusted actor/request/trace context
          ▼
Application service / business outcome
          │
          ├─ Structured event builder (allowlisted fields)
          │
          ▼
SLF4J facade / JUL / chosen backend
          │
          ├─ level + filters
          ├─ JSON encoder (1 event / 1 line)
          └─ bounded appender / stdout
                       │
                       ▼
             node agent / collector
                       │
              buffering + retry
                       │
                       ▼
            central log backend/index
                       │
              retention + RBAC
                       │
                search / alert

Security/audit event ──► independent audit policy/sink when required
Metrics & tracing ─────► own pipelines; correlate via trusted IDs
```

### Ranh giới trách nhiệm

- **Business/application code** quyết định event name, target, outcome, reason code và thời điểm nghiệp vụ.
- **Security layer** xác định actor đã xác thực; không lấy `userId` từ raw request header/body.
- **Logging facade/backend** kiểm level, encode và chuyển event tới stdout/file; **chưa có nghĩa backend tập trung đã nhận**.
- **Collector** thu dữ liệu, buffer, parse/route và chuyển vào backend; cần metric lag, retries và dropped records.
- **Search/storage** giữ index, quyền truy vấn, retention, archive và khả năng điều tra.
- **Tracing** tạo/propagate trace/span context nếu có instrumentation đúng. **Đừng coi trace ID là identity của con người.**
- **Audit pipeline** có semantics bảo toàn riêng nếu là bằng chứng pháp lý/nghiệp vụ; không dùng một AsyncAppender có thể discard làm điểm lưu duy nhất cho audit bắt buộc.

Tất cả các chặng phải có owner. Nếu source ghi đúng nhưng collector sai, lỗi không thể sửa chỉ bằng `logging.level.root=DEBUG`.

## 4. Logging baseline so với metrics, traces và audit

| Tín hiệu | Trả lời tốt nhất | Ví dụ |
| --- | --- | --- |
| **Application log** | Có sự kiện cụ thể gì đã xảy ra? | `checkout.rejected`, `error.code=OUT_OF_STOCK` |
| **HTTP access log** | Request tới service, status, latency? | `POST /orders/{id}/checkout 409 4ms` |
| **Metric** | Tỷ lệ lỗi/latency thay đổi bao nhiêu? | `checkout_rejected_total`, histogram latency |
| **Trace** | Request đi qua service/span nào, mất thời gian ở đâu? | `trace_id`, `span_id`, dependency call |
| **Security event** | Xác thực/phân quyền nào bị từ chối? | `authorization_denied` |
| **Audit event** | Actor nào đã thay đổi tài nguyên và outcome nghiệp vụ? | `actor.id`, `target.id`, `COMMITTED` |

Dòng access và dòng business event **không bắt buộc có cùng status/outcome semantics**: HTTP 202 có nghĩa yêu cầu được nhận, worker có thể thất bại về sau. Không suy “thành công nghiệp vụ” chỉ dựa HTTP 200.

Logging không thay thế metrics: đếm INFO logs có thể bị lệch khi sampling, async discard hoặc log không được index. Logging cũng không thay thế tracing: chỉ có trace ID không cho biết mọi span hay quan hệ parent-child.

## 5. Chốt schema JSONL trước khi code

Một **sự kiện ứng dụng mẫu** có thể được biểu diễn:

```json
{
  "@timestamp": "2026-11-10T03:15:00Z",
  "schema.version": 1,
  "level": "INFO",
  "service.name": "checkout-api",
  "event.name": "checkout.completed",
  "http.route": "/orders/{id}/checkout",
  "http.status_code": 200,
  "duration_ms": 12,
  "outcome": "SUCCESS",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "req_101"
}
```

**Đây là schema của dự án, không phải cam kết output tự động từ mọi Logback encoder, OpenTelemetry hay ECS.** Một thư viện có thể dùng key `log.level` thay `level` hoặc object nested `http.status_code`; cần cấu hình mapping và test output cuối cho phù hợp.

### Bảng hợp đồng trường dữ liệu

| Field | Kiểu JSON | Required | Nguồn và ràng buộc |
| --- | --- | --- | --- |
| `@timestamp` | string | Có | UTC ISO-8601, từ clock tại nơi event được tạo |
| `schema.version` | integer | Có | Phiên bản schema contract; không là string |
| `level` | string | Có | Severity đã normalize của backend |
| `service.name` | string | Có | Từ trusted deployment config |
| `event.name` | string | Có | Mã event từ enum/catalog do server kiểm soát |
| `http.route` | string | Với HTTP events | Matched route template/class, không raw URI |
| `http.status_code` | integer | Với HTTP completed | Mã HTTP 100–599; không quote như `"200"` |
| `duration_ms` | integer | Với completed event | Thời lượng không âm, đo bằng monotonic clock |
| `outcome` | string | Có | `SUCCESS`, `DENIED`, `FAILED`, `ACCEPTED`... theo catalog |
| `trace_id` | string | Nếu tracing context có | 32 hex lowercase khi dùng W3C Trace Context; không giả ID |
| `span_id` | string | Tùy chọn | 16 hex lowercase khi có span thực |
| `request_id` | string | Nếu request context có | Format/độ dài theo policy, validate trước log |
| `error.code` | string | Với lỗi nghiệp vụ có mã | Safe enum; không dùng raw exception message |
| `actor.type`/`actor.id` | string | Tùy security/audit contract | Verified principal; có privacy/retention |
| `tenant.id` | string | Nếu multi-tenant | Verified tenant, không từ raw header |

### Quy tắc field name và shape

- **Đừng tự thay tên theo cảm hứng:** `duration_ms` khác `duration` và `duration_ns`. Đổi đơn vị mà giữ key là lỗi nghiêm trọng.
- **Kiểu dữ liệu phải đúng:** `http.status_code=200` là JSON number; `success=true` là boolean, không phải string.
- **Không suy luận key từ raw input:** tên event và field phải do code/config kiểm soát.
- **Chỉ thêm field có mục đích:** email, IP, user ID có thể là PII; không phải field “miễn phí”.
- **Error code là enum** ổn định (ví dụ `OUT_OF_STOCK`), khác thông điệp exception có thể chứa bí mật.
- **Null và missing:** xác định rõ. Startup log có thể không có trace ID; không ghi `trace_id="null"` như một ID thật.
- **Timestamp:** UTC event time khác ingestion time; backend có thể thêm trường riêng.
- **Schema version:** thay đổi field name/type cần version/migration và kiểm tra dashboard/alerts.

Các trường có dấu chấm trong ví dụ là **flat JSON keys**. Nếu chọn nested objects, hãy dùng schema nested nhất quán và test đúng shape. Không trộn lẫn hai kiểu tùy ý.

## 6. Chọn JSON Lines thay vì text tự do

JSONL yêu cầu mỗi event tạo **một JSON object trên một dòng vật lý**, dễ cho collector parse và kiểm kiểu. Dấu xuống dòng trong message phải được encode thành ký tự escape `\n` trong JSON string, không làm một event thành hai dòng.

Ví dụ:

```json
{"event.name":"checkout.rejected","message":"request\nrejected","http.status_code":409}
```

Khi đọc JSON bằng parser, `message` chứa một newline logic, nhưng raw JSONL vẫn là một dòng.

**Không dùng việc nhìn một chuỗi bắt đầu bằng `{` để kết luận là JSON hợp lệ.** Phải parse bằng thư viện có khả năng kiểm type, kiểm UTF-8, escaping, object shape, length và duplicate-key policy nếu cần. Đặc biệt với stack traces, không phát raw multi-line exception ngoài JSON nếu pipeline contract yêu cầu JSONL.

Trong production, dùng encoder JSON của framework/backend hoặc thư viện như Jackson/logstash encoder đã kiểm thử. Mã encoder giản lược ở phần Java 17 phía dưới chỉ phục vụ học và cố ý không hỗ trợ mọi loại giá trị.

## 7. Event catalog: ghi gì, ở level nào và khi nào?

| Sự kiện | Level gợi ý | Trigger | Field quan trọng |
| --- | --- | --- | --- |
| `checkout.started` | DEBUG hoặc không log từng request | Bắt đầu workflow | operation/request ID, không payload |
| `checkout.completed` | INFO | Business transaction đã hoàn tất | outcome, duration, target type, status |
| `checkout.rejected` | INFO/WARN theo policy | Quy tắc nghiệp vụ từ chối | reason code, status, request ID |
| `checkout.dependency_failed` | ERROR | Dependency lỗi, cần chú ý vận hành | safe error code, dependency class, trace |
| `checkout.retry_scheduled` | DEBUG/INFO | Có retry hợp lệ | attempt, backoff class, operation ID |
| `authorization_denied` | Security event riêng | Tầng quyền từ chối | verified actor/anonymous, action, outcome |
| `health.checked` | Thường metric hoặc access tối giản | Health probe | Không spam app log từng lần nếu không cần |
| `application.started` | INFO | Startup thành công | version/environment safe |
| `configuration.changed` | Audit/admin event | Cấu hình đổi | actor verified, change ID, không secret |

**Không có quy tắc INFO/WARN/ERROR chung cho mọi tổ chức.** Ví dụ HTTP 409 từ quy tắc nghiệp vụ thông thường có thể là INFO, không phải một lỗi hạ tầng cần đánh thức on-call. ERROR nên dành cho lỗi có ý nghĩa ứng cứu; đừng biến mỗi 4xx thành ERROR nếu sẽ tạo alert fatigue.

### Một số lỗi cần tránh

- INFO ở đầu controller “checkout success” trước khi transaction commit.
- Ghi cùng lỗi dependency tại HTTP client, service, controller và exception handler như bốn ERROR trùng không có phân biệt.
- Dùng `logger.error("Failed", e)` với exception chứa raw URI/token.
- Log thông điệp `user={...}` lấy username body làm actor đã xác thực.
- Ghi raw request/response object hoặc card information chỉ để tìm lỗi.
- Mỗi vòng lặp retry đều in stack trace lớn trong khi volume không có giới hạn.

## 8. Thiết kế privacy và security ngay từ baseline

**Không bao giờ mặc định ghi** password, OTP, access/refresh token, Authorization header, Cookie/Set-Cookie, session secret, API key, reset code, PAN/CVV, private key, raw request/response body, hoặc URL query chứa secret.

### Allowlist thay cho blacklist

Giả sử request chứa:

```text
POST /orders/991/checkout?promo=...&token=FAKE_SECRET_CANARY_494
Authorization: Bearer FAKE_SECRET_CANARY_494
Body: {"card":"FAKE_SECRET_CANARY_494"}
```

Log an toàn có thể chỉ chứa:

```json
{"event.name":"checkout.completed","http.route":"/orders/{id}/checkout","http.status_code":200,"duration_ms":12}
```

Không đưa raw `requestURI`, query, headers hay body vào event, thay bằng **matched route template đáng tin** của router. Trường `trace_id` hoặc `request_id` nên được validate độ dài/format; không được sử dụng chúng làm bằng chứng người đã đăng nhập.

Các nguy cơ phải kiểm thử:

- **Log forging (CWE-117):** chuỗi chứa CRLF/control characters làm tạo record giả nếu text formatter không neutralize.
- **Nested JSON:** field `metadata.password` mới có thể lọt qua regex cũ.
- **Exception string:** một HTTP client có thể đưa response body hoặc URL có token vào message.
- **PII trong path:** reset token, email, user identifier có thể nằm trong đường dẫn dù query đã bỏ.
- **MDC/baggage:** dữ liệu cá nhân được gắn vào context rồi phát tán sang mọi event.
- **Backend copies:** masking ở dashboard không xóa dữ liệu đã ghi vào file/index/backup.

**Baseline tốt là không thu bí mật tại nguồn.** Masking của collector là lớp phòng vệ bổ sung, không phải biện pháp duy nhất.

## 9. Correlation: gắn ID đúng nhưng không rò giữa request

Log dễ tìm hơn khi mọi event cùng request có `request_id` và, nếu hệ thống có distributed tracing, `trace_id`/`span_id` nhất quán.

### Không nhầm ba loại ID

| ID | Ý nghĩa | Không được suy diễn |
| --- | --- | --- |
| `request_id` | Khóa tương quan tại HTTP/app boundary | Chưa chứng minh user hoặc transaction commit |
| `trace_id` | Khóa cho một trace qua nhiều span/service | Không đồng nghĩa auth identity |
| `operation_id`/`job_id` | Khóa cho workflow có thể kéo dài qua queue/retry | Không mặc định đúng một log cho mỗi nghiệp vụ |

### Trust boundary

`traceparent` và `X-Request-ID` có thể do client gửi. Nếu nhận ID từ edge, validate theo spec/format/length và chính sách trusted proxy; không in nguyên chuỗi tùy ý hoặc tin nó là actor. Trong multi-tenant, tenant identity cần đến từ context đã được xác thực.

### ThreadLocal/MDC và async

- Với request đồng bộ, có thể set MDC trong filter rồi restore trong `finally`.
- Thread pool tái sử dụng thread; thiếu restore làm request B thừa context từ A.
- `@Async`, `CompletableFuture`, message consumer và scheduled task không tự nhận đúng context chỉ vì producer có MDC. Cần capture/propagate metadata được phép và xóa khi hoàn tất.
- Tracing library/Micrometer có thể làm propagation theo cấu hình nhưng **không giả định được bật sẵn** nếu chưa thêm dependencies/instrumentation.
- Khi không có active trace, bỏ field hoặc thể hiện trạng thái rõ; không bịa một trace ID “đẹp”.

## 10. Bài thực hành A — Java 17 không cần dependency ngoài

Ta xây chương trình **`LoggingBaselineDemo.java`** có các tính chất:

1. Ghi JSONL qua một **JUL Logger và Handler** thật, chứ không chỉ nối string rồi giả gọi là logger.
2. Mỗi event có field typed: schema version, status, duration; code dùng allowlist.
3. Hai request có trace/request ID khác nhau, context được restore sau xử lý.
4. Input có **canary giả** nhưng token/card không được xuất ra.
5. Test trong `main` kiểm event count, JSON field literal, event isolation và canary; sai thì ném `AssertionError`.
6. Timestamp cố định để stdout tái lập. Ứng dụng production phải lấy từ `Clock` thực.

**Lưu ý:** JSON encoder trong demo **chỉ hỗ trợ dữ liệu String/Integer/Long/Boolean từ schema cố định**. Không đưa vào production để thay Jackson hoặc encoder chuyên dụng. Handler in nội dung đã encode mà demo kiểm soát; chương trình không implement HTTP server, auth, queue, file rotation hoặc collector.

Tạo tệp **`LoggingBaselineDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingBaselineDemo {
    private static final Pattern TRACE =
            Pattern.compile("[0-9a-f]{32}");
    private static final Pattern REQUEST =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private static final ThreadLocal<RequestContext> CONTEXT =
            new ThreadLocal<>();

    record RequestContext(String traceId, String requestId) {
        RequestContext {
            if (traceId == null || !TRACE.matcher(traceId).matches()
                    || requestId == null
                    || !REQUEST.matcher(requestId).matches()) {
                throw new IllegalArgumentException("Invalid context IDs");
            }
        }
    }

    record SensitiveInput(String authorization, String card) {}

    private static void within(
            RequestContext context, Runnable work) {
        RequestContext previous = CONTEXT.get();
        CONTEXT.set(context);
        try {
            work.run();
        } finally {
            if (previous == null) {
                CONTEXT.remove();
            } else {
                CONTEXT.set(previous);
            }
        }
    }

    // Encoder đơn giản chỉ cho dữ liệu do ứng dụng kiểm soát.
    private static String quote(String text) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            switch (ch) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        String hex = Integer.toHexString(ch);
                        out.append("\\u")
                                .append("0".repeat(4 - hex.length()))
                                .append(hex);
                    } else {
                        out.append(ch);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static String json(Map<String, Object> fields) {
        StringBuilder out = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> item : fields.entrySet()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append(quote(item.getKey())).append(':');
            Object value = item.getValue();
            if (value instanceof String s) {
                out.append(quote(s));
            } else if (value instanceof Integer
                    || value instanceof Long
                    || value instanceof Boolean) {
                out.append(value);
            } else {
                throw new IllegalArgumentException("Unsupported field type");
            }
        }
        return out.append('}').toString();
    }

    private static void event(
            Logger logger,
            Level level,
            String eventName,
            int status,
            long durationMs,
            String outcome,
            String errorCode,
            SensitiveInput ignoredSensitiveInput) {

        if (!Set.of("checkout.completed", "checkout.rejected")
                .contains(eventName)) {
            throw new IllegalArgumentException("Unknown event");
        }
        if (!Set.of("SUCCESS", "DENIED").contains(outcome)
                || status < 100 || status > 599
                || durationMs < 0) {
            throw new IllegalArgumentException("Invalid event fields");
        }
        RequestContext ctx = CONTEXT.get();
        if (ctx == null) {
            throw new IllegalStateException("Missing request context");
        }

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("@timestamp", "2026-11-10T03:15:00Z");
        fields.put("schema.version", 1);
        fields.put("level", level.getName());
        fields.put("service.name", "checkout-api");
        fields.put("event.name", eventName);
        fields.put("http.route", "/orders/{id}/checkout");
        fields.put("http.status_code", status);
        fields.put("duration_ms", durationMs);
        fields.put("outcome", outcome);
        fields.put("trace_id", ctx.traceId());
        fields.put("request_id", ctx.requestId());

        if (errorCode != null) {
            if (!Set.of("OUT_OF_STOCK").contains(errorCode)) {
                throw new IllegalArgumentException("Invalid error code");
            }
            fields.put("error.code", errorCode);
        }

        // Chỉ log fields allowlisted, không đọc token/card input.
        logger.log(level, json(fields));
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.logging.baseline");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        List<String> lines = new ArrayList<>();
        Handler capture = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    lines.add(record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        SensitiveInput secret = new SensitiveInput(
                "Bearer FAKE_SECRET_CANARY_494",
                "FAKE_SECRET_CANARY_494");

        try {
            within(new RequestContext(
                    "4bf92f3577b34da6a3ce929d0e0e4736",
                    "req_101"),
                    () -> event(logger, Level.INFO,
                            "checkout.completed", 200, 12L,
                            "SUCCESS", null, secret));

            require(CONTEXT.get() == null,
                    "Context leaked after first request");

            within(new RequestContext(
                    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "req_102"),
                    () -> event(logger, Level.WARNING,
                            "checkout.rejected", 409, 4L,
                            "DENIED", "OUT_OF_STOCK", secret));

            require(CONTEXT.get() == null,
                    "Context leaked after second request");
            require(lines.size() == 2, "Expected two events");
            require(lines.get(0).contains(
                    "\"http.status_code\":200"),
                    "Numeric HTTP status missing");
            require(lines.get(1).contains(
                    "\"error.code\":\"OUT_OF_STOCK\""),
                    "Safe error code missing");
            require(lines.get(0).contains(
                    "\"request_id\":\"req_101\"")
                    && !lines.get(0).contains("req_102"),
                    "First request ID incorrect");
            require(lines.get(1).contains(
                    "\"request_id\":\"req_102\"")
                    && !lines.get(1).contains("req_101"),
                    "Second request ID incorrect");

            for (String line : lines) {
                require(!line.contains("FAKE_SECRET_CANARY_494"),
                        "Sensitive input leaked");
                require(line.indexOf('\n') < 0
                        && line.indexOf('\r') < 0,
                        "JSONL event has physical newline");
                System.out.println(line);
            }
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Lệnh chạy:

```bash
javac --release 17 LoggingBaselineDemo.java
java LoggingBaselineDemo
```

**Stdout chính xác (hai JSONL records):**

```json
{"@timestamp":"2026-11-10T03:15:00Z","schema.version":1,"level":"INFO","service.name":"checkout-api","event.name":"checkout.completed","http.route":"/orders/{id}/checkout","http.status_code":200,"duration_ms":12,"outcome":"SUCCESS","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","request_id":"req_101"}
{"@timestamp":"2026-11-10T03:15:00Z","schema.version":1,"level":"WARNING","service.name":"checkout-api","event.name":"checkout.rejected","http.route":"/orders/{id}/checkout","http.status_code":409,"duration_ms":4,"outcome":"DENIED","trace_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","request_id":"req_102","error.code":"OUT_OF_STOCK"}
```

**Cách đọc kết quả:**

- `schema.version`, `http.status_code` và `duration_ms` là JSON numbers chứ không phải string.
- Event thứ nhất INFO, event thứ hai **WARNING** theo tên `java.util.logging.Level.WARNING`. Ở SLF4J/Logback cùng ý nghĩa thường là **WARN**; nếu dashboard dùng enum `WARN`, phải normalize hoặc map đúng backend.
- `trace_id` và `request_id` không bị lẫn giữa hai context.
- `FAKE_SECRET_CANARY_494` không xuất hiện dù có mặt trong `SensitiveInput`.
- Vì `handler` được gắn vào JUL Logger thật, ta kiểm được điều kiện logger/handler thực sự nhận hai event; nhưng ví dụ không kiểm collector hay lưu bền vững.
- `quote(...)` escape dấu nháy, backslash và ASCII control chars, **không phải JSON serializer production tổng quát** (chưa kiểm Unicode surrogate, nested data, binary và nhiều kiểu khác). Dùng encoder JSON có kiểm thử khi triển khai thực.
- Timestamp cố định là **fixture**, không phải cách production lấy thời gian. Ứng dụng thật phải ghi UTC/offset từ nguồn clock tin cậy.
- ThreadLocal ở ví dụ chỉ dành cho demo đồng bộ. Khi dùng executor/async, phải truyền context có kiểm soát và restore nó ở worker.
- Thông tin business outcome trong mẫu do code tạo cố định để minh họa; production phải phản ánh kết quả nghiệp vụ đã thực sự xảy ra.

## 11. Bài thực hành B — Tích hợp Spring Boot/SLF4J

Với ứng dụng mới đã dùng **Spring Boot phiên bản có structured logging tích hợp**, có thể bắt đầu bằng logging JSON trên console. Theo tài liệu Spring Boot 4.x, thuộc tính sau được hỗ trợ:

```properties
# application.properties cho một Spring Boot release tương thích
spring.application.name=checkout-api
logging.level.root=INFO
logging.level.com.example.checkout=INFO

# Dùng JSON Logstash format tích hợp của Spring Boot.
logging.structured.format.console=logstash
```

**Điểm quan trọng:**

- Các properties này **không có hiệu lực trên chương trình JDK thuần** ở phần A.
- `logging.structured.format.console=logstash` là **format identifier do Spring Boot hỗ trợ trong các release tương thích**; với Boot cũ, có thể phải thêm một JSON encoder riêng. Không áp dụng bừa vào Spring Boot không hỗ trợ property.
- Nếu đã cung cấp `logback-spring.xml`/cấu hình Log4j2 tùy chỉnh, **cấu hình appender có thể cần sử dụng structured encoder/layout tương ứng**. Chỉ set property chưa chắc override custom pattern.
- Format `logstash` thường có các field mặc định của backend như `@timestamp`, `level`, `logger_name`, `message`; **không mặc định trùng 100% schema trong bài JDK**.
- Các cặp key-value của SLF4J 2 có thể xuất hiện trong JSON nếu encoder/framework hỗ trợ, nhưng **phải chạy integration test kiểm field shape/type**.
- Theo cùng tài liệu Spring Boot, có thể chọn `ecs` hoặc `gelf` thay `logstash` khi backend tiêu thụ format đó. Không đổi format mà không cập nhật parsing/mapping và dashboard.
- **Không bật cả console JSON và file JSON nếu collector cùng thu cả hai nguồn**: việc đó có thể nhân đôi event hoặc tăng chi phí.

### Maven/Gradle và versions

Đối với project Spring Boot, hãy tạo project bằng bản Spring Boot được tổ chức hỗ trợ, thêm Web và Test (và Actuator nếu có kế hoạch dùng metrics/health), giữ một logging backend được framework chọn và lock versions trong build của repo. Mẫu phần B là **hướng dẫn tích hợp vào project có sẵn**, không phải một `pom.xml` độc lập với version cố định cho mọi môi trường.

Nếu chỉ muốn chạy ví dụ phần A, **không cần Maven, SLF4J, Spring Boot hay JSON dependency nào**.

## 12. Spring service: structured fields bằng SLF4J 2.x

Ví dụ **trích đoạn** trong một service Spring Boot đã cấu hình `org.slf4j.Logger`:

```java
// Trích đoạn tích hợp; cần Spring Boot/SLF4J 2.x và logger của service.
logger.atInfo()
      .addKeyValue("event.name", "checkout.completed")
      .addKeyValue("http.route", "/orders/{id}/checkout")
      .addKeyValue("http.status_code", 200)
      .addKeyValue("duration_ms", 12L)
      .addKeyValue("outcome", "SUCCESS")
      .log("Checkout completed");
```

Ở đây `.addKeyValue(...)` làm phần key-value rõ ràng hơn so với ghép chuỗi text. **Nhưng không tự động bảo đảm** encoder sinh cùng một JSON schema, vì backend/JSON format có thể chọn cách serialize khác.

Nếu dùng code tương ứng cho lỗi:

```java
// Trích đoạn có logger đã tạo; chỉ ghi safe reason code.
logger.atWarn()
      .addKeyValue("event.name", "checkout.rejected")
      .addKeyValue("http.route", "/orders/{id}/checkout")
      .addKeyValue("http.status_code", 409)
      .addKeyValue("error.code", "OUT_OF_STOCK")
      .addKeyValue("outcome", "DENIED")
      .log("Checkout rejected");
```

Để output nhất quán, cân nhắc một `AuditEventBuilder` / `ApplicationEventLogger` **do dự án tự xây** nhằm chuẩn hóa names, outcome, đơn vị, field restrictions và field collision policy. Các tên class này là abstraction thiết kế, **không phải class bắt buộc của Spring**.

### Tránh duplicate fields

Một JSON encoder có thể tự thêm `level`, `service.name`, `trace_id`, `@timestamp`. Nếu ứng dụng lại thêm cùng tên qua MDC/key-value, output có thể có duplicate JSON keys hoặc bị ghi đè tùy backend. Hãy định nghĩa rõ **quyền sở hữu mỗi field**.

| Field | Owner gợi ý |
| --- | --- |
| Timestamp/log level/logger | Logging backend/encoder |
| Service name/environment/version | Trusted deployment/config |
| Event name/action/outcome | Business/security code |
| HTTP route/status/duration | HTTP instrumentation/business boundary |
| Trace ID/span ID | Tracing instrumentation |
| Request ID | Gateway/filter tạo/validate |
| Tenant/actor | Verified security context |
| Ingest time/host/agent ID | Collector/backend |

Không lấy `service.name` hay `tenant.id` từ headers do client tự khai.

## 13. Correlation trong Spring: MDC, tracing và propagation

Nếu đã bật Micrometer Tracing đúng dependencies/config trong Spring Boot, tài liệu Spring Boot mô tả correlation logging dựa trên `traceId`/`spanId` trong MDC. Điều đó giúp tìm log gắn với trace, nhưng **không có nghĩa dependency tracing tự được bật chỉ vì đã thêm Actuator**. Xác nhận bản build đang có tracing implementation phù hợp.

Một trích đoạn tạo request ID an toàn trong scope hiện tại:

```java
// Trích đoạn SLF4J; validatedRequestId đến từ nguồn đã kiểm tra.
String old = org.slf4j.MDC.get("request_id");
org.slf4j.MDC.put("request_id", validatedRequestId);
try {
    handleCheckoutRequest();
} finally {
    if (old == null) {
        org.slf4j.MDC.remove("request_id");
    } else {
        org.slf4j.MDC.put("request_id", old);
    }
}
```

**Đây không phải lớp HTTP filter hoàn chỉnh.** Nó minh họa save/restore một key. Không bỏ `finally` trong thread pool; không dùng `MDC.clear()` để xóa cả context của tầng cha khi không sở hữu.

### Với xử lý bất đồng bộ

Nếu service enqueue một job:

1. Lúc HTTP request đã được xác thực, chụp metadata correlation và initiated_by theo schema hợp lệ.
2. Bảo vệ job metadata trước khi truyền sang queue/DB; không mang password/token vào job để tiện logging.
3. Worker chạy dưới **service identity** và có context riêng; nếu cần truy người khởi xướng, ghi `initiated_by` với bằng chứng.
4. Thiết lập context trong scope của message handler, restore sau khi hoàn tất.
5. Khi retry, giữ `operation_id` và attempt ID để phân biệt retry và một thao tác mới.
6. Đừng mặc định MDC là một hệ thống distributed tracing: propagation qua process/network cần instrumentation thích hợp.

Truyền trace context qua HTTP client nên dựa vào builder/instrumentation mà framework hỗ trợ; một `new RestClient`/`new WebClient` tạo thủ công có thể không được tự instrument tùy phiên bản/cấu hình.

## 14. HTTP access log: đừng ghi trùng và không dump payload

Application events trong service không thay thế access log của HTTP server. Có hai cách phổ biến:

- **Container/gateway access log** ghi method/status/duration, có thể dùng trước khi request vào controller.
- **Application filter/instrumentation** ghi metadata theo route đã match và business boundary.

Nếu cả hai đều phát, có thể hợp lý **nếu phân biệt nguồn/hop/event type**, nhưng không nên đếm số dòng log là số request thực khi chưa có cơ chế dedup.

### Trường không nên dùng mặc định

- `getRequestURI()`/raw URL: có thể chứa ID, reset token, email, query.
- `getHeader("Authorization")`, `getCookies()`, `getQueryString()`.
- Request/response body, file upload và DTO `toString()`.
- Stack trace exception chứa raw HTTP client response.
- Các ID không được validate từ client.

Một access event an toàn có thể chỉ gồm `method`, **trusted matched route template**, `status`, `duration_ms`, `request_id` đã kiểm tra và source service. Đối với endpoint login/token/payment có policy riêng, có thể chỉ dùng nhãn `AUTH_ENDPOINT` hoặc `PAYMENT_ENDPOINT`.

**Async/SSE/streaming:** filter `finally` không luôn tương đương response completion; nếu yêu cầu status/duration cuối, dùng server/access logger hoặc lifecycle instrumentation phù hợp. Không gọi `response.getStatus()` ở một thời điểm chưa kết thúc rồi khẳng định đó là final status.

## 15. Cấu hình theo môi trường

Một baseline nên có **một nguồn sự thật về chính sách** và profile rõ:

| Môi trường | Định dạng và sink | Level và mục đích |
| --- | --- | --- |
| Local/dev | Console text hoặc JSON tùy nhu cầu | DEBUG theo package, không log real secret |
| Test/CI | JSONL/captured appender | INFO và test schema/secret/trace; deterministic fixtures |
| Staging | Gần giống production | Kiểm end-to-end, collector, retention, async |
| Production container | stdout/stderr JSONL + collector | Root INFO, package override đã review |
| Production VM | Rolling file hoặc stdout/systemd | File size + archive retention + permissions |

### Development không được làm môi trường “không cần privacy”

Đừng bật raw body/tokens chỉ vì “chạy local”. Dữ liệu thử có thể bị copy từ production hoặc đi qua CI logs. Cần dùng canary giả và test accounts.

### Production baseline tối thiểu

- Logger level root INFO; giảm DEBUG/TRACE không cần thiết.
- JSON structured output theo format/schema đã chốt.
- Không log bí mật; các exception/dependency logs được review.
- Correlation IDs cho request flows, không rò context.
- Queue/collector/sink có health signals và ownership.
- Retention phân loại theo application/access/security/audit.
- Có runbook đổi DEBUG tạm thời và rollback.
- Có test phát hiện schema drift, missing fields và raw secret.

## 16. Async logging: chọn trade-off trước khi bật

Async appender có thể giảm thời gian chờ ghi disk/network trên request thread, nhưng không phải phép màu. Khi sink chậm:

```text
Application thread
    |
    ▼
Bounded queue ──► Consumer ──► File/stdout/collector
    |
    ├─ queue còn chỗ: enqueue
    └─ queue đầy: block / discard / fallback theo policy
```

Với Logback `AsyncAppender`, các tùy chọn như `queueSize`, `discardingThreshold`, `neverBlock`, `maxFlushTime` kiểm soát khả năng chịu tải và mất event. Tài liệu Logback cho biết mặc định có thể loại INFO/DEBUG/TRACE sớm khi queue gần đầy (tùy cấu hình). Nếu `neverBlock=false` thì producer có thể bị chặn khi queue đầy; `neverBlock=true` có thể bỏ event thay vì chặn.

**Đừng đặt `discardingThreshold=0` rồi tuyên bố “không mất log”.** Crash, shutdown không drain, appender write errors và backend failures vẫn có thể gây mất.

### Những câu hỏi phải có câu trả lời

- Queue giới hạn bao nhiêu event/bytes, tại tốc độ peak chịu được mấy giây?
- Khi đầy, ưu tiên **request latency** hay **khả năng giữ log**?
- Event nào có thể discard? Audit/security event bắt buộc có sink riêng chưa?
- App có metrics queue depth/dropped/wait/sink errors không?
- Shutdown/deploy rollout có drain queue trong giới hạn thời gian không?
- Collector outages kéo dài thì node disk/spool chịu được bao lâu?
- Replay hoặc retry có tạo duplicate không? Có event ID/operation ID để đối soát?

**Đánh giá bằng load test** với sink chậm và traffic burst; không chọn chính sách chỉ từ một benchmark throughput lý tưởng.

## 17. File rotation và retention không phải cùng việc

Nếu ứng dụng chạy trên VM cần file logging, **`FileAppender` không có rolling** có thể để file tăng vô hạn. Logback có `RollingFileAppender` và policy size/time:

```xml
<!-- Trích đoạn Logback; chọn khi triển khai file sink trên VM. -->
<appender name="APPLICATION"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>
    <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
        <maxFileSize>50MB</maxFileSize>
        <maxHistory>7</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
        <cleanHistoryOnStart>true</cleanHistoryOnStart>
    </rollingPolicy>
    <encoder>
        <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

**Trích đoạn này dùng pattern text, không tự tạo JSON và không thể đi kèm config `logging.structured.format.console` để mặc định file thành JSON.** Nếu file sink cần structured JSON, thay encoder phù hợp hoặc dùng cấu hình Boot structured file đã được hỗ trợ/kiểm thử. Nó không phải một `logback-spring.xml` hoàn chỉnh.

- `maxFileSize` kích hoạt rollover, không là hard quota tuyệt đối.
- `maxHistory=7` với date pattern ngày nghĩa là 7 kỳ archive, không phải chính xác 7 file.
- `totalSizeCap` giới hạn tổng archive do policy quản lý, không phải toàn filesystem.
- Cleanup có thể chạy vào rollover/startup, không bảo đảm đúng giây.
- Application access log, Tomcat, gateway, container stdout và central backend có retention riêng.

Trong Kubernetes, stdout/stderr thường được container runtime/kubelet rotate; file tự ghi vào volume không tự được kubelet quản lý. Không để appender rolling và host logrotate **cùng thay file** nếu chưa test; `copytruncate` có thể có cửa sổ mất log.

**Retention phải phân loại:** DEBUG/application/access có thể giữ ngắn hơn security/audit. Không có số ngày mặc định hợp lệ cho tất cả tổ chức; cần quyết định theo nghiệp vụ, hợp đồng, luật và quy trình legal hold.

## 18. Audit/security event: một đường riêng khi cần bảo toàn

Một thay đổi quyền có thể cần câu trả lời “ai đã làm, ai bị ảnh hưởng, outcome thật là gì?”. Baseline application logging có ích nhưng chưa đủ chứng minh audit reliability.

Event audit nên tách rõ:

```json
{
  "event.name": "role.granted",
  "actor.type": "USER",
  "actor.id": "user_42",
  "target.type": "USER",
  "target.id": "user_91",
  "outcome": "COMMITTED",
  "operation_id": "op_19"
}
```

Không dùng `target.id` làm actor; không lấy actor từ raw `X-User-ID`. Nếu worker chạy bằng service identity nhưng user khởi xướng, có thể ghi `executor=SERVICE` và `initiated_by=USER` **nếu liên kết đã được xác minh**, không gộp bừa.

Đối với audit sau transaction, cân nhắc **transactional outbox** hoặc storage chuyên dụng để gắn business state với event trong cùng transaction; vẫn cần retry, duplicate handling, bảo vệ kho và chứng minh event cuối cùng được ingest.

### Không sampling audit tùy tiện

Sampling 1/100 log debug có thể hợp lý khi traffic cao, nhưng sampling event `role.granted` có thể làm mất chứng cứ. Chọn chính sách theo **event kind** và retention requirement; không áp cùng cơ chế discard cho mọi stream.

## 19. Baseline error handling và exception hygiene

Khi một dependency lỗi, cần biết:

- Tên dependency **loại dịch vụ**, không nhất thiết URL/host nội bộ nhạy cảm.
- Safe reason code do server định nghĩa, ví dụ `PAYMENT_TIMEOUT` hoặc `INVENTORY_UNAVAILABLE`.
- Status và outcome nghiệp vụ ở đúng mốc.
- Request/trace/operation ID để tìm chuỗi xử lý.
- Duration và attempt number khi retry.
- Exception type/stack trace **chỉ khi đã review khả năng chứa secret**.

Tránh:

```java
// Ví dụ KHÔNG AN TOÀN, trích đoạn:
logger.error("Failed request {}", request);
logger.error("Headers={}, body={}", headers, body);
logger.error("Dependency error " + exception.getMessage());
```

Các call trên có thể kéo token/PII từ DTO, headers hoặc message của thư viện. Thay bằng event có allowlisted fields và error code; nếu cần stack trace, đưa vào sink có policy và kiểm thử riêng.

**Một event lỗi nên có owner rõ.** Không để cùng exception bị log ERROR lặp ở mọi tầng khi không có thêm thông tin. Có thể ghi một ERROR ở HTTP/business boundary, còn các bước bên trong dùng metric hoặc debug context có kiểm soát.

## 20. Kiểm thử baseline: unit, integration và end-to-end

Một log schema đúng trong code chưa bảo đảm JSON encoder/backend đúng. Cần tối thiểu ba tầng:

| Tầng | Nội dung test |
| --- | --- |
| Unit | Event catalog, required fields, safe codes, allowed value types |
| Integration | Logger + encoder + appender thật, output JSONL, level/filters, MDC |
| End-to-end | Collector → backend mapping/query, retention, dropped/lag, quyền xem |

### Bộ test contract cốt lõi

1. **Schema:** event có các trường bắt buộc, optional chỉ xuất hiện khi được phép.
2. **Type:** `http.status_code` và `duration_ms` là JSON number, `success` là boolean nếu contract có.
3. **Time:** timestamp parse được, UTC/offset rõ, không dựa locale.
4. **Escape:** quote/backslash/CR/LF/Unicode không làm JSONL thành nhiều dòng vật lý.
5. **Privacy:** canary giả trong header/body/query/exception không xuất hiện ở JSON.
6. **Correlation:** request A và B không lẫn trace/request/tenant.
7. **No context:** scheduled/startup event có policy rõ khi thiếu request ID.
8. **Error case:** safe error code, không tự dump Throwable chứa token.
9. **Level:** INFO/WARN/ERROR được xuất hoặc lọc theo effective config thực.
10. **Async:** drain hoặc synchronization trước assertion, không chỉ `Thread.sleep(...)` tùy may.
11. **Backpressure:** queue đầy, sink chậm, shutdown, retry và dropped semantics đã test.
12. **Collector:** parse đúng types, index đúng service/tenant, time lag trong ngưỡng.
13. **Retention:** xóa theo policy, archive/backup/hold được kiểm tra riêng.
14. **Deployment:** release/version change không làm schema vỡ hoặc duplicate event.

### Assertion JSON bằng Jackson (trích đoạn integration test)

Giả sử test fixture đã lấy **một dòng JSON từ actual encoder** vào biến `line`, có thể dùng:

```java
// Trích đoạn JUnit 5 + Jackson; line là một dòng JSONL thực tế
// được fixture của test capture từ appender/file/stdout.
com.fasterxml.jackson.databind.JsonNode node =
        new com.fasterxml.jackson.databind.ObjectMapper().readTree(line);

org.junit.jupiter.api.Assertions.assertTrue(node.isObject());
org.junit.jupiter.api.Assertions.assertTrue(
        node.path("http.status_code").isIntegralNumber());
org.junit.jupiter.api.Assertions.assertEquals(
        200, node.path("http.status_code").intValue());
org.junit.jupiter.api.Assertions.assertTrue(
        node.path("duration_ms").isIntegralNumber());
org.junit.jupiter.api.Assertions.assertFalse(
        line.contains("FAKE_SECRET_CANARY_494"));
```

**Không chỉ gọi `node.path(...).asInt()`** rồi tưởng đã kiểm type: một số conversion API có thể chuyển string số thành int. Cần kiểm `isIntegralNumber()` hoặc schema validator trước.

Nếu dùng ECS/Logstash/nested JSON, phải sửa JSON path theo **format đã chọn và xác minh bằng test**, không ép assertion flat keys của dự án mẫu vào format khác mà không mapping.

## 21. Baseline release gate cho CI/CD

Đề xuất nhóm tối thiểu:

| Gate | PASS khi |
| --- | --- |
| **Compile** | JDK17 demo build và chạy, status code 0 |
| **Content schema** | Required field names/types hợp lệ cho từng event |
| **Secret scanner** | Canary không xuất hiện trong output/logs |
| **JSONL parser** | Mỗi dòng parse ra một JSON object hợp lệ |
| **Event isolation** | Request/trace IDs không lẫn giữa các context |
| **Logger config** | Effective levels/format đúng profile |
| **Backend compatibility** | Encoder output parse và index theo schema đã chốt |
| **Async/failure** | Không phá p99 ngoài ngưỡng; dropped policy đúng |
| **Operational safety** | Retention/quota/owner có bằng chứng và alert |
| **Audit preservation** | Các event bắt buộc không bị sampling nhầm |

Một test PASS không có nghĩa toàn bộ production luôn giữ được log khi crash. Chia rõ **unit correctness**, **appender delivery**, **collector ingestion** và **durability requirements**.

### Dùng fixture có thể tái lập

Inject `Clock.fixed`, dùng IDs/actor giả và **canary token**; không cần dùng bí mật thật trong CI. Tách logger state, MDC và output capture giữa các test để không tạo flaky tests khi chạy song song.

## 22. Mẫu dữ liệu nghiệm thu

Bảng này giúp người review hiểu ngay dự án đã hoàn tất phần nào:

| Tình huống | Event mong đợi | Status/Outcome | Không được xuất |
| --- | --- | --- | --- |
| Checkout thành công | `checkout.completed` | 200 / SUCCESS | Token/card/raw body |
| Hết hàng | `checkout.rejected` | 409 / DENIED | PII trong error message |
| Dependency timeout | `checkout.dependency_failed` | 504 / FAILED | Full URL có token |
| Login denied | Security event từ auth layer | 401/403 / DENIED | Password/OTP, actor tự khai |
| Job accepted | `checkout.accepted` | 202 / ACCEPTED | Đánh dấu completed trước worker |
| Worker completed | `checkout.completed` | COMMITTED/SUCCESS theo nghiệp vụ | Nhầm executor service với initiator |
| Health probe | Metric hoặc access tối giản | 200/UP theo schema | Log INFO spam mỗi vài giây |
| Unknown URL | Generic route class | 404 / FAILED theo HTTP semantics | Raw path/query do client đặt |
| Logger sink lỗi | Appender error + metric | Delivery incident | Khẳng định đã lưu khi chưa có ack |

Đừng viết `actor.id=user_42` từ username trong login request bị từ chối. Một login attempt chưa xác thực nên được ghi dưới dạng anonymous/claimed identifier phân biệt rõ, nếu policy cần.

## 23. Monitoring và SLO tối thiểu

Bộ metric đề xuất (**không mặc định có sẵn** ở mọi SLF4J backend):

| Metric / tín hiệu | Tác dụng |
| --- | --- |
| `logging_events_attempted_total` | Số event ứng dụng dự định phát |
| `logging_events_filtered_total` | Số bị lọc theo level/policy |
| `logging_events_dropped_total` | Số mất do queue/overload |
| `logging_queue_depth` | Backlog appender |
| `logging_sink_errors_total` | Lỗi ghi file/stdout/socket |
| `collector_receiver_accepted_total` | Số collector nhận (theo semantic của collector) |
| `collector_exporter_failed_total` | Lỗi gửi backend |
| `log_ingest_lag_seconds` | Trễ event → searchable backend |
| `last_seen_log_event_timestamp` | Dữ liệu mới nhất theo source |
| `log_storage_used_bytes` | Nguy cơ vượt quota/retention |
| `audit_delivery_errors_total` | Audit pipeline cần được đánh giá riêng |

**Không so counters ở các ranh giới khác nhau như một đẳng thức tuyệt đối:** window, retry, filtered-by-design, batch ack và duplicate có thể gây lệch.

Ví dụ mục tiêu SLO **cần được tổ chức điều chỉnh**:

- 95% application events được tìm thấy trong backend trong 2 phút sau ingest ở tải ổn định.
- Queue không backlog kéo dài quá một ngưỡng đã thống nhất.
- Không có sink errors không được cảnh báo.
- Production disk còn capacity an toàn theo forecast.
- Không có canary hoặc raw secret vào sink không cho phép.
- Security/audit pipeline đáp ứng yêu cầu bền vững riêng.

Nếu backend search tạm trống, phân biệt **chưa thấy**, **đến chậm** và **đã mất**. Chỉ producer ghi INFO không chứng minh backend lưu được.

## 24. Cấu hình runtime và quyền truy cập

### Container

Ứng dụng thường ghi stdout/stderr, collector đọc và chuyển đi. Cần:

- JSONL nhất quán trên stream được thu, tránh lẫn text multi-line.
- Chính sách node-local log rotation không phụ thuộc retention của backend.
- Health/metrics của collector, disk spool, queue và retry.
- Namespace/service/tenant routing đáng tin.
- Không bật cả file+stdout nếu sẽ duplicate thu gom.

### VM

Nếu dùng file appender, xác định log directory, quyền filesystem, user process, quota, rotation và collector tail behavior. Một file `app.log` đang được mở có thể không giải phóng dung lượng ngay khi bị unlink; không dùng `rm`/`truncate` như remediation mặc định.

### RBAC & privacy

- Quyền **xem/search** khác **đổi retention** và **xóa**.
- Security/audit logs có thể cần permission riêng và immutable archive.
- Dashboard masking không xóa bản raw trong index, snapshot, backup và export.
- Khi incident liên quan token/PII, cần xử lý revoke/rotate và báo security, không chỉ giảm log level.

## 25. Kịch bản diễn tập lỗi cho dự án

### Case 1: Collector bị ngắt

Ứng dụng vẫn in JSONL nhưng backend không có event mới. Kiểm source stdout, collector retry/lag, buffer policy và thời gian chịu đựng trước khi log bị drop. Không restart cả cluster chỉ vì dashboard trống.

### Case 2: Queue đầy

Tạo burst trong staging; kiểm chính xác appender đang block producer hay discard. Đo request p95/p99 và số event bị mất; đảm bảo event audit bắt buộc không bị bỏ theo policy debug.

### Case 3: Bật DEBUG ngoài ý muốn

Thấy tốc độ byte/s tăng sau deploy; kiểm effective logger levels, size/event, serializer, MDC, stack traces và log volume. Khôi phục đúng logger qua change process, không hạ mọi ERROR nếu nó báo sự cố thật.

### Case 4: Token trong exception

Canary giả xuất hiện ở message của HTTP client; test phải FAIL. Sửa tại nguồn/encoder và kiểm mọi copies: app file, stdout, collector, index, export; với secret thật cần security response và rotation.

### Case 5: Sai trace ID do ThreadLocal

Hai request chạy chung pool; logger dùng `MDC.put` nhưng không dọn. Reproduce trong concurrent test, thêm scope/restore, xác nhận tenant/trace không lẫn.

### Case 6: Schema drift

Thay JSON encoder dẫn đến `http.status_code` từ number thành string. Dashboard aggregation hỏng dù event vẫn hiện. Contract test phải phát hiện và rollout có schema version/migration.

### Case 7: Retention bị đặt nhầm

Application logs xóa sau 7 ngày trong khi điều tra cần 30 ngày; kiểm ILM/index-age/rollover, node file rotation và archive/snapshots. Không tự xóa hoặc đổi legal hold không có thẩm quyền.

## 26. Bài tập mở rộng có thể giao cho người học

Bộ dự án đủ dùng có thể hoàn tất theo từng bước:

**Giai đoạn 1 — Baseline contract:** tạo event catalog và JSON schema; quyết định required/optional, units, enum, pii classes. Giải thích vì sao `status` là number và vì sao không ghi raw URL.

**Giai đoạn 2 — JDK demo:** chạy `LoggingBaselineDemo.java`, kiểm hai JSONL records đúng stdout; sửa code để kiểm missing context, invalid request ID và log forging negative cases.

**Giai đoạn 3 — Spring integration:** dùng Spring Boot release được hỗ trợ, bật `logging.structured.format.console=logstash`, thêm SLF4J key-value fields trong một service, kiểm actual encoder output. Thêm mapping nếu format không trùng contract đã chọn.

**Giai đoạn 4 — Context:** tích hợp request ID qua một boundary đáng tin, tracing nếu có; thử hai request song song và một async job, xác nhận không rò context.

**Giai đoạn 5 — Privacy:** đưa `FAKE_SECRET_CANARY_494` vào header/body/error fixture, quét stdout/appender/backend; chặn từ nguồn và kiểm regression.

**Giai đoạn 6 — Operations:** cấu hình logging sink đúng VM/container, collector, retention/alerting, bài thử sink chậm và playbook xử lý.

**Giai đoạn 7 — Handoff:** review schema version, owner, CI gates, SLO, privacy policy và rollback instructions, lưu bằng chứng test.

### Tiêu chí chấm bài thực hành

| Tiêu chí | Đạt khi |
| --- | --- |
| Đúng bài toán | Có kiến trúc và mục tiêu logging baseline cụ thể cho checkout-api |
| Đúng dữ liệu | Event catalog, schema, types, units và outcome được mô tả |
| Runnable | JDK17 demo chạy và ra hai JSONL records đúng |
| An toàn | Không log secret/token/card, dùng route template |
| Quan sát được | Có request/trace ID tương quan, context isolation |
| Tích hợp | Spring Boot JSON layout + SLF4J được kiểm actual output |
| Vận hành | Có retention/quota, dropped/lag metrics, runbook |
| Kiểm thử | Unit/integration/E2E matrix và canary checks |
| Đúng giới hạn | Phân biệt app logging, access log, audit và tracing |
| Bàn giao | Có owner, config/version, acceptance evidence |

**Không đạt** nếu chỉ có code `logger.info("hello")`, hoặc chỉ đổi format từ text sang JSON mà không kiểm schema, secret, correlation, retention và khả năng tìm log.

## 27. Những anti-pattern thường gặp

| Anti-pattern | Vì sao sai | Thay bằng |
| --- | --- | --- |
| Ghi message tự do không schema | Query/aggregation dễ vỡ | Event code + structured fields |
| Mọi log đều ERROR | Alert fatigue, không thấy mức nghiêm trọng | Level policy theo event/outcome |
| Dump raw request/response | Lộ token/PII, log volume lớn | Field allowlist + route template |
| Tự ghép JSON bằng string production | Escape/type/encoding lỗi | Encoder JSON được kiểm thử |
| Dùng trace ID làm actor | Trace không chứng minh identity | Verified principal và audit schema |
| MDC không cleanup | Rò request/tenant qua thread pool | Scoped put + finally/restore |
| Async queue vô hạn hoặc “không bao giờ mất” | OOM/drop/block hoặc false assurance | Bounded queue, counters, failure tests |
| File log không rolling | Disk full, vận hành khó | Rolling/retention/quota hoặc stdout với node rotation |
| Ghi audit vào debug log có discard | Có thể mất bằng chứng | Dedicated audit policy/outbox |
| Đổi JSON encoder không test backend | Mapping/type/field drift | Consumer contract tests |
| Dashboard có log nên tưởng bền | Collector/index có thể trễ/lỗi | End-to-end checks + acknowledgement semantics |
| Bật DEBUG toàn root khi incident | Volume/PII/CPU tăng | Scoped temporary change + rollback |
| Không phân loại dữ liệu theo retention | Giữ PII lâu hoặc xóa audit sớm | Retention theo event kind và legal review |
| Dùng IDs làm metric labels | Cardinality và chi phí bùng nổ | Low-cardinality route/status/service |
| In exception nguyên gốc | Có thể chứa token/body | Safe code và controlled stack trace |

## 28. Mẫu README bàn giao cho service thật

Khi triển khai dự án vào repository của tổ chức, tài liệu vận hành của từng service nên trả lời:

```text
Service: checkout-api
Owner: application on-call / observability on-call
Logging facade/backend: SLF4J + configured JSON backend
Default output: stdout JSONL (container)
Format contract: baseline schema v1 + accepted encoder mapping
Environment: production / staging / dev
Levels: root INFO, package overrides under change control
Correlation: validated request ID + trace/span context if enabled
Sensitive fields: token/password/card/raw body excluded at source
Event catalog: checkout.completed, checkout.rejected, ...
Retention classes: app/access/security/audit defined by owner
Sink/backpressure: known queue and failure policy
SLO/alerting: lag, dropped, sink errors, disk quota
Search workflow: service → event.name → trace/request ID
Change workflow: scoped DEBUG with expiry and rollback
Test evidence: schema JSON, privacy canary, async isolation, ingest
Escalation: application, platform, security/compliance
```

Đây là mẫu minh họa, không phải giá trị môi trường thật. Không đưa secret, URL nội bộ nhạy cảm hoặc thông tin xác thực vào README bàn giao.

## 29. Checklist nghiệm thu cuối cùng

- [ ] Có mục tiêu rõ: troubleshooting, security, performance và mức độ chi tiết cần thiết.
- [ ] Đã mô tả đầy đủ chặng Java → stdout/file → collector → backend.
- [ ] Event catalog có mã sự kiện, owner, level, outcome và điều kiện phát.
- [ ] Schema có tên field/type/units, required/optional và version.
- [ ] Timestamp UTC, numeric status/duration, route template an toàn.
- [ ] Dữ liệu nhạy cảm bị loại ở nguồn; canary test PASS.
- [ ] Log forging/escaping được kiểm tra bằng JSON parser thật khi tích hợp.
- [ ] Request/trace ID được validate, không dùng làm identity.
- [ ] MDC/context không rò giữa request/async worker và tenant.
- [ ] Spring Boot/SLF4J format thực tế đã được đối chiếu schema.
- [ ] File/stdout có owner, rotation/quota hoặc collector policy phù hợp.
- [ ] Có retention riêng cho app, access, security và audit.
- [ ] Có quan sát queue/backpressure, sink errors, dropped events, ingest lag.
- [ ] Không khẳng định logger call = backend đã lưu.
- [ ] Có kiểm thử startup, INFO/WARN/ERROR, missing field, schema drift.
- [ ] Có ít nhất một bài test sink failure và một bài test privacy leak giả.
- [ ] DEBUG tạm thời có quyền, scope, thời hạn và rollback.
- [ ] Có runbook tìm log theo event/ID an toàn và escalation owner.
- [ ] Có release gate, CI evidence, schema contract và version change process.
- [ ] Có giới hạn rõ: baseline không thay thế audit durability, metrics hoặc traces.

**Ghi nhớ:** một **logging baseline đạt yêu cầu** không đơn thuần là “bật logger” hoặc “xuất JSON”. Nó là một **hợp đồng chung giữa mã Java, backend logging, collector, đội vận hành và bảo mật**: log đúng sự kiện, đúng kiểu, đúng context, không lộ bí mật, được đưa tới nơi cần tìm, được giữ đúng thời hạn và có kiểm thử xác minh thực tế.

### Tài liệu tham khảo

- [Spring Boot — Logging, structured logging và formats](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot — Tracing, correlation IDs và propagation](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [SLF4J Manual — Fluent Logging API](https://www.slf4j.org/manual.html)
- [Logback — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html)
- [Logback — RollingFileAppender](https://logback.qos.ch/manual/appenders-rolling.html)
- [Oracle — java.util.logging.Logger (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [Kubernetes — Logging architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/)

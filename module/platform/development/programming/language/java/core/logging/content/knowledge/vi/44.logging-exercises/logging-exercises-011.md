# Tạo runbook vận hành Java Logging: dự án thực hành từ cảnh báo đến phục hồi

## 1. Mục tiêu và sản phẩm cuối của dự án

**Runbook vận hành** là tài liệu hành động giúp người trực ca (on-call), SRE, developer và bộ phận liên quan **phát hiện, xác minh, phân loại, giảm tác động, khôi phục và ghi nhận** một sự cố. Đối với Java Logging, runbook không chỉ hướng dẫn “mở file log”, mà mô tả rõ **đường log, ý nghĩa các sự kiện, bằng chứng cần thu thập, điểm ra quyết định, quyền thực thi và điều kiện xác nhận sự cố đã được xử lý**.

Sau bài thực hành, bạn sẽ tạo một runbook mẫu cho dịch vụ Java giả định `orders-api` có hai loại sự cố:

- **Sự cố ứng dụng:** yêu cầu `POST /orders` bị HTTP 503 do timeout ở dependency. Log có các sự kiện `REQUEST_STARTED`, `DEPENDENCY_TIMEOUT` và `REQUEST_FAILED`.
- **Sự cố khả năng quan sát:** ứng dụng vẫn chạy nhưng log không xuất hiện ở backend vì level/filter, output sink, agent, Collector hoặc exporter có vấn đề.

**Sản phẩm hoàn thành** gồm: runbook có owner và phạm vi, bảng tín hiệu/cảnh báo, cách thu thập evidence, sơ đồ quyết định, thao tác chẩn đoán an toàn, điều kiện escalation/rollback/recovery, hướng dẫn kiểm tra pipeline log, kịch bản diễn tập và một chương trình **Java 17 chạy độc lập** tạo dữ liệu JSON Lines để luyện đọc log.

Bài học thuộc mục **Dự án thực hành**, nên các lệnh và tình huống được viết để người học có thể áp dụng vào môi trường test trước khi chuyển thành SOP cho hệ thống thật. **Không coi tên service, namespace, ngưỡng alert hoặc thời hạn trong bài là cấu hình đang tồn tại ở doanh nghiệp.** Chúng là giả định có chủ đích cho phòng thực hành.

## 2. Runbook khác tài liệu logging và playbook như thế nào?

Một tài liệu giới thiệu logging có thể giải thích `INFO`, `WARN`, `ERROR` và cách cấu hình Logback. Một **runbook** phải trả lời các câu hỏi vận hành theo đúng thứ tự hành động:

1. **Tín hiệu kích hoạt là gì?** Cảnh báo 5xx tăng, collector exporter lỗi, log gap, disk watermark, latency tăng?
2. **Ai nhận và chịu trách nhiệm?** On-call của service, platform, database, security hay incident commander?
3. **Cần kiểm tra gì trước?** Scope, thời gian, số lượng request, deployments, metrics, service health, access permission?
4. **Làm sao khoanh vùng sự cố?** Dịch vụ bị lỗi hay chỉ thiếu log? Một tenant, một pod hay cả cụm?
5. **Hành động nào được phép?** Các bước read-only, giảm tác động theo change policy, rollback có phê duyệt.
6. **Khi nào phải dừng và escalation?** Nghi ngờ mất dữ liệu, lỗi bảo mật, dashboard không đáng tin, outage kéo dài?
7. **Khi nào đóng sự cố?** Metrics phục hồi, canary/trace/consumer flow thành công, log pipeline được xác nhận lại, có khoảng theo dõi.
8. **Lưu dấu ở đâu?** Incident ID, timeline, quyết định, người phê duyệt, bằng chứng đã loại dữ liệu nhạy cảm.

**Playbook** thường bao trùm chiến lược xử lý một lớp sự cố, có thể yêu cầu nhiều runbooks. **SOP** có thể quy định thủ tục thường xuyên hoặc bước bắt buộc có kiểm soát. Tên gọi có thể khác nhau trong các tổ chức; quan trọng là tài liệu phải **rõ, đủ hành động và kiểm chứng được**.

## 3. Xác định phạm vi trước khi viết

Runbook mẫu của dự án này dùng những giả định:

| Thuộc tính | Giá trị phòng thực hành | Cần thay bằng gì ở hệ thống thật |
| --- | --- | --- |
| Dịch vụ | `orders-api` Java 17 | Tên workload/resource thực tế |
| Điểm vào | `/orders` | Endpoint và HTTP method tương ứng |
| Trạng thái lỗi | HTTP `503` | Trạng thái/exception theo hợp đồng API |
| Dependency | `inventory` giả lập | Dependency chính xác sau tra cứu kiến trúc |
| Event code | `DEPENDENCY_TIMEOUT`, `REQUEST_FAILED` | Event taxonomy đã được phê duyệt |
| Log transport | JSON Lines từ stdout | stdout/file/OTLP và agent thật |
| Hạ tầng | Có thể triển khai Kubernetes, không bắt buộc | Cluster, namespace, deployment/VM owner |
| Mốc timestamp | UTC, cố định trong lab | UTC runtime thật, có khả năng lệch clock |
| Trace context | `trace_id` trong JSON | W3C Trace Context/OpenTelemetry instrumentation thật |
| Backend query | Cú pháp giả định để giải thích | Query API và schema của backend đang dùng |

Với hệ thống thật, runbook phải có link vào **service catalog**, kiến trúc, dashboards, alert rules, SLO, change history, routing on-call, vault/secrets policy và chính sách truy cập. Bài không bịa các URL nội bộ đó; người triển khai phải liên kết tới tài nguyên đã được xác nhận.

**Định nghĩa phạm vi không xử lý:** Không tự chỉnh database, xóa log, mở quyền truy cập, thay config production hay restart hàng loạt pod trong bài thực hành. Các hành động có thể gây mất dữ liệu/phá bằng chứng chỉ được thực hiện theo quy trình quản lý thay đổi và phân quyền của hệ thống thật.

## 4. Luồng observability cần nắm

~~~text
Client / Gateway
       │
       ▼
orders-api (Java)
   ├─ business request / dependency call
   ├─ Logger facade (JUL / SLF4J / Log4j 2)
   └─ metric + tracing instrumentation
       │
       ▼
Stdout/stderr, file hoặc OTLP exporter
       │
       ▼
Container runtime / node agent / file shipper
       │
       ▼
OpenTelemetry Collector hoặc log gateway
       ├─ parse / enrich / filter / transform
       ├─ batch / queue / retry
       └─ exporter
       │
       ▼
Log backend / index / search API
       │
       ▼
Dashboard / Alert / Investigation
~~~

Mỗi chặng là một **ranh giới xác nhận khác nhau**:

- Logger được gọi **không chứng minh** bản ghi đã đi vào file hay stdout.
- File/stdout xuất hiện **không chứng minh** agent đã đọc.
- Collector nhận event **không chứng minh** exporter gửi thành công.
- Exporter báo gửi thành công **không tự chứng minh** dữ liệu có thể query ở index cuối.
- Một record không tìm thấy trên dashboard **không chứng minh** ứng dụng chưa thực hiện hành động.

Do đó runbook cần luôn phân biệt **sự cố nghiệp vụ** và **sự cố logging pipeline**. Nếu service 503 tăng mà log tạm biến mất, không nên vội kết luận “không có exception”.

## 5. Mẫu cấu trúc chuẩn cho mọi runbook

Một runbook có thể giữ các mục cố định sau:

| Mục | Nội dung bắt buộc |
| --- | --- |
| **Document metadata** | ID, title, owner, reviewers, version, hiệu lực, lần diễn tập gần nhất |
| **Scope/assumptions** | Service/env, dependencies, phiên bản, những điều không bao phủ |
| **Trigger/symptoms** | Alert name, severity, biểu hiện đối với người dùng |
| **Prerequisites** | Quyền read-only, VPN/auth, dashboards, access logging |
| **Safety/guardrails** | Data privacy, change approval, không xóa bằng chứng, rollback requirements |
| **First response** | Xác minh alert, time window, blast radius, customer impact |
| **Diagnosis** | Chuỗi bước/decision tree với expected observations |
| **Mitigation** | Phương án giảm tác động được ủy quyền, người phê duyệt |
| **Recovery** | Điều kiện phục hồi đa tín hiệu, khoảng theo dõi |
| **Escalation** | Khi nào gọi service/platform/security/DB owner |
| **Communication** | Incident updates, scope và thông tin đã được xác minh |
| **Evidence** | Trace/request/event IDs, metric snapshots, logs đã redacted |
| **Post-incident** | Timeline, root-cause hypothesis, action owners, review date |
| **Validation** | Diễn tập, kết quả test, các assumptions cần cập nhật |

Các heading có thể được lưu trong Git hoặc hệ tài liệu nội bộ. Nên có **owner cụ thể theo vai trò/đội nhóm**, tránh runbook “không ai chịu trách nhiệm” hoặc đã lỗi thời sau khi service được chuyển đội.

## 6. Định nghĩa tiêu chí cảnh báo và mức độ nghiêm trọng

Một alert tốt cần phản ánh **tác động có thể quan sát** thay vì chỉ thấy một dòng `ERROR`. Ví dụ giả lập:

| Tín hiệu | Ngưỡng minh họa | Mục đích |
| --- | --- | --- |
| HTTP 5xx ratio cho `orders-api` | Trên 5% trong 5 phút **và** có tối thiểu 100 requests | Phân biệt lỗi thật với traffic quá ít |
| P95 request latency | Vượt SLO trong 10 phút | Xác minh trải nghiệm người dùng |
| Dependency timeout rate | Tăng đáng kể so với baseline | Kiểm tra lỗi tích hợp |
| Readiness failure | Probe liên tục thất bại | Phân biệt instance không sẵn sàng |
| Log ingestion gap | Có traffic nhưng log từ service không tăng trong khoảng quan sát | Phát hiện khả năng quan sát bị mất |
| Exporter queue/deletes | Backlog tăng hoặc failed exports liên tục | Phát hiện pipeline lỗi |

**Các ngưỡng đều là ví dụ**, phải hiệu chỉnh theo SLO, lịch sử tải và cấu hình metrics thực. Tránh biểu thức chỉ dựa trên tỉ lệ khi mẫu quá ít: một request lỗi trên một request tạo 100% 5xx nhưng chưa chắc là incident diện rộng.

Severity ví dụ:

- **SEV1:** phần lớn khách hàng không dùng được dịch vụ cốt lõi, có nguy cơ mất/sai dữ liệu hoặc sự cố bảo mật nghiêm trọng; kích hoạt điều phối sự cố.
- **SEV2:** một phần chức năng trọng yếu suy giảm rõ, ảnh hưởng nhiều người hoặc có khả năng lan rộng.
- **SEV3:** lỗi hạn chế hoặc thiếu một phần telemetry, có workaround trong giới hạn được chấp nhận.

**Sự cố logging pipeline có thể nghiêm trọng** nếu làm mất khả năng phát hiện an ninh hoặc bằng chứng bắt buộc, dù HTTP endpoint vẫn trả 200. Mức độ phải đánh giá theo mục đích và nghĩa vụ của dữ liệu log.

## 7. Trước khi thao tác: safety checklist

Người trực cần:

1. Xác nhận **đúng môi trường**, cluster, account, tenant và service; mọi lệnh ví dụ dưới đây chỉ dành cho phòng lab.
2. Dùng quyền **read-only** cho giai đoạn đầu. Không tự tăng quyền chỉ để xem toàn bộ dữ liệu nhạy cảm.
3. Tạo/ghi **incident ID** trong hệ thống quản lý sự cố trước khi chia sẻ evidence.
4. Ghi lại thời điểm bắt đầu alert, timezone UTC và thời gian truy vấn, tránh nhầm dữ liệu cũ.
5. Không copy toàn bộ production logs vào chat, ticket hoặc dashboard công khai.
6. Không ghi raw passwords, tokens, cookies, HTTP body, thông tin thanh toán, raw SQL binds vào log để “dễ debug”.
7. Không tắt/sửa alert, xóa file, truncate index, flush buffer hoặc restart mù khi chưa biết tác động.
8. Nếu nghi ngờ data breach hoặc sự cố an ninh, thông báo đúng đội security/incident commander và tuân thủ quy trình bảo toàn chứng cứ.
9. Nếu cân nhắc bật DEBUG tạm, đánh giá log volume, retention, dữ liệu nhạy cảm và **thời điểm tắt lại**.
10. Nếu có action thay đổi hệ thống, ghi approver, change scope, rollback criteria và kết quả.

Đừng coi việc tìm được một dòng `SEVERE` là lý do để restart ngay. Một restart có thể xóa in-memory evidence, làm tăng lỗi và che giấu nguyên nhân.

## 8. Quy trình 5 phút đầu khi nhận cảnh báo

**T0 — Alert tới:** Xác nhận tên, ID, nhãn service/environment, observed time, mức độ và trạng thái alert còn active hay không. Kiểm tra alert có liên quan đến production hay staging.

**T+1 — Blast radius:** Xem request rate, success/error ratio, p95/p99 latency, số instance, dependency health và số tenant/region ảnh hưởng. Nếu metric chưa tin cậy, ghi rõ khoảng trống.

**T+2 — Recent changes:** Xem release/deploy gần thời điểm sự cố, config/feature flags, dependency rollout, certificate/token rotation hoặc quota/rate limit. “Có deploy mới” là giả thuyết, **chưa phải kết luận root cause**.

**T+3 — Tìm log theo ID:** Bắt đầu bằng event code, request/trace ID, service, time window và reason code; không phụ thuộc một câu text tự do.

**T+4 — Phân nhánh:** Nếu log nguồn có nhưng backend không có, đi sang runbook pipeline; nếu có `DEPENDENCY_TIMEOUT` và 503, điều tra dependency và error propagation.

**T+5 — Quyết định:** Nếu impact/severity vượt ngưỡng, escalation và mở incident channel; nếu còn giới hạn, tiếp tục triage có thời hạn. Cập nhật điều **đã biết**, điều **chưa biết** và hành động tiếp theo.

Mốc phút là **thứ tự thao tác tham khảo**, không phải SLA hứa hẹn. Trong SEV1 có thể cần gọi điều phối ngay tại T0 thay vì chờ đến cuối.

## 9. Sơ đồ quyết định tổng quát

~~~text
Nhận cảnh báo / báo cáo lỗi
     │
     ├─ Metrics/health xác nhận user impact?
     │         │
     │         ├─ CÓ → Kiểm tra trace/log nghiệp vụ
     │         │          │
     │         │          ├─ Có lỗi dependency / code rõ
     │         │          │   → Khoanh vùng và mitigations được phê duyệt
     │         │          └─ Không có log / log không nhất quán
     │         │              → Điều tra pipeline song song
     │         └─ CHƯA RÕ → Kiểm tra telemetry freshness,
     │                     sampling, query window và canary
     │
     ├─ Log xuất hiện ở nguồn?
     │         ├─ KHÔNG → Level/filter/appender/process/lifecycle
     │         └─ CÓ
     │             └─ Agent nhận?
     │                 ├─ KHÔNG → Path/permissions/CRI/rotation/checkpoint
     │                 └─ CÓ
     │                     └─ Collector xuất?
     │                         ├─ KHÔNG → Processor/drop/queue/exporter
     │                         └─ CÓ → Backend ingest/index/query/RBAC
     │
     └─ Đã giảm impact + xác minh bằng nhiều tín hiệu?
               ├─ KHÔNG → tiếp tục xử lý/escalate
               └─ CÓ → theo dõi, ghi evidence, post-incident
~~~

**Lưu ý:** Log vắng mặt chỉ là một quan sát. Nếu pipeline gặp sự cố, application metrics và traces có thể vẫn còn; cũng có thể **cả ba signal** bị hỏng do shared infrastructure. Runbook cần kiểm tra nguồn độc lập khi có thể.

## 10. Thực hành: yêu cầu đối với lab Java 17

Phòng thực hành dựng một Java class duy nhất tên `LoggingRunbookLab` dùng **JUL**, chạy không cần dependency:

- Chế độ `healthy`: phát `REQUEST_STARTED` và `REQUEST_SUCCEEDED`, HTTP status cuối là 200.
- Chế độ `incident`: phát `REQUEST_STARTED`, `DEPENDENCY_TIMEOUT`, `REQUEST_FAILED` với status 503; sau đó tạo một log `RECOVERY_PROBE_OK` **thuộc request probe độc lập**.
- Mỗi event có timestamp UTC, service, event code, level, trace ID, request ID, route, HTTP status, reason code và message.
- Output là **JSON Lines trên stdout**, một dòng vật lý/một event; mặc định JUL không in bản sao ra stderr.
- Có chuỗi secret giả trong scope code, nhưng không truyền vào Logger.
- Timestamp cố định **chỉ cho test**; không được coi là log production thời gian thực.
- Cố tình **không** có exporter, agent, Collector hay backend thật: bài lab giúp luyện **triage ở nguồn** trước khi nối vào môi trường staging.

Thiết kế này cho phép người trực tập trung vào **đọc dấu hiệu, correlation và ranh giới recovery**, không cần cài đặt Kafka, Docker hay một hệ thống log đắt tiền.

## 11. Chương trình Java 17 chạy độc lập — LoggingRunbookLab.java

Tạo file `LoggingRunbookLab.java` với **toàn bộ** nội dung:

~~~java
import java.time.Instant;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingRunbookLab {
    private static final Logger LOG = Logger.getLogger("lab.orders-api");
    private static final String TRACE = "0123456789abcdef0123456789abcdef";
    private static final String PROBE_TRACE = "fedcba9876543210fedcba9876543210";

    record Event(String eventCode, String traceId, String requestId,
                 String route, int httpStatus, String reasonCode) {}

    static String quote(String text) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            switch (c) {
                case '"': out.append("\\\""); break;
                case '\\': out.append("\\\\"); break;
                case '\n': out.append("\\n"); break;
                case '\r': out.append("\\r"); break;
                case '\t': out.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        out.append("\\u");
                        for (int shift = 12; shift >= 0; shift -= 4) {
                            out.append(Character.forDigit((c >>> shift) & 0xf, 16));
                        }
                    } else {
                        out.append(c);
                    }
            }
        }
        return out.append('"').toString();
    }

    static void stringField(StringBuilder line, String key, String value) {
        if (line.length() > 1) line.append(',');
        line.append(quote(key)).append(':').append(quote(value));
    }

    static final class JsonHandler extends Handler {
        JsonHandler() { setLevel(Level.ALL); }
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) return;
            Object[] args = record.getParameters();
            if (args == null || args.length != 1 || !(args[0] instanceof Event)) {
                throw new IllegalArgumentException("safe Event required");
            }
            Event e = (Event) args[0];
            StringBuilder line = new StringBuilder("{");
            stringField(line, "timestamp", record.getInstant().toString());
            stringField(line, "service", "orders-api");
            stringField(line, "event_code", e.eventCode());
            stringField(line, "level", record.getLevel().getName());
            stringField(line, "trace_id", e.traceId());
            stringField(line, "request_id", e.requestId());
            stringField(line, "route", e.route());
            line.append(",\"http_status\":").append(e.httpStatus());
            stringField(line, "reason_code", e.reasonCode());
            stringField(line, "message", record.getMessage());
            System.out.println(line.append('}'));
        }
        @Override public void flush() { System.out.flush(); }
        @Override public void close() { flush(); }
    }

    static void emit(Level level, String message, Event event, String time) {
        LogRecord r = new LogRecord(level, message);
        r.setInstant(Instant.parse(time));
        r.setLoggerName(LOG.getName());
        r.setParameters(new Object[]{event});
        LOG.log(r);
    }

    public static void main(String[] args) {
        if (args.length != 1 ||
                (!"healthy".equals(args[0]) && !"incident".equals(args[0]))) {
            System.err.println("Usage: java LoggingRunbookLab healthy|incident");
            System.exit(2);
            return;
        }
        Handler out = new JsonHandler();
        boolean oldParent = LOG.getUseParentHandlers();
        Level oldLevel = LOG.getLevel();
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(out);
        try {
            String privateToken = "FAKE_TOKEN_NEVER_LOG";
            if (privateToken.isEmpty()) throw new IllegalStateException();
            emit(Level.INFO, "request received",
                    new Event("REQUEST_STARTED", TRACE, "req-42",
                            "/orders", 0, "NONE"),
                    "2026-11-10T02:00:00Z");
            if ("healthy".equals(args[0])) {
                emit(Level.INFO, "request completed",
                        new Event("REQUEST_SUCCEEDED", TRACE, "req-42",
                                "/orders", 200, "NONE"),
                        "2026-11-10T02:00:01Z");
            } else {
                emit(Level.WARNING, "inventory lookup timed out",
                        new Event("DEPENDENCY_TIMEOUT", TRACE, "req-42",
                                "/orders", 0, "DB_TIMEOUT"),
                        "2026-11-10T02:00:01Z");
                emit(Level.SEVERE, "request failed safely",
                        new Event("REQUEST_FAILED", TRACE, "req-42",
                                "/orders", 503, "UPSTREAM_UNAVAILABLE"),
                        "2026-11-10T02:00:02Z");
                emit(Level.INFO, "independent readiness probe passed",
                        new Event("RECOVERY_PROBE_OK", PROBE_TRACE, "probe-42",
                                "/health/ready", 200, "NONE"),
                        "2026-11-10T02:00:04Z");
            }
        } finally {
            LOG.removeHandler(out);
            LOG.setUseParentHandlers(oldParent);
            LOG.setLevel(oldLevel);
            out.flush();
            out.close();
        }
    }
}
~~~

**Lưu ý kỹ thuật:**

- `JsonHandler` chỉ là collector demo, tạo JSON string thủ công để học; production nên dùng **JSON encoder đã được bảo trì** để xử lý Unicode, surrogate pairs, escaping, schema, errors và throughput.
- `http_status=0` trong sự kiện bắt đầu/timeout là **giá trị sentinel do lab tự quy định cho “chưa có response HTTP”**, không phải mã trạng thái hợp lệ từ HTTP.
- `Level.SEVERE` của JUL được giữ nguyên như `"SEVERE"`. Backend thường map sang ERROR nhưng **không mặc định** đã được mapping; hãy kiểm tra pipeline thật.
- `RECOVERY_PROBE_OK` chỉ báo **một probe độc lập** đã thành công, không chứng minh request `req-42` đã khôi phục hoặc toàn dịch vụ hết lỗi.
- `setUseParentHandlers(false)` tránh JUL root handler ghi trùng vào stderr; `LOG.removeHandler` cùng restore level giúp lab không để lại cấu hình toàn cục nếu chạy cùng JVM khác.
- Secret giả không được đi vào `Event`/message. Giá trị nhạy cảm thực **không bao giờ** nên được dùng làm fixture.

## 12. Biên dịch, chạy và kết quả chính xác

Cần **JDK 17 trở lên** có `javac`, không cần framework bên ngoài.

~~~bash
javac --release 17 LoggingRunbookLab.java
java LoggingRunbookLab healthy
~~~

**Stdout chế độ healthy** (hai dòng JSON Lines, trong thứ tự bên dưới):

~~~json
{"timestamp":"2026-11-10T02:00:00Z","service":"orders-api","event_code":"REQUEST_STARTED","level":"INFO","trace_id":"0123456789abcdef0123456789abcdef","request_id":"req-42","route":"/orders","http_status":0,"reason_code":"NONE","message":"request received"}
{"timestamp":"2026-11-10T02:00:01Z","service":"orders-api","event_code":"REQUEST_SUCCEEDED","level":"INFO","trace_id":"0123456789abcdef0123456789abcdef","request_id":"req-42","route":"/orders","http_status":200,"reason_code":"NONE","message":"request completed"}
~~~

Chạy chế độ sự cố:

~~~bash
java LoggingRunbookLab incident
~~~

**Stdout chế độ incident** (bốn dòng JSON Lines):

~~~json
{"timestamp":"2026-11-10T02:00:00Z","service":"orders-api","event_code":"REQUEST_STARTED","level":"INFO","trace_id":"0123456789abcdef0123456789abcdef","request_id":"req-42","route":"/orders","http_status":0,"reason_code":"NONE","message":"request received"}
{"timestamp":"2026-11-10T02:00:01Z","service":"orders-api","event_code":"DEPENDENCY_TIMEOUT","level":"WARNING","trace_id":"0123456789abcdef0123456789abcdef","request_id":"req-42","route":"/orders","http_status":0,"reason_code":"DB_TIMEOUT","message":"inventory lookup timed out"}
{"timestamp":"2026-11-10T02:00:02Z","service":"orders-api","event_code":"REQUEST_FAILED","level":"SEVERE","trace_id":"0123456789abcdef0123456789abcdef","request_id":"req-42","route":"/orders","http_status":503,"reason_code":"UPSTREAM_UNAVAILABLE","message":"request failed safely"}
{"timestamp":"2026-11-10T02:00:04Z","service":"orders-api","event_code":"RECOVERY_PROBE_OK","level":"INFO","trace_id":"fedcba9876543210fedcba9876543210","request_id":"probe-42","route":"/health/ready","http_status":200,"reason_code":"NONE","message":"independent readiness probe passed"}
~~~

Cả hai chế độ: **stderr trống, exit code 0** khi chạy bình thường. Không có dòng chứa `FAKE_TOKEN_NEVER_LOG`.

**Không dùng các timestamp này làm thời điểm hiện tại khi điều tra.** Trong lab, chúng được **cố định** để kiểm tra đầu ra. Trong một ứng dụng thật, timestamp phải phản ánh event time của log record; query backend cần dùng khoảng thời gian phù hợp với incident.

## 13. Bài thực hành: tạo evidence files cục bộ

Chỉ thao tác trên **thư mục phòng lab**. Các lệnh sau ghi output của chương trình đã biên dịch ra hai file:

~~~bash
java LoggingRunbookLab healthy > healthy.jsonl
java LoggingRunbookLab incident > incident.jsonl
~~~

Ở PowerShell (Windows), nếu shell đang dùng encoding khác, có thể đọc file theo UTF-8 với `Get-Content -Encoding UTF8`. Nội dung demo là ASCII nên hai trường hợp đều dễ đối chiếu; production nên cố định charset UTF-8 tại logger/encoder.

**Ví dụ PowerShell lọc theo request ID:**

~~~powershell
Get-Content .\incident.jsonl -Encoding UTF8 |
    ForEach-Object { $_ | ConvertFrom-Json } |
    Where-Object { $_.request_id -eq 'req-42' } |
    Select-Object timestamp,event_code,level,reason_code,http_status
~~~

**Ví dụ Linux/macOS nếu có `jq`:**

~~~bash
jq -c 'select(.request_id == "req-42")' incident.jsonl
jq -c 'select(.event_code == "REQUEST_FAILED")' incident.jsonl
~~~

Ở chế độ incident, lọc `req-42` phải cho **ba sự kiện**, còn `probe-42` là sự kiện **khác request và trace**. Khi incident giả có 503, xem `reason_code=DB_TIMEOUT` trước khi quyết định lỗi do application code, dependency hay infrastructure.

**Không áp đặt lệnh `jq` lên các bản production chỉ có text logs**. Nếu backend đã parse JSON sang Resource/Attributes/Body theo OpenTelemetry, cú pháp query và vị trí field có thể khác. Dùng schema đúng của sink thực.

## 14. Kịch bản vận hành A — HTTP 503 tăng

Giả định alert về `orders-api` trên staging báo 5xx tăng.

**Bước A1 — Xác nhận tác động:** Kiểm tra request rate, 5xx ratio, p95/p99, route, vùng địa lý, tỷ lệ từng instance và số khách hàng ảnh hưởng. Nếu traffic thấp, đối chiếu số requests tuyệt đối.

**Bước A2 — Chọn cửa sổ:** Lấy khoảng từ trước khi alert bắt đầu đến sau alert, ở UTC. Không mở search không giới hạn khiến kết quả cũ làm nhiễu.

**Bước A3 — Tìm event:** Dùng `service=orders-api AND event_code=REQUEST_FAILED`, kết hợp time window và environment, sau đó mở `request_id` hoặc `trace_id` cụ thể.

**Bước A4 — Dựng timeline:** `REQUEST_STARTED` → `DEPENDENCY_TIMEOUT` → `REQUEST_FAILED` cho request `req-42`. Trong lab, `http_status=503` gắn với sự kiện cuối, còn `reason_code=UPSTREAM_UNAVAILABLE` mô tả cách service phản hồi lỗi.

**Bước A5 — Xác minh dependency:** Kiểm tra các signals của dependency, saturation, connection pool, timeout budget, retry rate và recent changes. **Một chuỗi “inventory lookup timed out” không đủ để xác định database là root cause**; nó là một giả thuyết cần kiểm chứng.

**Bước A6 — Chọn mitigation được phê duyệt:** Có thể giảm tải, giới hạn concurrency, tắt một tính năng phụ, chuyển sang fallback đã thiết kế hoặc rollback release gây lỗi. Không tự tăng timeout/retry vô hạn vì có thể làm tình trạng nghẽn trầm trọng hơn.

**Bước A7 — Đánh giá kết quả:** 5xx ratio và latency trở về ngưỡng chấp nhận, traffic và route quan trọng hoạt động, error rate của dependency giảm, logs/traces tương ứng có mặt. **Probe `RECOVERY_PROBE_OK` không đủ một mình**.

**Bước A8 — Theo dõi và handoff:** Ghi mitigation, thời gian, người phê duyệt, dữ liệu đã kiểm chứng và điều còn bất định. Duy trì theo dõi trong khoảng đã định của on-call policy.

## 15. Kịch bản vận hành B — log biến mất nhưng metrics vẫn tăng

Triệu chứng: traffic `orders-api` vẫn tăng nhưng search API không trả log mới.

**Quy tắc:** Không đánh dấu service healthy chỉ vì không thấy ERROR, và không khẳng định ứng dụng đã ngừng ghi log. Kiểm tra từng hop:

| Hop | Kiểm tra đọc trước | Nếu không đạt |
| --- | --- | --- |
| JVM/logger | Level, filters, logger category, appender lifecycle | Truy code/config/logger hierarchy |
| App sink | stdout/stderr, file path, FileHandler/Logback/Log4j 2 output | Xác định output thật, rotation hoặc disk full |
| Runtime | Container logs, CRI wrapper, truncation/partial events | Kiểm tra node log path/runtime |
| Shipper/agent | Input include path, permission, checkpoint, parser reject | Phối hợp platform/agent owner |
| Collector | Receiver/pipeline active, processors, queue, exporter | Xem internal telemetry/errors |
| Backend | Ingest, index, mapping, tenant, retention, query time | Kiểm tra raw record và access scope |
| UI | Timezone, saved filters, role access | So query trực tiếp với dashboard |

Nếu **stdout có JSONL mới nhưng Collector không thấy**, ưu tiên agent input/permission/CRI parsing thay vì sửa `log.info` trong Java. Nếu Collector debug exporter nhận mà backend query không thấy, ưu tiên exporter/backend/mapping/retention. Cẩn thận: debug exporter chỉ cho biết Collector nhận/đã xử lý ở stage đó, không chứng minh backend đã lưu.

Lúc pipeline mất log và có sự cố nghiệp vụ đồng thời, lập hai track: **phục hồi vận hành dịch vụ** và **phục hồi khả năng quan sát**. Báo cáo rõ thông tin nào chưa thể kết luận vì thiếu telemetry.

## 16. Lệnh kiểm tra Kubernetes chỉ mang tính minh họa

Chỉ thực thi khi đã xác nhận **context/namespace và quyền**. Các tên ở đây đều của phòng lab.

~~~bash
kubectl -n logging-lab get pods -l app=orders-api
kubectl -n logging-lab get deploy orders-api
kubectl -n logging-lab logs deploy/orders-api --since=15m --tail=200 --timestamps=true
kubectl -n logging-lab get events --sort-by=.lastTimestamp
~~~

Giải thích:

- `get pods`: xác định pods đang hoạt động, restart, readiness, số replica và placement; lệnh này không chẩn đoán được mọi root cause.
- `get deploy`: kiểm tra rollout trạng thái, số replica và generation.
- `logs deploy/orders-api`: xem log của một pod mà kubectl chọn theo workload; **không có nghĩa đã lấy hết log của mọi replica**.
- `--since=15m` và `--tail=200` giúp giới hạn output để không kéo quá nhiều dữ liệu nhạy cảm vào terminal/ticket.
- `get events`: xem các hoạt động tại cluster/namespace; event retention cũng có giới hạn.

**Đừng chạy** `kubectl delete pod`, `rollout restart`, `scale` hoặc sửa ConfigMap/Secret chỉ để xem log. Nếu cần mitigation, dùng quy trình change approval và rollback riêng.

Đối với các bản Logback/JUL ghi file trong container, `kubectl logs` có thể **không chứa** nội dung file appender. Cần xác nhận đường thu log của môi trường (sidecar, shared volume, node agent hoặc direct OTLP).

## 17. Correlation: không truy vết chỉ bằng một câu message

Khi sự cố đi qua API gateway, service, queue và consumer, một request có thể phát nhiều logs ở nhiều process. Runbook nên ưu tiên:

- `trace_id` để nối spans/logs theo tracing contract.
- `request_id` để liên kết những sự kiện thuộc cùng HTTP request.
- `message_id` hoặc `event_id` cho logical event và retry.
- `event_code` để lọc sự kiện ổn định không phụ thuộc ngôn ngữ message.
- `service.name`, environment và timestamp để giới hạn phạm vi.
- `reason_code` để phân loại lỗi mà không dump exception message.

Trong lab, `req-42` cùng trace ID chạy qua ba events; `probe-42` có một trace khác. Nếu người trực gom cả bốn events rồi gọi “request req-42 được phục hồi”, đó là **nhầm correlation**.

Một trace có thể bị sampling và không có đầy đủ spans. Việc không tìm thấy trace **không chứng minh** event chưa xảy ra; có thể dựa vào request ID, event ID và metrics khác. Không dùng trace ID làm metric label có cardinality vô hạn.

## 18. Diễn giải severity và lựa chọn tín hiệu

JUL dùng `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`. SLF4J/Logback/Log4j 2 thường dùng ERROR/WARN/INFO/DEBUG/TRACE.

**Quy tắc runbook:**

- Trước khi truy vấn severity=ERROR, xác nhận pipeline có map **JUL SEVERE → ERROR** hay không.
- Một `WARNING` có thể là sự cố cấp cao nếu nó biểu hiện mất dữ liệu; một `SEVERE` không tự là SEV1.
- Không bật TRACE trên toàn hệ thống để tìm một request ID nếu đã có structured INFO/WARN đủ nghĩa.
- Một lỗi có thể sinh nhiều dòng ở controller/service/callback/retry; đếm **logical events/request failures** bằng event code/ID thay vì số dòng chứa `ERROR`.
- Logger level/filter có thể khác nhau giữa JVM và appender, và ở Collector vẫn có processor drop/sampling.

Chỉ đổi level động nếu framework đã hỗ trợ quản trị đúng cách. JUL có `Logger.setLevel`; trong một JVM thật, thay đổi này ảnh hưởng event volume và cần cách revert. Logback/Log4j 2 có API/config quản lý riêng; không giả định một endpoint actuator tồn tại trong mọi Java service.

## 19. Bảo vệ chứng cứ khi nghi ngờ mất dữ liệu hoặc vi phạm an toàn

Nếu một incident có dấu hiệu tác động tới integrity/audit/security:

1. Ghi incident ID, thời gian, môi trường, tài nguyên liên quan.
2. Giữ **ít nhưng đủ** metadata được phép: event IDs, hashes nếu policy yêu cầu, timestamps, error codes, configs đã che secrets và metrics.
3. Không xóa index/file/queue để lấy lại disk khi chưa hỏi chủ sở hữu dữ liệu và người có trách nhiệm.
4. Không copy production logs thô vào email hoặc chat không được phê duyệt.
5. Không vô tình thay đổi tài liệu/bằng chứng bằng thao tác sửa log source.
6. Theo dõi legal hold/retention exception theo quy trình thích hợp.
7. Phân biệt “log không query được” với “bằng chứng thật sự bị xóa”; một backend có thể ẩn theo quyền/time range hoặc còn trong cold tier.
8. Nếu secret đã vào log, phối hợp security để xử lý quyền, bản sao, credential rotation khi cần và điều tra phạm vi.

**Logging vận hành không thay thế audit trail** có yêu cầu bất biến hoặc bảo toàn riêng. Nếu nghiệp vụ cần audit, runbook phải trỏ tới hệ thống lưu giữ phù hợp chứ không dùng stdout làm bằng chứng duy nhất.

## 20. Lỗi log pipeline do backend 429/503, queue và retries

Collector/exporter hoặc shipper có thể gặp:

- `429 Too Many Requests` hoặc throttling do quota.
- `503 Service Unavailable` từ gateway/backend.
- Timeout không rõ downstream đã nhận chưa.
- Queue full/agent buffer pressure.
- Ingest reject do schema/index mapping.
- Authentication/TLS errors.
- Disk full hoặc fail checkpoint.

**Chẩn đoán theo trạng thái:**

| Tín hiệu | Giải thích có thể | Hành động đầu |
| --- | --- | --- |
| Exporter 429 liên tục | Throttling/quota | Đo ingest rate, backoff, pending queue, hợp đồng rate limit |
| Exporter 503 | Backend/gateway unavailable | Kiểm tra health, retry policy và queue deadline |
| Parse errors | JSON/CRI/multiline không đúng schema | Xem sample giả/đã redact và parser config |
| Queue tăng, không export | Downstream chậm hoặc không reachable | Theo dõi backlog, disk/memory, cảnh báo |
| Retry tăng nhưng record trùng | Response ACK có thể bị mất | Dùng event ID khi phù hợp và xác định delivery semantics |
| No data from one pod | Agent path/permission/metadata lỗi | So nguồn local với shipper receiver |
| Query không tìm thấy dù export thành công | Index reject, tenant/time range/mapping | Kiểm tra ingestion và search API |

Không trả lời mọi 429 bằng cách tăng concurrency vô hạn; có thể làm quota càng bị vượt. Không tăng hàng đợi RAM vô hạn để cố “không mất log”: crash có thể làm mất toàn bộ pending records và memory pressure ảnh hưởng ứng dụng.

Với audit bắt buộc, cân nhắc durable recorder/queue độc lập với pipeline log chẩn đoán best-effort.

## 21. Disk pressure, rotation và retention

Khi một node bị đầy disk bởi logs, runbook cần phân biệt:

- **Active file** đang được Java appender ghi.
- **Archive rotated** do Logback/Log4j 2 policy.
- **Container runtime logs** do kubelet quản lý rotation.
- **Agent spool/queue** có thể chứa dữ liệu chưa export.
- **Backend index/object storage** có lifecycle riêng.
- **Snapshots/backups/exports** có thời hạn và hold độc lập.

Hành động read-only ưu tiên đo usage, tuổi archive, số lượng files, tốc độ tăng và pending shipper queue. **Không tự chạy `rm -rf` hoặc `truncate` trên active file**: có thể làm mất chứng cứ, không giải quyết root cause và thậm chí không giải phóng đúng lượng disk với open file descriptors.

**Mitigations được phê duyệt** có thể là giảm DEBUG tạm thời, áp rate limit log không bắt buộc, tăng capacity có kiểm soát hoặc điều chỉnh shipping/rotation. Với audit/security, việc xóa sớm có thể vi phạm policy; hãy escalation đúng owner.

**Retention không chỉ là `maxHistory`.** Logback local archive retention không tự xóa dữ liệu đã index ở backend; backend retention cũng không tự xóa file cục bộ. Khi xem tính toàn vẹn log, cần xét mọi bản sao.

## 22. Khi nào cần escalation?

Runbook phải nêu **trigger cụ thể** và vai trò liên quan, không chỉ ghi “liên hệ người phụ trách”:

| Dấu hiệu | Đội cần tham gia | Hành động của on-call đầu |
| --- | --- | --- |
| 503 tăng ảnh hưởng nhiều khách hàng | Service owner + incident commander | Xác minh impact, thời điểm, request sample |
| Timeout dependency rõ trong nhiều requests | Dependency/DB owner | Gửi reason codes, metrics/timeline an toàn |
| Không có logs ở mọi service/cluster | Platform/observability | Kiểm tra Collector/backend/agent health |
| Logging pipeline rớt audit/security events | Security/compliance + platform | Bảo toàn evidence, xác định severity/hold |
| Disk pressure có nguy cơ dừng workload | Infrastructure owner | Thu metrics, lập mitigation an toàn |
| Suspected token/PII exposure | Security/privacy | Ngừng chia sẻ raw logs, kích hoạt incident process |
| Cần rollback hoặc thay config production | Change approver + service owner | Đưa bằng chứng và rollback plan |
| Các dấu hiệu trái nhau, chưa xác định root cause | Incident lead / SRE | Ghi rõ uncertainty và chia track điều tra |

Thời hạn escalation cụ thể do policy on-call của tổ chức quyết định. **Không bịa số điện thoại, ID phòng chat hoặc SLA nội bộ** trong runbook. Liên kết tới danh bạ/on-call schedule đã được xác minh khi đưa vào production.

## 23. Cách viết bản cập nhật incident có ích

Một bản cập nhật nên phân biệt **facts, hypotheses và actions**:

~~~text
Incident: INC-TEST-042 (phòng thực hành)
Scope: orders-api / staging / route /orders
Observed: 503 tăng trong cửa sổ điều tra; log có
          REQUEST_FAILED reason_code=UPSTREAM_UNAVAILABLE
          và DEPENDENCY_TIMEOUT reason_code=DB_TIMEOUT.
Confirmed: request req-42 thất bại; readiness probe probe-42 độc lập đã thành công.
Unknown: tỷ lệ lỗi trên toàn service đã trở về baseline hay chưa;
         dependency là root cause hay hậu quả của tải cao.
Action: đối chiếu metrics của dependency và release timeline,
        chỉ đánh giá mitigation sau khi có xác minh.
Next update: theo lịch điều phối sự cố được phê duyệt.
~~~

Không viết “database đã chết” chỉ vì một log message nói timeout. Không viết “khôi phục hoàn toàn” chỉ vì một readiness probe trả 200. Nếu thiếu telemetry, nói rõ **sự thiếu hụt** thay vì tự suy ra kết quả.

Bản cập nhật không cần chèn raw payload, session cookie hoặc toàn bộ stack trace. Gửi request/trace ID đủ để người có quyền mở thêm dữ liệu tại hệ thống phù hợp.

## 24. Tiêu chí xác nhận phục hồi — không dựa vào một tín hiệu

Có ít nhất ba lớp:

**A. Service health:** Error rate, latency và throughput trở về ngưỡng phù hợp trên đủ traffic; readiness/liveness ổn định; không còn sự cố đang lan rộng.

**B. Business correctness:** Tác vụ quan trọng trả kết quả đúng, không phát sinh mất/trùng dữ liệu ngoài contract, queue/retry backlog có xử lý, reconciliation nếu có được kiểm chứng.

**C. Observability restored:** Log từ canary/request mới xuất hiện ở nguồn, shipper/Collector và backend search; không có exporter queue đang tăng vô hạn; alert về mất telemetry đã hết theo một khoảng ổn định.

**Không coi các điều sau là đủ:** Một request thành công, một pod READY, một INFO `RECOVERY_PROBE_OK` hoặc việc tạm tắt alert. Thời gian theo dõi sau mitigation phải tính theo SLO và mức độ incident, không chỉ vài giây vì muốn đóng ticket nhanh.

Nếu log pipeline vẫn đang lỗi, có thể cần giữ incident mở hoặc lập follow-up rõ trách nhiệm ngay cả khi HTTP 503 đã giảm.

## 25. Handoff giữa ca trực

Một handoff nên chứa:

- Incident ID, owner hiện tại, mức severity và người nhận ca tiếp.
- Scope service/env/region/tenant, thời gian bắt đầu và các mốc thay đổi.
- Tác động đã xác minh (request errors, availability, backlog, user impact).
- Log query hoặc event IDs an toàn đã sử dụng; **không dán raw log secrets**.
- Những giả thuyết đã loại, giả thuyết còn chờ kiểm chứng.
- Actions đã thực hiện, approvals, kết quả, các config đã thay đổi và cách revert.
- Mitigation đang hoạt động và chỉ số cần theo dõi.
- Rủi ro dữ liệu, legal hold, logging gaps và tình trạng Collector/backend.
- Điều kiện escalation ngay và người chịu trách nhiệm tiếp theo.
- Deadline review/runbook update theo quy trình.

**Chỉ bàn giao khi người nhận xác nhận** nếu quy trình on-call yêu cầu. Một link dashboard không có diễn giải và scope rõ ràng không đủ thay cho handoff.

## 26. Post-incident review và cập nhật runbook

Sau phục hồi, tiến hành review mang tính hệ thống:

1. Timeline theo UTC: alert, first response, triage, mitigations, recovery, closure.
2. Điều gì là **user impact** và phạm vi thực tế.
3. Root cause được hỗ trợ bởi bằng chứng nào; những giả thuyết nào vẫn chưa xác nhận.
4. Vì sao alert có/không phát hiện đúng và mức độ sớm của tín hiệu.
5. Log nào hữu ích, log nào thiếu, thiếu do **ứng dụng** hay **pipeline**.
6. Correlation IDs có giúp nối request/queue/consumer không.
7. Có INFO/DEBUG quá nhiều hoặc exception messages lộ dữ liệu không.
8. Những thao tác giảm tác động có gây tác dụng phụ như restart loop hay retry storm không.
9. Runbook bước nào khiến người đọc hiểu sai hoặc không tìm được quyền/endpoint.
10. Action items có owner, tiêu chí nghiệm thu và hạn review.
11. Cập nhật runbook version, test lại sau khi thay đổi cấu hình.
12. Lưu bài học và hành động phòng ngừa, tránh chỉ đổ lỗi cá nhân.

Một runbook tốt **cần được diễn tập** sau những thay đổi lớn ở architecture, logging backend, cluster hoặc alert rule. Tài liệu chưa từng được chạy thử có thể khiến người trực tự tin sai.

## 27. Bài diễn tập nâng cao: failure injection an toàn

Thực hiện trong **staging hoặc hệ thống mô phỏng**, không phá production:

| Kịch bản | Thao tác lab | Điều cần kiểm tra |
| --- | --- | --- |
| Healthy baseline | Chạy `healthy` | Hai JSON records, có `REQUEST_SUCCEEDED=200` |
| Dependency timeout | Chạy `incident` | `WARNING DEPENDENCY_TIMEOUT` rồi `SEVERE REQUEST_FAILED=503` |
| Correlation | Lọc `req-42` | Có ba events chung trace; probe không nhập chung |
| Secret test | Tìm `FAKE_TOKEN_NEVER_LOG` | Không có trong stdout/event sink |
| Wrong time window | Truy vấn cửa sổ khác timestamp demo | Không thấy record **không đồng nghĩa** record không phát |
| Severity mapping | So JUL `SEVERE/WARNING` và backend | Backend giữ/mapping theo contract |
| Missing logs | Chặn source ở test fixture | Runbook phát hiện telemetry gap nhờ positive control |
| Collector outage | Dùng mock receiver trả 503 | Queue/retry/drop đúng policy, có alert |
| Exporter 429 | Mock throttling | Có backoff và giới hạn queue |
| Duplicate delivery | Mock ACK loss rồi retry | Phân biệt logical event ID và transport attempts |
| Rotation/CRI | Dùng filelog/container fixture | Parser giữ event boundary, không mất/trùng ngoài contract |
| Privacy | Synthetic secret/CRLF trong fixture | Mask/escape tới sink cuối |
| Recovery probe | Chạy probe sau lỗi | Không tự coi probe đơn lẻ là service recovery |
| Handoff | Đổi vai on-call trong lab | Người nhận dựng lại timeline và next steps |

**Acceptance:** Người thực hành phải giải thích được *vì sao* cùng một request có log WARNING rồi SEVERE, vì sao probe không khẳng định recovery và vì sao log không thấy trong backend có thể là do exporter thay vì logger.

## 28. Dự án nâng cấp: thêm Collector và backend thật trong staging

Nếu có Docker/Kubernetes/Collector ở môi trường test, mở rộng:

~~~text
LoggingRunbookLab (hoặc service Java instrumented)
    │ stdout JSONL / file JSONL / OTLP exporter
    ▼
Runtime + agent (nếu đi stdout/file)
    ▼
Collector receiver/processor/exporter
    ▼
Test backend index/search
    ▼
Query theo eventId / requestId / traceId
~~~

**Các bước xác minh:**

1. Xác nhận đúng đường transport: JSONL stdout cần agent/filelog parser; **không gửi raw JSONL vào OTLP receiver** rồi kỳ vọng nó trở thành LogRecord chuẩn.
2. Dùng test event IDs **duy nhất** mỗi lần chạy trong staging; ID cố định của lab chỉ dành cho output minh họa.
3. Kiểm tra mapping: service thường nằm trong Resource, severity nằm đúng field, event code và correlation vào attributes theo schema.
4. Chờ event searchable bằng poll với deadline, không `Thread.sleep` một lần rồi kết luận FAIL.
5. Xác minh đủ event IDs, không chỉ count; xét duplicate do retries.
6. Kiểm tra lỗi parser, receiver refused, exporter failures, queue depth và backend ingest errors.
7. Phát event privacy sentinel giả đã được duyệt và xác minh nó không xuất ở sink cuối, trong error logs của pipeline hoặc backup test.
8. Kiểm tra dashboard/query time range dựa theo event time và ingest time.
9. Thu cleanup logs và ngừng test fixture; không để debug exporter/trace logging bật vô hạn.

Một pipeline được cấu hình ở Collector chưa chắc đã dùng component đó: receiver, processors và exporters phải được nối trong **`service.pipelines.logs`**. Kiểm thử tới backend query mới xác nhận đường cuối, tùy mức đảm bảo của storage.

## 29. Các anti-pattern trong runbook vận hành

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| “Khi lỗi hãy xem log” | Không nói xem ở đâu, tìm theo gì | Có query, event code, scope/time window |
| Chỉ nhìn `ERROR` | Bỏ sót WARN quan trọng hoặc data loss | Kết hợp metrics, event taxonomy, impact |
| Kết luận root cause từ một dòng text | Dễ sai vì timeout chỉ là triệu chứng | Đối chiếu dependency metrics/traces |
| Không phân biệt service và logging pipeline | Không log thì kết luận “không có lỗi” | Triaging hai tracks độc lập |
| Dán toàn bộ logs vào ticket | Rò PII/tokens | Chia sẻ IDs/sanitized evidence |
| Dùng query không có time/env | Kết quả cũ gây nhiễu | Scope rõ, timestamp UTC |
| Coi một probe thành công là phục hồi | Lỗi vẫn có thể đang ảnh hưởng users | Kiểm tra traffic, 5xx, latency và nghiệp vụ |
| Restart mọi pod ngay | Mất state, tăng load hoặc che evidence | Đánh giá mitigation có approval |
| Bật DEBUG không hạn định | Tăng log volume, security risk, disk full | Thời hạn, scope, kế hoạch revert |
| Thay retention/xóa file để lấy disk | Có thể mất audit/evidence | Ownership/hold và cleanup policy |
| Cho rằng HTTP 200 của exporter = index durable | Bỏ qua ranh giới storage | Query và xác minh contract backend |
| Không kiểm tra log collector | Pipeline có thể mất log im lặng | Internal telemetry và canary |
| Hướng dẫn lệnh có namespace/role không rõ | Thực thi nhầm production | Mục scope/context/checklist trước lệnh |
| Không có owner/escalation | Người trực không biết gọi ai | Link service catalog và on-call |
| Copy ngưỡng cảnh báo mẫu vào production | Alert noise hoặc không phát hiện lỗi | Tune theo SLO/baseline |
| Không diễn tập sau cập nhật infra | Runbook lỗi thời | Drill và owner review định kỳ |

## 30. Rubric chấm dự án thực hành

Đánh giá theo bốn nhóm; mỗi nhóm được chấm **đạt/chưa đạt** dựa trên bằng chứng:

**A. Tài liệu vận hành** — Runbook có scope, prerequisites, owner, cảnh báo, severity, safety, triage, mitigation, escalation, recovery, handoff và post-incident.

**B. Thực hành Java 17** — Compile/run `healthy` và `incident`; output JSONL hợp lệ; có hai và bốn records; event codes/HTTP statuses/correlation chính xác; secret giả không xuất.

**C. Phán đoán kỹ thuật** — Nêu rõ ranh giới Logger → stdout → agent → Collector → backend, không nhầm “không thấy log” với “không có lỗi”, không tuyên bố một probe là full recovery, không coi retry của exporter là exactly-once.

**D. An toàn và tính lặp lại** — Không thao tác phá môi trường thật; không dùng credential/PII; biết cách phục hồi cấu hình sau debug; có test evidence và cách cập nhật runbook khi kiến trúc đổi.

**Tiêu chí hoàn thành:** Cả bốn nhóm đạt; các câu hỏi ở mục tiếp theo có câu trả lời dựa trên output và các thao tác cụ thể, không chỉ lý thuyết.

## 31. Câu hỏi tự kiểm tra

1. Tại sao `log.info("done")` không chứng minh backend tìm kiếm đã nhận event?
2. Điều gì khác nhau giữa **runbook** và tài liệu giới thiệu API logging?
3. Ở lab, tại sao `RECOVERY_PROBE_OK` không chứng minh request `req-42` đã thành công?
4. Những field nào giúp lọc một chuỗi log về request thay vì tìm theo chuỗi text tự do?
5. Vì sao không nên đổi mọi `WARNING` thành SEV1?
6. Khi dashboard không có log nhưng request metrics còn tăng, hai nhánh điều tra nào phải chạy?
7. Nếu local stdout có record nhưng backend không, nên kiểm tra những hop nào?
8. Tại sao `kubectl logs deploy/orders-api` không chắc trả logs của mọi replica?
9. Khi Collector báo exporter 429, vì sao tăng retry concurrency vô hạn có thể làm tệ hơn?
10. Vì sao HTTP 200 từ một proxy/Collector không tự chứng minh backend đã durable/index?
11. Tại sao một query “không có log trong 5 phút” có thể sai khi đồng hồ và index lag lệch?
12. Nếu có nghi ngờ token bị ghi vào logs, bước đầu là gì?
13. Có thể dùng chung kênh DEBUG best-effort cho audit cần bảo toàn chứng cứ không?
14. Tại sao runbook phải có ai phê duyệt mitigation/rollback?
15. Khi nào người trực được đánh dấu service recovered?
16. Test lab hai modes có xác nhận Collector/Kubernetes/backend thật đã hoạt động không?
17. Vì sao nên có một test event ID duy nhất mỗi lần chạy staging?
18. Nếu sau mitigation không còn ERROR nhưng 503 vẫn cao, runbook phải kết luận gì?
19. Những thông tin nào cần được bàn giao khi đổi ca?
20. Điều gì chứng minh runbook còn dùng được sau khi thay logging backend hoặc alert rules?

**Đáp án gợi ý:** (1) còn sink, transport, Collector và backend; (2) runbook là quy trình hành động/ra quyết định; (3) probe có request/trace khác và chỉ kiểm tra một endpoint; (4) service, event code, request/trace ID, time, reason; (5) severity cần dựa trên impact; (6) app incident và telemetry incident; (7) runtime/agent/Collector/exporter/backend/query; (8) chọn pod đại diện, không tổng hợp mọi pod; (9) vượt quota, queue và tải tăng; (10) ACK khác indexed/durable state; (11) time window/ingestion delay; (12) không lan truyền raw logs, kích hoạt security process; (13) không nếu yêu cầu bền vững riêng; (14) giảm thao tác gây mất dữ liệu; (15) metrics, nghiệp vụ và observability cùng được xác minh; (16) không, chỉ lab ở nguồn; (17) tránh nhầm event cũ; (18) chưa phục hồi, tiếp tục điều tra; (19) impact, timeline, evidence an toàn, mitigation, owner/next steps; (20) drill có kết quả và review cập nhật.

## 32. Checklist triển khai runbook thật

1. [ ] Title/ID/version, service owner, approver và thời điểm review được xác nhận.
2. [ ] Scope env/region/tenant, dependency graph và link service catalog đúng.
3. [ ] Alert trigger, severity policy, dashboard, SLO/baseline đã được kiểm chứng.
4. [ ] Read-only permissions, account/cluster context, safety guardrails rõ.
5. [ ] Cách xác minh incident bằng metrics/traces trước khi nhìn một dòng log.
6. [ ] Cú pháp query backend theo event code, request/trace ID, time window.
7. [ ] Cách phân biệt logger sink, shipper/agent, Collector và backend/query.
8. [ ] Runbook có lối rẽ cho log missing, parse errors, 429/503, disk pressure.
9. [ ] Có yêu cầu bảo mật khi xử lý PII/token/stack traces và cơ chế escalation.
10. [ ] Mitigation có approvals, rollback plan, limit và kiểm tra tác động.
11. [ ] Recovery criteria gồm user impact, business correctness, telemetry health.
12. [ ] Handoff và incident update tách facts/hypotheses/actions.
13. [ ] Post-incident follow-up có owner, review date và tiêu chí nghiệm thu.
14. [ ] Diễn tập `healthy`/`incident` với Java17, xác minh JSONL/correlation.
15. [ ] Nếu production có Collector/backend, test đường end-to-end trong staging.
16. [ ] Rehearsal sau thay đổi framework/agent/Collector/backend/alert rules.

**Kết luận thực hành:** Một runbook tốt không phải là danh sách lệnh dài. Nó là **chuỗi quyết định có chứng cứ**, giúp người trực biết *khi nào đọc ở đâu, khi nào thay đổi điều gì, khi nào cần giúp đỡ và bằng tiêu chí nào có thể nói đã phục hồi*.

## 33. Nguồn đọc chính thức để kiểm tra và cập nhật runbook

- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): Logger, level, `LogRecord` và handlers.
- [Oracle Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): timestamp, parameters, logger metadata.
- [Oracle Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `publish`, `flush` và lifecycle.
- [Oracle Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): timestamp UTC trong lab.
- [SLF4J — Manual](https://www.slf4j.org/manual.html): facade, levels, parameterized/structured logging.
- [Logback — Manual](https://logback.qos.ch/manual/index.html): appenders, logger hierarchy, configuration.
- [Apache Log4j 2 — Manual](https://logging.apache.org/log4j/2.x/manual/index.html): logging API, configuration, layouts, appenders.
- [Kubernetes — Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/): stdout/stderr, container logs, node agents và retention tại node.
- [Kubernetes — kubectl logs](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/): flags `--since`, `--tail`, pod/deployment log retrieval.
- [OpenTelemetry — Collector Troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/): receivers, processors, exporters, debug, telemetry khi mất log.
- [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/): service pipeline wiring, components, exporter.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): Resource, Body, Severity, Attributes, TraceId/SpanId.
- [Prometheus — Alerting Best Practices](https://prometheus.io/docs/practices/alerting/): alert có tính hành động, có labels/annotations hữu ích.
- [Google SRE Book — Managing Incidents](https://sre.google/sre-book/managing-incidents/): vai trò, cấu trúc điều phối và truyền đạt khi sự cố.
- [Google SRE Workbook — Incident Response](https://sre.google/workbook/incident-response/): thực hành xử lý sự cố và cải tiến quy trình.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): điều nên/không nên log, sanitization, an toàn và truy cập.

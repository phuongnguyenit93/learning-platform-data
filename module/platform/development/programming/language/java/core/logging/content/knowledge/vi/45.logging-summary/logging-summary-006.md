# Bước học tiếp theo sau khi tổng kết Java Core Logging

## 1. Mục tiêu của giai đoạn học tiếp

Sau khi nắm Java Core Logging, người học đã có nền tảng để tạo log, chọn level, truyền exception, hiểu appender/handler, sử dụng MDC và cấu hình nơi xuất. **Bước học tiếp theo** không phải chỉ là học thêm một thư viện logging; cần nâng cấp từ **ghi log trong một class** sang **thiết kế observability giúp điều tra và vận hành một ứng dụng Java thực**.

Một hệ thống có thể có hàng triệu dòng log nhưng vẫn khó xử lý incident nếu:

- Log thiếu `requestId`, `messageId` hoặc `errorCode` để nối các bước.
- Cùng Throwable bị log rồi rethrow ở repository, service và controller.
- Worker thread mất MDC hoặc nhận nhầm context của request trước.
- Log định dạng tự do, collector không thể parse thành field có kiểu.
- File tăng vô hạn, rotation xóa audit quá sớm hoặc exporter bỏ event khi queue đầy.
- Log có secret/PII vì in nguyên request body hay exception message.
- Có trace ID dạng text nhưng không có trace thực để mở từ dashboard.
- Metrics đếm số ERROR logs, dẫn tới một request retry ba lần bị tính thành ba failed requests.

**Đích đến:** tự thiết kế được một pipeline **logging → structured context → metrics/traces → collector/backend → alert/runbook**, xác minh bằng test và biết giới hạn của từng thành phần. Không nhất thiết phải học mọi công cụ cùng lúc; chọn dựa trên nhu cầu và sản phẩm đầu ra.

Bài này cung cấp **thứ tự ưu tiên**, **dự án Java 17 độc lập**, **lộ trình thực hành**, **tiêu chí nghiệm thu** và **tài nguyên chính thức**. Những lịch học bên dưới chỉ là gợi ý; không phải thời hạn bắt buộc hay chuẩn chứng nhận.

## 2. Tự đánh giá nền tảng trước khi đi tiếp

Thử giải thích và chứng minh các mục dưới đây với một dự án mẫu:

| Năng lực | Câu hỏi kiểm tra | Bằng chứng thực hành |
| --- | --- | --- |
| JUL | `Logger`, `Handler`, `Formatter`, `LogRecord` có vai trò nào? | Chạy được logger với handler tùy biến |
| SLF4J | Façade/API khác provider/backend thế nào? | Dependency tree chỉ có tuyến provider chủ định |
| Level | Khi nào dùng INFO, WARN, ERROR? | Validation bình thường không in ERROR stack vô ích |
| Throwable | Tại sao log-and-rethrow có thể nhân bản lỗi? | Terminal failure chỉ có một owner log rõ |
| Structured fields | `errorCode` khác exception class, status, message thế nào? | Output có schema và kiểu nhất quán |
| Context | `requestId`, `correlationId`, `traceId`, `messageId` khác gì? | Tìm được các event đúng request/message |
| MDC | Vì sao thread pool có thể lẫn ID? | Test A → B → no-context trên một worker |
| Retention | Rolling khác audit retention thế nào? | Test giới hạn archives không xóa audit sai |
| Reliability | Làm sao biết log đã drop hoặc export lỗi? | Metrics và alert tại sink/pipeline |
| Privacy | Vì sao không in raw headers/payload? | Test marker secret giả không xuất log |
| Tracing | MDC có tự tạo span không? | Trace liên kết với log khi span được export |

Nếu chưa trả lời một mục, hãy làm một mini-exercise cho mục đó **trước khi thêm nhiều công nghệ**. Đừng dùng việc thuộc tên OpenTelemetry hoặc Prometheus thay cho hiểu luồng của một event từ code tới backend.

### Thang phát triển năng lực gợi ý

- **Mức 1 — logging đúng:** chọn level, API, Throwable, không lộ secret và không log thừa.
- **Mức 2 — log có cấu trúc:** có `event`, `errorCode`, ID tương quan, typed fields, MDC không rò.
- **Mức 3 — pipeline đáng tin:** cấu hình appender, rotation, collector, retention, cảnh báo mất log.
- **Mức 4 — observability tích hợp:** logs, metrics, traces nối nhau, có dashboard, SLO và runbook.
- **Mức 5 — năng lực production:** thực hành incident drill, debugging async/microservices, privacy và cost.

Đây là một **khung học tập do bài học đề xuất**, không phải cấp độ chính thức của Java hoặc OpenTelemetry.

## 3. Lộ trình ưu tiên và các nhánh chuyên sâu

~~~text
Nền tảng Java Core Logging
          |
          v
[1] Chuẩn hóa Logger/API/Backend + Exception ownership
          |
          v
[2] Structured events + Error code + Schema
          |
          v
[3] MDC + Request context + Async propagation
          |
          +-----------------------+
          |                       |
          v                       v
[4A] Reliability pipeline    [4B] Metrics nền tảng
     rolling, collector           rate, errors, latency
     queue, retention             saturation
          |                       |
          +-----------+-----------+
                      |
                      v
[5] OpenTelemetry + Distributed tracing
    trace/span context, OTLP, Resource
                      |
                      v
[6] Dashboard, alerts, SLO, incident response
                      |
                      v
[7] Capstone hoặc specialization
    Backend / Messaging / Platform / Security
~~~

**Chặng 4A và 4B có thể học song song.** Một ứng dụng single-process vẫn cần logging có cấu trúc và disk/retention phù hợp. Một microservice có nhiều downstream calls hưởng lợi lớn từ tracing. Một hệ thống audit có chính sách lưu giữ nghiêm ngặt nên giải quyết durability/retention trước khi bật sampling để giảm chi phí.

### Quyết định chủ đề học tiếp theo vấn đề thực

| Nếu bạn gặp tình huống | Chủ đề cần ưu tiên | Kết quả có thể đo |
| --- | --- | --- |
| Mỗi developer log một kiểu | SLF4J, một provider, quy ước level và event | Không có provider/appender trùng |
| Không tìm được log cùng request | Structured logging + MDC | Tìm log bằng requestId, không lẫn task |
| Worker mất requestId | Context propagation qua ExecutorService | Test A/B/no-context |
| Cùng stack trace in ba lần | Exception ownership và log-and-rethrow | Một terminal failure record |
| Log làm đầy ổ hoặc mất khi restart | Rotation, retention, stdout/container pipeline | Có time-to-reserve và drop alert |
| Tắc nghẽn chỉ thấy trên production | Metrics: rate/errors/latency/saturation | Dashboard và SLO rõ đơn vị |
| Request đi qua nhiều services | Distributed tracing, W3C context | Log gắn span thật |
| Kafka/RabbitMQ xử lý lặp | Message ID, retry, DLQ, idempotency | Log phân biệt attempts |
| Dữ liệu log nhạy cảm | Redaction, RBAC, audit | Privacy test ở mọi sink |

## 4. Chặng 1: chuẩn hóa API logging và nơi ghi lỗi

**JUL** thuộc JDK và cung cấp `Logger`/`Handler`/`Formatter`. **SLF4J** là façade/API cho ứng dụng và thư viện; **Logback** hoặc một provider phù hợp mới thực sự định dạng và chuyển event ra sink. **Log4j 2** có API/core riêng và các bridge thích hợp tùy môi trường.

Bài thực hành quan trọng:

1. Tạo một dự án nhỏ dùng JUL, ghi một INFO event và một WARNING event có Throwable.
2. Chuyển cùng logic sang SLF4J 2.x với một backend được chọn, ví dụ Logback; không thêm nhiều SLF4J providers vô ý.
3. Ghi `event`/`requestId`/`errorCode` theo quy ước, không đưa raw exception message thành error code.
4. Cấu hình một appender console; nếu thêm file appender, xác minh một LogEvent chỉ đi tới mỗi sink đã chủ định một lần.
5. Dùng test handler/capturing appender để đếm số event ở sink, không chỉ kiểm tra lời gọi mock logger.

Ví dụ **SLF4J snippet** (cần dependency phù hợp, không phải file Java độc lập):

~~~java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

void report(String safeOrderRef, long durationMs) {
    LOG.info("event=order_processed orderRef={} durationMs={}",
            safeOrderRef, durationMs);
}
~~~

`OrderService` và các biến do ứng dụng định nghĩa. Parameterized logging giúp backend xử lý format, nhưng **không tự sanitize secret** và không tự biến các placeholder thành typed JSON fields.

Trong SLF4J 2.x có API fluent:

~~~java
LOG.atInfo()
   .addKeyValue("event", "order_processed")
   .addKeyValue("orderRef", safeOrderRef)
   .addKeyValue("durationMs", durationMs)
   .log("Order processed");
~~~

Encoder/layout thực tế phải hỗ trợ key–value nếu muốn export JSON. Không có fluent API này trong SLF4J 1.7. Tránh tính object lớn hay serialize JSON khi DEBUG bị tắt; dùng level checks/lazy computation khi cần.

**Đầu ra chặng 1:** một trang logging conventions ghi chuẩn level, error boundary, context fields, approved provider, appender routes và policy xử lý Throwable.

## 5. Chặng 2: structured logging và contract của event

Trong log text:

~~~text
INFO order done
WARN payment failed
~~~

người vận hành khó tổng hợp theo request và loại lỗi. Một event có cấu trúc cung cấp từng trường:

~~~json
{
  "timestamp": "2026-11-10T08:00:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event": "payment_failed",
  "errorCode": "PAY_TIMEOUT",
  "requestId": "req-A",
  "attempt": 2,
  "outcome": "failure",
  "durationMs": 47
}
~~~

JSON này chỉ **minh họa schema ứng dụng**, không phải output tự động của SLF4J/Logback hay một OpenTelemetry LogRecord nguyên gốc. `durationMs` là **number**, không phải chuỗi `"47ms"`. `event` và `errorCode` là những tập giá trị hữu hạn giúp nhóm/chạy alert, còn `requestId` là định danh động phục vụ truy vấn từng request.

Quy tắc thiết kế schema:

- **Event name ổn định:** `request_received`, `operation_succeeded`, `operation_failed`, `retry_scheduled`, `message_dead_lettered`. Không ghép userId, filename hoặc timestamp vào tên event.
- **Error code có taxonomy:** phân biệt validation, business conflict, dependency timeout, unexpected bug; không dùng `exception.getMessage()` hoặc class name thô làm public API code.
- **Tách field theo vai trò:** Resource/service metadata; context của request/trace/message; attributes riêng của event.
- **Kiểu dữ liệu nhất quán:** duration numeric, attempt integer, success boolean nếu dùng; thay đổi kiểu/tên cần migration plan.
- **Không ghi body/headers nguyên vẹn:** có thể lộ PII, cookie, token, SQL và dữ liệu bí mật.
- **Giới hạn input:** validate ID, escape newline/control characters, chọn encoder hỗ trợ JSON escaping.
- **Test thực tế:** assert nội dung sau encoder/appender và sau collector, không chỉ kiểm tra object trong code.

**Đầu ra chặng 2:** structured output có thể parse, catalog ít nhất năm event hữu ích, hai loại lỗi và một integration test schema.

## 6. Chặng 3: MDC và context propagation

MDC (**Mapped Diagnostic Context**) giữ key–value gắn với thread xử lý, ví dụ `requestId`/`tenantRef`. Logging backend có thể lấy chúng từ MDC và thêm vào nhiều event. Nhưng `MDC.put(...)` trên web thread **không tự chuyển giá trị sang worker thread**, càng không tự truyền qua HTTP hoặc message broker.

Một **snippet SLF4J** quản lý scope:

~~~java
import java.util.Map;
import org.slf4j.MDC;

Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("requestId", verifiedRequestId);
    businessOperation();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
~~~

Đây không phải chương trình standalone: `verifiedRequestId` và `businessOperation()` do ứng dụng định nghĩa. ID phải được generate/validate ở boundary; không tin `X-Tenant-Id` do người dùng gửi là chứng cứ quyền tenant.

**Bài test bắt buộc:** dùng một `ExecutorService` có một worker tái sử dụng, xử lý A rồi B rồi một task không thuộc request:

~~~text
task A -> requestId=req-A
task B -> requestId=req-B
task không request -> requestId=none
~~~

Không được có log B mang ID A. Wrapper cần **capture** MDC khi submit, **set/restore** tại worker và dọn trong `finally`. Nếu framework đã tích hợp tracing context, đừng gọi `MDC.clear()` ở layer tùy ý làm mất key do agent khác sở hữu; cần hiểu ownership của scope.

**Đầu ra chặng 3:** middleware/context wrapper có test cleanup khi exception, task propagation và absence of leaked context.

## 7. Chặng 4: exception, retry và ownership khi log

Một lỗi ở repository đi qua service rồi HTTP handler vẫn có thể là **một failure nghiệp vụ**. Nếu mọi catch đều `LOG.error(..., ex)` rồi `throw ex`, dashboard có thể đếm ba ERROR, chi phí I/O tăng và stack trace được sao chép nhiều lần.

Hướng thiết kế:

1. Domain/repository **giữ Throwable cause** và chuyển exception có nghĩa khi cần.
2. Tầng service có thể thực hiện fallback/retry, nhưng không in lại cùng stack chỉ vì rethrow.
3. Boundary HTTP/message/job quyết định outcome cuối cùng và log failure với `errorCode`/`requestId`/`outcome` tại một vị trí rõ.
4. Retry attempt và retry scheduled là **mốc thật**, có thể log riêng với attempt và reason, nhưng không coi chúng là ba terminal failures.
5. Metrics đếm **số operation cuối thất bại**, không đơn thuần số ERROR logs.
6. Với Kafka/RabbitMQ, `messageId` có thể giữ qua redelivery, còn delivery metadata/attempt đổi; việc biết message ID **không thay thế idempotency**.

Ví dụ:

~~~text
event=payment_attempt_failed requestId=req-B attempt=1 errorCode=PAY_TIMEOUT
event=retry_scheduled requestId=req-B attempt=1 delayMs=200
event=checkout_failed requestId=req-B attempt=2 outcome=failure errorCode=PAY_TIMEOUT
~~~

Có ba events nhưng chỉ một terminal checkout failure. Khi chuyển exception, đừng mất cause bằng `new DomainException("failed", null)` rồi log text không có nguyên nhân; giữ cause trong sink nội bộ có quyền.

## 8. Mini-capstone Java 17: log event và đo outcome đúng đơn vị

Trước khi tích hợp thư viện ngoài, dùng một bài chạy **chỉ với JDK 17** để hiểu đường đi của LogRecord, sự kiện riêng cho retry và terminal failure. Đoạn sau chứa toàn bộ class, có tên tệp và output xác định. Nó **không thực hiện HTTP, không đo latency thật, không có exporter metrics và không tạo distributed trace**.

Tạo file **`LoggingNextStepsDemo.java`**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingNextStepsDemo {
    record Event(
            String event, String requestId,
            String outcome, String errorCode, long durationMs) {}

    private static final Logger LOG =
            Logger.getLogger("learning.next.steps");

    private static final class CompactHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            Object[] params = record.getParameters();
            if (params == null || params.length != 1
                    || !(params[0] instanceof Event e)) {
                return;
            }
            System.out.println(
                    "level=" + record.getLevel().getName()
                    + " event=" + e.event()
                    + " requestId=" + e.requestId()
                    + " outcome=" + e.outcome()
                    + " errorCode=" +
                        (e.errorCode() == null ? "none" : e.errorCode())
                    + " durationMs=" + e.durationMs()
                    + " hasCause=" + (record.getThrown() != null));
        }

        @Override
        public void flush() {
            // Không có bộ đệm I/O riêng.
        }

        @Override
        public void close() {
            // Không có tài nguyên ngoài.
        }
    }

    private static void emit(
            Level level, Event event, Throwable thrown) {
        LogRecord record = new LogRecord(level, event.event());
        record.setParameters(new Object[] { event });
        record.setLoggerName(LOG.getName());
        record.setThrown(thrown);
        LOG.log(record);
    }

    public static void main(String[] args) {
        Level oldLevel = LOG.getLevel();
        boolean oldParent = LOG.getUseParentHandlers();

        CompactHandler handler = new CompactHandler();
        handler.setLevel(Level.ALL);
        LOG.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(handler);

        int operations = 0;
        int failures = 0;

        try {
            operations++;
            emit(Level.INFO,
                    new Event(
                            "order_processed", "req-A",
                            "success", null, 12),
                    null);

            operations++;
            IllegalStateException cause =
                    new IllegalStateException(
                            "simulated upstream timeout");

            emit(Level.WARNING,
                    new Event(
                            "payment_retry_scheduled", "req-B",
                            "retry", "PAY_TIMEOUT", 40),
                    cause);

            emit(Level.SEVERE,
                    new Event(
                            "checkout_failed", "req-B",
                            "failure", "PAY_TIMEOUT", 45),
                    cause);
            failures++;

            System.out.println(
                    "operations=" + operations
                    + " failures=" + failures);
        } finally {
            LOG.removeHandler(handler);
            LOG.setUseParentHandlers(oldParent);
            LOG.setLevel(oldLevel);
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LoggingNextStepsDemo.java
java LoggingNextStepsDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
level=INFO event=order_processed requestId=req-A outcome=success errorCode=none durationMs=12 hasCause=false
level=WARNING event=payment_retry_scheduled requestId=req-B outcome=retry errorCode=PAY_TIMEOUT durationMs=40 hasCause=true
level=SEVERE event=checkout_failed requestId=req-B outcome=failure errorCode=PAY_TIMEOUT durationMs=45 hasCause=true
operations=2 failures=1
~~~

Logic tương đương đã được chạy bằng JShell dùng API có mặt từ Java 17, cho đúng bốn dòng. Chưa biên dịch tệp trên bằng `javac --release 17` trong phiên kiểm tra, nên người học cần xác minh lại bằng lệnh đã ghi.

### Giải thích code

- `Event` là Java record chứa các thuộc tính riêng cho một log. `LogRecord.setParameters` được handler tùy biến đọc theo **hợp đồng riêng của demo**; JUL logger/OTel exporter mặc định **không tự** biến record này thành JSON Attributes.
- `requestId=req-A` hoàn tất thành công với `hasCause=false`. Request B có một mốc retry và một terminal failure, cả hai giữ `errorCode=PAY_TIMEOUT` nhưng `outcome` khác nhau.
- `durationMs` là các **số cố định minh họa**, không lấy từ đồng hồ đo. Khi triển khai thật, dùng `System.nanoTime()` tính elapsed duration thay vì lấy chênh wall-clock.
- `operations=2 failures=1` thể hiện đếm operation/outcome, không đếm số LogRecord hay stack frames. Những biến local không phải Prometheus/OpenTelemetry metrics.
- `LogRecord.setThrown(cause)` giữ một nguyên nhân để sink nội bộ được phép ghi chẩn đoán. Demo chỉ in `hasCause` để stdout ổn định; không có nghĩa production nên bỏ stack trace ở mọi nơi.
- `LOG.setUseParentHandlers(false)` ngăn parent JUL console handler in thêm event. Đây là xử lý đường đi của log, **không phải** giải pháp cho code log-and-rethrow.
- Chương trình không tạo retry thật, không dùng network hoặc side effect. Không dùng `errorCode` làm idempotency key.

### Bài mở rộng với demo

1. Thêm event started/succeeded/failed, dùng event schema và typed fields thay vì ghép chuỗi.
2. Di chuyển sang SLF4J + Logback với structured JSON encoder, kiểm tra output bằng test appender.
3. Thêm requestId qua MDC và thực hiện trong thread pool với wrapper capture/restore.
4. Tạo một Throwable khác và kiểm tra một failure chỉ được log ở boundary.
5. Thay biến counter trong `main` bằng một metrics SDK thực theo stack đang dùng.
6. Thêm tracing instrumentation, lấy trace ID từ active span và liên kết log với trace đã export.

## 9. Chặng 5: học metrics để đo xu hướng

**Logs trả lời “điều gì đã xảy ra ở một lần xử lý cụ thể?”** Metrics trả lời “xảy ra bao nhiêu, tỷ lệ thế nào, có bất thường không?”. Khi học metrics, chú trọng **đơn vị đo đúng**:

- Request/operation rate: số operations trên một đơn vị thời gian.
- Terminal error rate: số operation cuối thất bại / tổng operations.
- Duration distribution: histogram latency để ước lượng percentile phù hợp.
- Saturation: thread pool queue, heap/GC, CPU, connection pool, disk.
- Logging pipeline health: drops, write errors, exporter retry, queue backlog.
- Business outcomes: payment succeeded/failed, message processed/DLQ theo schema.

Có thể tìm hiểu **Micrometer** khi dùng Spring hoặc **OpenTelemetry Metrics SDK** tùy kiến trúc. Không bắt buộc dùng cả hai cho cùng instrument nếu gây duplicate telemetry.

Ví dụ dạng Prometheus text **minh họa** (không do code ở mục 8 xuất):

~~~text
operations_total{operation="checkout",outcome="success"} 1200
operations_total{operation="checkout",outcome="failure"} 12
~~~

Chỉ dùng các nhãn hữu hạn như `operation`/`outcome`/`service`/`route template`/`errorCode` catalog. Không đưa `requestId`, `messageId`, `userId`, exception message, URL chứa số ID thành metric labels; cardinality có thể tăng theo số request làm bộ nhớ và chi phí bùng nổ.

**Thực hành:** thêm counter và duration histogram vào capstone; tạo dashboard error rate/latency; mô phỏng một operation retry hai lần rồi thành công để xác minh **terminal failure counter không tăng sai**.

## 10. Chặng 6: distributed tracing và OpenTelemetry

Khi request đi qua HTTP service A → message broker → service B, chỉ có log riêng từng service khó thấy đường đi và thời gian chờ. **Distributed tracing** mô hình hóa hoạt động bằng traces/spans. **OpenTelemetry** cung cấp API/SDK, instrumentation, semantic conventions và context propagation để kết nối telemetry.

| Trường | Ý nghĩa | Không nên nhầm với |
| --- | --- | --- |
| `traceId` | Định danh toàn trace có quan hệ nhân quả | requestId của API hoặc idempotency key |
| `spanId` | Một span thực thi trong trace | Toàn bộ request/business workflow |
| `requestId` | ID theo hợp đồng request của app | Span parent hoặc W3C traceparent |
| `messageId` | Một message logic | Kafka offset hoặc RabbitMQ deliveryTag |
| `correlationId` | Liên kết các bước workflow | Mặc định bằng traceId |
| `errorCode` | Loại lỗi ổn định | Một error occurrence duy nhất |

**MDC không tự tạo trace.** Một chuỗi đặt thủ công vào `MDC.put("traceId", "...")` không chứng minh có span được export. Hãy lấy trace context từ active span của instrumentation; khi qua process boundary, dùng propagator hỗ trợ chuẩn như W3C `traceparent`.

Tài liệu OpenTelemetry Java khuyến nghị người mới **bắt đầu với Java agent** khi framework có instrumentation sẵn, sau đó bổ sung manual spans cho thao tác nghiệp vụ cần quan sát. Bản agent/SDK thực, các module và khả năng auto-instrument phụ thuộc phiên bản/dependency; không copy một câu lệnh `-javaagent` với path không tồn tại rồi tuyên bố tracing đã bật.

### Ba tín hiệu bổ trợ nhau

~~~text
Alert: latency tăng và error rate tăng
       |
       v
Metrics: operation checkout nào chậm?
       |
       v
Trace: span nào chiếm thời gian, downstream nào lỗi?
       |
       v
Logs: event/errorCode/requestId/cause của span đó?
       |
       v
Runbook: sửa nguyên nhân, xác minh số liệu phục hồi
~~~

Trace sampling có thể khiến log có traceId nhưng **không có span tương ứng trên backend**; export failure cũng có thể gây thiếu. Không tuyên bố mọi log có traceId đều click mở được trace. Audit cần retention/durability riêng, không thể thay bằng traces đã sample.

### Logs sang OpenTelemetry bằng hai cách

1. **Logback/Log4j appender bridge → OTel Log SDK → OTLP → Collector → backend**.
2. **Structured stdout/file → shipper/agent → collector parse/map → backend**.

Mỗi cách có trade-off về queue, overhead và durability. Tránh thu **cùng một event** qua cả hai đường rồi ingest vào cùng index không có provenance/dedup. Trong OpenTelemetry Log Data Model, metadata nguồn thuộc **Resource**, event-specific fields thuộc **Attributes**, còn `TraceId`/`SpanId` là những trường chuyên dụng, không chỉ là hai đoạn text tự đặt.

**Thực hành:** một HTTP request tạo active span, gọi downstream stub, mở trace từ dashboard và tìm log đúng traceId khi span được sampled/export thành công.

## 11. Chặng 7: collector, rotation, retention và vận hành

Một pipeline logging có thể có nhiều tầng:

~~~text
Java logger
  |
  v
Appender / Formatter / Encoder
  |
  +--> file (rotation + retention)
  |         hoặc stdout/stderr
  v
Container runtime / shipper
  |
  v
Collector receiver
  |
  v
Processors: enrich / redact / filter / schema
  |
  v
Exporter queue, retry, transport
  |
  v
Storage, index, archive, dashboards
~~~

Trong OpenTelemetry Collector, receiver nhận data, processors transform/filter data, exporter gửi ra nơi lưu. **Chỉ khai báo một processor trong config không kích hoạt nó**; phải đưa processor vào `service.pipelines.logs.processors`. Thứ tự processor và nguồn dữ liệu ảnh hưởng kết quả, đặc biệt khi thêm/trộn resource fields và redaction.

Những điểm cần học/tự kiểm tra:

- **Disk capacity:** free bytes, inode, tốc độ tăng log, time-to-reserve, log file active/archives.
- **Rotation:** với Logback, `maxFileSize` không giới hạn cả filesystem; `maxHistory`/`totalSizeCap` chủ yếu quản lý archives theo policy, không thay SRE alert.
- **Container:** stdout vẫn có thể chiếm host/ephemeral storage; cần hiểu Docker logging driver và Kubernetes eviction.
- **Async appender:** queue có thể block/drop khi đầy; crash trước flush có thể làm mất buffered events.
- **Collector:** backlog, exporter errors, retries, duplicate ingestion và missing metrics.
- **Retention:** application DEBUG log có thể có thời hạn ngắn; audit/security logs có policy và legal hold riêng.
- **Billing:** bytes sinh tại app, bytes đã ingest và stored/indexed bytes không nhất thiết bằng nhau.
- **Alerting:** phải biết khi exporter down/missing metrics, không coi không có data là không có lỗi.

**Thực hành:** dùng môi trường test riêng với volume nhỏ hoặc collector cố ý tạm dừng, quan sát queue/drops và recovery. Không thử làm đầy disk production, xóa log Docker-managed hoặc truncate active audit files để “đo giới hạn”.

## 12. Security và privacy không phải phần tùy chọn

Logging hiệu quả vẫn có thể gây rủi ro nếu lưu nhầm thông tin. Khi nâng cấp sang structured logging, hãy thực hiện:

- **Data minimization:** không ghi password, token, JWT, cookie, OTP, private key, connection strings hoặc full Authorization headers.
- **Input validation:** giới hạn độ dài/ký tự của requestId và fields do client ảnh hưởng; tránh newline/control characters gây log injection.
- **Public vs internal error:** response API dùng error code và message an toàn; stack trace chi tiết chỉ tại sink nội bộ có quyền.
- **Tenant isolation:** MDC `tenantRef` phục vụ correlation, **không tự bảo đảm authorization**; cần kiểm tra principal và phân quyền truy vấn ở backend.
- **RBAC/retention:** ai được xem raw logs, lưu bao lâu, audit truy cập và backup theo chính sách.
- **Audit riêng:** actor/action/outcome/time, integrity, retention và legal hold nếu có nghĩa vụ, không trộn với DEBUG rotation.
- **Testing:** đặt token/PII marker giả vào input thử nghiệm rồi kiểm tra mọi sink, không chỉ console.

Không dùng một phép hash đơn giản để tuyên bố ID đã “ẩn danh” nếu có thể brute-force hoặc liên kết theo thời gian. Chỉ thu thập ID cần thiết, cân nhắc pseudonymization đúng threat model.

## 13. Dự án capstone: Order API quan sát được

Một capstone vừa đủ để củng cố các chặng trên:

**Ứng dụng mẫu:** một Order HTTP API, một Payment stub có timeout, một notification worker chạy qua ExecutorService; sử dụng SLF4J/Logback hoặc backend tương đương, metrics, tracing và một pipeline log. Không nhất thiết phải dựng nhiều microservices thật.

~~~text
Client -> HTTP Filter / Authentication
                   |
                   +--> requestId, tenantRef, trace extract
                   |
                   v
             OrderService
                   |
                   +--> PaymentAdapter (simulated timeout)
                   |
                   +--> Async Notification Worker
                   |          |
                   |          +--> MDC/trace context propagation
                   v
        Outcome event + errorCode
                   |
             +-----+-----+
             |     |     |
             v     v     v
           Logs  Metrics Traces
             |     |     |
             +-----+-----+
                   |
                   v
              Collector / Backend
                   |
                   v
             Alert + Dashboard + Runbook
~~~

### Tiêu chí nghiệm thu capstone

| Hạng mục | Kết quả có thể chứng minh |
| --- | --- |
| Logging backend | Một provider chủ định, không có duplicate appender |
| Event taxonomy | `event`/`errorCode`/`outcome` rõ và ổn định |
| Context | Một requestId có ở controller, service và worker khi thích hợp |
| Context cleanup | Request A → B → no-context không bị rò MDC |
| Structured logging | JSON fields và kiểu duration/attempt chính xác tại sink |
| Exception | Một terminal failure không bị log-and-rethrow ở nhiều lớp |
| Retry | Attempts có mốc riêng, metric terminal failures đếm đúng |
| Real tracing | Trace/span ID lấy từ instrumentation; mở được span khi export |
| Metrics | Rate, terminal error rate, duration, collector drops |
| Reliability | Có alert queue/exporter/disk và hành vi khi sink lỗi |
| Security | Không lộ secret marker giả trong các sink không được phép |
| Retention | Audit không bị xóa bởi config rotation của DEBUG log |
| Troubleshooting | Từ alert tìm được log, trace, root cause, runbook |
| Documentation | README hướng dẫn chạy, test, cấu hình, giới hạn và cleanup |

Đừng cố dựng Kafka/Kubernetes/Grafana cùng lúc chỉ để bài tập “đủ công nghệ”. Làm một pipeline nhỏ **có thể kiểm chứng** rồi tăng độ khó theo vấn đề cần giải.

## 14. Kế hoạch thực hành bốn tuần (gợi ý)

| Tuần | Nội dung | Bài thực hành | Bàn giao |
| --- | --- | --- | --- |
| **1** | API/provider, level, exception, structured event | Chuyển project sang một logger backend; typed fields | Logging conventions và test appender |
| **2** | MDC, async, privacy | A/B/no-context trong thread pool; redaction test | Helper propagation + test cleanup |
| **3** | Metrics + distributed tracing | Instrument HTTP/service/worker; dashboard lỗi/latency | Metrics/trace liên kết với log |
| **4** | Pipeline + production | Collector, rotation, queue failure, incident drill | Demo end-to-end và runbook |

Đây chỉ là lịch tham khảo: nếu dự án đang xử lý dữ liệu nhạy cảm, **privacy và retention phải được đưa vào ngay từ tuần đầu**, không để sang cuối. Một người có ít thời gian có thể làm mỗi chặng thành một bài tập 1–2 buổi; tiêu chí là đã **chạy/test** chứ không phải đã đọc tài liệu.

**Quy trình làm việc học hiệu quả:** đặt một giả thuyết (“requestId bị mất tại worker”), tạo test tái hiện, sửa đúng boundary, kiểm chứng output và ghi bài học vào README. Tránh thay đồng thời appender, collector và code khi chưa xác định nơi đầu tiên log biến mất.

## 15. Chọn hướng chuyên sâu tiếp theo

Sau capstone, chọn theo nghề nghiệp và hệ thống:

### Backend Java / Spring

Tập trung servlet filters, exception handling (`@ControllerAdvice`), Spring Boot logging config, structured output, metrics và tracing integration. **Sản phẩm:** request thất bại trả public error an toàn, operator có thể dùng ID truy ngược log và trace.

### Messaging / distributed systems

Tìm hiểu Kafka `topic/partition/offset`, RabbitMQ `message_id`/delivery tag, at-least-once delivery, retry/DLQ, transactional outbox và idempotent consumers. **Sản phẩm:** redelivery không gây side effect sai, logs phân biệt message logic và delivery attempts.

### SRE / platform

Tập trung Docker logs, Kubernetes ephemeral storage, collector, Prometheus/Grafana, SLO/error budget, capacity và incident response. **Sản phẩm:** alert khi logs bị drop/disk sắp đầy, khôi phục pipeline trong môi trường thử nghiệm.

### Security / compliance

Tập trung audit schema, tamper detection, immutable storage/WORM nếu có yêu cầu, RBAC, retention/legal hold, log injection và privacy. **Sản phẩm:** audit event bảo toàn mà không in secret ra diagnostic logs.

### Performance / JVM

Tìm hiểu JFR, GC logs, heap/thread profiling, benchmark encoder/async appender, queue backpressure và tail latency. **Sản phẩm:** đo overhead với cùng workload thay vì khẳng định logger async luôn nhanh.

Không cần trở thành chuyên gia mọi nhánh. Học đủ để nhận biết ranh giới và chọn một chuyên sâu theo mục tiêu dự án.

## 16. Các hiểu lầm cần tránh

| Hiểu lầm | Sự thật cần nhớ |
| --- | --- |
| “Có nhiều log chắc chắn debug nhanh hơn” | Event đúng + context đúng + pipeline đáng tin mới quan trọng |
| “SLF4J là backend lưu file” | SLF4J là API/façade, cần provider phù hợp |
| “MDC tự đi theo mọi thread và message” | Cần capture/restore và context propagation theo boundary |
| “Có traceId trong text là có trace” | Cần active span, propagation và exporter |
| “OpenTelemetry thay SLF4J/Logback” | OTel có bridge/collector, thường bổ sung logging hiện có |
| “JSON không thể lộ token” | Structured log chỉ khiến dữ liệu dễ parse hơn; vẫn cần minimization |
| “Một exception phải log ở mọi catch” | Log-and-rethrow có thể gây nhiều stack traces cho một failure |
| “Số ERROR logs là error rate” | Retry và duplicates làm đếm sai; metrics theo terminal outcome |
| “Logback rotation thay audit retention” | Audit có policy và nghĩa vụ lưu giữ riêng |
| “Async logger đảm bảo không mất log” | Queue/shutdown/network failure có thể dẫn tới drop |
| “Một sự kiện ở stdout và OTLP là hai events” | Có thể là cùng nguồn được ingest qua hai đường |
| “RequestId thích hợp làm Prometheus label” | ID động có cardinality cao; chỉ để query log/trace |
| “Unit test logger mock đủ kiểm chứng” | Phải test tại backend/collector sink thật |

## 17. Bộ câu hỏi tự đánh giá cuối bài

1. Có thể mô tả đường đi của một JUL LogRecord từ Logger qua Handler đến console và so với SLF4J/Logback không?
2. Một Throwable được log ở repository và controller: làm sao phân biệt anti-pattern với một event retry có ý nghĩa khác?
3. Vì sao `errorCode` không được dùng làm unique event ID hoặc idempotency key?
4. Nếu người dùng gửi `X-Tenant-Id` tùy ý, có nên đưa trực tiếp vào MDC và dùng để phân quyền truy vấn logs không?
5. Khi hai request nối tiếp trên một worker, test gì chứng minh MDC không rò?
6. Khi enable SLF4J 2.x `addKeyValue`, phải kiểm tra gì để JSON backend thực sự có fields?
7. Metric nào đếm **failed operations cuối cùng** chính xác hơn số stack traces?
8. Một log có traceId nhưng backend không tìm thấy trace: những khả năng nào cần kiểm tra?
9. Khi collector bị down, bạn kiểm tra queue/drops/exporter errors ở đâu?
10. Vì sao `maxHistory`/`totalSizeCap` không bảo đảm mọi audit event được giữ đúng hạn?
11. Khi Docker/Kubernetes lưu stdout logs, liệu không dùng FileAppender đồng nghĩa không chiếm disk không?
12. Làm sao chứng minh một token giả không lọt vào console, file, shipper và backend?

Có thể dùng câu trả lời làm **checklist nghiệm thu** thay vì học thuộc. Ví dụ câu 6: cần test encoder/provider/layout thật; câu 8: sampling, export, propagation và ID giả đều là khả năng cần xét; câu 7: operation outcome metric được định nghĩa theo đúng boundary.

## 18. Checklist hành động sau bài tổng kết

- [ ] Có một project Java 17 cho thấy log event, Throwable và một terminal outcome đúng đơn vị.
- [ ] Có tài liệu logging conventions với API/backend, level, error code và owner của exception.
- [ ] Có structured fields, kiểu dữ liệu ổn định, schema migration plan.
- [ ] Có MDC request scope, finally cleanup và propagation test A/B/no-context.
- [ ] Không có log-and-rethrow dư thừa hoặc duplicate ingest không chủ ý.
- [ ] Có metrics về rate, errors, latency, saturation và logging pipeline health.
- [ ] Có trace context thực, không tự chế trace ID, và thử mở log liên kết với span.
- [ ] Có rotation, collector, alert disk/queue/drop và retention theo đúng loại log.
- [ ] Có data minimization, redaction, RBAC và privacy test.
- [ ] Có một capstone chạy được, README hướng dẫn, incident drill và runbook.
- [ ] Đã chọn nhánh chuyên sâu tiếp theo dựa trên khoảng trống và công việc thật.

**Kết luận:** Sau khi tổng kết Java Core Logging, **bước học tiếp theo** là chuyển kiến thức về logger, MDC và exception thành một **hệ thống quan sát được, có bảo mật, có metrics/traces và được kiểm thử trong tình huống lỗi**. Tiến từng chặng và giữ minh chứng từ chương trình chạy, tests và dashboard quan trọng hơn việc thêm nhiều thư viện cùng lúc.

### Tài liệu tham khảo chính thức

- Oracle Java SE 17 — [java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html), [LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html), [Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html).
- SLF4J — [Manual: parameterized logging, fluent API và MDC](https://www.slf4j.org/manual.html).
- Logback — [Architecture](https://logback.qos.ch/manual/architecture.html), [Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html), [Rolling Appendices](https://logback.qos.ch/manual/appenders-rolling.html).
- Log4j 2 — [Manual](https://logging.apache.org/log4j/2.x/manual/index.html), [Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html).
- OpenTelemetry — [Java Instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/), [Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/), [Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/), [Collector Configuration](https://opentelemetry.io/docs/collector/configuration/).
- Prometheus — [Overview](https://prometheus.io/docs/introduction/overview/), [Instrumentation best practices](https://prometheus.io/docs/practices/instrumentation/).
- Micrometer — [Documentation](https://docs.micrometer.io/micrometer/reference/).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html).
- Docker — [Logging drivers](https://docs.docker.com/engine/logging/configure/); Kubernetes — [Local ephemeral storage](https://kubernetes.io/docs/concepts/storage/ephemeral-storage/).

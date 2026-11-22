# Log enrichment trong Java Core Logging và Observability

## 1. Log enrichment là gì?

**Log enrichment** (làm giàu log) là quá trình bổ sung **metadata có ngữ nghĩa và cấu trúc** vào một sự kiện log để người đọc hoặc hệ thống quan sát có thể xác định **sự kiện gì**, **xảy ra ở đâu**, **thuộc request/trace nào**, **ảnh hưởng đối tượng nào** và **kết quả ra sao** — mà không cần đoán từ một chuỗi message tự do.

Ví dụ trước enrichment:

~~~text
INFO Order saved
ERROR Payment timeout
~~~

Sau enrichment, vẫn cùng loại thông điệp nhưng có thể điều tra và tổng hợp:

~~~json
{
  "timestamp": "2026-11-10T03:00:00Z",
  "severity": "ERROR",
  "service.name": "checkout",
  "service.version": "1.0.0",
  "deployment.environment.name": "production",
  "event": "payment_failed",
  "errorCode": "PAY-TIMEOUT",
  "requestId": "req-42",
  "traceId": "4f0e2c13b69a497389d74e71a52b4e62",
  "spanId": "00f067aa0ba902b7",
  "orderRef": "ord-demo-7",
  "outcome": "failed"
}
~~~

Đây là **JSON minh họa**, không phải một payload OpenTelemetry LogRecord gốc hay đầu ra mặc định của JUL. Việc đặt tên trường ở ví dụ giúp giải thích ý nghĩa; khi triển khai OpenTelemetry cần ánh xạ đúng vào `Resource`, `Attributes` và các trường chuyên dụng `TraceId`/`SpanId` của data model.

Enrichment khác với chỉ **viết message dài hơn**. Message có thể dành cho con người; các trường riêng cho phép lọc, nhóm, liên kết và kiểm thử schema. Cũng khác với việc **thu toàn bộ context**: metadata thừa, sai hoặc nhạy cảm làm tăng chi phí, rủi ro và nhiễu. Giá trị enrichment đến từ **đúng trường, đúng nguồn, đúng vòng đời**.

### Mục tiêu vận hành

- Truy từ `requestId` đến những log cùng một request trong nhiều lớp của một service.
- Truy từ `traceId`/`spanId` đến traces, latency và đoạn xử lý liên quan.
- Phân biệt log của các phiên bản và môi trường khi nhiều deployment chạy đồng thời.
- Nhóm lỗi theo `event`, `errorCode`, `outcome`, `dependency` mà không parse message.
- Chỉ ra một log từ worker/job/message nào, hoặc tenant nào **sau khi đã xác thực ngữ cảnh**.
- Tăng giá trị của tìm kiếm/alert mà không biến mọi trường thành metric label có cardinality cao.

Một request có thể phát nhiều log, một trace có thể chứa nhiều service và span, và cùng một event có thể xuất ở nhiều sink. Enrichment giúp **nối chúng đúng phạm vi**, nhưng không tự giải quyết duplicate logs, distributed tracing, audit trail hoặc idempotency của nghiệp vụ.

## 2. Ba lớp thông tin nên phân biệt

Một schema rõ ràng phân loại metadata theo **mức ổn định và nguồn phát**.

| Lớp | Trường mẫu | Vòng đời | Nguồn đáng tin cậy |
| --- | --- | --- | --- |
| **Resource / nguồn phát** | `service.name`, `service.version`, `deployment.environment.name`, `service.instance.id` | Tương đối ổn định trong một instance/deployment | Cấu hình deploy, SDK, orchestrator hoặc collector có kiểm chứng |
| **Ngữ cảnh xử lý** | `requestId`, `traceId`, `spanId`, `correlationId`, `tenantRef`, `messageId` | Request, span, message hoặc job | Middleware, tracing SDK, envelope đã validate |
| **Thuộc tính sự kiện** | `event`, `errorCode`, `outcome`, `attempt`, `durationMs`, `orderRef` | Riêng cho từng log event | Logic nghiệp vụ tại thời điểm phát event |

Ví dụ cùng một service `checkout` có thể xử lý hàng nghìn request, nên `service.name` thường không cần được tính lại trong mỗi method. `requestId` đổi theo request; `event=order_completed` và `durationMs=34` chỉ có nghĩa với bản ghi hoàn thành order.

### Trong mô hình OpenTelemetry Logs

OpenTelemetry phân biệt:

- **`Timestamp`:** thời điểm sự kiện xảy ra, khác `ObservedTimestamp` là lúc hệ thống thu thập quan sát được.
- **`SeverityText`/`SeverityNumber`:** mức log; không phải error code.
- **`Body`:** nội dung sự kiện, có thể là string hoặc giá trị cấu trúc theo exporter.
- **`Resource`:** metadata mô tả nguồn telemetry, ví dụ service và môi trường.
- **`Attributes`:** metadata của riêng log record; phù hợp `orderRef`, `errorCode`, `outcome`.
- **`TraceId` và `SpanId`:** các trường chuyên dụng để liên kết trace; không chỉ là hai key trong text.
- **`InstrumentationScope`:** thông tin thành phần instrumentation phát tín hiệu.
- **`EventName`:** tên loại event có cấu trúc khi tín hiệu được biểu diễn theo mô hình event.

Đây là mô hình đích; **không nên tự động gộp mọi trường vào một Map rồi gọi đó là OpenTelemetry**. Nếu chỉ xuất JSON từ Logback và collector parse, cần biết adapter ánh xạ field nào vào từng phần của OTel LogRecord. Nếu dùng OpenTelemetry SDK/bridge, hãy xem phiên bản và exporter thực tế có ánh xạ cấu trúc như mong muốn không.

**Không giả định** `Timestamp` của nguồn và `ObservedTimestamp` của collector giống nhau. Chênh lệch có thể gợi ý buffer/queue, clock drift hoặc transport delay; cần clock synchronization và quy ước chính xác trước khi đo latency.

## 3. Chọn schema có tính nhất quán

Một schema hữu ích không cần hàng trăm trường. Bắt đầu từ **nhóm giá trị cốt lõi** và khai báo contract cụ thể:

| Field | Loại nên dùng | Ý nghĩa | Lưu ý |
| --- | --- | --- | --- |
| `event` / `event.name` | string hữu hạn | Loại sự kiện: `order_received`, `order_processed` | Đừng gắn requestId vào tên event |
| `service.name` | string hữu hạn | Tên service logic | Giống nhau giữa các replica cùng service |
| `service.version` | string | Version binary/deploy | Không nhầm với phiên bản schema sự kiện |
| `deployment.environment.name` | string hữu hạn | `development`/`staging`/`production`... | Thuộc Resource trong OTel |
| `service.instance.id` | string | Instance phát sự kiện | Có thể có cardinality cao; không làm label metric tùy tiện |
| `requestId` | string đã validate | Correlation request | Không phải traceId hay userId |
| `traceId`, `spanId` | định dạng W3C khi thực sự traced | Liên kết trace/span | Không bịa để lấp trường trống |
| `messageId` | string theo contract message | Thông điệp logic | Giữ qua redelivery nếu là cùng message |
| `tenantRef` | string đã kiểm tra/ẩn phù hợp | Phân vùng theo tenant | Không coi giá trị này là authorization |
| `errorCode` | enum/string hữu hạn | Loại lỗi ổn định | Không dùng raw Throwable message |
| `durationMs` | số không âm | Khoảng thời gian xử lý | Lưu number, không ghép `"34ms"` nếu schema yêu cầu số |
| `attempt` | integer | Lần thử xử lý | Tách khỏi message ID và error code |
| `outcome` | string hữu hạn | `success`, `failure`, `cancelled`... | Khác log level |
| `orderRef` | string an toàn | Tham chiếu nghiệp vụ phục vụ debug | Chỉ giữ khi chính sách cho phép |

Nếu có semantic convention chính thức đã phù hợp với tín hiệu, **ưu tiên tên và kiểu của convention đó** hơn tên tự đặt. Các tên như `requestId` và `orderRef` trong ví dụ là trường **tùy biến của ứng dụng**, không tuyên bố chúng là thuộc tính chuẩn OpenTelemetry. Đừng dùng tên chuẩn nhưng đổi semantics riêng: sự nhất quán giữa các service quan trọng hơn đẹp từng dòng log.

### Schema version và nguồn sự thật

Khi muốn đổi `durationMs` thành `duration_ms` hoặc đổi chuỗi số thành numeric, đó có thể là **breaking change cho collector/query/dashboard**. Nên định nghĩa:

1. Tên field, kiểu dữ liệu, nguồn, ràng buộc, giá trị khi thiếu.
2. Trường nào bắt buộc ở event nào; không ép `errorCode` có mặt trên event thành công.
3. Schema version hoặc migration plan cho log pipeline khi thay đổi không tương thích.
4. Mức độ tin cậy: trường do application xác minh, collector xác định, hay client truyền lên.
5. Cách xung đột khi hai tầng cùng điền field: không âm thầm overwrite giá trị đã xác thực bằng header chưa xác thực.

Một chuẩn hóa sơ sài như đổi mọi thiếu giá trị thành `"unknown"` có thể trộn nhiều loại sự kiện. Cần phân biệt **missing do không áp dụng**, **missing do lỗi propagation** và **unknown do không xác thực được** trong giám sát chất lượng.

## 4. Enrich ở tầng nào?

~~~text
Business code
   |
   +-- event attributes: event, outcome, errorCode, orderRef
   |
   v
Request/message middleware
   |
   +-- scoped context: requestId, tenantRef, correlationId
   |
   v
Logging API/backend
   |
   +-- MDC / key-value pairs + encoder/layout
   |
   v
SDK/agent/collector
   |
   +-- resource: service/version/environment/pod metadata
   +-- validate/transform/redact according to schema
   |
   v
Log storage / index / dashboard
~~~

**Không có một tầng phù hợp cho mọi field.** Một số gợi ý:

- **Tại điểm xảy ra sự kiện:** ghi event name, error code, outcome, duration và ID nghiệp vụ an toàn. Collector thường không thể suy chính xác một thanh toán thất bại từ câu text tự do.
- **Tại request middleware:** tạo/kiểm tra requestId, lấy principal/tenant từ xác thực, thiết lập scope và dọn khi kết thúc. Không tin hoàn toàn `X-Request-Id` hoặc `X-Tenant-Id` do client tự khai.
- **Tại tracing instrumentation:** lấy trace/span context thực từ SDK/agent đang chạy. Truyền trace context qua các ranh giới async và network theo thư viện hỗ trợ.
- **Tại cấu hình deploy/OpenTelemetry resource:** xác định service name, version, environment và instance. Nếu field không có trong app, collector có thể bổ sung từ nguồn đáng tin như Kubernetes metadata.
- **Tại collector:** có thể thêm/đổi/xóa field, chuẩn hóa schema và thực thi redaction bổ sung, nhưng **không thể sửa thông tin gốc không tồn tại**. Log đã lộ secret ra stdout/file trước collector vẫn là một sự cố bảo mật ở nguồn.
- **Tại backend:** index/search/quản lý retention và quyền truy cập; đây không phải nơi tạo ra danh tính hoặc business truth của một event.

### Xung đột giá trị

Nếu ứng dụng ghi `service.name=checkout` nhưng collector tự đặt `service.name=payments`, sự kiện có thể bị gán nhầm cho dashboard/runbook. Nếu header client nói `tenantId=B` nhưng authenticated principal chỉ có quyền tenant A, không cho header quyết định partition của log. Cần thiết kế **nguồn sự thật và ưu tiên rõ**, fail closed cho field dùng cách ly dữ liệu, kèm alert khi phát hiện conflict.

**Enrichment phải có tính lặp lại có kiểm soát (idempotent)**: nếu collector retry hoặc đi qua cùng một processor hai lần, không tạo hai mảng field trùng tên, nối chuỗi lặp hoặc đánh mất value hợp lệ. Dùng chính sách insert/update/upsert có chủ đích, test cả dữ liệu đã có field.

## 5. Ví dụ Java 17 độc lập: gắn metadata cho event và truyền qua thread pool

Ví dụ sau dùng **chỉ Java 17**, không phụ thuộc OpenTelemetry, SLF4J hay Logback. Nó minh họa ba ý tưởng:

- Resource cố định trong ví dụ (`service`, `environment`, `version`).
- Context cho request (`requestId`, `traceId`, `spanId`) được quản lý theo scope.
- Event riêng (`event`, `orderRef`, `outcome`) được chụp theo log record và truyền qua một `java.util.logging.Handler` tùy biến.

**Quan trọng:** `java.util.logging.LogRecord` không có API MDC/attribute map chuẩn tương ứng trực tiếp với OpenTelemetry. Để độc lập với thư viện ngoài, demo đặt một `EventData` bất biến vào `LogRecord.parameters` và handler do bài học định nghĩa đọc nó. Đây là **hợp đồng riêng của ví dụ**, không phải quy ước tất cả JUL Formatter hoặc exporter tự hiểu.

Tạo file **`LogEnrichmentDemo.java`**:

~~~java
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogEnrichmentDemo {
    // Context của lần xử lý; chỉ tồn tại trên thread hiện tại.
    record Context(String requestId, String traceId, String spanId) {}

    // Snapshot dữ liệu trên từng event, không dựa vào thread writer.
    record EventData(
            String service, String environment, String version,
            String requestId, String traceId, String spanId,
            String event, String orderRef, String outcome) {}

    private static final Logger LOG =
            Logger.getLogger("demo.enrichment");
    private static final ThreadLocal<Context> CURRENT =
            new ThreadLocal<>();

    // Scope đúng cả khi lời gọi lồng nhau hoặc ném exception.
    private static <T> T within(Context next, Supplier<T> work) {
        Context before = CURRENT.get();
        try {
            if (next == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(next);
            }
            return work.get();
        } finally {
            if (before == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(before);
            }
        }
    }

    // Chụp context ở lúc submit, khôi phục tại worker.
    private static Runnable capture(Runnable task) {
        Context snapshot = CURRENT.get();
        return () -> within(snapshot, () -> {
            task.run();
            return null;
        });
    }

    private static void emit(
            String event, String orderRef, String outcome) {

        Context ctx = Objects.requireNonNull(
                CURRENT.get(), "context missing");

        EventData data = new EventData(
                "checkout", "development", "1.0.0",
                ctx.requestId(), ctx.traceId(), ctx.spanId(),
                event, orderRef, outcome);

        LogRecord record = new LogRecord(Level.INFO, event);
        record.setLoggerName(LOG.getName());

        // Contract riêng của demo JUL: EventData trong parameters.
        record.setParameters(new Object[] { data });
        LOG.log(record);
    }

    private static final class StructuredHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }

            Object[] params = record.getParameters();
            if (params == null || params.length != 1
                    || !(params[0] instanceof EventData e)) {
                return;
            }

            // Dữ liệu demo đã được kiểm soát; production cần encoder
            // cấu trúc, escape/control-character handling và redaction.
            System.out.println(
                    "service=" + e.service()
                    + " env=" + e.environment()
                    + " version=" + e.version()
                    + " event=" + e.event()
                    + " requestId=" + e.requestId()
                    + " traceId=" + e.traceId()
                    + " spanId=" + e.spanId()
                    + " orderRef=" + e.orderRef()
                    + " outcome=" + e.outcome());
        }

        @Override
        public void flush() {
            // Không có bộ đệm I/O.
        }

        @Override
        public void close() {
            // Không có tài nguyên ngoài cần đóng.
        }
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        StructuredHandler handler = new StructuredHandler();
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<?> first = within(
                    new Context(
                            "req-A",
                            "11111111111111111111111111111111",
                            "aaaaaaaaaaaaaaaa"),
                    () -> {
                        emit("order_received", "ord-7", "accepted");
                        return pool.submit(capture(() ->
                                emit("order_processed", "ord-7",
                                        "success")));
                    });
            first.get();

            // Cùng worker được tái sử dụng, nhưng context phải là B.
            Future<?> second = within(
                    new Context(
                            "req-B",
                            "22222222222222222222222222222222",
                            "bbbbbbbbbbbbbbbb"),
                    () -> pool.submit(capture(() ->
                            emit("order_processed", "ord-8",
                                    "success"))));
            second.get();
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
            LOG.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 LogEnrichmentDemo.java
java LogEnrichmentDemo
~~~

**Stdout xác định**, vì chương trình `get()` từng `Future` trước khi xử lý request kế tiếp và custom handler không thêm timestamp:

~~~text
service=checkout env=development version=1.0.0 event=order_received requestId=req-A traceId=11111111111111111111111111111111 spanId=aaaaaaaaaaaaaaaa orderRef=ord-7 outcome=accepted
service=checkout env=development version=1.0.0 event=order_processed requestId=req-A traceId=11111111111111111111111111111111 spanId=aaaaaaaaaaaaaaaa orderRef=ord-7 outcome=success
service=checkout env=development version=1.0.0 event=order_processed requestId=req-B traceId=22222222222222222222222222222222 spanId=bbbbbbbbbbbbbbbb orderRef=ord-8 outcome=success
~~~

Ý nghĩa của ví dụ:

1. `EventData` là Java `record` bất biến; các field được **đóng gói vào sự kiện khi phát log**. Handler đọc chính event, không đọc `ThreadLocal` hiện tại của thread ghi log.
2. `within(...)` ghi lại `Context before`, đặt context mới rồi khôi phục trong `finally`. Nó hỗ trợ nested scopes và không làm mất scope caller. Không có scope cần được diễn đạt rõ, demo chọn ném exception thay vì âm thầm log một requestId giả.
3. `capture(...)` đọc snapshot trên **thread gửi task**. Worker thread pool nhận snapshot và dọn/khôi phục sau khi chạy. Request B không bị gắn requestId của A dù cùng một worker.
4. `traceId`/`spanId` ở ví dụ là **giá trị giả do bài học đưa vào**, không được OpenTelemetry sinh, không chứng minh có span thực. Trong production, lấy chúng từ context của tracing SDK đang active và không tự gán string do client khai.
5. `setParameters(...)` là cách demo vận chuyển metadata tới `StructuredHandler`. JUL formatter chuẩn có thể coi `parameters` là tham số cho message format, **không tự chuyển EventData thành OTel attributes**. Cần bridge/formatter/handler phù hợp nếu muốn gửi sang hệ thống thực.
6. Demo in các cặp `key=value` đã biết trước, **không có JSON escaping/sanitization cho input tùy ý**; không đưa vào sản phẩm khi field do client điều khiển. Trong production, dùng structured encoder, kiểm soát schema, sanitize và redaction.
7. `get()` đợi task hoàn tất trước bước tiếp theo, nên thứ tự stdout được xác định. Trong hệ thống đa luồng không nên assert thứ tự giữa các request độc lập.
8. `pool.shutdown()` chỉ dành cho vòng đời của demo. Server thường sở hữu executor dùng chung và không shutdown mỗi request; đặt scope/cleanup theo boundary ứng dụng.

### Vì sao ví dụ không dùng SLF4J?

Mục tiêu là người học chỉ cần JDK 17 có thể chạy và kiểm tra logic enrichment. SLF4J/Logback, Log4j 2 và OpenTelemetry giúp triển khai thực tế tốt hơn nhưng phải có dependency và backend. Không nên nhầm ThreadLocal tự viết với MDC của SLF4J hay propagation chính thức của tracing SDK.

## 6. SLF4J 2.x: event key–value pairs và MDC khác nhau thế nào?

SLF4J có hai cơ chế thường gặp:

- **MDC (`Mapped Diagnostic Context`):** map key–value gắn với thread hiện tại, phù hợp requestId/tenantRef/correlationId dùng chung trong nhiều lời gọi log cùng scope.
- **Fluent logging API (SLF4J 2.x):** `atInfo()`/`atError()`, `addKeyValue(...)`, `setCause(...)`, rồi `log(...)` để gắn thuộc tính **riêng cho một sự kiện**.

Ví dụ **snippet** cho ứng dụng có SLF4J 2.x và backend tương thích; `LOG`, `orderRef`, `durationMs` và `outcome` do ứng dụng định nghĩa:

~~~java
LOG.atInfo()
   .addKeyValue("event", "order_processed")
   .addKeyValue("orderRef", orderRef)
   .addKeyValue("durationMs", durationMs)
   .addKeyValue("outcome", outcome)
   .log("Order processed");
~~~

Cần **kết thúc bằng `log()`**; nếu chỉ gọi `addKeyValue` mà quên `log()` thì không có event phát ra. Fluent API của SLF4J 2.x không có ở SLF4J 1.7. Việc API chứa key–value pairs **không tự bảo đảm** formatter đang dùng xuất JSON hoặc in các pairs: phải cấu hình backend/encoder hỗ trợ rồi integration test log thật.

Ví dụ gắn request scope:

~~~java
// Snippet trong class/middleware có org.slf4j.MDC.
import java.util.Map;
import org.slf4j.MDC;

Map<String, String> before = MDC.getCopyOfContextMap();
try {
    MDC.put("requestId", verifiedRequestId);
    MDC.put("correlationId", correlationId);
    businessOperation();
} finally {
    if (before == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(before);
    }
}
~~~

`verifiedRequestId` và `correlationId` phải được validate và không chứa secret. `businessOperation()` là code thực của ứng dụng. `MDC.getCopyOfContextMap()` giúp giữ context của caller nếu đang ở lời gọi lồng nhau; `finally` ngăn request B bị dính metadata A trên server thread pool tái sử dụng.

**Không gắn `errorCode` vào MDC của cả request rồi quên remove**, vì một lỗi đã được xử lý ở đầu request có thể khiến log thành công phía sau vẫn mang code lỗi. `errorCode`, `durationMs` và `outcome` thường phù hợp hơn làm **event attributes** qua fluent API.

### Logback pattern hiển thị MDC

Ví dụ cấu hình **`logback.xml`** tối giản (cần Logback Classic trên classpath):

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level service=checkout req=%X{requestId} corr=%X{correlationId} %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

`%X{requestId}` và `%X{correlationId}` **chỉ hiển thị** field hiện có trong MDC; chúng không tự tạo field. Phần `service=checkout` là hằng trong pattern của ví dụ; production nên đưa service/environment vào Resource/metadata cấu hình deployment để nhất quán nhiều appender. Pattern text không chuyển các key–value fluent tự động thành structured JSON. Nếu cần JSON, chọn encoder hỗ trợ structured fields và kiểm thử output thực tế. Đừng suy ra mọi backend/phiên bản Logback có encoder JSON giống nhau.

### Log4j 2 ThreadContext

Với Log4j 2, cơ chế tương đương MDC là `ThreadContext`. Ví dụ snippet dùng Log4j 2 API, không phải chương trình JDK độc lập:

~~~java
import org.apache.logging.log4j.CloseableThreadContext;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

Logger log = LogManager.getLogger("checkout");

try (CloseableThreadContext.Instance ignored =
             CloseableThreadContext.put("requestId", verifiedRequestId)
                                   .put("correlationId", correlationId)) {
    log.info("event=order_received");
}
~~~

Cần validate input và bảo đảm scope được dọn. `ThreadContext` có context map và stack; trong thread pool, không giả định dữ liệu thread cha tự truyền. Có thể dùng `ThreadContext.getImmutableContext()` để snapshot và `CloseableThreadContext.putAll(snapshot)` khi vào worker, theo đúng contract backend. Với framework async/reactive, cần cơ chế propagation tương ứng thay vì hard-code ThreadLocal ở một điểm không còn request context.

## 7. Enrich traceId/spanId đúng cách

**Log–trace correlation** là một ứng dụng quan trọng của enrichment. Một request có thể qua API, checkout, payment và DB; nếu log có `TraceId`/`SpanId` tương ứng với span thực, từ một log lỗi có thể truy đến trace, rồi từ trace đi đến log của các service khác.

~~~text
TraceId = 4f0e...4e62
    |
    +-- Span API request         -> log event=request_received
    |
    +-- Span checkout operation  -> log event=order_processed
    |
    +-- Span payment dependency  -> log event=payment_timeout
~~~

**Không tự sinh một `traceId` mỗi lần gọi `logger.info(...)`**: như thế không có trace thực và mất khả năng liên kết. Tracing API/SDK có `SpanContext` chứa trace ID/span ID của span đang active. Dùng instrumentation/bridge hỗ trợ đọc context vào log; tránh copy một raw `traceparent` từ request chưa validate rồi coi là bằng chứng quan hệ service.

Theo W3C Trace Context, `traceparent` chứa cấu trúc version, trace-id, parent-id và flags. Giá trị thực phải được parser/propagator kiểm tra. Nếu `SpanId` có mặt, `TraceId` cũng nên có trong LogRecord; không nên gắn một span ID không thuộc trace tương ứng. Với distributed messaging, context propagation qua headers/envelope cần thiết kế, không thể dựa riêng MDC thread-local.

**Trace sampling không có nghĩa bỏ toàn bộ log.** Trường traceId có thể xuất hiện ở một số log ngay cả khi span không được export; khả năng truy tới trace thực phụ thuộc sampling/exporter. Đừng hứa mọi log có traceId đều mở được trace trên backend.

### OpenTelemetry Java và logging frameworks

OpenTelemetry có đường **bridge/appender** từ các framework logging hiện có như Logback/Log4j 2 sang OpenTelemetry Logs, và đường collector/OTLP cho hạ tầng thu thập. Các API Logs của OpenTelemetry có thiết kế khác với API logging người dùng phổ biến; khi ứng dụng đã dùng SLF4J/Logback, thường không cần thay mọi `LOG.info(...)` bằng API logs SDK thủ công.

Triển khai có thể là:

~~~text
SLF4J / Logback event
      |
      v
OTel appender/bridge (nếu được cấu hình)
      |
      v
OTel LogRecord + TraceId/SpanId + Resource + Attributes
      |
      v
SDK exporter (OTLP)
      |
      v
Collector -> log backend
~~~

Hoặc:

~~~text
Logback structured stdout
      |
      v
Agent/collector parse JSON
      |
      v
Map field/schema vào OTel hoặc backend
~~~

Đây là hai đường triển khai khác nhau, có thể có khả năng capture context và yêu cầu vận hành khác nhau. **Không kích hoạt đồng thời hai tuyến ingest cùng một event vào chung index** nếu không có chiến lược xử lý duplicate, provenance và chi phí.

## 8. Resource enrichment trong OpenTelemetry

Các thuộc tính Resource thường dùng:

- `service.name`: tên service logic, giống nhau trên các replica cùng service.
- `service.namespace`: namespace nếu cần phân biệt service giữa nhóm.
- `service.version`: version ứng dụng/artefact.
- `service.instance.id`: định danh một instance (không đồng nghĩa pod name trong mọi môi trường).
- `deployment.environment.name`: tên môi trường như `development`, `staging`, `production`.
- Các thuộc tính hạ tầng như container/Kubernetes/cloud nếu có instrumentations hoặc collector phù hợp và quyền thu thập.

Đặc biệt, tên chuẩn hiện dùng `deployment.environment.name`. Tên cũ `deployment.environment` đã được đánh dấu deprecated trong registry semantic conventions. Khi đọc tài liệu/thư viện cũ, cần kiểm tra phiên bản và mapping migration để không lưu cả hai field một cách không nhất quán.

Ví dụ cấu hình environment **minh họa** cho một runtime có OpenTelemetry SDK/Java agent hỗ trợ các biến OTel:

~~~text
OTEL_SERVICE_NAME=checkout
OTEL_RESOURCE_ATTRIBUTES=service.version=1.0.0,deployment.environment.name=production
~~~

Các biến này **không làm JUL tự xuất JSON/OTLP**. Chúng chỉ có tác dụng khi instrumentation/SDK/agent phù hợp đã được cài và nạp. Ở production, thiết lập qua manifest/deployment/secret/config system, tránh đặt giá trị sai khác giữa ứng dụng và collector.

Một Resource nên mô tả nguồn, không phải request: đừng đặt `requestId` hay `userId` vào `service.name` hoặc Resource rồi giữ qua nhiều request. Như vậy sẽ làm sai việc gom nhóm telemetry và tăng số thực thể vô nghĩa.

## 9. Enrichment tại collector và quy tắc ghi đè

Collector có thể enrich bằng resource processor, attributes processor hoặc transform processor tùy distribution/version. Ví dụ bổ sung `service.name` từ deployment metadata đáng tin, đổi tên trường cũ, xóa field nhạy cảm hoặc chuẩn hóa giá trị.

Chức năng thường gặp:

| Thao tác | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| **insert** | Chỉ thêm khi chưa có | Đưa default không làm mất value ứng dụng đã xác minh |
| **update** | Chỉ sửa khi đã tồn tại | Chuẩn hóa một key được bảo đảm có sẵn |
| **upsert** | Thêm hoặc sửa | Chuẩn hóa field có nguồn chân lý ưu tiên rõ |
| **delete** | Xóa field | Loại metadata không được phép giữ |
| **transform/rename** | Đổi tên/kiểu theo schema | Migration giữa version hoặc mapping source |

Một processor chỉ có tác dụng khi thực sự nằm trong pipeline của collector. Nếu đặt cấu hình processor nhưng không đưa nó vào `service.pipelines.logs.processors`, dữ liệu có thể đi qua mà không được enrich. Tên chính xác và cú pháp tùy bản collector và bộ processor được cài; không giả định bất cứ transform nào có mặt trong mọi distribution.

**Cần bảo toàn tính toàn vẹn dữ liệu nguồn:** collector không thể chắc tenant của request bằng cách đọc tùy ý `X-Tenant-Id`; còn `service.version` từ config deploy có thể được coi là đáng tin nếu pipeline quản lý chặt. Có thể lưu provenance hoặc phát cảnh báo khi field mâu thuẫn.

Với trường nhạy cảm, nên redaction **ngay từ ứng dụng**, collector là lớp bổ sung. Một token đã đi vào stdout/file/queue trước collector vẫn có thể bị đọc/backup dù bị xóa ở backend cuối.

### JSON và kiểu dữ liệu

Lợi ích lớn của structured logging là giữ được kiểu:

~~~json
{
  "event": "order_processed",
  "durationMs": 34,
  "attempt": 2,
  "success": true,
  "traceId": "4f0e2c13b69a497389d74e71a52b4e62"
}
~~~

`durationMs` là số, `attempt` là số, `success` là boolean. Nếu formatter biến tất cả thành text `"34ms"`/`"true"`, hệ thống query và aggregation có thể phải parse hoặc gặp lỗi mapping kiểu dữ liệu. Một schema nên định nghĩa null/missing và version. Đừng để cùng một field hôm nay là number, ngày mai là string nếu index/backend yêu cầu kiểu nhất quán.

## 10. Vấn đề lớn nhất: context qua async, thread pool và message broker

`MDC` và nhiều cách quản lý context gắn với thread hiện tại. Trong Java, `ExecutorService`, `CompletableFuture`, reactive code, scheduler hoặc message consumer có thể thực hiện công việc trên thread khác.

Hai lỗi:

1. **Context thiếu:** request A có `requestId=A`/`traceId=A` trong web thread, nhưng worker không nhận. Log ở worker không truy ngược được request nguồn.
2. **Context lẫn:** worker còn context của request A sau một task, rồi xử lý B và gắn ID A lên event B. Đây là lỗi nghiêm trọng khi field được dùng để phân vùng log theo tenant.

Để tránh, cần **capture tại boundary gửi task**, **restore/set ở boundary worker**, **cleanup trong finally**. Với SLF4J MDC:

~~~java
// Snippet: org.slf4j.MDC, java.util.Map.
static Runnable withMdc(Runnable task) {
    Map<String, String> captured = MDC.getCopyOfContextMap();
    return () -> {
        Map<String, String> before = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            if (before == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(before);
            }
        }
    };
}
~~~

Ví dụ sử dụng `executor.execute(withMdc(() -> LOG.info("event=...")))` khi caller còn MDC. Đây là snippet đặt trong class có `MDC` và `executor` đã khai báo, không phải file runnable độc lập.

**Lưu ý về reset:** cách restore `before` phù hợp nested scopes. Với những task **độc lập**, framework nên bảo đảm worker bắt đầu và kết thúc với context sạch; nếu `before` đã chứa dữ liệu rò từ code trước, restore không khắc phục được nguồn rò. Cần test một worker xử lý `A → B → no-context`.

### Async appender và event snapshot

Async logger có thể enqueue event và xử lý trên thread I/O khác. Không lấy `MDC.get("requestId")` từ thread writer rồi gán cho event đang xuất: đó là MDC của writer, không chắc là context của producer. Dùng MDC snapshot/event data mà backend đã gắn vào event theo contract. Với tracing SDK, context propagation phải do API/instrumentation hỗ trợ; copy một vài chuỗi vào MDC không tự tạo span hoặc liên kết parent–child.

### Qua message broker

Producer cần đưa correlation/trace context vào **message metadata được truyền qua broker**, không chỉ vào MDC. Consumer validate/extract context, thiết lập scope khi xử lý, rồi dọn. `messageId` nhận diện thông điệp logic; `traceId` nhận diện trace; `correlationId` nhận diện workflow theo hợp đồng; một trường không tự thay thế hai trường còn lại. Không tin user-supplied header làm bằng chứng xác thực tenant.

## 11. Chọn metadata có kiểm soát để tránh làm log kém chất lượng

**Enrich càng nhiều không đồng nghĩa observability càng tốt.**

### Cardinality

Có sự khác nhau giữa:

- **Log field** `requestId`: có thể có hàng triệu giá trị; hữu ích để tìm một request trong backend có index và retention phù hợp.
- **Metric label** `requestId`: có thể tạo hàng triệu time series, làm tăng CPU/memory/cost; **không** nên.
- **Resource attribute** `service.instance.id`: có thể có nhiều instance, phù hợp khi xác định nguồn nhưng phải đánh giá cách backend gom nhóm.
- **Event name/error code** từ catalog hữu hạn: thuận lợi cho aggregation và metric dimensions.

Các trường như userId, sessionId, orderId, URL đầy đủ, raw exception message, token hay timestamp dạng string không nên trở thành label metric. Nếu cần phân tích traffic theo tenant có số lượng lớn, tính toán/aggregation phải xét giới hạn cardinality và quyền riêng tư, không suy cứ có log field thì đưa thành metric dimension.

### Kích thước và chi phí

Mỗi event thêm nhiều trường có thể làm tăng kích thước JSON, chi phí ingest/index/storage và thời gian format. Khi 1 triệu event/ngày, chỉ cần thêm 200 byte/event cũng tăng khoảng 200 MB/ngày (trước compression/index/replica). Cần theo dõi dữ liệu thực, đặt giới hạn kích thước chuỗi, số field và schema. Không copy toàn bộ HTTP headers, object `toString()` hoặc payload JSON lớn để “enrich”.

### Độ tin cậy và tính đúng của trường

Một `traceId` sai còn nguy hiểm hơn field thiếu vì khiến người điều tra nối log sai trace. Một `tenantRef` sai có thể định tuyến log vào nơi không phù hợp; xác thực và data lineage phải đi cùng enrichment. Không suy định danh người dùng từ raw user-agent/IP nếu không được phép và không có lợi ích rõ.

Nếu metadata bắt buộc bị thiếu, phát cảnh báo chất lượng telemetry và xem nguyên nhân ở boundary; không tự chế chuỗi `requestId=random` trong collector rồi khẳng định nó là ID của request nguồn.

## 12. Bảo mật và quyền riêng tư khi enrichment

OWASP khuyến nghị không trực tiếp đưa nhiều loại dữ liệu nhạy cảm vào log: password, access token, session identifier, encryption key, dữ liệu cá nhân nhạy cảm và connection string. Enrichment có thể vô tình tăng rủi ro vì field dễ query và được sao chép qua nhiều backend.

| Trường/tình huống | Rủi ro | Cách tiếp cận |
| --- | --- | --- |
| `user.email`, `phone`, `ip.address` | Nhận dạng cá nhân, lưu dài hạn | Chỉ ghi khi có mục đích/căn cứ; mask/pseudonymize nếu thích hợp |
| Access token, cookie, JWT | Lộ credential | **Không log**; không hash bừa rồi coi là an toàn |
| `tenantId` do client tự đưa | Spoofing, ghi log sai tenant | Lấy từ principal/envelope được xác thực |
| Full URL có query | Token/PII ở query string | Ghi route template hoặc trường whitelist |
| `exception.getMessage()`, stack trace | Có thể chứa SQL, host, secret, user input | Kiểm tra/redact trước khi xuất sink không được phép |
| `requestId` chứa newline | Log injection và parse sai | Validate format/length, escape control characters |
| Stable userRef lâu dài | Có thể theo dõi một người theo thời gian | Giới hạn scope/retention và quyền query |
| File/collector sidecar khác nhau | Dữ liệu có thể xuất tại sink phụ | Test tất cả đầu ra, không chỉ dashboard chính |

**Hash/pseudonymization không đồng nghĩa vô danh tuyệt đối.** Với ID dễ đoán và cần correlation, có thể cân nhắc HMAC có key riêng, version và scope thay vì SHA-256 thuần; nhưng giải pháp thường tốt nhất là **không thu field không cần thiết**.

Cần áp:

1. Data minimization trước khi phát log.
2. Schema whitelist và giới hạn input.
3. RBAC/tenant isolation ở backend/query, không chỉ UI filter.
4. Retention, encryption và audit việc truy cập log.
5. Kiểm thử marker giả nhạy cảm trong stdout, file, collector, tracing và backup.
6. Policy xử lý trường thiếu/xung đột, không fail-open vào sink tenant khác.

Enrichment **không thay đổi quyền** của caller; biết `requestId`/`traceId` không được coi là bằng chứng cho phép truy vấn dữ liệu người khác.

## 13. Các ví dụ trước/sau có giá trị thực tế

### A. Debug payment timeout

Trước:

~~~text
ERROR request failed
~~~

Sau:

~~~json
{
  "event": "payment_attempt_failed",
  "errorCode": "PAY-TIMEOUT",
  "service.name": "billing",
  "dependency": "payment-gateway",
  "requestId": "req-42",
  "attempt": 2,
  "outcome": "retry_scheduled",
  "durationMs": 5030
}
~~~

Một log enriched như vậy giúp biết đây là lỗi attempt tạm và sẽ retry. Đừng dùng mỗi `errorCode=PAY-TIMEOUT` để suy đã có **failure cuối cùng**; cần `outcome` và `attempt`.

### B. Tìm lỗi chỉ xảy ra ở version mới

Trước:

~~~text
WARN validation failed
~~~

Sau:

~~~json
{
  "event": "request_validation_failed",
  "errorCode": "REQ-VALIDATION-001",
  "service.name": "checkout",
  "service.version": "2.4.1",
  "deployment.environment.name": "production",
  "requestId": "req-51",
  "route": "/orders/{orderId}",
  "outcome": "rejected"
}
~~~

Dùng **route template** thay vì URL chứa orderId và query, giúp nhóm theo endpoint, ít lộ dữ liệu hơn. Nhưng nếu muốn xác định request cụ thể, giữ requestId ở log được bảo vệ. Version service nên được lấy từ cấu hình artefact/deploy thay vì tự suy theo thời điểm.

### C. Liên kết với tracing

Trước:

~~~text
INFO request started
INFO db query slow
ERROR gateway timeout
~~~

Sau có thể thêm cùng `TraceId` và `SpanId` tương ứng từ **tracing SDK thực**, để liên kết từ log đến span gây chậm. Nếu một event xảy ra ngoài active span thì `SpanId` có thể không tồn tại; không tạo giá trị giả để “đầy schema”.

### D. Message consumer bị redelivery

Trước:

~~~text
INFO processing message
INFO processing message
~~~

Sau:

~~~text
event=message_received messageId=msg-1001 attempt=1 consumer=billing
event=message_failed messageId=msg-1001 attempt=1 errorCode=PAY-TIMEOUT
event=message_received messageId=msg-1001 attempt=2 consumer=billing
event=message_processed messageId=msg-1001 attempt=2 outcome=success
~~~

Enrichment cho thấy hai lần nhận cùng message do retry. Nhưng nó không đảm bảo idempotency: side effect cần cơ chế riêng ở database/transport nếu không được phép xử lý trùng.

## 14. Kiểm thử enrichment: chính xác hơn việc chỉ nhìn console

### Test ở ứng dụng

- **Resource:** `service.name`, `service.version`, `deployment.environment.name` đúng theo instance; không lẫn môi trường.
- **Request scope:** hai request liên tiếp trên cùng một thread pool không rò `requestId`, tenantRef hoặc trace context.
- **Event scope:** `errorCode` chỉ ở event lỗi, `durationMs` numeric và không âm, `outcome` đúng với kết quả nghiệp vụ.
- **Async:** event trong task nhận context đã capture tại submit, không dùng giá trị thread writer; callback/CompletableFuture có propagation phù hợp.
- **Missing trace:** khi không có active span, không bịa trace ID; schema xử lý optional đúng.
- **Input độc hại:** header có control characters/newline, giá trị quá dài, tenant spoof, user-supplied IDs không làm sai phân vùng hay log injection.
- **Sensitive data:** marker giả như `TEST_PRIVATE_VALUE` không có ở đầu ra không được phép.
- **Mức log:** khi DEBUG bị tắt, không tính enrichment đắt đỏ không cần thiết; khi error quan trọng, không drop im lặng do pipeline.

### Test ở backend/collector

- **Kiểu dữ liệu:** `durationMs` vẫn là number, không bị đổi thành string trong collector/index.
- **Structured fields:** SLF4J `addKeyValue` thật sự xuất ra sink; không chỉ nằm trong object API.
- **Mapping OTel:** `service.name` ở Resource, `traceId`/`spanId` ở trường trace, event attrs đúng, timestamp và observed time không bị nhầm.
- **Processor order:** collector transformations có được bật trong `service.pipelines.logs` và theo đúng thứ tự không?
- **Xung đột:** test khi app và collector đều có cùng key, đặc biệt trusted values; không overwrite sai.
- **Duplicate ingest:** app ghi stdout và OTLP song song có làm cùng event vào index hai lần không?
- **Cardinality và chi phí:** đo số field, kích thước trung bình, index mapping, query latency, high-cardinality metrics.
- **Quyền truy cập:** người có quyền tenant A không tìm được dữ liệu tenant B bằng cách sửa filter UI/query.
- **Retention:** có giữ quá lâu các log kèm pseudonymous identifier không?

### Hướng test bằng Java

Với JUL, test handler có thể chụp `LogRecord`. Với Logback/Log4j 2, dùng test appender/encoder thực và assert giá trị field. **Đừng chỉ mock `LOG.info(...)`** vì mock không chứng minh MDC/key–value pairs được backend xuất. Với OpenTelemetry, test các LogRecord theo đúng SDK/exporter đang triển khai hoặc query backend trong integration test, không chỉ so sánh chuỗi console.

## 15. Lỗi phổ biến và cách sửa

| Dấu hiệu | Nguyên nhân điển hình | Sửa/kiểm tra |
| --- | --- | --- |
| `%X{requestId}` trống | MDC chưa được đặt, sai key hoặc callback chạy thread khác | Thiết lập scope ở boundary, truyền snapshot đúng |
| Request B có requestId của A | Quên dọn MDC trên thread pool | `finally`, restore/clear và test A → B → no-context |
| Log có traceId nhưng không mở được trace | ID tự sinh, trace không được export, sampling hoặc context sai | Lấy từ active span, kiểm tra exporter/sampling |
| `addKeyValue` không xuất ra JSON | Backend/layout chưa hỗ trợ field | Dùng encoder JSON/structured thực và integration test |
| `service.name` là `unknown_service` | OTel Resource chưa cấu hình | Thiết lập `OTEL_SERVICE_NAME` và kiểm tra SDK/agent |
| `deployment.environment` và `deployment.environment.name` cùng xuất | Semantic convention cũ/mới và mapping chưa thống nhất | Chuẩn hóa theo version và migration plan |
| Field `durationMs` có khi số, có khi string | Producer/collector không thống nhất schema | Enforce typed field + contract test |
| Một log hiện hai lần trong backend | Thu stdout và OTLP/file song song | Vẽ ingest pipeline, bỏ route trùng có chủ đích |
| Tenant A nhìn thấy log B | Context/route sai hoặc backend không enforce ACL | Xác thực tenant, phân quyền server-side |
| Metric cardinality tăng vọt | Dùng requestId/userId làm label | Chỉ dùng label hữu hạn, giữ ID động trong log |
| Log có raw token mặc dù collector redact | Dữ liệu đã lộ ở stdout/file trước processor | Redact ở nguồn và kiểm tra mọi sink |
| Exception làm mất field | Bắt lỗi/rethrow trên boundary khác, MDC bị xóa | Test error paths, scope và event capture |
| Enrich rất chậm | Format object lớn/serialization ngay cả khi level tắt | Lazy computation, bounded attrs, profiling |
| Collector overwrites service.version sai | Nhiều nguồn giá trị cạnh tranh | Quy định trusted source và precedence |
| Rất nhiều field `unknown` | Không phân biệt missing và lỗi propagation | Quản lý optional schema + alert thiếu context |

## 16. Checklist triển khai thực tế

1. **Chọn mục tiêu quan sát**: tìm request, điều tra latency, phân loại lỗi, truy vết message hay phân biệt deploy; đừng enrich vô hạn.
2. **Thiết kế schema** theo Resource / request-span / event attributes, áp semantic conventions nơi có thể.
3. **Giữ nguồn sự thật:** service/version từ deploy, tenant từ principal xác thực, event/outcome từ logic nghiệp vụ, trace/span từ tracing instrumentation.
4. **Chuẩn hóa field và kiểu**: stable keys, typed numeric/duration, chính sách missing/null, schema evolution.
5. **Enrich tại đúng điểm**: event attributes ngay khi log, context tại middleware, resource tại runtime/collector, không ghi nhầm lên Global MDC.
6. **Giữ scope an toàn**: `try/finally` dọn MDC; thread pool/reactive/message broker truyền context theo boundary, không rò giữa task.
7. **Chọn một pipeline ingest được kiểm chứng**: structured stdout hoặc OTLP bridge, phân biệt các sink và tránh duplicate.
8. **Giảm dữ liệu**: không log credentials, body/headers nguyên vẹn, PII không cần thiết; validate input và redaction ngay nguồn.
9. **Kiểm thử end-to-end**: appender, JSON encoder, OTel mapping, collector, backend, quyền truy cập, missing context, error paths.
10. **Giám sát chất lượng telemetry**: tỷ lệ thiếu trace/request, parser errors, mismatched field types, duplicate ingest, queue drops và chi phí.
11. **Quản trị lâu dài**: catalog field, người sở hữu, version, retention và chính sách bổ sung/xóa field.

**Ghi nhớ:** Log enrichment là gắn **đúng metadata vào đúng sự kiện và đúng ngữ cảnh**, không chỉ tăng số ký tự trong message. Resource cho biết nguồn phát, context nối request/trace, event attributes giải thích hành động và kết quả. Sự chính xác của context, khả năng truyền qua async, typed schema, bảo vệ dữ liệu và kiểm thử ở sink thực tế quyết định enrichment có cải thiện observability hay không.

### Tài liệu tham khảo chính thức

- OpenTelemetry — [Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/), [Log correlation](https://opentelemetry.io/docs/specs/otel/logs/), [Semantic Conventions](https://opentelemetry.io/docs/specs/otel/semantic-conventions/).
- OpenTelemetry — [Service Resource attributes](https://opentelemetry.io/docs/specs/semconv/resource/#service), [Deployment environment](https://opentelemetry.io/docs/specs/semconv/resource/deployment-environment/), [Java instrumentation and logging](https://opentelemetry.io/docs/languages/java/instrumentation/).
- SLF4J — [Manual, Fluent API, MDC](https://www.slf4j.org/manual.html), [MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html).
- Logback — [Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html), [Configuration](https://logback.qos.ch/manual/configuration.html).
- Apache Log4j 2 — [Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- Oracle Java 17 — [`java.util.logging.LogRecord`](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html), [`java.util.concurrent.ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).

# Xác định sự kiện quan trọng trong chiến lược Java Core Logging

## 1. Sự kiện quan trọng là gì?

**Sự kiện quan trọng (important log event)** là hành động, thay đổi trạng thái, quyết định hoặc kết quả mà đội ngũ thực sự cần **quan sát, điều tra, đối soát hoặc chứng minh**. Xác định các sự kiện này là một bước thiết kế chiến lược logging: trước khi viết `logger.info()`, phải biết **chuyện gì đáng ghi, ghi để làm gì, ai sử dụng và giữ lại bao lâu**.

Ví dụ trong dịch vụ đặt hàng:

- `ORDER_CREATED`: đơn hàng đã được tạo và giao dịch đã được xác nhận hoàn tất.
- `ORDER_CREATION_REJECTED`: yêu cầu bị từ chối theo quy tắc nghiệp vụ hoặc phân quyền.
- `REPORT_ACCESS_DENIED`: một chủ thể bị chặn truy cập báo cáo.
- `DEPENDENCY_RECOVERED`: dịch vụ phụ thuộc có lỗi tạm, nhưng retry/fallback đã giúp phục hồi.
- `DEPENDENCY_UNAVAILABLE`: không thể hoàn thành request/job sau khi thử các phương án được phép.
- `CONFIG_CHANGED`: cài đặt có ảnh hưởng vận hành hoặc bảo mật được thay đổi.
- `MESSAGE_DEAD_LETTERED`: message đã được chuyển sang nơi cách ly theo hợp đồng của broker.

Ngược lại, `entered method findOrder()`, một phép so sánh nội bộ, hoặc cache miss bình thường có thể chỉ đáng ghi `DEBUG`/`TRACE`, aggregate thành metric hoặc không cần ghi riêng.

**“Quan trọng” không đồng nghĩa mức log `ERROR`.** Một đơn hàng tạo thành công có ý nghĩa lớn nhưng thường là `INFO`. Một lần truy cập bị từ chối có thể là audit/security event cần được giữ, nhưng không nhất thiết là lỗi kỹ thuật. Một lỗi hết retry khiến HTTP trả 503 mới thường thích hợp với `ERROR` hoặc `SEVERE`.

Một sự kiện có giá trị khi giúp trả lời: **Điều gì đã xảy ra? Khi nào? Ai/thành phần nào liên quan? Đối tượng nào bị tác động? Outcome là gì? Có thể theo dấu ở đâu?**

## 2. Phân nhóm trước khi quyết định ghi

| Nhóm | Ví dụ | Mục đích | Lưu ý |
| --- | --- | --- | --- |
| Nghiệp vụ | `ORDER_CREATED`, `REFUND_APPROVED` | Đối soát, hỗ trợ khách hàng, điều tra luồng | Log không thay sổ giao dịch hoặc dữ liệu nghiệp vụ gốc |
| Security/authentication | `LOGIN_DENIED`, `ROLE_GRANTED` | Phát hiện hành vi sai quyền, lịch sử quyết định | Có thể cần audit trail riêng và bảo vệ tính toàn vẹn |
| Vận hành/availability | `DEPENDENCY_UNAVAILABLE`, `CIRCUIT_OPENED` | Điều tra incident, xác định phạm vi ảnh hưởng | Kết hợp SLO/metric/trace |
| Tính toàn vẹn dữ liệu | `RECONCILIATION_FAILED`, `DATA_CHECK_FAILED` | Phát hiện lệch hoặc lỗi dữ liệu | Phân biệt lỗi đã được sửa với lỗi đang tồn tại |
| Thay đổi hệ thống | `CONFIG_CHANGED`, `FEATURE_FLAG_UPDATED` | Truy thay đổi trước một sự cố | Ghi version/actor; tránh giá trị bí mật |
| Job/message lifecycle | `JOB_COMPLETED`, `MESSAGE_DEAD_LETTERED` | Theo dõi batch và consumer | Giữ job/message ID và outcome |
| Chẩn đoán chi tiết | `cache miss`, `starting method` | Phân tích code khi debug | Có thể sampling, retention ngắn |

Một loại sự kiện có thể thuộc hai nhóm. `ROLE_GRANTED` vừa là thao tác quản trị vừa cần audit. Nhưng không nên lấy một `INFO` trong application log và mặc nhiên coi là bản ghi audit đáng tin cậy: audit thường có yêu cầu về completeness, integrity, quyền truy cập, thời gian giữ và khả năng kiểm chứng riêng.

**Business event** mà hệ thống khác cần tiêu thụ (ví dụ `OrderCreated` qua message broker) cũng khác với **log event** để quan sát. Nếu cần phân phối sự kiện nghiệp vụ có bảo đảm, phải dùng cơ chế transactional/outbox/broker theo thiết kế thay vì chỉ gọi logger.

## 3. Dùng câu hỏi dựa trên tác động, không dựa trên số method

Trước khi thêm một event vào danh mục logging, hỏi:

1. Nếu nó xảy ra, **ai sẽ tra cứu** và trong tình huống nào?
2. Nó có thay đổi tiền, quyền truy cập, trạng thái dữ liệu, cấu hình hoặc khả năng phục vụ không?
3. Nó giúp xác định kết quả cuối hoặc một quyết định quan trọng mà metric tổng hợp không thể giải thích riêng lẻ không?
4. Nếu bị bỏ sót, việc khôi phục chuỗi hành động sau incident có gặp khó khăn đáng kể không?
5. Có yêu cầu nội bộ hoặc nghĩa vụ áp dụng về lịch sử hành động không?
6. Có thể gắn request/job/message/trace ID để tìm đúng sự kiện không?
7. Có thể ghi bằng một **schema tối thiểu** mà không lộ raw payload/secret không?
8. Tần suất event có đủ nhỏ hoặc có chính sách volume/sampling thích hợp không?

Nếu không có use case rõ, hãy xem liệu một **metric** như `http_requests_total` hoặc một trace span đã đủ. Việc “logging mọi thứ” thường làm log quan trọng bị chìm trong hàng triệu dòng ít giá trị.

### Ma trận ưu tiên minh họa

| Sự kiện | Mức rủi ro/tác động | Tần suất | Chính sách gợi ý |
| --- | --- | --- | --- |
| Thay đổi vai trò quản trị | Rất cao | Thấp | Audit event với actor/target/outcome, bảo vệ độ tin cậy |
| Giao dịch tài chính được xác nhận | Rất cao | Trung bình | Nguồn sự thật là transaction ledger; log mã tương quan tối thiểu |
| Request cuối trả 503 | Cao về availability | Tăng khi incident | Structured terminal error, metric tỷ lệ, alert theo tác động |
| Retry dependency nhưng phục hồi | Trung bình | Có thể cao | Metric retry và event recovered khi hữu ích |
| Cache lookup miss bình thường | Thấp | Rất cao | Metric/sampling/`DEBUG`, không `INFO` mỗi lần |
| Input không hợp lệ trả 400 theo policy | Thường thấp | Cao | Access log hoặc event được phân loại, tránh `ERROR` mặc định |
| Login denied hàng loạt | Security đáng chú ý | Có thể rất cao | Security telemetry, rate alert, tránh lộ account/raw request |

Đây chỉ là cách **ưu tiên thiết kế**, không phải thang điểm cố định. Yêu cầu cụ thể của công ty, sản phẩm, ngành hoặc dữ liệu có thể khiến cùng một sự kiện cần lưu giữ khác nhau.

## 4. Phân biệt attempt, decision, success và failure

Trước khi đặt tên hoặc chọn level, cần xác định **sự kiện đang mô tả cái gì**:

- **Attempt:** hệ thống *đang cố* thực hiện hành động, chưa chắc đã thành công.
- **Decision:** authorization/business rules đã cho phép hoặc từ chối.
- **Committed success:** thay đổi nghiệp vụ đã được hoàn tất theo hợp đồng.
- **Terminal failure:** hết retry/fallback và kết quả cuối vẫn thất bại.
- **Recovered:** có lỗi tạm nhưng hệ thống đã hồi phục.
- **Unknown/ambiguous:** kết quả chưa xác định, ví dụ timeout sau khi gửi request có side effect.

Một luồng đơn giản:

~~~text
Create order request
        |
        v
 Validate + authorize ----- DENIED -> ORDER_CREATION_REJECTED
        |
        v
 DB transaction
        |
      commit
      /    \
   FAILED  SUCCESS
      |        |
      v        v
 ORDER_CREATION_FAILED   ORDER_CREATED
~~~

**Không ghi `ORDER_CREATED SUCCESS` trước commit** nếu DB vẫn có thể rollback. Đồng thời, log attempt hoặc DENIED khi chính sách cần cũng có giá trị dù không có transaction thành công.

Nếu chỉ phát application log **sau** commit, còn cửa sổ sự cố: DB commit thành công nhưng JVM chết trước khi logger/exporter ghi event. Khi event thật sự phải được bảo toàn cùng thay đổi nghiệp vụ, một cơ chế có thể cân nhắc là **transactional outbox** cùng database transaction: lưu trạng thái nghiệp vụ và một bản ghi cần phát event trong một commit, rồi worker chuyển đi.

~~~text
Transaction in database:
   update business row
   insert outbox event (eventId stable)
          |
        COMMIT
          |
     Outbox worker
          |
  send + retry / ACK
          |
     Destination store
~~~

Outbox giảm nguy cơ mất thông tin khi crash giữa commit và phát event, nhưng **không tự tạo exactly-once** ở đích cuối. Worker có thể gửi thành công rồi chết trước khi cập nhật trạng thái đã gửi; cần event ID ổn định, cơ chế idempotency/dedup phía nhận và đối chiếu. Outbox cũng không tự cung cấp kho audit bất biến; nếu cần audit phải thiết kế integrity, quyền, retention riêng.

### Retry và kết quả cuối

Một dependency timeout ở attempt 1, phục hồi ở attempt 2. Nếu tầng thấp phát `ORDER_CREATION_FAILED` ngay lần đầu, hệ thống có thể báo lỗi không đúng dù kết quả cuối thành công. Retry coordinator có thể ghi `DEPENDENCY_RETRY_SCHEDULED`, cuối cùng boundary ghi `ORDER_CREATED` hoặc `DEPENDENCY_RECOVERED` theo mục đích. **Một exception không đồng nghĩa một terminal failure.**

Ngược lại, timeout sau khi request đã gửi đến hệ thống ngoài có thể khiến trạng thái **không rõ**. Không tự đoán FAILED; cần kiểm tra trạng thái, idempotency hoặc reconciliation.

## 5. Đặt tên và chuẩn hóa taxonomy

Tên event nên phản ánh **sự kiện đã xảy ra** và giữ ổn định:

~~~text
ORDER_CREATED
ORDER_CREATION_REJECTED
ORDER_CREATION_FAILED
REPORT_ACCESS_DENIED
ROLE_GRANTED
ROLE_REVOKED
DEPENDENCY_RECOVERED
DEPENDENCY_UNAVAILABLE
CONFIG_CHANGED
JOB_COMPLETED
MESSAGE_DEAD_LETTERED
~~~

Tránh nhiều biến thể cho cùng một nghĩa như `create_order_success`, `OrderSuccessfullyCreated` và `order.done` nếu chúng phục vụ cùng một contract. Dùng enum hoặc danh mục sự kiện (event catalog) để thống nhất.

**Không nhét ID động vào tên event:** tránh `ORDER_CREATED_42`, nên là `eventCode=ORDER_CREATED` và `targetId=order-42`. Khi tên sự kiện được dùng trong metric/dimension, ID ngẫu nhiên gây cardinality cao; khi cần tìm một event cụ thể, ID hợp hơn ở log field có kiểm soát.

Một định nghĩa event tốt cần có: code, ý nghĩa, điều kiện phát, owner, cấp độ, outcome, schema, trường nhạy cảm, sink, retention, consumer và phương án kiểm thử. Khi đổi tên event hoặc kiểu field, hãy xem đó là **thay đổi hợp đồng**, có thể làm gãy dashboard/alert và truy vấn đã dùng.

## 6. Schema tối thiểu cho sự kiện quan trọng

Có thể quy định các trường tùy ngữ cảnh:

| Field | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `timestamp` | UTC ISO-8601 string | Thời điểm xảy ra/ghi theo định nghĩa |
| `schemaVersion` | integer/string | Phiên bản hợp đồng |
| `eventCode` | enum/string ổn định | Loại sự kiện |
| `outcome` | enum | SUCCESS, DENIED, FAILED, RECOVERED, UNKNOWN |
| `level` | string | Mức severity vận hành của backend |
| `service`, `component` | string | Nguồn ghi |
| `requestId`, `traceId` | string | Liên kết request với các dịch vụ |
| `eventId` | unique ID khi cần | Dedup, audit hoặc replay |
| `actorType`, `actorId` | enum/ID | Chủ thể thực hiện |
| `targetType`, `targetId` | enum/ID | Đối tượng chịu tác động |
| `reasonCode` | enum/string | Nguyên nhân được chuẩn hóa, không phải raw exception |
| `attempt`, `retryPolicyVersion` | integer/string | Cho event retry nếu có |

**Không phải event nào cũng có người dùng.** Job runner có thể có `actorType=SERVICE`; event ở một scheduled job có thể dùng `jobId` thay cho HTTP request ID. Không tạo ra actor hoặc request ID giả chỉ vì schema có field optional.

Ví dụ JSON log về một quyết định:

~~~json
{
  "timestamp": "2026-01-15T10:00:00Z",
  "schemaVersion": 1,
  "service": "reports-api",
  "eventCode": "REPORT_ACCESS_DENIED",
  "outcome": "DENIED",
  "level": "INFO",
  "actorType": "USER",
  "actorId": "user-demo-1",
  "targetType": "REPORT",
  "targetId": "report-7",
  "requestId": "req-102",
  "reasonCode": "POLICY_DENIED"
}
~~~

Đây chỉ là mẫu schema. ID trong bài là dữ liệu giả; trong thực tế actor/target/request ID **vẫn có thể là dữ liệu cá nhân có thể liên kết**, cần chính sách truy cập và lưu giữ. Đừng đưa token xác thực hoặc cookie vào `requestId`.

Chỉ ghi các field thuộc allowlist. Việc `logger.info("request=" + dto.toString())` hoặc in raw body dễ lộ password, dữ liệu cá nhân, token và thông tin thanh toán. **JSON escaping không đồng nghĩa redaction.**

## 7. Severity dựa trên outcome, không dựa trên tầm quan trọng đơn thuần

| Event/kết quả | Level JUL thường cân nhắc | Lý do |
| --- | --- | --- |
| `ORDER_CREATED` thành công | `INFO` | Đáng ghi nhưng không có lỗi |
| `REPORT_ACCESS_DENIED` theo chính sách | `INFO` + security/audit policy | Denial không đồng nghĩa hệ thống hỏng |
| `DEPENDENCY_RECOVERED` sau fallback | `WARNING` nếu suy giảm cần theo dõi | Có phục hồi, nhưng có tín hiệu vận hành |
| `DEPENDENCY_UNAVAILABLE` terminal | `SEVERE` | Request/job không thể phục hồi |
| Validation 400 thông thường | `FINE`/`INFO` hoặc access log | Không kích hoạt incident cho mỗi input sai |
| Thông tin debug một nhánh code | `FINE`/`FINER` | Giá trị chẩn đoán, không phải outcome chính |
| Thay đổi quyền quản trị | Audit policy riêng | Không chỉ dựa vào appender `INFO` có thể bị lọc |

**JUL không có `Level.ERROR`;** nhiều logging backend SLF4J/Logback/Log4j 2 lại có `ERROR`/`WARN`. Khi học và triển khai cần đúng API và cách ánh xạ level. Đừng chọn `SEVERE` cho mỗi exception đã được retry thành công hoặc các lần 403 dự kiến.

Mặt khác, **event quan trọng không tự động phải phát alert**. Một `ORDER_CREATED` thường không đáng đánh thức on-call; một tỷ lệ `DEPENDENCY_UNAVAILABLE` tăng cao có thể kích hoạt alert theo SLO/burn-rate. Security incident đặc biệt có thể cần cảnh báo theo một event đơn lẻ, nhưng phải có policy và cơ chế giảm false positive.

## 8. Ví dụ Java 17 chạy độc lập: phát đúng loại event

Chương trình sử dụng **JDK 17 và `java.util.logging`**, không cần Maven hay dependency ngoài. Nó mô phỏng bốn outcome đã được xác định:

1. Đơn hàng tạo thành công.
2. Quyền đọc báo cáo bị từ chối.
3. Dependency timeout nhưng đã phục hồi.
4. Dependency cuối cùng không khả dụng.

Code dùng **enum** cho event/outcome/reason, record cho dữ liệu và logger handler tùy chỉnh để output xác định. Nó chỉ phát log **sau khi được cung cấp outcome mô phỏng**, không thật sự mở DB, HTTP server, kiểm tra quyền hoặc thực hiện retry. Trong production, phải gọi từ component có quyền sở hữu **kết quả thực**.

Tạo **`ImportantEventLoggingDemo.java`**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ImportantEventLoggingDemo {
    enum EventCode {
        ORDER_CREATED, REPORT_ACCESS_DENIED,
        DEPENDENCY_RECOVERED, DEPENDENCY_UNAVAILABLE
    }

    enum Outcome { SUCCESS, DENIED, RECOVERED, FAILED }
    enum ActorType { USER, SERVICE }
    enum TargetType { ORDER, REPORT, DEPENDENCY }
    enum Reason {
        NONE, POLICY_DENIED, TEMP_TIMEOUT, RETRY_EXHAUSTED
    }

    record Event(
            Instant occurredAt,
            EventCode code,
            Outcome outcome,
            String requestId,
            ActorType actor,
            TargetType targetType,
            String targetId,
            Reason reason) {}

    private static String id(String field, String value) {
        if (value == null ||
                !value.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException(
                    "Invalid identifier: " + field);
        }
        return value;
    }

    private static void emit(
            Logger logger, Level level, Event e) {
        String payload =
                "at=" + Objects.requireNonNull(e.occurredAt())
                + " event=" + Objects.requireNonNull(e.code())
                + " outcome=" + Objects.requireNonNull(e.outcome())
                + " request=" + id("request", e.requestId())
                + " actor=" + Objects.requireNonNull(e.actor())
                + " targetType=" + Objects.requireNonNull(e.targetType())
                + " target=" + id("target", e.targetId())
                + " reason=" + Objects.requireNonNull(e.reason());
        logger.log(level, payload);
    }

    private static Logger createLogger() {
        Logger logger = Logger.getLogger("demo.important.events");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.print(getFormatter().format(record));
                }
            }
            @Override
            public void flush() {
                System.out.flush();
            }
            @Override
            public void close() {
                flush();
            }
        };
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(handler);
        return logger;
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-01-15T10:00:00Z"),
                ZoneOffset.UTC);
        Instant when = Instant.now(clock);
        Logger logger = createLogger();

        try {
            emit(logger, Level.INFO, new Event(
                    when, EventCode.ORDER_CREATED,
                    Outcome.SUCCESS, "req-101",
                    ActorType.USER, TargetType.ORDER,
                    "order-42", Reason.NONE));

            emit(logger, Level.INFO, new Event(
                    when, EventCode.REPORT_ACCESS_DENIED,
                    Outcome.DENIED, "req-102",
                    ActorType.USER, TargetType.REPORT,
                    "report-7", Reason.POLICY_DENIED));

            emit(logger, Level.WARNING, new Event(
                    when, EventCode.DEPENDENCY_RECOVERED,
                    Outcome.RECOVERED, "req-103",
                    ActorType.SERVICE, TargetType.DEPENDENCY,
                    "stock-api", Reason.TEMP_TIMEOUT));

            emit(logger, Level.SEVERE, new Event(
                    when, EventCode.DEPENDENCY_UNAVAILABLE,
                    Outcome.FAILED, "req-104",
                    ActorType.SERVICE, TargetType.DEPENDENCY,
                    "stock-api", Reason.RETRY_EXHAUSTED));
        } finally {
            for (Handler h : logger.getHandlers()) {
                logger.removeHandler(h);
                h.close();
            }
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac ImportantEventLoggingDemo.java
java ImportantEventLoggingDemo
~~~

**Stdout chính xác** khi chạy thành công:

~~~text
INFO: at=2026-01-15T10:00:00Z event=ORDER_CREATED outcome=SUCCESS request=req-101 actor=USER targetType=ORDER target=order-42 reason=NONE
INFO: at=2026-01-15T10:00:00Z event=REPORT_ACCESS_DENIED outcome=DENIED request=req-102 actor=USER targetType=REPORT target=report-7 reason=POLICY_DENIED
WARNING: at=2026-01-15T10:00:00Z event=DEPENDENCY_RECOVERED outcome=RECOVERED request=req-103 actor=SERVICE targetType=DEPENDENCY target=stock-api reason=TEMP_TIMEOUT
SEVERE: at=2026-01-15T10:00:00Z event=DEPENDENCY_UNAVAILABLE outcome=FAILED request=req-104 actor=SERVICE targetType=DEPENDENCY target=stock-api reason=RETRY_EXHAUSTED
~~~

**Stderr:** trống trong trường hợp thành công. Logger cha được tắt để tránh output trùng; handler demo in ra `System.out`. `ConsoleHandler` tiêu chuẩn của JUL thường in stderr, nhưng **không dùng trong ví dụ**.

### Vì sao ví dụ thiết kế như vậy?

- `EventCode`, `Outcome`, `ActorType`, `TargetType`, `Reason` là enum: giảm nguy cơ nhiều từ ngữ cho cùng một event.
- `Clock.fixed` chỉ nhằm có output kiểm thử tái lập. Ở production, dùng thời gian có nghĩa theo schema và đồng bộ đồng hồ; timestamp do client khai không mặc nhiên đáng tin.
- `id()` giới hạn ID demo và chặn newline, giảm log injection. Nó không chứng minh ID không thuộc dữ liệu cá nhân và không phải bộ parser ID đa ngôn ngữ.
- `emit()` chỉ ghi metadata đã được chọn, không dump `Exception.getMessage()` hay request body.
- `ORDER_CREATED` rất quan trọng nhưng `INFO`, trong khi `DEPENDENCY_UNAVAILABLE` ảnh hưởng khả năng phục vụ nên `SEVERE`.
- `REPORT_ACCESS_DENIED` chỉ phản ánh **decision** được giả định, không thực sự kiểm tra quyền. Nếu audit là bắt buộc, cần đường lưu riêng có durability và policy phù hợp.
- Handler được tháo, đóng trong `finally`. Ví dụ này là **logging chẩn đoán**, chưa có collector, persistent queue, outbox, JSON encoder hoặc bằng chứng lưu bền.

## 9. Chọn tầng chịu trách nhiệm phát event

Một sự kiện đáng tin nên được ghi ở tầng **biết kết quả thật** và có đủ context:

| Event | Tầng thường có quyền sở hữu | Điều cần biết |
| --- | --- | --- |
| `ORDER_CREATED` | Service sau commit/outbox cùng transaction | Thay đổi đã thành công thật |
| `REPORT_ACCESS_DENIED` | Authorization middleware/boundary | Quyết định chặn và mã lý do |
| `DEPENDENCY_RECOVERED` | Retry coordinator hoặc service fallback | Bao nhiêu attempt và outcome cuối |
| `DEPENDENCY_UNAVAILABLE` | Request/job error boundary | Không còn phục hồi, ảnh hưởng request/job |
| `JOB_COMPLETED` | Scheduler/job runner | Job ID, số item, thời lượng, trạng thái |
| `MESSAGE_DEAD_LETTERED` | Consumer recovery layer | DLQ handoff đã được xác nhận theo broker |
| `CONFIG_CHANGED` | Configuration/admin service | Actor, config version, action outcome |

Repository có thể bắt `SQLException`, nhưng chưa biết request sẽ được retry thành công hay không. Nếu chỉ wrap rồi rethrow, thường nên **giữ cause và không log cùng stack trace ở mọi tầng**. Boundary cuối ghi terminal event. Một service vẫn có thể ghi sự kiện độc lập như `CIRCUIT_OPENED` hoặc `FALLBACK_ACTIVATED` nếu nó thực sự xảy ra.

**“Log once” không có nghĩa một request chỉ có đúng một log.** Có thể có `ORDER_CREATED`, `CACHE_FALLBACK_ACTIVATED` và HTTP completion event vì chúng mô tả các sự kiện khác nhau; điều cần tránh là nhiều dòng lỗi trùng thông tin từ cùng một exception.

## 10. Sampling, volume, SLO và khả năng điều tra

Không nên giữ mọi log với một chính sách sampling duy nhất:

| Loại | Chính sách thường xem xét |
| --- | --- |
| Debug chi tiết mỗi branch | Bật có thời hạn, sampling hoặc môi trường test |
| HTTP 200 ở QPS cao | Metric, trace sampling hoặc structured access log tùy nhu cầu |
| Terminal failure ảnh hưởng SLO | Ưu tiên event đủ điều tra, alert theo tỷ lệ và tác động |
| Security/audit bắt buộc | Không sampling tùy tiện nếu mục tiêu đòi completeness |
| Đổi quyền/cấu hình quan trọng | Giữ bằng chứng theo security/audit policy |
| Sự kiện hiếm nhưng hậu quả lớn | Thường cần thu thập đầy đủ và có alert theo ngữ nghĩa |

**Sampling có thể làm rơi đúng sự kiện hiếm cần điều tra nhất.** Nên chọn theo `eventCode`, loại nguồn, impact và retention. Nếu bùng nổ log khi dependency lỗi, có thể rate-limit log chẩn đoán lặp hoặc tổng hợp số lần, đồng thời vẫn theo dõi terminal failure và metric drop count.

Một event được phát ở logger chưa chắc đã lưu tại collector. Async queue có thể đầy, transport có thể lỗi, file có thể bị xoay/xóa trước khi shipper đọc. Với event bắt buộc cần lưu, phải quy định durable storage, ACK, retry, queue/backpressure, retention và phản ứng khi không ghi được; **không chỉ trông vào mức `INFO`**.

### Metric, trace và alert bổ sung

~~~text
Log:
event=DEPENDENCY_UNAVAILABLE
requestId=req-104 reasonCode=RETRY_EXHAUSTED

Metric:
dependency_failures_total{dependency="stock-api",reason="timeout"} += 1

Trace:
HTTP span -> stock-api span (error, duration, traceId)
~~~

Đây là **mẫu minh họa**, không phải output chương trình Java. Metric không nên có user ID, request ID hoặc order ID làm label vì cardinality rất cao. Alert theo SLO/error rate và các sự kiện thực sự cần điều tra; **không đánh thức on-call vì từng `INFO`**.

## 11. Bảo mật và dữ liệu cá nhân của event quan trọng

Một log có actor ID, target ID, IP, trace ID và timestamp có thể vẫn liên kết với người dùng. Quan trọng không đồng nghĩa “ghi càng nhiều càng tốt”.

**Không mặc định ghi vào log:**

- Password, access/refresh token, OTP, cookie, khóa bí mật.
- Toàn bộ HTTP request/response body hoặc DTO `toString()`.
- Raw SQL/exception message có thể chứa tham số, URL hoặc PII.
- Số tài khoản/thông tin thanh toán, giấy tờ hoặc dữ liệu nhạy cảm không cần thiết.
- User input tự do trong tên event, metric label hoặc unescaped text log.

Chỉ giữ các trường theo **allowlist**. Nếu cần actor/target ID cho mục đích audit, xác định chính sách quyền đọc, encryption, retention và deletion phù hợp. Hash email cố định hoặc token hóa ID không tự động biến dữ liệu thành vô danh nếu còn có thể liên kết hay truy ngược.

Với text log, validate trường không tin cậy để tránh newline/log injection. Với JSON log, dùng serializer chuẩn; nó giúp escaping và kiểu dữ liệu, nhưng **không tự redaction**. Đặt mẫu dữ liệu sentinel giả trong unit/integration test để kiểm tra thông tin bí mật không lọt tới file, stdout hoặc collector.

## 12. Event catalog — hợp đồng dùng chung giữa các đội

Một danh mục event giúp các team thống nhất code, nguồn phát và cách sử dụng:

| Event | Trigger | Owner | Outcome | Sink/consumer |
| --- | --- | --- | --- | --- |
| `ORDER_CREATED` | DB commit được xác nhận | Order service | SUCCESS | Business/operations log |
| `REPORT_ACCESS_DENIED` | Authorization ra quyết định DENY | Security boundary | DENIED | Security/audit policy |
| `DEPENDENCY_RECOVERED` | Retry/fallback hoàn thành | Retry coordinator | RECOVERED | Operations + metric |
| `DEPENDENCY_UNAVAILABLE` | Hết retry, request/job fail | Error boundary | FAILED | Error log/alert theo tỷ lệ |
| `CONFIG_CHANGED` | Cập nhật config được xác nhận | Admin service | Theo hợp đồng | Audit/change log |
| `JOB_COMPLETED` | Job kết thúc | Job runner | SUCCESS/FAILED | Operations |
| `MESSAGE_DEAD_LETTERED` | DLQ handoff được xác nhận | Message consumer | DEAD_LETTERED | Messaging operations |

Một định nghĩa có thể kèm:

1. **Ý nghĩa, phạm vi và điều kiện phát** (attempt hay committed outcome).
2. **Owner** duy trì schema và xử lý cảnh báo.
3. **Trường bắt buộc**, kiểu dữ liệu, nullability, dữ liệu nhạy cảm.
4. **Severity, retention và routing** đến các kênh phù hợp.
5. **Volume kỳ vọng** và cách kiểm soát cardinality/sampling.
6. **Guarantee**: best-effort hay bắt buộc lưu; phản ứng khi ghi lỗi.
7. **Consumer**: dashboard, alert, support, audit hoặc investigation.
8. **Schema version, migration và contract test**.
9. **Runbook** khi có bất thường và cách tìm request/job/event.

Đổi `eventCode` hoặc kiểu `status` từ số sang string có thể làm dashboard gãy dù log vẫn parse được. Hãy xem schema logging là một hợp đồng với các downstream consumer.

## 13. Kiểm thử nội dung và pipeline event

### 13.1. Unit test producer

- `ORDER_CREATED` chỉ xuất hiện khi commit thật sự thành công, không phát sau rollback.
- Access denied tạo đúng `REPORT_ACCESS_DENIED` và mã lý do, không lộ input nhạy cảm.
- Retry thành công không tạo terminal failure giả; retry thất bại thật tạo `DEPENDENCY_UNAVAILABLE`.
- Event code được chọn từ danh mục chuẩn, không từ user input tùy tiện.
- Outcome, actor/target, reason code, request ID và timestamp đúng ngữ nghĩa.
- Không phát trùng cùng terminal event do nhiều `catch` log and rethrow.

### 13.2. Integration test logger/backend

- Capture `LogRecord` qua JUL `Handler` test hoặc appender của backend thực.
- Kiểm tra level/filter/parent handlers không làm rơi hoặc nhân event.
- Với JSON logging, parse JSON/NDJSON bằng thư viện thay vì chỉ so raw string.
- Với MDC/ThreadContext, context được dọn trong `finally` và không rò giữa request.
- Với async logging, chờ flush/drain hoặc await có timeout; không dùng `Thread.sleep` tùy tiện làm bảo đảm.
- Kiểm tra trường nhạy cảm bằng dữ liệu sentinel giả ở các sink.

### 13.3. Fault injection / end-to-end

- Collector down, queue đầy, file spool lỗi, disk full: ứng dụng phản ứng theo chính sách, có metric drop và alert.
- Retry transport sau timeout ACK: có thể duplicate; kiểm tra event ID ổn định/dedup.
- Với outbox: crash giữa commit–publish và publish–ACK; xác nhận khả năng hồi phục.
- Audit: kiểm tra quyền, integrity, retention và truy vấn theo actor/event ID nếu có yêu cầu.
- Schema nâng version hoặc thay đổi field: consumer cũ/mới đọc được theo contract.
- Đối soát event theo operation ID; phân biệt số **attempt** với số terminal outcome.

**Một mock `logger.info()` được gọi chỉ chứng minh code đã gọi logger.** Nó không chứng minh event đã đến hoặc lưu bền tại hệ thống đích.

## 14. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Ghi mọi method ở `INFO` | Log noise và chi phí cao | Chỉ định event có ý nghĩa; debug có chủ đích |
| Mọi exception đều `SEVERE` | Retry thành công bị tính incident | Severity theo outcome cuối |
| Ghi success trước commit | Log sai khi rollback | Phát sau commit hoặc outbox theo yêu cầu |
| Bỏ mọi DENIED | Không thấy hành động bị chặn | Security/audit event có policy |
| Tên event chứa request/user ID | Cardinality không kiểm soát | Event code cố định, ID là field |
| Mọi tầng log cùng exception | Trùng stack trace và alert | Boundary ownership, giữ cause |
| Dump DTO/exception/raw payload | Lộ dữ liệu cá nhân và secret | Allowlist, redaction, kiểm thử |
| Sampling mọi loại như nhau | Rơi event an ninh quan trọng | Sampling theo nhóm/contract |
| Chỉ log, không metric/trace | Khó phát hiện xu hướng và phạm vi | Kết hợp tín hiệu phù hợp |
| Logger không throw là audit đã lưu | Backend có thể drop/ghi lỗi | ACK, queue bền, integrity, retention |
| Đổi field nhưng không version | Gãy dashboard và parser | Event catalog + contract tests |

## 15. Checklist thiết kế logging

- [ ] Biết mục đích và người sử dụng từng event.
- [ ] Chọn các hành động/quyết định/thay đổi/tình trạng ảnh hưởng nghiệp vụ, bảo mật hoặc vận hành.
- [ ] Phân biệt attempt, decision, committed success, recovered, failed và unknown.
- [ ] Chốt event taxonomy ổn định và schema có version.
- [ ] Xác định tầng sở hữu outcome và thời điểm phát sau commit/ack thích hợp.
- [ ] Cân nhắc outbox/durability riêng với event bắt buộc không mất.
- [ ] Chọn severity theo tác động, không chỉ vì có exception.
- [ ] Dùng correlation/event ID hợp lý; tránh metric high-cardinality.
- [ ] Tối thiểu hóa dữ liệu, không ghi secret/raw payload.
- [ ] Cấu hình sampling, retention, routing và quyền đọc theo loại.
- [ ] Kết hợp logs, metrics, traces và audit theo mục đích.
- [ ] Test schema, số event, outcome, privacy và pipeline khi cần.

### Tự kiểm tra

**Câu 1.** `ORDER_CREATED` quan trọng nhưng thường `INFO` vì sao?  
**Đáp:** Vì nó là kết quả thành công, không phải lỗi vận hành. Độ quan trọng và severity là hai trục khác nhau.

**Câu 2.** Request timeout lần đầu nhưng retry sau thành công: có phải đã có terminal failure không?  
**Đáp:** Không. Có thể ghi retry event/metric, nhưng terminal outcome là thành công hoặc recovered theo contract.

**Câu 3.** Ghi `ORDER_CREATED SUCCESS` trước DB commit có nguy cơ gì?  
**Đáp:** Transaction rollback khiến log nói sai trạng thái thực. Cần ghi đúng điểm xác nhận hoặc dùng outbox khi cần bảo toàn.

**Câu 4.** Security denial có thể quan trọng dù HTTP 403 là expected không?  
**Đáp:** Có. Nó có thể cần audit record theo policy nhưng không biến mọi 403 thành `SEVERE`.

**Câu 5.** Đã gọi `logger.info("ROLE_GRANTED")` có chứng minh đã có audit log bất biến chưa?  
**Đáp:** Chưa. Cần đảm bảo nguồn outcome, delivery, integrity, quyền đọc và retention.

**Câu 6.** Tại sao không đưa ID đơn hàng vào event name hoặc metric label?  
**Đáp:** Tạo cardinality rất lớn, khó tổng hợp và tăng rủi ro dữ liệu; nên để ID ở field log có kiểm soát.

**Câu 7.** Khi đổi event code hoặc kiểu field, việc cần làm là gì?  
**Đáp:** Cập nhật schema/version, dashboard, alert, consumer và contract tests.

**Ghi nhớ:** Xác định sự kiện quan trọng là **thiết kế một hợp đồng quan sát**, không phải thêm log ở mọi chỗ. Hãy chọn sự kiện có người dùng và mục đích rõ, phản ánh đúng outcome, phát ở boundary phù hợp, dùng tên/schema ổn định, kiểm soát riêng tư và khả năng lưu giữ. Khi đó Java logging mới thực sự hỗ trợ điều tra và vận hành production.

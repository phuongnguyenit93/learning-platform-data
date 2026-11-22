# Chọn cách kiểm thử cho chiến lược Java Logging

## 1. Mục tiêu: chọn bài test phù hợp thay vì kiểm thử mọi thứ cùng một cách

Trong Java, logging vừa là một **giao diện chẩn đoán** cho người vận hành, vừa là một **pipeline dữ liệu** chạy xuyên từ JVM tới appender, agent, collector và backend. Mỗi lỗi xảy ra ở một lớp khác nhau: thiếu eventCode, sai requestId trong MDC, JSON formatter lỗi, queue async mất log, collector không nhận, hoặc audit log ghi sai kết quả nghiệp vụ.

Vì thế, chủ đề **chọn cách kiểm thử** trong **thiết kế chiến lược log** không phải đơn giản “viết một unit test cho câu logger.info()”. Mục tiêu là xác định **thuộc tính nào phải đúng, lỗi đó có thể xuất hiện ở boundary nào, và loại test rẻ nhất nhưng đủ chứng minh thuộc tính ấy là gì**.

Ví dụ những câu hỏi khác nhau:

- Có cần kiểm tra logic quyết định ghi WARN khi retry hay ERROR khi thất bại cuối?
- Có cần bảo đảm event có trường **eventCode, requestId, outcome** đúng?
- Có cần kiểm tra formatter JSON, encoding UTF-8, timestamp hoặc stack trace?
- Có cần khẳng định MDC không rò giữa hai request dùng chung thread pool?
- Có cần xác minh async appender không mất sự kiện quan trọng khi queue đầy?
- Có cần chứng minh agent/collector chuyển sự kiện tới backend và tìm kiếm được?
- Event có bị lộ PII hoặc token qua Throwable, payload hoặc logger của thư viện?
- Với **audit**, cần cam kết persistence, completeness và bằng chứng toàn vẹn ở mức nào?

Không có một loại test duy nhất trả lời tất cả. **Unit test nhanh có thể chặn lỗi schema; integration test kiểm encoder/provider; end-to-end test kiểm đường vận chuyển; fault-injection test kiểm behavior khi hệ thống lỗi; security test chặn rò dữ liệu.** Chọn kết hợp dựa trên rủi ro và độ tin cậy yêu cầu.

## 2. Bắt đầu từ logging contract, không bắt đầu từ framework test

Trước khi viết JUnit hoặc gắn ListAppender, hãy định nghĩa **logging contract**. Một contract tốt mô tả được:

| Thành phần | Câu hỏi |
| --- | --- |
| **Event** | Khi điều kiện nghiệp vụ nào xảy ra thì phát log gì? |
| **Severity** | TRACE/DEBUG/INFO/WARN/ERROR được dùng theo chính sách nào? |
| **Schema** | Event có eventCode, outcome, errorCode, duration và version không? |
| **Context** | requestId/traceId/messageId từ đâu, có hợp lệ không? |
| **Privacy** | Field nào được phép, field nào phải omit/redact? |
| **Exception** | Khi nào giữ stack trace, khi nào chỉ giữ exceptionType? |
| **Delivery** | Khi nào event được xem là đã ghi ở appender hay backend? |
| **Retention** | Loại event nào cần lưu, bao lâu và ở kho nào? |
| **Operational use** | Query, dashboard, alert hoặc audit control nào dựa vào event? |

Ví dụ contract cho một event:

~~~yaml
eventCode: INVENTORY_RETRY_SCHEDULED
level: WARN
trigger: "dependency call fails transiently and a retry is scheduled"
required:
  - eventCode
  - requestId
  - dependencyName
  - attemptNo
  - errorCode
forbidden:
  - authorization
  - cookie
  - rawRequestBody
  - email
outcome: "PENDING_RETRY"
~~~

Đây là YAML **minh họa chính sách của ứng dụng**, không phải cú pháp chuẩn tự động của SLF4J. Muốn có hiệu lực, contract phải được thực thi bằng code/schema validation, test và cấu hình sink.

Nếu trigger thực tế là “đã lên lịch retry” mà code ghi event ngay khi bắt được exception, một unit test có thể PASS về tên chuỗi nhưng không bảo đảm **event đúng thời điểm**. Do đó, kiểm thử cả **điều kiện phát** lẫn **dữ liệu phát**.

## 3. Phân lớp kiểm thử để chọn đúng nơi xác minh

Một mô hình tham khảo:

~~~text
            E2E / canary / production smoke
          (few, slower, realistic delivery)
                     /\
                    /  \
         Integration + fault injection
     (provider, encoder, async, collector)
                  /        \
                 /          \
       Unit contract + state + fixtures
     (many, fast, deterministic assertions)
                  |
           Static review / lint
         (broad coverage, low cost)
~~~

Các lớp không tạo thành tỷ lệ bắt buộc. Chúng có **mục tiêu khác nhau**:

| Lớp | Test được | Không chứng minh |
| --- | --- | --- |
| **Static checks** | API nguy hiểm, logger format, cấu hình thiếu quy tắc | Event runtime thật sự có dữ liệu đúng |
| **Unit tests** | Trigger, field selection, classification, level, redaction | Encoder/collector hoạt động |
| **Provider integration** | Logback/JUL/Log4j event, MDC, encoder, appender | Backend đã lưu |
| **Transport/pipeline integration** | Queue, retry, TLS, routing, parsing | Business event gốc luôn được tạo |
| **End-to-end/canary** | Event xuất hiện và truy vấn được tại backend | Tất cả concurrency/error scenarios |
| **Resilience/performance** | Backpressure, drops, shutdown/rotation, tải | Tính đúng nghiệp vụ ở mọi đường |
| **Security/privacy** | Không lộ dữ liệu qua những sink kiểm tra | Không có bất kỳ PII nào trong mọi trường hợp |

**Không đẩy mọi assertion vào E2E** chỉ vì E2E “giống thật”. Lỗi tên eventCode nên bắt trong unit test nhanh; E2E dành cho điều chỉ lộ ra khi nhiều thành phần kết nối.

## 4. Quy tắc chọn test từ thuộc tính cần bảo đảm

Dùng câu hỏi **“nếu lỗi xảy ra, lớp nào có thể quan sát lỗi chính xác nhất?”**

| Yêu cầu | Lựa chọn ưu tiên | Bổ sung khi cần |
| --- | --- | --- |
| Log đúng level khi lỗi cuối | Unit test trên decision/event policy | Capture event của provider |
| Có đúng eventCode, status | Unit schema test | JSON output test |
| Không chứa password/token | Unit negative test cho allowlist | Integration qua Throwable, MDC, agent |
| Không rò MDC khi thread pool reuse | Concurrency unit/integration với executor | HTTP/message consumer integration |
| JSON có field và escape hợp lệ | Encoder integration parse JSON | Collector schema E2E |
| Stack trace là một event | Formatter/multiline parser integration | Host agent canary |
| Khi logger disabled không format đối tượng tốn kém | Unit/integration side-effect test | Benchmark dưới cấu hình thực |
| Async queue đầy thì xử lý đúng policy | Fault-injection/load test | Monitoring của backend |
| Collector nhận sự kiện | E2E synthetic canary | Truy vấn backend + ingest latency |
| Audit bắt buộc không mất khi crash | Transaction/outbox/store integration | Failure recovery và đối soát |
| Sampling không bỏ audit | Config/policy test | Canary qua pipeline |
| Thay phiên bản Logback/encoder không phá schema | Contract/integration regression | Staging release smoke |

**Một logging strategy hoàn chỉnh cần cả các test âm tính** (điều không được xuất hiện) **và dương tính** (điều bắt buộc phải xuất hiện). Một filter xóa toàn bộ logs có thể khiến test “không lộ token” PASS, nhưng hệ thống quan sát trở nên vô dụng.

## 5. Chấm rủi ro trước khi phân bổ test budget

Không phải event nào cũng có mức rủi ro như nhau. Có thể dùng ma trận nhỏ:

| Loại log | Hậu quả nếu sai/mất | Mức test đề xuất |
| --- | --- | --- |
| DEBUG tạm thời cho code nội bộ | Thấp nếu không chứa dữ liệu nhạy cảm | Static + unit cho helper quan trọng |
| INFO lifecycle của API quan trọng | Khó điều tra khi sai ID/outcome | Unit + provider/encoder integration |
| ERROR dùng cho alerting và SLO | Mất cảnh báo hoặc cảnh báo giả | Contract + formatter + canary |
| Correlation/tracing liên service | Không dựng được timeline incident | Unit MDC + integration propagation + E2E trace |
| Log bảo mật/PII-sensitive | Lộ dữ liệu và mở rộng phạm vi truy cập | Negative privacy + integration mọi sink |
| Audit compliance và giao dịch quan trọng | Có thể thiếu bằng chứng hoặc sai lịch sử | Transaction/recovery/integrity + E2E reconciliation |
| Logging tải rất cao | Nguy cơ queue đầy, tăng latency | Load/backpressure + resource monitoring |

Một công thức tư duy đơn giản: **ưu tiên = hậu quả khi sai × khả năng lỗi × độ khó phát hiện sau deploy**. Đây là heuristic để sắp thứ tự công việc, **không phải công thức định lượng pháp lý**. Cùng một hệ thống, audit/payment security thường cần lớp bảo vệ hơn debug log mang tính tùy chọn.

Bài test đắt nhưng chỉ xác minh một chuỗi text hiếm dùng nên đứng sau bài test rẻ kiểm tra eventCode mà alert production thực sự phụ thuộc.

## 6. Phân biệt “đúng event” và “đúng transport”

Hãy xét sự kiện **PAYMENT_FAILED**. Có ít nhất bốn nơi có thể sai:

~~~text
Business outcome FAILED
           |
           v
Event constructed with correct code/fields
           |
           v
Logger/provider constructs log event
           |
           v
Encoder/appender writes bytes
           |
           v
Agent/collector routes and stores event
~~~

Unit test **construct event** xác minh code/data. Provider integration kiểm event nhận được trong appender. Encoder test kiểm bytes/JSON. E2E test kiểm backend có record tìm được.

Một event có thể đúng ở tầng app nhưng mất do async appender full queue. Ngược lại, backend có thể lưu một event sai: E2E chỉ tìm thấy eventCode không chứng minh business outcome thực.

Nên định nghĩa **acceptance point** cho từng mục tiêu:

- **Logger call happened:** ứng dụng đã thử phát event.
- **Appender accepted:** provider/appender đã nhận event theo API.
- **Local durable:** file/WAL đã ghi bền vững theo contract.
- **Collector accepted:** remote endpoint trả ACK theo protocol.
- **Backend searchable:** query tìm thấy event đã ingest.

Các mốc này khác nhau. Không viết test “log đã lưu” chỉ bằng Mockito verify(logger). Mockito có thể chứng minh lời gọi, không tự kiểm transport/durability.

## 7. Static checks: chọn khi nguy cơ nằm trong code hoặc cấu hình

Static analysis phù hợp để phát hiện sớm các mẫu phổ biến mà không cần chạy ứng dụng:

- Logger truyền **raw request, response, headers, password, DTO chứa PII**, hoặc exception text chưa kiểm soát.
- Ghép chuỗi tốn kém thay vì parameterized logging ở đường nóng.
- **MDC.put** nhưng thiếu try/finally hoặc close đúng scope.
- Dynamic level DEBUG/TRACE được bật rộng ở production.
- Logger name, marker hoặc eventCode không theo convention.
- Test code có quá nhiều appender global mà không teardown.
- Quên giới hạn log length/size khi nhận user-controlled input.
- Encoder/config có khả năng xuất toàn bộ MDC hoặc SQL bind values.
- Logging dependency có nhiều provider/binding xung đột.

Các rule này **không đủ để kết luận an toàn**. Một biến tên “payload” có thể chỉ chứa thông tin vô hại, trong khi biến tên “details” có thể chứa token. Vì vậy static rules cần severity và exception process hợp lý, tránh block mọi pull request bằng false positives.

Khi tổ chức duy trì event schema registry, có thể kiểm tra tên eventCode theo enum/allowlist ngay khi compile hoặc chạy test. Nên ưu tiên invariant có thể áp máy hơn là style text chung chung.

## 8. Unit test: kiểm quyết định phát event

Ví dụ luồng retry:

~~~text
Dependency fails on attempt 1 -> schedule retry -> WARN
Dependency fails on final attempt -> operation failed -> ERROR
Dependency recovers -> operation completed -> INFO
~~~

Không thể kiểm tra policy bằng một test “logger.warn() được gọi một lần” nếu không kiểm điều kiện và fields.

Một unit test tốt nên:

1. Inject dependency giả để tạo đúng branch.
2. Gắn requestId/eventId xác định.
3. Gọi method một lần.
4. Capture **event object hoặc lời gọi logger** ở boundary cho phép.
5. Assert eventCode, level, outcome, errorCode và attemptNo.
6. Assert **không phát terminal-failure event** khi sẽ retry.
7. Assert không log raw secret/PII.
8. Kiểm tra cả case success, expected failure, unexpected exception.

**Không test toàn bộ prose của human-readable message** nếu nó không phải contract. Việc đổi dấu câu nên không làm hàng trăm tests fail, trong khi đổi eventCode mà alert dùng phải bị bắt ngay.

Nếu dùng facade tự định nghĩa như AuditEventPublisher/DiagnosticEventSink, unit test có thể capture typed event trực tiếp thay vì phụ thuộc implementation của logger. Nhưng phải có integration test riêng để chứng minh adapter chuyển typed event thành log đúng.

## 9. Java 17 runnable: chọn và thực thi ba loại kiểm tra

Chương trình độc lập sau dùng **java.util.logging (JUL)** trong JDK 17, không yêu cầu Maven hoặc thư viện ngoài. Nó mô phỏng ba tiêu chí thường chọn trước tiên:

- **Unit contract:** event theo allowlist, định dạng và requestId hợp lệ.
- **Handler capture:** hai event tới provider handler với level chính xác.
- **Privacy negative:** secret không xuất hiện và input chứa newline không chèn được dòng log.

Tạo file **LoggingTestChoiceDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingTestChoiceDemo {
    private static final Pattern REQUEST_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    enum EventCode { LOGIN_DENIED, OPERATION_FAILED }

    static final class CaptureHandler extends Handler {
        final List<String> messages = new ArrayList<>();
        final List<Level> levels = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                messages.add(record.getMessage());
                levels.add(record.getLevel());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    private static String safeId(String raw) {
        return raw != null && REQUEST_ID.matcher(raw).matches()
                ? raw : "invalid";
    }

    private static String event(EventCode code, String requestId,
                                String outcome) {
        return "event=" + code.name().toLowerCase(Locale.ROOT)
                + " requestId=" + safeId(requestId)
                + " outcome=" + outcome;
    }

    private static void check(String name, boolean passed) {
        if (!passed) {
            throw new AssertionError(name);
        }
        System.out.println(name + "=PASS");
    }

    public static void main(String[] args) {
        String email = "alice@example.test";
        String token = "Bearer synthetic-secret";
        String first = event(EventCode.LOGIN_DENIED, "req-42", "DENIED");
        String second = event(EventCode.OPERATION_FAILED,
                "req-43\r\nERROR forged=1", "FAILED");

        boolean contract =
                first.equals("event=login_denied requestId=req-42 outcome=DENIED")
                && second.equals(
                        "event=operation_failed requestId=invalid outcome=FAILED");

        Logger logger = Logger.getLogger("learning.logging.testchoice");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        CaptureHandler handler = new CaptureHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);
        try {
            logger.log(Level.INFO, first);
            logger.log(Level.WARNING, second);

            boolean captured =
                    handler.messages.size() == 2
                    && handler.levels.get(0) == Level.INFO
                    && handler.levels.get(1) == Level.WARNING
                    && handler.messages.get(0).equals(first)
                    && handler.messages.get(1).equals(second);

            String combined = String.join("|", handler.messages);
            boolean privateFieldsAbsent =
                    !combined.contains(email)
                    && !combined.contains(token)
                    && !combined.contains("\r")
                    && !combined.contains("\n");

            check("unitContract", contract);
            check("handlerCapture", captured);
            check("privacyNegative", privateFieldsAbsent);
            System.out.println("summary=3/3");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy với JDK 17:

~~~bash
javac LoggingTestChoiceDemo.java
java LoggingTestChoiceDemo
~~~

**Stdout chính xác** nếu chương trình chạy thành công:

~~~text
unitContract=PASS
handlerCapture=PASS
privacyNegative=PASS
summary=3/3
~~~

Giải thích:

1. Enum **EventCode** ngăn tên sự kiện được lấy trực tiếp từ raw user input.
2. **safeId** dùng regex allowlist và giới hạn độ dài; input chứa CR/LF trở thành invalid thay vì phá text log.
3. Handler giữ String và Level, vì vậy **không phụ thuộc formatter mặc định có timestamp không xác định**.
4. **unitContract** xác nhận policy tạo tên event và outcome mong đợi.
5. **handlerCapture** xác nhận chính JUL handler đã thấy hai event với INFO/WARNING.
6. **privacyNegative** xác nhận email/token mẫu không xuất hiện và không có CR/LF trong captured messages.
7. Đây là **test logic minh họa**, không dùng real HTTP request, file appender, JSON, async queue hay collector; chưa chứng minh mọi PII đều bị chặn.
8. **ArrayList** trong handler không thread-safe; ví dụ chạy tuần tự. Khi test concurrent logging phải dùng cấu trúc hoặc synchronization phù hợp.
9. Không có assertion về **log record durability**; Handler trong memory không thể thay thế E2E canary.
10. Dù biểu thức privacyNegative đúng, một logger khác trong ứng dụng vẫn có thể làm rò dữ liệu. Cần kiểm tích hợp toàn pipeline với secret giả ở các nguồn rủi ro.

Đây là ví dụ **chọn test có mục tiêu**: ba bài kiểm tra đều có ý nghĩa riêng, không lặp ba lần cùng một assertion trên chuỗi. Khi cần kiểm formatter hoặc transport, phải chọn test ở lớp kế tiếp.

## 10. Mock logger hay capture event thật?

Khi viết unit tests, hai cách phổ biến:

| Cách | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Mockito/mock logging facade | Kiểm tra method, args, level và số lần gọi nhanh | Không xác minh provider, MDC snapshot hoặc output |
| In-memory appender/handler | Chụp event thật của backend | Coupled với provider và test fixture |
| Fake typed event sink | Xác minh event contract độc lập logger implementation | Cần integration test chuyển event sang logger |
| JSON encoder sink | Kiểm output serialized schema | Setup phức tạp hơn unit |
| Real collector test | Xác minh hệ thống kết nối end-to-end | Chậm và dễ phụ thuộc mạng |

Nếu mục tiêu là **“đúng business branch phát đúng event”**, mock/fake typed sink hợp lý. Nếu mục tiêu là **“Logback event chứa requestId”**, một mock không giúp được nhiều; dùng appender capture hoặc encoder. Nếu mục tiêu là **“dashboard truy xuất được trace”**, phải có integration/E2E.

**Đừng chọn công cụ test vì dễ viết mock nhất.** Chọn điểm quan sát phản ánh sự thật bạn muốn chứng minh.

## 11. Test trực tiếp Logback: bảo vệ snapshot MDC

Với SLF4J + Logback, một event được tạo trên request thread có thể được format muộn bởi async appender. Bài test nên capture **MDC của chính event**, không đọc MDC.get của thread test sau khi event đã phát.

Mẫu appender tích hợp với Logback (không phải chương trình standalone; yêu cầu dependency Logback, SLF4J và fixture JUnit):

~~~java
final class ContextCaptureAppender
        extends ch.qos.logback.core.AppenderBase<
                ch.qos.logback.classic.spi.ILoggingEvent> {

    final java.util.List<java.util.Map<String, String>> snapshots =
            new java.util.concurrent.CopyOnWriteArrayList<>();

    @Override
    protected void append(
            ch.qos.logback.classic.spi.ILoggingEvent event) {
        event.prepareForDeferredProcessing();
        java.util.Map<String, String> mdc = event.getMDCPropertyMap();
        snapshots.add(mdc == null
                ? java.util.Map.of()
                : java.util.Map.copyOf(mdc));
    }
}
~~~

Một JUnit test tương ứng:

1. Tạo **logger name riêng**, tắt additivity nếu cần và attach appender đã start.
2. Đặt MDC requestId=req-A, log một event.
3. Đổi MDC requestId=req-B, log event thứ hai.
4. Clear/restore MDC trong finally.
5. Assert snapshot của event A vẫn là req-A, của event B là req-B.
6. Detach/stop appender và restore level/additivity trong teardown.

**prepareForDeferredProcessing** và **Map.copyOf** giúp chụp dữ liệu event ở thời điểm phù hợp, giảm lỗi lazy read. Tuy nhiên đây là kỹ thuật **Logback-specific**; khi dùng Log4j 2 hoặc adapter khác cần test theo API phù hợp. Không dùng MDC.clear() của test thread để giả định worker thread khác cũng sạch.

## 12. Cách chọn test cho MDC và async context

MDC thường gắn với thread hiện tại. Các boundary cần kiểm tra riêng:

| Bối cảnh | Lựa chọn test | Assertion quan trọng |
| --- | --- | --- |
| HTTP filter/interceptor | Request integration + event capture | Trong request có ID; sau request restore |
| Nested service method | Unit scope test | Inner scope không xóa outer requestId |
| ExecutorService | Single-thread pool regression | Task B không kế thừa task A |
| CompletableFuture async | Test-owned executor + wrapper/decorator | Capture/activate/restore đúng |
| Message consumer | Consumer integration | ID theo delivery, không rò giữa messages |
| Reactor/WebFlux | Context propagation integration | Thread switch không làm sai correlation |
| Scheduled job | Job lifecycle test | jobId có trong stage đúng và cleanup |
| AsyncAppender | Snapshot/flush test | Event giữ ID lúc phát dù caller đổi MDC |

Một test thread reuse có thể tạo **một worker duy nhất**, chạy task A và B nối tiếp, rồi kiểm tra event của từng task. Nếu chạy trên pool nhiều threads nhưng không điều khiển scheduler, test có thể pass ngẫu nhiên do hai task tình cờ không reuse cùng worker.

Dùng Future.get(), CountDownLatch hoặc CyclicBarrier có deadline phù hợp. **Không dùng Thread.sleep làm cách đồng bộ duy nhất**; test dễ flaky trên CI.

**MDC putCloseable không mặc định khôi phục nested previous value.** Nếu code ghi đè requestId đang tồn tại, test cần xác nhận helper lưu previous và restore trong finally, chứ không chỉ remove.

## 13. Chọn test formatter, JSON và schema evolution

Nếu backend truy vấn theo JSON fields, hãy test **serialized bytes hoặc JSON object**, không chỉ event trên logger.

Ví dụ contract:

~~~json
{
  "timestamp": "2026-11-10T03:10:00Z",
  "level": "WARN",
  "service": "payment-api",
  "eventCode": "DEPENDENCY_TIMEOUT",
  "requestId": "req-42",
  "errorCode": "INVENTORY_TIMEOUT",
  "durationMs": 1200
}
~~~

JSON trên là ví dụ, không phải output tự động của một thư viện. Integration test nên:

1. Dùng cùng encoder/version sẽ chạy production.
2. Gắn output vào buffer/file test được kiểm soát.
3. Phát các event hợp lệ và event thiếu optional fields.
4. Parse JSON, assert field **đúng tên, kiểu dữ liệu và giá trị**.
5. Kiểm schemaVersion và backward compatibility cho dashboards.
6. Test newline, quote, Unicode, stacktrace và null/empty values.
7. Xác minh timestamp có timezone hoặc UTC theo contract.
8. Test không xuất token/PII ngoài policy.

**Tìm substring không đủ:** requestId có thể có trong message nhưng thiếu structured field, hoặc xuất hai lần ở vị trí sai. Với JSON, parse và assert object shape.

Khi schema version thay đổi, test cả consumer/parser downstream hoặc có canary. Một PR đổi key **errorCode → error_code** có thể hợp lý trong code nhưng làm alert cũ bị mù; cần regression contract.

## 14. Chọn test cho exception và log level

Một chiến lược log thường muốn:

- Expected validation failure: WARN hoặc INFO tùy policy, không spam stacktrace.
- Retryable dependency failure: WARN có attemptNo và retryScheduled.
- Terminal operation failure: ERROR với errorCode/traceId.
- Internal unexpected exception: ERROR với exceptionType và stacktrace được kiểm soát.
- Successful fallback: event xác nhận outcome thành công, không bị hiểu là terminal error.

Test branch logic của level ở unit layer. Test cách Throwable được **serialize** trong integration layer. Hai điều này khác nhau: một mock verify logger.error(exception) không chứng minh formatter đã bảo vệ exception message có secret.

Với Java có nhiều lớp wrap exception, kiểm tra **cause chain** và field errorCode thay vì chỉ so khớp một tên exception. Không assert toàn bộ stack trace text vì line numbers và thứ tự frames có thể đổi theo compiler/JVM. Assert loại lỗi, marker/field cần thiết và **không rò dữ liệu thử nghiệm**.

**Log level không phải mã kết quả nghiệp vụ.** Có WARN tạm thời rồi COMPLETED thành công; đếm WARN bằng số requests thất bại là sai. Chọn test kiểm **terminal outcome** riêng với severity.

## 15. Chọn test cho log filtering, sampling và rate limit

Các hệ thống tải cao có thể giảm log volume bằng level, sampling hoặc rate limiting. Những thuộc tính cần kiểm:

- **DEBUG disabled**: không phát event debug tới appender; logic nóng không tốn serialization không cần thiết.
- **INFO sampling**: ratio hoặc rule được áp trong phạm vi có thể đo; không giả định mẫu ngẫu nhiên cho kết quả chính xác ở một test nhỏ.
- **ERROR always-on** theo policy: không bị filter ngoài ý muốn.
- **Audit mandatory**: không được sampling/drop bởi đường chẩn đoán nếu yêu cầu bảo đảm lưu.
- **Rate limiting**: một sự cố lặp lại không làm đầy disk, nhưng có counters/summary để biết bao nhiêu event bị giới hạn.
- **Per-logger overrides**: cấu hình production không mở logging thô của HTTP/ORM chứa PII.
- **Dynamic config**: khi bật/tắt DEBUG có phạm vi và tự phục hồi theo thời gian nếu có policy.

Một test xác suất **không nên assert đúng 50/100 events** trong một bộ random nhỏ nếu sampler không cung cấp seed hoặc deterministic mode. Thay vào đó unit test rule với sampler được inject deterministic, rồi load test đo tỷ lệ trong giới hạn thống kê hợp lý.

Không test “ngừng log” bằng việc kỳ vọng không có record khi pipeline đang đứt; phải biết liệu event bị lọc chủ đích hay collector bị lỗi.

## 16. Chọn test cho privacy và security

Với PII/secret, nên ưu tiên **negative tests nhiều nguồn**:

| Nguồn rủi ro | Test nên có |
| --- | --- |
| HTTP body/headers/query | Inject email/token giả, assert mọi sink không có raw secret |
| DTO.toString | Thêm field PII mới, event allowlist không bị mở rộng |
| MDC | Context không chứa email/password/cookie |
| Throwable | Exception message giả chứa token không lọt sink ngoài |
| ORM bind parameters | TRACE/DEBUG không dump raw values ngoài policy |
| Kafka/RabbitMQ payload | Retry/error/DLQ logs không chứa payload bí mật |
| APM/tracing attributes | Span/log correlation không copy raw PII |
| Access/export | Unauthorized role không thể xem dữ liệu nhạy cảm |
| Encoder + collector | JSON escaping/redaction không bị bypass |
| Backup/archive | Retention và quyền đọc phù hợp |

**Không test bằng credential thật.** Dùng giá trị giả, nhận dạng rõ như synthetic token. Positive assertion phải chứng minh eventCode, status, requestId vẫn tồn tại để log không bị vô hiệu hóa.

Regex redaction không thể bảo đảm phát hiện mọi biến thể PII: URL encoding, nested JSON, Unicode và nội dung tự do có thể bypass. Kiến trúc ưu tiên **omit/allowlist ngay tại Java source**, redaction ở encoder/collector chỉ là lớp bổ sung.

**Masking không đồng nghĩa anonymization**. Một customerId hoặc hash có thể còn linkable, cần xác định policy về truy cập và retention.

## 17. Chọn test cho log forging và input không tin cậy

Một requestId hoặc field từ client có thể chứa CR/LF để giả mạo dòng:

~~~text
req-42
ERROR user=admin event=payment_approved
~~~

Test cần tạo input với newline, tab, quote, Unicode control, chuỗi rất dài và các ký tự parser đặc biệt. Bài test không chỉ assert “formatter không crash”, mà còn kiểm:

1. Raw user input không được dùng làm eventCode/level.
2. requestId có grammar và giới hạn độ dài.
3. JSON/text encoder escape theo sink, không cho một field thành hai records.
4. Parser agent/collector vẫn nhận đúng **một event logic** khi payload string chứa newline.
5. Một event giả không xuất hiện trong kết quả truy vấn.
6. Raw PII/credential trong input không lọt output.

Với NDJSON, khi JSON serialization đúng, newline **trong string** được escape, không trở thành newline vật lý mới. Nếu dùng multiline text logs, test cấu hình parser của agent cùng format thật, không chỉ test regex trong Java.

**Không gọi JSON escaping là redaction**: escaping ngăn phá cấu trúc, còn redaction quyết định có được ghi nội dung hay không.

## 18. Chọn test cho AsyncAppender và backpressure

AsyncAppender hoặc queue của logging backend cho phép thread ứng dụng enqueue event và worker ghi sau. Lớp này cần test riêng vì event có thể mất do queue full hoặc shutdown.

Các tình huống:

| Tình huống | Test | Quan sát |
| --- | --- | --- |
| Caller đổi MDC ngay sau logger.info | Event snapshot | Output giữ ID tại thời điểm phát |
| Queue gần/full | Fault/load test | Block/drop/discard theo policy |
| Sink chậm | Backpressure test | Application latency và queue depth |
| Process shutdown bình thường | Flush/drain test | Những event đã chấp nhận được xử lý trong giới hạn |
| Abrupt crash | Recovery test | Mất dữ liệu theo contract, không giả định không mất |
| Output error/timeout | Retry policy test | Alert, buffer hoặc drop behavior |
| Throwable được format ở worker | Snapshot/formatter test | Không đọc context sai hoặc lộ raw secret |

Khi test queue overflow, cần **cấu hình nhỏ có chủ đích** để tái hiện, không cần sản sinh hàng triệu event rồi hy vọng tình huống xảy ra. Đặt số event, barrier chặn sink, kiểm bounded queue, sau đó nhả sink và đo accepted/dropped theo API hoặc metrics.

Một test không thấy dropped logs không chứng minh sẽ không drop ở production khi tải cao hơn; đây là nơi cần **load/performance test** bổ sung.

**Phân biệt diagnostic logs best effort với audit logs bắt buộc**. Không coi một queue async thông thường là durable audit store chỉ vì appender.start() thành công.

## 19. Chọn test cho collector, agent và lưu trữ cuối

Pipeline có thể là:

~~~text
Java logger -> stdout/file -> agent/DaemonSet
             -> collector/gateway -> index/archive
             -> query/dashboard/alert
~~~

Một **pipeline integration test** nên dùng nguồn và destination test ở môi trường được phép:

- Java phát một event synthetic có eventId/correlationId duy nhất và dữ liệu giả an toàn.
- Agent nhận từ stdout/rolling file đúng path và parser.
- Collector nhận event, không làm mất/đổi các field bắt buộc.
- Backend có thể truy vấn event trong giới hạn thời gian chấp nhận.
- Nếu có nhiều outputs, kiểm từng nhánh, không chỉ nhánh search.
- Khi backend lỗi, xem queue/retry/drop và tách **read offset** khỏi **delivery ACK**.
- Khi file rotate hoặc pod restart, xác minh recovery theo semantics đã mô tả.

**E2E canary cần một deadline hợp lý**; nếu collector còn backlog, một câu query trả rỗng ngay lập tức không chứng minh event mất. Có thể poll trong thời hạn test xác định rồi báo rõ **timeout/unverified**, không coi không thấy event là business failure chắc chắn.

Để giảm flakiness, dùng eventId unique, namespace/index riêng, cleanup test data và giải thích môi trường. Không đẩy raw PII vào production chỉ để kiểm logging.

## 20. Chọn test cho distributed tracing và correlation

Một log có traceId format hợp lệ chưa chứng minh distributed trace hoạt động. Với OpenTelemetry hoặc instrumentation tương thích, cần test:

1. Producer inject trace context khi gửi HTTP/message.
2. Consumer extract context đúng từ headers theo propagator.
3. Span tạo ra có quan hệ parent/child hoặc link theo model của framework.
4. Log được gắn **traceId/spanId thực**, không chỉ chuỗi random có tên giống.
5. MDC được restore khi request/task kết thúc, không leak sang request sau.
6. Trace backend tìm được spans liên quan trong giới hạn sampling/retention.
7. EventCode và correlationId của app vẫn đúng khi trace sampling tắt một số spans.

**Logging correlation và distributed tracing là hai hợp đồng riêng.** Test MDC trên một thread là cần thiết nhưng không đủ để chứng minh propagation qua network. Một span bị sampling không đồng nghĩa nghiệp vụ chưa chạy.

Với asynchronous messaging, span link có thể phù hợp hơn quan hệ parent-child ở một số mô hình; test theo semantic convention của instrumentation thật, không ép một cây trace duy nhất cho mọi workflow fan-out.

## 21. Chọn test cho audit và event bắt buộc

Audit có yêu cầu cao hơn diagnostic logs. Một audit event có thể cần:

- Tạo cùng thời điểm business transaction được cam kết đúng contract.
- Lưu bền vững hoặc được chấp nhận trong outbox bền vững trước khi trả kết quả.
- Có eventId, actor/action/resource/outcome chuẩn hóa.
- Có cơ chế idempotency để retry không tạo lịch sử giả.
- Không thể sửa/xóa ngoài chính sách, có retention/permission.
- Có hash/signature/checkpoint nếu threat model yêu cầu tamper evidence.
- Có đối soát completeness và alert khi audit pipeline unavailable.

Chọn test **transaction integration + failure injection + storage policy + reconciliation**, không dừng ở mock logger.

Một test quan trọng: business update commit nhưng publish audit gặp lỗi. Hệ thống phải **fail-closed** hoặc giữ event trong durable outbox theo policy, không âm thầm ghi WARN rồi coi là đã bảo đảm audit. Ngược lại, audit SUCCESS ghi trước transaction rollback có thể tạo lịch sử sai.

**Hash chain verify=true không chứng minh tất cả event đã được tạo**, nhất là khi xóa phần đuôi hoặc không có checkpoint ngoài. Muốn kiểm tính đầy đủ phải so với expected sequence/nguồn nghiệp vụ.

## 22. Chọn test cho hiệu năng và tính sẵn sàng

Logging có thể gây overhead đáng kể trên đường nóng:

- Tính toán argument đắt khi level disabled.
- JSON serialization và Throwable stacktrace lớn.
- MDC map copy trên thread pool/concurrency.
- Lock contention trong synchronous appender.
- Async buffer và context switching.
- File I/O, disk pressure, agent/collector network.
- Rối loạn do log storm trong một dependency outage.

**Microbenchmark** có thể đo chi phí format/logging call khi cấu hình được kiểm soát, nhưng không thay load test qua pipeline thật. Với JVM, JIT warm-up, allocation, GC, disk cache và scheduler có thể làm kết quả naive benchmark sai.

Đề xuất ba tầng:

1. **Unit/perf guard:** xác nhận đường disabled không gọi supplier/serializer nặng nếu API hỗ trợ lazy computation.
2. **Focused benchmark:** dùng JMH hoặc benchmark harness phù hợp cho chi phí một hàm/logging wrapper.
3. **Load/integration:** đo throughput, p95/p99 latency, allocation, GC, queue depth, disk bytes và dropped events khi backend chậm.

Không tự đặt một ngưỡng toàn cục kiểu “logging dưới 1ms” nếu chưa có SLO và baseline. Ngưỡng nên theo workload, hạ tầng, level mix và error rate thực tế.

**Không hi sinh privacy hoặc audit completeness để vượt performance test.** Chọn chính sách log budget theo loại event.

## 23. Property-based, mutation và regression tests

Ngoài happy path, hãy kiểm tra nhiều biến thể dữ liệu để tìm lỗi mà ví dụ đơn lẻ không bắt được:

- **Property-based tests:** với một tập request IDs hợp lệ, event output vẫn parse được và key schema không đổi.
- **Fuzz tests:** input dài, Unicode, CR/LF, nested maps, null, malformed headers; parser không crash hoặc log secret.
- **Mutation tests:** nếu đổi eventCode, bỏ field bắt buộc, tắt cleanup MDC hoặc đảo level, có test fail đúng chỗ không?
- **Golden file/snapshot:** hữu ích cho JSON schema ổn định, nhưng tránh snapshot toàn timestamp, random UUID và stack trace biến động.
- **Compatibility tests:** chạy schema cũ/mới với collector config tương ứng trong staging.
- **Security regression:** khi thêm DTO field nhạy cảm mới, allowlist không tự mở rộng.
- **Concurrency regression:** nhiều tác vụ xen kẽ không trộn ID hoặc làm rơi event ngoài contract.

**Đừng viết snapshot quá rộng rồi cập nhật hàng loạt mỗi khi refactor.** Nếu snapshot thay đổi nhưng không ai hiểu ý nghĩa, test trở thành rào cản hình thức. Snapshot nên mô tả **contract field names/types**, không đóng băng chi tiết trang trí.

## 24. CI: chọn suite theo tốc độ và độ tin cậy

Một chiến lược triển khai:

| Giai đoạn | Test nên chạy | Lý do |
| --- | --- | --- |
| Local/pre-commit | Static checks + unit contract/privacy | Nhanh, phản hồi trực tiếp |
| Pull request CI | Unit + provider/encoder integration + MDC concurrency | Bắt lỗi thay code và dependency |
| Merge/release candidate | Collector/agent integration + compatibility | Bảo đảm pipeline cấu hình cùng phiên bản |
| Staging | E2E canary, crash/rotation/timeout, load subset | Thử hành vi gần production |
| Production smoke | Synthetic low-risk canary + health metrics | Theo dõi deployment không có bí mật |
| Scheduled drills | Audit recovery, spool full, failover, restoration | Kiểm các failure path hiếm nhưng quan trọng |

Không nhất thiết mọi suite chạy ở mỗi commit. **Một test E2E thường xuyên flaky làm chậm release** có thể hữu ích hơn nếu chuyển thành canary định kỳ với alert rõ, trong khi unit/schema tests vẫn bắt lỗi ở PR.

Nhưng đừng giảm coverage rủi ro cao chỉ để CI xanh: nếu quy định bắt buộc audit correctness, cần release gate đủ mạnh và có owner xử lý test hỏng.

Phải quản lý **test fixtures**: logger/appender global, random port, log storage, shared index và environment secrets. Unit tests không nên phụ thuộc backend production.

## 25. Tránh test flaky vì logging bất đồng bộ

Những nguồn flakiness thường gặp:

| Sai sót | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Assert ngay sau async logger.info | Queue chưa drain | Wait/flush theo API, bounded deadline |
| Dùng Thread.sleep(100) | Phụ thuộc scheduler CI | Latch/Future/condition có timeout |
| Assert thứ tự log giữa nhiều threads | Interleaving khác nhau | Nhóm theo ID, assert causal order cần thiết |
| Dùng root logger chung | Test khác thay level/appender | Logger riêng, restore config |
| Không stop/detach appender | Event trùng hoặc memory leak | Fixture teardown |
| Dùng timestamp thật trong exact stdout | Kết quả nondeterministic | Clock injection hoặc assert format/range |
| Random sampling không seed | Tỷ lệ dao động | Deterministic sampler ở unit |
| Dùng một index E2E chung | Dữ liệu test khác xuất hiện | Unique eventId và namespace |
| Chỉ clear MDC ở test thread | Worker còn context cũ | Clear/restore ngay trong task |
| Eventual consistency của backend | Query tạm rỗng | Poll có deadline và báo unverified |

Chọn test **chứng minh điều cần biết trong giới hạn biết rõ**, thay vì tăng số lần retry test cho đến khi may mắn PASS. Retry test có thể che bug thật của async ordering.

Trong test provider, phải hiểu **lazy event fields**. Ví dụ Logback ILoggingEvent có phương thức prepareForDeferredProcessing để chuẩn bị dữ liệu trước khi worker đọc; không giữ raw event rồi đọc MDC sau khi context bị clear mà không xét semantics backend.

## 26. Ma trận tình huống: nên chọn cách kiểm thử nào?

| Thay đổi đang thực hiện | Test bắt buộc đầu tiên | Test bổ sung có giá trị |
| --- | --- | --- |
| Thêm eventCode cho API | Unit event policy | JSON schema integration |
| Thay Logback pattern hoặc JSON encoder | Encoder integration | Dashboard/collector canary |
| Thêm requestId qua filter | Scope + event capture | HTTP concurrency/reuse |
| Chuyển xử lý sang CompletableFuture | Context propagation test | Trace integration |
| Đổi log level khi retry | Unit branch/terminal outcome | Alert aggregation regression |
| Thêm HTTP client wire logs | Privacy negative test | Staging secret canary tại mọi sink |
| Bật SQL DEBUG | Security review + controlled test | Resource/volume load test |
| Chuyển stdout sang rolling file | File/rotation integration | Agent tail + restart |
| Thay host agent/collector config | Pipeline integration | E2E synthetic query |
| Thêm AsyncAppender | Snapshot/queue overflow | Load + shutdown flush |
| Thay sampling policy | Deterministic policy test | Aggregate sampling/load canary |
| Chuyển trace instrumentation | Propagation integration | E2E span/log correlation |
| Thay audit storage/retention | Storage/write/read/recovery test | Integrity & completeness reconciliation |
| Incident postmortem yêu cầu điều tra nhanh hơn | Query/field contract test | Runbook drill trên synthetic event |

Nếu thời gian rất hạn chế, ưu tiên **không làm sai event chính, không rò dữ liệu, không mất MDC, không phá alert**, sau đó mở rộng tới các failure path vận hành tương ứng mức độ rủi ro. Đây là thứ tự gợi ý, không áp dụng cứng cho mọi tổ chức.

## 27. Khi nào test phải kiểm tra “không có log”?

Không phải mọi hành vi đều phải phát một event. **Negative logging contract** có giá trị khi muốn:

- Không log dữ liệu người dùng ở một path.
- Không log success ở ERROR.
- Không phát terminal failure khi retry đang được lên lịch.
- Không dump exception stack ở validation failure dự kiến.
- Không ghi DEBUG khi disabled theo chính sách.
- Không duplicate cùng audit event khi retry idempotent.
- Không đưa PII vào MDC, headers, structured arguments hoặc collector output.

Tuy nhiên, test “không có log” có hai cạm bẫy:

1. Nếu logger/appender không chạy, mọi negative tests đều PASS giả.
2. Nếu chỉ kiểm message string, field nhạy cảm có thể vẫn nằm trong structured fields/Throwable/MDC.

Bởi vậy phải có **positive control** trong cùng fixture: phát một event hợp lệ, xác nhận sink đã nhận, rồi mới assert dữ liệu bị cấm vắng mặt. Nếu không có positive control, test có thể chứng minh một pipeline chết chứ không phải policy đúng.

Đây là nguyên tắc quan trọng khi kiểm privacy, sampling và suppression.

## 28. Tiêu chí PASS và release gates

Một test tốt phải có **một câu PASS cụ thể**:

| Test | PASS khi |
| --- | --- |
| Unit event policy | Đúng eventCode, level, trigger, required fields, không có forbidden fields |
| MDC state | Scope restore chính xác, kể cả lỗi và nested call |
| Provider event | Appender capture đúng context/level/message |
| JSON schema | Parse được, fields đúng type, không lộ secret |
| Async resilience | Queue/flush/drop theo policy đo được |
| Pipeline integration | Event qua các stages đúng schema và route |
| E2E canary | Backend truy vấn được synthetic event trong SLA |
| Security negative | Tất cả sink được kiểm tra không chứa các canary secrets |
| Audit consistency | Business transaction/outbox và audit event đối soát hợp lệ |
| Performance | Resource/latency/drops đạt ngân sách đã duyệt |

Không viết PASS chung chung như “logging works” hoặc “không có ERROR”. Hãy ghi rõ **điều kiện thử, môi trường, bộ dữ liệu, ngưỡng, giới hạn và nguồn xác minh**.

Một release gate lỗi do collector tạm unavailable nên báo **INCONCLUSIVE/INFRA FAILURE** theo quy trình chứ không gán nhầm là lỗi business event contract; tuy vậy không được tuyên bố hệ thống đã kiểm chứng end-to-end khi thiếu dữ liệu. Các lỗi nội dung và lỗi công cụ phải được phân biệt.

## 29. Checklist lựa chọn chiến lược kiểm thử

| Câu hỏi | Nếu câu trả lời là Có |
| --- | --- |
| Event dùng cho alert hoặc vận hành quan trọng? | Thêm event contract + encoder/canary |
| Có dữ liệu PII/secret trong workflow? | Thêm negative security ở source và mọi sink |
| Có MDC hoặc context thay đổi thread? | Thêm scope/propagation/reuse tests |
| Có async appender hay buffering? | Thêm snapshot, overflow, flush, shutdown tests |
| Có external collector/agent? | Thêm pipeline + E2E canary |
| Có message brokers? | Thêm retry/redelivery/ACK correlation |
| Có audit bắt buộc? | Thêm transaction/recovery/completeness/integrity tests |
| Có log sampling/rate limiting? | Thêm policy + dropped-event visibility tests |
| Có schema được dashboard truy vấn? | Thêm compatibility/contract regression |
| Có thay đổi logger provider/version? | Chạy provider integration trên runtime thực |
| Có rủi ro performance? | Baseline benchmark và load test có kiểm soát |
| Test chạy song song trên CI? | Logger/fixtures được isolation và teardown |
| Có quyền truy cập log cho nhiều vai trò? | RBAC/retention/privacy integration tests |
| Có yêu cầu điều tra incident? | Thử runbook với event synthetic end-to-end |

**Kết luận:** chọn cách kiểm thử trong chiến lược Java Logging là **gắn thuộc tính cần bảo đảm với điểm quan sát đúng và mức rủi ro thực tế**. Kiểm event logic bằng unit tests; kiểm backend/appender/MDC/JSON bằng integration tests; kiểm collector và khả năng truy vấn bằng end-to-end canary; kiểm mất log, backpressure, retry và recovery bằng failure tests; kiểm privacy và audit bằng những test bảo đảm riêng. Một bộ test nhỏ nhưng có contract và coverage đúng chỗ đáng tin hơn một bộ test lớn chỉ lặp lại assert cùng một lời gọi logger.
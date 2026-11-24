# Giảm duplicate log trong Spring Boot

## 1. Mục tiêu và bối cảnh

Trong một ứng dụng Spring Boot, cùng một lỗi có thể được ghi nhiều lần: repository log exception, service bắt rồi log lại, controller advice tiếp tục log, và servlet container ghi thêm stack trace. Một request lỗi vì thế tạo nhiều bản ghi gần giống nhau. Khi hệ thống có nhiều service và retry, log volume tăng, chi phí lưu trữ tăng và tín hiệu quan trọng bị chìm trong dữ liệu lặp.

**Duplicate log** là những log records lặp lại hoặc gần giống nhau về sự kiện, ngữ cảnh và nội dung. Tuy nhiên, hai log có cùng message chưa chắc là duplicate: một request có thể đi qua nhiều bước hợp lệ, hoặc cùng một lỗi được quan sát ở hai service khác nhau. Mục tiêu là loại bỏ bản ghi dư thừa mà vẫn giữ thông tin cần thiết để điều tra.

Bài thuộc chương **Logging** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng thực tế.

Sau bài học, bạn có thể:
1. Nhận diện duplicate logs do exception nhiều tầng, framework instrumentation, retry hoặc nhiều appender.
2. Chọn đúng một nơi chịu trách nhiệm ghi stack trace đầy đủ.
3. Phân biệt log ở các boundary với log lặp trong cùng call path.
4. Thiết kế log level, message và structured fields để tránh lặp.
5. Sử dụng sampling/rate limiting cho sự kiện tần suất cao mà không che lỗi quan trọng.
6. Kết hợp logs với traceId/spanId, metrics và error counters.
7. Kiểm thử số lượng log và thông tin còn lại sau refactor.

**Baseline:** Spring Boot 3.x/4.x, Java 17+, SLF4J với Logback mặc định nếu không thay logging backend. Một số API/cấu hình phụ thuộc logging implementation; kiểm tra runtime dependency và cấu hình thực tế.

## 2. Phân biệt các dạng log lặp

| Dạng | Ví dụ | Cách nhận diện |
| --- | --- | --- |
| Cùng exception nhiều tầng | Repository log rồi service/controller log cùng throwable | Cùng exception/cause chain, cùng request |
| Caller và callee cùng log | Client wrapper log lỗi, service gọi nó log lại | Cùng lỗi lan truyền theo call stack |
| Access log chồng lặp | Gateway, servlet container và custom filter đều ghi request | Cùng method/path/status, khác logger |
| Retry logs | Mỗi attempt ghi cùng timeout | Attempt number khác nhau; có thể là event riêng |
| Instrumentation chồng lặp | Auto instrumentation cộng custom interceptor cùng log một call | Cùng operation, hai cơ chế |
| Nhiều appender | Logger con và root cùng ghi một event | Một event xuất hiện hai lần trong một process |
| Replayed message | Consumer nhận lại message sau redelivery | Delivery/attempt metadata khác nhau |
| Job/batch lặp | Job summary được ghi ở nhiều method con | Cần phân biệt một run với các run riêng |

### 2.1. Duplicate hay hai sự kiện hợp lệ?

So sánh thời điểm, traceId/spanId, request/correlation ID, logger name, service/pod, thread, exception class/cause chain, attempt number, message ID và appender.

Hai service cùng log một dependency failure có thể hữu ích: service gọi mô tả outbound dependency failure; service nhận mô tả nguyên nhân nội bộ. Cần correlation để liên kết chúng, không xóa một log chỉ vì message giống nhau.

## 3. Nguyên tắc: log một lần ở nơi có đủ thông tin

Với exception được ném lên theo call stack, chọn **một tầng chịu trách nhiệm ghi stack trace đầy đủ**. Các tầng khác có thể thêm context, wrap exception, chuyển thành response, cập nhật metric hoặc span status mà không log lại cùng throwable.

| Layer | Trách nhiệm logging thường phù hợp |
| --- | --- |
| Repository/DAO | Không log mọi exception sẽ propagate; chỉ log khi có thông tin nội bộ riêng |
| Service | Thêm business context, throw/wrap exception; không log lại nếu chỉ rethrow |
| Controller/API boundary | Chuyển lỗi thành HTTP response; ghi log nếu boundary là owner |
| Global exception handler | Thường ghi lỗi request chưa xử lý và map response |
| Message consumer boundary | Ghi failure cuối cùng, message ID/attempt/DLQ action |
| Scheduled job boundary | Ghi run summary/final outcome |
| Retry component | Ghi attempt ở level phù hợp; tránh full stack trace cho mọi lần retry |

Đây là convention, không phải luật cứng. Ownership cần rõ: tầng nào biết exception đã được xử lý hay chưa và có thể ghi nhận kết quả cuối cùng?

## 4. Tránh log rồi rethrow cùng exception

Mẫu dễ tạo duplicate:

```java
public Order loadOrder(String id) {
    try {
        return repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));
    } catch (RuntimeException ex) {
        log.error("Cannot load order {}", id, ex);
        throw ex;
    }
}
```

Nếu controller advice hoặc boundary phía trên cũng ghi exception, stack trace xuất hiện nhiều lần. Service không thêm thông tin xử lý mà chỉ log lại lỗi sẽ làm tăng volume.

Mẫu gọn hơn:

```java
public Order loadOrder(String id) {
    return repository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
}
```

Global exception handler ghi lỗi tại boundary:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleNotFound(OrderNotFoundException ex) {
        log.warn("Order request could not be completed: {}", ex.getMessage());

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Order not found");
        problem.setDetail("The requested order does not exist.");
        return problem;
    }

    @ExceptionHandler(Exception.class)
    ProblemDetail handleUnexpected(Exception ex) {
        log.error("Unhandled request failure", ex);

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
        problem.setTitle("Internal server error");
        problem.setDetail("The request could not be completed.");
        return problem;
    }
}
```

Trong ví dụ:
- OrderNotFoundException là tình huống nghiệp vụ dự kiến, có thể ghi ngắn ở WARN thay vì stack trace.
- Lỗi bất ngờ được ghi ERROR kèm throwable.
- Response không trả stack trace, SQL, token hoặc chi tiết nội bộ.
- Service không log lại lỗi trước khi ném lên handler.

Không phải exception nào cũng cần ERROR. Validation, not-found hoặc business rejection có thể là WARN/INFO hoặc chỉ được đo bằng metric theo policy. Nếu lỗi đã được xử lý hoàn toàn và không cần điều tra, không nhất thiết tạo stack trace log.

## 5. Wrap exception mà không log kép

Khi service cần chuyển exception kỹ thuật thành exception nghiệp vụ, giữ cause để boundary có thể ghi stack trace gốc:

```java
public Receipt issueReceipt(String orderId) {
    try {
        return receiptGateway.issue(orderId);
    } catch (GatewayTimeoutException ex) {
        throw new ReceiptUnavailableException(
                "Receipt provider is unavailable", ex);
    }
}
```

Đây là wrapping, không phải lý do để log ở cả catch và handler. Handler cuối có thể ghi throwable đã wrap; stack trace vẫn giữ cause chain.

Tránh pattern vừa log đầy đủ ở catch vừa wrap rồi throw nếu boundary sẽ log cùng lỗi. Nếu catch có thông tin duy nhất không thể khôi phục phía trên, cân nhắc một log ngắn có event code/context và thống nhất boundary không ghi lại cùng stack trace.

## 6. Logging responsibility ở các boundary

Một HTTP request có thể gặp lỗi ở service layer rồi được handler chuyển thành 4xx/5xx. Global exception handler hoặc boundary filter phù hợp là nơi có thể biết response cuối cùng.

Với message consumer, lỗi có thể được retry rồi thành công hoặc chuyển Dead Letter Queue (DLQ). Nếu log ERROR stack trace ở mỗi lần retry rồi cuối cùng vẫn xử lý thành công, dashboard có thể báo lỗi quá mức. Thiết kế theo lifecycle:
- Mỗi attempt có thể tạo event ngắn ở DEBUG/INFO hoặc metric counter.
- Lỗi tạm thời đang retry không nhất thiết là ERROR.
- Khi hết retry và message vào DLQ, ghi failure event cuối cùng với message ID, attempt count và routing decision.
- Không ghi payload nhạy cảm của message.

Với scheduled job, ghi start/summary/final outcome ở cấp run; tránh để mọi method con log cùng failure nếu exception propagate tới job runner.

## 7. Framework logs và custom logs

Spring Boot và thư viện có thể tự ghi log cho request, server, client, SQL, retry hoặc connection pool. Nếu thêm custom log cùng boundary, xác định hai bản ghi có mục đích khác nhau hay chỉ lặp.

Với access logs:
- Reverse proxy ghi method, path, status và latency.
- Servlet container/gateway cũng có thể ghi access record.
- Custom filter có thể ghi request completed.

Có thể giữ một source authoritative; hoặc giữ nhiều nguồn khi cần phân biệt edge latency với application processing time, nhưng phải phân biệt logger/fields. Nếu hai nguồn hoàn toàn trùng và không thêm giá trị, tắt một nguồn sau khi đánh giá tác động.

Không tắt log framework theo package wildcard chỉ để giảm volume mà chưa kiểm tra hậu quả. Giảm verbosity của connection pool có thể che leak, timeout hoặc reconnect bất thường.

### 7.1. Request/response body logging

HTTP body logging dễ tạo duplicate và rủi ro privacy. Tránh ghi toàn bộ body ở filter, client interceptor và controller cùng lúc. Nếu cần audit, dùng audit event riêng với schema, retention và redaction rõ ràng. Nếu chỉ cần chẩn đoán, ghi metadata allowlist như method, route template, status và duration.

## 8. Logback additivity và appender trùng

Duplicate có thể đến từ logger hierarchy: logger con có appender riêng, đồng thời additivity=true khiến event tiếp tục lên root logger cũng có appender.

Ví dụ có nguy cơ lặp:

```xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <logger name="com.example.payment" level="INFO">
    <appender-ref ref="CONSOLE"/>
  </logger>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
```

Logger com.example.payment có appender CONSOLE; event tiếp tục propagate lên root rồi được CONSOLE ghi thêm lần nữa.

Nếu không cần appender riêng ở logger con, giữ appender ở root:

```xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
```

Nếu thật sự cần appender riêng, có thể đặt additivity=false cho logger đó và thiết kế routing rõ ràng. Không gắn cùng appender ở nhiều nơi mà không hiểu logger hierarchy.

Spring Boot mặc định dùng Logback nếu logging starter và dependency không bị thay đổi. Với Log4j2 hoặc backend khác, kiểm tra cơ chế additivity/filter tương ứng.

## 9. Structured logging để nhận diện event

Message text tự do làm việc nhận diện duplicate khó hơn. Structured fields giúp backend group theo event type, service, trace ID, operation và outcome.

Ví dụ SLF4J 2 fluent API:

```java
log.atWarn()
        .addKeyValue("event", "payment.retry_scheduled")
        .addKeyValue("provider", providerName)
        .addKeyValue("attempt", attempt)
        .addKeyValue("traceId", traceId)
        .log("Payment attempt will be retried");
```

Một log event có thể có:
- Event/eventCode ổn định.
- Service name và environment.
- traceId/spanId nếu có tracing.
- Correlation/request ID nếu ứng dụng cần.
- Outcome, attempt number và dependency name trong tập giá trị có kiểm soát.
- Timestamp, level và logger do logging framework cung cấp.

Không đưa dynamic identifiers như order ID, customer ID hoặc correlation ID vào metric tags. ID có thể cần trong logs để tìm kiếm nhưng phải xét privacy, retention và quyền truy cập.

Khi dùng Spring Boot structured logging, cấu hình JSON output và kiểm tra field thực tế. Cùng một event code không có nghĩa hai bản ghi là duplicate; cần xem trace/span, attempt và timestamp.

## 10. Sampling và rate limiting cho log tần suất cao

Một số sự kiện lặp là thật: health checks, polling, retry, cache misses hoặc lỗi kết nối từ client. Có thể giảm volume bằng sampling/rate limiting, nhưng phải chọn theo loại event.

### 10.1. Khi nào sampling phù hợp?

Sampling phù hợp khi event:
- Có tần suất cao và pattern ổn định.
- Mỗi bản ghi riêng lẻ ít giá trị nếu không có bất thường.
- Có metric/counter khác giữ tổng số lần xảy ra.
- Có cách bảo đảm lỗi hiếm/đột biến không bị che.

Ví dụ log DEBUG cho mỗi lần polling có thể chỉ giữ một phần mẫu, đồng thời metric counter ghi tổng số lần polling.

### 10.2. Không sample mù quáng errors

Không áp dụng cùng một sampling rate cho mọi log levels. Với failure/error:
- Giữ log đầu tiên hoặc ghi summary theo cửa sổ thời gian.
- Đếm toàn bộ occurrences bằng metric counter.
- Giữ mẫu có exception type mới, status nghiêm trọng hoặc dependency chuyển trạng thái.
- Ghi tổng số event bị suppressed trong cửa sổ.
- Có burst detection để tăng verbosity khi lỗi tăng đột biến.

Sampling logs không giống trace sampling. Trace sampler quyết định trace/span được ghi/export; log sampling quyết định log records nào được ghi. Hai chính sách vận hành riêng.

### 10.3. Minh họa suppression window

Ví dụ pseudocode cho một logger suppress lặp theo event key trong khoảng thời gian:

```java
public final class DuplicateEventGate {
    private final ConcurrentMap<String, Long> lastLogged =
            new ConcurrentHashMap<>();
    private final long intervalMillis;

    public DuplicateEventGate(Duration interval) {
        this.intervalMillis = interval.toMillis();
    }

    public boolean shouldLog(String eventKey, long nowMillis) {
        AtomicBoolean allowed = new AtomicBoolean(false);
        lastLogged.compute(eventKey, (key, previous) -> {
            if (previous == null || nowMillis - previous >= intervalMillis) {
                allowed.set(true);
                return nowMillis;
            }
            return previous;
        });
        return allowed.get();
    }
}
```

Cách dùng:

```java
if (gate.shouldLog("inventory.poll.timeout", clock.millis())) {
    log.warn("Inventory poll timed out; repeated events are suppressed");
} else {
    suppressedCounter.increment();
}
```

Đây là minh họa thuật toán, không phải production-ready component. Trong hệ thống nhiều instance, mỗi JVM có map riêng nên suppression không global. Map cần eviction/giới hạn key để tránh memory leak; dùng monotonic time cho interval, xử lý concurrency và counter. Nếu cần global rate limit, dùng cơ chế tập trung hoặc backend/appender hỗ trợ và cân nhắc chi phí.

## 11. Retry logs: ghi attempt và kết quả cuối

Retry là trường hợp dễ nhầm giữa duplicates và event hợp lệ. Giả sử payment call timeout ba lần rồi thành công. Có thể log:
- Một log INFO/DEBUG cho mỗi attempt nếu cần quan sát retry behavior.
- Một log WARN khi retry budget gần cạn.
- Một log ERROR nếu cuối cùng vẫn thất bại.

Không log full stack trace cho cùng transient exception ở mọi attempt nếu volume lớn. Thay vào đó ghi metric attempts, retry exhaustion và final failure.

```java
public Receipt issueWithRetry(String orderId) {
    try {
        return retryExecutor.execute(
                () -> receiptGateway.issue(orderId));
    } catch (ReceiptProviderException ex) {
        log.error("Receipt issue failed after retries; orderRef={}",
                safeOrderReference(orderId), ex);
        throw ex;
    }
}
```

Đây là log ở boundary sau khi retry exhausted. Nếu retry framework đã log mọi attempt, điều chỉnh level/config hoặc custom retry listener để tránh full stack trace lặp. Vẫn giữ attempt visibility khi đó là bằng chứng cần thiết; có thể dùng fields gọn hoặc metrics thay cho stack trace mỗi lần.

## 12. Liên kết duplicate logs với tracing và metrics

Spring Boot/Micrometer Tracing thường đưa traceId và spanId vào MDC khi tracing hoạt động. Log pattern hoặc structured logging có thể chứa chúng để mở đúng trace.

Khi điều tra log lặp:
1. Group theo traceId/spanId, logger, event code và thời gian.
2. So sánh exception class/cause chain và stack trace.
3. Kiểm tra bản ghi từ cùng service/pod hay nhiều service.
4. Kiểm tra attempt/message delivery metadata.
5. Mở trace để xác định các span là một call hay nhiều call thực.
6. Đối chiếu metric counter/error rate để bảo đảm giảm logs không làm mất phép đo.

Metrics nên giữ số lần xảy ra dù logs bị sampling:
- Counter cho lỗi dependency.
- Counter cho retry attempts và exhausted retries.
- Counter cho log events bị suppressed.
- Timer cho latency operation.

Không dùng traceId/correlationId làm metric tags vì cardinality tăng theo request. Logs liên kết records; traces thể hiện quan hệ và duration; metrics thể hiện xu hướng tổng hợp.

## 13. Kiểm thử và xác minh

Một thay đổi logging cần test để chắc chắn chỉ bỏ bản ghi dư thừa.

### 13.1. Unit test ở boundary

Dùng test appender hoặc OutputCaptureExtension để kiểm tra:
- Service không log stack trace rồi rethrow cùng exception.
- Global exception handler ghi đúng một event cho một request failure.
- Unexpected exception vẫn có throwable/cause chain.
- Business rejection không tạo ERROR stack trace ngoài policy.
- Structured fields như event, outcome, traceId được xuất đúng.

Không chỉ assert số dòng; kiểm tra logger name, level, event code và throwable.

### 13.2. Integration test

1. Gửi request thành công; xác nhận số access/application logs theo thiết kế.
2. Gửi request gây business exception; xác nhận một boundary log theo policy.
3. Gửi request gây unexpected exception; xác nhận một stack trace đầy đủ và response an toàn.
4. Bật retry và tạo transient failure; xác nhận attempt events có metadata khác nhau, final failure chỉ ghi một lần.
5. Gửi request đồng thời; bảo đảm traceId/MDC không bị trộn.
6. Nếu dùng nhiều appender, kiểm tra event không xuất hiện hai lần ngoài ý muốn.

### 13.3. Kiểm thử sampling/rate limiting

- Tạo chuỗi high-volume event để kiểm tra suppression window.
- Xác nhận metric tổng occurrences vẫn tăng theo số sự kiện thật.
- Xác nhận metric suppressed tăng cho event bị loại khỏi logs.
- Tạo error type mới/đột biến và bảo đảm cơ chế vẫn ghi nhận.
- Chạy test nhiều instance nếu suppression phải có hiệu lực toàn cluster.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Cùng stack trace xuất hiện nhiều lần | Nhiều layer log rồi rethrow | Chọn boundary ghi full exception; layer khác throw/wrap |
| Log cùng event xuất hai lần trong process | Logback additivity hoặc appender trùng | Kiểm tra logger hierarchy và appender refs |
| Một service ghi access record lặp | Filter và container/proxy cùng access-log | Chọn owner hoặc phân biệt latency ở từng tầng |
| Logs tăng sau khi bật tracing | Custom instrumentation cộng auto instrumentation log cùng event | Kiểm tra handlers/interceptors và bỏ instrumentation trùng |
| Retry thành công nhưng dashboard ERROR tăng | Mỗi transient attempt ghi ERROR | Hạ level cho retryable attempt; giữ final failure và counter |
| Giảm log khiến không biết số lần lỗi | Sampling không có metric counter | Thêm counter và suppressed count |
| Mất stack trace sau refactor | Ghi message nhưng bỏ throwable ở boundary | Ghi exception tại đúng owner |
| Event hiếm không xuất hiện | Sampling hoặc suppression window | Không sample event critical; giữ first/new transition |
| Log async có context request trước | MDC/context không cleanup ở thread pool | Propagate và restore/clear đúng scope |
| Cùng message nhưng là nhiều retry | Thiếu attempt/delivery metadata | Thêm attempt number và message identifier có kiểm soát |
| Hai service cùng log một failure | Không phân biệt service boundary | Giữ record cần thiết, correlate bằng traceId |
| Metric series tăng sau thay đổi | Correlation/request ID thành metric tag | Bỏ tag động, dùng tags hữu hạn |

## 15. Checklist production

- [ ] Xác định nguồn duplicate trước khi hạ level hoặc tắt logger.
- [ ] Một layer ghi stack trace đầy đủ cho exception lan truyền trong cùng call path.
- [ ] Layer khác thêm context bằng structured fields mà không log lại cùng throwable.
- [ ] Boundary ghi kết quả cuối cho HTTP request, message và scheduled job.
- [ ] Retry attempts được phân biệt với final failure.
- [ ] Framework access logs và custom access logs có owner/mục đích rõ ràng.
- [ ] Logback additivity/appender hierarchy không phát event hai lần.
- [ ] Sampling/rate limit chỉ áp dụng cho nhóm high-volume phù hợp.
- [ ] Error nghiêm trọng và trạng thái chuyển tiếp quan trọng không bị suppress mù quáng.
- [ ] Có counters giữ tổng occurrences và số event bị suppressed.
- [ ] Logs có traceId/spanId, event code và service context khi thích hợp.
- [ ] Không đưa traceId/correlationId vào metric tags.
- [ ] MDC được restore/clear khi request/task kết thúc.
- [ ] Không ghi secrets, tokens hoặc body không được phép.
- [ ] Đã test success, failure, retry, concurrency và nhiều appender.

## 16. Câu hỏi tự luyện

1. Vì sao service log exception rồi rethrow có thể tạo duplicate khi global exception handler cũng log?
2. Nên ghi full stack trace ở repository, service hay request boundary? Khi nào có ngoại lệ?
3. Làm thế nào phân biệt error log lặp với ba retry attempts hợp lệ?
4. Vì sao hai service có thể cùng log một dependency failure mà không phải duplicate?
5. Logback additivity có thể làm một event xuất hai lần như thế nào?
6. Khi nào business exception nên được log WARN hoặc chỉ đo bằng metric?
7. Vì sao cần giữ cause khi wrap exception?
8. Sampling DEBUG logs cần metric nào để không mất tổng occurrences?
9. Làm sao tránh duplicate access logs giữa gateway, servlet container và custom filter?
10. TraceId/spanId giúp điều tra log lặp ra sao?
11. Vì sao không nên dùng traceId làm metric tag?
12. Kiểm thử nào chứng minh refactor đã bỏ log dư mà vẫn giữ stack trace cho lỗi bất ngờ?

## Tài liệu tham khảo

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [SLF4J — Manual](https://www.slf4j.org/manual.html)
- [Logback — Architecture and Logger Additivity](https://logback.qos.ch/manual/architecture.html)
- [Logback — Filters](https://logback.qos.ch/manual/filters.html)
- [Micrometer Tracing — Logging Correlation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)


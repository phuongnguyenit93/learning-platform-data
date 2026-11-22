# Giảm log noise khi retry

Retry là một phần quan trọng của reliability trong Spring Kafka. Khi database, HTTP service hoặc broker tạm thời không khả dụng, consumer có thể thử xử lý lại record sau một khoảng backoff. Nhưng nếu mỗi lần thất bại đều ghi một stack trace đầy đủ, một record có thể tạo hàng chục log lines; hàng nghìn records cùng gặp lỗi có thể làm log backend quá tải và che khuất sự cố quan trọng.

**Giảm log noise khi retry** là thiết kế cách ghi log để vẫn giữ thông tin cần chẩn đoán — listener nào, record nào, attempt thứ mấy, lỗi thuộc nhóm nào và kết quả cuối cùng ra sao — mà không ghi lặp cùng stack trace ở mọi lần delivery. Trong Spring Kafka, cần phối hợp **DefaultErrorHandler**, **BackOff**, **RetryListener**, **DeadLetterPublishingRecoverer**, **@RetryableTopic**, logging levels và metrics.

Bài học thuộc chương **Logging và chẩn đoán** của **Spring Kafka Reliability Operations**. Trọng tâm là giảm log lặp nhưng giữ nguyên retry semantics, offset safety và khả năng điều tra.

## 1. Vì sao retry tạo log noise?

Giả sử listener xử lý một OrderCreated record. Database tạm thời không kết nối được trong 30 giây. Error handler được cấu hình retry bốn lần trước khi chuyển record sang Dead Letter Topic (DLT).

~~~text
Record orders.created-2@184
  attempt 1 -> DataAccessResourceFailureException
  attempt 2 -> DataAccessResourceFailureException
  attempt 3 -> DataAccessResourceFailureException
  attempt 4 -> DataAccessResourceFailureException
  attempt 5 -> DataAccessResourceFailureException
  recovery  -> publish to orders.created.DLT
~~~

Nếu nhiều tầng cùng ghi ERROR với full stack trace, cùng một lỗi có thể xuất hiện từ business listener, DefaultErrorHandler, RetryListener, Kafka client, DLT publisher và global exception handler. Một record tạo nhiều dòng trùng lặp; nhiều records cùng gặp lỗi dependency làm log volume tăng nhanh đúng lúc đội vận hành cần tìm root cause.

### 1.1 Hậu quả của noise

- Signal-to-noise giảm: lỗi quan trọng bị chìm trong stack traces giống nhau.
- Chi phí ingest, indexing và retention tăng.
- Alert fatigue: một lỗi transient tạo hàng trăm alert events.
- Khó phân biệt record đang retry, đã recover hay đã vào DLT.
- Logging đồng bộ hoặc format stack trace có thể làm tăng CPU/I/O.
- Collector hoặc backend quá tải có thể drop cả log có giá trị.

**Giảm log không có nghĩa giảm retry.** Retry policy quyết định số lần delivery và thời gian backoff; logging policy quyết định severity, nội dung và sampling. Không thay đổi retry budget chỉ để dashboard bớt đỏ.

## 2. Phân biệt các nguồn log

| Nguồn | Nội dung thường gặp | Cách kiểm soát |
|---|---|---|
| Business listener | Validation, DB/HTTP exception, domain context | Tránh log rồi rethrow cùng exception |
| DefaultErrorHandler | Failed delivery, retry/recovery state | Error handler log level |
| RetryListener | Callback delivery failure và recovery | Metrics hoặc log có chọn lọc |
| DeadLetterPublishingRecoverer | DLT send và recovery failures | Recoverer logs, producer outcome |
| @RetryableTopic infrastructure | Main/retry/DLT listener activity | Phân biệt listener stage |
| Kafka client | Fetch, coordinator, network, producer retry | Logger levels của Apache Kafka |
| Spring container | Start/stop, assignment, commit, lifecycle | Logger levels và container events |
| Global exception handler | Exception đã được log ở tầng khác | Tránh log trùng khi rethrow |

Một lỗi có thể được log ở nhiều lớp. Trước khi đổi logger level, xác định **logger nào phát ra dòng lặp**. Không hạ toàn bộ org.springframework.kafka hoặc org.apache.kafka xuống ERROR chỉ vì một retry handler tạo nhiều log.

## 3. Retry policy và logging policy độc lập

Spring Kafka dùng CommonErrorHandler để xử lý listener exceptions. Một lựa chọn phổ biến cho record listeners là DefaultErrorHandler. Nó phối hợp exception classification, BackOff, redelivery/seek và recovery.

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff = new FixedBackOff(
        1_000L, // interval giữa các lần retry
        3L     // số retry sau lần delivery ban đầu
    );

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.setLogLevel(LogIfLevelEnabled.Level.WARN);

    return handler;
}
~~~

Ví dụ đặt log level cho các exception logs do error handler quản lý. Imports và API phải khớp Spring Kafka version đang chạy. BackOff vẫn giữ nguyên số retries; setLogLevel không thay đổi số lần xử lý.

### 3.1 Mức log theo lifecycle

| Giai đoạn | Mức log gợi ý | Thông tin cần giữ |
|---|---|---|
| Attempt thất bại còn retry | DEBUG hoặc WARN có chọn lọc | Listener, topic/partition/offset, attempt, error category |
| Nhiều attempts cùng lỗi | Metrics và summary | Tổng attempts, error category, retry window |
| Retry exhausted, DLT publish thành công | WARN hoặc INFO theo impact | Record đã quarantine và destination |
| DLT/recovery thất bại | ERROR | Original failure và recovery failure |
| Fatal/non-retryable exception | WARN/ERROR theo impact | Lý do không retry và final action |
| Authentication/transaction infrastructure failure | ERROR và alert | Listener/client, cluster, failure category |

Không hạ mọi exception xuống DEBUG. Nếu record hết retry hoặc DLT publish thất bại, phải còn tín hiệu đủ mạnh để vận hành phát hiện.

### 3.2 Log level của handler không đổi mọi logger

DefaultErrorHandler có cơ chế log-level control qua setLogLevel(LogIfLevelEnabled.Level). Cơ chế này ảnh hưởng log do error handler quản lý; nó không đổi business service logger, Kafka client logger, DLT publisher, global exception handler hoặc database/HTTP client logger.

Nếu sau khi đổi handler sang WARN vẫn còn ERROR, hãy xem logger name trong log record trước khi chỉnh package level.

## 4. Tránh log-and-rethrow ở listener

Anti-pattern:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderCreated event) {
    try {
        orderService.apply(event);
    }
    catch (Exception ex) {
        log.error("Could not process order", ex);
        throw ex;
    }
}
~~~

Listener ghi full stack trace rồi rethrow. DefaultErrorHandler nhận exception và có thể ghi lại lỗi trong cùng delivery attempt. Khi retry, chuỗi log này lặp lại.

Nếu listener không thể tự phục hồi, thường chỉ cần để exception propagate:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderCreated event) {
    orderService.apply(event);
}
~~~

Error handler có thông tin về retry attempt, BackOff và recovery outcome; đó thường là nơi phù hợp để sở hữu retry logging.

### 4.1 Khi nào listener vẫn nên log?

Listener có thể log khi nó bổ sung domain context duy nhất mà tầng error handler không biết. Nhưng nên:

- Log gọn một lần ở tầng có thông tin duy nhất.
- Không ghi full stack trace ở mọi attempt.
- Dùng structured fields, không stringify toàn payload.
- Vẫn để exception propagate nếu cần retry.
- Không log cùng exception nếu tầng sau đã ghi đầy đủ.

### 4.2 Không nuốt exception để giảm log

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderCreated event) {
    try {
        orderService.apply(event);
    }
    catch (Exception ex) {
        log.debug("Ignoring processing error", ex);
        // Return bình thường.
    }
}
~~~

Nếu method return bình thường, container có thể coi invocation thành công theo acknowledgment/transaction semantics hiện tại và tiến offset. Record có thể bị bỏ qua dù business side effect thất bại.

**Giảm log noise không được biến failure thành success giả.**

## 5. RetryListener: đo attempts mà không log stack trace lặp

Spring Kafka cung cấp **RetryListener** cho error handler. Các callback có thể quan sát delivery failure, successful recovery và recovery failure. Đây là nơi phù hợp để tăng retry counter, phân loại exception, ghi log final outcome và đếm recovery success/failure.

~~~java
public class OrdersRetryObserver implements RetryListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrdersRetryObserver.class);

    private final MeterRegistry registry;

    public OrdersRetryObserver(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {

        registry.counter(
            "orders.kafka.retry.attempts",
            "error_category", classify(exception)
        ).increment();

        // Intermediate attempts được đo bằng metrics.
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {

        log.warn(
            "Kafka record recovered: topic={}, partition={}, offset={}, errorCategory={}",
            record.topic(),
            record.partition(),
            record.offset(),
            classify(exception)
        );
    }

    @Override
    public void recoveryFailed(
            ConsumerRecord<?, ?> record,
            Exception original,
            Exception failure) {

        log.error(
            "Kafka record recovery failed: topic={}, partition={}, offset={}, originalError={}, recoveryError={}",
            record.topic(),
            record.partition(),
            record.offset(),
            original.getClass().getSimpleName(),
            failure.getClass().getSimpleName(),
            failure
        );
    }

    private String classify(Exception exception) {
        if (exception instanceof TransientDataAccessException) {
            return "database_transient";
        }
        if (exception instanceof TimeoutException) {
            return "timeout";
        }
        return "other";
    }
}
~~~

Ví dụ minh họa callback cho record listener; imports, overloads và signatures phải khớp Spring Kafka version. RetryListener chỉ quan sát callbacks, không quyết định retry count, BackOff, exception classification, offset commit hay DLT routing.

Đăng ký listener trên handler:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer recoverer,
        OrdersRetryObserver observer) {

    var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );

    handler.setRetryListeners(observer);
    handler.setLogLevel(LogIfLevelEnabled.Level.WARN);

    return handler;
}
~~~

Nếu ứng dụng đã đăng ký RetryListeners, hãy giữ callbacks hiện có và bổ sung observer theo đúng API của version. Đừng ghi đè cấu hình retry hoặc recovery chỉ để thêm logging.

### 5.1 Không log mọi failedDelivery ở ERROR

failedDelivery có thể được gọi ở mỗi attempt. Nếu callback ghi ERROR với stack trace, noise vẫn còn nguyên. Thường nên dùng callback để tăng counter và chỉ log một dòng khi record đã recover hoặc recovery thất bại.

## 6. Metrics thay cho log lặp

Một counter có thể đo retry attempts:

~~~text
orders.kafka.retry.attempts{
  error_category="database_transient"
}
~~~

Metric tổng hợp attempts theo nhóm lỗi mà không tạo log event cho từng delivery.

| Metric | Ý nghĩa |
|---|---|
| kafka_retry_attempts_total | Delivery failures dẫn đến retry |
| kafka_recovery_success_total | Records recover thành công |
| kafka_recovery_failure_total | Recovery thất bại |
| kafka_dlt_publish_total | Kết quả publish DLT |
| kafka_retry_exhausted_total | Records đã hết retry |
| kafka_listener_processing_duration | Listener invocation latency |
| kafka_consumer_lag | Backlog theo group/topic/partition |
| kafka_log_suppressed_total | Log events bị sampling/suppress bởi custom policy |

Đây là gợi ý instrumentation; không phải mọi metric đều do Spring Kafka tự tạo. Định nghĩa rõ counter đếm **attempt**, **record** hay **final business operation**.

### 6.1 Metric tags cần cardinality thấp

Dùng các error categories có tập giá trị hữu hạn: database_transient, http_unavailable, timeout, invalid_payload, other.

Không dùng orderId, eventId, requestId, Kafka offset, raw message key, full exception message hoặc user ID làm metric tags. Những giá trị này có thể có hàng triệu biến thể. Dùng structured logs hoặc traces có policy để tra record cụ thể.

### 6.2 Attempts khác unique records

Một record retry ba lần rồi thành công có thể làm retry counter tăng ba, trong khi chỉ có một unique business event. Không cộng retry attempts và listener successes để suy ra unique records.

Nếu cần unique outcomes, dùng event ID và idempotent business storage. Không biến event ID thành metric label.

## 7. Phân loại exception để tránh retry vô ích

Một nguyên nhân tạo log noise là retry những lỗi không thể tự phục hồi:

- Database connection reset: có thể transient.
- HTTP 503: có thể transient.
- Invalid payload: thường không tự hết.
- Unsupported event version: có thể cần quarantine hoặc compatibility handling.
- Authentication/ACL misconfiguration: retry dày thường không giúp.

DefaultErrorHandler hỗ trợ exception classification. Có thể đánh dấu một số exception không retry:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );

    handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class
    );

    handler.setLogLevel(LogIfLevelEnabled.Level.WARN);
    return handler;
}
~~~

Default classifications và API cụ thể phụ thuộc Spring Kafka version. Trước khi thay đổi, kiểm tra các exception framework đã mặc định coi là fatal/non-retryable.

| Nhóm lỗi | Policy thường cân nhắc |
|---|---|
| Transient dependency | Retry với BackOff hữu hạn |
| Rate limiting | BackOff phù hợp, tôn trọng Retry-After nếu có tích hợp |
| Invalid schema/payload | Không retry vô hạn; quarantine/DLT |
| Business conflict có thể hết | Retry có giới hạn hoặc xử lý riêng |
| Authentication/ACL misconfiguration | Alert vận hành, tránh retry dày |
| Unknown/unexpected | Retry hữu hạn rồi recovery |

Không đánh dấu mọi Exception là non-retryable chỉ để giảm logs. Làm vậy có thể đẩy lỗi transient vào DLT ngay lập tức.

## 8. BackOff kiểm soát nhịp retry

Fixed backoff:

~~~java
new FixedBackOff(2_000L, 4L)
~~~

Exponential backoff:

~~~java
ExponentialBackOffWithMaxRetries backOff =
    new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(30_000L);
~~~

Class và constructor phải có trong Spring Framework version đang dùng. BackOff giãn thời gian giữa attempts, giúp giảm retry storm, nhưng **không tự giảm số log** nếu mỗi attempt vẫn ghi full stack trace.

### 8.1 Retry storm sau outage

Nếu hàng nghìn records cùng thất bại, cùng một backoff interval có thể khiến chúng retry gần đồng thời khi dependency phục hồi. Cần cân nhắc BackOff hữu hạn, jitter nếu retry mechanism hỗ trợ, circuit breaker/bulkhead ở downstream, retry metrics, lag monitoring và log sampling.

Không dùng Thread.sleep() trong listener để tạo delay; dùng BackOff/error handling phù hợp với container.

## 9. Recovery và DeadLetterPublishingRecoverer

Khi retries hết, DefaultErrorHandler có thể gọi recoverer để publish record sang DLT.

~~~java
@Bean
DeadLetterPublishingRecoverer ordersRecoverer(
        KafkaTemplate<Object, Object> template) {

    return new DeadLetterPublishingRecoverer(template);
}
~~~

Đây là cấu hình minh họa với default destination resolution. Production cần quyết định topic/partition routing, serializers, headers và producer behavior.

### 9.1 Log final recovery outcome

Khi DLT publish thành công, một structured log gọn có thể là:

~~~text
event=kafka_record_recovered
listener=orders-main
topic=orders.created
partition=2
offset=184
attempts=4
destination=orders.created.DLT
errorCategory=invalid_payload
~~~

Không cần in full payload hoặc lặp stack trace nếu đã có một log failure đầy đủ ở tầng khác.

### 9.2 Recovery failure phải nổi bật

Nếu DLT publisher thất bại, record có thể chưa được quarantine an toàn. Log ERROR nên giữ source topic/partition/offset, listener/group context khi có, original exception class, recovery exception class, destination DLT nếu đã xác định và action/alert theo policy.

Không log dlt_published trước khi publish outcome thực sự thành công. Nếu kết quả chưa rõ do timeout, ghi outcome unknown và thực hiện reconciliation theo policy.

### 9.3 Không log payload toàn phần

ConsumerRecord.toString() có thể đưa key/value/headers vào logs. Payload có thể chứa email, địa chỉ, account number hoặc token. Hãy ghi metadata đủ để tìm record trong Kafka/DLT, và chỉ log payload fields đã whitelist/mask nếu có lý do nghiệp vụ.

## 10. @RetryableTopic và log noise

Spring Kafka hỗ trợ non-blocking retries qua @RetryableTopic. Record lỗi được route sang retry topics và được xử lý lại sau delay thay vì giữ main listener flow chờ backoff.

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 30_000
    ),
    include = {
        TransientDataAccessException.class,
        ResourceAccessException.class
    }
)
@KafkaListener(
    id = "orders-main",
    topics = "orders.created",
    groupId = "orders-projection"
)
public void handle(OrderCreated event) {
    orderService.apply(event);
}

@DltHandler
public void handleDlt(OrderCreated event) {
    // Quarantine hoặc recovery workflow.
}
~~~

Annotation options và imports phải khớp Spring Kafka version. Ví dụ minh họa exception allowlist và backoff; kiểm tra semantics attempts của version dự án trước khi đặt retry budget.

### 10.1 Retry topics tạo nhiều listener containers

Một flow có thể có main topic, retry topics và DLT:

~~~text
orders.created
orders.created-retry-1000
orders.created-retry-2000
orders.created-retry-4000
orders.created.DLT
~~~

Tên thật phụ thuộc retry topic naming strategy. Một record có thể tạo logs từ nhiều listener IDs và containers. Structured logs nên có stage như main/retry/dlt để phân biệt.

### 10.2 Blocking và non-blocking retry khác nhau

| Đặc điểm | DefaultErrorHandler | @RetryableTopic |
|---|---|---|
| Backoff | Trong flow của container/error handler | Route sang retry topic |
| Partition progress | Có thể chặn partition tùy handler semantics | Main topic có thể tiếp tục với records khác |
| Log sources | Listener, error handler, recoverer | Main + retry listeners + DLT handler |
| Noise risk | Stack trace lặp theo delivery | Log rải qua nhiều topics/containers |
| Final recovery | Recoverer, thường là DLT | Retry chain rồi DLT |

Chọn một chiến lược rõ cho mỗi processing path. Đừng vô tình xếp blocking retries bên trong một flow đã dùng @RetryableTopic khiến attempts nhân lên ngoài dự tính.

### 10.3 Không log full stack trace ở mọi retry stage

Log một dòng gọn khi route sang retry topic nếu cần audit transition. Dùng metrics để đếm attempts. Chỉ ghi final disposition khi record recover hoặc chuyển DLT; recovery failure phải giữ exception context.

## 11. Logging theo retry lifecycle

Một logical lifecycle:

~~~text
DELIVERY_FAILED
    -> RETRYING
    -> RECOVERED
       hoặc
    -> RECOVERY_FAILED
~~~

Đây là trạng thái logic để thiết kế logs/metrics, không phải tên event API chính thức.

- **Attempt failure:** increment counter, phân loại lỗi, có thể log DEBUG gọn; không ghi full stack trace mỗi lần.
- **Retry exhausted:** log WARN/INFO một lần với source metadata, attempt count và action.
- **Recovery success:** ghi final disposition nếu cần; không gọi nó là business success nếu record chỉ được chuyển DLT.
- **Recovery failure:** log ERROR với original và recovery exception, đồng thời tạo alert phù hợp.

Nếu cần full stack trace để điều tra, chọn một nơi sở hữu nó: ví dụ lần đầu xuất hiện một error class mới hoặc lần recovery thất bại. Các attempts còn lại chỉ cần metadata, category và counter.

## 12. Structured logging cho retry

~~~java
log.warn(
    "Kafka record exhausted retries: listenerId={}, topic={}, partition={}, offset={}, attempts={}, errorType={}, action={}",
    listenerId,
    record.topic(),
    record.partition(),
    record.offset(),
    attempts,
    exception.getClass().getSimpleName(),
    "DLT"
);
~~~

Fields hữu ích gồm listenerId, groupId khi đã xác định, source topic, partition, offset, attempt count, error category/class, retry/DLT destination, event ID/operation ID nếu policy cho phép và final outcome.

### 12.1 Key có thể chứa dữ liệu nhạy cảm

Kafka key đôi khi là customer ID, email hoặc business identifier. Không log raw key mặc định. Nếu cần correlation, dùng opaque identifier đã được policy chấp thuận hoặc hash có đánh giá rủi ro phù hợp.

### 12.2 Offset là log field, không phải metric tag

Topic/partition/offset hữu ích để tìm record trong Kafka hoặc DLT. Chúng phù hợp làm structured log fields. Offset tăng liên tục, vì vậy không dùng nó làm Prometheus label.

### 12.3 Exception message không phải metric category

Exception message có thể chứa host, SQL, URL, record ID hoặc user input. Dùng exception class hoặc category hữu hạn cho metrics. Nếu cần message chi tiết trong log, kiểm tra masking và data policy.

## 13. Rate limiting và sampling log

Nếu một dòng ngắn cho mỗi attempt vẫn tạo quá nhiều noise, có thể áp dụng sampling hoặc rate limiting.

~~~text
Trong mỗi cửa sổ 60 giây:
  log tối đa 5 samples cho cùng listener + error category
  metrics vẫn đếm tất cả attempts
  log summary với suppressedCount
  final recovery failure luôn được log
~~~

Đây là policy custom, không phải behavior mặc định của Spring Kafka.

### 13.1 Không tạo cache vô hạn theo event ID

Một Map giữ event IDs đã log có thể tăng theo tổng số records và trở thành memory leak. Nếu cần deduplicate logs, dùng cache bounded/TTL hoặc aggregation theo listener + error category + time window.

Không để sampling suppress final outcomes hoặc fatal infrastructure errors.

### 13.2 Sampling phải minh bạch

Nếu nhiều transient failures bị suppress, cần counter hoặc summary để operator biết volume thật. Có thể tạo metric kafka_log_suppressed_total theo listener/error category với cardinality hữu hạn.

Đừng âm thầm bỏ log rồi làm dashboard có vẻ như hệ thống hết lỗi.

## 14. Chỉnh logger levels đúng phạm vi

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.kafka.listener: WARN
    org.apache.kafka.clients.consumer: WARN
~~~

Đây chỉ là ví dụ. Logger class thực tế cần được xác định từ log record. Không đặt toàn bộ Kafka packages thành ERROR trước khi biết dòng noise đến từ đâu.

Nếu noise do DefaultErrorHandler phát ra, setLogLevel trên handler thường chính xác hơn việc hạ cả package. Nếu listener log ERROR trong catch rồi rethrow, sửa behavior ở business service. Nếu noise từ network reconnect hoặc fetch, xem logger Kafka client cụ thể và giữ lại warnings quan trọng về authentication, rebalance, fencing và broker availability.

## 15. MDC và correlation context

MDC có thể gắn correlationId hoặc traceId vào log. Kafka consumer threads thường được tái sử dụng, vì vậy context phải được clear sau mỗi record.

~~~java
@KafkaListener(topics = "orders.created")
public void handle(ConsumerRecord<String, OrderCreated> record) {

    String correlationId = safeCorrelationId(record.headers());

    try {
        MDC.put("correlationId", correlationId);
        orderService.apply(record.value());
    }
    finally {
        MDC.remove("correlationId");
    }
}
~~~

Đây là ví dụ vòng đời MDC; safeCorrelationId là application code. Nếu cần correlation trong error handler/retry callback, propagate metadata qua record headers và đọc lại trong callback. MDC trong listener có thể đã được clear trước khi error handler ghi log.

Nếu listener submit task sang executor, MDC/trace context không tự động được đảm bảo ở thread khác. Dùng context propagation phù hợp và clear context trên executor thread. Trace ID và event ID cũng là hai khái niệm khác nhau: trace ID liên kết execution path, event ID định danh business event.

## 16. Những trường hợp vẫn cần full stack trace

Giảm noise không có nghĩa loại bỏ stack traces. Giữ exception context đầy đủ khi:

- Lần đầu xuất hiện error class chưa biết.
- Recovery/DLT publish thất bại.
- Authentication/authorization/configuration error.
- Kafka transaction abort/fencing đe dọa consistency.
- Error handler tự ném exception.
- Có nguy cơ record bị mất hoặc offset tiến sai.
- Root cause khác với transient failure đã biết.

Một log ERROR tốt nên trả lời: listener nào, record ở đâu, lỗi gốc là gì, recovery failure là gì, retry đã hết chưa, DLT đã nhận record chưa và hành động tiếp theo là gì.

Nếu commit/publish outcome chưa rõ vì timeout, ghi outcome unknown; đừng khẳng định record đã recover khi chưa có bằng chứng.

## 17. Retry trong transactional listener

Với transactional listener, exception có thể abort Kafka transaction và làm record được giao lại theo container semantics. Cần phân biệt listener method failure, Kafka transaction abort, consumer offset không commit, AfterRollbackProcessor/retry flow và final recovery/DLT outcome.

Không log “record lost” chỉ vì một transaction abort. Abort thường có nghĩa transaction không commit; record có thể được giao lại. Phải kiểm tra offset và recovery state.

Producer fencing hoặc transaction timeout là infrastructure issues, không phải business record errors thông thường. Giảm noise không được hạ severity của lỗi khiến consumer không thể commit.

Kafka EOS không loại bỏ retry logs hoặc mọi lỗi downstream. Nó bảo vệ các thao tác nằm trong Kafka transaction được cấu hình đúng; business side effects ngoài Kafka vẫn cần thiết kế riêng.

## 18. Tránh xếp chồng nhiều retry layers

Một flow có thể vô tình kết hợp:

~~~text
@RetryableTopic attempts=4
  -> DefaultErrorHandler retries=5
    -> business service retries HTTP 3 lần
      -> HTTP client retries 2 lần
~~~

Tổng số downstream calls có thể nhân lên ngoài dự tính. Log volume cũng tăng theo từng tầng.

Cần chỉ định owner retry cho từng loại failure, giới hạn tổng retry budget và deadline, tránh retry cùng lỗi ở mọi tầng, gắn stage/attempt context, đo downstream calls thực tế và xác định final recovery owner.

| Tầng | Trách nhiệm logging |
|---|---|
| HTTP client | Metric retry count, không stack trace mọi lần |
| Business service | Log domain decision duy nhất nếu cần |
| Kafka listener | Để exception propagate, không log-and-rethrow |
| DefaultErrorHandler | Log outcome theo handler level |
| RetryListener | Counter và final recovery result |
| DLT recoverer | ERROR khi recovery/publish thất bại |

## 19. Kiểm thử logging policy

Unit test gọi trực tiếp listener method không kiểm chứng đầy đủ container, retry callbacks và error handler logs. Nên dùng Embedded Kafka hoặc Testcontainers Kafka với Spring context thật.

### 19.1 Retry rồi thành công

1. Cấu hình DefaultErrorHandler với BackOff nhỏ, hữu hạn.
2. Listener fail một vài lần rồi thành công.
3. Gắn RetryListener tăng counter.
4. Capture logs từ listener và error handler.
5. Xác nhận retry attempts được đếm đủ.
6. Xác nhận không có full stack trace lặp ở business listener.
7. Xác nhận recovery/DLT counter không tăng nếu record xử lý thành công.
8. Xác nhận offset tiến theo AckMode/transaction policy.

### 19.2 Retry exhausted và DLT success

1. Làm listener fail đến khi BackOff exhausted.
2. Cho recoverer publish sang DLT.
3. Xác nhận DLT nhận record.
4. Xác nhận final log có source/destination/offset.
5. Xác nhận retry exhausted metric tăng theo định nghĩa.
6. Xác nhận không log full stack trace ở mọi attempt.

### 19.3 DLT publish failure

1. Làm recoverer không thể publish.
2. Xác nhận recovery failure được log ERROR.
3. Xác nhận log giữ cả original và recovery exception.
4. Kiểm tra record/offset không bị đánh dấu recovered giả.
5. Kiểm tra container behavior theo version.
6. Xác nhận alert hoặc operational signal được phát.

### 19.4 Non-retryable exception

- Gửi poison record.
- Xác nhận classification không retry theo policy.
- Xác nhận final disposition được ghi.
- Xác nhận record không bị silently discarded.
- Đối chiếu số attempts với policy.

### 19.5 @RetryableTopic và sampling

- Kiểm tra main/retry/DLT listeners có identity riêng.
- Xác nhận log stage đúng.
- Đếm logs ở các transitions.
- Xác nhận không có full stack trace ở mọi retry stage.
- Tạo nhiều failures cùng error category và xác nhận logs được giới hạn.
- Xác nhận metrics vẫn đếm mọi attempts và summary có suppressed count.
- Xác nhận recovery failure/fatal alert không bị suppress.

Không assert toàn bộ format log nội bộ của Spring Kafka giữa các versions; ưu tiên kiểm tra logger, severity, event marker và số lần theo policy của ứng dụng.

## 20. Runbook khi retry log bùng nổ

1. Xác định logger phát nhiều dòng nhất: listener, error handler, Kafka client hay DLT publisher.
2. Group theo listener ID, topic, exception class và time window.
3. Kiểm tra consumer lag, retry attempt rate và DLT rate.
4. Xác định một record hay nhiều records đang lặp.
5. Phân loại transient error, poison record hay infrastructure failure.
6. Kiểm tra BackOff và retry budget ở mọi tầng.
7. Tìm catch-log-throw hoặc log-and-rethrow.
8. Kiểm tra handler log level và package logger level.
9. Dùng RetryListener/metrics để giữ số attempts khi giảm log.
10. Chọn final outcome log cho recovery success/failure.
11. Nếu sampling, đặt giới hạn và suppressed counter.
12. Không log payload/credentials để tìm nguyên nhân.
13. Kiểm thử retry success, exhaustion và DLT failure.
14. Theo dõi log volume cùng retry/recovery metrics sau rollout.

Không giảm tất cả log xuống ERROR chỉ để log backend hết nghẽn. Trước tiên xác định tầng tạo noise và giữ lại signals về recovery, broker health và data correctness.

## 21. Bảng quyết định: nên log gì?

| Tình huống | Logging gợi ý | Metrics/action |
|---|---|---|
| Transient attempt còn retry | DEBUG hoặc dòng gọn có sampling | Retry counter |
| Nhiều attempts cùng lỗi | Không stack trace từng lần | Aggregate attempts |
| Record phục hồi thành công | INFO/WARN một lần nếu đáng chú ý | Recovery success |
| Retry exhausted, DLT publish thành công | WARN với source/destination | DLT success + exhausted |
| DLT publish thất bại | ERROR với original và recovery exception | Alert, recovery state |
| Invalid payload không retry | WARN/ERROR một final disposition | Non-retryable/DLT counter |
| Kafka auth/ACL failure | ERROR và alert hạ tầng | Client/auth metric |
| Producer fencing/transaction timeout | ERROR có context | Transaction abort/fencing metric |
| Listener bắt exception rồi return | Sửa behavior; không chỉ đổi level | Bảo đảm error handler nhận exception |
| Retry topic transition | Log gọn, không payload | Routing/stage metric |

## 22. Những hiểu nhầm cần tránh

**“Hạ log level sẽ giảm số retry.”** Sai. Log level và BackOff độc lập.

**“Log-and-rethrow giúp error handler hiểu lỗi tốt hơn.”** Thường không cần; nó có thể tạo log trùng.

**“Nuốt exception là cách giảm noise an toàn.”** Sai. Listener có thể return bình thường và offset tiến dù business processing thất bại.

**“Mỗi failedDelivery là một unique record.”** Sai. Một record có thể tạo nhiều attempts.

**“RetryListener quyết định retry.”** Sai. Nó quan sát callbacks; error handler/BackOff quyết định policy.

**“DLT publish success nghĩa business đã xử lý xong.”** Không. Record đã được quarantine theo recovery path.

**“Không thấy listener failure log nghĩa không có lỗi consumer.”** Sai. Deserialization/poll/client errors có thể xảy ra trước listener.

**“@RetryableTopic và DefaultErrorHandler luôn xếp chồng an toàn.”** Không. Nhiều retry layers có thể nhân attempts và log volume.

**“Log full ConsumerRecord giúp debug tốt hơn.”** Rủi ro payload lớn và PII/secret exposure.

**“Dùng eventId làm metric tag giúp tìm record.”** Không. Cardinality có thể bùng nổ; dùng logs/traces có kiểm soát.

**“Sampling được phép suppress mọi ERROR.”** Không. Recovery failure và fatal infrastructure errors cần tín hiệu rõ.

**“BackOff tự làm log ít đi.”** Không. Nó giãn thời gian giữa attempts; mỗi attempt vẫn có thể tạo log.

## 23. Checklist triển khai

**Retry policy**

- [ ] Chọn blocking retry hay non-blocking retry cho mỗi path.
- [ ] BackOff và retry budget hữu hạn, phù hợp SLA.
- [ ] Exception được phân loại transient/non-retryable có chủ đích.
- [ ] Không xếp chồng retry ở nhiều tầng ngoài dự kiến.
- [ ] Recovery/DLT outcome được xác định rõ.
- [ ] Recovery failure không bị xem như success.

**Logging**

- [ ] Không log-and-rethrow cùng exception ở mọi tầng.
- [ ] Intermediate attempts không ghi full stack trace lặp.
- [ ] Error handler log level được đặt có chủ đích.
- [ ] Final recovery outcome được log.
- [ ] DLT/recovery failure được log ERROR với context.
- [ ] Structured fields gồm listener/topic/partition/offset/attempt/outcome khi có.
- [ ] Không log payload, secret, raw key hoặc PII.
- [ ] Sampling có suppressed counter/summary.
- [ ] Không hạ toàn bộ Kafka logger một cách mù quáng.

**Metrics và tracing**

- [ ] Retry attempts được đếm bằng counter.
- [ ] Recovery success/failure được đo riêng.
- [ ] DLT publish rate và backlog được theo dõi.
- [ ] Consumer lag và listener duration có dashboard.
- [ ] Metric tags có cardinality thấp.
- [ ] Event ID/offset nằm trong logs/traces, không phải metric labels.
- [ ] Correlation context được propagate và clear đúng lifecycle.

**Verification**

- [ ] Test retry success sau transient failures.
- [ ] Test retry exhausted và DLT success.
- [ ] Test DLT publish failure.
- [ ] Test non-retryable exception.
- [ ] Test @RetryableTopic nếu sử dụng.
- [ ] Test logging severity/count và sampling.
- [ ] Test không mất retry behavior sau khi giảm log.
- [ ] Test offset/transaction outcome sau recovery.

## 24. Tài liệu tham khảo

- Spring for Apache Kafka — Handling Exceptions: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring for Apache Kafka — Retry Topic: https://docs.spring.io/spring-kafka/reference/retrytopic.html
- Spring Kafka API — DefaultErrorHandler: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/DefaultErrorHandler.html
- Spring Kafka API — RetryListener: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/RetryListener.html
- Spring Kafka API — KafkaExceptionLogLevelAware: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/KafkaExceptionLogLevelAware.html

Đối chiếu API và callback signatures với Spring Kafka version đang dùng; không copy nguyên cấu hình từ tài liệu của một minor version khác.

## 25. Kết luận

**Giảm log noise khi retry** đòi hỏi tách retry policy khỏi logging policy. Hãy để DefaultErrorHandler/BackOff quyết định attempts và recovery, dùng RetryListener để đếm delivery failures và quan sát final outcome, đồng thời tránh việc listener log full stack trace rồi rethrow khiến error handler ghi lại cùng exception ở mỗi attempt.

Trong production, intermediate transient failures thường chỉ cần metrics hoặc log gọn có sampling; retry exhausted và DLT success cần một final disposition dễ truy vấn; recovery failure, authentication, producer fencing hoặc lỗi có nguy cơ mất dữ liệu vẫn cần log/alert đủ mạnh. Kết hợp structured logs, bounded metric tags, retry budget, DLT monitoring và integration tests sẽ giảm noise mà vẫn giữ bằng chứng cần thiết để điều tra và phục hồi.


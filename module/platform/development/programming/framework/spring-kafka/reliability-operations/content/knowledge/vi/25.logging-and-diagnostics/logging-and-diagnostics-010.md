# Structured logging trong Spring Kafka

Trong một hệ thống Spring Kafka chạy production, log cần trả lời được câu hỏi: **record nào đã được consumer xử lý, listener nào xử lý, lần xử lý diễn ra ở đâu, kết quả là gì và nếu thất bại thì record được retry hay chuyển sang DLT như thế nào?** Một dòng log chỉ có nội dung “Processing failed” không đủ để điều tra khi hàng triệu record được xử lý đồng thời.

**Structured logging** ghi log dưới dạng dữ liệu có trường rõ ràng, thường là JSON. Thay vì nhúng mọi thông tin vào một chuỗi tự do, mỗi log event có những fields như timestamp, level, service, listener ID, topic, partition, offset, event ID, trace ID, outcome và exception type. Hệ thống log có thể lọc, nhóm, tìm kiếm và liên kết những fields này mà không cần parse lại câu văn.

Trong Spring Kafka, structured logging cần được thiết kế quanh các ranh giới thực tế: consumer poll, listener invocation, database/API side effect, retry/error handler, DLT publisher và DLT consumer. **Kafka record metadata, business correlation ID và tracing context là ba nhóm thông tin khác nhau**; cần ghi đúng vai trò và không nhầm chúng với nhau.

Bài học này giải thích cách cấu hình JSON logging, dùng SLF4J key-value pairs và MDC, quản lý context theo consumer thread, ghi log cho retry/DLT, truyền context qua executor, bảo vệ dữ liệu nhạy cảm, kiểm soát log volume và kết hợp logs với metrics/traces.

## 1. Vì sao structured logging cần thiết?

Giả sử có hàng trăm listener containers cùng ghi log dạng text:

~~~text
Processing order failed
Retrying message
Consumer stopped
Dead letter published
Processing order failed
~~~

Những dòng này không cho biết:

- Lỗi thuộc listener nào?
- Topic, partition và offset của record là gì?
- Hai dòng lỗi có cùng một event hay hai event khác nhau?
- Record đã retry mấy lần?
- Exception thuộc nhóm validation hay database?
- DLT publish đã thành công hay chỉ mới được yêu cầu?
- Trace nào liên quan đến lần xử lý?
- Consumer đang ở pod/instance nào?

Structured logging biến từng log event thành một object có fields:

~~~json
{
  "timestamp": "2026-11-15T10:21:30.123Z",
  "level": "ERROR",
  "service": "order-service",
  "logger": "OrderEventListener",
  "message": "Kafka record processing failed",
  "listener_id": "ordersListener",
  "consumer_group": "orders-service",
  "kafka_topic": "orders.events",
  "kafka_partition": 2,
  "kafka_offset": 105,
  "event_id": "evt-100",
  "event_type": "OrderCreated",
  "outcome": "failure",
  "exception_type": "DatabaseTimeoutException",
  "traceId": "7c2a..."
}
~~~

Đây là ví dụ minh họa; schema thực tế nên được chuẩn hóa cho toàn service. Từ những fields đó, log backend có thể tìm tất cả lỗi ở partition 2, nhóm theo listener, hoặc nối record với trace.

Structured logging đặc biệt hữu ích khi điều tra:

- Consumer lag tăng nhưng không rõ listener nào chậm.
- Một partition liên tục gặp poison pill.
- Retry tăng sau khi database quá tải.
- DLT ingress tăng đột ngột.
- Một event được xử lý nhiều lần sau rebalance.
- Một pod có lỗi trong khi các pod khác vẫn khỏe.
- Trace bị sampling hoặc bị đứt ở ranh giới bất đồng bộ.

## 2. Structured log khác log text như thế nào?

| Đặc điểm | Log text | Structured log |
|---|---|---|
| Nội dung | Một câu tự do | Một object có fields |
| Tìm theo topic | Parse text hoặc regex | Filter theo kafka_topic |
| Tìm offset | Phải đọc câu log | Filter theo kafka_offset |
| Nhóm theo exception | Parse tên exception | Group by exception_type |
| Liên kết trace | Tìm chuỗi trong message | Filter theo traceId/spanId |
| Mở rộng schema | Dễ phát sinh format không đồng nhất | Có contract fields |
| Xử lý trong log backend | Cần parse text | Index fields trực tiếp |
| Rủi ro | Câu văn thay đổi làm query hỏng | Schema drift nếu field names không được quản trị |

Structured logging không bắt buộc phải dùng JSON, nhưng JSON là định dạng phổ biến cho log shipping. Mỗi event nên được xuất thành một JSON object trên một dòng, còn stack trace cần được encode an toàn trong field riêng.

Không nên nhồi toàn bộ dữ liệu vào một field message rồi gọi đó là structured logging. Hãy giữ message ngắn và đưa thông tin có thể lọc thành fields riêng.

## 3. Những fields nên có cho Kafka record processing

Một schema log hữu ích có thể chia thành các nhóm:

| Nhóm | Fields tiêu biểu | Mục đích |
|---|---|---|
| Runtime | timestamp, level, service, environment, version, instance | Xác định ứng dụng và deployment |
| Listener | listener_id, consumer_group, client_id | Xác định consumer xử lý |
| Kafka source | kafka_topic, kafka_partition, kafka_offset | Tọa độ record nguồn |
| Business | event_id, event_type, aggregate_id | Nhận diện logical event |
| Execution | attempt, outcome, duration_ms | Theo dõi lần xử lý |
| Error | exception_type, error_category, stack_trace | Chẩn đoán lỗi |
| Tracing | traceId, spanId | Nối với distributed trace |
| Recovery | recovery_action, destination_topic | Theo dõi retry/DLT |
| DLT origin | original_topic, original_partition, original_offset | Truy ngược record nguồn |

Không phải mọi log event đều cần tất cả fields. Một log “consumer started” không có record offset; một log DLT publish cần cả source và destination coordinates nếu đã biết.

Dùng tên fields nhất quán giữa các services. Ví dụ, không để service A dùng topic, service B dùng kafkaTopic và service C dùng sourceTopic cho cùng một khái niệm.

## 4. Phân biệt event ID, Kafka coordinates và trace ID

Ba loại định danh thường bị nhầm lẫn:

**Event ID** là định danh logical event do business contract quy định. Nó nên giữ ổn định qua retry, redelivery, DLT và replay nếu những lần đó vẫn đại diện cùng một event.

**Kafka coordinates** gồm topic, partition và offset. Bộ ba này định vị một record cụ thể trong Kafka log của topic/partition. Khi record được publish sang retry hoặc DLT, destination có topic/partition/offset mới; source coordinates cần được giữ riêng.

**Trace ID** định danh một distributed trace theo tracing system. Một event có thể được xử lý lại trong trace mới, được replay nhiều giờ sau hoặc không có trace do sampling. Trace ID không phải business event ID và không nên dùng làm idempotency key.

~~~text
Logical event:
  event_id = evt-100

Source record:
  topic = orders.events
  partition = 2
  offset = 105

DLT record:
  topic = orders.events.DLT
  partition = 0
  offset = 19

Tracing:
  traceId = 7c2a...
  spanId  = 31af...
~~~

Khi DLT record được replay, nó có thể có destination coordinates khác và trace context mới. Event ID cùng source coordinates giúp nối lịch sử qua các lần xử lý.

Nếu business event không có eventId, có thể dùng source topic/partition/offset làm correlation reference cho một record cụ thể. Nhưng không nên giả định tọa độ nguồn vẫn duy nhất sau khi record được copy qua các topics khác.

## 5. Cấu hình JSON logging với Logback

Một cách phổ biến trong Spring Boot là dùng Logback cùng thư viện **logstash-logback-encoder**. Thư viện này cung cấp encoder tạo JSON fields từ logging event, MDC, SLF4J key-value pairs và exception.

Dependency Maven minh họa:

~~~xml
<dependency>
    <groupId>net.logstash.logback</groupId>
    <artifactId>logstash-logback-encoder</artifactId>
    <version>8.1</version>
</dependency>
~~~

Chọn version tương thích với Java, Logback và Spring Boot của project; không nhất thiết dùng đúng số version trong ví dụ.

Cấu hình Logback tối giản:

~~~xml
<configuration>
    <appender name="JSON_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">

        <encoder class="net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder">
            <providers>
                <timestamp/>
                <logLevel/>
                <loggerName/>
                <threadName/>
                <message/>
                <mdc/>
                <keyValuePairs/>
                <stackTrace/>
            </providers>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_CONSOLE"/>
    </root>
</configuration>
~~~

Các providers trên có ý nghĩa:

- timestamp: thời điểm log.
- logLevel: DEBUG, INFO, WARN, ERROR.
- loggerName: class/package phát log.
- threadName: thread hiện tại.
- message: nội dung ngắn.
- mdc: các trường trong Mapped Diagnostic Context.
- keyValuePairs: fields được thêm bằng SLF4J fluent logging.
- stackTrace: exception stack trace nếu có.

Tên provider và cấu hình encoder cần đối chiếu với version logstash-logback-encoder thực tế. Nếu dùng Spring Boot structured logging tích hợp sẵn hoặc một logging backend khác, schema/output configuration sẽ khác nhưng nguyên tắc fields vẫn giống nhau.

Một JSON log mẫu:

~~~json
{
  "@timestamp": "2026-11-15T10:21:30.123Z",
  "level": "INFO",
  "logger_name": "com.example.orders.OrderEventListener",
  "thread_name": "org.springframework.kafka.KafkaListenerEndpointContainer#0-0-C-1",
  "message": "Kafka record processing completed",
  "listener_id": "ordersListener",
  "consumer_group": "orders-service",
  "kafka_topic": "orders.events",
  "kafka_partition": "2",
  "kafka_offset": "105",
  "event_id": "evt-100",
  "outcome": "success"
}
~~~

Một số encoder ghi MDC values dưới dạng string, vì vậy partition và offset có thể xuất thành chuỗi. Nếu cần kiểu số trong log backend, có thể dùng structured key-value fields với kiểu dữ liệu phù hợp hoặc pipeline parsing có schema rõ ràng.

## 6. Dùng SLF4J key-value pairs thay vì nối chuỗi

Với SLF4J 2, fluent logging API cho phép thêm key-value pairs vào một logging event:

~~~java
log.atInfo()
        .addKeyValue("listener_id", "ordersListener")
        .addKeyValue("consumer_group", "orders-service")
        .addKeyValue("kafka_topic", record.topic())
        .addKeyValue("kafka_partition", record.partition())
        .addKeyValue("kafka_offset", record.offset())
        .addKeyValue("outcome", "started")
        .log("Kafka record processing started");
~~~

Log message vẫn ngắn, còn các fields được encoder xuất riêng. Ví dụ với lỗi:

~~~java
log.atError()
        .addKeyValue("listener_id", "ordersListener")
        .addKeyValue("kafka_topic", record.topic())
        .addKeyValue("kafka_partition", record.partition())
        .addKeyValue("kafka_offset", record.offset())
        .addKeyValue("outcome", "failure")
        .setCause(exception)
        .log("Kafka record processing failed");
~~~

Điều kiện: ứng dụng cần dùng SLF4J 2.x và encoder hỗ trợ xuất key-value pairs. Spring Boot dependency management thường chọn SLF4J phù hợp; tránh override SLF4J API hoặc Logback versions không tương thích.

Một cách không nên dùng:

~~~java
log.info(
        "Processing failed topic=" + record.topic()
        + " partition=" + record.partition()
        + " offset=" + record.offset()
);
~~~

Đây vẫn là một message text. Log backend phải parse lại để tách fields. Ngoài ra, nối chuỗi tạo object/string ngay cả khi log level có thể không được bật, tùy cách viết.

## 7. Dùng MDC để gắn context cho nhiều dòng log

**Mapped Diagnostic Context (MDC)** là một map gắn với execution context của thread, thường được logging framework dùng để thêm fields tự động vào mỗi log event.

Ví dụ, trong lúc xử lý một record, MDC có thể chứa:

~~~text
listener_id = ordersListener
consumer_group = orders-service
kafka_topic = orders.events
kafka_partition = 2
kafka_offset = 105
event_id = evt-100
~~~

Sau khi set MDC, các logger ở những service được gọi đồng bộ trong cùng thread có thể xuất các fields đó mà không phải truyền từng tham số vào mỗi log statement.

~~~text
Kafka listener thread
      |
      +--> MDC set từ ConsumerRecord
      |
      +--> OrderListener log
      |
      +--> OrderService log
      |
      +--> Repository adapter log
      |
      +--> MDC restore/clear
~~~

MDC tiện lợi nhưng cần quản lý lifecycle cẩn thận. Kafka listener thread được tái sử dụng để xử lý nhiều records. Nếu không xóa hoặc khôi phục context sau mỗi record, log của event tiếp theo có thể mang topic, offset hoặc eventId của event trước.

## 8. MDC phải được dọn trong finally

Một ví dụ helper đơn giản:

~~~java
public final class KafkaMdc {

    private KafkaMdc() {
    }

    public static Map<String, String> snapshot() {
        Map<String, String> values = new HashMap<>();

        Map<String, String> previous =
                MDC.getCopyOfContextMap();

        if (previous != null) {
            values.putAll(previous);
        }

        return values;
    }

    public static void setRecordContext(
            ConsumerRecord<?, ?> record,
            String listenerId,
            String groupId) {

        MDC.put("listener_id", listenerId);
        MDC.put("consumer_group", groupId);
        MDC.put("kafka_topic", record.topic());
        MDC.put("kafka_partition",
                Integer.toString(record.partition()));
        MDC.put("kafka_offset",
                Long.toString(record.offset()));
    }

    public static void restore(Map<String, String> previous) {
        if (previous == null || previous.isEmpty()) {
            MDC.clear();
        }
        else {
            MDC.setContextMap(previous);
        }
    }
}
~~~

Dùng trong listener:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "orders-service"
)
public void handle(ConsumerRecord<String, OrderCreated> record) {

    Map<String, String> previous = KafkaMdc.snapshot();

    try {
        KafkaMdc.setRecordContext(
                record,
                "ordersListener",
                "orders-service"
        );

        log.atInfo()
                .addKeyValue("outcome", "started")
                .log("Kafka record processing started");

        orderService.process(record.value());

        log.atInfo()
                .addKeyValue("outcome", "success")
                .log("Kafka record processing completed");
    }
    catch (RuntimeException exception) {
        log.atError()
                .addKeyValue("outcome", "failure")
                .setCause(exception)
                .log("Kafka record processing failed");

        throw exception;
    }
    finally {
        KafkaMdc.restore(previous);
    }
}
~~~

Ở đây snapshot giữ context đã có trước khi listener bắt đầu. finally khôi phục context đó thay vì luôn clear vô điều kiện; điều này hữu ích khi có một context bao ngoài.

Nếu code không có context lồng nhau và MDC trước đó luôn rỗng, MDC.clear() trong finally cũng có thể phù hợp. Quy tắc quan trọng là **không để record context rò sang lần xử lý tiếp theo**.

Không lưu toàn bộ ConsumerRecord hoặc payload trong MDC. MDC chỉ nên chứa những chuỗi ngắn, đã chuẩn hóa và cần cho log correlation.

## 9. Thêm event ID an toàn vào MDC

Event ID thường hữu ích khi tìm một logical event qua retry và DLT. Có thể lấy từ payload hoặc header theo business contract.

Ví dụ helper đọc header:

~~~java
private static String eventIdFromHeader(
        ConsumerRecord<?, ?> record) {

    Header header =
            record.headers().lastHeader("event-id");

    if (header == null || header.value() == null) {
        return "unknown";
    }

    String value = new String(
            header.value(),
            StandardCharsets.UTF_8
    );

    if (value.isBlank() || value.length() > 128) {
        return "invalid";
    }

    return value;
}
~~~

Sau đó:

~~~java
MDC.put("event_id", eventIdFromHeader(record));
~~~

Giới hạn độ dài giúp tránh một header bất thường làm log quá lớn. Nếu eventId có thể chứa PII, không log nguyên giá trị; dùng một identifier đã được thiết kế cho observability hoặc masking theo policy.

Nếu record không có event ID, có thể ghi source coordinates như topic/partition/offset để định vị. Không tạo một random ID mới cho mỗi lần retry nếu muốn tìm cùng logical event qua nhiều attempts.

Event ID có thể có cardinality cao, nhưng **structured logs** có thể lưu nó để tìm kiếm. Đừng chuyển cùng eventId sang Micrometer metric tag.

## 10. MDC và Micrometer Tracing

Khi Spring Boot được cấu hình Micrometer Tracing, logging integration có thể đưa traceId và spanId vào MDC hoặc correlation fields theo convention của stack.

Một log có thể chứa:

~~~json
{
  "message": "Order database update failed",
  "traceId": "7c2a9f...",
  "spanId": "31af...",
  "event_id": "evt-100",
  "kafka_topic": "orders.events",
  "kafka_partition": "2",
  "kafka_offset": "105"
}
~~~

Điều này cho phép operator:

1. Tìm log theo eventId.
2. Lấy traceId từ log.
3. Mở trace trong tracing backend.
4. Xem các spans của producer, consumer, database và downstream calls.
5. Quay lại log theo traceId hoặc spanId.

**MDC traceId không tự tạo distributed trace.** Nó chỉ là một cách biểu diễn context hiện tại trong log. Để propagate trace qua Kafka, cần Observation/tracing instrumentation và propagator inject/extract headers phù hợp.

Không tự tạo một traceId ngẫu nhiên trong listener rồi ghi vào MDC và coi đó là distributed tracing. Nếu không có tracing system, có thể dùng correlation ID nghiệp vụ, nhưng phải gọi đúng tên để tránh nhầm lẫn.

## 11. Structured logging trong listener: log đầu, cuối và lỗi

Một listener không nhất thiết phải ghi INFO cho mọi record ở mọi bước. Với throughput cao, log per-record ở INFO có thể tạo lượng log rất lớn.

Một policy thường dùng:

- DEBUG: record received hoặc chi tiết xử lý bình thường.
- INFO: trạng thái nghiệp vụ quan trọng hoặc kết quả tổng hợp.
- WARN: retry, recoverable failure, bất thường cần chú ý.
- ERROR: record không thể xử lý, recovery thất bại hoặc lỗi hệ thống nghiêm trọng.

Ví dụ:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "orders-service"
)
public void handle(ConsumerRecord<String, OrderCreated> record) {

    Map<String, String> previous = MDC.getCopyOfContextMap();

    try {
        KafkaMdc.setRecordContext(
                record,
                "ordersListener",
                "orders-service"
        );

        log.atDebug()
                .addKeyValue("event_type", "OrderCreated")
                .log("Kafka record received");

        orderService.process(record.value());

        log.atDebug()
                .addKeyValue("outcome", "success")
                .log("Kafka record processing completed");
    }
    catch (RuntimeException exception) {
        log.atError()
                .addKeyValue("outcome", "failure")
                .addKeyValue(
                        "exception_type",
                        exception.getClass().getSimpleName()
                )
                .setCause(exception)
                .log("Kafka record processing failed");

        throw exception;
    }
    finally {
        KafkaMdc.restore(previous);
    }
}
~~~

Đoạn code minh họa record listener đồng bộ. Nếu listener sử dụng async completion hoặc batch processing, context và thời điểm log kết thúc cần được thiết kế riêng.

**Đừng bắt exception rồi chỉ log mà không rethrow** nếu container cần biết record thất bại để retry hoặc recovery. Nuốt exception có thể khiến listener return bình thường và offset được commit theo AckMode.

## 12. Log trong error handler và retry

Listener log được exception ở nơi xử lý nghiệp vụ, nhưng retry policy nằm ở error handler. Cần log rõ lần retry, khoảng backoff, loại lỗi và quyết định tiếp theo.

Một cấu hình error handler:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 2L)
            );

    handler.addNotRetryableExceptions(
            InvalidOrderException.class
    );

    return handler;
}
~~~

Ví dụ này minh họa cấu hình hai lần retry theo FixedBackOff trước recovery; số lần delivery chính xác và semantics cần xác nhận với Spring Kafka version cùng error handler đang dùng.

Log nên phân biệt:

~~~text
listener_failure
retry_scheduled
retry_attempt
recovery_started
dlt_publish_requested
dlt_publish_succeeded
dlt_publish_failed
~~~

Không ghi một log duy nhất “message failed” rồi coi như đã mô tả toàn bộ vòng đời. Retry là một quyết định của framework; log cần thể hiện attempt và policy mà operator có thể đối chiếu.

Nếu framework đã cung cấp retry/DLT metrics, không tạo thêm counters trùng nghĩa. Structured logs bổ sung chi tiết từng record, còn metrics dùng để theo dõi xu hướng.

## 13. Log structured trong DeadLetterPublishingRecoverer

Khi hết retry hoặc gặp lỗi non-retryable, DeadLetterPublishingRecoverer chuyển record sang DLT. Có thể bọc recoverer để ghi structured log ở bước bắt đầu và khi thao tác recoverer trả kết quả.

~~~java
@Bean
DefaultErrorHandler loggingDltErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer delegate =
            new DeadLetterPublishingRecoverer(dltTemplate);

    delegate.setFailIfSendResultIsError(true);

    ConsumerRecordRecoverer loggingRecoverer =
            (record, exception) -> {

                log.atWarn()
                        .addKeyValue("recovery_action", "publish_dlt")
                        .addKeyValue("source_topic", record.topic())
                        .addKeyValue(
                                "source_partition",
                                record.partition()
                        )
                        .addKeyValue(
                                "source_offset",
                                record.offset()
                        )
                        .addKeyValue(
                                "exception_type",
                                exception.getClass().getSimpleName()
                        )
                        .setCause(exception)
                        .log("DLT recovery started");

                try {
                    delegate.accept(record, exception);

                    log.atInfo()
                            .addKeyValue(
                                    "recovery_action",
                                    "publish_dlt"
                            )
                            .addKeyValue(
                                    "source_topic",
                                    record.topic()
                            )
                            .addKeyValue(
                                    "source_partition",
                                    record.partition()
                            )
                            .addKeyValue(
                                    "source_offset",
                                    record.offset()
                            )
                            .log("DLT recoverer invocation completed");
                }
                catch (RuntimeException publishFailure) {
                    log.atError()
                            .addKeyValue(
                                    "recovery_action",
                                    "publish_dlt"
                            )
                            .addKeyValue(
                                    "source_topic",
                                    record.topic()
                            )
                            .addKeyValue(
                                    "source_partition",
                                    record.partition()
                            )
                            .addKeyValue(
                                    "source_offset",
                                    record.offset()
                            )
                            .setCause(publishFailure)
                            .log("DLT recovery failed");

                    throw publishFailure;
                }
            };

    return new DefaultErrorHandler(
            loggingRecoverer,
            new FixedBackOff(1_000L, 2L)
    );
}
~~~

Cần lưu ý:

- setFailIfSendResultIsError có mặt trong các phiên bản Spring Kafka hỗ trợ và khiến lỗi gửi được phản ánh theo contract của recoverer.
- Cách recoverer chờ kết quả producer, timeout và cách exception được ném ra phụ thuộc version/configuration.
- Dòng “DLT recoverer invocation completed” chỉ nên được diễn giải là broker publish thành công nếu cấu hình đảm bảo kết quả send đã được xác nhận trước khi accept trả về.
- Nếu cần phân biệt send requested với broker acknowledged, hãy đặt tên log event chính xác hoặc quan sát KafkaTemplate future/result riêng.
- DLT destination topic/partition có thể được xác định bởi destination resolver; nếu cần log destination, hãy dùng resolver chung hoặc một wrapper có cùng policy, không đoán tên topic.

Không commit source offset như đã recovery nếu DLT publish thất bại và hệ thống yêu cầu bảo toàn record.

## 14. Original Kafka coordinates và DLT headers

Khi một record được chuyển sang DLT, nó trở thành record mới ở topic đích. DLT record có destination coordinates riêng và có thể mang headers mô tả source record.

Ví dụ:

~~~text
Source:
  topic = orders.events
  partition = 2
  offset = 105

DLT:
  topic = orders.events.DLT
  partition = 0
  offset = 19
~~~

Các DLT headers trong Spring Kafka có thể cung cấp original topic, partition, offset và exception metadata theo version/cấu hình. Khi log DLT consumer, nên ghi cả:

~~~text
destination_topic
destination_partition
destination_offset
original_topic
original_partition
original_offset
event_id
traceId
~~~

Không nhầm offset của DLT với offset nguồn. Khi operator tìm record trong source topic, cần original coordinates.

Headers có thể được mã hóa dưới dạng bytes hoặc kiểu dữ liệu cụ thể. Không giả định tất cả DLT headers là UTF-8 strings. Dùng KafkaHeaders constants và cách đọc phù hợp với Spring Kafka version.

## 15. Structured logging cho DLT consumer

DLT consumer thường có trách nhiệm lưu quarantine, tạo ticket, hiển thị cho operator hoặc chờ replay. Nó nên log nguồn gốc và hành động thực hiện.

~~~java
@Component
public class OrderDltListener {

    @KafkaListener(
            id = "ordersDltListener",
            topics = "orders.events.DLT",
            groupId = "orders-dlt-investigation"
    )
    public void onDeadLetter(
            ConsumerRecord<byte[], byte[]> record) {

        log.atWarn()
                .addKeyValue("listener_id", "ordersDltListener")
                .addKeyValue("destination_topic", record.topic())
                .addKeyValue(
                        "destination_partition",
                        record.partition()
                )
                .addKeyValue(
                        "destination_offset",
                        record.offset()
                )
                .addKeyValue("recovery_state", "received")
                .log("Dead letter record received");

        quarantineService.store(record);
    }
}
~~~

Đây là ví dụ raw bytes vì DLT có thể chứa record không deserialize được. QuarantineService cần lưu bytes và headers theo schema bảo mật phù hợp; không log raw value.

Nếu quarantine lưu thành công, ghi một log riêng với outcome=stored. Nếu lưu thất bại, ném exception để container/error handler xử lý theo policy; không ghi nhận record đã được điều tra xong.

DLT listener không nên chỉ ghi “received” rồi commit offset trước khi quarantine persistence hoàn tất.

## 16. Log deserialization errors

Một số lỗi xảy ra trước khi business listener được gọi. Ví dụ JSON không hợp lệ hoặc schema không tương thích khiến deserializer thất bại.

~~~text
KafkaConsumer.poll()
       |
       v
Deserializer
       |
       +--> SerializationException
       |
       v
ErrorHandlingDeserializer / error handler
       |
       v
Recovery / DLT
~~~

Trong trường hợp này, listener method có thể chưa chạy, nên log MDC do listener tự thiết lập cũng không có.

Với ErrorHandlingDeserializer, Spring Kafka có thể lưu thông tin exception và raw data trong headers để error handler/recoverer sử dụng. Cần ghi structured log tại error handling path, gồm source topic/partition/offset, exception class, error category và recovery action.

Ví dụ log event:

~~~json
{
  "level": "ERROR",
  "message": "Kafka deserialization failed",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "exception_type": "SerializationException",
  "error_category": "deserialization",
  "recovery_action": "publish_dlt"
}
~~~

Không log raw payload để tiện debug nếu payload có thể chứa thông tin cá nhân, payment data hoặc secrets. Nếu cần forensic payload, lưu ở quarantine storage có access control, encryption và retention rõ ràng.

## 17. MDC và consumer threads

KafkaConsumer không thread-safe; Spring Kafka listener container quản lý consumer trên thread riêng. Với synchronous record listener, listener method và các lời gọi service đồng bộ thường chạy trên consumer thread.

MDC cũng thường là thread-local. Do đó:

- MDC được set trong listener thread có thể xuất hiện ở logs từ service đồng bộ.
- Không nên dùng một static mutable Map chung cho mọi consumer threads.
- Không để context của record trước rò sang record sau.
- Không gọi KafkaConsumer trực tiếp từ worker thread.
- Không giả định MDC tự truyền qua CompletableFuture hoặc Executor.

Với concurrency 3, có ba child consumers và có thể ba consumer threads:

~~~text
ordersListener
    |
    +--> consumer thread 0 --> record A --> MDC A
    |
    +--> consumer thread 1 --> record B --> MDC B
    |
    +--> consumer thread 2 --> record C --> MDC C
~~~

Mỗi thread cần context riêng. Khi record hoàn tất, context phải được restore/clear trước khi thread xử lý record kế tiếp.

## 18. MDC không tự truyền qua Executor

Một listener có thể dispatch công việc async:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {

    MDC.put("kafka_topic", record.topic());

    executor.execute(() -> orderService.process(record.value()));

    MDC.clear();
}
~~~

Code này không đảm bảo worker thread có kafka_topic. Thread pool tái sử dụng thread; MDC trên consumer thread không tự động chuyển sang executor thread.

Một cách dùng TaskDecorator để snapshot/restore MDC:

~~~java
@Bean
TaskDecorator mdcTaskDecorator() {

    return task -> {
        Map<String, String> captured =
                MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous =
                    MDC.getCopyOfContextMap();

            try {
                if (captured == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(captured);
                }

                task.run();
            }
            finally {
                if (previous == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(previous);
                }
            }
        };
    };
}
~~~

TaskDecorator cần được gắn vào executor phù hợp. Đây chỉ truyền **MDC values**; nó không tự bảo đảm truyền toàn bộ Micrometer Observation/trace context.

Nếu ứng dụng cần propagation của Observation qua async boundary, dùng Context Propagation integration và executor decorator phù hợp với Spring/Micrometer version. Không tự dựng trace context chỉ từ traceId string.

Ngoài ra, async fire-and-forget trong Kafka listener có thể khiến listener return và offset commit trước khi công việc hoàn tất. Context propagation chỉ giải quyết correlation của logs; nó **không giải quyết acknowledgment hoặc durability**. Cần thiết kế async completion/ack hoặc lưu công việc vào durable store trước khi return.

## 19. RecordInterceptor có thể tập trung hóa MDC

Nếu nhiều listener cần cùng Kafka record context, có thể cân nhắc RecordInterceptor để thiết lập context trước listener và dọn sau record.

Ý tưởng:

~~~text
ConsumerRecord
      |
      v
RecordInterceptor.intercept(...)
      |
      +--> Set MDC fields
      |
      v
@KafkaListener
      |
      +--> Application logs dùng MDC
      |
      v
RecordInterceptor cleanup callback
      |
      v
Restore MDC
~~~

Một interceptor dùng chung có thể giảm code lặp, nhưng cần xác minh chính xác lifecycle callbacks của RecordInterceptor theo Spring Kafka version đang dùng. Đặc biệt phải xử lý:

- Listener thành công.
- Listener ném exception.
- Record bị interceptor loại bỏ.
- Container retry/seek.
- Batch listener.
- Child consumers chạy đồng thời.
- Context được restore ngay cả khi callback lỗi.

Không chỉ set MDC trong intercept() mà quên cleanup. Nếu framework version cung cấp callbacks success/failure/afterRecord, hãy dùng đúng semantics của chúng; đừng giả định error handler chạy trong cùng MDC scope sau khi interceptor đã hoàn tất.

Với một vài listeners, wrapper try/finally ngay trong listener có thể dễ hiểu hơn. Với nhiều endpoints, interceptor hữu ích khi được kiểm thử kỹ và có contract rõ.

## 20. Ghi log structured cho retry attempts

Retry logs cần phân biệt một record được thử lại với một event mới.

Fields hữu ích:

~~~text
event_id
source_topic
source_partition
source_offset
listener_id
consumer_group
attempt
backoff_ms
error_category
exception_type
next_action
~~~

Ví dụ JSON:

~~~json
{
  "level": "WARN",
  "message": "Kafka record retry scheduled",
  "event_id": "evt-100",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "listener_id": "ordersListener",
  "attempt": 2,
  "backoff_ms": 1000,
  "error_category": "database",
  "next_action": "retry"
}
~~~

Attempt number cần đến từ cơ chế retry hoặc state do ứng dụng quản lý. Không suy ra retry attempt từ Kafka offset vì offset không biểu thị số lần xử lý.

Với blocking retry, record có thể được seek/redeliver trong cùng topic. Với non-blocking retry, record có thể được publish sang retry topic; lúc đó source coordinates và current retry coordinates khác nhau. Log nên giữ cả hai khi cần.

Không log mỗi lần retry ở ERROR nếu đó là hành vi dự kiến của policy. WARN có thể phù hợp cho retry attempts, còn ERROR cho exhausted retries, recovery failure hoặc sự cố cần can thiệp.

## 21. Structured logging cho recovery và DLT publish

Một DLT flow cần tối thiểu hai loại log:

**Recovery started / send requested**

~~~json
{
  "level": "WARN",
  "message": "Dead letter recovery started",
  "event_id": "evt-100",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "destination_topic": "orders.events.DLT",
  "recovery_action": "publish_dlt",
  "error_category": "validation"
}
~~~

**Publish result**

~~~json
{
  "level": "INFO",
  "message": "Dead letter publish acknowledged",
  "event_id": "evt-100",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "destination_topic": "orders.events.DLT",
  "destination_partition": 0,
  "destination_offset": 19,
  "publish_result": "success"
}
~~~

Không ghi publish_result=success ngay sau khi gọi KafkaTemplate.send nếu future chưa hoàn tất hoặc recoverer chưa xác nhận send theo policy. Dùng các trạng thái như requested, acknowledged, failed để tránh đánh đồng request với kết quả.

Nếu publish lỗi do ACL, serializer, topic missing hoặc broker unavailable, log phải giữ source coordinates để record còn có thể điều tra. Error handler không được xem record đã recover nếu DLT publish thất bại theo contract ứng dụng.

## 22. Logging trong transactional listener

Với transactional listener container, một listener failure có thể làm Kafka transaction abort. Log cần phân biệt **listener processing failure**, **transaction outcome** và **recovery outcome**.

~~~text
Listener starts
     |
     v
Kafka transaction active
     |
     +--> Business processing
     |
     +--> Exception
             |
             v
       Transaction abort
             |
             v
       AfterRollbackProcessor
             |
             +--> retry
             |
             +--> DLT recovery
~~~

Một log listener failure không chứng minh transaction đã abort thành công; transaction manager và container quyết định outcome. Tương tự, log “recovery started” không chứng minh DLT record đã commit.

Các fields có thể cần:

- listener_id, consumer_group.
- source topic/partition/offset.
- event_id.
- exception_type/error_category.
- transaction outcome nếu framework/application có thông tin đáng tin cậy.
- retry/recovery action.
- DLT destination và publish result.

Không tự log transaction outcome=committed trong listener trước khi container commit transaction. Nếu cần quan sát transaction outcome, dùng hooks/metrics/events phù hợp với transaction lifecycle hoặc log từ lớp biết chính xác kết quả.

## 23. Structured logging không thay thế tracing

Logs và traces trả lời những câu hỏi khác nhau:

| Logs | Traces |
|---|---|
| Ghi sự kiện rời rạc | Mô tả các spans trong một hành trình |
| Dễ chứa Kafka topic/partition/offset và exception details | Thể hiện quan hệ thời gian và parent-child/link |
| Tìm kiếm theo event ID | Theo dõi cross-service latency |
| Có thể tồn tại ngay cả khi trace bị sampled out | Có thể bị sampling hoặc export failure |
| Không tự biểu diễn causal graph | Biểu diễn quan hệ giữa các operations |
| Thường có stack trace chi tiết | Có span events/status và attributes |

Khi Micrometer Tracing được cấu hình, traceId/spanId có thể được thêm vào log correlation fields. Điều này giúp mở trace từ log.

Không đưa toàn bộ stack trace hoặc exception message vào trace tags/metric labels. Dùng logs cho chi tiết, traces cho causal flow và metrics cho xu hướng.

## 24. Structured logging không thay thế metrics

Một log event cho biết một record thất bại. Metrics cho biết lỗi đang xảy ra bao nhiêu lần và xu hướng có xấu đi không.

| Mục tiêu | Công cụ phù hợp |
|---|---|
| Tìm record cụ thể theo offset | Structured logs |
| Xem eventId thất bại ở listener nào | Logs |
| Đo p95 listener duration | Micrometer Timer |
| Theo dõi consumer lag | Kafka consumer/group metrics |
| Đếm DLT publish failures | Counter/metrics và logs |
| Theo dõi end-to-end request path | Distributed tracing |
| Theo dõi database saturation | Hikari/DB metrics |
| Điều tra exception stack trace | Structured logs |

Không tạo metric tag event_id, order_id, trace_id hoặc kafka_offset chỉ vì chúng có trong structured logs. Những fields có cardinality cao phù hợp với log search, không phù hợp với metrics time series.

## 25. Bảo vệ dữ liệu nhạy cảm trong log

Kafka payload có thể chứa:

- Tên, email, số điện thoại, địa chỉ.
- Customer ID hoặc account number.
- Payment token hoặc thông tin giao dịch.
- Authorization headers hoặc access tokens.
- Dữ liệu nội bộ của khách hàng.
- Secret do producer vô tình đưa vào headers.

Không log toàn bộ ConsumerRecord.toString(), payload JSON hoặc tất cả Kafka headers để debug.

Một policy an toàn:

1. Chỉ log eventId/operationId được phép.
2. Không log raw key nếu key có thể chứa PII.
3. Không log payload mặc định.
4. Chỉ log allowlist headers.
5. Redact token, credentials và payment data.
6. Không đưa PII vào trace baggage hoặc MDC.
7. Giới hạn độ dài message và exception detail.
8. Áp access control và retention cho log backend.
9. Không để debug logging vô tình bật ở production.
10. Có cách lấy payload forensic từ quarantine storage có kiểm soát nếu thật sự cần.

Một field tên customer_reference không tự động an toàn; phải xác định contract dữ liệu và chính sách privacy. Hashing cũng không phải lúc nào làm dữ liệu vô danh nếu không gian giá trị có thể đoán được.

## 26. Log volume và throughput của Kafka

Một topic có thể nhận hàng trăm nghìn records mỗi phút. Nếu mỗi record ghi 5 log events ở INFO, hệ thống có thể tạo lượng log lớn hơn đáng kể so với lượng business data cần thiết.

Các cách kiểm soát:

- INFO cho trạng thái quan trọng và kết quả tổng hợp.
- DEBUG cho per-record details, mặc định tắt trong production.
- WARN cho retry hoặc degradation cần theo dõi.
- ERROR cho failure cần điều tra.
- Rate limit hoặc sampling logs lặp lại khi có incident lớn.
- Không log cùng một exception ở mọi layer mà không thêm thông tin mới.
- Đếm failures bằng metrics thay vì chỉ dựa vào log volume.
- Dùng async appender có queue và policy rõ khi queue đầy.
- Theo dõi disk/ingestion limits của log pipeline.

Nếu dùng sampling, cần giữ lại đầy đủ hoặc có xác suất cao hơn cho những sự kiện quan trọng như DLT publish failure, authentication failure hoặc exhausted retries. Nhưng sampling logs không được làm mất audit events bắt buộc của nghiệp vụ.

## 27. JSON logging và multiline stack traces

Một JSON log nên được xuất thành một object trên một dòng. Stack trace có thể chứa newline; encoder cần escape thành JSON string hoặc lưu trong field có cấu trúc để log shipper không tách nhầm thành nhiều events.

Không nên tự nối stack trace vào message:

~~~java
log.error("Kafka failed: " + exception);
~~~

Thay vào đó:

~~~java
log.atError()
        .addKeyValue("error_category", "database")
        .setCause(exception)
        .log("Kafka record processing failed");
~~~

Encoder sẽ quyết định cách serialize exception/stacktrace theo configuration. Kiểm tra JSON output thật bằng log shipper và backend, vì một cấu hình multiline sai có thể làm mỗi stack trace bị tách thành nhiều log entries.

## 28. Error classification để tìm nguyên nhân nhanh

Exception class có thể bị bọc qua nhiều lớp. Một listener nhận ListenerExecutionFailedException, trong cause mới là DataAccessResourceFailureException hoặc SerializationException.

Một classifier đơn giản:

~~~java
private static String classifyError(Throwable error) {

    Throwable current = error;

    for (int depth = 0;
         current != null && depth < 10;
         depth++, current = current.getCause()) {

        if (current instanceof InvalidOrderException) {
            return "validation";
        }

        if (current instanceof SerializationException) {
            return "deserialization";
        }

        if (current instanceof TimeoutException) {
            return "timeout";
        }

        if (current instanceof DataAccessException) {
            return "database";
        }
    }

    return "other";
}
~~~

Các imports và exception hierarchy cần điều chỉnh theo ứng dụng. Vòng lặp giới hạn depth để tránh cause chain bất thường hoặc cyclic references.

Dùng error_category với một tập giá trị hữu hạn. Có thể log exception_type cụ thể ở field riêng, nhưng tránh dùng exception message làm metric label hoặc tag cardinality cao.

## 29. Log khi consumer rebalance hoặc partition bị revoke/lost

Structured logging cũng hữu ích cho lifecycle events:

~~~text
event = kafka_partition_revoked
consumer_group = orders-service
listener_id = ordersListener
topic = orders.events
partition = 2
last_safe_offset = 106
reason = rebalance
~~~

Phân biệt:

- **Partitions revoked:** consumer được thông báo partition sắp chuyển chủ; có thể có cơ hội commit tiến độ an toàn.
- **Partitions lost:** consumer đã mất quyền sở hữu; không nên giả định còn có thể commit.
- **Partitions assigned:** consumer nhận assignment mới.
- **Commit failed:** offset commit không được xác nhận.

Log nên ghi partition subset được callback cung cấp, không giả định toàn bộ assignment bị thay đổi trong cooperative rebalance.

Không log last_safe_offset nếu ứng dụng chưa thực sự tính được dãy record hoàn tất liên tục. Một offset poll gần nhất không đồng nghĩa offset an toàn để commit.

## 30. Log khi pause/resume vì database overload

Khi backpressure controller pause container, nên ghi lý do và trạng thái:

~~~json
{
  "level": "WARN",
  "message": "Kafka listener pause requested",
  "listener_id": "ordersListener",
  "pause_reason": "DATABASE_SATURATION",
  "db_pool_active": 19,
  "db_pool_max": 20,
  "db_threads_waiting": 4,
  "container_state": "PAUSE_REQUESTED"
}
~~~

Khi container thực sự pause, ghi event riêng:

~~~json
{
  "level": "INFO",
  "message": "Kafka consumer paused",
  "listener_id": "ordersListener",
  "partitions": ["orders.events-0", "orders.events-1"]
}
~~~

Khi resume:

~~~json
{
  "level": "INFO",
  "message": "Kafka consumer resumed",
  "listener_id": "ordersListener",
  "pause_duration_ms": 45000,
  "pause_reason": "DATABASE_SATURATION"
}
~~~

Đừng ghi pause requested và actual paused như một event duy nhất. Container có thể áp dụng pause ở poll boundary. Nếu nhiều lý do pause tồn tại, log lý do cụ thể và chỉ resume khi mọi lý do cần thiết đã được giải quyết.

## 31. Correlation giữa logs của source và DLT

Một DLT record nên có thể được nối lại với source record qua:

- eventId/operationId.
- Original topic.
- Original partition.
- Original offset.
- DLT destination topic/partition/offset.
- traceId/spanId nếu có.
- Exception type/error category.
- Retry/recovery outcome.

Ví dụ hai logs:

~~~json
{
  "message": "Source record processing failed",
  "event_id": "evt-100",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "error_category": "validation"
}
~~~

~~~json
{
  "message": "DLT publish acknowledged",
  "event_id": "evt-100",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "destination_topic": "orders.events.DLT",
  "destination_partition": 0,
  "destination_offset": 19,
  "publish_result": "success"
}
~~~

Nếu trace bị sampling hoặc DLT producer chạy ngoài listener observation scope, eventId và origin metadata vẫn giúp điều tra. Không dùng traceId thay thế eventId vì một event có thể đi qua nhiều traces qua retry/replay.

## 32. Log schema cần được quản trị

Khi nhiều teams cùng dùng Spring Kafka, structured log fields nên có schema contract:

| Field | Kiểu | Quy ước |
|---|---|---|
| timestamp | ISO-8601 | UTC |
| level | string | DEBUG/INFO/WARN/ERROR |
| service | string | Tên service ổn định |
| environment | string | dev/staging/prod |
| listener_id | string | Listener endpoint ID |
| consumer_group | string | Consumer group |
| kafka_topic | string | Source/destination topic theo field riêng |
| kafka_partition | integer/string | Theo encoder contract |
| kafka_offset | integer/string | Theo encoder contract |
| event_id | string | Business ID đã chuẩn hóa |
| outcome | enum | started/success/failure |
| error_category | enum | validation/database/timeout/other |
| traceId | string | Tracing context nếu có |
| spanId | string | Span context nếu có |
| recovery_action | enum | retry/publish_dlt/replay |
| destination_topic | string | Chỉ khi có destination |

Dùng source_topic và destination_topic thay vì một field topic không rõ ngữ nghĩa trong log DLT. Tránh thay đổi kiểu dữ liệu của cùng field giữa các services nếu không có migration.

Khi thêm field, hãy xem log backend có index tất cả fields hay chỉ những field đã được khai báo. Một schema tốt giúp truy vấn ổn định và tránh chi phí index không cần thiết.

## 33. Test structured logging

Kiểm thử cần xác nhận JSON output thật, không chỉ kiểm tra rằng một logger method đã được gọi.

Các tình huống:

| Tình huống | Điều cần xác nhận |
|---|---|
| Listener thành công | Có source coordinates và outcome success |
| Listener exception | Có exception type/category và stack trace |
| Retry | Attempt/action được ghi đúng |
| DLT publish | Source và destination metadata được nối |
| DLT publish failure | Outcome failure, exception được ghi, không báo success giả |
| Listener concurrency | MDC của các consumer threads không trộn |
| Record kế tiếp trên cùng thread | Không còn MDC của record trước |
| Async executor | Context được truyền/restore đúng theo policy |
| Header thiếu | eventId fallback hợp lệ |
| Payload có PII | Không xuất raw payload hoặc secret |
| Deserialization failure | Có log ở error handling path dù listener chưa chạy |
| Rebalance | Partition revoked/lost được phân biệt |
| Pause/resume | Requested và actual state có log riêng |
| JSON stack trace | Mỗi log event vẫn là JSON hợp lệ |
| High throughput | Log volume và async appender queue được kiểm soát |

Có thể dùng Logback ListAppender hoặc test appender phù hợp để kiểm tra event fields. Với integration test, xác nhận JSON encoder tạo output đúng schema và log shipper có thể parse.

Đừng kiểm tra log bằng cách chỉ assert message string chứa topic; cần xác nhận topic là field có cấu trúc nếu đó là mục tiêu.

## 34. Troubleshooting structured logging

### Log không có Kafka topic/partition/offset

MDC chưa được thiết lập, listener không nhận ConsumerRecord, hoặc log xảy ra trước khi record context được tạo. Kiểm tra nơi thiết lập context và cleanup.

### Log của record B lại có eventId của record A

MDC không được clear/restore trong finally, hoặc async task dùng lại worker thread với stale context. Kiểm tra lifecycle và TaskDecorator.

### Trace ID không xuất hiện

Micrometer Tracing chưa được cấu hình, log encoder không xuất MDC/correlation fields hoặc trace context chưa được propagate. MDC eventId không thay thế traceId.

### DLT logs báo success nhưng topic không có record

Có thể log được ghi sau khi send requested nhưng trước broker acknowledgment. Kiểm tra producer future, recoverer send-result behavior, serializer, ACL và broker errors.

### Retry logs không có attempt number

Không tự suy ra attempt từ offset. Lấy từ error handler/retry context hoặc lưu state riêng theo policy.

### Một event xuất hiện nhiều log failure

Có thể listener, error handler và recoverer đều ghi cùng một exception. Giữ một log chi tiết ở điểm phù hợp, các layer khác chỉ ghi decision/outcome mới.

### JSON bị tách thành nhiều lines

Kiểm tra stacktrace provider, encoder và log shipper multiline configuration. Mỗi logging event cần được encode thành một JSON document hợp lệ.

### Log volume tăng đột ngột

Per-record INFO logs, retry storm hoặc exception stack traces lặp lại có thể làm tăng volume. Dùng log levels, sampling/rate limiting có chủ đích và metrics để đo tổng lượng.

### Log backend không tìm thấy field

Kiểm tra encoder provider, field name mapping, parser/index template và kiểu dữ liệu. Structured JSON tại stdout chưa đủ nếu pipeline shipper parse sai.

### Async logs thiếu correlation context

Context chưa được propagate sang executor hoặc MDC bị restore trước khi task chạy. Dùng context propagation có kiểm soát và không giữ ConsumerRecord object tùy tiện.

## 35. Runbook điều tra một record lỗi

Khi nhận eventId hoặc source coordinates từ operator:

1. Tìm structured logs theo eventId.
2. Nếu chưa có eventId, tìm source topic/partition/offset.
3. Xác định listener ID, consumer group, pod và thời gian.
4. Tìm lần xử lý đầu tiên và exception category.
5. Xác định record có retry hay được chuyển thẳng DLT.
6. Đếm attempts theo log/metrics, không suy ra từ offset.
7. Tìm recovery action và kết quả DLT publish.
8. Đối chiếu DLT destination coordinates và original metadata.
9. Mở trace theo traceId nếu có.
10. Kiểm tra database/API side effects đã hoàn tất hay chưa.
11. Xác định event đã được quarantine, replay hay bỏ qua theo policy.
12. Trước khi replay, xác nhận idempotency để không lặp side effects.
13. Ghi audit quyết định xử lý và kết quả cuối.

Structured logs giúp tìm dữ kiện, nhưng quyết định replay cần kiểm tra trạng thái business. Kafka offset/DLT không tự hoàn tác database hoặc external API effects.

## 36. Checklist triển khai production

- Log output là JSON có schema rõ.
- Mỗi record log quan trọng có listener ID và consumer group.
- Source topic/partition/offset được ghi thành fields riêng.
- Destination coordinates tách khỏi source coordinates.
- Event ID ổn định qua retry/replay và được bảo vệ theo privacy policy.
- TraceId/spanId được lấy từ tracing integration phù hợp.
- Không dùng traceId thay eventId.
- MDC được snapshot/restore hoặc clear trong finally.
- MDC không bị trộn giữa concurrent consumer threads.
- Async executor có context propagation phù hợp.
- Async processing không làm offset commit trước khi công việc bền vững.
- SLF4J key-value pairs được encoder xuất thành fields.
- Error handler logs ghi retry/recovery decision.
- DLT publish requested được phân biệt với broker acknowledged.
- DLT send failure không bị log thành success.
- Deserialization errors có logging path riêng.
- Exception type/error category được chuẩn hóa.
- Không log raw payload, credentials, tokens hoặc PII.
- Không đưa eventId/offset/traceId vào metric tags.
- Log volume, stack traces và appender queue được kiểm soát.
- JSON multiline/stacktrace được encode hợp lệ.
- Schema fields nhất quán giữa services.
- Log retention và access control phù hợp.
- Dashboard liên kết logs, metrics và traces.
- Đã kiểm thử success, retry, DLT, concurrency, async context, rebalance và malformed records.

**Kết luận:** Structured logging trong Spring Kafka biến những câu log rời rạc thành dữ liệu vận hành có thể tìm kiếm và đối chiếu. Khi mỗi log mang đúng **listener, consumer group, source coordinates, event ID, outcome, error category và trace context**, operator có thể theo record qua xử lý, retry và DLT. Chất lượng phụ thuộc vào việc quản lý MDC đúng vòng đời, phân biệt send request với broker acknowledgment, kiểm soát log volume và bảo vệ dữ liệu nhạy cảm. Structured logs bổ sung cho Micrometer metrics và distributed tracing; chúng không thay thế offset management, retry policy hay tính idempotent của business processing.


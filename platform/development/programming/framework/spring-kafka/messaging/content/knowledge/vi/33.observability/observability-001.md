# Logging của producer và consumer trong Spring Kafka

Logging giúp vận hành luồng Kafka trả lời được các câu hỏi: event nào đã được gửi, broker xác nhận ở topic/partition/offset nào, consumer group nào đã xử lý, lần xử lý kết thúc ra sao và lỗi đang được retry hay đã chuyển tới DLT. Một log hữu ích cần có ngữ cảnh đủ để tìm lại record, nhưng không làm lộ payload hoặc tạo quá nhiều log trong luồng có throughput cao.

Với Spring Kafka, nên kết hợp log nghiệp vụ trong publisher/listener, log lifecycle của listener container và log từ Kafka client ở mức phù hợp. Log không thay thế metric hoặc distributed tracing: log giải thích một sự kiện cụ thể, metric cho biết xu hướng và mức độ, trace nối các bước qua nhiều service.

## 1. Mục tiêu của logging trong Kafka

Producer và consumer có góc nhìn khác nhau:

| Thành phần | Câu hỏi vận hành | Metadata quan trọng |
|---|---|---|
| Producer | Đã gửi event nào? Gửi tới đâu? Broker đã xác nhận chưa? | event ID, topic, key, partition, offset, timestamp, kết quả send |
| Consumer | Group nào nhận record? Listener xử lý thành công hay lỗi? | event ID, group ID, topic, partition, offset, key, attempt |
| Retry handler | Record còn retry hay đã hết attempt? | exception type, retry attempt, source topic/partition/offset, retry topic |
| DLT handler | Record nào đã được đưa vào DLT? | original topic/partition/offset, DLT topic, exception type |
| Container lifecycle | Consumer có start, stop, pause, resume hoặc rebalance không? | listener ID, group ID, client ID, partition assignment |

Mục tiêu không phải ghi mọi thứ. Mục tiêu là tạo một chuỗi log có thể liên kết bằng event ID và metadata Kafka, đồng thời giữ chi phí lưu trữ và độ nhiễu ở mức kiểm soát được.

## 2. Bộ trường log nên thống nhất

Nên thống nhất tên field giữa producer, consumer và các service liên quan:

| Field | Ý nghĩa | Lưu ý |
|---|---|---|
| eventId | ID ổn định của event nghiệp vụ | Dùng để tra cứu xuyên service và phát hiện xử lý lặp |
| correlationId | ID nối một luồng nghiệp vụ lớn | Có thể khác event ID |
| traceId, spanId | Ngữ cảnh distributed tracing | Lấy từ tracing instrumentation |
| service | Tên service phát log | Dùng để lọc log tập trung |
| listenerId | ID của KafkaListener | Hữu ích khi một ứng dụng có nhiều listener |
| groupId | Consumer group | Cần ghi rõ khi chẩn đoán assignment/lag |
| topic | Topic liên quan | Với consumer retry/DLT, ghi cả topic hiện tại và topic gốc nếu có |
| partition, offset | Vị trí record | Offset chỉ có ý nghĩa trong một partition |
| key | Kafka record key | Chỉ log nếu key không chứa dữ liệu nhạy cảm |
| attempt | Số lần xử lý/retry | Phân biệt lần xử lý đầu với retry |
| outcome | Kết quả send/process/recovery | Dùng giá trị có quy ước như success, failed, recovered |
| exceptionType | Tên lớp exception | Không dùng message làm nhãn metric có cardinality cao |

Record được định danh trong log Kafka bằng tổ hợp topic, partition và offset. Offset 42 ở partition 0 không phải cùng record với offset 42 ở partition 1. Khi tra cứu, luôn giữ cả ba trường.

Không dùng mỗi eventId để thay thế metadata Kafka. Một event có thể được publish lại thành nhiều record với offset khác nhau; metadata giúp xác định chính xác lần xuất hiện cần điều tra.

## 3. Logging kết quả gửi từ KafkaTemplate

Từ Spring Kafka 3.0, KafkaTemplate.send(...) trả về CompletableFuture<SendResult<K,V>>; các phiên bản cũ dùng ListenableFuture. Lời gọi send() trả về future chỉ cho biết producer đã nhận yêu cầu ở API; kết quả broker xác nhận hoặc lỗi cuối cùng được thể hiện khi future hoàn tất.

Ví dụ publisher log kết quả cuối:

```java
@Service
public class OrderEventPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventPublisher.class);

    private static final String TOPIC = "orders.created.v1";

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        String eventId = event.eventId();
        String key = event.orderId();

        try {
            CompletableFuture<SendResult<String, OrderCreated>> future =
                    kafkaTemplate.send(TOPIC, key, event);

            log.debug(
                    "kafka.publish.submitted eventId={} topic={} key={}",
                    eventId, TOPIC, key);

            return future.whenComplete((result, exception) -> {
                if (exception != null) {
                    log.error(
                            "kafka.publish.failed eventId={} topic={} key={}",
                            eventId, TOPIC, key, exception);
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                log.info(
                        "kafka.publish.acknowledged eventId={} topic={} " +
                        "partition={} offset={} timestamp={}",
                        eventId,
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset(),
                        metadata.timestamp());
            });
        }
        catch (RuntimeException exception) {
            // Lỗi đồng bộ trước khi send() trả về future.
            log.error(
                    "kafka.publish.submit_failed eventId={} topic={} key={}",
                    eventId, TOPIC, key, exception);
            throw exception;
        }
    }
}
```

Ví dụ dùng record OrderCreated có các accessor eventId() và orderId(). Điều chỉnh theo model thực tế của ứng dụng.

Nếu topic compacted có thể chứa tombstone, record.value() có thể là null. Hãy kiểm tra value trước khi đọc eventId hoặc gọi service; log tombstone bằng topic, partition, offset và key nếu key được phép log.

Nên phân biệt ba trạng thái:

- submitted: ứng dụng đã gọi API gửi và nhận được future.
- acknowledged: future hoàn tất thành công và có RecordMetadata.
- failed hoặc submit_failed: gửi thất bại bất đồng bộ hoặc API ném lỗi đồng bộ.

Không ghi log acknowledged ngay sau dòng gọi send(). Chỉ ghi khi future hoàn tất thành công. send() cũng có thể ném lỗi đồng bộ, chẳng hạn producer đã đóng hoặc lỗi xảy ra trước khi yêu cầu được đưa vào quá trình gửi.

## 4. Phân biệt log gửi thành công và transaction commit

Với producer thông thường, future hoàn tất thành công cho biết broker đã xác nhận record theo cấu hình acks. Với transactional producer, callback gửi thành công không đồng nghĩa transaction đã commit. Record có thể được ghi vào transaction nhưng transaction sau đó bị abort.

Vì vậy, khi dùng Kafka transaction:

- Log callback gửi record là record_sent_in_transaction hoặc thông điệp tương đương.
- Chỉ log transaction_committed sau khi thao tác transaction hoàn tất thành công.
- Khi transaction abort, log kết quả abort cùng transaction context và nguyên nhân.

Không đặt tên log published_and_committed trong callback của từng lần send() nếu transaction chưa commit. Điều này khiến dashboard và điều tra sự cố kết luận sai rằng consumer chắc chắn sẽ đọc được record.

## 5. Logging trong @KafkaListener

Consumer cần log metadata của record trước hoặc sau xử lý. Có thể nhận trực tiếp ConsumerRecord để lấy topic, partition, offset, key, timestamp và headers:

```java
@Component
public class OrderListener {

    private static final Logger log =
            LoggerFactory.getLogger(OrderListener.class);

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "orders-projection-listener",
            topics = "orders.created.v1",
            groupId = "orders-projection"
    )
    public void onOrder(ConsumerRecord<String, OrderCreated> record) {
        OrderCreated event = record.value();
        String eventId = event.eventId();

        if (eventId != null) {
            MDC.put("eventId", eventId);
        }
        try {
            log.debug(
                    "kafka.consume.started groupId={} topic={} " +
                    "partition={} offset={} key={}",
                    "orders-projection",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    record.key());

            orderService.process(event);

            log.debug(
                    "kafka.consume.processed eventId={} groupId={} " +
                    "topic={} partition={} offset={}",
                    eventId,
                    "orders-projection",
                    record.topic(),
                    record.partition(),
                    record.offset());
        }
        catch (RuntimeException exception) {
            log.error(
                    "kafka.consume.failed eventId={} groupId={} " +
                    "topic={} partition={} offset={} exceptionType={}",
                    eventId,
                    "orders-projection",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    exception.getClass().getSimpleName(),
                    exception);
            throw exception;
        }
        finally {
            if (eventId != null) {
                MDC.remove("eventId");
            }
        }
    }
}
```

Ví dụ log started và processed ở DEBUG để tránh ghi hai dòng INFO cho mọi record ở throughput cao. Log lỗi có stack trace được ghi tại listener boundary; nếu error handler cũng ghi cùng exception ở ERROR, hãy chọn một nơi làm chủ stack trace để tránh nhân đôi log.

Không bắt exception rồi bỏ qua. Khi listener cần retry, exception phải được truyền tới container/error handler theo đúng policy. Nếu code catch exception và không ném lại, Spring Kafka có thể xem listener đã hoàn tất bình thường và xử lý offset theo AckMode đang cấu hình.

## 6. Log processed không có nghĩa offset đã commit

Đây là điểm rất quan trọng khi đọc log consumer.

Một dòng kafka.consume.processed chỉ cho biết method listener đã chạy hết phần xử lý nghiệp vụ và không ném exception. Nó không tự chứng minh offset đã được broker commit.

Ví dụ:

1. Listener cập nhật database thành công.
2. Listener ghi log processed.
3. JVM dừng trước khi offset được commit.
4. Consumer khởi động lại và nhận lại record.
5. Cùng event có thể xuất hiện thêm một dòng processed.

Do đó:

- Dùng processed cho kết quả xử lý ở tầng listener.
- Chỉ log offset_committed khi có bằng chứng từ callback/event phù hợp với AckMode và commit strategy thực tế.
- Không suy luận commit thành công chỉ từ log cuối method.
- Thiết kế consumer idempotent để chịu được redelivery.

Với AckMode.RECORD, BATCH, MANUAL hoặc MANUAL_IMMEDIATE, thời điểm commit khác nhau. Logging phải phản ánh cấu hình thực tế, không gắn một ý nghĩa commit chung cho mọi listener.

## 7. Event ID và correlation ID

Event ID nên được tạo ở nơi phát sinh event và giữ nguyên khi retry ở tầng ứng dụng hoặc replay. Correlation ID có thể nối nhiều event cùng một nghiệp vụ; trace ID nối các span trong distributed trace.

Ví dụ:

```json
{
  "eventId": "evt-2026-000184",
  "correlationId": "order-flow-42",
  "orderId": "order-42",
  "eventType": "OrderCreated"
}
```

Các ID này có vai trò khác nhau:

| ID | Mục đích |
|---|---|
| eventId | Nhận diện một event nghiệp vụ |
| correlationId | Liên kết nhiều bước hoặc nhiều event của một workflow |
| traceId | Liên kết trace phân tán |
| spanId | Nhận diện một operation trong trace |

Không dùng email, số điện thoại, account number hoặc token làm correlation ID. Chọn ID ngẫu nhiên/opaque, không chứa dữ liệu cá nhân.

Nếu producer gửi cùng event qua retry, giữ nguyên eventId. Nếu tạo một event nghiệp vụ mới, tạo ID mới. Điều này giúp phân biệt application resend với hai event khác nhau có payload giống nhau.

## 8. Dùng MDC để đưa ngữ cảnh vào mọi dòng log

MDC (Mapped Diagnostic Context) cho phép gắn các field như eventId, correlationId, traceId vào log mà không phải truyền chúng vào từng câu lệnh logger.

Ví dụ:

```java
if (event.eventId() != null) {
    MDC.put("eventId", event.eventId());
}
if (event.correlationId() != null) {
    MDC.put("correlationId", event.correlationId());
}
try {
    orderService.process(event);
}
finally {
    if (event.eventId() != null) {
        MDC.remove("eventId");
    }
    if (event.correlationId() != null) {
        MDC.remove("correlationId");
    }
}
```

Phải xóa MDC trong finally. Kafka listener thường chạy trên thread được tái sử dụng; nếu không xóa, event tiếp theo có thể nhận nhầm eventId hoặc correlationId của record trước. Tương tự, callback của CompletableFuture do Kafka producer hoàn tất trên thread callback của producer; MDC từ thread gọi KafkaTemplate.send() không tự động được truyền sang đó. Nếu cần trace/event context trong callback, hãy capture context lúc gửi rồi restore và dọn context trong callback bằng cơ chế propagation có kiểm soát.

Nếu listener chuyển xử lý sang executor hoặc CompletableFuture, MDC không tự động được bảo đảm truyền sang thread khác. Cần dùng cơ chế context propagation/TaskDecorator hoặc capture và restore context ở ranh giới executor. Không copy MDC mà quên khôi phục context cũ của thread đích.

Với ứng dụng có Micrometer Tracing hoặc OpenTelemetry, để instrumentation quản lý trace context và bridge sang MDC. Tránh tự tạo trace ID giả hoặc tự parse header tùy ý khi đã có tracing library.

## 9. Đọc correlation metadata từ Kafka header

Header có thể mang event-id, correlation-id hoặc W3C trace context. Ví dụ lấy một header:

```java
Header header = record.headers().lastHeader("event-id");
String headerEventId = header == null
        ? null
        : new String(header.value(), StandardCharsets.UTF_8);
```

Nếu payload đã có event ID, hãy thống nhất nguồn dữ liệu chuẩn. Không âm thầm dùng payload ID ở producer nhưng header ID ở consumer nếu hai giá trị có thể lệch nhau.

Header có thể do producer bên ngoài gửi vào, nên xem là dữ liệu đầu vào không đáng tin cậy:

- Validate độ dài và định dạng.
- Loại bỏ ký tự xuống dòng/control character trước khi ghi log.
- Không log toàn bộ headers vì có thể chứa token hoặc dữ liệu riêng tư.
- Không dùng header do client gửi để quyết định quyền truy cập.

Trace context nên được propagation bằng chuẩn W3C thông qua tracing instrumentation tương thích, thay vì tự đặt một header tùy ý rồi coi đó là distributed tracing đầy đủ.

## 10. Cấu hình logging level cho Spring Kafka

Có thể điều chỉnh logger bằng application.yml:

```yaml
logging:
  level:
    root: INFO
    com.example.messaging: INFO
    org.springframework.kafka: INFO
    org.apache.kafka: WARN
```

Thay com.example.messaging bằng package của ứng dụng. Mức khởi đầu thường hợp lý:

- Application publisher/listener: INFO cho sự kiện quan trọng, DEBUG cho từng record thành công.
- org.springframework.kafka: INFO để quan sát lifecycle và cấu hình; tăng DEBUG tạm thời khi điều tra.
- org.apache.kafka: WARN trong production trừ khi cần điều tra lỗi client cụ thể.

Không bật TRACE cho toàn bộ org.apache.kafka hoặc org.springframework.kafka trong thời gian dài ở production. Log client ở mức quá chi tiết có thể tăng dung lượng rất nhanh và lộ metadata nội bộ.

Khi bật DEBUG tạm thời:

1. Giới hạn package/class cần điều tra.
2. Đặt thời gian bật rõ ràng.
3. Theo dõi log volume và latency.
4. Tắt lại sau khi có đủ bằng chứng.

## 11. Đưa MDC vào console pattern

Với Logback, Spring Boot cho phép tùy chỉnh console pattern:

```yaml
logging:
  pattern:
    console: "%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [%thread] traceId=%X{traceId:-} eventId=%X{eventId:-} %logger{36} - %msg%n"
```

Khi MDC có eventId, log sẽ hiển thị field đó trên từng dòng. Khi không có, pattern dùng giá trị mặc định rỗng.

Trong hệ thống production, thường nên xuất log dạng JSON với các field riêng thay vì chỉ dựa vào chuỗi text. Log platform có thể lọc theo eventId, topic, partition, offset, groupId, traceId mà không cần regex phức tạp.

## 12. Structured logging

Structured logging giúp hệ thống log tập trung parse field ổn định. Một record log có thể có dạng:

```json
{
  "timestamp": "2026-11-17T09:30:12.420Z",
  "level": "INFO",
  "service": "order-service",
  "event": "kafka.publish.acknowledged",
  "eventId": "evt-2026-000184",
  "topic": "orders.created.v1",
  "partition": 2,
  "offset": 98124,
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Tên field nên thống nhất giữa các service. Không lúc ghi topicName, lúc ghi destination, lúc lại ghi kafkaTopic nếu tất cả cùng biểu thị topic hiện tại.

Nếu dùng JSON encoder cho Logback, cấu hình encoder và dependency theo logging stack của dự án. Không tự serialize toàn bộ object message thành JSON log; structured logging nên chứa field allowlist đã chọn.

## 13. Chọn log level theo mức độ

| Level | Dùng cho Kafka messaging | Ví dụ |
|---|---|---|
| ERROR | Thao tác thất bại cần điều tra hoặc can thiệp | Publish cuối cùng thất bại, DLT publish lỗi, listener lỗi không phục hồi |
| WARN | Tình huống bất thường nhưng hệ thống có thể tiếp tục | Retry attempt, rebalance bất thường, consumer gần timeout |
| INFO | Sự kiện vận hành quan trọng, ít xảy ra | Listener start/stop, transaction commit, cấu hình consumer group |
| DEBUG | Chi tiết xử lý từng record hoặc từng attempt | Consume start/success, metadata đầy đủ |
| TRACE | Chi tiết protocol/client rất sâu | Chỉ bật ngắn hạn khi điều tra có mục tiêu |

Không nên log mọi record thành INFO nếu topic có hàng nghìn hoặc hàng triệu record mỗi phút. Có thể dùng DEBUG cho record-level logs, INFO cho summary định kỳ và ERROR cho lỗi cuối cùng.

## 14. Logging khi retry và error handling

Một record có thể được giao nhiều lần do blocking retry, non-blocking retry, rebalance hoặc crash trước commit. Vì vậy, nhiều dòng log cho cùng event ID không tự động có nghĩa producer đã publish duplicate.

Khi log retry, nên có:

- eventId.
- Topic hiện tại, partition và offset.
- Topic gốc nếu đang xử lý retry/DLT record.
- Exception class.
- Attempt hiện tại và giới hạn attempt nếu có.
- Retry destination hoặc backoff nếu hệ thống cung cấp metadata.

Ví dụ thông điệp:

```text
WARN kafka.consume.retry eventId=evt-2026-000184
     topic=orders-retry-1000 partition=1 offset=72
     originalTopic=orders.created.v1
     attempt=2 exceptionType=InventoryUnavailableException
```

Không log toàn bộ stack trace ở mọi attempt nếu lỗi transient xảy ra với tần suất cao. Có thể log attempt ở WARN/DEBUG và chỉ ghi stack trace đầy đủ khi hết retry hoặc có lỗi không mong đợi. Cần bảo đảm không làm mất thông tin exception cuối cùng.

Nếu listener tự log exception rồi ném lại, error handler có thể tiếp tục log cùng lỗi. Chọn một nơi làm chủ log stack trace cuối cùng: listener boundary hoặc error handler/recoverer. Các tầng khác chỉ log metadata ở DEBUG nếu cần.

## 15. Logging khi đưa record vào DLT

DLT là điểm kết thúc của một nhánh xử lý lỗi, nên log cần đủ thông tin để vận hành replay:

| Field | Mục đích |
|---|---|
| eventId | Tra event nghiệp vụ |
| originalTopic | Topic nguồn |
| originalPartition, originalOffset | Vị trí record ban đầu |
| dltTopic, dltPartition, dltOffset | Vị trí record sau khi publish DLT nếu có |
| exceptionType | Nhóm lỗi |
| attempts | Số lần xử lý đã thực hiện |
| recoveryOutcome | DLT publish thành công hay thất bại |

Chỉ ghi dlt.published sau khi recoverer xác nhận publish thành công. Nếu DLT publish thất bại, phải log lỗi recovery và giữ cơ chế xử lý lỗi theo cấu hình; không log như thể record đã được lưu an toàn.

Không ghi payload hoặc exception message chứa dữ liệu nhạy cảm vào log DLT. Stack trace, SQL message và HTTP response có thể chứa dữ liệu đầu vào hoặc credential.

## 16. Logging trong batch listener

Với batch listener, log một dòng summary cho batch thường hiệu quả hơn log từng record ở INFO:

```java
@KafkaListener(
        topics = "orders",
        groupId = "orders-batch",
        containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderCreated>> records) {
    if (records.isEmpty()) {
        return;
    }

    ConsumerRecord<String, OrderCreated> first = records.get(0);
    long partitionCount = records.stream()
            .map(ConsumerRecord::partition)
            .distinct()
            .count();

    log.info(
            "kafka.consume.batch.started groupId={} topic={} " +
            "recordCount={} partitionCount={} firstPartition={}",
            "orders-batch",
            first.topic(),
            records.size(),
            partitionCount,
            first.partition());

    orderService.processBatch(
            records.stream().map(ConsumerRecord::value).toList());

    log.info(
            "kafka.consume.batch.processed groupId={} topic={} recordCount={}",
            "orders-batch",
            first.topic(),
            records.size());
}
```

Ví dụ ghi số partition xuất hiện trong batch và metadata của record đầu tiên. Nếu cần log offset range, hãy group theo topic-partition trước; một batch poll có thể chứa record từ nhiều partition và offset không nhất thiết liên tục.

Nếu batch có một record lỗi, log thêm vị trí record gây lỗi theo semantics của listener/error handler. Tránh log toàn bộ danh sách payload.

## 17. Logging lifecycle và rebalance của consumer

Log nghiệp vụ không đủ để giải thích tại sao consumer ngừng nhận record. Cần theo dõi lifecycle container và consumer group:

- Listener/container started và stopped.
- Consumer paused và resumed.
- Partition assignment và revocation.
- Rebalance bắt đầu/kết thúc.
- Consumer không poll hoặc không phản hồi đúng hạn.
- Authentication, authorization hoặc broker connectivity failure.

Spring Kafka phát application events cho một số thay đổi lifecycle, ví dụ ConsumerPausedEvent, ConsumerResumedEvent, ListenerContainerIdleEvent và NonResponsiveConsumerEvent. Có thể dùng @EventListener để log listener ID, container ID và thông tin liên quan; kiểm tra event API của version Spring Kafka đang dùng trước khi truy cập chi tiết cụ thể.

Khi partition bị revoke, cần log assignment cũ và lý do nếu có. Khi được assign lại, log danh sách partition mới. Điều này giúp liên hệ các lần redelivery với rebalance thay vì kết luận nhầm là producer gửi lặp.

Không log mỗi poll thành công ở INFO. Dùng lifecycle event, rebalance callback và metric consumer để quan sát mà không làm log volume tăng theo tốc độ poll.

## 18. Phân biệt logging, metrics và tracing

Ba tín hiệu này bổ sung cho nhau:

| Tín hiệu | Trả lời | Ví dụ |
|---|---|---|
| Logs | Điều gì đã xảy ra với một record cụ thể? | Event evt-1001 lỗi tại offset 42 vì timeout |
| Metrics | Vấn đề xảy ra nhiều tới mức nào? | Retry rate tăng, consumer lag tăng, publish latency p99 |
| Traces | Request đi qua các service theo đường nào? | API → order service → Kafka publish → inventory consumer |

Không tạo metric label bằng event ID, order ID hoặc offset vì cardinality sẽ tăng rất cao. Dùng những dimension có tập giá trị giới hạn như service, topic, result, exception family hoặc consumer group theo quy hoạch.

Log có thể chứa ID cụ thể để tra cứu. Metric nên tổng hợp. Trace nên thể hiện quan hệ giữa các operation, không chứa payload nhạy cảm.

## 19. Logging không được làm lộ dữ liệu nhạy cảm

Không log toàn bộ event hoặc tất cả Kafka headers theo mặc định. Payload có thể chứa email, địa chỉ, số tài khoản, token, thông tin thanh toán hoặc dữ liệu cá nhân.

Nên áp dụng:

- Log event ID, topic, partition, offset và kết quả; chỉ thêm business key nếu được phép.
- Dùng allowlist cho field được phép log.
- Mask hoặc tokenize dữ liệu cần hiển thị một phần.
- Không log password, SASL JAAS config, access token, cookie, private key hoặc secret.
- Redact exception message nếu có thể chứa request/response body.
- Giới hạn quyền đọc log và retention của log platform.
- Sanitize giá trị do user kiểm soát để tránh log injection.

Ví dụ masking:

```java
String maskedEmail = email == null
        ? null
        : email.replaceAll("(^.).*(@.*$)", "$1***$2");

log.info("customer.contact eventId={} email={}", eventId, maskedEmail);
```

Masking phải phù hợp policy và không được xem là anonymization. Nếu không cần email để vận hành, tốt hơn là không log email.

## 20. Tránh log injection và log volume không kiểm soát

Record key, header và field payload có thể do hệ thống bên ngoài gửi vào. Nếu ghi trực tiếp chuỗi chứa newline hoặc control character, attacker có thể làm giả nhiều dòng log hoặc gây nhiễu truy vấn.

Hãy validate/sanitize giá trị không tin cậy trước khi log:

- Giới hạn độ dài.
- Loại bỏ CR/LF và control character không cần thiết.
- Không nối chuỗi log bằng dữ liệu user tùy ý.
- Dùng parameterized logging ({}) để tránh format không an toàn.
- Không log payload lớn hoặc binary.

Với topic throughput cao, kiểm soát volume bằng DEBUG, sampling hoặc log summary. Không dùng sampling cho audit event bắt buộc phải lưu; audit cần pipeline và retention riêng.

## 21. Kiểm thử logging

Logging có thể được kiểm thử ở cấp unit và integration:

1. Producer log acknowledged chỉ sau khi future hoàn tất thành công.
2. Producer log failed khi future hoàn tất exceptionally.
3. Producer log submit_failed khi API ném lỗi đồng bộ.
4. Consumer log đúng topic, partition, offset, group ID và event ID.
5. Consumer exception được truyền tới error handler, không bị nuốt.
6. MDC được xóa sau khi listener hoàn tất hoặc ném exception.
7. Log không chứa payload, password, token hoặc field bị cấm.
8. Retry log phân biệt topic gốc với retry topic hiện tại.
9. DLT log chỉ báo recovery thành công sau khi publish được xác nhận.
10. Transaction log phân biệt record gửi trong transaction và transaction commit.

Có thể dùng Logback ListAppender hoặc output capture để kiểm tra message/structured fields. Với integration test, dùng broker test để xác minh metadata producer và consumer. Không assert toàn bộ stack trace hoặc timestamp tuyệt đối vì chúng thay đổi theo runtime.

## 22. Các lỗi thường gặp

**Log send() thành công ngay sau khi gọi API:** future chưa hoàn tất; chuyển log thành submitted và chỉ log acknowledged trong callback thành công.

**Consumer log processed nhưng record vẫn được giao lại:** listener hoàn tất không đồng nghĩa offset đã commit. Kiểm tra AckMode, commit timing và crash window.

**Cùng event ID có nhiều log:** có thể do retry, redelivery hoặc application resend. Đối chiếu topic/partition/offset và attempt trước khi kết luận duplicate.

**MDC của record trước xuất hiện ở record sau:** thiếu MDC.remove() trong finally hoặc context không được restore đúng trên executor.

**Log chứa payload hoặc token:** thay log object bằng allowlist metadata; redaction phải được áp dụng ở cả exception/APM.

**Mỗi retry ghi nhiều stack trace:** nhiều tầng cùng log một exception. Chọn một tầng sở hữu stack trace cuối cùng và giảm log ở các tầng còn lại.

**Không biết record đến từ retry topic nào:** log topic hiện tại cùng original topic/partition/offset khi metadata có sẵn.

**Không tìm được record bằng offset:** chỉ log offset mà thiếu topic và partition. Luôn ghi đủ bộ ba.

**Bật DEBUG cho toàn bộ Kafka client trong production:** log volume tăng nhanh. Chỉ bật logger cần thiết trong thời gian điều tra.

**Metric dùng event ID làm label:** cardinality tăng không giới hạn. Giữ ID trong log/trace, dùng metric dimension có tập giá trị nhỏ.

## 23. Checklist production

- Producer có log submitted, acknowledged và failed rõ ràng.
- Consumer log event ID, group ID, topic, partition, offset và kết quả xử lý.
- Log xử lý nghiệp vụ được phân biệt với offset commit.
- Transactional send được phân biệt với transaction commit.
- Event ID và correlation ID ổn định xuyên service.
- MDC được thiết lập và dọn trong finally; async context có propagation rõ ràng.
- Retry và DLT log có attempt, exception type và original record location.
- Listener lifecycle, pause/resume và rebalance được quan sát.
- Log level không tạo record-level INFO quá lớn.
- Structured fields có naming thống nhất.
- Payload, secret, PII và header nhạy cảm không bị log ngoài policy.
- User-controlled values được sanitize để tránh log injection.
- Log retention, access control và audit phù hợp dữ liệu.
- Metric và trace được dùng bổ sung, không thay log.
- Có test cho success, failure, retry, DLT, MDC cleanup và redaction.

Logging producer và consumer tốt phải giúp nối được event nghiệp vụ với vị trí Kafka và kết quả xử lý. Hãy dùng event ID cùng topic/partition/offset, ghi kết quả gửi sau khi future hoàn tất, ghi kết quả listener theo đúng semantics commit, và luôn dọn MDC. Kết hợp log với metric và trace, đồng thời giới hạn payload/secret trong log để hệ thống vừa dễ điều tra vừa an toàn khi vận hành.

## Tài liệu tham khảo

- [Spring for Apache Kafka – Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
- [Spring for Apache Kafka – Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Boot – Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [SLF4J – Manual](https://www.slf4j.org/manual.html)

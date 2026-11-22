# Log topic, partition và offset

Trong Spring Kafka, một log như “đã xử lý OrderCreated” thường chưa đủ để điều tra sự cố. Một topic có thể chứa hàng triệu records, nhiều partition được xử lý đồng thời bởi nhiều consumer instances, và cùng một business event có thể xuất hiện lại sau retry hoặc DLT replay. Để tìm đúng record, đối chiếu thứ tự xử lý và xác định tiến độ consumer, log cần có ba tọa độ Kafka cơ bản: **topic, partition và offset**.

- **Topic** cho biết record thuộc luồng dữ liệu nào.
- **Partition** xác định log phân vùng nơi record được lưu và thứ tự được duy trì.
- **Offset** xác định vị trí của record trong partition đó.

Trong Spring Kafka, các thông tin này có sẵn trên `ConsumerRecord` khi listener nhận record. Có thể ghi chúng bằng SLF4J, đưa vào structured JSON logs, gắn vào MDC để mọi log trong cùng invocation có cùng context, và dùng metadata của producer để truy vết nơi output được ghi. Bài học tập trung vào cách ghi log có ích, diễn giải offset đúng, và giữ được nguồn gốc record khi retry/recovery.

## 1. Ba tọa độ cơ bản của một Kafka record

Một Kafka record được xác định về mặt vị trí bằng bộ ba:

~~~text
(topic, partition, offset)
~~~

Ví dụ:

~~~text
topic=orders.created
partition=3
offset=1842
~~~

Điều này có nghĩa record nằm trong partition 3 của topic `orders.created` tại offset 1842.

| Thuộc tính | Ý nghĩa | Phạm vi |
|---|---|---|
| Topic | Luồng dữ liệu Kafka | Tên topic |
| Partition | Một log có thứ tự bên trong topic | Chỉ có ý nghĩa cùng topic |
| Offset | Vị trí record trong partition | Tăng theo log của partition |

Một record có thể được log như sau:

~~~text
event=consumed topic=orders.created partition=3 offset=1842
~~~

Bộ ba này là **tọa độ record vật lý trong Kafka**. Nó rất hữu ích để tìm record, so sánh log consumer và kiểm tra offset trong công cụ Kafka. Nhưng nó không phải business identity: nếu cùng event được publish lại, record mới có thể có partition/offset khác dù `eventId` vẫn giữ nguyên.

## 2. Topic không phải consumer group

Topic mô tả nơi records được lưu. Consumer group mô tả nhóm consumer cùng phối hợp chia partition và duy trì tiến độ đọc.

Ví dụ:

~~~text
Topic: orders.created
  partition 0
  partition 1
  partition 2

Consumer group: order-projection
  consumer A -> partition 0
  consumer B -> partition 1, 2
~~~

Một topic có thể được nhiều consumer groups độc lập đọc. Mỗi group có committed offsets riêng, vì vậy log cần thêm group ID khi chẩn đoán tiến độ.

| Giá trị | Trả lời câu hỏi |
|---|---|
| Topic | Record thuộc luồng nào? |
| Partition | Record nằm ở phân vùng nào? |
| Offset | Record ở vị trí nào trong partition? |
| Consumer group | Nhóm nào đang đọc và commit tiến độ? |
| Consumer/client ID | Instance/client nào đang thực hiện thao tác? |
| Event ID | Đây là business event nào? |

`ConsumerRecord` cung cấp topic, partition và offset, nhưng **không phải lúc nào cũng cung cấp consumer group ID**. Group ID thường đến từ cấu hình listener/container hoặc metadata của ứng dụng. Đừng lấy client ID rồi ghi vào field group ID; đó là hai khái niệm khác nhau.

## 3. Offset có ý nghĩa trong phạm vi partition

Offset là vị trí của record trong một partition. Nó không phải số thứ tự toàn cục của topic.

~~~text
orders.created partition 0:
  offset 0 -> event A
  offset 1 -> event B
  offset 2 -> event C

orders.created partition 1:
  offset 0 -> event D
  offset 1 -> event E
  offset 2 -> event F
~~~

Offset 2 ở partition 0 và offset 2 ở partition 1 là hai records khác nhau. Vì vậy, log chỉ có `offset=2` là không đủ để định danh record.

Cũng không thể so sánh offset giữa các partitions để kết luận record nào xảy ra trước trên toàn topic. Kafka bảo đảm thứ tự trong một partition; nếu nghiệp vụ cần thứ tự theo aggregate, producer thường dùng key ổn định để records cùng aggregate đi vào cùng partition.

## 4. Offset không nhất thiết liên tục trong dữ liệu consumer nhìn thấy

Offset tăng theo log partition, nhưng consumer không nên giả định những record nó đọc được luôn có offset liên tiếp. Các nguyên nhân có thể gồm:

- Log compaction giữ lại record mới nhất theo key và loại bỏ các phiên bản cũ.
- Transactional records bị abort và không hiển thị với consumer `read_committed`.
- Retention xóa các records cũ.
- Consumer bắt đầu đọc từ một offset khác theo committed position hoặc reset policy.

Ví dụ:

~~~text
Log offsets vật lý:
  100, 101, 102, 103, 104, 105

Consumer read_committed nhìn thấy:
  100, 101,      103,      105
~~~

Khoảng trống offset không tự chứng minh consumer bị mất dữ liệu. Khi điều tra, hãy xem isolation level, compaction, retention và transaction state.

## 5. Đọc metadata trực tiếp từ ConsumerRecord

Với record listener, cách rõ ràng nhất là nhận `ConsumerRecord<K,V>` thay vì chỉ nhận payload:

~~~java
@Component
public class OrderListener {

    private static final Logger log =
            LoggerFactory.getLogger(OrderListener.class);

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "orders-listener",
        topics = "orders.created",
        groupId = "order-projection")
    public void onMessage(
            ConsumerRecord<String, OrderCreated> record) {

        log.info(
            "Kafka record received topic={} partition={} offset={} key={} timestamp={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key(),
            record.timestamp()
        );

        orderService.apply(record.value());
    }
}
~~~

Các method thường dùng:

| Method | Giá trị |
|---|---|
| `record.topic()` | Tên topic |
| `record.partition()` | Partition number |
| `record.offset()` | Offset của record |
| `record.key()` | Kafka key |
| `record.value()` | Deserialized payload |
| `record.timestamp()` | Timestamp của record theo Kafka |
| `record.timestampType()` | Loại timestamp |
| `record.headers()` | Kafka headers |
| `record.serializedKeySize()` | Kích thước key đã serialize |
| `record.serializedValueSize()` | Kích thước value đã serialize |

Không phải mọi field đều phù hợp để log. Key có thể chứa customer ID hoặc thông tin nhạy cảm; value có thể chứa dữ liệu cá nhân. Thường nên log topic/partition/offset/timestamp và một business correlation ID đã được phê duyệt, không log toàn bộ payload.

## 6. Log metadata bằng Spring Message headers

Nếu listener nhận payload thay vì ConsumerRecord, Spring Kafka có thể map metadata thành message headers:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-projection")
public void onMessage(
        OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    log.info(
        "Order event received topic={} partition={} offset={} eventId={}",
        topic,
        partition,
        offset,
        event.eventId()
    );

    orderService.apply(event);
}
~~~

Các constants `KafkaHeaders.RECEIVED_TOPIC`, `RECEIVED_PARTITION` và `OFFSET` giúp tránh hardcode tên header. Import tùy phiên bản Spring Kafka thường nằm trong `org.springframework.kafka.support.KafkaHeaders`.

Dùng header mapping khi listener chỉ cần payload và một vài metadata. Dùng `ConsumerRecord` khi cần thêm key, timestamp, headers, serialized sizes hoặc muốn có toàn bộ record context.

Nếu header không tồn tại hoặc method signature không tương thích với listener type, Spring có thể không resolve được argument. Kiểm tra kiểu dữ liệu được map và API của phiên bản Spring Kafka đang dùng.

## 7. Phân biệt record offset với committed consumer offset

Đây là một trong những nhầm lẫn phổ biến nhất khi đọc log.

Giả sử listener vừa nhận record offset 42:

~~~text
ConsumerRecord.offset() = 42
~~~

Khi consumer group xác nhận đã xử lý record này, committed offset thường là **43**, tức vị trí tiếp theo mà consumer group sẽ đọc. Vì vậy:

- Record offset là vị trí của record hiện tại.
- Consumer position là vị trí consumer sẽ đọc tiếp trong phiên hiện tại.
- Committed group offset là tiến độ đã được lưu bền vững cho group.
- Ba giá trị có liên quan nhưng không đồng nhất.

Ví dụ:

~~~text
Record vừa xử lý:      offset 42
Committed offset:      43
Record tiếp theo:      offset 43 (nếu có record ở vị trí đó)
~~~

Nếu log ghi `record offset=42`, đừng gọi nó là “committed offset 42” trừ khi bạn thực sự đang log giá trị commit. Với `AckMode.RECORD`, `BATCH`, `MANUAL` hoặc transaction, thời điểm commit có thể khác nhau.

## 8. Log lúc nhận record và lúc xử lý hoàn tất

Nên phân biệt ít nhất hai sự kiện:

~~~text
event=record_received topic=orders.created partition=3 offset=1842
event=record_processed topic=orders.created partition=3 offset=1842 result=success
~~~

Ví dụ:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-projection")
public void onMessage(
        ConsumerRecord<String, OrderCreated> record) {

    log.info(
        "Kafka record received topic={} partition={} offset={}",
        record.topic(),
        record.partition(),
        record.offset()
    );

    orderService.apply(record.value());

    log.info(
        "Kafka record processing completed topic={} partition={} offset={} result=success",
        record.topic(),
        record.partition(),
        record.offset()
    );
}
~~~

Khi `orderService.apply` trả về bình thường, log completed có thể phản ánh DB service transaction đã commit nếu service được gọi qua Spring proxy và transaction kết thúc trước khi proxy trả về.

Nhưng với Kafka transactional listener, **listener method trả về chưa có nghĩa container đã commit Kafka transaction**. Container còn phải đưa offset vào transaction và commit. Vì vậy log nên dùng từ ngữ chính xác như `listener_processing_completed`, không khẳng định `kafka_transaction_committed` nếu chưa quan sát commit outcome.

## 9. Log lỗi phải giữ nguyên topic, partition và offset

Khi listener ném exception, log cần giúp operator xác định record lỗi mà không cần in payload.

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-projection")
public void onMessage(
        ConsumerRecord<String, OrderCreated> record) {

    try {
        orderService.apply(record.value());
    } catch (RuntimeException ex) {
        log.error(
            "Kafka record processing failed topic={} partition={} offset={} exceptionType={}",
            record.topic(),
            record.partition(),
            record.offset(),
            ex.getClass().getSimpleName(),
            ex
        );
        throw ex;
    }
}
~~~

Ném lại exception giúp container error handler thực hiện retry/recovery theo cấu hình. Nếu chỉ log rồi return bình thường, listener có thể được coi là thành công và offset tiến lên dù business write thất bại.

Không log cùng một stack trace ở mọi tầng mà không có chủ đích. Nếu listener log error, error handler cũng log, và DLT recoverer log lần nữa, một lỗi duy nhất có thể tạo nhiều bản ghi giống nhau. Chọn một tầng sở hữu log đầy đủ và các tầng khác ghi metadata ngắn gọn.

## 10. Dùng MDC để gắn record context cho toàn bộ log trong invocation

MDC (Mapped Diagnostic Context) cho phép thêm các trường như topic, partition, offset và event ID vào mọi log được ghi trong scope hiện tại.

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-projection")
public void onMessage(
        ConsumerRecord<String, OrderCreated> record) {

    try (MDC.MDCCloseable topic =
                 MDC.putCloseable("kafka.topic", record.topic());
         MDC.MDCCloseable partition =
                 MDC.putCloseable("kafka.partition",
                                  Integer.toString(record.partition()));
         MDC.MDCCloseable offset =
                 MDC.putCloseable("kafka.offset",
                                  Long.toString(record.offset()));
         MDC.MDCCloseable eventId =
                 MDC.putCloseable("event.id",
                                  record.value().eventId().toString())) {

        log.info("Processing order event");
        orderService.apply(record.value());
        log.info("Order event processing completed");
    }
}
~~~

`MDC.putCloseable` có trong SLF4J 2.x. Nếu ứng dụng dùng SLF4J version cũ, có thể dùng `MDC.put` và `MDC.remove` trong `try/finally`.

Ví dụ fallback:

~~~java
MDC.put("kafka.topic", record.topic());
MDC.put("kafka.partition", Integer.toString(record.partition()));
MDC.put("kafka.offset", Long.toString(record.offset()));

try {
    orderService.apply(record.value());
} finally {
    MDC.remove("kafka.topic");
    MDC.remove("kafka.partition");
    MDC.remove("kafka.offset");
}
~~~

**Luôn xóa MDC sau invocation.** Consumer threads được tái sử dụng cho nhiều records. Nếu không clear, record tiếp theo có thể ghi log với topic/offset của record trước đó.

## 11. MDC và asynchronous processing

MDC thường gắn với thread hiện tại. Nếu listener submit công việc sang executor khác:

~~~java
@KafkaListener(topics = "orders.created")
public void onMessage(ConsumerRecord<String, OrderCreated> record) {
    MDC.put("kafka.offset", Long.toString(record.offset()));

    CompletableFuture.runAsync(() -> {
        log.info("Applying order projection");
        orderService.apply(record.value());
    });

    MDC.remove("kafka.offset");
}
~~~

Log trong async task có thể **không có MDC** vì task chạy trên thread khác. Ngoài ra listener trả về trước khi task hoàn tất có thể khiến container commit offset trước khi business work kết thúc, dẫn tới rủi ro mất xử lý.

Nếu dùng async processing:

- Xác định rõ listener có chờ task hoàn tất hay không.
- Sử dụng executor/context propagation phù hợp nếu cần giữ MDC hoặc trace context.
- Không truyền Kafka `Consumer` sang thread khác.
- Đảm bảo lỗi async được chuyển thành kết quả xử lý mà container hiểu.
- Không ack/commit offset trước khi side effect bắt buộc hoàn tất.

MDC là công cụ tương quan log, không phải transaction context và không tự bảo vệ thread safety.

## 12. Structured logging thay vì ghép chuỗi tự do

Một log text tốt có key-value fields ổn định:

~~~text
event=record_processed
listener=orders-listener
group=order-projection
topic=orders.created
partition=3
offset=1842
event_id=evt-91fe
result=success
duration_ms=27
~~~

Với JSON logging, một record có thể trông như:

~~~json
{
  "timestamp": "2026-11-15T10:20:30.120Z",
  "level": "INFO",
  "message": "Kafka record processing completed",
  "event": "record_processed",
  "listener": "orders-listener",
  "consumer_group": "order-projection",
  "topic": "orders.created",
  "partition": 3,
  "offset": 1842,
  "event_id": "evt-91fe",
  "result": "success",
  "duration_ms": 27
}
~~~

Lợi ích:

- Log search có thể filter theo topic, partition và offset.
- Operator có thể ghép log giữa producer, consumer và DLT.
- Dashboard có thể thống kê error events theo listener hoặc topic.
- Trường metadata có kiểu dữ liệu nhất quán, tránh parse text tự do.

Không đưa các fields thay đổi theo từng record vào metric labels. Structured log có thể chứa event ID/offset để tìm kiếm; Prometheus labels cần cardinality thấp hơn nhiều.

## 13. Nên log những field nào?

Một schema gợi ý:

| Field | Nguồn | Mục đích |
|---|---|---|
| event | Ứng dụng định nghĩa | record_received, record_processed, record_failed |
| listener | Listener/container ID | Xác định handler |
| consumer_group | Cấu hình container | Xác định tiến độ group |
| topic | ConsumerRecord.topic() | Luồng dữ liệu |
| partition | ConsumerRecord.partition() | Phân vùng |
| record_offset | ConsumerRecord.offset() | Vị trí record |
| key | ConsumerRecord.key() | Chỉ log nếu được phép |
| event_id | Business payload/header | Correlation xuyên retry/replay |
| trace_id | Tracing context | Liên kết spans/logs |
| result | Ứng dụng | success, failure, recovered |
| duration_ms | Timer/Stopwatch | Thời gian invocation |
| attempt | Retry metadata | Số lần thử nếu có nguồn đáng tin |
| exception_type | Exception classifier | Phân loại lỗi |
| instance | Deployment metadata | Pod/host xử lý |

Không phải mọi log đều cần đủ field. Một log nhận record có thể có topic/partition/offset/event ID; một log lỗi cần thêm exception type; một log recovery cần original coordinates và destination topic.

## 14. Không log payload và thông tin nhạy cảm theo mặc định

Kafka value có thể chứa email, số điện thoại, địa chỉ, thông tin tài chính, token hoặc dữ liệu khách hàng. Log toàn bộ `record.value()` có thể đưa dữ liệu nhạy cảm vào hệ thống log với retention và quyền truy cập khác với database.

Thay vào đó:

- Log topic, partition, offset và event type.
- Dùng business event ID đã được phê duyệt.
- Nếu cần key, xác định key có chứa PII hay không.
- Tránh log raw headers vì có thể chứa authorization hoặc trace baggage.
- Với payload lỗi, log schema/version và exception class; giữ raw bytes ở quarantine/DLT theo chính sách riêng.
- Redact dữ liệu trước khi ghi nếu một số field thật sự cần thiết cho điều tra.

Một ví dụ không an toàn:

~~~java
log.error("Failed to process record: {}", record, exception);
~~~

`ConsumerRecord.toString()` có thể hiển thị key/value/headers tùy implementation. Nên chọn rõ các metadata an toàn:

~~~java
log.error(
    "Record failed topic={} partition={} offset={} exceptionType={}",
    record.topic(),
    record.partition(),
    record.offset(),
    exception.getClass().getSimpleName(),
    exception
);
~~~

## 15. Log producer metadata để biết record được ghi ở đâu

Ở phía producer, topic có thể được chọn trong lệnh send, nhưng partition thực tế và offset chỉ có sau khi broker xác nhận record được ghi.

Với Spring Kafka 3.x, `KafkaTemplate.send` trả về `CompletableFuture<SendResult<K,V>>`:

~~~java
public void publish(OrderCreated event) {
    kafkaTemplate.send(
        "orders.created",
        event.orderId(),
        event
    ).whenComplete((result, exception) -> {
        if (exception != null) {
            log.error(
                "Kafka publish failed topic={} eventId={}",
                "orders.created",
                event.eventId(),
                exception
            );
            return;
        }

        RecordMetadata metadata = result.getRecordMetadata();

        log.info(
            "Kafka publish acknowledged topic={} partition={} offset={} eventId={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset(),
            event.eventId()
        );
    });
}
~~~

`RecordMetadata` cung cấp topic, partition, offset và các thông tin liên quan đến record đã được broker acknowledge.

Đối với Spring Kafka cũ hơn, API send có thể trả về `ListenableFuture`; cú pháp callback khác. Kiểm tra phiên bản thay vì copy `CompletableFuture` example vào project dùng API cũ.

**Không block consumer thread bằng `future.get()` chỉ để lấy offset** nếu không có lý do rõ ràng. Callback bất đồng bộ thường phù hợp hơn. Nếu producer send nằm trong Kafka transaction, log broker acknowledge của send không tự chứng minh transaction cuối cùng đã commit.

## 16. Key và partition routing

Producer key thường quyết định partition khi dùng partitioner mặc định và không chỉ định partition tường minh. Ví dụ key là `orderId` giúp records của cùng order đi vào cùng partition, qua đó duy trì thứ tự tương đối cho aggregate đó.

~~~java
kafkaTemplate.send(
    "orders.created",
    event.orderId(),
    event
);
~~~

Khi log producer, cần phân biệt:

- **Requested topic:** topic mà ứng dụng yêu cầu gửi.
- **Requested partition:** partition tường minh nếu producer chỉ định.
- **Acknowledged partition:** partition thực tế trong `RecordMetadata`.
- **Key:** giá trị routing/business key.
- **Offset:** vị trí được broker gán trong partition.

Nếu partition count thay đổi hoặc partitioner/config thay đổi, mapping key-to-partition có thể thay đổi theo thời gian. Không dùng log partition của một record cũ để kết luận mọi records cùng key sẽ luôn ở partition đó sau migration.

## 17. Retry có thể tạo tọa độ mới

Khi record lỗi được forward sang retry topic, nó trở thành record trên topic/partition/offset khác:

~~~text
Original:
  orders.created-3@1842

Forwarded retry:
  orders.created-retry-1000-1@205

DLT:
  orders.created.DLT-0@71
~~~

Đây là các **tọa độ vật lý khác nhau** có thể cùng mang một business event ID. Vì vậy, khi log retry cần lưu cả:

- Current topic/partition/offset.
- Original topic/partition/offset nếu có metadata.
- Business event ID ổn định.
- Retry attempt hoặc delivery metadata nếu được cung cấp.
- Destination topic khi forward.

Spring Kafka cung cấp các headers liên quan đến DLT như `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `DLT_ORIGINAL_PARTITION` và `DLT_ORIGINAL_OFFSET` trong những phiên bản hỗ trợ. Khi dùng recoverer, hãy kiểm tra header constants/API của phiên bản đang chạy.

Đừng ghi current offset của DLT như thể đó là original offset. Hai field nên có tên khác nhau trong structured logs.

## 18. Log trong error handler và DLT recoverer

`DefaultErrorHandler` điều phối retry và recovery. Có thể thêm recoverer để log record coordinates khi record được đưa tới bước phục hồi:

~~~java
ConsumerRecordRecoverer loggingRecoverer = (record, exception) -> {
    log.error(
        "Kafka record recovery invoked topic={} partition={} offset={} exceptionType={}",
        record.topic(),
        record.partition(),
        record.offset(),
        exception.getClass().getSimpleName(),
        exception
    );

    deadLetterPublishingRecoverer.accept(record, exception);
};

DefaultErrorHandler errorHandler = new DefaultErrorHandler(
    loggingRecoverer,
    new FixedBackOff(1_000L, 2L)
);
~~~

`deadLetterPublishingRecoverer` là một `DeadLetterPublishingRecoverer` được cấu hình riêng. Ví dụ trên minh họa điểm log khi recoverer được gọi; nó không thay thế việc kiểm tra DLT publish thành công. Cần quan sát kết quả send/recovery theo policy thực tế.

Tùy phiên bản Spring Kafka, factory gắn error handler qua `setCommonErrorHandler` hoặc API cũ hơn. Đối với transactional listener, after-rollback processor và recovery transaction có semantics riêng; không áp dụng ví dụ non-transactional một cách máy móc.

## 19. Log offset trong batch listener

Batch listener nhận nhiều records trong một lần invocation. Một log chỉ có một offset có thể gây hiểu nhầm nếu batch chứa records từ nhiều partitions.

Ví dụ:

~~~java
@KafkaListener(
    id = "orders-batch-listener",
    topics = "orders.created",
    groupId = "order-batch-projection",
    containerFactory = "batchListenerFactory")
public void onBatch(
        List<ConsumerRecord<String, OrderCreated>> records) {

    log.info(
        "Kafka batch received listener={} recordCount={}",
        "orders-batch-listener",
        records.size()
    );

    for (ConsumerRecord<String, OrderCreated> record : records) {
        log.debug(
            "Batch record topic={} partition={} offset={}",
            record.topic(),
            record.partition(),
            record.offset()
        );
    }

    orderBatchService.apply(records);
}
~~~

Batch có thể chứa records từ nhiều partitions. Nếu cần tóm tắt, nhóm theo `topic + partition` và log:

- Record count mỗi partition.
- Offset thấp nhất và cao nhất trong batch.
- Event ID hoặc correlation IDs theo chính sách.
- Batch invocation ID để liên kết các logs.

Không log duy nhất `minOffset=10, maxOffset=50` rồi giả định mọi offset 10–50 đều nằm trong batch. Compaction, transaction visibility và batch composition có thể tạo khoảng trống.

## 20. Thứ tự trong partition và log sequence

Kafka đảm bảo thứ tự đọc trong một partition theo offset. Nếu một consumer log:

~~~text
orders.created-2@100
orders.created-2@101
orders.created-2@102
~~~

đây là một chuỗi record theo vị trí log. Tuy nhiên, log lines có thể xuất hiện không đúng thứ tự offset khi:

- Nhiều consumer threads ghi đồng thời vào một log sink.
- Logging async/buffer flush làm thứ tự hiển thị thay đổi.
- Application xử lý bất đồng bộ sau khi listener trả về.
- Một record được retry và hoàn tất muộn hơn record có offset lớn hơn.
- Log aggregator nhận events từ nhiều pods với độ trễ khác nhau.

Khi điều tra ordering, dùng topic/partition/offset làm trật tự nguồn, không dựa duy nhất vào thứ tự dòng trong Kibana/Splunk/Loki. Nếu business ordering theo aggregate, bổ sung event sequence/version.

## 21. Correlation giữa Kafka coordinates và business event ID

Hai loại ID nên được log song song:

~~~text
topic=orders.created
partition=3
offset=1842
event_id=evt-91fe
order_id=ord-913
~~~

- Kafka coordinates giúp tìm record cụ thể.
- `event_id` giúp tìm cùng business event xuyên retry, DLT, republish và nhiều topics.
- `order_id` xác định aggregate nhưng có thể có nhiều events hợp lệ.

Nếu cùng event ID xuất hiện ở hai offsets khác nhau, đó có thể là producer duplicate hoặc intentional replay. Không kết luận chỉ từ việc offset khác nhau.

Trace ID là một loại correlation khác. Một event có thể được replay trong một trace mới; trace ID không thay event ID làm idempotency key.

## 22. Consumer group và committed offset trong log

Khi log tiến độ commit, nên ghi rõ đó là **committed offset** và consumer group:

~~~text
event=offset_commit
consumer_group=order-projection
topic=orders.created
partition=3
committed_offset=1843
~~~

Đừng dùng cùng field `offset` cho cả record offset và committed offset. Có thể đặt tên tường minh:

| Field | Ý nghĩa |
|---|---|
| record_offset | Offset của record listener đang xử lý |
| committed_offset | Offset được xác nhận cho consumer group |
| consumer_position | Vị trí consumer sẽ đọc tiếp trong phiên hiện tại |
| original_offset | Offset record nguồn trước retry/DLT |
| destination_offset | Offset record được ghi sang topic khác |

Với auto commit, record/batch ack mode, manual ack và Kafka transactions, commit timing khác nhau. Nếu log commit callback hoặc container event, phải xác định chính xác API nào tạo thông tin và giá trị đó là offset nào.

Không log `record.offset() + 1` như committed offset trừ khi bạn đang mô tả đúng record đã được commit theo semantics của container và không có các record trước đó chưa xử lý. Trong batch hoặc out-of-order processing, phép cộng đơn giản này có thể sai.

## 23. Offset và AckMode

`AckMode` quyết định container xác nhận offset theo cách nào. Những mode phổ biến:

| Ack mode | Ý nghĩa khái quát |
|---|---|
| `RECORD` | Commit khi mỗi record listener xử lý xong |
| `BATCH` | Commit sau khi tất cả records trong poll batch được xử lý |
| `TIME` | Commit theo thời gian và số records phù hợp |
| `COUNT` | Commit sau số records đã xử lý theo ngưỡng |
| `MANUAL` | Application gọi acknowledge; commit theo batch semantics |
| `MANUAL_IMMEDIATE` | Acknowledge có thể commit ngay tùy thread và cấu hình |

Khi đọc log record offset, không thể suy ra committed offset ngay tại thời điểm log nhận record. Nếu listener xử lý xong nhưng batch chưa hoàn tất, offset chưa chắc đã commit.

Với manual acknowledgment, không gọi `acknowledge()` trước khi business work hoàn tất. Nếu DB commit thành công nhưng Kafka offset chưa commit do crash, record có thể được giao lại; database cần idempotency.

## 24. Kafka transaction và log commit

Trong listener container transactional, Kafka output records và input offset có thể nằm trong cùng Kafka transaction. Một log ở listener:

~~~text
event=listener_processing_completed
topic=orders.created partition=3 offset=1842
~~~

chỉ cho biết method đã trả về bình thường theo quan sát của application. Nó **không nhất thiết chứng minh Kafka transaction đã commit**. Sau đó container còn thực hiện việc đưa offset vào transaction và commit.

Nên phân biệt log events:

~~~text
record_received
listener_processing_completed
kafka_transaction_commit_succeeded
kafka_transaction_rollback
record_recovered
~~~

Các event commit/rollback cần được ghi từ tầng có thông tin transaction outcome thực tế, không tự suy diễn bằng cách log ngay cuối listener.

Với consumer downstream dùng `read_committed`, output chỉ được nhìn thấy sau transaction commit. Một producer send callback thành công trước commit không có nghĩa downstream đã có thể đọc output đó.

## 25. Producer RecordMetadata và consumer ConsumerRecord có thể ghép thế nào?

Producer nhận `RecordMetadata` sau khi broker acknowledge:

~~~java
RecordMetadata metadata = sendResult.getRecordMetadata();

log.info(
    "Kafka output acknowledged topic={} partition={} offset={}",
    metadata.topic(),
    metadata.partition(),
    metadata.offset()
);
~~~

Consumer nhận `ConsumerRecord`:

~~~java
log.info(
    "Kafka input received topic={} partition={} offset={}",
    record.topic(),
    record.partition(),
    record.offset()
);
~~~

Nếu hai log có cùng topic/partition/offset trong cùng cluster và cùng record, operator có thể ghép chúng. Nhưng không nên dùng offset làm correlation xuyên hai topics. Khi service transform input topic A sang output topic B, output offset là một vị trí mới; cần giữ `eventId`/correlation ID để liên kết business flow.

## 26. Logging khi producer send thất bại

Producer send có thể thất bại trước khi nhận metadata broker. Khi đó không có acknowledged partition/offset đáng tin để log như kết quả thành công.

~~~java
kafkaTemplate.send("orders.created", event.orderId(), event)
    .whenComplete((result, exception) -> {
        if (exception != null) {
            log.error(
                "Kafka send failed topic={} eventId={}",
                "orders.created",
                event.eventId(),
                exception
            );
            return;
        }

        RecordMetadata metadata = result.getRecordMetadata();

        log.info(
            "Kafka send acknowledged topic={} partition={} offset={} eventId={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset(),
            event.eventId()
        );
    });
~~~

Không log partition/offset là `0` khi send fail chỉ để tránh null. Hãy để chúng absent hoặc ghi trạng thái `not_acknowledged`. Nếu producer retry nội bộ trước khi callback thất bại, callback failure là kết quả cuối cùng của send operation; cần dùng producer metrics/logs để điều tra attempts bên trong client.

## 27. Log khi forward sang retry topic hoặc DLT

Khi recover một record, nên phân biệt source và destination:

~~~text
event=record_forwarded
original_topic=orders.created
original_partition=3
original_offset=1842
destination_topic=orders.created.DLT
destination_partition=0
destination_offset=71
event_id=evt-91fe
reason=non_retryable
~~~

Destination offset chỉ có sau khi publish DLT được broker acknowledge. Nếu DLT publish asynchronous, log `forward_requested` trước send và `forward_acknowledged` sau callback; đừng ghi destination offset trước khi có metadata.

Với retry topic, giữ original coordinates trong headers nếu framework/recoverer hỗ trợ. Khi đọc lại từ retry topic, log cả current coordinates và original coordinates. Điều này cho phép operator tìm được record đầu tiên và toàn bộ lineage của event.

## 28. Log metadata từ DLT headers

Spring Kafka có các DLT headers để giữ thông tin nguồn, thường gồm:

- `KafkaHeaders.DLT_ORIGINAL_TOPIC`.
- `KafkaHeaders.DLT_ORIGINAL_PARTITION`.
- `KafkaHeaders.DLT_ORIGINAL_OFFSET`.
- `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP` trong các phiên bản hỗ trợ.
- Exception metadata headers do recoverer cấu hình.

Một DLT listener có thể đọc headers:

~~~java
@KafkaListener(
    topics = "orders.created.DLT",
    groupId = "orders-dlt-inspector")
public void inspect(
        ConsumerRecord<String, OrderCreated> record) {

    Header originalTopic =
            record.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC);

    Header originalPartition =
            record.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_PARTITION);

    Header originalOffset =
            record.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_OFFSET);

    log.error(
        "DLT record currentTopic={} currentPartition={} currentOffset={} originalTopicHeaderPresent={} originalPartitionHeaderPresent={} originalOffsetHeaderPresent={}",
        record.topic(),
        record.partition(),
        record.offset(),
        originalTopic != null,
        originalPartition != null,
        originalOffset != null
    );
}
~~~

Ví dụ trên chỉ log sự hiện diện của headers để tránh giả định encoding/deserialize của header values. Nếu cần giá trị thực, đọc byte arrays theo API/version và xử lý trường hợp header thiếu hoặc malformed. Không ép cast header value thành `String` hoặc `Integer` khi Kafka headers lưu raw bytes.

## 29. Log assignment và rebalance để đặt record context vào đúng consumer

Topic/partition/offset cho biết record ở đâu, nhưng khi điều tra “consumer nào đang giữ partition”, cần thêm thông tin group membership/assignment. Spring Kafka cung cấp rebalance listeners và container events để quan sát assignment/revocation.

Một log assignment có thể có dạng:

~~~text
event=partitions_assigned
listener=orders-listener
consumer_group=order-projection
partitions=[orders.created-0, orders.created-1]
instance=orders-pod-2
~~~

Không nhầm log assignment với record processing. Consumer có thể được assign partition nhưng chưa nhận record; topic có thể rỗng hoặc committed offset đã ở cuối log.

Khi partition bị revoke, log thông tin assignment cũ và lifecycle event để phân tích rebalance. Không ghi danh sách partitions vào một metric label dạng chuỗi động nếu số lượng/assignment thay đổi liên tục.

## 30. Không dùng offset làm metric label

Offset thay đổi theo từng record. Nếu gắn `offset` vào Micrometer tag hoặc Prometheus label, gần như mỗi record sẽ tạo một time series mới.

Không nên:

~~~java
Timer.builder("kafka.record.processing")
    .tag("topic", record.topic())
    .tag("partition", Integer.toString(record.partition()))
    .tag("offset", Long.toString(record.offset()))
    .register(registry);
~~~

Nên dùng metrics với dimensions có cardinality thấp:

~~~java
Timer.builder("kafka.record.processing")
    .tag("topic", record.topic())
    .tag("listener", "orders-listener")
    .tag("result", "success")
    .register(registry);
~~~

Offset phù hợp trong **logs/traces**, nơi có thể tìm theo một record cụ thể. Metrics nên thống kê latency/count theo topic, listener, partition (nếu số partition hữu hạn và được kiểm soát) và result.

## 31. Log volume và sampling

Một consumer xử lý 50.000 records/giây mà ghi một log INFO cho mỗi record có thể tạo hàng triệu log entries mỗi phút. Điều đó làm tăng chi phí storage, network và khả năng operator bỏ lỡ lỗi quan trọng.

Một chiến lược thường dùng:

| Loại log | Level gợi ý | Nội dung |
|---|---|---|
| Listener lifecycle/start/stop | INFO | Listener ID, group, instance |
| Mỗi record nhận được | DEBUG hoặc INFO có kiểm soát | Topic/partition/offset/event ID |
| Xử lý thành công | DEBUG hoặc sampled INFO | Coordinates + duration |
| Lỗi record | ERROR/WARN theo policy | Coordinates + exception |
| Retry attempt | WARN/INFO có rate limit | Coordinates + attempt |
| DLT recovery | ERROR hoặc WARN | Original + destination coordinates |
| Offset/commit lifecycle | DEBUG/INFO khi cần | Group, partition, committed offset |

Không sampling hoặc rate-limit lỗi theo cách làm mất toàn bộ thông tin sự cố nghiêm trọng. Có thể giảm success logs nhưng vẫn giữ failure logs, DLT logs và structured metrics.

Nếu dùng asynchronous logging, cần kiểm tra queue full/discard policy; lúc tải cao nhất, log lỗi có thể bị drop đúng lúc cần nhất.

## 32. Tạo một helper để log record context nhất quán

Để không lặp lại chuỗi format ở nhiều listeners, có thể tạo value object nhỏ:

~~~java
public record KafkaRecordCoordinates(
        String topic,
        int partition,
        long offset) {

    public static KafkaRecordCoordinates from(
            ConsumerRecord<?, ?> record) {
        return new KafkaRecordCoordinates(
            record.topic(),
            record.partition(),
            record.offset()
        );
    }
}
~~~

Sử dụng:

~~~java
KafkaRecordCoordinates coordinates =
        KafkaRecordCoordinates.from(record);

log.info(
    "Kafka record failed topic={} partition={} offset={}",
    coordinates.topic(),
    coordinates.partition(),
    coordinates.offset(),
    exception
);
~~~

Helper này chỉ đóng gói metadata vật lý; nó không chứa payload, không thay event ID và không đại diện cho committed group offset. Có thể bổ sung method tạo map cho structured logging, nhưng tránh đưa dynamic fields vào metric tags.

Nếu ứng dụng cần log source coordinates của retry/DLT, tạo type riêng cho `originalCoordinates` để không nhầm với coordinates hiện tại.

## 33. Kiểm tra log bằng Kafka command-line tools

Khi đã có topic/partition/offset trong log, operator có thể dùng Kafka tools để kiểm tra log theo vị trí. Tùy phiên bản Kafka, lệnh thường dùng gồm:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server kafka.example:9092 \
  --topic orders.created \
  --partition 3 \
  --offset 1842 \
  --max-messages 1
~~~

Lệnh minh họa đọc từ partition 3, offset 1842. Tùy Kafka CLI version, có thể cần thêm consumer properties, isolation level hoặc các tham số khác. Với topic transactional, consumer cần isolation phù hợp để thấy record đúng như ứng dụng production.

Để kiểm tra committed group offsets, dùng công cụ consumer groups:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example:9092 \
  --group order-projection \
  --describe
~~~

Lệnh group describe thường cho biết current offset, log-end offset và lag theo partition. Đây là thông tin tiến độ của group, không phải payload record ở một offset cụ thể.

Không chạy các lệnh reset offset trong production chỉ để điều tra. `--reset-offsets` có thể thay đổi tiến độ consumer group; chỉ sử dụng theo runbook có phê duyệt và audit.

## 34. Kiểm tra log trong môi trường có compaction và transactions

Nếu operator không tìm thấy record tại một offset đã log, hãy xem:

- Topic có `cleanup.policy=compact` không?
- Record key có bị ghi đè bởi một record mới hơn không?
- Retention đã xóa segment chứa record cũ chưa?
- Consumer đang dùng `read_committed` và record thuộc transaction abort không?
- Topic đã bị xóa/recreated kể từ khi log được ghi không?
- Cluster/bootstrap endpoint có đúng không?
- Partition count hoặc topic name có thay đổi trong migration không?

Log coordinates là bằng chứng vị trí **tại thời điểm record tồn tại**, không bảo đảm record luôn còn trong log vô hạn. Nếu cần audit dài hạn, lưu business event ID và audit data trong hệ thống bền vững phù hợp, không dựa vào Kafka retention như kho lưu trữ bất biến.

## 35. Phân biệt timestamp với offset

`ConsumerRecord.timestamp()` trả timestamp gắn với record theo Kafka. Timestamp có thể dựa trên producer create time hoặc broker log append time tùy topic configuration.

Offset không phải timestamp và cũng không thể chuyển thành thời gian bằng cách suy luận.

~~~text
topic=orders.created
partition=3
offset=1842
timestamp=1763202000123
timestampType=CREATE_TIME
~~~

Timestamp hữu ích để điều tra event age, nhưng cần hiểu nguồn:

- `CreateTime`: timestamp được gắn bởi producer.
- `LogAppendTime`: timestamp được broker ghi khi append, nếu topic dùng policy đó.
- Clock skew của producer có thể khiến create time không phản ánh thời gian thực chính xác.
- Timestamp không thay thế offset trong việc xác định thứ tự partition.

Log cả timestamp type nếu thời gian sự kiện là trọng yếu.

## 36. Bảo mật và tính nhất quán của log fields

Các quy tắc thực tế:

1. Dùng tên field thống nhất: `topic`, `partition`, `offset`, `consumer_group`.
2. Phân biệt `record_offset` và `committed_offset`.
3. Giữ số nguyên cho partition/offset trong JSON logs, không stringify nếu backend hỗ trợ numeric types.
4. Không log raw payload, secrets hoặc authorization headers.
5. Chỉ log key khi đã xác định nó không chứa PII.
6. Dùng event ID cho correlation nhưng kiểm soát quyền truy cập và retention.
7. Ghi exception type/cause, không chỉ exception message tự do.
8. Không biến offset/event ID thành metrics labels.
9. Giữ current và original coordinates riêng trong retry/DLT logs.
10. Có log schema/version nếu downstream search phụ thuộc field names.

Khi đổi schema log, hãy giữ compatibility cho dashboards và runbooks hoặc cập nhật chúng cùng release.

## 37. Ví dụ log end-to-end cho một record

Một flow có thể tạo các logs sau:

~~~text
event=producer_send_requested
topic=orders.created
event_id=evt-91fe
order_id=ord-913

event=producer_send_acknowledged
topic=orders.created
partition=3
offset=1842
event_id=evt-91fe

event=consumer_record_received
listener=orders-listener
consumer_group=order-projection
topic=orders.created
partition=3
offset=1842
event_id=evt-91fe

event=listener_processing_completed
listener=orders-listener
topic=orders.created
partition=3
offset=1842
event_id=evt-91fe
duration_ms=27
result=success

event=record_forwarded
original_topic=orders.created
original_partition=3
original_offset=1842
destination_topic=orders.created.DLT
destination_partition=0
destination_offset=71
event_id=evt-91fe
reason=non_retryable
~~~

Đây là các log events thuộc những tình huống khác nhau; không phải một record vừa được xử lý thành công lại vừa được chuyển DLT. Mỗi dòng minh họa một lifecycle branch hoặc stage khác nhau. Trong production, log schema phải bảo đảm các sự kiện có thể ghép qua event ID và trace context.

## 38. Runbook: tìm một record từ log coordinates

Khi nhận ticket chứa `topic=orders.created partition=3 offset=1842`:

1. Xác nhận cluster/environment và topic name.
2. Xác nhận partition tồn tại và topic chưa bị recreate.
3. Kiểm tra retention/compaction và isolation level.
4. Tìm record tại partition/offset bằng Kafka tooling được phép.
5. Tìm structured logs có cùng topic/partition/offset.
6. Tìm event ID trong log để theo dõi retry/DLT/output.
7. Xác định consumer group và instance đã xử lý record.
8. So sánh record offset với committed offset của group.
9. Xem error handler/retry logs và DLT metadata.
10. Nếu DB side effect bị trùng, kiểm tra idempotency key trong database.
11. Nếu output Kafka thiếu, kiểm tra producer metadata và transaction commit/rollback.
12. Ghi lại kết quả điều tra bằng source coordinates và business event ID.

Không reset offset trước khi xác định record đã được commit hay side effect đã xảy ra; replay có thể tạo duplicate nếu DB không idempotent.

## 39. Runbook: log offset lặp hoặc nhảy bất thường

**Cùng topic/partition/offset xuất hiện nhiều lần:** có thể do log ở các tầng khác nhau, listener retry, log duplication từ aggregator hoặc cùng record được xử lý lại. Kiểm tra event type và attempt metadata trước khi kết luận broker tạo duplicate.

**Offset tăng nhưng có khoảng trống:** xem compaction, aborted transactions, retention và consumer isolation. Khoảng trống không tự chứng minh record bị mất.

**Hai pods log cùng record coordinates:** có thể do redelivery sau rebalance hoặc log một record ở nhiều stages. Kiểm tra consumer group assignment, commit timing và instance ID.

**Offset giảm:** có thể do consumer seek/replay, reset group offset hoặc đọc topic khác/cluster khác. Tìm audit của offset reset, retry/DLT và bootstrap config.

**Offset giống nhau nhưng event ID khác:** có thể đang so sánh hai topics/partitions khác nhau hoặc dữ liệu log bị gắn sai metadata. Kiểm tra toàn bộ bộ ba topic/partition/offset.

## 40. Runbook: producer log có offset nhưng consumer không thấy record

1. Xác nhận producer và consumer dùng cùng Kafka cluster.
2. Xác nhận topic name và partition.
3. Kiểm tra send callback là acknowledged success hay chỉ log trước khi gửi.
4. Nếu dùng transaction, kiểm tra transaction commit/abort; consumer `read_committed` chỉ thấy committed output.
5. Kiểm tra consumer group assignment và committed offset.
6. Kiểm tra consumer có seek vượt qua offset đó không.
7. Kiểm tra topic retention/compaction.
8. Kiểm tra ACL và deserialization errors.
9. Kiểm tra consumer đang pause hoặc lag/assignment bất thường.
10. Dùng Kafka CLI với isolation level phù hợp để xác minh record.
11. Tìm trace/event ID trong retry/DLT topics nếu record đã được forward.
12. Không kết luận producer log sai chỉ vì consumer group hiện tại đã đọc qua offset đó.

Producer acknowledgement xác nhận broker đã nhận write theo semantics producer; nó không tự chứng minh mọi consumer group đều sẽ nhìn thấy record trong mọi thời điểm.

## 41. Những sai lầm thường gặp

### Chỉ log offset mà bỏ topic/partition

Offset chỉ có nghĩa trong một partition. Luôn log đủ bộ ba.

### Coi offset là event ID

Republish cùng business event tạo offset mới. Dùng event ID ổn định để correlation/dedup.

### Coi record offset là committed offset

Record offset là vị trí record; committed offset thường là vị trí tiếp theo cần đọc. Dùng tên field rõ ràng.

### Log success trước khi xử lý hoàn tất

Nếu log ngay đầu listener, không thể dùng dòng đó làm bằng chứng business operation đã thành công.

### Log success đồng nghĩa Kafka transaction đã commit

Listener method trả về và transaction commit là hai mốc khác nhau. Cần log commit outcome từ tầng có thông tin thật.

### Log toàn bộ ConsumerRecord

Có thể làm lộ payload, PII và headers nhạy cảm. Chọn metadata an toàn.

### Đưa offset vào Prometheus tag

Mỗi record tạo time series mới, làm bùng cardinality. Offset thuộc logs/traces.

### Dựa vào thứ tự log lines để kết luận thứ tự Kafka

Async logging và nhiều consumer threads có thể làm thứ tự hiển thị khác offset order. Dùng coordinates.

### Không giữ original coordinates khi retry/DLT

Không thể liên kết record mới với record nguồn nếu chỉ log destination offset.

### Quên clear MDC

Consumer thread tái sử dụng; log record sau có thể mang metadata record trước.

## 42. Checklist triển khai

- [ ] Log đầy đủ topic, partition và record offset.
- [ ] Bổ sung listener ID, consumer group và instance ID theo nhu cầu điều tra.
- [ ] Dùng ConsumerRecord khi cần toàn bộ record metadata.
- [ ] Dùng KafkaHeaders constants nếu listener nhận Spring Message/payload.
- [ ] Phân biệt record offset, consumer position và committed offset.
- [ ] Log riêng received, processing completed, failed và recovered.
- [ ] Không ghi success trước khi business work hoàn tất.
- [ ] Không tuyên bố Kafka transaction committed từ cuối listener method.
- [ ] Log producer topic/partition/offset từ RecordMetadata sau acknowledgement.
- [ ] Giữ current và original coordinates riêng trong retry/DLT.
- [ ] Dùng MDC có cleanup trong finally/try-with-resources.
- [ ] Có context propagation nếu async task cần correlation.
- [ ] Structured logs có field names và types nhất quán.
- [ ] Không log payload, secrets hoặc PII theo mặc định.
- [ ] Không dùng offset/event ID làm metric labels.
- [ ] Giữ log volume trong ngân sách và bảo toàn lỗi quan trọng.
- [ ] Có runbook dùng coordinates để tìm record và đối chiếu committed offsets.
- [ ] Kiểm tra retention, compaction và transaction isolation khi không tìm thấy record.

## 43. Nguồn tham khảo

- [Apache Kafka — ConsumerRecord API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/consumer/ConsumerRecord.html)
- [Apache Kafka — RecordMetadata API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/producer/RecordMetadata.html)
- [Spring for Apache Kafka — Listener Annotation](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
- [Spring for Apache Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)

**Kết luận:** Log topic, partition và offset tạo ra một địa chỉ có thể kiểm chứng cho từng Kafka record. Trong Spring Kafka, lấy metadata trực tiếp từ `ConsumerRecord` hoặc các `KafkaHeaders`, ghi structured logs với listener/group/event context, và phân biệt rõ record offset với committed group offset. Ở producer, chỉ ghi partition/offset sau khi nhận `RecordMetadata`; ở retry/DLT, giữ cả current lẫn original coordinates. Khi kết hợp với event ID, trace context, error handling và consumer lag, những logs này giúp operator tìm đúng record, hiểu redelivery và xác định tiến độ xử lý mà không phải log toàn bộ payload hay suy đoán từ thứ tự log lines.

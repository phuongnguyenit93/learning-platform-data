# Nhận List<ConsumerRecord> trong listener

## Mục tiêu của bài học

Trong chương **Batch và throughput**, bài này hướng dẫn nhận một lô Kafka record trong cùng một lần gọi listener bằng kiểu `List<ConsumerRecord<K, V>>` của Spring Kafka. Mỗi phần tử giữ metadata của record như topic, partition, offset, key, value, timestamp và headers, nhờ đó ứng dụng có thể xử lý dữ liệu theo lô mà vẫn truy cập được thông tin của từng bản ghi.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Batch listener giúp giảm chi phí gọi listener và có thể tăng throughput khi xử lý theo lô phù hợp, nhưng cần kiểm soát commit, lỗi từng record và thời gian xử lý.

Sau bài học, người học có thể:

- Phân biệt record listener với batch listener.
- Cấu hình `ConcurrentKafkaListenerContainerFactory` để gọi listener theo batch.
- Khai báo phương thức nhận `List<ConsumerRecord<K, V>>`.
- Đọc key, value, topic, partition, offset, timestamp và headers của từng record.
- Hiểu mối quan hệ giữa batch size, `max.poll.records`, partition và concurrency.
- Chọn acknowledgment mode và xử lý offset phù hợp với batch.
- Xử lý lỗi ở một record trong batch bằng `BatchListenerFailedException`.
- Kiểm thử batch listener và chẩn đoán các vấn đề throughput.

## 1. Record listener và batch listener

Spring Kafka hỗ trợ hai cách gọi listener phổ biến.

**Record listener** nhận từng bản ghi:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

**Batch listener** nhận nhiều bản ghi trong một lần gọi:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "batchListenerContainerFactory"
)
public void listen(List<ConsumerRecord<String, OrderCreated>> records) {
    for (ConsumerRecord<String, OrderCreated> record : records) {
        billingService.process(record.value());
    }
}
~~~

Với record listener, container gọi phương thức cho từng record. Với batch listener, container gom các record nhận được trong một lần poll và truyền chúng vào phương thức dưới dạng một danh sách.

| Tiêu chí | Record listener | Batch listener |
|---|---|---|
| Tham số listener | Một payload hoặc một `ConsumerRecord` | `List<Payload>` hoặc `List<ConsumerRecord>` |
| Số lần gọi | Thường một lần cho mỗi record | Một lần cho một batch được poll |
| Truy cập metadata | Có nếu nhận `ConsumerRecord` | Có cho từng phần tử nếu nhận `List<ConsumerRecord>` |
| Xử lý theo lô | Ứng dụng tự gom hoặc xử lý riêng | Có thể xử lý trực tiếp cả batch |
| Xử lý lỗi | Xác định theo record đang gọi | Cần xác định record/index lỗi trong batch |
| Commit | Có thể theo record hoặc cấu hình container | Thường theo batch hoặc manual acknowledgment |

Batch listener không có nghĩa Kafka lưu nhiều record thành một message duy nhất. Mỗi record vẫn là một bản ghi riêng trong partition; Spring Kafka chỉ gom kết quả poll thành một danh sách để gọi listener.

## 2. ConsumerRecord chứa những thông tin gì?

`ConsumerRecord<K, V>` là kiểu dữ liệu của Kafka client đại diện cho một record đã được consumer đọc. Nó giữ payload cùng metadata do Kafka cung cấp.

Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `topic()` | Tên topic |
| `partition()` | Partition chứa record |
| `offset()` | Offset của record trong partition |
| `key()` | Key sau khi deserialize |
| `value()` | Value sau khi deserialize |
| `timestamp()` | Timestamp của record |
| `timestampType()` | Loại timestamp |
| `headers()` | Các Kafka record headers |
| `serializedKeySize()` | Kích thước key đã serialize |
| `serializedValueSize()` | Kích thước value đã serialize |

Ví dụ record:

~~~text
topic     = commerce.order.created
partition = 2
offset    = 105
key       = order-10001
value     = OrderCreated(...)
timestamp = 1794894000000
~~~

Metadata giúp ứng dụng ghi log, trace, đối soát và chẩn đoán lỗi. Ví dụ, khi xử lý một record thất bại, log topic, partition và offset giúp xác định chính xác vị trí dữ liệu cần kiểm tra hoặc replay.

### 2.1. Phân biệt offset với chỉ số trong List

Offset là vị trí của record trong một partition. Chỉ số của phần tử trong Java List chỉ là vị trí record trong batch hiện tại.

Ví dụ:

| List index | Topic partition | Offset |
|---:|---|---:|
| 0 | partition 0 | 101 |
| 1 | partition 1 | 55 |
| 2 | partition 0 | 102 |
| 3 | partition 2 | 8 |

Không thể lấy `listIndex` làm Kafka offset. Một batch có thể chứa record từ nhiều partition và offset của các partition có phạm vi độc lập.

### 2.2. Batch có thể chứa nhiều partition

Nếu consumer được gán nhiều partition, một lần poll có thể trả về record từ nhiều partition. Do đó `List<ConsumerRecord<K, V>>` không nhất thiết chỉ chứa record của một partition.

Kafka bảo đảm thứ tự record trong từng partition. Không có thứ tự toàn cục giữa các partition. Ứng dụng không nên giả định hai record đứng cạnh nhau trong List luôn có quan hệ trước/sau về mặt nghiệp vụ.

Khi cần xử lý theo thứ tự của một aggregate, producer nên dùng key ổn định để các record liên quan được định tuyến vào cùng partition, sau đó consumer xử lý tuần tự trong partition đó.

## 3. Bật batch listener trong ConcurrentKafkaListenerContainerFactory

Để listener nhận danh sách record, factory cần được cấu hình batch mode bằng `setBatchListener(true)`.

Ví dụ:

~~~java
@Configuration
public class KafkaBatchListenerConfiguration {

    @Bean(name = "batchListenerContainerFactory")
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            batchListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setConcurrency(3);

        factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.BATCH);

        return factory;
    }
}
~~~

Các thiết lập quan trọng:

- `setConsumerFactory(...)` cung cấp consumer và deserializer.
- `setBatchListener(true)` yêu cầu container gọi listener theo batch.
- `setConcurrency(3)` tạo tối đa ba child consumer container cho endpoint dùng factory này.
- `AckMode.BATCH` commit offset theo batch sau khi listener xử lý thành công theo semantics của container.

Listener chỉ nhận batch khi endpoint sử dụng đúng factory đã bật batch mode.

### 3.1. Khai báo listener nhận List<ConsumerRecord>

~~~java
@Service
public class OrderBatchListener {

    private final BillingService billingService;

    public OrderBatchListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
        topics = "commerce.order.created",
        groupId = "billing-service",
        containerFactory = "batchListenerContainerFactory"
    )
    public void listen(
            List<ConsumerRecord<String, OrderCreated>> records) {

        for (ConsumerRecord<String, OrderCreated> record : records) {
            billingService.process(record.value());
        }
    }
}
~~~

Kiểu generic mô tả:

- `String`: kiểu key sau khi deserialize.
- `OrderCreated`: kiểu value sau khi deserialize.

Generic của listener phải tương thích với `ConsumerFactory` và deserializer được gắn vào factory. Java generic giúp kiểm tra kiểu ở compile time, nhưng không tự thay đổi cách Kafka deserialize byte.

### 3.2. Nếu không bật batch mode

Nếu listener khai báo `List<ConsumerRecord<...>>` nhưng container factory vẫn chạy record mode, kiểu tham số không khớp với kiểu gọi listener. Ứng dụng có thể lỗi khi khởi tạo endpoint hoặc khi container gọi listener tùy cấu hình và phiên bản.

Hãy kiểm tra endpoint đang dùng factory nào và factory đó đã gọi `setBatchListener(true)` hay chưa.

## 4. Cấu hình consumer và giới hạn batch size

Kafka consumer có thuộc tính `max.poll.records` để giới hạn số record tối đa được trả về trong một lần `poll()`.

Ví dụ:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
~~~

`max-poll-records: 100` có nghĩa một lần poll trả về tối đa 100 record cho consumer. Đây không phải cam kết mọi batch luôn có đúng 100 phần tử. Batch có thể nhỏ hơn do lượng dữ liệu sẵn có, số partition được gán, giới hạn fetch và thời điểm poll.

Một số thuộc tính liên quan:

| Thuộc tính | Tác động |
|---|---|
| `max.poll.records` | Giới hạn số record tối đa trả về trong một poll |
| `fetch.min.bytes` | Lượng dữ liệu broker cố gắng tích lũy trước khi trả fetch response |
| `fetch.max.wait.ms` | Thời gian broker chờ để đáp ứng fetch min bytes |
| `max.partition.fetch.bytes` | Giới hạn dữ liệu fetch từ mỗi partition |
| `max.poll.interval.ms` | Giới hạn thời gian giữa các lần poll |
| `fetch.max.bytes` | Giới hạn dữ liệu tối đa cho một fetch request theo cấu hình client |

Các giới hạn fetch không đồng nghĩa với số phần tử trong List. Kích thước batch thực tế phụ thuộc số record có thể fetch và `max.poll.records`.

### 4.1. Chọn batch size

Batch lớn có thể giảm số lần gọi listener và tận dụng xử lý theo lô ở database hoặc dịch vụ downstream. Tuy nhiên, batch quá lớn có thể:

- Tăng bộ nhớ cần thiết để giữ record.
- Kéo dài thời gian xử lý một lần poll.
- Làm tăng thời gian retry khi batch thất bại.
- Tăng số record phải xử lý lại nếu lỗi ở cuối batch.
- Khiến listener vượt `max.poll.interval.ms`.

Batch nhỏ giảm lượng công việc trong một lần gọi nhưng có thể làm tăng chi phí gọi listener và thao tác downstream.

Hãy đo processing time, consumer lag, batch size thực tế, tỷ lệ lỗi và tải database để chọn giá trị phù hợp.

## 5. Đọc metadata của từng ConsumerRecord

Lợi thế quan trọng của `List<ConsumerRecord<K, V>>` là mỗi phần tử vẫn giữ metadata đầy đủ.

Ví dụ ghi log vị trí record:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "batchListenerContainerFactory"
)
public void listen(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        log.info(
            "Received topic={}, partition={}, offset={}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key()
        );

        billingService.process(record.value());
    }
}
~~~

Metadata này hữu ích khi:

- Ghi nhận record nào gây lỗi.
- Theo dõi độ trễ theo partition.
- Đối chiếu dữ liệu với producer.
- Tạo log có thể truy vết.
- Phân loại record theo topic hoặc header.
- Xử lý nhiều topic trong cùng một listener nếu subscription được thiết kế như vậy.

Không ghi toàn bộ payload nhạy cảm vào log chỉ để debug. Thường chỉ cần topic, partition, offset, key và correlation ID.

### 5.1. Đọc Kafka headers

Kafka record có thể chứa headers dạng cặp tên và byte value.

Ví dụ đọc header `trace-id`:

~~~java
Header traceHeader = record.headers().lastHeader("trace-id");

String traceId = traceHeader == null
    ? null
    : new String(traceHeader.value(), StandardCharsets.UTF_8);
~~~

Khi xử lý batch:

~~~java
for (ConsumerRecord<String, OrderCreated> record : records) {
    Header header = record.headers().lastHeader("trace-id");

    String traceId = header == null
        ? null
        : new String(header.value(), StandardCharsets.UTF_8);

    billingService.process(record.value(), traceId);
}
~~~

Record headers là byte[]. Chỉ chuyển sang String khi producer đã quy định encoding tương ứng, chẳng hạn UTF-8. Với header nhị phân, cần dùng decoder theo đúng format.

### 5.2. Xử lý key và value null

Kafka cho phép record có key null. Với topic compacted, record có key khác null và value null có thể là tombstone dùng để biểu thị việc xóa key.

Vì vậy, không giả định `record.key()` hoặc `record.value()` luôn khác null:

~~~java
for (ConsumerRecord<String, OrderCreated> record : records) {
    if (record.value() == null) {
        handleTombstone(record.key());
        continue;
    }

    billingService.process(record.value());
}
~~~

Nếu topic không dùng tombstone, quy ước xử lý value null vẫn cần được xác định trong hợp đồng event. Không để null value vô tình đi vào business service và gây NullPointerException.

## 6. Phân biệt List<ConsumerRecord> với List<Payload>

Spring Kafka hỗ trợ batch listener nhận payload list hoặc danh sách ConsumerRecord.

**Chỉ nhận payload:**

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "batchPayloadListenerContainerFactory"
)
public void listen(List<OrderCreated> events) {
    billingService.processBatch(events);
}
~~~

**Nhận đầy đủ record:**

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "batchRecordListenerContainerFactory"
)
public void listen(
        List<ConsumerRecord<String, OrderCreated>> records) {
    // Có thể đọc metadata riêng của từng record.
}
~~~

| Tiêu chí | `List<OrderCreated>` | `List<ConsumerRecord<String, OrderCreated>>` |
|---|---|---|
| Payload | Có | Có qua `value()` |
| Key | Không có trong phần tử payload nếu không nằm trong object | Có qua `key()` |
| Topic | Không có trong phần tử payload | Có qua `topic()` |
| Partition | Không có | Có qua `partition()` |
| Offset | Không có | Có qua `offset()` |
| Timestamp | Không có | Có qua `timestamp()` |
| Headers | Không có trực tiếp | Có qua `headers()` |
| Mục đích | Xử lý nghiệp vụ theo danh sách payload | Xử lý theo lô nhưng vẫn cần metadata Kafka |

Nếu nghiệp vụ chỉ cần xử lý danh sách event, `List<Payload>` có thể đơn giản hơn. Nếu cần quan sát offset, partition, key, timestamp hoặc headers, hãy nhận `List<ConsumerRecord<K, V>>`.

## 7. Batch có thể nhận record từ nhiều topic

Một listener có thể subscribe nhiều topic bằng `topics` hoặc `topicPattern`, nếu hợp đồng payload và cách deserialize được thiết kế phù hợp.

Ví dụ:

~~~java
@KafkaListener(
    topics = {
        "commerce.order.created",
        "commerce.order.cancelled"
    },
    groupId = "order-audit-service",
    containerFactory = "batchRecordListenerContainerFactory"
)
public void audit(
        List<ConsumerRecord<String, Object>> records) {

    for (ConsumerRecord<String, Object> record : records) {
        switch (record.topic()) {
            case "commerce.order.created" ->
                auditOrderCreated(record);
            case "commerce.order.cancelled" ->
                auditOrderCancelled(record);
            default ->
                log.warn("Unexpected topic: {}", record.topic());
        }
    }
}
~~~

Cần bảo đảm deserializer hoặc message conversion có thể tạo kiểu value phù hợp với mọi topic mà listener nhận. Dùng `Object` không tự động giải quyết sự khác nhau giữa schema của các event.

Nếu các topic có cấu trúc khác nhau, có thể dùng event envelope chung, type mapping rõ ràng hoặc tách listener theo từng loại event.

## 8. Xử lý batch theo từng record

Có hai cách phổ biến:

1. Xử lý tuần tự từng record trong vòng lặp.
2. Chuyển các payload thành một collection để gọi service hoặc database theo batch.

Xử lý tuần tự:

~~~java
public void listen(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        billingService.process(record.value());
    }
}
~~~

Xử lý theo batch:

~~~java
public void listen(
        List<ConsumerRecord<String, OrderCreated>> records) {

    List<OrderCreated> events = records.stream()
        .map(ConsumerRecord::value)
        .filter(Objects::nonNull)
        .toList();

    billingService.processBatch(events);
}
~~~

Xử lý batch có thể giảm round trip nếu service hỗ trợ bulk operation. Ví dụ database có thể ghi nhiều invoice trong một batch thay vì gọi insert cho từng invoice.

Tuy nhiên, xử lý batch chỉ phù hợp khi các event có thể được xử lý chung và có chiến lược rollback/retry rõ ràng. Nếu một phần tử lỗi, cần biết các phần tử khác đã ghi thành công hay chưa.

### 8.1. Tránh song song hóa tùy tiện trong listener

Không nên đưa tất cả record vào thread pool rồi trả về khỏi listener ngay lập tức nếu container có thể commit offset trước khi công việc thực tế hoàn tất.

Ví dụ nguy hiểm:

~~~java
public void listen(List<ConsumerRecord<String, OrderCreated>> records) {
    records.forEach(record ->
        executor.submit(() -> billingService.process(record.value()))
    );
}
~~~

Listener có thể kết thúc trước khi các task hoàn tất. Container có thể commit offset của batch, sau đó một task thất bại và record không được Kafka giao lại.

Nếu cần xử lý bất đồng bộ, phải chờ toàn bộ công việc hoàn tất trước khi acknowledgment/commit hoặc thiết kế cơ chế quản lý offset và lỗi riêng. Cũng cần kiểm soát thứ tự theo partition nếu nghiệp vụ yêu cầu.

## 9. Acknowledgment và commit offset với batch listener

Với batch listener, container thường dùng `AckMode.BATCH`: sau khi listener xử lý thành công batch được poll, container commit offset tương ứng cho các partition trong batch theo cơ chế của Spring Kafka.

Ví dụ cấu hình:

~~~java
factory.getContainerProperties()
    .setAckMode(ContainerProperties.AckMode.BATCH);
~~~

Một số AckMode:

| AckMode | Ý nghĩa khái quát |
|---|---|
| BATCH | Commit sau khi listener xử lý xong batch của lần poll |
| MANUAL | Listener gọi acknowledge; container xử lý commit theo semantics của chế độ |
| MANUAL_IMMEDIATE | Yêu cầu commit ngay khi acknowledge được gọi trên consumer thread |
| TIME / COUNT / COUNT_TIME | Commit dựa trên điều kiện thời gian hoặc số record theo hỗ trợ của container |

`AckMode.RECORD` không phù hợp với batch listener vì listener được gọi cho cả batch, không phải từng record riêng lẻ. Hãy chọn acknowledgment mode theo kiểu listener và phiên bản Spring Kafka.

### 9.1. Manual acknowledgment

Nếu cần listener quyết định thời điểm xác nhận batch, có thể nhận `Acknowledgment`:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "manualBatchListenerContainerFactory"
)
public void listen(
        List<ConsumerRecord<String, OrderCreated>> records,
        Acknowledgment acknowledgment) {

    billingService.processBatch(
        records.stream()
            .map(ConsumerRecord::value)
            .toList()
    );

    acknowledgment.acknowledge();
}
~~~

Factory phải cấu hình `AckMode.MANUAL` hoặc `MANUAL_IMMEDIATE` tương ứng.

Chỉ acknowledge sau khi toàn bộ công việc nghiệp vụ cần thiết đã hoàn tất. Nếu xử lý database theo nhiều bước, cần xem xét transaction database hoặc idempotency để tránh trường hợp một phần batch đã ghi thành công nhưng offset chưa commit.

### 9.2. enable.auto.commit

Để Spring Kafka listener container quản lý commit, nên cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
~~~

Không dựa vào auto commit theo timer nếu muốn kiểm soát offset theo kết quả xử lý batch. Commit offset và commit database là hai thao tác khác nhau; chúng không tự tạo thành một transaction nguyên tử.

## 10. Xử lý lỗi tại một record trong batch

Một khó khăn của batch listener là xác định record nào gây lỗi.

Nếu listener ném một exception thông thường mà không chỉ ra record lỗi, error handler có thể phải xử lý toàn bộ batch theo fallback strategy. Khi có thể xác định phần tử lỗi, hãy báo rõ index hoặc record để Spring Kafka xử lý chính xác hơn.

Spring Kafka cung cấp `BatchListenerFailedException` để chỉ ra record thất bại trong batch.

Ví dụ:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "batchListenerContainerFactory"
)
public void listen(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderCreated> record = records.get(index);

        try {
            billingService.process(record.value());
        } catch (Exception exception) {
            throw new BatchListenerFailedException(
                "Cannot process order event",
                exception,
                index
            );
        }
    }
}
~~~

Với `DefaultErrorHandler`, exception này giúp handler biết phần tử nào trong batch thất bại. Tùy cấu hình retry, recoverer và phiên bản Spring Kafka, các record trước phần tử lỗi có thể được xem là đã xử lý, còn record lỗi và phần còn lại được retry hoặc phục hồi theo chính sách.

Nếu không xác định được record lỗi, error handler có thể retry toàn bộ batch. Điều này làm các record đã xử lý thành công trước đó có khả năng được giao lại. Vì vậy, xử lý nghiệp vụ nên idempotent.

### 10.1. Cấu hình DefaultErrorHandler

Ví dụ handler với backoff:

~~~java
@Bean
public DefaultErrorHandler batchErrorHandler() {
    return new DefaultErrorHandler(
        new FixedBackOff(1_000L, 2L)
    );
}
~~~

Gắn handler vào factory:

~~~java
factory.setCommonErrorHandler(batchErrorHandler);
~~~

Trong ứng dụng thực tế, hãy khai báo handler như một bean và inject vào factory. Nếu dùng DLT, có thể cấu hình `DeadLetterPublishingRecoverer` để publish record không phục hồi được tới dead-letter topic.

Cần kiểm tra serializer, DLT partition, retention và quy trình xử lý lại. Không giả định mọi lỗi trong batch đều được gửi riêng lẻ tới DLT nếu error handler chưa được cấu hình để xác định record thất bại.

### 10.2. Lỗi deserialize xảy ra trước listener

Nếu key hoặc value không deserialize được, listener có thể chưa được gọi với record đó. Hãy xem xét `ErrorHandlingDeserializer` để chuyển lỗi deserialize thành thông tin lỗi có thể được error handler xử lý.

Không xử lý lỗi deserialize như lỗi business thông thường trong vòng lặp nếu record chưa được tạo thành công. Cần cấu hình deserializer, error handler và DLT nhất quán.

## 11. Concurrency và partition assignment

Factory có thể tạo nhiều consumer để xử lý batch song song:

~~~java
factory.setConcurrency(3);
~~~

Mỗi child container dùng một consumer riêng. Trong cùng consumer group, một partition tại một thời điểm chỉ được gán cho tối đa một consumer.

Ví dụ topic có 6 partition:

| Concurrency | Consumer | Khả năng phân phối |
|---:|---:|---|
| 1 | 1 | Một consumer nhận các partition được gán |
| 3 | 3 | Tối đa ba consumer cùng xử lý |
| 6 | 6 | Có thể một consumer trên mỗi partition |
| 8 | 8 | Ít nhất hai consumer không có partition nếu chỉ có 6 partition |

Nếu ứng dụng chạy hai instance, mỗi instance concurrency 3, tổng số consumer trong group là 6.

Batch listener không làm một partition được nhiều consumer trong cùng group xử lý đồng thời. Batch gom nhiều record mà một consumer poll được; concurrency tăng số consumer và số partition có thể xử lý song song.

### 11.1. Concurrency không đồng nghĩa batch size

Hai cấu hình điều khiển hai yếu tố khác nhau:

- `concurrency`: số consumer container con.
- `max.poll.records`: giới hạn số record một consumer nhận trong một lần poll.

Ví dụ concurrency 3 và max.poll.records 100 có thể tạo tối đa ba consumer, mỗi consumer nhận tối đa 100 record trong một lần poll. Tổng số record một lần poll trên toàn group có thể lên tới 300 trong trường hợp mọi consumer đều nhận đủ giới hạn, nhưng không có cam kết batch luôn đạt con số này.

## 12. Thời gian xử lý batch và max.poll.interval.ms

Batch listener xử lý cả danh sách trên luồng consumer container. Nếu xử lý quá lâu, khoảng thời gian giữa hai lần poll có thể vượt `max.poll.interval.ms`, khiến consumer rời group hoặc bị rebalance.

Ví dụ batch có 100 record, mỗi record mất trung bình 500 ms nếu xử lý tuần tự. Tổng thời gian xử lý có thể lên tới khoảng 50 giây, chưa tính thời gian database, network và retry.

Nếu listener xử lý lâu:

- Giảm `max.poll.records`.
- Tối ưu thao tác database theo batch.
- Giảm round trip tới downstream.
- Chọn concurrency phù hợp với số partition và tài nguyên.
- Tăng `max.poll.interval.ms` khi có số liệu chứng minh cần thiết.
- Tránh chờ vô hạn trong listener.

Tăng `max.poll.interval.ms` không làm xử lý nhanh hơn. Nó chỉ cho consumer thêm thời gian giữa các lần poll; cần cân nhắc ảnh hưởng khi consumer thực sự bị treo.

## 13. Transaction và tính idempotent khi xử lý batch

Một batch có thể chứa nhiều event cần ghi vào database. Nếu database transaction rollback, toàn bộ thao tác database trong transaction đó có thể được hoàn tác. Tuy nhiên, offset Kafka vẫn cần được quản lý riêng.

Các rủi ro:

- Database đã ghi một phần nhưng listener thất bại trước commit offset.
- Batch được giao lại và các record đã ghi thành công bị xử lý lần nữa.
- Offset được commit nhưng công việc bất đồng bộ chưa hoàn tất.
- Kafka transaction và database transaction không tự động tạo một transaction phân tán duy nhất.

Để xử lý an toàn:

- Thiết kế operation idempotent theo event ID hoặc business key.
- Dùng unique constraint hoặc inbox table khi phù hợp.
- Thực hiện các cập nhật database của batch trong transaction phù hợp.
- Acknowledge/commit sau khi nghiệp vụ cần thiết hoàn tất.
- Với Kafka-to-Kafka flow, cân nhắc Kafka transaction và việc gửi offset vào transaction.
- Theo dõi record lỗi và có quy trình replay.

Không nên xem batch listener là cơ chế exactly-once. Batch chỉ thay đổi cách nhận và gọi listener; semantics giao nhận và transaction vẫn phụ thuộc cấu hình consumer, commit, producer và nghiệp vụ.

## 14. Kiểm thử List<ConsumerRecord> listener

Kiểm thử tích hợp nên xác nhận listener nhận đúng nhiều record và metadata vẫn chính xác.

Các bước:

1. Khởi động Kafka bằng EmbeddedKafka hoặc Testcontainers.
2. Tạo topic với số partition xác định.
3. Cấu hình batch listener factory với `setBatchListener(true)`.
4. Gửi nhiều record có key và value.
5. Chờ listener xử lý batch bằng latch hoặc Awaitility.
6. Kiểm tra số lượng record, payload, key, topic, partition và offset.
7. Kiểm tra trường hợp batch có record từ nhiều partition.
8. Kiểm tra retry, lỗi một phần tử và acknowledgment.

Ví dụ listener test probe:

~~~java
@Component
public class BatchListenerProbe {

    private final BlockingQueue<List<ConsumerRecord<String, OrderCreated>>>
        received = new LinkedBlockingQueue<>();

    @KafkaListener(
        id = "order-batch-test-listener",
        topics = "test.orders",
        groupId = "test-batch-group",
        containerFactory = "batchListenerContainerFactory"
    )
    public void listen(
            List<ConsumerRecord<String, OrderCreated>> records) {
        received.add(List.copyOf(records));
    }

    public List<ConsumerRecord<String, OrderCreated>> awaitBatch(
            Duration timeout) throws InterruptedException {

        return received.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Trong test, gửi nhiều record rồi lấy batch từ probe:

~~~java
List<ConsumerRecord<String, OrderCreated>> batch =
    probe.awaitBatch(Duration.ofSeconds(10));

assertThat(batch).isNotNull();
assertThat(batch).isNotEmpty();
assertThat(batch)
    .allSatisfy(record ->
        assertThat(record.topic()).isEqualTo("test.orders")
    );
~~~

Không giả định một lần poll luôn trả về đúng số record đã gửi. Consumer có thể nhận batch nhỏ hơn do timing, fetch và giới hạn poll. Nếu test cần kiểm tra một tập record cụ thể, hãy chờ và tích lũy đủ record qua nhiều lần gọi listener.

Khi kiểm tra offset, hãy so sánh trong cùng partition. Offset giữa hai partition không thể so sánh như một chuỗi thứ tự toàn cục.

## 15. Các lỗi thường gặp khi dùng List<ConsumerRecord>

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Listener nhận sai kiểu tham số | Factory chưa bật batch listener | Gọi `setBatchListener(true)` |
| Batch luôn nhỏ hơn mong đợi | Poll không có đủ record hoặc giới hạn fetch/poll | Kiểm tra `max.poll.records`, fetch và timing |
| Không thấy key hoặc metadata | Listener chỉ nhận payload list | Đổi sang `List<ConsumerRecord<K,V>>` |
| ClassCastException | Generic type không khớp deserializer | Kiểm tra key/value type và ConsumerFactory |
| Batch bị retry nhiều lần | Exception không chỉ ra record lỗi | Dùng `BatchListenerFailedException` khi xác định được index |
| Record đã xử lý bị xử lý lại | Batch retry hoặc commit chưa hoàn tất | Thiết kế idempotency |
| Consumer bị rebalance | Xử lý batch vượt `max.poll.interval.ms` | Giảm batch hoặc tối ưu/tăng timeout có kiểm soát |
| Batch chứa nhiều partition | Consumer được gán nhiều partition | Dùng topic/partition/offset của từng record |
| Mất thứ tự nghiệp vụ | Event cùng entity ở partition khác nhau hoặc xử lý song song | Dùng key ổn định và kiểm soát concurrency |
| NullPointerException | Key/value có thể null, đặc biệt tombstone | Kiểm tra null trước khi xử lý |
| DLT không nhận đúng record | Recoverer hoặc serializer chưa tương thích | Kiểm tra error handler, DLT và producer |

## 16. Quy trình thực hành hoàn chỉnh

Giả sử Billing nhận event OrderCreated và muốn ghi hóa đơn theo batch.

### Bước 1: Khai báo event

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    long total
) {
}
~~~

### Bước 2: Cấu hình consumer

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      max-poll-records: 100
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
        max.poll.interval.ms: 300000
~~~

### Bước 3: Tạo batch listener factory

~~~java
@Bean(name = "batchListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(3);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

### Bước 4: Nhận List<ConsumerRecord>

~~~java
@Service
public class BillingBatchListener {

    private final BillingService billingService;

    public BillingBatchListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
        topics = "commerce.order.created",
        groupId = "billing-service",
        containerFactory = "batchListenerContainerFactory"
    )
    public void listen(
            List<ConsumerRecord<String, OrderCreated>> records) {

        List<OrderCreated> events = records.stream()
            .map(ConsumerRecord::value)
            .filter(Objects::nonNull)
            .toList();

        billingService.processBatch(events);
    }
}
~~~

### Bước 5: Theo dõi kết quả

Theo dõi các chỉ số:

- Batch size thực tế.
- Thời gian xử lý mỗi batch.
- Số record thành công/thất bại.
- Consumer lag theo partition.
- Số lần retry.
- Số record chuyển tới DLT.
- Thời gian giữa hai lần poll.

~~~mermaid
flowchart TD
    A["Kafka Consumer poll"] --> B["Nhận ConsumerRecords"]
    B --> C["Spring tạo List<ConsumerRecord>"]
    C --> D["Batch listener"]
    D --> E["Đọc key/value/metadata"]
    E --> F["Xử lý batch nghiệp vụ"]
    F --> G{"Xử lý thành công?"}
    G -->|Có| H["Container commit theo AckMode"]
    G -->|Không| I["Error handler / retry"]
    I --> J{"Hết retry?"}
    J -->|Không| D
    J -->|Có| K["Recover hoặc DLT"]
~~~

## 17. Checklist trước khi đưa batch listener vào vận hành

- [ ] Factory đã gọi `setBatchListener(true)`?
- [ ] Listener dùng đúng `containerFactory`?
- [ ] Generic key/value khớp ConsumerFactory và deserializer?
- [ ] Chọn `List<ConsumerRecord<K,V>>` khi cần metadata?
- [ ] Đã kiểm tra key/value null và tombstone?
- [ ] Đã hiểu một batch có thể chứa nhiều partition?
- [ ] Không giả định offset giữa các partition có thứ tự toàn cục?
- [ ] `max.poll.records` phù hợp với thời gian xử lý?
- [ ] `max.poll.interval.ms` đủ cho worst-case processing time?
- [ ] AckMode tương thích với batch listener?
- [ ] `enable.auto.commit` được cấu hình có chủ đích?
- [ ] Lỗi một record được xác định bằng index/record khi có thể?
- [ ] Error handler, retry và DLT có cấu hình tương thích?
- [ ] Xử lý nghiệp vụ idempotent khi batch được giao lại?
- [ ] Không trả về khỏi listener trước khi công việc bất đồng bộ hoàn tất?
- [ ] Đã kiểm thử batch size, metadata, offset, retry và rebalance?
- [ ] Đã theo dõi lag và thời gian xử lý theo partition?

## Kết luận

Nhận `List<ConsumerRecord<K, V>>` cho phép Spring Kafka gọi listener một lần với nhiều record được trả về trong một lần poll, đồng thời giữ metadata riêng của từng record như key, topic, partition, offset, timestamp và headers. Để sử dụng, cần bật batch mode trên `ConcurrentKafkaListenerContainerFactory` và chỉ định đúng factory trong `@KafkaListener`.

Batch listener có thể tăng throughput khi xử lý theo lô phù hợp, nhưng batch size không cố định và một batch có thể chứa record từ nhiều partition. Hãy chọn `max.poll.records`, concurrency và acknowledgment mode theo thời gian xử lý thực tế; xác định rõ record lỗi bằng `BatchListenerFailedException` khi có thể; đồng thời thiết kế idempotency và kiểm thử commit/retry để xử lý batch đáng tin cậy.

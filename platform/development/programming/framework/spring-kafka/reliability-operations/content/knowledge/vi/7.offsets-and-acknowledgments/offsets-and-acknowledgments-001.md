# AckMode BATCH

## 1. AckMode trong Spring Kafka là gì?

Kafka consumer đọc record theo offset và cần commit offset để cho broker biết vị trí mà consumer group đã xử lý đến. Offset commit ảnh hưởng trực tiếp đến vị trí consumer tiếp tục đọc sau khi restart, rebalance hoặc gặp lỗi.

Spring Kafka cung cấp `AckMode` để xác định thời điểm listener container xác nhận các record đã xử lý và gửi offset commit. **AckMode.BATCH** yêu cầu container commit offset sau khi tất cả record được trả về trong một lần `poll()` đã được xử lý xong.

Đây là chế độ mặc định phổ biến của listener container Spring Kafka. Nó phù hợp với nhiều ứng dụng cần cân bằng throughput và số lần commit: container có thể xử lý nhiều record trong một poll rồi commit offset theo nhóm thay vì commit sau từng record.

Cần phân biệt hai khái niệm:

- **Batch returned by poll:** tập record KafkaConsumer trả về trong một lần gọi `poll()`. Một tập này có thể chứa record từ nhiều partition.
- **Batch listener:** kiểu listener nhận cả danh sách record trong một lần gọi phương thức, thay vì được gọi riêng cho từng record.

AckMode.BATCH không bắt buộc phải dùng batch listener. Với record listener, container vẫn có thể nhận một tập record từ poll, gọi listener lần lượt cho từng record, rồi commit sau khi tất cả record của poll đó đã được xử lý.

## 2. Cách AckMode.BATCH hoạt động

Một chu kỳ đơn giản của listener container:

1. Container gọi `poll()` để lấy record từ Kafka.
2. Kafka trả về các record thuộc những partition consumer đang được gán.
3. Container chuyển từng record cho listener, hoặc chuyển cả danh sách nếu đang dùng batch listener.
4. Container theo dõi kết quả xử lý trong tập record vừa nhận.
5. Khi tất cả record trong tập poll đã được xử lý thành công theo semantics của container, container commit offset tương ứng.

Ví dụ consumer nhận ba record từ partition 0 và hai record từ partition 1:

~~~text
Một lần poll() trả về:
  partition 0: offset 10, 11, 12
  partition 1: offset 20, 21

Container xử lý:
  p0/10  -> thành công
  p1/20  -> thành công
  p0/11  -> thành công
  p1/21  -> thành công
  p0/12  -> thành công

Sau khi cả tập poll hoàn tất:
  commit p0 -> offset 13
  commit p1 -> offset 22
~~~

Kafka lưu offset tiếp theo mà consumer group cần đọc. Vì vậy, sau khi xử lý offset 12, consumer commit giá trị 13; sau offset 21, commit giá trị 22. Offset commit được quản lý riêng theo từng partition, dù một commit request có thể mang offset của nhiều partition.

### 2.1. Thời điểm commit

Giả sử một poll trả về 100 record. Với AckMode.BATCH, container không commit ngay sau record đầu tiên. Nó chờ cho tới khi toàn bộ 100 record đã được xử lý xong theo luồng container, rồi mới gửi offset commit.

Nếu poll trả về ít record hơn, container chỉ cần xử lý số record thực tế đó. Một poll có thể trả về 1 record, vài record hoặc không có record nào; kích thước batch không cố định.

### 2.2. Batch không đồng nghĩa với một partition

Một poll có thể chứa record từ nhiều partition được gán cho cùng consumer. Khi commit, Kafka lưu offset riêng cho từng partition. Do đó, khái niệm batch ở đây là tập record của một lần poll, không phải toàn bộ record của một topic hoặc một partition.

Nếu một consumer group có nhiều consumer, mỗi consumer có poll cycle và commit boundary riêng. AckMode.BATCH không gom record từ tất cả instance trong group thành một batch chung.

## 3. AckMode.BATCH và các AckMode khác

Spring Kafka có nhiều chế độ xác nhận. Chọn chế độ dựa trên ranh giới xử lý, throughput và mức độ chấp nhận replay.

| AckMode | Thời điểm commit | Trường hợp sử dụng thường gặp |
|---|---|---|
| `RECORD` | Sau khi listener xử lý xong từng record | Muốn commit sát từng record, giảm số record có thể replay sau sự cố |
| `BATCH` | Sau khi tất cả record của một poll được xử lý | Cần cân bằng throughput và số lần commit |
| `TIME` | Sau khi xử lý xong batch và điều kiện thời gian commit được đáp ứng | Muốn giới hạn tần suất commit theo thời gian |
| `COUNT` | Sau khi xử lý xong batch và số lượng record đạt ngưỡng | Muốn commit theo số record đã xử lý |
| `COUNT_TIME` | Khi điều kiện count hoặc time được đáp ứng sau xử lý batch | Muốn kết hợp ngưỡng số lượng và thời gian |
| `MANUAL` | Listener gọi acknowledge; container commit theo ranh giới batch | Ứng dụng cần quyết định thời điểm xác nhận |
| `MANUAL_IMMEDIATE` | Listener gọi acknowledge và commit ngay nếu gọi trên consumer thread; nếu gọi từ thread khác, việc commit được xử lý theo cơ chế container | Cần điều khiển commit tường minh |

`RECORD` và `BATCH` là hai lựa chọn thường được so sánh trực tiếp. Với RECORD, một record hoàn tất có thể được commit trước khi các record tiếp theo trong cùng poll hoàn tất. Với BATCH, container đợi cả tập poll.

`TIME` và `COUNT` không có nghĩa commit ngay giữa lúc listener còn xử lý batch. Container chỉ commit khi các record cần thiết trong poll đã được xử lý; điều kiện thời gian hoặc số lượng quyết định lúc commit được kích hoạt.

### 3.1. So sánh RECORD và BATCH

Giả sử một poll trả về các offset 10, 11 và 12 của cùng partition.

Với RECORD:

~~~text
Xử lý offset 10 -> commit offset 11
Xử lý offset 11 -> commit offset 12
Xử lý offset 12 -> commit offset 13
~~~

Với BATCH:

~~~text
Xử lý offset 10
Xử lý offset 11
Xử lý offset 12
Cả poll hoàn tất -> commit offset 13
~~~

RECORD có thể tạo nhiều commit hơn nhưng giảm khoảng record đã xử lý mà chưa commit. BATCH giảm số commit trong trường hợp một poll có nhiều record, đổi lại nếu process dừng trước lần commit cuối, một phần hoặc toàn bộ record thuộc poll chưa commit có thể được giao lại tùy trạng thái và xử lý lỗi.

## 4. Cấu hình AckMode.BATCH trong Spring Boot

AckMode là cấu hình của listener container, không phải một Kafka consumer property như `fetch.min.bytes` hay `max.poll.records`.

Với Spring Boot, có thể khai báo trong `application.yml`:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      group-id: order-fulfillment
    listener:
      ack-mode: batch
      type: single
~~~

`ack-mode: batch` yêu cầu listener container dùng AckMode.BATCH. `type: single` biểu thị listener nhận từng record; container vẫn commit theo tập record của poll. Nếu muốn phương thức listener nhận một danh sách record, cần cấu hình listener type là batch và viết phương thức tương ứng.

Spring Kafka container thường tắt Kafka auto commit nếu ứng dụng không bật tường minh. Khai báo `enable-auto-commit: false` làm rõ rằng offset được quản lý bởi container. Tránh bật auto commit đồng thời với mong muốn container kiểm soát commit theo AckMode, vì Kafka client có thể commit định kỳ độc lập với kết quả xử lý của listener.

### 4.1. Cấu hình bằng Java

Khi tự tạo `ConcurrentKafkaListenerContainerFactory`, có thể đặt AckMode trên ContainerProperties:

~~~java
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

Nếu muốn listener nhận batch, factory cần bật batch listener:

~~~java
factory.setBatchListener(true);
~~~

Khi đó phương thức listener có thể nhận danh sách record:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "kafkaListenerContainerFactory"
)
public void handleBatch(List<ConsumerRecord<String, OrderCreated>> records) {
    for (ConsumerRecord<String, OrderCreated> record : records) {
        fulfillmentService.process(record.value());
    }
}
~~~

Các ví dụ giả định ứng dụng đã cấu hình `ConsumerFactory`, deserializer và các import liên quan. Nếu Spring Boot đã tạo factory mặc định, không cần tạo factory riêng chỉ để chọn AckMode; dùng cấu hình `spring.kafka.listener.ack-mode` thường đơn giản hơn.

## 5. Record listener với AckMode.BATCH

Đây là cách dùng phổ biến khi mỗi lần gọi listener xử lý một event, nhưng container vẫn commit theo poll batch:

~~~java
@Service
public class OrderListener {

    private final FulfillmentService fulfillmentService;

    public OrderListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-fulfillment"
    )
    public void consume(OrderCreated event) {
        fulfillmentService.process(event);
    }
}
~~~

Giả sử `poll()` trả về 50 record. Container gọi phương thức `consume()` cho từng record. Sau khi tất cả 50 lần gọi hoàn tất thành công, container commit offset của các partition liên quan.

Điều này không có nghĩa listener method nhận 50 record cùng lúc. Nó vẫn nhận một event mỗi lần gọi. Batch là ranh giới commit của container.

### 5.1. Khi nào record listener phù hợp?

Record listener thường phù hợp khi:

- Mỗi event có logic nghiệp vụ độc lập.
- Có thể xử lý và ghi nhận lỗi theo từng event.
- Không cần phối hợp dữ liệu giữa nhiều record trong một lần gọi.
- Muốn tận dụng AckMode.BATCH để giảm commit overhead mà không phải viết batch-processing code.

Nếu một record lỗi, error handler sẽ quyết định retry, recover hoặc chuyển record lỗi tới DLT. Phần record còn lại của poll được xử lý theo semantics của error handler và container. Không nên giả định rằng chỉ cần dùng BATCH thì mọi record trong poll luôn bị phát lại cùng nhau; hành vi cụ thể phụ thuộc cách xử lý lỗi.

## 6. Batch listener với AckMode.BATCH

Batch listener nhận nhiều record trong cùng một lần gọi phương thức. Cách này hữu ích khi có thể tối ưu xử lý theo nhóm, chẳng hạn bulk insert, bulk update hoặc gọi một API hỗ trợ nhiều phần tử.

Ví dụ:

~~~java
@Service
public class OrderBatchListener {

    private final FulfillmentService fulfillmentService;

    public OrderBatchListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-fulfillment-batch",
        containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
        List<OrderCreated> events = records.stream()
            .map(ConsumerRecord::value)
            .toList();

        fulfillmentService.processBatch(events);
    }
}
~~~

Factory tương ứng cần bật batch listener:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

Khi phương thức batch listener kết thúc bình thường, container xem tập record đã được trả về trong poll là đã xử lý và có thể commit offset tương ứng.

Nếu phương thức ném exception, container không thể coi toàn bộ batch là thành công. Error handler sẽ thực hiện retry hoặc recovery theo cấu hình. Nếu cần xử lý từng record lỗi trong batch, có thể dùng `BatchListenerFailedException` để chỉ ra vị trí record thất bại và phối hợp với `DefaultErrorHandler` phù hợp.

### 6.1. Batch size không cố định

Kích thước danh sách listener nhận được phụ thuộc số record Kafka trả về trong lần poll và các giới hạn liên quan. `max.poll.records` đặt số record tối đa consumer trả về trong một lần poll; nó không bảo đảm mỗi lần đều có đúng số record đó.

Một poll có thể trả:

- Ít record vì topic đang có ít dữ liệu.
- Nhiều record khi producer tạo tải cao.
- Record từ nhiều partition được gán cho cùng consumer.
- Không có record nếu chưa có dữ liệu phù hợp.

Vì vậy, xử lý batch phải chấp nhận danh sách rỗng hoặc nhỏ hơn ngưỡng dự kiến ở các luồng code có thể nhận các trường hợp đó.

## 7. Commit offset và bảo đảm giao nhận

AckMode.BATCH thường được sử dụng trong mô hình at-least-once khi container chỉ commit sau khi listener xử lý thành công. Nó giảm khả năng mất record do commit quá sớm, nhưng có thể khiến record đã xử lý bị giao lại nếu ứng dụng dừng trước khi commit.

Ví dụ:

1. Poll trả về offset 100, 101, 102.
2. Listener xử lý thành công cả ba record.
3. Process dừng trước khi commit offset 103.
4. Consumer khởi động lại hoặc partition được gán cho consumer khác.
5. Group đọc lại từ offset đã commit trước đó, có thể nhận lại 100, 101 và 102.

Đây là hành vi replay bình thường của at-least-once. Vì thế, consumer cần xử lý duplicate an toàn.

### 7.1. Commit offset là commit vị trí tiếp theo

Kafka commit offset tiếp theo mà consumer sẽ đọc. Nếu record cuối cùng đã xử lý ở partition có offset 42, offset commit thường là 43.

| Record đã xử lý cuối cùng | Offset commit | Vị trí đọc tiếp theo |
|---:|---:|---:|
| 9 | 10 | 10 |
| 42 | 43 | 43 |
| 1.024 | 1.025 | 1.025 |

Container theo dõi offset theo partition. Không lấy offset cuối của topic hoặc số lượng record trong batch để tính một offset chung.

### 7.2. Idempotent consumer

Vì batch commit có thể tạo ra replay, side effect nghiệp vụ nên có khả năng chống xử lý lặp.

Một cách phổ biến là gắn `eventId` ổn định vào event và lưu ID đã xử lý trong bảng inbox:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Consumer dùng transaction DB để kiểm tra và ghi nhận event ID cùng với side effect. Nếu event được giao lại, unique constraint giúp nhận ra event đã xử lý.

Ví dụ logic khái quát:

~~~java
@Transactional
public void process(OrderCreated event) {
    if (processedEventRepository.existsById(event.eventId())) {
        return;
    }

    fulfillmentRepository.createWork(event);
    processedEventRepository.save(
        new ProcessedEvent(event.eventId(), Instant.now())
    );
}
~~~

Ví dụ trên minh họa ý tưởng; trong triển khai đồng thời, cần dựa vào unique constraint và xử lý duplicate-key trong cùng transaction thay vì chỉ dựa vào thao tác kiểm tra trước khi insert. Nếu hai consumer hoặc hai lần xử lý cùng kiểm tra một lúc, cả hai có thể thấy ID chưa tồn tại.

Nếu DB commit thành công nhưng Kafka offset chưa commit, record có thể được giao lại. Transaction DB cùng inbox giúp lần xử lý lại không tạo side effect lần hai.

## 8. Xử lý exception trong BATCH mode

AckMode.BATCH chỉ xác định ranh giới commit bình thường. Khi listener ném exception, error handler quyết định record nào được retry, seek, recover hoặc gửi sang dead-letter topic.

Các hành vi cụ thể phụ thuộc phiên bản Spring Kafka, loại listener, error handler, retry policy, recoverer và transaction configuration.

### 8.1. Record listener gặp lỗi

Giả sử một poll trả về record A, B và C. Listener xử lý A thành công nhưng B ném exception. Container chuyển lỗi cho error handler.

Một error handler có thể:

- Retry B theo backoff.
- Seek partition về vị trí cần đọc lại.
- Recover B sau khi hết retry, ví dụ gửi tới DLT.
- Tiếp tục xử lý các record còn lại theo semantics đã cấu hình.
- Commit offset của record đã hoàn tất hoặc record đã recover theo chính sách handler.

Không nên tự suy luận rằng A luôn bị phát lại hay luôn được commit. Cần xem cấu hình error handler đang dùng và cách container quản lý pending offset trong phiên bản Spring Kafka của ứng dụng.

### 8.2. Batch listener gặp lỗi

Với batch listener, nếu phương thức xử lý cả danh sách rồi ném exception mà không chỉ ra record lỗi, error handler có thể phải retry toàn bộ batch vì không biết record nào gây lỗi.

Khi dùng `DefaultErrorHandler`, batch listener có thể ném `BatchListenerFailedException` cùng vị trí record lỗi. Điều đó cho phép handler biết phần nào đã xử lý và phần nào cần retry/recover:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment-batch",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int i = 0; i < records.size(); i++) {
        try {
            fulfillmentService.process(records.get(i).value());
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                "Could not process order event",
                ex,
                i
            );
        }
    }
}
~~~

Khi cấu hình recoverer như `DeadLetterPublishingRecoverer`, cần xác định rõ record nào được gửi tới DLT và điều kiện nào được xem là recovery thành công. Không đánh dấu một batch thành công chỉ vì lỗi đã được log.

### 8.3. Listener nuốt exception

Nếu listener bắt exception nhưng không ném lại và không báo trạng thái thất bại cho container, phương thức kết thúc bình thường. Container có thể xem record hoặc batch đã xử lý thành công và commit offset.

Ví dụ dễ gây mất xử lý:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    try {
        fulfillmentService.process(event);
    }
    catch (Exception ex) {
        log.error("Processing failed", ex);
        // Không ném lại exception và không có cơ chế retry/recovery.
    }
}
~~~

Nếu muốn retry, cần để exception được truyền tới container/error handler hoặc dùng cơ chế recovery rõ ràng. Log lỗi không thay thế cho trạng thái xử lý lỗi.

## 9. Kết hợp BATCH với Kafka transaction

Khi listener container được cấu hình với Kafka transaction manager, việc xử lý record và gửi offset có thể nằm trong một Kafka transaction. Container bắt đầu transaction, listener xử lý dữ liệu, sau đó gửi offset vào transaction và commit transaction. Nếu transaction abort, offset trong transaction không được commit cùng các output record.

Với consume-transform-produce, điều này giúp phối hợp output Kafka và offset input trong cùng transaction. Consumer downstream có thể dùng `isolation.level=read_committed` để chỉ đọc các record đã được commit.

Ví dụ khái quát:

~~~java
@KafkaListener(topics = "orders.in", groupId = "order-transformer")
public void transform(OrderCreated event) {
    ValidatedOrder output = validator.validate(event);
    kafkaTemplate.send("orders.validated", event.orderId(), output);
}
~~~

Khi listener container và KafkaTemplate được cấu hình tham gia cùng transaction, output và offset input có thể được commit như một đơn vị. Cách cấu hình transaction ID prefix, transaction manager và listener container phụ thuộc phiên bản Spring Kafka và cách ứng dụng quản lý transaction.

Kafka transaction không tự bao gồm transaction của cơ sở dữ liệu quan hệ hoặc HTTP service. Nếu listener ghi DB rồi Kafka transaction abort, DB không tự rollback. Cần outbox/inbox, DB transaction và idempotency ở ranh giới hệ thống để quản lý side effect ngoài Kafka.

## 10. Tương tác với poll, max.poll.records và concurrency

AckMode.BATCH gắn với tập record của một lần poll. Các cấu hình consumer khác ảnh hưởng kích thước và nhịp xử lý của tập đó.

### 10.1. max.poll.records

`max.poll.records` giới hạn số record consumer trả về trong một lần poll. Nếu tăng giá trị, mỗi batch có thể lớn hơn, từ đó container có thể xử lý nhiều record trước khi commit.

Điều này có thể giảm commit overhead nhưng cũng làm tăng thời gian xử lý poll batch. Nếu xử lý quá lâu, consumer có thể vi phạm `max.poll.interval.ms` và bị rời group.

### 10.2. max.poll.interval.ms

`max.poll.interval.ms` giới hạn khoảng cách giữa các lần poll. Với batch lớn hoặc xử lý từng record chậm, cần đảm bảo container có thể hoàn tất công việc và gọi poll tiếp theo trong giới hạn.

Không tăng max.poll.interval.ms một cách máy móc. Trước tiên đo thời gian xử lý p95/p99, kích thước poll batch, downstream latency và thời gian GC. Có thể cần giảm max.poll.records, tối ưu xử lý hoặc chia workload.

### 10.3. Concurrency

Spring Kafka listener container có thể chạy nhiều consumer qua concurrency. Mỗi consumer có poll batch và offset commit riêng.

Tăng concurrency có thể tăng throughput khi có đủ partition và tài nguyên. Tuy nhiên, concurrency lớn hơn số partition được gán hữu ích có thể tạo consumer không có partition, đồng thời tăng kết nối và tải broker. Không có một batch commit chung giữa các consumer.

## 11. Quan sát và chẩn đoán

Để đánh giá AckMode.BATCH, cần theo dõi cả hành vi commit, consumer lag, processing latency và retry.

| Chỉ số | Điều cần quan sát |
|---|---|
| Commit rate | Số lần commit offset theo thời gian |
| Commit latency | Thời gian gửi và hoàn tất commit |
| Records per poll | Số record trung bình và tối đa trong một poll |
| Processing duration | Thời gian xử lý từng record hoặc cả batch |
| Consumer lag | Khoảng cách giữa log end offset và committed offset |
| Rebalance count | Tần suất consumer group thay đổi assignment |
| Retry/recovery rate | Số record hoặc batch cần retry/recover |
| DLT rate | Số event được chuyển tới dead-letter topic |
| Duplicate detection | Số event bị nhận diện là đã xử lý |
| End-to-end event age | Tuổi event khi hoàn tất nghiệp vụ |

Tên metric chính xác phụ thuộc Kafka client, Spring Kafka, Micrometer và exporter. Một số thông tin commit/processing cần được instrument ở tầng ứng dụng hoặc listener container vì broker metrics không thể tự mô tả toàn bộ kết quả nghiệp vụ.

### 11.1. Dấu hiệu vận hành

- Commit rate giảm nhưng throughput giữ ổn định: BATCH có thể đang giảm commit overhead như mong muốn.
- Consumer lag tăng sau khi tăng max.poll.records: batch lớn có thể làm thời gian xử lý dài hơn hoặc downstream bị nghẽn.
- Duplicate detection tăng sau restart: có thể có record đã xử lý nhưng chưa commit trước khi process dừng.
- Rebalance tăng cùng processing duration cao: kiểm tra max.poll.interval.ms, listener time và GC.
- DLT rate tăng: kiểm tra exception, schema, dữ liệu đầu vào và retry policy.
- Commit latency tăng: kiểm tra broker, coordinator, network và tình trạng group.

## 12. Khi nào nên dùng AckMode.BATCH?

BATCH phù hợp khi:

- Listener xử lý record tương đối nhanh và có thể hoàn tất tập poll trong giới hạn poll interval.
- Workload có throughput vừa hoặc cao và muốn giảm số lần commit.
- Ứng dụng chấp nhận replay record đã xử lý nếu sự cố xảy ra trước commit.
- Side effect có idempotency hoặc cơ chế deduplication phù hợp.
- Batch listener có thể tận dụng bulk operation để tăng hiệu quả.

Có thể cân nhắc RECORD khi từng record có chi phí xử lý lớn, cần ranh giới commit sát hơn hoặc muốn giảm số record đã xử lý nhưng chưa commit. Tuy nhiên, commit từng record làm tăng số lần commit và không loại bỏ mọi duplicate trong các tình huống crash/rebalance.

Nếu cần commit theo logic nghiệp vụ phức tạp, MANUAL hoặc MANUAL_IMMEDIATE có thể phù hợp, nhưng cần hiểu rõ thứ tự acknowledge, consumer thread và container. Không chuyển sang manual chỉ để tránh duplicate; hãy thiết kế side effect idempotent trước.

## 13. Sai lầm thường gặp

**Cho rằng BATCH nghĩa là listener phải nhận List.** AckMode.BATCH là chính sách commit theo poll. Record listener vẫn dùng được.

**Cho rằng batch luôn có max.poll.records phần tử.** Đây là giới hạn trên, không phải kích thước cố định.

**Cho rằng commit sau batch loại bỏ duplicate.** Process có thể dừng sau side effect nhưng trước commit. Record chưa commit vẫn có thể được giao lại.

**Bật enable.auto.commit cùng AckMode.BATCH.** Auto commit có thể commit độc lập với listener. Hãy để container quản lý offset với auto commit tắt.

**Nuốt exception trong listener.** Container có thể xem lời gọi thành công và commit offset dù nghiệp vụ chưa hoàn tất.

**Cho rằng một batch thuộc một partition.** Poll có thể chứa record từ nhiều partition và commit offset riêng cho từng partition.

**Tăng max.poll.records mà không đo processing time.** Batch lớn hơn có thể khiến consumer vượt max.poll.interval.ms và rebalance.

**Cho rằng Kafka transaction rollback được DB.** Kafka transaction chỉ bao phủ tài nguyên Kafka. Side effect DB cần cơ chế transaction hoặc outbox/inbox riêng.

**Không kiểm tra error handler.** Hành vi retry, seek, recovery và commit khi listener lỗi phụ thuộc cấu hình error handler và phiên bản Spring Kafka.

## 14. Ví dụ tổng hợp: xử lý đơn hàng theo poll batch

Giả sử consumer group `order-fulfillment` nhận event `OrderCreated`. Mỗi lần poll có thể trả tối đa 200 record. Listener xử lý từng record bằng một service ghi trạng thái fulfillment vào DB.

Cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-fulfillment
      enable-auto-commit: false
      max-poll-records: 200
    listener:
      ack-mode: batch
      type: single
~~~

Trong một poll, container nhận 120 record trải trên ba partition. Listener được gọi 120 lần. Khi cả 120 lần gọi hoàn tất thành công, container commit offset tiếp theo cho từng partition có record trong poll.

Nếu process bị dừng sau khi ghi DB cho 90 record nhưng trước khi commit offset, một phần hoặc toàn bộ record chưa được commit có thể được giao lại sau khi consumer khởi động. Vì vậy, DB nên lưu event ID đã xử lý trong cùng transaction với cập nhật fulfillment. Khi record được giao lại, consumer phát hiện event đã hoàn tất và không tạo side effect lần hai.

Nếu một record gây lỗi, exception cần đi qua error handler. Đội vận hành cần xác định retry, backoff, DLT và quy tắc commit/recovery để bảo đảm record lỗi không bị bỏ qua ngoài ý muốn.

Khi đo hiệu quả, so sánh commit rate và commit latency trước/sau khi bật BATCH, đồng thời theo dõi processing duration, lag, duplicate detection và event freshness. Giảm số lần commit chỉ có ích nếu consumer vẫn hoàn tất batch đúng thời hạn và chất lượng xử lý không suy giảm.

## 15. Quy trình triển khai

1. Xác định Spring Kafka version và listener container thực tế đang sử dụng.
2. Xác nhận `enable.auto.commit=false` để container quản lý offset.
3. Chọn `AckMode.BATCH` trong `spring.kafka.listener.ack-mode` hoặc ContainerProperties.
4. Xác định listener là record listener hay batch listener; không nhầm loại listener với AckMode.
5. Chọn `max.poll.records` dựa trên thời gian xử lý và năng lực downstream.
6. Cấu hình error handler, retry, backoff và DLT cho lỗi xử lý.
7. Làm cho side effect idempotent để chịu được replay trước commit.
8. Nếu dùng Kafka transaction, kiểm tra transaction manager, producer factory và `read_committed` ở consumer downstream.
9. Đo commit rate, processing duration, lag, rebalance, duplicate và event freshness trong tải đại diện.
10. Ghi lại chính sách commit và recovery trong runbook để đội trực hiểu record được xử lý thế nào khi có sự cố.

## 16. Ghi nhớ

AckMode.BATCH yêu cầu Spring Kafka listener container commit offset sau khi toàn bộ record được trả về trong một lần poll đã được xử lý. Nó có thể giảm số lần commit và phù hợp với record listener lẫn batch listener.

Đổi lại, record đã tạo side effect nhưng chưa được commit có thể được giao lại sau crash hoặc rebalance. Vì vậy, hãy kết hợp BATCH với error handler phù hợp, xử lý exception đúng cách, idempotent consumer và đo thời gian xử lý so với max.poll.interval.ms. Khi hiểu rõ ranh giới poll và commit, đội vận hành có thể cân bằng throughput, độ trễ và khả năng phục hồi của consumer.



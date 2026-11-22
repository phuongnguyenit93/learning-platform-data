# sendOffsetsToTransaction

Trong Kafka và Spring Kafka, **sendOffsetsToTransaction** là thao tác đưa **consumer offsets** vào **Kafka producer transaction đang mở**, để offsets của dữ liệu đầu vào được commit **nguyên tử cùng các records đầu ra** khi transaction commit thành công. Đây là mắt xích quan trọng nhất của mô hình **consume → process → produce** theo **exactly-once semantics (EOS) trong phạm vi Kafka**.

Khi consumer đọc một record từ topic A, xử lý rồi publish sang topic B, ứng dụng không chỉ cần bảo đảm output được ghi thành công mà còn cần bảo đảm **checkpoint đọc đầu vào không tách rời với output**. Nếu output đã xuất hiện nhưng input offset chưa được lưu, một lần restart có thể khiến record cũ được xử lý lại và tạo output trùng. Nếu input offset được commit trước nhưng output thất bại, dữ liệu đầu vào có thể bị bỏ qua mà không có kết quả. Đưa offsets vào cùng Kafka transaction với output giải quyết hai cửa sổ lỗi này trong hệ sinh thái Kafka.

**Điểm cốt lõi:** gọi sendOffsetsToTransaction **chưa phải commit**. Nó chỉ đăng ký offsets vào transaction hiện tại. Các output records và offsets chỉ có hiệu lực được commit cùng nhau khi **commitTransaction()** thành công; nếu transaction bị abort, cả output transactional records lẫn offset update tương ứng không được commit.

## 1. Bài toán: xử lý Kafka-to-Kafka không giao dịch

Giả sử ứng dụng nhận đơn hàng:

~~~text
orders.created, partition 1, offset 100
value = OrderCreated(orderId=42)
~~~

Listener biến đổi thành sự kiện:

~~~text
inventory.commands, key=42
value = ReserveInventory(orderId=42)
~~~

Nếu không dùng transaction, một triển khai có thể thực hiện:

1. Consumer đọc offset 100.
2. Producer publish ReserveInventory vào inventory.commands.
3. Consumer commit offset 101 của orders.created-1.

Nhưng process có thể chết giữa bước 2 và bước 3. Output đã có nhưng committed offset vẫn là 100. Khi consumer khởi động lại, nó có thể đọc lại offset 100 và phát một output mới. Nếu đảo thứ tự và commit offset trước khi publish, một sự cố ở bước publish có thể dẫn đến **mất output**.

~~~mermaid
flowchart TD
    A["Consumer đọc offset 100"] --> B["Publish output"]
    B --> C{"Publish xong?"}
    C -->|Có| D["Commit offset 101 riêng lẻ"]
    C -->|Chết trước offset commit| E["Restart: đọc lại offset 100"]
    E --> F["Output có thể bị publish trùng"]
    D --> G["Hoàn tất"]
~~~

Kafka transaction cho phép gộp bước publish output và commit input offset vào một đơn vị logic duy nhất, thay vì hai thao tác không có ràng buộc.

## 2. sendOffsetsToTransaction làm gì?

API transactional producer thường được dùng theo chuỗi:

~~~text
initTransactions()
    |
    v
beginTransaction()
    |
    +-- send(output A)
    +-- send(output B)
    +-- sendOffsetsToTransaction({input partition: next offset}, group metadata)
    |
    v
commitTransaction()
~~~

Khi commit thành công:

- Các transactional output records có trạng thái committed, nên consumer dùng **read_committed** có thể đọc chúng.
- Input consumer group offsets được cập nhật như một phần của transaction.
- Khi consumer group tiếp tục, nó bắt đầu từ offsets đã commit.

Nếu transaction abort:

- Output records thuộc transaction này không được trả về cho **read_committed** consumers.
- Các offsets đã thêm bằng sendOffsetsToTransaction **không được commit**.
- Input record vẫn có thể được xử lý lại theo quy tắc offset/rebalance.

~~~mermaid
flowchart TD
    A["Poll input records"] --> B["beginTransaction"]
    B --> C["Produce output records"]
    C --> D["sendOffsetsToTransaction"]
    D --> E{"Transaction outcome"}
    E -->|Commit| F["Output visible với read_committed"]
    E -->|Commit| G["Consumer group offsets tiến"]
    E -->|Abort| H["Output bị đánh dấu aborted"]
    E -->|Abort| I["Group offsets không tiến do transaction"]
~~~

Dữ liệu output có thể đã được ghi vào Kafka log trước thời điểm commit. **Trạng thái committed**, không phải việc Kafka đã nhận bytes, mới là căn cứ để read_committed consumer xem record đó là output hợp lệ.

## 3. API của KafkaProducer

Kafka client cung cấp overload hiện đại nhận một map offsets và **ConsumerGroupMetadata**:

~~~java
void sendOffsetsToTransaction(
        Map<TopicPartition, OffsetAndMetadata> offsets,
        ConsumerGroupMetadata groupMetadata
) throws ProducerFencedException, KafkaException;
~~~

Chữ ký ở trên minh họa các kiểu dữ liệu và một số exception thường liên quan; danh sách đầy đủ exception thay đổi theo Kafka client version.

Ý nghĩa:

| Tham số | Ý nghĩa |
|---|---|
| **Map<TopicPartition, OffsetAndMetadata>** | Offset kế tiếp cần lưu cho từng input topic-partition đã xử lý thành công |
| **TopicPartition** | Cặp topic và partition của record **đầu vào** |
| **OffsetAndMetadata** | Offset cần commit, thường là last processed offset + 1, kèm metadata tùy chọn |
| **ConsumerGroupMetadata** | Thông tin về consumer group đang sở hữu partitions, phục vụ group coordination và fencing |

Ví dụ map:

~~~java
Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
        new TopicPartition("orders.created", 1),
        new OffsetAndMetadata(101L)
);
~~~

Map này nói rằng consumer group đã xử lý tới hết offset 100 của orders.created-1 và lần đọc tiếp theo nên bắt đầu ở offset 101.

Đây **không phải** offsets của output topic. Producer đã tự quản lý offset khi ghi output. Map chỉ đại diện cho tiến độ đọc **input partitions**.

## 4. Quy tắc offset + 1

Đây là lỗi logic phổ biến nhất khi tự gọi sendOffsetsToTransaction.

Với record có offset 100, sau khi xử lý thành công, **offset cần commit là 101**. Committed offset là vị trí kế tiếp consumer group sẽ đọc, không phải ID của record vừa xử lý.

Ví dụ:

| Partition | Records xử lý thành công | Offset cần đưa vào transaction |
|---|---|---:|
| orders.created-0 | 10, 11, 12 | 13 |
| orders.created-1 | 40, 41 | 42 |
| orders.created-2 | 100 | 101 |

Code:

~~~java
TopicPartition tp =
        new TopicPartition(record.topic(), record.partition());

OffsetAndMetadata next =
        new OffsetAndMetadata(record.offset() + 1L);
~~~

Nếu commit bằng chính offset cuối vừa xử lý thay vì offset + 1, record cuối có thể được đọc lại. Nếu commit vượt qua các records chưa được xử lý thành công, ứng dụng có thể bỏ sót dữ liệu.

### Offset tiến riêng cho từng partition

Một poll có thể trả records từ nhiều partitions. Phải tính checkpoint **riêng cho từng partition**.

~~~java
Map<TopicPartition, OffsetAndMetadata> nextOffsets =
        new HashMap<>();

for (TopicPartition tp : records.partitions()) {

    List<ConsumerRecord<String, String>> partitionRecords =
            records.records(tp);

    // Giả định toàn bộ records trong partition này đã được xử lý.
    ConsumerRecord<String, String> last =
            partitionRecords.get(partitionRecords.size() - 1);

    nextOffsets.put(
            tp,
            new OffsetAndMetadata(last.offset() + 1L)
    );
}
~~~

Không lấy offset lớn nhất của toàn bộ poll rồi gán cho tất cả partitions. Offsets chỉ có ý nghĩa bên trong cùng một topic-partition.

Nếu ứng dụng chỉ xử lý thành công **một phần** số records trong poll, tuyệt đối không commit qua record thất bại. Commit phải dựa trên **tiến độ liên tục đã hoàn tất** của mỗi partition.

## 5. Vì sao cần ConsumerGroupMetadata?

Kafka cần biết offset update thuộc consumer group nào và liệu producer đang commit thay mặt một consumer group member hợp lệ hay không.

Metadata của consumer group có thể chứa group ID, generation, member ID và các thông tin group protocol liên quan. Nó giúp Kafka nhận diện những thao tác commit offset đến từ consumer member cũ sau rebalance, từ đó tăng khả năng ngăn zombie processing.

Trong code Kafka client:

~~~java
ConsumerGroupMetadata groupMetadata =
        consumer.groupMetadata();

producer.sendOffsetsToTransaction(
        nextOffsets,
        groupMetadata
);
~~~

Lấy metadata từ **KafkaConsumer đang tham gia group và đã poll input**. Không tự dựng group metadata chỉ từ một chuỗi group ID khi bạn có thể dùng API này.

Một số Kafka client phiên bản cũ có overload chỉ nhận **groupId** dạng String. Overload hiện đại dùng ConsumerGroupMetadata cung cấp thông tin group đầy đủ hơn để hỗ trợ fencing. Khi migrate code cũ, đối chiếu Kafka client API và group management strategy.

### Khi rebalance xảy ra

Giả sử consumer A được giao partition 1, đọc offset 100 và bắt đầu xử lý. Sau đó group rebalance và partition 1 được giao sang consumer B. Nếu A vẫn cố commit offset bằng metadata đã lỗi thời, Kafka có thể từ chối thao tác liên quan group generation/fencing.

Điều này quan trọng: nếu A đã phát output nhưng không thể commit transaction chứa offset, output transactional của A không nên được read_committed consumers xem là kết quả committed của một lần xử lý không còn hợp lệ.

Trong một ứng dụng tự viết consumer loop, phải xử lý rebalance listener, revoke/assign partitions và rollback transaction cẩn thận. Spring Kafka listener container cung cấp cơ chế orchestration để giảm việc ứng dụng phải tự quản lý.

## 6. Điều kiện tiên quyết

Trước khi gọi sendOffsetsToTransaction, cần có cả một **transactional producer** và một **consumer group** được cấu hình phù hợp.

### Producer

- Có **transactional.id**.
- Đã gọi **initTransactions()** trước transaction đầu tiên.
- Đã gọi **beginTransaction()** cho transaction hiện tại.
- Producer đang ở trạng thái hợp lệ, chưa bị fenced.
- Output records được gửi bằng **cùng producer transaction**.

### Consumer

- Đã poll records và có metadata của consumer group hợp lệ.
- **enable.auto.commit=false**.
- Group ID rõ ràng, assignment hợp lệ.
- Không commit input offsets theo một đường riêng có thể phá atomicity.
- Không cho nhiều threads gọi KafkaConsumer đồng thời; KafkaConsumer không thread-safe cho thao tác poll/seek/commit thông thường.

### Downstream consumer

Nếu cần chỉ quan sát các transactional outputs đã commit, cấu hình:

~~~properties
isolation.level=read_committed
~~~

Nếu downstream dùng read_uncommitted, nó có thể nhận cả records của aborted transactions; khi đó không thể dựa trên EOS visibility để bảo đảm chỉ xử lý output đã commit.

### Broker và bảo mật

Kafka cluster phải hỗ trợ transactions và có cấu hình transaction coordinator phù hợp. Producer cần quyền topic WRITE và transactional ID cần thiết; consumer cần quyền READ và group operations. Security/ACL không đúng có thể khiến producer không bắt đầu hoặc commit transaction thành công.

## 7. Ví dụ Java thuần: consume → process → produce

Đây là ví dụ thể hiện các API quan trọng của Kafka client. Nó cố ý tách **transaction processing** khỏi phần **commit** để tránh tự động kết luận transaction đã abort nếu xảy ra timeout khi commit.

~~~java
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;

public class TransactionalBatchProcessor {

    private final KafkaConsumer<String, String> consumer;
    private final KafkaProducer<String, String> producer;

    public TransactionalBatchProcessor(
            KafkaConsumer<String, String> consumer,
            KafkaProducer<String, String> producer) {
        this.consumer = consumer;
        this.producer = producer;
    }

    public void pollAndProcess() throws Exception {

        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofSeconds(1));

        if (records.isEmpty()) {
            return;
        }

        producer.beginTransaction();

        try {
            Map<TopicPartition, OffsetAndMetadata> offsets =
                    new HashMap<>();

            for (TopicPartition tp : records.partitions()) {

                List<ConsumerRecord<String, String>> partitionBatch =
                        records.records(tp);

                for (ConsumerRecord<String, String> record :
                        partitionBatch) {

                    String result = transform(record.value());

                    producer.send(
                            new ProducerRecord<>(
                                    "processed.orders",
                                    record.key(),
                                    result
                            )
                    ).get();
                }

                long lastOffset =
                        partitionBatch.get(
                                partitionBatch.size() - 1
                        ).offset();

                offsets.put(
                        tp,
                        new OffsetAndMetadata(lastOffset + 1L)
                );
            }

            producer.sendOffsetsToTransaction(
                    offsets,
                    consumer.groupMetadata()
            );

        } catch (Exception processingFailure) {
            try {
                producer.abortTransaction();
            } catch (Exception abortFailure) {
                processingFailure.addSuppressed(abortFailure);
            }

            // Chưa cho phép poll thêm rồi bỏ qua records chưa commit.
            // Cần seek/khởi tạo lại theo assignment hiện tại.
            throw processingFailure;
        }

        // Commit được xử lý tách biệt.
        // Nếu lệnh này ném lỗi, KHÔNG kết luận bừa transaction đã abort.
        producer.commitTransaction();
    }

    private String transform(String value) {
        return value.toUpperCase();
    }
}
~~~

Ví dụ trên **không phải một Kafka consumer application hoàn chỉnh để chạy thẳng trong production**. Chưa có:

- Khởi tạo producer bằng transactional.id và initTransactions().
- subscribe/assign, poll loop liên tục và shutdown.
- Rebalance listener, chuyển giao partition và seek sau abort.
- Xử lý producer fatal/fencing.
- Retry/backoff, metric, timeout và tracing.
- Xử lý outcome không chắc chắn khi commitTransaction ném exception.
- Quản lý lifecycle trên nhiều threads và instances.

Nếu transaction abort và consumer vẫn giữ vị trí đọc sau poll, ứng dụng tự viết cần **seek về những offsets chưa commit hoặc tái tạo consumer để nhận lại theo committed offsets**. Không cứ tiếp tục poll record mới sau abort rồi coi input cũ đã xử lý. Spring Kafka container làm nhiều phần orchestration này thay ứng dụng.

## 8. Ví dụ producer initialization và consumer configuration

Producer transactional:

~~~java
Properties producerConfig = new Properties();

producerConfig.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "broker-1:9092,broker-2:9092"
);
producerConfig.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
);
producerConfig.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
);
producerConfig.put(
        ProducerConfig.TRANSACTIONAL_ID_CONFIG,
        "orders-projector-instance-a"
);

KafkaProducer<String, String> producer =
        new KafkaProducer<>(producerConfig);

producer.initTransactions();
~~~

Consumer:

~~~java
Properties consumerConfig = new Properties();

consumerConfig.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "broker-1:9092,broker-2:9092"
);
consumerConfig.put(
        ConsumerConfig.GROUP_ID_CONFIG,
        "orders-projector"
);
consumerConfig.put(
        ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
        false
);
consumerConfig.put(
        ConsumerConfig.ISOLATION_LEVEL_CONFIG,
        "read_committed"
);

consumerConfig.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
);
consumerConfig.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
);
~~~

Giá trị **read_committed** trên input consumer là cần thiết nếu input topic có transactional records và ứng dụng không muốn đọc những records đã bị abort ở upstream. Đối với EOS ở output, điều thiết yếu là **downstream consumer** cũng dùng read_committed.

**transactional.id** cần unique cho mỗi producer đang hoạt động đồng thời trong ngữ cảnh không có intentional takeover. Nếu các replicas dùng trùng transactional.id, producer mới có thể fence producer cũ.

## 9. Điều gì xảy ra bên trong Kafka?

Kafka transaction gồm producer, transaction coordinator, các topic-partitions mà producer ghi tới, và consumer group coordinator phụ trách offsets.

Khi producer gọi **sendOffsetsToTransaction**:

1. Producer xác định consumer group và danh sách offsets cần đưa vào transaction.
2. Kafka transaction coordinator và group coordinator phối hợp để ghi nhận các offsets như một phần của transaction đang diễn ra.
3. Offsets không trở thành group committed checkpoints theo cách độc lập trước khi transaction outcome được quyết định.
4. Khi **commitTransaction()** thành công, transaction coordinator ghi kết quả commit và offsets trở thành committed.
5. Khi abort, offset updates của transaction không được commit.

~~~mermaid
sequenceDiagram
    participant C as Kafka consumer
    participant P as Transactional producer
    participant TC as Transaction coordinator
    participant GC as Group coordinator
    participant O as Output partitions

    C->>C: poll input
    P->>TC: begin transaction
    P->>O: send output records
    P->>TC: add consumer group offsets to transaction
    TC->>GC: coordinate transactional offset commit
    P->>TC: commitTransaction()
    TC->>O: commit markers
    TC->>GC: transaction commit decision
    GC-->>C: next committed input offsets available
~~~

Sơ đồ là khái niệm; giao thức nội bộ có nhiều request, trạng thái và bước phối hợp hơn. Không cần tự mô phỏng protocol khi dùng KafkaProducer/KafkaTemplate đúng cách.

## 10. Producer identity, epoch và fencing

Transactional producer có **transactional.id** và producer epoch. Kafka sử dụng cơ chế này để ngăn một producer cũ tiếp tục ghi dữ liệu như thể vẫn đang sở hữu transaction sau khi một producer mới đã tiếp quản cùng transactional ID.

Ví dụ:

~~~text
Pod A: transactional.id = orders-projector-0
Pod B: transactional.id = orders-projector-0
~~~

Nếu hai pod cùng sống, producer mới có thể fence producer cũ. Producer bị fence có thể ném ProducerFencedException khi send/commit/abort.

Phân biệt:

- **Producer fencing:** ngăn zombie producer dùng transactional.id cũ.
- **Consumer group fencing:** metadata của group generation/member giúp phát hiện commit offset từ consumer không còn là member hợp lệ.
- **Idempotent producer:** tránh ghi trùng do producer retries trên cùng producer session/sequence, nhưng không thay thế transaction cho atomic output + offset.

Trong Spring Kafka, transaction-id-prefix cần được cấu hình sao cho các producer đang hoạt động không dùng trùng ID ngoài ý muốn, đặc biệt trong scale-out, rolling deployment và producer cache.

## 11. Spring Kafka thường tự gọi sendOffsetsToTransaction

Trong ứng dụng Spring Kafka dùng **transactional listener container**, thông thường **không cần gọi sendOffsetsToTransaction thủ công trong method @KafkaListener**.

Container đảm nhiệm:

1. Bắt đầu Kafka transaction cho đơn vị xử lý tương ứng.
2. Gọi listener.
3. Cho listener publish output qua KafkaTemplate gắn với transaction.
4. Sau khi listener xử lý thành công, xác định offsets đã xử lý.
5. Gửi offsets đó vào Kafka transaction.
6. Commit transaction.
7. Nếu lỗi, abort và thực hiện after-rollback processing.

Nhờ đó, listener tập trung vào nghiệp vụ và không phải tự tính offsets hoặc quản lý KafkaConsumer group metadata.

~~~mermaid
flowchart TD
    A["KafkaMessageListenerContainer"] --> B["begin transaction"]
    B --> C["@KafkaListener"]
    C --> D["KafkaTemplate.send() output"]
    D --> E{"Listener thành công?"}
    E -->|Có| F["Container gửi consumed offsets vào transaction"]
    F --> G["Commit Kafka transaction"]
    E -->|Không| H["Abort transaction"]
    H --> I["AfterRollbackProcessor / redelivery"]
~~~

Chú ý: nếu listener tự gọi một API commit offset/ack không phù hợp trong khi container đã điều khiển transaction, có thể gây mâu thuẫn hoặc làm tính toán checkpoint trở nên khó hiểu. Chỉ tự quản lý offsets khi có yêu cầu thiết kế và đã xác định rõ ownership của transaction.

## 12. Cấu hình Spring Boot transactional producer

Một cấu hình Spring Boot thường dùng:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker-1:9092,broker-2:9092
    producer:
      transaction-id-prefix: order-projector-pod-a-
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      group-id: order-projector
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Cấu hình **transaction-id-prefix** cho phép Spring tạo các transactional producer IDs từ prefix và suffix. Spring Boot ở những phiên bản hỗ trợ có thể auto-configure **KafkaTransactionManager** từ transactional producer factory. Cần kiểm tra factory/container thực sự được kết nối transaction manager, nhất là khi ứng dụng tự khai báo listener factory.

Trong deployment nhiều instances, prefix cần được thiết kế để tránh producer ID collisions. Giá trị minh họa pod-a chỉ đại diện cho một instance; không copy nguyên giá trị này sang toàn bộ replicas.

### Cấu hình listener factory

Tùy Spring Kafka version, có thể cấu hình Kafka-aware transaction manager trên container properties:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
transactionalFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        KafkaTransactionManager<String, ProcessedOrder> transactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(transactionManager);

    return factory;
}
~~~

Đây là API minh họa cho các phiên bản Spring Kafka hỗ trợ **setKafkaAwareTransactionManager**; trong codebase cũ method có thể khác. Generic types thực tế của transactional producer phụ thuộc kiểu output records, không cần bằng kiểu consumer input.

### Listener chỉ cần logic nghiệp vụ

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-projector",
    containerFactory = "transactionalFactory"
)
public void onOrder(OrderCreated event) {
    ProcessedOrder output = transform(event);

    kafkaTemplate.send(
            "orders.projected",
            event.orderId(),
            output
    );
}
~~~

Khi listener hoàn tất, container có trách nhiệm đưa offsets đã xử lý vào Kafka transaction trước commit. Nếu listener ném exception, container không được xem lần xử lý đó là thành công và sẽ đi theo rollback/recovery path phù hợp.

**Không phải mọi bean KafkaTransactionManager trong context tự động biến mọi listener thành transactional listener.** Hãy xác minh hiệu lực container factory, Spring Boot auto-configuration và transaction manager theo phiên bản.

## 13. KafkaTemplate và TransactionManager

KafkaTemplate có khả năng tham gia Kafka transaction do Spring quản lý. Một số phiên bản cũng có API **executeInTransaction** cho việc publish nhiều output records trong một transaction cục bộ.

~~~java
kafkaTemplate.executeInTransaction(ops -> {
    ops.send("orders.projected", key, value);
    ops.send("orders.audit", key, auditValue);
    return null;
});
~~~

Tuy nhiên, API này chủ yếu giải quyết nhóm **output records cùng transaction**. Nó không thay thế tự động luồng container commit **input consumer offsets** khi không có transactional listener container phù hợp.

Phân biệt ba trường hợp:

| Cách sử dụng | Kafka output trong transaction | Input offsets cùng transaction |
|---|---|---|
| KafkaTemplate.executeInTransaction để publish thuần | Có | Không tự động nếu không có cơ chế consumer offsets liên quan |
| @Transactional với KafkaTransactionManager cho service publish | Có | Không tự động chỉ vì method có @Transactional |
| Transactional KafkaListenerContainer consume-process-produce | Có | Container có thể gửi consumed offsets vào cùng transaction theo cấu hình |

Không thêm @Transactional vào một listener rồi mặc định rằng Kafka offsets được atomic với output nếu actual listener container không quản lý transaction đúng cách.

## 14. Record listener, batch listener và phạm vi transaction

Cần hiểu chính xác **đơn vị xử lý** mà container dùng làm transaction boundary.

Với một record listener, container có thể lấy nhiều records từ một poll rồi gọi listener từng record. Trong transactional mode, ranh giới transaction và cách commit offsets được framework quyết định; không nên suy luận từ method nhận một record rằng lúc nào cũng có đúng một transaction cho một record.

Với batch listener, method nhận một collection. Transaction có thể bao trùm toàn bộ batch hoặc một đơn vị được container chia theo cấu hình. Nếu một record trong batch thất bại, cần xác định các output records khác trong transaction đó có bị abort không.

Một số cấu hình có **subBatchPerPartition**, cho phép chia batch poll thành các nhóm theo partition. Khi phối hợp transaction manager, việc này có thể thay đổi ranh giới transaction trong các phiên bản tương ứng.

Luôn xác định:

- Listener loại record hay batch.
- Container concurrency.
- Số records mỗi poll.
- Transaction scope của version đang dùng.
- AckMode và error handler/after rollback semantics.
- Những partitions mà transaction có thể commit offsets.
- Khi lỗi một record, phần nào sẽ được giao lại.

Nếu batch đã xử lý ba partitions nhưng chỉ một partition thất bại, không được tự commit offsets của cả ba nếu output transaction đã abort.

## 15. sendOffsetsToTransaction và AckMode

AckMode của Spring Kafka quyết định cách container xác nhận tiến độ trong các mô hình listener thông thường, nhưng khi container dùng Kafka transaction, offsets được đưa vào transaction theo cơ chế transaction-aware của container.

Một số điểm cần tránh nhầm:

- **AckMode.RECORD** không có nghĩa ứng dụng phải tự gọi sendOffsetsToTransaction cho mỗi record.
- **Acknowledgment.acknowledge()** không phải một lời gọi trực tiếp tới KafkaProducer.sendOffsetsToTransaction.
- **Consumer.commitSync()** không thay thế transaction offset commit.
- Khi dùng transaction, nên để container làm chủ offset commit; tránh đường commit song song ngoài transaction.
- Với manual ack, cần hiểu đúng sự phối hợp của acknowledgement và transaction manager trong phiên bản đang dùng.

Hệ thống cần có **một nguồn sở hữu rõ ràng** đối với tiến độ offsets. Trộn commit thông thường với transaction commit mà không có thiết kế sẽ làm mất mục đích atomic consume-process-produce.

## 16. read_committed và Last Stable Offset

Output của Kafka transaction không được bảo vệ với consumer dùng **read_uncommitted** theo cách mong đợi trong EOS pipeline. Để downstream chỉ nhìn thấy output committed, cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
~~~

Khi đọc với read_committed:

- Consumer không trả records từ transactions đã abort.
- Consumer không trả records từ transaction đang mở chưa được commit.
- Consumer vẫn đọc records được publish không giao dịch.
- Kafka sử dụng **Last Stable Offset (LSO)** để giới hạn vị trí có thể trả về khi có open transactions.

Ví dụ transaction T1 viết record A rồi để mở rất lâu. Một read_committed consumer có thể bị chặn ở LSO và chưa đọc những record sau A trên cùng partition, kể cả khi các record sau đến từ producer khác.

Khi monitor lag, cần phân biệt backlog bình thường với delay do long-running/open transactions. Không kết luận Kafka consumer bị hỏng chỉ vì broker có record nhưng read_committed consumer chưa nhìn thấy chúng.

## 17. Fencing do rebalance: tình huống thực tế

Giả sử group inventory-projector có consumer C1 đang xử lý partition P0:

~~~text
T0: C1 poll P0 offset 100.
T1: C1 bắt đầu Kafka transaction.
T2: C1 publish output.
T3: C1 xử lý lâu hơn max.poll.interval.ms.
T4: Consumer group rebalance, P0 được giao cho C2.
T5: C1 cố sendOffsetsToTransaction bằng group metadata cũ.
~~~

Tại T5, group coordination có thể từ chối transactional offset commit vì C1 không còn là member hợp lệ/generation hiện tại. Nếu transaction không thể commit, read_committed consumers sẽ không xem output transaction đó là committed.

Cách giảm rủi ro:

- Rút ngắn thời gian xử lý listener.
- Giới hạn max.poll.records.
- Đặt max.poll.interval.ms dựa trên thời gian xử lý thực tế, không chỉ dựa trên happy path.
- Không giữ Kafka transaction mở khi chờ HTTP API nhiều phút nếu có thể thiết kế lại.
- Dùng Spring Kafka container để phối hợp rebalances và after-rollback logic.
- Theo dõi rebalance count, transaction abort và consumer lag.

Đừng nâng max.poll.interval.ms vô hạn chỉ để tránh rebalance; điều đó làm chậm việc nhận diện consumer không hoạt động.

## 18. transaction.timeout.ms và thời gian xử lý

Kafka producer transaction có **transaction.timeout.ms** và broker có giới hạn transaction timeout. Nếu transaction mở lâu vượt ngưỡng, broker có thể abort nó. Một transaction được abort sẽ không commit input offsets đã đưa vào bằng sendOffsetsToTransaction.

Cùng lúc, Kafka consumer có **max.poll.interval.ms**. Một listener có thể chạm cả transaction timeout lẫn poll interval nếu xử lý quá nhiều record hoặc chờ downstream.

| Cấu hình | Phạm vi |
|---|---|
| transaction.timeout.ms | Giới hạn thời gian Kafka producer transaction mở |
| transaction.max.timeout.ms | Giới hạn timeout do broker cho phép |
| max.poll.interval.ms | Giới hạn khoảng thời gian giữa những lần poll |
| max.poll.records | Số records tối đa trả về ở mỗi lần poll |
| delivery.timeout.ms | Thời gian tối đa producer cố hoàn tất record send |
| request.timeout.ms | Thời gian chờ một request của client |

Không xử lý các vấn đề transaction timeout bằng cách chỉ tăng một tham số. Đo transaction duration, số records/partition và dependency latency, rồi chọn transaction scope phù hợp.

## 19. Khi listener exception hoặc producer send thất bại

Với transactional listener container, nếu listener ném exception, Kafka transaction thường được abort và offset transaction không được commit. Sau rollback, **AfterRollbackProcessor** có thể thực hiện seek/redelivery hoặc recovery theo phiên bản và cấu hình.

Nếu ứng dụng tự dùng KafkaProducer:

- Lỗi xử lý trước commit thường cần abort nếu transaction vẫn ở trạng thái có thể abort.
- Fencing/fatal producer errors có thể yêu cầu đóng producer, không tiếp tục dùng.
- Sau abort, consumer cần đọc lại offsets chưa commit hoặc seek đúng vị trí.
- Không xem send() gọi thành công là đủ để kết luận output committed.
- Nếu lỗi xảy ra trong commitTransaction, cần phân tích outcome theo loại exception trước khi quyết định đường phục hồi.

Không bắt exception của listener rồi trả về bình thường nếu nghiệp vụ thật ra chưa hoàn tất:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "transactionalFactory"
)
public void handle(OrderCreated record) {
    try {
        businessService.process(record);
    } catch (RuntimeException ex) {
        log.error("Processing failed", ex);
        // Sai nếu muốn container rollback: đã nuốt exception.
    }
}
~~~

Đường đơn giản là để exception thoát ra ngoài:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "transactionalFactory"
)
public void handle(OrderCreated record) {
    businessService.process(record);
}
~~~

Với những lỗi nghiệp vụ được chủ đích bỏ qua, hãy mô hình hóa kết quả xử lý rõ ràng; không dùng kỹ thuật “nuốt lỗi” một cách tùy tiện làm thay đổi checkpoint.

## 20. Commit outcome không chắc chắn

Một lỗi khó nhất là client gọi **commitTransaction()**, nhưng connection bị ngắt trước khi nhận phản hồi. Kafka broker có thể đã commit, hoặc transaction chưa commit. Không nên giả định kết quả chỉ từ timeout ở ứng dụng.

Các nguyên tắc:

1. Phân biệt lỗi send, lỗi sendOffsetsToTransaction và lỗi commitTransaction.
2. Không catch mọi commit exception rồi gọi abort hoặc gửi lại output vô điều kiện.
3. Xem exception type và contract của Kafka client phiên bản đang dùng.
4. Khi producer ở fatal state, đóng nó và khởi tạo lại theo transaction recovery policy.
5. Dùng event IDs và idempotency để đối phó với redelivery hoặc kết quả commit không xác định.
6. Đối chiếu input committed offsets và downstream visibility sau khi hệ thống ổn định.
7. Nếu có side effect ngoài Kafka, chạy reconciliation theo domain.

Kafka EOS xử lý tốt hơn bài toán atomic Kafka output + Kafka offsets, nhưng không biến network thành kênh phản hồi commit luôn chắc chắn ở góc nhìn ứng dụng.

## 21. Vì sao cần idempotency dù đã dùng EOS?

**Exactly-once semantics trong Kafka** không đồng nghĩa listener method chỉ chạy đúng một lần. Một listener có thể bắt đầu, gửi output, transaction abort rồi được gọi lại. Các thao tác nội bộ (CPU, log, database, HTTP call) có thể chạy nhiều lần, nhưng read_committed consumers chỉ thấy output Kafka từ transaction committed.

Nếu listener cập nhật database trước khi Kafka transaction commit:

~~~text
1. Database update COMMIT.
2. Kafka transaction COMMIT thất bại.
3. Input offset chưa tiến cùng transaction.
4. Record được giao lại.
5. Database update có nguy cơ chạy lần thứ hai.
~~~

Để bảo vệ database, dùng **transactional inbox**:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(120) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong cùng database transaction, insert marker theo unique event_id và thực hiện thay đổi nghiệp vụ. Nếu record được giao lại sau Kafka abort, database có thể nhận diện duplicate.

Nếu cần phát event Kafka sau database commit, dùng **transactional outbox** để lưu domain change và outgoing event trong cùng database transaction, rồi có publisher riêng gửi ra Kafka.

Không dùng sendOffsetsToTransaction để thay thế inbox/outbox: API này chỉ phối hợp **Kafka consumer offsets** với **Kafka producer transaction**, không commit một external database hoặc REST API.

## 22. So sánh một số chiến lược bảo đảm xử lý

| Chiến lược | Output Kafka + input offset atomic | Chống duplicate external side effect | Complexity |
|---|---|---|---|
| Non-transactional producer + consumer commit riêng | Không | Không tự động | Thấp |
| Idempotent producer, commit offset riêng | Không | Không tự động | Vừa |
| Kafka transaction + sendOffsetsToTransaction | Có, trong Kafka | Không tự động | Vừa/cao |
| Kafka transaction + inbox database | Có trong Kafka; inbox bảo vệ database riêng | Có nếu triển khai chính xác | Cao |
| Database outbox + idempotent publisher | DB change + outbox atomic; Kafka publish riêng | Có thể đạt reliability bằng idempotency | Cao |
| Saga/workflow | Phụ thuộc orchestration | Cần thiết kế compensation/idempotency | Cao |

Idempotent producer giúp tránh duplicate do retry ở producer, nhưng một event bị ứng dụng xử lý lại sau consumer offset issue vẫn có thể tạo output mới. Kafka transaction kết hợp offsets giải quyết một lớp duplicate khác quan trọng trong Kafka-to-Kafka pipeline.

## 23. Partition ordering và tính đúng đắn của offsets

Kafka giữ thứ tự trong từng partition. Với transactional offset commit, phải bảo đảm offset tiến qua một dải record **đã xử lý hoàn chỉnh**.

Giả sử P0 có:

~~~text
Offset 10: success
Offset 11: failure
Offset 12: success (được xử lý bất đồng bộ)
~~~

Nếu commit offset 13 trong transaction sau khi chỉ có 10 và 12 hoàn tất, record 11 có thể bị bỏ qua khi restart. Đây là bug logic, dù commit transaction về mặt giao thức thành công.

Hệ thống phải chọn:

- Xử lý tuần tự theo partition.
- Chờ tất cả các jobs trước checkpoint hoàn tất.
- Dùng contiguous completed offset tracking cho asynchronous processing.
- Không commit vượt qua khoảng trống chưa xử lý.

Khi dùng KafkaListener container mặc định, tránh tự chuyển record sang executor bất đồng bộ rồi trả về ngay nếu container sẽ đánh dấu listener đã hoàn tất trước khi side effect/output thực sự hoàn thành. Nếu dùng async acknowledgements hoặc asynchronous listener APIs theo phiên bản, phải hiểu rõ cách framework theo dõi completion, ordering và transaction boundary.

## 24. Multi-partition poll và transaction scope

Một consumer có thể poll nhiều partitions cùng lúc. Nếu xử lý tất cả trong một transaction, offsets map phải chứa riêng các partitions đã xử lý.

Ví dụ:

~~~text
Poll:
  orders.created-0 : offsets 2, 3
  orders.created-1 : offsets 20, 21, 22
  orders.created-2 : offset 105

Transaction outputs:
  6 processed records

sendOffsetsToTransaction:
  orders.created-0 -> 4
  orders.created-1 -> 23
  orders.created-2 -> 106
~~~

Nếu transaction abort vì một record lỗi, offsets cả ba partitions trong transaction sẽ không commit. Khi ứng dụng khởi động lại, có thể đọc lại dữ liệu đã xử lý trong lần thử thất bại. Điều này đúng với atomic transaction scope, nhưng có thể làm tăng chi phí xử lý lại.

Nếu workload có nhiều partitions và batch lớn, cân nhắc transaction scope theo partition hoặc batch nhỏ hơn khi Spring Kafka version cho phép. Không tự commit một phần map offsets trong transaction đã abort.

## 25. Khi nào không nên tự gọi API này?

Trong ứng dụng Spring Kafka dùng **@KafkaListener** và transactional container được cấu hình đúng, thường **không cần viết code gọi sendOffsetsToTransaction**.

Tự gọi trực tiếp trong listener có những rủi ro:

- Không có quyền truy cập consumer group metadata đúng cách.
- Gửi sai offset vì nhầm record đã xử lý.
- Commit offsets hai lần hoặc đi đường riêng với container.
- Không quản lý rebalance/seek/abort đúng chuẩn.
- Trộn producer của container với một producer transaction khác.
- Đưa offsets vào transaction không chứa đúng output records.
- Không xử lý transaction outcome khi commit thất bại.

Chỉ tự dùng KafkaProducer API khi bạn đang triển khai một consumer loop riêng, một framework adapter hoặc có yêu cầu kỹ thuật buộc kiểm soát transaction trực tiếp. Ngay cả khi đó cũng cần integration tests với broker thật.

## 26. Monitoring và observability

Các metric nên theo dõi:

| Metric | Mục đích |
|---|---|
| Transaction begin/commit/abort count | Theo dõi transaction outcome |
| Transaction duration | Phát hiện giao dịch mở quá lâu |
| Producer commit latency | Phát hiện coordinator/network bất thường |
| Offset-in-transaction failure rate | Phát hiện lỗi nhóm consumer hoặc coordinator |
| Producer fencing errors | Phát hiện tranh chấp transactional.id |
| Consumer group rebalance count | Liên hệ với stale group metadata |
| Consumer lag | Backlog đầu vào |
| Read-committed visibility delay | Thời gian output chờ transaction commit |
| Transaction timeout count | Phát hiện transaction quá dài |
| AfterRollbackProcessor retry/recovery | Quan sát redelivery sau abort |
| Downstream failure rate | Hiểu lý do transaction abort |

Một log sự kiện theo transaction có thể chứa:

~~~text
event=kafka_transaction_committed
service=orders-projector
instance=pod-a
consumer_group=orders-projector
input_topic=orders.created
input_partition=1
next_committed_offset=101
transaction_id_prefix=orders-projector-pod-a-
duration_ms=48
~~~

Không dùng offset, event ID hoặc transactional.id thay đổi liên tục làm metric tags vì cardinality tăng cao. Các giá trị đó phù hợp hơn với structured logs hoặc traces có kiểm soát.

### Alert nên ưu tiên

- Transaction abort rate tăng sau deploy.
- ProducerFencedException xuất hiện hàng loạt.
- Commit latency tăng cùng với consumer lag.
- max.poll.interval.ms violations hoặc rebalance liên tục.
- read_committed downstream lag tăng do transaction mở lâu.
- AfterRollbackProcessor liên tục retry cùng record mà không phục hồi.
- Có output không đi kèm input offset commit do cấu hình transaction thiếu.

## 27. Các lỗi triển khai thường gặp

**Commit offset bằng chính offset vừa xử lý.** Phải dùng last processed offset + 1.

**Tính một offset chung cho cả poll.** Offset là riêng cho từng topic-partition.

**Commit qua record chưa xử lý xong.** Có thể làm mất dữ liệu nghiệp vụ dù transaction commit thành công.

**Dùng consumer.commitSync() bên cạnh transaction commit.** Tạo một đường checkpoint không được atomic cùng output.

**Quên enable.auto.commit=false.** Auto-commit có thể tiến offset bên ngoài Kafka transaction.

**Chưa beginTransaction nhưng gọi sendOffsetsToTransaction.** API yêu cầu transactional producer với transaction đang mở.

**Không lấy ConsumerGroupMetadata từ consumer thật.** Có thể thiếu generation/member information và fencing phù hợp.

**Coi API call sendOffsetsToTransaction đã commit.** Cần commitTransaction để outcome có hiệu lực.

**Downstream đọc read_uncommitted.** Có thể thấy output đã abort.

**Trùng transactional.id khi scale-out.** Producer mới fence producer cũ.

**Listener nuốt exception.** Container có thể commit transaction và offsets dù nghiệp vụ thất bại.

**Khi transaction abort vẫn tiếp tục poll từ vị trí cũ trong custom loop.** Có thể bỏ record chưa commit; cần seek/reinitialize phù hợp.

**Cho rằng EOS bảo vệ database và HTTP API.** Cần inbox/outbox/idempotency.

**Không thử rebalance giữa lúc xử lý.** Lỗi stale group metadata có thể xảy ra ngay dưới tải thực tế.

## 28. Tình huống sự cố: timeout khi gửi offsets

Giả sử ứng dụng đã publish output records trong transaction nhưng **sendOffsetsToTransaction** thất bại do coordinator timeout.

Điều chưa được bảo đảm:

- Không thể coi output đã committed.
- Không thể coi input offsets đã tiến.
- Không thể kết luận chỉ vì send output future hoàn tất là pipeline thành công.

Cách phản ứng:

1. Ghi exception và phân loại retryable/fatal/fencing.
2. Nếu transaction ở trạng thái có thể abort theo contract của client, abort có kiểm soát.
3. Nếu producer bị fenced hoặc fatal, đóng producer và khởi tạo lại theo policy.
4. Không tiếp tục poll và bỏ qua input chưa commit.
5. Để consumer group nhận lại records theo committed offset hoặc seek lại khi assignment còn hợp lệ.
6. Theo dõi transaction coordinator và group coordinator health.
7. Kiểm tra rebalance xảy ra trong lúc xử lý không.
8. Dùng idempotency cho side effects có thể đã diễn ra ngoài Kafka.

Không tự động gọi commitSync() sau khi sendOffsetsToTransaction lỗi để “cứu offset”. Điều đó phá mục tiêu atomic Kafka transaction.

## 29. Tình huống sự cố: producer bị fenced

Nếu producer bị fence bởi một producer khác cùng transactional.id:

~~~text
Producer A begins transaction
Producer B starts with same transactional.id
Kafka increments epoch for that identity
Producer A tries sendOffsetsToTransaction/commit
Producer A is fenced
~~~

Hành động:

- Đóng Producer A; không tái sử dụng.
- Xác định nguyên nhân trùng transactional.id.
- Kiểm tra rolling deployment, replica count và transaction-id-prefix.
- Để instance có ownership hợp lệ tiếp tục xử lý.
- Đối chiếu consumer group assignment và các transactional offsets.
- Theo dõi việc records của transaction cũ không visible với read_committed consumers khi transaction không commit.

Đừng “khắc phục” bằng cách tắt idempotence hoặc bỏ transactional.id. Việc đó bỏ luôn cơ chế bảo vệ transaction và fencing mà hệ thống đang cần.

## 30. Kiểm thử integration với Kafka broker

Unit test có thể xác minh map offsets được tính đúng. Nhưng để chứng minh atomic Kafka output + offsets, cần Kafka broker thực hoặc Testcontainers.

Các kịch bản:

| Test | Kỳ vọng |
|---|---|
| Input 1 record, output 1 record, commit | read_committed thấy output; group offset = input offset + 1 |
| Input nhiều partitions | Mỗi partition có next offset độc lập |
| Send output rồi abort | read_committed không thấy output; group offsets không tiến |
| Producer chết trước commit | Transaction không commit; input có thể được xử lý lại |
| Producer chết sau commit | Output và input offsets cùng committed |
| sendOffsetsToTransaction dùng group metadata cũ | Commit bị từ chối theo fencing/group rules khi phù hợp |
| Consumer rebalance trong xử lý | Không âm thầm commit offsets stale |
| Duplicate transactional.id | Producer fencing được phát hiện |
| Downstream read_uncommitted | Có thể thấy aborted/uncommitted output, minh họa giới hạn |
| Database side effect rồi abort | Inbox/idempotency ngăn duplicate khi redelivery |
| Batch một phần thất bại | Không commit vượt records chưa hoàn thành |
| Transaction timeout | Abort/failure được quan sát, không tạo checkpoint sai |

### Gợi ý assertions

1. Dùng group ID test riêng, không chia committed offsets với test khác.
2. Gửi input record có event ID xác định.
3. Chạy transactional listener với output topic.
4. Chờ output bằng read_committed consumer.
5. Kiểm tra committed offset của input group đúng vị trí next offset.
6. Gây exception trong listener, xác nhận không xuất output committed.
7. Xác nhận input có thể redeliver hoặc đi recovery theo policy.
8. Thử rollback trong lúc output send futures đã hoàn thành để chứng minh send không tương đương commit.
9. Thử nhiều partitions và tính offset riêng.
10. Dùng assertion polling có timeout, không chỉ Thread.sleep cố định.

Khi chạy tests có transactions, topic và group metadata cần được cleanup hoặc cô lập phù hợp; tránh dùng lại transactional.id đồng thời từ các test khác nhau.

## 31. Runbook khi exactly-once pipeline không tiến

Nếu pipeline xử lý input nhưng output không visible hoặc consumer lag tăng:

1. Xác định listener ID, service, consumer group và transactional.id/prefix.
2. Xác minh container thực sự transactional, không chỉ có KafkaTransactionManager bean tồn tại.
3. Kiểm tra producer begin/commit/abort logs và send failures.
4. Kiểm tra input offset có được đưa vào transaction hay không.
5. Đối chiếu map offsets theo từng topic-partition, đặc biệt offset + 1.
6. Xác định consumer group metadata có hợp lệ khi gọi sendOffsetsToTransaction.
7. Kiểm tra rebalance, max.poll.interval.ms và transaction.timeout.ms.
8. Kiểm tra producer fencing/transactional ID collisions.
9. Xác nhận downstream dùng read_committed nếu cần EOS visibility.
10. Đối chiếu Last Stable Offset và các open transactions.
11. Kiểm tra listener có nuốt exception hoặc trả về trước khi async processing hoàn thành không.
12. Nếu transaction abort, xác minh redelivery/AfterRollbackProcessor không bị mắc kẹt.
13. Nếu có DB/API ngoài Kafka, xác minh inbox/outbox/reconciliation.
14. Sau sửa, theo dõi commit rate, abort rate, consumer lag và duplicate side effects.

Không dùng commitSync() để đẩy offsets qua một transaction đang lỗi. Nếu output không committed, việc tiến offset riêng có thể gây mất dữ liệu đầu ra.

## 32. Checklist trước production

**Producer và transaction**

- [ ] Transactional producer có unique transactional.id giữa các live instances.
- [ ] Đã gọi initTransactions hoặc dùng ProducerFactory của Spring Kafka.
- [ ] Output records được publish trong cùng Kafka transaction.
- [ ] sendOffsetsToTransaction được gọi trước commitTransaction trong custom loop.
- [ ] Producer fatal/fencing errors có đường xử lý rõ ràng.
- [ ] Transaction timeouts và commit latency được đo.

**Consumer offsets**

- [ ] Consumer group có group.id rõ ràng, auto-commit tắt.
- [ ] Offset map tính theo từng TopicPartition.
- [ ] Committed offset là next offset sau record cuối đã xử lý liên tục.
- [ ] Không commit vượt record chưa hoàn thành.
- [ ] ConsumerGroupMetadata lấy từ consumer đang thuộc group.
- [ ] Rebalance/abort có xử lý seek hoặc replay phù hợp.

**Spring Kafka**

- [ ] Listener container có Kafka-aware transaction manager phù hợp.
- [ ] KafkaTemplate dùng transactional ProducerFactory đồng bộ với container.
- [ ] Không gọi commit offset thủ công trùng với container ownership.
- [ ] AfterRollbackProcessor và recovery policy được xác định.
- [ ] Downstream cần EOS dùng isolation.level=read_committed.

**Nghiệp vụ và vận hành**

- [ ] Side effects ngoài Kafka có idempotency/inbox/outbox.
- [ ] Có integration tests commit, abort, crash, rebalance và fencing.
- [ ] Có metrics transaction duration, commit/abort và lag.
- [ ] Không coi send success là transaction committed.
- [ ] Có runbook khi commit outcome không chắc chắn.
- [ ] DLT/replay không phá business consistency.

## 33. Tóm lược nguyên tắc

**sendOffsetsToTransaction** gắn **input consumer group offsets** vào Kafka producer transaction đang chứa các output records. Khi transaction commit, output và input checkpoint cùng được committed trong Kafka; khi abort, cả output transactional và offset update không có hiệu lực commit. Điều này là nền tảng để xây dựng exactly-once Kafka-to-Kafka processing.

Ba điểm cần nhớ: **(1)** commit offset kế tiếp, tức last processed offset + 1 cho từng TopicPartition; **(2)** dùng ConsumerGroupMetadata của consumer đang thực sự tham gia group để phục vụ fencing; **(3)** sendOffsetsToTransaction chỉ chuẩn bị offset update, còn commitTransaction mới quyết định kết quả transaction. Trong Spring Kafka, nên để transactional listener container quản lý thao tác này thay vì tự gọi từ @KafkaListener.

Cuối cùng, Kafka exactly-once không bảo đảm listener chỉ chạy một lần và không tự làm transaction nguyên tử với database hay HTTP API. Hãy bổ sung idempotency, inbox/outbox, quản lý transactional IDs, read_committed consumers, kiểm thử crash/rebalance và monitoring để EOS thật sự bảo vệ hệ thống trong production.

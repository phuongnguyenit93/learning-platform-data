# Commit transaction

Trong Spring Kafka, **commit transaction** là bước kết thúc thành công một **Kafka transaction**: Kafka transaction coordinator ghi nhận transaction đã được commit để những record được publish trong transaction trở nên nhìn thấy đối với consumer dùng **isolation.level=read_committed**. Nếu transaction đồng thời chứa các consumer offsets thông qua cơ chế **sendOffsetsToTransaction**, các offset đó được commit cùng với các record đầu ra. Đây là nền tảng để xây dựng luồng **consume → process → produce** có exactly-once semantics **trong phạm vi Kafka**.

Commit transaction **không giống** việc gọi KafkaTemplate.send(), không giống flush producer, cũng không giống commit offset đơn lẻ. Một lời gọi send có thể hoàn tất việc ghi dữ liệu vào log Kafka trong khi transaction vẫn chưa kết thúc; với consumer đọc committed-only, record đó chưa thể được xử lý trước khi transaction commit.

Trong sản xuất, cần hiểu chính xác điều gì được commit, khi nào commit thành công, cách nhận diện commit failure và giới hạn của exactly-once với database hoặc API ngoài Kafka.

## 1. Kafka transaction giải quyết vấn đề nào?

Giả sử một consumer đọc event **orders.created**, xử lý và ghi hai event tiếp theo:

- **inventory.reserved**
- **billing.requested**

Nếu dùng producer không giao dịch, send đầu tiên có thể thành công còn send thứ hai thất bại. Một consumer downstream có thể thấy inventory đã được giữ chỗ nhưng không có billing request. Khi producer giao dịch, hai record có thể được ghi trong cùng Kafka transaction và chỉ được coi là **committed** cùng nhau.

Với ứng dụng vừa đọc Kafka vừa ghi Kafka, còn một vấn đề khác: đã ghi output nhưng offset input chưa được commit thì sau restart, input có thể được xử lý lại. Kafka transaction cho phép thêm **offset input** vào transaction chứa output records, để commit cả hai như một đơn vị trong hệ thống Kafka.

~~~mermaid
flowchart LR
    A["Input topic: orders.created"] --> B["Consumer / listener"]
    B --> C["Xử lý dữ liệu"]
    C --> D["Kafka transaction"]
    D --> E["Output: inventory.reserved"]
    D --> F["Output: billing.requested"]
    D --> G["Offset input"]
    E --> H{"Commit transaction"}
    F --> H
    G --> H
    H -->|Thành công| I["Output visible với read_committed và offset tiến"]
    H -->|Abort| J["Output aborted, offset không được commit trong transaction"]
~~~

Kafka vẫn có thể lưu các record đã được gửi vào log trước khi commit. Transaction commit/abort markers và isolation của consumer quyết định record nào được phép trả về cho ứng dụng.

## 2. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa |
|---|---|
| **send()** | Gửi một record tới producer; thao tác có thể hoàn tất bất đồng bộ |
| **flush()** | Chờ những record đang đợi producer gửi hoàn tất ở cấp producer |
| **beginTransaction()** | Bắt đầu transaction cho transactional producer |
| **commitTransaction()** | Yêu cầu transaction coordinator hoàn tất transaction với trạng thái commit |
| **abortTransaction()** | Hủy transaction đang xử lý nếu trạng thái/API cho phép |
| **commitSync()/commitAsync()** của consumer | Commit offset thông thường, không tự gắn với Kafka producer transaction |
| **sendOffsetsToTransaction()** | Đưa offsets của consumer group vào producer transaction |
| **@Transactional** với KafkaTransactionManager | Quản lý transaction boundary qua Spring |
| **read_committed** | Consumer chỉ trả về record thuộc transaction đã commit hoặc record không giao dịch |
| **read_uncommitted** | Consumer có thể thấy record của transaction chưa commit hoặc đã abort |

Không thể thay commitTransaction bằng flush. Flush chỉ nói rằng các send được hoàn tất ở cấp producer; nó không ghi quyết định commit của transaction coordinator.

## 3. Vòng đời một Kafka transaction

Với producer API thuần, trình tự khái niệm:

1. Khởi tạo producer có **transactional.id** và serializer thích hợp.
2. Gọi **initTransactions()** trước khi thực hiện transaction đầu tiên.
3. Gọi **beginTransaction()**.
4. Gửi một hoặc nhiều record.
5. Tùy use case, thêm consumer offsets bằng **sendOffsetsToTransaction()**.
6. Nếu toàn bộ công việc hợp lệ, gọi **commitTransaction()**.
7. Nếu có lỗi trước giai đoạn commit và transaction vẫn có thể abort, gọi **abortTransaction()**.
8. Đóng producer hoặc tái sử dụng producer cho transaction tiếp theo theo lifecycle.

~~~mermaid
stateDiagram-v2
    [*] --> Ready: initTransactions()
    Ready --> InTransaction: beginTransaction()
    InTransaction --> InTransaction: send()/sendOffsetsToTransaction()
    InTransaction --> Committing: commitTransaction()
    InTransaction --> Aborting: abortTransaction()
    Committing --> Ready: commit thành công
    Aborting --> Ready: abort thành công
    Committing --> Failed: lỗi nghiêm trọng / kết quả không chắc chắn
    Aborting --> Failed: lỗi khi abort
    Failed --> [*]: đóng producer, phục hồi an toàn
~~~

Sơ đồ thể hiện logic ứng dụng; Kafka producer có nhiều trạng thái nội bộ hơn. Không dùng sơ đồ để suy luận rằng producer luôn có thể tái sử dụng sau bất kỳ exception nào. Những lỗi như fencing hoặc producer fatal error có thể buộc ứng dụng đóng producer và tạo producer khác.

## 4. Cấu hình Kafka producer có transaction

Kafka producer giao dịch cần **transactional.id**. Đây là định danh mà transaction coordinator dùng để quản lý epoch, trạng thái transaction và fencing producer cũ.

Ví dụ Java Kafka client:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;

Properties config = new Properties();
config.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "broker-1:9092,broker-2:9092"
);
config.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
);
config.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
);
config.put(
        ProducerConfig.TRANSACTIONAL_ID_CONFIG,
        "orders-service-instance-a"
);

KafkaProducer<String, String> producer =
        new KafkaProducer<>(config);

producer.initTransactions();
~~~

Khi cấu hình transactional.id, Kafka client áp dụng các ràng buộc phù hợp với transactional producer, bao gồm idempotent producer. Tuy nhiên, ứng dụng vẫn cần kiểm tra **acks**, retries, delivery timeout, broker compatibility và quyền transactional ID theo môi trường đang chạy.

Mỗi producer giao dịch đang hoạt động cần transactional ID tránh va chạm ngoài ý muốn. Nếu hai producer đồng thời dùng cùng transactional.id, producer có epoch mới có thể **fence** producer cũ. Fencing hữu ích để ngăn zombie producer nhưng sẽ gây lỗi nếu nhiều instance cùng lấy trùng ID mà không chủ đích.

## 5. Commit transaction bằng KafkaProducer API

Ví dụ gửi hai output records trong cùng transaction:

~~~java
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;

public void publishBoth(
        KafkaProducer<String, String> producer,
        String orderId,
        String inventoryPayload,
        String billingPayload) throws Exception {

    producer.beginTransaction();

    boolean commitStarted = false;

    try {
        producer.send(new ProducerRecord<>(
                "inventory.reserved",
                orderId,
                inventoryPayload
        )).get();

        producer.send(new ProducerRecord<>(
                "billing.requested",
                orderId,
                billingPayload
        )).get();

        commitStarted = true;
        producer.commitTransaction();

    } catch (Exception ex) {

        if (!commitStarted) {
            try {
                producer.abortTransaction();
            } catch (Exception abortFailure) {
                ex.addSuppressed(abortFailure);
            }
        }

        throw ex;
    }
}
~~~

Trong ví dụ, các lời gọi **get()** đợi kết quả send để phát hiện failure trước khi thử commit. Việc đợi là lựa chọn minh họa giúp transaction boundary rõ ràng; trong hệ thống throughput cao, có thể dùng bất đồng bộ và thu thập các completion signals trước khi commit theo cơ chế phù hợp.

Biến commitStarted giúp phân biệt lỗi **trước khi bắt đầu commit** với lỗi **trong lúc commit**. Khi commitTransaction đã được gọi mà ném exception, outcome có thể phụ thuộc loại exception và trạng thái coordinator; không nên tùy tiện gọi abort rồi kết luận transaction chắc chắn chưa commit. Cần xử lý theo contract của Kafka client/version, và nếu không xác định chắc chắn trạng thái, dừng producer, dùng idempotency và cơ chế phục hồi an toàn.

Đối với ứng dụng Spring Kafka, thường nên dùng KafkaTemplate và KafkaTransactionManager thay vì tự quản lý transactional producer.

## 6. Commit transaction khác commit offset

**Commit offset thông thường** lưu vị trí consumer group đã xử lý để lần khởi động sau có thể tiếp tục đọc từ đó. **Commit Kafka transaction** quyết định trạng thái của những record được producer giao dịch phát ra và có thể commit thêm offsets được gửi vào transaction.

Ví dụ nếu consumer đọc offset 42 và tạo output:

~~~text
Input: orders.created-0, offset 42
Output: inventory.reserved, order 9001
Offset phải lưu tiếp theo: 43
~~~

Một số trường hợp:

| Cách xử lý | Khi process chết sau khi publish output nhưng trước offset commit |
|---|---|
| Publish không transaction, commit offset riêng | Input offset 42 có thể được xử lý lại và tạo output trùng |
| Kafka transaction chứa output và input offset | Nếu transaction chưa commit, output không visible với read_committed và offset transaction chưa tiến |
| Kafka transaction đã commit | Output và offset input cùng được commit trong Kafka transaction |
| Database update ngoài transaction Kafka | Không có atomicity tự động giữa database và Kafka |

Nếu một partition xử lý các record đến offset 42, giá trị offset được lưu là **43**: vị trí record tiếp theo cần đọc. Nhầm commit offset 42 thay vì 43 có thể gây xử lý lại record cuối.

## 7. Đưa consumer offsets vào Kafka transaction

Kafka client cung cấp API **sendOffsetsToTransaction** để thêm offsets của một consumer group vào producer transaction. Đây là cơ chế quan trọng để đạt exactly-once processing khi input và output đều nằm trên Kafka.

Luồng khái niệm:

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

void processPollTransactionally(
        KafkaConsumer<String, String> consumer,
        KafkaProducer<String, String> producer) throws Exception {

    ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofSeconds(1));

    if (records.isEmpty()) {
        return;
    }

    producer.beginTransaction();

    boolean commitStarted = false;

    try {
        Map<TopicPartition, OffsetAndMetadata> nextOffsets =
                new HashMap<>();

        for (TopicPartition partition : records.partitions()) {

            List<ConsumerRecord<String, String>> batch =
                    records.records(partition);

            for (ConsumerRecord<String, String> record : batch) {
                String output = transform(record.value());

                producer.send(new ProducerRecord<>(
                        "processed.events",
                        record.key(),
                        output
                )).get();
            }

            ConsumerRecord<String, String> last =
                    batch.get(batch.size() - 1);

            nextOffsets.put(
                    partition,
                    new OffsetAndMetadata(last.offset() + 1)
            );
        }

        producer.sendOffsetsToTransaction(
                nextOffsets,
                consumer.groupMetadata()
        );

        commitStarted = true;
        producer.commitTransaction();

    } catch (Exception ex) {
        if (!commitStarted) {
            try {
                producer.abortTransaction();
            } catch (Exception abortFailure) {
                ex.addSuppressed(abortFailure);
            }
        }
        throw ex;
    }
}
~~~

Code minh họa một lần poll, một transaction. Nó chưa triển khai đầy đủ vòng poll liên tục, shutdown/rebalance listener, seek lại các offset chưa commit sau abort, error classification và lifecycle producer. Khi tự viết consumer loop, phải xử lý những vấn đề đó để không bỏ record sau transaction rollback. Trong Spring Kafka, nên để container quản lý.

Đặc biệt, **sendOffsetsToTransaction** phải dùng metadata của consumer group đang sở hữu các partition và đúng offsets cần commit. API mới nhận **ConsumerGroupMetadata** giúp transaction coordinator kiểm tra thông tin group phù hợp với cơ chế fencing và group membership; không dùng group ID hay metadata tự dựng tùy tiện.

## 8. Kafka transactions trong Spring Boot

Spring Boot hỗ trợ auto-configuration của Kafka transactional producer khi khai báo **transaction-id-prefix**:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker-1:9092,broker-2:9092
    producer:
      transaction-id-prefix: orders-service-instance-a-
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Khi có transactional producer factory, Spring Boot có thể auto-configure **KafkaTransactionManager** và KafkaTemplate tương ứng theo phiên bản Boot đang sử dụng. Mục tiêu là để Spring quản lý producer lifecycle, transaction begin/commit/abort và khả năng tái sử dụng producer cache.

**transaction-id-prefix** không phải một transactional.id duy nhất. Spring Kafka tạo transactional IDs bằng cách kết hợp prefix và suffix/sequence theo cơ chế phiên bản. Mỗi instance chạy đồng thời phải có namespace ID không va chạm với instance khác. Trên Kubernetes, prefix có thể chứa pod identity hoặc một định danh instance ổn định theo chiến lược triển khai.

Không hard-code cùng một prefix cho tất cả replicas nếu cơ chế cấp suffix của các instance có thể tạo ID trùng. Trùng transactional.id dẫn đến **ProducerFencedException** hoặc lỗi transaction khó phân tích.

## 9. KafkaTemplate.executeInTransaction

Nếu ứng dụng chỉ cần gửi nhiều Kafka records như một nhóm nguyên tử và không nhận input từ Kafka trong cùng transaction, có thể dùng **KafkaTemplate.executeInTransaction**:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishEvents(
            OrderEvent inventoryEvent,
            OrderEvent billingEvent) {

        kafkaTemplate.executeInTransaction(operations -> {
            operations.send(
                    "inventory.events",
                    inventoryEvent.orderId(),
                    inventoryEvent
            );

            operations.send(
                    "billing.events",
                    billingEvent.orderId(),
                    billingEvent
            );

            return null;
        });
    }
}
~~~

Callback được thực thi trong transaction do KafkaTemplate quản lý. Khi callback hoàn tất bình thường, template cố commit. Khi callback ném lỗi, template thực hiện rollback/abort theo semantics của transactional producer.

Các thao tác send trong Spring Kafka hiện đại thường trả về **CompletableFuture**. Nếu nghiệp vụ cần biết một send đã thất bại trước khi callback trả về, cần await/combine futures hoặc thiết kế callback ném lỗi phù hợp. Không xem việc gọi send() không ném exception ngay là bảo đảm publish thành công. Transaction commit cũng có thể phát hiện producer errors, nhưng xử lý exception rõ ràng giúp biết record nào gây lỗi.

Trong production, nên dùng timeout phù hợp khi đợi producer future và quan sát exception từ send lẫn commit. Không dùng executeInTransaction để bao bọc database writes rồi cho rằng database tự tham gia Kafka transaction.

## 10. @Transactional với KafkaTransactionManager

Spring Kafka cung cấp **KafkaTransactionManager** để quản lý Kafka producer transaction qua Spring transaction abstraction. Với ứng dụng có bean transaction manager phù hợp, service có thể dùng **@Transactional**:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class KafkaOnlyPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public KafkaOnlyPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(String orderId) {
        kafkaTemplate.send(
                "inventory.events",
                orderId,
                "reserved"
        );

        kafkaTemplate.send(
                "billing.events",
                orderId,
                "requested"
        );
    }
}
~~~

Tên **kafkaTransactionManager** trong annotation phải trùng bean transaction manager thực tế. Nếu cùng application có JpaTransactionManager hoặc DataSourceTransactionManager, đặt rõ tên giúp tránh chọn sai transaction manager theo mặc định.

Có thể khai báo manager tường minh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTransactionManager;
import org.springframework.kafka.core.ProducerFactory;

@Bean
KafkaTransactionManager<String, String> kafkaTransactionManager(
        ProducerFactory<String, String> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Trong Spring Boot, chỉ cần tự khai báo nếu auto-configuration không tạo manager phù hợp hoặc muốn custom setup. Không tạo manager thứ hai cùng vai trò mà không hiểu bean selection.

**Self-invocation:** lời gọi nội bộ giữa hai method trong cùng bean có thể không đi qua Spring transaction proxy. Để @Transactional có hiệu lực, cần bảo đảm caller gọi qua Spring proxy hoặc dùng TransactionTemplate/biện pháp khác phù hợp.

## 11. Listener container transaction và commit sau khi xử lý

Trong mô hình **consume → process → produce**, listener container có thể tự quản lý Kafka transaction:

1. Container poll input records.
2. Container bắt đầu Kafka transaction cho đơn vị xử lý tương ứng.
3. Container gọi @KafkaListener.
4. Listener publish output qua KafkaTemplate transactional tương thích.
5. Nếu listener hoàn tất thành công, container đưa input offsets vào Kafka transaction.
6. Container commit transaction.
7. Nếu listener lỗi, transaction abort và cơ chế after-rollback điều phối redelivery/recovery.

Spring Kafka có API để gắn Kafka-aware transaction manager vào ContainerProperties. Trong các phiên bản hỗ trợ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
transactionalListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);

    return factory;
}
~~~

Đây là ví dụ hướng dẫn API theo thế hệ Spring Kafka có **setKafkaAwareTransactionManager**. Ở phiên bản cũ có thể dùng method khác, ví dụ **setTransactionManager**; hãy đối chiếu phiên bản đang dùng. Generic types thực tế của ProducerFactory/KafkaTemplate phải tương thích với output cần publish, không nhất thiết giống kiểu value của consumer.

Ví dụ listener:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-projector",
    containerFactory = "transactionalListenerFactory"
)
public void onOrder(OrderEvent event) {

    var projection = transform(event);

    kafkaTemplate.send(
            "orders.projected",
            event.orderId(),
            projection
    );
}
~~~

Container transaction bao quanh listener. Nếu method ném exception, nó phải đi ra ngoài để container nhận được tín hiệu rollback. Không nên bắt và bỏ qua exception khiến container commit Kafka transaction như một lần xử lý thành công trong khi nghiệp vụ thật ra thất bại.

Khi đã cấu hình transactional listener container, thường không cần thêm @Transactional Kafka trên chính listener để mở một transaction Kafka độc lập khác. Cần hiểu manager và transaction synchronization trước khi kết hợp nhiều annotation.

## 12. Phạm vi transaction của record và batch listener

Transaction boundary phụ thuộc container configuration và loại listener.

- **Record listener:** container gọi method theo record, nhưng phạm vi transaction có thể bao gồm các record từ poll tùy container semantics/version. Không mặc định một transaction tương đương đúng một record trong mọi cấu hình.
- **Batch listener:** một lần invocation có thể xử lý nhiều record trong một batch; lỗi có thể làm transaction của phần batch đang xử lý rollback.
- **subBatchPerPartition:** một số cấu hình cho phép chia batch thành các sub-batch theo partition để có ranh giới xử lý/transaction theo partition.
- **Concurrency:** mỗi consumer thread/container con có transaction context và producer lifecycle riêng; transactional IDs không được va chạm.

Không thiết kế recovery dựa trên giả định mỗi record được commit riêng nếu container đang commit theo poll hoặc batch. Xác định phạm vi transaction thực tế từ version, listener type, AckMode và cấu hình container.

## 13. Visibility: read_committed và read_uncommitted

Kafka consumer có cấu hình **isolation.level**:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
~~~

Với **read_committed**, consumer không trả về những record được ghi trong transaction đã abort hoặc đang mở, nhưng vẫn đọc record không giao dịch như bình thường. Với **read_uncommitted**, consumer có thể thấy cả record thuộc aborted/uncommitted transaction trước khi transaction hoàn tất, vì thế không thể dựa vào commit marker để lọc chúng.

Ví dụ:

~~~text
T0: Producer bắt đầu transaction T1.
T1: Producer gửi record A.
T2: Producer gửi record B.
T3: Transaction vẫn mở.
T4: Producer commit transaction T1.
~~~

Consumer read_committed không nhận A và B trước khi transaction commit ở T4. Consumer read_uncommitted có thể nhìn thấy record đã ghi trước T4, tùy thời điểm fetch và log availability.

### Last Stable Offset (LSO)

Đối với read_committed, Kafka xác định **last stable offset** để tránh trả record vượt qua transaction đang mở chưa quyết định. Một transaction mở lâu có thể làm read_committed consumer chưa đọc được cả những record phía sau trên cùng partition, dù chúng thuộc producer khác.

Vì vậy, **open transaction lâu** có thể gây consumer lag hoặc apparent stall. Không nên chỉ nhìn producer send success để kết luận consumer downstream đã thấy record.

## 14. Commit marker, abort marker và broker state

Kafka transaction coordinator quản lý trạng thái giao dịch, còn partition logs ghi các record và control markers cần thiết để consumer hiểu transaction outcome.

Một transaction có thể gửi record tới nhiều partitions hoặc topics. Kafka tổ chức commit/abort decision với protocol của transaction coordinator để đảm bảo read_committed consumers quan sát nhất quán.

Không nhầm **transaction committed** với **record đã được xử lý bởi downstream business listener**. Commit chỉ làm record sẵn sàng cho consumer hợp lệ; downstream vẫn có thể chậm, lỗi deserialize hoặc bị backlog.

Một record được publish vào log có thể chiếm disk/network trước khi transaction commit. Abort không phải thao tác xóa bytes lập tức khỏi log; aborted records được read_committed consumers bỏ qua dựa trên metadata và transaction markers.

## 15. Commit thành công, commit thất bại và outcome không chắc chắn

Khi gọi commitTransaction, một số trường hợp:

| Trường hợp | Điều biết được | Hướng xử lý |
|---|---|---|
| Commit thành công | Transaction đã được coordinator commit theo client contract | Có thể bắt đầu transaction kế tiếp |
| Lỗi trước khi commit bắt đầu | Chưa gọi commit; transaction có thể abort nếu producer còn hợp lệ | Abort theo loại exception; giữ đủ log |
| Producer bị fenced | Producer mất quyền dùng transactional ID | Đóng producer, sửa ownership/ID, không tiếp tục dùng |
| Lỗi transaction timeout | Transaction có thể đã hết hạn/abort | Xem error type và trạng thái coordinator |
| Network timeout khi commit | Có thể chưa xác định chắc chắn outcome ở phía ứng dụng | Không tự kết luận đã abort; xử lý thận trọng và dựa vào idempotency |
| Lỗi fatal producer state | Producer có thể không thể tiếp tục | Đóng producer và khởi tạo lại theo policy |

**Outcome không chắc chắn** là tình huống đặc biệt cần thiết kế vận hành. Nếu response commit bị mất do network nhưng broker đã commit, việc phát lại side effect bên ngoài có thể gây duplicate. Nếu broker chưa commit, dữ liệu output của transaction sẽ không visible với read_committed consumers và input offset chưa tiến theo transaction.

Hãy tránh viết logic “catch mọi exception từ commit, gọi abort, gửi lại toàn bộ output vô điều kiện” mà không xét loại exception. Tùy trạng thái, client có thể không cho abort hoặc commit đã thành công nhưng response chưa được nhận.

Ứng dụng nên sử dụng transactional Kafka APIs của framework, error classification, producer lifecycle management và idempotent business identifiers để phục hồi an toàn khi không thể biết outcome ngay lập tức.

## 16. Producer fencing và transactional.id

Kafka sử dụng **transactional.id** và producer epoch để bảo vệ khỏi zombie producer. Khi producer mới có cùng transactional.id được khởi tạo, producer cũ có thể bị fence. Nếu producer cũ cố send hoặc commit, nó có thể gặp **ProducerFencedException**.

Ví dụ deployment có hai replicas:

~~~text
Replica A: transactional.id = orders-worker-0
Replica B: transactional.id = orders-worker-0
~~~

Nếu hai replica này thật sự cùng hoạt động, chúng có thể liên tục fence nhau. Cấu hình đó không an toàn nếu không phải một cơ chế takeover được kiểm soát.

Một cách tiếp cận:

~~~text
Replica A: transaction-id-prefix = orders-worker-a-
Replica B: transaction-id-prefix = orders-worker-b-
~~~

Spring Kafka sẽ tạo transactional IDs trong namespace riêng của từng instance. Với hệ thống có nhiều pod, suffix/prefix nên được xác định từ identity triển khai hoặc cơ chế phân phối ID được quản lý, tránh trùng trong lúc rolling update.

Cần phân biệt **fencing có chủ đích** khi instance mới tiếp quản một logical identity với **fencing do config lỗi**. Nếu log thấy ProducerFencedException liên tục sau scale-out, trước tiên kiểm tra prefix trùng, số producer cache và concurrent ownership.

## 17. Transaction timeout và max.poll.interval.ms

Kafka producer có **transaction.timeout.ms**. Broker cũng có giới hạn tối đa cho transaction timeout. Nếu transaction mở quá lâu, coordinator có thể tự abort transaction hoặc từ chối cấu hình vượt ngưỡng.

Consumer có **max.poll.interval.ms** để giới hạn khoảng thời gian giữa các poll theo group management. Nếu listener giữ luồng xử lý quá lâu, consumer có thể bị xem là không còn tham gia group hợp lệ và partition bị chuyển cho consumer khác.

Các setting này liên quan nhưng khác nhau:

| Cấu hình | Phạm vi | Tác động |
|---|---|---|
| transaction.timeout.ms | Kafka transactional producer | Giới hạn thời gian một transaction được mở |
| transaction.max.timeout.ms | Broker | Giới hạn timeout transaction do broker cho phép |
| max.poll.interval.ms | Kafka consumer | Giới hạn thời gian giữa poll calls |
| max.poll.records | Consumer | Giới hạn record trả mỗi poll, gián tiếp ảnh hưởng thời gian xử lý |
| delivery.timeout.ms | Producer | Giới hạn thời gian hoàn tất send |
| request.timeout.ms | Client request | Thời gian đợi phản hồi một request |

Một transaction quá dài có thể vừa timeout ở producer vừa khiến consumer bị rebalance. Nếu producer commit offset cho group metadata đã hết hiệu lực, transaction có thể thất bại hoặc bị fence theo cơ chế nhóm.

Không dùng transaction để bao bọc những thao tác network chậm hoặc chờ thủ công trong nhiều phút nếu có thể thiết kế khác. Giảm batch size, rút ngắn việc xử lý, dùng outbox hoặc tách workflow khi cần.

## 18. Không nuốt exception trong listener transaction

Ví dụ sai:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "transactionalListenerFactory"
)
public void handle(OrderEvent event) {
    try {
        orderService.apply(event);
    } catch (RuntimeException ex) {
        log.error("Order processing failed", ex);
        // Trả về bình thường: container có thể commit transaction.
    }
}
~~~

Nếu exception bị nuốt, listener method kết thúc bình thường. Container có thể cho rằng công việc thành công, thêm offsets và commit Kafka transaction. Điều này gây mất cơ hội redelivery theo Kafka ngay cả khi nghiệp vụ chưa được hoàn tất.

Cách xử lý cần thiết là **ném lỗi ra ngoài** để transaction rollback và để after-rollback recovery quyết định bước tiếp theo:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "transactionalListenerFactory"
)
public void handle(OrderEvent event) {
    orderService.apply(event);
}
~~~

Nếu một lỗi là expected domain event và nghiệp vụ muốn xác nhận offset mà không retry, hãy mô hình hóa nó như một kết quả xử lý rõ ràng hoặc publish event thất bại/compensation thích hợp trong transaction, thay vì âm thầm nuốt lỗi.

## 19. DefaultErrorHandler và AfterRollbackProcessor

Với listener container **không có Kafka transaction**, Spring Kafka thường dùng **DefaultErrorHandler** để quyết định retry và recovery khi listener ném exception.

Với listener container **đang dùng Kafka transaction**, khi listener lỗi và transaction rollback, đường phục hồi thường đi qua **AfterRollbackProcessor** (ví dụ DefaultAfterRollbackProcessor) để seek/redeliver hoặc recover record. Việc sử dụng DefaultErrorHandler không thay thế trực tiếp transaction rollback semantics.

Phân biệt:

| Thành phần | Dùng trong bối cảnh |
|---|---|
| DefaultErrorHandler | Xử lý lỗi listener trong container thông thường, retry/backoff/recovery |
| AfterRollbackProcessor | Xử lý hậu quả sau rollback transaction trong transactional listener container |
| DeadLetterPublishingRecoverer | Publish record lỗi đến DLT theo policy |
| KafkaTransactionManager | Quản lý Kafka producer transaction |
| KafkaTemplate | Gửi record trong transaction được liên kết |
| KafkaListener container | Điều phối poll, listener invocation, offsets và transaction |

Nếu muốn gửi record lỗi sang DLT và commit offset recovered theo một Kafka transaction, cần cấu hình processor và transaction manager tương thích với phiên bản Spring Kafka. Ví dụ các option recovery transaction và commit recovered offsets phụ thuộc constructor và version. Không mặc định một DefaultErrorHandler được gắn vào transactional factory sẽ thực thi recovery đúng như container không giao dịch.

## 20. Kafka transaction không bao trùm database tự động

Một ngộ nhận nguy hiểm: nếu listener được cấu hình Kafka transaction và đồng thời có @Transactional của JPA, thì **Kafka records và database rows sẽ commit nguyên tử**. Thực tế đây là **hai transaction manager khác nhau** trên hai hệ thống tài nguyên khác nhau.

Có thể đồng bộ thứ tự commit trong một số cấu hình Spring, ví dụ database-first rồi Kafka-second, nhưng không có một giao dịch phân tán nguyên tử mặc định. Tình huống:

1. Database transaction commit thành công.
2. Kafka transaction commit thất bại.
3. Database đã thay đổi nhưng output Kafka chưa visible.

Hoặc khi đổi thứ tự commit, Kafka commit thành công nhưng database commit sau đó thất bại. Các trạng thái không đồng nhất vẫn có thể xảy ra.

Vì thế cần:

- **Transactional outbox:** lưu thay đổi nghiệp vụ và outbox event trong cùng database transaction; worker riêng publish outbox sang Kafka, có idempotency.
- **Transactional inbox:** lưu event ID đã xử lý và side effect database trong cùng transaction để chịu redelivery.
- **Idempotency key:** bảo vệ external API và domain command khỏi lặp.
- **Reconciliation/compensation:** xử lý các trạng thái đã commit một phía nhưng không commit phía còn lại.

Kafka EOS bảo vệ luồng Kafka-to-Kafka, không biến REST call, email, database hay file system thành một phần của Kafka transaction.

## 21. Exactly-once semantics: điều được và chưa được bảo đảm

Kafka transaction và idempotent producer giúp đạt exactly-once processing semantics trong phạm vi Kafka theo điều kiện:

- Output records được gửi qua transactional producer.
- Input offsets được commit trong cùng Kafka transaction với output.
- Downstream consumer dùng **read_committed** nếu cần chỉ thấy committed transactional outputs.
- Transactional IDs được quản lý để chống zombie producer.
- Ứng dụng không có side effect bên ngoài Kafka vượt khỏi transaction mà không có cơ chế bổ sung.

Không nên phát biểu “mỗi @KafkaListener method chỉ chạy đúng một lần”. Listener vẫn có thể được gọi lại sau abort/restart/rebalance. Bảo đảm nằm ở **khả năng quan sát output Kafka đã commit và offset input**, không phải số lần CPU thực thi code.

Tương tự, nếu listener gọi một API thanh toán trước khi Kafka transaction commit, API có thể đã xử lý yêu cầu. Sau abort, listener được gọi lại và có thể gọi API lần nữa. Phải dùng idempotency key hoặc workflow khác.

## 22. Throughput và chi phí commit transaction

Kafka transactions có overhead hơn non-transactional publishing:

- Transaction coordinator phải quản lý trạng thái và các partition tham gia.
- Commit/abort cần giao thức, control records và network requests.
- Transactional producer có lifecycle và cache riêng.
- Downstream read_committed có thể phải chờ open transactions.
- Transaction timeout cần được điều chỉnh theo batch và processing duration.

Nếu commit sau mỗi record cực nhỏ, overhead có thể đáng kể. Nếu transaction quá lớn, commit ít hơn nhưng latency và rủi ro timeout/rebalance tăng.

Một số lựa chọn tối ưu:

1. Đo throughput và end-to-end latency thực tế.
2. Chọn batch size/transaction duration phù hợp.
3. Giảm call ngoài Kafka trong transaction.
4. Tránh producer transaction cache quá nhỏ so với concurrency.
5. Điều chỉnh number of partitions dựa trên capacity.
6. Theo dõi transaction commit/abort rate.
7. Nếu không cần EOS Kafka-to-Kafka, đánh giá liệu idempotent non-transactional producer cùng inbox/outbox có phù hợp hơn.

Không tắt transaction chỉ vì thấy overhead trước khi xác định business invariant cần bảo vệ.

## 23. Concurrency và producer cache

Trong Spring Kafka, transactional ProducerFactory có thể cache producer theo transactional ID suffix. Mỗi transaction đồng thời cần producer hợp lệ và unique ID trong phạm vi factory.

Khi listener concurrency tăng, số transaction đồng thời tăng. Nếu producer cache/suffix pool không đáp ứng, ứng dụng có thể gặp lỗi cấp producer transactional hoặc phải tạo thêm resource ngoài dự kiến, tùy phiên bản.

Cần tính:

- Số listener containers con trong một instance.
- Số publisher transaction ngoài listener đang chạy đồng thời.
- Số instance của ứng dụng.
- Transactional ID namespace trên mỗi instance.
- Producer cache capacity và suffix strategy.
- Broker connections và quota.

Theo dõi lỗi transactional ID, fencing, producer initialization và transaction commit latency sau mỗi lần scale-out. Nếu prefix trùng giữa các instance, cache lớn hơn không giải quyết vấn đề ownership.

## 24. Quan sát commit/abort trong production

Các metric/field quan trọng:

| Chỉ số | Ý nghĩa |
|---|---|
| Transaction commit rate | Số transaction commit thành công |
| Transaction abort rate | Số transaction bị hủy |
| Commit latency | Thời gian gọi commit/đợi coordinator |
| Transaction duration | Thời gian từ begin tới commit/abort |
| Transactional producer errors | Fencing, timeout, invalid state |
| Producer send failure rate | Lỗi xảy ra trước khi commit |
| Consumer lag | Đầu vào tồn đọng |
| Read-committed visibility lag | Thời gian record đầu ra xuất hiện với downstream |
| Rebalance count | Mất group membership ảnh hưởng offset transaction |
| AfterRollbackProcessor recovery | Retry/recovery sau transaction rollback |
| DLT publish failures | Recovery không lưu được record |

Structured log nên ghi:

~~~text
event=kafka_transaction_commit
service=order-projector
listener_id=ordersProjection
group_id=order-projector
input_topic=orders.created
input_partition=2
last_processed_offset=845
transactional_id_prefix=order-projector-pod-a-
outcome=committed
elapsed_ms=37
~~~

Không đưa transactional.id, event ID hoặc offset vào metric tags có cardinality cao nếu chúng thay đổi quá nhiều; các giá trị định danh chi tiết phù hợp với log/trace. Không log secret hoặc toàn bộ payload.

### Dấu hiệu cần alert

- Commit failures tăng sau deploy.
- ProducerFencedException xuất hiện hàng loạt khi scale-out.
- Abort rate tăng cùng với downstream error rate.
- Read_committed consumer lag tăng trong lúc open transactions kéo dài.
- Transaction timeout thường xuyên.
- DLT/recovery không tiến sau rollback.
- DB side effects và Kafka output không nhất quán.

## 25. Kiểm thử commit transaction

Để kiểm chứng semantics, dùng Kafka broker thật hoặc Testcontainers. Unit test của một phương thức gọi commitTransaction không chứng minh broker đã ghi commit marker hoặc read_committed consumer xử lý đúng.

Các kịch bản:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Hai sends trong cùng transaction rồi commit | read_committed consumer thấy cả hai |
| Send thành công nhưng abort | read_committed consumer không nhận records aborted |
| Consumer read_uncommitted | Có thể thấy records chưa commit hoặc đã abort |
| Input → output và offsets chung transaction | Output và offset cùng commit |
| Process chết trước commit | Output không được xem committed; input có thể xử lý lại |
| Process chết sau commit | Output visible và input offsets đã tiến trong Kafka |
| Producer mới dùng cùng transactional.id | Producer cũ bị fenced theo protocol |
| Timeout transaction | Transaction không commit thành công ngoài chính sách |
| Listener ném exception | Container rollback và after-rollback xử lý |
| Producer send failure | Không commit output một phần |
| Database commit trước Kafka commit thất bại | Phát hiện inconsistency và kiểm chứng inbox/outbox |
| Rebalance lúc xử lý | Offset/group metadata và rollback an toàn |

### Ví dụ kiểm chứng read_committed

Tạo transactional producer và hai consumers với cùng topic test nhưng group ID khác nhau:

~~~java
consumerProperties.put(
        ConsumerConfig.ISOLATION_LEVEL_CONFIG,
        "read_committed"
);
~~~

1. Begin transaction.
2. Send record A và B.
3. Chờ send futures hoàn tất.
4. Poll read_committed consumer và xác nhận không nhận A/B trước khi commit.
5. Commit transaction.
6. Poll tiếp với timeout đủ và xác nhận nhận cả A/B.
7. Lặp lại với transaction khác nhưng abort; xác nhận read_committed không trả record aborted.
8. Dùng read_uncommitted consumer để đối chiếu khi cần.

Kiểm thử không nên dựa vào Thread.sleep cố định. Dùng assertion polling có timeout và consumer group riêng để tránh ảnh hưởng từ committed offsets của lần chạy test trước.

## 26. Runbook khi commit transaction thất bại

Khi log có transaction commit failure:

1. Xác định service, instance, listener container, transactional.id/prefix và transaction manager.
2. Lấy exception class, cause chain và thời điểm commit.
3. Phân biệt lỗi send, lỗi add offsets, lỗi commit hoặc lỗi abort.
4. Kiểm tra broker coordinator, network, authorization và topic availability.
5. Nếu ProducerFencedException, xác định producer khác có cùng transactional.id đang chạy hay không.
6. Kiểm tra rolling deploy, scale-out và cách đặt transaction-id-prefix.
7. Đối chiếu transaction.timeout.ms, thời gian xử lý listener và max.poll.interval.ms.
8. Kiểm tra consumer group rebalance và offset metadata khi sendOffsetsToTransaction.
9. Nếu commit outcome không chắc chắn, không tự replay side effect ngoài Kafka trước khi xác định/idempotently reconcile.
10. Kiểm tra consumer read_committed đã thấy output hay chưa và input committed offsets.
11. Kiểm tra AfterRollbackProcessor, recovery/DLT và transaction producer lifecycle.
12. Khắc phục nguyên nhân rồi triển khai kiểm soát, theo dõi commit/abort rate và lag.
13. Nếu có database, kiểm tra tính nhất quán business state và chạy reconciliation theo runbook.
14. Ghi lại mức độ ảnh hưởng, số record phải replay và biện pháp ngăn tái diễn.

Khi một instance bị fenced, không cố tiếp tục commit bằng producer đã mất quyền. Đóng producer, xử lý ownership của transactional ID và để framework tạo producer mới theo chính sách thích hợp.

## 27. Những lỗi triển khai thường gặp

**Nhầm send thành commit.** Send hoàn tất không có nghĩa transaction committed; read_committed consumer chưa chắc thấy record.

**Nhầm flush thành commit.** Flush chỉ chờ producer sends; không ghi transaction commit marker.

**Chỉ dùng @Transactional mà chọn sai manager.** Với ứng dụng có nhiều transaction managers, phải chỉ rõ KafkaTransactionManager khi cần Kafka transaction.

**Listener nuốt exception.** Container có thể commit transaction dù nghiệp vụ thất bại.

**Không đưa offsets vào transaction.** Nếu commit input offset riêng, output và checkpoint không còn atomic trong Kafka.

**Dùng cùng transactional.id cho nhiều live producers.** Các instance fence lẫn nhau khi concurrent.

**Producer transaction mở quá lâu.** Có thể timeout, làm read_committed consumers bị chặn sau Last Stable Offset và tăng lag.

**Tự retry commit khi outcome không chắc chắn.** Có thể gây trạng thái khó đoán hoặc side effect lặp; cần dựa trên Kafka producer protocol và idempotency.

**Cho rằng Kafka transaction bao gồm database.** Không có distributed atomicity mặc định; dùng inbox/outbox.

**Consumer downstream dùng read_uncommitted rồi kỳ vọng không thấy record aborted.** Phải cấu hình read_committed cho yêu cầu này.

**Dùng DefaultErrorHandler như đường rollback duy nhất trong transactional listener.** Cần hiểu AfterRollbackProcessor và transaction-aware recovery.

**Tăng concurrency không tính transactional producer resources.** Có thể thiếu producer cache/suffix hoặc tăng fencing nếu namespace trùng.

**Không test crash ở ranh giới commit.** Happy path không đủ chứng minh recovery và EOS behavior.

## 28. Checklist trước production

**Producer và transaction manager**

- [ ] Transactional producer có prefix/ID không va chạm giữa các instances đồng thời.
- [ ] Đã xác nhận KafkaTransactionManager và KafkaTemplate dùng cùng transactional ProducerFactory phù hợp.
- [ ] Producer serializers, ACL và broker compatibility đúng.
- [ ] Transaction timeout phù hợp với thời gian xử lý.
- [ ] Có monitoring commit failures, aborts, fencing và send errors.

**Consumer và listener container**

- [ ] Consumer enable.auto.commit=false khi container quản lý offsets.
- [ ] Nếu cần Kafka-to-Kafka EOS, input offsets được gửi vào cùng transaction với outputs.
- [ ] Downstream consumer yêu cầu committed-only dùng isolation.level=read_committed.
- [ ] Listener không nuốt exception cần rollback.
- [ ] AfterRollbackProcessor/recovery được cấu hình phù hợp.
- [ ] Đã tính concurrency, producer cache, rebalance và max.poll.interval.ms.

**Nghiệp vụ**

- [ ] Không tuyên bố Kafka transaction bao trùm database hoặc API ngoài Kafka.
- [ ] External side effects có idempotency keys nếu có thể bị gọi lại.
- [ ] Dùng inbox/outbox hoặc reconciliation khi cần consistency xuyên hệ thống.
- [ ] Có chính sách DLT và replay với event ID ổn định.
- [ ] Transaction scope được chọn theo throughput và latency yêu cầu.

**Kiểm thử và vận hành**

- [ ] Có integration test commit/abort với read_committed consumer.
- [ ] Có test process crash trước và sau commit.
- [ ] Có test producer fencing và transaction timeout.
- [ ] Có test listener rollback/recovery và offset tiến đúng.
- [ ] Có runbook cho commit outcome không chắc chắn.
- [ ] Dashboard có transaction duration, commit/abort, lag và DLT.

## 29. Tóm lược nguyên tắc

**Commit transaction** là ranh giới khiến các Kafka records trong transaction được xem là committed và, nếu dùng sendOffsetsToTransaction, khiến **input consumer offsets** được commit cùng output records. Trong Spring Kafka, KafkaTransactionManager, KafkaTemplate và listener container giúp quản lý begin/commit/abort thay vì ứng dụng phải tự viết đầy đủ giao thức transaction.

Thiết kế cần dựa trên một số phân biệt cốt lõi: send khác commit; flush khác commit; commit offset thông thường khác gửi offset vào transaction; read_committed khác read_uncommitted; Kafka exactly-once khác tính nguyên tử với database/API ngoài Kafka. Khi đã quản lý transactional IDs, producer fencing, timeouts, rollback, idempotency và quan sát commit outcome, hệ thống có thể triển khai Kafka-to-Kafka processing nhất quán và phục hồi an toàn trước restart hoặc rebalance.

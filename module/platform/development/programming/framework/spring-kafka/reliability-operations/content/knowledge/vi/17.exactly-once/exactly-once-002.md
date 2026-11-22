# EOSMode.V2

**EOSMode.V2** là chế độ **Exactly Once Semantics (EOS)** trong Spring Kafka dùng cơ chế transaction của Kafka để phối hợp việc **ghi các record đầu ra** và **commit offset của các record đầu vào** trong một Kafka transaction. Điểm khác biệt quan trọng của V2 so với cơ chế cũ là khả năng broker dựa trên **consumer group metadata** trong thao tác gửi offset vào transaction để hỗ trợ phát hiện và fencing consumer/producer không còn quyền xử lý partition, thay vì phụ thuộc vào chiến lược tạo transactional producer riêng cho từng group/topic/partition như trước.

EOSMode.V2 xuất hiện trong quá trình chuyển đổi các phiên bản Spring Kafka 2.x sang cơ chế transaction mới hơn. Với Spring Kafka 3.x, **V2 là chế độ EOS được hỗ trợ**; mã nguồn mới thường không cần khai báo enum EOSMode để lựa chọn V2. Do đó, hiểu **EOSMode.V2** quan trọng hơn việc thuộc một dòng setter cụ thể: cần xác định transaction manager, transactional ProducerFactory, consumer container, offset-in-transaction, broker compatibility và cấu hình downstream.

Bài viết đi từ semantics và API đến triển khai, lỗi thường gặp, kiểm chứng bằng integration test và vận hành production. Phạm vi **exactly once** được định nghĩa cẩn thận: Kafka có thể bảo đảm atomicity giữa output Kafka records và input Kafka offsets trong điều kiện cấu hình đúng; **nó không biến mọi side effect ở database, HTTP hoặc email thành exactly-once**.

## 1. Bài toán EOS giải quyết

Xét một ứng dụng đọc topic **orders.in**, chuẩn hóa dữ liệu rồi ghi topic **orders.out**:

~~~mermaid
flowchart LR
    I["orders.in"] --> C["Spring Kafka consumer"]
    C --> L["Transform OrderEvent"]
    L --> P["KafkaTemplate producer"]
    P --> O["orders.out"]
    C --> F["Commit input offset"]
~~~

Nếu bước gửi output và commit input offset là **hai thao tác độc lập**, có hai khoảng lỗi:

1. **Output được ghi, offset chưa commit**: process chết sau khi gửi output; khi restart, cùng input có thể được đọc lại và output trùng.
2. **Offset được commit, output chưa ghi**: input được coi là đã xử lý nhưng record đầu ra bị mất.

Ví dụ partition 0 của orders.in có offset 200:

~~~text
Không có transaction phối hợp:

consume orders.in-0@200
  -> send orders.out: event X       [THÀNH CÔNG]
  -> process bị kill
  -> input offset vẫn là 200
  -> restart
  -> consume lại orders.in-0@200
  -> send orders.out: event X       [CÓ THỂ TRÙNG]
~~~

Kafka EOS cho mô hình consume-transform-produce cho phép **output record và consumer offset** được commit cùng Kafka transaction. Nếu transaction abort, downstream dùng read_committed sẽ không nhìn thấy output của transaction đó và input offset không được commit thông qua transaction đó. Khi input được xử lý lại, một transaction mới có thể thành công.

**Lưu ý:** listener có thể được gọi nhiều lần; EOS ở đây không hứa Java method chỉ chạy một lần. Nó cung cấp semantics cho các bản ghi Kafka committed và offset đã commit, không loại bỏ mọi duplicate computation.

## 2. EOSMode.V2 là gì?

Trong lịch sử Spring Kafka có các cách tạo/định danh transactional producer khác nhau cho listener container.

- Cơ chế cũ thường được nhắc tới dưới tên **EOSMode.V1**, gắn chặt hơn với nhận diện theo consumer group/topic/partition để hỗ trợ fencing.
- **EOSMode.V2** sử dụng khả năng của Kafka mới hơn khi gửi **consumer group metadata** trong bước thêm consumer offsets vào transaction. Broker có thông tin để đánh giá tính hợp lệ của consumer member/generation trong giao thức group coordination và fencing phù hợp.
- Với **Spring Kafka 3.x**, tài liệu và cấu hình mới dùng V2 như cách vận hành mặc định của transactional listener; không nên sao chép setter chọn EOSMode từ ví dụ dành riêng cho bản 2.x mà chưa đối chiếu API hiện có.

Một số tài liệu dùng cụm **fetch-offset-request** khi mô tả tiến trình chuyển đổi cơ chế fencing. Điều quan trọng về vận hành là: **V2 không cần chiến lược transactional.id riêng cố định cho từng group/topic/partition**, nhưng **vẫn cần transactional.id duy nhất giữa các transactional producer đang đồng thời hoạt động**.

### 2.1 V2 không phải “exactly once phiên bản thứ hai” cho mọi hệ thống

Tên V2 không có nghĩa tự động nâng cấp mọi ứng dụng Kafka từ at-least-once sang exactly-once. Một consumer có thể chạy trên Spring Kafka 3.x nhưng:

- ProducerFactory không transaction capable.
- KafkaTemplate gửi ngoài transaction.
- Listener container không mở Kafka transaction.
- Consumer tự commit offset tách khỏi output transaction.
- Downstream đọc read_uncommitted.
- Business service gọi một HTTP API ngoài Kafka với side effect không idempotent.

Trong các trường hợp đó, nhãn V2 không tự sửa ranh giới giao dịch. V2 là một phần của hạ tầng phối hợp, không phải một annotation bảo đảm tất cả tác vụ chỉ xảy ra một lần.

### 2.2 Bảng phân biệt

| Câu hỏi | EOSMode.V2 có giải quyết? | Điều kiện hoặc giới hạn |
|---|---|---|
| Atomicity giữa các Kafka output records cùng transaction | Có | Producer transaction và commit/abort đúng |
| Commit Kafka consumer offsets cùng output transaction | Có | Listener container phối hợp offsets vào transaction |
| Fencing phù hợp với consumer group metadata | Có | Broker/client/Spring Kafka hỗ trợ V2 |
| Không hiển thị output của transaction abort | Có cho read_committed consumer | Consumer phải đặt isolation.level=read_committed |
| Đảm bảo listener method chỉ được gọi một lần | Không | Abort/restart có thể làm listener chạy lại |
| Atomicity giữa Kafka và SQL database | Không tự động | Cần thiết kế transaction/outbox riêng |
| Ngăn gửi hai business event trùng từ upstream | Không | Cần idempotency/deduplication |
| Bỏ qua nhu cầu transactional.id | Không | Producer vẫn phải có transactional.id đúng |

## 3. Kafka transaction vận hành như thế nào?

Một Kafka transactional producer có một **transactional.id** và thực hiện transaction lifecycle:

1. Khởi tạo transactional producer.
2. Bắt đầu transaction.
3. Gửi một hoặc nhiều Kafka records.
4. Nếu có consume-transform-produce, gửi input offsets cùng consumer group metadata vào transaction.
5. Commit transaction khi toàn bộ công việc đủ điều kiện thành công; hoặc abort khi có lỗi.

~~~mermaid
sequenceDiagram
    participant K as Consumer (orders.in)
    participant L as Spring Kafka listener
    participant P as Transactional producer
    participant B as Kafka brokers
    participant R as read_committed consumer
    K->>L: Input record
    L->>P: Gửi output record
    P->>B: Write transactional output
    L-->>K: Listener thành công
    K->>P: Send consumed offsets + group metadata
    P->>B: Add offsets to transaction
    P->>B: Commit transaction
    B-->>R: Output đủ điều kiện đọc
~~~

Sơ đồ lược bớt các bước internal của Kafka client, coordinator và Spring container. Điểm cốt lõi: **output và input offset phải đi cùng giao dịch**. Nếu output commit còn input offset commit ở một cơ chế riêng, EOS của chuỗi consume-transform-produce không được thiết lập.

### 3.1 Hai thao tác cần nằm cùng Kafka transaction

Ví dụ concept:

~~~text
Transaction TX-42:
  produce orders.out-1@500
  produce orders.audit-0@207
  commit consumed offset orders.in-0 -> 201

COMMIT TX-42
~~~

Sau commit, consumer group của input có committed offset tiến tới 201 và các output trong transaction được xem là committed. Nếu TX-42 abort, input offset vẫn cần xử lý lại và downstream read_committed không nhận output của transaction đó.

### 3.2 Bảo đảm “đầu ra committed” khác “listener chạy đúng một lần”

Nếu listener thực hiện:

~~~java
analyticsCounter.increment();
kafkaTemplate.send("orders.out", event.orderId(), serialize(event));
~~~

và Kafka transaction abort, record Kafka chưa committed nhưng bộ đếm trong bộ nhớ đã tăng. Nếu counter là external side effect bền vững hoặc metric nghiệp vụ, chạy lại listener có thể tạo kết quả lặp.

Vì vậy, phải phân biệt:

- **Exactly-once Kafka processing effect**: các record Kafka committed và offset Kafka được phối hợp theo transaction.
- **Exactly-once business side effect**: database, HTTP, email, cache… cần cơ chế khác.

## 4. Điều kiện nền tảng để dùng V2

Trước khi triển khai, cần xác định đồng thời:

- **Phiên bản Spring Kafka** có hỗ trợ cơ chế EOS V2.
- **Kafka brokers** hỗ trợ API/giao thức mà V2 dùng (thông thường yêu cầu broker Kafka 2.5 trở lên đối với V2).
- **Kafka clients** tương thích broker, transaction và consumer group metadata.
- **Transaction-capable ProducerFactory** có transactionIdPrefix đúng.
- **KafkaTransactionManager** hoặc Kafka-aware transaction manager tương ứng với phiên bản.
- **Listener container** thực sự bật transaction cho input listener.
- **KafkaTemplate** dùng cùng transactional producer infrastructure.
- **enable.auto.commit=false** để container/transaction điều phối offsets.
- **read_committed** ở consumer cần chỉ thấy committed transactional output.
- **Topic replication/ISR và broker transaction configuration** phù hợp production.

V2 không yêu cầu một biến cấu hình duy nhất để “bật EOS cho mọi listener”. Một project có nhiều ConsumerFactory/KafkaTemplate/container factory có thể có cả transactional flow và non-transactional flow.

### 4.1 Tính tương thích theo phiên bản

| Bối cảnh | Cách hiểu |
|---|---|
| Spring Kafka 2.x có EOSMode enum | Có thể cần cấu hình chế độ V2 cụ thể trên container, phụ thuộc minor version |
| Spring Kafka 3.x | V2 là cơ chế được hỗ trợ; tránh dùng code chọn V1/V2 từ ví dụ cũ |
| Broker quá cũ | Không đáp ứng yêu cầu giao thức V2; cần nâng cấp hoặc xem giải pháp version tương ứng |
| Spring Kafka, client và broker hỗn hợp | Đọc compatibility matrix của tổ hợp phiên bản được triển khai |

**Không nâng cấp Spring Kafka riêng lẻ rồi mặc định broker đã đáp ứng.** Một số lỗi chỉ xuất hiện khi transaction bắt đầu, gửi offsets hoặc commit, không nhất thiết tại application startup.

## 5. Transactional ProducerFactory

Spring Kafka tạo producer qua **ProducerFactory**; triển khai thường dùng là DefaultKafkaProducerFactory. Để factory có thể tạo transactional producers, cần cấu hình **transaction ID prefix**.

Ví dụ Spring Boot YAML:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092

    producer:
      transaction-id-prefix: orders-transformer-instance-01-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      properties:
        acks: all
        enable.idempotence: true
        transaction.timeout.ms: 60000

    consumer:
      group-id: orders-transformer-prod
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      properties:
        isolation.level: read_committed
~~~

Cấu hình trên minh họa **một application instance**. Với deployment nhiều pod, mỗi instance đang hoạt động phải được cấp prefix không trùng nhau. Ví dụ instance-01 là placeholder về ý nghĩa, không phải giá trị chung có thể copy vào tất cả pod production.

### 5.1 transactionIdPrefix và group.id là hai danh tính khác nhau

- **group.id**: giống nhau giữa các consumer replicas thuộc cùng logical consumer group, để Kafka chia partition và duy trì group offsets.
- **transactionIdPrefix**: cần duy nhất giữa các producer factory instance đang hoạt động đồng thời, để tránh các transactional producers tranh chấp transactional.id.
- **client.id**: phục vụ logging, metrics và quota; không thay thế group.id hoặc transactional.id.

Ví dụ:

~~~text
Pod A:
  group.id = orders-transformer-prod
  transactionIdPrefix = orders-transformer-pod-a-

Pod B:
  group.id = orders-transformer-prod
  transactionIdPrefix = orders-transformer-pod-b-
~~~

Hai pod cùng group để chia input partitions; mỗi pod có prefix riêng để producer transactions không fencing lẫn nhau.

### 5.2 V2 giảm ràng buộc per-partition, không xóa producer fencing

Với V2, broker dùng consumer group metadata trong flow gửi offsets vào transaction để hỗ trợ kiểm soát ownership. Nhưng producer fencing dựa trên **transactional.id/epoch** vẫn tồn tại và cực kỳ quan trọng.

Nếu hai pod cố tạo transactional producer cùng transactional.id:

~~~text
Pod A transactional.id = orders-transformer-0
Pod B transactional.id = orders-transformer-0

Pod B khởi tạo producer epoch mới
=> producer cũ ở Pod A bị fenced
~~~

V2 không “cho phép dùng chung transactional.id ở nhiều pod”. Nó cho phép mô hình quản lý producer ít phụ thuộc việc gắn ID cứng với từng partition, nhưng tính duy nhất của producer identity vẫn phải được giữ.

### 5.3 Kiểm tra transaction-capable

Có thể kiểm tra sớm:

~~~java
@Component
public class TransactionalProducerGuard {

    public TransactionalProducerGuard(
            ProducerFactory<String, String> producerFactory) {

        if (!producerFactory.transactionCapable()) {
            throw new IllegalStateException(
                "EOS flow requires transactional ProducerFactory"
            );
        }
    }
}
~~~

Nếu có nhiều factory, cần inject đúng factory bằng qualifier. Trả về true chỉ chứng minh **capability**, không chứng minh listener container đã mở transaction hay offsets đã được commit trong transaction đó.

## 6. KafkaTemplate, KafkaTransactionManager và listener container

Một ứng dụng Spring Kafka transaction thường gồm:

~~~mermaid
flowchart TD
    P["ProducerFactory (transaction capable)"] --> KT["KafkaTemplate"]
    P --> TM["KafkaTransactionManager"]
    TM --> LC["Kafka listener container"]
    LC --> L["@KafkaListener"]
    L --> KT
    LC --> C["KafkaConsumer input offsets"]
    KT --> O["Kafka output records"]
    C --> TX["Cùng Kafka transaction"]
    O --> TX
~~~

Các thành phần cần kết nối đúng với nhau:

- KafkaTemplate gửi output bằng transactional producer.
- KafkaTransactionManager quản lý transaction context.
- Listener container khởi tạo transaction khi tiêu thụ input.
- Khi listener thành công, container đưa offsets tương ứng vào transaction và commit.
- Khi listener lỗi, container rollback/abort, rồi thực hiện recovery/redelivery theo transactional error handling.

### 6.1 Mẫu bean producer factory và manager

Ví dụ Java dùng một ProducerFactory:

~~~java
@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    ProducerFactory<String, String> transactionalProducerFactory() {

        Map<String, Object> props = new HashMap<>();

        props.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "kafka-1:9092,kafka-2:9092,kafka-3:9092"
        );
        props.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        props.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(
            ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
            true
        );

        var factory =
            new DefaultKafkaProducerFactory<String, String>(props);

        // Phải là prefix riêng cho instance này.
        factory.setTransactionIdPrefix(
            "orders-transformer-instance-01-"
        );

        return factory;
    }

    @Bean
    KafkaTemplate<String, String> transactionalKafkaTemplate(
            ProducerFactory<String, String> transactionalProducerFactory) {

        return new KafkaTemplate<>(transactionalProducerFactory);
    }

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> transactionalProducerFactory) {

        return new KafkaTransactionManager<>(
            transactionalProducerFactory
        );
    }
}
~~~

Với Spring Boot auto-configuration, không nhất thiết cần tự khai báo cả ba bean. Nếu dự án tự tạo bean, cần bảo đảm không tạo ra hai factory/manager không đồng bộ mà cùng tên logic.

### 6.2 Cấu hình listener container transaction theo Spring Kafka version

Với Spring Kafka 2.x, tài liệu của một số minor version dùng cách cấu hình minh họa:

~~~java
var factory =
    new ConcurrentKafkaListenerContainerFactory<String, String>();

factory.setConsumerFactory(consumerFactory);
factory.getContainerProperties()
       .setTransactionManager(kafkaTransactionManager);

// Dành cho các bản 2.x có lựa chọn EOSMode:
factory.getContainerProperties()
       .setEosMode(ContainerProperties.EOSMode.V2);
~~~

**Đây là đoạn minh họa API lịch sử, không phải code copy nguyên cho Spring Kafka 3.x.** Trong Spring Kafka 3.x, V2 là mô hình được hỗ trợ; không nên gọi setEosMode nếu API đã được loại bỏ. Một số bản hiện đại dùng API cấu hình Kafka-aware transaction manager khác, ví dụ setter tương ứng trên ContainerProperties.

Với Spring Kafka 3.x, nên làm theo ba bước:

1. Tạo KafkaTransactionManager từ transactional ProducerFactory.
2. Gắn manager vào **đúng** ConcurrentKafkaListenerContainerFactory theo API của phiên bản đang chạy.
3. Kiểm chứng bằng integration test rằng output records và consumed offsets thực sự commit/abort cùng transaction.

Không chỉ thấy @KafkaListener trong class có @Transactional rồi kết luận đã có container transaction. Nếu listener container chưa quản lý transaction đầu vào, input offset và output transaction có thể tách rời.

### 6.3 Listener transform đơn giản

~~~java
@Component
public class OrdersTransformer {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrdersTransformer(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        id = "orders-transformer",
        topics = "orders.in",
        groupId = "orders-transformer-prod",
        containerFactory = "transactionalListenerFactory"
    )
    public void transform(
            ConsumerRecord<String, String> input) {

        String output = input.value().trim().toUpperCase();

        kafkaTemplate.send(
            "orders.out",
            input.key(),
            output
        );
    }
}
~~~

Method này tập trung vào nghiệp vụ. **Exactly-once Kafka semantics phụ thuộc containerFactory** và transaction manager được cấu hình đúng, không phụ thuộc việc listener chỉ gọi send một lần.

## 7. Gửi consumed offsets vào transaction

Điểm mấu chốt của EOSMode.V2 là broker nhận **consumer group metadata** khi offsets được gửi vào transaction.

Trong Kafka client, dạng API liên quan là **sendOffsetsToTransaction(offsets, groupMetadata)**. Nó kết hợp:

- Map các topic-partition với offsets cần commit.
- ConsumerGroupMetadata mô tả consumer group context hiện tại.

~~~java
// Sơ đồ khái niệm bằng Kafka Java client thuần.
// Spring Kafka transactional listener container thực hiện
// phần phối hợp offsets thay cho application code.

Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
    new TopicPartition("orders.in", 0),
    new OffsetAndMetadata(201L)
);

producer.sendOffsetsToTransaction(
    offsets,
    consumer.groupMetadata()
);
~~~

**Không cần tự gọi đoạn API này bên trong @KafkaListener thông thường** nếu container đã được cấu hình transactional. Spring Kafka chịu trách nhiệm chuyển consumed offsets vào transaction tại đúng boundary.

### 7.1 Vì sao group metadata quan trọng?

Trong consumer group, partition assignment có thể thay đổi khi:

- Pod restart.
- Consumer mất heartbeat hoặc vượt poll interval.
- Group rebalance do tăng concurrency.
- Partition được chuyển sang member khác.

Consumer A có thể tưởng vẫn sở hữu partition trong khi group đã giao partition đó cho B. Nếu A tiếp tục commit offsets không hợp lệ, nó có nguy cơ làm trạng thái xử lý lạc hậu hoặc can thiệp vào tiến độ của member mới.

V2 tận dụng consumer group metadata trong transaction offset commit để broker có thêm thông tin liên quan tới membership/generation và thực hiện fencing theo protocol. Điều này đặc biệt quan trọng khi group assignment đổi trong lúc transaction đang thực hiện.

### 7.2 Offset commit trong transaction không phải “commit trước”

Ví dụ input record tại offset 200:

~~~text
Input: orders.in-0@200

Sau khi xử lý:
  output -> orders.out-1@500
  next input offset -> 201

Cả output và offset 201
được đưa vào cùng transaction.
~~~

Offset 201 là **vị trí tiếp theo cần đọc** sau record 200, không phải “đã xử lý offset 201”. Khi tự kiểm chứng trạng thái, cần hiểu semantics của committed offset trong Kafka.

### 7.3 Khi group rebalance giữa transaction

Nếu consumer mất quyền sở hữu partition giữa lúc xử lý, container/transaction có thể thất bại hoặc phải abort theo trạng thái group mới. Không nên cố ép commit bằng một đường offset commit khác để tránh exception.

Các bước vận hành đúng:

1. Ghi nhận lỗi transaction và group membership.
2. Để consumer/container thực hiện abort hoặc cleanup theo lifecycle framework.
3. Cho group rebalance hoàn tất.
4. Xử lý lại input từ committed offset hợp lệ.
5. Dựa vào Kafka transaction để không công bố output của transaction abort tới read_committed downstream.
6. Bảo vệ side effect ngoài Kafka bằng idempotency.

## 8. Đối chiếu V1 và V2 theo cách hiểu vận hành

| Khía cạnh | Cơ chế V1 cũ | EOSMode.V2 |
|---|---|---|
| Mục tiêu | EOS consume-transform-produce trong Kafka | Cùng mục tiêu |
| Cách hỗ trợ fencing consumer zombie | Gắn transactional identity chặt hơn với group/topic/partition | Tận dụng consumer group metadata khi gửi offsets vào transaction |
| Transactional producer identity | Phụ thuộc chiến lược ID của V1 | Prefix riêng instance và suffix quản lý bởi factory |
| Phù hợp multi-instance/concurrency | Phải tuân theo các ràng buộc của cơ chế cũ | Linh hoạt hơn về quản lý producer theo instance |
| Hỗ trợ framework mới | Chỉ gặp ở tài liệu/code cũ | Cơ chế EOS được hỗ trợ của Spring Kafka 3.x |
| Có thay đổi ranh giới EOS ngoài Kafka? | Không | Không |
| Cần broker compatibility | Có | Có, với yêu cầu giao thức mới hơn |

Không cần chuyển đổi dữ liệu business chỉ vì đổi enum từ V1 sang V2. Nhưng việc nâng cấp ứng dụng phải xem xét tính tương thích broker, cách tạo transactional.id, producer cache và hệ thống test. Những thay đổi về identity hoặc producer lifecycle có thể ảnh hưởng fencing và transaction throughput.

## 9. Producer fencing khác consumer group fencing

Có hai lớp “fencing” dễ bị nhập nhằng:

### 9.1 Transactional producer fencing

Kafka quản lý producer epoch theo transactional.id. Producer mới giành cùng transactional.id có thể làm producer cũ bị fenced.

~~~text
A dùng transactional.id X
B khởi tạo transactional.id X
A cố ghi/commit
=> A bị fenced
~~~

Đây là lý do transactionIdPrefix cần duy nhất giữa các instance đang chạy. Lỗi này có thể xuất hiện dù consumer group vẫn ổn định nếu hai transactional producers cùng dùng một ID.

### 9.2 Consumer group metadata trong V2

Khi sendOffsetsToTransaction dùng group metadata, broker có cơ sở nhận diện offset commit đến từ consumer group context hiện tại hay context đã lỗi thời. Nhờ đó cơ chế fencing liên quan ownership của consumer không còn cần được mã hóa chủ yếu qua transactional.id của từng group/topic/partition.

**Hai cơ chế bổ sung nhau**, không thay thế nhau:

- Producer epoch bảo vệ transactional producer identity.
- Group metadata hỗ trợ tính hợp lệ của input offset commit theo group ownership.

Nếu ứng dụng gặp ProducerFencedException, không thể kết luận ngay nguyên nhân là consumer rebalance. Cũng có thể do hai pod trùng transactional.id. Cần xem exception, transactional ID, producer lifecycle và group generation/assignment.

## 10. Consumer isolation.level và LSO

Transactional output không tự bảo đảm downstream consumer chỉ thấy committed records. Consumer đọc output cần cấu hình **isolation.level=read_committed** nếu yêu cầu bỏ qua aborted records.

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
~~~

Hai chế độ:

| isolation.level | Hành vi |
|---|---|
| read_uncommitted | Có thể trả về records thuộc transaction chưa commit hoặc đã abort |
| read_committed | Chỉ trả về transactional records đã commit và records non-transactional phù hợp, bỏ qua aborted records |

Khi một transaction đang mở trên partition, read_committed consumer có thể bị giới hạn bởi **Last Stable Offset (LSO)**. Record phía sau một transaction chưa ổn định có thể chưa được trả về ngay, kể cả khi broker đã nhận chúng.

### 10.1 Ví dụ về abort

~~~text
TX-1 gửi orders.out@100
TX-1 gửi orders.out@101
TX-1 abort

read_committed:
  không giao hai record trên như output hợp lệ

read_uncommitted:
  có thể nhìn thấy records của transaction đã abort
~~~

Nếu downstream consumer dùng read_uncommitted, phát biểu “output của transaction abort không ai thấy” là sai. Khi đánh giá EOS end-to-end cần xem cấu hình downstream.

### 10.2 Read_committed ở input có bắt buộc không?

Nếu input topic có transactional producers upstream và service chỉ muốn xử lý committed inputs, consumer đầu vào nên dùng read_committed.

Nếu input topic chỉ có producers non-transactional, read_committed vẫn có thể được dùng và sẽ đọc các records non-transactional bình thường.

Điểm cần phân biệt: read_committed ở **input** quyết định record nào được listener đọc; transaction ở **output** quyết định atomicity của việc ghi output và commit input offsets. Hai quyết định hỗ trợ nhau nhưng không đồng nhất.

## 11. AckMode, offset và container transaction

Với transactional listener container, việc commit offsets cần tuân theo Kafka transaction lifecycle. Container sẽ điều phối offsets theo semantics của record/batch listener và ack mode hỗ trợ ở phiên bản framework đang dùng.

Các nguyên tắc:

- **enable.auto.commit=false**: không để Kafka client tự động commit offsets ngoài transaction.
- **Không tự gọi consumer.commitSync/commitAsync** trong listener để “chắc chắn” khi container đã quản lý transaction.
- **Không tự mở một Kafka transaction khác** không liên quan rồi commit input offsets ngoài container mà không hiểu rõ lifecycle.
- **Không acknowledge sớm** nếu business processing chưa hoàn tất.
- **Không trả về từ listener trước khi công việc bắt buộc thực sự hoàn tất**, trừ khi framework và kiến trúc async được thiết kế rõ.

### 11.1 Record listener và batch listener

Trong record listener, mỗi invocation gắn với một record; container xử lý offsets theo policy của nó. Trong batch listener, một invocation có thể chứa nhiều records; transaction có thể bao phủ batch input và output tương ứng.

Ví dụ một batch có 100 records. Nếu listener xử lý record thứ 70 thất bại và transaction abort, các output Kafka trong transaction bị abort. Khi input chưa được commit, batch hoặc phần record liên quan có thể được giao lại theo transactional rollback/recovery policy.

Không tự giả định rằng DefaultErrorHandler của non-transactional listener là handler duy nhất cho transactional batch. Spring Kafka thường phối hợp **AfterRollbackProcessor** và các cơ chế recovery tương ứng cho transactional container.

### 11.2 Manual ack không đồng nghĩa exactly-once

Một listener manual ack vẫn có thể commit input offset sai thời điểm nếu ack trước output commit. Ngược lại, transactional container có thể phối hợp offset commit mà không cần listener tự gọi acknowledge().

Nếu mục tiêu là Kafka EOS, hãy để container thực hiện transactional offset commit theo API/framework được hỗ trợ, thay vì thêm commit thủ công trong nghiệp vụ.

## 12. Retry, rollback và AfterRollbackProcessor

Transaction không ngăn exception xảy ra. Nó giúp abort các Kafka output và offset của lần xử lý thất bại.

Ví dụ:

~~~text
consume input offset 700
  -> send output A
  -> call transformService
  -> throw IllegalStateException

Kafka transaction abort
  -> output A không visible cho read_committed
  -> input offset không được commit trong transaction
  -> input có thể được redeliver
~~~

Trong transactional listener, **AfterRollbackProcessor** có thể giúp xác định record cần seek/reprocess sau rollback, áp dụng BackOff hoặc recovery theo cấu hình. Cách dùng cụ thể khác với DefaultErrorHandler cho non-transactional listener.

### 12.1 Không nuốt exception

Nếu listener gặp lỗi nhưng bắt rồi log và return bình thường, container có thể coi transaction là thành công và commit output/offset:

~~~java
@KafkaListener(
    topics = "orders.in",
    containerFactory = "transactionalListenerFactory"
)
public void transform(String input) {
    try {
        service.process(input);
    }
    catch (Exception ex) {
        log.error("processing failed", ex);
        // Nếu return bình thường, container có thể commit.
    }
}
~~~

Nếu lỗi bắt buộc làm transaction abort, exception cần được propagage hoặc transaction được đánh dấu rollback theo API phù hợp.

### 12.2 Poison record và retry exhaustion

Nếu cùng record luôn thất bại vì dữ liệu không hợp lệ, transaction sẽ liên tục abort và input có thể bị redeliver. Không nên retry vô hạn.

Một recovery policy có thể:

1. Retry hữu hạn cho lỗi transient.
2. Sau khi exhausted, publish record lỗi sang DLT.
3. Xác định DLT publication có cần transaction riêng hay không.
4. Chỉ tiến input offset khi recovery được xem là hoàn tất theo policy.
5. Bảo toàn raw record và metadata để replay.

Trong Spring Kafka, transactional recovery có những khả năng như commit recovered offset trong một transaction mới theo cấu hình processor tương ứng. Cần kiểm tra API và semantics chính xác của phiên bản, thay vì sao chép cấu hình recoverer của non-transactional listener.

### 12.3 Kafka transaction không rollback database

Nếu listener ghi database thành công rồi lỗi trước Kafka commit:

~~~text
DB update: COMMIT
Kafka TX: ABORT
input: REDLIVER
DB update: có thể bị thực hiện lần nữa
~~~

Cần idempotency key, inbox/deduplication hoặc outbox. EOSMode.V2 không sửa khoảng lỗi ngoài Kafka này.

## 13. Transaction timeout và vòng đời producer

Kafka transactional producer phải kết thúc transaction trong timeout broker cho phép. Nếu một listener giữ transaction mở quá lâu vì database hoặc API chậm, coordinator có thể abort transaction.

Các tham số cần quan sát:

| Tham số | Ý nghĩa |
|---|---|
| transaction.timeout.ms | Timeout producer yêu cầu cho Kafka transaction |
| transaction.max.timeout.ms | Giới hạn tối đa phía broker |
| max.poll.interval.ms | Giới hạn thời gian giữa consumer polls trước nguy cơ mất assignment |
| request.timeout.ms | Timeout của request mạng riêng lẻ |
| delivery.timeout.ms | Giới hạn thời gian gửi producer records |
| acks | Mức ghi nhận từ broker cho producer send |
| min.insync.replicas | Ngưỡng replica ISR cần thiết cho producer durability theo policy |
| transactional.id.expiration.ms | Cơ chế expiration của transactional IDs không hoạt động |

Không nhầm transaction.timeout.ms với consumer retry backoff. Hai khoảng thời gian phục vụ hai mục đích khác nhau.

### 13.1 Đừng giữ transaction mở qua một workflow dài

Ví dụ một listener:

1. Bắt đầu Kafka transaction.
2. Gọi HTTP API không có timeout.
3. Chờ người dùng approve.
4. Đợi thêm một job hoàn tất.
5. Gửi output và commit.

Đây là mô hình không phù hợp cho Kafka transaction. Nên tách thành các bước với Kafka events/workflow state và transaction ngắn. Transaction Kafka phù hợp với nhóm thao tác Kafka cần commit/abort nhất quán trong khoảng thời gian có giới hạn.

### 13.2 Producer cache và maxAge

DefaultKafkaProducerFactory có thể cache transactional producers để tái sử dụng sau khi transaction kết thúc. Nếu producer nằm idle quá lâu, broker có thể hết hạn transactional.id, gây lỗi khi factory tái sử dụng producer cũ.

Một số phiên bản Spring Kafka hỗ trợ cấu hình **maxAge** để factory làm mới cached producer trước khi transactional.id hết hạn tại broker. Với service chạy theo đợt hoặc có khoảng idle dài, đây là yếu tố cần đánh giá.

V2 không loại bỏ nhu cầu quản lý producer cache, TTL hoặc transaction coordinator.

## 14. Rolling deployment, scale và concurrency

Một consumer group có thể có nhiều pod và mỗi pod chạy nhiều child consumer containers. Với V2:

- Các consumer trong cùng logical group vẫn phải dùng chung **group.id**.
- Mỗi application instance cần transactional ID prefix riêng.
- Các transactional producers được cấp suffix/cache trong phạm vi factory.
- Không đặt transactional ID theo từng record hoặc mỗi lần gọi listener.
- Phải chấp nhận group rebalance khi scale hoặc rolling deploy.
- Khi ownership thay đổi giữa lúc transaction chưa hoàn tất, transaction có thể abort/fencing thay vì commit.

### 14.1 Ví dụ 3 pod, concurrency 2

~~~text
Topic orders.in: 6 partitions
Consumer group: orders-transformer-prod

Pod A:
  2 child consumers
  tx prefix: orders-transformer-a-

Pod B:
  2 child consumers
  tx prefix: orders-transformer-b-

Pod C:
  2 child consumers
  tx prefix: orders-transformer-c-
~~~

Tổng cộng có sáu consumer members cho group, có thể phân phối sáu partitions. Số transactional producers được tạo/cache có thể phụ thuộc số giao dịch đồng thời và producer factory lifecycle, không nhất thiết lúc nào cũng đúng bằng số consumer members.

Nếu tăng concurrency từ 2 lên 4 trên cả ba pod, tổng consumer members có thể lên 12 trong khi topic chỉ có sáu partitions. Một số consumer idle, nhưng chi phí resource và rebalance vẫn tồn tại.

### 14.2 Tại sao group.id không được dùng trực tiếp làm prefix chung?

Một cấu hình sai:

~~~text
Pod A:
  group.id = orders-transformer-prod
  tx prefix = orders-transformer-prod-

Pod B:
  group.id = orders-transformer-prod
  tx prefix = orders-transformer-prod-
~~~

Hai pod có thể tạo trùng transactional IDs khi factory cấp suffix giống nhau. Kết quả là fencing giữa các producer, lỗi commit và mất ổn định. Group id là danh tính **chia tải**; transactional prefix là danh tính **producer ownership**.

### 14.3 Khi bị fencing trong rolling deploy

Không nên chỉ tăng retries. Cần kiểm tra:

- Hai pod có cùng transactionIdPrefix không?
- Pod cũ có thực sự đã dừng chưa?
- Có dùng shared ConfigMap chứa một ID cố định không?
- Factory có tạo transactional producers mới với ID trùng đang hoạt động không?
- Consumer group rebalance có diễn ra cùng thời điểm không?
- Broker transaction coordinator có báo lỗi khác không?

Khi producer đã bị fenced, producer cũ không thể tiếp tục transaction của mình một cách hợp lệ. Cần để framework/lifecycle thay thế producer theo cấu hình ownership đúng.

## 15. Độ tin cậy khi commit bị lỗi hoặc không rõ trạng thái

Một producer gửi record thành công chưa đồng nghĩa Kafka transaction đã commit. Có thể xảy ra:

~~~text
send output: broker ACK
commitTransaction: timeout do network
client không nhận được commit response
~~~

Ứng dụng không nên kết luận từ send ACK rằng output chắc chắn đã committed. Cũng không nên kết luận mọi commit timeout chắc chắn đã abort nếu không có bằng chứng phù hợp với Kafka protocol.

Một hướng xử lý an toàn:

1. Để Kafka client/transaction manager xác định trạng thái và xử lý exception theo contract.
2. Không tái sử dụng producer fatal/fenced.
3. Cho input được xử lý lại khi offset chưa commit theo framework semantics.
4. Dùng event ID ổn định để downstream loại trùng nếu có khoảng không chắc chắn.
5. Quan sát consumer read_committed thay vì chỉ dựa trên log “send success”.

V2 cải thiện cơ chế phối hợp/fencing offset trong group, nhưng không thể loại bỏ mọi trường hợp client mất kết nối hoặc không biết kết quả của request tức thời.

## 16. V2 và side effect ngoài Kafka

Giả sử một listener:

~~~java
@KafkaListener(
    topics = "payments.in",
    containerFactory = "transactionalListenerFactory"
)
public void onPayment(PaymentRequested event) {

    paymentGateway.charge(event);
    kafkaTemplate.send(
        "payments.out",
        event.paymentId(),
        "PAID"
    );
}
~~~

Nếu paymentGateway.charge() thành công rồi Kafka transaction abort, input có thể được xử lý lại. Ở lần tiếp theo, charge() có thể được gọi lần thứ hai.

Do đó, **Kafka EOS không đủ để bảo đảm thanh toán đúng một lần**.

Cần:

- Idempotency key ổn định gửi tới payment gateway.
- Cơ chế lưu trạng thái xử lý/processed event trong database.
- Reconciliation khi external response không rõ kết quả.
- Transactional outbox/inbox hoặc workflow thích hợp.

### 16.1 Dùng transactional outbox

Nếu nghiệp vụ ghi database rồi muốn publish Kafka event:

~~~text
DB transaction:
  UPDATE orders
  INSERT outbox_event
COMMIT DB

Outbox relay:
  đọc outbox
  publish Kafka
  đánh dấu trạng thái đã publish
~~~

Outbox giúp lưu ý định phát event cùng thay đổi nghiệp vụ, nhưng relay có thể gửi trùng khi crash giữa publish và đánh dấu trạng thái. Consumer vẫn cần idempotent.

Không coi EOSMode.V2 là thay thế cho outbox trong hệ thống có database side effect.

### 16.2 Chỉ có Kafka records mới nằm trong Kafka transaction

Một Kafka transaction có thể chứa output từ nhiều Kafka topics/partitions và input offsets. Nó không trực tiếp bao gồm HTTP requests, database commits hoặc cloud storage writes. Khi thiết kế kiến trúc, nên vẽ rõ ranh giới transaction như sau:

~~~mermaid
flowchart TB
    subgraph K["Kafka transaction"]
        A["Kafka output records"]
        B["Kafka input offsets"]
    end
    C["SQL database"] --- K
    D["External HTTP API"] --- K
    E["Email service"] --- K
    F["Business idempotency + outbox/inbox"] --> C
    F --> D
    F --> E
~~~

Các kết nối nét thường trong sơ đồ chỉ biểu thị một workflow liên quan; chúng **không** nói database/HTTP/email đã nằm trong transaction Kafka.

## 17. Quan sát EOSMode.V2 trong production

Một dashboard đúng phải quan sát **transaction outcome**, không chỉ số lần producer send.

| Nhóm | Metrics/sự kiện cần theo dõi |
|---|---|
| Producer transaction | Begin, commit, abort, timeout, commit latency |
| Producer fencing | ProducerFencedException, invalid epoch, duplicate tx prefix |
| Kafka broker | Transaction coordinator health, ISR, transaction timeouts |
| Consumer group | Rebalance count, generation/member changes, assignment |
| Consumer lag | Committed offset, log end offset, LSO đối với read_committed |
| Output | Records committed, downstream processing progress |
| Retry/rollback | AfterRollbackProcessor attempts, DLT/recovery failures |
| Business | Event ID, deduplication, mismatch giữa input và output |
| Factory | transactionCapable, prefix uniqueness, cached producer age |

### 17.1 Log phân biệt send và commit

Log tốt nên phân biệt các sự kiện:

~~~text
event=KAFKA_TX_BEGIN
listener=orders-transformer
group=orders-transformer-prod
instance=pod-a

event=KAFKA_SEND_ACK
topic=orders.out
key=order-1001

event=KAFKA_TX_COMMIT_SUCCESS
group=orders-transformer-prod
inputTopic=orders.in
inputPartition=0
inputOffset=200
~~~

Nếu chỉ có KAFKA_SEND_ACK mà không có commit success, không thể khẳng định output đã đủ điều kiện cho read_committed downstream.

### 17.2 Triệu chứng cần phân biệt

**Output không xuất hiện:** có thể do transaction abort hoặc vẫn mở, downstream dùng read_committed và đang chờ LSO, listener chưa chạy, hoặc producer send thất bại.

**Input record được xử lý lại:** có thể do Kafka transaction abort hoặc offset chưa commit, không nhất thiết EOS bị hỏng.

**ProducerFencedException tăng:** có thể do trùng transactional ID hoặc ownership/lifecycle không ổn định, không chỉ do Kafka broker lỗi.

**Consumer lag tăng khi HW vẫn tiến:** với read_committed có thể liên quan open transactions giữ LSO, ngoài các nguyên nhân thông thường như listener chậm.

## 18. Integration test để chứng minh EOS V2

Một unit test mock KafkaTemplate không chứng minh được Kafka transaction semantics. Nên dùng Kafka broker thật qua Testcontainers hoặc môi trường tích hợp tương đương, với version đáp ứng V2.

### 18.1 Test happy path

1. Tạo topic orders.in và orders.out.
2. Khởi chạy transactional listener container và KafkaTemplate.
3. Gửi input event có event ID duy nhất.
4. Listener gửi một output record trong transaction.
5. Chờ commit transaction.
6. Dùng consumer read_committed đọc orders.out.
7. Kiểm tra output xuất hiện một lần theo business ID và input group offset tiến.
8. Dùng logs/metrics để xác nhận transaction commit.

### 18.2 Test abort khi listener exception

1. Gửi input event.
2. Trong listener, gửi output rồi cố ý ném exception.
3. Xác nhận transaction abort.
4. Consumer read_committed của orders.out không đọc output aborted.
5. Kiểm tra input offset chưa được commit qua transaction thất bại.
6. Cho listener chạy lại và thành công.
7. Xác nhận chỉ output của transaction thành công được downstream read_committed nhìn thấy.

Có thể có nhiều lần listener invocation; đó là điều dự kiến khi retry. Kiểm tra committed Kafka effect, không chỉ số lần method được gọi.

### 18.3 Test rebalance và zombie fencing

1. Chạy hai consumer instances cùng group, transactionIdPrefix khác nhau.
2. Làm một consumer đang xử lý chậm hoặc ngừng poll theo tình huống thử nghiệm.
3. Tạo rebalance để partition chuyển ownership.
4. Cố cho consumer cũ tiếp tục commit transaction khi không còn ownership hợp lệ.
5. Xác nhận protocol/framework không cho offset commit không hợp lệ trở thành kết quả thành công.
6. Consumer mới xử lý input và commit hợp lệ.
7. Kiểm tra downstream read_committed không thấy output từ transaction abort.

Test này phải được thiết kế thận trọng với framework version, transaction timeout và max.poll.interval.ms; không phải cứ kill một pod là tái tạo đúng mọi tình huống fencing.

### 18.4 Test duplicate transactional ID

1. Trong test environment, cố cấu hình hai producer dùng cùng transactional ID.
2. Xác nhận có fencing/epoch-related error theo Kafka semantics.
3. Sửa prefix riêng từng instance.
4. Chạy lại transaction commit.
5. Xác nhận cả hai instances cùng hoạt động mà không tranh chấp ID.

Đây là test **sai cấu hình producer identity**, khác với test consumer group metadata.

### 18.5 Test read_uncommitted và read_committed

- Gửi output trong một transaction rồi abort.
- Dùng read_uncommitted consumer quan sát behavior theo Kafka protocol.
- Dùng read_committed consumer kiểm chứng aborted output không được giao như record hợp lệ.
- Gửi transaction mới và commit; kiểm chứng output committed xuất hiện.
- Quan sát LSO khi có open transaction nếu cần.

### 18.6 Test crash giữa side effect và commit

Nếu listener ghi một database:

1. Cho database write thành công.
2. Gây Kafka transaction abort hoặc crash trước Kafka commit.
3. Để input được redeliver.
4. Xác nhận idempotency ở database ngăn ghi trùng.
5. Chỉ khi side effect được bảo vệ mới kết luận workflow nghiệp vụ đủ an toàn.

## 19. Các hiểu nhầm thường gặp

**“EOSMode.V2 chỉ cần thêm một enum là có exactly-once.”** Sai. Cần ProducerFactory transaction capable, transaction manager, listener container transaction và offset-in-transaction thực sự hoạt động.

**“V2 bỏ nhu cầu transactional.id.”** Sai. Producer vẫn cần transactional identity; prefix phải không trùng giữa những producer hoạt động đồng thời.

**“group.id và transactionIdPrefix nên giống nhau trên mọi pod.”** Sai. Group id nên giống nhau giữa replicas của một group, còn transactional prefix cần uniqueness theo producer factory instance.

**“KafkaTemplate.send() trả về thành công là transaction đã commit.”** Sai. Send acknowledgment và commit outcome là hai sự kiện khác nhau.

**“read_committed không cần thiết vì producer đã transactional.”** Sai nếu downstream cần bỏ qua aborted records.

**“Consumer method sẽ không bao giờ chạy lại.”** Sai. Retry, abort, restart và rebalance có thể làm input được xử lý lại.

**“V2 tự làm database transaction và Kafka transaction atomic.”** Sai. Cần cơ chế riêng cho database/HTTP side effects.

**“Transaction abort đồng nghĩa mọi side effect đã rollback.”** Sai với những hiệu ứng ngoài Kafka.

**“ProducerFencedException luôn là lỗi broker.”** Sai. Trùng transactional ID hoặc thay đổi ownership có thể là nguyên nhân.

**“Tăng transaction timeout sẽ sửa mọi vấn đề.”** Sai. Nó có thể che transaction quá dài và làm read_committed tiến chậm.

**“Spring Kafka 3.x phải gọi setEosMode(V2).”** Không nên giả định. V2 là cơ chế EOS được hỗ trợ trong các bản hiện đại; API enum có thể không còn.

**“read_committed nghĩa là mọi record trong Kafka đều thuộc transaction.”** Sai. Consumer read_committed vẫn đọc records non-transactional phù hợp.

## 20. Quy trình xử lý sự cố EOS V2

Khi input được đọc lại bất thường, output thiếu hoặc producer bị fenced:

1. **Xác định phiên bản:** Spring Kafka, Kafka client và broker có tương thích V2 không?
2. **Kiểm tra factory:** ProducerFactory đúng có transactionCapable()=true không?
3. **Kiểm tra prefix:** transactionIdPrefix có duy nhất trên các active instances không?
4. **Kiểm tra manager:** KafkaTransactionManager dùng factory nào?
5. **Kiểm tra container:** listener container có mở Kafka transaction và commit offsets qua transaction không?
6. **Kiểm tra auto commit:** consumer enable.auto.commit có bị bật nhầm không?
7. **Xem exception:** phân biệt producer fencing, transaction timeout, commit failure, serialization và broker errors.
8. **Xem group assignment:** có rebalance hoặc member bị mất ownership giữa transaction không?
9. **Kiểm tra output visibility:** downstream isolation.level là gì? Có open transaction/LSO stall không?
10. **Đối chiếu input offset:** committed offset đã tiến hay chưa, có replay đúng phạm vi không?
11. **Kiểm tra external side effects:** database/HTTP đã thực hiện trước khi transaction abort không?
12. **Khôi phục:** sửa configuration, để framework cleanup transaction, kiểm chứng bằng canary.
13. **Theo dõi sau sửa:** commit/abort rate, output, lag, DLT và duplicate business effects.

Không reset input offset chỉ để “làm mất lỗi” trước khi biết transaction nào đã committed. Seek/reset có thể tạo replay lớn hoặc bỏ qua records chưa được xử lý.

## 21. Checklist triển khai

**Compatibility và capability**

- [ ] Kafka brokers và clients đáp ứng yêu cầu của EOS V2.
- [ ] Biết Spring Kafka version đang dùng EOSMode enum hay đã chỉ hỗ trợ V2.
- [ ] ProducerFactory thực tế là transaction capable.
- [ ] KafkaTemplate và KafkaTransactionManager dùng đúng factory.
- [ ] Có transaction ID prefix duy nhất giữa các active application instances.

**Listener và offset**

- [ ] Transactional listener container được cấu hình theo API của Spring Kafka version thực tế.
- [ ] Consumer auto offset commit đã tắt.
- [ ] Input offsets được container gửi vào cùng Kafka transaction với output.
- [ ] Không có đường commitSync/commitAsync độc lập phá ranh giới transaction.
- [ ] Retry/rollback/recovery dùng cơ chế phù hợp với transactional listener.

**Producer và downstream**

- [ ] Producer idempotence, acks, timeout, replication/ISR phù hợp.
- [ ] Transaction không kéo dài quá mức vì external I/O.
- [ ] Producer fencing, cache age và transaction timeout được theo dõi.
- [ ] Downstream dùng read_committed khi cần committed visibility.
- [ ] Có cảnh báo open transaction/LSO stall và bất thường về consumer lag.

**Business correctness**

- [ ] Ranh giới EOS được mô tả chính xác: Kafka output + Kafka offset.
- [ ] Database/HTTP/email side effects có idempotency hoặc outbox/inbox.
- [ ] Có business event ID để đối chiếu và deduplication khi cần.
- [ ] Có runbook rollback, DLT và xử lý lỗi commit không rõ kết quả.

**Verification**

- [ ] Đã kiểm thử commit thành công bằng consumer read_committed.
- [ ] Đã kiểm thử abort sau khi gửi output.
- [ ] Đã kiểm thử rebalance/fencing trong môi trường tích hợp.
- [ ] Đã kiểm thử trùng transactional ID và cách phục hồi.
- [ ] Đã kiểm thử crash giữa external side effect và Kafka commit.
- [ ] Có metrics transaction commit/abort, fencing và offset progression.

## 22. Kết luận

**EOSMode.V2** là cơ chế EOS hiện đại của Spring Kafka nhằm kết hợp Kafka producer transactions với thông tin consumer group khi commit offsets vào cùng transaction. Nó cải thiện khả năng fencing/ownership so với cơ chế cũ và là nền tảng của mô hình consume-transform-produce exactly-once **trong phạm vi Kafka**.

Triển khai đúng đòi hỏi nhiều hơn một lựa chọn chế độ: ProducerFactory phải transaction capable, transactional IDs không được trùng giữa producers đang hoạt động, KafkaTransactionManager và listener container phải dùng đúng factory, input offsets phải đi cùng output vào transaction, và downstream phải đọc read_committed nếu cần loại bỏ aborted output. Khi input bị retry hoặc transaction abort, code nghiệp vụ vẫn có thể chạy lại; những side effect ngoài Kafka luôn cần biện pháp bảo vệ riêng. Đó là ranh giới giúp EOSMode.V2 trở thành một cơ chế reliability có thể kiểm chứng thay vì một tên cấu hình dễ gây hiểu nhầm.


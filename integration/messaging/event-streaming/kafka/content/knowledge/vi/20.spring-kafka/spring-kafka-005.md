# @KafkaListener, container factory và nhóm consumer

Spring Kafka giúp tích hợp Kafka vào ứng dụng Spring bằng cách quản lý vòng đời consumer, poll loop, listener thread, offset commit và xử lý lỗi. Thay vì tự tạo KafkaConsumer rồi viết vòng lặp poll, ứng dụng khai báo một phương thức listener bằng @KafkaListener. Spring tạo listener container để gọi phương thức đó khi có record.

Container factory là nơi định nghĩa cách listener hoạt động: ConsumerFactory nào được dùng, số consumer instance, kiểu record hay batch, acknowledgment mode, error handler và các thuộc tính container khác. Consumer group quyết định các instance chia partition như thế nào và mỗi group có tiến độ đọc độc lập ra sao.

Ba thành phần cần hiểu cùng nhau:

- **@KafkaListener:** khai báo endpoint nhận record và phương thức xử lý.
- **Listener container factory:** tạo container và consumer theo cấu hình chung.
- **Consumer group:** xác định phạm vi chia sẻ partition và offset giữa các consumer.

Nếu cấu hình ba thành phần này không nhất quán, ứng dụng có thể tạo quá nhiều consumer, đọc trùng giữa các group, commit offset sai thời điểm hoặc không đạt concurrency mong muốn.

## 1. Luồng xử lý của Spring Kafka

Trong ứng dụng dùng Spring Kafka, listener container quản lý KafkaConsumer. Container gọi poll, nhận record, chuyển dữ liệu sang listener method, xử lý acknowledgment và phối hợp error handler.

~~~mermaid
flowchart TD
    A["Kafka broker"] --> B["KafkaConsumer"]
    B --> C["Listener container"]
    C --> D["Poll records"]
    D --> E["@KafkaListener method"]
    E --> F{"Xử lý thành công?"}
    F -->|Có| G["Acknowledgment / offset commit"]
    F -->|Không| H["CommonErrorHandler"]
    H --> I["Retry hoặc recover / DLT"]
    I --> G
    G --> C
~~~

Ứng dụng không cần tự gọi poll trong listener method. Container chịu trách nhiệm duy trì consumer loop và điều phối việc nhận record.

Với một listener endpoint, Spring tạo một container. Nếu container có concurrency lớn hơn một, nó tạo các child container/consumer instance để tham gia group. Mỗi consumer instance có poll loop riêng.

### 1.1. Những trách nhiệm được Spring quản lý

Spring Kafka hỗ trợ quản lý:

- Khởi tạo và đóng KafkaConsumer.
- Subscribe topic hoặc gán partition.
- Poll record theo cấu hình.
- Chuyển record hoặc payload vào listener method.
- Gọi listener theo record hoặc batch.
- Commit offset theo acknowledgment mode.
- Xử lý exception qua error handler.
- Pause/resume container hoặc partition.
- Rebalance callback và lifecycle của container.
- Tạo consumer concurrency theo factory hoặc endpoint.

Ứng dụng vẫn phải quyết định logic nghiệp vụ, idempotency, retry policy, ordering, transaction boundary và cách phục hồi dữ liệu lỗi.

## 2. Thêm dependency và bật listener annotation

Với Spring Boot, dependency phổ biến là starter Kafka:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
~~~

Khi dùng Spring Boot dependency management, thường không cần tự chỉ định version riêng cho spring-kafka. Nên để Spring Boot BOM quản lý phiên bản tương thích giữa Spring Kafka và Kafka client.

Một ứng dụng Spring có thể bật listener annotation bằng @EnableKafka:

~~~java
@SpringBootApplication
@EnableKafka
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            OrderApplication.class,
            args
        );
    }
}
~~~

Trong một số phiên bản/cấu hình Spring Boot, hạ tầng annotation-driven được auto-configure sẵn. Nếu dùng cấu hình Spring thuần hoặc custom application context, cần bảo đảm @EnableKafka được khai báo để đăng ký listener endpoint.

Không tạo KafkaConsumer trực tiếp trong bean listener. Hãy để listener container quản lý consumer và lifecycle.

## 3. Cấu hình Kafka cơ bản trong application.yml

Một cấu hình Spring Boot tối thiểu:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.OrderEvent
        spring.json.trusted.packages: com.example.orders
    listener:
      ack-mode: record
      concurrency: 3
~~~

Ý nghĩa:

| Thuộc tính | Ý nghĩa |
|---|---|
| bootstrap-servers | Địa chỉ broker dùng để khởi tạo kết nối |
| consumer.group-id | Group mặc định cho consumer |
| auto-offset-reset | Chính sách khi group chưa có offset hợp lệ |
| enable-auto-commit | Tắt auto commit để container quản lý acknowledgment |
| key-deserializer | Chuyển key bytes thành Java type |
| value-deserializer | Chuyển value bytes thành Java object |
| spring.json.value.default.type | Kiểu đích khi dùng JsonDeserializer |
| spring.json.trusted.packages | Các package được phép deserialize |
| listener.ack-mode | Cách container xác nhận offset |
| listener.concurrency | Số consumer instance cho listener mặc định |

Các tên property cần được kiểm tra theo phiên bản Spring Boot/Spring Kafka đang sử dụng. Không đưa package wildcard quá rộng vào trusted packages nếu không cần thiết. Với hệ thống nhiều loại event, có thể dùng type mapping hoặc event envelope chung thay vì phụ thuộc hoàn toàn vào class name trong header.

### 3.1. auto-offset-reset không reset offset mỗi lần restart

auto-offset-reset chỉ được dùng khi group chưa có committed offset hoặc offset đã commit không còn hợp lệ theo retention/truncation. Nó không làm consumer luôn đọc từ đầu mỗi khi ứng dụng khởi động.

Các giá trị thường gặp:

- earliest: đọc từ offset sớm nhất còn có thể đọc.
- latest: đọc từ cuối log khi không có offset hợp lệ.
- none: báo lỗi nếu không tìm thấy offset hợp lệ.

Trong production, chọn policy có chủ đích. Dùng earliest có thể khiến một group mới đọc lại lượng dữ liệu lớn; latest có thể bỏ qua lịch sử trước khi group bắt đầu.

## 4. ConsumerFactory: nơi tạo KafkaConsumer

ConsumerFactory tạo KafkaConsumer với cấu hình như bootstrap servers, group ID, deserializer, security và các consumer properties khác.

Trong Spring Boot, Boot có thể tự cấu hình ConsumerFactory dựa trên spring.kafka.*. Nếu cần custom behavior, có thể khai báo factory rõ ràng.

Ví dụ dùng JSON deserializer:

~~~java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    public ConsumerFactory<String, OrderEvent> orderConsumerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
        properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        properties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

        return new DefaultKafkaConsumerFactory<>(
            properties,
            new StringDeserializer(),
            new JsonDeserializer<>(OrderEvent.class, false)
        );
    }
}
~~~

Đây là ví dụ cấu hình cho một phiên bản Spring Kafka có constructor JsonDeserializer tương ứng. Nếu phiên bản khác, dùng constructor hoặc property binding được tài liệu của phiên bản đó hỗ trợ.

Không nên khai báo cùng một consumer property ở nhiều nơi với giá trị mâu thuẫn. Hãy xác định cấu hình nào là mặc định của ứng dụng và cấu hình nào được override riêng cho một listener.

### 4.1. Một ConsumerFactory có thể được nhiều listener dùng chung

Nếu các listener có cùng deserializer, security và phần lớn consumer properties, có thể dùng chung ConsumerFactory.

Nếu một listener cần group ID, deserializer hoặc isolation level khác, có thể tạo ConsumerFactory riêng hoặc dùng factory chung với cấu hình phù hợp. Cần cân nhắc chi phí quản lý connection và số consumer thực tế.

### 4.2. Không dùng một KafkaConsumer cho nhiều listener thread

ConsumerFactory tạo consumer instance theo yêu cầu của container. KafkaConsumer không thread-safe. Spring Kafka quản lý mỗi consumer instance trên thread tương ứng; ứng dụng không nên lấy consumer nội bộ rồi dùng từ thread tùy ý.

## 5. ConcurrentKafkaListenerContainerFactory

Container factory tạo listener container cho các phương thức @KafkaListener. Với record listener, factory thường là ConcurrentKafkaListenerContainerFactory.

Ví dụ:

~~~java
@Configuration
public class OrderListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> orderConsumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(orderConsumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD
        );

        return factory;
    }
}
~~~

Factory này thiết lập:

- ConsumerFactory dùng để tạo consumer.
- Concurrency mặc định là 3.
- Acknowledgment mode là RECORD.

Mỗi listener có thể chọn factory bằng tên bean:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-projection",
    containerFactory = "kafkaListenerContainerFactory"
)
public void consume(OrderEvent event) {
    // Xử lý event.
}
~~~

Nếu không chỉ định containerFactory, Spring Kafka tìm factory mặc định có tên kafkaListenerContainerFactory. Nếu ứng dụng có nhiều factory, nên đặt tên rõ ràng và chỉ định trên listener để tránh chọn nhầm.

### 5.1. Tạo nhiều container factory cho các kiểu xử lý khác nhau

Có thể cần nhiều factory:

- Record listener đồng bộ với acknowledgment RECORD.
- Batch listener nhận nhiều record mỗi poll.
- Listener cần concurrency khác.
- Listener có error handler hoặc transaction manager riêng.
- Listener dùng deserializer hoặc consumer properties khác.

Ví dụ factory cho batch:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(2);

    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.BATCH
    );

    return factory;
}
~~~

Factory batch phải được dùng với listener method có signature tương thích batch. Không bật batchListener cho factory nhưng vẫn viết listener như chỉ nhận một payload đơn lẻ.

## 6. @KafkaListener cơ bản

Một listener đơn giản:

~~~java
@Component
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        topics = "order-events",
        groupId = "order-service"
    )
    public void onOrderEvent(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

Khi record đến, Spring Kafka deserialize value thành OrderEvent rồi gọi onOrderEvent.

Các thuộc tính quan trọng:

| Thuộc tính | Vai trò |
|---|---|
| topics | Danh sách topic listener subscribe |
| topicPattern | Subscribe các topic khớp regex |
| groupId | Group ID cho listener |
| id | ID của listener container endpoint |
| containerFactory | Tên bean container factory |
| concurrency | Override số consumer instance cho endpoint |
| autoStartup | Có tự khởi động container khi context start không |
| clientIdPrefix | Prefix cho client.id của consumer |
| properties | Consumer properties bổ sung cho endpoint |
| errorHandler | Error handler theo endpoint nếu phiên bản hỗ trợ |

Một listener thường chọn topics hoặc topicPattern. Cấu hình topicPartitions dùng khi cần gán partition cụ thể và có semantics khác với subscription group thông thường.

### 6.1. topics và topicPattern

Dùng topics khi biết tên topic cố định:

~~~java
@KafkaListener(
    topics = {"order-created", "order-cancelled"},
    groupId = "order-audit"
)
public void audit(OrderEvent event) {
    auditService.record(event);
}
~~~

Dùng topicPattern khi cần subscribe các topic được tạo theo quy tắc tên:

~~~java
@KafkaListener(
    topicPattern = "tenant-.*-events",
    groupId = "tenant-audit"
)
public void auditTenantEvent(String event) {
    // Xử lý event từ các topic khớp pattern.
}
~~~

Pattern subscription có thể phát hiện topic mới khi metadata được cập nhật. Cần kiểm soát regex để không vô tình subscribe các topic nội bộ, retry hoặc DLT.

### 6.2. topicPartitions cho assignment tường minh

Có thể chỉ định partition cụ thể:

~~~java
@KafkaListener(
    id = "partition-0-listener",
    groupId = "manual-partition-reader",
    topicPartitions = @TopicPartition(
        topic = "order-events",
        partitions = {"0", "1"}
    )
)
public void readSelectedPartitions(OrderEvent event) {
    process(event);
}
~~~

Assignment tường minh dùng cơ chế assign partition thay vì để group coordinator phân phối qua subscribe/rebalance thông thường. Cần tự quản lý việc phân chia partition giữa các listener instance và xử lý thay đổi partition topology. Không cấu hình nhiều instance cùng gán một partition nếu không có chủ đích.

## 7. Phân biệt id, groupId và clientId

Ba giá trị này có mục đích khác nhau:

- id xác định listener endpoint/container trong Spring.
- groupId xác định consumer group trong Kafka.
- clientId nhận diện client instance trong log, metric và broker request.

Ví dụ:

~~~java
@KafkaListener(
    id = "order-projection-listener",
    groupId = "order-projection",
    clientIdPrefix = "order-projection-client",
    topics = "order-events"
)
public void consume(OrderEvent event) {
    projection.apply(event);
}
~~~

Một listener endpoint có id ổn định, nhưng khi concurrency lớn hơn một, Spring có thể thêm suffix để tạo client ID riêng cho từng consumer instance.

### 7.1. id không phải groupId

Nếu không khai báo groupId riêng, Spring Kafka có thể dùng id làm group ID khi idIsGroup đang bật theo mặc định. Điều này dễ gây nhầm lẫn nếu developer tưởng id chỉ là tên container.

Khi muốn tách rõ hai vai trò, khai báo groupId rõ ràng. Nếu cần giữ group ID từ consumer properties và không muốn id override nó, kiểm tra thuộc tính idIsGroup của phiên bản Spring Kafka đang dùng.

Không dùng cùng một group ID cho hai ứng dụng có logic xử lý khác nhau nếu chúng cần mỗi ứng dụng nhận toàn bộ dữ liệu. Các ứng dụng khác group sẽ có tiến độ đọc độc lập.

## 8. Consumer group và cách chia partition

Consumer group là nhóm các consumer cùng dùng một group ID để chia partition. Trong cùng group, mỗi partition tại một thời điểm chỉ được gán cho tối đa một member.

Ví dụ topic order-events có sáu partition và group order-service có ba consumer:

~~~text
order-events:
  P0  P1  P2  P3  P4  P5

Group order-service:
  Consumer A -> P0, P1
  Consumer B -> P2, P3
  Consumer C -> P4, P5
~~~

Nếu group có sáu consumer, mỗi consumer có thể nhận một partition. Nếu có tám consumer, hai consumer có thể không được gán partition.

### 8.1. Cùng group thì chia nhau dữ liệu

~~~text
Topic orders
    |
    +--> Group billing
    |       Consumer B1 -> P0, P1
    |       Consumer B2 -> P2, P3
    |
    +--> Group analytics
            Consumer A1 -> P0, P1
            Consumer A2 -> P2, P3
~~~

Billing và analytics đều có thể đọc toàn bộ topic theo offset riêng vì chúng thuộc hai group khác nhau. Các consumer trong cùng group chia partition cho nhau.

### 8.2. Khác group thì mỗi group nhận toàn bộ luồng

Nếu tạo group audit mới, group audit không lấy mất partition của billing. Nó có assignment và offset độc lập.

Điều này thường dùng khi nhiều ứng dụng cần phản ứng độc lập với cùng event:

- billing xử lý thanh toán.
- analytics cập nhật chỉ số.
- audit lưu dấu vết.
- notification gửi thông báo.

Không dùng một group chung nếu mỗi ứng dụng cần xử lý mọi record độc lập.

## 9. Concurrency và số partition

Concurrency là số consumer instance mà một listener container tạo ra. Có thể đặt ở factory:

~~~java
factory.setConcurrency(4);
~~~

Hoặc override trên listener:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-service",
    concurrency = "4"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Giả sử topic có ba partition:

| Concurrency | Số consumer có thể nhận partition | Consumer dư |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 3 | 0 |
| 4 | 3 | 1 |
| 6 | 3 | 3 |

Concurrency cao hơn partition count không làm tăng mức song song đọc topic đó. Các consumer dư vẫn có thể tham gia group nhưng không nhận partition trong assignment hiện tại.

Nếu listener subscribe nhiều topic, tổng partition và tập subscription có ảnh hưởng đến assignment. Không mặc định mọi consumer sẽ nhận đúng cùng số partition.

### 9.1. Concurrency không phải worker pool cho từng record

Concurrency tạo thêm KafkaConsumer instance và poll loop. Nó không tự tạo một thread cho từng record và không làm một partition được chia đồng thời cho nhiều consumer trong cùng group.

Nếu cần xử lý song song record bên trong một partition, phải tự quản lý worker pool, thứ tự hoàn thành và offset commit. Đây là bài toán riêng với listener concurrency.

### 9.2. Tác động của rebalance

Khi consumer instance tham gia hoặc rời group, partition assignment có thể thay đổi. Deployment, autoscaling hoặc crash liên tục có thể gây rebalance thường xuyên.

Cần:
- Chọn concurrency phù hợp với partition count.
- Tránh scale dao động quá nhanh.
- Đặt poll interval phù hợp thời gian xử lý.
- Theo dõi rebalance rate và consumer lag.
- Xử lý revoke/assign an toàn nếu ứng dụng có state hoặc worker pool.

## 10. Listener method có thể nhận những tham số nào?

Spring Kafka hỗ trợ nhiều kiểu signature. Lựa chọn phụ thuộc mức metadata mà ứng dụng cần.

### 10.1. Chỉ nhận payload

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-service"
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

Đây là cách đơn giản khi logic chỉ cần nội dung event.

### 10.2. Nhận ConsumerRecord

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-audit"
)
public void listen(ConsumerRecord<String, OrderEvent> record) {
    log.info(
        "topic={}, partition={}, offset={}, key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );

    auditService.record(record.value());
}
~~~

ConsumerRecord cung cấp:
- topic.
- partition.
- offset.
- key và value.
- timestamp.
- headers.
- serialized key/value size.

Đây là lựa chọn hữu ích cho tracing, audit, kiểm tra offset và xử lý phụ thuộc metadata Kafka.

### 10.3. Nhận header

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-audit"
)
public void listen(
        @Payload OrderEvent event,
        @Header(KafkaHeaders.RECEIVED_KEY) String key,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    auditService.record(event, key, partition, offset);
}
~~~

Tên header và kiểu dữ liệu cần khớp phiên bản Spring Kafka. Nếu cần toàn bộ header hoặc xử lý header trùng tên, nhận ConsumerRecord thường rõ ràng hơn.

### 10.4. Nhận Acknowledgment

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-service"
)
public void listen(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    orderService.process(event);
    acknowledgment.acknowledge();
}
~~~

Acknowledgment chỉ phù hợp khi container được cấu hình manual acknowledgment mode. Nếu dùng ack mode tự động như RECORD hoặc BATCH, không cần gọi acknowledge thủ công.

Không acknowledge trước khi side effect nghiệp vụ hoàn tất. Nếu commit offset trước khi database transaction thành công, consumer crash có thể làm record không được giao lại.

## 11. Record listener và batch listener

Mặc định, listener thường xử lý từng record. Batch listener nhận một danh sách record từ một poll.

### 11.1. Record listener

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-service",
    containerFactory = "kafkaListenerContainerFactory"
)
public void listen(ConsumerRecord<String, OrderEvent> record) {
    orderService.process(record.value());
}
~~~

Ưu điểm:
- Xử lý lỗi và retry theo từng record dễ hiểu.
- Có thể commit theo từng record với AckMode.RECORD.
- Logic nghiệp vụ đơn lẻ dễ kiểm thử.

Đổi lại, overhead gọi listener cho từng record có thể cao hơn khi throughput rất lớn.

### 11.2. Batch listener

Factory batch:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        batchFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(2);

    return factory;
}
~~~

Listener nhận batch:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch",
    containerFactory = "batchFactory"
)
public void listenBatch(
        List<ConsumerRecord<String, OrderEvent>> records) {

    orderService.processBatch(records);
}
~~~

Batch size bị ảnh hưởng bởi dữ liệu sẵn có, max.poll.records và giới hạn fetch. Không bảo đảm mỗi poll luôn trả đủ số record tối đa.

### 11.3. Lưu ý về lỗi trong batch

Nếu một record trong batch lỗi, error handler cần biết record nào thất bại và phần nào đã xử lý. Batch listener có thể dùng BatchListenerFailedException để chỉ ra index/record lỗi trong các phiên bản Spring Kafka hỗ trợ.

Nếu batch được ghi vào database trong một transaction, có thể rollback toàn bộ batch. Nếu xử lý từng record riêng, phải quản lý tiến độ và commit sao cho không bỏ qua record chưa thành công.

Không dùng batch listener chỉ vì muốn tăng tốc. Đo throughput, latency và độ phức tạp recovery trước khi chuyển.

## 12. Acknowledgment mode và offset commit

Spring Kafka container quản lý commit offset dựa trên acknowledgment mode. Cần hiểu mode đang dùng trước khi viết listener.

| Ack mode | Hành vi khái quát |
|---|---|
| RECORD | Commit sau khi từng record listener xử lý xong |
| BATCH | Commit sau khi xử lý xong toàn bộ records trả về trong poll |
| TIME | Commit theo khoảng thời gian cấu hình |
| COUNT | Commit khi đạt số record đã xử lý |
| COUNT_TIME | Kết hợp điều kiện count và time |
| MANUAL | Listener gọi acknowledge; commit theo semantics batch |
| MANUAL_IMMEDIATE | Listener gọi acknowledge để yêu cầu commit ngay khi có thể |

Ack mode mặc định phổ biến của container là BATCH. RECORD chỉ phù hợp với record listener, không phải batch listener.

### 12.1. Ví dụ RECORD

~~~java
factory.getContainerProperties().setAckMode(
    ContainerProperties.AckMode.RECORD
);
~~~

Sau khi listener xử lý một record thành công và trả về, container xác nhận offset tương ứng theo mode này. Nếu listener ném exception, error handler quyết định retry/recover và tiến độ commit.

### 12.2. Ví dụ MANUAL

~~~java
factory.getContainerProperties().setAckMode(
    ContainerProperties.AckMode.MANUAL
);
~~~

Listener:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-manual"
)
public void listen(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    orderService.process(event);
    acknowledgment.acknowledge();
}
~~~

Chỉ gọi acknowledge sau khi công việc cần được xác nhận đã hoàn tất. Nếu acknowledgment được gọi từ thread khác hoặc theo thứ tự không đồng bộ, cần kiểm tra cấu hình async acknowledgments và các giới hạn của phiên bản Spring Kafka. Mặc định nên acknowledge trên listener thread sau khi xử lý xong.

### 12.3. enable.auto.commit

Với listener container, nên để container quản lý commit thay vì bật auto commit của KafkaConsumer. Có thể cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
~~~

Nếu auto commit chạy độc lập với việc xử lý nghiệp vụ, offset có thể tiến lên trước khi side effect hoàn tất. Điều đó làm tăng nguy cơ mất xử lý khi process crash.

### 12.4. Offset là vị trí tiếp theo cần đọc

Kafka lưu offset tiếp theo cần đọc, không phải offset cuối đã xử lý. Nếu record offset 10 đã xử lý xong, commit offset 11.

Với xử lý bất đồng bộ, không commit vượt qua record chưa hoàn tất. Ví dụ offset 10 chưa xong nhưng offset 11 đã xong thì không thể commit offset 12 một cách an toàn.

## 13. Error handler và retry trong container factory

Listener method có thể ném exception. Spring Kafka dùng CommonErrorHandler để xử lý lỗi từ listener container.

Ví dụ dùng DefaultErrorHandler và DLT recoverer:

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            template,
            (record, exception) ->
                new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
        );

    FixedBackOff backOff = new FixedBackOff(
        1_000L,
        2L
    );

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class
    );

    return handler;
}
~~~

Gắn handler vào factory:

~~~java
factory.setCommonErrorHandler(kafkaErrorHandler);
~~~

Trong ví dụ, record được retry hữu hạn với backoff. Khi hết retry, recoverer publish sang DLT theo topic và partition tương ứng. DLT cần có số partition phù hợp nếu muốn giữ partition mapping nguồn.

Đây là ví dụ cấu hình khái quát. Cần kiểm tra phiên bản Spring Kafka, serializer của KafkaTemplate và policy exception thực tế.

### 13.1. Lỗi deserialize xảy ra trước listener

Nếu JSON hoặc Avro deserialize thất bại, listener method có thể chưa được gọi. Cần cấu hình ErrorHandlingDeserializer hoặc cơ chế tương ứng để exception deserialize được chuyển đến error handler.

Ví dụ JSON deserializer delegate:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.OrderEvent
        spring.json.trusted.packages: com.example.orders
~~~

Khi deserialize lỗi, Spring Kafka có thể chuyển thông tin lỗi trong header để error handler/recoverer xử lý. Cần thiết kế DLT publisher có khả năng giữ raw bytes khi value không thể tạo thành OrderEvent.

### 13.2. Blocking retry và retry topic

DefaultErrorHandler có thể retry tại luồng xử lý hiện tại. Spring Kafka cũng có @RetryableTopic để chuyển record sang retry topic và thử lại sau delay.

Retry topic giúp main listener tiếp tục, nhưng event sau của cùng key có thể được xử lý trước event đang retry. Nếu cần ordering nghiêm ngặt, hãy dùng blocking retry có giới hạn hoặc aggregate version/holdback để ngăn event vượt version.

Không retry vô hạn trong listener thread. Retry cần phân loại exception, số lần thử, backoff, DLT và cảnh báo.

## 14. Cấu hình listener riêng theo endpoint

Có thể override consumer properties cho một listener bằng properties:

~~~java
@KafkaListener(
    topics = "priority-orders",
    groupId = "priority-order-service",
    properties = {
        "max.poll.records=20",
        "max.poll.interval.ms=300000"
    }
)
public void listenPriority(OrderEvent event) {
    priorityService.process(event);
}
~~~

Các properties này bổ sung hoặc override consumer properties theo quy tắc của Spring Kafka phiên bản đang dùng. Không nên dùng override rải rác mà không ghi lại cấu hình hiệu lực.

Nếu endpoint cần deserializer khác hoặc batch mode khác, dùng container factory riêng thường dễ quản lý hơn.

## 15. Quản lý listener container bằng KafkaListenerEndpointRegistry

Spring Kafka đăng ký các listener container để ứng dụng có thể quản lý lifecycle.

Ví dụ:

~~~java
@Component
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControlService(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrderListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("order-listener");

        if (container != null) {
            container.pause();
        }
    }

    public void resumeOrderListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("order-listener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

Listener cần có id tương ứng:

~~~java
@KafkaListener(
    id = "order-listener",
    topics = "order-events",
    groupId = "order-service"
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

Pause/resume hữu ích khi downstream quá tải hoặc cần bảo trì. Pause container không đồng nghĩa đóng consumer; container vẫn cần poll để duy trì membership và xử lý trạng thái group. Không nên gọi các thao tác KafkaConsumer trực tiếp từ thread tùy ý.

### 15.1. autoStartup

Có thể trì hoãn việc khởi động một listener:

~~~java
@KafkaListener(
    id = "delayed-listener",
    topics = "order-events",
    groupId = "order-delayed",
    autoStartup = "false"
)
public void listen(OrderEvent event) {
    process(event);
}
~~~

Sau đó điều khiển qua KafkaListenerEndpointRegistry. Chỉ dùng khi startup sequencing thực sự cần thiết; listener bị dừng sẽ làm lag tích lũy.

## 16. Tạo topic bằng NewTopic bean

Spring Kafka hỗ trợ khai báo topic qua KafkaAdmin và NewTopic:

~~~java
@Bean
public NewTopic orderEventsTopic() {
    return TopicBuilder.name("order-events")
        .partitions(6)
        .replicas(3)
        .build();
}
~~~

Cấu hình replication factor phải phù hợp số broker trong cluster. Ví dụ replicas 3 không thể tạo thành công trên cluster chỉ có một broker.

Trong production, topic có thể được quản lý bởi nền tảng hoặc quy trình infrastructure-as-code. Nếu ứng dụng tự tạo topic, cần thống nhất quyền ACL và tránh nhiều service tranh chấp cấu hình topic.

Không tự ý thay đổi partition count từ code khởi động nếu việc đó ảnh hưởng ordering/key mapping.

## 17. Giao dịch và acknowledgment trong Spring Kafka

Spring Kafka hỗ trợ transaction manager để producer gửi nhiều record trong một Kafka transaction. Listener container có thể tham gia Kafka transaction nếu được cấu hình transaction-capable producer factory và transaction manager tương ứng.

Khái niệm cần phân biệt:

- Acknowledgment/offset commit xác nhận consumer progress.
- Kafka transaction có thể kết hợp output records và offset của input trong cùng transaction.
- Database transaction không tự động nằm trong Kafka transaction.
- Exactly-once trong Kafka không tự động bao trùm HTTP hoặc database side effect bên ngoài.

Với xử lý consume-transform-produce trong Kafka, transaction có thể giúp output và offset được commit nguyên tử. Consumer downstream cần dùng isolation.level=read_committed nếu chỉ muốn đọc transaction đã commit.

Nếu listener cập nhật database rồi commit Kafka offset, vẫn cần thiết kế idempotency hoặc inbox/outbox để xử lý crash giữa hai hệ thống. Không gọi acknowledge sớm chỉ vì producer đã gửi output; phải hiểu transaction boundary và container configuration.

## 18. Quan sát consumer group và listener

Một listener chạy đúng cần được theo dõi ở cả tầng Spring và Kafka.

Các thông tin quan trọng:

- Listener endpoint ID.
- Group ID và client ID.
- Topic, partition và offset.
- Consumer lag theo partition.
- Số record nhận và xử lý thành công.
- Processing latency p95/p99.
- Commit latency và commit failure.
- Retry count, DLT count.
- Rebalance count và thời gian rebalance.
- Consumer poll interval và heartbeat health.
- Số child container đang chạy.

Có thể dùng kafka-consumer-groups CLI:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
~~~

Đối chiếu member, assignment, current offset, log end offset và lag. Tên metric JMX hoặc Micrometer phụ thuộc phiên bản Kafka client, Spring Kafka và exporter đang dùng.

### 18.1. clientIdPrefix giúp tìm consumer instance

Nếu listener concurrency lớn, đặt clientIdPrefix có thể giúp phân biệt từng consumer instance trong log và metric.

~~~java
@KafkaListener(
    id = "order-listener",
    clientIdPrefix = "order-worker",
    topics = "order-events",
    groupId = "order-service",
    concurrency = "3"
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

Theo dõi từng client giúp xác định instance nào có poll chậm, xử lý lâu hoặc lag cao.

## 19. Kiểm thử @KafkaListener

Không nên chỉ kiểm tra listener bằng cách gọi trực tiếp method. Cần kiểm thử cả việc publish record, deserialize, container nhận record và side effect được thực hiện.

### 19.1. Kiểm thử với EmbeddedKafka

Spring Kafka cung cấp spring-kafka-test và EmbeddedKafka để chạy broker nhúng trong test.

Ví dụ dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Một test có thể dùng @EmbeddedKafka và KafkaTemplate để gửi event, sau đó đợi listener cập nhật kết quả.

~~~java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = {"order-events"}
)
class OrderListenerTest {

    @Autowired
    private KafkaTemplate<String, OrderEvent> kafkaTemplate;

    @Autowired
    private OrderRepository repository;

    @Test
    void shouldProcessOrderEvent() {
        OrderEvent event = new OrderEvent(
            "evt-1",
            "order-42",
            "CREATED"
        );

        kafkaTemplate.send(
            "order-events",
            event.orderId(),
            event
        );

        await().atMost(Duration.ofSeconds(10))
            .untilAsserted(() ->
                assertThat(repository.existsById("order-42"))
                    .isTrue()
            );
    }
}
~~~

Đây là ví dụ minh họa; cần cung cấp bean, serializer, repository và thư viện awaitility phù hợp project. Không dùng Thread.sleep dài để đồng bộ test nếu có thể chờ theo điều kiện.

### 19.2. Kiểm thử với Testcontainers

Testcontainers hữu ích khi cần kiểm thử với Kafka broker thật trong container và cấu hình gần production hơn. Test nên xác minh:

- Group ID và assignment.
- Deserialization của key/value.
- Record listener và batch listener.
- Ack mode và offset sau restart.
- Retry và DLT.
- Rebalance khi consumer dừng.
- Concurrency với nhiều partition.
- Transactional listener nếu ứng dụng dùng Kafka transaction.

EmbeddedKafka nhanh cho test tích hợp trong process; Testcontainers hữu ích khi cần kiểm tra hành vi broker và môi trường container thực tế.

## 20. Ví dụ tổng hợp: Order listener theo record và group

Một cấu hình cơ bản gồm application properties:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.OrderEvent
        spring.json.trusted.packages: com.example.orders
    listener:
      concurrency: 3
      ack-mode: record
~~~

Listener:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "order-listener",
        topics = "order-events",
        groupId = "order-service",
        clientIdPrefix = "order-consumer"
    )
    public void onMessage(
            ConsumerRecord<String, OrderEvent> record) {

        orderService.process(
            record.key(),
            record.value()
        );
    }
}
~~~

Với topic có sáu partition và concurrency bằng ba, group có thể gán khoảng hai partition cho mỗi consumer khi assignment cân bằng. Các event cùng key đi cùng partition nếu producer dùng cùng key bytes và partitioning rule. Listener xử lý tuần tự trên từng consumer thread; không có thứ tự tổng thể giữa các partition.

Nếu cần concurrency khác cho một endpoint, khai báo thuộc tính concurrency trên @KafkaListener hoặc tạo container factory riêng.

## 21. Các lỗi cấu hình thường gặp

- **Không chỉ định group ID:** consumer có thể thiếu group.id và không tham gia group theo cách mong muốn.
- **Nhầm id với groupId:** id dùng quản lý endpoint; groupId xác định consumer group.
- **Tăng concurrency vượt partition count:** consumer dư không làm tăng mức song song của topic.
- **Dùng sai containerFactory:** listener nhận kiểu dữ liệu không khớp deserializer hoặc batch mode.
- **Bật batch listener nhưng method chỉ nhận một payload:** listener signature không tương thích.
- **Commit offset trước side effect:** crash có thể làm mất xử lý nghiệp vụ.
- **Bật auto commit ngoài ý muốn:** offset có thể tiến trước khi listener hoàn tất.
- **Không cấu hình ErrorHandlingDeserializer:** lỗi deserialize xảy ra trước listener và không đi qua error flow mong muốn.
- **Dùng chung group ID cho hai ứng dụng cần đọc độc lập:** hai ứng dụng chia partition thay vì mỗi ứng dụng nhận toàn bộ luồng.
- **Retry vô hạn:** một record lỗi có thể chặn partition và làm lag tăng.
- **Dùng topicPattern quá rộng:** listener có thể subscribe nhầm topic nội bộ hoặc DLT.
- **Tạo topic với replication factor lớn hơn số broker:** topic creation thất bại.
- **Gọi KafkaConsumer từ thread ngoài container:** vi phạm thread-safety và lifecycle.
- **Không theo dõi rebalance:** deployment hoặc autoscaling có thể làm group gián đoạn thường xuyên.

## 22. Checklist trước khi đưa listener lên production

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Dependency | Spring Boot và Spring Kafka version có tương thích không? |
| Annotation | @EnableKafka hoặc annotation infrastructure đã được bật chưa? |
| ConsumerFactory | Bootstrap, deserializer, security và group properties đúng chưa? |
| Container factory | Record/batch mode và error handler có đúng không? |
| Listener | Method signature có khớp payload và metadata cần dùng không? |
| Group ID | Các service cần đọc độc lập đã dùng group riêng chưa? |
| Concurrency | Số consumer có phù hợp partition count và downstream capacity không? |
| Offset | Ack mode và auto commit có phù hợp side effect không? |
| Retry | Exception được phân loại, retry hữu hạn và DLT có chưa? |
| Ordering | Key và listener concurrency có giữ yêu cầu thứ tự không? |
| Lifecycle | Có pause/resume và shutdown behavior phù hợp không? |
| Monitoring | Có lag, processing latency, rebalance và DLT alert không? |
| Testing | Có test deserialize, offset, retry, concurrency và restart không? |

## 23. Kết luận

@KafkaListener là điểm khai báo xử lý record; listener container thực hiện poll và quản lý consumer lifecycle; container factory định nghĩa cách tạo container, concurrency, acknowledgment và error handling. Consumer group quyết định các instance chia partition và lưu tiến độ đọc độc lập với group khác.

Khi thiết kế, hãy phân biệt listener ID với group ID, chọn record hoặc batch listener phù hợp, đặt concurrency theo partition count, tắt auto commit nếu container quản lý offset và chỉ xác nhận record sau khi side effect hoàn tất. Với lỗi, cấu hình error handler và DLT có giới hạn; với vận hành, theo dõi lag, rebalance và processing latency.

Một listener production-ready cần được kiểm thử như một luồng tích hợp hoàn chỉnh: producer gửi record, serializer/deserializer tạo đúng kiểu, container gọi listener, nghiệp vụ hoàn tất, offset được commit và lỗi được phục hồi theo chính sách.

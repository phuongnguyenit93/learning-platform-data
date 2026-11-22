# ConsumerFactory và listener container

Trong Spring Kafka, consumer không thường được tạo và điều khiển trực tiếp bên trong phương thức xử lý nghiệp vụ. Spring Kafka cung cấp hai thành phần phối hợp để quản lý vòng đời đó: **ConsumerFactory** tạo Kafka Consumer với cấu hình phù hợp, còn **listener container** sở hữu consumer, chạy vòng lặp poll, chuyển record tới listener và điều phối commit offset, rebalance, lỗi cũng như dừng ứng dụng.

Hiểu rõ hai thành phần này giúp cấu hình consumer group nhất quán, điều chỉnh concurrency theo số partition, chọn cách commit offset phù hợp và xử lý lỗi mà không làm mất message. Đây là nền tảng của chương Consumer bền vững trong Spring Kafka.

## 1. Vai trò của ConsumerFactory và listener container

Hai thành phần có trách nhiệm khác nhau:

- **ConsumerFactory** là factory tạo các đối tượng Kafka Consumer. Nó cung cấp bootstrap servers, group settings, deserializer và những thuộc tính Kafka client khác.
- **Listener container** quản lý một hoặc nhiều Kafka Consumer. Container khởi tạo consumer từ ConsumerFactory, gọi poll(), phân phối record cho listener, điều phối acknowledgment và quản lý vòng đời của consumer.
- **Message listener** là phần code nghiệp vụ nhận record hoặc batch record. Listener không tự sở hữu vòng lặp poll.

Luồng hoạt động khái quát:

    Spring application context
             |
             v
    ConcurrentKafkaListenerContainerFactory
             |
             | tạo listener container
             v
    ConcurrentMessageListenerContainer
             |
             | quản lý các child container
             v
    KafkaMessageListenerContainer
             |
             | tạo Kafka Consumer qua ConsumerFactory
             v
    Kafka Consumer
             |
             | poll records
             v
    Message listener
             |
             | xử lý nghiệp vụ / acknowledge
             v
    Container quản lý commit offset

Factory dành cho listener container và ConsumerFactory là hai factory ở hai tầng khác nhau. ConcurrentKafkaListenerContainerFactory không trực tiếp tạo KafkaConsumer; nó dùng ConsumerFactory đã được cấu hình để tạo container, sau đó container mới tạo consumer khi khởi động.

## 2. ConsumerFactory tạo Kafka Consumer như thế nào?

ConsumerFactory định nghĩa cách tạo Kafka Consumer cho các container. Trong cấu hình phổ biến, Spring Kafka dùng DefaultKafkaConsumerFactory. Factory này nhận một map cấu hình và các deserializer, sau đó tạo Kafka Consumer mới mỗi khi container cần consumer.

Ví dụ tạo ConsumerFactory cho key dạng String và value là JSON được chuyển thành OrderCreated:

~~~java
@Bean
public ConsumerFactory<String, OrderCreated> consumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    JsonDeserializer<OrderCreated> valueDeserializer =
            new JsonDeserializer<>(OrderCreated.class);

    valueDeserializer.addTrustedPackages("com.example.orders");

    return new DefaultKafkaConsumerFactory<>(
            props,
            new StringDeserializer(),
            valueDeserializer
    );
}
~~~

Đây là ví dụ minh họa; trong production, bootstrap servers và các thông tin bảo mật nên lấy từ cấu hình môi trường hoặc secret store. Chỉ thêm package tin cậy cần thiết cho JSON deserializer. Không mở rộng trusted packages tùy tiện khi dữ liệu đến từ nguồn không tin cậy.

ConsumerFactory không phải một Kafka Consumer dùng chung cho mọi listener. Mỗi container hoặc child container tạo consumer riêng. Một Kafka Consumer không thread-safe; không chia sẻ cùng một consumer instance cho nhiều luồng xử lý nghiệp vụ.

### 2.1. Các nhóm thuộc tính consumer quan trọng

| Thuộc tính | Mục đích | Lưu ý vận hành |
|---|---|---|
| bootstrap.servers | Danh sách broker để client kết nối ban đầu | Nên cấu hình nhiều địa chỉ broker có thể truy cập |
| group.id | Tên consumer group | Listener có thể ghi đè group ID ở cấp annotation |
| key/value.deserializer | Chuyển byte thành kiểu dữ liệu ứng dụng | Phải tương thích với serializer của producer |
| enable.auto.commit | Bật/tắt commit offset tự động của Kafka client | Thường tắt để container quản lý acknowledgment |
| auto.offset.reset | Hành vi khi group không có offset hợp lệ | earliest và latest có thể dẫn đến phạm vi dữ liệu đọc khác nhau |
| max.poll.records | Số record tối đa trả về trong một lần poll | Ảnh hưởng thời gian xử lý một batch và commit |
| max.poll.interval.ms | Khoảng tối đa giữa các lần poll trước khi group xem consumer không còn hoạt động | Phải phù hợp với thời gian xử lý dài nhất |
| session.timeout.ms | Thời gian phát hiện consumer mất kết nối trong group protocol | Phối hợp với heartbeat và cấu hình broker |
| isolation.level | Cách đọc record transactional | read_committed bỏ qua record thuộc transaction chưa commit |
| fetch.min.bytes / fetch.max.wait.ms | Điều kiện gom dữ liệu khi fetch | Có thể ảnh hưởng latency và throughput |

Không nên sao chép mọi thuộc tính từ một cấu hình mẫu mà không hiểu tác động. Ví dụ, tăng max.poll.records có thể tăng throughput nếu listener xử lý nhanh, nhưng cũng làm một poll batch mất nhiều thời gian hơn và tăng nguy cơ vượt max.poll.interval.ms.

### 2.2. Tắt auto commit khi container quản lý offset

Khi dùng Spring Kafka listener container, nên để container điều phối commit offset. Cấu hình consumer thường đặt enable.auto.commit=false. Khi đó, acknowledgment mode của container quyết định thời điểm commit.

Nếu bật auto commit, Kafka client có thể commit theo lịch trong khi listener chưa hoàn tất xử lý. Khi consumer lỗi giữa chừng, offset đã tiến lên có thể khiến record chưa được xử lý bị bỏ qua. Với hệ thống cần at-least-once, tắt auto commit và commit sau xử lý thành công là cách tiếp cận phổ biến.

Spring Kafka container có thể tự đặt auto commit thành false nếu thuộc tính chưa được cấu hình, tùy phiên bản và cách tạo ConsumerFactory. Dù vậy, khai báo rõ ràng giúp cấu hình dễ đọc và tránh phụ thuộc vào mặc định.

### 2.3. Deserializer và kiểu dữ liệu

Deserializer là một phần của cấu hình ConsumerFactory. Nếu producer gửi JSON nhưng consumer dùng StringDeserializer cho value, ứng dụng sẽ nhận chuỗi JSON và phải tự chuyển đổi. Nếu dùng JsonDeserializer, Spring Kafka có thể chuyển payload thành kiểu Java đã định.

Hãy thống nhất schema, type mapping và trusted packages giữa các producer/consumer. Lỗi deserialize xảy ra trước khi listener nhận được đối tượng nghiệp vụ thông thường; vì vậy, cần cấu hình ErrorHandlingDeserializer khi muốn chuyển lỗi deserialize tới cơ chế xử lý lỗi của container.

Ví dụ cấu hình ErrorHandlingDeserializer với JSON value:

~~~java
props.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    ErrorHandlingDeserializer.class
);
props.put(
    ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS,
    JsonDeserializer.class
);
~~~

Cách cấu hình delegate và target type cần khớp với phiên bản Spring Kafka, serializer và schema của ứng dụng. Không giả định mọi lỗi dữ liệu đều xuất hiện dưới dạng exception trong listener; lỗi ở tầng deserialize cần được chuyển tiếp theo cấu hình tương ứng.

## 3. Listener container làm gì?

Listener container là thành phần điều khiển vòng đời của consumer. Container tạo consumer, subscribe topic hoặc assign partition, chạy vòng lặp poll, gọi listener, quản lý acknowledgment, commit offset và phối hợp với consumer group khi rebalance.

Spring Kafka có hai loại container cơ bản:

- **KafkaMessageListenerContainer** quản lý một Kafka Consumer và xử lý record trên một luồng consumer.
- **ConcurrentMessageListenerContainer** quản lý nhiều KafkaMessageListenerContainer con. Mỗi child container có consumer và luồng riêng.

ConcurrentMessageListenerContainer thường được tạo thông qua ConcurrentKafkaListenerContainerFactory. Khi concurrency bằng 3, factory tạo một container cha quản lý ba child container; mỗi child sở hữu một consumer.

Sơ đồ:

    ConcurrentMessageListenerContainer
       |
       +-- child container 1 --> Consumer 1 --> poll/listener thread 1
       |
       +-- child container 2 --> Consumer 2 --> poll/listener thread 2
       |
       +-- child container 3 --> Consumer 3 --> poll/listener thread 3

Các consumer thuộc cùng group sẽ chia partition của topic theo cơ chế group assignment. Một partition chỉ được gán cho tối đa một consumer trong cùng group tại một thời điểm. Nếu số consumer lớn hơn số partition, một số consumer sẽ không có partition để đọc.

## 4. Cấu hình ConcurrentKafkaListenerContainerFactory

ConcurrentKafkaListenerContainerFactory là factory thường được dùng với annotation @KafkaListener. Nó kết hợp ConsumerFactory với các thuộc tính mặc định của listener container như concurrency, acknowledgment mode, error handler và batch listener.

Ví dụ cấu hình một factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                CommonErrorHandler commonErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.setCommonErrorHandler(commonErrorHandler);

    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

Tên bean mặc định thường dùng trong cấu hình @KafkaListener là kafkaListenerContainerFactory. Nếu ứng dụng có nhiều loại listener, có thể tạo nhiều factory với tên khác nhau và chọn bằng thuộc tính containerFactory trên annotation.

Ví dụ listener dùng factory riêng:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-service",
    containerFactory = "orderListenerContainerFactory"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

Factory không phải nơi viết logic xử lý message. Nó định nghĩa cách container được tạo. Listener vẫn là phương thức nhận message và gọi service nghiệp vụ.

### 4.1. Dùng cấu hình tự động của Spring Boot

Spring Boot có thể tự tạo ConsumerFactory và ConcurrentKafkaListenerContainerFactory mặc định từ các thuộc tính spring.kafka. Ví dụ:

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
        spring.json.value.default.type: com.example.orders.OrderCreated
        spring.json.trusted.packages: com.example.orders
    listener:
      ack-mode: record
      concurrency: 3
~~~

Các thuộc tính trên là ví dụ minh họa. Hãy kiểm tra phiên bản Spring Boot/Spring Kafka và cấu hình thực tế của ứng dụng. Khi tự khai báo một bean factory cùng tên với bean mặc định, ứng dụng có thể thay thế hoặc làm thay đổi quá trình auto-configuration. Đừng vừa khai báo factory thủ công vừa giả định mọi thuộc tính tự động vẫn được áp dụng giống hệt.

### 4.2. Nhiều factory cho nhiều kiểu listener

Một ứng dụng có thể có listener record thông thường, listener batch hoặc listener dùng transaction riêng. Khi cần chính sách khác nhau, tạo các factory có tên rõ ràng:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}

@Bean
public ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
        auditBatchListenerContainerFactory(
                ConsumerFactory<String, AuditEvent> auditConsumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, AuditEvent>();

    factory.setConsumerFactory(auditConsumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(2);

    return factory;
}
~~~

Listener batch chọn factory tương ứng:

~~~java
@KafkaListener(
    topics = "audit.events",
    containerFactory = "auditBatchListenerContainerFactory"
)
public void consumeBatch(List<AuditEvent> events) {
    auditService.processBatch(events);
}
~~~

Các factory có thể chia sẻ một số cấu hình, nhưng ConsumerFactory phải có deserializer phù hợp với kiểu dữ liệu và topic tương ứng. Không dùng chung một factory chỉ vì hai listener cùng kết nối một cluster nếu chúng cần kiểu dữ liệu hoặc semantics xử lý khác nhau.

## 5. @KafkaListener và container được tạo ra

Khi Spring khởi động và phát hiện phương thức có @KafkaListener, KafkaListenerAnnotationBeanPostProcessor xử lý annotation và đăng ký endpoint với KafkaListenerEndpointRegistry. Registry sử dụng container factory được chỉ định để tạo listener container.

Quá trình khái quát:

1. Spring tạo bean có phương thức @KafkaListener.
2. Annotation processor phát hiện endpoint và đọc topic, group ID, concurrency, containerFactory cùng các thuộc tính khác.
3. Endpoint được đăng ký với KafkaListenerEndpointRegistry.
4. Registry dùng factory để tạo listener container.
5. Container khởi động, tạo consumer qua ConsumerFactory và bắt đầu poll.
6. Record được chuyển tới phương thức listener.

Ví dụ:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "order-created-listener",
        topics = "orders.created",
        groupId = "order-service"
    )
    public void onOrderCreated(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

Ở đây, phương thức onOrderCreated là message listener. Container đảm nhận việc lấy record và gọi phương thức. Không cần tự tạo KafkaConsumer hoặc viết vòng lặp poll trong listener.

### 5.1. Chọn group ID

group.id xác định nhóm consumer phối hợp đọc partition và lưu offset. Các instance cùng group chia nhau partition. Các group khác nhau đọc độc lập từ cùng topic và có offset riêng.

Group ID có thể đặt trong cấu hình ConsumerFactory hoặc ghi đè ở annotation @KafkaListener. Nếu một listener cần group khác với listener khác, hãy khai báo rõ group ID để tránh vô tình dùng chung offset và assignment.

### 5.2. Chọn topic, topic pattern hoặc partition cụ thể

Listener có thể subscribe theo tên topic, pattern hoặc gán partition cụ thể. Subscribe theo topic cho phép Kafka group coordinator phân phối partition. Gán partition tường minh phù hợp với một số tác vụ có phạm vi cố định nhưng cần hiểu rằng cách assign này không giống cơ chế subscribe và rebalance tự động thông thường.

Ví dụ gán partition cụ thể:

~~~java
@KafkaListener(
    topicPartitions = @TopicPartition(
        topic = "orders.created",
        partitions = { "0", "1" }
    ),
    groupId = "order-replay"
)
public void replay(OrderCreated event) {
    replayService.process(event);
}
~~~

Khi dùng partition assignment tường minh, cần quản lý phạm vi partition và khả năng mở rộng topic cẩn thận. Không nên hard-code partition trong ứng dụng production nếu số partition có thể thay đổi mà không có quy trình cập nhật tương ứng.

## 6. Điều chỉnh concurrency theo partition

Concurrency là số consumer thread mà ConcurrentMessageListenerContainer quản lý. Mỗi child container tạo một Kafka Consumer riêng. Tăng concurrency có thể tăng khả năng xử lý song song, nhưng chỉ có tác dụng khi topic có đủ partition và hệ thống downstream có đủ năng lực.

Ví dụ topic có 6 partition:

| Concurrency | Consumer có partition | Tác động |
|---:|---:|---|
| 1 | 1 consumer nhận 6 partition | Một luồng xử lý; ít song song |
| 3 | 3 consumer chia 6 partition | Có thể xử lý tối đa 3 luồng song song |
| 6 | 6 consumer, mỗi consumer có thể nhận 1 partition | Có thể tận dụng hết partition song song |
| 8 | Tối đa 6 consumer nhận partition | Ít nhất 2 consumer không có partition |

Số partition, số consumer trong group và cách assign partition quyết định mức song song thực tế. Nếu một partition có record chậm, consumer xử lý partition đó có thể trở thành điểm nghẽn. Tăng concurrency vượt số partition không làm một partition được xử lý đồng thời bởi nhiều consumer trong cùng group.

Có thể cấu hình concurrency ở factory:

~~~java
factory.setConcurrency(4);
~~~

Hoặc ghi đè cho một listener:

~~~java
@KafkaListener(
    id = "order-listener",
    topics = "orders.created",
    groupId = "order-service",
    concurrency = "4"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

Concurrency của annotation là thuộc tính riêng cho endpoint đó. Hãy kiểm tra tổng số consumer trên toàn bộ instance ứng dụng: nếu có 3 instance và mỗi instance concurrency 4, group có thể có tổng cộng 12 consumer. Số consumer này phải được đối chiếu với partition count.

### 6.1. Thứ tự record và partition

Kafka bảo đảm thứ tự record trong một partition. Consumer group gán mỗi partition cho tối đa một consumer tại một thời điểm, nên các record trong partition được đưa tới một consumer theo thứ tự offset.

Tuy nhiên, nếu listener xử lý bất đồng bộ rồi trả về trước khi công việc hoàn tất, thứ tự hoàn tất side effect có thể khác thứ tự nhận record. Tương tự, tăng concurrency không đảm bảo thứ tự toàn cục giữa các partition.

Nếu nghiệp vụ cần thứ tự theo orderId, producer nên dùng orderId làm key để các record của cùng order được định tuyến vào cùng partition. Consumer xử lý tuần tự trong partition hoặc áp dụng kiểm soát version/sequence khi xử lý bất đồng bộ.

### 6.2. Rebalance khi thay đổi số consumer

Khi consumer tham gia/rời group hoặc topic partition thay đổi, Kafka thực hiện rebalance để phân phối lại partition. Trong thời gian rebalance, việc xử lý có thể tạm gián đoạn. Listener container phối hợp với consumer group và xử lý các callback/revoke assignment theo lifecycle.

Khi tăng concurrency hoặc triển khai thêm instance, hãy quan sát số lần rebalance, thời gian rebalance và consumer lag. Khởi động đồng loạt nhiều consumer hoặc cấu hình poll không phù hợp có thể gây dao động assignment và làm tăng độ trễ.

## 7. Acknowledgment mode và commit offset

Container quyết định thời điểm commit offset thông qua AckMode. Đây là một trong những cấu hình quan trọng nhất để kiểm soát khả năng phát lại và nguy cơ mất message.

Một số chế độ phổ biến:

| AckMode | Thời điểm commit | Tình huống |
|---|---|---|
| RECORD | Sau khi listener xử lý thành công từng record | Listener record, cần ranh giới commit theo record |
| BATCH | Sau khi tất cả record trong poll batch được xử lý thành công | Mặc định phổ biến cho container record listener |
| TIME | Khi đủ thời gian cấu hình và các điều kiện xử lý của container được đáp ứng | Gom commit theo thời gian |
| COUNT | Khi đạt số record cấu hình | Gom commit theo số lượng |
| COUNT_TIME | Kết hợp điều kiện thời gian và số record | Cân bằng tần suất commit |
| MANUAL | Listener chủ động acknowledge; container điều phối commit | Ứng dụng kiểm soát thời điểm xác nhận |
| MANUAL_IMMEDIATE | Acknowledge có thể commit ngay khi gọi trên consumer thread | Cần kiểm soát chặt thread gọi acknowledge |

Với AckMode.RECORD, container commit offset sau khi listener hoàn tất thành công record. Với BATCH, commit được thực hiện sau khi các record của lần poll được xử lý thành công. Nếu một record lỗi và không được phục hồi, error handler quyết định cách xử lý tiếp; không nên giả định offset của cả batch sẽ tự động được commit.

Ví dụ cấu hình RECORD:

~~~java
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.RECORD);
~~~

Cấu hình trong Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

### 7.1. Manual acknowledgment

Khi listener cần quyết định thời điểm xác nhận, có thể nhận tham số Acknowledgment:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-service"
)
public void consume(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    orderService.process(event);
    acknowledgment.acknowledge();
}
~~~

Chỉ gọi acknowledge() sau khi tác vụ nghiệp vụ đã hoàn tất bền vững. Nếu listener ACK trước database commit rồi transaction database thất bại, offset có thể tiến lên và record không được giao lại.

Với MANUAL, container nhận acknowledgment và điều phối commit theo semantics của chế độ này. Với MANUAL_IMMEDIATE, commit có thể diễn ra ngay nếu acknowledge được gọi trên consumer thread. Nếu gọi acknowledgment từ một thread khác, hành vi có thể được xếp hàng để consumer thread xử lý. Vì vậy, không nên chuyển Acknowledgment sang executor tùy tiện mà không hiểu giới hạn thread và commit mode.

### 7.2. Commit sync và async

Container có thể dùng synchronous hoặc asynchronous commit tùy cấu hình. Synchronous commit chờ broker phản hồi, dễ quan sát lỗi commit nhưng có thể tăng độ trễ. Asynchronous commit giảm thời gian chờ nhưng lỗi commit cần được xử lý qua callback/logging và có thể khó quan sát hơn.

Thuộc tính syncCommits và commit callback của container có thể được dùng để điều chỉnh cách commit. Việc lựa chọn phải dựa trên latency, throughput và yêu cầu độ bền. Dù chọn cách nào, thiết kế consumer vẫn phải chấp nhận khả năng record được giao lại nếu side effect đã hoàn tất nhưng offset chưa được commit.

## 8. Record listener và batch listener

Container có thể gọi listener một record mỗi lần hoặc chuyển cả batch record từ poll tới listener.

**Record listener** nhận một record:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

**Batch listener** nhận danh sách record:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consumeBatch(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

Để cấu hình batch listener, factory bật batch mode:

~~~java
factory.setBatchListener(true);
~~~

Batch listener có thể giảm overhead gọi phương thức và tận dụng xử lý theo lô ở database. Đổi lại, một batch có thể chứa nhiều record và thời gian xử lý lâu hơn. Hãy điều chỉnh max.poll.records, max.poll.interval.ms và giới hạn kích thước batch theo năng lực downstream.

Khi một record trong batch thất bại, cách xác định record lỗi và xử lý phần còn lại phức tạp hơn record listener. Error handler có thể dùng thông tin về index/record lỗi nếu listener ném BatchListenerFailedException theo cách Spring Kafka hỗ trợ. Hãy thiết kế batch operation có khả năng rollback hoặc idempotent để tránh cập nhật một phần khó khôi phục.

Không chuyển sang batch mode chỉ để tăng throughput mà chưa đánh giá semantics lỗi, transaction database và khả năng xử lý từng record.

## 9. Error handler gắn với listener container

Listener container là nơi nhận exception từ listener và chuyển cho cơ chế xử lý lỗi. Trong Spring Kafka hiện đại, CommonErrorHandler là abstraction chung; DefaultErrorHandler là implementation thường dùng cho record listener và hỗ trợ retry/backoff cùng recoverer.

Ví dụ cấu hình error handler với DeadLetterPublishingRecoverer:

~~~java
@Bean
public CommonErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 3L)
            );

    handler.addNotRetryableExceptions(
            IllegalArgumentException.class
    );

    return handler;
}
~~~

Sau đó gắn handler vào factory:

~~~java
factory.setCommonErrorHandler(commonErrorHandler);
~~~

Ví dụ minh họa cần được điều chỉnh theo serializer, topic DLT và phiên bản Spring Kafka. Recoverer mặc định thường định tuyến record tới topic có hậu tố .DLT và giữ partition tương ứng; hãy bảo đảm topic đích tồn tại và có đủ partition cho cách định tuyến đó.

Error handler có thể retry lỗi tạm thời, bỏ qua/recover lỗi không thể retry hoặc chuyển record sang DLT. Cần đặt giới hạn số lần thử và backoff. Retry blocking có thể giữ partition trong thời gian chờ; retry topic phù hợp khi cần trì hoãn lâu hơn nhưng có thể thay đổi thứ tự xử lý.

Lỗi deserialize xảy ra trước khi listener nhận được object thông thường. Dùng ErrorHandlingDeserializer để chuyển thông tin lỗi deserialize vào cơ chế xử lý lỗi của container. Nếu không cấu hình đúng, lỗi deserialize có thể khiến consumer không thể tiếp tục theo cách mong muốn.

## 10. Container lifecycle và KafkaListenerEndpointRegistry

Container có vòng đời riêng: start, pause, resume và stop. Với @KafkaListener, Spring thường đăng ký container trong KafkaListenerEndpointRegistry. Registry cho phép ứng dụng tìm và điều khiển container theo ID.

Ví dụ dừng và khởi động lại một listener:

~~~java
@Component
public class ListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrderListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("order-created-listener");

        if (container != null) {
            container.pause();
        }
    }

    public void resumeOrderListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("order-created-listener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

Listener cần có id tương ứng:

~~~java
@KafkaListener(
    id = "order-created-listener",
    topics = "orders.created",
    groupId = "order-service"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

Pause và resume có thể hữu ích khi bảo trì hoặc khi downstream cần giảm tải. Container thực hiện pause/resume theo cơ chế consumer thread an toàn. Không gọi trực tiếp KafkaConsumer.pause(), poll() hoặc commitSync() từ một thread nghiệp vụ khác; Kafka Consumer không thread-safe và container sở hữu vòng đời consumer.

Các thuộc tính autoStartup và id trên @KafkaListener cho phép điều khiển listener có khởi động cùng application context hay không và định danh container. Với container được tạo thủ công, ứng dụng có thể quản lý lifecycle trực tiếp. Đối với container annotation, nên dùng registry thay vì giữ reference tới consumer.

## 11. Container properties và giới hạn poll

Ngoài acknowledgment mode, ContainerProperties cung cấp nhiều thiết lập vận hành:

- pollTimeout: thời gian chờ dữ liệu trong mỗi lần poll.
- idleBetweenPolls: khoảng nghỉ giữa các lần poll trong một số tình huống.
- syncCommits: lựa chọn synchronous commit.
- ackMode: chính sách acknowledgment.
- shutdownTimeout: thời gian chờ container dừng hoàn tất.
- monitorInterval và noPollThreshold: hỗ trợ phát hiện container không poll theo ngưỡng cấu hình.
- missingTopicsFatal: hành vi khi topic được yêu cầu chưa tồn tại, tùy phiên bản/cấu hình.

Ví dụ:

~~~java
ContainerProperties properties = factory.getContainerProperties();
properties.setPollTimeout(3_000);
properties.setSyncCommits(true);
properties.setShutdownTimeout(15_000);
properties.setAckMode(ContainerProperties.AckMode.RECORD);
~~~

Không phải mọi thuộc tính đều cần tùy chỉnh. Giữ mặc định phù hợp thường dễ vận hành hơn. Chỉ thay đổi khi có mục tiêu cụ thể và đo được.

### 11.1. max.poll.interval.ms và thời gian xử lý

Kafka yêu cầu consumer tiếp tục poll trong giới hạn max.poll.interval.ms. Nếu listener xử lý một batch quá lâu và container không poll lại trong thời hạn này, group có thể xem consumer không còn hoạt động và rebalance partition.

Ví dụ, nếu max.poll.records là 500 và mỗi record mất trung bình 100 ms, thời gian xử lý lý thuyết của một batch đã có thể lên tới 50 giây, chưa tính thời gian database hoặc mạng. Nếu max.poll.interval.ms nhỏ hơn tổng thời gian xử lý thực tế, consumer có thể liên tục bị loại khỏi group.

Cần đánh giá phân phối thời gian xử lý, không chỉ thời gian trung bình. Một số record có thể gọi dịch vụ chậm hoặc cần retry. Điều chỉnh max.poll.records, max.poll.interval.ms, concurrency và thiết kế batch để giữ poll cadence ổn định.

### 11.2. Consumer lag và tốc độ xử lý

Consumer lag là khoảng cách giữa offset mới nhất của partition và offset mà group đã commit. Lag tăng có thể do producer gửi nhanh hơn consumer xử lý, downstream chậm, concurrency thấp, rebalance lặp hoặc lỗi retry.

Tăng concurrency có thể giúp nếu còn partition chưa được khai thác và downstream đủ khả năng xử lý. Nếu mọi partition đã có consumer, cần tối ưu thời gian xử lý, fetch/batch, database hoặc dịch vụ phụ thuộc. Tăng concurrency vượt số partition không làm giảm lag một cách tự động.

## 12. Transaction và listener container

Spring Kafka hỗ trợ listener container tham gia Kafka transaction. Khi container được cấu hình với transaction manager phù hợp, việc xử lý record và gửi các record Kafka đầu ra có thể nằm trong một transaction Kafka. Offset đầu vào có thể được gửi cùng transaction để đảm bảo consume-process-produce có tính nguyên tử trong phạm vi Kafka.

Khi transaction commit, record đầu ra và offset được commit cùng nhau. Khi transaction abort, record đầu ra không hiển thị với consumer read_committed và offset đầu vào không được tiến lên như một lần xử lý thành công.

Transaction container không tự bao trùm database hoặc HTTP API. Nếu listener cập nhật database rồi gửi Kafka, cần outbox/inbox hoặc một cách phối hợp phù hợp. Nếu database commit xong nhưng Kafka transaction abort, side effect database vẫn tồn tại và record có thể được giao lại.

Cấu hình transaction manager và listener container thay đổi theo phiên bản Spring Kafka và loại transaction được sử dụng. Hãy dùng đúng API của dependency hiện tại; không sao chép cấu hình transaction từ một phiên bản khác mà chưa kiểm tra.

## 13. Tùy biến container và quan sát

Khi cần áp dụng một chính sách chung cho container được tạo từ factory, có thể dùng container customizer hoặc các điểm mở rộng tương ứng của phiên bản Spring Kafka.

Ví dụ ý tưởng dùng customizer để gắn thuộc tính theo container:

~~~java
factory.setContainerCustomizer(container -> {
    log.info("Creating Kafka listener container: {}", container);
});
~~~

Tùy phiên bản, API customizer và thời điểm callback có thể khác nhau. Dùng customizer cho cấu hình hạ tầng chung như metric, event listener hoặc thuộc tính container; không nhồi logic nghiệp vụ vào factory.

Nên quan sát các chỉ số:

| Nhóm | Tín hiệu cần theo dõi |
|---|---|
| Consumer group | Lag, số member, partition assignment và rebalance |
| Listener container | Trạng thái running, pause/resume, thời gian poll |
| Xử lý nghiệp vụ | Throughput, thời gian xử lý, exception rate |
| Commit | Commit latency, commit failure và số lần giao lại |
| Retry/DLT | Số record retry, DLT, tuổi record lỗi |
| Broker/client | Fetch latency, request error, network và heartbeat |

Log nên có topic, partition, offset, key, group ID và eventId để truy vết. Tránh ghi payload nhạy cảm. Một container đang chạy không đồng nghĩa nó đang xử lý record; cần đối chiếu lag, poll activity và throughput.

## 14. Các lỗi cấu hình thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng nhầm ConsumerFactory cho kiểu payload khác | Deserialize lỗi hoặc listener nhận kiểu không mong đợi | Tạo factory với deserializer đúng |
| Nghĩ ConcurrentKafkaListenerContainerFactory trực tiếp tạo KafkaConsumer | Hiểu sai lifecycle và quản lý thread | Container tạo consumer thông qua ConsumerFactory |
| Đặt concurrency lớn hơn partition count | Có consumer không nhận partition | Chọn concurrency theo partition và số instance |
| Bật auto commit trong khi listener xử lý lâu | Offset có thể tiến trước khi nghiệp vụ hoàn tất | Tắt auto commit và chọn AckMode |
| ACK trước khi database commit | Có thể mất tác vụ khi database lỗi | ACK sau khi side effect bền vững |
| Listener xử lý quá lâu so với max.poll.interval.ms | Rebalance và giao lại record | Điều chỉnh poll, batch, timeout và xử lý |
| Gọi KafkaConsumer từ thread ngoài container | Vi phạm thread-safety | Dùng API container/registry |
| Retry vô hạn trong error handler | Partition có thể bị chặn và lag tăng | Backoff hữu hạn, phân loại lỗi và DLT |
| Chọn batch listener nhưng không thiết kế lỗi từng record | Khó xác định phần nào đã xử lý | Thiết kế transaction/idempotency và batch error handling |
| Dùng group ID chung ngoài ý muốn | Listener chia partition và offset với nhau | Đặt group ID theo mục đích xử lý |
| Coi consumer lag bằng 0 là bằng chứng không mất message | Offset có thể đã commit quá sớm | Đối chiếu kết quả nghiệp vụ và nguồn event |

## 15. Cấu hình tham khảo cho một listener production

Ví dụ dưới đây kết hợp ConsumerFactory, ConcurrentKafkaListenerContainerFactory và một listener record. Các giá trị concurrency, poll và acknowledgment phải được điều chỉnh theo partition count, thời gian xử lý và SLA.

~~~java
@Configuration
@EnableKafka
public class OrderKafkaConfiguration {

    @Bean
    public ConsumerFactory<String, OrderCreated> orderConsumerFactory(
            KafkaProperties kafkaProperties) {

        Map<String, Object> props =
                new HashMap<>(kafkaProperties.buildConsumerProperties());

        props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);

        return new DefaultKafkaConsumerFactory<>(
                props,
                new StringDeserializer(),
                new JsonDeserializer<>(OrderCreated.class)
        );
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> orderConsumerFactory,
                    CommonErrorHandler commonErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(orderConsumerFactory);
        factory.setConcurrency(3);
        factory.setCommonErrorHandler(commonErrorHandler);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Phương thức buildConsumerProperties có chữ ký thay đổi theo phiên bản Spring Boot; ví dụ này cần điều chỉnh đúng dependency của ứng dụng. Nếu không dùng KafkaProperties, có thể xây dựng map cấu hình thủ công như các ví dụ trước.

Listener:

~~~java
@Component
public class OrderCreatedListener {

    private final OrderService orderService;

    public OrderCreatedListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "order-created-listener",
        topics = "orders.created",
        containerFactory = "orderListenerContainerFactory"
    )
    public void onMessage(OrderCreated event) {
        orderService.processIdempotently(event);
    }
}
~~~

Trong ví dụ, service xử lý theo cách idempotent vì record có thể được giao lại nếu side effect hoàn tất nhưng offset chưa commit. Error handler cần được cấu hình để retry lỗi tạm thời và chuyển lỗi không thể phục hồi sang DLT theo chính sách của ứng dụng.

## 16. Nguyên tắc thiết kế

- Dùng ConsumerFactory để khai báo cách tạo Kafka Consumer: kết nối, group, deserializer và client properties.
- Dùng listener container để quản lý consumer, poll loop, acknowledgment, commit, rebalance và lifecycle.
- Dùng ConcurrentKafkaListenerContainerFactory để chuẩn hóa cách tạo container cho @KafkaListener.
- Chọn concurrency dựa trên partition count, số instance và khả năng của downstream.
- Tắt auto commit khi container chịu trách nhiệm commit offset; chọn AckMode theo semantics cần có.
- Chỉ acknowledge sau khi tác vụ nghiệp vụ hoàn tất bền vững.
- Dùng batch listener khi nghiệp vụ hỗ trợ xử lý theo lô và có cách phục hồi khi một phần batch lỗi.
- Gắn CommonErrorHandler phù hợp, giới hạn retry và thiết lập DLT cho record không thể xử lý.
- Điều chỉnh max.poll.records và max.poll.interval.ms theo thời gian xử lý thực tế.
- Dùng KafkaListenerEndpointRegistry để điều khiển listener container; không truy cập trực tiếp KafkaConsumer từ thread ngoài.
- Thiết kế consumer idempotent để xử lý an toàn record được giao lại.
- Theo dõi lag, rebalance, commit, retry và DLT để phát hiện vấn đề trước khi ảnh hưởng nghiệp vụ.

ConsumerFactory và listener container tạo thành lớp hạ tầng điều khiển việc đọc Kafka trong Spring. Factory xác định consumer được tạo với cấu hình nào; container quyết định consumer được chạy, poll, commit và phục hồi ra sao. Khi hai lớp này được cấu hình đúng với semantics nghiệp vụ, listener có thể tập trung vào xử lý sự kiện trong khi Spring Kafka quản lý vòng đời và tương tác với consumer group.

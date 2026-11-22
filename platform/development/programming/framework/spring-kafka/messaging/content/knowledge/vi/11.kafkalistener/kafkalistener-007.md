# Khai báo topics trên @KafkaListener

Thuộc tính `topics` của `@KafkaListener` xác định một hoặc nhiều topic mà listener đăng ký nhận. Có thể khai báo tên topic trực tiếp, lấy tên từ cấu hình Spring hoặc dùng biểu thức SpEL để cung cấp danh sách topic. Chọn đúng cách khai báo giúp listener dễ triển khai giữa các môi trường, tránh lỗi tên topic và giữ subscription rõ ràng.

`topics` là danh sách tên topic cụ thể. Nó không phải consumer group, partition hay biểu thức wildcard. Kafka nhận subscription từ listener container, sau đó phân công partition của các topic đó cho consumer trong group.

## 1. Khai báo một topic

Cách đơn giản nhất là truyền tên topic vào `topics`:

```java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created.v1",
            groupId = "order-projection"
    )
    public void onOrderCreated(OrderCreated event) {
        // Cập nhật read model.
    }
}
```

Trong ví dụ:

- `topics = "orders.created.v1"` yêu cầu consumer subscribe topic có tên chính xác đó.
- `groupId = "order-projection"` xác định consumer group. Các instance dùng cùng group ID sẽ chia nhau partition được gán.
- `OrderCreated` là kiểu payload listener nhận sau khi Kafka deserializer và message converter hoàn tất chuyển đổi.

Tên topic trong `topics` phải khớp tên đã provision trên Kafka, bao gồm cả chữ hoa/chữ thường. `orders.created.v1` và `Orders.Created.v1` là hai tên khác nhau.

## 2. Khai báo nhiều topic

`topics` có kiểu mảng chuỗi, vì vậy có thể khai báo nhiều tên topic trong cùng annotation:

```java
@KafkaListener(
        topics = {
                "orders.created.v1",
                "orders.updated.v1",
                "orders.cancelled.v1"
        },
        groupId = "order-audit"
)
public void onOrderEvent(OrderEvent event) {
    // Xử lý các event có cùng cấu trúc.
}
```

Listener đăng ký cả ba topic. Các partition của ba topic trở thành một subscription của consumer group; Kafka phân phối chúng giữa các consumer theo partition assignor. Nếu tổng subscription có chín partition và listener container có ba consumer, mỗi consumer có thể nhận khoảng ba partition, tùy assignment thực tế.

Nhiều topic trong một listener phù hợp khi chúng có payload tương thích và cùng một logic xử lý. Nếu các topic có schema hoặc kiểu event khác nhau, nên cân nhắc tách listener hoặc dùng một envelope chung có trường `eventType` rõ ràng.

Ví dụ tách listener khi kiểu payload khác nhau:

```java
@Component
public class OrderEventListeners {

    @KafkaListener(topics = "orders.created.v1", groupId = "order-report")
    public void onCreated(OrderCreated event) {
        // Xử lý OrderCreated.
    }

    @KafkaListener(topics = "orders.cancelled.v1", groupId = "order-report")
    public void onCancelled(OrderCancelled event) {
        // Xử lý OrderCancelled.
    }
}
```

Hai listener có thể dùng chung group ID. Kafka phân công partition từ các topic mà group đăng ký; không có nghĩa mỗi listener sẽ tự động nhận mọi record của tất cả topic. Nếu mỗi chức năng cần nhận độc lập toàn bộ dữ liệu, hãy dùng group ID riêng.

## 3. Đưa tên topic vào application.yml

Trong ứng dụng thực tế, nên quản lý tên topic qua cấu hình thay vì ghi cứng ở nhiều class. Ví dụ:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.OrderCreated
        spring.json.trusted.packages: com.example.orders

app:
  kafka:
    topics:
      orders-created: orders.created.v1
      orders-updated: orders.updated.v1
```

Listener sử dụng property placeholder:

```java
@KafkaListener(
        topics = "${app.kafka.topics.orders-created}",
        groupId = "order-projection"
)
public void onOrderCreated(OrderCreated event) {
    // Xử lý sự kiện.
}
```

Spring resolve `${app.kafka.topics.orders-created}` từ `Environment` khi tạo listener endpoint. Nếu property có giá trị `orders.created.v1`, consumer subscribe đúng topic đó.

Có thể khai báo default value để ứng dụng local chạy được khi chưa truyền biến môi trường:

```java
@KafkaListener(
        topics = "${app.kafka.topics.orders-created:orders.created.local}"
)
public void onOrderCreated(OrderCreated event) {
    // Xử lý sự kiện.
}
```

Default value chỉ nên dùng khi topic mặc định thực sự phù hợp với môi trường. Với production, thường nên yêu cầu cấu hình tường minh để tránh ứng dụng vô tình subscribe nhầm topic local hoặc topic mặc định.

## 4. Khai báo nhiều topic lấy từ cấu hình

Vì `topics` là mảng, cách dễ đọc và dễ kiểm soát là đặt mỗi topic trong một phần tử annotation riêng:

```java
@KafkaListener(
        topics = {
                "${app.kafka.topics.orders-created}",
                "${app.kafka.topics.orders-updated}"
        },
        groupId = "order-audit"
)
public void onOrderEvent(OrderEvent event) {
    // Xử lý event từ hai topic.
}
```

Tương ứng trong YAML:

```yaml
app:
  kafka:
    topics:
      orders-created: orders.created.v1
      orders-updated: orders.updated.v1
```

Không nên đặt hai tên topic trong một property dạng chuỗi phân cách bằng dấu phẩy rồi giả định Spring tự tách chúng thành hai phần tử của `topics`:

```yaml
app:
  kafka:
    topics:
      order-events: orders.created.v1,orders.updated.v1
```

Nếu gắn property này vào một phần tử annotation như `topics = "${app.kafka.topics.order-events}"`, kết quả có thể được hiểu là một tên topic duy nhất chứa dấu phẩy, không phải hai topic. Hãy dùng nhiều placeholder như ví dụ trên hoặc dùng SpEL trả về một mảng chuỗi.

## 5. Dùng SpEL khi danh sách topic được cung cấp bởi bean

Khi danh sách topic cần được tập trung trong một bean hoặc được xây dựng theo cấu hình ứng dụng, có thể dùng biểu thức SpEL trong `topics`.

Ví dụ bean cung cấp danh sách topic:

```java
import org.springframework.stereotype.Component;

@Component("orderTopicCatalog")
public class OrderTopicCatalog {

    public String[] orderEventTopics() {
        return new String[] {
                "orders.created.v1",
                "orders.updated.v1"
        };
    }
}
```

Listener tham chiếu bean bằng SpEL:

```java
@KafkaListener(
        topics = "#{@orderTopicCatalog.orderEventTopics()}",
        groupId = "order-audit"
)
public void onOrderEvent(OrderEvent event) {
    // Nhận các event từ danh sách topic do bean cung cấp.
}
```

Biểu thức `#{@orderTopicCatalog.orderEventTopics()}` gọi bean `orderTopicCatalog` và lấy mảng `String[]` làm danh sách topic. Cách này hữu ích khi danh sách được gom trong một thành phần cấu hình có kiểu rõ ràng.

SpEL được đánh giá khi Spring tạo endpoint. Nếu phương thức bean trả về danh sách mới ở một thời điểm sau đó, subscription đang chạy không tự cập nhật theo kết quả mới. Muốn thay đổi subscription khi ứng dụng đang chạy, cần chủ động quản lý listener container và quy trình cập nhật phù hợp.

Không nên dùng SpEL phức tạp nếu một vài property placeholder đã đáp ứng yêu cầu. Biểu thức càng phức tạp càng khó kiểm tra giá trị cuối cùng mà listener đăng ký.

## 6. Phân biệt topics, topicPattern và topicPartitions

Spring Kafka cung cấp ba cách khai báo subscription thường gặp:

| Thuộc tính | Cách đăng ký | Trường hợp phù hợp |
|---|---|---|
| `topics` | Danh sách tên topic cụ thể | Biết rõ topic cần đọc |
| `topicPattern` | Regex khớp tên topic | Muốn nhận các topic được tạo thêm theo một quy ước tên |
| `topicPartitions` | Chỉ định topic và partition cụ thể | Cần assignment tường minh cho một số partition |

Ví dụ `topics`:

```java
@KafkaListener(topics = {"orders.created.v1", "orders.updated.v1"})
public void onOrder(OrderEvent event) {
    // Subscribe hai topic có tên cụ thể.
}
```

Ví dụ `topicPattern`:

```java
@KafkaListener(topicPattern = "orders\\..*")
public void onOrderTopic(ConsumerRecord<String, byte[]> record) {
    // Nhận topic có tên bắt đầu bằng orders.
}
```

Ví dụ `topicPartitions`:

```java
@KafkaListener(
        topicPartitions = @TopicPartition(
                topic = "orders",
                partitions = {"0", "1"}
        )
)
public void onOrderPartition(ConsumerRecord<String, OrderCreated> record) {
    // Chỉ nhận assignment partition 0 và 1.
}
```

Không khai báo đồng thời `topics`, `topicPattern` và `topicPartitions` trên cùng một listener endpoint. Đây là các chiến lược subscription thay thế nhau, không phải các bộ lọc có thể cộng dồn.

Đặc biệt, `topics = "orders.*"` không phải wildcard. `topics` coi chuỗi này là tên topic; nếu muốn khớp nhiều topic theo regex, dùng `topicPattern`.

## 7. Topic subscription và consumer group

`topics` quyết định luồng dữ liệu mà listener muốn nhận. `groupId` quyết định listener tham gia consumer group nào. Hai thuộc tính này phối hợp nhưng không thay thế nhau.

Ví dụ hai dịch vụ cùng subscribe topic `orders.created.v1`:

```java
@KafkaListener(
        topics = "orders.created.v1",
        groupId = "billing-service"
)
public void createBillingRecord(OrderCreated event) {
    // Xử lý thanh toán.
}

@KafkaListener(
        topics = "orders.created.v1",
        groupId = "analytics-service"
)
public void updateAnalytics(OrderCreated event) {
    // Cập nhật số liệu.
}
```

Hai group có offset độc lập và mỗi group có thể nhận toàn bộ record của topic. Nếu hai instance cùng chạy listener với `groupId = "billing-service"`, chúng chia partition để xử lý cùng một luồng công việc.

Nếu bỏ `groupId` khỏi annotation, listener thường dùng group ID từ `spring.kafka.consumer.group-id` trong consumer factory. Có thể cấu hình group chung ở `application.yml` và ghi đè tại annotation khi listener cần group riêng.

## 8. Nhiều topic không có nghĩa là một record được gửi tới mọi listener

Khi một listener subscribe nhiều topic, nó nhận record từ những topic đó theo partition assignment của group. Trong trạng thái ổn định, một partition được giao cho tối đa một consumer trong cùng group; tuy nhiên, record vẫn có thể được đọc lại sau lỗi hoặc rebalance nếu offset chưa được commit. Kafka không nhân bản cùng record thành một bản cho từng listener trong cùng group.

Nếu cần nhiều chức năng cùng nhận một event, tạo các consumer group riêng. Ví dụ:

```text
Topic orders.created.v1
  ├── group billing-service       -> tạo dữ liệu thanh toán
  ├── group order-projection      -> cập nhật read model
  └── group analytics-service     -> tổng hợp số liệu
```

Nếu nhiều listener dùng chung group ID và cùng subscribe một topic, Kafka chia partition giữa các consumer trong group. Một consumer không nhất thiết nhận mọi record nếu partition đó được giao cho consumer khác.

## 9. Kiểu payload khi subscribe nhiều topic

Một listener nhận nhiều topic bằng cùng một phương thức thường giả định các record có thể được deserialize về kiểu tham số chung. Nếu các topic dùng cùng schema hoặc cùng envelope, cách này đơn giản:

```java
public record OrderEvent(
        String eventId,
        String orderId,
        String eventType) {
}

@KafkaListener(
        topics = {"orders.created.v1", "orders.updated.v1"},
        groupId = "order-search"
)
public void updateSearchIndex(OrderEvent event) {
    switch (event.eventType()) {
        case "OrderCreated" -> createDocument(event);
        case "OrderUpdated" -> updateDocument(event);
        default -> throw new IllegalArgumentException(
                "Unsupported event type: " + event.eventType());
    }
}
```

Nếu schema khác nhau, có thể tách listener theo topic để mỗi phương thức nhận đúng kiểu:

```java
@KafkaListener(topics = "orders.created.v1", groupId = "order-search")
public void onCreated(OrderCreated event) {
    createDocument(event);
}

@KafkaListener(topics = "orders.updated.v1", groupId = "order-search")
public void onUpdated(OrderUpdated event) {
    updateDocument(event);
}
```

Hoặc nhận record gốc để định tuyến theo topic:

```java
@KafkaListener(
        topics = {"orders.created.v1", "orders.updated.v1"},
        groupId = "order-router"
)
public void route(ConsumerRecord<String, byte[]> record) {
    switch (record.topic()) {
        case "orders.created.v1" -> handleCreated(record.value());
        case "orders.updated.v1" -> handleUpdated(record.value());
        default -> throw new IllegalArgumentException(
                "Unexpected topic: " + record.topic());
    }
}
```

Ví dụ cuối cần thêm bước deserialize byte theo schema của từng topic. Không ép byte array thành POJO bằng cast; phải dùng deserializer hoặc converter phù hợp.

## 10. Topic phải được tạo và cấp quyền riêng

Khai báo tên topic trong `@KafkaListener` chỉ tạo subscription. Nó không quyết định partition count, replication factor, retention hoặc ACL của topic.

Trong production, topic thường được tạo trước bằng quy trình quản trị, IaC hoặc `KafkaAdmin`/`NewTopic`. Ví dụ:

```java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic ordersCreatedTopic() {
        return TopicBuilder.name("orders.created.v1")
                .partitions(6)
                .replicas(3)
                .build();
    }
}
```

Ứng dụng cũng cần principal có quyền đọc topic và quyền sử dụng consumer group. Nếu topic chưa tồn tại hoặc ACL không hợp lệ, listener có thể không khởi động hoặc không nhận được record tùy cấu hình broker và container.

Không nên dựa vào auto topic creation để tạo topic production theo tên annotation. Topic tự tạo có thể nhận cấu hình mặc định không phù hợp với yêu cầu partition, replication, retention hoặc bảo mật.

## 11. Tên topic và versioning

Tên topic nên theo quy ước thống nhất, thể hiện domain, event và version khi cần:

```text
orders.created.v1
orders.updated.v1
payments.authorized.v1
inventory.stock-changed.v1
```

Khi schema hoặc ý nghĩa event thay đổi không tương thích, có thể tạo topic version mới và cập nhật property theo từng môi trường. Không nên đổi tên topic trong annotation rồi kỳ vọng dữ liệu cũ tự chuyển sang topic mới; topic mới là một log độc lập.

Kafka phân biệt chữ hoa/chữ thường trong tên topic. Tránh tạo các tên chỉ khác bởi dấu chấm và dấu gạch dưới vì một số công cụ metric có thể chuẩn hóa chúng giống nhau.

## 12. Thay đổi danh sách topics khi ứng dụng đang chạy

Các giá trị trong `@KafkaListener` được resolve khi Spring tạo listener endpoint. Nếu đổi biến môi trường hoặc file cấu hình sau khi ứng dụng đã khởi động, subscription hiện tại không tự động đọc lại annotation.

Với thay đổi cấu hình thông thường, cách đơn giản là triển khai lại ứng dụng với property mới. Nếu có yêu cầu thay đổi topic động, cần dùng `KafkaListenerEndpointRegistry` để dừng và quản lý container, hoặc xây dựng cơ chế đăng ký endpoint/container theo chương trình. Quy trình đó cần kiểm soát offset, group ID, thời điểm dừng và khởi động để tránh bỏ sót hoặc xử lý trùng record.

Ví dụ tra cứu container bằng listener ID:

```java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null) {
    container.stop();
    // Thực hiện quy trình cập nhật subscription đã được thiết kế.
}
```

Chỉ dừng container không làm thay đổi danh sách topic trong annotation. Muốn đổi subscription, ứng dụng phải có bước cập nhật endpoint hoặc tạo container mới với danh sách topic mới theo API phù hợp phiên bản Spring Kafka.

## 13. Kiểm thử danh sách topics

Integration test nên xác minh listener đăng ký đúng các topic và nhận được record từ từng topic mong muốn. Có thể dùng `@EmbeddedKafka` hoặc Testcontainers Kafka.

Ví dụ khai báo broker embedded cho hai topic:

```java
@SpringBootTest
@EmbeddedKafka(
        partitions = 1,
        topics = {"orders.created.v1", "orders.updated.v1"}
)
class OrderListenerIntegrationTest {

    @Autowired
    private KafkaTemplate<String, OrderEvent> kafkaTemplate;

    @Test
    void shouldPublishToConfiguredTopic() throws Exception {
        OrderEvent event = new OrderEvent(
                "event-101", "order-42", "OrderCreated");

        SendResult<String, OrderEvent> result = kafkaTemplate
                .send("orders.created.v1", "order-42", event)
                .get(10, TimeUnit.SECONDS);

        assertThat(result.getRecordMetadata().topic())
                .isEqualTo("orders.created.v1");
    }
}
```

Đoạn test trên xác minh producer gửi vào đúng topic. Để xác minh subscription của listener, bổ sung assertion ở phía consumer, chẳng hạn latch hoặc Awaitility được listener kích hoạt khi nhận event. Dùng timeout hữu hạn để test không treo khi listener không nhận được record.

Nên có các trường hợp kiểm thử:

- Listener nhận record từ từng topic trong danh sách.
- Listener không nhận record từ topic ngoài danh sách.
- Placeholder được resolve đúng theo profile.
- Danh sách topic rỗng hoặc property thiếu được phát hiện khi khởi tạo context.
- Nhiều topic có schema tương thích được deserialize đúng.
- Topic không tồn tại hoặc ACL thiếu được quan sát qua log và trạng thái container.

## 14. Lỗi thường gặp khi khai báo topics

**Sai tên hoặc sai chữ hoa/chữ thường:** consumer subscribe một tên khác với topic đã tạo. Kiểm tra property sau khi resolve và metadata broker.

**Gộp nhiều tên bằng dấu phẩy trong một chuỗi:** một phần tử `topics` có thể trở thành một tên topic chứa dấu phẩy. Dùng nhiều phần tử annotation hoặc SpEL trả về `String[]`.

**Dùng wildcard trong `topics`:** `topics` không diễn giải wildcard. Dùng `topicPattern` khi cần regex.

**Khai báo đồng thời `topics` và `topicPattern`:** các chiến lược subscription loại trừ nhau. Chọn một thuộc tính.

**Property placeholder không tồn tại:** Spring không resolve được tên topic khi tạo endpoint. Khai báo property cho mọi profile hoặc dùng default value có chủ đích.

**Danh sách topic chứa phần tử rỗng:** kiểm tra cấu hình và kết quả SpEL để không trả về tên rỗng hoặc null.

**Một listener nhận nhiều schema không tương thích:** deserializer hoặc argument resolver không thể tạo kiểu tham số. Tách listener hoặc dùng envelope/định tuyến rõ ràng.

**Nhầm topic với group ID:** đổi topic làm thay đổi luồng được đọc; đổi group ID làm thay đổi phạm vi tiến độ consumer.

**Tưởng annotation tự tạo topic:** provision topic riêng và cấu hình partition, replication, retention, ACL theo yêu cầu.

**Đổi property nhưng subscription không đổi:** annotation được resolve khi đăng ký endpoint. Cần triển khai lại hoặc quản lý container/endpoint bằng cơ chế động.

## 15. Checklist trước khi đưa listener vào production

- Mỗi phần tử trong `topics` là một tên topic hợp lệ và chính xác.
- Danh sách nhiều topic được khai báo bằng nhiều phần tử hoặc SpEL trả về mảng, không dựa vào việc tự tách chuỗi CSV.
- Placeholder có giá trị trong profile triển khai và không trả về chuỗi rỗng.
- `topics`, `topicPattern` và `topicPartitions` được dùng riêng theo đúng chiến lược subscription.
- Các topic trong cùng listener có schema tương thích hoặc có cơ chế định tuyến/deserialization rõ ràng.
- `groupId` phản ánh đúng mục tiêu chia tải hoặc tiêu thụ độc lập.
- Tổng partition và concurrency được tính cho toàn bộ subscription.
- Topic đã được provision với partition, replication, retention và ACL phù hợp.
- Có kiểm thử nhận record từ từng topic và kiểm tra profile/configuration.
- Có log/metric để xác minh topic, partition, offset, consumer group và lag.

Khai báo `topics` trên `@KafkaListener` là cách xác định rõ luồng sự kiện mà một endpoint cần nhận. Dùng tên cụ thể cho subscription ổn định, property placeholder cho cấu hình theo môi trường và SpEL khi thật sự cần danh sách từ bean. Khi phân biệt đúng `topics`, `topicPattern`, `topicPartitions` và `groupId`, listener sẽ dễ cấu hình, kiểm thử và vận hành hơn.

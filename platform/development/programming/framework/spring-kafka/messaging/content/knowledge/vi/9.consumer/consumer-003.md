# Subscribe topic theo tên trong Spring Kafka

Consumer cần đăng ký nhận dữ liệu từ một hoặc nhiều topic trước khi Kafka phân phối partition cho nó. Với Spring Kafka, cách phổ biến nhất là khai báo `@KafkaListener(topics = "...")`. Tên topic có thể viết trực tiếp hoặc lấy từ cấu hình Spring để thay đổi theo môi trường mà không phải sửa mã nguồn.

Đăng ký topic theo tên giúp dịch vụ chỉ rõ luồng sự kiện mà nó tiêu thụ. Cần phân biệt tên topic với consumer group và partition: topic xác định luồng dữ liệu, group xác định nhóm consumer chia sẻ tiến độ đọc, còn Kafka phân công partition thuộc topic cho các consumer trong group.

## 1. Topic subscription hoạt động như thế nào?

Khi listener container khởi động, Spring Kafka tạo Kafka consumer và gọi cơ chế `subscribe` với danh sách topic đã khai báo. Consumer tham gia group, nhận partition assignment từ Kafka và gọi listener khi poll được record.

```mermaid
flowchart TD
    A[application.yml: topic names] --> B[@KafkaListener topics]
    B --> C[Spring listener container]
    C --> D[Kafka consumer subscribe]
    D --> E[Join consumer group]
    E --> F[Kafka phân công partitions]
    F --> G[Consumer poll records]
    G --> H[Deserializer]
    H --> I[Phương thức listener]
```

Khi khai báo `topics = "orders"`, consumer đăng ký nhận topic có tên chính xác là `orders`. Nó không đăng ký một partition cụ thể. Kafka sẽ phân công các partition của topic đó cho những consumer trong cùng group dựa trên partition assignor và trạng thái thành viên group.

Ví dụ topic `orders` có sáu partition và group `order-projection` có ba consumer. Kafka có thể giao hai partition cho mỗi consumer. Nếu chạy thêm instance cùng group, Kafka có thể rebalance để chia lại partition. Chi tiết phân công phụ thuộc số partition, số consumer, subscription và assignor.

## 2. Subscribe một topic bằng @KafkaListener

Ví dụ listener nhận sự kiện đơn hàng từ topic `orders`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-projection"
    )
    public void onOrderCreated(OrderCreated event) {
        // Cập nhật read model của đơn hàng.
    }
}
```

Các thuộc tính trong ví dụ:

- `topics`: danh sách tên topic mà listener đăng ký nhận.
- `groupId`: consumer group của listener. Các instance dùng cùng group ID sẽ chia nhau partition.
- `onOrderCreated`: phương thức được Spring Kafka gọi khi consumer nhận và chuyển đổi được record.
- `OrderCreated`: kiểu payload phải tương thích với deserializer đã cấu hình.

`groupId` là danh tính consumer group, không phải tên topic. Một topic có thể được nhiều group đăng ký độc lập. Ví dụ `order-projection`, `billing-service` và `analytics-service` đều có thể subscribe `orders`; mỗi group duy trì offset riêng và đọc luồng dữ liệu độc lập.

Nếu không đặt `groupId` tại annotation, listener sử dụng group ID từ cấu hình consumer factory, thường là `spring.kafka.consumer.group-id`. Chọn một nơi cấu hình rõ ràng để tránh nhầm lẫn giữa các listener.

## 3. Đưa tên topic vào application.yml

Trong ứng dụng thực tế, nên đặt tên topic trong cấu hình thay vì ghi cứng ở nhiều class. Ví dụ:

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
      orders: orders.v1
```

Listener tham chiếu đến property:

```java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "${app.kafka.topics.orders}"
    )
    public void onOrderCreated(OrderCreated event) {
        // Xử lý sự kiện.
    }
}
```

Spring giải quyết placeholder `${app.kafka.topics.orders}` khi tạo listener endpoint. Nếu property có giá trị `orders.v1`, consumer đăng ký đúng topic `orders.v1`.

Lợi ích của cấu hình tên topic:

- Đổi topic theo local, staging hoặc production mà không sửa Java code.
- Tập trung quy ước tên topic tại một nơi.
- Tránh lỗi gõ sai tên hoặc dùng các tên khác nhau cho cùng một luồng.
- Dễ quản lý version topic, ví dụ `orders.v1` và `orders.v2`.

Tên property là quy ước của ứng dụng. `app.kafka.topics.orders` không phải thuộc tính Kafka client; nó chỉ là giá trị cấu hình mà Spring đưa vào annotation.

## 4. Subscribe nhiều topic bằng tên

Một listener có thể đăng ký nhiều topic bằng thuộc tính `topics` dạng mảng:

```java
@KafkaListener(
        topics = {"orders.created", "orders.updated"},
        groupId = "order-audit"
)
public void onOrderEvent(OrderEvent event) {
    // Xử lý các event có cùng cấu trúc.
}
```

Có thể lấy từng tên từ cấu hình:

```java
@KafkaListener(
        topics = {
                "${app.kafka.topics.order-created}",
                "${app.kafka.topics.order-updated}"
        },
        groupId = "order-audit"
)
public void onOrderEvent(OrderEvent event) {
    // Xử lý event từ cả hai topic.
}
```

```yaml
app:
  kafka:
    topics:
      order-created: orders.created.v1
      order-updated: orders.updated.v1
```

Kafka phân công partition của tất cả topic đã đăng ký cho consumer group. Tổng số partition trong subscription quyết định mức song song có thể khai thác. Nếu listener có ba consumer nhưng subscription chỉ có hai partition tổng cộng, tối đa hai consumer được giao partition trong trạng thái ổn định.

### Khi nhiều topic có cùng kiểu event

Một phương thức listener nhận nhiều topic thuận tiện khi các topic có payload tương thích, ví dụ cùng dùng `OrderEvent`:

```java
@KafkaListener(
        topics = {"orders.created", "orders.updated"},
        groupId = "order-search-index"
)
public void updateIndex(OrderEvent event) {
    // Cập nhật chỉ mục tìm kiếm.
}
```

Nếu các topic có schema hoặc kiểu payload khác nhau, không nên ép tất cả vào một POJO không tương thích. Có thể dùng các listener riêng với kiểu payload tương ứng, hoặc nhận `ConsumerRecord<String, byte[]>`/một envelope chung rồi định tuyến theo topic và event type.

Ví dụ tách listener khi schema khác nhau:

```java
@KafkaListener(topics = "orders.created", groupId = "order-report")
public void onCreated(OrderCreated event) {
    // Xử lý OrderCreated.
}

@KafkaListener(topics = "orders.cancelled", groupId = "order-report")
public void onCancelled(OrderCancelled event) {
    // Xử lý OrderCancelled.
}
```

Hai listener có thể dùng cùng group ID. Khi cùng group đăng ký các topic tương ứng, Kafka phân phối partition của các topic trong subscription theo group đó. Hãy kiểm tra cấu hình concurrency và tổng partition để tránh tạo consumer dư thừa.

## 5. Tên topic và quy tắc đặt tên

Topic name là định danh chính xác trong Kafka. Tên topic phân biệt chữ hoa/chữ thường, vì vậy `orders`, `Orders` và `ORDERS` được xem là các tên khác nhau.

Quy tắc tên topic phổ biến của Kafka:

- Độ dài từ 1 đến 249 ký tự.
- Chỉ dùng chữ cái ASCII, chữ số, dấu chấm (`.`), gạch dưới (`_`) và gạch ngang (`-`).
- Không dùng tên chỉ gồm `.` hoặc `..`.
- Nên dùng một quy ước thống nhất để dễ quản lý theo domain, event và version.

Ví dụ:

```text
orders.created.v1
payments.authorized.v1
inventory.stock-changed.v1
customer-profile.updated.v2
```

Tránh tạo nhiều topic chỉ khác nhau bởi dấu chấm và dấu gạch dưới, ví dụ `orders.created` và `orders_created`. Một số hệ thống metric chuẩn hóa hai ký tự này theo cách giống nhau, gây khó phân biệt số liệu.

Tên topic nên thể hiện domain và sự kiện, đồng thời có chiến lược version khi schema hoặc ngữ nghĩa event thay đổi không tương thích. Không nên dùng tên topic như một nơi chứa tên môi trường nếu cùng một ứng dụng có thể chọn topic qua cấu hình môi trường.

## 6. Topic name khác topicPattern

`topics` dùng tên topic cụ thể. `topicPattern` dùng biểu thức chính quy để đăng ký mọi topic có tên khớp mẫu. Hai cách này có mục đích khác nhau.

Subscribe tên cụ thể:

```java
@KafkaListener(topics = "orders.created.v1")
public void onOrder(OrderCreated event) {
    // Chỉ nhận topic orders.created.v1.
}
```

Subscribe theo pattern:

```java
@KafkaListener(topicPattern = "orders\\..*")
public void onAnyOrderEvent(ConsumerRecord<String, byte[]> record) {
    // Nhận các topic khớp biểu thức orders\..*.
}
```

Trong mã Java, pattern dùng hai dấu gạch chéo ngược để tạo regex escape dấu chấm; nó khớp tên topic bắt đầu bằng orders.

Không dùng `topics = "orders.*"` với kỳ vọng đó là wildcard. Trong `topics`, đây là một tên topic cụ thể; ký tự `*` cũng không hợp lệ trong tên topic Kafka. Nếu cần đăng ký một tập topic thay đổi theo thời gian, dùng `topicPattern` và kiểm soát regex chặt chẽ.

Không khai báo đồng thời `topics`, `topicPattern` và `topicPartitions` trên cùng một listener endpoint. Chọn một cách đăng ký phù hợp với nhu cầu.

## 7. Khi nào dùng topicPartitions thay cho subscribe tên?

`topics` và `topicPattern` sử dụng cơ chế subscription do Kafka quản lý trong consumer group. `topicPartitions` dùng khi ứng dụng muốn chỉ định trực tiếp partition cụ thể cho listener.

Ví dụ:

```java
@KafkaListener(
        groupId = "orders-partition-reader",
        topicPartitions = @TopicPartition(
                topic = "orders",
                partitions = {"0", "1"}
        )
)
public void onPartitionRecord(ConsumerRecord<String, OrderCreated> record) {
    // Chỉ xử lý partition 0 và 1.
}
```

Với cách này, listener nhận assignment tường minh cho partition đã chọn. Ứng dụng chịu trách nhiệm phân chia partition giữa các listener/instance để tránh nhiều consumer cùng cố gắng đọc một partition theo cách không mong muốn. Cách này ít linh hoạt khi số partition thay đổi và không tận dụng đầy đủ cơ chế phân phối subscription tự động.

Trong phần lớn ứng dụng nghiệp vụ, nên dùng `topics` theo tên và để Kafka quản lý partition assignment. Chỉ dùng `topicPartitions` khi có yêu cầu rõ ràng về quyền sở hữu partition, xử lý một tập partition cố định hoặc cần điều khiển offset ban đầu theo partition.

## 8. Subscription không tự tạo topic

Khai báo `@KafkaListener(topics = "orders")` có nghĩa là consumer đăng ký đọc topic đó. Nó không phải lệnh quản trị để tạo topic với số partition hoặc replication factor mong muốn.

Một số broker có thể bật `auto.create.topics.enable`; trong trường hợp đó, topic có thể được tạo tự động khi client tham chiếu tới topic chưa tồn tại. Tuy nhiên, không nên dựa vào cơ chế này trong production vì topic có thể được tạo với cấu hình mặc định không phù hợp với yêu cầu partition, replication, retention hoặc bảo mật.

Nên tạo topic trước bằng quy trình quản trị hoặc dùng `KafkaAdmin` với `NewTopic`:

```java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .build();
    }
}
```

`KafkaAdmin` cần bootstrap servers hợp lệ và quyền tạo topic. Trong hệ thống production, nhóm nền tảng có thể quản lý topic riêng qua IaC hoặc quy trình triển khai; khi đó ứng dụng chỉ cần subscribe topic đã được cấp.

Nếu topic chưa tồn tại, consumer có thể không nhận được record và hành vi khởi động phụ thuộc cấu hình Spring Kafka cùng broker. Có thể bật kiểm tra topic thiếu bằng thuộc tính `missingTopicsFatal` của listener container nếu muốn ứng dụng fail fast; mặc định của thuộc tính này thay đổi theo phiên bản và cấu hình, vì vậy cần kiểm tra đúng version đang dùng.

## 9. Nhiều listener và nhiều consumer group

Một ứng dụng có thể khai báo nhiều listener cho các topic khác nhau:

```java
@Component
public class OrderListeners {

    @KafkaListener(
            id = "orderProjectionListener",
            topics = "${app.kafka.topics.orders}",
            groupId = "order-projection"
    )
    public void project(OrderCreated event) {
        // Cập nhật read model.
    }

    @KafkaListener(
            id = "orderAuditListener",
            topics = "${app.kafka.topics.orders}",
            groupId = "order-audit"
    )
    public void audit(OrderCreated event) {
        // Ghi audit độc lập.
    }
}
```

Hai listener subscribe cùng topic nhưng dùng hai group ID khác nhau. Vì vậy, mỗi group có thể nhận toàn bộ record của topic và duy trì offset riêng. Thuộc tính `id` định danh listener endpoint trong Spring; nó không thay thế `groupId`.

Nếu hai listener cần chia tải cùng một công việc, hãy dùng chung group ID và thiết kế partition assignment phù hợp. Nếu chúng là hai chức năng nghiệp vụ độc lập cần nhận đủ sự kiện, dùng group ID riêng.

## 10. Lấy topic từ cấu hình kiểu mạnh

Với ứng dụng có nhiều topic, có thể gom tên topic vào một lớp cấu hình để giảm lỗi gõ và dễ kiểm tra cấu hình khi khởi động:

```java
@ConfigurationProperties(prefix = "app.kafka.topics")
public record KafkaTopicProperties(
        String orders,
        String payments,
        String inventory) {
}
```

Kích hoạt binding:

```java
@Configuration
@EnableConfigurationProperties(KafkaTopicProperties.class)
public class KafkaPropertiesConfiguration {
}
```

Với `@KafkaListener`, annotation thường dùng placeholder `${...}` để lấy giá trị cấu hình trực tiếp. Nếu muốn dùng biểu thức SpEL để lấy danh sách từ bean, cần bảo đảm bean đã được đăng ký và biểu thức trả về đúng kiểu mà annotation mong đợi. Với các topic tĩnh theo môi trường, placeholder đơn giản thường dễ đọc và ít phức tạp hơn.

Lưu ý rằng annotation được xử lý khi Spring tạo endpoint. Thay đổi file cấu hình bên ngoài sau khi ứng dụng đã khởi động không tự động đổi subscription đang chạy. Muốn đổi topic trong runtime, cần cơ chế quản lý listener container hoặc khởi động lại ứng dụng theo quy trình triển khai.

## 11. Cấu hình theo môi trường

Local, staging và production có thể dùng các topic khác nhau:

```yaml
# application-local.yml
app:
  kafka:
    topics:
      orders: orders.local

---
# application-prod.yml
app:
  kafka:
    topics:
      orders: orders.v1
```

Kích hoạt profile phù hợp bằng `SPRING_PROFILES_ACTIVE`. Listener vẫn dùng một placeholder:

```java
@KafkaListener(topics = "${app.kafka.topics.orders}")
public void onOrder(OrderCreated event) {
    // Logic không phụ thuộc tên topic cụ thể.
}
```

Khi triển khai, cần xác minh property được nạp đúng profile và topic tương ứng đã tồn tại. Có thể kiểm tra cấu hình đã resolve qua log startup hoặc Spring Actuator environment endpoint nếu endpoint đó được bảo vệ phù hợp.

Không nên để cùng một consumer group vô tình chạy trên hai môi trường dùng chung cụm Kafka nhưng subscribe các topic không chủ đích. Group ID và topic naming cần có phạm vi môi trường rõ ràng khi các môi trường chia sẻ broker.

## 12. Kiểm tra subscription và partition assignment

Sau khi ứng dụng khởi động, xác minh consumer đã đăng ký đúng topic, đúng group và được giao partition mong muốn.

Xem thông tin topic:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Xem trạng thái consumer group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection
```

Kết quả consumer group cho biết topic, partition, consumer ID, offset đã commit và lag. Nếu topic không xuất hiện trong group, hãy kiểm tra listener có được khởi tạo hay không, property topic đã resolve đúng chưa, group ID có đúng không và consumer có quyền đọc topic không.

Trong ứng dụng, có thể log các trường topic, partition, offset ở listener để xác nhận dữ liệu thực tế:

```java
@KafkaListener(topics = "${app.kafka.topics.orders}")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    log.info(
            "Received Kafka record: topic={}, partition={}, offset={}",
            record.topic(), record.partition(), record.offset());

    // Xử lý record.value().
}
```

Không ghi toàn bộ payload hoặc dữ liệu nhạy cảm vào log. Với hệ thống nhiều topic, thêm event ID hoặc correlation ID để truy vết qua các dịch vụ.

## 13. Các lỗi thường gặp khi subscribe theo tên

**Sai tên topic:** Kafka phân biệt chữ hoa/chữ thường. Kiểm tra giá trị cấu hình đã resolve và tên topic trên broker.

**Dùng nhầm property:** listener trỏ tới `${app.kafka.topic.orders}` nhưng YAML khai báo `app.kafka.topics.orders`. Placeholder sai có thể làm ứng dụng không khởi tạo endpoint hoặc dùng giá trị không mong muốn.

**Nhầm topic với group ID:** đổi group ID làm thay đổi tiến độ đọc độc lập; đổi topic làm thay đổi luồng dữ liệu được đăng ký. Hai thuộc tính không thay thế nhau.

**Nhiều instance dùng group ID khác nhau:** mỗi instance có thể nhận toàn bộ dữ liệu thay vì chia partition. Đảm bảo group ID giống nhau nếu mục tiêu là scale cùng một consumer group.

**Topic chưa tồn tại:** subscription không thay thế quy trình tạo topic. Provision topic trước và kiểm tra quyền truy cập.

**Dùng wildcard trong topics:** `topics` nhận tên cụ thể; dùng `topicPattern` nếu cần regex.

**Dùng một listener cho nhiều schema không tương thích:** deserializer có thể lỗi hoặc listener không thể bind payload. Tách listener hoặc dùng envelope chung có chiến lược định tuyến rõ ràng.

**Thay property nhưng kỳ vọng listener đổi ngay:** subscription được tạo khi endpoint khởi động. Thay đổi cấu hình cần quy trình cập nhật container hoặc restart.

**Dùng topicPartitions mà vẫn mong Kafka tự chia partition:** chỉ định partition trực tiếp thay đổi cơ chế assignment. Chọn `topics` cho subscription thông thường.

**Không có quyền đọc topic:** kiểm tra ACL của principal consumer đối với topic và group, cùng security protocol và credential.

## 14. Checklist trước khi đưa listener vào production

- Tên topic chính xác, tuân thủ quy ước và được đặt trong cấu hình phù hợp.
- Placeholder trong `@KafkaListener` trỏ đúng property và đã resolve ở profile triển khai.
- Topic đã được provision với partition, replication, retention và cấu hình bảo mật phù hợp.
- `groupId` phản ánh đúng mục tiêu chia tải hay tiêu thụ độc lập.
- Kiểu payload của listener tương thích với key/value deserializer.
- Nhiều topic trong một listener có schema tương thích hoặc có chiến lược định tuyến rõ ràng.
- Dùng `topicPattern` khi thực sự cần đăng ký theo regex; dùng `topicPartitions` khi cần assignment tường minh.
- Concurrency phù hợp với tổng partition trong subscription.
- Consumer có ACL đọc topic và quyền tham gia group.
- Có log/metric để xác minh topic, partition, offset, lag và lỗi listener.

Subscribe theo tên giúp listener khai báo rõ luồng sự kiện mà ứng dụng cần nhận. Khi tách bạch topic, group ID và partition assignment, đồng thời quản lý tên topic qua cấu hình, ứng dụng Spring Kafka có thể triển khai nhất quán giữa các môi trường và mở rộng consumer group mà không phải thay đổi logic xử lý sự kiện.

# Dùng SpEL trong annotation

## Mục tiêu của bài học

Trong chương **@KafkaListener**, bài này hướng dẫn dùng Spring Expression Language (SpEL) trong các thuộc tính của annotation để cấu hình listener linh hoạt theo bean, cấu hình ứng dụng và môi trường triển khai.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. SpEL trong @KafkaListener giúp xác định topic, topic pattern hoặc group ID từ nguồn cấu hình có quản lý, nhờ đó listener có thể dùng cùng mã nguồn ở nhiều môi trường.

Sau bài học, người học có thể:

- Phân biệt property placeholder `${...}` với SpEL expression `#{...}`.
- Tham chiếu bean Spring trong thuộc tính @KafkaListener.
- Dùng pseudo bean `__listener` để lấy cấu hình từ chính listener bean.
- Cấu hình topics, topicPattern và groupId bằng expression.
- Hiểu kiểu dữ liệu mà expression cần trả về.
- Nhận diện thời điểm expression được đánh giá và ảnh hưởng tới vòng đời listener.
- Chẩn đoán lỗi expression, placeholder, bean reference và topic subscription.
- Kiểm thử listener được cấu hình bằng SpEL.

## 1. Vì sao cần SpEL trong @KafkaListener?

Một listener thường cần khai báo topic và consumer group:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void handle(OrderCreated event) {
    // Xử lý sự kiện đơn hàng.
}
~~~

Cách khai báo trực tiếp này dễ đọc, nhưng khi cùng một ứng dụng chạy ở nhiều môi trường hoặc topic được quản lý tập trung, hard-code tên topic trong annotation có thể gây khó khăn khi thay đổi cấu hình.

Spring Kafka cho phép dùng property placeholder hoặc SpEL trong các thuộc tính của @KafkaListener. Thay vì ghi tên topic trực tiếp, listener có thể lấy giá trị từ application.yml hoặc một bean Spring.

Ví dụ:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.order-created}",
    groupId = "${app.kafka.consumer-groups.billing}"
)
public void handle(OrderCreated event) {
    // Xử lý sự kiện đơn hàng.
}
~~~

Hoặc dùng SpEL để tham chiếu bean:

~~~java
@KafkaListener(
    topics = "#{@kafkaTopicProperties.orderCreated}",
    groupId = "#{@consumerGroupProperties.billing}"
)
public void handle(OrderCreated event) {
    // Xử lý sự kiện đơn hàng.
}
~~~

Cả hai cách đều giúp tách cấu hình khỏi logic xử lý. Property placeholder phù hợp với giá trị đơn giản từ Environment; SpEL hữu ích khi cần đọc thuộc tính bean, gọi phương thức hoặc tính giá trị theo một biểu thức.

## 2. Phân biệt property placeholder và SpEL

Hai cú pháp thường xuất hiện cạnh nhau trong annotation Spring nhưng có mục đích khác nhau.

| Cú pháp | Tên | Nguồn giá trị | Ví dụ |
|---|---|---|---|
| `${...}` | Property placeholder | Environment, application.yml, biến môi trường, property source | `${app.kafka.topics.order-created}` |
| `#{...}` | SpEL expression | Spring Expression Language, bean và expression context | `#{@kafkaTopicProperties.orderCreated}` |

### 2.1. Property placeholder

Giả sử application.yml có:

~~~yaml
app:
  kafka:
    topics:
      order-created: commerce.order.created
    consumer-groups:
      billing: billing-service
~~~

Listener dùng trực tiếp các thuộc tính:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.order-created}",
    groupId = "${app.kafka.consumer-groups.billing}"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Spring thay placeholder bằng giá trị tương ứng từ cấu hình. Đây là lựa chọn đơn giản nhất khi giá trị chỉ phụ thuộc cấu hình môi trường.

Nếu property không tồn tại và không có default phù hợp, quá trình tạo listener endpoint có thể thất bại khi ứng dụng khởi động.

Có thể đặt default ngay trong placeholder:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.order-created:commerce.order.created}"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Cú pháp sau dấu hai chấm là giá trị mặc định khi property chưa được khai báo.

### 2.2. SpEL expression

SpEL cho phép biểu diễn một biểu thức thay vì chỉ lấy một chuỗi cấu hình. Expression có thể:

- Đọc property của một bean Spring.
- Gọi phương thức trên bean.
- Truy cập giá trị trong expression context.
- Sử dụng toán tử điều kiện để chọn giá trị.
- Truy cập hằng số static thông qua type operator.

Ví dụ tham chiếu bean:

~~~java
@KafkaListener(
    topics = "#{@kafkaTopicProperties.orderCreated}"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Trong đó:

- `#` mở đầu một SpEL expression.
- `@kafkaTopicProperties` tham chiếu bean có tên kafkaTopicProperties.
- `.orderCreated` đọc property orderCreated của bean.

SpEL hữu ích khi giá trị cần lấy từ bean hoặc được tính toán. Nếu chỉ cần đọc một property đơn giản, placeholder thường dễ đọc và dễ vận hành hơn.

## 3. Khai báo bean cấu hình topic

Một cách phổ biến là gom các topic vào một bean cấu hình có kiểu dữ liệu rõ ràng.

application.yml:

~~~yaml
app:
  kafka:
    topics:
      order-created: commerce.order.created
      order-cancelled: commerce.order.cancelled
      payment-authorized: commerce.payment.authorized
~~~

Bean cấu hình:

~~~java
@Component("kafkaTopicProperties")
@ConfigurationProperties(prefix = "app.kafka.topics")
public class KafkaTopicProperties {

    private String orderCreated;
    private String orderCancelled;
    private String paymentAuthorized;

    public String getOrderCreated() {
        return orderCreated;
    }

    public void setOrderCreated(String orderCreated) {
        this.orderCreated = orderCreated;
    }

    public String getOrderCancelled() {
        return orderCancelled;
    }

    public void setOrderCancelled(String orderCancelled) {
        this.orderCancelled = orderCancelled;
    }

    public String getPaymentAuthorized() {
        return paymentAuthorized;
    }

    public void setPaymentAuthorized(String paymentAuthorized) {
        this.paymentAuthorized = paymentAuthorized;
    }
}
~~~

Spring Boot bind các property trong application.yml vào bean. Annotation `@Component("kafkaTopicProperties")` đăng ký bean với tên được dùng trong SpEL.

Listener tham chiếu bean:

~~~java
@Service
public class OrderEventListener {

    @KafkaListener(
        topics = "#{@kafkaTopicProperties.orderCreated}",
        groupId = "billing-service"
    )
    public void handleCreated(OrderCreated event) {
        // Xử lý đơn hàng mới.
    }

    @KafkaListener(
        topics = "#{@kafkaTopicProperties.orderCancelled}",
        groupId = "billing-service"
    )
    public void handleCancelled(OrderCancelled event) {
        // Xử lý đơn hàng bị hủy.
    }
}
~~~

Nếu dùng `@ConfigurationProperties` mà không đăng ký bean bằng `@Component`, cần bật đăng ký thông qua `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan`.

Cách tổ chức này giúp tập trung tên topic và hạn chế việc nhiều listener dùng các chuỗi khác nhau cho cùng một luồng nghiệp vụ.

## 4. Tham chiếu bean Spring bằng SpEL

Trong SpEL, ký hiệu `@beanName` dùng để tham chiếu bean trong ApplicationContext.

Ví dụ:

~~~java
@KafkaListener(
    topics = "#{@kafkaTopicProperties.orderCreated}",
    groupId = "#{@consumerGroupProperties.billing}"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Giả sử bean group configuration:

~~~java
@Component("consumerGroupProperties")
@ConfigurationProperties(prefix = "app.kafka.consumer-groups")
public class ConsumerGroupProperties {

    private String billing;

    public String getBilling() {
        return billing;
    }

    public void setBilling(String billing) {
        this.billing = billing;
    }
}
~~~

Cấu hình:

~~~yaml
app:
  kafka:
    consumer-groups:
      billing: billing-service
~~~

Expression đọc giá trị group ID từ bean thay vì ghi chuỗi trực tiếp trong annotation.

### 4.1. Gọi phương thức của bean

SpEL có thể gọi phương thức để lấy giá trị:

~~~java
@KafkaListener(
    topics = "#{@topicResolver.resolve('orders')}"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Bean resolver:

~~~java
@Component
public class TopicResolver {

    public String resolve(String name) {
        return switch (name) {
            case "orders" -> "commerce.order.created";
            case "payments" -> "commerce.payment.authorized";
            default -> throw new IllegalArgumentException(
                "Unknown topic key: " + name
            );
        };
    }
}
~~~

Expression được dùng để lấy giá trị cấu hình khi listener endpoint được đăng ký. Vì vậy, phương thức resolve nên đơn giản, có kết quả xác định và không tạo side effect.

Không thực hiện truy vấn database, gọi HTTP hoặc công việc tốn thời gian trong biểu thức dùng để khai báo listener. Hãy nạp và kiểm tra cấu hình trước, sau đó để expression chỉ đọc giá trị đã sẵn sàng.

### 4.2. Dùng toán tử điều kiện

SpEL hỗ trợ toán tử điều kiện để chọn topic dựa trên một thuộc tính cấu hình:

~~~java
@KafkaListener(
    topics = "#{@topicSettings.useArchive ? @topicSettings.archiveTopic : @topicSettings.liveTopic}"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Bean settings có thể chứa:

~~~java
@Component("topicSettings")
@ConfigurationProperties(prefix = "app.kafka.topic-settings")
public class TopicSettings {

    private boolean useArchive;

    public boolean isUseArchive() {
        return useArchive;
    }

    public void setUseArchive(boolean useArchive) {
        this.useArchive = useArchive;
    }

    public String getArchiveTopic() {
        return "commerce.order.archive";
    }

    public String getLiveTopic() {
        return "commerce.order.created";
    }
}
~~~

Giá trị có thể được bind từ cấu hình:

~~~yaml
app:
  kafka:
    topic-settings:
      use-archive: false
~~~

Expression chọn một trong hai topic dựa trên cấu hình. Cách này có ích khi lựa chọn được quyết định tại thời điểm khởi động.

Không nên lạm dụng biểu thức điều kiện phức tạp trong annotation. Nếu logic chọn topic có nhiều nhánh hoặc phụ thuộc nghiệp vụ, hãy chuyển logic đó vào một bean cấu hình có tên phương thức rõ nghĩa.

## 5. Dùng pseudo bean __listener

Spring Kafka cung cấp một pseudo bean để SpEL tham chiếu chính bean chứa phương thức @KafkaListener. Tên mặc định là `__listener`.

Cơ chế này hữu ích khi mỗi listener bean có cấu hình riêng, chẳng hạn topic được truyền qua constructor.

Ví dụ:

~~~java
@Component
public class TenantOrderListener {

    private final String topic;

    public TenantOrderListener(
            @Value("${app.kafka.topics.tenant-orders}") String topic) {
        this.topic = topic;
    }

    public String getTopic() {
        return topic;
    }

    @KafkaListener(
        topics = "#{__listener.topic}",
        groupId = "tenant-order-service"
    )
    public void handle(OrderCreated event) {
        // Xử lý event từ topic đã cấu hình.
    }
}
~~~

Ở đây:

- Constructor nhận topic từ application.yml.
- Getter `getTopic()` cung cấp giá trị cho SpEL.
- `#{__listener.topic}` đọc property topic của listener bean.
- Listener vẫn dùng cùng mã nguồn khi topic thay đổi theo cấu hình môi trường.

Pseudo bean này đặc biệt hữu ích khi có nhiều listener bean cùng lớp hoặc nhiều instance bean có cấu hình khác nhau.

### 5.1. Đổi tên bean reference

Thuộc tính `beanRef` của @KafkaListener cho phép đổi tên pseudo bean reference. Nếu thay tên, expression phải sử dụng đúng tên mới.

Ví dụ:

~~~java
@KafkaListener(
    beanRef = "listenerBean",
    topics = "#{listenerBean.topic}"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Tên mặc định `__listener` thường đủ rõ ràng. Chỉ đổi khi có lý do cụ thể hoặc cần tránh xung đột với một tên bean khác trong expression context.

## 6. Dùng SpEL cho topics

Thuộc tính `topics` nhận một hoặc nhiều tên topic. Có thể dùng expression để lấy tên topic từ bean.

~~~java
@KafkaListener(
    topics = "#{@kafkaTopicProperties.orderCreated}"
)
public void handleCreated(OrderCreated event) {
    // Xử lý event.
}
~~~

Nếu listener cần subscribe nhiều topic, có thể khai báo nhiều giá trị:

~~~java
@KafkaListener(
    topics = {
        "${app.kafka.topics.order-created}",
        "${app.kafka.topics.order-cancelled}"
    },
    groupId = "order-audit-service"
)
public void audit(Object event) {
    // Xử lý các loại event được subscribe.
}
~~~

Hai topic trên cùng được subscribe bởi một listener endpoint. Payload thực tế cần được deserialize hoặc convert theo cấu hình tương thích với các loại event nhận được.

Nếu các topic có payload khác kiểu, hãy cân nhắc dùng listener riêng hoặc một kiểu envelope chung để tránh ép kiểu không an toàn.

### 6.1. Không trộn topics với topicPattern hoặc topicPartitions

@KafkaListener hỗ trợ các cách subscription chính:

- `topics`: subscribe theo tên topic.
- `topicPattern`: subscribe theo regular expression.
- `topicPartitions`: chỉ định topic và partition cụ thể.

Các cách này là những lựa chọn thay thế cho nhau trong cùng một endpoint. Không khai báo đồng thời nhiều thuộc tính subscription này cho một listener.

## 7. Dùng SpEL cho topicPattern

Khi cần subscribe nhiều topic theo một quy tắc tên, có thể dùng `topicPattern`.

Ví dụ cấu hình:

~~~yaml
app:
  kafka:
    topic-patterns:
      order-events: 'commerce\.order\.(created|cancelled)'
~~~

Bean cấu hình:

~~~java
@Component("topicPatternProperties")
@ConfigurationProperties(prefix = "app.kafka.topic-patterns")
public class TopicPatternProperties {

    private String orderEvents;

    public String getOrderEvents() {
        return orderEvents;
    }

    public void setOrderEvents(String orderEvents) {
        this.orderEvents = orderEvents;
    }
}
~~~

Listener:

~~~java
@KafkaListener(
    topicPattern = "#{@topicPatternProperties.orderEvents}",
    groupId = "order-audit-service"
)
public void handle(String payload) {
    // Nhận record từ topic có tên khớp pattern.
}
~~~

Pattern là regular expression, không phải tên topic cụ thể. Ví dụ `commerce\.order\..*` có thể khớp các topic bắt đầu bằng commerce.order.

Khi topic mới được tạo và tên khớp pattern, consumer có thể phát hiện topic đó thông qua quá trình cập nhật metadata và subscription của Kafka client.

Cần kiểm tra regex cẩn thận. Pattern quá rộng có thể khiến listener nhận dữ liệu từ những topic không thuộc phạm vi nghiệp vụ dự kiến.

## 8. Dùng SpEL cho groupId

groupId xác định consumer group lưu tiến độ đọc và chia sẻ partition assignment.

Có thể lấy group ID từ bean:

~~~java
@KafkaListener(
    topics = "#{@kafkaTopicProperties.orderCreated}",
    groupId = "#{@consumerGroupProperties.billing}"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Hoặc dùng property placeholder:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.order-created}",
    groupId = "${app.kafka.consumer-groups.billing}"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Hãy giữ group ID ổn định qua các lần restart và deploy nếu muốn tiếp tục committed offset hiện tại. Nếu expression vô tình trả về một group ID mới theo timestamp hoặc giá trị ngẫu nhiên, ứng dụng có thể tạo group mới và bắt đầu theo auto.offset.reset.

### 8.1. Phân biệt id và groupId

@KafkaListener có thuộc tính `id` để định danh listener endpoint trong Spring Kafka. `groupId` là định danh consumer group của Kafka.

Hai giá trị có thể liên quan theo cấu hình `idIsGroup`. Khi không khai báo groupId, mặc định id của listener có thể được dùng làm group ID nếu idIsGroup bật. Vì vậy, nếu muốn kiểm soát group rõ ràng, nên khai báo groupId trực tiếp hoặc cấu hình mặc định có chủ đích.

Ví dụ:

~~~java
@KafkaListener(
    id = "order-created-listener",
    groupId = "billing-service",
    topics = "${app.kafka.topics.order-created}"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Trong ví dụ này, id phục vụ quản lý listener endpoint; groupId xác định consumer group.

## 9. SpEL có thể dùng cho thuộc tính nào?

Các thuộc tính cấu hình của @KafkaListener hỗ trợ cơ chế phân giải placeholder và expression theo quy tắc Spring Kafka. Những trường hợp thường gặp:

| Thuộc tính | Mục đích | Ví dụ |
|---|---|---|
| topics | Tên topic cần subscribe | `#{@topicProperties.orderCreated}` |
| topicPattern | Regex topic | `#{@topicPatternProperties.orderEvents}` |
| groupId | Consumer group ID | `#{@groupProperties.billing}` |
| id | ID listener endpoint | `#{@listenerSettings.orderListenerId}` |
| clientIdPrefix | Tiền tố client ID | `#{@listenerSettings.clientPrefix}` |
| concurrency | Số consumer container con | `#{@listenerSettings.concurrency}` |
| autoStartup | Có tự động start container không | `#{@listenerSettings.autoStartup}` |

Cần bảo đảm expression trả về giá trị có thể chuyển đổi sang kiểu mà thuộc tính yêu cầu. Ví dụ, topics cần tên topic hợp lệ; groupId cần chuỗi ổn định; concurrency cần giá trị số phù hợp; autoStartup cần giá trị boolean có thể chuyển đổi.

Khi dùng expression cho concurrency hoặc autoStartup, hãy kiểm tra kiểu dữ liệu và cách chuyển đổi của phiên bản Spring Kafka đang dùng. Nếu cấu hình đơn giản, placeholder từ application.yml thường dễ bảo trì hơn.

## 10. Thời điểm SpEL được đánh giá

SpEL trong @KafkaListener được Spring phân giải khi listener endpoint được xử lý và đăng ký trong quá trình khởi tạo ứng dụng. Giá trị sau khi phân giải được dùng để tạo và cấu hình listener container.

Điều này có một số hệ quả:

- Expression không được đánh giá lại cho từng record.
- Thay đổi property hoặc giá trị bean sau khi container đã khởi tạo không tự động làm listener subscribe topic mới.
- Thay đổi cấu hình group ID không tự động di chuyển consumer sang group mới trong một container đang chạy.
- Nếu muốn đổi subscription, cần thực hiện qua vòng đời container hoặc cơ chế cập nhật subscription phù hợp, có kiểm soát.

~~~mermaid
flowchart TD
    A["Spring Application khởi động"] --> B["Khởi tạo bean cấu hình"]
    B --> C["Xử lý @KafkaListener"]
    C --> D["Phân giải placeholder và SpEL"]
    D --> E["Đăng ký listener endpoint"]
    E --> F["Tạo listener container"]
    F --> G["Consumer subscribe và join group"]
    G --> H["Poll và gọi listener"]
~~~

Vì expression được đánh giá trong quá trình khởi tạo endpoint, bean được tham chiếu phải sẵn sàng trong ApplicationContext. Tránh phụ thuộc vòng giữa listener bean và bean cung cấp cấu hình topic.

## 11. Kết hợp SpEL với cấu hình nhiều môi trường

Một ứng dụng có thể dùng cùng một listener nhưng nhận topic khác nhau theo profile hoặc biến môi trường.

application-dev.yml:

~~~yaml
app:
  kafka:
    topics:
      order-created: dev.commerce.order.created
    consumer-groups:
      billing: billing-service-dev
~~~

application-prod.yml:

~~~yaml
app:
  kafka:
    topics:
      order-created: commerce.order.created
    consumer-groups:
      billing: billing-service
~~~

Listener:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.order-created}",
    groupId = "${app.kafka.consumer-groups.billing}"
)
public void handle(OrderCreated event) {
    // Logic xử lý giống nhau ở mọi môi trường.
}
~~~

Spring nạp property source phù hợp với profile đang hoạt động. Listener không cần thay đổi mã nguồn giữa development và production.

Cần lưu ý group ID khác nhau giữa môi trường tạo tiến độ đọc độc lập. Đây thường là chủ đích để dữ liệu development không dùng chung offset với production.

## 12. Kiểm tra giá trị expression trước khi tạo listener

Expression có thể hợp lệ về cú pháp nhưng trả về giá trị không hợp lệ cho Kafka.

Ví dụ các vấn đề:

- Bean được tham chiếu không tồn tại.
- Property topic bị null hoặc chuỗi rỗng.
- Expression trả về sai kiểu dữ liệu.
- Tên topic sai quy tắc Kafka.
- groupId thay đổi ngoài ý muốn giữa các lần deploy.
- topicPattern không phải regex hợp lệ.
- Bean cấu hình chưa được đăng ký trong ApplicationContext.

Nên xác thực cấu hình ngay khi ứng dụng khởi động:

~~~java
@Component
public class KafkaTopicPropertiesValidator {

    private final KafkaTopicProperties properties;

    public KafkaTopicPropertiesValidator(
            KafkaTopicProperties properties) {
        this.properties = properties;
    }

    @PostConstruct
    public void validate() {
        if (properties.getOrderCreated() == null
                || properties.getOrderCreated().isBlank()) {
            throw new IllegalStateException(
                "Kafka topic orderCreated must not be blank"
            );
        }
    }
}
~~~

Validation giúp lỗi cấu hình xuất hiện sớm với thông báo rõ ràng, thay vì đợi consumer subscribe hoặc nhận record mới phát hiện.

Nếu cần kiểm tra tên topic kỹ hơn, có thể dùng một validator riêng để kiểm tra ký tự, độ dài và convention của tổ chức.

## 13. Các lỗi thường gặp khi dùng SpEL

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Could not resolve placeholder | Thiếu property hoặc sai tên key | Kiểm tra application.yml, profile và biến môi trường |
| Bean reference không tồn tại | Sai bean name hoặc bean chưa được đăng ký | Kiểm tra tên trong @Component/@Bean và component scan |
| SpEL parse exception | Sai cú pháp expression, dấu nháy hoặc ngoặc | Kiểm tra expression và escape ký tự |
| Expression trả về null | Property bean chưa được bind hoặc giá trị chưa cấu hình | Validate bean trước khi tạo listener |
| Listener subscribe sai topic | Tham chiếu nhầm property hoặc expression chọn sai nhánh | Log giá trị cấu hình đã phân giải và kiểm tra profile |
| Consumer group thay đổi sau deploy | groupId expression phụ thuộc giá trị biến đổi | Dùng group ID ổn định |
| Topic pattern nhận quá nhiều topic | Regex quá rộng | Giới hạn prefix và kiểm tra regex |
| Listener không đổi topic sau khi sửa config | Expression đã được đánh giá lúc đăng ký endpoint | Khởi tạo lại container hoặc áp dụng quy trình cập nhật subscription |
| Lỗi chuyển kiểu concurrency | Expression trả về chuỗi không chuyển được thành số | Kiểm tra giá trị và kiểu dữ liệu |
| Không tìm thấy topic khi start | Tên topic không tồn tại hoặc broker không cho auto-create | Kiểm tra topic và chính sách tạo topic |

## 14. Kiểm thử @KafkaListener dùng SpEL

Kiểm thử nên xác nhận cả giá trị cấu hình được phân giải lẫn hành vi nhận record.

Các bước gợi ý:

1. Khởi tạo Spring context với property test riêng.
2. Đăng ký bean cấu hình topic và consumer group.
3. Đăng ký listener dùng SpEL.
4. Khởi chạy Kafka thử nghiệm bằng EmbeddedKafka hoặc Testcontainers.
5. Gửi record vào topic mà expression dự kiến trả về.
6. Xác nhận listener nhận đúng payload.
7. Gửi record vào một topic khác để xác nhận listener không nhận nhầm.
8. Nếu dùng topicPattern, tạo một topic khớp regex và một topic không khớp.
9. Xác nhận group ID của listener đúng với cấu hình.

Ví dụ kiểm thử tích hợp có thể dùng EmbeddedKafka:

~~~java
@SpringBootTest(properties = {
    "app.kafka.topics.order-created=test.commerce.order.created",
    "app.kafka.consumer-groups.billing=test-billing-group"
})
@EmbeddedKafka(
    partitions = 1,
    topics = "test.commerce.order.created"
)
class OrderEventListenerTest {

    @Autowired
    private KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @Test
    void shouldConsumeFromTopicResolvedBySpel() throws Exception {
        OrderCreated event = new OrderCreated(
            "order-10001",
            "customer-20001",
            1250000
        );

        kafkaTemplate.send(
            "test.commerce.order.created",
            event.orderId(),
            event
        ).get(10, TimeUnit.SECONDS);

        // Xác nhận listener đã xử lý event bằng latch hoặc test probe.
    }
}
~~~

Phần assertion nên dùng CountDownLatch, Awaitility hoặc test probe để đợi listener xử lý bất đồng bộ. Không dùng Thread.sleep cố định làm bằng chứng chắc chắn rằng listener đã nhận record.

Nếu kiểm thử group ID, có thể kiểm tra container đã đăng ký trong KafkaListenerEndpointRegistry hoặc quan sát consumer group trên broker test.

## 15. Nguyên tắc thiết kế expression dễ bảo trì

- Ưu tiên placeholder khi chỉ cần đọc một giá trị từ cấu hình.
- Dùng SpEL khi cần tham chiếu bean hoặc tính giá trị đơn giản.
- Đặt tên bean cấu hình rõ nghĩa và ổn định.
- Giữ expression ngắn, tránh nhiều nhánh điều kiện lồng nhau.
- Không thực hiện I/O hoặc side effect trong expression.
- Không đưa dữ liệu đầu vào không tin cậy vào expression để đánh giá.
- Validate topic, group ID và pattern trước khi tạo listener.
- Giữ group ID ổn định để không vô tình tạo consumer group mới.
- Không nhầm listener id với Kafka groupId.
- Kiểm thử giá trị đã phân giải và hành vi subscribe thực tế.

## 16. Checklist trước khi đưa listener dùng SpEL vào vận hành

- [ ] Đã chọn placeholder hay SpEL đúng với nhu cầu?
- [ ] Bean được tham chiếu đã được đăng ký trong ApplicationContext?
- [ ] Bean name trong expression chính xác?
- [ ] Expression trả về kiểu dữ liệu phù hợp với annotation attribute?
- [ ] Topic không null, không rỗng và đúng quy ước Kafka?
- [ ] topicPattern là regex có phạm vi phù hợp?
- [ ] Chỉ dùng một trong topics, topicPattern hoặc topicPartitions?
- [ ] groupId ổn định qua các lần restart và deploy?
- [ ] Đã phân biệt id của listener với groupId?
- [ ] Đã hiểu expression được đánh giá khi đăng ký endpoint?
- [ ] Không kỳ vọng đổi bean property sẽ tự đổi subscription đang chạy?
- [ ] Không có I/O hoặc side effect trong expression?
- [ ] Có validation và thông báo lỗi cấu hình rõ ràng?
- [ ] Có kiểm thử với topic thực tế và group ID dự kiến?

## Kết luận

SpEL trong @KafkaListener cho phép lấy cấu hình listener từ bean Spring và biểu diễn các lựa chọn đơn giản bằng expression. Property placeholder `${...}` phù hợp với giá trị cấu hình trực tiếp; SpEL `#{...}` phù hợp khi cần tham chiếu bean, gọi getter/phương thức hoặc chọn giá trị theo điều kiện. Pseudo bean `__listener` còn giúp listener tham chiếu cấu hình của chính bean chứa nó.

Các expression được phân giải trong quá trình đăng ký listener endpoint, không phải mỗi lần nhận record. Vì vậy, bean cấu hình cần sẵn sàng khi ứng dụng khởi động, topic và group ID phải được kiểm tra trước, và thay đổi cấu hình sau khi container chạy cần quy trình cập nhật có kiểm soát. Dùng expression ngắn gọn, rõ nghĩa và có kiểm thử sẽ giúp @KafkaListener linh hoạt giữa các môi trường mà vẫn giữ consumer group và subscription ổn định.

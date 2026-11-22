# Dùng property placeholder trong annotation

Spring Kafka cho phép dùng property placeholder trong các thuộc tính của @KafkaListener để lấy topic, consumer group, concurrency và các thiết lập listener từ cấu hình bên ngoài. Cách này giúp cùng một mã nguồn chạy ở local, test, staging và production với giá trị cấu hình khác nhau.

Placeholder có dạng ${property.name}. Spring lấy giá trị từ Environment rồi thay vào annotation khi tạo listener endpoint. Có thể khai báo giá trị mặc định bằng cú pháp ${property.name:default}. Khi cần biểu thức hoặc tham chiếu bean, Spring hỗ trợ SpEL với cú pháp #{...}; hai cơ chế này có mục đích khác nhau và không nên nhầm lẫn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cách Spring resolve property placeholder trong annotation.
- Dùng placeholder cho topics, topicPattern, groupId, concurrency và containerFactory.
- Khai báo nhiều topic và giá trị mặc định an toàn.
- Phân biệt placeholder ${...} với SpEL #{...}.
- Tổ chức cấu hình theo application.yml, profile, environment variable và command line.
- Hiểu quan hệ giữa id, groupId và group.id trong @KafkaListener.
- Nhận biết lỗi placeholder không tồn tại, giá trị sai kiểu và cấu hình rỗng.
- Kiểm thử listener với các giá trị cấu hình khác nhau.
- Hiểu vì sao thay đổi cấu hình ngoài runtime không tự cập nhật endpoint đang chạy.

## 1. Property placeholder hoạt động như thế nào?

Property placeholder là một tham chiếu đến giá trị trong Spring Environment. Thay vì viết cứng topic hoặc group ID trong annotation, ta đặt tên property:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.orders}",
    groupId = "${app.kafka.consumer.group-id}"
)
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Giả sử cấu hình có:

~~~yaml
app:
  kafka:
    topics:
      orders: orders.v1
    consumer:
      group-id: order-service
~~~

Khi Spring đăng ký listener endpoint, các giá trị được resolve thành:

- topics = orders.v1
- groupId = order-service

Luồng xử lý khái quát:

~~~mermaid
flowchart TD
    A["application.yml / environment / profile"] --> B["Spring Environment"]
    B --> C["Resolve property placeholder"]
    C --> D["@KafkaListener endpoint"]
    D --> E["Listener container factory"]
    E --> F["Consumer và listener container"]
    F --> G["Đăng ký với Kafka"]
~~~

Việc resolve diễn ra trong giai đoạn khởi tạo application context và đăng ký listener endpoint. Listener container nhận các giá trị đã được xử lý để tạo consumer và subscribe topic tương ứng.

Placeholder chỉ là cơ chế lấy cấu hình. Nó không tự tạo topic trên Kafka, không xác minh schema message và cũng không thay thế cấu hình serializer/deserializer.

## 2. Cấu hình topic và group ID bên ngoài annotation

Một cách tổ chức phổ biến là đặt các giá trị ứng dụng cần dùng trong application.yml:

~~~yaml
app:
  kafka:
    topics:
      orders: orders.v1
      refunds: refunds.v1
      audit: audit.events
    consumer:
      group-id: order-service
    listener:
      concurrency: 3
      auto-startup: true
~~~

Listener dùng các property này:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        id = "orders-listener",
        topics = "${app.kafka.topics.orders}",
        groupId = "${app.kafka.consumer.group-id}",
        concurrency = "${app.kafka.listener.concurrency:1}",
        autoStartup = "${app.kafka.listener.auto-startup:true}"
    )
    public void onOrder(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

Một số thuộc tính thường được đưa ra ngoài annotation:

| Annotation attribute | Property placeholder phù hợp |
|---|---|
| topics | Tên topic hoặc các topic được khai báo riêng |
| topicPattern | Regex để chọn topic |
| groupId | Consumer group của listener |
| clientIdPrefix | Prefix client ID để quan sát consumer |
| concurrency | Số consumer con của listener container |
| containerFactory | Tên listener container factory |
| autoStartup | Bật/tắt việc tự khởi động container |

Hãy đưa ra ngoài cấu hình những giá trị thay đổi theo môi trường hoặc cần điều chỉnh vận hành. Các thông tin định danh ổn định của listener như id thường có thể giữ trong mã nguồn để dễ quản lý lifecycle và log.

## 3. Dùng placeholder cho nhiều topic

Thuộc tính topics của @KafkaListener nhận một mảng tên topic. Khi cần nghe nhiều topic, khai báo từng placeholder thành một phần tử của mảng:

~~~java
@KafkaListener(
    id = "order-domain-listener",
    topics = {
        "${app.kafka.topics.orders}",
        "${app.kafka.topics.refunds}"
    },
    groupId = "${app.kafka.consumer.group-id}"
)
public void onDomainEvent(Object event) {
    domainService.handle(event);
}
~~~

Cấu hình:

~~~yaml
app:
  kafka:
    topics:
      orders: orders.v1
      refunds: refunds.v1
    consumer:
      group-id: order-domain-service
~~~

Khai báo từng topic giúp người đọc thấy rõ các nguồn dữ liệu mà listener sử dụng. Không mặc định rằng một chuỗi phân tách bằng dấu phẩy trong một property sẽ luôn được tách thành nhiều phần tử của mảng annotation; cách chuyển đổi phụ thuộc vị trí và cơ chế binding. Với topics dạng mảng, cách rõ ràng nhất là đặt một placeholder cho mỗi phần tử.

Nếu danh sách topic cần thay đổi thường xuyên hoặc được quản lý như một danh sách cấu hình, cân nhắc dùng @ConfigurationProperties và tạo endpoint/container theo cách lập trình thay vì cố nhồi danh sách động vào annotation.

## 4. Placeholder cho topicPattern

Nếu listener cần subscribe các topic theo regex, dùng topicPattern:

~~~yaml
app:
  kafka:
    topics:
      order-pattern: "orders\\..*"
~~~

~~~java
@KafkaListener(
    id = "all-order-topics-listener",
    topicPattern = "${app.kafka.topics.order-pattern}",
    groupId = "${app.kafka.consumer.group-id}"
)
public void onOrderTopicEvent(OrderEvent event) {
    orderService.process(event);
}
~~~

Ví dụ regex có thể khớp các topic như orders.created, orders.updated hoặc orders.cancelled. Pattern được áp dụng khi consumer đăng ký topic pattern và metadata được cập nhật.

Cần phân biệt:

- topics khai báo các tên topic cụ thể.
- topicPattern khai báo biểu thức chính quy để chọn topic.
- topicPartitions chỉ định partition cụ thể.

Đây là các cách khai báo subscription/assignment khác nhau. Không khai báo đồng thời chúng như thể listener sẽ hợp nhất mọi danh sách.

## 5. Placeholder cho concurrency và container factory

Concurrency quyết định số consumer con mà ConcurrentMessageListenerContainer tạo cho listener endpoint. Có thể cấu hình theo môi trường:

~~~yaml
app:
  kafka:
    listener:
      concurrency: 3
      container-factory: orderListenerContainerFactory
~~~

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "${app.kafka.topics.orders}",
    groupId = "${app.kafka.consumer.group-id}",
    concurrency = "${app.kafka.listener.concurrency:1}",
    containerFactory = "${app.kafka.listener.container-factory:kafkaListenerContainerFactory}"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Nếu topic có sáu partition, concurrency bằng ba cho phép tối đa ba consumer con nhận partition của topic. Nếu concurrency lớn hơn số partition, một số consumer con có thể không được gán partition.

Giá trị concurrency cần là số nguyên dương hợp lệ. Nếu property chứa chuỗi không chuyển được thành số, listener endpoint có thể không khởi tạo được. Nên kiểm tra giá trị ở cấu hình triển khai và chọn default có chủ đích.

Nếu mỗi listener có yêu cầu khác nhau, có thể tạo nhiều container factory. Placeholder containerFactory giúp chọn factory theo môi trường, nhưng tên property phải trỏ đến đúng bean factory đã được đăng ký trong application context.

## 6. Giá trị mặc định với cú pháp colon

Spring hỗ trợ giá trị mặc định trong placeholder:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.orders:orders}",
    groupId = "${app.kafka.consumer.group-id:order-service}",
    concurrency = "${app.kafka.listener.concurrency:1}"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Cú pháp có dạng:

~~~text
${property.name:defaultValue}
~~~

Nếu property không tồn tại, Spring dùng giá trị sau dấu hai chấm. Điều này hữu ích cho cấu hình local hoặc giá trị mặc định an toàn.

Tuy nhiên, default không nên che giấu lỗi cấu hình production. Ví dụ, nếu production yêu cầu topic riêng theo tenant hoặc group ID riêng cho từng service, dùng default chung có thể khiến nhiều instance vô tình đọc cùng group hoặc ghi vào nhầm topic.

Cũng cần phân biệt property không tồn tại với property tồn tại nhưng giá trị rỗng. Default thường được dùng khi không resolve được property; một giá trị rỗng đã được khai báo có thể vẫn được giữ là chuỗi rỗng. Hãy validate cấu hình bắt buộc thay vì dựa hoàn toàn vào placeholder default.

### Khi nào nên dùng default?

| Property | Có nên đặt default? | Lý do |
|---|---|---|
| concurrency | Thường có | Có thể chọn mức thấp an toàn cho local |
| autoStartup | Có thể có | Có thể mặc định true theo hành vi ứng dụng |
| groupId | Tùy môi trường | Default chung có thể làm nhiều service dùng chung group ngoài ý muốn |
| topic bắt buộc của production | Thận trọng | Default có thể khiến dữ liệu được gửi/đọc nhầm topic |
| containerFactory | Có thể có | Chỉ khi factory mặc định chắc chắn tồn tại |

## 7. Phân biệt placeholder và SpEL

Spring hỗ trợ hai cú pháp trong annotation:

| Cú pháp | Cơ chế | Mục đích |
|---|---|---|
| ${property.name} | Property placeholder | Đọc giá trị từ Spring Environment |
| #{expression} | Spring Expression Language (SpEL) | Tính biểu thức, gọi bean hoặc truy cập property/method |

Placeholder phù hợp với giá trị cấu hình đơn giản:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.orders}",
    groupId = "${app.kafka.consumer.group-id}"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

SpEL phù hợp khi giá trị cần lấy từ bean hoặc được tính toán:

~~~java
@KafkaListener(
    topics = "#{@kafkaTopicSettings.ordersTopic}",
    groupId = "#{@consumerSettings.groupId}"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Ví dụ bean cung cấp giá trị:

~~~java
@Component("kafkaTopicSettings")
public class KafkaTopicSettings {

    public String getOrdersTopic() {
        return "orders.v1";
    }
}
~~~

Trong SpEL, cú pháp @beanName truy cập bean trong application context. Biểu thức được đánh giá trong ngữ cảnh SpEL mà Spring Kafka cung cấp khi tạo endpoint.

Không dùng SpEL chỉ vì placeholder chưa hoạt động. Trước tiên kiểm tra property source và tên property. Ngược lại, nếu cần gọi bean hoặc tính giá trị, dùng SpEL sẽ diễn đạt đúng mục đích hơn.

Có thể kết hợp hai cơ chế trong một biểu thức SpEL, nhưng cú pháp lồng nhau khó đọc và dễ lỗi. Chỉ dùng khi thực sự cần; với cấu hình thông thường, giữ ${...} cho property và #{...} cho biểu thức là cách dễ bảo trì.

## 8. Property source: application.yml, profile và environment variable

Spring Environment có thể nhận property từ nhiều nguồn. Trong Spring Boot, các nguồn thường gặp gồm:

- application.yml hoặc application.properties.
- File cấu hình theo profile như application-dev.yml, application-prod.yml.
- Environment variable trong môi trường chạy.
- Java system properties.
- Command-line arguments.
- Các nguồn cấu hình ngoài khác được ứng dụng tích hợp.

Ví dụ cấu hình mặc định:

~~~yaml
# application.yml
app:
  kafka:
    topics:
      orders: orders.local
    consumer:
      group-id: order-service-local
~~~

Cấu hình production:

~~~yaml
# application-prod.yml
app:
  kafka:
    topics:
      orders: orders.production
    consumer:
      group-id: order-service
~~~

Kích hoạt profile:

~~~bash
java -jar messaging-service.jar --spring.profiles.active=prod
~~~

Có thể override bằng environment variable:

~~~bash
APP_KAFKA_TOPICS_ORDERS=orders.production-v2
APP_KAFKA_CONSUMER_GROUPID=order-service-v2
~~~

Hoặc command line:

~~~bash
java -jar messaging-service.jar \
  --app.kafka.topics.orders=orders.canary \
  --app.kafka.consumer.group-id=order-service-canary
~~~

Spring Boot áp dụng quy tắc binding và độ ưu tiên giữa các property source. Khi có nhiều nguồn cùng khai báo một key, giá trị từ nguồn có độ ưu tiên cao hơn sẽ thắng. Hãy kiểm tra cấu hình hiệu lực của môi trường triển khai thay vì chỉ đọc file application.yml trong repository.

## 9. Sử dụng placeholder với @TopicPartition

Khi listener cần assignment tĩnh, các giá trị topic và partition cũng có thể được cấu hình bằng placeholder trong các thuộc tính annotation tương ứng.

Ví dụ:

~~~yaml
app:
  kafka:
    topics:
      orders: orders.v1
    partitions:
      orders: "0"
~~~

~~~java
@KafkaListener(
    id = "orders-partition-listener",
    groupId = "${app.kafka.consumer.group-id}",
    topicPartitions = @TopicPartition(
        topic = "${app.kafka.topics.orders}",
        partitions = {"${app.kafka.partitions.orders:0}"}
    )
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Trong ví dụ, listener được gán partition 0 của topic đã cấu hình. Partition index là chuỗi trong annotation; giá trị phải chuyển được thành partition hợp lệ và partition đó phải tồn tại trên topic.

Nếu dùng partitionOffsets và @PartitionOffset, initialOffset cũng có thể được lấy từ property:

~~~java
@KafkaListener(
    id = "orders-replay-listener",
    groupId = "${app.kafka.replay.group-id}",
    topicPartitions = @TopicPartition(
        topic = "${app.kafka.topics.orders}",
        partitionOffsets = @PartitionOffset(
            partition = "0",
            initialOffset = "${app.kafka.replay.initial-offset:0}"
        )
    )
)
public void replay(OrderEvent event) {
    replayService.handle(event);
}
~~~

Hãy phân biệt initial offset với committed offset của group. Một job replay nên dùng group ID riêng để tránh làm thay đổi vị trí đọc mà consumer production đang sử dụng. Cách xử lý initial seek và committed offset có thể chịu ảnh hưởng bởi phiên bản Spring Kafka và cấu hình container; cần xác nhận theo phiên bản thư viện thực tế.

## 10. Quan hệ giữa id và groupId trong @KafkaListener

Hai thuộc tính này có mục đích khác nhau:

- id định danh listener endpoint/container trong Spring Kafka. Có thể dùng ID này để tìm container trong KafkaListenerEndpointRegistry, dừng, chạy hoặc pause listener.
- groupId xác định consumer group dùng để chia partition và lưu offset.
- idIsGroup điều khiển việc dùng id làm group ID khi groupId không được khai báo. Mặc định idIsGroup là true trong các phiên bản Spring Kafka hỗ trợ thuộc tính này.

Ví dụ khai báo rõ cả hai:

~~~java
@KafkaListener(
    id = "orders-listener",
    idIsGroup = false,
    topics = "${app.kafka.topics.orders}",
    groupId = "${app.kafka.consumer.group-id}"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Khi đã khai báo groupId, group ID được lấy từ property đó. Đặt idIsGroup=false giúp thể hiện rõ rằng ID chỉ dùng để quản lý endpoint. Nếu bỏ groupId và để idIsGroup=true, id có thể được dùng làm group ID thay cho group.id cấu hình chung.

Điều này quan trọng khi có nhiều listener trong cùng ứng dụng: mỗi listener có thể cần group ID riêng dù cùng một class hoặc cùng một topic.

## 11. Lỗi thường gặp khi resolve placeholder

| Lỗi | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Could not resolve placeholder | Property chưa được khai báo hoặc file/profile chưa được nạp | Kiểm tra tên property, profile và nguồn cấu hình |
| Topic rỗng | Property tồn tại nhưng giá trị rỗng | Validate giá trị bắt buộc và kiểm tra biến môi trường |
| Invalid concurrency | Property không phải số nguyên dương | Kiểm tra giá trị sau khi resolve |
| Container factory không tồn tại | Placeholder trỏ đến tên bean sai | Kiểm tra tên @Bean factory trong context |
| Listener dùng sai group | groupId bị override hoặc idIsGroup gây nhầm lẫn | Khai báo groupId rõ ràng và kiểm tra effective config |
| Listener nghe sai topic | Property source khác ghi đè giá trị | Kiểm tra profile và cấu hình hiệu lực |
| Thay file nhưng listener không đổi | Endpoint đã được tạo và container đang chạy | Khởi động lại hoặc cập nhật container theo cơ chế quản lý |

Khi placeholder bắt buộc không resolve được, Spring thường báo lỗi trong quá trình tạo application context hoặc đăng ký listener. Đây là lỗi startup cần được xử lý sớm; không nên bỏ qua bằng cách cấu hình ignore unresolved placeholder cho toàn ứng dụng nếu listener cần giá trị đó để chạy đúng.

## 12. Validate cấu hình trước khi tạo listener

Với ứng dụng có nhiều topic và listener, nên gom cấu hình vào một lớp rõ ràng bằng @ConfigurationProperties. Annotation vẫn có thể dùng placeholder cho các trường cần thiết, còn cấu hình phức tạp được validate tập trung.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.kafka")
@Validated
public class KafkaApplicationProperties {

    @NotBlank
    private String ordersTopic;

    @NotBlank
    private String consumerGroupId;

    @Min(1)
    @Max(20)
    private int concurrency = 1;

    // getters và setters
}
~~~

Cấu hình trên minh họa ý tưởng validate giá trị bắt buộc và giới hạn concurrency. Nếu dùng cấu trúc YAML lồng như topics.orders và consumer.group-id, hãy định nghĩa các class lồng tương ứng thay vì ép các property vào tên phẳng.

Có thể inject bean cấu hình vào service hoặc factory. Với annotation, property placeholder là cách đơn giản để lấy giá trị tại thời điểm đăng ký endpoint. Với cấu hình cần kiểm tra chéo hoặc thay đổi cấu trúc, @ConfigurationProperties dễ tổ chức và kiểm thử hơn.

## 13. Kiểm thử listener với các giá trị cấu hình khác nhau

Kiểm thử cần xác nhận endpoint thực sự dùng đúng topic và group ID sau khi resolve, không chỉ kiểm tra file YAML có chứa property.

Có thể override property trong test:

~~~java
@SpringBootTest(properties = {
    "app.kafka.topics.orders=orders-test",
    "app.kafka.consumer.group-id=order-test-group",
    "app.kafka.listener.concurrency=1"
})
class OrderListenerTest {
    // Integration test với Kafka broker hoặc EmbeddedKafka.
}
~~~

Các kịch bản hữu ích:

- Khởi chạy application context với property hợp lệ và xác nhận listener endpoint được tạo.
- Override topic trong test để bảo đảm listener nghe topic test thay vì topic môi trường thật.
- Override group ID và xác nhận consumer thuộc đúng group.
- Bỏ property bắt buộc để xác nhận ứng dụng fail-fast với thông báo dễ hiểu.
- Đặt concurrency không hợp lệ và xác nhận lỗi được phát hiện khi khởi tạo.
- Kiểm tra profile dev/prod chọn đúng topic và group.
- Kiểm tra placeholder default khi property không tồn tại.
- Kiểm tra topicPattern và topicPartitions nếu ứng dụng dùng các kiểu endpoint đó.

Với integration test, hãy đồng bộ theo trạng thái listener/container và message thực nhận. Không dựa vào sleep ngắn để kết luận endpoint đã subscribe hoặc assignment đã hoàn tất.

## 14. Khi nào thay đổi property có hiệu lực?

Placeholder trong @KafkaListener được resolve khi Spring tạo endpoint. Vì vậy, thay đổi application.yml hoặc environment variable sau khi listener đã khởi động không tự động cập nhật topic, group ID hoặc concurrency của container đang chạy.

Để thay đổi cấu hình, có thể:

1. Restart ứng dụng để endpoint được tạo lại với property mới.
2. Quản lý container qua KafkaListenerEndpointRegistry và dừng/khởi động lại theo cấu hình được cập nhật.
3. Với nhu cầu thay đổi động thực sự, tạo và quản lý listener container bằng code thay vì chỉ dựa vào annotation tĩnh.

Không sửa trực tiếp Environment rồi kỳ vọng annotation đang chạy tự được resolve lại. Placeholder không phải cơ chế hot reload listener.

Nếu hệ thống dùng Spring Cloud refresh hoặc một config server, việc refresh bean cấu hình không đồng nghĩa listener endpoint được đăng ký lại tự động. Cần có logic lifecycle rõ ràng và kiểm thử việc thay đổi assignment/topic trước khi triển khai.

## 15. Checklist sử dụng placeholder trong @KafkaListener

- [ ] Property topic và group ID được khai báo trong nguồn cấu hình phù hợp.
- [ ] Placeholder có tên chính xác và không bị sai profile.
- [ ] Giá trị bắt buộc không rỗng.
- [ ] Default chỉ dùng cho trường hợp thực sự an toàn.
- [ ] Nhiều topic được khai báo rõ ràng theo từng phần tử.
- [ ] topicPattern và topicPartitions được dùng đúng mục đích.
- [ ] concurrency là số nguyên dương và phù hợp số partition.
- [ ] containerFactory trỏ đến bean đã đăng ký.
- [ ] id và groupId được phân biệt rõ.
- [ ] SpEL chỉ dùng khi cần biểu thức hoặc truy cập bean.
- [ ] Test có thể override property mà không chạm topic production.
- [ ] Có quy trình restart hoặc cập nhật container khi cấu hình thay đổi.

## Kết luận

Property placeholder giúp tách cấu hình của @KafkaListener khỏi mã nguồn. Dùng ${...} để lấy topic, group ID, concurrency và container factory từ Spring Environment; dùng ${...:default} cho giá trị mặc định có chủ đích. SpEL #{...} phù hợp khi cần biểu thức hoặc tham chiếu bean. Hãy phân biệt id với groupId, kiểm tra property source theo môi trường, validate giá trị trước khi tạo listener và nhớ rằng thay đổi cấu hình sau startup không tự cập nhật endpoint đang chạy. Cách tổ chức này giúp Spring Kafka dễ triển khai giữa các môi trường và giảm lỗi do hard-code topic hoặc consumer group.


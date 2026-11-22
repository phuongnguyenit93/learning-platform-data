# Cấu hình broker nhúng

Broker nhúng (embedded broker) cho phép chạy một Kafka broker ngay trong tiến trình kiểm thử, nhờ đó bài test có thể gửi và nhận record qua Kafka thật mà không cần khởi động một cluster bên ngoài. Spring Kafka cung cấp hỗ trợ này trong module `spring-kafka-test`, chủ yếu qua annotation `@EmbeddedKafka` và interface `EmbeddedKafkaBroker`.

Broker nhúng phù hợp để kiểm tra luồng producer, consumer, listener container, serialization, partition và offset trong môi trường tự động. Nó giúp test gần với hành vi Kafka thực hơn mock, nhưng không thay thế kiểm thử cluster nhiều broker, replication hoặc hạ tầng bảo mật production.

## 1. Thêm dependency kiểm thử

Với Maven, thêm `spring-kafka-test` ở scope `test`. Hãy để Spring Boot dependency management hoặc Spring Kafka BOM quản lý version tương thích với `spring-kafka` đang dùng:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Với Gradle:

```kotlin
dependencies {
    testImplementation("org.springframework.kafka:spring-kafka-test")
}
```

Nếu dự án dùng Spring Boot, có thể dùng starter Kafka test do phiên bản Boot cung cấp; trong mọi trường hợp, dependency test cần tương thích với dòng Spring Kafka và Kafka client của ứng dụng. Không đưa thư viện test này vào runtime artifact của service.

## 2. Khởi tạo broker bằng @EmbeddedKafka

`@EmbeddedKafka` khởi tạo broker cho test class và tạo sẵn topic theo khai báo. Ví dụ:

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderConsumerIntegrationTest {

    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @Autowired
    private KafkaTemplate<String, OrderEvent> kafkaTemplate;

    // Các test dùng broker và topic orders.
}
```

Spring Kafka đăng ký `EmbeddedKafkaBroker` trong test context để có thể inject vào test. Thuộc tính `bootstrapServersProperty` ánh xạ địa chỉ broker nhúng vào `spring.kafka.bootstrap-servers`, nhờ đó Spring Boot auto-configuration tạo producer và consumer kết nối đến broker test.

Từ Spring Kafka 3.0.10, thuộc tính này mặc định được ánh xạ sang `spring.kafka.bootstrap-servers` khi kiểm thử Spring Boot. Khai báo tường minh trong annotation giúp ý định cấu hình dễ thấy và tương thích với các version cũ hơn có hỗ trợ thuộc tính này.

## 3. Cấu hình số broker, partition và port

Các thuộc tính thường dùng của `@EmbeddedKafka` gồm:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `count` | Số broker nhúng cần khởi chạy. |
| `partitions` | Số partition mặc định cho các topic được tạo bởi annotation. |
| `topics` | Danh sách topic được tạo trước khi test chạy. |
| `ports` | Port broker; dùng `0` để chọn port ngẫu nhiên. |
| `brokerProperties` | Các thuộc tính cấu hình broker dạng `key=value`. |
| `brokerPropertiesLocation` | Resource chứa các thuộc tính broker bổ sung. |

Ví dụ tạo một broker, hai partition và port ngẫu nhiên:

```java
@EmbeddedKafka(
    count = 1,
    partitions = 2,
    topics = { "orders", "order-events" },
    ports = 0,
    bootstrapServersProperty = "spring.kafka.bootstrap-servers")
```

Port ngẫu nhiên giúp tránh xung đột khi chạy nhiều test suite trên cùng máy hoặc trong CI. Hạn chế cố định port nếu không có lý do rõ ràng; một process khác có thể đã chiếm port đó.

Nếu cần cấu hình broker sâu hơn, dùng `brokerProperties`, ví dụ điều chỉnh `auto.create.topics.enable` hoặc thư mục log. Các thuộc tính phụ thuộc phiên bản Kafka; chỉ đặt những giá trị mà broker version đang dùng hỗ trợ.

## 4. Tạo topic trong lúc kiểm thử

Topic khai báo trong `@EmbeddedKafka` được tạo khi broker khởi động. Nếu test cần topic có cấu hình riêng, có thể tạo qua `EmbeddedKafkaBroker.addTopics(...)`:

```java
@SpringBootTest
@EmbeddedKafka(bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class RetryTopicTest {
    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @BeforeAll
    void createTestTopic() {
        embeddedKafka.addTopics(
            new NewTopic("orders-retry", 3, (short) 1));
    }
}
```

Ví dụ tạo topic retry có ba partition và replication factor bằng một, phù hợp với broker đơn. Mặc định, `addTopics` ném exception nếu tạo topic gặp lỗi, chẳng hạn topic đã tồn tại. Có overload trả về map kết quả để test có thể kiểm tra từng topic khi cần xử lý trường hợp đã tồn tại.

Tên topic nên tách biệt giữa các test hoặc test class để dữ liệu của bài test trước không làm sai kết quả bài test sau. Nếu tái sử dụng một broker cho nhiều test, đừng mặc định topic đã sạch sau mỗi method.

## 5. Kiểm tra Spring Boot kết nối đúng broker nhúng

Trong test dùng `@SpringBootTest`, `bootstrapServersProperty` phải trỏ đến property mà cấu hình ứng dụng thực sự đọc. Ví dụ với cấu hình mặc định:

```properties
spring.kafka.bootstrap-servers=${spring.embedded.kafka.brokers}
spring.kafka.consumer.group-id=orders-test
spring.kafka.consumer.auto-offset-reset=earliest
```

Có thể dùng placeholder `spring.embedded.kafka.brokers` do broker nhúng cung cấp. Tuy nhiên, chỉ chọn một cách ánh xạ bootstrap servers trong test: đặt `bootstrapServersProperty` trên annotation hoặc tham chiếu property broker nhúng trong cấu hình. Tránh để một cấu hình khác ghi đè địa chỉ broker.

Với Spring Kafka 3.0.10 trở lên, broker tự ánh xạ property sang `spring.kafka.bootstrap-servers` theo mặc định cho Spring Boot. Nếu dùng version cũ, khai báo mapping rõ ràng hoặc dùng placeholder theo tài liệu của version đó.

## 6. Gửi và nhận record trong test

Sau khi broker khởi động, test có thể dùng `KafkaTemplate` do ứng dụng cấu hình để gửi record. Dùng `Future.get` để chờ xác nhận gửi và một cơ chế chờ có giới hạn để đợi listener xử lý:

```java
@Test
void publishesOrderEvent() throws Exception {
    OrderEvent event = new OrderEvent("order-42", "CREATED");

    kafkaTemplate.send("orders", event.orderId(), event)
        .get(10, TimeUnit.SECONDS);

    await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
        assertThat(orderEventRecorder.events())
            .anyMatch(received -> received.orderId().equals("order-42")));
}
```

`await()` ở ví dụ là Awaitility. Chờ theo điều kiện giúp test không phụ thuộc vào một khoảng `Thread.sleep()` cố định. Nếu không dùng Awaitility, có thể dùng `CountDownLatch` hoặc một hàng đợi đồng bộ có timeout để nhận tín hiệu từ listener.

Đặt `auto-offset-reset=earliest` khi test consumer mới cần đọc record đã được gửi trước khi consumer bắt đầu. Nếu listener đã chạy trước producer và subscribe thành công, `latest` cũng có thể phù hợp; hãy chọn theo thứ tự khởi động của test thay vì dùng một giá trị cho mọi tình huống.

## 7. Dùng KafkaTestUtils với consumer kiểm thử

`KafkaTestUtils` cung cấp các helper để tạo consumer properties, đọc record và kiểm tra kết quả. Có thể dùng consumer độc lập để xác minh broker và serializer mà không phụ thuộc listener nghiệp vụ:

Đoạn code dưới đây dùng `KafkaTemplate<String, String>` để gửi chuỗi vào topic kiểm thử:

```java
Map<String, Object> props =
    KafkaTestUtils.consumerProps("orders-test-group", "false", embeddedKafka);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

ConsumerFactory<String, String> consumerFactory =
    new DefaultKafkaConsumerFactory<>(
        props, new StringDeserializer(), new StringDeserializer());

Consumer<String, String> consumer = consumerFactory.createConsumer();
try {
    embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");
    stringKafkaTemplate.send("orders", "order-42", "created")
        .get(10, TimeUnit.SECONDS);
    ConsumerRecord<String, String> record =
        KafkaTestUtils.getSingleRecord(consumer, "orders");
    assertThat(record.key()).isEqualTo("order-42");
} finally {
    consumer.close();
}
```

Consumer được tạo trong test phải được đóng trong `finally` hoặc try-with-resources nếu API/version đang dùng hỗ trợ. Helper `consumeFromAnEmbeddedTopic` có thể seek về offset đầu hoặc cuối tùy tham số; kiểm tra đúng overload để test không bỏ lỡ record đã gửi.

## 8. Vòng đời broker và Spring test context

Broker nhúng có chi phí khởi động, vì vậy Spring Kafka khuyến nghị dùng một broker cho nhiều test khi phù hợp và tách topic giữa các test. Khi dùng `@EmbeddedKafka` cùng Spring TestContext, broker gắn với application context. Với một số cấu hình `@SpringJUnitConfig`, tài liệu Spring Kafka khuyến nghị `@DirtiesContext` để tránh race condition khi JVM shutdown làm broker đóng trước khi context còn cần tài nguyên.

```java
@SpringJUnitConfig
@DirtiesContext
@EmbeddedKafka(topics = "orders")
class OrderMessagingTests {
    // Các test dùng chung broker trong context này.
}
```

`@DirtiesContext` làm context bị loại khỏi cache sau test class và có thể khiến suite chậm hơn. Chỉ dùng khi lifecycle của context/broker cần được cô lập hoặc theo khuyến nghị phù hợp với cấu hình test; không thêm một cách máy móc cho mọi method.

Spring Kafka từ 3.0 còn hỗ trợ global embedded broker qua JUnit Platform listener, nhưng tính năng này mặc định tắt. Không nên trộn global embedded broker với `@EmbeddedKafka` riêng từng test class trong cùng suite vì chúng dùng chung system properties và có thể gây cấu hình không mong muốn.

## 9. KRaft, ZooKeeper và tương thích phiên bản

Cách triển khai broker nhúng phụ thuộc phiên bản Kafka và Spring Kafka. Với Kafka 4.0, Kafka đã chuyển hoàn toàn sang KRaft; ZooKeeper không còn được hỗ trợ và Spring Kafka 4 chỉ còn implementation `EmbeddedKafkaKraftBroker`. Các thuộc tính cấu hình liên quan ZooKeeper trong annotation cũng đã bị loại bỏ.

Với dự án dùng Kafka hoặc Spring Kafka phiên bản cũ hơn, hãy theo tài liệu đúng version vì có thể còn khác biệt về KRaft, ZooKeeper và broker properties. Thông thường nên dùng `@EmbeddedKafka` để test không phụ thuộc trực tiếp vào implementation broker cụ thể.

## 10. Khi nào nên dùng Testcontainers?

Embedded broker chạy Kafka broker trong cùng tiến trình test, thuận tiện và nhanh cho kiểm thử listener, producer, offset, retry hoặc DLT ở mức tích hợp. Tuy nhiên, một broker đơn không mô phỏng đầy đủ replication, leader election, lỗi broker hoặc cấu hình cluster nhiều node.

| Nhu cầu kiểm thử | Lựa chọn phù hợp |
| --- | --- |
| Gửi/nhận record, listener, serializer, offset | Embedded Kafka |
| Retry, DLT và partition routing cơ bản | Embedded Kafka với topic được cấu hình rõ |
| Broker version cụ thể, nhiều broker, replication | Testcontainers với Kafka container phù hợp |
| TLS/SASL, ACL và cấu hình gần production | Testcontainers hoặc môi trường Kafka tích hợp chuyên biệt |
| Hành vi failover, mất broker, leader election | Cluster kiểm thử nhiều broker |

Không dùng mock broker để kết luận hành vi protocol hoặc broker configuration đã đúng. Mock hữu ích cho unit test logic cô lập; embedded broker hoặc container broker phù hợp cho integration test.

## 11. Các lỗi thường gặp

- **Consumer kết nối nhầm broker:** kiểm tra `spring.kafka.bootstrap-servers` và property mapping của `@EmbeddedKafka`.
- **Test không nhận được record:** kiểm tra topic, group ID, `auto-offset-reset`, listener startup và serializer/deserializer.
- **Topic đã tồn tại:** dùng topic riêng theo test hoặc xử lý kết quả `addTopics` có chủ đích.
- **Port bị chiếm:** dùng port `0` để broker chọn port ngẫu nhiên.
- **Test chạy riêng thì qua, chạy cả suite thì lỗi:** kiểm tra topic dùng chung, context cache, broker lifecycle và việc trộn global/per-class broker.
- **Broker không khởi động với version mới:** xác minh cặp Kafka/Spring Kafka và cấu hình KRaft/ZooKeeper tương thích.

## 12. Checklist cho broker nhúng

- Thêm `spring-kafka-test` ở test scope và dùng version được dependency management quản lý.
- Khai báo `@EmbeddedKafka` với topic, partition và bootstrap property rõ ràng.
- Ưu tiên port ngẫu nhiên để tránh xung đột môi trường CI.
- Dùng topic riêng hoặc chiến lược dọn dữ liệu rõ ràng giữa các test.
- Chờ kết quả gửi và listener bằng timeout/condition thay vì sleep tùy tiện.
- Đóng consumer và tài nguyên test do mình tạo.
- Chọn `@DirtiesContext` hoặc broker dùng chung theo lifecycle test context.
- Dùng Testcontainers hoặc cluster test khi cần xác minh replication, security hay failover.

Broker nhúng cung cấp một Kafka broker thật, khởi tạo tự động trong vòng đời test. Kết hợp `spring-kafka-test`, `@EmbeddedKafka`, property bootstrap servers chính xác và topic tách biệt giúp kiểm thử producer/consumer Spring Kafka ổn định. Hãy chọn Testcontainers hoặc cluster nhiều broker khi bài test cần xác minh những đặc tính hạ tầng mà broker đơn không thể mô phỏng.

## Tài liệu tham khảo

- [Testing Applications - Spring Kafka](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Apache Kafka Support - Spring Boot](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)

# Giới hạn Test Binder với giao dịch, broker metadata và Kafka Streams

Spring Cloud Stream Test Binder giúp kiểm tra nhanh cách một function hoặc consumer xử lý message mà không cần khởi chạy Kafka, RabbitMQ hay Pulsar. Test Binder chạy trong cùng JVM, dùng Spring Integration làm broker trung gian và cung cấp các điểm gửi/nhận message cho test. Vì không có broker thật, nó không mô phỏng giao thức, metadata, partition, consumer group, transaction hoặc cơ chế lưu trữ của Kafka.

Một test xanh với Test Binder chỉ chứng minh phần ứng dụng được thực thi trong môi trường test đó hoạt động như kỳ vọng. Nó không chứng minh Kafka Binder đã tạo đúng topic, broker đã chấp nhận transaction, consumer đã commit offset cùng output record, hay Kafka Streams đã khôi phục state store và phân phối partition đúng. Cần chọn công cụ theo câu hỏi muốn xác minh: Test Binder cho logic binding/message, TopologyTestDriver cho topology Kafka Streams, và broker thật cho hành vi tích hợp.

## 1. Test Binder hoạt động như thế nào?

Spring Cloud Stream cung cấp artifact `spring-cloud-stream-test-binder` để thay binder messaging bằng một broker in-memory dựa trên Spring Integration. Test có thể gửi message vào input binding và lấy message từ output binding mà không cần network hoặc service bên ngoài.

Dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Khai báo `@EnableTestBinder` trong cấu hình test:

~~~java
@SpringBootTest
@EnableTestBinder
class UppercaseFunctionTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void convertsInputAndPublishesOutput() {
        input.send(new GenericMessage<>(
            "hello".getBytes(StandardCharsets.UTF_8)
        ));

        Message<byte[]> result = output.receive(1_000);

        assertThat(result).isNotNull();
        assertThat(new String(
            result.getPayload(), StandardCharsets.UTF_8
        )).isEqualTo("HELLO");
    }

    @SpringBootApplication
    static class TestApplication {
        @Bean
        Function<String, String> uppercase() {
            return value -> value.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

Test có thể xác minh function nhận đúng payload, áp dụng business transformation và phát output mong đợi. Có thể gửi message có header, chỉ định destination khi ứng dụng có nhiều binding, kiểm tra content type hoặc xác minh nhánh output.

Test Binder rất phù hợp cho:

- Kiểm tra logic Supplier, Function, Consumer và function composition.
- Kiểm tra mapping payload/header ở ranh giới binding.
- Kiểm tra routing và nhiều output channel ở mức message contract.
- Kiểm tra validation, exception mapping và logic nghiệp vụ không phụ thuộc broker.
- Chạy test nhanh, lặp lại ổn định mà không phải quản lý tiến trình broker.

## 2. Vì sao Test Binder không thay thế broker thật?

Test Binder không khởi chạy Kafka broker và không dùng Kafka client để gửi hoặc nhận record. Nó cũng không tạo topic, partition, leader, replica, consumer group hoặc offset trong Kafka. Vì vậy, những hành vi chỉ tồn tại khi giao tiếp với broker không nằm trong phạm vi của test này.

| Hành vi cần xác minh | Test Binder | Công cụ phù hợp |
|---|---|---|
| Function biến đổi payload đúng | Có | Test Binder hoặc unit test |
| Message header và content type ở tầng Spring Message | Có thể kiểm tra | Test Binder |
| Kafka topic có tồn tại và đúng partition count | Không | Kafka broker thật |
| Metadata trả về leader, replica và partition | Không | Kafka broker thật/AdminClient |
| Consumer group join, offset commit và rebalance | Không | Kafka broker thật |
| Producer acknowledgement, retry ở client và broker error | Không | Kafka broker thật |
| Kafka transaction và isolation level | Không | Kafka broker thật |
| Kafka Streams topology và state store logic | Không mô phỏng Kafka Streams runtime | TopologyTestDriver |
| Kafka Streams Binder tạo topology, topic nội bộ và tham gia group | Không | Kafka broker thật |
| ACL, TLS, SASL, network partition và broker failover | Không | Môi trường tích hợp phù hợp |

Test Binder có thể giúp kiểm tra code xử lý message trước khi gửi ra output. Tuy nhiên, nó không chứng minh output đã được broker lưu, cũng không chứng minh offset input đã được commit. Không dùng kết quả Test Binder để kết luận hệ thống đáp ứng yêu cầu at-least-once, exactly-once hoặc durability.

## 3. Giới hạn khi kiểm thử giao dịch Kafka

Kafka transaction liên kết việc ghi một hoặc nhiều output record với offset của consumer trong cùng một transaction. Khi transaction commit, consumer đọc với isolation level phù hợp có thể nhìn thấy các output record đã commit. Nếu transaction abort, output record thuộc transaction đó không được hiển thị cho consumer `read_committed` và offset không được commit như một giao dịch thành công.

Test Binder không chạy Kafka transaction coordinator, transactional producer, transaction marker hoặc consumer isolation level. Vì vậy, nó không thể xác minh:

- Transaction được mở và commit/abort trên broker.
- Output record và input offset có được commit nguyên tử hay không.
- Producer fencing khi có instance khác dùng cùng transactional ID.
- Consumer `read_committed` có bỏ qua record thuộc transaction đang mở hoặc đã abort hay không.
- Retry sau rollback và dead-letter có được thực hiện ngoài transaction đã rollback hay không.

Có thể kiểm tra riêng business logic có gọi đúng nhánh xử lý khi exception xảy ra, nhưng đó không phải kiểm thử Kafka transaction. Muốn xác minh giao dịch phải chạy Kafka Binder thật với broker hỗ trợ transaction.

## 4. Cấu hình transactional binder cần được kiểm thử với Kafka thật

Với Kafka Binder, bật transaction bằng một transaction ID prefix khác rỗng:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: test-orders-
~~~

Trong processor application, consumer khởi tạo transaction; các record được gửi trên consumer thread có thể tham gia cùng transaction. Khi listener kết thúc bình thường, offset được đưa vào transaction và transaction được commit. Cấu hình producer dùng chung cho transactional binder nằm dưới `spring.cloud.stream.kafka.binder.transaction.producer`; các producer properties riêng của từng binding bị bỏ qua khi transaction được bật.

Mỗi instance ứng dụng cần transaction ID prefix duy nhất để tránh xung đột transactional ID và fencing. Khi kiểm thử nhiều instance, hãy cấp prefix khác nhau cho từng instance.

Một bài kiểm thử transaction tối thiểu nên có hai trường hợp:

1. **Commit:** gửi input, để processor publish output và kết thúc bình thường; consumer `read_committed` phải nhận output và offset input được commit.
2. **Abort:** gửi input làm processor ném exception sau khi publish; output thuộc transaction bị abort không được consumer `read_committed` nhìn thấy, và record input phải có thể được xử lý lại theo retry/rollback policy.

Consumer dùng để quan sát kết quả phải đặt `isolation.level=read_committed`. Consumer mặc định `read_uncommitted` có thể nhìn thấy record thuộc transaction chưa commit hoặc đã abort trong một số cách đọc, vì vậy không dùng nó để khẳng định tính nguyên tử của giao dịch.

Lưu ý: retry thông thường và dead-lettering của binder không chạy theo cùng cách khi bật transaction. Retry được chuyển sang cơ chế sau rollback ở listener container; dead-letter cũng được thực hiện sau khi transaction chính rollback. Kiểm tra cấu hình và hành vi này bằng broker thật, không suy ra từ Test Binder.

## 5. Broker metadata là gì và Test Binder không kiểm tra được điều gì?

Kafka client lấy metadata từ broker để biết topic có tồn tại hay không, topic có bao nhiêu partition, partition nào có leader và replica nào đang giữ dữ liệu. Kafka Binder cũng cần thông tin này khi provision binding, xác định partition, kiểm tra health và tạo hoặc mở rộng topic.

Test Binder không có Kafka metadata API. Nó không thể xác nhận:

- Tên topic mà binding thực sự sử dụng có tồn tại trên broker.
- Topic có đủ số partition cho producer partitioning hoặc consumer concurrency.
- Metadata có leader cho mọi partition hay không.
- Replica và in-sync replica (ISR) có đáp ứng yêu cầu durability.
- Broker có quyền tạo topic, thêm partition hoặc đọc/ghi topic.
- Cấu hình auto-create/auto-add partition của binder có hoạt động.
- Client có thể lấy metadata qua DNS, TLS, SASL hoặc network route thực tế.

Ví dụ, cấu hình binding yêu cầu bốn partition có thể vẫn chạy qua Test Binder vì không có broker kiểm tra metadata. Khi dùng Kafka Binder thật với topic chỉ có một partition và không cho phép auto-add partition, ứng dụng có thể lỗi lúc khởi tạo hoặc không đạt concurrency mong muốn.

## 6. Kiểm thử topic và partition metadata

Kafka Binder có các thuộc tính liên quan đến provision topic:

| Thuộc tính | Vai trò |
|---|---|
| `autoCreateTopics` | Cho phép binder tạo topic nếu chưa tồn tại |
| `autoAddPartitions` | Cho phép binder tăng số partition khi cần |
| `minPartitionCount` | Số partition tối thiểu binder cấu hình cho topic trong điều kiện áp dụng |
| `replicationFactor` | Replication factor cho topic binder tự tạo |
| `healthTimeout` | Thời gian chờ metadata partition trước khi health được đánh giá |

Các thuộc tính này cần được xác minh với Kafka broker thật. Đặc biệt, `autoCreateTopics` của binder là cấu hình phía ứng dụng; nó độc lập với `auto.create.topics.enable` phía broker. Nếu broker tự tạo topic khi client gửi metadata request, topic có thể được tạo bằng cấu hình mặc định của broker thay vì các giá trị mong muốn của ứng dụng.

Ví dụ dùng Kafka AdminClient để kiểm tra topic có ba partition:

~~~java
try (Admin admin = Admin.create(Map.of(
        AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
        bootstrapServers))) {

    TopicDescription description = admin
        .describeTopics(List.of("orders.events"))
        .topicNameValues()
        .get("orders.events")
        .get(10, TimeUnit.SECONDS);

    assertThat(description.partitions()).hasSize(3);
    assertThat(description.partitions())
        .allSatisfy(partition ->
            assertThat(partition.leader()).isNotNull()
        );
}
~~~

Đây là kiểm tra broker metadata thật. Có thể mở rộng để xác minh replica, ISR, partition leader và quyền AdminClient theo chính sách cluster. Không thể thay thế đoạn kiểm tra này bằng cách gửi một message qua Test Binder.

## 7. Kafka Streams cần chiến lược test riêng

Kafka Streams Binder tạo topology từ chữ ký function như `Function<KStream<...>, KStream<...>>`, `Consumer<KStream<...>>` hoặc các tổ hợp KStream/KTable. Test Binder thông thường không tạo Kafka Streams runtime, không tạo task, không khôi phục state store từ changelog và không tham gia consumer group Kafka.

Vì vậy, cần tách hai câu hỏi:

- Topology có tính toán đúng với record đầu vào không?
- Kafka Streams Binder có kết nối, triển khai topology và vận hành đúng trên Kafka không?

Câu hỏi thứ nhất có thể được kiểm tra bằng `TopologyTestDriver`. Câu hỏi thứ hai cần Kafka broker thật và test ứng dụng dùng Kafka Streams Binder.

## 8. Dùng TopologyTestDriver để kiểm thử logic topology

Kafka cung cấp artifact `kafka-streams-test-utils` với `TopologyTestDriver`. Driver chạy topology trong test mà không cần Kafka broker; test có thể gửi record vào topic giả lập, đọc output và truy vấn state store.

Dependency Maven (dùng cùng phiên bản Kafka Streams mà ứng dụng đang dùng):

~~~xml
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-streams-test-utils</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ví dụ kiểm thử topology đếm đơn hàng theo key:

~~~java
StreamsBuilder builder = new StreamsBuilder();
KStream<String, String> orders =
    builder.stream("orders.events");

KTable<String, Long> counts = orders
    .groupByKey()
    .count(Materialized.as("order-counts"));

Topology topology = builder.build();

Properties properties = new Properties();
properties.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "order-count-test"
);
properties.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "dummy:9092"
);
properties.put(
    StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
    Serdes.StringSerde.class
);
properties.put(
    StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
    Serdes.StringSerde.class
);

try (TopologyTestDriver driver =
         new TopologyTestDriver(topology, properties)) {

    TestInputTopic<String, String> input =
        driver.createInputTopic(
            "orders.events",
            Serdes.String().serializer(),
            Serdes.String().serializer()
        );

    input.pipeInput("customer-1", "order-A");
    input.pipeInput("customer-1", "order-B");

    KeyValueStore<String, Long> store =
        driver.getKeyValueStore("order-counts");

    assertThat(store.get("customer-1")).isEqualTo(2L);
}
~~~

TopologyTestDriver phù hợp để kiểm tra:

- Filter, map, branch, join, aggregate và window operation.
- Kết quả output record theo key/value/timestamp.
- State store trước và sau khi xử lý.
- Event-time punctuation và wall-clock punctuation được điều khiển trong test.
- Serde ở ranh giới topic và các trường hợp null/tombstone.

Driver xử lý record đồng bộ và mô phỏng input topic một partition. Nó không chạy broker thật. Do đó, test này không xác minh consumer group, rebalance, partition assignment giữa nhiều instance, broker metadata, replication hoặc giao dịch Kafka broker. Một số cấu hình runtime như commit interval/cache không có hiệu lực giống runtime thật vì driver xử lý từng record đồng bộ.

## 9. Kiểm thử Kafka Streams Binder bằng broker thật

Để xác minh binder, cần khởi động ứng dụng Spring Boot cùng Kafka broker và để Kafka Streams Binder thực sự tạo topology. Có thể dùng Embedded Kafka trong test scope:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ví dụ khung test:

~~~java
@SpringBootTest(properties = {
    "spring.cloud.stream.kafka.streams.binder.brokers=${spring.kafka.bootstrap-servers}"
})
@EmbeddedKafka(
    partitions = 3,
    topics = {"orders.events", "orders.summary"}
)
class OrderStreamsBinderIntegrationTests {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Test
    void streamsBinderConsumesAndPublishes() throws Exception {
        kafkaTemplate.send(
            "orders.events",
            "order-1",
            "{\"orderId\":\"order-1\",\"total\":120}"
        ).get(10, TimeUnit.SECONDS);

        // Use a test consumer subscribed to orders.summary.
        // Poll with a bounded timeout and assert the actual broker record.
    }
}
~~~

Đoạn code minh họa cách khởi tạo test broker và gửi input qua Kafka thật. Trong test hoàn chỉnh, tạo consumer với group riêng, cấu hình deserializer đúng schema, poll có timeout và assert output record. Có thể dùng `KafkaTestUtils` để tạo consumer/producer properties và lấy record từ broker.

Nếu ứng dụng có `spring-cloud-stream-test-binder` trên test classpath, test binder có thể thay binder thật. Với test cần Embedded Kafka và Kafka Binder thật, phải loại trừ `TestSupportBinderAutoConfiguration` trong test class hoặc tổ chức test binder và test broker thật thành các module/test context riêng:

~~~java
@SpringBootTest(properties =
    "spring.autoconfigure.exclude="
        + "org.springframework.cloud.stream.test.binder.TestSupportBinderAutoConfiguration")
@EmbeddedKafka(
    partitions = 3,
    topics = {"orders.events", "orders.summary"}
)
class RealKafkaBinderTests {
    // Tests exercise the actual Kafka binder.
}
~~~

Không để test binder tự động chiếm binding trong khi test đang kỳ vọng broker thật. Khi dùng `@EmbeddedKafka` cùng Spring test context, cân nhắc `@DirtiesContext` nếu cần bảo đảm application context đóng trước broker và tránh race lúc JVM shutdown.

## 10. Embedded Kafka có giới hạn gì?

Embedded Kafka là broker Kafka thật trong tiến trình test, vì vậy có thể kiểm tra metadata, topic, partition, consumer group, offset và transaction ở mức tích hợp. Tuy nhiên, cấu hình thường dùng một broker đơn lẻ và ít replica. Nó không đại diện đầy đủ cho cluster production có nhiều broker.

| Kiểm tra | Embedded Kafka một broker | Cluster nhiều broker |
|---|---|---|
| Kafka client kết nối và lấy metadata | Có | Có |
| Binder provision topic/partition | Có | Có |
| Producer/consumer hoạt động | Có | Có |
| Kafka transaction commit/abort cơ bản | Có | Có |
| Replication factor lớn hơn số broker | Không thể xác minh đúng | Có |
| ISR thay đổi khi broker mất | Không | Có |
| Leader election và failover giữa broker | Hạn chế hoặc không đại diện | Có |
| Broker rack awareness, network partition và failure domain | Không đại diện | Có |
| ACL/TLS/SASL giống production | Chỉ khi cấu hình riêng, không mặc định | Có thể kiểm tra sát production |

Khi cần kiểm tra transaction protocol cơ bản, Embedded Kafka hữu ích. Khi cần chứng minh durability với replication factor, min ISR, broker failover hoặc mất một node, dùng cluster nhiều broker trong Testcontainers hoặc môi trường tích hợp tương đương.

## 11. Kiểm thử transaction với consumer read_committed

Một test transaction cần quan sát cả record output và offset/khả năng redelivery. Consumer kiểm tra output nên đặt isolation level:

~~~java
Map<String, Object> consumerProperties =
    KafkaTestUtils.consumerProps(
        "transaction-verifier",
        "false",
        embeddedKafka
    );

consumerProperties.put(
    ConsumerConfig.ISOLATION_LEVEL_CONFIG,
    "read_committed"
);
~~~

Kịch bản commit:

1. Gửi một input record vào topic.
2. Processor bắt đầu transaction, xử lý và gửi output.
3. Processor kết thúc bình thường.
4. Consumer `read_committed` nhận output đã commit.
5. Xác minh output chỉ xuất hiện một lần theo hợp đồng xử lý.

Kịch bản abort:

1. Gửi input làm processor phát output rồi phát sinh exception.
2. Transaction rollback.
3. Consumer `read_committed` không nhận output thuộc transaction bị abort.
4. Xác minh retry/after-rollback xử lý input theo chính sách đã cấu hình.

Không chỉ assert số message trên output topic bằng consumer `read_uncommitted`. Consumer này có thể nhìn thấy record chưa commit, làm kết quả test không phản ánh góc nhìn của downstream application sử dụng `read_committed`.

## 12. Kiểm thử metadata và provisioning với Embedded Kafka

Tạo topic với số partition xác định:

~~~java
@EmbeddedKafka(
    partitions = 4,
    topics = {"orders.events", "orders.retry"}
)
class TopicMetadataTests {
    @Autowired
    EmbeddedKafkaBroker broker;

    @Test
    void topicHasExpectedPartitions() throws Exception {
        Map<String, Object> properties = Map.of(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            broker.getBrokersAsString()
        );

        try (Admin admin = Admin.create(properties)) {
            TopicDescription topic = admin
                .describeTopics(List.of("orders.events"))
                .topicNameValues()
                .get("orders.events")
                .get(10, TimeUnit.SECONDS);

            assertThat(topic.partitions()).hasSize(4);
        }
    }
}
~~~

Có thể dùng test này để kiểm tra binder đã tạo topic và số partition theo cấu hình. Nếu test chỉ khai báo topic trong `@EmbeddedKafka`, nó kiểm tra topic do test fixture tạo; muốn kiểm tra binder provisioning, hãy để binder tạo topic trong test hoặc kiểm tra AdminClient sau khi application context khởi động.

Để kiểm tra `autoAddPartitions`, cần tạo topic ban đầu có ít partition hơn số binder yêu cầu, bật auto-add và xác minh metadata sau khi binder khởi tạo. Để kiểm tra broker policy từ chối tạo topic, cấu hình broker/test ACL tương ứng và assert lỗi khởi tạo. Test Binder không thể thực hiện các kịch bản này.

## 13. Kiểm thử consumer group, offset và rebalance

Test Binder không có Kafka consumer group coordinator. Vì vậy, nó không kiểm tra được:

- Hai instance cùng group chia partition như thế nào.
- Một partition chỉ được gán cho một consumer trong group tại một thời điểm.
- Rebalance khi instance mới tham gia hoặc instance cũ rời group.
- Offset commit sau xử lý thành công hoặc rollback.
- Redelivery sau crash giữa lúc xử lý và commit.
- Lag và tốc độ catch-up khi consumer bị dừng.

Dùng Kafka thật để tạo ít nhất hai consumer instance trong cùng group, gửi record đến nhiều partition và quan sát assignment. Sau đó dừng một instance, chờ rebalance và xác minh instance còn lại tiếp tục nhận partition. Với kiểm thử crash, cần kiểm soát chính xác thời điểm xử lý, ack/commit và restart để xác nhận semantics mong đợi.

## 14. Kiểm thử lỗi broker và kết nối

Test Binder không thể tái hiện lỗi network hoặc broker. Dùng môi trường Kafka thật để kiểm tra:

- Broker unavailable khi application khởi động.
- Mất kết nối trong lúc publish hoặc poll.
- Topic bị xóa hoặc metadata thay đổi khi ứng dụng đang chạy.
- Partition leader không có hoặc vừa được bầu lại.
- Broker từ chối request do ACL hoặc authentication.
- Producer timeout, retry và duplicate sau khi confirm bị mất.
- Broker restart trong khi có transaction đang mở.

Embedded Kafka phù hợp với các bài test có vòng đời broker trong một process. Testcontainers hoặc cluster dùng chung phù hợp hơn khi cần cấu hình nhiều broker, security, replication và failure injection. Không đưa sự cố mạng ngẫu nhiên vào mọi unit test; hãy giữ các kịch bản này trong nhóm integration/chaos test có thời gian và điều kiện rõ ràng.

## 15. Chọn đúng công cụ cho từng lớp kiểm thử

| Lớp test | Công cụ | Xác minh | Không kết luận thay cho |
|---|---|---|---|
| Unit test | JUnit, Mockito | Business logic thuần Java | Binding hoặc broker |
| Binding/message test | Spring Cloud Stream Test Binder | Input/output binding và xử lý Message trong JVM | Kafka metadata, transaction, group |
| Topology test | Kafka Streams TopologyTestDriver | Processor topology, Serde, state store và punctuation | Kafka Streams Binder runtime, rebalance |
| Binder integration | Embedded Kafka + Kafka Binder thật | Binding, topic, partition, metadata, offset và transaction cơ bản | Replication/failover production |
| Cluster integration | Testcontainers hoặc Kafka cluster nhiều node | Replication, ISR, leader election, ACL/TLS và failure | Mọi hành vi production không được mô phỏng |

Một pipeline kiểm thử hợp lý thường chạy unit test và Test Binder nhiều lần trong quá trình phát triển; chạy TopologyTestDriver cho logic Kafka Streams; chạy Embedded Kafka/Testcontainers trong CI cho binder và broker semantics; và chạy thêm test trên cluster gần production trước các thay đổi liên quan transaction, metadata hoặc topology.

## 16. Ma trận test cho một ứng dụng Spring Cloud Stream

Ví dụ ứng dụng có function xử lý đơn hàng bằng Kafka Binder và một topology Kafka Streams tổng hợp số lượng đơn. Có thể chia test như sau:

| Kịch bản | Test Binder | TopologyTestDriver | Embedded Kafka |
|---|---|---|---|
| Function chuẩn hóa payload | Có | Không cần | Có thể, nhưng không cần |
| Header/content type mapping | Có | Chỉ khi nằm trong topology | Có |
| Aggregate và state store | Không đủ cho runtime Kafka Streams | Có | Có |
| Serde đọc/ghi topic | Chỉ kiểm tra conversion ở JVM | Có thể kiểm tra serializer bytes | Có |
| Topic partition count | Không | Không | Có |
| Transaction commit/abort | Không | Không | Có |
| read_committed visibility | Không | Không | Có |
| Consumer group rebalance | Không | Không | Có |
| Broker leader/replica/ISR | Không | Không | Một broker không đủ cho replication; cần cluster nhiều node |
| ACL/TLS/SASL | Không | Không | Có nếu cấu hình broker và client tương ứng |

Mỗi test nên có tên phản ánh đúng mức độ xác minh. Ví dụ, `uppercaseFunction_withTestBinder` không nên mang tên `kafkaTransaction_isAtomic` vì nó không chạy Kafka transaction.

## 17. Những hiểu nhầm thường gặp

**Test Binder gửi được message nên Kafka Binder chắc chắn gửi được.** Không đúng. Test Binder chỉ chuyển message qua broker in-memory; Kafka client có thể gặp lỗi serialization, metadata, authorization, timeout hoặc broker rejection.

**Test Binder test được output nên transaction commit đã đúng.** Không đúng. Không có transaction coordinator hoặc transactional producer của Kafka trong Test Binder.

**TopologyTestDriver không có broker nên vô dụng với Kafka Streams.** Không đúng. Nó rất hữu ích để kiểm tra logic topology, state store, timestamp và output một cách nhanh, có kiểm soát. Chỉ cần bổ sung broker integration test cho phần runtime mà driver không mô phỏng.

**Embedded Kafka tương đương cluster production.** Không đúng. Một broker embedded không chứng minh replication, ISR, leader failover hoặc fault tolerance giữa nhiều node.

**Test Binder và binder thật có thể tự động dùng chung trong một test context.** Không nên giả định như vậy. Khi test binder có mặt trên test classpath, Spring Cloud Stream có thể chọn nó thay binder thật. Test cần broker thật phải loại trừ test binder auto-configuration hoặc tách test/module theo hướng dẫn của Spring.

## 18. Checklist trước khi chấp nhận kết quả test

- [ ] Test Binder chỉ được dùng để kiểm tra logic function và message contract trong JVM.
- [ ] Không dùng Test Binder để kết luận broker metadata, partition hoặc consumer group hoạt động đúng.
- [ ] Không dùng Test Binder để kết luận Kafka transaction, commit offset hoặc read_committed visibility.
- [ ] Topology Kafka Streams được kiểm tra bằng TopologyTestDriver cho logic và state store.
- [ ] Kafka Streams Binder được kiểm tra với Kafka broker thật.
- [ ] Test dùng broker thật đã loại trừ Test Binder auto-configuration khi cần.
- [ ] Topic/partition metadata được kiểm tra qua AdminClient hoặc KafkaTestUtils.
- [ ] Transaction test có cả trường hợp commit và abort, consumer kiểm tra dùng read_committed.
- [ ] Consumer group test có nhiều instance và kịch bản rebalance nếu nghiệp vụ phụ thuộc partition assignment.
- [ ] Đã phân biệt giới hạn Embedded Kafka một broker với cluster production nhiều broker.
- [ ] Các test ACL, TLS, replication, ISR và failover chạy trong môi trường đủ thành phần.
- [ ] Test có timeout hữu hạn, topic/group riêng và cleanup để tránh ảnh hưởng giữa các lần chạy.

Test Binder là công cụ nhanh để kiểm tra phần xử lý message của ứng dụng Spring Cloud Stream, nhưng nó không phải Kafka giả lập đầy đủ. Dùng TopologyTestDriver cho logic Kafka Streams; dùng Embedded Kafka hoặc Testcontainers với binder thật để xác minh transaction, metadata, partition và consumer group; dùng cluster nhiều broker khi cần chứng minh replication và failover. Chọn đúng lớp test giúp kết quả xanh mang đúng ý nghĩa và tránh nhầm kiểm tra logic trong JVM với bảo đảm giao nhận của broker.

## Tài liệu tham khảo

- [Spring Cloud Stream — Testing Applications with the Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream — Kafka Binder Reference and Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html)
- [Spring for Apache Kafka — Testing Applications and Embedded Kafka](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Apache Kafka — TopologyTestDriver API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/TopologyTestDriver.html)
- [Apache Kafka — Testing a Streams Application](https://kafka.apache.org/39/streams/developer-guide/testing/)

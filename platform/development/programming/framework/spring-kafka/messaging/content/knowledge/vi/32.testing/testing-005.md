# KafkaTestUtils.consumerProps

`KafkaTestUtils.consumerProps()` là tiện ích của module `spring-kafka-test`, dùng để tạo nhanh `Map<String, Object>` chứa các thuộc tính cơ bản cho một Kafka consumer trong bài kiểm thử. Hàm này giúp test kết nối tới broker, chọn consumer group và đặt các cấu hình mặc định thường cần khi đọc record do test vừa gửi.

Điều cần nhớ là `consumerProps()` **chỉ tạo cấu hình**. Nó không khởi tạo consumer, không subscribe topic, không poll record và cũng không tự kiểm tra kết quả. Sau khi nhận map, test vẫn cần tạo `KafkaConsumer` hoặc `DefaultKafkaConsumerFactory`, đăng ký topic và dùng `KafkaTestUtils.getSingleRecord()` hoặc `getRecords()` để đọc dữ liệu.

## 1. Thêm dependency kiểm thử

Nếu dự án dùng Spring Boot, thêm starter kiểm thử Kafka với scope test:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Với dự án Spring Kafka không dùng Spring Boot starter, thêm `spring-kafka-test` cùng phiên bản tương thích với `spring-kafka`:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Các lớp thường dùng trong bài kiểm thử:

| Lớp | Vai trò |
|---|---|
| `EmbeddedKafkaBroker` | Cung cấp địa chỉ broker và quản lý broker Kafka nhúng |
| `KafkaTestUtils` | Tạo consumer/producer properties, poll record và đọc offset |
| `DefaultKafkaConsumerFactory` | Tạo Kafka consumer từ map cấu hình |
| `ConsumerRecord` | Đại diện record consumer nhận được |
| `KafkaTemplate` hoặc `KafkaProducer` | Gửi record để chuẩn bị dữ liệu kiểm thử |

Spring Kafka hiện dùng JUnit Jupiter cho hướng dẫn kiểm thử; các phiên bản mới không còn hỗ trợ JUnit 4. Với Kafka 4.0, embedded broker chuyển hoàn toàn sang KRaft và `EmbeddedKafkaKraftBroker` là implementation được sử dụng.

## 2. `consumerProps()` trả về những gì?

Hàm nhận thông tin broker, consumer group và chế độ auto commit, sau đó tạo map thuộc tính cho consumer. Trong Spring Kafka 4.x, các overload chính là:

```java
// Dùng trực tiếp EmbeddedKafkaBroker
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka, "orders-test", false);

// Dùng bootstrap server dạng chuỗi
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka.getBrokersAsString(),
                "orders-test", false);

// Từ Spring Kafka 3.3: auto commit mặc định false
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka.getBrokersAsString(),
                "orders-test");
```

Các tham số có ý nghĩa:

- `embeddedKafka` hoặc `brokers`: broker mà consumer kết nối tới. Với embedded broker, địa chỉ thường được lấy từ `getBrokersAsString()`.
- `group`: consumer group dùng trong test. Nên đặt group riêng cho từng kịch bản để tránh offset của test trước ảnh hưởng kết quả.
- `autoCommit`: bật hoặc tắt `enable.auto.commit`. Phần lớn test cần `false` để chủ động kiểm tra thời điểm commit offset.

Trong các phiên bản hiện hành, phương thức trả về `Map<String, Object>`, không phải `Properties` và cũng không phải một `Consumer` đã được tạo.

## 3. Các giá trị mặc định được thiết lập

`consumerProps()` tạo cấu hình cơ bản và đặt một số giá trị thuận tiện cho test. Với implementation hiện tại, các thuộc tính chính gồm:

| Kafka property | Giá trị được thiết lập | Ý nghĩa |
|---|---|---|
| `bootstrap.servers` | Địa chỉ broker truyền vào | Đích kết nối của consumer |
| `group.id` | Giá trị `group` | Định danh consumer group |
| `enable.auto.commit` | Theo tham số `autoCommit` | Có tự động commit offset hay không |
| `auto.commit.interval.ms` | `10` | Chu kỳ auto commit khi auto commit được bật |
| `session.timeout.ms` | `60000` | Thời gian session timeout của consumer |
| `key.deserializer` | `IntegerDeserializer` | Mặc định key trong ví dụ tiện ích là Integer |
| `value.deserializer` | `StringDeserializer` | Mặc định value là String |
| `auto.offset.reset` | `earliest` | Đọc từ đầu nếu group chưa có committed offset hợp lệ |

Từ Spring Kafka 2.5, `consumerProps()` đặt `auto.offset.reset=earliest`. Điều này giúp consumer mới đọc được record mà test đã gửi trước khi consumer bắt đầu. Nếu dùng `latest`, consumer mới có thể chỉ đọc record được gửi sau thời điểm nó bắt đầu đọc.

`earliest` chỉ được áp dụng khi group chưa có offset đã commit hoặc offset hiện tại không còn hợp lệ. Nếu tái sử dụng group đã có committed offset, consumer sẽ tiếp tục từ offset đó; đặt `earliest` không tự động đưa group về đầu topic.

## 4. Khác biệt API giữa các phiên bản Spring Kafka

Chữ ký của `consumerProps()` đã thay đổi ở Spring Kafka 4.0. Khi nâng cấp dependency, cần kiểm tra overload đang dùng để tránh cảnh báo deprecated hoặc lỗi biên dịch.

| Phiên bản | Chữ ký tiêu biểu | Trạng thái |
|---|---|---|
| 3.2.x trở về trước | `consumerProps(String group, String autoCommit, EmbeddedKafkaBroker broker)` | Cách gọi cũ |
| 3.2.x trở về trước | `consumerProps(String brokers, String group, String autoCommit)` | Cách gọi cũ |
| Từ 3.3 | `consumerProps(String brokers, String group)` | Mặc định auto commit false |
| Từ 4.0 | `consumerProps(EmbeddedKafkaBroker broker, String group, boolean autoCommit)` | API mới |
| Từ 4.0 | `consumerProps(String brokers, String group, boolean autoCommit)` | API mới |

Hai overload nhận `String autoCommit` và overload nhận `group, autoCommit, EmbeddedKafkaBroker` bị deprecated for removal từ Spring Kafka 4.0.0. Khi dùng 4.x, ưu tiên overload mới nhận `boolean`:

```java
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka, "orders-test", false);
```

Nếu dự án vẫn dùng Spring Kafka 3.2 hoặc cũ hơn, dùng chữ ký có tham số String mà phiên bản đó cung cấp:

```java
Map<String, Object> props =
        KafkaTestUtils.consumerProps("orders-test", "false", embeddedKafka);
```

Không copy ví dụ của Spring Kafka 4.x vào dự án 3.x mà chưa kiểm tra dependency. Ngược lại, khi đã nâng lên 4.x, hãy chuyển dần khỏi các overload String bị deprecated.

## 5. Tạo consumer từ map cấu hình

Quy trình cơ bản gồm bốn bước:

1. Lấy broker đang chạy từ `EmbeddedKafkaBroker`.
2. Gọi `consumerProps()` để tạo map.
3. Truyền map vào `DefaultKafkaConsumerFactory` và tạo consumer.
4. Subscribe topic hoặc dùng helper của embedded broker để gán partition, sau đó poll record.

```java
Map<String, Object> consumerProperties =
        KafkaTestUtils.consumerProps(embeddedKafka, "orders-test", false);

DefaultKafkaConsumerFactory<Integer, String> consumerFactory =
        new DefaultKafkaConsumerFactory<>(consumerProperties);

Consumer<Integer, String> consumer = consumerFactory.createConsumer();
```

Consumer vừa tạo chưa tự đọc topic. Với embedded broker, có thể dùng:

```java
embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");
```

Helper này gán consumer vào topic và đưa vị trí đọc của partition được gán về đầu. Nếu tự dùng Kafka consumer thuần, cần gọi `subscribe()` hoặc `assign()` trước khi `poll()`.

Đóng consumer sau khi test hoàn tất để giải phóng socket, heartbeat thread và tài nguyên khác. Nên dùng try-with-resources:

```java
try (Consumer<Integer, String> consumer = consumerFactory.createConsumer()) {
    embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");
    // poll và assert tại đây
}
```

## 6. Ví dụ hoàn chỉnh với Embedded Kafka và JUnit Jupiter

Ví dụ sau gửi một record có key Integer và value String, sau đó tạo consumer bằng `consumerProps()` để nhận đúng record đó. Test dùng một topic riêng và một group mới.

```java
@SpringJUnitConfig
@EmbeddedKafka(partitions = 1, topics = "orders")
class KafkaConsumerPropsTest {

    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @Test
    void shouldConsumeRecordUsingConsumerProps() throws Exception {
        // Chuẩn bị record trước khi tạo consumer.
        try (Producer<Integer, String> producer = new KafkaProducer<>(
                KafkaTestUtils.producerProps(this.embeddedKafka))) {

            producer.send(new ProducerRecord<>("orders", 42, "created"))
                    .get(10, TimeUnit.SECONDS);
        }

        Map<String, Object> consumerProperties = KafkaTestUtils.consumerProps(
                this.embeddedKafka, "orders-test", false);

        DefaultKafkaConsumerFactory<Integer, String> consumerFactory =
                new DefaultKafkaConsumerFactory<>(consumerProperties);

        try (Consumer<Integer, String> consumer = consumerFactory.createConsumer()) {
            this.embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");

            ConsumerRecord<Integer, String> received = KafkaTestUtils.getSingleRecord(
                    consumer, "orders", Duration.ofSeconds(10));

            assertThat(received.key()).isEqualTo(42);
            assertThat(received.value()).isEqualTo("created");
            assertThat(received.topic()).isEqualTo("orders");
            assertThat(received.partition()).isZero();
        }
    }
}
```

`producerProps()` cũng là tiện ích của `KafkaTestUtils`; nó tạo producer properties mặc định cho cặp kiểu Integer/String. Trong ví dụ, producer gửi record trước khi consumer được tạo. `auto.offset.reset=earliest` cùng helper gán topic về đầu giúp consumer đọc được record đã tồn tại.

`getSingleRecord()` chờ record của topic và yêu cầu nhận đúng một record. Overload có `Duration` cho phép giới hạn thời gian chờ rõ ràng; overload không có `Duration` dùng timeout mặc định dài hơn. Nếu không nhận được record hoặc nhận nhiều hơn một record của topic trong lần poll, helper báo lỗi thay vì trả về kết quả mơ hồ.

## 7. Thay đổi deserializer và các thuộc tính sau khi gọi helper

`consumerProps()` được thiết kế cho consumer `<Integer, String>`. Nếu key hoặc value của test có kiểu khác, cần thay deserializer tương ứng trong map trước khi tạo consumer.

Ví dụ test dùng key và value đều là String:

```java
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka, "string-orders-test", false);

props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);

ConsumerFactory<String, String> factory = new DefaultKafkaConsumerFactory<>(props);
```

Với payload JSON hoặc kiểu domain, cấu hình deserializer tương ứng, type information và trusted packages theo đúng serializer mà producer dùng. Không giữ `IntegerDeserializer` mặc định khi producer thực tế gửi key String; lỗi deserialization có thể xuất hiện ngay trong poll và làm test thất bại trước khi assertion chạy.

Có thể override bất kỳ property nào sau khi nhận map:

```java
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka, "orders-test", false);

props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");
props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 5);
props.put(ConsumerConfig.CLIENT_ID_CONFIG, "orders-test-client");
```

Các giá trị do test đặt sau helper sẽ ghi đè giá trị có cùng key. Dùng `ConsumerConfig` constants để tránh lỗi chính tả trong tên property.

## 8. Chọn auto commit hay manual commit trong test

Tham số `autoCommit` điều khiển `enable.auto.commit`:

| Giá trị | Hành vi | Khi nào dùng |
|---|---|---|
| `false` | Consumer không tự commit offset theo chu kỳ | Kiểm thử xử lý record, retry, commit thủ công và offset deterministically |
| `true` | Consumer tự commit offset theo `auto.commit.interval.ms` | Chỉ dùng khi test cần kiểm tra hành vi auto commit |

Thông thường nên truyền `false`. Test có thể chủ động commit sau khi xử lý:

```java
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka, "manual-commit-test", false);

try (Consumer<Integer, String> consumer =
             new DefaultKafkaConsumerFactory<Integer, String>(props).createConsumer()) {

    embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");
    ConsumerRecord<Integer, String> record =
            KafkaTestUtils.getSingleRecord(consumer, "orders", Duration.ofSeconds(10));

    process(record);
    consumer.commitSync();
}
```

Khi `autoCommit=true`, helper đặt `auto.commit.interval.ms=10`. Khoảng commit ngắn có thể khiến offset thay đổi trong lúc test đang kiểm tra. Vì vậy, không bật auto commit chỉ để consumer đọc được record; `auto.offset.reset=earliest` đã hỗ trợ trường hợp group chưa có offset.

## 9. Kết hợp với các tiện ích KafkaTestUtils khác

`KafkaTestUtils` cung cấp nhiều helper để giảm code phụ trong test:

| Method | Công dụng |
|---|---|
| `consumerProps(...)` | Tạo map cấu hình consumer |
| `producerProps(...)` | Tạo map cấu hình producer |
| `getSingleRecord(consumer, topic)` | Poll và yêu cầu đúng một record của topic |
| `getSingleRecord(consumer, topic, timeout)` | Tương tự nhưng chỉ định timeout |
| `getRecords(consumer)` | Poll và trả về `ConsumerRecords` |
| `getRecords(consumer, timeout)` | Poll với timeout chỉ định |
| `getCurrentOffset(...)` | Đọc committed offset của group/topic/partition |
| `getEndOffsets(consumer, topic, partitions...)` | Lấy end offset của các partition |

Ví dụ kiểm tra committed offset sau khi consumer commit:

```java
OffsetAndMetadata offset = KafkaTestUtils.getCurrentOffset(
        embeddedKafka.getBrokersAsString(),
        "orders-test",
        "orders",
        0);

assertThat(offset).isNotNull();
assertThat(offset.offset()).isEqualTo(1L);
```

Committed offset là vị trí tiếp theo consumer group sẽ đọc, không phải offset của record vừa xử lý. Nếu record được đọc có offset `0` và commit thành công, committed offset thường là `1`.

## 10. Tránh test bị nhiễm dữ liệu từ lần chạy trước

Embedded broker có thể được dùng chung qua nhiều test class để giảm thời gian khởi động. Khi chia sẻ broker, dữ liệu trên topic cũng được giữ lại trong thời gian broker còn chạy. Cần kiểm soát vị trí bắt đầu đọc và consumer group.

- Ưu tiên dùng topic riêng cho từng test hoặc từng kịch bản để tránh record cũ làm sai số lượng mong đợi.
- Dùng group ID riêng cho mỗi test nếu muốn `auto.offset.reset=earliest` có hiệu lực.
- `consumeFromAnEmbeddedTopic()` và helper tương ứng thường seek các partition được gán về đầu sau khi assignment. Nếu tái sử dụng topic và chỉ muốn đọc record mới, dùng overload hỗ trợ `seekToEnd=true` khi phiên bản đang dùng cung cấp, hoặc chủ động seek đến end trước khi gửi dữ liệu test.
- Không dựa vào `auto.offset.reset=earliest` để reset một group đã có committed offset hợp lệ.
- Đóng consumer, producer và tài nguyên test sau mỗi kịch bản; nếu dùng broker dùng chung, để framework quản lý vòng đời broker ở cấp test suite.

Khi test chạy song song, đặt topic/group khác nhau hoặc cô lập dữ liệu bằng cách khác. Nếu hai test cùng ghi và đọc một topic, `getSingleRecord()` có thể nhận nhiều record và báo lỗi đúng theo thiết kế.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không đọc được record đã gửi trước khi consumer tạo | Dùng group đã có offset hoặc `auto.offset.reset` không phải `earliest` | Dùng group mới và kiểm tra reset policy |
| `SerializationException` hoặc `RecordDeserializationException` | Deserializer mặc định không khớp kiểu key/value | Override `KEY_DESERIALIZER_CLASS_CONFIG` và `VALUE_DESERIALIZER_CLASS_CONFIG` |
| `getSingleRecord()` báo không có record | Chưa subscribe/assign, sai topic, producer chưa gửi xong hoặc timeout quá ngắn | Kiểm tra topic, chờ send completion và tăng timeout hợp lý |
| `getSingleRecord()` báo nhiều record | Topic/group dùng chung với test khác hoặc dữ liệu cũ | Dùng topic/group riêng, hoặc seek đến end trước khi gửi |
| Offset test thay đổi ngoài dự kiến | `autoCommit=true` hoặc group đã có committed offset | Dùng auto commit false và group mới |
| Không biên dịch sau khi nâng Spring Kafka 4.x | Vẫn gọi overload nhận `String autoCommit` | Chuyển sang overload nhận `boolean` hoặc `consumerProps(broker, group, boolean)` |
| Consumer không đóng sau test | Không đóng consumer hoặc producer | Dùng try-with-resources và quản lý lifecycle rõ ràng |

## 12. Ghi nhớ

- `KafkaTestUtils.consumerProps()` trả về `Map<String, Object>` cấu hình consumer; nó không tự tạo hoặc chạy consumer.
- Helper mặc định cho key Integer, value String, `auto.offset.reset=earliest` và nhận `autoCommit` qua tham số.
- Từ Spring Kafka 2.5, helper đặt `earliest`; điều này giúp group mới đọc record đã được gửi trước khi consumer bắt đầu.
- Từ Spring Kafka 4.0, ưu tiên overload nhận `boolean`; các overload nhận `String autoCommit` cũ đã deprecated for removal.
- Sau khi gọi helper, có thể override deserializer, `auto.offset.reset`, `max.poll.records` và các property khác trước khi tạo consumer.
- Dùng `autoCommit=false` để kiểm soát offset trong đa số test; dùng `getSingleRecord()` hoặc `getRecords()` để đọc kết quả.
- Dùng topic/group riêng, chú ý helper embedded broker seek về đầu và luôn đóng consumer sau test.

## Tài liệu tham khảo

- [Spring for Apache Kafka 4.1 — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [KafkaTestUtils — Spring Kafka 4.0 API](https://docs.spring.io/spring-kafka/docs/4.0.x/api/org/springframework/kafka/test/utils/KafkaTestUtils.html)
- [KafkaTestUtils — Spring Kafka 3.2 API](https://docs.spring.io/spring-kafka/docs/3.2.x/api/org/springframework/kafka/test/utils/KafkaTestUtils.html)
- [Spring Kafka — EmbeddedKafkaBroker API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/test/EmbeddedKafkaBroker.html)

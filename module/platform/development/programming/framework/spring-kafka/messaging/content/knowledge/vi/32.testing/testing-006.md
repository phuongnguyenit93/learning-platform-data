# KafkaTestUtils.producerProps

## 1. `producerProps()` dùng để làm gì?

Khi kiểm thử producer Kafka, mỗi test cần tạo một producer kết nối đến broker đang chạy trong test. Nếu tự viết lại toàn bộ cấu hình `bootstrap.servers`, serializer, buffer và batch cho từng test, code kiểm thử sẽ dài và dễ lệch nhau.

Spring Kafka cung cấp `KafkaTestUtils.producerProps()` trong artifact `spring-kafka-test`. Phương thức này tạo một `Map<String, Object>` chứa các thuộc tính producer cơ bản để gửi record đến broker kiểm thử.

Hai overload thường dùng:

```java
Map<String, Object> producerProps(EmbeddedKafkaBroker embeddedKafka);

Map<String, Object> producerProps(String brokers);
```

Overload nhận `EmbeddedKafkaBroker` lấy địa chỉ broker từ `embeddedKafka.getBrokersAsString()` rồi gọi overload nhận chuỗi địa chỉ. Overload nhận `String` có từ Spring Kafka 2.3.5, phù hợp khi test dùng broker bên ngoài hoặc Testcontainers và đã có bootstrap server.

Điểm cần nhớ: `producerProps()` chỉ tạo cấu hình. Nó không khởi động Kafka broker, không tạo topic, không tạo `KafkaProducer` và không gửi record. Broker và topic phải sẵn sàng trước khi tạo producer.

## 2. Thêm dependency spring-kafka-test

`KafkaTestUtils` thuộc package:

```java
import org.springframework.kafka.test.utils.KafkaTestUtils;
```

Nếu dùng Spring Boot 4.x, tài liệu Spring Boot khuyến nghị starter test Kafka:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Với dự án không dùng Spring Boot, hoặc dự án Boot đang quản lý trực tiếp các module Spring Kafka, có thể thêm artifact `spring-kafka-test` với scope test.

Maven:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

Với Kotlin DSL và Spring Boot 4.x:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-kafka-test")
}
```

Nếu dự án dùng Spring Boot dependency management, để BOM quản lý phiên bản tương thích. Nếu tự quản lý dependency, chọn `spring-kafka-test` cùng dòng phiên bản với `spring-kafka` và Kafka client mà ứng dụng đang dùng. Không đặt artifact test vào dependency production vì các lớp test không cần có mặt trong runtime application.

## 3. Kết hợp với EmbeddedKafkaBroker

`producerProps(EmbeddedKafkaBroker)` thường được dùng cùng `@EmbeddedKafka`. Annotation tạo broker nhúng cho test context; Spring Kafka cung cấp bean `EmbeddedKafkaBroker` để test lấy địa chỉ kết nối.

Ví dụ JUnit Jupiter:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig
@DirtiesContext
@EmbeddedKafka(partitions = 1, topics = "orders")
class OrderProducerTests {

    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @Test
    void embeddedBrokerIsAvailable() {
        String brokers = embeddedKafka.getBrokersAsString();
        assertNotNull(brokers);
        assertFalse(brokers.isBlank());
    }
}
```

`@EmbeddedKafka` quản lý vòng đời broker trong phạm vi Spring test context. `partitions = 1` tạo topic một partition; `topics = "orders"` yêu cầu topic được tạo khi broker khởi động. `@DirtiesContext` giúp đóng test context sau class và tránh race condition khi embedded broker bị shutdown trong lúc context khác còn sử dụng tài nguyên. Trong test thật, nên dùng topic riêng cho từng test hoặc quy ước đặt tên để các test chạy song song không đọc nhầm record của nhau.

Spring Kafka 4.x chạy embedded broker ở KRaft mode vì Kafka 4.0 đã loại bỏ ZooKeeper. Với các dòng Spring Kafka cũ hơn, implementation embedded broker và lựa chọn ZooKeeper/KRaft phụ thuộc phiên bản.

Khi test đã có `EmbeddedKafkaBroker`, không cần tự ghép port hoặc đoán địa chỉ broker. Dùng chính bean này để tạo producer properties:

```java
Map<String, Object> producerProperties =
        KafkaTestUtils.producerProps(embeddedKafka);
```

## 4. Gửi record bằng KafkaProducer

Javadoc mô tả producer properties mặc định cho producer kiểu `<Integer, String>`. Vì vậy, ví dụ trực tiếp dùng `Integer` làm key và `String` làm value:

```java
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@Test
void sendsRecordToEmbeddedKafka() throws Exception {
    Map<String, Object> props = KafkaTestUtils.producerProps(embeddedKafka);

    try (KafkaProducer<Integer, String> producer = new KafkaProducer<>(props)) {
        ProducerRecord<Integer, String> record =
                new ProducerRecord<>("orders", 42, "ORDER_CREATED");

        RecordMetadata metadata = producer.send(record).get(10, TimeUnit.SECONDS);

        assertEquals("orders", metadata.topic());
        assertEquals(0, metadata.partition());
        assertTrue(metadata.offset() >= 0);
    }
}
```

`KafkaProducer` nhận trực tiếp map do `producerProps()` trả về. Khi gửi, `send()` trả về `Future<RecordMetadata>`; gọi `get()` trong test giúp chờ kết quả broker xác nhận thay vì kết thúc test ngay sau khi enqueue record vào buffer cục bộ.

`RecordMetadata` cho biết topic, partition và offset mà broker đã gán cho record. Với topic một partition, partition mong đợi là `0`. Nếu topic có nhiều partition và record không chỉ rõ partition, không nên hard-code partition trong assertion; hãy kiểm tra key/partitioner hoặc chỉ xác nhận partition thuộc tập partition hợp lệ.

`try-with-resources` bảo đảm producer được đóng ngay cả khi assertion hoặc send thất bại. Đóng producer giúp flush các request đang chờ và giải phóng network thread, buffer cùng socket.

## 5. Các thuộc tính mà producerProps tạo ra

Trong implementation hiện hành, overload nhận chuỗi broker tạo map với các giá trị sau:

| Kafka producer property | Giá trị | Ý nghĩa |
|---|---|---|
| `bootstrap.servers` | Địa chỉ broker truyền vào | Điểm kết nối ban đầu để producer lấy metadata cluster |
| `batch.size` | `16384` | Kích thước batch mặc định 16 KiB cho mỗi partition |
| `linger.ms` | `1` | Producer có thể chờ tối đa khoảng 1 ms để gom record vào batch trước khi gửi |
| `buffer.memory` | `33554432` | Bộ nhớ buffer producer 32 MiB |
| `key.serializer` | `IntegerSerializer.class` | Chuyển key kiểu `Integer` thành byte[] |
| `value.serializer` | `StringSerializer.class` | Chuyển value kiểu `String` thành byte[] |

Các giá trị `batch.size` và `buffer.memory` được biểu diễn bằng chuỗi số trong map; `linger.ms` được đặt bằng số nguyên. Kafka client chấp nhận giá trị cấu hình ở dạng phù hợp theo từng property.

Các thuộc tính trên là bộ cấu hình tiện ích để viết test producer cơ bản. Phương thức không cấu hình toàn bộ mọi tùy chọn producer. Những property không có trong map sẽ dùng default của Kafka client hoặc được lấy từ cấu hình bổ sung mà test cung cấp.

Đặc biệt, không nên hiểu `batch.size`, `linger.ms` hoặc `buffer.memory` ở đây là benchmark tuning cho production. Đây là giá trị thuận tiện cho test; ứng dụng thật cần cấu hình theo throughput, latency, message size và tài nguyên.

Có thể kiểm tra hợp đồng của helper bằng unit test nhỏ:

```java
@Test
void producerPropsContainsExpectedDefaults() {
    Map<String, Object> props = KafkaTestUtils.producerProps(embeddedKafka);

    assertEquals(embeddedKafka.getBrokersAsString(),
            props.get(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG));
    assertEquals("16384", props.get(ProducerConfig.BATCH_SIZE_CONFIG));
    assertEquals(1, props.get(ProducerConfig.LINGER_MS_CONFIG));
    assertEquals("33554432", props.get(ProducerConfig.BUFFER_MEMORY_CONFIG));
    assertEquals(IntegerSerializer.class,
            props.get(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG));
    assertEquals(StringSerializer.class,
            props.get(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG));
}
```

Đây là kiểm thử hợp đồng của helper theo implementation đang dùng. Nếu nâng Spring Kafka, các giá trị mặc định có thể thay đổi; test này sẽ giúp nhóm phát hiện thay đổi cấu hình và chủ động quyết định có cần cập nhật test setup hay không.

## 6. Vì sao kiểu mặc định là Integer và String?

`KafkaTestUtils.producerProps()` được xây dựng cho cặp kiểu dữ liệu `<Integer, String>`:

- Key serializer là `IntegerSerializer`.
- Value serializer là `StringSerializer`.

Do đó producer sau đây tương thích trực tiếp:

```java
KafkaProducer<Integer, String> producer =
        new KafkaProducer<>(KafkaTestUtils.producerProps(embeddedKafka));
```

Nếu generic type không khớp serializer, test có thể lỗi lúc gửi. Ví dụ dùng `String` làm key nhưng vẫn giữ `IntegerSerializer` có thể dẫn đến `ClassCastException` hoặc lỗi serialization.

Generic type của Java không tự thay đổi Kafka serializer. Dòng khai báo `KafkaProducer<String, OrderCreated>` chỉ giúp compiler kiểm tra kiểu; Kafka producer vẫn cần serializer tương ứng trong cấu hình.

## 7. Ghi đè serializer cho kiểu dữ liệu riêng

Map được trả về có thể chỉnh sửa. Khi cần key kiểu `String` và value là JSON object, sao chép hoặc cập nhật map rồi thay hai serializer:

```java
import org.springframework.kafka.support.serializer.JacksonJsonSerializer;

Map<String, Object> props = new HashMap<>(
        KafkaTestUtils.producerProps(embeddedKafka));

props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JacksonJsonSerializer.class);

try (KafkaProducer<String, OrderCreated> producer = new KafkaProducer<>(props)) {
    OrderCreated event = new OrderCreated("order-42", "CREATED");
    RecordMetadata metadata = producer.send(
            new ProducerRecord<>("orders", event.orderId(), event))
            .get(10, TimeUnit.SECONDS);

    assertEquals("orders", metadata.topic());
}
```

`JacksonJsonSerializer` thuộc `org.springframework.kafka.support.serializer`. Với Spring Kafka 2.x/3.x dùng Jackson 2, serializer quen thuộc là `JsonSerializer`; từ Spring Kafka 4.0, `JsonSerializer` đã deprecated để chuyển sang `JacksonJsonSerializer` cho Jackson 3. Nếu dùng serializer khác, thay class tương ứng và bảo đảm consumer test dùng deserializer tương thích.

Việc tạo `new HashMap<>(...)` làm rõ rằng test đang sở hữu map cấu hình riêng để tùy chỉnh. Có thể gọi `put()` trực tiếp trên map trả về vì implementation trả về một `HashMap` mới, nhưng copy map hữu ích khi muốn giữ nguyên base config hoặc dùng lại nó ở nhiều producer khác nhau.

## 8. Ghi đè các producer property khác

Ngoài serializer, test có thể bổ sung hoặc thay thế property khác. Ví dụ:

```java
Map<String, Object> props = new HashMap<>(
        KafkaTestUtils.producerProps(embeddedKafka));

props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.CLIENT_ID_CONFIG, "orders-producer-test");
props.put(ProducerConfig.LINGER_MS_CONFIG, 0);
```

`Map.put(key, value)` ghi đè giá trị cũ nếu key đã tồn tại. Trong ví dụ, `linger.ms` đổi từ `1` thành `0`; `acks` và `client.id` được bổ sung.

Chỉ thêm property có mục đích kiểm thử cụ thể. Ví dụ `client.id` giúp nhận diện producer trong log broker; `acks` có thể cần khi test semantics xác nhận ghi. Tránh copy toàn bộ cấu hình production vào test nếu test chỉ cần xác nhận serialization và gửi record.

Nếu test cần xác minh một thuộc tính, hãy assert trực tiếp map trước khi tạo producer:

```java
assertEquals("all", props.get(ProducerConfig.ACKS_CONFIG));
assertEquals("orders-producer-test", props.get(ProducerConfig.CLIENT_ID_CONFIG));
```

Không phụ thuộc thứ tự các entry trong map; `Map` không cam kết thứ tự iteration.

## 9. Dùng producerProps(String brokers)

Khi không dùng `EmbeddedKafkaBroker`, overload nhận chuỗi bootstrap server vẫn tạo cùng bộ thuộc tính cơ bản:

```java
String bootstrapServers = "localhost:9092";
Map<String, Object> props = KafkaTestUtils.producerProps(bootstrapServers);

try (KafkaProducer<Integer, String> producer = new KafkaProducer<>(props)) {
    producer.send(new ProducerRecord<>("orders", 7, "ORDER_CREATED"))
            .get(10, TimeUnit.SECONDS);
}
```

Đây là cách dùng với broker chạy ngoài test process, ví dụ Kafka Testcontainers hoặc Kafka test cluster riêng. `producerProps(String)` không kiểm tra broker có thật sự sẵn sàng hay không; địa chỉ phải hợp lệ và broker phải reachable.

Nếu broker yêu cầu SASL, TLS hoặc credential, map cơ bản không tự thêm security properties. Test cần bổ sung `security.protocol`, SASL/SSL config, truststore và credential qua secret test phù hợp. Không đưa password hoặc keytab thật vào source control.

## 10. Dùng producerProps với KafkaTemplate

Ứng dụng Spring Kafka thường gửi record bằng `KafkaTemplate`, nên integration test có thể tạo `DefaultKafkaProducerFactory` từ map của `KafkaTestUtils` rồi khởi tạo template.

Ví dụ với `String` key và `OrderCreated` value:

```java
import org.springframework.kafka.support.serializer.JacksonJsonSerializer;

@Test
void sendsEventWithKafkaTemplate() throws Exception {
    Map<String, Object> props = new HashMap<>(
            KafkaTestUtils.producerProps(embeddedKafka));
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JacksonJsonSerializer.class);

    DefaultKafkaProducerFactory<String, OrderCreated> producerFactory =
            new DefaultKafkaProducerFactory<>(props);
    KafkaTemplate<String, OrderCreated> kafkaTemplate =
            new KafkaTemplate<>(producerFactory);

    try {
        OrderCreated event = new OrderCreated("order-100", "CREATED");
        SendResult<String, OrderCreated> result = kafkaTemplate
                .send("orders", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);

        assertEquals("orders", result.getRecordMetadata().topic());
    } finally {
        producerFactory.destroy();
    }
}
```

`KafkaTemplate` không thay thế serializer. Template gửi key/value xuống producer factory; serializer cấu hình trong map vẫn quyết định cách chuyển dữ liệu thành bytes.

Trong test dùng Spring context thật, thường nên inject `KafkaTemplate` đã được cấu hình trong application context và để Spring quản lý lifecycle. Ví dụ tự tạo factory/template ở trên phù hợp khi test muốn cô lập producer config; phải destroy factory sau test để đóng producer được cache.

## 11. Gửi bất đồng bộ và chờ kết quả đúng cách

Kafka producer gửi bất đồng bộ. `send()` trả về `Future<RecordMetadata>` (hoặc API tương ứng theo phiên bản Kafka client). Trong test, có ba cách phổ biến:

**Chờ Future:**

```java
RecordMetadata metadata = producer.send(record).get(10, TimeUnit.SECONDS);
```

Cách này đơn giản và cho phép assert metadata. Timeout giúp test kết thúc có giới hạn nếu broker không phản hồi.

**Gọi flush:**

```java
producer.send(record);
producer.flush();
```

`flush()` đợi các record đã gửi trước đó được xử lý xong ở phía producer, nhưng không cung cấp `RecordMetadata` cho assertion. Khi cần kiểm tra partition/offset hoặc bắt lỗi gửi cụ thể, giữ Future và gọi `get()`.

**Dùng callback:**

```java
CompletableFuture<RecordMetadata> completion = new CompletableFuture<>();

producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        completion.completeExceptionally(exception);
    } else {
        completion.complete(metadata);
    }
});

RecordMetadata metadata = completion.get(10, TimeUnit.SECONDS);
```

Callback hữu ích khi test muốn xác minh nhánh thành công và thất bại bất đồng bộ. Không dùng callback chỉ để tăng độ phức tạp nếu Future đơn giản đã đáp ứng nhu cầu.

Tránh `Thread.sleep()` cố định để chờ record được gửi. Chờ Future hoặc dùng consumer polling với timeout giúp test đồng bộ theo sự kiện thực tế và ít flaky hơn.

## 12. Kiểm tra record đã thực sự đến broker

`Future<RecordMetadata>` hoàn tất thành công chứng minh broker đã xác nhận send theo cấu hình producer, nhưng nếu test cần xác minh payload mà consumer đọc được, hãy kết hợp consumer test.

Ví dụ minh họa phần producer và phần consumer độc lập:

```java
Map<String, Object> producerProps =
        KafkaTestUtils.producerProps(embeddedKafka);

try (KafkaProducer<Integer, String> producer = new KafkaProducer<>(producerProps)) {
    producer.send(new ProducerRecord<>("orders", 9, "ORDER_CREATED"))
            .get(10, TimeUnit.SECONDS);
}

Map<String, Object> consumerProps =
        KafkaTestUtils.consumerProps(embeddedKafka, "orders-test-group", false);
consumerProps.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, IntegerDeserializer.class);
consumerProps.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);

try (KafkaConsumer<Integer, String> consumer = new KafkaConsumer<>(consumerProps)) {
    embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");
    ConsumerRecord<Integer, String> received =
            KafkaTestUtils.getSingleRecord(consumer, "orders", Duration.ofSeconds(10));

    assertEquals(9, received.key());
    assertEquals("ORDER_CREATED", received.value());
}
```

Consumer helper ở ví dụ dùng overload `consumerProps(EmbeddedKafkaBroker, String, boolean)` có từ Spring Kafka 4.0. Với dòng phiên bản cũ hơn, dùng overload consumer properties được hỗ trợ ở phiên bản đó hoặc cấu hình consumer map thủ công. Phần này chỉ minh họa cách xác minh end-to-end; trọng tâm của bài vẫn là producer properties.

Chú ý thứ tự subscribe/assignment: `consumeFromAnEmbeddedTopic()` gán consumer vào topic và mặc định seek về đầu partition trong embedded broker. Nếu test cần chỉ đọc record mới sau một mốc, chọn overload có `seekToEnd` phù hợp hoặc dùng topic riêng cho test.

## 13. Dùng với Testcontainers hoặc broker ngoài

Nếu test sử dụng Testcontainers Kafka, lấy bootstrap server từ container rồi truyền vào overload chuỗi:

```java
String brokers = kafkaContainer.getBootstrapServers();
Map<String, Object> props = KafkaTestUtils.producerProps(brokers);

props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
```

Phương thức này không phụ thuộc `EmbeddedKafkaBroker`; nó chỉ cần chuỗi bootstrap server. Đây là điểm hữu ích khi cùng một test suite có thể chạy với embedded broker hoặc broker container.

Nếu container yêu cầu security protocol hoặc test dùng nhiều broker, hãy bổ sung property tương ứng và xác nhận topic đã được tạo. Không giả định `producerProps()` tự cấu hình Testcontainers hoặc tự bật Kafka container.

## 14. Những gì producerProps không làm

Để tránh kỳ vọng sai, cần phân biệt helper với các thành phần khác:

| Thành phần | Trách nhiệm |
|---|---|
| `KafkaTestUtils.producerProps()` | Tạo map thuộc tính producer test cơ bản |
| `@EmbeddedKafka` / `EmbeddedKafkaBroker` | Khởi tạo và quản lý broker nhúng cho test |
| `KafkaProducer` | Gửi record bằng Kafka Java client |
| `DefaultKafkaProducerFactory` | Tạo/quản lý producer cho Spring Kafka |
| `KafkaTemplate` | API Spring để gửi record |
| `ProducerRecord` | Mô tả topic, partition/key/value/timestamp/headers của record gửi |
| `spring-kafka-test` | Cung cấp test utilities và embedded broker support |

`producerProps()` không:

- Tạo topic hoặc chọn partition cho record.
- Tạo producer hoặc KafkaTemplate.
- Chờ broker sẵn sàng.
- Cấu hình consumer group hay deserializer.
- Tự cấu hình JSON serializer cho domain object.
- Tự bật TLS, SASL, Kerberos hoặc credential.
- Bảo đảm producer transaction hoặc xác minh exactly-once.
- Tự đóng producer được tạo từ map.

Những trách nhiệm đó thuộc broker, producer factory, Kafka client properties hoặc code test tương ứng.

## 15. Lưu ý khi test chạy song song

Embedded broker có thể được chia sẻ giữa nhiều test class thông qua Spring test context cache. Điều này giúp giảm chi phí khởi động broker, nhưng các test dùng chung topic có thể ảnh hưởng nhau.

Để tránh test phụ thuộc thứ tự:

- Dùng topic riêng cho từng test class hoặc từng test case nếu test chạy song song.
- Dùng consumer group ID riêng khi test offset độc lập.
- Không dựa vào offset bắt đầu mặc định nếu topic có thể đã chứa record từ test trước.
- Chờ send Future hoàn tất trước khi consumer assertion.
- Đóng producer/consumer sau test.
- Nếu dùng chung context và broker, không xóa topic hoặc dừng broker khi test khác vẫn đang dùng.

Nếu test cần kiểm tra producer retry, idempotence hoặc transaction, hãy cấu hình riêng property liên quan và thiết kế broker phù hợp. Không suy ra hành vi transaction chỉ từ map producer cơ bản.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `SerializationException` hoặc `ClassCastException` | Generic key/value không khớp `IntegerSerializer` và `StringSerializer` mặc định | Override key/value serializer theo kiểu dữ liệu thật |
| `No resolvable bootstrap urls` | Broker string rỗng, sai định dạng hoặc broker chưa sẵn sàng | Dùng `embeddedKafka.getBrokersAsString()` hoặc bootstrap server thật |
| `TimeoutException` khi chờ Future | Broker chưa sẵn sàng, topic chưa tồn tại, network hoặc ACL lỗi | Kiểm tra broker lifecycle, topic, log và timeout |
| Producer gửi được nhưng consumer không thấy record | Consumer subscribe/assignment muộn, offset reset hoặc group đã có offset | Dùng topic riêng, kiểm tra assignment và seek strategy |
| Test pass trên máy này nhưng fail trên máy khác | Port cố định, broker lifecycle hoặc test dùng chung topic | Dùng port động, `@EmbeddedKafka`, topic riêng và timeout có giới hạn |
| Record gửi đi nhưng test kết thúc trước khi ack | Không chờ Future hoặc flush | Gọi `get(timeout)` hoặc flush khi phù hợp |
| Producer thread còn chạy sau test | Không đóng producer/factory | Dùng try-with-resources hoặc destroy factory |
| JSON payload không deserialize được | Chỉ thay serializer producer nhưng consumer vẫn dùng StringDeserializer hoặc type config không khớp | Cấu hình deserializer tương thích và kiểm tra type/header |
| Test broker yêu cầu SASL/TLS nhưng producer bị từ chối | Helper chỉ tạo thuộc tính producer cơ bản, thiếu security properties | Bổ sung protocol, JAAS/SSL và credential test |
| Nhiều test đọc nhầm record | Dùng chung topic và consumer group/offset | Cô lập topic/group hoặc reset offset có chủ đích |

## 17. Quy trình dùng producerProps trong một test

1. Thêm `spring-boot-starter-kafka-test` nếu dùng Spring Boot 4.x, hoặc `spring-kafka-test` ở test scope cho dự án Spring Kafka thuần; đồng bộ version.
2. Khởi tạo broker bằng `@EmbeddedKafka` hoặc lấy bootstrap server từ broker test khác.
3. Tạo map bằng `KafkaTestUtils.producerProps(embeddedKafka)` hoặc `producerProps(brokers)`.
4. Kiểm tra key/value type của test có khớp serializer mặc định `<Integer, String>` hay không.
5. Nếu kiểu dữ liệu khác, ghi đè `KEY_SERIALIZER_CLASS_CONFIG` và `VALUE_SERIALIZER_CLASS_CONFIG`.
6. Bổ sung các property riêng chỉ khi test cần chúng, ví dụ `client.id`, `acks` hoặc security config.
7. Tạo `KafkaProducer` hoặc `ProducerFactory`/`KafkaTemplate` từ map.
8. Gửi record và chờ Future hoàn tất với timeout.
9. Assert metadata hoặc dùng consumer để xác minh payload.
10. Đóng producer/factory và giữ topic/group test độc lập để tránh cross-talk.

## 18. Tổng kết

- `KafkaTestUtils.producerProps()` tạo `Map<String, Object>` để cấu hình producer test.
- Overload nhận `EmbeddedKafkaBroker` lấy bootstrap server từ broker; overload nhận `String` có từ Spring Kafka 2.3.5.
- Bộ property mặc định dành cho producer `<Integer, String>` với `IntegerSerializer` và `StringSerializer`.
- Map gồm bootstrap server, batch size, linger, buffer memory và serializer; các property khác dùng default Kafka client nếu test không ghi đè.
- Có thể dùng map với `KafkaProducer`, `DefaultKafkaProducerFactory` hoặc `KafkaTemplate`.
- Khi dùng key/value khác kiểu mặc định, phải thay serializer tương ứng; generic type không tự cấu hình serializer.
- Chờ send Future với timeout để test có kết quả xác định; đóng producer/factory sau test.
- Helper không khởi động broker, tạo topic, bật security hoặc tạo producer.
- Dùng topic/group riêng và kiểm soát assignment/offset để tránh test phụ thuộc nhau.

`KafkaTestUtils.producerProps()` giúp giảm phần cấu hình lặp lại khi viết producer test. Khi hiểu rõ các property mà helper cung cấp, kiểu dữ liệu mặc định và cách ghi đè serializer, bạn có thể tập trung kiểm tra hành vi gửi record của ứng dụng Spring Kafka mà vẫn giữ test có vòng đời rõ ràng và kết quả ổn định.

## Tài liệu tham khảo

- [Spring Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Kafka API — KafkaTestUtils](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/test/utils/KafkaTestUtils.html)
- [Spring Kafka source — KafkaTestUtils.java](https://github.com/spring-projects/spring-kafka/blob/main/spring-kafka-test/src/main/java/org/springframework/kafka/test/utils/KafkaTestUtils.java)

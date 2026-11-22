# Test deserialization failure trong Spring Kafka

Một Kafka consumer có thể hoạt động bình thường với hàng triệu sự kiện, nhưng chỉ một record chứa bytes sai định dạng cũng có khả năng làm nó liên tục thất bại ở cùng offset. Ví dụ topic chờ JSON cho `OrderEvent` nhưng producer gửi value `{broken-json`, gửi Avro bytes sang consumer JSON, hoặc đính kèm type header không được tin cậy. Lỗi phát sinh **trong Kafka deserializer trước khi `@KafkaListener` được gọi**; một `try/catch` bên trong listener không thể bắt lỗi mà listener chưa từng nhìn thấy.

Với Spring Kafka, thiết kế kiểm thử tin cậy không chỉ cần chứng minh “có exception” mà phải trả lời: **record hỏng đi đâu, consumer có tiếp tục sau record hỏng không, offset được xử lý theo chính sách nào, và khi đường recovery lỗi có mất dữ liệu âm thầm không?**

Bài thuộc **Spring Kafka Reliability Operations → Kiểm thử tin cậy**, tập trung vào **Test deserialization failure** bằng raw bytes, `ErrorHandlingDeserializer`, `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, test với Embedded Kafka, lỗi key/value, DLT, retry, replay, quan sát offset và kiểm thử những failure mode thường bị bỏ sót. Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Kafka 3.x và Kafka clients tương ứng; cần điều chỉnh chi tiết cấu hình theo phiên bản thực tế.

## 1. Mục tiêu kiểm thử và các invariant

Sau bài thực hành, một bộ test nên chứng minh được những tính chất sau:

1. Record **value bytes không hợp lệ** được phát hiện là deserialization failure thay vì được chuyển thành một DTO không đúng.
2. Listener xử lý business event **không được gọi** như thể record malformed là sự kiện hợp lệ.
3. Record lỗi được **cách ly vào DLT** hoặc khiến consumer dừng theo chính sách đã công bố; không bị bỏ âm thầm.
4. Nếu chọn DLT rồi tiếp tục, record hợp lệ **phía sau trong cùng partition** được xử lý.
5. DLT giữ được **raw bytes** và metadata nguồn đủ để điều tra topic, partition, offset.
6. Khi DLT publish thất bại, hệ thống không tự tuyên bố đã recovery thành công và bỏ offset không thể lấy lại.
7. Restart consumer và khả năng redelivery/duplicate được xử lý theo ack mode và idempotency đã thiết kế.
8. Key deserialization, message conversion và business validation **không bị nhầm là cùng một loại lỗi**.

Mỗi invariant cần có kiểm chứng rõ ràng. Ví dụ “listener tiếp tục” nên được assert bằng record hợp lệ sau poison pill, không phải chỉ bằng một log “consumer started”.

## 2. Kafka deserialization xảy ra trước listener

Kafka broker lưu record dưới dạng key/value byte arrays và metadata về topic, partition, offset. Trong consumer:

~~~mermaid
flowchart TD
    A["Kafka broker: key/value bytes"] --> B["KafkaConsumer.poll()"]
    B --> C["Key deserializer"]
    C --> D["Value deserializer"]
    D -->|Thành công| E["Spring Kafka listener container"]
    E --> F["@KafkaListener nhận OrderEvent"]
    D -->|Deserializer trực tiếp ném lỗi| G["Exception từ poll()\nlistener chưa chạy"]
    D -->|ErrorHandlingDeserializer bắt lỗi| H["Header chứa DeserializationException\nvalue thường là null"]
    H --> I["CommonErrorHandler / DefaultErrorHandler"]
    I --> J["Recovery: DLT, stop hoặc chính sách khác"]
~~~

Ví dụ:

~~~text
topic     = orders.events
partition = 0
offset    = 42
key bytes = UTF8("order-42")
value     = UTF8("{broken-json")
~~~

Nếu `JsonDeserializer` không thể biến value thành `OrderEvent`, Java code trong listener **không có một object `OrderEvent` để nhận**. Lỗi có thể xuất hiện từ `KafkaConsumer.poll()`. Khi dùng deserializer trực tiếp, một error handler vốn xử lý `ConsumerRecord` ở listener container không nhất thiết có đủ record context để recovery thông thường.

### Phân biệt lỗi theo tầng

| Loại lỗi | Vị trí | Ví dụ | Điều cần test |
|---|---|---|---|
| **Key deserialization** | Consumer giải mã key bytes. | Key JSON malformed. | Không kẹt, DLT giữ được raw key. |
| **Value deserialization** | Consumer giải mã value bytes. | JSON sai cú pháp, type header không tin cậy. | Header lỗi, DLT raw value, record sau vẫn chạy. |
| **Message conversion** | Spring chuyển record thành tham số/payload. | Converter không tạo được DTO. | Conversion error handler, không giả định cùng wrapper. |
| **Business validation** | Listener/service xử lý object hợp lệ. | `amount <= 0`. | Error policy nghiệp vụ, retry/skip riêng. |
| **Business infrastructure** | Service trong listener gọi DB/API. | DB timeout, HTTP 503. | Retry/backoff, transaction/idempotency. |

Một JSON hợp lệ nhưng thiếu field chưa chắc tạo deserialization exception; tùy ObjectMapper, dữ liệu có thể thành `null` hoặc giá trị mặc định rồi lỗi ở validation. Muốn chắc chắn gây **raw parsing failure**, dùng một payload sai cú pháp thực sự.

## 3. Vì sao unit test gọi listener trực tiếp chưa đủ?

Ví dụ:

~~~java
OrderEvent event = new OrderEvent("ORD-1", 100);
listener.handle(event);
~~~

Đoạn test này xác minh nghiệp vụ khi DTO **đã** được tạo. Nó không đi qua broker, deserializer, error headers, consumer poll, container ack/offset hoặc DLT. Vì thế nó không chứng minh một poison pill có thể được xử lý.

Một integration test deserialization cần dùng producer với `ByteArraySerializer` để gửi **bytes thô không hợp lệ**, sau đó dùng consumer/config production-like để quan sát kết quả. Nếu test chỉ mock `JsonDeserializer.deserialize` ném exception, phần xử lý hồi phục giữa Kafka client và Spring listener container vẫn chưa được xác thực.

## 4. Sai lầm khi dùng JsonDeserializer trực tiếp

Một cấu hình ban đầu có thể là:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Khi record malformed gây lỗi trong `poll()`, một `DefaultErrorHandler` ở tầng listener không tự xử lý được mọi `SerializationException` như lỗi listener bình thường. Có phiên bản/luồng thông báo rằng error handler không thể xử lý `SerializationException` trực tiếp và gợi ý `ErrorHandlingDeserializer`.

Nếu container tiếp tục đọc lại đúng record mà không có recovery, partition có thể bị **kẹt một offset**, các bản ghi hợp lệ phía sau không được xử lý. Restart process với cùng group vẫn có thể gặp lại record hỏng.

Điểm cần ghi nhớ: **`DefaultErrorHandler` không thay thế cho cấu hình deserializer phù hợp**. Với raw JSON errors, cách Spring Kafka thường khuyến nghị là dùng `ErrorHandlingDeserializer` làm wrapper cho delegate `JsonDeserializer`.

## 5. ErrorHandlingDeserializer biến lỗi thành dữ liệu có thể xử lý

`org.springframework.kafka.support.serializer.ErrorHandlingDeserializer` gọi một **delegate deserializer**. Khi delegate thành công, wrapper trả về DTO. Khi delegate ném exception, wrapper lưu thông tin `DeserializationException` vào Kafka headers theo cơ chế Spring Kafka và thông thường trả `null`. Spring Kafka listener container phát hiện header lỗi, rồi chuyển tới `CommonErrorHandler` trước khi listener record được gọi như thường lệ.

~~~mermaid
flowchart TD
    A["Raw value bytes"] --> B["ErrorHandlingDeserializer"]
    B --> C["Delegate: JsonDeserializer"]
    C --> D{"Decode OK?"}
    D -->|Có| E["OrderEvent đến listener"]
    D -->|Không| F["Exception header + raw bytes\nvalue null"]
    F --> G["Spring Kafka container"]
    G --> H["DefaultErrorHandler"]
    H --> I["DeadLetterPublishingRecoverer"]
    I --> J["orders.events.DLT"]
~~~

Wrapper **không tự gửi DLT** và cũng không tự quyết định skip. Nó tạo một đường đi để container error handler phân loại lỗi và áp dụng recovery policy. Nếu cấu hình `failedDeserializationFunction`, wrapper có thể trả một object fallback; khi đó test cần xác định liệu object ấy được đưa đến listener hay vẫn phải xử lý theo headers.

Với batch listener, cách xử lý khác record listener và cần được test riêng ở phần sau.

## 6. Cấu hình Spring Boot dùng wrapper cho value

Giả sử topic `orders.events` chứa JSON:

~~~json
{"id":"ORD-1","amount":100}
~~~

DTO:

~~~java
package com.example.kafka;

public record OrderEvent(String id, long amount) {}
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: orders-processor
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.kafka.OrderEvent
        spring.json.trusted.packages: com.example.kafka
        spring.json.use.type.headers: false
    listener:
      ack-mode: record
~~~

Các property thể hiện ý định:

- Deserializer cấp Kafka client thực tế là `ErrorHandlingDeserializer`.
- `spring.deserializer.value.delegate.class` chọn `JsonDeserializer` làm delegate.
- `spring.json.value.default.type` quy định DTO cho JSON không dùng type headers.
- `spring.json.use.type.headers: false` hợp lý trong demo một topic có target type cố định.
- `spring.json.trusted.packages` giới hạn package được phép deserialize; không đặt `*` tùy tiện chỉ để test qua.
- `ack-mode: record` và `enable-auto-commit: false` dùng cơ chế commit của container, nhưng **không chứng minh offset commit ngay** sau khi error handler chạy trong mọi tình huống.

Nếu producer gắn type headers, ứng dụng có thể dùng type mappings hoặc schema contract khác. Đừng thay `trusted.packages` thành wildcard để vượt một lỗi compatibility mà chưa hiểu rủi ro deserialize type ngoài dự kiến.

### Nếu lỗi ở key?

Key cũng có thể được bọc bằng `ErrorHandlingDeserializer`, ví dụ topic có JSON key riêng:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.key.default.type: com.example.kafka.OrderKey
~~~

Đây là **fragment thay key policy**, không tự ý áp cho topic dùng String key. Nếu key deserialize lỗi, key có thể được chuyển sang dạng **raw `byte[]` khi gửi DLT**, nên producer DLT cũng phải có key serializer phù hợp. Không dùng `StringSerializer` cho raw key bytes rồi mong recoverer tự sửa.

## 7. Chọn chính sách với một record không decode được

Mỗi loại nguồn dữ liệu có quy tắc riêng. Một record tham khảo sai format có thể được cách ly và cho luồng chạy tiếp; một giao dịch bắt buộc có thể cần dừng toàn bộ consumer group hoặc ngăn downstream công bố kết quả.

| Policy | Ý nghĩa | Khi phù hợp | Cần kiểm chứng |
|---|---|---|---|
| **Stop/fail** | Consumer dừng hoặc giữ offset để xử lý sự cố. | Mọi event đều bắt buộc, không được tự bỏ. | Có alert, runbook, không retry âm thầm mãi. |
| **DLT rồi tiếp tục** | Phát raw record lỗi sang dead-letter topic. | Cho phép cô lập record riêng lẻ. | DLT nhận bytes/header, consumer chạy record sau. |
| **Retry có giới hạn** | Thử lại khi lỗi có thể tạm thời. | Schema registry hoặc dependency tạm lỗi. | Backoff/timeout; không retry JSON malformed vô hạn. |
| **Fallback payload** | Trả object mô tả decode failure. | Application tự phân luồng xử lý lỗi. | Fallback không bị coi là event nghiệp vụ hợp lệ. |
| **Discard theo policy** | Cho offset tiến nhưng không giữ record. | Chỉ khi được phê duyệt nghiệp vụ. | Audit, cảnh báo, thống kê phần bị bỏ. |

Một `{broken-json` không tự trở thành JSON hợp lệ dù retry 1.000 lần. Nếu lỗi do producer gửi bytes sai cú pháp, phương án thường cần sửa producer hoặc dữ liệu nguồn, không chờ parser “tự hồi phục”.

## 8. DefaultErrorHandler và DeadLetterPublishingRecoverer

Spring Kafka có `DefaultErrorHandler` làm cơ chế lỗi record thông dụng và `DeadLetterPublishingRecoverer` để gửi record lỗi sang DLT.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.support.serializer.DeserializationException;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<String, Object> dltKafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(
        dltKafkaTemplate,
        (record, error) ->
            new TopicPartition(record.topic() + ".DLT", record.partition())
    );

    // Demo: không có retry bổ sung cho record đã được recover.
    var handler = new DefaultErrorHandler(
        recoverer, new FixedBackOff(0L, 0L));

    handler.addNotRetryableExceptions(DeserializationException.class);
    return handler;
}
~~~

Ý nghĩa:

1. Destination là `orders.events.DLT` nếu nguồn là `orders.events`.
2. Giữ nguyên source partition, vì thế topic DLT phải có **ít nhất số partition tương ứng**.
3. `FixedBackOff(0L, 0L)` không có retry thêm; phù hợp demo lỗi JSON vĩnh viễn. Lỗi transient của listener cần policy khác.
4. Deserialization errors thường đã được phân loại fatal/non-retryable trong `DefaultErrorHandler` ở các phiên bản tương ứng; khai báo tường minh cho thấy chủ đích.
5. DLT publication không có nghĩa consumer phía DLT đã xử lý nghiệp vụ xong.

**Điểm dễ bị bỏ qua:** Khi `ErrorHandlingDeserializer` fail với **value**, `DeadLetterPublishingRecoverer` có thể dùng lại **raw `byte[]`** làm value của record DLT. Với một listener failure sau khi JSON decode thành công, value có thể là `OrderEvent`. Producer dùng để ghi DLT cần serializer tương ứng cho những type nó thực sự gặp.

### DLT publisher lỗi thì sao?

Nếu recoverer không thể publish vì DLT topic thiếu, producer serializer sai, ACL từ chối hoặc broker không ACK, một hệ thống yêu cầu không mất record phải **không coi đó là recovery thành công**. Cần kiểm chứng publisher acknowledgement, hành vi của error handler khi recoverer ném lỗi, và commit offset gốc theo ack mode/transaction settings cụ thể. Đừng áp dụng kết luận “sau error handler thì offset luôn được commit” cho mọi cấu hình.

## 9. DLT KafkaTemplate xử lý cả raw bytes và DTO

Trong ví dụ chỉ kiểm thử **value deserialization failure với key dạng String**, có thể dùng `DelegatingByTypeSerializer` ở DLT producer:

~~~java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.Serializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

@Bean
ProducerFactory<String, Object> dltProducerFactory(
        @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers) {

    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

    Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
    delegates.put(byte[].class, new ByteArraySerializer());
    delegates.put(OrderEvent.class, new JsonSerializer<>());

    return new DefaultKafkaProducerFactory<>(
        props,
        new StringSerializer(),
        new DelegatingByTypeSerializer(delegates)
    );
}

@Bean
KafkaTemplate<String, Object> dltKafkaTemplate(
        ProducerFactory<String, Object> dltProducerFactory) {
    return new KafkaTemplate<>(dltProducerFactory);
}
~~~

Producer template này có thể serialize value kiểu `byte[]` và `OrderEvent` theo chính sách demo. Nếu hệ thống gửi nhiều loại DTO hoặc exception của listener có kiểu khác, cần mở rộng serializer mappings hoặc thiết kế envelope DLT. Nếu **key deserialization cũng có thể fail**, key có thể trở thành `byte[]`; `StringSerializer` của ví dụ không phù hợp cho case đó và phải được thay bằng cơ chế mixed key serializers hoặc template thích hợp.

`ENABLE_IDEMPOTENCE_CONFIG=true` của producer giúp giảm duplicate trong một số retry của producer theo Kafka semantics, nhưng không làm workflow **end-to-end exactly once**. App có thể crash sau ACK trước khi commit source offset, rồi gửi lại cùng record DLT trong lượt recovery tiếp theo.

## 10. Listener dùng để chứng minh consumer tiến lên

Một listener tối giản:

~~~java
package com.example.kafka;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final BlockingQueue<String> processed =
        new LinkedBlockingQueue<>();

    @KafkaListener(topics = "orders.events", groupId = "orders-processor")
    public void handle(OrderEvent event) {
        processed.add(event.id());
    }

    public String awaitProcessedId(long timeoutSeconds)
            throws InterruptedException {
        return processed.poll(timeoutSeconds, TimeUnit.SECONDS);
    }
}
~~~

Phần queue chỉ làm test probe. Consumer thực tế có thể ghi database hoặc gọi service và phải có idempotency nếu record được redeliver.

Test sẽ gửi **hai record trên cùng partition**:

~~~text
offset N:   key="bad-1",  value=bytes("{broken-json")
offset N+1: key="good-2", value=bytes("{\"id\":\"ORD-2\",\"amount\":100}")
~~~

Sau khi lỗi được đưa DLT:

- Listener không thấy một `OrderEvent` thành công từ bad-1.
- DLT chứa raw bytes `{broken-json`.
- Listener nhận `ORD-2`, chứng minh partition không bị chặn bởi poison pill.

Đây là điểm test quan trọng hơn chỉ thấy “message đã được gửi” ở producer.

## 11. Integration test với Embedded Kafka

Dependency test thường cần `spring-boot-starter-test` và `spring-kafka-test`. Dùng `@EmbeddedKafka` để tạo broker/topic trong test, và một Kafka producer test **dùng ByteArraySerializer cho value** để gửi raw bytes sai.

~~~java
package com.example.kafka;

import static java.nio.charset.StandardCharsets.UTF_8;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.ByteArrayDeserializer;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.events", "orders.events.DLT"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class DeserializationFailureIntegrationTest {

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Autowired
    OrderListener listener;

    @Test
    void malformedValueGoesToDltAndValidValueContinues() throws Exception {
        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            embeddedKafka.getBrokersAsString());

        byte[] invalid = "{broken-json".getBytes(UTF_8);
        byte[] valid =
            "{\"id\":\"ORD-2\",\"amount\":100}".getBytes(UTF_8);

        try (var producer = new KafkaProducer<>(
                props, new StringSerializer(), new ByteArraySerializer())) {

            producer.send(new ProducerRecord<>(
                "orders.events", "bad-1", invalid))
                .get(10, TimeUnit.SECONDS);

            producer.send(new ProducerRecord<>(
                "orders.events", "good-2", valid))
                .get(10, TimeUnit.SECONDS);
        }

        // Chứng minh consumer không bị kẹt tại bản ghi malformed.
        assertThat(listener.awaitProcessedId(10)).isEqualTo("ORD-2");

        Map<String, Object> dltProps = KafkaTestUtils.consumerProps(
            "dlt-reader-" + UUID.randomUUID(),
            "false",
            embeddedKafka
        );
        dltProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        try (Consumer<String, byte[]> dltConsumer =
                new DefaultKafkaConsumerFactory<>(
                    dltProps,
                    new StringDeserializer(),
                    new ByteArrayDeserializer()
                ).createConsumer()) {

            dltConsumer.subscribe(List.of("orders.events.DLT"));

            ConsumerRecord<String, byte[]> dlt =
                KafkaTestUtils.getSingleRecord(
                    dltConsumer,
                    "orders.events.DLT",
                    Duration.ofSeconds(15)
                );

            assertThat(dlt.key()).isEqualTo("bad-1");
            assertThat(dlt.value()).isEqualTo(invalid);
            assertThat(dlt.headers().lastHeader(
                KafkaHeaders.DLT_ORIGINAL_TOPIC)).isNotNull();
        }
    }
}
~~~

### Giả định của đoạn integration test

1. Application context có `OrderListener`, config `ErrorHandlingDeserializer` và error handler gửi DLT như các phần trên.
2. DLT producer có serializer hỗ trợ **raw `byte[]`** cho value và String key.
3. Test được cô lập: không có consumer group offset cũ hoặc DLT records từ test khác. Nếu nhiều test dùng chung broker, hãy dùng topic/group khác nhau hoặc reset fixture có kiểm soát.
4. `orders.events` và `orders.events.DLT` đều có partition 0.
5. Consumer đọc DLT dùng `ByteArrayDeserializer` để so sánh **bytes gốc**, không dùng lại JSON deserializer đã thất bại.
6. Queue của `OrderListener` không còn kết quả từ test trước; với suite lớn, nên có probe reset riêng hoặc test context cô lập.
7. `KafkaTestUtils.getSingleRecord` phù hợp khi dự kiến một DLT record. Nếu cố ý gửi nhiều record lỗi, poll/lọc theo key và original source offset phù hợp.

Đây là ví dụ **kiểm thử luồng thực** và cần các bean/config của ứng dụng. Nó không được viết để thay thế test transaction, security, nhiều broker và consumer rebalance trên môi trường gần production.

## 12. Xác minh original topic, partition và offset

Không chỉ assert DLT có raw bytes; metadata nguồn giúp điều tra record trong broker. `DeadLetterPublishingRecoverer` có thể thêm headers mô tả topic, partition và offset gốc. Ví dụ trong phạm vi test có biến `dlt`:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.support.KafkaHeaders;

Header sourceTopic = dlt.headers().lastHeader(
    KafkaHeaders.DLT_ORIGINAL_TOPIC);

assertThat(sourceTopic).isNotNull();
assertThat(new String(
    sourceTopic.value(), StandardCharsets.UTF_8))
    .isEqualTo("orders.events");

assertThat(dlt.headers().lastHeader(
    KafkaHeaders.DLT_ORIGINAL_PARTITION)).isNotNull();

assertThat(dlt.headers().lastHeader(
    KafkaHeaders.DLT_ORIGINAL_OFFSET)).isNotNull();
~~~

Khi cần assert số offset chính xác, hãy lấy `RecordMetadata.offset()` từ kết quả producer gửi malformed record, thay vì hard-code `0`. Trong một broker đã có dữ liệu, offset không bắt đầu từ 0 theo kỳ vọng của test.

Các headers exception có thể chứa class, message hoặc stack trace. Không đưa raw exception header/payload vào log tập trung nếu chứa PII, token hoặc thông tin nội bộ. DLT cần ACL, retention, kiểm soát replay và phân quyền xem dữ liệu phù hợp.

## 13. Negative test không có ErrorHandlingDeserializer

Tạo **một test context/consumer group riêng** dùng `JsonDeserializer` trực tiếp rồi gửi malformed bytes. Kiểm chứng:

- Deserialization-related error xảy ra từ luồng tiêu thụ trước listener.
- Listener không nhận event sai như một DTO hợp lệ.
- Error handler record-based không nhất thiết có thể phục hồi như với wrapper.
- Consumer có thể lặp lại lỗi trên cùng record nếu không có chính sách xử lý đặc biệt.

Không làm negative test trên chính group/topic của test DLT tích cực, nếu không một record xấu có thể làm test khác mắc kẹt. Mục đích của test này là **chứng minh ranh giới lỗi nằm trước listener**, không phụ thuộc vào chuỗi log cụ thể của một version Spring Kafka.

## 14. Kiểm thử lỗi key deserialization

Nếu key được serialize bằng JSON `OrderKey` thay vì String, cần kiểm thử riêng:

~~~text
key bytes   = "{broken-key"
value bytes = "{\"id\":\"ORD-3\",\"amount\":10}"
~~~

Trong test, dùng `ByteArraySerializer` cho cả key và value để tạo raw record:

~~~java
ProducerRecord<byte[], byte[]> badKey = new ProducerRecord<>(
    "orders.events",
    "{broken-key".getBytes(UTF_8),
    "{\"id\":\"ORD-3\",\"amount\":10}".getBytes(UTF_8)
);
~~~

Đây là fragment tạo record; test thực phải có producer và consumer JSON-key config riêng. Kỳ vọng:

1. Wrapper cho key nhận lỗi và container xử lý đúng error header.
2. Listener không nhận event sai như thành công.
3. DLT giữ được original raw **key bytes**.
4. DLT producer có serializer cho byte[] key, không dựa vào `StringSerializer`.
5. Sau recovery, valid record cùng partition vẫn được xử lý theo policy.

Nếu DLT chưa nhận được record, hãy kiểm tra **producer DLT**, không chỉ consumer deserializer: serializer mismatch, topic không đủ partitions, thiếu quyền publish hoặc broker timeout đều có thể gây lỗi ở bước recovery.

## 15. JSON hợp lệ nhưng business data sai: không phải cùng bài test

Payload:

~~~json
{"id":"ORD-4","amount":-100}
~~~

Đây là JSON hợp lệ, có thể deserialize thành `OrderEvent`. Nếu application yêu cầu amount dương:

~~~java
if (event.amount() <= 0) {
    throw new InvalidOrderException("INVALID_AMOUNT");
}
~~~

thì lỗi thuộc **business validation** trong listener/service, không phải deserialization. Test riêng cần xác minh handler retry/DLT theo loại exception nghiệp vụ. Không sử dụng loại lỗi này để tuyên bố đã kiểm tra malformed JSON.

Tương tự, nếu JSON thiếu `id`, Jackson có thể vẫn tạo object với `null` tùy cấu hình. Muốn tạo deserialization failure chắc chắn, hãy dùng cú pháp JSON không hợp lệ hoặc mapping constraint đã được cấu hình rõ và được kiểm chứng tại tầng deserializer.

### Type headers, trusted packages và schema mismatch

Một topic chứa nhiều event type có thể dùng type headers hoặc schema registry. Lỗi có thể do:

- Producer gửi type header lạ.
- Consumer không tin cậy package hoặc type chưa được mapping.
- Schema version không tương thích.
- Payload serialized theo format khác.
- Decode thành công nhưng nội dung/semantics chưa đúng contract.

Test nên phân loại đúng tầng lỗi và giữ chính sách trusted packages an toàn. Đừng sửa lỗi bằng `spring.json.trusted.packages=*` khi chưa có đánh giá bảo mật. Với Avro/Protobuf/registry, dùng bộ serializer/deserializer thật và lỗi phiên bản tương ứng; JSON test không thay thế toàn bộ protocol đó.

## 16. Batch listener cần test deserialization riêng

Một `@KafkaListener` có thể xử lý từng record hoặc một batch:

~~~java
@KafkaListener(
    topics = "orders.events",
    containerFactory = "batchKafkaListenerContainerFactory"
)
void handleBatch(java.util.List<OrderEvent> orders) {
    // ...
}
~~~

Trong batch listener, `ErrorHandlingDeserializer` có thể khiến vị trí của record lỗi chứa payload null và header deserialization exception. Cách chuyển lỗi sang error handler **không tự giống record listener**. Tùy cơ chế batch converter/container, application có thể cần xem exception header theo index và ném `BatchListenerFailedException` chỉ rõ record/index lỗi.

Test ví dụ với 5 record và một lỗi ở index 2:

| Tình huống | Cần chứng minh |
|---|---|
| Index 0,1 hợp lệ | Được xử lý đúng trước khi failure được xác định. |
| Index 2 malformed | Listener nhận diện chính xác index/offset lỗi. |
| Index 3,4 hợp lệ | Sau recovery, không mất hoặc xử lý trùng ngoài semantics retry. |
| Batch rollback/replay | Business handler chịu được redelivery. |
| Record lỗi chuyển DLT | Đúng raw bytes và metadata, không sai offset. |

Không chỉ chạy record-listener test rồi kết luận batch-listener production cũng tin cậy. Chính sách batch retry, partial batch processing, converter và ack mode cần được xác minh đúng cấu hình.

## 17. Poison pill trong partition và consumer progression

Ví dụ:

~~~text
orders.events partition 0:
  offset 100: valid A
  offset 101: malformed JSON
  offset 102: valid B
  offset 103: valid C

orders.events partition 1:
  offset 77: valid D
~~~

Với chính sách “DLT rồi tiếp tục”, kỳ vọng A, B, C được xử lý đúng thứ tự trong partition 0, record offset 101 được cách ly, và partition 1 vẫn hoạt động theo nhóm consumer. Không nên assert **thứ tự tuyệt đối giữa hai partition**, vì Kafka chỉ bảo đảm thứ tự theo partition.

Với policy stop/fail nghiêm ngặt, kết quả đúng có thể là container dừng/pause và alert. Tin cậy không luôn đồng nghĩa “skip mọi record hỏng”; nó là hành vi nhất quán với business contract đã chọn.

DLT **không xóa record gốc** khỏi source topic. Một group khác hoặc reset offset có thể gặp lại cùng malformed bytes. Test cần phân biệt **sự tồn tại của record trong Kafka log** với **vị trí tiêu thụ/committed offset của một consumer group**.

## 18. Kiểm tra offset sau khi recovery và restart

Để kiểm chứng bền vững:

1. Gửi record malformed rồi valid record **trong cùng partition**.
2. Đợi recoverer xuất DLT và listener xử lý record hợp lệ.
3. Dừng container có điều khiển, chờ consumer rời group.
4. Truy vấn committed offset của group hoặc khởi động lại container với cùng group ID.
5. Xác nhận không mắc kẹt vô hạn ở record malformed đã được recovery.
6. Nếu có redelivery do crash/commit race, DLT và business consumer phải xử lý duplicate an toàn.

`AckMode.RECORD`, `MANUAL`, `MANUAL_IMMEDIATE` và các tùy chọn error handler/transaction có hành vi commit khác nhau. **Không giả định offset được commit ngay khi callback recoverer kết thúc**. Test phải xác định rõ:

- *Functional progression*: valid record phía sau được xử lý.
- *Durable progression*: committed offset/đường chạy lại phù hợp với policy khi consumer restart.

Tránh `Thread.sleep(...)` tùy ý để đoán offset đã được commit; dùng synchronization, chờ trạng thái container/group và timeout có kiểm soát.

## 19. Failure injection ở DLT publisher

Một test DLT happy path chưa bao phủ lỗi ở chính recovery pipeline. Cần diễn tập:

| Failure được tạo | Điều cần xác nhận |
|---|---|
| DLT topic không tồn tại khi auto-creation bị tắt. | Recoverer fail đúng cách; không silent-loss record nguồn. |
| Producer thiếu quyền ghi DLT. | Alert/đường retry phù hợp; không thông báo recovery thành công giả. |
| DLT ít partition hơn source. | Lỗi chọn partition được phát hiện; sửa topic topology. |
| DLT value producer không hỗ trợ `byte[]`. | Serialization error được báo, không coi là đã gửi. |
| Key deserialization fail nhưng DLT key serializer chỉ nhận String. | Serializer mismatch được phát hiện bằng test key path. |
| Broker không ACK hoặc publish timeout. | Error handler giữ recovery semantics/offset theo cấu hình. |
| Crash sau DLT ACK trước commit source offset. | Có thể xuất hiện DLT duplicate, đường xử lý DLT idempotent. |
| DLT consumer dùng lại JsonDeserializer cho raw malformed bytes. | Test thất bại đúng vị trí; cần DLT reader raw bytes/envelope. |

Muốn chứng minh “record không bị mất”, phải xem **xác nhận broker ghi DLT** và **hành vi offset gốc** khi publication thất bại, không chỉ assert `DeadLetterPublishingRecoverer.accept(...)` được gọi. Nếu recoverer publish bất đồng bộ, cần cấu hình/kiểm chứng thời điểm hoàn thành future và cơ chế timeout theo phiên bản thực tế.

## 20. DLT replay và sửa dữ liệu

DLT là **nơi cách ly** record lỗi, không phải là “đã xử lý nghiệp vụ”. Ví dụ metadata DLT:

~~~text
originalTopic     = orders.events
originalPartition = 0
originalOffset    = 42
rawValue          = "{broken-json"
errorCategory     = DESERIALIZATION
~~~

Một quy trình replay có kiểm soát:

1. Xác định lỗi do record bytes thực sự sai, schema/version không tương thích, consumer deployment sai hay type header không tin cậy.
2. Kiểm tra source producer và payload format; xác định bản sửa có hợp đồng dữ liệu hợp lệ.
3. Nếu raw bytes hỏng vĩnh viễn, quarantine hoặc yêu cầu upstream phát lại phiên bản đúng; không replay nguyên bytes sai vào topic gốc vô hạn.
4. Nếu consumer config/schema đã được sửa, replay bằng event key ổn định và có monitoring cho kết quả.
5. Áp dụng idempotency cho business effect của consumer vì DLT có thể chứa duplicate do recovery race.
6. Lưu outcome `REPLAYED`, `REJECTED_FINAL` hoặc `WAITING_FOR_SOURCE_FIX` theo audit của ứng dụng.

Có thể tạo source reference từ original topic, partition và offset:

~~~text
sourceRecordRef = originalTopic + ":" +
                  originalPartition + ":" + originalOffset
~~~

Đây là **định danh vị trí** trong một Kafka log/cluster, không phải business ID toàn cầu. Khi producer phát lại một event với offset mới, business key vẫn là chìa khóa để tránh thực hiện tác động trùng.

## 21. Observability: log điều gì và cảnh báo khi nào?

Một sự kiện log nên ghi metadata vừa đủ để điều tra, không dump raw payload:

~~~json
{
  "event": "kafka.deserialization.failed",
  "consumerGroup": "orders-processor",
  "topic": "orders.events",
  "partition": 0,
  "offset": 42,
  "errorCategory": "INVALID_JSON",
  "recoveryAction": "DLT",
  "dltTopic": "orders.events.DLT"
}
~~~

Đây là schema **ứng dụng tự định nghĩa**, không phải log mặc định. Những giá trị như key, headers và raw payload có thể chứa PII/token, nên chỉ lưu vào DLT hoặc công cụ có quyền/retention phù hợp nếu nghiệp vụ yêu cầu.

Các chỉ số cần quan sát:

| Chỉ số | Vấn đề phát hiện |
|---|---|
| Deserialization errors theo topic/error category | Một producer/schema rollout mới gây lỗi hàng loạt? |
| DLT publish success/failure | Recovery có hoạt động hay đang mất đường cách ly? |
| DLT backlog và oldest pending age | Bao nhiêu record chưa được remediation? |
| Consumer group lag theo partition | Có một poison pill giữ offset không tiến? |
| Retry attempts và thời gian recovery | Có retry vô hạn hoặc backoff bất hợp lý? |
| Lượng record hợp lệ được xử lý sau lỗi | Container có thực sự tiếp tục không? |
| Replay success/failed/dropped | DLT có trở thành “hố đen dữ liệu” không? |

Không dùng offset, event ID hoặc correlation ID duy nhất làm **metric label phổ biến** vì cardinality tăng mạnh. Dùng log/audit cho định danh chi tiết, metric cho nhóm hữu hạn.

Cảnh báo nên phân biệt:

- Một malformed record được DLT thành công: warning tùy policy.
- DLT publish fail: critical nếu không có đường recovery khác.
- Error rate tăng đột biến: có thể toàn bộ producer sai schema.
- Consumer lag tăng liên tục tại một partition: có thể mắc poison pill.
- DLT tồn đọng lâu: record đã được giữ nhưng chưa có quyết định nghiệp vụ cuối.

## 22. Ma trận kiểm thử tin cậy

| Mã | Dữ liệu hoặc failure | Kỳ vọng |
|---|---|---|
| D-01 | JSON đúng schema. | Listener xử lý, không DLT. |
| D-02 | JSON malformed `{broken-json`. | ErrorHandlingDeserializer báo lỗi, DLT raw bytes. |
| D-03 | Malformed rồi valid cùng partition. | Valid phía sau được xử lý. |
| D-04 | Key JSON malformed. | Key error path, DLT raw key/serializer phù hợp. |
| D-05 | JSON hợp lệ, amount âm. | Business validation error, không gán nhầm deserialize. |
| D-06 | Untrusted type header. | Không deserialize class ngoài policy; recovery đúng. |
| D-07 | JSON đúng cú pháp nhưng sai mapping type. | Loại lỗi được phân loại tại tầng chính xác. |
| D-08 | DLT topic thiếu/ACL từ chối. | Không silent-ack như recovery thành công. |
| D-09 | DLT producer sai serializer. | Test bắt serialization/publish failure. |
| D-10 | Restart sau record malformed. | Offset progression và possible replay đúng policy. |
| D-11 | Crash sau DLT ACK. | Có thể duplicate, DLT consumer idempotent. |
| D-12 | Multi-partition có một poison pill. | Partition khác hoạt động theo policy, không đòi global order. |
| D-13 | Batch listener có malformed ở index giữa. | Xác định đúng index/offset và recovery. |
| D-14 | Schema registry tạm không khả dụng. | Retry/backoff giới hạn nếu được phân loại transient. |
| D-15 | Malformed hàng loạt. | Error rate/quality alert, không công bố dữ liệu sai. |
| D-16 | DLT chứa PII giả lập. | Log/metric không xuất payload nhạy cảm, quyền phù hợp. |
| D-17 | Replay sau producer/consumer fix. | Kết quả nghiệp vụ không bị nhân đôi. |

Với dự án nhỏ, thực hiện D-01, D-02, D-03, D-08 và D-10 trước. Các kịch bản này chứng minh cơ chế decode, recovery, progression và restart mà một unit test listener không thể bao phủ.

## 23. Làm test ổn định và không phụ thuộc timing ngẫu nhiên

Integration test Kafka dễ flaky khi chỉ `Thread.sleep(1000)` rồi assert. Thực hành tốt:

1. **Dùng topic/group riêng** cho mỗi test hoặc dọn fixture có kiểm soát.
2. **Chờ producer ACK** bằng `Future.get(timeout)` trước khi quan sát consumer.
3. **Chờ listener bằng queue/latch/Awaitility**, có timeout hữu hạn.
4. **Dùng offset thực từ RecordMetadata** cho assert offset DLT; không hard-code.
5. **Gửi raw malformed bytes cố định**, không dựa vào rule validation có thể thay đổi.
6. **Tách test probe khỏi business side effects**, hoặc dùng database test idempotent.
7. **Kiểm soát consumer lifecycle**, topic partition assignment và offset group khi test restart.
8. **Đọc DLT bằng ByteArrayDeserializer** cho record deserialize failure.
9. **Không phụ thuộc chuỗi exception message cụ thể**, ưu tiên exception class/category và output behavior.
10. **Bổ sung test cluster gần production** khi cần ACL, TLS, rebalance, rolling upgrade, broker outage và nhiều partitions.

Embedded Kafka phù hợp để kiểm tra cơ chế container trong JVM/test process, nhưng không tự chứng minh mọi hạ tầng production. Với Testcontainers/Kafka cluster test, cần chờ broker ready, topic created, listener assigned trước khi gửi fixture.

## 24. Runbook khi production gặp deserialization failure

Người vận hành nên theo trình tự:

1. **Xác định topic/partition/offset và consumer group.** Thu thập timestamp, correlation ID nếu có.
2. **Phân loại lỗi:** key deserializer, value deserializer, conversion, validation hay listener service.
3. **Đọc cấu hình deserializer:** wrapper, delegate class, schema/type mapping, trusted packages và header policy.
4. **Kiểm tra DLT:** topic, partition, producer serializer, ACL, ACK, backlog và retention.
5. **Đánh giá phạm vi:** một record corrupt hay producer deploy gửi sai toàn bộ schema?
6. **Xác minh progression:** record hợp lệ sau poison pill được xử lý hay consumer group lag vẫn tăng?
7. **Sửa gốc và chọn remediation:** producer fix, consumer config fix, quarantine, DLT replay hoặc stop theo hợp đồng.
8. **Đối soát business side effects:** event bị redeliver có tạo dữ liệu trùng hay không?
9. **Đóng sự cố bằng bằng chứng:** record lỗi có outcome, offset/lag ổn, DLT backlog được xử lý.

Không reset consumer group offsets hoặc xóa DLT chỉ để biểu đồ hết đỏ. Reset offset có thể phát lại hàng triệu event đã xử lý; xóa DLT có thể làm mất record chưa remediation. Những hành động đó cần quyết định được phê duyệt, kế hoạch idempotency và audit.

## 25. Những sai lầm thường gặp

**“Thêm try/catch trong `@KafkaListener` là xong.”** Lỗi deserialize xảy ra trước listener, nên cần test qua raw bytes và container.

**“`DefaultErrorHandler` xử lý được mọi `SerializationException` từ poll.”** Không mặc định đúng với deserializer trực tiếp; `ErrorHandlingDeserializer` giúp chuyển lỗi thành header/context mà container xử lý được.

**“Bật wrapper là DLT tự xuất hiện.”** Wrapper không tự tạo recoverer, topic hay KafkaTemplate phù hợp.

**“DLT có record là consumer chắc chắn tiến tiếp.”** Phải assert valid record phía sau, cùng partition, và offset/restart semantics.

**“DLT chỉ cần JsonSerializer.”** Raw deserialization failure có thể đưa `byte[]` tới DLT producer; key error còn yêu cầu key serializer phù hợp.

**“JSON hợp lệ nhưng sai amount là deserialization failure.”** Nếu object được decode, đó thường là validation/business error và có policy riêng.

**“Retry nhiều lần sẽ sửa record malformed.”** Bytes trong Kafka log không đổi khi producer được sửa. Cần fix format/config rồi replay có chủ đích.

**“DLT luôn đúng một bản ghi, không duplicate.”** Crash sau ACK trước source offset commit có thể làm publish lại; phải chịu được duplicate.

**“EmbeddedKafka một bài test là đủ cho production.”** Còn broker outage, ACL/TLS, rebalance, multi-partition, CDC/replay và hạ tầng thực cần kiểm thử riêng.

**“Log nguyên payload/exception headers để debug cho nhanh.”** Có thể làm lộ PII, secrets hoặc dữ liệu nội bộ; ưu tiên metadata an toàn và DLT có phân quyền.

**“Discard malformed record luôn an toàn vì chỉ một record.”** Một record có thể là giao dịch bắt buộc; quyết định bỏ, DLT hay stop phải dựa trên hợp đồng dữ liệu.

## 26. Quy trình hoàn thành bài thực hành

1. Định nghĩa input contract của `orders.events`: key/value encoding, JSON target type và policy với malformed bytes.
2. Cấu hình `ErrorHandlingDeserializer` cho value và delegate `JsonDeserializer`.
3. Tạo `DefaultErrorHandler` với recoverer chọn `orders.events.DLT`.
4. Cấu hình DLT producer hỗ trợ raw `byte[]`; tạo topic/partition phù hợp.
5. Tạo listener/probe thread-safe nhận event hợp lệ.
6. Dùng `KafkaProducer<String,byte[]>` gửi malformed JSON rồi gửi valid JSON.
7. Assert valid record phía sau được listener xử lý.
8. Đọc DLT bằng `ByteArrayDeserializer`; assert bytes gốc và metadata nguồn.
9. Thử DLT publisher failure để bảo đảm không silent loss.
10. Dừng/khởi động lại consumer để kiểm chứng committed offset và duplicate tolerance.
11. Bổ sung test key deserialization, batch listener, untrusted type headers và multiple partitions.
12. Xây monitoring/runbook cho DLT backlog, error rate và replay có phê duyệt.

Một bộ test đạt mục tiêu khi chứng minh được cả **hành vi với record lỗi** và **hành vi với record đúng sau lỗi**, không chỉ một exception class. Nếu hệ thống quyết định dừng thay vì DLT thì test phải xác nhận dừng có kiểm soát và không mất dữ liệu, thay vì buộc mọi consumer phải skip.

## Kết luận

**Test deserialization failure** trong Spring Kafka phải bắt đầu từ **bytes không hợp lệ trên broker**, vì lỗi key/value deserializer có thể xảy ra trước `@KafkaListener` và khiến consumer mắc ở cùng offset. `ErrorHandlingDeserializer` tạo cầu nối đến cơ chế xử lý lỗi của Spring Kafka; `DefaultErrorHandler` và `DeadLetterPublishingRecoverer` cho phép cách ly record malformed sang DLT khi nghiệp vụ cho phép.

Đừng dừng ở assertion rằng “đã ném exception” hay “DLT có dữ liệu”. Kiểm thử tin cậy cần chứng minh **raw bytes và source metadata được giữ**, **record hợp lệ tiếp theo vẫn chạy**, **DLT publish failure không bị coi là thành công**, **offset/restart phù hợp với policy**, và **redelivery/duplicate không gây sai lệch dữ liệu nghiệp vụ**. Những invariant này biến deserialization failure từ một poison pill khó kiểm soát thành một tình huống có thể phát hiện, điều tra và phục hồi.

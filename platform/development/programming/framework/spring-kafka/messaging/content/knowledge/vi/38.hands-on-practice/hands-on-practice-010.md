# Mô phỏng lỗi deserialize

Consumer Kafka phải chuyển byte của record thành kiểu dữ liệu mà listener hiểu. Với Spring Kafka, `JsonDeserializer` thường thực hiện việc chuyển JSON thành DTO. Nếu payload bị cắt, JSON sai cú pháp, type metadata không đúng hoặc field không thể chuyển đổi, quá trình deserialize có thể thất bại ngay trong lúc consumer poll. Khi đó, phương thức `@KafkaListener` chưa được gọi nên không thể tự bắt exception bằng `try/catch` bên trong listener.

Bài thực hành này tạo một topic nhận sự kiện `OrderCreated`, cấu hình `ErrorHandlingDeserializer` bọc `JsonDeserializer`, cố ý gửi một payload JSON lỗi và dùng `DefaultErrorHandler` cùng `DeadLetterPublishingRecoverer` để chuyển record sang dead-letter topic (DLT). Cuối bài, ta đọc lại DLT để xác minh payload byte gốc và metadata lỗi vẫn còn để điều tra.

## 1. Mục tiêu và luồng thực hành

Sau khi hoàn thành, bạn có thể:

- Phân biệt lỗi deserialize với exception phát sinh bên trong listener.
- Cấu hình `ErrorHandlingDeserializer` và delegate `JsonDeserializer`.
- Hiểu vì sao listener không nhận được DTO khi payload không hợp lệ.
- Cấu hình `DefaultErrorHandler` để phục hồi lỗi deserialize.
- Dùng `DeadLetterPublishingRecoverer` gửi record lỗi sang DLT.
- Đọc payload byte gốc và các header nguồn từ DLT.

Luồng xử lý:

```text
Producer gửi JSON bytes
          |
          v
      orders-json
          |
          v
ErrorHandlingDeserializer
          |
          v
    JsonDeserializer
       /       \
  JSON hợp lệ   JSON lỗi
      |            |
      v            v
OrderCreated   exception được lưu vào headers
      |            |
      v            v
@KafkaListener  DefaultErrorHandler
                   |
                   v
          DeadLetterPublishingRecoverer
                   |
                   v
             orders-json.DLT
```

Record hợp lệ đi vào listener. Record không deserialize được được container nhận diện từ header của `ErrorHandlingDeserializer`; listener không được gọi cho record đó. Error handler chuyển record đến recoverer, recoverer publish sang DLT.

## 2. Chuẩn bị dependency và topic

Ứng dụng cần Spring Kafka và thư viện kiểm thử `spring-kafka-test` nếu chạy bài thực hành bằng Embedded Kafka. Với Maven:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu dùng Spring Boot dependency management, để BOM quản lý version tương thích. Không nâng riêng `spring-kafka-test` khác version với Spring Kafka của ứng dụng.

Tạo topic nguồn `orders-json` và topic DLT `orders-json.DLT`. Recoverer mặc định định tuyến record từ topic nguồn sang topic có hậu tố `.DLT` và thường giữ partition tương ứng. Vì vậy, DLT phải có ít nhất số partition tương ứng với topic nguồn. Trong bài lab dùng một partition cho mỗi topic để đơn giản hóa.

Với broker thật, nên tạo topic bằng quy trình quản trị hạ tầng, đồng thời cấu hình replication factor và ACL phù hợp. Không phụ thuộc vào broker auto-create trong production.

## 3. Tạo DTO và listener nhận sự kiện hợp lệ

Tạo DTO sự kiện đơn giản:

```java
package com.example.orders.events;

public record OrderCreated(
        String eventId,
        String orderId,
        String customerId) {
}
```

Listener nhận DTO và ghi nhận sự kiện để phục vụ xử lý nghiệp vụ:

```java
package com.example.orders.listener;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import com.example.orders.events.OrderCreated;

@Component
public class OrderListener {

    private final BlockingQueue<OrderCreated> received =
            new LinkedBlockingQueue<>();

    @KafkaListener(
            topics = "orders-json",
            groupId = "orders-deserialize-lab",
            containerFactory = "ordersListenerFactory")
    public void listen(OrderCreated event) {
        received.add(event);
    }

    public BlockingQueue<OrderCreated> received() {
        return received;
    }
}
```

`BlockingQueue` ở đây chỉ dùng để quan sát trong bài lab. Ứng dụng thật cần gọi service nghiệp vụ và chỉ hoàn tất listener sau khi side effect đã được lưu bền vững theo thiết kế.

## 4. Cấu hình ErrorHandlingDeserializer

`ErrorHandlingDeserializer` là wrapper gọi một deserializer delegate. Nếu delegate deserialize thành công, wrapper trả về object bình thường. Nếu delegate ném exception, wrapper lưu thông tin exception và dữ liệu gốc vào headers rồi trả về giá trị null để container có thể nhận diện lỗi.

Ví dụ cấu hình bằng Java:

```java
package com.example.orders.config;

import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import com.example.orders.events.OrderCreated;

@Configuration
@EnableKafka
public class OrdersConsumerConfiguration {

    @Bean
    ConsumerFactory<String, OrderCreated> ordersConsumerFactory(
            @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers) {

        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-deserialize-lab");
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                ErrorHandlingDeserializer.class);

        props.put(
                "spring.deserializer.value.delegate.class",
                JsonDeserializer.class);
        props.put(
                JsonDeserializer.VALUE_DEFAULT_TYPE,
                OrderCreated.class.getName());
        props.put(JsonDeserializer.TRUSTED_PACKAGES,
                "com.example.orders.events");
        props.put(JsonDeserializer.USE_TYPE_INFO_HEADERS, false);

        return new DefaultKafkaConsumerFactory<>(props);
    }
}
```

Các điểm cần chú ý:

- `VALUE_DESERIALIZER_CLASS_CONFIG` trỏ tới `ErrorHandlingDeserializer`, không trỏ trực tiếp tới `JsonDeserializer`.
- `spring.deserializer.value.delegate.class` chỉ định `JsonDeserializer` làm delegate cho value.
- `spring.json.value.default.type` xác định DTO mặc định cần tạo.
- `spring.json.trusted.packages` giới hạn package được phép deserialize khi xử lý type metadata.
- `spring.json.use.type.headers=false` yêu cầu consumer dùng kiểu mặc định thay vì phụ thuộc class name trong header.

Nếu dùng Spring Boot YAML, cấu hình tương đương có thể viết:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-deserialize-lab
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
        spring.json.use.type.headers: false
```

Không cấu hình trusted packages là `*` trong production nếu không có lý do bảo mật được đánh giá. Chỉ cho phép các package contract mà consumer cần deserialize.

## 5. Cấu hình producer có thể gửi cả DTO và byte[]

Ta cần gửi hai loại value lên cùng topic:

- `OrderCreated` hợp lệ để kiểm tra luồng bình thường.
- `byte[]` chứa JSON sai cú pháp để mô phỏng lỗi deserialize.

Recoverer cũng cần publish lại dữ liệu byte gốc sang DLT. Vì vậy, producer factory dùng `DelegatingByTypeSerializer`: `byte[]` đi qua `ByteArraySerializer`, còn object thông thường đi qua `JsonSerializer`.

```java
package com.example.orders.config;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.Serializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

@Configuration
public class OrdersProducerConfiguration {

    @Bean
    ProducerFactory<String, Object> ordersProducerFactory(
            @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers) {

        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ProducerConfig.ACKS_CONFIG, "all");

        Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
        delegates.put(byte[].class, new ByteArraySerializer());
        delegates.put(Object.class, new JsonSerializer<>());

        return new DefaultKafkaProducerFactory<>(
                props,
                new StringSerializer(),
                new DelegatingByTypeSerializer(delegates, true));
    }

    @Bean
    KafkaTemplate<String, Object> ordersKafkaTemplate(
            ProducerFactory<String, Object> ordersProducerFactory) {
        return new KafkaTemplate<>(ordersProducerFactory);
    }
}
```

Đặt các method `@Bean` này trong một class có `@Configuration`. Serializer được chọn theo runtime type của value. Thứ tự map đặt `byte[].class` trước `Object.class` để dữ liệu thô được xử lý bằng byte serializer.

Nếu ứng dụng không cần gửi DTO từ template này, có thể dùng một producer factory riêng chỉ serialize byte[]. Trong bài lab, một template hỗ trợ cả hai kiểu giúp recoverer publish được payload gốc khi gặp lỗi deserialize.

## 6. Cấu hình DefaultErrorHandler và DLT recoverer

Tạo `DeadLetterPublishingRecoverer` dùng `KafkaTemplate` ở trên, rồi gắn nó vào `DefaultErrorHandler`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;
import com.example.orders.events.OrderCreated;

@Configuration
public class OrdersListenerConfiguration {

    @Bean
    DefaultErrorHandler ordersErrorHandler(
            KafkaTemplate<String, Object> ordersKafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(ordersKafkaTemplate);
        // Không retry lỗi deserialize; recover ngay sang DLT.
        return new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(0L, 0L));
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreated> ordersConsumerFactory,
            DefaultErrorHandler ordersErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(ordersConsumerFactory);
        factory.setCommonErrorHandler(ordersErrorHandler);
        return factory;
    }
}
```

`DeserializationException` được `DefaultErrorHandler` xem là lỗi fatal/not retryable theo phân loại mặc định trong các phiên bản Spring Kafka hiện đại. `FixedBackOff(0L, 0L)` cũng đặt số lần retry là 0, vì vậy record được chuyển tới recoverer ngay sau lần xử lý thất bại đầu tiên. Cách cấu hình này làm rõ mục tiêu bài lab: JSON sai không thể tự trở thành JSON đúng chỉ bằng cách gửi lại cùng payload.

Recoverer mặc định định tuyến `orders-json` sang `orders-json.DLT` và giữ partition tương ứng. Hãy tạo topic DLT trước với số partition bằng hoặc lớn hơn topic nguồn. Nếu đổi quy tắc đặt tên DLT, có thể cung cấp destination resolver riêng cho `DeadLetterPublishingRecoverer`.

## 7. Vì sao listener không nhận được record lỗi?

Với listener nhận `OrderCreated`, Spring Kafka phải deserialize value trước khi gọi phương thức listener. Nếu `JsonDeserializer` ném exception mà không có `ErrorHandlingDeserializer`, lỗi xảy ra ngay trong quá trình poll và container không có object nghiệp vụ hợp lệ để truyền vào listener.

Khi bọc bằng `ErrorHandlingDeserializer`:

1. Delegate `JsonDeserializer` cố chuyển JSON bytes thành `OrderCreated`.
2. Nếu thành công, object được chuyển cho listener.
3. Nếu thất bại, wrapper lưu exception cùng byte gốc trong headers của record và trả value null.
4. Container nhận diện header lỗi deserialize và chuyển exception đến `CommonErrorHandler`.
5. `DefaultErrorHandler` gọi recoverer; `DeadLetterPublishingRecoverer` khôi phục byte gốc từ thông tin lỗi và publish sang DLT.

Vì lỗi xảy ra trước listener, không nên đặt `try/catch` trong `onOrder()` để mong bắt được lỗi JSON. Listener không có cơ hội chạy khi deserialization thất bại.

## 8. Gửi một record hợp lệ và một record JSON lỗi

Sau khi ứng dụng chạy và listener container đã được khởi động, gửi record hợp lệ:

```java
OrderCreated valid = new OrderCreated(
        "event-100", "order-100", "customer-7");

ordersKafkaTemplate.send("orders-json", "order-100", valid);
```

Listener sẽ nhận `OrderCreated` và đưa vào queue quan sát. Tiếp theo, gửi payload sai cú pháp dưới dạng byte[]:

```java
import java.nio.charset.StandardCharsets;

byte[] invalidJson = "{\"eventId\":\"bad-1\",\"orderId\":"
        .getBytes(StandardCharsets.UTF_8);

ordersKafkaTemplate.send("orders-json", "bad-order-1", invalidJson);
```

Payload trên bị cắt giữa một property và không phải JSON hoàn chỉnh. Producer vẫn có thể gửi thành công vì producer chỉ serialize byte[]; nó không biết consumer mong đợi `OrderCreated` hay payload có hợp lệ theo JSON hay không.

Để quan sát lỗi một cách xác định, hãy chờ kết quả future của `send()` trong test hoặc ghi callback ở ứng dụng. Việc broker xác nhận publish chỉ chứng minh record đã được ghi theo cấu hình producer, không chứng minh consumer deserialize thành công.

## 9. Đọc record gốc từ DLT

Có thể dùng Kafka consumer riêng với `ByteArrayDeserializer` để đọc DLT. Ví dụ:

```java
import java.time.Duration;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.serialization.ByteArrayDeserializer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.test.utils.KafkaTestUtils;

Map<String, Object> dltProps = KafkaTestUtils.consumerProps(
        "orders-dlt-inspector", "false", embeddedKafka);
dltProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

try (Consumer<String, byte[]> dltConsumer =
        new DefaultKafkaConsumerFactory<String, byte[]>(
                dltProps,
                new StringDeserializer(),
                new ByteArrayDeserializer()).createConsumer()) {

    embeddedKafka.consumeFromAnEmbeddedTopic(
            dltConsumer, "orders-json.DLT");

    ConsumerRecord<String, byte[]> dltRecord =
            KafkaTestUtils.getSingleRecord(
                    dltConsumer,
                    "orders-json.DLT",
                    Duration.ofSeconds(10));

    System.out.println(new String(
            dltRecord.value(), StandardCharsets.UTF_8));
}
```

Đoạn code dùng `EmbeddedKafkaBroker` trong test; khi chạy broker thật, thay bằng bootstrap server và cấu hình consumer phù hợp. Consumer DLT dùng `ByteArrayDeserializer` vì mục tiêu là xem chính xác bytes gốc, không deserialize lại payload lỗi thành DTO.

Record DLT thường có các headers do `DeadLetterPublishingRecoverer` thêm, chẳng hạn topic/partition/offset gốc, exception class và exception message. Có thể kiểm tra các header qua `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, `KafkaHeaders.DLT_ORIGINAL_OFFSET`, `KafkaHeaders.DLT_EXCEPTION_FQCN` và `KafkaHeaders.DLT_EXCEPTION_MESSAGE` nếu phiên bản Spring Kafka đang dùng cung cấp các hằng số đó.

## 10. Kiểm thử tích hợp với Embedded Kafka

Một test có thể xác minh cả ba hành vi: record hợp lệ đến listener, JSON lỗi không đến listener và JSON lỗi xuất hiện ở DLT dưới dạng byte gốc.

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.serialization.ByteArrayDeserializer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import com.example.orders.config.OrdersConsumerConfiguration;
import com.example.orders.config.OrdersListenerConfiguration;
import com.example.orders.config.OrdersProducerConfiguration;
import com.example.orders.events.OrderCreated;
import com.example.orders.listener.OrderListener;

@SpringJUnitConfig(classes = {
        OrdersConsumerConfiguration.class,
        OrdersListenerConfiguration.class,
        OrdersProducerConfiguration.class,
        OrderListener.class
})
@EmbeddedKafka(
        topics = {"orders-json", "orders-json.DLT"},
        partitions = 1,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class DeserializationFailureTest {

    @Autowired
    KafkaTemplate<String, Object> ordersKafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Autowired
    OrderListener orderListener;

    @Test
    void malformedJsonIsRecoveredToDltAsOriginalBytes() throws Exception {
        OrderCreated valid = new OrderCreated(
                "event-100", "order-100", "customer-7");
        ordersKafkaTemplate.send("orders-json", "order-100", valid)
                .get(10, TimeUnit.SECONDS);

        OrderCreated received = orderListener.received()
                .poll(10, TimeUnit.SECONDS);
        assertNotNull(received);
        assertEquals(valid, received);

        byte[] invalidJson = "{\"orderId\":"
                .getBytes(StandardCharsets.UTF_8);

        Map<String, Object> props = KafkaTestUtils.consumerProps(
                "orders-dlt-test", "false", embeddedKafka);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        try (Consumer<String, byte[]> dltConsumer =
                new DefaultKafkaConsumerFactory<String, byte[]>(
                        props,
                        new StringDeserializer(),
                        new ByteArrayDeserializer()).createConsumer()) {

            embeddedKafka.consumeFromAnEmbeddedTopic(
                    dltConsumer, "orders-json.DLT");

            ordersKafkaTemplate.send(
                    "orders-json", "bad-1", invalidJson)
                    .get(10, TimeUnit.SECONDS);

            ConsumerRecord<String, byte[]> dltRecord =
                    KafkaTestUtils.getSingleRecord(
                            dltConsumer,
                            "orders-json.DLT",
                            Duration.ofSeconds(10));

            assertNotNull(dltRecord);
            assertEquals("bad-1", dltRecord.key());
            assertArrayEquals(invalidJson, dltRecord.value());
            assertEquals("orders-json", new String(
                    dltRecord.headers()
                            .lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC).value(),
                    StandardCharsets.UTF_8));
            assertNotNull(dltRecord.headers()
                    .lastHeader(KafkaHeaders.DLT_EXCEPTION_FQCN));
            assertNull(orderListener.received().poll(100, TimeUnit.MILLISECONDS),
                    "Record lỗi deserialize không được chuyển đến listener");
        }
    }
}
```

Đây là skeleton kiểm thử; gộp các bean producer/consumer vào class `@Configuration` thực tế của dự án và bảo đảm `EmbeddedKafkaBroker` được inject bởi test context. Nếu dùng `@SpringBootTest`, đặt `bootstrapServersProperty` để Spring Boot trỏ tới broker nhúng, tránh kết nối nhầm broker local.

Trong test thực tế, nên có thêm một test gửi `OrderCreated` hợp lệ và chờ `orderListener.received()` để xác nhận listener hoạt động bình thường. Có thể dùng `BlockingQueue.poll(timeout)` thay cho `Thread.sleep()` để đồng bộ với listener thread.

Tên header DLT có thể được truy cập bằng các hằng số `KafkaHeaders` thay vì chuỗi literal. Khi kiểm tra header, xác minh đúng tên hằng số trong version Spring Kafka của dự án. Mục tiêu chính của test là xác nhận raw bytes trong DLT giống payload đã gửi và record có metadata nguồn.

## 11. Phân biệt deserialize failure với validation failure

Hai loại lỗi xuất hiện ở hai thời điểm khác nhau:

| Loại lỗi | Thời điểm | Listener có được gọi? | Cách xử lý |
| --- | --- | --- | --- |
| Deserialize failure | Trong quá trình consumer poll/convert byte thành object | Không, container xử lý exception từ `ErrorHandlingDeserializer` | `ErrorHandlingDeserializer` + `DefaultErrorHandler` + recoverer |
| Validation/business failure | Sau khi payload đã thành DTO và listener/service chạy | Có | Validation trong service, ném exception, retry hoặc DLT theo chính sách |

Ví dụ JSON hợp lệ nhưng `orderId` rỗng có thể deserialize thành `OrderCreated`; đây là lỗi validation chứ không phải deserialize. Listener được gọi và service phải quyết định cách xử lý. Ngược lại, JSON sai dấu ngoặc hoặc trường số không thể chuyển thành kiểu mong đợi sẽ lỗi trước listener.

Không dùng `ErrorHandlingDeserializer` để thay thế validation nghiệp vụ. Deserialize thành công chỉ chứng minh payload có thể chuyển thành kiểu Java, không chứng minh nội dung hợp lệ.

## 12. Retry hay đưa thẳng vào DLT?

JSON sai cú pháp thường là lỗi không thể tự phục hồi bằng cách gửi lại cùng bytes. Vì vậy, Spring Kafka phân loại `DeserializationException` là fatal/not retryable theo mặc định trong các phiên bản hiện đại. Recoverer có thể được gọi ngay mà không cần chờ backoff.

Nếu lỗi có khả năng tạm thời (ví dụ schema registry tạm mất kết nối trong một thiết kế deserializer cụ thể), cần phân biệt exception kỹ thuật đó với lỗi payload thực sự. Không nên đánh dấu mọi exception deserialize là retryable hoặc mọi lỗi consumer là không retryable mà không xem xét nguyên nhân. Cấu hình classifier, BackOff và recoverer theo chính sách của hệ thống.

Khi gửi DLT thất bại, recovery chưa hoàn tất. Không bắt rồi bỏ qua exception từ `DeadLetterPublishingRecoverer`; cần để error handler nhận biết lỗi recovery, giám sát và áp dụng chính sách phù hợp. DLT producer phải có quyền ghi, topic đích tồn tại và serializer phải hỗ trợ byte[] gốc.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Listener không nhận record JSON sai | Đây là hành vi đúng vì deserialize thất bại trước listener | Kiểm tra DLT và error handler thay vì chờ listener |
| Consumer dừng khi gặp JSON lỗi | Dùng trực tiếp `JsonDeserializer`, không có `ErrorHandlingDeserializer` | Bọc delegate bằng `ErrorHandlingDeserializer` |
| DLT nhận value null hoặc không giữ byte gốc | DLT template không serialize được byte[] hoặc raw data header không được phục hồi | Dùng `DelegatingByTypeSerializer` hỗ trợ byte[] và object |
| Publish DLT thất bại do partition | DLT ít partition hơn topic nguồn | Tạo DLT có số partition tương ứng hoặc dùng resolver phù hợp |
| `ClassNotFoundException` | Type header trỏ tới class không có ở consumer | Dùng default type/type mapping và kiểm soát trusted packages |
| JSON lỗi bị retry nhiều lần | Classifier/backoff không đúng hoặc version có hành vi khác | Kiểm tra exception thực tế và phân loại fatal/not retryable |
| DLT consumer cũng deserialize lỗi | DLT consumer đang dùng `JsonDeserializer` cho payload lỗi | Dùng `ByteArrayDeserializer` để đọc raw bytes |
| Không thấy record ở DLT | Listener container chưa chạy, sai topic/group hoặc recoverer chưa được gắn | Kiểm tra factory, error handler, group và topic đích |

## 14. Checklist hoàn thành bài thực hành

- [ ] Topic nguồn và DLT đã tồn tại, số partition tương thích.
- [ ] Consumer dùng `ErrorHandlingDeserializer` bọc `JsonDeserializer`.
- [ ] Default type, trusted packages và type-header strategy được cấu hình rõ.
- [ ] Listener nhận được JSON hợp lệ thành DTO.
- [ ] Payload JSON lỗi được gửi bằng raw byte[] để tái hiện lỗi thật.
- [ ] `DefaultErrorHandler` được gắn vào listener container factory.
- [ ] `DeadLetterPublishingRecoverer` dùng producer có serializer hỗ trợ byte[].
- [ ] Record lỗi không đi vào listener và được chuyển sang DLT.
- [ ] DLT consumer dùng `ByteArrayDeserializer` để đọc payload gốc.
- [ ] Đã kiểm tra key, raw value và DLT source/error headers.
- [ ] Đã kiểm thử trường hợp publish DLT thất bại và giám sát recovery.

Bài thực hành hoàn tất khi một record hợp lệ được deserialize và đến listener, còn record JSON sai được container nhận diện trước listener, chuyển qua `DefaultErrorHandler` và lưu vào DLT với payload byte gốc cùng metadata lỗi. Cách kiểm tra này xác nhận ứng dụng có thể cô lập dữ liệu hỏng mà vẫn giữ bằng chứng để điều tra và xử lý lại sau này.

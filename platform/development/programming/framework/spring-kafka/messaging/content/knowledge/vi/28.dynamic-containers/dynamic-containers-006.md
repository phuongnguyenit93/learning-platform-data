# Cấu hình nhiều container factory

Trong Spring Kafka, `ConcurrentKafkaListenerContainerFactory` là nơi cấu hình cách các listener container được tạo ra: consumer factory nào được dùng, concurrency bao nhiêu, xử lý từng record hay theo batch, acknowledgment mode, error handler và transaction manager. Một ứng dụng có thể khai báo nhiều container factory để phục vụ các luồng Kafka có yêu cầu khác nhau.

Ví dụ, service có thể nhận `OrderCreated` bằng record listener với concurrency cao, đồng thời nhận `AuditEvent` theo batch với concurrency thấp hơn. Hai listener có thể cần deserializer, consumer group, `AckMode` và error handling khác nhau. Ta tạo hai factory có tên riêng rồi chọn factory tương ứng trong từng `@KafkaListener`.

Container factory là cấu hình để tạo listener container; nó không phải consumer và cũng không phải container đang chạy. Khi Spring xử lý một `@KafkaListener`, factory được chọn sẽ tạo container endpoint với cấu hình tương ứng.

## 1. Vì sao cần nhiều container factory?

Một ứng dụng Kafka thường có nhiều luồng dữ liệu với đặc tính khác nhau:

- `orders.events`: JSON event cần deserialize thành `OrderCreated`, xử lý từng record và commit sau mỗi record.
- `audit.events`: nhiều audit record có thể gom thành batch để giảm overhead khi ghi database.
- `payments.commands`: yêu cầu xử lý có retry/error handler riêng và concurrency được giới hạn để bảo vệ hệ thống thanh toán.
- `inventory.events`: cần consumer group và deserializer khác với các luồng còn lại.

Nếu mọi listener dùng chung một factory, các thuộc tính như consumer factory, deserializer, concurrency, batch mode và error handler có thể không phù hợp với tất cả luồng. Nhiều factory giúp đóng gói cấu hình theo mục đích và thể hiện rõ listener nào dùng chính sách nào.

| Nhu cầu | Cấu hình có thể tách theo factory |
| --- | --- |
| Payload khác nhau | `ConsumerFactory` và deserializer riêng |
| Tốc độ xử lý khác nhau | `concurrency`, `pollTimeout`, `max.poll.records` |
| Record listener và batch listener | `setBatchListener(true/false)` |
| Cách commit offset khác nhau | `AckMode` |
| Retry/DLT khác nhau | `CommonErrorHandler` riêng |
| Transaction khác nhau | Transaction manager hoặc container properties phù hợp |
| Message conversion khác nhau | Record/batch message converter |

Không nhất thiết phải tạo factory mới cho mọi listener. Nếu hai listener có cùng consumer, deserializer và container semantics, chúng có thể dùng chung một factory. Tạo factory riêng khi có khác biệt thực sự cần quản lý.

## 2. Phân biệt các thành phần

| Thành phần | Trách nhiệm |
| --- | --- |
| `ConsumerFactory<K,V>` | Tạo Kafka consumer với cấu hình, key/value deserializer và các thuộc tính client |
| `ConcurrentKafkaListenerContainerFactory<K,V>` | Tạo listener container và áp dụng concurrency, AckMode, error handler, transaction, converter |
| `ConcurrentMessageListenerContainer<K,V>` | Container thực tế được factory tạo; quản lý một hoặc nhiều child consumer container |
| `@KafkaListener` | Khai báo endpoint nhận record và chọn container factory |
| `KafkaTemplate<K,V>` / `ProducerFactory<K,V>` | Gửi record; không phải cấu hình consumer listener container |

Một `ConcurrentKafkaListenerContainerFactory` có thể dùng một `ConsumerFactory` được chia sẻ bởi nhiều endpoint. Ngược lại, nhiều factory cũng có thể dùng cùng một `ConsumerFactory` nếu khác biệt chỉ nằm ở container-level settings như concurrency hoặc AckMode.

Ví dụ:

```text
ordersKafkaListenerContainerFactory
    └── ordersConsumerFactory
          └── String key + OrderCreated JSON value

auditBatchKafkaListenerContainerFactory
    └── auditConsumerFactory
          └── String key + AuditEvent JSON value

@KafkaListener(containerFactory = "ordersKafkaListenerContainerFactory")
@KafkaListener(containerFactory = "auditBatchKafkaListenerContainerFactory")
```

## 3. Factory mặc định và factory được chọn tường minh

Nếu `@KafkaListener` không khai báo thuộc tính `containerFactory`, Spring Kafka tìm factory mặc định theo tên `kafkaListenerContainerFactory`.

Ví dụ khai báo factory mặc định:

```java
@Bean(name = "kafkaListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, Object>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, Object> consumerFactory) {
    var factory = new ConcurrentKafkaListenerContainerFactory<String, Object>();
    factory.setConsumerFactory(consumerFactory);
    return factory;
}
```

Các factory bổ sung có thể dùng tên riêng:

```java
@Bean(name = "ordersKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersKafkaListenerContainerFactory(...) { ... }

@Bean(name = "paymentsKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, PaymentRequested>
        paymentsKafkaListenerContainerFactory(...) { ... }
```

Chọn factory trong listener bằng thuộc tính `containerFactory`:

```java
@KafkaListener(
        topics = "orders.events",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory"
)
public void onOrderCreated(OrderCreated event) {
    orderService.handle(event);
}
```

Tên trong `containerFactory` phải khớp chính xác với tên bean. Nếu tên bean không tồn tại hoặc factory không tương thích với kiểu key/value/deserializer, listener endpoint có thể không khởi tạo được hoặc lỗi khi nhận record.

Spring Boot thường tự cấu hình factory mặc định khi ứng dụng chưa cung cấp bean tương ứng. Nếu chỉ thêm các factory custom với tên riêng, factory mặc định của Boot vẫn có thể tồn tại. Khi muốn thay thế factory mặc định, khai báo bean đúng tên `kafkaListenerContainerFactory` và cấu hình đầy đủ cho ứng dụng.

`@Primary` giúp Spring chọn một bean khi autowire theo type có nhiều ứng viên, nhưng không thay thế quy ước tên factory mặc định mà `@KafkaListener` sử dụng. Nếu muốn endpoint dùng factory custom, khai báo `containerFactory` tường minh.

Trong cấu hình Spring Framework không dùng Spring Boot auto-configuration, cần bật xử lý annotation listener bằng `@EnableKafka` trên một class `@Configuration`. Với Spring Boot Kafka auto-configuration, listener infrastructure thường đã được bật; tránh cấu hình lặp nếu ứng dụng đã có cơ chế này.

## 4. Tạo nhiều ConsumerFactory cho các payload khác nhau

Mỗi `ConsumerFactory` định nghĩa cách tạo Kafka consumer. Khi các topic chứa payload khác nhau, ta có thể dùng deserializer được định kiểu cho từng DTO.

Ví dụ có hai DTO:

```java
package com.example.messaging.event;

import java.math.BigDecimal;

public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total
) {}
```

```java
package com.example.messaging.event;

public record AuditEvent(
        String eventId,
        String actor,
        String action,
        long occurredAt
) {}
```

Có thể cấu hình hai `ConsumerFactory` với JSON deserializer target type khác nhau:

```java
package com.example.messaging.config;

import java.util.HashMap;
import java.util.Map;
import com.example.messaging.event.AuditEvent;
import com.example.messaging.event.OrderCreated;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;

@Configuration
public class KafkaConsumerFactories {

    private Map<String, Object> baseConsumerProperties(
            String bootstrapServers,
            String groupId
    ) {
        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        return props;
    }

    @Bean
    public ConsumerFactory<String, OrderCreated> ordersConsumerFactory(
            @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers
    ) {
        return new DefaultKafkaConsumerFactory<>(
                baseConsumerProperties(bootstrapServers, "orders-service"),
                new StringDeserializer(),
                new JsonDeserializer<>(OrderCreated.class)
        );
    }

    @Bean
    public ConsumerFactory<String, AuditEvent> auditConsumerFactory(
            @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers
    ) {
        return new DefaultKafkaConsumerFactory<>(
                baseConsumerProperties(bootstrapServers, "audit-service"),
                new StringDeserializer(),
                new JsonDeserializer<>(AuditEvent.class)
        );
    }
}
```

Hai factory dùng cùng broker và cùng key deserializer nhưng khác group ID và target type của value. Trong project thực tế, có thể đưa các thuộc tính group ID, offset reset, security và fetch settings vào `application.yml`/configuration properties thay vì hardcode như ví dụ.

`JsonDeserializer` có thể dùng type headers để chọn class nếu được cấu hình như vậy. Nếu muốn mỗi consumer factory luôn deserialize thành một DTO cố định, cấu hình target type và chính sách sử dụng type headers nhất quán. Chỉ tin cậy package chứa contract cần thiết; không mở rộng trusted packages tùy tiện.

## 5. Tạo nhiều ConcurrentKafkaListenerContainerFactory

Sau khi có các `ConsumerFactory`, tạo container factory tương ứng:

```java
package com.example.messaging.config;

import com.example.messaging.event.AuditEvent;
import com.example.messaging.event.OrderCreated;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class KafkaListenerContainerFactories {

    @Bean(name = "ordersKafkaListenerContainerFactory")
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersKafkaListenerContainerFactory(
                    @Qualifier("ordersConsumerFactory")
                    ConsumerFactory<String, OrderCreated> consumerFactory
            ) {
        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD
        );
        return factory;
    }

    @Bean(name = "auditBatchKafkaListenerContainerFactory")
    public ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
            auditBatchKafkaListenerContainerFactory(
                    @Qualifier("auditConsumerFactory")
                    ConsumerFactory<String, AuditEvent> consumerFactory
            ) {
        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, AuditEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(2);
        factory.setBatchListener(true);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.BATCH
        );
        return factory;
    }
}
```

Ở đây:

- Factory `ordersKafkaListenerContainerFactory` tạo record listener với ba consumer trên mỗi application instance và commit theo `RECORD`.
- Factory `auditBatchKafkaListenerContainerFactory` tạo batch listener với hai consumer trên mỗi instance và commit theo `BATCH`.
- Mỗi factory dùng `ConsumerFactory` đã định kiểu tương ứng.
- `@Qualifier` giúp Spring inject đúng bean khi có nhiều bean cùng interface `ConsumerFactory`.

Đây là ví dụ cấu hình hai listener có semantics khác nhau. Số consumer thực tế của mỗi group còn phụ thuộc số replica ứng dụng và số partition topic. Tăng concurrency vượt số partition không tạo thêm partition assignment hữu ích.

## 6. Chọn factory trong @KafkaListener

Listener Order chọn factory record:

```java
package com.example.messaging.consumer;

import com.example.messaging.event.OrderCreated;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "orders-service",
            containerFactory = "ordersKafkaListenerContainerFactory"
    )
    public void onOrderCreated(OrderCreated event) {
        // Xử lý một record OrderCreated.
    }
}
```

Listener Audit chọn factory batch:

```java
package com.example.messaging.consumer;

import java.util.List;
import com.example.messaging.event.AuditEvent;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class AuditListener {

    @KafkaListener(
            id = "auditListener",
            topics = "audit.events",
            groupId = "audit-service",
            containerFactory = "auditBatchKafkaListenerContainerFactory"
    )
    public void onAuditEvents(List<AuditEvent> events) {
        // Xử lý một batch AuditEvent.
    }
}
```

Method signature phải phù hợp với factory. Record listener thường nhận một payload hoặc `ConsumerRecord`; batch listener có thể nhận `List<Payload>`, `List<ConsumerRecord<K,V>>` hoặc các dạng batch được Spring Kafka hỗ trợ. Không chọn batch factory rồi giữ method signature chỉ nhận một DTO như record listener.

## 7. Record listener và batch listener

`setBatchListener(true)` làm container chuyển danh sách record của một lần poll vào listener method. Điều này có thể giảm overhead và cho phép xử lý dữ liệu theo lô, nhưng thay đổi ranh giới lỗi và commit.

| Đặc điểm | Record listener | Batch listener |
| --- | --- | --- |
| Tham số phổ biến | Một payload/record | Một danh sách payload/record |
| Đơn vị xử lý | Từng record | Một batch từ poll |
| AckMode thường dùng | `RECORD` hoặc `BATCH` tùy yêu cầu | `BATCH` hoặc manual theo thiết kế |
| Khi một record lỗi | Có thể retry/recover riêng record | Cần xác định record lỗi trong batch hoặc retry cả batch |
| Throughput | Đơn giản, xử lý từng record | Có thể tối ưu bulk I/O |
| Ordering | Dễ reasoning theo từng record | Cần cẩn thận khi xử lý song song bên trong batch |

Batch listener phù hợp với bulk insert, bulk update hoặc API hỗ trợ danh sách. Nếu xử lý một batch theo nhiều thread rồi trả về trước khi mọi tác vụ hoàn tất, offset có thể được xác nhận sớm; phải quản lý acknowledgment và completion rõ ràng.

## 8. Mỗi factory có thể có concurrency riêng

`setConcurrency(n)` đặt số consumer child container mà mỗi listener container được tạo bởi factory sử dụng. Vì vậy, hai factory có thể đặt concurrency khác nhau:

| Factory | Concurrency mỗi instance | Replica | Tổng consumer member |
| --- | ---: | ---: | ---: |
| Orders | 3 | 2 | 6 |
| Audit batch | 2 | 2 | 4 |

Con số tổng là `replica × concurrency` cho mỗi listener endpoint. Một group chỉ có thể sử dụng song song tối đa số partition được assign; nếu consumer member vượt partition count, một số member sẽ không có partition.

Có thể ghi đè concurrency ở từng `@KafkaListener` bằng thuộc tính `concurrency` nếu cần khác mặc định factory:

```java
@KafkaListener(
        topics = "orders.priority",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory",
        concurrency = "5"
)
public void onPriorityOrder(OrderCreated event) {
    // Listener này dùng concurrency riêng.
}
```

Không nên tăng concurrency chỉ vì có thể. Cần xét partition count, CPU, downstream capacity, listener latency và consumer lag.

## 9. AckMode và commit policy riêng cho từng luồng

Factory có thể cấu hình `AckMode` qua `ContainerProperties`:

```java
factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.RECORD
);
```

Các mode thường gặp:

| AckMode | Ý nghĩa khái quát |
| --- | --- |
| `RECORD` | Commit sau khi từng record listener xử lý thành công |
| `BATCH` | Commit sau khi các record trong một lần poll được xử lý thành công |
| `TIME` | Commit khi đạt ngưỡng thời gian tại điểm kiểm tra của container |
| `COUNT` | Commit khi đạt số record đã xử lý |
| `COUNT_TIME` | Kết hợp ngưỡng số lượng và thời gian |
| `MANUAL` | Listener gọi `Acknowledgment.acknowledge()`; container commit theo semantics của mode |
| `MANUAL_IMMEDIATE` | Yêu cầu commit ngay khi acknowledge trên consumer thread |

`enable.auto.commit=false` thường được dùng để Spring Kafka container quản lý offset. Không bật Kafka auto commit đồng thời với thiết kế manual/container acknowledgment nếu chưa hiểu rõ tương tác, vì có thể commit trước khi nghiệp vụ hoàn tất.

Nếu mỗi listener có yêu cầu commit khác nhau, đặt AckMode trên factory riêng. Cần kiểm thử tình huống listener lỗi, retry và process restart để xác nhận record nào có thể được giao lại.

## 10. Gắn CommonErrorHandler riêng cho từng factory

Các luồng có thể có chính sách lỗi khác nhau. Ví dụ Orders cần retry nhanh vài lần rồi DLT; Audit có thể dùng backoff dài hơn hoặc recoverer khác.

Factory hỗ trợ cấu hình `CommonErrorHandler`:

```java
factory.setCommonErrorHandler(ordersErrorHandler);
```

Ví dụ tạo hai handler độc lập:

```java
@Bean
public DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer ordersRecoverer
) {
    return new DefaultErrorHandler(
            ordersRecoverer,
            new FixedBackOff(500L, 2L)
    );
}

@Bean
public DefaultErrorHandler auditErrorHandler(
        DeadLetterPublishingRecoverer auditRecoverer
) {
    return new DefaultErrorHandler(
            auditRecoverer,
            new FixedBackOff(2_000L, 5L)
    );
}
```

Imports cần có `DefaultErrorHandler`, `DeadLetterPublishingRecoverer` và `FixedBackOff`; các recoverer có thể route sang DLT tương ứng. Gắn handler đúng factory:

```java
ordersFactory.setCommonErrorHandler(ordersErrorHandler);
auditFactory.setCommonErrorHandler(auditErrorHandler);
```

Khi dùng batch listener, cần chọn cách biểu diễn record lỗi phù hợp, ví dụ `BatchListenerFailedException` để chỉ ra index record lỗi. Nếu không xác định được record lỗi, error handler có thể phải retry/recover toàn bộ batch theo semantics tương ứng. Hãy kiểm tra behavior của phiên bản Spring Kafka và loại listener đang dùng.

Không nên dùng cùng một `DeadLetterPublishingRecoverer` nếu hai luồng cần destination, serializer hoặc ACL khác nhau mà recoverer đó không xử lý được. Error handler phải tương thích với record type và container mode.

## 11. Cấu hình transaction riêng cho factory

Nếu một listener cần Kafka transaction, transaction manager có thể được gắn vào container properties/factory theo cấu hình Spring Kafka. Những listener khác vẫn có thể dùng factory non-transactional.

Với transaction Kafka, cần cấu hình producer factory có transaction ID prefix và `KafkaTransactionManager` phù hợp. Container sẽ tham gia transaction theo semantics đã cấu hình; offset và output Kafka có thể được phối hợp trong transaction Kafka.

Không nên dùng cùng transaction manager một cách máy móc cho mọi factory. Hãy phân biệt:

- Listener chỉ consume và xử lý database.
- Listener consume rồi publish Kafka output cần transaction Kafka.
- Listener cập nhật database và publish Kafka cần outbox hoặc cơ chế phối hợp phù hợp.

Kafka transaction không tự bao gồm JDBC/HTTP side effect. Nếu listener cập nhật database rồi Kafka transaction rollback, database có thể vẫn đã commit trừ khi ứng dụng phối hợp transaction riêng.

## 12. Cấu hình dùng chung và cấu hình riêng

Không phải mọi thuộc tính đều cần lặp lại. Có thể tạo hàm chung cho cấu hình consumer cơ bản rồi override các thuộc tính riêng.

Ví dụ `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        "[security.protocol]": ${KAFKA_SECURITY_PROTOCOL:PLAINTEXT}

app:
  kafka:
    orders:
      group-id: orders-service
      concurrency: 3
    audit:
      group-id: audit-service
      concurrency: 2
```

Có thể bind phần `app.kafka` vào `@ConfigurationProperties` để quản lý cấu hình có kiểu. Mỗi `ConsumerFactory` sử dụng group ID và các thuộc tính riêng; mỗi container factory sử dụng concurrency/AckMode riêng.

Khi dùng Spring Boot auto-configured `ConsumerFactory`, các property chung trong `spring.kafka.consumer` có thể được chia sẻ. Tuy nhiên, nếu cần deserializer khác nhau theo DTO, thường phải tạo các `ConsumerFactory` riêng hoặc cấu hình delegate deserializer có khả năng xử lý nhiều type.

Không nên copy nguyên cấu hình bảo mật hoặc tuning vào nhiều nơi nếu chúng giống nhau. Tạo hàm tạo property chung hoặc configuration properties để tránh drift giữa các factory.

## 13. Một ConsumerFactory dùng chung cho nhiều container factory

Nếu các listener có cùng broker, group, deserializer và consumer client properties, có thể chia sẻ một `ConsumerFactory` nhưng tạo nhiều container factory để khác concurrency hoặc AckMode:

```java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersFastFactory(
                @Qualifier("ordersConsumerFactory")
                ConsumerFactory<String, OrderCreated> consumerFactory
        ) {
    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(6);
    factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}

@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersLowConcurrencyFactory(
                @Qualifier("ordersConsumerFactory")
                ConsumerFactory<String, OrderCreated> consumerFactory
        ) {
    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(1);
    factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.BATCH);
    return factory;
}
```

Hai factory dùng chung consumer properties nhưng tạo container có concurrency và acknowledgment khác nhau. Nếu listener dùng cùng `group.id` và cùng topic, chúng tham gia cùng group và chia partition cho nhau. Nếu muốn nhận toàn bộ bản sao event độc lập, cần group ID riêng.

Hãy tránh dùng cùng một `ConsumerFactory` nếu các listener thực sự cần group ID, deserializer hoặc security identity khác nhau. Những thuộc tính consumer-level phải nằm ở `ConsumerFactory`, không thể tách chỉ bằng container factory.

## 14. Message converter và kiểu payload

Ngoài deserializer, container factory có thể cấu hình message converter để chuyển `ConsumerRecord`/message thành tham số listener. Cần phân biệt:

- Kafka deserializer chuyển byte array thành key/value Java.
- Spring message converter chuyển payload/header thành dạng method argument.
- Listener method signature quyết định kiểu tham số mà endpoint nhận.

Ví dụ factory có thể đặt record message converter:

```java
factory.setRecordMessageConverter(recordMessageConverter);
```

Batch listener có thể cần batch message converter phù hợp nếu muốn chuyển toàn bộ batch sang `List<SomeType>` hoặc Spring `Message`. Không cấu hình converter của record cho batch rồi giả định semantics giống nhau; hãy kiểm tra loại converter và chữ ký listener.

Nếu dùng JSON deserializer target type trực tiếp, listener thường nhận DTO đã deserialize. Nếu dùng `StringDeserializer` và converter JSON ở tầng Spring, hãy thống nhất một chiến lược duy nhất để tránh deserialize hai lần hoặc nhận `String` trong khi listener mong DTO.

## 15. Container factory không phải dynamic container

Nhiều factory và dynamic container là hai khái niệm liên quan nhưng khác nhau:

- Nhiều factory định nghĩa nhiều bộ cấu hình để tạo listener container.
- Dynamic container là container được tạo, đăng ký, start/stop trong runtime theo nhu cầu ứng dụng.

`@KafkaListener` thường được xử lý lúc application context khởi động. Nếu cần tạo listener endpoint hoặc container theo tenant/topic xuất hiện lúc runtime, có thể dùng `KafkaListenerEndpointRegistry` hoặc `ConcurrentKafkaListenerContainerFactory.createContainer(...)` và tự quản lý lifecycle.

Ví dụ tạo container thủ công từ factory:

```java
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.MessageListener;

ConcurrentMessageListenerContainer<String, OrderCreated> container =
        ordersKafkaListenerContainerFactory.createContainer("orders.tenant-a");

container.getContainerProperties().setGroupId("orders-tenant-a");
container.setupMessageListener((MessageListener<String, OrderCreated>) record -> {
    orderService.handleTenant("tenant-a", record.value());
});

container.start();
```

Container tạo thủ công cần được giữ reference và dừng/đóng đúng lifecycle khi không còn sử dụng. Không tạo container mới cho mỗi request HTTP; điều đó có thể tạo quá nhiều consumer và group membership. Nên quản lý tập container theo vòng đời tenant hoặc topic và có giới hạn tài nguyên.

Nếu chỉ cần listener cố định với cấu hình khác nhau, khai báo nhiều `@KafkaListener` và chọn factory thường đơn giản hơn tự tạo dynamic container.

## 16. Đặt tên và tổ chức cấu hình

Tên bean nên thể hiện mục đích và kiểu xử lý, ví dụ:

| Tên bean | Mục đích |
| --- | --- |
| `kafkaListenerContainerFactory` | Factory mặc định |
| `ordersKafkaListenerContainerFactory` | Record listener cho Order |
| `auditBatchKafkaListenerContainerFactory` | Batch listener cho Audit |
| `paymentsKafkaListenerContainerFactory` | Listener thanh toán với error policy riêng |
| `ordersConsumerFactory` | Consumer factory của Order |
| `auditConsumerFactory` | Consumer factory của Audit |

Có thể tách class cấu hình theo domain (`OrdersKafkaConfiguration`, `AuditKafkaConfiguration`) khi số factory tăng. Nếu mọi cấu hình ở một class quá lớn, việc thay đổi một listener có thể ảnh hưởng nhầm luồng khác.

Nên dùng `@Qualifier` khi inject nhiều bean cùng interface. Đặt tên rõ ràng cho `ConsumerFactory`, `CommonErrorHandler`, `KafkaTemplate` và container factory để tránh phụ thuộc vào thứ tự hoặc kiểu generic mà IDE khó suy luận.

## 17. Kiểm tra cấu hình factory thực tế

Khi ứng dụng chạy, hãy xác minh listener dùng đúng factory:

- Kiểm tra `containerFactory` trong từng `@KafkaListener`.
- Kiểm tra tên bean được đăng ký trong application context.
- Xem log khởi tạo container và consumer client ID.
- Xác minh group ID, key/value deserializer và assignment.
- Kiểm tra concurrency qua số consumer member của group.
- Kiểm tra AckMode, error handler và transaction manager theo factory.

Có thể xem group bằng Kafka CLI:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service
```

Lệnh này cho biết consumer member, topic/partition, offset và lag. Nó không hiển thị trực tiếp toàn bộ cấu hình Spring factory, nên cần kết hợp log ứng dụng hoặc actuator/metrics để xác minh concurrency, processing time và error handling.

## 18. Kiểm thử nhiều container factory

Integration test nên xác nhận từng listener thực sự dùng đúng factory và nhận đúng kiểu payload.

Một kịch bản với `@EmbeddedKafka` hoặc Testcontainers:

1. Tạo `orders.events` và `audit.events` với partition phù hợp.
2. Khởi động context có cả `ordersKafkaListenerContainerFactory` và `auditBatchKafkaListenerContainerFactory`.
3. Gửi `OrderCreated` vào topic Orders và xác minh record listener nhận một DTO.
4. Gửi nhiều `AuditEvent` vào topic Audit và xác minh batch listener nhận danh sách.
5. Kiểm tra group ID và partition assignment của từng listener.
6. Xác minh concurrency khác nhau giữa hai factory.
7. Làm một listener ném exception và kiểm tra error handler đúng factory được gọi.
8. Kiểm tra AckMode/committed offset sau thành công và thất bại.
9. Nếu có transaction, kiểm tra rollback/commit trên factory tương ứng.
10. Kiểm tra ứng dụng vẫn có factory mặc định cho listener không khai báo `containerFactory` nếu thiết kế cần.

Không chỉ kiểm tra bean tồn tại. Cần xác minh endpoint đã đăng ký, container đã start và message đi qua đúng deserializer/handler. Dùng `CountDownLatch`, `BlockingQueue` hoặc assertion có timeout thay vì `Thread.sleep()` cố định.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Listener không khởi động | `containerFactory` trỏ đến tên bean không tồn tại | Kiểm tra bean name và spelling |
| Listener nhận `LinkedHashMap` thay vì DTO | Deserializer/type header không được cấu hình theo target type mong muốn | Kiểm tra `JsonDeserializer`, type mapping và trusted packages |
| Listener nhận sai kiểu payload | Chọn nhầm factory hoặc ConsumerFactory | Kiểm tra `containerFactory` và `@Qualifier` |
| Nhiều ConsumerFactory gây lỗi inject | Nhiều bean cùng interface nhưng không phân biệt qualifier | Dùng `@Qualifier` rõ ràng |
| Batch listener nhận một record thay vì List | Factory chưa bật `setBatchListener(true)` | Dùng đúng batch factory và method signature |
| Record listener nhận kiểu không mong muốn | Dùng batch factory cho endpoint record hoặc ngược lại | Đồng bộ factory mode với listener signature |
| Concurrency không như kỳ vọng | Annotation override hoặc số partition giới hạn assignment | Kiểm tra factory, endpoint và group assignment |
| Hai listener chia message ngoài ý muốn | Dùng cùng group ID và cùng topic | Dùng group ID riêng nếu cần fan-out độc lập |
| Error handler không được gọi | Gắn handler vào factory khác với factory listener đang dùng | Kiểm tra bean factory của endpoint |
| Offset commit không đúng mong muốn | AckMode/auto commit hoặc manual acknowledgment không phù hợp | Kiểm tra container properties và test crash/retry |
| Transaction không có hiệu lực | Factory không gắn đúng transaction manager hoặc producer factory chưa transactional | Kiểm tra transaction config theo endpoint |
| Tạo quá nhiều consumer | Nhiều factory/endpoint tạo concurrency cao trên nhiều replica | Tính tổng consumer và partition trước khi scale |

## 20. Checklist cấu hình nhiều factory

Trước khi triển khai, hãy xác nhận:

1. Có một factory mặc định tên `kafkaListenerContainerFactory` nếu listener nào cần dùng mặc định.
2. Mỗi custom factory có tên bean duy nhất, dễ hiểu.
3. Mỗi `@KafkaListener` chọn đúng `containerFactory`.
4. `ConsumerFactory` có group ID, deserializer và security properties phù hợp.
5. Dùng `@Qualifier` khi inject nhiều bean cùng interface.
6. Record/batch mode khớp method signature.
7. Concurrency được tính theo partition count và số replica.
8. AckMode phù hợp với ranh giới xử lý và retry.
9. Error handler/recoverer được gắn vào đúng factory.
10. Transaction manager chỉ được cấu hình cho listener cần transaction.
11. Message converter phù hợp với record/batch payload.
12. Factory dùng chung chỉ khi consumer-level properties thực sự tương thích.
13. Dynamic container được quản lý lifecycle riêng nếu tạo trong runtime.
14. Integration test xác minh routing, deserialization, assignment, error handling và offset.
15. Có metric/log để quan sát consumer group, lag, processing latency và rebalance.

Nhiều `ConcurrentKafkaListenerContainerFactory` cho phép một service tổ chức các listener theo yêu cầu riêng về consumer, payload, concurrency, batch, acknowledgment và error handling. Chọn factory bằng `containerFactory` giúp mỗi endpoint dùng đúng cấu hình. Hãy tách factory khi semantics khác nhau, chia sẻ cấu hình khi chúng tương thích và luôn kiểm thử container thực tế thay vì chỉ kiểm tra bean được tạo.

## 21. Tự kiểm tra

1. `ConsumerFactory` khác `ConcurrentKafkaListenerContainerFactory` ở trách nhiệm nào?
2. Vì sao Spring Kafka mặc định tìm bean `kafkaListenerContainerFactory` khi annotation không chỉ định `containerFactory`?
3. Khi nào một ứng dụng nên tạo nhiều `ConsumerFactory` thay vì chỉ nhiều container factory?
4. Làm thế nào để `@KafkaListener` chọn factory tùy chỉnh?
5. Vì sao cần `@Qualifier` khi inject nhiều `ConsumerFactory`?
6. `setBatchListener(true)` ảnh hưởng method signature như thế nào?
7. Vì sao mỗi factory có thể đặt concurrency và AckMode riêng?
8. Điều gì xảy ra nếu listener dùng chung group ID và subscribe cùng topic?
9. Nhiều container factory khác gì với dynamic container được tạo trong runtime?
10. Cần kiểm thử những gì để xác nhận listener thực sự dùng đúng factory?

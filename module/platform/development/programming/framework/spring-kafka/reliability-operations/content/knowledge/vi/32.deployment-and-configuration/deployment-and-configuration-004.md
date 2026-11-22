# Cấu hình listener container factory trong Spring Kafka

## 1. Bối cảnh: vì sao listener container factory quyết định độ tin cậy?

Trong Spring Kafka, phương thức gắn `@KafkaListener` trông rất đơn giản:

```java
@KafkaListener(topics = "orders.events")
public void onOrder(String payload) {
    process(payload);
}
```

Nhưng phía sau phương thức này là một **listener container** có nhiệm vụ tạo Kafka consumer, gọi `poll()`, phân phối record tới method, xử lý exception, quản lý consumer group/rebalance, commit offset và dừng/khởi động đúng vòng đời ứng dụng. Nếu factory cấu hình sai, business code vẫn có thể “chạy được” trong môi trường thử nghiệm nhưng gây mất dữ liệu, xử lý lặp, consumer lag, rebalancing liên tục hoặc tự động bỏ qua poison message khi triển khai nhiều replica.

**Cấu hình listener container factory** thuộc chương *Deployment và cấu hình* trong module *Spring Kafka Reliability Operations*. Nội dung bài tập trung vào cách chọn và cấu hình `ConcurrentKafkaListenerContainerFactory` cho một dịch vụ cần vận hành bền vững.

Sau bài học, bạn có thể:

- Phân biệt `ConsumerFactory`, `KafkaListenerContainerFactory`, `ConcurrentMessageListenerContainer` và `@KafkaListener`.
- Sử dụng cấu hình tự động của Spring Boot hoặc định nghĩa nhiều factory theo từng loại workload.
- Chọn `AckMode`, concurrency, poll timeout, idle events và consumer properties có cơ sở.
- Kết hợp `DefaultErrorHandler`, backoff, `DeadLetterPublishingRecoverer` và chính sách deserialization.
- Hiểu offset commit, at-least-once, idempotency, transaction, retry và ranh giới giữa Kafka với database.
- Cấu hình record listener và batch listener mà không nhầm lẫn semantics.
- Điều khiển startup/pause/resume, quan sát consumer lag, rebalance và non-responsive consumer.
- Kiểm thử factory bằng test tích hợp broker và triển khai nhiều replica an toàn.

Ví dụ Java nhắm tới **Java 17, Spring Boot 3.4.x, Spring Kafka 3.3.x**. Với Boot 4/Spring Kafka 4, một số package của Spring Boot auto-configuration và API có thể thay đổi; cần đối chiếu theo phiên bản sử dụng, không sao chép import giữa hai đời framework.

---

## 2. Bốn lớp cấu hình phải phân biệt

```text
application.yml / environment / secrets
                 │
                 ▼
          ConsumerFactory<K, V>
       ├── bootstrap servers
       ├── group ID / client ID
       ├── key/value deserializer
       ├── max.poll.records / interval
       ├── isolation level
       └── TLS / SASL / other consumer configs
                 │
                 ▼
  ConcurrentKafkaListenerContainerFactory<K, V>
       ├── concurrency
       ├── batchListener
       ├── CommonErrorHandler
       ├── record/message converter
       ├── record filter/interceptor
       └── ContainerProperties template
              ├── AckMode
              ├── pollTimeout
              ├── idleEventInterval
              ├── autoStartup
              ├── observationEnabled
              └── lifecycle / commit controls
                 │
                 ▼  container created for each endpoint
      ConcurrentMessageListenerContainer
                 │
            N child containers
                 │
            KafkaConsumer.poll()
                 │
                 ▼
     @KafkaListener application method
                 │
       success / throw exception
                 │
                 ▼
       commit / retry / DLT / seek
```

### 2.1. ConsumerFactory: định nghĩa cách tạo KafkaConsumer

`ConsumerFactory<K,V>` quản lý cấu hình dùng khi tạo `KafkaConsumer`, ví dụ:

- `bootstrap.servers`, `group.id`, `client.id`.
- `key.deserializer` và `value.deserializer`.
- `enable.auto.commit`, `auto.offset.reset`.
- `max.poll.records`, `max.poll.interval.ms`.
- `session.timeout.ms`, `heartbeat.interval.ms` nếu cần.
- `isolation.level=read_committed` khi cần chỉ đọc những record transactional đã commit.
- Security: `security.protocol`, SASL, SSL.

**ConsumerFactory không phải là một KafkaConsumer dùng chung cho các luồng.** Một concurrent listener container tạo các consumer con; KafkaConsumer không được truy cập đồng thời từ nhiều thread tùy ý.

### 2.2. Listener container factory: mẫu để tạo container

`ConcurrentKafkaListenerContainerFactory` là **factory bean**, không phải consumer thread đang chạy. Nó cung cấp mẫu cấu hình; khi Spring xử lý `@KafkaListener`, mỗi endpoint sẽ có container tương ứng được tạo từ factory đó.

Hệ quả:

- Hai listener cùng sử dụng một factory có thể có **hai listener containers độc lập**, mỗi container lại có nhiều consumer con.
- `setConcurrency(3)` áp dụng cho container được tạo bởi factory, không có nghĩa toàn bộ ứng dụng chỉ có ba consumer.
- Thay đổi factory object sau khi container đã được khởi tạo không nên được coi là cách cập nhật runtime tất cả consumer đã chạy; cần cấu hình trước khi endpoint được tạo hoặc dùng API runtime phù hợp.
- Nếu chỉ muốn thay đổi một listener, cân nhắc `@KafkaListener(concurrency=...)` hoặc factory chuyên biệt thay vì sửa mặc định cho toàn hệ thống.

### 2.3. KafkaListenerEndpointRegistry: quản lý các listener đã tạo

Các container từ `@KafkaListener` được đăng ký với `KafkaListenerEndpointRegistry`. Registry cho phép truy cập bằng listener ID để quan sát, start, stop, pause, resume theo khả năng của container.

Registry không phải nơi cấu hình tất cả consumer properties ban đầu. Nó chủ yếu giúp **điều khiển vòng đời** của các listener hiện hữu.

### 2.4. Listener: nơi đặt business logic

`@KafkaListener` nên tập trung vào:

1. Decode/validate event theo schema.
2. Gọi domain service có kiểm soát transaction/idempotency.
3. Hoàn tất thành công hoặc ném exception có phân loại.
4. Không tự nuốt exception khi muốn container retry/DLT.

Đừng lồng `while(true)` hoặc tự gọi `consumer.poll()` trong listener. Container đã quản lý poll, group membership và offset.

---

## 3. Quyết định: dùng Spring Boot auto-configuration hay factory tự định nghĩa?

Spring Boot cung cấp Kafka auto-configuration qua namespace `spring.kafka.*`. Nếu ứng dụng chỉ cần một loại listener, thường **không cần** tự khai báo `ConcurrentKafkaListenerContainerFactory`: Boot sẽ tạo default bean tên `kafkaListenerContainerFactory` dựa trên cấu hình và các bean liên quan.

### 3.1. Cấu hình mặc định bằng application.yml

Ví dụ cho record listener thông thường:

```yaml
spring:
  kafka:
    bootstrap-servers: "localhost:9092"
    consumer:
      group-id: "orders-worker"
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      max-poll-records: 200
      properties:
        max.poll.interval.ms: 300000
    listener:
      type: single
      ack-mode: record
      concurrency: 3
      poll-timeout: 2s
      auto-startup: true
      missing-topics-fatal: true
```

Ý nghĩa:

- `type: single` dùng record listener, không truyền toàn bộ poll batch vào method.
- `ack-mode: record` commit offset sau khi listener xử lý record thành công theo container policy, khi consumer auto commit đã tắt.
- `concurrency: 3` tạo tối đa ba consumer con cho **mỗi listener container**.
- `poll-timeout: 2s` điều chỉnh thời gian chờ của `poll()`, **không** giới hạn thời gian chạy business method.
- `missing-topics-fatal: true` giúp fail sớm khi topic cấu hình bắt buộc chưa tồn tại; cách phát hiện và áp dụng có giới hạn với subscription pattern.
- `auto-offset-reset: earliest` chỉ dùng khi **không có committed offset hợp lệ** cho group/partition (hoặc tình huống offset out of range), không bắt group đã có offset đọc lại từ đầu.
- `max-poll-records: 200` hạn chế số record trả về trong một lần poll, không thay concurrency.
- `enable-auto-commit: false` để offset commit thuộc cơ chế container, tránh Kafka tự commit theo thời gian khi business processing chưa xong.

Đây là policy mẫu, không phải bộ giá trị production dùng cho mọi workload. `earliest` có thể khiến consumer group hoàn toàn mới đọc một lượng lịch sử rất lớn; phải xác nhận phạm vi và retention.

### 3.2. Khi nào nên tự khai báo factory?

Cần custom factory khi:

- Cùng ứng dụng có **record listener** và **batch listener** với ngưỡng khác nhau.
- Một nhóm topic yêu cầu `AckMode.RECORD` và nhóm khác yêu cầu `MANUAL_IMMEDIATE`.
- Một nhóm cần DLT/retry riêng, nhóm khác fail-fast.
- Một nhóm cần concurrency 1 để tiết kiệm tài nguyên hoặc bảo đảm xử lý tuần tự theo partition.
- Cần message converter/record filter/interceptor riêng.
- Cần container-level metrics/observations/events khác nhau.
- Muốn kiểm soát startup theo feature flag hoặc quy trình vận hành.
- Có các nhóm consumer dùng deserializer/credentials/bootstrap clusters khác nhau.

**Một factory không phải nơi duy nhất cấu hình Kafka.** Nếu hai nhóm dùng hai broker hoặc hai schema/value deserializers khác nhau, thường cần **hai ConsumerFactory** tương ứng, không chỉ hai listener container factory dùng chung một consumer factory.

### 3.3. Dùng Boot configurer để giữ baseline

Trong Spring Boot 3.4.x, `ConcurrentKafkaListenerContainerFactoryConfigurer` nằm tại:

```java
import org.springframework.boot.autoconfigure.kafka
        .ConcurrentKafkaListenerContainerFactoryConfigurer;
```

Khi tự tạo factory, dùng configurer giúp kế thừa phần thiết lập mà Boot đã đọc từ `spring.kafka.*` và các bean được auto-wire. Sau đó override **chỉ** những khác biệt của nhóm listener.

Điều này an toàn hơn việc tạo một factory hoàn toàn mới rồi quên mất converter, transaction manager, error handler, observation hoặc consumer configuration mà Boot trước đó đã quản lý.

**Chú ý version:** ở Spring Boot 4, class configurer nằm dưới namespace auto-configuration Kafka khác. Đừng áp import Boot 4 cho dự án Boot 3.

---

## 4. Ví dụ hoàn chỉnh: record listener có retry và Dead Letter Topic

### 4.1. Nghiệp vụ giả định

Dịch vụ `orders-service` đọc topic `orders.events`:

- Key: order ID ở dạng String.
- Value: JSON ở dạng String, ví dụ `{"eventId":"evt-201","orderId":201,"status":"PAID"}`.
- Topic chính có **3 partitions**.
- Consumer group `orders-worker`, triển khai ban đầu một instance với concurrency 3.
- Business validation sai → không retry, chuyển DLT.
- Phụ thuộc database tạm thời lỗi → retry 2 lần, cách nhau 1 giây.
- Hết retry → publish DLT, và chỉ tiếp tục nếu DLT publish thành công.
- DLT tên `orders.events.DLT`, ít nhất 3 partitions vì ví dụ giữ nguyên partition gốc.
- Database-side effect phải idempotent vì Kafka offset và DB commit không có một giao dịch nguyên tử mặc định.

### 4.2. Dependency

Ví dụ Gradle cho hệ Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

Nếu nghiệp vụ ghi DB, thêm `spring-boot-starter-jdbc` hoặc `spring-boot-starter-data-jpa` cùng JDBC driver theo database thực tế. Ví dụ không nhúng credential vào source.

### 4.3. YAML tách infra config và business names

```yaml
spring:
  kafka:
    bootstrap-servers: "${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}"
    consumer:
      group-id: "orders-worker"
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
    listener:
      type: single
      ack-mode: record
      auto-startup: true
      poll-timeout: 2s

app:
  kafka:
    orders:
      topic: "orders.events"
      group-id: "orders-worker"
      concurrency: 3
```

Với String deserializer/serializer, ví dụ đơn giản và dễ nhìn thấy JSON sai ở tầng listener. Nếu sử dụng typed `JsonDeserializer<OrderEvent>` thì lỗi có thể xảy ra **trước khi vào listener**; cần `ErrorHandlingDeserializer` và producer tương thích DLT cho dữ liệu giải mã thất bại (xem mục 10).

`acks: all` và idempotent Kafka producer giúp tăng độ tin cậy của **publish lên Kafka**, nhưng không tạo exactly-once side effect ở database.

### 4.4. Exception phân loại

Đặt trong `com.example.kafka.orders`:

```java
package com.example.kafka.orders;

public final class OrderExceptions {

    private OrderExceptions() {}

    public static class InvalidOrderEventException
            extends RuntimeException {
        public InvalidOrderEventException(String message) {
            super(message);
        }
        public InvalidOrderEventException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static class TemporaryStorageException
            extends RuntimeException {
        public TemporaryStorageException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

Trong ứng dụng thật, đừng bắt mọi `RuntimeException` rồi đổi thành `TemporaryStorageException`. Bug mapping hoặc lỗi security không được retry chỉ vì cùng superclass; cần classifier chính xác hơn.

### 4.5. Cấu hình factory và error handler

```java
package com.example.kafka.orders;

import java.time.Duration;

import org.apache.kafka.common.TopicPartition;

import org.springframework.boot.autoconfigure.kafka
        .ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;

import org.springframework.kafka.config
        .ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;

import org.springframework.util.backoff.FixedBackOff;

import com.example.kafka.orders.OrderExceptions
        .InvalidOrderEventException;

@Configuration(proxyBeanMethods = false)
public class OrdersListenerConfiguration {

    @Bean
    DefaultErrorHandler ordersErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        kafkaTemplate,
                        (record, exception) ->
                                new TopicPartition(
                                        record.topic() + ".DLT",
                                        record.partition()));

        // Không bỏ qua bản ghi lỗi khi publish DLT thất bại.
        recoverer.setFailIfSendResultIsError(true);
        recoverer.setWaitForSendResultTimeout(
                Duration.ofSeconds(20));

        // 2 retries, tổng cộng tối đa 3 delivery attempts.
        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(1000L, 2L));

        handler.addNotRetryableExceptions(
                InvalidOrderEventException.class);

        return handler;
    }

    @Bean("ordersListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<Object, Object>
    ordersListenerContainerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<Object, Object> consumerFactory,
            DefaultErrorHandler ordersErrorHandler,
            @Value("${app.kafka.orders.concurrency:3}")
                    int concurrency) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory
                        <Object, Object>();

        // Lấy cấu hình baseline từ Spring Boot.
        configurer.configure(factory, consumerFactory);

        factory.setBatchListener(false);
        factory.setConcurrency(concurrency);
        factory.setCommonErrorHandler(ordersErrorHandler);

        ContainerProperties props =
                factory.getContainerProperties();

        props.setAckMode(ContainerProperties.AckMode.RECORD);
        props.setPollTimeout(2000L);
        props.setIdleEventInterval(60_000L);
        props.setObservationEnabled(true);
        props.setMissingTopicsFatal(true);
        props.setLogContainerConfig(true);

        return factory;
    }
}
```

**Các điểm cần đọc kỹ:**

- Factory bean có tên **`ordersListenerContainerFactory`**. Listener phải chỉ rõ `containerFactory="ordersListenerContainerFactory"`.
- `configurer.configure(...)` nhận các giá trị đã được Boot cấu hình, sau đó code override batch mode, concurrency, ack mode và error handler.
- `ContainerProperties` là **template của container được tạo từ factory**, không phải một đối tượng được dùng chung để vận hành trực tiếp các KafkaConsumer.
- `FixedBackOff(1000L, 2L)` nghĩa là **hai lần retry sau lần thử đầu**, thường tổng tối đa ba delivery attempts. Không nhầm tham số 2 là “tổng hai lần gọi”.
- `InvalidOrderEventException` được coi là không retryable, nên recoverer được gọi ngay khi lỗi phù hợp.
- Nếu DLT topic thiếu partition `record.partition()`, publish sẽ lỗi. Vì vậy DLT phải có ít nhất số partition của topic nguồn khi dùng resolver này.
- `setFailIfSendResultIsError(true)` yêu cầu recoverer quan sát kết quả publish DLT, giảm rủi ro coi recover thành công khi send thực tế lỗi.
- `setObservationEnabled(true)` yêu cầu có Micrometer Observation/registry phù hợp để metric/trace hữu ích. Nó không tự tạo dashboard hay alert.
- `setMissingTopicsFatal(true)` phù hợp topic bắt buộc đã được provisioning; môi trường tạo topic động cần cân nhắc.
- Một bean `DefaultErrorHandler` duy nhất có thể cũng được Boot dùng cho factory auto-config khác. Nếu nhiều factory cần chính sách khác nhau, cấu hình rõ từng factory, kiểm tra auto-wiring và không ngầm dùng một error handler chung ngoài ý muốn.

Trong demo, Kafka producer của DLT dùng `StringSerializer`, do input dùng `StringDeserializer`. Với record có lỗi deserialization dẫn đến dữ liệu gốc là `byte[]`, cần producer serializer phù hợp để gửi dữ liệu thô lên DLT.

### 4.6. Listener xử lý từng record

```java
package com.example.kafka.orders;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.apache.kafka.clients.consumer.ConsumerRecord;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

import com.example.kafka.orders.OrderExceptions
        .InvalidOrderEventException;

@Component
public class OrdersListener {

    private final ObjectMapper mapper;
    private final OrderProcessingService service;

    public OrdersListener(
            ObjectMapper mapper,
            OrderProcessingService service) {
        this.mapper = mapper;
        this.service = service;
    }

    @KafkaListener(
            id = "orders-v1",
            topics = "${app.kafka.orders.topic}",
            groupId = "${app.kafka.orders.group-id}",
            containerFactory = "ordersListenerContainerFactory")
    public void handle(ConsumerRecord<String, String> record) {

        JsonNode event;
        try {
            event = mapper.readTree(record.value());
        } catch (JsonProcessingException invalidJson) {
            throw new InvalidOrderEventException(
                    "INVALID_JSON", invalidJson);
        }

        if (event == null
                || !event.hasNonNull("eventId")
                || !event.hasNonNull("orderId")
                || !event.get("orderId").isIntegralNumber()
                || !event.hasNonNull("status")) {
            throw new InvalidOrderEventException(
                    "MISSING_OR_INVALID_FIELDS");
        }

        String eventId = event.get("eventId").asText();
        long orderId = event.get("orderId").asLong();
        String status = event.get("status").asText();

        if (eventId.isBlank()
                || orderId <= 0
                || status.isBlank()) {
            throw new InvalidOrderEventException(
                    "INVALID_VALUES");
        }

        // Service phải xử lý idempotency ở nơi có durable state.
        service.process(
                eventId,
                orderId,
                status,
                record.topic(),
                record.partition(),
                record.offset());

        // Chỉ return khi xử lý bền vững đã thành công.
        // Container quyết định commit theo AckMode.RECORD.
    }
}
```

Interface nghiệp vụ:

```java
package com.example.kafka.orders;

public interface OrderProcessingService {

    void process(
            String eventId,
            long orderId,
            String status,
            String topic,
            int partition,
            long offset);
}
```

Ví dụ chưa cài `OrderProcessingService` vì persistence layer phụ thuộc DB nghiệp vụ; mục 12 minh họa idempotency. Điều quan trọng trong cấu hình container: **listener phải ném lỗi khi xử lý chưa thành công**. Nếu bắt exception, log rồi return bình thường, container có thể commit offset và mất cơ hội retry/DLT.

---

## 5. AckMode: quyết định lúc offset được commit

Kafka consumer đọc record tại một offset. Sau khi ứng dụng xử lý, container có thể ghi committed offset tiếp theo vào Kafka consumer group. Nếu xử lý thành công nhưng process chết **trước khi offset commit**, record có thể được giao lại.

Kafka không tự bảo đảm “mỗi business side effect xảy ra đúng một lần” khi ghi vào DB, email hay HTTP service.

### 5.1. Các chế độ chính

| AckMode | Khi nào commit theo container | Điểm cần lưu ý |
|---|---|---|
| `RECORD` | Sau mỗi record được listener xử lý thành công | Dễ hiểu, nhiều lần commit hơn, phù hợp xử lý riêng từng record |
| `BATCH` | Sau khi xử lý các record nhận từ một `poll()` | Đây là default container ack mode, **không bắt buộc listener là batch method** |
| `TIME` | Khi điều kiện thời gian đã đạt và các record thích hợp được xử lý | Độ trễ commit có thể lớn hơn; phải xét `pollTimeout` |
| `COUNT` | Sau ít nhất số record được cấu hình | Có thể replay nhiều record hơn sau crash |
| `COUNT_TIME` | Khi đạt số lượng hoặc thời gian | Điều chỉnh chi phí commit theo traffic |
| `MANUAL` | Listener gọi `Acknowledgment.acknowledge()`; commit theo quy tắc container | Cần biết ack được queue và thời điểm commit |
| `MANUAL_IMMEDIATE` | Ack trên consumer thread có thể commit ngay | Phải nhất quán thread/context; không trộn ack bất thường |

Các cơ chế này được hiểu khi `enable.auto.commit=false` và không có transactional container làm thay đổi cách gửi offset.

### 5.2. Đừng nhầm AckMode.BATCH và batch listener

Hai trục **khác nhau**:

- `factory.setBatchListener(true)`: method nhận **một danh sách record trong mỗi lần gọi**.
- `AckMode.BATCH`: **thời điểm commit offset** sau khi xử lý các record của một `poll()`.

Có thể có **record listener + AckMode.BATCH**: container gọi method lần lượt cho từng record, sau đó commit offset khi hoàn thành poll batch. Đây là trường hợp nhiều cấu hình mặc định.

Ngược lại, batch listener có thể dùng các chế độ ack hỗ trợ phù hợp. Tuy nhiên error handling, partial batch commits và transaction semantics phải được xem theo tài liệu version, không giả định chỉ cần đổi flag.

### 5.3. Manual ack trong một factory riêng

Một nhóm listener muốn ack rõ ràng sau khi lưu dữ liệu bền vững:

```java
@Bean("manualAckListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<Object, Object>
manualAckListenerContainerFactory(
        ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
        ConsumerFactory<Object, Object> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory
                    <Object, Object>();

    configurer.configure(factory, consumerFactory);

    factory.setConcurrency(1);
    factory.setBatchListener(false);

    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.MANUAL_IMMEDIATE);

    return factory;
}
```

Listener:

```java
@KafkaListener(
        id = "accounting-v1",
        topics = "accounting.events",
        groupId = "accounting-worker",
        containerFactory = "manualAckListenerContainerFactory")
public void handle(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    accountingService.persistIdempotently(
            record.key(), record.value());

    acknowledgment.acknowledge();
}
```

Import:

```java
import org.springframework.kafka.support.Acknowledgment;
```

**Không gọi `acknowledge()` trong `finally`**: nếu service thất bại mà offset vẫn được ack, message có thể bị coi là đã xử lý.

Với `MANUAL_IMMEDIATE`, ack trên listener/consumer thread có semantics khác ack từ thread khác. Không dùng async callback mà chưa hiểu `asyncAcks`, gaps, pause và duplicate risk. Manual ack không tạo exactly-once DB/Kafka.

### 5.4. Khi nào chọn RECORD thay vì MANUAL?

- **RECORD:** method đồng bộ, hoàn thành khi side effect durable; thường dễ bảo trì hơn.
- **MANUAL:** app thực sự cần điều khiển acknowledgement, ví dụ có hand-off đồng bộ tới một durable store rồi ack theo hợp đồng.
- **MANUAL_IMMEDIATE:** muốn commit ngay theo thao tác ack trên consumer thread, hiểu các trade-off.
- **BATCH/COUNT/TIME:** throughput và commit overhead cần tối ưu, chấp nhận cửa sổ redelivery rộng hơn.

Không chọn MANUAL chỉ vì nghe “an toàn hơn”; nhiều lỗi production đến từ quên ack, ack quá sớm hoặc ack sai thread.

---

## 6. Concurrency và số partitions

### 6.1. Công thức năng lực xử lý

Với một consumer group được triển khai trên nhiều pod:

```text
Tổng consumer con ≈
    số replica × concurrency của từng listener container

Active consumer nhận dữ liệu ≤ số partition hiện có
    (cho một topic trong cùng group, theo assignment)
```

Ví dụ một topic `orders.events` có 6 partitions:

| Replicas | Concurrency mỗi replica | Tổng consumer con | Tối đa active cho topic 6 partitions |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 1 |
| 1 | 3 | 3 | 3 |
| 2 | 3 | 6 | 6 |
| 3 | 3 | 9 | 6; phần còn lại có thể idle |
| 6 | 2 | 12 | 6; tăng thêm consumer không tăng throughput |

Các giá trị giả định chỉ xét một listener/group và một topic với sáu partitions. Khi subscribe nhiều topics và dùng partition assignor khác nhau, phân phối active consumers phức tạp hơn.

### 6.2. Ordering

Kafka bảo đảm thứ tự trong **một partition**, không bảo đảm thứ tự toàn topic. Nếu order events của cùng `orderId` phải có thứ tự, producer nên dùng một key ổn định để các event của cùng aggregate đi vào cùng partition trong phạm vi cấu hình partitioning ổn định.

Tăng concurrency không khiến cùng một partition được hai consumer trong group xử lý song song tại cùng lúc. Nếu business logic tự đẩy record từ listener sang thread pool mà không quản lý thứ tự/ack, bạn có thể tự phá ordering dù Kafka vẫn giữ thứ tự log.

### 6.3. Concurrency không thay group.id

`group.id` quyết định tập consumer chia nhau partitions và committed offsets. Nếu hai ứng dụng dùng cùng group ID, chúng chia công việc; nếu dùng group ID khác, mỗi group nhận luồng riêng.

`@KafkaListener(id="...")` có thể được dùng làm group ID trong một số trường hợp khi `groupId` không được cung cấp (theo semantics của annotation). Để tránh bất ngờ khi đổi listener ID, hãy khai báo `groupId` chủ đích.

### 6.4. Multi-topic subscriptions và assignor

Khi một group subscribe nhiều topic với số partition khác nhau, default partition assignor có thể phân phối không như kỳ vọng. Cần quan sát **partition assignment thực tế** trước khi quyết định concurrency.

Có thể lựa chọn assignor theo Kafka client config, ví dụ:

```yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: >-
          org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Đây là ví dụ cần kiểm tra tương thích với broker/client, nhóm consumer hiện hữu và quy trình rolling deployment. Đổi assignor trong một group đang chạy cần lên kế hoạch rebalance; không thay ngay giữa giờ cao điểm.

### 6.5. Không tăng concurrency chỉ để “sửa lag”

Consumer lag còn có thể do:

- DB/HTTP dependency chậm.
- Record xử lý không đều; một partition có rất nhiều record.
- Lỗi retry liên tục trên một partition.
- GC pause, CPU throttling, connection pool cạn.
- `max.poll.records` quá lớn so với thời gian xử lý.
- Producer key skew khiến một partition quá nóng.
- DLT publish hoặc transaction bị nghẽn.

Tăng consumer threads có thể làm DB chậm hơn hoặc tăng rebalance khi pod hết CPU. Phải xác định bottleneck trước khi scale.

---

## 7. Consumer poll: max.poll.records và max.poll.interval.ms

### 7.1. Một poll khác một chunk và khác một transaction

`KafkaConsumer.poll()` nhận một nhóm record từ broker. Với record listener, container có thể gọi listener nhiều lần từ nhóm đó trước lần poll tiếp theo.

Hai cấu hình thường gặp:

- `max.poll.records`: số record tối đa được trả về trong một lần poll.
- `max.poll.interval.ms`: thời gian tối đa giữa những lần poll hợp lệ trước khi consumer bị coi là không tiến triển trong group theo quy tắc client/broker.

Nếu xử lý 500 record mỗi record 2 giây trên một consumer thread, tổng thời gian cho poll có thể khoảng 1.000 giây, vượt `max.poll.interval.ms=300000` (5 phút). Consumer có thể bị rebalance hoặc mất assignment; kết quả là duplicate deliveries và lag bất thường.

### 7.2. Công thức tư duy

```text
Worst-case processing time per poll ≈
    max.poll.records × p99 processing time per record
  + retry/backoff overhead
  + scheduling/GC/I/O overhead
```

Công thức mang tính bảo thủ; số record nhận thực tế có thể ít hơn, và thời gian xử lý phân bố không đều. Trong production cần **đo p99 và outliers** chứ không chỉ latency trung bình.

Ví dụ:

```text
max.poll.records = 100
p99 business processing = 1.5 seconds
retry/outlier budget = 60 seconds
--------------------------------
estimated worst-case ≈ 210 seconds
max.poll.interval.ms = 300 seconds
```

Còn khoảng 90 giây headroom theo giả định. Nếu processor đôi khi đợi HTTP 10 phút, thiết kế đồng bộ này không phù hợp; nên dùng timeout, circuit breaker, giảm poll batch hoặc handoff bền vững.

### 7.3. pollTimeout không giới hạn business method

`factory.getContainerProperties().setPollTimeout(2000L)` chỉ giới hạn một lần KafkaConsumer.poll đợi dữ liệu trong tối đa khoảng 2 giây. Nó **không** hủy method `handle(...)` sau 2 giây.

Muốn giới hạn xử lý business, cấu hình timeout tại JDBC/HTTP, transaction, deadline hoặc worker protocol. Đừng dùng pollTimeout làm “timeout tổng của listener”.

### 7.4. max.poll.records không phải concurrency

`max.poll.records=100` không tạo 100 thread. `concurrency=3` tạo tối đa ba consumer con, mỗi consumer có thể nhận tới 100 record/poll. Working set và số request DB có thể tăng theo số consumer.

### 7.5. idleBetweenPolls và backpressure

`ContainerProperties.setIdleBetweenPolls(...)` có thể tạo thời gian nghỉ giữa các poll, nhưng phải bảo đảm thời gian xử lý và idle phù hợp với `max.poll.interval.ms`. Đây là phương án throttle đơn giản, **không thay** rate limiter và cơ chế backpressure chuyên nghiệp khi dependency có quota nghiêm ngặt.

---

## 8. Error handling: Retry, recover và Dead Letter Topic

### 8.1. Dòng xử lý lỗi

```text
Kafka record
     │
     ▼
@KafkaListener
     │
     ├── thành công
     │      └── container commit theo AckMode
     │
     └── throw exception
              │
              ▼
       DefaultErrorHandler
              │
              ├── lỗi non-retryable
              │     └── recoverer → DLT
              │
              └── lỗi retryable
                    ├── retry 1
                    ├── retry 2
                    └── vẫn lỗi
                          └── recoverer → DLT
                                      │
                             DLT publish thành công?
                                ├── Có → hoàn tất recovery,
                                │         offset có thể advance
                                └── Không → báo lỗi/re-deliver
```

Dòng trên mô tả cấu hình demo record listener không transactional. Cách seek/redelivery, commit và error handler khác đi khi có transaction hoặc batch listener.

### 8.2. DefaultErrorHandler và FixedBackOff

`DefaultErrorHandler` thay thế nhiều error handler đời cũ, cho phép retry và chuyển record sang recoverer khi hết retry.

`FixedBackOff(1000L,2L)`:

- Lần gọi business đầu tiên thất bại.
- Retry lần thứ nhất sau 1 giây.
- Retry lần thứ hai sau 1 giây.
- Nếu tiếp tục lỗi, recoverer nhận record.

Khi test, đếm **tổng 3 lần gọi listener** cho case retryable thất bại liên tục theo policy này (trừ khi có ngoại lệ môi trường/transaction và handler khác). Với non-retryable, không dành các retry kể trên.

### 8.3. DLT không phải “bỏ record không cần báo”

`DeadLetterPublishingRecoverer` giúp lưu record lỗi ở topic khác để điều tra/replay. Nhưng nếu DLT publish lỗi mà container vẫn coi recover thành công, record có nguy cơ bị mất theo chính sách offset.

Vì vậy demo bật `setFailIfSendResultIsError(true)`. Cần giám sát producer errors, DLT topic availability, broker acks và timeout. Với yêu cầu dữ liệu quan trọng, cần chọn retention, ACL và khả năng replay DLT phù hợp.

**Một record đã chuyển DLT vẫn chưa được xử lý nghiệp vụ thành công.** Cần quy trình triage/quarantine/replay và báo cáo ảnh hưởng.

### 8.4. DLT partition phải khớp resolver

Default resolver của Spring Kafka thường đưa record lỗi sang topic với hậu tố `-dlt` và **partition gốc**. Demo thay hậu tố bằng `.DLT` nhưng vẫn giữ partition:

```java
(record, exception) ->
        new TopicPartition(
                record.topic() + ".DLT",
                record.partition())
```

Nếu topic chính có 6 partitions mà DLT chỉ có 3, record từ partition 4/5 không thể gửi sang cùng index partition. Có thể đổi resolver để Kafka chọn partition theo key (trả partition âm theo API hỗ trợ), nhưng phải quyết định lại ordering/traceability. Phương án đơn giản là provision DLT đủ partitions và kiểm thử mapping.

### 8.5. Poison pill và deserialization error

Lỗi xảy ra **trước listener** như `JsonDeserializer` không parse được JSON có thể ngăn listener method được gọi. Nếu trực tiếp dùng deserializer mà không có lớp xử lý phù hợp, container có thể lặp lỗi poll hoặc dừng mà không có DLT record.

`ErrorHandlingDeserializer` là adapter Spring Kafka giúp chuyển thông tin deserialization error vào header để container/error handler có cơ hội xử lý. Với record listener, Spring Kafka có tích hợp để route lỗi deserialization; với batch listener cần xử lý lỗi từng record rõ ràng.

Nếu dùng typed deserializer, DLT producer phải có serializer tương thích với **giá trị raw byte[]** khi phục hồi record không deserialize được. Một producer chỉ dùng StringSerializer/JsonSerializer có thể không gửi được một byte[] chưa giải mã. Có thể dùng `DelegatingByTypeSerializer` hoặc nhiều template phù hợp.

### 8.6. Chọn loại lỗi retryable

| Lỗi | Chính sách thường cân nhắc | Lý do |
|---|---|---|
| DB connection timeout tạm thời | Retry có giới hạn | Dependency có thể hồi phục |
| HTTP 503/429 | Retry/backoff/rate limit | Tránh retry storm |
| JSON thiếu trường bắt buộc | DLT ngay | Retry cùng payload không tự sửa |
| Schema version không hỗ trợ | DLT/quarantine, nâng cấp consumer | Cần thay code/schema |
| Authentication/authorization Kafka | Xử lý infra/security, không DLT từng record | Consumer không truy cập được broker/topic |
| Business validation permanent | DLT ngay hoặc reject theo hợp đồng | Đó là dữ liệu không hợp lệ |
| Bug NullPointerException | Thường cảnh báo và điều tra; policy rất thận trọng | Retry có thể che bug hoặc gây tải |
| Redis/DB outage kéo dài | Stop/pause hoặc circuit breaker | Retry vô hạn có thể làm group stuck |
| DLT publish lỗi | Không xác nhận recover thành công | Cần giữ record để retry recovery |

Policy của ứng dụng phải phân loại exception theo domain. Không thêm `IllegalArgumentException.class` vào non-retryable một cách máy móc nếu các tầng thư viện cũng dùng exception đó cho lỗi khác.

---

## 9. Record listener và batch listener: factory nào thích hợp?

### 9.1. Record listener

Cấu hình:

```java
factory.setBatchListener(false);
```

Method:

```java
@KafkaListener(
        topics = "orders.events",
        containerFactory = "ordersListenerContainerFactory")
public void onRecord(ConsumerRecord<String, String> record) {
    orderService.process(record.key(), record.value());
}
```

Phù hợp khi mỗi record có validation, retry và DLT độc lập, cần dễ theo dõi lỗi theo topic/partition/offset.

### 9.2. Batch listener

Cấu hình factory riêng:

```java
@Bean("auditBatchContainerFactory")
ConcurrentKafkaListenerContainerFactory<Object, Object>
auditBatchContainerFactory(
        ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
        ConsumerFactory<Object, Object> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory
                    <Object, Object>();

    configurer.configure(factory, consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(2);

    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.BATCH);

    return factory;
}
```

Listener nhận nhiều record:

```java
@KafkaListener(
        id = "audit-batch-v1",
        topics = "audit.events",
        groupId = "audit-batch-worker",
        containerFactory = "auditBatchContainerFactory")
public void onBatch(
        List<ConsumerRecord<String, String>> records) {

    for (int i = 0; i < records.size(); i++) {
        ConsumerRecord<String, String> record = records.get(i);

        try {
            auditService.store(record.value());
        } catch (RuntimeException e) {
            throw new BatchListenerFailedException(
                    "Audit item failed", e, i);
        }
    }
}
```

Các import:

```java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.BatchListenerFailedException;
```

### 9.3. Vì sao BatchListenerFailedException quan trọng?

Trong batch listener, nếu một item thứ ba lỗi mà method chỉ ném `RuntimeException` chung, handler có thể không biết index của record lỗi, dẫn đến retry **toàn batch** theo fallback policy.

`BatchListenerFailedException` giúp handler xác định record/index thất bại và xử lý các offset có liên quan theo semantics Spring Kafka. Nhưng business side effect ở những item trước đó **vẫn cần idempotency** khi retry/rebalance.

Không giả định `BatchListenerFailedException` làm mọi partial DB write rollback nếu code đã commit ngoài transaction. Đặc biệt với HTTP/email, những item đã gọi thành công không thể tự bị rollback.

### 9.4. Non-blocking retry với @RetryableTopic

`@RetryableTopic` là một hướng khác: chuyển record lỗi qua các retry topics, dùng timer/backoff và sau đó DLT thay vì giữ record trong xử lý blocking retry. Nó có cấu hình topology/auto topic creation và công cụ riêng.

Điều cần biết:

- Non-blocking retries có thể **thay đổi ordering** trong các record cùng partition khi record lỗi được chuyển sang topic khác.
- Không áp dụng cho batch listeners theo cơ chế retry topic thông thường.
- Không dùng đồng thời retry topic và `DefaultErrorHandler` retry dài mà chưa tính tổng attempts/backoff.
- Có những giới hạn với transactional container và các kiểu consumer/record; cần kiểm tra documentation đúng version.
- Factory vẫn chịu trách nhiệm tạo listener containers cho cả main/retry/DLT endpoints theo cách annotation infrastructure cấu hình.

Nếu cần ordering rất chặt, cân nhắc blocking retry, pause partition hoặc mô hình xử lý tuần tự có trạng thái thay vì chuyển record lỗi sang retry topic ngay.

---

## 10. Deserialization và message converter

### 10.1. Ba lớp chuyển dữ liệu có thể xuất hiện

```text
Kafka bytes
    │
    ▼
Kafka Deserializer<K,V>
    │ String / byte[] / JSON object
    ▼
Spring RecordMessageConverter / BatchMessageConverter
    │ optional adaptation to listener signature
    ▼
@KafkaListener arguments
```

**Deserializer** là cấu hình của Kafka consumer, ví dụ `StringDeserializer` hoặc `JsonDeserializer<OrderEvent>`. **MessageConverter** thuộc tầng adapter Spring Kafka, có thể chuyển payload sang parameter của listener.

Nếu cấu hình một `JsonDeserializer` trả `OrderEvent` nhưng method lại mong `String`, hoặc thêm converter khác không phù hợp, ứng dụng có thể thất bại ở tầng conversion trước khi vào business code.

### 10.2. String + Jackson trong listener

Demo dùng StringDeserializer và `ObjectMapper.readTree`:

- Lỗi JSON được chuyển thành `InvalidOrderEventException` trong method.
- Dễ mô tả logic DLT ở tầng application.
- Cần chú ý parse cost và validation schemas.
- Không tự tạo “typed deserialization contract” ở broker; producer và consumer vẫn cần schema/versioning rõ.

### 10.3. Typed JSON deserializer

Khi dùng `JsonDeserializer<OrderEvent>`, cần đặt trusted packages/target type và thường bọc bằng `ErrorHandlingDeserializer` để lỗi parse không làm consumer poll lặp vô hạn. Không cấu hình `trusted.packages=*` tùy tiện khi sự kiện đến từ nguồn không đáng tin; ưu tiên danh sách package/domain được cho phép.

Ví dụ hướng cấu hình bằng YAML (cần điều chỉnh target type và serializer DLT theo project):

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.kafka.orders.OrderEvent
        spring.json.trusted.packages: com.example.kafka.orders
```

Nếu event classes sử dụng các polymorphic types, phải đánh giá bảo mật deserialization và trusted type headers. Đừng để producer có thể gửi tùy ý Java class name rồi consumer khởi tạo type không được phép.

### 10.4. DLT phải giữ bằng chứng lỗi

Khi recover deserialization failure, payload thô có thể cần được gửi lên DLT ở dạng byte array để người vận hành biết record nào bị hỏng. Cần chính sách:

- Producer DLT serialize được loại key/value thực.
- Topic DLT có ACL, retention, encryption tương ứng dữ liệu nguồn.
- Exception headers/stacktrace không làm lộ secrets hoặc PII.
- Có replay tool kiểm soát số lần, schema version và business idempotency.
- Nếu DLT publish thất bại, không tự commit offset như đã recover thành công.

---

## 11. Nhiều listener container factory trong cùng service

### 11.1. Khi nào cần nhiều factory?

Ví dụ một microservice nhận:

- `orders.events`: xử lý đơn hàng theo record, concurrency 3, retry ngắn và DLT.
- `payments.events`: side effect quan trọng, concurrency 1 trên mỗi instance, `MANUAL_IMMEDIATE` và reconciliation.
- `audit.events`: batch listener, processing theo nhóm và writer idempotent.

Có thể tách:

```text
ConsumerFactory (common broker/credentials)
       │
       ├─ ordersListenerContainerFactory
       │     RECORD, concurrency=3, DefaultErrorHandler + DLT
       │
       ├─ paymentsListenerContainerFactory
       │     MANUAL_IMMEDIATE, concurrency=1,
       │     payment-specific policy
       │
       └─ auditBatchContainerFactory
             batchListener=true, concurrency=2,
             batch-specific handling
```

Mỗi listener chọn bean:

```java
@KafkaListener(
        topics = "orders.events",
        containerFactory = "ordersListenerContainerFactory")
void orders(String value) { ... }

@KafkaListener(
        topics = "payments.events",
        containerFactory = "paymentsListenerContainerFactory")
void payments(String value, Acknowledgment acknowledgment) { ... }

@KafkaListener(
        topics = "audit.events",
        containerFactory = "auditBatchContainerFactory")
void audit(List<String> values) { ... }
```

### 11.2. Không tự động chia consumer group theo factory

Hai factory khác tên **không tự tạo hai group ID**. Consumer group được cấu hình qua consumer factory properties và có thể override bằng `@KafkaListener(groupId=...)`.

Nếu các listener cùng group ID nhưng subscribe vào cùng topic, chúng **chia nhau** partition, không phải mỗi listener đọc tất cả record. Nếu cần hai tính năng độc lập cùng nhận toàn bộ topic, đặt group ID khác nhau theo hợp đồng.

### 11.3. Nhiều cluster, nhiều credential

Nếu nhóm payments dùng Kafka cluster khác hoặc bắt buộc credential riêng:

- Định nghĩa `ConsumerFactory` riêng cho payments với bootstrap/security config đúng.
- Định nghĩa `ProducerFactory/KafkaTemplate` DLT đúng cluster.
- Gắn payments factory vào payments consumer factory.
- Đừng lấy configurer của Boot với default consumer factory rồi vô tình giữ lại client cho cluster chính.
- Kiểm thử kết nối và topic ACL cho từng nhóm.

Các client factory có thể chia sẻ bootstrap config, nhưng không nên chia sẻ mutable deserializer instance không thread-safe. Dùng cấu hình và supplier/consumer factory cơ chế chuẩn.

### 11.4. Tên bean mặc định

Nếu `@KafkaListener` không khai báo `containerFactory`, mặc định tìm bean tên `kafkaListenerContainerFactory` (trừ khi cấu hình endpoint registrar có default khác). Nếu bạn chỉ tạo `ordersListenerContainerFactory` nhưng method khác quên chỉ định factory, nó có thể dùng default Boot hoặc không tìm thấy bean tùy cách auto-configuration hoạt động.

Trong ứng dụng nhiều chính sách reliability, nên **khai báo tên factory rõ trên từng listener** và kiểm tra qua integration tests.

---

## 12. Offset, transaction và idempotency

### 12.1. At-least-once mặc định của nhiều pipeline

Một flow phổ biến:

```text
Kafka consume record
        │
        ▼
Write business DB
        │
        ▼
DB commit thành công
        │
        ▼
Container commit Kafka offset
```

Nếu process crash giữa hai bước commit, record được giao lại dù DB đã lưu thành công. Đây là **at-least-once delivery** theo hướng ứng dụng cần chịu được redelivery.

Không thể bảo đảm exactly-once DB side effect chỉ bằng:

```java
props.setAckMode(ContainerProperties.AckMode.RECORD);
```

### 12.2. Idempotency trong DB

Một mẫu PostgreSQL:

```sql
CREATE TABLE processed_kafka_events (
    consumer_group VARCHAR(100) NOT NULL,
    event_id       VARCHAR(120) NOT NULL,
    topic_name     VARCHAR(255) NOT NULL,
    partition_id   INTEGER NOT NULL,
    offset_id      BIGINT NOT NULL,
    PRIMARY KEY (consumer_group, event_id)
);
```

Ý tưởng trong một **database transaction**:

```java
@Transactional
public void process(
        String eventId,
        long orderId,
        String newStatus,
        String topic,
        int partition,
        long offset) {

    int inserted = jdbc.update("""
            INSERT INTO processed_kafka_events
                (consumer_group, event_id,
                 topic_name, partition_id, offset_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (consumer_group, event_id) DO NOTHING
            """,
            "orders-worker", eventId,
            topic, partition, offset);

    if (inserted == 0) {
        return; // Đã xử lý eventId này thành công trước đó.
    }

    jdbc.update("""
            INSERT INTO order_status (order_id, status)
            VALUES (?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET status = EXCLUDED.status
            """,
            orderId, newStatus);
}
```

Đây là **mã ví dụ PostgreSQL**, cần schema `order_status` và bean `JdbcTemplate` thích hợp. Điều kiện quan trọng: cả dedup insert và business write phải nằm **trong cùng DB transaction**. Nếu commit dấu “đã xử lý” trước rồi business write thất bại, lần redelivery có thể bị bỏ qua dù dữ liệu chưa được cập nhật.

### 12.3. Dedup theo offset hay business ID?

- `(topic, partition, offset)` giúp nhận diện một record cụ thể khi Kafka redeliver cùng offset.
- `eventId` ổn định theo nghiệp vụ giúp nhận diện bản sao event được producer publish ở offset khác.
- `orderId` không phải lúc nào cũng đủ, vì một đơn hàng có nhiều events hợp lệ qua thời gian.

Chọn key theo semantics: event ID, aggregate version, business transaction ID hoặc combination có thể được kiểm chứng. Với event cập nhật trạng thái theo phiên bản, cần kiểm tra thứ tự và version để event cũ không ghi đè event mới, ngay cả khi dedup đã chạy đúng.

### 12.4. Kafka transactions

Khi sử dụng Kafka transactions với `KafkaTransactionManager`, container có thể đưa offset vào Kafka transaction và kết hợp với Kafka produce để đạt exactly-once semantics **trong phạm vi Kafka read-process-write** theo cấu hình đúng.

Tuy nhiên:

- Kafka transaction **không tự commit nguyên tử database ngoài Kafka**.
- Nếu có JDBC side effect, cần idempotency/outbox/reconciliation hoặc mô hình transaction coordination được thiết kế cẩn thận.
- Với transactional container, exception thường dẫn tới rollback; error handling dùng `AfterRollbackProcessor` theo policy, không giống demo `DefaultErrorHandler` non-transactional.
- Nếu tự cấu hình `CommonErrorHandler` cho transactional container mà handler nuốt lỗi, có nguy cơ không rollback như kỳ vọng.
- `isolation.level=read_committed` ở consumer quan trọng khi cần tránh record của producer transaction đã abort.

Không bật Kafka transaction chỉ để “giảm trùng” mà không nắm rõ transaction ID, producer fencing, transactional broker settings và mô hình xử lý lỗi.

### 12.5. DLT publish và source offset

Trong demo, recovery bằng DLT được coi là thành công nếu record đã được chuyển tới DLT. Offset của record gốc sau đó có thể được commit theo handler/container. Nhưng đây không phải chính sách “đã xử lý nghiệp vụ”; record đang chờ triage.

Với yêu cầu tuyệt đối không được mất nghĩa vụ nghiệp vụ, DLT phải có consumer/replay workflow, reconciliation và alert. Nếu DLT lỗi hoặc retention hết hạn trước khi xử lý, tính đúng đắn dữ liệu vẫn bị ảnh hưởng.

---

## 13. Vòng đời listener container: startup, pause, resume, stop

### 13.1. autoStartup

`spring.kafka.listener.auto-startup=true` hoặc thuộc tính tương ứng của factory thường khiến listener khởi động theo vòng đời Spring application.

Có những trường hợp nên dùng `autoStartup=false`:

- Ứng dụng phải chạy database migration trước khi nhận record.
- Đợi cache/reference data được khởi tạo.
- Một feature chưa được mở ở môi trường đang triển khai.
- Muốn vận hành rollback/replay có người xác nhận.

Không quên rằng container không startup thì consumer lag vẫn có thể tăng; cần giám sát để phân biệt tạm dừng có chủ đích với sự cố.

### 13.2. Điều khiển bằng registry

```java
import org.springframework.kafka.config
        .KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;

@Service
public class ListenerOperations {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerOperations(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer c =
                registry.getListenerContainer("orders-v1");
        if (c == null) {
            throw new IllegalStateException("Missing orders listener");
        }
        c.pause();
    }

    public void resumeOrders() {
        MessageListenerContainer c =
                registry.getListenerContainer("orders-v1");
        if (c == null) {
            throw new IllegalStateException("Missing orders listener");
        }
        c.resume();
    }

    public void stopOrders() {
        MessageListenerContainer c =
                registry.getListenerContainer("orders-v1");
        if (c != null) {
            c.stop();
        }
    }

    public void startOrders() {
        MessageListenerContainer c =
                registry.getListenerContainer("orders-v1");
        if (c != null) {
            c.start();
        }
    }
}
```

Đoạn code này giả định `@KafkaListener(id="orders-v1")` đã đăng ký. API điều khiển nên chỉ được gọi bởi hệ thống quản trị có authentication/authorization và audit; không phơi bày trực tiếp một endpoint public cho phép dừng mọi consumer.

### 13.3. Pause không giống Stop

| Thao tác | Ý nghĩa |
|---|---|
| `pause()` | Yêu cầu container tạm dừng delivery/partitions, vẫn duy trì cơ chế poll/nhóm theo policy |
| `resume()` | Cho phép tiếp tục từ trạng thái pause |
| `stop()` | Dừng listener container, có thể làm thay đổi membership của group |
| `start()` | Khởi động lại container đã dừng |
| `autoStartup=false` | Không tự khởi động lúc context startup |

Pause thường hữu ích cho short-term backpressure hoặc maintenance. Stop phù hợp khi dịch vụ không nên giữ consumer đang hoạt động. Cả hai có điều kiện thời điểm thực thi; không giả định method return nghĩa là mọi record in-flight đã dừng ngay lập tức.

### 13.4. Graceful shutdown

Khi Kubernetes gửi SIGTERM:

1. Ứng dụng bắt đầu shutdown Spring context.
2. Listener containers dừng nhận thêm record và xử lý/hoàn tất in-flight theo chính sách.
3. Offset commit/transaction được thực hiện nếu xử lý thành công và thời gian cho phép.
4. Consumer rời group hoặc mất assignment; các replica còn lại có thể nhận partitions.

Cần tính thời gian:

- `terminationGracePeriodSeconds` của pod.
- Container `shutdownTimeout`.
- Kafka consumer poll/processing time.
- DB/HTTP timeouts.
- Retry backoff và DLT publish timeout.

Nếu pod bị SIGKILL trước khi commit offset, record có thể được giao lại; side effect cần idempotent. Không tăng termination grace vô hạn để che lỗi code.

---

## 14. Rebalance và deployment nhiều replica

### 14.1. Rebalance xảy ra khi nào?

- Pod/instance bắt đầu hoặc dừng.
- Consumer mất heartbeat hoặc vượt khoảng thời gian poll.
- Topic partition count thay đổi.
- Group membership hoặc partition assignor thay đổi.
- Broker/coordinator gặp sự cố.
- Rolling deployment làm consumer join/leave group.

Rebalance không luôn là lỗi. Nhưng quá nhiều rebalance làm giảm thời gian xử lý và tăng redelivery.

### 14.2. Kết hợp poll interval và retry

Nếu listener bị chặn 10 phút ở HTTP call trong khi `max.poll.interval.ms=5 phút`, consumer group có thể thu hồi assignment. Khi worker tiếp tục cố commit offset, có thể gặp lỗi hoặc record đã được xử lý trên consumer khác.

Cần chọn:

- Timeout HTTP/DB ngắn hơn SLA thực tế.
- `max.poll.records` phù hợp p99 xử lý.
- `max.poll.interval.ms` có headroom đủ.
- Circuit breaker hoặc fail-fast khi dependency lỗi.
- Error handler/backoff không giữ consumer quá lâu.
- Mô hình retry topic/async durable handoff nếu outage dài và ordering cho phép.

### 14.3. Static membership

Kafka hỗ trợ `group.instance.id` cho static group membership trong những môi trường kiểm soát instance identity. Có thể giảm churn khi restart ngắn, nhưng phải bảo đảm ID **duy nhất trên mỗi consumer instance** và phù hợp concurrency/replica lifecycle. Đừng đặt cùng một static group.instance.id cho mọi pod; nguy cơ fencing và không join được group.

Với Kubernetes pods có identity thay đổi, lựa chọn static membership cần được đánh giá và kiểm thử kỹ; không phải một default bắt buộc.

### 14.4. Rolling deployment

Một kế hoạch triển khai:

1. Xác nhận schema compatibility giữa bản producer/consumer cũ và mới.
2. Kiểm tra topology topic, partitions, ACL, group ID, DLT và metrics.
3. Tăng một replica/bản mới với resource limits phù hợp.
4. Quan sát assignment, lag, rebalance, error rate, throughput.
5. Triển khai tiếp khi hệ thống ổn định.
6. Giữ khả năng rollback binary mà không làm event schema mới trở nên không đọc được ở bản cũ.

Nếu consumer mới có DLT policy khác, rollback phải xem record đã được recover sang DLT hay chưa; khôi phục binary không tự đưa những record đó trở lại topic chính.

---

## 15. Quan sát và monitoring ở container level

### 15.1. Những tín hiệu quan trọng

| Signal | Nguồn | Trả lời câu hỏi |
|---|---|---|
| Consumer lag (records/time) | Broker/consumer group metrics | Có theo kịp producer không? |
| Records consumed rate | Kafka client metrics | Có tiếp tục nhận record không? |
| Processing latency p95/p99 | App/Micrometer observation | Business method chậm ở đâu? |
| Retry attempts | `DefaultErrorHandler` retry listener/custom metrics | Có lỗi lặp nhiều không? |
| DLT publish success/failure | Producer/Recoverer metrics | Record lỗi có lưu được không? |
| Rebalance frequency | Client logs/events/metrics | Assignment có ổn định không? |
| Active consumer count | Container metrics/JMX | Concurrency thực có khớp không? |
| Non-responsive consumer events | Spring Kafka container monitor | Poll thread có bị kẹt không? |
| Listener container idle | `ListenerContainerIdleEvent` | Có im lặng khi đáng lẽ phải có dữ liệu? |
| Commit latency/errors | Kafka consumer metrics/logs | Offset có được commit đúng hạn? |
| Container alive/started | Registry/health | Listener đã dừng ngoài ý muốn không? |
| Dependency errors | DB/HTTP client/trace | Nút thắt nằm ở Kafka hay downstream? |

Một consumer có lag bằng 0 không nhất thiết hệ thống nghiệp vụ đã đúng: nếu listener bắt exception rồi return, offset vẫn có thể được commit trong khi DB không xử lý.

### 15.2. Observation

Spring Kafka 3.x hỗ trợ Micrometer Observation ở listener container. Có thể bật:

```java
factory.getContainerProperties().setObservationEnabled(true);
```

Cần có registry/Actuator/tracing backend được cấu hình đúng. Không tự thêm business ID hoặc payload nhạy cảm làm tag/attribute trên mọi message; high-cardinality có thể khiến metrics đắt và lộ dữ liệu.

### 15.3. Idle và non-responsive khác nhau

- **Idle listener event:** container không nhận dữ liệu trong khoảng thời gian quy định. Có thể là trạng thái bình thường khi topic không có message.
- **Non-responsive consumer event:** thread không trở về vòng poll trong khoảng thời gian bất thường theo monitor. Có thể là blocking call, GC, deadlock hoặc các vấn đề xử lý khác.
- **Consumer lag cao:** dữ liệu tồn đọng ở broker, không nhất thiết consumer bị treo; throughput có thể vẫn dương nhưng không đủ.

Cấu hình minh họa:

```java
ContainerProperties props = factory.getContainerProperties();
props.setIdleEventInterval(60_000L);
props.setPollTimeout(2000L);
props.setMonitorInterval(30);
props.setNoPollThreshold(3.0f);
```

`monitorInterval` có đơn vị giây, `pollTimeout` có đơn vị mili giây. Quan sát events và cảnh báo phải được hiệu chỉnh theo traffic profile, không coi mọi interval im lặng là lỗi.

### 15.4. Application event listener

```java
@Component
public class KafkaContainerEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaContainerEvents.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Kafka listener idle: listenerId={}, idleMs={}",
                event.getListenerId(), event.getIdleTime());
    }

    @EventListener
    public void onNonResponsive(
            NonResponsiveConsumerEvent event) {
        log.warn(
                "Kafka consumer non-responsive: listenerId={}",
                event.getListenerId());
    }
}
```

Imports:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
```

**Không coi event là cơ chế recovery tự động:** một container bị block cần xác định nguyên nhân. Thêm logic `stop/start` ngay trong mọi event callback có thể tạo vòng rebalance vô hạn.

### 15.5. Consumer lag và alerting

Ví dụ policy tham khảo:

- Warning khi lag tăng liên tục 10 phút và throughput thấp hơn input rate.
- Critical khi thời gian dự kiến catch-up vượt deadline.
- Critical khi container stop ngoài ý muốn.
- Critical khi DLT publish thất bại.
- Warning khi DLT rate vượt baseline hoặc số pending replay tăng.
- Điều tra khi rebalance liên tục hoặc không có record consumed dù topic đang nhận dữ liệu.

Ngưỡng phụ thuộc workload; lag 10.000 records có thể nhỏ với event đơn giản nhưng rất lớn với xử lý 1 giây/event. Ưu tiên **lag time/ETA và business SLA**, không chỉ lag count.

---

## 16. Cấu hình bảo mật và secret

Factory cần consumer factory cấu hình security đúng. Ví dụ skeleton:

```yaml
spring:
  kafka:
    bootstrap-servers: "${KAFKA_BOOTSTRAP_SERVERS}"
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: "${KAFKA_SASL_JAAS_CONFIG}"
```

Các giá trị chỉ để minh họa; đường cấp secret phù hợp có thể là workload identity, mounted secret, vault hoặc service credential được quản lý. Không commit password/keytab/private key vào Git, không log JAAS configuration.

Production cần kiểm soát:

- ACL consume/topic, group join và DLT produce.
- TLS truststore/keystore và certificate rotation.
- Quyền DLT riêng nếu chứa payload lỗi hoặc exception headers nhạy cảm.
- Client/network policy chỉ được kết nối đến Kafka cluster cho phép.
- Timeout/retry authentication exception policy: sai quyền thường cần alert, không nên retry vô hạn.
- Config masking khi bật `logContainerConfig`; tránh in các secret-bearing properties ra log.
- Namespace group ID theo môi trường, không để dev cùng group với prod.
- Security of schema registry nếu dùng Avro/Protobuf.

### 16.1. Auth exception retry interval

`ContainerProperties.authExceptionRetryInterval` khi được cấu hình cho phép container thử lại sau authentication/authorization exception theo chu kỳ. Mặc định null thường coi những lỗi này là fatal và dừng container.

Chỉ bật khi quy trình credentials/ACL có khả năng khôi phục tạm thời và có alert rõ. Nếu mật khẩu sai vĩnh viễn, retry vô hạn không giúp gì và làm che tín hiệu cấu hình lỗi.

### 16.2. Missing topic

`missingTopicsFatal=true` phù hợp topic bắt buộc có provisioning trước deploy. Nếu ứng dụng tạo topic theo tenant on-demand hoặc subscribe pattern, behavior có thể khác; cần điều chỉnh policy để không gây crash-loop khi việc topic xuất hiện muộn là hợp lệ.

---

## 17. Test listener container factory

### 17.1. Unit test cấu hình

Kiểm tra các thuộc tính bạn chủ động set:

- Bean tên `ordersListenerContainerFactory` tồn tại.
- `batchListener=false`.
- `concurrency=3`.
- `AckMode.RECORD`.
- `pollTimeout=2000ms`.
- `CommonErrorHandler` là handler của orders.
- `observationEnabled=true` nếu đã yêu cầu.
- Consumer config có `enable.auto.commit=false`, StringDeserializer.
- Không vô tình áp policy payments lên orders.

Khi sử dụng Boot configurer, hãy test trong Spring application context thực thay vì chỉ `new OrdersListenerConfiguration()`, vì property binding và auto-wiring là phần quan trọng của behavior.

### 17.2. Spring Kafka EmbeddedKafka integration test

Dependency `spring-kafka-test` cung cấp `@EmbeddedKafka`. Một skeleton:

```java
@SpringBootTest
@EmbeddedKafka(
        partitions = 3,
        topics = {
                "orders.events",
                "orders.events.DLT"
        },
        bootstrapServersProperty =
                "spring.kafka.bootstrap-servers")
class OrdersListenerIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> template;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Test
    void containerIsRegistered() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-v1");

        assertNotNull(container);
    }
}
```

Imports tham khảo:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
```

Skeleton trên chỉ chứng minh container được đăng ký trong context. Để kiểm tra delivery, cần gửi record thật, đợi xử lý bất đồng bộ bằng latch/Awaitility/eventually assertion và query state bền vững. Không dùng `Thread.sleep(100)` rồi cho rằng broker đã xử lý xong.

### 17.3. Các test bắt buộc về reliability

| Scenario | Kết quả cần xác nhận |
|---|---|
| Hợp lệ | Business service được gọi, offset tiến sau success |
| Invalid JSON/domain | Không retry nhiều lần; record được publish DLT |
| DB transient fail hai lần rồi thành công | Tổng attempts đúng policy; không có DLT |
| DB luôn lỗi | Hết retry, DLT được publish, không mất record |
| DLT topic unavailable | Recovery thất bại, record không bị coi là xử lý thành công |
| Crash sau DB commit trước offset commit | Redelivery không tạo duplicate side effect |
| Consumer group thay đổi | Offset và replay behavior theo group mới |
| Tăng concurrency vượt partitions | Không có throughput tăng tuyến tính, số idle consumers có thể tăng |
| Listener processing vượt max.poll.interval.ms | Phát hiện rebalance/redelivery và xử lý idempotent |
| Ack trước khi business commit (negative test) | Có thể mất dữ liệu; chứng minh anti-pattern |
| Manual ack sau durable commit | Không ack khi service ném lỗi |
| Batch listener lỗi record thứ ba | `BatchListenerFailedException` trỏ đúng index, phần còn lại xử lý theo policy |
| Typed deserializer lỗi | ErrorHandlingDeserializer + DLT serializer xử lý raw payload |
| Container pause/resume | Lag có thể tăng khi pause và giảm sau resume |
| SIGTERM/redeploy | Graceful shutdown, redelivery an toàn |
| Auth/ACL sai | Container báo lỗi/stop theo policy, có alert |

### 17.4. Testcontainers

Với độ trung thực cao hơn, có thể dùng Kafka Testcontainers để kiểm thử trên broker thật chạy trong container, kết hợp Postgres Testcontainers nếu cần idempotency DB. Ưu điểm là chạy được tests với topic partitions, networking và broker behavior gần production hơn.

Testcontainers không thay thế load/rebalance tests trong staging, nhưng giúp bắt lỗi cấu hình bootstrap, topic provisioning, serializers và producer/consumer interaction.

### 17.5. Không giả lập KafkaConsumer bằng Mockito để chứng minh offset semantics

Mockito unit test giúp kiểm tra mapper/business code và bean configuration. Tuy nhiên offset commit, partition assignment, rebalance, DLT recoverer và Kafka transaction cần integration tests có broker. Một mock gọi `handle()` thành công không chứng minh listener container đã commit đúng lúc.

---

## 18. Kế hoạch triển khai production

### 18.1. Trước deploy

- Provision topic chính và DLT với partition count/retention đúng.
- Cấu hình ACL consume và produce DLT; kiểm tra security credentials.
- Quyết định group IDs theo ứng dụng và môi trường.
- Chốt consumer deserializer, message schema và compatibility.
- Chọn concurrency theo tổng partitions, số replicas và tài nguyên DB/CPU.
- Đặt `enable.auto.commit=false` nếu dùng container-managed commits.
- Chọn AckMode theo loại side effect và yêu cầu replay.
- Tính `max.poll.records × processing latency` so với `max.poll.interval.ms`.
- Định nghĩa retry/backoff, exception classification, DLT publish verification.
- Chuẩn bị idempotency store và replay DLT runbook.
- Bật monitoring lag, rebalance, error rate và health của container.

### 18.2. Trong deploy

- Khởi động một replica/canary và kiểm tra topic assignment.
- Quan sát số consumer con, concurrency và active partitions.
- Kiểm tra deserializer/schema với message thật.
- Theo dõi lag trend, processing latency, DLT count và exceptions.
- Xác nhận graceful shutdown khi pod bị thay.
- Nếu thấy retry storm hoặc DB overload, cân nhắc pause/throttle/thay policy có kiểm soát.

### 18.3. Sau deploy

- Xem committed offset và consumer lag theo group.
- Xác nhận không xuất hiện group ID mới ngoài ý muốn.
- Đối chiếu business record counts/side effects bằng ID, không chỉ dashboard lag.
- Kiểm tra DLT topic retention/ACL và replay tool.
- Ghi lại factory configuration version theo deployment để có bằng chứng khi điều tra.
- Định kỳ kiểm tra behavior khi broker failover, DB outage, pod crash và rebalance.

---

## 19. Runbook chẩn đoán lỗi cấu hình

### 19.1. Listener không nhận message

Kiểm tra theo thứ tự:

1. `@KafkaListener` đã được Spring scan và container đã start chưa?
2. `containerFactory` name có đúng bean tồn tại không?
3. Topic có tồn tại, tên có khớp environment không?
4. Consumer group ID đúng chưa?
5. Có committed offset và `auto.offset.reset` nào đang áp dụng?
6. Partition assignment có thuộc listener này không? Concurrency có quá cao không?
7. ACL/TLS/SASL có hoạt động không?
8. Deserializer có ném lỗi trước listener không?
9. Container có bị pause/stop hoặc retry lỗi liên tục không?

Không lập tức đổi group ID để “nhìn thấy message”: group mới có offset riêng và có thể đọc lại hàng triệu record hoặc bỏ qua lịch sử tùy `auto.offset.reset`.

### 19.2. Lag cao dù đã tăng concurrency

- So sánh tổng consumer con với số partitions.
- Kiểm tra một partition hot do producer key skew.
- Xem latency của DB/API và connection pool.
- Kiểm tra `max.poll.interval.ms`, rebalance và retry.
- Kiểm tra throttling CPU, GC pause, network.
- Đo tốc độ xử lý thực theo partition và định kỳ cân nhắc tăng partitions với tác động tới key routing/order.

Nếu topic chỉ có ba partitions, từ ba consumer lên chín consumer trong cùng group không tự làm throughput gấp ba.

### 19.3. Duplicate business writes

- Xác định topic/partition/offset và `eventId`.
- So sánh DB commit time với Kafka offset commit.
- Xem pod crash/rebalance/consumer group change.
- Kiểm tra idempotency transaction/key.
- Nếu record có offset khác nhưng cùng eventId, điều tra producer duplicate.
- Sửa business dedup/versioning thay vì chỉ đổi AckMode.

### 19.4. Poison message lặp vô hạn

- Xác định lỗi ở deserializer, converter hay listener.
- Kiểm tra `ErrorHandlingDeserializer` nếu lỗi trước listener.
- Xem `DefaultErrorHandler`, non-retryable classification và backoff.
- Xem DLT topic có đủ partitions/ACL không.
- Bật verify DLT send result và kiểm tra producer errors.
- Không dùng infinite retries cho lỗi validation cố định.
- Replay sau khi sửa root cause, tránh loop DLT → main → DLT.

### 19.5. Consumer liên tục rebalance

- Kiểm tra thời gian xử lý so với `max.poll.interval.ms`.
- Đo GC, CPU throttling, container restarts.
- Kiểm tra rolling deploy replica churn.
- Xem partition assignor, group membership.
- Xác nhận không có nhiều deploy cùng group ID ngoài ý muốn.
- Kiểm tra network/broker coordinator/heartbeat logs.

### 19.6. DLT không có message dù listener thất bại

- Không phải mọi lỗi đều được route DLT: có thể lỗi bị method nuốt.
- Có thể error handler khác được gắn với factory thực tế.
- Listener có thể transactional với after-rollback policy khác.
- DLT topic sai tên hoặc số partitions/ACL không phù hợp.
- Producer serializer không thể serialize raw byte[] của deserialization error.
- DLT send thất bại; nếu không verify send, tín hiệu có thể gây hiểu nhầm.
- Kiểm tra logs, retry count và offset behavior trước khi kết luận.

---

## 20. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Tạo custom factory nhưng quên `setConsumerFactory` | Listener không tạo được consumer | Dùng Boot configurer hoặc gắn ConsumerFactory rõ |
| Tạo factory mới và bỏ cấu hình Boot đã có | Mất converter/error handler/observation | `configurer.configure(...)` trước, override sau |
| Dùng sai bean name trong `containerFactory` | Listener dùng default không đúng policy hoặc startup lỗi | Chỉ định và test bean name |
| Nhầm `AckMode.BATCH` với `setBatchListener(true)` | Hiểu sai số lần gọi listener và retry | Tách ack timing với method payload mode |
| Bật `enable.auto.commit=true` rồi tin AckMode bảo vệ side effect | Offset commit có thể xảy ra trước business success | Để container quản lý offset commit |
| Chọn `MANUAL` nhưng quên gọi ack | Redelivery/lag không như dự kiến | Ack sau durable success và test |
| Ack trong `finally` | Mất record lỗi vì vẫn commit | Không ack khi business fail |
| `concurrency=12` cho topic 3 partitions | Nhiều consumer idle, tốn tài nguyên | Cân theo partitions × replicas |
| Cùng group ID cho hai feature muốn đọc độc lập | Hai feature chia partitions, không nhận đủ events | Dùng group riêng theo tính năng |
| Tăng `pollTimeout` để giới hạn business method | Không tác dụng lên thời gian xử lý | Timeout HTTP/DB/transaction riêng |
| `max.poll.records` quá lớn so với xử lý | Vượt poll interval, rebalance | Giảm poll batch, tối ưu processing |
| Retry mọi exception | Poison pill không bao giờ thoát | Phân loại permanent/transient |
| Infinite retry khi dependency outage | Lag tăng, không có chiến lược recovery | Bounded retry, circuit breaker/DLT/pause |
| DLT thiếu partition cần thiết | Recoverer không publish được | Provision đủ partitions hoặc đổi resolver |
| Không verify DLT publish | Có thể coi recover thành công dù DLT lỗi | `setFailIfSendResultIsError(true)` |
| DLT producer sai serializer | Không gửi được payload raw của record lỗi | Template/serializer phù hợp loại dữ liệu |
| Đổi group ID để “reset offset” | Replay/mất lịch sử ngoài ý muốn | Quản lý offset và backfill có chủ đích |
| Cho rằng AckMode.RECORD là exactly-once DB | Crash sau DB commit có thể redeliver | Idempotent business transaction |
| Bật transactions mà vẫn nuốt error | Có thể không rollback | Transaction-aware error handling |
| Chỉ nhìn consumer lag=0 | Business write có thể bị bỏ qua | Đối soát side effect và DLT |
| Không có quyền DLT produce | Poison message không recover | Kiểm tra ACL/retention/topic provisioning |
| Thay assignor giữa deploy mà không kiểm tra | Rebalance/assignment khác mong đợi | Rolling plan và integration test |
| Log toàn bộ payload/headers lỗi | Lộ PII/secret, log quá lớn | Structured metadata và masking |

---

## 21. Bài tập thực hành

### Bài 1 — Tự tạo default factory

Khởi tạo Spring Boot project có topic `events.demo` ba partitions. Chỉ dùng YAML để đặt group ID, `AckMode.RECORD`, concurrency 2 và `enable.auto.commit=false`. Kiểm tra Spring Boot tạo default factory và listener hoạt động khi không khai báo `containerFactory`.

### Bài 2 — Factory riêng

Tạo `criticalContainerFactory` với concurrency 1, `AckMode.MANUAL_IMMEDIATE` và error handler riêng. Một listener khác dùng `ordersListenerContainerFactory`. Thử thay annotation `containerFactory` và quan sát khác biệt behavior/offset commit.

### Bài 3 — Concurrency và partitions

Topic có bốn partitions, chạy một replica concurrency 1, 2, 4, 8. Sau đó chạy hai replicas concurrency 2. Ghi partition assignment thực tế, số consumer idle và throughput. Giải thích tại sao tăng từ 4 lên 8 threads không tự tăng tốc.

### Bài 4 — Blocking retry

Tạo listener ném `TemporaryStorageException` hai lần rồi thành công. Dùng `FixedBackOff(1000,2)`. Test số lần gọi, thời gian giữa attempts, không có DLT.

### Bài 5 — DLT

Tạo record JSON thiếu `orderId`. Cấu hình `addNotRetryableExceptions(InvalidOrderEventException.class)`; kiểm tra record vào DLT ngay, chứa topic/partition/offset gốc và không được xử lý tiếp như success.

### Bài 6 — DLT fail

Xóa DLT topic hoặc chặn ACL produce trong môi trường test. Bật verify send result. Quan sát handler không coi recovery đã thành công và kiểm tra cách record được redeliver. Không thực hiện thử nghiệm phá ACL trong production.

### Bài 7 — Ack timing

Cấu hình MANUAL_IMMEDIATE, tạo callback ghi DB. Cố ý ack **trước** DB commit để thấy rủi ro mất event. Sửa thành ack sau durable transaction và thêm idempotency cho redelivery.

### Bài 8 — max.poll.interval.ms

Giả lập xử lý mỗi record 2 giây, `max.poll.records=200` và `max.poll.interval.ms=300000`. Quan sát rebalance/lag. Giảm max poll records, thêm timeout và đo lại.

### Bài 9 — Batch listener

Chuyển listener audit sang `setBatchListener(true)`, truyền `List<ConsumerRecord<String,String>>`, ném `BatchListenerFailedException` tại index thứ ba. Kiểm chứng handler xử lý các record trước, record lỗi và record sau đúng policy.

### Bài 10 — Deserialization poison pill

Chuyển sang typed `JsonDeserializer<OrderEvent>` với `ErrorHandlingDeserializer`. Gửi payload sai JSON, kiểm tra DLT chứa raw payload ở định dạng serializer hỗ trợ và consumer không bị kẹt vô hạn.

### Bài 11 — Multi-replica và graceful shutdown

Chạy ba pods với concurrency 2 trên topic sáu partitions. Rolling restart một pod, đo group rebalance, lag, duplicate delivery và thời gian shutdown. Kiểm tra business idempotency.

### Bài 12 — Observability và runbook

Bật Micrometer Observation, collect consumer lag, DLT rate, retry, rebalance và idle/non-responsive events. Viết alert khi listener dừng ngoài ý muốn và khi DLT publish thất bại. Tạo runbook có câu lệnh kiểm tra topic, group và consumer assignment.

---

## 22. Tài liệu tham khảo

- [Spring Kafka — @KafkaListener Annotation](https://docs.spring.io/spring-kafka/reference/3.3/kafka/receiving-messages/listener-annotation.html): factory mặc định, containerFactory, concurrency, batch listener và các override.
- [Spring Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/3.3/kafka/receiving-messages/message-listener-container.html): `ConcurrentMessageListenerContainer`, ack modes, concurrency, rebalance và commit.
- [Spring Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/3.3/kafka/container-props.html): danh sách thuộc tính `ContainerProperties` và mặc định.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/3.3/kafka/annotation-error-handling.html): `CommonErrorHandler`, `DefaultErrorHandler`, retry, DLT và deserialization.
- [Spring Kafka — ErrorHandlingDeserializer](https://docs.spring.io/spring-kafka/reference/3.3/kafka/serdes.html): deserializer và xử lý lỗi decode.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/3.3/kafka/exactly-once.html): Kafka transactions và offset trong transaction.
- [Spring Kafka — @RetryableTopic](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic.html): retry topics, DLT và non-blocking retry.
- [Spring Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/3.3/kafka/events.html): idle, non-responsive và các event vận hành.
- [Spring Boot 3.4 — Apache Kafka Support](https://docs.spring.io/spring-boot/3.4/reference/messaging/kafka.html): `spring.kafka.*` và auto-configured factory.
- [Spring Boot 3.4 — ConcurrentKafkaListenerContainerFactoryConfigurer API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/kafka/ConcurrentKafkaListenerContainerFactoryConfigurer.html): giữ baseline của Boot khi định nghĩa factory riêng.
- [Spring Kafka 3.3 — DeadLetterPublishingRecoverer API](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/listener/DeadLetterPublishingRecoverer.html): DLT routing và xác minh publish.
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): `max.poll.records`, `max.poll.interval.ms`, group, fetch và offset settings.
- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): acks, idempotence và timeout của producer.

## 23. Tổng kết

`ConcurrentKafkaListenerContainerFactory` là trung tâm nối **Kafka consumer configuration** với **lifecycle, processing mode, ack/offset, retry/DLT và observability** của `@KafkaListener`. Một cấu hình đáng tin cậy không chỉ là `setConcurrency(3)`; nó phải đồng bộ với số partitions và replicas, khả năng chịu tải của downstream, timeout/poll budget, cách commit offset, chính sách phân loại lỗi và tính idempotent của business side effect.

Với ứng dụng đơn giản, hãy tận dụng factory được Spring Boot auto-configure từ `spring.kafka.*`. Với nhiều workload có độ tin cậy khác nhau, tạo các factory có tên rõ ràng bằng Boot configurer và override có kiểm soát. Sau đó kiểm chứng bằng integration tests có broker, đo consumer lag/rebalance/retry/DLT và diễn tập restart/pod crash. Khi những lựa chọn đó được thiết kế cùng nhau, listener sẽ có khả năng **xử lý lại an toàn, phát hiện lỗi đúng lúc và phục hồi có kiểm soát** trong quá trình triển khai và vận hành.

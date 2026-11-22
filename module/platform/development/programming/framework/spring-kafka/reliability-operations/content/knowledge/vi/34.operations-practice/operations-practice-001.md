# Xây consumer có retry và DLT trong Spring Kafka

## 1. Mục tiêu bài thực hành

Một consumer Spring Kafka nhận sự kiện cập nhật đơn hàng từ topic `orders.events`. Khi kết nối database bị gián đoạn trong vài giây, hệ thống nên **retry có giới hạn** để tránh làm mất công việc. Khi event không thể xử lý vì JSON sai hoặc thiếu mã đơn hàng, retry liên tục sẽ vô ích; consumer nên **đưa bản ghi sang Dead Letter Topic (DLT)** để điều tra hoặc xử lý lại có kiểm soát.

Nếu không có chiến lược này, một record lỗi có thể khiến partition dừng mãi ở một offset, hoặc một error handler quá rộng sẽ bỏ qua bản ghi mà không lưu được bằng chứng. Ngược lại, retry quá nhiều có thể làm Kafka lag tăng, quá tải database, gây redelivery và tạo tác động nghiệp vụ trùng.

Bài **“Xây consumer có retry và DLT”**, thuộc nhóm **Thực hành vận hành** của module **Spring Kafka Reliability Operations**, hướng dẫn một luồng xử lý có khả năng phục hồi:

```text
                      Apache Kafka
                    topic: orders.events
                            |
                            v
                      @KafkaListener
                            |
                            v
                   Parse + validate event
                            |
                    +-------+-------+
                    |               |
                 Hợp lệ         Không hợp lệ
                    |               |
                    v               v
             Business service   Non-retryable
                    |               |
             +------+-----+         |
             |            |         |
          Thành công   Lỗi tạm thời  |
             |            |         |
             v            v         |
          Offset      Retry + backoff
          tiến tới         |
                         +-- Thành công --> offset tiến tới
                         |
                         +-- Hết retry ---+
                                          |
                                          v
                            DeadLetterPublishingRecoverer
                                          |
                                          v
                                orders.events.DLT
                                          |
                                  Audit + cảnh báo
                                  + replay có kiểm soát
```

Sau bài học, bạn có thể:

1. Cấu hình Spring Boot 3.x / Spring Kafka 3.x để đọc và ghi Kafka an toàn.
2. Xây `@KafkaListener` xử lý lỗi nghiệp vụ và lỗi hạ tầng theo nhóm khác nhau.
3. Dùng `DefaultErrorHandler`, `FixedBackOff` và `DeadLetterPublishingRecoverer` để retry có giới hạn rồi chuyển DLT.
4. Hiểu quan hệ giữa thành công của handler, DLT publish và việc commit consumer offset.
5. Bảo vệ business side effect bằng transaction và idempotency.
6. Tách consumer DLT, tránh tạo vòng chuyển tiếp DLT → DLT vô hạn.
7. Viết integration test với embedded Kafka và thiết kế test trên database/broker tương thích production.
8. Thiết lập metric, cảnh báo, retention và quy trình replay an toàn.

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Kafka 3.x, PostgreSQL và JUnit 5. API và hành vi cụ thể có thể khác theo các bản Spring Kafka/Kafka client; cần kiểm thử trên phiên bản thực tế trước khi vận hành production.

## 2. Chọn chiến lược: retry tại consumer hay retry qua topic?

Trong Spring Kafka có hai hướng thường gặp:

| Chiến lược | Cơ chế | Lợi thế | Đánh đổi |
| --- | --- | --- | --- |
| **Blocking retry** | `DefaultErrorHandler` thử lại record trong phạm vi container, có thể seek/resubmit theo policy | Cấu hình tập trung, dễ giữ thứ tự theo partition trong trường hợp đơn giản | Partition/consumer có thể chậm hoặc bị chặn trong thời gian retry |
| **Non-blocking retry** | `@RetryableTopic` chuyển record qua một hoặc nhiều retry topic với lịch xử lý trì hoãn | Không để lỗi của một record giữ partition nguồn quá lâu | Tăng topic/consumer topology, cần quản lý thứ tự và offset ở các topic riêng |
| **DLT** | Gửi record không thể xử lý tới dead-letter topic | Bảo toàn bằng chứng lỗi và tiếp tục luồng chính khi recovery hợp lệ | Cần storage, alert, quyền truy cập và quy trình xử lý sau DLT |

Bài thực hành chính chọn **blocking retry + DLT**, vì có thể mô tả rõ ràng một luồng end-to-end với `DefaultErrorHandler`.

Ở phần cuối, bài sẽ giới thiệu cách chuyển sang `@RetryableTopic` khi một poison record không được phép làm nghẽn partition quá lâu. **Không bật đồng thời hai lớp retry mà chưa tính tổng số attempts**, vì một record có thể bị thử lại ở nhiều tầng.

### Phân biệt tên gọi

- **Retry**: một operation gặp lỗi và được thử lại.
- **Recoverer**: thành phần được gọi khi lỗi không còn được retry theo policy, chẳng hạn publish record vào DLT.
- **DLT**: topic chứa các record cần điều tra/xử lý ngoài đường tiêu thụ chính.
- **Replay**: thao tác chủ động đưa một record từ DLT trở lại pipeline xử lý.
- **Skip**: chấp nhận cho nguồn tiến tiếp sau một record lỗi theo chính sách đã định. Việc DLT publish thành công có thể là điều kiện để error handler xem record nguồn đã được recover, nhưng **không** có nghĩa nghiệp vụ của record ấy thành công.

## 3. Thiết kế kịch bản nghiệp vụ

Sự kiện đầu vào:

```json
{
  "eventId": "evt-20261115-001",
  "orderId": "order-42",
  "version": 7,
  "status": "PAID"
}
```

Topic nguồn là `orders.events` với 3 partition. Topic lỗi là `orders.events.DLT` với **ít nhất 3 partition** nếu muốn giữ lại partition number của source record.

Chúng ta giả định ba loại kết quả:

| Trường hợp | Exception/điều kiện | Chính sách |
| --- | --- | --- |
| Sự kiện hợp lệ, DB sẵn sàng | Không ném lỗi | Lưu nghiệp vụ, container quản lý commit offset |
| DB mất kết nối tạm thời | `TransientDataAccessException` hoặc exception tạm thời do ứng dụng định nghĩa | Retry với backoff, hết giới hạn thì DLT |
| JSON sai, eventId/orderId rỗng, version không hợp lệ | `InvalidOrderEventException` | Không retry, chuyển DLT ngay |
| Lỗi ngoài các nhóm đã phân loại | Exception khác | Phải có policy rõ: fail/retry/DLT theo mức độ; không mặc định lỗi lập trình là transient |
| DLT broker/topic không khả dụng | Lỗi publish DLT | Không nên xác nhận record nguồn đã được xử lý; phải có cảnh báo và recovery |

Ở ví dụ này, **sự kiện không hợp lệ vẫn có giá trị để điều tra**, nên được gửi DLT thay vì chỉ log rồi bỏ qua.

### Số lần xử lý phải được định nghĩa rõ

Ta sử dụng:

```text
Initial delivery: 1
Retries after failure: 2
Maximum handler invocations in simple case: 3

Backoff giữa các retry: 1 giây
```

Đây là diễn giải của `FixedBackOff(1000L, 2L)`: **hai lần retry sau lần xử lý ban đầu**, trong kịch bản thông thường không có thay đổi assignment/rollback/rebalance. Không nhầm tham số thứ hai với “tổng số attempts”.

Với restart/rebalance, số lần xử lý thực tế có thể lớn hơn vì record chưa commit có thể được giao lại. Vì vậy business handler vẫn phải idempotent.

## 4. Cấu trúc dự án

Một cấu trúc thư mục phù hợp:

```text
order-consumer/
├── build.gradle
├── src/
│   ├── main/
│   │   ├── java/com/example/orderconsumer/
│   │   │   ├── OrderConsumerApplication.java
│   │   │   ├── config/KafkaConsumerConfiguration.java
│   │   │   ├── config/KafkaTopicConfiguration.java
│   │   │   ├── model/OrderEvent.java
│   │   │   ├── consumer/OrderEventListener.java
│   │   │   ├── consumer/OrderDltListener.java
│   │   │   ├── service/OrderProjectionService.java
│   │   │   ├── service/DltAuditService.java
│   │   │   └── error/
│   │   │       ├── InvalidOrderEventException.java
│   │   │       └── TemporaryOrderDependencyException.java
│   │   └── resources/
│   │       ├── application.yml
│   │       └── db/migration/V1__order_projection.sql
│   └── test/
│       └── java/com/example/orderconsumer/
│           ├── OrderEventListenerTest.java
│           └── OrderKafkaIntegrationTest.java
```

Các class được trình bày theo phần và có thể điều chỉnh package/import cho dự án. Các đoạn code phía dưới là mẫu thực hành; một hệ thống sản xuất cần bổ sung xác thực Kafka, schema registry, quan sát, migration và security policy.

## 5. Dependency cần thiết

Với một dự án Gradle sử dụng Spring Boot plugin/BOM tương thích:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'

    // Dùng khi muốn integration test PostgreSQL bằng container.
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot quản lý versions của nhiều dependency qua BOM; chọn một Spring Boot 3.x phù hợp với Spring Kafka 3.x của ứng dụng. Không tự ghép các versions bất kỳ mà chưa kiểm tra compatibility.

Các nhóm thư viện:

- `spring-kafka`: listener container, Kafka producer/consumer, common error handler, recoverer.
- `spring-boot-starter-jdbc`: `JdbcTemplate` và transaction manager cho side effect ở database.
- `spring-boot-starter-actuator`: nền tảng health/metrics; muốn có metric đầy đủ có thể cần cấu hình Micrometer/Prometheus.
- `spring-kafka-test`: broker test và KafkaTestUtils.
- `Testcontainers`: khi cần Kafka/PostgreSQL phù hợp môi trường production và fault injection tách process.

Không dùng `spring-retry` và `@Retryable` như một giải pháp ngầm thay cho `DefaultErrorHandler` nếu mục tiêu là quản lý record/offset của Kafka. Chúng hoạt động ở những tầng khác nhau và có thể tạo retry lồng nhau.

## 6. Cấu hình Kafka trong application.yml

Ví dụ sử dụng String key/value để **parse JSON trong listener**. Cách này giúp lỗi JSON trong ví dụ được phân loại thành lỗi nghiệp vụ không retryable, thay vì thất bại ở tầng Kafka deserializer trước khi listener được gọi.

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    consumer:
      group-id: ${KAFKA_GROUP_ID:order-projection-v1}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      max-poll-records: 100
      properties:
        isolation.level: read_committed

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all

    listener:
      ack-mode: record
      concurrency: 1

app:
  kafka:
    orders:
      topic: ${ORDERS_TOPIC:orders.events}
      dlt-topic: ${ORDERS_DLT_TOPIC:orders.events.DLT}

logging:
  level:
    org.springframework.kafka: INFO
    com.example.orderconsumer: INFO
```

**Giải thích một số lựa chọn:**

- `enable-auto-commit=false`: để listener container kiểm soát việc commit offsets theo ack mode.
- `ack-mode: record`: container xử lý tiến độ theo record sau khi handler xử lý thành công hoặc record đã được error handler recover theo cấu hình.
- `concurrency: 1`: một Kafka consumer thread trong mỗi instance cho bài học; nếu tăng concurrency, có thể có nhiều consumer cùng group và nhiều partition được xử lý song song.
- `max-poll-records: 100`: giới hạn số bản ghi trả về trên một lần poll; cần phối hợp với thời gian xử lý và `max.poll.interval.ms`.
- `auto-offset-reset: earliest`: chỉ có ý nghĩa khi group chưa có committed offset hợp lệ hoặc offset ngoài phạm vi retention; không buộc group đang chạy đọc lại từ đầu.
- `isolation.level: read_committed`: consumer đọc những record từ producer transaction đã commit nếu nguồn sử dụng transactional production. Nó không làm JDBC side effect trở thành exactly-once.
- `acks: all`: producer chờ acknowledgments theo policy Kafka; production còn cần xét min.insync.replicas, replication, delivery timeout và lỗi producer.

Lưu ý: cấu hình security (TLS, SASL, ACL, secret) cần được bổ sung theo cluster. Không commit password hoặc API key vào source.

## 7. Chuẩn bị source topic và DLT

Cơ chế `DeadLetterPublishingRecoverer` dưới đây sẽ gửi record lỗi tới **cùng partition number** trên topic DLT:

```text
orders.events-0  -> orders.events.DLT-0
orders.events-1  -> orders.events.DLT-1
orders.events-2  -> orders.events.DLT-2
```

Đây là lựa chọn tiện cho truy vết. Nó đòi hỏi topic DLT có ít nhất số partition tương ứng với source. Nếu DLT có ít hơn, publish vào partition không tồn tại sẽ thất bại.

Với môi trường local/test, có thể tạo topic bằng `NewTopic`:

```java
package com.example.orderconsumer.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic(
            @Value("${app.kafka.orders.topic}")
                String topicName) {

        return TopicBuilder.name(topicName)
            .partitions(3)
            .replicas(1)
            .build();
    }

    @Bean
    NewTopic ordersDltTopic(
            @Value("${app.kafka.orders.dlt-topic}")
                String topicName) {

        return TopicBuilder.name(topicName)
            .partitions(3)
            .replicas(1)
            .build();
    }
}
```

Spring Kafka có thể dùng KafkaAdmin để tạo các `NewTopic` khi có quyền và cấu hình phù hợp. Trong production, thường nên tạo/manage topics bằng Terraform, operator, CLI hoặc quy trình quản trị Kafka, vì topic DLT cần policy bảo mật, retention, replication và partition count riêng.

**Không dùng replication factor 1 trong production nếu cần chịu lỗi broker.** Ví dụ `replicas(1)` chỉ để local. Khi source topic tăng số partition, phải kiểm tra DLT có đủ partition cho chiến lược giữ nguyên partition number.

### Có nên dùng cùng retention cho source và DLT?

Không mặc định. DLT phục vụ điều tra/replay nên thời gian lưu có thể khác source, tùy yêu cầu pháp lý, dung lượng, bảo mật và quy trình xử lý. Retention quá ngắn có thể làm mất record lỗi trước khi người vận hành xử lý; quá dài có thể lưu PII không cần thiết.

## 8. Định nghĩa event và exception

Record của ứng dụng:

```java
package com.example.orderconsumer.model;

public record OrderEvent(
        String eventId,
        String orderId,
        long version,
        String status) {
}
```

Hai exception minh họa:

```java
package com.example.orderconsumer.error;

public class InvalidOrderEventException extends RuntimeException {
    public InvalidOrderEventException(String message) {
        super(message);
    }

    public InvalidOrderEventException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

```java
package com.example.orderconsumer.error;

public class TemporaryOrderDependencyException
        extends RuntimeException {

    public TemporaryOrderDependencyException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Chính sách lỗi:

- `InvalidOrderEventException`: lỗi **không kỳ vọng tự hết khi thử lại cùng payload**; đi DLT ngay.
- `TemporaryOrderDependencyException`: lỗi **có thể hồi phục** do hệ thống đích tạm thời không sẵn sàng; retry có giới hạn.
- `TransientDataAccessException` của Spring Data Access: ví dụ nhóm lỗi JDBC transient; cũng có thể retry.

Cần tránh loại exception quá rộng như `Exception.class` vì lỗi lập trình hoặc cấu hình cũng sẽ bị thử lại không cần thiết. Khi dùng exception của HTTP client, hãy phân loại dựa trên mã lỗi và timeout thực tế, thay vì mặc định mọi HTTP error đều transient.

## 9. Viết listener đọc và xác thực sự kiện

Listener nhận raw JSON string, parse qua Jackson và chuyển cho business service. Lỗi parse/validation được phân loại rõ trước khi đưa vào error handler.

```java
package com.example.orderconsumer.consumer;

import com.example.orderconsumer.error.InvalidOrderEventException;
import com.example.orderconsumer.model.OrderEvent;
import com.example.orderconsumer.service.OrderProjectionService;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventListener.class);

    private final ObjectMapper mapper;
    private final OrderProjectionService service;

    public OrderEventListener(
            ObjectMapper mapper,
            OrderProjectionService service) {
        this.mapper = mapper;
        this.service = service;
    }

    @KafkaListener(
        id = "order-projection-listener",
        topics = "${app.kafka.orders.topic}",
        groupId = "${spring.kafka.consumer.group-id}",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void onMessage(
            ConsumerRecord<String, String> record) {

        OrderEvent event;

        try {
            event = mapper.readValue(
                record.value(), OrderEvent.class
            );
        } catch (JsonProcessingException ex) {
            throw new InvalidOrderEventException(
                "Malformed order event JSON", ex
            );
        }

        validate(event);

        // Service phải có idempotency/transaction phù hợp.
        service.apply(event);

        log.debug(
            "event=orders.processed topic={} partition={} " +
            "offset={} eventId={}",
            record.topic(),
            record.partition(),
            record.offset(),
            event.eventId()
        );
    }

    private static void validate(OrderEvent event) {
        if (event == null ||
                event.eventId() == null ||
                event.eventId().isBlank() ||
                event.orderId() == null ||
                event.orderId().isBlank() ||
                event.version() < 1 ||
                event.status() == null ||
                event.status().isBlank()) {

            throw new InvalidOrderEventException(
                "Missing or invalid order event fields"
            );
        }
    }
}
```

**Không catch mọi RuntimeException rồi trả về bình thường.** Nếu service ném exception nhưng listener nuốt lỗi, container có thể cho offset tiến tới theo ack mode dù business operation chưa thành công.

**Không log toàn bộ raw payload hoặc exception message từ nguồn bên ngoài** nếu message chứa PII, token hoặc thông tin nhạy cảm. Log correlation có thể dùng eventId/key sau khi đã kiểm duyệt; với JSON parse lỗi, chỉ cần topic/partition/offset và loại exception.

### Một lưu ý về ordering

Kafka đảm bảo thứ tự theo offset **trong từng partition** khi tiêu thụ tuần tự, không đảm bảo thứ tự tổng thể giữa partition. Nếu mỗi order phát nhiều version, hãy chọn event key ổn định theo `orderId` để các event cùng order thường đến cùng partition (theo partitioner và số partition không đổi), đồng thời writer phải có kiểm soát version để tránh event cũ ghi đè mới.

## 10. Ghi dữ liệu nghiệp vụ theo cách idempotent

Một record có thể được xử lý lại sau retry/rebalance/crash. Với Kafka at-least-once, business side effect cần được bảo vệ độc lập với số lần listener được gọi.

Ví dụ PostgreSQL:

```sql
CREATE TABLE processed_order_event (
    projection_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (projection_name, event_id)
);

CREATE TABLE order_projection (
    order_id VARCHAR(120) PRIMARY KEY,
    event_version BIGINT NOT NULL,
    current_status VARCHAR(40) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Dùng `JdbcTemplate` trong một transaction:

```java
package com.example.orderconsumer.service;

import com.example.orderconsumer.model.OrderEvent;

import org.springframework.dao.TransientDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderEvent event) {

        int inserted = jdbc.update(
            """
            INSERT INTO processed_order_event (
                projection_name, event_id
            ) VALUES ('orders-projection', ?)
            ON CONFLICT (projection_name, event_id)
            DO NOTHING
            """,
            event.eventId()
        );

        if (inserted == 0) {
            // Đã áp dụng event này ở một delivery trước.
            return;
        }

        jdbc.update(
            """
            INSERT INTO order_projection (
                order_id, event_version, current_status
            ) VALUES (?, ?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET
                event_version = EXCLUDED.event_version,
                current_status = EXCLUDED.current_status,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_projection.event_version
                < EXCLUDED.event_version
            """,
            event.orderId(),
            event.version(),
            event.status()
        );
    }
}
```

Trong ví dụ này:

1. Marker và update projection dùng cùng datasource và transaction manager.
2. Nếu xảy ra exception trước commit, cả hai statement có thể rollback cùng nhau.
3. Nếu DB commit thành công nhưng Kafka offset chưa commit, một delivery lặp sẽ gặp marker đã có và không tạo tác động trùng.
4. Điều kiện version ngăn event version thấp hơn ghi đè trạng thái mới.
5. Marker chỉ xác nhận sự kiện đã đi qua logic ứng dụng; nó không chứng minh mọi side effect bên ngoài DB đã thành công.

**Lưu ý:** Nếu event cần thực hiện tác động ngoài transaction như gửi email, thanh toán hoặc publish Kafka, phải có thêm outbox/idempotency của hệ thống đích. Transaction của PostgreSQL không tự bao phủ HTTP/Kafka offset commit.

Nếu database yêu cầu xử lý mọi phiên bản theo thứ tự liên tục, chỉ kiểm tra `version > current` là chưa đủ: còn cần phát hiện gap, thiết kế replay và trạng thái chờ.

## 11. Cấu hình DefaultErrorHandler và DeadLetterPublishingRecoverer

Đây là phần trọng tâm.

Một `DefaultErrorHandler` nhận exception của listener, thử lại theo `BackOff`, rồi gọi recoverer khi không còn retry. `DeadLetterPublishingRecoverer` publish record lỗi tới topic DLT.

```java
package com.example.orderconsumer.config;

import com.example.orderconsumer.error.InvalidOrderEventException;
import com.example.orderconsumer.error.TemporaryOrderDependencyException;

import org.apache.kafka.common.TopicPartition;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    CommonErrorHandler orderCommonErrorHandler(
            KafkaTemplate<String, String> kafkaTemplate,
            @Value("${app.kafka.orders.dlt-topic}")
                String dltTopic) {

        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) -> new TopicPartition(
                    dltTopic, record.partition()
                )
            );

        // Publish DLT lỗi thì không nên coi record đã recover.
        recoverer.setFailIfSendResultIsError(true);

        // 2 retries sau lần delivery ban đầu, cách 1 giây.
        FixedBackOff backOff =
            new FixedBackOff(1_000L, 2L);

        DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

        // Lỗi dữ liệu dự kiến không tự hết khi retry.
        handler.addNotRetryableExceptions(
            InvalidOrderEventException.class
        );

        // Các nhóm lỗi tạm thời được phép retry.
        handler.addRetryableExceptions(
            TemporaryOrderDependencyException.class,
            TransientDataAccessException.class
        );

        return handler;
    }
}
```

### Về cách phân loại exception

`DefaultErrorHandler` có cơ chế phân loại exception mặc định của Spring Kafka, bao gồm một số exception dạng fatal không được retry, ví dụ lỗi serialization/deserialization/conversion phù hợp. `addRetryableExceptions` bổ sung các loại retryable và `addNotRetryableExceptions` đánh dấu loại không retryable.

**Đừng hiểu việc gọi `addRetryableExceptions(...)` là đã thiết lập allowlist loại trừ mọi exception còn lại.** Mặc định của error handler có thể cho retry những exception khác không thuộc danh sách fatal. Khi muốn policy “chỉ nhóm transient được retry”, phải kiểm tra cấu hình classification/default false của phiên bản Spring Kafka đang dùng, hoặc bọc lỗi tại biên service thành một tập exception được kiểm soát và test rõ các trường hợp ngoài nhóm.

### Về DLT publication

Recoverer ở ví dụ gán **topic DLT cố định** và giữ `record.partition()`. Source và DLT cần có partition tương ứng. Với producer `StringSerializer`, source record ở đây được deserialize thành `String`, nên DLT KafkaTemplate cũng gửi string an toàn.

`setFailIfSendResultIsError(true)` yêu cầu recoverer xem lỗi gửi DLT là failure thay vì lặng lẽ kết luận đã publish thành công. Thời gian chờ/điều kiện xác nhận còn phụ thuộc KafkaTemplate, producer và phiên bản Spring Kafka. Production cần điều chỉnh delivery timeout, acks, retries và quan sát publish error.

Một recoverer có thể đính kèm header về source topic/partition/offset và exception class/message. Cần tránh phát tán PII qua exception message, DLT payload và headers.

## 12. Gắn error handler vào listener container factory

Spring Boot có thể nhận `CommonErrorHandler` bean trong cấu hình phù hợp, nhưng để thấy rõ đường wiring, ví dụ tạo factory tên `kafkaListenerContainerFactory`:

```java
package com.example.orderconsumer.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class KafkaListenerFactoryConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            CommonErrorHandler orderCommonErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<
                String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(
            orderCommonErrorHandler
        );

        factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD
        );

        factory.setConcurrency(1);
        return factory;
    }
}
```

Tên bean `kafkaListenerContainerFactory` trùng với tên mà `@KafkaListener` có thể dùng mặc định; listener ở phần trước cũng chỉ định tên này tường minh.

**Cần thống nhất cách quản lý factory.** Nếu dự án đã có Spring Boot `ConcurrentKafkaListenerContainerFactoryConfigurer` và các customizer riêng, việc tự dựng factory phải bảo đảm những tùy chọn security, observation, converter, interceptors và consumer properties cần thiết vẫn được áp dụng. Có thể dùng Boot configurer để kế thừa cấu hình chuẩn rồi gắn error handler.

### Lifecycle của một record lỗi

Ví dụ handler nhận record ở source offset 105:

```text
orders.events partition 2 offset 105
                 |
                 v
           Listener attempt 1
                 |
          transient exception
                 |
            backoff 1s
                 |
                 v
           Listener attempt 2
                 |
          transient exception
                 |
            backoff 1s
                 |
                 v
           Listener attempt 3
                 |
          transient exception
                 |
                 v
      DeadLetterPublishingRecoverer
                 |
                 v
    orders.events.DLT partition 2
                 |
           publish succeeds?
           /             \
         Yes              No
         |                 |
         v                 v
    Handler recovery   Recovery failure,
    completed          source must not
         |             silently advance
         v
    Container may
    commit source
    offset under
    configured policy
```

**DLT không phải nghiệp vụ thành công.** Consumer group có thể tiến qua offset 105 sau khi message được recover thành DLT, nhưng một luồng xử lý riêng vẫn phải giải quyết nội dung thất bại.

Không nên suy ra số commit chính xác từ sơ đồ; commit timing phụ thuộc ack mode, container error-handling, transaction và cấu hình producer/consumer.

## 13. Cách Kafka offset tương tác với retry và DLT

Có bốn sự kiện khác nhau:

1. Kafka consumer poll một record.
2. Business handler xử lý record và có thể commit database.
3. Recoverer có thể gửi record lỗi tới DLT.
4. Container commit offset của consumer group.

Chúng **không mặc định là một transaction nguyên tử**.

| Tình huống | Business DB | Kafka offset nguồn | Hệ quả |
| --- | --- | --- | --- |
| Listener thành công, offset commit thành công | Đã cập nhật | Tiến lên | Xử lý bình thường |
| DB commit, process chết trước offset commit | Đã cập nhật | Chưa tiến | Có thể redeliver; cần idempotency |
| Listener thất bại, retry thành công | Tùy transaction, cuối cùng hoàn tất | Tiến khi xử lý thành công theo policy | Không cần DLT |
| Retry cạn, DLT publish thành công, source offset commit thành công | Business chưa hoàn tất | Tiến lên | Record đang chờ ở DLT |
| DLT publish thất bại | Business chưa hoàn tất | Không được xác nhận như đã recover | Cần retry/error alert và tránh mất record |
| DLT publish thành công nhưng process chết trước source offset commit | Business chưa hoàn tất | Có thể chưa tiến | Có thể gửi DLT trùng khi replay từ source |

Điểm cuối rất quan trọng: **DLT cũng có thể có duplicate records** khi có lỗi ở ranh giới publish/offset commit. Hệ thống audit/replay DLT nên có khóa chống trùng, ví dụ kết hợp group/service, source topic, partition, offset hoặc business event ID.

### Có cần dùng Kafka transactions?

Nếu cần exactly-once trong pipeline consume → transform → produce hoàn toàn trên Kafka, có thể dùng Kafka transaction và producer transaction manager với offset coordination phù hợp. Nhưng việc đồng bộ với PostgreSQL, HTTP hay email là vấn đề riêng; transactions trên Kafka không mặc định biến mọi side effect ngoài Kafka thành exactly-once.

Bài thực hành chọn mô hình dễ hiểu: **at-least-once + JDBC idempotent + DLT có publish confirmation**.

## 14. Vì sao lỗi deserialization cần cách xử lý riêng?

Trong ví dụ chính, Kafka value là String, nên JSON parse nằm trong listener. Nhưng nhiều ứng dụng cấu hình thẳng:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
```

Nếu JSON không deserialize được, exception có thể xảy ra **trước khi `@KafkaListener` nhận event**. Khi đó logic `try/catch` trong listener không chạy.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để đưa thông tin lỗi deserialization vào tầng container/error handler.

Ví dụ cấu hình khái niệm:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orderconsumer.model.OrderEvent
        spring.json.trusted.packages: com.example.orderconsumer.model
```

Đối với cấu hình này, listener nhận `OrderEvent` trực tiếp nếu dữ liệu hợp lệ. Khi có deserialization exception, `ErrorHandlingDeserializer` cung cấp thông tin để error handler xử lý thay vì để lỗi lặp vô tận ở poll.

**Lưu ý với DLT serialization:** đối với failed deserialization, recoverer có thể cần publish **byte[] nguyên gốc**, trong khi bản ghi thành công có kiểu `OrderEvent`. Producer DLT phải có serializer hỗ trợ kiểu dữ liệu thực sự được gửi; có thể sử dụng `DelegatingByTypeSerializer` với mapping `byte[].class -> ByteArraySerializer` và `OrderEvent.class -> JsonSerializer`, hoặc thiết kế recoverer/producer tách biệt. Nếu vẫn dùng KafkaTemplate với `StringSerializer` trong ví dụ chính, không được mặc định nó sẽ ghi được object/byte[] của cấu hình typed-deserializer.

Ngoài ra, cấu hình trusted packages, schema compatibility và việc preserve original payload phải được quản lý an toàn; không dùng wildcard package trong môi trường không tin cậy chỉ để tránh lỗi deserialize.

## 15. DLT record gồm những gì?

Một bản ghi trong `orders.events.DLT` thường giữ key và value gốc của source record, đồng thời có thể mang headers về nguồn lỗi, như:

- Original topic.
- Original partition.
- Original offset.
- Original consumer group (tùy phiên bản/cấu hình).
- Exception class, cause và message (theo cấu hình recoverer).
- Timestamp và một số metadata liên quan.

Ví dụ mô tả:

```text
DLT topic:     orders.events.DLT
DLT partition: 2
DLT key:       order-42
DLT value:     {"eventId":"evt-42","orderId":"order-42",...}

Headers (minh họa):
  originalTopic     = orders.events
  originalPartition = 2
  originalOffset    = 105
  exceptionClass    = TemporaryOrderDependencyException
```

Tên header vật lý cụ thể phải dùng constants/API của Spring Kafka version đang chạy, ví dụ các constant trong `KafkaHeaders`. Không parse một tên header tự đặt nếu chưa có producer ghi header đó.

### Bảo mật dữ liệu DLT

DLT là **một bản sao dữ liệu có thể chứa payload lỗi và metadata exception**. Hãy áp dụng:

1. Kafka ACL riêng, chỉ cấp cho những service/nhân sự cần điều tra.
2. Retention hợp lý, tránh lưu PII vô thời hạn.
3. Log redaction và secret masking ở error handler/DLT consumer.
4. Quy tắc mã hóa/bảo vệ dữ liệu giống hoặc nghiêm hơn topic nguồn.
5. Audit ai truy xuất/replay hoặc tải payload DLT.
6. Giới hạn nội dung exception message để tránh đưa SQL, credential hay raw HTTP body vào header.

## 16. Có nên tạo @KafkaListener để tự động đọc DLT?

Có thể, nhưng **đừng để DLT consumer tự động chuyển lỗi sang một DLT khác không giới hạn**.

Một handler DLT nên làm nhiệm vụ **audit, quarantine và cảnh báo**, không mặc định replay vào source ngay khi đọc:

```text
orders.events.DLT
        |
        v
   DLT audit consumer
        |
        v
  Persist error case / alert
        |
        v
  Manual review or approved replay
```

Ví dụ class tiêu thụ DLT:

```java
package com.example.orderconsumer.consumer;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderDltListener {

    private final DltAuditService auditService;

    public OrderDltListener(DltAuditService auditService) {
        this.auditService = auditService;
    }

    @KafkaListener(
        id = "orders-dlt-audit",
        topics = "${app.kafka.orders.dlt-topic}",
        groupId = "orders-dlt-audit-group",
        containerFactory = "dltListenerContainerFactory"
    )
    public void onDlt(
            ConsumerRecord<String, String> record) {

        auditService.recordFailure(record);
    }
}
```

**Quan trọng:** `dltListenerContainerFactory` ở đây phải được cấu hình **riêng**, với error policy có giới hạn và không tái sử dụng recoverer đẩy vào `orders.events.DLT` rồi tiếp tục sinh `orders.events.DLT.DLT` hoặc lặp lại chính record lỗi. Nếu audit DB đang lỗi, chính DLT audit consumer cần retry/backoff có giới hạn và cảnh báo, giữ record chưa ack; không nên “nuốt” lỗi rồi commit.

Nếu chưa thiết kế xong đường audit, **đừng bật DLT listener**. Vẫn có thể vận hành DLT bằng monitoring/AdminClient và công cụ kiểm tra thủ công trong thời gian đầu. DLT hoạt động độc lập với việc có consumer DLT hay không.

### Mẫu lưu audit DLT

```sql
CREATE TABLE order_dlt_case (
    source_topic VARCHAR(200) NOT NULL,
    source_partition INTEGER NOT NULL,
    source_offset BIGINT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    failure_type VARCHAR(200),
    state VARCHAR(30) NOT NULL DEFAULT 'NEW',
    reviewer VARCHAR(100),
    PRIMARY KEY (
        source_topic, source_partition, source_offset
    )
);
```

Khóa theo tọa độ record nguồn giúp không tạo nhiều case cho cùng source offset nếu DLT có duplicate. Nếu các hệ thống/group khác nhau dùng chung bảng, bổ sung consumer projection/group vào khóa theo chính sách nghiệp vụ.

Không dùng **DLT offset** làm identity chính của sự kiện nguồn: một source record có thể xuất hiện tại nhiều DLT offsets qua những lần recover lặp.

## 17. Giám sát retry và DLT bằng metric và log

Các chỉ số đáng theo dõi:

| Metric/sự kiện | Ý nghĩa | Gợi ý cảnh báo |
| --- | --- | --- |
| Consumer lag | Nguồn đang chậm hoặc bị chặn tại lỗi | Lag tăng liên tục, vượt SLA |
| Handler error rate | Tỷ lệ exception trên deliveries | Tăng bất thường theo loại lỗi |
| Retry attempts | Hạ tầng đang thiếu ổn định | Retry rate cao dù DLT chưa tăng |
| DLT publish rate | Số record không thể xử lý theo policy | Bất kỳ event critical nào hoặc ngưỡng theo baseline |
| DLT publish failure | Không đưa được record lỗi ra DLT | Cảnh báo nghiêm trọng |
| DLT backlog/cases `NEW` | Record chưa được giải quyết | Tồn đọng quá thời hạn xử lý |
| Processing latency | Thời gian handler + downstream | p95/p99 vượt SLA |
| DB/HTTP failure | Lỗi upstream/downstream | Correlation với retry |
| Rebalance frequency | Group thay đổi ownership | Rebalance liên tục gây lặp/chậm |
| Duplicate suppression | Số lần handler gặp eventId đã xử lý | Gia tăng có thể chỉ ra redelivery |

Các metric có thể đến từ Kafka client, Spring Kafka/Micrometer hoặc metric do ứng dụng tự khai báo. Không mặc định mọi tên trong bảng là metric tự có. Ví dụ một counter ứng dụng có thể tên `orders_consumer_retry_errors_total`, nhưng phải tự instrumentation nếu stack hiện tại không cung cấp.

### Log nên ghi loại lỗi và tọa độ Kafka

```text
WARN event=orders.retryable_failure
     topic=orders.events partition=2 offset=105
     exceptionType=TransientDataAccessResourceException

ERROR event=orders.dlt_recovered
      sourceTopic=orders.events sourcePartition=2
      sourceOffset=105 dltTopic=orders.events.DLT
      reason=RETRIES_EXHAUSTED
```

Không log `event=orders.dlt_recovered` tại thời điểm **chưa xác minh publish thành công**. Hãy sử dụng callback/observation của recoverer hoặc downstream evidence phù hợp.

Nếu log chứa eventId từ payload, chỉ dùng eventId đã validate và được phép ghi. Với lỗi malformed JSON, tọa độ topic-partition-offset đủ để điều tra record nguồn qua công cụ có quyền.

## 18. Bảng chính sách lỗi trước khi triển khai

Một dự án thật nên có bảng phân loại:

| Nhóm exception | Retry? | Backoff | Khi hết retry |
| --- | --- | --- | --- |
| `TemporaryOrderDependencyException` | Có | 1s, 2 retries (ví dụ) | DLT |
| `TransientDataAccessException` | Có | 1s, 2 retries | DLT |
| `InvalidOrderEventException` | Không | Không | DLT ngay |
| JSON deserialization error | Không hoặc theo policy cụ thể | Không | DLT với raw bytes/headers phù hợp |
| Authentication/permission failure | Thường không retry nhanh | Sửa cấu hình, alert | Theo runbook; tránh retry storm |
| HTTP 429 | Có khi tuân thủ Retry-After và rate limit | Backoff dài/jitter | DLT/quarantine hoặc fail theo nghiệp vụ |
| HTTP 400 do request invalid | Không | Không | DLT |
| Serialization/publishing DLT error | Không được xác nhận thành công | Retry/alert theo producer policy | Giữ recovery pending |
| Unknown programming error | Không tự đánh đồng transient | Phân loại/alert | DLT hoặc fail-stop theo yêu cầu dữ liệu |

**DLT không phải phương án bắt buộc cho mọi exception.** Với hệ thống có yêu cầu “không được bỏ qua một bản ghi tài chính quan trọng”, chính sách có thể là dừng partition/job để điều tra thay vì commit source offset sau khi gửi DLT. Phải thống nhất ý nghĩa nghiệp vụ của việc chuyển DLT.

## 19. Tạo một test không phụ thuộc broker production

Có thể dùng `spring-kafka-test` để chạy embedded broker, tạo cả source và DLT rồi xác minh record không hợp lệ được publish vào DLT.

Các mục tiêu của test:

- Source topic có đủ partition.
- DLT topic có cùng số partition.
- Listener và error handler khởi tạo thật.
- Gửi JSON không hợp lệ hoặc event thiếu dữ liệu.
- Đợi consumer xử lý; xác minh record xuất hiện ở DLT.
- Kiểm tra DLT key/value và metadata header nguồn.
- Không phụ thuộc thứ tự các consumer member hoặc `Thread.sleep` cố định.

Một cấu hình annotation minh họa:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(properties = {
    "spring.kafka.consumer.group-id=orders-it",
    "spring.kafka.consumer.auto-offset-reset=earliest",
    "app.kafka.orders.topic=orders.events",
    "app.kafka.orders.dlt-topic=orders.events.DLT"
})
@EmbeddedKafka(
    partitions = 3,
    topics = {
        "orders.events",
        "orders.events.DLT"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class OrderKafkaIntegrationTest {
    // Các test methods ở phần tiếp theo.
}
```

Phần test này giả định Spring Boot context có datasource/transaction manager và bean nghiệp vụ; nếu ứng dụng kết nối PostgreSQL, cần test database riêng hoặc Testcontainers. Đừng chạy integration test trỏ tới database production.

### Test malformed record đến DLT

Mẫu test method:

```java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.serialization.StringDeserializer;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.junit.jupiter.api.Assertions.*;

@Autowired
private KafkaTemplate<String, String> kafkaTemplate;

@Autowired
private EmbeddedKafkaBroker embeddedKafka;

@Test
void invalidJsonIsPublishedToDlt() throws Exception {

    String payload = "{bad-json";

    // Listener source phải đang chạy/được assign theo
    // cấu hình integration test trước khi gửi.
    kafkaTemplate.send(
        "orders.events", 0, "order-42", payload
    ).get(10, TimeUnit.SECONDS);

    Map<String, Object> props = new HashMap<>(
        KafkaTestUtils.consumerProps(
            "dlt-verifier-" + UUID.randomUUID(),
            "false",
            embeddedKafka
        )
    );

    props.put("auto.offset.reset", "earliest");

    try (Consumer<String, String> verifier =
            new DefaultKafkaConsumerFactory<>(
                props,
                new StringDeserializer(),
                new StringDeserializer()
            ).createConsumer()) {

        // Utility sẽ subscribe và poll topic được chỉ định.
        ConsumerRecord<String, String> dlt =
            KafkaTestUtils.getSingleRecord(
                verifier,
                "orders.events.DLT",
                Duration.ofSeconds(20)
            );

        assertEquals("order-42", dlt.key());
        assertEquals(payload, dlt.value());
        assertEquals(0, dlt.partition());
    }
}
```

Ví dụ trên dùng `getSingleRecord` vì chỉ gửi một record lỗi trong kịch bản cô lập. Nếu có nhiều record DLT, không dùng tiện ích “single” rồi mặc định Kafka luôn trả đúng một message. Hãy dùng poll có timeout và chọn record theo key/metadata nguồn.

**Lưu ý:** Để test ổn định, nên chờ listener container của source được assign partition (qua `KafkaListenerEndpointRegistry` hoặc `ContainerTestUtils.waitForAssignment(...)`), rồi mới publish. Với `auto-offset-reset=earliest` và topic cô lập, test ít rủi ro bỏ qua record lúc startup, nhưng vẫn cần chờ điều kiện system ready.

## 20. Test retry thành công và retry cạn

DLT test cho JSON sai chỉ chứng minh đường non-retryable. Còn phải test lỗi transient.

### 20.1. Retry thành công

Dùng một dependency giả lập có thể ném exception ở hai lần đầu rồi thành công ở lần thứ ba:

```java
import java.util.concurrent.atomic.AtomicInteger;

import com.example.orderconsumer.error.TemporaryOrderDependencyException;

public final class FlakyOrderGateway {

    private final AtomicInteger attempts =
        new AtomicInteger();

    public void apply(OrderEvent event) {
        int current = attempts.incrementAndGet();

        if (current <= 2) {
            throw new TemporaryOrderDependencyException(
                "Temporary DB/network failure",
                new IllegalStateException("test-only")
            );
        }
    }

    public int attempts() {
        return attempts.get();
    }
}
```

Khi injected gateway này được gọi trong consumer test với một record duy nhất, kỳ vọng:

- Handler được gọi lại theo cấu hình.
- Lần thứ ba thành công.
- Không có DLT record cho event đó.
- Business output xuất hiện đúng một lần.
- Consumer group vẫn tiếp tục xử lý record tiếp theo.

Chỉ đếm `attempts==3` là chưa đủ nếu test không kiểm tra business effect và offset progress.

### 20.2. Retry cạn

Nếu dependency luôn ném `TemporaryOrderDependencyException`:

- Handler được gọi lần đầu, sau đó retry theo backoff.
- Khi retry cạn, recoverer publish DLT.
- DLT record giữ payload/key và thông tin nguồn.
- Source partition có thể tiếp tục sau khi error handler recover thành công theo ack policy.
- Không có business output cho record chưa xử lý được.

Với integration test, nên kiểm tra cả **tốc độ tiến triển của record phía sau**: gửi một event hợp lệ đứng sau poison record vào cùng partition, xác minh nó cuối cùng được xử lý sau khi record lỗi đã được recover.

Đừng kiểm tra thời gian chính xác đến từng mili-giây. Backoff, scheduler, Kafka poll và CI load làm timing có sai số; đặt timeout hữu hạn và kiểm tra kết quả cuối.

## 21. Test lỗi publish DLT

Một kịch bản thường bị bỏ quên: recoverer không publish được DLT vì topic không tồn tại, ACL thiếu quyền hoặc producer lỗi.

Thiết kế test:

1. Gửi một record lỗi vào source.
2. Cấu hình DLT đích không khả dụng trong môi trường test riêng hoặc giả lập KafkaTemplate send failure.
3. Xác minh error handler **không ghi nhận recovery thành công một cách giả**.
4. Kiểm tra source group không lặng lẽ bỏ qua record chỉ vì DLT publish thất bại.
5. Đảm bảo có log/metric cảnh báo producer/DLT failure.
6. Khôi phục DLT và quan sát cơ chế retry/recover phù hợp.

Đây là một phép thử **mức hạ tầng**, không nên thực hiện bằng cách xóa topic production hoặc vô hiệu hóa ACL thật. Dùng embedded broker/Testcontainers hoặc producer test double có thể điều khiển kết quả send.

Về mặt thiết kế, `setFailIfSendResultIsError(true)` giúp lỗi publish được phản ánh. Nhưng cách container xử lý recovery failure, số lần retry tiếp theo và việc seek phụ thuộc error handler state/config. Cần integration test với phiên bản Spring Kafka mục tiêu.

## 22. Test offset và idempotency khi consumer crash

Một lỗi tiêu biểu trong production:

```text
Consumer A nhận event evt-42
       |
       v
Business DB COMMITTED
       |
       X JVM chết trước Kafka offset commit
       |
       v
Consumer B nhận lại evt-42 sau rebalance
       |
       v
Business service thấy marker evt-42 đã tồn tại
       |
       v
Không tạo side effect trùng
```

Đây là nơi cần kiểm chứng **at-least-once + idempotency**:

- Event được replay khi source committed offset chưa tiến qua nó.
- Có thể có nhiều lần gọi handler cho cùng event.
- Marker trong DB không nhân đôi.
- Projection chỉ có một phiên bản trạng thái hợp lệ.
- Consumer tiếp tục tiêu thụ các record tiếp theo sau khi B tiếp quản partition.

**Không dùng `container.stop()` ngẫu nhiên để thay thế crash.** Graceful shutdown có thể cho handler hoàn tất và commit offset. Với test crash thực, dùng consumer process/container độc lập và điểm fault injection sau DB commit, trước Kafka offset commit; sau đó kill process và kiểm tra committed offset trên broker.

Testcontainers hoặc staging lab phù hợp hơn cho tình huống này. Embedded Kafka trong cùng JVM chủ yếu phục vụ join/leave và retry integration đơn giản.

## 23. Blocking retry có ảnh hưởng đến thứ tự và lag không?

Có. Khi retry một record thất bại, xử lý ở partition đó có thể bị trì hoãn. Nếu nhiều event đến nhanh, consumer lag của partition có thể tăng.

Ví dụ:

```text
Partition 1:
  offset 100 -> lỗi DB, retry 2 lần
  offset 101 -> chờ
  offset 102 -> chờ
  offset 103 -> chờ
```

Lợi ích là không vội xử lý các event phía sau khi event trước chưa được giải quyết, trong mô hình xử lý tuần tự phù hợp. Nhưng chi phí là throughput giảm khi downstream chậm.

Với `FixedBackOff(1000L, 2L)` và hàng nghìn record lỗi, tổng thời gian chờ có thể đáng kể. Tăng retryLimit vô hạn là cách dễ tạo backlog và không tự sửa outage.

### Chỉ số cần đặt cạnh nhau

- Tỷ lệ retryable exceptions.
- Thời gian handler đang chờ/backoff.
- Consumer lag mỗi partition.
- Thời gian p95/p99 xử lý mỗi event.
- Tỷ lệ event được recover sang DLT.
- DB/HTTP latency và error rate.
- Rebalance frequency và poll interval.

Nếu vấn đề là outage kéo dài, một chiến lược circuit breaker hoặc pause/resume theo policy có thể phù hợp hơn retry nhanh. Nhưng khi pause consumer phải hiểu heartbeat/poll behavior của container; `pause()` không đồng nghĩa leave group.

## 24. Phương án khác: @RetryableTopic cho non-blocking retry

Khi không muốn một poison record giữ partition nguồn quá lâu, Spring Kafka hỗ trợ `@RetryableTopic`.

Mô hình khái niệm:

```text
orders.events
    |
    +-- Xử lý thành công --> done
    |
    +-- Lỗi transient
            |
            v
      orders.events-retry-...
            |
         backoff
            |
       +----+-----+
       |          |
     success    exhausted
       |          |
       v          v
      done    orders.events-dlt
```

Đoạn cấu hình minh họa:

```java
import org.springframework.kafka.annotation.EnableKafkaRetryTopic;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableKafkaRetryTopic
class RetryTopicsConfiguration {
}

@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1000,
        multiplier = 2.0,
        maxDelay = 4000
    ),
    include = {
        TemporaryOrderDependencyException.class
    }
)
@KafkaListener(
    topics = "${app.kafka.orders.topic}",
    groupId = "${spring.kafka.consumer.group-id}"
)
public void onMessage(OrderEvent event) {
    orderProjectionService.apply(event);
}
```

Đây là đoạn **minh họa cơ chế**, không phải phần code được ghép nguyên trạng với pipeline String listener/DefaultErrorHandler trước đó. Khi dùng non-blocking retry thực tế:

1. Chọn đúng serializer/deserializer, topic names và producer template cho source/retry/DLT.
2. Xác định số lần attempts, delay và số retry topics cần tạo.
3. Cấu hình handler cho non-retryable exceptions và đường DLT riêng.
4. Không đồng thời áp dụng blocking retry 3 lần rồi non-blocking retry 4 lần mà chưa chủ động tính tổng attempts.
5. Kiểm tra thứ tự event theo key và business version.
6. Quản lý offset/consumer group của những retry topics độc lập với source topology.
7. Kiểm tra DLT handler, retention, ACL và metric cho mọi retry/DLT topic.

**Non-blocking retry có thể làm thay đổi thứ tự xử lý theo partition.** Khi record X được chuyển sang retry topic, record Y phía sau trên source topic có thể được xử lý trước X. Với tài khoản, thanh toán hay state machine theo version, cần thiết kế ordering/version checks chặt chẽ. Không chọn `@RetryableTopic` chỉ vì “đỡ chờ” nếu nghiệp vụ yêu cầu strict per-key processing order.

Spring Kafka có nhiều cách cấu hình non-blocking retries: annotation `@RetryableTopic`, `RetryTopicConfiguration`, các topic naming/exception policies và `@DltHandler`. Chi tiết annotation tương ứng cần tham khảo đúng API version của dự án; không sao chép toàn bộ cấu hình blocking ở ví dụ đầu sang non-blocking mà không điều chỉnh topology.

## 25. DLT không phải queue để replay tự động vô hạn

Một anti-pattern nguy hiểm:

```text
Source -> lỗi -> DLT
                   |
                   v
              Auto replay
                   |
                   v
                 Source
                   |
                 lỗi lại
                   |
                   v
                  DLT
                   |
                   ... vô hạn
```

Nó gây:

- Tăng số record, chi phí lưu trữ và lưu lượng Kafka.
- Gây retry storm tại database/API.
- Làm khó xác định root cause và số lần thất bại của một event.
- Khiến cùng side effect bị lặp nếu handler không idempotent.
- Che giấu lỗi nghiệp vụ vốn cần sửa dữ liệu thủ công.

DLT nên được xem như **khu cách ly cần có chủ sở hữu và quy trình xử lý**, không phải “thùng rác” hoặc một retry queue vô hạn.

Một quy trình replay an toàn:

1. Đọc DLT case và nguyên nhân lỗi.
2. Xác nhận hệ thống đích đã hồi phục hoặc dữ liệu đã được sửa hợp lệ.
3. Đối soát eventId với business DB để tránh xử lý lặp.
4. Phê duyệt phạm vi replay: event IDs/offsets, số lượng, thời gian, người thực hiện.
5. Gửi tới **replay topic** hoặc source theo quy trình với marker/correlation ID, có giới hạn số lần replay.
6. Theo dõi kết quả, giữ audit nguồn DLT và trạng thái CASE `RESOLVED`/`REOPENED` nếu cần.
7. Không xóa DLT record ngay khi publish replay mà chưa xác nhận business outcome theo policy.

Nếu payload cần sửa để hợp lệ, phải ghi lại phiên bản payload mới cùng lý do. Không thay thầm original event rồi mất khả năng audit.

## 26. Runbook vận hành khi DLT tăng bất thường

Giả sử dashboard báo DLT rate từ 0 lên 500 events/phút.

**Bước 1 — Xác nhận phạm vi.** Kiểm tra group, topic, partition, release version, thời điểm bắt đầu tăng và số eventId duy nhất. Không chỉ đếm DLT offsets.

**Bước 2 — Phân loại exception.** Xem nhóm lỗi JSON, DB, API, permission, schema hoặc code regression. Dùng log exception class/error code; tránh lộ raw payload.

**Bước 3 — Đánh giá tác động dữ liệu.** Source offsets có đang tiến không? Consumer lag tăng hay giảm? Có business event đã bị quarantine mà chưa hoàn tất không?

**Bước 4 — Kiểm tra hạ tầng.** Xem DB/HTTP latency, Kafka DLT topic availability, producer errors, quota/ACL và broker health. Nếu DLT producer thất bại, tránh tuyên bố lỗi đã được cách ly thành công.

**Bước 5 — Chọn phản ứng.** Rollback canary, giảm concurrency, tạm dừng consumer theo runbook hoặc sửa lỗi dữ liệu/DB. Không reset group offsets tùy tiện.

**Bước 6 — Khôi phục và replay.** Sau khi nguyên nhân được giải quyết, replay có giới hạn và đối soát theo business IDs.

**Bước 7 — Đóng sự cố.** Lưu số lượng impacted events, thời gian phục hồi, số case đã giải quyết, dữ liệu thiếu/trùng và thay đổi cấu hình phòng ngừa.

Một DLT topic không được giám sát có thể khiến ứng dụng “xanh” nhưng nghiệp vụ âm thầm thiếu dữ liệu nhiều ngày.

## 27. Các lỗi triển khai thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| JSON lỗi làm consumer poll lặp vô tận | Deserializer ném lỗi trước listener | Parse String trong listener hoặc dùng `ErrorHandlingDeserializer` |
| Retry mãi với dữ liệu sai | Chưa phân loại non-retryable | `addNotRetryableExceptions` cho lỗi dữ liệu |
| Lỗi transient được đưa DLT quá sớm | Retry limit quá thấp hoặc exception bị phân loại sai | Kiểm tra classification/backoff và policy |
| Một record lỗi chặn partition rất lâu | Blocking retries kéo dài | Giới hạn backoff/attempts hoặc cân nhắc retry topic |
| DLT không nhận được record | Topic/partition/ACL/serializer sai | Kiểm tra DLT topic partition count và producer errors |
| DLT publish thất bại nhưng offset vẫn tiến | Recovery confirmation/ack policy không đúng | Kiểm tra `setFailIfSendResultIsError` và integration test |
| DLT record chứa byte[] không gửi được | Producer StringSerializer nhưng payload là byte[] | DLT serializer hỗ trợ raw bytes hoặc producer riêng |
| DLT audit listener tạo DLT.DLT | Dùng cùng error handler của source | DLT container factory riêng, không recursive recovery |
| Event đã xử lý bị ghi thêm lần nữa | DB commit trước Kafka offset commit | Idempotency marker/unique constraint |
| DLT có duplicate records | DLT publish xong nhưng source offset chưa commit | Audit theo original topic/partition/offset |
| Lag tăng dù Kafka khỏe | Handler retry hoặc downstream chậm | Theo dõi retry wait, DB latency, partition lag |
| DLT rate thấp nhưng nghiệp vụ vẫn thiếu | Record bị filter/ack sai hoặc side effect không thành công | Đối soát business keys/output |
| DLT vô hạn và replay loop | Auto-replay không giới hạn | Manual/approved replay với retry budget |
| Non-blocking retry làm đảo thứ tự | Record sau chạy trước retry record | Event version/ordering policy |
| Handler nuốt exception | `catch(Exception)` và `return` | Để error handler xử lý và test offset progress |
| Consumer lặp retry sau mỗi deploy | Group offset chưa commit hoặc process crash | Phân biệt redelivery với retry nội bộ |
| Test pass local nhưng fail CI | Kafka assignment bất đồng bộ, dùng sleep | Awaitility, ready signals, topic/group isolation |
| Không biết DLT record nguồn nào | Thiếu/cắt metadata headers | Bảo toàn KafkaHeaders nguồn và audit |
| Mỗi môi trường dùng chung groupId | Offset hoặc workload bị chia ngoài dự kiến | Group theo ứng dụng/môi trường |
| Log chứa bí mật từ exception | Raw payload/stack trace không được redacted | Allowlist fields, phân quyền |
| Rollback image nhưng DB vẫn sai | Side effect đã commit | Compensation/reconciliation, không chỉ rollback code |

## 28. Checklist trước khi đưa consumer vào production

| Hạng mục | Câu hỏi |
| --- | --- |
| Phân loại lỗi | Đã biết exception nào retryable và non-retryable chưa? |
| Số attempts | Có giới hạn retry hữu hạn và backoff hợp lý chưa? |
| Poll/timeout | Thời gian chờ và xử lý có phù hợp `max.poll.interval.ms` chưa? |
| DLT topology | DLT topic tồn tại, có đủ partitions, replication và ACL chưa? |
| Producer | DLT producer gửi đúng serializer, acks, delivery timeout chưa? |
| Commit semantics | Ack mode, auto-commit, error handler, offset commit đã rõ chưa? |
| Idempotency | Rebalance/crash có thể replay mà không nhân đôi side effect chưa? |
| Ordering | Retry topic/partition concurrency có làm đảo thứ tự nghiệp vụ không? |
| Monitoring | Có lag, retry rate, DLT rate, DLT publish failures, alert không? |
| DLT ownership | Có người/nhóm chịu trách nhiệm và SLA xử lý case không? |
| Security | DLT có ACL, retention và chính sách PII phù hợp không? |
| Replay | Có runbook replay có giới hạn, audit và phê duyệt chưa? |
| Testing | Đã test transient success, exhaustion, malformed event, DLT outage, crash window chưa? |
| Rollout | Có canary/rollback và kiểm tra business output không? |
| Versioning | Consumer mới/cũ có tương thích schema và dữ liệu đích không? |

Nếu câu trả lời cho một mục quan trọng là “chưa biết”, cần bổ sung test hoặc thiết kế trước khi mở rộng production.

## 29. Bài tập thực hành mở rộng

Tạo ứng dụng `order-projection-consumer` có source topic ba partition và DLT tương ứng.

### Phần A — Consumer cơ bản

1. Cấu hình `StringDeserializer` cho payload JSON.
2. Xây `OrderEventListener` parse/validate như phần ví dụ.
3. Tạo hai nhóm exception: transient và invalid payload.
4. Cấu hình `DefaultErrorHandler` với `FixedBackOff(1000,2)`.
5. Dùng `DeadLetterPublishingRecoverer` giữ nguyên partition number.

### Phần B — Tình huống lỗi

1. Gửi một event hợp lệ; kiểm tra DB có projection đúng.
2. Gửi JSON sai; kiểm tra record xuất hiện DLT không cần retry dài.
3. Giả lập DB lỗi hai lần rồi hồi phục; kiểm tra event được xử lý, không nằm DLT.
4. Giả lập DB lỗi kéo dài; kiểm tra record được gửi DLT sau retry budget.
5. Cho DLT publish thất bại; kiểm tra có cảnh báo và không mất âm thầm record nguồn.

### Phần C — Idempotency và restart

1. Gửi hai lần cùng eventId, kiểm tra marker chỉ tồn tại một bản ghi.
2. Gửi version 5 rồi version 4 của cùng order; projection không được cập nhật lùi.
3. Cho consumer crash sau DB commit nhưng trước offset commit trong một process độc lập.
4. Sau rebalance, kiểm tra event có thể replay nhưng business output không bị nhân đôi.

### Phần D — Vận hành

1. Tạo dashboard biểu diễn consumer lag, retry/DLT rates và DB latency.
2. Tạo cảnh báo khi DLT publish fail hoặc backlog case vượt SLA.
3. Thiết kế bảng audit theo original topic/partition/offset.
4. Viết runbook replay 10 event DLT sau khi sửa nguyên nhân.
5. Đề xuất khi nào chuyển sang `@RetryableTopic` và mô tả rủi ro ordering.

Báo cáo thí nghiệm nên ghi: source topic/partition/offset, eventId, exception type, attempts, recovery outcome, offset state và số business side effect thực tế.

## 30. Tổng kết

Một **Spring Kafka consumer có retry và DLT** đáng tin cậy cần nhiều hơn một annotation. Phần chính gồm: listener để lỗi được lan tới container; chính sách retry/backoff phân loại transient và non-retryable; recoverer gửi record không thể xử lý tới DLT; offset/ack policy nhất quán với recovery; và business handler **idempotent** để chịu được redelivery sau commit failure hoặc rebalance.

Với workload yêu cầu giữ thứ tự theo partition, `DefaultErrorHandler` và blocking retry là điểm khởi đầu dễ hiểu. Khi cần tránh giữ partition nguồn vì một record lỗi lâu, `@RetryableTopic` có thể phù hợp hơn nhưng đòi hỏi quản lý retry topics, offset và ordering cẩn thận. Dù theo mô hình nào, **DLT là nơi cách ly và cần được vận hành**, không phải bằng chứng nghiệp vụ đã xử lý thành công.

Hãy xác minh bằng integration test các tình huống: retry thành công, retry cạn, lỗi payload, publish DLT thất bại, consumer crash giữa DB commit và offset commit; đồng thời có dashboard, cảnh báo và runbook replay có kiểm soát. Khi những điều kiện ấy được thực hiện, hệ thống có thể vượt qua lỗi tạm thời, không mất âm thầm các record khó xử lý và giữ kết quả nghiệp vụ đúng sau retry hoặc rebalance.

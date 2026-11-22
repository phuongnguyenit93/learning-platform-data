# Mô phỏng consumer restart

## 1. Mục tiêu thực hành

Trong bài thực hành này, bạn sẽ mô phỏng một consumer xử lý record thành công ở tầng nghiệp vụ nhưng dừng trước khi xác nhận offset. Khi listener container được khởi động lại với cùng consumer group, Kafka giao lại record chưa được commit.

Bài lab dùng một topic, một partition và một consumer để dễ quan sát thứ tự:

1. Producer gửi một sự kiện đơn hàng.
2. Consumer nhận record và ghi nhận event vào database.
3. Listener cố ý không gọi Acknowledgment.acknowledge() ở lần đầu.
4. Listener container dừng rồi khởi động lại.
5. Vì offset chưa được commit, consumer nhận lại cùng record.
6. Idempotency check phát hiện event đã được xử lý và không tạo side effect lần thứ hai.
7. Listener xác nhận offset sau lần nhận lại.

Kết quả cần đạt:

- Listener nhận cùng event hai lần.
- Database chỉ có một bản ghi xử lý cho event ID đó.
- Offset của partition được commit sau lần nhận lại.
- Bạn hiểu vì sao Kafka có thể giao lại record sau restart và vì sao consumer cần idempotent.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant K as Kafka
    participant C as Consumer
    participant DB as Database
    P->>K: Publish event E (offset 0)
    K->>C: Deliver E
    C->>DB: Insert processed_event(E)
    DB-->>C: Commit DB transaction
    C--xK: Không acknowledge offset
    Note over C: Listener container dừng
    Note over C: Listener container khởi động lại
    K->>C: Deliver lại E (offset 0)
    C->>DB: Kiểm tra event ID E
    DB-->>C: Đã tồn tại, bỏ qua side effect
    C->>K: acknowledge()
    K-->>C: Commit offset kế tiếp (1)
~~~

Bài này mô phỏng restart của Spring Kafka listener container trong cùng JVM. Database H2 vẫn tồn tại trong lúc container dừng. Đây là cách kiểm thử có kiểm soát để quan sát redelivery; phần cuối sẽ chỉ ra cách mở rộng thành restart toàn bộ JVM với database bền vững.

## 2. Kiến thức cần áp dụng

| Thành phần | Vai trò trong bài lab |
|---|---|
| `KafkaTemplate` | Gửi sự kiện vào topic kiểm thử |
| `@KafkaListener` | Nhận record từ topic |
| Consumer group | Lưu committed offset của luồng xử lý |
| `AckMode.MANUAL` | Listener chủ động xác nhận offset |
| `enable.auto.commit=false` | Không để Kafka client tự commit ngoài ý muốn |
| `KafkaListenerEndpointRegistry` | Lấy listener container để stop/start |
| `AdminClient` | Đọc committed offset để xác minh |
| `JdbcTemplate` và H2 | Lưu dấu event đã xử lý |
| Event ID | Khóa idempotency để loại bỏ side effect trùng |

Kafka lưu offset theo consumer group và partition. Với record ở offset 0, sau khi xác nhận thành công, committed offset thường là 1 vì offset đã commit biểu thị vị trí đọc kế tiếp.

Nếu consumer dừng trước khi commit, lần khởi động sau sẽ tiếp tục từ committed offset gần nhất. Khi chưa có committed offset, `auto.offset.reset=earliest` cho phép consumer bắt đầu từ record sớm nhất còn trong log.

## 3. Tạo project và dependency

Ví dụ dùng Gradle với phiên bản Spring Boot do project quản lý. Nếu project đã có plugin và dependency management, chỉ bổ sung các dependency còn thiếu.

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-json'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.kafka:spring-kafka'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

`spring-kafka-test` cung cấp Embedded Kafka, `KafkaTestUtils` và tiện ích chờ listener được assign partition. H2 dùng để lưu event đã xử lý trong cùng test context.

Cấu trúc package gợi ý:

~~~text
src/
  main/
    java/com/example/restartlab/
      RestartLabApplication.java
      domain/OrderCreated.java
      service/OrderProcessingService.java
      messaging/RestartLabListener.java
    resources/
      application.yml
      schema.sql
  test/
    java/com/example/restartlab/
      ConsumerRestartIntegrationTest.java
~~~

## 4. Cấu hình Kafka và database

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: restart-lab
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    listener:
      ack-mode: manual
      concurrency: 1

  datasource:
    url: jdbc:h2:mem:restartlab;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:

  sql:
    init:
      mode: always

lab:
  skip-first-ack: false
~~~

Các thiết lập quan trọng:

- `enable-auto-commit=false`: tắt auto commit của Kafka client.
- `ack-mode=manual`: listener phải gọi `acknowledge()` để xác nhận record.
- `concurrency=1`: chỉ dùng một consumer thread cho bài lab.
- `auto-offset-reset=earliest`: nếu group chưa có committed offset, bắt đầu từ log start.
- H2 `DB_CLOSE_DELAY=-1`: giữ database in-memory trong thời gian JVM đang chạy, kể cả khi connection cuối cùng đóng.

Trong integration test, Embedded Kafka sẽ ghi đè `spring.kafka.bootstrap-servers` để ứng dụng kết nối broker nhúng. Không cần chạy Kafka bên ngoài cho bài test này.

## 5. Tạo schema lưu event đã xử lý

Tạo `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE IF NOT EXISTS processed_event (
    event_id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    order_status VARCHAR(32) NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
~~~

`event_id` là primary key để mỗi sự kiện chỉ được ghi nhận một lần. Bài lab dùng một partition và một consumer thread, nên thao tác kiểm tra rồi insert được thực hiện tuần tự.

Trong hệ thống có nhiều partition hoặc nhiều consumer xử lý song song, cần dùng thao tác insert-if-absent nguyên tử theo dialect database và unique constraint. Ví dụ PostgreSQL:

~~~sql
INSERT INTO processed_event(event_id, order_id, order_status)
VALUES (?, ?, ?)
ON CONFLICT (event_id) DO NOTHING;
~~~

Chỉ cập nhật projection hoặc thực hiện side effect tiếp theo khi câu lệnh insert trả về số dòng được thêm là 1. Unique constraint vẫn cần thiết để bảo vệ trường hợp hai consumer cùng nhận event trùng gần như đồng thời.

## 6. Tạo application class và event

Tạo application class `RestartLabApplication.java`:

~~~java
package com.example.restartlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RestartLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(RestartLabApplication.class, args);
    }
}
~~~

Tạo event `OrderCreated.java`:

~~~java
package com.example.restartlab.domain;

public record OrderCreated(
    String eventId,
    String orderId,
    String status
) {
}
~~~

`eventId` phải ổn định giữa các lần giao lại. Không tạo UUID mới ở listener cho mỗi lần nhận vì khi đó lần replay sẽ bị xem là một event hoàn toàn khác.

## 7. Viết service xử lý idempotent

Tạo `OrderProcessingService.java`:

~~~java
package com.example.restartlab.service;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.restartlab.domain.OrderCreated;

@Service
public class OrderProcessingService {

    private final JdbcTemplate jdbcTemplate;

    public OrderProcessingService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public boolean process(OrderCreated event) {
        Integer count = jdbcTemplate.queryForObject(
            """
            SELECT COUNT(*)
            FROM processed_event
            WHERE event_id = ?
            """,
            Integer.class,
            event.eventId()
        );

        if (count != null && count > 0) {
            return false;
        }

        jdbcTemplate.update(
            """
            INSERT INTO processed_event(
                event_id,
                order_id,
                order_status
            )
            VALUES (?, ?, ?)
            """,
            event.eventId(),
            event.orderId(),
            event.status()
        );

        return true;
    }
}
~~~

Service trả về:

- `true`: event ID chưa tồn tại và đã được ghi nhận.
- `false`: event ID đã được xử lý trước đó, không tạo thêm side effect.

`@Transactional` bảo đảm phần ghi nhận event nằm trong transaction database. Listener gọi service qua Spring bean proxy; khi lời gọi service trả về, transaction của service đã hoàn tất trước khi listener quyết định acknowledge.

Đây là cách minh họa ngắn gọn cho consumer tuần tự. Với tải song song, thay thao tác SELECT rồi INSERT bằng insert-if-absent nguyên tử như ví dụ PostgreSQL ở trên; nếu insert không thêm dòng thì bỏ qua side effect.

## 8. Viết listener có chế độ bỏ qua acknowledge một lần

Tạo `RestartLabListener.java`:

~~~java
package com.example.restartlab.messaging;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.example.restartlab.domain.OrderCreated;
import com.example.restartlab.service.OrderProcessingService;

@Component
public class RestartLabListener {

    private final ObjectMapper objectMapper;
    private final OrderProcessingService processingService;

    private final AtomicBoolean skipFirstAck = new AtomicBoolean(true);
    private final AtomicInteger deliveryCount = new AtomicInteger();

    private final CountDownLatch firstProcessedWithoutAck =
        new CountDownLatch(1);

    private final CountDownLatch replayAcknowledged =
        new CountDownLatch(1);

    @Value("${lab.skip-first-ack:false}")
    private boolean skipFirstAckEnabled;

    public RestartLabListener(
            ObjectMapper objectMapper,
            OrderProcessingService processingService) {
        this.objectMapper = objectMapper;
        this.processingService = processingService;
    }

    @KafkaListener(
        id = "restartLabListener",
        topics = "orders.restart-lab",
        groupId = "restart-lab",
        concurrency = "1"
    )
    public void onMessage(
            String payload,
            Acknowledgment acknowledgment)
            throws JsonProcessingException {

        OrderCreated event =
            objectMapper.readValue(payload, OrderCreated.class);

        processingService.process(event);
        deliveryCount.incrementAndGet();

        if (skipFirstAckEnabled
                && skipFirstAck.compareAndSet(true, false)) {
            // Side effect đã hoàn tất, nhưng offset chưa được acknowledge.
            firstProcessedWithoutAck.countDown();
            return;
        }

        acknowledgment.acknowledge();
        replayAcknowledged.countDown();
    }

    public boolean awaitFirstProcessed(long timeout, TimeUnit unit)
            throws InterruptedException {
        return firstProcessedWithoutAck.await(timeout, unit);
    }

    public boolean awaitReplayAcknowledged(long timeout, TimeUnit unit)
            throws InterruptedException {
        return replayAcknowledged.await(timeout, unit);
    }

    public int deliveryCount() {
        return deliveryCount.get();
    }
}
~~~

Cơ chế mô phỏng:

- `lab.skip-first-ack=true` chỉ được bật trong integration test.
- Lần nhận đầu, service ghi event vào database rồi listener trả về mà không acknowledge.
- Test dừng listener container sau khi nhận tín hiệu `firstProcessedWithoutAck`.
- Khi container khởi động lại, Kafka giao lại record vì offset chưa được commit.
- Lần nhận thứ hai, service nhận ra event ID đã tồn tại; listener gọi acknowledge.

Không bật `lab.skip-first-ack=true` trong cấu hình production. Đây là công tắc phục vụ bài lab để mô phỏng cửa sổ lỗi giữa side effect và offset commit.

## 9. Viết integration test với Embedded Kafka

Tạo `ConsumerRestartIntegrationTest.java`. Test dùng một topic có một partition và consumer group cố định để quan sát offset một cách xác định.

~~~java
package com.example.restartlab;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.annotation.DirtiesContext;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.example.restartlab.domain.OrderCreated;
import com.example.restartlab.messaging.RestartLabListener;

@SpringBootTest(properties = {
    "lab.skip-first-ack=true",
    "spring.kafka.consumer.enable-auto-commit=false",
    "spring.kafka.listener.ack-mode=manual",
    "spring.kafka.consumer.auto-offset-reset=earliest"
})
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.restart-lab"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class ConsumerRestartIntegrationTest {

    private static final String TOPIC = "orders.restart-lab";
    private static final String GROUP_ID = "restart-lab";

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    RestartLabListener listener;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Test
    void redeliversRecordWhenContainerRestartsBeforeAck()
            throws Exception {

        MessageListenerContainer container =
            registry.getListenerContainer("restartLabListener");

        assertThat(container).isNotNull();
        ContainerTestUtils.waitForAssignment(container, 1);

        OrderCreated event = new OrderCreated(
            "event-1001",
            "order-1001",
            "CREATED"
        );

        String payload = objectMapper.writeValueAsString(event);

        kafkaTemplate.send(
            TOPIC,
            event.orderId(),
            payload
        ).get(10, TimeUnit.SECONDS);

        // Đợi side effect database hoàn tất; listener chưa acknowledge.
        assertThat(
            listener.awaitFirstProcessed(10, TimeUnit.SECONDS)
        ).isTrue();

        // Chờ callback để chắc chắn consumer đã dừng trước khi kiểm tra offset.
        CountDownLatch stopped = new CountDownLatch(1);
        container.stop(stopped::countDown);
        assertThat(stopped.await(10, TimeUnit.SECONDS)).isTrue();
        assertThat(container.isRunning()).isFalse();

        // Group chưa có committed offset cho partition này.
        assertThat(committedOffset()).isNull();

        // Khởi động lại listener container với cùng group ID.
        container.start();
        ContainerTestUtils.waitForAssignment(container, 1);

        assertThat(
            listener.awaitReplayAcknowledged(10, TimeUnit.SECONDS)
        ).isTrue();

        // MANUAL ack được container commit sau khi xử lý record.
        await()
            .atMost(Duration.ofSeconds(10))
            .untilAsserted(() ->
                assertThat(committedOffset()).isEqualTo(1L)
            );

        assertThat(listener.deliveryCount()).isEqualTo(2);

        Integer processedRows = jdbcTemplate.queryForObject(
            """
            SELECT COUNT(*)
            FROM processed_event
            WHERE event_id = ?
            """,
            Integer.class,
            event.eventId()
        );

        assertThat(processedRows).isEqualTo(1);
    }

    private Long committedOffset() throws Exception {
        Properties properties = new Properties();
        properties.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            embeddedKafka.getBrokersAsString()
        );

        try (AdminClient admin = AdminClient.create(properties)) {
            var offsets = admin.listConsumerGroupOffsets(GROUP_ID)
                .partitionsToOffsetAndMetadata()
                .get(10, TimeUnit.SECONDS);

            var committed = offsets.get(new TopicPartition(TOPIC, 0));

            return committed == null ? null : committed.offset();
        }
    }
}
~~~

Test xác minh bốn điều kiện độc lập:

1. `deliveryCount = 2`: cùng record đã được listener nhận hai lần.
2. `processedRows = 1`: database chỉ ghi nhận event một lần.
3. `committedOffset = 1`: consumer đã xác nhận vị trí đọc kế tiếp sau record offset 0.
4. `committedOffset` trước lần restart là `null`: lần nhận đầu chưa xác nhận offset.

Nếu test không thấy redelivery, hãy kiểm tra AckMode, `enable-auto-commit`, consumer group và thời điểm stop container. Không thêm `Thread.sleep()` cố định để chờ; dùng latch, `waitForAssignment` và Awaitility như ví dụ.

## 10. Chạy bài thực hành

Với Gradle Wrapper trên Linux/macOS:

~~~bash
./gradlew test --tests "com.example.restartlab.ConsumerRestartIntegrationTest"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.restartlab.ConsumerRestartIntegrationTest"
~~~

Kết quả mong đợi:

~~~text
ConsumerRestartIntegrationTest
  redeliversRecordWhenContainerRestartsBeforeAck() PASSED

Tests run: 1, Failures: 0
~~~

Nếu project dùng Maven, chạy test class tương ứng:

~~~bash
./mvnw -Dtest=ConsumerRestartIntegrationTest test
~~~

Embedded Kafka được khởi động trong test context và tự dừng sau khi context đóng. Không cần chạy broker local riêng cho test này.

## 11. Quan sát offset và trạng thái consumer group

Trong môi trường Kafka chạy độc lập, có thể kiểm tra group bằng CLI:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group restart-lab
~~~

Sau khi record được xác nhận, partition 0 có committed offset là 1. Nếu gửi thêm record ở offset 1 và consumer xử lý thành công, committed offset tiếp theo sẽ là 2.

Có thể quan sát topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.restart-lab
~~~

Với Embedded Kafka, test đã dùng `AdminClient` để kiểm tra committed offset trực tiếp. CLI chỉ dùng khi bạn chạy bài lab với broker độc lập.

## 12. Vì sao database có một dòng nhưng listener nhận hai lần?

Kafka và database là hai hệ thống lưu trạng thái riêng. Trong ví dụ này, database commit trước khi listener acknowledge offset:

~~~text
Database transaction: COMMIT
Kafka offset:          NOT COMMITTED
Consumer container:    STOPPED
~~~

Khi consumer khởi động lại, Kafka không biết database đã xử lý event. Broker chỉ biết group chưa commit offset, nên giao lại record.

Lần nhận thứ hai:

~~~text
Database lookup: event_id already exists
Business side effect: skipped
Kafka offset: ACKNOWLEDGED
~~~

Đây là hành vi at-least-once delivery. Consumer cần chấp nhận khả năng một record được giao nhiều lần và bảo vệ side effect bằng idempotency.

## 13. Thử các biến thể để hiểu rõ hơn

Sau khi test cơ bản chạy thành công, thay đổi từng điều kiện và quan sát kết quả.

| Thử nghiệm | Thay đổi | Điều cần quan sát |
|---|---|---|
| A. Acknowledge ngay | Tắt `lab.skip-first-ack` | Listener nhận một lần, offset được commit |
| B. Không có idempotency | Bỏ kiểm tra event ID | Record được nhận hai lần và side effect có thể nhân đôi |
| C. Auto commit bật | Bật `enable-auto-commit` | Offset có thể được commit ngoài thời điểm xử lý nghiệp vụ mong muốn |
| D. Group ID mới | Đổi group ID | Group mới không dùng committed offset của group cũ |
| E. Gửi hai record | Gửi hai event cùng partition | Quan sát offset và thứ tự xử lý |
| F. Nhiều partition | Tăng partition và concurrency | Cần xử lý idempotency khi event trùng có thể chạy song song |

Khi thử nghiệm C, không dùng kết quả của một lần chạy để kết luận auto commit luôn gây mất dữ liệu. Kết quả phụ thuộc poll interval, thời điểm commit và thời điểm tiến trình dừng. Mục tiêu là thấy vì sao auto commit không phù hợp nếu ứng dụng cần gắn offset commit với kết quả xử lý nghiệp vụ.

## 14. Thử mô phỏng lỗi thay vì chỉ bỏ acknowledge

Một biến thể khác là để listener ghi database rồi ném exception trước khi acknowledge. Khi đó, error handler có thể retry ngay trong cùng container thay vì chờ restart.

~~~java
processingService.process(event);

if (simulateFailureBeforeAck) {
    throw new IllegalStateException("Simulated crash window");
}

acknowledgment.acknowledge();
~~~

Nếu `DefaultErrorHandler` được cấu hình retry, record có thể được giao lại ngay trong cùng vòng đời container. Để mô phỏng restart đúng mục tiêu bài này, test dùng đường đi stop/start container sau khi listener trả về mà không acknowledge.

Không dùng exception giả lập trong cùng test nếu mục tiêu là đo riêng hành vi restart; hai kịch bản có cơ chế retry khác nhau.

## 15. Mở rộng thành restart toàn bộ JVM

Bài test chính restart listener container trong cùng Spring application context. Để mô phỏng process restart thực tế:

1. Thay H2 in-memory bằng PostgreSQL hoặc database bền vững có volume.
2. Chạy Kafka và database bên ngoài JVM của consumer.
3. Dùng cùng `group.id` trước và sau restart.
4. Tạo một điểm dừng có kiểm soát sau khi database transaction commit nhưng trước `acknowledge()`.
5. Dừng cưỡng bức JVM tại điểm đó để consumer không thể commit offset.
6. Khởi động lại ứng dụng với cùng cấu hình.
7. Xác minh event được giao lại và database unique key ngăn side effect lặp.

Không dùng H2 in-memory cho thử nghiệm process restart vì dữ liệu mất khi JVM kết thúc. Nếu dùng H2 file-based, cần kiểm tra recovery và file lock của database khi tiến trình bị kill; database server riêng thường phù hợp hơn cho bài mô phỏng production.

Không nên dùng `Runtime.halt()` hoặc kill tiến trình production để thử. Thực hiện trong môi trường local/staging cô lập, với topic, consumer group và database riêng.

## 16. Những giới hạn cần hiểu

- Restart listener container không đồng nghĩa restart toàn bộ JVM.
- H2 in-memory giữ dữ liệu trong cùng JVM; nó không chứng minh khả năng phục hồi database sau process crash.
- `AckMode.MANUAL` chỉ kiểm soát offset khi listener gọi acknowledge; cần tắt auto commit để tránh một cơ chế commit khác can thiệp.
- Một record có thể được giao lại sau rebalance, timeout hoặc consumer crash, không chỉ sau restart có chủ ý.
- Idempotency ở database không tự bảo vệ side effect gọi HTTP, gửi email hoặc thanh toán. Những side effect đó cần idempotency key hoặc cơ chế bù trừ riêng.
- Kafka transaction có thể phối hợp việc publish record Kafka và commit offset Kafka; nó không tự tạo transaction phân tán với database quan hệ.
- Nếu dùng batch listener hoặc nhiều partition, offset commit và thứ tự xử lý phức tạp hơn ví dụ một record/một partition này.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Listener không nhận được `Acknowledgment` | Ack mode không phải MANUAL/MANUAL_IMMEDIATE | Đặt `spring.kafka.listener.ack-mode=manual` |
| Record không được giao lại | Offset đã commit hoặc auto commit đang bật | Kiểm tra committed offset và `enable-auto-commit=false` |
| Listener nhận nhiều hơn hai lần | Container chưa dừng, retry khác đang chạy hoặc test gửi trùng | Kiểm tra group, container state và event ID |
| Test không tìm thấy container | Listener ID không khớp | Kiểm tra `@KafkaListener(id=...)` và registry |
| `waitForAssignment` timeout | Broker chưa sẵn sàng hoặc listener chưa subscribe | Kiểm tra Embedded Kafka và topic |
| Offset không tăng lên 1 | Listener chưa acknowledge hoặc container chưa commit | Chờ latch và poll committed offset với timeout |
| Database có nhiều dòng trùng | Idempotency check thiếu hoặc không nguyên tử khi xử lý song song | Dùng unique constraint và insert-if-absent |
| Event bị xử lý lại sau deploy | Consumer group hoặc offset thay đổi | Xác minh group ID và chiến lược reset offset |

## 18. Checklist hoàn thành

- [ ] Tạo project có `spring-kafka`, `spring-kafka-test`, JDBC và H2.
- [ ] Tạo topic có một partition.
- [ ] Tắt Kafka auto commit.
- [ ] Cấu hình listener `AckMode.MANUAL`.
- [ ] Gửi event có event ID ổn định.
- [ ] Ghi nhận event vào database trước khi acknowledge.
- [ ] Bỏ acknowledge có chủ đích ở lần đầu.
- [ ] Dừng listener container sau lần xử lý đầu.
- [ ] Xác minh group chưa có committed offset.
- [ ] Khởi động lại container với cùng group ID.
- [ ] Xác minh listener nhận lại cùng event.
- [ ] Xác minh database chỉ có một dòng cho event ID.
- [ ] Xác minh committed offset tăng lên 1.
- [ ] Thử tắt idempotency để quan sát side effect trùng.
- [ ] Phân biệt container restart với JVM restart.

Bài thực hành chứng minh rằng consumer restart có thể làm Kafka giao lại record khi offset chưa được commit. Listener có thể nhận cùng event nhiều lần dù side effect database đã hoàn tất ở lần trước. Khi xử lý idempotent bằng event ID, ứng dụng giữ được kết quả nghiệp vụ đúng và vẫn xác nhận offset sau lần giao lại.

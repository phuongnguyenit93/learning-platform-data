# Retry ở tầng broker: Kafka, RabbitMQ và Spring Application Events

Khi một ứng dụng Spring phát sự kiện để hệ thống khác xử lý, có thể xảy ra các lỗi như mất kết nối, consumer tạm ngừng, HTTP downstream trả `503`, database deadlock, hoặc dữ liệu message không hợp lệ. **Retry ở tầng broker** là cách dùng **hạ tầng message broker và consumer container** để thực hiện lại việc **giao/tiêu thụ message** theo quy tắc được kiểm soát, thay vì chỉ giữ một vòng lặp retry trong thread đang xử lý request.

Với chủ đề **Spring Framework Application Events**, phải phân biệt ngay từ đầu:

- `ApplicationEventPublisher.publishEvent(...)` và `@EventListener` là cơ chế **application event trong Spring ApplicationContext**, thường chỉ trong một JVM. **Spring event bus này không tự có retry topic, dead-letter queue (DLQ), offset, acknowledgement hay lưu bền vững.**
- `@KafkaListener` của **Spring for Apache Kafka** và `@RabbitListener` của **Spring AMQP** nhận message qua **broker**. Retry được điều khiển bởi container, error handler, acknowledgement, retry topics/queues, chính sách broker và/hoặc application recovery.
- Muốn nối từ một domain event bên trong transaction tới Kafka/RabbitMQ mà không bỏ mất message khi process crash, thường cần thiết kế riêng **Transactional Outbox** hoặc một giải pháp giao nhận có đảm bảo tương đương.

Mục tiêu bài học: hiểu **retry có giới hạn** ở broker, phân biệt **blocking** và **non-blocking retries**, sử dụng Spring Kafka `@RetryableTopic`/DLT và Spring AMQP DLX/TTL, thiết kế idempotency, xử lý poison message, tính toán backoff, quan sát backlog và kiểm thử cả thành công lẫn thất bại.

## 1. Vì sao retry trong JVM chưa đủ cho tích hợp bên ngoài?

Giả sử đơn hàng đã commit và ứng dụng muốn thông báo cho dịch vụ hóa đơn:

```text
HTTP request
    |
    +-- OrderService: UPDATE order; COMMIT
    |
    +-- publishEvent(OrderApproved)
            |
            +-- @EventListener
                    |
                    +-- gọi API hóa đơn
                         +-- thất bại -> retry 3 lần trong RAM
```

Nếu lỗi chỉ kéo dài một giây và tiến trình còn sống, retry cục bộ có thể hữu ích. Nhưng nếu ứng dụng chết ngay sau commit hoặc trong lúc chờ attempt tiếp theo, **không có một message bền vững bắt buộc còn tồn tại** để consumer khác nhận lại. `@TransactionalEventListener(AFTER_COMMIT)` cũng không tự tạo cơ chế lưu message.

Kiến trúc broker:

```text
OrderService
     |
     +-- COMMIT business data + outbox row (nếu cần atomicity)
                |
                v
       Outbox publisher / producer
                |
                v
          Kafka / RabbitMQ
                |
                +-- durable topic / queue
                |
                v
            Consumer
                |
                +-- success -> acknowledge/advance offset
                |
                +-- transient failure
                |      -> retry với backoff/giới hạn
                |
                +-- permanent failure / hết attempts
                       -> DLT/DLQ/quarantine
```

**Broker retry không đồng nghĩa exactly-once side effect.** Consumer có thể xử lý xong trong database nhưng bị crash trước khi ack/commit offset, dẫn tới **redelivery**. Vì vậy business handlers cần **idempotent** hoặc một cơ chế inbox/deduplication phù hợp.

### Thuật ngữ cốt lõi

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Message / record** | Dữ liệu đã được đưa vào topic/queue; thường có key, headers, payload, metadata |
| **Delivery attempt** | Một lần consumer nhận và thử xử lý message |
| **Ack / Nack / Reject** | Tín hiệu consumer/broker về kết quả giao hoặc xử lý; semantics tùy giao thức |
| **Kafka offset** | Vị trí record trong topic partition; commit offset liên quan tiến độ consumer group |
| **Requeue** | Đưa message RabbitMQ trở lại hàng đợi để được giao lại |
| **Retry topic/queue** | Đích tạm lưu message thất bại để được xử lý lại theo lịch/backoff |
| **DLT / DLQ** | Dead Letter Topic / Dead Letter Queue: đích cho message không thể xử lý trong policy hiện tại |
| **Poison message** | Message liên tục làm consumer lỗi do payload/schema/logic không thể sửa chỉ bằng chờ |
| **Idempotency key** | Định danh ổn định của logical operation/event qua nhiều attempts |
| **Backoff / jitter** | Thời gian hoãn và biến thiên ngẫu nhiên để tránh retry storm |

Một record chỉ “đã tới broker” khi có **bằng chứng xác nhận publish** theo producer config. Gọi `KafkaTemplate.send(...)` mà không quan sát completion/error là không đủ để kết luận broker đã lưu record thành công.

## 2. Lựa chọn tầng retry: blocking hay non-blocking?

### 2.1. Blocking retry

**Blocking retry** giữ consumer/partition xử lý record lỗi cho tới khi hết các lần thử (hoặc có recovery). Với Spring Kafka, `DefaultErrorHandler` cùng `BackOff` là một lựa chọn điển hình.

```text
Kafka topic / partition P0:
    record A -> attempt 1 fail
               wait 1 s
               attempt 2 fail
               wait 1 s
               attempt 3 success
    record B -> chỉ được xử lý tiếp theo theo chiến lược container
```

Ưu điểm:

- Thường dễ giữ trật tự xử lý trên cùng partition khi không chuyển record sang topic khác.
- Không cần thiết kế/triển khai nhiều retry topics.
- Hợp với lỗi ngắn, số attempts nhỏ và yêu cầu ordering chặt.

Nhược điểm:

- Record lỗi có thể làm **head-of-line blocking**, giảm throughput của partition/consumer.
- Backoff lâu có thể tương tác với `max.poll.interval.ms`, assignment/rebalance; cần dùng cơ chế tạm dừng container phù hợp nếu thời gian chờ dài.
- Poison message sẽ gây nghẽn nếu cấu hình retry vô hạn.

Không diễn giải “blocking” là Kafka broker tự ngủ 1 giây. Ở đây error handler/listener container trong consumer **điều phối việc giao lại** và backoff; broker vẫn là kho lưu topic.

### 2.2. Non-blocking retry qua retry topic

Spring Kafka cung cấp `@RetryableTopic` để hỗ trợ **non-blocking retry topology**:

```text
notifications.commands  (main topic)
      |
      +-- success -> done
      |
      +-- failure -> notifications.commands-retry-1000
                          |
                          +-- due time -> consumer retry
                          |
                          +-- failure -> notifications.commands-retry-2000
                                              |
                                              +-- due time -> consumer retry
                                              |
                                              +-- failure/hết budget
                                                     -> notifications.commands-dlt
```

Các tên topic là **ví dụ minh họa**: suffix thực tế phụ thuộc policy, khoảng backoff và phiên bản/cấu hình; không hard-code tên do framework tạo vào nghiệp vụ mà không kiểm tra.

Lợi ích: main consumer có thể tiếp tục các record khác khi record thất bại được chuyển sang retry topic. Đổi lại:

- **Không còn bảo đảm thứ tự tuyệt đối** giữa record A được retry và record B cùng khóa đi qua main topic thành công trước.
- Phải vận hành thêm topic/consumer, retention, partitions, storage và metrics.
- Forwarding sang retry/DLT và commit offset có ranh giới lỗi; cần hiểu acknowledgement, confirm và cơ chế recovery.
- Delay theo due timestamp/topic consumer có **độ chính xác hữu hạn**, không phải một deadline real-time cứng.

**Giới hạn quan trọng của Spring Kafka 3.3:** non-blocking retries **không hỗ trợ batch listeners** và **không kết hợp với Kafka container transactions**. Không áp dụng `@RetryableTopic` một cách máy móc vào pipeline đã sử dụng những chế độ đó. Đối với workload phải giữ ordering nghiêm ngặt, cân nhắc blocking retry ngắn, workflow theo aggregate hoặc chiến lược partition/sequence riêng.

### 2.3. So sánh nhanh

| Thuộc tính | Blocking consumer retry | Retry topic/queue |
| --- | --- | --- |
| Nơi chờ | Consumer/container, có thể pause poll | Message chuyển sang hạ tầng chờ riêng |
| Main pipeline | Có thể bị chặn bởi record lỗi | Có thể tiếp tục record khác |
| Ordering | Dễ bảo toàn hơn theo partition | Có thể đảo thứ tự xử lý |
| Số topic/queue | Ít hơn | Thường tăng |
| Retry lâu phút/giờ | Không lý tưởng nếu giữ consumer | Thường phù hợp hơn |
| Durable qua restart | Phụ thuộc broker offset/ack và recovery | Broker giữ retry message nếu cấu hình đúng |
| Xử lý hết lượt | Recoverer/DLT/DLQ | DLT/DLQ và workflow xử lý |
| Idempotency | Vẫn cần | **Vẫn cần** |

## 3. Thiết kế retry policy: lỗi nào, bao nhiêu lần, chờ bao lâu?

Trước khi chọn annotation hoặc broker policy, cần trả lời:

1. **Transient hay permanent?** Timeout, 503, temporary DB unavailability có thể retry. Invalid schema, business rule vi phạm cố định, quyền truy cập không có thường không nên.
2. **Max attempts bao gồm lần đầu?** Ví dụ **3 attempts** = lần đầu + **2 lần retry**. Không dùng mơ hồ “retry ba lần”.
3. **Backoff và jitter:** 1 s, 2 s, 4 s hoặc exponential có trần; thêm jitter khi nhiều consumer cùng chịu outage.
4. **Per-attempt timeout** và **deadline toàn event**: một network call không timeout có thể treo consumer vô hạn.
5. **Lỗi cuối đi đâu?** DLT/DLQ, trạng thái terminal, alert, replay procedure.
6. **Ai có quyền replay?** Không nên tự đẩy poison message trở lại main topic vô hạn.
7. **Có thể xử lý trùng không?** Downstream side effect phải idempotent.
8. **Có yêu cầu ordering theo orderId không?** Nếu có, retry topic có thể làm sai sequence.

Ví dụ **3 attempts** với backoff 1 s và 2 s:

```text
attempt 1 (main topic) -> fail
wait about 1 s
attempt 2 (retry topic) -> fail
wait about 2 s
attempt 3 (retry topic) -> success OR DLT
```

Các khoảng chờ là mục tiêu cấu hình, không phải thời gian thực nghiệm cam kết tuyệt đối. Total processing time còn gồm queue lag, consumer startup, rebalance, network và thời gian của từng attempt.

### Tránh retry nhầm lỗi

Bảng gợi ý, cần điều chỉnh theo hợp đồng downstream:

| Tình huống | Policy |
| --- | --- |
| HTTP 503, kết nối reset tạm thời | Retry có backoff/timeout |
| HTTP 429 | Retry theo `Retry-After` và giới hạn; đừng retry ngay |
| Deserialization/JSON không hợp lệ | Thường DLT/quarantine sớm, không retry vô nghĩa |
| Thiếu quyền 403 | Thường fail, cảnh báo cấu hình; không retry liên tục |
| Database deadlock | Cân nhắc retry **toàn transaction** mới khi an toàn |
| Lỗi lập trình cố định | Fail/alert, không retry vô hạn |
| Gateway thực hiện xong nhưng response mất | Chỉ retry an toàn khi có idempotency key hoặc cách đối soát |
| Consumer bị restart trước ack | Chuẩn bị cho redelivery dù attempt trước đã có side effect |

Một policy retry lỗi vĩnh viễn ba mươi lần không làm hệ thống “bền vững hơn”; nó chỉ kéo dài lỗi và tăng backlog.

## 4. Spring Kafka: hai cách xử lý lỗi thường dùng

### 4.1. DefaultErrorHandler: blocking retries trên listener container

Spring for Apache Kafka cung cấp `DefaultErrorHandler` và `DeadLetterPublishingRecoverer`.

Mã **minh họa cấu hình**, chưa là chương trình độc lập:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1000L, 2L));

    // Hai backoff attempts sau lần xử lý đầu: tối đa ba deliveries.
    handler.addNotRetryableExceptions(
            IllegalArgumentException.class);

    return handler;
}
```

Cần các imports từ `org.springframework.kafka.listener`, `org.springframework.kafka.core`, `org.springframework.util.backoff.FixedBackOff`, cùng một Spring context có `KafkaTemplate` đúng serializer và container factory sử dụng handler này.

Cụ thể:

- `FixedBackOff(1000L, 2L)` nghĩa là **hai retries** sau lần đầu, không phải ba retries.
- `DeadLetterPublishingRecoverer` chuyển record cuối cùng tới dead-letter destination theo cấu hình.
- Với default resolver trong Spring Kafka 3.3, DLT thường có hậu tố `-dlt` và dùng **cùng partition**; DLT topic cần đủ partitions nếu giữ nguyên partition.
- Nếu DLT publish thất bại mà recoverer không báo/quan sát lỗi đúng, có rủi ro mất record khi được đánh dấu recovered. Cần xem producer send result, cấu hình recoverer, timeout và tests cho đường lỗi.
- `DefaultErrorHandler` là container-level facility; không kết hợp tùy tiện với `@RetryableTopic` khiến policy retry chồng nhau và số attempts vượt dự kiến.

### 4.2. @RetryableTopic: non-blocking retry topics

Với Spring Kafka 3.3, thêm `@RetryableTopic` vào `@KafkaListener` để tạo retry/DLT topology:

```java
@RetryableTopic(
        attempts = "3",
        backoff = @Backoff(delay = 1000, multiplier = 2.0),
        include = TransientGatewayException.class)
@KafkaListener(
        topics = "notifications.commands",
        groupId = "notification-group")
public void onMessage(String eventId) {
    notificationService.deliver(eventId);
}

@DltHandler
public void onDeadLetter(String eventId) {
    deadLetterService.recordFailure(eventId);
}
```

Đây là **mã tích hợp minh họa**; yêu cầu `org.springframework.kafka.annotation`, `org.springframework.retry.annotation.Backoff`, Spring-managed bean và các service types tương ứng.

- `attempts = "3"` giới hạn tổng **ba lần xử lý**, bao gồm main attempt.
- `include` chỉ định lỗi phù hợp retry; lỗi không thuộc policy có thể đi thẳng DLT.
- `@DltHandler` định nghĩa việc xử lý record ở DLT trong **cùng listener class**; nó không tự “sửa” dữ liệu poison.
- Framework dùng retry topics và consumers để delay; **không giữ nguyên ordering** của main topic.
- Cần topic, permissions, group IDs, serializers, container factories và producer config phù hợp môi trường.
- Khả năng auto-create topics có thể phải tắt trong production nếu broker ACL/quản trị topic yêu cầu provisioning riêng.

**Spring Kafka version matters:** đọc đúng tài liệu của phiên bản đang sử dụng, không trộn các thuộc tính `@RetryableTopic` và cơ chế retry core khác phiên bản. Spring Kafka 3.3 là hệ sinh thái Spring Framework 6.2; Spring Kafka 4.x có thể thay đổi chi tiết API và cách cấu hình.

## 5. Thực hành Java 17+ với Kafka thật: retry thành công và DLT

Ví dụ đầy đủ này chạy trên **Spring Boot 3.4.6 / Spring Kafka 3.3.x**, **JDK 17+**, Maven và một Apache Kafka broker tại `localhost:9092`. Không cần tạo HTTP endpoint.

Ứng dụng publish hai message khác nhau:

- `evt-transient` thất bại tạm thời hai lần, đến lần thứ ba thành công.
- `evt-invalid` ném lỗi dữ liệu không thuộc `include`, nên chuyển DLT mà không lặp vô ích.

Chương trình dùng `CountDownLatch` để đợi **terminal outcomes**, không dùng `Thread.sleep` để đoán việc broker đã xử lý. Cuối cùng in một dòng summary với attempts/delivered/DLT. Đây là **integration demo cần Kafka broker**, không phải event bus thuần Spring Context.

### 5.1. Cấu trúc

```text
spring-kafka-broker-retry-demo/
├── pom.xml
└── src/main/
    ├── java/example/BrokerRetryDemo.java
    └── resources/application.properties
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.6</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>spring-kafka-broker-retry-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.kafka</groupId>
            <artifactId>spring-kafka</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.retry</groupId>
            <artifactId>spring-retry</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Version Spring Kafka thực tế được Spring Boot 3.4.6 dependency management chọn. Nếu dự án pin phiên bản riêng, phải kiểm tra tương thích giữa Boot, Framework, Kafka client và Spring Kafka.

### 5.3. src/main/resources/application.properties

```properties
spring.application.name=broker-retry-demo
spring.main.web-application-type=none

spring.kafka.bootstrap-servers=localhost:9092

spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer

spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer

logging.level.org.apache.kafka=WARN
logging.level.org.springframework.kafka=WARN
```

Trong demo chỉ dùng String payload để tập trung vào retry semantics. Production nên có event envelope với `eventId`, `schemaVersion`, `occurredAt` và ID đối tượng; đặt serializer/schema registry policy rõ ràng nếu chuyển sang JSON/Avro/Protobuf.

### 5.4. src/main/java/example/BrokerRetryDemo.java

```java
package example;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableKafka
public class BrokerRetryDemo {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(BrokerRetryDemo.class, args);
        SpringApplication.exit(context);
    }

    static final class TransientGatewayException
            extends RuntimeException {
        TransientGatewayException(String message) {
            super(message);
        }
    }

    @Component
    static class Outcome {
        private final Map<String, AtomicInteger> attempts =
                new ConcurrentHashMap<>();
        private final AtomicInteger delivered = new AtomicInteger();
        private final AtomicInteger deadLettered = new AtomicInteger();
        private final CountDownLatch done = new CountDownLatch(2);

        int nextAttempt(String id) {
            return attempts.computeIfAbsent(
                    id, ignored -> new AtomicInteger())
                    .incrementAndGet();
        }

        int count(String id) {
            AtomicInteger value = attempts.get(id);
            return value == null ? 0 : value.get();
        }

        void delivered() {
            delivered.incrementAndGet();
            done.countDown();
        }

        void deadLettered() {
            deadLettered.incrementAndGet();
            done.countDown();
        }
    }

    @Component
    static class NotificationConsumer {
        private final Outcome outcome;

        NotificationConsumer(Outcome outcome) {
            this.outcome = outcome;
        }

        @RetryableTopic(
                attempts = "3",
                backoff = @Backoff(
                        delay = 1000,
                        multiplier = 2.0),
                include = TransientGatewayException.class,
                autoCreateTopics = "true",
                numPartitions = "1",
                replicationFactor = "1")
        @KafkaListener(
                topics = "notifications.commands",
                groupId = "notifications-demo")
        public void receive(String eventId) {
            int attempt = outcome.nextAttempt(eventId);

            if ("evt-transient".equals(eventId) && attempt < 3) {
                throw new TransientGatewayException(
                        "gateway unavailable");
            }

            if ("evt-invalid".equals(eventId)) {
                throw new IllegalArgumentException(
                        "invalid payload");
            }

            if ("evt-transient".equals(eventId)) {
                outcome.delivered();
            }
        }

        @DltHandler
        public void onDeadLetter(String eventId) {
            if ("evt-invalid".equals(eventId)) {
                outcome.deadLettered();
            }
        }
    }

    @Bean
    ApplicationRunner sendDemo(
            KafkaTemplate<String, String> template,
            Outcome outcome) {

        return args -> {
            template.send(
                    "notifications.commands",
                    "evt-transient",
                    "evt-transient")
                    .get(10, TimeUnit.SECONDS);

            template.send(
                    "notifications.commands",
                    "evt-invalid",
                    "evt-invalid")
                    .get(10, TimeUnit.SECONDS);

            if (!outcome.done.await(60, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Kafka retries/DLT did not complete");
            }

            System.out.println(
                    "summary: transientAttempts="
                    + outcome.count("evt-transient")
                    + " invalidAttempts="
                    + outcome.count("evt-invalid")
                    + " delivered="
                    + outcome.delivered.get()
                    + " dlt="
                    + outcome.deadLettered.get());
        };
    }
}
```

**Chạy broker** trong một terminal với Docker (chỉ dùng cho demo local; không phải cấu hình production HA/secure):

```bash
docker run --rm --name broker-retry-local -p 9092:9092 apache/kafka:3.8.1
```

Image Kafka JVM này có hướng dẫn chính thức chạy standalone trên cổng mặc định `9092`. Kiểm tra Docker đã hoạt động và broker sẵn sàng trước khi chạy Maven. Trong một terminal khác, tại thư mục dự án:

```bash
mvn -q spring-boot:run
```

Khi broker khả dụng, topic có thể được tạo và người tiêu thụ hoàn thành trong timeout, dòng **summary của chương trình** có dạng:

```text
summary: transientAttempts=3 invalidAttempts=1 delivered=1 dlt=1
```

Spring Boot/Kafka có thể in thêm log. **Thứ tự xử lý bên trong listener không phải cam kết** vì có nhiều retry/DLT consumers. Phần cần kiểm tra là terminal state và số attempts trên cùng một logical event trong lần chạy demo với topic/group sạch.

**Giới hạn thực hành:**

1. Đây là ví dụ dùng **Kafka thật** nên không chạy được nếu không có broker, Docker/Maven/JDK hoặc ACL phù hợp. Không coi lệnh `mvn compile` thành công là đã kiểm chứng retry end-to-end.
2. `@RetryableTopic` tạo hoặc sử dụng main/retry/DLT topics theo cấu hình và version. Production nên provisioning topics qua IaC/admin; không phụ thuộc auto-create khi môi trường cấm.
3. `Outcome` là **in-memory recorder chỉ để demo**, không phải bảng inbox/idempotency. Dữ liệu không survive restart và không đồng bộ giữa nhiều consumers.
4. Với topic đã có message từ lần chạy trước hoặc một consumer group chia sẻ, các bộ đếm demo có thể không phản ánh đúng chỉ hai message được tạo. Dùng Kafka instance/topic group riêng cho thực hành và làm sạch môi trường trước lần chạy.
5. `onDeadLetter` đang chỉ đếm message. Production phải ghi đầy đủ lý do vào failure store/quarantine, gửi cảnh báo và có workflow replay có kiểm soát.
6. Message `evt-invalid` được đưa đến DLT sau lần xử lý đầu vì exception không thuộc nhóm retry. `evt-transient` thành công trong attempt thứ ba sau hai lần chuyển sang retry topic.
7. Kafka producer send được đợi completion ở demo; **việc producer hoàn tất không chứng minh business side effect của consumer đã hoàn tất**, nên còn phải đợi terminal latch.
8. Thời gian backoff 1 s/2 s không phải SLA chính xác từng millisecond: queue lag, poll, scheduling và load ảnh hưởng thời gian giao thực tế.

Muốn test deterministic hơn, có thể dùng `spring-kafka-test` và `@EmbeddedKafka` trong JUnit 5 để chạy broker nhúng, chờ latch rồi assert attempts; không dùng `Thread.sleep(...)` để đoán event đã hoàn thành. Khi cần kiểm tra durability thật qua restart, cần chạy broker persistent và test khởi động lại consumer/process riêng.

## 6. Kafka offset, ack và lỗi forwarding: ranh giới đảm bảo

Kafka là append-only log; consumer group theo dõi offsets. Một record **không bị xóa khỏi topic khi consumer ack**, mà vẫn được giữ theo Kafka topic retention/compaction policy. Cơ chế khác RabbitMQ, nơi ack thường xác nhận xử lý một delivery để broker không giao lại chính message đó.

Một số tình huống:

```text
Consumer đọc record at offset 100
  |
  +-- thực hiện side effect thành công
  |
  +-- crash trước khi offset được commit
  |
  v
Restart -> offset 100 có thể bị giao lại
           -> side effect có thể chạy lần thứ hai
```

Trong non-blocking retry flow:

```text
Main record failure
    |
    +-- framework forward sang retry topic
    |
    +-- main consumer có thể tiến sang record tiếp theo
    |
    +-- retry consumer xử lý ở thời điểm đến hạn
```

Giữa **forwarding thành công** và **commit vị trí main consumer** có những failure windows nếu không có một cơ chế giao dịch/đảm bảo riêng. Không tự suy diễn rằng bật `@RetryableTopic` đồng nghĩa atomic end-to-end giữa database, Kafka topics và external API. Nếu recoverer publish vào DLT thất bại, policy phải bảo đảm **không âm thầm bỏ record**.

### Blocking retry và Kafka transactions

Khi dùng Kafka container transactions, chiến lược xử lý lỗi có thể khác:

- Với record listener không transactional, `DefaultErrorHandler` có thể quản lý backoff/recovery.
- Với container transactional, một lựa chọn là `DefaultAfterRollbackProcessor` để xử lý records sau khi transaction rollback.
- Spring Kafka 3.3 **không cho kết hợp non-blocking retry topics với container transactions**. Cần chọn thiết kế khác nếu atomic consumption/production Kafka transaction là yêu cầu.
- Kafka transaction **không tự tạo transaction chung với database và dịch vụ ngoài**. Cần đánh giá từng resource và failure window.

Không ghép `@RetryableTopic` với cấu hình transactional error handlers chỉ vì cả hai đều liên quan retry.

### Ordering theo aggregate

Ví dụ consumer nhận trên một partition:

```text
Order-42 status version=1 -> lỗi, sang retry topic
Order-42 status version=2 -> main consumer xử lý thành công
Order-42 version=1 -> retry xong sau version=2
```

Read model có thể bị kéo về version cũ nếu update không có kiểm tra sequence. Các cách xử lý:

- Dùng **aggregate version** và bỏ qua event có version thấp hơn trạng thái đã áp dụng.
- Giữ blocking retry cho luồng yêu cầu strict ordering.
- Tách logical processing theo key, partition và concurrency policy rõ.
- Thiết kế handler có **commutative/idempotent semantics** nếu có thể.
- Dùng workflow riêng khi thứ tự là business invariant không thể thỏa thuận.

Kafka partition ordering chỉ áp dụng **trong một partition của cùng topic**; chuyển một message sang retry topic làm thay đổi phạm vi đảm bảo thứ tự đó.

## 7. Spring AMQP/RabbitMQ: requeue, DLX, TTL và DLQ

Với RabbitMQ, listener sử dụng `@RabbitListener` của Spring AMQP, và container sẽ xử lý exception/ack/rejection theo cấu hình.

### 7.1. Requeue ngay có thể tạo vòng lặp nóng

Mã minh họa:

```java
@RabbitListener(queues = "notifications.main")
public void receive(String payload) {
    notificationService.deliver(payload);
}
```

Nếu listener liên tục ném exception, một cấu hình requeue có thể làm broker giao message lại **rất nhanh**. Nếu queue có poison message, CPU/logs có thể tăng, việc xử lý message lành bị nghẽn.

Spring AMQP cho phép cấu hình `defaultRequeueRejected=false` hoặc ném `AmqpRejectAndDontRequeueException` để từ chối message **không requeue**. Broker có thể chuyển message qua **Dead Letter Exchange (DLX)** nếu queue được cấu hình. Nếu không có DLX phù hợp, message bị từ chối có thể **bị bỏ**.

```java
@RabbitListener(queues = "notifications.main")
public void receive(String payload) {
    try {
        notificationService.deliver(payload);
    } catch (InvalidPayloadException ex) {
        throw new AmqpRejectAndDontRequeueException(
                "permanent invalid payload", ex);
    }
}
```

Đây là **mã tích hợp minh họa**, cần Spring AMQP, các lớp ứng dụng/import và container factory hợp lệ. Cách ném exception có ý nghĩa dưới **container-managed acknowledgement**; khi tự dùng manual acknowledgements, phải áp dụng đúng `basicAck`/`basicNack` và error-handling contract, không trộn hai mô hình tùy tiện.

### 7.2. Topology retry bằng TTL + DLX

Một kiến trúc thường gặp:

```text
Exchange notifications.exchange
   |
   +-- routing key notification.main
           |
           v
       notifications.main.queue
           |
           +-- consumer fail / reject(requeue=false)
           |
           v
      retry DLX / retry queue
      notifications.retry.30s
      (TTL = 30 s, dead-letter route trở lại main)
           |
           +-- TTL expires
           |
           v
      notifications.exchange
           |
           v
      notifications.main.queue

      Sau khi vượt budget hoặc lỗi permanent:
           |
           v
      notifications.dead.queue  (DLQ, manual review)
```

**Mô hình chỉ minh họa topology**. Muốn an toàn phải thiết lập đầy đủ bindings, routing keys, queue policies, TTL và max-attempt checking. Nếu chỉ tạo vòng DLX từ main sang retry rồi trở lại main mà **không có bộ đếm/budget**, hệ thống có thể retry vô hạn.

RabbitMQ cung cấp metadata như `x-death` cho dead-letter transitions. Tuy nhiên **không được tự giả định** bộ đếm `x-death` luôn giống “số lần handler chạy”; semantics thay đổi theo lý do dead-letter, queue, version và cách consumer republish. Không cho client tự tạo `x-death` để điều khiển độ tin cậy vì đây là header do broker quản lý.

Trong Spring AMQP 3.2 có API `MessageProperties.getRetryCount()` và `incrementRetryCount()` để hỗ trợ luồng retry/republish được quản lý. Với retry qua DLX, framework có thể ánh xạ thông tin `x-death.count` thành retry count trong những tình huống tương ứng. Nếu republish bằng application, phải cập nhật retry count **có chủ đích** theo hợp đồng. Mỗi dự án cần test thực tế với broker version đang dùng.

### 7.3. Quorum queues và delivery limit

RabbitMQ **quorum queues** có cơ chế xử lý poison message và **delivery limit**; mặc định delivery limit là 20 từ RabbitMQ 4.0 (khác 3.x). Nếu vượt giới hạn, message có thể bị dead-lettered hoặc dropped tùy cấu hình DLX.

**Chi tiết theo phiên bản rất quan trọng:** Tài liệu RabbitMQ 4.3 phân biệt `delivery-count` với `acquired-count`, và một số kiểu `nack/requeue` không tăng delivery-count như bạn có thể suy đoán. Vì vậy không thiết kế budget bằng cách chỉ nhìn cờ `redelivered` hoặc đoán mọi requeue đều tăng broker count.

RabbitMQ 4.3 còn hỗ trợ **delayed retry trên quorum queue** với các policy điều khiển; đây là cơ chế **khác** retry TTL/DLX truyền thống. Chọn một chiến lược nhất quán theo version, không vô tình đặt nhiều lớp retry gây nhân số attempts.

RabbitMQ DLX có những chế độ reliability khác nhau, gồm khả năng dead-lettering `at-least-once` đối với quorum queues khi cấu hình phù hợp. Không mặc định mọi DLX chuyển message thành công một cách bền vững trong mọi tình huống. Cần theo dõi broker confirms, capacity và hàng đợi đích.

### 7.4. Phân biệt retry local ở consumer và retry over broker

Spring AMQP còn có `RetryOperationsInterceptor`/Spring Retry, cho phép nhiều attempts **trong cùng listener invocation**. Điều đó khác với việc message được lưu vào **retry queue** rồi broker giao lại sau vài phút.

| Cơ chế AMQP | Cách hoạt động | Đặc tính |
| --- | --- | --- |
| Listener interceptor retry | Gọi lại logic trên consumer thread, có backoff | Ngắn, có thể chặn consumer |
| Requeue trực tiếp | Message trở lại queue ngay | Dễ loop nóng nếu không chặn |
| TTL + DLX | Message chờ trong retry queue rồi quay lại main | Cần topology/attempt budget |
| Quorum delayed retry (version hỗ trợ) | Broker giữ message tới hạn retry | Phụ thuộc chính sách/quorum/version |
| DLQ/recoverer | Đưa message lỗi vào nơi xử lý riêng | Cần quan sát, kiểm tra, replay có kiểm soát |

Không nên ghi “RabbitMQ tự retry ba lần” nếu thực tế bạn đang dùng một interceptor Spring trong JVM. Cần xác định nơi **sở hữu lịch retry và trạng thái attempt**.

## 8. Outbox: từ ApplicationEventPublisher sang broker không mất khoảng trống

Một source event trong Spring có thể được publish khi transaction business chưa commit. Nếu listener gửi Kafka ngay:

```text
BEGIN T1
  UPDATE order status=APPROVED
  publishEvent(OrderApproved)
       -> Kafka send thành công
  T1 ROLLBACK
```

Consumer ngoài có thể thấy `OrderApproved` dù database cuối cùng không phê duyệt đơn. Ngược lại, publish sau commit mà process chết trước send thì **database đã commit nhưng broker không có message**.

Khi yêu cầu “mỗi thay đổi business đã commit phải tạo message để consumer xử lý”, hãy xem **Transactional Outbox**:

```text
Transaction T1:
    UPDATE orders SET status='APPROVED'
    INSERT INTO outbox_events(
        event_id, event_type, aggregate_id,
        payload, status='PENDING', created_at)
    COMMIT T1
            |
            v
Outbox worker:
    đọc PENDING, claim atomically
    publish đến broker, xác nhận send
    mark SENT hoặc retry có backoff
            |
            v
Kafka/RabbitMQ:
    consumer process / broker-level retry / DLT/DLQ
```

Điểm cần giữ:

- Outbox record và business data được ghi **cùng một transaction database**.
- Outbox dispatcher phải có **trạng thái/retry**, có thể resume sau restart.
- Publish success nhưng crash trước mark SENT có thể **gửi trùng**: downstream idempotency bắt buộc.
- Nếu use case có ordering theo aggregate, sequence/version và partition key phải được chọn có chủ đích.
- **Outbox retry** (producer gửi tới broker) và **broker retry** (consumer xử lý thất bại) là **hai hàng đợi trách nhiệm khác nhau**. Cần metric và deadline riêng.
- `@TransactionalEventListener(AFTER_COMMIT)` có thể là cách kích hoạt tối ưu để “đánh thức” worker, nhưng không nên là **duy nhất** cách phát hiện message pending nếu độ tin cậy là yêu cầu; worker vẫn cần poll/quét trạng thái bền vững.

Một event envelope đi vào broker có thể có:

```json
{
  "eventId": "evt-85f",
  "eventType": "OrderApproved",
  "schemaVersion": 1,
  "aggregateId": "order-42",
  "aggregateVersion": 7,
  "occurredAt": "2026-01-10T00:00:00Z"
}
```

Các giá trị là minh họa; không mặc định lưu toàn bộ JPA entity/PII trong event. Event ID phải ổn định **qua retry topic, DLT và replay** để nhận dạng cùng logical event.

## 9. Idempotent consumer: không để retry tạo side effect trùng

Một timeout không nhất thiết có nghĩa hệ thống ngoài chưa xử lý request:

```text
consumer -> Payment Gateway: charge(eventId=evt-85f)
gateway: charge thành công
consumer: mất response, xem là timeout
broker retry: cùng message được xử lý lần nữa
consumer -> gateway: charge(eventId=evt-85f) lần nữa
```

Nếu không có idempotency contract, có nguy cơ charge hai lần. Retry đúng chỉ khi side effect có cơ chế đảm bảo an toàn.

### 9.1. Dùng stable idempotency key

Với downstream API hỗ trợ, gửi cùng `Idempotency-Key` cho mọi attempts:

```text
Idempotency-Key: evt-85f
```

Không tạo key mới mỗi lần attempt. Một số API chỉ lưu idempotency key trong thời hạn nhất định; phải đối chiếu **thời gian retry và replay** với thời hạn đó.

### 9.2. Inbox table cho side effect database

Một thiết kế thực tế:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Với một transaction đơn DB, handler có thể thử insert marker với unique constraint, rồi cập nhật business table trong **cùng transaction**. Nếu marker đã tồn tại, bỏ qua duplicate theo policy. Một thao tác chỉ gọi `SELECT EXISTS(...)` rồi mới INSERT có thể race khi có nhiều workers; unique key và transaction boundary mới là phần bảo vệ quan trọng.

Một số side effects ở ngoài DB (email, payment, webhook) cần **idempotency ở API downstream** hoặc workflow đối soát; inbox local không thể tự undo một request đã được dịch vụ ngoài xử lý trước khi local transaction rollback.

## 10. DLT/DLQ không phải “thùng rác tự xóa”

DLT/DLQ là nơi **cách ly message lỗi** để tránh chặn pipeline chính, không phải lời khẳng định “hệ thống đã xử lý thành công”.

Một workflow tốt:

1. Lưu event ID, topic/queue nguồn, consumer, attempt count, loại lỗi, timestamp, trace/correlation ID.
2. Tránh ghi secrets/PII nhạy cảm vào error headers/logs mà không có nhu cầu và quyền thích hợp.
3. Báo metric/alert cho số lượng message vào DLT, age lớn nhất, tốc độ backlog.
4. Phân loại message có thể sửa bằng redeploy/config/migration hay phải được xử lý thủ công.
5. Cung cấp **replay có phê duyệt** với cùng event ID và giới hạn attempts mới (hoặc một revision được ghi rõ), tránh vòng loop từ DLT về main.
6. Ghi lại ai replay, tại sao và kết quả sau replay; lưu lại failure history cần thiết theo retention policy.
7. Thiết lập topic/queue retention phù hợp: DLT giữ quá ngắn có thể làm mất bằng chứng trước khi team xử lý; giữ mãi có thể tăng rủi ro dữ liệu.

Với hệ thống có strict ordering, replay record cũ sau nhiều record mới còn làm lộ vấn đề thứ tự. Handler cần aggregate version guard, hoặc replay trong quy trình tái dựng có kiểm soát.

### Failure state rõ ràng

```text
NEW -> PROCESSING -> SUCCEEDED
          |
          +-- TRANSIENT_FAILED -> RETRY_SCHEDULED
          |                            |
          |                            +-- PROCESSING
          |
          +-- EXHAUSTED -> DLT_PENDING_REVIEW
                                |
                                +-- REPLAY_APPROVED -> PROCESSING
                                |
                                +-- QUARANTINED / COMPENSATED
```

Không đặt “DLT đã nhận record” là “thanh toán đã thành công”. Đây là **hai trạng thái nghiệp vụ khác nhau**.

## 11. Observability: theo dõi delivery, attempts và lag

Một hệ thống có retry topic/queue có thể trả HTTP 200 rất nhanh nhưng backlog tăng liên tục. Cần đo **end-to-end** thay vì chỉ request latency.

| Signal | Giải thích |
| --- | --- |
| Producer send failures/confirm latency | Outbox worker đưa được message vào broker chưa? |
| Consumer processing success/failure | Handler có xử lý được message không? |
| Attempts per logical event | Số lần nhận và xử lý một event, không nhầm với event mới |
| Retry queue/topic lag | Số message chờ retry và chờ đã quá hạn |
| Oldest pending age | Event chờ lâu nhất kể từ lúc được tạo |
| DLT/DLQ rate | Số message hết budget hoặc bị phân loại permanent |
| DLQ replay success rate | Replay có giải quyết lỗi hay đang tạo loop |
| Kafka consumer group lag | Khoảng cách offset giữa consumer và topic log |
| RabbitMQ ready/unacked/requeue | Trạng thái queue và delivery trên broker |
| Broker publish/republish errors | Lỗi trên đường forward retry/DLT |
| Downstream timeout/error rate | Nguyên nhân gây retry storm |
| Idempotency duplicate suppression | Số lần redelivery được bỏ qua an toàn |

Metric labels nên có cardinality hữu hạn: `topic`, `consumerGroup`, `errorCategory`, `outcome`. Không đưa `eventId`, email hoặc order ID vào mọi low-cardinality metric tag. Các IDs hữu ích trong logs/traces và audit records đã được bảo vệ.

Spring Framework `@EventListener` không tự tạo observation cho mọi listener; Spring Kafka/AMQP có hạ tầng observability riêng tùy version và cấu hình. Không mặc định chỉ bật Actuator là mọi retry topic và DLQ sẽ có SLO dashboard hoàn chỉnh.

### Ví dụ dashboard

```text
Kafka notifications:
  - main consumer lag:        120 records
  - retry topics lag:          45 records
  - DLT unreviewed:             3 records
  - p95 event completion:      8.4 seconds
  - retries exhausted/hour:     2
```

Các con số là **dữ liệu minh họa**. Một retry backlog tăng nhanh cùng downstream 503 rate tăng có thể báo hiệu outage; cần giảm concurrency/rate, tăng backoff, kích hoạt circuit breaker, hoặc tạm dừng replay thay vì tăng retries vô hạn.

## 12. Tính toán capacity và retry storm

Giả sử một consumer nhận `1.000` logical events mỗi phút, downstream đang lỗi toàn bộ. Với `maxAttempts=3`, nếu không có circuit breaker và mỗi event đều thử hết lượt, hệ thống có thể tạo tới **3.000 processing attempts/phút** (nếu hạ tầng đủ khả năng thực hiện) thay vì 1.000 calls.

Những yếu tố cần xem:

- `maxAttempts` và `maxElapsedTime`: tổng budget cho một logical event.
- `backoff`/`jitter`: giãn tải để downstream phục hồi.
- `consumer concurrency`, `prefetch` (RabbitMQ), Kafka partitions: số công việc có thể đồng thời.
- `queue length/storage limits`: retry messages chiếm disk/retention, có thể bị drop khi vượt policy.
- `rejection`/`dead-letter` behavior: đừng bỏ message khi quá tải mà không ghi nhận.
- `circuit breaker/bulkhead`: giảm gọi vô ích vào hệ thống đang hỏng.
- `consumer lag/SLA`: sau outage, backlog bao lâu mới được xử lý xong?
- `hot partitions`: một aggregate key quá phổ biến có thể gây nghẽn partition dù tổng cluster còn rảnh.

Một policy retry tốt thường có **hai giới hạn**: tối đa lần thử và tối đa thời gian sống của công việc. Không nên tiếp tục xử lý một message nhiều ngày nếu hành động đã mất ý nghĩa (ví dụ mã OTP hết hạn), trừ khi có lý do lưu và điều tra riêng.

## 13. Kiểm thử broker retry đúng cách

Không chỉ viết unit test handler rồi xem như toàn hệ thống đã bền vững. Các lớp test cần thiết:

### 13.1. Unit test business handler

- Lỗi transient được phân loại đúng.
- Lỗi permanent không bị retry.
- Side effect idempotent khi nhận duplicate event ID.
- Aggregate version guard ngăn event cũ ghi đè state mới.
- Payload schema/migration hoạt động với event lịch sử.

### 13.2. Spring Kafka integration test

Dùng `spring-kafka-test`, `@EmbeddedKafka` hoặc broker chạy container/test environment:

1. Publish message chỉ một lần.
2. Consumer lần đầu ném transient exception, assert đúng attempts và delay *theo khoảng*.
3. Consumer sau N attempts thành công, assert side effect **một lần**.
4. Permanent error đi DLT sớm; assert DLT payload, headers, metadata.
5. Khi hết max attempts, assert không còn retry vô hạn.
6. Tắt consumer rồi khởi động lại, kiểm tra offset/ack và redelivery.
7. Simulate crash sau side effect nhưng trước offset commit; verify idempotency.
8. Nếu thứ tự theo key quan trọng, publish version 1 rồi 2 và kiểm tra behavior khi version 1 retry.
9. Khi forwarding sang retry/DLT lỗi do ACL/topic down, assert message không bị mất âm thầm.
10. Test thực với container transactions **tách khỏi** non-blocking `@RetryableTopic` nếu kiến trúc cần.

Đừng assert mili-giây chính xác của backoff trong test bất đồng bộ. Dùng deadline hợp lý, latch/`Awaitility` (nếu có dependency), kiểm tra trạng thái terminal và approximate timing.

### 13.3. Spring AMQP/RabbitMQ integration test

Có thể dùng Testcontainers RabbitMQ để kiểm chứng với broker thật:

- `defaultRequeueRejected=true` và handler luôn lỗi có gây redelivery storm không?
- `AmqpRejectAndDontRequeueException` có route sang DLX/DLQ đúng không?
- TTL retry queue có đưa message trở lại main sau thời gian dự kiến không?
- Budget ở `x-death`/`retry_count` đúng với **version broker thực tế**?
- Khi DLX đích bị xóa, có mất message không theo dead-letter strategy?
- Quorum delivery-limit có hoạt động như dự kiến với kiểu `nack`/`reject` đang dùng?
- Publish confirms và ack có được phối hợp an toàn?
- Manual ack khi gặp lỗi bảo đảm không ack nhầm trước side effect?

Không trộn “test consumer code” với “test broker topology”. Muốn chứng minh message bền vững, phải test queue/topic/broker restart hoặc failure windows; mock `RabbitTemplate` không đủ.

### 13.4. Chaos và load test

- Downstream 503 trong 5 phút, sau đó hồi phục.
- Broker mất kết nối tạm thời giữa consumer acknowledgement và producer forwarding.
- Message đến DLT khi ACL không cho publish.
- Consumer crash sau DB commit nhưng trước Kafka offset commit.
- Retry topic bị đầy hoặc retention ngắn hơn retry delay.
- RabbitMQ quorum leader failover/queue policy thay đổi.
- Poison message chiếm một partition, khiến main lag tăng.
- Operator replay DLT trong lúc consumer mới vẫn hoạt động.

Đánh giá **không chỉ request p95** mà còn thời gian xử lý event cuối cùng, độ trễ backlog recovery, số lost/duplicate side effects và khả năng điều tra.

## 14. Lỗi thường gặp và cách tránh

**1. Tưởng `@EventListener` in-process có Kafka/RabbitMQ retries.**  
Không. Cần bridge/publish message tới broker và consumer riêng.

**2. Dùng `@TransactionalEventListener(AFTER_COMMIT)` làm bảo đảm durable delivery.**  
Callback đúng phase nhưng process có thể chết trước khi gửi. Nếu event không được mất, cân nhắc outbox.

**3. Dùng non-blocking retry topics cho dữ liệu cần strict per-key order.**  
Record lỗi có thể đi vòng qua retry topic trong khi record mới được xử lý trước. Dùng version guard hoặc chiến lược khác.

**4. Dùng `@RetryableTopic` cho batch listener hoặc Kafka container transactions trong Spring Kafka 3.3.**  
Không được hỗ trợ theo tài liệu. Cần chọn DefaultErrorHandler/transaction-aware recovery khác.

**5. Không giới hạn requeue với RabbitMQ.**  
Poison message có thể chạy vòng nóng và gây nghẽn. Dùng DLX/TTL/broker policy/attempt counter phù hợp.

**6. Tin `x-death.count` luôn là số lần listener chạy.**  
Sai trong nhiều topology và version; phải test headers và broker behavior.

**7. Cấu hình broker delivery limit nhưng không có DLQ.**  
Message vượt giới hạn có thể bị bỏ, gây mất dữ liệu nghiệp vụ; cần dead-letter topology và alerts.

**8. “Retry thành công” dù việc gửi vào DLT thất bại.**  
Nếu recoverer/producer không báo lỗi đúng hoặc ack trước, message có thể bị mất. Test recovery failure.

**9. Một logical event có event ID mới ở mỗi lần retry.**  
Phá dedup và correlation, có thể nhân đôi side effects. Giữ ID ổn định qua main/retry/DLT/replay.

**10. Dựa vào Kafka offsets để khẳng định side effect chính xác một lần.**  
Commit offset và DB/payment side effect có failure window; thiết kế idempotency.

**11. Đặt attempts vô hạn để “không mất message”.**  
Có thể giữ head-of-line blocking, tạo retry storm và trì hoãn điều tra poison messages.

**12. DLT chỉ ghi một log rồi xóa.**  
Không có nơi review/replay, thiếu runbook và retention; mất khả năng phục hồi.

**13. Retry trước khi biết lỗi là transient hay permanent.**  
400/invalid schema thường không tự hồi phục; phải phân loại và chuyển quarantine sớm.

**14. Không đo lag của retry topic/queue.**  
Main consumer vẫn chạy bình thường nhưng event completion SLA có thể đang thất bại.

**15. Không xử lý yêu cầu bảo mật/quyền truy cập cho DLT.**  
DLT có thể chứa payload nhạy cảm hoặc headers lỗi; cần ACL, encryption, retention và masking tương ứng.

**16. Cấu hình hai retry layers không kiểm soát.**  
Ba attempts trong service kết hợp ba attempts ở container có thể tạo **chín calls** cho cùng event; cần một tổng retry budget rõ.

## 15. Checklist đưa vào production

Trước khi bật retry ở tầng broker, xác nhận:

1. **Event contract:** topic/queue, event ID, schema version, aggregate key/version, headers ổn định?
2. **Source atomicity:** DB update và việc phát message có outbox/transaction phù hợp không?
3. **Producer confirmation:** send failures được quan sát và retry có giới hạn?
4. **Consumer errors:** transient/permanent exception classification có test?
5. **Max attempts:** tổng số attempts hay retries sau lần đầu; bao nhiêu layers tham gia?
6. **Backoff:** delay, multiplier, jitter, max delay, queue lag và deadline?
7. **Broker semantics:** Kafka offset/partition hoặc RabbitMQ ack/requeue/DLX cụ thể?
8. **Compatibility:** Spring Kafka/AMQP và broker versions có hỗ trợ tính năng đang chọn?
9. **Ordering:** cùng aggregate có thể bị xử lý đảo thứ tự do retry topic không?
10. **Idempotency:** crash giữa side effect và ack/offset commit có tạo trùng không?
11. **DLT/DLQ:** retention, ACL, alerts, routing, replay approval và audit có rõ?
12. **Capacity:** poison message, outage, broker storage, partitions/prefetch và retry storm?
13. **Observability:** attempts, terminal success, failures, lag, oldest message age, DLQ backlog?
14. **Operations:** nếu broker down hoặc topic missing, có cơ chế recovery/runbook và không ack nhầm?
15. **Testing:** đã chạy integration/chaos test với broker thật, mô phỏng restart và failure window?

## 16. Câu hỏi tự đánh giá

**1. `ApplicationEventPublisher.publishEvent(...)` có tự lưu message vào Kafka hay RabbitMQ không?**  
Không. Spring application event trong JVM khác với broker messaging. Cần producer/bridge riêng.

**2. Kafka `@RetryableTopic(attempts = "3")` tương ứng mấy lần xử lý?**  
Tối đa **ba attempts**, bao gồm lần đầu. Nếu lỗi retryable ở cả ba, record có thể chuyển DLT theo policy.

**3. Vì sao retry topic có thể phá ordering?**  
Một record lỗi được chuyển sang topic khác chờ backoff, còn record mới trong main topic có thể được xử lý trước.

**4. `DefaultErrorHandler(new FixedBackOff(1000, 2))` tạo bao nhiêu retries?**  
Hai lần retry sau lần xử lý đầu, thường cho tối đa ba lần trước recovery.

**5. RabbitMQ `requeue=true` có phải một chính sách backoff an toàn không?**  
Không. Nó có thể lập tức giao lại, tạo hot loop. Cần DLX/TTL/delayed retry và budget.

**6. DLT có nghĩa business operation đã thành công không?**  
Không. DLT nghĩa message đang ở trạng thái lỗi cần review/replay hoặc một quyết định xử lý khác.

**7. Vì sao cần idempotent consumer nếu broker đã đảm bảo giao message bền vững?**  
Vì consumer có thể xử lý side effect xong rồi crash trước ack/offset commit; broker sẽ giao lại.

**8. Khi yêu cầu business DB commit thì message phải có trên broker, nên dùng gì?**  
Một pattern phổ biến là **Transactional Outbox**: ghi outbox cùng business transaction, worker gửi broker rồi retry.

**9. Spring Kafka 3.3 có hỗ trợ `@RetryableTopic` với batch listeners và container transactions không?**  
Không, theo tài liệu non-blocking retry của phiên bản đó.

**10. Khi nào chọn blocking retry thay vì retry topics?**  
Khi lỗi thường ngắn, cần giữ ordering theo partition và chấp nhận tạm chặn consumer; phải có max attempts/backoff và recovery.

## 17. Tài liệu chính thức

- [Spring Framework — Application Events và @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Kafka 3.3 — Non-blocking Retries (@RetryableTopic)](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic.html)
- [Spring Kafka 3.3 — Retry Topic Configuration](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic/retry-config.html)
- [Spring Kafka 3.3 — Error Handlers và DeadLetterPublishingRecoverer](https://docs.spring.io/spring-kafka/reference/3.3/kafka/annotation-error-handling.html)
- [Spring Kafka 3.3 — @RetryableTopic Javadoc](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/annotation/RetryableTopic.html)
- [Spring AMQP 3.2 — Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/3.2/amqp/resilience-recovering-from-errors-and-broker-failures.html)
- [Spring AMQP 3.2 — Listener Error Handling](https://docs.spring.io/spring-amqp/reference/3.2/amqp/receiving-messages/async-annotation-driven/error-handling.html)
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
- [RabbitMQ — Quorum Queues, delivery-limit và delayed retry](https://www.rabbitmq.com/docs/quorum-queues)
- [Apache Kafka 3.8 — Docker Quick Start](https://kafka.apache.org/38/getting-started/docker/)


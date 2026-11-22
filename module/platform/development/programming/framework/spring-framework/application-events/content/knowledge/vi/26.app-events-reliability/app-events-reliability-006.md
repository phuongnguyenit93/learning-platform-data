# Chuyển event nội bộ sang message broker trong Spring Application Events

## 1. Vì sao cần chuyển event ra ngoài ứng dụng?

Spring Framework cung cấp `ApplicationEventPublisher` để một thành phần phát sự kiện và những thành phần khác trong **cùng ApplicationContext/tiến trình** có thể phản ứng. Ví dụ, khi tạo đơn hàng thành công, ứng dụng phát `OrderCreated`; một listener cập nhật dữ liệu đọc, một listener chuẩn bị gửi email.

Cơ chế này hữu ích để giảm phụ thuộc trực tiếp giữa các module, nhưng **không phải message broker bền vững**:

- Event thường được phân phối trong bộ nhớ; process chết có thể làm công việc chưa xử lý bị mất.
- Mặc định `@EventListener` được gọi đồng bộ; một listener lỗi có thể ảnh hưởng publisher.
- Một listener `@Async` có thể chạy trên pool khác, nhưng task trong executor không tự bền vững sau restart.
- Hệ thống khác không tự nhận được event chỉ vì application đã gọi `publishEvent(...)`.
- Spring event không tự cung cấp xác nhận broker, dead-letter queue, replay hay consumer offset.

Khi nghiệp vụ cần thông báo sang **service khác**, ví dụ Billing, Shipping hoặc Analytics, ta thường thêm một **integration adapter** để chuyển domain/application event nội bộ thành **integration event** theo hợp đồng dữ liệu và gửi vào RabbitMQ, Kafka hoặc broker tương ứng.

Bài này giải thích cách tổ chức adapter, đưa ra một demo **Spring Boot + RabbitMQ chạy được**, sau đó phân tích mức độ tin cậy của ba cách gửi: trực tiếp, sau commit và **transactional outbox**.

## 2. Phân biệt internal event, integration event và broker message

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Internal/domain event | Một sự thật đã xảy ra trong mô hình nghiệp vụ | `OrderCreated(orderId, amount)` |
| Application event mechanism | Phân phối đối tượng giữa các bean trong một Spring context | `publisher.publishEvent(event)` |
| Integration adapter/bridge | Chuyển đổi, version hóa, serialize và gửi dữ liệu ra ngoài | `OrderEventBridge` |
| Integration event | Hợp đồng trao đổi ổn định giữa các service | `order.created.v1` với `eventId` |
| Message broker | Nhận, định tuyến, lưu/giữ và chuyển thông điệp theo cấu hình | RabbitMQ exchange/queue, Kafka topic |
| Consumer | Đọc thông điệp và thực hiện công việc có kiểm soát lỗi/lặp | `@RabbitListener` hoặc `@KafkaListener` |

**Không nên truyền nguyên JPA entity hoặc Spring `ApplicationEvent` qua broker** rồi bắt các service khác giải mã class domain nội bộ. Điều này tạo phụ thuộc vào package Java, lazy-loading, cấu trúc entity và serializer; có thể vô tình lộ field nhạy cảm.

Một adapter nên ánh xạ từ event trong ứng dụng sang dữ liệu **ổn định trên đường truyền**:

```text
Aggregate/Application Service
  |
  v
publishEvent(OrderCreated)
  |
  v
Spring @EventListener / adapter
  |
  +--> mapping internal -> integration event v1
  +--> JSON/Avro/Protobuf serialization
  +--> broker routing/partition key
  |
  v
RabbitMQ exchange / Kafka topic
  |
  v
Billing/Shipping service consumer
```

Đây là **kiến trúc luồng thông điệp**, chưa hàm ý transaction gốc và lần gửi broker nằm trong một giao dịch nguyên tử.

## 3. Ba lựa chọn và mức độ tin cậy

### Cách A — Gửi trực tiếp trong @EventListener

```text
@Transactional service
  UPDATE orders
  publishEvent(OrderCreated)
    -> @EventListener
       -> rabbitTemplate.convertAndSend(...)
  COMMIT
```

Ưu điểm: ít mã, dễ thử nghiệm. Nhược điểm quan trọng: message có thể được gửi ra ngoài **trước khi transaction DB commit**. Nếu DB rollback, consumer có thể nhận một event nói rằng đơn hàng đã được tạo dù bản ghi chưa tồn tại.

Nếu không có transaction và chỉ muốn thông báo best-effort, một bridge đơn giản có thể chấp nhận được **khi rủi ro mất sự kiện đã được nghiệp vụ đồng ý**. Không dùng nó như mặc định cho thanh toán, ghi nhận tồn kho hoặc thay đổi trạng thái cần đảm bảo.

### Cách B — Gửi sau commit bằng @TransactionalEventListener

```text
@Transactional service
  UPDATE orders
  publishEvent(OrderCreated)
  COMMIT
    -> @TransactionalEventListener(AFTER_COMMIT)
       -> rabbitTemplate.convertAndSend(...)
```

Ưu điểm: tránh gửi event về transaction đã rollback. Nhược điểm: còn **khoảng hở mất event** nếu process chết sau khi DB commit nhưng trước khi gửi tới broker. Việc publish thành công vào broker cũng chưa tự đảm bảo consumer đã xử lý xong.

Lưu ý: `@TransactionalEventListener` mặc định **không được gọi khi event phát ngoài transaction đang hoạt động**, trừ khi bật `fallbackExecution=true`. Không thể thay `@EventListener` bằng annotation này trong demo in-memory mà vẫn kỳ vọng chạy nếu không mở transaction.

### Cách C — Transactional outbox

```text
DB transaction:
   UPDATE orders ...
   INSERT INTO outbox_events ...
   COMMIT
                  |
                  v
Outbox worker / CDC (sau commit)
                  |
                  v
Broker -> Consumers
```

Ưu điểm: thay đổi nghiệp vụ và **ý định gửi event** được lưu trong **cùng DB transaction**. Khi broker tạm lỗi hoặc process restart, worker có thể đọc lại event chưa gửi và tiếp tục.

Đổi lại, outbox cần relay worker/CDC, retry state, idempotency, giám sát và cleanup. Thường được chọn cho business event quan trọng khi không được mất thông báo.

**Quy tắc quyết định:** `AFTER_COMMIT` giải quyết vấn đề *không gửi khi rollback*; **outbox** giải quyết thêm bài toán *ghi lại ý định gửi một cách bền vững*. Cả hai vẫn cần cơ chế bảo vệ khỏi xử lý trùng và lỗi ở consumer.

## 4. Thiết kế hợp đồng integration event

Ví dụ message JSON được phát ra RabbitMQ:

```json
{
  "eventId": "evt-001",
  "eventType": "order.created",
  "schemaVersion": 1,
  "orderId": "ORD-101",
  "amountMinorUnits": 12500,
  "occurredAt": "2026-11-11T06:00:00Z"
}
```

Các field có vai trò khác nhau:

- **`eventId`:** ID của một lần xảy ra, dùng theo dõi và chống xử lý trùng. Retry **cùng event** phải giữ cùng ID.
- **`eventType`:** tên sự thật nghiệp vụ, độc lập với tên class Java.
- **`schemaVersion`:** phiên bản cấu trúc và ý nghĩa payload, không phải phiên bản ứng dụng hay aggregate.
- **`orderId`:** định danh đối tượng để consumer liên kết và có thể dùng làm routing/partition key.
- **`amountMinorUnits`:** số tiền theo đơn vị nhỏ nhất đã được định nghĩa. Trong hệ thống nhiều loại tiền, cần thêm `currency` hoặc thiết kế hợp đồng rõ.
- **`occurredAt`:** thời điểm sự kiện xảy ra theo UTC/ISO-8601; không phải thời điểm consumer nhận.

Một event có thể mang thêm `correlationId`, tenant ID, aggregate version hoặc trace metadata khi cần, nhưng **không biến integration event thành bản sao mọi field của domain entity**. Chỉ gửi dữ liệu mà consumer có quyền và cần sử dụng.

Hợp đồng cần nói rõ field bắt buộc, giá trị `null`, đơn vị, enum, phiên bản và chính sách tương thích. Khi nhiều service triển khai độc lập, ưu tiên event type/schema ổn định và contract tests thay vì dựa vào Java class name từ producer.

### Cách tổ chức tên và định tuyến

Với RabbitMQ, thông thường producer gửi đến **exchange** cùng **routing key**; queue thuộc quyền sở hữu consumer và được bind vào exchange.

```text
                    exchange: shop.events
                              |
           routing key: order.created.v1
                       /                \
                      v                  v
      shop.billing.order-created    shop.analytics.order-created
                      |                  |
               Billing consumer     Analytics consumer
```

Hai queue độc lập cho hai nhóm consumer giúp mỗi nhóm xử lý/retry theo nhịp riêng. Nếu nhiều instance Billing cùng tiêu thụ **một queue**, RabbitMQ phân phối các message giữa các competing consumers của queue đó, không tự nhân bản một message cho mọi instance.

Kafka có mô hình topic/partition/consumer group khác RabbitMQ exchange/queue; **không chuyển nguyên khái niệm routing và acknowledgement** giữa hai broker mà không thiết kế lại.

## 5. Dự án chạy được: Spring Boot gửi internal event sang RabbitMQ

Ví dụ sử dụng **Java 17+, Spring Boot 3.3.13, RabbitMQ và Jackson JSON**. Phiên bản được cố định để bài dễ tái lập; khi làm production, chọn nhánh Spring Boot và RabbitMQ còn được hỗ trợ và kiểm tra tương thích.

Demo gồm một ứng dụng chứa cả producer và consumer để dễ học. Trong triển khai thật, hai phần thường nằm ở **hai service độc lập**, dùng chung schema tích hợp chứ không chung domain object.

### 5.1. Kết quả muốn quan sát

1. `CommandLineRunner` phát record nội bộ `OrderCreated` bằng `ApplicationEventPublisher`.
2. Một `@EventListener` chuyển record đó thành `OrderCreatedMessage` phiên bản 1.
3. `RabbitTemplate` serialize message thành JSON string và gửi đến exchange `shop.events` với routing key `order.created.v1`.
4. Queue bền vững `shop.billing.order-created.v1` được bind vào exchange.
5. `@RabbitListener` nhận message, deserialize JSON và in dữ liệu.
6. `CountDownLatch` giúp runner đợi consumer trong demo; không dùng sleep cố định.

### 5.2. Cấu trúc thư mục

```text
internal-event-to-rabbitmq/
├── compose.yaml
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/events/EventToRabbitDemo.java
    │   └── resources/application.properties
    └── test/
        └── java/example/events/BridgeMappingTest.java
```

### 5.3. compose.yaml

```yaml
services:
  rabbitmq:
    image: rabbitmq:4.1-management
    ports:
      - "5672:5672"
      - "15672:15672"
```

Chạy Docker Compose tại thư mục project:

```bash
docker compose up -d
docker compose exec rabbitmq rabbitmq-diagnostics -q ping
```

Đợi broker khởi động xong trước khi chạy app. Giao diện quản trị cho môi trường local có thể mở ở `http://localhost:15672`, tài khoản demo mặc định `guest/guest` khi broker giữ cấu hình mặc định. **Chỉ sử dụng cặp credential này trên máy local**; không mở port quản trị/broker ra Internet hoặc dùng cấu hình demo trong production.

### 5.4. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>internal-event-to-rabbitmq</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-amqp</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

`spring-boot-starter-amqp` cung cấp Spring AMQP/RabbitMQ và cấu hình tự động cho `RabbitTemplate`, listener container và `RabbitAdmin`. `spring-boot-starter-json` cung cấp Jackson để tạo và đọc JSON; ví dụ chủ động giữ wire contract ở một record tích hợp riêng.

### 5.5. application.properties

```properties
spring.main.web-application-type=none

spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
spring.rabbitmq.username=guest
spring.rabbitmq.password=guest

# Chỉ dành cho demo. Khi lỗi, không requeue vô hạn.
# Chưa có DLX nên message bị từ chối có thể bị loại bỏ.
spring.rabbitmq.listener.simple.default-requeue-rejected=false

logging.level.root=WARN
```

Thuộc tính `default-requeue-rejected=false` ở đây làm lỗi dễ quan sát thay vì rơi vào vòng lặp giao lại vô hạn. **Nó không biến message lỗi thành một message an toàn đang chờ xử lý**: vì demo chưa cấu hình dead-letter exchange, message bị reject không requeue có thể bị loại bỏ. Với production, phải thiết kế DLX/DLQ/quarantine và chính sách retry rõ ràng.

### 5.6. EventToRabbitDemo.java

```java
package example.events;

import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
@EnableRabbit
public class EventToRabbitDemo {

    public static final String EXCHANGE = "shop.events";
    public static final String ROUTING_KEY = "order.created.v1";
    public static final String QUEUE =
            "shop.billing.order-created.v1";

    // Event nội bộ: POJO/record thuần Java, KHÔNG phải AMQP message.
    public record OrderCreated(
            String eventId,
            String orderId,
            long amountMinorUnits,
            Instant occurredAt) {
    }

    // Hợp đồng JSON được gửi tới các service khác.
    public record OrderCreatedMessage(
            String eventId,
            String eventType,
            int schemaVersion,
            String orderId,
            long amountMinorUnits,
            String occurredAt) {
    }

    public static final class EventBridge {
        private final RabbitTemplate template;
        private final ObjectMapper mapper;

        public EventBridge(
                RabbitTemplate template, ObjectMapper mapper) {
            this.template = template;
            this.mapper = mapper;
        }

        // Mapping thuần: dễ kiểm thử mà không cần RabbitMQ.
        public static OrderCreatedMessage map(OrderCreated domain) {
            Objects.requireNonNull(domain, "domain");
            return new OrderCreatedMessage(
                    domain.eventId(),
                    "order.created",
                    1,
                    domain.orderId(),
                    domain.amountMinorUnits(),
                    domain.occurredAt().toString());
        }

        @EventListener
        public void on(OrderCreated domain) {
            OrderCreatedMessage message = map(domain);
            String json;

            try {
                json = mapper.writeValueAsString(message);
            } catch (JsonProcessingException ex) {
                throw new IllegalStateException(
                        "Cannot serialize OrderCreated", ex);
            }

            System.out.println(
                    "BRIDGE_SEND eventId=" + message.eventId());

            // Giữ wire message kiểu String để SimpleMessageConverter
            // phía consumer nhận được dưới dạng text.
            template.convertAndSend(
                    EXCHANGE,
                    ROUTING_KEY,
                    json,
                    amqpMessage -> {
                        amqpMessage.getMessageProperties()
                                .setDeliveryMode(
                                        MessageDeliveryMode.PERSISTENT);
                        return amqpMessage;
                    });
        }
    }

    public static final class BillingConsumer {
        private final ObjectMapper mapper;
        private final CountDownLatch consumed;

        public BillingConsumer(
                ObjectMapper mapper, CountDownLatch consumed) {
            this.mapper = mapper;
            this.consumed = consumed;
        }

        @RabbitListener(queues = QUEUE)
        public void onMessage(String body) {
            final OrderCreatedMessage message;

            try {
                message = mapper.readValue(
                        body, OrderCreatedMessage.class);

                if (message.schemaVersion() != 1
                        || !"order.created".equals(
                                message.eventType())) {
                    throw new IllegalArgumentException(
                            "Unsupported event schema/type");
                }
            } catch (JsonProcessingException
                    | IllegalArgumentException ex) {
                throw new AmqpRejectAndDontRequeueException(
                        "Invalid integration message", ex);
            }

            // Demo chỉ log; production cần giao dịch/idempotency
            // cho side effect thật trước khi cho container ACK.
            System.out.printf(
                    "BROKER_CONSUMED eventId=%s orderId=%s"
                            + " amount=%d version=%d%n",
                    message.eventId(),
                    message.orderId(),
                    message.amountMinorUnits(),
                    message.schemaVersion());

            consumed.countDown();
        }
    }

    // Broker topology: exchange, queue và binding bền vững.
    @Bean
    TopicExchange shopExchange() {
        return new TopicExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue billingQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding billingBinding(
            Queue billingQueue, TopicExchange shopExchange) {
        return BindingBuilder.bind(billingQueue)
                .to(shopExchange)
                .with(ROUTING_KEY);
    }

    @Bean
    CountDownLatch receivedLatch() {
        return new CountDownLatch(1);
    }

    @Bean
    EventBridge eventBridge(
            RabbitTemplate template, ObjectMapper mapper) {
        return new EventBridge(template, mapper);
    }

    @Bean
    BillingConsumer billingConsumer(
            ObjectMapper mapper, CountDownLatch receivedLatch) {
        return new BillingConsumer(mapper, receivedLatch);
    }

    @Bean
    CommandLineRunner demo(
            ApplicationEventPublisher publisher,
            CountDownLatch receivedLatch) {
        return args -> {
            System.out.println("APP_PUBLISH orderId=ORD-101");

            publisher.publishEvent(new OrderCreated(
                    "evt-001",
                    "ORD-101",
                    12500,
                    Instant.parse("2026-11-11T06:00:00Z")));

            if (!receivedLatch.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Consumer did not receive event in time");
            }

            System.out.println("APP_CONSUMED=true");
        };
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(
                             EventToRabbitDemo.class, args)) {
            // Demo chạy và đợi consumer rồi đóng context.
        }
    }
}
```

### 5.7. Biên dịch và chạy

Chạy broker trước bằng `docker compose up -d`, xác minh RabbitMQ đã sẵn sàng rồi chạy:

```bash
mvn -q package
java -jar target/internal-event-to-rabbitmq-1.0.0.jar
```

Các dòng **do code demo tự in** khi broker chạy và message được xử lý thành công:

```text
APP_PUBLISH orderId=ORD-101
BRIDGE_SEND eventId=evt-001
BROKER_CONSUMED eventId=evt-001 orderId=ORD-101 amount=12500 version=1
APP_CONSUMED=true
```

Spring/RabbitMQ có thể in thêm log riêng. Trong ví dụ:

- `APP_PUBLISH` xảy ra trước khi gọi Spring publisher.
- `BRIDGE_SEND` in ra trước khi bridge gọi `RabbitTemplate.convertAndSend(...)`.
- `BROKER_CONSUMED` xuất hiện ở thread Rabbit listener container, sau khi message thật được broker định tuyến vào queue.
- `APP_CONSUMED=true` chỉ xuất hiện sau khi consumer đã gọi `CountDownLatch.countDown()`. Latch giữ thứ tự output trong demo, **không thay thế ACK hoặc business confirmation trong hệ thống thật**.

Nếu broker chưa khởi động, cấu hình sai hoặc message không đến, chương trình có thể báo lỗi kết nối/timeout thay vì in output trên. Dòng `BRIDGE_SEND` **không chứng minh RabbitMQ đã chấp nhận message**, vì nó được in trước lệnh send; muốn xác nhận broker acceptance cần publisher confirms/returns được trình bày ở phần sau.

Tắt demo:

```bash
docker compose down
```

Nếu muốn giữ message/queue sau khi container bị xóa, cần cấu hình Docker volume bền vững cho dữ liệu RabbitMQ; chỉ đánh dấu queue là durable không giữ được dữ liệu khi toàn bộ storage của container bị xóa.

### 5.8. Vì sao đây mới là ví dụ bridge cơ bản?

Demo cố tình chưa có database transaction/outbox, chưa có publisher confirms, consumer idempotency hoặc DLQ thật. Nó chỉ chứng minh **một internal event được chuyển đổi và gửi qua RabbitMQ**, sau đó một consumer nhận message. Không coi demo này là mẫu đảm bảo exactly-once hoặc end-to-end reliability.

## 6. Unit test phần mapping mà không cần broker

File `src/test/java/example/events/BridgeMappingTest.java`:

```java
package example.events;

import java.time.Instant;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BridgeMappingTest {

    @Test
    void internalEventMapsToStableIntegrationContract() {
        var domain = new EventToRabbitDemo.OrderCreated(
                "evt-123", "ORD-123", 7350L,
                Instant.parse("2026-11-11T06:00:00Z"));

        var message = EventToRabbitDemo.EventBridge.map(domain);

        assertEquals("evt-123", message.eventId());
        assertEquals("order.created", message.eventType());
        assertEquals(1, message.schemaVersion());
        assertEquals("ORD-123", message.orderId());
        assertEquals(7350L, message.amountMinorUnits());
        assertEquals(
                "2026-11-11T06:00:00Z",
                message.occurredAt());
    }
}
```

Chạy:

```bash
mvn -Dtest=BridgeMappingTest test
```

Test này chỉ thao tác trên các Java record và mapping thuần, nên **không cần RabbitMQ chạy**. Khi thành công, Maven Surefire có một JUnit test method pass. Nó xác minh hợp đồng JSON v1 được xây dựng đúng từ domain event, nhưng **không chứng minh exchange/binding/consumer hoạt động**. Phần đó phải được kiểm chứng bằng chạy demo với RabbitMQ hoặc integration test với broker thật (có thể dùng Testcontainers).

Với production, nên thêm test rằng mapper:
- Không đổi `eventId` khi một event được publish lại.
- Giữ đúng đơn vị tiền và UTC timestamp.
- Không đưa field nhạy cảm từ aggregate vào integration event.
- Không phá schema v1 khi một field nội bộ đổi tên.
- Xử lý event type/schema version không được hỗ trợ bằng luồng lỗi có chủ đích.

## 7. @TransactionalEventListener(AFTER_COMMIT) và giới hạn của nó

Trong ứng dụng dùng database, khi muốn gửi ra broker **chỉ sau khi DB commit**, có thể thay bridge listener bằng mẫu sau:

```java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    rabbitPublisher.send(mapToIntegrationMessage(event));
}
```

**Đây là đoạn minh họa**, không phải code thêm trực tiếp vào demo mục 5: phương thức giả định có `OrderCreated`, `rabbitPublisher` và `mapToIntegrationMessage(...)`, và phải nằm trong bean Spring. Event phải được publish khi **transaction đang chạy**.

Ví dụ application service:

```java
@Service
public class OrderApplicationService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    @Transactional
    public void createOrder(CreateOrderCommand command) {
        Order order = Order.create(command);
        repository.save(order);
        publisher.publishEvent(
                new OrderCreated(order.getEventId(),
                        order.getId(), order.getAmount(),
                        Instant.now()));
    }
}
```

Đây cũng là **khung minh họa**, không thuộc project ở mục 5: các class `OrderRepository`, `Order`, `CreateOrderCommand` và imports cần được định nghĩa trong ứng dụng DB thật. Mục tiêu là nhìn thấy transaction boundary, không phải đưa pseudocode vào build demo.

Một điều quan trọng: **AFTER_COMMIT không làm thay đổi DB transaction đã commit nếu send thất bại**. Lúc callback sau commit chạy, nếu broker đang mất kết nối, đơn hàng vẫn đã lưu, nhưng event có thể chưa ra broker. Nếu process chết ngay sau commit trước khi callback hoàn thành, không có hàng đợi bền vững để tiếp tục.

Nếu `@TransactionalEventListener` dùng để ghi DB mới sau commit, việc một số transaction resource còn gắn với thread có thể gây nhầm lẫn. Với thao tác DB ghi mới, dùng service có `@Transactional(propagation = Propagation.REQUIRES_NEW)` thông qua Spring proxy hoặc `TransactionTemplate`; đừng giả định transaction cũ còn commit được.

**Tránh dùng `fallbackExecution=true` tùy tiện:** nó khiến callback được thực thi kể cả khi không có transaction, làm thay đổi hợp đồng "chỉ gửi sau commit".

## 8. Transactional outbox: cách giảm nguy cơ mất event

Hãy lưu **business change** và **outbox record** trong một transaction của **cùng database**:

```sql
BEGIN;

INSERT INTO orders (id, status, amount_minor)
VALUES ('ORD-101', 'CREATED', 12500);

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type,
    schema_version, payload_json, status)
VALUES (
    'evt-001', 'ORD-101', 'order.created',
    1, '{"eventId":"evt-001","eventType":"order.created"}',
    'NEW');

COMMIT;
```

Đây là **pseudocode SQL minh họa trình tự ghi**: tên bảng/cột và JSON rút gọn không phải schema sẵn có của demo. Trong thực tế, payload cần đủ field theo integration contract; transaction phải do database/JDBC/JPA quản lý nhất quán.

Luồng relay:

```text
OrderService: @Transactional
    |
    +--> save Order
    +--> save OutboxEvent
    |
    v
DB COMMIT (atomic cho hai bản ghi)
    |
    v
Outbox relay / CDC đọc event NEW
    |
    +--> serialize/send to broker
    +--> chờ broker confirm
    +--> đánh dấu SENT / ACK theo chính sách
    |
    v
RabbitMQ / Kafka -> consumers
```

### Vì sao outbox đáng tin hơn?

Nếu DB transaction rollback, **cả order và outbox đều không tồn tại**. Nếu transaction commit, outbox có thể được worker đọc lại sau restart. Khi broker tạm thời không sẵn sàng, worker giữ trạng thái và retry theo lịch. Đó là cách khắc phục khoảng hở "đơn đã commit nhưng application event biến mất trong RAM".

### Một outbox record cần có gì?

Các field thường hữu ích:

| Field | Mục đích |
| --- | --- |
| `event_id` (unique) | Nhận dạng event và chống insert lặp |
| `aggregate_id` | Khóa định tuyến/ordering theo aggregate |
| `event_type`, `schema_version` | Hợp đồng consumer |
| `payload_json` | Thông điệp sẽ gửi, bất biến về ý nghĩa |
| `created_at` | Thời điểm ghi outbox |
| `status` | NEW/IN_PROGRESS/SENT/FAILED... |
| `attempt_count` | Kiểm soát retry |
| `next_attempt_at` | Lịch thử lại |
| `last_error` (rút gọn, không chứa secret) | Chẩn đoán |
| `locked_until`/lease (nếu cần) | Tránh nhiều worker cùng claim row |
| `published_at` | Audit thời điểm xác nhận phát |

Có thể triển khai relay bằng polling SQL có claim/lease an toàn hoặc change data capture (CDC). Việc chọn cách nào phụ thuộc throughput, hạ tầng, DB log và khả năng vận hành.

### Cửa sổ crash vẫn còn ở relay

Giả sử relay gửi message thành công, broker đã nhận, nhưng process chết **trước khi cập nhật outbox status thành SENT**. Lần chạy sau nó sẽ gửi lại cùng message. Vì vậy outbox thường đem lại **at-least-once publication**, không phải exactly-once end-to-end. Consumer **phải idempotent**.

Không được đánh dấu outbox SENT chỉ vì gọi `convertAndSend(...)` đã trả về nếu yêu cầu bảo đảm broker thực sự chấp nhận message. Kết hợp publisher confirms/returns, policy xử lý timeout và trạng thái có thể chưa xác định.

## 9. Publisher confirms và publisher returns trong RabbitMQ

**Đừng nhầm thành công ở API gửi với thành công ở broker hay consumer.**

Trong Spring AMQP, `RabbitTemplate.convertAndSend(...)` có thể trả về sau khi gửi request mà không biết chắc broker đã chấp nhận và định tuyến đúng queue. Hai cơ chế hỗ trợ:

1. **Publisher confirm:** broker gửi ACK/NACK cho lần publish; xác nhận ở cấp broker. Nó **không** xác nhận business consumer đã xử lý xong.
2. **Publisher return:** khi message được publish với chế độ `mandatory` nhưng không có queue phù hợp để route, broker trả lại message, thay vì âm thầm bỏ vì không route được.

Với Spring Boot, cấu hình thông dụng:

```properties
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
```

Khi bật correlated confirms, dùng `CorrelationData` để liên kết lần publish với callback hoặc future. Khi bật returns và mandatory, đăng ký `RabbitTemplate.ReturnsCallback` hoặc kiểm tra returned message gắn với correlation. Thiết kế relay cần xử lý cả **NACK, unroutable, timeout và kết quả không xác định**.

**Ví dụ định hướng API (không phải chương trình độc lập):**

```java
CorrelationData correlation = new CorrelationData(eventId);
rabbitTemplate.convertAndSend(
        exchangeName, routingKey, jsonBody, correlation);

var confirm = correlation.getFuture()
        .get(5, TimeUnit.SECONDS);

if (!confirm.isAck()) {
    throw new IllegalStateException(
            "Broker did not ACK publication");
}
```

Đoạn trên giả định template đã bật publisher confirms, có imports, các biến, và một cơ chế xử lý `InterruptedException`, `ExecutionException`, `TimeoutException`. Kiểm tra ACK **chưa đủ** để phát hiện unroutable nếu không kiểm tra publisher returns trong cấu hình mandatory. Khi timeout, message **có thể đã được broker nhận**; retry bằng cùng `eventId` và chuẩn bị cho duplicate.

Cũng không nên giữ một database transaction mở để chờ confirm broker quá lâu. Với outbox relay, worker thường xử lý **ngoài** transaction nghiệp vụ gốc và dùng transaction ngắn để claim/update trạng thái.

### Durable không phải bảo đảm tuyệt đối

- Durable exchange và durable queue cho phép broker định nghĩa lại topology sau restart theo cơ chế lưu trữ của broker.
- Persistent delivery mode giúp message đủ điều kiện lưu bền trong queue phù hợp.
- Publisher confirm hỗ trợ biết broker đã chấp nhận lần gửi theo cơ chế nó triển khai.
- Các yếu tố như loại queue (classic/quorum), replication, storage failure, HA và cơ chế shutdown còn ảnh hưởng đến độ bền thực tế.

Không dùng riêng từ `durable` hay `persistent` để hứa "không bao giờ mất message". Hãy đặt SLO về độ trễ, durability, retention và recovery phù hợp với broker cụ thể.

## 10. Consumer acknowledgement, redelivery và DLQ

Ở RabbitMQ, message đi qua queue và được consumer nhận. Với Spring AMQP, `@RabbitListener` thường chạy trong một listener container có chế độ acknowledgement. Ở `AcknowledgeMode.AUTO`, container thực hiện ACK theo kết quả xử lý callback (trừ khi cấu hình khác), không phải vì method vừa bắt đầu.

Những kết quả phổ biến:

- Handler hoàn tất bình thường → container có thể ACK message.
- Handler ném exception → theo retry/error handler và requeue policy, message có thể được giao lại, reject hoặc dead-letter.
- Consumer chết trước ACK → broker có thể giao lại message đã unacked cho consumer khác.
- Handler đã thực hiện side effect nhưng crash trước ACK → message giao lại có thể tạo side effect trùng.

Chính vì vậy, **acknowledgement không thay thế idempotency**, và broker-delivery-at-least-once không tự biến nghiệp vụ thành exactly-once.

### Poison message

Một message có JSON lỗi hoặc schemaVersion chưa hỗ trợ có thể luôn thất bại. Nếu cấu hình requeue vô hạn, nó có thể tạo vòng lặp lỗi kéo dài:

```text
consume -> deserialize fail -> requeue -> consume
        -> deserialize fail -> requeue -> ...
```

Nên phân loại lỗi:

| Loại lỗi | Hành động gợi ý |
| --- | --- |
| Timeout/connectivity downstream | Retry hữu hạn và backoff |
| HTTP 429/rate limit | Tôn trọng quota và Retry-After |
| JSON không parse được | Reject/quarantine và cảnh báo, không requeue vô hạn |
| Schema version không hỗ trợ | DLQ/quarantine, hỗ trợ migration hoặc nâng consumer |
| Vi phạm invariant nghiệp vụ | Không retry cùng payload vô hạn |
| Duplicate eventId đã xử lý | Trả thành công/idempotent skip, tránh side effect lần hai |

Production nên cấu hình **dead-letter exchange/queue** với retention, giới hạn lần redelivery, cảnh báo và đường replay có kiểm soát. DLQ không tự bảo đảm xử lý xong; nó là nơi giữ bằng chứng lỗi để sửa/replay.

Demo ở mục 5 đặt `default-requeue-rejected=false` để không lặp lỗi vô hạn nhưng **chưa có DLQ**, nên chỉ thích hợp học kỹ thuật.

## 11. Consumer idempotency: tránh ghi hoặc gửi hai lần

Một integration event có thể được xử lý lặp do broker redelivery, producer retry hoặc outbox relay gửi trùng. Nếu listener tạo hóa đơn, gửi thông báo hay trừ kho, việc lặp có thể gây hậu quả nghiêm trọng.

Mô hình **inbox/dedup table** thường dùng:

```sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Với một consumer cập nhật **cùng database**, có thể đặt việc ghi dấu xử lý và side effect DB trong **cùng transaction**:

```text
BEGIN DB TRANSACTION
    INSERT processed_messages(consumer, event_id)
        -- unique key: đã tồn tại => duplicate
    UPDATE billing_projection ...
COMMIT

Sau commit xử lý DB thành công:
    cho listener container ACK theo cấu hình
```

Khi duplicate key, consumer có thể xác nhận event đã được xử lý trước đó và bỏ qua an toàn **nếu** record dedup chỉ được commit sau khi side effect DB đã thành công. Không nên ghi dấu `processed` rồi commit trước khi thực hiện side effect trong transaction khác; crash giữa hai bước có thể khiến lần retry bị bỏ qua, gây mất công việc.

Với side effect **ngoài database** (API thanh toán, email, shipping provider), cần idempotency key được downstream hỗ trợ, hoặc workflow/saga/outbox phụ khác để quản lý kết quả "đã gửi nhưng mất phản hồi". Transaction DB local **không thể rollback HTTP request đã thực thi**.

### Chọn khóa idempotency

- Dùng `eventId` khi một occurrence nghiệp vụ được phát lại; mọi lần retry giữ cùng ID.
- Định nghĩa thêm khóa nghiệp vụ khi có nguy cơ producer tạo event ID mới cho cùng chuyển trạng thái.
- Không dùng `threadName`, timestamp gần đúng hoặc mã random mới mỗi attempt làm khóa chống trùng.
- Khi có nhiều consumer độc lập, khóa có thể là **(consumerName, eventId)** để Billing và Analytics xử lý cùng event theo trạng thái riêng.

Idempotency giúp chống side effect trùng, nhưng cần kết hợp unique constraint/atomic operation để tránh race khi nhiều worker xử lý đồng thời.

## 12. Ordering và nhiều consumer

Một message broker không nhất thiết bảo đảm thứ tự nghiệp vụ tuyệt đối khi có nhiều producer, nhiều partition/queue, nhiều consumer hoặc retry.

Ví dụ các event của một đơn:

```text
OrderCreated(orderId=ORD-7, aggregateVersion=1)
OrderPaid(orderId=ORD-7, aggregateVersion=2)
OrderCancelled(orderId=ORD-7, aggregateVersion=3)
```

Consumer có thể thấy event về muộn hoặc xử lý lại phiên bản trước. Nếu thứ tự là yêu cầu quan trọng:

- Với Kafka, cân nhắc partition key = `orderId` để event cùng aggregate vào cùng partition; thứ tự vẫn phụ thuộc cấu hình producer/consumer và replay.
- Với RabbitMQ, xem số consumer trên queue, prefetch, requeue/redelivery và giới hạn xử lý song song.
- Thêm `aggregateVersion` hoặc sequence number; consumer có thể kiểm tra event cũ, event thiếu hoặc xử lý out-of-order.
- Với workflow nhiều dịch vụ, không chỉ dựa vào "message đến trước" để khẳng định trạng thái đã hợp lệ.

**SchemaVersion khác aggregateVersion.** Hai event đều có schemaVersion=1 nhưng aggregateVersion khác nhau; không dùng version payload để sắp thứ tự chuyển trạng thái.

## 13. So sánh RabbitMQ và Kafka ở điểm tích hợp

Tư duy **internal event → integration event → broker** là chung, nhưng các API và mô hình delivery không giống nhau:

| Nội dung | RabbitMQ/Spring AMQP | Kafka/Spring Kafka |
| --- | --- | --- |
| Nơi producer gửi | Exchange + routing key | Topic + optional key |
| Subscriber | Queue + `@RabbitListener` | Consumer group + `@KafkaListener` |
| Định tuyến | Exchange binding, routing key | Partition, subscription/topic |
| Chống trùng | Consumer idempotency/inbox | Consumer idempotency; Kafka transaction chỉ bao phủ một số luồng Kafka-to-Kafka |
| Xác nhận gửi | Publisher confirms/returns | Future/callback của producer, broker acknowledgements |
| Replay | Phụ thuộc lưu trữ, DLQ và ứng dụng | Topic retention/offset/replay |
| Thứ tự | Phụ thuộc queue/consumer/requeue | Theo partition trong điều kiện phù hợp |

Nếu dùng Spring Kafka, adapter thường gọi:

```java
// Schematic: cần KafkaTemplate, topic và serializer.
kafkaTemplate.send(
        "order.created.v1", event.orderId(), payload);
```

Đây **không phải code của demo RabbitMQ**. Spring Kafka send thường bất đồng bộ; phải xử lý completion/failure thay vì bỏ mặc future. Nếu cần không mất sự kiện giữa DB transaction và Kafka, transactional outbox/CDC vẫn là một giải pháp phù hợp, thay vì nghĩ `@Transactional` của JDBC tự biến thành distributed transaction an toàn với Kafka.

## 14. Kiểm thử từng lớp của pipeline

Để chẩn đoán chính xác, tách unit, integration và failure testing:

### Unit test mapping

- `OrderCreated` ánh xạ đúng sang `OrderCreatedMessage`.
- Giữ nguyên eventId, orderId và amountMinorUnits.
- Schema version, event type và timestamp đúng.
- Không leak field nhạy cảm.
- Nếu mapping thất bại, callback phát ra exception hoặc trạng thái lỗi đúng hợp đồng.

Test `BridgeMappingTest` ở mục 6 minh họa nhóm này.

### Integration test với broker thật hoặc Testcontainers

Dùng RabbitMQ container tạm trong test hoặc broker test đã cô lập:

1. Khởi động broker, đăng ký exchange, queue, binding.
2. Publish domain event thông qua Spring publisher; assert consumer nhận JSON đúng.
3. Kiểm tra routing key sai và returns/mandatory behavior.
4. Kiểm tra consumer lỗi schema → reject/DLQ theo cấu hình.
5. Đảm bảo listener không được đăng ký hai lần ngoài ý muốn.
6. Kiểm tra restart consumer, queue durability và thông điệp tồn đọng khi broker vẫn giữ storage.
7. Dùng assertion có timeout/latch để tránh test flaky; không chỉ `Thread.sleep(100)` rồi khẳng định "message không đến".

### Transaction/outbox tests

Với database thực:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Business transaction commit | Order và outbox record cùng tồn tại |
| Business transaction rollback | Không có order và không có outbox event |
| Broker tạm không khả dụng | Outbox giữ event chưa gửi, relay retry |
| Broker ACK nhưng relay crash trước cập nhật SENT | Event có thể phát lại; consumer dedup |
| Consumer cập nhật DB rồi crash trước broker ACK | Redelivery không cập nhật DB hai lần |
| Event không parse được | Được DLQ/quarantine, không loop vô hạn |
| Schema v1 và v2 cùng tồn tại | Consumer hỗ trợ version đúng, không đoán giá trị |
| Duplicate eventId | Chỉ một side effect theo transaction/idempotency |
| Tăng số consumer | Không phá yêu cầu ordering theo aggregate |
| DLQ replay | Có audit và idempotency khi xử lý lại |

**Quan trọng:** Không thể dùng một test chỉ khẳng định `rabbitTemplate.convertAndSend(...)` không ném lỗi để chứng minh end-to-end delivery. Nó mới kiểm tra một phần nhỏ của đường gửi.

## 15. Vận hành và bảo mật

Một pipeline message broker đáng tin cần quan sát **mỗi giai đoạn**:

- **Producer:** số internal events được tạo, mapping error, publish attempts, confirm ACK/NACK, returns.
- **Outbox:** pending records, độ tuổi event cũ nhất, next retry time, số attempts, failed/stuck lease.
- **Broker:** queue depth/lag, unacked messages, throughput, dead-letter count, connection/channel health.
- **Consumer:** received, processed, failed, retry count, DLQ count, duplicate skipped và end-to-end latency.

Chỉ gắn metric tag loại event, consumer, outcome, service; **không** gắn `eventId` hoặc `orderId` làm tag vì gây cardinality rất cao. ID chi tiết thuộc log/tracing có phân quyền.

Về bảo mật: dùng TLS và credential riêng cho từng service/vhost theo least privilege, quản lý secrets bằng hệ thống phù hợp, giới hạn quyền publish/consume, kiểm soát schema và payload PII. Không gửi toàn bộ entity hoặc token vào message. Định nghĩa retention, xóa dữ liệu, encryption khi lưu và đường xử lý thông tin nhạy cảm trong DLQ.

Về khả năng mở rộng: điều chỉnh concurrency, prefetch, backpressure, retry delay và broker resource limits dựa trên tải thực, không chỉ tăng số consumer. Một consumer liên tục lỗi có thể tạo retry storm, tăng lag và làm broker quá tải.

## 16. Lỗi thiết kế thường gặp

**1. Coi @EventListener là message queue bền vững.** Spring event bình thường nằm trong bộ nhớ của context. Nó không tự replay sau restart.

**2. Gửi broker trước khi DB commit rồi nói "OrderCreated".** Nếu rollback, integration event có thể là thông tin sai. Phân biệt transaction boundary và chọn AFTER_COMMIT/outbox.

**3. Coi AFTER_COMMIT là đủ để không mất event.** Process có thể chết ngay sau DB commit. Dùng outbox khi delivery thật sự quan trọng.

**4. Gửi cả JPA entity ra broker.** Schema liên kết chặt với implementation, lazy-loading và PII; dùng DTO integration event bất biến với version.

**5. Không có publisher confirms/returns khi cần kết quả chắc chắn.** Method send trả về không chứng minh message đã route vào queue, càng không chứng minh consumer đã xử lý.

**6. Không xét consumer duplicate.** Redelivery và outbox relay có thể gửi cùng event nhiều lần; thiết kế idempotency với key ổn định.

**7. Retry lỗi dữ liệu mãi mãi.** JSON sai hoặc version lạ không tự hết. Đưa vào DLQ/quarantine và cảnh báo.

**8. Chỉ có một queue chung cho mọi service cần sự kiện.** Khi mỗi service cần nhận mọi event, dùng queue/group riêng tùy broker; nhiều consumer trên cùng RabbitMQ queue là competing consumers.

**9. Ghi outbox SENT trước khi gửi/confirm.** Crash có thể làm mất notification. Cần trạng thái và quy tắc xác nhận/retry rõ.

**10. Xem ACK từ broker là consumer thành công.** Publisher confirm chỉ nói về broker nhận publish; consumer outcome là bước khác.

**11. Bật @Async cho bridge và cho rằng đủ tin cậy.** Executor vẫn ở trong memory; không có durable retry sau crash.

**12. Không có quan sát pipeline.** Không biết event mất tại producer, outbox, routing, consumer hay side effect. Cần correlation ID và metrics cho từng mốc.

## 17. Checklist khi đưa vào production

1. Nghiệp vụ có thật sự cần phát event sang service khác, hay chỉ cần listener nội bộ?
2. Đã chọn đúng **internal event và integration event riêng** với DTO/schemaVersion rõ ràng?
3. Đã xác định **sự kiện được phát lúc nào** so với transaction commit?
4. Nếu không được mất event, đã có transactional outbox hoặc cơ chế bền vững tương đương?
5. Outbox relay đã có claim, retry/backoff, confirm, lease/cleanup và recovery sau crash?
6. Broker topology đã có exchange/topic, routing/partition key và queue/consumer group đúng?
7. Producer đã phân biệt ACK/NACK, unroutable, timeout và trạng thái không xác định?
8. Consumer có idempotency/dedup để chịu được at-least-once delivery?
9. Đã tách lỗi retryable khỏi lỗi validation/schema và cấu hình DLQ/quarantine?
10. Có bảo đảm tương thích schema, versioning và retention/replay?
11. Đã kiểm tra ordering theo aggregate với concurrency thực?
12. Có integration/failure tests cho rollback, broker outage, crash, duplicate và DLQ?
13. Có monitoring về pending outbox, consumer lag, DLQ, retries và side-effect outcome?
14. Payload và broker credential đã được bảo vệ theo chính sách sản phẩm?
15. Đã hiểu giới hạn của demo in-process khi tách producer và consumer thành service độc lập?

**Kết luận:** Chuyển event nội bộ sang message broker không chỉ là thay `publishEvent(...)` bằng `rabbitTemplate.convertAndSend(...)`. Cần định nghĩa **hợp đồng integration event**, xác định ranh giới transaction, lựa chọn cách gửi phù hợp với mức độ tin cậy, xử lý ACK/return/retry và bảo đảm consumer idempotent. Với nghiệp vụ quan trọng, mô hình **DB transaction + outbox + broker + idempotent consumer** thường là nền tảng hợp lý hơn so với listener gửi trực tiếp.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): `ApplicationEventPublisher`, `@EventListener`, listener đồng bộ/bất đồng bộ.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): `@TransactionalEventListener`, AFTER_COMMIT và fallback behavior.
- [Spring Boot — AMQP/RabbitMQ](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): starter AMQP, `RabbitTemplate`, `@RabbitListener`, queue declarations và retry.
- [Spring AMQP — AmqpTemplate and Publisher Confirms/Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): confirm, mandatory returns và rủi ro unroutable messages.
- [Spring AMQP — @RabbitListener Annotation](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable.html): listener container và `@EnableRabbit`.
- [Spring AMQP — Asynchronous Consumer](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): consumer threads, prefetch và throughput.
- [Microservices.io — Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): dual-write problem, relay và duplicate publication.

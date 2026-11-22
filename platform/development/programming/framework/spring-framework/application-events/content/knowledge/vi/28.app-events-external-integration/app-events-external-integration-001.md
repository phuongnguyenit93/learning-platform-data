# Khác biệt giữa Spring event và broker message trong hệ thống Spring

## 1. Hai cơ chế đều gọi là “event”, nhưng không có cùng hợp đồng

Trong một ứng dụng Spring, ta có thể phát một đối tượng:

```java
applicationEventPublisher.publishEvent(
        new OrderCreated("evt-101", "ORD-101"));
```

Ở một hệ thống dùng RabbitMQ, ta cũng có thể gửi thông điệp diễn tả đúng sự việc đó:

```java
rabbitTemplate.convertAndSend(
        "orders.events", "order.created.v1", jsonBody);
```

Hai dòng code dễ tạo cảm giác chúng chỉ khác nhau ở API. Thực tế, **Spring application event** chủ yếu là cơ chế giao tiếp giữa các thành phần trong một ứng dụng; **broker message** là thông điệp đi qua một hạ tầng trao đổi độc lập, có giao thức, định tuyến, lưu trữ và quy tắc xác nhận riêng.

Một sự kiện nghiệp vụ như “đơn hàng đã được tạo” có thể tồn tại ở cả hai hình thức, nhưng **không nên đánh đồng cơ chế truyền với sự thật nghiệp vụ**.

- **Domain event**: sự thật trong mô hình, ví dụ `OrderCreated`.
- **Spring application event**: một Java object được `ApplicationEventPublisher` chuyển cho listener trong Spring ApplicationContext (có thể lan theo hierarchy context).
- **Integration event**: hợp đồng dữ liệu công bố cho ứng dụng/bounded context khác, ví dụ `order.created.v1`.
- **Broker message**: một bản tin ở mức giao thức/transport mang integration event và metadata, đi qua RabbitMQ exchange/queue hoặc Kafka topic/partition.

Có thể dùng một domain event để sinh integration event, nhưng nó **không tự động** tạo bảo đảm dữ liệu bền vững, retry hoặc exactly-once.

## 2. Bảng so sánh nền tảng

| Tiêu chí | Spring Application Events | Message broker (ví dụ RabbitMQ/Kafka) |
| --- | --- | --- |
| Phạm vi | Giữa bean/listener trong cùng ứng dụng/context; context hierarchy có thể chuyển event | Giữa tiến trình, service, máy hoặc ngôn ngữ khác nhau |
| Đơn vị truyền | Java object; `ApplicationEvent` hoặc POJO/record | Bytes/message/record với headers, payload, routing metadata |
| Giao thức mạng | Không cần giao thức mạng chỉ để dispatch | Có giao thức client-broker, kết nối và broker vận hành riêng |
| Đăng ký người nhận | `ApplicationListener<E>`, `@EventListener` | Queue subscription, `@RabbitListener`, consumer group, `@KafkaListener` |
| Dispatch mặc định | Thường đồng bộ trên thread publisher | Việc gửi và việc consumer xử lý thường tách theo thời gian/thread/process |
| Độ bền | Không mặc định lưu event | Phụ thuộc broker, queue/topic, persistence, replication và cấu hình |
| Xác nhận | Lời gọi Java trả về hoặc ném lỗi; không có broker ACK | Producer confirm/ack, consumer ACK/offset theo từng broker |
| Retry | Phải thiết kế; `@Async` không tự retry bền vững | Có redelivery, retry/DLQ hoặc retry ở ứng dụng theo cấu hình |
| Transaction | Listener đồng bộ có thể chia sẻ thread-bound transaction | DB transaction và broker publish thường **không** nguyên tử |
| Ordering | Đồng bộ thường theo trình tự gọi; async có thể khác | Theo queue/partition/consumer/concurrency và chính sách redelivery |
| Hợp đồng | Thường là class Java nội bộ | Schema/version, serializer và compatibility giữa các service |
| Giám sát | Log/tracing ở publisher, listener và executor | Còn có queue depth, consumer lag, unacked, DLQ, producer confirms |
| Mất sự kiện khi crash | Có thể mất event chưa xử lý, nhất là async | Có thể tồn đọng/recover nếu đúng cấu hình, **không tự động không mất** |
| Chi phí vận hành | Thấp, dùng Spring context sẵn có | Broker, kết nối, topology, quotas, retention, monitoring, security |

**Không có kết luận “broker luôn tốt hơn Spring event”.** Đối với cập nhật cache hoặc thông báo cho một module nội bộ, `@EventListener` có thể đơn giản, đúng và dễ bảo trì hơn. Đối với thông tin phải tới nhiều service dù producer đã restart, broker cùng một phương thức lưu ý định gửi bền vững thường phù hợp hơn.

## 3. Spring event chạy như thế nào?

Một ví dụ:

```text
HTTP request / scheduled job
          |
          v
OrderService.createOrder()
          |
          v
ApplicationEventPublisher.publishEvent(OrderCreated)
          |
          v
ApplicationEventMulticaster trong Spring context
          |
        +-+-+
        |   |
        v   v
 @EventListener   ApplicationListener<OrderCreatedEvent>
        |                  |
        +-------+----------+
                |
                v
     Trả về publisher (khi callback đồng bộ hoàn tất)
```

Spring thường sử dụng `SimpleApplicationEventMulticaster`. Theo cấu hình mặc định, các listener được gọi trên **thread đang publish**, không có hàng đợi bền vững nằm giữa.

Một method ví dụ:

```java
@EventListener
public void on(OrderCreated event) {
    projectionService.update(event.orderId());
}
```

Đây là **mảnh code minh họa**, giả định có `OrderCreated` và `projectionService`. Với listener đồng bộ, nếu method này chậm thì `publishEvent(...)` có thể bị chặn. Nếu ném exception không được xử lý, exception thường lan ngược tới caller; ảnh hưởng đến transaction phụ thuộc việc event được phát ở đâu và cấu hình lỗi.

### Spring event không bắt buộc extends ApplicationEvent

Đối tượng `record OrderCreated(String orderId)` có thể được publish trực tiếp; Spring hỗ trợ nhận nó bằng `@EventListener`. Internally, Spring có thể dùng `PayloadApplicationEvent` cho payload không phải `ApplicationEvent`.

Trong khi đó, nếu một class implements `ApplicationListener<E>`, generic `E` phải extends `ApplicationEvent`. Do đó, không nên lấy ví dụ về record POJO rồi ép `ApplicationListener<OrderCreatedRecord>` nếu record không kế thừa `ApplicationEvent`.

### Có thể chạy bất đồng bộ nhưng vẫn trong application

```java
@Async("eventTaskExecutor")
@EventListener
public void on(OrderCreated event) {
    emailService.send(event.orderId());
}
```

Đây là **mảnh code minh họa**, cần `@EnableAsync`, bean executor và bean listener được Spring quản lý. Khi xử lý async, callback thường chạy thread khác. Tuy nhiên:

- Lỗi trong method async không tự lan ngược về caller.
- Task executor trong memory không tự đảm bảo còn event sau restart.
- Transaction, MDC, security context và request context không tự đi sang worker.
- Executor có thể đầy queue, từ chối task hoặc chạy theo rejection policy khác.
- Thread pool có thể giữ task nhưng không có broker message hoặc offset để replay.

**Async Spring event không tương đương broker message.**

## 4. Broker message chạy như thế nào?

Ví dụ RabbitMQ:

```text
Producer service
      |
      | Basic.Publish(exchange, routingKey, message)
      v
RabbitMQ broker
      |
      v
Topic exchange: orders.events
      |
      | routing key: order.created.v1
      +---------------------+
      |                     |
      v                     v
billing.order-created   analytics.order-created
      |                     |
      v                     v
Billing consumers       Analytics consumers
      |                     |
      v                     v
ACK/reject              ACK/reject
```

Producer gửi tới **exchange**; exchange dùng binding/routing key để quyết định queue. Mỗi queue là luồng delivery độc lập. Nếu hai service cần tự nhận mọi sự kiện, thường mỗi service có **queue riêng**. Hai instance cùng đọc một RabbitMQ queue sẽ là competing consumers, không phải cả hai đều nhận mọi message.

Với Kafka, producer gửi record vào **topic**, thường theo key; consumer group và partition quyết định việc phân chia công việc và đọc lại theo offset. Không áp dụng nguyên mô hình queue/ACK của RabbitMQ cho Kafka: Kafka có commit offset, retention và consumer group semantics riêng.

Broker có thể lưu message đến khi consumer sẵn sàng (theo cấu hình), nên producer và consumer không cần đang chạy đồng thời. Đây là **lợi ích tách rời theo thời gian** (*temporal decoupling*). Nhưng producer vẫn phải xử lý lỗi kết nối, broker còn phải đủ tài nguyên, và consumer phải biết làm gì khi payload không hợp lệ.

## 5. “Gửi thành công” có thể mang ba nghĩa khác nhau

Khi chẩn đoán, đừng dùng một biến boolean `sent=true` để đại diện cho toàn bộ pipeline.

### Mức 1 — Producer đã gọi API

```java
publisher.publishEvent(event);
rabbitTemplate.convertAndSend(exchange, routingKey, json);
```

Dòng thứ nhất chỉ chứng minh mã producer đã yêu cầu dispatch trong ứng dụng. Dòng thứ hai chỉ chứng minh lệnh gửi được gọi và có thể trả về bình thường, **không đủ** để biết message đã được route, lưu, consumer nhận hay xử lý nghiệp vụ.

### Mức 2 — Broker chấp nhận và định tuyến

Với RabbitMQ, có thể cấu hình:

- **Publisher confirms**: broker gửi ACK/NACK cho một lần publish theo cơ chế confirm.
- **Publisher returns + mandatory**: message không có queue phù hợp để route được trả về producer.

Một ACK của publisher **không đồng nghĩa consumer đã xử lý xong**. Nếu chỉ có publisher confirms mà bỏ qua returns, message có thể được broker nhận tại exchange nhưng không có queue nào nhận được.

Ví dụ cấu hình Spring Boot:

```properties
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
```

Khi cần chắc chắn, application phải **kiểm tra kết quả** từ CorrelationData/confirm callback và returned message; chỉ bật property không biến mỗi `convertAndSend` thành lệnh chờ xác nhận hoàn tất.

### Mức 3 — Consumer thực hiện xong side effect

Một `@RabbitListener` có thể nhận message, nhưng việc cập nhật DB hoặc gọi API khác vẫn có thể lỗi. Trong listener container với chế độ `AcknowledgeMode.AUTO`, khi callback hoàn tất bình thường, container thường ACK; khi lỗi, chính sách retry/requeue/reject quyết định xử lý tiếp.

Không nên ACK/commit offset quá sớm rồi mới bắt đầu side effect quan trọng. Nếu process chết sau ACK nhưng trước khi lưu nghiệp vụ, broker có thể không phát lại message đó.

## 6. Cửa sổ lỗi: tại sao Spring event và broker khác nhau?

### 6.1. Lỗi trong listener đồng bộ

```text
Service transaction mở
   -> lưu Order
   -> publishEvent(OrderCreated)
       -> listener synchronous gửi email
   -> DB commit / rollback
```

Nếu listener gửi email thành công rồi transaction DB rollback, email vẫn đã đi: **transaction local không rollback dịch vụ email**. Nếu listener ném unchecked exception trước commit, transaction gốc có thể rollback tùy cấu hình.

Một listener chỉ cập nhật dữ liệu trong cùng transaction có thể hợp lý; một listener gọi remote API trước commit cần đánh giá kỹ.

### 6.2. Lỗi khi gửi broker trực tiếp

```text
DB transaction
  UPDATE orders
  RabbitTemplate.send(order.created)
  COMMIT DB
```

Nếu RabbitMQ đã nhận message nhưng DB rollback, consumer nhìn thấy “OrderCreated” không còn đúng. Nếu DB đã commit mà gửi broker thất bại, dữ liệu nghiệp vụ tồn tại nhưng event không đến hệ thống khác.

Đây là **dual-write problem**: hai hệ thống ghi độc lập (database và broker) không tự có một transaction nguyên tử chung chỉ vì Java method được annotate `@Transactional`.

### 6.3. Gửi sau commit

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void publishToBroker(OrderCreated event) {
    bridge.send(event);
}
```

Đoạn này **chỉ minh họa** và giả định có Spring transaction đang hoạt động, bean listener, `OrderCreated` và `bridge`. Nó giúp tránh gửi event khi transaction DB rollback. Tuy nhiên, **process có thể crash ngay sau commit trước khi callback gửi thành công**. Nếu gửi lỗi, DB đã commit nên exception không làm transaction cũ đảo ngược được.

`@TransactionalEventListener` mặc định chỉ hoạt động khi có transaction tại thời điểm publish; ngoài transaction, callback bị bỏ qua nếu `fallbackExecution=false`. Nó không lưu event bền vững.

### 6.4. Transactional outbox

Khi không được mất ý định gửi, ghi thay đổi nghiệp vụ và outbox record trong cùng transaction database:

```text
@Transaction:
  save order
  INSERT outbox(id, type, payload, status=NEW)
  COMMIT
         |
         v
Outbox relay / CDC
   read NEW
   publish to broker
   wait confirm
   mark SENT
         |
         v
Consumer idempotent
```

Nếu transaction rollback, cả order và outbox cùng rollback. Nếu commit, worker có thể đọc lại outbox sau khi process restart. Tuy nhiên, worker có thể gửi thành công rồi crash trước lúc đánh dấu SENT. Khi đó message bị gửi lại, nên **at-least-once và idempotency** là thiết kế thường gặp.

Outbox giải quyết vấn đề **mất ý định gửi sau commit** tốt hơn gửi trong `@EventListener`, nhưng không có nghĩa downstream side effect chỉ xảy ra đúng một lần mà không cần logic dedup.

## 7. Độ bền và delivery semantics: không dùng nhãn tuyệt đối

Ba thuật ngữ hay gặp:

| Semantics | Ý tưởng | Rủi ro |
| --- | --- | --- |
| At-most-once | Không chủ động giao lại sau khi coi đã gửi/đã xử lý | Có thể mất message |
| At-least-once | Khi chưa xác nhận sẽ có thể retry/redelivery | Có thể trùng message |
| Exactly-once | Một bảo đảm trong **phạm vi được định nghĩa cụ thể** | Không mặc định bao phủ DB, HTTP và broker cùng lúc |

Spring application event mặc định **không phải một hệ thống delivery bền vững**, nên việc gắn nhãn “at-most-once” cũng phải cẩn trọng: một publisher có thể publish lại cùng event, hoặc ứng dụng có nhiều listener. Nó đơn giản là dispatch object theo code/context hiện tại.

Broker không tự động có một bảo đảm giống nhau ở mọi cấu hình. Ví dụ RabbitMQ:

- Durable queue giúp giữ **định nghĩa queue** sau broker restart theo cấu hình phù hợp.
- Persistent delivery mode giúp message phù hợp được lưu bền trong queue tương ứng.
- Publisher confirm giúp biết broker chấp nhận publish, **không** xác nhận business effect.
- Quorum/replication/storage, broker outage, TTL, dead-letter và policy còn ảnh hưởng khả năng mất/giữ message.
- Nếu container Docker bị xóa cùng data volume, khai báo queue durable **không làm dữ liệu xuất hiện lại**.

Với Kafka, retention, replication, acks, producer idempotence/transaction và commit offset ảnh hưởng khả năng khôi phục. Kafka transaction có những guarantee trong phạm vi Kafka, **không đồng nghĩa transaction JDBC và một API bên ngoài được atomic**.

## 8. Ví dụ thực hành: một event nội bộ và một broker message

Ví dụ dùng **Spring Boot 3.3.13, Java 17+, RabbitMQ, Maven**. Mục tiêu là quan sát sự khác nhau khi ứng dụng vừa publish Spring event vừa gửi thông điệp broker. Phiên bản Boot được khóa để dễ chạy lại bài học; với hệ thống vận hành thực, nên chọn nhánh còn được hỗ trợ và kiểm tra dependency/security updates.

Trong demo:
1. `CommandLineRunner` publish `LocalOrderCreated` trong context.
2. `@EventListener` xử lý ngay, không cần network.
3. Runner biến dữ liệu sang `OrderCreatedWire` và gửi JSON đến RabbitMQ exchange.
4. Broker route message vào queue.
5. `@RabbitListener` nhận message trên listener container riêng.
6. Runner dùng `CountDownLatch` để đợi callback bên broker, tránh kết thúc app trước khi thấy kết quả.

**Quan trọng:** Đây là demo **hai kênh dispatch song song nhằm so sánh**, không phải transactional outbox hoặc cách phát hai lần phục vụ hai hệ thống production.

### 8.1. Cấu trúc project

```text
spring-event-vs-broker/
├── pom.xml
├── compose.yaml
└── src/
    ├── main/
    │   ├── java/example/events/EventComparisonDemo.java
    │   └── resources/application.properties
    └── test/java/example/events/EventContractTest.java
```

### 8.2. compose.yaml

```yaml
services:
  rabbitmq:
    image: rabbitmq:4.1-management
    ports:
      - "5672:5672"
      - "15672:15672"
```

Chạy RabbitMQ bằng Docker Compose:

```bash
docker compose up -d
docker compose exec rabbitmq rabbitmq-diagnostics -q ping
```

Tài khoản mặc định của image demo thường là `guest/guest` khi truy cập local; trang quản trị ở `http://localhost:15672`. **Chỉ dùng cấu hình này trên máy học tập**, không expose port/credential demo ra mạng công cộng.

### 8.3. pom.xml

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
    <artifactId>spring-event-vs-broker</artifactId>
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

### 8.4. application.properties

```properties
spring.main.web-application-type=none

spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
spring.rabbitmq.username=guest
spring.rabbitmq.password=guest

# Demo không có DLQ; không để poison message requeue vô hạn.
spring.rabbitmq.listener.simple.default-requeue-rejected=false

logging.level.root=WARN
```

Cấu hình trên dùng RabbitMQ ở máy local; nó không thiết lập publisher confirms, retry có giới hạn, DLX/DLQ hay outbox. Nếu consumer lỗi, message có thể bị reject và **bị loại bỏ** vì không có DLQ, nên không dùng chính sách này nguyên xi ở production.

### 8.5. EventComparisonDemo.java

```java
package example.events;

import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.ObjectMapper;

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
public class EventComparisonDemo {

    private static final String EXCHANGE = "demo.orders.events";
    private static final String ROUTING_KEY = "order.created.v1";
    private static final String QUEUE = "demo.billing.order-created.v1";

    // Spring event nội bộ: record Java bình thường.
    public record LocalOrderCreated(
            String eventId,
            String orderId,
            long amountMinorUnits,
            Instant occurredAt) {
    }

    // Message payload dùng trên wire: có schema version rõ ràng.
    public record OrderCreatedWire(
            String eventId,
            String eventType,
            int schemaVersion,
            String orderId,
            long amountMinorUnits,
            String occurredAt) {
    }

    // Mapper thuần Java: không phụ thuộc broker.
    public static OrderCreatedWire toWire(LocalOrderCreated event) {
        return new OrderCreatedWire(
                event.eventId(),
                "order.created",
                1,
                event.orderId(),
                event.amountMinorUnits(),
                event.occurredAt().toString());
    }

    public static final class InternalListener {
        @EventListener
        public void on(LocalOrderCreated event) {
            System.out.println(
                    "LOCAL_LISTENER id=" + event.eventId());
        }
    }

    public static final class BrokerListener {
        private final ObjectMapper mapper;
        private final CountDownLatch observed;

        public BrokerListener(ObjectMapper mapper,
                              CountDownLatch observed) {
            this.mapper = mapper;
            this.observed = observed;
        }

        @RabbitListener(queues = QUEUE)
        public void on(String json) throws Exception {
            OrderCreatedWire message =
                    mapper.readValue(json, OrderCreatedWire.class);

            if (!"order.created".equals(message.eventType())
                    || message.schemaVersion() != 1) {
                throw new IllegalArgumentException(
                        "Unexpected event type or version");
            }

            System.out.printf(
                    "BROKER_LISTENER id=%s order=%s%n",
                    message.eventId(),
                    message.orderId());

            // Chỉ để đồng bộ stdout trong demo, không thay broker ACK.
            observed.countDown();
        }
    }

    @Bean
    InternalListener internalListener() {
        return new InternalListener();
    }

    @Bean
    CountDownLatch brokerObserved() {
        return new CountDownLatch(1);
    }

    @Bean
    BrokerListener brokerListener(
            ObjectMapper mapper, CountDownLatch brokerObserved) {
        return new BrokerListener(mapper, brokerObserved);
    }

    @Bean
    TopicExchange orderExchange() {
        return new TopicExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue orderQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding orderBinding(
            Queue orderQueue, TopicExchange orderExchange) {
        return BindingBuilder.bind(orderQueue)
                .to(orderExchange)
                .with(ROUTING_KEY);
    }

    @Bean
    CommandLineRunner compare(
            ApplicationEventPublisher publisher,
            RabbitTemplate rabbitTemplate,
            ObjectMapper mapper,
            CountDownLatch brokerObserved) {

        return args -> {
            LocalOrderCreated local = new LocalOrderCreated(
                    "evt-42",
                    "ORD-42",
                    12500L,
                    Instant.parse("2026-11-11T06:00:00Z"));

            System.out.println("LOCAL_PUBLISH id=evt-42");
            publisher.publishEvent(local);
            System.out.println("LOCAL_RETURN id=evt-42");

            OrderCreatedWire wire = toWire(local);
            String json = mapper.writeValueAsString(wire);

            System.out.println("BROKER_SEND_START id=evt-42");
            rabbitTemplate.convertAndSend(
                    EXCHANGE,
                    ROUTING_KEY,
                    json,
                    amqpMessage -> {
                        amqpMessage.getMessageProperties()
                                .setDeliveryMode(
                                        MessageDeliveryMode.PERSISTENT);
                        return amqpMessage;
                    });

            System.out.println("BROKER_SEND_RETURN id=evt-42");

            if (!brokerObserved.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Broker consumer did not receive message");
            }

            System.out.println("BROKER_OBSERVED id=evt-42");
        };
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(
                             EventComparisonDemo.class, args)) {
            // Runner chạy trong startup; context đóng khi kết thúc.
        }
    }
}
```

**Giải thích annotation:**
- `@EventListener` nhận record `LocalOrderCreated` qua Spring context mà không cần broker.
- `@RabbitListener` không nhận record Java đó; nó nhận **JSON String từ RabbitMQ** qua listener container và sau đó deserialize thành `OrderCreatedWire`.
- `TopicExchange`, durable `Queue` và `Binding` được đăng ký thành bean; Spring AMQP có thể khai báo topology ở broker khi ứng dụng kết nối.
- `MessageDeliveryMode.PERSISTENT` yêu cầu broker xử lý message như persistent, nhưng **không phải bảo đảm tuyệt đối về durability**.
- `CountDownLatch` chỉ giúp demo đợi consumer trước khi ứng dụng kết thúc.

### 8.6. Chạy và đọc kết quả

Sau khi broker đã sẵn sàng:

```bash
mvn -q package
java -jar target/spring-event-vs-broker-1.0.0.jar
```

Phần **Spring event nội bộ** tạo ba dòng theo đúng thứ tự:

```text
LOCAL_PUBLISH id=evt-42
LOCAL_LISTENER id=evt-42
LOCAL_RETURN id=evt-42
```

Sau đó broker path tạo thêm ba dòng:

```text
BROKER_SEND_START id=evt-42
BROKER_SEND_RETURN id=evt-42
BROKER_LISTENER id=evt-42 order=ORD-42
BROKER_OBSERVED id=evt-42
```

**Lưu ý thứ tự:** Ba dòng đầu của internal event có thứ tự ổn định do listener đồng bộ. Trong phần broker, **`BROKER_LISTENER` có thể xuất hiện trước hoặc sau `BROKER_SEND_RETURN`**, vì consumer là worker độc lập. Chỉ chắc chắn rằng `BROKER_OBSERVED` xuất hiện sau khi listener đã gọi `countDown()`; `BROKER_SEND_START` xảy ra trước khi gọi lệnh gửi.

Dòng `BROKER_SEND_RETURN` không phải broker confirm và `BROKER_OBSERVED` không phải một API báo ACK; đây là dấu vết do ứng dụng tự in. Demo không mở database transaction và không tự cung cấp exactly-once, retry bền vững hoặc producer confirm.

Kết thúc:

```bash
docker compose down
```

Nếu muốn giữ message sau khi xóa container, thêm volume bền vững. Một queue durable **không** giúp phục hồi dữ liệu nếu toàn bộ storage của broker bị xóa.

## 9. Kiểm thử: phân biệt logic nội bộ với broker integration

### 9.1. Kiểm thử mapping đơn giản không cần RabbitMQ

File `src/test/java/example/events/EventContractTest.java`:

```java
package example.events;

import java.time.Instant;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class EventContractTest {

    @Test
    void internalEventMapsToVersionedWireContract() {
        var local = new EventComparisonDemo.LocalOrderCreated(
                "evt-test",
                "ORD-TEST",
                2500L,
                Instant.parse("2026-11-11T06:00:00Z"));

        var wire = EventComparisonDemo.toWire(local);

        assertEquals("evt-test", wire.eventId());
        assertEquals("order.created", wire.eventType());
        assertEquals(1, wire.schemaVersion());
        assertEquals("ORD-TEST", wire.orderId());
        assertEquals(2500L, wire.amountMinorUnits());
        assertEquals("2026-11-11T06:00:00Z",
                wire.occurredAt());
    }
}
```

Chạy:

```bash
mvn -Dtest=EventContractTest test
```

Test này kiểm tra mapping từ Java record nội bộ sang schema wire. Nó **không khởi động RabbitMQ**, không chứng minh exchange/queue tồn tại và không kiểm thử consumer ACK. Muốn xác nhận broker path, chạy demo với RabbitMQ thực hoặc dùng Testcontainers + integration test có timeout.

### 9.2. Các tầng test cần có

| Mức kiểm thử | Xác minh | Không thể thay thế |
| --- | --- | --- |
| Unit test listener Spring | Logic callback, exception, tham số | Việc Spring đăng ký/match listener |
| Spring context integration | `publishEvent` thực sự gọi listener phù hợp | Broker routing và persistence |
| Serialization/contract | JSON/schemaVersion và field semantics | Broker ACK và consumer business effect |
| Broker integration | Exchange, queue, routing, consumer nhận được message | Dual-write/transaction failure |
| Transaction integration | Rollback/AFTER_COMMIT và outbox atomic | Sự cố broker/worker thật |
| Failure/recovery test | Consumer crash trước ACK, producer retry, DLQ, idempotency | Nghiệp vụ khác và quyền truy cập |

**Đừng dùng một test “`convertAndSend` không ném exception” để kết luận message đã tới consumer**. Khi cần delivery guarantee, kiểm tra publisher confirms/returns và trạng thái xử lý downstream.

## 10. Hợp đồng dữ liệu: internal class và integration schema

Một Java class nội bộ có thể refactor tên, đổi package, thêm field, thay representation để phục vụ cùng một module. Thay đổi đó có thể không ảnh hưởng phần còn lại nếu code cùng được build/deploy.

Trên broker, consumer có thể là service deploy độc lập hoặc thậm chí viết bằng ngôn ngữ khác. Vì thế:

- Dùng `eventType` ổn định, ví dụ `order.created`.
- Có `schemaVersion` hoặc hệ thống schema registry tương ứng.
- Quy định field required/optional/default, đơn vị tiền, currency, timezone và null semantics.
- Có `eventId`/correlation ID đủ để trace/dedup.
- Không serialize trực tiếp JPA entity hoặc Spring `ApplicationEvent` nếu consumer không cần Java class/source.
- Có contract tests với payload thực của các phiên bản trước, đặc biệt khi outbox/broker giữ message cũ.
- Thay đổi ý nghĩa nghiệp vụ có thể đòi một **event type mới**, không chỉ tăng version.

Ví dụ envelope đơn giản:

```json
{
  "eventId": "evt-42",
  "eventType": "order.created",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T06:00:00Z",
  "orderId": "ORD-42",
  "amountMinorUnits": 12500
}
```

Bản ghi này là **hợp đồng minh họa**, không phải cấu trúc do RabbitMQ hoặc Spring Framework bắt buộc. RabbitMQ có message properties/headers riêng; Kafka có headers và record key. Metadata transport và payload nghiệp vụ nên được phân định rõ.

## 11. Retry, redelivery và idempotency

Với Spring event đồng bộ, khi listener lỗi, xử lý tiếp hay rollback phụ thuộc vào exception, transaction, `ErrorHandler` và ứng dụng. Spring không mặc định lưu một event lỗi để phát lại sau restart. Bạn có thể dùng Spring Retry hoặc job store, nhưng đó là **thiết kế bổ sung**.

Với broker, consumer có thể nhận cùng message nhiều lần:

```text
Broker giao evt-42
       |
       v
Consumer cập nhật DB thành công
       |
       v
Consumer crash trước khi ACK
       |
       v
Broker giao lại evt-42
```

Nếu lần giao lại tiếp tục ghi DB, có thể tạo side effect trùng. Cách xử lý hay dùng là **inbox/dedup table**:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Khi consumer chỉ sửa **cùng một database**, ghi dấu xử lý và update nghiệp vụ trong **một transaction**. Unique constraint bảo vệ việc hai worker xử lý đồng thời. Nếu duplicate, quyết định bỏ qua và ACK theo hợp đồng.

Đối với side effect bên ngoài như thanh toán hay email, cần **idempotency key được downstream hiểu**, hoặc workflow có thể xác minh kết quả sau timeout. Lưu dedup flag ở DB rồi gọi HTTP sau commit mà không có cơ chế phục hồi vẫn có cửa sổ mất công việc.

### Retry không phải chuyện bật một property

- Lỗi tạm như mất kết nối, rate limit có thể retry theo giới hạn/backoff.
- Lỗi schema/validation thường không tự hết khi thử cùng payload.
- Message độc (*poison message*) nên đưa vào dead-letter queue/quarantine để điều tra.
- RabbitMQ có thể requeue theo container policy; nếu không giới hạn, cùng message lỗi có thể bị nhận đi nhận lại rất nhanh.
- Kafka consumer có mô hình offset/retry topic/dead-letter riêng, không đồng nhất với RabbitMQ reject/requeue.

**Bảo đảm hợp lý thường là “at-least-once delivery + idempotent business effect”**, không tuyên bố exactly-once end-to-end chỉ vì có broker.

## 12. Ordering và thời gian xử lý

Trong Spring listener đồng bộ, khi ứng dụng phát lần lượt A rồi B từ cùng thread, callback đồng bộ của A thường chạy trước khi lời gọi publish A hoàn tất. Nhưng nếu nhiều listener, async tasks hoặc nhiều thread cùng publish, thứ tự nghiệp vụ có thể không còn đơn giản.

Trong broker:

- RabbitMQ một queue với một consumer có thể dễ kiểm soát thứ tự hơn nhiều consumer song song; requeue, ưu tiên và retries vẫn có thể ảnh hưởng.
- Kafka có bảo đảm ordering theo partition trong các điều kiện cấu hình nhất định; event cùng aggregate có thể dùng partition key để hỗ trợ xử lý theo thứ tự.
- Consumer nhận event trước/sau không luôn đồng nghĩa trạng thái DB có thứ tự đó, nhất là khi producer/outbox có nhiều worker.
- Nếu nghiệp vụ cần kiểm tra thứ tự, thêm `aggregateVersion`/sequence và xây logic chống event cũ hoặc nhận thiếu event.

Ví dụ:

```text
OrderCreated(orderId=ORD-42, aggregateVersion=1)
OrderPaid(orderId=ORD-42, aggregateVersion=2)
OrderCancelled(orderId=ORD-42, aggregateVersion=3)
```

`aggregateVersion` diễn tả thứ tự thay đổi của aggregate, còn `schemaVersion` diễn tả hợp đồng payload. **Không dùng schemaVersion để suy luận thứ tự business events.**

## 13. Security, context và tracing

### Spring event trong process

Listener đồng bộ có thể nhìn thấy `ThreadLocal`, MDC hoặc imperative transaction context gắn với thread của publisher tại lúc gọi. Điều đó không có nghĩa mọi listener dùng đúng principal, hoặc transaction chắc chắn sẽ commit.

Listener async thường chạy trên worker thread khác, nên context không tự được truyền. Nếu cần, dùng `TaskDecorator`/context propagation phù hợp, hoặc đưa correlation ID vào event; **không copy bừa JDBC transaction ThreadLocal** sang thread khác.

### Broker message qua network

Consumer nằm ở process khác, không có Java `ThreadLocal` hoặc Spring `SecurityContextHolder` của producer. Nếu cần correlation, truyền ID qua headers/payload theo hợp đồng và khởi tạo **trace span của consumer** theo hệ thống tracing. Không nhét access token hoặc cookie request vào message để “giữ context”.

Một thiết kế quan sát cơ bản:

```text
producer log:
  eventId=evt-42 traceId=t-91 stage=publish_started

broker relay log:
  eventId=evt-42 traceId=t-91 stage=broker_confirmed

consumer log:
  eventId=evt-42 traceId=t-91 stage=processed
```

Những dòng trên là **định dạng log gợi ý**, không phải log Spring tự sinh. Không dùng `eventId`/`orderId` làm metric tag vì cardinality rất lớn; nên để chúng trong log/traces theo quyền truy cập.

### Phân quyền và dữ liệu

Với broker, mỗi service nên có credential và quyền publish/subscribe giới hạn theo vhost/topic/queue. Bật TLS khi dữ liệu đi qua hạ tầng không tin cậy, có chính sách retention/DLQ và loại dữ liệu nhạy cảm ra khỏi payload nếu không cần. Broker cho phép truyền dữ liệu xa hơn nên ranh giới bảo mật **rộng hơn** callback trong cùng JVM.

## 14. Quan sát và vận hành: nên nhìn chỉ số nào?

| Spring event | Broker message |
| --- | --- |
| Số event được publish theo loại | Producer publish attempts / confirm ACK-NACK |
| Số callback bắt đầu, kết thúc, thất bại | Broker queue depth/topic lag |
| Listener latency | Consumer end-to-end processing latency |
| Executor active threads, queue, rejection | Consumer count, unacked, rebalance, offsets |
| Transaction phase/rollback | Retry/redelivery, DLQ/quarantine |
| Exception propagation và ErrorHandler | Publisher returns, unroutable messages |
| MDC/trace propagation | Cross-service tracing/correlation |
| Startup/lifecycle registration | Broker availability, retention, replication, quota |

Các tên metric cụ thể tùy Micrometer/Spring Boot/broker exporter; không tự khẳng định hệ thống đã có sẵn mọi metric chỉ vì thêm annotation listener.

Với broker, còn phải quản lý connection pool, channel, topology migration, schema compatibility, partition/queue scaling, dead-letter replay và quyền truy cập. Chi phí này có thể đáng giá cho nhiều service độc lập, nhưng quá nặng nếu chỉ cần hai bean trao đổi dữ liệu trong một context.

## 15. Chọn phương án cho từng nhu cầu

### Khi nên ưu tiên Spring Application Events

- Các module nằm trong cùng ứng dụng và lifecycle triển khai.
- Event không cần giữ lại sau khi process kết thúc, hoặc tác dụng phụ có thể tái tính toán.
- Muốn tách logic thông báo nội bộ, cache/projection hoặc xử lý UI/metrics best-effort.
- Không cần kết nối network, không muốn vận hành hạ tầng messaging.
- Có thể chịu trách nhiệm kiểm soát exception và độ trễ callback.

Ví dụ, một ứng dụng monolith cập nhật bộ nhớ cache phụ khi một domain object thay đổi. Nếu cache mất event, có thể làm mới bằng cách đọc nguồn dữ liệu bền vững.

### Khi nên ưu tiên broker

- Service khác cần nhận sự kiện mà không phụ thuộc thời gian sống của producer.
- Có nhiều subscriber deploy độc lập, mỗi subscriber cần queue/group và retry riêng.
- Cần chịu burst traffic, backpressure hoặc xử lý chậm tách khỏi request.
- Muốn giữ/replay message theo retention của broker.
- Có yêu cầu logging, audit, retry/triage lỗi xuyên service.
- Chấp nhận đầu tư vận hành, schema versioning và idempotency.

Ví dụ Billing, Shipping, Analytics cùng cần biết đơn đã được tạo. Mỗi bounded context có trách nhiệm riêng và có thể triển khai khác lịch.

### Khi cần kết hợp cả hai

Một kiến trúc hợp lý:

```text
Order aggregate
    |
    v
Domain event OrderCreated
    |
    v
Application service / internal handlers
    |
    +--> internal cache/projection event listener
    |
    +--> cùng DB transaction:
           UPDATE orders
           INSERT outbox(eventId, payload)
                 |
                 v
           Outbox relay
                 |
                 v
              Broker
                 |
            +----+----+
            |         |
            v         v
          Billing   Shipping
```

**Không mặc định phải publish Spring event rồi mới ghi outbox.** Khi invariants yêu cầu không mất integration event, application service có thể ghi outbox ngay trong transaction sau khi aggregate tạo domain event; hoặc hạ tầng tương ứng phải bảo đảm outbox được ghi đúng phase. Điều cần chứng minh là **atomicity của business change và outbox record**, không phải số lần gọi annotation.

## 16. Những lỗi nhận thức phổ biến

**1. “@Async biến Spring event thành queue.”** Sai: executor trong RAM không phải message broker bền vững.

**2. “Broker bảo đảm message không bao giờ mất.”** Sai: phụ thuộc confirm, persistence, replication, retention, topology, consumer ACK và lỗi hạ tầng.

**3. “publishEvent trả về nghĩa là mọi listener đã thành công.”** Chỉ trong đường đồng bộ phù hợp có thể suy luận callback đã trả về; async/condition/transaction phase thay đổi điều đó.

**4. “convertAndSend trả về nghĩa là consumer đã xử lý.”** Sai: producer send, broker confirm và consumer side effect là các mốc khác nhau.

**5. “@Transactional làm DB và RabbitMQ cùng commit.”** Sai: một transaction JDBC thông thường không tự gom broker vào atomic transaction.

**6. “@TransactionalEventListener(AFTER_COMMIT) là outbox.”** Sai: AFTER_COMMIT vẫn có cửa sổ process chết sau DB commit trước khi gửi.

**7. “Chỉ cần duplicate retry, hệ thống tự exactly-once.”** Retry giúp khôi phục nhưng dễ gây side effect lặp; cần idempotency.

**8. “Một queue cho tất cả service, ai cũng nhận.”** Với RabbitMQ, nhiều consumer trên cùng queue thường chia nhau messages. Muốn mỗi service nhận mỗi event, thiết kế queue/group riêng.

**9. “Dùng Java ApplicationEvent làm JSON contract cho mọi service.”** Gây phụ thuộc class/package và rủi ro lazy-loading/PII. Dùng integration DTO và schema.

**10. “Mọi event đều có thứ tự toàn hệ thống.”** Ordering bị ảnh hưởng bởi concurrency, partitioning, retry, broker semantics. Dùng aggregate sequence khi cần.

**11. “MDC đi qua RabbitMQ như qua method call.”** Sai: context gắn thread không tự đi qua process; truyền correlation/trace metadata theo tiêu chuẩn.

**12. “Có DLQ tức là đã xử lý xong lỗi.”** DLQ là nơi giữ message thất bại, cần cảnh báo, điều tra, fix và replay có kiểm soát.

**13. “Tăng số consumer luôn tăng throughput.”** Có thể tạo cạnh tranh DB, vượt downstream quota, phá yêu cầu ordering hoặc tăng retries.

**14. “Cần broker cho mọi microinteraction.”** Thêm broker khi không có yêu cầu giao tiếp xuyên service hoặc persistence sẽ làm tăng latency, topology và complexity không cần thiết.

## 17. Ma trận sự cố và cách xác minh

| Tình huống | Spring event thông thường | Broker message |
| --- | --- | --- |
| Listener/consumer tạm lỗi | Exception ở thread đồng bộ/async; cần chính sách ứng dụng | Retry/requeue/replay/DLQ theo consumer/broker |
| Publisher process chết ngay sau publish | Có thể mất task async chưa chạy | Message có thể vẫn ở broker nếu đã confirm và lưu bền đúng |
| Consumer không chạy | Không có một queue bền vững mặc định để đợi | Message có thể ở queue/topic đến khi consumer lên lại, theo retention |
| DB rollback sau khi phát | Callback trước commit có thể đã chạy | Direct broker send trước commit có thể tạo phantom event |
| Crash sau DB commit trước send | Event chưa được broker nhận có thể mất | Outbox có thể giữ ý định gửi nếu cùng DB transaction |
| Mất broker connection | Không liên quan đến pure internal dispatch | Producer send lỗi/timeout; xác nhận và retry theo hợp đồng |
| Message bị gửi trùng | Publisher/listener logic phải quản lý | Producer retry/redelivery có thể gây trùng; cần dedup |
| Payload schema đổi | Thường cùng codebase/Java type, vẫn cần tương thích | Consumer độc lập cần schema version/contract tests |
| Downstream chỉ xử lý một phần | Không có outcome toàn hệ thống tự động | Cần trạng thái consumer, idempotency, saga/outbox khác |
| Tăng tải đột ngột | Thread pool nội bộ có thể nghẽn | Broker buffer/backpressure theo resource và retention |

### Kiểm thử lỗi đúng phạm vi

1. Spring context test: publish event thật, assert listener được gọi đúng số lần/type.
2. Spring async test: task hoàn thành với latch/timeout; assert exception handler hoặc trạng thái lỗi.
3. Broker integration test: chạy RabbitMQ/Testcontainers, assert binding/routing và payload.
4. Confirm/return test: gửi vào routing key không có queue, phân biệt broker ACK và returned message.
5. Transaction integration: DB rollback không sinh integration event “đã commit”; commit có outbox record.
6. Crash/retry test: relay gửi thành công rồi chết trước mark-SENT; consumer bỏ qua duplicate.
7. Consumer test: dữ liệu lỗi/sai version được quarantine, không requeue vô hạn.
8. Ordering test: nhiều worker, thông điệp cùng aggregate, xử lý event cũ/missing event.

Khi test async/broker, dùng latch hoặc polling có timeout; đừng dùng `Thread.sleep(100)` rồi giả định hệ thống chắc chắn hoàn tất. Tránh dựa vào stdout order khi hai luồng/process chạy song song.

## 18. Checklist thiết kế trước khi lựa chọn

1. Event chỉ dành cho bean trong cùng ứng dụng hay phải đến service khác?
2. Nếu producer restart, thông điệp có bắt buộc vẫn đến consumer?
3. Có cần nhiều subscriber độc lập, mỗi bên retry theo nhịp riêng?
4. Thời gian xử lý có được phép chặn request/transaction gốc không?
5. Đã hiểu rõ mốc **business commit**, **broker confirm**, **consumer success**?
6. Nếu DB và broker đều được ghi, đã giải quyết dual-write bằng outbox hoặc cơ chế chứng minh tương đương?
7. Có eventId, schemaVersion và hợp đồng payload độc lập class Java nội bộ?
8. Khi at-least-once delivery, consumer đã có idempotency key và unique constraint thích hợp?
9. Có retry/backoff, DLQ, monitoring và quy trình replay?
10. Ordering theo aggregate/partition/queue cần bảo đảm đến mức nào?
11. Có bảo vệ credential, PII, retention và quyền truy cập broker?
12. Test đã tái hiện crash, rollback, mất kết nối và duplicate trước khi đưa production?

**Kết luận:** Spring Application Events và broker message là **hai cơ chế khác tầng**. Spring event phù hợp giao tiếp nội bộ trong một tiến trình, mặc định đồng bộ và không có lưu trữ event bền vững. Broker hỗ trợ liên kết những service độc lập qua hạ tầng messaging, nhưng delivery và business effect chỉ đáng tin khi kết hợp đúng **publisher confirms, persistence, retry, transaction/outbox và idempotent consumer**. Chọn cơ chế theo ranh giới hệ thống và mức độ mất/nhận trùng được phép, không chỉ theo tên “event”.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): dispatch đồng bộ, `@EventListener`, `ApplicationEventPublisher`, `@Async`.
- [Spring Framework — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): thread model, executor và error handler.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): transaction phases và `fallbackExecution`.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): `RabbitTemplate`, `@RabbitListener`, retry và queues.
- [Spring AMQP — RabbitTemplate and Publisher Confirms/Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): semantics gửi, confirms/returns.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): hai lớp xác nhận khác nhau.
- [Apache Kafka — Delivery Semantics](https://kafka.apache.org/documentation/#semantics): phạm vi delivery và producer/consumer settings.
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html): dual-write, relay và duplicate.

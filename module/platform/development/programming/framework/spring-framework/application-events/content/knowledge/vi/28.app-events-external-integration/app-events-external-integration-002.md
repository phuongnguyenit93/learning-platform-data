# Khi dùng Kafka, RabbitMQ hoặc JMS để tích hợp Spring Application Events ra ngoài ứng dụng

## 1. Bài toán và ranh giới kiến trúc

Trong nhóm **Tích hợp ngoài ứng dụng** của chủ đề **Spring Framework Application Events**, câu hỏi không phải “thay `@EventListener` bằng annotation nào?”, mà là **khi nào một sự kiện phải vượt qua ranh giới JVM, được lưu bền vững và được một hệ thống khác tiêu thụ**.

Spring Framework có `ApplicationEventPublisher` và `@EventListener` để giao tiếp giữa các bean/module **trong cùng `ApplicationContext`**, hoặc truyền từ child context lên parent theo quy tắc hierarchy. Ví dụ:

```java
publisher.publishEvent(new OrderPaid("O-42", 125_000));
```

Đây là mã minh họa; `OrderPaid` do ứng dụng định nghĩa. Lời gọi trên không tự gửi một record tới topic Kafka, exchange RabbitMQ hay destination JMS. Nó cũng không tự lưu event để replay sau restart.

Với hai microservices ở hai process khác nhau:

```text
Spring Application A                              Spring Application B
--------------------                              --------------------
OrderService
    |
    +-- ApplicationEventPublisher
              |
              +-- @EventListener trong A
              |
              +-- Bridge / Externalizer
                      |
                      +-- Message broker --------> Broker consumer của B
                          (Kafka/RabbitMQ/JMS)      |
                                                    +-- Xử lý nghiệp vụ B
```

Tầng bridge phải làm thêm những việc mà `ApplicationEventPublisher` không tự làm: **chuyển event sang contract bên ngoài, serialize, chọn routing target/key, gửi tới broker, quan sát xác nhận, retry và xử lý khả năng gửi trùng**.

### Quy tắc lựa chọn ban đầu

- Chỉ các thành phần trong cùng JVM cần notification ngắn hạn, mất event khi process chết có thể chấp nhận: **Application Events** thường đủ.
- Nhiều service độc lập phải nhận thông điệp, có queue/retry, quản lý consumer lifecycle: cân nhắc **RabbitMQ hoặc JMS provider**, tùy topology và hạ tầng.
- Có nhu cầu log stream, đọc lại trong retention, nhiều consumer groups và xử lý theo partition: cân nhắc **Kafka**.
- Cập nhật DB và **bắt buộc** phát thông điệp không được mất: chọn một cơ chế **transactional outbox/event publication registry bền vững** hoặc giải pháp transaction được chứng minh phù hợp; chỉ đổi sang broker không tự giải bài toán nhất quán.

## 2. So sánh ba lựa chọn

| Khía cạnh | Kafka | RabbitMQ | JMS |
| --- | --- | --- | --- |
| Bản chất | Distributed event log với topics/partitions | Message broker với exchanges, bindings và queues | Đặc tả/API nhắn tin Jakarta; dùng JMS provider |
| Tích hợp Spring | Spring for Apache Kafka | Spring AMQP | Spring JMS |
| Producer phổ biến | `KafkaTemplate<K,V>` | `RabbitTemplate` | `JmsTemplate` |
| Consumer phổ biến | `@KafkaListener` | `@RabbitListener` | `@JmsListener` |
| Phân phối cho nhiều hệ thống | Consumer groups đọc stream riêng | Mỗi hệ thống có queue bind vào exchange | Topics/durable subscriptions |
| Một worker xử lý một công việc | Consumer group/partitions, cần thiết kế | Work queue/competing consumers rất tự nhiên | Queue/competing consumers |
| Replay | Có nếu log còn trong retention | Queue thường xóa/ack message; cần event store riêng nếu muốn replay lịch sử | Provider và durable subscription quyết định |
| Ordering | Bảo đảm log order **trong một partition** | Phụ thuộc queue, consumer concurrency, prefetch, requeue | Phụ thuộc provider, session, destination, concurrency |
| Producer confirmation | Future result/record metadata | Publisher confirm, return, mandatory routing | Send/session/transaction contract của provider |
| Delivery acknowledgment | Consumer offsets/commit | Consumer ACK/NACK/requeue | Session acknowledgment/transaction |
| Retry, dead letter | Error handlers, retry topics, DLT | Requeue, retry, dead-letter exchange/queue | Provider redelivery và DLQ policy |

**JMS không phải một sản phẩm broker duy nhất.** Nó là lớp API/đặc tả; ví dụ hệ thống có thể dùng ActiveMQ Artemis làm provider và Spring JMS làm integration layer. Không thể suy luận mọi provider có retention, ack timing và DLQ giống hệt nhau.

**Có broker không đồng nghĩa exactly-once business processing.** Khi xảy ra crash hoặc timeout, hệ thống thường phải chịu được việc message **được gửi hoặc nhận nhiều lần**.

## 3. Kafka: khi cần event stream, consumer groups và replay

Kafka tổ chức records theo topics và partitions. Producer có thể đặt key để các event của một aggregate (`orderId`) được định tuyến nhất quán vào một partition, nếu partitioning configuration ổn định. Một partition có thứ tự log của chính nó; không nên giả định thứ tự toàn cục giữa nhiều partitions.

### 3.1. Gửi qua `KafkaTemplate`

```java
@Component
public class KafkaOrderPublisher {

    private final KafkaTemplate<String, String> kafka;

    public KafkaOrderPublisher(KafkaTemplate<String, String> kafka) {
        this.kafka = kafka;
    }

    public void send(ExternalEvent event) {
        String json = serialize(event);

        kafka.send("orders.events.v1",
                   event.aggregateId(), json)
                .whenComplete((result, failure) -> {
                    if (failure != null) {
                        recordFailure(event.eventId(), failure);
                    } else {
                        recordAck(event.eventId(),
                                result.getRecordMetadata().partition(),
                                result.getRecordMetadata().offset());
                    }
                });
    }
}
```

**Đây là đoạn minh họa**, không phải chương trình độc lập. `ExternalEvent`, `serialize`, `recordFailure`, `recordAck`, imports, Kafka producer properties và credentials do dự án cung cấp.

Trong các phiên bản Spring Kafka hiện đại, `KafkaTemplate.send(...)` trả `CompletableFuture<SendResult<K,V>>`. **Lúc gọi `send()` chưa phải lúc broker xác nhận đã lưu record**. Cần quan sát future/callback và lỗi bất đồng bộ. Producer ACK chỉ chứng minh kết quả của bước gửi theo Kafka protocol, **không chứng minh billing service đã xử lý nghiệp vụ thành công**.

Chọn key theo aggregate khi cần ordering:

```text
topic=orders.events.v1
key=O-42
value={eventId, aggregateId=O-42, sequence=7, ...}
```

Nhưng key không cứu được thứ tự nếu producer/relay **gửi các event của O-42 sai sequence**, hoặc consumer đưa records của cùng key vào nhiều worker chạy song song rồi commit offset bất cẩn.

### 3.2. Nhận qua `@KafkaListener`

```java
@Component
public class BillingKafkaListener {

    @KafkaListener(
            topics = "orders.events.v1",
            groupId = "billing-service")
    public void handle(String json) {
        ExternalEvent event = decodeAndValidate(json);
        processIdempotently(event);
    }
}
```

Đây là đoạn minh họa; cần `@EnableKafka`/Spring Boot Kafka configuration, listener container factory, converters và business processor.

- Mỗi consumer group có **tiến độ đọc/offset riêng**; analytics group và billing group có thể đều đọc cùng topic.
- Các instances trong cùng group phân chia partitions theo assignment.
- `@KafkaListener` là listener **message từ Kafka**, không phải `@EventListener` từ `ApplicationEventPublisher`.
- Error handler, retry topic/DLT, commit offset và consumer transaction phải được cấu hình rõ.
- Retention cho phép replay nếu record còn được lưu; không xem Kafka topic như storage vô hạn.

### 3.3. Kafka transactions có thay thế outbox không?

Kafka hỗ trợ idempotent producer và giao dịch trong phạm vi các Kafka records/offsets được hỗ trợ. Nhưng bật Kafka transactions **không tự tạo một atomic transaction giữa Kafka với database nghiệp vụ bất kỳ**, cũng không bao gồm email, HTTP hoặc payment gateway ngoài Kafka.

Nếu một method `@Transactional` chỉ dùng JDBC transaction manager nhưng gọi `KafkaTemplate.send(...)`, không được suy luận cả hai sẽ commit/rollback nguyên tử. Có các cách phối hợp transaction, nhưng mỗi cách cần kiểm tra thứ tự commit và cửa sổ lỗi; không đánh đồng transaction synchronization với distributed XA.

## 4. RabbitMQ: khi cần exchange routing, nhiều queues và work queues

RabbitMQ dùng **exchange** nhận message từ producer rồi định tuyến qua **bindings** đến một hoặc nhiều queues.

```text
Producer
   |
   +-- exchange: domain.events
          |
          +-- routing key: order.paid
                 |
                 +-- queue: billing.paid
                 |
                 +-- queue: analytics.paid
```

Mỗi queue có thể có một hoặc nhiều competing consumers. Nếu hai service phải **đều nhận bản sao riêng**, thông thường mỗi service dùng queue riêng cùng bind vào exchange; không đặt cả hai service vào một queue rồi mong cả hai nhận mọi message.

### 4.1. Gửi qua `RabbitTemplate`

```java
@Component
public class RabbitOrderPublisher {
    private final RabbitTemplate rabbit;

    public RabbitOrderPublisher(RabbitTemplate rabbit) {
        this.rabbit = rabbit;
    }

    public void send(ExternalEvent event) {
        rabbit.convertAndSend(
                "domain.events",
                "order.paid",
                serialize(event));
    }
}
```

Đây là **mã minh họa**, cần exchange, bindings, message converter, Rabbit connection và các kiểu nghiệp vụ đã định nghĩa.

Không coi `convertAndSend(...)` trả về là bằng chứng message đã đến queue. Với RabbitMQ phải phân biệt:

- **Publisher confirm:** broker xác nhận publish theo publisher confirms configuration.
- **Publisher return:** cho biết message không route được khi bật mandatory/returns đúng cách.
- **Consumer ACK:** container/consumer xác nhận delivery đã xử lý theo policy.
- **Business completion:** ví dụ billing DB đã cập nhật; đây là mốc riêng với producer confirm và consumer ACK.

Queue durable đi cùng chính sách persistent message và broker durability thích hợp; chỉ khai báo queue durable không tự bảo đảm mọi message tồn tại qua broker restart trong mọi cấu hình.

### 4.2. Nhận qua `@RabbitListener`

```java
@Component
public class BillingRabbitListener {

    @RabbitListener(queues = "billing.paid")
    public void handle(String json) {
        ExternalEvent event = decodeAndValidate(json);
        processIdempotently(event);
    }
}
```

Đây là mã minh họa; cần Spring AMQP listener infrastructure, `@EnableRabbit`/Boot auto-configuration, queue declarations và converter.

Lỗi thường gặp:

- Consumer ném exception, container `requeue` ngay liên tục -> **requeue storm**.
- Có nhiều consumers và prefetch cao -> hoàn tất không theo strict FIFO.
- Không có dead-letter exchange/queue -> poison message làm nghẽn.
- Không cấu hình publisher confirms/returns -> không nhận ra thông điệp bị lỗi route.

Có thể dùng retry/backoff, `AmqpRejectAndDontRequeueException`, DLX và consumer ACK policy. Cần kiểm tra chính xác Spring AMQP/container version: requeue mặc định, xử lý exception và retries không nên dựa vào giả định chung.

## 5. JMS: khi hệ thống dùng JMS provider và destination chuẩn

JMS cung cấp khái niệm **queue/topic**, connection/session, acknowledgment và transactions. Spring JMS hỗ trợ sử dụng API mà không phải quản lý toàn bộ resource lifecycle thủ công.

### 5.1. Producer `JmsTemplate`

```java
@Component
public class JmsOrderPublisher {
    private final JmsTemplate jms;

    public JmsOrderPublisher(JmsTemplate jms) {
        this.jms = jms;
    }

    public void send(ExternalEvent event) {
        jms.convertAndSend(
                "billing.paid",
                serialize(event));
    }
}
```

Đây là đoạn minh họa. `JmsTemplate` cần `jakarta.jms.ConnectionFactory`, provider, converter và destination phù hợp. Mặc định `pubSubDomain=false` thường hướng tới **queue**; muốn topic/pub-sub cần thiết lập mode và durable subscription theo yêu cầu.

### 5.2. Consumer `@JmsListener`

```java
@Component
public class BillingJmsListener {

    @JmsListener(destination = "billing.paid")
    public void onMessage(String json) {
        ExternalEvent event = decodeAndValidate(json);
        processIdempotently(event);
    }
}
```

Cần `@EnableJms`, `DefaultJmsListenerContainerFactory` và provider connection. Ví dụ cấu hình (đoạn minh họa, cần import tương ứng):

```java
@Configuration
@EnableJms
public class JmsListenersConfig {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory factory) {

        DefaultJmsListenerContainerFactory result =
                new DefaultJmsListenerContainerFactory();
        result.setConnectionFactory(factory);
        result.setSessionTransacted(true);
        result.setConcurrency("2-6");
        return result;
    }
}
```

`ConnectionFactory` ở đây là `jakarta.jms.ConnectionFactory`. `sessionTransacted(true)` cho phép rollback/commit ở phạm vi JMS session; nếu listener lỗi, redelivery thường được provider/container điều khiển.

**Điểm tin cậy:** `JmsTransactionManager` chỉ quản lý local JMS transaction cho một `ConnectionFactory`. Nó không tự gộp transaction của một DB JDBC khác thành một commit nguyên tử. Nếu thực sự cần distributed transaction thì phải có JTA/XA và provider hỗ trợ; điều đó phức tạp hơn một outbox thông thường và không nên giả định bật `@Transactional` là đủ.

## 6. Event nội bộ và external message có hợp đồng khác nhau

Một record nội bộ:

```java
public record OrderPaid(String orderId, int amountCents) {}
```

không nhất thiết là contract public để gửi qua broker. External envelope có thể là:

```java
public record ExternalEvent<T>(
        String eventId,
        String eventType,
        int schemaVersion,
        String aggregateId,
        long aggregateSequence,
        String correlationId,
        Instant occurredAt,
        T payload) {}
```

Đây là **định nghĩa minh họa**, cần `java.time.Instant`. Mục đích:

| Field | Vì sao cần |
| --- | --- |
| `eventId` | Dedupe khi gửi lại/redelivery, correlation producer ACK |
| `eventType` | Diễn tả business fact, ví dụ `OrderPaid` |
| `schemaVersion` | Version payload/serialization, không phải entity version |
| `aggregateId` | Ordering key/partition key và định danh nghiệp vụ |
| `aggregateSequence` | Thứ tự event của một aggregate khi contract đòi hỏi |
| `correlationId` | Theo dõi một workflow/request xuyên service |
| `occurredAt` | Thời điểm producer ghi nhận event, không tạo total ordering đa máy |
| `payload` | Snapshot bất biến hoặc delta đã kiểm soát dữ liệu |

Một JSON event ngoài ứng dụng minh họa:

```json
{
  "eventId": "evt-42-7",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "aggregateId": "O-42",
  "aggregateSequence": 7,
  "correlationId": "checkout-19",
  "occurredAt": "2026-11-11T00:00:00Z",
  "payload": {
    "orderId": "O-42",
    "amountCents": 125000,
    "currency": "VND"
  }
}
```

Không lấy nguyên entity JPA/Hibernate lazy proxy, `HttpServletRequest`, session hoặc object mutable đang gắn transaction/thread làm payload. DTO nên bất biến, có defensive copy cho nested collections, và chỉ chứa dữ liệu bên ngoài thật sự cần. Dùng Jackson/Avro/Protobuf hoặc serializer phù hợp, không lấy Java `toString()` làm wire format.

**Cần phân biệt:** `schemaVersion` của message khác `aggregateSequence` dành cho ordering. Version entity JPA `@Version` không đương nhiên là event sequence liên tục.

## 7. Bẫy transaction: DB commit không đồng nghĩa broker gửi xong

Ví dụ chống chỉ định nếu đòi hỏi atomically reliable:

```java
@Transactional
public void pay(OrderCommand command) {
    repository.markPaid(command.id());
    kafka.send(
            "orders.events.v1",
            command.id(),
            serializePaid(command));
}
```

Đây là đoạn minh họa với repository, Kafka và serializer do ứng dụng cung cấp.

Những lỗi có thể xảy ra:

1. Broker nhận message, DB về sau rollback -> consumer tưởng order đã paid.
2. DB commit thành công, broker unreachable -> event mất.
3. Producer timeout dù broker thực tế đã lưu -> retry có thể gửi trùng.
4. JVM chết giữa DB commit và publish -> thiếu message.
5. `send()` chỉ submit tác vụ, nhưng service return bình thường -> gọi nhầm là “gửi thành công”.

### 7.1. `@TransactionalEventListener(AFTER_COMMIT)` có đủ không?

Cầu nối đơn giản:

```java
@Component
public class BestEffortBridge {
    private final KafkaTemplate<String, String> kafka;

    public BestEffortBridge(KafkaTemplate<String, String> kafka) {
        this.kafka = kafka;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onPaid(OrderPaid event) {
        kafka.send("orders.events.v1",
                   event.orderId(), serialize(event));
    }
}
```

Đây là đoạn minh họa. Listener chạy sau khi transaction chứa event commit thành công, nếu event được phát **trong transaction đó**. Nó tránh đưa event xuống broker **trước khi DB commit**, nhưng vẫn có cửa sổ process chết ngay sau commit, hoặc broker send thất bại.

Ngoài ra `KafkaTemplate.send` là bất đồng bộ: method `onPaid` có thể return trước khi broker xác nhận. Exception callback hậu commit không tự rollback transaction đã commit. Nếu ứng dụng yêu cầu message không bị mất, đây **không phải guarantee đủ**.

Nếu publish event **ngoài transaction**, `@TransactionalEventListener` mặc định không chạy (`fallbackExecution=false`). Đừng bật `fallbackExecution=true` chỉ để “cho listener chạy” nếu nghiệp vụ thực sự yêu cầu đã commit.

### 7.2. Transactional outbox

Mẫu đáng tin hơn:

```text
BEGIN T1 (database)
  +-- UPDATE business state: OrderPaid
  +-- INSERT outbox(eventId, type, payload, status=NEW)
COMMIT T1
  |
  +-- relay/CDC worker đọc outbox đã commit
        |
        +-- gửi message tới Kafka/RabbitMQ/JMS
        +-- quan sát broker confirmation theo protocol
        +-- đánh dấu SENT hoặc lưu retry state
             |
             +-- consumer nhận, kiểm tra idempotency
```

Outbox row được ghi **cùng transaction** với business state; nếu T1 rollback thì cả hai cùng rollback. Nếu crash sau commit, relay có thể khôi phục từ DB.

Cũng phải nhớ: nếu broker đã nhận nhưng relay chưa kịp đánh dấu `SENT`, relay sẽ có thể gửi lại. Vì vậy outbox hỗ trợ **at-least-once delivery có thể có duplicate**, không tạo exactly-once business effect tự động. Điều kiện xử lý side effect trùng nằm ở consumer.

## 8. Ví dụ Java 17+ chạy được: outbox và fake broker trước khi nối Kafka/RabbitMQ/JMS

Để chứng minh transaction semantics mà **không yêu cầu cài broker thật**, ví dụ console này dùng Spring Framework **6.2.12**, Spring JDBC, H2 và một `FakeBroker` triển khai `BrokerPort`.

Nó kiểm tra:

1. Tạo order A và outbox event A trong **cùng transaction**, commit thành công.
2. Tạo order B rồi ném unchecked exception, khiến **cả order và outbox** rollback.
3. Listener `@TransactionalEventListener(AFTER_COMMIT)` chỉ chạy cho A.
4. Relay gửi A khi fake broker lỗi lần đầu -> outbox A vẫn `NEW`.
5. Retry gửi thành công -> outbox A thành `SENT`.
6. Consumer nhận lại cùng một event hai lần -> side effect in-memory chỉ áp dụng một lần.

**Fake broker không phải Kafka/RabbitMQ/JMS thật.** Chương trình chứng minh business transaction, outbox, retry và dedupe ở mức mô phỏng. Khi nối broker thật phải thay adapter, thêm producer confirms, serialize/deserialize, cấu hình kết nối, và kiểm thử broker integration riêng.

### 8.1. Cấu trúc

```text
external-event-outbox-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ExternalEventsDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'external-event-outbox-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.ExternalEventsDemo'
}
```

### 8.2. `src/main/java/demo/ExternalEventsDemo.java`

```java
package demo;

import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class ExternalEventsDemo {

    public record OrderPaid(String orderId, int amountCents) {}

    public record ExternalMessage(
            String eventId,
            String aggregateId,
            String eventType,
            int schemaVersion,
            String payloadJson) {}

    public interface BrokerPort {
        void send(ExternalMessage event);
    }

    public static class FakeBroker implements BrokerPort {
        private final AtomicBoolean failNext = new AtomicBoolean();
        private final CopyOnWriteArrayList<ExternalMessage> sent =
                new CopyOnWriteArrayList<>();

        public void failNextSend() {
            failNext.set(true);
        }

        @Override
        public void send(ExternalMessage event) {
            if (failNext.getAndSet(false)) {
                throw new IllegalStateException("broker unavailable");
            }
            sent.add(event);
        }

        public List<ExternalMessage> sentMessages() {
            return List.copyOf(sent);
        }
    }

    public static class AfterCommitProbe {
        private final AtomicInteger callbacks = new AtomicInteger();

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void onPaid(OrderPaid event) {
            callbacks.incrementAndGet();
        }

        public int count() {
            return callbacks.get();
        }
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher events;

        public OrderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher events) {
            this.jdbc = jdbc;
            this.events = events;
        }

        @Transactional
        public void pay(String id, int cents, boolean rollback) {
            jdbc.update(
                    "insert into purchase_orders "
                    + "(order_id, amount_cents) values (?, ?)",
                    id, cents);

            // Chỉ ID demo A/B, JSON thủ công KHÔNG dành cho input thật.
            String json = "{\"orderId\":\"" + id
                    + "\",\"amountCents\":" + cents + "}";

            jdbc.update(
                    "insert into outbox_events "
                    + "(event_id, aggregate_id, event_type, "
                    + "schema_version, payload_json, status) "
                    + "values (?, ?, ?, ?, ?, ?)",
                    "evt-" + id, id, "OrderPaid", 1, json, "NEW");

            events.publishEvent(new OrderPaid(id, cents));

            if (rollback) {
                throw new IllegalStateException("rollback requested");
            }
        }
    }

    public static class OutboxRelay {
        private final JdbcTemplate jdbc;
        private final BrokerPort broker;

        public OutboxRelay(JdbcTemplate jdbc, BrokerPort broker) {
            this.jdbc = jdbc;
            this.broker = broker;
        }

        @Transactional
        public void deliverPending() {
            List<ExternalMessage> pending = jdbc.query(
                    "select event_id, aggregate_id, event_type, "
                    + "schema_version, payload_json "
                    + "from outbox_events where status = 'NEW' "
                    + "order by event_id",
                    (rs, rowNum) -> new ExternalMessage(
                            rs.getString("event_id"),
                            rs.getString("aggregate_id"),
                            rs.getString("event_type"),
                            rs.getInt("schema_version"),
                            rs.getString("payload_json")));

            for (ExternalMessage event : pending) {
                // Fake broker xác nhận đồng bộ; broker thật khác.
                broker.send(event);
                jdbc.update(
                        "update outbox_events set status = 'SENT' "
                        + "where event_id = ?",
                        event.eventId());
            }
        }
    }

    public static class DeduplicatingConsumer {
        // Demo RAM-only. Production: unique key ở persistent DB.
        private final Set<String> handled =
                ConcurrentHashMap.newKeySet();
        private final AtomicInteger effects = new AtomicInteger();

        public void consume(ExternalMessage event) {
            if (handled.add(event.eventId())) {
                effects.incrementAndGet();
            }
        }

        public int effects() {
            return effects.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                    "jdbc:h2:mem:external_events;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        FakeBroker fakeBroker() {
            return new FakeBroker();
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        OutboxRelay outboxRelay(
                JdbcTemplate jdbc, BrokerPort broker) {
            return new OutboxRelay(jdbc, broker);
        }

        @Bean
        AfterCommitProbe afterCommitProbe() {
            return new AfterCommitProbe();
        }
    }

    private static int count(JdbcTemplate jdbc, String sql) {
        return jdbc.queryForObject(sql, Integer.class);
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService orders = context.getBean(OrderService.class);
            OutboxRelay relay = context.getBean(OutboxRelay.class);
            FakeBroker broker = context.getBean(FakeBroker.class);
            AfterCommitProbe afterCommit =
                    context.getBean(AfterCommitProbe.class);

            jdbc.execute(
                    "create table purchase_orders ("
                    + "order_id varchar(40) primary key, "
                    + "amount_cents int not null)");
            jdbc.execute(
                    "create table outbox_events ("
                    + "event_id varchar(80) primary key, "
                    + "aggregate_id varchar(40) not null, "
                    + "event_type varchar(80) not null, "
                    + "schema_version int not null, "
                    + "payload_json varchar(1000) not null, "
                    + "status varchar(20) not null)");

            String orderSql =
                    "select count(*) from purchase_orders";
            String pendingSql =
                    "select count(*) from outbox_events "
                    + "where status = 'NEW'";

            orders.pay("A", 1200, false);
            System.out.println("after commit: orders="
                    + count(jdbc, orderSql)
                    + ", pending=" + count(jdbc, pendingSql)
                    + ", callbacks=" + afterCommit.count());

            boolean rolledBack = false;
            try {
                orders.pay("B", 2500, true);
            } catch (IllegalStateException ex) {
                rolledBack = true;
            }
            System.out.println(
                    "transaction B rolled back=" + rolledBack);
            System.out.println("after rollback: orders="
                    + count(jdbc, orderSql)
                    + ", pending=" + count(jdbc, pendingSql)
                    + ", callbacks=" + afterCommit.count());

            broker.failNextSend();
            boolean sendFailed = false;
            try {
                relay.deliverPending();
            } catch (IllegalStateException ex) {
                sendFailed = true;
            }
            System.out.println("first send failed=" + sendFailed
                    + ", pending=" + count(jdbc, pendingSql));

            relay.deliverPending();
            System.out.println("after retry: sent="
                    + broker.sentMessages().size()
                    + ", pending=" + count(jdbc, pendingSql));

            DeduplicatingConsumer consumer =
                    new DeduplicatingConsumer();
            ExternalMessage message =
                    broker.sentMessages().get(0);
            consumer.consume(message);
            consumer.consume(message);

            System.out.println(
                    "consumer side effects after duplicate="
                    + consumer.effects());
        }
    }
}
```

### 8.3. Chạy và quan sát

Với JDK 17+ và Gradle đã cài:

```bash
gradle -q run
```

Các dòng do chương trình chủ động in:

```text
after commit: orders=1, pending=1, callbacks=1
transaction B rolled back=true
after rollback: orders=1, pending=1, callbacks=1
first send failed=true, pending=1
after retry: sent=1, pending=0
consumer side effects after duplicate=1
```

**Giải thích theo transaction:**

- `OrderService.pay` được gọi qua Spring transaction proxy. Với A, `purchase_orders` và `outbox_events` được INSERT trong T1; commit thành công nên `AfterCommitProbe` nhận callback.
- Với B, unchecked exception khiến T2 rollback; không có order/outbox B và không có callback hậu commit B.
- `OutboxRelay` cũng được gọi qua proxy, dùng transaction riêng. Lần đầu `FakeBroker` ném exception nên relay transaction rollback, hàng A còn `NEW`.
- Lần hai broker giả lập nhận event rồi relay cập nhật `SENT`; consumer giả nhận một `eventId` hai lần và chỉ tăng effect một lần.

**Đây không phải bằng chứng kết nối thành công với broker thật**: Java console không có Kafka, RabbitMQ hoặc JMS provider. Những adapter minh họa ở mục sau cần integration tests với broker thật. `FakeBroker` gửi đồng bộ, trong khi các producer API có ACK/future/confirm semantics khác nhau.

## 9. Vì sao relay demo chưa đủ để dùng production?

### 9.1. DB transaction đang mở trong lúc gọi broker

`OutboxRelay.deliverPending()` trong demo dùng một transaction bao toàn bộ đọc/sent/update. Nếu network chậm, DB connection hoặc lock có thể bị giữ lâu. Production thường cần **claim/lease/batch + timeout**, transaction ngắn và cơ chế recovery.

### 9.2. Send OK rồi crash trước `SENT`

Nếu broker đã nhận message, nhưng DB update `SENT` chưa commit, lần sau relay thấy `NEW` và gửi lại. Đây là lý do **consumer idempotency bắt buộc** với outbox at-least-once.

### 9.3. `sent` khác `processed`

Outbox `SENT` chỉ nên mang ý nghĩa **broker đã xác nhận giao message theo contract của adapter**, không phải consumer đã hoàn thành side effect. Muốn biết invoice đã phát hành, cần status/reply event của consumer.

### 9.4. Fake dedupe không sống qua restart

`DeduplicatingConsumer` dùng `Set` trong RAM. Production nên lưu `processed_events(consumer_name,event_id)` với unique constraint trong cùng transaction với cập nhật business DB, hoặc áp dụng idempotency key tại hệ thống ngoài.

### 9.5. Ordering và concurrency

Demo `ORDER BY event_id` chỉ đủ cho một ví dụ nhỏ, **không tạo thứ tự nghiệp vụ**. Nếu nhiều event của cùng aggregate cần áp dụng tuần tự, cấp `aggregateSequence` trong transaction và xử lý relay/consumer theo key, không dùng timestamp hoặc thứ tự từ ID ngẫu nhiên như cơ chế đảm bảo.

## 10. Chuyển `BrokerPort` sang từng công nghệ

Trong project demo:

```java
public interface BrokerPort {
    void send(ExternalMessage message);
}
```

có thể được thay bằng một trong các adapters sau. **Các đoạn dưới đây chỉ minh họa API**, không phải phần của project runnable đã trình bày.

### 10.1. Kafka adapter có chờ kết quả gửi

```java
@Component
public class KafkaBrokerPort implements BrokerPort {
    private final KafkaTemplate<String, String> kafka;

    public KafkaBrokerPort(KafkaTemplate<String, String> kafka) {
        this.kafka = kafka;
    }

    @Override
    public void send(ExternalMessage event) {
        try {
            kafka.send("orders.events.v1",
                    event.aggregateId(),
                    event.payloadJson())
                    .get(10, TimeUnit.SECONDS);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Kafka send interrupted", ex);
        } catch (ExecutionException | TimeoutException ex) {
            throw new IllegalStateException("Kafka send failed", ex);
        }
    }
}
```

Cần imports `KafkaTemplate`, `TimeUnit`, `ExecutionException`, `TimeoutException`, producer configuration và serializers. Chờ future bằng timeout cho biết kết quả gửi theo producer API, **không xử lý được mọi trường hợp ambiguous timeout**: broker có thể đã nhận nhưng client không kịp thấy ACK. Thực tế relay có thể dùng callback async và state machine thay vì chặn thread; phải giữ nguyên recovery semantics.

### 10.2. RabbitMQ adapter

```java
@Component
public class RabbitBrokerPort implements BrokerPort {
    private final RabbitTemplate rabbit;

    public RabbitBrokerPort(RabbitTemplate rabbit) {
        this.rabbit = rabbit;
    }

    @Override
    public void send(ExternalMessage event) {
        rabbit.convertAndSend(
                "domain.events",
                "order.paid",
                event.payloadJson());
    }
}
```

Đoạn này **chưa đủ để mark `SENT` đáng tin cậy**. Production cần quan sát publisher confirm, returned/unroutable message theo topology và settings; có thể gắn `CorrelationData` với `eventId`.

### 10.3. JMS adapter

```java
@Component
public class JmsBrokerPort implements BrokerPort {
    private final JmsTemplate jms;

    public JmsBrokerPort(JmsTemplate jms) {
        this.jms = jms;
    }

    @Override
    public void send(ExternalMessage event) {
        jms.convertAndSend(
                "billing.paid",
                event.payloadJson());
    }
}
```

JMS `ConnectionFactory`, destination, QoS và transaction policy phải được cấu hình rõ. Không đồng nhất một send về `void` với xác nhận consumer đã hoàn thành.

**Đăng ký duy nhất một `BrokerPort`** hoặc dùng `@Qualifier` khi nhiều adapter beans cùng tồn tại. Nếu tạo cả Fake, Kafka, Rabbit, JMS cùng một lúc mà không có qualifier/conditional config, dependency injection có thể mơ hồ.

## 11. Ordering theo `aggregateId`, không phải timestamp

Ví dụ event stream:

```text
Order O-42
  seq=1 OrderCreated
  seq=2 OrderPaid
  seq=3 OrderShipped
```

- Kafka: đặt `aggregateId` làm key; mọi record cùng key cần đi vào cùng partition và được producer gửi theo sequence. Consumer không tự ý áp dụng seq=3 trước seq=2.
- RabbitMQ: queue có thể có nhiều consumers, prefetch và requeue; cần chính sách per-key serialization/version check nếu strict order.
- JMS: kiểm tra semantics session/provider, consumer concurrency và redelivery; không mặc định total order xuyên mọi consumers.
- Outbox relay: hai workers song song đọc outbox có thể gửi E2 trước E1 nếu dùng `SKIP LOCKED` mà không ràng buộc per-key order.

Một consumer cần thứ tự liên tục có thể lưu `lastAppliedSequence` trong DB:

```text
Nếu incoming == last + 1: được áp dụng và cập nhật progress atomically
Nếu incoming <= last: duplicate/cũ, xử lý theo idempotency contract
Nếu incoming > last + 1: gap; defer/retry/alert
```

Đây là pseudocode, **chỉ đúng nếu contract sequence liên tục**. Nếu entity version có khoảng trống do thay đổi không phát event, cần sequence sự kiện riêng hoặc policy cho phép gap.

## 12. Retry, ACK và dead-letter theo từng broker

### Kafka

Có producer future/record metadata, consumer offsets, error handler, backoff và DLT/retry topics. **Commit offset** không chứng minh mọi external side effect đã thành công nếu không có quy tắc transaction/idempotency tương ứng. Retry có thể làm order hoàn tất thay đổi; test per-partition/per-key.

### RabbitMQ

Có publisher confirms/returns, consumer ACK/NACK, requeue, DLX/DLQ. Tránh retry vô hạn tạo requeue storm. Queue rỗng sau ACK không chứng minh hệ thống khác đã xử lý nếu chính consumer ACK quá sớm.

### JMS

Có session acknowledgment modes và transacted sessions; `DefaultMessageListenerContainer` cùng provider quản lý nhận/redelivery. Auto-ack có thể không đủ cho workload quan trọng. DLQ, redelivery delay, max attempts phụ thuộc provider, nên phải test hạ tầng thực tế.

**Tách ba tầng thành công:**

```text
Message đã được producer submit
    -> Broker đã xác nhận lưu/route theo contract
        -> Consumer đã áp dụng side effect và ACK/commit
```

Ba mốc này không tương đương. Cần thêm trạng thái `COMPLETED` hoặc event kết quả nếu nghiệp vụ cần xác nhận từ consumer.

## 13. Mẫu idempotent consumer bền vững

Một cơ chế thường dùng:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong một transaction DB của consumer:

```text
BEGIN
  +-- INSERT (consumer_name, event_id) với unique constraint
  +-- Nếu đã tồn tại: xác định duplicate, tránh side effect trùng
  +-- Nếu mới: cập nhật business state
COMMIT
  +-- ACK/commit offset theo consumer protocol
```

**Không** làm check-then-act rời rạc:

```java
if (!alreadyProcessed(eventId)) {
    chargeCustomer();
    markProcessed(eventId);
}
```

Đây là **phản ví dụ**. Hai workers có thể cùng đọc `false`, hoặc process chết sau `chargeCustomer()` trước `markProcessed()`. Với side effect HTTP, DB unique key nội bộ không tự ngăn lần charge thứ hai nếu remote không có idempotency key. Nên dùng stable operation ID và API remote idempotency khi có.

## 14. Bảo mật và schema evolution

Message broker mở rộng phạm vi lan truyền dữ liệu. Một DTO gửi qua Kafka/RabbitMQ/JMS có thể được lưu nhiều ngày hoặc đi tới nhiều đội/system khác.

- Chỉ công bố trường cần thiết; không chứa password, bearer token, cookie, session, full request object.
- Dùng `eventId`, correlation ID, aggregate ID đã validate; tenant/user ID phải được xác thực/ủy quyền ở ingress.
- Sử dụng TLS, credential rotation, topic/queue ACL, secrets manager theo broker.
- Có retention và quyền xóa/ẩn thông tin cá nhân phù hợp.
- Schema version, backward compatibility và staged rollout phải được test; đổi field `amount` từ cents sang decimal mà giữ nguyên tên/schema là rủi ro nghiêm trọng.
- Không serialize entity Hibernate có lazy associations; map sang immutable external DTO.
- Với dữ liệu lớn (ảnh/file), cân nhắc object storage + object key/checksum thay vì đưa toàn bộ blob vào message.

## 15. Khi nào nên dùng Spring Modulith event externalization?

Nếu kiến trúc là modular monolith chạy với Spring Boot, **Spring Modulith** có Event Publication Registry và event externalization để chuyển một số application events đã chọn ra Kafka/AMQP/JMS, tùy modules, dependencies và cấu hình.

Nhưng Spring Modulith **không phải tính năng mặc định của Spring Framework**. Registry và externalization cần storage/configuration thích hợp; chính sách retry/republish và ordering có thể khác theo phiên bản. Một số kiểu externalization dựa trên async transactional listener không cung cấp mọi guarantee của outbox, vì vậy phải đọc tài liệu phiên bản cụ thể và test crash windows.

Điều cần xác minh khi dùng:

- Sự kiện nào được chọn externalize, routing target/key nào?
- Có publication registry lưu trong transaction gốc không?
- Restart và republish outstanding events làm gì?
- Nếu broker ACK nhưng registry chưa mark complete, consumer chống trùng thế nào?
- Có đảm bảo per-aggregate ordering hay không, nhất là khi replay nhiều rows?

Có thể chọn Spring Modulith để giảm boilerplate, nhưng thiết kế event contract/idempotency vẫn thuộc trách nhiệm ứng dụng.

## 16. Kiểm thử với Kafka, RabbitMQ hoặc JMS thật

**Unit test** mock `KafkaTemplate`, `RabbitTemplate` hay `JmsTemplate` chỉ chứng minh một method được gọi. **Integration test** với `@RecordApplicationEvents` chứng minh event được publish trong Spring context, không chứng minh broker delivery.

Với yêu cầu đáng tin cậy, cần test ở những ranh giới:

| Kịch bản | Điều phải xác minh |
| --- | --- |
| Business transaction rollback | Không có outbox row đã commit |
| Commit, broker unavailable | Outbox pending vẫn còn để retry |
| Broker phục hồi | Relay gửi được message và mark theo ACK contract |
| Broker nhận nhưng relay chết trước mark SENT | Duplicate xảy ra an toàn; consumer idempotent |
| Consumer xử lý rồi chết trước ACK/offset commit | Redelivery không gây side effect trùng |
| Wrong routing key/queue | Rabbit publisher return/monitoring báo không route |
| Sai schema/poison message | Retry có giới hạn, DLQ/quarantine/alert |
| Kafka nhiều consumer groups | Mỗi group nhận theo offset policy riêng |
| Rabbit nhiều queues bind một exchange | Mỗi queue nhận copy; consumers cùng queue chia việc |
| JMS transaction rollback | Redelivery đúng theo provider/container configuration |
| Hai event của cùng aggregate trong nhiều workers | Sequence/gap checking và ordering theo key |
| Restart khi outbox còn NEW | Work được khôi phục từ DB thay vì mất trong RAM |

Có thể dùng Testcontainers để chạy Kafka, RabbitMQ hoặc ActiveMQ Artemis trong integration tests, cộng persistent test database và network failure injection. Tránh chỉ đo `publishEvent` đã trả về; hãy quan sát producer confirmations, broker storage/delivery và side effect consumer.

## 17. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân đáng kiểm tra | Giải pháp |
| --- | --- | --- |
| B nghe `@EventListener` không nhận event của A ở JVM khác | ApplicationEventPublisher không phải remote bus | Bridge sang broker |
| Kafka `send()` gọi nhưng consumer không nhận | Future lỗi, topic/ACL/serializer/group offset | Quan sát send future và consumer configuration |
| Rabbit gửi nhưng queue không thấy | Routing/binding sai, thiếu mandatory returns | Publisher confirms/returns + topology checks |
| JMS listener không chạy | Thiếu `@EnableJms`, container factory, destination/provider | Kiểm tra provider connection và listener |
| DB commit mà broker không có message | In-memory after-commit bridge mất tác vụ | Transactional outbox/publication registry bền vững |
| Message gửi trùng | Timeout, crash sau broker ACK hoặc redelivery | eventId và consumer idempotency |
| Kafka có EOS nhưng email vẫn gửi trùng | Transaction Kafka không bao external HTTP side effect | Idempotency key bên ngoài |
| Message cùng order bị đảo thứ tự | Parallel relay/consumer, retry, partition sai | Per-key ordering, sequence checking |
| Rabbit requeue storm | Poison message và retry không giới hạn | Backoff, max attempts, DLQ |
| JMS rollback không rollback JDBC DB | JMS session transaction không cùng DB | Outbox hoặc JTA/XA được cấu hình thật |
| Outbox status SENT nhưng downstream chưa xong | SENT chỉ phản ánh producer/broker milestone | Consumer result/status riêng |
| Service crash làm event nội bộ mất | Spring Application Events không tự persist | Outbox hoặc durable queue |
| Schema đổi gây deserialization failure | Thiếu backward compatibility | Schema version và compatibility tests |

## 18. Checklist production

**Ranh giới**

- [ ] Đã phân biệt event nội bộ và external message?
- [ ] Chọn Kafka cho stream/replay, RabbitMQ cho routing/work queues, JMS theo provider/enterprise needs với lý do cụ thể?
- [ ] Không kỳ vọng một `@EventListener` ở process khác tự nhận Application Event?

**Reliability**

- [ ] Business DB + outbox ghi chung transaction khi không được phép mất message?
- [ ] Relay đợi đúng broker confirmation trước khi mark `SENT`?
- [ ] Gửi trùng do crash/timeout đã được consumer xử lý idempotently?
- [ ] Có replay/recovery, backoff, DLQ, poison-message policy?
- [ ] Đã phân biệt producer ACK, consumer ACK và business completion?

**Contract & operations**

- [ ] Event ID, aggregate ID, sequence, schema version và correlation ID có ý nghĩa rõ?
- [ ] Đã kiểm tra ordering, keys/partitions, consumer concurrency và gaps?
- [ ] Payload chỉ chứa dữ liệu cần thiết, không leak secrets/PII?
- [ ] Có metrics outbox backlog/age, broker lag, queue depth, failure/retry, oldest event?
- [ ] Có integration tests với broker thật, commit/rollback, crash và duplicate?

**Tóm lại:** `ApplicationEventPublisher` là cơ chế phát sự kiện **trong ứng dụng**. **Kafka, RabbitMQ và JMS** là các lựa chọn messaging khi thông tin phải đi ra ngoài JVM với retention/routing/ack/retry riêng. Chọn công nghệ theo hành vi hệ thống cần, ánh xạ domain event thành external contract ổn định và dùng **outbox + idempotent consumer** khi cần độ tin cậy xuyên transaction, network và crash. Không coi `publishEvent`, `send`, broker confirmation và consumer completion là một mốc duy nhất.

## Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Kafka — Sending Messages với `KafkaTemplate`](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Kafka — `@KafkaListener`](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring AMQP — Sending, Publisher Confirms và Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html)
- [Spring AMQP — Receiving Messages](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages.html)
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html)
- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — `@JmsListener` endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [Spring Modulith — Event Publication Registry và Externalization](https://docs.spring.io/spring-modulith/reference/events.html)

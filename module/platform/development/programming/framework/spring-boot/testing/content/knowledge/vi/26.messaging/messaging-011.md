# Transaction, outbox và quan hệ giữa ghi database với gửi thông điệp

Trong nhóm **Messaging** của module **Spring Boot - testing**, một yêu cầu phổ biến là: *khi tạo đơn hàng thành công trong database, hệ thống phải gửi sự kiện OrderCreated tới RabbitMQ hoặc Kafka*. Tưởng như chỉ cần đặt cả hai lệnh trong `@Transactional` là xong:

```java
@Transactional
public void placeOrder(Order order) {
    orderRepository.save(order);
    rabbitTemplate.convertAndSend(
            "orders.exchange", "orders.created", order);
}
```

Nhưng **đây không phải một transaction nguyên tử giữa database và broker**. `@Transactional` với `DataSourceTransactionManager` chủ yếu điều khiển tài nguyên JDBC. Broker có connection/channel/transaction/ack riêng. Nếu publish thành công rồi database rollback, consumer có thể nhìn thấy một đơn hàng chưa từng commit; nếu database commit rồi publish thất bại, đơn hàng tồn tại nhưng không có sự kiện. Mỗi tình huống đều là **dual-write problem**.

Bài học giải thích ranh giới commit, failure windows, transactional outbox, relay/poller, publisher confirm, retry, idempotent inbox và cách kiểm thử từ unit đến broker integration. Ví dụ thực hành dùng **Java 17+, Spring Boot 3.5, Spring JDBC, H2, RabbitMQ, Testcontainers và JUnit Jupiter**. Điểm cốt lõi không phải có càng nhiều mock càng tốt, mà là test **đúng hợp đồng độ tin cậy**:

- Cùng database transaction: ghi business row **và** outbox row phải **cùng commit hoặc cùng rollback**.
- Sau commit: relay đọc outbox đã commit, publish tới broker, rồi ghi nhận trạng thái published.
- Khi broker tạm không khả dụng: event vẫn ở outbox để retry; không mất vĩnh viễn chỉ vì request đã trả success.
- Khi publish thành công nhưng việc đánh dấu published thất bại: event có thể **được gửi lại**; consumer cần **idempotency** dựa trên `eventId`.
- Khi test: phải phân biệt việc database có outbox row, producer được gọi, broker xác nhận publish, queue nhận message và consumer đã commit side effect. Đó là **năm mức bằng chứng khác nhau**.

Bài gồm source Java có thể biên dịch trong project Spring Boot đã cấu hình, SQL schema, unit tests, Spring JDBC transaction tests, RabbitMQ Testcontainers integration, một demo Java SE với stdout chính xác, checklist lỗi/QA và liên hệ với Kafka/Debezium CDC.

## 1. Ba tài nguyên không tự dùng chung một transaction

Hình dung ứng dụng tạo đơn hàng:

```text
HTTP request
    |
    v
OrderService @Transactional
    |
    +---- JDBC INSERT orders -------[Database transaction]
    |
    +---- RabbitTemplate.send ------[AMQP connection/channel]
    |
    v
HTTP response
```

Spring JDBC transaction thường là một `DataSourceTransactionManager` hoặc `JdbcTransactionManager` quản lý **database connection trên thread hiện tại**. RabbitMQ hoặc Kafka sử dụng **broker protocol**; message không “nằm trong cùng JDBC transaction” chỉ vì nó được gửi bên trong một method có `@Transactional`.

**Cần phân biệt:**

| Hoạt động | Ai điều khiển? | Khi nào có bằng chứng? |
| --- | --- | --- |
| `INSERT orders` | JDBC transaction manager | Database COMMIT thành công |
| `INSERT outbox_events` | **Cùng** JDBC transaction manager | Cùng DB COMMIT với order |
| Publish AMQP | RabbitTemplate/AMQP channel | Broker publisher confirm hoặc lỗi |
| Broker route vào queue | Exchange/binding/queue | Publisher returns/queue observation theo cấu hình |
| Consumer xử lý | Listener container + application | DB side effect/ack/offset observation riêng |

**Publisher confirm ACK không phải consumer ACK.** RabbitMQ xác nhận nó đã xử lý publish tại broker theo publisher-confirm semantics; message vẫn có thể chưa được consumer đọc, handler chưa xử lý và DB của consumer chưa commit. Publisher return còn giúp phát hiện message **không route được** khi bật mandatory và returns.

Với Kafka, broker producer transactions và Spring Kafka transaction synchronization có thể phối hợp với JDBC, nhưng **chúng vẫn không tự tạo ra một distributed atomic commit với JDBC**. Luôn phân tích thứ tự commit và failure window.

## 2. Dual write: các thứ tự đều có cửa sổ mất nhất quán

Hai thứ tự trực tiếp phổ biến:

### Cách A: gửi message trước, commit database sau

```text
BEGIN DB TX
INSERT order
PUBLISH OrderCreated  --> broker chấp nhận
ROLLBACK DB TX (hoặc server crash)
----------------------------------
Consumer nhận event, order không tồn tại.
```

Nếu subscriber cập nhật inventory, gửi email hoặc charge payment vì sự kiện ấy, hệ quả có thể phát sinh dù order chưa tồn tại bền vững.

### Cách B: commit database trước, gửi message sau

```text
BEGIN DB TX
INSERT order
COMMIT DB TX
PROCESS CRASH / network failure
PUBLISH OrderCreated không diễn ra
----------------------------------
Order tồn tại, sự kiện bị bỏ lỡ.
```

Cách B có thể tránh “phantom event” nhưng vẫn tạo **missing event**. Retry HTTP request từ client có thể lại tạo đơn hàng khác nếu không có idempotency key.

### Vì sao “đặt trong @Transactional” không sửa được?

```java
@Transactional
public void placeOrder() {
    jdbc.update("INSERT INTO orders ...");
    rabbitTemplate.convertAndSend(...);
}
```

JDBC commit xảy ra khi Spring transactional interceptor kết thúc method. RabbitTemplate có cơ chế publish riêng. Nếu send thành công, DB commit có thể fail; nếu broker gửi thành công nhưng ack tới producer thất lạc, producer không biết kết quả. Method trả/throw không khẳng định hai tài nguyên đã nhất quán.

### Thử dùng @TransactionalEventListener(AFTER_COMMIT)?

Cách này hữu ích khi event chỉ nên phát **sau DB commit**:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderCreated event) {
    rabbitTemplate.convertAndSend(...);
}
```

Đây là snippet minh họa cần imports và ứng dụng cấu hình listener. Nó **tránh publish trước commit**, nhưng callback chạy **trong process**. Crash ngay sau COMMIT và trước callback, broker unavailable hoặc callback fail vẫn có thể làm mất event. `@Async` còn đưa việc gửi sang thread khác, không làm callback trở nên durable.

**Khi cần bảo đảm có thể phát lại sau crash**, dùng một **bản ghi durable trong cùng database transaction** — transactional outbox — hoặc một kiến trúc có cam kết giao dịch tương đương đã được kiểm chứng.

## 3. Transactional outbox: biến hai lần ghi thành một transaction DB

**Transactional outbox pattern** tách hai bước:

1. **Request transaction:** INSERT business row và INSERT outbox row **trong cùng DB transaction**. Nếu có lỗi, cả hai rollback.
2. **Relay ngoài request transaction:** đọc outbox rows đã commit, publish tới broker, xác nhận khi đủ điều kiện, rồi đánh dấu đã publish. Nếu publish không chắc thành công, giữ row để retry.

```text
Request thread                     Relay worker
--------------                     ------------
BEGIN DB TX
 INSERT orders
 INSERT outbox_events (PENDING)
COMMIT DB TX
   |
   v
Business row + event cùng bền vững
                                  |
                         SELECT pending outbox
                                  |
                         PUBLISH to RabbitMQ
                                  |
                         Wait publisher confirm
                                  |
                         UPDATE state=PUBLISHED
                                  |
                              Consumer
                                  |
                      Deduplicate by eventId
                      Apply side effect + inbox TX
```

**Bảo đảm cốt lõi:** không có trạng thái “order đã commit nhưng không lưu intent phát event” nếu cả hai inserts thật sự dùng **cùng datasource, cùng JDBC transaction, cùng commit**. Điều này không đồng nghĩa broker luôn có ngay event sau khi COMMIT; relay có thể chậm hoặc tạm lỗi.

### Vì sao không DELETE outbox ngay khi publish?

Có thể xóa hoặc đánh dấu sau khi publish, tùy thiết kế. Ví dụ dùng `state=PENDING/PUBLISHED` để dễ quan sát và test. Production cần retention/cleanup vì bảng sẽ tăng mãi. Khi sử dụng **CDC + Debezium outbox Event Router**, quy ước thường là **INSERT-only events**, và việc UPDATE state trên cùng outbox table có thể không phù hợp với SMT default. **Đừng copy sơ đồ polling mutable state này nguyên xi sang Debezium rồi tin nó hoạt động**: chọn cơ chế relay trước và thiết kế schema phù hợp.

## 4. Bảng failure windows của outbox

| Thời điểm lỗi | Business row | Outbox row | Message broker | Hành vi cần có |
| --- | --- | --- | --- | --- |
| Trước COMMIT request | Rollback | Rollback | Chưa gửi | Không phát event |
| COMMIT DB thành công, relay chưa chạy | Tồn tại | PENDING | Chưa có | Relay gửi về sau |
| Relay gặp network lỗi trước publish | Tồn tại | PENDING | Chưa có hoặc không rõ | Retry |
| Broker nhận publish nhưng confirm thất lạc | Tồn tại | PENDING | **Có thể đã nhận** | Retry có thể trùng |
| Broker ACK, process chết trước mark | Tồn tại | PENDING | Đã nhận | Retry → duplicate có thể xảy ra |
| Mark PUBLISHED thành công | Tồn tại | PUBLISHED | Broker đã confirm/route theo policy | Không gửi lại trừ thao tác khôi phục |
| Consumer ghi DB rồi chết trước ACK | Tồn tại | PUBLISHED | Có thể redeliver | Consumer idempotent |
| Consumer handler fail | Tồn tại | PUBLISHED | Retry/DLQ tùy config | Không lặp side effect sai |

Bảng này là **mô hình trạng thái**, không phải bảo đảm rằng mọi broker hỗ trợ exactly-once. Với polling relay gửi theo kiểu at-least-once và consumer có thể nhận trùng, mục tiêu thực tế là **at-least-once delivery + idempotent effect**.

**Không thể tránh hoàn toàn duplicate chỉ bằng “gửi rồi mark”**: luôn có khoảng giữa hai hành động độc lập. Nếu đánh dấu trước khi publish, crash sau mark sẽ gây **mất message**; vì vậy lựa chọn phổ biến là chấp nhận duplicate, rồi deduplicate phía consumer.

## 5. Thiết kế event envelope và outbox row

Một event đủ thông tin nên có:

- `eventId`: định danh **duy nhất cho mỗi sự kiện**, dùng dedup/inbox, tracing, correlation.
- `aggregateId`: định danh order/customer của sự kiện; khi dùng Kafka có thể dùng làm partition key để bảo vệ ordering theo aggregate.
- `eventType`: ví dụ `order.created`.
- `schemaVersion`: version payload cho producer/consumer evolution.
- `payload`: dữ liệu cần thiết (tránh PII/secrets không cần).
- `createdAt`: thời điểm tạo event trong database; không phải một ordering key đủ mạnh trong mọi trường hợp.
- `state`, `attempts`, `publishedAt`: dành cho **polling relay**, không phải mọi CDC schema.

Ví dụ payload:

```json
{
  "eventId": "evt-101",
  "orderId": "ORD-101",
  "quantity": 2,
  "schemaVersion": 1
}
```

Trong mã runnable, `ObjectMapper` serialize Java record thành JSON. Message được gắn thêm AMQP header `eventId` để consumer không cần dựa vào body parsing chỉ để lấy dedup key.

**Không nhầm:**

- Một aggregate có thể phát nhiều events → mỗi event phải có eventId riêng.
- HTTP request retry cùng idempotency key không được tạo nhiều orders/events ngoài ý muốn.
- Ordering theo `created_at` có thể trùng timestamp hoặc khác thứ tự commit; nếu nghiệp vụ cần ordering nghiêm ngặt theo aggregate, nên thiết kế `aggregateVersion`/sequence và serialization/partition key thích hợp.
- Một event có thể được publish nhiều lần nhưng vẫn là **cùng eventId**, vì đó là retry của cùng logical event.
- Một request tạo nhiều business rows/events phải cùng transaction nếu chúng thuộc cùng atomic business operation.

## 6. Kế hoạch kiểm thử trước khi viết Java

| Cấp test | Chủ đích | Có broker? | Assertion quan trọng |
| --- | --- | --- | --- |
| Java unit | Validate dữ liệu, tạo event/payload | Không | Đúng mapping, ID và boundary |
| JDBC transaction integration | `orders` + `outbox_events` atomic | Không | Success: cả hai có; failure: cả hai rollback |
| Relay unit | Retry/failure/mark behavior | Mock publisher | Publish fail → vẫn PENDING; thành công → mark |
| Rabbit broker integration | RabbitTemplate → exchange → queue | **RabbitMQ thật** | Confirm, routing, body, eventId header |
| Consumer idempotency integration | Duplicate same eventId | DB + broker/handler thật | Business effect chỉ một lần |
| E2E | Request → DB → outbox → broker → consumer DB | DB/broker thật | Contract end-to-end và cleanup |

**Một test xanh chỉ có Mockito.verify(rabbitTemplate).convertAndSend(...) không chứng minh message đã đến broker.** Ngược lại, một test đọc được message trong RabbitMQ queue không chứng minh consumer đã commit business side effect.

Bài thực hành cung cấp đầy đủ các tầng **DB atomicity, relay unit và broker integration**. Phần inbox/idempotent consumer được trình bày như một pattern test riêng với SQL và lưu ý đúng engine; không tuyên bố nó đã được kiểm chứng bởi bộ publisher tests.

## 7. Project Spring Boot 3.5 / Java 17

Mẫu project dùng Spring JDBC và RabbitMQ; H2 chỉ trên test classpath.

```text
src/
├── main/
│   ├── java/example/outbox/
│   │   ├── OutboxApplication.java
│   │   ├── OrderCreatedEvent.java
│   │   ├── OutboxEvent.java
│   │   ├── OrderStore.java
│   │   ├── OutboxStore.java
│   │   ├── OrderCommandService.java
│   │   ├── EventPublisher.java
│   │   ├── OutboxTopology.java
│   │   ├── RabbitOutboxPublisher.java
│   │   ├── OutboxRelay.java
│   │   ├── OutboxPollingJob.java
│   │   └── OutboxCrashModel.java
│   └── resources/application.properties
└── test/
    ├── resources/schema.sql
    └── java/example/outbox/
        ├── AtomicOutboxTest.java
        ├── OutboxRelayUnitTest.java
        ├── RabbitOutboxIntegrationTest.java
        └── OutboxCrashModelTest.java
```

Không có HTTP controller trong ví dụ để tập trung vào **transaction + outbox + broker**. Một web/controller layer có thể gọi `OrderCommandService.create(...)` rồi trả 201 sau DB commit, nhưng không nên đợi consumer hoàn tất trong cùng request trừ khi contract đòi hỏi.

### 7.1. Gradle dependencies

Trong một project Gradle đã có Spring Boot plugin, Java toolchain 17+, repositories và dependency management/BOM cho **Spring Boot 3.5.x**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
    implementation 'org.springframework.boot:spring-boot-starter-json'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:rabbitmq'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **phần dependency và test task**, không phải build file độc lập. Version của Spring AMQP/Jackson/Testcontainers do Boot 3.5 BOM quyết định. Testcontainers **2.x** có thể thay group/artifact/package của module RabbitMQ; ví dụ nhắm **Testcontainers 1.x** để imports nhất quán.

Khi chạy ứng dụng ở ngoài test, phải cấu hình database thật, migrations, RabbitMQ host/credentials và polling schedule. `com.h2database:h2` ở `testRuntimeOnly` **không** cung cấp datasource production. Không đưa secret sản xuất vào test fixtures.

### 7.2. OutboxApplication.java

Tạo `src/main/java/example/outbox/OutboxApplication.java`:

```java
package example.outbox;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class OutboxApplication {
    public static void main(String[] args) {
        SpringApplication.run(OutboxApplication.class, args);
    }
}
```

`@EnableScheduling` cho phép một polling job tự chạy khi được bật bằng property. Trong các tests bài này, polling job mặc định **tắt** để assertions không tranh race với scheduler.

### 7.3. application.properties

Tạo `src/main/resources/application.properties`:

```properties
# Correlated publisher confirms + detect unroutable messages.
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true

# Explicitly enable the polling job only where desired.
app.outbox.polling.enabled=false
```

Các properties đầu là cần thiết để `RabbitOutboxPublisher` dùng `CorrelationData.getFuture()` và `getReturn()` một cách có ý nghĩa.

- **Publisher confirm:** broker trả ACK/NACK cho publish.
- **Publisher return + mandatory:** broker báo message không được route vào queue theo rule phù hợp. Broker ACK **vẫn có thể true cho message không route được**, vì vậy không chỉ xét `confirm.isAck()`.
- **Polling disabled mặc định:** test/manual demo tự gọi `relay.flushOnce()`. Trong ứng dụng production, hãy bật `app.outbox.polling.enabled=true` sau khi đã cấu hình database, broker, monitoring, claim/locking và retries phù hợp.

**Không đồng nhất broker confirm với consumer completion.** Đây chỉ là một bước đủ điều kiện đánh dấu published trong relay, tùy delivery policy của hệ thống.

## 8. SQL schema: business và outbox cùng một database

Tạo `src/test/resources/schema.sql` (H2 2.x):

```sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    quantity INTEGER NOT NULL
        CHECK (quantity BETWEEN 1 AND 100)
);

CREATE TABLE outbox_events (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload VARCHAR(2000) NOT NULL,
    state VARCHAR(16) NOT NULL DEFAULT 'PENDING'
        CHECK (state IN ('PENDING', 'PUBLISHED')),
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP,
    CONSTRAINT fk_outbox_order FOREIGN KEY (aggregate_id)
        REFERENCES orders(order_id)
);

CREATE INDEX idx_outbox_pending
    ON outbox_events(state, created_at);
```

**Những đặc tính cần lưu ý:**

- `orders.order_id` là business primary key của ví dụ.
- `outbox_events.event_id` là unique event key. Đừng sử dụng một ID mới cho mỗi retry của **cùng event**.
- FK bảo vệ việc outbox tham chiếu order có thật; trong một transaction, INSERT order trước rồi INSERT outbox là hợp lệ.
- `state=PENDING/PUBLISHED` là trạng thái của **polling relay**, không phải trạng thái consumer đã xử lý.
- `attempts` tăng khi relay gặp lỗi/không chắc chắn; cần metric/alert và giới hạn retry thực tế.
- `published_at` dùng để theo dõi vận hành, không chứng minh mọi consumer đã nhận.
- H2 `VARCHAR`/timestamp/index có thể khác production PostgreSQL; integration test database production cần migration và dialect đúng.
- Schema không chứa các cột lease/owner/claim. **Relay mẫu chỉ an toàn khi có một worker**, chưa được thiết kế multi-instance processing. Sẽ phân tích ở mục production hardening.

Với database thật, nên quản lý schema bằng Flyway/Liquibase; test schema đơn giản ở đây phục vụ minh họa transaction atomicity. Không chạy đồng thời `schema.sql` và migrations cùng tạo bảng.

## 9. Domain event: OrderCreatedEvent.java

Tạo `src/main/java/example/outbox/OrderCreatedEvent.java`:

```java
package example.outbox;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        int quantity,
        int schemaVersion) {
}
```

Record là payload được serialize thành JSON trong `OrderCommandService`. Nó **không** tự mang RabbitMQ delivery tag, correlation data hoặc transaction state. `eventId` dùng cho deduplication, `orderId` giúp consumer biết aggregate và `schemaVersion` hỗ trợ compatibility.

Tạo `src/main/java/example/outbox/OutboxEvent.java`:

```java
package example.outbox;

public record OutboxEvent(
        String eventId,
        String aggregateId,
        String eventType,
        String payload,
        int attempts) {
}
```

Đây là row model dành cho relay, không phải entity JPA. Nó chứa đúng những trường cần publish; trạng thái PENDING được dùng trong câu SELECT chứ không cần đưa vào record.

## 10. OrderStore: chỉ làm việc với JDBC

Tạo `src/main/java/example/outbox/OrderStore.java`:

```java
package example.outbox;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {
    private final JdbcTemplate jdbc;

    public OrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String orderId, int quantity) {
        jdbc.update("""
                INSERT INTO orders(order_id, quantity)
                VALUES (?, ?)
                """, orderId, quantity);
    }

    public int countById(String orderId) {
        Integer result = jdbc.queryForObject("""
                SELECT COUNT(*) FROM orders
                WHERE order_id = ?
                """, Integer.class, orderId);
        return result == null ? 0 : result;
    }
}
```

Store **không tự mở transaction riêng**. `JdbcTemplate` sử dụng connection đang được Spring transaction manager liên kết với thread; nhờ vậy INSERT order và INSERT outbox trong service có thể cùng commit/rollback.

**Tránh dùng `new JdbcTemplate(customDataSource)` của một datasource khác ở OutboxStore**. Nếu mỗi store dùng một database/transaction manager khác, bạn không còn atomicity chỉ nhờ annotation `@Transactional`.

## 11. OutboxStore: insert, pending, mark và record failure

Tạo `src/main/java/example/outbox/OutboxStore.java`:

```java
package example.outbox;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OutboxStore {
    private final JdbcTemplate jdbc;

    public OutboxStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(OutboxEvent event) {
        jdbc.update("""
                INSERT INTO outbox_events
                    (event_id, aggregate_id,
                     event_type, payload)
                VALUES (?, ?, ?, ?)
                """,
                event.eventId(),
                event.aggregateId(),
                event.eventType(),
                event.payload());
    }

    public List<OutboxEvent> findPending(int limit) {
        return jdbc.query("""
                SELECT event_id, aggregate_id,
                       event_type, payload, attempts
                FROM outbox_events
                WHERE state = 'PENDING'
                ORDER BY created_at, event_id
                LIMIT ?
                """,
                (rs, rowNumber) -> new OutboxEvent(
                        rs.getString("event_id"),
                        rs.getString("aggregate_id"),
                        rs.getString("event_type"),
                        rs.getString("payload"),
                        rs.getInt("attempts")),
                limit);
    }

    public void markPublished(String eventId) {
        int updated = jdbc.update("""
                UPDATE outbox_events
                SET state = 'PUBLISHED',
                    published_at = CURRENT_TIMESTAMP
                WHERE event_id = ?
                  AND state = 'PENDING'
                """, eventId);

        if (updated != 1) {
            throw new IllegalStateException(
                    "outbox state transition failed");
        }
    }

    public void recordFailure(String eventId) {
        jdbc.update("""
                UPDATE outbox_events
                SET attempts = attempts + 1
                WHERE event_id = ?
                  AND state = 'PENDING'
                """, eventId);
    }

    public String stateOf(String eventId) {
        return jdbc.queryForObject("""
                SELECT state FROM outbox_events
                WHERE event_id = ?
                """, String.class, eventId);
    }

    public int countByEventId(String eventId) {
        Integer count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM outbox_events
                WHERE event_id = ?
                """, Integer.class, eventId);
        return count == null ? 0 : count;
    }
}
```

**Các lưu ý về semantics:**

- `insert(...)` tham gia transaction do service mở; SQL chỉ thêm event khi business operation thành công.
- `findPending(limit)` là **polling query đơn giản, không claim/lock rows**. Hai relay instances có thể cùng đọc một PENDING event và publish trùng; mẫu này cố ý dành cho **một worker**.
- `markPublished(...)` chỉ chạy **sau khi publisher báo điều kiện gửi thành công**. Nếu nó fail, retry có thể phát trùng; điều đó phải được consumer chịu đựng.
- `recordFailure(...)` tăng attempts nhưng không tự áp retry backoff, jitter hoặc max attempts. Mục vận hành sẽ nêu cách bổ sung.
- `created_at` hỗ trợ ordering gần đúng, không thay thế aggregate sequence khi đòi hỏi ordering nghiêm ngặt theo từng order.

Đừng đặt cả `findPending → network publish → markPublished` trong một JDBC transaction mở kéo dài qua network call; như vậy giữ row locks/connections lâu và vẫn **không** làm publish trở nên atomic với DB.

## 12. OrderCommandService: atomic insert order + outbox

Tạo `src/main/java/example/outbox/OrderCommandService.java`:

```java
package example.outbox;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCommandService {
    private final OrderStore orders;
    private final OutboxStore outbox;
    private final ObjectMapper mapper;

    public OrderCommandService(
            OrderStore orders,
            OutboxStore outbox,
            ObjectMapper mapper) {
        this.orders = orders;
        this.outbox = outbox;
        this.mapper = mapper;
    }

    @Transactional
    public void create(
            String orderId, int quantity, String eventId) {
        if (orderId == null || orderId.isBlank()
                || eventId == null || eventId.isBlank()
                || quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "invalid order command");
        }

        OrderCreatedEvent event =
                new OrderCreatedEvent(
                        eventId, orderId, quantity, 1);

        final String payload;
        try {
            payload = mapper.writeValueAsString(event);
        } catch (JsonProcessingException error) {
            throw new IllegalStateException(
                    "cannot serialize order event",
                    error);
        }

        orders.insert(orderId, quantity);
        outbox.insert(new OutboxEvent(
                eventId, orderId,
                "order.created", payload, 0));
    }
}
```

**Đây là trọng tâm của transactional outbox.** Khi method được gọi thông qua Spring-managed service proxy, `@Transactional` mở transaction ở JDBC datasource. Cả hai stores sử dụng **cùng JdbcTemplate/DB connection infrastructure**:

```text
BEGIN
  INSERT orders
  INSERT outbox_events
COMMIT
```

Nếu `outbox.insert(...)` thất bại vì `event_id` duplicate, Spring JDBC ném unchecked `DataIntegrityViolationException`/`DuplicateKeyException`; mặc định Spring transaction rollback **cả INSERT order trước đó**. Vì vậy một test cần tạo tình huống outbox fail sau khi order insert, rồi kiểm tra order mới **không tồn tại**.

**Tại sao serialize trước khi INSERT?** Nếu serialization fail, chưa có JDBC write; nếu có write trước rồi serialize fail, exception runtime cũng rollback đúng khi transaction hoạt động. Cách này giúp code rõ ràng, nhưng bảo đảm atomicity vẫn đến từ **cùng database transaction**.

**Tại sao không gửi RabbitTemplate ở đây?** Khi method request kết thúc, DB đã lưu **ý định phát sự kiện** bền vững. Relay phát sau; lỗi broker không khiến request tạo order bị rollback vô nghĩa hoặc tạo dual-write gap.

**Giới hạn khác:** nếu client retry request sau timeout, `orders.order_id` và eventId cần một cơ chế idempotency nghiệp vụ ổn định. Ví dụ bắt `DuplicateKeyException` và trả conflict; hệ thống production có thể chọn trả kết quả đã tạo cho cùng request idempotency key.

## 13. EventPublisher port, RabbitMQ topology và publisher confirms

### 13.1. EventPublisher.java

Tạo `src/main/java/example/outbox/EventPublisher.java`:

```java
package example.outbox;

public interface EventPublisher {
    void publish(OutboxEvent event);
}
```

Port này giúp **unit test relay mà không cần broker**. Test mock `EventPublisher` có thể mô phỏng success, network failure và ambiguous publish, nhưng không chứng minh exchange/routing thật. Broker integration test sẽ dùng implementation Spring AMQP.

### 13.2. OutboxTopology.java

Tạo `src/main/java/example/outbox/OutboxTopology.java`:

```java
package example.outbox;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OutboxTopology {
    public static final String EXCHANGE =
            "lesson.outbox.exchange";
    public static final String ROUTING_KEY =
            "lesson.order.created";
    public static final String QUEUE =
            "lesson.order.events";

    @Bean
    DirectExchange outboxExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue outboxQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding outboxBinding(
            @Qualifier("outboxQueue") Queue queue,
            @Qualifier("outboxExchange")
                    DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange)
                .with(ROUTING_KEY);
    }
}
```

Spring AMQP `RabbitAdmin` có thể khai báo các beans exchange/queue/binding trên broker khi connection hình thành, với auto-declare behavior mặc định phù hợp. Integration test kết nối qua Testcontainers và đọc chính queue này để xác minh routing.

**Không phải ứng dụng nào cũng có quyền tự khai báo topology production.** Nếu dùng RabbitMQ operator/IaC, kiểm tra các names/arguments/bindings tương thích; đừng dựa vào test tự tạo queue khác production.

### 13.3. RabbitOutboxPublisher.java

Tạo `src/main/java/example/outbox/RabbitOutboxPublisher.java`:

```java
package example.outbox;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class RabbitOutboxPublisher
        implements EventPublisher {

    private final RabbitTemplate template;

    public RabbitOutboxPublisher(
            RabbitTemplate template) {
        this.template = template;
    }

    @Override
    public void publish(OutboxEvent event) {
        CorrelationData correlation =
                new CorrelationData(event.eventId());

        template.convertAndSend(
                OutboxTopology.EXCHANGE,
                OutboxTopology.ROUTING_KEY,
                event.payload(),
                message -> {
                    MessageProperties properties =
                            message.getMessageProperties();

                    properties.setMessageId(event.eventId());
                    properties.setHeader(
                            "eventId", event.eventId());
                    properties.setHeader(
                            "eventType", event.eventType());
                    properties.setContentType(
                            MessageProperties.CONTENT_TYPE_JSON);
                    return message;
                },
                correlation);

        try {
            CorrelationData.Confirm confirm =
                    correlation.getFuture().get(
                            5, TimeUnit.SECONDS);

            if (!confirm.isAck()
                    || correlation.getReturn() != null) {
                throw new IllegalStateException(
                        "broker did not confirm routed publish");
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "publisher interrupted", error);
        } catch (ExecutionException
                 | TimeoutException error) {
            throw new IllegalStateException(
                    "publisher confirm unavailable", error);
        }
    }
}
```

**Ba tầng cần phân biệt:**

1. `RabbitTemplate.convertAndSend(...)` viết message vào AMQP channel; chỉ việc method return **chưa** chứng minh broker đã xử lý publish.
2. `CorrelationData.getFuture().get(...)` chờ publisher confirmation. `confirm.isAck()` cho biết broker ACK publish; `false` có thể kèm reason.
3. `correlation.getReturn()` khác null nghĩa message bị **return do không route** khi bật returns/mandatory. Broker vẫn có thể ACK publish tới exchange nhưng không có queue nhận được; **phải xét cả confirm lẫn return** nếu hợp đồng cần routing.

**Khai báo `spring.rabbitmq.publisher-confirm-type=correlated`, `publisher-returns=true` và `template.mandatory=true` là bắt buộc cho semantics ví dụ.** Nếu một property bị tắt, `getFuture()` có thể không hoàn tất hoặc `getReturn()` không cho biết unroutable message như mong đợi.

**Tại sao timeout phải coi là trạng thái chưa chắc chắn?** Producer có thể không nhận ACK vì network lỗi mặc dù broker đã nhận. Relay giữ event PENDING và retry; consumer cần dedup eventId. Đừng “sửa” timeout bằng cách đánh dấu PUBLISHED để không bị gửi trùng — có thể gây mất event.

**Giới hạn bảo đảm:** publisher confirm/return không chứng minh consumer đã xử lý hoặc commit. RabbitMQ durability, persistent messages, quorum queue và restart tests cần cấu hình/assertions riêng nếu đó là contract.

## 14. OutboxRelay: publish trước, mark sau

Tạo `src/main/java/example/outbox/OutboxRelay.java`:

```java
package example.outbox;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OutboxRelay {
    private static final Logger log =
            LoggerFactory.getLogger(OutboxRelay.class);

    private final OutboxStore outbox;
    private final EventPublisher publisher;

    public OutboxRelay(
            OutboxStore outbox,
            EventPublisher publisher) {
        this.outbox = outbox;
        this.publisher = publisher;
    }

    public int flushOnce() {
        int published = 0;

        for (OutboxEvent event :
                outbox.findPending(50)) {
            try {
                publisher.publish(event);
                outbox.markPublished(event.eventId());
                published++;
            } catch (RuntimeException error) {
                outbox.recordFailure(event.eventId());

                log.warn(
                        "Outbox publish pending for eventId={}",
                        event.eventId());
            }
        }

        return published;
    }
}
```

**Mã có chủ ý đơn giản, dành cho một relay worker:**

- Không có `@Transactional` bao trùm cả network publish và DB state update.
- `findPending(50)` đọc một batch nhỏ để tránh lấy toàn bảng.
- Publisher báo điều kiện confirm/return thành công → `markPublished`.
- Publisher lỗi/unknown → giữ PENDING, tăng attempts, log **eventId** chứ không log raw payload/credentials, rồi retry ở lần sau.
- Một lỗi markPublished sau publish cũng có thể dẫn tới lần gửi lại; consumer phải idempotent.
- `flushOnce()` trả số row được mark PUBLISHED trong lượt này, **không** phải số consumer đã xử lý.

**Không sử dụng nguyên trạng làm production multi-instance relay.** Hai instances có thể cùng đọc một PENDING row, publish trùng, và một instance thất bại khi mark. Muốn scale an toàn, bổ sung lease/claim/ownership và locking/ack semantics ở database phù hợp; vẫn phải chấp nhận duplicate khi crash giữa publish và mark.

### 14.1. Polling job chỉ bật có chủ đích

Tạo `src/main/java/example/outbox/OutboxPollingJob.java`:

```java
package example.outbox;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        name = "app.outbox.polling.enabled",
        havingValue = "true")
public class OutboxPollingJob {
    private final OutboxRelay relay;

    public OutboxPollingJob(OutboxRelay relay) {
        this.relay = relay;
    }

    @Scheduled(fixedDelay = 1000)
    public void publishPending() {
        relay.flushOnce();
    }
}
```

Trong bộ test, property `app.outbox.polling.enabled=false` nên relay chỉ chạy khi test **gọi tường minh**. Nếu scheduler tự chạy đồng thời với test, kết quả pending/published có thể thay đổi trước assertions, khiến tests flaky.

Production có thể cấu hình poll interval, backoff, batch size, metrics, shutdown và graceful drain. `fixedDelay=1000` ở đây chỉ mô tả cơ chế, không phải một SLO được khuyến nghị cho mọi tải.

## 15. Test atomicity của order + outbox (không cần broker)

Tạo `src/test/java/example/outbox/AtomicOutboxTest.java`:

```java
package example.outbox;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE,
        properties =
                "app.outbox.polling.enabled=false")
class AtomicOutboxTest {

    @Autowired
    private OrderCommandService command;

    @Autowired
    private OrderStore orders;

    @Autowired
    private OutboxStore outbox;

    @Autowired
    private JdbcTemplate jdbc;

    private final List<String> createdOrders =
            new ArrayList<>();

    private String orderId() {
        String value = "ORD-" + UUID.randomUUID();
        createdOrders.add(value);
        return value;
    }

    private static String eventId() {
        return "evt-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanupCommittedRows() {
        for (String id : createdOrders) {
            jdbc.update("""
                    DELETE FROM outbox_events
                    WHERE aggregate_id = ?
                    """, id);
            jdbc.update("""
                    DELETE FROM orders
                    WHERE order_id = ?
                    """, id);
        }
    }

    @Test
    void orderAndOutboxCommitTogether() {
        String order = orderId();
        String event = eventId();

        command.create(order, 2, event);

        assertEquals(1, orders.countById(order));
        assertEquals(1, outbox.countByEventId(event));
        assertEquals("PENDING", outbox.stateOf(event));

        String payload = jdbc.queryForObject("""
                SELECT payload FROM outbox_events
                WHERE event_id = ?
                """, String.class, event);

        assertTrue(payload.contains(order));
        assertTrue(payload.contains(event));
    }

    @Test
    void outboxUniqueFailureRollsBackPriorOrderInsert() {
        String first = orderId();
        String second = orderId();
        String duplicateEventId = eventId();

        command.create(first, 1, duplicateEventId);

        assertThrows(
                DataIntegrityViolationException.class,
                () -> command.create(
                        second, 3, duplicateEventId));

        assertEquals(1, orders.countById(first));
        assertEquals(0, orders.countById(second));
        assertEquals(
                1,
                outbox.countByEventId(duplicateEventId));
    }

    @Test
    void invalidQuantityDoesNotWriteEitherTable() {
        String order = orderId();
        String event = eventId();

        assertThrows(
                IllegalArgumentException.class,
                () -> command.create(order, 0, event));

        assertEquals(0, orders.countById(order));
        assertEquals(0, outbox.countByEventId(event));
    }
}
```

**Ba JUnit integration methods** kiểm tra database atomicity mà **không kết nối tới RabbitMQ**:

1. **Success:** sau khi method `command.create` trả về và service transaction commit, cả `orders` và `outbox_events` cùng có row; state vẫn PENDING vì relay chưa chạy.
2. **Outbox failure sau INSERT order:** cố ý dùng trùng eventId; DB unique constraint reject INSERT outbox; Spring rollback transaction thứ hai. Không được còn row order thứ hai — đây là assertion quan trọng nhất để bảo vệ tính atomic.
3. **Input invalid:** service từ chối trước khi tạo row.

**Tại sao test class không có `@Transactional`?** Nếu đặt `@Transactional` lên chính JUnit test, cả lệnh `command.create(...)` mặc định `REQUIRED` có thể join transaction do TestContext mở và chưa commit khi assertion chạy. Test kiểm tra atomic rollback **sau service commit thực** nên ví dụ không dùng test-managed transaction; nó cleanup bằng `@AfterEach` trên một database **chỉ dành cho test**.

**Lưu ý:** các test này không gọi `OutboxRelay.flushOnce()` và cũng không chứng minh message đã được broker nhận. Chúng chứng minh **transaction boundary phía DB**.

## 16. Unit test relay bằng Mockito: retry và mark behavior

Tạo `src/test/java/example/outbox/OutboxRelayUnitTest.java`:

```java
package example.outbox;

import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class OutboxRelayUnitTest {

    private static OutboxEvent sample() {
        return new OutboxEvent(
                "evt-1", "ORD-1", "order.created",
                "{\"eventId\":\"evt-1\"}", 0);
    }

    @Test
    void successfulPublishMarksEventPublished() {
        OutboxStore store = mock(OutboxStore.class);
        EventPublisher publisher =
                mock(EventPublisher.class);
        OutboxEvent event = sample();

        when(store.findPending(50))
                .thenReturn(List.of(event));

        OutboxRelay relay =
                new OutboxRelay(store, publisher);

        assertEquals(1, relay.flushOnce());

        verify(publisher).publish(event);
        verify(store).markPublished(event.eventId());
    }

    @Test
    void publisherFailureDoesNotMarkPublished() {
        OutboxStore store = mock(OutboxStore.class);
        EventPublisher publisher =
                mock(EventPublisher.class);
        OutboxEvent event = sample();

        when(store.findPending(50))
                .thenReturn(List.of(event));
        doThrow(new IllegalStateException(
                "broker unavailable"))
                .when(publisher).publish(event);

        OutboxRelay relay =
                new OutboxRelay(store, publisher);

        assertEquals(0, relay.flushOnce());

        verify(store).recordFailure(event.eventId());
        verify(publisher).publish(event);
        // Không có markPublished nào:
        verify(store, times(0))
                .markPublished(event.eventId());
    }

    @Test
    void retryMayPublishSameEventIdAgain() {
        OutboxStore store = mock(OutboxStore.class);
        EventPublisher publisher =
                mock(EventPublisher.class);
        OutboxEvent event = sample();

        when(store.findPending(50))
                .thenReturn(List.of(event));

        doThrow(new IllegalStateException(
                "confirm lost"))
                .doNothing()
                .when(publisher).publish(event);

        OutboxRelay relay =
                new OutboxRelay(store, publisher);

        assertEquals(0, relay.flushOnce());
        assertEquals(1, relay.flushOnce());

        verify(publisher, times(2)).publish(event);
        verify(store).recordFailure(event.eventId());
        verify(store).markPublished(event.eventId());
    }

    @Test
    void emptyOutboxDoesNotCallPublisher() {
        OutboxStore store = mock(OutboxStore.class);
        EventPublisher publisher =
                mock(EventPublisher.class);

        when(store.findPending(50))
                .thenReturn(List.of());

        OutboxRelay relay =
                new OutboxRelay(store, publisher);

        assertEquals(0, relay.flushOnce());
        verifyNoInteractions(publisher);
    }
}
```

**Bốn unit methods** chạy không cần Spring context, H2 hay RabbitMQ. Chúng chứng minh relay gọi đúng gateway, xử lý retry, không mark khi publisher lỗi và có thể gọi publish cùng eventId hai lần.

**Điều chúng không chứng minh:** Mockito mock không mở AMQP connection, không kiểm tra publisher confirm thật, topology hoặc DB update thật. Chính vì vậy cần test ở mục tiếp theo.

**Một chi tiết:** test gọi retry liên tiếp với `findPending(50)` mock luôn trả cùng event — nó **mô phỏng** event còn PENDING. Nó không phải DB test chứng minh query đã lọc state chính xác; các test JDBC/integration kiểm tra phần lưu trữ.

## 17. RabbitMQ Testcontainers: publish/confirm/routing thực

Tạo `src/test/java/example/outbox/RabbitOutboxIntegrationTest.java`:

```java
package example.outbox;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE,
        properties =
                "app.outbox.polling.enabled=false")
class RabbitOutboxIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer(
                    DockerImageName.parse(
                            "rabbitmq:4.1-management-alpine"));

    @Autowired
    private OrderCommandService command;

    @Autowired
    private OutboxRelay relay;

    @Autowired
    private OutboxStore outbox;

    @Autowired
    private RabbitTemplate rabbitTemplate;

    @Autowired
    private ObjectMapper mapper;

    @Autowired
    private JdbcTemplate jdbc;

    private final List<String> createdOrders =
            new ArrayList<>();

    @AfterEach
    void cleanupDatabaseRows() {
        for (String order : createdOrders) {
            jdbc.update("""
                    DELETE FROM outbox_events
                    WHERE aggregate_id = ?
                    """, order);
            jdbc.update("""
                    DELETE FROM orders
                    WHERE order_id = ?
                    """, order);
        }
    }

    @Test
    void committedOutboxEventIsPublishedToRealQueue()
            throws Exception {
        assertTrue(rabbit.isRunning());

        String order = "ORD-" + UUID.randomUUID();
        String event = "evt-" + UUID.randomUUID();
        createdOrders.add(order);

        command.create(order, 2, event);

        assertEquals("PENDING", outbox.stateOf(event));
        assertEquals(1, relay.flushOnce());
        assertEquals("PUBLISHED", outbox.stateOf(event));

        Message message = rabbitTemplate.receive(
                OutboxTopology.QUEUE, 10_000L);

        assertNotNull(message);
        assertEquals(
                event,
                message.getMessageProperties()
                        .getHeaders().get("eventId"));
        assertEquals(
                event,
                message.getMessageProperties()
                        .getMessageId());

        OrderCreatedEvent fromBroker =
                mapper.readValue(
                        message.getBody(),
                        OrderCreatedEvent.class);

        assertEquals(
                new OrderCreatedEvent(
                        event, order, 2, 1),
                fromBroker);
    }

    @Test
    void relayWithNoPendingEventsPublishesNothing() {
        assertTrue(rabbit.isRunning());
        assertEquals(0, relay.flushOnce());
    }
}
```

**Hai integration methods** dùng **RabbitMQ server thật trong Docker** và H2 cho outbox/order:

- @Testcontainers + static @Container quản lý RabbitMQ theo class.
- `@ServiceConnection` từ Spring Boot tạo `RabbitConnectionDetails`; không hardcode `localhost:5672` hoặc credentials.
- Order/outbox row được commit trước khi relay chạy; kiểm tra state chuyển PENDING → PUBLISHED.
- `RabbitOutboxPublisher` thực sự chờ correlated publisher confirm, kiểm tra return, rồi mark PUBLISHED.
- `RabbitTemplate.receive(queue, 10_000L)` lấy message thật từ queue (đây là **consume**, không phải peek); kiểm tra eventId header/messageId và JSON body.
- Không có consumer @RabbitListener trong bộ test này; nó kiểm tra **producer + broker topology/routing**, không kiểm tra downstream business handler.
- Test không đánh dấu `@Transactional`; như vậy relay đọc được committed outbox state và không lệ thuộc transaction test chưa commit.

**Cảnh báo quan trọng:** publisher confirm ACK cùng việc đọc được message từ queue **không chứng minh** message vẫn tồn tại sau broker restart hoặc downstream consumer đã xử lý. Nếu contract yêu cầu durable/quorum queue, persistent delivery mode, confirm after fsync và failover, cần integration tests/cluster topology tương ứng.

### Tại sao @ServiceConnection không thay thế database transaction?

`@ServiceConnection` chỉ cấp **RabbitMQ connection details**. Transaction DB được tạo qua JDBC transaction manager của Spring Boot. Nó không bao giờ tự tạo một XA transaction chung với RabbitMQ. Kết quả được kiểm chứng bởi sự tách biệt: `OrderCommandService.create` commit DB, relay publish sau, rồi cập nhật state.

### Cleanup với H2 test

Các tests lưu mỗi order ID riêng và `@AfterEach` xóa outbox trước, order sau vì FK. H2 test-only datasource không phải production. Nếu một assertion ở giữa thất bại, cleanup vẫn được chạy theo lifecycle JUnit thông thường.

**Không đem những đoạn DELETE này chạy trên production/staging DB shared.** Nếu đổi sang PostgreSQL Testcontainers, dùng database ephemeral riêng và migration/cleanup tương ứng. Với test song song trên shared broker/DB, queue names và data keys phải cô lập để không lấy nhầm message.

## 18. Test tiếp tình huống DB fail nhưng broker không được gửi

Một integration test quan trọng không chỉ xác nhận success mà còn phải bảo vệ failure window:

```text
command.create(orderA, eventX) -> COMMIT
command.create(orderB, eventX) -> outbox UNIQUE error
                                     |
                                     v
                                  ROLLBACK orderB
relay.flushOnce() chỉ được thấy eventX của orderA
```

`AtomicOutboxTest.outboxUniqueFailureRollsBackPriorOrderInsert()` đã kiểm tra phần chính: orderB không còn trong DB. Bạn có thể mở rộng với publisher spy/gateway fake để xác nhận relay không bao giờ publish event của orderB.

**Không test kiểu “mock OutboxStore ném exception rồi verify service gọi save”** và cho đó là atomicity. Một mock không thể chứng minh JDBC rollback. Chỉ transaction integration test với DB thật (H2 hoặc production-like engine) mới có bằng chứng đối với SQL commit/rollback.

Một trường hợp nữa là database commit **thành công** nhưng process chết ngay sau đó. Row outbox PENDING vẫn tồn tại vì đã commit cùng order. Test có thể tạo dữ liệu, đóng instance service/context và khởi tạo relay mới trỏ cùng database để chứng minh recovery; khi test dùng H2 memory DB với context reset, database có thể biến mất nên phải dùng database lifecycle thích hợp (ví dụ PostgreSQL container lưu DB trong khoảng test).

## 19. Inbox/idempotent consumer: bảo vệ trước duplicate event

Transactional outbox không loại bỏ khả năng event gửi hai lần. Consumer cần bảo đảm **logical business effect chỉ áp dụng một lần** cho cùng eventId.

Phác thảo schema consumer database:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(64) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_projection (
    order_id VARCHAR(64) PRIMARY KEY,
    quantity INTEGER NOT NULL
);
```

**Cách làm sai:** `if (!exists(eventId)) { applyEffect(); insertProcessed(eventId); }` ở ngoài transaction hoặc không có UNIQUE. Hai consumers có thể cùng thấy “chưa tồn tại” và cùng áp dụng side effect.

**Cách tốt hơn:** consumer xử lý *đánh dấu idempotency + business effect trong cùng DB transaction*, dùng unique constraint để chặn duplicate:

```text
BEGIN consumer DB TX
  INSERT processed_events(event_id)
    -- unique constraint chặn eventId đã xử lý
  APPLY business projection
COMMIT consumer DB TX
ACK broker
```

Nếu INSERT processed_events bị trùng, consumer có thể nhận biết đó là duplicate và ACK/no-op theo policy. Tuy nhiên, với PostgreSQL, **một constraint violation bên trong transaction làm transaction hiện tại vào failed state**; không nên chỉ catch `DuplicateKeyException` rồi tiếp tục SQL trong cùng transaction như thể không có gì. Dùng một transaction boundary phù hợp hoặc một insert-idempotent statement theo engine.

### PostgreSQL-specific: ON CONFLICT DO NOTHING

Ví dụ snippet **dành cho PostgreSQL, không phải class runnable độc lập**:

```sql
INSERT INTO processed_events(event_id)
VALUES (:event_id)
ON CONFLICT (event_id) DO NOTHING;
```

Kiểm tra số row affected:

- 1 row → event mới, tiếp tục business effect trong **cùng transaction**.
- 0 row → duplicate, skip effect và return success theo policy.
- Một lỗi DB khác → không xem nó là duplicate.

Trong Java/Spring JDBC có thể dùng `NamedParameterJdbcTemplate.update(...)` và `@Transactional` trên service xử lý message, nhưng cần bảo đảm cả insert và projection update dùng **cùng datasource/transaction manager**.

### Idempotency không tự bảo vệ HTTP/email ngoài DB

Nếu consumer đã gửi email/charge payment trước khi insert idempotency row rồi crash, redelivery có thể gửi lần nữa. Đối với external API, truyền idempotency key đến provider nếu họ hỗ trợ; dùng outbox khác cho side effects hoặc thiết kế saga/compensation.

Đừng tuyên bố exactly-once trên toàn hệ thống chỉ vì một local unique constraint. Có thể đạt “effectively once” cho **một phạm vi DB side effect được giao dịch và dedup đúng**, không phải mọi downstream system.

## 20. Kafka, transaction synchronization và Debezium CDC

### 20.1. Kafka producer transaction không bằng XA với JDBC

Spring Kafka có cơ chế Kafka transaction manager và transaction synchronization, ví dụ:

```java
@Transactional
public void process() {
    jdbc.update("INSERT ...");
    kafkaTemplate.send("orders.events", "key", "value");
}
```

Đây là **snippet kiến trúc**, không phải code runnable của bộ RabbitMQ demo; cần KafkaTemplate bean, topic, transaction settings và imports. Khi KafkaTemplate tham gia một transaction được đồng bộ với JDBC manager, Spring Kafka có thể commit database trước rồi commit Kafka (hoặc điều chỉnh thứ tự qua boundary thích hợp). Nếu transaction thứ hai fail **sau transaction thứ nhất đã commit**, hệ thống vẫn có inconsistency và phải xử lý bằng compensation/reconciliation. <https://docs.spring.io/spring-kafka/reference/kafka/transactions.html> giải thích chi tiết.

Kafka exactly-once semantics (EOS) áp dụng **trong phạm vi Kafka transactions/consume-transform-produce** theo các điều kiện cụ thể; nó không tự đưa một external relational database vào cùng atomic commit. Nếu contract yêu cầu DB-to-Kafka reliability và phục hồi khi process crash, transactional outbox/CDC thường dễ lý giải hơn.

### 20.2. Polling relay so với Debezium outbox event router

| Khía cạnh | Polling relay (bài này) | CDC / Debezium |
| --- | --- | --- |
| Phát hiện event | SELECT rows PENDING | Theo DB change log/binlog/WAL |
| Schema | Có thể dùng state/attempts | Thường INSERT-only outbox records |
| Điểm vận hành | Scheduler, claim/lease, retry, status | Kafka Connect/Debezium, offsets, SMT, lag |
| Ordering | Cần sequence/claim policy | Theo commit log và connector, thêm key/partition strategy |
| Failure | Retry + idempotency | CDC replay + idempotency |
| Tích hợp | Tự viết publisher API | Config connector/router phù hợp |
| Độ phức tạp | App có thêm relay code | Hạ tầng CDC riêng |

Debezium Outbox Event Router đọc outbox records, route topic và có thể đưa event ID vào message header, aggregate ID vào key. **Nếu dùng default Debezium SMT, không biến mỗi PENDING row thành một loạt UPDATE state rồi mong router tự hiểu semantics**; Debezium docs nêu outbox rows thường được xử lý như insert events và UPDATE có policy riêng.

**Test CDC thực sự** cần database transaction log, connector, Kafka broker, SMT config, offsets và assertions end-to-end. Unit test mapper hoặc H2 outbox test không chứng minh connector phát event như mong đợi.

## 21. Multi-instance relay: claim/lease thay vì SELECT PENDING đơn giản

Mã `OutboxStore.findPending(50)` ở mục 11 phù hợp **một worker**. Trong triển khai nhiều replicas:

```text
Worker A: SELECT event X PENDING
Worker B: SELECT event X PENDING
Worker A: publish X
Worker B: publish X
```

Hai workers có thể publish cùng một event, dù chỉ một worker mark được PUBLISHED. Idempotent consumer vẫn cần, nhưng duplicate traffic/ordering tăng lên.

Một kiến trúc polling production thường dùng:

1. Trong transaction **ngắn** ở DB, claim batch pending rows: `SELECT ... FOR UPDATE SKIP LOCKED` ở PostgreSQL hoặc cơ chế lock/lease tương đương theo engine.
2. Ghi `ownerId`, `leaseUntil`, trạng thái `IN_PROGRESS` và increment attempts rồi **commit claim**.
3. Publish tới broker **ngoài DB transaction**; đợi publisher confirm/return có timeout.
4. Nếu thành công, update PUBLISHED với điều kiện `event_id` + `ownerId` + lease/version, tránh worker cũ ghi đè trạng thái mới.
5. Nếu lỗi/timeout, retry với backoff và lease expiry; crash trước bước hoàn tất sẽ để event được claim lại.
6. Reconciliation job phát hiện rows stuck, alert theo age/attempts; có manual replay/recovery policy.

**Không giữ row lock suốt network call.** Long transaction làm pool/locks cạn và ảnh hưởng business writes. Kể cả có claim/lease, crash sau publish mà trước mark vẫn có thể tạo duplicate; consumer idempotency là lớp không thể bỏ.

**Ordering theo aggregate:** nếu order có `created` rồi `paid`, cần tránh gửi `paid` trước `created` khi nhiều workers. Cân nhắc `aggregate_version`, partition key, chỉ claim next sequence của aggregate hoặc route serial theo aggregate; không dựa vào timestamp alone.

## 22. Testing failure injection có ý nghĩa

Một bộ test outbox tốt không chỉ có happy path. Nên kiểm tra ma trận:

| Failure injection | Cách mô phỏng | Điều cần assert |
| --- | --- | --- |
| Business rule invalid | quantity = 0 | Không có order/outbox |
| Outbox constraint fail | Duplicate eventId | Order mới rollback |
| Broker send fail | Mock EventPublisher throw | Không mark published |
| Confirm timeout | Mock publisher throw timeout wrapper | Giữ pending, tăng attempts |
| Publish succeeds, mark fails | Stub OutboxStore.markPublished throw | Lượt sau có thể publish lại cùng eventId |
| Unroutable | Real broker, wrong routing key | Publisher return được nhận; không mark |
| DB outage sau publish | DB fault injection / proxy | Không giả định event mất; có thể duplicate |
| Consumer duplicate | Publish cùng eventId hai lần | Business effect tối đa một lần |
| Poison payload | Invalid schema/version | DLQ/error policy; không endless retry |
| Broker unavailable lâu | Dedicated Testcontainers outage test | Outbox pending, retry/backoff, alert |
| Process restart | Stop/recreate relay với DB còn sống | Event PENDING được phát về sau |

**Những gì ví dụ đã có:** transaction rollback qua duplicate eventId; mocked publisher fail/retry/success; RabbitMQ broker confirm và route vào queue. Những dòng khác là **kịch bản mở rộng**, không phải tuyên bố toàn bộ đã được tự động test.

Nếu thật sự test broker outage, cần điều phối lifecycle container, chờ connection fail có timeout và tránh làm các test khác share Spring context bị lỗi do container stop. Không tùy tiện gọi `rabbit.stop()` giữa suite rồi để cached context tiếp tục giữ connection cũ.

## 23. @Transactional trong JUnit test có thể che dấu vấn đề

Một test có thể viết:

```java
@SpringBootTest
@Transactional
class WrongProofTest {
    @Test
    void writesOrderAndEvent() {
        command.create("ORD-1", 1, "evt-1");
        // SELECT trong cùng transaction thấy 2 rows.
    }
}
```

Đây là **anti-pattern minh họa**, không phải file thuộc bộ runnable. Vì test-managed transaction đã có trên JUnit thread, `OrderCommandService.create` dùng propagation REQUIRED thường join nó. Các SELECT trong test có thể thấy **uncommitted rows**; kết thúc method TestContext sẽ rollback. Nó **không chứng minh order và outbox cùng bền vững sau service COMMIT**.

Trong `AtomicOutboxTest`, test **không** đặt `@Transactional` để cho service proxy commit thật. Dọn rows trong `@AfterEach` bằng test-only datasource. Hoặc dùng `TestTransaction.flagForCommit/flagForRollback/end` một cách có chủ đích khi cần quan sát sau test transaction; không nhầm với semantics production.

Với RabbitMQ consumer chạy thread khác, `@Transactional` trên JUnit test không bao trùm write của consumer. Với HTTP thật qua `@SpringBootTest(RANDOM_PORT)` cũng vậy. Dùng test DB/container cô lập, timeout hữu hạn và cleanup ở transaction thích hợp.

## 24. Chương trình Java SE độc lập: duplicate sau crash

Để thấy vì sao **at-least-once relay** cần consumer idempotency, ta mô phỏng broker đã nhận event nhưng relay crash trước mark. Không cần Spring/DB/Docker.

Tạo `src/main/java/example/outbox/OutboxCrashModel.java`:

```java
package example.outbox;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class OutboxCrashModel {
    private OutboxCrashModel() {
    }

    public record Result(
            int brokerDeliveries, int uniqueEffects) {
    }

    public static Result simulate() {
        String eventId = "evt-1";
        List<String> brokerDeliveries =
                new ArrayList<>();

        // Publish thành công, nhưng relay crash
        // trước khi mark PUBLISHED:
        brokerDeliveries.add(eventId);

        // Relay restart và gửi lại eventId cũ:
        brokerDeliveries.add(eventId);

        Set<String> processedEventIds =
                new HashSet<>();
        int applied = 0;

        for (String received : brokerDeliveries) {
            if (processedEventIds.add(received)) {
                applied++;
            }
        }

        return new Result(
                brokerDeliveries.size(), applied);
    }

    public static void main(String[] args) {
        Result result = simulate();

        System.out.println(
                "brokerDeliveries="
                        + result.brokerDeliveries());
        System.out.println(
                "uniqueEffects="
                        + result.uniqueEffects());
    }
}
```

Compile/run bằng JDK 17+:

```bash
javac -d out src/main/java/example/outbox/OutboxCrashModel.java
java -cp out example.outbox.OutboxCrashModel
```

Stdout **chính xác**:

```text
brokerDeliveries=2
uniqueEffects=1
```

Ý nghĩa:

- Broker nhận 2 lần cùng eventId do retry sau crash.
- Consumer **mô phỏng** dedup bằng `HashSet` nên business effect chỉ áp dụng một lần.
- **Đây chỉ là Java SE model**, không phải một transactional inbox production. `HashSet` mất state khi process restart, không atomic với business DB write và không an toàn khi nhiều consumer instances. Với production, dùng database unique constraint/transaction hoặc idempotent external API.

Tạo `src/test/java/example/outbox/OutboxCrashModelTest.java`:

```java
package example.outbox;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OutboxCrashModelTest {
    @Test
    void duplicateDeliveryCanProduceOneLogicalEffect() {
        OutboxCrashModel.Result result =
                OutboxCrashModel.simulate();

        assertEquals(2, result.brokerDeliveries());
        assertEquals(1, result.uniqueEffects());
    }
}
```

**Một JUnit unit method** kiểm tra mô hình, không thay thế RabbitMQ/PostgreSQL integration.

## 25. Chạy các test

Unit tests không cần Docker:

```bash
./gradlew test --tests example.outbox.OutboxRelayUnitTest
./gradlew test --tests example.outbox.OutboxCrashModelTest
```

JDBC transaction tests dùng H2 và Spring context, không cần broker đang chạy (không gọi publisher):

```bash
./gradlew test --tests example.outbox.AtomicOutboxTest
```

RabbitMQ broker integration cần Docker:

```bash
./gradlew test --tests example.outbox.RabbitOutboxIntegrationTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.outbox.OutboxRelayUnitTest"
.\gradlew.bat test --tests "example.outbox.OutboxCrashModelTest"
.\gradlew.bat test --tests "example.outbox.AtomicOutboxTest"
.\gradlew.bat test --tests "example.outbox.RabbitOutboxIntegrationTest"
```

**Kỳ vọng nếu JDK 17+, Boot 3.5 BOM, H2 schema và Docker image phù hợp:**

| Test class | JUnit methods | Yêu cầu |
| --- | ---: | --- |
| `OutboxRelayUnitTest` | 4 | Mockito, không broker |
| `OutboxCrashModelTest` | 1 | Java/JUnit, không broker |
| `AtomicOutboxTest` | 3 | Spring JDBC + H2 |
| `RabbitOutboxIntegrationTest` | 2 | Spring JDBC + H2 + RabbitMQ Testcontainers |
| **Tổng** | **10** | Có cả unit, DB và broker tests |

Đây là **kết quả kỳ vọng khi người học thực sự chạy bộ test**; bài không tuyên bố đã khởi động Docker trong môi trường của người đọc. Gradle/JUnit logs phụ thuộc runner/version nên không có stdout chung chính xác. Riêng `OutboxCrashModel` là Java SE demo, có stdout cố định ở mục 24.

**Một lưu ý về test context cache:** static `@Container` của JUnit dừng RabbitMQ sau test class; Spring có thể cache `ApplicationContext` lâu hơn. Khi nhiều classes dùng cùng cached context, cần đồng bộ lifecycle hoặc khai báo container dưới dạng Spring-managed bean, tránh datasource/RabbitConnectionFactory trỏ vào container đã dừng.

## 26. Quan sát và vận hành outbox trong production

Một outbox không có monitoring chỉ chuyển lỗi từ request sang worker âm thầm. Nên theo dõi:

- Số event PENDING; tuổi của PENDING row lâu nhất.
- Attempts trung bình và các rows vượt retry threshold.
- Chênh lệch thời gian từ DB COMMIT → broker confirm.
- Publisher confirm ACK/NACK, unroutable returns, broker connection timeouts.
- Tốc độ publish, throughput, queue depth, consumer lag, DLQ rates.
- Dead-letter reason được mask, không log raw payload nhạy cảm.
- Số duplicate eventId bị inbox loại bỏ, số event lỗi schema.
- Worker claim/lease expired, stuck jobs, reconciliation counts.
- Retention/partitioning/index size của outbox table, VACUUM/cleanup nếu PostgreSQL.
- Alert theo **tuổi event** và business SLO; đừng chỉ alert khi worker process chết.

**Retry/backoff:** không poll liên tục hàng trăm lần mỗi giây khi broker không sẵn sàng. Dùng exponential backoff/jitter, cooldown/max-attempts/parking queue theo policy; poison event nên được điều tra thay vì retry vô hạn.

**Bảo mật:** event payload có thể chứa PII/financial info. Chỉ đưa trường thực sự cần; mã hóa đường truyền, quản lý credentials, quyền truy cập broker/topic, TTL/retention và logs. Không đưa database URL, AMQP password hay raw payload nhạy cảm vào exception public.

**Migrations:** khi đổi event schema, tăng `schemaVersion` và hỗ trợ consumer cũ/producer mới theo contract. Trong rollouts, các outbox rows từ phiên bản cũ có thể còn PENDING; relay/consumer phải đọc được chúng sau deploy.

## 27. Các lỗi phổ biến

**1. Đặt RabbitTemplate.send trong @Transactional JDBC rồi tưởng atomic.** Broker và DB không tự share một commit.

**2. Gửi event trước commit DB.** Consumer có thể nhìn thấy phantom order nếu DB rollback.

**3. Commit DB trước rồi gửi event mà không lưu durable intent.** Crash ở giữa làm mất message.

**4. Chỉ dùng @TransactionalEventListener(AFTER_COMMIT) như durability guarantee.** Callback trong process có thể không chạy sau crash; cần outbox.

**5. Ghi order và outbox vào hai database/transaction managers khác nhau.** Atomicity của cùng DB transaction bị mất.

**6. Catch exception outbox INSERT rồi bỏ qua.** Business order có thể commit mà không có event; phải rollback hoặc có chiến lược rõ.

**7. Unit test mocks đã pass và kết luận database transaction đúng.** Mocks không chứng minh SQL rollback.

**8. Test có @Transactional trên JUnit rồi đọc uncommitted rows.** Không xác nhận service đã commit; thiết kế outside-test-transaction assertions.

**9. Gọi RabbitTemplate.convertAndSend và mark PUBLISHED ngay.** Chưa chờ publisher confirm/returns; có thể mất event nếu send fail.

**10. Xem RabbitMQ confirm ACK là consumer processed/DB commit.** Không phải; consumer có acknowledgement và transaction riêng.

**11. Không bật mandatory+publisher returns rồi xem confirm ACK là routed.** Broker có thể ACK message không route được.

**12. Timeout confirm thì mark success vì sợ duplicate.** Có thể gây missing event; giữ PENDING và chấp nhận retry.

**13. Đánh dấu PUBLISHED trước publish.** Crash sau mark có thể mất event vĩnh viễn.

**14. Tạo eventId mới cho mỗi retry.** Phá dedup; retry phải giữ **cùng eventId**.

**15. Không có idempotency ở consumer.** Crash giữa broker publish và DB mark hoặc giữa consumer commit và ACK có thể double-apply.

**16. Chỉ kiểm tra existence rồi apply side effect không có unique constraint.** Hai consumers concurrent có thể cùng xử lý event.

**17. Catch PostgreSQL unique violation rồi tiếp tục SQL trong transaction đã aborted.** Phải xử lý conflict theo transaction boundary hoặc ON CONFLICT.

**18. Có hai relay instances cùng SELECT PENDING không claim/lease.** Cả hai có thể publish trùng, reorder aggregate events.

**19. Giữ DB transaction/row locks xuyên suốt network call.** Tăng contention/connection exhaustion, không mang lại atomic distributed commit.

**20. Dùng timestamp làm ordering tuyệt đối.** Timestamp có thể trùng; cần aggregate sequence/partition policy khi ordering là contract.

**21. Áp polling mutable outbox schema cho Debezium Event Router mặc định.** CDC SMT thường xử lý outbox như INSERT-only events; config/update semantics khác.

**22. Tưởng Kafka EOS tự đưa JDBC vào cùng XA transaction.** Cần phân tích commit order/failure gap, không suy diễn từ Kafka producer transaction.

**23. Dùng H2 tests để bảo đảm PostgreSQL deadlocks/locks/SQL dialect.** Dùng Testcontainers production-like database khi rủi ro phụ thuộc engine.

**24. Dùng @DirtiesContext để dọn committed data/broker messages.** Context reload không xóa external DB/queue.

**25. Thiếu backoff/monitoring/retention.** Outbox sẽ tích lũy PENDING hoặc tăng không giới hạn mà không ai biết.

## 28. Checklist QA và tiêu chí kết luận

**Phạm vi transaction:**

- Order và outbox có dùng **cùng datasource/transaction manager**?
- Service `@Transactional` có được gọi qua Spring proxy, không self-invocation?
- Có test outbox INSERT failure → order rollback thật trên DB?
- Test có quan sát state **sau commit** thay vì chỉ trong test-managed transaction?
- Có tránh gửi broker trong request DB transaction?

**Publisher/relay:**

- `eventId` ổn định qua retry và độc lập với aggregateId?
- Có publisher confirms và returns theo contract, không chỉ verify method call?
- Broker ACK được phân biệt với routing, consumer processing và DB commit?
- Publish fail/timeout có giữ event PENDING?
- Publish success + mark fail có thể resend, consumer có chịu duplicate?
- Có claim/lease/ownership nếu nhiều relay instances?
- Có ordering policy theo aggregate nếu events phụ thuộc thứ tự?
- Có retry/backoff, alert và DLQ/parking policy?

**Consumer/idempotency:**

- Có processed-event unique key hoặc idempotent external API?
- Dedup marker và business DB effect có atomic trong cùng transaction?
- Duplicate/concurrent deliveries có test không?
- Retry after crash có thể safely reapply hoặc skip?
- Consumer ACK/offset commit có được xem là transaction riêng?
- Poison message/schemaVersion cũ có policy rõ?

**Test isolation/CI:**

- Unit relay test không phụ thuộc RabbitMQ/Docker?
- DB atomicity test có H2/PostgreSQL thật, không mock JDBC?
- Broker integration có publish và nhận từ queue thật với timeout hữu hạn?
- Không gắn @Transactional trên test rồi suy diễn đã commit?
- Cleanup order/outbox/queue độc lập, không chạm dữ liệu production?
- Docker image/version, Spring Boot/Testcontainers BOM và mapped ports đúng?
- Full suite không bị context cache/container lifecycle race?
- Có kiểm tra production-specific SQL/CDC qua integration test riêng khi cần?

**Kết luận:** transactional outbox không khiến JDBC và broker trở thành một transaction chung. Nó thay **hai hành động khó commit nguyên tử** thành **một commit DB cho business row + outbox event**, rồi chuyển trách nhiệm gửi sang relay có thể phục hồi. Vì publish/mark vẫn là hai bước, một event có thể được gửi hơn một lần: **at-least-once + idempotent consumer** là mô hình an toàn và dễ kiểm thử. Test phải kiểm tra atomicity ở DB, retry/mark ở relay, confirms/routing trên broker thật, và side effect/idempotency ở consumer — mỗi mức đưa ra một bằng chứng khác nhau.

## 29. Tài liệu tham khảo

- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy, propagation, rollback và ranh giới transaction.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): khác biệt test transaction với application transaction.
- [Spring AMQP — RabbitTemplate and Publisher Confirms/Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `CorrelationData.getFuture()`, returns, mandatory và publisher acknowledgements.
- [Spring Boot 3.5 — AMQP Messaging](https://docs.spring.io/spring-boot/3.5/reference/messaging/amqp.html): RabbitTemplate, RabbitAdmin, listener infrastructure và config.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` cho RabbitMQContainer.
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): JDBC/Kafka transaction synchronization, thứ tự commit và giới hạn.
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): CDC/SMT, event IDs, aggregate keys và insert-only outbox semantics.
- [Testcontainers Java — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): RabbitMQ container; kiểm tra 1.x/2.x artifacts theo project BOM.

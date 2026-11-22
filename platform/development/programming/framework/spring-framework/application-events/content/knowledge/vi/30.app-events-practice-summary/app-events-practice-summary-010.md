# Thiết kế outbox cho integration event trong Spring Framework Application Events

## 1. Mục tiêu thiết kế: một thay đổi nghiệp vụ, một integration event bền vững

Giả sử dịch vụ **Order** ghi đơn hàng vào database và cần thông báo cho hệ thống **Inventory**, **Billing** hoặc **Delivery**. Trong Spring, ta có thể gọi `ApplicationEventPublisher.publishEvent(new OrderPlaced(...))` và xử lý sự kiện bằng `@EventListener`. Cách đó rất phù hợp để giảm phụ thuộc giữa các module trong cùng ứng dụng, nhưng **Spring Application Events thông thường không phải cơ chế giao message bền vững giữa các dịch vụ**.

Đối với **integration event**, yêu cầu thường mạnh hơn:

- Không phát event cho một transaction tạo đơn **đã rollback**.
- Nếu transaction đã commit, có một **bản ghi event bền** để chuyển phát ngay cả khi JVM chết hoặc broker tạm ngừng.
- Nếu relay không biết lần gửi trước đã thành công chưa, có thể **gửi lại cùng eventId**.
- Consumer **không áp dụng side effect hai lần** khi một event bị gửi lặp.
- Event có định dạng/schema/version ổn định để các dịch vụ deploy độc lập.
- Có cơ chế giám sát backlog, retry, lỗi dữ liệu và thời gian giao nhận.

**Transactional outbox** là một mẫu đáp ứng những điều kiện đầu tiên: producer ghi **business data** và **outbox record** trong **cùng local database transaction T1**, rồi một relay gửi outbox record sang broker/API sau commit.

> Bảo đảm cốt lõi: nếu T1 commit, business row và event row cùng tồn tại; nếu T1 rollback, cả hai cùng rollback. Việc gửi event ra broker vẫn thường có ngữ nghĩa **at-least-once**, không phải exactly-once end-to-end. Consumer phải idempotent.

Đây là bài **thiết kế thực hành**: ta đi từ yêu cầu, event contract, schema, transaction boundary, relay, consumer, fault injection đến checklist review production. Ví dụ chính dùng **Java 17, Spring Framework 6.2, Spring JDBC và H2** để dễ chạy mà không cần một Kafka cluster thật.

## 2. Ranh giới: domain event khác integration event

Một **domain event** mô tả điều quan trọng vừa xảy ra trong một aggregate hoặc module, ví dụ `OrderPlaced`. Trong một ứng dụng Spring, domain event có thể được xử lý bởi `@EventListener` hoặc `@TransactionalEventListener`.

Một **integration event** là **hợp đồng công khai giữa các thành phần có vòng đời độc lập**. Không nên xuất thẳng một entity JPA hay chi tiết nội bộ của service sang downstream; integration event cần được thiết kế như API.

| Tiêu chí | Domain event nội bộ | Integration event |
|---|---|---|
| Mục đích | Tách logic/module bên trong ứng dụng | Đồng bộ sự kiện giữa dịch vụ/hệ thống |
| Vòng đời | Có thể rất ngắn, trong JVM | Có thể tồn tại trong DB, broker, DLQ nhiều ngày |
| Versioning | Thường thay đổi cùng một codebase | Cần schema evolution và compatibility |
| Delivery | Spring dispatch trong ApplicationContext | Broker/API, có retry/ack/offset |
| Payload | Object Java/domain model | Snapshot/contract đã serialize, tránh entity mutable |
| Duplicate | Tùy flow cục bộ | Phải giả định có thể nhận lặp |
| Ordering | Phụ thuộc listener/dispatcher | Phụ thuộc key, partition, version và worker |
| Security | Trust boundary trong process | Trust boundary giữa hệ thống |

Ví dụ: service có `OrderPlacedDomainEvent(orderId, orderEntity)` bên trong, nhưng integration event có thể là `OrderPlacedV1` chỉ chứa `eventId`, `orderId`, `tenantId`, `amountMinor`, `currency`, `aggregateVersion` và thời điểm nghiệp vụ. Payload không phụ thuộc đến session Hibernate hoặc database schema nội bộ.

### Không biến tên method thành contract

`OrderCreated`, `OrderPlaced` hoặc `PaymentCaptured` cần định nghĩa **khi nào sự kiện được coi là đúng**: trước commit hay sau commit, khi đặt hàng hay khi xác nhận thanh toán, có cho phép retry/cancel hay không. Với integration event, nên phát hành **một business fact đã được commit** thay vì thông báo mơ hồ “service vừa gọi method create”.

## 3. Failure matrix: lý do phải dùng outbox

Nếu một service vừa ghi DB vừa gửi Kafka/HTTP, đó là bài toán **dual write**. Hai lệnh không tự nằm trong cùng một transaction ACID.

### Gửi trước khi commit

~~~text
BEGIN T1
  INSERT orders(id='ORD-344')
  send Kafka OrderPlaced('ORD-344') -> broker ACK
  COMMIT T1 -> thất bại
~~~

Consumer nhận một event cho đơn hàng không tồn tại trong database. Broker ACK không buộc database commit.

### Gửi sau khi commit

~~~text
BEGIN T1
  INSERT orders(id='ORD-344')
COMMIT T1 -> thành công
JVM crash trước lệnh send Kafka
~~~

Đơn hàng đã tồn tại nhưng Inventory/Billing không được thông báo. Nếu event chỉ nằm trong RAM, không có thứ gì để tự phát lại khi service khởi động.

### Chỉ dùng @TransactionalEventListener(AFTER_COMMIT)

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    kafkaTemplate.send("order-events", event.orderId(), serialize(event));
}
~~~

Đây là **mã minh họa tích hợp**, không chạy độc lập. `@TransactionalEventListener(AFTER_COMMIT)` giúp callback chỉ chạy sau khi T1 commit nhưng **không tự lưu event vào database trước commit**. Nếu JVM crash giữa DB commit và việc gửi, vẫn có thể mất event. Nếu gửi bất đồng bộ, cần đợi xác nhận của broker đúng contract; method `send(...)` trả về không tự chứng minh message đã durable.

| Thời điểm hỏng | Direct send | Callback AFTER_COMMIT | Transactional outbox |
|---|---|---|---|
| Rollback T1 sau send | Có thể có event mồ côi | Callback không chạy sau rollback | Outbox cũng rollback |
| Crash sau T1 commit, trước send | Có thể mất event | Có thể mất event | Outbox còn để relay |
| Broker tạm thời không hoạt động | Cần retry riêng | Cần retry riêng | Relay retry từ dữ liệu bền |
| Gửi thành công, crash trước đánh dấu đã gửi | Có thể lặp | Có thể lặp | Có thể lặp: consumer phải dedupe |
| Process restart | Không có log event mặc định | Không có log event mặc định | Tiếp tục đọc outbox chưa gửi |

**Outbox không làm cho broker và database thành một transaction phân tán.** Nó thay đổi điểm commit quan trọng: thứ cần đảm bảo nguyên tử là **business state + ý định publish** trên một database.

## 4. Luồng kiến trúc đề xuất

~~~text
              SPRING ORDER SERVICE
                    |
             @Transactional T1
                    |
          +---------+---------+
          |                   |
          v                   v
      orders table       outbox_events table
          |                   |
          +---------+---------+
                    |
                  COMMIT
                    |
      +-------------+----------------+
      |                              |
      v                              v
  Order state                  Outbox PENDING
                                     |
                          Polling relay / CDC
                                     |
                            Kafka / RabbitMQ
                                     |
                     +---------------+--------------+
                     |                              |
                Inventory consumer             Billing consumer
                     |                              |
                durable inbox                  durable inbox
                     |                              |
                 update stock                 create invoice
                     |                              |
                 ACK message                    ACK message
~~~

Có **ba transaction boundaries**, không nên trộn lẫn:

1. **T1 của producer:** cập nhật aggregate và INSERT outbox.
2. **T2 của relay:** claim hoặc mark SENT/retry state cho outbox. Broker send nằm giữa các bước, không nguyên tử với chúng.
3. **T3 của consumer:** nhận eventId, đánh dấu processed và áp dụng side effect DB trong một transaction riêng.

Một service không thể dựa vào `@Transactional` ở producer để tự động bao gồm DB của consumer hoặc broker.

## 5. Thiết kế event contract trước khi viết code

Một integration event nên có **envelope** ổn định, còn dữ liệu nghiệp vụ nằm trong payload theo version.

Ví dụ minh họa:

~~~json
{
  "eventId": "d51d4ab8-11b2-4e9c-9845-7a4115e5801e",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "producer": "order-service",
  "tenantId": "tenant-demo",
  "aggregateType": "Order",
  "aggregateId": "ORD-344",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-11T07:00:00Z",
  "correlationId": "req-demo-344",
  "data": {
    "currency": "VND",
    "amountMinor": 350000,
    "state": "PLACED"
  }
}
~~~

Đây là dữ liệu **giả định**. Số tiền dạng **đơn vị nhỏ nhất** tránh chuyển số thực thiếu chính xác; nếu dùng VND, hệ thống phải định nghĩa rõ quy tắc `amountMinor` theo ISO currency scale. Không tự suy ra mọi loại tiền đều có 2 chữ số thập phân.

### Trách nhiệm từng field

| Field | Vì sao cần? | Lưu ý |
|---|---|---|
| `eventId` | Định danh duy nhất lần phát sinh event; dùng idempotency | Retry **giữ nguyên** eventId |
| `eventType` | Định nghĩa loại fact | Không đặt theo tên method thay đổi liên tục |
| `schemaVersion` | Kiểm soát định dạng | Có chiến lược migrate/replay |
| `producer` | Ownership và route vận hành | Không dùng làm access-control proof |
| `aggregateId` | Dùng làm Kafka key, liên hệ đối tượng | Không thay thế eventId |
| `aggregateVersion` | Kiểm soát thứ tự/stale events | Cần cấp trong transaction của aggregate |
| `tenantId` | Hỗ trợ isolation/routing | Validate authorization ở consumer |
| `occurredAt` | Thời điểm nghiệp vụ | Không mặc định là commit timestamp |
| `correlationId` | Liên hệ command, trace, log | Không phải idempotency key bắt buộc |
| `data` | Payload immutable cần cho consumer | Tránh thừa PII hoặc entity/proxy |

Cần quyết định **độ hạt của event**: một `OrderPlaced` cho cả aggregate hay một event cho từng line item? Nếu một event có nhiều người nhận, contract phải đáp ứng họ nhưng không vì vậy chứa toàn bộ object graph.

### eventId khác aggregateId

~~~text
OrderPlaced(eventId=E1, orderId=ORD-344, version=1)
OrderPaid(eventId=E2, orderId=ORD-344, version=2)
Retry OrderPlaced(eventId=E1, orderId=ORD-344, version=1)
~~~

Consumer nên xử lý E1 và E2; bỏ bản E1 retry. Dedupe theo `orderId` sẽ vô tình bỏ cả E2.

### Cách thay đổi schema

- Thêm trường optional có default và bảo đảm consumer cũ bỏ qua field lạ khi contract cho phép.
- Khi đổi semantics/field bắt buộc, cân nhắc `OrderPlacedV2` hoặc nâng `schemaVersion` có kế hoạch.
- Chạy contract tests cho producer/consumer khi release độc lập.
- Event còn trong outbox hoặc DLQ phải vẫn deserialize được sau deploy mới.
- Version của **event contract** khác với version của **JPA entity** hay database migration.

## 6. Thiết kế bảng outbox theo hai hướng khác nhau

### 6.1. Polling outbox schema

Một schema tổng quát cho JDBC polling:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(24) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE integration_outbox (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(64) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    schema_version INT NOT NULL,
    payload_json VARCHAR(4000) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    next_retry_at TIMESTAMP NULL,
    published_at TIMESTAMP NULL,
    attempts INT NOT NULL DEFAULT 0
);

CREATE INDEX ix_integration_outbox_pending
    ON integration_outbox(status, next_retry_at, created_at);
~~~

Đây là **schema minh họa cho polling**, không phải cú pháp portable hoàn toàn hoặc schema mặc định của Debezium. Với PostgreSQL có thể dùng `uuid`, `jsonb`, `timestamptz`, partial index; MySQL/H2 có khác biệt. `status` có thể gồm:

~~~text
PENDING -> PROCESSING -> SENT
                  |
                  +-> RETRY_PENDING -> PROCESSING
                  |
                  +-> FAILED_PERMANENT / QUARANTINED
~~~

Nếu dùng nhiều workers, cần thêm `locked_by`, `lease_until`, `next_retry_at` và chiến lược claim atomic.

### 6.2. Schema dành cho Debezium Outbox Event Router

Nếu chọn **CDC** bằng Debezium, cần biết **Outbox Event Router SMT** mặc định mong đợi các cột:

~~~sql
-- Minh họa schema cho PostgreSQL + Debezium Outbox SMT:
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregatetype VARCHAR(255) NOT NULL,
    aggregateid VARCHAR(255) NOT NULL,
    type VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL
);
~~~

Trong cấu hình mặc định, `id` vào message header; `aggregateid` thành message key; `aggregatetype` dùng route topic, `type` là event type và `payload` là message payload. Có thể map field khác bằng SMT options như `table.field.event.id`, `table.field.event.key`, `table.field.event.payload`.

**Quan trọng:** tài liệu Debezium Outbox Router nêu rằng outbox table dành cho SMT **mong đợi các INSERT event rows**, không dùng workflow UPDATE status như polling. Updates được coi là thao tác không hợp lệ theo chính sách SMT mặc định. Nếu muốn CDC, thiết kế schema và cleanup theo Debezium/connector; đừng mang nguyên việc `UPDATE status='SENT'` của polling sang bảng CDC rồi hy vọng tương thích.

### 6.3. Quyết định schema bằng chiến lược relay

**Chọn polling** nếu muốn worker ứng dụng quản lý retry/backoff/status và chỉ cần RDBMS. **Chọn CDC** nếu đã có Kafka Connect/Debezium và muốn đọc change log của DB; hệ thống cần quản lý connector offsets, log retention và deployment. Cả hai đều cần chống duplicate ở consumer.

Không nên vận hành **polling và CDC phát cùng một dòng** tới cùng topic nếu không có cơ chế ownership/dedupe rõ; rất dễ double-publish.

## 7. Atomic write trong Spring: chỗ quan trọng nhất

Cách rõ ràng nhất là ghi business row và integration outbox row **ngay trong cùng method transactional**:

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orderRepository;
    private final IntegrationOutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orderRepository,
            IntegrationOutboxRepository outbox) {
        this.orderRepository = orderRepository;
        this.outbox = outbox;
    }

    @Transactional
    public void place(CreateOrder command) {
        Order order = orderRepository.create(command);
        IntegrationEvent event = IntegrationEvent.orderPlaced(order);
        outbox.insert(event);
    }
}
~~~

Đây là **đoạn tích hợp**, cần định nghĩa repository, event factory, transaction manager và serializer. Để thực sự bảo đảm atomicity:

1. `place(...)` phải được gọi qua Spring transactional proxy hoặc transaction programmatic thực sự.
2. Hai repository phải dùng **cùng DB/resource mà transaction manager điều khiển**.
3. Outbox INSERT chạy **trước T1 commit**, không chạy trong `AFTER_COMMIT`.
4. Nếu outbox INSERT thất bại, transaction phải rollback cả business change.
5. Nếu code bắt exception của outbox rồi tiếp tục commit, toàn bộ invariant bị phá.
6. Nếu business ở DB A nhưng outbox ở DB B và không có coordinator, đó vẫn là dual-write.

### Không lưu integration outbox lần đầu trong AFTER_COMMIT

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void writeOutbox(OrderPlaced domainEvent) {
    outboxRepository.insert(domainEvent);
}
~~~

Đây là **phản ví dụ** nếu mục tiêu là atomic outbox. Khi callback chạy, T1 business đã commit. Nếu mở một `REQUIRES_NEW` để INSERT outbox, đó là T2 độc lập; JVM vẫn có thể chết giữa T1 và T2. Nếu không mở T2 mà dùng resource cũ trong transaction completion, thao tác DB có thể không có commit tiếp theo.

`@TransactionalEventListener(AFTER_COMMIT)` hữu ích để thực thi side effect hậu commit nhưng **không tạo durability**. Nếu yêu cầu chắc chắn có event khi T1 commit, hãy ghi outbox ngay trong T1.

### Nếu dùng @EventListener thông thường để ghi outbox?

Có thể, nhưng cần đảm bảo listener chạy **đồng bộ** và tham gia **cùng T1**, đồng thời exception từ outbox phải làm transaction rollback. Nếu một ngày cấu hình multicaster executor hoặc `@Async`, outbox write có thể tách transaction và phá atomicity. Vì outbox là invariant quan trọng, lời gọi outbox repository **tường minh** trong service/domain unit of work thường dễ audit hơn.

## 8. Ví dụ runnable: Java 17 + Spring Framework 6.2 + JDBC/H2

Chương trình này chứng minh **thiết kế tối thiểu** với các nhánh:

1. Producer ghi order và outbox **trong cùng T1**, rồi commit.
2. Producer cố ý ném exception sau cả hai INSERT trong T2; cả hai INSERT rollback.
3. Relay gửi event nhưng **không đánh dấu SENT**, mô phỏng crash giữa broker send và ack database.
4. Relay chạy lại, gửi **chính eventId cũ**. Consumer in-memory dedupe, nên chỉ áp dụng một lần.
5. Relay đánh dấu SENT; chương trình đọc lại row counts từ H2.

Không cần Kafka thật để chứng minh transaction atomicity và crash window. Broker trong demo là stub đồng bộ. Phần production nhiều worker/durable inbox trình bày ở các mục sau.

### 8.1. Cấu trúc dự án

~~~text
integration-event-outbox/
├── pom.xml
└── src/main/java/demo/IntegrationOutboxDemo.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>integration-event-outbox</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. src/main/java/demo/IntegrationOutboxDemo.java

~~~java
package demo;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public final class IntegrationOutboxDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderWriter producer = context.getBean(OrderWriter.class);

            jdbc.execute("CREATE TABLE orders (" +
                "order_id VARCHAR(64) PRIMARY KEY, state VARCHAR(24) NOT NULL)");

            jdbc.execute("CREATE TABLE integration_outbox (" +
                "event_id VARCHAR(64) PRIMARY KEY, " +
                "aggregate_id VARCHAR(64) NOT NULL, " +
                "aggregate_version BIGINT NOT NULL, " +
                "event_type VARCHAR(100) NOT NULL, " +
                "schema_version INT NOT NULL, " +
                "payload_json VARCHAR(2000) NOT NULL, " +
                "status VARCHAR(20) NOT NULL, " +
                "created_at TIMESTAMP NOT NULL)");

            // T1: business + integration event cùng commit.
            producer.place("ORD-344", "EVT-344", false);
            printState("after commit", jdbc);

            // T2: cố tình rollback cả business + outbox.
            try {
                producer.place("ORD-ROLLBACK", "EVT-ROLLBACK", true);
            } catch (IllegalStateException e) {
                System.out.println("rollback cause=" + e.getMessage());
            }
            printState("after rollback", jdbc);

            CountingConsumer consumer = new CountingConsumer();
            LocalBroker broker = new LocalBroker(consumer);
            PollingRelay relay = new PollingRelay(jdbc, broker);

            // Lần 1: gửi thành công nhưng chưa mark SENT.
            relay.sendNext(false);
            System.out.println("simulated relay crash before marking SENT");

            // Lần 2: retry eventId cũ, consumer phải dedupe.
            relay.sendNext(true);

            System.out.println("final orders=" + ordersCount(jdbc) +
                " pending=" + outboxCount(jdbc, "PENDING") +
                " sent=" + outboxCount(jdbc, "SENT") +
                " consumerApplied=" + consumer.applied());
        }
    }

    private static int ordersCount(JdbcTemplate jdbc) {
        Integer result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM orders", Integer.class);
        return result == null ? 0 : result;
    }

    private static int outboxCount(JdbcTemplate jdbc, String status) {
        Integer result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM integration_outbox WHERE status=?",
            Integer.class, status);
        return result == null ? 0 : result;
    }

    private static void printState(String label, JdbcTemplate jdbc) {
        System.out.println(label + " orders=" + ordersCount(jdbc) +
            " pending=" + outboxCount(jdbc, "PENDING"));
    }

    public record IntegrationMessage(
        String eventId, String aggregateId,
        String eventType, String payloadJson) {
    }

    // Không final để Spring dùng class-based transaction proxy.
    public static class OrderWriter {
        private final JdbcTemplate jdbc;

        public OrderWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void place(String orderId, String eventId, boolean forceFail) {
            jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                orderId, "PLACED");

            // Demo dùng payload constant; production dùng JSON serializer.
            String payload = "{\"state\":\"PLACED\"}";

            jdbc.update(
                "INSERT INTO integration_outbox (" +
                "event_id, aggregate_id, aggregate_version, " +
                "event_type, schema_version, payload_json, " +
                "status, created_at) " +
                "VALUES (?, ?, ?, ?, ?, ?, 'PENDING', CURRENT_TIMESTAMP)",
                eventId, orderId, 1L, "OrderPlaced", 1, payload);

            if (forceFail) {
                throw new IllegalStateException("simulated rollback");
            }
        }
    }

    // Chỉ mô phỏng consumer trong cùng JVM, không durable sau restart.
    public static class CountingConsumer {
        private final Set<String> seenIds = new HashSet<>();
        private int applied;

        public void handle(IntegrationMessage message) {
            if (!seenIds.add(message.eventId())) {
                System.out.println(
                    "consumer duplicate event_id=" + message.eventId());
                return;
            }
            applied++;
            System.out.println(
                "consumer applied event_id=" + message.eventId());
        }

        public int applied() {
            return applied;
        }
    }

    // Stub, KHÔNG tương đương broker có durability/ack thật.
    public static class LocalBroker {
        private final CountingConsumer consumer;

        public LocalBroker(CountingConsumer consumer) {
            this.consumer = consumer;
        }

        public void publish(IntegrationMessage message) {
            System.out.println(
                "broker published event_id=" + message.eventId());
            consumer.handle(message);
        }
    }

    // Một relay duy nhất cho demo, không có lock/lease multi-worker.
    public static class PollingRelay {
        private final JdbcTemplate jdbc;
        private final LocalBroker broker;

        public PollingRelay(JdbcTemplate jdbc, LocalBroker broker) {
            this.jdbc = jdbc;
            this.broker = broker;
        }

        public boolean sendNext(boolean acknowledge) {
            List<IntegrationMessage> records = jdbc.query(
                "SELECT event_id, aggregate_id, event_type, payload_json " +
                "FROM integration_outbox WHERE status='PENDING' " +
                "ORDER BY created_at, event_id LIMIT 1",
                (rs, index) -> new IntegrationMessage(
                    rs.getString("event_id"),
                    rs.getString("aggregate_id"),
                    rs.getString("event_type"),
                    rs.getString("payload_json"))
            );

            if (records.isEmpty()) {
                return false;
            }

            IntegrationMessage message = records.get(0);
            broker.publish(message);

            if (acknowledge) {
                int affected = jdbc.update(
                    "UPDATE integration_outbox SET status='SENT' " +
                    "WHERE event_id=? AND status='PENDING'",
                    message.eventId());
                if (affected != 1) {
                    throw new IllegalStateException("ack conflict");
                }
            }
            return true;
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:integration_outbox_344;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public OrderWriter orderWriter(JdbcTemplate jdbc) {
            return new OrderWriter(jdbc);
        }
    }
}
~~~

### 8.4. Chạy

Đứng trong thư mục `integration-event-outbox`, dùng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.IntegrationOutboxDemo
~~~

Các dòng do code chương trình in (log phụ thuộc Maven/Spring/H2 có thể khác):

~~~text
after commit orders=1 pending=1
rollback cause=simulated rollback
after rollback orders=1 pending=1
broker published event_id=EVT-344
consumer applied event_id=EVT-344
simulated relay crash before marking SENT
broker published event_id=EVT-344
consumer duplicate event_id=EVT-344
final orders=1 pending=0 sent=1 consumerApplied=1
~~~

### 8.5. Phân tích kết quả

**T1 commit:** service `OrderWriter` là bean Spring, method `place(...)` được gọi qua transaction proxy, `JdbcTemplate` dùng cùng `DataSource`. Hai INSERT vào `orders` và `integration_outbox` cùng T1. Sau commit có một đơn và một outbox `PENDING`.

**T2 rollback:** service INSERT một đơn và một event mới, sau đó ném `IllegalStateException`. Unchecked exception làm T2 rollback theo quy tắc mặc định; hai bảng vẫn chỉ có row từ T1.

**Crash gap lần 1:** relay đọc outbox `PENDING`, stub broker gửi cho consumer. Vì `acknowledge=false`, trạng thái trong DB không được cập nhật. Đây là một **mô phỏng có chủ đích**; tiến trình demo thực sự chưa chết.

**Retry lần 2:** cùng row, cùng `eventId=EVT-344` được gửi lại. Consumer sử dụng `Set` để bỏ duplicate; kết quả `consumerApplied=1` dù broker publish hai lần. Relay đánh dấu `SENT`.

### Giới hạn rõ ràng của demo

- `LocalBroker` không phải Kafka/RabbitMQ/HTTP client và không có broker durability hay real ack.
- Consumer `HashSet` **mất dữ liệu sau restart**; production cần inbox/unique constraint bền.
- Relay chỉ có một worker và chưa có claim/lease; **không triển khai nguyên xi trong nhiều replica**.
- Không có exponential backoff, DLQ, batch processing, quarantine, message authentication, schema registry hay CDC.
- Code `OrderWriter` dùng eventId cố định do caller cung cấp cho output xác định. Production cần ID độc nhất cho mỗi event occurrence (thường UUID/ULID theo policy).
- Payload JSON cố định chỉ để demo; production phải dùng serializer được test thay vì nối chuỗi JSON từ input.

Kết luận từ ví dụ **không phải exactly-once delivery**, mà là: transaction local bảo vệ business/outbox atomicity; **retry có thể lặp**, nên consumer cần idempotency.

## 9. Thiết kế polling relay trong production

Một relay cần state machine, khả năng claim atomic và khả năng hồi phục:

~~~text
OUTBOX PENDING
   |
   +-- Worker claim ngắn, set PROCESSING + lease
   |
   +-- Gọi broker producer và chờ ack
        |
        +-- Thành công -> UPDATE SENT
        |
        +-- Lỗi tạm -> attempts++, next_retry_at, RETRY_PENDING
        |
        +-- Lỗi vĩnh viễn -> QUARANTINED / DLQ + alert
        |
        +-- Worker crash -> lease hết hạn, worker khác claim lại
~~~

Đừng chạy hai worker cùng một truy vấn `SELECT PENDING` rồi gửi không có lock. Hai worker có thể **gửi cùng message** trước khi một worker cập nhật trạng thái.

### Claim với PostgreSQL (tùy DB)

Ví dụ **ý tưởng PostgreSQL-specific**:

~~~sql
BEGIN;
SELECT event_id
FROM integration_outbox
WHERE status = 'PENDING'
ORDER BY created_at, event_id
FOR UPDATE SKIP LOCKED
LIMIT 100;

-- Với các event vừa chọn, UPDATE sang PROCESSING và gắn lease.
-- Commit transaction claim trước khi gọi broker.
COMMIT;
~~~

Cú pháp và thứ tự clause phải được kiểm tra theo phiên bản PostgreSQL/hệ DB đang dùng; đây là đoạn minh họa thiết kế, **không phải migration hoàn chỉnh**. Với production, chọn claim SQL được test thật: `FOR UPDATE SKIP LOCKED` hoặc conditional UPDATE/optimistic locking, cần index thích hợp.

**Không giữ transaction DB đang khóa rows xuyên một network call dài**. Claim trong transaction ngắn, commit claim, gọi broker, rồi update outcome trong transaction khác. Giữa broker ack và UPDATE SENT vẫn có crash gap: nếu không biết đã gửi hay chưa, **retry cùng eventId**. Đó là mô hình at-least-once có chủ đích.

### Lease và retry

Một bản ghi `PROCESSING` cần `lease_until`; nếu worker chết, job manager trả nó về trạng thái có thể claim. Cần xử lý trường hợp lease hết hạn khi worker vẫn đang gửi, dẫn tới gửi lặp — consumer vẫn phải dedupe.

Retry policy nên có:

- **Timeout** cho broker/API send, phân biệt timeout với definitive error.
- **Exponential backoff + jitter**, hạn chế thundering herd khi broker hồi phục.
- **Maximum attempts hoặc time budget** có chính sách quarantine/DLQ cho lỗi vĩnh viễn.
- **Last error class** hữu hạn cho metrics; log stack trace có kiểm soát.
- **Idempotent replay** với cùng `eventId`; không sinh ID mới cho retry.
- **Manual replay tooling** có audit và quyền hạn, tránh phát lại hàng loạt email/thanh toán.

Một alert “`oldest PENDING age` vượt SLO” hữu ích hơn chỉ nhìn tổng số rows.

## 10. CDC/Debezium khi muốn đọc commit log

Thay vì polling table, **change data capture (CDC)** đọc những record changes đã commit từ DB transaction log. **Debezium Outbox Event Router** giúp đổi outbox INSERT thành message ra Kafka.

Một kiến trúc:

~~~text
T1 COMMIT:
  business change + outbox INSERT
          |
       DB WAL / binlog
          |
   Debezium source connector
          |
   Outbox Event Router SMT
          |
      Kafka topic
          |
       Consumer
~~~

Tài liệu Debezium xác định mặc định:

- `id` là event ID ở message header.
- `aggregatetype` dùng để route topic.
- `aggregateid` là message key, hữu ích cho partition ordering.
- `type` là loại event.
- `payload` là nội dung event.

Nếu schema khác tên mặc định, cấu hình SMT mappings. Các trường như `schemaVersion`, correlation/tenant có thể đặt làm additional header hoặc envelope, phải quản lý compatibility.

**Không áp đặt cùng lúc polling mutable status table và CDC insert-only schema** mà không thiết kế rõ. Debezium Outbox Router giả định các outbox events được INSERT; bản cập nhật outbox row là operation không được mong đợi. CDC có cơ chế offsets/snapshot/log retention riêng; dữ liệu event chưa được consume/processed ở bên kia vẫn cần consumer idempotency.

### Chọn polling hay CDC

| Yếu tố | Polling | CDC |
|---|---|---|
| Hạ tầng | RDBMS + worker | RDBMS log capture + connector + broker |
| Thời gian phát hiện | Theo khoảng poll | Có thể gần realtime |
| Claim multi-worker | Worker tự quản lý | Connector/offset vận hành riêng |
| Retry state | `status/attempts/lease` trong DB | Connector/broker retry semantics |
| Schema | Có thể mutable | Nên tương thích SMT/insert-only |
| Tác động DB | Truy vấn và lock/index | Log streaming và retention |
| Phù hợp | Hệ thống nhỏ-vừa, cần dễ kiểm soát | Hệ thống đã vận hành CDC platform |

Cả hai không tự giải quyết exactly-once **business effect** ở consumer.

## 11. Consumer idempotency với inbox bền

Demo dùng `HashSet` để minh họa; production phải giả định:

1. Consumer đã apply event E1 thành công.
2. Consumer crash trước khi ACK broker.
3. Broker gửi lại E1 sau restart.
4. Consumer không được apply side effect lần hai.

Bảng inbox:

~~~sql
CREATE TABLE processed_integration_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(64) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Một transaction consumer:

~~~text
BEGIN T3
   INSERT processed_integration_events(consumer_name, event_id)
   - nếu duplicate key -> đã xử lý, không làm side effect lần hai
   UPDATE inventory_projection ...
COMMIT T3
ACK broker delivery
~~~

**Processed marker và business DB mutation phải commit nguyên tử trong cùng T3.** Nếu ghi marker vào DB trước rồi crash trước khi apply business effect (ở T4 khác), lần retry bị bỏ nhầm, gây mất tác dụng.

Ví dụ PostgreSQL:

~~~sql
INSERT INTO processed_integration_events(
    consumer_name, event_id, processed_at
) VALUES ('inventory', :eventId, CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

Đây là SQL PostgreSQL-specific; consumer kiểm tra affected rows. Nếu 0 là duplicate, có thể ACK theo policy; nếu 1, tiếp tục business update trong cùng transaction. Không ack message trước khi T3 commit. Nếu T3 commit xong nhưng ACK broker thất bại, message có thể quay lại; inbox bỏ duplicate.

### Side effect là email/API ngoài database thì sao?

Không có một local DB transaction nào tự làm gửi email hoặc gọi HTTP thành nguyên tử với marker. Cần idempotency key do phía API hỗ trợ, outbox ở service consumer, durable job status hoặc compensation. **Không tuyên bố exactly-once side effect** chỉ vì có bảng processed events.

## 12. Ordering: khi aggregate có nhiều events

Giả sử một đơn hàng có:

~~~text
OrderPlaced(orderId=ORD-344, version=1, eventId=E1)
OrderPaid(orderId=ORD-344, version=2, eventId=E2)
OrderShipped(orderId=ORD-344, version=3, eventId=E3)
~~~

Để giữ thứ tự có ý nghĩa:

- Dùng `aggregateId` làm message key phù hợp trên Kafka để các events của cùng aggregate thường được phân vào cùng partition.
- Cấp `aggregateVersion` bằng optimistic locking hoặc một cơ chế sequence trong transaction.
- Relay phải cân nhắc thứ tự gửi khi có nhiều instance, retry, lease; `ORDER BY created_at` **không chứng minh thứ tự commit** vì transactions có thể commit khác thứ tự tạo row.
- Consumer cần chống stale/out-of-order theo version và business invariants.
- Nếu một stream có version không liên tục do lọc event types, **không** bắt buộc quy tắc `incomingVersion == current+1` cho mọi event.

Ví dụ logic phù hợp với **stream version liên tục**:

~~~text
incomingVersion <= lastAppliedVersion -> duplicate / stale
incomingVersion == lastAppliedVersion + 1 -> apply
incomingVersion > lastAppliedVersion + 1 -> gap: buffer/retry/resync
~~~

Nếu aggregate version tăng ở các transaction không có integration event, cần contract ordering khác (event sequence riêng, lookup/resync). Không suy rằng UUID, timestamp hoặc DB auto-increment ID luôn là commit order tuyệt đối trong mọi điều kiện.

## 13. Nên dùng @EventListener, @TransactionalEventListener và Spring Modulith ở đâu?

### @EventListener cho domain logic nội bộ

Một domain event có thể kích hoạt các xử lý trong cùng process. Nếu muốn dùng `@EventListener` đồng bộ để ghi outbox **trong T1**, phải đảm bảo publisher thực sự ở trong T1, event listener không được `@Async`, multicaster không chuyển thread và exception không bị nuốt. Đó là nhiều giả định phải kiểm soát.

Đối với integration event bắt buộc, **ghi outbox trực tiếp trong application service/unit of work** thường dễ review và kiểm thử atomicity hơn.

### @TransactionalEventListener(AFTER_COMMIT) không phải original outbox writer

Không ghi outbox lần đầu sau commit của aggregate rồi kỳ vọng atomicity. Callback AFTER_COMMIT vẫn có crash gap giữa T1 và T2. Hãy dùng nó cho tác vụ không bắt buộc durable hoặc tín hiệu đánh thức relay, nhưng **relay luôn phải quét outbox durable**, không phụ thuộc hoàn toàn vào wake-up event in-memory.

Một optimization hợp lý:

~~~text
T1: ghi aggregate + outbox row -> COMMIT
    |
    +-- sau commit gửi wake-up signal cho relay
    |
    +-- relay cũng có scheduled poll fallback
~~~

Nếu wake-up signal bị mất, periodic poll vẫn quét được outbox đã commit.

### Spring Modulith Event Publication Registry

Spring Modulith có **Event Publication Registry** theo dõi publication tới transactional event listeners, ghi trạng thái để hỗ trợ phát lại incomplete publications tùy phiên bản/cấu hình. Đây là giải pháp đáng cân nhắc cho **reliable application-module events**.

Không đồng nhất Modulith registry với một integration outbox cho Kafka: muốn phát qua broker vẫn cần xác định serializer, message key, destination, delivery acknowledgment, retry và consumer idempotency. Có thể tích hợp các cơ chế nếu ownership rõ, nhưng tránh double-publish cùng event tới một downstream.

## 14. Test plan cho thiết kế integration outbox

Chỉ test happy path “có một row PENDING” là chưa đủ. Bộ test nên bao gồm ít nhất:

| ID | Tình huống | Assertion chính |
|---|---|---|
| T1 | Producer commit thành công | Có order row và đúng một outbox row, cùng business fact |
| T2 | Outbox INSERT lỗi sau order INSERT | Cả business write rollback |
| T3 | Service throw sau cả hai INSERT | Không có order/outbox của transaction rollback |
| T4 | JVM crash sau commit trước relay | Relay mới có thể đọc outbox còn PENDING |
| T5 | Broker gửi thành công nhưng mark SENT chưa chạy | Gửi lại cùng eventId, consumer không áp dụng lại |
| T6 | Hai relay workers claim cùng lúc | Row claim theo lock/lease đúng policy |
| T7 | Retry gặp network timeout | Backoff, không mark SENT quá sớm |
| T8 | Consumer ACK lỗi sau T3 commit | Redelivery được inbox dedupe |
| T9 | Consumer nhận version 3 trước version 2 | Không revert projection về state cũ |
| T10 | Event v1 còn pending khi deploy v2 | Deserialize/migrate tương thích |
| T11 | Broker downtime kéo dài | Queue age alert, storage capacity và DLQ hoạt động |
| T12 | Cleanup/retention | Chỉ xóa/archival rows an toàn, không mất PENDING |
| T13 | Consumer external API idempotency | Retry không gửi khoản thanh toán/email trùng |
| T14 | Multi-tenant isolation | Event tenant A không được xử lý/lookup dưới tenant B |

### Test transaction thật, không chỉ mock publisher

Một fake `ApplicationEventPublisher` có thể chứng minh method gọi `publishEvent`, nhưng **không chứng minh outbox row được commit nguyên tử với business**. Để xác minh atomicity, dùng Spring transaction manager và database thật hoặc test DB có semantics đủ gần.

Spring TestContext thường **rollback @Transactional test method** sau test. Để assert commit thật, để test method không transactional rồi gọi service proxy transactional, hoặc chủ động dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` khi test-managed transaction đang active.

`@RecordApplicationEvents`/`ApplicationEvents` trong spring-test cũng chỉ ghi events trong test; nó **không thay thế** việc assert outbox durable row, broker ack và consumer outcome.

## 15. Observability, SLO và vận hành

Một integration event đi qua nhiều mốc:

~~~text
Business COMMIT -> Outbox pending -> Relay claim
    -> Broker ACK -> Consumer received
    -> Consumer business transaction COMMIT -> ACK delivery
~~~

Mỗi mốc nên có trạng thái và metric tương ứng.

| Metric / tín hiệu | Ý nghĩa vận hành |
|---|---|
| `outbox.pending.count` | Số lượng events chưa gửi |
| `outbox.oldest.pending.age` | Tuổi event chờ lâu nhất; cảnh báo stuck relay |
| `outbox.relay.attempts` | Số lần thử gửi |
| `outbox.relay.failures` | Lỗi broker/serialization/credentials |
| `outbox.delivery.latency` | Từ lúc tạo row đến broker ack |
| `outbox.quarantine.count` | Events không thể xử lý tự động |
| `consumer.duplicate.count` | Tần suất redelivery/dedupe |
| `consumer.processing.latency` | Thời gian xử lý downstream |
| `consumer.processing.failures` | Failures sau khi nhận message |
| `consumer.lag` | Độ trễ còn tồn trong broker/partition |

Dashboard cần phân biệt: **producer committed**, **broker accepted**, **consumer processed** và **business effect completed**. `status=SENT` ở outbox chỉ cho biết relay tin rằng đã gửi theo ack policy, **không** chứng minh consumer nghiệp vụ đã hoàn tất.

Tránh `eventId`, `aggregateId`, email, số điện thoại làm **low-cardinality metric tags**. Dùng event type, relay, outcome và error category hữu hạn cho metrics; correlationId/traceId có thể dùng trong structured logs/traces theo chính sách bảo mật.

### SLO theo end-to-end

Ví dụ SLO (cần hiệu chỉnh theo nghiệp vụ):

- 99% integration events được broker ACK trong một khoảng thời gian đã thống nhất sau DB commit.
- 99% được consumer xử lý xong trong một khoảng khác.
- Không có outbox row `PENDING` quá ngưỡng tuổi mà không alert.
- Có playbook cho retry storm, connector lag, poison event và schema mismatch.

Đừng chọn SLO chỉ theo `@EventListener` duration; end-to-end integration còn bao gồm queueing, broker và consumer.

## 16. Security và retention

Outbox là dữ liệu có thể tồn tại lâu qua deploy và outage, nên cần quản trị như business data:

- **Payload tối thiểu:** không lưu token, password, số thẻ, PII nếu không thật sự cần.
- **Tenant isolation:** xác thực tenantId/aggregate ownership ở phía consumer; event header không tự chứng minh quyền.
- **Encryption và quyền DB/broker:** kiểm soát truy cập, key rotation và log redaction.
- **Schema registry:** định nghĩa compatibility của producer/consumer deploy độc lập.
- **Retention:** không xóa PENDING/PROCESSING đang cần retry chỉ vì cũ; archive SENT theo SLA.
- **Replay có audit:** manual replay cần quyền và theo dõi; idempotency cần bền ít nhất trong cửa sổ replay có thể xảy ra.
- **Backup/recovery:** khôi phục business và outbox nhất quán để không mất sự kiện đã được commit.
- **CDC WAL/binlog:** chính sách log retention/offset/snapshot phải đồng bộ với connector.
- **Backpressure:** khi broker down dài, DB outbox tăng; cần theo dõi disk, index bloat, vacuum/partitioning và throttling.

## 17. Bảng các lỗi thiết kế hay gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Coi Spring `publishEvent` như durable broker | Event có thể mất khi restart | Lưu outbox trong DB |
| Gửi message trước DB commit | Consumer nhận event cho transaction rollback | Outbox cùng T1, relay sau commit |
| Chỉ dùng `@TransactionalEventListener(AFTER_COMMIT)` | Crash gap sau commit vẫn tồn tại | Ghi durable outbox trước commit |
| Ghi original outbox trong AFTER_COMMIT | Outbox và business ở hai transactions | Ghi cùng T1 |
| Hai datasources nhưng coi là một transaction | Không atomic | Đặt outbox cùng DB hoặc kiến trúc khác |
| Nuốt exception INSERT outbox | Business commit không event | Rollback toàn bộ unit of work |
| `@Async` ghi outbox sau business INSERT | Tách ThreadLocal transaction | Ghi đồng bộ trong T1, async relay |
| Mark SENT trước broker ACK | Có thể mất event | Đợi ack thích hợp rồi mark; chấp nhận duplicate |
| Retry sinh eventId mới | Dedupe không hoạt động | Retry giữ eventId gốc |
| Consumer dedupe bằng aggregateId | Bỏ nhầm các event sau của cùng aggregate | Dedupe bằng eventId |
| Inbox và projection update không atomic | Crash có thể làm event bị bỏ nhầm | Cùng T3 |
| Nhiều relays đọc PENDING không claim | Double-send không kiểm soát | Lock/lease/atomic claim |
| Dùng created_at làm commit order tuyệt đối | Race transaction làm đảo thứ tự | Aggregate version và ordering contract |
| Dùng schema polling mutable với Debezium SMT | UPDATE không được mong đợi | Thiết kế schema CDC phù hợp |
| Chỉ nhìn `status=SENT` | Chưa biết consumer xử lý | Tách producer/broker/consumer metrics |
| Không có versioned contract | Event cũ không còn đọc được | Schema version/contract tests |
| Xóa PENDING theo retention cứng | Mất event chưa gửi | Cleanup theo state và SLA |
| Tin outbox mặc định exactly-once | Side effect vẫn có thể lặp | Consumer idempotency |

## 18. Checklist review một pull request triển khai outbox

1. Event name có nghĩa nghiệp vụ và ổn định không?
2. EventId/aggregateId/aggregateVersion/schemaVersion được xác định rõ chưa?
3. Payload là snapshot immutable và được serializer test chưa?
4. Business row và outbox row có dùng **cùng T1/resource** không?
5. Outbox INSERT lỗi có rollback business change không?
6. Có kiểm tra self-invocation và Spring transaction proxy không?
7. Relay là polling hay CDC, có owner rõ, không double-publish không?
8. Có lock/lease và recovery khi nhiều workers không?
9. Có retry giữ nguyên eventId, backoff, max attempts, quarantine không?
10. Broker ACK policy có rõ và không mark SENT trước ack không?
11. Consumer có durable inbox và idempotent side effect không?
12. Có ordering/version policy theo aggregate không?
13. Schema evolution và replay event cũ có được test không?
14. Có metrics backlog age, retries, failures, duplicate và consumer outcome không?
15. Có bảo vệ PII/tenant, retention/cleanup và replay authorization không?
16. Có fault-injection test rollback/crash-gap/duplicate/concurrent claim chưa?

## 19. Kết luận và tài liệu

**Thiết kế outbox cho integration event** không chỉ là thêm một bảng `outbox_events`. Đó là một hợp đồng end-to-end:

**Producer** ghi business state + event record trong **cùng local transaction**, **relay** chuyển event đã commit ra broker với retry và crash recovery, **consumer** áp dụng idempotency trong transaction của mình, và **vận hành** theo dõi latency, backlog, errors, schema evolution và replay.

Với Spring, `@EventListener` hữu ích cho domain events nội bộ, `@TransactionalEventListener(AFTER_COMMIT)` giúp chọn phase xử lý, nhưng **không thay thế atomic outbox INSERT trong T1**. Chọn polling hoặc Debezium CDC theo hạ tầng; phân biệt schema của hai hướng. Outbox đưa ra nền tảng **at-least-once delivery**; muốn đạt hiệu quả business “một lần” cần thêm eventId ổn định, inbox/idempotency, ordering và quy tắc side effect phù hợp.

### Tài liệu chính thức/tham khảo

- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): semantics của `@TransactionalEventListener`.
- [Spring Framework Reference — Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): transaction proxy, propagation, rollback rules.
- [Debezium — Outbox Event Router SMT](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): schema mặc định, key/header/topic routing, INSERT-only expectation.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): Event Publication Registry và incomplete event publications.
- [Microservices.io — Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): dual-write, relay, delivery semantics.
- [PostgreSQL Documentation — SELECT](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE` và `SKIP LOCKED` khi thiết kế polling workers.

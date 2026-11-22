# Đảm bảo không mất event quan trọng trong Spring Framework Application Events

## 1. Bài toán độ tin cậy: một event quan trọng không được chỉ nằm trong bộ nhớ

Giả sử ứng dụng đã commit trạng thái đơn hàng **PAID** nhưng event **OrderPaid** không tới hệ thống phát hành hóa đơn. Dữ liệu thanh toán đúng, song hóa đơn có thể không được tạo. Nếu event ngược lại được gửi **trước khi transaction commit** rồi database rollback, downstream có thể lập hóa đơn cho giao dịch chưa thực sự thành công.

Đây là **dual-write problem**: hai hành động cần nhất quán — cập nhật dữ liệu nghiệp vụ và công bố thông điệp — không thể được đảm bảo chỉ bằng cách gọi hai API liên tiếp.

Trong Spring Framework, **ApplicationEventPublisher.publishEvent(Object)** chủ yếu bàn giao một object cho cơ chế event listeners **trong application**. **@EventListener** đồng bộ mặc định thường chạy ngay trên thread publisher; **@Async** hoặc custom executor có thể tách việc sang thread khác. **@TransactionalEventListener(AFTER_COMMIT)** chọn đúng phase theo kết quả transaction, nhưng không tự tạo một hàng đợi bền vững. Cả ba cách không tự khôi phục event sau khi JVM chết.

Một thiết kế có độ tin cậy cao thường sử dụng:

1. **Transactional outbox**: cập nhật dữ liệu nghiệp vụ và ghi bản ghi cần phát trong **cùng DB transaction**.
2. **Outbox relay**: worker hoặc CDC đọc event đã commit, gửi đến broker/downstream và retry khi lỗi.
3. **At-least-once delivery**: cho phép redelivery vì crash có thể xảy ra sau khi gửi thành công nhưng trước ACK.
4. **Idempotent consumer**: không nhân đôi hiệu ứng nghiệp vụ dù nhận cùng event nhiều lần.
5. **Monitoring và reconciliation**: phát hiện event kẹt, đối chiếu trạng thái cuối và khôi phục có kiểm soát.

**Đừng hứa “không thể mất trong mọi hoàn cảnh”.** Nếu database chứa outbox mất dữ liệu đã được xác nhận commit, hoặc bản ghi pending bị xóa nhầm, outbox cũng không thể tự cứu. Bảo đảm thực tế phụ thuộc durability/backup/replication của database, ack của broker, vận hành và lỗi mà hệ thống cam kết chịu được.

## 2. Xác định event nào thật sự quan trọng

| Event | Tác động nếu mất | Hướng xử lý |
| --- | --- | --- |
| **OrderPaid** cần làm hóa đơn | Thanh toán đã ghi nhận nhưng hóa đơn vắng mặt | Transactional outbox, retry, consumer idempotent |
| **InventoryReserved** dùng trong checkout saga | Orchestrator không biết bước đã xong | Durable result event và workflow state |
| **AccountActivated** để đồng bộ quyền | Các hệ thống lệch trạng thái | Durable integration message, reconciliation |
| **AuditEntryRequired** cùng database | Thiếu bằng chứng nghiệp vụ | Ghi audit trong cùng DB transaction; dùng outbox nếu phát ra ngoài |
| **SearchIndexUpdateRequested** | Search hiển thị dữ liệu cũ | Tùy SLA: queue/replay hoặc rebuild/TTL |
| **MetricIncremented** | Thiếu một số telemetry | Best-effort có thể đủ, tránh outbox không cần thiết |

**Câu hỏi then chốt:** Nếu JVM dừng ngay sau khi business transaction commit, liệu hệ thống có còn thông tin bền vững để biết **phải gửi cái gì** hay không?

Một event Java thuần:

~~~java
public record OrderPaid(String orderId, String paymentId) {}
~~~

Chỉ là một **POJO payload**, không phải durable message. Tính immutable giúp biểu đạt sự thật nghiệp vụ, không đảm bảo event đã được ghi vào disk hoặc được broker nhận.

## 3. Những khoảng trống làm mất hoặc phát sai event

### 3.1. Publish trước commit: event có thể là sự thật chưa xảy ra

~~~text
BEGIN DB TRANSACTION
    UPDATE orders SET state = PAID
    publishEvent(OrderPaid)
       |
       +-- listener gọi email, HTTP hoặc broker
    business method ném lỗi
ROLLBACK DB
~~~

Với **@EventListener** đồng bộ mặc định, một side effect có thể đã xảy ra dù transaction sau đó rollback. Khi đó event không còn đại diện cho sự thật đã commit.

### 3.2. Commit trước rồi publish: crash window gây mất

~~~text
UPDATE orders -> COMMIT thành công
                   |
                   X JVM bị kill hoặc node dừng
                   |
              Chưa kịp publish OrderPaid
~~~

Không còn một bản ghi ổn định để biết cần gửi event. Dù đặt publication ngay sau câu lệnh save hoặc sau khi method transactional trả về, vẫn có khoảng trống nếu hai thao tác không có cơ chế liên kết bền vững.

### 3.3. AFTER_COMMIT không giải quyết độ bền sau commit

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterPayment(OrderPaid event) {
    invoiceClient.requestInvoice(event.orderId());
}
~~~

Đây là snippet; cần Spring-managed bean và các loại/imports liên quan. **AFTER_COMMIT** làm handler chờ commit thành công. Mặc định **fallbackExecution=false**, nên listener không chạy nếu event publish ngoài transaction phù hợp. Nhưng nếu database commit rồi JVM chết **trước callback hoặc giữa khi callback đang gọi remote API**, Spring không tự lưu lại callback để retry sau restart.

**AFTER_COMMIT** rất có ích để tránh phản ứng trước commit, nhưng không nên được xem là durable queue. Nếu có dùng để “đánh thức worker”, worker phải vẫn có khả năng quét **outbox bền vững** định kỳ.

### 3.4. @Async chỉ đổi thread, không đổi tính bền vững

~~~java
@Async
@EventListener
public void on(OrderPaid event) {
    invoiceClient.requestInvoice(event.orderId());
}
~~~

Snippet trên có thể đưa task vào queue **trong memory**. Nếu process chết khi task còn chờ, công việc mất. Exception trong void async method không tự truyền về caller; tăng số threads cũng không tạo khả năng phục hồi. **ApplicationEventPublisher** và executor không cung cấp broker ACK hay transaction chung với database.

### 3.5. Broker đã nhận nhưng ACK bị mất: có thể giao trùng

Nếu worker đã gửi thành công rồi chết **trước khi đánh dấu SENT**, lần khởi động sau nó sẽ gửi lại. Nếu client mất ACK dù broker đã lưu message, cũng có thể cần retry. Do đó chiến lược không mất event thường cần chấp nhận **at-least-once** và có **idempotent consumer**.

## 4. Giải pháp nền tảng: transactional outbox

### 4.1. Ghi business state và publication intent cùng transaction

~~~text
           Application service
                   |
                   | BEGIN
                   v
          +-------------------+
          | UPDATE orders     |
          | INSERT outbox     |
          +-------------------+
                   |
                  COMMIT
                   |
             Durable database
                   |
                   v
          Relay / poller / CDC
                   |
             send and ACK
                   |
                   v
             Message broker
                   |
             Deliver/retry
                   |
                   v
         Consumer + dedup/inbox
                   |
              Business effect
~~~

**Producer invariant:**

> Khi business state commit thành công, một **outbox record cho event cần phát** cũng phải commit; khi business transaction rollback, cả business state và outbox record phải rollback.

Điều kiện quan trọng là **cùng database transaction thực**. Nếu order được lưu trong DB A còn outbox ghi tại DB B mà không có protocol phù hợp, hai thao tác không tự nguyên tử. Nếu phần ghi outbox dùng **REQUIRES_NEW** và commit riêng trước khi business transaction lỗi, vẫn có thể có event phantom.

### 4.2. Schema outbox và nội dung cần lưu

Ví dụ schema kiến trúc:

~~~sql
CREATE TABLE outbox (
    event_id          VARCHAR(80) PRIMARY KEY,
    aggregate_type    VARCHAR(80) NOT NULL,
    aggregate_id      VARCHAR(80) NOT NULL,
    event_type        VARCHAR(120) NOT NULL,
    schema_version    INTEGER NOT NULL,
    payload           TEXT NOT NULL,
    state             VARCHAR(20) NOT NULL,
    attempts          INTEGER NOT NULL,
    created_at        TIMESTAMP NOT NULL,
    next_attempt_at   TIMESTAMP,
    last_error        TEXT,
    claimed_by        VARCHAR(80),
    claim_until       TIMESTAMP
);
~~~

Các trường đáng chú ý:

- **event_id**: ID duy nhất và **ổn định qua mọi retry** của cùng event, thường UUID/ULID.
- **aggregate_id / aggregate_type**: định danh business entity, giúp trace và giữ ordering khi cần.
- **event_type / schema_version**: contract integration, không dùng class Java serializable tùy tiện.
- **payload**: snapshot dữ liệu cần thiết, không chứa JPA EntityManager hoặc object mutable/lazy-loaded entity.
- **state**: ví dụ PENDING, IN_PROGRESS, SENT, PARKED.
- **attempts / next_attempt_at**: retry và backoff.
- **claimed_by / claim_until**: lease để phục hồi khi worker chết.
- **created_at / last_error**: giám sát, sửa lỗi và audit.

Đây là **schema tham khảo**, không phải bắt buộc mọi trường. Ví dụ runnable ở phần 7 dùng một schema rút gọn để tập trung vào atomicity, replay và idempotency.

### 4.3. @Transactional service mẫu

~~~java
@Service
public final class MarkOrderPaidService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    @Transactional
    public void markPaid(String orderId, String paymentId) {
        Order order = orders.load(orderId);
        order.markPaid(paymentId);
        orders.save(order);

        outbox.insert(
                IntegrationEvent.orderPaid(orderId, paymentId));
    }
}
~~~

**Đây là snippet kiến trúc**, chưa đủ imports/classes để biên dịch độc lập. Điểm mấu chốt là **orders.save** và **outbox.insert** dùng cùng transaction manager và connection/context phù hợp. Không ghi outbox từ một callback AFTER_COMMIT rồi cho rằng nó đã atomic với cập nhật order.

**Khuyến nghị:** Domain vẫn có thể tạo **OrderPaid** thuần Java; application/infrastructure map nó thành integration message và lưu outbox. Aggregate domain không cần inject trực tiếp Spring **ApplicationEventPublisher** hoặc Kafka client.

## 5. Relay gửi event: mark SENT đúng thời điểm

Một relay production thường làm:

1. Đọc những outbox rows đến hạn và claim chúng bằng cơ chế đồng thời phù hợp.
2. Gửi message với **eventId ổn định** và correlation/trace metadata cần thiết.
3. Chờ **broker ACK đáng tin cậy** hoặc kết quả xác nhận theo protocol.
4. Chỉ sau ACK mới cập nhật outbox thành SENT.
5. Nếu timeout/lỗi, cho phép retry với backoff. Không xóa record pending chỉ vì lần gửi đầu thất bại.
6. Nếu retry quá lâu, chuyển PARKED/DLQ và **báo cho người chịu trách nhiệm**, không âm thầm bỏ qua.

Nếu đánh dấu SENT trước khi broker lưu message, có thể mất vĩnh viễn. Nếu đánh dấu SENT sau ACK, có thể gửi trùng khi worker crash giữa hai hành động. Đây là trade-off cố hữu, nên consumer bắt buộc xử lý duplicate.

**Đừng nhầm send() trả Future với broker đã xác nhận.** Cần dùng chính xác ack/confirm semantics của Kafka/RabbitMQ/JMS/client được chọn.

### 5.1. Nhiều workers và claim/lease

Demo một worker có thể dùng SELECT PENDING; production nhiều worker cần concurrency control:

- **SELECT ... FOR UPDATE SKIP LOCKED**, hoặc CAS/optimistic locking tùy dialect.
- **Claim state + claim_until** để worker chết rồi record được xử lý tiếp.
- Transaction claim nên ngắn, tránh giữ DB lock mở khi chờ HTTP/broker network lâu.
- Các worker cần tránh starvation và lưu số attempt/next_attempt_at.
- Với event cùng aggregate, có thể cần partition/sequence để giữ thứ tự phù hợp.

Không copy SQL SKIP LOCKED giữa PostgreSQL, MySQL và H2 mà không xác minh hành vi transaction isolation/index. DB-specific SQL và worker leasing phải được integration test trên database thật.

## 6. Consumer idempotency để xử lý at-least-once

Giả sử cùng event **EVT-42** đến hai lần. Consumer lập hóa đơn chỉ nên tạo **một hóa đơn** nếu đó là invariant nghiệp vụ.

Mẫu thông dụng:

~~~text
BEGIN consumer transaction
  INSERT processed_messages(consumer_name, event_id)
      UNIQUE(consumer_name, event_id)
  IF đã có ID:
      không làm lại business side effect
  ELSE:
      INSERT invoice / UPDATE business state
COMMIT
ACK broker
~~~

**Processed marker và business effect trên DB phải cùng transaction.** Nếu marker đã commit trước mà invoice chưa được tạo, crash khiến retry tưởng event đã xử lý và bỏ qua. Ngược lại, invoice đã commit nhưng marker chưa commit thì retry có thể tạo trùng.

Ngoài event ID, **unique business key** như một invoice gốc trên mỗi order ID có thể bảo vệ trường hợp producer phát hai event IDs khác nhau cho cùng hành động. Với HTTP API như payment provider, cần **idempotency key phía provider**, state reconciliation và manual review khi timeout không biết kết quả. Inbox DB riêng không tự làm HTTP call exactly-once.

### 6.1. Ba mức độ bảo đảm thường bị lẫn

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **At-most-once** | Tránh redelivery nhưng có thể mất công việc |
| **At-least-once** | Retry để không bỏ sót khi hạ tầng phục hồi; có thể xử lý lặp |
| **Effectively-once effect** | Consumer idempotent làm kết quả nghiệp vụ chỉ xảy ra một lần dù thông điệp lặp |

Không nên tuyên bố **exactly-once end-to-end** chỉ vì producer dùng idempotent broker mode hoặc outbox relay có status SENT. Mỗi DB, broker, provider bên ngoài có ranh giới commit và failure modes khác nhau.

## 7. Demo Java 17+ chạy được: outbox bền vững, rollback và retry qua restart

Ví dụ dưới đây dùng **Spring Framework 6.2.9**, **Spring JDBC**, **H2 2.3.232**, **Java 17+** và **Gradle 8.x**. Nó không cần Spring Boot, server HTTP hay broker thật.

Ý tưởng:

1. Ghi **orders + outbox** trong một **TransactionTemplate** để commit/rollback.
2. Phát một Spring **OutboxWritten** event như tín hiệu quan sát; listener tức thời in ra trước commit, listener AFTER_COMMIT chỉ in ở nhánh commit.
3. Lưu database ở **H2 file** thay vì H2 in-memory để dữ liệu còn sau khi JVM kết thúc.
4. Relay xử lý **PENDING** và ghi vào **consumer_inbox** giả lập, rồi cố ý **mô phỏng crash trước ACK**.
5. Chạy lệnh lần sau, vẫn thấy pending outbox, consumer biết event đã nhận bằng **eventId**, không nhân đôi effect giả lập.

**Giới hạn:** Fake receiver và producer trong demo dùng cùng H2 file cho dễ thực hành. Chúng thực hiện hai transactions tách biệt, nhưng không mô phỏng broker, service độc lập, network partition hoặc crash thật. Code không triển khai claim/lease đa worker; chỉ chạy các modes tuần tự.

### 7.1. Cấu trúc và build

~~~text
reliable-spring-events/
  build.gradle
  src/main/java/demo/ReliableEventsDemo.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'org.springframework:spring-jdbc:6.2.9'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.ReliableEventsDemo'
}
~~~

### 7.2. File Java hoàn chỉnh

**src/main/java/demo/ReliableEventsDemo.java**:

~~~java
package demo;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public final class ReliableEventsDemo {

    public record OutboxWritten(String eventId) {}
    public record EventRow(String eventId, String payload) {}

    public static final class EventObservers {

        @EventListener
        public void immediate(OutboxWritten event) {
            System.out.println("event-now: " + event.eventId());
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OutboxWritten event) {
            // Tín hiệu gợi ý để worker quét outbox sớm.
            // Relay bên dưới KHÔNG phụ thuộc vào tín hiệu này.
            System.out.println("event-after-commit: " + event.eventId());
        }
    }

    public static final class Producer {
        private final JdbcTemplate db;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        public Producer(
                JdbcTemplate db,
                PlatformTransactionManager manager,
                ApplicationEventPublisher publisher) {
            this.db = db;
            this.tx = new TransactionTemplate(manager);
            this.publisher = publisher;
        }

        private int count(String sql, Object... args) {
            return db.queryForObject(sql, Integer.class, args);
        }

        public void reset() {
            db.update("DELETE FROM consumer_inbox");
            db.update("DELETE FROM outbox");
            db.update("DELETE FROM orders");
            System.out.println("reset: done");
        }

        public void rollback() {
            tx.executeWithoutResult(status -> {
                db.update(
                    "INSERT INTO orders (id, state) VALUES (?, ?)",
                    "ORD-ROLL", "PAID");
                db.update(
                    "INSERT INTO outbox "
                    + "(event_id, aggregate_id, payload, state, attempts) "
                    + "VALUES (?, ?, ?, ?, ?)",
                    "EVT-ROLL", "ORD-ROLL",
                    "OrderPaid:ORD-ROLL", "PENDING", 0);

                publisher.publishEvent(new OutboxWritten("EVT-ROLL"));
                status.setRollbackOnly();
            });

            System.out.println("rollback: orders="
                + count("SELECT COUNT(*) FROM orders WHERE id = ?",
                        "ORD-ROLL")
                + " outbox="
                + count("SELECT COUNT(*) FROM outbox WHERE event_id = ?",
                        "EVT-ROLL"));
        }

        public void produce() {
            tx.executeWithoutResult(status -> {
                db.update(
                    "INSERT INTO orders (id, state) VALUES (?, ?)",
                    "ORD-42", "PAID");
                db.update(
                    "INSERT INTO outbox "
                    + "(event_id, aggregate_id, payload, state, attempts) "
                    + "VALUES (?, ?, ?, ?, ?)",
                    "EVT-42", "ORD-42",
                    "OrderPaid:ORD-42", "PENDING", 0);
                publisher.publishEvent(new OutboxWritten("EVT-42"));
            });

            System.out.println("produce: order="
                + count("SELECT COUNT(*) FROM orders WHERE id = ?",
                        "ORD-42")
                + " pending="
                + count("SELECT COUNT(*) FROM outbox WHERE state = ?",
                        "PENDING"));
        }
    }

    public static final class Relay {
        private final JdbcTemplate db;
        private final TransactionTemplate tx;

        public Relay(
                JdbcTemplate db,
                PlatformTransactionManager manager) {
            this.db = db;
            this.tx = new TransactionTemplate(manager);
        }

        private int count(String sql, Object... args) {
            return db.queryForObject(sql, Integer.class, args);
        }

        public void status() {
            long attempts = db.queryForObject(
                "SELECT COALESCE(SUM(attempts), 0) FROM outbox",
                Long.class);
            System.out.println(
                "state: orders="
                + count("SELECT COUNT(*) FROM orders")
                + " pending="
                + count("SELECT COUNT(*) FROM outbox "
                        + "WHERE state = 'PENDING'")
                + " sent="
                + count("SELECT COUNT(*) FROM outbox "
                        + "WHERE state = 'SENT'")
                + " inbox="
                + count("SELECT COUNT(*) FROM consumer_inbox")
                + " attempts=" + attempts);
        }

        public void deliver(boolean interruptBeforeAck) {
            List<EventRow> pending = db.query(
                "SELECT event_id, payload FROM outbox "
                + "WHERE state = 'PENDING' ORDER BY event_id",
                (rs, n) -> new EventRow(
                    rs.getString("event_id"),
                    rs.getString("payload")));

            if (pending.isEmpty()) {
                System.out.println("relay: nothing pending");
                return;
            }

            EventRow event = pending.get(0);

            // Bản demo có một relay worker chạy tuần tự.
            db.update(
                "UPDATE outbox SET attempts = attempts + 1 "
                + "WHERE event_id = ? AND state = 'PENDING'",
                event.eventId());

            // Receiver giả lập: một transaction commit riêng.
            // Inbox row đại diện cho side effect được tạo một lần.
            boolean duplicate = tx.execute(status -> {
                int exists = count(
                    "SELECT COUNT(*) FROM consumer_inbox "
                    + "WHERE event_id = ?", event.eventId());
                if (exists > 0) {
                    return true;
                }
                db.update(
                    "INSERT INTO consumer_inbox "
                    + "(event_id, payload) VALUES (?, ?)",
                    event.eventId(), event.payload());
                return false;
            });

            System.out.println(
                "receiver: " + (duplicate ? "duplicate " : "new ")
                + event.eventId());

            if (interruptBeforeAck) {
                // Mô phỏng crash SAU receiver commit, TRƯỚC outbox ACK.
                System.out.println(
                    "relay: simulated crash after receiver commit, before ACK");
                status();
                return;
            }

            tx.executeWithoutResult(status -> {
                db.update(
                    "UPDATE outbox SET state = 'SENT' "
                    + "WHERE event_id = ? AND state = 'PENDING'",
                    event.eventId());
            });
            System.out.println("relay: marked SENT " + event.eventId());
            status();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                "jdbc:h2:file:./reliable_event_demo;DB_CLOSE_ON_EXIT=FALSE");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            JdbcTemplate db = new JdbcTemplate(ds);
            db.execute(
                "CREATE TABLE IF NOT EXISTS orders ("
                + "id VARCHAR(80) PRIMARY KEY,"
                + "state VARCHAR(20) NOT NULL)");
            db.execute(
                "CREATE TABLE IF NOT EXISTS outbox ("
                + "event_id VARCHAR(80) PRIMARY KEY,"
                + "aggregate_id VARCHAR(80) NOT NULL,"
                + "payload VARCHAR(400) NOT NULL,"
                + "state VARCHAR(20) NOT NULL,"
                + "attempts INTEGER NOT NULL)");
            db.execute(
                "CREATE TABLE IF NOT EXISTS consumer_inbox ("
                + "event_id VARCHAR(80) PRIMARY KEY,"
                + "payload VARCHAR(400) NOT NULL)");
            return db;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        EventObservers eventObservers() {
            return new EventObservers();
        }

        @Bean
        Producer producer(
                JdbcTemplate db,
                PlatformTransactionManager manager,
                ApplicationEventPublisher publisher) {
            return new Producer(db, manager, publisher);
        }

        @Bean
        Relay relay(JdbcTemplate db, PlatformTransactionManager manager) {
            return new Relay(db, manager);
        }
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "mode: reset|rollback|produce|relay-crash|relay-retry|status");
        }

        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Producer producer = context.getBean(Producer.class);
            Relay relay = context.getBean(Relay.class);

            switch (args[0]) {
                case "reset" -> producer.reset();
                case "rollback" -> producer.rollback();
                case "produce" -> producer.produce();
                case "relay-crash" -> relay.deliver(true);
                case "relay-retry" -> relay.deliver(false);
                case "status" -> relay.status();
                default -> throw new IllegalArgumentException(
                    "unknown mode: " + args[0]);
            }
        }
    }
}
~~~

### 7.3. Các lệnh chạy và kết quả kỳ vọng

Chạy lần lượt từ thư mục **reliable-spring-events**, với Java 17+ và Gradle 8.x đã cài. Mỗi lệnh **gradle run** là một lần thực thi chương trình riêng. H2 dùng file **reliable_event_demo.mv.db** để dữ liệu tồn tại qua những lần chạy liên tiếp.

~~~bash
gradle --console=plain -q run --args="reset"
gradle --console=plain -q run --args="rollback"
gradle --console=plain -q run --args="produce"
gradle --console=plain -q run --args="relay-crash"
gradle --console=plain -q run --args="relay-retry"
~~~

**Các dòng do Java in ra**, nhóm theo lệnh:

~~~text
reset: done

event-now: EVT-ROLL
rollback: orders=0 outbox=0

event-now: EVT-42
event-after-commit: EVT-42
produce: order=1 pending=1

receiver: new EVT-42
relay: simulated crash after receiver commit, before ACK
state: orders=1 pending=1 sent=0 inbox=1 attempts=1

receiver: duplicate EVT-42
relay: marked SENT EVT-42
state: orders=1 pending=0 sent=1 inbox=1 attempts=2
~~~

Các dòng trống chỉ phân tách output của năm lần chạy. Không tính những log khác do Gradle hoặc môi trường thêm vào.

**Phân tích kết quả:**

- **Rollback:** listener thông thường in ngay **event-now: EVT-ROLL**, nhưng transaction rollback nên database không còn order/outbox và listener AFTER_COMMIT không in event cho EVT-ROLL.
- **Produce:** order và outbox cùng commit. Listener AFTER_COMMIT in **event-after-commit: EVT-42** sau commit; outbox vẫn còn **PENDING**. Bản ghi này — không phải dòng log listener — là nguồn phục hồi.
- **Relay-crash:** fake receiver đã commit row **EVT-42** vào inbox, relay cố ý dừng trước khi mark SENT. Outbox vẫn pending, mô phỏng một crash window gây redelivery.
- **Relay-retry:** JVM mới đọc lại cùng H2 file, thấy pending record và gửi lại event ID cũ. Inbox nhận diện duplicate, không tạo row thứ hai. Relay đánh dấu SENT; **attempts=2**.
- Từ đây chạy thêm **gradle --console=plain -q run --args="status"** để thấy record đã SENT. Nếu chạy lại **produce** mà chưa **reset**, H2 sẽ báo vi phạm primary key cố định; đây là hành vi đúng của demo.
- **Độ bền được minh họa:** file H2 qua restart bình thường và khả năng retry. Chương trình **không** mô phỏng kernel crash/fsync loss, HA DB hay message broker ACK.

### 7.4. Bẫy của fake receiver trong demo

Câu lệnh **SELECT COUNT** rồi **INSERT** chỉ đúng trong kịch bản **một worker tuần tự**. Khi nhiều consumers cùng xử lý event, hai thread có thể đều thấy count=0. Production cần:

- **UNIQUE(consumer_name, event_id)** hoặc ràng buộc tương đương.
- **Atomic insert/upsert** theo DB dialect hoặc xử lý duplicate-key collision an toàn.
- Dedup marker và business DB effect trong **cùng transaction**.
- Với external side effect, idempotency của provider hoặc reconciliation.
- Không chỉ ghi inbox rồi trả ACK trước khi side effect thật đã thành công.

Ví dụ này không tuyên bố đảm bảo exactly-once xuyên broker và không nên copy nguyên Relay vào production.

## 8. Khi outbox vẫn không đủ: lỗi hạ tầng và vận hành

### 8.1. Database durability

Nếu database trả lời commit thành công nhưng cấu hình storage/replication có thể mất dữ liệu khi mất điện/leader failover, outbox có thể mất cùng business state hoặc xảy ra divergence. Cần kiểm tra **WAL/fsync, synchronous replication, backup, restore testing, RPO/RTO**. Không tự giả định H2 file demo có mức bảo đảm tương đương một production database HA.

### 8.2. Worker kẹt mãi vẫn là thất bại nghiệp vụ

Nếu outbox có record PENDING tồn tại 10 ngày mà không có alert, về kỹ thuật event chưa mất nhưng **workflow bị bỏ quên**. Hệ thống cần:

- **pending_count**, **oldest_pending_age**, **retry_count**, **publish_failure_rate**.
- **Broker ACK latency**, **consumer lag**, **DLQ/parked count**, **consumer deduplicated_total**.
- **Business completion lag**, ví dụ thời gian từ OrderPaid đến InvoiceCreated.
- Alert gắn SLA, escalation owner và quy trình redrive có audit.
- Chính sách không xóa row PENDING/IN_PROGRESS/PARKED trước khi được xử lý.

### 8.3. Reconciliation định kỳ

Một nhiệm vụ đối soát có thể tìm:

~~~text
Orders đang PAID
  nhưng chưa có InvoiceCreated/result
  sau ngưỡng thời gian nghiệp vụ cho phép
      |
      v
So sánh outbox, broker/consumer, hệ thống hóa đơn
      |
      +-- Retry/redrive theo eventId ổn định
      +-- Repair có audit
      +-- Manual review khi kết quả chưa rõ
~~~

Nếu outbox row đã mất do lỗi vận hành, đối soát **business state** có thể giúp tái dựng một công việc phục hồi, nhưng phải tránh tạo hai hóa đơn hoặc replay side effect vô kiểm soát.

### 8.4. Thứ tự theo aggregate

Với cùng một order:

~~~text
OrderCreated(version=1)
OrderPaid(version=2)
OrderRefunded(version=3)
~~~

Nếu nhiều relay workers và broker partitions, consumer có thể thấy events đảo thứ tự. Khi cần ordering, dùng **aggregateId** làm partition/ordering key, version/sequence, cách claim phù hợp và **state/version guards** ở consumer. Timestamp không tự chứng minh thứ tự commit tuyệt đối của nhiều concurrent transactions.

## 9. Kiểm thử độ tin cậy theo ranh giới lỗi

### 9.1. Producer atomicity

- Commit thành công: **order và outbox cùng tồn tại**.
- Rollback-only: **cả hai đều không tồn tại**.
- Exception sau khi ghi outbox nhưng trước commit: rollback cả hai.
- Đảm bảo hai repositories cùng transaction manager; không có REQUIRES_NEW ngoài ý muốn.
- Retry request cùng business operation không tạo hai bản ghi business/event sai.

### 9.2. Relay

- Worker chết trước publish: outbox còn và có thể retry.
- Broker mất kết nối: không mark SENT, có backoff.
- Broker nhận được message rồi ACK mất: retry với cùng eventId.
- Worker chết sau ACK trước mark SENT: có redelivery, consumer dedup.
- Worker chết sau khi claim: lease hết hạn và record được lấy lại.
- Nhiều workers: claim/CAS hoạt động, không xử lý đồng thời mất kiểm soát.
- Poison message: parked/DLQ có monitoring và runbook, không xóa âm thầm.

### 9.3. Consumer

- Cùng eventId được giao hai lần: **business side effect chỉ được commit một lần**.
- Crash trước consumer DB commit: inbox marker và business effect cùng rollback; retry được.
- Crash sau commit trước ACK: redelivery bị dedup.
- Hai event IDs cho cùng nghiệp vụ: business unique constraint bảo vệ.
- HTTP timeout: idempotency key và reconciliation, không retry mù.
- Out-of-order / replay: không áp dụng state transition lùi hoặc phát side effect cũ.

### 9.4. Test Spring event hooks

- **@EventListener** thường có thể chạy trước khi DB commit/rollback.
- **@TransactionalEventListener(AFTER_COMMIT)** chạy chỉ khi commit thành công và transaction phù hợp.
- Outside transaction: transactional listener mặc định không chạy, trừ **fallbackExecution=true**.
- Test method có **@Transactional** trong Spring TestContext thường mặc định rollback; dùng **TestTransaction.flagForCommit(); TestTransaction.end()** để kiểm chứng AFTER_COMMIT trong cùng test method.
- **Đừng chỉ verify publisher.publishEvent(...) được gọi** rồi tuyên bố event đã bền vững. Cần assert outbox DB row, kết quả commit/rollback và cả các crash windows.

## 10. Cách kết hợp Spring events với outbox

Một thiết kế sạch:

~~~text
domain/
   Order
   OrderPaid                       (domain event Java thuần)
application/
   MarkPaidUseCase
   OrderRepository, OutboxPort
infrastructure/
   JdbcOrderRepository
   JdbcOutboxWriter
   OutboxRelay / CDC publisher
   BrokerPublisher
   ConsumerInbox / invoice adapter
observability/
   eventId, aggregateId, traceId, retries, backlog age
~~~

**Spring ApplicationEventPublisher** vẫn có thể hỗ trợ observer nội bộ hoặc một **AFTER_COMMIT hint** giúp worker quét outbox sớm. Tuy nhiên nên luôn có **poller/CDC** khôi phục những bản ghi chưa gửi mà không cần hint. Không dùng in-memory callback làm nguồn dữ liệu duy nhất cho event quan trọng.

**Spring Modulith** có các khả năng liên quan tới lưu/tracking publication trong một số module và phiên bản; nếu chọn giải pháp đó, phải kiểm tra chính xác persistence configuration, retry/resubmission và phạm vi bảo đảm của phiên bản đang dùng. Không suy ra rằng một annotation bất kỳ thay thế được mọi công việc về durable broker delivery và consumer idempotency.

## 11. Lỗi phổ biến

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Publish ngay trong transaction và gửi side effect ngoài DB | Event phantom khi rollback | Ghi outbox cùng business transaction |
| Commit rồi gọi publish trong Java | Crash giữa hai thao tác làm mất event | Transactional outbox |
| Xem AFTER_COMMIT là durable queue | Callback vẫn mất nếu JVM chết | Durable outbox + poller/CDC |
| Chỉ dùng @Async để đảm bảo eventual delivery | Task memory có thể mất | Queue/outbox, retry |
| Mark SENT khi mới enqueue vào client memory | Broker chưa chắc nhận | Đợi broker ACK đủ mạnh |
| Gửi retry bằng eventId mới | Consumer không dedup được | Giữ eventId ổn định |
| Ghi processed marker trước side effect ở transaction khác | Crash tạo mất effect | Cùng local transaction cho inbox + DB effect |
| Dựa vào check-then-insert khi có nhiều consumers | Race condition | Unique constraint và atomic dedup |
| Cho rằng broker exactly-once bao hết DB/external API | Side effect vẫn trùng hoặc mất | Idempotency tại từng hệ thống |
| Business DB và outbox ở hai transaction độc lập | Không bảo đảm atomicity | Một transaction thực hoặc protocol rõ |
| Nhiều workers không claim/lease | Retry storm và race | Lock/CAS/lease, backoff |
| Không giám sát pending age | Event tồn tại nhưng mãi không được gửi | Metrics, alerts, runbook |
| Purge outbox pending | Mất bản ghi phục hồi | Retention, audit và repair |
| Không version schema | Consumer hỏng khi deploy | Event type/version và compatibility |
| Replay lịch sử gây gửi email/payment lại | Lặp side effect | Tách projections và side-effect policy |

## 12. Checklist triển khai

1. **Đã xác định event nào quan trọng và hậu quả nếu mất chưa?**
2. **Business state và outbox row có cùng transaction thật không?**
3. **Rollback có làm cả hai biến mất không?**
4. **Commit rồi JVM chết có còn outbox row để phát lại không?**
5. **Relay có đợi ACK đúng mức bảo đảm rồi mới mark SENT không?**
6. **Retry có giữ nguyên eventId không?**
7. **Consumer có dedup cùng transaction với DB effect không?**
8. **External API có idempotency/reconciliation không?**
9. **Nhiều workers có claim/lease/backoff không?**
10. **Có xử lý poison message, parked/DLQ và manual review không?**
11. **Có monitoring pending age, lag, retry và business completion không?**
12. **Có backup/replication/retention bảo vệ chính outbox đã commit không?**
13. **Có kiểm thử crash sau send trước ACK, rollback, duplicate, restart không?**
14. **Có phân biệt broker ACK với consumer business completion không?**

**Kết luận:** Để **không bỏ quên event quan trọng sau khi nghiệp vụ đã commit**, hãy lưu **outbox cùng database transaction với business state**, cho relay gửi và retry đến khi nhận xác nhận, chấp nhận **at-least-once**, và làm **consumer idempotent**. Spring **@EventListener**, **@Async** và **@TransactionalEventListener(AFTER_COMMIT)** vẫn hữu ích, nhưng không tự tạo durability. Độ tin cậy đến từ một chuỗi invariant và kiểm thử qua các failure windows, cộng với giám sát để xử lý các event bị kẹt.

### Tài liệu chính thức

- Spring Framework 6.2 — *Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework Javadoc 6.2.9 — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Javadoc 6.2.9 — *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework Javadoc 6.2.9 — *TransactionTemplate*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- H2 Database — *SQL commands and transaction behavior*: https://h2database.com/html/commands.html

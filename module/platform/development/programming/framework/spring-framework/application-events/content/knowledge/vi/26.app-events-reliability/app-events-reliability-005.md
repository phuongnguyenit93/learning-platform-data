# Event và Outbox Pattern trong Spring Framework Application Events

## 1. Bài toán: độ tin cậy khi phát event ra ngoài tiến trình

Trong Spring, `ApplicationEventPublisher.publishEvent(...)` và `@EventListener` giúp tách các module xử lý nghiệp vụ. Một service có thể lưu đơn hàng, phát `OrderPlaced` và để listener gửi email, cập nhật tìm kiếm hoặc tích hợp một hệ thống khác. Tuy nhiên, **Spring Application Events không phải durable message queue**: event chủ yếu được dispatch trong JVM và Spring Framework không tự ghi một bản event có thể replay sau crash.

Ví dụ quen thuộc:

~~~java
@Transactional
public void placeOrder(String orderId) {
    orderRepository.insert(orderId);
    eventPublisher.publishEvent(new OrderPlaced(orderId));
}
~~~

Đây là mẫu tích hợp, không phải một chương trình độc lập. Phải có `OrderPlaced`, repository, publisher và Spring transaction manager tương ứng.

Nếu một listener gửi message tới Kafka hoặc HTTP API, chương trình cần **hai thay đổi độc lập**: commit DB và gửi message. Chúng không tự trở thành một transaction nguyên tử chỉ vì method có `@Transactional`. Đây là **dual-write problem**.

Có hai cách sắp thứ tự dễ sai:

- **Gửi message trước DB commit:** broker nhận `OrderPlaced`, rồi DB rollback. Consumer có thể tin rằng đơn hàng tồn tại dù thực tế không có row committed.
- **DB commit trước, gửi message sau:** DB đã có đơn hàng, nhưng JVM crash trước khi gửi. Consumer không bao giờ nhận thông báo về thay đổi ấy.

**Transactional Outbox Pattern** thay trực tiếp gửi message bằng thao tác **INSERT một bản ghi outbox trong cùng local database transaction với dữ liệu nghiệp vụ**. Sau khi commit, một relay riêng sẽ gửi outbox ra broker. Nếu process chết, row outbox vẫn còn và có thể được gửi lại.

> Bảo đảm chính: business update và outbox event **commit cùng nhau hoặc rollback cùng nhau**. Relay thường gửi theo mô hình *at least once*, nên consumer phải chịu được duplicate. Outbox không tự hứa *exactly once end-to-end*.

### Mục tiêu của bài học

1. Hiểu vì sao `@EventListener` và `@TransactionalEventListener(AFTER_COMMIT)` không tự giải quyết dual-write durability.
2. Thiết kế transaction bao cả business row và outbox row.
3. Xây polling relay/CDC publisher có khả năng phục hồi khi crash.
4. Dùng `eventId` và inbox/idempotency để xử lý duplicate đúng.
5. Quản lý ordering/version, retry, schema, security, observability.
6. Chạy ví dụ Java 17 + Spring JDBC + H2 cho commit, rollback và resend sau crash gap.
7. Phân biệt Spring Modulith Event Publication Registry với outbox tích hợp broker.

## 2. Failure matrix: chuyện gì xảy ra nếu crash ở từng thời điểm?

Giả sử muốn tạo đơn `ORD-295` và thông báo cho hệ thống kho. Các tình huống:

| Thời điểm lỗi | Nếu gửi trực tiếp | Nếu dùng transactional outbox |
|---|---|---|
| Lỗi trước DB commit | Event có thể đã gửi dù DB rollback | Outbox row cũng rollback |
| DB commit thành công, crash trước gửi | Event có thể mất vĩnh viễn | Outbox row committed còn để relay |
| Relay đọc row nhưng broker tạm ngừng | Không có retry bền nếu chỉ callback in-memory | Row chờ retry, có attempts/backoff |
| Broker nhận nhưng producer không nhận ack | Gửi lại có thể tạo duplicate | Relay gửi lại cùng eventId; consumer dedupe |
| Worker crash sau gửi trước mark SENT | Không rõ đã gửi hay chưa | Row còn pending/lease hết hạn, retry |
| Consumer nhận message hai lần | Side effect có thể lặp | Idempotent consumer ngăn lặp theo eventId |

### Crash gap trong AFTER_COMMIT

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendToBroker(OrderPlaced event) {
    broker.send(event);
}
~~~

Đây là mã minh họa. `AFTER_COMMIT` chỉ đảm bảo callback được lên lịch theo phase sau khi transaction gốc commit; nó **không persist event trước commit**. Nếu crash sau commit nhưng trước callback, message vẫn có thể mất. Nếu callback ném exception, business row đã commit và không thể rollback transaction gốc bằng cách throw ở phase này.

**Kết luận:** `AFTER_COMMIT` là một **execution phase**, không phải durable outbox.

## 3. Kiến trúc transactional outbox

~~~text
Client / HTTP request
        |
        v
Spring OrderService.placeOrder()
        |
        +-- BEGIN T1 (local JDBC/JPA transaction)
        |      |
        |      +-- INSERT/UPDATE orders
        |      |
        |      +-- INSERT outbox_events
        |      |
        |      +-- COMMIT T1
        |            |
        |            +-- Nếu rollback: cả hai thay đổi biến mất
        |
        v
Database: orders + outbox_events (durable)
        |
        +--> Polling relay hoặc Debezium CDC
                  |
                  +-- claim/đọc event đã commit
                  +-- gửi broker, chờ ack
                  +-- lỗi thì retry
                  |
                  v
             Broker / API
                  |
                  v
            Consumer service
                  |
                  +-- dedupe eventId trong durable inbox
                  +-- apply business side effect
                  +-- ack message
~~~

Có ba đơn vị trách nhiệm:

**Producer transaction** ghi aggregate và outbox **vào cùng transaction vật lý và cùng database/resource**. Đây là chỗ nhận được tính nguyên tử. Nếu business DB là A nhưng outbox đặt ở DB B và không có transaction coordinator, bài toán dual-write vẫn còn.

**Relay** chuyển event đã commit ra broker/API; nó phải xử lý lỗi tạm thời, process restart, lock/lease nhiều worker, retries và cleanup. Relay không phải thành phần nghiệp vụ chịu trách nhiệm quyết định một đơn hàng hợp lệ hay không.

**Consumer** kiểm tra event contract, chống lặp, xử lý ordering và side effect theo transaction của chính nó. Một message được broker xác nhận chưa chứng minh consumer đã xử lý thành công.

## 4. Thiết kế schema outbox

Bảng polling minh họa:

~~~sql
CREATE TABLE orders (
    id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE outbox_events (
    event_id VARCHAR(36) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(64) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    schema_version INT NOT NULL,
    payload_json VARCHAR(4000) NOT NULL,
    status VARCHAR(16) NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    next_retry_at TIMESTAMP NULL,
    published_at TIMESTAMP NULL
);

CREATE INDEX idx_outbox_status_retry
    ON outbox_events(status, next_retry_at, created_at);
~~~

Đây là schema ví dụ để giải thích polling. DB production có thể dùng `UUID`, `JSONB`, `CLOB`, timestamp with timezone, partitioning hoặc index khác. Cần thiết kế dựa trên throughput, retention, query plan và SQL dialect thật.

| Cột | Ý nghĩa |
|---|---|
| `event_id` | ID **một occurrence event**, dùng dedupe |
| `aggregate_type` | Loại nguồn, ví dụ `Order` |
| `aggregate_id` | Khóa đối tượng nghiệp vụ; có thể làm partition key |
| `aggregate_version` | Phiên bản aggregate, hữu ích cho ordering |
| `event_type` | `OrderPlaced`, `OrderPaid`, v.v. |
| `schema_version` | Phiên bản cấu trúc payload |
| `payload_json` | Event snapshot/delta tối thiểu, serializable |
| `status` | `PENDING`/`PROCESSING`/`SENT` cho polling |
| `attempts` và `next_retry_at` | Lịch sử retry và thời điểm thử tiếp |
| `created_at` | Thời điểm tạo row, không chắc là commit sequence |
| `published_at` | Relay xác nhận đã gửi, không đồng nghĩa consumer đã hoàn tất |

Một event payload tham khảo:

~~~json
{
  "eventId": "16d9e1e5-a625-4bcb-9223-5d127c7b91db",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "ORD-295",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-11T06:40:00Z",
  "data": {
    "state": "PLACED",
    "currency": "VND",
    "totalMinorUnits": 350000
  }
}
~~~

Đây là dữ liệu giả định. `occurredAt` không chứng minh thứ tự DB commit tuyệt đối. Tránh dùng `entity.toString()`, proxy JPA hoặc secret/PII không cần thiết làm payload. Các field mà consumer cần dùng theo trạng thái **lúc event xảy ra** nên là snapshot bất biến, không chỉ một entity ID nếu đọc lại DB có thể thấy phiên bản khác.

### Phân biệt eventId và aggregateId

`ORD-295` có thể phát nhiều event:

~~~text
OrderPlaced(eventId=E1, aggregateId=ORD-295)
OrderPaid(eventId=E2, aggregateId=ORD-295)
OrderShipped(eventId=E3, aggregateId=ORD-295)
Retry OrderPaid(eventId=E2, aggregateId=ORD-295)
~~~

Consumer phải nhận `E1`, `E2`, `E3`; lần `E2` lặp được bỏ qua. Nếu dedupe bằng aggregateId, hệ thống sẽ bỏ nhầm mọi sự kiện sau lần đầu của cùng đơn. Retry **giữ nguyên eventId**; một event nghiệp vụ mới cần eventId mới.

## 5. Ghi outbox cùng business transaction trong Spring

Mẫu rõ ràng nhất là ghi hai row trực tiếp bên trong Spring transactional service:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders, OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void place(CreateOrder command) {
        Order order = orders.create(command);
        outbox.insert(new OutboxMessage(
            UUID.randomUUID(),
            "Order",
            order.id(),
            order.version(),
            "OrderPlaced",
            1,
            serialize(order)
        ));
    }
}
~~~

Đây là **mã tích hợp minh họa**, cần định nghĩa các class, serializer, repositories, transaction manager và imports phù hợp. Trong một unit of work:

- Nếu `orders.create` lỗi, outbox không commit.
- Nếu `outbox.insert` lỗi và exception khiến transaction rollback, orders không commit.
- Nếu transaction commit thành công, **hai row cùng tồn tại bền vững**.
- Relay gửi sau commit; không phụ thuộc vào request thread còn sống hay không.

### Không đưa outbox INSERT sang AFTER_COMMIT

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPlaced event) {
    outbox.insert(event); // Không nằm trong T1 đã commit.
}
~~~

Đây là **phản ví dụ cho atomic outbox**. Khi callback chạy, transaction đã commit. Một `REQUIRES_NEW` ở đây chỉ tạo T2 độc lập; crash giữa T1 và T2 vẫn làm mất event. Nếu dùng resource transaction cũ ở completion, thao tác ghi có thể không có một commit tiếp theo. Outbox row phải ghi **trước commit T1**.

### Có thể dùng @EventListener thường để ghi outbox không?

Có thể, nếu `@EventListener` **thật sự đồng bộ** và `outbox.insert` tham gia **đúng T1**, event được publish khi T1 còn mở. Nhưng cần kiểm soát việc bean có được gọi, multicaster có chuyển thread không, exception có bị `ErrorHandler` nuốt không và transaction manager có đúng resource không.

Với invariant độ tin cậy bắt buộc, gọi outbox writer trực tiếp từ service hoặc domain unit of work thường **dễ chứng minh và kiểm thử** hơn một đường dispatch có thể bị cấu hình async.

## 6. Ví dụ chạy được Java 17 / Maven / Spring JDBC / H2

Ví dụ tạo hai transaction, sau đó mô phỏng relay gửi một message thành công rồi crash trước khi đánh dấu SENT. Một consumer đơn giản dùng `eventId` để bỏ qua bản trùng.

**Mục đích:** minh họa atomic write, rollback và at-least-once/dedupe. `StubBroker` không phải Kafka thực; `HashSet` consumer chỉ có trạng thái trong bộ nhớ. Code không thay thế thiết kế production cho nhiều worker.

Cấu trúc:

~~~text
outbox-demo/
├── pom.xml
└── src/main/java/demo/OutboxDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>outbox-demo</artifactId>
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

### src/main/java/demo/OutboxDemo.java

~~~java
package demo;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

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

public final class OutboxDemo {

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            OrderService service = ctx.getBean(OrderService.class);

            jdbc.execute("CREATE TABLE orders (" +
                "id VARCHAR(64) PRIMARY KEY, state VARCHAR(20) NOT NULL)");

            jdbc.execute("CREATE TABLE outbox_events (" +
                "event_id VARCHAR(36) PRIMARY KEY, " +
                "aggregate_id VARCHAR(64) NOT NULL, " +
                "event_type VARCHAR(64) NOT NULL, " +
                "payload_json VARCHAR(1024) NOT NULL, " +
                "status VARCHAR(16) NOT NULL, " +
                "created_at TIMESTAMP NOT NULL)");

            // Cả hai INSERT cùng commit trong T1.
            service.createOrder("ORD-295", false);
            printState("after commit", jdbc);

            // Cả hai INSERT cùng rollback trong T2.
            try {
                service.createOrder("ORD-ROLLBACK", true);
            } catch (IllegalStateException e) {
                System.out.println("rollback cause=" + e.getMessage());
            }
            printState("after rollback", jdbc);

            Consumer consumer = new Consumer();
            BrokerStub broker = new BrokerStub(consumer);
            Relay relay = new Relay(jdbc, broker);

            // Giả lập crash sau broker send nhưng trước outbox ack.
            relay.sendNext(false);
            System.out.println("simulated crash before ack");

            // Retry lại đúng eventId cũ, consumer chống trùng.
            relay.sendNext(true);

            System.out.println("final: pending=" + count(jdbc, "PENDING") +
                " sent=" + count(jdbc, "SENT") +
                " applied=" + consumer.appliedCount());
        }
    }

    private static void printState(String label, JdbcTemplate jdbc) {
        Integer orders = jdbc.queryForObject(
            "SELECT COUNT(*) FROM orders", Integer.class);
        System.out.println(label + ": orders=" + orders +
            " pending=" + count(jdbc, "PENDING"));
    }

    private static int count(JdbcTemplate jdbc, String status) {
        Integer value = jdbc.queryForObject(
            "SELECT COUNT(*) FROM outbox_events WHERE status=?",
            Integer.class, status);
        return value == null ? 0 : value;
    }

    public record OutboxRow(
            String eventId, String aggregateId,
            String eventType, String payloadJson) {
    }

    // Class không final để class-based Spring proxy hoạt động.
    public static class OrderService {
        private final JdbcTemplate jdbc;

        public OrderService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void createOrder(String id, boolean fail) {
            jdbc.update("INSERT INTO orders(id, state) VALUES (?, ?)",
                id, "PLACED");

            // Payload cố định cho demo; production dùng JSON serializer.
            String payload = "{\"state\":\"PLACED\"}";

            jdbc.update(
                "INSERT INTO outbox_events " +
                "(event_id, aggregate_id, event_type, " +
                "payload_json, status, created_at) " +
                "VALUES (?, ?, ?, ?, 'PENDING', CURRENT_TIMESTAMP)",
                UUID.randomUUID().toString(), id, "OrderPlaced", payload);

            if (fail) {
                throw new IllegalStateException("force rollback");
            }
        }
    }

    // Broker stub đồng bộ, chỉ dùng để quan sát demo.
    public static class BrokerStub {
        private final Consumer consumer;

        public BrokerStub(Consumer consumer) {
            this.consumer = consumer;
        }

        public void send(OutboxRow row) {
            System.out.println("broker delivered type=" +
                row.eventType() + " aggregate=" + row.aggregateId());
            consumer.receive(row);
        }
    }

    // Consumer Set chỉ là ví dụ: restart sẽ mất dedupe state.
    public static class Consumer {
        private final Set<String> processed = new HashSet<>();
        private int applied;

        public void receive(OutboxRow row) {
            if (!processed.add(row.eventId())) {
                System.out.println("consumer duplicate skipped aggregate=" +
                    row.aggregateId());
                return;
            }
            applied++;
            System.out.println("consumer applied aggregate=" +
                row.aggregateId());
        }

        public int appliedCount() {
            return applied;
        }
    }

    // Relay một worker: chưa có atomic claim/lease.
    public static class Relay {
        private final JdbcTemplate jdbc;
        private final BrokerStub broker;

        public Relay(JdbcTemplate jdbc, BrokerStub broker) {
            this.jdbc = jdbc;
            this.broker = broker;
        }

        public boolean sendNext(boolean acknowledge) {
            List<OutboxRow> pending = jdbc.query(
                "SELECT event_id, aggregate_id, event_type, payload_json " +
                "FROM outbox_events WHERE status='PENDING' " +
                "ORDER BY created_at, event_id LIMIT 1",
                (rs, index) -> new OutboxRow(
                    rs.getString("event_id"),
                    rs.getString("aggregate_id"),
                    rs.getString("event_type"),
                    rs.getString("payload_json"))
            );
            if (pending.isEmpty()) {
                return false;
            }

            OutboxRow row = pending.get(0);
            broker.send(row);

            if (acknowledge) {
                int changed = jdbc.update(
                    "UPDATE outbox_events SET status='SENT' " +
                    "WHERE event_id=? AND status='PENDING'",
                    row.eventId());
                if (changed != 1) {
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
            ds.setURL("jdbc:h2:mem:outbox295;DB_CLOSE_DELAY=-1");
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
        public OrderService orderService(JdbcTemplate jdbc) {
            return new OrderService(jdbc);
        }
    }
}
~~~

### Chạy

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.OutboxDemo
~~~

Các dòng do chương trình chủ động in, theo thứ tự mong đợi:

~~~text
after commit: orders=1 pending=1
rollback cause=force rollback
after rollback: orders=1 pending=1
broker delivered type=OrderPlaced aggregate=ORD-295
consumer applied aggregate=ORD-295
simulated crash before ack
broker delivered type=OrderPlaced aggregate=ORD-295
consumer duplicate skipped aggregate=ORD-295
final: pending=0 sent=1 applied=1
~~~

### Giải thích kết quả

**Thành công:** Spring AOP transaction proxy mở T1. `JdbcTemplate` ghi cả bảng orders và outbox trên cùng `DataSource`/transaction manager. Khi service trả về, T1 commit; số orders và pending đều là 1.

**Rollback:** T2 ghi cả hai bảng rồi ném `IllegalStateException`. Transaction interceptor rollback T2; `ORD-ROLLBACK` không có record business và outbox. Hai count sau rollback không đổi.

**Lần gửi đầu:** relay đọc row `PENDING` và gửi tới broker stub, consumer ghi nhận event ID. Vì `acknowledge=false`, relay không cập nhật trạng thái, mô phỏng crash sau send trước ack.

**Lần gửi thứ hai:** row vẫn `PENDING` nên relay gửi lại **cùng eventId**. Consumer nhận diện duplicate bằng `HashSet`, bỏ side effect; relay cập nhật `SENT`. Consumer applied count vẫn bằng 1.

### Giới hạn của ví dụ

- Không có Kafka, ack network, rebalance, offset hay durable broker.
- Consumer `HashSet` là in-memory; hệ thống thật phải dùng **durable processed_events table**, unique constraint/idempotency key.
- Relay không lock và chỉ giả định một worker; nhiều replica cần row claim/lease.
- SQL không quản lý backoff, retries, retention, DLQ, schema version hay migrations.
- Không chứng minh exactly-once end-to-end. Nó chỉ minh họa các failure windows và cơ chế bảo vệ cần có.
- Payload JSON là chuỗi cố định cho demo. Trong ứng dụng thật phải dùng Jackson/serializer đúng schema, không nối input tùy ý thành JSON.

## 7. Polling relay trong production: claim, retry, lease

Polling publisher thường làm việc theo vòng:

~~~text
1. SELECT events sẵn sàng gửi
2. Claim bằng transaction/lock/lease ngắn
3. Gửi broker, chờ xác nhận delivery thích hợp
4. Thành công -> mark SENT
5. Lỗi -> attempts++, next_retry_at, last_error
6. Crash trong PROCESSING -> lease hết hạn, worker khác retry
7. Cleanup/archival có kiểm soát sau khi SENT
~~~

Không nên chạy nhiều relay cùng thực hiện:

~~~java
// Phản ví dụ với hai worker chạy đồng thời:
List<Event> events = findPending();
for (Event event : events) {
    broker.send(event);
    markSent(event);
}
~~~

Hai worker có thể cùng đọc một row `PENDING`, cùng gửi trước khi bất kỳ worker nào đánh dấu. Đây là một lý do duplicates vẫn phải được chấp nhận.

### Claim an toàn hơn

Các kỹ thuật:

- `SELECT ... FOR UPDATE SKIP LOCKED` trên DB có hỗ trợ, trong **transaction claim ngắn**.
- Atomic `UPDATE status='PROCESSING' WHERE status='PENDING'`, kiểm tra số affected rows.
- Lease `claimed_by`, `lease_until` để hồi phục khi worker crash.
- Optimistic locking bằng version.
- Định tuyến partition để giảm cạnh tranh.

Ví dụ **PostgreSQL-specific**, không phải SQL demo H2:

~~~sql
BEGIN;

SELECT event_id
FROM outbox_events
WHERE status = 'PENDING'
ORDER BY created_at, event_id
LIMIT 100
FOR UPDATE SKIP LOCKED;

-- Claim các event đã chọn thành PROCESSING, ghi lease owner/expiry
-- trong cùng transaction ngắn.
COMMIT;
~~~

Không giữ transaction khóa DB mở xuyên suốt thời gian gọi broker có thể rất lâu. Claim và ack là hai transaction riêng, nên crash gap vẫn tồn tại và consumer idempotency vẫn bắt buộc.

### Chính sách retry

| Lỗi | Hành động phù hợp |
|---|---|
| Network timeout, broker tạm ngừng | Exponential backoff với jitter và retry |
| Rate limiting/HTTP 429 | Tôn trọng throttling/Retry-After khi có |
| Payload không serializable | Quarantine, DLQ, alert; không retry vô hạn |
| Auth/cert/permission | Khắc phục cấu hình rồi retry có kiểm soát |
| Message đã gửi nhưng ack không rõ | Có thể gửi lại **cùng eventId** |
| Consumer business error vĩnh viễn | DLQ hoặc quy trình manual resolution |

**Chỉ mark SENT sau khi tiêu chí broker ack phù hợp được đáp ứng.** Mark trước send có nguy cơ mất message; mark sau send có nguy cơ duplicate. Outbox chọn khả năng **không mất** và buộc consumer chống lặp.

## 8. CDC / Debezium Outbox Event Router

**Polling** đọc bảng outbox định kỳ. Cách thứ hai là **transaction log tailing / CDC**: connector như Debezium đọc các thay đổi đã commit từ transaction log của DB và chuyển bản ghi ra broker. Debezium có **Outbox Event Router SMT** (single message transformation).

Schema mặc định được tài liệu Debezium Outbox Router sử dụng gồm:

| Field mặc định | Ý nghĩa |
|---|---|
| `id` | Event ID; đưa vào message header |
| `aggregatetype` | Routing tới topic theo loại aggregate |
| `aggregateid` | Message key; hữu ích cho Kafka partition ordering |
| `type` | Event type |
| `payload` | Nội dung event gửi tới consumer |

**Không nhầm schema CDC mặc định với schema polling ở mục 4.** Nếu dùng tên cột khác, phải cấu hình mapping tương ứng. Debezium Outbox Router mặc định giả định bảng outbox chứa những **INSERT event records**; update trạng thái các rows như polling có thể bị xem là invalid operation. Không mang nguyên thiết kế `status=PENDING→SENT` vào CDC Outbox SMT nếu chưa đối chiếu tài liệu và cấu hình.

### So sánh

| Tiêu chí | Polling publisher | Debezium CDC |
|---|---|---|
| Cách phát hiện event | Query rows pending | Đọc commit log của DB |
| Độ trễ | Theo polling interval | Có thể gần real-time |
| Tác động database | Query/index/locking | Log capture và connector |
| State retry | Do relay app quản lý | Connector offsets/broker/consumer |
| Hạ tầng | Có thể đơn giản hơn | Cần CDC, connector, broker |
| Tính bền | Có outbox row + retry | Có commit log/connector + retry |
| Exactly-once business effect | Không tự bảo đảm | Không tự bảo đảm |

Với CDC, phải quản lý connector snapshot, offsets, log retention, schema history, cleanup outbox và quyền DB. CDC không làm mất yêu cầu dedupe ở consumer vì kết quả delivery có thể bị lặp trong các failure modes của hệ thống.

## 9. Consumer idempotency bền vững

Một consumer không nên chỉ dùng `Set` như demo. Sau restart, Set mất trạng thái, khiến event đã xử lý được áp dụng lại.

Lưu dấu event theo consumer:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Thiết kế tiêu chuẩn cho side effect DB:

~~~text
BEGIN T2
  INSERT processed_events(consumer_name, event_id, processed_at)
  - Nếu duplicate key: nhận diện đã xử lý và không áp dụng lại
  UPDATE downstream_projection(...), hoặc ghi bảng side effect nghiệp vụ
COMMIT T2
ACK broker message
~~~

Điểm then chốt: **insert dấu processed và business effect phải trong cùng T2**. Nếu ghi processed ở T2 rồi business effect ở T3, crash giữa chúng khiến lần redelivery bị bỏ nhầm.

Ví dụ PostgreSQL:

~~~sql
INSERT INTO processed_events(consumer_name, event_id, processed_at)
VALUES ('billing', :eventId, CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

SQL trên là **dialect-specific**. Consumer kiểm tra số hàng insert: 1 nếu mới, 0 nếu đã tồn tại; thực hiện cùng transaction với thay đổi business. Nếu downstream side effect là email hoặc API bên ngoài, không thể atomic với local DB. Cần idempotency key ở đích, outbox bước tiếp hoặc cơ chế compensation.

### Broker acknowledgment và consumer processing

Đừng ack broker trước khi thay đổi downstream của consumer đã commit. Nếu ack quá sớm rồi consumer crash, có thể mất tác vụ. Nếu commit xong rồi crash trước ack, broker có thể gửi lại; inbox sẽ bỏ duplicate.

**Broker ack của producer** khác **ack của consumer** và khác **đã xử lý business effect**. Dashboard cần tách ba khái niệm.

## 10. Ordering: aggregateId, version và nhiều event

Outbox đảm bảo có bản ghi để relay, không tự đảm bảo tất cả consumer xử lý đúng thứ tự cuối cùng nếu có parallelism, retries, partitions hoặc nhiều producers.

~~~text
OrderPlaced(aggregate=ORD-295, version=1)
OrderPaid(aggregate=ORD-295, version=2)
OrderShipped(aggregate=ORD-295, version=3)
~~~

Các biện pháp:

1. Dùng `aggregateId` làm key gửi Kafka để events cùng aggregate thường cùng partition **khi mapping nhất quán**.
2. Thêm `aggregateVersion` hoặc sequence được cấp trong transaction của aggregate.
3. Dùng optimistic locking để tránh concurrent writers cấp version trùng.
4. Consumer lưu lastAppliedVersion và xử lý stale/gap theo contract.
5. Thiết kế relay dựa trên thứ tự commit/sequence phù hợp; `created_at` không chứng minh commit order tuyệt đối.
6. Nếu nhiều types/streams cùng aggregate, version tăng có thể không liên tục ở từng consumer.

Quy tắc ví dụ:

~~~text
incoming.version <= lastAppliedVersion  -> stale/duplicate
incoming.version == lastAppliedVersion+1 -> apply khi stream liên tục
incoming.version > lastAppliedVersion+1  -> gap, chờ replay/resync
~~~

Đây không phải quy tắc Spring áp đặt. Nếu consumer bỏ qua một số event types hoặc một aggregate version phát nhiều events, phải thiết kế sequence contract khác. Timestamp và UUID ngẫu nhiên không thay thế một thứ tự commit được định nghĩa rõ.

## 11. Spring Modulith Event Publication Registry

**Spring Modulith** có cơ chế **Event Publication Registry** dành cho application events tới transactional listeners. Theo tài liệu Spring Modulith, trong business transaction, registry ghi publication entries cho các listeners quan tâm; khi listener xử lý thành công, entry được đánh dấu completed. Publication chưa hoàn thành có thể được quản lý và resubmit theo cấu hình/API của phiên bản tương ứng.

Phân biệt các lớp:

| Công cụ | Giải quyết vấn đề nào? |
|---|---|
| `ApplicationEventPublisher` của Spring Framework | Phát/dispatch events nội bộ |
| `@TransactionalEventListener` | Chọn phase khi transaction commit/rollback |
| Spring Modulith Event Publication Registry | Ghi nhận và phục hồi publication tới transactional listeners |
| Outbox table + relay | Gửi integration events bền vững ra broker/API |
| Inbox + idempotency | Consumer chống duplicate và xử lý side effect |

Spring Modulith registry rất phù hợp khi cần **reliable event listener execution giữa các module trong cùng ứng dụng**. Nó **không tự động** biến mọi event thành Kafka message hoặc thay thế broker connector và downstream inbox.

Với event qua broker, có thể tích hợp listener chuyển tới broker theo một thiết kế riêng, hoặc dùng outbox/CDC trực tiếp. Nếu kết hợp hai cơ chế, cần tránh phát một event hai lần ngoài dự kiến và xác định ranh giới transaction rõ.

API resubmission và trạng thái publication khác nhau giữa các phiên bản Spring Modulith; phải đối chiếu **đúng version đang dùng**, thay vì sao chép nguyên tùy chọn của version mới.

## 12. Giao dịch, proxy và những cách làm mất atomicity

### Self-invocation

~~~java
@Service
class CheckoutService {
    public void checkout() {
        this.writeOrderAndOutbox(); // Bỏ qua Spring proxy.
    }

    @Transactional
    public void writeOrderAndOutbox() {
        // Annotation có thể không tạo transaction như mong đợi.
    }
}
~~~

Với Spring AOP proxy mode mặc định, `this.method()` không đi qua proxy. Có nguy cơ các INSERT auto-commit từng statement. Sửa bằng gọi qua bean proxy bên ngoài hoặc `TransactionTemplate`, rồi test rollback thật.

### Hai datasource

~~~text
DataSource A: orders INSERT
DataSource B: outbox INSERT
~~~

Nếu hai datasource không cùng một transaction coordinator, `@Transactional` trên một method không tự tạo atomicity giữa chúng. Outbox phải nằm cùng resource commit được bảo đảm. Với kiến trúc nhiều database, cân nhắc ownership redesign/saga/event store hoặc giải pháp transaction phân tán có chủ đích và đánh giá trade-off.

### Bắt lỗi rồi nuốt

~~~java
@Transactional
public void place(String id) {
    orders.insert(id);
    try {
        outbox.insert(id);
    } catch (Exception ex) {
        log.warn("outbox failed", ex);
        // Sai nếu business transaction vẫn commit.
    }
}
~~~

Đây là phản ví dụ. Nếu INSERT outbox là bắt buộc, exception phải gây rollback đúng quy tắc hoặc transaction được đánh dấu rollback-only. Đừng dùng log-and-continue rồi chấp nhận business row không có event. Chú ý checked exceptions và `rollbackFor`: theo quy tắc mặc định phổ biến, runtime exceptions gây rollback nhưng checked exceptions không nhất thiết.

### @Async không mang transaction gốc

Đẩy outbox INSERT sang `@Async` worker thường tách thread và resource transaction, làm mất atomicity với T1. Tracing/MDC context propagation không phải transaction propagation. Ghi outbox **đồng bộ trong T1**, chỉ relay gửi qua async sau commit.

## 13. Reliability testing: cần fault injection

Đừng chỉ kiểm tra happy path. Một bộ integration tests nên chứng minh:

| Test | Cách gây tình huống | Assertion |
|---|---|---|
| Commit | Ghi business + outbox, commit T1 | Hai rows tồn tại |
| Rollback | Ném exception sau cả hai INSERT | Không row nào của T1 thất bại còn lại |
| Outbox INSERT lỗi | Vi phạm constraint/DB failure | Business INSERT cũng rollback |
| Crash trước relay | Giữ PENDING rồi restart worker | Message cuối cùng được gửi |
| Crash sau send trước ack | Cố ý không mark SENT rồi chạy lại | Cùng eventId được gửi lại |
| Duplicate ở consumer | Deliver E1 hai lần | Side effect chỉ áp dụng một lần |
| Concurrent workers | Hai relays claim cùng rows | Không double-claim ngoài policy; idempotency vẫn chịu retry |
| Out-of-order | Deliver version 3 trước version 2 | Projection không trở về state cũ |
| Broker timeout | Ném lỗi giả lập | Retry/backoff, không mark SENT sớm |
| Schema migration | Event v1 còn trong outbox khi deploy v2 | Relay/consumer vẫn deserialize được |
| Cleanup | Dọn SENT sau retention | PENDING/processing còn cần retry không bị xóa |

Một test phương thức đánh dấu `@Transactional` trong Spring TestContext thường **rollback lúc kết thúc**, do đó để kiểm tra commit thật, đừng vô tình gộp service transaction vào test transaction chưa commit. Có thể test method không transactional gọi service proxy, hoặc dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` nếu test-managed transaction thực sự active.

**`ApplicationEvents` test recorder chỉ ghi event được publish trong test**, không chứng minh broker đã gửi hoặc outbox row đã được commit; phải kiểm tra DB/relay và consumer outcome riêng.

## 14. Observability và vận hành

Theo dõi pipeline như những bước riêng biệt:

~~~text
Business commit
    -> Outbox PENDING
    -> Relay claim
    -> Broker ack
    -> Consumer received
    -> Consumer processed
    -> Downstream effect completed
~~~

Metrics thường hữu ích:

- `outbox.pending.count` và `outbox.oldest.pending.age`: hàng đợi đang tắc không?
- `outbox.relay.attempts`, `outbox.relay.errors`, `outbox.relay.backoff`: relay có lỗi hay throttling?
- `outbox.delivery.latency`: mất bao lâu từ commit tới broker ack?
- `consumer.duplicates.count`: retry có tăng bất thường?
- `consumer.processing.errors` và `consumer.processing.latency`: downstream xử lý thành công không?
- `outbox.dead_letter.count`: các events cần manual intervention?
- `consumer.lag` theo aggregate/topic khi có broker: lag/ordering có vấn đề không?

Đặt alert dựa vào backlog age, retry failures và SLO, không chỉ số rows tổng. `SENT` ở producer không chứng minh downstream side effect đã thành công.

**Cardinality:** `event.type`/`relay.name`/`outcome` là tags hữu hạn; tránh làm `eventId`, `aggregateId`, email hay userId trở thành low-cardinality metric labels. Với tracing, lưu correlation/causation metadata vừa đủ và theo chính sách bảo mật; trace không thay thế durability.

## 15. Schema evolution, retention và security

Outbox tồn lâu qua deploy hoặc outage, nên payload phải chịu được version skew.

- **Versioned contract:** event type, schemaVersion và quy tắc backward/forward compatibility.
- **Immutable payload:** snapshot/delta đã được serialize đúng, không giữ tham chiếu tới JPA entity.
- **Safe deserialization:** không tin message từ broker như dữ liệu đã authorize; kiểm tra schema và nguồn.
- **Data minimization:** tránh token, password, số thẻ và PII không cần thiết.
- **Tenant isolation:** nếu aggregateId unique theo tenant, message key/lookup phải gồm tenant context và kiểm tra quyền.
- **Retention:** chỉ dọn rows SENT theo SLA; không xóa PENDING chỉ vì đã cũ.
- **Replay authorization:** replay có thể tạo email/side effect nếu consumer thiếu idempotency; cần audit thao tác replay.
- **Backup consistency:** business và outbox cùng backup/recovery scope, tránh khôi phục business DB nhưng mất outbox.
- **CDC retention:** cleanup outbox, transaction log và connector offsets cần phối hợp để không phá replay/khôi phục.
- **Payload encryption:** nếu phải lưu dữ liệu nhạy cảm, kiểm soát quyền DB/broker và vòng đời khóa giải mã cho messages cũ.

Định nghĩa rõ thời điểm `eventId`, `aggregateVersion` và `occurredAt` được tạo; **không** dùng timestamp làm strict ordering nếu hệ phân tán cần thứ tự đáng tin.

## 16. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Sửa như thế nào |
|---|---|---|
| Tin rằng `publishEvent` có retry sau restart | In-memory event không durable | Outbox record cùng business transaction |
| Gửi message trước DB commit | Consumer nhận event của rollback | Relay chỉ đọc rows đã commit |
| Chỉ dùng `AFTER_COMMIT` | Crash gap vẫn làm mất message | Ghi outbox trước commit |
| Ghi outbox trong listener AFTER_COMMIT | Outbox ở transaction khác | Ghi trong T1 của business |
| Ghi outbox ở datasource khác | Không cùng local transaction | Dùng cùng DB/transaction resource |
| Mark SENT trước broker ack | Crash gây mất event | Ack trước rồi mark, chấp nhận duplicate |
| Dedupe theo aggregateId | Bỏ nhầm các events hợp lệ sau | Dùng eventId per occurrence |
| Dedupe bằng Set in-memory ở production | Restart mất lịch sử | Durable inbox unique constraint |
| Nhiều relay không claim/lock | Cùng gửi một row đồng thời | Lease, atomic update, SKIP LOCKED |
| Mong outbox tự cho exactly-once | Crash giữa send/ack vẫn có resend | Idempotent consumer và side effects |
| Dùng created_at làm commit order chắc chắn | Thời gian insert khác commit time | Aggregate version/ordering contract |
| Áp polling UPDATE vào CDC insert-only | Debezium SMT có contract khác | Thiết kế schema/SMT đúng |
| Không kiểm tra schema cũ | Event pending khó đọc sau deploy | Versioned serializer/consumer |
| Nuốt exception outbox INSERT | Business có thể commit thiếu event | Rollback unit of work |
| @Async ghi outbox sau T1 | Mất atomicity | Ghi trong T1, async chỉ relay |
| Không theo dõi pending age | Queue tắc mà không biết | Metrics/alerts và DLQ |
| Xóa pending vì retention | Event chưa gửi bị mất | Cleanup theo trạng thái/SLA |
| Lộ secrets trong payload | Rủi ro bảo mật DB/broker | Giảm dữ liệu, ACL, encryption |

## 17. Checklist trước khi chạy production

1. Business row và outbox row có thực sự dùng **cùng một transaction** không?
2. Khi INSERT outbox thất bại, business transaction có rollback không?
3. Mỗi event có `eventId` riêng, ổn định qua retry không?
4. Payload có aggregateId, type, schemaVersion và dữ liệu cần thiết không?
5. Relay dùng polling hay CDC; schema có đúng contract không?
6. Multi-worker có claim/lease/failover và xử lý crash gap không?
7. Khi broker ack không rõ, hệ thống có retry cùng eventId không?
8. Consumer có durable idempotency store/unique constraint không?
9. Side effect của consumer và processed marker có commit cùng T2 không?
10. Ordering theo aggregate và version được kiểm soát như thế nào?
11. Retry, backoff, DLQ, visibility timeout và alerts đã có chưa?
12. Có test crash sau send trước ack và concurrency chưa?
13. Có chính sách retention, replay, schema migration và security chưa?
14. Business SLO tính tới **consumer hoàn tất**, không chỉ producer `SENT`?
15. Spring Modulith registry và integration outbox có bị trùng trách nhiệm/phát trùng event không?

## 18. Câu hỏi ôn tập

**1. Vì sao gửi Kafka ngay trong `@Transactional` nguy hiểm?** Vì Kafka send và JDBC commit không phải một local atomic transaction; gửi thành công rồi DB rollback có thể sinh event mồ côi.

**2. `@TransactionalEventListener(AFTER_COMMIT)` có tương đương outbox?** Không. Nó quyết định thời điểm callback, không tự persist event trước commit.

**3. Outbox có đảm bảo đúng một lần gửi không?** Thường không. Relay có thể gửi lại sau crash, nên consumer phải idempotent.

**4. Vì sao eventId không được thay bằng orderId?** Cùng một order có nhiều event hợp lệ; dedupe orderId sẽ bỏ nhầm các cập nhật.

**5. Outbox và business row nên nằm đâu?** Trong cùng một local transaction/resource để atomic commit hoặc rollback.

**6. Polling khác CDC ở đâu?** Polling query/claim outbox rows; CDC đọc transaction log và có schema/mapping/offset riêng.

**7. Debezium Outbox Router có dùng y nguyên schema polling PENDING/SENT không?** Không mặc định; SMT mong đợi các INSERT event rows và có mapping riêng.

**8. Spring Modulith Event Publication Registry có tự gửi Kafka không?** Không tự động; registry theo dõi publication tới transactional listeners, còn integration broker cần cấu hình/giải pháp riêng.

**9. Consumer cần xử lý duplicate như thế nào?** Lưu processed eventId bền cùng business side effect trong một transaction nếu có thể; với external APIs dùng idempotency key hoặc cơ chế tương ứng.

**10. Lợi ích cốt lõi của transactional outbox?** Nếu business transaction commit, có một event record bền để relay; nếu rollback, event record cũng rollback.

## 19. Kết luận và tài liệu chính thức

**Transactional Outbox Pattern** giải quyết dual-write problem bằng cách đưa **business update và durable event record vào cùng transaction DB**. Relay gửi event ra ngoài sau commit, có retry khi hỏng mạng hoặc process crash. Vì không thể atomic giữa broker ack và outbox mark SENT trong mô hình thông thường, duplicate là thực tế phải dự phòng; consumer cần idempotency, đồng thời có kiểm soát ordering, version và event schema.

Spring Framework Application Events vẫn phù hợp cho sự kiện trong JVM; `@TransactionalEventListener` hữu ích về phase nhưng không tự làm event durable. Spring Modulith Event Publication Registry hỗ trợ reliable publication giữa các transactional listeners theo mô hình module; Debezium Outbox Event Router hỗ trợ CDC publication ra broker với schema riêng. Chọn đúng công cụ theo mục tiêu: **bảo đảm event được lưu cùng business commit**, **giao tới hệ thống ngoài**, hay **xử lý event nội bộ có thể resubmit**.

Tài liệu đối chiếu:

- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html).
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).
- [Spring Framework — Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
- [Spring Modulith 1.4 — Working with Application Events](https://docs.spring.io/spring-modulith/reference/1.4/events.html).
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html).
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html).
- [Microservices.io — Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html).

# Thiết kế listener có thể chạy lại

## 1. Vấn đề: cùng một event được xử lý nhiều lần

Trong Spring Framework Application Events, một listener thường phản ứng với sự việc nghiệp vụ:

~~~java
@EventListener
public void onOrderPaid(OrderPaid event) {
    reportingService.addRevenue(event.orderId(), event.amountCents());
}
~~~

Đoạn minh họa trên có nguy cơ **cộng doanh thu hai lần** nếu cùng một `OrderPaid` được chuyển đến listener thêm lần nữa. Điều đó có thể xảy ra do:

- Một người vận hành **replay event** để tái tạo báo cáo hoặc sửa dữ liệu đã lệch.
- Consumer retry sau timeout; nó không chắc lần trước đã commit hay chưa.
- Một message broker cung cấp **at-least-once delivery**, khiến cùng message được nhận lại.
- Worker crash sau khi ghi kết quả nhưng trước khi gửi ACK.
- Một quy trình migration/reindex đọc lại lịch sử event.
- Một bug ở producer hoặc consumer gửi cùng sự việc nhiều lần.
- Ứng dụng tự gọi `publishEvent(...)` lần thứ hai với **cùng event identity**.

**Listener có thể chạy lại (replayable/retry-safe listener)** là listener được thiết kế để có thể xử lý lại cùng một sự việc mà không gây tác dụng phụ sai, đồng thời vẫn xử lý được những event mới. Trong nhiều trường hợp, tính chất quan trọng nhất là **idempotency**: lặp lại cùng thao tác hợp lệ không làm thay đổi kết quả quan sát sau lần thành công đầu tiên.

Cần phân biệt:

1. **Retry:** chạy lại một công việc đã thất bại hoặc chưa rõ kết quả.
2. **Redelivery:** nguồn gửi lại message/event cũ, có thể dù lần trước đã thành công.
3. **Replay:** đọc lại một tập sự kiện lịch sử đã lưu để tái dựng projection hoặc phục hồi consumer.
4. **Rebuild:** tạo lại trạng thái phái sinh từ lịch sử hoặc nguồn chân lý, thường có phiên bản projection mới.
5. **Reconciliation:** so sánh và sửa sự khác biệt giữa projection và nguồn dữ liệu.

Cả năm tình huống đều liên quan đến khả năng “chạy lại”, nhưng yêu cầu về **lưu lịch sử, thứ tự, marker và side effect** không hoàn toàn giống nhau.

## 2. Giới hạn đầu tiên: Spring application event không tự lưu lịch sử

`ApplicationEventPublisher.publishEvent(...)` bàn giao event cho cơ chế dispatch của `ApplicationContext`. Với `SimpleApplicationEventMulticaster` mặc định, các listener thông thường chạy đồng bộ trên thread publish, trừ khi ứng dụng cấu hình executor, `@Async` hoặc cơ chế khác.

~~~text
Service
  |
  +-- publishEvent(OrderPaid E1)
             |
             +--> @EventListener ReportingListener
             +--> @EventListener AuditListener
             +--> @Async NotificationListener (nếu cấu hình)
~~~

**Spring application event mặc định không có event log bền vững, offset, ACK hoặc nút replay tự động.** Khi process restart, Spring không tự đọc lại những event đã phát trong lần chạy trước.

Để replay thật sự, cần một **nguồn phát lại có thể đọc được**, ví dụ:

- event store / append-only event log;
- transactional outbox có chính sách retention phù hợp;
- message broker giữ lịch sử trong khoảng thời gian cho phép;
- bảng nghiệp vụ và quy trình tạo **synthetic rebuild events** từ trạng thái nguồn (phải phân biệt với lịch sử gốc).

Trong bài này, ta xây một ví dụ Spring có bảng `event_archive` để **minh họa replay thủ công trong một process**. Bảng H2 in-memory của demo không bền vững qua restart; production cần database/broker lưu bền vững và cơ chế transactional consistency riêng.

Đừng suy luận rằng vì một listener có `@EventListener` hoặc `@TransactionalEventListener`, Spring sẽ tự thử lại khi method lỗi. Mặc định, cách xử lý exception phụ thuộc multicaster/async/transaction phase và cấu hình ứng dụng; **retry policy phải được thiết kế rõ**.

## 3. Event identity: cùng event hay một sự kiện mới?

Ví dụ event bất biến:

~~~java
public record OrderPaid(
    java.util.UUID eventId,
    long orderId,
    long amountCents
) {}
~~~

Các định danh nên phân biệt:

| Trường | Diễn giải | Dùng làm khóa dedup? |
| --- | --- | --- |
| `eventId` | Danh tính của **một sự việc đã được ghi nhận** | Thường là khóa chính cho dedup cùng sự việc |
| `orderId` / `aggregateId` | Entity/aggregate mà sự việc liên quan | Không đủ: một order có thể có nhiều thanh toán |
| `correlationId` | Gắn các thao tác vào cùng workflow/request | Không đủ: workflow có thể có nhiều event |
| `causationId` | Event/command gây ra event hiện tại | Không đủ: một nguyên nhân có thể dẫn tới nhiều kết quả |
| `deliveryAttempt` | Lần giao thứ mấy (nếu transport có) | Không: mỗi lần retry thay đổi |
| `schemaVersion` | Phiên bản contract dữ liệu | Không thay thế event identity |

**Retry cùng sự việc phải giữ nguyên `eventId`.** Nếu mỗi lần retry lại tạo một UUID mới, consumer sẽ cho rằng đó là sự việc khác và tính cộng thêm.

Ngược lại, **hai khoản thanh toán khác nhau của cùng đơn hàng** phải có hai event ID khác nhau. Dùng `orderId` làm khóa dedup có thể làm mất một khoản thanh toán hợp lệ.

~~~text
E1: eventId=111..., orderId=101, amount=500
  -> xử lý lần 1: +500
  -> replay E1   : +0

E2: eventId=222..., orderId=101, amount=200
  -> xử lý lần 1: +200 (một sự việc khác)

Kết quả đúng cho hai sự việc: 700, không phải 500 hay 1.200.
~~~

Nếu producer phát **cùng eventId nhưng payload khác**, đó là vi phạm identity/immutability contract; đừng lặng lẽ coi bản mới là duplicate an toàn. Production nên có validation hoặc payload fingerprint/version policy để phát hiện xung đột.

## 4. Idempotent side effect và marker đã xử lý

Một chiến lược phổ biến là dùng **inbox/processed-events table** ghi consumer nào đã xử lý event nào:

~~~text
processed_events
+-----------------+--------------------------------------+
| consumer_name   | event_id                             |
+-----------------+--------------------------------------+
| revenue-report  | E1                                   |
| audit-projector | E1                                   |
| revenue-report  | E2                                   |
+-----------------+--------------------------------------+
PRIMARY KEY (consumer_name, event_id)
~~~

Tại sao khóa là **(consumer, eventId)** thay vì chỉ `eventId`?

Một event có thể được nhiều listener độc lập xử lý. Nếu `AuditListener` đã xử lý E1, điều đó **không có nghĩa** `RevenueListener` đã làm xong. Mỗi consumer cần namespace marker riêng. Trong rebuild, có thể cần thêm `projectionVersion` hoặc tạo một namespace/target mới.

Cách xử lý đúng cho side effect **cùng database**:

~~~text
BEGIN transaction
  INSERT processed_events(consumer, eventId) [unique constraint]
  UPDATE/INSERT reporting_projection (...)
COMMIT transaction
~~~

Nếu cùng `(consumer, eventId)` đã commit, lần lặp bỏ qua. Nếu transaction lỗi trước commit, cả **marker và projection update đều rollback**, nên lần retry có thể làm lại.

**Bắt buộc atomically commit marker và hiệu ứng nghiệp vụ.** Hai cách sai:

- **Ghi marker trước rồi commit, sau đó mới ghi projection:** crash giữa hai bước khiến event bị đánh dấu done nhưng side effect chưa được làm.
- **Ghi projection trước rồi commit, sau đó mới ghi marker:** crash khiến retry cộng/chèn thêm dữ liệu lần thứ hai.

Nếu side effect ở **hệ thống ngoài** (gửi email, gọi payment provider, HTTP API), hai hệ thống thường không chung transaction. Lúc đó processed marker nội bộ **không tự bảo đảm exactly-once external effect**: cần idempotency key ở phía đích, outbox/worker, giao thức retry và reconciliation.

## 5. Bốn cách làm listener có thể chạy lại

### 5.1 Thao tác tự nhiên idempotent

Thay vì:

~~~java
// Có thể cộng trùng khi replay:
revenueRepository.incrementTotal(event.amountCents());
~~~

Một projection lưu **trạng thái cuối cùng** theo key/version có thể dùng kiểu upsert:

~~~text
Projection event: CustomerTierChanged(customerId, version=8, tier=GOLD)

UPDATE customer_tier
SET tier = 'GOLD', source_version = 8
WHERE customer_id = 101 AND source_version < 8;
~~~

Đây là SQL khái niệm: cần xử lý hàng chưa tồn tại và concurrency bằng upsert/constraint/locking thực tế của DB. Cập nhật theo **version tăng đơn điệu** giúp không áp dụng lại trạng thái cũ; tính đúng đắn phụ thuộc hợp đồng version của aggregate.

Với nghiệp vụ cộng dồn (số tiền, điểm thưởng), thường phải có marker/unique effect ID rõ ràng vì `x += amount` không tự idempotent.

### 5.2 Unique constraint theo event

Ví dụ bảng `revenue_entries(event_id PRIMARY KEY, amount_cents)`. Nếu insert E1 lần nữa, DB từ chối bản trùng. Một phép tính tổng theo các entry độc nhất sẽ không cộng lại. Ưu điểm là ít state; hạn chế là mỗi side effect có thể có nhiều bảng và cần xử lý duplicate/key conflict đúng chỗ.

### 5.3 Processed marker + transaction

Bảng `processed_events(consumer_name, event_id)` với unique key, cộng hiệu ứng **cùng transaction**. Đây là lựa chọn dễ hiểu cho nhiều projection JDBC/JPA, miễn mọi thao tác cần nguyên tử nằm trong cùng datasource/transaction manager.

### 5.4 Inbox/outbox và consumer state bền vững

Broker có thể deliver cùng message nhiều lần. Consumer dùng inbox marker và transaction local để xử lý idempotent; nếu phải gọi hệ thống ngoài, ghi outbox message trong cùng transaction rồi một worker giao lại với idempotency key.

~~~text
Broker redelivery E1
        |
        v
Consumer transaction
  +-- dedup E1
  +-- update local projection
  +-- create outgoing outbox item
        |
        v
Commit + ACK broker
        |
        v
Outbox delivery to external API (stable key E1)
~~~

ACK broker thường phải **sau commit**; nếu crash sau commit trước ACK, message được giao lại và marker giúp skip. Nếu ACK trước commit, crash có thể làm mất side effect. Hành vi ACK cụ thể phụ thuộc broker/client; cần tuân thủ contract của transport.

## 6. Ví dụ chạy được: replay cùng event nhưng kết quả không nhân đôi

Demo dùng **Java 17+**, **Spring Framework 6.2.19**, **Spring JDBC** và **H2 2.3.232**. Đây là một **Spring Application Event listener thật** được chạy trong `AnnotationConfigApplicationContext`, không phải test gọi method listener thủ công.

Ta tạo ba bảng:

~~~sql
CREATE TABLE event_archive (
    seq BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_id VARCHAR(36) NOT NULL UNIQUE,
    order_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL
);

CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE revenue_entries (
    event_id VARCHAR(36) PRIMARY KEY,
    order_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL
);
~~~

Trong code:

- `EventArchive` lưu sự việc với `eventId` cố định, rồi publish.
- `RevenueListener` xử lý trong `TransactionTemplate` với một transaction riêng, ghi **processed marker + revenue entry**.
- Bảng có unique key bảo vệ khỏi duplicate.
- `FailureGate` cố ý ném exception **sau khi đã INSERT hai bảng trong transaction nhưng trước commit**. H2 rollback cả hai INSERT, vì vậy replay vẫn làm lại an toàn.
- `EventArchive.replayAll()` đọc lịch sử theo `seq` rồi công bố lại **cùng `eventId`**.

**Giới hạn cực kỳ quan trọng:** demo lưu archive rồi publish bằng hai bước tách rời, **không bảo đảm atomicity với business transaction**. H2 cũng ở bộ nhớ: đóng process là mất lịch sử. Đây là minh họa idempotency + replay trong một lần chạy; xem mục 10 về outbox production.

### 6.1. Cấu trúc

~~~text
replayable-event-listener/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/ReplayableListenerDemo.java
    └── test/java/demo/ReplayableListenerDemoTest.java
~~~

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'replayable-event-listener'
~~~

### 6.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-jdbc:6.2.19'
    implementation 'com.h2database:h2:2.3.232'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ReplayableListenerDemo'
}

test {
    useJUnitPlatform()
}
~~~

### 6.4. src/main/java/demo/ReplayableListenerDemo.java

~~~java
package demo;

import java.util.List;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class ReplayableListenerDemo {

    public record OrderPaid(
        UUID eventId,
        long orderId,
        long amountCents
    ) {
        public OrderPaid {
            Objects.requireNonNull(eventId, "eventId");
            if (orderId <= 0 || amountCents <= 0) {
                throw new IllegalArgumentException(
                    "Invalid paid order event"
                );
            }
        }
    }

    @Bean
    DataSource dataSource() {
        JdbcDataSource dataSource = new JdbcDataSource();
        // Mỗi context/test có một database riêng trong RAM.
        String name = UUID.randomUUID().toString()
            .replace("-", "");
        dataSource.setURL(
            "jdbc:h2:mem:replay_" + name + ";DB_CLOSE_DELAY=-1"
        );
        dataSource.setUser("sa");
        dataSource.setPassword("");
        return dataSource;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    FailureGate failureGate() {
        return new FailureGate();
    }

    @Bean
    EventArchive eventArchive(
            JdbcTemplate jdbc,
            ApplicationEventPublisher publisher) {

        jdbc.execute("""
            CREATE TABLE event_archive (
                seq BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                event_id VARCHAR(36) NOT NULL UNIQUE,
                order_id BIGINT NOT NULL,
                amount_cents BIGINT NOT NULL
            )
            """);

        jdbc.execute("""
            CREATE TABLE processed_events (
                consumer_name VARCHAR(80) NOT NULL,
                event_id VARCHAR(36) NOT NULL,
                PRIMARY KEY (consumer_name, event_id)
            )
            """);

        jdbc.execute("""
            CREATE TABLE revenue_entries (
                event_id VARCHAR(36) PRIMARY KEY,
                order_id BIGINT NOT NULL,
                amount_cents BIGINT NOT NULL
            )
            """);

        return new EventArchive(jdbc, publisher);
    }

    @Bean
    RevenueListener revenueListener(
            EventArchive archive,
            JdbcTemplate jdbc,
            PlatformTransactionManager transactionManager,
            FailureGate gate) {

        // Phụ thuộc EventArchive bảo đảm schema đã được tạo.
        // Không dùng archive trong listener: một source, hai vai trò.
        return new RevenueListener(jdbc, transactionManager, gate);
    }

    public static final class FailureGate {
        private final AtomicBoolean armed = new AtomicBoolean();

        public void failNextProcessing() {
            armed.set(true);
        }

        public void failIfArmed() {
            if (armed.compareAndSet(true, false)) {
                throw new IllegalStateException(
                    "simulated transient failure"
                );
            }
        }
    }

    public static final class EventArchive {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public EventArchive(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        public void appendAndPublish(OrderPaid event) {
            // Bản demo: ghi archive trước, sau đó mới publish.
            // Production phải thiết kế transactional consistency riêng.
            jdbc.update(
                "INSERT INTO event_archive" +
                "(event_id, order_id, amount_cents) VALUES (?,?,?)",
                event.eventId().toString(),
                event.orderId(),
                event.amountCents()
            );
            publisher.publishEvent(event);
        }

        public void replayAll() {
            List<OrderPaid> history = jdbc.query(
                "SELECT event_id, order_id, amount_cents " +
                "FROM event_archive ORDER BY seq",
                (rs, row) -> new OrderPaid(
                    UUID.fromString(rs.getString("event_id")),
                    rs.getLong("order_id"),
                    rs.getLong("amount_cents")
                )
            );
            history.forEach(publisher::publishEvent);
        }

        public int archivedCount() {
            return jdbc.queryForObject(
                "SELECT COUNT(*) FROM event_archive",
                Integer.class
            );
        }
    }

    public static final class RevenueListener {
        private static final String CONSUMER = "revenue-report";

        private final JdbcTemplate jdbc;
        private final TransactionTemplate transaction;
        private final FailureGate gate;

        public RevenueListener(
                JdbcTemplate jdbc,
                PlatformTransactionManager transactionManager,
                FailureGate gate) {

            this.jdbc = jdbc;
            this.transaction = new TransactionTemplate(
                transactionManager
            );
            // Tách transaction local của consumer khỏi caller.
            this.transaction.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW
            );
            this.gate = gate;
        }

        @EventListener
        public void onOrderPaid(OrderPaid event) {
            try {
                transaction.executeWithoutResult(status -> {
                    // UNIQUE (consumer_name, event_id):
                    // một event chỉ được apply một lần ở consumer này.
                    jdbc.update(
                        "INSERT INTO processed_events" +
                        "(consumer_name, event_id) VALUES (?,?)",
                        CONSUMER,
                        event.eventId().toString()
                    );

                    jdbc.update(
                        "INSERT INTO revenue_entries" +
                        "(event_id, order_id, amount_cents)" +
                        " VALUES (?,?,?)",
                        event.eventId().toString(),
                        event.orderId(),
                        event.amountCents()
                    );

                    // Ném sau cả hai INSERT nhưng trước COMMIT.
                    // Transaction rollback cả marker lẫn effect.
                    gate.failIfArmed();
                });
            } catch (DuplicateKeyException duplicate) {
                // Sau transaction rollback của attempt trùng,
                // chỉ swallow khi marker consumer đã commit.
                if (!alreadyProcessed(event.eventId())) {
                    throw duplicate;
                }
            }
        }

        private boolean alreadyProcessed(UUID eventId) {
            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM processed_events " +
                "WHERE consumer_name = ? AND event_id = ?",
                Integer.class,
                CONSUMER,
                eventId.toString()
            );
            return count != null && count > 0;
        }

        public long totalCents() {
            Long result = jdbc.queryForObject(
                "SELECT COALESCE(SUM(amount_cents), 0) " +
                "FROM revenue_entries",
                Long.class
            );
            return result == null ? 0L : result;
        }

        public int processedCount() {
            return jdbc.queryForObject(
                "SELECT COUNT(*) FROM processed_events " +
                "WHERE consumer_name = ?",
                Integer.class,
                CONSUMER
            );
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                ReplayableListenerDemo.class)) {

            var archive = context.getBean(EventArchive.class);
            var report = context.getBean(RevenueListener.class);
            var gate = context.getBean(FailureGate.class);

            OrderPaid e1 = new OrderPaid(
                UUID.fromString(
                    "00000000-0000-0000-0000-000000000001"),
                101L, 500L
            );
            OrderPaid e2 = new OrderPaid(
                UUID.fromString(
                    "00000000-0000-0000-0000-000000000002"),
                102L, 700L
            );
            OrderPaid e3 = new OrderPaid(
                UUID.fromString(
                    "00000000-0000-0000-0000-000000000003"),
                101L, 300L
            );

            archive.appendAndPublish(e1);
            archive.appendAndPublish(e2);

            System.out.println(
                "first: total=" + report.totalCents()
                + " processed=" + report.processedCount()
                + " archived=" + archive.archivedCount()
            );

            archive.replayAll();

            System.out.println(
                "replay: total=" + report.totalCents()
                + " processed=" + report.processedCount()
            );

            gate.failNextProcessing();

            try {
                archive.appendAndPublish(e3);
            } catch (IllegalStateException ex) {
                System.out.println("injected failure observed");
            }

            System.out.println(
                "failed: total=" + report.totalCents()
                + " processed=" + report.processedCount()
                + " archived=" + archive.archivedCount()
            );

            archive.replayAll();

            System.out.println(
                "retry: total=" + report.totalCents()
                + " processed=" + report.processedCount()
            );
        }
    }
}
~~~

### 6.5. Chạy và đối chiếu stdout

Cài JDK 17+ và Gradle tương thích hoặc dùng Gradle Wrapper của dự án:

~~~bash
gradle run --quiet
# Nếu có Wrapper: ./gradlew run --quiet
# Trên Windows: gradlew.bat run --quiet
~~~

Các dòng do `main` chủ động in, không tính log từ dependency:

~~~text
first: total=1200 processed=2 archived=2
replay: total=1200 processed=2
injected failure observed
failed: total=1200 processed=2 archived=3
retry: total=1500 processed=3
~~~

**Giải thích:**

1. E1 và E2 là hai event khác nhau, được ghi vào archive và xử lý; tổng = 500 + 700 = 1.200.
2. Replay đọc lại E1/E2 với **cùng eventId**. Khi insert vào `processed_events`, unique constraint làm lần xử lý trùng bị từ chối; transaction attempt rollback, listener kiểm tra marker đã commit rồi bỏ qua. Tổng vẫn 1.200.
3. E3 được ghi vào archive thành công trước khi publish. `FailureGate` ném exception sau khi listener đã INSERT vào cả marker và projection, nhưng transaction chưa commit.
4. Transaction của E3 rollback cả hai bảng, nên sau lỗi **tổng vẫn 1.200**, **processed vẫn 2**, **archived là 3**.
5. Gọi `replayAll()`: E1/E2 bị skip, còn E3 không có marker nên được xử lý; tổng = 1.500 và processed = 3.

Không có phép màu “lỗi tự retry”. Chính code demo **chủ động gọi** `replayAll()`. Trong production, một worker/outbox/broker scheduler phải đảm nhận việc phát lại, kiểm soát backoff, ACK, poison message và retry budget.

**Ý nghĩa của H2 in-memory:** đây là thử nghiệm đúng transaction/unique constraint trong **một JVM còn sống**. Vì database URL bắt đầu bằng `jdbc:h2:mem:`, nó **không lưu archive qua restart**. Dữ liệu production phải được lưu trên DB/broker bền vững nếu muốn replay sau process crash.

## 7. JUnit 5: kiểm thử retry, duplicate và failure atomicity

Tạo `src/test/java/demo/ReplayableListenerDemoTest.java`:

~~~java
package demo;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ReplayableListenerDemoTest {

    private static ReplayableListenerDemo.OrderPaid paid(
            String suffix, long orderId, long cents) {

        return new ReplayableListenerDemo.OrderPaid(
            UUID.fromString(
                "00000000-0000-0000-0000-" + suffix),
            orderId,
            cents
        );
    }

    @Test
    void sameEventReplayDoesNotMultiplyRevenue() {
        try (var ctx = new AnnotationConfigApplicationContext(
                ReplayableListenerDemo.class)) {

            var archive = ctx.getBean(
                ReplayableListenerDemo.EventArchive.class);
            var report = ctx.getBean(
                ReplayableListenerDemo.RevenueListener.class);

            archive.appendAndPublish(
                paid("000000000001", 101L, 500L));
            archive.replayAll();
            archive.replayAll();

            assertEquals(500L, report.totalCents());
            assertEquals(1, report.processedCount());
            assertEquals(1, archive.archivedCount());
        }
    }

    @Test
    void failingAttemptRollsBackMarkerAndSideEffect() {
        try (var ctx = new AnnotationConfigApplicationContext(
                ReplayableListenerDemo.class)) {

            var archive = ctx.getBean(
                ReplayableListenerDemo.EventArchive.class);
            var report = ctx.getBean(
                ReplayableListenerDemo.RevenueListener.class);
            var gate = ctx.getBean(
                ReplayableListenerDemo.FailureGate.class);

            gate.failNextProcessing();

            assertThrows(
                IllegalStateException.class,
                () -> archive.appendAndPublish(
                    paid("000000000002", 102L, 700L))
            );

            assertEquals(0L, report.totalCents());
            assertEquals(0, report.processedCount());
            assertEquals(1, archive.archivedCount());

            archive.replayAll();

            assertEquals(700L, report.totalCents());
            assertEquals(1, report.processedCount());
        }
    }

    @Test
    void distinctEventIdsForSameOrderAreBothApplied() {
        try (var ctx = new AnnotationConfigApplicationContext(
                ReplayableListenerDemo.class)) {

            var archive = ctx.getBean(
                ReplayableListenerDemo.EventArchive.class);
            var report = ctx.getBean(
                ReplayableListenerDemo.RevenueListener.class);

            archive.appendAndPublish(
                paid("000000000003", 101L, 400L));
            archive.appendAndPublish(
                paid("000000000004", 101L, 200L));

            archive.replayAll();

            assertEquals(600L, report.totalCents());
            assertEquals(2, report.processedCount());
        }
    }
}
~~~

Chạy:

~~~bash
gradle test
# Wrapper Linux/macOS: ./gradlew test
# Wrapper Windows: gradlew.bat test
~~~

Bộ test kỳ vọng **3 test pass** với cấu hình ví dụ:

- **Replay một event** nhiều lần mà `totalCents` và số marker không tăng.
- **Lỗi giữa transaction:** side effect lẫn marker cùng rollback, sau đó replay chạy lại được.
- **Hai event ID khác nhau của cùng order:** được tính riêng, không bị loại sai vì cùng `orderId`.

Mỗi test tạo một `ApplicationContext` với H2 database name ngẫu nhiên, tránh trộn dữ liệu giữa các test. Không cần `Thread.sleep()`; demo dùng listener đồng bộ nên sau mỗi `publishEvent` thành công có thể đọc kết quả ngay.

Lưu ý: bộ test này chưa chứng minh khả năng xử lý đầy đủ các cuộc đua đa thread, process crash, broker partition/rebalance hay external side effects. Các trường hợp đó cần integration/failure-injection test với hạ tầng production tương ứng.

## 8. Điểm chốt về transaction, exception và concurrency

### 8.1. Vì sao marker và effect phải ở một transaction?

Một listener như sau **không đủ an toàn**:

~~~java
// Anti-pattern minh họa, không phải chương trình độc lập.
if (!seen(event.eventId())) {
    projection.increment(event.amountCents());
    markProcessed(event.eventId());
}
~~~

Nếu `increment` commit trước `markProcessed` rồi process chết, retry sẽ increment lần nữa. Nếu `markProcessed` commit trước `increment` rồi process chết, event bị đánh dấu đã làm mà projection chưa cập nhật.

Dùng cùng transaction và **unique key tại database**. Unique constraint là lớp bảo vệ trước hai worker đồng thời thấy “chưa xử lý”.

### 8.2. Chỉ SELECT trước rồi INSERT có race condition

~~~text
Worker A: SELECT marker E1 => absent
Worker B: SELECT marker E1 => absent
Worker A: process
Worker B: process
~~~

Không thể dựa vào câu `if (not exists)` trong application code để chống trùng. Cần database unique constraint hoặc atomic claim/locking tùy DB; những worker còn lại phải xử lý conflict đúng cách.

Trong demo, worker **INSERT marker trước** với primary key `(consumer_name,event_id)`. Khi duplicate, lỗi được bắt **ngoài transaction** rồi code xác nhận marker đã commit. Với DB/driver khác, lỗi duplicate có thể trả qua mã SQL/vendor-specific; không bắt mọi `DataAccessException` rồi coi là duplicate. Nếu transaction lỗi vì deadlock/timeout, phải retry theo chính sách khác.

### 8.3. Vì sao không nuốt mọi exception?

~~~java
// Sai: biến lỗi hạ tầng thành "đã xử lý".
try {
    process(event);
} catch (Exception ignored) {
    return;
}
~~~

Nếu listener báo thành công khi DB tạm thời không truy cập được, broker có thể ACK và vĩnh viễn không giao lại event. Chỉ skip **duplicate đã xác nhận**, không skip lỗi không rõ kết quả. Ghi log/metric lỗi theo eventId và consumer; dùng retry với backoff, timeout và DLQ khi thích hợp.

### 8.4. REQUIRES_NEW giải quyết điều gì?

Demo cấu hình `TransactionTemplate` với `PROPAGATION_REQUIRES_NEW` để consumer có transaction local riêng, không nhập vào transaction caller. Đây là lựa chọn **của ví dụ**, không phải bắt buộc cho mọi listener.

Nếu nghiệp vụ cần audit/projection update rollback **cùng** use case chính, một transaction chung có thể đúng hơn. Nếu handler chạy `AFTER_COMMIT` hoặc ngoài một transaction, nó có thể cần transaction mới để ghi DB.

**Không dùng REQUIRES_NEW theo thói quen**: nó có thể làm side effect commit độc lập ngay cả khi transaction của caller sau đó rollback. Phải xác định rõ lúc nào source event được công nhận là một fact đã commit.

## 9. Replay an toàn là tái tạo trạng thái, không kích hoạt lại mọi side effect

Một nhược điểm lớn khi replay qua một event bus chung: nếu event lịch sử được publish lại cho **mọi listener**, nhiều side effect không nên lặp có thể bị kích hoạt.

~~~text
Replay OrderPaid E1
    +--> RevenueProjection: nên rebuild
    +--> AuditProjection  : có thể rebuild
    +--> EmailSender      : KHÔNG gửi lại email vô cớ
    +--> PaymentGateway   : KHÔNG thu tiền lại
    +--> Analytics        : có thể tính lại có kiểm soát
~~~

Phân biệt:

- **Projection listener:** biến event thành trạng thái phái sinh (reporting, search index), có thể rebuild với đúng schema/version/ordering.
- **Effect listener:** gọi hệ thống ngoài (email, push, payment), cần chính sách side effect rõ ràng và idempotency ở đích; không tự động chạy lại trong một đợt rebuild dữ liệu.
- **Audit:** có thể cần giữ audit trail lịch sử thay vì xóa và phát lại như một side effect mới.

Khi xây production replay, nên có **replay runner gọi trực tiếp nhóm projection consumer được phép**, hoặc một topology/stream riêng. Đừng gửi toàn bộ history lại qua một topic/event bus có cả các effect listeners mà chưa kiểm tra điều kiện. Không dùng flag `isReplay` trong payload như lớp bảo vệ duy nhất nếu các consumer có quyền gây tác động lớn; cần thiết kế phân quyền và pipeline phù hợp.

### Side effect ngoài database

Nếu gọi một payment provider hay email gateway:

~~~text
Consumer receives E1
  -> remote API accepted request
  -> consumer crashes before recording DONE
  -> E1 redelivered
~~~

Marker local chưa được ghi, nên lần hai vẫn có thể gọi API. Cần **stable idempotency key** được phía đích hỗ trợ, hoặc một giao thức dedup/reconciliation đã phân tích tình huống timeout không rõ kết quả. Không thể tạo một atomic transaction giữa mọi database, HTTP API và broker bằng mỗi `@Transactional`.

## 10. Transactional outbox và nguồn replay bền vững

Demo `EventArchive.appendAndPublish` chỉ ghi event vào bảng riêng trước khi publish. Production cần tính nhất quán giữa domain state và nguồn replay.

Một kiến trúc phổ biến:

~~~text
BEGIN T1
    UPDATE orders SET status='PAID' WHERE id=101
    INSERT INTO outbox(
        event_id, event_type, aggregate_id,
        schema_version, payload, occurred_at
    ) VALUES (...)
COMMIT T1
          |
          v
Outbox relay / broker
          |
          +--> consumer retry/replay by stable eventId
                    |
                    +--> inbox marker + projection update
                    |    in one local transaction
                    |
                    +--> ACK after commit
~~~

Bằng cách ghi **domain state và outbox record trong cùng transaction**, sự kiện chỉ được lưu bền vững nếu domain change commit. Event được gửi qua worker sau đó vẫn có thể lặp: outbox giải bài toán không mất việc, **idempotent consumer** giải bài toán giao trùng.

**Cần phân biệt outbox và event store:**

- Outbox thường phục vụ giao message với retention có giới hạn; có thể xóa các bản ghi đã gửi.
- Event store lưu lịch sử đủ dài và đủ thông tin cho replay/rebuild theo yêu cầu.
- Nếu đã xóa outbox `DONE`, không thể kỳ vọng replay **toàn bộ lịch sử** từ outbox đó.
- Một bảng sự kiện chỉ chứa `orderId` mà không có dữ liệu lịch sử cần thiết có thể không đủ để khôi phục projection chính xác.

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` giúp ràng buộc handler với phase commit nhưng **không tự tạo lưu trữ bền vững**. Crash sau commit trước enqueue vẫn có thể làm mất task. Nếu gọi listener ngoài transaction, mặc định `fallbackExecution=false` thì callback transaction-bound bị bỏ qua.

Reactive transaction sử dụng Reactor Context và `TransactionalEventPublisher` khi phù hợp; không giả định transaction thread-local của servlet áp dụng cho mọi reactive listener.

## 11. Replay và rebuild: quản lý version/checkpoint

Khi rebuild projection từ lịch sử, không nhất thiết dùng lại marker production cũ. Nếu consumer version 1 đã xử lý E1, bản rebuild version 2 vẫn cần áp dụng E1 vào **projection mới**.

Hai chiến lược thường dùng:

1. **Projection version riêng:** processed marker khóa theo `(consumer_name, projection_version, event_id)` hoặc namespace khác.
2. **Shadow projection + atomic cutover:** xây bảng `revenue_projection_v2` từ event history, kiểm tra tổng/đối chiếu, rồi chuyển ứng dụng sang đọc v2; không xóa bảng v1 trong khi production còn phục vụ.

~~~text
Event store E1..En
       |
       +--> Consumer report-v1 -> projection_v1 (đang phục vụ)
       |
       +--> Consumer report-v2 -> projection_v2 (đang rebuild)
                                      |
                                verify/checkpoint
                                      |
                                 atomic switch
~~~

**Checkpoint/offset không thay thế event-level idempotency.** Có thể crash sau khi ghi một phần batch nhưng trước khi checkpoint; replay lại batch phải an toàn. Checkpoint nên được cập nhật với trạng thái projection trong transaction phù hợp, hoặc có giao thức at-least-once + dedup rõ.

Nếu hệ thống vẫn nhận live events trong lúc rebuild, phải có cách **catch up** phần tail từ mốc snapshot/offset mà không bỏ sót hoặc đếm hai lần. Thời điểm cutover cần bảo đảm projection mới đã theo kịp mức consistency được yêu cầu.

### Schema evolution và dữ liệu lịch sử

Event từ ba năm trước có thể theo schema v1 còn consumer mới dùng schema v3. Cần có:

- `eventType` và `schemaVersion` rõ ràng;
- upcaster/adapter có test cho từng phiên bản còn lưu;
- quy tắc mặc định cho field mới, không tự điền dữ liệu lịch sử không tồn tại;
- xử lý event không hỗ trợ bằng quarantine/DLQ và alert, không lặng lẽ bỏ qua;
- khả năng replay trong môi trường thử nghiệm trước khi chạy thật.

Nếu consumer replay bằng cách query **trạng thái hiện tại** theo `orderId` thay vì dùng fact lịch sử, kết quả có thể khác ở thời điểm gốc. Điều này có thể đúng khi rebuild current-state projection, nhưng không đúng cho mọi mục tiêu (ví dụ báo cáo lịch sử theo ngày). Phải định nghĩa nguồn chân lý và semantics của projection.

## 12. Ordering, concurrency và reprocessing

Nếu event là delta không giao hoán, thứ tự có thể quan trọng:

~~~text
E1: account status = ACTIVE, version=4
E2: account status = SUSPENDED, version=5
~~~

Nếu E2 được áp dụng trước rồi E1 đến muộn, một phép gán mù có thể làm trạng thái trở về ACTIVE. Listener cần bảo vệ bằng:

- aggregate version/sequence, chỉ apply nếu version hợp lệ;
- partition theo `aggregateId` để giữ thứ tự trong phạm vi cần thiết;
- cơ chế concurrency control/optimistic locking;
- khi gap, dừng và fetch missing event thay vì đoán giá trị.

Không trộn `occurredAt`/timestamp với sequence tuyệt đối: clock skew và timestamp cùng độ phân giải có thể gây thứ tự sai. Đừng tuyên bố rằng FIFO của một queue cục bộ bảo đảm thứ tự trên nhiều worker/partition/instance.

Với nghiệp vụ tính tổng doanh thu từ các khoản thanh toán độc lập, phép cộng có tính giao hoán theo giá trị, nhưng **duplicate vẫn làm sai tổng**, nên cần dedup. Với các trạng thái thay đổi theo version, cả **dedup lẫn ordering** đều cần được thiết kế.

## 13. Observability cho listener có thể chạy lại

Metric cần phân biệt:

| Metric đề xuất | Ý nghĩa |
| --- | --- |
| `event.deliveries.total` | Số lần một consumer nhận/được gọi, gồm các lần trùng |
| `event.applied.total` | Số event mới được áp dụng thành công |
| `event.duplicates.skipped.total` | Số lần xử lý trùng được bỏ qua có chủ ý |
| `event.processing.errors.total` | Số attempt lỗi, có phân loại nguyên nhân |
| `event.retry.total` | Số lần retry |
| `event.replay.run.total` | Số lần chạy tác vụ replay |
| `event.replay.lag` | Độ trễ replay/catch-up theo offset hoặc tuổi event |
| `event.inbox.pending` | Số item chưa hoàn thành trong inbox/queue |
| `event.projection.drift` | Sai lệch với dữ liệu nguồn khi có reconciliation |

Những tên này **do ứng dụng tự định nghĩa**, Spring không tự tạo toàn bộ metric trên.

Hãy log tối thiểu `eventType`, `eventId`, `consumer`, `attempt`, `outcome`, `duration`, nguồn replay/normal mode và correlation ID phù hợp. Không đưa `eventId` hay `correlationId` vào metric tags: cardinality tăng theo số event. Không log raw credentials/PII không cần thiết trong event payload hoặc DLQ.

Một chiến dịch replay nên có **run ID** để audit và dashboard theo dõi tiến độ, nhưng run ID không thay thế event ID của sự việc gốc.

## 14. Tình huống lỗi và kỳ vọng đúng

| Tình huống | Kết quả cần mong đợi |
| --- | --- |
| Giao E1 một lần | Projection áp dụng E1, marker commit |
| Giao lại E1 sau thành công | Không áp dụng thêm effect |
| Lỗi trước marker/effect commit | Transaction rollback; retry có thể xử lý lại |
| Crash sau commit nhưng trước ACK | Redelivery -> thấy marker -> skip/ACK |
| Worker A/B xử lý cùng E1 | Unique constraint/claim đồng bộ; không double-apply |
| Hai event ID khác nhau cùng order | Được xử lý riêng nếu là hai fact hợp lệ |
| Lỗi DB timeout/deadlock | Không đánh đồng duplicate; retry/backoff có giới hạn |
| Remote side effect đã xảy ra nhưng local ACK mất | Dùng idempotency key phía đích hoặc reconciliation |
| Rebuild v2 từ history | Dùng projection/marker namespace v2, không bỏ qua vì marker v1 |
| Replay thiếu bản ghi lịch sử | Không thể tái dựng chính xác từ một nguồn không đầy đủ |
| Event schema cũ không hỗ trợ | Upcast/quarantine với audit, không âm thầm drop |
| Event đến ngược thứ tự | Version/sequence hoặc cơ chế chờ gap |
| Consumer vĩnh viễn lỗi (poison event) | Retry budget, DLQ, alert và công cụ reprocess có kiểm soát |

### Không có “exactly-once” miễn phí

Một local transaction có unique marker + projection có thể làm một **database effect** có tính effectively-once trong một phạm vi hẹp. Điều đó không đồng nghĩa mọi API gọi ra, email, push notification và broker commit cùng exactly-once.

Hợp đồng thực tế thường là **at-least-once delivery + idempotent processing**. Quan trọng hơn nhãn “exactly-once” là định nghĩa cụ thể: một event, một consumer, một side effect, một transaction, trường hợp timeout/retry nào được xử lý.

## 15. Những sai lầm phổ biến

**Sai 1 — Cho rằng `@EventListener` tự replay sau restart.** Spring application events mặc định chỉ dispatch; muốn replay cần archive/event store/broker.

**Sai 2 — Dùng `orderId` làm duy nhất khóa dedup.** Một order có thể phát sinh nhiều event khác nhau; phải giữ `eventId` cho từng fact.

**Sai 3 — Sinh lại UUID khi retry.** Khi đó một delivery trùng bị hiểu là event mới.

**Sai 4 — Lưu marker và side effect ở hai transaction.** Crash khiến skip nhầm hoặc double-apply.

**Sai 5 — Chỉ kiểm tra SELECT NOT EXISTS trước INSERT.** Hai worker đồng thời có thể cùng nhìn thấy chưa có marker; cần unique key/atomic claim.

**Sai 6 — Catch mọi `Exception` rồi ACK thành công.** Lỗi DB hoặc external API không được che thành duplicate.

**Sai 7 — Replay toàn bộ bus, vô tình gửi lại email hoặc thu tiền lần nữa.** Rebuild projections cần một đường xử lý riêng với chính sách side effect.

**Sai 8 — Dùng `@Async` như một retry engine.** Async chỉ chuyển thread, không cung cấp log bền vững, retry hay ACK mặc định.

**Sai 9 — Coi `@TransactionalEventListener(AFTER_COMMIT)` là durable.** Callback sau commit có crash window; dùng outbox nếu không được mất event.

**Sai 10 — Xóa projection rồi replay với marker cũ.** Marker vẫn cho rằng mọi event đã xử lý; rebuild phải dùng version/namespace mới.

**Sai 11 — Rebuild bằng dữ liệu hiện tại cho mọi báo cáo lịch sử.** Lịch sử có thể thay đổi/thiếu thông tin. Cần định nghĩa fact bất biến và schema evolution.

**Sai 12 — Chỉ test happy path và một duplicate tuần tự.** Production cần test concurrency, timeout, crash, poison event, schema cũ và cutover.

**Sai 13 — Không kiểm soát quyền replay.** Replay là thao tác có thể chạy nhiều tác vụ; cần IAM, audit, rate limit và tách các consumer có quyền gây side effect.

**Sai 14 — Dùng event payload có raw secret.** Một event được lưu và replay mở rộng phạm vi rò rỉ; chỉ chứa metadata phù hợp và ACL.

## 16. Checklist thiết kế replayable listener

- [ ] Event có `eventId` ổn định, payload immutable và version rõ ràng.
- [ ] Định nghĩa chính xác retry, redelivery, replay và rebuild cho use case.
- [ ] Có nguồn replay phù hợp về durability, retention, completeness và ordering.
- [ ] Dùng khóa dedup theo **consumer + eventId** hoặc mô hình idempotent tương đương.
- [ ] Marker và local effect commit atomically trong cùng transaction.
- [ ] Có unique constraint/atomic claim để chống concurrent duplicate.
- [ ] Phân biệt duplicate đã xử lý với DB lỗi hoặc payload mismatch.
- [ ] Xử lý timeout không rõ kết quả và side effect ngoài DB bằng stable idempotency key.
- [ ] Không gửi lại email/payment chỉ vì rebuild projection.
- [ ] Có namespace/version và chiến lược shadow projection cho reprocessing.
- [ ] Theo dõi schema evolution/upcasting và xử lý event cũ không tương thích.
- [ ] Có kế hoạch catch-up live events và kiểm soát cutover.
- [ ] Đã kiểm thử failure-injection trước commit, retry sau rollback và crash sau commit trước ACK.
- [ ] Đã kiểm thử concurrency, out-of-order, poison event và retry budget khi triển khai.
- [ ] Metrics/logs thể hiện deliveries, applied, duplicates, errors và replay lag.
- [ ] Replay được phân quyền, audit và có giới hạn tác động.
- [ ] Payload không chứa secret, dữ liệu cá nhân thừa hoặc object có vòng đời HTTP/JPA không an toàn.

### Ghi nhớ

~~~text
publishEvent() = dispatch, KHÔNG có event history tự động.

Muốn replay:
    có nguồn event history bền vững và đủ dữ liệu.

Muốn tránh double-apply:
    stable eventId
    + consumer-specific dedup
    + unique constraint
    + marker và local effect cùng transaction.

Muốn rebuild projection:
    chọn consumer/projection version riêng,
    không phát lại các side effect nguy hiểm.

Muốn xử lý crash:
    outbox/broker durable + ACK/retry/idempotency.

Chạy lại an toàn không phải "không có exception".
Chạy lại an toàn là đúng kết quả dù event được giao nhiều lần.
~~~

## Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationContext Events, @EventListener và @Async](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — TransactionTemplate và quản lý transaction bằng code](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Microsoft Azure Architecture Center — Idempotent Consumer Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/idempotent-consumer)

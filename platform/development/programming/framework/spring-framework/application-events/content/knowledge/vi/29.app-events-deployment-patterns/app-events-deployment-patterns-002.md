# Cập nhật read model sau thay đổi domain trong Spring Framework Application Events

## 1. Vì sao cần read model riêng?

Một ứng dụng Spring có thể dùng **domain model** để thực hiện các thao tác nghiệp vụ, đồng thời dùng một **read model** (projection/query model) để phục vụ màn hình tra cứu. Hai mô hình giải quyết hai nhu cầu khác nhau.

- **Write/domain model** biểu diễn aggregate, invariants và những state transitions hợp lệ. Ví dụ Order.markPaid(...) phải xác nhận giao dịch và ngăn thao tác trái luật.
- **Read model** là bảng/tài liệu/dữ liệu denormalized tối ưu cho truy vấn, pagination, dashboard hoặc tìm kiếm. Ví dụ OrderOverview chứa orderId, customerName, status, total, paidAt và lastVersion.
- **Domain event** mô tả sự thật sau một thay đổi hợp lệ, ví dụ OrderPaid(orderId, paymentId, version).
- **Projection handler** tiêu thụ event và cập nhật read model.
- **Query service** đọc read model thay vì phải load nhiều aggregate và join phức tạp cho mỗi request.

Đây là một mẫu của **CQRS nhẹ**: tách trách nhiệm command/write khỏi query/read. Không nhất thiết phải có hai database, Kafka hay một kiến trúc microservices. Một ứng dụng monolith dùng Spring Framework và hai bảng trong cùng database cũng có thể áp dụng.

**Mục tiêu của bài:** Hiểu cách chuyển một thay đổi domain thành event, cập nhật projection sau commit, xử lý rollback, event trùng hoặc đến sai thứ tự, và chọn mức nhất quán phù hợp. Bài có ví dụ hoàn chỉnh Java 17+ dùng Spring JDBC và H2.

~~~text
Command: PayOrder
      |
      v
Application service / transaction
      |
      v
Order aggregate: CREATED -> PAID
      |
      +---- Save domain data
      |
      +---- OrderStateChanged(orderId, state, version)
                          |
                          v
                Projection listener
                          |
                          v
                   OrderOverview
                          |
                          v
                Query API / dashboard
~~~

**Đừng nhầm việc publish event với việc read model đã cập nhật.** Read model có thể được cập nhật trong cùng transaction, ngay sau commit hoặc bất đồng bộ qua broker; từng lựa chọn có tính nhất quán và failure mode khác nhau.

## 2. Domain event nào nên kích hoạt projection?

Một event có ích cho read model nên có ý nghĩa nghiệp vụ rõ và mang dữ liệu đủ để cập nhật projection.

Ví dụ:

~~~java
public record OrderPaid(
        String eventId,
        String orderId,
        String paymentId,
        long aggregateVersion) {}
~~~

Record trên là **Java thuần**, không phải Spring ApplicationEvent subclass. Spring có thể publish POJO như event payload. Nhưng domain không cần biết Spring; một application adapter có thể công bố event hoặc ghi outbox trong transaction.

Các thông tin nên xem xét:

| Trường | Vì sao cần? |
| --- | --- |
| **eventId** | Nhận diện redelivery/trùng khi dùng outbox hoặc broker |
| **aggregateId** | Tìm đúng row/document cần cập nhật |
| **aggregateVersion** | Chặn stale events ghi đè trạng thái mới hơn |
| **eventType** | Phân biệt OrderPlaced, OrderPaid, OrderRefunded |
| **occurredAt** | Hiển thị thời gian nghiệp vụ và đo projection lag |
| **payload snapshot/delta** | Xác định các trường được cập nhật |
| **schemaVersion** | Quản lý tương thích giữa phiên bản producer và consumer |
| **correlationId** | Gắn command, event và projection vào cùng workflow |

**Đừng đưa nguyên JPA entity mutable hoặc lazy-loaded proxy vào event** rồi giữ nó qua async boundary. Nên truyền identity và dữ liệu immutable cần thiết; dữ liệu trong event phải có hợp đồng schema rõ ràng.

Một event như **OrderPaid** là sự thật; **PaymentRequested** là yêu cầu. Không đổi tên tùy tiện để lẫn command với event đã hoàn tất.

## 3. Chọn chiến lược đồng bộ trước khi viết listener

### 3.1. Cập nhật write và read model trong cùng transaction

~~~text
BEGIN TRANSACTION
   validate domain rules
   update orders
   update order_overview
COMMIT
~~~

Khi read model ở **cùng database**, cần read-after-write mạnh và projection đơn giản, đây có thể là lựa chọn tốt nhất. Domain state và read model cùng commit hoặc cùng rollback.

Ưu điểm: không có khoảng trống commit giữa hai bảng. Nhược điểm: command path bị phụ thuộc thêm vào chi phí ghi projection, lock và schema; việc cập nhật sang một datastore khác không nằm trong transaction local này.

Có thể gọi projection component trực tiếp trong application service, thay vì dùng event. **Đừng ép event-driven chỉ vì có @EventListener** nếu một call rõ ràng giúp bảo vệ invariant tốt hơn.

### 3.2. Sử dụng @EventListener đồng bộ ngay khi publish

~~~java
@EventListener
public void on(OrderPaid event) {
    projector.apply(event);
}
~~~

Đây là **snippet minh họa**, cần Spring-managed bean, event definition và projector. Với **SimpleApplicationEventMulticaster** mặc định, listener có thể được gọi **trước commit**, ngay trong lúc service gọi **ApplicationEventPublisher.publishEvent(...)**. Nếu listener ghi sang hệ thống khác rồi domain transaction rollback, projection có thể thể hiện một sự kiện nghiệp vụ chưa thực sự commit.

Một synchronous listener ghi **cùng DB transaction** có thể cho atomicity, nhưng phải kiểm tra transaction boundary, multicaster configuration và ordering. Một cấu hình executor/@Async sẽ làm giả định “cùng thread, cùng transaction” không còn đúng.

### 3.3. @TransactionalEventListener(AFTER_COMMIT)

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPaid event) {
    projector.apply(event);
}
~~~

Đoạn này là snippet. Spring sẽ kích hoạt handler khi transaction gắn với event **commit thành công**. Nếu transaction rollback, callback AFTER_COMMIT không được gọi. Theo mặc định **fallbackExecution=false**: event publish ngoài transaction phù hợp sẽ bị bỏ qua bởi transactional listener.

**Điểm cực kỳ quan trọng:** callback **AFTER_COMMIT** chạy sau khi transaction chính đã commit, nhưng transaction resources có thể vẫn còn gắn với thread. Nếu code tiếp tục ghi database mà không mở **transaction mới**, các thay đổi có thể không được commit. Khi cập nhật read model sau commit, cần **PROPAGATION_REQUIRES_NEW** qua Spring-managed service proxy hoặc TransactionTemplate, như demo phần 6.

AFTER_COMMIT **không atomic** với domain commit. Nếu JVM chết hoặc projector gặp lỗi sau commit, domain đã thay đổi nhưng projection có thể vẫn cũ. Cần cơ chế phục hồi khi read model quan trọng.

### 3.4. Outbox + consumer: cập nhật eventually consistent

~~~text
BEGIN WRITE DB TRANSACTION
    update orders
    insert outbox(OrderPaid)
COMMIT
      |
      v
Outbox relay / CDC
      |
      v
Durable broker / message transport
      |
      v
Idempotent projection consumer
      |
      v
Read database / search index
~~~

**Transactional outbox** giữ business state và ý định phát event trong cùng commit. Relay có thể đọc lại event sau crash và retry giao. Consumer đọc message rồi cập nhật read model trong transaction của chính nó.

Ưu điểm: tách command khỏi query infrastructure, có khả năng phục hồi sau restart và mở rộng nhiều consumers. Nhược điểm: **eventual consistency**, vận hành relay/broker, sự kiện trùng hoặc đảo thứ tự, schema migration và backlog. **Outbox + retry thường là at-least-once**, không có exactly-once end-to-end tự động.

### 3.5. So sánh

| Tiêu chí | Cùng DB transaction | AFTER_COMMIT in-process | Outbox + consumer |
| --- | --- | --- | --- |
| Projection sẵn sàng ngay khi write commit | Có nếu các writes cùng TX | Không đảm bảo trước commit; thường được cập nhật ngay sau | Không; read side có thể lag |
| Domain rollback | Cả hai cùng rollback | Callback commit bị bỏ qua | Outbox cũng rollback cùng domain |
| Process chết sau commit | Hai bảng đã cùng commit | Callback có thể bị mất | Outbox vẫn còn nếu DB durable |
| Read model ở database khác | Không chia sẻ local TX dễ dàng | Có thể gọi nhưng không bền vững | Phù hợp |
| Thứ tự và duplicate | Ít vấn đề nếu một transaction | Cần kiểm tra nếu replay | Phải thiết kế idempotency/ordering |
| Query SLA | Dễ read-after-write | Có thể cần trạng thái chờ | Cần lag budget/watermark |
| Độ phức tạp | Thấp hơn | Trung bình | Cao hơn: relay, retry, monitoring |

**Chọn theo hợp đồng dữ liệu trước, công cụ sau.** Không phải mọi projection đều cần Kafka; cũng không phải mọi read model chậm là sai.

## 4. Thiết kế write model và read model

Giả sử command side có bảng:

~~~sql
CREATE TABLE domain_orders (
    order_id VARCHAR(80) PRIMARY KEY,
    state VARCHAR(30) NOT NULL,
    row_version INTEGER NOT NULL
);
~~~

Read side có bảng tối ưu cho query:

~~~sql
CREATE TABLE order_overview (
    order_id VARCHAR(80) PRIMARY KEY,
    state VARCHAR(30) NOT NULL,
    row_version INTEGER NOT NULL
);
~~~

Demo dùng các cột tối giản để thấy rõ transaction và version guard. Production read model thường có thêm customerDisplayName, itemCount, totalMinorUnits, paidAt, shippingStatus và các index đáp ứng pattern truy vấn thực tế.

**row_version trong read model** cho biết version của domain aggregate mà row đã materialize. Nó giúp chặn event cũ ghi đè event mới, và cho client biết query side đã bắt kịp expectedVersion hay chưa.

### Snapshot vs delta

- **Snapshot event** chứa trạng thái mới, ví dụ OrderOverviewChanged(orderId, status, version). Projection có thể áp dụng idempotently bằng cách SET dữ liệu nếu event mới hơn.
- **Delta event** chứa thay đổi, ví dụ OrderItemAdded(orderId, itemId, quantity, version). Nếu cộng thêm itemCount hoặc total nhiều lần vì redelivery, kết quả sai; cần processed-event ledger và ordering rõ.
- **Event chỉ chứa ID** buộc projector truy vấn write model để lấy current state. Cách này đơn giản cho current-state read model nhưng không bảo đảm event replay lịch sử sẽ có kết quả đúng từng bước.

Nếu yêu cầu xây projection lại từ event log, payload phải đủ dữ liệu hoặc có snapshot/history source thích hợp. Không suy rằng một event ID đơn thuần cho phép dựng lại trạng thái đã mất.

## 5. Event được publish khi nào trong use case?

Ứng dụng thường phát event theo một trong các mẫu:

**Mẫu A — Application service publish sau khi domain mutation đã được chấp nhận:**

~~~java
@Transactional
public void payOrder(String orderId, String paymentId) {
    Order order = orders.load(orderId);
    order.markPaid(paymentId);
    orders.save(order);
    publisher.publishEvent(
            new OrderPaid(newEventId(), orderId, paymentId,
                          order.version()));
}
~~~

Snippet này chưa có đầy đủ imports/classes. Nếu dùng AFTER_COMMIT listener, publication diễn ra **trong transaction đang hoạt động** để Spring đăng ký callback. Nếu dùng outbox, phải **ghi outbox record trong cùng transaction**, không chỉ dựa vào publishEvent.

**Mẫu B — Aggregate thu thập domain events:**

~~~text
Order.markPaid()
  -> mutate aggregate
  -> record OrderPaid in pendingEvents
Application service
  -> save aggregate and persist outbox events in the same transaction
  -> clear published/persisted pendingEvents according to contract
~~~

Đây là mô hình domain độc lập framework. Cần xác định lúc nào clear pending events; không xóa event khỏi aggregate rồi để transaction/outbox thất bại không có cách retry trong cùng unit of work.

Trong Spring Data có cơ chế **@DomainEvents** trên aggregate để thu thập/phát sự kiện ở những repository operations tương ứng. Nhưng **@DomainEvents** tự nó không tạo một durable outbox hoặc đảm bảo listener hậu commit; phải kiểm tra lifecycle cụ thể của repository, transaction và application configuration.

## 6. Ví dụ Java 17+ chạy được: domain commit rồi cập nhật read model

Demo dùng **Java 17+**, **Spring Framework 6.2.9**, **Spring JDBC**, **H2 2.3.232**, **Gradle 8.x**. Không cần Spring Boot, broker hay web server.

Mục tiêu:

1. TransactionTemplate lưu domain state và publish event.
2. Listener **@TransactionalEventListener(AFTER_COMMIT)** chỉ xử lý sau commit thành công.
3. Projector dùng **REQUIRES_NEW** khi ghi read model ở callback hậu commit.
4. Một transaction rollback không tạo projection.
5. Event cũ hoặc cùng version được gửi lại không làm trạng thái mới bị ghi đè.

Demo dùng H2 **in-memory** và **một worker đồng bộ**, không chứng minh multi-consumer race safety hoặc crash recovery. Dùng outbox nếu muốn event không bị mất sau restart.

### 6.1. Cấu trúc thư mục

~~~text
read-model-demo/
  build.gradle
  src/main/java/demo/ReadModelDemo.java
~~~

File **build.gradle**:

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
    mainClass = 'demo.ReadModelDemo'
}
~~~

### 6.2. File Java hoàn chỉnh

File **src/main/java/demo/ReadModelDemo.java**:

~~~java
package demo;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public final class ReadModelDemo {

    public record OrderStateChanged(
            String orderId, String state, int version) {}

    public static final class Commands {
        private final JdbcTemplate db;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        public Commands(
                JdbcTemplate db,
                PlatformTransactionManager manager,
                ApplicationEventPublisher publisher) {
            this.db = db;
            this.tx = new TransactionTemplate(manager);
            this.publisher = publisher;
        }

        public void change(
                String id, String newState, int version, boolean rollback) {
            tx.executeWithoutResult(status -> {
                if (version == 1) {
                    db.update(
                        "INSERT INTO domain_orders "
                        + "(order_id, state, row_version) "
                        + "VALUES (?, ?, ?)",
                        id, newState, version);
                } else {
                    int changed = db.update(
                        "UPDATE domain_orders "
                        + "SET state = ?, row_version = ? "
                        + "WHERE order_id = ? AND row_version = ?",
                        newState, version, id, version - 1);
                    if (changed != 1) {
                        throw new IllegalStateException(
                            "invalid domain transition");
                    }
                }

                publisher.publishEvent(
                    new OrderStateChanged(id, newState, version));

                System.out.println(
                    "domain: " + id + "=" + newState + " v" + version);

                if (rollback) {
                    status.setRollbackOnly();
                }
            });
        }

        public void replay(
                String id, String state, int version) {
            // Replay/duplicate chỉ để kiểm tra projector.
            tx.executeWithoutResult(status ->
                publisher.publishEvent(
                    new OrderStateChanged(id, state, version)));
        }
    }

    public static final class Projector {
        private final JdbcTemplate db;
        private final TransactionTemplate writeReadModelTx;

        public Projector(
                JdbcTemplate db, PlatformTransactionManager manager) {
            this.db = db;
            this.writeReadModelTx = new TransactionTemplate(manager);
            this.writeReadModelTx.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        }

        public void apply(OrderStateChanged event) {
            writeReadModelTx.executeWithoutResult(status -> {
                List<Integer> versions = db.query(
                    "SELECT row_version FROM order_overview "
                    + "WHERE order_id = ?",
                    (rs, row) -> rs.getInt("row_version"),
                    event.orderId());

                if (!versions.isEmpty()
                        && versions.get(0) >= event.version()) {
                    System.out.println(
                        "projection: ignored "
                        + event.orderId() + " v" + event.version());
                    return;
                }

                if (versions.isEmpty()) {
                    db.update(
                        "INSERT INTO order_overview "
                        + "(order_id, state, row_version) "
                        + "VALUES (?, ?, ?)",
                        event.orderId(), event.state(), event.version());
                } else {
                    int updated = db.update(
                        "UPDATE order_overview "
                        + "SET state = ?, row_version = ? "
                        + "WHERE order_id = ? AND row_version < ?",
                        event.state(), event.version(),
                        event.orderId(), event.version());

                    if (updated != 1) {
                        System.out.println(
                            "projection: ignored "
                            + event.orderId() + " v" + event.version());
                        return;
                    }
                }

                System.out.println(
                    "projection: applied "
                    + event.orderId() + "=" + event.state()
                    + " v" + event.version());
            });
        }

        public String find(String id) {
            List<String> rows = db.query(
                "SELECT state, row_version FROM order_overview "
                + "WHERE order_id = ?",
                (rs, row) -> rs.getString("state")
                        + " v" + rs.getInt("row_version"),
                id);
            return rows.isEmpty() ? "none" : rows.get(0);
        }
    }

    public static final class ProjectionListener {
        private final Projector projector;

        public ProjectionListener(Projector projector) {
            this.projector = projector;
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void on(OrderStateChanged event) {
            projector.apply(event);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:read_model_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            JdbcTemplate jdbc = new JdbcTemplate(ds);
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS domain_orders ("
                + "order_id VARCHAR(80) PRIMARY KEY, "
                + "state VARCHAR(30) NOT NULL, "
                + "row_version INTEGER NOT NULL)");
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS order_overview ("
                + "order_id VARCHAR(80) PRIMARY KEY, "
                + "state VARCHAR(30) NOT NULL, "
                + "row_version INTEGER NOT NULL)");
            return jdbc;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        Projector projector(
                JdbcTemplate jdbc, PlatformTransactionManager manager) {
            return new Projector(jdbc, manager);
        }

        @Bean
        ProjectionListener projectionListener(Projector projector) {
            return new ProjectionListener(projector);
        }

        @Bean
        Commands commands(
                JdbcTemplate jdbc,
                PlatformTransactionManager manager,
                ApplicationEventPublisher publisher) {
            return new Commands(jdbc, manager, publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Commands commands = context.getBean(Commands.class);
            Projector projector = context.getBean(Projector.class);

            commands.change("A", "CREATED", 1, false);
            commands.change("A", "PAID", 2, false);
            commands.change("B", "CREATED", 1, true);

            commands.replay("A", "CREATED", 1);
            commands.replay("A", "PAID", 2);

            System.out.println("query A: " + projector.find("A"));
            System.out.println("query B: " + projector.find("B"));
        }
    }
}
~~~

Chạy từ thư mục **read-model-demo**:

~~~bash
gradle --console=plain -q run
~~~

**Stdout do chương trình tự in ra**, bỏ qua log khác từ Gradle/môi trường:

~~~text
domain: A=CREATED v1
projection: applied A=CREATED v1
domain: A=PAID v2
projection: applied A=PAID v2
domain: B=CREATED v1
projection: ignored A v1
projection: ignored A v2
query A: PAID v2
query B: none
~~~

### 6.3. Giải thích kết quả

- **A v1:** transaction ghi domain order rồi publish **OrderStateChanged(A, CREATED, 1)**. Dòng log domain nằm trong transaction. Sau commit, Spring kích hoạt listener; projector mở **REQUIRES_NEW** transaction và ghi read row version 1.
- **A v2:** command cập nhật domain từ version 1 lên 2, ghi PAID; sau commit projector áp dụng version mới vì version 2 lớn hơn 1.
- **B v1:** command ghi domain và publish event nhưng đặt rollback-only. Domain insert B rollback, **AFTER_COMMIT listener không chạy**, nên read model không có B.
- **Replay v1:** một transaction riêng chỉ phát lại event cũ. Projector thấy read version 2, bỏ qua stale v1.
- **Duplicate v2:** projector thấy read model đang ở version 2, bỏ qua event cùng version.
- Cuối cùng, **query A** trả **PAID v2**, còn **query B** không có row.

Đây là ví dụ cho **một worker, một database, hai transactions**. Không có broker/outbox, do đó nếu JVM chết sau domain commit mà chưa ghi projection, update có thể bị mất. Không chuyển code trực tiếp thành production relay.

### 6.4. Vì sao phải mở transaction mới trong projector?

Theo Javadoc **@TransactionalEventListener**, lúc AFTER_COMMIT chạy, transaction chính đã hoàn thành nhưng resources có thể vẫn accessible. Một lời gọi JdbcTemplate/repository mà không mở transaction mới có thể tham gia resources cũ và **không được commit**. Demo sử dụng:

~~~java
this.writeReadModelTx.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW);
~~~

Một cách khác là gọi method trên **Spring-managed service** có **@Transactional(propagation = Propagation.REQUIRES_NEW)** thông qua Spring proxy. Không dùng self-invocation để kích hoạt advice rồi giả định interceptor vẫn áp dụng.

## 7. Chống xử lý trùng và đảo thứ tự

### 7.1. Version guard cho snapshot projection

Giả sử có events:

~~~text
OrderCreated v1
OrderPaid v2
OrderRefunded v3
~~~

Nếu projector nhận **v3 trước v2**, một current-state snapshot đủ dữ liệu có thể được apply khi version lớn hơn version lưu. Khi v2 tới sau, bỏ qua để không ghi đè trạng thái mới.

Nhưng với **delta event** như **LineItemAdded(+2 items)** hoặc **BalanceIncremented(+100)**, bỏ qua một event cũ có thể làm sai tổng. Delta projection cần lưu processed event IDs/sequence, áp dụng đúng từng thay đổi hoặc có rebuild path.

### 7.2. Dedup bằng event ID

Một consumer dùng at-least-once thường cần:

~~~text
BEGIN consumer DB transaction
  INSERT processed_events(consumer_name, event_id)
  nếu event_id đã tồn tại:
      bỏ qua business effect
  nếu mới:
      cập nhật read model
COMMIT
ACK broker
~~~

**Marker xử lý và read model update phải ở cùng local transaction**, với unique constraint phù hợp. Không commit marker rồi mới cập nhật read model trong transaction khác, vì crash giữa hai bước khiến retry bị bỏ qua và projection không bao giờ hoàn tất.

Một event có nhiều projector khác nhau phải dedup theo **(consumerName, eventId)** hoặc key tương đương. Không dùng một processed flag toàn cục rồi chặn những subscribers hợp lệ khác.

### 7.3. Concurrent workers

Demo sử dụng **SELECT row_version rồi INSERT/UPDATE**, đủ để minh họa khi chỉ có một worker. Nhưng nhiều workers có thể cùng thấy chưa có row, hoặc cùng đọc version cũ. Production cần:

- **Unique key** trên projection identity.
- **Atomic conditional upsert/compare-and-set** theo dialect.
- **Row lock / optimistic locking**, conflict retries hoặc single-writer partition theo aggregate.
- **Ordering key** và checkpoints nếu event cần xử lý tuần tự.
- Integration tests có concurrency/race injection.

Không coi một kiểm tra phiên bản trong Java là cơ chế đồng bộ hóa đủ mạnh khi nhiều consumers chạy đồng thời.

## 8. Query API và eventual consistency

Một user thực hiện **PayOrder** rồi ngay lập tức gọi endpoint query. Với async projection, domain đã PAID nhưng read model có thể vẫn CREATED. Đây là **read-model lag**, không mặc định nghĩa payment thất bại.

Các hợp đồng tốt hơn:

1. **Trả expectedVersion từ command:** client nhận version mới đã commit.
2. **Expose projectionVersion:** query trả version mà read model đã áp dụng.
3. **Poll với timeout/backoff:** chờ khi projectionVersion đạt expectedVersion, hoặc hiển thị “đang đồng bộ”.
4. **Read-your-writes fallback:** nếu bắt buộc phản hồi mới ngay, đọc write side cho thao tác vừa cập nhật.
5. **Optimistic UI:** cập nhật giao diện theo command result và làm rõ trạng thái pending.

Ví dụ minh họa, không phải endpoint sẵn của Spring Framework:

~~~text
POST /orders/A/pay
-> { "orderId": "A", "expectedVersion": 12 }

GET /orders/A/overview
-> { "status": "PAID", "projectionVersion": 12 }
~~~

**Không retry lại command thanh toán chỉ vì projection chưa theo kịp.** Điều này có thể gây duplicate side effect. Command cần idempotency riêng; read model lag là vấn đề của query side.

## 9. Một projection từ nhiều event sources

~~~text
OrderPlaced ---------------------+
PaymentCaptured -----------------+--> OrderOverview
ShipmentScheduled ---------------+
CustomerDisplayNameChanged ------+
~~~

Một read row có thể tổng hợp nhiều bounded contexts. Khi đó:

- **Order version** và **Customer version** không dùng chung một đồng hồ; không so sánh số version từ hai aggregates khác nhau như một thứ tự toàn cục.
- Xác định **field ownership**: payment event cập nhật payment fields, shipment event cập nhật shipping fields.
- Dùng per-source checkpoint/version hoặc processed-event ledger.
- Khi thiếu một event, một vài fields có thể stale dù các trường khác cập nhật; cần reconciliation.
- Projection chỉ chứa current-state đôi khi phải thiết kế một **join/aggregation pipeline** có chiến lược chờ đủ dữ liệu và timeout.

Nếu update là **increment counter**, event trùng gây cộng trùng; dùng atomic dedup và transactional effect. Nếu cập nhật “set status=PAID at version 12”, version guard giúp idempotency dễ hơn.

## 10. Rebuild, replay và backfill

Read model là dữ liệu dẫn xuất. Khi đổi schema hoặc logic projector, nên có khả năng rebuild:

~~~text
Durable event log / write-store snapshot
                   |
                   v
         Build projection_v2
                   |
                   v
     Validate count/checksum/queries
                   |
                   v
      Catch up with live event stream
                   |
                   v
      Switch read traffic to v2
~~~

**Spring ApplicationEventPublisher không giữ lịch sử event mặc định.** Nếu chỉ dùng @EventListener in-process, bạn không tự có replay. Muốn dựng lại từ history, cần retained event log/event store/outbox archive đủ dữ liệu. Nếu chỉ còn write DB current state, có thể rebuild **current-state snapshot projection** bằng backfill, nhưng không nhất thiết dựng được mọi event history.

Trong production nên rebuild ở **shadow table/index**, catch-up với live events rồi chuyển read traffic có kiểm tra. Giữ version/checkpoint, test schema compatibility và khả năng rollback cutover.

**Không để replay projection kích hoạt side effect nghiệp vụ** như gửi email, tạo payment hoặc gửi command ngoài hệ thống. Tách read model projector khỏi listener thực thi side effect.

### Delete và tombstone

Nếu domain phát **OrderDeleted v5**, projector có thể xóa row, ẩn row hoặc ghi tombstone có version để event **OrderCreated v1** đến muộn không tạo lại row. Quyết định phụ thuộc chính sách retention, quyền riêng tư và hợp đồng query.

## 11. Read model không phải nơi bảo vệ domain invariant

Các quyết định quan trọng như số dư đủ rút tiền, kho còn đủ hàng, voucher đã dùng hay payment đã chắc chắn hoàn tất phải được xác nhận ở **write/domain owner**. Read model có thể trễ, denormalized và bị rebuild.

Chỉ dùng projection cho **truy vấn/hiển thị** theo hợp đồng của nó. Nếu read store được định nghĩa là nguồn chính thức cho một loại dữ liệu khác, đó là ownership decision riêng; không tự dùng read model event-driven làm nguồn xác minh mọi business mutation.

## 12. Những bài test cần có

| Test | Cần xác nhận |
| --- | --- |
| Commit domain change | Projection có status/version mới sau đúng phase |
| Rollback domain transaction | AFTER_COMMIT handler không tạo read row |
| Duplicate event | Side effect/projection không bị áp dụng hai lần |
| Stale event | Version cũ không ghi đè version mới |
| New event sau multiple updates | Query state và lastVersion đúng |
| Mất DB read side trong lúc xử lý | Event bền vững vẫn có thể retry nếu dùng outbox |
| Consumer crash sau effect trước ACK | Redelivery được dedup |
| Concurrent projectors | Không race/overwrite với unique key và conditional update |
| Rebuild | Query output bằng dữ liệu kỳ vọng sau replay/backfill |
| Query ngay sau command | API xử lý projection lag như hợp đồng |
| Schema version mismatch | Consumer có chiến lược compatibility/parking |
| Shutdown/restart | Resume từ outbox/offset/checkpoint đúng |

**Test trực tiếp projector.apply(event)** chỉ kiểm tra mapping. Để test **Spring @TransactionalEventListener**, phải publish event qua một Spring **ApplicationContext** thật trong transaction do manager thật quản lý. Test method có **@Transactional** thường rollback mặc định trong Spring TestContext; để kiểm tra AFTER_COMMIT trong cùng test có thể dùng **TestTransaction.flagForCommit(); TestTransaction.end()** hoặc một TransactionTemplate chủ động ngoài test-managed transaction.

Với async consumer, không dựa vào Thread.sleep() cố định; dùng CountDownLatch, Awaitility hoặc poll persisted projectionVersion có timeout.

## 13. Monitoring và điều tra projection lag

Một pipeline projection nên cung cấp:

| Metric/log field | Ý nghĩa |
| --- | --- |
| **projection_applied_total** | Số event đã áp dụng |
| **projection_duplicate_ignored_total** | Số event trùng được bỏ qua |
| **projection_stale_ignored_total** | Số event cũ bị chặn |
| **projection_failed_total** | Event lỗi |
| **projection_lag_seconds** | Thời gian từ domain commit/event đến projection |
| **projection_version/checkpoint** | Watermark xử lý |
| **outbox_pending_count** | Event đang chờ được giao |
| **oldest_pending_event_age** | Event kẹt lâu nhất |
| **rebuild_progress** | Tiến độ backfill |
| **reconciliation_mismatch_count** | Khác biệt giữa domain state và read model |

Log **eventId, aggregateId, version, projectorName, traceId, attempt, result**, tránh log thông tin nhạy cảm của payload. Với broker, truyền trace context qua headers; với async thread pool, cấu hình propagation phù hợp. **Có cùng trace ID không đồng nghĩa cùng transaction**.

Nên có job định kỳ đối chiếu write/read data theo những invariants quan trọng, thay vì chỉ kiểm tra consumer process còn chạy.

## 14. Các lỗi thiết kế phổ biến

| Sai lầm | Hệ quả | Sửa thế nào |
| --- | --- | --- |
| Dùng @EventListener trước commit cập nhật DB khác | Projection phản ánh một transaction đã rollback | Cùng DB transaction hoặc AFTER_COMMIT/outbox |
| Ghi DB trong AFTER_COMMIT mà không có TX mới | Update có thể không được commit | REQUIRES_NEW và integration test |
| Nghĩ AFTER_COMMIT bảo đảm event không mất | Crash sau commit vẫn mất callback | Transactional outbox |
| Không có aggregate version | Stale event ghi đè state mới | Version guard/sequence |
| Chỉ có version nhưng delta event cần mọi bước | Dữ liệu cộng dồn sai | Inbox + strict sequence/replay |
| Không dedup eventId | Redelivery tạo duplicate side effect | Dedup marker và effect cùng transaction |
| SELECT rồi INSERT trên nhiều workers không khóa | Race condition | Atomic upsert/unique key |
| Gửi nguyên JPA entity mutable làm payload | Coupling/lazy loading errors | Immutable event/envelope |
| Handler luôn query write store | Replay khó đúng lịch sử | Snapshot/delta hợp đồng rõ |
| Dùng timestamp làm ordering tuyệt đối | Clock skew/concurrent writes | Aggregate version |
| Dùng một version cho nhiều nguồn độc lập | Ghi đè các fields khác ownership | Per-source version/checkpoint |
| Để replay gửi lại notification | Side effect trùng | Tách projector và business action |
| Để read model quyết định payment retry | Projection lag gây double charge | Write owner và idempotent command |
| Không có rebuild/backfill | Search/read index hỏng không phục hồi | Durable history/snapshot và shadow rebuild |
| Test chỉ verify publishEvent | Không chứng minh data mới đã commit | Assert persisted projection và transaction outcomes |

## 15. Checklist trước khi đưa vào production

1. **Mục đích của read model và query patterns đã rõ chưa?**
2. **Thay đổi domain nào phát event, event mang ID/version gì?**
3. **Chọn strong consistency hay eventual consistency vì yêu cầu nào?**
4. **Nếu dùng AFTER_COMMIT, projector có transaction mới khi ghi DB không?**
5. **Nếu process chết sau domain commit, còn durable outbox/replay path không?**
6. **Consumer có xử lý duplicate và stale/out-of-order events không?**
7. **Version có phạm vi theo aggregate/source phù hợp không?**
8. **Concurrent workers có atomic upsert/locking không?**
9. **Read API có expectedVersion/projectionVersion hoặc lag policy không?**
10. **Tombstone/delete event có ngăn record cũ tái xuất hiện không?**
11. **Có lịch sử/snapshot để rebuild, và có test cutover không?**
12. **Projection không phát side effects nguy hiểm khi replay chứ?**
13. **Có tests commit/rollback/retry/restart/rebuild/concurrency chưa?**
14. **Có monitoring lag, backlog, errors và reconciliation chưa?**

**Kết luận:** Trong Spring Framework, **domain event** giúp tách logic nghiệp vụ khỏi việc materialize **read model**. Nếu cập nhật sau commit trong cùng ứng dụng, hãy dùng **@TransactionalEventListener(AFTER_COMMIT)** và **transaction mới cho read model write**. Nếu projection phải sống sót khi process crash, chọn **transactional outbox và idempotent consumer**. Luôn thiết kế **version/ordering**, hợp đồng **eventual consistency**, và khả năng **replay/rebuild**; read model là dữ liệu dẫn xuất, không thay thế các invariants của domain.

### Tài liệu chính thức

- Spring Framework 6.2 — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — *Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework Javadoc 6.2.9 — *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework Javadoc 6.2.9 — *TransactionTemplate*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework Javadoc 6.2.9 — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html

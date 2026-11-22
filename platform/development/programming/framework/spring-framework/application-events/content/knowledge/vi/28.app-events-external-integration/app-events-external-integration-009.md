# Phân tách domain event và integration event trong Spring Framework

## 1. Bài toán: một thay đổi nghiệp vụ, hai loại hợp đồng

Trong Domain-Driven Design (DDD), **domain event** diễn tả một sự thật có ý nghĩa với mô hình nghiệp vụ: `OrderPaid`, `InvoiceIssued`, `StockReserved`. Trong khi đó, **integration event** là thông điệp được thiết kế để các **ứng dụng/dịch vụ bên ngoài** tiêu thụ qua message broker, webhook, API hoặc một hệ tích hợp khác.

Hai loại event đôi khi cùng nói về một sự thật nhưng có trách nhiệm khác nhau:

- **Domain event** phục vụ mô hình domain và các module nội bộ; phản ánh thuật ngữ, invariant và vòng đời nghiệp vụ. Nó có thể thay đổi khi refactor domain, và không mặc nhiên là public API.
- **Integration event** là **hợp đồng giao tiếp giữa những bên triển khai độc lập**. Nó phải có schema, version, metadata, quyền truy cập, độ tương thích, serialization, định tuyến và chính sách giao nhận rõ ràng.

Nếu publish **nguyên object domain event** ra Kafka/RabbitMQ rồi cho bên ngoài phụ thuộc trực tiếp vào tên class Java và mọi field nội bộ, ta đã biến cấu trúc domain thành hợp đồng public ngoài ý muốn. Một lần đổi tên `OrderPaid` thành `PaymentCaptured`, tách aggregate hoặc đổi kiểu ID trong code nội bộ có thể làm hàng loạt consumer bên ngoài hỏng.

Ngược lại, nếu ép domain luôn sinh ra message JSON theo schema của broker, mô hình domain sẽ phụ thuộc infrastructure và khó thay đổi vì những ràng buộc không thuộc nghiệp vụ.

**Nguyên tắc trung tâm:** domain phát biểu "điều gì đã xảy ra"; integration boundary quyết định "điều gì được phép/đủ để công bố ra ngoài, theo hợp đồng nào và bằng cơ chế bền vững nào".

```text
                      DOMAIN / APPLICATION
Command: pay order
        |
        v
Order aggregate / domain service
        |
        +-- validates invariant, changes state
        +-- records OrderPaid (domain event)
                    |
                    v
            Application boundary
                    |
                    +-- internal listener: update internal read model
                    |
                    +-- Domain -> Integration mapper
                               |
                               +-- allowlist fields
                               +-- public event type + schema version
                               +-- stable event ID / correlation
                               v
                         PaymentConfirmedV1
                               |
                               v
                     Transactional outbox
                               |
                        database COMMIT
                               |
                               v
                          Relay / broker
                               |
                               v
                       External consumers
```

Trong ví dụ này, domain event **không tự được broker nhìn thấy**; integration event là sản phẩm của tầng ánh xạ chuyên trách.

## 2. So sánh domain event và integration event

| Góc nhìn | Domain event | Integration event |
| --- | --- | --- |
| Đối tượng sử dụng | Aggregate, application service, module nội bộ | Hệ thống/đội phát triển bên ngoài boundary |
| Mục đích | Diễn tả business fact trong bounded context | Công bố thay đổi/contract để bên khác phản ứng |
| Ngôn ngữ | Ubiquitous language của domain | Ngôn ngữ đã thống nhất giữa publisher và consumers |
| Ownership | Domain/bounded context sở hữu | Provider sở hữu schema và chính sách compatibility |
| Mức ổn định | Có thể đổi khi domain model refactor | Cần quản lý phiên bản và deprecation |
| Hình thức | Java record/class, domain abstraction, có thể là in-memory | JSON/Avro/Protobuf/message envelope theo contract |
| Dữ liệu | Chi tiết đủ cho phản ứng nội bộ, vẫn phải bảo mật | Dữ liệu tối thiểu được phép chia sẻ, được versioned |
| Transport | Spring Application Events hoặc domain event collection | Broker, queue, webhook, integration API |
| Thời điểm | Có thể ghi nhận trong quá trình transaction | Thường chỉ phân phối khi thay đổi bền vững được commit |
| Reliability | Chưa mặc định có durability | Cần định nghĩa retry, delivery, outbox, deduplication |
| Consumer autonomy | Coupling trong cùng sản phẩm/process có thể chấp nhận | Consumer triển khai độc lập, không dựa vào JVM internals |
| Testing | Domain unit test và internal module integration | Contract, schema compatibility và end-to-end integration |

Hai loại này không nhất thiết là hai class trong mọi hệ thống nhỏ. Nhưng **khác biệt trách nhiệm phải rõ**. Khi một sự kiện vượt bounded context hoặc đi ra broker/public integration, việc tạo contract riêng thường giúp kiểm soát thay đổi và bảo mật tốt hơn.

### Hai ví dụ payload

Domain event nội bộ:

```java
record OrderPaid(
        String eventId,
        String orderId,
        long amountCents,
        String currency,
        String internalRiskCode) {}
```

Integration event được công bố:

```java
record PaymentConfirmedV1(
        String eventId,
        String orderId,
        long amountCents,
        String currency,
        int schemaVersion) {}
```

Trường `internalRiskCode` là dữ liệu kỹ thuật/nghiệp vụ nội bộ không cần chia sẻ với bên ngoài. Integration event có schema version ổn định và chỉ chứa các trường consumer cần theo hợp đồng. Hai đoạn này chỉ minh họa kiểu record; project Maven hoàn chỉnh ở mục 7.

**Lưu ý:** `orderId`, `eventId` và `internalRiskCode` đều có thể nhạy cảm tùy miền dữ liệu. Opaque ID không tự biến dữ liệu thành ẩn danh. Không gửi cả entity/DTO gốc để "consumer tự lấy field cần".

## 3. Domain event được tạo khi nào?

Một domain event phải được tạo từ **một thay đổi hợp lệ** của domain, ví dụ `Order.pay()` sau khi kiểm tra đơn chưa thanh toán, amount hợp lệ và trạng thái thanh toán đã được chấp nhận. Với aggregate root, có thể dùng pending events:

```java
// Trích đoạn thuộc aggregate, không phải một file hoàn chỉnh.
private final List<Object> pendingEvents = new ArrayList<>();

void pay(Payment payment) {
    if (paid) throw new IllegalStateException("Order already paid");

    paid = true;
    pendingEvents.add(
            new OrderPaid(eventId, id, payment.amountCents(),
                    payment.currency(), internalRiskCode));
}

List<Object> pendingEvents() {
    return List.copyOf(pendingEvents);
}
```

Domain có thể thu thập nhiều sự kiện cho một command. Việc gọi `registerEvent` hoặc thêm vào list **không đồng nghĩa** event đã được publish ra Spring hoặc broker. Application service hoặc repository boundary chịu trách nhiệm lấy event ra và điều phối sau khi state hợp lệ.

Spring Data Commons cung cấp `@DomainEvents`, `@AfterDomainEventPublication` và `AbstractAggregateRoot` để hỗ trợ công bố events khi sử dụng repository operations thích hợp. Tuy nhiên những cơ chế này **không tự chuyển events thành durable broker messages**, và callback "after domain event publication" không có nghĩa transaction đã commit hoặc mọi listener đã xử lý xong.

Một số domain events có thể hữu ích chỉ trong một bounded context, ví dụ "pricing rule recomputed". Đừng công bố tất cả events chỉ vì chúng tồn tại. External consumers nên nhìn một tập **được lựa chọn có chủ đích**.

## 4. Integration event là hợp đồng bên ngoài, không phải bản copy entity

Khi thông điệp vượt ranh giới ứng dụng, phải quyết định:

1. **Ý nghĩa sự kiện:** "OrderPaid" có nghĩa đã xác nhận thanh toán nội bộ, đã thu tiền thành công, hay chỉ gửi request charge? Một event tên không rõ gây lỗi tích hợp khó phát hiện.
2. **Boundary:** consumer ngoài ứng dụng cần biết sự thật nào? Nếu chỉ cần invoice creation, có thể công bố `PaymentConfirmedV1` thay vì dữ liệu order domain quá chi tiết.
3. **Payload:** chỉ field thực sự được phép sử dụng; có snapshot để đảm bảo tính lịch sử khi cần.
4. **Event identity:** ID bất biến cho business fact, không sinh lại mỗi lần retry.
5. **Schema/version:** kiểu dữ liệu, required/optional fields, enum, null semantics, format thời gian, tiền tệ và giá trị mặc định.
6. **Envelope:** event ID, type, version, occurredAt, producer, correlation/causation ID nếu có.
7. **Delivery policy:** at-least-once, ack, retry, DLQ, ordering, retention, replay.
8. **Security:** xác thực producer/consumer, quyền truy cập topic/queue, encryption, data classification.
9. **Lifecycle:** consumer nào sử dụng, khi nào deprecated, migration và khả năng xử lý song song v1/v2.

Ví dụ một integration message dạng JSON **minh họa**:

```json
{
  "eventId": "evt-100",
  "type": "payment.confirmed.v1",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T00:00:00Z",
  "aggregateId": "O-100",
  "payload": {
    "orderId": "O-100",
    "amountMinor": 1500,
    "currency": "USD"
  }
}
```

Đây là **contract thiết kế ví dụ**, không phải format Spring tạo tự động. Trường `amountMinor` dùng đơn vị nhỏ nhất theo mô hình tiền tệ thống nhất. Với tiền tệ khác nhau có số chữ số thập phân khác nhau, phải định nghĩa cách biểu diễn rõ ràng thay vì mặc định "cents" cho mọi currency.

Có thể dùng ISO-8601 UTC cho `occurredAt` và một ID thực sự độc lập với địa chỉ email/PII. Nếu message bị replay, giữ nguyên `eventId` và `occurredAt`; có thể bổ sung `publishedAt` khi mỗi lần chuyển tiếp cần theo dõi riêng, nhưng không thay timestamp của business fact bằng thời điểm retry.

## 5. Lớp ánh xạ (mapper / anti-corruption layer)

Integration adapter nhận domain event, áp dụng một **allowlist mapping**, tạo integration DTO và ghi outbox hoặc gọi một messaging gateway.

```java
// Trích đoạn minh họa, DTO đã định nghĩa.
PaymentConfirmedV1 toIntegrationEvent(OrderPaid domain) {
    return new PaymentConfirmedV1(
            domain.eventId(),
            domain.orderId(),
            domain.amountCents(),
            domain.currency(),
            1);
}
```

Mapping nên làm những việc sau:

- **Lược bỏ dữ liệu nội bộ:** `internalRiskCode`, DB entity relations, JPA lazy-loaded graph, internal notes và secrets.
- **Ổn định tên trường:** ngoài hệ thống dùng `amountMinor` hoặc schema chuẩn, không buộc consumer dùng property name của entity.
- **Chuẩn hóa kiểu:** `Instant` → RFC 3339/ISO-8601, tiền → minor units + currency, ID → stable string.
- **Tách event type:** tên domain có thể đổi; public `payment.confirmed.v1` vẫn giữ khi semantic không đổi.
- **Duy trì tương quan:** event ID, aggregate ID, aggregate version/correlation ID khi hợp đồng đòi hỏi.
- **Rà soát quyền:** không dựa vào việc "đã serialize thành JSON" để kết luận an toàn.
- **Không biến một lỗi kỹ thuật thành sự thật nghiệp vụ:** bridge không được phát `PaymentConfirmed` nếu domain chưa xác nhận payment.

Mapper không nên có I/O mạng hoặc dựa vào dữ liệu thay đổi ngoài transaction khi cần snapshot tại thời điểm sự kiện. Nếu một phần dữ liệu cho integration contract phải được lookup thêm, thực hiện ở boundary có consistency và authorization rõ ràng; tránh consumer nhận một snapshot pha trộn nhiều phiên bản.

## 6. Thời điểm chuyển event và vấn đề transaction

### 6.1. Gửi trực tiếp trước commit: nguy cơ published-but-rolled-back

```text
BEGIN TRANSACTION
  update orders paid=true
  publishEvent(OrderPaid)
    -> listener gọi KafkaTemplate.send(...) / HTTP POST
  ROLLBACK
```

Nếu side effect đã ra khỏi process, database rollback không thể thu hồi message hoặc HTTP request. Consumer bên ngoài thấy "paid" khi đơn hàng trong database lại chưa được commit.

### 6.2. Gửi sau commit: đúng thời điểm nhưng vẫn có khe mất event

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` giúp listener chỉ chạy sau commit thành công. Tuy nhiên:

- Sau commit nhưng trước khi listener thực thi, process có thể crash.
- Callback after-commit thất bại **không** làm rollback transaction đã commit.
- Spring Application Events mặc định không là durable queue.
- Với transaction imperative, callback gắn vào transaction thread-bound; sự kiện ngoài transaction mặc định không kích hoạt `@TransactionalEventListener` nếu không bật fallback.
- Nếu listener after-commit muốn ghi DB, cần thiết kế transaction mới; tài nguyên cũ có thể vẫn bind nhưng không còn commit tiếp theo.

**Kết luận:** after-commit là chính sách thời điểm, không phải bảo đảm bền vững.

### 6.3. Transactional outbox: ghi ý định công bố cùng transaction

Một cơ chế phổ biến để liên kết thay đổi DB và integration event:

```text
BEGIN TRANSACTION
   update/insert orders
   insert into integration_outbox(
       event_id, type, payload, version, status, created_at)
COMMIT
               |
               v
Outbox relay (đọc row đã commit)
               |
               v
Broker publish with eventId + routing
               |
               v
Mark delivered after broker acknowledgement
```

Outbox row và order state được commit/rollback **nguyên tử trong cùng database transaction**. Relay đọc lại row sau restart nếu crash. Tuy nhiên nếu broker đã nhận message nhưng relay crash trước khi đánh dấu DELIVERED, relay có thể gửi lại. Vì vậy **at-least-once + idempotent consumer** là giả định an toàn hơn "exactly once" cho tác dụng phụ ngoài hệ thống.

Lựa chọn an toàn ở mức kiến trúc:

- Domain code tạo domain event hoặc ghi nhận pending events.
- Application/integration boundary mapping sang integration event.
- **Ghi outbox trong cùng transaction** với state; không đợi after-commit mới chèn outbox nếu cần atomicity.
- Relay phát message *sau commit*, có retry/backoff, stable key và monitoring.
- Consumer deduplicate event ID và xử lý side effect idempotent.

Khi dùng Spring `@EventListener` để ghi outbox, hãy để listener bridge **đồng bộ và tham gia transaction của publisher**; không gắn `@Async` hoặc `@TransactionalEventListener(AFTER_COMMIT)` cho đoạn chèn outbox cần nguyên tử. Ví dụ runnable dưới đây minh họa cách này.

## 7. Ví dụ Maven Java 17: domain event → integration event → outbox

Dự án sử dụng **Spring Framework 6.2.8**, Spring JDBC, H2 2.3.232, Java 17. Chạy bằng Maven, không cần Spring Boot hoặc broker thật.

Kịch bản:

1. `CheckoutService` kiểm tra amount hợp lệ, insert order và publish **domain event `OrderPaid`** trong transaction.
2. `DomainToIntegrationBridge` là `@EventListener` đồng bộ, mapping `OrderPaid` sang `PaymentConfirmedV1`, sau đó ghi outbox **cùng transaction**. Trường nội bộ `internalRiskCode` không có trong outbox.
3. Commit thành công: order và outbox cùng tồn tại.
4. `OutboxRelay` chạy **sau commit** theo lệnh main, đọc outbox, dùng fake broker in message rồi đánh dấu delivered.
5. Chạy relay lần hai không gửi lại một event đã đánh dấu delivered.
6. Lệnh amount âm bị từ chối trước transaction, không phát domain event.
7. Lỗi bridge giả lập khiến cả order và outbox rollback, minh họa atomicity.

> Đây là ví dụ về ranh giới module và transaction, **không phải** publisher Kafka production. Relay giả lập chưa có locking, lease, retry và broker ack thực. Không dùng bản demo để tuyên bố exactly-once delivery.

### 7.1. Cấu trúc

```text
separate-domain-integration-events/
├── pom.xml
└── src/main/java/demo/SeparateEventsDemo.java
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>separate-domain-integration-events</artifactId>
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
            <scope>runtime</scope>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.SeparateEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. src/main/java/demo/SeparateEventsDemo.java

```java
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
import org.springframework.transaction.support.TransactionTemplate;

public class SeparateEventsDemo {

    // Sự kiện nội bộ: có internalRiskCode, không được serialize ra broker.
    public record OrderPaid(
            String eventId,
            String orderId,
            long amountCents,
            String currency,
            String internalRiskCode) {}

    // Contract bên ngoài: chỉ các trường được phép công bố.
    public record PaymentConfirmedV1(
            String eventId,
            String orderId,
            long amountCents,
            String currency,
            int schemaVersion) {}

    public static final class CheckoutService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transactions;
        private final ApplicationEventPublisher publisher;

        public CheckoutService(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.transactions = transactions;
            this.publisher = publisher;
        }

        public void pay(
                String eventId,
                String orderId,
                long amountCents,
                String currency,
                String internalRiskCode) {

            if (amountCents <= 0) {
                throw new IllegalArgumentException(
                        "amount must be positive");
            }

            transactions.executeWithoutResult(status -> {
                jdbc.update(
                        "insert into orders " +
                        "(order_id, amount_cents, currency, internal_risk_code)" +
                        " values (?, ?, ?, ?)",
                        orderId, amountCents, currency, internalRiskCode);

                System.out.println("domain: paid " + orderId);

                // Event nội bộ, publish khi transaction đang hoạt động.
                publisher.publishEvent(new OrderPaid(
                        eventId, orderId, amountCents,
                        currency, internalRiskCode));
            });

            System.out.println("service: committed " + orderId);
        }
    }

    public static final class DomainToIntegrationBridge {
        private final JdbcTemplate jdbc;

        public DomainToIntegrationBridge(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @EventListener
        public void onPaid(OrderPaid domain) {

            // Mô phỏng lỗi adapter để quan sát rollback nguyên tử.
            if ("evt-fail".equals(domain.eventId())) {
                throw new IllegalStateException("outbox unavailable");
            }

            PaymentConfirmedV1 external = new PaymentConfirmedV1(
                    domain.eventId(),
                    domain.orderId(),
                    domain.amountCents(),
                    domain.currency(),
                    1);

            // Ghi outbox đồng bộ trong transaction của CheckoutService.
            // Không lưu internalRiskCode trong contract bên ngoài.
            jdbc.update(
                    "insert into integration_outbox " +
                    "(event_id, event_type, order_id, amount_cents," +
                    " currency, schema_version, delivered)" +
                    " values (?, ?, ?, ?, ?, ?, false)",
                    external.eventId(),
                    "payment.confirmed.v1",
                    external.orderId(),
                    external.amountCents(),
                    external.currency(),
                    external.schemaVersion());

            System.out.println("bridge: staged " + external.eventId());
        }
    }

    public static final class FakeBroker {
        public void send(PaymentConfirmedV1 event) {
            System.out.println(
                    "broker: payment.confirmed.v1 event="
                            + event.eventId()
                            + " amount=" + event.amountCents()
                            + " " + event.currency());
        }
    }

    public static final class OutboxRelay {
        private final JdbcTemplate jdbc;
        private final FakeBroker broker;

        public OutboxRelay(JdbcTemplate jdbc, FakeBroker broker) {
            this.jdbc = jdbc;
            this.broker = broker;
        }

        public void flushOnce() {
            List<PaymentConfirmedV1> pending = jdbc.query(
                    "select event_id, order_id, amount_cents," +
                    " currency, schema_version" +
                    " from integration_outbox" +
                    " where delivered = false order by event_id",
                    (rs, index) -> new PaymentConfirmedV1(
                            rs.getString("event_id"),
                            rs.getString("order_id"),
                            rs.getLong("amount_cents"),
                            rs.getString("currency"),
                            rs.getInt("schema_version")));

            System.out.println("relay: pending=" + pending.size());

            for (PaymentConfirmedV1 event : pending) {
                // Trong thực tế phải chờ broker acknowledgement đúng nghĩa.
                broker.send(event);
                jdbc.update(
                        "update integration_outbox set delivered = true" +
                        " where event_id = ? and delivered = false",
                        event.eventId());
                System.out.println("relay: delivered " + event.eventId());
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:event_separation;DB_CLOSE_DELAY=-1",
                    "sa", "");
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
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        CheckoutService checkoutService(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher publisher) {
            return new CheckoutService(jdbc, transactions, publisher);
        }

        @Bean
        DomainToIntegrationBridge bridge(JdbcTemplate jdbc) {
            return new DomainToIntegrationBridge(jdbc);
        }

        @Bean
        FakeBroker fakeBroker() {
            return new FakeBroker();
        }

        @Bean
        OutboxRelay outboxRelay(
                JdbcTemplate jdbc, FakeBroker broker) {
            return new OutboxRelay(jdbc, broker);
        }
    }

    private static int count(JdbcTemplate jdbc, String table) {
        // table là hằng số nội bộ do main truyền, KHÔNG phải input user.
        Integer value = jdbc.queryForObject(
                "select count(*) from " + table, Integer.class);
        return value == null ? 0 : value;
    }

    private static int pending(JdbcTemplate jdbc) {
        Integer value = jdbc.queryForObject(
                "select count(*) from integration_outbox" +
                " where delivered = false",
                Integer.class);
        return value == null ? 0 : value;
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                    "create table orders (" +
                    "order_id varchar(64) primary key," +
                    "amount_cents bigint not null," +
                    "currency varchar(3) not null," +
                    "internal_risk_code varchar(64) not null)");
            jdbc.execute(
                    "create table integration_outbox (" +
                    "event_id varchar(64) primary key," +
                    "event_type varchar(64) not null," +
                    "order_id varchar(64) not null," +
                    "amount_cents bigint not null," +
                    "currency varchar(3) not null," +
                    "schema_version int not null," +
                    "delivered boolean not null)");

            CheckoutService service =
                    context.getBean(CheckoutService.class);
            OutboxRelay relay =
                    context.getBean(OutboxRelay.class);

            System.out.println("=== SUCCESS ===");
            service.pay(
                    "evt-100", "O-100", 1500, "USD", "INTERNAL-RISK-A");
            System.out.println(
                    "db: orders=" + count(jdbc, "orders") +
                    " pending=" + pending(jdbc));

            System.out.println("=== RELAY ===");
            relay.flushOnce();
            System.out.println("db: pending=" + pending(jdbc));

            System.out.println("=== REPEATED RELAY ===");
            relay.flushOnce();

            System.out.println("=== INVALID COMMAND ===");
            try {
                service.pay(
                        "evt-invalid", "O-invalid", -1, "USD", "RISK-X");
            } catch (IllegalArgumentException ex) {
                System.out.println("main: invalid amount rejected");
            }

            System.out.println("=== BRIDGE FAILURE ===");
            try {
                service.pay(
                        "evt-fail", "O-fail", 500, "USD", "RISK-Y");
            } catch (IllegalStateException ex) {
                System.out.println("main: transaction rolled back");
            }
            System.out.println(
                    "db: orders=" + count(jdbc, "orders") +
                    " pending=" + pending(jdbc));
        }
    }
}
```

### 7.4. Cách chạy

Cần JDK 17+ và Maven. Tại thư mục chứa `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Đầu ra do các `System.out.println` trong chương trình tạo ra (không tính log Maven):

```text
=== SUCCESS ===
domain: paid O-100
bridge: staged evt-100
service: committed O-100
db: orders=1 pending=1
=== RELAY ===
relay: pending=1
broker: payment.confirmed.v1 event=evt-100 amount=1500 USD
relay: delivered evt-100
db: pending=0
=== REPEATED RELAY ===
relay: pending=0
=== INVALID COMMAND ===
main: invalid amount rejected
=== BRIDGE FAILURE ===
domain: paid O-fail
main: transaction rolled back
db: orders=1 pending=0
```

### 7.5. Phân tích tính nhất quán

**Ở nhánh SUCCESS:**

- `CheckoutService` INSERT vào bảng `orders` trong transaction, tạo `OrderPaid` có cả `internalRiskCode`, rồi gọi `publishEvent`.
- Spring gọi `DomainToIntegrationBridge.onPaid(...)` **đồng bộ trong publisher thread**. `JdbcTemplate` của bridge dùng cùng `DataSourceTransactionManager`/transaction connection, nên outbox row được thêm vào cùng transaction.
- Bridge mapping riêng sang `PaymentConfirmedV1`, không ghi `internalRiskCode` vào bảng integration outbox. Broker (giả lập) cũng không thấy trường nội bộ.
- Chỉ sau khi `TransactionTemplate` commit xong, main mới gọi relay. Outbox row với `delivered=false` đã bền vững trong H2 đang chạy.
- Fake broker in message rồi relay đánh dấu delivered. Lần chạy relay thứ hai không thấy hàng `pending`.

**Ở nhánh INVALID COMMAND:** lệnh amount âm bị từ chối trước khi transaction bắt đầu, nên không có INSERT, không publish event và không tạo outbox row.

**Ở nhánh BRIDGE FAILURE:** INSERT order đã chạy nhưng chưa commit; bridge giả lập ném unchecked exception ngay trong `publishEvent`. `TransactionTemplate` rollback cả INSERT order. Vì không có event nào được xác nhận commit, không có outbox row mới. Số orders cuối vẫn là 1.

**Giới hạn**: Fake broker không trả acknowledgement thực, relay không claim hàng bằng lease/lock, chưa có retry/backoff, không có transaction riêng khi đánh dấu delivered và chưa có multi-instance coordination. Việc in `broker: ...` không chứng minh message được giao bền vững. Production phải sử dụng broker client phù hợp, handle ack/errors và idempotent consumer.

**Rủi ro dữ liệu:** internal risk code được giữ trong database/domain event nhưng không có trong integration contract. Tuy vậy domain event nội bộ vẫn có thể bị log/snapshot nếu code sai; nội bộ không đồng nghĩa không cần data classification.

## 8. Vì sao không mapping trong domain aggregate?

Phản ví dụ:

```java
// Anti-pattern minh họa: domain biết Kafka, JSON và public version.
void pay(Payment p) {
    this.paid = true;
    kafkaTemplate.send(
            "payment.confirmed.v1",
            serializeToJson(new PaymentConfirmedV1(...)));
}
```

Domain lúc này phụ thuộc Kafka, serializer, routing target và external schema. Khi đổi từ Kafka sang AMQP hoặc từ JSON sang Avro, ta phải sửa code nghiệp vụ. Khi thay đổi public schema có thể vô tình làm thay đổi invariant.

Thiết kế tốt hơn:

```text
Domain / Aggregate
    └── ghi nhận OrderPaid

Application / Integration Boundary
    ├── chuyển OrderPaid -> PaymentConfirmedV1
    ├── xác định event nào đủ điều kiện externalize
    └── persist outbox / publish qua messaging port

Infrastructure adapter
    ├── serialize contract
    ├── resolve topic/routing key
    ├── send + ack/retry
    └── metrics/logging/DLQ
```

Trong kiến trúc Ports and Adapters, domain/application có thể định nghĩa một `IntegrationEventPort` hoặc `OutboxWriter` interface theo nhu cầu, infrastructure hiện thực. Không bắt buộc domain event phải biết Spring. `ApplicationEventPublisher` có thể được gọi ở application service hoặc một adapter, còn aggregate thu thập pending domain events thuần Java.

## 9. Chọn event nào được externalize?

**Không phải mọi domain event đều nên có integration event.**

Một bounded context có thể phát:

- `OrderItemRepriced`: cập nhật giá chi tiết nội bộ, không cần lộ ra public.
- `OrderReadyForPayment`: trạng thái nội bộ, có thể còn thay đổi.
- `OrderPaid`: consumer kế toán cần biết khi thanh toán đã xác nhận.
- `FraudRuleTriggered`: có thông tin nội bộ nhạy cảm; không phát ra topic chung.
- `OrderCancellationApproved`: external fulfillment service cần biết để ngừng giao hàng.

Một integration event đôi khi là projection của **nhiều** domain facts hoặc một nghiệp vụ tổng hợp, ví dụ `OrderFinanciallySettledV1` chỉ được phát sau khi tất cả điều kiện settlement hoàn tất. Không ép mapping luôn 1:1. Ngược lại, một domain event có thể dẫn tới nhiều integration contracts riêng cho các consumer có mục đích và quyền khác nhau, chẳng hạn một bản công khai tối giản và một luồng nội bộ hạn chế.

Đặt quyết định externalization ở boundary và được review như API public. Không serialize cả domain-event hierarchy rồi để mọi consumer tự chọn, vì điều đó mở rộng bề mặt coupling và dữ liệu nhạy cảm.

### Event vs command

`OrderPaid` là **fact**: thanh toán đã được xác nhận. `SendReceipt` là **command**: yêu cầu dịch vụ gửi biên nhận. Không đặt tên command là `ReceiptSent` trước khi gửi thành công, và không đặt tên fact là `PayOrder` để consumer hiểu sai. Một workflow có thể nhận `PaymentConfirmedV1` rồi tạo command gửi receipt, nhưng event chỉ nên mô tả điều thực sự đã xảy ra.

### Event vs CDC

Change Data Capture (CDC) từ database có thể phát thay đổi row, ví dụ một field `paid` đổi `false→true`. Nhưng **row change không tự là domain event**: nó thường thiếu nguyên nhân nghiệp vụ, semantic public, ranh giới transaction nhiều bảng và dữ liệu cần/không cần công bố. CDC có thể dùng để **relay outbox rows** — khi đó schema outbox là integration contract, còn CDC là transport mechanism — thay vì lộ table changes trực tiếp làm API.

## 10. Phiên bản hóa integration event và tiến hóa schema

Domain model có thể đổi nhanh nhưng integration contract phải tránh làm consumer cũ hỏng.

Ví dụ `PaymentConfirmedV1` có:

```json
{
  "eventId": "evt-100",
  "type": "payment.confirmed.v1",
  "schemaVersion": 1,
  "payload": {
    "orderId": "O-100",
    "amountMinor": 1500,
    "currency": "USD"
  }
}
```

Khi cần thêm `paymentMethodCategory` cho consumer mới, có thể thêm field **optional có default rõ** nếu schema registry và consumer cùng hỗ trợ. Khi cần **đổi ý nghĩa** của `amountMinor` hoặc thay một fact bằng fact khác, thường phải tạo `payment.confirmed.v2` và có kế hoạch migration.

| Thay đổi | Thường an toàn? | Điều kiện |
| --- | --- | --- |
| Thêm optional field có default | Thường có | Consumer bỏ qua field lạ, format/registry cho phép |
| Bỏ một required field | Thường breaking | Consumer cũ đang phụ thuộc |
| Đổi `amountMinor` từ number sang string | Breaking với nhiều serializer | Cần version/adapter tương thích |
| Đổi nghĩa `OrderPaid` từ "đã charge" sang "đã settle" | Semantic breaking | Cần event type/version mới |
| Thêm enum value | Có thể breaking | Consumer không xử lý unknown enum |
| Đổi tên routing topic | Có thể breaking | Consumer/broker ACL/subscription phải migrate |
| Thêm PII vào payload | Đòi security/privacy review | Không chỉ là thay đổi schema kỹ thuật |
| Thay `eventId` mỗi retry | Sai contract idempotency | Giữ ID cho cùng business fact |

Không có quy tắc "chỉ cần schemaVersion tăng là an toàn". Ngoài syntax compatibility còn có **semantic compatibility**: cùng field nhưng ý nghĩa thay đổi là breaking change. Nếu dùng Avro/Protobuf/JSON Schema, định nghĩa chiến lược backward/forward/full compatibility phù hợp, version trong schema registry, hợp đồng và tests.

Một kế hoạch nâng cấp có thể gồm:

1. Định nghĩa contract v2 và lý do.
2. Đảm bảo consumer chấp nhận v2 hoặc triển khai dual consumption.
3. Publisher chuyển sang v2, hoặc dual publish có stable event identity và consumer dedup rõ.
4. Theo dõi lag/usage, thông báo thời gian ngừng v1.
5. Ngừng v1 khi consumer đã migrate và retention/replay policy cho phép.

**Tránh dual publish mù:** hai message v1/v2 có thể diễn tả cùng một fact. Consumer đọc cả hai topic phải nhận ra đó là **một** sự kiện nghiệp vụ khi tính toán side effects.

## 11. Envelope, định tuyến và thứ tự

Một integration envelope thường gồm metadata:

| Trường | Mục đích |
| --- | --- |
| `eventId` | Idempotency/dedup, giữ ổn định qua retry |
| `type` | Public event type, ví dụ `payment.confirmed.v1` |
| `schemaVersion` | Đọc payload theo contract |
| `occurredAt` | Khi business fact xảy ra |
| `publishedAt` | Khi thực sự gửi qua transport (có thể khác khi retry) |
| `aggregateId` | Hỗ trợ định tuyến/ordering; vẫn có thể nhạy cảm |
| `aggregateVersion` | Xác định thứ tự thay đổi trong một aggregate khi cần |
| `correlationId` | Liên hệ command/request và các bước xử lý |
| `causationId` | Event/command gây nên event hiện tại |
| `source` | Producer service/bounded context |
| `tenantId` | Chỉ dùng khi cần và được phép, kiểm soát phân quyền |

Đối với Kafka, key có thể là aggregate ID để những thay đổi của cùng một aggregate cùng partition và giữ **thứ tự trong partition** dưới các điều kiện producer/broker cụ thể. Điều đó không đảm bảo thứ tự toàn cục, và consumer retry/DLQ có thể làm event sau vượt event trước. Nếu ordering là invariant nghiệp vụ, cần thiết kế cả relay, partitioning, aggregate version và consumer reorder/idempotency.

Thứ tự **được tạo trong domain** cũng có thể khác thứ tự **được broker xác nhận** khi relay chạy song song. Không mặc định một bảng outbox với `ORDER BY created_at` bảo đảm order trên nhiều instance nếu worker claim row cạnh tranh; phải có chiến lược claim/serialize theo aggregate khi cần.

## 12. Failure modes và khắc phục

| Sự cố | Hệ quả | Chiến lược |
| --- | --- | --- |
| Domain operation bị từ chối | Không có business fact cần công bố | Không tạo success event |
| Database insert state thất bại | Transaction rollback | Không tạo outbox đã commit |
| Mapper/outbox insert thất bại trong transaction | State + outbox cùng rollback | Log an toàn, retry command khi hợp lệ |
| Commit thành công, relay chưa chạy thì process chết | Outbox row vẫn còn | Relay sau restart |
| Broker nhận event nhưng relay chưa đánh dấu delivered | Có thể publish trùng | Stable event ID + idempotent consumer |
| Consumer không hiểu v2 | Lỗi parse/semantic | Contract tests, dual support, DLQ |
| Consumer dùng domain enum nội bộ | Coupling tới refactor | Tạo external enum/public mapping |
| Integration message chứa secret | Rò rỉ qua broker/DLQ/logs | Allowlist fields, ACL, retention, encryption |
| Relay song song cùng claim một row | Duplicate hoặc reorder | Lock/lease, unique ID, idempotency, partition |
| Handler after-commit ghi outbox sau commit | Mất tính nguyên tử của outbox | Ghi outbox trong transaction gốc |
| Consumer nhận lại event sau rollback giả | Side effect sai | Chỉ relay những outbox rows đã commit |
| Domain event chỉ có pending list trong RAM khi process crash | Có thể mất event | Flush vào outbox trong Unit of Work |
| Schema v1 bị xóa sớm | Replay/consumer cũ lỗi | Deprecation/retention/compatibility plan |

### Producer idempotency

Outbox row thường dùng `event_id` làm primary/unique key để không có hai bản ghi cùng business fact. Nhưng event ID do service tạo phải **ổn định qua retry của cùng command** nếu hợp đồng cần tránh trùng. Chỉ gọi `UUID.randomUUID()` mỗi lần command bị retry có thể khiến cùng một thao tác nghiệp vụ được tạo hai lần dưới hai event IDs khác nhau.

Cần kiểm soát duplicate ở **nguồn** bằng idempotency key, database uniqueness hoặc aggregate state. Outbox unique constraint chỉ là một tầng bảo vệ, không tự giải quyết duplicate business operations.

### Consumer idempotency

Mẫu consumer giả định:

```text
BEGIN CONSUMER TRANSACTION
  INSERT INTO processed_events(event_id) ... UNIQUE
  IF inserted:
      apply side effects in same transaction
  ELSE:
      skip duplicate
COMMIT
ACK broker
```

Đây là sơ đồ thiết kế, không phải SQL copy-paste. Với side effect ra email/API, transaction DB của consumer không tự bảo đảm atomicity với bên ngoài; cần downstream idempotency key, outbox riêng hoặc reconciliation. Mục tiêu thường là **effectively once** cho nghiệp vụ cụ thể, không hứa "exactly once" xuyên mọi hệ thống.

## 13. Spring Framework, Spring Data và Spring Modulith hỗ trợ gì?

### Spring Framework

`ApplicationEventPublisher.publishEvent(Object)` là cơ chế thông báo cho listeners trong context. `@EventListener` được hỗ trợ với POJO/record payload. Với default multicaster, listener thông thường chạy đồng bộ; tuy nhiên API publication mang tính **handoff**, không bảo đảm giao nhận bền vững hoặc hoàn thành async.

`@TransactionalEventListener` cho phép chọn `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION` và mặc định là after-commit. Nó hữu ích để chạy internal reactions đúng phase, nhưng tự nó không chuyển sự kiện thành public integration contract hay outbox.

### Spring Data

`@DomainEvents` và `AbstractAggregateRoot` hỗ trợ register/publish domain events từ repository-managed aggregate. `@AfterDomainEventPublication` giúp dọn pending event buffer sau publication. Không coi đó là "message đã tới Kafka" hoặc "transaction đã commit".

### Spring Modulith

Spring Modulith cung cấp khả năng kiểm soát **module boundaries**, application module listeners, event publication registry và event externalization. Theo tài liệu chính thức, event externalization cho phép:

- Chọn events được externalize (ví dụ dùng `@Externalized` hoặc configuration selector).
- Mapping original event sang payload bên ngoài.
- Xác định broker routing target và headers.
- Tích hợp Kafka/AMQP/JMS/Spring Messaging theo dependency phù hợp.
- Ghi nhận/khôi phục event publications thông qua registry và các cơ chế cấu hình tương ứng.

**Không đánh đồng mọi event externalization với transactional outbox truyền thống.** Các mode/công cụ khác nhau có đặc tính khác nhau. Tài liệu Spring Modulith 2.1 mô tả lựa chọn outbox thông qua các tích hợp như Namastack/JobRunr bên cạnh listener-based externalization. Chọn đúng version và cơ chế theo yêu cầu durability, concurrency và ordering; không copy cấu hình từ một phiên bản khác mà không kiểm tra.

Một đoạn cấu hình ý tưởng, **không phải chương trình độc lập**:

```java
// Đường API trong Spring Modulith phụ thuộc version đã chọn.
// Đây chỉ là ví dụ mục đích ánh xạ; cần config bean đầy đủ.
EventExternalizationConfiguration.externalizing()
    .select(EventExternalizationConfiguration.annotatedAsExternalized())
    .mapping(OrderPaid.class, event -> toExternal(event))
    .build();
```

Khi dùng externalization framework, vẫn cần review mapping để không tự serialize nguyên domain event nhạy cảm. Cần định nghĩa “event nào”, “payload nào”, “route nào” và độ tin cậy/retention rõ.

## 14. Kiểm thử ranh giới domain và integration

### 14.1. Domain unit test

Kiểm tra domain behavior và pending events **không cần Spring broker**:

- Lệnh thanh toán hợp lệ tạo fact `OrderPaid` đúng dữ liệu.
- Lệnh sai invariant không tạo success event.
- Không có dependency Kafka/JSON schema trong domain code.
- Event ID, occurredAt và aggregate version được tạo đúng quy tắc.
- Không tạo event hai lần do aggregate đã ở trạng thái paid.

### 14.2. Mapper unit test

Kiểm tra **schema allowlist**:

```java
// Trích đoạn test, dùng định nghĩa record từ ví dụ và JUnit phù hợp.
OrderPaid domain = new OrderPaid(
        "evt-100", "O-100", 1500, "USD", "PRIVATE-RISK");
PaymentConfirmedV1 external = toIntegrationEvent(domain);

assertEquals("evt-100", external.eventId());
assertEquals("O-100", external.orderId());
assertEquals(1, external.schemaVersion());
```

Đây là đoạn minh họa; `toIntegrationEvent` và `assertEquals` cần được định nghĩa/import trong fixture test. Ngoài kiểm tra giá trị, hãy serialize **đúng serializer thực tế** rồi xác nhận JSON/Avro/Protobuf không chứa `internalRiskCode` hoặc dữ liệu không được phép.

### 14.3. Integration transaction/outbox test

Chạy với DB transaction thực:

1. Command hợp lệ → đúng một order row và một integration outbox row.
2. Outbox row có event type `payment.confirmed.v1`, `schemaVersion=1` và **không có** internal risk field.
3. Command sai amount → không có order/outbox row mới.
4. Bridge ném exception → cả hai thay đổi rollback.
5. Sau commit, relay thấy row; trước commit một connection khác không thấy row chưa commit theo isolation phù hợp.
6. Relay gửi thành công và mark delivered; chạy lại relay không gửi lại nếu marker đã commit.
7. Mô phỏng relay crash sau broker ack nhưng trước marker update → có thể resend; consumer idempotency tránh side effect trùng.
8. Mô phỏng nhiều relays/ordering/retry để xác nhận locking/lease strategy.

### 14.4. Contract test với consumer

Một integration contract phải được kiểm thử **không phụ thuộc class Java nội bộ**:

- Consumer đọc được message từ schema chính thức.
- Required/optional fields và enum unknown handling phù hợp.
- Version cũ còn được hỗ trợ trong deprecation window.
- Consumer không dựa vào thứ tự field JSON, string representation của enum Java hoặc package name.
- Replay giữ event ID, timestamp, payload semantics.
- Contract không chứa PII/secret không được phép; logs, DLQ, broker payload và tracing cũng không rò rỉ.

### 14.5. Failure/chaos test

Tạo các lỗi: DB mất kết nối, mapper lỗi, broker timeout, process crash giữa commit và relay, broker ack bị mất, duplicate delivery, DLQ replay, schema incompatibility, consumer chậm, queue backlog. Kiểm tra response và trạng thái **bền vững**, không chỉ nhìn log "event published".

## 15. Lỗi thiết kế phổ biến

**Lỗi 1 — Public domain-event class trực tiếp làm integration DTO.** Dễ làm consumer phụ thuộc vào field nội bộ và thay đổi class.

**Lỗi 2 — Cho aggregate import KafkaTemplate/RestClient.** Domain chịu trách nhiệm nghiệp vụ nhưng bị buộc vào transport/serializer.

**Lỗi 3 — Mọi domain event đều đi broker.** Tăng coupling, traffic, retention và rò rỉ dữ liệu không cần thiết.

**Lỗi 4 — Copy nguyên JPA entity làm payload.** Lộ lazy relations, field nhạy cảm, mutable state và khó đảm bảo serialization.

**Lỗi 5 — Phát message ra broker trước khi transaction commit.** Consumer có thể nhìn thấy business fact không được commit.

**Lỗi 6 — Ghi outbox bằng callback AFTER_COMMIT nhưng tuyên bố atomic.** Commit state đã xong, ghi outbox không còn trong transaction gốc.

**Lỗi 7 — Dùng @EventListener async cho bridge ghi outbox cùng transaction.** Context/transaction thread-bound không tự di chuyển; mất atomicity.

**Lỗi 8 — Chỉ thêm schemaVersion mà không test compatibility.** Semantic breaking vẫn có thể làm consumer xử lý sai.

**Lỗi 9 — Tạo event ID mới mỗi lần retry.** Consumer không thể deduplicate một business fact.

**Lỗi 10 — Coi gọi publishEvent trả về là broker delivery.** Nó là in-process publication/handoff, không phải broker acknowledgement.

**Lỗi 11 — Bỏ qua duplicate/reorder khi relay chạy song song.** At-least-once thực tế cần consumer idempotency và ordering strategy.

**Lỗi 12 — Không quản lý deprecation.** Consumer ngoài tổ chức có thể vẫn cần schema v1, bao gồm replay của dữ liệu cũ.

**Lỗi 13 — Đưa internalRiskCode, token, password vào integration payload.** Một event có thể được lưu trên broker/DLQ/backups lâu hơn database gốc.

**Lỗi 14 — Consumer lookup current entity rồi dùng làm snapshot lịch sử.** State có thể đổi sau khi event được tạo; chọn snapshot fields có chủ đích.

**Lỗi 15 — Đếm broker messages làm số domain facts.** Relay retry có thể gửi cùng event ID nhiều lần.

**Lỗi 16 — Gọi một command là sự thật đã xảy ra.** `SendReceipt` và `ReceiptSent` có semantic khác nhau, cần đặt tên đúng.

**Lỗi 17 — Đặt integration version trong package name Java làm contract duy nhất.** Consumer không dùng Java vẫn cần schema/documentation/compatibility rules rõ.

## 16. Checklist triển khai

- [ ] Xác định bounded context và consumer ngoài boundary.
- [ ] Định nghĩa domain fact và đặt tên theo thuật ngữ nghiệp vụ.
- [ ] Giữ aggregate không phụ thuộc broker/client/serializer.
- [ ] Chỉ externalize events có nhu cầu từ consumer được phê duyệt.
- [ ] Tạo integration event contract riêng, immutable, tối thiểu dữ liệu.
- [ ] Có event ID ổn định, type, schema/version và timestamp semantic rõ.
- [ ] Mapping có allowlist, không gửi entity/credentials/PII không cần thiết.
- [ ] Định nghĩa amount/currency/time/ID/enum/nullable format.
- [ ] Ghi state và outbox trong cùng transaction nếu cần atomicity.
- [ ] Chỉ relay message đã commit, có broker ack/retry/backoff.
- [ ] Multi-instance relay có claim/lease và cơ chế ordering phù hợp.
- [ ] Consumer idempotent với stable event ID và có DLQ/replay policy.
- [ ] Có contract tests và migration/deprecation plan cho v1→v2.
- [ ] Có producer/consumer ACL, data retention, mã hóa và log redaction.
- [ ] Đo event created, outbox pending, relay delivered/failed, consumer lag.
- [ ] Đánh giá Spring Modulith externalization/publication registry đúng phiên bản và nhu cầu.
- [ ] Test rollback, process crash, duplicate, replay, schema compatibility và dữ liệu nhạy cảm.

## 17. Câu hỏi tự kiểm tra

1. **Domain event và integration event khác nhau ở điểm chính nào?** — Domain event diễn tả sự thật trong mô hình nội bộ; integration event là hợp đồng ổn định để bên ngoài tiêu thụ.
2. **Có bắt buộc 1:1 giữa hai loại event không?** — Không; mapping có thể lọc, gộp hoặc tạo các contract riêng theo nhu cầu.
3. **Vì sao không gửi nguyên entity hoặc domain event ra Kafka?** — Vì làm lộ cấu trúc nội bộ, gây coupling và có thể rò rỉ dữ liệu nhạy cảm.
4. **Công việc của mapper là gì?** — Chuyển domain semantics sang public schema, chuẩn hóa/allowlist fields và gắn metadata cần thiết.
5. **Vì sao không publish broker trước DB commit?** — Có thể gửi fact ngoài ứng dụng rồi transaction nguồn rollback.
6. **AFTER_COMMIT có tương đương outbox không?** — Không; after-commit chọn thời điểm, không tự có durability.
7. **Chèn outbox ở đâu để atomic với state?** — Trong cùng transaction DB với thay đổi aggregate.
8. **Nếu broker nhận event nhưng relay crash trước mark delivered thì sao?** — Event có thể được gửi lại; consumer phải idempotent.
9. **SchemaVersion có đủ bảo đảm consumer cũ không hỏng không?** — Không, cần kiểm tra syntax và semantic compatibility.
10. **Khi thêm một field internalRiskCode trong domain, integration event có cần thay theo không?** — Không, trừ khi consumer ngoài thật sự cần và có quyền; mapper kiểm soát contract.
11. **Một integration event có thể đại diện cho nhiều domain facts không?** — Có, khi contract công bố một business milestone tổng hợp.
12. **Spring ApplicationEventPublisher có bảo đảm broker nhận message không?** — Không, nó là cơ chế thông báo trong application context.
13. **Domain events từ Spring Data có tự bảo đảm Kafka delivery không?** — Không, cần integration/publication infrastructure.
14. **Consumer đọc v1 và v2 cần tránh điều gì khi dual publishing?** — Tránh áp dụng side effect hai lần cho cùng business fact.
15. **Vì sao event ID cần giữ nguyên qua retry?** — Để dedup/replay có thể nhận ra cùng một sự kiện nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2.8 — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Data Commons — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Event Externalization Configuration](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/EventExternalizationConfiguration.html)
- [Apache Kafka — Core Concepts](https://kafka.apache.org/documentation/)

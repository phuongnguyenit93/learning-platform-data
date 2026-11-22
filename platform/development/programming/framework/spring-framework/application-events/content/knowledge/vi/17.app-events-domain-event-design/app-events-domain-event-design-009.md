# Domain event và transaction boundary

Trong thiết kế hướng domain, một **domain event** là một sự thật có ý nghĩa đối với nghiệp vụ, chẳng hạn `OrderPaid`, `BookingConfirmed` hoặc `StockReserved`. Một event thường được phát sau khi aggregate chuyển trạng thái; nhưng “đã gọi `publishEvent(...)`” và “thay đổi dữ liệu đã commit” là **hai mốc khác nhau**. Hiểu rõ **transaction boundary** giúp tránh gửi email cho đơn hàng cuối cùng bị rollback, giảm việc mở rộng transaction không cần thiết và chọn được cách giao event đáng tin cậy.

Trong Spring Framework, ba cơ chế có vai trò khác nhau:

- `ApplicationEventPublisher.publishEvent(...)`: đưa event tới cơ chế phát sự kiện trong ứng dụng; bản thân phương thức này không tự commit database hay đảm bảo event được lưu bền vững.
- `@EventListener`: thường chạy ngay khi phát event, đồng bộ trên thread gọi nếu dùng `SimpleApplicationEventMulticaster` mặc định và không cấu hình bất đồng bộ.
- `@TransactionalEventListener`: gắn xử lý event với pha của transaction đang hoạt động, mặc định là `AFTER_COMMIT`; một lần publish trong transaction chỉ dẫn đến xử lý sau khi kết cục phù hợp xảy ra.

Bài này đi từ ranh giới aggregate tới transaction, giải thích các trường hợp có và không có transaction, đưa ra ví dụ kiểm thử Java 17+ bằng Spring Test + JDBC/H2 và thảo luận khi nào cần transactional outbox thay cho callback trong bộ nhớ.

## 1. Domain event diễn tả điều gì?

Event nên đặt tên bằng **một sự kiện nghiệp vụ đã xảy ra theo góc nhìn domain**, thường dùng thì quá khứ: `PaymentCaptured`, `OrderPlaced`, `ReservationCancelled`. Nó khác một **command** như `CapturePayment`: command là yêu cầu làm việc; event là mô tả một thay đổi/quyết định.

Ví dụ một đơn hàng được chuyển từ `CREATED` sang `PAID`:

~~~text
Client --command PayOrder--> Order application service
                                  |
                                  +-- Kiểm tra điều kiện nghiệp vụ
                                  +-- Aggregate chuyển CREATED -> PAID
                                  +-- Ghi trạng thái vào database
                                  +-- Publish OrderPaid(orderId)
                                  |
                                  +-- Kết thúc transaction
                                           |
                                           +-- COMMIT
                                           |     +-- after-commit listener
                                           |
                                           +-- ROLLBACK
                                                 +-- bỏ hiệu ứng after-commit
~~~

Ở cấp độ **domain**, một aggregate có thể ghi nhận `OrderPaid` ngay sau khi quy tắc chuyển trạng thái thỏa mãn. Ở cấp độ **lưu trữ**, thay đổi đó chỉ bền vững sau commit. Vì vậy nếu event sẽ dẫn tới tác dụng phụ bên ngoài (email, API, broker), hệ thống phải xác định người tiêu thụ xử lý **trong transaction** hay **sau khi transaction thành công**.

Thiết kế payload nên giữ dữ liệu tối thiểu và ổn định:

~~~java
public record OrderPaid(
    String eventId,
    String orderId,
    long orderVersion
) { }
~~~

Đây là một record Java 17+ độc lập. `eventId` có thể phục vụ deduplication, `orderId` xác định aggregate, và `orderVersion` giúp consumer nhận ra sự kiện cũ hoặc sai thứ tự. Không nên gắn trực tiếp một JPA entity đang managed hoặc một persistence context vào event dùng giữa các module, vì sau khi transaction đóng, lazy loading hoặc trạng thái mutable có thể gây lỗi/hiểu nhầm.

## 2. Boundary của nghiệp vụ, aggregate và database transaction

Một **aggregate boundary** quy định phần trạng thái phải giữ bất biến nhất quán khi xử lý một command. Một **database transaction boundary** là phạm vi các thao tác DB cùng commit/rollback. Hai boundary này có liên quan, nhưng không đồng nhất: một transaction có thể thay đổi nhiều bảng/aggregate; một quy trình nghiệp vụ dài có thể cần nhiều transaction và event khác nhau.

Ví dụ trong cùng một transaction:

~~~java
@Transactional
public void payOrder(String orderId) {
    Order order = orderRepository.getRequired(orderId);
    order.markPaid();
    orderRepository.save(order);
    publisher.publishEvent(new OrderPaid(eventId(), orderId, order.version()));
}
~~~

**Đây là trích đoạn thiết kế**, không phải file Java độc lập: `Order`, repository, `eventId()` và các bean cần được ứng dụng định nghĩa. Khi dùng JPA, `save()` có thể chưa flush SQL ngay; dù đã flush, **flush không phải commit**.

Nếu Spring transaction interceptor tạo transaction quanh `payOrder`, việc publish nằm **bên trong transaction**. Một `@EventListener` đồng bộ được gọi ngay khi `publishEvent` thực thi, lúc transaction vẫn còn mở; một `@TransactionalEventListener(AFTER_COMMIT)` được đăng ký chờ đến khi commit thực sự thành công. Nếu một exception dẫn đến rollback, callback after-commit không thực thi.

Lưu ý `@Transactional` trong proxy mode mặc định cần lời gọi đi **qua Spring proxy**. Tự gọi `this.payOrder(...)` từ cùng bean có thể bỏ qua interceptor, khiến transaction không được tạo như kỳ vọng.

### Ba mốc không thể đánh đồng

| Mốc | Điều đã xảy ra | Điều chưa chắc xảy ra |
| --- | --- | --- |
| Aggregate thay đổi trạng thái | Quy tắc domain đã cho phép chuyển trạng thái trong bộ nhớ | SQL flush, commit, ghi nhận bền vững |
| `publishEvent(new OrderPaid(...))` trả về | Lệnh phát event đã hoàn tất theo cấu hình multicaster tại thời điểm đó | Commit thành công; async listener hoàn tất; delivery bền vững |
| Database commit thành công | Các thay đổi thuộc transaction được chốt | Email/Kafka được gửi thành công; consumer xử lý đúng một lần |

“Publish sau `save()`” **không đồng nghĩa** “publish sau commit”. Nếu business yêu cầu gọi hệ thống ngoài sau khi dữ liệu đã chốt, phải dùng cơ chế phù hợp với **kết cục transaction**, không chỉ thay đổi thứ tự hai dòng code.

## 3. Listener đồng bộ có thể mở rộng transaction

Mặc định Spring sử dụng `SimpleApplicationEventMulticaster` đồng bộ. Ví dụ:

~~~java
@EventListener
public void onOrderPaid(OrderPaid event) {
    inventoryRepository.reserveFor(event.orderId());
}
~~~

Đây là trích đoạn trong một bean Spring. Nếu service publish event trong transaction và listener gọi repository qua cùng thread/transaction, thao tác reserve có thể tham gia **transaction đang mở**. Điều này có thể hữu ích khi cả hai thay đổi bắt buộc phải commit hoặc rollback cùng nhau.

Tuy nhiên, cần phân biệt **đồng bộ** và **nghiệp vụ bắt buộc**:

- Nếu không reserve được hàng thì thanh toán đơn hàng không được hoàn tất, một lời gọi service tường minh hoặc xử lý trong cùng aggregate/application service có thể rõ ràng hơn listener ẩn.
- Nếu listener chỉ cập nhật metric hoặc gửi email phụ, để lỗi của nó kéo rollback nghiệp vụ chính là coupling không cần thiết.
- Một listener đồng bộ gọi HTTP, gửi mail hoặc publish broker trước commit có thể tạo tác dụng phụ bên ngoài **không thể rollback** cùng database.

Ví dụ rủi ro:

~~~text
BEGIN DB TRANSACTION
  UPDATE orders SET status='PAID' ...
  publish OrderPaid
      -> @EventListener gửi email "Thanh toán thành công"
  INSERT audit ...  -- gặp lỗi constraint
ROLLBACK
Kết quả: DB không có đơn PAID, khách đã nhận email.
~~~

Nếu listener ném exception, với multicaster đồng bộ mặc định và không cấu hình error handler xử lý exception, lỗi có thể truyền ngược tới publisher và làm transaction rollback theo quy tắc Spring. Khi bật `@Async` hoặc executor, ngoại lệ của listener có thể không quay lại transaction gốc; không suy từ điều đó thành đảm bảo retry hoặc tính nguyên tử.

## 4. @TransactionalEventListener gắn xử lý với kết cục transaction

Spring cung cấp `@TransactionalEventListener` để listener thực thi theo một pha của transaction:

| TransactionPhase | Khi nào listener chạy | Tình huống phù hợp |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi commit được hoàn tất; transaction vẫn có thể thất bại | Công việc chuẩn bị/kiểm tra cần nằm trong vòng đời commit |
| `AFTER_COMMIT` (**mặc định**) | Sau commit thành công | Gửi notification, phát tín hiệu cho hệ thống khác nếu không cần cam kết giao nhận bền vững |
| `AFTER_ROLLBACK` | Khi transaction rollback | Ghi nhận thất bại hoặc dọn dẹp logic dựa trên kết cục rollback |
| `AFTER_COMPLETION` | Sau completion, dù commit hay rollback | Dọn dẹp chung, theo dõi lifecycle |

Ví dụ chỉ gửi receipt sau khi trạng thái đơn hàng được commit:

~~~java
@Component
class ReceiptListener {

    private final ReceiptGateway gateway;

    ReceiptListener(ReceiptGateway gateway) {
        this.gateway = gateway;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onPaid(OrderPaid event) {
        gateway.sendReceipt(event.orderId());
    }
}
~~~

Đây là trích đoạn; cần định nghĩa `ReceiptGateway`, `OrderPaid` và import `@Component`, `@TransactionalEventListener`, `TransactionPhase`. Nếu transaction rollback, listener này không được gọi do event đó. Nếu transaction commit, callback được thực thi, nhưng lỗi gateway **không làm DB đã commit tự động rollback**. Vì vậy after-commit xử lý **đúng thời điểm**, không tự bảo đảm delivery thành công.

Nếu không có transaction phù hợp khi publish, `@TransactionalEventListener` **mặc định không chạy**. Thuộc tính `fallbackExecution = true` cho phép xử lý dù không có transaction, nhưng phải dùng theo chủ đích: nếu yêu cầu nghiệp vụ là “chỉ gửi sau commit”, bật fallback có thể phá vỡ hợp đồng đó.

### Database access trong listener sau commit

Sau commit, tài nguyên transaction có thể **vẫn còn gắn với thread** một khoảng thời gian, dù transaction đã hoàn tất. Nếu callback sau commit ghi thêm dữ liệu vào repository mà không có transaction mới, không thể mặc định kỳ vọng một lần commit thứ hai cho thay đổi đó.

Nếu listener after-commit cần ghi bản ghi audit hoặc trạng thái delivery bền vững, hãy gọi một service có transaction mới với `@Transactional(propagation = Propagation.REQUIRES_NEW)` qua Spring proxy, hoặc dùng `TransactionTemplate` cấu hình `PROPAGATION_REQUIRES_NEW`. Cần kiểm thử readback từ DB sau callback; không suy rằng một lệnh repository `save()` tự có commit.

## 5. Tách domain event khỏi integration event

**Domain event** diễn tả điều xảy ra trong mô hình nghiệp vụ của ứng dụng. **Integration event** là thông điệp công bố qua ranh giới module/service/process; nó cần hợp đồng dữ liệu có thể phát triển theo phiên bản và có quy tắc giao nhận, retry, trùng lặp riêng.

Ví dụ:

~~~text
Trong domain/application:
  OrderPaid(eventId, orderId, version)
  --> listener nội bộ cập nhật read model

Khi xuất ra hệ thống khác:
  PaymentSettledV1 {
    eventId,
    orderId,
    occurredAt,
    schemaVersion
  }
  --> transactional outbox / publisher --> Kafka/RabbitMQ/HTTP
~~~

Đây là sơ đồ, không phải JSON đầy đủ. Không dùng kiểu entity persistence hoặc `TransactionContext` nội bộ như một hợp đồng message xuyên mạng. Khi externalize event, cần cân nhắc dữ liệu được công bố, quyền truy cập, schema evolution, ordering theo key (ví dụ orderId) và idempotency.

Một domain event được publish trong memory chỉ là **notification nội bộ**. Nó không tự tồn tại sau khi process chết. Vì vậy khác biệt giữa listener after-commit và outbox là **độ bền của ý định gửi**.

## 6. Ví dụ tích hợp Java 17+: transaction thật, commit và rollback

Ví dụ dưới dùng Spring Framework, Spring JDBC, H2 in-memory và JUnit 5. Nó kiểm chứng:

1. Service cập nhật DB và publish `PaymentCaptured` bên trong cùng JDBC transaction.
2. Listener `@EventListener` đồng bộ quan sát trạng thái `CAPTURED` chưa commit bằng **cùng transaction**.
3. Listener `AFTER_COMMIT` chỉ ghi dấu sau commit.
4. Nếu rollback, DB trở về `CREATED`; callback `AFTER_COMMIT` không chạy, callback `AFTER_ROLLBACK` chạy.
5. Nếu publish ngoài transaction, listener bình thường vẫn được gọi, còn transactional listeners mặc định không chạy.

### 6.1. Gradle dependencies

File `build.gradle` dùng Java 17 và bộ dependency test tối thiểu:

~~~groovy
plugins {
    id 'java'
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
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-jdbc'
    testImplementation 'org.springframework:spring-tx'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
    testRuntimeOnly 'com.h2database:h2:2.3.232'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot project nên ưu tiên BOM của Boot đang được sử dụng và không ép các phiên bản Spring Framework riêng nếu chúng không tương thích với BOM đó.

### 6.2. File src/test/java/example/events/DomainEventTransactionTest.java

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

@SpringJUnitConfig(DomainEventTransactionTest.Config.class)
class DomainEventTransactionTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired PaymentService service;
    @Autowired ApplicationEventPublisher publisher;
    @Autowired Trace trace;

    @BeforeEach
    void setUp() {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS payment (" +
            "id VARCHAR(40) PRIMARY KEY, " +
            "state VARCHAR(20) NOT NULL)"
        );
        jdbc.update("DELETE FROM payment");
        jdbc.update(
            "INSERT INTO payment(id, state) VALUES (?, ?)",
            "A-1", "CREATED"
        );
        jdbc.update(
            "INSERT INTO payment(id, state) VALUES (?, ?)",
            "B-2", "CREATED"
        );
        jdbc.update(
            "INSERT INTO payment(id, state) VALUES (?, ?)",
            "C-3", "CREATED"
        );
        trace.clear();
    }

    @Test
    void commitDeliversAfterCommitEvent() {
        service.capture("A-1", false);

        assertEquals("CAPTURED", state("A-1"));
        assertEquals(
            List.of(
                "inside:A-1:CAPTURED",
                "committed:A-1"
            ),
            trace.snapshot()
        );
    }

    @Test
    void rollbackDoesNotDeliverAfterCommitEvent() {
        service.capture("B-2", true);

        assertEquals("CREATED", state("B-2"));
        assertEquals(
            List.of(
                "inside:B-2:CAPTURED",
                "rolledBack:B-2"
            ),
            trace.snapshot()
        );
    }

    @Test
    void withoutTransactionOnlyNormalListenerRuns() {
        publisher.publishEvent(new PaymentCaptured("C-3"));

        assertEquals("CREATED", state("C-3"));
        assertEquals(
            List.of("inside:C-3:CREATED"),
            trace.snapshot()
        );
    }

    private String state(String id) {
        return jdbc.queryForObject(
            "SELECT state FROM payment WHERE id = ?",
            String.class,
            id
        );
    }

    record PaymentCaptured(String orderId) { }

    static class Trace {
        private final List<String> values = new ArrayList<>();

        void add(String value) {
            values.add(value);
        }

        List<String> snapshot() {
            return List.copyOf(values);
        }

        void clear() {
            values.clear();
        }
    }

    static class PaymentService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        PaymentService(JdbcTemplate jdbc, TransactionTemplate tx,
                       ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.tx = tx;
            this.publisher = publisher;
        }

        void capture(String id, boolean rollback) {
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "UPDATE payment SET state = ? WHERE id = ?",
                    "CAPTURED", id
                );
                publisher.publishEvent(new PaymentCaptured(id));
                if (rollback) {
                    status.setRollbackOnly();
                }
            });
        }
    }

    static class PaymentListeners {
        private final JdbcTemplate jdbc;
        private final Trace trace;

        PaymentListeners(JdbcTemplate jdbc, Trace trace) {
            this.jdbc = jdbc;
            this.trace = trace;
        }

        @EventListener
        public void onPublication(PaymentCaptured event) {
            String current = jdbc.queryForObject(
                "SELECT state FROM payment WHERE id = ?",
                String.class,
                event.orderId()
            );
            trace.add(
                "inside:" + event.orderId() + ":" + current
            );
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void afterCommit(PaymentCaptured event) {
            trace.add("committed:" + event.orderId());
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK
        )
        public void afterRollback(PaymentCaptured event) {
            trace.add("rolledBack:" + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                "jdbc:h2:mem:domain_event_tx;DB_CLOSE_DELAY=-1",
                "sa",
                ""
            );
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        DataSourceTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                DataSourceTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        Trace trace() {
            return new Trace();
        }

        @Bean
        PaymentService paymentService(JdbcTemplate jdbc,
                TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            return new PaymentService(jdbc, tx, publisher);
        }

        @Bean
        PaymentListeners paymentListeners(JdbcTemplate jdbc, Trace trace) {
            return new PaymentListeners(jdbc, trace);
        }
    }
}
~~~

Chạy từ project có Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.DomainEventTransactionTest"
~~~

Trên Windows PowerShell có thể dùng `./gradlew.bat` thay `./gradlew`. Nếu phụ thuộc và cấu hình test phù hợp, ba test **PASS**. Chúng không in các dòng `inside:`, `committed:` hay `rolledBack:` ra stdout; những chuỗi đó được lưu vào `Trace` và so sánh qua assertion.

**Điều test chứng minh:** `PaymentService` mở transaction với `TransactionTemplate` rồi ghi DB và publish trong cùng phạm vi; listener thường dùng `JdbcTemplate` trên cùng thread nên đọc được giá trị chưa commit; listener `AFTER_COMMIT` chỉ ghi dấu khi commit thành công; khi rollback, callback đúng pha rollback chạy và DB phục hồi trạng thái ban đầu.

Nếu thử thay `AFTER_COMMIT` bằng một `@EventListener` thường để gửi thông báo thật, thông báo có thể xảy ra ngay cả ở test rollback. Đó là lý do không để hiệu ứng bên ngoài quan trọng trong listener đồng bộ nếu điều kiện nghiệp vụ yêu cầu commit trước.

### 6.3. Vì sao không đặt @Transactional trên chính test?

Trong Spring TestContext, test có `@Transactional` thường bị **rollback tự động** sau test method. Nếu chỉ dựa vào test transaction đó, callback `AFTER_COMMIT` chưa có cơ hội chạy khi assertion được kiểm tra bên trong method. Ví dụ dùng `TransactionTemplate` trong một test không bọc transaction để chủ động kết thúc commit/rollback ngay trong lời gọi service.

Nếu bắt buộc dùng test-managed transaction, có thể sử dụng `TestTransaction.flagForCommit()` rồi `TestTransaction.end()` trong trường hợp phù hợp. Với JPA/Hibernate, cần xem thêm thời điểm `flush` và các ràng buộc DB; tránh nhầm persistence context đã đổi với dữ liệu đã commit.

## 7. Sự cố sau commit: tại sao event nội bộ chưa đủ bền?

`@TransactionalEventListener(AFTER_COMMIT)` giúp tránh xử lý khi transaction rollback. Nhưng có một **khoảng trống sau commit**:

~~~text
T0: UPDATE order
T1: COMMIT thành công
T2: JVM/process đột ngột dừng
T3: Listener AFTER_COMMIT chưa kịp gọi broker/email
=> DB đã đổi, nhưng notification có thể bị mất.
~~~

Ngay cả khi listener đã chạy, broker hoặc hệ thống ngoài cũng có thể lỗi mạng; retry có thể gửi nhiều lần. Vì vậy `AFTER_COMMIT` là điều kiện thời điểm, không phải hợp đồng giao nhận exactly-once. Khi thông báo chỉ mang tính phụ, có thể chấp nhận rủi ro kết hợp logging/retry ở mức phù hợp. Khi một event bắt buộc phải được giao, cần lưu **ý định publish** bền vững.

### Transactional outbox

Mẫu phổ biến là ghi **dữ liệu nghiệp vụ và bản ghi outbox trong cùng một database transaction**:

~~~sql
BEGIN;

UPDATE orders
SET state = 'PAID'
WHERE id = 'O-42';

INSERT INTO outbox(event_id, aggregate_id, event_type,
                   payload, delivery_state)
VALUES ('E-42', 'O-42', 'OrderPaid',
        '{"orderId":"O-42"}', 'PENDING');

COMMIT;
~~~

SQL trên là **minh họa ý tưởng**, cần schema thực tế, các cột định danh và xử lý lỗi phù hợp trước khi chạy trong sản phẩm. Nếu transaction rollback, cả update và outbox insert đều rollback. Một worker độc lập đọc các outbox record đã commit rồi publish sang broker, sau đó đánh dấu kết quả; khi lỗi thì retry. Vì một bản ghi có thể được gửi lại, consumer phải xử lý idempotent, thường theo `eventId`.

~~~text
Business transaction:
  UPDATE order + INSERT outbox  -- atomic commit

Publisher worker:
  read committed outbox
  -> send broker with retry
  -> mark delivered

Consumer:
  deduplicate by eventId
  -> apply business side effect
~~~

Outbox giải quyết rủi ro “đã commit DB nhưng chưa ghi ý định gửi”. Nó **không tự đảm bảo exactly-once end-to-end**, cũng không tự bảo đảm thứ tự toàn cục giữa mọi aggregate. Nếu cần thứ tự theo từng `orderId`, hãy chọn partition key và cơ chế xử lý bảo toàn thứ tự theo khóa đó.

### Spring Modulith Event Publication Registry

Khi hệ thống gồm nhiều application module trong một Spring application, **Spring Modulith** cung cấp cơ chế ghi nhận việc phát application event đến các transactional listeners vào một publication registry. Registry có thể lưu thông tin publication trong transaction nguồn, đánh dấu hoàn thành khi listener xử lý xong, và hỗ trợ tìm/resubmit publication chưa hoàn thành theo cơ chế và cấu hình được chọn.

Đây là cơ chế bổ trợ cụ thể của **Spring Modulith**, **không phải mặc định của Spring Framework**. Nó cần dependency, persistence integration và cấu hình thích hợp. Cũng không nên đánh đồng mọi cách externalization của Modulith với một transactional outbox giao broker đầy đủ; phải kiểm tra đảm bảo giao nhận của adapter đang dùng.

## 8. Chọn thiết kế theo yêu cầu transaction

| Tình huống | Gợi ý thiết kế | Cần kiểm thử |
| --- | --- | --- |
| Bất biến của cùng aggregate bắt buộc giữ đúng | Xử lý trực tiếp trong aggregate/application service cùng transaction | Quy tắc domain + rollback khi vi phạm |
| Listener cập nhật dữ liệu liên quan và phải commit/rollback cùng nghiệp vụ | Listener đồng bộ trong cùng transaction, nếu có lý do tách module rõ ràng | Listener tham gia transaction, failure policy |
| Gửi email sau khi thanh toán thực sự commit; chấp nhận rủi ro hiếm của process crash | `@TransactionalEventListener(AFTER_COMMIT)` | Commit gửi, rollback không gửi; lỗi gateway được quan sát |
| Bắt buộc không mất ý định giao event | Transactional outbox hoặc registry có cơ chế khôi phục phù hợp | Crash ở các mốc, retry, idempotency, ordering key |
| Listener tạo bản ghi mới sau commit | Mở transaction riêng (`REQUIRES_NEW`) | Bản ghi có commit riêng và đọc được sau callback |
| Hai nghiệp vụ ở hai microservice | Mỗi service có transaction riêng + integration event và eventual consistency | Dữ liệu cuối, thông điệp trùng, thất bại tạm thời |
| Reactive transaction bằng R2DBC | Giữ event trong Reactor subscriber context; dùng `TransactionalEventPublisher` | Commit/rollback với `ReactiveTransactionManager` |

Đặc biệt, **`@Order` không tạo transaction boundary**. Thứ tự invocation listener không thay thế commit, không tạo lock, không làm cho email tham gia DB transaction. Đồng thời, dùng `@Async` làm listener chạy thread khác cũng không có nghĩa context transaction từ thread gốc được truyền sang.

Với reactive transaction, Spring Framework 6.1+ hỗ trợ `@TransactionalEventListener` khi event mang `TransactionContext` trong source; `TransactionalEventPublisher` là tiện ích gắn context từ Reactor chain. Không áp dụng trực tiếp giả định JDBC thread-bound của ví dụ trên cho pipeline R2DBC.

## 9. Các lỗi thiết kế phổ biến

**1. Phát domain event rồi nghĩ rằng dữ liệu đã commit.** Event có thể được tạo và publish bên trong transaction chưa hoàn tất. Cần nêu rõ consumer nào được chạy trước commit và consumer nào phải chờ kết quả transaction.

**2. Dùng listener để che giấu bước nghiệp vụ bắt buộc.** Nếu “A phải thành công trước B” là bất biến, một lời gọi service tường minh/aggregate operation có thể dễ hiểu và dễ debug hơn một chuỗi event listener không hiển thị tại call site.

**3. Gửi email hoặc HTTP đồng bộ trước commit.** Rollback chỉ hủy thay đổi nằm trong transaction, không thu hồi request gửi bên ngoài. Nếu phù hợp, dời side effect sang after-commit; nếu không được mất thông báo, dùng outbox.

**4. Bật `fallbackExecution = true` mà không xét yêu cầu.** Listener transactional khi đó có thể chạy cả ngoài transaction, khiến ý nghĩa “chỉ sau commit” không còn đúng cho mọi lần gọi.

**5. Ghi DB trong `AFTER_COMMIT` nhưng không mở transaction mới.** Có thể tương tác với tài nguyên transaction cũ sau commit mà không có lần commit tiếp theo. Mở transaction mới, dùng `REQUIRES_NEW`, và test readback.

**6. Đưa JPA entity mutable vào payload event rồi xử lý muộn.** Sau transaction, entity có thể detached; lazy fields không sẵn sàng, object có thể khác trạng thái tại lúc publish. Dùng immutable DTO/record chứa ID và dữ liệu cần thiết.

**7. Hiểu nhầm `@Async` là durable.** Async listener có thể mất tác vụ khi process chết; exception không nhất thiết truyền ngược đến publisher. Sử dụng retry/idempotency, registry hoặc outbox nếu yêu cầu delivery.

**8. Viết integration test có `@Transactional` rồi mong `AFTER_COMMIT` chạy ngay.** TestContext thường rollback test transaction ở cuối test. Hãy chủ động commit bằng `TransactionTemplate` hoặc `TestTransaction` khi cần kiểm tra callback sau commit.

**9. Truyền một event ra nhiều hệ thống mà không có ID/version.** Retry thường tạo duplicate; các consumer cần khóa idempotency và khi cần có thông tin phiên bản/sequence để kiểm soát cập nhật không đúng thứ tự.

## 10. Câu hỏi tự kiểm tra

**Câu 1:** Nếu một service gọi `repository.save(order)` rồi `publishEvent(new OrderPaid(...))` bên trong `@Transactional`, event đã chắc chắn bền vững chưa?

Chưa. Bản ghi DB có thể chưa flush và transaction vẫn có thể rollback; lệnh publish bằng `ApplicationEventPublisher` không đồng nghĩa với một lần commit hay lưu event bền vững.

**Câu 2:** Khi nào nên dùng `@EventListener` đồng bộ và khi nào nên dùng `@TransactionalEventListener`?

Dùng listener đồng bộ khi công việc cần xảy ra trong luồng đang phát event và có thể phù hợp với transaction của caller. Dùng transactional listener khi việc xử lý phải phụ thuộc vào kết cục commit/rollback, đặc biệt với side effect sau commit.

**Câu 3:** Vì sao listener `AFTER_COMMIT` không bảo đảm email chắc chắn tới được khách?

Vì callback có thể chưa chạy khi process chết sau commit; gateway có thể lỗi. Nó chỉ gắn thời điểm xử lý với commit, không cung cấp durable queue và retry hoàn chỉnh.

**Câu 4:** Outbox đảm bảo điều gì và còn cần gì?

Nó cho phép lưu trạng thái nghiệp vụ và ý định gửi event **atomically** trong cùng DB transaction. Cần worker giao nhận, retry, xử lý duplicate/idempotency và ordering theo yêu cầu.

**Câu 5:** Nếu event được publish bên ngoài transaction thì `@TransactionalEventListener` mặc định có chạy không?

Không. Không có transaction phù hợp để đăng ký callback; chỉ khi bật `fallbackExecution = true` mới có nhánh xử lý fallback với semantics khác.

**Điểm cần nhớ:** domain event và transaction boundary phải được thiết kế cùng nhau. **Aggregate chuyển trạng thái**, **event được publish**, **database commit** và **consumer nhận hiệu ứng** là các mốc độc lập. Chọn listener đồng bộ, listener theo transaction phase hoặc outbox dựa vào yêu cầu nhất quán và giao nhận, rồi kiểm thử cả commit, rollback và lỗi sau commit.

## Tài liệu tham khảo

- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework – Application Events và mặc định dispatch đồng bộ](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework – TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework – TransactionSynchronization API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Modulith – Working with Application Events và Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)

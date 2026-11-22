# Idempotency của event listener trong Spring Framework Application Events

## 1. Vấn đề: một sự kiện có thể được xử lý nhiều lần

Một ứng dụng thanh toán phát `PaymentCaptured` để lên lịch gửi biên nhận. Khi môi trường có retry, message redelivery, nhiều worker hoặc thao tác publish lặp, cùng một sự kiện có thể đến listener hơn một lần. Nếu mỗi callback đều thực hiện cùng tác dụng phụ, hệ thống có thể gửi hai email, tạo hai hóa đơn hoặc cộng điểm hai lần.

Ví dụ:

```text
PaymentCaptured(eventId="evt-pay-100")
             |
             +--> callback lần 1 --> lên lịch gửi biên nhận
             |
             +--> callback lần 2 --> lên lịch gửi biên nhận LẦN NỮA
```

Spring Application Events **không tự cung cấp exactly-once delivery hoặc khử trùng theo eventId**. Một lần gọi `ApplicationEventPublisher.publishEvent(...)` là thao tác chuyển event cho hạ tầng phân phối; framework không biết hai object có cùng `eventId` phải được xem là một nghiệp vụ. Trong ứng dụng dùng multicaster mặc định, listener thường chạy đồng bộ; với `@Async` hoặc executor của multicaster, thứ tự và thời điểm hoàn tất có thể khác. Dù ở chế độ nào, **idempotency là hợp đồng của handler và dữ liệu nghiệp vụ**, không phải một bảo đảm ngầm từ event bus. 

**Idempotency** nghĩa là: việc áp dụng lại cùng một thao tác (theo tiêu chí nhận diện được định nghĩa rõ) **không làm thay đổi kết quả nghiệp vụ sau lần thực hiện thành công đầu tiên**. Một listener idempotent có thể **được gọi nhiều lần** nhưng không được tạo **tác dụng phụ trùng ngoài ý muốn**.

Điểm quan trọng: idempotent **không có nghĩa listener chỉ chạy một lần**; cũng không có nghĩa broker chuyển message đúng một lần; và không tự giải quyết trường hợp event bị **mất hoàn toàn**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt event phát lại, duplicate delivery, tác dụng phụ trùng và một hành động nghiệp vụ hợp lệ khác.
- Thiết kế khóa idempotency theo **consumer + eventId** hoặc theo một business invariant thích hợp.
- Hiểu vì sao kiểm tra `exists(...)` rồi mới `insert(...)` không an toàn khi xử lý đồng thời.
- Dùng **unique constraint** và transaction để bảo đảm việc ghi marker và tạo tác dụng phụ nội bộ là nguyên tử.
- Tách **receipt marker** khỏi **transactional outbox** và khỏi thao tác gửi email/HTTP thật.
- Dùng `@TransactionalEventListener(AFTER_COMMIT)` đúng thời điểm, hiểu khi nào cần `REQUIRES_NEW`.
- Kiểm thử duplicate, rollback, concurrency, retry và các “cửa sổ crash”.
- Nhận biết giới hạn: **idempotency không thay thế durability**, exactly-once end-to-end hoặc cơ chế phục hồi.

Chủ đề thuộc nhóm **Độ tin cậy** của Spring Framework Application Events. Trọng tâm là xây handler an toàn khi **cùng sự kiện được giao lại**.

## 2. Khi nào cùng một event có thể xuất hiện lần nữa?

Các tình huống rất thực tế:

1. **Gọi publish hai lần trong code.** Hai lớp controller/service cùng phát `OrderAccepted` hoặc một vòng lặp gọi `publishEvent` lặp.
2. **Retry của method nghiệp vụ.** AOP retry, HTTP client retry, scheduler hoặc thao tác người dùng gửi lại request.
3. **Broker giao lại message.** Consumer xử lý xong nhưng crash trước khi ack/commit offset; broker có thể chuyển lại.
4. **Outbox poller chạy lại.** Worker gửi event rồi chết trước khi đánh dấu outbox row đã được xử lý.
5. **Hai worker cạnh tranh.** Cùng công việc được claim do khóa/distributed coordination chưa đủ.
6. **Replay lịch sử.** Event store hoặc bộ khôi phục read model phát lại event cũ.
7. **Listener có nhiều đường đăng ký.** Một sự kiện có thể đến nhiều handler hoặc hai instance cùng chức năng; idempotency phải xác định **hiệu ứng nào cần bảo vệ**.
8. **Timeout phía ngoài.** Email/HTTP đã được xử lý nhưng client chưa nhận được response; retry có thể lặp effect.

Cần xác định **event occurrence** là gì. Nếu `PaymentCaptured(eventId="evt-100")` được giao lại, đó thường là **cùng occurrence** với eventId giữ nguyên. Nếu có hai lần thanh toán khác nhau cho cùng một đơn, chúng có thể cùng `orderId` nhưng có **eventId/paymentId khác nhau** và cả hai đều hợp lệ.

Đừng dùng một bộ lọc rộng như “đơn này đã từng có event bất kỳ” để chặn những sự việc nghiệp vụ khác nhau.

## 3. Ba khái niệm: invocation, occurrence và effect

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Listener invocation | Phương thức listener đã được gọi bao nhiêu lần? | `onCaptured` nhận 3 callback |
| Event occurrence | Những callback đó có thuộc cùng một sự kiện nghiệp vụ không? | Cả 3 mang `eventId="evt-100"` |
| Business effect | Bao nhiêu kết quả thực tế được tạo? | Chỉ 1 công việc gửi biên nhận trong outbox |

Một listener idempotent **không cần che giấu số lần invocation**. Tốt hơn, hãy quan sát rõ cả `attempts`, `accepted` và `duplicatesSkipped`. Khi ba callback dẫn đến một outbox row, ta có thể chứng minh hiệu ứng idempotent theo khóa đã chọn.

### Không đồng nhất với exactly-once

Có thể đạt **effect-once cho một bất biến cụ thể** (ví dụ “một outbox row cho mỗi payment event và consumer”) dù event được gửi ít nhất một lần. Nhưng không nên tuyên bố “exactly-once toàn hệ thống” nếu chưa chứng minh cả transaction, broker, API ngoài, các replica và những tình huống crash.

Cơ chế chống trùng không bảo đảm **event nào cũng tới listener ít nhất một lần**. Một event bị mất sau commit nhưng trước khi callback chạy không thể được cứu chỉ bằng bảng `processed_events`.

## 4. Chọn khóa idempotency đúng

### 4.1. eventId phải ổn định qua retry

Payload record:

```java
public record PaymentCaptured(
        String eventId,
        String paymentId,
        String correlationId
) {}
```

Các field có vai trò khác nhau:

- `eventId`: định danh **một occurrence** của sự kiện.
- `paymentId`: định danh nghiệp vụ một lần thanh toán.
- `correlationId`: liên kết các bước thuộc cùng request/workflow; **không phải khóa dedupe mặc định**.
- Nếu có `causationId`, nó mô tả event cha trực tiếp, không định danh duy nhất mọi event con.

Khi retry **cùng một occurrence**, phải giữ `eventId`. Nếu mỗi lần retry sinh một UUID mới, listener dựa trên eventId sẽ xem đó là các event mới.

### 4.2. Khóa theo consumer + eventId

Một sự kiện `PaymentCaptured` có thể cần **cả** email, audit và projection:

```text
PaymentCaptured(evt-100)
     |
     +--> receipt-email-scheduler
     |
     +--> accounting-projection
     |
     +--> audit-logger
```

Nếu bảng processed chỉ khóa theo `eventId` toàn cục, consumer email có thể chặn nhầm consumer projection. Để mỗi consumer độc lập xử lý event một lần, dùng cặp:

```text
(consumer_name, event_id)
```

Ví dụ ba marker hợp lệ:

```text
(receipt-email-scheduler, evt-100)
(accounting-projection,  evt-100)
(audit-logger,           evt-100)
```

**Lưu ý:** các tên consumer này là danh tính chức năng ổn định, không nên gắn với random process ID hoặc tên thread. Nếu mỗi lần restart sinh `consumer_name` khác, hệ thống mất khả năng nhận biết event đã xử lý trước đó.

### 4.3. Khóa theo hiệu ứng nghiệp vụ

Có trường hợp **hai eventId khác nhau** nhưng chúng cùng yêu cầu tạo **một hóa đơn cho cùng paymentId**. Khi đó chống trùng theo `(consumer, eventId)` **chưa đủ** để bảo vệ bất biến “một hóa đơn cho mỗi payment”. Nên bổ sung unique business key như:

```sql
CREATE UNIQUE INDEX uq_invoice_payment
    ON invoices(payment_id);
```

Đây là ví dụ schema tích hợp, yêu cầu bảng `invoices` tồn tại; không nằm trong chương trình Maven ở mục 8.

Thiết kế vững thường có **hai lớp bảo vệ**:

1. **Delivery dedupe:** `(consumer_name,event_id)` chống giao lại cùng occurrence cho cùng handler.
2. **Business uniqueness:** ví dụ `payment_id + invoice_type` chống hai event khác nhau cùng tạo hiệu ứng bị cấm lặp.

Không dùng `correlationId` để dedupe toàn workflow: một workflow chứa nhiều event khác nhau cùng correlation là bình thường.

## 5. Vì sao bộ nhớ cục bộ không đủ?

Phản ví dụ:

```java
private final Set<String> processed = ConcurrentHashMap.newKeySet();

@EventListener
public void onCaptured(PaymentCaptured event) {
    if (!processed.add(event.eventId())) {
        return;
    }
    sendReceipt(event.paymentId());
}
```

Đây là đoạn **không đủ an toàn cho production**, không phải chương trình độc lập. Nó chỉ ghi nhớ trong một process:

- Restart làm mất `processed`.
- Mỗi replica có một set khác nhau.
- Event bị đánh dấu trước khi gửi; nếu gửi lỗi, retry trong cùng process có thể bị chặn vĩnh viễn.
- Thao tác `sendReceipt` có thể thành công rồi báo timeout; mã không biết có được retry hay không.
- Không có transaction với database; không ràng buộc marker và side effect.

Ngay cả `ConcurrentHashMap` bảo đảm atomic add trên **một JVM** cũng không xử lý được ranh giới process, crash và external API.

Một biến thể khác, `if (!repository.existsById(...)) repository.save(...)`, cũng không an toàn khi **hai transaction cùng đọc “chưa có” rồi cùng insert**. Việc “check trước” không thay unique constraint do database thực thi.

## 6. Bảo vệ bằng unique constraint và transaction nguyên tử

### 6.1. Marker cho từng consumer

Schema tối thiểu:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Database từ chối lần insert marker thứ hai có cùng cặp khóa. Khi hai worker cạnh tranh, database quyết định theo constraint/transaction isolation và lock thực tế, thay vì để hai luồng tự đánh giá một biến boolean.

### 6.2. Marker và effect nội bộ phải cùng transaction

Giả sử listener muốn tạo một yêu cầu gửi biên nhận trong bảng `notification_outbox`. Luồng xử lý:

```text
BEGIN TRANSACTION
       |
       +--> INSERT processed_events(consumer, eventId)
       |      |
       |      +--> Trùng khóa?  -> ROLLBACK, bỏ qua occurrence đã xử lý
       |
       +--> INSERT notification_outbox(...)
       |
COMMIT
```

Nếu insert outbox thất bại, transaction rollback **cả marker**; lần retry sau có thể thử lại hợp lệ. Nếu insert marker thất bại vì khóa đã tồn tại, transaction chứa lời gọi đó rollback, và logic nhận biết đây là duplicate.

**Tránh bắt exception unique constraint rồi tiếp tục dùng transaction đang lỗi.** Trên một số DB, transaction sau SQL error không còn hợp lệ cho các câu lệnh tiếp theo. Cách dễ kiểm soát là để exception làm rollback transaction và chỉ **bắt/diễn giải sau ranh giới transaction**.

### 6.3. Phân biệt lỗi duplicate với lỗi khác

Không nên:

```java
try {
    saveMarkerAndOutbox();
} catch (Exception ignored) {
    // "Chắc là trùng" — sai: có thể do DB down, timeout,
    // syntax error, dữ liệu vô hiệu hoặc outbox insert lỗi.
}
```

Đây là **phản ví dụ**. Chỉ bỏ qua trường hợp constraint cho biết marker **đã tồn tại** theo khóa cần xử lý. Lỗi DB không liên quan cần được báo, retry hoặc chuyển DLQ theo chính sách của nguồn delivery.

Khi dùng Spring JDBC, `DuplicateKeyException` là một kiểu cụ thể của `DataIntegrityViolationException`. Hệ thống thật nên kiểm tra mapping lỗi unique constraint theo database/driver và tên constraint nếu có nhiều constraint có thể vi phạm. Demo bên dưới bắt `DuplicateKeyException` **chỉ quanh câu INSERT marker**, rồi chuyển thành tín hiệu duplicate nội bộ; mọi lỗi khác vẫn được ném ra.

## 7. Đặt transaction ở đâu với Spring Application Events?

### 7.1. @EventListener đồng bộ

Với multicaster mặc định, `@EventListener` đồng bộ thường chạy trên thread đang publish. Nếu publisher đang trong transaction, callback có thể tham gia transaction đó.

Ví dụ khái niệm:

```java
@Transactional
public void capturePayment(PaymentCommand command) {
    paymentRepository.save(...);
    publisher.publishEvent(new PaymentCaptured(...));
}
```

Đây là đoạn minh họa thiếu repository/command, **không phải mã độc lập**. Listener đồng bộ có thể chạy trước commit, nên nếu gọi email/HTTP trực tiếp thì rollback business transaction **không thu hồi email đã gửi**.

Nếu marker và thay đổi DB của listener nằm trong **cùng transaction nguồn**, rollback sẽ làm mất marker và thay đổi DB cùng nhau, nhưng cần quyết định rõ listener có được phép tạo tác dụng phụ trước commit hay không.

### 7.2. @TransactionalEventListener(AFTER_COMMIT)

Một callback hậu commit:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCaptured(PaymentCaptured event) {
    // Được gọi sau khi transaction nguồn commit thành công.
}
```

Mặc định `@TransactionalEventListener` dùng `AFTER_COMMIT`. Nếu publish ngoài một transaction đang hoạt động, listener này **thường không được gọi** vì `fallbackExecution = false`. Nếu transaction rollback, listener AFTER_COMMIT **không được chạy**.

Điểm quan trọng: **AFTER_COMMIT không tự chống duplicate**. Nếu publisher phát cùng event hai lần trong transaction đã commit, có thể có **hai callback hậu commit**. Và mỗi lần callback được gọi, nó vẫn phải dùng marker/idempotency để bảo vệ effect.

### 7.3. REQUIRES_NEW khi ghi DB hậu commit

Spring cảnh báo rằng trong callback completion, một số resource của transaction nguồn có thể **vẫn còn gắn với thread** dù commit đã xảy ra. Nếu ghi DB hậu commit mà không bắt đầu một transaction mới thực sự, dữ liệu có thể “tham gia” resource cũ nhưng **không còn commit tiếp theo**.

Vì vậy khi callback `AFTER_COMMIT` cần ghi marker và outbox mới, nên dùng:

- `@Transactional(propagation = Propagation.REQUIRES_NEW)` qua **Spring proxy** trên một service riêng; hoặc
- `TransactionTemplate` được cấu hình `PROPAGATION_REQUIRES_NEW`.

Không gọi một phương thức `@Transactional(REQUIRES_NEW)` qua `this.method()` trong cùng bean rồi nghĩ proxy đã kích hoạt; self-invocation có thể bỏ qua Spring AOP transaction.

### 7.4. Cảnh báo nghiêm trọng: AFTER_COMMIT + marker vẫn có cửa sổ mất event

Luồng:

```text
BEGIN business transaction
    save payment
    publish PaymentCaptured in memory
COMMIT business transaction    <-- dữ liệu nghiệp vụ bền vững
    |
    | process crash tại đây
    v
@TransactionalEventListener(AFTER_COMMIT)
    insert processed marker + outbox
```

Nếu process chết **sau business commit nhưng trước khi listener ghi outbox**, không có callback nào để retry sau restart. Không có marker và cũng không có outbox. Idempotency chỉ giải quyết **duplicate nếu event được xử lý lại**, chứ không cứu được event **chưa từng được lưu**.

**Khi yêu cầu không được mất event:** ghi outbox record (đại diện cho event cần chuyển) **trong cùng business transaction** với thay đổi payment, sau đó worker độc lập đọc, retry và publish. Khi đó local Spring event hậu commit có thể được dùng như **gợi ý đánh thức worker**, không phải nguồn duy nhất đảm bảo delivery.

## 8. Ví dụ hoàn chỉnh Java 17 + Spring Framework 6.2 + JDBC + H2

Ví dụ này minh họa cụ thể hợp đồng **“cùng một PaymentCaptured được gửi lại nhưng chỉ tạo một công việc outbox”**. Dự án dùng Spring Framework thuần, không cần Spring Boot, web server hay message broker.

Mô hình:

- `PaymentCaptured` là record payload với `eventId` ổn định.
- `PaymentCaptured` được publish **hai lần trong một transaction đã commit**, rồi publish thêm **một lần trong transaction khác** để mô phỏng replay.
- Một event khác được publish trong transaction **rollback**, nên `@TransactionalEventListener(AFTER_COMMIT)` không xử lý.
- Một event nữa được publish **ngoài transaction**, nên listener với `fallbackExecution=false` không chạy.
- Listener hậu commit dùng `TransactionTemplate` với `PROPAGATION_REQUIRES_NEW`.
- Trong transaction mới, listener insert marker `(receipt-scheduler,eventId)` rồi insert một row `notification_outbox`. Lần lặp trùng bị chặn bằng unique constraint.
- Không gửi email thật: outbox là **yêu cầu gửi** bền vững, không phải bằng chứng email đã gửi.

### 8.1. Cấu trúc dự án

```text
idempotent-spring-event-listener/
├── pom.xml
└── src/main/java/example/IdempotentEventDemo.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>idempotent-spring-event-listener</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.0</version>
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
                <configuration>
                    <mainClass>example.IdempotentEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. src/main/java/example/IdempotentEventDemo.java

```java
package example;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class IdempotentEventDemo {

    // Một occurrence thanh toán: eventId phải giữ nguyên khi replay.
    public record PaymentCaptured(
            String eventId,
            String paymentId,
            String correlationId) {

        public PaymentCaptured {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(paymentId, "paymentId");
            Objects.requireNonNull(correlationId, "correlationId");
            if (eventId.isBlank()
                    || paymentId.isBlank()
                    || correlationId.isBlank()) {
                throw new IllegalArgumentException(
                        "Identifiers cannot be blank");
            }
        }
    }

    // Chỉ đại diện cho vi phạm unique key của receipt marker.
    private static final class DuplicateDelivery
            extends RuntimeException {
        DuplicateDelivery(DuplicateKeyException cause) {
            super(cause);
        }
    }

    public static class ReceiptScheduler {
        private static final String CONSUMER = "receipt-scheduler";

        private final JdbcTemplate jdbc;
        private final TransactionTemplate newWorkTx;
        private final AtomicInteger attempts = new AtomicInteger();
        private final AtomicInteger scheduled = new AtomicInteger();
        private final AtomicInteger duplicates = new AtomicInteger();

        public ReceiptScheduler(JdbcTemplate jdbc,
                                TransactionTemplate newWorkTx) {
            this.jdbc = jdbc;
            this.newWorkTx = newWorkTx;
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void onCaptured(PaymentCaptured event) {
            attempts.incrementAndGet();

            try {
                newWorkTx.executeWithoutResult(status -> {
                    try {
                        // Atomic claim, dựa vào PRIMARY KEY ở DB.
                        jdbc.update(
                                "INSERT INTO processed_events "
                                + "(consumer_name, event_id) "
                                + "VALUES (?, ?)",
                                CONSUMER, event.eventId());
                    } catch (DuplicateKeyException duplicate) {
                        // Để TransactionTemplate rollback trước khi
                        // caller diễn giải đây là duplicate.
                        throw new DuplicateDelivery(duplicate);
                    }

                    // Cùng transaction với marker: nếu lỗi,
                    // marker cũng rollback, retry có thể làm lại.
                    jdbc.update(
                            "INSERT INTO notification_outbox "
                            + "(consumer_name, event_id, payment_id, "
                            + "correlation_id) VALUES (?, ?, ?, ?)",
                            CONSUMER, event.eventId(),
                            event.paymentId(), event.correlationId());
                });

                // Chỉ đếm khi transaction mới commit thành công.
                scheduled.incrementAndGet();
            } catch (DuplicateDelivery alreadyHandled) {
                duplicates.incrementAndGet();
            }
        }

        public int attempts() {
            return attempts.get();
        }

        public int scheduled() {
            return scheduled.get();
        }

        public int duplicates() {
            return duplicates.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds =
                    new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                    "jdbc:h2:mem:idempotency_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean("businessTx")
        public TransactionTemplate businessTx(
                PlatformTransactionManager transactionManager) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean("newWorkTx")
        public TransactionTemplate newWorkTx(
                PlatformTransactionManager transactionManager) {
            TransactionTemplate template =
                    new TransactionTemplate(transactionManager);
            template.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRES_NEW);
            return template;
        }

        @Bean
        public ReceiptScheduler receiptScheduler(
                JdbcTemplate jdbc,
                @Qualifier("newWorkTx")
                TransactionTemplate newWorkTx) {
            return new ReceiptScheduler(jdbc, newWorkTx);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate businessTx =
                    context.getBean(
                            "businessTx", TransactionTemplate.class);
            ReceiptScheduler scheduler =
                    context.getBean(ReceiptScheduler.class);

            jdbc.execute(
                    "CREATE TABLE payment_records ("
                    + "event_id VARCHAR(80) PRIMARY KEY,"
                    + "payment_id VARCHAR(80) NOT NULL)");
            jdbc.execute(
                    "CREATE TABLE processed_events ("
                    + "consumer_name VARCHAR(80) NOT NULL,"
                    + "event_id VARCHAR(80) NOT NULL,"
                    + "PRIMARY KEY (consumer_name, event_id))");
            jdbc.execute(
                    "CREATE TABLE notification_outbox ("
                    + "id BIGINT GENERATED BY DEFAULT AS IDENTITY "
                    + "PRIMARY KEY,"
                    + "consumer_name VARCHAR(80) NOT NULL,"
                    + "event_id VARCHAR(80) NOT NULL,"
                    + "payment_id VARCHAR(80) NOT NULL,"
                    + "correlation_id VARCHAR(80) NOT NULL,"
                    + "UNIQUE (consumer_name, event_id))");

            PaymentCaptured captured = new PaymentCaptured(
                    "evt-100", "PAY-42", "flow-7");

            // Hai lần publish cùng occurrence trước business commit.
            businessTx.executeWithoutResult(status -> {
                jdbc.update(
                        "INSERT INTO payment_records "
                        + "(event_id, payment_id) VALUES (?, ?)",
                        captured.eventId(), captured.paymentId());
                context.publishEvent(captured);
                context.publishEvent(captured);
            });

            // Giao lại cùng occurrence trong transaction khác.
            businessTx.executeWithoutResult(
                    status -> context.publishEvent(captured));

            // Event phát trong transaction rollback: không AFTER_COMMIT.
            PaymentCaptured rolledBack = new PaymentCaptured(
                    "evt-rollback", "PAY-X", "flow-X");
            businessTx.executeWithoutResult(status -> {
                jdbc.update(
                        "INSERT INTO payment_records "
                        + "(event_id, payment_id) VALUES (?, ?)",
                        rolledBack.eventId(), rolledBack.paymentId());
                context.publishEvent(rolledBack);
                status.setRollbackOnly();
            });

            // Ngoài transaction: fallbackExecution mặc định false.
            context.publishEvent(
                    new PaymentCaptured(
                            "evt-no-tx", "PAY-NO", "flow-NO"));

            System.out.println("Listener attempts: "
                    + scheduler.attempts());
            System.out.println("Scheduled once: "
                    + scheduler.scheduled());
            System.out.println("Duplicates skipped: "
                    + scheduler.duplicates());
            System.out.println("Payment records: "
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM payment_records",
                            Integer.class));
            System.out.println("Processed markers: "
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM processed_events",
                            Integer.class));
            System.out.println("Outbox rows: "
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM notification_outbox",
                            Integer.class));
        }
    }
}
```

### 8.4. Chạy ứng dụng

Trong thư mục chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

**Sáu dòng kết quả do chương trình in**, không tính log hạ tầng của Maven/Spring:

```text
Listener attempts: 3
Scheduled once: 1
Duplicates skipped: 2
Payment records: 1
Processed markers: 1
Outbox rows: 1
```

Giải thích:

1. Lần business transaction đầu tiên lưu một `payment_records` và publish **hai lần** cùng `PaymentCaptured("evt-100", ...)`.
2. Business transaction commit; hai callback hậu commit được kích hoạt. Callback thứ nhất mở transaction `REQUIRES_NEW`, insert marker và outbox, commit thành công. Callback thứ hai insert cùng marker nên vi phạm `PRIMARY KEY`, bị rollback, rồi được tính là duplicate.
3. Một transaction mới publish lại cùng `evt-100`. Listener lại nhận callback và lại bị chặn bởi marker đã commit.
4. Transaction chứa `evt-rollback` chủ động rollback. Không có callback `AFTER_COMMIT` cho event này; `payment_records` của nó cũng rollback.
5. Event `evt-no-tx` được publish không có transaction; listener với `fallbackExecution=false` không chạy.
6. Vì vậy có **3 callback được thực thi**, **1 scheduling thành công** và **2 duplicate được bỏ qua**; database chỉ có một payment record, một marker và một outbox row.

**Vì sao dùng transaction mới?** `@TransactionalEventListener(AFTER_COMMIT)` được gọi sau khi transaction nguồn commit. `newWorkTx` được cấu hình `PROPAGATION_REQUIRES_NEW`, bảo đảm marker và outbox nằm trong giao dịch độc lập có commit riêng.

**Vì sao catch duplicate ở ngoài ranh giới transaction?** Bên trong lambda, chỉ riêng `INSERT processed_events` được chuyển lỗi `DuplicateKeyException` thành `DuplicateDelivery`. TransactionTemplate thấy runtime exception nên rollback. Ngoài transaction, listener bắt đúng `DuplicateDelivery` và đánh dấu bỏ qua. Lỗi tạo outbox hoặc lỗi DB khác **không bị nuốt như duplicate**.

**Giới hạn của ví dụ:** mã dùng H2 in-memory DB và chạy một process. Khi process kết thúc, dữ liệu H2 không tồn tại bền vững qua restart. `DriverManagerDataSource` không dùng connection pool; phù hợp demo, không phải cấu hình production. Để chứng minh độ tin cậy khi crash/restart, cần DB bền vững, outbox worker thật, idempotency phía recipient, và integration test nhiều process.

Ví dụ kiểm tra **duplicate theo eventId ở listener hậu commit**, nhưng **không sửa cửa sổ mất event giữa business commit và AFTER_COMMIT callback**. Phần 10 trình bày kiến trúc mạnh hơn để giải quyết durability.

## 9. Điều gì xảy ra khi hai worker xử lý đồng thời?

Giả sử hai replica đồng thời nhận cùng `eventId=evt-100`:

```text
Worker A                      Worker B
   |                             |
   | BEGIN                       | BEGIN
   | INSERT processed(evt-100)   | INSERT processed(evt-100)
   |      |                      |      |
   |      +--> thắng khóa DB     |      +--> chờ hoặc lỗi unique
   | INSERT outbox               |
   | COMMIT                      | ROLLBACK / duplicate
   |
   +--> chỉ một outbox effect
```

Với primary key/unique constraint thực thi đúng trên database dùng chung, hai transaction không thể **cùng commit** hai marker có cùng khóa. Chi tiết worker nào chờ, worker nào nhận exception và thời điểm lỗi phụ thuộc database/isolation/driver; không nên mặc định worker B lúc nào cũng thất bại ngay ở câu INSERT.

Mẫu kiểm tra trước:

```java
if (!repository.existsById(key)) {
    repository.insert(key);
    createOutboxWork();
}
```

là **phản ví dụ**: cả hai worker có thể cùng đọc “chưa có”. Chỉ khi database thực thi constraint và transaction đi cùng effect, ta mới có nền tảng chống trùng đủ mạnh giữa nhiều process.

**Nhưng nếu logic createOutboxWork() được gọi trước khi claim key**, hai worker có thể đã thực hiện effect rồi mới tranh chấp marker. Vì vậy **claim marker trước effect nội bộ**, trong cùng transaction, mới có tác dụng ngăn effect trùng.

### Khác biệt giữa unique violation và timeout/deadlock

Khi hai transaction cạnh tranh, ngoài duplicate còn có thể xảy ra lock timeout, deadlock hoặc lỗi connection. Không được bắt mọi `DataAccessException` rồi coi như “đã xử lý rồi”. Một transient failure cần retry theo chính sách; unique violation của **đúng marker key** có thể được xem là duplicate đã xử lý.

Đặc biệt, một transaction có thể thất bại **trước commit** sau khi đã insert marker nhưng chưa tạo outbox. Nếu transaction rollback, marker không tồn tại bền vững và retry cần được phép chạy lại.

## 10. Chống mất event: transactional outbox trong business transaction

Nếu yêu cầu nghiệp vụ là **không được mất thông báo khi payment đã commit**, giải pháp mạnh hơn là ghi outbox **cùng transaction với thay đổi payment**, thay vì chỉ cố gắng ghi outbox từ callback hậu commit.

```text
Payment service
  BEGIN TRANSACTION
       |
       +--> UPDATE/INSERT payment business state
       |
       +--> INSERT event_outbox(eventId, paymentId, payload)
       |
  COMMIT -- cả business state và outbox cùng bền vững
       |
       v
Outbox worker (có thể chạy sau restart)
  claim pending row
  publish/execute action with retry
  mark delivered/complete
```

Mẫu service khái niệm:

```java
@Transactional
public void capturePayment(PaymentCommand command) {
    Payment payment = saveCapturedPayment(command);
    outboxRepository.insert(
            new OutboxEntry(
                    payment.eventId(),
                    "PaymentCaptured",
                    payment.paymentId()));
    // Có thể phát local event để đánh thức worker,
    // nhưng worker cũng phải poll outbox để không mất việc.
}
```

Đây **không phải mã độc lập**; cần định nghĩa `PaymentCommand`, `Payment`, repository, transaction manager và `OutboxEntry`. Điểm cốt lõi: thay đổi nghiệp vụ và outbox record **phải được commit cùng nhau**.

### Phân biệt hai outbox

- `Event outbox` do business service ghi cùng transaction gốc: bảo đảm có bản ghi cần giao sau business commit.
- `Notification outbox` do một consumer ghi sau khi đã nhận event: bảo đảm một công việc gửi email nội bộ được tạo nếu consumer đã xử lý.

Hai bảng có thể cùng tồn tại trong kiến trúc nhiều chặng. Một bảng không tự giải quyết độ tin cậy của chặng trước. Đừng gọi một listener `AFTER_COMMIT` ghi notification_outbox là “transactional outbox toàn tuyến” nếu event nguồn chưa được lưu bền vững.

### Worker giao ra ngoài phải tự idempotent

Khi worker gọi một API gửi email, vẫn có hai cửa sổ:

1. **Gửi thành công, crash trước khi ghi DONE:** retry có thể gửi lại.
2. **Ghi DONE trước khi gửi, crash:** email có thể **không bao giờ được gửi**.

Không có transaction ACID thông thường nào bao trùm cùng lúc database nội bộ và một HTTP/email API bên ngoài. Cần chiến lược như **idempotency key phía provider**, trạng thái job, retry, backoff, reconciliation, hoặc chấp nhận at-least-once với tác dụng phụ không gây hại.

Trong một hệ thống thanh toán, khóa gửi có thể là một **operation ID ổn định** gắn với payment/event + loại effect. Không dùng UUID ngẫu nhiên mới mỗi retry nếu muốn phía provider nhận ra cùng tác vụ.

## 11. Phân tích các “cửa sổ crash” theo từng thời điểm

| Thời điểm crash | Điều còn lại trong DB | Hệ quả | Phương án |
| --- | --- | --- | --- |
| Trước business commit | Transaction nghiệp vụ rollback | Không có payment hoàn tất | Retry theo transaction/request key |
| Sau business commit, trước callback `AFTER_COMMIT` | Payment đã commit; callback chưa có marker/outbox | **Có thể mất event follow-up** | Ghi event outbox cùng business transaction |
| Trong transaction marker + notification outbox | Transaction mới rollback | Không có marker/effect commit dở dang | Retry toàn transaction |
| Sau marker + outbox commit, trước gửi email | Outbox tồn tại, marker tồn tại | Có thể tiếp tục bằng worker | Poll/retry pending row |
| Sau email thành công, trước ack/DONE | Email có thể đã gửi nhưng trạng thái nội bộ chưa cập nhật | Retry có thể gửi trùng | Provider idempotency key/reconcile |
| Khi hai worker claim cùng event | Có thể tranh chấp unique key/lock | Một worker xử lý, worker kia duplicate/retry | DB constraint + claim transaction |

**Idempotency là kiểm soát “đừng thực hiện effect hai lần”; durability là kiểm soát “đừng làm mất việc đã cần thực hiện”.** Cả hai cần thiết trong quy trình có hậu quả tài chính hoặc dữ liệu quan trọng.

## 12. Mô hình trạng thái processed marker

Một marker đơn giản chỉ biểu diễn **đã xử lý xong** khi được commit cùng hiệu ứng nội bộ. Với công việc dài, đặc biệt external I/O, cần tách state rõ hơn:

```text
PENDING -> CLAIMED/IN_PROGRESS -> SUCCEEDED
                      |
                      +--> FAILED_RETRYABLE -> PENDING
                      |
                      +--> FAILED_TERMINAL / DEAD_LETTER
```

Những trạng thái này đòi hỏi thiết kế lease/timeout, `attempt_count`, `next_attempt_at` và phân biệt lỗi tạm thời với lỗi vĩnh viễn. Không lưu một marker “DONE” chỉ vì handler đã nhận được event.

Một ví dụ bảng outbox có thể gồm:

```sql
CREATE TABLE event_outbox (
    event_id          VARCHAR(80) PRIMARY KEY,
    event_type        VARCHAR(120) NOT NULL,
    payload_json      CLOB NOT NULL,
    status            VARCHAR(30) NOT NULL,
    attempt_count     INTEGER NOT NULL,
    next_attempt_at   TIMESTAMP,
    created_at        TIMESTAMP NOT NULL
);
```

Schema này là ví dụ độc lập về thiết kế **event outbox**, không phải bảng mà ứng dụng mục 8 sử dụng. Production nên có index phù hợp cho worker polling, khóa/lease đúng database, retention và cơ chế phân phối có kiểm soát.

## 13. Idempotency và các loại listener Spring

### @EventListener đồng bộ

- Thường chạy trên thread publish theo multicaster mặc định.
- Nếu publisher đang trong transaction, listener có thể tham gia transaction.
- Exception có thể lan lên publisher và ảnh hưởng commit/rollback tùy đường gọi.
- Nếu gọi API ngoài trực tiếp, rollback DB không rollback API; cần tách ranh giới.

### @Async @EventListener

```java
@Async("eventExecutor")
@EventListener
public void onCaptured(PaymentCaptured event) {
    // Worker thread: không mặc định mang transaction nguồn.
}
```

Đây là snippet tích hợp, cần `@EnableAsync`, bean executor và import phù hợp. Với `@Async`:

- Một lần publish có thể gửi task vào queue và trả về trước khi task chạy xong.
- Lỗi `@Async void` thường đi qua `AsyncUncaughtExceptionHandler`, không tự về caller.
- Nếu xử lý cần transaction, worker mở transaction riêng.
- Không truyền entity mutable, persistence context hoặc JDBC connection từ publisher làm payload.
- Trạng thái MDC/security/transaction không mặc định truyền giữa thread; `TaskDecorator` cho logging context không thay thế transaction.
- Duplicate có thể xuất hiện do upstream redelivery, nhiều publish hoặc retry.
- **Unique constraint ở database dùng chung** vẫn là bảo vệ quan trọng giữa các worker.

### @TransactionalEventListener(AFTER_COMMIT)

- Chỉ callback khi transaction nguồn đã commit, trừ các cấu hình `fallbackExecution` khác.
- Không tự dedupe những lần publish trùng.
- Khi cần write trong callback, dùng transaction mới phù hợp.
- Có cửa sổ crash sau business commit trước callback.
- Nếu yêu cầu chắc chắn không mất event, ghi event outbox trong transaction gốc.

### @Order và condition

`@Order` điều khiển thứ tự tương đối của listener trong điều kiện áp dụng; nó **không giảm callback count** và không ngăn duplicate khi retry. `@EventListener(condition = "...")` lọc theo thuộc tính event/SpEL, nhưng **không có bộ nhớ eventId đã xử lý**; đó không phải cơ chế idempotency bền vững.

### Spring Application Events và broker

Spring `publishEvent(Object)` là cơ chế **in-process**. Kafka, RabbitMQ hoặc outbox worker có thể đưa message vào một Spring listener qua `publishEvent(...)`, nhưng Spring không tự cung cấp ack/offset/replay xuyên process. **Nguồn duplicate và at-least-once** ở ranh giới broker cần được phân tích riêng.

## 14. Sai lầm khi bắt lỗi duplicate

Bảng marker thường có nhiều constraint. Nếu listener bắt mọi `DuplicateKeyException` phát sinh từ **toàn transaction**, có thể lầm lỗi duplicate của bảng nghiệp vụ/outbox thành “event đã xử lý”. Điều này nguy hiểm vì outbox có thể đang ở trạng thái không nhất quán.

Cách an toàn hơn:

1. Chỉ **dịch** duplicate exception ngay quanh `INSERT processed_events` của đúng consumer key.
2. Để transaction rollback khi marker đã tồn tại.
3. Chỉ **bắt tín hiệu duplicate có chủ đích** ở ngoài transaction.
4. Để những lỗi ở các SQL statement khác nổi lên như lỗi cần xử lý.
5. Có test riêng khi insert outbox thất bại để xác nhận marker rollback và không bị đánh dấu thành duplicate.

**Không dựa vào text của exception message** vì khác DB, driver và locale. Ưu tiên kiểu exception/SQLState/tên constraint được quy ước và test trên database đích.

Trên một số database, `INSERT ... ON CONFLICT DO NOTHING` hoặc `INSERT IGNORE` có thể hữu ích nhưng có ngữ nghĩa riêng và không portable. Nếu dùng, phải kiểm tra **affected rows** (0 hay 1) và chắc chắn chỉ bỏ qua unique key của marker, không che lỗi dữ liệu khác. Ví dụ mục 8 dùng insert thông thường để trình bày cơ chế rõ ràng trên H2.

## 15. Khi sự kiện có thứ tự hoặc phiên bản aggregate

Idempotency và ordering là hai bài toán khác nhau:

```text
OrderUpdated(eventId=evt-9, orderId=ORD-42, version=9)
OrderUpdated(eventId=evt-8, orderId=ORD-42, version=8)
```

Cả hai có eventId khác nhau nên marker `(consumer,eventId)` **không coi cái nào là duplicate**. Nhưng nếu consumer cập nhật read model theo phiên bản, xử lý `version=8` **sau** version 9 có thể làm dữ liệu lùi về trạng thái cũ.

Giải pháp là bổ sung điều kiện monotonic version:

```sql
UPDATE order_projection
SET status = ?, aggregate_version = ?
WHERE order_id = ?
  AND aggregate_version < ?;
```

Đây là snippet SQL minh họa, cần bảng có các cột tương ứng và xét trường hợp row chưa tồn tại. Một `UPDATE` có affected rows 0 có thể mang nghĩa “version đã cũ”, không đồng nghĩa với duplicate eventId. Với những chuỗi cập nhật không cho phép bỏ phiên bản, có thể cần buffer/ordering hoặc replay theo sequence.

**Không dùng correlationId làm version**. Một workflow có thể bao gồm nhiều event hợp lệ cùng correlation.

## 16. Kiểm thử idempotency đủ sâu

Một test tốt cần xác minh **kết quả nghiệp vụ**, không chỉ count method.

### 16.1. Test cùng event gửi hai lần

Input:

```text
PaymentCaptured(evt-100, PAY-42, flow-7)
PaymentCaptured(evt-100, PAY-42, flow-7)
```

Kỳ vọng:

- Listener có thể nhận **2 callback**.
- Bảng marker của consumer chỉ có **1 row**.
- Bảng notification outbox chỉ có **1 row**.
- Không có hai email/credit/transfer từ cùng một effect key.

Chương trình mục 8 mô phỏng thêm một lần replay, cho kết quả `attempts=3`, `scheduled=1`, `duplicates=2`.

### 16.2. Test hai event hợp lệ khác nhau

Hai event với `eventId` khác nhau và `paymentId` khác nhau phải đều tạo marker/effect riêng khi hợp đồng cho phép. Một bài test chỉ thử duplicate mà không thử event hợp lệ thứ hai có thể che lỗi “dedupe quá rộng”.

### 16.3. Test rollback effect nội bộ

Cố tình làm insert outbox thất bại **sau khi insert marker**; transaction mới phải rollback cả marker. Sau khi sửa lỗi giả lập và retry, handler phải thành công. Nếu marker vẫn tồn tại sau lỗi, thiết kế transaction chưa nguyên tử.

### 16.4. Test rollback transaction nguồn

Publish event trong transaction nguồn rồi rollback. Với `@TransactionalEventListener(AFTER_COMMIT)`, listener **không** được tạo marker/outbox cho event đó. Chương trình mục 8 đã có nhánh này.

### 16.5. Test publish ngoài transaction

Với `fallbackExecution=false`, listener transaction-bound không được gọi nếu publish không có transaction. Test phải xác nhận chính sách này phù hợp; nếu cần xử lý cả sự kiện ngoài transaction, thiết kế đường xử lý riêng hoặc chọn cấu hình có chủ đích.

### 16.6. Test cạnh tranh giữa hai worker

Dùng hai transaction/connection riêng, đồng bộ thời điểm cùng nộp marker bằng barrier/latch, không trông đợi `Thread.sleep` cố định. Với DB thật và unique constraint, cuối cùng **chỉ một marker và một effect** được commit. Worker thua phải được xử lý như duplicate hoặc lỗi cạnh tranh cần retry theo trạng thái thực tế, không đơn giản nuốt mọi exception.

### 16.7. Test crash windows

Cần integration/system test ngoài JVM của unit test:

- Kill process sau business commit nhưng trước callback hậu commit: **mô hình chỉ AFTER_COMMIT có thể mất follow-up**.
- Kill worker sau gửi message ra ngoài nhưng trước khi ack: broker/outbox có thể redeliver, consumer phải không tạo effect trùng.
- Kill worker sau outbox commit nhưng trước gửi: công việc phải được worker mới nhận lại.
- Đặt lỗi tạm thời ở database: marker không được đánh dấu thành success nếu effect chưa commit.
- Kiểm tra idempotency key được giữ nguyên qua retry, restart và nhiều replica.

### 16.8. Test using @RecordApplicationEvents

`@RecordApplicationEvents` trong Spring TestContext hữu ích để assert **event được publish** và payload đúng, nhưng nó **không tự chứng minh handler đã idempotent**. Cần kiểm tra bảng marker, outbox, effect sau khi transaction commit. Một event được record hai lần có thể vẫn tạo đúng **một** tác dụng phụ — đó chính là hành vi idempotent cần chứng minh.

## 17. Quan sát vận hành: đếm attempts, duplicate, success và failure

Log/metric nên trả lời:

```text
eventType
eventId
consumerName
correlationId
causationId (nếu có)
aggregateId / paymentId
deliveryAttempt
handlerInvocationId
processingStatus
effectKey
instanceId
```

Ví dụ hai lần callback cùng occurrence:

```text
type=PaymentCaptured id=evt-100 consumer=receipt-scheduler
attempt=1 status=SCHEDULED effectKey=receipt:PAY-42

type=PaymentCaptured id=evt-100 consumer=receipt-scheduler
attempt=2 status=DUPLICATE_SKIPPED effectKey=receipt:PAY-42
```

Không log toàn bộ thông tin khách hàng/thẻ thanh toán chỉ để debug. Phân biệt `DUPLICATE_SKIPPED` với `FAILED_RETRYABLE`; nếu mọi exception đều bị phân loại là duplicate, các vấn đề hạ tầng nghiêm trọng có thể bị che giấu.

Metric hữu ích:

- `listener_attempts_total`: số callback vào handler.
- `listener_succeeded_total`: số effect nội bộ commit thành công.
- `listener_duplicates_skipped_total`: số callback bị chặn bởi marker.
- `listener_failed_total`: lỗi khác duplicate.
- `outbox_pending_count` và `outbox_oldest_age`: công việc tồn đọng.
- `retry_count`, `dead_letter_count`, `idempotency_conflict_count` theo consumer.

Nếu duplicate tăng đột biến, cần điều tra nguyên nhân upstream: HTTP retries, redelivery, timeout, nhiều publisher hay consumer xử lý quá chậm. Idempotency giúp hệ thống an toàn hơn nhưng **không phải lý do bỏ qua gốc vấn đề**.

## 18. Những lỗi thường gặp

1. **Cho rằng Spring tự dedupe eventId.** `publishEvent` không có hợp đồng đó.
2. **Nhầm idempotency với listener gọi đúng một lần.** Callback có thể nhiều, effect vẫn một.
3. **Dùng `HashSet`/`ConcurrentHashMap` trong RAM làm bảo đảm duy nhất.** Không chịu được restart hoặc nhiều replica.
4. **Dùng `correlationId` làm unique key.** Chặn các event hợp lệ cùng workflow.
5. **Đổi `eventId` khi retry cùng occurrence.** Marker không nhận ra duplicate.
6. **Dùng `orderId` làm khóa quá rộng.** Một đơn có thể có nhiều sự kiện hợp lệ.
7. **Chỉ `SELECT exists` trước `INSERT` mà không có unique constraint.** Hai worker có thể vượt qua cùng lúc.
8. **Ghi marker rồi thực hiện effect ở transaction khác mà không có thiết kế failure.** Có thể bỏ sót effect hoặc tạo trùng.
9. **Gửi email/HTTP rồi đánh dấu marker, giả định DB rollback sẽ thu hồi API.** Không có ACID xuyên hệ thống ngoài.
10. **Đánh dấu processed trước khi side effect ngoài thực sự có thể tiếp tục.** Retry có thể bị khóa nhầm.
11. **Bắt mọi exception rồi xem là duplicate.** Nuốt lỗi DB/outbox khiến công việc mất.
12. **Bắt lỗi unique trong transaction rồi tiếp tục chạy SQL trên transaction lỗi.** Cần rollback đúng.
13. **Dùng `@TransactionalEventListener(AFTER_COMMIT)` và tưởng nó chống duplicate.** Nó chỉ ràng buộc thời điểm.
14. **Ghi DB hậu commit mà không mở transaction mới.** Dễ dính resource cũ, không có commit tiếp.
15. **Cho rằng listener hậu commit đủ bảo đảm không mất event.** Vẫn có crash window sau business commit.
16. **Chỉ dùng outbox ở callback hậu commit nhưng không có outbox trong business transaction.** Chặng nguồn còn dễ mất.
17. **Dùng một marker toàn cục cho mọi consumer.** Consumer thứ hai bị chặn không đúng.
18. **Không kiểm tra business uniqueness cho hai eventId khác nhau nhưng cùng effect.** Delivery dedupe không bảo vệ mọi bất biến.
19. **Coi `@Async` giúp tránh trùng.** Async chỉ đổi thread/executor, có thể làm race rõ hơn.
20. **Không xét ordering khi event khác version đến đảo thứ tự.** Idempotency không phải version control.
21. **Ghi “SENT” khi mới đưa vào outbox.** Outbox row là yêu cầu, chưa chứng minh provider đã gửi.
22. **Không test crash/restart.** Unit test đồng bộ không phát hiện mất event giữa các transaction.
23. **Không có số liệu duplicate và retry.** Hệ thống có thể chống trùng đúng nhưng nguồn upstream đang phát quá nhiều lần.
24. **Tuyên bố exactly-once end-to-end khi chỉ có unique marker.** Chưa chứng minh broker/HTTP/provider và toàn bộ failure windows.

## 19. Checklist thiết kế listener idempotent

- [ ] Đã xác định **event occurrence** và giữ `eventId` ổn định qua delivery/retry.
- [ ] Đã xác định **consumer identity** ổn định, độc lập giữa các handler hợp lệ.
- [ ] Khóa dedupe phản ánh đúng effect: `(consumerName,eventId)` và business uniqueness khi cần.
- [ ] Có unique constraint ở **database dùng chung**, không chỉ in-memory lock.
- [ ] Marker được claim trước effect nội bộ trong cùng transaction.
- [ ] Khi effect nội bộ lỗi, marker cũng rollback; retry vẫn có thể thực hiện.
- [ ] Chỉ bỏ qua unique violation của **đúng marker key**, không nuốt lỗi ngoài ý muốn.
- [ ] Phân biệt `SCHEDULED` trong outbox với `SENT`/`DELIVERED` thực sự.
- [ ] Nếu listener hậu commit ghi DB, có transaction mới bằng `REQUIRES_NEW`/`TransactionTemplate`.
- [ ] Đã xác định chính sách publish ngoài transaction (`fallbackExecution`).
- [ ] Nếu business commit không được mất event, có event outbox trong business transaction.
- [ ] Worker outbox có retry, backoff, claim/lease, metric và idempotency phía downstream.
- [ ] Không nhầm idempotency với ordering, delivery guarantees hay transaction boundary.
- [ ] Có test duplicate tuần tự và đồng thời, rollback, outbox failure và crash/restart.
- [ ] Log/metric tách attempts, skipped duplicates, succeeded và failed theo consumer.
- [ ] Không đưa dữ liệu nhạy cảm vào log hoặc idempotency key lộ ra ngoài không cần thiết.

**Ghi nhớ:** listener idempotent là listener có thể **được nhận/gọi lại** nhưng không làm **tác dụng phụ cần bảo vệ** bị nhân đôi. Hãy dùng **khóa ổn định, unique constraint và transaction nguyên tử** cho marker + effect nội bộ. Khi cần dữ liệu đáng tin sau commit, thiết kế thêm **transactional outbox ở business transaction** và cơ chế retry/downstream idempotency. Spring Application Events phân phối event; độ tin cậy end-to-end vẫn là trách nhiệm kiến trúc của hệ thống.

## Tài liệu chính thức

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — TransactionSynchronization Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework — TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)

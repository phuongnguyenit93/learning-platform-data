# Duplicate event trong xử lý thực tế với Spring Application Events

## 1. Vấn đề: một sự thật có thể được xử lý nhiều lần

Trong hệ thống hướng sự kiện, **một sự thật nghiệp vụ xảy ra một lần không có nghĩa mã xử lý sự kiện được gọi đúng một lần**. Với một sự kiện như `OrderPaid`, người phát có thể gửi lại sau timeout, một message broker có thể giao lại vì chưa nhận acknowledgement, outbox relay có thể restart sau khi gửi nhưng trước khi ghi trạng thái, hoặc một bug có thể tạo thêm event nói lại cùng một kết quả.

Ví dụ:

```text
10:00:00  Payment được xác nhận -> OrderPaid(eventId=E-101, orderId=O-42)
10:00:01  Consumer nhận E-101 -> tạo lệnh fulfillment cho O-42
10:00:02  Consumer hoàn tất fulfillment nhưng ACK thất bại
10:00:05  Consumer nhận lại E-101
10:00:06  Nếu không chống trùng: tạo fulfillment lần thứ hai
```

Lặp lại một event không phải lúc nào cũng gây lỗi. Handler chỉ gán `status=PAID` vào record với đúng giá trị có thể tự nhiên idempotent. Nhưng handler làm `balance = balance - amount`, `sendEmail()`, `createShipment()` hoặc `issueRefund()` thường tạo thêm tác dụng nếu gọi lại.

**Mục tiêu của độ tin cậy:** chấp nhận rằng delivery có thể lặp, xác định *tác dụng nghiệp vụ* nào cần xảy ra tối đa một lần, và làm cho consumer có thể thử lại an toàn. Kỹ thuật quan trọng nhất là **idempotency**: thực hiện lại cùng một yêu cầu/sự kiện không làm thay đổi kết quả nghiệp vụ thêm lần nữa.

Trong Spring, cần phân biệt:

- `ApplicationEventPublisher.publishEvent(...)` của **Spring Framework** là cơ chế giao sự kiện trong tiến trình/context; mặc định listener đồng bộ, không tự cung cấp persistent queue, retry hay exactly-once.
- Khi ứng dụng có broker, transactional outbox, Spring Modulith Event Publication Registry hoặc logic retry bổ sung, **cùng một occurrence có thể được xử lý lại**.
- Khi code publisher gọi `publishEvent(...)` hai lần, listener được gọi hai lần ngay cả khi không có broker. Điều này là do có hai lần publish, không phải lỗi phát trùng tự động của Spring.

Đừng cố loại bỏ mọi duplicate ở hạ tầng rồi giả định phần nghiệp vụ đã an toàn. **Tính idempotent phải được xác định ở consumer và ranh giới side effect thực tế.**

## 2. Hai loại trùng lặp thường bị nhầm

### 2.1. Trùng một event occurrence (redelivery/replay)

Hai delivery có cùng `eventId`:

```json
{"eventId":"e-101","type":"OrderPaid","orderId":"O-42"}
{"eventId":"e-101","type":"OrderPaid","orderId":"O-42"}
```

Trong contract đúng, `eventId` định danh **một occurrence của fact**. Khi broker giao lại chính fact đó, producer/relay cần **giữ nguyên eventId**. Consumer có thể lưu rằng nó đã xử lý ID này.

Nếu mỗi retry lại tạo UUID mới, consumer chỉ dựa vào eventId sẽ không nhận ra đó là cùng fact.

### 2.2. Trùng tác dụng nghiệp vụ dù eventId khác

Ví dụ:

```json
{"eventId":"e-101","type":"OrderPaid","orderId":"O-42"}
{"eventId":"e-202","type":"OrderPaid","orderId":"O-42"}
```

Có hai event IDs khác nhau nhưng cùng nói rằng đơn `O-42` đã được thanh toán. Điều này có thể là bug của publisher, một lệnh nghiệp vụ được chạy lại, hoặc hai sự thật hợp lệ bị mô hình hóa thiếu chính xác.

Nếu tác dụng là **tạo một fulfillment duy nhất cho mỗi đơn đã trả tiền**, khóa chống trùng theo `eventId` **không đủ**. Cần thêm ràng buộc nghiệp vụ, chẳng hạn `UNIQUE(order_id)` trên bảng fulfillment hoặc khóa `FULFILL:<orderId>`.

**Nhưng không được bỏ mọi event mới chỉ vì cùng orderId.** Một đơn có thể có nhiều lần thanh toán từng phần, hoàn tiền, điều chỉnh hoặc hai gói fulfillment thực sự khác nhau. Phải định nghĩa chính xác “một lần” theo nghiệp vụ: `orderId`, `paymentId`, `shipmentId`, `invoiceId`, hoặc cặp `(aggregateId, operationType)`.

### 2.3. Trùng xử lý giữa các subscriber không phải lỗi

`OrderPaid` được xử lý bởi Audit, Fulfillment và Analytics là **ba subscriber độc lập**, không phải ba lần xử lý trùng của một subscriber.

Nếu lưu processed ID trong bảng chung, khóa phù hợp thường là:

```sql
PRIMARY KEY (subscriber_id, event_id)
```

Nếu chỉ dùng `event_id` làm khóa chung cho mọi consumer, subscriber Fulfillment xử lý trước có thể vô tình khiến subscriber Audit tưởng event đã được xử lý. Chống trùng phải có **phạm vi**.

## 3. Phân biệt duplicate message, duplicate fact và duplicate side effect

| Loại | Ví dụ | Có phải lỗi? | Kiểm soát chính |
| --- | --- | --- | --- |
| Duplicate delivery | Broker giao lại E-101 sau ACK timeout | Có thể là hoạt động bình thường của at-least-once | Processed event ID theo subscriber |
| Duplicate publish của cùng occurrence | Relay gửi lại cùng E-101 | Có thể xảy ra sau crash/retry | Giữ ID, consumer idempotent |
| Duplicate business event | E-101 và E-202 đều nói cùng đơn đã Paid | Phải đối chiếu semantics | Business invariant/unique effect key |
| Nhiều subscriber hợp lệ | Audit và Fulfillment cùng nhận E-101 | **Không** | Trạng thái processed riêng từng subscriber |
| Repeated legitimate operation | Hai lần capture tiền thật sự ở hai payment IDs | **Có thể hợp lệ** | Không loại nhầm dựa chỉ vào orderId |
| Duplicate side effect | Cùng đơn tạo hai shipment ngoài ý muốn | Thường là lỗi nghiệp vụ | Transaction + UNIQUE + external idempotency |
| Replayed historical event | Rebuild read model từ event log | Có thể là hoạt động mong muốn | Replay mode, versioning, idempotency rõ |

Trong tài liệu và metrics, nên ghi rõ đơn vị đếm: *delivery attempts*, *event occurrences*, *consumer executions* hay *business effects*. Một dashboard chỉ ghi “duplicate count” mà không định nghĩa sẽ rất khó dùng khi sự cố.

## 4. Duplicate phát sinh ở đâu trong thực tế?

### 4.1. Producer retry sau timeout

Producer gửi một message, broker đã nhận nhưng kết nối bị ngắt trước khi producer thấy ACK. Producer retry. Nếu retry dùng cùng message/event ID, downstream có thể dedupe. Nếu retry tạo một fact mới bằng UUID mới, downstream cần kiểm tra thêm business key.

### 4.2. Consumer crash sau side effect, trước ACK

```text
Broker -> Consumer -> DB commit thành công
                      |
                      +-- JVM crash trước khi ACK
Broker thấy chưa ACK -> giao lại cùng message
```

Không thể suy từ “đã xử lý” trong log rằng broker đã ghi nhận ACK. Consumer nên an toàn khi nhận lại.

### 4.3. Outbox relay crash đúng cửa sổ bất tiện

Transactional outbox giúp ghi business state và bản ghi cần publish **trong cùng transaction**, giảm nguy cơ mất event khi producer chết giữa DB commit và publish. Nhưng relay có thể đã gửi message ra broker rồi chết trước khi đánh dấu outbox row là đã gửi:

```text
DB transaction:  cập nhật order + lưu outbox E-101 -> COMMIT
Relay:           publish E-101 -> broker ACK
Relay:           CRASH trước khi mark sent
Relay restart:   thấy E-101 chưa marked sent -> publish E-101 lần nữa
```

**Outbox giải quyết cửa sổ mất message, không loại trừ duplicate delivery.** Consumer vẫn cần idempotency.

### 4.4. Event registry và resubmission

Spring Modulith có **Event Publication Registry** để lưu việc publish đến transactional listeners và đánh dấu completion. Nếu listener thất bại hoặc process ngừng ở giai đoạn nhạy cảm, publication có thể được resubmit theo cơ chế và cấu hình của phiên bản đang dùng. Một listener có thể đã làm xong side effect rồi crash trước khi registry đánh dấu completed.

Vì vậy, registry **không thay thế idempotency** của handler. Nó cung cấp theo dõi/recovery cho publication, nhưng không thể tự biến mọi external side effect thành exactly-once.

### 4.5. Bug đăng ký listener, parent-child context, manual publish

Trong một ứng dụng Spring không dùng broker, cần kiểm tra:

- Cùng event được gọi `publishEvent(...)` ở hai nơi.
- Một publisher bị retry ở service layer nhưng không dùng business idempotency key.
- Có nhiều listener class/bean vô tình cùng thực hiện một tác dụng.
- Có context hierarchy; event từ child có thể lan lên parent và được nhận ở các scope khác nhau.
- Một listener publish nested event, tạo luồng callback bất ngờ.
- Một tác vụ scheduled replay dữ liệu nghiệp vụ mà không chặn đã hoàn thành.

Đừng kết luận “Spring ApplicationEventPublisher tự retry” chỉ vì một listener log hai lần. Hãy tìm **publisher call sites, message IDs, context IDs, listener bean identity và retry boundaries** trước.

## 5. Idempotency ở mức độ nào?

Có hai tầng quan trọng và thường phải dùng cùng nhau.

### 5.1. Dedupe theo event ID — xử lý lại cùng message

Ví dụ bảng:

```sql
CREATE TABLE processed_messages (
    subscriber_id VARCHAR(80) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (subscriber_id, event_id)
);
```

Consumer `fulfillment-v1` nhận E-101:

1. Bắt đầu transaction.
2. `INSERT` `(subscriber_id="fulfillment-v1", event_id="E-101")`.
3. Nếu uniqueness conflict: đây là event occurrence đã hoàn tất theo contract này; rollback/skip.
4. Nếu insert được: thực hiện thay đổi nghiệp vụ **cùng transaction**.
5. Commit cả processed marker và effect.

Nếu rollback trước commit, processed marker cũng rollback; delivery sau có thể thử lại. Nếu commit thành công rồi ACK thất bại, delivery sau thấy processed marker và bỏ qua side effect. Đây là idempotent consumer pattern.

**Điều kiện quan trọng:** marker và business effect phải cùng một giao dịch hoặc có cơ chế phối hợp tương đương. Ghi marker ở Redis rồi thực hiện ghi tiền ở DB khác, không có atomicity, sẽ mở cửa sổ lỗi mới.

### 5.2. Business idempotency — một tác dụng tối đa một lần

Ví dụ một đơn đã trả tiền chỉ được tạo một fulfillment:

```sql
CREATE TABLE fulfillment_effects (
    effect_key     VARCHAR(120) PRIMARY KEY,
    first_event_id VARCHAR(80) NOT NULL
);
```

Với key `FULFILL:O-42`, cả E-101 và E-202 đều đụng cùng unique key. Đây là một lớp bảo vệ **theo tác dụng**, khác việc lưu delivered event IDs.

Nên có cả hai khi cần: processed messages tránh xử lý lại cùng occurrence, còn business key bảo vệ invariant ngay cả khi publisher tạo occurrence mới không hợp lệ.

### 5.3. Tính đúng của khóa quan trọng hơn kỹ thuật lưu

| Side effect | Khóa idempotency thường hợp lý | Rủi ro khi chọn sai |
| --- | --- | --- |
| Ghi một audit row cho mỗi event occurrence | `(subscriberId,eventId)` | Bỏ thiếu audit khi gộp nhiều event khác nhau |
| Tạo một fulfillment trên một order được trả đủ | `(orderId,fulfillmentType)` | Fulfillment trùng hoặc chặn nhầm nhiều kiện hợp lệ |
| Gửi một thông báo cho mỗi fact đến mỗi kênh | `(eventId,notificationChannel)` | Gửi lặp, hoặc chặn email/SMS khác kênh |
| Thu một payment attempt | Stable `paymentAttemptId` / provider idempotency key | Charge hai lần nếu chỉ dựa trên eventId mới |
| Chuyển tiền ở ledger | Stable transaction reference có uniqueness | Double debit/credit khi replay |
| Phát một callback cho mỗi subscriber | `(subscriberId,eventId)` | Một subscriber khiến subscriber khác bỏ qua |
| Set projection thành một version cụ thể | `(aggregateId,version)`, quy tắc ordering | Mất cập nhật mới hoặc ghi đè bằng event cũ |

Không chọn khóa chỉ vì nó dễ lấy trong payload. Phải xác định **đơn vị nghiệp vụ được phép xảy ra đúng một lần** trước, rồi mới chọn field/unique constraint.

## 6. Những giải pháp chống trùng giả an toàn

### 6.1. Chỉ dùng Set trong bộ nhớ

```java
Set<UUID> seen = ConcurrentHashMap.newKeySet();

@EventListener
public void on(OrderPaid event) {
    if (!seen.add(event.eventId())) return;
    sendShipmentRequest(event.orderId());
}
```

Đoạn trên là **phản ví dụ** trong một bean có `OrderPaid` và `sendShipmentRequest` do ứng dụng định nghĩa. Nó có ba vấn đề:

1. JVM restart thì Set mất; nhiều instance có Set riêng.
2. Nếu `sendShipmentRequest` ném lỗi **sau khi Set.add thành công**, retry sẽ bị bỏ dù tác dụng chưa hoàn tất.
3. Nếu external request thành công nhưng listener lỗi trước khi ghi trạng thái, không thể biết có nên retry hay không chỉ từ Set.

`ConcurrentHashMap.newKeySet()` tránh lỗi dữ liệu đồng thời ở bản thân Set, **không bảo đảm atomicity giữa Set và side effect**.

### 6.2. SELECT rồi INSERT không có unique constraint

```java
if (!repository.existsByEventId(eventId)) {
    repository.saveProcessed(eventId);
    doBusinessEffect();
}
```

Hai worker có thể cùng thấy “chưa có” trước khi một worker ghi. Đây là race **check-then-act**. Cần một constraint ở nơi lưu dữ liệu hoặc một cơ chế concurrency control có bảo đảm tương ứng.

### 6.3. Đánh dấu processed trước khi side effect

```text
write processed=true -> COMMIT
call external API      -> timeout/failure
retry                  -> thấy processed=true -> SKIP
```

Hệ thống mất cơ hội xử lý effect. Marker chỉ nên biểu thị completion theo đúng contract, hoặc phải có trạng thái `PENDING/PROCESSING/COMPLETED` với recovery.

### 6.4. Làm side effect rồi ghi marker ở hai transaction khác nhau

```text
call external API      -> success
CRASH
write processed marker -> chưa kịp
retry                  -> call external API lần nữa
```

Với external API, không thể đưa mọi thứ vào một local DB transaction. Cần **idempotency key tại dịch vụ đích** hoặc reconciliation/compensation rõ ràng.

### 6.5. Bỏ qua DuplicateKeyException quá rộng

Không phải mọi `DuplicateKeyException` đều là “đã xử lý event này”. Nó có thể phát sinh từ:
- Invoice ID trùng do bug.
- Mã business không hợp lệ.
- Một bảng khác đang bị conflict.
- Ràng buộc được thêm về sau.

Hãy giới hạn try/catch quanh thao tác insert **idempotency/effect key cụ thể**, hoặc kiểm tra constraint name/nguồn lỗi khi backend hỗ trợ. Đừng swallow mọi `DataIntegrityViolationException` rồi trả “duplicate ignored”.

## 7. Spring ApplicationEventPublisher có bảo đảm exactly-once không?

**Không.** Spring Framework Application Events chủ yếu là cơ chế dispatch đến listeners trong application context. Nó không tự lưu publication bền vững, không tự ACK message broker, không tự retry toàn bộ side effect, và không tự giao exactly-once.

Mặc định `SimpleApplicationEventMulticaster` phân phối listeners đồng bộ trên calling thread. Nếu một listener ném exception mà không có handler suppress, publisher có thể nhận lỗi. Việc caller tự retry toàn bộ business operation sau exception có thể khiến event được publish lại. Nếu cấu hình executor/`@Async`, lỗi listener có thể xảy ra sau khi publisher đã trả về.

Các hệ thống messaging có thể cung cấp at-least-once, at-most-once, hay tính năng transaction/exactly-once trong **một phạm vi xác định**. Nhưng ngay cả khi broker bảo đảm đúng một lần trong phạm vi record/offset của nó, **ghi tiền trong DB, gửi email hoặc gọi API thứ ba vẫn cần thiết kế idempotency riêng**. Không nói “Kafka exactly once” rồi suy ra mọi thao tác bên ngoài Kafka chắc chắn chỉ chạy một lần.

Một mục tiêu thực tế là **effectively-once business effect**: handler có thể được gọi nhiều lần nhưng trạng thái nghiệp vụ cuối cùng giống như xử lý hợp lệ một lần.

## 8. Ví dụ Spring Framework 6.2 + JDBC + H2 chạy được

Ví dụ sau dùng:

- **Java 17+**.
- **Spring Framework 6.2.12**: `spring-context`, `spring-jdbc` và transaction support đi kèm.
- **H2 2.3.232**: cơ sở dữ liệu trong bộ nhớ để demo unique constraint và rollback/commit.
- **Maven**: compile và chạy class `demo.DuplicateEventDemo`.

Ví dụ cố ý publish **ba lần** cùng business fact:

1. E1 đầu tiên: cập nhật fulfillment một lần.
2. E1 lặp lại: **redelivery** của cùng occurrence, phải skip.
3. E2 khác eventId nhưng cùng order: **duplicate effect** trong domain của demo, phải skip.

Khác với dùng Set, marker và fulfillment count được cập nhật trong **một DB transaction** dưới constraint duy nhất. Listener sẽ phân biệt trường hợp eventId trùng với trường hợp eventId khác dựa trên bản ghi đầu tiên.

### 8.1. Cấu trúc

```text
duplicate-event-demo/
├── pom.xml
└── src/main/java/demo/DuplicateEventDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>duplicate-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.DuplicateEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/DuplicateEventDemo.java`:

```java
package demo;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public final class DuplicateEventDemo {

    public record OrderPaid(
            UUID eventId,
            String orderId,
            Instant occurredAt) {
        public OrderPaid {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(occurredAt, "occurredAt");
            if (orderId.isBlank()) {
                throw new IllegalArgumentException("blank orderId");
            }
        }
    }

    // KHÔNG final: Spring tạo transactional proxy cho service.
    public static class FulfillmentService {
        private final JdbcTemplate jdbc;

        public FulfillmentService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void fulfill(OrderPaid event) {
            String key = "FULFILL:" + event.orderId();

            // UNIQUE effect_key chặn cả cùng eventId lẫn eventId mới.
            jdbc.update(
                    "INSERT INTO fulfillment_effects "
                    + "(effect_key, first_event_id) VALUES (?, ?)",
                    key, event.eventId().toString());

            int changed = jdbc.update(
                    "UPDATE orders "
                    + "SET fulfillment_count = fulfillment_count + 1 "
                    + "WHERE order_id = ?",
                    event.orderId());

            if (changed != 1) {
                // Rollback cả bản ghi effect_key nếu order không tồn tại.
                throw new IllegalStateException("missing order");
            }
        }
    }

    public static final class FulfillmentListener {
        private final FulfillmentService fulfillmentService;
        private final JdbcTemplate jdbc;

        public FulfillmentListener(
                FulfillmentService fulfillmentService, JdbcTemplate jdbc) {
            this.fulfillmentService = fulfillmentService;
            this.jdbc = jdbc;
        }

        @EventListener
        public void on(OrderPaid event) {
            String key = "FULFILL:" + event.orderId();
            try {
                // Phải gọi qua Spring bean proxy để @Transactional có hiệu lực.
                fulfillmentService.fulfill(event);
                System.out.println("FULFILLED order=" + event.orderId());
            } catch (DuplicateKeyException duplicate) {
                // Chỉ ví dụ: lỗi duplicate có thể đến từ constraint khác.
                // Với code này, INSERT đầu tiên là thao tác có UNIQUE key.
                String firstEventId = jdbc.queryForObject(
                        "SELECT first_event_id "
                        + "FROM fulfillment_effects WHERE effect_key = ?",
                        String.class, key);

                if (event.eventId().toString().equals(firstEventId)) {
                    System.out.println(
                            "REDELIVERY_SKIPPED order=" + event.orderId());
                } else {
                    System.out.println(
                            "BUSINESS_DUPLICATE_SKIPPED order=" + event.orderId());
                }
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:dedupe;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        FulfillmentService fulfillmentService(JdbcTemplate jdbc) {
            return new FulfillmentService(jdbc);
        }

        @Bean
        FulfillmentListener fulfillmentListener(
                FulfillmentService service, JdbcTemplate jdbc) {
            return new FulfillmentListener(service, jdbc);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute(
                    "CREATE TABLE orders ("
                    + "order_id VARCHAR(40) PRIMARY KEY, "
                    + "fulfillment_count INT NOT NULL)");

            jdbc.execute(
                    "CREATE TABLE fulfillment_effects ("
                    + "effect_key VARCHAR(120) PRIMARY KEY, "
                    + "first_event_id VARCHAR(36) NOT NULL)");

            jdbc.update(
                    "INSERT INTO orders (order_id, fulfillment_count) "
                    + "VALUES (?, ?)",
                    "O-100", 0);

            UUID original =
                    UUID.fromString("00000000-0000-0000-0000-000000000001");
            UUID another =
                    UUID.fromString("00000000-0000-0000-0000-000000000002");
            Instant at = Instant.parse("2026-01-01T00:00:00Z");

            context.publishEvent(new OrderPaid(original, "O-100", at));
            context.publishEvent(new OrderPaid(original, "O-100", at));
            context.publishEvent(new OrderPaid(another, "O-100", at));

            Integer count = jdbc.queryForObject(
                    "SELECT fulfillment_count FROM orders "
                    + "WHERE order_id = ?",
                    Integer.class, "O-100");

            Integer effectRows = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM fulfillment_effects",
                    Integer.class);

            System.out.println("FULFILLMENT_COUNT=" + count);
            System.out.println("EFFECT_ROWS=" + effectRows);
        }
    }
}
```

Chạy từ thư mục `duplicate-event-demo`:

```bash
mvn -q compile exec:java
```

Các dòng do chương trình in **theo thứ tự** (không tính log của Spring/Maven):

```text
FULFILLED order=O-100
REDELIVERY_SKIPPED order=O-100
BUSINESS_DUPLICATE_SKIPPED order=O-100
FULFILLMENT_COUNT=1
EFFECT_ROWS=1
```

### 8.2. Vì sao ví dụ có thể chống duplicate?

1. `AnnotationConfigApplicationContext` tạo context, đăng ký `@EventListener` và hạ tầng `@Transactional`.
2. Lời gọi `publishEvent(OrderPaid)` dùng record Java thường; Spring Framework hỗ trợ POJO event payload. Các listener được gọi đồng bộ theo mặc định nên stdout có thứ tự xác định.
3. Lần đầu, `FulfillmentService.fulfill(...)` qua transactional proxy bắt đầu DB transaction; insert `FULFILL:O-100` và tăng `fulfillment_count` từ 0 lên 1 cùng một transaction.
4. Lần thứ hai với **cùng eventId** đụng primary key trên `fulfillment_effects.effect_key`. `DuplicateKeyException` đi ra khỏi transactional method và transaction bị rollback. Listener đọc `first_event_id` đã commit, in `REDELIVERY_SKIPPED`.
5. Lần thứ ba với **eventId khác** nhưng cùng order tiếp tục đụng effect key; listener in `BUSINESS_DUPLICATE_SKIPPED`.
6. Bảng orders vẫn có `fulfillment_count=1`; bảng effects có đúng một row. Không xảy ra lần tăng thứ hai.

### 8.3. Giới hạn của bản demo

- Bảng `orders` và `fulfillment_effects` đều thuộc **cùng một H2 database** nên local transaction bảo vệ cả hai.
- Không có HTTP, broker, thread pool, retry policy hay external shipment API; event được publish trực tiếp ba lần để tái hiện trùng lặp **có chủ ý**.
- Phần log phân loại “duplicate” ở listener là minh họa. Trong hệ thống thật cần bắt đúng constraint và kiểm tra contract về business key.
- H2 được tạo trong bộ nhớ; restart JVM thì dữ liệu mất. Thay bằng DB bền vững trong production.
- `FULFILL:<orderId>` chỉ đúng cho domain cho phép **một fulfillment của loại đó trên mỗi order**. Với nhiều kiện hàng, nhiều shipment hoặc partial fulfillment, key phải bao gồm phân biệt phù hợp.
- Nếu tác dụng là gọi carrier API bên ngoài, một DB transaction không thể đảm bảo carrier không tạo hai shipment khi network timeout. Cần một **external idempotency key** và reconciliation.
- Nếu hệ thống có nhiều replicas, unique constraint trong cùng authoritative database là cơ chế phối hợp tốt hơn Set trong từng JVM. Phải dùng đúng database/partition và đảm bảo uniqueness theo tenant scope nếu ID không duy nhất toàn hệ thống.

**Tại sao không bắt toàn bộ exception rồi coi là duplicate?** Vì những lỗi khác như mất kết nối DB, invalid SQL hoặc missing order phải được báo rõ, không được giả thành “đã xử lý”. Ví dụ chỉ bắt `DuplicateKeyException`, và trong hệ thống thật nên cô lập thao tác unique insert để biết constraint nào bị vi phạm.

## 9. Ranh giới commit: xử lý lỗi trước và sau khi ghi marker

Giả sử consumer xử lý `OrderPaid(E-101)`.

### 9.1. Lỗi trước khi transaction commit

```text
BEGIN
  INSERT processed_messages(subscriber, E-101)
  UPDATE projection
  -- lỗi, ROLLBACK
END
```

Cả marker và projection cùng rollback, nên lần giao lại sau có thể xử lý lại. Đây là thuộc tính quan trọng của thiết kế transactional idempotency.

### 9.2. Commit xong rồi worker chết

```text
BEGIN
  INSERT processed_messages(subscriber, E-101)
  UPDATE projection
COMMIT
CRASH trước khi ACK
```

Lần giao lại thấy primary key đã tồn tại và bỏ qua effect. **Không cần tránh redelivery; cần làm redelivery vô hại.**

### 9.3. Side effect ở hệ thống ngoài

```text
BEGIN local DB
  INSERT processed marker
COMMIT
HTTP POST /shipments -> service ngoài đã tạo shipment
CRASH trước khi lưu phản hồi
retry -> nguy cơ tạo shipment thứ hai
```

Giao dịch nội bộ không bảo vệ một side effect ở service khác. Hướng xử lý:

- Gửi ổn định một key, ví dụ `fulfillment:O-42`, dưới dạng idempotency key nếu API đích hỗ trợ.
- Đích phải lưu key và kết quả, trả lại kết quả cũ cho retry hợp lệ.
- Nếu API không hỗ trợ, thiết kế state machine + reconciliation (tra cứu shipment theo business reference) hoặc compensation. Không coi `HTTP 500/timeout` là bằng chứng đích chưa xử lý.
- Có outbox/queue bền vững cho yêu cầu side effect và deduplication ở consumer cuối.
- Tách trạng thái “request đã gửi” khỏi “business effect đã xác nhận”.

Đặc biệt với tiền, email, chuyển hàng hoặc gửi thông báo ra ngoài, phải xác định **đơn vị tác dụng** cần idempotent ở chính nơi tác dụng xảy ra.

## 10. TransactionalEventListener và duplicate

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` giúp listener chỉ chạy sau khi transaction gốc commit thành công:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPaid event) {
    fulfillOrder(event);
}
```

Đây là snippet minh họa trong một Spring bean có transaction manager và method `fulfillOrder` hợp lệ, không thuộc code chạy ở phần 8.

Nhưng cần nhớ:

- `AFTER_COMMIT` **không tự tạo persistent event queue**.
- Process chết sau commit nhưng trước hoặc trong callback vẫn có thể mất xử lý nếu không có registry/outbox.
- Khi callback được retry/resubmitted từ cơ chế khác, side effect vẫn có thể chạy nhiều lần.
- Callback sau commit muốn ghi DB như transaction mới có thể cần `REQUIRES_NEW` tại một service/proxy đúng cách.
- Transaction synchronization không đồng nghĩa với “exactly-once delivery”.
- Nếu sự kiện được phát khi không có transaction, transactional listener mặc định không chạy, trừ khi cấu hình `fallbackExecution=true`.

### Spring Modulith Event Publication Registry

Spring Modulith có thể lưu record publication cho transactional listeners và đánh dấu completion. Những publication chưa hoàn tất có thể được resubmit theo cấu hình/API. Hệ thống vận hành cần theo dõi pending/failed/resubmitted publications để sửa sự cố.

Ví dụ cửa sổ duplicate:

```text
Business transaction commits + publication record stored
  |
  v
Listener xử lý xong side effect
  |
  +-- CRASH trước khi registry đánh dấu COMPLETED
         |
         v
Resubmit incomplete publication
         |
         v
Listener được gọi lại -> idempotent effect phải SKIP
```

Tính năng và tên APIs thay đổi theo phiên bản Spring Modulith (đặc biệt ở các đời có trạng thái publication cụ thể). Hãy dùng tài liệu **đúng phiên bản dự án**; không trộn các APIs registry đời mới vào dự án chỉ có Spring Framework core.

## 11. Thiết kế consumer idempotent với nhiều workers

Ví dụ hai worker nhận cùng event E-101:

```text
Worker A: SELECT processed -> none
Worker B: SELECT processed -> none
Worker A: INSERT + process
Worker B: INSERT + process
```

Nếu chỉ dùng `SELECT` rồi lưu không có uniqueness, cả hai có thể cùng thực hiện side effect. Vì vậy:

1. Dùng `PRIMARY KEY/UNIQUE` trong authoritative store.
2. Tiến hành atomic insert/claim theo transaction hoặc một compare-and-set có semantics được kiểm chứng.
3. Không giữ distributed lock như cơ chế duy nhất để đạt exactly-once nếu side effect và lock state không có atomicity.
4. Đảm bảo database uniqueness đúng tenant/subscriber/business key.
5. Với khóa composite, xác định ranh giới partition: uniqueness trong một shard không chặn trùng trên shard khác nếu cùng entity bị định tuyến sai.

### Kiểm tra uniqueness quan trọng hơn kiểm tra trước

Mẫu “check rồi insert” có thể giúp hiển thị sớm thông báo lỗi, nhưng **constraint của database mới là lớp bảo vệ cuối** khi nhiều worker cùng tranh chấp. Một race có thể khiến code thử insert và nhận conflict; conflict chính là kết quả dự kiến của idempotency, không nên ghi thành SEV-1 cho mọi lần duplicate bình thường.

### Không giả định ordering toàn cục

Message E2 có thể đến trước E1 khi async, replay hoặc repartition. Nếu effect phải xử lý theo version của aggregate, cần quy tắc ordering/version:

```text
OrderPaid(version=5)    -> projection version 5
OrderCancelled(version=6)-> projection version 6
Old OrderPaid(version=5) arrives later
                         -> không ghi đè version 6
```

Bỏ duplicate theo eventId **không tự xử lý out-of-order**. Consumer có thể cần expected aggregate version, optimistic locking hoặc state machine cho phép bỏ event cũ và chờ event thiếu.

## 12. Event ID, correlation ID, causation ID và business key

| Trường | Công dụng | Có nên dùng để dedupe? |
| --- | --- | --- |
| `eventId` | Định danh occurrence cụ thể | **Có** cho redelivery của cùng occurrence |
| `subscriberId` | Phạm vi một consumer | **Có** khi kết hợp eventId |
| `businessKey` | Định danh tác dụng nghiệp vụ | **Có**, nếu invariant được xác định đúng |
| `orderId` | Aggregate identity | **Chưa chắc**; có thể nhiều event hợp lệ cho cùng order |
| `paymentId` | Payment attempt/transaction | Thường tốt để chống trùng thanh toán theo contract |
| `correlationId` | Gom các bước của workflow | **Không**; một workflow có nhiều event |
| `causationId` | Chỉ nguồn gây ra fact | Không thay eventId/business key |
| `traceId` | Gắn traces trong observability | **Không**; nhiều events cùng trace |
| `occurredAt` | Thời điểm xảy ra | Không đủ làm khóa; có thể trùng và sai lệch đồng hồ |

Đừng dùng `correlationId` làm dedupe ID. Một checkout request có thể tạo `OrderPlaced`, `PaymentCaptured`, `InventoryReserved` cùng một correlation, nhưng mỗi fact và mỗi side effect là riêng biệt.

### UUID mới khi retry có thể làm mất ý nghĩa duplicate

Nếu retry là **gửi lại cùng event**, nên giữ nguyên `eventId` ban đầu. Nếu retry thực sự tạo **fact mới** theo quyết định domain, cần event ID mới. Phải tách rõ hai loại retry này.

## 13. Bảo vệ khỏi duplicate ngay ở producer

Chống trùng consumer là cần thiết nhưng không biện minh cho việc producer phát sự thật sai nhiều lần.

Ở producer, một business command có thể cần:

- `idempotencyKey` cho HTTP request (do caller cung cấp theo contract, được validate).
- Duy trì result của command theo idempotency key trong database.
- Optimistic locking/version check để chống hai lần chuyển trạng thái như PAID -> PAID.
- Unique constraint trên payment attempt/transaction reference.
- Domain invariant từ chối việc “capture tiền lần thứ hai” nếu nó không hợp lệ.
- Outbox row cùng transaction với business state để publication bền vững.
- Stable eventId cho một fact đã được ghi.

Ví dụ ý tưởng:

```text
POST /payments/capture
Idempotency-Key: capture-P-900

First request:
  verify authorization
  capture payment once
  persist result and event ID E-101
  return captured

Retry with same key:
  return prior result
  do not capture again
  do not manufacture a new business fact
```

Đây là **contract ví dụ**, không phải HTTP header tự động do Spring cấp. Nếu client gửi cùng key nhưng payload hoàn toàn khác, nên phát hiện conflict theo API policy, không âm thầm dùng kết quả cũ cho một yêu cầu khác.

Dù producer idempotent, relay hoặc consumer vẫn có thể thấy duplicate delivery, nên các lớp chống trùng bổ sung không phải dư thừa.

## 14. Retention, replay và thay đổi schema

Một bảng `processed_messages` không thể tăng mãi mà không có chính sách. Nhưng xóa marker quá sớm có thể khiến replay một message cũ tạo lại side effect.

Trước khi đặt TTL, cần biết:

- Broker giữ message tối đa bao lâu?
- Hệ thống có manual replay nhiều tháng sau không?
- Outbox/registry có thể resubmit publication tồn tại bao lâu?
- Side effect có thể xảy ra lại hợp lệ trong khoảng thời gian nào?
- Có luật lưu audit/ledger cần bảo toàn lâu hơn không?
- Nếu business key đủ bền, có thể giữ unique effect key lâu hơn event-level marker?

Với những tác dụng không thể lặp, **business invariant bền vững** thường quan trọng hơn một cache eventId có TTL ngắn.

Nếu event schema evolve, consumer phải biết cách đọc historical payload và key idempotency. Đổi tên `paymentId` hay thay logic tạo key mà không migrate state có thể khiến replay lọt qua dedupe.

### Replay có chủ đích khác duplicate xử lý production

Đôi khi replay dùng để rebuild read model mới. Nếu listener mới có subscriber ID mới, việc nhận lại events lịch sử có thể là điều hợp lệ. Nhưng listener gửi email/charge tiền **không được** vô tình thực hiện side effect production trên replay environment.

Có thể tách read-model replay khỏi effectful consumer, hoặc sử dụng replay mode với chính sách chặn external side effects. Không dùng duy nhất một biến `isReplay` từ message không đáng tin để quyết định có bỏ qua authorization hay không.

## 15. Quan sát duplicate và failure window

Để debug, nên ghi nhận tối thiểu:

- `eventType`, `eventId` (hoặc hash/opaque ID phù hợp).
- `subscriberId` và `businessEffectKey` đã được validate.
- `tenantId`/scope cần thiết, không chứa PII thừa.
- Attempt number nếu transport có cung cấp; đừng giả làm lần xử lý toàn cục.
- Outcome: `APPLIED`, `DUPLICATE_SKIPPED`, `FAILED_RETRYABLE`, `FAILED_TERMINAL`.
- Latency/queue age theo các mốc đã định nghĩa.
- Exception cause khi lỗi không phải duplicate.
- Source: producer double publish, outbox resend, broker redelivery, registry resubmission hay manual replay nếu có bằng chứng.

Ví dụ log có cấu trúc:

```text
eventType=OrderPaid eventId=E-101 subscriber=fulfillment
effectKey=FULFILL:O-42 outcome=APPLIED

eventType=OrderPaid eventId=E-101 subscriber=fulfillment
effectKey=FULFILL:O-42 outcome=REDELIVERY_SKIPPED

eventType=OrderPaid eventId=E-202 subscriber=fulfillment
effectKey=FULFILL:O-42 outcome=BUSINESS_DUPLICATE_SKIPPED
```

**Cẩn thận với metrics:** không đưa raw `eventId/orderId/customerId` làm tag trên mọi counter/timer vì cardinality rất lớn. Nên dùng low-cardinality `eventType`, `subscriber`, `outcome`, `errorClass` (có allowlist). Đưa ID chi tiết vào log/traces được phân quyền thích hợp.

### Duplicate rate tăng là tín hiệu gì?

Tùy nguồn:

- Tăng broker redelivery: listener chậm, ACK timeout hoặc consumer crash.
- Tăng outbox resend: relay crash, không cập nhật trạng thái gửi, network lỗi.
- Tăng business duplicate ID mới: command idempotency yếu hoặc publisher bug.
- Tăng `BUSINESS_DUPLICATE_SKIPPED` sau deploy: định nghĩa key mới có thể quá rộng, đang chặn tác dụng hợp lệ.
- Duplicate biến mất nhưng side effect mất: có thể do marker ghi trước effect, `DiscardPolicy` hoặc swallow exception.

**Không tối ưu duplicate rate về 0 bằng cách bỏ log hoặc âm thầm discard task.** Mục tiêu là xử lý đúng và dễ chẩn đoán, không phải che triệu chứng.

## 16. Kiểm thử chống duplicate thực sự

Một bộ test cần chứng minh cả **được xử lý một lần** lẫn **có thể retry sau lỗi**.

| Tình huống | Kỳ vọng |
| --- | --- |
| E1 được phát lần đầu | Effect được tạo một lần |
| E1 phát lại đúng cùng ID | Không tăng effect count |
| E2 ID khác nhưng trùng business key | Không tạo effect thứ hai nếu invariant chỉ cho phép một |
| E2 ID khác, business key khác | Effect hợp lệ mới vẫn được tạo |
| DB lỗi sau insert marker trước commit | Rollback marker + effect, retry sau có thể thành công |
| Worker crash sau DB commit trước ACK | Redelivery nhận diện completion, không làm lại effect |
| Hai worker xử lý E1 đồng thời | Unique constraint chặn effect trùng |
| Publisher retry với idempotency key ổn định | Không phát business fact mới không hợp lệ |
| Same event cho hai subscriber | Mỗi subscriber xử lý phần của mình, không chặn chéo |
| Event out-of-order | Consumer dùng version/state machine phù hợp |
| External API timeout sau khi xử lý | Retry dùng stable idempotency key hoặc reconciliation |
| Process restart | DB marker còn nếu dùng persistent store |
| Manual replay | Consumer side effect không bị thực hiện lại sai |
| Tenant A/B có trùng ID cục bộ | Dedupe scope và DB routing phân biệt đúng tenant |

### 16.1. JUnit với ví dụ Spring/JDBC

Có thể đưa phần dispatch của demo vào test và assert:

```java
context.publishEvent(new OrderPaid(e1, "O-100", at));
context.publishEvent(new OrderPaid(e1, "O-100", at));
context.publishEvent(new OrderPaid(e2, "O-100", at));

assertEquals(1, jdbc.queryForObject(
        "SELECT fulfillment_count FROM orders WHERE order_id = ?",
        Integer.class, "O-100"));

assertEquals(1, jdbc.queryForObject(
        "SELECT COUNT(*) FROM fulfillment_effects",
        Integer.class));
```

Đây là **snippet JUnit** (phải có JUnit Jupiter dependency, `context`, `jdbc`, `e1/e2/at`) chứ không phải file chạy của phần 8. Kiểm tra DB effect quan trọng hơn việc chỉ đếm số lần listener được gọi.

### 16.2. Test không được chỉ assert số lần publish

Với Spring TestContext và `@RecordApplicationEvents`:

```java
long published = events.stream(OrderPaid.class).count();
```

Có thể trả 3 nếu test publish ba lần, nhưng **không** chứng minh DB đã chống trùng. Recorder kiểm tra publisher path, còn idempotency phải được kiểm tra ở side effect/state store. Nếu listener async, test phải chờ outcome có timeout và probe đúng boundary.

### 16.3. Test cạnh tranh thật sự

Đừng dùng `Thread.sleep(50)` để “mong hai worker tranh chấp”. Hãy dùng `CountDownLatch` để đồng bộ thời điểm bắt đầu, chạy hai tasks, chờ `Future.get()`/timeouts và assert một effect. Nếu cần dựa vào locking/transaction của DB, test trên một database có isolation/constraint tương đương production; hành vi in-memory H2 không chứng minh toàn bộ semantics của PostgreSQL/MySQL/Oracle trong mọi cấu hình.

### 16.4. Test lỗi ngoài DB

Dùng fake external API có thể “thực hiện thành công rồi báo timeout” để kiểm chứng retry với cùng idempotency key. Đây là failure window khó nhất: một exception/timeout từ client không chứng minh downstream chưa hoàn thành thao tác.

## 17. Quy trình chẩn đoán khi thấy duplicate production

**Bước 1 — Xác định đang trùng cái gì.** Cùng eventId hay khác eventId? Một subscriber hay nhiều subscriber? Có trùng side effect thật hay chỉ trùng log?

**Bước 2 — Tìm nguồn publication.** Gắn mốc và ID tại producer, outbox, broker, registry và consumer; không kết luận chỉ dựa vào số dòng log.

**Bước 3 — Tìm ranh giới retry.** Request retry, transaction retry, outbox relay restart, broker redelivery, consumer retry policy hay manual replay?

**Bước 4 — Đối chiếu ACK/commit.** DB effect đã commit chưa khi ACK mất? Marker đã commit chưa? Có network timeout sau khi remote service thực thi không?

**Bước 5 — Xem khóa idempotency.** Có dùng eventId ổn định? Subscriber scope? Business effect key có đủ phân biệt các nghiệp vụ hợp lệ không?

**Bước 6 — Tìm race.** Có check-then-insert không constraint? Có nhiều replicas/threads? Có thao tác side effect ngoài transaction không?

**Bước 7 — Kiểm tra transaction proxy.** `@Transactional` có áp dụng không? Có self-invocation khiến proxy không chạy? Marker và effect có cùng DataSource/transaction không?

**Bước 8 — Kiểm tra các lần đã thất bại.** Có marker được ghi quá sớm làm mất retry? Có lỗi bị swallow hoặc ghi thành success giả?

**Bước 9 — Kiểm tra external idempotency.** Dịch vụ đích có lưu idempotency key không? Key có giữ nguyên khi retry? Có cần reconciliation?

**Bước 10 — Thêm test tái hiện.** Same event ID, different event ID same business key, concurrency, rollback, crash window, replay và multi-tenant scope.

### Một bảng triệu chứng

| Triệu chứng | Gợi ý nguyên nhân | Kiểm chứng |
| --- | --- | --- |
| Cùng eventId xuất hiện hai lần ở subscriber | Broker/outbox/registry resend | Logs producer/relay/ACK |
| Khác eventId cùng business key | Producer tạo fact hai lần hoặc workflow được gọi lại | Business command state, unique key |
| DB effect count = 2 | Thiếu unique constraint hoặc transaction không atomic | Schema, isolation, code path |
| Chỉ gửi email trùng, DB row vẫn một | External side effect không idempotent | Notification key/provider |
| Có processed marker nhưng không có effect | Mark-before-effect hoặc transaction tách rời | Transaction audit, error path |
| Retry không bao giờ xử lý lại | Marker ghi sai trước khi hoàn tất | Recovery/marker semantics |
| Subscriber Audit bỏ qua event do Fulfillment xử lý | Dedupe key không scoped theo subscriber | PK/unique key |
| Đôi khi xử lý hai lần khi tải cao | Check-then-act race hoặc nhiều instances | Concurrency test, uniqueness |
| Sau replay thủ công gửi nhiều notification | Replay mode không tách side effects | Replay policy, consumer isolation |
| Trace/log hai dòng nhưng effect chỉ một | Redelivery đã được skip đúng | Effect state, outcome metrics |

## 18. Những lỗi thường gặp

1. **Cho rằng một event luôn được deliver một lần.** Broker, outbox và retry có thể phát lại.
2. **Cho rằng Spring core tự retry mỗi ApplicationEvent.** Phải kiểm tra cơ chế ứng dụng bổ sung.
3. **Dùng UUID mới ở mỗi lần gửi lại cùng occurrence.** Làm event-level dedupe mất tác dụng.
4. **Chỉ dùng `Set` trong JVM.** Mất dữ liệu khi restart và không đồng bộ giữa replicas.
5. **Set.add trước side effect rồi quên failure path.** Lỗi nửa chừng làm mất retry.
6. **SELECT-then-INSERT không constraint.** Race giữa workers.
7. **Ghi processed marker và business effect ở hai giao dịch riêng.** Có cửa sổ mất hoặc nhân đôi tác dụng.
8. **Gọi API ngoài sau local commit rồi coi DB transaction bảo vệ API.** Không có atomicity xuyên hệ thống.
9. **Dùng eventId để dedupe mọi business effect.** EventId mới của cùng invariant có thể qua được.
10. **Dùng orderId để dedupe mọi loại event.** Có thể chặn giao dịch hợp lệ khác của cùng đơn.
11. **Không scope theo subscriber.** Một consumer làm consumer khác bỏ qua.
12. **Gộp correlationId với eventId.** Một workflow có nhiều fact riêng.
13. **Xem `@TransactionalEventListener` là queue bền vững.** After-commit callback không tự giải quyết crash window.
14. **Tin rằng outbox ngăn duplicate.** Relay có thể publish nhiều lần khi crash.
15. **Tin rằng broker exactly-once áp dụng đến mọi external side effect.** Guarantee có phạm vi.
16. **Bắt mọi DuplicateKeyException rồi trả success.** Che lỗi schema khác.
17. **Retry vô hạn khi payload không hợp lệ.** Poison event cần policy và dead-letter handling.
18. **Không theo dõi event age, attempts và outcome.** Khó phát hiện các publication mắc kẹt.
19. **Dùng ID có PII làm metric labels.** High cardinality và rủi ro dữ liệu.
20. **Dọn processed IDs quá sớm.** Replay cũ có thể tạo side effect lại.
21. **Không kiểm thử cạnh tranh.** Mã pass trong một thread nhưng lỗi với hai workers.
22. **Nhầm event log lặp với double charge.** Phải kiểm tra trạng thái effect thực.
23. **Không phân biệt genuine repeated operation với duplicate.** Làm mất nghiệp vụ hợp lệ.
24. **Thiếu cơ chế đối soát external API sau timeout.** Không biết đã hoàn tất hay chưa.

## 19. Checklist thiết kế chống duplicate

- [ ] Có định nghĩa **event occurrence**, **delivery attempt** và **business effect** rõ ràng?
- [ ] Retry của cùng occurrence giữ nguyên eventId?
- [ ] Dedupe được scope theo subscriber và, nếu cần, tenant?
- [ ] Business effect có unique key theo invariant thực sự?
- [ ] Không dùng `contains` rồi `insert` không đồng bộ như bảo đảm duy nhất?
- [ ] Processed marker và DB side effect nằm trong một transaction có unique constraint?
- [ ] Nếu effect ở hệ thống ngoài, có stable idempotency key hoặc reconciliation?
- [ ] Producer có business command idempotency và chống phát fact sai?
- [ ] Event routing/outbox/registry/broker đã được kiểm tra failure windows?
- [ ] Duplicate bình thường được ghi nhận khác với lỗi nghiêm trọng?
- [ ] Consumer không swallow lỗi không phải duplicate?
- [ ] Có thử retry sau rollback và replay sau commit?
- [ ] Có test cùng eventId, khác eventId cùng key và khác key hợp lệ?
- [ ] Có test concurrency trên database/transport gần production?
- [ ] Dedupe retention dài đủ cho replay/retry hợp lệ?
- [ ] Có tránh tạo lại side effect production khi manual replay?
- [ ] Có metric outcome, alert cho backlog/failed events và log có correlation an toàn?
- [ ] Không dùng “exactly once” mà không ghi rõ phạm vi guarantee?

**Kết luận:** Duplicate event trong thực tế thường là một phần của mô hình phục hồi: sau timeout, crash hoặc replay, producer và consumer có thể không biết tác dụng đã hoàn tất hay chưa. Trong Spring Application Events, việc publish hai lần có thể gọi listener hai lần; khi bổ sung outbox, broker hoặc Event Publication Registry, redelivery càng cần được xử lý có chủ đích. Cách bền vững là **stable event ID cho occurrence**, **idempotency theo từng subscriber**, **business unique key cho side effect**, **transaction atomic với dữ liệu nghiệp vụ**, và **idempotency/reconciliation tại external service**. Chấp nhận nhiều lần gọi handler, nhưng bảo vệ kết quả nghiệp vụ không bị nhân đôi.

## Tài liệu tham khảo

- [Spring Framework — Application Events và ApplicationEventPublisher](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Modulith — Working with Application Events và Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)
- [Microservices.io — Idempotent Consumer Pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
- [Microservices.io — Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [H2 Database documentation](https://h2database.com/html/main.html)

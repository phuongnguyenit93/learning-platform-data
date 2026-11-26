# Chọn Testcontainers khi cần dependency thật

## 1. Quyết định dựa vào hành vi phải chứng minh, không dựa vào độ “thật” của công cụ

Trong chiến lược kiểm thử của `SPRING_MODULITH_VERIFICATION_TESTING`, câu hỏi đúng không phải “có nên chạy mọi test bằng Testcontainers?”, mà là: **Nếu thay dependency bằng mock hoặc in-memory implementation, phép kiểm nào sẽ mất khả năng phát hiện lỗi?**

Hãy chọn **Testcontainers** khi kết luận của test phụ thuộc vào hành vi thực của một hệ thống có giao thức, engine hoặc persistence semantics riêng: PostgreSQL constraint/locking/transaction, Kafka partition/offset/group, RabbitMQ routing/ack/requeue hoặc một service tương thích API có state cần kiểm chứng.

| Hợp đồng cần kiểm chứng | Test double đủ? | Khi nào Testcontainers có giá trị |
| --- | --- | --- |
| Domain rule “số tiền phải dương” | **Có**: unit test thuần Java | Không cần container |
| Port thanh toán bị từ chối thì domain chuyển `REJECTED` | **Có**: fake/Mockito theo port | Không cần gateway thật để test nhánh domain |
| PostgreSQL unique index chặn hai transaction cùng reference | **Không**: mock repository không thực thi unique index | PostgreSQL container với schema/migration thật |
| JPA mapping, enum/converter, dialect-specific query | Mock thường không đủ; H2 có thể khác PostgreSQL | Container chứa đúng loại DB production |
| `@TransactionalEventListener(AFTER_COMMIT)` có nhìn thấy state đã commit? | Cần DB/transaction thật, nhưng không nhất thiết broker | PostgreSQL container có giá trị khi correctness phụ thuộc DB |
| RabbitMQ routing key đưa message tới đúng queue | Mock `RabbitTemplate` không kiểm chứng routing | RabbitMQ container và queue/binding thực |
| Kafka consumer group/partition/offset, retry/DLT | Mock producer không kiểm chứng consumer/broker semantics | Kafka container cùng topology cần test |
| JSON DTO được serialize đúng trong một method | Có thể dùng serializer/unit test | Container không tăng nhiều bằng chứng |
| HTTP client gửi method/header/body đúng contract | Stub server/WireMock thường đủ | Container service chỉ cần khi server behavior là điều cần kiểm chứng |
| Toàn bộ luồng payments → orders → notifications | Unit/module mocks riêng không thay integration | Chọn đúng các dependency thật theo đường đi end-to-end |

**Nguyên tắc chọn tối thiểu:** dùng dependency thật ở **ranh giới nơi lỗi có khả năng xuất hiện**, không biến mọi phép kiểm thành integration test toàn ứng dụng.

Trong học phần này, `ApplicationModules.verify()` vẫn được dùng để kiểm chứng module graph và `allowedDependencies`; Testcontainers kiểm chứng **hành vi hạ tầng**. Hai loại bằng chứng bổ trợ nhau nhưng không thay thế nhau.

### 1.1. Một quyết định theo ba câu hỏi

1. Test đang nói về **quy tắc của module** hay **semantics của adapter bên ngoài**?
2. Nếu dùng fake, liệu lỗi về SQL dialect, commit, lock, broker ack/routing hoặc network protocol có còn bị phát hiện không?
3. Có thể chạy dependency thật trong container với **dữ liệu/namespace/lifecycle cô lập**, không động vào môi trường production, hay không?

Nếu câu 1 là domain thuần, câu 2 là “vẫn phát hiện đầy đủ”, test nhẹ hơn có lợi thế. Nếu correctness phụ thuộc đặc tính DB/broker, dùng container cho **test tương ứng**.

## 2. PostgreSQL container: kiểm chứng unique constraint thật

Giả sử module `payments` lưu mỗi payment receipt theo `transaction_id` và yêu cầu **một transaction chỉ có tối đa một receipt**. Mockito repository có thể được stub để “ném duplicate” nhưng không xác minh rằng migration của production thực sự tạo unique constraint.

Một migration minh họa:

```sql
-- Ví dụ migration thuộc ứng dụng, không phải file được tạo bởi bài học.
CREATE TABLE payment_receipts (
    id UUID PRIMARY KEY,
    transaction_id VARCHAR(120) NOT NULL UNIQUE,
    amount NUMERIC(19, 2) NOT NULL
);
```

Khi chạy test, bảng phải tồn tại nhờ Flyway/Liquibase hoặc cơ chế schema initialization **thực sự được cấu hình trong project**. Không nên tạo schema giả trong test rồi tuyên bố migration production đã được kiểm chứng.

### 2.1. Test JUnit với PostgreSQL thật, không bọc transaction test

```java
package com.example.shop.payments;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@ApplicationModuleTest
class PaymentReceiptPostgresIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>(
                    DockerImageName.parse("postgres:16-alpine"))
                    .withDatabaseName("payment_it");

    @DynamicPropertySource
    static void postgresProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }

    @Autowired JdbcTemplate jdbc;

    @Test
    void databaseRejectsDuplicateTransactionReference() {
        String transactionId = "tx-" + UUID.randomUUID();

        try {
            jdbc.update(
                    "INSERT INTO payment_receipts " +
                    "(id, transaction_id, amount) VALUES (?, ?, ?)",
                    UUID.randomUUID(), transactionId,
                    new BigDecimal("125000.00"));

            assertThatThrownBy(() -> jdbc.update(
                    "INSERT INTO payment_receipts " +
                    "(id, transaction_id, amount) VALUES (?, ?, ?)",
                    UUID.randomUUID(), transactionId,
                    new BigDecimal("125000.00")))
                    .isInstanceOf(DuplicateKeyException.class);

            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM payment_receipts " +
                    "WHERE transaction_id = ?",
                    Integer.class, transactionId);

            assertThat(count).isEqualTo(1);
        } finally {
            // Chỉ xóa dữ liệu mang key do test sở hữu.
            jdbc.update(
                    "DELETE FROM payment_receipts " +
                    "WHERE transaction_id = ?",
                    transactionId);
        }
    }
}
```

Đây là ví dụ gần chạy được trong một dự án có `@SpringBootApplication`, module `payments`, Spring JDBC, migration tạo bảng, PostgreSQL driver, Testcontainers và JUnit Jupiter tương thích. Nó **không** thể tự biên dịch thành một ứng dụng hoàn chỉnh nếu chưa có project và dependencies đó.

**Vì sao không gắn `@Transactional` lên method test?** PostgreSQL đánh dấu transaction hiện tại bị lỗi sau statement vi phạm constraint; nếu test tiếp tục query trong cùng transaction chưa rollback, query có thể lỗi “current transaction is aborted”. Mẫu trên để từng thao tác JDBC thực thi theo cấu hình autocommit thông thường khi không có test-managed transaction bao quanh. Khi ứng dụng cần quản lý transaction thật, dùng transaction riêng có rollback rõ ràng cho trường hợp duplicate, rồi quan sát bằng transaction mới.

### 2.2. Bài test chứng minh gì?

- Container chạy PostgreSQL thật, không phải H2 hoặc Mockito.
- SQL unique constraint từ schema thực tế từ chối một `transaction_id` trùng.
- Spring JDBC dịch lỗi unique-key thích hợp thành `DuplicateKeyException` trong cấu hình minh họa.
- Sau insert thứ hai thất bại, còn đúng một receipt.
- Cleanup chỉ xóa `transactionId` do test tạo, kể cả assertion fail thông thường.

**Chưa chứng minh:** service payment thật sử dụng mapping và transaction đúng, hai consumers concurrent không double charge, listener `AFTER_COMMIT` chạy đúng, hoặc outbox/registry hoàn tất. Muốn kiểm tra những điều này, phải gọi **API/adapter thực** thay vì chỉ SQL, hoặc bổ sung module/integration tests.

### 2.3. Khi H2/mock có thể cho tín hiệu sai

H2 có ích trong những phép kiểm phù hợp, nhưng có khác biệt PostgreSQL về dialect, kiểu JSONB/UUID, SQL function, isolation/locking, constraint timing và execution plan. `MODE=PostgreSQL` không biến H2 thành PostgreSQL. Nếu sản phẩm dùng feature của PostgreSQL, một test H2 xanh không chứng minh SQL sẽ hoạt động trên production DB.

Không vì thế mà cần container cho mọi repository method. Dành container cho mapping/SQL/constraint/transaction có **rủi ro phụ thuộc engine**, còn unit test domain vẫn dùng fake hoặc object thật không cần database.

## 3. RabbitMQ container: kiểm chứng message đi qua broker thật

Một test mock `RabbitTemplate.convertAndSend(...)` chỉ cho biết code **đã gọi API** với tham số phù hợp. Nó không chứng minh broker nhận message hay default exchange có thể route tới một queue tồn tại.

Nếu mục tiêu là kiểm tra AMQP transport, dùng RabbitMQ container và một queue riêng cho test.

### 3.1. Ví dụ JUnit gửi/nhận qua queue thật

```java
package com.example.shop.notifications;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.AmqpAdmin;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@ApplicationModuleTest
class NotificationAmqpTransportIT {

    @Container
    static final RabbitMQContainer rabbit =
            new RabbitMQContainer(
                    DockerImageName.parse(
                            "rabbitmq:3.13-management-alpine"));

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        registry.add("spring.rabbitmq.username",
                rabbit::getAdminUsername);
        registry.add("spring.rabbitmq.password",
                rabbit::getAdminPassword);
    }

    @Autowired RabbitTemplate template;
    @Autowired AmqpAdmin admin;

    @Test
    void sendsAndReceivesThroughRealBroker() {
        String queueName = "it-notification-" + UUID.randomUUID();
        String message = "event-" + UUID.randomUUID();

        admin.declareQueue(new Queue(
                queueName, false, false, true));

        try {
            // Default exchange: routing key bằng tên queue.
            template.convertAndSend("", queueName, message);

            Object received =
                    template.receiveAndConvert(queueName, 5_000L);

            assertThat(received).isEqualTo(message);
        } finally {
            // Chỉ xóa queue do chính test tạo.
            admin.deleteQueue(queueName);
        }
    }
}
```

Điều kiện: ứng dụng có `spring-boot-starter-amqp` (hoặc cấu hình tương đương), AMQP auto-configuration và các dependency Testcontainers. Queue được tạo với tên riêng theo test, không dùng chung queue nghiệp vụ. `receiveAndConvert(..., timeout)` đợi message trong thời hạn hữu hạn; không cần `Thread.sleep(...)`.

**Bài test chứng minh:** kết nối tới RabbitMQ thật, queue tồn tại, gửi message String qua default exchange và nhận payload bằng `RabbitTemplate`.

**Chưa chứng minh:** exchange/routing key custom của ứng dụng, Jackson converter cho domain event, `@RabbitListener` của business consumer, manual acknowledgement, retry/DLQ, hoặc business state đã commit. Để chứng minh chúng phải cấu hình đúng queue/exchange/binding/listener của hệ thống và assert message ID/ack hoặc public read model tương ứng.

### 3.2. Không thay thế business consumer bằng observer cạnh tranh

Nếu dùng **cùng queue** cho business listener và test `RabbitTemplate.receiveAndConvert(...)`, hai consumers có thể tranh message; test nhận record mà listener nghiệp vụ lẽ ra phải xử lý. Vì vậy:

- Test transport thuần: tạo queue riêng như ví dụ.
- Test business listener: để listener ứng dụng tiêu thụ queue của nó, sau đó query business state.
- Test outbound notification: dùng một observer queue được bind riêng vào exchange, với routing phù hợp.
- Test ack/retry: chờ đúng completion, nack/requeue và DLQ, không chỉ chờ một message bất kỳ.

Với Kafka, nguyên tắc tương tự nhưng cách quản lý khác: dùng topic/group/offset có scope rõ; không dùng consumer test **cùng group** với business consumer nếu muốn quan sát bản sao event.

## 4. Module scenario: kết hợp dependency thật với assertion nghiệp vụ

Testcontainers không nên chỉ là “container start được”. Một test tích hợp có giá trị phải nối **behavior của module → commit/transport → state quan sát được**.

Ví dụ `orders` tiêu thụ Spring application event `PaymentCaptured` để cập nhật order:

```java
// Public event contract do ứng dụng định nghĩa.
package com.example.shop.payments.events;

import java.math.BigDecimal;
import java.util.UUID;

public record PaymentCaptured(
        UUID eventId,
        UUID orderId,
        String transactionId,
        BigDecimal amount) {}
```

```java
// Public read-model contract do module orders định nghĩa.
package com.example.shop.orders;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderPaymentView(
        UUID orderId,
        boolean paid,
        UUID capturedEventId,
        String transactionId,
        BigDecimal amount) {

    public boolean matches(
            UUID event, String transaction, BigDecimal expectedAmount) {
        return paid
                && event.equals(capturedEventId)
                && transaction.equals(transactionId)
                && amount != null
                && amount.compareTo(expectedAmount) == 0;
    }
}
```

```java
// File riêng: public query API của module orders.
package com.example.shop.orders;

import java.util.Optional;
import java.util.UUID;

public interface OrderQueries {
    Optional<OrderPaymentView> paymentOf(UUID orderId);
}
```

Trong một `@ApplicationModuleTest` có database Testcontainers đã cấu hình như mục 2, bài test có thể là:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@ApplicationModuleTest
class OrderPaymentConsumerIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }

    @Autowired OrderFixture fixture;
    @Autowired OrderQueries queries;

    @Test
    void commitsStateForExactlyThisPayment(Scenario scenario) {
        BigDecimal amount = new BigDecimal("125000.00");
        UUID orderId = fixture.awaitingPaymentAndCommit(amount);
        UUID eventId = UUID.randomUUID();
        String transactionId = "tx-" + eventId;

        assertThat(queries.paymentOf(orderId).orElseThrow().paid())
                .isFalse();

        scenario.publish(new PaymentCaptured(
                        eventId, orderId, transactionId, amount))
                .andWaitAtMost(Duration.ofSeconds(8))
                .forStateChange(
                        () -> queries.paymentOf(orderId),
                        state -> state.filter(view ->
                                view.matches(eventId, transactionId, amount))
                                .isPresent())
                .andVerify(state -> {
                    OrderPaymentView paid = state.orElseThrow();
                    assertThat(paid.orderId()).isEqualTo(orderId);
                    assertThat(paid.capturedEventId()).isEqualTo(eventId);
                });
    }
}
```

`OrderFixture` là test-support do dự án cung cấp; `awaitingPaymentAndCommit(...)` phải commit dữ liệu trước khi listener ở transaction khác cần đọc. Class trên khai báo PostgreSQL container và datasource properties ngay tại chỗ, nhưng project vẫn phải có schema migration, driver, Spring transaction manager và listener/query adapter phù hợp. Các đoạn event/read model ở trên phải đặt trong các file Java riêng đúng package và import phù hợp.

Cần kiểm tra ba điều:

1. `Scenario.publish(...)` phát **Spring application event** vào module test, **không tự đi qua RabbitMQ/Kafka**. Bài này chứng minh handler và DB state, không chứng minh AMQP transport.
2. Nếu listener là `@TransactionalEventListener(AFTER_COMMIT)`, transaction phát event phải **commit thật**; test-managed `@Transactional` mặc định rollback sẽ không kích hoạt phase `AFTER_COMMIT` như kỳ vọng.
3. Predicate phải đọc state **mới sau commit** qua query API; không giữ một JPA entity được load trước khi listener ghi rồi assert mãi trên object cũ.

Đây là cách thiết kế test không lẫn lộn **logic module**, **PostgreSQL persistence** và **broker routing**. Khi cần kiểm chứng cả chuỗi event end-to-end qua broker, viết một integration test có producer/consumer topology thật và state assertion tương ứng.

## 5. Kết nối container vào Spring: chọn một cơ chế rõ ràng

Có hai cách phổ biến; đừng cấu hình cả hai cùng key mà không biết đường nào được sử dụng.

### 5.1. `@DynamicPropertySource`: linh hoạt, dùng được với Spring TestContext

Mục 2 và 3 đã cho ví dụ hoàn chỉnh:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
}
```

Spring giải quyết URL/port được Docker cấp khi cần và đưa các property vào `Environment` của test. Supplier không có nghĩa datasource/connection factory đã được rebind sau khi tạo: container phải còn sống trong lifecycle của context.

### 5.2. `@ServiceConnection`: giảm boilerplate khi Spring Boot hỗ trợ

Ở những phiên bản Spring Boot có Testcontainers service connections, một container được nhận diện có thể cung cấp `ConnectionDetails` cho auto-configuration:

```java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;

@Container
@ServiceConnection
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
```

Đoạn này là **field trong một test class** đã có `@Testcontainers` và Spring Boot test configuration, không phải file Java độc lập. Cần dependency `spring-boot-testcontainers` và phiên bản Boot/Testcontainers tương thích. Cơ chế tương tự áp dụng với các container khác **khi loại container được Spring Boot hỗ trợ**.

| Tiêu chí | `@DynamicPropertySource` | `@ServiceConnection` |
| --- | --- | --- |
| Ánh xạ custom keys/URL | Rõ ràng, linh hoạt | Tốt khi Boot có factory `ConnectionDetails` tương ứng |
| Mức boilerplate | Cần đăng ký host/port/credentials | Thường ít hơn |
| Hỗ trợ engine/container tùy biến | Có thể tự đặt property phù hợp | Phụ thuộc integration Boot/container được hỗ trợ |
| Dễ nhìn nguồn datasource URL | Rõ từ các property key | Theo Spring Boot connection-details auto-config |
| Điều vẫn phải kiểm tra | Container/context lifecycle, migration, test data | Tương tự |

**Dù dùng cách nào:** khẳng định Testcontainers là database thật bằng cách kiểm tra endpoint hoặc truy vấn đặc thù engine khi điều đó quan trọng, rồi kiểm tra **business contract**, không chỉ `assertThat(dataSource).isNotNull()`.

### 5.3. Dependency build tối thiểu là điều kiện trước khi chạy

Ví dụ Gradle Groovy DSL, với version được quản lý bằng BOM/dependency management của dự án:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    // Nếu dùng @ServiceConnection:
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'

    // PostgreSQL driver theo cấu hình project:
    testRuntimeOnly 'org.postgresql:postgresql'

    // Ví dụ AMQP cần starter và module Testcontainers tương ứng:
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
    testImplementation 'org.testcontainers:rabbitmq'
}
```

Đây là **danh sách định hướng**, không phải file build được chỉnh sửa. Dùng dependency/BOM version tương thích với Spring Boot/Modulith của project. Không kéo `spring-boot-starter-amqp` vào một module production chỉ để chạy bài test vận chuyển nếu kiến trúc không sử dụng AMQP.

## 6. Vòng đời và isolation: container thật không tự làm test sạch

Một PostgreSQL container dùng chung cho cả test class có thể tăng tốc test, nhưng **các bảng vẫn giữ dữ liệu đã commit giữa test methods**. Một RabbitMQ container dùng chung vẫn giữ queues/messages trong lifetime container.

Các quy tắc bắt buộc:

- Mỗi scenario dùng `aggregateId`, `eventId`, `transactionId` riêng.
- Fixture commit trước khi listener ở transaction khác đọc.
- Không `TRUNCATE` bảng hoặc purge queue dùng chung khi các test đang chạy song song.
- Cleanup theo **ID/namespace do test sở hữu** sau khi worker liên quan hoàn tất.
- Đối với fault-injection hoặc recovery cần giữ dữ liệu qua restart, cấp database/schema/broker scope riêng; hủy sau cả hai pha.
- Không coi test `@Transactional` rollback là đủ khi listener `@Async` commit độc lập hoặc publication registry tồn tại trong DB.
- Không giữ một consumer test trên **cùng RabbitMQ queue** hoặc **cùng Kafka consumer group** với business consumer chỉ để quan sát message.

### 6.1. Cẩn thận Spring TestContext cache với `static @Container`

`@Testcontainers` với `@Container static` thường quản lý container theo test class: extension có thể dừng container khi class kết thúc. Spring TestContext cache có thể reuse một `ApplicationContext` và `DataSource` sang class khác nếu cấu hình context tương đương. Khi đó datasource vẫn trỏ tới container của class trước đã dừng.

Một số cách xử lý theo đúng ownership:

1. Dùng container có lifecycle đủ dài để sống cùng context/suite nếu muốn context reuse.
2. Tách các context có datasource/container khác nhau bằng configuration phù hợp.
3. Dùng `@DirtiesContext` có chủ đích sau class khi context thực sự không còn dùng được, đồng thời tránh chạy concurrent trên context chia sẻ.
4. Dùng một test class có container/class lifecycle rõ và không giả định context tự kết nối lại khi port thay đổi.

**Không** mặc định đánh dấu `@DirtiesContext` cho mọi test method: nó làm suite chậm nhưng không xóa static fields, DB đã commit hoặc broker offsets.

### 6.2. Không dọn dữ liệu trước khi async listener dừng

Nếu `Scenario` timeout, listener có thể còn chạy và sẽ ghi sau khi cleanup. Khi không chứng minh được quiescence, đừng xóa row của test khác hoặc hủy container chung để ép suite sạch. Báo lỗi, cô lập namespace/container của scenario, rồi dừng worker/hủy môi trường theo lifecycle được phép.

## 7. Kiểm chứng kết quả: một container xanh chưa phải test xanh

Chạy PostgreSQL/RabbitMQ thành công mới xác nhận hạ tầng test đã khởi động. Hãy xây assertion theo **failure mode cần bắt**:

| Dependency thật | Stimulus | Oracle có giá trị | Không đủ |
| --- | --- | --- | --- |
| PostgreSQL | Insert duplicate transaction | Constraint từ chối, một row còn sau transaction | `SELECT 1` |
| PostgreSQL transaction | Commit fixture, listener update | Query transaction mới thấy đúng state sau commit | `saveAndFlush` trong transaction chưa commit |
| PostgreSQL locking | Hai workers tranh cùng aggregate | Bất biến count/balance/stock sau cả hai futures hoàn tất | Chỉ `status == PAID` |
| RabbitMQ | Send qua exchange/binding | Queue/consumer đúng nhận payload và correlation ID | Mockito `convertAndSend` được gọi |
| RabbitMQ retry/DLQ | Listener fail, nack/requeue | Terminal ack/retry/DLQ state đúng | Message “đã gửi” |
| Kafka | Publish record, real consumer nhận | Group/partition/offset và payload đúng | Mock producer success |
| Registry Spring Modulith | Listener fail rồi retry | Publication đúng event/target, trạng thái hoàn tất, idempotency | Global `countIncomplete == 0` |
| HTTP stub | Gọi endpoint giả | Method/header/body và status contract đúng | Không cần container nếu stub server đủ |

### 7.1. Phân biệt ba bằng chứng event

- `PublishedEvents` kiểm chứng **Spring application event được publish** trong module test.
- Event Publication Registry kiểm chứng **publication tracking và completion/recovery** tùy provider.
- PostgreSQL business read model hoặc Kafka/RabbitMQ consumer kiểm chứng **state đã commit hoặc message đã vận chuyển/nhận**.

Không chuyển một assertion ở lớp này thành tuyên bố lớp khác. Ví dụ `Scenario.publish(...)` không tự chứng minh AMQP routing, còn RabbitMQ message được nhận không tự chứng minh order đã commit.

### 7.2. Tránh sai lầm với `@TransactionalEventListener(AFTER_COMMIT)`

Nếu producer publish event trong test-managed transaction mặc định rollback, `AFTER_COMMIT` listener có thể không được kích hoạt. Khi test cần after-commit behavior, hãy thiết kế publisher transaction thực sự commit rồi quan sát read model bằng transaction/snapshot mới. Dùng PostgreSQL container có ích để phát hiện visibility/locking nhưng **không thay** việc định nghĩa transaction boundary cho stimulus.

## 8. Chọn phạm vi Spring Modulith trước khi chọn container

Testcontainers quyết định **dependency hạ tầng**, `@ApplicationModuleTest` quyết định **bean/module scope**. Hai lựa chọn độc lập.

| Loại test | Spring scope phù hợp | Hạ tầng |
| --- | --- | --- |
| Domain policy | Không cần Spring context | Không có container |
| Repository/SQL adapter | Test slice hoặc module test đủ bean | PostgreSQL container nếu engine semantics quan trọng |
| Module consumer xử lý application event | `@ApplicationModuleTest` của consumer | DB container nếu cần persistence thật; không nhất thiết broker |
| AMQP adapter encode/decode/routing | Adapter integration test hoặc module test có AMQP beans | RabbitMQ container |
| Chuỗi qua nhiều module, listener và broker | Integration test với scope dependencies/`@SpringBootTest` tương ứng | Chỉ các dependency external thực sự cần |
| Architecture graph | `ApplicationModules.of(...).verify()` | Không cần container |

Nếu test module `orders` thiếu một port, không tự động nới bootstrap scope sang mọi module. Hãy xem lại named interfaces, `allowedDependencies` và fake của external adapter. “Container đã chạy” không hợp thức hóa một dependency production sai.

Ví dụ API công khai để `orders` chỉ phụ thuộc event contract:

```java
// File payments/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.payments.events;
```

```java
// File orders/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "payments::events")
package com.example.shop.orders;
```

Kiểm chứng cấu trúc độc lập với Docker:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void dependencyRulesRemainValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`ShopApplication` là class ứng dụng Spring Boot của ví dụ. Test kiến trúc bắt lỗi phụ thuộc package `internal`/named interface; test Testcontainers bắt lỗi giao thức/engine và side effects. **Cần cả hai khi mục tiêu là verification-testing đầy đủ.**

## 9. CI quality gate: dùng Testcontainers có kiểm soát

Một quality gate phù hợp:

1. **Unit + architecture tests trước:** chạy nhanh, không Docker; chặn lỗi domain và `ApplicationModules.verify()`.
2. **PostgreSQL adapter tests:** chỉ nhóm phụ thuộc SQL dialect/constraint/transaction; chạy migration thật và assert failure mode.
3. **Broker transport tests:** chỉ nhóm cần RabbitMQ/Kafka semantics; dùng queue/topic/group riêng.
4. **Module/integration behavior:** `@ApplicationModuleTest`, `Scenario`, public query API và transaction commit rõ.
5. **Failure/retry tests:** dùng DB/registry/broker riêng nếu resubmission có thể ảnh hưởng test khác.
6. **Resource lifecycle:** cleanup theo ID/namespace, đóng observers và chờ async completion; không global purge.
7. **Image policy:** pin version image phù hợp production, kiểm soát nguồn tải, cập nhật và scan theo chính sách CI.
8. **Resource budget:** kiểm soát số containers/forks, connection pool, Docker memory và startup; không tăng parallelism vô hạn.
9. **Diagnostics:** log tên image/version, module, event IDs, resource namespace và last observed state; không log credentials.
10. **Fail on missing dependency:** thiếu container runtime/migration không được biến thành test PASS giả. Có thể tách task yêu cầu Docker và báo rõ task đó chưa chạy.

Ví dụ chạy trong Gradle project đã khai báo test task:

```bash
./gradlew test
```

Nếu integration tests được tách vào `integrationTest` task, CI **phải chạy đúng task đó**. Lệnh ở trên chỉ minh họa, bài này không chạy Gradle hoặc khởi động containers.

### 9.1. Có nên reuse container?

Reuse container theo suite có thể hợp lý khi migrations/startup đắt và mọi test dùng ID/namespace riêng. Nhưng tránh bật Testcontainers reusable-container feature ở CI dùng chung mà không có ownership rõ; một container sống ngoài test job có thể giữ state/bí mật và làm kết quả phụ thuộc run trước. Không đánh đổi repeatability lấy thời gian khởi động nếu chưa có cleanup và isolation đúng.

### 9.2. Checklist ra quyết định

- [ ] Test đang cần chứng minh hành vi của **dependency thật**, không chỉ nhánh domain?
- [ ] Đã nêu rõ bug mà mock/H2/stub sẽ bỏ sót?
- [ ] Chọn đúng engine và image version tương thích môi trường production?
- [ ] Migration/schema/binding/topology thật được áp dụng, không giả lập bỏ qua phần quan trọng?
- [ ] Bean Spring test thực sự trỏ vào container, không vô tình trỏ DB/broker khác?
- [ ] Test kết thúc bằng business/transport assertion có correlation ID, không chỉ “container started”?
- [ ] `@DynamicPropertySource`/`@ServiceConnection` được dùng nhất quán?
- [ ] Context cache và container lifecycle tương thích?
- [ ] Fixture đã commit, reader đọc fresh state khi listener async?
- [ ] Data/queue/topic/group/registry thuộc scope test và cleanup an toàn?
- [ ] Không dùng broker observer cạnh tranh với consumer nghiệp vụ?
- [ ] Test không mutate production resource hoặc xóa DB chung?
- [ ] Dependency Testcontainers chỉ có ở nhóm cần thiết để giữ suite nhanh?
- [ ] Architecture verification vẫn chạy riêng không cần Docker?
- [ ] CI báo FAILED/NOT_RUN rõ khi Docker hoặc migration không sẵn sàng?

## 10. Bài tập tình huống và tài liệu tham khảo

### 10.1. Bài tập chọn chiến lược

**Bài A — Chọn mock thay vì container.** Với use case “payment bị từ chối → order chuyển `REJECTED`”, viết unit test dùng `PaymentGateway` fake. Giải thích vì sao không cần chạy gateway/database thật khi mục tiêu chỉ là domain transition.

**Bài B — PostgreSQL unique constraint.** Áp dụng migration `payment_receipts`, chạy `PaymentReceiptPostgresIT` và bỏ unique constraint trong nhánh học tập. Xác nhận test đỏ vì insert thứ hai không bị từ chối. Hoàn nguyên migration. Đây là ví dụ mutation để chứng minh test thực sự bảo vệ invariant database.

**Bài C — Dialect khác H2.** Dùng một query/column type của production PostgreSQL (ví dụ JSONB hoặc `ON CONFLICT`) trong adapter test. Chứng minh test H2 không đủ căn cứ nếu syntax/semantics khác. Dùng PostgreSQL container thay vì “mock SQL luôn thành công”.

**Bài D — RabbitMQ routing.** Chạy `NotificationAmqpTransportIT`; thay routing key thành một key không khớp queue của default exchange. Quan sát test không nhận payload mong đợi trong thời hạn hữu hạn. Hoàn nguyên key và chạy lại.

**Bài E — Module + DB.** Trên một datasource PostgreSQL container, tạo fixture order đã commit, publish `PaymentCaptured` qua `Scenario` và assert đúng event ID/state. Xác định điều bài này **chưa** chứng minh về AMQP/Kafka.

**Bài F — Consumer thật.** Với broker container có listener ứng dụng, gửi message qua exchange/topic thật, để business consumer xử lý và assert state qua public query API. Không đặt test observer vào cùng queue/group với business consumer.

**Bài G — Registry recovery.** Cố ý gây listener failure trong database registry cô lập, xác minh incomplete publication theo event/target, rồi resubmit và kiểm tra idempotency. Không `TRUNCATE` registry của những test khác.

**Bài H — Context cache/lifecycle.** Dùng container class-scoped và hai test classes có context configuration tương tự; thử điều kiện context reuse sau khi container đầu dừng. Thiết kế lifecycle phù hợp thay vì thêm `@DirtiesContext` vô điều kiện.

**Bài I — CI.** Tách unit/architecture gate không Docker và integration gate có Docker; báo rõ nếu runtime không sẵn. Theo dõi thời gian startup, số containers và tỷ lệ flakiness khi bật parallel có kiểm soát.

### 10.2. Tài liệu tham khảo

- [Spring Modulith — Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `Scenario` và scope module.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()` và dependency boundaries.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): listener và Event Publication Registry.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection`, ConnectionDetails và service integrations.
- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html): đăng ký endpoint động trong TestContext.
- [Testcontainers for Java](https://java.testcontainers.org/): PostgreSQL/RabbitMQ/Kafka modules, JUnit 5 lifecycle.
- [Spring AMQP — Reference](https://docs.spring.io/spring-amqp/reference/): RabbitTemplate, queue, routing và acknowledgement.
- [Spring for Apache Kafka — Reference](https://docs.spring.io/spring-kafka/reference/): topic, consumer groups và offsets.
- [PostgreSQL — Documentation](https://www.postgresql.org/docs/): unique constraints, transactions và locking.

**Chốt lựa chọn:** hãy dùng Testcontainers **khi một fake sẽ bỏ sót bug thuộc engine/giao thức hoặc dữ liệu bền**, rồi viết assertion quan sát đúng hợp đồng thực tế. Nếu domain rule có thể được kiểm chứng đầy đủ ở mức unit/module mà không cần dependency thật, đừng trả chi phí Docker chỉ để test “trông giống production” hơn.

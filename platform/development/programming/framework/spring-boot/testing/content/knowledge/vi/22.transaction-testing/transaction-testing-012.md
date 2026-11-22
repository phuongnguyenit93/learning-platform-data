# Chiến lược dọn dữ liệu khi rollback không bao phủ toàn bộ thao tác

Trong kiểm thử Spring Boot, `@Transactional` thường tạo cảm giác an toàn: test ghi dữ liệu, chạy assertion rồi Spring tự rollback. Điều đó **chỉ đúng cho những thay đổi thực sự tham gia transaction đang được Spring TestContext quản lý**. Khi bài test gửi HTTP request đến server thật, transaction nghiệp vụ chạy trong thread/server context riêng. Khi service dùng `REQUIRES_NEW`, một phần công việc đã commit trong transaction độc lập. Các tác động đến Redis, Kafka, email, object storage, filesystem hoặc API thanh toán cũng không tự được một `JpaTransactionManager` rollback.

Do đó, test suite có thể xanh ở lần chạy đầu và đỏ ở lần chạy sau: unique key trùng, row mồ côi, stale cache, message bị consumer xử lý muộn, file đã tải lên chưa bị xóa. Một chiến lược cleanup đúng không chỉ là gọi `deleteAll()`, mà phải **xác định rõ transaction boundary, sở hữu dữ liệu, thời điểm tác vụ kết thúc, cơ chế xóa, tính idempotent và bằng chứng trạng thái đã sạch**.

Bài Knowledge thuộc nhóm **Giao dịch kiểm thử**, giải thích cách lựa chọn `@AfterEach`, `@Sql` với transaction độc lập, cleanup service `REQUIRES_NEW`, `TestTransaction`, reset fake, namespace/container riêng và compensation. Ví dụ hoàn chỉnh dùng **Java 17, Spring Boot 3.5, JPA/H2 và `@SpringBootTest(RANDOM_PORT)`** để chứng minh cả server-side commit và tác động ngoài DB transaction.

## 1. Vì sao rollback trong test không bao phủ tất cả?

Hãy hình dung đường đi:

```text
JUnit test method
    |
    +-- test-managed transaction của Spring TestContext (nếu có)
    |       +-- thao tác repository cùng thread, cùng manager
    |           thường tham gia và được rollback sau test
    |
    +-- HTTP client: TestRestTemplate
            |
            v
        Embedded HTTP server (thread khác)
            |
            +-- @Transactional service
            |      +-- JPA INSERT/UPDATE/DELETE
            |      +-- commit / rollback của server
            |
            +-- side effect ngoài DB
                   +-- Redis / Kafka / file / fake payment /
                        external API / async worker
```

Spring Boot ghi rõ: với `@SpringBootTest(webEnvironment = RANDOM_PORT)` hay `DEFINED_PORT`, client và server chạy ở thread khác nhau nên **transaction ở server không rollback theo test-managed transaction**. Một HTTP response 201 có thể đồng nghĩa server đã commit dữ liệu, dù test method được gắn `@Transactional`.

**Ba câu hỏi quan trọng trước khi chọn cleanup:**

1. **Ai sở hữu tài nguyên?** Test hiện tại, một test class, cả CI run, một shared staging DB, hay external service?
2. **Transaction nào chứa thao tác?** Outer test transaction, server-side `@Transactional`, `REQUIRES_NEW`, reactive `TransactionalOperator`, hoặc không có transaction?
3. **Cần quan sát trạng thái sau boundary nào?** Trước khi test rollback, sau server commit, sau event consumer ACK, hay sau search index refresh?

Không trả lời được những câu hỏi này thì một assertion “count bằng 0” có thể chỉ đang đọc từ transaction chưa commit, cache cũ hoặc chưa thật sự chờ cleanup hoàn tất.

## 2. Những trường hợp dễ để lại dữ liệu

| Tình huống | Điều rollback không làm được | Hướng xử lý |
|---|---|---|
| HTTP request trong `RANDOM_PORT` | Không hoàn tác transaction server đã commit | Dọn theo test key qua service/JDBC có transaction commit riêng |
| `REQUIRES_NEW` trong service/audit | Commit inner transaction độc lập | Cleanup những row đã commit, hoặc dùng database tách riêng |
| `@Async`, scheduled task, background consumer | Công việc chạy ở thread khác, có thể hoàn tất sau test | Await/cancel rồi cleanup, có timeout |
| Reactive R2DBC/Mongo | Test-managed ThreadLocal không bao phủ Reactive Context | Cleanup Publisher có subscription, transaction reactive đúng |
| Redis/cache | Lệnh cache không tự theo JPA transaction | Xóa key theo run ID; không `FLUSHALL` trên server chia sẻ |
| Kafka/RabbitMQ | Bản tin, offset, queue có lifecycle riêng | Topic/queue/consumer-group của test, fake, drain/purge có kiểm soát |
| S3/object storage/filesystem | Upload và file write không nằm trong DB transaction | Prefix/temporary directory của test; delete trong finally |
| Email, SMS, payment provider | Tác động có thể không thể thu hồi bằng DB rollback | Sandbox/fake, void/refund/compensation và idempotency |
| `@TransactionalEventListener(AFTER_COMMIT)` | Event chạy khi transaction đã commit | Theo dõi outbox, await consumer, cleanup cả state phát sinh |
| Sequence/identity allocator | Nhiều DB không rollback ID đã cấp | Không assert ID liên tục; dùng test-owned business key |
| Nhiều datasource/store | Một transaction manager không quản lý mọi nguồn | Cleanup từng nguồn hoặc chiến lược phối hợp có chứng cứ |

Cả `@DirtiesContext` lẫn việc tạo `ApplicationContext` mới **không tự xóa** row đã commit trong DB ngoài, Redis remote, topic Kafka hay object storage. Nó chỉ ảnh hưởng vòng đời Spring context và một số bean state nằm trong context.

## 3. Ma trận chọn chiến lược dọn dữ liệu

| Điều kiện | Ưu tiên | Lưu ý |
|---|---|---|
| Mọi write cùng test-managed JPA/JDBC transaction | Rollback mặc định | Flush khi cần chứng minh SQL/constraint; không áp dụng cho external state |
| HTTP test tạo dữ liệu có khóa sở hữu | `@AfterEach` + cleanup service transaction độc lập | Dùng `REQUIRES_NEW` và kiểm sau khi commit |
| Fixture SQL tĩnh, biết trước key | `@Sql(AFTER_TEST_METHOD, transactionMode=ISOLATED)` | SQL đúng datasource/manager, không xóa dữ liệu test khác |
| Dữ liệu nhiều bảng có FK | Xóa child trước parent, hoặc cascade có thiết kế | Không vô hiệu FK chỉ để test xanh |
| Test cần reset toàn bộ bảng/schema | Schema/DB/container **độc quyền** rồi `TRUNCATE`/recreate | Không chạy destructive DDL trên shared resource |
| Dữ liệu trong Redis, object storage | Prefix/namespace riêng + delete theo ID | TTL chỉ là lớp dự phòng, không thay cleanup ngay |
| External system có side effect không đảo được | Fake/sandbox, compensation có kiểm soát | Compensation không phải ACID rollback |
| Test parallel/concurrency | Run ID/schema/topic tách theo worker | Tránh `DELETE WHERE prefix LIKE 'it-%'` toàn cục |
| HTTP timeout, commit chưa rõ | Idempotency key + query final state + bounded retry | Đừng cho rằng response lỗi = chưa ghi |

Một cleanup tốt có **scope**, **idempotency**, **verification**, **failure reporting**, và **ownership**. Có thể kết hợp nhiều chiến lược: DB transaction riêng + reset fake trong `finally` + TTL fallback cho tài nguyên test bỏ lại khi process crash.

## 4. Thiết kế test key: đừng xóa tất cả

Ví dụ mỗi test tạo một key:

```java
String testKey = "it-" + UUID.randomUUID();
```

Snippet dùng trong JUnit test, cần `java.util.UUID`. Ghi `testKey` vào order, outbox, cache key, tên file hoặc message header để cleanup theo đúng tài nguyên test đã tạo. Khi CI chạy song song, có thể dùng thêm run ID hoặc tenant ID để phân biệt.

**Không dùng** `DELETE FROM orders`, `Redis FLUSHALL` hoặc xóa toàn bộ index Elasticsearch nếu resource đang được chia sẻ. Nếu cần reset toàn bộ, trước hết phải tạo database/schema/container riêng do test sở hữu. Một bài test có thể tạo hai order, nhưng cleanup chỉ được xóa **chính hai order đó**.

Dùng namespace rõ trong log và khi điều tra rác test:

```text
it-run-7d21/test-593d/order-01
it-run-7d21/test-593d/outbox-01
it-run-7d21/test-593d/cache:order-01
```

Đây là ví dụ format ID, không phải nội dung thực tế. Không đưa mật khẩu, email thật hoặc PII vào test key.

## 5. Ví dụ runnable Java 17: server-side DB transaction và side effect ngoài DB

Giả sử API `POST /api/demo-orders` tạo một order:

- Service gọi `repository.saveAndFlush` trong `@Transactional`.
- Service gọi fake `PaymentCaptureSimulator.capture(testKey)` bên ngoài DB transaction.
- Nếu có `failAfterCapture`, service throw một unchecked exception, DB **rollback** nhưng fake **vẫn giữ capture**.
- Nếu không lỗi, DB commit và HTTP trả `201 Created`.
- Test gọi HTTP trên server RANDOM_PORT, **không dùng test-managed `@Transactional`**.
- `@AfterEach` xóa DB theo `testKey` qua một public service `REQUIRES_NEW`, dọn fake bằng `finally`, rồi assert dữ liệu không còn.

Đây là ví dụ có fake side effect **trong cùng JVM nhưng không thuộc JPA transaction**, giúp tái hiện vấn đề an toàn. Nó không giả làm payment gateway thật; với production payment phải dùng sandbox/refund API và không đưa `failAfterCapture` lên public endpoint.

### 5.1. Cây thư mục

```text
cleanup-transaction-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/cleanup/
    │   ├── CleanupDemoApplication.java
    │   ├── DemoOrder.java
    │   ├── DemoOrderRepository.java
    │   ├── PaymentCaptureSimulator.java
    │   ├── OrderCreationService.java
    │   ├── OrderCleanupService.java
    │   └── DemoOrderController.java
    └── test/java/com/example/cleanup/
        └── CleanupAcrossTransactionsTest.java
```

### 5.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>cleanup-transaction-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

POM dùng Spring MVC embedded server, Spring Data JPA, H2 và JUnit Jupiter. `spring-boot-starter-test` trên Boot 3.5 có `TestRestTemplate` và AssertJ. Không cần WebFlux/HTTP client reactive cho ví dụ; nếu ứng dụng thật là WebFlux/R2DBC thì transaction/lifecycle khác và được bàn ở phần sau.

### 5.3. `CleanupDemoApplication.java`

```java
package com.example.cleanup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CleanupDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CleanupDemoApplication.class, args);
    }
}
```

File nằm tại **`src/main/java/com/example/cleanup/CleanupDemoApplication.java`**. Spring scan các bean trong cùng package; test cũng thuộc package này.

### 5.4. Entity `DemoOrder`

File **`src/main/java/com/example/cleanup/DemoOrder.java`**:

```java
package com.example.cleanup;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "demo_orders",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_demo_orders_test_key",
                columnNames = "test_key"))
public class DemoOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
            name = "test_key",
            nullable = false,
            updatable = false,
            length = 80)
    private String testKey;

    @Column(name = "sku", nullable = false, length = 80)
    private String sku;

    protected DemoOrder() {
    }

    public DemoOrder(String testKey, String sku) {
        this.testKey = testKey;
        this.sku = sku;
    }

    public Long getId() {
        return id;
    }

    public String getTestKey() {
        return testKey;
    }

    public String getSku() {
        return sku;
    }
}
```

`test_key` unique giúp xác định một row thuộc test nào. `GenerationType.IDENTITY` có thể làm Hibernate INSERT sớm để lấy ID, nhưng **INSERT đã thực thi không đồng nghĩa commit**. Một exception ở cuối transaction vẫn có thể rollback nó.

### 5.5. Repository

File **`src/main/java/com/example/cleanup/DemoOrderRepository.java`**:

```java
package com.example.cleanup;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DemoOrderRepository
        extends JpaRepository<DemoOrder, Long> {

    Optional<DemoOrder> findByTestKey(String testKey);
}
```

Repository có các method `saveAndFlush`, `findByTestKey`, `delete` và `flush`. Cleanup dùng `findByTestKey` thay vì xóa toàn bảng.

### 5.6. Fake payment side effect

File **`src/main/java/com/example/cleanup/PaymentCaptureSimulator.java`**:

```java
package com.example.cleanup;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class PaymentCaptureSimulator {

    private final Set<String> captures =
            ConcurrentHashMap.newKeySet();

    public void capture(String testKey) {
        captures.add(testKey);
    }

    public boolean hasCapture(String testKey) {
        return captures.contains(testKey);
    }

    public void forget(String testKey) {
        captures.remove(testKey);
    }
}
```

`ConcurrentHashMap.newKeySet()` an toàn giữa test thread và server thread. Dù `capture` được gọi từ một service `@Transactional`, trạng thái này **không** thuộc H2 transaction nên JPA rollback không dọn được. Trong production không thể gọi `forget` để hủy charge thật; phải dùng sandbox và refund/void/compensating workflow đúng API.

### 5.7. Service lưu DB và tạo side effect

File **`src/main/java/com/example/cleanup/OrderCreationService.java`**:

```java
package com.example.cleanup;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCreationService {

    private final DemoOrderRepository repository;
    private final PaymentCaptureSimulator payments;

    public OrderCreationService(
            DemoOrderRepository repository,
            PaymentCaptureSimulator payments) {
        this.repository = repository;
        this.payments = payments;
    }

    @Transactional
    public DemoOrder create(
            String testKey, String sku, boolean failAfterCapture) {

        DemoOrder saved = repository.saveAndFlush(
                new DemoOrder(testKey, sku));

        payments.capture(testKey);

        if (failAfterCapture) {
            throw new IllegalStateException(
                    "simulated failure after capture");
        }
        return saved;
    }
}
```

Phương thức public `create` được controller gọi qua Spring bean proxy. Khi `failAfterCapture` là `true`, unchecked exception khiến DB transaction rollback nhưng fake đã cập nhật; khi `false`, DB transaction commit khi method hoàn tất. Không coi `saveAndFlush` là commit; nó chỉ đồng bộ SQL trong transaction hiện hành.

### 5.8. Cleanup service có transaction riêng

File **`src/main/java/com/example/cleanup/OrderCleanupService.java`**:

```java
package com.example.cleanup;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCleanupService {

    private final DemoOrderRepository repository;

    public OrderCleanupService(DemoOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void removePersistedOrder(String testKey) {
        repository.findByTestKey(testKey)
                .ifPresent(repository::delete);
        repository.flush();
    }
}
```

`removePersistedOrder` là public bean method, được test gọi qua Spring proxy; `REQUIRES_NEW` tạo transaction riêng và **commit DELETE khi method trả thành công**. `findByTestKey(...).ifPresent(delete)` đảm bảo **idempotent** khi row không tồn tại, còn `flush` giúp phát hiện sớm lỗi FK/SQL trước khi kết thúc method. Transaction cleanup này **không** tác động lên fake payment, nên test sẽ gọi `payments.forget` riêng trong `finally`.

Nếu test giữ outer transaction với lock trên cùng row, `REQUIRES_NEW` có thể bị block hoặc deadlock. Vì thế ví dụ không đặt `@Transactional` ở test class; khi áp dụng cho môi trường khác cần xem transaction/connection pool cụ thể.

### 5.9. Controller HTTP

File **`src/main/java/com/example/cleanup/DemoOrderController.java`**:

```java
package com.example.cleanup;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo-orders")
public class DemoOrderController {

    private final OrderCreationService creation;

    public DemoOrderController(OrderCreationService creation) {
        this.creation = creation;
    }

    public record CreateRequest(
            String testKey, String sku, boolean failAfterCapture) {
    }

    public record CreatedResponse(Long id, String testKey, String sku) {
    }

    @PostMapping
    public ResponseEntity<CreatedResponse> create(
            @RequestBody CreateRequest request) {

        DemoOrder saved = creation.create(
                request.testKey(),
                request.sku(),
                request.failAfterCapture());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new CreatedResponse(
                        saved.getId(),
                        saved.getTestKey(),
                        saved.getSku()));
    }
}
```

API hợp lệ trả HTTP **201 Created**; khi service throw và không có error handler riêng, server trả HTTP **5xx**. Tham số `failAfterCapture` là công cụ tạo failure path **chỉ dành cho bài test**; không expose public API như thế trong sản phẩm thật. Bài không có validation/authentication để giữ trọng tâm transaction.

### 5.10. Test chạy trên HTTP server thật

File **`src/test/java/com/example/cleanup/CleanupAcrossTransactionsTest.java`**:

```java
package com.example.cleanup;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.jpa.hibernate.ddl-auto=create-drop",
                "spring.datasource.url=jdbc:h2:mem:cleanup_demo;DB_CLOSE_DELAY=-1"
        })
class CleanupAcrossTransactionsTest {

    @Autowired
    private TestRestTemplate http;

    @Autowired
    private DemoOrderRepository repository;

    @Autowired
    private OrderCleanupService cleanup;

    @Autowired
    private PaymentCaptureSimulator payments;

    private String testKey;

    @BeforeEach
    void createUniqueKey() {
        testKey = "it-" + UUID.randomUUID();
    }

    @AfterEach
    void alwaysCleanupAndVerify() {
        if (testKey == null) {
            return;
        }
        try {
            cleanup.removePersistedOrder(testKey);
        } finally {
            payments.forget(testKey);
        }

        assertThat(repository.findByTestKey(testKey)).isEmpty();
        assertThat(payments.hasCapture(testKey)).isFalse();
    }

    private ResponseEntity<String> post(
            String key, boolean failAfterCapture) {
        var request = new DemoOrderController.CreateRequest(
                key, "BOOK-9", failAfterCapture);
        return http.postForEntity(
                "/api/demo-orders", request, String.class);
    }

    @Test
    void httpCommitProducesServerRowAndExternalEffect() {
        var response = post(testKey, false);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).contains(testKey);
        assertThat(repository.findByTestKey(testKey)).isPresent();
        assertThat(payments.hasCapture(testKey)).isTrue();
    }

    @Test
    void serverRollbackDoesNotUndoExternalEffect() {
        var response = post(testKey, true);

        assertThat(response.getStatusCode().is5xxServerError())
                .isTrue();
        assertThat(repository.findByTestKey(testKey)).isEmpty();
        assertThat(payments.hasCapture(testKey)).isTrue();
    }

    @Test
    void cleanupIsCommittedAndIdempotent() {
        assertThat(post(testKey, false).getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        cleanup.removePersistedOrder(testKey);
        payments.forget(testKey);

        cleanup.removePersistedOrder(testKey);
        payments.forget(testKey);

        assertThat(repository.findByTestKey(testKey)).isEmpty();
        assertThat(payments.hasCapture(testKey)).isFalse();
    }

    @Test
    void cleanupDoesNotDeleteUnrelatedOwnedKey() {
        String anotherKey = "it-other-" + UUID.randomUUID();
        try {
            assertThat(post(testKey, false).getStatusCode())
                    .isEqualTo(HttpStatus.CREATED);
            assertThat(post(anotherKey, false).getStatusCode())
                    .isEqualTo(HttpStatus.CREATED);

            cleanup.removePersistedOrder(testKey);
            payments.forget(testKey);

            assertThat(repository.findByTestKey(testKey)).isEmpty();
            assertThat(repository.findByTestKey(anotherKey)).isPresent();
            assertThat(payments.hasCapture(anotherKey)).isTrue();
        } finally {
            try {
                cleanup.removePersistedOrder(anotherKey);
            } finally {
                payments.forget(anotherKey);
            }
        }
    }

    @Test
    void cleanupOfNonexistentResourceIsSafe() {
        cleanup.removePersistedOrder(testKey);
        payments.forget(testKey);

        assertThat(repository.findByTestKey(testKey)).isEmpty();
        assertThat(payments.hasCapture(testKey)).isFalse();
    }
}
```

Test nhận HTTP body dưới dạng **String**, giúp case lỗi 5xx không phụ thuộc vào cách JSON error envelope được deserialize. Không gắn `@Transactional` lên test class. `@AfterEach` cleanup DB và fake trên mỗi method; `finally` còn dọn fake khi thao tác DB cleanup throw. Nếu DB DELETE lỗi, exception vẫn khiến test báo fail — không dùng `catch(Exception ignored)`.

**Các bằng chứng chính:**

| Test | Kết quả cần thấy |
|---|---|
| `httpCommitProducesServerRowAndExternalEffect` | Server trả 201, order có thật trước cleanup, fake capture tồn tại |
| `serverRollbackDoesNotUndoExternalEffect` | HTTP 5xx, DB row vắng do rollback, fake capture vẫn tồn tại |
| `cleanupIsCommittedAndIdempotent` | Xóa hai lần an toàn, DB và fake đều sạch |
| `cleanupDoesNotDeleteUnrelatedOwnedKey` | Cleanup key A không xóa key B; key B cũng được dọn trong `finally` |
| `cleanupOfNonexistentResourceIsSafe` | Dọn tài nguyên vốn không tồn tại không sinh lỗi |

Với đúng file/mapping trên, dự kiến có **5 phương thức `@Test`**, mỗi test tự tạo key. Không có phụ thuộc vào thứ tự chạy. Case 5xx là **negative test PASS khi response và dữ liệu cuối đúng**, không phải JUnit failure.

### 5.11. Chạy Maven

Cần Java 17+, Maven và quyền bind HTTP loopback port ngẫu nhiên:

```bash
mvn test
```

Chạy riêng:

```bash
mvn -Dtest=CleanupAcrossTransactionsTest test
```

Nếu project có Maven Wrapper, dùng `./mvnw test` hoặc `mvnw.cmd test` trên Windows. Khi chạy đúng example và dependencies thành công, kỳ vọng **Tests run: 5, Failures: 0, Errors: 0**. Server có thể ghi stack trace cho failure-path 5xx có chủ đích; điều đó không nhất thiết khiến test fail.

**Phạm vi:** ví dụ đã soát nội dung và Java signatures để có thể chạy, **không phải tuyên bố đã thực thi Maven trong bài viết này**. Khi đưa vào dự án thật cần chạy CI, kiểm database/schema và error mapping của phiên bản đang dùng.

## 6. Dọn bằng `@Sql` khi dữ liệu đã commit ngoài test transaction

Spring TestContext hỗ trợ `@Sql` thực hiện script trước/sau test. Dùng `SqlConfig.TransactionMode.ISOLATED` khi cần script cleanup chạy trong **transaction độc lập, được commit**, thay vì vô tình nằm trong test transaction mà sau đó rollback.

```java
@Test
@Sql(
    scripts = "/cleanup-fixed-fixture.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
void exercisesRealHttpEndpoint() {
    // Gửi request tới server thật, tạo row đã commit.
}
```

Đây là **snippet**, cần JUnit, `org.springframework.test.context.jdbc.Sql`, `SqlConfig`, Spring test context và fixture đã được định nghĩa. File **`src/test/resources/cleanup-fixed-fixture.sql`** ví dụ:

```sql
DELETE FROM demo_orders
WHERE test_key = 'fixture-owned-by-exactly-one-test';
```

Chỉ dùng key cố định khi test **sở hữu độc quyền** key ấy. Đừng đổi câu lệnh thành `DELETE FROM demo_orders WHERE test_key LIKE 'it-%'` nếu CI có nhiều tests parallel. `@Sql` chỉ quản lý SQL database, không tự xóa message, file, Redis hoặc external payment.

Khi có nhiều datasources/transaction managers, cấu hình cụ thể trong `@SqlConfig` phải trỏ đúng resource. Nếu test setup bằng một `@Sql` **ISOLATED** đã commit, test rollback không xóa fixture ấy; cần có cleanup đối xứng. Đối với UUID động hoặc nhiều loại resource, cleanup service ở mục 5 linh hoạt hơn SQL script tĩnh.

## 7. `TestTransaction` và `REQUIRES_NEW`: kiểm đúng transaction của ai

Trong Spring TestContext, `TestTransaction` cho phép kết thúc/bắt đầu **test-managed transaction** một cách chủ động:

```java
assertTrue(TestTransaction.isActive());
TestTransaction.flagForCommit();
TestTransaction.end();   // Commit test-managed transaction.
TestTransaction.start(); // Tạo một test-managed transaction mới.
```

Snippet chỉ minh họa trong một `@Transactional` JUnit test, cần static `assertTrue` và `org.springframework.test.context.transaction.TestTransaction`. Nó **không** commit hoặc rollback transaction của HTTP server đã kết thúc, cũng không quản lý message broker/S3.

Tương tự, method service:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditEvent(AuditEvent event) {
    // Lưu một audit row trong transaction độc lập.
}
```

Đây không phải file hoàn chỉnh: `AuditEvent` giả định. Nếu method public được gọi **qua Spring proxy** và commit thành công, rollback outer transaction **không xóa audit row**. Cleanup audit cần transaction riêng hoặc namespace DB test. Nếu method bị gọi bằng `this.writeAuditEvent(...)` trong cùng bean, Spring proxy-based transaction thường **không được kích hoạt**, phải kiểm thật transaction boundary thay vì đoán từ annotation.

**Một bẫy JUnit:** `@BeforeEach` và `@AfterEach` theo mặc định chạy **bên trong test-managed transaction** khi test method được gắn `@Transactional`; lệnh DELETE trong `@AfterEach` có thể bị rollback. `@BeforeTransaction`/`@AfterTransaction` của Spring chạy ngoài test-managed transaction, nhưng vẫn cần đảm bảo cleanup dùng transaction manager phù hợp và kiểm committed state.

## 8. Dữ liệu reactive và background: không cleanup khi công việc chưa hoàn tất

Với Spring Data R2DBC hoặc Reactive Mongo, repository `deleteById`/`deleteAll` trả Publisher. Chỉ tạo Publisher mà không subscribe là **chưa dọn được gì**:

```java
StepVerifier.create(repository.deleteById(testId))
        .verifyComplete();
```

Snippet cần `reactor.test.StepVerifier`, repository reactive và `testId` tồn tại. Với cleanup trong reactive transaction, phải dùng `TransactionalOperator` và đúng `ReactiveTransactionManager`; không mặc định `@Transactional` trên JUnit void test tạo Reactor Context bao mọi subscription. Nếu dùng `Mono.block()` trong WebFlux event-loop có thể gặp lỗi blocking; trong JUnit test thread, StepVerifier thường diễn đạt rõ hơn.

### Async worker có thể ghi lại dữ liệu sau cleanup

Giả sử server trả 202 Accepted và worker tiếp tục chạy sau response:

```text
test sends request -> HTTP 202
test deletes DB rows
background worker processes event -> inserts row again
next test sees unwanted row
```

Chiến lược đúng:

1. Đưa `testRunId` vào payload/job.
2. Chờ task hoàn tất hoặc cancel bằng signal/barrier/future với **timeout có giới hạn**, không dùng `Thread.sleep` đoán thời gian.
3. Dọn dữ liệu DB/cache/broker theo đúng test ID.
4. Đọc lại từ boundary đáng tin và xác minh không có state tồn dư.
5. Nếu hệ lưu trữ eventual consistency, dùng bounded polling theo deadline, không assert tức thời vô căn cứ.
6. Mới teardown namespace/container/test client khi worker không thể ghi lại.

Kafka/RabbitMQ: đã ACK một message không có nghĩa broker/queue có thể rollback theo DB transaction. Elasticsearch/OpenSearch: search chưa thấy document có thể chỉ vì chưa refresh, không phải document đã bị xóa. S3: delete request có thể liên quan versioned objects; cần biết bucket versioning và quyền cleanup. Với mọi hệ, chọn đúng resource API và trạng thái xác minh.

## 9. Dọn resource ngoài SQL theo namespace

| Resource | Khóa sở hữu test | Cleanup | Cảnh báo |
|---|---|---|---|
| **MongoDB** | `testRunId` trong document | `deleteMany` theo owner field | Không drop database chung; multi-document transaction phụ thuộc topology |
| **Redis** | `it:{runId}:...` | Delete/UNLINK đúng keys theo namespace | Không `FLUSHALL` trên Redis shared, TTL không thay immediate cleanup |
| **Elasticsearch** | ID/index riêng hoặc `testRunId` | Delete by ID / by query đúng scope, kiểm completion/refresh | Bulk có partial failures, search visibility khác write ACK |
| **Object storage S3** | Object-key prefix riêng | List/delete thuộc prefix, kiểm trạng thái cuối | Versioning, delete marker và external permissions |
| **Kafka/RabbitMQ** | Topic, queue, consumer group test | Tạo/dọn test-specific resources hoặc fake broker | Không purge shared topic/queue; messages có thể được retry |
| **Email/SMS/payment** | Sandbox request ID, idempotency key | Reset sandbox, void/refund/cancel theo contract | Compensation không phải ACID rollback; không dùng real credentials |
| **Local filesystem** | `@TempDir` hoặc temp path test | JUnit-managed temp cleanup, `finally` | Không xóa shared directory |
| **HTTP fake/WireMock** | Per-test stub/scenario | Reset đúng stub/scenario/test server | Reset toàn server có thể ảnh hưởng parallel tests |

**TTL là biện pháp dự phòng**, hữu ích khi process crash trước `@AfterEach`. Một test chạy ngay sau đó vẫn có thể gặp dữ liệu tồn dư trước khi TTL hết, nên cần explicit cleanup và, khi dùng môi trường shared, periodic janitor chỉ xóa **resource có owner rõ và đã quá hạn**.

## 10. Dọn bảng nhiều foreign keys, sequences và schema

Khi test tạo order và outbox có FK:

```sql
DELETE FROM order_items WHERE test_key = ?;
DELETE FROM outbox_events WHERE test_key = ?;
DELETE FROM orders WHERE test_key = ?;
```

Đây là SQL **minh họa**, không phải schema của demo H2 (demo chỉ có `demo_orders`). Khi child không có `test_key`, xóa theo parent ID hoặc join/subquery trước khi xóa parent. Dùng bound parameters, không nối input trực tiếp thành SQL. Không vô hiệu FK toàn cục chỉ để “dọn cho xong”; như vậy test có thể che lỗi integrity.

Khi database/schema là **của riêng test**, `TRUNCATE`, drop/recreate schema hoặc Testcontainers teardown có thể là phương án rõ ràng hơn xóa hàng trăm bảng. Nhưng với một số database như MySQL, DDL/`TRUNCATE` có thể implicit commit và không rollback; không thực hiện trên shared DB. Sau reset schema cần chạy migrations/seed như production thay vì chỉ dựa vào Hibernate auto-DDL khi test cần chứng minh migration.

Sequence/identity IDs thường không liên tục qua rollback; **đừng** assert order mới nhận ID = 1 hay test mới phải dùng ID vừa bị rollback. Hãy assert business key và quyền sở hữu test, không buộc reset sequence để làm test xanh.

## 11. Cleanup phải idempotent, có kiểm chứng và không che lỗi

Checklist kỹ thuật cho cleanup đáng tin:

- **Chỉ xóa dữ liệu thuộc test** theo ID/prefix/tenant/schema xác định.
- **Có thể gọi lại** khi resource đã vắng; tránh lỗi unnecessary.
- **Chạy dù assertion fail** bằng JUnit lifecycle hoặc `try/finally`.
- **Fail loudly** nếu cleanup lỗi; không `catch (Exception ignored) {}`.
- Nếu nhiều cleanup độc lập có thể fail, cố chạy tất cả và **thu thập/suppress errors** thay vì chỉ mất lỗi đầu hoặc chỉ báo lỗi sau.
- Kiểm **resource từng tồn tại trước cleanup**, để tránh test xanh giả khi bước tạo fixture không chạy.
- Kiểm **resource không còn sau cleanup** từ transaction/connection hoặc API đáng tin, không chỉ từ entity cache.
- Dừng/chờ **worker in-flight** trước khi cleanup; dùng timeout, retry bounded cho eventual consistency.
- Ghi diagnostic run ID, resource ID, cleaned count và failure cause nhưng không log PII/secrets.
- Có recovery cho CI crash (TTL, janitor chỉ scope test-owned, container teardown).

Trong ví dụ `@AfterEach`, nếu `cleanup.removePersistedOrder(testKey)` ném exception, `payments.forget(testKey)` vẫn chạy do `finally`. Ngoại lệ cleanup DB vẫn thoát ra và JUnit báo fail. Sau khi cleanup thành công, test xác nhận repository và fake đều sạch. Đó là bằng chứng mạnh hơn việc chỉ gọi một phương thức `delete` rồi cho rằng đã dọn xong.

## 12. Các ca test cleanup cần có trong dự án thực

| Case | Setup | Kết quả cần assert |
|---|---|---|
| Server request thành công | Tạo row bằng HTTP thật | Row tồn tại trước cleanup, vắng sau cleanup |
| Service throw sau DB flush | DB transaction rollback, side effect ngoài DB xảy ra | DB vắng, external còn, rồi cleanup external |
| Test assertion fail | Tạo resource rồi cố ý fail một assertion | `@AfterEach`/extension vẫn được gọi; CI báo test fail |
| Cleanup chạy lại | Không còn resource | Không exception, state không đổi |
| Hai tests parallel | Hai test IDs khác nhau | Xóa A không ảnh hưởng B |
| SQL FK | Tạo parent/child | Cleanup child trước parent, không còn orphan |
| Async eventual write | Worker hoàn tất sau response | Await/cancel, cleanup sau, không xuất hiện lại |
| External API timeout | Kết quả commit/ACK không chắc chắn | Query trạng thái theo idempotency key rồi cleanup |
| Reactive repository | `Mono<Void>` delete | Có subscription và verify completion |
| Dữ liệu không tồn tại | Không có row/cache key | Cleanup idempotent và không fail |
| Cleanup DB throw | DB connection lỗi hoặc constraint fail | Test fail có diagnostic, resource khác vẫn được thử dọn |
| Crash trước `@AfterEach` | CI process ngừng đột ngột | Test namespace/container/TTL/janitor cleanup sau đó |

**Không dùng một test đơn lẻ trong process với fake để tuyên bố đã kiểm được database failover hoặc real payment compensation.** Những mục tiêu đó cần test environment riêng, có fault injection có kiểm soát và API thật trong sandbox.

## 13. Những lỗi hay gặp

| Sai lầm | Tác hại | Sửa |
|---|---|---|
| `@Transactional` trên test `RANDOM_PORT` và tin server write rollback | Tồn dư DB row | Dọn committed state theo test ID |
| DELETE trong `@AfterEach` bị outer test transaction rollback | Cleanup không có hiệu lực | `REQUIRES_NEW` hoặc `@Sql(ISOLATED)`; tránh outer tx khi không cần |
| Dùng `@DirtiesContext` thay DB cleanup | DB/broker vẫn bẩn | Cleanup thật hoặc isolated DB/container |
| Gọi reactive delete mà không subscribe | Không xóa gì | `StepVerifier.verifyComplete` |
| Xóa toàn bảng Redis/SQL shared | Ảnh hưởng test khác | Namespace/testKey độc lập |
| Dùng TTL làm cleanup duy nhất | Test kế tiếp gặp data cũ | Explicit cleanup + TTL backup |
| Dọn DB trước khi worker async hoàn tất | Worker ghi lại sau cleanup | Await/cancel rồi cleanup |
| Xóa parent trước child | FK violation | Xóa child trước hoặc cleanup transaction phù hợp |
| Tin `REQUIRES_NEW` rollback cùng outer | Row audit vẫn commit | Cleanup độc lập theo owner key |
| Gọi `deleteAll()` trên một repository mock | Không chứng minh DB state sạch | Integration test với DB thật |
| Không kiểm dữ liệu trước cleanup | False positive: chưa từng tạo resource | Verify create rồi verify cleanup |
| Nuốt exception cleanup | CI xanh dù rác còn | Fail rõ và log diagnostic |
| Reset fake/cache toàn cục trong parallel suite | Phá test khác | Test-scoped fake hoặc namespace |
| Truncate/DDL trong transaction và tin sẽ rollback | Database có implicit commit | Chỉ destructive reset trên isolated DB |
| Network timeout được hiểu là write thất bại | Retry tạo duplicate | Idempotency key và query state |
| Container tái sử dụng được coi là DB mới cho mọi test | Data bleed giữa test classes | Per-class schema/test ID, cleanup đúng lifecycle |

## 14. Checklist trước khi merge bài integration test

- [ ] Đã vẽ transaction boundary của test thread, HTTP server, reactive pipeline, service `REQUIRES_NEW` và external resources.
- [ ] Không suy luận rollback test có hiệu lực với server-side transaction.
- [ ] Mọi fixture/row/message/object test tạo ra đều có test-owned key.
- [ ] Có cleanup cho từng loại resource không thuộc DB transaction.
- [ ] `@AfterEach` được gọi đúng và cleanup **không nằm trong một transaction sắp rollback**.
- [ ] Nếu dùng `@Sql`, transaction mode/datasource/phase được cấu hình đúng.
- [ ] Nếu dùng reactive cleanup, Publisher được subscribe và verify completion.
- [ ] Nếu có async consumers, tôi đợi/cancel công việc trước cleanup.
- [ ] Cleanup idempotent; gọi hai lần không xóa dữ liệu ngoài scope.
- [ ] Resource tồn tại trước cleanup và được xác minh không còn sau cleanup.
- [ ] Dữ liệu có FK được xóa theo thứ tự an toàn.
- [ ] Chạy parallel không dùng chung fixed key hay reset shared resource.
- [ ] External payments/email dùng fake hoặc sandbox, không phát side effect thật.
- [ ] Không dùng `@DirtiesContext` thay cho xóa dữ liệu external.
- [ ] Cleanup failures được báo đỏ trên CI; không silent ignore.
- [ ] Dùng Testcontainers/schema riêng khi cần destructive reset hoặc production-like DB.
- [ ] Có TTL/janitor **giới hạn quyền** xử lý dữ liệu sót khi process crash.
- [ ] Đã chạy lại test nhiều lượt hoặc đổi thứ tự chạy để phát hiện leakage.
- [ ] Những gì test chứng minh được mô tả chính xác; không đánh đồng fake với integration thật.

**Kết luận:** Rollback là một cơ chế quản lý transaction **có phạm vi**, không phải chức năng “khôi phục toàn bộ hệ thống sau test”. Khi có HTTP thật, nested/independent transactions, async và external systems, cần **dữ liệu có chủ sở hữu + cleanup từng resource bằng boundary phù hợp + đối chiếu trạng thái sạch**. Hãy ưu tiên cô lập môi trường và thiết kế cleanup an toàn hơn là xóa bừa dữ liệu để test tạm thời xanh.

### Tài liệu chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications và RANDOM_PORT transaction boundaries](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — Test-managed Transactions, @BeforeTransaction/@AfterTransaction](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework — @Sql và transactionMode ISOLATED](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html)
- [Spring Framework — Transaction propagation REQUIRES_NEW](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Reactive transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)

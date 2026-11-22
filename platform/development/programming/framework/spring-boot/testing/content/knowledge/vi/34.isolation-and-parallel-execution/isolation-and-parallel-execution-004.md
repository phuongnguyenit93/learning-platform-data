# Database, schema, topic, queue và namespace riêng

## 1. Bài toán: test chạy song song nhưng dùng chung tài nguyên

Trong một hệ thống Spring Boot, hai bài kiểm thử có thể độc lập về mã Java nhưng vẫn tranh chấp cùng **database**, **schema**, **Kafka topic**, **consumer group**, **RabbitMQ queue/exchange**, **Redis keys**, **S3 prefix** hoặc **Kubernetes namespace**. Khi chạy từng bài một, mọi thứ có thể xanh. Khi chạy cả suite trên CI, các vấn đề sau xuất hiện:

- Test A xóa mọi rows của bảng trong khi test B đang assert dữ liệu vừa insert.
- Hai test dùng cùng khóa `order-1` và cùng database/schema, gây duplicate-key violation hoặc đọc nhầm kết quả.
- Test Kafka A lấy message do B publish; hai consumers dùng cùng `group.id` có thể chia partitions và khiến test kia không nhận được message.
- Hai bài RabbitMQ dùng một queue tên `test.queue`; một consumer của A lấy message của B, hoặc teardown của A xóa queue B đang dùng.
- Test Redis dùng `FLUSHDB`/`FLUSHALL` khiến cache của mọi suite khác biến mất.
- Test tạo schema riêng nhưng app vẫn dùng datasource có `search_path=public` nên mọi write tiếp tục dồn vào cùng bảng.
- Test có `@Transactional` nhưng một HTTP request, async task hoặc message listener chạy ở thread/transaction riêng; side effect không được rollback cùng test method.
- Hai CI jobs dùng cùng Kafka broker/RabbitMQ vhost nhưng cùng tên topic/queue; chạy độc lập trên máy dev vẫn ổn, chạy đồng thời bị va chạm.
- Teardown `DROP SCHEMA ... CASCADE`, xóa Kubernetes namespace hoặc xóa cloud bucket quá rộng; một job test vô tình phá tài nguyên của job khác.

Bài thuộc nhóm **Cách ly và chạy song song**, với đề mục **“Database, schema, topic, queue và namespace riêng”**. Mục tiêu không chỉ là thêm hậu tố UUID vào mọi tên, mà là xây **quy tắc ownership**, vòng đời tài nguyên, phạm vi đọc/ghi/xóa và cách kiểm tra tính cô lập khi nhiều test chạy thực sự song song.

Ví dụ chính dùng **Java 17+**, **Spring Boot 3.3.5**, **JUnit Jupiter**, **Testcontainers PostgreSQL 16** và `JdbcTemplate`. Phần Kafka/RabbitMQ/Redis/S3/Kubernetes có API/snippets riêng, được đánh dấu là **mở rộng** vì không nằm trong project Gradle PostgreSQL tối giản.

### Kết quả học tập

1. Phân biệt database-per-suite, schema-per-class và namespace-key-per-method.
2. Sinh một `runId` an toàn, duy nhất và phù hợp cú pháp từng hệ thống.
3. Kết nối PostgreSQLContainer bằng `@Testcontainers`, `@Container` và Spring Boot `@ServiceConnection`.
4. Đảm bảo truy vấn SQL luôn có `test_namespace` và cleanup chỉ xóa dữ liệu mình sở hữu.
5. Hiểu vì sao `@Transactional`, `@DirtiesContext`, `@Sql` và `@BeforeEach` không phải giải pháp cô lập mọi external side effect.
6. Isolate Kafka topic, consumer group, retry/DLT topics, offsets và transactional IDs.
7. Isolate RabbitMQ queue, exchange, binding, vhost khi cần; chọn exclusive/auto-delete đúng mục đích.
8. Isolate Redis keys bằng prefix/TTL và không dùng lệnh xóa toàn bộ shared datastore.
9. Tổ chức lifecycle CI/parallel JUnit, resource lock, cleanup khi test fail và orphan scavenging.
10. Phân biệt isolation của **test input**, **processing**, **output** và **infrastructure**.

## 2. Mức cô lập: càng mạnh càng tốn tài nguyên

| Mức | Ví dụ | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| Process/container riêng | PostgreSQLContainer cho từng test class | Rất ít va chạm giữa classes | Startup tốn thời gian/tài nguyên |
| Database riêng | `it_db_abc...` trên một PostgreSQL server | Cô lập tables/schema/migrations | Cần quyền tạo/xóa database; còn chia sẻ server capacity |
| Schema riêng | `it_abc...` trong cùng database | Tách object names; migration theo schema | Phải cấu hình search_path/Flyway/JPA đúng, tránh connection leakage |
| Row namespace riêng | `test_namespace` trong shared tables | Rẻ, phù hợp parallel methods | Mọi query/write/cleanup phải filter đúng namespace |
| Logical resource riêng | Kafka topic, Rabbit queue/exchange | Ngăn test lấy message của nhau | Metadata broker, quotas, deletion và consumer config cần quản lý |
| Prefix riêng | Redis key `it:runId:...`; S3 `it/runId/...` | Không cần tạo datastore mới | Xóa prefix phải đúng ownership và có TTL |
| Infrastructure namespace | K8s namespace + labels | Cô lập deploy/service/config và RBAC | Chi phí vận hành; namespace chưa phải security boundary tuyệt đối |

**Một project thường dùng nhiều lớp đồng thời:** PostgreSQL container riêng cho một test class, bên trong đó từng test method dùng row namespace; Kafka broker Testcontainer có thể chia sẻ trong suite nhưng topic và group riêng cho từng scenario; RabbitMQ dùng queue/exchange riêng; Redis dùng key prefix có TTL.

### Bốn câu hỏi trước khi chọn

1. Test có làm thay đổi **global schema**, migrations hoặc server settings không? Nếu có, row namespace không đủ.
2. Test có consumer tự động chạy hoặc async worker không? Nếu có, cần tách routing/subscriptions và chờ completion trước cleanup.
3. CI có chạy nhiều forks, modules, machines hoặc pull requests đồng thời không? Nếu có, counter `1,2,3` trong JVM không đủ độc nhất.
4. Có quyền tạo/xóa tài nguyên thật không? Nếu không, ưu tiên test-owned prefix/group trên môi trường dành riêng hoặc dùng Testcontainers.

## 3. Đặt tên tài nguyên phải vừa unique vừa hợp lệ

UUID v4 sinh trong mỗi test run có xác suất trùng cực thấp; dùng **32 ký tự hex lowercase** giúp xây tên ổn định, không có dấu gạch chéo, dấu cách hay ký tự quote. Tuy nhiên từng hệ thống khác nhau về giới hạn tên:

| Loại | Ví dụ | Lưu ý |
| --- | --- | --- |
| PostgreSQL schema | `it_012345...` | Tối đa 63 bytes cho identifier mặc định; lowercase + underscore |
| PostgreSQL row namespace | `run_012345...` | Là dữ liệu tham số SQL, không phải identifier |
| Kafka topic | `it.orders.012345...` | Không lẫn với Kafka internal topic; tên ngắn, chỉ chữ/số/dot/hyphen |
| Kafka consumer group | `it.consumer.012345...` | Group riêng để tránh chia partition/offset |
| Rabbit exchange | `it.exchange.012345...` | Tránh reserved prefix `amq.` |
| Rabbit queue | `it.queue.012345...` | Queue riêng, lifecycle/auto-delete có chủ đích |
| Redis key prefix | `it:012345...:` | Không dùng `FLUSHALL` trên shared Redis |
| S3/object prefix | `it/012345.../` | Prefix là phân đoạn object key, không phải bucket security boundary |
| Kubernetes namespace | `it-012345...` | DNS label lowercase/hyphen; quotas/RBAC và labels riêng |

**Unique name không phải isolation tuyệt đối.** Nếu một reader scan toàn bộ database, một consumer subscribe `it.orders.*`, hoặc một cleanup xóa tất cả topics bắt đầu bằng `it.` thì test vẫn ảnh hưởng nhau. Mọi đường đọc, ghi, subscribe và cleanup phải dùng đúng namespace và ownership.

## 4. Vòng đời tài nguyên và ownership

```text
CI run / test class / test method
           |
   Generate runId (unique)
           |
   Allocate exact resources
   - DB/container/schema or row namespace
   - topic + group
   - exchange + queue + binding
   - cache prefix / object prefix
           |
   Prepare fixture -> start consumer -> wait ready
           |
   Execute -> await bounded results -> assertions
           |
   Stop listeners/consumers
           |
   Cleanup ONLY resources owned by runId
           |
   Close clients/containers, record orphan cleanup if needed
```

Nguyên tắc:

- Một resource có **owner** rõ (`runId`, CI build ID/label, TTL).
- **Create before use**, không assume topic/schema/queue có sẵn từ lần chạy cũ.
- **Observe readiness**: broker partition assignment, Rabbit queue binding, DB migrations hoàn tất, K8s Ready status.
- **Delete after consumers stop**; tránh cleanup trong khi worker vẫn xử lý.
- **Cleanup in finally/@AfterEach/@AfterAll** để thử dọn cả khi assertion fail.
- Nếu process bị kill cứng, lifecycle hooks không chạy: cần TTL, labels, orphan garbage collection ở môi trường thử nghiệm.
- Không bao giờ xóa tài nguyên nằm ngoài prefix/label của run mình.
- Không ghi secrets/PII vào tên topic/namespace, logs hay exception messages.

## 5. Project runnable: Java 17 + Boot 3.3.5 + PostgreSQL Testcontainers

Ví dụ chạy một PostgreSQLContainer **riêng cho test class**, đồng thời mọi test method ghi rows vào cùng bảng `it_orders` nhưng dùng **row namespace riêng**. Đây là hai lớp cô lập có chủ đích:

- **Class/suite isolation:** Testcontainers cung cấp database instance riêng, giảm ảnh hưởng với ứng dụng khác.
- **Method isolation:** `test_namespace` đi kèm mọi record và mọi truy vấn/cleanup; các methods chạy song song không thấy rows của nhau.

Cây thư mục:

```text
isolation-test-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/isolation/
│   ├── IsolationApplication.java
│   ├── IsolationNames.java
│   └── OrderStore.java
└── src/test/
    ├── java/com/example/isolation/
    │   ├── IsolationNamesTest.java
    │   └── OrderStoreIsolationTest.java
    └── resources/
        ├── application-test.yml
        ├── schema.sql
        └── junit-platform.properties
```

**Điều kiện chạy:** Docker/Podman-compatible Testcontainers environment đã cấu hình; PostgreSQL image có thể được tải; CI cần tài nguyên để khởi tạo container. Không có Docker thì network integration tests **không tự chuyển thành H2** hoặc được coi là đã PASS.

## 6. Gradle dependencies

### settings.gradle

```groovy
rootProject.name = 'isolation-test-lab'
```

### build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

- `spring-boot-starter-jdbc`: `JdbcTemplate`, DataSource và JDBC transaction support.
- `postgresql`: PostgreSQL JDBC driver.
- `spring-boot-starter-test`: JUnit Jupiter, AssertJ, Spring TestContext.
- `spring-boot-testcontainers`: `@ServiceConnection` support trong Spring Boot 3.3.
- `org.testcontainers:junit-jupiter`: JUnit Testcontainers extension và `@Container`.
- `org.testcontainers:postgresql`: `PostgreSQLContainer`.
- `junit-platform-launcher`: tương thích Gradle/JUnit Platform.

Không ghim Testcontainers version thủ công trong project này; Spring Boot 3.3.5 dependency management quyết định release tương thích. Testcontainers PostgreSQL cần Docker daemon/engine hoạt động, nhưng không cần cài PostgreSQL server vào máy local.

## 7. Application root

`src/main/java/com/example/isolation/IsolationApplication.java`:

```java
package com.example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }
}
```

Vì project chỉ có JDBC starter, ứng dụng không mở Servlet server. `@SpringBootTest` sẽ load repository và DataSource thật trong test; không có HTTP endpoint hoặc scheduled task làm thay đổi rows ngoài ý muốn.

## 8. IsolationNames: một nguồn tạo ID an toàn cho mọi loại resource

`src/main/java/com/example/isolation/IsolationNames.java`:

```java
package com.example.isolation;

import java.util.Objects;
import java.util.UUID;

public final class IsolationNames {

    private IsolationNames() {
    }

    public static String newRunId() {
        return UUID.randomUUID()
                .toString()
                .replace("-", "");
    }

    public static Names forRunId(String runId) {
        Objects.requireNonNull(runId, "runId");

        if (!runId.matches("[0-9a-f]{32}")) {
            throw new IllegalArgumentException(
                    "runId must be 32 lowercase hex characters");
        }

        return new Names(
                "it_" + runId,
                "run_" + runId,
                "it.orders." + runId,
                "it.consumer." + runId,
                "it.exchange." + runId,
                "it.queue." + runId,
                "it:" + runId + ":",
                "it/" + runId + "/",
                "it-" + runId);
    }

    public record Names(
            String postgresSchema,
            String rowNamespace,
            String kafkaTopic,
            String kafkaConsumerGroup,
            String rabbitExchange,
            String rabbitQueue,
            String redisPrefix,
            String objectPrefix,
            String kubernetesNamespace
    ) {
    }
}
```

Hàm `forRunId(...)` chỉ chấp nhận **32 ký tự hex lowercase**, do đó các tên được tạo không chứa dấu quote, khoảng trắng, slash lạ hoặc SQL punctuation tùy ý. Đặc biệt, `postgresSchema` dài 35 ký tự (3 + 32), nằm dưới giới hạn identifier PostgreSQL mặc định 63 bytes.

**Không lấy raw user input để ghép vào tên schema/SQL identifier**. Các SQL parameter bind như `?` chỉ áp dụng cho **values**, không áp dụng trực tiếp cho table/schema names. Nếu cần tạo schema động, phải kiểm soát identifier bằng allowlist/safe generator như ở đây và cấp quyền hạn chế cho test DB.

### Vì sao không dùng currentTimeMillis() làm tên?

Ở parallel tests hoặc nhiều CI processes, milliseconds có thể trùng và thread scheduling không đảm bảo uniqueness. UUID v4 ngẫu nhiên tránh phụ thuộc timestamp. Nếu cần truy vết CI run, lưu `runId` thành một test report/log label riêng; không nhồi branch name hoặc email vào tên resource vì có ký tự lạ, PII và giới hạn độ dài.

### Nhiều loại tên từ cùng một runId

Dùng một runId giúp trace và cleanup cùng một scenario. Nhưng prefix mỗi loại khác nhau để tránh nhầm:

```text
runId                 0123456789abcdef0123456789abcdef
postgresSchema        it_0123456789abcdef0123456789abcdef
rowNamespace          run_0123456789abcdef0123456789abcdef
kafkaTopic            it.orders.0123456789abcdef0123456789abcdef
kafkaConsumerGroup    it.consumer.0123456789abcdef0123456789abcdef
rabbitExchange        it.exchange.0123456789abcdef0123456789abcdef
rabbitQueue           it.queue.0123456789abcdef0123456789abcdef
redisPrefix           it:0123456789abcdef0123456789abcdef:
objectPrefix          it/0123456789abcdef0123456789abcdef/
kubernetesNamespace   it-0123456789abcdef0123456789abcdef
```

Đây là **ví dụ minh họa từ một runId cố định**, không phải stdout được chụp từ Gradle. Khi gọi `newRunId()`, các giá trị sẽ khác mỗi lần chạy.

## 9. OrderStore: luôn query và cleanup bằng namespace

`src/main/java/com/example/isolation/OrderStore.java`:

```java
package com.example.isolation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {

    private final JdbcTemplate jdbc;

    public OrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void save(
            String namespace,
            String orderId,
            String state) {

        jdbc.update("""
                INSERT INTO it_orders
                    (test_namespace, order_id, state)
                VALUES (?, ?, ?)
                """, namespace, orderId, state);
    }

    public long count(String namespace) {
        Long value = jdbc.queryForObject("""
                SELECT COUNT(*)
                FROM it_orders
                WHERE test_namespace = ?
                """, Long.class, namespace);

        return value == null ? 0L : value;
    }

    public String state(
            String namespace,
            String orderId) {
        return jdbc.queryForObject("""
                SELECT state
                FROM it_orders
                WHERE test_namespace = ?
                  AND order_id = ?
                """, String.class, namespace, orderId);
    }

    public int deleteNamespace(String namespace) {
        return jdbc.update("""
                DELETE FROM it_orders
                WHERE test_namespace = ?
                """, namespace);
    }
}
```

Quan trọng nhất không phải dùng `UUID` mà là **mỗi đường truy vấn đều truyền namespace**. Nếu test A và B lưu `order_id="ORDER-1"` ở hai namespaces khác nhau, composite primary key cho phép cả hai tồn tại mà không đụng nhau.

`deleteNamespace` dùng `WHERE test_namespace = ?`. Nó **không** dùng `DELETE FROM it_orders` không điều kiện, không `TRUNCATE` và không xóa dữ liệu test khác. Các bind parameters được JDBC thực hiện an toàn cho values.

### Khi nào row namespace không đủ?

Nếu code production query `SELECT * FROM it_orders` không filter namespace, test chỉ sửa repository ở đây vẫn có nguy cơ đọc nhầm. Với hệ thống multi-tenant phải có tenant isolation thực (RLS, tenant-scoped repository, schema per tenant...). Trong một test integration, hãy kiểm tra **tất cả** read/write/delete paths của subject under test chứ không chỉ một repository mẫu.

Với migrations/DDL, một cột namespace **không cách ly** schema changes hay global sequences; dùng schema/container/database riêng.

## 10. Test-only SQL schema và profile

`src/test/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS it_orders (
    test_namespace VARCHAR(80) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    state VARCHAR(40) NOT NULL,
    PRIMARY KEY (test_namespace, order_id)
);

CREATE INDEX IF NOT EXISTS idx_it_orders_namespace
    ON it_orders (test_namespace);
```

`src/test/resources/application-test.yml`:

```yaml
spring:
  main:
    web-application-type: none
  sql:
    init:
      mode: always
```

`spring.sql.init.mode=always` đảm bảo Spring Boot thực thi `schema.sql` trong test PostgreSQL, không chỉ khi DataSource được xem là embedded. Hệ thống thật có thể dùng Flyway/Liquibase thay cho `schema.sql`; **không chạy đồng thời nhiều schema initialization mechanisms** trên cùng objects khi chưa xác định ordering/ownership.

**Chỉ dùng bảng demo trong test database.** Không bật `spring.sql.init.mode=always` với một script destructive cho production datasource. Với Flyway, hãy apply migrations vào đúng database/schema test và dùng chính migrations production khi cần bắt lỗi migration compatibility.

## 11. Bật JUnit parallel một cách có kiểm soát

`src/test/resources/junit-platform.properties`:

```properties
# Bài tích hợp dùng @Testcontainers/@Container phải chạy tuần tự trong JUnit.
# Test đồng thời hai writer vẫn được kiểm tra bằng ExecutorService trong một @Test.
junit.jupiter.execution.parallel.enabled=false
```

Cấu hình runnable ở trên **tắt JUnit parallel** vì ví dụ dùng extension Testcontainers JUnit Jupiter (`@Testcontainers`/`@Container`), hiện chỉ hỗ trợ thực thi tuần tự. Đặt `@Execution(CONCURRENT)` trên lớp dùng extension đó hoặc bật concurrent methods/classes toàn suite có thể gây race ở vòng đời container và kết quả không được hỗ trợ. Bài vẫn chứng minh truy cập đồng thời bằng hai task `ExecutorService` trong một phương thức `@Test` chạy tuần tự ở tầng JUnit.

Với những test thuần JUnit không dùng extension này, có thể cấu hình parallel ở suite riêng đã được cô lập; `Gradle maxParallelForks`, modules và CI jobs vẫn có thể tăng concurrency ở các tầng khác. Không biến parallel execution của extension Testcontainers thành một cấu hình runnable mặc định.

### Chạy song song không đồng nghĩa không có race

Mỗi test có namespace riêng giúp tránh đụng rows, nhưng app còn có thể chứa static mutable singletons, caches không theo namespace, shared temp files, Kafka consumer group, fixed ports hoặc server-side global state. Chỉ bật parallel khi đã xác định mỗi dependency được cô lập hoặc khóa.

## 12. @SpringBootTest + PostgreSQLContainer + @ServiceConnection

`src/test/java/com/example/isolation/OrderStoreIsolationTest.java`:

```java
package com.example.isolation;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderStoreIsolationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    OrderStore store;

    // JUnit PER_METHOD mặc định: mỗi test có instance/list riêng.
    private final List<String> ownedNamespaces =
            new CopyOnWriteArrayList<>();

    private String ownedNamespace() {
        String ns = IsolationNames
                .forRunId(IsolationNames.newRunId())
                .rowNamespace();
        ownedNamespaces.add(ns);
        return ns;
    }

    @AfterEach
    void cleanupOwnedRows() {
        // Chỉ delete rows thuộc test method hiện tại.
        for (String ns : ownedNamespaces) {
            store.deleteNamespace(ns);
        }
    }

    @Test
    void identicalOrderIdsInDifferentNamespacesDoNotClash() {
        String first = ownedNamespace();
        String second = ownedNamespace();

        store.save(first, "ORDER-1", "NEW");
        store.save(second, "ORDER-1", "PAID");

        assertEquals("NEW", store.state(first, "ORDER-1"));
        assertEquals("PAID", store.state(second, "ORDER-1"));
        assertEquals(1L, store.count(first));
        assertEquals(1L, store.count(second));
    }

    @Test
    void cleanupOfOneNamespaceDoesNotDeleteAnother() {
        String first = ownedNamespace();
        String second = ownedNamespace();

        store.save(first, "ORDER-2", "READY");
        store.save(second, "ORDER-2", "READY");

        assertEquals(1, store.deleteNamespace(first));
        assertEquals(0L, store.count(first));
        assertEquals(1L, store.count(second));
    }

    @Test
    void duplicateOrderIdWithinSameNamespaceIsRejected() {
        String ns = ownedNamespace();

        store.save(ns, "ORDER-3", "NEW");

        assertThrows(
                DataIntegrityViolationException.class,
                () -> store.save(ns, "ORDER-3", "NEW"));

        assertEquals(1L, store.count(ns));
    }

    @Test
    void concurrentWritersCannotSeeEachOthersRows()
            throws Exception {
        String first = ownedNamespace();
        String second = ownedNamespace();

        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Void> writeFirst = () -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("start timed out");
            }
            for (int i = 0; i < 20; i++) {
                store.save(first, "A-" + i, "READY");
            }
            return null;
        };

        Callable<Void> writeSecond = () -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("start timed out");
            }
            for (int i = 0; i < 20; i++) {
                store.save(second, "B-" + i, "READY");
            }
            return null;
        };

        try {
            Future<Void> left = pool.submit(writeFirst);
            Future<Void> right = pool.submit(writeSecond);

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();

            left.get(15, TimeUnit.SECONDS);
            right.get(15, TimeUnit.SECONDS);

            assertEquals(20L, store.count(first));
            assertEquals(20L, store.count(second));
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

**Có 4 phương thức `@Test`** trong class này. Chúng yêu cầu Docker/Testcontainers và PostgreSQL thật. `@ServiceConnection` cho phép Boot tự đưa JDBC connection details từ PostgreSQLContainer vào application context, không hardcode JDBC port, username hoặc password. `@Container` cho JUnit Testcontainers extension quản lý lifecycle container.

### Vì sao @DirtiesContext(AFTER_CLASS)?

Testcontainers extension thường dừng static `@Container` sau test class, nhưng Spring TestContext có cache có thể giữ `ApplicationContext`/DataSource cũ cho một test class tiếp theo. `@DirtiesContext(classMode=AFTER_CLASS)` bảo đảm context không tiếp tục được tái sử dụng sau khi class này hoàn tất. Nó **không** tự xóa các rows hoặc topic/queue ở một hệ thống bên ngoài: nhiệm vụ đó vẫn thuộc cleanup riêng.

### Vì sao không @Transactional trên test class?

Test-managed `@Transactional` rollback transaction trong test thread, nhưng Kafka consumers, Rabbit listeners, `@Async` hoặc request HTTP khác thread/transaction không tự được rollback cùng nó. Trong demo, không dùng test transaction để bao trùm mọi work; mỗi method dùng namespace và cleanup. Khi cần test transaction semantics của repository, viết test riêng có commit/rollback expectations tường minh.

### Những giới hạn của @AfterEach cleanup

`@AfterEach` chạy khi assertion thông thường fail, nhưng không chạy nếu JVM bị kill cứng hoặc máy CI mất điện. Test-owned namespace trong container tạm sẽ biến mất khi container bị dọn; với shared broker/cloud service cần **TTL, labels và sweeper** để xử lý orphan resources.

Trong test `concurrentWritersCannotSeeEachOthersRows`, `shutdownNow()` gửi interruption nhưng không cam kết mọi task đã dừng ngay nếu future timeout; production-grade test helper nên await termination hoặc cancel/join futures trước khi cleanup. Bộ minh họa chờ cả hai futures thành công trong normal path; timeout/failure path phải được xử lý cẩn thận nếu mở rộng thành một stress suite.

## 13. Unit tests cho tên namespace và thuộc tính độc lập

`src/test/java/com/example/isolation/IsolationNamesTest.java`:

```java
package com.example.isolation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IsolationNamesTest {

    private static final String A =
            "0123456789abcdef0123456789abcdef";

    private static final String B =
            "fedcba9876543210fedcba9876543210";

    @Test
    void generatedRunIdIsSafeLowercaseHex() {
        String runId = IsolationNames.newRunId();

        assertTrue(runId.matches("[0-9a-f]{32}"));
    }

    @Test
    void postgresSchemaIsShortAndSqlIdentifierSafe() {
        String schema =
                IsolationNames.forRunId(A).postgresSchema();

        assertTrue(schema.matches("[a-z][a-z0-9_]*"));
        assertTrue(schema.length() <= 63);
    }

    @Test
    void kafkaAndRabbitResourcesUseDistinctPrefixes() {
        IsolationNames.Names names =
                IsolationNames.forRunId(A);

        assertTrue(names.kafkaTopic().startsWith("it.orders."));
        assertTrue(names.kafkaConsumerGroup()
                .startsWith("it.consumer."));
        assertTrue(names.rabbitQueue().startsWith("it.queue."));
        assertTrue(names.rabbitExchange()
                .startsWith("it.exchange."));
        assertNotEquals(
                names.rabbitQueue(),
                names.rabbitExchange());
    }

    @Test
    void redisS3AndKubernetesNamesUseSafePatterns() {
        IsolationNames.Names names =
                IsolationNames.forRunId(A);

        assertTrue(names.redisPrefix().startsWith("it:"));
        assertTrue(names.redisPrefix().endsWith(":"));
        assertTrue(names.objectPrefix().startsWith("it/"));
        assertTrue(names.objectPrefix().endsWith("/"));
        assertTrue(names.kubernetesNamespace()
                .matches("[a-z0-9]+(-[a-z0-9]+)*"));
    }

    @Test
    void runIdCannotContainInjectedSqlOrPathCharacters() {
        assertThrows(
                IllegalArgumentException.class,
                () -> IsolationNames.forRunId(
                        "x; DROP SCHEMA public CASCADE"));
    }

    @Test
    void twoRunIdsProduceDifferentNamespaces() {
        assertNotEquals(
                IsolationNames.forRunId(A).rowNamespace(),
                IsolationNames.forRunId(B).rowNamespace());
        assertNotEquals(
                IsolationNames.forRunId(A).kafkaTopic(),
                IsolationNames.forRunId(B).kafkaTopic());
    }
}
```

Class này có **6 phương thức `@Test`** không cần Docker; tổng project chính có **10 test methods** (4 integration + 6 unit). Các tests chỉ xác nhận naming contract, không chứng minh schema/topic/queue tương ứng đã được tạo ngoài đời thực.

### Tránh test uniqueness bằng thời gian

Test `twoRunIdsProduceDifferentNamespaces` dùng **hai runIds đầu vào cố định khác nhau**; nó deterministic. Test `generatedRunIdIsSafeLowercaseHex` kiểm tra format của UUID-derived string, không dựa vào một giá trị random cụ thể. Với phân phối xác suất của UUID v4, không tuyên bố “tuyệt đối không bao giờ trùng”, nhưng đây là lựa chọn thực tế phù hợp cho test runs.

## 14. Cách chạy, điều kiện môi trường và kết quả kỳ vọng

Nếu repository đã có Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.isolation.IsolationNamesTest'
./gradlew test --tests 'com.example.isolation.OrderStoreIsolationTest'
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Khi chưa có Wrapper nhưng máy đã cài Gradle tương thích:

```bash
gradle test
```

JUnit reports thường ở:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

**Chưa thực thi Gradle hay Docker trong quá trình viết bài này.** Bộ source có 10 `@Test` và expected assertions như mô tả, nhưng **không thể khẳng định 10 tests PASS** nếu chưa chạy suite và đọc reports thật. Nếu CI không có Docker permission, integration tests fail ngay ở container setup; không gọi đó là lỗi SQL isolation logic.

### Điều gì được kiểm chứng bởi project?

| Nhóm | Được test | Chưa được test |
| --- | --- | --- |
| RunId/naming | Format, prefix, khác biệt giữa two IDs | Kafka broker/K8s API chấp nhận resource thực |
| PostgreSQL | Per-class Testcontainer, rows theo namespace, unique key | Schema-per-class provisioning và migration đa schema |
| Method-level isolation | Same order ID khác namespace, owner-only delete | Production multi-tenant security |
| Parallel access | 2 workers ghi đồng thời 20 rows mỗi namespace | Tải lớn, chaos, long-term contention |
| Cleanup | Owner-specific SQL delete | Kill -9 cleanup, shared cloud resources |
| Kafka/Rabbit/Redis/S3 | Mẫu kiến trúc ở các mục sau | Không nằm trong runnable Gradle dependencies |

## 15. Ba cách cách ly PostgreSQL: database, schema và rows

### 15.1. Database-per-suite

Một `PostgreSQLContainer` riêng như project là cách dễ hiểu: mọi class có database instance riêng, các tables/migrations không chia với suite khác. Nhược điểm là startup, memory và Docker limits. Nếu có 100 test classes chạy cùng lúc, 100 containers có thể làm CI chậm hoặc sập.

Có thể dùng một container **cho một test module** với database riêng per class. Nhưng khi chuyển sang shared container, cần schema/database namespace hợp lệ, schema migrations đúng và cleanup; đừng chuyển một biến `static` sang global singleton rồi giả định isolation vẫn tự tồn tại.

### 15.2. Schema-per-class

Tạo một schema riêng, ví dụ `it_0123456789abcdef0123456789abcdef`, cho từng test class. Khi provisioning bằng JDBC:

```java
String schema =
        IsolationNames.forRunId(runId).postgresSchema();

try (Connection connection = adminDataSource.getConnection();
     Statement statement = connection.createStatement()) {

    statement.execute("CREATE SCHEMA \"" + schema + "\"");
}
```

**Đây là snippet mở rộng, không phải phần project runnable chính**: cần `runId`, `adminDataSource` và imports `java.sql.Connection/Statement` đã được cấu hình; schema phải được tạo **trước** khi app DataSource/Flyway/JPA tạo objects. Tên `schema` được sinh từ allowlisted UUID hex nên không có SQL injection hay identifier quoting bất ngờ.

Sau khi tạo, cấu hình **dedicated DataSource** của test class với schema phù hợp: ví dụ PostgreSQL JDBC `currentSchema`, Hikari `schema` hoặc connection-init SQL; dùng đúng cách cho mỗi connection pool. Nếu dùng Flyway/Liquibase, cấu hình target schemas/default schema, migrations và history table đúng, nếu dùng JPA thì cấu hình default schema/tenant routing phù hợp.

**Bẫy search_path:** gọi `SET search_path=...` một lần trên connection A không có nghĩa connection B của Hikari pool sẽ dùng schema ấy. Hơn nữa một connection được trả vào pool có thể giữ session state nếu không reset đúng, khiến test khác nhìn nhầm schema. Ưu tiên datasource/pool riêng theo schema và kiểm tra actual `current_schema()` ngay trong integration test.

### 15.3. Row namespace-per-method

Nếu mọi tests có thể dùng cùng schema, thêm `test_namespace` vào composite PK/WHERE clauses như project chính. Đây là lựa chọn rẻ cho test song song. Nhưng cần cảnh giác:

- Một câu lệnh `TRUNCATE it_orders` vẫn xóa mọi test namespaces.
- Query thiếu `WHERE test_namespace = ?` vẫn đọc dữ liệu test khác.
- Unique key chỉ trên `order_id`, không có namespace, vẫn collision.
- Global sequences, triggers hoặc singleton caches có thể được chia sẻ.
- Cleanup ở `@BeforeEach` bằng `DELETE FROM it_orders` không an toàn.
- Nếu service có connection pooling và tenant context dạng ThreadLocal, phải truyền đúng context xuyên HTTP/async tasks.

### So sánh nhanh

| Yêu cầu | Chọn cách |
| --- | --- |
| Kiểm tra DDL/migrations/schema structure | Database/schema riêng |
| Kiểm tra business queries đa luồng | Row namespace trong bảng, nếu code hỗ trợ |
| Kiểm tra multi-tenant behavior | Test tenant isolation thật, không chỉ đổi test ID |
| Kiểm tra transaction rollback trên PostgreSQL | Real PostgreSQL test DB và assertions commit/rollback |
| Tối ưu chi phí nhiều test methods | Shared container + per-method namespace |
| Đòi sạch hoàn toàn từng class | Fresh database/container, chấp nhận cost |

## 16. @Transactional không thay thế resource isolation

Một `@Transactional` trên JUnit method có thể rollback các JDBC writes thực hiện trong **cùng test-managed transaction**; điều này hữu ích cho repository tests đơn luồng. Nhưng nó **không** có quyền rollback:

- Message đã publish lên Kafka hoặc RabbitMQ.
- HTTP call xử lý trên thread/server khác.
- Job/step transaction của Spring Batch.
- `@Async` listener chạy executor khác.
- Redis writes qua client không tham gia JDBC transaction.
- Object trên S3/blob storage.
- Schema/table DDL tùy DB/transaction semantics.
- Một service được gọi từ HTTP test qua real server và tự commit.

Do đó cần nghĩ về **transaction scope** và **resource scope** riêng biệt. Với integration tests có async/external operations, dùng test DB/schema/namespace riêng và cleanup tương ứng; đừng chỉ thêm `@Rollback` rồi coi data không thể rò.

### @Sql và scripts cleanup

`@Sql` rất hữu ích để setup fixture bằng SQL trong test DB. Tuy nhiên, một `DELETE FROM orders` trong @Sql after script vẫn ảnh hưởng tất cả tests dùng chung bảng. Nếu script có cleanup, phải parameterize theo namespace hoặc dùng schema/database riêng mà test sở hữu. `@SqlConfig(transactionMode=ISOLATED)` liên quan transaction mode của script, **không** tạo namespace isolation tự động.

## 17. Spring TestContext cache, @DirtiesContext và @DynamicPropertySource

Spring TestContext cache thường tái sử dụng `ApplicationContext` giữa những classes có cấu hình tương đương để giảm startup cost. Điều này có lợi về tốc độ, nhưng có nguy cơ khi bean giữ URL của một Testcontainer đã shutdown hoặc dynamic property thay đổi giữa classes.

Các điểm cần hiểu:

1. `@Container static` do JUnit Testcontainers extension quản lý theo test class; không chắc container còn sống khi một cached context được sử dụng lại ở class khác.
2. `@ServiceConnection` có thể cấu hình DataSource connection details từ container; đổi container khác thì context nên được refresh đúng vòng đời.
3. `@DirtiesContext(AFTER_CLASS)` buộc context không được cache dùng lại sau class, **không thay thế DB cleanup**.
4. `@DynamicPropertySource` là cách gắn dynamic endpoint vào Spring Environment khi không dùng service connections; nó cũng phải gắn với context lifecycle, không phải biến JVM-global cần update giữa methods.
5. Nếu container là **shared singleton** across classes/modules, quản lý lifecycle ở một test fixture có ownership rõ và bảo đảm context/properties không bị cache trỏ endpoint cũ.
6. Đừng sử dụng cùng một `spring.kafka.bootstrap-servers`/`spring.rabbitmq.addresses` trỏ broker production trong test profile.
7. Một CI job khác có thể chạy ở process khác, nên Spring context cache không đủ tạo isolation cross-process.

**Chú ý:** `@DirtiesContext` thường làm suite chậm nếu lạm dụng. Với row namespaces đủ an toàn và container sống đúng scope, không cần đánh dấu dirty trên mọi method. Dùng khi thật sự cần reset Spring bean state/context, không dùng như “dọn Kafka topic” giả.

## 18. Kafka: cần topic riêng và consumer group riêng

Kafka có hai namespace vận hành khác nhau:

- **Topic**: giữ records/partitions; các tests cùng topic sẽ thấy chung log dữ liệu.
- **Consumer group**: quyết định partition assignment và committed offsets của một nhóm consumers. Hai tests dùng cùng group có thể chia partitions hoặc tạo rebalance lẫn nhau; hai groups khác nhau trên cùng topic đều có thể đọc log từ topic ấy theo offset policies.

Vì vậy, với parallel tests đòi **không chạm message của nhau**, nên tách **cả topic và group** nếu khả thi.

```text
Test A:
  topic = it.orders.runA
  group = it.consumer.runA
  producer A --> topic A --> consumer A

Test B:
  topic = it.orders.runB
  group = it.consumer.runB
  producer B --> topic B --> consumer B
```

Tên trên là sơ đồ, không dùng trực tiếp vào production. Trong project naming, cả topic và group được sinh từ `IsolationNames.forRunId(...)` với runId hex.

### AdminClient tạo topic khi chạy test

Mẫu Java sau cần dependency `spring-kafka` hoặc `org.apache.kafka:kafka-clients`, Kafka broker thử nghiệm và imports Apache Kafka Admin API; **không nằm trong project PostgreSQL runnable**:

```java
String topic =
        IsolationNames.forRunId(runId).kafkaTopic();

try (AdminClient admin = AdminClient.create(
        Map.of(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            bootstrapServers))) {

    admin.createTopics(
            List.of(new NewTopic(topic, 1, (short) 1)))
        .all()
        .get(10, TimeUnit.SECONDS);
}
```

Đây là snippet cần `runId`, `bootstrapServers`, `AdminClient`, `AdminClientConfig`, `NewTopic`, `List`, `Map`, `TimeUnit`. Replication factor 1 phù hợp **single-broker test**, không phải production cluster. Sau khi consumer đã đóng/stop, test có thể gọi `deleteTopics(...)` trên **chính topic ấy** và chờ/poll deletion; Kafka topic deletion có thể bất đồng bộ hoặc bị chặn bởi broker policy.

### @KafkaListener và dynamic topic

`@KafkaListener(topics = "...")` thường resolve tên topic khi Spring context/consumer container được tạo. Không thể chỉ đổi một property sau khi context khởi tạo rồi mặc định listener tự chuyển sang topic mới cho test method tiếp theo.

Cách an toàn:

- Tạo topic riêng **trước** khi listener container bắt đầu.
- Bind tên topic và group vào Spring test context riêng ở thời điểm initialization; hoặc dùng programmatic `ConcurrentMessageListenerContainer` với properties của test.
- Với `@EmbeddedKafka`, hiểu rằng broker có thể được share giữa tests; chỉ cách ly topic/group chứ không suy “embedded” là mọi test tự độc lập.
- Đợi listener có partition assignment trước khi publish, thay vì sleep cố định.
- Dùng correlation ID/test-specific headers khi assert consumed messages.
- Chỉ dọn topic/consumer group do test tạo.

**Nhớ các topic phụ:** retry topics, DLT/DLQ, changelog/state-store topics của Kafka Streams cũng phải có prefix/ownership tách biệt. Với producer transactional, `transactional.id` cũng cần unique để tránh producer fencing giữa tests.

### Offsets và auto.offset.reset

Một group mới không có committed offsets thường tuân theo `auto.offset.reset` (`earliest`/`latest`). Với topic mới và consumer chưa assigned, nếu publish trước khi listener ready và group dùng `latest`, test có thể bỏ lỡ record. Sử dụng bounded readiness checks và offset policy rõ, không đoán bằng `Thread.sleep(200)`.

## 19. RabbitMQ: queue, exchange, binding và vhost

RabbitMQ routing dựa vào **exchange**, **routing key**, **queue** và **binding**. Một test chỉ đổi routing key nhưng vẫn dùng chung queue có thể nhận message của test khác nếu binding bao quát cả hai keys. Nên tách queue và exchange/bindings khi test cần independence.

### Spring AMQP snippet tạo resources riêng

Cần `spring-boot-starter-amqp`, RabbitMQ broker test, `RabbitAdmin` và `RabbitTemplate` đã cấu hình; đây là **snippet mở rộng**, không thuộc project PostgreSQL runnable:

```java
IsolationNames.Names names =
        IsolationNames.forRunId(runId);

DirectExchange exchange =
        new DirectExchange(names.rabbitExchange(), false, false);

Queue queue =
        new Queue(names.rabbitQueue(), false, false, false);

rabbitAdmin.declareExchange(exchange);
rabbitAdmin.declareQueue(queue);
rabbitAdmin.declareBinding(
        BindingBuilder.bind(queue)
                .to(exchange)
                .with("events"));

try {
    rabbitTemplate.convertAndSend(
            exchange.getName(),
            "events",
            "order-created");

    Object received = rabbitTemplate.receiveAndConvert(
            queue.getName(), 5000);

    assertEquals("order-created", received);
} finally {
    rabbitAdmin.deleteQueue(queue.getName());
    rabbitAdmin.deleteExchange(exchange.getName());
}
```

Đây là sample integration flow với queue/exchange **non-durable** và manual cleanup; cần injected `rabbitAdmin`, `rabbitTemplate`, JUnit assertions và imports Spring AMQP classes. Nó giả định broker đang sẵn sàng, resource declarations thành công và có quyền delete đúng resources. Nếu test có asynchronous consumers đang chạy, **stop consumers trước khi delete queue**; ví dụ direct polling ở trên không dùng một listener khác cạnh tranh queue.

### AnonymousQueue khi nào phù hợp?

`AnonymousQueue` hoặc `RabbitAdmin.declareQueue()` có thể tạo queue với tên tự sinh, **non-durable, exclusive, auto-delete** theo semantics tương ứng. Nó phù hợp một consumer tạm trong integration tests. Nhưng khi test muốn verify durable queue/binding/persistence, dùng exclusive auto-delete queue sẽ **không bảo vệ** behavior sản phẩm thật. Cũng không có nghĩa queue tự xóa ngay sau mỗi message: auto-delete thường phụ thuộc consumer lifecycle/connection.

### Vhost riêng có tốt hơn không?

RabbitMQ **virtual host** tách namespace của queues/exchanges/permissions. Nếu một test suite có quyền tạo vhost, có thể tạo `/it-<runId>` riêng. Nhưng việc provision/cleanup vhost đòi management API/quyền cao và có thể tốn resources; với nhiều tests nhỏ, unique queue/exchange trên **vhost dành riêng cho CI** thường đủ.

Không dùng vhost `/` chung với production, không xóa toàn bộ vhost chỉ vì một test fail. Vhost là cấu trúc quản trị, không nên tự tạo/xóa trên một shared broker mà test không sở hữu.

## 20. Redis: dùng prefix và TTL, không FLUSHALL

Redis logical database index thường **không phải** mức cô lập đủ mạnh cho mọi môi trường (Redis Cluster chỉ hỗ trợ DB 0; các clients có thể dùng cùng index). Với shared Redis test instance, gắn namespace vào **mọi key**:

```text
it:0123456789abcdef0123456789abcdef:order:ORDER-1
it:0123456789abcdef0123456789abcdef:session:USER-1
it:fedcba9876543210fedcba9876543210:order:ORDER-1
```

Cùng business key nhưng namespace khác → hai Redis keys khác nhau.

Một pattern với Spring Data Redis (snippet; cần `RedisTemplate<String,String>`, không nằm trong main Gradle):

```java
String prefix =
        IsolationNames.forRunId(runId).redisPrefix();

String key = prefix + "order:ORDER-1";

redisTemplate.opsForValue().set(
        key, "READY", Duration.ofMinutes(5));

String value =
        redisTemplate.opsForValue().get(key);

assertEquals("READY", value);
```

**TTL 5 phút** ở đây là thời hạn dành cho test fixture, không phải cache TTL nghiệp vụ mặc định. Cleanup có thể scan prefix `it:<runId>:*` theo `SCAN` với giới hạn batch, sau đó xóa **chỉ keys đã match exact ownership**. Không dùng `KEYS *` cho Redis lớn, không dùng `FLUSHALL`/`FLUSHDB` với shared instance, và không xóa theo `it:*` nếu nhiều jobs CI cùng dùng prefix chung.

### Redis Streams/consumer groups

Nếu dùng Redis Streams, cần tách **stream key**, consumer group và pending entries. Chỉ đổi cache key prefix nhưng giữ stream `events` và consumer group `test-group` chung vẫn có thể cạnh tranh và đọc lẫn nhau. Tạo names/consumers theo `runId` hoặc dùng Redis container riêng cho test suite.

## 21. Object storage: bucket riêng hay prefix riêng?

Với S3/MinIO/Azure Blob, có thể chọn:

- **Bucket/container per suite**: isolation mạnh hơn, nhưng thường bị quota/name uniqueness constraints, provisioning chậm và permission management phức tạp.
- **Prefix per run**: cùng test bucket nhưng keys nằm dưới `it/<runId>/`.
- **Object version/etag per test**: có thể cần cho concurrency/race tests.

Một snippet object key:

```java
IsolationNames.Names names =
        IsolationNames.forRunId(runId);

String key = names.objectPrefix()
        + "reports/report.json";
```

Không ghi các objects vào `reports/report.json` global nếu nhiều suites chạy song song. Khi cleanup, **list và delete chỉ objects dưới prefix thuộc run**, xét pagination và versioned objects/delete markers. Một `deleteObjects` thiếu filtering có thể xóa dữ liệu của người khác. Giữ bucket test riêng với policies deny production credentials nếu được.

Không dùng cùng bucket/prefix với production rồi hy vọng test cleanup an toàn vì tên file là `test.json`.

## 22. Kubernetes namespace và các giới hạn của nó

Với test e2e cần deploy services/brokers, một Kubernetes namespace riêng theo `runId` giúp tách resource names và nhiều config objects.

Ví dụ từ `IsolationNames.forRunId(runId).kubernetesNamespace()`:

```text
it-0123456789abcdef0123456789abcdef
```

Nên gắn labels như `test-run=<runId>`, `managed-by=ci`, `expires-at=<timestamp>` và resource quotas. Khi cleanup, chỉ xóa namespace mà run đã tạo và xác nhận owner label/ID; không chạy namespace deletion trên shared system/production namespace.

**Namespace không phải bảo mật đầy đủ tự động:** cần NetworkPolicy, RBAC, quotas, service accounts, secret policies, storage class boundaries và cluster-wide resource names. Tests có thể va chạm ở CRDs, cluster roles, ingress hostnames, PVs hoặc DNS names dù namespaces khác nhau.

### Phương án khi không có quyền tạo namespace

Nếu CI chỉ có quyền deploy trong một namespace test dùng chung, dùng resource name prefixes, labels, service account/resource quotas và cleanup exact labels. Không xóa mọi pods theo label `app=test` nếu nhiều runs cùng dùng label chung; thêm test run ID để lọc.

## 23. Testcontainers reuse và resource ownership

Testcontainers có nhiều kiểu lifecycle:

- **Static @Container field:** container thường sống xuyên các test methods trong một class và dừng khi class xong.
- **Instance @Container field:** có thể tạo container per test method, mạnh hơn nhưng tốn startup.
- **Manual singleton container:** có thể reuse across classes nhưng developer phải quản lý lifecycle, Spring context cache và static mutable state.
- **Reusable containers feature:** không nên bật mặc định trong shared CI khi cleanup/isolated state không được đảm bảo.

Nếu container được chia sẻ, phải tách database/schema/namespace bên trong. “Mọi test cùng container PostgreSQL” không đồng nghĩa không an toàn, nhưng mọi shared mutability phải được kiểm soát.

### Phân biệt CI job isolation với local test isolation

Một CI pipeline có thể chạy nhiều **Gradle forks** hoặc shard jobs. `static` field chỉ sống trong từng JVM, không phân phối identity giữa processes. UUID-derived runId hoạt động xuyên processes; counter trong static field không. Một broker cloud có thể được dùng bởi nhiều Git branches, nên namespace phải bao gồm ownership của run hoặc hoàn toàn unique, không chỉ một tên class.

## 24. Chạy song song: @Execution, @ResourceLock và @Isolated

JUnit Jupiter hỗ trợ `@Execution(CONCURRENT)` cho tests có state độc lập. Với resource global không thể cô lập (ví dụ `System.setProperty`, fixed filesystem path hoặc một legacy mock server fixed port), dùng `@ResourceLock` hoặc `@Isolated` để serialize:

```java
@ResourceLock(value = "legacy-shared-queue")
@Test
void legacyQueueTest() {
    // Đây là snippet cấu trúc.
}
```

Cần import `org.junit.jupiter.api.parallel.ResourceLock` và đưa method vào test class có setup phù hợp. Nếu nhiều tests truy cập cùng resource, tất cả đều phải khai báo lock key nhất quán; một test quên lock vẫn tạo race.

`@Isolated` có thể dùng trên test class mà không thể chạy đồng thời với các tests khác trong JVM. **Nó không khóa resource giữa các JVM hoặc giữa các CI jobs**. Với tài nguyên shared cross-process, phải có namespaces, distributed locking hoặc dedicated infrastructure.

### Tại sao không khóa mọi thứ?

Serialize toàn bộ suite sẽ che race và làm CI chậm. Ưu tiên sửa resource ownership/isolation; dùng locks cho tài nguyên không thể tách trong ngắn hạn, ghi rõ lý do và kế hoạch refactor.

## 25. Tính sẵn sàng: create xong chưa chắc consumer đã ready

Với DB, schema creation/migrations phải hoàn tất trước khi query. Với Kafka, topic create request hoàn thành không có nghĩa listener đã được assigned partitions. Với Rabbit, queue được declare nhưng bindings/consumer lifecycle có thể chưa hoàn tất.

Một cách test đáng tin:

1. Generate runId.
2. Create topic/queue/schema.
3. Configure consumer/listener cho đúng topic, group, queue.
4. Start listener container.
5. Đợi readiness có timeout, ví dụ Kafka partition assignment/consumer state, Rabbit consumer registration, app health.
6. Publish/send test data.
7. Await **consumption/business effect** có timeout, không chỉ producer send acknowledgment.
8. Stop listeners, wait processing quiescent.
9. Cleanup resources only owned.

**Không dùng `Thread.sleep(1000)`** để đoán consumer ready. Khi event async chạy, assert acknowledgement/output theo correlation ID; nếu test B chạy cùng lúc, nó phải không thể consume events của A qua routing/group cấu hình.

## 26. Migrations với schema riêng: những bẫy đặc thù

Khi dùng Flyway/Liquibase và mỗi test class có schema riêng:

- Tạo schema **trước** khi Flyway/Liquibase chạy.
- Cấu hình target schemas/default schema và metadata history table đúng namespace.
- Tránh migration tạo global objects trong `public` hoặc extension/role dùng chung.
- Xác nhận JPA/Hibernate default schema, JDBC search_path và Flyway schema là **cùng một schema**.
- Không dùng một datasource singleton rồi đổi `search_path` tùy test method nếu pool có connections reused.
- Bảo đảm migration scripts không `DROP SCHEMA public CASCADE` hoặc clear unrelated objects.
- Với PostgreSQL schema per suite, dùng role chỉ có quyền trong test database/schema được cấp.
- Cleanup theo owner schema, nhưng kiểm tra whitelist và quyền trước khi `DROP SCHEMA ... CASCADE`; câu lệnh này có thể xóa tables/functions/views trong schema bị nhắm tới.
- Nếu muốn chạy migrations concurrent lên nhiều schemas cùng database, test lock/history policy, transaction boundaries và extension/global DDL conflicts.

### Không che bug migration bằng H2

H2 syntax/isolation khác PostgreSQL. Với test có PostgreSQL-specific JSONB, advisory locks, sequences hoặc transactional DDL, PostgreSQL Testcontainer có giá trị cao hơn in-memory H2. Nhưng không cần Docker cho unit tests thuần về tên namespace.

## 27. Kafka retry/DLT và transactional IDs

Isolate topic chính chưa đủ nếu framework retry tạo topic phụ theo convention:

```text
it.orders.<runId>
it.orders.<runId>-retry
it.orders.<runId>-dlt
```

Các tên trên chỉ là pattern học tập, không mặc định Spring Kafka tạo chúng với đúng suffix trong mọi version; khi dùng `@RetryableTopic`, cấu hình suffixes, attempts và DLT policy theo Spring Kafka release thực tế. Các topics retry/DLT phải dùng cùng runId và cleanup theo exact names.

Với Kafka producer transactions, **transactional.id prefix** không được dùng chung giữa hai producers độc lập hoạt động đồng thời; Kafka có thể fencing một producer khi producer khác dùng cùng transactional ID. Tương tự, Kafka Streams `application.id` quyết định consumer group và internal topics; cần unique per isolated test suite.

### Cleanup Kafka an toàn

- Đóng producers/consumers/listener containers trước.
- Xóa **chính xác** topic main/retry/DLT đã tạo.
- Đợi broker metadata cập nhật với bounded polling nếu assertion tiếp theo cần topic biến mất.
- Không giả định xóa topic sẽ lập tức xóa consumer group offsets hoặc mọi internal resource.
- Nếu delete topic bị cấm, dùng broker container riêng hoặc TTL/scavenger trong môi trường test; không tạo hàng nghìn topics không giới hạn trên shared CI broker.

## 28. RabbitMQ: tránh fan-out và queue tranh chấp ngoài ý muốn

Trong RabbitMQ, nhiều consumers của **cùng một queue** thường chia messages theo competing-consumer semantics. Hai tests cùng queue nên sẽ nhận xen kẽ, không bảo đảm ai nhận bản tin nào.

Nếu muốn hai tests **độc lập**, dùng hai queues hoặc vhosts. Nếu muốn test **pub/sub broadcast**, tạo một exchange riêng và hai queues riêng có bindings rõ. Test phải xác định đúng semantics:

| Mục tiêu | Cấu hình |
| --- | --- |
| Một test nhận đúng một message riêng | Queue per test, routing key/binding per test |
| Hai consumers cùng chia việc | Cùng queue, cùng test scope, assert distribution theo policy |
| Fan-out đến hai listeners | Một exchange fanout, hai queues riêng trong cùng test |
| Error to DLQ | Queue chính + DLX + DLQ cùng run namespace |
| Test reconnect/exclusive queue | Server-named/exclusive queue; lifecycle theo connection |
| Multiple CI jobs không ảnh hưởng | Unique vhost hoặc exchange+queue names per run |

**Không dùng `rabbitAdmin.purgeQueue("test.queue")` trên queue chung** để setup test vì purge xóa messages của test khác. Đừng dùng fixed queue name trong `@RabbitListener(queues="test.queue")` khi cùng app context được nhiều scenarios dùng; nếu cần dynamic queue, bind property vào test-specific context hoặc programmatically start listener container.

## 29. Cleanup không được gây cross-test deletion

| Tài nguyên | Cleanup nguy hiểm | Cleanup theo ownership |
| --- | --- | --- |
| PostgreSQL | `TRUNCATE orders`; `DROP SCHEMA public` | `DELETE ... WHERE test_namespace = ?` hoặc drop generated test schema |
| Kafka | Delete toàn bộ topics có prefix quá rộng | Delete exact topic names của runId |
| RabbitMQ | Purge fixed queue hoặc delete shared exchange | Delete declared queue/binding/exchange của run |
| Redis | `FLUSHALL`/`FLUSHDB` | TTL + scan/delete exact run prefix |
| S3 | Delete bucket/prefix chung | Delete only owned object prefix; account for versions |
| Kubernetes | Delete shared namespace | Delete exact generated namespace after label verification |
| Temp files | `rm -rf /tmp` hoặc thư mục shared | Unique temp directory per test, recursive delete only owned path |
| Metrics/logs | Clear global registries | Per-test registry/log capture hoặc namespaced assertions |

### Quy tắc hai bước trước thao tác xóa mạnh

1. **Validate target:** identifier phải thuộc prefix/schema/namespace do test tạo và nằm trong environment test.
2. **Validate ownership:** metadata/label/run record trùng owner, không xóa tài nguyên thuộc run khác.

Với bất kỳ command `DROP ... CASCADE`, delete bucket hoặc Kubernetes namespace, cần guardrails quyền và audit phù hợp. Không dùng admin/root credentials cho test thông thường nếu có thể cấp quyền hạn chế.

## 30. Dữ liệu thử nghiệm và observability cũng cần cô lập

Resource isolation không chỉ dành cho storage:

- **Filesystem:** `@TempDir` tạo thư mục riêng từng test, không ghi `/tmp/output.csv` chung.
- **Clock:** tránh thay `TimeZone.setDefault` hoặc `System.setProperty` global nếu tests parallel; inject `Clock` bean.
- **Random:** inject fixed seed khi test logic yêu cầu deterministic output; UUID cho resource uniqueness vẫn được.
- **Micrometer:** mỗi test có `SimpleMeterRegistry` riêng hoặc test-specific tags/clear plan; không reset global registry của test khác.
- **Spring Security:** tránh dùng global mutable auth context; hiểu `SecurityContextHolder` thread-local.
- **Caches:** prefix/namespace key; đừng xóa toàn bộ Caffeine/Redis cache nếu shared context giữa tests.
- **Log capture:** correlation ID/runId tách records; không assert logs chỉ bằng last line global.
- **Test fixtures:** primary keys, external invoice numbers và webhook event IDs không được dùng cố định xuyên nhiều parallel runs.
- **Schedulers:** disable startup schedulers trừ khi test đúng scheduling; job có thể đọc/xóa state của test khác nếu dùng chung namespace.

Nếu build chia test modules, mỗi module cần policy resource names tương thích nhưng không collision. Đặt test ownership conventions ở một thư viện test helpers thay vì copy random hardcoded prefixes khắp nơi.

## 31. Chiến lược CI: cân bằng tốc độ và tính cô lập

Có thể chia suite thành ba tầng:

| Tầng | Ví dụ | Policy |
| --- | --- | --- |
| Unit | IsolationNamesTest, pure services | Parallel mạnh, không cần Docker |
| Integration nhỏ | JDBC + một PostgreSQL container, Kafka listeners | Per-class/container/namespace, timeout và cleanup |
| E2E/chaos | Nhiều brokers/services/K8s | Dedicated namespace hoặc môi trường có quota, parallel hạn chế |

Không bật 32 Docker containers chỉ vì máy có 32 CPU threads. PostgreSQL startup, Kafka partition metadata, Rabbit connections và Redis memory cùng chiếm tài nguyên. Giới hạn theo CI quotas; đo thời gian suite và tỷ lệ flaky trước/sau khi tăng parallelism.

### Gradle forks

`maxParallelForks` làm nhiều test JVMs chạy đồng thời. Mỗi JVM có static state và context cache riêng; chúng **không chia một counter**. Namespaces cần unique xuyên processes, do đó UUID v4 phù hợp hơn suffix `test-1`. Nếu CI sharding tạo nhiều jobs đồng thời, cần tiếp tục giữ identity per run.

### Khi nào không dùng parallel?

Một migration integration suite thay đổi global DB schema, một test cluster-wide RBAC, hoặc chaos test stop shared broker thường nên chạy **serial trong môi trường riêng**. Dùng `@Isolated` chỉ giới hạn trong một JUnit process, không có tác dụng khóa giữa CI jobs.

## 32. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Test pass riêng nhưng fail khi parallel | Shared row/topic/queue/resource | Tạo namespace riêng và assert owner filtering |
| Vi phạm unique key giữa tests | PK không gồm namespace | Composite key hoặc DB/schema per test |
| Rows từ test khác xuất hiện trong kết quả | Query thiếu namespace predicate | Tenant/test scoping bắt buộc trên mọi read |
| @AfterEach xóa dữ liệu test bên cạnh | Cleanup quá rộng | Delete by exact runId/prefix |
| PostgreSQL schema riêng nhưng viết vào public | DataSource search_path/Flyway mismatch | Cấu hình pool/schema từ startup và assert current_schema() |
| Kafka test không nhận message | Shared group/rebalance, consumer chưa ready, latest offset | Unique topic+group; đợi assignment |
| Kafka có duplicate/old records | Dùng lại topic/group cố định | Unique topic, group, correlation |
| Rabbit queue bị xóa lúc test B chạy | Shared queue name và lifecycle | Queue/exchange per run |
| Redis test cache miss bất thường | FLUSHDB của test khác | Unique prefix, TTL, no global flush |
| Context còn giữ JDBC URL container cũ | Static container stopped nhưng context cached | @DirtiesContext hoặc align lifecycle |
| @Transactional không rollback HTTP/Kafka | Khác thread/transaction | Explicit cleanup và integration assertions |
| @DirtiesContext làm chậm CI nhưng không sửa broker collision | Tool reset sai tầng | Isolate broker resources |
| Kafka topic deletion flaky | Delete async/broker policy | Poll bounded, stop consumers trước |
| Parallel test dùng cùng System property | JVM-global mutable state | Inject config hoặc ResourceLock |
| Tên namespace có ký tự không hợp lệ | Lấy branch name/raw input | Sanitize/allowlist generated IDs |
| K8s delete phá namespace đồng nghiệp | Không xác minh owner label | RBAC + exact generated name |
| E2E suite hết quotas | Quá nhiều containers/topics | Limit parallelism, cleanup + resource budget |

## 33. Checklist QA trước khi merge

- [ ] Test isolation scope được xác định: per method, class, suite, process hay CI job?
- [ ] Mọi resource được đặt tên bằng runId unique/safe?
- [ ] Schema names tuân PostgreSQL identifier length/characters?
- [ ] Database/schema provisioning xong trước migrations/app startup?
- [ ] Nếu dùng pooled connections, mọi connection nhìn đúng schema?
- [ ] Nếu dùng row namespace, mọi SELECT/UPDATE/DELETE có namespace predicate?
- [ ] Unique constraints/indexes có xem xét namespace khi cần?
- [ ] Teardown chỉ xóa resources thuộc owner?
- [ ] @AfterEach và exception/failure paths có cleanup?
- [ ] Có xử lý orphan resources khi CI bị kill?
- [ ] Không dùng FLUSHALL/TRUNCATE/DROP public trong shared environment?
- [ ] @Transactional limitations với async/broker/HTTP đã được hiểu?
- [ ] @DirtiesContext chỉ dùng khi context cần refresh, không coi là broker cleanup?
- [ ] Kafka topic và consumer group cùng được isolate?
- [ ] Kafka retries/DLT/transactional IDs được isolate nếu dùng?
- [ ] Kafka consumer ready trước khi publish?
- [ ] Rabbit queue/exchange/binding/vhost có owner riêng?
- [ ] Rabbit temporary queue semantics phù hợp với thứ cần test?
- [ ] Redis keys/streams có prefix/TTL và cleanup an toàn?
- [ ] S3/bucket objects có prefix riêng, deletion theo exact scope?
- [ ] Kubernetes namespace labels/RBAC/quotas được thiết kế?
- [ ] JUnit parallel & Gradle forks đã tính tổng concurrency?
- [ ] Global System properties/Clock/metrics/temp files có isolation?
- [ ] Testcontainers static container lifecycle khớp Spring context cache?
- [ ] Docker/CI resource limits đã được tính?
- [ ] Có test thực sự chạy concurrent để chứng minh không đọc nhầm dữ liệu?
- [ ] Đã chạy suite/CI và xem report thật trước khi khẳng định tests PASS?

## 34. Bài tập thực hành

1. Chạy `IsolationNamesTest` không cần Docker, xác minh generated IDs hợp lệ.
2. Chạy `OrderStoreIsolationTest` với PostgreSQL Testcontainers.
3. Cố tình bỏ `WHERE test_namespace = ?` khỏi `OrderStore.count` rồi xem test nào phát hiện.
4. Cố tình đổi PK thành chỉ `order_id`, quan sát va chạm của two namespaces.
5. Đổi `cleanupOwnedRows` thành `DELETE FROM it_orders` không điều kiện trong sandbox, chạy parallel để thấy nguy cơ.
6. Tạo một test class khác dùng PostgreSQLContainer riêng; quan sát resources và context lifecycle.
7. Thử một shared PostgreSQL container nhưng mỗi class có schema riêng; assert `SELECT current_schema()` theo class.
8. Thêm Flyway migrations vào schema per class và xác minh history table được đặt đúng.
9. Thêm Kafka Testcontainer và tạo hai topic+consumer groups theo hai runIds.
10. Cố ý dùng chung `group.id`, quan sát rebalances/partition competition.
11. Thêm retry/DLT topics theo runId, dọn đúng owned topics.
12. Tạo RabbitMQ queue/exchange theo runId, gửi/nhận/cleanup đúng resource.
13. Dùng `AnonymousQueue` rồi kiểm tra lifecycle khi consumer disconnect.
14. Thêm Redis Testcontainer; ghi hai keys có cùng business ID dưới hai prefixes.
15. Thử xóa chỉ prefix một run, xác nhận dữ liệu run kia còn.
16. Ghi hai object cùng tên file dưới hai S3 prefixes và cleanup một run.
17. Tạo một test K8s namespace có labels và quota, cleanup có owner validation.
18. Với một suite JUnit thuần **không dùng Testcontainers JUnit extension**, thử bật 4 JUnit threads và đo failures/tài nguyên; giữ ví dụ @Testcontainers trong bài chạy tuần tự.
19. Thử `@ResourceLock` để serialize một global resource legacy, giải thích vì sao không khóa cross-JVM.
20. Thử tắt CI giữa chừng, thiết kế orphan sweeper chỉ xóa expired test-owned resources.
21. Đo thời gian test trước và sau khi tăng parallelism; chọn mức có lợi thực.
22. Chạy một scenario có @Async/message listener và xác minh cleanup xảy ra sau khi xử lý hoàn tất.

## 35. Tài liệu tham khảo

- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection` và integration với Spring Boot-managed connections.
- [Spring Boot 3.3 — Database Initialization](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html): `spring.sql.init.mode=always`, schema.sql, migrations.
- [Testcontainers for Java — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container` và lifecycle; xem cảnh báo về parallel execution của extension.
- [Testcontainers PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQLContainer.
- [Spring Framework — TestContext Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): context reuse.
- [Spring Kafka Reference — Topic Configuration](https://docs.spring.io/spring-kafka/reference/kafka/configuring-topics.html): KafkaAdmin và NewTopic.
- [Apache Kafka AdminClient API](https://kafka.apache.org/documentation/): topic creation/deletion, consumer groups/offsets.
- [Spring AMQP — Broker Configuration](https://docs.spring.io/spring-amqp/reference/amqp/broker-configuration.html): RabbitAdmin, queues, exchanges, bindings, temporary/anonymous queues.
- [RabbitMQ — Virtual Hosts](https://www.rabbitmq.com/docs/vhosts): vhosts as broker namespace.
- [Spring Data Redis Reference](https://docs.spring.io/spring-data/redis/reference/): RedisTemplate, key prefixes và TTL.
- [JUnit 5 — Parallel Execution](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parallel-execution): `@Execution`, `@ResourceLock`, `@Isolated`.
- [Gradle — Testing in Java Projects](https://docs.gradle.org/current/userguide/java_testing.html): forks và test reports.
- [Kubernetes — Namespaces](https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/): resource name scope, labels và RBAC/NetworkPolicy bổ sung.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycles/assertions.

## 36. Kết luận

**Cách ly tài nguyên là điều kiện để kiểm thử chạy song song có ý nghĩa.** UUID hay `@Transactional` đơn lẻ không giải quyết hết: cần chọn đúng boundary (database, schema, row namespace, Kafka topic và consumer group, RabbitMQ queue/exchange, Redis key prefix, object storage prefix hoặc Kubernetes namespace), truyền identity ấy qua **mọi thao tác**, rồi cleanup **chỉ tài nguyên mình tạo**.

Với Spring Boot 3.3.5, Testcontainers `@ServiceConnection` giúp có PostgreSQL thật mà không hardcode endpoint, còn `test_namespace` cùng composite primary key giúp nhiều test methods truy cập cùng bảng mà không dẫm lên nhau. Kafka cần chú ý topic **và group** cùng retry/DLT; RabbitMQ cần queue/exchange/binding và vhost policy; Redis tránh global flush; K8s cần label/RBAC/quotas. JUnit parallel, Gradle forks và Spring context cache quyết định liệu isolation đó được duy trì trong toàn suite và CI hay không.

Mã chính minh họa **10 phương thức test** (6 unit naming + 4 PostgreSQL integration), nhưng chỉ sau khi chạy Gradle/Docker thật và đọc JUnit reports mới có thể nói bao nhiêu tests PASS. Bảo vệ đúng ownership, readiness, resource lifetime và cleanup trước khi tăng concurrency để CI nhanh hơn mà vẫn đáng tin cậy.

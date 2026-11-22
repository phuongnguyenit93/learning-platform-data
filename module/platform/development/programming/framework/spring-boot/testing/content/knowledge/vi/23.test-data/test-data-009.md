# Schema, database hoặc namespace riêng cho từng nhóm test trong Spring Boot

> **Module:** Spring Boot – testing  
> **Nhóm kiến thức:** Dữ liệu kiểm thử  
> **Đề bài:** Schema, database hoặc namespace riêng cho từng nhóm test  
> **Mục tiêu:** Thiết kế cách cô lập dữ liệu giữa các nhóm kiểm thử (billing, shipping, search, cache...), đặc biệt khi chạy song song; chọn đơn vị tách phù hợp cho SQL/NoSQL/broker/object storage; cấu hình Spring Boot test context, migrations, cleanup và Testcontainers an toàn; phân biệt isolation của dữ liệu, transaction và quyền truy cập. Ví dụ chạy được dùng Java 17, Maven, Spring Boot 3.5 và hai H2 databases riêng cho hai nhóm test, cùng unit tests kiểm tra namespace key.

## 1. Tại sao cần không gian dữ liệu riêng cho từng nhóm test?

Giả sử hệ thống có hai nhóm kiểm thử:

- **Billing tests** lưu hóa đơn có reference `INV-001`.
- **Shipping tests** lưu vận đơn cũng có reference `INV-001`.

Nếu cùng sử dụng một bảng `records` trong một database test chung, có thể xuất hiện:

1. Billing insert trước; Shipping insert cùng unique key và thất bại dù logic Shipping không sai.
2. Shipping chạy `DELETE FROM records` ở `@BeforeEach`, làm Billing mất dữ liệu giữa lúc đang assert.
3. Một test đọc dữ liệu leftover từ test chạy trước và bất ngờ pass hoặc fail theo thứ tự.
4. CI bật parallel execution; hai groups cùng tạo/drop schema hoặc truncate bảng.
5. Flyway/liquibase của nhóm này thay đổi schema mà nhóm kia đang sử dụng.
6. Worker test sử dụng Redis `FLUSHDB` hoặc Elasticsearch `DELETE index-*`, xóa cả dữ liệu của groups khác.
7. Test kết nối nhầm shared development/staging database, gây nguy cơ mất dữ liệu hoặc truy xuất sai.
8. Một test chỉ pass khi chạy một mình (`mvn -Dtest=...`) nhưng fail trong full suite (`mvn test`).

Vấn đề không phải JUnit, Spring Boot hay database “không ổn định”; nó là **shared mutable state không được giới hạn phạm vi**.

Giải pháp là tạo tài nguyên dữ liệu có chủ sở hữu rõ ràng cho mỗi **test group**: SQL database, SQL schema, MongoDB database, Redis key prefix, Elasticsearch index, Kafka topic/consumer group, S3 bucket/prefix hoặc một cơ chế phù hợp với dịch vụ. Sau đó xác định ai tạo, ai dùng, khi nào dọn và phạm vi nào có thể chạy song song.

### 1.1. Mục tiêu cần chứng minh

Một chiến lược isolation tốt phải bảo vệ tối thiểu:

- **Không đọc nhầm:** Nhóm A không nhìn thấy dữ liệu của B nếu không được phép.
- **Không ghi nhầm:** A không sửa/xóa resource đang thuộc B.
- **Không va chạm tên:** Business keys, sequences, index names, topics hoặc cache keys không xung đột.
- **Không phụ thuộc thứ tự:** Test pass dù A chạy trước B, B trước A hay song song (trong phạm vi được hỗ trợ).
- **Dọn đúng sở hữu:** Cleanup chỉ chạm objects/resources của chính group.
- **Tái lập được:** Local/CI có thể tạo cùng một môi trường logic từ cấu hình/migrations.
- **An toàn:** Không bao giờ dùng production credentials hoặc destructive cleanup trên resource không được chứng minh là test-only.

**Lưu ý:** Cô lập dữ liệu không tự động bằng phân quyền. Hai schemas trong cùng PostgreSQL database vẫn có thể truy cập lẫn nhau nếu role có quyền; hai prefixes trong Redis cùng database không ngăn một client privileged đọc prefix khác. Với security isolation phải thêm role/ACL/IAM và tests phù hợp.

## 2. Chọn đơn vị cô lập: test method, class, group, suite hay CI job?

Một “nhóm test” không nhất thiết bằng một JUnit class. Nó có thể là module, bounded context, pipeline job, một nhóm tích hợp cùng hạ tầng, hoặc tests có chung lifecycle.

| Phạm vi | Ví dụ | Lợi ích | Cái giá |
| --- | --- | --- | --- |
| Mỗi test method | DB/schema độc lập cho từng `@Test` | Isolation cao, rất ít bleed | Khởi tạo và migration nhiều |
| Mỗi test class | `BillingRepositoryTest` một DB | Dễ hiểu, song song giữa classes | DB setup theo class |
| Mỗi nhóm/feature | `billing` và `shipping` có resource riêng | Cân bằng tốc độ và tính cô lập | Tests trong cùng group vẫn cần cleanup/transaction |
| Mỗi test suite/module | Một DB cho toàn integration suite | Ít containers, nhanh | Không tự động độc lập giữa classes |
| Mỗi CI job/shard | `run_942_shard_2` | Không đụng jobs khác khi song song | Cần tạo tên/cấp quyền/teardown theo job |
| Mỗi môi trường | Local/dev/CI/staging | Chặn cross-environment | Chưa tránh đụng nhau trong cùng môi trường |

**Chọn phạm vi theo rủi ro**, không bắt buộc mỗi test method khởi động một container riêng. Với tests chỉ đọc và không thay đổi state, có thể chia sẻ immutable fixtures. Với tests viết dữ liệu, chạy migrations, tạo/drop index hoặc mô phỏng concurrency, cần ranh giới rõ hơn.

### 2.1. Một mô hình ownership nên được ghi thành hợp đồng

```text
Test run: ci_942
  |
  +-- group: billing
  |     SQL database:   it_ci942_billing
  |     Redis prefix:   it:ci942:billing:
  |     Mongo database: it_ci942_billing
  |     ES index:       it-ci942-billing-orders
  |     Kafka topic:    it.ci942.billing.events
  |
  +-- group: shipping
        SQL database:   it_ci942_shipping
        Redis prefix:   it:ci942:shipping:
        Mongo database: it_ci942_shipping
        ES index:       it-ci942-shipping-orders
        Kafka topic:    it.ci942.shipping.events
```

Tên minh họa được chọn ngắn, không chứa thông tin nhạy cảm. Nếu cùng một group có **nhiều CI shards chạy đồng thời**, bổ sung shard id hoặc process id vào tên. Nếu cần chia sẻ dữ liệu read-only cố định, phải ghi rõ ai chịu trách nhiệm tạo và không cho test khác mutate.

### 2.2. Một database hay một schema hay chỉ prefix?

Không có lựa chọn đúng cho mọi engine:

- SQL database riêng thường mạnh hơn schema riêng về tên objects và nhiều thành phần cấu hình, nhưng tạo database nhiều lần có chi phí lớn hơn.
- SQL schema riêng phù hợp khi nhiều nhóm muốn chia sẻ một PostgreSQL server/database mà vẫn có table/index/sequence names riêng.
- Redis key prefix là cách phân vùng naming, không phải Redis database độc lập và cũng không tự ngăn flush toàn bộ DB.
- MongoDB database riêng tách collections/index names, nhưng server resources và admin privileges vẫn chia sẻ.
- Elasticsearch index riêng tách mappings/documents, nhưng cluster settings/quota/nodes vẫn chung.
- Kafka topic riêng tách messages; consumer-group id riêng tách offsets, hai thứ này không thay thế nhau.

## 3. Phân biệt chính xác SQL database và SQL schema

### 3.1. Database riêng

Trong PostgreSQL, một database chứa các schemas, tables, indexes và objects khác; các client JDBC kết nối tới **một database** qua connection URL.

```text
PostgreSQL server/container
   ├── database it_ci942_billing
   │       ├── schema public
   │       └── schema billing
   └── database it_ci942_shipping
           ├── schema public
           └── schema shipping
```

Ưu điểm: giảm nguy cơ table/sequence names va chạm, dễ quản lý migration history theo database, dọn bằng cách drop **đúng database test-only** sau khi ngắt connections.

Hạn chế: tạo database, pool connections và migrate schema tốn thời gian; vẫn chia sẻ server CPU/memory/roles nếu cùng instance. Việc tách database không phải bằng chứng về network/security isolation nếu cùng credentials có nhiều quyền.

### 3.2. Schema riêng

Trong PostgreSQL, nhiều schemas có thể thuộc **cùng một database**:

```sql
CREATE SCHEMA test_billing;
CREATE SCHEMA test_shipping;

CREATE TABLE test_billing.outbox_events (
    id BIGINT PRIMARY KEY,
    payload TEXT NOT NULL
);

CREATE TABLE test_shipping.outbox_events (
    id BIGINT PRIMARY KEY,
    payload TEXT NOT NULL
);
```

Hai bảng cùng tên `outbox_events` không đụng nhau vì ở khác schemas. Nhưng SQL có schema qualification và `search_path`:

```sql
SELECT * FROM test_billing.outbox_events;
SELECT * FROM test_shipping.outbox_events;

SHOW search_path;
SELECT current_schema();
```

Nếu query viết `SELECT * FROM outbox_events`, PostgreSQL tìm bảng theo `search_path` của **connection hiện tại**. Do đó việc thay đổi schema phải được áp dụng nhất quán cho mọi connections trong pool, mọi JPA query và mọi migration.

### 3.3. `search_path` không phải biên giới bảo mật

`SET search_path TO test_billing` thay thứ tự tìm tên object **không có schema prefix**. Nó không cấm một client đủ quyền chạy `SELECT * FROM test_shipping.outbox_events`. Nó cũng không bảo vệ khỏi query native cố ý dùng `public.some_table`.

Vì vậy:

- Đừng dùng schema naming như một cơ chế multi-tenant security duy nhất.
- Ở môi trường cần security isolation, cấu hình PostgreSQL roles, GRANT/REVOKE và nguyên tắc least privilege.
- Không đặt một schema chưa được tin cậy lên `search_path` của một role có đặc quyền; untrusted objects trên search path là rủi ro bảo mật.
- Không lấy schema name từ request header/user input rồi nối thẳng vào SQL.
- Khi dùng connection pools, đừng sửa session `search_path` bằng mã tùy tiện mà không hoàn nguyên trạng thái khi trả connection về pool.

### 3.4. Schema không đồng nghĩa table prefix

Hai cách sau khác nhau:

```sql
CREATE TABLE test_billing.orders (...);
CREATE TABLE test_shipping.orders (...);
```

và

```sql
CREATE TABLE billing_orders (...);
CREATE TABLE shipping_orders (...);
```

Dòng đầu là **schema isolation**; dòng sau chỉ là **đặt tiền tố tên bảng trong cùng schema**. Prefix giúp tránh name collisions nhưng không tách migration history, privileges hay search path như schema riêng.

## 4. Database/schema isolation khác transaction rollback

`@DataJpaTest` mặc định tạo transactional test methods và rollback ở cuối. Điều này giúp fixture DML ít để lại dữ liệu **trong transaction test**, nhưng không thay thế tách database/schema.

Ví dụ:

```java
@DataJpaTest
class OrdersRepositoryTest {
    @Test
    void createsOrder() {
        // Thông thường transaction của method được rollback.
    }
}
```

Đoạn trên chỉ minh họa annotation, không phải test class đầy đủ.

Giới hạn của rollback:

- DDL và migrations không nhất thiết rollback giống DML.
- Sequences/identity values có thể tăng dù DML rollback.
- Một `@SpringBootTest(RANDOM_PORT)` dùng HTTP thật có thể chạy business transaction trên server thread riêng; transaction/rollback của test thread không bao lấy server commit.
- `@Async`, scheduled jobs, message consumers và connection từ thread khác có thể commit độc lập.
- MongoDB/Redis/Kafka/Elasticsearch không tự tham gia transaction rollback của `@DataJpaTest`.
- Một test tắt `@Transactional` hoặc dùng `REQUIRES_NEW` có thể để lại dữ liệu.
- Hai test classes cùng chạy migrations hoặc drop objects có thể đụng nhau dù các test methods đều rollback.

**Kết luận:** Transaction rollback là **một lớp cleanup**, còn database/schema/namespace riêng là **ranh giới ownership và naming**. Có thể dùng cả hai.

## 5. Chọn tên namespace an toàn, không bị va chạm

### 5.1. Những thành phần nên có trong tên

Tên tài nguyên test thường cần:

1. Marker rõ `it`/`test` để người vận hành nhận diện.
2. CI run id hoặc một opaque random id, không chứa email/secret.
3. Group id (billing, shipping).
4. Shard/process id nếu nhiều workers song song.
5. Loại tài nguyên nếu cần (orders, sessions, events).

Ví dụ:

```text
SQL database:     it_942_billing_1
PostgreSQL schema: it_billing_1
Mongo database:   it_942_billing_1
Redis prefix:     it:942:billing:1:
ES index:         it-942-billing-1-orders
Kafka topic:      it.942.billing.1.events
S3 prefix:        it/942/billing/1/
```

Tránh đặt raw user input, tenant ID thật, secret, email hoặc access token vào tên tài nguyên. Với PostgreSQL, identifier length mặc định tối đa 63 bytes nên phải giới hạn phần tên và dùng hash ngắn nếu cần. Elasticsearch index naming có các giới hạn riêng (ví dụ lowercase), Kafka topic có tập ký tự/rule riêng. Dùng hàm tạo tên theo từng provider, không cố ép một string tùy ý lên mọi hệ.

### 5.2. Quy tắc deterministic và unique

- **Deterministic trong một run:** Tất cả classes thuộc group A có thể biết tên database của group A.
- **Unique giữa runs:** Run A và run B không dùng cùng namespace khi chạy đồng thời.
- **Idempotent setup:** Tạo lại schema trong một run không vô tình xóa data đang được test khác sử dụng.
- **Cleanup có scope:** Chỉ dọn tài nguyên mang ownership của run/group.
- **Có lease/TTL khi có thể:** Dọn orphaned resources sau CI bị cancel/crash.
- **Không chạy dọn toàn cục:** Không `DROP DATABASE`, `FLUSHALL`, `DELETE /*` hay xóa bucket root một cách thiếu điều kiện.

### 5.3. Tên riêng không ngăn resource-level race

Nếu các nhóm dùng khác schemas nhưng chung một PostgreSQL server, chúng vẫn cạnh tranh CPU, connections, locks trên shared catalog và disk. Nếu hai nhóm dùng khác Redis prefixes nhưng server có `maxmemory` và eviction, áp lực bộ nhớ từ A vẫn có thể khiến keys của B bị evict. Nếu ES indices khác nhau nhưng chung cluster, shards, indexing throughput và refresh load vẫn chia sẻ.

Khi test thật sự nhạy về latency/concurrency/failover, cần isolation cao hơn như container/cluster riêng và một performance environment ổn định.

## 6. Dự án Spring Boot chạy được: hai nhóm dùng hai H2 databases

Ví dụ gốc dùng **Java 17, Maven, Spring Boot 3.5.0**. Nó có 2 nhóm test:

- `BillingDataTest` dùng H2 database `billing_group`.
- `ShippingDataTest` dùng H2 database `shipping_group`.

Cả hai dùng **cùng entity/repository và cùng unique business key** để minh họa tên key không va chạm vì nằm ở hai database khác nhau. Có thêm `NamespaceKeysTest` kiểm tra hàm tạo Redis key prefix riêng cho mỗi run và group (đây là pure Java test, không cần Redis server).

**Quan trọng:** Ví dụ H2 này chỉ chứng minh isolation theo JDBC database URL và JPA persistence trong H2. Nó **không** chứng minh PostgreSQL dialect, Flyway migrations, Redis TTL hay security ACL. Phần 9–12 bàn cách nâng lên môi trường thực.

### 6.1. Cấu trúc thư mục

```text
isolated-test-data-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/isolation/
    │       ├── IsolationLabApplication.java
    │       ├── AuditRecord.java
    │       ├── AuditRecordRepository.java
    │       └── NamespaceKeys.java
    └── test/
        └── java/com/example/isolation/
            ├── BillingDataTest.java
            ├── ShippingDataTest.java
            └── NamespaceKeysTest.java
```

Mọi `public` class/interface nằm trong file cùng tên, package `com.example.isolation`. Không cần HTTP server hoặc external database. H2 databases được tạo theo tên khi test context khởi động.

### 6.2. `pom.xml`

```xml
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
    <artifactId>isolated-test-data-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
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

Spring Boot parent quản lý versions Hibernate/H2/JUnit. Dùng `h2` test scope; không khai production database credentials trong project. Hai test classes sẽ chỉ định đầy đủ JDBC URL và yêu cầu Spring Boot **không** thay nó bằng embedded DB khác.

### 6.3. `IsolationLabApplication.java`

```java
// src/main/java/com/example/isolation/IsolationLabApplication.java
package com.example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationLabApplication.class, args);
    }
}
```

Không có `@RestController` hoặc `@Service` bắt buộc vì đây là bài về test data isolation và JPA slice.

### 6.4. `AuditRecord.java`

```java
// src/main/java/com/example/isolation/AuditRecord.java
package com.example.isolation;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "audit_records")
public class AuditRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "reference_code",
            nullable = false,
            unique = true,
            length = 64)
    private String referenceCode;

    @Column(name = "owner_group",
            nullable = false,
            length = 32)
    private String ownerGroup;

    protected AuditRecord() {
    }

    public AuditRecord(
            String referenceCode,
            String ownerGroup) {
        this.referenceCode = referenceCode;
        this.ownerGroup = ownerGroup;
    }

    public Long getId() {
        return id;
    }

    public String getReferenceCode() {
        return referenceCode;
    }

    public String getOwnerGroup() {
        return ownerGroup;
    }
}
```

`reference_code` có unique constraint trong **mỗi database**, không phải unique toàn server. Hai databases tách biệt có thể cùng chứa `shared-ref` mà không có conflict.

### 6.5. `AuditRecordRepository.java`

```java
// src/main/java/com/example/isolation/AuditRecordRepository.java
package com.example.isolation;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AuditRecordRepository
        extends JpaRepository<AuditRecord, Long> {

    Optional<AuditRecord> findByReferenceCode(
            String referenceCode);
}
```

Repository không biết tên group/database; `DataSource` của Spring test context quyết định nơi SQL được gửi. Đó là lý do test phải chứng minh **cấu hình kết nối** chứ không chỉ assert business data.

## 7. Hai JPA test classes: cấu hình DB tách biệt

### 7.1. `BillingDataTest.java`

```java
// src/test/java/com/example/isolation/BillingDataTest.java
package com.example.isolation;

import java.sql.Connection;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:billing_group;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class BillingDataTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    AuditRecordRepository repository;

    @Test
    void usesBillingDatabaseAndSavesReference() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getURL())
                    .contains("mem:billing_group");
        }

        assertThat(repository.count()).isZero();

        AuditRecord saved = repository.saveAndFlush(
                new AuditRecord("shared-ref", "billing"));

        assertThat(saved.getId()).isNotNull();
        assertThat(repository.findByReferenceCode("shared-ref")
                .orElseThrow().getOwnerGroup())
                .isEqualTo("billing");
    }

    @Test
    void billingFixtureIsScopedToCurrentTransaction() {
        assertThat(repository.count()).isZero();

        repository.saveAndFlush(
                new AuditRecord("bill-only", "billing"));

        assertThat(repository.count()).isEqualTo(1L);
    }
}
```

**Vì sao cần từng cấu hình?**

- `jdbc:h2:mem:billing_group` tạo một H2 in-memory database có tên riêng.
- `DB_CLOSE_DELAY=-1` giữ DB tồn tại trong JVM sau khi đóng last connection; tránh việc database biến mất giữa những lần pool lấy/nhả connection, nhưng **cần isolation/cleanup rõ** trong suite dài vì DB có thể sống qua nhiều test contexts.
- `@AutoConfigureTestDatabase(replace=NONE)` yêu cầu giữ đúng DataSource đã cấu hình; nếu bị thay bằng embedded DB ngẫu nhiên, tên group có thể không đúng.
- `@DataJpaTest` dùng JPA slice và mặc định rollback DML sau mỗi test method.
- `ddl-auto=create-drop` tạo schema riêng cho **DB này** khi context bootstrap; không kiểm tra Flyway migrations.
- Assert JDBC metadata chứng minh test đang kết nối URL chứa `billing_group`, không đoán từ tên class.
- Trong hai methods, repository count bắt đầu bằng 0 theo rollback/default context behavior của ví dụ.

### 7.2. `ShippingDataTest.java`

```java
// src/test/java/com/example/isolation/ShippingDataTest.java
package com.example.isolation;

import java.sql.Connection;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:shipping_group;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class ShippingDataTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    AuditRecordRepository repository;

    @Test
    void usesShippingDatabaseAndSameBusinessKey() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getURL())
                    .contains("mem:shipping_group");
        }

        assertThat(repository.count()).isZero();

        repository.saveAndFlush(
                new AuditRecord("shared-ref", "shipping"));

        assertThat(repository.findByReferenceCode("shared-ref")
                .orElseThrow().getOwnerGroup())
                .isEqualTo("shipping");
    }

    @Test
    void shippingDataDoesNotDependOnBillingFixture() {
        assertThat(repository.count()).isZero();

        repository.saveAndFlush(
                new AuditRecord("ship-only", "shipping"));

        assertThat(repository.count()).isEqualTo(1L);
    }
}
```

Hai classes đều dùng `shared-ref` nhưng database URLs khác nhau. Điều này minh họa **business key trùng không phải conflict xuyên DB**. Tests còn khẳng định dữ liệu được đọc dưới owner group đúng của connection riêng.

**Giới hạn của phép thử:** Vì `@DataJpaTest` mặc định rollback sau từng method, các assertions `count()==0` một mình **không đủ** để chứng minh tách database; phần kiểm tra JDBC URL chính là bằng chứng trực tiếp. Nếu muốn test data còn tồn tại qua transactions/threads, phải thiết kế integration test không dựa vào rollback mặc định, với setup/cleanup rõ ràng.

### 7.3. Test context cache có làm lẫn hai databases?

Spring TestContext caches `ApplicationContext` khi test configuration giống nhau. Ở ví dụ này, hai lớp dùng **khác `@DataJpaTest(properties=...)`** nên có test configuration khác nhau và phải được phân biệt. Không thay một static string “currentDatabaseName” bên ngoài rồi mặc định Spring tự tạo context/DataSource mới.

Khi dùng `@DynamicPropertySource`, những values do supplier cung cấp có thể thay đổi trong khi context đã cache, nhất là với base test class và subclasses. Nếu một context cache đang chứa DataSource kết nối group A nhưng test B cố đổi dynamic URL thành B, cần cấu hình test context riêng hoặc dùng `@DirtiesContext` có chủ đích để buộc rebuild; không tự rely vào biến mutable toàn cục.

## 8. NamespaceKeys: isolation bằng key prefix cho Redis và các cache

Trong một Redis server/shared cache, ta thường không muốn tạo server mới cho mỗi unit test. Dùng prefix xác định run+group+resource giúp tránh key collisions. Tuy nhiên prefix **không bảo vệ khỏi `FLUSHDB`/`FLUSHALL` và không cung cấp ACL isolation**.

### 8.1. `NamespaceKeys.java`

```java
// src/main/java/com/example/isolation/NamespaceKeys.java
package com.example.isolation;

import java.util.regex.Pattern;

public final class NamespaceKeys {

    private static final Pattern PART =
            Pattern.compile("[a-z][a-z0-9_-]{0,31}");

    private static final Pattern ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private NamespaceKeys() {
    }

    public static String session(
            String run, String group, String subject) {
        if (run == null || !PART.matcher(run).matches()
                || group == null
                || !PART.matcher(group).matches()
                || subject == null
                || !ID.matcher(subject).matches()) {
            throw new IllegalArgumentException(
                    "Invalid namespace token");
        }

        return "it:" + run + ":" + group
                + ":session:" + subject;
    }
}
```

Hàm này là **một naming helper thuần Java**, không kết nối Redis. Nó kiểm tra token theo whitelist và tạo key có run+group. Nếu ứng dụng có arbitrary user IDs chứa ký tự đặc biệt, cần một cách encode/hash an toàn và ổn định thay vì nới whitelist vô hạn.

### 8.2. `NamespaceKeysTest.java`

```java
// src/test/java/com/example/isolation/NamespaceKeysTest.java
package com.example.isolation;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class NamespaceKeysTest {

    @Test
    void createsDeterministicKeyForOneGroup() {
        assertThat(NamespaceKeys.session(
                "run42", "billing", "user_1"))
                .isEqualTo(
                        "it:run42:billing:session:user_1");
    }

    @Test
    void changesWhenRunOrGroupChanges() {
        String billing = NamespaceKeys.session(
                "run42", "billing", "user_1");
        String shipping = NamespaceKeys.session(
                "run42", "shipping", "user_1");
        String nextRun = NamespaceKeys.session(
                "run43", "billing", "user_1");

        assertThat(billing).isNotEqualTo(shipping);
        assertThat(billing).isNotEqualTo(nextRun);
    }

    @Test
    void rejectsUnsafeNamespaceComponent() {
        assertThatThrownBy(() ->
                NamespaceKeys.session(
                        "run42", "billing:other", "user_1"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Invalid namespace token");
    }
}
```

**Giới hạn của ba tests này:** Chúng chứng minh **cách đặt tên key**, không chứng minh Redis server thật set TTL, giữ JSON bytes chính xác, atomic SET NX, evict keys hoặc áp dụng ACL. Những điều đó phải có integration test Redis thực.

### 8.3. Chạy toàn bộ project mẫu

```bash
java -version
mvn -version

# Chạy cả hai database groups và namespace utility:
mvn test

# Chạy một test group:
mvn -Dtest=BillingDataTest test
mvn -Dtest=ShippingDataTest test

# Unit test không cần JPA context:
mvn -Dtest=NamespaceKeysTest test
```

Project gồm **7 JUnit `@Test` methods**: BillingDataTest có 2, ShippingDataTest có 2, NamespaceKeysTest có 3. Các JPA tests sử dụng H2 trong JVM; Redis không được khởi động. Output Maven/Surefire tùy môi trường, không có stdout cố định được khẳng định ở đây. Chưa thực thi build trong bài hướng dẫn này; `mvn test` là lệnh người học chạy sau khi tạo đúng files.

### 8.4. Vì sao không dùng một H2 database rồi xóa tables giữa hai nhóm?

Nếu test classes chạy tuần tự, có thể khiến việc xóa trước mỗi group “trông như” isolation. Nhưng dưới parallel execution, group A đang assert có thể mất data khi group B cleanup. Hai JDBC database names khác nhau loại bỏ dạng interference đó ở **tầng database resource**.

Ngoài ra, một H2 `mem:db` trong một JVM không tự cô lập schema migrations/index names nếu hai nhóm cùng kết nối nó. Nếu dùng H2 cho integration tests, vẫn cần owner/group name và lifecycle rõ ràng như với database khác.

## 9. Nâng lên PostgreSQL Testcontainers: database thật cho từng nhóm

H2 minh họa nguyên tắc. Khi sản phẩm chạy PostgreSQL và tests cần kiểm tra native SQL, schema migrations, locks, row types hoặc JDBC behavior, dùng PostgreSQL engine thật trong container.

### 9.1. Thêm dependencies tùy chọn

Với project phần 6, để thêm PostgreSQL Testcontainers integration tests, khai báo các dependencies (đừng trùng với mục đã có):

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Spring Boot parent quản lý các versions tương thích. PostgreSQL driver `test` scope đủ cho test-only variant; nếu production dùng PostgreSQL, driver nên nằm trong application dependencies phù hợp thay vì chỉ test scope.

### 9.2. Class-specific PostgreSQL container — ví dụ hoàn chỉnh tùy chọn

Tạo `src/test/java/com/example/isolation/BillingPostgresTest.java` **chỉ sau khi** đã thêm dependencies và có Docker. Class này chạy trên PostgreSQL container của riêng nó:

```java
// src/test/java/com/example/isolation/BillingPostgresTest.java
package com.example.isolation;

import java.sql.Connection;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = {
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "test.group=pg-billing"
})
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class BillingPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("billing_group");

    @Autowired
    DataSource dataSource;

    @Autowired
    AuditRecordRepository repository;

    @Test
    void reallyUsesPostgresAndOwnDatabase() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData()
                    .getDatabaseProductName())
                    .isEqualTo("PostgreSQL");
            assertThat(connection.getCatalog())
                    .isEqualTo("billing_group");
        }

        repository.saveAndFlush(
                new AuditRecord("pg-shared-ref", "billing"));

        assertThat(repository
                .findByReferenceCode("pg-shared-ref")
                .orElseThrow().getOwnerGroup())
                .isEqualTo("billing");
    }
}
```

**Lưu ý kỹ thuật quan trọng:** Import đúng của `@DirtiesContext` là `org.springframework.test.annotation.DirtiesContext`; annotation thuộc Spring Test. Annotation class trên đã dùng import phù hợp.

**Cơ chế:**

- `PostgreSQLContainer` chạy PostgreSQL thật; `withDatabaseName("billing_group")` chọn database test được tạo trong container.
- `@ServiceConnection` cung cấp JDBC connection details của container; không dùng production URL.
- `replace=NONE` giữ container DataSource thay vì để JPA slice thay bằng H2.
- `getDatabaseProductName()` và `getCatalog()` kiểm tra đang kết nối đúng engine/database.
- `@DirtiesContext(AFTER_CLASS)` tránh giữ Spring context trỏ container đã dừng sau class trong cache dùng chung cho những test classes sau. Đây là lựa chọn rõ cho class-scoped container, nhưng có chi phí rebuild; không phải mọi test cần annotation này.
- Một `ShippingPostgresTest` muốn database khác có thể dùng một container khác với `withDatabaseName("shipping_group")` và configuration id riêng; điều đó làm tốn tài nguyên hơn schema-per-group trên một server.

**Chú ý đặc biệt về cache/container:** Testcontainers JUnit `static @Container` sống trong phạm vi class; Spring TestContext có thể cache `ApplicationContext` lâu hơn và tái sử dụng nó sau khi container dừng. Không dùng container static-per-class cộng shared cached Spring context mà không có lifecycle strategy. Tùy suite, ưu tiên container dưới Spring bean lifecycle, singleton container kéo dài toàn suite, hoặc `@DirtiesContext` khi thích hợp.

### 9.3. Testcontainers là resource thật, không phải cơ chế cô lập mọi thứ

Một container riêng theo group giúp cô lập DB server, nhưng không tự giúp test parallel nếu chúng cùng dùng Redis/Kafka hoặc files/ports bên ngoài. Nếu một class gọi `System.setProperty` global hay sửa shared static state, DB isolation không ngăn được lỗi đó.

Mặt khác, Testcontainers JUnit 5 extension thông thường chỉ được kiểm chứng cho **sequential test execution**; nếu bật JUnit parallel, cần xem tài liệu Testcontainers và chọn lifecycle/coordination phù hợp. Không dựa vào thứ tự test classes để giữ container alive.

## 10. PostgreSQL schema-per-group khi muốn dùng chung một server

Đây là cách tiết kiệm hơn so với một PostgreSQL instance/container mỗi group, nhưng cần chặt chẽ ở schema provisioning, connection pool và migrations.

### 10.1. Tạo schemas trước khi Spring context/JPA khởi động

Ví dụ chạy trên **một PostgreSQL database test-only** có tên `it_suite`:

```sql
CREATE SCHEMA IF NOT EXISTS test_billing;
CREATE SCHEMA IF NOT EXISTS test_shipping;
```

Các lệnh này phải chạy **trước** khi Hibernate validation hoặc Flyway migrations phụ thuộc schemas. Có thể dùng Testcontainers `withInitScript` với SQL resource được thêm vào `src/test/resources`, hoặc job/bootstrap tạo schemas bằng connection admin test-only.

**Sai vòng đời:** Tạo schema trong `@BeforeEach` nhưng để Flyway/JPA bootstrap trước đó; test có thể fail khi context đang tạo beans. Cần gắn schema creation vào container/database provisioning trước Spring application context.

### 10.2. Kết nối đúng schema bằng JDBC và Hibernate

Với PostgreSQL JDBC driver, `currentSchema` thiết lập search path của connection. Cấu hình mẫu **minh họa, không dùng production credentials**:

```properties
# Chỉ mô tả giá trị; phải thay bằng host/port DB TEST-ONLY.
spring.datasource.url=jdbc:postgresql://127.0.0.1:5432/it_suite?currentSchema=test_billing
spring.jpa.properties.hibernate.default_schema=test_billing
spring.flyway.schemas=test_billing
spring.flyway.default-schema=test_billing
spring.jpa.hibernate.ddl-auto=validate
```

Cho nhóm shipping, thay nhất quán `test_billing` thành `test_shipping`. Thêm driver, Testcontainers connection details và đúng config của project. Đừng trộn container URL runtime với hard-code localhost trong CI.

- `currentSchema` điều khiển lookup của unqualified SQL identifiers trên JDBC connection.
- `hibernate.default_schema` có thể giúp Hibernate qualify SQL/table mappings khi appropriate.
- `spring.flyway.schemas/default-schema` điều khiển các schemas và migration history của Flyway khi project có Flyway.
- `ddl-auto=validate` phù hợp khi schema đã được migrations tạo; không tự tạo tables.
- Với native SQL ghi đầy đủ `public.table`, search path **không đổi** table được truy cập. Review native queries trong tests.

### 10.3. Kiểm chứng schema bằng SQL thật

```sql
SELECT current_database();
SELECT current_schema();
SHOW search_path;

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('test_billing', 'test_shipping')
ORDER BY table_schema, table_name;
```

Kỳ vọng mỗi group kết nối tới database `it_suite` và current schema phù hợp. Đừng chỉ assert chuỗi config property; một DataSource wrapper/pool có thể dùng URL khác. Nếu có nhiều DataSources, kiểm tra từng bean thực.

### 10.4. Flyway/Liquibase và schema history

Mỗi group nên có migration history riêng hoặc migration configuration rõ ràng. Nếu Billing/Shipping cùng chạy Flyway vào một `public.flyway_schema_history` và cùng table names nhưng target schemas khác, có thể tạo va chạm hoặc hiểu nhầm một group đã migrate.

Quy tắc:

1. Tạo schemas trước.
2. Chọn schema migration location/history table cho từng group.
3. Chạy migrations đúng group, đúng version.
4. Assert table/index/constraint thuộc đúng schema.
5. Hibernate validate bằng DataSource/schema tương ứng.
6. Dọn schema **chỉ khi không còn group nào đang sử dụng nó**.

Liquibase cũng có default schema và tracking tables tương tự nhưng tên properties/API khác. Đừng copy nguyên Flyway properties sang Liquibase.

### 10.5. Không ghép raw group input vào `CREATE SCHEMA`

Identifiers không thể dùng JDBC `?` placeholder theo cách của value parameters. Nếu tool provisioning cần dynamic schema names, tạo tên từ một hàm whitelist/slug/hash đáng tin, quote identifiers bằng API/procedure đúng và cấp role test chỉ có quyền phù hợp. Tuyệt đối không nối một header `X-Tenant` tùy ý thành `DROP SCHEMA ... CASCADE`.

## 11. Isolation trong NoSQL và các dịch vụ khác

Những dịch vụ không có SQL schema vẫn có concept **namespace** ở những tầng khác nhau. Chọn ranh giới phù hợp với khả năng thật của provider.

### 11.1. MongoDB: database hoặc collection riêng

Ví dụ:

```properties
spring.data.mongodb.database=it_ci942_billing
```

Group shipping dùng một MongoDB database name khác. Đây là lựa chọn có ý nghĩa vì MongoDB indexes/collections/validators thường nằm trong database. Test `@DataMongoTest` cần đảm bảo instance/URI là test-only, qua Testcontainers `@ServiceConnection` hoặc properties được định nghĩa rõ.

Cảnh báo:

- `@DataMongoTest` không mặc nhiên rollback mọi writes như `@DataJpaTest`. Dùng fixture cleanup chủ động hoặc database riêng.
- `dropDatabase()` chỉ chấp nhận nếu database **được xác định chắc chắn thuộc run**; không dùng trên DB dev/shared.
- Index setup/migrations có thể chạy lúc context bootstraps; tạo database/collection scope trước.
- Test sessions/transactions trên MongoDB cần topology phù hợp (replica set nếu có multi-document transaction).
- Hai MongoDB databases vẫn dùng chung server/resources và một user admin vẫn có thể xem cả hai.

Nếu muốn tiết kiệm số databases, dùng collection names có group prefix. Nhưng test queries/repositories phải chỉ vào đúng collection, và các index definitions cũng phải được quản lý riêng.

### 11.2. Redis: key prefix, không `FLUSHDB` bừa bãi

Các keys:

```text
it:run42:billing:session:user_1
it:run42:shipping:session:user_1
```

không đụng nhau. Ở Spring Cache, có thể cấu hình cache name/key prefix, còn với `RedisTemplate` dùng key builder/serializer xác định. **Mọi thao tác** `get`, `set`, `delete`, `scan`, pipelines, Lua scripts và background cleanup phải tôn trọng prefix; chỉ thêm prefix trong một code path là chưa đủ.

Các cảnh báo:

- `FLUSHALL` xóa toàn server; `FLUSHDB` xóa toàn logical DB. Không dùng khi các groups chia sẻ Redis.
- Redis Cluster không hỗ trợ tách logical DB bằng `SELECT n` như một Redis standalone deployment; đừng dựa vào database index như khả năng portable.
- Prefix không tự cung cấp ACL isolation. Với Redis Enterprise/namespaces do vendor cung cấp, kiểm tra hợp đồng cụ thể.
- TTL và eviction vẫn chia sẻ resource budget; key của group A có thể ảnh hưởng áp lực bộ nhớ của B.
- Cleanup theo prefix nên có giới hạn và chạy **sau khi group đã dừng**, thường dùng `SCAN` với pattern đã kiểm soát; không dùng `KEYS *` trên hệ thống shared lớn.
- Nếu keys được hash-tag cho Redis Cluster, đừng vô tình đẩy toàn bộ workload tới một hash slot nóng mà không kiểm soát.

### 11.3. Elasticsearch/OpenSearch: index/alias per group

Ví dụ:

```text
it-ci942-billing-orders
it-ci942-shipping-orders
```

Mỗi index có mapping/settings riêng; tránh tên index cố định như `products-test` khi nhiều jobs chạy song song.

Cần kiểm tra:

- Test setup tạo đúng mappings, analyzers, aliases.
- Queries dùng index của group, không wildcard `it-*` quá rộng.
- Cleanup xóa **đúng index đã tạo**, không xóa toàn bộ test indices của job khác.
- Elasticsearch gần real-time: vừa index xong không tự được bảo đảm search nhìn thấy trước refresh; dùng refresh policy hoặc bounded await phù hợp.
- Một index riêng không cô lập cluster CPU, shard counts, security roles và quotas; perf/failover cần môi trường cao hơn.
- Nếu dùng aliases, verify mỗi alias chỉ trỏ tới indices thuộc group tương ứng.

### 11.4. Kafka: topic và consumer group id là hai lớp riêng

Một Kafka consumer group id mới chỉ tách **offset bookkeeping**, không tách message storage. Nếu hai test groups cùng đọc một topic, cả hai vẫn có thể nhận messages của nhau tùy filters/subscriptions/offsets. Cần:

- Topic riêng cho group hoặc unique run/shard suffix khi phù hợp.
- Consumer group id riêng cho mỗi group/subscription.
- Kiểm soát topic auto-creation, partition count, retention và cleanup.
- Assert event key/correlation id, schema/version và consumption offset behavior.
- Đừng delete một topic đang dùng chung chỉ để reset test data.

Ví dụ:

```text
Topic billing:   it.ci942.billing.events
Group billing:   it.ci942.billing.consumer

Topic shipping:  it.ci942.shipping.events
Group shipping:  it.ci942.shipping.consumer
```

**Cùng topic + group id riêng không bằng isolation của messages.** Nếu kiến trúc bắt buộc dùng topic chung, sử dụng correlation/test-run id và consumer filters đúng, nhưng vẫn phải đối mặt shared retention/race và cleanup.

### 11.5. RabbitMQ, S3/MinIO và filesystems

- RabbitMQ hỗ trợ virtual hosts: vhost riêng tách queues/exchanges theo namespace, nhưng users/roles/server resources vẫn cần kiểm soát.
- Object storage có thể dùng bucket riêng hoặc prefix `it/run/group/`. Nếu dùng prefix, mọi list/delete operations phải đặt đúng prefix, không xóa bucket root.
- Local filesystem: tạo temporary directory riêng cho test method/class bằng JUnit `@TempDir`; không dùng chung một đường dẫn `./tmp/test-output.json` cho mọi workers.
- Database test data không phải dạng tài nguyên duy nhất: environment variables, static caches, `System.setProperty`, clocks, ports và files cũng có thể gây cross-test interference.

## 12. Setup/cleanup lifecycle và cách tránh “test này xóa test kia”

Một quy trình chuẩn theo ownership:

```text
CI job starts
   │
   ├─ allocate run id (unique)
   │
   ├─ provision namespace per group
   │    ├─ DB/schema/collection/index/topic/key prefix
   │    └─ run schema/index migrations
   │
   ├─ start Spring test context with fixed group config
   │
   ├─ execute tests (parallel only when supported)
   │
   ├─ stop producers/consumers/background workers
   │
   ├─ cleanup only resources owned by group
   │
   └─ final cleanup/lease for orphaned resources
```

### 12.1. Cleanup phải biết chắc resource thuộc mình

Ví dụ lệnh sau **mang tính phá hủy**:

```sql
DROP SCHEMA test_billing CASCADE;
```

Chỉ chạy khi database test-only đã được chứng minh và không còn test nào dùng schema đó. Không tự động chạy trong một JVM đang chia sẻ PostgreSQL server với developer/staging.

Với MongoDB, `dropDatabase()` chỉ an toàn khi connection string và database name là test-only; với Redis, tránh `FLUSHDB`; với Elasticsearch, delete index cụ thể; với S3, xóa đúng bucket/prefix ownership.

### 12.2. Quy định một chủ sở hữu duy nhất

Nếu test group A cấp schema/index và group B cũng tự “ensure exists”/“cleanup” cùng resource, các job parallel dễ race. Nên có một component provisioning chịu trách nhiệm lifecycle, còn test methods chỉ tạo dữ liệu riêng trong scope đó.

Một workflow robust cần nhận biết:

- **owner-run-id**
- **resource-name**
- **creation-time**
- **group/shard**
- **cleanup-policy**
- **TTL/lease**
- **environment marker (test-only)**

Có thể lưu metadata trong CI artifacts hoặc test resource registry; không cần trộn vào dữ liệu business tables.

### 12.3. Không dùng fixed sleep để “đợi dọn xong”

`Thread.sleep(1000)` không bảo đảm Kafka consumer đã stop, Elasticsearch refresh đã hoàn tất hoặc PostgreSQL connections đã release. Dùng bounded waits dựa trên điều kiện thực: container readiness, connection health, index status, consumer assignment, observable event count, queue drained; đặt timeout rõ và report khi fail.

## 13. Spring Boot TestContext cache, `@DynamicPropertySource` và `@DirtiesContext`

Spring TestContext có cơ chế cache Spring `ApplicationContext` để tăng tốc. Nếu hai classes có cấu hình giống nhau, chúng có thể tái dùng context; đó là tối ưu hợp lệ nhưng nguy hiểm khi URL/namespace là biến mutable ngoài context identity.

### 13.1. Không đổi một global namespace field ở `@BeforeEach`

Anti-pattern:

```java
static String currentGroup = "billing";

@BeforeEach
void setGroup() {
    currentGroup = "shipping";
}
```

Nếu DataSource/Flyway/RedisTemplate đã bootstrap trước `@BeforeEach`, đổi `currentGroup` không khiến beans rebuild; test có thể vẫn dùng namespace cũ. Đây chỉ là snippet minh họa; đừng dùng nó trong project runnable.

### 13.2. `@DynamicPropertySource` có thời điểm và cache semantics

`@DynamicPropertySource` cho phép thêm dynamic properties như PostgreSQL container JDBC URL:

```java
@DynamicPropertySource
static void configure(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
}
```

Snippet cần một `static postgres` và imports phù hợp, không phải test class độc lập. Spring Framework docs cảnh báo khi base class dùng inherited dynamic property method nhưng values đổi giữa subclasses, test context cache có thể tái sử dụng context sai; `@DirtiesContext` hoặc distinct configurations là một cách tránh.

**Tách contexts theo resource identity** (URL/schema/group), không chỉ theo tên Java test class hiển thị. Nếu muốn nhiều tests cùng group chia sẻ context, bảo đảm container/namespace còn sống **ít nhất** tới khi context không được reuse nữa.

### 13.3. `@DirtiesContext` không phải cleanup dữ liệu mặc định

`@DirtiesContext` đánh dấu Spring ApplicationContext bị dirty và cần close/rebuild theo class/method mode; nó không tự drop MongoDB collections, xóa Redis prefixes hoặc delete Kafka topics. Dùng khi cần đổi bean configuration/context; dùng SQL cleanup/transaction/isolated DB cho dữ liệu.

Thêm `@DirtiesContext` cho mọi test làm suite chậm và có thể che thiết kế ownership tệ. Ưu tiên cấu hình group rõ và context caching có kiểm soát.

### 13.4. Testcontainers lifecycle tương tác với Spring cache

Một static `@Container` thuộc JUnit class có lifecycle class-scoped. Nhưng Spring context cache có thể sống lâu hơn class; context tái sử dụng DataSource/clients trỏ container đã dừng.

Các lựa chọn:

- Một class/container riêng, `@DirtiesContext(AFTER_CLASS)` để đóng context đúng hạn.
- Container được quản lý dưới Spring bean lifecycle để sống cùng context khi test architecture hỗ trợ.
- Singleton container sống toàn suite (quản lý start/stop rõ và không gắn `@Container` JUnit per-class sai cách).
- Test configuration identity khác cho resources khác, không reuse context nhầm.
- Với parallel execution, kiểm tra mức hỗ trợ của Testcontainers/JUnit version; không mặc định static container pattern là parallel-safe.

## 14. Parallel execution: isolation phải ở tất cả shared resources

JUnit 5 có thể được cấu hình chạy test methods/classes song song. Khi bật, những rủi ro sau cần được kiểm tra:

- Hai classes cùng dùng một PostgreSQL schema và cùng `TRUNCATE` tables.
- Hai groups cùng chạy Flyway migrate lên một schema.
- Redis key prefix không chứa CI run id, khiến hai jobs viết đè.
- Kafka topic name cố định, consumer group.id cố định gây rebalance/offset conflicts.
- Elasticsearch index name cố định và test A delete index test B đang query.
- Static mutable test fixtures, fixed temp files và shared ports.
- Testcontainers static field bị stop khi nhóm khác vẫn còn Spring context giữ references.
- H2 in-memory cùng tên trong **một JVM**, contexts khác nhau vẫn có thể kết nối cùng named database.

### 14.1. Khi nào có thể chạy song song an toàn?

Khi resources tách biệt theo ownership và không còn global mutable state quan trọng, việc chạy classes/groups song song phù hợp hơn. Với một group dùng chung một database, bạn vẫn có thể chạy các test methods theo tuần tự hoặc phân tách fixture keys/transactions đủ rõ.

Không tự nhận “parallel-safe” vì dùng `@Transactional`. SQL cleanup, async consumers và out-of-transaction writes vẫn có thể va chạm.

### 14.2. Muốn test song song thật cần kiểm chứng

Một bước QA hữu ích: chạy full suite nhiều lần với random ordering và parallel settings đã được dự định cho CI. Kết quả cần pass độc lập thứ tự, không phải chỉ 1 lần tình cờ. Khi fail, log run id/group id/resource name và SQL/consumer operations đủ để truy vết, **nhưng không log secrets/PII**.

## 15. Migrations, index creation và schema history có cùng scope không?

Tạo namespace chưa đủ nếu migration tool vẫn trỏ vào schema mặc định hoặc global metadata.

### 15.1. SQL schema-per-group

Với Flyway, kiểm tra `schemas`, `default-schema`, `locations` và schema history table. Với Liquibase, kiểm tra default schema và tracking tables. Với Hibernate, kiểm tra `default_schema` và DDL auto mode.

Một test dùng schema A nhưng Flyway migrate vào `public` có thể pass nếu Hibernate cũng đọc `public`, trong khi group B đang vô tình dùng chung các tables. Do đó assert `current_schema()`, SQL catalog và migration history location.

### 15.2. MongoDB indexes per group

Nếu nhóm A và B dùng riêng MongoDB databases/collections, index creation phải được thực hiện ở mỗi collection đang dùng. Annotations như `@CompoundIndex` mô tả mapping nhưng auto-index creation phụ thuộc configuration; đừng cho rằng một lần tạo index global áp dụng tất cả databases.

### 15.3. Elasticsearch mappings per index

Index riêng phải được tạo với settings/analyzers/mappings mong đợi. Chỉ thay tên index trong query mà không tạo mapping có thể khiến dynamic mapping thay đổi schema và test không thực sự kiểm tra production behavior.

### 15.4. Kafka schema registry và topics

Topic per group không tự tách schema registry subjects nếu subject naming strategy vẫn dùng tên cố định. Nếu serializer/Schema Registry là phần của test, kiểm tra subject name/version và cleanup policy theo group hoặc dùng registry instance riêng khi cần.

## 16. Test assertions nào chứng minh isolation tốt hơn việc “assert count=0”?

Một test `repository.count()==0` có thể pass vì transaction rollback trước đó hoặc cleanup toàn cục đã vô tình xóa data của nhóm khác. Để bảo vệ isolation thực, cần kết hợp:

1. **Identity:** verify JDBC URL/current_database/current_schema/Mongo database/Redis prefix/index/topic thật.
2. **Positive own data:** group A lưu và đọc dữ liệu của A qua repository/client thực.
3. **Negative other data:** group B không thấy A data (nếu dùng chung server nhưng khác namespace); không query bằng wildcard toàn cục.
4. **Same business key:** A và B có thể dùng cùng key nếu scope độc lập như thiết kế.
5. **No destructive cleanup:** xóa dữ liệu A không xóa B; kiểm tra bằng một integration scenario có kiểm soát.
6. **Order independence:** chạy hai nhóm đảo thứ tự, hoặc trong CI parallel mode được hỗ trợ.
7. **Correct migrations:** schema/index names thực đúng scope.
8. **No production access:** datasource/connection metadata khớp test-only config và credentials hạn chế.

Ở project H2, assertions trên metadata URL và cùng `shared-ref` bảo vệ đúng **tầng connection identity**. Để chứng minh cleanup không ảnh hưởng xuyên schema trên PostgreSQL, cần setup cả hai scopes trong một test integration có quyền giới hạn và assert sau khi cleanup A rằng B vẫn còn data; đó là một bài mở rộng có rủi ro destructive thao tác nên chỉ chạy trong DB ephemeral.

## 17. Troubleshooting: những lỗi thường gặp

### Lỗi A. Hai test classes dùng cùng `jdbc:h2:mem:testdb`

**Triệu chứng:** Test phụ thuộc thứ tự hoặc unique key bị trùng khi class khác chạy.  
**Khắc phục:** Đặt tên DB khác theo group/run; xác nhận JDBC URL từ `DataSource` thực. `DB_CLOSE_DELAY=-1` giữ named database tồn tại trong JVM, vì vậy càng cần tên riêng.

### Lỗi B. `@DataJpaTest` tự thay PostgreSQL DataSource bằng H2

**Triệu chứng:** Test “Postgres” xanh nhưng native JSONB query chưa từng được thực hiện.  
**Khắc phục:** Khi dùng PostgreSQL test-only container, đặt `@AutoConfigureTestDatabase(replace=NONE)` và xác minh `DatabaseMetaData.getDatabaseProductName()`/`current_database()`.

### Lỗi C. Test B vẫn kết nối DB của A

**Triệu chứng:** DataSource metadata không khớp group B.  
**Khắc phục:** Đừng đổi một static variable sau khi context bootstrap; phân biệt context configuration, xem `@DynamicPropertySource` inheritance/cache; `@DirtiesContext` khi thực sự cần.

### Lỗi D. Spring context lấy connection tới container đã dừng

**Triệu chứng:** Các tests đầu pass, test class sau báo connection refused.  
**Khắc phục:** Đồng bộ Testcontainers lifecycle và Spring context cache; dùng context-managed bean, suite singleton lifecycle hoặc `@DirtiesContext(AFTER_CLASS)` cho class-scoped containers.

### Lỗi E. Flyway migrate vào `public` dù test muốn `test_billing`

**Triệu chứng:** Table nằm sai schema hoặc duplicate migration history.  
**Khắc phục:** Provision schema trước context; đồng bộ JDBC `currentSchema`, Hibernate default schema, Flyway schemas/default-schema; kiểm tra PostgreSQL catalog thật.

### Lỗi F. `@BeforeEach` tạo schema quá muộn

**Triệu chứng:** JPA bootstrap/validation đã fail trước khi method chạy.  
**Khắc phục:** Tạo schema ở container init script, database bootstrap hoặc Spring initialization stage trước Flyway/Hibernate.

### Lỗi G. Dùng `TRUNCATE` hoặc `DROP SCHEMA CASCADE` của group khác

**Triệu chứng:** Parallel tests thất bại ngẫu nhiên.  
**Khắc phục:** Mỗi group có ownership metadata, cleanup chỉ resources của mình; destructive actions chỉ trong DB test-only.

### Lỗi H. Redis `FLUSHDB` xóa key của tất cả groups

**Triệu chứng:** Cache tests fail khi một suite chạy cleanup.  
**Khắc phục:** Prefix per group/run và cleanup theo prefix/TTL; không flush shared DB. Nếu cần full flush, cấp Redis instance riêng.

### Lỗi I. Kafka consumer group id đã unique nhưng topic vẫn chung

**Triệu chứng:** Test nhận messages từ group khác.  
**Khắc phục:** Topic riêng per group hoặc correlation/filtering đúng; group.id riêng chỉ tách offsets, không tách message store.

### Lỗi J. MongoDB test để lại data qua methods

**Triệu chứng:** Unique index violation/order-dependent tests.  
**Khắc phục:** `@DataMongoTest` không mặc định rollback; dùng DB/collection riêng và cleanup có kiểm soát.

### Lỗi K. Elasticsearch delete wildcard xóa index của job khác

**Triệu chứng:** Search tests đột ngột nhận index not found.  
**Khắc phục:** Index name có run/group/shard, delete **đúng indices đã tạo**, không wildcard toàn hệ.

### Lỗi L. Tests xanh riêng nhưng fail khi parallel

**Triệu chứng:** Dữ liệu bị mất hoặc duplicate key, static caches mang state cũ.  
**Khắc phục:** Kiểm kê tất cả shared resources, xác định groups có thể chạy parallel, dùng unique namespaces, bounded waits và test order-independent.

### Lỗi M. Schema tách biệt nhưng role vẫn xem được mọi schema

**Triệu chứng:** Test security sai kết luận “tenant B không thể xem A”.  
**Khắc phục:** Isolation naming khác authorization; kiểm tra GRANT/REVOKE và principal/tenant policy.

### Lỗi N. Test cleanup làm hỏng dữ liệu staging

**Triệu chứng:** `DROP DATABASE` hoặc `deleteAll` tác động môi trường không intended.  
**Khắc phục:** Test-only connection details, restricted roles, explicit environment markers và allowlisted resource names; **không** thực thi destructive cleanup trên production/staging shared.

## 18. Checklist review chiến lược test data isolation

- [ ] “Test group” đã được định nghĩa rõ (class/module/job/shard).
- [ ] Mỗi group có resource ownership name rõ, có run/shard suffix khi chạy song song.
- [ ] Test biết engine thật và JDBC URL/schema/namespace của mình.
- [ ] Không có production URL/secret trong test code và CI config.
- [ ] `@DataJpaTest` không vô tình replace DataSource thành embedded DB khác với mục tiêu.
- [ ] Spring TestContext cache và dynamic properties không làm lẫn group config.
- [ ] Testcontainers lifecycle khớp Spring context lifecycle.
- [ ] SQL migrations/indices/history được tạo trong schema/database đúng.
- [ ] Với PostgreSQL schema, `currentSchema`/`search_path`/Hibernate/Flyway config nhất quán.
- [ ] SQL schema naming không bị hiểu nhầm là authorization boundary.
- [ ] Test rollback không được coi là cleanup cho async/HTTP/NoSQL/broker.
- [ ] Mongo databases/collections được tách và cleanup đúng scope.
- [ ] Redis mọi key path có prefix, không dùng `FLUSHDB` trên server shared.
- [ ] Elasticsearch indices/aliases có unique names và correct mappings.
- [ ] Kafka topics **và** consumer groups được scoped theo yêu cầu.
- [ ] S3 buckets/prefixes/temporary files không bị xóa chéo.
- [ ] Resource names được sanitize/hash, không lộ PII hay inject SQL identifiers.
- [ ] Setup chạy trước schema-dependent Spring beans; teardown sau khi background tasks đã dừng.
- [ ] Parallel tests được kiểm tra thực bằng full-suite runs/ordering.
- [ ] Cleanup biết chắc owner-run-id và chỉ dùng tài nguyên test-only.

## 19. Bài tập và tình huống vận dụng

### Bài 1. Cùng business key, khác database

Chạy `BillingDataTest` và `ShippingDataTest`. Hai lớp đều ghi `shared-ref` với `ownerGroup` khác nhau. Quan sát JDBC metadata chứng minh chúng đang dùng hai named H2 databases; giải thích vì sao chỉ kiểm tra `count()==0` là chưa đủ.

### Bài 2. Cố tình dùng chung một H2 database

Trên nhánh thực hành riêng, đổi cả hai classes thành `jdbc:h2:mem:shared_group` và tắt rollback nếu muốn quan sát left-over state. Thiết kế cleanup test-only an toàn. Không dùng data production. Giải thích vì sao class-level context cache/`create-drop`/rollback có thể che vấn đề trong một lượt test đơn giản.

### Bài 3. Tách schemas trong PostgreSQL

Trong PostgreSQL container test-only, tạo `test_billing` và `test_shipping` trước context; cấu hình currentSchema/Flyway/Hibernate cho mỗi group. Lưu cùng reference vào hai schemas, kiểm tra `current_schema()` và table catalog, rồi cleanup schema A và assert schema B còn dữ liệu.

### Bài 4. Redis prefix theo CI run

Viết một key builder từ run id + group + subject; thêm test verify cùng user id không collide giữa run42/run43 hoặc billing/shipping. Sau đó dùng Redis container kiểm tra `GET/SET/TTL` thực sự với prefixed keys.

### Bài 5. MongoDB per database

Dùng MongoDB Testcontainers, cấu hình hai database names riêng. Seed một document cùng `_id` vào cả hai; assert repository/template của mỗi group chỉ thấy dữ liệu của mình. Không dùng `dropDatabase()` nếu URL/database chưa được xác định rõ thuộc test.

### Bài 6. Kafka topic isolation

Tạo hai topics có unique CI run/group suffix và hai consumer group IDs riêng, publish cùng event key. Assert các consumer nhận đúng messages của topic mình. Tiếp đó chứng minh đổi **chỉ** group.id mà giữ chung topic không tự tách data.

### Bài 7. Parallel và TestContext cache

Bật parallel tests theo cơ chế được JUnit/Testcontainers hỗ trợ, chạy suite nhiều lần và thu log dataSource URL/group names. Nếu có lỗi context reuse, điều chỉnh lifecycle/scope, không thêm `Thread.sleep` hoặc xóa DB toàn cục để “chữa”.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao dùng database riêng mạnh hơn chỉ đặt table prefix?

**Đáp án:** Database là một boundary của catalog/connection; table prefix chỉ đổi tên objects trong cùng schema/database. Tuy nhiên database riêng vẫn không tự cung cấp security nếu cùng privileged credentials.

**Câu 2.** PostgreSQL `search_path` có ngăn user query sang schema khác không?

**Đáp án:** Không. Nó điều khiển tên object không được qualify; quyền truy cập phải dùng GRANT/REVOKE/roles và policy riêng.

**Câu 3.** Hai `@DataJpaTest` đều rollback, có cần resource isolation không?

**Đáp án:** Có thể vẫn cần, vì migrations/DDL, sequences, shared cleanup, async operations hoặc tests không nằm trong cùng transaction. Rollback không thay isolation ownership.

**Câu 4.** Tại sao `@BeforeEach` không phải lúc thích hợp để tạo PostgreSQL schema phục vụ Hibernate validation?

**Đáp án:** Spring ApplicationContext/JPA/Flyway thường khởi tạo trước test method lifecycle; schema phải được cấp trước giai đoạn đó.

**Câu 5.** Thêm `@AutoConfigureTestDatabase(replace=NONE)` có luôn an toàn không?

**Đáp án:** Không. Nếu DataSource trỏ production, nó sẽ không bị thay. Chỉ dùng khi đã cấu hình một database test-only xác thực như H2 explicit URL hoặc Testcontainers.

**Câu 6.** Hai Redis key prefixes khác nhau có cho phép một group dùng `FLUSHDB` an toàn không?

**Đáp án:** Không. `FLUSHDB` xóa toàn logical database, không chỉ prefix; dùng cleanup scoped hoặc Redis instance riêng.

**Câu 7.** Kafka topic chung nhưng consumer group IDs khác có cô lập messages không?

**Đáp án:** Không. Consumer groups tách offsets/processing coordination; cả hai vẫn đọc cùng topic messages.

**Câu 8.** Spring context cache và static Testcontainers `@Container` có thể xung đột thế nào?

**Đáp án:** Container dừng sau class nhưng Spring context vẫn cached và bị tái dùng, làm DataSource trỏ một server không còn chạy. Cần lifecycle strategy phù hợp.

**Câu 9.** MongoDB `@DataMongoTest` có tự rollback mọi write sau mỗi method không?

**Đáp án:** Không mặc định như JPA transactional test; cần tách database/collection hoặc cleanup rõ ràng.

**Câu 10.** Muốn chứng minh test group A không xóa dữ liệu B, nên assert gì?

**Đáp án:** Identity/ownership resources, kết quả trước–sau cleanup có kiểm soát trên cả hai scopes và không có unscoped destructive operation; làm trên test-only environment.

## 21. Tài liệu chính thức

- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataJpaTest`, test databases, transactions và test slices.
- [Spring Boot 3.5 – Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, container lifecycle và Spring context caching.
- [Spring Framework – Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): test ApplicationContext reuse.
- [Spring Framework – `@DynamicPropertySource`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html): dynamic properties và inheritance.
- [Testcontainers – JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): static `@Container`/lifecycle/parallel support notes.
- [Testcontainers – Container Lifecycle and Spring](https://testcontainers.com/guides/testcontainers-container-lifecycle/): lưu ý container per-class và Spring context cache.
- [PostgreSQL – Schemas](https://www.postgresql.org/docs/current/ddl-schemas.html): namespaces, schema qualification, `search_path` và security.
- [pgJDBC – Connection Parameters](https://jdbc.postgresql.org/documentation/use/): `currentSchema` JDBC option.
- [Flyway – Schemas and Default Schema](https://documentation.red-gate.com/fd/flyway-schemas-setting-277579234.html): migration scope và history.
- [Spring Data MongoDB – Testing/Mapping](https://docs.spring.io/spring-data/mongodb/reference/): repository, converter, collection names và index management.
- [Redis – Key Naming and SCAN](https://redis.io/docs/latest/commands/scan/): key traversal/cleanup considerations.
- [Elasticsearch – Index Management](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-mgmt.html): indices, aliases và mappings.
- [Apache Kafka – Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): `group.id` và consumer group behavior.

**Kết luận:** Tách test data đúng nghĩa phải thống nhất **scope, resource identity, startup, migration, transaction, context caching, cleanup và an toàn quyền truy cập**. Dùng database hoặc schema riêng cho nhóm SQL, namespace/collection/index/topic đúng provider cho các dịch vụ khác, gắn tên với run/group/shard và tuyệt đối tránh thao tác destructive toàn cục. Một test chỉ thực sự độc lập khi không thể đọc/ghi/xóa tài nguyên của nhóm khác trong phạm vi mà thiết kế tuyên bố.
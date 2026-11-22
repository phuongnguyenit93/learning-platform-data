# Kiểm thử repository với database thật trong Testcontainers — Spring Boot và PostgreSQL

## 1. Tại sao không chỉ mock repository hoặc dùng H2?

Repository trong Spring Boot không đơn thuần là một interface Java: lời gọi đi qua Spring Data proxy, EntityManager, Hibernate, JDBC driver rồi được PostgreSQL thực thi dưới các ràng buộc SQL và transaction. Một Mockito mock có thể trả về đúng dữ liệu giả nhưng không chứng minh bất cứ điều gì về SQL generated, mapping column, unique constraint, index, migration hoặc cách engine xử lý transaction.

H2 in-memory có giá trị cho một số test nhanh nhưng không thay thế hoàn toàn PostgreSQL: `ILIKE`, `JSONB`, `ON CONFLICT`, PostgreSQL array, các loại timestamp, thứ tự NULL, collations, identity, isolation và error SQLSTATE có thể khác. Khi production dùng PostgreSQL, ít nhất một integration suite phải chạy qua **PostgreSQL thật**.

**Mục tiêu:** tạo PostgreSQL 16 bằng Testcontainers, áp dụng Flyway schema migration, kiểm Spring Data JPA repository bằng JUnit 5 trong Spring Boot 3.5/Java 17+, xác nhận CRUD, JPQL, native SQL, constraints, pagination và rollback. Không cần cài PostgreSQL trên host và không dùng fixed port 5432.

Sau bài, bạn có thể tự phân biệt test logic/service, JPA slice và full application integration; biết áp dụng `@DataJpaTest`, `@AutoConfigureTestDatabase(replace=NONE)`, `@ServiceConnection`, `TestEntityManager`, `flush/clear`; kiểm lỗi DB ở đúng thời điểm; và thiết kế CI Docker-enabled có khả năng tái lập.

## 2. Các lớp test và phạm vi hợp đồng

| Loại test | Context | Database | Đảm bảo được |
| --- | --- | --- | --- |
| Mockito unit test | Không hoặc MockitoExtension | Mock | Nhánh business logic tương tác với repository |
| `@DataJpaTest` với H2 | JPA slice | H2 | Một phần mapping/JPQL, không bảo đảm dialect |
| `@DataJpaTest` với Testcontainers | JPA slice | PostgreSQL thật | Query, mapping, constraints, transaction JPA |
| `@SpringBootTest` + Testcontainers | Full Boot | PostgreSQL thật | Service/transaction/wiring cùng repository |
| End-to-end trên môi trường triển khai | Nhiều services | Tuỳ hệ thống | API + network + DB + vận hành |

Nếu đang hỏi “`findBySku` có sinh SQL đúng, trả Optional và ánh xạ field không?”, **đừng mock chính repository ấy**. Nếu đang hỏi “service trả lỗi gì khi repository không tìm thấy SKU?”, mock repository trong unit test là phù hợp. Chọn layer theo mục tiêu, không chọn layer chỉ vì một test chạy nhanh.

### Testcontainers thực sự chạy gì?

~~~text
JUnit test JVM
  |
  +-- @Testcontainers / @Container
  |     +-- Docker API discovery
  |     +-- pull postgres:16-alpine if needed
  |     +-- create/start PostgreSQL container
  |     +-- wait until PostgreSQL is ready
  |
  +-- @DataJpaTest Spring context
        +-- @ServiceConnection JDBC/Flyway details
        +-- DataSource / JPA / Hibernate / transaction manager
        +-- Flyway V1 migration
        +-- Hibernate ddl-auto=validate
        +-- ProductRepository proxy
                 |
                 +-- SQL -> JDBC -> PostgreSQL mapped port
~~~

`PostgreSQLContainer` tạo server PostgreSQL thật. Docker API endpoint JVM dùng để start container **khác** host/port JVM dùng để gửi SQL. Mapped host port thường ngẫu nhiên, vì vậy không hardcode `jdbc:postgresql://localhost:5432/...`.

## 3. Những annotation bắt buộc và ý nghĩa

Một repository test theo Boot 3.5 có thể bắt đầu như sau:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class ProductRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Đây là snippet mở đầu, test class hoàn chỉnh ở phần sau.

- `@DataJpaTest` tạo JPA slice, quét entities và Spring Data repositories, cấu hình `TestEntityManager`.
- `@AutoConfigureTestDatabase(replace=NONE)` ngăn auto-configuration đổi datasource sang H2/embedded database nếu dependency đó có trên classpath.
- `@Testcontainers` kích hoạt JUnit Jupiter extension.
- `@Container` static quản lý một PostgreSQLContainer cho cả test class; instance field có thể tạo container từng method.
- `@ServiceConnection` do Spring Boot `spring-boot-testcontainers` cung cấp, tạo JDBC/Flyway connection details từ container.
- `@DataJpaTest` meta-register SpringExtension cho Jupiter, không cần thêm `@ExtendWith(SpringExtension.class)` lặp lại.
- `@DataJpaTest` mặc định test-managed transactional và rollback sau mỗi test method.

**Lưu ý lifecycle:** static `@Container` thuộc JUnit extension và stop sau class. Nếu Spring TestContext cache giữ ApplicationContext sang class khác, cached DataSource có thể trỏ vào container đã dừng. Bộ demo có một repository test class; phần sau chỉ cách quản lý container cùng lifecycle với context khi mở rộng.

## 4. Project thực hành có thể chạy

Cấu trúc:

~~~text
repository-postgres-test/
  settings.gradle
  build.gradle
  src/main/java/example/catalog/
    CatalogApplication.java
    Product.java
    ProductRepository.java
  src/main/resources/
    application.properties
    db/migration/V1__create_products.sql
  src/test/java/example/catalog/
    ProductRepositoryPostgresTest.java
  .github/workflows/
    repository-tests.yml
~~~

Yêu cầu: Java 17+, Gradle wrapper phù hợp Spring Boot 3.5, Docker-compatible runtime (Docker Engine/Desktop hoặc môi trường tương thích được hỗ trợ), quyền pull image. Tên file và package trong ví dụ đã thống nhất.

## 5. settings.gradle

~~~groovy
rootProject.name = 'repository-postgres-test'
~~~

## 6. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'

    implementation 'org.flywaydb:flyway-core'
    implementation 'org.flywaydb:flyway-database-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }
    reports {
        html.required = true
        junitXml.required = true
    }
}
~~~

### Vì sao chọn những dependency này?

`spring-boot-starter-data-jpa` mang Hibernate, Spring Data repositories và transactions; `org.postgresql:postgresql` là JDBC driver. `flyway-core` + `flyway-database-postgresql` cho Flyway nhận PostgreSQL: với các Flyway versions hiện đại, hỗ trợ PostgreSQL nằm trong database-specific module. `spring-boot-starter-test` đem Jupiter, AssertJ, Mockito và TestContext utilities; `spring-boot-testcontainers` cung cấp `@ServiceConnection`; Testcontainers `junit-jupiter` và `postgresql` cung cấp lifecycle và PostgreSQLContainer.

Không thêm H2 cho integration test này. Nếu dự án lớn có H2 dành cho tests khác, `replace=NONE` vẫn giữ PostgreSQL.

**Version note:** Spring Boot 3.5.0/Java 17 là mốc demo, không phải tuyên bố đây là bản mới nhất. Dùng dependency management của Boot để tránh lệch Testcontainers/JUnit modules, không phối các major versions tùy ý.

### Vì sao maxParallelForks=1?

Đây là baseline ít tranh CPU/RAM. Nhiều Gradle test JVMs có Spring TestContext cache độc lập và có thể khởi tạo nhiều DB containers. Sau khi đo runner resources/CI throughput, có thể tăng forks có kiểm soát. `forkEvery=1` tăng chi phí JVM/context và giảm cache reuse, nên không đặt làm mặc định.

## 7. application.properties

`src/main/resources/application.properties`:

~~~properties
# Flyway is the schema source of truth.
spring.flyway.enabled=true

# Hibernate checks columns and types; it must not recreate tables.
spring.jpa.hibernate.ddl-auto=validate

# No web application is required for JPA slice tests.
spring.jpa.open-in-view=false

# Don't mix schema.sql/data.sql initialization with Flyway.
spring.sql.init.mode=never

spring.jpa.show-sql=false
~~~

Không hardcode `spring.datasource.url/username/password` ở đây. Trong test, Spring Boot lấy connection details từ PostgreSQLContainer qua `@ServiceConnection`.

**Ứng dụng main chạy ngoài test vẫn cần datasource thật** được cấu hình qua environment/secrets. Không nói rằng `java -jar` một mình sẽ tự start Testcontainers: module `spring-boot-testcontainers` đang ở test scope, không phải production daemon provisioner.

## 8. Flyway V1__create_products.sql

`src/main/resources/db/migration/V1__create_products.sql`:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price_cents BIGINT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uk_products_sku UNIQUE (sku),
    CONSTRAINT ck_products_price_nonnegative
        CHECK (price_cents >= 0)
);

CREATE INDEX idx_products_enabled_price_id
    ON products (enabled, price_cents, id);
~~~

### Ý nghĩa DDL

- `id BIGINT GENERATED BY DEFAULT AS IDENTITY` tương thích với JPA `GenerationType.IDENTITY`.
- `sku` không null, tối đa 64 characters và unique.
- `price_cents` không âm, được DB CHECK constraint bảo vệ dù Java validation bị bỏ qua.
- `enabled` có DB default `TRUE`; khi Hibernate gửi boolean explicitly, default này không được áp dụng.
- `created_at TIMESTAMPTZ` do database tự set, có default hiện tại.
- Index có thể hỗ trợ query lọc enabled và sort price/id; PostgreSQL planner mới quyết định dùng index hay sequential scan.

Migrations chạy khi context khởi tạo, trước test transaction. Rollback một test method **không hoàn tác** V1 schema migration; nó rollback rows được seed/ghi trong transaction.

### Dùng migrate, không dùng ddl-auto=create-drop

Nếu đặt `spring.jpa.hibernate.ddl-auto=create-drop`, Hibernate có thể tự tạo schema theo entity và làm CRUD tests PASS dù SQL migration production sai. `validate` phát hiện một số mismatch mapping/column/type, còn test `flyway_schema_history` xác nhận Flyway đã chạy.

Nếu schema đã release, tạo `V2__...sql` thay vì sửa V1 làm Flyway checksum fail. Không gọi Flyway repair tùy tiện để bỏ qua thay đổi production DDL.

## 9. CatalogApplication.java

`src/main/java/example/catalog/CatalogApplication.java`:

~~~java
package example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Root package này chứa entity/repository. Spring Boot tìm `@SpringBootConfiguration` và scan đúng mà không cần thêm `@EntityScan` hoặc `@EnableJpaRepositories` cho một project đơn giản.

## 10. Product.java — entity tương thích PostgreSQL

`src/main/java/example/catalog/Product.java`:

~~~java
package example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @Column(name = "name", nullable = false, length = 200)
    private String name;

    @Column(name = "price_cents", nullable = false)
    private long priceCents;

    @Column(name = "enabled", nullable = false)
    private boolean enabled;

    protected Product() {
        // Required by JPA.
    }

    public Product(
            String sku, String name,
            long priceCents, boolean enabled) {

        this.sku = sku;
        this.name = name;
        this.priceCents = priceCents;
        this.enabled = enabled;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public long getPriceCents() {
        return priceCents;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void changePrice(long updatedPriceCents) {
        this.priceCents = updatedPriceCents;
    }

    public void rename(String updatedName) {
        this.name = updatedName;
    }

    public void changeEnabled(boolean value) {
        this.enabled = value;
    }
}
~~~

### Tại sao không map created_at?

`created_at` là DB-only column để minh họa PostgreSQL default. Hibernate `validate` có thể chấp nhận bảng có cột bổ sung ngoài entity mapping; test dùng `JdbcTemplate` để chứng minh DB default được set. Nếu production cần trả createdAt, có thể map `Instant` và refresh/reload entity sau insert, nhưng phải kiểm timestamp/timezone/dialect semantics.

### Tại sao constructor không chặn giá âm?

Test cần đi đến **DB CHECK constraint** để xác nhận Postgres từ chối dữ liệu âm. Trong ứng dụng thật, hãy validate đầu vào ở Java/service/DTO nữa, nhưng Java validation không thay thế DB constraint. Nếu constructor ném sớm, test sẽ không chứng minh CHECK hoạt động.

### Mapping vs migration

`@Column(name="price_cents")` khớp DDL, `@GeneratedValue(IDENTITY)` khớp PostgreSQL identity. DDL UNIQUE/CHECK được định nghĩa ở Flyway, không cần bật Hibernate schema generator để tạo constraints. Hibernate `validate` không bảo đảm kiểm toàn bộ indexes/constraints nên phải có tests database-specific.

## 11. ProductRepository.java

`src/main/java/example/catalog/ProductRepository.java`:

~~~java
package example.catalog;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findBySku(String sku);

    boolean existsBySku(String sku);

    List<Product>
        findByEnabledTrueOrderByPriceCentsAscIdAsc();

    Page<Product> findByEnabledTrue(Pageable pageable);

    @Query("""
           select p from Product p
           where p.priceCents >= :min
             and p.priceCents <= :max
           order by p.priceCents asc, p.id asc
           """)
    List<Product> findByPriceRange(
            @Param("min") long min,
            @Param("max") long max);

    @Query(
        value = """
                SELECT *
                FROM products
                WHERE sku ILIKE CONCAT('%', :fragment, '%')
                ORDER BY id
                """,
        nativeQuery = true)
    List<Product> findBySkuFragmentIgnoreCase(
            @Param("fragment") String fragment);
}
~~~

Phân biệt:

- **Derived query** `findBySku` dựa trên entity field `sku`.
- **JPQL** dùng tên entity `Product` và property `priceCents`.
- **Native SQL** dùng table `products` và column `sku` thật trong PostgreSQL.
- **Page** cần `Pageable`, có thể thêm count query để lấy `totalElements`.
- **Sort** theo price rồi id tie-breaker giữ ổn định với nhiều rows cùng price.
- **ILIKE** là PostgreSQL-specific, phù hợp mục tiêu integration.

`:fragment` được bind an toàn, không dùng string concatenation user input để tạo raw SQL. Tuy nhiên `%`/`_` trong user input vẫn là pattern wildcards của LIKE/ILIKE; nếu business cần **literal substring search** phải escape chúng. Parameter binding chống SQL injection không tự escape wildcard semantics.

## 12. ProductRepositoryPostgresTest.java — JUnit 5 complete

File `src/test/java/example/catalog/ProductRepositoryPostgresTest.java`:

~~~java
package example.catalog;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.TestTransaction;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(
    showSql = false,
    properties = {
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.flyway.enabled=true"
    })
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class ProductRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("catalog_it")
                .withUsername("catalog")
                .withPassword("catalog");

    @Autowired ProductRepository repository;
    @Autowired TestEntityManager entityManager;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void seedRows() {
        repository.saveAll(List.of(
            new Product("P-ALPHA", "Alpha", 1200, true),
            new Product("P-BETA", "Beta", 2500, true),
            new Product("P-GAMMA", "Gamma", 2500, false)
        ));
        repository.flush();
        entityManager.clear();
    }

    @Test
    void connectsToActualPostgres() {
        String database = jdbc.queryForObject(
                "SELECT current_database()", String.class);

        assertEquals("catalog_it", database);
        assertTrue(postgres.isRunning());
    }

    @Test
    void readsProductAndMapsColumns() {
        Product found = repository.findBySku("P-ALPHA")
                .orElseThrow();

        assertNotNull(found.getId());
        assertEquals("Alpha", found.getName());
        assertEquals(1200L, found.getPriceCents());
        assertTrue(found.isEnabled());
    }

    @Test
    void unknownSkuIsEmpty() {
        assertTrue(repository.findBySku("MISSING").isEmpty());
        assertFalse(repository.existsBySku("MISSING"));
    }

    @Test
    void filtersAndSortsEnabled() {
        List<String> skus = repository
                .findByEnabledTrueOrderByPriceCentsAscIdAsc()
                .stream()
                .map(Product::getSku)
                .toList();

        assertEquals(
                List.of("P-ALPHA", "P-BETA"), skus);
    }

    @Test
    void paginatesEnabledProducts() {
        repository.saveAndFlush(
                new Product("P-DELTA", "Delta", 500, true));

        Sort order = Sort.by(
                Sort.Order.asc("priceCents"),
                Sort.Order.asc("id"));

        Page<Product> first = repository.findByEnabledTrue(
                PageRequest.of(0, 2, order));

        assertEquals(3L, first.getTotalElements());
        assertEquals(2, first.getTotalPages());
        assertEquals(
                List.of("P-DELTA", "P-ALPHA"),
                first.getContent().stream()
                        .map(Product::getSku).toList());

        Page<Product> second = repository.findByEnabledTrue(
                PageRequest.of(1, 2, order));

        assertEquals(1, second.getNumberOfElements());
        assertEquals("P-BETA",
                second.getContent().get(0).getSku());
    }

    @Test
    void executesJpqlPriceRange() {
        List<String> skus = repository
                .findByPriceRange(1000, 1500)
                .stream()
                .map(Product::getSku)
                .toList();

        assertEquals(List.of("P-ALPHA"), skus);
    }

    @Test
    void executesNativePostgresIlike() {
        List<String> skus = repository
                .findBySkuFragmentIgnoreCase("alpha")
                .stream()
                .map(Product::getSku)
                .toList();

        assertEquals(List.of("P-ALPHA"), skus);
    }

    @Test
    void dirtyCheckingPersistsUpdate() {
        Product managed = repository.findBySku("P-ALPHA")
                .orElseThrow();
        managed.changePrice(1750);

        entityManager.flush();
        entityManager.clear();

        Product reread = repository.findBySku("P-ALPHA")
                .orElseThrow();

        assertEquals(1750L, reread.getPriceCents());
    }

    @Test
    void deleteRemovesRow() {
        Long id = repository.findBySku("P-BETA")
                .orElseThrow().getId();

        repository.deleteById(id);
        repository.flush();
        entityManager.clear();

        assertFalse(repository.existsBySku("P-BETA"));
    }

    @Test
    void uniqueConstraintRejectsDuplicate() {
        assertThrows(DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                    new Product("P-ALPHA", "Duplicate",
                            100, true)));
        // Do not run more SQL in this failed PostgreSQL transaction.
    }

    @Test
    void checkRejectsNegativePrice() {
        assertThrows(DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                    new Product("P-BAD", "Bad", -5, true)));
        // Database CHECK rejects value during SQL execution.
    }

    @Test
    void databaseTimestampIsCreated() {
        Boolean exists = jdbc.queryForObject(
                """
                SELECT created_at IS NOT NULL
                FROM products
                WHERE sku = ?
                """,
                Boolean.class, "P-ALPHA");

        assertEquals(Boolean.TRUE, exists);
    }

    @Test
    void flywayMigrationApplied() {
        Long count = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM flyway_schema_history
                WHERE success = TRUE
                """,
                Long.class);

        assertNotNull(count);
        assertTrue(count >= 1);
    }

    @Test
    void transactionRollsBackAcrossBoundary() {
        String sku = "P-ROLLBACK";
        repository.saveAndFlush(
                new Product(sku, "Temporary", 10, true));

        assertTrue(repository.existsBySku(sku));

        TestTransaction.flagForRollback();
        TestTransaction.end();

        try {
            Long remaining = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM products WHERE sku = ?",
                    Long.class, sku);
            assertEquals(0L, remaining);
        } finally {
            TestTransaction.start();
        }
    }
}
~~~

**14 methods `@Test`** được viết trong file này. `@BeforeEach` tạo dữ liệu chung trong test-managed transaction. Hai test constraint mong đợi exception, do đó PASS khi database thực sự từ chối các statements.

### Mỗi method đang chứng minh gì?

| Test | Lớp được kiểm |
| --- | --- |
| connectsToActualPostgres | JDBC tới database thật, không chỉ H2 |
| readsProductAndMapsColumns | Entity mapping + derived query |
| unknownSkuIsEmpty | Optional/exists semantics |
| filtersAndSortsEnabled | Derived filter và sort |
| paginatesEnabledProducts | Page content, count, tie-breaker |
| executesJpqlPriceRange | JPQL và named parameters |
| executesNativePostgresIlike | PostgreSQL SQL dialect |
| dirtyCheckingPersistsUpdate | JPA dirty checking + flush/clear |
| deleteRemovesRow | DELETE và requery |
| uniqueConstraintRejectsDuplicate | Database UNIQUE |
| checkRejectsNegativePrice | Database CHECK |
| databaseTimestampIsCreated | DB default CURRENT_TIMESTAMP |
| flywayMigrationApplied | Versioned migration history |
| transactionRollsBackAcrossBoundary | Spring test transaction rollback |

Đây là expected coverage dựa trên source code, **không phải kết quả Gradle đã chạy**.

## 13. Seed dữ liệu và test isolation

Fixture mỗi method gồm:

| SKU | price_cents | enabled |
| --- | ---: | --- |
| P-ALPHA | 1200 | true |
| P-BETA | 2500 | true |
| P-GAMMA | 2500 | false |

Các test không nên phụ thuộc method order. `@DataJpaTest` mặc định tạo transaction cho test method; `@BeforeEach` chạy trong test-managed transaction đó, nên seed rows rollback sau mỗi test. Điều này khác Flyway migrations, vốn chạy khi context khởi động và **không rollback** sau từng method.

Nếu một test tắt transaction hoặc dùng `@Commit`, fixture data có thể còn lại sang method khác. Khi đó phải cleanup cụ thể hoặc dùng database/schema riêng. Không assume static container tự tạo dữ liệu sạch giữa methods: container giữ process, rollback/fixtures mới giữ isolation.

### Sequence ID không nhất thiết rollback

PostgreSQL sequences có thể tăng dù transaction inserts bị rollback. Vì vậy đừng assert `id == 1` cho một test method nếu suite có nhiều methods. Chỉ assert ID non-null hoặc sử dụng ID được repository trả về; đừng hardcode identity values.

## 14. Flush và clear: chứng minh SQL thật

JPA giữ managed entities trong first-level persistence context. Nếu gọi `save` rồi `findById` với cùng ID, EntityManager có thể trả lại object đã managed thay vì roundtrip từ DB.

So sánh fragment:

~~~java
Product p = repository.save(new Product(
        "P-EXTRA", "Extra", 100, true));

Product maybeManaged = repository.findById(p.getId())
        .orElseThrow();
~~~

Điều này **không** chứng minh tất cả column mapping và SELECT được chạy như bạn tưởng.

Làm rõ SQL boundary:

~~~java
Product saved = repository.saveAndFlush(new Product(
        "P-EXTRA", "Extra", 100, true));

entityManager.clear();

Product fromDb = repository.findById(saved.getId())
        .orElseThrow();
~~~

Các fragments này cần test transaction/repository, không thêm vào class đầy đủ vì sẽ thay số methods. `flush` đẩy pending changes đến JDBC/DB; `clear` detach managed entities để lần đọc sau không bị first-level context che. `flush` **không phải commit**: rows có thể đã INSERT thật trong DB nhưng vẫn rollback cuối method.

### Identity generation nuance

Với PostgreSQL identity column và JPA `GenerationType.IDENTITY`, Hibernate có thể phải thực thi INSERT sớm để lấy ID, ngay cả trước explicit flush. Đó không phải lý do bỏ kiểm flush: nó giúp thống nhất thời điểm phát hiện SQL errors với inserts/updates/deletes có batching/deferred behavior.

### Dirty checking vs detached entity

Một entity loaded trong transaction được quản lý; sửa field rồi flush sẽ tạo UPDATE. Sau `entityManager.clear()`, object cũ detached, sửa nó tiếp không tự update database. Nếu cần persist detached changes, phải merge/save theo JPA semantics và kiểm kết quả thực.

## 15. Vì sao test constraint phải assert sau flush?

Trong PostgreSQL:

- Duplicate SKU vi phạm UNIQUE constraint: SQLSTATE `23505`.
- Giá âm vi phạm CHECK: SQLSTATE `23514`.
- Sau lỗi statement trong transaction, các câu SQL tiếp theo có thể trả `25P02` (“current transaction is aborted”).

Vì vậy test:

~~~java
assertThrows(
    DataIntegrityViolationException.class,
    () -> repository.saveAndFlush(
        new Product("P-ALPHA", "Duplicate", 100, true)));
~~~

là đúng hướng; nó buộc repository gửi SQL và kiểm Spring exception translation. `save` mà chưa flush có thể trả về trước khi constraint được DB kiểm (tùy ID strategy và Hibernate), làm negative test false PASS/FAIL khó giải thích.

**Sau `assertThrows` đừng query tiếp trong cùng PostgreSQL transaction**, vì DB có thể đang ở aborted state. Spring rollback cuối test dọn trạng thái. Nếu thật sự cần query sau lỗi, dùng một transaction/savepoint boundary được thiết kế rõ hoặc một test riêng.

### Validation phía Java khác constraint database

Nếu gắn `@Min(0)` hay constructor guard vào `priceCents`, code có thể ném exception trước khi gửi SQL; vậy test chỉ chứng minh Java validation, không chứng minh CHECK. Sample chủ động giữ constructor đơn giản để negative price đi tới Postgres. Production vẫn nên có validation phía API/service **và** DB constraint.

### SQLSTATE vs exception message

Nếu business logic cần phân biệt unique/check, có thể đi xuống cause chain tìm `java.sql.SQLException.getSQLState()` rồi assert `23505`/`23514`. Nhưng Hibernate/Spring wrappers thay đổi theo versions, còn error message có thể phụ thuộc locale/driver. Đừng viết test chỉ dựa toàn bộ string message.

## 16. Test rollback bằng TestTransaction

Một cách sai là dùng test method A INSERT và test method B mong không tìm thấy row của A. JUnit không bảo đảm A chạy trước B; B có thể PASS dù rollback hỏng.

`TestTransaction` giúp test có một controlled transaction boundary trong **cùng method**:

1. Test transaction do `@DataJpaTest` tạo được dùng để seed/write.
2. `TestTransaction.flagForRollback()` đánh dấu rollback.
3. `TestTransaction.end()` kết thúc transaction test và rollback.
4. JDBC query sau đó dùng connection/transaction khác, xác nhận record không tồn tại.
5. `TestTransaction.start()` khôi phục một test-managed transaction để afterTest callback cleanup bình thường.

Ví dụ đầy đủ đã nằm trong `transactionRollsBackAcrossBoundary` và dùng `try/finally` để restart ngay cả khi assertion thất bại.

Không dùng `TestTransaction` bên ngoài Spring TestContext-managed transaction. Với `@Transactional(propagation=NOT_SUPPORTED)` ở test, hoặc pure unit test, bạn không có test transaction đang hoạt động để end.

### Những trường hợp rollback mặc định không bao trùm

- HTTP server với `@SpringBootTest(RANDOM_PORT)` xử lý request ở thread/transaction khác test caller.
- Async/scheduled tasks dùng thread pool khác.
- `REQUIRES_NEW` transaction có thể commit độc lập.
- Flyway migration chạy lúc context initialization.
- External Kafka/Redis side effects.
- JDBC operations trên DataSource/transaction manager khác.

Phải phân biệt test-managed transaction, Spring-managed transaction và application-managed transaction. Đừng dùng `assertTimeoutPreemptively` trong transactional test nếu chưa kiểm ThreadLocal semantics: code chạy ở thread khác có thể không tham gia rollback.

## 17. Pagination, sorting và count query

Phân trang cần test nhiều hơn một trang trống. Trong sample, thêm P-DELTA price 500, enabled true; tổng enabled rows là 3. Page size 2 phải có:

- Page 0: P-DELTA và P-ALPHA.
- Page 1: P-BETA.
- `getTotalElements()==3`.
- `getTotalPages()==2`.

`Page<T>` có total count; `Slice<T>` thường không cần count đầy đủ. Với custom native queries có JOIN/GROUP BY, count query do framework sinh tự động có thể không đúng; hãy assert totalElements trên fixtures chứa duplicates/filters và khai báo `countQuery` khi cần.

**ORDER BY phải ổn định:** khi nhiều rows cùng `priceCents`, sort thêm `id`. Nếu chỉ order by price, PostgreSQL không cam kết thứ tự rows đồng giá giữa runs/page boundaries.

## 18. JPQL vs native PostgreSQL queries

### JPQL

~~~java
@Query("""
       select p from Product p
       where p.priceCents >= :min and p.priceCents <= :max
       order by p.priceCents, p.id
       """)
List<Product> range(@Param("min") long min,
                    @Param("max") long max);
~~~

`Product` là JPA entity name và `priceCents` là Java property. Đó không phải table/column SQL.

### Native PostgreSQL

~~~java
@Query(
    value = """
            SELECT *
            FROM products
            WHERE sku ILIKE CONCAT('%', :term, '%')
            ORDER BY id
            """,
    nativeQuery = true)
List<Product> search(@Param("term") String term);
~~~

`products`/`sku` là PostgreSQL table/column; `ILIKE` là operator DB-specific. Cả hai là **fragments minh họa**; file runnable đã định nghĩa các methods tương ứng.

Native SQL nên dùng parameters bound, không nối trực tiếp input thành câu SQL. Đối với literal substring search, cần escape wildcard `%` và `_` của LIKE. Với Unicode/collation phức tạp, phải test locale cụ thể vì case folding có thể khác tiếng Anh ASCII.

## 19. Có nên dùng @Sql để seed fixtures?

`@Sql` hữu ích khi nhiều repository test classes dùng dataset cố định hoặc cần SQL INSERT ngoài entity mapping:

~~~java
@Sql(
    scripts = "/sql/products.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
~~~

Đây là annotation fragment, cần file ở `src/test/resources/sql/products.sql`, imports và test class. `@Sql` có transaction modes, ví dụ `@SqlConfig(transactionMode=ISOLATED)` có thể làm fixture được committed trước test và **không rollback cùng test**. Nếu dùng, phải thiết kế cleanup rõ.

Các lựa chọn:

| Fixture strategy | Lợi ích | Rủi ro |
| --- | --- | --- |
| `@BeforeEach` qua repository | Dễ đọc, entity đúng | Chỉ kiểm data có thể tạo qua JPA |
| `TestEntityManager` | Flush/clear rõ | Thay đổi persistence context |
| `JdbcTemplate` raw SQL | DB-only columns/legacy rows | Cần quản lý table/column names |
| `@Sql` files | Datasets lớn/versioned | Transaction mode và cleanup |
| Flyway migration | Schema source of truth | Không nên làm fixture per method |
| Separate database per test | Isolation mạnh | Startup chậm, cần Docker capacity |

Nếu test cần kiểm repository đọc raw SQL row chưa được Hibernate seed, dùng JDBC/`@Sql` là một chiến lược tốt. Không xóa production migrations để dọn test data.

## 20. @ServiceConnection vs @DynamicPropertySource

Sample dùng `@ServiceConnection` vì Spring Boot 3.5 hỗ trợ connection details từ `PostgreSQLContainer`, bao gồm JDBC và Flyway.

Một lựa chọn khác khi cần property custom:

~~~java
@DynamicPropertySource
static void databaseProperties(
        DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
}
~~~

Fragment này giả định có static `postgres`, imports và test class. **Không thêm đồng thời cả hai approaches** mà không biết priority; nếu app có Flyway connection URL riêng, phải kiểm Flyway dùng đúng DB như JPA.

### Vì sao không dùng jdbc:tc:postgresql URL ở đây?

Testcontainers còn hỗ trợ JDBC URL dạng `jdbc:tc:postgresql:16-alpine:///catalog_it`, có thể start container theo JDBC connection lifecycle. Đây là alternative hợp lệ nhưng khác ownership; bài ưu tiên explicit PostgreSQLContainer để có `@ServiceConnection`, kiểm `isRunning()` và quản lý lifecycle minh bạch.

## 21. Static @Container và Spring TestContext cache

Static `@Container` trong JUnit Jupiter thường sống **một test class**, không mặc nhiên toàn suite. Spring TestContext cache có thể giữ ApplicationContext qua nhiều classes cùng cache key. Nếu class A stop DB sau khi chạy nhưng class B reuse cached context, DataSource có thể trỏ vào container đã stopped.

### Spring-managed container bean

Khi nhiều classes chia context, Spring Boot 3.5 cho phép gắn container lifecycle vào ApplicationContext qua test configuration:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
~~~

Đây là snippet cần imports, và classes dùng `@Import(PostgresTestConfig.class)`. Spring quản lý bean lifecycle, có thể đóng DB khi cached context đóng, thay vì JUnit extension đóng ngay cuối class A. Có thể cân nhắc `@ImportTestcontainers` theo Boot docs.

Không gắn đồng thời `@Container` Jupiter lifecycle lên Spring-owned bean mà không xác định ai sở hữu stop/cleanup.

### Reusable containers và CI

Testcontainers `withReuse(true)` là tính năng opt-in/experimental, không phù hợp cho CI phổ thông theo tài liệu chính thức: nó có thể giữ container/data qua runs và khiến test nondeterministic. Trên shared runners, đừng bật để tiết kiệm startup mà thiếu data isolation/cleanup policy.

## 22. Chạy Gradle trên máy dev

Linux/macOS:

~~~bash
./gradlew clean test
./gradlew test --tests '*ProductRepositoryPostgresTest'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
.\gradlew.bat test --tests '*ProductRepositoryPostgresTest'
~~~

Cần có Gradle wrapper file tương ứng. Nếu task UP-TO-DATE, Gradle có thể không thực thi tests mới; để chạy lại:

~~~bash
./gradlew test --rerun-tasks
~~~

`--rerun-tasks` ép dependency tasks chạy lại, nên không dùng tổng build wall time làm PostgreSQL startup benchmark. Test logs/reports có thể nằm ở:

~~~text
build/test-results/test/TEST-*.xml
build/reports/tests/test/index.html
~~~

### Kết quả dự kiến

14 `@Test` methods trong source được thiết kế để PASS khi Docker/PostgreSQL/Flyway versions phù hợp. Hai test `uniqueConstraintRejectsDuplicate` và `checkRejectsNegativePrice` chủ động assert exception được DB ném — đây là **PASS expected**, không phải một SQL failure làm test fail. Không có stdout giả định cụ thể về container port/startup duration.

Bài chưa thực thi Gradle hoặc Docker; các outcomes ở đây là thiết kế/expected behavior, không phải bằng chứng runtime đã thu được.

## 23. CI GitHub Actions chạy PostgreSQL Testcontainers

`.github/workflows/repository-tests.yml`:

~~~yaml
name: PostgreSQL Repository Integration Tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  jpa-tests:
    runs-on: ubuntu-24.04
    timeout-minutes: 30

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Docker preflight
        shell: bash
        run: |
          set -euo pipefail
          docker version
          docker info --format 'Docker server={{.ServerVersion}}'
          df -h
          df -i

      - name: Run repository tests
        shell: bash
        run: |
          chmod +x ./gradlew
          ./gradlew --no-daemon clean test --stacktrace

      - name: Diagnostics on failure
        if: failure()
        shell: bash
        run: |
          docker ps -a || true
          docker system df || true
          df -h || true

      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: postgres-jpa-test-results
          path: |
            build/test-results/test/
            build/reports/tests/test/
          if-no-files-found: warn
          retention-days: 7
~~~

Workflow này chạy **trực tiếp trên Ubuntu VM**, không thêm job-level `container:` và không cần khai báo `services.postgres` (vì Testcontainers đã quản lý Postgres). Docker thường có sẵn ở GitHub-hosted Ubuntu runner nhưng preflight vẫn cần xác nhận.

Trên GitLab/Kubernetes runner, phải provision Docker API-compatible runtime và mapped-port route phù hợp: Docker-in-Docker, socket passthrough hoặc managed remote runtime theo security policy. Không mở Docker API TCP không TLS trên untrusted network và không cấp host socket cho PR từ fork không tin cậy.

Lưu JUnit reports với `if: always()` để phân loại Docker missing, Flyway failure, SQL assertion hoặc test skipped. Không upload Docker credentials, TLS private key, DB test secrets hoặc shared daemon resources của jobs khác.

## 24. Tối ưu hiệu năng mà không bỏ integration coverage

Một container start có thể tốn thời gian kéo image, Docker create/start, PostgreSQL init và wait strategy. Spring context còn cần Flyway migrations, Hibernate metadata scanning và Hikari pool. Tách số đo:

~~~text
Docker image pull/cache lookup
    |
postgres.start() and DB ready
    |
Spring @DataJpaTest context + Flyway + Hibernate validate
    |
@BeforeEach seed rows
    |
repository method execution
    |
transaction rollback
    |
container stop/cleanup
~~~

Nếu CI chậm, đo đúng boundary trước:

- Cold image pull khác warm image cache.
- Context cache hit khác cache miss.
- Gradle Test task wall khác một repository method latency.
- Một static container/class khác instance container/method.
- Nhiều Gradle forks/CI jobs có thể nhân containers/RAM usage.
- `@DirtiesContext` sau mỗi method thường gây nhiều context loads không cần thiết.
- `@DataJpaTest` thường nhẹ hơn full `@SpringBootTest` cho chỉ repository, nhưng đừng thay integration/full test khi cần business wiring.

**Không dùng hard-coded timeout assertion** để bắt buộc `postgres.start()<2s` trên shared CI. Docker/network/registry/runner specs khác nhau; muốn performance regression gate cần baseline nhiều runs, median/p95 và controlled machine.

## 25. Troubleshooting theo lỗi thực tế

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| No valid Docker environment | Daemon/socket/TLS | Docker preflight ở đúng job |
| Ryuk privilege denied | Runner policy | Dedicated runtime hoặc cleanup plan |
| Image 401/403/429 | Registry | Token/mirror/rate limit |
| Postgres exit 137 | OOM/SIGKILL | Cgroup RAM/Gradle forks |
| No space left | Docker layers/inodes | df -h, df -i, docker system df |
| JDBC connection refused | Host/mapped port | getJdbcUrl, host/port route |
| Flyway unsupported DB | Thiếu database-specific module | flyway-database-postgresql |
| Flyway checksum mismatch | Migration V1 đã sửa | New migration/version governance |
| Relation products missing | Flyway không apply/schema sai | Check startup logs/history |
| Hibernate validate error | Entity vs SQL schema | Compare @Column with DDL |
| SQL 23505 | Unique violation | Check SKU, catch at SQL flush |
| SQL 23514 | CHECK violation | Verify price and constraint |
| SQL 25P02 | Transaction aborted | Stop queries/rollback |
| Page total wrong | Count-query/filters | Seed enough cases, assert totals |
| Test ignored/skipped | JUnit tags/conditions | Mandatory CI gate |
| Cached context points to stopped DB | Lifecycle mismatch | Spring-owned container |
| Slow startup | Cold image/context/Flyway | Measure each stage |

### Flyway startup failure không phải lỗi repository

Nếu Flyway không tạo `products`, repository test sẽ fail khi context load hoặc first query. Không “sửa” bằng cách tự CREATE TABLE trong `@BeforeEach`: đó là che mất lỗi migration production. Fix Flyway module/script/migration compatibility.

### Sau lỗi constraint không chạy query khác

Postgres transaction có thể aborted sau duplicate/check violation. Nếu test vẫn query `findAll`, nhận `25P02` thay vì dữ liệu cần kiểm. Chỉ assert exception rồi để transaction rollback, hoặc tách transaction boundaries đúng.

### Không tự chuyển sang H2 khi Docker unavailable

Nếu production SQL cần PostgreSQL, H2 fallback khiến CI xanh nhưng integration contract không được kiểm. Route test tới Docker-enabled runner hoặc fail rõ với môi trường thiếu; không skip toàn bộ bắt buộc.

## 26. Migrations, concurrency và khóa dữ liệu

CRUD tests đủ để chứng minh basic repository, chưa chứng minh những hợp đồng nâng cao:

- Atomic stock reservation và lost updates.
- Optimistic locking `@Version`/`OptimisticLockingFailureException`.
- Pessimistic row locks `@Lock(PESSIMISTIC_WRITE)`.
- Deadlocks và retry policy.
- Concurrent inserts cùng SKU, unique race.
- Transactions với `REQUIRES_NEW`/async threads.
- PostgreSQL `JSONB`/`ON CONFLICT`/partial indexes.

Các bài này cần **hai hoặc nhiều transactions/threads độc lập** với barriers/timing rõ. Một `@DataJpaTest` single-thread method không chứng minh isolation/concurrency. Đừng để thread phụ chạy trong test-managed transaction rồi mặc định transaction context được truyền qua; Spring transaction thường thread-bound.

### SQL indexes không chứng minh bằng ba test rows

V1 tạo index nhưng PostgreSQL optimizer có thể dùng sequential scan với bảng nhỏ. Kiểm functional result trong JUnit; performance/index plan nếu cần phải dùng dataset đủ lớn, `EXPLAIN (ANALYZE, BUFFERS)` và môi trường kiểm soát. Đừng assert query luôn dùng index trong fixture ba rows.

## 27. Checklist thực hành

- [ ] Test dùng PostgreSQL thật, không mock repository hoặc thay bằng embedded H2.
- [ ] Docker-compatible runtime reachable từ test JVM.
- [ ] `@DataJpaTest` tải đúng entities và Spring Data repositories.
- [ ] `@AutoConfigureTestDatabase(replace=NONE)` giữ datasource thật.
- [ ] `@ServiceConnection` và `spring-boot-testcontainers` có mặt.
- [ ] Image PostgreSQL được pin, không hardcode host port 5432.
- [ ] Flyway V1 migration thực thi với `flyway-database-postgresql`.
- [ ] Hibernate `ddl-auto=validate` không tự tạo/drop schema.
- [ ] JPA entity `@Column` khớp DDL.
- [ ] Fixture dữ liệu có enabled/disabled, giá bằng nhau và boundary cases.
- [ ] Flush rồi clear trước khi xác nhận database roundtrip.
- [ ] Test derived query, JPQL, native PostgreSQL ILIKE.
- [ ] Pagination test totalElements, totalPages và stable ordering.
- [ ] UNIQUE/CHECK test thực hiện SQL và assert exception ở flush boundary.
- [ ] Không query tiếp trong PostgreSQL transaction đã aborted.
- [ ] Database-created defaults được kiểm qua JDBC.
- [ ] TestTransaction/rollback không phụ thuộc test order.
- [ ] Static container lifecycle không lệch cached context ở nhiều classes.
- [ ] Không bật reusable containers trong CI thiếu isolation.
- [ ] Test không assert exact sequence-generated IDs giữa methods.
- [ ] CI có Docker preflight, JUnit reports và policy không skip integration tests.
- [ ] Không lộ registry/database secrets khi upload logs.
- [ ] Performance được đo theo DB/container/context/SQL, không gộp bừa.

## 28. Kết luận

**Kiểm thử repository với database thật nghĩa là JPA → JDBC → PostgreSQL server thực sự chạy SQL, migrations và constraints.** Bộ ví dụ dùng `@DataJpaTest` để khởi động JPA slice, `@ServiceConnection` nối PostgreSQLContainer, `@AutoConfigureTestDatabase(replace=NONE)` ngăn H2 thay DB, Flyway tạo schema và Hibernate validate mapping.

14 tests trong project kiểm đọc/ghi/xóa, sort, phân trang, JPQL, PostgreSQL ILIKE, unique/CHECK constraints, DB default, migration và rollback. Khi áp dụng vào dự án, giữ fixture isolation, flush/clear đúng boundary, tránh cached context trỏ container đã dừng và chạy integration suite trong CI có Docker. Mock repository vẫn hữu ích ở **unit layer**, nhưng không thay các bài kiểm SQL thật này.

### Tài liệu chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @DataJpaTest, TestEntityManager, @AutoConfigureTestDatabase.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): @ServiceConnection, FlywayConnectionDetails, Spring-managed containers.
- [Spring Boot 3.5 — Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html): Flyway và Hibernate DDL.
- [Spring Framework 6.2 — Test Transactions](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): TestTransaction, rollback, thread boundary.
- [Spring Framework 6.2 — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html): @Sql và transaction modes.
- [Testcontainers Java — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQLContainer và mapped JDBC URL.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): @Testcontainers và static/instance @Container.
- [Testcontainers Java — Reuse](https://java.testcontainers.org/features/reuse/): experimental reuse, không phù hợp CI.
- [Flyway — PostgreSQL Database](https://documentation.red-gate.com/flyway/reference/database-driver-reference/postgresql-database): Flyway database plugin.
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): named parameters, JPQL, native queries.
- [PostgreSQL 16 — Constraints](https://www.postgresql.org/docs/16/ddl-constraints.html): UNIQUE/CHECK/identity.
- [PostgreSQL 16 — Error Codes](https://www.postgresql.org/docs/16/errcodes-appendix.html): 23505/23514/25P02.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): useJUnitPlatform, reports.

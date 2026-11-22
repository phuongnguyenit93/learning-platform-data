# Spring Data JPA: Embedded database, database thật và @AutoConfigureTestDatabase

## 1. Câu hỏi quan trọng: repository test đang dùng database nào?

Một test repository Spring Data JPA có thể lưu entity, truy vấn lại và nhận kết quả xanh với H2. Nhưng query SQL ấy có thể thất bại trên PostgreSQL hoặc MySQL vì khác biệt về SQL dialect, kiểu dữ liệu, collation, constraint, transaction, index và migration. Ngược lại, không phải mỗi phép kiểm tra entity mapping đều đáng trả chi phí khởi động PostgreSQL.

Hai chiến lược bổ sung nhau:

- **Embedded database** (ví dụ H2 in-memory) cho nhiều test JPA mapping và repository đơn giản: nhanh, ít hạ tầng, dễ tạo fixture.
- **Database thật cùng engine production** (ví dụ PostgreSQL chạy trong Testcontainers) cho native SQL, constraint, schema migrations, locking, isolation, indexing hoặc những hành vi đặc thù của vendor.

Có một bẫy quan trọng: với `@DataJpaTest`, Spring Boot có thể **thay thế DataSource** của ứng dụng bằng embedded database. Vì vậy dù test cấu hình một PostgreSQL container, nó vẫn có thể truy vấn H2 nếu quy tắc replacement không đúng.

**Phiên bản quyết định:** Trong Spring Boot **3.3**, `@AutoConfigureTestDatabase` có mặc định `replace = Replace.ANY`; từ **3.4**, thêm `Replace.NON_TEST` và thay mặc định thành `NON_TEST` để nhận diện tốt hơn datasource được cung cấp từ test container. Bài dùng Java 17 và Spring Boot 3.3, rồi giải thích điểm khác biệt khi nâng version.

## 2. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Phân biệt **embedded**, **in-memory**, **file-backed**, **database server thật** và **database production**.
2. Hiểu phạm vi `@DataJpaTest`, repository/entity scanning, `TestEntityManager` và transaction rollback mặc định.
3. Giải thích `@AutoConfigureTestDatabase` làm gì, ba giá trị `Replace.ANY`, `AUTO_CONFIGURED`, `NONE` của Boot 3.3 và tham số `connection`.
4. Kiểm tra datasource bằng `DatabaseMetaData` thay vì đoán engine từ URL hoặc tên test.
5. Viết được H2 tests và PostgreSQL Testcontainers tests cùng kiểm tra một repository.
6. Dùng `@ServiceConnection`/`@DynamicPropertySource` đúng vai trò, không để datasource container vô tình bị thay bằng H2.
7. Phân biệt `save`, `flush`, `clear`, commit, rollback và dữ liệu do migration/startup task tạo.
8. Giải thích các giới hạn khi dùng H2 thay PostgreSQL cho native SQL, JSONB, unique constraint, collations, transaction isolation và locking.
9. Quản lý Docker-dependent test, test profiles, context cache, data isolation và dữ liệu nhạy cảm an toàn.
10. Lựa chọn phạm vi test nhỏ nhất đủ bắt lỗi: unit, JPA slice, real DB JPA test hoặc full application integration.

## 3. Embedded không đồng nghĩa in-memory, và real không đồng nghĩa production

| Loại database | Ví dụ | Đặc điểm |
| --- | --- | --- |
| Embedded in-memory | `jdbc:h2:mem:catalog` | H2 chạy trong JVM, dữ liệu theo lifecycle connection/DB |
| Embedded file-backed | `jdbc:h2:file:./sandbox/catalog` | H2 trong JVM nhưng lưu trên file, phải cleanup |
| Dedicated database server trong container | PostgreSQL `postgres:16-alpine` qua Testcontainers | Engine/server và JDBC protocol thật, được quản lý tạm thời |
| Test database server dùng chung | PostgreSQL staging/test instance | Engine thật nhưng dễ chia sẻ state và tranh chấp migrations |
| Production database | DB đang phục vụ người dùng thật | **Không được dùng** làm target của automated tests ghi dữ liệu |

H2/HSQLDB/Derby đều có dạng embedded. Một H2 database có thể chạy ở memory hoặc file; `in-memory` mô tả nơi lưu dữ liệu, `embedded` mô tả cách engine được nhúng, nên hai từ không hoàn toàn đồng nghĩa.

Testcontainers PostgreSQL **không phải embedded**. Nó khởi động PostgreSQL server bên trong container, dùng driver/protocol thật. Đây là cách gần engine production hơn mà không chia sẻ production data.

**Không dùng H2 `MODE=PostgreSQL` như bằng chứng “đã kiểm thử trên PostgreSQL”.** Compatibility mode chỉ mô phỏng một phần SQL, không bao phủ đầy đủ MVCC, JSONB, extensions, collation, locking hoặc transaction behavior của PostgreSQL.

## 4. `@DataJpaTest` chọn phạm vi gì?

Spring Boot `@DataJpaTest` là **test slice**. Trong Boot 3.3, theo tài liệu chính thức, nó:

- Nạp entities và Spring Data JPA repositories.
- Cấu hình JPA/Hibernate, transaction manager và test database auto-configuration phù hợp.
- Có thể dựng embedded database khi driver khả dụng.
- Cung cấp `TestEntityManager` cho thao tác persist/flush/clear trong test.
- Mặc định chạy test trong transaction **rollback ở cuối method**.
- Mặc định thường bật show SQL; `@DataJpaTest(showSql = false)` có thể giảm log.
- Không quét các `@Service`/`@Controller` thông thường như full Spring Boot application context.

```java
@DataJpaTest
class RepositoryTest {
    @Autowired
    ProductRepository repository;

    @Autowired
    TestEntityManager entityManager;
}
```

Đoạn trên chỉ là mẫu, các class runnable ở phần 9.

**Mục tiêu test slice:** kiểm tra persistence behavior, không kiểm tra HTTP mapping, controller-service integration, scheduler, message broker hoặc giao tiếp mạng. Nếu cần service thực phụ thuộc repository, có thể `@Import` chính service nhỏ đó vào JPA slice; nếu muốn toàn bộ luồng qua HTTP, cân nhắc `@SpringBootTest`.

### 4.1. Vì sao rollback không tạo database mới mỗi method?

Spring TestContext cache `ApplicationContext` theo cấu hình. H2 datasource và EntityManagerFactory có thể được tái sử dụng qua nhiều methods. Test-managed transaction rollback thường giúp mỗi test không để lại những row chưa được commit, **không phải vì Boot tạo lại database trước từng `@Test`**.

Các tác động chạy ngoài test transaction (migration, bean startup job, code mở `REQUIRES_NEW` hoặc thread khác) không nhất thiết bị rollback theo method.

## 5. `@AutoConfigureTestDatabase` thực sự điều khiển cái gì?

Trong Spring Boot 3.3:

```java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
```

Annotation quyết định **thay thế DataSource** bằng datasource test embedded (nếu thực hiện replacement) và chọn loại embedded database. Nó không tự tạo một PostgreSQL server hay tự bảo đảm schema/migrations.

### 5.1. Ba `Replace` modes của Boot 3.3

| Giá trị | Hành vi |
| --- | --- |
| `Replace.ANY` | Được thay DataSource dù nó do Boot auto-configure hay được người dùng định nghĩa thủ công |
| `Replace.AUTO_CONFIGURED` | Chỉ thay DataSource được auto-configured bởi Boot |
| `Replace.NONE` | Không thay DataSource hiện tại bằng test embedded database |

**Boot 3.3 mặc định `ANY`**, theo Javadoc chính thức; đừng nhầm với mặc định `NON_TEST` xuất hiện từ 3.4.

```java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.ANY
)
class EmbeddedRepositoryTest { }
```

Ví dụ ở trên diễn đạt “muốn dùng datasource embedded nếu có thể”, không nói engine là H2 hay PostgreSQL. Nó cần driver embedded thực sự ở classpath.

### 5.2. Chọn rõ H2 bằng `connection`

```java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY,
        connection = EmbeddedDatabaseConnection.H2
)
class H2RepositoryTest { }
```

Import thêm:

```java
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
```

`connection = H2` chỉ định embedded database khi replacement được thực hiện. Nếu `replace = NONE`, thêm `connection=H2` **không** phải lệnh tự khởi động H2. Ngoài ra, classpath phải có H2 JDBC driver.

### 5.3. Thế nào là DataSource “auto-configured”?

Trong nhiều Spring Boot apps, `DataSourceAutoConfiguration` dựa vào `spring.datasource.*`, driver và HikariCP để tạo DataSource. Đây là đối tượng có thể được `AUTO_CONFIGURED` thay.

Nếu application tự tạo một `@Bean DataSource` thủ công, `AUTO_CONFIGURED` không có ý định thay bean ấy; `ANY` có thể thay. `NONE` giữ nguyên DataSource — kể cả khi nó trỏ nhầm vào database nguy hiểm.

### 5.4. Khi ứng dụng có nhiều DataSources

Javadoc Boot 3.3 nói khi có nhiều `DataSource` beans, test replacement chỉ xem xét **`@Primary` DataSource**. Các datasource phụ, routing datasource hay nhiều persistence units cần được test và bảo vệ riêng.

Không được suy luận rằng một `@AutoConfigureTestDatabase` trên test class làm toàn bộ ứng dụng ngừng kết nối các database ngoài. Xác minh URL, profile và credentials cho **từng** DataSource.

## 6. Quy tắc theo phiên bản: Boot 3.3, 3.4 và 4.x

| Phiên bản | Các mode của `Replace` | Mặc định | Testcontainers |
| --- | --- | --- | --- |
| 3.3.x | `ANY`, `AUTO_CONFIGURED`, `NONE` | `ANY` | Cần ghi `replace=NONE` rõ ràng nếu muốn bảo toàn datasource từ container |
| 3.4–3.5 | Có thêm `NON_TEST` | `NON_TEST` | Cố nhận diện test datasource từ `@ServiceConnection`, `@DynamicPropertySource`, JDBC URL Testcontainers |
| 4.x | Các mode tương ứng nhưng package test thay đổi | `NON_TEST` ở các dòng hiện hành | Cần đối chiếu test modules và imports đúng phiên bản |

`Replace.NON_TEST` được bổ sung trong **Boot 3.4.0**. Nó giúp không thay một DataSource được auto-configured và được nhận diện là **test database**. Các kết nối có metadata container (`@ServiceConnection`), URL do `@DynamicPropertySource` cung cấp và JDBC URL dạng Testcontainers nằm trong các trường hợp nhận diện.

**Nhưng `NON_TEST` không phải hàng rào an toàn tuyệt đối để phân biệt production với staging.** Không được cho phép test có credentials/network truy cập production. Nếu mục tiêu là kết nối PostgreSQL test cụ thể, `replace=NONE` vẫn diễn đạt rõ yêu cầu nhưng phải chắc datasource ấy là test-only.

Trong **Spring Boot 4**, các test annotations được chuyển tới các module/package theo chức năng; không copy imports của ví dụ Boot 3.3 mà không xem migration guide.

## 7. Chọn H2 hay database vendor bằng câu hỏi nghiệp vụ

| Test cần chứng minh | Chọn gì? | Tại sao? |
| --- | --- | --- |
| Entity được persist và query derived method hoạt động? | `@DataJpaTest` + H2 | Nhẹ, phản hồi nhanh |
| `@Column`/basic association mapping? | H2 trước, vendor test cho case nhạy dialect | Bao phủ lỗi cơ bản với chi phí thấp |
| `@Query(nativeQuery=true)` dùng PostgreSQL JSONB/arrays? | PostgreSQL Testcontainers | H2 không phải engine PostgreSQL |
| Unique/index và collation giống production? | Database đúng vendor/config | H2 có semantics khác |
| Transaction isolation và pessimistic locking? | Vendor DB và nhiều transactions | Engine/concurrency behavior là phần cần chứng minh |
| Flyway/Liquibase migrations có chạy trên PostgreSQL? | Container DB + migration thật | Hibernate `create-drop` không kiểm tra scripts |
| Service phối hợp repository nhưng không cần web? | JPA slice + `@Import` service nhỏ hoặc service integration test | Không cần embedded HTTP |
| Controller + service + DB qua real HTTP? | Full Boot context + test DB | JPA slice không bao phủ HTTP |
| Thuật toán tính giá thuần? | JUnit unit test | Không cần database |

H2 không “kém”, PostgreSQL container không “tốt” một cách tuyệt đối. Mục tiêu là **bằng chứng đúng nhất với chi phí phù hợp**.

## 8. Dự án Java 17 và Spring Boot 3.3.0 chạy được

Cùng một entity/repository sẽ được kiểm tra bởi:

1. **H2 tests:** chạy được mà không cần Docker; chứng minh mapper/repository và unique constraint cơ bản.
2. **PostgreSQL Testcontainers tests:** chỉ bật nếu `RUN_PG_TESTS=true` và máy có Docker/runtime tương thích; chứng minh engine thực sự là PostgreSQL.

Dự án dùng **Spring Boot 3.3.0** để imports thống nhất. Đây là bản minh họa kỹ thuật, không phải đề xuất dùng release cũ ở production. Không có database production hoặc network ngoài Testcontainers.

### 8.1. Cấu trúc tệp

```text
jpa-database-choice/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/catalog/
    │   ├── CatalogApplication.java
    │   ├── CatalogProduct.java
    │   └── CatalogProductRepository.java
    └── test/java/example/catalog/
        ├── CatalogRepositoryH2Test.java
        └── CatalogRepositoryPostgresTest.java
```

### 8.2. Gradle settings

**`settings.gradle`:**

```groovy
rootProject.name = 'jpa-database-choice'
```

### 8.3. Gradle build

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.postgresql:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Boot dependency management cung cấp phiên bản phù hợp cho JPA/Hibernate/JUnit/Testcontainers/JDBC drivers. H2 và PostgreSQL drivers chỉ có trên **test runtime classpath**, không bật kết nối database production bằng default credentials.

Với project chỉ dùng để chạy tests như ví dụ, điều này là đủ. Nếu muốn chạy `bootRun` ngoài test, cần khai báo runtime driver và datasource riêng; đừng mặc định ví dụ là một deployment production hoàn chỉnh.

### 8.4. Spring Boot application

**`src/main/java/example/catalog/CatalogApplication.java`:**

```java
package example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

Đặt application trong package `example.catalog` giúp các classes và test cùng package tìm được primary configuration. `@DataJpaTest` sẽ áp dụng JPA slice filters, không nạp full application services như `@SpringBootTest`.

### 8.5. Entity có primary key và unique SKU

**`src/main/java/example/catalog/CatalogProduct.java`:**

```java
package example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "catalog_products",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_catalog_product_sku",
                columnNames = "sku")
)
public class CatalogProduct {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String sku;

    @Column(nullable = false, length = 150)
    private String displayName;

    @Column(nullable = false)
    private long priceCents;

    protected CatalogProduct() {
        // Required by JPA.
    }

    public CatalogProduct(
            String sku,
            String displayName,
            long priceCents) {
        this.sku = sku;
        this.displayName = displayName;
        this.priceCents = priceCents;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getDisplayName() {
        return displayName;
    }

    public long getPriceCents() {
        return priceCents;
    }
}
```

`jakarta.persistence` đúng với Spring Boot 3.x; không dùng `javax.persistence` từ Boot 2.x. Ràng buộc `UniqueConstraint` được Hibernate chuyển thành DDL khi test dùng `create-drop`. `IDENTITY` hoạt động với H2/PostgreSQL trong demo nhưng có khác biệt về sequence/identity behavior ở database khác.

**Không dùng `long` như bảo đảm price phải dương**: `@Column(nullable=false)` chỉ nói giá trị không null (primitive đã không null), không có business validation `priceCents > 0`. Nếu cần invariant ấy, bổ sung validation/check constraint rõ ràng và test riêng.

### 8.6. Spring Data repository

**`src/main/java/example/catalog/CatalogProductRepository.java`:**

```java
package example.catalog;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogProductRepository
        extends JpaRepository<CatalogProduct, Long> {
    Optional<CatalogProduct> findBySku(String sku);
}
```

Spring Data JPA cung cấp implementation của `findBySku` từ tên property entity. Test sẽ thực thi SQL thông qua repository proxy chứ không mock nó.

## 9. Test A: chạy với H2, không cần Docker

**`src/test/java/example/catalog/CatalogRepositoryH2Test.java`:**

```java
package example.catalog;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.dao.DataIntegrityViolationException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@DataJpaTest(properties =
        "spring.jpa.hibernate.ddl-auto=create-drop")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY,
        connection = EmbeddedDatabaseConnection.H2
)
class CatalogRepositoryH2Test {
    @Autowired
    CatalogProductRepository repository;

    @Autowired
    TestEntityManager entityManager;

    @Autowired
    DataSource dataSource;

    @Test
    void reallyUsesH2() throws SQLException {
        try (Connection connection =
                     dataSource.getConnection()) {
            assertEquals("H2",
                    connection.getMetaData()
                            .getDatabaseProductName());
        }
    }

    @Test
    void savesFlushesAndReloadsAnEntity() {
        CatalogProduct saved = repository.saveAndFlush(
                new CatalogProduct(
                        "SKU-H2-10", "Trà xanh", 12500L));

        assertNotNull(saved.getId());

        entityManager.clear();

        CatalogProduct reloaded = repository
                .findBySku("SKU-H2-10")
                .orElseThrow();

        assertEquals(saved.getId(), reloaded.getId());
        assertEquals("Trà xanh",
                reloaded.getDisplayName());
        assertEquals(12500L, reloaded.getPriceCents());
    }

    @Test
    void rejectsSameSkuAtDatabaseConstraint() {
        repository.saveAndFlush(
                new CatalogProduct(
                        "SKU-H2-20", "Mẫu A", 1000L));

        entityManager.clear();

        assertThrows(DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new CatalogProduct(
                                "SKU-H2-20", "Mẫu B", 2000L)));
    }
}
```

### 9.1. Tại sao phải assert database vendor?

Annotation `@AutoConfigureTestDatabase(connection=H2)` thể hiện cấu hình dự định, nhưng `Connection.getMetaData().getDatabaseProductName()` mới kiểm tra **JDBC connection đang được dùng** có thực sự báo H2 không. Đây là cách phát hiện tình huống datasource bị thay ngoài ý muốn.

Với PostgreSQL test, ta sẽ assert `"PostgreSQL"`, tránh kiểu test **pass nhầm H2**.

### 9.2. Tại sao `saveAndFlush` rồi `clear`?

- `save` đưa entity vào persistence context; SQL write có thể xảy ra khi flush/commit (với IDENTITY insert có thể xảy ra sớm để lấy ID).
- `saveAndFlush` yêu cầu flush pending changes vào database trong transaction hiện tại.
- `entityManager.clear()` xóa managed entities khỏi first-level cache nhưng **không xóa database rows**.
- `findBySku` sau clear kiểm tra repository query truy vấn lại dữ liệu.

Đây là một bằng chứng tốt hơn `assertNotNull(repository)` hoặc chỉ assert object trả về từ `save`.

### 9.3. Unique constraint và transaction sau lỗi

Nếu gọi `repository.save(duplicate)` rồi ngay lập tức `assertThrows`, exception có thể **chưa xuất hiện tại thời điểm đó** nếu SQL chưa flush. `saveAndFlush` giúp test chỉ đúng mốc constraint được database kiểm tra.

Sau khi PostgreSQL/Hibernate phát hiện constraint violation, transaction có thể ở trạng thái rollback-only/aborted. Vì vậy trong test negative, **không truy vấn thêm trong cùng transaction sau exception**; kết thúc test và để framework rollback.

**Không assert chuỗi SQL error message** vì chúng phụ thuộc database version/driver; `DataIntegrityViolationException` hoặc invariant quan sát được bền hơn.

## 10. Test B: PostgreSQL thật bằng Testcontainers (chỉ chạy khi bật)

Với dự án Boot 3.3 có H2 test driver trên classpath, khi dùng Testcontainers phải **không để DataSource PostgreSQL bị thay bằng H2**. Do đó đặt `replace=NONE` tường minh.

**`src/test/java/example/catalog/CatalogRepositoryPostgresTest.java`:**

```java
package example.catalog;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@EnabledIfEnvironmentVariable(
        named = "RUN_PG_TESTS",
        matches = "true"
)
@Testcontainers
@DataJpaTest(properties =
        "spring.jpa.hibernate.ddl-auto=create-drop")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class CatalogRepositoryPostgresTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    CatalogProductRepository repository;

    @Autowired
    DataSource dataSource;

    @Test
    void connectsToPostgreSQLAndPersistsEntity()
            throws SQLException {
        try (Connection connection =
                     dataSource.getConnection()) {
            assertEquals("PostgreSQL",
                    connection.getMetaData()
                            .getDatabaseProductName());
        }

        CatalogProduct saved = repository.saveAndFlush(
                new CatalogProduct(
                        "SKU-PG-10", "Cà phê", 35000L));

        assertNotNull(saved.getId());

        CatalogProduct reloaded = repository
                .findBySku("SKU-PG-10")
                .orElseThrow();

        assertEquals("Cà phê",
                reloaded.getDisplayName());
        assertEquals(35000L, reloaded.getPriceCents());
    }

    @Test
    void postgresReallyEnforcesUniqueKey() {
        repository.saveAndFlush(
                new CatalogProduct(
                        "SKU-PG-20", "Mẫu A", 1000L));

        assertThrows(DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new CatalogProduct(
                                "SKU-PG-20", "Mẫu B", 2000L)));
    }
}
```

### 10.1. Ý nghĩa từng annotation

- `@EnabledIfEnvironmentVariable(named="RUN_PG_TESTS", matches="true")`: chỉ chạy class khi biến môi trường bật. Mặc định **skip**, nên `./gradlew test` trên máy không có Docker vẫn thực hiện H2 tests.
- `@Testcontainers`: kích hoạt Testcontainers JUnit Jupiter extension.
- `@Container`: quản lý lifecycle PostgreSQL test container.
- `@ServiceConnection`: yêu cầu Spring Boot tạo connection details từ typed container; cần dependency `spring-boot-testcontainers`.
- `@DataJpaTest`: chỉ nạp JPA slice, không cần full Boot context.
- `@AutoConfigureTestDatabase(replace=NONE)`: bảo toàn datasource từ container, rất quan trọng với mặc định `ANY` của Boot 3.3.
- `ddl-auto=create-drop`: giúp demo tự tạo schema. Nếu test migrations thật, không dùng cách này như bằng chứng Flyway/Liquibase.
- Metadata assertion: chứng minh đã kết nối engine `PostgreSQL`, không chỉ có PostgreSQL driver trong build.

### 10.2. Test nào cần Docker?

**Chỉ** `CatalogRepositoryPostgresTest` khi `RUN_PG_TESTS=true`. Các H2 tests chạy độc lập và không khởi động container. Trong CI có thể chia fast test stage (H2) và database integration stage (PostgreSQL).

Tuy nhiên, “skip” không có nghĩa “PostgreSQL đã pass”. Báo cáo phải phân biệt **test chưa chạy** với **test đã chạy và thành công**.

### 10.3. JPA slice vẫn dùng database thật được

Không cần thêm `@SpringBootTest` chỉ để Testcontainers chạy. Chọn **database engine** và chọn **độ rộng Spring context** là hai quyết định khác nhau:

| Phạm vi | H2 | PostgreSQL |
| --- | --- | --- |
| `@DataJpaTest` | Có | Có |
| `@SpringBootTest` | Có | Có |

Nếu cần kiểm tra controller-service-repository end-to-end, chọn full Boot context; nếu chỉ cần repository query/constraints, JPA slice với PostgreSQL là hoàn toàn phù hợp.

## 11. Lệnh chạy và kết quả mong đợi

Với JDK17, Gradle Wrapper tương thích (ví dụ Gradle 8.5) và dependencies tải được:

### 11.1. Không có Docker

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.catalog.CatalogRepositoryH2Test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.catalog.CatalogRepositoryH2Test
```

Dự kiến **3 H2 test methods pass**. PostgreSQL test class được skip nếu `RUN_PG_TESTS` không có hoặc khác `true`.

### 11.2. Có Docker, bật PostgreSQL

Linux/macOS:

```bash
RUN_PG_TESTS=true ./gradlew test --tests example.catalog.CatalogRepositoryPostgresTest
RUN_PG_TESTS=true ./gradlew test
```

Windows PowerShell:

```powershell
$env:RUN_PG_TESTS = 'true'
.\gradlew.bat test --tests example.catalog.CatalogRepositoryPostgresTest
Remove-Item Env:RUN_PG_TESTS
```

Dự kiến **2 PostgreSQL test methods pass** khi chỉ chọn Postgres class, hoặc tổng **5 methods pass** khi chạy toàn bộ suite với biến môi trường bật. Không có stdout nghiệp vụ cố định; Gradle thường báo `BUILD SUCCESSFUL` khi tất cả tasks chạy thành công.

Những kết quả trên là **dự kiến dựa vào mã và cấu hình**, không phải tuyên bố đã chạy Docker trong môi trường tác giả. Cần môi trường có Docker và image PostgreSQL để xác nhận.

### 11.3. Kiểm tra image/engine version

Ví dụ dùng `postgres:16-alpine`, không dùng `postgres:latest`. Khi production dùng PostgreSQL 15 hoặc 17, nên có test đúng major/minor/extension hoặc tập tests tương thích được duyệt. Với yêu cầu tái hiện tuyệt đối, có thể pin image digest và mirror registry.

## 12. `@DynamicPropertySource`: một cách kết nối khác

Bên cạnh `@ServiceConnection` (Boot 3.1+), Spring TestContext có `@DynamicPropertySource`. Khi dùng alternative này, bỏ `@ServiceConnection` trên cùng container và khai báo dynamic JDBC properties:

```java
@Container
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

@DynamicPropertySource
static void postgresProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url",
            postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
}
```

Đây là **mảnh code thay thế**, cần class `@Testcontainers`, imports `DynamicPropertySource`/`DynamicPropertyRegistry` và các imports Testcontainers. Không copy thêm vào class bên trên cùng lúc với `@ServiceConnection` nếu không có lý do rõ.

Trong **Boot 3.3**, dù properties JDBC đã đến từ container, `@DataJpaTest` vẫn có thể thay datasource theo mặc định `ANY`. Vì thế giữ `@AutoConfigureTestDatabase(replace=NONE)`.

Từ Boot 3.4, mặc định `NON_TEST` có khả năng nhận diện những database từ dynamic properties/container tốt hơn. Nhưng nếu test phải dùng chính database cụ thể, cấu hình tường minh và assertion vendor vẫn có giá trị.

### 12.1. Static container và Spring context cache không cùng vòng đời

`@Container` static thường chạy theo lifecycle JUnit test class, còn Spring TestContext có thể cache `ApplicationContext`. Trong suite có nhiều classes dùng chung context, một datasource có thể còn trỏ container đã dừng nếu lifecycle thiết kế không nhất quán.

Ví dụ ở đây chỉ có một PostgreSQL test class, giúp vòng đời đơn giản. Với suite lớn, cân nhắc container bean do Spring Boot quản lý hoặc singleton container lifecycle phù hợp cache. Không tự share static mutable container giữa hàng chục tests rồi dựa vào ngẫu nhiên về thứ tự chạy.

## 13. H2 có thể che những lỗi nào?

### 13.1. Native queries/dialect

H2 compatibility mode không phải PostgreSQL. Những tính năng cần vendor tests:

- PostgreSQL `jsonb`/JSON operators, arrays và extensions.
- `ON CONFLICT`, `RETURNING`, native casts và SQL functions.
- Index expression/partial index, collations và case-insensitive uniqueness.
- Window functions/CTEs/locking behavior đặc thù vendor.
- Query planner/index statistics và performance.
- PostgreSQL error codes và transaction abortion semantics.

Một repository method chỉ dùng Spring Data derived `findBySku` có thể pass ở H2 và PostgreSQL. Điều đó chưa chứng minh một `@Query(nativeQuery=true)` dùng `jsonb` sẽ hoạt động.

### 13.2. Constraints và collation

`UNIQUE(sku)` trên H2 không mặc nhiên chứng minh uniqueness không phân biệt chữ hoa/thường trên PostgreSQL với collation/index cụ thể. Nếu business rule yêu cầu `sku-1` và `SKU-1` coi như trùng, phải thiết kế index/normalization có nghĩa và test engine production.

Trong demo, chúng ta chỉ kiểm tra **cùng một chuỗi SKU chính xác** để tránh suy luận vượt yêu cầu.

### 13.3. Identity/sequence behavior

`@GeneratedValue(IDENTITY)` hoặc `SEQUENCE` có thể tạo SQL khác nhau giữa vendors. Sequence counters có thể tăng dù transaction rollback, nên không assert “ID đầu tiên luôn là 1”. Assert `getId() != null` và bản ghi load được bằng business key.

### 13.4. Transaction isolation/locking

H2 và PostgreSQL khác nhau về MVCC, lock modes, deadlock detection và isolation. Một test trong transaction duy nhất chưa chứng minh hai requests cạnh tranh update đúng.

Nếu dùng `@Version`, `@Lock(PESSIMISTIC_WRITE)` hoặc transaction isolation đặc thù, test cần **nhiều connections/transactions** trên engine đúng. Không dùng `Thread.sleep` tùy tiện làm lời giải cho race; điều phối concurrency bằng barrier/latches có timeout và assert invariant.

### 13.5. Timezone và số tiền

Kiểu timestamp/offset, `BigDecimal` precision/scale và database rounding có thể khác. Với tiền, dùng minor units hoặc `BigDecimal` cùng schema constraints/scale. Test vendor khi numeric/timezone conversion ảnh hưởng nghiệp vụ.

## 14. `save`, `flush`, `clear`, `commit` và `rollback`

| Hành động | Nó làm gì | Nó **không** bảo đảm |
| --- | --- | --- |
| `repository.save(...)` | Làm entity managed/chuẩn bị persist | Đã commit |
| `flush()` | Đồng bộ thay đổi tới DB trong transaction hiện tại | Đã commit |
| `entityManager.clear()` | Bỏ entities khỏi first-level cache | Xóa data DB |
| `commit` | Hoàn tất transaction và công bố thay đổi | Những transaction khác sẽ rollback thay |
| `rollback` | Hủy thay đổi thuộc transaction đó | Hủy dữ liệu đã commit từ transaction khác |

Sơ đồ `@DataJpaTest` mặc định:

```text
Spring Test opens test-managed transaction
   |
   +--> repository.saveAndFlush(...)
   +--> entityManager.clear()
   +--> repository.findBySku(...)
   +--> assert data / constraints
   |
   +--> rollback after @Test
```

**Tại sao `clear()` hữu ích?** Nếu không, EntityManager có thể trả một managed entity đã tồn tại trong persistence context, làm test không chứng minh đầy đủ dữ liệu đã được load lại qua query. `clear()` giúp giảm khả năng false confidence (dù cache cấp hai/custom caches nếu có cần xem riêng).

### 14.1. Dữ liệu đã commit cần kiểm tra kiểu khác

Nếu mục tiêu là dữ liệu **được transaction khác nhìn thấy sau commit**, `@DataJpaTest` rollback mặc định chưa chứng minh điều đó. Có thể dùng `TestTransaction` để điều khiển test-managed transaction:

```java
repository.saveAndFlush(
        new CatalogProduct("SKU-COMMIT", "Mẫu", 100L));

TestTransaction.flagForCommit();
TestTransaction.end();

// Đã kết thúc test-managed transaction.
// Từ đây cần cleanup tường minh hoặc DB test ephemeral.
assertTrue(repository.findBySku("SKU-COMMIT").isPresent());
```

Đây là **mẫu nâng cao**, chưa phải một method trong runnable demo. Muốn dùng cần imports `org.springframework.test.context.transaction.TestTransaction`, `assertTrue` và một test đang có test-managed transaction; không được thêm vô ý vào H2 suite thông thường vì dữ liệu sẽ được commit.

Nếu `@SpringBootTest(RANDOM_PORT)` có HTTP server thật, server request chạy transaction riêng với test thread. `@Transactional` trên test method không tự rollback các writes server đã commit.

## 15. Schema: `ddl-auto=create-drop` không phải migration test

Bộ ví dụ cố tình dùng:

```properties
spring.jpa.hibernate.ddl-auto=create-drop
```

để H2 và PostgreSQL test DB có schema từ entity mà **không cần migration scripts**. Đây là lựa chọn thuận tiện cho demo persistence mapping.

Trong production-like project:

- Dùng Flyway/Liquibase với SQL migrations thực.
- Cho migration chạy trên database test cùng vendor.
- Đặt `spring.jpa.hibernate.ddl-auto=validate` hoặc `none` theo chính sách để Hibernate không thay thế schema được tạo từ migration.
- Kiểm tra các constraints/indexes/extensions/enum DB types mà ứng dụng kỳ vọng.
- Không tự bật `create-drop` trên một datasource có dữ liệu cần giữ; nó có thể phá schema.

Nếu H2 test tạo schema hoàn toàn từ Hibernate, test đó **không chứng minh** một Flyway SQL migration dành cho PostgreSQL chạy đúng.

### 15.1. `schema.sql`, `data.sql` và `@Sql`

Spring Boot có SQL initialization và Spring Test có `@Sql`, nhưng thứ tự với JPA DDL/migrations phụ thuộc configuration:

- `schema.sql`/`data.sql`: startup scripts nếu được bật theo Boot config.
- `Flyway`/`Liquibase`: migration lifecycle.
- Hibernate `ddl-auto`: có thể tạo/validate/drop schema.
- `@Sql`: scripts theo test lifecycle, thường trước hoặc sau test method.

**Đừng bật tất cả cùng lúc rồi coi schema sẽ tự đúng.** Chọn một nguồn schema chính, xác định thứ tự cụ thể, và thử migration trên vendor DB nếu production dùng migration.

`@Sql` chạy trước test method **không nhất thiết đã chạy trước startup runner** của application context. Nếu startup code cần fixture, phải chuẩn bị trước context bootstrap.

## 16. Rollback không xóa mọi side effects

Một số điều có thể sống lâu hơn test-managed transaction:

- Sequence/identity counters.
- Data được commit bởi `Propagation.REQUIRES_NEW` hoặc thread khác.
- Startup seed job và migration chạy trước method test.
- Events/email/HTTP calls từ service.
- File writes hoặc cache bên ngoài database.
- Data được commit từ HTTP server thread trong live integration test.

Vì thế test không nên “dọn” bằng cách dựa vào `@DirtiesContext`. Annotation này chỉ loại context khỏi cache, không tự rollback commit hoặc xóa data external.

Nếu cần test side effect commit, dùng database/schema riêng, unique test keys và cleanup đúng record. Không gọi `repository.deleteAll()` trên database dùng chung nếu không có quyền/ý đồ rõ ràng.

## 17. Khi có nhiều datasource/persistence units

Ứng dụng phức tạp có thể có:

- `ordersDataSource` (primary).
- `analyticsDataSource`.
- Nhiều `EntityManagerFactory`.
- Nhiều transaction managers.
- Routing datasource theo tenant.

Javadoc `@AutoConfigureTestDatabase` nêu nó chỉ xem xét **primary datasource** trong bối cảnh nhiều DataSources. Nó không có nghĩa sẽ an toàn thay mọi nguồn. `@DataJpaTest` mặc định phù hợp với một JPA configuration thông thường; các persistence units tùy biến cần test configuration rõ.

Checklist:

1. Xác định repository thuộc EntityManagerFactory nào.
2. Xác định datasource URL/driver/test credentials của từng unit.
3. Đảm bảo không có secondary datasource trỏ production.
4. Bật replacement hoặc cung cấp test connection cụ thể theo unit.
5. Assert đúng vendor/DB name khi bắt buộc.
6. Giữ state cô lập và rollback/cleanup theo từng transaction manager.

## 18. Bảo đảm an toàn khi dùng `Replace.NONE`

**`Replace.NONE` không phải “chỉ dùng PostgreSQL test database”.** Nó có nghĩa “đừng thay datasource hiện tại”. Nếu test nhầm cấu hình production, bạn có thể thực thi INSERT/DELETE/`create-drop` trên database không được phép.

Cần đặt hàng rào:

- Không cấp production credentials vào CI test workflow.
- Dùng container ephemeral hoặc test server chỉ dành cho kiểm thử.
- Nếu có thể, giới hạn network không cho test job truy cập production DB.
- Assert vendor và môi trường/schema/database name được cho phép.
- Giữ `ddl-auto=create-drop` chỉ trong demo/ephemeral DB.
- Dùng role test có quyền giới hạn, không phải superuser production.
- Tránh log JDBC URL nếu URL chứa secrets; không log passwords.
- Test dữ liệu cá nhân: dùng fixture giả, không copy production records.
- Với nhiều datasource, đánh giá mọi connection.
- Nếu Docker không có, cho test bị skip hoặc fail rõ; **không** tự fallback sang staging/production.

Metadata `PostgreSQL` chỉ xác nhận vendor; nó không tự chứng minh server cụ thể là test container. Kết hợp connection details, safe environment rules và network isolation.

## 19. Spring TestContext cache và container lifecycle

Spring TestContext cache contexts theo configuration classes, profiles, inline properties, context customizers, bean overrides và loaders. H2 test và PostgreSQL test có những settings khác nhau nên thường có cache keys riêng.

Lưu ý:

- Context cache có thể tái sử dụng H2 datasource giữa test methods.
- Rollback mặc định không reset identity counters.
- Container static `@Container` có vòng đời JUnit class; Spring context cache có vòng đời riêng.
- Nếu container bị dừng ở cuối class nhưng cached DataSource vẫn giữ connection URL, class khác tái dùng context có thể fail.
- `@DirtiesContext` làm startup lại, khiến suite chậm và có thể chạy migrations/startup jobs nhiều lần.
- Parallel test trên một DB/schema có thể gây collisions; cần isolation và unique business keys.

Trong demo, một class PG duy nhất giúp đơn giản hóa vòng đời. Khi mở rộng suite, chọn container lifecycle quản lý bởi Boot hoặc singleton lifecycle nhất quán, rồi thiết kế cleanup.

## 20. Chẩn đoán lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Test PostgreSQL tưởng pass nhưng metadata báo H2 | Boot 3.3 thay DataSource bằng H2 | `@AutoConfigureTestDatabase(replace=NONE)` |
| `Failed to replace DataSource with an embedded database` | Thiếu H2/HSQL/Derby test driver hoặc replacement không thể thực hiện | Thêm embedded driver hoặc dùng real datasource + NONE |
| `Failed to determine suitable driver class` | URL/driver/runtime dependency thiếu | Kiểm tra datasource properties và Gradle deps |
| `Connection refused` tới PostgreSQL | Container chưa chạy, port sai, network lỗi | Xem Testcontainers logs và service connection |
| `Could not find a valid Docker environment` | Không có Docker/compatible runtime | Bật PG tests ở CI node phù hợp |
| `Not a managed type` | Entity không thuộc JPA scan | Kiểm tra package/`@Entity`/`@EntityScan` |
| `NoSuchBeanDefinitionException` cho service | `@DataJpaTest` không quét service thường | `@Import` nhỏ hoặc `@SpringBootTest` |
| Table does not exist | Schema chưa được tạo/migration chưa chạy | Kiểm tra `ddl-auto`, Flyway, schema |
| H2 pass, PostgreSQL query fail | Native SQL/dialect khác | Test query trên vendor engine |
| Unique duplicate không ném exception tại `save` | SQL chưa flush | `saveAndFlush`/`flush` |
| Sau constraint error mọi query lỗi tiếp | Transaction bị aborted/rollback-only | Dừng thao tác trong test ấy, rollback |
| Test method khác không thấy data | Transaction rollback mặc định | Chuẩn bị fixture cho mỗi test |
| Dữ liệu còn dù test `@Transactional` | Data được commit ngoài test transaction | Cleanup và xác định transaction boundary |
| Boot 3.3 không có `Replace.NON_TEST` | Mode chỉ thêm từ 3.4 | Dùng đúng enum values version |
| Nâng Boot 4 import `DataJpaTest` lỗi | Test modules/packages đổi | Dùng dependencies/imports theo Boot 4 |
| Test riêng xanh, suite đỏ | Shared DB, context cache, container lifecycle, parallelism | Cô lập test state và lifecycle |

### 20.1. Root cause quan trọng hơn exception ngoài cùng

`Failed to load ApplicationContext` chỉ là biểu hiện chung. Phải kiểm tra `Caused by`:

- Không tạo được embedded DataSource?
- PostgreSQL container không khởi động?
- Chưa có JDBC driver?
- Hibernate DDL sai trên DB vendor?
- Migration thất bại?
- Repository query validation lỗi?
- Có service/application bean ngoài slice bị phụ thuộc nhầm?

Chỉ thay `@AutoConfigureTestDatabase` khi thật sự có bằng chứng datasource replacement là vấn đề.

## 21. Bài tập thực hành

### Bài 1 — Chứng minh H2 chứ không chỉ đoán

Chạy `CatalogRepositoryH2Test.reallyUsesH2`. Đổi expected vendor từ `H2` sang `PostgreSQL` ở nhánh sandbox và xem assertion đỏ. Khôi phục.

### Bài 2 — Bỏ H2 driver

Tạm bỏ `testRuntimeOnly 'com.h2database:h2'`, chạy H2 class và đọc root cause datasource replacement. Khôi phục. Giải thích vì sao chỉ có PostgreSQL driver không giúp `connection=H2` hoạt động.

### Bài 3 — `save` so với `saveAndFlush`

Thử dùng `repository.save(duplicate)` thay `saveAndFlush` rồi phân tích khi nào exception xuất hiện. Với `IDENTITY`, insert có thể sớm để sinh ID; không rút ra kết luận “save luôn chưa gọi SQL”.

### Bài 4 — Kiểm tra PostgreSQL thật

Bật `RUN_PG_TESTS=true` trên môi trường có Docker. Xác minh metadata là `PostgreSQL`. Thử bỏ `replace=NONE` ở Boot 3.3 để quan sát test có thể bị thay bằng H2 rồi khôi phục. Không bao giờ dùng production database làm phương án dự phòng.

### Bài 5 — Schema migration

Dùng Flyway trong một test nâng cao: tạo `V1__create_catalog_products.sql` cho PostgreSQL, chuyển `ddl-auto=validate` và assert repository query chạy. Giải thích vì sao `create-drop` không là migration test.

### Bài 6 — Native PostgreSQL query

Viết một native query đơn giản dùng PostgreSQL JSONB trong một test sandbox. Xem tại sao H2 không bảo đảm behavior; assert trên PostgreSQL container.

### Bài 7 — Transaction commit

Dùng `TestTransaction.flagForCommit()`/`end()` trong một test riêng, query dữ liệu sau commit và cleanup. Không để test này tham gia fast suite nếu không có isolation.

### Bài 8 — Concurrency

Thiết kế hai transaction cùng update một row có `@Version` hoặc `@Lock(PESSIMISTIC_WRITE)`. Dùng database vendor và coordination primitives có timeout; không dùng sleep cố định làm bằng chứng về ordering.

### Bài 9 — Nhiều datasources

Giả định có primary orders datasource và secondary analytics datasource. Liệt kê những kết nối có thể vẫn là production nếu chỉ cấu hình replacement cho primary. Thiết kế test profile riêng từng persistence unit.

### Bài 10 — Đề xuất bộ test cho dự án thật

Một hệ thống có 80 repositories, 8 native PostgreSQL queries, Flyway migrations, nhiều services và HTTP APIs. Đề xuất số lượng/nhóm test H2, PostgreSQL, full context, unit theo rủi ro. Mỗi test PostgreSQL phải trả lời: “Lỗi vendor-specific nào H2 không chứng minh được?”

## 22. Checklist khi review database tests

- [ ] Đã nói rõ mục tiêu H2 hay vendor database.
- [ ] Biết default replacement của Spring Boot version đang dùng.
- [ ] Không dùng `Replace.NON_TEST` trên Boot 3.3 (enum này chỉ thêm từ 3.4).
- [ ] `@DataJpaTest` là JPA slice, không phải full application integration.
- [ ] Test H2 có driver embedded đúng runtime classpath.
- [ ] Test PostgreSQL có datasource an toàn và `replace=NONE` ở Boot 3.3.
- [ ] Có JDBC metadata assertion để không pass nhầm vendor.
- [ ] Không dùng H2 compatibility mode làm bằng chứng engine thật.
- [ ] Unique constraint được kiểm tra tại mốc SQL flush.
- [ ] Không query tiếp trong transaction sau constraint violation.
- [ ] Hiểu rollback mặc định và sự khác nhau giữa flush và commit.
- [ ] Không assert fixed generated identity sequence.
- [ ] Không tự tin migrations đúng nếu chỉ dùng Hibernate `create-drop`.
- [ ] Database/test schema được cô lập và cleanup.
- [ ] Không có production credentials/network ở automated tests.
- [ ] Khi dùng nhiều DataSource, đánh giá connection của từng unit.
- [ ] Testcontainers lifecycle phù hợp Spring context caching.
- [ ] Nếu skip PostgreSQL tests vì Docker chưa sẵn, không báo chúng đã pass.
- [ ] Không thêm `@DirtiesContext` chỉ để xóa database rows.
- [ ] Khi nâng Boot 4, kiểm tra package/import/test modules của version mới.

## 23. Kết luận

**Embedded H2** và **PostgreSQL Testcontainers** không thay nhau mà bổ sung nhau. H2 cung cấp feedback nhanh cho nhiều JPA mappings/repository methods. PostgreSQL thật là cần thiết khi lỗi nằm ở SQL dialect, native queries, schema, constraints, migrations, concurrency hoặc transaction behavior của production vendor.

Trong **Spring Boot 3.3**, `@AutoConfigureTestDatabase` có mặc định `Replace.ANY`; để dùng test datasource PostgreSQL mà không bị thay bằng H2, đặt `replace=NONE` và **assert actual vendor**. Từ Boot 3.4, default `NON_TEST` giúp nhận diện nhiều test datasource tốt hơn nhưng không tự bảo vệ khỏi việc kết nối nhầm database ngoài.

Lựa chọn dựa trên hành vi cần chứng minh, cô lập dữ liệu và kiểm soát test lifecycle — không dựa vào suy đoán rằng “repository test có PostgreSQL dependency thì chắc chắn đã kiểm tra trên PostgreSQL”.

## 24. Tài liệu chính thức

- Spring Boot 3.3 — Testing Spring Boot Applications, `@DataJpaTest`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — `@AutoConfigureTestDatabase` Javadoc, default `ANY`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html
- Spring Boot 3.3 — Testcontainers, `@ServiceConnection` và `@DynamicPropertySource`: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Boot 3.4 — `Replace.NON_TEST` Javadoc: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html
- Spring Boot 3.4 — Release notes, database replacement với containers: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes
- Spring Boot 3.3 — Test slices auto-configurations: https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html
- Spring Framework — Transaction management in tests: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Framework — TestContext caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Data JPA — JPA query methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Testcontainers Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- JUnit Jupiter — Conditional test execution: https://docs.junit.org/current/user-guide/

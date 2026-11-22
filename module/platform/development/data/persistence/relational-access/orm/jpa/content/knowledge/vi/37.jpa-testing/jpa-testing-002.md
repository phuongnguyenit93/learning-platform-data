# Thiết lập persistence unit và lược đồ thử nghiệm có kiểm soát

Một bài kiểm thử JPA chỉ đáng tin khi người viết biết chính xác **entity nào được quản lý, database nào đang được sử dụng, schema được tạo từ đâu, transaction bắt đầu và kết thúc khi nào, và dữ liệu của test trước có còn ảnh hưởng tới test sau hay không**.

Ví dụ sau trông có vẻ là một integration test:

```java
@Test
void saveProduct() {
    EntityManager em = emf.createEntityManager();
    em.persist(new CatalogProduct(1L, 7L, "SKU-01",
            new BigDecimal("120.00")));
    assertNotNull(em.find(CatalogProduct.class, 1L));
    em.close();
}
```

Nhưng đoạn code này chưa có transaction ghi hợp lệ, chưa biết `emf` cấu hình thế nào, chưa biết schema có bảng `catalog_products`, chưa có database isolation, và nếu một object vẫn nằm trong persistence context thì `find()` cũng không chứng minh dữ liệu đã commit vào database.

Để kiểm thử JPA đúng nghĩa, cần xây dựng một **test harness có kiểm soát**:

```text
JUnit 5
   │
   ├─ Chọn database test riêng, phiên bản rõ ràng
   ├─ Áp schema migration có phiên bản
   ├─ Bootstrap EntityManagerFactory từ persistence unit
   ├─ Mỗi test dùng EntityManager và transaction độc lập
   ├─ Chuẩn bị fixture, gọi flush/commit có chủ đích
   ├─ Xác minh kết quả bằng context mới
   ├─ Rollback/dọn dữ liệu nếu thất bại
   └─ Đóng EntityManagerFactory và database resources
```

Bài **“Thiết lập persistence unit và lược đồ thử nghiệm có kiểm soát”**, thuộc chương **Kiểm thử JPA** trong chủ đề **Data Persistence Relational Access ORM JPA**, hướng dẫn thiết lập trọn luồng trên bằng **Jakarta Persistence, JUnit Jupiter, PostgreSQL Testcontainers và Flyway**. Bài cũng phân tích trường hợp dùng database trong bộ nhớ, Spring Data JPA, JTA, lifecycle của schema, kiểm soát dữ liệu và các lỗi kiểm thử giả thường gặp.

Các ví dụ dùng cú pháp `jakarta.persistence` của Jakarta Persistence 3.x. Ở những dự án JPA cũ dùng `javax.persistence`, cần điều chỉnh API/package và các phiên bản thư viện cho tương thích; không trộn ngẫu nhiên hai hệ namespace. Đoạn SQL migration minh họa PostgreSQL và không mặc định portable sang mọi database.

**Nguyên tắc chính:** test phải kiểm soát cả *persistence unit* lẫn *schema và transaction thực*, không chỉ kiểm tra một repository method trả đúng object trong bộ nhớ.

---

## 1. Persistence unit là gì?

Một **persistence unit** là một tập hợp cấu hình định nghĩa môi trường JPA mà `EntityManagerFactory` dùng để tạo các `EntityManager`.

Nó bao gồm, trực tiếp hoặc qua framework:

- Tên persistence unit.
- JPA provider (ví dụ Hibernate ORM, EclipseLink).
- Những entity classes được quản lý.
- Connection/DataSource và database dialect.
- Transaction type: resource-local hoặc JTA.
- Mappings, converter, entity listeners.
- Validation mode và optional lifecycle integration.
- Schema generation/validation settings.
- Shared cache settings.
- Những provider-specific properties khác.

Ví dụ khái quát:

```text
persistence-unit: catalog-test
   ├─ Provider: Hibernate ORM
   ├─ Entity: CatalogProduct
   ├─ Transaction: RESOURCE_LOCAL
   ├─ JDBC: PostgreSQL test container
   ├─ Schema: Flyway migrations
   ├─ Hibernate mapping check: validate
   └─ EntityManagerFactory
        ├─ EntityManager test #1
        ├─ EntityManager test #2
        └─ EntityManager test #3
```

`EntityManagerFactory` đại diện cho cấu hình tương đối bền trong vòng đời test suite/class, thường tốn chi phí bootstrap. `EntityManager` nhẹ hơn và **không thread-safe**; không nên dùng một EntityManager chung giữa nhiều tests chạy song song.

## 2. Persistence unit không phải database

Hai khái niệm dễ nhầm:

| Thành phần | Quyết định điều gì? | Không tự làm gì? |
| --- | --- | --- |
| Persistence unit | Entity mappings, provider, transaction, connection config | Không bảo đảm schema đã được migration |
| Database/schema | Tables, columns, types, PK/FK/UNIQUE/CHECK, indexes | Không tự tạo Java entity metadata |
| EntityManagerFactory | Bootstrap và tạo context | Không tự cô lập dữ liệu từng test |
| EntityManager | Persistence context, managed entities, operations | Không tương đương transaction đã commit |
| EntityTransaction | Begin/commit/rollback cho RESOURCE_LOCAL | Không được dùng thay JTA container |
| Migration tool | Triển khai phiên bản schema xác định | Không kiểm thử entity lifecycle thay JPA |

Một test có thể bootstrap `EntityManagerFactory` thành công nhưng fail ở lần truy vấn đầu vì bảng không tồn tại. Ngược lại, schema có thể đúng nhưng entity mappings hoặc transaction type sai.

**Cần kiểm tra cả hai: cấu hình JPA và trạng thái database trước khi chạy business assertions.**

## 3. Vì sao schema thử nghiệm phải có kiểm soát?

Một schema thiếu constraints có thể làm các phép thử "xanh" dù production từ chối thao tác:

```sql
-- Schema test yếu: không bảo vệ tính duy nhất hoặc giá trị âm.
CREATE TABLE catalog_products (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT,
    sku VARCHAR(64),
    unit_price NUMERIC(12,2)
);
```

Trong production, có thể cần:

```sql
tenant_id BIGINT NOT NULL,
sku VARCHAR(64) NOT NULL,
unit_price NUMERIC(12,2) NOT NULL,
UNIQUE (tenant_id, sku),
CHECK (unit_price >= 0)
```

Nếu một JPA integration test chạy trên schema yếu, nó không chứng minh hành vi tại `flush()`/`commit()` với các constraints thực.

Một schema test có kiểm soát cần:

1. Được tạo từ nguồn versioned có thể tái lập.
2. Có types/constraints/indexes quan trọng đúng với production.
3. Không phụ thuộc schema cũ còn lại từ lần chạy trước.
4. Có ownership rõ, không trỏ nhầm database dùng chung.
5. Có cách seed/cleanup dữ liệu độc lập giữa tests.
6. Có phương thức xác nhận migration thành công trước khi bootstrap JPA.
7. Không dùng quyền xóa schema production.
8. Có thông số phiên bản DB/dialect rõ ràng.

## 4. Chọn mức độ test phù hợp

Không phải bài test nào cũng cần database container:

| Loại test | Infrastructure | Phù hợp kiểm tra |
| --- | --- | --- |
| Unit test thuần | Không DB/JPA provider | Domain methods, pure business rules |
| JPA mapping/integration test | EntityManager + DB thật | Persist/merge/remove, callbacks, flush, queries |
| Repository slice test | Spring test context, DB | Repository JPQL, mappings, constraints |
| Service transaction test | JPA + transaction manager | Propagation, commit/rollback, concurrency |
| Database migration test | DB engine + migration tool | Schema, constraints/indexes |
| End-to-end test | API, JPA, DB, services | Contract xuyên tầng |

Hệ quả: **Mockito mock `EntityManager` không thay cho integration test JPA**, nhưng cũng không phải mọi phép tính trong domain đều cần khởi động PostgreSQL.

Bài này tập trung vào **JPA integration test và schema test**, không thay thế unit tests.

---

## 5. Hai lựa chọn database thử nghiệm

### Lựa chọn A: database trong bộ nhớ

Ví dụ H2 có thể nhanh cho vòng phát triển nhỏ:

```text
jdbc:h2:mem:catalogtest;DB_CLOSE_DELAY=-1
```

Ưu điểm là startup nhanh, không cần Docker và dễ tạo database riêng. Nhưng H2 **không phải PostgreSQL/MySQL/SQL Server thật**. Có thể khác:

- Data types và precision.
- SQL dialect/functions.
- Collation và Unicode.
- CHECK/UNIQUE/FK behavior, nhất là NULL semantics.
- Transaction isolation và locking.
- Generated IDs, sequences.
- Partial/expression indexes.
- Deferred constraints.
- JSON, arrays, timestamp/timezone.
- SQL planner và execution plans.

Compatibility mode không thể bảo đảm tất cả production semantics. Dùng H2 cho các tests có phạm vi rõ; nếu muốn khẳng định ràng buộc/schema/transaction trên PostgreSQL, **test trên PostgreSQL**.

### Lựa chọn B: container chạy cùng loại DB production

`Testcontainers` khởi động một database disposable:

```java
@Container
static PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16-alpine");
```

Ưu điểm:

- Engine SQL, transaction và constraints sát PostgreSQL thật.
- Container độc lập với database developer dùng.
- Có thể pin version, chạy trong CI.
- Test schema bằng migrations.
- Không yêu cầu thao tác thủ công tạo DB mỗi lần.

Hạn chế: cần runtime container tương thích, image availability, thời gian khởi động và tài nguyên máy/CI. Một version image cần được dự án pin/đánh giá tương thích, không dùng `latest` tùy tiện.

## 6. Resource-local và JTA: chọn một mô hình rõ ràng

JPA có hai kiểu transaction chính:

| Thuộc tính | RESOURCE_LOCAL | JTA |
| --- | --- | --- |
| Sở hữu transaction | Ứng dụng qua `EntityTransaction` | Container/transaction manager |
| Begin | `em.getTransaction().begin()` | JTA/Spring manager |
| Commit | `em.getTransaction().commit()` | JTA/Spring manager |
| Phù hợp | Java SE JUnit fixture nhỏ, explicit local tests | Jakarta EE hoặc ứng dụng có transaction framework |
| Yêu cầu | EntityManager JDBC connection thích hợp | Persistence unit/DataSource tham gia JTA |
| Bẫy | Quên begin/commit, test đọc L1 rồi tưởng đã lưu | Gọi `getTransaction()` trên container-managed EM |

Trong ví dụ độc lập JUnit, chúng ta dùng **RESOURCE_LOCAL**. Khi chuyển sang Spring/JTA, giữ nguyên mục tiêu kiểm thử nhưng thay transaction harness; không copy mọi `begin()/commit()` vào service do Spring quản lý.

### Vì sao chọn RESOURCE_LOCAL cho ví dụ?

Nó làm rõ mốc:

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    em.persist(product);
    em.flush(); // Đồng bộ nhưng CHƯA commit.

    em.getTransaction().commit(); // Kết thúc transaction.
} finally {
    em.close();
}
```

Khi test cần chứng minh commit thật, việc gọi `commit()` tường minh giúp tránh nhầm với các test frameworks tự rollback sau mỗi method.

## 7. Cấu trúc thư mục ví dụ

Một cấu trúc dự án:

```text
project/
├─ pom.xml hoặc build.gradle
├─ src/
│  ├─ main/
│  │  └─ java/com/example/jpa/
│  │     └─ CatalogProduct.java
│  └─ test/
│     ├─ java/com/example/jpa/
│     │  └─ CatalogPersistenceIT.java
│     └─ resources/
│        ├─ META-INF/
│        │  └─ persistence.xml
│        └─ db/migration/
│           └─ V1__create_catalog_products.sql
```

`persistence.xml` trong `src/test/resources/META-INF` giúp bài test chọn persistence unit riêng. Migrations nằm trong test resources ở ví dụ này; **trong dự án thực, nên cân nhắc dùng migrations production ở `src/main/resources/db/migration`** để test đúng schema sẽ được deploy, thay vì duy trì hai bản DDL dễ lệch.

Nếu dùng migrations production, test có thể bổ sung test-only seed/fixture scripts riêng nhưng không tự chỉnh sửa nguồn schema chuẩn.

---

## 8. Dependencies cần có

Để chạy ví dụ Jakarta Persistence + PostgreSQL + Flyway + JUnit:

- Jakarta Persistence API phù hợp version của provider.
- JPA provider (ví dụ Hibernate ORM).
- PostgreSQL JDBC driver.
- JUnit Jupiter API/engine.
- Testcontainers PostgreSQL module và Testcontainers JUnit Jupiter integration.
- Flyway core và module hỗ trợ PostgreSQL nếu version Flyway yêu cầu.
- Logging implementation nếu cần.
- Jakarta Validation API/provider nếu test Bean Validation lifecycle.

**Không trộn Hibernate ORM bản dùng `javax.persistence` với API `jakarta.persistence`**. Dependency versions nên được quản lý bằng BOM/platform tương thích; không lấy bản mới nhất của từng dependency độc lập khi chưa kiểm tra compatibility.

Một file build chỉ chứa Jakarta Persistence API mà không có provider sẽ không tự triển khai JPA. Tương tự, Testcontainers PostgreSQL module không tự tạo entity mappings hoặc migrations.

### Chọn version theo hợp đồng dự án

Một tổ hợp cần thống nhất:

```text
Java runtime
   ↔ Jakarta Persistence API
   ↔ Hibernate ORM version
   ↔ PostgreSQL JDBC driver
   ↔ Flyway support modules
   ↔ JUnit Jupiter / Testcontainers
   ↔ PostgreSQL Docker image version
```

Không tự cho rằng PostgreSQL JDBC driver bản A hỗ trợ mọi database version B hoặc Flyway core mới đã bao gồm mọi DB support khi chưa đọc tài liệu/version manifest dự án.

## 9. Entity mẫu có định danh do ứng dụng gán

Để phép thử dễ xác định ID và thời điểm SQL, dùng một entity không cần `@GeneratedValue`:

```java
package com.example.jpa;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "catalog_products")
public class CatalogProduct {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @Column(name = "unit_price",
            nullable = false,
            precision = 12,
            scale = 2)
    private BigDecimal unitPrice;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected CatalogProduct() {
        // JPA cần constructor không tham số thích hợp.
    }

    public CatalogProduct(
            Long id,
            Long tenantId,
            String sku,
            BigDecimal unitPrice) {
        this.id = id;
        this.tenantId = tenantId;
        this.sku = sku;
        this.unitPrice = unitPrice;
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getSku() {
        return sku;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public Long getVersion() {
        return version;
    }

    public void changePrice(BigDecimal newPrice) {
        this.unitPrice = newPrice;
    }
}
```

Ở ví dụ này `changePrice` cố ý không áp rule giá không âm để có thể kiểm thử riêng ràng buộc `CHECK` ở DB. **Trong domain production**, giá âm thường nên được chặn sớm bằng value object/domain method/Bean Validation; DB vẫn là hàng rào cuối.

`@Version` được đưa vào để tests tương lai có thể kiểm tra optimistic locking. Nó không thay UNIQUE/CHECK.

### Vì sao không dùng IDENTITY trong ví dụ đầu tiên?

Với `GenerationType.IDENTITY`, provider có thể phải INSERT ngay tại `persist()` để lấy ID, làm mốc SQL khác với entity có assigned ID hoặc sequence. Khi bài học tập trung vào `flush` và transaction, assigned ID giảm biến số. Điều đó **không phải khuyến nghị dùng assigned ID cho mọi ứng dụng**.

## 10. Migrations: schema là một nguồn sự thật rõ ràng

File `V1__create_catalog_products.sql`:

```sql
CREATE TABLE catalog_products (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku VARCHAR(64) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT uq_catalog_product_tenant_sku
        UNIQUE (tenant_id, sku),

    CONSTRAINT ck_catalog_product_nonnegative_price
        CHECK (unit_price >= 0)
);
```

Đây là PostgreSQL-compatible DDL.

Ràng buộc có ý nghĩa:

- `PRIMARY KEY(id)`: một entity identity duy nhất.
- `tenant_id NOT NULL`: không có Product thiếu tenant.
- `UNIQUE(tenant_id, sku)`: SKU không trùng **trong một tenant**.
- `CHECK(unit_price >= 0)`: không thể commit giá âm theo DB constraint.
- `NUMERIC(12,2)`: decimal chính xác theo scale.
- `version`: lưu optimistic version.

Những constraints này bảo vệ cả các đường ghi khác ORM như JDBC/native SQL. Test chỉ dựa vào annotation `@Column` mà không có schema thật sẽ không chứng minh chúng hoạt động.

### Có cần tạo bảng qua entity annotation nữa không?

Nếu Flyway tạo schema, **không bật thêm một công cụ DDL tự tạo bảng ở cùng thời điểm** khi không có chủ đích. Để JPA chỉ kiểm tra mapping so với schema, dùng provider's schema-validation setting; tránh hai nguồn DDL tranh nhau.

## 11. File `persistence.xml` tối thiểu cho test

Tạo `src/test/resources/META-INF/persistence.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="catalog-test"
        transaction-type="RESOURCE_LOCAL">

        <provider>
            org.hibernate.jpa.HibernatePersistenceProvider
        </provider>

        <class>com.example.jpa.CatalogProduct</class>

        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <validation-mode>AUTO</validation-mode>

        <properties>
            <!-- Chỉ kiểm tra mapping so với schema đã migration.
                 Thuộc tính này là của Hibernate. -->
            <property
                name="hibernate.hbm2ddl.auto"
                value="validate"/>
        </properties>
    </persistence-unit>
</persistence>
```

Chi tiết:

1. `name="catalog-test"` là tên lookup khi bootstrap.
2. `RESOURCE_LOCAL` cho phép dùng `em.getTransaction()`.
3. `provider` chỉ định Hibernate ORM rõ ràng; một số dự án để provider tự phát hiện.
4. `<class>` đăng ký entity trong Java SE test harness.
5. `exclude-unlisted-classes=true` giúp biết chính xác những entity nào thuộc unit; nếu có quan hệ tới entity khác, cần đăng ký đủ.
6. `AUTO` dùng Bean Validation provider nếu available theo integration semantics; không bảo đảm annotation sẽ được kiểm tra nếu runtime thiếu implementation.
7. `hibernate.hbm2ddl.auto=validate` là **Hibernate-specific**: kiểm tra một số khía cạnh mapping/schema thay vì tự tạo mới bảng.
8. JDBC connection properties sẽ được test cung cấp khi bootstrap, không hardcode host/user/password trong file.

Đừng lầm `hibernate.hbm2ddl.auto=validate` với một phép kiểm tra đầy đủ tất cả index, CHECK và unique constraints. Provider schema validation thường tập trung tables/columns/types và không phải thay thế migration/schema integration tests.

## 12. Cách JPA tìm persistence unit

Với Java SE:

```java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("catalog-test");
```

JPA tìm file `META-INF/persistence.xml` trên runtime classpath và persistence unit tên tương ứng.

Các lỗi thường gặp:

- File đặt sai thành `src/test/resources/persistence.xml`.
- Tên unit khác `catalog-test`.
- Test resource không được build tool đưa vào classpath.
- Entity class không được khai báo/scan.
- Provider class thiếu trên classpath.
- `javax.persistence` và `jakarta.persistence` không tương thích.
- Multiple persistence units trùng tên.
- Driver hoặc JDBC URL thiếu.
- Runtime profile nạp config khác dự kiến.

Một test nên kiểm tra bootstrap fail-fast ở setup, không để lỗi cấu hình xuất hiện sau hàng loạt tests.

## 13. Vì sao truyền JDBC settings khi bootstrap?

Nếu test dùng Testcontainers, host port/password được tạo hoặc xác định theo runtime. Không hardcode:

```xml
<property name="jakarta.persistence.jdbc.url"
          value="jdbc:postgresql://localhost:5432/production"/>
```

Thay vào đó truyền overrides:

```java
Map<String, Object> properties = Map.of(
    "jakarta.persistence.jdbc.url",
    postgres.getJdbcUrl(),

    "jakarta.persistence.jdbc.user",
    postgres.getUsername(),

    "jakarta.persistence.jdbc.password",
    postgres.getPassword(),

    "jakarta.persistence.jdbc.driver",
    "org.postgresql.Driver",

    "hibernate.hbm2ddl.auto",
    "validate"
);

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory(
        "catalog-test",
        properties
    );
```

Đây là **Java SE RESOURCE_LOCAL** example, không phải JTA DataSource wiring. Với Spring Boot nên dùng DataSource và transaction manager được framework quản lý, không tự mở thêm EntityManagerFactory tùy tiện.

Lấy JDBC URL từ container giúp test không trỏ nhầm một database developer/prod đang chạy.

---

## 14. Testcontainers + Flyway + JPA: thứ tự khởi tạo

Thứ tự đúng thường là:

```text
Start PostgreSQL container
           │
           ▼
Get JDBC URL / username / password
           │
           ▼
Run Flyway migrations
           │
           ▼
Bootstrap EntityManagerFactory (schema validate)
           │
           ▼
@BeforeEach: reset fixture data
           │
           ▼
@Test: begin → persist/query/flush → commit/rollback
           │
           ▼
Readback via fresh EntityManager
           │
           ▼
@AfterAll: close EntityManagerFactory
           │
           ▼
Stop container
```

Nếu Hibernate validate schema **trước khi** Flyway migrate, startup có thể fail với `missing table`. Nếu Hibernate tự tạo schema rồi Flyway tiếp tục migrate, có thể gặp `relation already exists` hoặc schema drift.

Một test harness cần có **một nguồn DDL có quyền sở hữu rõ ràng**.

## 15. JUnit 5 integration test fixture đầy đủ

Ví dụ skeleton trong `CatalogPersistenceIT.java`:

```java
package com.example.jpa;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.math.BigDecimal;
import java.util.Map;
import java.util.function.Consumer;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class CatalogPersistenceIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    private static EntityManagerFactory emf;

    @BeforeAll
    static void setUpPersistenceUnit() {
        Flyway.configure()
            .dataSource(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword()
            )
            .locations("classpath:db/migration")
            .load()
            .migrate();

        Map<String, Object> overrides = Map.of(
            "jakarta.persistence.jdbc.url",
            postgres.getJdbcUrl(),
            "jakarta.persistence.jdbc.user",
            postgres.getUsername(),
            "jakarta.persistence.jdbc.password",
            postgres.getPassword(),
            "jakarta.persistence.jdbc.driver",
            "org.postgresql.Driver",
            "hibernate.hbm2ddl.auto",
            "validate"
        );

        emf = Persistence.createEntityManagerFactory(
            "catalog-test",
            overrides
        );
    }

    @AfterAll
    static void closePersistenceUnit() {
        if (emf != null) {
            emf.close();
        }
    }

    @BeforeEach
    void resetData() {
        inTransaction(em -> {
            em.createQuery("DELETE FROM CatalogProduct p")
                .executeUpdate();
        });
    }

    static void inTransaction(Consumer<EntityManager> work) {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();
            work.accept(em);
            tx.commit();
        } catch (RuntimeException failure) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
            }
            throw failure;
        } finally {
            em.close();
        }
    }

    // @Test methods ở phần tiếp theo.
}
```

Testcontainers JUnit extension quản lý lifecycle của `@Container` static trước `@BeforeAll` và dọn sau khi hoàn thành class. Flyway chạy trên DB vừa tạo trước khi JPA schema validation. Mã mẫu giả định dependencies/version đã được cấu hình phù hợp và resource migration đúng đường dẫn.

### Vì sao `@BeforeEach` xóa dữ liệu?

Ví dụ chỉ có một table, nên dùng JPQL bulk DELETE đơn giản để mỗi test bắt đầu với bảng rỗng. Nhưng đây **chỉ là chiến lược cho fixture nhỏ**:

- JPQL bulk DELETE bỏ qua per-entity callbacks và không synchronize L1 managed entities.
- Với foreign keys, có thể cần xóa child tables trước parent.
- Test chạy song song trên cùng database sẽ ảnh hưởng nhau.
- Nếu dùng trigger/audit tables, phải có cleanup tương ứng.
- Với dữ liệu nhiều tables, transaction rollback, per-test schema/container hoặc test data builders có thể phù hợp hơn.

Không sử dụng global DELETE/TRUNCATE vô hạn trên database có dữ liệu chung.

---

## 16. Test đầu tiên: persist và đọc lại trong context mới

```java
@Test
void persistedProductIsVisibleAfterCommit() {
    inTransaction(em -> {
        CatalogProduct product = new CatalogProduct(
            101L,
            7L,
            "SKU-101",
            new BigDecimal("125.00")
        );

        em.persist(product);
        em.flush(); // SQL được đồng bộ, chưa commit.
    });

    EntityManager fresh = emf.createEntityManager();

    try {
        CatalogProduct persisted = fresh.find(
            CatalogProduct.class,
            101L
        );

        assertNotNull(persisted);
        assertEquals("SKU-101", persisted.getSku());
        assertEquals(7L, persisted.getTenantId());

        assertEquals(
            0,
            new BigDecimal("125.00").compareTo(
                persisted.getUnitPrice()
            )
        );
    } finally {
        fresh.close();
    }
}
```

Điều kiểm tra:

1. Entity được persist trong transaction.
2. Explicit flush giúp quan sát persistence synchronization.
3. `inTransaction` đã commit trước khi trả về.
4. `EntityManager` mới đọc row, không lấy object từ L1 context cũ.
5. Trị số decimal được so sánh bằng `compareTo` để tránh khác biệt scale của `BigDecimal.equals` sau DB mapping.

Nếu `em.persist` chỉ giữ entity ở L1 mà không commit, test đọc cùng EntityManager có thể vẫn thấy nó; đó không phải bằng chứng database đã lưu.

## 17. `flush()` không phải `commit()`

Có thể hình dung:

```text
em.persist(product)
     │
     ▼
Product managed trong L1
     │
     ▼
em.flush()
  └─ INSERT gửi vào transaction database
     │
     ├─ ROLLBACK → row không committed
     └─ COMMIT   → row committed
```

Với một số ID generation strategies, INSERT có thể phát trước explicit flush; vì vậy mốc SQL sớm hay muộn còn tùy provider/ID strategy. Nhưng **flush không đồng nghĩa durable commit** là một nguyên tắc quan trọng.

Test commit và rollback phải kiểm tra sau transaction completion, không chỉ dựa vào object state.

## 18. Test rollback thực sự không giữ row

Một exception test-only:

```java
static final class AbortForTest extends RuntimeException {
}
```

JUnit test:

```java
@Test
void rollbackDoesNotCommitProduct() {
    assertThrows(AbortForTest.class, () ->
        inTransaction(em -> {
            em.persist(new CatalogProduct(
                202L, 7L, "SKU-202",
                new BigDecimal("30.00")
            ));

            em.flush();

            throw new AbortForTest();
        })
    );

    EntityManager fresh = emf.createEntityManager();

    try {
        assertNull(fresh.find(CatalogProduct.class, 202L));
    } finally {
        fresh.close();
    }
}
```

Ở đây `flush` đã yêu cầu INSERT trong transaction, nhưng transaction rollback nên context mới không tìm thấy row. Test này chứng minh khác biệt giữa **SQL được gửi** và **dữ liệu được commit**.

Không dùng cùng entity instance sau rollback để suy database state; Java object có thể vẫn giữ ID và giá trị cũ.

## 19. Test database UNIQUE constraint

Schema quy định `UNIQUE(tenant_id, sku)`. Test:

```java
@Test
void duplicateSkuWithinTenantIsRejected() {
    inTransaction(em -> {
        em.persist(new CatalogProduct(
            301L, 7L, "SKU-X",
            new BigDecimal("10.00")
        ));
    });

    RuntimeException failure = assertThrows(
        RuntimeException.class,
        () -> inTransaction(em -> {
            em.persist(new CatalogProduct(
                302L, 7L, "SKU-X",
                new BigDecimal("20.00")
            ));
            em.flush();
        })
    );

    assertTrue(
        containsSqlState(failure, "23505"),
        "Expected PostgreSQL unique violation"
    );
}
```

Helper SQLState cho PostgreSQL:

```java
static boolean containsSqlState(
        Throwable failure,
        String expectedState) {

    Throwable current = failure;

    while (current != null) {
        if (current instanceof java.sql.SQLException sql
                && expectedState.equals(sql.getSQLState())) {
            return true;
        }

        current = current.getCause();
    }

    return false;
}
```

`23505` là mã unique violation của PostgreSQL. Khi dùng DB khác, SQLState/vendor code và cách provider bọc exception có thể khác; chọn assertions phù hợp DB thực tế.

Test này không gọi Bean Validation để thay thế UNIQUE. Nó cố xác nhận **ràng buộc database thật đã từ chối duplicate**.

## 20. Test ràng buộc CHECK

DDL:

```sql
CONSTRAINT ck_catalog_product_nonnegative_price
CHECK (unit_price >= 0)
```

Test:

```java
@Test
void negativePriceIsRejectedByDatabase() {
    RuntimeException failure = assertThrows(
        RuntimeException.class,
        () -> inTransaction(em -> {
            em.persist(new CatalogProduct(
                401L,
                7L,
                "SKU-NEGATIVE",
                new BigDecimal("-1.00")
            ));
            em.flush();
        })
    );

    assertTrue(
        containsSqlState(failure, "23514"),
        "Expected PostgreSQL CHECK violation"
    );
}
```

`23514` là PostgreSQL CHECK violation. Trong ví dụ entity chưa có `@DecimalMin`; điều này cố ý để kiểm tra DB CHECK một cách riêng biệt. Nếu dự án thêm Bean Validation, một exception có thể phát trước SQL; khi đó test DB constraint nên dùng một đường ghi JDBC/native SQL có kiểm soát để tránh nhầm nguồn lỗi.

**Test xanh vì bất kỳ RuntimeException nào không đủ**: phải xác minh nguyên nhân đúng với ràng buộc đang được kiểm thử.

## 21. Bài test dọn dữ liệu không nên dựa hoàn toàn vào rollback

Một số framework bọc toàn bộ test trong transaction và tự rollback sau method. Điều này hữu ích nhưng không giống mọi production flow.

Ví dụ nếu service dùng transaction mới hoặc JDBC autocommit connection khác, chúng có thể **commit ngoài test transaction**. Rollback của test không dọn được các rows ấy.

Hãy chọn isolation strategy rõ:

- Transaction rollback toàn test khi chỉ kiểm tra reads/writes trong cùng transaction.
- Explicit commit + cleanup khi kiểm tra commit semantics.
- Per-test schema/container khi cần isolation mạnh.
- Unique test IDs/tenant IDs kết hợp cleanup khi datasets không xung đột.
- Database restore/snapshot khi chạy destructive migrations.

**Không dựa vào “test framework tự rollback” mà không biết transaction boundaries của code đang kiểm tra.**

---

## 22. Các chiến lược tạo schema

Có ba cách phổ biến:

### A. ORM tự tạo schema từ entity metadata

Ví dụ Hibernate:

```properties
hibernate.hbm2ddl.auto=create-drop
```

Có thể tiện cho prototype/quick tests, nhưng schema do provider generate có thể thiếu:

- Partial indexes.
- Complex CHECK constraints.
- Triggers.
- Materialized views.
- Computed columns.
- Vendor-specific types.
- Schema migration history.
- Referential actions đặc thù.
- Những thay đổi dữ liệu đi cùng migration.

Vì vậy không lấy một test dùng `create-drop` làm bằng chứng production migrations hợp lệ.

### B. JPA standard schema generation

Jakarta Persistence có các properties như:

```properties
jakarta.persistence.schema-generation.database.action=drop-and-create
jakarta.persistence.schema-generation.create-source=metadata
```

Những giá trị/actions được hỗ trợ theo specification/provider; cần xác minh khi dùng scripts hoặc custom DDL. Thuộc tính này khác `hibernate.hbm2ddl.auto`.

### C. Migration-first (khuyến nghị cho schema integration quan trọng)

- Flyway/Liquibase tạo schema có phiên bản.
- JPA provider validate mapping khi bootstrap.
- Tests chạy queries/transactions lên schema thực.
- CI dùng cùng migrations như production.
- Schema drift được phát hiện sớm.

Không bật đồng thời nhiều cách tự tạo schema trừ khi có một lý do và thứ tự được chứng minh rõ.

## 23. `create`, `create-drop`, `update`, `validate` và `none`

Với Hibernate-specific `hibernate.hbm2ddl.auto`, các chế độ thường gặp:

| Setting | Mục đích chung | Phù hợp |
| --- | --- | --- |
| `create` | Tạo schema khi bootstrap, có thể tác động tables cũ | Disposable DB/test không giữ dữ liệu |
| `create-drop` | Tạo lúc bootstrap, dọn lúc shutdown theo provider lifecycle | Demo/disposable fixture đơn giản |
| `update` | Cố điều chỉnh schema theo metadata | Dev convenience, không thay migration production |
| `validate` | Kiểm tra mapping/schema hiện hữu | Migration-first integration test |
| `none` | Không tự thực hiện DDL | Schema đã quản lý riêng |

Cú pháp/hành vi cụ thể theo Hibernate version. **`update` không phải công cụ migration an toàn thay Flyway/Liquibase trên production**, vì có thể không biểu diễn data migrations, drop/rename, constraint changes và rollback có kiểm soát.

### Cẩn trọng với `create-drop`

Nếu JDBC URL trỏ nhầm DB dùng chung, bootstrap/shutdown có thể xóa cấu trúc dữ liệu quan trọng. Chỉ dùng trên disposable database đã xác minh ownership; không dựa vào database name bất kỳ để suy an toàn.

## 24. Migration-first và schema validation có vai trò khác nhau

`Flyway.migrate()` xác nhận tập scripts theo history table và thực hiện changes cần thiết. Hibernate `validate` kiểm tra khả năng mapping các entity lên schema ở mức provider hỗ trợ.

Hai phép kiểm tra không thay thế nhau:

- Flyway không biết entity fields có map sai column type hay không.
- Hibernate validate không bảo đảm mọi UNIQUE/CHECK/index/FK được tạo đúng.
- Unit test không chứng minh migrations đã chạy.
- Database integrity test không chứng minh mọi JPA entity mapping đúng.

Một test infrastructure tốt kết hợp migration, bootstrap validation và targeted SQL/schema tests.

## 25. Tại sao không viết hai bản schema song song?

Cách dễ lệch:

```text
src/main/resources/db/migration/V1.sql   (production)
src/test/resources/schema.sql             (test)
```

Nếu chỉ sửa production V1/V2 mà quên schema.sql, JPA tests có thể chạy trên một hệ constraints không còn đại diện production.

Hướng tốt:

- Dùng production migrations cho integration tests.
- Bổ sung test-only fixtures riêng.
- Chỉ có schema test chuyên dụng khi thật sự cần một phiên bản legacy/không FK.
- Document rõ schema thử nghiệm nào đại diện production và schema nào mô phỏng lỗi.
- Khi production migration có data backfill, test với dữ liệu trước/sau migration nếu cần.

**Một nguồn schema authoritative giúp tránh “test pass nhưng production fail”.**

---

## 26. Thời điểm bootstrap: migrate trước factory

Anti-pattern:

```java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("catalog-test");

flyway.migrate();
```

Nếu Hibernate chạy `validate`, table chưa tồn tại nên bootstrap fail. Nếu Hibernate được cấu hình `create`, nó có thể tạo tables trước Flyway rồi làm migration lỗi.

Đúng hơn:

```java
flyway.migrate();

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory(
        "catalog-test",
        overrides
    );
```

Thứ tự này cần được giữ trong CI, IDE và build tool test runner. Spring Boot có cơ chế tích hợp migration startup; khi dùng framework, để framework sở hữu thứ tự đó thay vì tự bootstrap một factory song song.

## 27. Không dùng database H2 để khẳng định PostgreSQL SQL behavior

Ví dụ:

```sql
CREATE INDEX ... WHERE deleted_at IS NULL;
```

hoặc:

```sql
EXPLAIN (ANALYZE, BUFFERS) ...
```

là PostgreSQL-specific. H2 có thể không hỗ trợ hoặc hỗ trợ khác ngay cả khi bật compatibility mode. Concurrency và transaction behavior cũng có thể khác.

Chọn database test phù hợp mục tiêu:

- Unit mapping smoke test không phụ thuộc dialect: H2 có thể đủ.
- Optimistic/pessimistic locking, isolation, FK/UNIQUE/CHECK, native SQL, migration: chọn production engine.
- Query plan/index tuning: cần schema/data/statistics sát production, không đủ chỉ có một container rỗng.
- PostgreSQL-specific JSONB/trigram/partial index: phải dùng PostgreSQL.

Không có một lựa chọn database duy nhất tốt nhất cho mọi tests.

## 28. Schema per test hay per class?

Các cách:

| Cách | Ưu điểm | Giới hạn |
| --- | --- | --- |
| Một container mỗi test method | Isolation rất mạnh | Startup/migration đắt |
| Một container mỗi test class | Tái sử dụng kết nối/schema | Cần cleanup giữa methods |
| Một container mỗi suite | Nhanh khi suite lớn | Cross-test contamination/parallel races |
| Một schema/database riêng mỗi test | Isolation tốt, có thể dùng chung server | Quản lý schema names/connections phức tạp |
| Transaction rollback per method | Nhanh, đơn giản | Không test commit hoàn chỉnh; REQUIRES_NEW/JDBC khác không rollback |
| Reset bằng SQL | Rõ ràng, cho phép test commit | FK order, triggers, cleanup cost |
| Unique IDs/tenants | Ít conflict IDs | Data có thể tích lũy nếu không dọn |

Ví dụ bài dùng container static per class + `@BeforeEach` cleanup vì chỉ một table. Khi project lớn hơn, chọn strategy nhất quán với parallelism, speed và correctness.

## 29. Parallel tests trên cùng schema có nguy cơ gì?

Test A:

```text
@BeforeEach DELETE FROM catalog_products
test creates Product #1
```

Test B song song:

```text
@BeforeEach DELETE FROM catalog_products
test expects Product #1 ...
```

Một test có thể xóa fixture của test kia. Hậu quả là flakiness không liên quan JPA mapping.

Giải pháp:

- Không chạy song song tests chia chung schema/cleanup.
- Dùng test DB/schema riêng.
- Sử dụng tenant/ID namespace riêng và cleanup có scope.
- Thiết lập transaction isolation phù hợp.
- Nếu dùng global Statistics counters, không so SQL count khi bị test khác làm nhiễu.
- Với shared containers, coi cleanup/ownership như tài nguyên tranh chấp thật.

**Không dùng một EntityManager chung giữa threads** ngay cả khi các IDs không trùng; EntityManager không thread-safe.

## 30. Migrations có thể không rollback cùng test transaction

DDL transaction semantics khác theo database. Trên một số engines, DDL commit ngầm hoặc có hạn chế rollback; sequence increments không phải lúc nào cũng được hoàn tác.

Vì vậy:

- Không thử "migrate trong @Test, rollback để quay về schema cũ" như một chiến lược portable.
- Test migrations trên disposable DB/schema/snapshot.
- Seed entities sau khi schema ổn định.
- Đừng dùng `@Transactional` của Spring để kỳ vọng rollback một DDL được thực thi bởi connection/migration tool khác.
- Flyway history table cần nhất quán khi test failed migration.
- Nếu muốn thử migration từ phiên bản V1 sang V2, khởi động một database có V1 fixture rồi apply V2 theo một scenario riêng.

Một test method rollback giúp xử lý **DML trong một transaction**, không phải nút "undo database" chung.

## 31. Làm sạch dữ liệu có foreign keys

Khi thêm `orders` và `order_lines`:

```text
customers
  └─ purchase_orders
        └─ order_lines
```

Cleanup theo quan hệ phụ thuộc:

```sql
DELETE FROM order_lines;
DELETE FROM purchase_orders;
DELETE FROM customers;
```

Với DB có FK, xóa parent trước có thể fail. `TRUNCATE ... CASCADE` trên PostgreSQL có thể xóa thêm tables ngoài dự định; chỉ dùng trong schema riêng với danh sách tables đã được kiểm tra.

Không tắt FK trong test cleanup nếu điều đó làm những tests sau không còn kiểm tra được constraints.

Một số projects dùng transaction rollback thay cleanup DML, nhưng nhớ giới hạn với commit tests và transactions độc lập.

## 32. Fixture builders và ID ổn định

Không dùng một số ID hardcode như `1L` trong toàn bộ suite chia sẻ DB, nếu tests có thể chạy song song hoặc data tồn tại từ lần trước.

Tạo fixture rõ:

```java
static CatalogProduct product(
        long id,
        long tenantId,
        String sku) {

    return new CatalogProduct(
        id,
        tenantId,
        sku,
        new BigDecimal("99.00")
    );
}
```

Với per-test clean database, IDs cố định có thể làm assertions dễ đọc. Với shared DB/parallel tests, nên tạo namespace riêng cho từng test/tenant và có cleanup có scope.

Không dùng random data làm test không thể tái hiện mà không log seed. Một fixture tốt **đủ đa dạng để bắt đúng bug nhưng deterministic**.

---

## 33. Persistence context có thể che lỗi đọc dữ liệu

JPA quản lý identity map trong context:

```java
CatalogProduct p =
    em.find(CatalogProduct.class, 101L);

CatalogProduct again =
    em.find(CatalogProduct.class, 101L);

assertSame(p, again);
```

Đây là hành vi đúng. Nhưng nếu test muốn chứng minh database đã nhận UPDATE và commit, việc đọc lại trong cùng EntityManager có thể chỉ trả managed object.

Cách xác minh state committed:

1. Hoàn tất transaction (commit/rollback).
2. Đóng EntityManager cũ.
3. Mở EntityManager mới.
4. `find` hoặc query/JDBC readback.
5. Nếu có L2 cache, cân nhắc cache policy hoặc dùng JDBC khi cần kiểm tra chính database.

Một test chỉ `assertEquals(newValue, p.getValue())` sau setter không chứng minh persistence hoạt động.

## 34. EntityManagerFactory và EntityManager có vòng đời khác

Factory:

```java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("catalog-test");
```

nên tái sử dụng trong class/suite, sau đó đóng một lần.

EntityManager:

```java
try {
    EntityManager em = emf.createEntityManager();

    try {
        // Unit of work.
    } finally {
        em.close();
    }
} finally {
    emf.close();
}
```

Đừng tạo EntityManagerFactory cho mỗi row hoặc mỗi query; bootstrap có thể tốn thời gian và tài nguyên. Đừng giữ EntityManager xuyên toàn suite khi tests cần isolation; L1 và pending changes sẽ gây nhiễu.

### Khi đóng factory?

Sau khi mọi EntityManagers/transactions dùng factory đã kết thúc. Với Testcontainers, đóng factory **trước khi container bị stop** để connection pool/provider resources được giải phóng bình thường.

## 35. Xử lý transaction failure trong fixture

Một helper tốt cần rollback nếu có exception:

```java
try {
    tx.begin();
    work.accept(em);
    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackError) {
            failure.addSuppressed(rollbackError);
        }
    }

    throw failure;
} finally {
    em.close();
}
```

Không làm:

```java
try {
    em.flush();
} catch (RuntimeException ignored) {
    em.persist(nextProduct);
    em.getTransaction().commit();
}
```

Sau một persistence failure, transaction có thể rollback-only hoặc không còn an toàn để tiếp tục. Test nên dọn context, không tạo ra false positives vì trạng thái lỗi.

## 36. Test lỗi commit cần bao cả transaction completion

Anti-pattern:

```java
em.persist(product);
assertDoesNotThrow(em::flush);
// Kết luận: transaction sẽ commit thành công.
```

Sai vì deferred constraints, optimistic conflicts hoặc transaction completion có thể fail sau flush.

Nếu test mục tiêu là commit:

```java
RuntimeException failure = assertThrows(
    RuntimeException.class,
    () -> inTransaction(em -> {
        // Arrange invalid work.
        em.persist(invalidProduct);
        // Không cần explicit flush nếu muốn
        // quan sát cả commit boundary.
    })
);
```

Để phân loại đúng failure, inspect cause chain/constraint name/SQLState khi DB cụ thể.

Đừng so sánh "có exception" quá rộng rồi kết luận test đúng loại constraint đang nhắm tới.

---

## 37. Bean Validation là một lớp khác với schema

Entity có thể thêm:

```java
@NotBlank
private String sku;

@NotNull
@DecimalMin("0.00")
private BigDecimal unitPrice;
```

Với Jakarta Bean Validation provider và JPA lifecycle integration phù hợp, lỗi có thể được phát hiện trước SQL ở pre-persist/pre-update.

Phân biệt:

| Kiểm tra | Nguồn | Khi nào |
| --- | --- | --- |
| `Validator.validate(entity)` | Jakarta Validation | Khi code gọi |
| Lifecycle Bean Validation | JPA + Validation provider | Theo pre-persist/update events và flush timing |
| `NOT NULL` | Database | Khi SQL được kiểm tra |
| `CHECK` | Database | Theo statement/transaction constraints |
| `UNIQUE` | Database | Khi kiểm tra unique key |
| `FOREIGN KEY` | Database | Khi kiểm tra referential integrity |

Một JPA test chỉ assert `jakarta.validation.ConstraintViolationException` không chứng minh DB CHECK có thật. Một DB test báo SQLState `23514` cũng không chứng minh Bean Validation integration hoạt động.

Giữ tests riêng để biết **lớp nào đã chặn dữ liệu không hợp lệ**.

## 38. Điều khiển validation mode

Trong `persistence.xml`:

```xml
<validation-mode>AUTO</validation-mode>
```

có thể để provider tự tích hợp Jakarta Bean Validation nếu provider có sẵn theo spec.

Các mode thường gặp:

- `AUTO`: tích hợp nếu có implementation phù hợp.
- `CALLBACK`: yêu cầu lifecycle validation callbacks theo contract.
- `NONE`: tắt automatic Bean Validation callback integration qua JPA.

`NONE` không tắt DB constraints, và không ngăn ứng dụng gọi `Validator.validate` trực tiếp.

Đối với test Bean Validation, phải có API **và implementation** tương thích, đồng thời kiểm tra đúng exception type. Đối với test DB constraints, cần tách đường ghi hoặc configuration để không bị Java validation bắt trước.

## 39. Những tình huống mapping schema validation không phát hiện

Hibernate `validate` có ích, nhưng không thay thế targeted database tests cho:

- CHECK constraint chưa được tạo.
- Unique index nhầm cột.
- FK đang disabled.
- Index thiếu.
- Partial/expression index sai predicate.
- Collation/Unicode differences.
- Trigger logic.
- RLS/tenant policies.
- Deferrable constraints.
- DDL privileges và migration history.
- Performance regressions do indexes.

Nếu một constraint quan trọng, hãy **test hành vi vi phạm** bằng SQL/JPA/JDBC phù hợp trên DB test thật.

---

## 40. Spring Data JPA: persistence unit có thể được framework tạo

Trong Spring Boot, nhiều ứng dụng không cần tự viết `persistence.xml` vì Spring cấu hình:

- `DataSource`.
- `EntityManagerFactory`.
- Entity scanning.
- Transaction manager.
- Hibernate/JPA properties.
- Flyway/Liquibase integration.

Một cấu hình test có thể dùng:

```properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
spring.jpa.open-in-view=false
```

Các settings cụ thể phụ thuộc Spring Boot version và cấu hình classpath. Khi dùng Boot, cần **chọn một chiến lược wiring**: không tạo riêng JPA factory RESOURCE_LOCAL trong cùng test nếu mục tiêu là kiểm thử repository/service đang sử dụng Spring-managed EntityManager.

## 41. `@DataJpaTest` hữu ích nhưng có bẫy

Spring Boot `@DataJpaTest` thường cấu hình JPA test slice và transaction rollback cho mỗi test. Ví dụ:

```java
@DataJpaTest
class CatalogRepositoryTest {

    @Autowired
    private CatalogProductRepository repository;

    @Autowired
    private TestEntityManager testEntityManager;

    @Test
    void findsProductBySku() {
        CatalogProduct p = new CatalogProduct(
            51L, 7L, "SKU-51",
            new BigDecimal("30.00")
        );

        testEntityManager.persistAndFlush(p);

        testEntityManager.clear();

        assertTrue(
            repository.findByTenantIdAndSku(
                7L,
                "SKU-51"
            ).isPresent()
        );
    }
}
```

Fixture giả định repository method đã khai báo. Các imports/dependencies thuộc Spring Boot Test, không phải Jakarta Persistence chuẩn.

Quan trọng:

- Test transaction thường rollback cuối method.
- Flush chưa phải commit.
- Nếu test cần kiểm tra constraint **chỉ phát tại commit**, phải có transaction completion thật.
- Slice có thể thay DataSource bằng embedded DB nếu cấu hình test database replacement mặc định cho version đó.
- Đừng suy rằng đang test PostgreSQL chỉ vì application production dùng PostgreSQL.

## 42. Buộc Spring dùng PostgreSQL Testcontainers khi cần

Một cách với `@DynamicPropertySource`:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class CatalogRepositoryPostgresIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {

        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl
        );

        registry.add(
            "spring.datasource.username",
            postgres::getUsername
        );

        registry.add(
            "spring.datasource.password",
            postgres::getPassword
        );
    }
}
```

Đây là mẫu Spring Boot; cần imports và hỗ trợ phiên bản tương ứng. Spring Boot các bản mới có thể có `@ServiceConnection` hoặc Testcontainers JDBC URL integration, nhưng vẫn phải hiểu **database nào được bind vào DataSource test**.

Với Flyway, bảo đảm auto-config thực sự chạy migrations trước Hibernate validation; slice composition/auto-configuration thay đổi theo version.

## 43. `@Transactional` test rollback che lỗi commit

Ví dụ:

```java
@Test
@Transactional
void savesProduct() {
    repository.save(product);
    // Test method kết thúc, Spring Test có thể rollback.
}
```

Không thể kết luận Product đã commit. Một số constraints được deferred tới commit; method chưa commit thật sẽ không quan sát được.

Hướng kiểm thử commit:

- `TestTransaction.flagForCommit(); TestTransaction.end();` khi dùng Spring test-managed transaction phù hợp.
- `TransactionTemplate` bên ngoài một test transaction bao trùm, để template sở hữu commit thật.
- Integration test không gắn outer `@Transactional`, gọi service proxy rồi kiểm tra readback bằng transaction/context mới.
- Hiểu `Propagation.REQUIRES_NEW` và transaction manager đang dùng.

Đừng bật `@Commit` tùy tiện trên toàn suite rồi để data rò sang các tests khác.

## 44. Spring service boundary và rollback

```java
@Service
class CatalogService {

    private final CatalogProductRepository repository;

    CatalogService(CatalogProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    void create(CatalogProduct product) {
        repository.save(product);
    }
}
```

Nếu flush được trì hoãn, exception có thể xuất hiện **khi Spring transaction interceptor commit sau khi method body trả về**. Một catch bên trong method quanh `repository.save` không chắc bắt được failure.

Khi viết integration test service:

1. Gọi service qua Spring proxy.
2. Bao cả method call trong assertion.
3. Kiểm tra exception cause/constraint.
4. Kiểm tra committed DB state bằng transaction mới.
5. Không dùng outer rollback test transaction nếu muốn service commit thật.
6. Không dựa vào entity còn managed trong cùng context.

---

## 45. Test schema production migration từ đầu

Một test thực tế nên mô phỏng:

```text
Disposable empty PostgreSQL
        │
        ▼
Run all production Flyway migrations
        │
        ▼
Bootstrap Hibernate in validate mode
        │
        ▼
Exercise representative CRUD / queries
        │
        ▼
Check critical DB constraints
```

Điều này bắt được những lỗi:

- Migration thiếu column dùng bởi entity.
- Một cột đổi type nhưng mapping chưa cập nhật.
- Unique constraint thiếu.
- FK sai.
- Column name bị rename nhưng JPQL/native SQL vẫn dùng tên cũ.
- Migration order/dependencies sai.
- Script chỉ chạy thành công khi database developer đã có một bảng thủ công từ trước.

Không đơn giản copy DDL từ production SQL dump rồi coi migrations đã được test.

## 46. Test nâng cấp schema từ dữ liệu cũ

Một migration quan trọng:

```text
V1 schema + fixture dữ liệu cũ
        │
        ▼
Apply V2 / V3 migrations
        │
        ▼
Check data backfill/invariants
        │
        ▼
Bootstrap new EntityManagerFactory
        │
        ▼
Verify old rows and new queries
```

Đây là **upgrade migration test**, khác với fresh DB migration test. Cần chạy một DB bắt đầu ở version cũ có data đại diện, rồi apply migration mới.

Ví dụ đổi `price` từ nullable sang NOT NULL cần backfill dữ liệu cũ trước khi thêm constraint. Một test fresh DB không có rows sẽ không phát hiện migration fail trên dữ liệu thật.

## 47. Kiểm thử native SQL cần schema đúng

Nếu application có:

```java
em.createNativeQuery(
    "SELECT id, tenant_id, sku, unit_price " +
    "FROM catalog_products WHERE tenant_id = ?"
)
.setParameter(1, 7L)
.getResultList();
```

JPA mapping validation có thể không phát hiện mọi lỗi tên cột/SQL dialect trong native queries. Integration test phải **thực thi native SQL trên database/schema được migration**, không chỉ kiểm tra repository interface compile thành công.

Ngoài ra, native/bulk DML có thể bỏ qua lifecycle Bean Validation và làm managed entities stale, nên sau update trực tiếp cần đọc lại trong context mới hoặc `clear/refresh` phù hợp khi test.

## 48. Kiểm thử schema constraints bằng JDBC độc lập

Để khẳng định DB thật ngăn dữ liệu sai, có thể bypass JPA:

```java
try (Connection connection =
         DriverManager.getConnection(
             postgres.getJdbcUrl(),
             postgres.getUsername(),
             postgres.getPassword()
         );
     PreparedStatement stmt =
         connection.prepareStatement(
             "INSERT INTO catalog_products " +
             "(id, tenant_id, sku, unit_price, version) " +
             "VALUES (?, ?, ?, ?, ?)"
         )) {

    stmt.setLong(1, 901L);
    stmt.setLong(2, 7L);
    stmt.setString(3, "SKU-BAD");
    stmt.setBigDecimal(4, new BigDecimal("-20.00"));
    stmt.setLong(5, 0L);

    assertThrows(
        SQLException.class,
        stmt::executeUpdate
    );
}
```

Cần imports `java.sql.*`, JUnit assertions và postgres fixture. Với PostgreSQL CHECK không deferred theo ví dụ, statement fail ở executeUpdate; nếu test các deferred constraints, phải assert qua commit.

Test này khẳng định database constraint tồn tại, không kiểm tra JPA event callbacks.

## 49. Spring `@Sql` và test scripts

Trong Spring Test, `@Sql` có thể chạy scripts setup/cleanup. Cần hiểu:

- Script dùng DataSource/transaction context nào?
- Được chạy trước hay sau test?
- Có commit riêng không?
- Có ảnh hưởng test rollback không?
- DML cleanup có vi phạm FK không?
- Có chạy khi test fail không?
- Script có portable sang production DB engine không?

Không coi mọi `@Sql` mặc nhiên chạy chung transaction với service method `REQUIRES_NEW`. Khi tests nhạy cảm transaction, xác định transaction mode và thứ tự thực tế.

---

## 50. Kiểm soát nhiều persistence units

Một dự án có thể có:

```text
catalog-test
billing-test
audit-test
```

Mỗi unit quản lý entities, connections, transaction settings khác nhau. Test phải gọi đúng tên và không vô tình lấy persistence unit production.

Các vấn đề:

- Entity khai báo trong sai unit.
- `@ManyToOne` tới class không managed trong unit.
- EntityManagerFactories trỏ chung schema dù tưởng độc lập.
- Transaction manager chỉ quản lý một DataSource.
- Migrations áp vào database A nhưng EntityManager dùng database B.
- Cache được chia sẻ ngoài ý định.
- Cùng table name trong schemas khác nhưng default schema sai.

Ghi rõ mapping giữa **unit → DataSource → schema → migration history → transaction manager** cho mỗi test.

## 51. Default schema và search path

Trong PostgreSQL, một kết nối có thể có `search_path` mặc định. Nếu migration tạo bảng ở `catalog_test.catalog_products` nhưng JPA query unqualified `catalog_products` bằng search_path khác, test có thể báo missing table hoặc đọc nhầm schema.

Cần chọn một chính sách:

- Schema mặc định thống nhất trong connection.
- `@Table(schema = "...")` khi thật sự cần chỉ định.
- Hibernate default schema provider property nếu phù hợp.
- Flyway schemas/defaultSchema nhất quán.
- DB user permissions và search_path được cấu hình rõ.
- Không dựa vào session state rò từ một test khác.

Nếu chạy per-test schema, schema name phải được tạo an toàn, không nối user input trực tiếp vào SQL DDL.

## 52. Multi-tenant database và isolation

Một test có thể xác minh:

- Tenant A tạo Product SKU-X.
- Tenant B cũng có Product SKU-X.
- UNIQUE(tenant_id, sku) cho phép cả hai.
- Hai Products cùng tenant với SKU-X bị từ chối.
- Repository query dùng tenant predicate.
- JPA filters/row-level policies không lộ dữ liệu chéo tenant.

Điều này phụ thuộc migration UNIQUE composite và application query logic đúng.

Không dùng duy nhất `@Column(unique=true)` trên SKU nếu business rule là unique **theo tenant**, vì đó có thể tạo uniqueness toàn bảng và không thể mô tả composite rule cần thiết.

## 53. Foreign key và cleanup order

Nếu schema có:

```sql
CREATE TABLE catalog_stock_movements (
    id BIGINT PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES catalog_products(id),
    delta INTEGER NOT NULL
);
```

Trước khi xóa Product fixture, phải xóa stock movements liên quan hoặc dùng database cascade nếu business schema định nghĩa.

Đối với test cleanup:

```sql
DELETE FROM catalog_stock_movements;
DELETE FROM catalog_products;
```

Đây là thứ tự child-first. Không tắt FK để cleanup cho nhanh rồi quên bật lại, vì tests sau đó có thể pass trên schema không còn ràng buộc.

---

## 54. Tránh kết nối nhầm production

Một integration test có quyền tạo/xóa schema hoặc dữ liệu là một tác nhân nguy hiểm nếu JDBC URL trỏ nhầm.

Kiểm soát bằng:

1. Testcontainers sinh JDBC URL trực tiếp từ disposable container.
2. Test profile không lấy production secrets.
3. DB user riêng với quyền giới hạn theo test database.
4. Guard ở test bootstrap nếu database không có dấu hiệu test ownership.
5. Không dùng Flyway.clean trên shared DB.
6. Không bật Hibernate create-drop trên DataSource production.
7. CI secrets và profile separation rõ.
8. Ghi nhận test database host/schema khi bootstrap, tránh in credentials.
9. Không tự động fallback sang connection URL default nếu container không start.
10. Không thực thi destructive cleanup khi kiểm tra ownership chưa thành công.

Test không được “tạm dùng DB developer” rồi giả định không ai khác đang chạy.

## 55. Testcontainers reuse và shared state

Testcontainers có cơ chế reuse trong một số cấu hình để giảm startup. Reuse có thể giúp developer, nhưng làm tăng nguy cơ:

- Data còn từ test trước.
- Migration history cũ.
- Schema không còn empty.
- Cùng database bị nhiều test suites dùng.
- Thứ tự tests ảnh hưởng nhau.

Nếu dùng reuse, phải có reset/ownership strategy rõ. Với integration tests xác minh migration từ empty DB, một container thực sự sạch thường dễ tái lập hơn.

## 56. CI yêu cầu gì để chạy JPA integration test?

CI runner cần:

- Java runtime và build tool tương thích.
- Container runtime hoặc dịch vụ hỗ trợ Testcontainers.
- Khả năng pull PostgreSQL image theo policy.
- CPU/memory/disk đủ cho DB.
- Test timeout phù hợp startup.
- Đường mạng được phép nếu cần image download.
- Không dùng secrets production.
- Test profile/migrations trên đúng classpath.
- Log để debug bootstrap failures.
- Dọn container/resources sau run.
- Không cho nhiều parallel jobs trỏ cùng test schema ngoài ý định.

Một test chạy trên laptop nhưng CI fail vì không truy cập được Docker không phải lỗi JPA mapping; phải phân biệt environmental failure với test assertion failure.

---

## 57. Chẩn đoán “No Persistence provider for EntityManager named ...”

Ví dụ:

```text
No Persistence provider for EntityManager named catalog-test
```

Kiểm tra:

- `persistence.xml` có trên runtime classpath chưa?
- Tên unit có đúng `catalog-test` không?
- Có JPA provider implementation (Hibernate) chưa?
- Provider version có dùng `jakarta.persistence` không?
- XML namespace/version có tương thích không?
- `<provider>` class đúng không?
- Test resources có bị exclude trong build không?
- Có hai persistence.xml cùng unit name gây xung đột không?

Không sửa bằng cách bỏ tên unit rồi chọn ngẫu nhiên factory khác.

## 58. Chẩn đoán “relation does not exist”

Nếu báo `relation "catalog_products" does not exist`:

1. Testcontainer đã start chưa?
2. Flyway migrate đã chạy trước JPA bootstrap chưa?
3. Flyway và JPA cùng JDBC URL/DB/schema chưa?
4. Có schema/search_path khác nhau không?
5. Migration resource path đúng không?
6. Có failed migration/rollback không?
7. Bảng có bị `create-drop` dọn bởi factory khác không?
8. Test cleanup có nhầm sang DDL không?
9. Database/user có quyền truy cập schema không?

Một giải pháp “bật Hibernate create để tự có bảng” có thể che lỗi migration thật; không nên làm trong migration-first tests.

## 59. Chẩn đoán mapping/column mismatch

Ví dụ:

```text
Schema-validation: missing column [unit_price]
```

Có thể vì:

- Entity mapping `@Column(name=...)` khác migration.
- Naming strategy của Hibernate khác kỳ vọng.
- Một migration chưa chạy.
- JPA trỏ sai schema.
- Database column được rename trong migration.
- Provider version đổi type inference.

Sửa ở **nguồn dữ liệu authoritative**: mapping hoặc migration theo schema contract đúng, không tắt validation để test tạm chạy xanh.

## 60. Chẩn đoán constraint test pass giả

Test:

```java
assertThrows(
    RuntimeException.class,
    () -> {
        // ghi invalid data
    }
);
```

có thể pass vì:

- DB connection failure.
- Duplicate PK từ fixture cũ.
- Entity mapping sai.
- Bean Validation chặn trước CHECK.
- SQL syntax error.
- Lock timeout.
- Missing table.

Một test về UNIQUE phải kiểm tra unique-specific cause/constraint/SQLState. Tương tự CHECK/FK tests. Khi dùng PostgreSQL, xác minh các codes tương ứng; với DB khác dùng contract phù hợp.

## 61. Chẩn đoán test thỉnh thoảng fail

Các nguyên nhân:

- Shared DB/schema giữa parallel tests.
- Không cleanup đầy đủ.
- IDs cố định nhưng database reuse.
- Clock/timezone phụ thuộc giờ máy.
- Transaction chưa commit khi context khác đọc.
- Fixture seed trong test transaction nhưng service mở REQUIRES_NEW.
- L1/L2 cache che state.
- SQL sort không có tie-breaker.
- Test dùng `Thread.sleep` thay synchronization primitives.
- DB container chưa ready/migrations chạy chưa xong.
- Sequence counters không rollback dù data rollback.
- Dữ liệu generated random không lưu seed.
- Global Hibernate Statistics bị tests khác cập nhật.

Khắc phục bằng isolation, deterministic fixtures, explicit transaction boundaries, waiting cơ chế chuẩn và logging context. Không dùng retries để che test flaky không rõ nguyên nhân.

---

## 62. Kiểm thử consistency với một EntityManager mới

Một test update:

```java
@Test
void priceUpdateIsCommitted() {
    inTransaction(em -> em.persist(
        new CatalogProduct(
            601L, 7L, "SKU-601",
            new BigDecimal("100.00")
        )
    ));

    inTransaction(em -> {
        CatalogProduct product =
            em.find(CatalogProduct.class, 601L);

        product.changePrice(new BigDecimal("120.00"));
        em.flush();
    });

    EntityManager fresh = emf.createEntityManager();

    try {
        CatalogProduct persisted =
            fresh.find(CatalogProduct.class, 601L);

        assertEquals(
            0,
            persisted.getUnitPrice().compareTo(
                new BigDecimal("120.00")
            )
        );
    } finally {
        fresh.close();
    }
}
```

Đây là ba contexts khác nhau: seed commit, update commit, readback. Nếu chỉ kiểm tra `product.getUnitPrice()` ngay sau setter trong update transaction, đó là Java-state assertion, chưa chứng minh dữ liệu đã commit.

## 63. Những tests cần database sạch ở mức schema

Có các phép thử không thể chỉ `DELETE FROM`:

- Fresh migration from version zero.
- Upgrade V1→V2 với dữ liệu trước migration.
- Verify schema constraints chưa từng tồn tại.
- Destructive DDL.
- Index creation validity.
- Trigger/procedure creation.
- Schema default/search_path setup.
- Database role/permission behavior.
- Tenant schema creation/dropping.
- Partition maintenance.

Cho những tests này, dùng **disposable schema/database/container riêng** và một quy trình khởi tạo/teardown rõ. DML cleanup sau mỗi test không biến một schema đã migration thành “database chưa từng migration”.

## 64. Khi nào nên tạo persistence unit riêng cho tests?

Một `catalog-test` unit hợp lý khi:

- Muốn RESOURCE_LOCAL để kiểm tra transaction tường minh.
- Muốn provider/schema mode khác production nhưng mapping giống.
- Cần database disposable/URL runtime.
- Muốn exclude unrelated entities để test module nhỏ.
- Có nhiều data sources và cần cô lập.
- Cần tùy chỉnh validation/lifecycle settings cho một nhóm tests.

Tuy nhiên, nếu test nhằm chứng minh **cấu hình runtime production** đúng, nên có một nhóm integration tests chạy đúng Spring/JTA wiring production-like. Một test PU tối giản không thể thay thế mọi tests sử dụng actual deployment settings.

## 65. Những giới hạn của một ví dụ đơn giản

Ví dụ này:

- Chỉ có một entity/table để tập trung vào setup.
- Dùng assigned ID, không kiểm tra IDENTITY/SEQUENCE.
- Dùng resource-local, không kiểm tra distributed JTA.
- Không dùng L2 cache để tránh nhiễu.
- Không tạo nhiều test classes cùng dùng container global.
- Cleanup bằng JPQL bulk DELETE, chưa có foreign-key graph.
- Dùng PostgreSQL CHECK/UNIQUE, không bao phủ tất cả engine semantics.
- Không chạy migration upgrade từ production data.
- Không đo performance trên hàng triệu rows.

Trong dự án thực, thêm tests theo các bối cảnh cần kiểm chứng, không biến một fixture thành công thành lời bảo đảm cho mọi integration scenario.

---

## 66. Các hiểu nhầm thường gặp

### Hiểu nhầm 1: Có `@Entity` là JPA test tự chạy

Không. Cần provider, persistence unit, DB, schema và transaction config.

### Hiểu nhầm 2: `persistence.xml` tự tạo mọi bảng

Không. Schema generation cần được cấu hình/chủ động; migration-first có thể để provider chỉ validate.

### Hiểu nhầm 3: Hibernate `create-drop` giống migration production

Không. Nó dựa trên mapping và có thể thiếu vendor-specific constraints, indexes/triggers/data migrations.

### Hiểu nhầm 4: Flyway migration thành công thì JPA mapping chắc đúng

Không. Cần bootstrap/mapping checks và CRUD/query tests.

### Hiểu nhầm 5: Hibernate `validate` xác minh mọi CHECK/UNIQUE/FK/index

Không. Nó không thay database integrity/schema tests có chủ đích.

### Hiểu nhầm 6: H2 PostgreSQL mode = PostgreSQL thực

Không. Dialect/locking/constraint/index behaviors vẫn có thể khác.

### Hiểu nhầm 7: `EntityManagerFactory` nên tạo cho mỗi test row

Thường không; bootstrap tốn tài nguyên. Factory dùng chung theo scope phù hợp.

### Hiểu nhầm 8: Một EntityManager có thể dùng cho các tests song song

Không. EntityManager không thread-safe và L1 state gây nhiễu.

### Hiểu nhầm 9: `persist()` trả về nghĩa đã commit

Không. Có thể mới trong persistence context.

### Hiểu nhầm 10: `flush()` nghĩa commit thành công

Không. Transaction vẫn có thể rollback hoặc fail ở commit.

### Hiểu nhầm 11: Đọc lại cùng EntityManager chứng minh DB đã commit

Không. Identity map có thể trả managed object.

### Hiểu nhầm 12: `@DataJpaTest` luôn test DB production thật

Không. Embedded replacement/transaction rollback có thể đang hoạt động.

### Hiểu nhầm 13: Test transaction rollback cũng rollback transaction `REQUIRES_NEW`

Không. Một transaction đã commit độc lập không bị outer test rollback hoàn tác.

### Hiểu nhầm 14: DDL luôn rollback được

Không portable; DDL/sequence semantics theo engine.

### Hiểu nhầm 15: Cleanup `DELETE FROM parent` luôn được

Không khi có FK children cần xóa trước.

### Hiểu nhầm 16: Testcontainer mỗi class tự cô lập từng method

Không. Static container giữ DB qua methods; cần cleanup/transactions.

### Hiểu nhầm 17: Random IDs tự tránh được mọi cross-test interference

Không nếu tests cùng DELETE global table hoặc shared tenant.

### Hiểu nhầm 18: Test exception loại RuntimeException là đủ

Không. Phải xác minh đúng DB/JPA failure cause.

### Hiểu nhầm 19: `@Column(nullable=false)` thay database NOT NULL

Không nếu production schema không được tạo đúng.

### Hiểu nhầm 20: UNIQUE(tenant_id,sku) giống UNIQUE(sku)

Không. Business scoping khác.

### Hiểu nhầm 21: Có schema riêng nhưng Flyway/JPA trỏ database khác nhau vẫn ổn

Không. Migrations và queries phải dùng cùng DB/schema.

### Hiểu nhầm 22: SQLState của PostgreSQL dùng cho mọi DB

Không. SQLState/vendor codes và exception wrapping cần theo DB cụ thể.

### Hiểu nhầm 23: Một fresh DB migration test đủ kiểm chứng upgrade từ dữ liệu cũ

Không. Cần V1→V2 fixture có preexisting rows.

### Hiểu nhầm 24: Test failures nên luôn retry

Không. Flakiness do isolation/concurrency phải được sửa, không che.

### Hiểu nhầm 25: DB disposable đồng nghĩa có thể xóa bất kỳ schema nào

Không. Cleanup/destructive operations vẫn cần ownership và scope rõ, tránh nhầm DataSource.

---

## 67. Bài tập 1: Phân biệt persistence unit và schema

**Câu hỏi:** JPA có thể bootstrap thành công nhưng `SELECT` báo bảng không tồn tại không?

**Đáp án:** Có. Unit mô tả provider/mapping, còn schema thực có thể chưa migration hoặc trỏ sai database.

## 68. Bài tập 2: Sai vị trí XML

File `persistence.xml` đặt ở `src/test/resources/config`.

**Đáp án:** Java SE JPA thường tìm `META-INF/persistence.xml` trên classpath. Sửa đường dẫn hoặc cấu hình bootstrap phù hợp.

## 69. Bài tập 3: RESOURCE_LOCAL

Test gọi `em.persist(product)` không begin transaction.

**Đáp án:** Ghi persistence cần transaction phù hợp; thêm begin/commit/rollback quản lý đúng.

## 70. Bài tập 4: Commit và flush

Test gọi `em.flush()` rồi ném exception khiến rollback.

**Câu hỏi:** Row có được commit không?

**Đáp án:** Không. Flush chỉ đồng bộ SQL trong transaction.

## 71. Bài tập 5: L1 cache

Test setter đổi price, rồi `em.find` cùng ID, thấy price mới.

**Đáp án:** Chưa chứng minh DB đã lưu; dùng commit và EntityManager mới.

## 72. Bài tập 6: Migration order

Hibernate validate chạy trước Flyway migration.

**Đáp án:** Có thể fail thiếu bảng/column. Migrate trước factory bootstrap.

## 73. Bài tập 7: Schema nguồn sự thật

Production Flyway thêm CHECK, nhưng H2 test schema.sql không có CHECK.

**Đáp án:** Test có thể pass giả. Chạy production migrations trên production-like DB.

## 74. Bài tập 8: Duplicate SKU

Hai Products có SKU giống nhau nhưng khác tenant.

**Đáp án:** `UNIQUE(tenant_id,sku)` cho phép nếu id khác; hai Products cùng tenant+SKU phải bị từ chối.

## 75. Bài tập 9: Bean Validation và DB CHECK

Entity `@DecimalMin` chặn giá âm trước khi SQL chạy.

**Câu hỏi:** Đã kiểm tra DB CHECK chưa?

**Đáp án:** Chưa. Dùng SQL/JDBC hoặc một đường test tách validation để xác minh database constraint thật.

## 76. Bài tập 10: Static Testcontainers

Một static PostgreSQLContainer dùng cho cả class.

**Câu hỏi:** DB có tự sạch giữa mọi @Test không?

**Đáp án:** Không. Cần cleanup/rollback/per-test namespace.

## 77. Bài tập 11: Parallel tests

Test A xóa tất cả products ở BeforeEach; Test B đang đọc cùng bảng.

**Đáp án:** Race. Dùng database/schema/tenant isolation hoặc chạy tuần tự theo policy.

## 78. Bài tập 12: Spring `@DataJpaTest`

Test persist + flush thành công, cuối method rollback.

**Câu hỏi:** Có chứng minh commit thật không?

**Đáp án:** Không. Cần explicit transaction completion.

## 79. Bài tập 13: Hibernate DDL

Test đang dùng `hibernate.hbm2ddl.auto=create-drop` trên DB dùng chung.

**Đáp án:** Nguy hiểm; có thể phá tables/data. Chuyển sang disposable DB và migration-first/validate.

## 80. Bài tập 14: JDBC CHECK SQLState

PostgreSQL check constraint fail với `23514`.

**Câu hỏi:** Có cần assert SQLState không?

**Gợi ý:** Nếu bài test nhắm DB CHECK cụ thể, xác minh failure source/constraint thay vì chỉ assert RuntimeException; với DB khác thay assertion phù hợp.

## 81. Bài tập 15: Child-first cleanup

Có Orders và Lines với FK line.order_id.

**Đáp án:** Xóa Lines trước Orders trừ khi schema có cascade đúng và bạn chủ ý kiểm thử nó.

## 82. Bài tập 16: Id strategy

`GenerationType.IDENTITY` khiến INSERT xảy ra sớm hơn expected.

**Đáp án:** Timing SQL có thể khác; test đừng giả định mọi INSERT chỉ xuất hiện ở flush.

## 83. Bài tập 17: Test schema upgrade

V2 thêm column NOT NULL nhưng database production còn rows cũ thiếu giá trị.

**Đáp án:** Fresh migration trên empty DB chưa đủ; test upgrade từ V1 với dữ liệu legacy và backfill.

## 84. Bài tập 18: Multi-persistence-unit

Flyway migrate DB A nhưng Hibernate dùng DB B.

**Đáp án:** JPA có thể báo missing table hoặc query sai data; đảm bảo URL/schema/transaction manager đồng nhất.

## 85. Bài tập 19: Concurrency

Hai tests cùng sử dụng `EntityManager` static và chạy parallel.

**Đáp án:** Sai. Mỗi thread/test dùng EntityManager riêng; EM không thread-safe.

## 86. Bài tập 20: CI Docker unavailable

Unit tests pass nhưng JPA IT báo không khởi động được Testcontainers.

**Đáp án:** Đây là infrastructure/runtime configuration issue; cần CI container support, không sửa entity mapping.

## 87. Bài tập 21: Query native

Native SQL query dùng column mới, mapping bootstrap vẫn pass nhưng query fail.

**Đáp án:** Targeted integration test phải thực thi native SQL trên migrated schema.

## 88. Bài tập 22: NoResult vs DB integrity

`find` trả null, còn duplicate SKU INSERT ném SQL unique violation.

**Đáp án:** Đây là hai failure sources khác nhau; test và xử lý exception riêng.

## 89. Bài tập 23: SQL cleanup sai DB

Test script nhận JDBC URL từ environment variable production.

**Đáp án:** Không an toàn. Bind trực tiếp disposable container DataSource và có guards cho destructive operations.

## 90. Bài tập 24: Snapshot/fixture independence

Test thứ hai chỉ pass khi test thứ nhất chạy trước.

**Đáp án:** Fixture không độc lập. Mỗi test phải có dữ liệu setup riêng và cleanup rõ.

## 91. Bài tập 25: Thiết kế bộ test nền tảng

**Yêu cầu:** Viết JPA integration tests đảm bảo Product có unique SKU theo tenant, giá không âm và rollback đúng.

**Hướng giải:**

1. PostgreSQL Testcontainers per class.
2. Flyway apply production migration schema.
3. `persistence.xml` RESOURCE_LOCAL, Hibernate validate.
4. EntityManagerFactory bootstrap sau migrations.
5. BeforeEach cleanup có scope.
6. Test persist/commit + fresh readback.
7. Test explicit flush + rollback + fresh readback.
8. Test duplicate SKU cùng tenant nhận SQL unique failure.
9. Test cùng SKU khác tenant được phép.
10. Test negative price nhận DB CHECK failure.
11. Dùng transactions/context mới cho mỗi test.
12. Đóng factory trước khi container stop.
13. Bổ sung Spring/JTA integration tests nếu production dùng những transaction managers đó.

---

## 92. Checklist setup persistence unit và schema thử nghiệm

Trước khi tin kết quả JPA integration test, xác nhận:

1. Test có đúng mục tiêu JPA integration, không chỉ unit mock không?
2. Persistence unit được đặt tên rõ và test gọi đúng tên không?
3. `META-INF/persistence.xml` nằm trên runtime test classpath không?
4. Jakarta Persistence API và ORM provider tương thích không?
5. Có trộn `javax.persistence` và `jakarta.persistence` không?
6. Những entities cần thiết đã được đăng ký/scan không?
7. Transaction type RESOURCE_LOCAL/JTA có đúng không?
8. Có cố gọi `getTransaction()` trên container-managed EM không?
9. Database được test trỏ tới có thật sự disposable không?
10. JDBC URL/user/schema lấy đúng từ Testcontainers/DataSource không?
11. Có dùng production secrets hoặc host production nhầm không?
12. Database engine/version có đại diện production cho scenario không?
13. Migrations đã chạy trước JPA bootstrap chưa?
14. Migrations có dùng cùng JDBC URL/schema như EntityManagerFactory không?
15. Có một nguồn DDL có quyền sở hữu rõ không?
16. Có tránh trộn Hibernate create-drop và Flyway thiếu kiểm soát không?
17. Schema validation có bật khi dùng migration-first không?
18. Có biết Hibernate validate không bao phủ mọi CHECK/UNIQUE/FK/index không?
19. Critical constraints đã được test bằng hành vi vi phạm chưa?
20. Test có tạo EntityManager riêng và đóng trong finally không?
21. Factory có được đóng sau suite/class không?
22. Có transaction begin/commit/rollback đúng owner không?
23. Test cần commit thật có thật sự commit không?
24. Test rollback có xác minh bằng context mới không?
25. Có tránh dùng L1 managed object để kết luận DB đã commit không?
26. Có test duplicate key bằng đúng tenant scope không?
27. Có phân biệt Bean Validation exception với DB SQLState không?
28. Có tránh assert RuntimeException quá chung không?
29. Fixture dữ liệu có độc lập giữa methods không?
30. Cleanup có tôn trọng FK/cascade không?
31. Có chạy parallel tests cùng schema không?
32. Nếu có, isolation đủ mạnh không?
33. Có tránh reset schema trên shared DB không?
34. Có kiểm tra default schema/search_path phù hợp không?
35. Có test native SQL/DB-specific mapping cần thiết không?
36. Có test migration upgrade trên data cũ khi phù hợp không?
37. Có hiểu DDL/sequence rollback semantics của engine không?
38. Có ghi nhận version PostgreSQL/driver/provider/migration tool không?
39. CI có container runtime và image access không?
40. Có logging đủ debug startup mà không lộ credentials không?
41. Testcontainers có bị reuse khiến data lưu giữa runs không?
42. Có tránh random fixtures không thể tái lập không?
43. Có xử lý transaction rollback-only sau failed flush không?
44. Có phân biệt Spring `@DataJpaTest` rollback với service commit không?
45. Có kiểm tra DB catalog/schema trong các tests cần index/constraint không?
46. Có giữ test setup đủ nhanh nhưng không hy sinh correctness không?
47. Có biết test nào chạy H2 và test nào chạy production engine không?
48. Có cleanup đúng ownership khi thất bại không?
49. Có tách unit/domain tests khỏi integration/schema tests hợp lý không?
50. Có thể chạy lại toàn suite từ một database sạch và cho cùng kết quả không?

Checklist không đòi một môi trường nặng cho mọi bài test; nó giúp bảo đảm **những khẳng định về JPA persistence/transaction/database thực sự được kiểm chứng trên một môi trường có thể tái lập**.

## Kết luận

**Thiết lập persistence unit và lược đồ thử nghiệm có kiểm soát** là nền móng của toàn bộ kiểm thử JPA.

Những nguyên tắc quan trọng:

- Persistence unit quyết định entity mappings, provider và transaction; database schema quyết định cấu trúc và ràng buộc thực. Cả hai phải nhất quán.
- Với Java SE integration test, `RESOURCE_LOCAL` + `EntityManagerFactory` + EntityManager riêng mỗi unit of work giúp thấy rõ begin/flush/commit/rollback.
- Một database disposable cùng engine production, như PostgreSQL Testcontainers, giúp test transaction/constraint semantics đáng tin hơn mô phỏng bằng H2 khi có DB-specific behavior.
- **Migration-first** với Flyway/Liquibase và Hibernate schema `validate` thường đáng tin hơn để kiểm tra deploy schema, nhưng vẫn cần targeted tests cho CHECK/UNIQUE/FK/index.
- Ghi dữ liệu trong persistence context và gọi `flush()` **không đồng nghĩa commit**. Hãy đọc lại bằng context mới sau transaction completion.
- Test fixture phải độc lập, có cleanup/rollback đúng phạm vi, tránh races khi parallel và không được chạy destructive operations trên shared/prod DB.
- Spring `@DataJpaTest` thường rollback cuối test; nếu muốn kiểm chứng commit, phải tạo boundary thật và biết transaction manager nào sở hữu nó.
- Migrations schema từ phiên bản cũ, native SQL, constraints và concurrency có thể cần các integration scenarios riêng.
- CI phải tái tạo cùng DB/schema/settings, không dựa vào dữ liệu sót lại của môi trường developer.

Một môi trường test được thiết lập đúng phải trả lời được sáu câu hỏi: **“EntityManager thuộc persistence unit nào? Nó đang kết nối database/schema nào? Ai tạo và kiểm chứng lược đồ? Ai sở hữu transaction? Dữ liệu được cô lập và dọn như thế nào? Và phép khẳng định đã đọc committed state thực hay chỉ là object trong bộ nhớ?”**.

Khi sáu câu hỏi đó có câu trả lời rõ ràng, các bài kiểm thử `persist`, `merge`, lazy fetching, JPQL, flush, optimistic locking và rollback mới có nền tảng đáng tin để phát hiện lỗi trước khi triển khai.

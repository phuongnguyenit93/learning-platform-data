# Ràng buộc UNIQUE, FOREIGN KEY và thời điểm phát sinh lỗi trong Spring Data JPA

Một bài test Spring Data JPA có thể gọi `repository.save(entity)` mà **không thấy exception**, dù dữ liệu thực tế vi phạm **unique constraint** hoặc **foreign key**. Nguyên nhân quan trọng là JPA/Hibernate quản lý **persistence context** và có thể trì hoãn lệnh SQL đến lúc **flush**. Ngược lại, một số chiến lược sinh ID (như `IDENTITY`) phải thực thi INSERT sớm; một số ràng buộc database (như `DEFERRABLE INITIALLY DEFERRED` của PostgreSQL) lại có thể dời việc kiểm tra tới **commit**, kể cả khi SQL đã chạy.

Vì vậy, muốn test tính toàn vẹn dữ liệu phải trả lời đủ bốn câu hỏi:

1. **Ràng buộc nào nằm thật trong schema database?** Java annotation mô tả mapping, nhưng schema production có thể do Flyway/Liquibase quản lý.
2. **Dữ liệu nào đang vi phạm?** Trùng khóa duy nhất, tham chiếu tới parent không tồn tại, xóa parent đang được child tham chiếu, v.v.
3. **Tại thời điểm nào SQL và constraint check xảy ra?** `save/persist`, auto-flush, `saveAndFlush`, `EntityManager.flush` hay `commit`.
4. **Exception được thấy ở lớp nào?** JDBC, Hibernate, Jakarta Persistence, Spring Data repository hoặc ranh giới transaction commit.

Bài Knowledge này tập trung vào **Spring Data JPA**, trình bày UNIQUE/FK, sơ đồ thời điểm kiểm tra, cách viết `@DataJpaTest` có assertion đáng tin và ví dụ **Java 17 + Spring Boot 3.5 + H2** chạy được. Cuối bài phân biệt kiểm thử trên H2 với PostgreSQL production có deferred constraints.

## 1. Hai loại ràng buộc quan trọng

### 1.1. UNIQUE — không cho dữ liệu trùng theo khóa xác định

Một khóa nghiệp vụ như `sku` của sản phẩm cần duy nhất trong toàn bảng. Database có thể kiểm bằng:

```sql
ALTER TABLE products
    ADD CONSTRAINT uk_products_sku UNIQUE (sku);
```

Lệnh trên là **ví dụ SQL DDL**, chỉ chạy được khi bảng `products` đã tồn tại và chưa có ràng buộc trùng tên. Trong entity JPA:

```java
@Entity
@Table(
    name = "products",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_products_sku",
        columnNames = "sku"))
class Product {
    // @Id, sku, ...
}
```

Đây là **snippet mapping**, không phải file Java đầy đủ. `@Table(uniqueConstraints=...)` dùng để mô tả ràng buộc khi **công cụ tạo schema** thực hiện DDL; nó không đồng nghĩa Hibernate sẽ “kiểm trùng” bằng Java trước mỗi `save()`.

Một khóa duy nhất có thể gồm **nhiều cột**, ví dụ cùng tenant không được trùng external code, nhưng hai tenant khác nhau có thể dùng cùng code:

```java
@Table(name = "orders",
       uniqueConstraints = @UniqueConstraint(
           name = "uk_orders_tenant_external",
           columnNames = {"tenant_id", "external_code"}))
```

`@Column(unique = true)` diễn tả **unique trên một cột**. Với composite unique, `@UniqueConstraint(columnNames = {...})` rõ ràng hơn. Trong cơ sở dữ liệu thực, constraint có thể dựa trên index; nhưng **index không unique** chỉ giúp truy vấn, không đảm bảo loại trừ bản ghi trùng.

**Điểm cần nhớ về NULL:** nhiều database cho phép nhiều giá trị `NULL` trong cột UNIQUE vì NULL không so sánh như giá trị thường; một số DB có tùy chọn ngữ nghĩa NULL khác. Nếu trường **bắt buộc duy nhất và phải có giá trị**, cần cả **`NOT NULL`** và **`UNIQUE`**, và kiểm schema thực của DB đang dùng.

### 1.2. FOREIGN KEY — child phải tham chiếu parent tồn tại

Giả sử một `Product` phải thuộc về một `Category`:

```sql
ALTER TABLE products
    ADD CONSTRAINT fk_products_categories
    FOREIGN KEY (category_id)
    REFERENCES categories (id);
```

Đây cũng là **snippet DDL**, cần hai bảng và dữ liệu tương thích. Một FK đảm bảo giá trị `products.category_id`, nếu **không null**, phải tham chiếu tới một `categories.id` hợp lệ. Nếu `category_id` không được null thì cần **`NOT NULL`** ngoài FK. Khi chưa có constraint thật trong database, một annotation `@ManyToOne` trên code **không đủ** để database tự bảo vệ toàn vẹn tham chiếu.

Mapping JPA tương ứng:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(
    name = "category_id",
    nullable = false,
    foreignKey = @ForeignKey(name = "fk_products_categories"))
private Category category;
```

- `@ManyToOne` mô tả quan hệ object từ child tới parent; `LAZY` điều chỉnh cách load association, **không phải FK check**.
- `optional=false` diễn tả yêu cầu association ở phía mô hình JPA; ORM có thể báo lỗi khi field null.
- `@JoinColumn(nullable=false)` là tín hiệu tạo cột NOT NULL nếu Hibernate tạo DDL; không thay thế kiểm schema production đã tồn tại.
- `@ForeignKey(name=...)` đặt metadata/name cho **constraint FK khi sinh DDL**, không phải lệnh thực hiện check sớm trong JVM.
- `CascadeType.PERSIST`/`REMOVE` của JPA **khác** quy tắc `ON DELETE CASCADE` của database. Không mặc định xóa Category sẽ tự xóa Product nếu chưa chủ đích thiết kế cascade.

**Tình huống kiểm quan trọng:** INSERT product với `category_id` không tồn tại phải fail; xóa category khi còn product phụ thuộc phải fail nếu FK mặc định không có cascade/set-null. Dùng SQL/JDBC trực tiếp để test FK vật lý có thể làm rõ hơn việc chỉ tạo một Java object parent chưa được persist — trường hợp thứ hai đôi khi bị ORM chặn **trước khi database kiểm FK**.

## 2. Khác nhau giữa Bean Validation, JPA mapping và database constraint

| Lớp kiểm tra | Ví dụ | Khi nào có thể báo lỗi | Bằng chứng |
|---|---|---|---|
| **Bean Validation** | `@NotNull`, `@Size`, `@Valid` | Khi validation được gọi hoặc lifecycle event JPA kích hoạt validation nếu provider/integration có mặt | DTO/entity đáp ứng rule validation, **không chứng minh DB UNIQUE/FK** |
| **JPA/Hibernate object graph** | `optional=false`, transient association | `persist`/`flush` tùy mapping, generator và ORM | Graph/association có lỗi mapping hoặc trạng thái object |
| **Database NOT NULL/UNIQUE/FK** | `NOT NULL`, `uk_products_sku`, `fk_products_categories` | Lúc SQL được DB thực thi hoặc **commit** nếu constraint được defer | **Database thật** bảo vệ tính toàn vẹn |
| **Spring DAO exception translation** | `DataIntegrityViolationException` | Khi JDBC/repository exception đi qua lớp được translate | Cách exception được trình bày ra tầng ứng dụng |

Cần tách bạch ba exception rất dễ nhầm:

- **`jakarta.validation.ConstraintViolationException`**: vi phạm *Bean Validation* (ví dụ `@NotBlank`) — không nhất thiết có SQL.
- **`org.hibernate.exception.ConstraintViolationException`**: Hibernate bọc một lỗi ràng buộc do **SQL/database** báo (có thể chứa constraint name/SQLState tùy driver).
- **`org.springframework.dao.DataIntegrityViolationException`**: abstraction của Spring cho lỗi integrity ở data-access layer, thường được repository/JdbcTemplate translate từ SQLException/Hibernate exception.

Trong Hibernate/JPA, lỗi còn có thể được bọc trong `PersistenceException`, `TransactionSystemException` hoặc exception của transaction boundary. **Đừng viết một test mong chính xác một loại exception cho mọi DB, mọi timing và mọi tầng gọi.** Chọn abstraction phù hợp tầng test và kiểm root cause/constraint name nếu contract thực sự phụ thuộc vào nó.

## 3. Thời điểm lỗi: `persist`, `save`, `flush`, query và commit

Sơ đồ điển hình với `GenerationType.SEQUENCE`, transaction đang hoạt động, database kiểm constraint **ngay khi SQL thực thi**:

```text
new Product(...)                  transient object
      |
      v
repository.save(product)          persist/merge vào persistence context
      |                             (có thể lấy sequence ID)
      |                             INSERT có thể vẫn chỉ nằm trong queue
      v
entityManager.flush()             Hibernate phát INSERT/UPDATE/DELETE SQL
      |
      +-- DB UNIQUE/FK hợp lệ ---> SQL thành công, transaction vẫn mở
      |
      +-- DB UNIQUE/FK sai -----> SQL lỗi, thường được Spring translate
      |
      v
transaction COMMIT                 nếu chưa flush: có thể flush ở đây
                                   với DEFERRABLE: có thể kiểm constraint tại đây
```

### `repository.save()` không phải lệnh `INSERT` tức thời

Spring Data JPA `save` thường gọi `EntityManager.persist` cho entity mới hoặc `merge` cho entity không mới. Hibernate có **write-behind persistence context**, nên việc kiểm constraint của **database** thường chưa xảy ra cho tới khi phát lệnh SQL.

Với **`SEQUENCE`**, ORM có thể lấy ID từ sequence mà **chưa INSERT row**. Vì vậy:

```java
Product p = repository.save(new Product("SKU-1", category));
assertNotNull(p.getId());
```

ID không null chỉ có nghĩa entity có identifier, **không chứng minh database đã chấp nhận row**, và cũng không chứng minh transaction sẽ commit thành công. Snippet ở đây dựa vào class `Product` của ví dụ sau, chưa độc lập.

### `IDENTITY` thường INSERT sớm để lấy ID

Với `GenerationType.IDENTITY`, database tạo ID trong lệnh INSERT; Hibernate **thường phải thực thi INSERT ngay khi persist/save** để biết ID. Vì vậy UNIQUE/FK có thể nổ ngay trong `save()`, **trước khi gọi `flush()`**. Không nên dạy “vi phạm UNIQUE chỉ xuất hiện ở saveAndFlush” như một quy tắc bất biến.

Một số cấu hình/version Hibernate có cơ chế trì hoãn identity insert trong tình huống riêng. Điều cần khẳng định là **generation strategy và flush mode ảnh hưởng timing**, không đoán bằng tên API.

### Flush không đồng nghĩa commit

- `EntityManager.flush()` / `repository.flush()`: đồng bộ các thay đổi đang pending thành SQL; **không commit**, transaction vẫn có thể rollback.
- `repository.saveAndFlush(entity)`: gọi save rồi flush; hữu ích khi muốn lỗi ràng buộc **immediate** xuất hiện ngay trong assertion của test, nhưng không ép tất cả lỗi phải xuất hiện tại đó.
- Flush tự động (`FlushModeType.AUTO`) có thể xảy ra trước query cần đồng bộ dữ liệu hoặc ở commit. Thời điểm chính xác phụ thuộc query/ORM/configuration.
- Với DB có constraint **deferred**, SQL có thể thành công ở flush rồi **commit mới fail**, vì DB còn chờ kiểm tính hợp lệ cuối transaction.

**Không bắt lỗi rồi tiếp tục dùng cùng persistence context/transaction như chưa có chuyện gì xảy ra.** Sau khi flush/JDBC command lỗi, transaction có thể bị đánh dấu rollback-only hoặc hỏng trạng thái; trong PostgreSQL, transaction gặp lỗi SQL thường cần rollback trước khi chạy SQL tiếp. Mỗi test dự kiến lỗi nên kết thúc sau assertion, để Spring TestContext xử lý rollback; muốn xác nhận exception ở commit phải kiểm **tại boundary commit** trong transaction riêng.

## 4. Ràng buộc immediate và deferrable: DB nào mới quyết định?

Mặc định nhiều DB kiểm UNIQUE/FK tại **thời điểm câu lệnh SQL**. Nhưng PostgreSQL hỗ trợ **`DEFERRABLE`** cho một số constraint như UNIQUE và FOREIGN KEY.

Ví dụ PostgreSQL (độc lập với JPA):

```sql
CREATE TABLE pg_categories (
    id bigint PRIMARY KEY
);

CREATE TABLE pg_products (
    id bigint PRIMARY KEY,
    sku text NOT NULL,
    category_id bigint NOT NULL,
    CONSTRAINT uq_pg_products_sku
        UNIQUE (sku) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_pg_products_categories
        FOREIGN KEY (category_id) REFERENCES pg_categories(id)
        DEFERRABLE INITIALLY DEFERRED
);
```

Với `INITIALLY DEFERRED`, PostgreSQL có thể cho **tạm vi phạm** trong transaction nhưng bắt buộc dữ liệu **hợp lệ lúc COMMIT**. Ví dụ forward reference:

```sql
BEGIN;
INSERT INTO pg_products(id, sku, category_id)
    VALUES (1, 'SKU-1', 42);
INSERT INTO pg_categories(id) VALUES (42);
COMMIT;
```

Ví dụ trên có thể **commit thành công** vì cuối transaction parent `42` đã tồn tại, dù khi INSERT child thì chưa tồn tại. Nếu không INSERT parent, FK được defer sẽ làm **COMMIT thất bại**. Tương tự, UNIQUE deferred có thể cho hai row cùng `sku` tồn tại tạm thời, nhưng sẽ fail khi commit nếu xung đột không được giải quyết.

```sql
BEGIN;
INSERT INTO pg_products(id, sku, category_id) VALUES (2, 'DUP', 42);
INSERT INTO pg_products(id, sku, category_id) VALUES (3, 'DUP', 42);
-- COMMIT sẽ báo lỗi UNIQUE nếu cả hai DUP vẫn còn.
ROLLBACK;
```

Snippet thứ hai cố ý **ROLLBACK thay vì thực hiện COMMIT lỗi** để không tạo dữ liệu; nếu muốn kiểm thời điểm phát sinh lỗi, chạy một transaction có commit trong **test DB tách biệt** và assert exception tại boundary commit. Trong PostgreSQL:

```sql
-- Trong transaction, chuyển constraint deferred sang kiểm ngay:
SET CONSTRAINTS uq_pg_products_sku, fk_pg_products_categories IMMEDIATE;
```

Lệnh `SET CONSTRAINTS` có thể kích hoạt việc kiểm các vi phạm đã tồn tại tại thời điểm chuyển sang IMMEDIATE. Nó là cú pháp PostgreSQL, **không phải JPQL hay SQL portable**.

**Không suy ra H2 có cùng ngữ nghĩa deferrable như PostgreSQL.** Các ví dụ runnable ở phần 6 dùng H2 để kiểm immediate UNIQUE/FK và flush. Muốn kiểm **commit-time deferral**, dùng PostgreSQL thật trong môi trường test (ví dụ Testcontainers) và migrations DDL đúng; không cố chuyển expected error từ commit thành flush bằng cách gọi `saveAndFlush`.

Lưu ý PostgreSQL: `NOT DEFERRABLE` là mặc định; chỉ những constraint đã khai báo `DEFERRABLE` mới có thể trì hoãn theo `INITIALLY DEFERRED`/`SET CONSTRAINTS`. Tính năng `ON CONFLICT` cũng có hạn chế khi chọn một deferrable unique constraint làm conflict arbiter.

## 5. Ví dụ runnable: Spring Boot 3.5, JPA, H2 và 6 phép kiểm

Ví dụ có hai entity: `Category` (parent) và `Product` (child).

- `categories.code` là duy nhất; `products.sku` có UNIQUE constraint tên `uk_products_sku`.
- `products.category_id` có FK tới `categories.id`, không null; **không bật ON DELETE CASCADE**.
- Cả hai entity dùng **`SEQUENCE`**, để có thể minh họa `save` cấp ID nhưng chưa INSERT, còn `flush` kích hoạt SQL.
- `@DataJpaTest` dùng database H2 in-memory, transaction riêng cho mỗi test và rollback sau test; không mở server HTTP.
- Test Spring Data repository kiểm vi phạm unique qua `saveAndFlush`/`flush`. Test `JdbcTemplate` bypass ORM để **chứng minh FK vật lý** được database áp dụng.

### 5.1. Cây thư mục

```text
jpa-constraints/
├── pom.xml
└── src/
    ├── main/java/com/example/catalog/
    │   ├── CatalogApplication.java
    │   ├── Category.java
    │   ├── CategoryRepository.java
    │   ├── Product.java
    │   └── ProductRepository.java
    └── test/java/com/example/catalog/
        └── ConstraintTimingTest.java
```

### 5.2. `pom.xml`: Java 17 + JPA + H2 test database

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
    <artifactId>jpa-constraints</artifactId>
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

Ở đây `spring-boot-starter-data-jpa` mang Hibernate/JPA và Spring Data; H2 đủ để chạy test immediate constraints trong bộ nhớ. `spring-boot-starter-test` cung cấp JUnit Jupiter/AssertJ/Spring Test. Bộ phiên bản do Boot BOM quản lý; khi đưa vào dự án thật, chọn patch Spring Boot phù hợp chính sách bảo trì của tổ chức.

### 5.3. Spring Boot application config

File **`src/main/java/com/example/catalog/CatalogApplication.java`**:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

`@DataJpaTest` từ package test tương ứng tìm được `@SpringBootApplication` ở cùng package gốc; nó vẫn giới hạn bean scope về JPA, không nạp controller/service không cần thiết.

### 5.4. Entity `Category` là parent

File **`src/main/java/com/example/catalog/Category.java`**:

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "categories")
public class Category {
    @Id
    @GeneratedValue(
            strategy = GenerationType.SEQUENCE,
            generator = "category_id_generator")
    @SequenceGenerator(
            name = "category_id_generator",
            sequenceName = "category_id_seq",
            allocationSize = 1)
    private Long id;

    @Column(name = "code", nullable = false, unique = true, length = 64)
    private String code;

    protected Category() {
        // Required by JPA.
    }

    public Category(String code) {
        this.code = code;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }
}
```

`Category.code` unique là một ví dụ single-column unique. `@SequenceGenerator` cho phép Hibernate dùng sequence để cấp identifier mà **không buộc INSERT ngay như IDENTITY** trong trường hợp thông thường.

### 5.5. Entity `Product` là child, có UNIQUE và FK

File **`src/main/java/com/example/catalog/Product.java`**:

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "products",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_products_sku",
                columnNames = {"sku"}))
public class Product {
    @Id
    @GeneratedValue(
            strategy = GenerationType.SEQUENCE,
            generator = "product_id_generator")
    @SequenceGenerator(
            name = "product_id_generator",
            sequenceName = "product_id_seq",
            allocationSize = 1)
    private Long id;

    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
            name = "category_id",
            nullable = false,
            foreignKey = @ForeignKey(name = "fk_products_categories"))
    private Category category;

    protected Product() {
        // Required by JPA.
    }

    public Product(String sku, Category category) {
        this.sku = sku;
        this.category = category;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public Category getCategory() {
        return category;
    }
}
```

Entity dùng **annotation sinh DDL** khi Hibernate được phép tạo schema trong test. `Product` yêu cầu parent `Category` có thật; nhưng nếu chỉ tạo một Category Java object chưa persist, Hibernate có thể báo **unsaved transient association** thay vì một SQLException về foreign key. Vì thế test FK phía dưới dùng **JDBC SQL insert** với nonexistent ID để chủ đích kiểm database constraint.

### 5.6. Spring Data JPA repositories

File **`src/main/java/com/example/catalog/CategoryRepository.java`**:

```java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CategoryRepository extends JpaRepository<Category, Long> {
}
```

File **`src/main/java/com/example/catalog/ProductRepository.java`**:

```java
package com.example.catalog;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
    Optional<Product> findBySku(String sku);
}
```

Hai repository có `saveAndFlush`/`flush` từ `JpaRepository`. `findBySku` dùng query derivation của Spring Data; test happy path sẽ flush và clear persistence context trước khi đọc để có bằng chứng rõ về dữ liệu database.

### 5.7. Test đầy đủ: 6 `@Test` độc lập

File **`src/test/java/com/example/catalog/ConstraintTimingTest.java`**:

```java
package com.example.catalog;

import javax.sql.DataSource;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop")
class ConstraintTimingTest {

    @Autowired
    private CategoryRepository categories;

    @Autowired
    private ProductRepository products;

    @Autowired
    private DataSource dataSource;

    @PersistenceContext
    private EntityManager entityManager;

    private JdbcTemplate jdbc;

    @BeforeEach
    void createJdbcHelper() {
        jdbc = new JdbcTemplate(dataSource);
    }

    @Test
    void validSkuAndForeignKeyCanBePersistedAndLoaded() {
        Category category = categories.saveAndFlush(new Category("BOOKS"));
        products.saveAndFlush(new Product("SKU-001", category));

        entityManager.clear(); // Bỏ cache JPA để đọc lại qua repository.
        Product loaded = products.findBySku("SKU-001").orElseThrow();

        assertEquals("SKU-001", loaded.getSku());
        assertEquals("BOOKS", loaded.getCategory().getCode());
    }

    @Test
    void duplicateUniqueSkuFailsWhenSaveAndFlushExecutesSql() {
        Category category = categories.saveAndFlush(new Category("BOOKS"));
        products.saveAndFlush(new Product("SKU-DUP", category));

        DataIntegrityViolationException error = assertThrows(
                DataIntegrityViolationException.class,
                () -> products.saveAndFlush(
                        new Product("SKU-DUP", category)));

        assertNotNull(error.getMostSpecificCause());
        // Kết thúc test; không tiếp tục thao tác với transaction đã lỗi.
    }

    @Test
    void saveCanAssignSequenceIdsBeforeUniqueCheckAtFlush() {
        Category category = categories.saveAndFlush(new Category("BOOKS"));

        Product first = products.save(new Product("SKU-LATER", category));
        Product second = products.save(new Product("SKU-LATER", category));

        assertNotNull(first.getId());
        assertNotNull(second.getId());

        assertThrows(
                DataIntegrityViolationException.class,
                products::flush);
        // Với SEQUENCE và flush mode thông thường, INSERT chờ tới flush.
    }

    @Test
    void databaseForeignKeyRejectsOrphanInsert() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbc.update(
                        "INSERT INTO products(id, sku, category_id) " +
                        "VALUES (?, ?, ?)",
                        900_001L, "SKU-ORPHAN", 999_999L));
        // Bypass ORM => vi phạm FK vật lý trong H2.
    }

    @Test
    void databaseForeignKeyBlocksDeletingReferencedParent() {
        Category category = categories.saveAndFlush(new Category("BOOKS"));
        products.saveAndFlush(new Product("SKU-CHILD", category));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbc.update(
                        "DELETE FROM categories WHERE id = ?",
                        category.getId()));
    }

    @Test
    void differentSkuValuesAreAllowedUnderSameParent() {
        Category category = categories.saveAndFlush(new Category("BOOKS"));
        products.saveAndFlush(new Product("SKU-A", category));
        products.saveAndFlush(new Product("SKU-B", category));

        entityManager.clear();

        assertTrue(products.findBySku("SKU-A").isPresent());
        assertTrue(products.findBySku("SKU-B").isPresent());
    }
}
```

**Vì sao các test được thiết kế theo cách này:**

- **Happy path** chứng minh cả UNIQUE/FK không chặn dữ liệu hợp lệ; `entityManager.clear()` tránh chỉ nhìn lại object đang managed trong persistence context.
- **Duplicate khi `saveAndFlush`** xác nhận Spring Data repository có thể expose `DataIntegrityViolationException` khi SQL vi phạm `uk_products_sku`. Đừng phụ thuộc nguyên văn error message của H2: khác DB/vendor/driver nó có thể đổi.
- **Hai `save` rồi `flush`** dùng `SEQUENCE` cố ý. Hai entity có ID **không đảm bảo** hai row đã được insert; flush phát hiện xung đột. Test minh họa một đường đi hợp lệ, không tuyên bố mọi `save` đều trì hoãn INSERT trong mọi mapping.
- **Orphan insert bằng JDBC** chứng minh **database** thật có FK tới `categories`. Nếu chỉ tạo `new Category` rồi gán vào child, ORM có thể báo lỗi transient trước DB, khiến bài test không có bằng chứng FK vật lý.
- **Xóa parent** dùng JDBC để kiểm FK chặn DELETE khi còn Product, khác với hành vi cascading của JPA nếu entity mapping cấu hình khác.
- **Hai SKU khác nhau** chứng minh unique không chặn các bản ghi hợp lệ cùng category.

Các test kỳ vọng lỗi **không chạy thêm query/repository operation sau khi bắt exception** vì transaction bị lỗi có thể không còn trạng thái tin cậy. Mỗi test có transaction riêng và `@DataJpaTest` rollback cuối test. Điều này giảm rò rỉ fixture giữa test methods. Không kiểm soát thứ tự thực thi test và không dựa vào trạng thái được để lại bởi test khác.

### 5.8. Chạy test và kết quả dự kiến

Trong thư mục chứa `pom.xml`, cần **JDK 17+** và Maven:

```bash
mvn test
```

Nếu có Maven Wrapper:

```bash
./mvnw test
```

Hoặc chạy riêng:

```bash
mvn -Dtest=ConstraintTimingTest test
```

Trên Windows dùng `mvnw.cmd` nếu có Wrapper, hoặc `mvn` khi Maven đã được cài. Với đúng file/mapping/H2 trong ví dụ, kết quả kỳ vọng **6 tests run, 0 failures, 0 errors**. Những test vi phạm UNIQUE/FK **PASS vì `assertThrows` bắt đúng ngoại lệ**, không phải vì database cho phép vi phạm. JUnit/Surefire có thể in SQL error log ở stderr dù test PASS; đó không nhất thiết là test failure.

**Giới hạn ví dụ:** test chạy trên **H2** với constraints immediate và DDL do Hibernate sinh trong context test. Nó **không chứng minh** migration production đã tạo đúng tên/ràng buộc, hay tính tương thích với PostgreSQL deferrable constraints/transaction isolation. Phần kiểm thực tế database production-like ở mục 7.

## 6. `@DataJpaTest` mặc định transactional: các lỗi “xanh giả”

Trong Spring Boot 3.5, `@DataJpaTest` thông thường tạo JPA slice, dùng embedded test database khi có và mỗi test **transactional + rollback sau test**. Đây là lựa chọn tốt cho repository mapping/query, nhưng có hai hệ quả quan trọng.

### 6.1. `save()` rồi không flush: test chưa chứng minh DB constraint

Ví dụ test **không đáng tin**:

```java
@Test
void doesNotActuallyCheckUniqueAtDatabase() {
    products.save(new Product("DUP", category));
    products.save(new Product("DUP", category));
    // Test kết thúc rồi rollback; INSERT có thể chưa chạy!
}
```

Đây **chỉ là anti-pattern snippet**, `category` là fixture giả định; không phải phương thức chạy độc lập. Trong `@DataJpaTest`, nếu không có flush/query kích hoạt SQL, test có thể **xanh dù vi phạm**, vì rollback chỉ cần vứt các changes chưa synchronize. Cần dùng `saveAndFlush`/`flush` để kiểm constraint immediate, hoặc **transaction commit thật** để kiểm deferrable.

### 6.2. Flush có thể xảy ra trước query

```java
products.save(new Product("DUP", category));
products.save(new Product("DUP", category));
products.count(); // Với AUTO, query có thể kích hoạt flush trước SELECT.
```

Đây là snippet cảnh báo: `count()` **không phải phép thử tính uniqueness**, nhưng Hibernate có thể flush pending inserts trước query, khiến exception xuất hiện tại `count` thay vì `save`. Không dựa vào việc xếp dòng code đơn giản để suy đoán nơi exception phát sinh.

### 6.3. Cần kiểm commit-time failure ở chính ranh giới commit

Khi dùng PostgreSQL `DEFERRABLE INITIALLY DEFERRED`, test dạng `@DataJpaTest` rollback cuối method **có thể không chạy bước commit để DB bắt vi phạm**. Muốn chứng minh commit fail:

1. Tạo database test đúng engine (thường **PostgreSQL Testcontainers**) và áp dụng Flyway/Liquibase migration chứa constraint deferrable.
2. Thực hiện các thao tác trong transaction **thật sự cố commit** (ví dụ một `TransactionTemplate` transaction độc lập, không nằm trong outer rollback test transaction).
3. Assert exception tại **`commit`/ranh giới `TransactionTemplate.execute`**, không chỉ quanh `save` hay `flush`.
4. Rollback/cleanup test fixture an toàn và xác minh không làm hỏng database dùng chung.

Ví dụ ý tưởng **không runnable trên H2**:

```java
assertThrows(RuntimeException.class, () ->
    transactionTemplate.executeWithoutResult(status -> {
        // save hai row trùng khóa được constraint DEFERRABLE kiểm lúc commit
        repository.save(new Product("DUP", existingCategory));
        repository.save(new Product("DUP", existingCategory));
        repository.flush(); // Có thể vẫn không lỗi do constraint deferred.
    })
);
```

Snippet này cố ý **không tự chạy độc lập**: `transactionTemplate`, `repository`, `existingCategory` và schema PostgreSQL deferrable là điều kiện phải dựng trong integration test; tránh bắt `RuntimeException` rộng trong test production mà không kiểm cause/constraint cụ thể. Trong test thật, chọn exception đúng ranh giới và xác nhận root cause của constraint dự kiến, không nhầm với lỗi kết nối hoặc mapping.

## 7. Schema production: Hibernate DDL khác Flyway/Liquibase migrations

Trong ví dụ `@DataJpaTest(properties="spring.jpa.hibernate.ddl-auto=create-drop")`, Hibernate **tạo schema test** từ annotations. Còn production thường dùng migration/versioned DDL:

```sql
CREATE TABLE categories (
    id BIGINT PRIMARY KEY,
    code VARCHAR(64) NOT NULL,
    CONSTRAINT uk_categories_code UNIQUE (code)
);

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    category_id BIGINT NOT NULL,
    CONSTRAINT uk_products_sku UNIQUE (sku),
    CONSTRAINT fk_products_categories
        FOREIGN KEY (category_id) REFERENCES categories (id)
);
```

Đây là **DDL minh họa**, không phải script migration hoàn chỉnh để áp dụng cho mọi hệ quản trị DB (chưa có sequences, identity/default ID, indexes theo yêu cầu và versioning). Khi production schema được tạo bởi Flyway/Liquibase, `@Column(unique=true)` hoặc `@ForeignKey` **không tự thực thi migration** lên DB đã tồn tại. Vì vậy, test trên Hibernate-generated H2 schema có thể pass, còn production thiếu constraint và cho dữ liệu sai đi vào.

Quy trình kiểm production-like được khuyến nghị:

1. Dùng Testcontainers hoặc database test riêng **cùng engine/major version** gần production.
2. Chạy **cùng Flyway/Liquibase migration scripts** như deploy, không tạo schema khác chỉ bằng annotations.
3. Dùng `spring.jpa.hibernate.ddl-auto=validate` (hoặc config nhất quán) để phát hiện một số mismatch mapping; **không dựa riêng `validate` để khẳng định mọi UNIQUE/FK tồn tại**, vì schema validation có giới hạn.
4. Chạy test **direct JDBC**: INSERT trùng SKU phải fail; INSERT orphan FK phải fail; DELETE referenced parent theo đúng policy phải fail (hoặc cascade/set-null nếu thiết kế).
5. Kiểm **đúng thời điểm lỗi**: immediate constraints tại SQL statement, deferred constraints tại commit.
6. Với dữ liệu nhiều tenant, test **composite unique** có thể trùng external code ở tenant khác nhưng fail trong cùng tenant.
7. Xác minh exception mapping phía service/API (ví dụ HTTP 409 cho duplicate SKU) ở **test cấp cao hơn**, không gán trách nhiệm status cho JPA slice.

Nếu database dùng constraint deferrable hoặc những SQL đặc thù (partial unique index, case-insensitive uniqueness, `NULLS NOT DISTINCT` ở PostgreSQL), H2 không phải nguồn chứng minh đủ. Cần **database thực** với migration và dữ liệu ranh giới.

## 8. Lỗi ở commit ảnh hưởng thiết kế service và HTTP API

Một phương thức service `@Transactional` có thể trả về từ phần body rồi **Spring transaction interceptor mới cố commit**. Vì vậy đoạn kiểu:

```java
@Transactional
public Product create(Product product) {
    try {
        return repository.save(product);
    } catch (DataIntegrityViolationException ex) {
        // Không chắc bắt được lỗi UNIQUE xuất hiện ở flush/commit sau đó.
        throw ex;
    }
}
```

Đây là snippet minh họa trong service, không độc lập. Nếu SQL chưa chạy khi `save` trả về, catch ở bên trong method sẽ không bắt được lỗi phát sinh sau method tại commit.

Cách thiết kế tốt hơn:

- Đặt database UNIQUE/FK làm **nguồn sự thật cuối cùng**, không thay bằng `existsBySku` rồi mới INSERT (race condition giữa hai request đồng thời).
- Nếu ứng dụng phải trả lỗi nghiệp vụ riêng cho duplicate, hiểu rõ **transaction boundary**, nơi exception translation diễn ra và lúc nào phù hợp để map sang conflict response; ví dụ ở **outer service/controller advice boundary** sau khi transactional method kết thúc.
- Có thể chủ động `saveAndFlush` trong transaction nếu muốn phát hiện **immediate** uniqueness sớm để xử lý, nhưng **không thể ép deferred commit-time constraint phải fail trước COMMIT** chỉ bằng flush.
- Sau violation, **rollback transaction**, không tiếp tục dùng cùng `EntityManager` rồi hy vọng sửa object và commit.
- Với FK, phân biệt hành vi “mất parent” do concurrent deletion, invalid reference và lỗi transient association; trả lỗi domain/HTTP theo contract chứ không lộ raw SQL/message.

### Race condition: `existsBySku` chỉ hỗ trợ UX, không đảm bảo uniqueness

Hai request A/B có thể cùng thấy `existsBySku("SKU-1") == false`, cùng INSERT. Nếu schema **không có UNIQUE**, cả hai có thể commit và dữ liệu bị trùng. Nếu có UNIQUE, database đảm bảo chỉ một kết quả hợp lệ theo isolation/constraint; phía còn lại cần xử lý integrity failure. Muốn chứng minh chuyện này, cần **integration concurrency test với transaction độc lập** và DB tương ứng — unit test giả `existsBySku` không thể chứng minh tính nguyên tử của database.

### Không ánh xạ mọi `DataIntegrityViolationException` thành HTTP 409

`DataIntegrityViolationException` có thể bao gồm **unique, FK, NOT NULL** và các lỗi khác. Nếu API có quy định `409 Conflict` cho duplicate business key, cần nhận diện **đúng constraint/code** một cách có căn cứ. Một FK failure do bug mapping không nên được gộp thành “SKU đã tồn tại” chỉ vì cùng loại exception Spring. Database messages và constraint names có thể khác theo driver/vendor, nên tránh parse string thông báo thiếu ổn định nếu có lựa chọn structured metadata hoặc domain checks phù hợp.

## 9. Bảng đối chiếu lỗi theo từng tầng

| Tình huống | Có thể xảy ra lỗi ở đâu? | Cần test thế nào? |
|---|---|---|
| `Product` có duplicate `sku`, SEQUENCE | Khi pending INSERT được flush, query auto-flush hoặc commit | `@DataJpaTest`, tạo row hợp lệ rồi `saveAndFlush` row trùng |
| Duplicate `sku` nhưng dùng IDENTITY | INSERT có thể diễn ra ngay ở `save/persist` | Assert tại thao tác thực sự thực thi SQL, không cố ép location |
| Duplicate `sku` trong PostgreSQL deferred UNIQUE | Có thể **COMMIT** mới fail | Test DB PostgreSQL thật, transaction commit độc lập |
| Product `category=null` với `optional=false` | Hibernate có thể kiểm nullability trước SQL; DB cũng có NOT NULL | Test mapping và DB NOT NULL riêng; không coi exception ORM là FK SQL |
| Product trỏ `new Category` chưa persist | Hibernate có thể báo transient object error trước DB | Để kiểm FK vật lý, dùng JDBC orphan ID hoặc managed reference có kiểm soát |
| Product có `category_id` không tồn tại | SQL INSERT/UPDATE bị FK từ chối (immediate) | Direct JDBC test trên DB có FK thật |
| Xóa Category còn Product | SQL DELETE parent bị FK từ chối nếu không có cascade/set-null phù hợp | Direct JDBC delete hoặc test repository xóa rồi flush |
| ORM mapping đúng nhưng migration thiếu FK | Không có integrity check ở DB production | Test migrations trên DB giống production, thử invalid SQL |
| `@Transactional` test rollback mà không flush | Constraint có thể chưa bao giờ được kiểm | Flush immediate hoặc commit test đúng khi cần |
| Service catch chỉ quanh `save` | Lỗi nổ ngoài method lúc transaction commit | Test boundary transactional và API error translation |

**Bài học chung:** cần xác định chính xác **who checks, when checks, where the exception emerges**. Cùng một dữ liệu không hợp lệ có thể tạo exception khác nhau tùy cách thực thi, mapping và database.

## 10. Debug thực tế: xem SQL, root cause và transaction state

Khi một test thất bại bất ngờ, thứ tự kiểm tra gợi ý:

1. **Schema:** constraint thật tồn tại không? Tên và cột nào? Có NOT NULL? FK trỏ bảng/cột nào? Có `ON DELETE` rule không?
2. **Data fixture:** parent đã được persist chưa, `id` có tồn tại trong DB chưa, test này có đang dùng transaction khác không?
3. **Timing:** code mới `save` hay đã `flush`? Có `IDENTITY` làm INSERT ngay? Có query auto-flush? Có `DEFERRABLE`?
4. **Exception stack:** Spring `DataIntegrityViolationException`, Hibernate SQL exception hay Bean Validation exception? Có SQLState/vendor code/constraint name không?
5. **Transaction state:** lỗi SQL có đánh dấu rollback-only không? Đã rollback trước khi query tiếp chưa?
6. **Môi trường:** H2 hay PostgreSQL? Schema do Hibernate tự tạo hay migration thật? Test có đang dùng embedded DB khác URL production không?

Với Spring Boot 3.5, có thể bật log SQL **trong test profile khi cần debug**, ví dụ:

```properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Đây là snippet properties **phục vụ debug**, không phải cài đặt production. SQL logs cho biết khi nào statement chạy, nhưng **không tự chứng minh commit thành công**; xem thêm transaction/constraint logs của DB khi kiểm deferred checks. Tránh ghi credentials hoặc dữ liệu nhạy cảm vào bind logs trên môi trường không được kiểm soát.

## 11. Checklist kiểm thử UNIQUE/FK và timing

- [ ] Tôi đã phân biệt **database constraint**, JPA association metadata và Bean Validation.
- [ ] Ràng buộc UNIQUE/FK **thực sự có trong schema test**, không chỉ có annotation.
- [ ] Nếu key cần không null, tôi có cả UNIQUE và NOT NULL theo DB contract.
- [ ] Với composite unique, tôi kiểm cả trường hợp trùng trong cùng scope và hợp lệ khác scope.
- [ ] Tôi biết ID generator là SEQUENCE, IDENTITY hay loại khác, và tác động tới timing INSERT.
- [ ] Tôi không cho rằng `save()` là bằng chứng database đã chấp nhận dữ liệu.
- [ ] Test immediate constraint gọi `saveAndFlush`/`flush` hoặc thực hiện JDBC statement rõ ràng.
- [ ] Nếu test deferred constraint, tôi **cố COMMIT** trên DB hỗ trợ deferral thay vì chỉ flush rồi rollback.
- [ ] Test `@DataJpaTest` không tiếp tục thao tác trong transaction sau expected SQL exception.
- [ ] Tôi dùng `DataIntegrityViolationException` ở Spring data-access boundary và xem root cause nếu cần; không nhầm với Jakarta Validation exception.
- [ ] Tôi đã thử orphan FK bằng SQL thật, không chỉ object graph chưa persist.
- [ ] Tôi đã thử xóa referenced parent và kiểm `ON DELETE` policy đúng.
- [ ] Tôi kiểm database engine/migrations đúng production khi rủi ro là DDL/vendor-specific.
- [ ] Tôi không dựa vào `existsBySku` để thay DB UNIQUE trước race condition.
- [ ] Tôi không bắt mọi lỗi integrity và trả cùng một lỗi nghiệp vụ sai.
- [ ] Nếu API cần HTTP 409/400, tôi có web/integration test cho exception mapping ngoài JPA slice.
- [ ] Tôi chạy được bộ test và hiểu vì sao một test **PASS dù thao tác bên trong ném exception**.

**Kết luận:** **UNIQUE và FOREIGN KEY là ràng buộc database cần có thật trong DDL.** `save` chỉ thay đổi trạng thái persistence; `flush` đồng bộ SQL nhưng không commit; `commit` là ranh giới cuối cùng để DB bảo vệ integrity, đặc biệt với **DEFERRABLE**. Viết test đúng phải tạo dữ liệu vi phạm, ép SQL hoặc commit **ở thời điểm thích hợp**, bắt exception đúng tầng và xác minh database được dùng trong test thực sự tương thích với điều muốn chứng minh.

### Tài liệu chính thức

- [Spring Boot 3.5 — `@DataJpaTest` Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html)
- [Hibernate ORM User Guide — Flushing](https://docs.hibernate.org/stable/orm/userguide/html_single/)
- [Spring Data JPA — Persisting Entities / `save`](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html)
- [Jakarta Persistence — `@UniqueConstraint`, `@JoinColumn`, `@ForeignKey`](https://jakarta.ee/specifications/persistence/)
- [PostgreSQL — CREATE TABLE, `DEFERRABLE` và `INITIALLY DEFERRED`](https://www.postgresql.org/docs/current/sql-createtable.html)
- [Spring Framework — Data Access Exception Hierarchy](https://docs.spring.io/spring-framework/reference/data-access/dao.html)

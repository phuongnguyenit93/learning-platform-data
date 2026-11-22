# @JdbcTest và kiểm thử JdbcTemplate trong Spring Boot

## 1. Mục tiêu: kiểm tra SQL và JDBC thật trong một Spring Test slice

Khi ứng dụng Spring Boot truy cập database trực tiếp qua `JdbcTemplate`, lỗi thường nằm ở **câu SQL, tham số, kiểu dữ liệu, kết quả truy vấn, thứ tự bản ghi, số dòng bị cập nhật và ràng buộc database**. Một unit test dùng Mockito để giả lập `JdbcTemplate` có thể xác nhận rằng DAO gọi một phương thức với SQL nào đó, nhưng **không chứng minh** câu SQL ấy chạy được trên database, cột thật có tồn tại hay `RowMapper` đọc đúng kiểu.

`@JdbcTest` là một **test slice** của Spring Boot dành cho phần **JDBC thuần**. Nó tạo một Spring application context nhỏ tập trung vào `DataSource`, `JdbcTemplate`, JDBC transaction support và các phần khởi tạo database phù hợp. Thông thường, nó sử dụng embedded database cho test và **tự rollback các thay đổi thuộc test transaction** sau mỗi test.

Bài học này giúp bạn:
- Hiểu những bean nào được tự cấu hình và những bean nào **không** được component scan của `@JdbcTest` nạp.
- Viết một DAO thực tế sử dụng `JdbcTemplate.update`, `query`, `queryForObject` và `RowMapper`.
- Kiểm tra insert/read/update/filter/sort, tính đúng của prepared-statement placeholders, khi không tìm thấy record, và constraint violations.
- Phân biệt kết quả JDBC thật với Mockito mock, `@DataJdbcTest` (Spring Data JDBC) và `@DataJpaTest` (JPA/Hibernate).
- Kiểm soát SQL schema/fixtures, test-managed transactions, rollback và datasource replacement.
- Biết khi nào H2 là đủ và khi nào cần PostgreSQL thật bằng Testcontainers.

**Phạm vi phiên bản cho code chạy được:** Java 17+, Spring Boot **3.5.x**, Spring Framework 6.x, Spring JDBC, JUnit Jupiter và H2 2.x. Phần cuối ghi rõ sự thay đổi import/module trong Spring Boot 4.x; không trộn API test của hai major versions.

## 2. @JdbcTest tự cấu hình những gì?

Một khai báo đơn giản:

```java
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;

@JdbcTest
class InventoryJdbcTest {
    // @Autowired JdbcTemplate jdbcTemplate;
}
```

Đây chỉ là khung khai báo, chưa phải file test chạy độc lập. Khi khởi tạo test context, Spring Boot áp dụng slice-specific filtering và các auto-configuration hỗ trợ JDBC.

Sơ đồ khái quát:

```text
JUnit Jupiter
      |
      v
Spring TestContext + @JdbcTest
      |
      +---- DataSource + JDBC driver / connection pool
      +---- JdbcTemplateAutoConfiguration
      |       |
      |       +---- JdbcTemplate
      |       +---- NamedParameterJdbcTemplate (khi phù hợp)
      +---- JdbcClientAutoConfiguration (theo classpath)
      +---- DataSourceTransactionManager / JdbcTransactionManager
      +---- TestDatabaseAutoConfiguration
      +---- SQL initialization / migrations nếu được bật
      |
      +---- KHÔNG mặc định:
               @Service, @RestController,
               custom @Repository/@Component thông thường,
               JPA EntityManager, HibernateJpaAutoConfiguration,
               Spring Data JDBC repository auto-configuration
```

**Lưu ý:** Đây là nhóm hạ tầng mà slice cho phép, không phải lời hứa rằng mọi bean đều xuất hiện vô điều kiện. Classpath, Boot version, datasource configuration, SQL initialization và các `@Import` của test quyết định context cụ thể.

Theo danh sách test slices của Boot 3.5, `@JdbcTest` thường import những auto-configurations liên quan `DataSource`, JDBC template/client, JDBC transaction manager, transaction support, test database, SQL initialization; tùy điều kiện cũng có Flyway/Liquibase và optional Testcontainers service connection. Nó **không tự import JPA repository hoặc Spring Data JDBC repository auto-configurations** như các slice khác.

### 2.1. Bean nào được chọn và bean nào cần import?

| Thành phần | Trong @JdbcTest? | Ý nghĩa |
|---|---|---|
| `DataSource` | Thường có khi database/driver được cấu hình | Cấp JDBC connections thật |
| `JdbcTemplate` | Thường được auto-configure | Query, update, batch JDBC |
| `NamedParameterJdbcTemplate` | Có thể được auto-configure khi điều kiện phù hợp | Sử dụng `:name` thay `?` |
| `JdbcClient` | Có thể được cấu hình trong Boot 3.x/Spring JDBC mới | Fluent JDBC API, không phải JPA |
| `PlatformTransactionManager` | Thường có theo JDBC setup | Transaction và rollback cho test |
| Embedded H2/HSQLDB/Derby | Khi driver có và test replacement chọn dùng | Database thật nhưng chạy trong process |
| `@Repository` viết tay | **Không tự được scan như full app** | Dùng `@Import(InventoryJdbcDao.class)` để test DAO thật |
| `@Service` nghiệp vụ | Không mặc định | Unit/service integration test riêng |
| `JpaRepository`, `EntityManager` | Không phải mục tiêu của slice | Dùng `@DataJpaTest` |
| Spring Data JDBC repositories | Không phải mục tiêu của `@JdbcTest` | Dùng `@DataJdbcTest` |
| HTTP server/Controller | Không mặc định | Dùng MVC/WebFlux/HTTP integration test |

Khi test cần một DAO thủ công như `InventoryJdbcDao`, cách rõ ràng là:

```java
@JdbcTest
@Import(InventoryJdbcDao.class)
class InventoryJdbcDaoTest {
    @Autowired InventoryJdbcDao dao;
}
```

`@Import` ở đây nạp **bean thông thường có chủ đích**, không biến cả ứng dụng thành full integration context. Ngược lại, khi cần bổ sung **một auto-configuration class** vào slice, Spring Boot hướng dẫn dùng `@ImportAutoConfiguration` hoặc cơ chế tương ứng, thay vì tùy tiện dùng `@Import` cho một auto-configuration. Phân biệt rõ hai mục đích này.

## 3. @JdbcTest, @DataJdbcTest, @DataJpaTest, @SpringBootTest khác nhau

| Loại test | Mục tiêu | Những gì được kiểm chứng tốt |
|---|---|---|
| JUnit + Mockito | Code Java độc lập, quyết định gọi dependency | Branching, SQL string được tạo, mapping logic khi tự dựng ResultSet giả |
| `@JdbcTest` | JDBC thuần với DataSource và JdbcTemplate | SQL thật, RowMapper, số dòng update, constraints |
| `@DataJdbcTest` | Spring Data JDBC repositories | Aggregate mapping và Spring Data JDBC repository behavior |
| `@DataJpaTest` | Spring Data JPA/Hibernate | Entity lifecycle, persistence context, JPQL, JPA repositories |
| `@SpringBootTest` | Context rộng hơn (service, repository, config...) | Nhiều tầng đang được nạp thật |
| `@SpringBootTest(RANDOM_PORT)` | HTTP server thực + ứng dụng | Request qua HTTP socket, controllers/filters/service/DB nếu dùng thật |

Một ứng dụng dùng `JdbcTemplate` **không cần JPA**. Vì vậy, nếu muốn kiểm tra `RowMapper` hoặc truy vấn JDBC, `@DataJpaTest` không phải lựa chọn mặc định hợp lý: nó mang Hibernate/JPA vào trong test một cách không cần thiết. Nếu đang dùng Spring Data JDBC aggregate repositories thì `@DataJdbcTest` mới phù hợp, không phải `@JdbcTest`.

**Đừng đánh đồng “JDBC” với “Spring Data JDBC”.** `JdbcTemplate` là API trực tiếp thuộc Spring JDBC; Spring Data JDBC là abstraction repository/aggregate khác hẳn.

## 4. Chuẩn bị một dự án Java 17+ có thể chạy

Ví dụ sử dụng một bảng `inventory_items` để kiểm tra CRUD đơn giản và SQL query thật. Ta cố ý **không dùng JPA/Hibernate** và **không mock JdbcTemplate**.

Hợp đồng cần kiểm tra:

1. `INSERT` một sản phẩm có ID, SKU, tên và số lượng tồn kho.
2. Tìm theo SKU: có sản phẩm thì tạo `Optional<ProductRow>`, không có thì `Optional.empty()`.
3. Liệt kê sản phẩm có quantity thấp hơn hoặc bằng ngưỡng, theo SKU tăng dần.
4. `UPDATE` tồn kho trả đúng số dòng bị cập nhật.
5. SKU phải **unique**, quantity không âm; câu SQL vi phạm được database từ chối.
6. SKU chứa dấu nháy và chuỗi trông như SQL vẫn được bind như **dữ liệu**, không bị chèn vào cấu trúc SQL.
7. `JdbcTemplate.queryForObject` và `query` có hành vi khác nhau khi không có record.
8. Các bản ghi được tạo trong test được **rollback**, không làm ô nhiễm test khác.

### 4.1. Cấu trúc tệp

```text
build.gradle
src/main/java/com/example/jdbcslice/
    JdbcSliceApplication.java
    ProductRow.java
    InventoryJdbcDao.java
    InventoryService.java
src/test/resources/sql/
    inventory-schema.sql
src/test/java/com/example/jdbcslice/
    InventoryJdbcDaoTest.java
```

Đặt test dưới cùng package gốc `com.example.jdbcslice` để Spring Boot tìm được application configuration cho test bootstrap.

### 4.2. build.gradle dùng một phiên bản Boot 3.5.x cụ thể

Tệp `build.gradle` (Gradle Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
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

    testRuntimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot **3.5.8** là một bản phát hành cụ thể của dòng 3.5, giúp ví dụ có tọa độ plugin rõ ràng. Với một dự án có security fixes mới hơn hoặc quy định version khác, thay **đồng bộ theo Boot BOM** thay vì trộn các starter/JUnit/Spring jars từ nhiều major versions.

Nếu dùng Maven, cần `spring-boot-starter-parent` hoặc BOM phù hợp, `spring-boot-starter-jdbc`, `spring-boot-starter-test` và H2 trong test scope; Surefire cần hỗ trợ JUnit Jupiter. Những lệnh `./gradlew`/ `./mvnw` ở mục 6 giả định wrapper tồn tại trong repo; `build.gradle` không tự tạo Gradle wrapper.

**Vì sao H2 là testRuntimeOnly?** `@JdbcTest` cần H2 cho test, nhưng application production không nên tự có H2 trên runtime classpath chỉ vì một bài học. Ở đây ứng dụng mẫu không chạy web server hay tự có datasource production; mục tiêu của nó là chạy **JDBC slice test**.

### 4.3. Application class

Tệp `src/main/java/com/example/jdbcslice/JdbcSliceApplication.java`:

```java
package com.example.jdbcslice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JdbcSliceApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcSliceApplication.class, args);
    }
}
```

Đây là application configuration chuẩn, nhưng khi chạy `@JdbcTest`, Spring Boot **giới hạn auto-configuration theo slice**, không khởi động HTTP server hoặc toàn bộ service. Không chạy `main` để kiểm thử JDBC; hãy chạy đúng class test.

### 4.4. Tạo schema SQL thật

Tệp `src/test/resources/sql/inventory-schema.sql`:

```sql
CREATE TABLE inventory_items (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    title VARCHAR(160) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);
```

Schema này phù hợp với H2 hiện đại và PostgreSQL cho các kiểu/ràng buộc được sử dụng. Trong ví dụ ta **tự cấp ID** để tránh phụ thuộc identity/sequence dialect và tập trung vào `JdbcTemplate`; không dùng `@Entity` hoặc Hibernate DDL.

Câu lệnh `CREATE TABLE` được Spring SQL script initializer chạy **một lần khi application context khởi tạo**, không chạy lại sau mỗi `@Test`. Vì test mặc định rollback, các dòng insert/update của từng test được dọn khi transaction kết thúc. DDL/schema là hạ tầng của context, không thuộc rollback fixture sau mỗi test.

Chúng ta **chỉ định đường dẫn schema tường minh** trong `@JdbcTest(properties=...)`. Nếu không chỉ định, Boot có thể tìm những tên mặc định như `schema.sql`/ `data.sql` ở classpath; việc đặt script vào `sql/inventory-schema.sql` tránh vô tình dùng một `schema.sql` của môi trường khác.

### 4.5. DTO đọc từ JDBC ResultSet

Tệp `src/main/java/com/example/jdbcslice/ProductRow.java`:

```java
package com.example.jdbcslice;

public record ProductRow(
        long id,
        String sku,
        String title,
        int quantity) {
}
```

`ProductRow` là Java 17 record để biểu diễn một row đã được mapping. Nó **không phải `@Entity`**, không có dirty checking/lazy loading. Khi JDBC query trả về dữ liệu, ta đọc từng cột từ `ResultSet` và xây dựng record mới; thay đổi record trong Java **không tự update database**.

### 4.6. DAO thật dùng JdbcTemplate

Tệp `src/main/java/com/example/jdbcslice/InventoryJdbcDao.java`:

```java
package com.example.jdbcslice;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryJdbcDao {

    private static final RowMapper<ProductRow> ROW_MAPPER =
            (rs, rowNum) -> new ProductRow(
                    rs.getLong("id"),
                    rs.getString("sku"),
                    rs.getString("title"),
                    rs.getInt("quantity"));

    private final JdbcTemplate jdbc;

    public InventoryJdbcDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int insert(
            long id, String sku, String title, int quantity) {

        return jdbc.update("""
                INSERT INTO inventory_items (
                    id, sku, title, quantity
                ) VALUES (?, ?, ?, ?)
                """, id, sku, title, quantity);
    }

    public Optional<ProductRow> findBySku(String sku) {
        List<ProductRow> rows = jdbc.query("""
                SELECT id, sku, title, quantity
                  FROM inventory_items
                 WHERE sku = ?
                """, ROW_MAPPER, sku);

        return rows.stream().findFirst();
    }

    public List<ProductRow> findWithQuantityAtMost(
            int maximumQuantity) {

        return jdbc.query("""
                SELECT id, sku, title, quantity
                  FROM inventory_items
                 WHERE quantity <= ?
                 ORDER BY sku ASC
                """, ROW_MAPPER, maximumQuantity);
    }

    public int setQuantity(String sku, int quantity) {
        return jdbc.update("""
                UPDATE inventory_items
                   SET quantity = ?
                 WHERE sku = ?
                """, quantity, sku);
    }

    public int deleteBySku(String sku) {
        return jdbc.update("""
                DELETE FROM inventory_items
                 WHERE sku = ?
                """, sku);
    }

    public long countBySku(String sku) {
        Long count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM inventory_items
                 WHERE sku = ?
                """, Long.class, sku);

        return count == null ? 0L : count;
    }
}
```

**Điểm quan trọng trong đoạn DAO:**

- `JdbcTemplate` thực hiện truy cập JDBC thật qua `DataSource` do Spring cung cấp, không phải Mockito mock.
- `?` là **bind placeholders**. Khi `sku` có dấu nháy, JDBC driver nhận nó dưới dạng **giá trị**, không cắt ghép thành SQL text.
- `jdbc.update(...)` trả về **số dòng được tác động**, không phải ID hoặc entity. Trong demo, một insert/update/delete đúng đối tượng thường trả 1.
- `jdbc.query(..., ROW_MAPPER, sku)` trả một `List<ProductRow>`; không có row sẽ là list rỗng. Bởi vậy `Optional.empty()` là kết quả hợp đồng có chủ đích.
- `ROW_MAPPER` đọc cột bằng tên và dựng Java record. Nếu đổi alias hoặc tên cột SQL, test mapping sẽ báo lỗi; không có JPA provider tự sửa field mapping.
- `countBySku` dùng `queryForObject` vì `COUNT(*)` bình thường trả một row ngay cả khi số lượng bằng 0. Nếu query tìm từng sản phẩm mà **không có row**, `queryForObject` sẽ hành xử khác (mục 7).
- `@Repository` cho phép DAO được Spring nhận diện trong full component scan và áp dụng exception translation khi thích hợp. Nhưng **trong `@JdbcTest`, class này được nạp tường minh bằng `@Import`**, vì slice không tự scan mọi component thường.

### 4.7. Service minh họa để nhận biết ranh giới slice

Tệp `src/main/java/com/example/jdbcslice/InventoryService.java`:

```java
package com.example.jdbcslice;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final InventoryJdbcDao dao;

    public InventoryService(InventoryJdbcDao dao) {
        this.dao = dao;
    }

    public long countSku(String sku) {
        return dao.countBySku(sku);
    }
}
```

Service này **không phải đối tượng đang được test** trong JPA/JDBC slice. Nó tồn tại để cho thấy `@JdbcTest` không tự động nạp `@Service` thông thường. Test chỉ inject `InventoryJdbcDao` sau `@Import`.

## 5. Bộ kiểm thử JDBC đầy đủ với JUnit 5 và H2

Tệp `src/test/java/com/example/jdbcslice/InventoryJdbcDaoTest.java`:

```java
package com.example.jdbcslice;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.List;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest(properties = {
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:sql/inventory-schema.sql"
})
@Import(InventoryJdbcDao.class)
class InventoryJdbcDaoTest {

    @Autowired
    InventoryJdbcDao dao;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    DataSource dataSource;

    @Autowired
    ApplicationContext context;

    @Test
    void usesH2InThisEmbeddedDatabaseSetup() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertEquals(
                    "H2",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void sliceImportsDaoButNotOrdinaryService() {
        assertFalse(context.getBeansOfType(
                InventoryJdbcDao.class).isEmpty());
        assertTrue(context.getBeansOfType(
                InventoryService.class).isEmpty());
    }

    @Test
    void insertsAndMapsRecordFromRealSqlResultSet() {
        assertEquals(
                1, dao.insert(101L, "SKU-A", "Keyboard", 15));

        ProductRow row = dao.findBySku("SKU-A").orElseThrow();

        assertEquals(101L, row.id());
        assertEquals("SKU-A", row.sku());
        assertEquals("Keyboard", row.title());
        assertEquals(15, row.quantity());
        assertEquals(1L, dao.countBySku("SKU-A"));
    }

    @Test
    void missingSkuReturnsEmptyOptionalAndZeroCount() {
        assertTrue(dao.findBySku("NOT-EXIST").isEmpty());
        assertEquals(0L, dao.countBySku("NOT-EXIST"));
    }

    @Test
    void queryWithFilterHasExplicitStableSortOrder() {
        dao.insert(201L, "SKU-C", "C", 3);
        dao.insert(202L, "SKU-A", "A", 1);
        dao.insert(203L, "SKU-B", "B", 10);

        List<String> codes = dao.findWithQuantityAtMost(3)
                .stream()
                .map(ProductRow::sku)
                .toList();

        assertEquals(List.of("SKU-A", "SKU-C"), codes);
    }

    @Test
    void updateAndDeleteReportAffectedRowCount() {
        dao.insert(301L, "SKU-U", "Mouse", 9);

        assertEquals(1, dao.setQuantity("SKU-U", 4));
        assertEquals(
                4, dao.findBySku("SKU-U").orElseThrow().quantity());

        assertEquals(0, dao.setQuantity("MISSING", 5));
        assertEquals(1, dao.deleteBySku("SKU-U"));
        assertEquals(0, dao.deleteBySku("SKU-U"));
        assertTrue(dao.findBySku("SKU-U").isEmpty());
    }

    @Test
    void duplicateSkuIsRejectedByDatabaseConstraint() {
        dao.insert(401L, "SKU-DUP", "First", 5);

        assertThrows(
                DataIntegrityViolationException.class,
                () -> dao.insert(402L, "SKU-DUP", "Second", 7));

        // Không tiếp tục gửi SQL trên transaction đã lỗi:
        // một số database đánh dấu transaction là aborted.
    }

    @Test
    void negativeQuantityIsRejectedByCheckConstraint() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> dao.insert(501L, "SKU-NEG", "Invalid", -1));
    }

    @Test
    void boundSkuIsDataNotSqlCode() {
        dao.insert(601L, "SAFE-1", "Safe", 2);

        String suspicious = "SAFE-1' OR '1'='1";
        assertTrue(dao.findBySku(suspicious).isEmpty());

        assertEquals(1L, dao.countBySku("SAFE-1"));
    }

    @Test
    void queryForObjectRequiresExactlyOneRow() {
        assertThrows(
                EmptyResultDataAccessException.class,
                () -> jdbc.queryForObject("""
                        SELECT title
                          FROM inventory_items
                         WHERE sku = ?
                        """, String.class, "NO-SUCH-SKU"));
    }
}
```

### 5.1. Các ca test chứng minh điều gì?

| Ca test | Bằng chứng | Không tự chứng minh |
|---|---|---|
| `usesH2InThisEmbeddedDatabaseSetup` | DataSource được dùng trong test là H2 thật | Production sử dụng H2 hoặc SQL dialect hoàn toàn tương đương |
| `sliceImportsDaoButNotOrdinaryService` | DAO được import, service thường bị loại khỏi slice | Mọi custom component đều bị loại trong mọi cấu hình |
| `insertsAndMapsRecordFromRealSqlResultSet` | INSERT, SELECT, RowMapper và COUNT trên DB thật | Dữ liệu đã được commit ra transaction khác |
| `missingSkuReturnsEmptyOptionalAndZeroCount` | Query list rỗng được chuyển thành Optional.empty, COUNT trả 0 | `queryForObject` cũng trả null khi không có row |
| `queryWithFilterHasExplicitStableSortOrder` | WHERE quantity và ORDER BY hoạt động với dataset mẫu | Query performance hoặc collation trên mọi database |
| `updateAndDeleteReportAffectedRowCount` | Số dòng affected và row trạng thái sau update/delete | Nhiều transaction đồng thời không có race |
| `duplicateSkuIsRejectedByDatabaseConstraint` | Constraint UNIQUE có hiệu lực ở H2 | Constraint được migrate đúng trong PostgreSQL production |
| `negativeQuantityIsRejectedByCheckConstraint` | CHECK quantity >= 0 từ chối input | Bean Validation ở HTTP layer đã được cấu hình |
| `boundSkuIsDataNotSqlCode` | Placeholder không biến input đáng ngờ thành mệnh đề OR | Toàn bộ query trong ứng dụng đều an toàn nếu chỗ khác có string concatenation |
| `queryForObjectRequiresExactlyOneRow` | Query không có row gây exception đúng loại trong setup này | Một query COUNT(*) cũng ném exception khi count bằng 0 |

**Lưu ý tính runnable:** các tệp `Application`, record, DAO, service, SQL script, Gradle và JUnit class đều được cung cấp. Với Java 17+, Boot 3.5.8 và dependencies đúng, đây là bộ test được **thiết kế để biên dịch và kiểm tra 10 tình huống**. Không tuyên bố đã chạy trên môi trường của bạn nếu chưa chạy đúng build, runner và database tại đó.

Với H2, vi phạm UNIQUE/CHECK được Spring JDBC exception translation đưa về nhánh `DataIntegrityViolationException` phù hợp. Thời điểm và subtype exception có thể khác trên driver/database khác: ví dụ PostgreSQL sau một statement lỗi có thể đánh dấu transaction aborted; hãy tách ca constraint lỗi ra test riêng, không cố tiếp tục query trong cùng transaction.

## 6. Chạy lớp test và đọc kết quả thật

Trong project đã có Gradle wrapper, ở Linux/macOS:

```bash
./gradlew test --tests "com.example.jdbcslice.InventoryJdbcDaoTest"
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.jdbcslice.InventoryJdbcDaoTest"
```

Nếu project dùng Maven wrapper và tương đương Spring Boot BOM/dependencies:

```bash
./mvnw -Dtest=InventoryJdbcDaoTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=InventoryJdbcDaoTest test
```

Khi test thực thi, xem báo cáo Gradle ở `build/reports/tests/test/index.html` hoặc Maven Surefire ở `target/surefire-reports/` (của **đúng module**). Đảm bảo **10 test methods thực sự được discover và chạy**, không bị `SKIPPED`, `NO-SOURCE` hoặc chỉ thấy kết quả cache `UP-TO-DATE`. Các test không có `System.out.println`, nên không bịa một stdout cố định.

**Một điểm vận hành:** ví dụ chỉ đặt H2 ở `testRuntimeOnly`. Nếu bạn chạy `JdbcSliceApplication.main` như production mà không cung cấp datasource/driver runtime, ứng dụng có thể không khởi động do thiếu datasource. Điều đó **không** làm test sai: mục tiêu minh họa là `@JdbcTest`, không phải sản phẩm server đầy đủ. Với ứng dụng thật, phải cấu hình datasource production rõ ràng.

## 7. Cách dùng JdbcTemplate: update, query, queryForObject, batchUpdate

### 7.1. update trả số dòng, không trả entity

`JdbcTemplate.update(String sql, Object... args)` trả một số nguyên biểu thị row count từ JDBC. Ví dụ:

```java
int updated = jdbc.update("""
        UPDATE inventory_items
           SET quantity = ?
         WHERE sku = ?
        """, 8, "SKU-A");
```

Đoạn trên là minh họa trong một class/test đã có `jdbc`, không phải file Java độc lập. Nó có thể trả:
- `1`: một row được cập nhật.
- `0`: không có row phù hợp.
- Giá trị khác nếu điều kiện chạm nhiều row và SQL/DB cho phép.

Đừng bỏ qua row count nếu nghiệp vụ kỳ vọng “chỉ một đơn hàng/sản phẩm được cập nhật”. `0` có thể có nghĩa ID không tồn tại hoặc điều kiện optimistic update không khớp; một update nhiều row có thể là bug nghiêm trọng.

Nếu cần generated ID, có thể dùng `PreparedStatement` khai báo `RETURN_GENERATED_KEYS` và `KeyHolder` (hoặc `SimpleJdbcInsert`), nhưng cú pháp/trả về keys phụ thuộc driver/dialect. Bài demo dùng explicit `id` để tập trung vào contract của `JdbcTemplate`.

### 7.2. query dùng RowMapper và thường trả List

`jdbc.query(sql, rowMapper, args...)` chạy SELECT và chuyển mỗi row thành Java object. Ví dụ:

```java
List<ProductRow> rows = jdbc.query("""
        SELECT id, sku, title, quantity
          FROM inventory_items
         WHERE quantity <= ?
         ORDER BY sku
        """,
        (rs, rowNum) -> new ProductRow(
                rs.getLong("id"),
                rs.getString("sku"),
                rs.getString("title"),
                rs.getInt("quantity")),
        5);
```

Đây là đoạn minh họa trong scope có `JdbcTemplate jdbc`, `ProductRow` đã định nghĩa. Nếu không có row, `query` trả list rỗng; **không tự ném `EmptyResultDataAccessException`**.

**RowMapper cần lưu ý:**
- `ResultSet.getInt(...)` trả `0` khi SQL NULL; sau đó dùng `ResultSet.wasNull()` để phân biệt NULL nếu cột nullable. Với demo `quantity NOT NULL`, `int` là lựa chọn có chủ đích.
- Dùng cột/alias chính xác. Nếu SQL trả `available_quantity AS quantity` thì RowMapper có thể đọc `quantity`; nếu không alias, tên cột sẽ khác.
- `BeanPropertyRowMapper` hỗ trợ mapping JavaBean theo convention; nó không phải lời hứa auto-map Java record của mọi phiên bản. `DataClassRowMapper` hỗ trợ các class/record có constructor phù hợp, nhưng vẫn nên test ánh xạ thực.
- `RowMapper` nên tập trung ánh xạ một row; không gửi network I/O hoặc mở transaction mới từ callback.

### 7.3. queryForObject không có nghĩa “trả null khi không tìm thấy”

`queryForObject` dành cho query **mong đợi đúng một row**. Trong Spring JDBC, nếu 0 row hoặc nhiều hơn 1 row xuất hiện, nó có thể phát `EmptyResultDataAccessException` hoặc `IncorrectResultSizeDataAccessException`. Nếu một row duy nhất có SQL value NULL, mapped result có thể null theo kiểu/mapper đã chọn, **khác với tình huống không có row**.

Đối chiếu:

```sql
SELECT title FROM inventory_items WHERE sku = 'MISSING';
-- 0 row: queryForObject không trả một Optional.empty tự động.

SELECT COUNT(*) FROM inventory_items WHERE sku = 'MISSING';
-- 1 row có giá trị 0: queryForObject(Long.class) có thể trả 0.
```

Nếu nghiệp vụ cần `Optional` khi 0 row, có thể dùng `query(..., rowMapper, args)` và `stream().findFirst()` như DAO ở mục 4, hoặc bắt riêng `EmptyResultDataAccessException` có cân nhắc. **Đừng catch mọi `DataAccessException` rồi trả empty**: lỗi connection, syntax, constraint hoặc timeout khi đó sẽ bị che thành “không tìm thấy”.

### 7.4. batchUpdate giúp gửi nhiều câu lệnh nhưng không thay transaction policy

Ví dụ minh họa:

```java
List<Object[]> batchArgs = List.of(
        new Object[] {701L, "SKU-X", "X", 1},
        new Object[] {702L, "SKU-Y", "Y", 2});

int[] counts = jdbc.batchUpdate("""
        INSERT INTO inventory_items (id, sku, title, quantity)
        VALUES (?, ?, ?, ?)
        """, batchArgs);
```

Đoạn trên cần `java.util.List`, `JdbcTemplate jdbc` và bảng demo. Với JDBC drivers, phần tử mảng update counts có thể chứa hằng số JDBC đặc biệt như `Statement.SUCCESS_NO_INFO` chứ không luôn bằng `1`. Kiểm tra số mục gửi, kết quả/SQL exception và transaction boundary đúng nghiệp vụ. `batchUpdate` **không tự đảm bảo atomicity** nếu chạy ngoài transaction hoặc driver/DB không có semantics như kỳ vọng.

### 7.5. NamedParameterJdbcTemplate và JdbcClient

Trong những truy vấn có nhiều tham số, `NamedParameterJdbcTemplate` thường dễ đọc hơn:

```java
int affected = named.update("""
        UPDATE inventory_items
           SET quantity = :quantity
         WHERE sku = :sku
        """,
        Map.of("quantity", 4, "sku", "SKU-A"));
```

Đây là đoạn minh họa có biến `NamedParameterJdbcTemplate named` và `import java.util.Map` trong scope. Spring chuyển named parameters thành JDBC binds thích hợp; nó vẫn dựa trên JDBC, không phải JPA/Hibernate.

`JdbcClient` là fluent facade được giới thiệu trong Spring Framework 6.1+ cho nhiều thao tác SQL. Nó có thể được Boot auto-configure trong `@JdbcTest` khi phù hợp. Tuy nhiên, không cần chuyển một bài `JdbcTemplate` sang `JdbcClient` chỉ vì API mới: hai cách nên được test theo cùng các nguyên tắc về bind parameters, mapping, affected rows và database dialect.

## 8. Transaction và rollback: điều gì thực sự bị dọn?

`@JdbcTest` mặc định transactional và Spring TestContext **rollback cuối mỗi test**. Khi `InventoryJdbcDaoTest` chèn `SKU-A` rồi assert dữ liệu, các câu `INSERT`/`SELECT` thường thực hiện trong **cùng test-managed transaction T1**.

```text
JUnit test method (thread hiện tại)
      |
      +-- T1 bắt đầu bởi Spring TestContext
      |       |
      |       +-- dao.insert(...)       -> SQL INSERT
      |       +-- dao.findBySku(...)    -> SELECT trong T1
      |       +-- assertions
      |
      +-- Spring TestContext rollback T1
      |
      v
Bản ghi chưa commit không còn sau khi kết thúc test
```

### 8.1. Query thấy row không có nghĩa row đã commit

Vì test được bảo vệ bởi T1, `jdbc.queryForObject("select count(*) ...")` **có thể nhìn thấy thay đổi chưa commit của chính T1**. Một test xanh sau `dao.insert` không chứng minh một kết nối database/HTTP request khác nhìn thấy row đó trước khi commit.

Muốn kiểm chứng đúng nghĩa **commit/rollback hoặc isolation**:
- Kiểm soát transaction boundary rõ ràng bằng Spring transaction testing support.
- Có thể dùng `TestTransaction` để kết thúc transaction của test một cách chủ động khi TestContext đang quản lý T1.
- Khi muốn kiểm chứng dữ liệu đã commit, đọc ở transaction/connection độc lập **sau khi commit**.
- Dọn dữ liệu đã commit bằng transaction riêng hoặc database test lifecycle phù hợp; không dùng database production.

### 8.2. Bật/tắt rollback

`@Rollback(false)` hoặc `@Commit` có thể đổi chính sách kết thúc **test-managed transaction**, nhưng có nguy cơ để lại dữ liệu. Nếu không muốn test-managed transaction:

```java
@JdbcTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NonTransactionalJdbcTest {
    // Cần tự dọn thay đổi đã commit.
}
```

Đây là **mẫu annotation**, cần imports `JdbcTest`, `Transactional`, `Propagation`, không phải lớp test hoàn chỉnh. Trong setup này, code thường thực hiện các SQL operations theo auto-commit hoặc transaction programmatic của chính nó, nên rollback mặc định của test **không còn bảo vệ dữ liệu**.

**Không lẫn transaction trên test thread với transaction do HTTP server mở:** khi test qua `@SpringBootTest(RANDOM_PORT)` và một HTTP client thật, server xử lý request trong luồng khác; `@Transactional` của test **không tự rollback** những transaction server đã commit.

### 8.3. Timeout, @BeforeEach và transaction context

Spring TestContext thường thực thi `@BeforeEach` và `@AfterEach` trong test-managed transaction nếu nó đang active; `@BeforeTransaction`/`@AfterTransaction` chạy ngoài transaction đó. Vì vậy, một thao tác cleanup ở `@AfterEach` cũng có thể bị rollback; nếu dữ liệu được commit ở transaction khác, dọn bằng `@AfterTransaction` hoặc cơ chế rõ ràng.

**Preemptive timeout** như `assertTimeoutPreemptively` có thể chạy code trong thread khác và **làm mất transaction thread-bound của test**, khiến SQL commit ngoài ý định. Đây là lý do không mặc định mọi thay đổi trong test `@JdbcTest` sẽ được rollback nếu code chuyển sang thread khác hoặc lập transaction mới.

## 9. Test database replacement: H2 hay PostgreSQL thật?

Khi H2 có trên classpath, `@JdbcTest` thường có thể tạo embedded database. Theo cấu hình test database trong Boot, một datasource được xác định là **test connection** có thể được giữ lại khi sử dụng chế độ replace phù hợp; không nên khẳng định mọi datasource đều bị thay trong mọi version/case.

Nếu mục tiêu là kiểm tra SQL syntax hoặc constraint **đặc thù PostgreSQL**, dùng PostgreSQL test database và ngăn test database auto-config tự thay nó bằng H2.

### 9.1. Dùng @AutoConfigureTestDatabase(replace = NONE)

Trong Boot 3.5:

```java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;

@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
```

Đây là annotation minh họa đặt trên test class. **`Replace.NONE` không tự tạo database**: nó chỉ yêu cầu không thay datasource được cung cấp; bạn phải bảo đảm URL/driver/credentials trỏ tới **database test**, không phải production.

Các mode khác có thể gồm `ANY`, `AUTO_CONFIGURED` và `NON_TEST`; `NON_TEST` của Boot 3.5 không thay những datasource được Boot nhận diện là test DB, chẳng hạn một số service connections/Testcontainers hoặc URL test khai báo qua `@DynamicPropertySource`. Chọn theo **dòng phiên bản và cách kết nối thật**, không chỉ sao chép giá trị từ bài khác.

### 9.2. Độ khác biệt H2 và PostgreSQL

H2 thường tốt để test nhanh SQL phổ thông:
- Query cơ bản, placeholders, mappings.
- `UNIQUE`, `NOT NULL`, `CHECK` và CRUD đơn giản.
- `JdbcTemplate` exception translation trong một driver cụ thể.

Nhưng H2 **không bảo đảm** giống PostgreSQL về:
- `ON CONFLICT`, `RETURNING`, `ILIKE`, JSONB, arrays, indexes.
- Transaction isolation, locking, concurrent writes và deadlocks.
- Unicode collation, case sensitivity, ordering.
- Date/timezone, decimal rounding, generated keys và schema default.
- Flyway/Liquibase migrations dùng cú pháp database-specific.
- Exception vendor codes và thời điểm constraint failure.

Do đó nên giữ test nhanh với H2 cho phần lớn CRUD đơn giản, rồi bổ sung test production-like database cho query/ràng buộc quan trọng.

## 10. Ví dụ Testcontainers PostgreSQL cho JDBC slice

Phần này là **một lớp test bổ sung**, không thay thế 10 ca H2 ở mục 5. Nó dùng DAO `InventoryJdbcDao`, `ProductRow` và SQL script từ ví dụ đã có.

### 10.1. Dependency bổ sung

Trong `build.gradle` Boot 3.5.8, bổ sung:

```groovy
dependencies {
    testRuntimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

Đây là fragment bổ sung, không phải toàn bộ build. Testcontainers cần container runtime (thường Docker hoặc tương đương được hỗ trợ). Không cố chạy test này trên môi trường không có container runtime rồi coi đó là lỗi của `JdbcTemplate`.

### 10.2. Test class hoàn chỉnh

Tệp `src/test/java/com/example/jdbcslice/InventoryPostgresJdbcTest.java`:

```java
package com.example.jdbcslice;

import java.sql.Connection;
import java.sql.SQLException;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
@JdbcTest(properties = {
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:sql/inventory-schema.sql"
})
@Import(InventoryJdbcDao.class)
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class InventoryPostgresJdbcTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("inventory_test")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void postgresProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    InventoryJdbcDao dao;

    @Autowired
    DataSource dataSource;

    @Test
    void usesPostgresRatherThanEmbeddedH2() throws SQLException {
        try (Connection c = dataSource.getConnection()) {
            assertEquals(
                    "PostgreSQL",
                    c.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void writesAndReadsThroughRealPostgres() {
        assertEquals(
                1, dao.insert(901L, "PG-A", "Postgres Test", 6));
        assertEquals(
                6, dao.findBySku("PG-A").orElseThrow().quantity());
    }
}
```

**Giải thích kết nối:**
- `@Container` + `@Testcontainers` quản lý PostgreSQL container theo JUnit Jupiter extension.
- `@DynamicPropertySource` đăng ký **suppliers** để Spring đọc JDBC URL, username và password lúc cấu hình datasource; JDBC URL chứa host và mapped port của container, không hard-code `localhost:5432`.
- `@AutoConfigureTestDatabase(replace=NONE)` ngăn `@JdbcTest` thay datasource PostgreSQL bằng H2.
- `spring.sql.init.mode=always` bật script SQL initialization ngay cả khi datasource **không** phải embedded.
- `schema-locations` sử dụng SQL script chung của ví dụ; DDL được thiết kế dùng những tính năng tương thích H2/PostgreSQL.
- Mỗi test vẫn thường có **test-managed transaction và rollback**, dù database server là PostgreSQL thật.

**Lưu ý lifecycle:** nếu application context cache còn giữ datasource sau khi class-level container đã dừng, test class khác có thể gặp JDBC URL/port không còn sống. Khi tái sử dụng resource giữa nhiều test, chọn container lifetime/cache scope phù hợp và không dựa vào một port cũ. Với một lớp test cô lập như ví dụ, static container lifecycle theo lớp giúp tình huống dễ quản lý.

Trong dự án Boot đã dùng `@ServiceConnection` và module `spring-boot-testcontainers`, có thể dùng cơ chế service connection thay cho `@DynamicPropertySource` khi phù hợp. Không khai báo nhiều nguồn cạnh tranh cho cùng properties mà không hiểu precedence.

## 11. schema.sql, data.sql, @Sql và migrations có phải cùng một thứ?

**Không.** Ba cách quản lý schema/fixtures phục vụ mục tiêu khác nhau.

| Cơ chế | Khi nào thực thi? | Mục đích |
|---|---|---|
| Boot `spring.sql.init.schema-locations` | Khi DataSource context được initialize | Tạo bảng/schema cho test context |
| Boot `spring.sql.init.data-locations` | Khi SQL initialization chạy | Seed dữ liệu mặc định, cần chú ý state giữa tests |
| Spring Test `@Sql` | Theo `BEFORE_TEST_METHOD`/`AFTER_TEST_METHOD` đã chỉ định | Fixture cụ thể cho một class/method |
| Flyway/Liquibase | Khi migration auto-config được nạp và bật | Chạy/kiểm tra versioned schema migration |
| DAO setup bằng `jdbc.update` | Trong `@BeforeEach` hoặc test body | Dữ liệu gắn rõ với ca test |
| Testcontainers | Khi container lifecycle bắt đầu | Cấp database server, **không tự tạo schema** |

Trong ví dụ, ta chỉ dùng **một SQL schema initializer** rồi insert fixture ngay trong mỗi test. Nhờ đó, test không cần chia sẻ `data.sql` hoặc phụ thuộc thứ tự chạy.

Nếu project production dùng Flyway/Liquibase, thường nên để **migration là nguồn duy nhất tạo schema** trong test tích hợp liên quan và không đồng thời bật một `schema.sql` khác tạo cùng bảng. Hãy kiểm tra rằng JPA/JDBC test slice đã nạp migration auto-config thực tế, datasource đã đúng và scripts có thể chạy trên database mục tiêu.

### 11.1. @Sql fixture mẫu

Ví dụ annotation trong một `@JdbcTest` có file SQL fixture thực:

```java
@Sql(
        scripts = "/sql/inventory-fixture.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Test
void readsKnownFixture() {
    // Assertions trên dữ liệu fixture.
}
```

Đây là minh họa, cần imports `@Sql`, `Sql.ExecutionPhase` và một script `src/test/resources/sql/inventory-fixture.sql`. Với test-managed transaction mặc định, `@Sql` trong cùng transaction có thể rollback cuối test. Với `@SqlConfig(transactionMode=ISOLATED)`, script chạy trong transaction riêng; nếu đã commit thì không tự rollback theo transaction của method — cần cleanup đúng.

**Không trông chờ “schema.sql có sẵn” nếu file thật nằm ở package/path khác.** Dùng `spring.sql.init.schema-locations` để khai báo chính xác, và khi file bị thiếu có thể dùng location không có `optional:` để fail-fast thay vì âm thầm tạo context không có bảng.

## 12. An toàn truy vấn SQL và số dòng cập nhật

### 12.1. Prepared placeholders ngăn việc input trở thành cú pháp SQL

Nếu người dùng truyền `"A' OR '1'='1"` cho SKU, sử dụng:

```java
jdbc.query(
        "SELECT sku FROM inventory_items WHERE sku = ?",
        (rs, rowNum) -> rs.getString("sku"),
        inputSku);
```

Bộ tham số được bind qua JDBC, không tạo một mệnh đề OR mới. Nhưng **SQL injection vẫn có thể xảy ra ở vị trí không bind được**, ví dụ nối tên bảng, tên cột hoặc `ORDER BY` từ input không được whitelist:

```java
// CỐ Ý SAI: không nối tên cột do client tự chọn vào SQL.
String sql = "SELECT * FROM inventory_items ORDER BY " + userSort;
```

`userSort` ở đây là biến minh họa, không có trong chương trình mẫu. Nếu cần sort tùy chọn, ánh xạ input vào một **allowlist** như `sku`, `title`, `quantity`; có thể bind giá trị điều kiện nhưng không bind một identifier SQL bằng placeholder thông thường.

**Không coi một test với chuỗi đáng ngờ là chứng chỉ bảo mật cho toàn ứng dụng.** Nó chỉ chứng minh đường query được test không diễn giải input đó thành mệnh đề SQL.

### 12.2. Check row counts và optimistic update

Ví dụ khi chỉ muốn trừ hàng tồn kho nếu đủ số lượng:

```java
int changed = jdbc.update("""
        UPDATE inventory_items
           SET quantity = quantity - ?
         WHERE sku = ?
           AND quantity >= ?
        """,
        requested, sku, requested);
```

Nếu `changed == 1`, một row phù hợp đã bị trừ quantity. Nếu `changed == 0`, có thể SKU không tồn tại **hoặc** không đủ hàng. Không thể kết luận một trong hai từ row count đơn lẻ; cần contract và query bổ sung nếu API phải phân biệt 404 với 409.

Đây là đoạn minh họa trong method có `requested`, `sku` và `jdbc`. Nó thể hiện một kỹ thuật có ích hơn đọc quantity rồi update không điều kiện: câu SQL update có điều kiện làm giảm một số race giữa hai requests. **Nhưng** để chứng minh tính đúng dưới concurrent load/locking/isolation, cần integration test với database thật và các transaction chạy đồng thời, không chỉ một `@JdbcTest` tuần tự trên H2.

## 13. Lỗi thường gặp khi viết @JdbcTest

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `No qualifying bean of type InventoryJdbcDao` | DAO `@Repository` thường không được quét trong slice | `@Import(InventoryJdbcDao.class)` |
| `NoSuchBeanDefinitionException` cho service | Service không thuộc JDBC slice | Test DAO trực tiếp; service test dùng context phù hợp |
| `Failed to configure a DataSource` | Thiếu embedded driver/JDBC URL/credentials | Check testRuntimeOnly H2 hoặc test datasource thật |
| `Table INVENTORY_ITEMS not found` | Schema script không được nạp, sai location hoặc DB schema | Kiểm tra `spring.sql.init.schema-locations`, mode, log |
| Test H2 xanh nhưng PostgreSQL fail | Dialect, collation, data types, migration khác | Thêm Testcontainers PostgreSQL |
| SQL trả map sai field | RowMapper dùng tên cột/alias không đúng | Assert từng record component từ query thật |
| `queryForObject` ném exception khi không có row | API yêu cầu exactly one row | Dùng `query` + Optional theo hợp đồng |
| `COUNT(*)` trả 0 bị nhầm thành không có row | COUNT vẫn trả một row | Assert count value, không catch EmptyResult |
| UPDATE test xanh dù SKU không tồn tại | Bỏ qua affected row count | Assert `jdbc.update(...)` trả 1/0 |
| SQL constraint không phát hiện trong unit test mock | Không chạy SQL thật | Dùng `@JdbcTest` + schema có constraint |
| Truy vấn cắt ghép input trực tiếp | SQL injection | Sử dụng placeholders/named parameters; allowlist identifiers |
| Test có `@Transactional` nhưng thấy row vừa ghi | Cùng transaction đọc được uncommitted changes của nó | Đừng đồng nhất đọc được với commit |
| Test không rollback dữ liệu sau async/preemptive timeout | SQL chạy khác thread/transaction | Kiểm soát thread và TestTransaction/cleanup |
| Test không bắt exception đúng subtype trên DB khác | Driver/exceptions translation khác H2 | Assert loại exception ổn định theo contract và database |
| Test chậm do full app startup | Dùng `@SpringBootTest` dù chỉ cần JDBC | Giới hạn bằng `@JdbcTest`, import đúng DAO |
| Schema được tạo hai lần | Dùng `schema.sql` và migration cùng tạo bảng | Chọn một schema owner |
| Test chạy riêng xanh nhưng suite fail | DB share, fixture ID trùng, context cache hoặc commit leaked | Dùng rollback/unique fixtures/isolated database |
| Boot 4 không resolve `org.springframework.boot.test.autoconfigure.jdbc.JdbcTest` | Package/module chuyển từ Boot 3 | Đổi sang Boot 4 test module/import phù hợp |

**Đọc root cause** trong chuỗi `Caused by` khi application context không khởi động. Nếu SQLException nêu tên bảng/cột, hãy kiểm tra schema/SQL thật; không chữa bằng cách mock JdbcTemplate vì như vậy bạn vừa bỏ cơ chế đang cần kiểm chứng.

## 14. Dòng phiên bản: Spring Boot 3.5 so với Spring Boot 4.x

Mã ở các mục 4–10 dùng **Spring Boot 3.5.x**, nơi `@JdbcTest` được import:

```java
org.springframework.boot.test.autoconfigure.jdbc.JdbcTest
org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase
```

Đây là danh sách package để đối chiếu, không phải một file Java độc lập.

Trong Spring Boot **4.x**, test slices được chia module. `@JdbcTest` tương ứng nằm ở:

```java
org.springframework.boot.jdbc.test.autoconfigure.JdbcTest
org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase
```

Module cần có là **`spring-boot-jdbc-test`** và phần test starter/dependencies phù hợp với Boot BOM. Đừng cố thêm JAR của Boot 4 vào một runtime Boot 3.5 để sửa import; làm vậy có thể phá dependency alignment của Spring Framework.

Những nguyên tắc vẫn giống nhau:
- `@JdbcTest` dành cho JDBC + DataSource + templates, không phải JPA/Hibernate.
- Ordinary service/DAO `@Repository` viết tay không được mặc định tự scan, nên import bean cần test.
- Transaction rollback của test không thay thế cleanup cho transaction bên ngoài.
- H2 không chứng minh SQL dialect production; nên thêm Testcontainers khi độ tin cậy phụ thuộc PostgreSQL/MySQL thực.
- Migrations và test database replacement cần kiểm soát theo **phiên bản đang chạy**.

Khi nâng Boot, hãy kiểm tra đúng import `JdbcTest`, `AutoConfigureTestDatabase`, test dependencies, schema initialization properties và report integration test. Nếu dự án đã ở Boot 4, dùng **tài liệu Boot 4** thay vì copy mọi import Boot 3 trong bài này.

## 15. Checklist trước khi báo JDBC integration test đạt

- [ ] Đã xác định đúng mục tiêu **JdbcTemplate/SQL/JDBC DataSource**, không nhầm với Spring Data JDBC/JPA.
- [ ] `@JdbcTest` đúng package/module Boot version, context chỉ nạp các thành phần JDBC cần thiết.
- [ ] DAO thật được `@Import` nếu không tự được slice scan; `JdbcTemplate` không bị mock.
- [ ] Đã kiểm tra `DataSource` thật sự trỏ tới embedded H2 hay database test mong muốn.
- [ ] Schema SQL được tạo từ **một cơ chế rõ ràng** (script initializer hoặc migration), không xung đột.
- [ ] Test `INSERT`, `SELECT`, `UPDATE`, `DELETE`, row counts và RowMapper trên SQL thật.
- [ ] Query có placeholders/named parameters, không nối dữ liệu người dùng trực tiếp vào SQL.
- [ ] Khi kết quả không có row, đã phân biệt `query` (list rỗng) và `queryForObject` (error expected).
- [ ] Dữ liệu đại diện gồm điều kiện lọc, sorting, missing key và ràng buộc UNIQUE/CHECK/NOT NULL.
- [ ] Đã hiểu test-managed rollback; không coi row thấy trong cùng transaction là bằng chứng commit.
- [ ] Không tiếp tục query trên transaction đã SQL error trong DB có transaction-aborted semantics.
- [ ] Nếu câu SQL phụ thuộc dialect/locking, có bài test trên PostgreSQL/MySQL hoặc database gần production.
- [ ] Đã kiểm soát `@AutoConfigureTestDatabase`, `@DynamicPropertySource` và container lifecycle khi dùng Testcontainers.
- [ ] Đã chạy đúng JUnit test class trong đúng module và xem report để chắc chắn test được thực thi, không bị skip.
- [ ] Không tuyên bố HTTP/service transaction/security đúng chỉ từ một `@JdbcTest`.

## 16. Tài liệu chính thức

- [Spring Boot 3.5 – Auto-configured JDBC Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): phạm vi `@JdbcTest`, embedded database, `JdbcTemplate` và rollback.
- [Spring Boot 3.5 – Test Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): auto-configurations được đưa vào `@JdbcTest`.
- [Spring Boot – Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html): `schema.sql`, `data.sql`, init mode, migration.
- [Spring Framework – JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, query, update và mapping.
- [Spring Framework – Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback, `@BeforeTransaction`/`@AfterTransaction`, preemptive timeout.
- [Spring Boot 4 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@JdbcTest` từ module `spring-boot-jdbc-test` và namespace mới.

**Kết luận:** `@JdbcTest` cho phép kiểm thử **JdbcTemplate và SQL trên database thật trong một Spring slice nhỏ**. Test đáng tin cậy phải dùng DAO thực, dữ liệu/schema phù hợp, assertion trên row mapping và affected row counts, hiểu đúng việc rollback chỉ áp dụng cho **test-managed transaction**, và kiểm soát database replacement. H2 giúp phát hiện nhanh nhiều lỗi SQL phổ biến; khi query, constraint hoặc concurrency phụ thuộc PostgreSQL/MySQL, hãy bổ sung Testcontainers với database gần production.
# JDBC và dữ liệu SQL: Kiểm thử stored procedure hoặc tính năng riêng của database khi có sử dụng

## 1. Khi nào bài kiểm thử cần database thật?

Một ứng dụng Spring Boot thường có các truy vấn SQL thông thường: `SELECT`, `INSERT`, `UPDATE`, `DELETE`. Nhưng một số hệ thống còn dùng **stored procedure**, **database function**, kiểu `JSONB`, UPSERT, `RETURNING`, trigger, sequence, locking, window function hoặc tính năng theo từng SQL dialect. Trong trường hợp đó, **H2 hoặc một repository mock không thể chứng minh code sẽ hoạt động đúng trên PostgreSQL, SQL Server, Oracle hay MySQL**.

Ví dụ: application gửi lệnh đặt trước hàng tồn kho, yêu cầu database giảm stock **một cách nguyên tử** và trả lại số lượng còn lại. Một unit test chỉ stub:

~~~java
when(gateway.reserve("SKU-101", 3)).thenReturn(4);
~~~

chỉ chứng minh mock trả `4`, **không** chứng minh:

- Tên procedure, số lượng/thứ tự/type tham số đúng.
- Spring JDBC và JDBC driver thực thi `CALL` đúng.
- Procedure cập nhật row theo điều kiện và trả đúng output.
- Khi thiếu hàng hoặc số lượng sai, transaction bị rollback và SQLSTATE đúng.
- Hai giao dịch đồng thời không làm tồn kho âm.
- `JSONB`, `ON CONFLICT`, `RETURNING` có cú pháp và semantics giống database production.

**Quy tắc chọn bài test:** khi implementation phụ thuộc database-specific SQL, ít nhất một tầng integration test phải chạy trên **đúng engine** và phiên bản đủ gần production. Còn business rules độc lập SQL vẫn nên được kiểm nhanh bằng unit test.

### Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt stored **procedure** và **function**; `CALL` với `SELECT` và tham số `IN`/`OUT`/`INOUT`.
2. Chọn `JdbcTemplate`, `SimpleJdbcCall`, `CallableStatement`, `@JdbcTest` và `@DataJdbcTest` đúng mục đích.
3. Kết nối PostgreSQL thực bằng Testcontainers và `@ServiceConnection`, tránh Spring tự thay datasource thành H2.
4. Viết dữ liệu đầu vào có thể lặp lại, gọi code data-access production, assert **output lẫn side effects**.
5. Test `JSONB`, `INSERT ... ON CONFLICT ... RETURNING`, ràng buộc unique và SQLSTATE.
6. Hiểu mặc định transaction rollback của JDBC slice và tình trạng **transaction aborted** của PostgreSQL sau lỗi SQL.
7. Thiết kế thêm test concurrency, migrations, permissions, timeout và khóa mà không giả định một test đơn luồng đã chứng minh tất cả.
8. Phân biệt code chạy thật, ví dụ minh họa không độc lập và kết quả dự kiến khi chạy bằng Gradle.

## 2. Phạm vi: không cần procedure thì không nên tự thêm procedure

Stored procedure hữu ích khi nhiều thao tác gần dữ liệu cần được thực hiện bằng một lệnh DB, có logic dùng chung giữa nhiều hệ thống, hoặc DB cần tối ưu an toàn, kiểm soát quyền và đồng bộ. Nhưng nếu ứng dụng không dùng procedure, không cần tạo routine nhân tạo chỉ để có “test đầy đủ”.

| Trường hợp ứng dụng | Bài kiểm thử hợp lý |
| --- | --- |
| Chỉ dùng SQL chuẩn, repository đơn giản | `@JdbcTest` hoặc `@DataJdbcTest` với fixture và query thật |
| Dùng `CALL` cho PostgreSQL procedure | Test PostgreSQL thật; kiểm input/output và side effect |
| Dùng `SELECT some_function(...)` | Test function với input biên, null, return type, empty set |
| Dùng `JSONB @>`/`->>` | Test PostgreSQL đúng kiểu cột, kiểu parameter và index |
| Dùng UPSERT vendor-specific | Test conflict branch lẫn insert branch, constraints, `RETURNING` |
| Dùng stored routine của Oracle/SQL Server/MySQL | Test đúng driver, engine, schema/package và parameter modes |
| Dùng trigger/sequence/generated column | Test hiệu ứng sau `INSERT/UPDATE` và rollback/permissions |
| Cần chống lost update, oversell, deadlock | Concurrency integration test có nhiều connection/transactions |
| Cần chính sách transaction từ service | Integration test giữ service thật + transaction manager + DB |
| Đọc dữ liệu hàng triệu dòng hoặc SQL plan | Performance test/`EXPLAIN` trên dataset và engine gần production |

**Không lẫn mục tiêu:** test JDBC là bằng chứng cho câu SQL và mapping thật; nó không phải bằng chứng HTTP endpoint/status đúng. Nếu feature được gọi từ API, cần thêm test web/integration theo phạm vi.

## 3. So sánh procedure, function và query SQL

Tên gọi “stored procedure” đôi khi được dùng chung cho mọi routine DB, nhưng **PostgreSQL phân biệt** khá rõ:

| Loại | Khai báo PostgreSQL | Cách gọi | Giá trị trả về |
| --- | --- | --- | --- |
| Procedure | `CREATE PROCEDURE` | `CALL procedure(...)` | Có thể trả dòng output từ `OUT/INOUT` |
| Function scalar | `CREATE FUNCTION ... RETURNS ...` | `SELECT function(...)` | Một giá trị đã khai báo |
| Function trả bảng | `RETURNS TABLE(...)` hoặc `SETOF` | `SELECT * FROM function(...)` | Tập dòng |
| SQL statement | `SELECT/INSERT/UPDATE/DELETE` | JDBC query/update | ResultSet hoặc update count |
| Trigger function | Function được gọi bởi trigger | Thường không gọi trực tiếp từ ứng dụng | Tác dụng qua DML/trigger |

Ví dụ procedure nhận số lượng và trả remaining:

~~~sql
CALL reserve_stock('SKU-101', 3, NULL);
~~~

Trong PostgreSQL, `CALL` với output parameters trả về **một result row**. Với `INOUT p_remaining integer`, argument thứ ba là một input/output placeholder; ví dụ truyền `NULL` và procedure đặt lại giá trị qua `UPDATE ... RETURNING`.

Ví dụ function chỉ đọc:

~~~sql
SELECT stock_total('SKU-');
~~~

**Không gọi PostgreSQL procedure bằng `SELECT reserve_stock(...)`**, cũng không mặc định gọi function bằng `CALL stock_total(...)`. JDBC escape syntax `{call ...}` có hành vi phụ thuộc driver và connection setting; đối với ví dụ này ta dùng **native `CALL`** và **native `SELECT`** để tránh mơ hồ.

### 3.1 IN, OUT, INOUT và JDBC driver

- **IN:** client truyền giá trị vào routine.
- **OUT:** routine cung cấp kết quả ra.
- **INOUT:** vừa nhận input vừa trả output; trong ví dụ input có thể null, sau routine là số lượng còn lại.
- Kiểu JDBC tương ứng phải khớp với PostgreSQL: `text`, `integer`, `bigint`, `numeric`, `uuid`, `jsonb`, v.v.
- SQL `NULL` khác chuỗi `"null"`, khác Java `null` truyền với type không xác định; với overloaded procedures, type inference có thể cần explicit `CAST`.
- Result set của `CALL` có output parameters **không đồng nghĩa** procedure tùy ý trả một table nhiều rows. Nếu API cần nhiều dòng, có thể dùng function `RETURNS TABLE`/cursor tùy engine.

### 3.2 Vì sao không copy routine giữa database engines?

PostgreSQL có `LANGUAGE plpgsql` và dollar-quoted body `$$...$$`. MySQL dùng cú pháp `CREATE PROCEDURE ... BEGIN ... END` với quy tắc delimiter của client, SQL Server dùng `CREATE OR ALTER PROCEDURE` và `EXEC`, Oracle dùng PL/SQL/package và `REF CURSOR`. Các kiểu parameter, transaction, exception, temporary table và quyền `EXECUTE` đều khác nhau.

**Khi chính tính năng riêng là điều cần kiểm, H2 compatibility mode không thay thế engine thật.** Một test H2 chạy được có thể chỉ chứng minh bản SQL đã sửa cho H2, không phải migration/driver production.

## 4. Spring Boot hỗ trợ những lớp test nào?

### @JdbcTest

`@JdbcTest` thuộc `org.springframework.boot.test.autoconfigure.jdbc.JdbcTest` (Spring Boot 3.5.x). Nó tập trung vào **DataSource**, `JdbcTemplate`, transaction manager và những JDBC auto-configurations liên quan, thay vì tải cả web/server/service graph.

Theo mặc định, `@JdbcTest`:

- Có thể thay `DataSource` thành database embedded nếu tìm thấy.
- Có transaction cho test method và **rollback sau mỗi test**.
- Không scan mọi regular `@Component`/`@Repository` business như full application.
- Phù hợp khi adapter dùng trực tiếp `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`.

Vì production `@Repository InventoryGateway` trong ví dụ cần được test thật, ta dùng `@Import(InventoryGateway.class)` để đưa đúng một bean vào slice, không tải toàn bộ application.

### @DataJdbcTest

`@DataJdbcTest` dành cho **Spring Data JDBC repositories** cùng JDBC infrastructure. Nó **khác `@DataJpaTest`**: Spring Data JDBC không dùng Hibernate/JPA entity manager. Nếu dự án dùng `CrudRepository` của Spring Data JDBC, chọn `@DataJdbcTest`; nếu chỉ dùng `JdbcTemplate` + SQL/procedure, `@JdbcTest` gọn hơn.

### @SpringBootTest

`@SpringBootTest` tải context rộng hơn và phù hợp để kiểm service wiring, transaction, scheduling hoặc nhiều tầng. Không cần mặc định dùng nó chỉ để test một SQL statement.

### @AutoConfigureTestDatabase

Đối với database-specific code, dùng:

~~~java
@JdbcTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
class MyPostgresJdbcTest {
    // Kết nối database thật của test, không bị thay bằng H2.
}
~~~

Đây là **annotation mẫu**, chưa có container và datasource. Trong ví dụ hoàn chỉnh, `@ServiceConnection` cấp JDBC connection details từ PostgreSQL Testcontainers.

**Tránh trỏ test vào production DB.** Không bao giờ dùng thông tin kết nối prod cho test integration có `DROP TABLE`, `TRUNCATE` hoặc rollback. Ưu tiên container hoặc database dedicated có schema độc lập, quyền giới hạn.

## 5. Testcontainers và @ServiceConnection: vì sao cần cả hai?

**Testcontainers** khởi động một instance PostgreSQL thật trong Docker/container runtime cho test. **Spring Boot `@ServiceConnection`** dùng thông tin kết nối của container để tạo `JdbcConnectionDetails` phù hợp cho `DataSource`.

~~~text
JUnit Jupiter
    |
    v
@Testcontainers + @Container PostgreSQLContainer
    |
    v
PostgreSQL 16 (container runtime, random mapped port)
    |
    v
@ServiceConnection -> DataSource -> JdbcTemplate
    |
    v
@JdbcTest + @Import(InventoryGateway.class)
    |
    v
Production InventoryGateway -> native CALL / SELECT / JSONB / UPSERT
~~~

Những điều Testcontainers giúp xác minh:

- Driver PostgreSQL kết nối, gửi bind parameters và nhận result set từ engine thật.
- PostgreSQL phân tích `CREATE PROCEDURE`/`PLpgSQL`, `JSONB` và `ON CONFLICT` đúng.
- Constraints/SQLSTATE của PostgreSQL, transaction và isolation đặc trưng.
- Tập dữ liệu test lặp lại được bằng image version cố định.

Những điều Testcontainers **không tự chứng minh**: network proxy, TLS/certificates của production, quyền role production, dữ liệu thực/khối lượng lớn, HA/replication và mọi race concurrency.

### 5.1 Chốt engine và driver

Đối với ví dụ, dùng PostgreSQL 16 qua image `postgres:16-alpine`, với JDBC driver `org.postgresql:postgresql` do Spring Boot BOM quản lý. Một release khác có thể khác behavior của function/procedure, JSONB indexing hoặc SQLSTATE cho tính năng mới.

Khi production nâng PostgreSQL major version, chạy integration tests với version tương ứng trước khi deploy.

### 5.2 Docker là yêu cầu thực tế

Testcontainers yêu cầu Docker Engine hoặc container runtime tương thích, có quyền pull image/chạy container. Nếu CI không có runtime, test sẽ **không khởi động**; không nên biến lỗi environment đó thành “assertion SQL PASS”. Có thể tách suite unit tests chạy mọi nơi và integration tests chỉ chạy trên CI runner có container support.

## 6. Bài thực hành: kiểm cả SQL routine lẫn code Java production

Xây mini application với dữ liệu hàng tồn kho:

~~~text
inventory_item
+----------+-----------+------------------------+
| sku      | available | attributes (jsonb)     |
+----------+-----------+------------------------+
| SKU-101  |         7 | {"origin":"VN"}        |
| SKU-102  |         4 | {"origin":"US"}        |
+----------+-----------+------------------------+

PROCEDURE reserve_stock(p_sku, p_quantity, INOUT p_remaining)
  -> kiểm p_quantity > 0
  -> UPDATE ... WHERE available >= quantity
  -> trả remaining sau update
  -> lỗi nếu SKU không có hoặc thiếu stock

FUNCTION stock_total(p_prefix)
  -> SUM(available) hoặc 0 nếu không có dòng

InventoryGateway (Java thật)
  -> reserve(): CALL reserve_stock
  -> totalAvailable(): SELECT stock_total
  -> upsert(): INSERT ... ON CONFLICT ... RETURNING
  -> findByAttributes(): JSONB @> CAST(? AS jsonb)
~~~

**Ý nghĩa kiểm thử:** procedure và function là code chạy **thật trong PostgreSQL**, gateway là code production **thật**, còn test thay đổi **dữ liệu fixture**, không mock JDBC.

### 6.1 Cấu trúc file

~~~text
src/
  main/
    java/example/pgsql/
      InventoryApplication.java
      InventoryGateway.java
  test/
    java/example/pgsql/
      PostgreSqlInventoryTest.java
~~~

Tất cả Java sources thuộc `package example.pgsql;`. Test nằm cùng package hierarchy với root `@SpringBootApplication` để Boot tìm primary configuration.

### 6.2 Gradle dependency

Trong một project **Spring Boot 3.5.x** đã có Boot Gradle plugin, dependency management và Java 17 toolchain, bổ sung vào `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    testRuntimeOnly 'org.postgresql:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **đoạn cấu hình**, không phải toàn bộ Gradle build file. Spring Boot BOM nên quản lý version của starter, driver và Testcontainers. Dùng `testRuntimeOnly` cho driver vì test code không tham chiếu trực tiếp tới lớp pgjdbc; production application thật cần driver ở runtime của ứng dụng theo deployment config.

Với dự án chỉ dùng JDBC repository, không cần `spring-boot-starter-data-jpa` hoặc Hibernate. Thêm JPA chỉ để test procedure sẽ tăng startup/auto-configuration mà không mang lại bằng chứng cần thiết.

## 7. Production Java: InventoryApplication.java

~~~java
package example.pgsql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

Lớp này là primary config để Spring Boot tìm đúng package. Ứng dụng production standalone cần `spring.datasource.*`/secrets bên ngoài và migrations để tạo schema; bài test không dùng connection production vì `@ServiceConnection` cấp PostgreSQL container.

## 8. Production Java: InventoryGateway.java

~~~java
package example.pgsql;

import java.util.List;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryGateway {

    private final JdbcTemplate jdbc;

    public InventoryGateway(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * Gọi PostgreSQL procedure có tham số INOUT:
     * p_sku, p_quantity là IN; p_remaining là INOUT.
     * CALL với output parameter trả một result row.
     */
    public int reserve(String sku, int quantity) {
        Integer remaining = jdbc.queryForObject(
                "CALL reserve_stock(?, ?, NULL)",
                Integer.class,
                sku, quantity);

        return Objects.requireNonNull(
                remaining, "procedure returned null remaining");
    }

    /** Gọi PostgreSQL scalar function qua SELECT. */
    public long totalAvailable(String prefix) {
        Long total = jdbc.queryForObject(
                "SELECT stock_total(?)",
                Long.class, prefix);
        return Objects.requireNonNull(
                total, "function returned null total");
    }

    /** PostgreSQL UPSERT + RETURNING đưa số tồn mới về Java. */
    public int upsert(String sku, int increment) {
        Integer next = jdbc.queryForObject("""
                INSERT INTO inventory_item(
                    sku, available, attributes)
                VALUES (?, ?, '{}'::jsonb)
                ON CONFLICT (sku)
                DO UPDATE SET
                    available =
                        inventory_item.available + EXCLUDED.available
                RETURNING available
                """, Integer.class, sku, increment);

        return Objects.requireNonNull(
                next, "UPSERT returned null available");
    }

    /** Operator JSONB containment, bind JSON qua CAST(? AS jsonb). */
    public List<String> findByAttributes(String jsonFilter) {
        return jdbc.query("""
                SELECT sku
                FROM inventory_item
                WHERE attributes @> CAST(? AS jsonb)
                ORDER BY sku
                """,
                (rs, rowNum) -> rs.getString("sku"),
                jsonFilter);
    }

    /** Đọc stock để assert side effect của routine/upsert. */
    public int available(String sku) {
        Integer value = jdbc.queryForObject("""
                SELECT available
                FROM inventory_item
                WHERE sku = ?
                """, Integer.class, sku);

        return Objects.requireNonNull(
                value, "row has null available");
    }
}
~~~

Những điểm quan trọng:

- `reserve` gọi **native PostgreSQL `CALL`** và nhận một result row từ parameter `INOUT`, tránh giả định JDBC escape syntax `{call...}` ở mọi driver sẽ tự chọn đúng `CALL`.
- `totalAvailable` gọi function bằng `SELECT`.
- `upsert` sử dụng `ON CONFLICT (sku) DO UPDATE ... RETURNING available`, có cả nhánh insert và update.
- `findByAttributes` dùng `?` bind parameter, không nối JSON filter của client vào SQL string; `@>` là operator containment của PostgreSQL `jsonb`.
- `available` là helper đọc trạng thái để test **tác dụng thật** của procedure. Nó cũng dùng bind parameter, không tự ghép SKU vào query.
- `Objects.requireNonNull` ngăn kết quả null bị auto-unbox thành lỗi khó hiểu; trong production có thể thay bằng exception/`Optional` theo contract.

**Lưu ý về bảo mật:** parameter binding giúp tránh SQL injection vào **giá trị**, nhưng không tự bảo vệ identifier động (tên bảng, tên cột, ORDER BY), quy tắc quyền `EXECUTE` hoặc JSON filter rất lớn. Whitelist identifiers và validate input ở tầng API/service.

## 9. Test Java hoàn chỉnh: PostgreSqlInventoryTest.java

Test sử dụng `@JdbcTest` + `@Import(InventoryGateway.class)` để kiểm production gateway thật, `@Testcontainers` + `@ServiceConnection` cho PostgreSQL thật, và `@AutoConfigureTestDatabase(replace=NONE)` để không thay bằng H2.

**Fixture/migration cho bài thực hành** được dựng bằng `JdbcTemplate.execute(...)` trong `@BeforeEach`. Mỗi `CREATE TABLE`/`CREATE PROCEDURE`/`CREATE FUNCTION` là **một SQL statement gửi nguyên văn** cho PostgreSQL, vì SQL body `$$...;...$$` có semicolon nội bộ. Không sử dụng một `@Sql` script với splitter mặc định rồi vô tình cắt routine tại dấu chấm phẩy trong body.

~~~java
package example.pgsql;

import java.sql.SQLException;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

@JdbcTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(InventoryGateway.class)
@Testcontainers
@DisplayName("JDBC integration: PostgreSQL procedure/function/JSONB")
class PostgreSqlInventoryTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    InventoryGateway gateway;

    @BeforeEach
    void setUp() {
        jdbc.execute("""
                CREATE TABLE inventory_item (
                    sku text PRIMARY KEY,
                    available integer NOT NULL
                        CHECK (available >= 0),
                    attributes jsonb NOT NULL
                        DEFAULT '{}'::jsonb
                )
                """);

        jdbc.execute("""
                CREATE OR REPLACE PROCEDURE reserve_stock(
                    IN p_sku text,
                    IN p_quantity integer,
                    INOUT p_remaining integer
                )
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF p_quantity IS NULL
                       OR p_quantity <= 0 THEN
                        RAISE EXCEPTION
                            'quantity must be positive'
                            USING ERRCODE = '22023';
                    END IF;

                    UPDATE inventory_item
                    SET available = available - p_quantity
                    WHERE sku = p_sku
                      AND available >= p_quantity
                    RETURNING available INTO p_remaining;

                    IF NOT FOUND THEN
                        RAISE EXCEPTION
                            'missing SKU or insufficient stock'
                            USING ERRCODE = 'P0001';
                    END IF;
                END;
                $$;
                """);

        jdbc.execute("""
                CREATE OR REPLACE FUNCTION stock_total(
                    p_prefix text
                )
                RETURNS bigint
                LANGUAGE sql
                STABLE
                AS $$
                    SELECT COALESCE(SUM(available), 0)
                    FROM inventory_item
                    WHERE sku LIKE p_prefix || '%'
                $$;
                """);

        jdbc.update("""
                INSERT INTO inventory_item(
                    sku, available, attributes)
                VALUES (?, ?, CAST(? AS jsonb))
                """,
                "SKU-101", 7, "{\"origin\":\"VN\",\"fragile\":false}");

        jdbc.update("""
                INSERT INTO inventory_item(
                    sku, available, attributes)
                VALUES (?, ?, CAST(? AS jsonb))
                """,
                "SKU-102", 4, "{\"origin\":\"US\",\"fragile\":true}");
    }

    @Test
    @DisplayName("CALL INOUT trả remaining và cập nhật row thật")
    void reserveReturnsRemainingAndUpdatesDatabase() {
        int remaining = gateway.reserve("SKU-101", 3);

        assertEquals(4, remaining);
        assertEquals(4, gateway.available("SKU-101"));
        assertEquals(4, gateway.available("SKU-102"));
    }

    @Test
    @DisplayName("Đặt đúng toàn bộ tồn kho còn về zero")
    void exactReservationLeavesZero() {
        int remaining = gateway.reserve("SKU-101", 7);

        assertEquals(0, remaining);
        assertEquals(0, gateway.available("SKU-101"));
    }

    @Test
    @DisplayName("Quantity zero bị từ chối bằng SQLSTATE 22023")
    void zeroQuantityRaisesSqlState22023() {
        DataAccessException failure = assertThrows(
                DataAccessException.class,
                () -> gateway.reserve("SKU-101", 0));

        assertSqlState(failure, "22023");
        // PostgreSQL transaction đã bị đánh dấu aborted.
        // Không query DB tiếp trong test method này.
    }

    @Test
    @DisplayName("Thiếu hàng tạo lỗi nghiệp vụ SQLSTATE P0001")
    void insufficientStockRaisesDomainSqlState() {
        DataAccessException failure = assertThrows(
                DataAccessException.class,
                () -> gateway.reserve("SKU-101", 8));

        assertSqlState(failure, "P0001");
    }

    @Test
    @DisplayName("SKU không tồn tại cũng được xử lý có chủ đích")
    void missingSkuRaisesDomainSqlState() {
        DataAccessException failure = assertThrows(
                DataAccessException.class,
                () -> gateway.reserve("DOES-NOT-EXIST", 1));

        assertSqlState(failure, "P0001");
    }

    @Test
    @DisplayName("SELECT function: tổng đúng và tập rỗng trả 0")
    void functionReturnsExpectedTotals() {
        assertEquals(11L, gateway.totalAvailable("SKU-"));
        assertEquals(0L, gateway.totalAvailable("UNKNOWN-"));
    }

    @Test
    @DisplayName("ON CONFLICT cập nhật row và RETURNING đúng")
    void upsertConflictBranch() {
        int next = gateway.upsert("SKU-101", 3);

        assertEquals(10, next);
        assertEquals(10, gateway.available("SKU-101"));
    }

    @Test
    @DisplayName("UPSERT insert branch tạo một SKU mới")
    void upsertInsertBranch() {
        int next = gateway.upsert("SKU-NEW", 2);

        assertEquals(2, next);
        assertEquals(2, gateway.available("SKU-NEW"));
    }

    @Test
    @DisplayName("JSONB containment @> và CAST bind parameter")
    void jsonbFilterFindsOnlyMatchingSku() {
        List<String> result = gateway.findByAttributes(
                "{\"origin\":\"VN\"}");

        assertEquals(List.of("SKU-101"), result);
        assertEquals(List.of(),
                gateway.findByAttributes("{\"origin\":\"FR\"}"));
    }

    @Test
    @DisplayName("JSON filter có ký tự nháy không biến thành SQL")
    void jsonFilterIsBoundAsValue() {
        List<String> result = gateway.findByAttributes(
                "{\"origin\":\"VN' OR '1'='1\"}");

        assertTrue(result.isEmpty());
        assertEquals(11L, gateway.totalAvailable("SKU-"));
    }

    @Test
    @DisplayName("Unique key vi phạm SQLSTATE 23505")
    void duplicateSkuViolatesUniqueConstraint() {
        DataAccessException failure = assertThrows(
                DataAccessException.class,
                () -> jdbc.update("""
                        INSERT INTO inventory_item(
                            sku, available, attributes)
                        VALUES (?, ?, '{}'::jsonb)
                        """,
                        "SKU-101", 1));

        assertSqlState(failure, "23505");
        // Không query thêm vì transaction PostgreSQL đang aborted.
    }

    private static void assertSqlState(
            Throwable failure, String expected) {
        Throwable current = failure;

        while (current != null) {
            if (current instanceof SQLException sql
                    && expected.equals(sql.getSQLState())) {
                return;
            }
            current = current.getCause();
        }

        fail("Expected SQLSTATE " + expected, failure);
    }
}
~~~

**Tổng cộng 11 phương thức JUnit Jupiter `@Test`.** Chúng dùng repository/gateway thật và PostgreSQL thật. Dữ liệu `SKU-101` có 7 đơn vị, `SKU-102` có 4; test có thể chứng minh routine trả output và **cập nhật đúng trạng thái**.

### 9.1 Tại sao tạo schema/procedure ở @BeforeEach?

Với `@JdbcTest`, Spring TestContext bắt đầu transaction kiểm thử trước các callback Jupiter `@BeforeEach` và mặc định rollback sau từng test. **PostgreSQL hỗ trợ transactional DDL**, nên table/procedure/function vừa tạo trong transaction test sẽ biến mất khi rollback. Test sau dựng lại fixture từ đầu.

Cách này đơn giản cho ví dụ độc lập, không thay thế cách production triển khai schema. Production nên quản lý DDL qua **Flyway/Liquibase**, có version và migration rollback/forward policy. Với một database engine **không hỗ trợ rollback DDL đầy đủ**, `CREATE TABLE` trong `@BeforeEach` có thể tồn tại sau test; cần schema riêng, migrations và cleanup rõ.

**Không chạy test methods song song** trên cùng schema khi chúng dùng tên table/routine cố định, trừ khi mỗi test có schema/database riêng. Dù transaction rollback giúp cô lập dữ liệu, concurrency của DDL và locks vẫn có thể gây race.

### 9.2 Vì sao bắt lỗi rồi không đọc DB ngay?

PostgreSQL có một quy tắc quan trọng: **sau lỗi SQL trong transaction hiện tại, transaction được đánh dấu aborted**. Kể cả `assertThrows` đã bắt exception Java, PostgreSQL sẽ từ chối câu lệnh SQL tiếp theo bằng lỗi kiểu:

~~~text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
SQLSTATE 25P02
~~~

Do đó trong `zeroQuantityRaisesSqlState22023`, `insufficientStockRaisesDomainSqlState` và `duplicateSkuViolatesUniqueConstraint`, test chỉ kiểm SQLSTATE rồi kết thúc. Spring test transaction rollback sau method sẽ xóa trạng thái aborted.

Nếu bạn muốn kiểm “sau lỗi, database không có thay đổi nào”, hãy **kết thúc transaction bị lỗi trước**, rồi mở transaction/connection mới để quan sát. Không kiểm bằng `SELECT` trên cùng transaction đang aborted. Phần 13 trình bày kỹ cách test atomicity và rollback.

### 9.3 Tại sao SQLSTATE quan trọng hơn exact error text?

`getSQLState()` là mã lỗi có ý nghĩa theo driver/DB, thường ổn định hơn message chứa SQL, locale, parameter values hoặc implementation detail.

Trong ví dụ:

| SQLSTATE | Ý nghĩa |
| --- | --- |
| `22023` | PostgreSQL `invalid_parameter_value`, được routine dùng cho quantity ≤ 0 |
| `P0001` | `raise_exception`, routine dùng cho SKU không tồn tại hoặc thiếu stock |
| `23505` | Vi phạm `unique_violation` do primary key |
| `25P02` | Transaction đã bị abort, không nhận SQL kế tiếp |

**Chú ý:** SQLSTATE cũng **có những mã đặc thù vendor**; không thay nó bằng một enum “chung cho mọi database” mà không kiểm driver. Nếu ứng dụng có policy mapping error sang `OutOfStockException`/HTTP 409, test thêm lớp service/error translation tương ứng.

### 9.4 Vì sao không kiểm bằng mock?

Nếu mock `JdbcTemplate` rồi stub `queryForObject` trả 4, test sẽ không phát hiện:

- `CALL` sai tên routine hoặc thiếu argument `INOUT`.
- `PostgreSQLContainer` không tương thích schema.
- `JSONB @>` bị viết thành query sai.
- `ON CONFLICT` không match unique key.
- Ràng buộc DB không được tạo bởi migrations.
- Driver trả SQLSTATE khác expectation.

Unit test có thể kiểm mapping/exception translation ở Java, nhưng **không thay database integration test** khi chính vendor-specific SQL cần được bảo đảm.

## 10. Cách chạy và stdout dự kiến

Tại thư mục dự án đã cấu hình Spring Boot 3.5.x/Java 17+:

~~~bash
./gradlew test --tests example.pgsql.PostgreSqlInventoryTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.pgsql.PostgreSqlInventoryTest
~~~

Yêu cầu:

- Docker/container runtime đang chạy và tài khoản CI có quyền sử dụng.
- Image `postgres:16-alpine` được tải được; lần đầu có thể cần internet.
- Java 17+, Gradle wrapper/Boot plugin cùng dependency versions tương thích.
- Test classes ở đúng package/path và không có test-specific datasource khác override `@ServiceConnection`.

**Kết quả dự kiến:** JUnit Jupiter phát hiện **11 tests** và tất cả PASS, Gradle có thể hiển thị `BUILD SUCCESSFUL`. Đây là **kết quả kỳ vọng từ thiết kế**; không phải stdout đã được ghi nhận bởi một lần chạy Gradle trong bài viết. Startup logs, port được map của container, số lượng SQL debug statements và thời gian chạy không cố định.

Nếu container không khởi động, hãy đọc nguyên nhân (Docker socket không truy cập được, image pull fail, resource limits); đừng coi đó là lỗi assertion stored procedure. Nếu test không tìm được `InventoryApplication`, kiểm package hierarchy và Boot config đúng.

## 11. Dùng SimpleJdbcCall khi nào?

Spring JDBC có `SimpleJdbcCall` hỗ trợ stored procedure/function qua metadata và/hoặc cấu hình tham số tường minh. Nó có giá trị khi số lượng tham số lớn, có nhiều OUT parameters hoặc ứng dụng đã chuẩn hóa cách gọi routine.

Ví dụ **minh họa một stored procedure thông thường** (không phải file độc lập và **không cam kết chạy nguyên xi trên mọi JDBC driver**):

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(jdbcTemplate)
        .withProcedureName("reserve_stock")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(
                new SqlParameter("p_sku", Types.VARCHAR),
                new SqlParameter("p_quantity", Types.INTEGER),
                new SqlInOutParameter("p_remaining", Types.INTEGER));

Map<String, Object> result = call.execute(
        Map.of(
                "p_sku", "SKU-101",
                "p_quantity", 3,
                "p_remaining", 0));
~~~

Cần imports từ `org.springframework.jdbc.core.simple.SimpleJdbcCall`, `org.springframework.jdbc.core.SqlParameter`, `org.springframework.jdbc.core.SqlInOutParameter`, `java.sql.Types`, `java.util.Map`. Với PostgreSQL, **driver's call escape mode** và việc register INOUT/output parameters ảnh hưởng cách `SimpleJdbcCall` gửi SQL và nhận kết quả.

- Metadata có thể thiếu/khác thứ tự hoặc phân biệt schema; dùng `withoutProcedureColumnMetaDataAccess()` và declare params khi cần rõ.
- PostgreSQL JDBC driver có connection setting `escapeSyntaxCallMode`, ảnh hưởng cách chuyển JDBC escape syntax thành `SELECT` hoặc `CALL`.
- Nếu dùng `SimpleJdbcCall` trong production, **integration test phải gọi chính SimpleJdbcCall của ứng dụng**, không chỉ thay bằng native SQL trong test rồi kết luận wrapper đúng.
- Khi native `CALL ...` qua `JdbcTemplate` đơn giản, dễ kiểm và đúng mục tiêu, không cần thêm abstraction chỉ vì API tồn tại.

### 11.1 Phân biệt CallableStatement

JDBC thuần có `CallableStatement`:

~~~java
Connection connection = ...;
CallableStatement call =
        connection.prepareCall("{call some_procedure(?, ?)}");
call.setString(1, "SKU-101");
call.registerOutParameter(2, Types.INTEGER);
call.execute();
int value = call.getInt(2);
~~~

Đây là **khung minh họa**, chưa có connection lifecycle, procedure phù hợp hoặc exception handling. Khi dùng trong Spring JDBC, hãy thao tác trong `JdbcTemplate.execute(ConnectionCallback)`/`CallableStatementCallback` để Spring quản lý connection, exception translation và transaction.

Đừng dùng ví dụ `{call...}` từ SQL Server rồi copy thẳng vào PostgreSQL với assumption driver luôn dịch đúng. Tài liệu pgjdbc về `escapeSyntaxCallMode=callIfNoReturn` cần được xem khi procedure với OUT/INOUT không hoạt động.

## 12. Function trả một giá trị, nhiều dòng hoặc refcursor

Ví dụ function `stock_total` trả `bigint` từ aggregate. Không phải function nào cũng trả scalar:

| Kết quả | PostgreSQL | API Java điển hình |
| --- | --- | --- |
| Scalar | `RETURNS bigint` | `queryForObject("SELECT fn(?)", Long.class, ...)` |
| Một record/composite | `RETURNS record` / custom type | ResultSet mapping cụ thể |
| Nhiều dòng | `RETURNS TABLE(...)` hoặc `SETOF` | `jdbc.query("SELECT * FROM fn(?)", rowMapper, ...)` |
| Cursor | `refcursor` | Driver-specific handling, có thể yêu cầu transaction |
| Không có result set | `CALL procedure_without_out(...)` | `JdbcTemplate.update/execute` theo JDBC behavior |

Với function trả bảng, assert **số dòng, thứ tự (nếu có ORDER BY), types, nullability và lọc**. Đừng dựa vào việc database trả rows theo insertion order khi query không có `ORDER BY`.

Với `refcursor`, các driver yêu cầu session/transaction vẫn còn mở khi fetch cursor. Một test “chạy được trên H2” thường không tái hiện cursor semantics của PostgreSQL/Oracle. Phải test bằng đúng driver và đảm bảo resource cleanup.

## 13. Transaction, rollback và atomicity cần hiểu chính xác

### 13.1 Test rollback mặc định không phải commit production

`@JdbcTest` mặc định test transactional và rollback khi kết thúc. Điều này tiện cho fixtures, nhưng nó **không chứng minh production transaction commit thành công** qua một service khác hoặc một connection khác.

Một procedure có thể thực hiện SQL UPDATE trong cùng transaction đang mở; test đọc lại row sẽ thấy thay đổi, rồi rollback sau test. Đây là bằng chứng **logic UPDATE đúng**, không phải bằng chứng commit/persistence qua restart.

### 13.2 PostgreSQL procedure có thể tự COMMIT khi nào?

PostgreSQL cho phép một số procedure thực hiện transaction control `COMMIT`/`ROLLBACK` **chỉ khi `CALL` phù hợp điều kiện top-level, không nằm trong explicit transaction block**. Một procedure chứa `COMMIT` sẽ không chạy như mong đợi nếu bị gọi bên trong test transaction của `@JdbcTest`.

Nếu routine production tự quản lý transaction:

- Không dùng test method mặc định transactional để gọi nó.
- Có thể dùng `@Transactional(propagation = Propagation.NOT_SUPPORTED)` để tắt transaction của Spring TestContext cho test đó.
- Chủ động khởi tạo schema/fixtures và cleanup riêng vì không còn rollback tự động.
- Đảm bảo test database là dedicated, không dùng production.
- Assert behavior sau commit/rollback bằng **connection khác** và đúng isolation.

Trong ví dụ `reserve_stock` **không** có `COMMIT/ROLLBACK` bên trong procedure, nên hoạt động trong test transaction của Spring.

### 13.3 Atomic update và chống oversell

Procedure dùng một statement:

~~~sql
UPDATE inventory_item
SET available = available - p_quantity
WHERE sku = p_sku
  AND available >= p_quantity
RETURNING available INTO p_remaining;
~~~

Điều kiện `available >= p_quantity` nằm **trong cùng UPDATE**; database lock và recheck row theo transaction semantics phù hợp sẽ ngăn cùng một statement làm stock âm. Đây là thiết kế tốt hơn kiểu “SELECT available trong Java → nếu đủ thì UPDATE” vì hai request đồng thời có thể đọc cùng stock cũ.

Tuy nhiên, một unit/integration test **đơn luồng** không chứng minh được không có lost update khi hai transactions chạy cùng lúc. Cần một **concurrency test** với ít nhất hai connections thực, barrier để điều khiển thời điểm, timeout, và các assertion cuối cùng sau commit.

### 13.4 Cách test rollback sau khi procedure ném exception

Để xem DB có rollback đúng, không làm:

~~~java
// Sai trong cùng PostgreSQL transaction sau lỗi SQL:
assertThrows(DataAccessException.class,
        () -> gateway.reserve("SKU-101", 99));
assertEquals(7, gateway.available("SKU-101"));
~~~

Vì transaction đã aborted, `SELECT` ở dòng cuối có thể nhận SQLSTATE `25P02`, dù bản ghi thực tế không thay đổi.

Cách đúng ở mức nguyên tắc:

1. Dùng một test database riêng, seed data trong **transaction đã commit**.
2. Bắt đầu **một transaction mới**, thực hiện các thay đổi và gọi procedure gây lỗi.
3. Rollback transaction lỗi.
4. Mở **connection/transaction mới** và query stock để xác nhận không có state partial.
5. Cleanup fixture bằng transaction/schema độc lập.

Khi dùng `TransactionTemplate`, nhớ rằng exception phải được phép thoát callback hoặc phải đánh dấu `setRollbackOnly()`. Với PG, chỉ catch exception rồi tiếp tục SQL trong cùng transaction vẫn không phục hồi transaction; phải rollback và mở giao dịch mới.

## 14. Kiểm lỗi: exception translation và SQLSTATE

`JdbcTemplate` dùng Spring `SQLExceptionTranslator` chuyển nhiều `SQLException` thành các subclass `DataAccessException`. Chi tiết phân loại có thể phụ thuộc database/driver/version, nhưng root cause thường giữ SQLSTATE.

Ví dụ:

~~~java
DataAccessException thrown = assertThrows(
        DataAccessException.class,
        () -> gateway.reserve("SKU-101", 0));

assertSqlState(thrown, "22023");
~~~

Ở đây `assertSqlState` là helper đã định nghĩa trong file runnable mục 9.

**Vì sao không assert chính xác message?**

- Message có thể bị localize hoặc thêm thông tin của server.
- Driver có thể wrap thêm SQL/parameters.
- Error text của `RAISE EXCEPTION` có thể đổi khi routine được nâng version.
- Message có thể chứa thông tin nhạy cảm nếu đưa raw SQL/parameters vào log công khai.

Nếu ứng dụng mapping `P0001` thành một domain exception riêng, unit test có thể kiểm mapping, còn database test kiểm SQLSTATE gốc. Không dùng `getMessage().contains("inventory")` làm điều kiện duy nhất để xác định business conflict.

### 14.1 Lỗi khi PostgreSQL transaction bị abort

Sau một SQL exception:

~~~text
SQLSTATE 22023 / P0001 / 23505   <-- lỗi gốc
SQLSTATE 25P02                   <-- lỗi phụ khi tiếp tục query
~~~

Đừng báo “database trả lỗi sai” nếu câu lệnh thứ hai nhận `25P02`; đó là dấu hiệu test tiếp tục sử dụng transaction chưa rollback.

### 14.2 Negative cases cần test

| Kịch bản | Điều mong đợi |
| --- | --- |
| Quantity = 0 hoặc âm | Lỗi input `22023`, không có kết quả reserve |
| SKU không tồn tại | Lỗi `P0001` theo routine |
| Quantity vượt stock | Lỗi `P0001`; không được trừ stock |
| SKU trùng khi INSERT thông thường | `23505` unique violation |
| `attributes` là JSON không hợp lệ | PostgreSQL báo lỗi JSON cast, SQLSTATE driver/vendor phù hợp |
| SQL user không có quyền EXECUTE | Permission denied / SQLSTATE `42501` ở role phù hợp |
| Procedure signature bị đổi | Driver/DB báo routine không tìm thấy hoặc parameter mismatch |
| Deadline query quá thấp | Timeout/cancel; không giả định transaction đã rollback mọi side effects ngoài DB |
| Mất kết nối | Exception connection-level; phải xử lý retry/idempotency theo policy |

Khi viết test có SQL exception, sử dụng một transaction riêng **cho mỗi failure case**, không cố thực hiện tất cả case trong một transaction bị đánh dấu aborted sau lỗi đầu.

## 15. PostgreSQL JSONB: test đúng operator và kiểu dữ liệu

`JSONB` của PostgreSQL không giống một cột `VARCHAR` chứa chuỗi JSON. Nó là kiểu có parsing, indexing và operators riêng:

~~~sql
SELECT sku
FROM inventory_item
WHERE attributes @> '{"origin":"VN"}'::jsonb;
~~~

`@>` hỏi phía trái có chứa cấu trúc JSON phía phải theo containment semantics của PostgreSQL. Với dữ liệu:

~~~json
{"origin":"VN","fragile":false}
~~~

filter `{"origin":"VN"}` khớp, `{"origin":"US"}` không khớp.

Trong Java, để tránh SQL injection, code sử dụng:

~~~java
jdbc.query("""
    SELECT sku
    FROM inventory_item
    WHERE attributes @> CAST(? AS jsonb)
    ORDER BY sku
    """, rowMapper, jsonFilter);
~~~

Với PostgreSQL JDBC driver, bind string vào `?` rồi `CAST(... AS jsonb)` cho phép database parse JSON theo kiểu thật. Không xây SQL bằng:

~~~java
// Sai: ghép input không đáng tin vào SQL.
String sql = "SELECT sku FROM inventory_item WHERE attributes @> '"
        + userJson + "'::jsonb";
~~~

Test cần kiểm **cả JSON filter hợp lệ và input chứa dấu nháy**; đoạn `jsonFilterIsBoundAsValue()` minh họa input chứa `' OR ...` nhưng vẫn chỉ là một string JSON, không biến thành SQL condition.

**Giới hạn:** bind parameters bảo vệ cú pháp SQL, không tự đảm bảo JSON được validate theo business schema hoặc không có payload quá lớn. Production nên có giới hạn độ sâu/size và schema validation khi tiếp nhận JSON từ client.

### 15.1 Index và hiệu năng

PostgreSQL có thể dùng GIN index cho `jsonb` containment trong nhiều trường hợp:

~~~sql
CREATE INDEX idx_inventory_attributes
ON inventory_item
USING GIN (attributes);
~~~

Đây là SQL PostgreSQL, không có trong fixture runnable vì mục tiêu ở đây là correctness, không benchmark. Test filter trả đúng record **không chứng minh** query sử dụng index hoặc chạy nhanh trên một triệu rows. Nếu performance quan trọng, kiểm `EXPLAIN (ANALYZE, BUFFERS)` trên dataset và DB gần production.

## 16. UPSERT, RETURNING và ranh giới giữa update count với result set

PostgreSQL hỗ trợ:

~~~sql
INSERT INTO inventory_item(sku, available, attributes)
VALUES ('SKU-101', 3, '{}'::jsonb)
ON CONFLICT (sku)
DO UPDATE SET
  available = inventory_item.available + EXCLUDED.available
RETURNING available;
~~~

Trong ví dụ, `SKU-101` tồn tại với `available=7`, nên nhánh conflict trả **10**. Với `SKU-NEW` chưa có, câu lệnh insert trả **2**.

**Điểm dễ nhầm trong Spring JDBC:** vì câu SQL có `RETURNING`, nó **trả ResultSet**. `JdbcTemplate.queryForObject(...)` phù hợp để đọc giá trị; đừng mặc định dùng `jdbc.update(...)` rồi mong nhận số stock mới. `update(...)` trả **row count**, không phải giá trị của cột `available`.

Nếu muốn kiểm insert/update side effects:

- Assert returned value từ `RETURNING`.
- Query row sau lệnh bằng `SELECT` trong cùng transaction.
- Kiểm key/unique constraint thực.
- Kiểm nhánh conflict với cùng key, không chỉ nhánh insert.
- Kiểm overflow/negative increments nếu business rule cho phép/hạn chế.

Nếu `increment` âm, `CHECK (available >= 0)` có thể chặn đưa stock dưới zero; đây là tính năng constraint độc lập. Nếu logic nghiệp vụ là “không được giảm bằng upsert”, service phải validate input; không giả định PostgreSQL tự cấm mọi increment âm miễn kết quả vẫn ≥0.

## 17. Quản lý schema: Flyway, Liquibase và SQL scripts

Trong hệ thống production, stored procedures/functions phải được **version control** như Java code. Ví dụ Flyway migrations:

~~~text
src/main/resources/db/migration/
  V1__create_inventory_item.sql
  V2__reserve_stock_procedure.sql
  V3__stock_total_function.sql
  V4__inventory_constraints_and_indexes.sql
~~~

Test example tự tạo routine trong `@BeforeEach` để **độc lập và dễ đọc**. Nhưng integration test production nên chạy migrations thật trên PostgreSQL container, thay vì có **hai bản DDL** được bảo trì thủ công khác nhau. Nếu test tạo một procedure “đẹp” của riêng nó, còn migration thực tạo procedure sai, test sẽ PASS sai mục tiêu.

### 17.1 Dollar quote và script splitting

PostgreSQL PL/pgSQL dùng:

~~~sql
CREATE OR REPLACE PROCEDURE demo()
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'hello';
END;
$$;
~~~

Body có nhiều semicolons. Một SQL runner tách statements chỉ bằng dấu chấm phẩy **không hiểu dollar-quoting** có thể cắt sai giữa `BEGIN ... END`. Flyway/Liquibase hỗ trợ PostgreSQL routine scripting theo cú pháp/thiết lập phù hợp. Với Spring `@Sql`/`ScriptUtils`, nếu script phức tạp, có thể dùng **custom separator** hoặc gọi mỗi DDL statement nguyên văn bằng `JdbcTemplate.execute` như trong bài.

**Đừng đặt `spring.sql.init.mode=always` rồi đồng thời chạy Flyway migrations mà không thiết kế rõ thứ tự.** Test có thể vô tình tạo schema hai lần hoặc nạp fixture trước migration.

### 17.2 Migration verification cần tách biệt

Một suite integration tốt có thể có:

- **Migration smoke test:** PostgreSQL container trống, chạy từ V1 đến version hiện tại, kiểm bảng/routine/privileges tồn tại.
- **Routine contract test:** gọi production gateway và assert output/side effects trên schema do migration tạo.
- **Upgrade test:** migration từ schema version cũ có dữ liệu lịch sử lên version mới, kiểm dữ liệu còn nguyên và routine trả đúng.
- **Permission test:** app role chỉ có quyền cần thiết, không phải database superuser như container default.
- **Rollback policy:** nếu migration không đảo ngược được, phải có forward-fix/backup/recovery strategy.

Testcontainers giúp cô lập môi trường, **không tự chạy migrations** trừ khi có Flyway/Liquibase/SQL init được cấu hình cho context test.

## 18. Test các tính năng vendor-specific khác: chọn theo rủi ro

| Tính năng | Ví dụ engine | Kiểm trực tiếp |
| --- | --- | --- |
| `JSONB` | PostgreSQL | Operator containment, cast/bind, JSON path/index, null semantics |
| `ON CONFLICT ... RETURNING` | PostgreSQL | Insert/conflict branches và returned values |
| `MERGE` | SQL Server/Oracle/PostgreSQL theo version | Matched/unmatched branches, trigger/locking behavior |
| `INSERT ... ON DUPLICATE KEY UPDATE` | MySQL/MariaDB | Conflict rule, affected rows, generated IDs |
| `OUTPUT INSERTED.*` | SQL Server | Result set và trigger interactions |
| Stored procedure/PLSQL package | Oracle | Parameter modes, cursors, exception mapping |
| `UPSERT` và `RETURNING` | Vendor-specific | ResultSet vs update count, rows thực cập nhật |
| `FOR UPDATE SKIP LOCKED` | PostgreSQL/Oracle/MySQL tùy version | Two-transaction lock behavior, queue claims |
| Advisory locks | PostgreSQL | Lock acquisition, release, session vs transaction scope |
| Window functions | Nhiều DB | Partition/order/frame và boundary rows |
| Generated columns, triggers | Nhiều DB | Server-generated values sau INSERT/UPDATE |
| Collation/timezone/case folding | Theo DB | Sorting và comparison cho tiếng Việt, Unicode, timezone |
| Sequence/identity columns | Theo DB | Generated key type, gaps và rollback semantics |

**Không ép các test này vào H2** nếu ứng dụng dùng semantics vendor-specific. Với tính năng khác PostgreSQL, thay container/driver và viết fixture SQL cho engine thật.

### 18.1 Kiểm lock cần nhiều connections

Nếu production dùng `SELECT ... FOR UPDATE SKIP LOCKED` để nhận việc trong hàng đợi, một test có một connection không chứng minh được “hai workers không lấy cùng job”. Cần:

1. Seed một hoặc nhiều jobs và commit.
2. Transaction A lock một job và giữ transaction mở.
3. Transaction B trên **connection độc lập** chạy cùng claim query.
4. Assert B không lấy job mà A đang lock (hoặc lấy job khác đúng contract).
5. Commit/rollback cả hai, kiểm final state và cleanup.

Không dùng một `JdbcTemplate` trong **cùng thread + cùng Spring transaction** rồi tưởng đó là hai giao dịch. Dùng `TransactionTemplate` với propagation rõ hoặc hai connections/threads và synchronization barriers.

### 18.2 Test isolation, deadlock và retry

SQLSTATE cho serialization failure/deadlock có thể cần retry đúng giới hạn, nhưng **không retry mọi DataAccessException**. Retry một stored procedure có side effects (email, external payment, sequence IDs) có thể nhân đôi tác vụ. Test cần phân biệt **idempotency**, isolation level, timeout, số lần thử và mapping lỗi, bằng các scenarios riêng.

## 19. Testing exception với transaction độc lập

Khi cần assert trạng thái DB sau một transaction đã lỗi, có thể viết test chuyên trách theo mẫu **khái niệm** sau:

~~~java
// Pseudocode trong một integration test đã cấu hình DB test:
// 1. Seed và COMMIT bằng transaction riêng.
// 2. Chạy giao dịch muốn kiểm trong TransactionTemplate.
// 3. Để exception thoát callback -> transaction rollback.
// 4. Query qua một transaction/connection MỚI sau rollback.
// 5. Assert snapshot trạng thái trước/sau bằng nhau.
~~~

Đây là **pseudocode**, không phải code Java để compile. Sở dĩ không gắn trực tiếp vào class `PostgreSqlInventoryTest` là vì class đó đã dùng transaction rollback mặc định, và fixture schema chỉ tồn tại **bên trong transaction của mỗi test**. Một `REQUIRES_NEW` transaction sẽ không thấy DDL/rows chưa commit của transaction fixture ở PostgreSQL.

Nếu cần test rollback thật, hãy dùng **migration/schema đã commit trước test**, seed data trong transaction riêng đã commit, rồi mới kiểm transaction thất bại và query sau rollback. Việc nắm rõ thứ tự commit này quan trọng hơn viết thêm một `assertEquals` sau `assertThrows` nhưng khiến test trả `25P02`.

### 19.1 Vì sao TestTransaction không phải công cụ duy nhất?

Spring TestContext có `TestTransaction` để đánh dấu và kết thúc/restart test transaction. Nó hữu ích trong một số bài integration test, nhưng đòi hiểu fixture lifecycle, committed DDL và cleanup. Không nhất thiết dùng `TestTransaction` cho mỗi method nếu một `@JdbcTest` rollback đơn giản đã đủ để kiểm routine success/output.

Nếu code production thực sự dùng `@Transactional(propagation = REQUIRES_NEW)` hoặc procedure tự commit, hãy test **chính semantics đó** trong context có transaction manager thật.

## 20. SQL injection và quyền EXECUTE

Một routine có thể chạy với quyền caller hoặc definer theo engine/configuration. Với PostgreSQL:

- Mặc định nhiều functions/procedures chạy theo quyền invoker; có `SECURITY DEFINER` cho một số routines.
- `SECURITY DEFINER` có thể mở rộng quyền đáng kể; cần kiểm owner, `search_path`, schema qualification và revoke/GRANT phù hợp.
- Các `?` bind parameter chỉ bind **giá trị**, không bind tên procedure/schema/table.
- Không xây `CALL ` + userInput + `(...)` hay dynamic SQL bên trong routine không được quote/whitelist.
- Test thông thường chạy bằng user container có quyền rộng sẽ **không phát hiện** việc production app role thiếu `EXECUTE`.
- Một permission test thật nên tạo role quyền hạn giống application và kết nối bằng credentials riêng.

Khi routine dùng dynamic SQL trong PL/pgSQL, ưu tiên `EXECUTE ... USING` cho giá trị và `format('%I', identifier)` khi identifier thực sự cần động. Đừng log nguyên connection credentials hoặc raw PII/SQL bên ngoài test environment.

### 20.1 Một function result hợp lệ chưa chứng minh security

`SELECT stock_total('SKU-')` trả 11 trên superuser không chứng minh ứng dụng được phép chạy function. Nếu business bắt buộc áp dụng row-level security, test phải dùng role/tenant context thực và kiểm `SELECT`/`CALL` không vượt visibility rules. Test này tách biệt correctness của aggregate.

## 21. Lỗi thường gặp khi kiểm stored procedures/database features

**1. Dùng H2 để xác nhận PostgreSQL PL/pgSQL.**  
H2 không triển khai tương đương mọi procedure, JSONB, UPSERT, transaction semantics. Dùng PostgreSQL container khi production dùng PostgreSQL.

**2. Test chỉ stub return value của gateway.**  
Mock không chứng minh routine có mặt, SQL đúng hoặc side effect. Test production adapter với JDBC thật.

**3. Dùng `SELECT proc(...)` cho procedure PostgreSQL.**  
`CREATE PROCEDURE` được gọi bằng `CALL`; `CREATE FUNCTION` thường gọi qua `SELECT`.

**4. Quên output/INOUT parameter trong CALL.**  
Đối với PostgreSQL CALL, phải cung cấp argument position cần thiết; parameter OUT/INOUT có semantics khác nhau. Kiểm signature hiện hành.

**5. Tin `{call ...}` luôn map thành CALL.**  
pgjdbc `escapeSyntaxCallMode` có thể dịch JDBC escape syntax theo chế độ connection. Khi cần kiểm native procedure, dùng native `CALL` hoặc cấu hình driver có test.

**6. Dùng `JdbcTemplate.update(...)` cho SQL có RETURNING và mong nhận cột trả về.**  
`update` trả affected row count, không phải result value. Dùng `queryForObject` hoặc mapping ResultSet.

**7. Không assert state sau CALL thành công.**  
Chỉ assert output parameter có thể bỏ sót UPDATE sai bảng/filter. Kiểm row thực.

**8. Bắt exception rồi SELECT trong PostgreSQL transaction bị abort.**  
Sau lỗi, transaction có thể nhận `25P02`. Rollback rồi mở transaction mới.

**9. Dùng @JdbcTest transactional mặc định để gọi procedure có COMMIT bên trong.**  
PostgreSQL cấm transaction control trong procedure khi CALL nằm trong explicit transaction block. Thiết kế test non-transactional có cleanup.

**10. Không phân biệt SQLSTATE và message.**  
Message dễ thay đổi theo driver/locale/version; kiểm mã lỗi đáng tin cậy, map về domain error ở tầng khác.

**11. Dùng ScriptUtils/@Sql với delimiter mặc định cắt PL/pgSQL giữa $$ body.**  
Chạy migration runner hỗ trợ PostgreSQL hoặc custom separator, không tách mù ở mọi semicolon.

**12. Chạy tests song song trên một schema với CREATE/DROP cố định.**  
Dễ race/lock; dùng schema riêng hoặc tuần tự, rollback và cleanup đúng.

**13. Tưởng H2 transaction rollback DDL giống PostgreSQL.**  
DDL rollback phụ thuộc engine; fixture strategy phải phù hợp.

**14. Cho rằng bind parameter cho JSONB là tự động không cần type.**  
Driver có thể truyền varchar khiến operator/type mismatch. Dùng `CAST(? AS jsonb)` hoặc type adapter thích hợp.

**15. Ghép JSON/ID input vào SQL string.**  
Có nguy cơ SQL injection. Bind dữ liệu bằng `?`/named parameter, whitelist SQL identifiers.

**16. Chỉ kiểm nhánh INSERT của UPSERT.**  
Bỏ sót conflict clause, unique key và RETURNING đúng giá trị sau UPDATE.

**17. Không test unique/foreign-key/check constraints.**  
Một mock repository luôn có thể trả “thành công” dù schema production từ chối dữ liệu.

**18. Dùng connection cùng transaction để giả lập concurrency.**  
Không có hai giao dịch độc lập nên không test được row-level locking/race.

**19. Cho rằng test với PostgreSQL nhỏ đã chứng minh performance production.**  
Index, query plan, cardinality, disk, vacuum, contention và network ảnh hưởng mạnh. Đo riêng trên dữ liệu gần production.

**20. Không chạy migrations production trong integration suite.**  
DDL test riêng có thể khác production; cần test migrations và code trên cùng schema.

**21. Mọi SQL exception đều retry.**  
Unique violation hoặc invalid quantity không phải transient. Retry đúng loại lỗi và có idempotency policy.

**22. Không giới hạn thời gian cho lock/wait.**  
Test có thể treo nếu row bị lock lâu. Thiết lập statement timeout, test deadline và cleanup sessions.

## 22. Quy trình thiết kế kiểm thử thực tế

1. **Liệt kê SQL riêng của database:** procedure/function, JSONB/arrays, UPSERT/RETURNING, lock/trigger/sequence.
2. **Gắn chức năng với engine/version:** PostgreSQL 16, SQL Server 2022, Oracle, MySQL v.v.; test đúng phiên bản/dialect.
3. **Chọn tầng test:** unit cho Java business rules; `@JdbcTest`/`@DataJdbcTest` cho SQL; `@SpringBootTest` khi cần service/transaction wiring.
4. **Dùng Testcontainers hoặc test DB isolated**, tuyệt đối không dùng production credentials.
5. **Chạy migrations thật** nếu mục tiêu là contract production; chỉ tạo DDL trực tiếp cho ví dụ nhỏ, có ghi rõ giới hạn.
6. **Chuẩn bị fixture có dữ liệu biên:** zero, missing, insufficient, duplicate, JSON hợp lệ/sai, conflict branch.
7. **Gọi production adapter thật**, không chỉ chạy SQL do test tự viết rồi quên Java mapping.
8. **Assert output AND side effects:** output param, return value, rows updated, constraints, rows không bị thay sai.
9. **Assert SQLSTATE** khi có lỗi; đừng query tiếp trong transaction PostgreSQL đã abort.
10. **Kiểm rollback bằng transaction/connection mới** nếu atomicity là contract, seed đã commit trước.
11. **Kiểm two-transaction cases** nếu feature liên quan lock/concurrency.
12. **Kiểm role/permission riêng** khi routine chạy với quyền đặc biệt.
13. **Giữ test ổn định:** image cố định, dataset reset, timeout hữu hạn, không chạy song song trên cùng DDL.
14. **Kiểm performance/SQL plan tách biệt**, đừng thay correctness bằng benchmark.
15. **Đưa kết quả vào CI:** báo rõ runtime Docker, DB image, migrations, version, code paths được kiểm.

### Checklist trước khi commit

- [ ] Chỉ test procedure/vendor feature thực sự được codebase sử dụng.
- [ ] Test chạy trên DB engine phù hợp, không coi H2 mode là bằng chứng PostgreSQL/Oracle/MySQL.
- [ ] Database test cô lập, không chạm production.
- [ ] DDL/migration version đồng bộ với production hoặc giới hạn fixture được ghi rõ.
- [ ] Chọn `@JdbcTest` khi chỉ cần JdbcTemplate, `@DataJdbcTest` khi dùng Spring Data JDBC.
- [ ] `@AutoConfigureTestDatabase(replace=NONE)`/`@ServiceConnection` trỏ đúng PostgreSQL container.
- [ ] Code Java production được gọi thật, không mock SUT SQL adapter.
- [ ] `CALL`/`SELECT` và OUT/INOUT parameters đúng signature.
- [ ] Có test result value và state thay đổi sau routine.
- [ ] Có test invalid quantity, missing key, insufficient stock và constraint violation.
- [ ] SQL exception được kiểm bằng SQLSTATE phù hợp; không tái sử dụng transaction đã abort.
- [ ] Nếu routine có COMMIT/ROLLBACK bên trong, test không cưỡng ép nó chạy trong explicit transaction block.
- [ ] JSONB type/operator được kiểm qua driver với bind parameters.
- [ ] UPSERT có test insert branch, conflict branch và RETURNING.
- [ ] Concurrency/locking, permissions, migration upgrade được test riêng khi là rủi ro.
- [ ] Có timeout, fixture reset/rollback, cleanup và version pin cho CI.
- [ ] Không log secrets hoặc chạy DDL phá hủy trên môi trường chia sẻ.

**Tổng kết:** stored procedure và các tính năng riêng của database phải được kiểm bằng **database thật** vì contract không chỉ là kết quả Java trả về; nó bao gồm SQL parser, driver, kiểu tham số, transaction, output mapping, constraints, error codes và side effects. Với Spring Boot, `@JdbcTest` kết hợp PostgreSQL Testcontainers và gateway production là lựa chọn tập trung. Khi kiểm kỹ **CALL/SELECT, INOUT, JSONB, UPSERT, SQLSTATE, rollback và concurrency ở tầng phù hợp**, test sẽ phát hiện những lỗi mà mock hoặc H2 không thể thấy.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Auto-configured JDBC Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@JdbcTest`, `@DataJdbcTest`, transactional rollback, test database replacement.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, `PostgreSQLContainer` và connection details.
- [Spring Framework — JdbcTemplate & SimpleJdbcCall](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html): routine calls, stored procedure metadata, parameter declarations.
- [Spring Framework — Testing with @Sql](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): test scripts, separators, transactions và script execution.
- [PostgreSQL 16 — CREATE PROCEDURE](https://www.postgresql.org/docs/16/sql-createprocedure.html): procedure signature, PL/pgSQL, parameter modes.
- [PostgreSQL 16 — CALL](https://www.postgresql.org/docs/16/sql-call.html): output parameters, result row và transaction control restrictions.
- [PostgreSQL 16 — JSON Types](https://www.postgresql.org/docs/16/datatype-json.html): `jsonb` và cách biểu diễn dữ liệu.
- [PostgreSQL 16 — JSON Functions and Operators](https://www.postgresql.org/docs/16/functions-json.html): `@>`, `->>` và các JSON operators.
- [PostgreSQL 16 — INSERT / ON CONFLICT / RETURNING](https://www.postgresql.org/docs/16/sql-insert.html): insert, UPSERT, returned rows.
- [PostgreSQL 16 — Error Codes](https://www.postgresql.org/docs/16/errcodes-appendix.html): `22023`, `23505`, `25P02` và `P0001`.
- [Testcontainers — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/): khởi động PostgreSQL container cho integration tests.

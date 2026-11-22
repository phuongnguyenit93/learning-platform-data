# Chạy kiểm thử hợp đồng trước khi đổi nền cơ sở dữ liệu trong JDBC

Trong chương **Đa hệ quản trị**, một lợi thế của JDBC là ứng dụng Java truy cập nhiều hệ quản trị cơ sở dữ liệu quan hệ qua những giao diện chung như `DataSource`, `Connection`, `PreparedStatement` và `ResultSet`. Tuy nhiên, **cùng biên dịch được với API JDBC không đồng nghĩa cùng hành vi trên mọi database và driver**. Một câu lệnh từng chạy đúng trên PostgreSQL có thể cần cú pháp khác trên MySQL hoặc SQL Server; ngay cả khi câu SQL chạy thành công, kết quả về `NULL`, độ chính xác `DECIMAL`, Unicode, khóa sinh, transaction và số hàng cập nhật vẫn có thể không tương đương.

Giả sử hệ thống muốn chuyển từ PostgreSQL sang MySQL. Nhóm phát triển thay JDBC URL, driver và các câu SQL dùng `RETURNING`. Các bài kiểm tra CRUD đơn giản đều xanh, nhưng khi triển khai lại phát hiện cùng một email được so sánh không phân biệt hoa/thường do collation mới; thời điểm `TIMESTAMP` bị dịch vì timezone; một `INSERT` trùng khóa bị phân loại sai thành lỗi hệ thống; hoặc một công việc ghi hai bảng chỉ được commit một nửa do engine/transaction khác. Vấn đề là hệ thống đã kiểm tra rằng SQL *chạy*, nhưng chưa xác nhận **hợp đồng nghiệp vụ và dữ liệu**.

**Kiểm thử hợp đồng (*contract testing*)** là xác định trước những điều repository phải bảo đảm và chạy cùng một bộ assertion với từng cấu hình **DB + JDBC driver + schema + transaction/pool** dự kiến sử dụng. Bài này hướng dẫn xây dựng hợp đồng có thể kiểm chứng, tách phần khác biệt theo hệ quản trị, viết ví dụ JUnit 5 trên JDBC chuẩn, tổ chức ma trận CI và đặt điều kiện rõ ràng trước khi quyết định chuyển nền cơ sở dữ liệu.

## 1. Thứ cần giữ nguyên là hành vi, không phải tên driver

Một “nền cơ sở dữ liệu” gồm nhiều thành phần ảnh hưởng tới kết quả:

```text
                       Hợp đồng nghiệp vụ
                    (dữ liệu, CRUD, transaction)
                               |
                        Repository/DAO
                               |
                    SQL + JDBC Type Mapping
                               |
                  DataSource / JDBC Driver
                               |
            Database engine + version + schema + collation
                               |
                    Cấu hình session, timezone,
                    isolation, permission, pooling
```

JDBC chuẩn hóa **cách gọi API**, còn DB và driver vẫn quyết định nhiều chi tiết về:

| Phạm vi | Câu hỏi cần xác minh khi chuyển DB |
| --- | --- |
| SQL dialect | `LIMIT`, `OFFSET/FETCH`, `RETURNING`, UPSERT, tên kiểu, hàm ngày giờ có chạy không? |
| Kiểu dữ liệu | `UUID`, `JSON`, `BOOLEAN`, `BLOB/CLOB` và `NUMERIC` được gán/đọc theo cơ chế nào? |
| NULL/chuỗi | `NULL` có bị nhầm với `0`/`""` không? DB xử lý chuỗi rỗng, collation thế nào? |
| Số và thời gian | Precision/scale, rounding, micro/nano giây, timezone và DST có giữ đúng ý nghĩa không? |
| Ràng buộc | `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK` có cưỡng chế đúng phạm vi? |
| Transaction | Rollback, autocommit, isolation, savepoint, lỗi giữa transaction hoạt động thế nào? |
| Đồng thời | Optimistic locking, affected-row counts, deadlock và retry có giữ dữ liệu đúng? |
| JDBC driver | `getGeneratedKeys`, `setObject`, `getObject(..., Class)`, fetch/batch, metadata có hỗ trợ? |
| Vận hành | Connection pool, giới hạn session, quyền truy cập, TLS, SQLState và monitoring có tương thích? |

Do đó mục tiêu của contract suite là **cùng một tập kỳ vọng nghiệp vụ trên các nền**, không phải cưỡng ép mọi SQL, schema và tên kiểu giống hệt nhau.

## 2. Chuyển yêu cầu nghiệp vụ thành các bất biến có thể assert

Trước khi chuyển DB, hãy chốt bằng văn bản những điều một repository phải bảo đảm. Ví dụ với `CustomerRepository`:

| Mã hợp đồng | Bất biến bắt buộc | Assertion đáng tin |
| --- | --- | --- |
| C01 – Identity | Tạo khách hàng trả một ID sử dụng được để đọc lại | `getGeneratedKeys()` có ID; `SELECT` theo ID thấy đúng hàng |
| C02 – Tenant | Mã ngoài `external_code` chỉ duy nhất trong một tenant | Hai hàng cùng tenant/code bị DB từ chối; hai tenant có thể trùng code |
| C03 – Unicode | Tên tiếng Việt và emoji được giữ theo quy tắc chuẩn hóa đã chọn | So nội dung ký tự sau round-trip |
| C04 – NULL | Ghi chú SQL `NULL` khác chuỗi rỗng | `getString` trả `null` và `""` trong hai ca riêng |
| C05 – Decimal | Số tiền chính xác ở scale 4 | `BigDecimal.compareTo(...) == 0`; kiểm tra scale theo hợp đồng |
| C06 – Time | Giờ nghiệp vụ ở cột không timezone giữ nguyên trường ngày/giờ đến micro giây | So `LocalDateTime` sau khi đọc |
| C07 – Version | Update với phiên bản cũ không ghi đè | Update lần đầu = 1, cùng version cũ = 0; giá trị mới không bị thay |
| C08 – Atomicity | Thay đổi trong transaction không commit phải rollback được | Đọc sau rollback không thấy bản ghi đã ghi |
| C09 – Pagination | Trang liên tiếp trong dữ liệu đứng yên không trùng/bỏ sót | `ORDER BY` có tie-breaker duy nhất; kiểm tra toàn bộ ID |
| C10 – Error contract | Unique violation có thể được phân loại chính xác | Adapter trả `DUPLICATE_KEY`, không gom FK/CHECK/timeout |

Không phải mọi dự án cần đủ những bất biến này; chọn theo chức năng đang sử dụng. Với hệ thống có JSONB, mảng, stored procedure hoặc optimistic locking nhiều bảng, thêm những test riêng cho chúng trước khi migration.

**Phân biệt hai loại yêu cầu:**

- **Bất biến bắt buộc:** ví dụ tiền không được mất chính xác, dữ liệu tenant khác không được đọc, transaction phải nguyên tử. Không chấp nhận bỏ qua vì DB mới hoạt động khác.
- **Khác biệt được cho phép có kiểm soát:** ví dụ thông điệp lỗi native khác, độ dài tên index khác, ID tự sinh không liên tiếp, `OffsetDateTime` đọc lại có offset khác nhưng cùng `Instant`. Assertion nên kiểm tra ngữ nghĩa cần giữ chứ không phụ thuộc chi tiết không được bảo đảm.

Một test “chạy không ném exception” không thay thế được một assertion về tính đúng đắn.

## 3. Phân loại khả năng tương thích trước khi viết adapter

Có ba nhóm thay đổi thường gặp:

1. **Giữ nguyên JDBC nhưng đổi cú pháp SQL:** PostgreSQL `INSERT ... RETURNING id` so với việc dùng `Statement.RETURN_GENERATED_KEYS`; `LIMIT ?` so với `OFFSET ... FETCH`.
2. **Giữ API JDBC nhưng đổi ánh xạ kiểu:** PostgreSQL `uuid`/`jsonb`, MySQL `JSON`, SQL Server `uniqueidentifier`; cùng `setObject` có thể cần cách bind khác.
3. **Thay đổi ngữ nghĩa DB:** collation so chữ, `NULL`, cách giữ timezone, transaction isolation, độ chính xác số, khóa và số dòng bị ảnh hưởng.

Nhóm thứ ba nguy hiểm hơn thay cú pháp vì SQL có thể chạy **thành công nhưng sai nghiệp vụ**. Chỉ một ma trận hợp đồng có dữ liệu biên và thử nghiệm concurrency mới phát hiện một phần đáng kể các trường hợp ấy.

### Lập bảng quyết định cho mỗi khác biệt

| Tình huống | Cách xử lý ưu tiên |
| --- | --- |
| Cùng ngữ nghĩa, khác SQL dialect | Tách câu SQL theo DB hoặc một adapter rất nhỏ |
| Driver không hỗ trợ một overload | Dùng API thay thế **đã kiểm thử**, không ép kiểu mù quáng |
| Khác collation nhưng nghiệp vụ cần so sánh chính xác | Xác định collation/normalization rõ hoặc đổi ràng buộc/schema |
| DB mới không hỗ trợ bất biến quan trọng | **Block cutover**, không đánh dấu test “skip” cho qua |
| Nghiệp vụ chấp nhận khác biệt | Ghi rõ phiên bản hợp đồng, tác động và người phê duyệt |

Trong môi trường nhiều DB, không nên tạo một lớp trừu tượng khổng lồ chỉ để ẩn mọi khác biệt. Bắt đầu bằng hợp đồng và một adapter đủ nhỏ cho cú pháp/kiểu mà JDBC không chuẩn hóa, rồi mở rộng khi có bằng chứng.

## 4. Hai schema khác cú pháp nhưng cùng hợp đồng dữ liệu

Để thử một bảng `contract_customer` trên PostgreSQL và MySQL, giữ những bất biến chung:

- `id` do DB sinh và là khóa chính.
- `(tenant_id, external_code)` duy nhất.
- `display_name` chứa Unicode; `note` cho phép SQL `NULL`.
- `amount` là thập phân 18 chữ số, trong đó 4 chữ số sau dấu phẩy.
- `occurred_at` là **giờ trên đồng hồ**, không đại diện trực tiếp cho một thời điểm UTC.
- `version` khởi tạo 0 và tăng theo mỗi cập nhật hợp lệ.

### PostgreSQL: DDL minh họa

```sql
-- Chạy bằng migration identity trên test database, không phải production.
CREATE TABLE contract_customer (
    id            BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id     BIGINT NOT NULL,
    external_code VARCHAR(80) NOT NULL,
    display_name  VARCHAR(200) NOT NULL,
    amount        NUMERIC(18,4) NOT NULL,
    note          VARCHAR(200),
    occurred_at   TIMESTAMP(6) WITHOUT TIME ZONE NOT NULL,
    version       BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_contract_customer_tenant_code
        UNIQUE (tenant_id, external_code)
);
```

### MySQL: DDL minh họa

```sql
-- Chạy bằng migration identity trên test database MySQL.
CREATE TABLE contract_customer (
    id            BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    tenant_id     BIGINT NOT NULL,
    external_code VARCHAR(80) NOT NULL,
    display_name  VARCHAR(200) NOT NULL,
    amount        DECIMAL(18,4) NOT NULL,
    note          VARCHAR(200) NULL,
    occurred_at   DATETIME(6) NOT NULL,
    version       BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_contract_customer_tenant_code
        UNIQUE (tenant_id, external_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Đây là **hai DDL riêng**, không phải hai cách viết có ngữ nghĩa mặc nhiên giống hệt nhau. Trong MySQL, collation mặc định có thể so sánh chữ không phân biệt hoa/thường hoặc dấu, tùy phiên bản và cấu hình; PostgreSQL thường có quy tắc khác. Nếu `external_code` phải phân biệt chính xác chữ hoa/chữ thường, hãy quy định collation hoặc chuẩn hóa mã trước khi lưu và **kiểm tra unique constraint bằng case-sensitive test**.

`NUMERIC(18,4)` và `DECIMAL(18,4)` có mục tiêu chung nhưng cần thử những giá trị sát biên; `TIMESTAMP(6) WITHOUT TIME ZONE` ở PostgreSQL và `DATETIME(6)` ở MySQL được chọn để minh họa `LocalDateTime`, không tự động tạo hợp đồng về timezone tuyệt đối. Nếu nghiệp vụ cần instant, cần thiết kế và kiểm thử kiểu/cách lưu khác theo DB.

**Quan trọng:** DDL được thực hiện trong bước setup/migration **trước** test. Không để test nghiệp vụ tự `CREATE TABLE` rồi `DROP TABLE` trong transaction và giả định mọi DB rollback DDL giống nhau; một số hệ quản trị tự commit DDL.

## 5. Chạy cùng một bộ test trên từng DB, không thay expected value theo driver

Ý tưởng tổ chức:

```text
                       JdbcCustomerContractSuite
                       (JUnit 5 assertions chung)
                           /              \
                          /                \
             PostgreSQL binding        MySQL binding
             DataSource PG             DataSource MySQL
             Schema migration PG       Schema migration MySQL
             Classifier PG 23505       Classifier MySQL 1062
                          \                /
                           \              /
                       Kết quả PASS/FAIL
                       cho cùng bất biến
```

JUnit có thể triển khai bằng một **abstract test class** hoặc cùng các test `@ParameterizedTest`/`@TestFactory` nhận tham số `DbTarget`. Ở ví dụ này, class cơ sở chứa assertion; mỗi subclass cấu hình `DataSource` trỏ tới database test tương ứng và cách phân loại unique violation.

### Giao diện tối thiểu của bộ test

```java
import java.sql.SQLException;
import javax.sql.DataSource;

public abstract class JdbcCustomerContractSuite {
    // Mỗi target cấp DataSource với driver và quyền runtime đúng môi trường.
    protected abstract DataSource dataSource();

    // Mỗi target hiện thực bằng mã lỗi đã được kiểm tra trên DB/driver đó.
    protected abstract boolean isUniqueViolation(SQLException error);

    // Các phương thức @Test tiếp theo dùng chung cho mọi target.
}
```

Test dùng một bảng đã được tạo đúng tên/kiểu và **không tự thay assertion chỉ vì driver khác**. Ví dụ code có thể là `@Test` JUnit 5 kế thừa từ class cơ sở; những subclass chỉ được cấp quyền điều chỉnh setup/dialect được cho phép. Nếu một DB không thể đáp ứng hợp đồng, test phải FAIL hoặc bị block migration, không nên lặng lẽ bỏ test.

## 6. Ví dụ JUnit 5: round-trip Unicode, NULL, DECIMAL, timestamp và khóa sinh

Đoạn sau là **phần bổ sung bên trong `JdbcCustomerContractSuite`** ở mục 5. Nó dùng JDBC chuẩn và JUnit Jupiter; lớp con sẽ cung cấp `dataSource()`. Mỗi test mượn connection riêng, mở transaction, rồi rollback để không để lại dữ liệu fixture. Test database phải được cấu hình cô lập; pool test nếu có phải được xác minh khả năng reset hoặc loại bỏ connection hỏng.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Types;
import java.time.LocalDateTime;
import java.util.UUID;
import org.junit.jupiter.api.Test;

// Các phương thức dưới đây đặt trong JdbcCustomerContractSuite.
protected long insertCustomer(
        Connection c, long tenant, String code, String name,
        BigDecimal amount, String note, LocalDateTime occurredAt)
        throws SQLException {
    String sql = """
            INSERT INTO contract_customer (
                tenant_id, external_code, display_name,
                amount, note, occurred_at, version
            ) VALUES (?, ?, ?, ?, ?, ?, 0)
            """;

    try (PreparedStatement ps = c.prepareStatement(
            sql, Statement.RETURN_GENERATED_KEYS)) {
        ps.setLong(1, tenant);
        ps.setString(2, code);
        ps.setString(3, name);
        ps.setBigDecimal(4, amount);
        if (note == null) {
            ps.setNull(5, Types.VARCHAR);
        } else {
            ps.setString(5, note);
        }
        ps.setObject(6, occurredAt);

        assertEquals(1, ps.executeUpdate());
        try (ResultSet keys = ps.getGeneratedKeys()) {
            assertTrue(keys.next(),
                    "Driver phải trả khóa sinh của hàng đã INSERT");
            long id = keys.getLong(1);
            assertFalse(keys.wasNull());
            return id;
        }
    }
}

@Test
void generatedKeyAndValueRoundTrip() throws SQLException {
    BigDecimal expectedAmount = new BigDecimal("123456.6700");
    String expectedName = "Hà Nội – Đà Nẵng 🌏 e\u0301";
    LocalDateTime expectedTime = LocalDateTime.of(
            2026, 11, 17, 9, 30, 15, 123_456_000);
    String code = "unicode-" + UUID.randomUUID();

    try (Connection c = dataSource().getConnection()) {
        c.setAutoCommit(false);
        try {
            long id = insertCustomer(
                    c, 7L, code, expectedName, expectedAmount,
                    null, expectedTime);

            String sql = """
                    SELECT tenant_id, external_code, display_name,
                           amount, note, occurred_at, version
                    FROM contract_customer
                    WHERE id = ?
                    """;
            try (PreparedStatement ps = c.prepareStatement(sql)) {
                ps.setLong(1, id);
                try (ResultSet rs = ps.executeQuery()) {
                    assertTrue(rs.next());
                    assertEquals(7L, rs.getLong("tenant_id"));
                    assertEquals(code, rs.getString("external_code"));
                    assertEquals(expectedName,
                            rs.getString("display_name"));

                    BigDecimal actual = rs.getBigDecimal("amount");
                    assertNotNull(actual);
                    assertEquals(0, expectedAmount.compareTo(actual));
                    assertEquals(4, actual.scale());

                    assertNull(rs.getString("note"));
                    assertEquals(expectedTime, rs.getObject(
                            "occurred_at", LocalDateTime.class));
                    assertEquals(0L, rs.getLong("version"));
                    assertFalse(rs.next());
                }
            }
        } finally {
            c.rollback(); // Không để lại dữ liệu test.
        }
    }
}
```

**Hợp đồng thực sự được kiểm tra:**

- `getGeneratedKeys()` trả khóa cho câu `INSERT` có yêu cầu `Statement.RETURN_GENERATED_KEYS`; không assert rằng ID liên tiếp, vì sequence/identity có thể để lại khoảng trống sau rollback hoặc ghi đồng thời.
- Unicode được so **đúng chuỗi**; nếu nghiệp vụ yêu cầu chuẩn hóa NFC, hãy áp dụng ở ứng dụng và sửa hợp đồng một cách tường minh, không cho qua lỗi bằng cách normalize đầu vào và đầu ra tùy tiện.
- `getBigDecimal` giữ đúng giá trị số và scale 4 của cột thập phân theo schema đã chọn. Không chuyển qua `double`.
- SQL `NULL` ở `note` được đọc thành Java `null`, **không** tự chuyển thành `""`. Bổ sung một test riêng ghi `note=""` để chứng minh hai trạng thái khác nhau trên DB mục tiêu.
- `LocalDateTime` kiểm tra giờ theo các trường lịch, không mặc định là instant UTC. Giá trị nano ở ví dụ tương ứng micro giây để phù hợp độ chính xác cột.

Nếu `getGeneratedKeys()` hoặc `getObject(..., LocalDateTime.class)` không được driver hỗ trợ, test báo lỗi tương thích. Khi có phương án thay thế hợp lệ, đặt nó trong adapter đã kiểm chứng và chạy lại hợp đồng; **không xóa assertion về dữ liệu chỉ để test xanh**.

## 7. Kiểm thử unique constraint và optimistic locking trên DB thật

### Một test bắt lỗi trùng khóa từ database

Không nên chỉ `SELECT` kiểm tra mã khách hàng tồn tại trước `INSERT`. Hai transaction đồng thời vẫn có thể chèn cùng giá trị sau khi cùng kiểm tra “chưa có”. Bất biến duy nhất phải do DB cưỡng chế.

Đoạn sau bổ sung vào cùng test class:

```java
@Test
void uniqueConstraintRejectsDuplicateWithinTenant() throws SQLException {
    String code = "dup-" + UUID.randomUUID();
    LocalDateTime time = LocalDateTime.of(2026, 11, 17, 8, 0);

    try (Connection c = dataSource().getConnection()) {
        c.setAutoCommit(false);
        try {
            insertCustomer(c, 8L, code, "Bản thứ nhất",
                    new BigDecimal("1.0000"), null, time);

            SQLException failure = assertThrows(
                    SQLException.class,
                    () -> insertCustomer(c, 8L, code, "Bản thứ hai",
                            new BigDecimal("2.0000"), null, time));
            assertTrue(isUniqueViolation(failure),
                    "Phải phân loại đúng unique violation");

            // Không tiếp tục SELECT trong transaction sau lỗi.
            // PostgreSQL có thể đánh dấu transaction đang bị lỗi.
        } finally {
            c.rollback();
        }
    }
}
```

Lưu ý: đây là test **negative**; `assertThrows` chỉ xác nhận có lỗi nhưng `isUniqueViolation` mới xác nhận **đúng nhóm lỗi**. Cần thêm test cùng `external_code` ở hai tenant khác nhau, và test trùng `id` nếu nghiệp vụ cần phân biệt khóa chính với mã nghiệp vụ.

### Optimistic locking phải chống ghi đè

Với cột `version`, câu SQL cần tăng version ngay khi cập nhật:

```sql
UPDATE contract_customer
SET display_name = ?, version = version + 1
WHERE tenant_id = ? AND id = ? AND version = ?;
```

Test:

```java
@Test
void staleVersionMustNotOverwriteLatestValue() throws SQLException {
    String code = "stale-" + UUID.randomUUID();
    LocalDateTime time = LocalDateTime.of(2026, 11, 17, 8, 30);

    try (Connection c = dataSource().getConnection()) {
        c.setAutoCommit(false);
        try {
            long id = insertCustomer(c, 9L, code, "Tên gốc",
                    new BigDecimal("1.0000"), "", time);
            String update = """
                    UPDATE contract_customer
                    SET display_name = ?, version = version + 1
                    WHERE tenant_id = ? AND id = ? AND version = ?
                    """;

            try (PreparedStatement ps = c.prepareStatement(update)) {
                ps.setString(1, "Tên do A sửa");
                ps.setLong(2, 9L);
                ps.setLong(3, id);
                ps.setLong(4, 0L);
                assertEquals(1, ps.executeUpdate());

                ps.setString(1, "Tên do B sửa");
                ps.setLong(4, 0L); // B vẫn cầm phiên bản cũ.
                assertEquals(0, ps.executeUpdate());
            }

            try (PreparedStatement ps = c.prepareStatement(
                    "SELECT display_name, version "
                            + "FROM contract_customer WHERE id = ?")) {
                ps.setLong(1, id);
                try (ResultSet rs = ps.executeQuery()) {
                    assertTrue(rs.next());
                    assertEquals("Tên do A sửa",
                            rs.getString("display_name"));
                    assertEquals(1L, rs.getLong("version"));
                }
            }
        } finally {
            c.rollback();
        }
    }
}
```

Test này kiểm tra **điều kiện phiên bản**, chưa phải phép thử hai transaction thật sự chạy đồng thời. Trước cutover, thêm một test concurrency dùng **hai connection độc lập**, lịch chạy có `CountDownLatch`/timeout và kiểm tra cùng bất biến khi có lock/transaction isolation thật.

Không diễn giải mọi `executeUpdate()==0` là “bản ghi không tồn tại”: với điều kiện `version=?`, đó còn có thể là bản ghi đã thay đổi. Đối với MySQL, cấu hình đếm *matched rows* so với *changed rows* có thể ảnh hưởng các câu `UPDATE` không làm thay đổi giá trị; mẫu tăng `version` giúp tránh nhập nhằng ở trường hợp update thành công.

## 8. Bộ phân loại lỗi theo driver không được làm biến dạng hợp đồng

JDBC có `SQLException.getSQLState()` và `getErrorCode()`, nhưng mã unique violation khác nhau theo DB. Ví dụ PostgreSQL thường dùng SQLState `23505`; MySQL thường báo mã lỗi vendor `1062` cùng SQLState `23000` cho lỗi trùng khóa.

```java
import java.sql.SQLException;

public final class UniqueErrorAdapters {
    private UniqueErrorAdapters() {}

    public static boolean postgres(SQLException error) {
        for (SQLException e = error; e != null;
             e = e.getNextException()) {
            if ("23505".equals(e.getSQLState())) {
                return true;
            }
        }
        return false;
    }

    public static boolean mysql(SQLException error) {
        for (SQLException e = error; e != null;
             e = e.getNextException()) {
            if ("23000".equals(e.getSQLState())
                    && e.getErrorCode() == 1062) {
                return true;
            }
        }
        return false;
    }
}
```

Những phương thức trên là **adapter minh họa**, phải được kiểm chứng với đúng phiên bản driver đang dùng. Không dùng `error.getMessage().contains("duplicate")` làm điều kiện quyết định nghiệp vụ vì câu thông báo có thể đổi theo driver/ngôn ngữ. Cũng không coi **mọi SQLState bắt đầu bằng 23** là lỗi unique: `FOREIGN KEY`, `NOT NULL` hay `CHECK` cũng thuộc nhóm ràng buộc.

Nếu một bảng có nhiều unique constraint, nhận biết `23505` hoặc `1062` **chưa đủ** để kết luận đó là trùng email hay mã đơn hàng. Khi cần báo lỗi ở mức trường, phải xác minh đúng tên constraint bằng thông tin lỗi có cấu trúc do driver cung cấp hoặc một chiến lược DB-specific đã kiểm thử; không đoán bằng cách parse nguyên văn message.

### Hai class target có thể liên kết vào cùng bộ test

Ví dụ phần cấu hình **minh họa**; `TestDataSources.postgres()` và `TestDataSources.mysql()` là các factory test do dự án tự viết để cung cấp `DataSource` phù hợp, không phải API JDK:

```java
public final class PostgresCustomerContractTest
        extends JdbcCustomerContractSuite {
    @Override
    protected DataSource dataSource() {
        return TestDataSources.postgres();
    }

    @Override
    protected boolean isUniqueViolation(SQLException error) {
        return UniqueErrorAdapters.postgres(error);
    }
}

public final class MySqlCustomerContractTest
        extends JdbcCustomerContractSuite {
    @Override
    protected DataSource dataSource() {
        return TestDataSources.mysql();
    }

    @Override
    protected boolean isUniqueViolation(SQLException error) {
        return UniqueErrorAdapters.mysql(error);
    }
}
```

Trong một project Java thật, mỗi `public` class ở file Java riêng; đoạn trên nhóm chúng lại để minh họa ý tưởng. Factory phải cấu hình qua secret test và chỉ cho phép JDBC URL trỏ tới DB thử nghiệm, không tới dữ liệu production. Nếu dùng JUnit `@Nested`, `@ParameterizedTest` hoặc hệ thống test containers, cấu trúc class sẽ khác nhưng **hợp đồng assertion không thay**.

## 9. Transaction: thử atomicity, rollback và trạng thái sau lỗi

Các phép thử CRUD đơn lẻ không chứng minh **hai thao tác SQL cùng commit hoặc cùng rollback**. Một lỗi hay gặp khi chuyển DB là migration dùng engine/table không transactional hoặc code lấy hai connection khác nhau, khiến đơn hàng được tạo nhưng việc trừ tồn kho thất bại vẫn để lại hàng đầu tiên.

Một phép thử tối thiểu:

```java
@Test
void rollbackMustUndoSuccessfulInsert() throws SQLException {
    String code = "rollback-" + UUID.randomUUID();
    LocalDateTime time = LocalDateTime.of(2026, 11, 17, 10, 0);

    try (Connection c = dataSource().getConnection()) {
        c.setAutoCommit(false);
        try {
            insertCustomer(c, 10L, code, "Chưa commit",
                    new BigDecimal("9.0000"), null, time);
        } finally {
            c.rollback();
        }
    }

    // Connection mới: một bản ghi đã rollback không được tồn tại.
    try (Connection c = dataSource().getConnection();
         PreparedStatement ps = c.prepareStatement(
                 "SELECT COUNT(*) FROM contract_customer "
                         + "WHERE tenant_id = ? AND external_code = ?")) {
        ps.setLong(1, 10L);
        ps.setString(2, code);
        try (ResultSet rs = ps.executeQuery()) {
            assertTrue(rs.next());
            assertEquals(0L, rs.getLong(1));
        }
    }
}
```

**Lưu ý:** Test trên chứng minh rollback cho một `INSERT`; hợp đồng *atomicity nhiều bước* cần test hai hay nhiều câu SQL trên cùng `Connection` hoặc transaction manager, làm bước thứ hai thất bại rồi xác nhận **mọi** thay đổi của bước trước được hoàn tác.

Những điểm phải thử hoặc cấu hình rõ trước cutover:

- `autoCommit` ban đầu và hành vi khi `setAutoCommit(false)`; test không được tự giả định trạng thái kết nối từ pool.
- Khác biệt isolation (`READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`), phantom/nonrepeatable reads và deadlock theo DB; `setTransactionIsolation(...)` cần xác minh mức thực tế được áp dụng.
- Cơ chế savepoint (`setSavepoint`/`rollback(savepoint)`), nếu hệ thống có nested transaction.
- Hành vi sau `SQLException` bên trong transaction: PostgreSQL thường yêu cầu rollback sau lỗi SQL, trong khi DB khác có thể cho thực thi tiếp với điều kiện nhất định.
- Kết quả khi mất kết nối lúc `commit` **có thể không xác định**; cần idempotency để không tạo bản ghi trùng khi retry.
- Tính nguyên tử của DDL và migration không đồng nhất giữa các hệ quản trị, nên không giả định rollback sẽ xóa mọi bảng/index vừa tạo.

Khi dùng Spring, kiểm thử thêm `@Transactional`/`JdbcTemplate` với transaction manager và `DataSource` thực tế. Repository không tự `commit` hoặc đóng connection do framework sở hữu; **không dùng test JDBC thuần để kết luận transaction Spring đã được cấu hình đúng**.

## 10. SQL dialect, pagination và kiểu đặc thù: tách khác biệt, giữ kết quả

Một repository thường chứa những cú pháp không có tính khả chuyển tuyệt đối:

| Nhu cầu | PostgreSQL | MySQL | Hợp đồng cần kiểm |
| --- | --- | --- | --- |
| Chọn một trang | `LIMIT ? OFFSET ?` | `LIMIT ? OFFSET ?` (tùy driver và version) | Tổng hàng, thứ tự, trang tiếp chính xác |
| Lấy khóa mới sinh | `RETURNING id` hoặc `getGeneratedKeys` | `getGeneratedKeys`/identity mechanism | ID đọc lại được, không trùng |
| Upsert | `ON CONFLICT ... DO UPDATE` | `ON DUPLICATE KEY UPDATE` | Giá trị cập nhật và affected-row count theo hợp đồng |
| JSON | `json`/`jsonb` | `JSON` | Round-trip và phép truy vấn theo path cần thiết |
| UUID | `uuid` | `CHAR(36)`/`BINARY(16)` hoặc biểu diễn được chọn | Giá trị 128 bit đọc lại đúng |
| Thời điểm | `TIMESTAMP WITH TIME ZONE` | Thường cần quy tắc lưu UTC/kiểu riêng | Cùng instant, không nhất thiết cùng offset |
| Chuỗi không phân biệt hoa | `ILIKE` hoặc collation/phương án khác | `LIKE` có thể phụ thuộc collation | So sánh tên/email theo chính sách nghiệp vụ |

Ngay cả khi cú pháp giống nhau, **optimizer, kiểu dữ liệu, collation và trả update count** có thể khác. Ví dụ, thao tác UPSERT trên hai DB có thể báo số hàng ảnh hưởng khác nhau, dù hàng cuối cùng có dữ liệu tương đương. Test hợp đồng nên xác định nó quan tâm **trạng thái cuối** hay thật sự yêu cầu một update count cụ thể, rồi thiết kế DAO để dịch khác biệt ấy.

### Keyset pagination yêu cầu thứ tự duy nhất

```sql
-- Truy vấn minh họa trên hai DB hỗ trợ LIMIT ?.
SELECT id, occurred_at, display_name
FROM contract_customer
WHERE tenant_id = ?
ORDER BY occurred_at DESC, id DESC
LIMIT ?;

-- Trang tiếp theo: cursor từ (occurred_at, id) cuối trang trước.
SELECT id, occurred_at, display_name
FROM contract_customer
WHERE tenant_id = ?
  AND (occurred_at < ?
       OR (occurred_at = ? AND id < ?))
ORDER BY occurred_at DESC, id DESC
LIMIT ?;
```

Chỉ `ORDER BY occurred_at` không đủ ổn định nếu nhiều hàng trùng thời gian; thêm `id` làm khóa phá hòa. Các điều kiện cursor phải khớp **chiều sort, xử lý `NULL` và độ chính xác timestamp**. Kiểm thử bằng nhiều hàng trùng `occurred_at`, lấy từng trang size nhỏ và kiểm tra mỗi ID xuất hiện đúng một lần khi dữ liệu đứng yên.

Nếu DB mới thay đổi cách so sánh text trong khóa sort, cursor chứa giá trị chuỗi có thể thay đổi hành vi; không chỉ sửa cú pháp `LIMIT` rồi kết luận phân trang đã tương thích.

## 11. Các ca biên khó thường lộ ra khi đổi DB

### SQL NULL, chuỗi rỗng và getter nguyên thủy

`getInt(...)` trả `0` khi cột SQL `NULL`; phải gọi `wasNull()` ngay sau getter để phân biệt với giá trị `0` thật. Với `VARCHAR`, kiểm tra SQL `NULL` khác chuỗi `""`. Oracle có đặc tính riêng về chuỗi rỗng trong một số kiểu ký tự, nên một hợp đồng yêu cầu phân biệt cả hai cần được đánh giá **trước khi** chọn Oracle làm nền đích.

### Unicode và collation

Đừng chỉ test `"ABC"`. Hãy dùng `"Đà Nẵng 🌏"`, chuỗi có ký tự kết hợp như `"e\u0301"`, viết hoa/thường và chuỗi có dấu. Một DB có thể lưu lại chuỗi đúng nhưng áp quy tắc so sánh `UNIQUE` khác: kiểm tra **round-trip** và **ràng buộc so sánh** là hai test khác nhau.

### Decimal và overflow

Kiểm tra `BigDecimal("0.1000")`, số âm, số sát giới hạn `DECIMAL(18,4)` và số có quá 4 chữ số thập phân. Không dùng `double` làm oracle; xác định DB sẽ từ chối hay làm tròn khi vượt scale, và không chấp nhận silent rounding nếu nghiệp vụ yêu cầu từ chối.

### Timestamp, timezone và DST

`LocalDateTime` là giờ địa phương không có offset; `OffsetDateTime` là giá trị gắn offset và có thể chuyển sang `Instant`. Với cột lưu thời điểm tuyệt đối, kiểm tra `toInstant()`, không assert offset đọc lại luôn trùng offset ban đầu. Thử session timezone khác nhau, timezone JVM khác nhau và một ca DST nếu ứng dụng phục vụ vùng có DST.

### Kiểu nâng cao và LOB

UUID/JSON/enum/array/spatial type có thể đi qua `Types.OTHER` hoặc lớp riêng của driver. Với BLOB/CLOB, thử `setBinaryStream`/`getBinaryStream` và `setCharacterStream`/`getCharacterStream` trên tệp không quá lớn trước, rồi kiểm tra giới hạn và memory dưới tải. Không mặc định overload JDBC phổ biến trên driver cũ hoặc mỗi driver thực hiện streaming giống nhau.

### Batching và lỗi giữa lô

`executeBatch()` có thể trả `SUCCESS_NO_INFO`, `EXECUTE_FAILED` hoặc ném `BatchUpdateException` với số phần tử đã chạy tùy driver/chế độ. Test phần tử thứ hai vi phạm unique constraint phải xác nhận **trạng thái dữ liệu cuối sau commit/rollback**, thay vì chỉ so mảng update counts theo một DB. Nếu ứng dụng dùng generated keys theo batch, cần kiểm thử thứ tự và khả năng ghép khóa với từng bản ghi; không giả định thứ tự luôn được bảo đảm.

## 12. Tổ chức CI: một ma trận target, nhiều lớp kiểm tra

Để hạn chế rủi ro chuyển nền, pipeline nên chạy **từng DB thật**, cùng schema được tạo bằng migration riêng và cùng dữ liệu fixture có kiểm soát. Ví dụ:

```text
Source DB contract suite                 Target DB contract suite
PostgreSQL + pgjdbc                       MySQL + Connector/J
        |                                          |
        +----> migration/schema setup              |
        |                                          |
        +----> CRUD + null/unicode/decimal/time <---+
        +----> keys + constraints + SQLState   <---+
        +----> transaction + optimistic lock   <---+
        +----> pagination + concurrency        <---+
        +----> permissions + operational checks<---+
        |                                          |
       PASS?                                      PASS?
          \                                       /
           \-- So bất biến và đánh giá khác biệt --/
                           |
                  Quyết định cutover?
```

Đề xuất cấu trúc chạy:

1. **Build/lint/unit:** kiểm tra code Java và logic adapter thuần trong mọi pull request.
2. **Integration contract:** với mỗi thay đổi repository hoặc schema, chạy trên DB/driver mục tiêu, không dùng H2 để đại diện hoàn toàn cho sản phẩm khác.
3. **Cross-version:** thử ít nhất phiên bản DB/driver đang chạy và phiên bản sẽ triển khai; không chỉ tên sản phẩm.
4. **Concurrency/transaction:** thử có kiểm soát với hai connection, lock timeout và rollback; không để test deadlock treo CI.
5. **Performance contract:** trên dữ liệu và tải đại diện, so latency p95/p99, throughput, query plan, số hàng scan và connection wait. **Đúng chức năng nhưng chậm không kiểm soát được** cũng chưa đủ điều kiện chuyển.
6. **Security/operations:** dùng quyền runtime production-like; thử truy cập bị cấm, TLS, pooling, credential rotation và backup/restore ở môi trường kiểm thử thích hợp.

### Lưu ý về fixture và CI

- Mỗi target cần database/schema test **riêng biệt**. Không trỏ các biến `JDBC_TEST_URL` hoặc `MYSQL_TEST_URL` vào production; CI nên kiểm tra allowlist host/database.
- Migration thiết lập schema theo **đúng thứ tự** trước test; quyền tạo schema thuộc migration identity, không cấp cho account runtime.
- Dùng mã fixture duy nhất và rollback sau test. Với DB tự commit DDL hoặc tài nguyên không transactional, dọn schema ở bước setup/teardown riêng.
- Test liên quan tới thứ tự phải có `ORDER BY` ổn định; không đoán thứ tự các hàng chỉ theo thứ tự insert.
- Chạy các ca bất đồng bộ bằng đồng bộ hóa như `CountDownLatch`/`CyclicBarrier` và timeout, không trông chờ `Thread.sleep()` may mắn.
- Nếu test chạy nhiều worker song song, không dùng chung các ID, tên bảng tạm hoặc global setting có thể làm test ảnh hưởng nhau.
- Lưu **database product/version, driver/version, timezone, collation/isolation** cùng kết quả test để phân tích hồi quy.

## 13. Đặt điều kiện chuyển nền bằng cổng chất lượng rõ ràng

Không nên đưa ra quyết định từ một bảng “các bài test đa số xanh”. Hãy phân loại lỗi:

| Mức | Ví dụ | Quyết định |
| --- | --- | --- |
| **Blocker dữ liệu** | Mất số thập phân, Unicode sai, bỏ sót tenant, rollback không nguyên tử | Không cutover |
| **Blocker tương thích** | DAO không đọc được generated key, sai version conflict, unique constraint không đúng | Sửa adapter/schema và chạy lại |
| **Blocker vận hành** | Pool cạn ở tải dự kiến, migration không hoàn tất, thiếu kế hoạch khôi phục | Không cutover |
| **Khác biệt được phê duyệt** | Offset hiển thị khác nhưng cùng instant; ID không liên tiếp | Ghi nhận trong contract và test đúng ngữ nghĩa |
| **Cải tiến có thể làm sau** | Query chưa tối ưu ở màn hình không quan trọng nhưng vẫn trong giới hạn SLA | Chỉ chấp nhận nếu có tiêu chí và người chịu trách nhiệm |

**Ví dụ cổng trước cutover:** tất cả bài test bất biến bắt buộc PASS; dữ liệu đối chiếu trước/sau migration không mất/trùng; các negative test quyền và constraint đúng; throughput/latency trong giới hạn đã phê duyệt; backup, restore và kế hoạch quay lại đã được tập dượt. Các ngưỡng SLA và độ phủ cần được **dự án xác định từ nhu cầu thật**, không lấy một con số chung áp cho mọi hệ thống.

Không dùng `@Disabled` hoặc `Assumptions.assumeTrue(false)` chỉ để biến một lỗi tương thích thành “test bị bỏ qua”. Nếu một tính năng không được yêu cầu ở DB đích, phải sửa **hợp đồng và thiết kế nghiệp vụ** bằng quyết định có ghi nhận; nếu vẫn bắt buộc, kết quả là FAIL/BLOCKER.

### Đối chiếu dữ liệu khi chuyển thật

Kiểm thử hợp đồng trên fixture kiểm tra **cơ chế**, còn migration dữ liệu production cần thêm:

- Đếm số hàng theo bảng/tenant và đối chiếu khóa chính hoặc khóa nghiệp vụ.
- So checksum hoặc kết quả chuẩn hóa cho trường quan trọng; không chỉ so tổng số hàng.
- Kiểm tra ngoại lệ của chuyển đổi charset, precision/scale, timestamp và NULL.
- Thử tính đúng đắn khi dữ liệu đang được ghi đồng thời: thời điểm chốt snapshot, CDC/replication hoặc giai đoạn đóng băng ghi.
- Kiểm tra ràng buộc FK/UNIQUE, index, sequence/identity sau import, và kết quả của câu SQL nghiệp vụ trên **dữ liệu đã di chuyển**.
- Xác định điểm rollback/fallback và cách tránh ghi hai nơi gây dữ liệu lệch; không bật dual-write mà thiếu chính sách idempotency/đối soát.

Không ghi toàn bộ thông tin khách hàng thật vào artifact so sánh hoặc log CI. Dùng dữ liệu giả lập và chỉ tổng hợp/checksum đã được phê duyệt theo chính sách bảo vệ dữ liệu.

## 14. Bài thực hành: dựng cổng kiểm thử cho một cuộc chuyển DB

Tình huống: dịch vụ JDBC quản lý khách hàng đang chạy PostgreSQL và dự kiến hỗ trợ MySQL, nhưng phải giữ nguyên API nghiệp vụ.

1. **Viết hợp đồng:** chọn ít nhất C01–C08 ở phần 2. Ghi rõ Unicode phải giữ nguyên, `amount` chính xác 4 chữ số, `note` phân biệt `NULL`/`""`, optimistic update không ghi đè.
2. **Tạo schema hai nền:** áp dụng DDL PostgreSQL/MySQL ở phần 4 trên database test tách biệt; kiểm tra collation của `external_code` theo chính sách mã nghiệp vụ.
3. **Cấp nguồn dữ liệu:** tạo hai `DataSource` dùng credential test ít đặc quyền và driver đúng phiên bản; không hard-code password vào Java.
4. **Dùng cùng test class:** triển khai `dataSource()` và `isUniqueViolation()` cho từng target, chạy `generatedKeyAndValueRoundTrip` và `uniqueConstraintRejectsDuplicateWithinTenant`.
5. **Kiểm tra cập nhật stale:** chạy `staleVersionMustNotOverwriteLatestValue` rồi bổ sung kiểm thử hai connection đồng thời.
6. **Kiểm tra transaction:** chạy `rollbackMustUndoSuccessfulInsert`, sau đó mở rộng thành hai statement trong một transaction. Thử lỗi statement thứ hai, xác nhận cả hai thay đổi rollback.
7. **Kiểm tra khác biệt có chủ ý:** thêm test `note=""`, case-sensitive unique, timestamp qua các timezone, số vượt scale; ghi lại kết quả và quyết định schema/adapter.
8. **Kiểm tra phân trang:** chèn nhiều hàng cùng `occurred_at`, truy vấn từng trang và assert bộ ID đọc được không thiếu/trùng trong dữ liệu đứng yên.
9. **Chạy trên CI:** tổ chức ma trận DB/driver/version; chặn merge hoặc cutover nếu test bắt buộc fail. Ghi lại môi trường và mức độ lỗi.
10. **Lập kế hoạch di chuyển:** thử import dữ liệu giả lập, đối chiếu kết quả, xác định phương án quay lại và thời điểm chuyển traffic theo chính sách vận hành.

**Câu hỏi tự kiểm tra:**

- Vì sao đổi JDBC URL và driver mà code biên dịch thành công chưa chứng minh tương thích?
- Kiểm thử round-trip và kiểm thử ràng buộc `UNIQUE` giải quyết hai vấn đề khác nhau như thế nào?
- Tại sao không assert khóa `IDENTITY` phải liên tiếp sau rollback?
- Vì sao test unique violation phải xác nhận loại lỗi, không chỉ `assertThrows(SQLException.class)`?
- `executeUpdate()==0` khi cập nhật có điều kiện `version=?` chứng minh điều gì và chưa chứng minh điều gì?
- Tại sao `DATETIME(6)` và `TIMESTAMP WITH TIME ZONE` không thể kiểm thử bằng một assertion `LocalDateTime` giống nhau?
- Khi chuyển PostgreSQL sang MySQL, vì sao một test so `"Code"` với `"code"` có thể quan trọng dù dữ liệu Unicode round-trip đều đúng?
- Vì sao database in-memory không thể thay thế toàn bộ contract tests trên hệ quản trị đích?
- Một cuộc chuyển DB có đầy đủ functional tests xanh nhưng không có backup/rollback plan đã đủ điều kiện cutover chưa?

**Ghi nhớ:** JDBC tạo một **lớp API chung**, không bảo đảm hai hệ quản trị có cùng cú pháp và ngữ nghĩa. Trước khi đổi nền cơ sở dữ liệu, hãy định nghĩa **bất biến nghiệp vụ và dữ liệu**, chạy **cùng một bộ kiểm thử hợp đồng trên DB/driver/schema thật**, cô lập khác biệt SQL và kiểu dữ liệu bằng adapter có kiểm chứng, thử cả nhánh lỗi, transaction và concurrency, rồi chặn cutover nếu mất tính đúng đắn. Đánh giá thêm hiệu năng, quyền truy cập, cách đối chiếu dữ liệu và khả năng khôi phục: **một migration thành công là migration vẫn giữ đúng hợp đồng, không chỉ là migration chạy hết lệnh SQL**.

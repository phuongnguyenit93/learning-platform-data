# Phân biệt kiểm thử logic ánh xạ và kiểm thử tích hợp driver trong JDBC

Một phương thức Java đọc dữ liệu bằng JDBC thường làm **hai công việc khác nhau**: chuyển các giá trị từ `ResultSet` thành đối tượng Java, và giao tiếp thật với cơ sở dữ liệu qua `Connection`, `PreparedStatement`, JDBC driver cùng SQL. Hai công việc này có thể cùng nằm trong vài dòng code nhưng cần **hai loại kiểm thử với mục tiêu khác nhau**.

Ví dụ, một lớp repository đọc cột `credit_limit` kiểu `NUMERIC` thành `BigDecimal`, rồi đọc `referrer_id` kiểu `BIGINT NULL` thành `Long`. Kiểm thử đơn vị có thể xác nhận quy tắc “SQL NULL phải thành Java `null`” bằng dữ liệu giả. Nhưng kiểm thử đó **không chứng minh** driver thật sẽ chuyển đúng kiểu, câu SQL hợp lệ trên PostgreSQL, bảng tồn tại hay transaction rollback như mong đợi.

Bài thuộc chương **Kiểm thử JDBC** của module JDBC. Ta sẽ phân biệt rõ **kiểm thử logic ánh xạ (unit test)** với **kiểm thử tích hợp driver (integration test)**, thiết kế ranh giới kiểm thử, viết ví dụ Java và JUnit, lựa chọn dữ liệu/DB thử nghiệm, kiểm tra transaction, kiểu dữ liệu, SQL tham số hóa và các khác biệt chỉ xuất hiện khi chạy với driver thật.

## 1. Hai loại kiểm thử nhằm xác nhận hai hợp đồng

Một luồng truy cập dữ liệu điển hình:

```text
Service / nghiệp vụ
        |
        v
CustomerRepository
        |
        +---- SQL + PreparedStatement + Connection ----> JDBC driver
        |                                                   |
        |                                                   v
        |                                              DBMS thật
        |                                                   |
        +<--------------------------- ResultSet -------------+
        |
        v
CustomerRowMapper / hàm ánh xạ
        |
        v
Customer (đối tượng domain)
```

Ranh giới quan trọng:

- **Logic ánh xạ** quyết định đọc cột nào, hiểu `NULL` ra sao, tạo đối tượng với kiểu Java nào và kiểm tra quy tắc dữ liệu gì.
- **Tích hợp driver** quyết định SQL có thực thi được không, driver trả về giá trị/metadata nào, API JDBC nào được hỗ trợ, cách transaction hoạt động và tài nguyên có được đóng đúng không.

| Tiêu chí | Unit test logic ánh xạ | Integration test với JDBC driver thật |
|---|---|---|
| Mục tiêu | Chứng minh phép biến đổi dữ liệu/nhánh xử lý Java đúng | Chứng minh Java + driver + SQL + DBMS phối hợp đúng |
| Phụ thuộc database chạy thật | Không | Có |
| Đối tượng thử | Hàm thuần, mapper, đôi khi `ResultSet` mock | `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` thật |
| Tốc độ | Thường nhanh, chạy hàng nghìn test dễ dàng | Chậm hơn do khởi động DB, kết nối, DDL, I/O |
| Dễ mô phỏng giá trị biên | Rất dễ: `null`, số lớn, trạng thái lạ | Cần schema và fixture đại diện |
| Phát hiện SQL sai cú pháp/bind sai | Không bảo đảm | Có |
| Phát hiện khác biệt kiểu dữ liệu/driver | Không bảo đảm | Có |
| Phát hiện rollback/commit không như mong đợi | Không | Có, nếu test được thiết kế đúng |
| Độ tin cậy về production | Giới hạn ở logic đã mô phỏng | Cao hơn nếu DBMS/driver/cấu hình tương đương production |

**Không chọn một trong hai để loại bỏ loại kia.** Unit test giúp định vị nhanh lỗi mapper; integration test kiểm chứng ranh giới thật, nơi nhiều lỗi JDBC quan trọng phát sinh.

## 2. Vì sao mock `ResultSet` không thay được driver?

Giả sử có code:

```java
long referrerId = rs.getLong("referrer_id");
Long value = rs.wasNull() ? null : referrerId;
```

Với JDBC, `getLong(...)` trả `0` khi cột SQL là `NULL`; `wasNull()` cho biết **giá trị vừa đọc** có phải SQL NULL hay không. Unit test bằng mock có thể xác nhận mapper gọi `wasNull()` ngay sau `getLong(...)`.

Nhưng với mock, ta có thể cấu hình:

```java
when(rs.getLong("referrer_id")).thenReturn(0L);
when(rs.wasNull()).thenReturn(true);
```

Chính người viết test **đã quyết định** hai giá trị trả về. Test không truy cập một cột SQL `BIGINT NULL` thật, không xác nhận driver hỗ trợ `getLong("referrer_id")`, và không phát hiện column label sai trong SQL.

Hãy xem từng phần việc:

```text
Bài toán: SQL NULL -> Java null

Unit test:
  tạo tình huống rs.getLong(...) == 0 và rs.wasNull() == true
  -> mapper phải trả Long null
  -> xác nhận logic điều kiện và thứ tự đọc

Integration test:
  INSERT hàng có referrer_id IS NULL trên DB thật
  -> SELECT bằng PreparedStatement thật
  -> ResultSet thật trả giá trị và wasNull()
  -> repository trả Customer.referrerId() == null
  -> xác nhận cả driver, tên cột, SQL, schema và mapper
```

Unit test chứng minh **nếu đầu vào như đã giả lập, code Java xử lý đúng**. Integration test chứng minh **đầu vào thực từ DB đúng hợp đồng mà code kỳ vọng**.

## 3. Những phần nào nên tách ra để dễ kiểm thử?

Không cần tạo một framework riêng chỉ để test JDBC, nhưng nên tách hai trách nhiệm nhỏ:

1. `CustomerMapping`: chuyển dữ liệu đã đọc thành `Customer`, bao gồm các quy tắc validation.
2. `CustomerRepository`: giữ SQL, lấy connection, bind tham số, đóng tài nguyên và gọi mapping.

Cách tách này giúp viết unit test **không có DB** cho quy tắc thuần, và viết integration test cho **toàn tuyến** JDBC.

Giả sử schema thử nghiệm là:

```sql
CREATE TABLE customers (
    id          BIGINT PRIMARY KEY,
    full_name   VARCHAR(100) NOT NULL,
    credit_limit NUMERIC(14, 2) NOT NULL
        CHECK (credit_limit >= 0),
    referrer_id BIGINT NULL
);
```

Hợp đồng ánh xạ:

| Cột SQL | Kiểu trong DB mẫu | Trường Java | Lưu ý kiểm thử |
|---|---|---|---|
| `id` | `BIGINT NOT NULL` | `long id` | Khóa chính và giới hạn số nguyên |
| `full_name` | `VARCHAR(100) NOT NULL` | `String fullName` | Unicode, chuỗi rỗng, khác `NULL` |
| `credit_limit` | `NUMERIC(14,2) NOT NULL` | `BigDecimal creditLimit` | Precision, scale, không dùng `double` |
| `referrer_id` | `BIGINT NULL` | `Long referrerId` | Phân biệt SQL NULL với giá trị 0 |

### 3.1. Đối tượng domain

Ví dụ dùng Java **record** (Java 16+, phù hợp với Java 17 trở lên):

```java
import java.math.BigDecimal;
import java.util.Objects;

public record Customer(
        long id,
        String fullName,
        BigDecimal creditLimit,
        Long referrerId) {

    public Customer {
        if (id <= 0) {
            throw new IllegalArgumentException("id phải dương");
        }
        if (fullName == null || fullName.isBlank()) {
            throw new IllegalArgumentException("Thiếu tên khách hàng");
        }
        Objects.requireNonNull(creditLimit, "creditLimit");
        if (creditLimit.signum() < 0) {
            throw new IllegalArgumentException(
                    "Hạn mức tín dụng không được âm");
        }
    }
}
```

Validation trong constructor là **logic Java**, nên không cần database để kiểm thử. Ràng buộc `CHECK` ở DB lại là **hợp đồng database** phải được xác minh riêng. Cả hai có thể bảo vệ cùng bất biến nhưng phát lỗi ở những tầng khác nhau.

### 3.2. Mapper: một hàm thuần và một lớp trích xuất `ResultSet`

```java
import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class CustomerMapping {
    private CustomerMapping() {}

    // Phần thuần: không phụ thuộc Connection, ResultSet hay driver.
    public static Customer toDomain(
            long id, String name, BigDecimal credit,
            Long referrerId) {

        String normalized = name == null ? null : name.trim();
        return new Customer(id, normalized, credit, referrerId);
    }

    // Phần biên JDBC: đọc từng cột từ ResultSet.
    public static Customer fromResultSet(ResultSet rs)
            throws SQLException {

        long id = rs.getLong("id");
        String name = rs.getString("full_name");
        BigDecimal credit = rs.getBigDecimal("credit_limit");

        long rawReferrerId = rs.getLong("referrer_id");
        // Phải gọi ngay sau getLong("referrer_id").
        Long referrerId = rs.wasNull() ? null : rawReferrerId;

        return toDomain(id, name, credit, referrerId);
    }
}
```

Ta có **hai loại quy tắc** để test:

- `toDomain(...)`: trim tên, cấm hạn mức âm, giữ chính xác `BigDecimal` và `null`.
- `fromResultSet(...)`: dùng đúng column label, API getter, thứ tự `wasNull()` và chuyển ngoại lệ JDBC lên caller.

Nếu `fromResultSet(...)` đọc sai tên cột, mock vẫn có thể được cấu hình để “đồng ý” với sai sót ấy. Integration test thực mới chứng minh query thật trả `full_name` và các cột khác theo contract.

## 4. Unit test logic ánh xạ thuần với JUnit

Khi một hàm không cần `DataSource`, không khởi tạo database chỉ để kiểm tra nó.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class CustomerMappingUnitTest {

    @Test
    void trimsNameAndPreservesNullReferrer() {
        Customer customer = CustomerMapping.toDomain(
                7L, "  Mai An  ",
                new BigDecimal("123.40"), null);

        assertEquals(7L, customer.id());
        assertEquals("Mai An", customer.fullName());
        assertEquals(new BigDecimal("123.40"),
                customer.creditLimit());
        assertNull(customer.referrerId());
    }

    @Test
    void rejectsNegativeCreditLimit() {
        assertThrows(IllegalArgumentException.class, () ->
                CustomerMapping.toDomain(
                        8L, "Binh",
                        new BigDecimal("-0.01"), null));
    }

    @Test
    void keepsZeroDifferentFromNull() {
        Customer zero = CustomerMapping.toDomain(
                9L, "Lan", BigDecimal.ZERO, 0L);

        assertEquals(Long.valueOf(0L), zero.referrerId());
    }

    @Test
    void requiresNameAfterNormalization() {
        assertThrows(IllegalArgumentException.class, () ->
                CustomerMapping.toDomain(
                        10L, "   ", BigDecimal.ZERO, null));
    }
}
```

Các test này nhanh, xác định rõ hành vi và không phụ thuộc trạng thái database. Chúng **không** kiểm tra `SQL SELECT`, `PreparedStatement`, transaction hoặc JDBC driver.

Lưu ý: ví dụ giữ giá trị `referrerId=0` để phân biệt với `null` về logic Java; nếu schema thật có khóa ngoại đến khách hàng thì một giá trị `0` có thể không hợp lệ. Quy tắc nghiệp vụ và ràng buộc DB cần thống nhất trong thiết kế thật.

## 5. Unit test phần trích xuất `ResultSet` bằng mock

Có thể dùng **Mockito** để kiểm tra lớp biên đọc `ResultSet` mà không có database. Mockito là **thư viện test ngoài JDK**, không phải API JDBC; cần cấu hình dependency test tương ứng.

```java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;

class CustomerResultSetMapperTest {

    @Test
    void mapsSqlNullFromMockResultSet() throws SQLException {
        ResultSet rs = mock(ResultSet.class);

        when(rs.getLong("id")).thenReturn(51L);
        when(rs.getString("full_name")).thenReturn("  Hoa  ");
        when(rs.getBigDecimal("credit_limit"))
                .thenReturn(new BigDecimal("500.00"));

        when(rs.getLong("referrer_id")).thenReturn(0L);
        when(rs.wasNull()).thenReturn(true);

        Customer actual = CustomerMapping.fromResultSet(rs);

        assertEquals(51L, actual.id());
        assertEquals("Hoa", actual.fullName());
        assertEquals(new BigDecimal("500.00"),
                actual.creditLimit());
        assertNull(actual.referrerId());

        // Xác minh mapper kiểm tra NULL ngay sau lần đọc
        // giá trị referrer_id.
        InOrder order = inOrder(rs);
        order.verify(rs).getLong("referrer_id");
        order.verify(rs).wasNull();
    }

    @Test
    void mapsNonNullReferrer() throws SQLException {
        ResultSet rs = mock(ResultSet.class);

        when(rs.getLong("id")).thenReturn(52L);
        when(rs.getString("full_name")).thenReturn("Nam");
        when(rs.getBigDecimal("credit_limit"))
                .thenReturn(new BigDecimal("0.00"));
        when(rs.getLong("referrer_id")).thenReturn(7L);
        when(rs.wasNull()).thenReturn(false);

        Customer actual = CustomerMapping.fromResultSet(rs);

        assertEquals(Long.valueOf(7L), actual.referrerId());
    }

    @Test
    void propagatesJdbcReadFailure() throws SQLException {
        ResultSet rs = mock(ResultSet.class);

        when(rs.getLong("id")).thenReturn(53L);
        when(rs.getString("full_name")).thenReturn("Lan");
        when(rs.getBigDecimal("credit_limit"))
                .thenThrow(new SQLException("Lỗi đọc cột"));

        assertThrows(SQLException.class,
                () -> CustomerMapping.fromResultSet(rs));
    }
}
```

**Điểm test có ý nghĩa:** ta kiểm tra chính xác việc mapper dùng `wasNull()` để phân biệt `0` và `NULL`. Với `getLong(...)`, kiểm tra quá muộn sẽ không còn phản ánh cột cần xét, vì `wasNull()` chỉ báo trạng thái lần đọc gần nhất.

**Nhưng mock có giới hạn rõ ràng:**

- Không có SQL thật và không có schema thật.
- Không kiểm chứng `ResultSetMetaData`, kiểu JDBC, precision/scale hay encoding.
- Không biết `getBigDecimal("credit_limit")` có được driver hỗ trợ cho cột thật hay không.
- Không phát hiện cú pháp SQL khác biệt giữa PostgreSQL, MySQL, Oracle hoặc SQL Server.
- Không kiểm tra connection pool, commit, rollback, khóa hay timeout.

Đừng quá phụ thuộc các assert như `verify(ps).setLong(1, id)` để kết luận repository đúng. Những tương tác mock chỉ chứng minh **lời gọi Java**, không chứng minh SQL đã chạy an toàn hoặc tạo ra dữ liệu đúng.

## 6. Repository thật: ranh giới cần integration test

Để thấy cả tuyến JDBC, tạo repository thực sự dùng `DataSource`. Nó giữ SQL tham số hóa, đóng tài nguyên bằng `try-with-resources` và gọi lại `CustomerMapping.fromResultSet(...)`.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Objects;
import java.util.Optional;

public final class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(
                dataSource, "dataSource");
    }

    public void insert(Customer customer) throws SQLException {
        String sql = "INSERT INTO customers "
                + "(id, full_name, credit_limit, referrer_id) "
                + "VALUES (?, ?, ?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setLong(1, customer.id());
            ps.setString(2, customer.fullName());
            ps.setBigDecimal(3, customer.creditLimit());

            if (customer.referrerId() == null) {
                ps.setNull(4, Types.BIGINT);
            } else {
                ps.setLong(4, customer.referrerId());
            }

            if (ps.executeUpdate() != 1) {
                throw new SQLException("Không INSERT đúng một khách hàng");
            }
        }
    }

    public Optional<Customer> findById(long customerId)
            throws SQLException {

        String sql =
                "SELECT id, full_name, credit_limit, referrer_id "
                + "FROM customers WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setLong(1, customerId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                Customer customer =
                        CustomerMapping.fromResultSet(rs);

                if (rs.next()) {
                    throw new SQLException(
                            "Truy vấn khóa chính trả nhiều hơn một hàng");
                }
                return Optional.of(customer);
            }
        }
    }

    public Optional<Customer> findByName(String name)
            throws SQLException {

        String sql =
                "SELECT id, full_name, credit_limit, referrer_id "
                + "FROM customers WHERE full_name = ? ORDER BY id";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setString(1, name);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(
                        CustomerMapping.fromResultSet(rs));
            }
        }
    }

    public int changeCreditLimit(long id, BigDecimal value)
            throws SQLException {

        String sql = "UPDATE customers SET credit_limit = ? "
                + "WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setBigDecimal(1, value);
            ps.setLong(2, id);
            return ps.executeUpdate();
        }
    }
}
```

**Phạm vi transaction của ví dụ:** các hàm này thực hiện **một câu SQL trong mỗi phương thức**, dùng chế độ auto-commit mặc định của connection được cấp. Trong ứng dụng có transaction nhiều bước, cần để tầng service làm chủ **một connection chung**, tắt auto-commit và quản lý commit/rollback; không ghép nhiều hàm mở connection riêng rồi coi chúng là một transaction nguyên tử.

Repository trên có những điều unit test thuần không kiểm tra được: câu SQL, thứ tự bind `?`, kiểu tham số `BIGINT`, `NUMERIC`, kết quả `executeUpdate()`, giá trị `ResultSet` từ driver, ràng buộc DB và việc đóng connection thật.

## 7. Integration test driver là gì?

**Kiểm thử tích hợp driver** phải đi qua đường JDBC thật:

```text
JUnit test
  |
  +-> DataSource / DriverManager
       |
       +-> JDBC driver thật
            |
            +-> DBMS chạy thật
                 |
                 +-> schema, constraint, transaction, types
```

Test cần sử dụng **cùng họ DBMS** với mục tiêu triển khai, nếu đang kiểm chứng đặc tính riêng của DB đó. Ví dụ code ứng dụng dành cho PostgreSQL thì nên có ít nhất một tập integration test dùng PostgreSQL và **pgJDBC**, thay vì chỉ H2 chạy chế độ tương thích PostgreSQL.

Một database in-memory vẫn có thể có ích cho test repository nhanh hoặc thử luồng CRUD cơ bản, nhưng **nó không thay thế** việc kiểm tra driver, SQL dialect, kiểu `TIMESTAMPTZ`, ràng buộc/locking và transaction trên DBMS đích.

### 7.1. Các lựa chọn tạo database cho test

| Cách chạy | Ưu điểm | Giới hạn |
|---|---|---|
| DBMS cài trong môi trường CI/lab | Gần với hệ thống thật, tự quản lý cấu hình sâu | Cần quản trị vòng đời, isolation, dữ liệu |
| Container database tạm thời | Có thể khởi tạo môi trường sạch, dễ cô lập mỗi suite | Cần Docker/container runtime và image phù hợp |
| Database thử nghiệm dùng chung | Có dữ liệu/schema lớn, thuận tiện benchmark | Nguy cơ test can thiệp lẫn nhau; cần schema, user, cleanup |
| H2/SQLite/fake driver | Nhanh, ít hạ tầng | **Không chứng minh** hành vi của PostgreSQL/MySQL/Oracle driver thật |

**Testcontainers** là một lựa chọn dùng container database trong integration test Java, nhưng nó là thư viện bên ngoài JDK và cần container runtime hoạt động. Ví dụ tiếp theo dùng PostgreSQL + Testcontainers + JUnit Jupiter, nên cần các test dependencies tương ứng và driver PostgreSQL trong classpath. Không cố định version dependency ở đây vì phải chọn bộ version tương thích với dự án.

## 8. Ví dụ integration test với PostgreSQL, Testcontainers và JUnit 5

Ví dụ dùng container PostgreSQL 16 trong một môi trường thử nghiệm riêng. Tag image chỉ mang tính minh họa; dự án cần chốt phiên bản gần với production và theo dõi cập nhật bảo mật.

### 8.1. Khởi tạo container và schema

```java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.postgresql.ds.PGSimpleDataSource;

@Testcontainers
class CustomerRepositoryPgIT {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    private DataSource dataSource;
    private CustomerRepository repository;

    @BeforeEach
    void setUp() throws SQLException {
        PGSimpleDataSource pgDataSource = new PGSimpleDataSource();
        pgDataSource.setURL(postgres.getJdbcUrl());
        pgDataSource.setUser(postgres.getUsername());
        pgDataSource.setPassword(postgres.getPassword());

        dataSource = pgDataSource;
        repository = new CustomerRepository(dataSource);

        // Schema fixture độc lập cho từng test trong lớp này.
        try (Connection connection = dataSource.getConnection();
             Statement st = connection.createStatement()) {

            st.execute("DROP TABLE IF EXISTS customers");
            st.execute("""
                CREATE TABLE customers (
                    id BIGINT PRIMARY KEY,
                    full_name VARCHAR(100) NOT NULL,
                    credit_limit NUMERIC(14, 2) NOT NULL
                        CHECK (credit_limit >= 0),
                    referrer_id BIGINT NULL
                )
                """);
        }
    }

    @Test
    void mapsNullFromRealPostgresResultSet()
            throws SQLException {

        repository.insert(new Customer(
                101L, "Mai An",
                new BigDecimal("123.40"), null));

        Customer actual = repository.findById(101L)
                .orElseThrow();

        assertEquals(101L, actual.id());
        assertEquals("Mai An", actual.fullName());
        assertEquals(
                new BigDecimal("123.40"), actual.creditLimit());
        assertNull(actual.referrerId());
    }

    @Test
    void mapsNonNullReferrerAndDecimalScale()
            throws SQLException {

        repository.insert(new Customer(
                102L, "Lan",
                new BigDecimal("50.00"), 101L));

        Customer actual = repository.findById(102L)
                .orElseThrow();

        assertEquals(Long.valueOf(101L), actual.referrerId());
        assertEquals(0,
                new BigDecimal("50.00")
                        .compareTo(actual.creditLimit()));
    }

    @Test
    void parameterizedSearchTreatsInputAsData()
            throws SQLException {

        repository.insert(new Customer(
                103L, "Binh", new BigDecimal("0.00"), null));

        String maliciousLookingName = "' OR 1=1 --";

        assertTrue(repository
                .findByName(maliciousLookingName)
                .isEmpty());

        assertTrue(repository.findByName("Binh").isPresent());
    }

    @Test
    void databaseConstraintRejectsNegativeCredit()
            throws SQLException {

        repository.insert(new Customer(
                104L, "Chi", BigDecimal.ZERO, null));

        SQLException error = assertThrows(
                SQLException.class,
                () -> repository.changeCreditLimit(
                        104L, new BigDecimal("-1.00")));

        assertNotNull(error.getSQLState());
        assertEquals(
                BigDecimal.ZERO.setScale(2),
                repository.findById(104L)
                        .orElseThrow().creditLimit());
    }
}
```

Các đoạn trên được đặt trong cùng lớp `CustomerRepositoryPgIT`; chúng dựa vào lớp `Customer`, `CustomerMapping` và `CustomerRepository` ở phần trước. Text block SQL `"""` yêu cầu Java 15+; vì ví dụ dùng record, lựa chọn Java 17+ là phù hợp.

**Điểm được xác minh thật:**

- PostgreSQL chấp nhận `CREATE TABLE` với `NUMERIC(14,2)` và `CHECK`.
- pgJDBC map `NUMERIC` sang `BigDecimal` và đọc giá trị từ `ResultSet`.
- Giá trị SQL `NULL` của `referrer_id` đi qua `getLong` + `wasNull` thành `null`.
- `PreparedStatement.setNull(4, Types.BIGINT)` thực sự ghi một giá trị NULL.
- SQL có dấu `?` xử lý chuỗi chứa ký tự giống cú pháp SQL như **dữ liệu**, không phải phần lệnh SQL.
- Ràng buộc `CHECK` được DB thực thi; lỗi `SQLException` xuất hiện thực, không do mock tạo sẵn.
- Try-with-resources đóng statement/result set/connection thật trong các nhánh thực thi.

**Giới hạn của ví dụ:** `PGSimpleDataSource` tạo connection theo cơ chế driver, **không phải connection pool sản xuất**. Đoạn test này kiểm tra driver, SQL và repository. Nếu hệ thống dùng HikariCP hoặc pool khác, cần bổ sung bộ kiểm thử với **pool thật và cấu hình thật** để xác nhận mượn/trả connection, reset trạng thái và xử lý lỗi connection.

### 8.2. Vì sao setup dùng database sạch?

Integration test có thể thất bại ngẫu nhiên nếu kế thừa dữ liệu từ test khác. Ở ví dụ này, `@BeforeEach` xóa và tạo lại bảng trong container dành riêng cho lớp test.

Trong dự án lớn có nhiều test song song, **không dùng chung một schema rồi `DROP TABLE` cùng lúc**. Thay vào đó, có thể:

- Dùng schema riêng cho mỗi test hoặc class.
- Dùng container/database độc lập theo nhóm test.
- Chạy migration rồi làm sạch fixture theo thứ tự được kiểm soát.
- Bật parallel execution chỉ khi chiến lược isolation đã đảm bảo.

Chạy migration thật bằng công cụ dự án trong integration test thường tốt hơn tự chép một `CREATE TABLE` khác production. Ví dụ ở đây dùng DDL ngắn để bài học **tự chứa** và dễ quan sát.

## 9. Unit test nhanh khác integration test ở cách xác định kỳ vọng

Giả sử một unit test viết:

```java
when(rs.getBigDecimal("credit_limit"))
        .thenReturn(new BigDecimal("125.50"));
assertEquals(new BigDecimal("125.50"),
        CustomerMapping.fromResultSet(rs).creditLimit());
```

Kết quả này chỉ cho biết mapper trả đúng object mà mock cung cấp. Nó **không chứng minh** DB lưu `125.50` hay driver làm tròn đúng hai chữ số thập phân.

Trong integration test, giá trị kỳ vọng phải đến từ **hợp đồng dữ liệu**, không phải từ chính hàm đang được test:

```java
repository.insert(new Customer(
        200L, "Thu", new BigDecimal("125.50"), null));

Customer actual = repository.findById(200L).orElseThrow();

assertEquals(0, new BigDecimal("125.50")
        .compareTo(actual.creditLimit()));
```

Đoạn trên là mã trong phương thức test có `repository` đã được cấu hình như phần trước. Nó xác minh hành trình ghi/đọc thật, nhưng nếu cả hai phương thức cùng chứa một lỗi có tính đối xứng, một test round-trip có thể vẫn pass. Khi cần tin cậy hơn, **kiểm tra bằng một truy vấn SQL độc lập** hoặc fixture do test tạo trực tiếp:

```java
try (Connection c = dataSource.getConnection();
     Statement st = c.createStatement();
     ResultSet rs = st.executeQuery(
             "SELECT credit_limit FROM customers WHERE id = 200")) {

    assertTrue(rs.next());
    assertEquals(0, new BigDecimal("125.50")
            .compareTo(rs.getBigDecimal(1)));
}
```

Đó là lý do integration test nên có các assertion **độc lập tương đối với code sản xuất** và không chỉ xác nhận “ghi bằng hàm A rồi đọc bằng chính hàm A thấy cùng một đối tượng”.

## 10. Kiểm thử NULL, số tiền và ngày giờ: nhóm lỗi chỉ rõ khi có driver

### 10.1. `NULL` và primitive

Với `ResultSet.getLong(...)`:

```java
long value = rs.getLong("referrer_id");
Long referrer = rs.wasNull() ? null : value;
```

Một test cần có ít nhất ba trường hợp:

1. SQL `NULL` → Java `null`.
2. SQL `0` → Java `0L`, **không phải null**.
3. SQL số dương → Java giá trị tương ứng.

Nếu bảng có khóa ngoại làm `0` không hợp lệ, hãy kiểm tra trường hợp 0 trên schema/cột khác cho phép hoặc trong unit test thuần; đừng sửa dữ liệu test bằng cách vô hiệu toàn bộ constraint production.

API `rs.getObject("referrer_id", Long.class)` có thể thuận tiện nếu driver hỗ trợ đúng typed getter, nhưng điều đó cũng cần **integration test với driver cụ thể**. Không suy rằng mọi kiểu chuyển đổi `getObject(..., Class<T>)` đều được tất cả driver hỗ trợ.

### 10.2. `BigDecimal` và precision/scale

Với `NUMERIC(14,2)`, test nên xét:

- Giá trị `0.00`.
- Giá trị có hai số thập phân, ví dụ `123.40`.
- Giá trị chạm giới hạn precision.
- Giá trị nhiều chữ số thập phân hơn cột lưu được.
- Giá trị âm nếu có ràng buộc `CHECK`.

`BigDecimal.equals(...)` xét cả scale, trong khi `compareTo(...)` so sánh giá trị số. Đối với quy tắc số tiền, chọn assertion đúng hợp đồng: test scale khi API **cam kết scale**, hoặc dùng `compareTo` khi chỉ yêu cầu giá trị số bằng nhau.

Không dùng `double` để kiểm tra chính xác tiền tệ nhị phân; sai số biểu diễn có thể che lỗi ánh xạ.

### 10.3. Kiểu ngày giờ và múi giờ

Giả sử PostgreSQL có cột:

```sql
CREATE TABLE event_times (
    id BIGINT PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL
);
```

Với JDBC 4.2 và driver hỗ trợ, có thể ghi/đọc `OffsetDateTime`:

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

Instant expected = Instant.parse("2026-11-15T09:30:00Z");
OffsetDateTime toStore =
        OffsetDateTime.ofInstant(expected, ZoneOffset.UTC);

try (Connection c = dataSource.getConnection()) {
    try (PreparedStatement ps = c.prepareStatement(
            "INSERT INTO event_times(id, occurred_at) VALUES (?, ?)")) {
        ps.setLong(1, 1L);
        ps.setObject(2, toStore);
        ps.executeUpdate();
    }

    try (PreparedStatement ps = c.prepareStatement(
            "SELECT occurred_at FROM event_times WHERE id = ?")) {
        ps.setLong(1, 1L);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("Không thấy sự kiện");
            }

            OffsetDateTime actual =
                    rs.getObject(1, OffsetDateTime.class);

            // Với timestamp đã chọn ở độ chính xác giây,
            // PostgreSQL không cần làm tròn phần nano.
            assertEquals(expected, actual.toInstant());
        }
    }
}
```

Đoạn minh họa nằm trong test đã có `DataSource dataSource` và import `assertEquals` của JUnit. Test tương ứng phải tạo bảng `event_times` trong fixture độc lập.

**Vì sao so `Instant` thay vì `OffsetDateTime.equals(...)`?** PostgreSQL `TIMESTAMPTZ` lưu thời điểm, không lưu nguyên offset múi giờ đầu vào. Driver có thể trả `OffsetDateTime` với offset khác nhưng vẫn cùng một instant. Nếu input có nanosecond vượt precision hỗ trợ (PostgreSQL thường lưu microsecond), test phải xác định quy tắc làm tròn/cắt cụ thể thay vì assert giữ mọi nano nguyên vẹn.

Cần thử trên JVM có timezone khác và DB session timezone khác nếu sản phẩm chạy xuyên vùng; test in-memory hoặc mock không chứng minh được ngữ nghĩa DB này.

## 11. Kiểm thử giao dịch: phải dùng connection thật

Một mock có thể xác nhận:

```java
verify(connection).rollback();
```

Nhưng assertion này **chỉ chứng minh hàm `rollback()` đã được gọi**, không chứng minh những cập nhật trước đó thực sự bị DBMS hoàn tác. Một integration test transaction phải quan sát trạng thái dữ liệu **sau khi transaction kết thúc** trên connection độc lập.

### 11.1. Test rollback thật

Sau khi tạo bảng `customers` như phần trước:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import org.junit.jupiter.api.Test;

@Test
void rollbackDiscardsUncommittedInsert() throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement ps = connection.prepareStatement(
                    "INSERT INTO customers "
                    + "(id, full_name, credit_limit, referrer_id) "
                    + "VALUES (?, ?, ?, ?)")) {

                ps.setLong(1, 301L);
                ps.setString(2, "Rollback Demo");
                ps.setBigDecimal(3, BigDecimal.ZERO);
                ps.setNull(4, Types.BIGINT);
                assertEquals(1, ps.executeUpdate());
            }

            connection.rollback();

        } catch (SQLException | RuntimeException failure) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        }
    }

    // Repository mở connection KHÁC sau rollback.
    assertTrue(repository.findById(301L).isEmpty());
}
```

Đây là một test method đặt bên trong lớp `CustomerRepositoryPgIT` đã khai báo `dataSource` và `repository`, không phải một chương trình Java độc lập.

Điểm chính:

- `executeUpdate() == 1` chỉ nói rằng SQL đã tác động một hàng trong transaction, **không phải đã commit**.
- `rollback()` được gọi trên đúng `Connection` đang thực hiện `INSERT`.
- Sau khi đóng connection, truy vấn qua repository dùng một connection mới và **không thấy bản ghi**.

Để thử transaction nhiều bước, hãy cập nhật hai bảng/đối tượng trong cùng transaction, cố tình gây lỗi giữa chừng và xác nhận tất cả thay đổi chưa commit bị hủy. Từng bước cần chạy trên **cùng connection**; nếu DAO tự mở connection mới cho mỗi câu SQL, test phải phát hiện sự vi phạm biên transaction.

### 11.2. Test ràng buộc dữ liệu và `SQLException`

Driver thật cho phép quan sát SQLSTATE:

```java
SQLException error = assertThrows(
        SQLException.class,
        () -> repository.insert(new Customer(
                101L, "Trung",
                new BigDecimal("20.00"), null)));

// Phần fixture phải bảo đảm ID 101 đã tồn tại trước đó.
System.out.println("SQLState: " + error.getSQLState());
System.out.println("Vendor code: " + error.getErrorCode());
```

Trên PostgreSQL, một lỗi unique violation thường có SQLSTATE `23505`, nhưng không nên viết assertion sử dụng mã này cho MySQL/Oracle hay cho mọi loại lỗi. Nếu test có chủ đích khóa hành vi PostgreSQL, có thể assert mã được DBMS công bố; lưu ý thông điệp lỗi có thể thay đổi theo version và ngôn ngữ.

## 12. Kiểm thử SQL tham số hóa khác kiểm thử chuỗi đầu vào

Khi dùng `PreparedStatement`:

```java
String sql = "SELECT id FROM customers WHERE full_name = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "' OR 1=1 --");
    try (ResultSet rs = ps.executeQuery()) {
        assertFalse(rs.next());
    }
}
```

Đoạn test chạy trên DB thật đã có ít nhất một hàng với tên khác payload. Nó chứng minh đường query được viết không coi payload như SQL syntax. Tuy nhiên, **một test payload duy nhất không chứng minh mọi đường SQL của ứng dụng không có injection**.

Cần kiểm tra cả:

- Bind đúng thứ tự tham số, đúng kiểu dữ liệu.
- `NULL` được gửi đúng qua `setNull` hoặc API tương đương.
- Không nối trực tiếp giá trị người dùng vào SQL.
- Tên bảng/cột động (**identifier**) được giới hạn bằng allowlist và quote đúng; placeholder `?` **không dùng để bind tên bảng**.
- SQL động trong stored procedure cũng phải an toàn, vì chỉ gọi `CallableStatement` chưa loại bỏ injection trong routine.

Mock `PreparedStatement` thường chỉ ghi lại lời gọi `setString`; integration test mới chứng minh driver truyền giá trị an toàn tới DB theo giao thức thực.

## 13. Cần kiểm chứng những khác biệt driver nào?

Một số tính năng JDBC được định nghĩa chung nhưng có khác biệt đáng kể giữa các driver/DBMS:

| Chủ đề | Unit test có thể kiểm tra | Integration test bắt buộc nếu dùng tính năng |
|---|---|---|
| `BigDecimal` | Phép tính/validation với giá trị cho trước | Precision/scale từ `NUMERIC/DECIMAL` thực |
| `NULL` và primitive getter | Gọi `wasNull()` đúng logic | Getter trả gì khi cột DB thật là NULL |
| `OffsetDateTime`/`LocalDateTime` | Quy tắc đổi timezone trong Java | `TIMESTAMPTZ`, `TIMESTAMP`, precision và DB session timezone |
| `PreparedStatement` | Lời gọi bind có đúng index? | SQL có compile/execute và dùng kiểu bind đúng không |
| `executeBatch()` | Logic chia chunk và xử lý count giả | Partial success, `BatchUpdateException`, update counts |
| `getGeneratedKeys()` | Ứng dụng đọc kết quả giả hợp lệ | Driver trả keys, thứ tự, độ đầy đủ khi batch |
| `ResultSet` scroll/updatable | Logic chọn type/concurrency | Driver hỗ trợ, query có updatable không |
| `CallableStatement` + `REF_CURSOR` | Luồng mapping từ cursor giả | Kiểu OUT, khả năng driver, vòng đời cursor |
| Commit/rollback/savepoint | Chọn nhánh code, phát lời gọi thích hợp | DB thực sự commit/hủy và giữ isolation đúng |
| Lock/deadlock/timeout | Retry policy, tính toán backoff | SQLSTATE, thời điểm timeout, trạng thái transaction |
| Connection pool | Cách gọi `close()` | Reset state, reuse physical connection, eviction |
| Metadata | Cách xây pattern và escape từ giá trị cho trước | `getSearchStringEscape()`, identifier case, catalog/schema thực |

Đây không phải lý do làm integration test cho **mọi nhánh Java nhỏ**. Hãy dùng unit test cho nhánh quyết định thuần, còn integration test tập trung vào **giao kèo với driver và DBMS** mà mock không thể chứng minh.

### Ví dụ: `ResultSet.TYPE_SCROLL_INSENSITIVE`

Một unit test có thể xác nhận code yêu cầu:

```java
connection.prepareStatement(
        sql,
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY);
```

Nhưng chỉ test trên driver thật mới biết `rs.getType()` là gì sau `executeQuery()`, `rs.previous()` có hoạt động hay driver từ chối/downgrade. `DatabaseMetaData.supportsResultSetType(...)` cung cấp khả năng tổng quát; vẫn cần xác nhận `ResultSet` của truy vấn cụ thể.

## 14. Mock `DataSource` phù hợp khi nào?

Không phải mọi test dùng mock JDBC đều vô ích. Ví dụ service có nhánh:

```text
Nếu mã khách hàng không hợp lệ -> không gọi repository
Nếu hợp lệ -> gọi repository.findById(...)
Nếu không tìm thấy -> trả NOT_FOUND
Nếu tìm thấy -> áp chính sách nghiệp vụ
```

Trong unit test service, nên mock **interface repository** hơn là dựng toàn bộ chuỗi `DataSource → Connection → PreparedStatement → ResultSet`. Khi mock quá sâu vào JDBC, test thường trở nên giòn: đổi implementation từ `getObject(...)` sang `getBigDecimal(...)` làm test hỏng dù hành vi nghiệp vụ không thay đổi.

Mock `DataSource`, `Connection` hoặc `PreparedStatement` phù hợp khi muốn kiểm tra **một nhánh tương tác thật cụ thể**:

- Đảm bảo resource được đóng khi lỗi.
- Đảm bảo transaction xử lý `rollback()` khi helper ném exception.
- Đảm bảo tham số bind được truyền đúng index khi có bug hồi quy cụ thể.
- Giả lập lỗi hiếm khó tái hiện ở DB, như rollback cũng ném `SQLException`.

Dù vậy, những test này là **kiểm thử logic điều khiển JDBC**, không thay thế kiểm thử commit/rollback và driver thật. Đặc biệt, `verify(connection).commit()` không chứng minh dữ liệu sau commit đúng hay được nhìn thấy từ connection khác.

## 15. Tổ chức bộ test nhanh, đáng tin và dễ chạy

Một chiến lược cân bằng:

```text
src/main/java
  Customer.java
  CustomerMapping.java
  CustomerRepository.java

src/test/java
  CustomerMappingUnitTest.java
  CustomerResultSetMapperTest.java

src/integrationTest/java (nếu build hỗ trợ source set riêng)
  CustomerRepositoryPgIT.java
  TransactionPgIT.java

CI pipeline
  1. Biên dịch + unit test nhanh
  2. Integration test với PostgreSQL thật/container
  3. Test driver/pool/timezone/concurrency chuyên sâu theo lịch
```

Cấu trúc thư mục chỉ là một ví dụ; không bắt buộc dự án nào cũng có source set `integrationTest`. Có thể dùng Maven Failsafe, Gradle source set/test task hoặc tag JUnit để tách suite theo cấu hình hiện hành.

Khi lựa chọn test suite:

| Tầng | Nên chạy khi nào | Mục tiêu |
|---|---|---|
| Unit test mapper và nghiệp vụ thuần | Mỗi commit/PR | Phản hồi nhanh, rõ lỗi |
| Integration test repository CRUD với DB thật | CI thường xuyên nếu hạ tầng cho phép | SQL, driver, type conversion, constraint |
| Integration test transaction/locking/timezone/batching | CI có cấu hình kiểm soát hoặc lịch định kỳ | Các khác biệt hệ quản trị và tình huống lỗi |
| Load/performance/chaos test | Môi trường riêng, theo chu kỳ hoặc trước release | Lock contention, plan, pool, failover, throughput |

Không cần đưa mọi bài test chậm vào mỗi lần sửa code nhỏ nếu làm pipeline mất ổn định; nhưng các đường đi dữ liệu quan trọng phải được xác minh với DBMS thật **trước khi triển khai production**.

## 16. Fixture và cô lập test: tránh false positive và flaky test

Một integration test tốt cần **dữ liệu đầu vào, trạng thái DB và kết quả kỳ vọng rõ ràng**.

Các nguyên tắc:

1. **Không dùng database production.** Test tạo/xóa bảng và gây lỗi SQL phải ở môi trường tách biệt.
2. **Dữ liệu có định danh ổn định.** Ví dụ dùng ID 101–104 trong test và làm sạch trước mỗi test.
3. **Không phụ thuộc thứ tự thực thi test.** Test B không được âm thầm yêu cầu test A chạy trước.
4. **Tránh dùng `Thread.sleep()` làm đồng bộ chung.** Với concurrency/deadlock test, nên dùng latch hoặc điều kiện được kiểm soát.
5. **Không chỉ assert “không có exception”.** Đọc lại dữ liệu cuối, số hàng, cột null và constraint.
6. **Dùng migration gần production.** Test schema tự viết chỉ là bước học tập; khác biệt DDL có thể che lỗi.
7. **Kiểm soát transaction do framework quản lý.** Một test framework tự rollback sau test không chứng minh service thật đã commit/rollback đúng.
8. **Giữ tài nguyên đóng đúng cách.** Dùng `try-with-resources` với `ResultSet`, `Statement` và `Connection`; quan sát pool khi test lỗi.
9. **Giữ DB và driver tương thích production.** Nâng driver version cần chạy lại các test kiểu dữ liệu, cursor, batch và timeout.
10. **Không chạy song song khi chia sẻ cùng bảng fixture.** Nếu cần parallelism, tách schema/container/DB hoặc thiết kế key/cleanup an toàn.

### Test được bao quanh bởi transaction tự rollback có đủ không?

Một số framework mở transaction cho mỗi test rồi rollback cuối test để dọn fixture. Cách này hữu ích, nhưng có thể làm sai mục tiêu nếu muốn xác minh:

- Một service tự commit riêng.
- Tính hiển thị dữ liệu giữa **hai connection**.
- Khóa, isolation và deadlock.
- Hành vi connection pool khi transaction đã kết thúc.
- Các sự kiện sau commit.

Nếu test cần chứng minh `commit()` thực, hãy dùng scope transaction đúng và **connection độc lập để quan sát**. Một test pass do framework rollback fixture không chứng minh toàn bộ ranh giới nghiệp vụ của production.

## 17. Khi test tích hợp thất bại, định vị lỗi ra sao?

Có thể dùng bảng chẩn đoán sau:

| Dấu hiệu | Khả năng cao thuộc đâu? | Bước kiểm tra |
|---|---|---|
| Unit test `toDomain(...)` sai | Quy tắc Java/validation | Không cần khởi động DB; sửa mapper |
| Mock `ResultSet` test sai thứ tự `wasNull()` | Phần trích xuất JDBC của mapper | Xem thứ tự getter và kiểm tra NULL |
| Unit test pass nhưng integration không tìm thấy cột | SQL alias/schema không khớp mapper | Xem SELECT và `ResultSetMetaData` |
| PostgreSQL báo lỗi cú pháp | SQL dialect hoặc tên identifier | Chạy SQL thật, xem SQLSTATE |
| Java nhận ngày giờ lệch | Kiểu Java/SQL, timezone JVM/session/server | Test instant, offset, session timezone |
| Số tiền có scale khác | Driver/DB precision và mapping | Kiểm tra DDL, `BigDecimal`, assertion |
| INSERT không rollback | Sai phạm vi connection/transaction | Test bằng connection mới sau rollback |
| Mock bind pass nhưng query chạy sai | Thứ tự bind, kiểu bind hoặc SQL | Dùng integration test parameterized |
| Test chạy với H2 nhưng production lỗi | Khác DBMS/driver/dialect | Chạy cùng họ DBMS và driver thật |
| Test lúc pass lúc fail | Fixture chung, concurrency, cache, transaction chưa dọn | Cô lập DB và quản lý cleanup |
| CI không chạy integration tests | Phân tách task/tag nhưng pipeline bỏ qua | Kiểm tra cấu hình thực thi suite |
| Query đúng nhưng chậm | Kế hoạch DB, index, pool, fetch | Đo JDBC và xem EXPLAIN thực tế |

### Lấy SQLSTATE và driver metadata

Khi lỗi, nên giữ đầy đủ thông tin kỹ thuật, không chỉ message:

```java
import java.sql.SQLException;
import java.sql.DatabaseMetaData;
import java.sql.Connection;

public static void logJdbcContext(
        Connection connection, SQLException error)
        throws SQLException {

    DatabaseMetaData meta = connection.getMetaData();

    System.out.println("DB: "
            + meta.getDatabaseProductName()
            + " " + meta.getDatabaseProductVersion());

    System.out.println("Driver: "
            + meta.getDriverName()
            + " " + meta.getDriverVersion());

    for (SQLException current = error;
         current != null;
         current = current.getNextException()) {

        System.out.println("SQLState=" + current.getSQLState()
                + ", vendorCode=" + current.getErrorCode()
                + ", message=" + current.getMessage());
    }
}
```

Mẫu này giả định connection vẫn hoạt động; nếu lỗi mạng khiến connection hỏng, **đừng ép gọi metadata trên connection hỏng chỉ để log**. Thông tin DB/driver thường nên được ghi từ lúc test setup, rồi gắn vào báo cáo lỗi. Không đưa username/password, URL chứa credential hoặc dữ liệu cá nhân vào log.

## 18. Ma trận kiểm thử đề xuất cho repository JDBC

Khi một repository xử lý nhiều bảng/kiểu dữ liệu, không cần mỗi dòng là một test riêng, nhưng cần đảm bảo các yêu cầu quan trọng đều được kiểm tra.

| Kịch bản | Unit mapping | Driver integration | Kỳ vọng |
|---|---|---|---|
| Tên có khoảng trắng | Có | Có nếu DB chuẩn hóa khác | Quy tắc trim như thiết kế |
| Tên Unicode tiếng Việt | Có | Có | Không mất ký tự khi ghi/đọc |
| SQL NULL ở cột nullable | Có, mock/thuần | **Bắt buộc** | Java `null`, không bị đổi thành 0 |
| Giá trị 0 khác NULL | Có | Có trên schema cho phép | Hai trạng thái phân biệt |
| `NUMERIC(14,2)` | Có | **Bắt buộc** | Giá trị và scale/precision đúng |
| `TIMESTAMPTZ` | Có phần logic Java | **Bắt buộc** | Cùng instant, xét độ chính xác DB |
| Không có hàng | Có phần nghiệp vụ | Có | `Optional.empty()` hoặc contract tương ứng |
| Nhiều hàng khi kỳ vọng một | Có phần quyết định | Có | Lỗi có ý nghĩa hoặc lựa chọn rõ ràng |
| SQL tham số hóa với input đặc biệt | Có thể mock bind | **Bắt buộc** | Không diễn giải input như cú pháp |
| Khóa chính trùng/FK/`CHECK` | Không thay DB | **Bắt buộc** | DB từ chối, SQLSTATE phù hợp |
| Commit/rollback | Có thể test nhánh điều khiển | **Bắt buộc** | Dữ liệu cuối đúng trên connection khác |
| Batch partial failure | Test xử lý counts giả | **Bắt buộc** | Chính sách all-or-nothing/partial rõ |
| Driver unsupported type/API | Không thể kết luận bằng mock | **Bắt buộc** | Fallback hoặc lỗi minh bạch |
| Pool reset / tenant state | Test nhánh helper | **Bắt buộc với pool thật** | Không rò rỉ state giữa borrower |
| Timeout/lock contention | Test retry policy thuần | Test chuyên biệt | Cleanup, trạng thái transaction đúng |

## 19. Bài thực hành tự kiểm tra

### Bài 1: Tìm giới hạn của unit test

Viết unit test cho `CustomerMapping.toDomain(...)` với tên `"  An  "`, số tiền `0.00`, hạn mức âm và `referrerId=null`. Nêu **ít nhất ba lỗi** mà các test đó không thể phát hiện: ví dụ sai SQL, sai tên cột và khác biệt mapping `NUMERIC` của driver.

### Bài 2: Phát hiện bug `wasNull()`

Cố tình chuyển `rs.wasNull()` xuống sau một getter khác rồi chạy test mock kiểm tra thứ tự. Vì sao kết quả có thể bị hiểu sai? Sau đó sửa mapper để gọi `wasNull()` ngay sau `getLong("referrer_id")`.

### Bài 3: Chạy test trên PostgreSQL thật

Dùng Testcontainers hoặc DB test độc lập, tạo bảng `customers` và chạy test trường hợp `referrer_id` NULL. Bảo đảm đã sử dụng **pgJDBC thật**, không phải H2 giả lập.

### Bài 4: Ràng buộc do DB bảo vệ

Thử thêm khách hàng có hạn mức âm bằng SQL trực tiếp trong test để kiểm tra `CHECK`, không chỉ dựa vào constructor `Customer`. Quan sát SQLSTATE thực và xác minh không có dữ liệu không hợp lệ.

### Bài 5: Biên transaction

Trong cùng connection tắt auto-commit, INSERT một hàng rồi rollback. Đọc lại trên connection khác và khẳng định không có hàng. Thử làm sai bằng cách mở connection mới trong DAO rồi giải thích vì sao rollback ngoài không hủy những thay đổi của connection kia.

### Bài 6: Kiểu thời gian

Thêm bảng `event_times`, ghi `OffsetDateTime` qua JDBC 4.2 và đọc lại. So sánh `Instant` thay vì chỉ so offset. Thử một giá trị có precision microsecond và xác nhận kỳ vọng đúng với DBMS.

### Bài 7: Hai driver/DBMS khác nhau

Nếu dự án cần hỗ trợ PostgreSQL và MySQL, chạy cùng các test **hợp đồng nghiệp vụ** trên từng driver thật nhưng điều chỉnh DDL và kỳ vọng đặc thù. Ghi lại khác biệt SQLSTATE, generated keys, kiểu ngày giờ và isolation.

### Bài 8: Kiểm tra pipeline

Đánh dấu test unit và integration bằng quy tắc đặt tên/tag rõ ràng. Chạy suite thường xuyên trong CI, bảo đảm lỗi integration test sẽ làm job thất bại chứ không chỉ hiển thị log cảnh báo.

## 20. Checklist trước khi kết luận repository đã được kiểm thử

1. **Logic Java:** đã test mapping, validation, null và nhánh lỗi bằng unit test không cần DB chưa?
2. **Biên JDBC:** đã chạy ít nhất một đường đọc/ghi thật qua driver và DBMS tương đương production chưa?
3. **SQL schema:** DDL/migration trong test có phản ánh schema production không?
4. **Kiểu dữ liệu:** đã xác nhận `BigDecimal`, `NULL`, `getObject` typed, ngày giờ và timezone nếu được sử dụng chưa?
5. **SQL tham số hóa:** đã kiểm tra input đặc biệt không bị biến thành cú pháp SQL chưa?
6. **Transaction:** đã xác minh commit/rollback bằng dữ liệu cuối trên connection độc lập chưa?
7. **Tài nguyên:** `ResultSet`, `PreparedStatement` và `Connection` có được đóng trong cả nhánh thành công/lỗi không?
8. **Cô lập test:** fixture có độc lập, không chạy đè nhau và không bị ảnh hưởng bởi thứ tự test không?
9. **Khác biệt driver:** đã ghi phiên bản DBMS/driver và kiểm thử các API không portable mà dự án dùng chưa?
10. **CI:** unit test nhanh và integration test có được chạy theo chiến lược rõ ràng, không bỏ sót trước release không?

## Ghi nhớ

- **Unit test logic ánh xạ** xác minh phép biến đổi dữ liệu và các nhánh Java với đầu vào được kiểm soát; chạy nhanh, không cần DBMS.
- **Mock `ResultSet` không phải JDBC driver.** Nó chỉ trả các giá trị test đã cấu hình và không chứng minh SQL/schema/kiểu DB hoạt động thật.
- **Integration test driver** phải sử dụng `DataSource`/`Connection`/`PreparedStatement`/`ResultSet` thật với DBMS phù hợp để xác minh giao thức, kiểu dữ liệu, constraint và transaction.
- **Tách mapping khỏi repository** giúp unit test rõ ràng nhưng vẫn cần integration test kiểm tra hợp đồng giữa hai phần.
- **H2 hoặc fake driver không thay PostgreSQL/MySQL/Oracle/SQL Server thật** khi test những hành vi phụ thuộc sản phẩm.
- **Đừng chỉ test round-trip qua cùng hai hàm production**; bổ sung fixture/assertion độc lập để phát hiện lỗi tương đồng.
- **Kiểm tra dữ liệu sau commit/rollback từ connection khác**, không chỉ `verify(connection).rollback()` trên mock.
- **Một chiến lược tốt kết hợp cả hai tầng:** unit tests rộng và nhanh, integration tests nhắm các ranh giới JDBC quan trọng, cùng test chuyên sâu cho lỗi concurrency, pool và driver.

Biết phân biệt hai loại kiểm thử giúp nhóm Java tránh hai ảo tưởng trái ngược: **“mock pass nghĩa là JDBC chạy đúng”** và **“có test DB rồi thì không cần test logic ánh xạ”**. Khi unit test bảo vệ quy tắc Java còn integration test xác minh sự thật từ driver và cơ sở dữ liệu, repository JDBC sẽ dễ thay đổi, dễ chẩn đoán và đáng tin cậy hơn khi triển khai.

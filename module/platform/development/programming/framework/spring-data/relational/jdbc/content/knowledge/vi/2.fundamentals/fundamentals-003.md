# Connection, PreparedStatement, ResultSet và JDBC driver

Khi một ứng dụng Java đọc hoặc ghi dữ liệu trong cơ sở dữ liệu quan hệ, cuối cùng nó phải gửi lệnh SQL qua một kết nối thật. **JDBC (Java Database Connectivity)** là bộ API chuẩn của Java cho công việc đó. Spring JDBC giảm mã lặp khi thao tác với JDBC; **Spring Data JDBC** tiếp tục xây dựng khả năng ánh xạ aggregate và repository trên nền tảng này. Hiểu bốn thành phần **JDBC driver**, **`Connection`**, **`PreparedStatement`** và **`ResultSet`** giúp giải thích chính xác điều gì xảy ra bên dưới một lệnh `repository.save(...)` hay `repository.findById(...)`.

## 1. Bốn thành phần phối hợp như thế nào?

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| **JDBC driver** | Thư viện triển khai JDBC và giao tiếp bằng giao thức của hệ quản trị cơ sở dữ liệu cụ thể. | Ứng dụng phải có driver tương thích với PostgreSQL, MySQL, H2, v.v. |
| **`Connection`** | Đại diện cho một phiên làm việc JDBC với cơ sở dữ liệu; chứa ngữ cảnh transaction và cấu hình phiên. | Lấy từ `DataSource` hoặc `DriverManager` và luôn hoàn trả/đóng đúng cách. |
| **`PreparedStatement`** | Lệnh SQL đã được chuẩn bị, cho phép gắn giá trị vào các tham số `?` và thực thi truy vấn/cập nhật. | Chỉ gắn **giá trị dữ liệu**, không ghép trực tiếp dữ liệu người dùng vào chuỗi SQL. |
| **`ResultSet`** | Kết quả dạng các hàng/cột của truy vấn `SELECT` (hoặc kết quả khóa sinh tự động). | Con trỏ ban đầu đứng **trước hàng đầu tiên**; gọi `next()` trước khi đọc cột. |

Luồng đơn giản của một truy vấn:

```text
Ứng dụng / Spring Data JDBC
           │ yêu cầu đọc dữ liệu
           ▼
   DataSource (có thể dùng connection pool)
           │ cấp Connection
           ▼
       Connection
           │ prepareStatement(SQL)
           ▼
   PreparedStatement -- setXxx(...) --> tham số
           │ executeQuery()
           ▼
      JDBC driver <---- giao thức mạng / giao thức DB ----> Database
           │ trả các hàng
           ▼
        ResultSet
           │ next(), getXxx(...)
           ▼
     Đối tượng Java
```

Sơ đồ là mô hình khái niệm: **driver cũng tham gia từ bước thiết lập `Connection`**, không chỉ ở bước thực thi SQL. Truy vấn `INSERT`, `UPDATE`, `DELETE` thường trả về số hàng bị ảnh hưởng thay vì một `ResultSet` chứa dữ liệu của `SELECT`.

## 2. JDBC driver: cầu nối giữa API Java và database

JDBC định nghĩa các interface chủ yếu trong `java.sql` và `javax.sql`; driver của từng nhà cung cấp hiện thực phần giao tiếp với database. Vì giao diện Java được chuẩn hóa, mã nguồn sử dụng `Connection` hoặc `PreparedStatement` có thể tương tự nhau giữa các hệ quản trị, dù cú pháp SQL, kiểu dữ liệu, tính năng transaction và cách driver tối ưu hóa vẫn có thể khác nhau.

Ví dụ URL kết nối:

| Database | JDBC URL minh họa | Driver thường dùng |
| --- | --- | --- |
| PostgreSQL | `jdbc:postgresql://localhost:5432/learn_db` | PostgreSQL JDBC Driver |
| MySQL | `jdbc:mysql://localhost:3306/learn_db` | MySQL Connector/J |
| H2 in-memory | `jdbc:h2:mem:learn_db` | H2 JDBC Driver |

Trong một dự án Spring Boot có quản lý phiên bản dependency, có thể khai báo driver tương ứng trong Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Đây là ví dụ cho **PostgreSQL**; nếu dùng H2, thay dependency driver bằng `runtimeOnly 'com.h2database:h2'`. Cấu hình quản lý phiên bản của Spring Boot phải đang được bật để có thể bỏ phiên bản cụ thể như trên; dự án Java thuần cần khai báo phiên bản driver tương thích.

Từ JDBC 4.0, driver hiện đại thường tự đăng ký qua cơ chế Java Service Provider. Vì vậy mã ứng dụng thông thường **không cần** gọi `Class.forName("org.postgresql.Driver")` trước khi kết nối. Việc nạp lớp driver bằng tay chủ yếu xuất hiện trong ứng dụng cũ hoặc môi trường có cơ chế classloader đặc biệt.

Hai cách phổ biến để xin kết nối:

```java
// Java/JDBC thuần: kết nối trực tiếp.
Connection connection = DriverManager.getConnection(
        "jdbc:postgresql://localhost:5432/learn_db",
        "app_user",
        password
);

// Ứng dụng dùng Spring: DataSource được cấu hình và cấp phát sẵn.
Connection pooledConnection = dataSource.getConnection();
```

`DriverManager` phù hợp để học cơ chế JDBC và các chương trình nhỏ. Trong ứng dụng server, `DataSource` là abstraction thuận tiện hơn cho cấu hình, pooling và tích hợp transaction với Spring. **`DataSource` không phải driver**: nó cung cấp `Connection` và sử dụng driver ở bên dưới.

## 3. Connection: phiên làm việc, tài nguyên và transaction

`Connection` được tạo khi kết nối database được thiết lập hoặc được lấy ra từ pool. Nó cung cấp các phương thức như:

- `prepareStatement(sql)`: tạo `PreparedStatement` gắn với kết nối.
- `createStatement()`: tạo `Statement` để thực thi SQL không tham số, thường chỉ nên dùng khi SQL là hằng hoặc được kiểm soát.
- `setAutoCommit(false)`, `commit()`, `rollback()`: điều khiển transaction khi quản lý JDBC trực tiếp.
- `setTransactionIsolation(...)`: thiết lập mức cô lập khi database/driver hỗ trợ.
- `close()`: kết thúc quyền sử dụng kết nối.

### 3.1. Vì sao phải đóng Connection?

Kết nối thực tiêu tốn tài nguyên ở client, server và có thể chiếm một vị trí trong connection pool. Không hoàn trả kết nối sẽ khiến ứng dụng dần không còn kết nối rảnh, dẫn đến lỗi timeout hoặc pool exhaustion.

Nên dùng **try-with-resources**:

```java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
             "SELECT id, full_name FROM customers WHERE id = ?")) {
    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            System.out.println(rs.getString("full_name"));
        }
    }
} // rs, ps, conn được đóng theo thứ tự ngược lại
```

Với kết nối lấy trực tiếp từ `DriverManager`, `close()` thông thường đóng kết nối vật lý. Với connection pool như **HikariCP**, gọi `close()` trên kết nối được pool cấp thường **trả kết nối về pool** để tái sử dụng. Vì thế, dù có pool, mã mượn kết nối vẫn phải gọi `close()`.

Không chia sẻ một `Connection` đang thao tác giữa nhiều thread. `PreparedStatement` và `ResultSet` cũng nên thuộc phạm vi một thao tác, thay vì lưu làm biến dùng chung trong singleton service.

### 3.2. Auto-commit và transaction

Trong JDBC thuần, kết nối thường có `autoCommit = true` theo mặc định: một câu lệnh hoàn thành thành công sẽ được commit tự động. Nếu hai thao tác phải **cùng thành công hoặc cùng thất bại**, cần transaction:

```java
void transfer(DataSource dataSource, long fromId, long toId,
              BigDecimal amount) throws SQLException {
    try (Connection conn = dataSource.getConnection()) {
        conn.setAutoCommit(false);
        try (PreparedStatement debit = conn.prepareStatement(
                     "UPDATE accounts SET balance = balance - ? " +
                     "WHERE id = ? AND balance >= ?");
             PreparedStatement credit = conn.prepareStatement(
                     "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {

            debit.setBigDecimal(1, amount);
            debit.setLong(2, fromId);
            debit.setBigDecimal(3, amount);
            if (debit.executeUpdate() != 1) {
                throw new SQLException("Không tìm thấy tài khoản nguồn hoặc không đủ số dư");
            }

            credit.setBigDecimal(1, amount);
            credit.setLong(2, toId);
            if (credit.executeUpdate() != 1) {
                throw new SQLException("Không tìm thấy tài khoản đích");
            }

            conn.commit();
        } catch (SQLException e) {
            conn.rollback();
            throw e;
        }
    }
}
```

Ví dụ giả định `amount` dương, hai tài khoản khác nhau và schema/DB hỗ trợ transaction; các điều kiện đầu vào khác phải được kiểm tra ở tầng nghiệp vụ. Hai lệnh cập nhật chạy trên **cùng một `Connection`**, nên thuộc cùng một transaction.

Trong ứng dụng Spring, thông thường nên đặt `@Transactional` trên phương thức service và để **Spring transaction manager** quản lý commit/rollback, thay vì tự gọi `setAutoCommit` hoặc `commit` trên connection do Spring quản lý. Transaction Spring sẽ ràng buộc các thao tác tương thích trong cùng luồng xử lý với connection phù hợp.

## 4. PreparedStatement: SQL có tham số

`PreparedStatement` được tạo từ `Connection` với câu SQL xác định. Ký hiệu `?` là **parameter marker**, được gắn giá trị qua `setString`, `setLong`, `setBigDecimal`, v.v. Chỉ số tham số **bắt đầu từ 1**, trong khi nhiều cấu trúc Java bắt đầu từ 0.

Giả sử database có bảng:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE
);
```

Chèn một khách hàng:

```java
String sql = "INSERT INTO customers (full_name, email) VALUES (?, ?)";

try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setString(1, "Nguyễn An");
    ps.setString(2, "an@example.test");

    int affectedRows = ps.executeUpdate(); // ở đây thường là 1
    System.out.println("Số hàng được chèn: " + affectedRows);
}
```

Các phương thức thực thi quan trọng:

| Phương thức | Khi dùng | Kết quả trả về |
| --- | --- | --- |
| `executeQuery()` | Câu SQL trả tập hàng, thường là `SELECT` | `ResultSet` |
| `executeUpdate()` | `INSERT`, `UPDATE`, `DELETE` hoặc DDL tương thích | `int` là số hàng bị ảnh hưởng; ý nghĩa với DDL phụ thuộc driver |
| `execute()` | Khi không biết trước câu SQL sẽ trả tập hàng hay số hàng cập nhật | `boolean` cho biết kết quả đầu tiên có phải `ResultSet` hay không |
| `addBatch()` / `executeBatch()` | Gửi một nhóm thao tác cùng mẫu SQL | Mảng kết quả cập nhật; chi tiết phụ thuộc driver |

### 4.1. Vì sao không nối dữ liệu người dùng vào SQL?

Ví dụ **không an toàn**:

```java
String sql = "SELECT id FROM customers WHERE email = '" + emailInput + "'";
```

Nội dung của `emailInput` có thể thay đổi cấu trúc SQL, gây **SQL injection**. Cách đúng:

```java
String sql = "SELECT id FROM customers WHERE email = ?";
try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setString(1, emailInput);
    try (ResultSet rs = ps.executeQuery()) {
        // Đọc dữ liệu...
    }
}
```

Driver xử lý chuỗi SQL và giá trị tham số theo hợp đồng JDBC, tránh việc giá trị dữ liệu trở thành một phần cú pháp SQL. Tuy nhiên `?` **không** thay thế được tên bảng, tên cột, từ khóa SQL hoặc một đoạn `ORDER BY` tùy ý. Nếu cần chọn tên cột để sắp xếp, phải dùng danh sách tên hợp lệ do ứng dụng định nghĩa.

`PreparedStatement` cũng cho phép tái sử dụng cùng mẫu SQL với bộ giá trị khác nhau. Việc database có thực sự tạo server-side prepared statement và cache execution plan hay không tùy driver, cấu hình và database; không nên giả định mọi driver đều tối ưu giống nhau.

### 4.2. Kiểu dữ liệu và giá trị NULL

Nên chọn setter phù hợp kiểu SQL:

```java
ps.setLong(1, 1001L);
ps.setString(2, "an@example.test");
ps.setBigDecimal(3, new BigDecimal("150000.50"));
ps.setNull(4, java.sql.Types.VARCHAR);
```

`setNull(index, sqlType)` truyền giá trị SQL `NULL` kèm thông tin kiểu, khác với chuỗi `"null"`. Kiểu Java và kiểu SQL không luôn tương ứng một-một; các kiểu ngày giờ, số thập phân, UUID hay JSON có thể cần API hoặc cấu hình riêng theo driver.

### 4.3. Lấy khóa được database sinh

Nếu cột `id` do database sinh, có thể yêu cầu `getGeneratedKeys()`:

```java
String sql = "INSERT INTO customers (full_name, email) VALUES (?, ?)";
try (PreparedStatement ps = conn.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {
    ps.setString(1, "Nguyễn An");
    ps.setString(2, "an@example.test");
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long generatedId = keys.getLong(1);
            System.out.println("ID: " + generatedId);
        }
    }
}
```

Cú pháp tạo ID và mức hỗ trợ lấy khóa tự sinh có thể khác nhau giữa các hệ quản trị. Spring Data JDBC xử lý phần lớn thao tác sinh/đọc ID trong quá trình lưu entity khi mapping và database dialect hỗ trợ.

## 5. ResultSet: đọc từng hàng của kết quả

`ResultSet` không phải một `List` đã được ánh xạ thành đối tượng Java. Nó biểu diễn dữ liệu trả về qua một con trỏ JDBC. Sau `executeQuery()`, phải gọi `next()` để chuyển đến hàng đầu tiên; mỗi lần gọi `next()` thành công, con trỏ chuyển tới hàng kế tiếp.

Ví dụ đọc một khách hàng theo ID:

```java
record Customer(long id, String fullName, String email) {}

static Optional<Customer> findById(DataSource dataSource, long id)
        throws SQLException {
    String sql = """
            SELECT id, full_name, email
            FROM customers
            WHERE id = ?
            """;

    try (Connection conn = dataSource.getConnection();
         PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setLong(1, id);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                return Optional.empty();
            }
            Customer customer = new Customer(
                    rs.getLong("id"),
                    rs.getString("full_name"),
                    rs.getString("email")
            );
            return Optional.of(customer);
        }
    }
}
```

Đoạn mã cần import `java.sql.*`, `java.util.Optional` và `javax.sql.DataSource`. Nó giả định cột `id` không `NULL` vì là khóa chính.

Nếu truy vấn có thể trả nhiều hàng, dùng `while (rs.next())` thay vì `if (rs.next())`:

```java
List<Customer> customers = new ArrayList<>();
while (rs.next()) {
    customers.add(new Customer(
            rs.getLong("id"),
            rs.getString("full_name"),
            rs.getString("email")
    ));
}
```

Lưu ý khi ánh xạ dữ liệu:

- Có thể đọc cột theo chỉ số **từ 1** (`getString(2)`) hoặc theo tên/alias (`getString("full_name")`). Alias rõ ràng giúp việc mapping ít nhầm lẫn hơn trong query có `JOIN`.
- Với kiểu nguyên thủy, ví dụ `getLong(...)`, SQL `NULL` có thể được chuyển thành `0`; gọi `rs.wasNull()` ngay sau getter nếu cần phân biệt. Với các kiểu thích hợp, `getObject("column", Long.class)` có thể giữ được `null`, tùy mức hỗ trợ của driver.
- `ResultSet` thông thường là **forward-only/read-only** theo tùy chọn mặc định của `Connection.prepareStatement(...)`. Không mặc định rằng có thể kéo ngược con trỏ, cập nhật hàng trực tiếp hoặc tự động tải toàn bộ dữ liệu.
- `ResultSet` gắn với `Statement` và `Connection` đã tạo ra nó. Đừng trả trực tiếp `ResultSet` ra ngoài một khối `try-with-resources` đã đóng kết nối; hãy ánh xạ thành object/DTO trước.

Đối với tập dữ liệu lớn, tránh đọc tất cả hàng vào RAM nếu không cần thiết. Có thể phân trang SQL, giới hạn cột cần đọc, hoặc cân nhắc `setFetchSize(...)`. Việc fetch theo từng đợt và server-side cursor phụ thuộc database, driver và cấu hình transaction; **`setFetchSize` không bảo đảm streaming** trong mọi môi trường.

## 6. Ví dụ JDBC thuần hoàn chỉnh với H2

Ví dụ Java sau tạo một database H2 trong bộ nhớ, tạo bảng, thêm một hàng, lấy ID vừa sinh và truy vấn theo ID. H2 JDBC driver phải hiện diện trên runtime classpath. Nếu dùng Spring Boot với dependency management, có thể thêm `runtimeOnly 'com.h2database:h2'`; còn ứng dụng Java thuần phải khai báo một phiên bản H2 thích hợp.

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public class JdbcBasics {
    public static void main(String[] args) throws SQLException {
        String url = "jdbc:h2:mem:learn_db;DB_CLOSE_DELAY=-1";

        try (Connection conn = DriverManager.getConnection(url, "sa", "")) {
            try (Statement ddl = conn.createStatement()) {
                ddl.executeUpdate("""
                        CREATE TABLE customers (
                            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                            full_name VARCHAR(100) NOT NULL,
                            email VARCHAR(255) NOT NULL UNIQUE
                        )
                        """);
            }

            long newId;
            String insertSql =
                    "INSERT INTO customers (full_name, email) VALUES (?, ?)";

            try (PreparedStatement insert = conn.prepareStatement(
                    insertSql, Statement.RETURN_GENERATED_KEYS)) {
                insert.setString(1, "Nguyễn An");
                insert.setString(2, "an@example.test");
                int rows = insert.executeUpdate();
                if (rows != 1) {
                    throw new SQLException("INSERT không tạo đúng một hàng");
                }

                try (ResultSet keys = insert.getGeneratedKeys()) {
                    if (!keys.next()) {
                        throw new SQLException("Database không trả ID mới");
                    }
                    newId = keys.getLong(1);
                }
            }

            try (PreparedStatement find = conn.prepareStatement(
                    "SELECT id, full_name, email FROM customers WHERE id = ?")) {
                find.setLong(1, newId);

                try (ResultSet rs = find.executeQuery()) {
                    while (rs.next()) {
                        System.out.printf("%d | %s | %s%n",
                                rs.getLong("id"),
                                rs.getString("full_name"),
                                rs.getString("email"));
                    }
                }
            }
        }
    }
}
```

Kết quả minh họa:

```text
1 | Nguyễn An | an@example.test
```

Giá trị ID thực tế do database cấp. Tham số `DB_CLOSE_DELAY=-1` giữ database H2 in-memory trong phạm vi tiến trình JVM sau khi connection cuối cùng đóng; đây là thiết lập cho ví dụ học tập, không phải cấu hình lưu trữ bền vững. Database H2 in-memory mất dữ liệu khi JVM kết thúc.

Trong ví dụ này:

1. `DriverManager` tìm driver xử lý URL `jdbc:h2:...` và lấy `Connection`.
2. `Statement` chạy câu tạo bảng không có dữ liệu đầu vào từ người dùng.
3. `PreparedStatement` gắn tên/email vào `?` và chạy `INSERT`.
4. `getGeneratedKeys()` trả một `ResultSet` chứa ID mới.
5. `executeQuery()` trả một `ResultSet` khác chứa hàng được chọn.
6. Các đối tượng JDBC được đóng theo phạm vi `try-with-resources`.

## 7. Các thành phần này nằm ở đâu trong Spring Data JDBC?

Với Spring Boot, thông thường bạn cấu hình `spring.datasource.*` để Boot tạo `DataSource`; nếu có HikariCP trên classpath (thông thường qua các JDBC starter), pool sẽ quản lý việc mượn/trả các kết nối. **Spring JDBC** dùng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` để mở/đóng tài nguyên đúng cách, gắn tham số và chuyển `SQLException` thành các exception thuộc hệ thống `DataAccessException` của Spring.

Ví dụ dùng `JdbcTemplate`:

```java
@Repository
class CustomerQueries {
    private final JdbcTemplate jdbc;

    CustomerQueries(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    List<Customer> findByEmail(String email) {
        return jdbc.query(
                "SELECT id, full_name, email FROM customers WHERE email = ?",
                (rs, rowNum) -> new Customer(
                        rs.getLong("id"),
                        rs.getString("full_name"),
                        rs.getString("email")),
                email
        );
    }
}
```

`JdbcTemplate` vẫn sử dụng JDBC driver, `Connection`, `PreparedStatement` và `ResultSet` bên dưới; ứng dụng chỉ không cần điều khiển trực tiếp từng tài nguyên. Với `NamedParameterJdbcTemplate`, bạn có thể viết tham số dạng `:email`; Spring chuyển chúng thành tham số JDBC thích hợp trước khi gửi tới driver. **JDBC nguyên bản dùng `?`, không hiểu cú pháp `:email`.**

Ở mức **Spring Data JDBC**, bạn làm việc với entity và repository:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.repository.CrudRepository;

@Table("customers")
record Customer(@Id Long id, String fullName, String email) {}

interface CustomerRepository extends CrudRepository<Customer, Long> {}
```

Trong Spring Boot được cấu hình Spring Data JDBC phù hợp, repository có thể thực hiện:

```java
Customer saved = repository.save(
        new Customer(null, "Nguyễn An", "an@example.test"));

Optional<Customer> found = repository.findById(saved.id());
```

Ở đây, bạn không tự viết `PreparedStatement` hoặc đọc `ResultSet`: Spring Data JDBC xây dựng SQL, liên kết giá trị, thực thi qua hạ tầng JDBC và ánh xạ kết quả theo metadata. Quy tắc đặt tên cột mặc định thường ánh xạ `fullName` sang `full_name`; cấu hình naming strategy và annotation có thể thay đổi điều đó. **Spring Data JDBC không mặc định tự tạo schema bảng**: ứng dụng cần schema phù hợp, thường quản lý bằng migration hoặc script khởi tạo.

Spring Data JDBC không phải JPA/Hibernate. Nó không có persistence context hoặc cơ chế dirty checking tự động như JPA; `save`, `findById` và các thao tác repository có ngữ nghĩa của Spring Data JDBC và mô hình **aggregate**. Dù thao tác ở tầng cao hơn, nó vẫn dựa vào các khái niệm JDBC trong bài này.

## 8. Lỗi thường gặp và cách xác định nguyên nhân

| Biểu hiện | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `No suitable driver` | Thiếu JAR driver trên runtime classpath, URL JDBC sai hoặc driver không phù hợp. | Kiểm tra dependency runtime và tiền tố `jdbc:...`. |
| Không mở được `Connection` | Database chưa chạy, sai host/port, thiếu quyền hoặc thông tin xác thực không đúng. | Kiểm tra trạng thái DB, mạng, tài khoản và URL kết nối. |
| Lỗi cú pháp SQL / không tìm thấy bảng | SQL không hợp dialect, bảng/cột chưa được tạo hoặc sai schema. | Chạy SQL trên đúng DB, kiểm tra migration và tên object. |
| `Parameter index out of range` | Số lượng hoặc chỉ số `setXxx(...)` không khớp các dấu `?`. | Đếm parameter marker và nhớ chỉ số bắt đầu từ 1. |
| Không đọc được tên cột | Query thiếu cột mong đợi hoặc dùng alias khác. | Đối chiếu `SELECT` và `rs.getXxx("alias")`. |
| Pool hết kết nối / truy vấn treo | Không đóng connection, query/transaction lâu hoặc pool quá nhỏ so với tải. | Đảm bảo đóng tài nguyên; đo thời gian query và thời gian giữ connection. |
| Đọc số `0` nhưng dữ liệu SQL là `NULL` | Dùng getter nguyên thủy mà không kiểm tra `wasNull()`. | Dùng `wasNull()` hoặc kiểu Java nullable phù hợp. |
| Một phần thao tác đã ghi dù phần sau lỗi | Các lệnh chạy ở auto-commit riêng lẻ, thiếu transaction bao quanh. | Dùng transaction JDBC đúng cách hoặc `@Transactional` trong Spring. |

`SQLException` chứa các thông tin như message, `SQLState` và mã lỗi riêng của database. Hãy xem cả lỗi gốc trong chuỗi exception (cause) khi chẩn đoán; ứng dụng production nên ghi log đủ ngữ cảnh kỹ thuật nhưng tránh log mật khẩu và giá trị dữ liệu nhạy cảm.

## 9. Ghi nhớ qua một lượt truy vấn

Một lần đọc khách hàng theo ID thường đi qua chuỗi:

**Chọn driver/`DataSource` → mượn `Connection` → chuẩn bị SQL bằng `PreparedStatement` → gắn ID bằng `setLong(1, id)` → `executeQuery()` → duyệt `ResultSet` bằng `next()` → ánh xạ cột thành Java object → đóng `ResultSet` và statement → hoàn trả connection.**

Khi nhìn thấy một method Spring Data JDBC như `findById`, bạn có thể dùng chuỗi này để giải thích nguồn gốc dữ liệu, vị trí transaction, tài nguyên nào bị giữ trong lúc query và vì sao cấu hình driver/pool ảnh hưởng đến ứng dụng.

### Tự luyện tập

1. Sửa ví dụ H2 để tìm khách hàng theo email bằng một `PreparedStatement`; thử email chứa dấu nháy đơn và quan sát vì sao truyền qua `setString` vẫn an toàn.
2. Thêm cột `phone` cho phép `NULL` và thử hai cách đọc: `getString("phone")` và một cột số tùy chọn với `getLong(...)` + `wasNull()`.
3. Thực hiện hai câu `UPDATE` cùng một transaction; cố ý gây lỗi ở câu thứ hai và quan sát kết quả sau `rollback()`, rồi đối chiếu khi để auto-commit.

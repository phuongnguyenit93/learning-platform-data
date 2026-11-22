# Phạm vi chuẩn JDBC và các phần mở rộng riêng của driver

**JDBC (Java Database Connectivity)** là API Java để truy cập cơ sở dữ liệu quan hệ. Trong một ứng dụng thực tế, lập trình viên vừa dùng những giao diện được chuẩn hóa như `Connection`, `PreparedStatement`, `ResultSet`, vừa có thể gặp các lớp, cấu hình và cách xử lý riêng của driver PostgreSQL, MySQL, SQL Server hoặc Oracle.

Phân biệt hai phạm vi này là một phần quan trọng của **kiến trúc JDBC**. Nó giúp trả lời ba câu hỏi: mã nào có thể dùng lại khi đổi hệ quản trị cơ sở dữ liệu (DBMS), tính năng nào cần kiểm tra driver trước khi dùng, và lúc nào việc phụ thuộc một sản phẩm cụ thể là lựa chọn có chủ đích.

## 1. Ba lớp trách nhiệm: chuẩn API, driver và DBMS

JDBC cung cấp **hợp đồng API**; driver hiện thực hợp đồng đó; DBMS cung cấp các khả năng dữ liệu thực tế. Mối quan hệ có thể hình dung như sau:

```text
                Mã ứng dụng Java
                      |
             API JDBC tiêu chuẩn
            java.sql / javax.sql
                      |
         +------------+------------+
         |                         |
  PostgreSQL JDBC Driver     MySQL JDBC Driver
         |                         |
  Giao thức PostgreSQL        Giao thức MySQL
         |                         |
     PostgreSQL                  MySQL
         |                         |
   Schema và dữ liệu         Schema và dữ liệu

  (API chung)       (driver và DBMS có hành vi riêng)
```

| Tầng | Quyết định điều gì? | Không tự bảo đảm điều gì? |
| --- | --- | --- |
| **Chuẩn JDBC** | Tên giao diện/phương thức, tham số, nhiều quy tắc về kết nối, truy vấn, transaction, metadata và exception | Mọi DBMS có cùng kiểu dữ liệu, cú pháp SQL hoặc tính năng tùy chọn |
| **JDBC driver** | Cách hiện thực API và giao tiếp với một DBMS; khả năng chuyển đổi kiểu, streaming, tối ưu batch, thuộc tính kết nối | Có thể thực thi mọi câu SQL viết cho DBMS khác |
| **DBMS** | Cú pháp SQL hỗ trợ, kiểu cột, quyền, giao dịch, khóa, stored procedure, tối ưu truy vấn và lưu trữ | Mọi thao tác đều được đưa ra dưới dạng API JDBC mở rộng |

Một phương thức **được định nghĩa trong JDBC** và một phương thức **hoạt động với driver hiện tại** là hai nhận định khác nhau. JDBC có những khả năng tùy chọn hoặc phụ thuộc DBMS; driver có thể báo không hỗ trợ, ném `SQLFeatureNotSupportedException` hoặc biểu hiện giới hạn cụ thể theo phiên bản.

## 2. Phần nào thuộc chuẩn JDBC?

Hầu hết các thao tác nền tảng nằm trong các gói `java.sql` và `javax.sql` của Java:

| Thành phần chuẩn | Vai trò trong ứng dụng |
| --- | --- |
| `DriverManager` | Tìm driver phù hợp với JDBC URL và lấy `Connection` |
| `DataSource` | Cung cấp `Connection`; có thể kết hợp với connection pool |
| `Connection` | Tạo statement; quản lý autocommit, commit/rollback và một số thiết lập phiên |
| `Statement` | Thực thi SQL không dùng tham số ràng buộc |
| `PreparedStatement` | Truyền dữ liệu an toàn qua `?`, chạy truy vấn/cập nhật |
| `CallableStatement` | Gọi stored procedure/function, đăng ký OUT/INOUT khi được hỗ trợ |
| `ResultSet` | Đọc dữ liệu từng hàng/cột |
| `DatabaseMetaData` | Hỏi driver về sản phẩm DBMS, phiên bản và các khả năng được hỗ trợ |
| `ResultSetMetaData` | Xem số cột, tên, loại JDBC, precision/scale của kết quả |
| `SQLException` và các lớp con | Biểu diễn lỗi và trạng thái SQL được báo qua JDBC |
| `Types`, `JDBCType`, `SQLType` | Biểu diễn kiểu dữ liệu SQL trong các lời gọi JDBC |

Những thao tác sau là **lời gọi API chuẩn**:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT id, title FROM books WHERE author_id = ?")) {

    statement.setLong(1, 42L);

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            long id = result.getLong("id");
            String title = result.getString("title");
            System.out.println(id + ": " + title);
        }
    }
}
```

Đoạn mã giả định biến `dataSource` kiểu `javax.sql.DataSource` đã được cấu hình, bảng `books` tồn tại và cột `author_id` có kiểu phù hợp. Các tên `getConnection`, `prepareStatement`, `setLong`, `executeQuery`, `getLong`, `getString` là **chuẩn JDBC**; câu SQL và schema vẫn do hệ quản trị xử lý.

### API chuẩn không có nghĩa tính năng nào cũng bắt buộc

Các ví dụ dễ gây nhầm lẫn gồm:

- **Batch:** JDBC có `addBatch()` và `executeBatch()`, nhưng cách tối ưu và các giới hạn phụ thuộc driver/DBMS.
- **Savepoint:** JDBC có `setSavepoint()` và `rollback(Savepoint)`; không phải DBMS hay chế độ giao dịch nào cũng hỗ trợ.
- **Result set cuộn/cập nhật:** các loại `TYPE_SCROLL_INSENSITIVE`, `TYPE_SCROLL_SENSITIVE` hoặc `CONCUR_UPDATABLE` là yêu cầu khả năng, không phải bảo đảm driver hỗ trợ.
- **Generated keys:** JDBC có `Statement.RETURN_GENERATED_KEYS` và `getGeneratedKeys()`; loại khóa, cú pháp SQL và cách lấy về còn tùy sản phẩm.
- **Kiểu dữ liệu:** JDBC định nghĩa `Types.ARRAY`, `Types.STRUCT`, `Types.SQLXML`, `Types.OTHER`, nhưng DBMS/driver có thể không hỗ trợ hoặc ánh xạ khác nhau.
- **Java Time:** JDBC 4.2 đưa thêm cách ánh xạ các loại `java.time` (như `LocalDate`, `LocalDateTime`); cần kiểm tra driver với kiểu SQL và phương thức `getObject()/setObject()` sử dụng.

Do đó, **lập trình dựa trên interface chuẩn** là bước đầu để dễ bảo trì, còn **kiểm tra khả năng và thử nghiệm với driver thật** mới quyết định tính tương thích.

## 3. Phần mở rộng riêng của driver là gì?

Driver có thể cung cấp các API hoặc cấu hình nằm **ngoài hợp đồng JDBC chuẩn** để dùng tính năng của sản phẩm hiệu quả hơn.

| Dạng đặc thù | Ví dụ minh họa | Điều gì bị ràng buộc? |
| --- | --- | --- |
| **Lớp/giao diện Java riêng** | PostgreSQL `org.postgresql.PGConnection` | Mã Java phụ thuộc thư viện PostgreSQL JDBC Driver |
| **Kiểu dữ liệu Java riêng** | PostgreSQL `org.postgresql.util.PGobject` | Cách mã hóa/giải mã kiểu SQL đặc thù như `jsonb` |
| **API tối ưu riêng** | PostgreSQL COPY API (`CopyManager`) | Cách chuyển dữ liệu hàng loạt riêng PostgreSQL |
| **Thuộc tính kết nối riêng** | PostgreSQL `reWriteBatchedInserts`, MySQL `rewriteBatchedStatements` | Tên thuộc tính, giá trị và hành vi tối ưu tùy driver |
| **Chuyển đổi kiểu riêng** | Ánh xạ JSON, UUID, array hoặc kiểu không chuẩn | Kết quả `getObject()` / `setObject()` có thể khác |
| **Cú pháp SQL riêng DBMS** | PostgreSQL `::jsonb`, MySQL `ON DUPLICATE KEY UPDATE` | Câu SQL phụ thuộc dialect DBMS dù gọi qua `PreparedStatement` chuẩn |

**Phân biệt rõ hai loại phụ thuộc:**

1. **Mở rộng driver:** ứng dụng import `org.postgresql.*` hoặc cấu hình một thuộc tính chỉ PostgreSQL JDBC Driver hiểu. Đây là sự phụ thuộc vào thư viện driver.
2. **Tính năng DBMS/SQL dialect:** ứng dụng dùng cột `JSONB` hoặc cú pháp `::jsonb`. Kể cả toàn bộ mã Java chỉ import `java.sql.*`, câu SQL vẫn phụ thuộc PostgreSQL.

Chúng thường đi cùng nhau, nhưng là **hai nguồn phụ thuộc khác nhau**. Thay thư viện driver không tự chuyển câu SQL hoặc schema sang DBMS khác.

## 4. Lấy thông tin và kiểm tra khả năng bằng `DatabaseMetaData`

Trước khi dùng một tính năng tùy chọn, hãy hỏi metadata do driver cung cấp. Đây là cách kiểm tra trong phạm vi API JDBC chuẩn:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class JdbcCapabilityReport {
    private JdbcCapabilityReport() {}

    public static void print(DataSource dataSource) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();

            System.out.println("DBMS: "
                    + meta.getDatabaseProductName() + " "
                    + meta.getDatabaseProductVersion());
            System.out.println("Driver: "
                    + meta.getDriverName() + " " + meta.getDriverVersion());

            System.out.println("Batch: " + meta.supportsBatchUpdates());
            System.out.println("Savepoint: " + meta.supportsSavepoints());
            System.out.println("Generated keys: "
                    + meta.supportsGetGeneratedKeys());
            System.out.println("Scrollable ResultSet: "
                    + meta.supportsResultSetType(
                            ResultSet.TYPE_SCROLL_INSENSITIVE));
            System.out.println("Serializable isolation: "
                    + meta.supportsTransactionIsolationLevel(
                            Connection.TRANSACTION_SERIALIZABLE));
        }
    }
}
```

`DatabaseMetaData` có thêm các phương thức như `supportsStoredProcedures()`, `supportsTransactions()`, `supportsResultSetConcurrency(type, concurrency)` và `getSQLKeywords()`.

**Giới hạn của việc dò khả năng:** Metadata là thông tin **driver báo cáo**. Một kết quả `true` không bảo đảm mọi kiểu cột, chế độ ResultSet hay câu SQL đều chạy như mong đợi; vẫn cần thử bằng câu lệnh đại diện. Nếu trả `false`, nên dùng cách thay thế có hỗ trợ. Trên một số tính năng, driver có thể ném `SQLFeatureNotSupportedException` hoặc `SQLException` khi thực thi.

### Ví dụ: xử lý `getGeneratedKeys()` có điều kiện

```java
try (Connection connection = dataSource.getConnection()) {
    if (!connection.getMetaData().supportsGetGeneratedKeys()) {
        throw new UnsupportedOperationException(
                "Driver khong bao cao ho tro generated keys");
    }

    String sql = "INSERT INTO books(title) VALUES (?)";
    try (PreparedStatement statement = connection.prepareStatement(
            sql, Statement.RETURN_GENERATED_KEYS)) {

        statement.setString(1, "JDBC căn ban");
        statement.executeUpdate();

        try (ResultSet keys = statement.getGeneratedKeys()) {
            if (keys.next()) {
                long newId = keys.getLong(1);
                System.out.println("Inserted id: " + newId);
            } else {
                throw new SQLException("Khong nhan duoc generated key");
            }
        }
    }
}
```

Ví dụ cần import `java.sql.PreparedStatement`, `java.sql.Statement` và các kiểu liên quan. Bảng phải có cơ chế tạo khóa phù hợp. Một số DBMS có cách chuẩn hơn cho hệ thống đó, chẳng hạn mệnh đề `RETURNING`; nó có thể là SQL riêng của sản phẩm. Việc lựa chọn giữa cách chung và cách đặc thù cần dựa trên **tính đúng đắn được kiểm thử** và yêu cầu thực tế.

## 5. Dùng API riêng của PostgreSQL: hai cách tiếp cận

Giả sử PostgreSQL có bảng:

```sql
CREATE TABLE app_settings (
    id BIGINT PRIMARY KEY,
    payload JSONB NOT NULL
);
```

Ta muốn chèn cấu hình JSON `{"mode":"dark"}`.

### Cách A: chỉ dùng kiểu Java/JDBC tiêu chuẩn

```java
String sql = "INSERT INTO app_settings (id, payload) VALUES (?, ?::jsonb)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 101L);
    statement.setString(2, "{\"mode\":\"dark\"}");
    statement.executeUpdate();
}
```

Mã Java chỉ sử dụng giao diện JDBC chuẩn, nhưng **`?::jsonb` là cú pháp ép kiểu PostgreSQL**, do đó câu SQL **không hoàn toàn portable**. Driver PostgreSQL xử lý tham số chuỗi theo cơ chế của nó và server diễn giải phép ép kiểu.

### Cách B: dùng kiểu dữ liệu riêng của PostgreSQL JDBC Driver

```java
import java.sql.PreparedStatement;
import org.postgresql.util.PGobject;

PGobject jsonb = new PGobject();
jsonb.setType("jsonb");
jsonb.setValue("{\"mode\":\"dark\"}");

String sql = "INSERT INTO app_settings (id, payload) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 102L);
    statement.setObject(2, jsonb);
    statement.executeUpdate();
}
```

Ở cách B, `PGobject` là **lớp của PostgreSQL JDBC Driver**, không có trong `java.sql`. Kết quả là ứng dụng có thể tận dụng cách ánh xạ kiểu `jsonb` mà driver cung cấp, đổi lại mã nguồn phải phụ thuộc gói `org.postgresql` khi biên dịch và chạy.

Hai ví dụ có các giả định: bảng đã tồn tại, kết nối có quyền `INSERT`, ID chưa trùng, JSON hợp lệ và driver PostgreSQL phù hợp. Khi đổi sang DBMS khác, phải thay kiểu cột và/hoặc chiến lược ánh xạ dữ liệu theo sản phẩm mới.

### Dùng `unwrap()` để truy cập giao diện riêng khi thực sự cần

JDBC có cơ chế `Wrapper` với `isWrapperFor()` và `unwrap()`, cho phép truy cập một giao diện do driver cung cấp nếu nó thực sự hỗ trợ. Ví dụ dưới đây chỉ biên dịch khi thư viện PostgreSQL JDBC Driver nằm trong dependency:

```java
import java.sql.Connection;
import java.sql.SQLException;
import org.postgresql.PGConnection;

public static PGConnection requirePostgres(Connection connection)
        throws SQLException {
    if (!connection.isWrapperFor(PGConnection.class)) {
        throw new SQLException(
                "Connection khong cung cap PGConnection");
    }
    return connection.unwrap(PGConnection.class);
}
```

`PGConnection` có các khả năng riêng (ví dụ truy cập cơ chế notification của PostgreSQL). Lưu ý rằng `unwrap()` và `isWrapperFor()` **thuộc JDBC chuẩn**, nhưng kiểu đích `PGConnection` là **extension**. Một `Connection` trả về từ connection pool có thể là wrapper; khả năng unwrap phụ thuộc lớp bọc và driver.

**Không ép kiểu trực tiếp** `(PGConnection) connection` trong trường hợp connection bị bọc bởi proxy/pool. Dùng `isWrapperFor()`/`unwrap()` và xử lý tình huống không hỗ trợ sẽ rõ ràng hơn.

## 6. Những khác biệt dễ gặp dù chỉ dùng JDBC chuẩn

Ngay cả khi mã không import lớp của vendor, hành vi có thể khác theo driver và DBMS:

| Tình huống | API JDBC chung | Điểm cần xác minh theo driver/DBMS |
| --- | --- | --- |
| Lấy khóa tự sinh | `RETURN_GENERATED_KEYS`, `getGeneratedKeys()` | Cơ chế tạo khóa, số cột trả về, cách xử lý batch |
| Gửi nhiều lệnh | `addBatch()`, `executeBatch()` | Hỗ trợ, số lượng batch, kiểu update count khi lỗi |
| Đọc số lượng lớn hàng | `setFetchSize()`, `ResultSet` | Có stream theo đợt hay tải dữ liệu sớm; yêu cầu autocommit/transaction |
| Stored procedure | `prepareCall()`, `registerOutParameter()` | Cú pháp gọi, OUT/INOUT, nhiều result set |
| Ngày giờ | `getObject(..., LocalDate.class)`, `setObject()` | Kiểu `DATE`, `TIMESTAMP`, vùng giờ và hỗ trợ Java Time |
| JSON/array | `getObject()`, `setObject()`, `createArrayOf()` | Kiểu cột, kiểu Java ánh xạ, thao tác với `Types.OTHER` |
| Kiểm soát đồng thời | `setTransactionIsolation()`, `setSavepoint()` | Mức isolation hỗ trợ và ngữ nghĩa khóa/MVCC |
| Timeout | `setQueryTimeout()`, `setNetworkTimeout()` | Driver có thể hỗ trợ khác nhau; server có cấu hình timeout riêng |

Chẳng hạn, `statement.setFetchSize(500)` là lời gọi chuẩn nhưng **chỉ là một yêu cầu/gợi ý cho driver**. Nó không cam kết mọi driver chỉ giữ tối đa 500 hàng trong bộ nhớ. Với dữ liệu lớn, cần quan sát thực tế bộ nhớ, connection/transaction và cấu hình của driver.

Tương tự, `connection.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE)` dùng hằng số JDBC chuẩn; cách DBMS triển khai mức cô lập và xử lý xung đột vẫn cần đọc tài liệu sản phẩm và kiểm thử tình huống đồng thời.

## 7. JDBC URL và các tùy chọn kết nối

JDBC URL thường bắt đầu bằng `jdbc:` nhưng phần còn lại do driver quy định:

```text
jdbc:postgresql://localhost:5432/demo
jdbc:mysql://localhost:3306/demo
jdbc:sqlserver://localhost:1433;databaseName=demo
```

`DriverManager.getConnection(url, properties)` và `DataSource` là cơ chế chung; **tên property và cách diễn giải từng property** không hoàn toàn chuẩn hóa. Ví dụ, một driver có thể cung cấp tùy chọn tối ưu việc viết lại lệnh INSERT trong batch, trong khi driver khác dùng tên khác hoặc chiến lược khác.

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

Properties properties = new Properties();
properties.setProperty("user", System.getenv("APP_DB_USER"));
properties.setProperty("password", System.getenv("APP_DB_PASSWORD"));

try (Connection connection = DriverManager.getConnection(
        "jdbc:postgresql://localhost:5432/demo", properties)) {
    System.out.println(connection.getMetaData().getDriverName());
}
```

Ví dụ giả định biến môi trường đã được cấu hình. Chỉ thêm các tùy chọn đặc thù (TLS, batch rewrite, prepared statement cache, socket timeout...) sau khi **xem tài liệu đúng driver và phiên bản**. Không sao chép nguyên bộ properties từ MySQL sang PostgreSQL rồi kỳ vọng chúng có cùng tác dụng.

Trong hệ thống thực tế, lưu cấu hình kết nối ở nơi quản lý bí mật phù hợp và dùng connection pool để quản lý vòng đời connection. Không nên ghi mật khẩu vào file mã nguồn hay log.

## 8. Thiết kế ranh giới phụ thuộc driver

Một ứng dụng Java có thể hỗ trợ nhiều DBMS nếu chủ động thiết kế lớp truy cập dữ liệu. Cách tổ chức đơn giản:

```text
BusinessService
      |
      v
BookRepository (interface ứng dụng)
      |
      +-------------------+
      |                   |
JdbcBookRepository    PostgresBookRepository
chỉ dùng JDBC chung   JDBC + SQL/API đặc thù
      |                   |
    DataSource / Connection
      |
   JDBC driver và DBMS
```

Cần phân biệt **interface nghiệp vụ của ứng dụng** (`BookRepository`) với **interface JDBC** (`Connection`, `PreparedStatement`). Ứng dụng có thể thống nhất hợp đồng nghiệp vụ, đồng thời triển khai riêng phần cần đặc tính PostgreSQL.

Một cách viết có kiểm tra tính năng và phương án dự phòng:

```java
boolean batchSupported =
        connection.getMetaData().supportsBatchUpdates();

if (batchSupported) {
    // Dung PreparedStatement.addBatch()/executeBatch()
    // voi bo dem kich thuoc batch phu hop.
} else {
    // Thuc hien tung PreparedStatement.executeUpdate().
}
```

Đây là ví dụ **chọn hướng xử lý**, chưa phải mã thực thi batch hoàn chỉnh. Nếu cần dùng `PGobject`, COPY API hoặc `PGConnection`, nên đặt các import `org.postgresql.*` và xử lý liên quan tại lớp adapter dành cho PostgreSQL, thay vì để chúng lan sang các lớp nghiệp vụ.

### Các mức phụ thuộc cần chủ động chọn

1. **Mức 1 — API JDBC chuẩn + SQL phổ thông:** phù hợp CRUD đơn giản; dễ chuyển đổi hơn nhưng vẫn phải thử với các schema và dialect cụ thể.
2. **Mức 2 — API JDBC chuẩn + SQL đặc thù DBMS:** phù hợp khi cần tính năng như JSONB, UPSERT hoặc RETURNING; thay DBMS sẽ phải điều chỉnh SQL.
3. **Mức 3 — API/lớp riêng của driver:** phù hợp khi cần COPY, notifications hoặc ánh xạ kiểu phức tạp; cần dependency đúng vendor và mã adapter riêng.

Không có quy tắc rằng mức 1 luôn tốt nhất: nếu sản phẩm chỉ dùng một DBMS lâu dài, tính năng đặc thù có thể mang lại lợi ích rõ rệt. Quan trọng là **định vị và ghi nhận sự phụ thuộc** để dễ nâng cấp hoặc thay thế.

## 9. Quy trình đánh giá một tính năng trước khi đưa vào ứng dụng

Khi muốn dùng tính năng JDBC hoặc mở rộng của driver, có thể đi theo trình tự:

1. **Xác định yêu cầu nghiệp vụ.** Ví dụ: cần nhập hàng triệu bản ghi, truy vấn JSON hay lấy ID vừa chèn.
2. **Tìm khả năng trong JDBC chuẩn.** Xem `PreparedStatement`, batch, `getGeneratedKeys()`, các kiểu SQL được hỗ trợ.
3. **Hỏi metadata và đối chiếu tài liệu driver.** Kiểm tra tên driver, phiên bản, DBMS và giới hạn hỗ trợ.
4. **Thử tải thực tế.** Đo độ đúng, hiệu năng, bộ nhớ, lỗi/rollback, timeout và xử lý `NULL`.
5. **Cân nhắc API riêng nếu cần.** Chẳng hạn dùng PostgreSQL COPY khi bài toán nhập dữ liệu quy mô lớn chứng minh lợi ích.
6. **Đặt code đặc thù tại một ranh giới rõ ràng.** Quản lý dependency/phiên bản và dự phòng nếu hệ thống cần nhiều DBMS.

Đặc biệt, khi cập nhật Java, driver hoặc DBMS, cần chạy lại các trường hợp tích hợp trọng yếu. **Khả năng đã hoạt động ở phiên bản driver cũ không bảo đảm giữ nguyên ở phiên bản mới** nếu đặc tả, giao thức hoặc cấu hình liên quan thay đổi.

## 10. Lỗi hiểu nhầm thường gặp

| Nhầm lẫn | Thực tế | Cách xử lý |
| --- | --- | --- |
| “Dùng JDBC nên câu SQL nào cũng chạy trên mọi DBMS.” | JDBC chuẩn hóa lời gọi Java, không chuẩn hóa toàn bộ SQL dialect. | Tách và kiểm thử SQL theo DBMS. |
| “Method có trong `Connection` nghĩa là driver chắc chắn hỗ trợ.” | Một số tính năng tùy chọn hoặc có giới hạn. | Dùng `DatabaseMetaData`, tài liệu driver và bài thử thực tế. |
| “Lấy `PGConnection` bằng cast từ mọi `Connection`.” | Connection có thể bị bọc bởi pool/proxy. | Dùng `isWrapperFor()`/`unwrap()` và xử lý không hỗ trợ. |
| “`setFetchSize(100)` đảm bảo chỉ tải 100 hàng mỗi lần.” | Fetch size có thể được diễn giải khác nhau. | Đọc cấu hình streaming và thử bộ nhớ theo driver. |
| “`PGobject` thuộc thư viện Java chuẩn.” | Đây là lớp của PostgreSQL JDBC Driver. | Thêm đúng dependency; giới hạn phạm vi import. |
| “Mọi SQL exception của các DBMS đều có mã lỗi giống nhau.” | `SQLState` có phần chuẩn hóa, còn mã vendor và thông tin chi tiết khác nhau. | Phân loại lỗi theo `SQLException` và tài liệu DBMS/driver. |
| “Đổi JDBC URL và driver là đủ để di chuyển DBMS.” | Schema, kiểu dữ liệu, SQL, transaction và hành vi khác nhau. | Lập kế hoạch migration và chạy kiểm thử tích hợp. |

## 11. Câu hỏi tự luyện

**Câu 1.** `Connection.prepareStatement()` và `org.postgresql.util.PGobject` cùng thuộc JDBC chuẩn phải không?

*Trả lời:* Không. `prepareStatement()` thuộc `java.sql.Connection`; `PGobject` là một kiểu Java riêng do PostgreSQL JDBC Driver cung cấp.

**Câu 2.** Nếu chỉ dùng `PreparedStatement` mà SQL chứa `?::jsonb`, code có thể chuyển thẳng sang MySQL không?

*Trả lời:* Không chắc. API Java là chuẩn JDBC, nhưng cú pháp cast và kiểu `JSONB` phụ thuộc PostgreSQL; cần sửa SQL/schema cho DBMS đích.

**Câu 3.** `DatabaseMetaData.supportsBatchUpdates()` trả `true` có nghĩa batch luôn tối ưu hơn gọi từng lệnh?

*Trả lời:* Không. Nó chỉ báo khả năng hỗ trợ; hiệu năng còn phụ thuộc driver, DBMS, câu SQL, kích thước batch và dữ liệu.

**Câu 4.** Trong một ứng dụng dùng connection pool, nên lấy giao diện driver-specific như thế nào?

*Trả lời:* Kiểm tra `isWrapperFor(VendorInterface.class)` và gọi `unwrap(VendorInterface.class)`; xử lý trường hợp không hỗ trợ. Tránh ép kiểu trực tiếp.

**Câu 5.** Vì sao `getGeneratedKeys()` có thể không hoạt động như dự kiến dù dùng API chuẩn?

*Trả lời:* Vì DBMS và driver khác nhau về hỗ trợ, cơ chế tạo khóa và cách trả kết quả. Kiểm tra metadata, định nghĩa schema và thực thi thử với phiên bản thực tế.

## Ghi nhớ

**Chuẩn JDBC xác định cách ứng dụng Java yêu cầu truy cập dữ liệu; JDBC driver và DBMS xác định những khả năng thực tế phía dưới.** Hãy bắt đầu từ `java.sql`/`javax.sql`, kiểm tra tính năng qua `DatabaseMetaData` và kiểm thử trên môi trường chạy thật. Khi cần chức năng riêng như `PGobject`, `PGConnection` hoặc COPY, sử dụng chúng một cách có chủ đích, đặt trong lớp tích hợp rõ ràng và ghi nhận sự phụ thuộc vào vendor/phiên bản. Đồng thời nhớ rằng **SQL dialect riêng của DBMS vẫn tạo ra phụ thuộc ngay cả khi toàn bộ Java code chỉ dùng API JDBC chuẩn**.

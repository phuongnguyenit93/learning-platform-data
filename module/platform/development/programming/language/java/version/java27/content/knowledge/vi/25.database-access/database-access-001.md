# JDBC, driver và DataSource

Ứng dụng Java thường cần đọc, ghi và quản lý giao dịch với một cơ sở dữ liệu quan hệ. Để kết nối được nhiều hệ quản trị cơ sở dữ liệu (DBMS) theo một mô hình API thống nhất, Java cung cấp **JDBC** (*Java Database Connectivity*). Tuy nhiên, ba tên gọi **JDBC**, **JDBC driver** và **`DataSource`** không có cùng vai trò:

- **JDBC API** là tập hợp interface và class chuẩn mô tả cách tạo kết nối, thực thi SQL, đọc kết quả và quản lý transaction.
- **JDBC driver** là triển khai của nhà cung cấp hoặc dự án cơ sở dữ liệu, chuyển các lời gọi JDBC thành giao tiếp với DBMS cụ thể.
- **`DataSource`** là một abstraction cung cấp `Connection` cho ứng dụng. Nó tách việc cấu hình, tạo hoặc mượn kết nối khỏi mã nghiệp vụ và có thể được hỗ trợ bởi connection pool.

Bài học thuộc chương **Truy cập cơ sở dữ liệu** trong module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Nội dung sử dụng API JDBC đang áp dụng trong Java SE 27, ưu tiên `DataSource`, `PreparedStatement` và `try-with-resources`. Các kỹ thuật cũ như bắt buộc gọi `Class.forName(...)` để nạp mọi driver hoặc tự quản lý connection dùng chung sẽ **không** được xem là cách triển khai mặc định.

## 1. Bức tranh tổng thể: JDBC nằm ở đâu?

```text
              Java application
                     |
             Repository / DAO
                     |
                     v
            javax.sql.DataSource
               getConnection()
                     |
                     v
             java.sql.Connection
                     |
           PreparedStatement
                     |
          executeQuery/Update
                     |
                     v
                 JDBC driver
                     |
           Protocol / DB client
                     |
                     v
                  Database
```

Kiến trúc này cho thấy ứng dụng **viết code theo interface JDBC**, còn driver quyết định cách giao tiếp với PostgreSQL, MySQL, SQL Server hoặc một DBMS cụ thể. Các driver không nhất thiết dùng cùng giao thức, cú pháp SQL mở rộng, quy tắc kiểu dữ liệu hay chiến lược pooling.

### 1.1. Các thành phần chuẩn thường gặp

| Thành phần | Package/module | Vai trò |
| --- | --- | --- |
| `Driver` | `java.sql` / `java.sql` | Interface của một JDBC driver |
| `DriverManager` | `java.sql` / `java.sql` | Quản lý/chọn driver và mở kết nối trực tiếp qua JDBC URL |
| `DataSource` | `javax.sql` / `java.sql` | Factory/abstraction để lấy `Connection` |
| `Connection` | `java.sql` / `java.sql` | Phiên làm việc với database; transaction, statement và metadata |
| `PreparedStatement` | `java.sql` / `java.sql` | Câu lệnh SQL được tham số hóa với placeholders |
| `ResultSet` | `java.sql` / `java.sql` | Duyệt các hàng kết quả truy vấn |
| `SQLException` | `java.sql` / `java.sql` | Thông tin lỗi JDBC, SQLState và mã lỗi của vendor |
| `DatabaseMetaData` | `java.sql` / `java.sql` | Khả năng và thông tin về database/driver |
| `ConnectionPoolDataSource`, `PooledConnection` | `javax.sql` / `java.sql` | Các hợp đồng dành cho hạ tầng quản lý pooled connections |

**`javax.sql` vẫn là package chuẩn hiện hành trong module `java.sql` của Java SE 27.** Tiền tố `javax` không có nghĩa API này đã lỗi thời hoặc phải tự đổi thành `jakarta.sql`. Với JDBC `DataSource`, dùng đúng `javax.sql.DataSource`.

### 1.2. JDBC không phải ORM

JDBC cung cấp primitives để gửi SQL và đọc dữ liệu; nó **không tự động ánh xạ** mỗi bảng thành Java object, không tự sinh migrations hoặc quản lý mọi ranh giới transaction nghiệp vụ. Repository có thể ánh xạ `ResultSet` thành `record` hoặc class Java; các framework ORM nếu được sử dụng sẽ xây trên một hoặc nhiều lớp abstraction, chứ không thay đổi vai trò cơ bản của driver và connection.

## 2. JDBC driver là gì?

Một JDBC driver cung cấp triển khai `java.sql.Driver` cùng các đối tượng JDBC cần thiết để kết nối DBMS cụ thể.

```java
package java.sql; // Tên package thuộc API chuẩn; không tự khai báo như vậy.

public interface Driver {
    // Rút gọn: các method như connect, acceptsURL,
    // getPropertyInfo, getMajorVersion và getMinorVersion.
}
```

Đoạn trên chỉ minh họa khái niệm; **không** sao chép mã giả này vào project. Ứng dụng không cần tự viết driver trừ khi thật sự xây bộ kết nối cho DBMS/giao thức mới.

### 2.1. JDBC URL và driver phải tương thích

Một JDBC URL thường bắt đầu bằng tiền tố `jdbc:`:

```text
jdbc:postgresql://db.example.internal:5432/appdb
jdbc:mysql://db.example.internal:3306/appdb
jdbc:sqlserver://db.example.internal:1433;databaseName=appdb
```

Đây là **các dạng minh họa**: cú pháp, tham số TLS, cách mã hóa giá trị và options phải lấy theo tài liệu driver/vendor đang sử dụng. Không phải mọi JDBC URL có cùng format, và driver của một DBMS không mặc nhiên hiểu URL của DBMS khác.

Ví dụ:

```java
import java.sql.Driver;
import java.sql.DriverManager;
import java.sql.SQLException;

String url = "jdbc:postgresql://db.example.internal:5432/appdb";

try {
    Driver driver = DriverManager.getDriver(url);
    System.out.println(driver.getClass().getName());
} catch (SQLException ex) {
    System.err.println("No suitable registered driver: " + ex.getMessage());
}
```

`getDriver(url)` tra driver có thể nhận URL trong tập các drivers khả dụng đối với caller; nó **không thử** đăng nhập DB, không chứng minh credentials hay mạng đang hoạt động.

### 2.2. Đưa driver vào runtime

Module `java.sql` của JDK định nghĩa **hợp đồng JDBC**, không có nghĩa JDK đã đóng gói sẵn driver cho mọi DBMS. Ứng dụng cần đưa **driver tương thích** vào classpath/module path hoặc cách nạp dependency của framework/deployment.

Ví dụ, mã ứng dụng có thể compile vì `DataSource` nằm trong Java SE, nhưng vẫn thất bại khi kết nối nếu thiếu JDBC driver/runtime configuration của database đã chọn.

Không hardcode phiên bản dependency vào bài học này: dùng bản driver còn được hỗ trợ và tương thích với **JDK, database server, cách kết nối và chính sách bảo mật** của hệ thống.

## 3. Driver discovery: không bắt buộc `Class.forName` trong ứng dụng hiện đại

`DriverManager` có cơ chế tìm drivers khi khởi tạo, bao gồm **service-provider loading** dành cho `java.sql.Driver`. Các JDBC drivers hiện đại thường công bố provider, ví dụ qua metadata service hoặc cơ chế module tương ứng, giúp `DriverManager` phát hiện mà không cần ứng dụng gọi tay:

```java
// Thường không cần gọi riêng dòng sau cho JDBC driver hiện đại:
// Class.forName("org.postgresql.Driver");
```

Thay vào đó, khi dependency đã có ở runtime:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

static Connection openForTool(
        String url, String user, String password)
        throws SQLException {
    return DriverManager.getConnection(url, user, password);
}
```

`DriverManager` chọn driver phù hợp từ tập drivers đã nạp/đăng ký. Tùy class loader/module layer và packaging, một driver có thể không được phát hiện dù file JAR có trong một thư mục nào đó; **có trên ổ đĩa** không đồng nghĩa **đã được đưa vào runtime**.

Đôi khi mã tích hợp đặc biệt cần nạp driver tường minh, nhưng đó là tình huống cần giải thích rõ, **không phải quy trình mặc định của JDBC hiện đại**.

### 3.1. Service provider và module

Với ứng dụng có `module-info.java`, cần khai báo quyền đọc JDBC:

```java
module com.example.orders {
    requires java.sql;
}
```

Ngoài ra, driver implementation phải **khả dụng và được resolve** trong cấu hình triển khai thực tế. Việc sử dụng module path, classpath, service provider hay module của driver phụ thuộc packaging/runtime; không suy rằng `requires java.sql` tự tải một driver từ Internet.

Khi gặp `No suitable driver`, nên xác minh:

1. Dependency driver có thật sự hiện diện tại **runtime**?
2. JDBC URL có đúng prefix/cú pháp mà driver hỗ trợ?
3. Driver provider có được nhận diện trong môi trường class loader/module?
4. Có đang nhầm một lỗi thiếu driver với lỗi mạng, xác thực hoặc cấu hình TLS sau khi đã chọn driver?

Không nên chữa lỗi `No suitable driver` bằng cách vô điều kiện thêm `Class.forName` cho tất cả projects.

## 4. `DriverManager` và `DataSource`: chọn cách mở kết nối

`DriverManager` và `DataSource` đều có thể dẫn tới `Connection`, nhưng định hướng sử dụng khác nhau.

| Tiêu chí | `DriverManager` | `DataSource` |
| --- | --- | --- |
| Cách lấy kết nối | `DriverManager.getConnection(url, ...)` | `dataSource.getConnection()` |
| Cấu hình gắn với code gọi | Caller thường truyền JDBC URL/credentials | Cấu hình nằm trong implementation/deployment của `DataSource` |
| Quản lý pooling | Không cung cấp connection pool qua mỗi `getConnection` | **Có thể** được backed bởi pool, tùy implementation |
| Thay đổi database/driver | Mã tạo kết nối có thể phải đổi | Repository chỉ biết abstraction `DataSource` |
| Phù hợp nhất | Công cụ nhỏ, thao tác trực tiếp, ví dụ setup | Ứng dụng dịch vụ, nhiều repositories, ứng dụng quản lý tài nguyên |

**`DataSource` là cách được khuyến nghị trong Java SE 27 để lấy kết nối.** Không vì thế mà `DriverManager` bị cấm hoặc deprecated: nó vẫn là API chuẩn hợp lệ, đặc biệt trong tiện ích nhỏ và một số công cụ quản trị.

### 4.1. Dùng `DriverManager` cho thao tác đơn giản

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

static boolean checkConnection(
        String jdbcUrl, String user, String password)
        throws SQLException {

    try (Connection connection =
            DriverManager.getConnection(jdbcUrl, user, password)) {
        return connection.isValid(2);
    }
}
```

`isValid(2)` yêu cầu driver kiểm tra kết nối trong giới hạn timeout **tính bằng giây** theo hợp đồng JDBC; khả năng đáp ứng cụ thể phụ thuộc driver và mạng.

Ví dụ không tự có URL hay database thật; chỉ có thể kết nối khi môi trường cung cấp driver, database và credentials phù hợp.

### 4.2. Dùng `DataSource` để tránh ràng buộc repository với hạ tầng

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;

final class HealthRepository {
    private final DataSource dataSource;

    HealthRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    boolean databaseAvailable() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            return connection.isValid(2);
        }
    }
}
```

`HealthRepository` không tự khởi tạo vendor driver, cũng không biết JDBC URL hay password. Thành phần khởi động/dependency injection cung cấp một `DataSource` đã cấu hình. Bằng cách này, thay cấu hình database và pool có thể không yêu cầu sửa code nghiệp vụ.

## 5. `DataSource` không đồng nghĩa có connection pool

`javax.sql.DataSource` là **factory** cung cấp `Connection`. Javadoc Java SE phân biệt:

1. **Basic implementation:** tạo những kết nối JDBC thông thường.
2. **Pooling implementation:** cấp các logical `Connection` handles tham gia tái sử dụng physical connections, phối hợp với connection pool manager.
3. **Distributed-transaction implementation:** phối hợp với transaction manager khi cần và thường kết hợp connection pool.

Điều này có nghĩa:

```java
DataSource dataSource = getConfiguredDataSource();
Connection connection = dataSource.getConnection();
```

**Không thể kết luận** từ kiểu biến `DataSource` rằng đang có pool. `getConfiguredDataSource()` ở đây là method do framework/ứng dụng cung cấp; phải biết implementation và cách cấu hình thật.

### 5.1. Logical connection so với physical connection

Trong một connection pool:

```text
         Application
              |
      dataSource.getConnection()
              |
              v
      Logical Connection handle
              |
              v
    [Connection pool manager]
        |        |       |
        v        v       v
      DB #1    DB #2   DB #3
        ^
        |
   handle.close() ---> Trả về pool để dùng lại
```

Khi ứng dụng `close()` logical connection, pool thường thu hồi handle và tái sử dụng underlying physical connection. Với basic implementation **không có pool**, `close()` có thể đóng physical connection thực.

Mã nghiệp vụ thường **không** trực tiếp dùng `javax.sql.PooledConnection`: đó là giao diện dành cho hạ tầng pool/driver, liên quan tới sự kiện đóng logical handle và quản lý physical connection.

Không tự xây connection pool đơn giản bằng cách lưu các `Connection` trong một `List` rồi chia sẻ giữa threads; việc quản lý transaction state, validation, failures, lifetime và hủy kết nối bị hỏng cần implementation chuyên dụng.

### 5.2. Pool size không bằng số request threads

Trong ứng dụng có nhiều virtual threads, số threads đang chờ database có thể rất lớn nhưng **không nên** tăng số physical connections theo số virtual threads. Chọn pool size theo ngân sách DB, số ứng dụng/replicas, thời gian giữ connection và hiệu năng truy vấn.

Ví dụ 4 replicas × pool tối đa 8 connections có thể yêu cầu tới 32 connections từ các pool đó; cần chừa budget cho workload khác của database.

Pool còn là một **concurrency limiter tự nhiên cho connections**. Không mặc định thêm semaphore có đúng cùng giới hạn ngay trước `dataSource.getConnection()`; như vậy dễ tạo hai tầng chờ mà không bảo vệ thêm tài nguyên nào.

## 6. Vòng đời `Connection` và `try-with-resources`

`Connection`, `PreparedStatement` và `ResultSet` đều hỗ trợ `AutoCloseable`. Trong code JDBC hiện đại, **try-with-resources** là cách thông thường để đóng tài nguyên.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

static long countCustomers(DataSource dataSource)
        throws SQLException {

    String sql = "SELECT COUNT(*) FROM customers";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql);
         ResultSet results = statement.executeQuery()) {

        if (!results.next()) {
            throw new SQLException("COUNT query returned no row");
        }
        return results.getLong(1);
    }
}
```

Khi rời `try` — kể cả do `return` hoặc `SQLException` — Java đóng `ResultSet`, `PreparedStatement`, rồi `Connection` theo **thứ tự ngược khai báo**.

Với pooled data source, `Connection.close()` trả handle về pool. Với basic data source, nó giải phóng connection theo implementation. **Dù implementation nào, caller vẫn phải đóng tài nguyên mình đã mượn.**

Không làm thế này:

```java
// Không nên:
Connection shared = dataSource.getConnection();
// Lưu shared vào static field để toàn bộ requests tái sử dụng.
```

Connection thường mang state của phiên/transaction. Chia sẻ cùng handle cho nhiều request threads có thể dẫn tới tranh chấp, sai transaction và vi phạm các bảo đảm concurrency của driver. Tài nguyên được chia sẻ nên là **DataSource/pool**, không phải một `Connection` đang được mượn.

### 6.1. Thời điểm mượn và trả

Chỉ mượn `Connection` khi thật sự chuẩn bị truy cập database và trả ngay khi hoàn thành transaction tương ứng. Tránh giữ connection trong lúc gọi API ngoài mạng hoặc đợi tác vụ dài không liên quan.

```java
// Hai bước riêng khi nghiệp vụ KHÔNG đòi một DB transaction xuyên suốt:
Customer customer = readCustomer(dataSource, customerId);
String shippingQuote = callShippingService(customer); // Chờ mạng.
saveShippingQuote(dataSource, customerId, shippingQuote);
```

Các method là minh họa. Nếu yêu cầu nghiệp vụ đòi giao dịch nguyên tử, cần thiết kế transaction/outbox/consistency phù hợp, **không** tách transaction một cách máy móc.

### 6.2. Lỗi khi đóng tài nguyên

Khi body `try` ném exception và một thao tác `close()` cũng ném exception, `try-with-resources` giữ exception chính và đưa lỗi `close` vào **suppressed exceptions** khi phù hợp. Không tự viết nhiều `finally` đóng tài nguyên rồi vô tình che lỗi gốc.

## 7. `PreparedStatement`: tham số hóa SQL thay vì ghép chuỗi

Một truy vấn nhận dữ liệu từ người dùng phải phân biệt **cấu trúc SQL** và **giá trị tham số**.

Không nối input trực tiếp vào SQL:

```java
// Không an toàn nếu email đến từ input bên ngoài:
String sql = "SELECT id FROM customers WHERE email = '" + email + "'";
```

Mã này dễ dẫn tới SQL injection, sai escape ký tự và khó quản lý kiểu dữ liệu.

Thay bằng `PreparedStatement`:

```java
import javax.sql.DataSource;
import java.sql.*;
import java.util.OptionalLong;

static OptionalLong findCustomerId(
        DataSource ds, String email) throws SQLException {

    String sql = "SELECT id FROM customers WHERE email = ?";

    try (Connection connection = ds.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setString(1, email);

        try (ResultSet rows = statement.executeQuery()) {
            return rows.next()
                    ? OptionalLong.of(rows.getLong("id"))
                    : OptionalLong.empty();
        }
    }
}
```

JDBC parameter indices bắt đầu từ **1**, không phải 0. Dấu `?` đại diện cho **giá trị**, không phải tên bảng, cột, toán tử hoặc một đoạn SQL tự do.

Ví dụ, không thể dùng `ORDER BY ?` để nhận một tên cột tùy ý theo cách tương đương identifier. Với sort field do người dùng chọn, phải **ánh xạ sang allowlist identifiers đã định nghĩa trước** và chỉ tạo SQL structure từ những lựa chọn hợp lệ.

### 7.1. Lợi ích ngoài bảo mật

`PreparedStatement` giúp driver xử lý binding kiểu dữ liệu, escaping và có thể tận dụng query preparation/caching nếu DBMS/driver/pool hỗ trợ. **Không** hứa mọi lời gọi đều được server prepare hoặc mọi truy vấn đều nhanh hơn; chi tiết thực thi phụ thuộc hệ thống.

Các method khác như `setLong`, `setBigDecimal`, `setBoolean` và `setObject` cho phép binding theo loại giá trị. Với `null`, cân nhắc `setNull(index, java.sql.Types.X)` hoặc dạng binding có chỉ định SQL type nếu driver/kiểu cột yêu cầu.

## 8. `ResultSet`: duyệt hàng và ánh xạ sang Java

`ResultSet` biểu diễn kết quả của truy vấn. Khi mới tạo, cursor thường đứng **trước hàng đầu tiên**; cần gọi `next()` để di chuyển:

```java
import java.sql.*;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

record Customer(long id, String name) {}

static List<Customer> listCustomers(DataSource ds)
        throws SQLException {

    String sql = "SELECT id, name FROM customers ORDER BY id";
    List<Customer> result = new ArrayList<>();

    try (Connection connection = ds.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql);
         ResultSet rows = statement.executeQuery()) {

        while (rows.next()) {
            result.add(new Customer(
                    rows.getLong("id"),
                    rows.getString("name")));
        }
    }
    return List.copyOf(result);
}
```

`ResultSet.getString("name")` đọc theo **column label**, còn `getLong(1)` đọc theo **1-based column index**. Việc dùng tên rõ ràng giúp giảm lỗi khi thay thứ tự các cột trong SELECT.

### 8.1. Cẩn thận với `NULL` trong SQL

`getString(...)` có thể trả Java `null` nếu SQL value là `NULL`. Với primitive getters như `getInt`/`getLong`, SQL `NULL` thường được trả về như giá trị mặc định của primitive; hãy gọi `rows.wasNull()` **ngay sau getter liên quan** nếu cần phân biệt `NULL` với `0`:

```java
long score = rows.getLong("score");
Long scoreOrNull = rows.wasNull() ? null : score;
```

Không suy rằng getter primitive đủ phân biệt mọi ý nghĩa của dữ liệu thiếu.

### 8.2. Mapping kiểu ngày giờ và số học

Với driver hỗ trợ các mapping JDBC hiện đại:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;

BigDecimal amount = rows.getBigDecimal("amount");
LocalDate businessDate = rows.getObject("business_date", LocalDate.class);
OffsetDateTime recordedAt =
        rows.getObject("recorded_at", OffsetDateTime.class);
```

Đây là **mảnh minh họa** giả định `rows` đang đứng ở hàng hợp lệ và các SQL column types/driver hỗ trợ mapping tương ứng. Không phải mọi DBMS có cùng kiểu “timestamp with time zone” hay lưu cùng semantics. Chọn `BigDecimal` cho số tiền thập phân cần độ chính xác, tránh tự chuyển các giá trị tiền thành `double` rồi làm tròn bất ngờ.

## 9. `SQLException` và thông tin chẩn đoán

Các thao tác JDBC thường khai báo `throws SQLException`. Exception này có nhiều thông tin hơn một message:

- `getMessage()`: mô tả lỗi.
- `getSQLState()`: mã trạng thái theo quy ước SQLState do driver cung cấp.
- `getErrorCode()`: mã lỗi riêng của database vendor.
- `getNextException()`: chuỗi lỗi SQL bổ sung nếu có.
- `getCause()`: exception gây ra lỗi, nếu có.

```java
import java.sql.SQLException;

static void reportSQLException(SQLException ex) {
    for (Throwable problem : ex) {
        if (problem instanceof SQLException sql) {
            System.err.println(
                    "SQLState=" + sql.getSQLState()
                    + ", vendorCode=" + sql.getErrorCode());
        } else {
            System.err.println(problem.getClass().getSimpleName());
        }
    }
}
```

`SQLException` triển khai `Iterable<Throwable>`; việc duyệt có thể gồm exception gốc và các exception nối tiếp/cause theo quy tắc API. Dữ liệu chẩn đoán phải được **đưa vào log có kiểm soát**, tránh gửi SQL chứa thông tin nhạy cảm hoặc credentials trực tiếp cho người dùng cuối.

### 9.1. Không phân loại lỗi chỉ bằng câu chữ

Một câu báo lỗi như “duplicate key” có thể khác nhau giữa DBMS, phiên bản và locale. Khi cần phân loại lỗi để xử lý, sử dụng SQLState, những subclass như `SQLTransientException`/`SQLRecoverableException` khi phù hợp, và mã lỗi vendor theo driver thực tế. **Không** mặc định mọi `SQLException` đều retry được.

Nếu chuyển tầng:

```java
try {
    repository.save(customer);
} catch (SQLException ex) {
    throw new IllegalStateException("Could not save customer", ex);
}
```

Đây là mã minh họa với `repository` và `customer` đã được định nghĩa ở nơi khác. Luôn giữ **cause** nếu bọc exception để người vận hành còn truy vết sự cố.

## 10. Cấu hình kết nối và bảo vệ bí mật

Những thành phần cấu hình thường gồm:

| Thông tin | Mục đích | Lưu ý |
| --- | --- | --- |
| JDBC URL | Chỉ định DBMS, host, port, database và options | Cú pháp/vendor-specific; kiểm tra TLS |
| Username/credentials | Xác thực tài khoản DB | Lấy từ secret manager hoặc cấu hình bảo mật |
| TLS/CA/hostname verification | Bảo mật đường truyền | Cấu hình theo driver/server, tránh “trust all” |
| Pool maximum size | Giới hạn connections được mượn | Cân theo tổng replicas và DB capacity |
| Borrow/acquisition timeout | Giới hạn thời gian đợi pool | Không được chuẩn hóa đồng nhất bởi `DataSource` |
| Connect/login timeout | Giới hạn thiết lập kết nối | Khác borrow timeout |
| Query/statement timeout | Giới hạn thời gian truy vấn | Phụ thuộc driver/DB khi thực thi |

Không commit password vào source code, không log đầy đủ JDBC URL nếu chứa token/password và không trả exception gốc cho API response công khai khi nó làm lộ cấu hình hệ thống.

### 10.1. Timeouts thuộc các tầng khác nhau

`DataSource.setLoginTimeout(int seconds)` liên quan tới nỗ lực **thiết lập database connection** theo hợp đồng `CommonDataSource`; nó **không** phải bảo đảm mọi pool áp dụng làm borrow timeout khi chờ một handle trong hàng đợi.

`Statement.setQueryTimeout(int seconds)` áp dụng cho thao tác statement theo driver, còn `Connection.setNetworkTimeout(...)` liên quan tới network operations theo hợp đồng JDBC khi được hỗ trợ. Chính sách deadline cuối cùng còn cần được kiểm thử bằng driver và database thật.

Không coi một cấu hình timeout là đủ cho toàn bộ request; thường phải tách thời gian chờ pool, thời gian kết nối, thực thi query và deadline nghiệp vụ.

### 10.2. Cấu hình `DataSource` ở ranh giới hạ tầng

Một ứng dụng thường cấu hình `DataSource` từ:

- Một framework hoặc DI container.
- Thư viện connection pool hỗ trợ driver/DBMS đang dùng.
- Application server, hoặc dịch vụ cấu hình/naming phù hợp deployment.

Repository **chỉ nhận một `DataSource` đã sẵn sàng**:

```java
final class OrderRepository {
    private final DataSource ds;

    OrderRepository(DataSource ds) {
        this.ds = java.util.Objects.requireNonNull(ds);
    }
}
```

Không có method chuẩn kiểu `DataSource.setMaximumPoolSize(...)` dùng chung cho mọi implementations. Pool size, validation, connection lifetime và acquisition timeout phải cấu hình theo **implementation thực tế**, không bịa ra những method của interface chuẩn.

## 11. Transaction: `autoCommit`, `commit` và `rollback`

Một `Connection` mới thường có **auto-commit = true** theo hợp đồng JDBC. Khi đó, các statements được commit theo quy tắc completion của JDBC. Với một nghiệp vụ cần **nhiều câu SQL cùng thành công hoặc cùng bị hủy**, cần ranh giới transaction rõ ràng.

Ví dụ chuyển một số tiền giữa hai tài khoản trong **cùng database**, giả định bảng `accounts(id, balance)` có kiểu số tiền chính xác:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

static void transfer(
        DataSource dataSource,
        long fromId,
        long toId,
        BigDecimal amount) throws SQLException {

    if (amount == null || amount.signum() <= 0 || fromId == toId) {
        throw new IllegalArgumentException("Invalid transfer");
    }

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try (PreparedStatement debit = connection.prepareStatement(
                     "UPDATE accounts SET balance = balance - ? "
                     + "WHERE id = ? AND balance >= ?");
             PreparedStatement credit = connection.prepareStatement(
                     "UPDATE accounts SET balance = balance + ? "
                     + "WHERE id = ?")) {

            debit.setBigDecimal(1, amount);
            debit.setLong(2, fromId);
            debit.setBigDecimal(3, amount);
            if (debit.executeUpdate() != 1) {
                throw new SQLException("Source account not eligible");
            }

            credit.setBigDecimal(1, amount);
            credit.setLong(2, toId);
            if (credit.executeUpdate() != 1) {
                throw new SQLException("Destination account not found");
            }

            connection.commit();
        } catch (SQLException | RuntimeException failure) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        }
    }
}
```

**Điều kiện của ví dụ:** database và bảng đã tồn tại, driver hỗ trợ transactions và kiểu dữ liệu phù hợp; business logic và isolation đã được xem xét. Đây là minh họa transaction JDBC, **không phải hệ thống chuyển tiền production hoàn chỉnh**. Những yêu cầu như concurrent transfers, auditing, idempotency, deadlock retry có kiểm soát và đối soát số dư cần thiết kế riêng.

Quy trình:

1. Mượn một connection cho toàn bộ transaction.
2. Gọi `setAutoCommit(false)` **trước** khi chạy những câu SQL thuộc transaction.
3. Thực thi hai `PreparedStatement` với giá trị tham số.
4. Nếu thành công, gọi `commit()`.
5. Nếu thất bại, gọi `rollback()`; lỗi rollback được giữ trong `getSuppressed()` của lỗi chính.
6. `try-with-resources` đóng/trả connection dù method thành công hay thất bại.

**Không dựa vào `Connection.close()` để rollback một transaction chưa hoàn tất.** Theo Javadoc, kết quả khi đóng connection còn transaction đang hoạt động có thể phụ thuộc implementation. Luôn chủ động `commit` hoặc `rollback` trước khi đóng.

### 11.1. Transaction state và pooled connections

Một pooled implementation cần quản lý việc reset trạng thái connection khi được trả cho pool. Nhưng ứng dụng **không** nên lấy đó làm lý do để bỏ quên transaction boundary. Mỗi lần mượn connection, hãy xem các giả định về auto-commit, isolation, read-only và schema theo hợp đồng pool/driver đang dùng.

Việc chuyển `setAutoCommit(false)` sang `setAutoCommit(true)` **trong khi transaction vẫn đang hoạt động** có thể commit transaction theo JDBC. Vì vậy không cố “khôi phục auto-commit” một cách bất cẩn trong `finally` mà chưa xác định đúng trạng thái giao dịch.

### 11.2. Không đánh đồng JDBC transaction với distributed transaction

`connection.commit()` điều khiển transaction trên một connection theo khả năng DB/driver. Nó **không** tự đảm bảo atomicity giữa database và một API HTTP bên ngoài. Với nhiều hệ thống, cần mẫu kiến trúc như outbox hoặc transaction manager phù hợp; đó là một bài toán kiến trúc khác, không chỉ thêm `try/catch` quanh hai lời gọi.

## 12. Kiểm tra và quản lý connection pool

Một pool được cấu hình phù hợp thường cần:

- **Maximum pool size:** trần connections một instance được quyền mượn.
- **Acquisition/borrow timeout:** thời gian chờ khi không có connection rảnh.
- **Idle/lifetime policy:** thời gian giữ và loại bỏ physical connections.
- **Connection validation:** phát hiện connection hỏng hoặc đã bị server đóng.
- **State reset:** đưa logical connection về trạng thái phù hợp trước khi cấp cho borrower tiếp theo.
- **Metrics:** active/idle/pending connections, số lỗi kết nối và thời gian chờ.

Đây là **khái niệm cấu hình**, không phải các phương thức mặc định của interface `DataSource`. Tên option khác nhau giữa implementations.

### 12.1. Pool không tự đảm bảo database khỏe

Một pool lớn không cứu được database đang quá tải CPU, chờ khóa kéo dài hoặc truy vấn thiếu index. Pool nhỏ quá có thể làm requests chờ không cần thiết; pool lớn quá có thể gây thêm cạnh tranh ở DB.

Khi thấy “pool exhausted”, hãy đo:

1. Số connections đang mượn và thời gian giữ.
2. Thời gian chờ mượn p95/p99, timeout count.
3. SQL latency, lock waits, long transactions.
4. Số application replicas × maximum pool size.
5. Các đường code thiếu `Connection.close()` hoặc bị kẹt trong tác vụ ngoài DB.

Không nâng pool size chỉ vì có nhiều virtual threads. Virtual threads có thể giúp nhiều tasks chờ I/O, nhưng **không làm tăng** số kết nối DB mà DBMS xử lý an toàn.

### 12.2. Giữ giới hạn chung giữa nhiều replicas

Nếu 6 replicas đều cấu hình `maximumPoolSize = 10`, tổng trần từ các pools này có thể lên tới **60 connections**. Database còn cần budget cho ứng dụng khác, việc quản trị, backup và migration.

Một semaphore trong mỗi JVM chỉ giới hạn JVM đó, **không tự tạo giới hạn toàn cụm**. Nếu DBMS hoặc tài khoản có quota toàn hệ thống, phải phân bổ ngân sách và quan sát toàn bộ triển khai.

## 13. Ghi dữ liệu, cập nhật và batch

`PreparedStatement.executeQuery()` dùng cho SQL trả một `ResultSet`. `executeUpdate()` dùng phổ biến với `INSERT`, `UPDATE` và `DELETE`, trả số hàng bị ảnh hưởng theo hợp đồng driver/SQL.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

static boolean renameCustomer(
        DataSource ds, long id, String newName) throws SQLException {

    String sql = "UPDATE customers SET name = ? WHERE id = ?";

    try (Connection connection = ds.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setString(1, newName);
        statement.setLong(2, id);
        return statement.executeUpdate() == 1;
    }
}
```

Nếu row không tồn tại, kết quả thường là `0`. Ứng dụng quyết định có xem việc không cập nhật hàng nào là bình thường, not-found hay conflict; JDBC **không** quyết định hợp đồng nghiệp vụ đó thay bạn.

### 13.1. Batch nhiều giá trị cùng một SQL

`PreparedStatement.addBatch()` và `executeBatch()` phù hợp khi cần gửi nhiều bộ tham số cho một câu SQL:

```java
static int[] insertNames(DataSource ds, List<String> names)
        throws SQLException {

    String sql = "INSERT INTO customers (name) VALUES (?)";

    try (Connection connection = ds.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        for (String name : names) {
            statement.setString(1, name);
            statement.addBatch();
        }
        return statement.executeBatch();
    }
}
```

Ví dụ trên dùng auto-commit mặc định của connection; **không hứa batch là một giao dịch nguyên tử**. Nếu phải cùng thành công hoặc cùng rollback, hãy quản lý transaction chủ động như mục 11.

`executeBatch()` có thể trả những giá trị đặc biệt như `Statement.SUCCESS_NO_INFO`; lỗi batch có thể dùng `BatchUpdateException` cùng các update counts tùy driver. Vì vậy không luôn giả định mỗi phần tử của mảng kết quả là `1`.

### 13.2. Đọc generated keys

Khi cần khóa tự sinh, dùng khả năng JDBC `Statement.RETURN_GENERATED_KEYS` và `getGeneratedKeys()` **nếu DBMS/driver hỗ trợ**. Không dựa vào việc truy vấn “ID lớn nhất” sau insert: điều đó dễ sai khi nhiều giao dịch chạy đồng thời.

Hình thức:

```java
PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO customers (name) VALUES (?)",
        java.sql.Statement.RETURN_GENERATED_KEYS);
```

Mảnh code này phải đặt trong phạm vi có `Connection` hợp lệ và đóng `PreparedStatement`/`ResultSet` đúng cách. Cách trả keys/khả năng hỗ trợ có thể khác theo DBMS.

## 14. `DatabaseMetaData` và mức độ tương thích giữa các DBMS

Không phải mọi DBMS hiểu cùng tập kiểu dữ liệu hoặc SQL dialect. JDBC cung cấp `DatabaseMetaData` để hỏi một số khả năng đang được công bố bởi driver/database:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

static void printDatabaseInfo(DataSource ds) throws SQLException {
    try (Connection connection = ds.getConnection()) {
        DatabaseMetaData meta = connection.getMetaData();
        System.out.println(meta.getDatabaseProductName());
        System.out.println(meta.getDatabaseProductVersion());
        System.out.println(meta.getDriverName());
        System.out.println(meta.supportsTransactions());
    }
}
```

Metadata giúp chẩn đoán hoặc chọn nhánh tương thích, nhưng **không** có nghĩa mọi tính năng vendor đã được chuẩn hóa thành một SQL dialect chung. Ví dụ, cách khai báo JSON columns, câu lệnh UPSERT và cú pháp generated identity có thể khác nhau.

Để giữ API ổn định, có thể tách phần SQL đặc thù ở một adapter/repository layer; không viết một chuỗi SQL giả định chạy trên mọi DB nếu chưa được kiểm thử.

## 15. Timeout, cancellation và quan hệ với virtual threads

Một thao tác database có thể chờ theo các giai đoạn:

```text
Request deadline
      |
      +-- Chờ pool cấp logical connection
      |
      +-- Thiết lập physical connection (nếu cần)
      |
      +-- Chờ DB thực thi SQL / locks
      |
      +-- Đọc ResultSet qua network
      |
      +-- Đóng/hoàn tất transaction
```

Không dùng một con số “timeout” chung để suy rằng mọi giai đoạn đều được giới hạn. Pool acquisition timeout, login/connect timeout, statement query timeout và network timeout có trách nhiệm khác nhau.

`Statement.cancel()` tồn tại trong JDBC, nhưng hiệu quả và cơ chế hủy phụ thuộc driver/DBMS. `Future.cancel(true)` hoặc interrupt một virtual thread **không phải cam kết** rằng database đã dừng một SQL statement tức thì hoặc đã rollback toàn bộ transaction. Khi xử lý deadline, cần tuân thủ cơ chế cancellation/timeout của cả pool, driver và database.

### 15.1. Virtual threads không thay thế connection pool

Virtual thread chờ database có thể tiêu thụ ít tài nguyên thread hơn platform thread tương ứng, nhưng database vẫn cần connections thật. Với Java 27, mô hình thông dụng là **virtual thread per task + pooled `DataSource`**, thay vì pool virtual threads rồi lầm tưởng nó sẽ bảo vệ kết nối.

Một pool 16 connections vẫn chỉ có thể cấp tối đa 16 handles đang mượn từ pool ấy. Các tasks vượt ngưỡng phải chờ hoặc bị từ chối theo chính sách; thiết kế request admission/deadline phải giới hạn **tổng công việc đang tồn tại**, không chỉ số active queries.

## 16. Ví dụ `Demo.java` chạy độc lập: kiểm tra JDBC drivers

Để phân biệt **JDBC API trong JDK** với **driver phụ thuộc môi trường**, có thể chạy một chương trình **không yêu cầu database**. Khi không cấu hình JDBC URL, nó chỉ liệt kê những drivers có sẵn và dừng. Khi có URL/driver/credentials phù hợp, nó thử mở kết nối và in metadata cơ bản.

Tạo file `Demo.java`:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.Driver;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.List;
import java.util.Properties;

public class Demo {
    public static void main(String[] args) {
        List<Driver> drivers = DriverManager.drivers().toList();

        System.out.println("Available JDBC drivers: " + drivers.size());
        for (Driver driver : drivers) {
            System.out.println("  " + driver.getClass().getName());
        }

        String url = System.getenv("DEMO_JDBC_URL");
        if (url == null || url.isBlank()) {
            System.out.println("No URL configured; skipping connection.");
            return;
        }

        Properties properties = new Properties();
        String user = System.getenv("DEMO_JDBC_USER");
        String password = System.getenv("DEMO_JDBC_PASSWORD");
        if (user != null && !user.isBlank()) {
            properties.setProperty("user", user);
        }
        if (password != null) {
            properties.setProperty("password", password);
        }

        try (Connection connection =
                DriverManager.getConnection(url, properties)) {

            DatabaseMetaData metadata = connection.getMetaData();
            System.out.println("Database: "
                    + metadata.getDatabaseProductName());
            System.out.println("Driver: "
                    + metadata.getDriverName());
            System.out.println("Valid: " + connection.isValid(2));
        } catch (SQLException ex) {
            // Không in credentials hay JDBC URL vào error log công khai.
            System.err.println("Connection failed; SQLState="
                    + ex.getSQLState());
        }
    }
}
```

Biên dịch và chạy khi không cần kết nối database:

```shell
javac Demo.java
java Demo
```

Nếu runtime chưa được bổ sung driver và không đặt `DEMO_JDBC_URL`, kết quả có dạng:

```text
Available JDBC drivers: 0
No URL configured; skipping connection.
```

Nếu đã có driver trên classpath/module path, số lượng drivers và tên class được in ra sẽ khác. Để thử kết nối thật, phải **cài driver tương thích**, cấu hình ba biến môi trường `DEMO_JDBC_URL`, `DEMO_JDBC_USER`, `DEMO_JDBC_PASSWORD` khi phù hợp và đảm bảo database có thể truy cập.

Đây là **chương trình chẩn đoán minh họa**, không phải mô hình cấu hình production. Secret manager và pooled `DataSource` phù hợp hơn khi ứng dụng có nhiều requests; ngay cả environment variables cũng phải được quản lý quyền truy cập và bảo vệ trong hệ thống triển khai.

Điểm quan sát:

1. `DriverManager.drivers()` dùng service discovery/driver registration của runtime.
2. Không bắt buộc gọi `Class.forName(...)` cho driver hiện đại nếu driver đã được phát hiện.
3. Không có driver vẫn **biên dịch được** vì `java.sql` thuộc Java SE.
4. Có JDBC URL **không đủ** để kết nối: phải có driver, network, credentials và cấu hình phù hợp.
5. `try-with-resources` đóng connection khi rời khối.
6. `getMetaData()` đọc thông tin driver/DBMS, không tự chỉnh schema hay tạo table.

## 17. Ví dụ repository theo `DataSource`: đọc bản ghi

Ví dụ sau thể hiện cách business code phụ thuộc **`DataSource` thay vì `DriverManager`**. Nó cần một database thật khi chạy, nhưng mọi API được sử dụng đều thuộc Java SE 27:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

record Product(long id, String name) {}

final class ProductRepository {
    private final DataSource dataSource;

    ProductRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    Optional<Product> findById(long id) throws SQLException {
        String sql = "SELECT id, name FROM products WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, id);

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Product(
                        rows.getLong("id"),
                        rows.getString("name")));
            }
        }
    }
}
```

Repository không biết JDBC URL, driver class, database password hoặc pool implementation. Composition root/framework cung cấp `DataSource` thích hợp; repository sử dụng nó như một **dependency đã được cấu hình**.

Hãy quản lý error policy ở tầng phù hợp: một exception khi kết nối DB **không đồng nghĩa** dữ liệu không tồn tại. Chỉ trả `Optional.empty()` nếu truy vấn hợp lệ và **không có hàng**; `SQLException` phải được xử lý hoặc truyền đúng hợp đồng.

## 18. Chẩn đoán lỗi thường gặp theo lớp

| Triệu chứng | Khả năng cần kiểm tra | Không nên làm |
| --- | --- | --- |
| `No suitable driver` | Driver chưa có ở runtime, URL sai, classloader/module provider chưa được resolve | Thêm `Class.forName` vô điều kiện mà không kiểm tra dependency |
| Timeout khi thiết lập kết nối | Mạng, DNS, firewall, DB listener, TLS hoặc login timeout | Tăng pool size để “chữa” vấn đề mạng |
| Authentication failed | Credentials, quyền truy cập, DB/user, chế độ xác thực | In password vào log |
| `Connection is closed` | Dùng lại handle đã đóng, lỗi lifecycle | Chia sẻ một `Connection` static |
| Pool acquisition timeout | Pool đã bận, connection leak, transaction/query dài | Tăng max liên tục không đo DB |
| Query timeout | SQL chậm, chờ lock, DB quá tải, timeout policy | Retry vô hạn mọi statement |
| Data truncation/type mismatch | Mapping SQL–Java sai, độ rộng/scale không phù hợp | Cast tùy tiện hoặc bỏ lỗi |
| Duplicate key / constraint violation | Dữ liệu và quy tắc ràng buộc trong DB | Bỏ qua exception rồi trả thành công |
| Lỗi parse SQL do khác dialect | Cú pháp/SQL type vendor-specific | Tin rằng JDBC chuẩn hóa toàn bộ SQL |
| Transaction đã đóng mà vẫn dùng result set | Scope của result set/connection không đúng | Giữ `ResultSet` ngoài phạm vi connection |
| Lỗi tùy môi trường khi load driver | Packaging, module path, class loader, dependency version | Giả định compile pass thì runtime cũng đủ dependencies |

Chẩn đoán theo từng lớp: **dependency → driver discovery → URL → network/auth → connection lifecycle → SQL/transaction**. Cách này giúp tìm đúng nguyên nhân thay vì thay cấu hình ngẫu nhiên.

## 19. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Thay thế phù hợp |
| --- | --- | --- |
| Bắt buộc dùng `Class.forName("vendor.Driver")` ở mọi nơi | Cấu hình thừa, gắn chặt driver vào business code | Service discovery và `DataSource` |
| Viết mật khẩu vào Java source | Rò rỉ secrets | Secret manager/cấu hình bảo mật |
| Để mọi repository gọi `DriverManager.getConnection(...)` với URL hardcode | Khó cấu hình, khó pooling và kiểm thử | Inject `DataSource` |
| Cho rằng mọi `DataSource` đã có connection pool | Basic implementation có thể không pool | Xác minh implementation và cấu hình |
| Không đóng `Connection` vì nghĩ pool tự thu hồi | Connection leak và pool exhaustion | `try-with-resources` |
| Dùng một `Connection` chung cho các threads | Sai transaction và rủi ro concurrency | Mỗi tác vụ mượn/trả connection qua pool |
| Nối input vào chuỗi SQL | SQL injection | `PreparedStatement` với bind parameters |
| Dùng `?` để truyền table/column name | Placeholder dùng cho giá trị, không phải identifier | Allowlist identifiers trong SQL structure |
| Coi `executeBatch` luôn atomic | Partial success có thể xảy ra | Explicit transaction khi cần all-or-nothing |
| Coi `close()` luôn rollback tự động | Kết quả của active transaction có thể implementation-defined | `commit`/`rollback` rõ ràng |
| Dùng `double` cho cột tiền có độ chính xác cố định | Lỗi làm tròn | `BigDecimal`/DECIMAL và chính sách scale |
| Không xử lý SQL `NULL` với primitive getter | Không phân biệt NULL và 0 | `wasNull()` sau getter |
| Bắt mọi `SQLException` rồi trả list rỗng | Che lỗi hạ tầng thành “không có dữ liệu” | Giữ cause và hợp đồng lỗi |
| Tăng pool theo số virtual threads | Có thể gây quá tải DB | Sizing theo capacity và metrics DB |
| Xem `setLoginTimeout` như borrow timeout phổ quát | Sai semantics giữa các pools | Cấu hình timeout đúng implementation |
| Log toàn bộ connection URL/SQL params | Rò rỉ secrets/dữ liệu nhạy cảm | Logging đã lọc, giới hạn quyền truy cập |
| Tin mọi JDBC call có cancellation tức thời | Driver/DB có đặc thù riêng | Timeout/query cancellation có kiểm thử thực tế |

## 20. Checklist trước khi triển khai ứng dụng JDBC

1. **Đã chọn JDBC driver tương thích với JDK và DBMS chưa?** Nó có ở runtime chứ không chỉ compile time?
2. **JDBC URL đúng định dạng vendor không?** Host, port, database và TLS options đã được xác minh?
3. **Có dùng `DataSource` cho application code không?** Repository nên nhận dependency thay vì tự cấu hình URL/password.
4. **Đã xác nhận `DataSource` có pool hay chưa?** Nếu có, ai quản lý max size, validation, lifetime và metrics?
5. **Có budget tổng connections giữa các replicas và services không?** Không cấp mỗi pool theo số virtual threads.
6. **Mọi `Connection`, `PreparedStatement` và `ResultSet` được đóng đúng scope không?**
7. **SQL nhận user input có dùng parameter binding không?** Dynamic identifiers có allowlist?
8. **SQL NULL, decimal và temporal types có mapping chính xác không?** Không mặc định mọi vendor hỗ trợ đồng nhất.
9. **Transaction boundary đã rõ chưa?** Multi-statement cần commit/rollback, isolation và consistency được xem xét.
10. **Các loại timeout đã tách chưa?** Borrow, connect, query và deadline tổng.
11. **Có kế hoạch xử lý `SQLException` theo SQLState/vendor code không?** Không retry tất cả lỗi.
12. **Secrets có được quản lý an toàn không?** Không commit vào source hoặc lộ trong log.
13. **Có metrics về connection pool active/idle/wait/timeouts không?** Query latency và lock waits có được quan sát?
14. **Đã kiểm thử quá tải, connection leak, mất DB, reconnect và rollback chưa?**
15. **Đã chạy integration tests với đúng driver/DBMS thực tế chưa?** Một Demo không kết nối DB không chứng minh SQL dialect/transaction đã đúng.

## 21. Tổng kết

**JDBC** là giao diện chuẩn cho Java giao tiếp cơ sở dữ liệu; **driver** là implementation nói chuyện với một DBMS; **`DataSource`** là abstraction ưu tiên để cung cấp `Connection` cho mã ứng dụng. `DriverManager` vẫn hợp lệ, nhưng không cần làm điểm phụ thuộc của mọi repository khi ứng dụng đã có `DataSource`.

Trong Java SE 27, driver hiện đại thường được nhận diện qua **service-provider loading**, không bắt buộc `Class.forName` thủ công. `DataSource` có thể là basic, pooled hoặc hỗ trợ distributed transactions; **không tự suy ra pooling chỉ từ interface**. Khi có pool, `Connection.close()` phải được gọi để trả logical handle và cho phép tái sử dụng physical connection.

Mã JDBC an toàn cần có **`PreparedStatement`**, xử lý `ResultSet` chính xác, dùng **`try-with-resources`**, quản lý `commit/rollback` đúng ranh giới transaction, giữ thông tin `SQLException` và cấu hình database/credentials/timeout tại tầng hạ tầng. Virtual threads có thể giảm chi phí chờ I/O nhưng **không** biến nguồn connections hữu hạn thành vô hạn.

## Tài liệu tham khảo

- [JDBC API — java.sql (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/package-summary.html) — interfaces và classes JDBC cốt lõi.
- [javax.sql (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/javax/sql/package-summary.html) — `DataSource` và các SPI liên quan pooling/distributed transactions.
- [Driver (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Driver.html) — hợp đồng của driver JDBC.
- [DriverManager (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/DriverManager.html) — service-provider discovery, `drivers()` và `getConnection()`.
- [DataSource (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/javax/sql/DataSource.html) — basic, pooled và distributed transaction implementations.
- [Connection (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Connection.html) — session, auto-commit, commit, rollback và close.
- [PreparedStatement (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/PreparedStatement.html) — parameter binding, execute và batch.
- [ResultSet (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/ResultSet.html) — cursor, getters và `wasNull()`.
- [SQLException (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/SQLException.html) — SQLState, vendor codes, exception chains.
- [DatabaseMetaData (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/DatabaseMetaData.html) — đặc điểm driver và database.
- [ConnectionPoolDataSource (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/javax/sql/ConnectionPoolDataSource.html) và [PooledConnection](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/javax/sql/PooledConnection.html) — SPI cho connection pool infrastructure.
- [Virtual Threads (Java SE 27 Core Libraries)](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html) — virtual-thread-per-task, tài nguyên giới hạn và connection pools.

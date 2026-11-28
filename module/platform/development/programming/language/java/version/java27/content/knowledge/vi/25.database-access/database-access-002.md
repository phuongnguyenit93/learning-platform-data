# PreparedStatement, tham số truy vấn và phòng tránh SQL injection trong Java 27

Giả sử ứng dụng Java nhận email từ một biểu mẫu để tìm tài khoản. Nếu xây dựng SQL bằng cách ghép trực tiếp chuỗi từ người dùng, nội dung email có thể bị cơ sở dữ liệu hiểu thành **một phần cú pháp SQL**, thay vì dữ liệu cần tra cứu. Lỗi này thuộc nhóm **SQL injection**, có thể dẫn đến đọc sai phạm vi dữ liệu, thay đổi bản ghi hoặc những tác động nghiêm trọng khác tùy quyền của tài khoản cơ sở dữ liệu.

Trong chương **Truy cập cơ sở dữ liệu** của **Java 27**, giải pháp nền tảng là dùng **`java.sql.PreparedStatement`** và **tham số hóa truy vấn** (*parameterized query*). Mẫu SQL do ứng dụng kiểm soát, còn các giá trị động được truyền qua `setString`, `setLong`, `setBigDecimal`, `setObject`... Cách làm này giúp tách **cấu trúc lệnh** khỏi **giá trị dữ liệu**, kể cả khi dữ liệu chứa dấu nháy, khoảng trắng hoặc ký tự giống từ khóa SQL.

Bài học sử dụng **JDBC chuẩn hiện hành trong Java SE 27**, kết hợp quy tắc phòng vệ theo [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet). Không sử dụng mẹo escape thủ công, API lỗi thời hay phụ thuộc một cơ sở dữ liệu cụ thể làm nguyên tắc bảo vệ chính.

## 1. Cách SQL injection xuất hiện

### 1.1. Ví dụ không an toàn: ghép input vào câu SQL

~~~~java
// PHẢN VÍ DỤ: tuyệt đối không dùng cách này với dữ liệu bên ngoài.
String inputEmail = requestEmail;

String sql =
        "SELECT id, display_name FROM customers WHERE email = '"
        + inputEmail + "'";

// Statement statement = connection.createStatement();
// ResultSet rows = statement.executeQuery(sql);
~~~~

Đoạn code này biến `inputEmail` thành một phần **văn bản của câu lệnh SQL**. Ví dụ, một chuỗi chứa dấu nháy đơn và các toán tử có thể thay đổi biểu thức trong mệnh đề `WHERE`. Nội dung cụ thể, mức độ khai thác và hành vi khi thực thi còn phụ thuộc SQL dialect, driver, quyền của tài khoản và những chính sách ở cơ sở dữ liệu.

Vấn đề cốt lõi **không phải** “dấu nháy đơn là ký tự nguy hiểm”, mà là chương trình đã đặt dữ liệu không tin cậy vào **vị trí được SQL parser diễn giải như code**.

~~~~text
Input từ HTTP / queue / file / database
                |
                v
     Ghép vào văn bản SQL
                |
                v
       SQL parser diễn giải
                |
          dữ liệu và cú pháp
          bị trộn lẫn với nhau
~~~~

Tất cả dữ liệu nằm ngoài hợp đồng tin cậy đều phải được xử lý theo quy tắc này, kể cả dữ liệu đọc lại từ cơ sở dữ liệu, thông tin gửi qua message queue hoặc nội dung do dịch vụ khác tạo ra. Việc dữ liệu “đã lưu trong database” **không tự biến nó thành một đoạn SQL an toàn để ghép**; rủi ro đó thường được gọi là *second-order SQL injection*.

### 1.2. Cách đúng: SQL cố định và bind giá trị

~~~~java
String sql = """
        SELECT id, display_name
        FROM customers
        WHERE email = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, requestEmail);

    try (ResultSet rows = statement.executeQuery()) {
        while (rows.next()) {
            System.out.println(rows.getString("display_name"));
        }
    }
}
~~~~

Mẫu SQL có ký hiệu `?` ở vị trí cần một **giá trị**. Driver JDBC nhận giá trị qua `setString(1, requestEmail)` theo hợp đồng của `PreparedStatement`; giá trị ấy không trở thành cú pháp SQL chỉ vì chứa các ký tự trông giống toán tử.

**Lưu ý về ví dụ:** đoạn code giả định biến `connection` là `java.sql.Connection` đang mở và đã có bảng `customers` với các cột tương ứng. Để biên dịch, cần import `java.sql.PreparedStatement` và `java.sql.ResultSet`. Ví dụ đầy đủ với `DataSource` sẽ xuất hiện ở phần sau.

~~~~text
     SQL template do ứng dụng viết
       "... WHERE email = ?"
                 |
      marker #1 là giá trị
                 |
                 v
      PreparedStatement.setString(1, inputEmail)
                 |
                 v
          JDBC driver / DBMS
                 |
         xử lý giá trị dưới
         dạng tham số dữ liệu
~~~~

Đây là điểm khác biệt có ý nghĩa bảo mật. `PreparedStatement` không chỉ là một cách khác để gọi `executeQuery`: khi sử dụng **đúng cách**, nó giữ dữ liệu người dùng ra khỏi cấu trúc cú pháp của câu SQL.

## 2. Các thành phần của JDBC hiện đại

JDBC nằm chủ yếu trong module `java.sql`, còn interface `DataSource` nằm trong package `javax.sql`, cũng thuộc module `java.sql`.

| Thành phần | Vai trò | Lưu ý |
| --- | --- | --- |
| `DataSource` | Tạo/cấp `Connection`; thường được cấu hình pooling bởi framework/driver | Nên được inject vào repository/service |
| `Connection` | Phiên làm việc với database, sở hữu transaction và tạo statement | Đóng khi hết phạm vi sử dụng |
| `PreparedStatement` | Câu SQL cố định có thể chứa marker `?` và các tham số được bind | Được dùng cho SELECT/INSERT/UPDATE/DELETE có giá trị động |
| `ResultSet` | Cursor duyệt các dòng trả về từ truy vấn | Đóng sau khi đọc; không trả ra ngoài khi đã đóng connection |
| `SQLException` | Báo lỗi JDBC, gồm SQLState và error code của vendor | Không hiển thị nguyên văn cho người dùng cuối |
| `SQLType` / `JDBCType` / `Types` | Biểu diễn kiểu SQL khi bind tham số hoặc SQL NULL | Cần chọn tương thích schema/driver |

Một luồng thực thi thường là:

~~~~text
     Controller / Service
            |
            v
        Repository
            |
            v
      DataSource.getConnection()
            |
            v
      Connection.prepareStatement(SQL)
            |
            v
      statement.setXxx(index, value)
            |
            v
      executeQuery / executeUpdate
            |
            v
        ResultSet / row count
            |
            v
      Domain record / DTO
            |
            v
   Đóng ResultSet, PreparedStatement,
   Connection theo try-with-resources
~~~~

`DataSource` là cách Javadoc JDBC ưu tiên để lấy kết nối trong một ứng dụng được cấu hình bài bản; `DriverManager` vẫn là API chuẩn nhưng thường phù hợp hơn với ví dụ nhỏ hoặc công cụ đơn giản. Một **JDBC driver tương thích với DBMS** vẫn cần được cung cấp riêng; JDK không tự kèm đầy đủ driver cho mọi database.

### 2.1. Import thường dùng

~~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.JDBCType;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;
~~~~

Trong một named module có dùng JDBC:

~~~~java
// module-info.java của module ứng dụng (minh họa riêng).
module com.example.application {
    requires java.sql;
}
~~~~

Module cần thêm các `requires` khác nếu ứng dụng dùng thư viện hoặc module khác. Không cần `--enable-preview` cho JDBC hay `PreparedStatement` trong Java 27.

## 3. Chu trình tạo, bind, thực thi và đóng `PreparedStatement`

### 3.1. Marker `?` được đánh số từ 1

Trong JDBC, tham số đầu tiên có chỉ số **1**, không phải 0 như mảng Java:

~~~~java
String sql = """
        SELECT id, email, status
        FROM customers
        WHERE tenant_id = ?
          AND email = ?
          AND status = ?
        """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setString(2, email);
    ps.setString(3, "ACTIVE");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
~~~~

Thứ tự bind phải đúng **thứ tự xuất hiện marker `?` trong SQL**, không phải thứ tự cột trong bảng hay thứ tự tên biến. Nếu marker thứ nhất là `tenant_id` thì phải gọi `setLong(1, tenantId)`.

Trong JDBC chuẩn, `PreparedStatement` sử dụng marker vị trí `?`. Một số framework cung cấp **named parameters** dạng `:email`, nhưng đó là tính năng của framework hoặc driver tương ứng, **không phải cú pháp thay thế phổ quát trong `Connection.prepareStatement(String)`**.

### 3.2. `executeQuery()` và `executeUpdate()` không nhận lại SQL

| Lệnh SQL | Cách thực thi | Kết quả |
| --- | --- | --- |
| `SELECT` trả rows | `executeQuery()` | `ResultSet` |
| `INSERT` / `UPDATE` / `DELETE` | `executeUpdate()` | `int` số hàng bị ảnh hưởng |
| DML lớn có thể vượt `int` | `executeLargeUpdate()` | `long` số hàng bị ảnh hưởng |
| Câu lệnh có nhiều loại kết quả | `execute()` | `boolean` cho biết loại kết quả đầu tiên; cần xử lý tiếp |

Phân biệt với `Statement.executeQuery(String sql)`: sau khi `PreparedStatement` đã được tạo từ SQL template, **không truyền SQL khác vào lúc gọi execute**.

~~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE products SET price = ? WHERE id = ?")) {

    ps.setBigDecimal(1, new BigDecimal("120000.00"));
    ps.setLong(2, 1001L);

    int updated = ps.executeUpdate();
    System.out.println(updated); // Số bản ghi được cập nhật
}
~~~~

Không dùng `ps.executeUpdate(dynamicSql)`. Với `PreparedStatement`, các overload của `Statement` nhận SQL `String` không phải cách thực thi đúng và theo Javadoc sẽ bị từ chối với `SQLException`. SQL đã được định nghĩa ở `prepareStatement`.

### 3.3. `try-with-resources` giữ vòng đời tài nguyên rõ ràng

~~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
             "SELECT id, display_name FROM customers WHERE id = ?")) {

    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            System.out.println(rs.getString("display_name"));
        }
    }
}
~~~~

`Connection`, `PreparedStatement` và `ResultSet` đều có thể được đóng bằng `try-with-resources`. Khi thoát khối, tài nguyên được đóng kể cả khi xảy ra exception. Với pooled `DataSource`, `Connection.close()` thường trả kết nối về pool tùy implementation, không nhất thiết đóng socket vật lý.

Không giữ `ResultSet` hoặc `PreparedStatement` trong field của singleton service rồi sử dụng khi connection đã đóng. Với repository API, nên đọc dữ liệu thành một record/DTO độc lập trước khi trả kết quả cho caller.

### 3.4. `PreparedStatement` có thể dùng lại trong phạm vi sở hữu kết nối

~~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE products SET quantity = ? WHERE id = ?")) {

    ps.setInt(1, 15);
    ps.setLong(2, 101L);
    ps.executeUpdate();

    ps.setInt(1, 20);
    ps.setLong(2, 102L);
    ps.executeUpdate();
}
~~~~

Khi dùng lại statement, **giá trị tham số cũ có thể còn được giữ** cho đến khi gán mới hoặc gọi `clearParameters()`. Để tránh lỗi dùng giá trị stale, hãy bind đầy đủ tất cả các tham số mỗi lần chạy. `clearParameters` xóa giá trị được bind, nhưng không thay đổi cấu trúc SQL của statement.

Lợi ích hiệu năng nhờ chuẩn bị và tái sử dụng SQL phụ thuộc JDBC driver và DBMS; không suy ra rằng mọi `prepareStatement` đều được biên dịch trước trên server đúng một lần, hoặc tự động nhanh hơn trong mọi workload. **Tách code và data để chống injection vẫn là lý do chính**, ngay cả khi hiệu năng bằng một cách thực thi khác.

## 4. Chọn `setXxx` theo kiểu dữ liệu

Các hàm `setXxx` chuyển dữ liệu Java thành kiểu SQL tương thích với marker tương ứng. Cần biết schema và khả năng driver, tránh phụ thuộc vào ép kiểu ngầm khi không cần thiết.

| Dữ liệu Java | Cách bind phổ biến | Lưu ý |
| --- | --- | --- |
| `String` | `setString(index, text)` | Tương thích trường text phù hợp |
| `int` / `Integer` | `setInt(index, value)` | Giá trị primitive không biểu diễn SQL NULL |
| `long` / `Long` | `setLong(index, value)` | Đảm bảo miền của cột đủ lớn |
| `boolean` | `setBoolean(index, value)` | Kiểu SQL và phép ánh xạ tùy DB/driver |
| `BigDecimal` | `setBigDecimal(index, amount)` | Phù hợp với cột DECIMAL/NUMERIC cho tiền |
| `LocalDate` | `setObject(index, date)` hoặc overload chỉ định SQL type | Hỗ trợ JDBC 4.2+; kiểm tra driver |
| `LocalDateTime` | `setObject(index, dateTime)` | Không tự chứa time zone |
| `OffsetDateTime` | `setObject(index, value)` | Kiểu TIMESTAMP WITH TIME ZONE và mapping phụ thuộc driver |
| SQL `NULL` | `setNull(index, Types.VARCHAR)`, v.v. | Khai báo kiểu SQL tường minh |
| Giá trị tùy biến | `setObject(index, value, JDBCType.DECIMAL)` hoặc overload phù hợp | Tránh chuyển đổi mơ hồ |

Ví dụ:

~~~~java
import java.math.BigDecimal;
import java.sql.JDBCType;
import java.sql.PreparedStatement;
import java.time.LocalDate;

try (PreparedStatement ps = connection.prepareStatement("""
        INSERT INTO invoices (customer_id, amount, issued_on)
        VALUES (?, ?, ?)
        """)) {

    ps.setLong(1, 101L);
    ps.setBigDecimal(2, new BigDecimal("158000.50"));
    ps.setObject(3, LocalDate.of(2026, 11, 27), JDBCType.DATE);

    int inserted = ps.executeUpdate();
}
~~~~

**Không dùng `double` theo thói quen cho tiền** nếu ứng dụng đòi hỏi độ chính xác thập phân. `BigDecimal` kết hợp cột `DECIMAL/NUMERIC` có precision/scale được xác định rõ thường phù hợp hơn; cần kiểm tra chính sách làm tròn và giới hạn cột ở tầng nghiệp vụ.

### 4.1. Bind SQL NULL đúng kiểu

`NULL` không giống chuỗi `"null"` và không giống chuỗi rỗng. Ví dụ muốn cho phép số điện thoại không tồn tại:

~~~~java
import java.sql.PreparedStatement;
import java.sql.Types;

try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE customers SET phone_number = ? WHERE id = ?")) {

    if (phoneNumber == null) {
        ps.setNull(1, Types.VARCHAR);
    } else {
        ps.setString(1, phoneNumber);
    }

    ps.setLong(2, customerId);
    ps.executeUpdate();
}
~~~~

Javadoc yêu cầu `setNull(parameterIndex, sqlType)` có kiểu SQL tường minh. `setObject(index, null)` có thể gặp vấn đề suy luận kiểu hoặc hành vi khác nhau theo driver; hãy chọn kiểu mục tiêu nếu cần truyền null cho một cột cụ thể.

**Lưu ý:** `WHERE column = ?` với bind SQL NULL **không tương đương** `WHERE column IS NULL` vì logic ba giá trị của SQL. Nếu nghiệp vụ cần lọc những dòng có cột NULL, xây dựng SQL template thích hợp (cấu trúc do code quyết định), không mong `setNull` tự thay toán tử `=` thành `IS NULL`.

### 4.2. Đọc kết quả SQL NULL

~~~~java
String phone = rs.getString("phone_number");
// SQL NULL -> Java null với getter kiểu tham chiếu như getString.

int count = rs.getInt("optional_count");
if (rs.wasNull()) {
    // Cột optional_count trong hàng hiện tại là SQL NULL.
}
~~~~

Với các getter kiểu primitive, JDBC có thể trả giá trị mặc định như 0 cho SQL NULL; gọi `wasNull()` ngay sau getter cần kiểm tra để phân biệt. Với các kiểu tham chiếu thích hợp, `getObject(column, TargetClass.class)` có thể trả `null` nếu SQL NULL, tùy mapping được driver hỗ trợ.

### 4.3. Các kiểu thời gian nên rõ ngữ nghĩa

`LocalDate` tương ứng với ngày không có giờ; `LocalDateTime` tương ứng ngày giờ **không kèm offset/zone**. `OffsetDateTime` có offset nhưng cần kiểm tra khả năng driver/DBMS. Không biến `LocalDateTime` thành một instant UTC bằng cách giả định máy chủ nào cũng có cùng time zone.

~~~~java
import java.time.LocalDate;

LocalDate issuedOn = rs.getObject("issued_on", LocalDate.class);
~~~~

JDBC driver hiện đại thường hỗ trợ kiểu `java.time` theo JDBC 4.2, nhưng không nên hứa rằng mọi DBMS đều map mọi kiểu thời gian giống nhau; phải kiểm tra schema, driver, precision và chính sách time zone của ứng dụng.

## 5. Tham số `?` chỉ đại diện cho **giá trị**, không phải cú pháp SQL

Đây là giới hạn quan trọng nhất sau khi đã biết `PreparedStatement`. Marker `?` thường đứng ở vị trí SQL mong đợi một **giá trị biểu thức**, ví dụ:

~~~~sql
SELECT id FROM customers WHERE email = ?
UPDATE products SET price = ? WHERE id = ?
INSERT INTO orders (customer_id, total) VALUES (?, ?)
~~~~

Nhưng không thể dùng marker để thay thế **tên bảng, tên cột, tên schema, toán tử hay từ khóa SQL**:

~~~~sql
-- KHÔNG đúng: marker không phải tên bảng.
SELECT * FROM ?

-- KHÔNG đúng: marker không phải tên cột cần sắp xếp.
SELECT id FROM customers ORDER BY ?

-- KHÔNG đúng: marker không đại diện một hướng sắp xếp.
SELECT id FROM customers ORDER BY id ?
~~~~

Ngay cả khi DBMS chấp nhận `ORDER BY ?` như một biểu thức/hằng giá trị, nó **không có nghĩa** rằng nội dung bind được diễn giải là tên cột cho mục đích sắp xếp. Không giải quyết bài toán bằng cách bỏ marker rồi ghép thẳng văn bản đầu vào.

### 5.1. Allowlist cho tên cột và hướng sắp xếp

Nếu client muốn chọn cách sắp xếp danh sách khách hàng, hãy map từng lựa chọn được phép thành **đoạn SQL cố định do ứng dụng sở hữu**:

~~~~java
import java.util.Objects;

static String sortColumn(String requested) {
    return switch (Objects.requireNonNull(requested)) {
        case "name" -> "display_name";
        case "created" -> "created_at";
        default -> throw new IllegalArgumentException("Unsupported sort field");
    };
}

static String sortDirection(String requested) {
    return switch (Objects.requireNonNull(requested)) {
        case "asc" -> "ASC";
        case "desc" -> "DESC";
        default -> throw new IllegalArgumentException("Unsupported direction");
    };
}

static String buildListSql(String field, String direction) {
    String column = sortColumn(field);
    String order = sortDirection(direction);

    // Chỉ nội suy hai chuỗi cố định do switch phía trên trả về.
    return """
            SELECT id, display_name, created_at
            FROM customers
            WHERE tenant_id = ?
            ORDER BY %s %s, id ASC
            """.formatted(column, order);
}
~~~~

Sau khi có SQL template đã lựa chọn cấu trúc hợp lệ, tiếp tục bind **giá trị**:

~~~~java
try (PreparedStatement ps = connection.prepareStatement(
        buildListSql("name", "asc"))) {

    ps.setLong(1, tenantId);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("display_name"));
        }
    }
}
~~~~

**Tính an toàn của ví dụ đến từ allowlist**, không phải vì đã nối chuỗi một cách đặc biệt. Caller không thể đưa `"name; DELETE ..."` vào SQL vì `switch` từ chối mọi lựa chọn ngoài những giá trị cố định đã biết.

Nếu sản phẩm chỉ có vài kiểu sắp xếp, có thể viết hẳn các câu SQL riêng để giảm số nhánh động. Khi cần một biểu thức ORDER BY nhiều cột, hãy map cả **biểu thức SQL cố định** theo từng lựa chọn được công bố. Không đưa “tên cột đã qua regex” trở thành quyền truy cập tùy ý vào mọi cột của bảng.

### 5.2. Không dùng escape thủ công thay cho tham số

Một cách sửa lỗi thường được đề xuất nhưng thiếu tin cậy là tự thêm ký tự escape vào dấu nháy hoặc dấu gạch chéo ngược:

~~~~java
// PHẢN VÍ DỤ: không coi replace dấu nháy là lớp bảo vệ chính.
String supposedlyEscaped = userValue.replace("'", "''");
String sql = "SELECT * FROM customers WHERE email = '" +
        supposedlyEscaped + "'";
~~~~

Quy tắc escape thay đổi theo dialect, cấu hình và ngữ cảnh SQL. Biện pháp **đúng** là bind giá trị bằng `PreparedStatement`, không tự biến chuỗi người dùng thành SQL literal. OWASP cũng khuyến nghị chống SQL injection bằng parameterization và allowlist cho các thành phần cấu trúc.

### 5.3. PreparedStatement không chữa được SQL đã ghép nguy hiểm **trước khi prepare**

~~~~java
// VẪN KHÔNG AN TOÀN:
String sql = "SELECT id FROM customers WHERE email = '" +
        userEmail + "' AND tenant_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    // userEmail đã nằm trong SQL syntax trước khi prepare.
}
~~~~

Việc thêm `PreparedStatement` sau khi đã trộn dữ liệu không tin cậy vào SQL **không đảo ngược lỗi**. Tất cả **giá trị động** phải đi qua binding; phần SQL không thể bind phải được chọn từ cấu trúc do ứng dụng kiểm soát.

## 6. Tìm kiếm bằng `LIKE`: tham số hóa và quy tắc wildcard

Với `LIKE`, ký tự `%` và `_` là wildcard của SQL. Có **hai yêu cầu độc lập**:

1. **Chống SQL injection:** bind input như một giá trị bằng `setString`.
2. **Đúng ngữ nghĩa tìm kiếm:** quyết định dấu `%`/`_` của người dùng là wildcard hay ký tự literal.

### 6.1. Tìm đoạn văn bản có chứa keyword

~~~~java
String sql = """
        SELECT id, display_name
        FROM customers
        WHERE tenant_id = ?
          AND display_name LIKE ?
        """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setString(2, "%" + keyword + "%");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("display_name"));
        }
    }
}
~~~~

Đoạn này **không mở SQL injection** qua `keyword`, nhưng nó cho phép `%` và `_` do người dùng cung cấp tác động tới **mẫu LIKE**. Nếu sản phẩm chủ đích cung cấp tìm kiếm wildcard, đây có thể là ngữ nghĩa hợp lệ; nếu sản phẩm muốn tìm **nguyên văn**, phải xử lý riêng.

### 6.2. Tìm nguyên văn dấu `%` và `_`

SQL chuẩn hỗ trợ mệnh đề `ESCAPE` để chỉ định ký tự escape cho `LIKE`. Ví dụ lựa chọn dấu `!` (cần kiểm tra cách DBMS/dialect triển khai):

~~~~java
static String escapeLikeLiteral(String value) {
    return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}

String sql = """
        SELECT id, display_name
        FROM customers
        WHERE tenant_id = ?
          AND display_name LIKE ? ESCAPE '!'
        """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setString(2, "%" + escapeLikeLiteral(keyword) + "%");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("display_name"));
        }
    }
}
~~~~

**Không nhầm hai tầng escape:** `escapeLikeLiteral` chỉ làm cho các ký tự wildcard có nghĩa **literal trong biểu thức LIKE**. Nó **không** là biện pháp chống SQL injection độc lập. Dữ liệu vẫn phải được bind bằng `setString`. Cách chọn ký tự escape, collation, so khớp hoa thường và SQL chuẩn so với dialect phải được kiểm thử trên DBMS thực tế.

**Giới hạn hiệu năng:** mẫu `LIKE '%keyword%'` thường khó tận dụng index B-tree thông thường; ứng dụng có nhu cầu tìm kiếm lớn có thể cần full-text search hoặc cấu trúc chỉ mục riêng do DBMS cung cấp. Parameterization không tự động khiến một truy vấn chậm trở nên nhanh.

## 7. Truy vấn `IN` với số lượng tham số động

Với danh sách ID do client gửi, cách **sai** là tạo danh sách chữ số bằng cách nối trực tiếp input từ người dùng:

~~~~java
// PHẢN VÍ DỤ:
String sql = "SELECT id FROM products WHERE id IN (" +
        rawIdsFromRequest + ")";
~~~~

Thay vào đó, kiểm tra số lượng phần tử và tạo **đúng N marker `?`**, còn từng ID được bind riêng. Bởi marker được sinh bởi ứng dụng, không có cú pháp SQL nào đến từ nội dung của từng ID.

~~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

static List<Long> findPresentIds(Connection connection, List<Long> ids)
        throws SQLException {

    Objects.requireNonNull(connection, "connection");
    List<Long> input = List.copyOf(Objects.requireNonNull(ids, "ids"));

    if (input.isEmpty()) {
        return List.of();
    }
    if (input.size() > 500) {
        throw new IllegalArgumentException("Too many IDs");
    }

    String markers = String.join(
            ", ", Collections.nCopies(input.size(), "?"));
    String sql = "SELECT id FROM products WHERE id IN (" + markers + ")";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        for (int i = 0; i < input.size(); i++) {
            ps.setLong(i + 1, input.get(i));
        }

        List<Long> found = new ArrayList<>();
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                found.add(rs.getLong("id"));
            }
        }
        return List.copyOf(found);
    }
}
~~~~

**Những điểm cần nhớ:**

- `List.copyOf` từ chối null trong danh sách và tách cấu trúc khỏi những thay đổi sau đó. Với đầu vào có thể bị sửa đồng thời, việc sao chép vẫn cần chính sách đồng bộ phù hợp.
- `String.join` chỉ ghép **ký hiệu `?` được chương trình tạo**, không phải giá trị ID.
- Chỉ số JDBC bắt đầu từ 1, nên gọi `setLong(i + 1, input.get(i))`.
- Nếu danh sách rỗng, return ngay; đừng tự tạo `IN ()` rồi giả định mọi DBMS đều chấp nhận.
- Giới hạn 500 chỉ là **ví dụ về chính sách ứng dụng**; mỗi DBMS/driver có giới hạn marker, SQL length, packet và hiệu năng khác nhau.
- `IN` không bảo đảm thứ tự kết quả giống thứ tự trong danh sách input; muốn thứ tự xác định cần có `ORDER BY` và chính sách tương ứng.

Một số DBMS hỗ trợ **array parameters** hoặc table-valued parameters có thể hiệu quả hơn khi có rất nhiều ID, nhưng cú pháp và driver hỗ trợ khác nhau. Không giả định `setArray` là một cách tương đương trực tiếp với mọi dạng `WHERE id IN (?)` của mọi database.

## 8. Repository có kiểu rõ và tách biệt tầng dữ liệu

Ví dụ sau sử dụng `javax.sql.DataSource` được cấp bởi hệ thống, tạo `Connection` cho mỗi thao tác, bind mọi giá trị động, kiểm tra phạm vi tenant và chuyển `ResultSet` thành record độc lập.

Giả sử bảng `customers` có những cột:

~~~~sql
-- Minh họa schema logic; DDL chi tiết và constraint tùy DBMS.
customers (
    id             BIGINT,
    tenant_id      BIGINT,
    email          VARCHAR(...),
    display_name   VARCHAR(...),
    registered_on  DATE
)
~~~~

**Điều kiện nghiệp vụ:** `(tenant_id, email)` phải là một cặp duy nhất. Hãy đảm bảo một **unique constraint/index trong database** theo thiết kế schema thực, không chỉ tin vào `if (!rs.next())`.

Chương trình đầy đủ về mặt Java, có thể lưu thành `CustomerRepository.java` (để chạy cần cấu hình JDBC driver, DataSource và schema thật):

~~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerRepository {

    public record Customer(
            long id,
            String displayName,
            LocalDate registeredOn) {
    }

    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(
                dataSource, "dataSource");
    }

    public Optional<Customer> findByEmail(
            long tenantId, String email) throws SQLException {

        if (tenantId <= 0) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
        Objects.requireNonNull(email, "email");
        if (email.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }

        final String sql = """
                SELECT id, display_name, registered_on
                FROM customers
                WHERE tenant_id = ?
                  AND email = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setLong(1, tenantId);
            ps.setString(2, email);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }

                Customer customer = new Customer(
                        rs.getLong("id"),
                        rs.getString("display_name"),
                        rs.getObject("registered_on", LocalDate.class));

                if (rs.next()) {
                    throw new SQLException(
                            "Expected a unique customer per tenant and email");
                }
                return Optional.of(customer);
            }
        }
    }

    public boolean updateDisplayName(
            long tenantId, long customerId, String newName)
            throws SQLException {

        if (tenantId <= 0 || customerId <= 0) {
            throw new IllegalArgumentException("Invalid identifier");
        }
        Objects.requireNonNull(newName, "newName");
        if (newName.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }

        final String sql = """
                UPDATE customers
                SET display_name = ?
                WHERE tenant_id = ?
                  AND id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setString(1, newName);
            ps.setLong(2, tenantId);
            ps.setLong(3, customerId);

            int rows = ps.executeUpdate();
            if (rows > 1) {
                throw new SQLException(
                        "Unexpected number of updated customer rows: " + rows);
            }
            return rows == 1;
        }
    }
}
~~~~

### 8.1. Vì sao ví dụ này có ý nghĩa?

1. **Hợp đồng rõ ràng:** `findByEmail` trả `Optional<Customer>`, không trả `ResultSet` đang phụ thuộc một connection mở.
2. **Nguồn kết nối quản lý bên ngoài:** repository nhận `DataSource`, không hardcode tài khoản/mật khẩu hoặc tạo connection pool mới mỗi lần gọi.
3. **Cấu trúc SQL cố định:** `email`, `tenantId`, `newName` và `customerId` đều được bind.
4. **Kiểm tra kiểu và domain:** ID không âm, tên/email không trống. Đây là validation bổ sung, không thay parameter binding.
5. **Phạm vi tenant:** SQL có `WHERE tenant_id = ?` để giới hạn dữ liệu theo tenant ID **do tầng xác thực đáng tin xác định**. Nếu caller tùy ý chọn tenant ID của người khác, query vẫn chống injection nhưng **không chống truy cập trái phép**.
6. **Tài nguyên đóng đúng:** `Connection`, `PreparedStatement` và `ResultSet` đều được đóng trong khối.
7. **Đọc kiểu thời gian:** `getObject("registered_on", LocalDate.class)` phù hợp JDBC driver hỗ trợ ánh xạ `DATE` sang `LocalDate`.
8. **Giới hạn số dòng:** code phát hiện kết quả trùng ngoài kỳ vọng; database cần unique constraint thật để bảo vệ invariant dưới concurrency.

Trong ví dụ `updateDisplayName`, nếu `executeUpdate` thật sự sửa nhiều hơn một dòng khi connection đang ở **auto-commit** (mặc định), ném exception sau đó **không tự rollback** thay đổi đã xảy ra. Do đó tính duy nhất của `(tenant_id, id)` phải được bảo đảm bằng khóa/constraint ở database, và nếu cần nhiều thao tác cùng thành công hoặc thất bại thì phải dùng transaction như phần tiếp theo.

### 8.2. Không biến repository thành “SQL injection guard” duy nhất

`PreparedStatement` ngăn dữ liệu bind bị hiểu như cú pháp SQL. Nó **không tự** quyết định người dùng có quyền xem khách hàng hay không, tenant ID có đáng tin hay không, hoặc một request được phép sửa cột nào. Tầng xác thực, phân quyền, giới hạn dữ liệu và constraint database vẫn phải tồn tại.

## 9. `PreparedStatement` bên trong transaction

Tham số hóa truy vấn và transaction giải quyết **hai vấn đề khác nhau**:

- **Parameter binding:** giữ dữ liệu không tin cậy khỏi cú pháp SQL.
- **Transaction:** gom các thao tác liên quan thành một đơn vị nhất quán, được commit hoặc rollback theo chính sách.

Một công việc có thể dùng nhiều `PreparedStatement` trong **cùng một `Connection`** để bảo đảm transaction. Tạo một connection mới cho mỗi lệnh riêng lẻ rồi gọi `commit` trên connection khác sẽ **không** gộp những lệnh đó vào cùng transaction.

### 9.1. Ví dụ chuyển số dư trong một transaction

Giả sử cơ sở dữ liệu có bảng `accounts(tenant_id, id, balance)`, với số dư kiểu `DECIMAL/NUMERIC` và mỗi cặp `(tenant_id, id)` là duy nhất. Ví dụ sau dùng các lệnh SQL có cấu trúc cố định và tất cả giá trị đều được bind.

Chương trình minh họa `AccountTransferRepository.java` có thể biên dịch nếu có `DataSource` thích hợp; để chạy cần JDBC driver, schema, transaction support và cấu hình DBMS thật.

~~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class AccountTransferRepository {
    private final DataSource dataSource;

    public AccountTransferRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void transfer(
            long tenantId,
            long sourceId,
            long targetId,
            BigDecimal amount) throws SQLException {

        Objects.requireNonNull(amount, "amount");
        if (tenantId <= 0 || sourceId <= 0 || targetId <= 0
                || sourceId == targetId || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        final String withdrawSql = """
                UPDATE accounts
                SET balance = balance - ?
                WHERE tenant_id = ?
                  AND id = ?
                  AND balance >= ?
                """;

        final String depositSql = """
                UPDATE accounts
                SET balance = balance + ?
                WHERE tenant_id = ?
                  AND id = ?
                """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                try (PreparedStatement withdraw =
                             connection.prepareStatement(withdrawSql);
                     PreparedStatement deposit =
                             connection.prepareStatement(depositSql)) {

                    withdraw.setBigDecimal(1, amount);
                    withdraw.setLong(2, tenantId);
                    withdraw.setLong(3, sourceId);
                    withdraw.setBigDecimal(4, amount);

                    if (withdraw.executeUpdate() != 1) {
                        throw new SQLException(
                                "Source not found or insufficient balance");
                    }

                    deposit.setBigDecimal(1, amount);
                    deposit.setLong(2, tenantId);
                    deposit.setLong(3, targetId);

                    if (deposit.executeUpdate() != 1) {
                        throw new SQLException(
                                "Target account not found");
                    }
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
}
~~~~

Đọc kỹ những quyết định:

1. `setAutoCommit(false)` bắt đầu chế độ quản lý commit tường minh cho connection đang sở hữu.
2. Lệnh trừ tiền kiểm tra `balance >= ?` **ngay trong SQL UPDATE**, giảm rủi ro khi nhiều giao dịch đồng thời cùng thao tác tài khoản so với “SELECT số dư rồi kiểm tra trong Java” mà không khóa.
3. Cả nguồn và đích đều có điều kiện `tenant_id = ?`; tenantId phải đến từ context xác thực đáng tin.
4. Hai lệnh được chạy qua **cùng connection và transaction**; chỉ `commit` sau khi cả hai thành công.
5. Nếu SQL hoặc kiểm tra số hàng thất bại, cố `rollback`; lỗi rollback được đính vào exception gốc dưới dạng *suppressed exception* để không mất nguyên nhân ban đầu.
6. `try-with-resources` đóng statement và connection khi ra khỏi phạm vi, kể cả trường hợp exception.

**Không coi ví dụ là hệ thống ngân hàng hoàn chỉnh.** Còn phải thiết kế độ chính xác của `DECIMAL`, giới hạn số tiền, isolation/locking, xử lý deadlock, idempotency, audit, hạn mức, chính sách retry, đối soát và tính bền vững giao dịch. Khả năng rollback/transaction thực sự tùy DBMS, storage engine và driver; phải kiểm chứng khi triển khai.

### 9.2. Vì sao không đổi auto-commit tùy tiện trên connection dùng chung?

`Connection` là một **phiên** với trạng thái như auto-commit và transaction isolation. Không nên giữ một connection dùng chung cho nhiều request không đồng bộ rồi cho chúng tự gọi `setAutoCommit`, `commit`, `rollback` trên cùng object.

Ví dụ trên tự lấy một connection, sở hữu nó trong phạm vi method và đóng sau khi hoàn tất. Trong ứng dụng có connection pool, việc đóng thường trả connection về pool, và cần cấu hình pool để trạng thái connection được quản lý đúng. Nếu caller cấp connection vào method thay vì repository tự sở hữu, quy ước phải chỉ rõ **ai quản lý transaction và ai được phép commit/close**.

### 9.3. Transaction không thay cho parameter binding

Nếu SQL vẫn được ghép từ dữ liệu người dùng, việc chạy nó trong transaction **không ngăn SQL injection**. Ngược lại, dùng `PreparedStatement` không thay cho việc commit/rollback nhiều bước theo yêu cầu nhất quán.

## 10. Batch update và tham số thay đổi theo từng bản ghi

Khi có nhiều bộ giá trị cùng sử dụng một SQL template, có thể dùng `PreparedStatement.addBatch()` và `executeBatch()`. Mỗi lần `addBatch()` chụp một bộ giá trị tham số hiện hành để đưa vào batch:

~~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

static int[] insertTags(
        Connection connection, long tenantId, List<String> tags)
        throws SQLException {

    String sql = """
            INSERT INTO tags (tenant_id, tag_name)
            VALUES (?, ?)
            """;

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        for (String tag : tags) {
            ps.setLong(1, tenantId);
            ps.setString(2, tag);
            ps.addBatch();
        }
        return ps.executeBatch();
    }
}
~~~~

Đoạn code này là **method minh họa**, đặt trong một class có cấu hình và validation phù hợp. Khi nguồn tag đến từ request, phải giới hạn số phần tử, độ dài mỗi tag và tránh đưa dữ liệu nhạy cảm vào log. Dù batch có nhiều dòng, **mỗi giá trị vẫn được bind**.

### 10.1. Batch không mặc nhiên hoàn toàn thành công hoặc thất bại đồng loạt

`executeBatch` trả mảng số đếm tương ứng các lệnh, với các giá trị đặc biệt:

| Giá trị | Ý nghĩa |
| --- | --- |
| `0, 1, 2, ...` | Số hàng bị tác động được driver báo |
| `Statement.SUCCESS_NO_INFO` | Lệnh thành công nhưng không biết chính xác số hàng |
| `Statement.EXECUTE_FAILED` | Lệnh thất bại khi driver tiếp tục batch sau lỗi |

Khi một lệnh trong batch thất bại, JDBC có thể ném `BatchUpdateException`. Theo đặc tả, driver **có thể dừng ngay hoặc tiếp tục thực thi các lệnh còn lại**; `getUpdateCounts()` và `getLargeUpdateCounts()` cung cấp thông tin tiến độ theo hợp đồng.

Nếu nghiệp vụ yêu cầu **atomic batch**, hãy đặt batch trong một transaction của connection có hỗ trợ transaction, rồi rollback nếu có lỗi. Không suy luận rằng riêng `addBatch` hoặc `executeBatch` đã tự cung cấp transaction.

### 10.2. `clearParameters` không xóa cấu trúc SQL

`clearParameters()` bỏ các giá trị đã bind trên `PreparedStatement`. `clearBatch()` xóa tập lệnh đã thêm vào batch. Hai thao tác khác nhau:

~~~~java
ps.clearParameters(); // Xóa giá trị bind hiện tại.
ps.clearBatch();      // Xóa các bộ thao tác đang chờ trong batch.
~~~~

Đừng tái sử dụng một `PreparedStatement` dùng chung giữa nhiều thread. Vì statement có **state của tham số, result set và batch**, việc hai request cùng bind sẽ có nguy cơ ghi đè giá trị của nhau nếu không có mô hình sở hữu và đồng bộ thích hợp.

## 11. Lấy khóa được tạo tự động

Nếu database tạo ID khi INSERT, JDBC có thể yêu cầu khóa được sinh ra bằng `Statement.RETURN_GENERATED_KEYS`:

~~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

static long createCustomer(
        Connection connection, long tenantId, String email)
        throws SQLException {

    String sql = """
            INSERT INTO customers (tenant_id, email)
            VALUES (?, ?)
            """;

    try (PreparedStatement ps = connection.prepareStatement(
            sql, Statement.RETURN_GENERATED_KEYS)) {

        ps.setLong(1, tenantId);
        ps.setString(2, email);

        if (ps.executeUpdate() != 1) {
            throw new SQLException("Insert did not affect one row");
        }

        try (ResultSet generated = ps.getGeneratedKeys()) {
            if (!generated.next()) {
                throw new SQLException("No generated key returned");
            }
            return generated.getLong(1);
        }
    }
}
~~~~

Khả năng truy xuất generated keys và dạng khóa trả về **phụ thuộc driver/DBMS/schema**. Một số hệ thống hỗ trợ cú pháp `RETURNING` hoặc cơ chế định danh riêng; nếu cần portability, phải kiểm tra hợp đồng của driver được dùng. Không lấy khóa mới bằng cách chạy `SELECT MAX(id)`: giá trị lớn nhất toàn bảng không nhất thiết là khóa của bản ghi vừa tạo khi nhiều transaction hoạt động đồng thời.

## 12. Resource, timeout và connection pool

### 12.1. Giới hạn thời gian truy vấn

`PreparedStatement` kế thừa `Statement.setQueryTimeout(int seconds)`:

~~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, display_name FROM customers WHERE tenant_id = ?")) {

    ps.setQueryTimeout(5); // Giới hạn xử lý theo khả năng JDBC driver/DBMS.
    ps.setLong(1, tenantId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc từng hàng hoặc áp dụng giới hạn output hợp lý.
        }
    }
}
~~~~

Khi thời hạn bị vượt, driver có thể ném `SQLTimeoutException` và **ít nhất cố hủy câu lệnh đang chạy** theo hợp đồng API. **Không bảo đảm** rằng mọi DBMS ngừng thực thi ngay tại đúng mốc thời gian hoặc đã rollback mọi side effect. Cần kết hợp server-side timeout, network timeout và giới hạn request theo cấu hình của hệ thống.

`setQueryTimeout(0)` thường có nghĩa không giới hạn bằng cơ chế này. Không cho phép client không tin cậy tùy ý chọn timeout quá lớn hoặc vô hạn cho truy vấn nặng.

### 12.2. Giới hạn dữ liệu trả về

Một câu `SELECT` an toàn trước SQL injection vẫn có thể đọc **hàng triệu bản ghi** nếu không giới hạn. Với API phân trang, dùng mệnh đề phân trang được DBMS hỗ trợ cùng các tham số value nếu dialect/driver cho phép:

~~~~java
// Cú pháp LIMIT / OFFSET minh họa cho dialect hỗ trợ chúng.
String sql = """
        SELECT id, display_name
        FROM customers
        WHERE tenant_id = ?
        ORDER BY id
        LIMIT ? OFFSET ?
        """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setInt(2, Math.min(requestedPageSize, 100));
    ps.setInt(3, offset);

    try (ResultSet rs = ps.executeQuery()) {
        // Chỉ dựng DTO các dòng cần trả.
    }
}
~~~~

Trong thực tế, còn phải kiểm tra `requestedPageSize > 0`, `offset >= 0` và chống tràn số khi tính offset, cũng như tính ổn định thứ tự sắp xếp. SQL phân trang khác nhau giữa các DBMS; không nên xem `LIMIT ? OFFSET ?` là cú pháp phổ quát của JDBC.

### 12.3. Tái sử dụng statement và pool

**Không** giữ một `PreparedStatement` được tạo từ connection X rồi dùng trên connection Y. `PreparedStatement` gắn với connection đã tạo ra nó và chứa state của parameter/cursor; thông thường nên để một operation sở hữu statement trong phạm vi ngắn.

Connection pool và JDBC driver có thể có cơ chế **statement caching** để giảm overhead chuẩn bị truy vấn, nhưng phải kiểm tra implementation và tải thực tế. Không tự viết global map cache chứa những instance `PreparedStatement` đang mở để “tăng tốc”; cách này dễ gây lỗi trạng thái, kết nối, concurrency và leak tài nguyên.

### 12.4. Tránh blocking vô hạn và tài nguyên hết hạn

Đối với luồng xử lý request, cần quan tâm cả:

- **Connection acquisition timeout** của pool.
- **Query timeout** theo driver/DBMS.
- **Network timeout** và khả năng hủy request thật.
- **Giới hạn số hàng, kích thước dữ liệu và mức đồng thời**.
- **Đóng tài nguyên khi không còn dùng**, kể cả khi code ném exception.

JDBC truyền thống là API có thể **blocking**. Chạy nó trên virtual thread của Java hiện đại có thể giúp quản lý nhiều tác vụ chờ I/O hơn trong một số hệ thống, nhưng không thay đổi quyền truy cập SQL, không làm truy vấn nhanh hơn và không tạo thêm connection vật lý trong pool. Giới hạn **số connection và mức tải DBMS** vẫn rất quan trọng.

## 13. Phòng vệ nhiều lớp trước SQL injection

**PreparedStatement dùng đúng cách là biện pháp chính cho các giá trị trong SQL**, nhưng bảo vệ một hệ thống thật cần nhiều lớp khác.

### 13.1. Validation đầu vào bổ trợ, không thay binding

Giả sử API nhận một mã sản phẩm gồm chữ hoa ASCII, chữ số và dấu gạch ngang, dài tối đa 32:

~~~~java
import java.util.regex.Pattern;

private static final Pattern PRODUCT_CODE =
        Pattern.compile("[A-Z0-9-]{1,32}");

static String requireProductCode(String raw) {
    if (raw == null || !PRODUCT_CODE.matcher(raw).matches()) {
        throw new IllegalArgumentException("Invalid product code");
    }
    return raw;
}
~~~~

Đây là **validation nghiệp vụ**: bảo đảm mã có cấu trúc hợp lệ, không phải thay thế `PreparedStatement`. Khi dùng mã này làm điều kiện truy vấn:

~~~~java
ps.setString(1, requireProductCode(userProductCode));
~~~~

Vẫn phải bind ngay cả khi đã đi qua regex. Một regex có vẻ “chặt” vẫn có thể sai, trong khi những trường text tự do như tên, địa chỉ, ghi chú cần chứa dấu nháy và nhiều ký tự Unicode hợp lệ; không thể cấm mọi ký tự đặc biệt để thay cho parameterization.

**Không nhầm kiểm tra SQL injection với phân quyền.** Mã sản phẩm hợp lệ về cú pháp chưa chắc thuộc tenant hoặc người dùng hiện tại.

### 13.2. Database account theo nguyên tắc ít quyền nhất

Một tài khoản chỉ đọc báo cáo không cần quyền `INSERT`, `UPDATE`, `DELETE` hoặc `DROP TABLE`. Một worker chỉ ghi một vài bảng không nên được cấp quyền DBA để “dễ vận hành”.

Tùy kiến trúc:

- Tạo tài khoản riêng cho service hoặc nhóm trách nhiệm phù hợp.
- Chỉ cấp quyền `SELECT`/`INSERT`/`UPDATE`/`DELETE` trên những bảng hoặc view thực sự cần dùng.
- Nếu cần giấu cột nhạy cảm, cân nhắc view chỉ công bố dữ liệu được phép và cấp quyền tương ứng.
- Kiểm soát credential qua secret manager hoặc cơ chế cấu hình an toàn; không commit mật khẩu vào source code.
- Không dùng cùng một tài khoản có toàn quyền quản trị DB cho mọi request ứng dụng.

Ít quyền làm giảm tác động nếu một lỗi khác vẫn xảy ra, nhưng không biến việc ghép SQL động thành an toàn.

### 13.3. Ràng buộc phạm vi người dùng/tenant

Một câu truy vấn **được parameterize hoàn hảo** vẫn có thể lộ dữ liệu nếu tầng ứng dụng chấp nhận `tenantId` do người dùng tùy ý gửi:

~~~~java
// Câu SQL chống injection, nhưng tenantId phải đến từ context đáng tin.
String sql = """
        SELECT id, display_name
        FROM customers
        WHERE tenant_id = ?
          AND id = ?
        """;
~~~~

Hãy lấy tenant ID từ session hoặc identity đã được xác thực và phân quyền; không tự tin rằng `setLong(1, tenantId)` sẽ xác minh quyền truy cập. Nếu DBMS hỗ trợ row-level security, có thể dùng thêm như một lớp bảo vệ **sau khi cấu hình đầy đủ**.

### 13.4. Stored procedure không tự loại bỏ injection

Gọi stored procedure bằng tham số:

~~~~java
try (CallableStatement call = connection.prepareCall(
        "{call update_account_status(?, ?)}")) {

    call.setLong(1, customerId);
    call.setString(2, status);
    call.execute();
}
~~~~

Điều này bind an toàn các đối số của lời gọi ở **phía Java**, nhưng stored procedure vẫn có thể xây dựng SQL động **không an toàn bên trong** bằng cách ghép tham số thành lệnh. Cần review cả code trong DBMS và áp dụng parameterization trong dynamic SQL phía server nếu có.

**Lưu ý:** để biên dịch đoạn ví dụ cần import `java.sql.CallableStatement`; tên procedure và quy ước tham số tùy DBMS. Việc cho phép ứng dụng gọi procedure phải gắn với các quyền thật sự cần thiết.

### 13.5. ORM/JPQL/HQL cũng có thể gặp injection

ORM không phải bảo đảm tự động nếu code vẫn ghép dữ liệu không tin cậy vào truy vấn động. Với JPA/Hibernate, nên dùng **named/bound parameters** của chính framework thay vì tạo chuỗi JPQL/HQL chứa literal từ user.

Ví dụ về **nguyên tắc**:

~~~~java
// PHẢN VÍ DỤ cho một API ORM, không phải JDBC:
// "from Customer c where c.email = '" + userEmail + "'"

// Hướng đúng: query cố định với named parameter do ORM hỗ trợ.
// "from Customer c where c.email = :email"
// query.setParameter("email", userEmail);
~~~~

Chính sách allowlist cho tên property, sort direction và những đoạn query structure vẫn cần thiết nếu framework cho phép tạo query động.

### 13.6. Không ghi bí mật vào log khi xử lý SQLException

Để chẩn đoán lỗi JDBC, `SQLException` có:

- `getSQLState()`: mã trạng thái SQL theo quy ước driver.
- `getErrorCode()`: mã lỗi đặc thù DBMS/driver.
- `getNextException()`: chuỗi ngoại lệ bổ sung.

~~~~java
try {
    repositoryOperation();
} catch (SQLException exception) {
    System.err.println(
            "Database operation failed; SQLState=" +
            exception.getSQLState() +
            ", vendorCode=" + exception.getErrorCode());
    throw exception;
}
~~~~

Đây là **mẫu xử lý minh họa** trong một method `throws SQLException`. Production thường dùng logger, tracing và phân loại lỗi thống nhất. Không log thẳng mật khẩu, access token, trường dữ liệu nhạy cảm hoặc toàn bộ câu lệnh kèm tham số không được phép công bố.

Một số lỗi từ DBMS có thể tiết lộ tên bảng, cấu trúc schema, constraint hoặc chi tiết truy vấn trong `getMessage()`. Tầng HTTP nên trả thông điệp được chuẩn hóa; log nội bộ cần được hạn chế truy cập và có chính sách che dữ liệu.

## 14. Kiểm thử chống injection và tính đúng của truy vấn

Không nên chỉ kiểm thử đường thành công với một email như `hello@example.test`. Cần xác minh đầu vào có ký tự đặc biệt vẫn là **giá trị dữ liệu**, không thay đổi cấu trúc SQL, và repository chỉ trả bản ghi trong phạm vi được phép.

### 14.1. Các nhóm dữ liệu cần thử

| Nhóm | Input ví dụ | Kỳ vọng |
| --- | --- | --- |
| Giá trị bình thường | `ana@example.test` | Tra cứu đúng user nếu tồn tại |
| Dấu nháy đơn hợp lệ trong text | `O'Connor` | Được lưu/tìm theo đúng literal, không lỗi cú pháp SQL |
| Chuỗi giống điều kiện SQL | `' OR '1'='1` | Được bind như một giá trị; không làm mở rộng kết quả |
| Ký tự Unicode | `Nguyễn An` | Được xử lý theo schema/driver, không cắt mất ký tự |
| Chuỗi rỗng | `""` | Theo validation hợp đồng; không tự sinh truy vấn rộng hơn |
| `null` | SQL NULL hoặc Java null | Xử lý bằng `setNull` hoặc validation tường minh |
| `%` và `_` trong LIKE | `100%_real` | Theo chính sách wildcard hoặc literal đã công bố |
| Chuỗi quá dài | 10.000 ký tự | Bị từ chối/giới hạn theo schema hoặc policy |
| Tên cột lạ | `unknown_column` | Allowlist từ chối |
| Hướng sắp xếp lạ | `desc; ...` | Allowlist từ chối, không ghép thẳng |
| Mảng IN rỗng | `[]` | Trả rỗng hoặc policy riêng, không tạo SQL không hợp lệ |
| Mảng IN quá lớn | 10.000 ID | Bị giới hạn hoặc dùng phương án DBMS đã thiết kế |
| Tenant của người khác | ID hợp lệ nhưng không được quyền truy cập | Bị từ chối ở tầng authorization, không lộ dữ liệu |

Các ví dụ mang ý nghĩa **kiểm thử phòng vệ trong hệ thống được phép**. Không cần đưa vào production logging nội dung đầy đủ của các chuỗi thử nghiệm nếu chúng có thể chứa dữ liệu thật của khách hàng.

### 14.2. Kiểm thử tích hợp với database thật

Các giả lập `DataSource` hoặc `PreparedStatement` có thể giúp kiểm tra **thứ tự setter**, nhưng không chứng minh tất cả vấn đề với SQL dialect, kiểu dữ liệu, collation, transaction hay driver.

Với một database test được phép sử dụng:

1. Tạo schema test có constraint và dữ liệu mẫu xác định.
2. Gọi repository bằng input thường và input có ký tự đặc biệt.
3. Kiểm tra số hàng/ID trả về, tenant scoping và dữ liệu không bị thay đổi bất thường.
4. Kiểm tra rollback khi thao tác thứ hai thất bại.
5. Kiểm tra batch failure, generated keys, SQL NULL và kiểu `LocalDate` nếu ứng dụng sử dụng.
6. Kiểm tra timeout/giới hạn số hàng với driver thật nếu có yêu cầu vận hành.
7. Xóa dữ liệu test hoặc rollback transaction test theo quy định môi trường.

Không thử những mẫu có khả năng gây thiệt hại lên database production. Môi trường test phải có tài khoản riêng và quyền thấp nhất cần thiết.

### 14.3. Ví dụ kiểm tra repository bằng dữ liệu đã biết

Giả sử trong bảng test có đúng khách hàng với `(tenant_id=10, email="ana@example.test")` và không có khách hàng nào với một chuỗi giống SQL:

~~~~java
CustomerRepository repository =
        new CustomerRepository(testDataSource);

System.out.println(
        repository.findByEmail(10L, "ana@example.test").isPresent());
// true

System.out.println(
        repository.findByEmail(10L, "' OR '1'='1").isEmpty());
// true, nếu test database không có email literal này.
~~~~

Đoạn này **không phải chương trình độc lập** vì cần class `CustomerRepository` từ ví dụ trước và một `testDataSource` được cấu hình. Điều kiểm tra là: chuỗi tìm kiếm đặc biệt **không tự thay đổi cấu trúc WHERE**; kết quả vẫn theo dữ liệu test.

### 14.4. Kiểm thử concurrency và quản lý kết nối

Nếu repository phục vụ nhiều request:

- Không chia sẻ cùng một instance `PreparedStatement` cho các request đồng thời.
- Không dùng một connection duy nhất cho toàn ứng dụng rồi tự quản lý transaction xen kẽ.
- Kiểm tra pool không bị cạn khi có nhiều request hoặc khi query ném exception.
- Đảm bảo `Connection` được trả về pool và `ResultSet` không còn mở sau khi xử lý.
- Nếu cần retry giao dịch, xác định lỗi nào **được phép retry** và thao tác có idempotent không.

Hệ thống dùng virtual threads cũng không nên mở số connection vượt quá khả năng DBMS. Khả năng tạo nhiều thread **không** biến một backend có hạn mức kết nối thành tài nguyên vô hạn.

## 15. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Ghép input vào WHERE bằng `+` | Dữ liệu có thể trở thành cú pháp SQL | Dùng `?` và bind với `setXxx` |
| Bọc SQL nguy hiểm trong `prepareStatement` | SQL đã bị ghép trước đó | Chỉ bind giá trị, giữ SQL structure do code sở hữu |
| Cho rằng regex validation thay parameter binding | Validation có thể thiếu và không bao quát mọi text hợp lệ | Giữ binding cho mọi dữ liệu động |
| Tự escape dấu nháy để chống injection | Quy tắc escape phụ thuộc dialect và ngữ cảnh | Dùng parameterized query |
| Dùng `?` cho tên bảng/cột hoặc `ASC/DESC` | Marker dành cho giá trị, không phải identifier/keyword | Allowlist ánh xạ sang SQL literal cố định |
| Gán marker theo chỉ số 0 | JDBC dùng chỉ số bắt đầu từ 1 | `setXxx(1, ...)` cho tham số đầu |
| Đổi thứ tự setter | Giá trị bind sai cột hoặc sai kiểu | Đối chiếu thứ tự marker trong SQL |
| Gọi `ps.executeQuery(dynamicSql)` | Đã chuẩn bị SQL từ trước; overload nhận SQL không dành cho PS | Gọi `ps.executeQuery()` |
| Dùng lại statement mà quên bind một số tham số | Giá trị cũ có thể còn hiệu lực | Bind đầy đủ hoặc `clearParameters` |
| Dùng `setString(index, "null")` cho NULL | Chuỗi `"null"` khác SQL NULL | `setNull(index, Types.X)` |
| Mong `WHERE column = NULL` tìm ra dòng NULL | SQL cần `IS NULL` | Dùng template phù hợp |
| Dùng `LIKE` mà không xác định wildcard semantics | `%`/`_` có thể làm rộng phạm vi tìm kiếm | Quy định wildcard và ESCAPE |
| Tạo `IN ()` với input rỗng | Cú pháp có thể không hợp lệ | Xử lý rỗng tường minh |
| Nối chuỗi ID để làm `IN` | Dễ tạo injection và lỗi kiểu | Sinh N marker `?` và bind từng giá trị |
| Giữ ResultSet bên ngoài khối đóng connection | Cursor mất hiệu lực, leak tài nguyên | Mapping DTO/record trong try-with-resources |
| Chia sẻ một PreparedStatement giữa nhiều thread | Có state tham số/cursor/batch mutable | Dùng statement riêng theo thao tác |
| Nghĩ `executeBatch` tự bảo đảm atomicity | Driver có thể thực thi một phần | Transaction và rollback nếu cần |
| Dùng `SELECT MAX(id)` để lấy ID vừa tạo | Race với giao dịch khác | `getGeneratedKeys` hoặc cơ chế DBMS đúng |
| Dùng tài khoản DB toàn quyền | Tăng tác động khi có lỗi | Least privilege |
| Nghĩ chống injection là đã có authorization | Vẫn có thể truy cập object của tenant khác | Kiểm tra quyền và ràng buộc phạm vi |
| Log SQL kèm mật khẩu/dữ liệu cá nhân | Rò rỉ dữ liệu | Cấu hình log che dữ liệu, phân quyền truy cập log |
| Không giới hạn số hàng/kích thước input | Có thể gây quá tải | Validation, pagination, query timeout và quota |

## 16. Checklist trước khi đưa một câu SQL vào production

- [ ] Cấu trúc SQL được ứng dụng viết hoặc lựa chọn từ template cố định.
- [ ] **Mọi giá trị** đến từ user/service/file/database đều đi qua parameter binding.
- [ ] Không còn đoạn nối dữ liệu không tin cậy vào `WHERE`, `VALUES`, `SET` hoặc một literal SQL bất kỳ.
- [ ] Tên bảng, cột, hướng sắp xếp hoặc biểu thức SQL động được chọn từ **allowlist chính xác**.
- [ ] Đã kiểm tra thứ tự marker `?` (bắt đầu từ **1**) và kiểu `setXxx`.
- [ ] Có chính sách xử lý `null` rõ, gồm sự khác nhau giữa `IS NULL` và `= ?`.
- [ ] Với `LIKE` đã xác định wildcard có được phép hay cần escape literal.
- [ ] Với `IN` có giới hạn số phần tử, trường hợp danh sách rỗng và chính sách thứ tự kết quả.
- [ ] Repository không mở rộng phạm vi dữ liệu ngoài quyền của caller; tenant ID đến từ context tin cậy.
- [ ] Database account chỉ có đúng quyền cần thiết.
- [ ] Có constraint và transaction cho các invariant quan trọng; không chỉ kiểm tra bằng code Java.
- [ ] `Connection`, `PreparedStatement` và `ResultSet` được đóng đúng vòng đời.
- [ ] Không share statement mutable/connection transaction giữa các request một cách tùy tiện.
- [ ] Có chính sách timeout, kích thước dữ liệu và mức đồng thời phù hợp với DBMS.
- [ ] Log/exception không tiết lộ mật khẩu, token, dữ liệu cá nhân hoặc nội bộ schema không cần thiết.
- [ ] Đã kiểm thử với dấu nháy, Unicode, chuỗi giống SQL, input rỗng/quá dài và truy cập sai tenant.
- [ ] Đã kiểm thử với **driver và database thực** cho SQL dialect, mapping kiểu, generated keys, batch và transaction.

## 17. Bảng lựa chọn API nhanh

| Nhu cầu | Lựa chọn |
| --- | --- |
| Tìm một bản ghi theo input | `Connection.prepareStatement(sql)` + `setXxx` + `executeQuery()` |
| Thêm/sửa/xóa bản ghi | `PreparedStatement.executeUpdate()` |
| Thao tác trả số hàng rất lớn | `executeLargeUpdate()` khi driver hỗ trợ |
| Bind SQL NULL | `setNull(index, Types.X)` |
| Bind ngày không có giờ | `setObject(index, LocalDate, JDBCType.DATE)` khi driver hỗ trợ |
| Tìm văn bản chứa keyword | `LIKE ?`, bind mẫu; kiểm soát `%`/`_` |
| Sắp xếp theo một số cột được phép | Allowlist identifier/order, rồi bind phần WHERE |
| `WHERE id IN (...)` với số phần tử biến đổi | Tạo N marker và bind từng ID; kiểm soát N |
| Gộp nhiều UPDATE thuộc một giao dịch | Một `Connection`, `setAutoCommit(false)`, `commit/rollback` |
| Thực thi nhiều bộ tham số cùng SQL | `addBatch()` / `executeBatch()` |
| Lấy ID do DB tạo | `prepareStatement(sql, RETURN_GENERATED_KEYS)` + `getGeneratedKeys()` |
| Cần giới hạn chạy query | `setQueryTimeout` và timeout ở DB/driver/network |
| Cần chia sẻ nguồn kết nối trong ứng dụng | `DataSource` được cấu hình/tiêm vào |
| Cần kiểm tra quyền truy cập | Authorization tin cậy + giới hạn SQL và quyền DB |

## Tài liệu tham khảo

- [Java SE 27 — PreparedStatement](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/PreparedStatement.html): marker `?`, các hàm `setXxx`, `setNull`, `setObject`, `executeQuery`, `executeUpdate` và batch.
- [Java SE 27 — Connection](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Connection.html): `prepareStatement`, transaction, auto-commit, `commit`, `rollback` và vòng đời connection.
- [Java SE 27 — ResultSet](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/ResultSet.html): cursor, getter, kiểu dữ liệu và SQL NULL.
- [Java SE 27 — Statement](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Statement.html): `setQueryTimeout`, `RETURN_GENERATED_KEYS`, `SUCCESS_NO_INFO` và `EXECUTE_FAILED`.
- [Java SE 27 — DataSource](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/javax/sql/DataSource.html): abstraction tạo connection và những loại triển khai pooling.
- [Java SE 27 — BatchUpdateException](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/BatchUpdateException.html): xử lý cập nhật theo batch có lỗi một phần.
- [Java SE 27 — SQLException](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor code và chuỗi lỗi.
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet): parameterized queries, allowlist cho SQL structure và least privilege.

**Kết luận:** Trong Java 27, `PreparedStatement` là cách chuẩn và quan trọng nhất để thực thi truy vấn với **giá trị động** mà không biến giá trị đó thành cú pháp SQL. Sử dụng marker `?`, bind chính xác bằng `setXxx`, quản lý tài nguyên JDBC và transaction rõ ràng. Với những thành phần **không thể parameterize** như tên cột hoặc hướng sắp xếp, chỉ chọn từ allowlist do ứng dụng quản lý. Để bảo vệ hệ thống thực sự, kết hợp thêm validation nghiệp vụ, phân quyền, giới hạn quyền DB, kiểm soát tài nguyên và kiểm thử trên driver/database thật; **chống SQL injection không đồng nghĩa đã giải quyết mọi vấn đề bảo mật dữ liệu**.

# Lựa chọn kiểu SQL khi đăng ký tham số đầu ra

## 1. Vì sao `CallableStatement` cần biết kiểu tham số đầu ra?

Trong **JDBC**, ứng dụng Java không chỉ chạy các câu `SELECT`, `INSERT`, `UPDATE` hay `DELETE` qua `PreparedStatement`. Khi cần gọi **thủ tục lưu trữ** (*stored procedure*), ứng dụng có thể dùng `CallableStatement` để truyền tham số vào (`IN`), nhận tham số ra (`OUT`) hoặc truyền và nhận trên cùng một tham số (`INOUT`).

Một procedure có thể tính thống kê đơn hàng và trả về **số đơn** và **tổng tiền**. Hai kết quả này không nhất thiết xuất hiện trong `ResultSet`: chúng có thể được trả trực tiếp qua tham số `OUT`. Trước khi thực thi, JDBC cần được khai báo **kiểu SQL dự kiến của mỗi tham số OUT**:

```java
try (CallableStatement call =
         connection.prepareCall("{call read_paid_summary(?, ?, ?, ?)}")) {
    call.setLong(1, customerId);                  // IN BIGINT
    call.registerOutParameter(2, Types.BIGINT);   // OUT BIGINT
    call.registerOutParameter(3, Types.DECIMAL);  // OUT DECIMAL
    call.registerOutParameter(4, Types.BIGINT);   // OUT BIGINT có thể NULL

    call.execute();

    long count = call.getLong(2);
    BigDecimal total = call.getBigDecimal(3);
    long lastId = call.getLong(4);
    Long lastOrderId = call.wasNull() ? null : lastId;
}
```

Đoạn mã minh họa giả định đã có `connection`, `customerId` và các `import` liên quan; ví dụ hoàn chỉnh sẽ xuất hiện ở mục 5.

**Điểm trọng tâm:** tham số thứ hai phải được đăng ký bằng kiểu SQL tương ứng với **khai báo trong procedure**, không phải kiểu mà lập trình viên muốn hiển thị trên giao diện. Với một số driver, chọn sai kiểu có thể tạo lỗi chuyển đổi, mất phần thập phân, tràn số hoặc dữ liệu trả về không như mong đợi.

## 2. Phân biệt loại tham số và phương thức thao tác

Giả sử thủ tục có chữ ký:

```sql
-- Chữ ký minh họa; cú pháp CREATE PROCEDURE tùy DBMS.
read_paid_summary(
    IN  p_customer_id BIGINT,
    OUT p_order_count BIGINT,
    OUT p_total DECIMAL(18, 2),
    OUT p_last_order_id BIGINT
)
```

Mỗi dấu `?` trong chuỗi `{call ...}` ứng với một **vị trí tham số đánh số từ 1**. Với `CallableStatement`:

| Chế độ | Trước khi thực thi | Sau khi thực thi |
| --- | --- | --- |
| `IN` | Gán giá trị bằng `setLong`, `setString`, `setBigDecimal`, ... | Thường không cần đọc lại qua getter OUT |
| `OUT` | Đăng ký kiểu bằng `registerOutParameter` | Đọc bằng `getLong`, `getBigDecimal`, `getString`, ... |
| `INOUT` | **Vừa gán** giá trị đầu vào **vừa đăng ký** kiểu đầu ra | Đọc giá trị mới từ chính vị trí đã đăng ký |
| Giá trị trả về của function theo JDBC escape | Đăng ký vị trí đầu tiên trong `{? = call ...}` | Đọc giá trị trả về ở vị trí 1 |

Ví dụ một `IN` kiểu `BIGINT` dùng `setLong(1, id)`. Một `OUT` kiểu `DECIMAL(18,2)` dùng `registerOutParameter(3, Types.DECIMAL)`. Nếu đó là `INOUT`, phải có **cả** thao tác `setXxx` và `registerOutParameter` trước `execute()`.

Lưu ý:

- **Không gọi `getXxx` để đọc OUT trước `execute()`.**
- **Không dùng `setNull` thay cho `registerOutParameter`.** `setNull` là cách truyền đầu vào `NULL`; đăng ký OUT là một thao tác khác.
- **Không tự suy kiểu OUT từ tên cột hiển thị.** Cần xem chữ ký thực tế của procedure hoặc tài liệu hợp đồng của DBMS.
- `CallableStatement` kế thừa `PreparedStatement`, nhưng truy vấn `SELECT` thông thường không cần `registerOutParameter`.

## 3. Chọn `java.sql.Types` hay `java.sql.JDBCType`?

JDBC có hai cách biểu đạt kiểu SQL chuẩn thường gặp:

1. **`java.sql.Types`**: tập hằng số kiểu `int` như `Types.INTEGER`, `Types.VARCHAR`, `Types.DECIMAL`, `Types.TIMESTAMP`.
2. **`java.sql.JDBCType`**: enum triển khai giao diện `SQLType`, chẳng hạn `JDBCType.INTEGER`, `JDBCType.DECIMAL`, `JDBCType.REF_CURSOR` (JDBC 4.2 trở lên).

Hai cách đăng ký tương ứng:

```java
import java.sql.CallableStatement;
import java.sql.JDBCType;
import java.sql.Types;

// Biến call minh họa một CallableStatement đã prepare.
call.registerOutParameter(2, Types.BIGINT);

// Biến thể JDBC 4.2+: driver cần hỗ trợ overload dùng SQLType.
call.registerOutParameter(3, JDBCType.DECIMAL);
```

Các overload `registerOutParameter` quan trọng:

| Phương thức | Khi dùng |
| --- | --- |
| `registerOutParameter(int index, int sqlType)` | Phổ biến nhất, dùng hằng số `Types` |
| `registerOutParameter(int index, int sqlType, int scale)` | Có thêm scale cho kiểu số thập phân như `DECIMAL`/`NUMERIC` |
| `registerOutParameter(int index, int sqlType, String typeName)` | Kiểu SQL do người dùng/DBMS định nghĩa cần tên kiểu |
| `registerOutParameter(int index, SQLType sqlType)` | Dùng `JDBCType` hoặc triển khai `SQLType`, tùy hỗ trợ driver |
| Các biến thể `SQLType` có `scale`/`typeName` | Tương tự overload kiểu `int`, khi driver hỗ trợ |
| `registerOutParameter(String name, ...)` | Đăng ký theo tên tham số, phụ thuộc DBMS/driver |

Trong dự án đa hệ quản trị hoặc cần hỗ trợ driver cũ, dùng `Types` là lựa chọn thực tế dễ tương thích hơn. Việc enum `JDBCType` tồn tại trong JDK **không bảo đảm** driver đã triển khai overload nhận `SQLType`; có driver trả `SQLFeatureNotSupportedException`. Cần thử nghiệm trên đúng phiên bản driver đang triển khai.

Mỗi `sqlType` ở đây biểu diễn **kiểu SQL của tham số OUT**, không phải `java.sql.Types.JAVA_OBJECT` chỉ vì phía Java muốn đọc bằng `getObject()`.

## 4. Bảng chọn kiểu cho các kết quả OUT phổ biến

Kiểu đăng ký nên dựa trên khai báo thực tế của stored procedure. Bảng sau đưa ra điểm khởi đầu, không thay thế kiểm tra dialect và driver:

| Kiểu OUT khai báo trong DBMS | Kiểu `Types` thường dùng | Cách đọc phổ biến | Điều phải chú ý |
| --- | --- | --- | --- |
| `SMALLINT` | `Types.SMALLINT` | `getShort` / `getObject` | Có thể `NULL`; tránh tràn miền `short` |
| `INTEGER` / `INT` | `Types.INTEGER` | `getInt` | Không dùng cho giá trị có thể vượt `int` |
| `BIGINT` | `Types.BIGINT` | `getLong` | `COUNT` lớn và ID nên dùng `long` khi schema cho phép |
| `DECIMAL(p,s)` / `NUMERIC(p,s)` | `Types.DECIMAL` / `Types.NUMERIC` | `getBigDecimal` | Giữ precision và scale thích hợp |
| `REAL` / `FLOAT` / `DOUBLE` | `Types.REAL` / `Types.FLOAT` / `Types.DOUBLE` | `getFloat` / `getDouble` | Giá trị xấp xỉ, không phù hợp tiền cần chính xác |
| `CHAR(n)` / `VARCHAR(n)` | `Types.CHAR` / `Types.VARCHAR` | `getString` | Kiểm tra Unicode, charset và độ dài |
| `NCHAR` / `NVARCHAR` | `Types.NCHAR` / `Types.NVARCHAR` | `getNString` / `getString` | Cần DBMS/driver hỗ trợ kiểu ký tự quốc gia |
| `BOOLEAN` | `Types.BOOLEAN` | `getBoolean` / `getObject` | Có DBMS thay boolean bằng `BIT` hoặc kiểu số |
| `DATE` | `Types.DATE` | `getDate` / `getObject` | Không mang giờ, cần thống nhất cách ánh xạ |
| `TIME` | `Types.TIME` | `getTime` / `getObject` | Không mặc định có timezone |
| `TIMESTAMP` | `Types.TIMESTAMP` | `getTimestamp` / `getObject` | Phân biệt với timestamp có offset |
| `TIMESTAMP WITH TIME ZONE` | `Types.TIMESTAMP_WITH_TIMEZONE` | `getObject` với kiểu thời gian thích hợp | Hỗ trợ và ngữ nghĩa phụ thuộc DBMS/driver |
| `VARBINARY` | `Types.VARBINARY` | `getBytes` | Dữ liệu nhị phân khác văn bản mã hóa |
| `BLOB` / `CLOB` | `Types.BLOB` / `Types.CLOB` | `getBlob` / `getClob` | Quản lý tài nguyên LOB khi driver yêu cầu |
| `ARRAY` | `Types.ARRAY` | `getArray` | Không phải hệ quản trị nào cũng hỗ trợ |
| `SQLXML` | `Types.SQLXML` | `getSQLXML` | Cần xử lý/giải phóng đối tượng đúng cách |
| Cursor OUT | `Types.REF_CURSOR` | `getObject`, đôi khi ép thành `ResultSet` | Chỉ khi DBMS/driver hỗ trợ REF CURSOR theo JDBC |
| Kiểu SQL riêng của DBMS | Có thể `Types.STRUCT`, `Types.OTHER` hoặc type chuyên biệt | `getObject`/driver API | Cần tài liệu DBMS, tên kiểu và quy tắc chuyển đổi |

### Những nhầm lẫn dễ gây lỗi

- Một procedure khai báo `OUT p_count BIGINT`, dù Java chỉ cần hiển thị số nhỏ, vẫn nên đăng ký `Types.BIGINT` và đọc `getLong`, **không chọn `Types.INTEGER` theo nhu cầu giao diện**.
- `DECIMAL(18,2)` là thập phân chính xác; không đăng ký thành `Types.DOUBLE` chỉ vì `double` tiện tính toán.
- `VARCHAR` có thể lưu Unicode nếu charset/collation cho phép. `NVARCHAR` không đơn giản là “kiểu Unicode cho tất cả DBMS”; trong SQL Server, các hệ `VARCHAR`/`NVARCHAR` có ngữ nghĩa riêng và tùy collation.
- `Types.DATE`, `Types.TIMESTAMP` và `Types.TIMESTAMP_WITH_TIMEZONE` không đồng nghĩa. Chọn đúng kiểu để tránh đánh mất thông tin giờ hoặc offset.
- `Types.NULL` không phải cách “đăng ký một OUT có thể null”. Vẫn đăng ký **kiểu SQL thực** (ví dụ `Types.BIGINT`) và kiểm tra `NULL` **sau khi đọc**.

## 5. Ví dụ hoàn chỉnh: hai số tổng hợp và một OUT có thể `NULL`

Ví dụ sau dùng **MySQL 8.x với bảng InnoDB** và JDBC driver MySQL tương thích (chẳng hạn Connector/J). Mục tiêu là tính số đơn đã thanh toán của một khách hàng, tổng số tiền và ID đơn thanh toán cuối cùng theo thứ tự ID.

### 5.1. Tạo bảng và procedure

```sql
CREATE TABLE paid_orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    payment_status VARCHAR(12) NOT NULL,
    amount DECIMAL(18, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO paid_orders (
    order_id, customer_id, payment_status, amount
) VALUES
    (1, 101, 'PAID', 120.50),
    (2, 101, 'PAID', 79.25),
    (3, 101, 'CANCELLED', 50.00),
    (4, 102, 'PAID', 25.00);

DELIMITER //

CREATE PROCEDURE read_paid_summary(
    IN  p_customer_id BIGINT,
    OUT p_order_count BIGINT,
    OUT p_paid_total DECIMAL(18, 2),
    OUT p_last_order_id BIGINT
)
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(amount), 0),
        MAX(order_id)
    INTO
        p_order_count,
        p_paid_total,
        p_last_order_id
    FROM paid_orders
    WHERE customer_id = p_customer_id
      AND payment_status = 'PAID';
END //

DELIMITER ;
```

`DELIMITER` là **lệnh của client dòng lệnh MySQL** để nhập câu lệnh nhiều dấu chấm phẩy, không phải SQL gửi trực tiếp qua JDBC. Khi triển khai bằng migration tool hoặc `Statement.execute(...)`, phải gửi phần `CREATE PROCEDURE ... BEGIN ... END` đúng theo cách công cụ hỗ trợ, **không** gửi `DELIMITER` như một câu SQL tới DBMS.

Ở procedure này, `SELECT ... INTO` gán ba kết quả vào tham số OUT; nó **không trả một bảng kết quả SELECT riêng** cho phía Java. Điều này giúp ví dụ tập trung vào `registerOutParameter`.

Với `customer_id = 101`, kết quả mong đợi:

| OUT | Kiểu SQL | Giá trị |
| --- | --- | --- |
| `p_order_count` | `BIGINT` | `2` |
| `p_paid_total` | `DECIMAL(18,2)` | `199.75` |
| `p_last_order_id` | `BIGINT` | `2` |

Với `customer_id = 999` không có đơn đã thanh toán: `COUNT(*) = 0`, tổng sau `COALESCE` là `0.00`, còn `MAX(order_id)` là **`NULL`**. Đây là lý do phải thiết kế kiểu Java cho tham số cuối có thể thiếu.

### 5.2. Ánh xạ OUT sang Java record

Với Java 17 trở lên, có thể tạo một record cho kết quả tổng hợp, **không cần** biến nó thành thực thể của bảng `paid_orders`:

```java
import java.math.BigDecimal;

public record PaidOrderSummary(
        long orderCount,
        BigDecimal paidTotal,
        Long lastOrderId
) {}
```

Trường `lastOrderId` dùng `Long` (không dùng `long`) để biểu diễn trường hợp SQL `NULL`.

### 5.3. Sử dụng `CallableStatement` đúng kiểu

```java
import java.math.BigDecimal;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public final class PaidOrderSummaryRepository {
    private final DataSource dataSource;

    public PaidOrderSummaryRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public PaidOrderSummary loadForCustomer(long customerId)
            throws SQLException {
        String sql = "{call read_paid_summary(?, ?, ?, ?)}";

        try (Connection connection = dataSource.getConnection();
             CallableStatement call = connection.prepareCall(sql)) {
            // Vị trí 1: IN BIGINT.
            call.setLong(1, customerId);

            // Vị trí 2, 3, 4: OUT theo khai báo SQL.
            call.registerOutParameter(2, Types.BIGINT);
            call.registerOutParameter(3, Types.DECIMAL, 2);
            call.registerOutParameter(4, Types.BIGINT);

            call.execute();

            long count = call.getLong(2);
            BigDecimal total = call.getBigDecimal(3);

            long rawLastOrderId = call.getLong(4);
            Long lastOrderId =
                    call.wasNull() ? null : rawLastOrderId;

            return new PaidOrderSummary(
                    count, total, lastOrderId);
        }
    }
}
```

Ví dụ gọi:

```java
PaidOrderSummaryRepository repository =
        new PaidOrderSummaryRepository(dataSource);

PaidOrderSummary active = repository.loadForCustomer(101L);
System.out.println(active);
// PaidOrderSummary[orderCount=2, paidTotal=199.75, lastOrderId=2]

PaidOrderSummary empty = repository.loadForCustomer(999L);
System.out.println(empty);
// orderCount=0; paidTotal=0.00 (cách hiển thị scale có thể tùy driver);
// lastOrderId=null
```

**Điểm kỹ thuật cần giải thích:**

1. `prepareCall` nhận cú pháp escape `{call ...}`. Driver chuyển đổi sang lời gọi procedure của MySQL theo khả năng hỗ trợ; một số DBMS dùng cú pháp khác.
2. Tham số JDBC **đếm từ 1**, đúng thứ tự xuất hiện trong lời gọi.
3. Tham số `IN` được gán bằng `setLong(1, customerId)`; ba `OUT` được đăng ký **trước `execute()`**.
4. `Types.BIGINT` và `Types.DECIMAL` khớp khai báo `BIGINT`, `DECIMAL(18,2)` của procedure. Không đăng ký `p_paid_total` bằng kiểu `INTEGER` hoặc `DOUBLE`.
5. `registerOutParameter(3, Types.DECIMAL, 2)` chỉ định **scale mong muốn** là 2 chữ số thập phân. Precision 18 và scale thật vẫn do procedure/DBMS xác định; không coi tham số scale của JDBC là công cụ sửa sai schema hoặc bảo đảm không bị làm tròn ở mọi driver.
6. `getLong(4)` trả 0 khi OUT có `NULL`, vì vậy phải gọi `wasNull()` **ngay sau getter đó**. `getBigDecimal` thường trả `null` nếu OUT là SQL `NULL` nên không cần `wasNull` để phân biệt trong trường hợp này.
7. `try-with-resources` bảo đảm đóng `CallableStatement` và trả `Connection` cho pool (nếu sử dụng pool), kể cả khi có `SQLException`.

Đối với procedure **chỉ đọc** ở ví dụ này, một lời gọi thường không cần transaction thủ công. Nếu procedure thay đổi nhiều bảng và ứng dụng cần phối hợp thêm DML bên ngoài procedure, hãy đặt toàn bộ thao tác vào transaction phù hợp trên **cùng một `Connection`**, sử dụng `commit`/`rollback` rõ ràng và xác minh procedure không tự ý kết thúc transaction theo cách trái hợp đồng.

## 6. `DECIMAL`, `NUMERIC`: precision, scale và cách đọc

Sự khác nhau giữa **precision** và **scale** dễ gây nhầm khi đăng ký OUT:

- `DECIMAL(18,2)`: precision tối đa **18 chữ số thập phân** theo định nghĩa kiểu SQL, trong đó scale là **2 chữ số bên phải dấu thập phân**.
- `registerOutParameter(index, Types.DECIMAL, 2)`: cung cấp thông tin **scale của kết quả OUT** cho JDBC driver; nó **không truyền precision 18**, cũng không thay đổi khai báo `DECIMAL(18,2)` tại máy chủ.
- `getBigDecimal(index)`: nhận giá trị số thập phân chính xác dưới dạng `BigDecimal`. Đây thường là cách đọc phù hợp nhất cho tiền.

Ví dụ:

```java
call.registerOutParameter(3, Types.DECIMAL, 2);
call.execute();

BigDecimal total = call.getBigDecimal(3);
if (total != null) {
    System.out.println(total.toPlainString());
}
```

Nếu DBMS khai báo OUT là `NUMERIC(20,4)`, nên đăng ký `Types.NUMERIC` (hoặc kiểu tương thích theo driver) với scale phù hợp, **không chọn scale 2 chỉ vì Java đang hiển thị hai chữ số**. Việc làm tròn cho giao diện phải là một quyết định nghiệp vụ sau khi đã nhận giá trị chính xác.

Trường hợp tính `AVG` từ các số `DECIMAL(18,2)`, kết quả có thể cần nhiều chữ số thập phân hơn 2. Nên định nghĩa rõ kiểu OUT và scale theo yêu cầu, tránh âm thầm làm tròn trung bình hoặc ép sang `double`.

## 7. `INOUT`: một tham số cần vừa `set` vừa `register`

Với MySQL, có thể viết procedure đơn giản cộng vào một biến:

```sql
DELIMITER //

CREATE PROCEDURE increment_counter(
    INOUT p_counter BIGINT,
    IN p_increment BIGINT
)
BEGIN
    SET p_counter = p_counter + p_increment;
END //

DELIMITER ;
```

Phía Java:

```java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.Types;

try (Connection c = dataSource.getConnection();
     CallableStatement call =
             c.prepareCall("{call increment_counter(?, ?)}")) {
    call.registerOutParameter(1, Types.BIGINT); // INOUT phải register.
    call.setLong(1, 10L);                       // INOUT phải set.
    call.setLong(2, 5L);                        // IN.

    call.execute();
    long updated = call.getLong(1);
    System.out.println(updated); // 15
}
```

Nếu `p_counter` là `BIGINT` có thể nhận `NULL` thì biểu thức `NULL + 5` vẫn là `NULL`, và `getLong(1)` sẽ trả 0; cần gọi `wasNull()` nếu ứng dụng cần phân biệt `NULL` với giá trị 0 thật.

Không thể chỉ đăng ký OUT mà bỏ qua `set` với `INOUT`, vì DBMS vẫn cần giá trị đầu vào. Ngược lại, chỉ `setLong` mà không `registerOutParameter` sẽ làm JDBC thiếu hợp đồng đọc giá trị đầu ra.

## 8. Function return khác procedure OUT

Một số DBMS có **stored function** trả một giá trị qua `RETURN` và **stored procedure** với các tham số `OUT`. Cú pháp escape JDBC cho function có một vị trí **kết quả trả về đặt ở đầu**:

```java
// Giả sử DBMS/driver hỗ trợ JDBC function escape và function trả BIGINT.
try (CallableStatement call =
         connection.prepareCall("{? = call calculate_rank(?)}")) {
    call.registerOutParameter(1, Types.BIGINT); // RETURN
    call.setLong(2, customerId);                // IN

    call.execute();
    long rank = call.getLong(1);
}
```

Trong `{? = call calculate_rank(?)}`, vị trí 1 là **giá trị trả về**, vị trí 2 là đầu vào; chúng **không** tương ứng với cách đánh số của `{call read_paid_summary(?, ?, ?, ?)}`.

**Không tự giả định procedure và function của các DBMS giống nhau:**

- **MySQL:** procedure có thể có `OUT`/`INOUT`; function thường trả kết quả thông qua `RETURN`.
- **SQL Server:** stored procedure có output parameters và có integer return status riêng; không nên coi return status là kiểu dữ liệu của một OUT khác.
- **PostgreSQL:** function, procedure, `OUT` parameters và `refcursor` có quy tắc gọi riêng; pgJDBC còn có cấu hình liên quan đến việc JDBC escape gọi function hay procedure.
- **Oracle:** function có giá trị return, procedure có tham số `OUT` và kiểu con trỏ riêng tùy driver.

Với dự án đa DBMS, hãy kiểm tra cú pháp procedure/function và driver thay vì sao chép nguyên một chuỗi `prepareCall`.

## 9. OUT có `NULL`, kiểu dữ liệu và chuyển đổi phía Java

Phân biệt **giá trị không có** và **giá trị bằng 0/rỗng** là điều quan trọng khi ánh xạ dữ liệu:

```java
call.registerOutParameter(2, Types.INTEGER);
call.execute();

int result = call.getInt(2);
if (call.wasNull()) {
    System.out.println("OUT là SQL NULL");
} else {
    System.out.println("OUT có giá trị: " + result);
}
```

`wasNull()` phản ánh **getter vừa được gọi gần nhất**. Nếu muốn kiểm tra `getLong(4)`, không nên gọi `getBigDecimal(3)` xen vào rồi mới `wasNull()`, vì khi ấy cờ `NULL` đã thuộc lần đọc khác.

Các getter tham chiếu có thể giúp xử lý `NULL` dễ hơn. Đoạn mã sau giả định **một procedure khác** có OUT kiểu `VARCHAR` tại vị trí 2 và `DECIMAL` tại vị trí 3, đã được đăng ký và thực thi:

```java
String note = call.getString(2);      // SQL NULL -> Java null.
BigDecimal amount = call.getBigDecimal(3);
```

Không nên lấy một kiểu Java thuận tiện bất kỳ rồi hy vọng driver chuyển đổi không mất thông tin:

- `BIGINT` vượt `int` nên `getInt` có thể tràn hoặc gây lỗi tùy driver.
- `DECIMAL` đọc thành `double` có thể làm mất chính xác.
- `TIMESTAMP WITH TIME ZONE` đọc như thời gian không offset có thể bỏ mất ý nghĩa timezone.
- `BLOB` hoặc cursor OUT không nên giả định sẽ là một `String`.

Hãy chọn `registerOutParameter` theo SQL, rồi **đọc bằng getter phù hợp**, sau đó chuyển sang DTO/record của ứng dụng nếu cần.

## 10. Kiểu đặc biệt: `REF_CURSOR`, `STRUCT` và `OTHER`

Một số procedure trả kết quả phức tạp qua tham số OUT thay vì số hoặc chuỗi.

### 10.1. REF CURSOR

JDBC 4.2 có `Types.REF_CURSOR`, dùng cho những DBMS và driver hỗ trợ con trỏ trả về qua OUT:

```java
import java.sql.ResultSet;
import java.sql.Types;

// Giả định procedure thật có một OUT REF CURSOR tại vị trí 1.
call.registerOutParameter(1, Types.REF_CURSOR);
call.execute();

Object returned = call.getObject(1);
if (returned instanceof ResultSet cursor) {
    try (ResultSet rs = cursor) {
        while (rs.next()) {
            System.out.println(rs.getString(1));
        }
    }
}
```

Đây là **mẫu minh họa**, không bảo đảm dùng nguyên xi trên tất cả DBMS. Với PostgreSQL và Oracle, kiểu cursor có quy tắc riêng về cú pháp gọi, chuyển kiểu JDBC, transaction còn mở và cách đóng tài nguyên. Một số driver đời cũ dùng hằng số kiểu riêng của nhà cung cấp hoặc `Types.OTHER` và cần cast kết quả theo API tương ứng.

Con trỏ có thể phụ thuộc vào **thời gian sống của transaction**; nếu commit/đóng kết nối quá sớm, ứng dụng không còn đọc được dữ liệu từ cursor. Luôn đọc tài liệu driver cụ thể khi dùng OUT cursor.

### 10.2. Kiểu SQL do người dùng định nghĩa

Nếu procedure khai báo OUT là một SQL structured type do DBMS định nghĩa, một số driver yêu cầu tên kiểu:

```java
// Minh họa cú pháp API; "APP.ADDRESS_TYPE" phải thực sự tồn tại
// và được driver/DBMS hỗ trợ như một SQL structured type.
call.registerOutParameter(
        2, Types.STRUCT, "APP.ADDRESS_TYPE");
```

Overload này không có nghĩa mọi DBMS đều hỗ trợ `STRUCT` giống nhau. Tương tự, `Types.OTHER` có thể được driver dùng cho các kiểu riêng như một số dạng UUID/JSON/enum, nhưng **không** phải lựa chọn mặc định khi chưa biết SQL type. Nếu đăng ký `OTHER` hoặc `STRUCT`, cần thử dữ liệu thực tế và xác nhận cách `getObject` trả đối tượng.

### 10.3. Dữ liệu ngày giờ và timezone

Hai kiểu OUT `TIMESTAMP` và `TIMESTAMP WITH TIME ZONE` có ngữ nghĩa khác nhau. Ở nơi driver hỗ trợ JDBC 4.2:

```java
import java.sql.Types;
import java.time.OffsetDateTime;

call.registerOutParameter(2, Types.TIMESTAMP_WITH_TIMEZONE);
call.execute();

OffsetDateTime when =
        call.getObject(2, OffsetDateTime.class);
```

Không phải DBMS nào cũng khai báo hay lưu timezone theo cùng cách; có DBMS chuẩn hóa thời điểm theo timezone của phiên, có DBMS dùng kiểu không chứa offset và driver áp dụng quy tắc chuyển đổi. Luôn chọn kiểu theo **cột OUT trong procedure**, quy ước timezone của hệ thống và khả năng của driver.

## 11. Nhiều `ResultSet` và update count không thay thế OUT

Một procedure có thể thực hiện `UPDATE` và chạy một hoặc nhiều `SELECT`, bên cạnh việc gán tham số OUT. Do đó `CallableStatement.execute()` trả `boolean` cho biết **kết quả đầu tiên có phải `ResultSet` không**, chứ không có nghĩa “procedure thành công hay thất bại”.

Với procedure trả nhiều kết quả, JDBC có thể duyệt:

```java
boolean hasResultSet = call.execute();

while (true) {
    if (hasResultSet) {
        try (ResultSet rs = call.getResultSet()) {
            while (rs.next()) {
                // Ánh xạ hàng của ResultSet này.
            }
        }
    } else {
        int updateCount = call.getUpdateCount();
        if (updateCount == -1) {
            break; // Hết cả ResultSet lẫn update count.
        }
        // Xử lý update count nếu hợp đồng procedure cần.
    }

    hasResultSet = call.getMoreResults();
}

// Đọc các giá trị OUT đã được register theo hợp đồng driver.
```

Các ví dụ trên giả định `CallableStatement` vẫn còn mở; nếu dùng con trỏ hoặc result set của procedure, cần chú ý chúng có thể bị đóng khi chuyển kết quả. Một số driver chỉ làm cho OUT values khả dụng sau khi các kết quả trung gian đã được xử lý. Vì thế, **không giả định mọi procedure chỉ trả OUT**, và nên kiểm tra hợp đồng driver với procedure có nhiều kết quả.

Trong ví dụ `read_paid_summary` tại mục 5, câu `SELECT ... INTO` không tạo một `ResultSet` người dùng phải duyệt. Chỉ cần `execute()` và lấy các OUT values.

## 12. Xác định đúng kiểu OUT từ metadata và schema

Khi làm việc với hệ thống có nhiều stored procedure, có thể tra cứu metadata:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ProcedureMetadataInspector {
    private ProcedureMetadataInspector() {}

    public static void showParameters(DataSource source)
            throws SQLException {
        try (Connection connection = source.getConnection()) {
            DatabaseMetaData metadata = connection.getMetaData();

            try (ResultSet columns = metadata.getProcedureColumns(
                    connection.getCatalog(),
                    null,
                    "read_paid_summary",
                    "%")) {
                while (columns.next()) {
                    System.out.printf(
                            "%s: mode=%d, jdbcType=%d, typeName=%s%n",
                            columns.getString("COLUMN_NAME"),
                            columns.getShort("COLUMN_TYPE"),
                            columns.getInt("DATA_TYPE"),
                            columns.getString("TYPE_NAME"));
                }
            }
        }
    }
}
```

Trong `DatabaseMetaData.getProcedureColumns(...)`:

- `COLUMN_TYPE` phân loại tham số đầu vào, đầu ra hoặc đầu vào/đầu ra (giá trị so sánh với các hằng `DatabaseMetaData.procedureColumnIn`, `procedureColumnOut`, `procedureColumnInOut`).
- `DATA_TYPE` là mã JDBC SQL type thuộc tập `java.sql.Types`; `TYPE_NAME` là tên kiểu của DBMS.
- `PRECISION`, `LENGTH`, `SCALE` và các trường khác có thể giúp hiểu tham số thập phân hoặc văn bản, nhưng độ đầy đủ phụ thuộc driver.

Tính khả dụng của metadata khác nhau theo quyền truy cập, DBMS, tên catalog/schema, driver, cách khai báo procedure và overload. `CallableStatement.getParameterMetaData()` cũng có thể không cho biết chính xác tất cả loại OUT/INOUT.

Vì vậy, tài liệu khai báo procedure và schema/migration **vẫn là nguồn hợp đồng chính**. Nếu metadata không đầy đủ, không suy kiểu bằng cách thử lần lượt `Types.INTEGER`, `Types.VARCHAR` rồi mặc định chọn cái “chạy được”.

## 13. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách giải quyết |
| --- | --- | --- |
| Báo lỗi “output parameter not registered” | Quên `registerOutParameter` hoặc đăng ký sai vị trí | Kiểm tra toàn bộ chữ ký và đánh số bắt đầu từ 1 |
| OUT `DECIMAL` trả sai/mất phần lẻ | Đăng ký/đọc bằng `INTEGER`, `DOUBLE` hoặc dùng scale không phù hợp | Khai báo `Types.DECIMAL`/`NUMERIC` và `getBigDecimal` |
| `OUT BIGINT` bị tràn khi đọc | Sử dụng `getInt` hoặc `int` | Đọc `getLong` và kiểm tra quy tắc miền giá trị |
| OUT `NULL` thành số 0 | `getLong`/`getInt` trả 0 cho SQL NULL | Gọi `wasNull()` ngay sau getter, dùng kiểu boxed khi cần |
| `INOUT` trả lỗi hoặc không cập nhật | Chỉ `set` mà chưa `register` hoặc ngược lại | Làm cả hai trước `execute` |
| Đăng ký `JDBCType` không chạy | Driver không hỗ trợ overload `SQLType` | Dùng `Types` với driver tương thích hoặc nâng cấp driver |
| Không tìm thấy procedure/function | Sai catalog/schema, tên, chế độ gọi hoặc quyền `EXECUTE` | Kiểm tra tên đầy đủ, quyền và dialect |
| Cursor OUT không đọc được | Sai loại `REF_CURSOR`/type riêng hoặc transaction đã kết thúc | Xác minh driver, kiểu và vòng đời cursor |
| Lẫn `ResultSet` với OUT | Procedure trả `SELECT` và OUT đồng thời | Xử lý chuỗi kết quả bằng `getMoreResults` và đọc OUT đúng thời điểm |
| Driver trả kiểu kỳ lạ qua `getObject` | Dùng kiểu DBMS riêng không có mapping chuẩn | Đọc tài liệu driver, ánh xạ tường minh, thử trên DBMS thật |

**An toàn:** Cú pháp tham số `?` chỉ thay thế **giá trị** `IN`; không dùng nó để thay tên procedure, schema hoặc tên tham số. Hãy chọn tên procedure từ cấu hình tin cậy hoặc danh sách cho phép, không ghép trực tiếp chuỗi do người dùng nhập. Quyền `EXECUTE` trên procedure cũng phải được giới hạn theo chức năng; stored procedure không tự động làm mọi mã gọi nó an toàn.

## 14. Kiểm thử đăng ký OUT theo hợp đồng thực tế

Với procedure MySQL ở mục 5, các ca kiểm thử nên bao gồm:

| Trường hợp | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Nhiều đơn đã thanh toán | Khách `101` | `orderCount=2`, `paidTotal=199.75`, `lastOrderId=2` |
| Một đơn đã thanh toán | Khách `102` | `orderCount=1`, `paidTotal=25.00`, `lastOrderId=4` |
| Không có đơn | Khách `999` | `orderCount=0`, `paidTotal=0.00`, `lastOrderId=null` |
| Đơn bị hủy | Khách `101` có thêm `CANCELLED` | Không tính đơn bị hủy vào số đếm và tổng |
| Giá trị tiền sát giới hạn precision | Dữ liệu test `DECIMAL(18,2)` | Không tràn, không mất giá trị ngoài quy tắc SQL |
| `INOUT` | Counter `10`, increment `5` | OUT tại vị trí 1 là `15` |
| Sai kiểu/vị trí đăng ký | Đăng ký OUT không trùng chữ ký | Bắt được lỗi đúng; không tiếp tục dựa trên dữ liệu sai |
| Nhiều kết quả | Procedure chuyên biệt có `SELECT` và OUT | Đọc hết kết quả cần thiết, lấy OUT thành công |

Kiểm thử JDBC tích hợp phải chạy với **cùng DBMS và phiên bản driver** dự kiến dùng ở môi trường vận hành. Một test chỉ mô phỏng `CallableStatement` không thể xác nhận đầy đủ conversion `DECIMAL`, cursor, metadata hay sự hỗ trợ của `SQLType` overload.

Nếu procedure thay đổi dữ liệu, cần kiểm tra cả rollback/commit và những trường hợp SQL failure; không xem `execute()` trả `false` là lỗi, cũng không mặc định `execute()` trả `true` là thành công của toàn nghiệp vụ.

## 15. Checklist lựa chọn kiểu SQL

Trước khi viết `registerOutParameter`:

1. **Đọc chữ ký procedure/function** để biết thứ tự, chế độ `IN/OUT/INOUT` và tên kiểu SQL thực.
2. **Đăng ký đúng kiểu SQL** bằng `Types` hoặc `JDBCType`, không quyết định theo kiểu giao diện hay thói quen đọc `String`.
3. **Xác nhận scale và precision** nếu có `DECIMAL`/`NUMERIC`; dùng `BigDecimal` khi cần chính xác.
4. **Gán đủ tham số IN/INOUT** bằng `setXxx` hoặc `setNull` thích hợp.
5. **Đăng ký tất cả OUT/INOUT trước `execute`** và đọc bằng getter tương thích; xử lý SQL `NULL`.
6. **Kiểm tra dialect** khi dùng return function, named parameters, `REF_CURSOR`, kiểu DBMS riêng và procedure có nhiều kết quả.
7. **Quản lý Connection/transaction** theo nghiệp vụ, nhất là nếu procedure cập nhật nhiều bảng hoặc mở cursor.
8. **Kiểm thử trên driver thật**, bao gồm dữ liệu lớn, ký tự Unicode, giá trị NULL, scale số, lỗi schema và quyền gọi procedure.

**Ghi nhớ:** Khi gọi thủ tục lưu trữ bằng JDBC, `registerOutParameter` là lời khai báo **kiểu SQL và vị trí của tham số đầu ra** cho driver, không phải thao tác tạo ra kết quả. Hãy chọn `Types`/`JDBCType` theo chữ ký stored procedure, dùng `setXxx` cho IN/INOUT, `execute()` để chạy, `getXxx` để đọc OUT, xử lý `NULL` và xác minh các tính năng đặc biệt theo DBMS/driver. Làm đúng như vậy giúp dữ liệu tổng hợp, số tiền và các giá trị trả về được ánh xạ chính xác, dễ kiểm thử và dễ bảo trì.

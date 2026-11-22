# Phân biệt tham số theo vị trí và tham số theo tên trong JDBC

## 1. Vấn đề cần giải quyết

Trong JDBC, ứng dụng Java có thể gọi **stored procedure** (thủ tục lưu trữ) qua `CallableStatement`. Một thủ tục có thể có tham số đầu vào (`IN`), đầu ra (`OUT`) hoặc vừa đầu vào vừa đầu ra (`INOUT`). Khi gán và đọc các tham số này, Java cung cấp hai cách tham chiếu chính:

- **Theo vị trí** (*positional parameters*): chỉ rõ thứ tự tham số bằng số nguyên, ví dụ `setLong(1, customerId)`, `registerOutParameter(3, Types.INTEGER)` và `getInt(3)`.
- **Theo tên** (*named parameters*): chỉ rõ tên tham số mà thủ tục khai báo, ví dụ `setLong("p_customer_id", customerId)`, `registerOutParameter("p_rows_changed", Types.INTEGER)` và `getInt("p_rows_changed")`, **khi driver và cơ sở dữ liệu hỗ trợ** các overload này.

Hai cách diễn đạt cùng một ý định: gắn giá trị Java với **tham số hình thức** của thủ tục trong cơ sở dữ liệu. Khác biệt nằm ở cách định danh tham số, khả năng tương thích driver, mức phụ thuộc vào chữ ký thủ tục và cách chẩn đoán lỗi.

Bài thuộc chương **Thủ tục lưu trữ** của module **JDBC**, trong phạm vi dùng driver, `DataSource`, `PreparedStatement`, `CallableStatement`, `ResultSet`, câu lệnh SQL tham số hóa, CRUD, quản lý kết nối, transaction và xử lý lỗi. Sau bài học, bạn có thể:

1. Viết lời gọi thủ tục với `CallableStatement` bằng **chỉ số** và **tên**.
2. Ánh xạ `IN`, `OUT`, `INOUT` và giá trị trả về của function đúng quy tắc.
3. Phân biệt **tham số theo tên của API JDBC** với **cú pháp named arguments trong SQL riêng của DB** và với placeholder `?`.
4. Nhận diện những driver không hỗ trợ named access, đặc biệt khi phải chạy với nhiều hệ quản trị.
5. Chọn cách truyền tham số phù hợp, giữ đúng transaction và viết kiểm thử tích hợp.

## 2. Ví dụ thực tế: thủ tục đổi trạng thái khách hàng

Giả sử ứng dụng cần gọi thủ tục cập nhật trạng thái khách hàng, sau đó nhận số hàng được cập nhật. Thủ tục có ba tham số:

| Thứ tự khai báo | Tên trong DB | Chế độ | Kiểu SQL | Ý nghĩa |
|---:|---|---|---|---|
| 1 | `p_customer_id` | `IN` | `BIGINT` | Khóa khách hàng cần cập nhật |
| 2 | `p_new_status` | `IN` | `VARCHAR(20)` | Trạng thái mới |
| 3 | `p_rows_changed` | `OUT` | `INTEGER` | Số hàng được cập nhật |

Để có ví dụ chạy được trên một hệ quản trị cụ thể, ta dùng cú pháp **MySQL** sau. Cú pháp định nghĩa procedure khác nhau giữa PostgreSQL, Oracle, SQL Server và MySQL; không nên sao chép đoạn DDL này sang DB khác rồi giả định tương thích.

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);

INSERT INTO customers (id, status)
VALUES (101, 'PENDING'), (102, 'ACTIVE');
```

Trong một công cụ hỗ trợ thay đổi dấu kết thúc câu lệnh, chẳng hạn MySQL CLI, tạo procedure:

```sql
DELIMITER //

CREATE PROCEDURE change_customer_status(
    IN p_customer_id BIGINT,
    IN p_new_status VARCHAR(20),
    OUT p_rows_changed INT
)
BEGIN
    UPDATE customers
    SET status = p_new_status
    WHERE id = p_customer_id;

    SET p_rows_changed = ROW_COUNT();
END //

DELIMITER ;
```

`DELIMITER` là lệnh của **công cụ khách MySQL**, không phải câu SQL gửi qua JDBC. Khi chạy migration bằng một công cụ khác, hãy dùng cơ chế phân tách câu lệnh mà công cụ đó hỗ trợ.

Lời gọi qua JDBC escape syntax:

```sql
{call change_customer_status(?, ?, ?)}
```

Ba dấu `?` tương ứng với **ba vị trí** trong chữ ký thủ tục. Kể cả khi ứng dụng chọn các overload `setXxx(String parameterName, ...)`, chuỗi call escape trên vẫn chứa `?`; tên tham số được chuyển qua **API `CallableStatement`**, không phải bằng cách tự thay `?` thành `:p_customer_id`.

## 3. Cách A: tham số theo vị trí

### 3.1. Quy tắc đánh chỉ số

Với procedure `change_customer_status(IN, IN, OUT)`, thứ tự các vị trí là:

```text
Java CallableStatement:
{call change_customer_status( ?,               ?,             ? )}
                               1                2              3
                               |                |              |
                         p_customer_id     p_new_status    p_rows_changed
                               IN               IN            OUT
```

**Chỉ số tham số trong JDBC bắt đầu từ 1**, không phải 0. Chỉ số ở đây là **vị trí tham số trong lời gọi**, không phải index hàng của một mảng Java.

Các bước cơ bản:

1. Tạo `CallableStatement` với `Connection.prepareCall(...)`.
2. Đăng ký từng tham số `OUT` hoặc `INOUT` bằng `registerOutParameter(index, sqlType)` trước khi thực thi.
3. Gán các tham số `IN` hoặc phần đầu vào của `INOUT` bằng `setXxx(index, value)`.
4. Thực thi bằng `execute()` khi thủ tục có thể tạo các loại kết quả khác nhau.
5. Đọc tham số `OUT` sau khi thực thi, kiểm tra `wasNull()` ngay sau getter kiểu nguyên thủy nếu cần.

### 3.2. Ví dụ Java hoàn chỉnh dùng DataSource

Đoạn mã Java 17+ dưới đây gọi đúng procedure đã định nghĩa ở trên:

```java
import javax.sql.DataSource;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Objects;

public final class CustomerProcedureGateway {
    private static final String CALL_SQL =
            "{call change_customer_status(?, ?, ?)}";

    private final DataSource dataSource;

    public CustomerProcedureGateway(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public int changeStatusByPosition(
            long customerId, String newStatus
    ) throws SQLException {
        if (newStatus == null
                || newStatus.isBlank()
                || newStatus.length() > 20) {
            throw new IllegalArgumentException("newStatus không hợp lệ");
        }

        try (Connection connection = dataSource.getConnection();
             CallableStatement call =
                     connection.prepareCall(CALL_SQL)) {
            call.registerOutParameter(3, Types.INTEGER);
            call.setLong(1, customerId);
            call.setString(2, newStatus);

            call.execute();

            int changed = call.getInt(3);
            if (call.wasNull()) {
                throw new SQLException(
                        "Procedure trả p_rows_changed = NULL");
            }
            return changed;
        }
    }
}
```

Ví dụ giả định `DataSource` đã được cấu hình cho DB có procedure nêu trên. Phương thức có thể trả `0` nếu không có khách hàng nào khớp ID; `0` **không phải** `NULL`. Ứng dụng phải quyết định việc không tìm thấy khách hàng là kết quả hợp lệ hay cần báo lỗi nghiệp vụ.

`execute()` trả `boolean` cho biết **kết quả đầu tiên** có phải `ResultSet` hay không. Giá trị `boolean` đó **không phải** giá trị của tham số `p_rows_changed`; muốn đọc kết quả `OUT`, vẫn phải gọi `getInt(3)` sau khi thực thi.

Đối với thủ tục trả cả `ResultSet` hoặc nhiều kết quả, một số driver yêu cầu xử lý/đóng các kết quả trước khi đọc tham số `OUT`. Hãy kiểm tra hợp đồng driver; ví dụ trên chỉ dùng một procedure cập nhật với tham số `OUT`.

### 3.3. Ưu điểm và rủi ro của index

Cách theo vị trí thường là lựa chọn trực tiếp, dễ hiểu và có tính tương thích thực tế tốt trên nhiều JDBC driver. Nó cũng không cần hỏi driver ánh xạ **tên tham số hình thức** sang vị trí nào.

Tuy nhiên, code phụ thuộc vào **thứ tự** của lời gọi:

```java
call.setLong(1, customerId);   // IN thứ nhất
call.setString(2, newStatus);  // IN thứ hai
call.registerOutParameter(3, Types.INTEGER); // OUT thứ ba
```

Nếu DB thay chữ ký thành `change_customer_status(IN p_new_status VARCHAR(20), IN p_customer_id BIGINT, OUT ...)`, các index phải được cập nhật. Nếu hai tham số đổi chỗ đều có cùng kiểu như `String`, driver có thể không báo lỗi ngay mà thủ tục nhận nhầm giá trị. Vì vậy, nên xem chữ ký thủ tục như **hợp đồng API** giữa Java và database, có kiểm thử tích hợp.

## 4. Cách B: tham số theo tên

### 4.1. Các overload của CallableStatement

JDBC định nghĩa các phương thức thao tác theo tên tham số:

```java
call.setLong("p_customer_id", customerId);
call.setString("p_new_status", newStatus);
call.registerOutParameter("p_rows_changed", Types.INTEGER);

// Sau execute():
int changed = call.getInt("p_rows_changed");
```

Các chuỗi tên phải tương ứng với tên tham số mà thủ tục khai báo (hoặc dạng tên mà driver công nhận). Chẳng hạn `p_customer_id` là tên **tham số IN** trong chữ ký procedure, không phải tên một cột `ResultSet`.

**Điều kiện rất quan trọng:** mặc dù các overload nhận `String parameterName` là một phần của giao diện JDBC, một số driver **không hỗ trợ** truy cập tham số thủ tục theo tên hoặc có giới hạn về cách xác định tên, chữ hoa/chữ thường, schema, overload và metadata. Driver có thể ném `SQLFeatureNotSupportedException` hoặc một `SQLException` khác. Không nên hứa rằng mọi đoạn code theo tên chạy được trên mọi DB chỉ vì biên dịch Java thành công.

### 4.2. Ví dụ Java theo tên

Để so sánh trực tiếp, giữ nguyên chuỗi call `{call change_customer_status(?, ?, ?)}` và thay các lời gọi theo index bằng lời gọi theo tên:

```java
import javax.sql.DataSource;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Types;

public final class NamedCustomerProcedureGateway {
    private final DataSource dataSource;

    public NamedCustomerProcedureGateway(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int changeStatusByName(
            long customerId, String newStatus
    ) throws SQLException {
        String sql = "{call change_customer_status(?, ?, ?)}";

        try (Connection connection = dataSource.getConnection();
             CallableStatement call = connection.prepareCall(sql)) {
            call.registerOutParameter(
                    "p_rows_changed", Types.INTEGER);
            call.setLong("p_customer_id", customerId);
            call.setString("p_new_status", newStatus);

            call.execute();

            int changed = call.getInt("p_rows_changed");
            if (call.wasNull()) {
                throw new SQLException(
                        "Procedure trả p_rows_changed = NULL");
            }
            return changed;
        }
    }
}
```

Đây là **ví dụ cách dùng API JDBC khi driver hỗ trợ named access**, không phải cam kết riêng cho tất cả bản phát hành driver MySQL hay các DB khác. Muốn triển khai thật, hãy kiểm thử với phiên bản JDBC driver, cấu hình quyền truy cập metadata và phiên bản DB mục tiêu.

Tên tham số khiến code thể hiện ý nghĩa rõ hơn và có thể tránh lỗi nhầm vị trí trong môi trường hỗ trợ tốt. Nhưng nó tạo phụ thuộc vào **tên hình thức**: nếu DBA đổi `p_rows_changed` thành `p_updated_count`, code Java theo tên phải được cập nhật, dù số thứ tự tham số không đổi.

### 4.3. Không tự trộn tên và index theo thói quen

Về mặt ý tưởng, một `CallableStatement` có thể có nhiều overload cho tên và vị trí; tuy nhiên, khả năng phối hợp, cách định danh và số lần ánh xạ có thể phụ thuộc driver. Để dễ kiểm tra và bảo trì, nên **chọn nhất quán một chiến lược** cho từng lời gọi:

- Theo index: `setXxx(1, ...)`, `registerOutParameter(3, ...)`, `getXxx(3)`.
- Theo tên: `setXxx("p_customer_id", ...)`, `registerOutParameter("p_rows_changed", ...)`, `getXxx("p_rows_changed")`.

Không nên hardcode một phần theo tên, một phần theo số chỉ để “đỡ gõ”, nhất là khi thủ tục đang thay đổi chữ ký và cần bảo đảm mọi tham số cùng tham chiếu đúng vị trí.

## 5. Ba khái niệm dễ bị nhầm lẫn

### 5.1. Named parameters của CallableStatement không phải SQL `:name`

Trong JDBC chuẩn, `PreparedStatement` thường bind giá trị bằng **dấu `?` và index**:

```java
String sql = "SELECT * FROM customers WHERE id = ?";
PreparedStatement ps = connection.prepareStatement(sql);
ps.setLong(1, customerId);
```

Chuỗi SQL sau **không phải cú pháp named placeholder chuẩn của PreparedStatement JDBC**:

```sql
SELECT * FROM customers WHERE id = :customerId
```

Một số framework và thư viện như Spring hỗ trợ kiểu placeholder có tên rồi dịch sang JDBC, nhưng đây là **cơ chế của thư viện**, không có nghĩa `PreparedStatement.setLong("customerId", ...)` tồn tại trong API JDBC chuẩn.

`CallableStatement` là giao diện **riêng cho thủ tục/hàm**; nó định nghĩa thêm overload `setXxx(String parameterName, ...)` và `registerOutParameter(String parameterName, ...)`. Không thể suy từ đó ra rằng mọi câu SQL thuần đều hỗ trợ bind theo tên.

### 5.2. Named parameters của CallableStatement khác named arguments trong SQL

Một số DB cho phép viết **named arguments** trực tiếp trong SQL, chẳng hạn cú pháp minh họa kiểu:

```sql
-- Ví dụ cú pháp named notation của PostgreSQL cho lời gọi function.
SELECT some_function(
    arg_name => 123,
    flag => TRUE
);
```

Đây là **cú pháp của SQL dialect**, do server phân giải tên đối số. Nó **không tự đồng nghĩa** với việc Java gọi `CallableStatement.setInt("arg_name", 123)`.

Nếu dùng `SELECT some_function(arg_name => ?, flag => ?)` trong một driver hỗ trợ dạng SQL đó, các dấu `?` vẫn được bind theo **index của PreparedStatement**. Còn `setInt(String parameterName, ...)` là cơ chế của `CallableStatement` và cần được driver hỗ trợ độc lập.

Không nên nhầm cú pháp named argument của một DB với cú pháp `:arg` do framework cung cấp. Ba lớp này có nơi giải quyết tên tham số khác nhau:

| Cơ chế | Ai phân giải tên? | Ví dụ |
|---|---|---|
| `CallableStatement.setXxx("p_id", ...)` | JDBC driver và metadata/thực thi của procedure | `call.setLong("p_customer_id", 101)` |
| SQL named argument theo dialect | Bộ phân tích SQL của DB | `arg_name => ?` ở DB hỗ trợ |
| Framework named placeholder | Thư viện phía Java trước khi gửi SQL qua JDBC | `:customerId` trong API hỗ trợ của framework |

### 5.3. Tên tham số OUT khác tên cột trong ResultSet

`getInt("p_rows_changed")` của `CallableStatement` lấy **tham số OUT**; `rs.getInt("rows_changed")` của `ResultSet` lấy **cột trong một hàng kết quả**. Dù cùng dùng `String`, hai thao tác khác nhau về nơi lưu giá trị, vòng đời và hợp đồng SQL.

Procedure có thể trả đồng thời nhiều `ResultSet` và tham số `OUT`. Muốn lấy cột từ `ResultSet`, phải dùng chính result set đã được trả về; không thể thay bằng `CallableStatement.getXxx("tên_cột")` nếu đó không phải tên tham số OUT.

## 6. IN, OUT và INOUT: khác nhau ở cách gán và đọc

| Chế độ tham số | Java thực hiện trước `execute()` | Java thực hiện sau `execute()` |
|---|---|---|
| `IN` | `setXxx(index/name, value)` | Thông thường không đọc lại qua `CallableStatement.getXxx(...)` |
| `OUT` | `registerOutParameter(index/name, sqlType)` | `getXxx(index/name)`; kiểm tra null nếu cần |
| `INOUT` | **Cả** `setXxx(...)` **và** `registerOutParameter(...)` cho cùng một tham số | `getXxx(...)` đọc giá trị cuối do procedure cung cấp |
| Giá trị trả về của function | `registerOutParameter` cho vị trí return theo escape syntax | Đọc return value sau khi thực thi theo cơ chế driver hỗ trợ |

### 6.1. Ví dụ INOUT theo vị trí

Giả sử có procedure `increase_value(INOUT p_current INTEGER, IN p_step INTEGER)`, được DB định nghĩa theo dialect tương ứng. Sau khi gọi, giá trị `p_current` là tổng giá trị ban đầu và `p_step`.

```java
try (CallableStatement call = connection.prepareCall(
        "{call increase_value(?, ?)}")) {
    call.registerOutParameter(1, Types.INTEGER);  // INOUT
    call.setInt(1, 10);                           // giá trị IN của INOUT
    call.setInt(2, 5);                            // IN

    call.execute();

    int updated = call.getInt(1);                  // kỳ vọng 15
    if (call.wasNull()) {
        throw new SQLException("p_current là NULL");
    }
}
```

`connection` là `Connection` đã được caller cấp; ví dụ cần import `java.sql.CallableStatement`, `java.sql.Types`, `java.sql.SQLException`. Với cách theo tên và driver hỗ trợ, các lời gọi tương ứng là `registerOutParameter("p_current", Types.INTEGER)`, `setInt("p_current", 10)`, `setInt("p_step", 5)`, `getInt("p_current")`.

**Lỗi thường gặp:** chỉ `setInt` cho tham số `INOUT` mà quên `registerOutParameter`, hoặc chỉ đăng ký `OUT` mà không gán giá trị đầu vào cho `INOUT`.

### 6.2. SQL NULL và getter primitive

`CallableStatement.getInt(...)` trả `0` nếu giá trị OUT là SQL `NULL`; `getLong(...)` cũng trả `0` trong tình huống tương tự. Để phân biệt `NULL` với giá trị 0 hợp lệ:

```java
int result = call.getInt(3);
if (call.wasNull()) {
    // Tham số OUT vừa đọc là SQL NULL.
}
```

`wasNull()` phải được gọi ngay sau getter mà bạn muốn kiểm tra. Với các kiểu tham chiếu như `BigDecimal`, `String`, `Date`, getter có thể trả `null` trực tiếp.

Đối với tham số đầu vào SQL `NULL`, dùng overload `setNull(index, sqlType)` hoặc `setNull(parameterName, sqlType)` nếu cách truy cập theo tên được hỗ trợ. Không nên tùy tiện thay null bằng `0`, chuỗi rỗng hoặc giá trị mặc định nếu điều đó làm thay đổi ý nghĩa nghiệp vụ.

### 6.3. Kiểu SQL cần đăng ký phù hợp

`registerOutParameter(..., Types.INTEGER)` không phải một lời hứa để driver tự đổi mọi giá trị sang `Integer` an toàn. Chọn hằng `java.sql.Types` phù hợp với kiểu OUT được thủ tục khai báo:

- `INTEGER` → `Types.INTEGER`, đọc qua `getInt` hoặc `getObject` có chuyển kiểu được hỗ trợ.
- `BIGINT` → `Types.BIGINT`, đọc qua `getLong`.
- `DECIMAL`/`NUMERIC` → `Types.DECIMAL`/`Types.NUMERIC`, nên đọc qua `getBigDecimal` khi cần độ chính xác số thập phân.
- `VARCHAR` → `Types.VARCHAR`, đọc qua `getString`.
- `DATE` → `Types.DATE`, chuyển đổi sang `LocalDate` theo khả năng driver.

Với kiểu có scale, các overload `registerOutParameter(..., sqlType, scale)` có thể được áp dụng theo yêu cầu của kiểu/driver. Một số kiểu DB đặc thù, cursor hoặc cấu trúc phức tạp có thể cần API hay type name riêng.

## 7. Function return value làm thay đổi index

Trong cú pháp escape chuẩn dùng cho function, thường có dạng:

```sql
{? = call calculate_total(?)}
```

Khi dùng cơ chế này:

```text
{ ?      = call calculate_total( ? ) }
  |                              |
  1                              2
  |                              |
Giá trị return                 IN argument
```

**Vị trí 1 là giá trị trả về của function**, còn tham số đầu vào đầu tiên của function nằm ở vị trí 2 của `CallableStatement`. Không nhầm “tham số đầu vào đầu tiên” với “placeholder thứ nhất” trong lời gọi function.

```java
try (CallableStatement call = connection.prepareCall(
        "{? = call calculate_total(?)}")) {
    call.registerOutParameter(1, Types.DECIMAL); // return value
    call.setLong(2, orderId);                     // IN argument

    call.execute();

    BigDecimal total = call.getBigDecimal(1);
    if (total == null) {
        throw new SQLException("Function trả NULL");
    }
}
```

Đoạn này giả định `calculate_total` là function phù hợp với DB, đã được tạo trước, `connection` và `orderId` đã tồn tại; import `java.sql.*` và `java.math.BigDecimal`. Một số DB phân biệt procedure/function, dùng cú pháp gọi và chính sách hỗ trợ escape khác nhau. Chẳng hạn driver có thể yêu cầu chế độ đặc biệt để chuyển `{call ...}` thành `CALL` hoặc `SELECT`. Hãy kiểm thử cụ thể trên hệ quản trị đích.

Với function return, cách theo tên cho chính **giá trị return** không phải lúc nào cũng có tên hình thức như các tham số `IN`/`OUT`. Việc đăng ký và đọc return ở **vị trí 1** thường rõ ràng và tương thích hơn; không cố đoán một tên như `"returnValue"` nếu driver không tài liệu hóa.

## 8. So sánh chi tiết hai cách tiếp cận

| Tiêu chí | Theo vị trí | Theo tên |
|---|---|---|
| Cú pháp bind | `setLong(1, id)` | `setLong("p_customer_id", id)` |
| Cú pháp OUT | `registerOutParameter(3, Types.INTEGER)` | `registerOutParameter("p_rows_changed", Types.INTEGER)` |
| Cách hiểu mã | Cần nhìn chữ ký/constant để biết index 1, 2, 3 là gì | Thể hiện ý nghĩa tham số trực tiếp trong lời gọi |
| Khi đổi thứ tự tham số trong chữ ký | Dễ yêu cầu cập nhật index của Java | Có thể dễ duy trì hơn **nếu** driver phân giải tên chính xác và hỗ trợ lời gọi mới |
| Khi đổi tên tham số trong DB | Có thể không ảnh hưởng nếu index/type/hợp đồng không đổi | Có thể làm hỏng lời gọi do tên cũ không còn |
| Hỗ trợ driver thực tế | Thường rộng hơn | Không đồng đều; cần kiểm chứng riêng |
| Phụ thuộc metadata | Có thể bind theo index ngay cả khi tên tham số không được công bố | Có thể cần driver tra cứu tên/mapping từ DB hoặc metadata |
| Phù hợp stored function return | Index 1 cho return trong escape syntax thông dụng | Return value có thể không có tên đáng tin cậy |
| Chi phí hiệu năng | Không có bước người gọi phân giải tên | Có thể phát sinh tra cứu tên tùy driver; hiệu năng cần đo |
| Rủi ro lỗi | Lệch index, lệch kiểu, bỏ sót OUT | Gõ sai tên, khác hoa/thường, driver không hỗ trợ, tên trùng/mơ hồ |

**Không có quy tắc tuyệt đối rằng theo tên luôn an toàn hơn**: tên rõ ràng cải thiện khả năng đọc, nhưng nếu production driver không hỗ trợ, lời gọi thất bại ở runtime. **Cũng không đúng rằng theo vị trí luôn dễ bảo trì hơn**: thay đổi chữ ký có thể tạo lỗi rất khó phát hiện nếu hai tham số cùng kiểu bị đảo chỗ.

### 8.1. Một số quy tắc giúp giảm phụ thuộc vào thứ tự

Nếu quyết định dùng index, nên đặt constant với tên rõ nghĩa cho vị trí:

```java
private static final int CUSTOMER_ID = 1;
private static final int NEW_STATUS = 2;
private static final int ROWS_CHANGED = 3;

// ...
call.setLong(CUSTOMER_ID, customerId);
call.setString(NEW_STATUS, newStatus);
call.registerOutParameter(ROWS_CHANGED, Types.INTEGER);
```

Đây là ví dụ trích đoạn trong lớp Java, không phải biến toàn cục. Constant không tự sửa được lỗi khi DB đổi chữ ký, nhưng giúp code review và cập nhật theo thay đổi dễ hơn.

Nếu dùng named access, có thể tập trung tên vào constant `String` và đối chiếu chúng với migration tạo procedure. Tránh hardcode tên khác nhau ở nhiều repository.

## 9. Tra cứu chữ ký bằng metadata: hữu ích nhưng có giới hạn

### 9.1. DatabaseMetaData.getProcedureColumns

JDBC có `DatabaseMetaData.getProcedureColumns(catalog, schemaPattern, procedureNamePattern, columnNamePattern)` để hỏi DB về các tham số của procedure. Kết quả có thể chứa các cột như `COLUMN_NAME`, `COLUMN_TYPE`, `DATA_TYPE`, `TYPE_NAME` và `ORDINAL_POSITION`:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

static void printProcedureSignature(Connection connection)
        throws SQLException {
    DatabaseMetaData meta = connection.getMetaData();

    try (ResultSet columns = meta.getProcedureColumns(
            null, null, "change_customer_status", "%")) {
        while (columns.next()) {
            String name = columns.getString("COLUMN_NAME");
            int mode = columns.getInt("COLUMN_TYPE");
            int sqlType = columns.getInt("DATA_TYPE");
            int position = columns.getInt("ORDINAL_POSITION");

            System.out.printf(
                    "position=%d name=%s mode=%d sqlType=%d%n",
                    position, name, mode, sqlType);
        }
    }
}
```

Các giá trị mode được chuẩn hóa qua hằng như `DatabaseMetaData.procedureColumnIn`, `procedureColumnOut`, `procedureColumnInOut`, `procedureColumnReturn`, `procedureColumnResult`. Đối với function, có `getFunctionColumns(...)` với tập hằng tương ứng.

**Giới hạn cần hiểu:**

- Database và driver có thể yêu cầu `catalog`, schema, quyền xem metadata hoặc quy tắc phân biệt chữ hoa/thường khác nhau; hai chuỗi `null` ở ví dụ không phải giá trị đúng cho mọi môi trường.
- Một số driver không công bố đầy đủ tham số hoặc không nhất quán về `ORDINAL_POSITION` trong trường hợp function return, overloaded procedure hoặc kiểu tham số đặc biệt.
- Có metadata về tên **không đồng nghĩa** driver chắc chắn hỗ trợ `CallableStatement.setXxx("name", ...)`.
- `CallableStatement.getParameterMetaData()` cung cấp `ParameterMetaData` để hỏi số lượng, chế độ, kiểu tham số khi được hỗ trợ; API này **không có phương thức chuẩn để lấy tên tham số**. Không nên nhầm nó với `DatabaseMetaData.getProcedureColumns()`.

Có thể dùng kết quả metadata để kiểm tra tính tương thích giữa Java và procedure lúc khởi động hoặc trong kiểm thử tích hợp, nhưng tránh truy vấn metadata ở **mỗi lần gọi** nếu không cần: có thể tăng round-trip và chi phí xử lý của driver.

### 9.2. Xác minh tính năng trên driver thực tế

`DatabaseMetaData` có thể cho biết nhiều khả năng SQL hoặc DB, nhưng JDBC không có một công tắc chuẩn duy nhất chứng minh **mọi overload named parameter của một procedure cụ thể sẽ hoạt động**. Cách chắc chắn nhất là thử một lời gọi tối thiểu:

1. Cài đúng phiên bản DB/driver mà ứng dụng sẽ chạy.
2. Tạo procedure thử nghiệm có `IN`, `OUT` và `INOUT` phù hợp.
3. Gọi theo index và đối chiếu kết quả với một câu `SELECT` độc lập.
4. Gọi theo tên, kiểm tra cả `setXxx(String)`, `registerOutParameter(String)` và `getXxx(String)`.
5. Kiểm tra `NULL`, chữ hoa/thường, schema, quyền và hành vi sau khi đổi chữ ký.
6. Kiểm tra exception được ném nếu driver không hỗ trợ hoặc không phân giải được tên.

Nếu named access không dùng được, **fallback sang index** chỉ nên được thiết kế sau khi xác nhận cùng procedure có hợp đồng vị trí rõ ràng. Không bắt mọi `SQLException` rồi âm thầm thử lại cách khác: lỗi có thể đến từ logic thủ tục đã thực thi một phần hoặc từ kết quả commit chưa chắc chắn.

## 10. Kết quả thủ tục và quyền sở hữu transaction

### 10.1. Một lời gọi có thể trả nhiều loại kết quả

`CallableStatement.execute()` có thể dẫn đến `ResultSet`, update count, nhiều kết quả kế tiếp và tham số `OUT`, tùy procedure/driver. Khi procedure tạo nhiều kết quả, cần xử lý bằng `getResultSet()`, `getUpdateCount()`, `getMoreResults()` và quy tắc của driver.

Ví dụ khung duyệt kết quả (không gắn với một procedure cụ thể):

```java
boolean hasResultSet = call.execute();

while (true) {
    if (hasResultSet) {
        try (ResultSet rs = call.getResultSet()) {
            while (rs.next()) {
                // Đọc các cột từ ResultSet này.
            }
        }
    } else {
        int updated = call.getUpdateCount();
        if (updated == -1) {
            break; // không còn kết quả nào
        }
        // Xử lý update count theo hợp đồng.
    }
    hasResultSet = call.getMoreResults();
}

// Đọc tham số OUT ở thời điểm mà driver cho phép,
// sau khi xử lý các kết quả cần thiết.
```

Đoạn trích giả định `call` là `CallableStatement` đã gán/đăng ký tham số, cần import `java.sql.ResultSet`. Một số driver và DB có thể biểu diễn kết quả procedure rất khác nhau; không nên suy rằng `execute() == false` có nghĩa thủ tục thất bại. Nó chỉ nói **kết quả đầu tiên** không phải `ResultSet`.

**Ngữ nghĩa cột kết quả và tham số OUT là độc lập.** Các hàng `ResultSet` đọc bằng `rs.getXxx(columnLabel)`; tham số OUT đọc bằng `call.getXxx(index/name)`.

### 10.2. Stored procedure không tự bảo đảm một transaction nguyên tử

Nếu procedure thay đổi dữ liệu, lời gọi theo index hay theo tên đều chạy trong phạm vi transaction của **Connection** đang dùng. Một số procedure có điều khiển transaction riêng hoặc giới hạn việc gọi trong transaction, tùy DB. Vì vậy, khi caller cần kết hợp gọi procedure với CRUD thông thường, phải kiểm tra quy tắc của DB và giữ cùng connection khi hợp đồng cho phép.

Ví dụ repository chỉ **mượn** connection:

```java
public int changeStatus(
        Connection connection, long customerId, String status
) throws SQLException {
    try (CallableStatement call = connection.prepareCall(
            "{call change_customer_status(?, ?, ?)}")) {
        call.registerOutParameter(3, Types.INTEGER);
        call.setLong(1, customerId);
        call.setString(2, status);
        call.execute();

        int updated = call.getInt(3);
        if (call.wasNull()) {
            throw new SQLException("Không có số hàng cập nhật");
        }
        return updated;
    }
}
```

Đây là một phương thức ví dụ nằm trong lớp repository đã khai báo, sử dụng import `Connection`, `CallableStatement`, `SQLException`, `Types`. Hàm không gọi `connection.commit()`, `rollback()` hoặc `close()`; tầng nghiệp vụ sở hữu connection quyết định khi nào kết thúc transaction.

Nếu tên procedure được chọn động, không nối trực tiếp đầu vào không tin cậy vào SQL. Placeholder `?` chỉ bind **giá trị tham số**, không bind tên procedure hoặc identifier SQL. Hạn chế tên procedure bằng allowlist hoặc cấu hình cố định; đồng thời kiểm tra quyền thực thi procedure và nguy cơ dynamic SQL thiếu tham số hóa **bên trong** procedure.

## 11. Lỗi thường gặp và cách phát hiện

| Hiện tượng | Nguyên nhân có thể | Cách sửa |
|---|---|---|
| Gán tham số bằng index 0 | JDBC đánh chỉ số từ 1 | Dùng index 1, 2, 3 đúng theo thứ tự lời gọi |
| `getXxx(3)` không trả giá trị mong đợi | Chưa `registerOutParameter`, sai SQL type hoặc thứ tự | Đăng ký OUT/INOUT trước `execute()`, đối chiếu chữ ký |
| Đổi thứ tự tham số làm hỏng nghiệp vụ | Java vẫn bind theo index cũ | Cập nhật cùng lúc procedure và Java, có kiểm thử tích hợp |
| `setXxx("p_name", ...)` bị từ chối | Driver không hỗ trợ named access hoặc tên không được phân giải | Kiểm tra hỗ trợ driver, quyền metadata, tên hình thức; dùng index khi phù hợp |
| SQL chứa `:param` bị lỗi | Đang nhầm cú pháp framework với JDBC chuẩn | Dùng `?` trong SQL JDBC hoặc API riêng của framework |
| Đọc OUT bằng `ResultSet.getXxx` | Nhầm OUT parameter với cột trong result set | Dùng `CallableStatement.getXxx` cho OUT |
| Lấy return value của function ở index 2 | Quên placeholder return đứng đầu trong `{? = call ...}` | Đăng ký/đọc return ở index 1 |
| `getInt` trả 0 nhưng thực tế OUT là SQL NULL | Không kiểm tra `wasNull()` | Gọi `wasNull()` ngay sau getter primitive |
| Procedure trả dữ liệu nhưng `execute() == false` | Kết quả đầu tiên là update count | Xem `getUpdateCount()` và `getMoreResults()` |
| Call thất bại sau khi đổi schema | Chữ ký/kiểu/tên/overload hoặc quyền đã thay đổi | Đồng bộ migration, metadata và code, kiểm thử trên DB mục tiêu |
| Không có lỗi Java nhưng dữ liệu sai | Hai tham số `VARCHAR` cùng kiểu bị đảo chỗ | Dùng constant, named access có hỗ trợ, validation và kiểm thử hành vi |
| Retry lại procedure gây cập nhật gấp đôi | Lỗi kết nối xảy ra sau khi DB có thể đã thực thi | Thiết kế idempotency, transaction và đối soát thay vì retry mù |

Đừng bắt `SQLException` để chuyển mọi lỗi thành “tham số sai”. Driver còn có thể trả lỗi kết nối (SQLState class `08`), cú pháp/quy tắc truy cập (`42`), ràng buộc (`23`) và dữ liệu (`22`), hoặc các mã riêng của DB. Khi báo lỗi, nên ghi tên thao tác ổn định, `SQLState`, vendor code và nguyên nhân, tránh lộ mật khẩu hay tham số nhạy cảm trong log.

## 12. Kiểm thử và thực hành

### 12.1. Ma trận kiểm thử bắt buộc

| Trường hợp | Thực hiện | Kỳ vọng |
|---|---|---|
| `IN` hợp lệ | Gọi procedure cho ID có tồn tại | DB cập nhật đúng hàng và OUT báo `1` |
| Không có bản ghi khớp | ID không tồn tại | OUT báo `0`; không nhầm với SQL NULL |
| Gọi theo index | `setLong(1)`, `setString(2)`, `getInt(3)` | Kết quả đúng hợp đồng đã định |
| Gọi theo tên | `setLong("p_customer_id")` và các API named access | Cùng kết quả như positional **nếu driver hỗ trợ** |
| Gõ sai tên tham số | `setLong("p_customerr_id", ...)` | Lỗi được phát hiện, không có giá trị gán nhầm âm thầm |
| Sai chỉ số | `setLong(0, ...)` hoặc index vượt số placeholder | Driver báo lỗi tham số không hợp lệ |
| Quên đăng ký OUT | Không gọi `registerOutParameter` | Lỗi hoặc kết quả không đáp ứng hợp đồng; cần phát hiện |
| OUT trả SQL NULL | Procedure thử nghiệm cho phép OUT nullable | Kiểm tra `wasNull()` đúng |
| INOUT | Gán ban đầu rồi đọc kết quả cuối | Giá trị đầu ra phản ánh thay đổi đúng |
| Function return | Sử dụng `{? = call ...}` | Return ở index 1, IN đầu tiên ở index 2 |
| Migration đổi thứ tự | Hoán đổi hai tham số cùng kiểu trong bản thử nghiệm | Test hành vi phát hiện giá trị bị gán nhầm |
| Driver khác hoặc thiếu metadata | Thử cùng procedure trên driver/DB dự kiến | Xác định rõ tính năng được hỗ trợ và phương án fallback |
| Procedure trả nhiều kết quả | Bản thử nghiệm có kết quả hỗn hợp | Duyệt đúng result sets/update counts và OUT |
| Gọi trong transaction | Cùng Connection cho procedure và CRUD tiếp theo | Lỗi ở bước sau dẫn đến rollback theo quy tắc DB |

Nên dùng **test database** và đúng phiên bản JDBC driver dự kiến triển khai, thay vì chỉ mock `CallableStatement`: mock không xác nhận được metadata, tên tham số, cú pháp call escape hoặc ngữ nghĩa `OUT` thực tế.

### 12.2. Bài tập tự thực hành

1. Tạo procedure `change_customer_status` như mục 2 trong DB thử nghiệm; chạy `changeStatusByPosition(101, "ACTIVE")` và kiểm tra `SELECT status FROM customers WHERE id = 101`.
2. Triển khai `changeStatusByName` bằng tên `p_customer_id`, `p_new_status`, `p_rows_changed`. Nếu driver không hỗ trợ, ghi nhận loại `SQLException` và chọn fallback theo index.
3. Đổi chữ ký procedure trong môi trường thử nghiệm: đảo thứ tự hai tham số IN. Quan sát điều gì xảy ra với code index và code tên, lưu ý rằng bản SQL call có thể cần thay đổi theo cách phân giải của driver.
4. Bổ sung procedure nhỏ có `INOUT` và kiểm tra giá trị trước/sau. Thử truyền và nhận SQL `NULL` nếu hợp đồng cho phép.
5. Thử `DatabaseMetaData.getProcedureColumns(...)` để in tên, mode và vị trí; so sánh với chữ ký thực tế và ghi nhận dữ liệu metadata còn thiếu.
6. Đưa lời gọi procedure vào transaction cùng một `INSERT audit_log` trên đúng `Connection`, cố tình gây lỗi insert rồi kiểm tra dữ liệu sau rollback bằng kết nối độc lập, theo khả năng transaction của DB.

## 13. Ghi nhớ

- **Theo vị trí:** dùng index bắt đầu từ 1 trong `setXxx`, `registerOutParameter` và `getXxx`; phụ thuộc thứ tự của chữ ký procedure.
- **Theo tên:** dùng overload `CallableStatement.*(String parameterName, ...)`; dễ đọc hơn nhưng phụ thuộc tên hình thức và **mức hỗ trợ của JDBC driver**.
- **`IN` cần set**, **`OUT` cần register và get**, **`INOUT` cần cả set/register và get**; dùng kiểu `java.sql.Types` phù hợp và xử lý SQL NULL.
- **Function return** trong `{? = call ...}` thường chiếm vị trí 1; tham số IN đầu tiên bắt đầu từ vị trí 2.
- **Named parameter của `CallableStatement`, named arguments của SQL dialect và placeholder có tên của framework là ba cơ chế khác nhau.**
- **Metadata không bảo đảm named access chạy được**; kiểm thử trực tiếp với đúng DB, driver, schema và quyền.
- **Ranh giới transaction thuộc Connection**, không thuộc phương thức set tham số theo tên hay vị trí; luôn giữ cơ chế commit/rollback và đối soát phù hợp.

# Xử lý tham số INOUT và giá trị trả về trong JDBC

Trong JDBC, `CallableStatement` là giao diện để ứng dụng Java gọi **stored procedure** hoặc **stored function** được cơ sở dữ liệu hỗ trợ. Khác với câu `SELECT` thông thường, một lời gọi routine có thể vừa **nhận đầu vào**, vừa **sửa giá trị một tham số**, vừa **trả giá trị riêng của hàm**. Nếu không phân biệt rõ các cơ chế này, ứng dụng rất dễ đặt sai vị trí tham số, đọc giá trị quá sớm, bỏ sót `NULL` hoặc nhầm kết quả thực thi với kết quả nghiệp vụ.

Bài học thuộc chương **Thủ tục lưu trữ** của module **JDBC**. Mục tiêu là sử dụng các API chuẩn `Connection.prepareCall(...)`, `CallableStatement.setXxx(...)`, `registerOutParameter(...)`, `execute()` và `getXxx(...)` để xử lý chính xác tham số `INOUT` và giá trị trả về. Ta cũng sẽ kết hợp `DataSource`, transaction, `ResultSet`, xử lý lỗi và các kiểm tra tương thích driver.

## 1. Phân biệt IN, OUT, INOUT và giá trị RETURN

Các tham số của stored routine mô tả **chiều dữ liệu** giữa ứng dụng và DBMS.

| Hình thức | Ứng dụng Java đưa dữ liệu vào? | Ứng dụng Java đọc dữ liệu ra? | Cách dùng điển hình |
|---|---|---|---|
| `IN` | Có, qua `setXxx(index, value)` | Không đọc như một output parameter | Mã khách hàng, số lượng cần xử lý, tiêu chí tra cứu |
| `OUT` | Không bắt buộc truyền giá trị đầu vào; cần khai báo kiểu đầu ra | Có, qua `registerOutParameter(...)` rồi `getXxx(...)` | Thông báo trạng thái, tổng được tính, mã vừa sinh |
| `INOUT` | **Có**, phải gán đầu vào | **Có**, phải đăng ký đầu ra rồi đọc lại | Số điểm cần điều chỉnh, bộ đếm hoặc trạng thái cập nhật |
| Giá trị `RETURN` của **function** | Thường là các tham số `IN` riêng của function | Có, qua vị trí trả về của cú pháp call function hoặc cơ chế riêng của DBMS | Giá trị tính toán, trạng thái/nhãn suy ra |

**`INOUT` không phải hai tham số riêng biệt.** Nó là **một vị trí tham số** vừa có giá trị trước khi gọi vừa có giá trị sau khi routine chạy. Vì thế, với một `INOUT` ở vị trí 2, ứng dụng phải:

1. Đăng ký kiểu đầu ra ở **vị trí 2** bằng `registerOutParameter(2, ...)`.
2. Gán đầu vào **cũng ở vị trí 2** bằng `setXxx(2, value)`.
3. Thực thi routine.
4. Đọc lại kết quả bằng `getXxx(2)`.

Giá trị `RETURN` của stored function là khái niệm khác: trong cú pháp escape call của JDBC, nó thường nằm ở **vị trí 1** và các tham số thực sự của function được đánh số tiếp từ **2**.

> **Cẩn thận với tên “return”:** giá trị `boolean` từ `CallableStatement.execute()` **không** phải kết quả của stored function và không phải cờ thành công nghiệp vụ. Nó chỉ cho biết **kết quả đầu tiên có phải `ResultSet` hay không**. Stored routine cũng có thể trả update count và nhiều result set, tách biệt với `INOUT`, `OUT` hay function return.

## 2. Mô hình dữ liệu đi qua lời gọi

Giả sử routine có hợp đồng sau:

```text
adjust_points(
    IN    p_customer_id BIGINT,
    INOUT p_points      INTEGER,
    OUT   p_message     VARCHAR
)
```

Java truyền `p_customer_id = 42` và `p_points = 80`. Routine cộng thêm 10 vào `p_points`, trả `p_points = 90` và gán `p_message = "Customer 42 updated"`.

```mermaid
sequenceDiagram
    participant Java as Ứng dụng Java
    participant JDBC as CallableStatement
    participant DB as Stored procedure
    Java->>JDBC: registerOutParameter(2, INTEGER)
    Java->>JDBC: registerOutParameter(3, VARCHAR)
    Java->>JDBC: setLong(1, 42)
    Java->>JDBC: setInt(2, 80)
    Java->>JDBC: execute()
    JDBC->>DB: CALL adjust_points(42, 80, OUT)
    DB-->>JDBC: INOUT=90; OUT=thông báo
    Java->>JDBC: getInt(2); getString(3)
    JDBC-->>Java: 90; "Customer 42 updated"
```

Phương thức Java **không** nhận trực tiếp `90` qua giá trị trả về của `execute()`. Kết quả được đọc thông qua tham số đã đăng ký sau khi lời gọi hoàn tất.

## 3. Chuẩn bị stored procedure minh họa

Cú pháp tạo routine **không đồng nhất giữa các hệ quản trị**. Để có ví dụ cụ thể, phần này dùng **MySQL** với một procedure đơn giản chỉ gán tham số, chưa sửa bảng dữ liệu. Trên PostgreSQL, Oracle, SQL Server hoặc H2, cần viết lại câu DDL theo cú pháp, quy tắc `OUT/INOUT` và driver tương ứng.

Trong MySQL command-line client, có thể tạo procedure với phần thay đổi delimiter như sau:

```sql
-- DELIMITER là lệnh của MySQL CLI, không phải SQL chuẩn
-- và không được gửi nguyên khối qua Statement.execute(...).
DELIMITER $$

CREATE PROCEDURE adjust_points(
    IN p_customer_id BIGINT,
    INOUT p_points INT,
    OUT p_message VARCHAR(80)
)
BEGIN
    SET p_points = COALESCE(p_points, 0) + 10;
    SET p_message = CONCAT('Customer ', p_customer_id, ' updated');
END$$

DELIMITER ;
```

Nếu chạy DDL bằng công cụ quản trị cơ sở dữ liệu, hãy dùng cơ chế thực thi script của chính công cụ đó. Với `Statement.execute(...)` trực tiếp từ JDBC, chỉ gửi **câu `CREATE PROCEDURE` hợp lệ** theo driver/DBMS; không gửi `DELIMITER` như câu SQL. Quyền tạo routine và cách truy cập routine phụ thuộc cấu hình máy chủ.

**Hợp đồng của ví dụ:**

| Vị trí | Tên | Chiều | Kiểu SQL | Ý nghĩa |
|---|---|---|---|---|
| 1 | `p_customer_id` | `IN` | `BIGINT` | Định danh được đưa vào |
| 2 | `p_points` | `INOUT` | `INT` | Điểm ban đầu, sau đó nhận điểm mới |
| 3 | `p_message` | `OUT` | `VARCHAR(80)` | Thông báo trả về |

Vì procedure minh họa chỉ làm phép tính và gán biến, **không có thay đổi bảng cần commit**. Một procedure khác có `INSERT`, `UPDATE` hoặc `DELETE` sẽ có tác động dữ liệu và cần chính sách transaction thích hợp; phần sau trình bày riêng.

## 4. Gọi procedure bằng `CallableStatement`

`Connection.prepareCall(...)` tạo câu lệnh gọi routine. JDBC cung cấp cú pháp **escape** có dạng:

```java
String callSql = "{call adjust_points(?, ?, ?)}";
```

Dấu `?` là placeholder cho tham số. Nó tương tự cơ chế bind tham số ở `PreparedStatement`, nhưng `CallableStatement` còn có khả năng **đăng ký và đọc output parameter**.

Ví dụ hoàn chỉnh với `DataSource` đã được ứng dụng cấu hình:

```java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public final class PointsProcedureCaller {
    private PointsProcedureCaller() {
    }

    public static void runExample(DataSource dataSource)
            throws SQLException {
        String callSql = "{call adjust_points(?, ?, ?)}";

        try (Connection connection = dataSource.getConnection();
             CallableStatement call =
                     connection.prepareCall(callSql)) {

            // Vị trí 2 được dùng theo cả hai chiều.
            call.registerOutParameter(2, Types.INTEGER);
            call.registerOutParameter(3, Types.VARCHAR);

            // Dữ liệu gửi vào procedure:
            call.setLong(1, 42L); // IN p_customer_id
            call.setInt(2, 80);   // INOUT p_points: giá trị ban đầu

            call.execute();

            // Dữ liệu nhận về sau khi procedure đã thực thi:
            int updatedPoints = call.getInt(2);
            String message = call.getString(3);

            System.out.println(updatedPoints); // 90
            System.out.println(message);       // Customer 42 updated
        }
    }
}
```

Khi dùng driver có hỗ trợ đúng hợp đồng routine, ví dụ cho kết quả trên. Một số driver/DBMS có yêu cầu riêng về cách nhận output, khả năng gọi routine hoặc quyền đọc metadata; hãy kiểm tra với **đúng phiên bản** đang triển khai.

### Thứ tự triển khai nên theo

1. **Xác định hợp đồng của routine**: tên, chiều (`IN/OUT/INOUT`), vị trí và kiểu SQL thực tế.
2. **Tạo `CallableStatement`** từ một `Connection` hợp lệ.
3. **Đăng ký** tất cả `OUT` và `INOUT` bằng `registerOutParameter(...)` trước khi thực thi.
4. **Bind đầu vào** cho tất cả `IN` và `INOUT` bằng `setXxx(...)`.
5. **Thực thi** bằng `execute()` (thường phù hợp nếu routine có thể có nhiều dạng kết quả).
6. **Xử lý các result set và update count nếu có**, trước khi đọc output parameter để tăng tính tương thích.
7. **Đọc** các vị trí `OUT/INOUT` bằng `getXxx(...)`, kiểm tra giá trị `NULL` nếu có.
8. **Đóng** `CallableStatement` và `Connection` bằng `try-with-resources`; commit/rollback nếu routine thay đổi dữ liệu và transaction do ứng dụng quản lý.

Việc đăng ký output và gán input đều phải xảy ra **trước `execute()`**; chỉ có thể biết giá trị đầu ra sau khi routine đã chạy. Trong ví dụ, `registerOutParameter(2, ...)` và `setInt(2, ...)` dùng chung chỉ số `2` vì đây là **INOUT**.

## 5. Giá trị trả về của stored function: vị trí `1`

Giả sử muốn tính hạng thành viên từ điểm, routine hợp lý là một **function** trả về một `VARCHAR`. Với MySQL, ví dụ DDL một biểu thức:

```sql
CREATE FUNCTION points_tier(p_points INT)
RETURNS VARCHAR(20)
DETERMINISTIC
RETURN IF(p_points >= 100, 'GOLD', 'STANDARD');
```

Lưu ý cú pháp `CREATE FUNCTION`, yêu cầu quyền và giới hạn routine khác nhau giữa DBMS; mẫu trên mang tính **MySQL**, không phải một câu DDL chuẩn có thể dùng nguyên văn với mọi driver.

Theo JDBC escape syntax, có thể gọi stored function qua `CallableStatement` như sau **nếu driver hỗ trợ dạng function-return này**:

```java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public final class PointsFunctionCaller {
    private PointsFunctionCaller() {
    }

    public static String getTier(DataSource dataSource, int points)
            throws SQLException {
        String callSql = "{? = call points_tier(?)}";

        try (Connection connection = dataSource.getConnection();
             CallableStatement call =
                     connection.prepareCall(callSql)) {

            // Dấu ? đầu tiên dành cho giá trị RETURN của function.
            call.registerOutParameter(1, Types.VARCHAR);

            // Tham số p_points của function ở vị trí thứ hai.
            call.setInt(2, points);

            call.execute();
            return call.getString(1);
        }
    }
}
```

`getTier(dataSource, 120)` được kỳ vọng trả về `"GOLD"`; `getTier(dataSource, 80)` trả về `"STANDARD"` theo logic function mẫu.

### Ba điểm rất dễ nhầm

| Biểu thức | Đây là kết quả gì? | Cách đọc |
|---|---|---|
| `call.execute()` | `boolean` cho biết kết quả đầu tiên có là `ResultSet` hay không. | Không phải business return value. |
| `call.getString(1)` sau khi gọi `{? = call points_tier(?)}` | Giá trị trả về của function đã đăng ký `OUT` tại vị trí 1. | Đọc như một output parameter của JDBC. |
| `call.getInt(2)` sau khi gọi `{call adjust_points(?, ?, ?)}` | Giá trị mới của tham số `INOUT` ở vị trí 2. | Đọc cùng vị trí đã được bind đầu vào. |

Một số hệ quản trị phân biệt rõ procedure và function ở cấp ngôn ngữ SQL; có driver yêu cầu cách gọi function bằng `SELECT function_name(?)` thay vì JDBC escape function. Một số sản phẩm còn hỗ trợ **return status** riêng cho procedure, không đồng nghĩa với `OUT` hay function `RETURN`. Do đó, hãy kiểm tra đặc tả routine và driver trước khi suy từ tên gọi.

## 6. Chỉ số tham số, kiểu dữ liệu và tính tương thích

Một lỗi phổ biến là đếm vị trí sai do nhầm function return với tham số đầu vào. Mỗi `?` trong chuỗi call tương ứng một vị trí JDBC, đánh số **từ 1**.

```text
{call adjust_points(?, ?, ?)}
                    1  2  3
  1 = IN customerId
  2 = INOUT points
  3 = OUT message

{? = call points_tier(?)}
 1                    2
  1 = function RETURN
  2 = IN points
```

Khi gọi API:

```java
call.registerOutParameter(2, java.sql.Types.INTEGER);
call.setInt(2, 80);
```

`java.sql.Types.INTEGER` mô tả **kiểu SQL** của tham số đầu ra. `setInt` mô tả giá trị Java đưa vào theo kiểu tương ứng. Lựa chọn `getInt`, `getLong`, `getBigDecimal` hoặc `getString` phải phù hợp với kiểu được DBMS công bố và có thể bị giới hạn bởi các phép chuyển kiểu driver hỗ trợ.

| Kiểu đầu ra SQL thường gặp | Đăng ký đầu ra | Phương thức đọc thường dùng | Lưu ý |
|---|---|---|---|
| `INTEGER` / `INT` | `Types.INTEGER` | `getInt(index)` hoặc `getObject(...)` | `getInt` trả 0 khi SQL `NULL`; cần `wasNull()`. |
| `BIGINT` | `Types.BIGINT` | `getLong(index)` | Không ép giá trị ngoài phạm vi `int`. |
| `VARCHAR` | `Types.VARCHAR` | `getString(index)` | Có thể trả `null`. |
| `DECIMAL` / `NUMERIC` | `Types.DECIMAL` / `Types.NUMERIC` | `getBigDecimal(index)` | Phù hợp tiền/số thập phân; kiểm tra precision/scale. |
| `DATE` | `Types.DATE` | `getDate(index)` hoặc `getObject` với `LocalDate` khi được hỗ trợ | Kiểu Java thời gian hiện đại phụ thuộc driver/JDBC. |
| `TIMESTAMP` | `Types.TIMESTAMP` | `getTimestamp(index)` hoặc kiểu `java.time` phù hợp | Xác định rõ ngữ nghĩa múi giờ. |

Ở driver JDBC 4.2 trở lên, một số overload dùng `SQLType` hoặc `getObject(index, Class<T>)` có thể hữu ích, nhưng tính hỗ trợ không đồng nhất. Với portable code, bắt đầu từ `java.sql.Types` và getter được driver tài liệu hóa là cách dễ kiểm chứng.

### `OUT` và `INOUT` mang kiểu `NULL`

Không phải getter nào cũng trả đối tượng có thể là `null`. Với `getInt` và `getLong`, nếu giá trị SQL là `NULL`, JDBC trả giá trị mặc định của primitive, ví dụ `0`; cần gọi **`wasNull()` ngay sau getter** để phân biệt.

```java
call.execute();

int points = call.getInt(2);
boolean pointsIsNull = call.wasNull();

String message = call.getString(3);
boolean messageIsNull = call.wasNull();

if (pointsIsNull) {
    System.out.println("Procedure trả points = SQL NULL");
} else {
    System.out.println("Points = " + points);
}

if (messageIsNull) {
    System.out.println("Message = SQL NULL");
} else {
    System.out.println(message);
}
```

`wasNull()` phản ánh **giá trị được đọc gần nhất** bởi một getter; nếu gọi nhiều getter liên tiếp rồi kiểm tra một lần, ứng dụng có thể đang kiểm tra sai tham số. Với `String`, `getString` trả `null` khi SQL `NULL`, nhưng kiểm tra `wasNull()` vẫn cho thấy quy tắc chung.

Nếu đầu vào của `INOUT` phải mang `NULL`, ứng dụng có thể bind như sau:

```java
call.registerOutParameter(2, Types.INTEGER);
call.setNull(2, Types.INTEGER);  // Giá trị IN ban đầu là SQL NULL.
call.execute();
int result = call.getInt(2);
boolean resultIsNull = call.wasNull();
```

Ví dụ procedure `adjust_points` dùng `COALESCE(p_points, 0)`, nên nhận `NULL` rồi trả `10`. Với routine khác, `NULL` có thể giữ nguyên hoặc dẫn tới lỗi theo logic bên trong. **Đừng tự thay `NULL` thành 0 ở Java** nếu nghiệp vụ phân biệt “chưa có điểm” với “điểm bằng không”.

### Output kiểu thập phân và `scale`

Một số routine có tham số `INOUT` dạng `DECIMAL(12, 2)`. Khi cần khai báo số chữ số phần thập phân, JDBC có overload:

```java
call.registerOutParameter(2, Types.DECIMAL, 2);
call.setBigDecimal(2, new java.math.BigDecimal("145.75"));
call.execute();
java.math.BigDecimal adjusted = call.getBigDecimal(2);
```

`scale = 2` có nghĩa là hai chữ số sau dấu thập phân trong ngữ cảnh loại SQL numeric phù hợp. Cần đối chiếu precision, scale của routine và hành vi chuyển đổi thực tế của driver; không dùng `double` cho giá trị tiền nếu cần độ chính xác thập phân.

## 7. Procedure trả nhiều dạng kết quả: xử lý trước khi đọc INOUT

Một stored procedure có thể thực thi câu `SELECT` để phát ra **`ResultSet`**, đồng thời chạy `UPDATE` để tạo update count và gán tham số `OUT/INOUT`. Khi ấy:

- `CallableStatement.execute()` có thể trả `true` nếu kết quả đầu tiên là `ResultSet`.
- `CallableStatement.getResultSet()` cho phép đọc kết quả hiện tại khi kết quả đó là result set.
- `CallableStatement.getUpdateCount()` trả số dòng của kết quả cập nhật hiện tại hoặc `-1` khi không có update count hiện tại.
- `CallableStatement.getMoreResults()` chuyển sang kết quả tiếp theo.
- **Để tương thích tối đa, nên xử lý các result set và update count trước khi đọc output parameter**, theo quy tắc JDBC về thứ tự kết quả.

Mẫu tổng quát sau dành cho routine **có thể** trả nhiều kết quả. Hàm này chỉ minh họa xử lý result set; ứng dụng cần chọn tên cột và quy tắc đọc phù hợp với routine thực tế:

```java
import java.sql.CallableStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

// call đã được prepare, register và bind trước khi gọi:
boolean hasResultSet = call.execute();

while (true) {
    if (hasResultSet) {
        try (ResultSet rs = call.getResultSet()) {
            while (rs.next()) {
                // Đọc đúng các cột do routine công bố.
                // Ví dụ: System.out.println(rs.getObject(1));
            }
        }
    } else {
        int updateCount = call.getUpdateCount();
        if (updateCount == -1) {
            // Không còn ResultSet hoặc update count.
            break;
        }
        // Nếu cần, ghi nhận updateCount theo nghiệp vụ.
    }

    hasResultSet = call.getMoreResults();
}

// Sau khi xử lý các kết quả trung gian:
int finalPoints = call.getInt(2);
boolean pointsIsNull = call.wasNull();
String finalMessage = call.getString(3);
```

**Lưu ý:** Đoạn trên giả định routine có `INOUT` ở 2 và `OUT` ở 3 như `adjust_points`, nhưng routine đó **không phát ResultSet** trong DDL mẫu. Để kiểm chứng nhiều result set thực tế, cần tạo một procedure khác thực sự chứa `SELECT`. Không phải mọi DBMS/driver đều cho procedure phát đồng thời mọi loại kết quả theo cùng cách.

Đừng xử lý `execute() == false` như một lỗi: `false` chỉ có nghĩa kết quả đầu tiên **không phải** `ResultSet`, có thể là update count hoặc không có kết quả dạng đó. Tương tự, đừng nhầm `getUpdateCount()` với một tham số `OUT` có tên “affected_rows”.

## 8. Giá trị trả về từ procedure khác function return như thế nào?

Một số DBMS có cơ chế procedure trả **mã trạng thái** riêng của nhà cung cấp. Ví dụ SQL Server hỗ trợ số nguyên `RETURN` trong stored procedure; cách gọi và đăng ký giá trị đó là quy ước của SQL Server và JDBC driver tương ứng. Trong khi đó, nhiều DBMS chỉ dùng `OUT` để trả thông tin từ procedure.

Bảng khái quát:

| Cơ chế | Khái niệm | Truy xuất từ Java |
|---|---|---|
| Procedure `OUT` | Một tham số chỉ trả dữ liệu | `registerOutParameter(index, sqlType)`, rồi `getXxx(index)` |
| Procedure `INOUT` | Tham số vừa nhận input vừa trả output | `registerOutParameter` và `setXxx` **cùng index**, rồi `getXxx` |
| Stored function `RETURN` | Giá trị kết quả của hàm | Thường `{? = call function(?)}`, đăng ký vị trí 1 nếu driver hỗ trợ; hoặc `SELECT function(?)` theo DBMS |
| Procedure return status riêng | Cơ chế do DBMS quy định, không phổ quát cho mọi procedure | Tra tài liệu JDBC driver, không suy từ `INOUT` |
| Result set từ `SELECT` trong routine | Tập hàng, có metadata và cursor | `execute()`, `getResultSet()`, `ResultSet.next()` |
| Update count từ routine | Số hàng được thao tác SQL tác động theo driver | `getUpdateCount()` hoặc cơ chế update count tương ứng |

Nếu nghiệp vụ cần **mã lỗi có thể đọc được ở mọi hệ quản trị**, có thể thiết kế routine dùng một tham số `OUT p_status_code INTEGER` với hợp đồng rõ ràng. Không nên mặc định procedure ở mọi DBMS đều có return code hay có cùng ý nghĩa của `RETURN`.

## 9. Kiểm soát giao dịch khi routine thay đổi dữ liệu

`CallableStatement` vẫn chạy trên một `Connection` JDBC. Nếu routine sửa dữ liệu bằng `INSERT`/`UPDATE`/`DELETE`, những thay đổi đó cần được đánh giá theo **transaction của kết nối**, cú pháp routine và quy tắc DBMS.

Ví dụ giả định có một procedure `update_customer_points(?, ?, ?)` được ứng dụng/DBA định nghĩa để **vừa sửa bảng điểm**, vừa trả `INOUT` và `OUT`. Trường hợp này có tác động dữ liệu, khác với procedure `adjust_points` ở phần 3.

```java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Types;

// dataSource đã được ứng dụng cấu hình.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        int updatedPoints;
        String message;

        try (CallableStatement call = connection.prepareCall(
                "{call update_customer_points(?, ?, ?)}")) {

            call.registerOutParameter(2, Types.INTEGER);
            call.registerOutParameter(3, Types.VARCHAR);

            call.setLong(1, 42L);
            call.setInt(2, 80);

            call.execute();

            // Nếu routine trả ResultSet/update count, xử lý theo mục 7.
            updatedPoints = call.getInt(2);
            if (call.wasNull()) {
                throw new SQLException("Procedure không trả điểm mới");
            }

            message = call.getString(3);
            if (message == null) {
                throw new SQLException("Procedure không trả thông báo");
            }

            // Kiểm tra điều kiện nghiệp vụ trước khi commit.
            if (updatedPoints < 0) {
                throw new SQLException("Số điểm không hợp lệ");
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
```

Ví dụ trên **không cung cấp DDL** của `update_customer_points`; nó thể hiện cách gọi một routine có hợp đồng đã được triển khai và được phép sửa dữ liệu. Khi dùng trên DBMS thực tế, phải xác nhận routine không tự kết thúc transaction ngoài ý muốn và có hỗ trợ tham gia transaction của `Connection` như kỳ vọng.

**Những điều cần lưu ý:**

- Mặc định auto-commit có thể bật trên kết nối mới theo JDBC. Muốn kết hợp lời gọi routine với các câu SQL khác trong một đơn vị atomic, cần tắt auto-commit từ trước thao tác ghi đầu tiên, nếu DBMS/driver hỗ trợ.
- Việc routine có tham số `INOUT` **không đồng nghĩa** routine có thay đổi bảng. Routine có thể chỉ tính toán và trả biến, như ví dụ `adjust_points`.
- Nếu routine tự chạy DDL, commit, rollback hoặc có quy tắc transaction đặc biệt, phạm vi mà ứng dụng có thể rollback phụ thuộc DBMS. Không nên suy rằng `Connection.rollback()` luôn hoàn tác được mọi thứ do routine làm.
- `execute()` thành công nghĩa là lời gọi ở cấp JDBC hoàn tất bình thường; thông báo `OUT p_status` có thể cho biết **nghiệp vụ từ chối**. Ứng dụng cần kiểm tra mã trạng thái nghiệp vụ trước khi commit.
- Nếu `commit()` ném `SQLException` do mất kết nối, kết quả commit đôi khi **không xác định**. Dùng khóa yêu cầu duy nhất, idempotency và đối soát nếu nghiệp vụ cần retry; không tự động giả định chưa có thay đổi nào được xác nhận.

## 10. Lỗi thường gặp khi xử lý INOUT và RETURN

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ gọi `setInt(2, 80)` cho tham số `INOUT` | JDBC không được khai báo cách đọc output; getter có thể lỗi hoặc không có kết quả. | Đăng ký `registerOutParameter(2, Types.INTEGER)` trước `execute()`. |
| Chỉ gọi `registerOutParameter(2, ...)` mà không bind input `INOUT` | Routine không nhận giá trị đầu vào bắt buộc hoặc driver báo thiếu tham số. | Gán input bằng `setXxx(2, value)` hoặc `setNull(2, sqlType)`. |
| Dùng index 1 cho return của function nhưng vẫn bind input ở index 1 | Đặt sai vị trí, giá trị hoặc kiểu tham số không khớp. | Với `{? = call f(?)}`, output ở 1, input bắt đầu ở 2. |
| Xem `execute() == false` là “routine chạy lỗi” | Một lời gọi không trả `ResultSet` có thể chạy hoàn toàn thành công. | Kiểm tra exception và output/status nghiệp vụ thay vì boolean. |
| Gọi `getInt` rồi dùng 0 như giá trị chắc chắn | SQL `NULL` bị biểu diễn bằng 0. | Gọi `wasNull()` ngay sau getter. |
| Nhầm output parameter với `ResultSet` | Bỏ sót tập hàng hoặc đọc OUT sai trình tự ở driver nhạy thứ tự. | Dùng `getResultSet()/getMoreResults()` khi routine có kết quả trung gian. |
| Đăng ký `Types.VARCHAR` cho output thực sự là `DECIMAL` | Driver có thể chuyển kiểu khó lường hoặc ném lỗi. | Đối chiếu kiểu SQL được định nghĩa, dùng `Types` phù hợp. |
| Ghép chuỗi đầu vào người dùng vào câu `CALL` | Dễ lỗi SQL injection hoặc cú pháp. | Chỉ bind **giá trị** bằng placeholder `?` và `setXxx`. |
| Xem procedure trả status tốt là transaction đã commit | OUT status và trạng thái transaction là hai cơ chế riêng. | Với transaction thủ công, vẫn phải `commit()` sau kiểm tra. |
| Retry ngay khi xảy ra lỗi commit do mất kết nối | Có nguy cơ thực hiện nghiệp vụ hai lần. | Thiết kế idempotency, mã yêu cầu duy nhất, đối soát. |
| Giữ một `CallableStatement` chung cho nhiều thread | Giá trị bind và output của các lời gọi có thể xung đột; JDBC statement thường không được thiết kế để chia sẻ đồng thời. | Mỗi luồng nghiệp vụ dùng statement và kết nối thích hợp theo quy tắc pool/driver. |

### Lỗi ở DBMS và lỗi ở nghiệp vụ

Nên phân biệt:

1. **Lỗi kỹ thuật:** `SQLException` do thiếu routine, sai signature, không có quyền gọi, kiểu tham số không khớp, kết nối hỏng hoặc constraint vi phạm.
2. **Lỗi nghiệp vụ:** procedure thực thi thành công về kỹ thuật nhưng trả `OUT p_status_code = 2` với ý nghĩa “không đủ điểm” theo hợp đồng đã định nghĩa.
3. **Lỗi trạng thái transaction:** routine hoặc SQL đã chạy nhưng `commit()` không thành công hoặc phản hồi bị mất; không tự suy ra đã rollback.

Với `SQLException`, có thể khai thác `getSQLState()`, `getErrorCode()` và chuỗi ngoại lệ liên quan để tìm nguyên nhân. Mã lỗi cụ thể phụ thuộc driver/DBMS. Không nên bắt mọi `SQLException` rồi trả một status “thất bại” chung mà quên rollback khi đang quản lý transaction.

## 11. Quy tắc an toàn với routine và placeholder

`CallableStatement` vẫn có lợi ích của SQL tham số hóa đối với **giá trị**:

```java
String sql = "{call adjust_points(?, ?, ?)}";

try (CallableStatement call = connection.prepareCall(sql)) {
    call.registerOutParameter(2, Types.INTEGER);
    call.registerOutParameter(3, Types.VARCHAR);
    call.setLong(1, customerId); // Không ghép customerId vào chuỗi SQL.
    call.setInt(2, currentPoints);
    call.execute();
}
```

Tuy nhiên, placeholder `?` **không đại diện cho tên procedure hoặc tên schema**. Nếu ứng dụng cho người dùng chọn routine động, phải dùng **allowlist** tên routine được phép gọi, không nối trực tiếp tên tự do từ request vào SQL.

Stored routine chạy dưới các quy tắc quyền của DBMS. Ngoài quyền `EXECUTE`, cần đánh giá quyền truy cập dữ liệu bên trong routine, cơ chế definer/invoker và bảo vệ dữ liệu trả về theo DBMS. Bản thân việc SQL nằm trong stored procedure không đồng nghĩa mọi input bên trong procedure đều được xử lý an toàn; routine tự ghép dynamic SQL cũng có thể có lỗ hổng.

## 12. Tương thích giữa các hệ CSDL

JDBC cố gắng chuẩn hóa API phía Java, nhưng **định nghĩa, lời gọi và kết quả stored routine** khác nhau giữa hệ quản trị.

| Hệ quản trị | Điều cần kiểm tra trước khi triển khai |
|---|---|
| **MySQL** | Cú pháp `CREATE PROCEDURE` với `IN/OUT/INOUT`, `CREATE FUNCTION`, metadata quyền gọi routine, cách driver xử lý OUT và function return. |
| **PostgreSQL** | Khác biệt giữa `CALL` procedure và `SELECT` function; ánh xạ các tham số output/INOUT tùy phiên bản PostgreSQL JDBC, chế độ escape call và routine signature. |
| **SQL Server** | Procedure có thể có `OUTPUT` parameter và return status; driver cần được gọi theo cú pháp phù hợp, nhiều update count/result set có thể cùng xuất hiện. |
| **Oracle Database** | Procedure/function trong schema hoặc package, tham số `OUT/IN OUT`, `REF CURSOR` và các loại dữ liệu riêng; driver có thể yêu cầu mapping đặc biệt. |
| **Các driver khác** | Hỗ trợ `CallableStatement`, output parameter theo tên hay chỉ số, kiểu SQL, nhiều result set và routine metadata có thể khác. |

Một số driver hỗ trợ `registerOutParameter("p_points", Types.INTEGER)` và `getInt("p_points")`, nhưng khả năng truy cập bằng **tên** không đồng đều. Dùng **chỉ số vị trí** dựa trên hợp đồng routine thường dễ kiểm chứng hơn khi cần chạy trên nhiều driver.

Nếu không chắc thông tin về signature, có thể tham khảo tài liệu DBMS, đọc định nghĩa routine do DBA cung cấp, hoặc sử dụng `DatabaseMetaData.getProcedureColumns(...)` / `getFunctionColumns(...)` nếu driver hỗ trợ. Metadata không phải lúc nào cũng đầy đủ hoặc chính xác, nhất là với tên được overload, package, quyền truy cập hoặc kiểu riêng.

**Không giả định** chuỗi `{call ...}` sẽ làm việc giống hệt ở tất cả DBMS. Đây là cú pháp escape của JDBC; driver chịu trách nhiệm diễn dịch lời gọi và một số hệ có tùy chọn cấu hình ảnh hưởng cách diễn dịch procedure/function.

## 13. Thực hành từng bước

Nên làm trên cơ sở dữ liệu kiểm thử, với routine đơn giản có hợp đồng rõ ràng. Các thao tác tạo procedure cần được thực hiện bằng tài khoản được cấp quyền phù hợp.

### Bài 1 — Đọc INOUT sau khi đã bind đầu vào

Tạo `adjust_points` theo ví dụ MySQL ở phần 3, gọi với `customerId = 42` và `points = 80`. Kỳ vọng tham số `INOUT` trả `90` và tham số `OUT` trả thông báo.

Thử thay `setInt(2, 80)` bằng `setInt(2, 95)`; nếu routine cộng 10, kết quả `INOUT` tương ứng phải là `105`. Sau đó cố tình bỏ `registerOutParameter(2, ...)` và ghi nhận lỗi/hành vi của driver, rồi khôi phục mã đúng.

### Bài 2 — Trả về của function

Tạo `points_tier`, gọi bằng `{? = call points_tier(?)}`. Thử `p_points = 99` và `p_points = 100`; kỳ vọng `STANDARD` và `GOLD`.

Nhìn lại hai vị trí placeholder: vì sao phải `registerOutParameter(1, Types.VARCHAR)` và `setInt(2, points)`? Nếu driver không hỗ trợ escape function, kiểm tra cách `SELECT points_tier(?)` theo tài liệu của DBMS; so sánh cách đọc kết quả qua `ResultSet`.

### Bài 3 — Phân biệt `NULL` với 0

Gọi procedure với `INOUT p_points = NULL` bằng `setNull(2, Types.INTEGER)`. Procedure mẫu dùng `COALESCE` nên kỳ vọng trả `10`. Sau đó thay routine thử nghiệm bằng routine chủ động trả `NULL`, đọc bằng `getInt` và `wasNull` để thấy vì sao chỉ kiểm tra `points == 0` là chưa đủ.

### Bài 4 — Một procedure có nhiều kết quả

Tạo procedure thử nghiệm phát một `SELECT`, cập nhật một bản ghi trong bảng kiểm thử và gán tham số `OUT`. Chạy `execute()`, lặp `getResultSet()`, `getUpdateCount()`, `getMoreResults()` như phần 7, sau đó mới đọc `OUT`. Ghi nhận thứ tự result set/update count và các khác biệt khi đổi driver.

### Bài 5 — Transaction và lỗi

Tạo một procedure viết vào bảng kiểm thử rồi trả status. Gọi qua kết nối đã `setAutoCommit(false)`; thử rollback thay vì commit và kiểm tra xem bảng có trở về trạng thái cũ trên DBMS đang dùng không. Thử trường hợp procedure trả status từ chối nghiệp vụ nhưng không ném `SQLException`, kiểm chứng logic ứng dụng **không** commit nhầm.

### Bài 6 — Kiểm chứng signature và driver

Dựa trên metadata, tài liệu hoặc định nghĩa routine, lập bảng gồm tên, vị trí, chiều, SQL type và cách bind/đọc. Cố tình dùng sai `Types` hoặc sai index trên môi trường thử nghiệm để nhận diện lỗi. Không suy đoán loại `INOUT` chỉ từ tên biến hay giá trị muốn nhận về.

## 14. Câu hỏi tự kiểm tra

**1. Với `INOUT` ở vị trí 2, tại sao cần cả `setInt(2, ...)` lẫn `registerOutParameter(2, Types.INTEGER)`?**

Vì đó là **một tham số hai chiều**: routine phải có giá trị đầu vào để xử lý và JDBC cần biết kiểu đầu ra để ứng dụng đọc kết quả sau khi thực thi.

**2. Vì sao không thể dựa vào `execute() == true` để khẳng định procedure đã thành công?**

`execute()` trả `true` khi kết quả đầu tiên là `ResultSet`, không phản ánh tình trạng nghiệp vụ. Lời gọi trả `false` vẫn có thể đã chạy thành công. Kiểm tra ngoại lệ, output status và transaction theo hợp đồng routine.

**3. Trong `{? = call points_tier(?)}`, đâu là vị trí của giá trị RETURN?**

Vị trí **1**. Tham số `IN` của function là vị trí **2**.

**4. Nếu `getInt(2)` trả 0, có chắc stored procedure trả số 0 không?**

Không. Giá trị SQL `NULL` cũng được getter primitive biểu diễn bằng 0. Phải gọi `wasNull()` ngay sau `getInt(2)`.

**5. OUT parameter và `ResultSet` khác gì nhau?**

`OUT` là giá trị của một tham số đã đăng ký; `ResultSet` là tập hàng do một kết quả truy vấn của routine tạo ra. Chúng có API và vòng đời riêng.

**6. Nếu procedure có cập nhật bảng và trả status “OK”, có cần gọi `commit()` không?**

Nếu ứng dụng tắt auto-commit và DBMS cho phép routine tham gia transaction của kết nối, vẫn phải commit sau khi kiểm tra mọi điều kiện. Status của routine không thay `Connection.commit()`.

**7. Nếu `commit()` lỗi do mất mạng, có thể lập tức gọi lại routine cộng điểm không?**

Không nên tự động gọi lại khi chưa biết giao dịch đã được xác nhận hay chưa. Cần cơ chế idempotency/đối soát để tránh cộng điểm hai lần.

## 15. Checklist áp dụng trong DAO/repository

Trước khi đưa lời gọi routine vào lớp truy cập dữ liệu, hãy xác nhận:

- **Hợp đồng routine:** đã biết chính xác nó là procedure hay function, các tham số `IN/OUT/INOUT`, thứ tự, SQL type và điều kiện `NULL`?
- **Đầu vào hai chiều:** mọi `INOUT` đều được **bind input** và **register output** trên đúng một index trước `execute()`?
- **Function return:** giá trị `RETURN` được đăng ký ở đúng vị trí (thường `1` trong escape function syntax) và gọi theo cách driver hỗ trợ?
- **Kết quả phụ:** nếu routine phát `ResultSet` hoặc update count, có xử lý chúng trước khi lấy output để tăng tính tương thích?
- **Kiểu dữ liệu:** dùng `Types`, `setXxx`, `getXxx` phù hợp; primitive output đã được kiểm tra `wasNull()` khi cần?
- **An toàn:** dữ liệu bind bằng `?`; tên routine động nếu có phải được allowlist; quyền gọi routine và dynamic SQL bên trong đã được kiểm tra?
- **Giao dịch:** routine có thay đổi dữ liệu không, có commit ngầm không, trạng thái nghiệp vụ ra sao, và `Connection.commit()/rollback()` do tầng nào chịu trách nhiệm?
- **Tương thích:** đã kiểm tra với DBMS, JDBC driver và phiên bản triển khai thật, không chỉ dựa vào chữ ký routine từ một hệ khác?

**Ghi nhớ:** `INOUT` vừa nhận giá trị ban đầu vừa trả giá trị mới **trên cùng một vị trí tham số**. Với JDBC, hãy `registerOutParameter(index, sqlType)`, `setXxx(index, input)`, thực thi qua `CallableStatement` rồi `getXxx(index)` và kiểm tra `NULL`. Giá trị `RETURN` của function là kết quả riêng và thường được đọc qua vị trí trả về trong cú pháp `{? = call ...}`; `ResultSet`, update count và `execute()` có ngữ nghĩa khác. Tất cả vẫn phải tuân thủ kiểu SQL, hợp đồng của routine, khả năng của driver và ranh giới transaction của `Connection`.

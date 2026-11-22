# Vai trò của `CallableStatement` trong JDBC

Khi xây dựng ứng dụng Java truy cập cơ sở dữ liệu quan hệ bằng **JDBC (Java Database Connectivity)**, không phải mọi tác vụ đều được thực hiện bằng câu lệnh `SELECT`, `INSERT`, `UPDATE` hay `DELETE` viết trực tiếp trong ứng dụng. Một số hệ thống đóng gói logic xử lý dữ liệu ở phía cơ sở dữ liệu dưới dạng **stored procedure** (thủ tục lưu trữ) hoặc **stored function** (hàm lưu trữ). JDBC cung cấp giao diện **`java.sql.CallableStatement`** để gọi các routine này và trao đổi dữ liệu với chúng.

Vai trò cốt lõi của `CallableStatement` là **tạo lời gọi có tham số đến routine trong cơ sở dữ liệu, truyền tham số đầu vào, đăng ký và đọc tham số đầu ra, đồng thời xử lý các kết quả do routine trả về**. Nó giúp Java tương tác với logic đã được định nghĩa trong database thông qua một API JDBC thống nhất, dù cú pháp SQL và khả năng hỗ trợ chi tiết vẫn phụ thuộc hệ quản trị và driver.

## 1. `CallableStatement` đứng ở đâu trong JDBC?

Ba giao diện dùng để thực thi SQL có các mục đích khác nhau:

| Giao diện | Mục đích chính | Cách tạo thông thường | Đặc điểm nổi bật |
| --- | --- | --- | --- |
| `Statement` | Thực thi SQL trực tiếp | `connection.createStatement()` | Phù hợp với SQL tĩnh, không cần placeholder |
| `PreparedStatement` | Thực thi SQL có các tham số đầu vào | `connection.prepareStatement(sql)` | Dùng `?` và `setXxx()` để truyền giá trị |
| `CallableStatement` | Gọi stored procedure hoặc function | `connection.prepareCall(callSql)` | Có `setXxx()`, `registerOutParameter()` và `getXxx()` để giao tiếp hai chiều |

Trong hệ thống kiểu JDBC, `CallableStatement` **kế thừa `PreparedStatement`**, còn `PreparedStatement` kế thừa `Statement`. Do đó, `CallableStatement` có thể sử dụng nhiều thao tác quen thuộc như `setInt()`, `setString()`, `execute()`, `getResultSet()` và `getMoreResults()`. Phần riêng quan trọng nhất của nó là cơ chế **tham số OUT/INOUT**.

Một luồng gọi điển hình:

```text
Ứng dụng Java
    |
    | Connection.prepareCall("{call ten_thu_tuc(?, ?)}")
    v
CallableStatement
    | 1. setXxx(...)                 -> truyền tham số IN
    | 2. registerOutParameter(...)  -> khai báo tham số OUT
    | 3. execute()                  -> yêu cầu DB thực hiện
    v
Cơ sở dữ liệu: stored procedure / function
    |
    | 4. OUT/INOUT, ResultSet, update count, hoặc lỗi SQL
    v
CallableStatement -> ứng dụng Java xử lý kết quả
```

**Không nên nhầm:** `CallableStatement` không tự tạo thủ tục hay chạy logic Java ở phía database. Routine phải tồn tại trong hệ quản trị (hoặc được tạo trước bằng DDL); JDBC chỉ cung cấp API để **gọi** và nhận kết quả.

## 2. Ba chế độ tham số: IN, OUT và INOUT

Tham số trong routine có thể mang dữ liệu theo các hướng sau:

| Chế độ | Ý nghĩa | Việc cần làm từ Java |
| --- | --- | --- |
| **IN** | Ứng dụng gửi dữ liệu vào routine | Gọi `setXxx(index, value)` trước `execute()` |
| **OUT** | Routine trả dữ liệu ra ngoài | Gọi `registerOutParameter(index, sqlType)` trước `execute()`, sau đó `getXxx(index)` |
| **INOUT** | Ứng dụng truyền giá trị ban đầu; routine có thể thay đổi rồi trả lại | Kết hợp `setXxx()` và `registerOutParameter()` trên **cùng vị trí**, đọc lại sau `execute()` |

Vị trí tham số JDBC bắt đầu từ **1**, không phải 0. `sqlType` trong `registerOutParameter` thường là hằng số của `java.sql.Types`, chẳng hạn `Types.INTEGER`, `Types.BIGINT`, `Types.VARCHAR` hay `Types.DECIMAL`. Cần chọn loại tương ứng với kiểu tham số được định nghĩa trong database.

Ví dụ phác họa một thủ tục nhận một giá trị và trả lại giá trị đã điều chỉnh qua tham số `INOUT`:

```java
try (CallableStatement call =
         connection.prepareCall("{call adjust_threshold(?)}")) {

    call.setInt(1, 50);                          // Gia tri IN ban dau
    call.registerOutParameter(1, Types.INTEGER); // Cung vi tri la OUT

    call.execute();
    int updatedThreshold = call.getInt(1);
}
```

Đoạn này minh họa cơ chế JDBC: để chạy được, cơ sở dữ liệu phải có routine `adjust_threshold` đúng chữ ký và hỗ trợ tham số `INOUT`.

## 3. Ví dụ hoàn chỉnh: gọi stored procedure có IN và OUT

Giả sử hệ thống đặt hàng có bảng `orders` với cột `customer_id`, và cần biết tổng số đơn của một khách hàng. Ví dụ sau dùng **MySQL 8.x** để minh họa định nghĩa thủ tục; cú pháp tạo thủ tục của PostgreSQL, SQL Server, Oracle và các hệ khác sẽ khác.

### Bước 1. Định nghĩa routine trong database

```sql
CREATE PROCEDURE count_customer_orders(
    IN p_customer_id BIGINT,
    OUT p_order_count BIGINT
)
BEGIN
    SELECT COUNT(*)
      INTO p_order_count
      FROM orders
     WHERE customer_id = p_customer_id;
END;
```

Trong MySQL command-line client, có thể cần đổi `DELIMITER` khi nhập phần thân chứa dấu `;`; `DELIMITER` là lệnh của client, **không phải** SQL để gửi qua JDBC. Ví dụ giả định bảng `orders` đã tồn tại, cột `customer_id` tương thích `BIGINT` và tài khoản kết nối được cấp quyền cần thiết.

### Bước 2. Gọi bằng Java JDBC

```java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Types;

public final class OrderStatistics {
    private OrderStatistics() {}

    public static long countOrdersForCustomer(
            Connection connection, long customerId) throws SQLException {

        if (customerId <= 0) {
            throw new IllegalArgumentException("customerId phai duong");
        }

        String callSql = "{call count_customer_orders(?, ?)}";

        try (CallableStatement call = connection.prepareCall(callSql)) {
            call.setLong(1, customerId);                 // p_customer_id: IN
            call.registerOutParameter(2, Types.BIGINT); // p_order_count: OUT

            call.execute();

            long total = call.getLong(2);               // Doc tham so OUT
            if (call.wasNull()) {
                throw new SQLException("Routine tra ve OUT NULL");
            }
            return total;
        }
    }
}
```

Điểm cần nhớ:

1. `connection.prepareCall(...)` tạo `CallableStatement`. Cú pháp `{call ...}` là **JDBC escape syntax** cho lời gọi procedure, được driver chuyển đổi hoặc xử lý tùy cách triển khai.
2. `setLong(1, customerId)` gán tham số ở vị trí 1; routine nhận ID khách hàng làm đầu vào.
3. `registerOutParameter(2, Types.BIGINT)` thông báo vị trí 2 là tham số đầu ra tương ứng `BIGINT`. **Phải đăng ký trước khi gọi `execute()`.**
4. `execute()` gửi yêu cầu tới cơ sở dữ liệu. Chỉ sau khi thực thi xong mới đọc giá trị OUT bằng `getLong(2)`.
5. `getLong()` trả về 0 nếu giá trị SQL thực tế là `NULL`, vì vậy `wasNull()` giúp phân biệt. Trong routine sử dụng `COUNT(*)`, kết quả thông thường là số không âm và không `NULL`; kiểm tra vẫn cho thấy cách xử lý API đúng.
6. `try-with-resources` tự đóng `CallableStatement`. `Connection` được truyền từ bên ngoài nên phương thức để bên gọi quản lý vòng đời của connection.

**Ví dụ kết quả:** Nếu khách hàng ID 42 có 7 đơn hàng thì `countOrdersForCustomer(connection, 42)` trả về `7L`. Nếu không có đơn nào, kết quả là `0L`; không có hàng khớp trong truy vấn `COUNT(*)` vẫn trả về một hàng kết quả với giá trị 0.

## 4. Gọi stored function có giá trị trả về

Stored procedure và stored function không hoàn toàn giống nhau: **function có giá trị trả về**, còn procedure thường được gọi để thực hiện một thao tác và có thể trả dữ liệu qua OUT/INOUT hoặc result set. Cú pháp, giới hạn và khả năng trả result set phụ thuộc từng hệ quản trị.

Một dạng JDBC escape syntax thường dùng cho hàm là:

```text
{? = call ten_ham(?, ?)}
```

Dấu `?` đầu tiên biểu diễn **giá trị trả về của hàm**. Khi đó vị trí 1 được đăng ký là tham số OUT; các tham số đầu vào theo sau:

```java
import java.math.BigDecimal;
import java.sql.CallableStatement;
import java.sql.Types;

// Gia su database co function compute_fee(customerId) tra DECIMAL.
try (CallableStatement call =
         connection.prepareCall("{? = call compute_fee(?)}")) {

    call.registerOutParameter(1, Types.DECIMAL); // Gia tri return
    call.setLong(2, 42L);                         // Tham so IN dau tien

    call.execute();
    BigDecimal fee = call.getBigDecimal(1);
    // fee == null neu ket qua SQL la NULL.
}
```

**Sự khác biệt về vị trí rất quan trọng:** Với procedure `{call count_customer_orders(?, ?)}`, tham số thứ nhất là đầu vào của procedure; với function `{? = call compute_fee(?)}`, vị trí 1 là giá trị trả về, còn đầu vào thực tế đầu tiên nằm ở vị trí 2. Một số driver hoặc hệ CSDL có hạn chế riêng với function call syntax; khi đó có thể cần cú pháp SQL bản địa hoặc truy vấn `SELECT` nếu routine hỗ trợ.

## 5. Routine có thể trả `ResultSet` hoặc số hàng bị ảnh hưởng

Không phải routine nào cũng trả kết quả qua tham số `OUT`. Nhiều procedure thực hiện `SELECT` bên trong và trả về một hoặc nhiều **`ResultSet`**; một số còn tạo **update count** khi cập nhật dữ liệu.

Vì không thể luôn biết trước dạng kết quả, `execute()` thường là lựa chọn linh hoạt:

- `execute()` trả về `true` nếu **kết quả đầu tiên** là `ResultSet`; trả về `false` nếu kết quả đầu tiên là update count hoặc không có kết quả.
- `getResultSet()` lấy `ResultSet` hiện tại nếu có.
- `getUpdateCount()` lấy số hàng bị ảnh hưởng của kết quả hiện tại, hoặc `-1` nếu hiện tại không phải update count.
- `getMoreResults()` chuyển sang kết quả kế tiếp. Khi không còn result set hoặc update count, chuỗi kết quả đã hết.

Ví dụ duyệt cả result set và update count khi một routine có thể tạo **nhiều kết quả**:

```java
import java.sql.CallableStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void inspectResults(
        java.sql.Connection connection, long customerId) throws SQLException {

    // Routine minh hoa phai duoc tao san trong database.
    try (CallableStatement call =
             connection.prepareCall("{call inspect_customer(?)}")) {

        call.setLong(1, customerId);
        boolean hasResultSet = call.execute();

        while (true) {
            if (hasResultSet) {
                try (ResultSet rs = call.getResultSet()) {
                    while (rs.next()) {
                        // Doc cot theo schema ResultSet do routine tra ve.
                        System.out.println(rs.getObject(1));
                    }
                }
            } else {
                int affectedRows = call.getUpdateCount();
                if (affectedRows == -1) {
                    break; // Khong con ResultSet hay update count.
                }
                System.out.println("Update count: " + affectedRows);
            }
            hasResultSet = call.getMoreResults();
        }
    }
}
```

Vòng lặp trên minh họa **cách tiêu thụ chuỗi kết quả JDBC**, không xác định ý nghĩa cột hay số kết quả của routine giả định. Các hệ quản trị/driver khác nhau về việc routine có trả update count trung gian hay không. Một số driver yêu cầu **đọc hoặc đóng hết result set trước khi lấy tham số OUT**; nên thực hiện việc này nếu routine kết hợp nhiều loại đầu ra.

Chỉ dùng `executeQuery()` khi chắc chắn lời gọi trả đúng dạng result set mà driver hỗ trợ, và `executeUpdate()` khi chắc chắn xử lý được theo ngữ nghĩa cập nhật. `execute()` ít giả định hơn cho routine có kết quả hỗn hợp.

## 6. Vòng đời, giao dịch và xử lý lỗi

### Quản lý tài nguyên

`CallableStatement` gắn với một `Connection` đang mở. Dùng `try-with-resources` để đóng statement và các `ResultSet` phát sinh. Khi làm việc với connection pool, phải trả connection theo cơ chế của pool; việc đóng statement **không** đồng nghĩa đóng connection.

### Transaction không tự động được quyết định bởi `CallableStatement`

Lệnh gọi procedure tham gia vào bối cảnh giao dịch của connection, nhưng **quy tắc transaction còn phụ thuộc database và nội dung routine**. Nếu ứng dụng cần kết hợp lời gọi với các cập nhật khác thành một giao dịch, có thể tắt autocommit và chủ động commit/rollback:

```java
// connection do ung dung quan ly; minh hoa khong tu dong dong no.
boolean oldAutoCommit = connection.getAutoCommit();
try {
    connection.setAutoCommit(false);
    try (CallableStatement call =
             connection.prepareCall("{call reserve_stock(?, ?)}")) {
        call.setLong(1, 101L);
        call.setInt(2, 3);
        call.execute();
    }
    connection.commit();
} catch (SQLException error) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        error.addSuppressed(rollbackError);
    }
    throw error;
} finally {
    connection.setAutoCommit(oldAutoCommit);
}
```

Ví dụ giả định routine `reserve_stock` tồn tại và không tự thay đổi ranh giới giao dịch. **Không mặc định mọi thủ tục đều rollback được hoàn toàn**: một số hệ quản trị cho phép transaction control trong procedure, hoặc có câu lệnh DDL gây implicit commit. Cần xác minh chính sách của database trước khi dựa vào tính nguyên tử của lời gọi.

### Các loại lỗi cần dự liệu

Lời gọi có thể ném `SQLException` do sai tên hoặc chữ ký routine, thiếu quyền `EXECUTE`, sai kiểu tham số, lỗi ràng buộc dữ liệu, timeout, deadlock hay lỗi do routine chủ động phát sinh. Để chẩn đoán có thể đọc `getSQLState()` và `getErrorCode()` từ `SQLException`, đồng thời kiểm tra log database.

Không đưa nguyên thông báo SQL chứa thông tin nhạy cảm trực tiếp ra giao diện người dùng. Nếu routine xử lý lâu, cân nhắc cấu hình `setQueryTimeout(seconds)` trên statement; mức độ hỗ trợ và cách hủy thực thi tùy driver.

## 7. Tính di động, hiệu năng và bảo mật

**Tính di động:** API `CallableStatement` thuộc JDBC nhưng cú pháp `CREATE PROCEDURE`, kiểu tham số, cách trả nhiều result set và cách gọi function có thể khác nhau giữa MySQL, PostgreSQL, SQL Server, Oracle và các hệ khác. Cú pháp `{call ...}` là dạng chuẩn JDBC escape, song vẫn phải thử nghiệm với phiên bản driver thực tế. `DatabaseMetaData.supportsStoredProcedures()` có thể giúp kiểm tra khả năng hỗ trợ tổng quát; đó không phải bảo đảm mọi tính năng của một routine đều dùng được.

**Hiệu năng:** Routine có thể giảm trao đổi giữa ứng dụng và database khi gói nhiều thao tác liên quan trong một lần gọi, nhưng không đồng nghĩa luôn chạy nhanh hơn SQL qua `PreparedStatement`. Chi phí xử lý tại server, thiết kế truy vấn, chỉ mục, khóa, transaction và kế hoạch thực thi vẫn quyết định hiệu năng. Hãy đo đạc với dữ liệu và tải thực tế.

**Bảo mật:** Luôn truyền dữ liệu vào tham số `?` bằng `setXxx()` thay vì ghép chuỗi để tạo câu gọi SQL. Tài khoản ứng dụng nên chỉ có các quyền cần thiết, trong đó có `EXECUTE` đối với routine cần gọi. Tuy nhiên, tham số hóa lời gọi JDBC **không tự ngăn SQL injection nếu chính thủ tục tạo dynamic SQL bằng cách nối chuỗi đầu vào không an toàn**.

**Thiết kế:** Logic nghiệp vụ được đặt trong database có thể tái sử dụng giữa nhiều ứng dụng, nhưng cần quản lý phiên bản routine, thay đổi chữ ký và việc triển khai schema cùng với mã Java. Nên lựa chọn procedure khi logic cần thực thi gần dữ liệu hoặc do schema/API database quy định; không bắt buộc chuyển mọi truy vấn SQL sang procedure.

## 8. Lỗi thường gặp khi dùng `CallableStatement`

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `SQLException` khi gọi routine | Sai tên, sai schema, thiếu quyền hoặc driver không hỗ trợ cú pháp call | Đối chiếu chữ ký và quyền của routine với driver đang dùng |
| Không lấy được tham số OUT | Chưa đăng ký OUT trước `execute()`, hoặc sai vị trí/kiểu | Dùng `registerOutParameter()` đúng chỉ số và `Types` |
| Giá trị OUT/return không đúng | Nhầm chỉ số: function có ô return đứng đầu | Kiểm tra vị trí theo `{? = call ...}` và thứ tự tham số thực |
| Nhận 0 dù database trả `NULL` | Getter nguyên thủy `getInt`/`getLong` biến `NULL` thành 0 | Gọi `wasNull()` ngay sau getter |
| Lỗi khi procedure có nhiều kết quả | Chỉ xử lý kết quả đầu tiên hoặc dùng sai phương thức execute | Duyệt `getResultSet()`, `getUpdateCount()`, `getMoreResults()` |
| Thủ tục gây thay đổi dữ liệu không mong muốn | Autocommit hoặc transaction trong database khác giả định | Xác định ranh giới giao dịch; thử rollback thực tế |
| Code chạy trên DB này nhưng lỗi trên DB khác | Cú pháp hoặc khả năng stored function/procedure khác nhau | Kiểm thử trên đúng DBMS/driver; tách phần SQL đặc thù |

## 9. Tự kiểm tra kiến thức

**Câu 1.** `CallableStatement` khác `PreparedStatement` ở điểm nào quan trọng nhất đối với stored procedure?

*Gợi ý:* Ngoài các tham số đầu vào, `CallableStatement` có thể đăng ký, nhận OUT/INOUT và kết quả của routine.

**Câu 2.** Trong `{? = call calculate_tax(?)}`, vị trí nào dành cho kết quả của function, vị trí nào dành cho đầu vào?

*Gợi ý:* Vị trí 1 là return; vị trí 2 là tham số đầu vào.

**Câu 3.** Vì sao `execute()` thường phù hợp hơn `executeQuery()` khi chưa biết procedure trả result set, update count hay OUT?

*Gợi ý:* `execute()` chấp nhận nhiều kiểu kết quả và cho phép duyệt lần lượt; `executeQuery()` giả định lời gọi có kết quả truy vấn phù hợp.

**Câu 4.** Nếu một procedure trả OUT `BIGINT` bằng `NULL`, điều gì xảy ra khi dùng `getLong()`?

*Gợi ý:* `getLong()` cho giá trị 0; gọi ngay `wasNull()` để phân biệt với số 0 thật.

## Ghi nhớ

Trong JDBC, **`CallableStatement` là giao diện chuyên dụng để gọi routine của cơ sở dữ liệu từ Java**. Một lời gọi chuẩn thường đi qua `prepareCall()` → `setXxx()` cho IN → `registerOutParameter()` cho OUT/INOUT → `execute()` → đọc OUT, `ResultSet` hoặc update count. Hãy tuân theo chữ ký routine, kiểm tra chỉ số tham số bắt đầu từ 1, quản lý tài nguyên và transaction rõ ràng, đồng thời xác nhận hành vi với hệ quản trị cùng JDBC driver cụ thể.

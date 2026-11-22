# Làm việc với con trỏ trả về khi driver hỗ trợ trong JDBC

Khi gọi một **stored procedure** hoặc một hàm trong cơ sở dữ liệu, ứng dụng Java có thể cần nhận về **nhiều dòng dữ liệu** thay vì chỉ một giá trị `OUT` như số nguyên hay chuỗi. Một số hệ quản trị cho phép routine mở **con trỏ (cursor)** và chuyển tham chiếu con trỏ cho bên gọi. Với JDBC, ứng dụng thường nhận con trỏ đó dưới dạng `ResultSet` qua `CallableStatement`.

Ví dụ, routine `find_customer_orders` nhận mã khách hàng, chạy truy vấn tìm đơn và trả một con trỏ để Java đọc từng hàng. Cách dùng cụ thể phụ thuộc **DBMS, loại routine, phiên bản JDBC driver** và cơ chế cursor mà driver hỗ trợ. Đây là điểm khác biệt lớn so với một câu `SELECT` thông thường, nơi `PreparedStatement.executeQuery()` trả `ResultSet` trực tiếp.

Bài học thuộc chương **Thủ tục lưu trữ** trong module JDBC. Ta sẽ học cách đăng ký tham số con trỏ đầu ra, gọi routine, đọc và đóng `ResultSet` an toàn; phân biệt Oracle `SYS_REFCURSOR` với PostgreSQL `refcursor`; quản lý transaction, connection và các lỗi liên quan đến driver.

## 1. Con trỏ trả về là gì?

**Cursor** là một cơ chế phía database để đại diện cho kết quả của truy vấn hoặc vị trí duyệt kết quả. Khi một routine trả về tham chiếu con trỏ, bên gọi có thể sử dụng tham chiếu đó để lấy các hàng. Trong Java, driver tương thích thường ánh xạ kết quả này sang `java.sql.ResultSet`, cung cấp `next()` và các phương thức `getXxx(...)` quen thuộc.

Cần phân biệt ba khái niệm:

| Khái niệm | Nơi tồn tại | Vai trò |
|---|---|---|
| Cursor phía database | Phiên/kết nối cơ sở dữ liệu, tùy DBMS | Tham chiếu hoặc trạng thái duyệt truy vấn mà routine mở |
| `REF_CURSOR` / `SYS_REFCURSOR` / `refcursor` | Kiểu dữ liệu và cách khai báo của hệ quản trị | Cho phép routine trả con trỏ theo cơ chế hỗ trợ |
| `ResultSet` | Đối tượng API JDBC phía Java | Giao diện để ứng dụng đọc cột, duyệt các hàng từ driver |

`ResultSet` là **giao diện JDBC**, không đồng nghĩa trong mọi trường hợp với một cursor server đang giữ mở. Driver có thể lấy dữ liệu theo từng đợt hoặc nạp trước nhiều hàng vào bộ nhớ. Không nên mặc định rằng vì SQL trả `refcursor` thì tất cả `ResultSet.next()` đều phát sinh một lần fetch tới database.

Luồng điển hình:

```text
Ứng dụng Java
     |
     |  CallableStatement.prepareCall("{call ...}")
     |  setXxx(IN), registerOutParameter(OUT, ...)
     v
Routine trong DBMS
     |
     |  OPEN cursor FOR SELECT ...
     v
Cursor / kết quả do DB quản lý
     |
     |  CallableStatement.execute()
     |  CallableStatement.getObject(OUT)
     v
ResultSet ở JDBC
     |
     |  rs.next(), rs.getLong(), rs.getString()...
     v
Dữ liệu được chuyển thành đối tượng của ứng dụng
```

Chú ý rằng **mã Java thường phải đọc hết những dữ liệu cần dùng trong khi statement và connection còn hợp lệ**. Việc trả thẳng một `ResultSet` từ DAO sau khi đóng connection có thể khiến bên gọi đọc dữ liệu thất bại.

## 2. Khi nào cần dùng con trỏ đầu ra?

Một routine có thể dùng con trỏ trả về khi:

- Muốn đóng gói logic truy vấn phức tạp trong database, nhưng kết quả gồm **nhiều hàng** và nhiều cột.
- Cần trả **hai hoặc nhiều tập dòng** bằng nhiều tham số con trỏ đầu ra, nếu DBMS/driver hỗ trợ.
- Hệ thống đã dùng các procedure hoặc package PL/SQL có tham số `SYS_REFCURSOR`.
- Ứng dụng phải tích hợp với API database có sẵn thay vì sửa schema hoặc thay routine bằng SQL trực tiếp.

Ví dụ quy ước:

```text
find_customer_orders(
    p_customer_id  IN  NUMBER,
    p_orders       OUT SYS_REFCURSOR
)
```

Java truyền `p_customer_id`, đăng ký `p_orders` là tham số `OUT` rồi đọc các hàng trong `ResultSet`.

Tuy nhiên, **không phải truy vấn trả nhiều hàng đều cần stored procedure/cursor**. Nếu mục tiêu chỉ là lấy dữ liệu từ một bảng, `PreparedStatement.executeQuery()` thường đơn giản và rõ ràng hơn. Việc đẩy logic xuống routine có thể phù hợp với chính sách bảo mật, quản trị dữ liệu hoặc yêu cầu tích hợp của dự án, nhưng cũng làm code phụ thuộc đặc tính DBMS.

## 3. Những API JDBC liên quan

| API | Tác dụng |
|---|---|
| `Connection.prepareCall(sql)` | Tạo `CallableStatement` để gọi procedure/function |
| `CallableStatement.setLong(...)`, `setString(...)` | Truyền tham số `IN` hoặc `INOUT` |
| `CallableStatement.registerOutParameter(index, sqlType)` | Khai báo kiểu SQL của tham số `OUT` hoặc giá trị trả về |
| `CallableStatement.execute()` | Thực thi routine; trả boolean cho biết **kết quả trực tiếp đầu tiên** có phải `ResultSet` hay không |
| `CallableStatement.getObject(index)` | Lấy giá trị `OUT`; với cursor được hỗ trợ có thể là `ResultSet` |
| `CallableStatement.getResultSet()` | Lấy kết quả trực tiếp hiện tại nếu `execute()` hoặc `getMoreResults()` cho biết có `ResultSet` |
| `CallableStatement.getMoreResults()` | Chuyển đến kết quả trực tiếp kế tiếp của statement |
| `ResultSet.next()` / `getXxx(...)` | Duyệt các hàng và đọc giá trị cột |
| `ResultSet.close()` | Đóng đối tượng kết quả; giải phóng tài nguyên liên quan theo driver |

Trong JDBC 4.2, `java.sql.Types.REF_CURSOR` là hằng kiểu SQL tiêu chuẩn cho con trỏ tham chiếu. Tuy nhiên, **sự tồn tại của hằng trong JDK không bảo đảm driver và DBMS hỗ trợ nó**. Tùy sản phẩm có thể cần `Types.OTHER` hoặc một hằng riêng của driver.

```java
import java.sql.Types;

// Khi driver hỗ trợ kiểu REF_CURSOR chuẩn:
call.registerOutParameter(2, Types.REF_CURSOR);
```

Ví dụ trên là một câu lệnh bên trong phương thức đã có `CallableStatement call`. Chỉ sử dụng khi tham số thứ hai thực sự được định nghĩa là `OUT` cursor và driver hỗ trợ.

Có thể kiểm tra khả năng gọi stored procedures qua `DatabaseMetaData.supportsStoredProcedures()`, nhưng **kết quả `true` không tự chứng minh hỗ trợ `REF_CURSOR`**, càng không nói được routine cụ thể sẽ trả kiểu nào. Cần xem tài liệu và kiểm thử với chính phiên bản driver.

## 4. Quy trình chuẩn với `CallableStatement`

Quy trình xử lý một tham số `OUT` cursor thường là:

1. Lấy `Connection` từ `DataSource` đã cấu hình driver của database.
2. Tạo `CallableStatement` bằng `prepareCall("{call routine(?, ?)}")` hoặc cú pháp gọi **function** phù hợp.
3. Truyền đầy đủ tham số `IN` bằng `setXxx(...)`.
4. Gọi `registerOutParameter(...)` cho tham số `OUT` trước khi thực thi.
5. Gọi `execute()`; đọc cursor từ `getObject(index)`.
6. Kiểm tra kiểu đối tượng, ép về `ResultSet` nếu driver trả đối tượng tương thích; duyệt và ánh xạ các cột.
7. Đóng `ResultSet`, sau đó `CallableStatement`, rồi kết thúc transaction/đóng `Connection` theo đúng thứ tự và chính sách.
8. Nếu routine có thay đổi dữ liệu, quản lý `commit()` và `rollback()` như những transaction JDBC bình thường, trừ khi routine/DBMS có ngữ nghĩa riêng phải kiểm tra.

Hai tình huống dễ nhầm:

- `execute()` trả `false` **không có nghĩa routine không trả cursor qua tham số `OUT`**. Boolean đó mô tả **kết quả trực tiếp đầu tiên** của statement, chứ không phải sự hiện diện của tham số `OUT`.
- `getResultSet()` và `getObject(outIndex)` phục vụ **hai đường trả kết quả khác nhau**. Nếu cursor là tham số `OUT`, đọc qua `getObject(outIndex)` theo hợp đồng driver. Không giả định `getResultSet()` tự truy cập đúng cursor đó.

## 5. Ví dụ Oracle: thủ tục có `OUT SYS_REFCURSOR`

Oracle hỗ trợ `SYS_REFCURSOR` trong PL/SQL. Ví dụ sau sử dụng bảng đơn hàng và một thủ tục trả về các đơn của khách hàng.

### 5.1. Định nghĩa bảng và procedure

Cú pháp Oracle:

```sql
CREATE TABLE shop_orders (
    order_id      NUMBER(19) PRIMARY KEY,
    customer_id   NUMBER(19) NOT NULL,
    total_amount  NUMBER(18, 2) NOT NULL,
    status        VARCHAR2(20) NOT NULL
);

INSERT INTO shop_orders
    (order_id, customer_id, total_amount, status)
VALUES (1001, 51, 125000, 'PAID');

INSERT INTO shop_orders
    (order_id, customer_id, total_amount, status)
VALUES (1002, 51, 89000, 'NEW');

COMMIT;

CREATE OR REPLACE PROCEDURE find_customer_orders (
    p_customer_id IN NUMBER,
    p_orders      OUT SYS_REFCURSOR
)
AS
BEGIN
    OPEN p_orders FOR
        SELECT order_id, total_amount, status
        FROM shop_orders
        WHERE customer_id = p_customer_id
        ORDER BY order_id;
END;
/
```

Dấu `/` sau `END;` là lệnh của một số công cụ chạy script Oracle như SQL*Plus/SQLcl; không phải nội dung PL/SQL để đưa trực tiếp vào `PreparedStatement`. Tùy công cụ tạo routine, cách gửi DDL có thể khác.

Trong routine trên, `OPEN p_orders FOR SELECT ...` tạo con trỏ trả về các hàng; **không có tham số OUT riêng cho từng cột**. Java sẽ dùng `ResultSet.getLong`, `getBigDecimal` và `getString` để đọc các cột.

### 5.2. Gọi procedure bằng JDBC

Ví dụ dùng chuẩn JDBC 4.2 cùng driver Oracle **có hỗ trợ `Types.REF_CURSOR`**. Ứng dụng nhận một danh sách ID, đọc và đóng cursor trước khi rời phương thức.

```java
import javax.sql.DataSource;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.ArrayList;
import java.util.List;

public final class OracleOrderCursorDao {
    private OracleOrderCursorDao() {
    }

    public static List<Long> findOrderIds(
            DataSource dataSource, long customerId) throws SQLException {

        String callSql = "{call find_customer_orders(?, ?)}";
        List<Long> orderIds = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             CallableStatement call = connection.prepareCall(callSql)) {

            call.setLong(1, customerId);                   // IN
            call.registerOutParameter(2, Types.REF_CURSOR); // OUT
            call.execute();

            Object cursor = call.getObject(2);
            if (!(cursor instanceof ResultSet)) {
                throw new SQLException(
                        "Driver không trả OUT cursor dưới dạng ResultSet");
            }

            try (ResultSet rs = (ResultSet) cursor) {
                while (rs.next()) {
                    long orderId = rs.getLong("order_id");
                    // Có thể đọc thêm:
                    // BigDecimal total = rs.getBigDecimal("total_amount");
                    // String status = rs.getString("status");
                    orderIds.add(orderId);
                }
            }
        }

        return orderIds;
    }
}
```

Kết quả kỳ vọng với khách hàng `51` là danh sách `[1001, 1002]`. Nếu không có đơn hàng, cursor hợp lệ có thể vẫn được trả về nhưng `rs.next()` trả `false` ngay từ lần đầu, và danh sách rỗng là kết quả nghiệp vụ bình thường.

Ví dụ chỉ **đọc dữ liệu**, nên không chủ động mở transaction bằng `setAutoCommit(false)`. Nếu procedure thực sự ghi dữ liệu hoặc driver yêu cầu giữ transaction cho cursor, cần thiết kế ranh giới transaction tường minh và kiểm thử. Oracle cũng có API driver riêng để đăng ký con trỏ ở một số phiên bản, nhưng không nên tự dùng hằng vendor khi driver hiện tại đã hỗ trợ `Types.REF_CURSOR`.

### 5.3. Những giới hạn cần kiểm chứng trên Oracle

- Dùng đúng tên schema/package, cách cấp quyền `EXECUTE` và các tham số của procedure; tên `find_customer_orders` ở đây chỉ là ví dụ.
- Khi dùng package, chuỗi gọi có thể chứa tên như `{call shop_pkg.find_customer_orders(?, ?)}`.
- Thứ tự tham số trong `CallableStatement` bắt đầu từ **1**. Đầu vào ở vị trí 1 và cursor ở vị trí 2.
- `ResultSet` còn phụ thuộc trạng thái của connection/statement. Hãy xử lý nó ngay trong phạm vi còn mở tài nguyên.
- Có driver cung cấp cursor qua kiểu riêng của vendor; phải đối chiếu tài liệu version đang dùng thay vì giả định một ánh xạ duy nhất.

## 6. Ví dụ PostgreSQL: hàm trả `refcursor`

PostgreSQL có kiểu `refcursor`. Cách gọi từ JDBC khác ví dụ Oracle ở hai điểm trọng yếu:

1. PostgreSQL thường khai báo **hàm `RETURNS refcursor`**, thay vì procedure có tham số `OUT SYS_REFCURSOR` như Oracle.
2. Với pgJDBC theo đường dùng `refcursor` đã được hỗ trợ phổ biến, tham số trả về thường đăng ký bằng **`Types.OTHER`**, sau đó `getObject(...)` trả `ResultSet`. Đây là **quy tắc driver PostgreSQL**, không phải lý do đổi tất cả cursor JDBC sang `Types.OTHER`.

### 6.1. Tạo bảng và hàm trả con trỏ

SQL PostgreSQL:

```sql
CREATE TABLE shop_orders (
    order_id      BIGINT PRIMARY KEY,
    customer_id   BIGINT NOT NULL,
    total_amount  NUMERIC(18, 2) NOT NULL,
    status        VARCHAR(20) NOT NULL
);

INSERT INTO shop_orders
    (order_id, customer_id, total_amount, status)
VALUES
    (1001, 51, 125000.00, 'PAID'),
    (1002, 51, 89000.00, 'NEW');

CREATE OR REPLACE FUNCTION find_customer_orders(
    p_customer_id BIGINT
) RETURNS refcursor
LANGUAGE plpgsql
AS $$
DECLARE
    result_cursor refcursor;
BEGIN
    OPEN result_cursor FOR
        SELECT order_id, total_amount, status
        FROM shop_orders
        WHERE customer_id = p_customer_id
        ORDER BY order_id;

    RETURN result_cursor;
END;
$$;
```

Điểm dễ bỏ sót: con trỏ PostgreSQL thông thường gắn với **transaction**. Nếu transaction đã kết thúc, cursor có thể không còn hợp lệ để fetch dữ liệu. Vì vậy khi dùng `refcursor` từ JDBC, cần tắt auto-commit và đọc cursor **trước khi commit hoặc rollback**.

### 6.2. Gọi hàm từ `CallableStatement`

```java
import javax.sql.DataSource;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.ArrayList;
import java.util.List;

public final class PostgresOrderCursorDao {
    private PostgresOrderCursorDao() {
    }

    public static List<Long> findOrderIds(
            DataSource dataSource, long customerId) throws SQLException {

        String callSql = "{? = call find_customer_orders(?)}";
        List<Long> orderIds = new ArrayList<>();

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                try (CallableStatement call =
                             connection.prepareCall(callSql)) {

                    // Tham số số 1 là giá trị trả về của function.
                    call.registerOutParameter(1, Types.OTHER);
                    call.setLong(2, customerId);
                    call.execute();

                    Object cursor = call.getObject(1);
                    if (!(cursor instanceof ResultSet)) {
                        throw new SQLException(
                                "pgJDBC không trả refcursor là ResultSet");
                    }

                    try (ResultSet rs = (ResultSet) cursor) {
                        while (rs.next()) {
                            orderIds.add(rs.getLong("order_id"));
                        }
                    }
                }

                // Cursor đã được đọc/đóng trước khi transaction kết thúc.
                connection.commit();

            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }

        return orderIds;
    }
}
```

Với pgJDBC, cú pháp escape cho **function** thường là `{? = call ...}`. Driver có tùy chọn diễn giải cú pháp gọi routine như `escapeSyntaxCallMode`; kết quả thực tế cần xác minh khi chuyển giữa function và procedure, đặc biệt với phiên bản PostgreSQL có hỗ trợ `CALL`. Ví dụ này cố ý sử dụng **function trả một `refcursor`**.

`Types.OTHER` ở đây chỉ thể hiện cách pgJDBC ánh xạ kiểu `refcursor` ở phiên bản hỗ trợ; nếu driver của dự án có cách ánh xạ khác hoặc không trả `ResultSet`, phải theo hợp đồng của driver đó. Không viết code tự động thử hàng loạt kiểu OUT và suy rằng kiểu nào cũng tương đương.

### 6.3. Một lưu ý về hiệu năng của pgJDBC

Ở một số phiên bản pgJDBC, khi đọc `refcursor` thông qua `CallableStatement.getObject(...)`, driver có thể **nạp toàn bộ dữ liệu con trỏ vào phía client**, nên `setFetchSize(...)` không nhất thiết giúp stream từng lô như khi chạy `PreparedStatement.executeQuery()` thông thường. Đây là hành vi cần xác nhận bằng phiên bản driver và benchmark của dự án.

Nếu routine trả hàng triệu dòng, không mặc định rằng con trỏ trả về luôn tiết kiệm RAM. Có thể cân nhắc:

- Truy vấn tham số hóa trực tiếp bằng `PreparedStatement` với cách fetch thích hợp.
- Phân trang theo khóa hoặc điều kiện nghiệp vụ.
- Giới hạn dữ liệu trả về ngay trong routine.
- Đo lượng bộ nhớ của JVM, thời gian giữ transaction và số lượt fetch.

## 7. Hai con trỏ OUT và nhiều tập kết quả

Một số procedure trả **nhiều con trỏ OUT**, chẳng hạn `p_orders` và `p_payments`. Mỗi tham số được đăng ký và lấy riêng:

```java
String callSql = "{call fetch_customer_report(?, ?, ?)}";

try (CallableStatement call = connection.prepareCall(callSql)) {
    call.setLong(1, customerId);
    call.registerOutParameter(2, Types.REF_CURSOR);
    call.registerOutParameter(3, Types.REF_CURSOR);

    call.execute();

    try (ResultSet orders = (ResultSet) call.getObject(2)) {
        while (orders != null && orders.next()) {
            System.out.println("Order: " + orders.getLong("order_id"));
        }
    }

    try (ResultSet payments = (ResultSet) call.getObject(3)) {
        while (payments != null && payments.next()) {
            System.out.println("Payment: " +
                    payments.getLong("payment_id"));
        }
    }
}
```

Đây là ví dụ **minh họa phần đọc**: routine `fetch_customer_report` và cấu trúc cột phải được tạo đúng trong DBMS hỗ trợ. Không nên đưa thẳng tên này vào production khi chưa có routine tương ứng.

Không nhầm **hai tham số `OUT REF_CURSOR`** với một routine trả **nhiều kết quả trực tiếp**. Nếu procedure phát sinh result sets và update counts trực tiếp, JDBC dùng chuỗi `execute()`, `getResultSet()`, `getUpdateCount()` và `getMoreResults()`. Đó là cơ chế khác với lấy cursor qua `getObject(outIndex)`.

Một vòng duyệt kết quả trực tiếp có thể viết:

```java
boolean hasResultSet = call.execute();

while (true) {
    if (hasResultSet) {
        try (ResultSet rs = call.getResultSet()) {
            while (rs.next()) {
                // Đọc ResultSet hiện tại.
            }
        }
    } else {
        int updateCount = call.getUpdateCount();
        if (updateCount == -1) {
            break; // Không còn kết quả trực tiếp nào.
        }
        // Xử lý số hàng của một kết quả UPDATE nếu cần.
    }

    hasResultSet = call.getMoreResults();
}
```

Vòng trên minh họa cách xử lý **kết quả trực tiếp**, giả định có biến `call` loại `CallableStatement` trong phạm vi còn mở. Với tham số con trỏ `OUT`, lấy kết quả bằng `getObject(...)` theo driver thay vì tự suy rằng vòng `getMoreResults()` sẽ chuyển qua các con trỏ đó.

## 8. Vòng đời của cursor, ResultSet, statement và connection

Một cursor trả về có thể giữ tài nguyên phía DBMS: trạng thái kết quả, bộ nhớ, snapshot, khóa hoặc những handle cần thiết. Thời điểm giữ và giải phóng cụ thể phụ thuộc hệ quản trị và loại cursor.

Thứ tự xử lý thường an toàn:

```text
Mở Connection
  └── tạo CallableStatement
        ├── truyền IN và đăng ký OUT
        ├── execute()
        └── lấy ResultSet từ OUT cursor
              ├── rs.next() / ánh xạ dữ liệu
              └── close ResultSet
        └── close CallableStatement
  └── commit/rollback nếu transaction do ứng dụng quản lý
Đóng/trả Connection về pool
```

**Không trả `ResultSet` ra khỏi phạm vi `try-with-resources` nếu connection hoặc statement đã được đóng ở bên trong.** Một phương thức DAO nên trả `List<OrderDto>`, đối tượng domain hoặc cấu trúc kết quả đã được materialize, để tầng gọi không phải giữ connection.

Một ví dụ **cần tránh**:

```java
// Sai: ResultSet còn phụ thuộc tài nguyên đã bị đóng!
public ResultSet queryCursor(DataSource source) throws SQLException {
    try (Connection connection = source.getConnection();
         CallableStatement call =
                 connection.prepareCall("{call find_customer_orders(?, ?)}")) {
        call.setLong(1, 51L);
        call.registerOutParameter(2, Types.REF_CURSOR);
        call.execute();
        return (ResultSet) call.getObject(2);
    }
}
```

Trong thiết kế streaming đặc biệt, có thể giữ connection mở trong một abstraction có quản lý tài nguyên rõ ràng, nhưng đó là một giao kèo khác và caller phải đóng đúng hạn. Với các tình huống đọc kết quả thông thường, xử lý ngay trong DAO dễ bảo trì hơn.

### 8.1. Auto-commit và transaction

- Với PostgreSQL `refcursor`, thường cần `setAutoCommit(false)` và giữ transaction mở trong lúc fetch; tự động commit có thể khiến cursor không còn dùng được.
- Với Oracle `SYS_REFCURSOR`, ngữ nghĩa vòng đời và khả năng tồn tại sau các lệnh commit phụ thuộc đặc tính con trỏ/driver; không suy từ PostgreSQL sang Oracle.
- Nếu routine **ghi dữ liệu**, transaction bao quanh lời gọi và dữ liệu cập nhật cần được quản lý chặt chẽ. `ResultSet.close()` không tương đương `commit()` hoặc `rollback()`.
- `Connection.close()` không phải cơ chế bảo đảm rollback khi còn transaction chưa kết thúc; hành vi phụ thuộc driver và pool. Khi tự quản lý transaction, hãy kết thúc rõ ràng.

### 8.2. Holdability có giải quyết được tất cả?

JDBC có `ResultSet.HOLD_CURSORS_OVER_COMMIT` và `ResultSet.CLOSE_CURSORS_AT_COMMIT`, cùng phương thức `Connection.getHoldability()`. Tuy nhiên, đây **không phải bảo đảm chung** rằng tham số `OUT refcursor` của mọi DBMS vẫn đọc được sau commit. Loại cursor, cơ chế PL/SQL, driver và DBMS có thể áp dụng quy tắc riêng. Cách đơn giản nhất là giữ ranh giới transaction phù hợp và hoàn tất việc đọc con trỏ trong khoảng còn hợp lệ.

## 9. Đọc dữ liệu chính xác và an toàn

### 9.1. Kiểu dữ liệu và NULL

Với `ResultSet` nhận từ cursor, dùng những API đọc dữ liệu quen thuộc:

```java
while (rs.next()) {
    long id = rs.getLong("order_id");
    java.math.BigDecimal amount =
            rs.getBigDecimal("total_amount");
    String status = rs.getString("status");

    // Kiểm tra null nếu cột cho phép NULL.
    System.out.printf("%d | %s | %s%n", id, amount, status);
}
```

`getLong(...)` trả `0` khi cột SQL là `NULL`; nếu cần phân biệt NULL thật, gọi `rs.wasNull()` ngay sau lần đọc hoặc dùng `getObject(..., Long.class)` khi driver hỗ trợ. `BigDecimal` phù hợp với cột `DECIMAL`/`NUMERIC` cho tiền tệ.

### 9.2. SQL tham số hóa trong lời gọi routine

`CallableStatement` sử dụng dấu `?` cho tham số. Không tự tạo chuỗi gọi procedure bằng cách nối mã khách hàng hay mã đơn vào SQL:

```java
// Nên dùng:
CallableStatement call =
        connection.prepareCall("{call find_customer_orders(?, ?)}");
call.setLong(1, customerId);
call.registerOutParameter(2, Types.REF_CURSOR);
```

Chú ý: việc gọi procedure qua `CallableStatement` **không tự loại bỏ mọi lỗ hổng SQL injection**. Nếu bên trong routine tự ghép câu SQL động từ input không tin cậy, vẫn cần bind parameter/quote identifier đúng cách theo DBMS. Phân quyền `EXECUTE` và quyền đọc dữ liệu cũng cần tuân thủ nguyên tắc cấp quyền tối thiểu.

### 9.3. Tên cột và thứ tự cột

Routine có thể thay đổi danh sách cột theo schema hoặc logic SQL. Để giảm lỗi khi nhận cursor, nên khai báo cột có tên rõ ràng và alias ổn định:

```sql
SELECT order_id,
       total_amount AS amount,
       status
FROM shop_orders
WHERE customer_id = p_customer_id;
```

Trong Java, đọc tên alias `amount` khi SQL trả alias đó. Nếu routine trả `SELECT *`, thay đổi schema có thể vô tình đổi nhiều cột mà Java phụ thuộc. Với API lâu dài, xem cấu trúc kết quả của routine như một phần hợp đồng giữa DB và ứng dụng.

## 10. Lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `SQLFeatureNotSupportedException` khi đăng ký `Types.REF_CURSOR` | Driver chưa hỗ trợ kiểu OUT cursor tiêu chuẩn | Xem driver/version; áp dụng mapping do vendor công bố, nếu có |
| `SQLException` khi gọi `prepareCall/execute` | Routine không tồn tại, sai schema/package, sai quyền, sai chữ ký | Kiểm tra tên routine, quyền `EXECUTE`, thứ tự và số lượng tham số |
| `getObject(outIndex)` trả đối tượng không phải `ResultSet` | Driver trả kiểu riêng, trả tên cursor hoặc mapping không phù hợp | Kiểm tra API và cơ chế của driver; không ép kiểu mù |
| `ClassCastException` khi ép sang `ResultSet` | Kỳ vọng không khớp kiểu kết quả thực | Dùng `instanceof`/kiểm tra null trước khi cast |
| Cursor PostgreSQL không còn hợp lệ | Transaction đã commit/rollback hoặc auto-commit bật | `setAutoCommit(false)`, đọc và đóng cursor trước khi kết thúc transaction |
| `ResultSet.next()` lỗi sau khi DAO trả về | Statement/connection đã đóng quá sớm | Materialize kết quả trong DAO hoặc quản lý streaming scope rõ ràng |
| `execute()` trả `false` dù routine có dữ liệu | Dữ liệu được trả qua OUT parameter, không phải result set trực tiếp | Lấy `call.getObject(index)` thay vì suy từ boolean |
| Dữ liệu nhiều gây tốn bộ nhớ | Driver nạp trước toàn bộ cursor hoặc kết quả quá lớn | Giới hạn/paginate, đo memory, kiểm tra fetch behavior của driver |
| Lỗi khi đọc cột | Tên cột/alias hoặc kiểu dữ liệu khác hợp đồng | Kiểm tra metadata `ResultSetMetaData` và SQL của routine |
| Đọc nhiều cursor nhưng bỏ quên đóng một kết quả | Cursor/session resources không được giải phóng kịp | `try-with-resources` cho từng `ResultSet` |
| Chạy được trên Oracle nhưng không chạy trên PostgreSQL | Ngôn ngữ routine và mapping OUT cursor khác nhau | Viết adapter theo DBMS, xác nhận contract driver |

### 10.1. Xem kiểu cột từ `ResultSetMetaData`

Khi nhận được một `ResultSet` nhưng chưa rõ cấu trúc thực tế, có thể đọc metadata thay vì suy đoán:

```java
import java.sql.ResultSetMetaData;

ResultSetMetaData meta = rs.getMetaData();
for (int i = 1; i <= meta.getColumnCount(); i++) {
    System.out.println(
            meta.getColumnLabel(i) + " : " +
            meta.getColumnTypeName(i));
}
```

Đoạn này chạy trong phạm vi có `ResultSet rs`. Kết quả phản ánh cấu trúc **các cột của cursor hiện tại**, không chứng minh driver hỗ trợ `REF_CURSOR` khi bước đăng ký tham số còn chưa thành công.

### 10.2. Lưu giữ đầy đủ thông tin `SQLException`

```java
catch (SQLException error) {
    for (SQLException current = error;
         current != null;
         current = current.getNextException()) {

        System.err.println("SQLState=" + current.getSQLState()
                + ", vendorCode=" + current.getErrorCode()
                + ", message=" + current.getMessage());
    }
    throw error;
}
```

Mã trên là nhánh `catch` minh họa, cần được đặt trong một phương thức có khối `try` tương ứng. Trong hệ thống thực tế, không ghi thông tin nhạy cảm như mật khẩu hay dữ liệu khách hàng vào log. Nếu routine có side effect, cần đảm bảo transaction được commit/rollback theo ranh giới nghiệp vụ, không xem việc in log là xử lý lỗi đầy đủ.

## 11. So sánh các cách trả về nhiều hàng

| Cách trả kết quả | JDBC sử dụng | Thường phù hợp |
|---|---|---|
| `SELECT` tham số hóa trực tiếp | `PreparedStatement.executeQuery()` trả `ResultSet` | Truy vấn thông thường, kiểm soát SQL từ Java |
| Procedure trả tham số `OUT REF_CURSOR` | `CallableStatement.registerOutParameter()` + `getObject()` | API routine cần trao một hay nhiều cursor |
| Function PostgreSQL trả `refcursor` | `CallableStatement` theo quy ước pgJDBC hoặc cơ chế DB tương ứng | Hệ thống PostgreSQL sử dụng function/cursor |
| Procedure trả tập kết quả trực tiếp/implicit results | `CallableStatement.execute()` + `getResultSet()`/`getMoreResults()` | Driver/DBMS trả trực tiếp nhiều kết quả không qua OUT cursor |
| Trả JSON/XML/LOB chứa danh sách | `getString()`, `getBlob()`/`getClob()` và giải mã | Khi hợp đồng API ưu tiên một payload tổng hợp |

Các cách trên **không tương đương về bộ nhớ, giao thức, transaction hoặc độ portable**. Ví dụ, việc mã hóa nhiều hàng thành JSON có thể thuận tiện cho vài API nhưng làm mất khả năng duyệt cột kiểu JDBC trực tiếp; con trỏ OUT lại cần chú ý resource lifetime.

Khi lựa chọn, hãy bắt đầu từ hợp đồng nghiệp vụ và driver hiện có. Không chuyển hàng loạt truy vấn sang con trỏ chỉ vì muốn tăng hiệu năng: lợi ích thực tế cần được đo trên DB, dữ liệu và cách fetch của ứng dụng.

## 12. Kiểm thử tích hợp với driver thật

Vì tính năng REF_CURSOR phụ thuộc nhiều vào driver và DBMS, cần kiểm chứng trên môi trường giống production.

1. **Trường hợp có dữ liệu:** routine trả 2–3 hàng; xác nhận đúng cột, kiểu Java và thứ tự mong muốn.
2. **Trường hợp rỗng:** procedure/function hợp lệ trả cursor không có dòng; code trả danh sách rỗng, không xem là lỗi.
3. **Chữ ký tham số:** thử sai index OUT hoặc sai kiểu đăng ký để chắc chắn test phát hiện lỗi cấu hình.
4. **Driver support:** kiểm thử `Types.REF_CURSOR` với driver dự kiến; nếu dùng PostgreSQL mapping `Types.OTHER`, kiểm tra đúng kiểu `ResultSet` được trả.
5. **Đóng tài nguyên:** kiểm tra không trả `ResultSet` ra ngoài scope; theo dõi connection, statement, cursor có được đóng đúng hạn không.
6. **Transaction PostgreSQL:** thử bật/tắt auto-commit; xác nhận cursor được fetch trước khi transaction kết thúc.
7. **Dữ liệu lớn:** thử nhiều nghìn/hàng trăm nghìn hàng, đo memory, fetch time và thời gian giữ connection; không suy fetch size từ code khi chưa đo.
8. **Nhiều cursor:** với routine trả hai OUT cursors, xác nhận cả hai result sets được đọc và đóng riêng.
9. **Lỗi giữa lúc đọc:** mô phỏng mất kết nối hoặc `SQLException` trong `rs.next()`; đảm bảo đóng tài nguyên và rollback nếu transaction do code quản lý.
10. **Thay đổi routine:** cập nhật alias/cột trong một môi trường test để xác nhận các consumer phát hiện sai lệch hợp đồng dữ liệu.

Ghi lại **phiên bản DBMS, phiên bản JDBC driver, SQL định nghĩa routine, SQL call, chế độ auto-commit và các kết quả `SQLException`**. Một ví dụ chạy đúng trên Oracle hoặc PostgreSQL không đủ chứng minh code portable sang mọi cơ sở dữ liệu quan hệ.

## 13. Checklist khi đưa vào ứng dụng

- Routine là **procedure** hay **function**? Cú pháp `prepareCall` có đúng với loại routine và driver không?
- Có xác định chính xác thứ tự/tham số `IN`, `OUT` và kiểu cursor của DBMS chưa?
- Driver có hỗ trợ `Types.REF_CURSOR` hay yêu cầu mapping riêng như `Types.OTHER` không?
- `execute()`, `getObject(outIndex)` và `ResultSet.next()` có được dùng đúng vai trò không?
- Có đọc hết dữ liệu cần thiết trước khi đóng `ResultSet`/`CallableStatement`/`Connection` không?
- Có giữ transaction mở khi cursor cần, đặc biệt với PostgreSQL `refcursor` không?
- Nếu routine cập nhật dữ liệu, transaction và xử lý lỗi/rollback có thuộc đúng tầng sở hữu nghiệp vụ không?
- Có đo hiệu năng, bộ nhớ và xác minh fetch behavior trên driver thực tế không?
- Có kiểm tra permission, SQL injection trong routine và tuân thủ nguyên tắc không log dữ liệu nhạy cảm không?

## Ghi nhớ

- **`XA` không liên quan ở đây**: con trỏ `OUT` là cơ chế trả kết quả của routine trên JDBC connection; không cần giao dịch phân tán chỉ vì dùng cursor.
- **`CallableStatement`** gọi routine, nhận tham số `IN` và đăng ký tham số `OUT`.
- **`Types.REF_CURSOR`** là hằng kiểu SQL chuẩn trong JDBC 4.2, nhưng cần **driver hỗ trợ thực tế**; PostgreSQL thường dùng `Types.OTHER` cho function `RETURNS refcursor` theo pgJDBC.
- **`getObject(outIndex)`** lấy giá trị cursor `OUT`, thường là `ResultSet`; còn `getResultSet()`/`getMoreResults()` xử lý kết quả trực tiếp.
- **Đóng `ResultSet`, `CallableStatement` và `Connection` đúng phạm vi** để không rò rỉ tài nguyên.
- **Vòng đời cursor phụ thuộc DBMS và transaction**; với PostgreSQL nên tắt auto-commit và đọc trước khi commit.
- **Không giả định REF_CURSOR tự động stream từng hàng**; kiểm chứng khả năng driver và hiệu năng bằng test thực tế.

Làm chủ con trỏ trả về giúp ứng dụng JDBC tích hợp với stored procedure phức tạp mà vẫn giữ được cách đọc dữ liệu bằng `ResultSet` quen thuộc, kiểm soát tài nguyên rõ ràng và tránh những giả định sai về hỗ trợ của driver.

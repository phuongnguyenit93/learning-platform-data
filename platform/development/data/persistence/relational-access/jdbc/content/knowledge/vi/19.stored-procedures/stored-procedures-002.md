# Cú pháp JDBC để gọi procedure và function

Trong JDBC, ứng dụng Java có thể gửi SQL tham số hóa bằng `PreparedStatement` hoặc gọi **routine đã được định nghĩa trong cơ sở dữ liệu**: *stored procedure* (thủ tục lưu trữ) và *function* (hàm). API chính để gọi routine là `CallableStatement`, một nhánh mở rộng của `PreparedStatement` có khả năng đăng ký tham số đầu ra và nhận giá trị trả về.

Khác biệt quan trọng nhất ở cấp cú pháp là **procedure được gọi qua `{call ...}`**, còn **function có giá trị trả về dạng scalar có thể gọi qua `{? = call ...}`** nếu driver và hệ quản trị hỗ trợ. `?` đầu tiên trong cú pháp function dành riêng cho giá trị return; vì thế các tham số đầu vào của function bị dịch một vị trí so với chữ ký logic.

Bài học nằm trong chương **Thủ tục lưu trữ** của module **JDBC**, gắn với các API chuẩn `DataSource`, `Connection`, `CallableStatement`, `ResultSet`, SQL tham số hóa và transaction.

Sau bài học, bạn có thể:

- Phân biệt procedure, function và các loại kết quả của routine.
- Viết cú pháp escape JDBC phù hợp, đếm chính xác vị trí tham số từ **1**.
- Dùng `setXxx`, `registerOutParameter`, `execute` và `getXxx` cho `IN`, `OUT` và `INOUT`.
- Xử lý `NULL`, `BigDecimal` và tham số kiểu ngày giờ.
- Duyệt result set, update count và tham số OUT khi routine trả nhiều kết quả.
- Xác định ranh giới transaction, kiểm soát lỗi và nhận biết các khác biệt giữa DBMS/driver.

## 1. Procedure và function: mục đích và hợp đồng

**Stored procedure** là một thao tác có tên trong database; nó có thể thực hiện DML và trả thông tin qua tham số `OUT`, `INOUT`, result set hoặc các cách đặc thù của DBMS. **Stored function** có một giá trị trả về theo khai báo; tùy hệ quản trị, function được dùng trong biểu thức SQL, trong `SELECT` hoặc qua cú pháp gọi dành riêng cho function.

| Tiêu chí | Procedure | Function |
| --- | --- | --- |
| Cú pháp JDBC escape điển hình | `{call name(?, ?)}` | `{? = call name(?, ?)}` |
| Vị trí return bắt buộc trong escape | Không có | **Index 1** |
| Cung cấp tham số vào | `setXxx` cho `IN`/`INOUT` | `setXxx` cho đối số đầu vào |
| Nhận giá trị đầu ra | `OUT`/`INOUT`, result set hoặc update count | Giá trị return; đôi khi có kiểu kết quả khác theo DBMS |
| Có thực hiện thay đổi dữ liệu? | Thường có thể, phụ thuộc routine/DBMS | Có thể bị hạn chế nghiêm ngặt tùy DBMS |
| Ranh giới transaction | Theo DBMS và ngữ cảnh gọi | Theo DBMS và ngữ cảnh gọi |

Không suy rằng mọi procedure đều có OUT, mọi function đều không có tác dụng phụ, hoặc mọi routine đều trả một `ResultSet`. **Chữ ký routine và hợp đồng kết quả** là nguồn thông tin quyết định cách gọi Java.

Cú pháp `CREATE PROCEDURE` và `CREATE FUNCTION` khác nhau giữa PostgreSQL, MySQL, SQL Server và Oracle. Các chữ ký mô tả bên dưới là **hợp đồng logic** để giải thích JDBC; chúng không phải câu DDL dùng chung cho mọi DBMS.

## 2. Cú pháp JDBC escape

JDBC có dạng escape để yêu cầu driver chuyển lời gọi sang cú pháp của hệ quản trị:

~~~sql
{call schema.procedure_name(?, ?)}
{? = call schema.function_name(?, ?)}
~~~

Một số trường hợp thường gặp:

| Tình huống | Escape string | Tham số JDBC |
| --- | --- | --- |
| Procedure không tham số | `{call system.ping()}` | Không có `?` |
| Procedure một tham số | `{call inventory.refresh(?)}` | Vị trí 1 |
| Procedure có `IN` và `OUT` | `{call report.count_items(?, ?)}` | Vị trí 1 và 2 |
| Function không tham số | `{? = call system.next_value()}` | Return tại vị trí 1 |
| Function một tham số | `{? = call billing.tax_rate(?)}` | Return 1, input 2 |
| Function hai tham số | `{? = call math.add_values(?, ?)}` | Return 1, input 2 và 3 |

Các chỉ số trên **bắt đầu từ 1** theo quy ước JDBC. Không dùng index 0. Đối với function, cần đếm cả dấu `?` của giá trị return.

Luồng gọi tổng quát:

~~~mermaid
flowchart LR
    A["DataSource.getConnection"] --> B["Connection.prepareCall"]
    B --> C["setXxx cho IN/INOUT"]
    C --> D["registerOutParameter cho OUT/INOUT/return"]
    D --> E["execute"]
    E --> F["Xử lý ResultSet / update count nếu có"]
    F --> G["getXxx đọc OUT / return"]
    G --> H["Đóng statement và connection"]
~~~

`CallableStatement` kế thừa những thao tác của `PreparedStatement`: `setInt`, `setLong`, `setString`, `setBigDecimal`, `setObject`, `setNull`. Nó bổ sung `registerOutParameter` và khả năng đọc giá trị đầu ra.

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement call =
             connection.prepareCall("{call inventory.refresh(?)}")) {

    call.setLong(1, 101L);
    call.execute();
}
~~~

Đây là đoạn mã minh họa bên trong phương thức đã có biến `dataSource`. Routine `inventory.refresh` phải tồn tại, có đúng một tham số đầu vào và cho phép tài khoản kết nối thực thi.

## 3. Ví dụ gọi procedure có `IN` và `OUT`

Giả sử database đã triển khai procedure với hợp đồng:

~~~text
report.count_open_orders(
    IN  p_customer_id BIGINT,
    OUT p_count       INTEGER
)
~~~

Ứng dụng truyền ID khách hàng và nhận số đơn hàng đang mở.

~~~java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Objects;
import javax.sql.DataSource;

public final class OrderReportRepository {
    private final DataSource dataSource;

    public OrderReportRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public int countOpenOrders(long customerId) throws SQLException {
        String sql = "{call report.count_open_orders(?, ?)}";

        try (Connection connection = dataSource.getConnection();
             CallableStatement call = connection.prepareCall(sql)) {

            call.setLong(1, customerId);              // IN
            call.registerOutParameter(2, Types.INTEGER); // OUT

            call.execute();

            int count = call.getInt(2);
            if (call.wasNull()) {
                throw new SQLException("OUT p_count là NULL");
            }
            if (count < 0) {
                throw new SQLException("OUT p_count không hợp lệ");
            }
            return count;
        }
    }
}
~~~

Điểm cần chú ý:

1. `connection.prepareCall(sql)` tạo `CallableStatement`, không phải `PreparedStatement` thường.
2. `call.setLong(1, customerId)` truyền tham số **IN** ở vị trí 1.
3. `registerOutParameter(2, Types.INTEGER)` đăng ký tham số **OUT** trước khi `execute()`.
4. `getInt(2)` đọc giá trị OUT sau khi routine chạy; `wasNull()` phân biệt `NULL` và số 0 thực sự.
5. `try-with-resources` đóng `CallableStatement` và `Connection` kể cả khi xảy ra `SQLException`.
6. Một số driver yêu cầu tiêu thụ hết `ResultSet` và update count trước khi đọc OUT. Ví dụ này giả định routine không tạo các kết quả bổ sung cần xử lý; mục 7 trình bày trường hợp tổng quát.

Không lấy số dòng cập nhật từ `executeUpdate()` rồi coi đó là tham số OUT: **update count và tham số OUT là hai loại kết quả khác nhau**.

## 4. Ví dụ gọi function có giá trị trả về

Giả sử function logic:

~~~text
math.add_values(
    IN p_left  INTEGER,
    IN p_right INTEGER
) RETURNS INTEGER
~~~

Dạng JDBC escape là:

~~~sql
{? = call math.add_values(?, ?)}
~~~

**Index 1 dành cho return**; hai đối số `p_left` và `p_right` tương ứng index 2 và 3.

~~~java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Objects;
import javax.sql.DataSource;

public final class MathRepository {
    private final DataSource dataSource;

    public MathRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public int add(int left, int right) throws SQLException {
        String sql = "{? = call math.add_values(?, ?)}";

        try (Connection connection = dataSource.getConnection();
             CallableStatement call = connection.prepareCall(sql)) {

            call.registerOutParameter(1, Types.INTEGER);
            call.setInt(2, left);
            call.setInt(3, right);

            call.execute();

            int result = call.getInt(1);
            if (call.wasNull()) {
                throw new SQLException("Function trả về NULL");
            }
            return result;
        }
    }
}
~~~

Khi database thực sự định nghĩa `math.add_values` theo hợp đồng trên và driver hỗ trợ cú pháp escape của function:

~~~java
MathRepository repository = new MathRepository(dataSource);
System.out.println(repository.add(7, 5)); // Dự kiến: 12
~~~

Nếu viết nhầm `setInt(1, left)`, bạn đang dùng vị trí return cho input. Đây là lỗi phổ biến nhất khi chuyển từ `{call procedure(...)}` sang `{? = call function(...)}`.

Không phải driver nào cũng thực hiện lời gọi scalar function bằng escape theo cùng cách. Khi DBMS khuyến nghị gọi function trong `SELECT`, hãy dùng `PreparedStatement` với cú pháp SQL và cơ chế binding của DBMS như ở mục 8.

## 5. `IN`, `OUT` và `INOUT`

| Hướng | Java làm gì trước `execute()`? | Java làm gì sau `execute()`? |
| --- | --- | --- |
| `IN` | `setXxx(index, value)` | Không có OUT để đọc |
| `OUT` | `registerOutParameter(index, sqlType)` | `getXxx(index)` |
| `INOUT` | **Cả** `setXxx` và `registerOutParameter` trên cùng index | `getXxx` tại chính index đó |
| Function return | `registerOutParameter(1, sqlType)` | `getXxx(1)` |

### Thực hành `INOUT`

Giả sử procedure được khai báo logic:

~~~text
inventory.increase_quota(
    INOUT p_remaining INTEGER,
    IN    p_delta     INTEGER
)
~~~

Java:

~~~java
String sql = "{call inventory.increase_quota(?, ?)}";

try (Connection connection = dataSource.getConnection();
     CallableStatement call = connection.prepareCall(sql)) {

    call.setInt(1, 10);                        // IN tại vị trí 1
    call.registerOutParameter(1, Types.INTEGER); // OUT cũng vị trí 1
    call.setInt(2, 3);                         // IN tại vị trí 2

    call.execute();

    int remaining = call.getInt(1);
    if (call.wasNull()) {
        throw new SQLException("INOUT p_remaining trả NULL");
    }

    System.out.println(remaining); // Dự kiến: 13 nếu routine cộng 3
}
~~~

`INOUT` **không** tiêu thụ hai dấu `?`. Nó có một vị trí vừa để nhập vừa để xuất. Tất cả lời gọi `setXxx` và `registerOutParameter` phải hoàn tất **trước** `execute()`.

Không nên mặc định rằng tham số không truyền sẽ dùng giá trị default do DBMS định nghĩa. Cú pháp bỏ qua tham số, mặc định tham số và overload routine phụ thuộc dialect.

## 6. Khai báo đúng SQL type và xử lý `NULL`

### 6.1. Chọn `Types` khớp hợp đồng routine

`registerOutParameter` cần biết kiểu dữ liệu SQL của tham số đầu ra:

| Kiểu khai báo trong DB | Đăng ký thường gặp | Đọc ra |
| --- | --- | --- |
| `INTEGER` | `Types.INTEGER` | `getInt` |
| `BIGINT` | `Types.BIGINT` | `getLong` |
| `DECIMAL/NUMERIC` | `Types.DECIMAL` hoặc `Types.NUMERIC` | `getBigDecimal` |
| `VARCHAR` | `Types.VARCHAR` | `getString` |
| `NVARCHAR` | `Types.NVARCHAR` | `getNString`, tùy hỗ trợ |
| `BOOLEAN` | `Types.BOOLEAN` | `getBoolean` |
| `DATE` | `Types.DATE` | `getDate` hoặc kiểu Java time được driver hỗ trợ |
| `TIMESTAMP` | `Types.TIMESTAMP` | `getTimestamp` hoặc kiểu Java time được driver hỗ trợ |

Các kiểu phức tạp như cursor, array, struct hoặc kiểu riêng DBMS có thể yêu cầu tên kiểu, hằng số driver hoặc cách ánh xạ đặc thù. Không suy rằng `Types.OTHER` hoặc `Types.REF_CURSOR` hoạt động đồng nhất trên mọi hệ quản trị.

JDBC 4.2 có overload dùng `SQLType`, chẳng hạn `JDBCType.DECIMAL`, nhưng mức hỗ trợ phụ thuộc driver. `Types` theo kiểu `int` vẫn hữu dụng khi cần tương thích.

### 6.2. Đọc OUT có thể là `NULL`

Với getter object:

~~~java
call.registerOutParameter(2, Types.DECIMAL);
call.execute();

BigDecimal amount = call.getBigDecimal(2);
if (amount == null) {
    // Giá trị OUT là SQL NULL.
}
~~~

Với getter primitive:

~~~java
int count = call.getInt(2);
if (call.wasNull()) {
    // Không thể coi count == 0 là số 0 thực sự.
}
~~~

`wasNull()` phản ánh **lần đọc giá trị OUT gần nhất**. Gọi nó ngay sau getter cần kiểm tra, trước khi đọc tham số OUT khác.

### 6.3. Truyền `NULL` vào tham số `IN`

~~~java
if (customerId == null) {
    call.setNull(1, Types.BIGINT);
} else {
    call.setLong(1, customerId.longValue());
}
~~~

Dùng kiểu SQL rõ ràng khi truyền `NULL` để tránh mơ hồ khi DBMS có nhiều overload cùng tên. Không dùng giá trị giả như số 0 hoặc chuỗi rỗng nếu hợp đồng không nói chúng tương đương `NULL`.

### 6.4. Tiền và thời gian

Với tiền hoặc số thập phân cần độ chính xác, dùng `setBigDecimal`/`getBigDecimal`; tránh đi qua `double`. Mức precision/scale được quy định bởi chữ ký routine, SQL engine và nghiệp vụ, không tự được bảo đảm chỉ nhờ `BigDecimal`.

Với `LocalDate`, `LocalTime` và `LocalDateTime`, `setObject` có thể truyền vào các kiểu SQL ngày giờ tương ứng nếu driver JDBC 4.2 hỗ trợ. Đối với OUT, đăng ký `Types.DATE/TIME/TIMESTAMP` và dùng getter tương ứng hoặc `getObject(index, LocalDate.class)` khi có hỗ trợ. `LocalDateTime` không chứa thông tin múi giờ; cần làm rõ ý nghĩa của tham số SQL trước khi chuyển sang `Instant`.

## 7. `execute` và nhiều kết quả của procedure

Procedure có thể trả:

- Tham số `OUT/INOUT`;
- Một hoặc nhiều `ResultSet`;
- Một hoặc nhiều update count từ các câu DML;
- Kết hợp nhiều loại trên, tùy DBMS/driver.

Ba phương thức thực thi có khác biệt:

| API | Mục đích | Giá trị trả |
| --- | --- | --- |
| `execute()` | Tổng quát cho routine có nhiều loại kết quả | `boolean`: `true` khi **kết quả đầu tiên** là `ResultSet` |
| `executeQuery()` | Khi chắc chắn routine trả một result set phù hợp với hợp đồng driver | `ResultSet` |
| `executeUpdate()` | Khi statement chủ yếu trả update count hoặc không có result set | `int` số dòng cập nhật / kết quả tùy driver |

**`execute() == false` không phải lỗi.** Nó chỉ báo rằng kết quả đầu tiên không phải `ResultSet`, có thể là update count hoặc không có kết quả dạng câu truy vấn.

### 7.1. Duyệt tất cả result set và update count

Để không bỏ sót kết quả, có thể dùng:

~~~java
import java.sql.CallableStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

static void drainResults(CallableStatement call)
        throws SQLException {

    boolean hasResultSet = call.execute();

    while (true) {
        if (hasResultSet) {
            try (ResultSet rs = call.getResultSet()) {
                while (rs.next()) {
                    // Ánh xạ từng dòng theo hợp đồng của routine.
                    // Đừng tự ý ghi toàn bộ nội dung dòng vào log.
                }
            }
        } else {
            int updateCount = call.getUpdateCount();

            if (updateCount == -1) {
                break; // Không còn kết quả.
            }

            // updateCount có thể bằng 0; đây vẫn là kết quả hợp lệ.
        }

        hasResultSet = call.getMoreResults();
    }
}
~~~

Chu trình ở trên xét **cả** giá trị của `getMoreResults()` **và** `getUpdateCount()`. Không dừng vòng lặp chỉ vì `getMoreResults()` trả `false`: `false` còn có thể nghĩa là kết quả hiện tại là một update count, chưa chắc đã hết kết quả.

Với những driver chỉ cho đọc tham số OUT **sau khi đã tiêu thụ mọi result set/update count**, nên hoàn tất vòng này rồi mới đọc OUT:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement call = connection.prepareCall(
             "{call report.fetch_open_invoices(?, ?)}")) {

    call.setLong(1, customerId);
    call.registerOutParameter(2, Types.INTEGER);

    drainResults(call); // Hàm này tự gọi execute() đúng một lần.

    int total = call.getInt(2);
    if (call.wasNull()) {
        throw new SQLException("Procedure trả total NULL");
    }
}
~~~

Hợp đồng giả định của `report.fetch_open_invoices` là `IN customerId` và `OUT total` cùng một hoặc nhiều kết quả SQL có thể phát sinh. **Không gọi thêm `call.execute()` trước hoặc sau `drainResults`**, nếu không procedure có thể chạy lại và gây tác dụng phụ hai lần.

Khi gọi `getMoreResults()`, result set hiện tại có thể bị đóng theo cơ chế JDBC. Hãy xử lý và đóng `ResultSet` trước khi chuyển tiếp. Với procedure trả nhiều result set có **cấu trúc cột khác nhau**, mapper phải dựa vào hợp đồng cụ thể của từng kết quả, không được ép mọi tập dòng vào cùng DTO.

### 7.2. Tại sao không luôn dùng `executeQuery`?

Một procedure có thể phát update count trước khi trả result set, hoặc trả cả hai. `executeQuery` không phải cách duyệt loại kết quả tổng quát và có thể thất bại hay bỏ sót thông tin tùy driver. Khi biết trước routine **chỉ trả một result set** theo hợp đồng được kiểm thử, `executeQuery` có thể đơn giản hơn.

## 8. Dùng `PreparedStatement` với function khi phù hợp

JDBC escape `{? = call function(...)}` được hỗ trợ và biên dịch khác nhau giữa các driver. Nhiều DBMS cho gọi scalar function trong biểu thức `SELECT`; khi đó có thể sử dụng `PreparedStatement` thông thường:

~~~java
String sql = "SELECT math.add_values(?, ?) AS result";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    ps.setInt(1, 7);
    ps.setInt(2, 5);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            int result = rs.getInt("result");
            if (rs.wasNull()) {
                throw new SQLException("Function trả NULL");
            }
            System.out.println(result);
        }
    }
}
~~~

Đây là **SQL của DBMS**, không phải JDBC escape; cú pháp `SELECT schema.function(...)` và cách đặt alias phụ thuộc dialect. Điểm khác biệt ở Java: **không có dấu `?` của return** trong `SELECT`, vì giá trị function được trả dưới dạng cột `result` của `ResultSet`.

| Dùng `CallableStatement` | Dùng `PreparedStatement` |
| --- | --- |
| `{? = call math.add_values(?, ?)}` | `SELECT math.add_values(?, ?) AS result` |
| Return ở `registerOutParameter(1, ...)` | Return là cột của `ResultSet` |
| Input ở index 2, 3 | Input ở index 1, 2 |
| Dùng `execute` + `getInt(1)` | Dùng `executeQuery` + `rs.getInt("result")` |

Chọn cách được **driver và DBMS công bố hỗ trợ**, không chuyển đổi tùy tiện nếu function trả bảng, cursor hoặc kiểu dữ liệu đặc thù.

## 9. Các khác biệt giữa PostgreSQL, MySQL, SQL Server và Oracle

| Hệ quản trị | Lưu ý khi gọi routine |
| --- | --- |
| **PostgreSQL** | SQL `CALL` dùng cho procedure; function thường gọi qua `SELECT function(...)`. Driver pgJDBC có cấu hình `escapeSyntaxCallMode` ảnh hưởng cách dịch `{call ...}` thành `SELECT` hoặc `CALL`; cần đối chiếu đúng kiểu routine. |
| **MySQL** | Procedure gọi bằng `CALL` và có thể dùng `IN/OUT/INOUT`. Function thường sử dụng trong biểu thức SQL. Việc truy cập parameter metadata và nhận nhiều kết quả phụ thuộc phiên bản connector. |
| **SQL Server** | Procedure có `OUTPUT` parameter và return status dạng số nguyên. **Return status của procedure** không đồng nghĩa với giá trị của scalar function; đừng đánh đồng `{? = call proc(...)}` trên driver với function theo khái niệm chung. Scalar function thường dùng trong `SELECT`. |
| **Oracle Database** | PL/SQL procedure/function có nhiều kiểu dữ liệu riêng, bao gồm cursor. Driver có thể cần type code hoặc cơ chế register/nhận cursor đặc biệt; phải kiểm tra tài liệu Oracle JDBC. |

Chỉ riêng việc driver hỗ trợ `CallableStatement` không bảo đảm mọi kiểu routine, overload, kiểu OUT hay control transaction có hành vi giống nhau. Nếu một cuộc gọi không chạy dù routine tồn tại, cần kiểm tra **schema, quyền EXECUTE, chữ ký, cấu hình escape của driver và kiểu SQL của từng tham số**.

### Parameter metadata và overload

`CallableStatement.getParameterMetaData()` có thể hỗ trợ điều tra số lượng/kiểu tham số, nhưng không phải driver nào cũng trả metadata đầy đủ cho procedure/function có overload, kiểu DBMS đặc biệt hoặc OUT. Hãy duy trì một **hợp đồng routine đã được version hóa** ở code và kiểm thử tích hợp.

Nếu DBMS có nhiều overload cùng tên, tham số `NULL` hoặc kiểu không rõ có thể khiến nó chọn sai routine. Dùng `setNull(index, Types.XXX)` và `setXxx`/`setObject` phù hợp; cân nhắc tên routine và kiểu SQL rõ ràng ở ranh giới Java.

### Tham số theo tên

Một số overload API JDBC cho phép thao tác OUT theo tên tham số. Hỗ trợ theo tên phụ thuộc driver và ngữ nghĩa procedure/function ở database. Khi mục tiêu là ví dụ dễ di chuyển giữa các hệ quản trị, **định danh tham số bằng index** và ghi rõ signature theo thứ tự là cách an toàn, dễ kiểm tra.

## 10. Transaction khi gọi procedure có tác dụng ghi

Nhiều procedure làm thay đổi nhiều bảng. Trong JDBC, transaction được quản lý thông qua `Connection`. Đối với routine tham gia transaction của connection, có thể điều phối nó cùng SQL Java khác:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (CallableStatement call = connection.prepareCall(
                "{call billing.apply_payment(?, ?)}")) {

            call.setLong(1, invoiceId);
            call.setBigDecimal(2, paymentAmount);
            call.execute();
        }

        // Có thể gọi các câu SQL khác trên cùng connection.
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
~~~

Ví dụ giả định procedure `billing.apply_payment` nhận hai input và không tạo result set/update count cần xử lý thêm. Mã chạy trong một phương thức đã có `dataSource`, `invoiceId` và `paymentAmount`.

Điểm quan trọng:

- **Service/tầng giao dịch** sở hữu `commit()` và `rollback()` cho toàn bộ công việc cần nguyên tử, còn mapper/repository con không tự commit nếu được truyền connection của caller.
- Khi `autoCommit=true`, mỗi statement có ngữ nghĩa commit riêng theo JDBC/DBMS. Đừng giả định một procedure mặc nhiên là giao dịch độc lập.
- Một số DBMS cho routine thực hiện điều khiển transaction hoặc có cơ chế *autonomous transaction*; một số DBMS lại giới hạn `COMMIT` bên trong procedure, đặc biệt khi được gọi trong transaction ngoài. Cần kiểm tra hợp đồng routine.
- Nếu `execute()` lỗi, phải xem transaction còn có thể tiếp tục không. Khi chưa phân loại được lỗi, phương án an toàn thường là rollback toàn bộ transaction và báo lỗi.
- Nếu kết nối mất đúng lúc `commit()`, kết quả có thể bất định. Không retry mù một thao tác chuyển tiền/thanh toán; dùng idempotency và đối soát.
- Các tác động ngoài database (HTTP, email, gửi message) không nhất thiết được rollback cùng JDBC transaction.

Nếu dùng connection pool, lớp quản lý connection phải khôi phục auto-commit/isolation phù hợp khi trả connection. Không thay đổi auto-commit của một transaction đang hoạt động mà không hiểu hệ quả commit ngầm theo JDBC.

## 11. Bảo mật và xử lý lỗi

`CallableStatement` sử dụng dấu `?` để bind **giá trị** tham số, giảm rủi ro SQL injection so với ghép chuỗi:

~~~java
String sql = "{call security.find_user(?, ?)}";

try (CallableStatement call = connection.prepareCall(sql)) {
    call.setString(1, userInput);
    call.registerOutParameter(2, Types.INTEGER);
    call.execute();
}
~~~

Không viết:

~~~java
// Sai: đưa dữ liệu từ request trực tiếp vào câu SQL.
String unsafe = "{call security.find_user('" + userInput + "', ?)}";
~~~

**Không thể dùng `?` để bind tên procedure, schema hoặc tên cột.** Nếu ứng dụng phải chọn routine động, ánh xạ lựa chọn vào một tập tên cố định được khai báo trong code thay vì nối tên tùy ý từ request.

Routine vẫn cần được đánh giá về SQL động bên trong, quyền truy cập và tác dụng phụ. Tài khoản database chỉ nên có quyền phù hợp với nghiệp vụ; chú ý cơ chế thực thi theo quyền owner/definer/invoker của từng DBMS.

Khi ghi log, nên có **mã thao tác, tên logic routine được cho phép, trace ID, SQLState và loại lỗi**. Tránh log giá trị tham số, `CallableStatement.toString()`, toàn bộ bản ghi, thông điệp driver chứa dữ liệu nhạy cảm hoặc connection string có mật khẩu. Lỗi SQL chi tiết có thể được xử lý trong kênh nội bộ được kiểm soát nhưng không đưa nguyên văn tới client.

| Triệu chứng | Nguyên nhân có thể gặp | Cách sửa |
| --- | --- | --- |
| Sai vị trí tham số | Bắt đầu từ 0 hoặc quên return `?` | Đếm tất cả `?`, áp dụng index từ 1 |
| Báo chưa đăng ký OUT | Thiếu `registerOutParameter` | Đăng ký OUT/return trước execute |
| Báo input chưa gán | Thiếu `setXxx` cho IN/INOUT | Gán kiểu, vị trí đúng |
| `execute()` trả false | Kết quả đầu tiên không phải result set | Kiểm tra update count và OUT |
| OUT không đọc được | Chưa tiêu thụ result set, driver có yêu cầu riêng | Đọc hết các kết quả trước OUT |
| Getter số trả 0 thay vì NULL | Quên `wasNull()` | Gọi ngay sau getter primitive |
| Function không gọi được qua escape | Driver/dialect không hỗ trợ cơ chế đó | Xem tài liệu driver; cân nhắc `SELECT` tham số hóa |
| Procedure không tìm thấy | Sai schema, quyền, chữ ký hoặc overload | Kiểm tra schema/search path, EXECUTE và kiểu tham số |
| Decimal bị mất chữ số | Dùng double hoặc scale không phù hợp | Dùng BigDecimal và kiểm tra hợp đồng SQL |
| ResultSet đóng sớm | Gọi `getMoreResults` khi chưa đọc xong | Tiêu thụ/đóng ResultSet rồi chuyển kết quả |

## 12. Kiểm thử tích hợp và checklist

Routine nằm trong database nên cần **kiểm thử tích hợp với driver và DBMS thật**. Mock `CallableStatement` không thể phản ánh đầy đủ cơ chế escape, overload, OUT, cursor hoặc cách phát sinh result set/update count.

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Procedure chỉ có IN | Nhận đúng giá trị, thao tác đúng |
| Procedure có OUT INTEGER | Register type và lấy OUT đúng |
| Procedure có INOUT | Gán input và đăng ký OUT tại cùng vị trí |
| Function scalar | Return tại index 1, input bắt đầu index 2 |
| OUT/return là NULL | Getter object hoặc `wasNull()` xử lý đúng |
| OUT DECIMAL | BigDecimal giữ chính xác và scale phù hợp |
| Procedure có result set | Đọc đủ dòng, đóng tài nguyên |
| Procedure có nhiều result set/update count | Vòng `getMoreResults` không bỏ sót kết quả |
| Routine sai tên hoặc sai quyền | Báo lỗi có kiểm soát, không lộ tham số nhạy cảm |
| Routine ghi dữ liệu trong transaction | Commit và rollback đúng theo DBMS |
| Signature routine thay đổi | Test phát hiện lệch thứ tự/kiểu tham số |
| Thay driver hoặc phiên bản DBMS | Kiểm chứng lại escape, OUT, metadata và lỗi |

Checklist rà soát trước khi đưa code vào hệ thống:

1. Xác định routine là **procedure** hay **function**, có cần cú pháp escape đặc biệt không.
2. Ghi rõ schema, tên, số lượng, hướng và kiểu SQL của từng tham số.
3. Đối với function, dành index 1 cho return và đặt input bắt đầu từ index 2.
4. Đăng ký toàn bộ OUT/INOUT/return trước `execute()`.
5. Dùng `setNull` với SQL type rõ ràng khi truyền `NULL`.
6. Biết routine trả result set, update count, OUT hay nhiều loại kết quả kết hợp.
7. Đọc hết các kết quả trước khi lấy OUT nếu driver yêu cầu.
8. Quản lý `Connection`, `CallableStatement`, `ResultSet` bằng try-with-resources và transaction có chủ sở hữu rõ.
9. Dùng tham số hóa, quyền tối thiểu, không ghi log dữ liệu nhạy cảm.
10. Có integration test trên đúng database/driver được triển khai.

## 13. Bài tập tự luyện

### Bài 1 — Chọn cú pháp

Cho hai routine logic:

~~~text
shipping.create_label(IN order_id BIGINT, OUT label_id BIGINT)
pricing.discounted_price(IN original DECIMAL, IN rate DECIMAL)
    RETURNS DECIMAL
~~~

Hãy viết JDBC escape tương ứng và liệt kê vị trí return/input.

**Gợi ý:** Procedure là `{call shipping.create_label(?, ?)}` với OUT ở 2. Function là `{? = call pricing.discounted_price(?, ?)}`, return ở 1, input ở 2 và 3.

### Bài 2 — Sửa index

~~~java
CallableStatement call =
        connection.prepareCall("{? = call math.add_values(?, ?)}");
call.setInt(1, 7);
call.setInt(2, 5);
call.registerOutParameter(3, Types.INTEGER);
call.execute();
~~~

Hãy sửa ba câu thao tác tham số để trả được tổng.

**Gợi ý:** `registerOutParameter(1, Types.INTEGER)`; `setInt(2, 7)`; `setInt(3, 5)`; sau execute đọc `getInt(1)`.

### Bài 3 — Kiểm tra `INOUT`

Một procedure nhận `INOUT quantity INTEGER`. Nếu Java chỉ gọi `setInt(1, 10)` rồi `getInt(1)`, còn thiếu gì?

**Gợi ý:** Cần `registerOutParameter(1, Types.INTEGER)` trước execute. Nếu kết quả có thể NULL thì gọi `wasNull()` sau `getInt(1)`.

### Bài 4 — Phân biệt OUT và result set

Procedure dùng `SELECT` để trả nhiều dòng hóa đơn, đồng thời trả `OUT total INTEGER`. Trên driver yêu cầu đọc hết kết quả trước OUT, trình tự nào là đúng?

**Gợi ý:** `execute()`, duyệt mọi result set và update count qua `getMoreResults()`/`getUpdateCount()`, sau đó mới đọc `getInt`/`wasNull` của OUT.

### Bài 5 — Transaction

Một service phải gọi procedure ghi thanh toán và sau đó ghi bản ghi đối soát. Vì sao hai repository mở connection riêng và tự commit có thể làm sai nghiệp vụ?

**Gợi ý:** Hai transaction commit độc lập không bảo đảm nguyên tử. Khi DBMS/routine cho phép, service sở hữu một connection, tắt auto-commit, thực thi cả hai thao tác và commit một lần hoặc rollback toàn bộ khi lỗi.

---

**Ghi nhớ:** Với JDBC, procedure thường dùng `{call name(...)}`, còn function có scalar return có thể dùng `{? = call name(...)}` với return ở **index 1**. `CallableStatement` xử lý `IN/OUT/INOUT` và các loại kết quả; còn cách routine được tạo, ánh xạ function, nhiều result set và ranh giới transaction cần xác minh trên **DBMS và driver thực tế**.

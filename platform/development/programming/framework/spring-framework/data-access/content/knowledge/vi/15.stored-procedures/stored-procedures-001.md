# `CallableStatement` và nhu cầu gọi mã trong cơ sở dữ liệu

Trong Spring Framework Data Access, phần lớn thao tác đọc/ghi thông thường có thể thực hiện bằng `JdbcTemplate.query(...)`, `update(...)` hoặc JDBC `PreparedStatement`. Tuy nhiên, một hệ thống cũng có thể đặt **mã thực thi bên trong cơ sở dữ liệu** dưới dạng *stored procedure* (thủ tục lưu trữ) và *stored function* (hàm lưu trữ). Khi ứng dụng Java cần gọi những đối tượng này, JDBC cung cấp `java.sql.CallableStatement`; Spring JDBC cung cấp các lớp tiện ích như `SimpleJdbcCall` để giảm mã lặp.

Mục tiêu của bài: hiểu **khi nào cần gọi mã trong database**, procedure/function khác câu SQL thông thường thế nào, cách truyền/nhận tham số `IN`/`OUT`/`INOUT`, đọc kết quả và tích hợp lời gọi đó vào ứng dụng Spring mà vẫn quản lý connection, transaction và lỗi đúng cách.

## 1. Vì sao ứng dụng cần gọi mã đã lưu trong database?

Giả sử một hệ thống có logic tổng hợp doanh thu theo khách hàng. Có ba cách tổ chức thường gặp:

1. Java gửi `SELECT SUM(amount) ...` trực tiếp bằng `PreparedStatement`/`JdbcTemplate`.
2. Database đã định nghĩa `get_customer_total(customer_id, total OUT)`; Java gọi procedure này để nhận giá trị.
3. Database đã định nghĩa một function `with_ten_percent_fee(amount)`; Java dùng kết quả function trong câu `SELECT`, hoặc gọi qua API dành cho function.

Việc đóng gói logic dưới dạng routine có thể phù hợp khi:

- **Nhiều ứng dụng cùng cần quy tắc xử lý dữ liệu** và database là nơi quản lý tập trung quy tắc đó.
- **Hệ thống có sẵn procedure/function** (ví dụ hệ thống lâu năm hoặc cơ sở dữ liệu tích hợp với phần mềm bên ngoài) mà ứng dụng bắt buộc phải sử dụng.
- **Một nghiệp vụ liên quan nhiều câu SQL** có thể được thực thi tại database, giảm một số lượt trao đổi giữa client và server khi thiết kế phù hợp.
- **Quyền truy cập được cấp theo routine**: tài khoản ứng dụng có thể được cho phép gọi một procedure thay vì được quyền thao tác trực tiếp với tất cả bảng bên dưới, tùy cấu hình quyền và chế độ thực thi của RDBMS.

Đó là những khả năng có ích, **không phải lý do mặc định để đưa mọi nghiệp vụ vào stored procedure**. Cách làm này có thể tăng phụ thuộc vào hệ quản trị, gây khó khăn khi version/migration, kiểm thử và theo dõi mã; procedure chạy ở database cũng tiêu thụ tài nguyên database. Một lệnh `SELECT` hay `UPDATE` đơn giản thường không cần routine.

### Procedure, function và câu SQL khác nhau thế nào?

| Hình thức | Mục đích chính | Đầu vào/đầu ra điển hình | Cách gọi thường thấy |
| --- | --- | --- | --- |
| SQL trực tiếp | Đọc/ghi dữ liệu với câu lệnh cụ thể | `ResultSet`, affected-row count | `PreparedStatement` hoặc `JdbcTemplate` |
| Stored procedure | Thực hiện một chuỗi thao tác được định nghĩa trong DB | `IN`, `OUT`, `INOUT`; có thể có result set/update count | `CALL ...`, JDBC `{call ...}` |
| Stored function | Tính một giá trị và trả về cho biểu thức gọi | Đối số đầu vào và một giá trị `RETURN` | `SELECT function(...)` hoặc JDBC `{? = call ...}` khi driver hỗ trợ |

Cú pháp định nghĩa routine và những điều routine được phép làm **khác nhau giữa MySQL, PostgreSQL, SQL Server, Oracle…**. Bài này dùng **MySQL 8.4** để có ví dụ SQL và đầu ra cụ thể; phần `CallableStatement` là API JDBC chung, nhưng tính tương thích của driver và SQL cần được kiểm tra trên hệ quản trị thực tế.

## 2. Cơ chế của `CallableStatement` trong JDBC

`CallableStatement` là interface thuộc `java.sql` và **kế thừa `PreparedStatement`**. Do đó nó có các phương thức gắn tham số như `setInt`, `setLong`, `setString` và được bổ sung các phương thức khai báo/đọc tham số đầu ra như `registerOutParameter`, `getInt`, `getBigDecimal`.

Một lời gọi điển hình:

```text
Mã Java / Spring
    |
    | Connection.prepareCall("{call ...}")
    | setXxx(IN), registerOutParameter(OUT), execute()
    v
JDBC driver (chuyển cú pháp escape sang giao thức DB phù hợp)
    |
    v
Stored procedure / function trên database
    |
    | kết quả, OUT parameters, result sets, update counts hoặc lỗi
    v
CallableStatement -> mã Java đọc kết quả
```

Hai dạng *JDBC escape syntax* phổ biến:

```java
// Gọi procedure có hai tham số; đây là chuỗi SQL, không phải Java hoàn chỉnh.
"{call get_customer_total(?, ?)}"

// Gọi function có một đối số và một return value.
"{? = call with_ten_percent_fee(?)}"
```

- `?` là vị trí tham số, được đánh số **bắt đầu từ 1**.
- Với procedure `get_customer_total`, vị trí 1 là `IN`, vị trí 2 là `OUT`.
- Với function theo cú pháp `{? = call ...}`, **vị trí 1 là giá trị trả về**, còn đối số của function bắt đầu từ vị trí 2.
- `Connection.prepareCall(...)` tạo `CallableStatement`; JDBC driver xử lý cú pháp escape và giao tiếp với database.
- `CallableStatement.execute()` thực thi routine. Giá trị `boolean` của `execute()` báo **kết quả đầu tiên có phải `ResultSet` hay không**, không phải cờ “thành công/thất bại”. Lỗi thường được báo bằng `SQLException`.

### Ba chế độ tham số

| Chế độ | Ý nghĩa | Phương thức cần thiết |
| --- | --- | --- |
| `IN` | Java truyền giá trị vào routine | `setXxx(index, value)` |
| `OUT` | Routine trả giá trị về Java | `registerOutParameter(index, Types.XXX)`, rồi `getXxx(index)` sau khi thực thi |
| `INOUT` | Java vừa truyền giá trị ban đầu, vừa nhận giá trị cuối | **Cả** `setXxx` **và** `registerOutParameter` tại cùng vị trí, sau đó `getXxx` |

Mọi tham số `OUT`/`INOUT` (bao gồm return parameter của function khi dùng JDBC escape) phải được **register trước khi thực thi**. Chọn `Types.INTEGER`, `Types.BIGINT`, `Types.DECIMAL`, `Types.VARCHAR`... phù hợp kiểu SQL. Nếu `getInt()`, `getLong()` đọc giá trị SQL `NULL` thì Java trả `0`; gọi `wasNull()` ngay sau getter để phân biệt `NULL` với giá trị 0 thực sự. Với số tiền, dùng `BigDecimal` thay vì `double` khi cần độ chính xác thập phân.

## 3. Chuẩn bị database MySQL dùng xuyên suốt ví dụ

Ví dụ này chạy trên **MySQL 8.4**, sử dụng schema riêng `callable_demo`. Lưu toàn bộ SQL sau vào `routines.sql` rồi thực thi bằng MySQL command-line client trong môi trường học tập; cần tài khoản có quyền tạo schema, bảng và routine tương ứng. Các lệnh tạo và nạp dữ liệu minh họa được thiết kế cho lần chạy đầu trên schema mới.

```sql
CREATE DATABASE IF NOT EXISTS callable_demo;
USE callable_demo;

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    amount DECIMAL(12, 2) NOT NULL
);

INSERT INTO orders (id, customer_id, amount) VALUES
    (1, 42, 100.50),
    (2, 42, 50.00),
    (3, 99, 25.00);

DELIMITER //

CREATE PROCEDURE get_customer_total(
    IN p_customer_id BIGINT,
    OUT p_total DECIMAL(12, 2)
)
BEGIN
    SELECT COALESCE(SUM(amount), 0.00)
      INTO p_total
      FROM orders
     WHERE customer_id = p_customer_id;
END//

CREATE PROCEDURE increment_number(INOUT p_number INT)
BEGIN
    SET p_number = p_number + 1;
END//

CREATE FUNCTION with_ten_percent_fee(p_amount DECIMAL(12, 2))
RETURNS DECIMAL(12, 2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_amount * 1.10, 2)//

DELIMITER ;
```

**Giải thích:**

- `get_customer_total` nhận `p_customer_id` (`IN`), tính tổng `amount`, gán vào `p_total` (`OUT`). Khách không có đơn được tổng `0.00` nhờ `COALESCE`.
- `increment_number` dùng `INOUT`: nhận một số rồi tăng số đó lên 1, trả lại qua cùng tham số.
- `with_ten_percent_fee` là function trả một giá trị: tăng số tiền thêm **10% phí giả định cho ví dụ**, làm tròn hai chữ số thập phân. Hàm chỉ tính toán từ tham số nên khai báo `DETERMINISTIC NO SQL`.
- `DELIMITER //` và `DELIMITER ;` là **lệnh của MySQL client** để gửi nguyên khối `CREATE ... BEGIN ... END`; đây không phải câu SQL để gửi nguyên văn qua `PreparedStatement`.
- MySQL stored function nhận đối số đầu vào và `RETURN` một giá trị; `OUT` và `INOUT` trong ví dụ thuộc về **procedure**. Một số RDBMS có quy tắc khác.
- Dữ liệu thử nghiệm: khách hàng `42` có hai đơn `100.50` và `50.00`; tổng bằng `150.50`.

Có thể tự kiểm tra routine từ MySQL client:

```sql
CALL get_customer_total(42, @total);
SELECT @total;
SET @counter = 7;
CALL increment_number(@counter);
SELECT @counter;
SELECT with_ten_percent_fee(150.50) AS total_with_fee;
```

Các giá trị kỳ vọng lần lượt là `150.50`, `8` và `165.55`. Cách truyền **session variable** như `@total` và `@counter` là cú pháp MySQL client; bên Java ta sẽ dùng `registerOutParameter` của JDBC.

## 4. Ví dụ Java 17: gọi procedure có IN/OUT, INOUT và function

Đây là **chương trình Java độc lập có thể biên dịch bằng JDK 17+**, sử dụng API JDBC chuẩn. Để chạy thực tế cần MySQL đang chạy, schema/routines ở mục 3, MySQL Connector/J trên runtime classpath và ba biến môi trường `JDBC_URL`, `JDBC_USER`, `JDBC_PASSWORD` đúng với cơ sở dữ liệu. Lưu chương trình trong file **`CallableStatementDemo.java`**:

```java
import java.math.BigDecimal;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Types;

public final class CallableStatementDemo {
    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null) {
            throw new IllegalStateException("Missing environment variable: " + name);
        }
        return value;
    }

    public static void main(String[] args) throws SQLException {
        String url = requiredEnv("JDBC_URL");
        String user = requiredEnv("JDBC_USER");
        String password = requiredEnv("JDBC_PASSWORD");

        try (Connection connection =
                     DriverManager.getConnection(url, user, password)) {

            BigDecimal total;
            try (CallableStatement call = connection.prepareCall(
                    "{call get_customer_total(?, ?)}")) {
                call.setLong(1, 42L);                         // IN
                call.registerOutParameter(2, Types.DECIMAL); // OUT
                call.execute();
                total = call.getBigDecimal(2);
            }
            System.out.println("customerTotal=" + total.toPlainString());

            try (CallableStatement call = connection.prepareCall(
                    "{? = call with_ten_percent_fee(?)}")) {
                call.registerOutParameter(1, Types.DECIMAL); // RETURN
                call.setBigDecimal(2, total);                 // IN
                call.execute();
                BigDecimal feeTotal = call.getBigDecimal(1);
                System.out.println("totalWithFee=" + feeTotal.toPlainString());
            }

            try (CallableStatement call = connection.prepareCall(
                    "{call increment_number(?)}")) {
                call.setInt(1, 7);                            // IN
                call.registerOutParameter(1, Types.INTEGER);   // OUT
                call.execute();
                int nextValue = call.getInt(1);
                System.out.println("incremented=" + nextValue);
            }
        }
    }
}
```

Chương trình dùng `try-with-resources` để đóng từng `CallableStatement` và `Connection` ngay cả khi xảy ra ngoại lệ. `DriverManager` tìm JDBC driver đã được thêm vào classpath theo cơ chế đăng ký driver chuẩn; mã trên không phụ thuộc lớp MySQL cụ thể lúc biên dịch.

**Biên dịch:** đặt `CallableStatementDemo.java` trong thư mục làm việc, dùng JDK 17+:

```bash
javac -encoding UTF-8 CallableStatementDemo.java
```

**Chạy:** tải MySQL Connector/J (ví dụ bản `8.4.0`), đặt file `mysql-connector-j-8.4.0.jar` cạnh file `.class`; cấu hình biến môi trường bằng URL dạng `jdbc:mysql://127.0.0.1:3306/callable_demo` và tài khoản MySQL có quyền `EXECUTE` trên các routines. Trên Linux/macOS:

```bash
java -cp ".:mysql-connector-j-8.4.0.jar" CallableStatementDemo
```

Trên Windows PowerShell:

```powershell
java -cp ".;mysql-connector-j-8.4.0.jar" CallableStatementDemo
```

Kết quả trên dữ liệu và routines đã tạo:

```text
customerTotal=150.50
totalWithFee=165.55
incremented=8
```

Điểm cần kiểm tra từng bước:

1. Khi gọi `get_customer_total`, `setLong(1, 42L)` gắn ID; `registerOutParameter(2, Types.DECIMAL)` khai báo giá trị lấy về; `getBigDecimal(2)` đọc tổng sau khi `execute()`.
2. Khi gọi **function**, dấu `?` đứng **trước** dấu `=` là return value ở vị trí 1. Vì thế đầu vào `BigDecimal` được gắn vào vị trí **2**, và kết quả đọc từ vị trí **1**.
3. Với `INOUT`, vị trí **1** vừa nhận `7` qua `setInt`, vừa được khai báo output qua `registerOutParameter`; sau khi gọi trả `8`.
4. `getBigDecimal` có thể trả `null` khi SQL output là `NULL`. Trong dữ liệu ví dụ, `get_customer_total` dùng `COALESCE` nên trả số khác null. Ứng dụng thực tế phải định nghĩa rõ cách xử lý output null.
5. Việc `execute()` trả `false` ở một routine không sinh `ResultSet` **không phải bằng chứng routine bị lỗi**. Chỉ dựa vào output/exception và loại kết quả phù hợp.

## 5. Kết quả routine có thể nhiều hơn một OUT parameter

`CallableStatement` có thể gặp các dạng output sau, tùy routine và RDBMS:

- **Tham số OUT/INOUT:** lấy bằng `getXxx(index)` sau khi execute, chẳng hạn một tổng tiền hoặc mã trạng thái.
- **Giá trị RETURN từ function:** đăng ký và lấy ở vị trí thích hợp, với JDBC escape thông thường là vị trí 1.
- **Một hoặc nhiều ResultSet:** nếu procedure trả các bảng kết quả bằng `SELECT` (như trên MySQL), dùng `getResultSet()`, `getMoreResults()`.
- **Update count:** khi các lệnh thao tác dữ liệu cho biết số hàng chịu tác động, dùng `getUpdateCount()`.

Ví dụ sau là **một phương thức Java có thể thêm vào một lớp JDBC**, dùng khi procedure sinh một hoặc nhiều `ResultSet`/update count. Truyền vào một `CallableStatement` đã khai báo input và output nhưng **chưa gọi `execute()`**:

```java
static void printAllResults(CallableStatement call) throws SQLException {
    boolean hasResultSet = call.execute();

    while (true) {
        if (hasResultSet) {
            try (java.sql.ResultSet rs = call.getResultSet()) {
                while (rs.next()) {
                    System.out.println("firstColumn=" + rs.getObject(1));
                }
            }
        } else {
            int updateCount = call.getUpdateCount();
            if (updateCount == -1) {
                break; // Không còn ResultSet hoặc update count.
            }
            System.out.println("updateCount=" + updateCount);
        }
        hasResultSet = call.getMoreResults();
    }
}
```

Phương thức trên in cột đầu tiên trong các result set (đối với result set có ít nhất một cột). Đây là **công cụ quan sát kết quả**, không phải cách mapping DTO cho ứng dụng nghiệp vụ. Khi muốn mapping hàng dữ liệu, hãy đọc các cột và kiểu tương ứng. Với output parameters, JDBC khuyến nghị xử lý result set/update count trước khi lấy OUT để đạt tính di động tốt hơn. Một số driver cung cấp cơ chế trả cursor/REF_CURSOR qua output parameter; cách đăng ký và giải phóng tài nguyên phụ thuộc driver và loại cơ sở dữ liệu.

### Khi nào dùng `executeQuery`, `executeUpdate`, `execute`?

- `executeQuery()` phù hợp câu lệnh chỉ trả một `ResultSet` theo hợp đồng đã biết.
- `executeUpdate()` phù hợp lệnh thao tác dữ liệu có update count theo hợp đồng đã biết.
- **`execute()` là lựa chọn linh hoạt cho `CallableStatement`**, nhất là khi chưa biết routine sinh `ResultSet`, update count hay nhiều loại kết quả. Sau đó dùng các API đọc kết quả tương ứng.

Không nhầm **procedure thành công** với `execute() == true`; `true` chỉ nói rằng **kết quả đầu tiên là `ResultSet`**.

## 6. Từ JDBC thuần đến Spring JDBC

Trong một ứng dụng Spring sử dụng `spring-jdbc` và đã cấu hình `DataSource`, hai hướng chính là:

1. Dùng `JdbcTemplate.execute(CallableStatementCreator, CallableStatementCallback)` khi cần kiểm soát trực tiếp các bước `prepareCall`, gắn tham số, đọc kết quả phức tạp.
2. Dùng `SimpleJdbcCall` khi muốn một lớp gọi procedure/function rõ tên, khai báo mapping input/output và để Spring quản lý mã JDBC lặp.

### 6.1. Gọi procedure qua `SimpleJdbcCall`

Lớp sau là **thành phần Spring**; đặt vào dự án đã có `JdbcTemplate`, `spring-jdbc` và MySQL driver. Nó gọi đúng routine `get_customer_total` trong mục 3.

```java
import java.math.BigDecimal;
import java.sql.Types;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerRoutineRepository {
    private final SimpleJdbcCall totalCall;
    private final SimpleJdbcCall feeCall;

    public CustomerRoutineRepository(JdbcTemplate jdbcTemplate) {
        this.totalCall = new SimpleJdbcCall(jdbcTemplate)
                .withProcedureName("get_customer_total")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("p_customer_id", Types.BIGINT),
                        new SqlOutParameter("p_total", Types.DECIMAL));

        this.feeCall = new SimpleJdbcCall(jdbcTemplate)
                .withFunctionName("with_ten_percent_fee");
    }

    public BigDecimal customerTotal(long customerId) {
        Map<String, Object> output = totalCall.execute(
                new MapSqlParameterSource("p_customer_id", customerId));
        return (BigDecimal) output.get("p_total");
    }

    public BigDecimal totalWithFee(BigDecimal amount) {
        return feeCall.executeFunction(
                BigDecimal.class,
                new MapSqlParameterSource("p_amount", amount));
    }
}
```

Giải thích:

- `totalCall` được **cấu hình một lần** trong constructor, không dựng lại mỗi lần gọi.
- `withoutProcedureColumnMetaDataAccess()` yêu cầu Spring không tự hỏi database về metadata của procedure; vì vậy phải khai báo đủ tham số qua `declareParameters(...)`. Cách này hữu ích khi driver metadata không ổn định hoặc quyền truy cập metadata bị giới hạn.
- `SqlParameter` mô tả `IN`; `SqlOutParameter` mô tả `OUT`; trường hợp `INOUT` có `SqlInOutParameter`.
- `execute(...)` trả `Map` chứa output với key là tên output. Cách viết `output.get("p_total")` giả định tên kết quả khớp khai báo. Với routine dựa trên metadata, tên chữ hoa/thường có thể khác theo database/driver.
- `feeCall.withFunctionName(...)` cấu hình **function**; `executeFunction(BigDecimal.class, ...)` trả trực tiếp một `BigDecimal`. Ở đây Spring sử dụng metadata function từ MySQL. Nếu metadata thiếu hoặc khác mong đợi, cần khai báo tham số/điều chỉnh cấu hình phù hợp driver.

`SimpleJdbcCall` không có nghĩa là procedure được biên dịch thành mã Java. Logic vẫn thực thi ở database; Spring lo phần kết nối, bind tham số, giải mã output và chuyển lỗi JDBC thành hệ thống `DataAccessException`.

### 6.2. Gọi qua `JdbcTemplate` khi cần `CallableStatement` trực tiếp

Đoạn sau minh họa **một method bên trong lớp có trường `JdbcTemplate jdbcTemplate`**; không phải file Java độc lập:

```java
public BigDecimal readTotalWithJdbcTemplate(long customerId) {
    return jdbcTemplate.execute(
            connection -> {
                CallableStatement call = connection.prepareCall(
                        "{call get_customer_total(?, ?)}");
                call.setLong(1, customerId);
                call.registerOutParameter(2, Types.DECIMAL);
                return call;
            },
            (org.springframework.jdbc.core.CallableStatementCallback<BigDecimal>) call -> {
                call.execute();
                return call.getBigDecimal(2);
            });
}
```

Cần import `java.math.BigDecimal`, `java.sql.CallableStatement`, `java.sql.Types` và có sẵn trường `JdbcTemplate`. `JdbcTemplate` lấy/giải phóng JDBC connection và statement theo cơ chế Spring, xử lý `SQLException` thành `DataAccessException`; khi dùng đúng `DataSource` với transaction manager, kết nối được tích hợp vào transaction đang hoạt động.

**Không mở một `DriverManager.getConnection(...)` mới bên trong một service Spring đã có `@Transactional`** rồi mặc định nó tham gia transaction của Spring. Cần để `JdbcTemplate`/`DataSourceUtils` dùng chính `DataSource` và transaction manager được cấu hình.

## 7. Transaction và quyền: routine chạy ở đâu?

Gọi procedure qua JDBC không tự tạo ranh giới giao dịch riêng. Với phần lớn thao tác DML, transaction vẫn phụ thuộc vào connection, chế độ auto-commit, cấu hình RDBMS và transaction manager.

Ví dụ tại Spring service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerReportService {
    private final CustomerRoutineRepository repository;

    public CustomerReportService(CustomerRoutineRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public BigDecimal readCustomerTotal(long customerId) {
        return repository.customerTotal(customerId);
    }
}
```

Đây là đoạn **class chạy trong dự án Spring** với repository ở trên và transaction manager phù hợp. `@Transactional(readOnly = true)` báo ý định chỉ đọc, có thể giúp framework/driver tối ưu; nó **không phải lớp bảo vệ tuyệt đối** ngăn mọi stored procedure ghi dữ liệu trên mọi hệ quản trị. Routine trong ví dụ chỉ đọc. Với routine có ghi dữ liệu, chọn transaction thích hợp và thiết kế rollback/exception rõ ràng.

Các lưu ý thực tế:

- MySQL **stored procedure có thể chứa lệnh điều khiển transaction** trong những điều kiện được hỗ trợ; lệnh `COMMIT`/DDL bên trong routine có thể ảnh hưởng cách rollback của lời gọi bên ngoài. Không mặc định `@Transactional` sẽ hoàn tác một phần đã được database commit độc lập.
- Stored function của MySQL bị giới hạn hơn procedure về transaction và result set. Chức năng hỗ trợ thay đổi theo RDBMS.
- Cần quyền **`EXECUTE`** để gọi routine, ngoài các quyền cần thiết cho kết nối và tùy chế độ bảo mật như `SQL SECURITY DEFINER`/`INVOKER`. Không cấp quá rộng quyền database chỉ để làm cho lời gọi chạy.
- Khi Spring bắt được `DataAccessException`, hãy xem lỗi gốc/`SQLState`/vendor error code để hiểu lỗi thiếu quyền, routine không tồn tại, kiểu tham số sai, deadlock hay lỗi nghiệp vụ.

## 8. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Gọi `{call ...}` nhưng driver báo không tìm thấy routine | Nhầm schema, tên routine, quyền `EXECUTE` hoặc kết nối nhầm DB | Xác nhận JDBC URL, schema, `SHOW PROCEDURE STATUS`/metadata, quyền |
| Lỗi “OUT parameter not registered” | Thiếu `registerOutParameter` trước `execute()` | Khai báo đúng vị trí và `Types` |
| Nhận nhầm output ở function | Quên return parameter chiếm vị trí 1 trong `{? = call function(?)}` | Vẽ sơ đồ index rồi gắn/đọc đúng vị trí |
| `getInt()` trả 0 nhưng dữ liệu có thể null | Getter số nguyên dùng primitive | Gọi `wasNull()` ngay sau getter |
| `execute()` trả `false` và bị coi là lỗi | Nhầm boolean kết quả đầu tiên với trạng thái thành công | Kiểm tra `SQLException`, OUT, `getUpdateCount()` theo hợp đồng |
| Procedure trả nhiều result set nhưng mất dữ liệu | Chỉ đọc một result set rồi đóng statement | Lặp qua `getMoreResults()` và kiểm tra update counts |
| Spring không map đúng output | Khác tên/chữ hoa thường hoặc driver metadata không đủ | Cấu hình `SimpleJdbcCall` bằng tham số khai báo tường minh, kiểm tra output key |
| Bị lỗi transaction hoặc khó rollback | Routine tự commit, DDL có implicit commit, hoặc connection ở ngoài Spring transaction | Xem mã routine, cấu hình transaction manager và ranh giới kết nối |
| Chạy chậm dù đã dùng procedure | SQL bên trong routine chưa tối ưu; nhiều lần `prepareCall`/metadata round trip | Đo query plan, I/O, thời gian DB/ứng dụng; cấu hình/reuse call phù hợp |

### Kiểm thử có giá trị

- **Input hợp lệ:** với `customerId = 42`, tổng là `150.50`; `with_ten_percent_fee` trả `165.55`; `increment_number(7)` trả `8`.
- **Input không có dữ liệu:** `get_customer_total(12345)` trả `0.00` vì `COALESCE`, khác với procedure có thể trả `NULL`.
- **INOUT:** kiểm tra giá trị trước và sau, gồm trường hợp 0 hay giá trị âm nếu routine cho phép.
- **OUT NULL:** thử trên một routine thật sự có thể trả `NULL`; xác nhận getter kiểu object hoặc `wasNull()` xử lý đúng.
- **Thiếu quyền/sai tên routine:** kiểm tra lỗi được ghi nhận và Spring chuyển ngoại lệ phù hợp.
- **Transaction:** với routine có DML, thực nghiệm commit/rollback trên chính RDBMS/driver môi trường triển khai, kiểm tra các hiệu ứng phụ có được rollback như hợp đồng mong đợi.
- **Metadata:** kiểm thử lại `SimpleJdbcCall` khi đổi phiên bản driver, đổi tên tham số hoặc thay schema.

Unit test chỉ mock `CallableStatement` có thể kiểm tra thứ tự `set`, `register`, `execute`, `get`; integration test với database mới cho biết routine thực thi và trả giá trị thế nào.

## 9. Những kết luận dễ nhầm

**“`CallableStatement` là cách nhanh hơn của `PreparedStatement`?”** Không. Đây là interface phù hợp để **gọi stored procedures/functions** và trao đổi tham số đầu ra. Tốc độ phụ thuộc SQL, driver, network, kế hoạch thực thi và cách thiết kế routine.

**“Function bắt buộc phải gọi qua `CallableStatement`?”** Không. Trên MySQL, function có thể dùng trong SQL expression, ví dụ `SELECT with_ten_percent_fee(?)` với `PreparedStatement`. `CallableStatement` hữu ích khi muốn sử dụng dạng JDBC callable và nhận return parameter theo API chung, nếu driver hỗ trợ.

**“Procedure luôn trả một `ResultSet`?”** Không. Nó có thể không trả result set nào, trả nhiều result sets, xuất ra `OUT`, hoặc cung cấp update count.

**“Dùng `SimpleJdbcCall` thì không cần hiểu JDBC nữa?”** Không. Vẫn phải hiểu tham số, kiểu SQL, metadata, tên output, transaction và cách database báo lỗi.

**“Stored procedure luôn là một transaction nguyên tử?”** Không. Batch câu lệnh trong routine, transaction, auto-commit và cơ chế lỗi là các khái niệm khác nhau; điều kiện rollback phụ thuộc từng DBMS và code routine.

**“Có thể lấy tên procedure do người dùng nhập rồi ghép thành SQL?”** Không nên. Placeholder `?` dành cho **giá trị tham số**, không thay thế tùy ý tên routine/identifier. Sử dụng danh sách routine hợp lệ do ứng dụng định nghĩa và quyền tối thiểu, thay vì ghép identifier tùy ý từ input không tin cậy.

## 10. Ghi nhớ và tài liệu chính thức

Trình tự căn bản của JDBC khi gọi procedure có output:

`prepareCall` → `setXxx(IN/INOUT)` → `registerOutParameter(OUT/INOUT)` → `execute` → xử lý result sets/update counts (nếu có) → `getXxx(OUT)` → đóng tài nguyên.

Trong Spring, `SimpleJdbcCall` phù hợp với lời gọi routine có hợp đồng tham số rõ ràng; `JdbcTemplate.execute(...)` phù hợp khi cần điều khiển kết quả JDBC chi tiết. Trước khi đưa logic vào database, hãy cân nhắc tính dùng chung, chi phí vận hành, tính di động và khả năng kiểm thử.

Tài liệu đối chiếu:

- Java SE 17 `CallableStatement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/CallableStatement.html
- Java SE 17 `Connection.prepareCall`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html
- Spring Framework, *Simplifying JDBC Operations with the SimpleJdbc Classes*: https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html
- MySQL 8.4, *CREATE PROCEDURE and CREATE FUNCTION Statements*: https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html
- MySQL Connector/J, *Using JDBC CallableStatements to Execute Stored Procedures*: https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-statements-callable.html
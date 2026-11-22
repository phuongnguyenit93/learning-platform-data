# Tham số IN, OUT và INOUT trong thủ tục và hàm của cơ sở dữ liệu

Khi ứng dụng Java gọi **stored procedure** qua Spring Framework Data Access, dữ liệu có thể đi vào thủ tục, đi ra từ thủ tục, hoặc đi theo **cả hai chiều**. Ba chế độ tham số `IN`, `OUT` và `INOUT` mô tả chính xác đường đi đó. Hiểu chế độ tham số giúp khai báo đúng SQL, truyền dữ liệu đúng qua JDBC, lấy kết quả trong Spring JDBC, tránh lỗi mất giá trị đầu vào và phân biệt kết quả của thủ tục với giá trị trả về của hàm.

Bài học dùng **MySQL 8.x** để minh họa SQL và **Java 17+ / Spring JDBC** để gọi từ ứng dụng. Cú pháp khai báo thủ tục, quy tắc hàm, cách driver xử lý tham số theo tên và kiểu dữ liệu có thể khác ở PostgreSQL, Oracle, SQL Server và các hệ quản trị khác.

## 1. Ý nghĩa ba chế độ tham số

| Chế độ | Chiều dữ liệu | Bên gọi phải cung cấp giá trị ban đầu? | Có thể đọc giá trị sau khi thủ tục chạy? | Ví dụ |
| --- | --- | --- | --- | --- |
| `IN` | Caller → Procedure | Có, trừ khi thiết kế routine/DB có cơ chế mặc định riêng | Không được trả ngược qua chính tham số này | ID đơn hàng, số tiền, bộ lọc |
| `OUT` | Procedure → Caller | Không phải cung cấp giá trị nghiệp vụ đầu vào; JDBC phải **đăng ký kiểu output** | Có, sau khi gọi thành công | Mã kết quả, tổng số, trạng thái |
| `INOUT` | Caller ↔ Procedure | Có, vừa truyền giá trị ban đầu vừa đăng ký output | Có; nhận giá trị mới được procedure gán | Bộ đếm, tổng tích lũy |

Một cách ghi nhớ:

```text
IN:     Java/SQL caller ---> [ PROCEDURE ]
OUT:    Java/SQL caller <--- [ PROCEDURE ]
INOUT:  Java/SQL caller <---> [ PROCEDURE ]
```

Ví dụ: một routine nhận `p_delta = 5` (IN), tính `p_double = 10` (OUT), và thay đổi `p_total` từ `10` thành `15` (INOUT).

**Chú ý về ngữ nghĩa:**

- `IN` là đầu vào của routine. Việc routine thay đổi biến tham số cục bộ (nếu DB cho phép) không biến tham số đó thành output cho caller.
- `OUT` là một vị trí kết quả. Trong MySQL, giá trị của tham số `OUT` ban đầu là `NULL` ở bên trong procedure; nên routine cần gán trước khi bên gọi sử dụng. Giá trị có thể vẫn là `NULL`.
- `INOUT` phải được khởi tạo từ caller; procedure đọc giá trị ban đầu và có thể gán giá trị mới. `INOUT` **không tự lưu biến trong database giữa các lần gọi**: nếu muốn dữ liệu tồn tại lâu dài, routine phải thực hiện DML hoặc caller phải lưu kết quả.
- Những chế độ này là **hợp đồng tham số SQL**; chúng không giống cơ chế truyền đối số của Java. Java vẫn truyền giá trị tham chiếu/primitive theo quy tắc *pass-by-value* của Java; JDBC truyền và nhận giá trị thông qua SQL và driver.

## 2. Ví dụ SQL chạy được: cả IN, OUT và INOUT trong một thủ tục

Thực thi đoạn SQL sau bằng **MySQL command-line client** với tài khoản có quyền tạo routine. `DELIMITER` là lệnh của công cụ `mysql` để đọc trọn phần thân có dấu `;`, **không phải câu lệnh SQL gửi trực tiếp qua JDBC**.

```sql
CREATE DATABASE IF NOT EXISTS procedure_lab;
USE procedure_lab;

DROP PROCEDURE IF EXISTS compute_points;

DELIMITER $$
CREATE PROCEDURE compute_points(
    IN p_delta INT,
    OUT p_double INT,
    INOUT p_total INT
)
BEGIN
    SET p_double = p_delta * 2;
    SET p_total = p_total + p_delta;
END$$
DELIMITER ;
```

Giải thích chữ ký `compute_points`:

1. `p_delta` là `IN`: bên gọi gửi số cần cộng; ở đây là `5`.
2. `p_double` là `OUT`: procedure đặt bằng `p_delta * 2`; bên gọi nhận `10`.
3. `p_total` là `INOUT`: nhận tổng ban đầu `10`, sau đó trả tổng mới `15`.

Gọi thủ tục bằng biến phiên `@...` trong MySQL:

```sql
SET @total = 10;
SET @double = 999;

CALL compute_points(5, @double, @total);

SELECT @double AS doubled, @total AS total;
```

Dữ liệu kết quả của câu `SELECT`:

```text
+---------+-------+
| doubled | total |
+---------+-------+
|      10 |    15 |
+---------+-------+
```

`@double` được gán lại bằng `10`. Giá trị `999` đặt trước đó chỉ để minh họa rằng `OUT` **không dùng giá trị cũ làm input**. `@total` lại bắt buộc có giá trị ban đầu vì là `INOUT`.

**Vì sao dùng biến `@double`/`@total`?** Với lời gọi `CALL` trực tiếp trong MySQL, vị trí `OUT` và `INOUT` thường nhận **user-defined variables** để có nơi lưu giá trị sau khi kết thúc. Trong JDBC, dấu `?` và cơ chế `registerOutParameter` đảm nhiệm việc này; không cần tạo biến `@...` trong Java.

### Điều gì xảy ra với NULL?

```sql
SET @total = NULL;
CALL compute_points(5, @double, @total);
SELECT @double AS doubled, @total AS total;
```

Giá trị logic trả về là `doubled = 10` và `total = NULL`, bởi `NULL + 5` vẫn là `NULL`. Nếu nghiệp vụ muốn coi tổng ban đầu chưa có là 0, phải ghi rõ chính sách đó, ví dụ `SET p_total = COALESCE(p_total, 0) + p_delta;`. **Không tự động đổi NULL thành 0 trong Java mà không hiểu ý nghĩa dữ liệu.**

## 3. JDBC CallableStatement: ánh xạ SQL sang Java

Trong JDBC, `java.sql.CallableStatement` là API cơ bản để gọi stored procedure và lấy kết quả OUT/INOUT. Với chữ ký `compute_points(IN, OUT, INOUT)`:

```java
try (CallableStatement statement =
         connection.prepareCall("{call compute_points(?, ?, ?)}")) {

    statement.setInt(1, 5);                         // IN
    statement.registerOutParameter(2, Types.INTEGER); // OUT

    statement.setInt(3, 10);                        // INOUT: input
    statement.registerOutParameter(3, Types.INTEGER); // INOUT: output

    statement.execute();

    int doubled = statement.getInt(2);
    int total = statement.getInt(3);
}
```

Đây là **đoạn mã nằm trong một phương thức đã có biến `Connection connection`**, chưa phải một chương trình Java độc lập. Điểm khác biệt quan trọng:

| Vị trí JDBC (bắt đầu từ 1) | Tham số SQL | Lệnh chuẩn bị trước `execute()` | Lệnh lấy kết quả sau `execute()` |
| --- | --- | --- | --- |
| `1` | `IN p_delta` | `setInt(1, 5)` | Không có output |
| `2` | `OUT p_double` | `registerOutParameter(2, Types.INTEGER)` | `getInt(2)` |
| `3` | `INOUT p_total` | **Cả** `setInt(3, 10)` **và** `registerOutParameter(3, Types.INTEGER)` | `getInt(3)` |

Phải đăng ký các tham số `OUT`/`INOUT` **trước khi thực thi**. Số thứ tự theo **chữ ký procedure**, không theo thứ tự gọi `set...` hay thứ tự trong một `Map`. JDBC dùng chỉ số **1-based**; Java array mới là 0-based.

**Các trường hợp cần lưu ý:**

- `execute()` trả về `boolean` cho biết kết quả đầu tiên là `ResultSet` hay không. Nó **không** có nghĩa boolean “procedure thành công/thất bại”. Lỗi JDBC thường xuất hiện dưới dạng `SQLException`.
- `getInt(...)` trả `0` cho SQL `NULL`; dùng `wasNull()` ngay sau `getInt`, hoặc lấy bằng `getObject(...)` nếu cần phân biệt `0` thực với `NULL`.
- SQL `DECIMAL`/`NUMERIC` thường ánh xạ sang `BigDecimal`; register với `Types.DECIMAL` và scale thích hợp nếu driver yêu cầu. Không mặc định chuyển tiền tệ thành `double`.
- Với routine có thêm `ResultSet` hoặc update count, để tương thích tối đa nên xử lý các kết quả đó trước khi đọc OUT parameters; ví dụ `compute_points` phía trên không phát ra `ResultSet`.
- Tên tham số trong JDBC (`registerOutParameter("p_double", ...)`) phụ thuộc hỗ trợ của driver. Dùng chỉ số đúng chữ ký là lựa chọn đơn giản khi cần tương thích.

## 4. Chương trình Java 17+ hoàn chỉnh: JDBC thuần

Đây là ví dụ **chạy được độc lập sau khi đã tạo database, routine và cấu hình quyền truy cập MySQL**. Tổ chức thư mục:

```text
inout-demo/
├── pom.xml
└── src/main/java/example/InOutJdbcDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>inout-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.mysql</groupId>
            <artifactId>mysql-connector-j</artifactId>
            <version>9.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.InOutJdbcDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/InOutJdbcDemo.java`:

```java
package example;

import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Types;

public final class InOutJdbcDemo {
    private InOutJdbcDemo() {
    }

    public static void main(String[] args) throws Exception {
        String url = requiredEnvironment("DB_URL");
        String username = requiredEnvironment("DB_USER");
        String password = requiredEnvironment("DB_PASSWORD");

        try (Connection connection =
                     DriverManager.getConnection(url, username, password);
             CallableStatement call =
                     connection.prepareCall("{call compute_points(?, ?, ?)}")) {

            call.setInt(1, 5);
            call.registerOutParameter(2, Types.INTEGER);
            call.setInt(3, 10);
            call.registerOutParameter(3, Types.INTEGER);

            call.execute();

            int doubled = call.getInt(2);
            if (call.wasNull()) {
                throw new IllegalStateException("p_double is NULL");
            }

            int total = call.getInt(3);
            if (call.wasNull()) {
                throw new IllegalStateException("p_total is NULL");
            }

            System.out.println("doubled=" + doubled);
            System.out.println("total=" + total);
        }
    }

    private static String requiredEnvironment(String name) {
        String value = System.getenv(name);
        if (value == null) {
            throw new IllegalStateException("Missing environment variable: " + name);
        }
        return value;
    }
}
```

Lớp có `main`, tên file và `package` khớp; không cần thêm code để biên dịch. Nó **không tự tạo routine**: phải chạy SQL ở mục 2 trước. Cấp quyền `EXECUTE` cho tài khoản được dùng.

Ví dụ mở PowerShell và điền thông tin tài khoản MySQL đang dùng:

```powershell
$env:DB_URL = 'jdbc:mysql://127.0.0.1:3306/procedure_lab'
$env:DB_USER = Read-Host 'MySQL user'
$env:DB_PASSWORD = Read-Host 'MySQL password'

mvn -q compile exec:java
```

Khi kết nối hợp lệ và procedure `compute_points` giữ nguyên định nghĩa ở mục 2, stdout của chương trình là:

```text
doubled=10
total=15
```

Trong môi trường có Maven, `mvn compile` dùng Maven Compiler Plugin và `exec:java` chạy class với dependency trên classpath. Có thể dùng `javac`/`java` trực tiếp nếu tự cấu hình toàn bộ JDBC driver và các thư viện trên classpath; ví dụ này dùng Maven để tránh sai sót classpath.

## 5. Gọi bằng Spring JDBC: SimpleJdbcCall

`SimpleJdbcCall` thuộc gói `org.springframework.jdbc.core.simple`. Nó triển khai cách gọi thủ tục dựa trên `DataSource`/`JdbcTemplate`, khai báo tham số có kiểu SQL và nhận kết quả dưới dạng `Map<String, Object>`. Đây là lựa chọn phù hợp khi ứng dụng đã sử dụng Spring Data Access và không muốn tự đóng từng `Connection`/`CallableStatement`.

Ba kiểu khai báo trong Spring tương ứng trực tiếp với ba chế độ SQL:

| SQL | Spring JDBC | Cần input trong `execute(...)`? | Xuất hiện trong result map? |
| --- | --- | --- | --- |
| `IN p_delta` | `new SqlParameter("p_delta", Types.INTEGER)` | Có | Không, trừ khi routine có output khác cùng tên |
| `OUT p_double` | `new SqlOutParameter("p_double", Types.INTEGER)` | Không | Có |
| `INOUT p_total` | `new SqlInOutParameter("p_total", Types.INTEGER)` | Có | Có |

**Cảnh báo đặc biệt:** dùng `SqlOutParameter` thay cho `SqlInOutParameter` ở tham số hai chiều khiến `SimpleJdbcCall` **không coi nó là nguồn input**. Kết quả có thể khác kỳ vọng hoặc cuộc gọi bị lỗi. Không phải cứ đặt một giá trị cùng tên trong `Map` thì nó tự trở thành INOUT.

### Ví dụ Spring JDBC chạy trên cùng database

Thêm file `src/main/java/example/InOutSpringDemo.java` vào project Maven ở mục 4:

```java
package example;

import java.sql.Types;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlInOutParameter;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

public final class InOutSpringDemo {
    private InOutSpringDemo() {
    }

    public static void main(String[] args) {
        DataSource dataSource = new DriverManagerDataSource(
                requiredEnvironment("DB_URL"),
                requiredEnvironment("DB_USER"),
                requiredEnvironment("DB_PASSWORD"));

        JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource);
        jdbcTemplate.setResultsMapCaseInsensitive(true);

        SimpleJdbcCall call = new SimpleJdbcCall(jdbcTemplate)
                .withProcedureName("compute_points")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("p_delta", Types.INTEGER),
                        new SqlOutParameter("p_double", Types.INTEGER),
                        new SqlInOutParameter("p_total", Types.INTEGER));

        MapSqlParameterSource input = new MapSqlParameterSource()
                .addValue("p_delta", 5, Types.INTEGER)
                .addValue("p_total", 10, Types.INTEGER);

        Map<String, Object> output = call.execute(input);

        Number doubled = (Number) output.get("p_double");
        Number total = (Number) output.get("p_total");
        if (doubled == null || total == null) {
            throw new IllegalStateException("Procedure returned NULL output");
        }

        System.out.println("doubled=" + doubled.intValue());
        System.out.println("total=" + total.intValue());
    }

    private static String requiredEnvironment(String name) {
        String value = System.getenv(name);
        if (value == null) {
            throw new IllegalStateException("Missing environment variable: " + name);
        }
        return value;
    }
}
```

Sau khi đã đặt ba biến môi trường ở mục trước, chạy:

```powershell
mvn -q compile
mvn -q -Dexec.mainClass=example.InOutSpringDemo exec:java
```

Stdout dự kiến, với routine và dữ liệu đầu vào trong ví dụ:

```text
doubled=10
total=15
```

**Đọc kỹ cấu hình:**

1. `withProcedureName("compute_points")` chọn **thủ tục**, không phải câu `SELECT` thông thường.
2. `withoutProcedureColumnMetaDataAccess()` tắt việc Spring tự suy luận danh sách tham số từ database metadata. Do đó `declareParameters(...)` phải đủ **mọi tham số theo đúng thứ tự chữ ký**. Cách này hữu ích khi driver không trả metadata đầy đủ hoặc tài khoản thiếu quyền xem định nghĩa routine.
3. `SqlParameter` là input; `SqlOutParameter` là output; `SqlInOutParameter` vừa nhận đầu vào vừa xuất kết quả.
4. `MapSqlParameterSource` chỉ chứa `p_delta` và `p_total`. Không cần gửi giá trị ban đầu cho `p_double`.
5. `call.execute(input)` trả `Map` có giá trị các tham số output. Kiểu object thực tế phải được đọc an toàn: với kiểu số, thường dùng `Number` rồi chuyển phù hợp, thay vì giả định mọi driver đều trả đúng `Integer`.
6. `setResultsMapCaseInsensitive(true)` giúp truy cập key trong map kết quả ít phụ thuộc kiểu chữ hoa/thường của database/driver.
7. `DriverManagerDataSource` chỉ để ví dụ đơn giản, tạo kết nối mới mỗi lần yêu cầu. Ứng dụng thực tế thường dùng connection pool và `DataSource` do Spring Boot quản lý.

Sau khi cấu hình xong, có thể đặt `SimpleJdbcCall` làm trường của một bean DAO và dùng lại cho nhiều lần gọi. **Không chỉnh lại tên/khai báo tham số của cùng instance trong khi các request đồng thời đang sử dụng nó**; cấu hình một lần khi khởi tạo.

### Biến thể dùng Map trực tiếp

Có thể dùng `Map.of` thay cho `MapSqlParameterSource`:

```java
Map<String, Object> output = call.execute(
        Map.of("p_delta", 5, "p_total", 10));
```

Đây là **đoạn trích bổ sung**, giả định biến `call` đã cấu hình như trên. `Map.of` không chấp nhận giá trị `null`; khi tham số SQL có thể nullable, nên dùng `MapSqlParameterSource` hoặc map cho phép null và khai báo rõ kiểu SQL.

### Metadata tự động hay khai báo thủ công?

Nếu database và driver trả metadata routine đáng tin cậy, có thể cấu hình ngắn hơn:

```java
SimpleJdbcCall call = new SimpleJdbcCall(jdbcTemplate)
        .withProcedureName("compute_points");
```

Spring sẽ cố dò tên, loại và thứ tự tham số bằng JDBC metadata. Cần kiểm thử thực tế: tên tham số có thể khác về hoa/thường, schema/catalog, quyền xem metadata, overload hoặc cách driver hỗ trợ. Với bài cần minh họa `INOUT` rõ ràng, khai báo tường minh là cách dễ kiểm tra hơn.

## 6. Procedure và function: tham số khác với giá trị return

**Procedure** thường được gọi bằng `CALL` và có thể trả dữ liệu thông qua `OUT`/`INOUT`, một hoặc nhiều result set, và có thể thực hiện thao tác ghi. **Function** được dùng để tính và trả về một giá trị được khai báo bằng `RETURNS`. **Giá trị trả về của function không đồng nghĩa với tham số OUT**, dù JDBC có thể dành một vị trí cho return value trong cú pháp lời gọi function.

Trong **MySQL 8.x**, khai báo `IN`, `OUT`, `INOUT` chỉ áp dụng cho **procedure**; tham số của stored function được xem là `IN`, còn kết quả của function được trả qua `RETURN`. Các hệ quản trị khác có thể hỗ trợ chế độ tham số function khác, nên không áp nguyên xi quy tắc MySQL lên tất cả database.

Ví dụ function MySQL:

```sql
DROP FUNCTION IF EXISTS add_tax;

DELIMITER $$
CREATE FUNCTION add_tax(
    p_net DECIMAL(10, 2),
    p_rate DECIMAL(5, 4)
)
RETURNS DECIMAL(10, 2)
DETERMINISTIC
NO SQL
BEGIN
    RETURN ROUND(p_net * (1 + p_rate), 2);
END$$
DELIMITER ;

SELECT add_tax(100.00, 0.10) AS gross;
```

Kết quả cột `gross` là `110.00`. Hai đối số `p_net` và `p_rate` là input, kết quả được trả bởi `RETURN`.

Trong Spring JDBC có thể gọi function bằng `JdbcTemplate`:

```java
java.math.BigDecimal gross = jdbcTemplate.queryForObject(
        "SELECT add_tax(?, ?)",
        java.math.BigDecimal.class,
        new java.math.BigDecimal("100.00"),
        new java.math.BigDecimal("0.10"));

System.out.println(gross); // 110.00
```

Đây là **đoạn mã đặt trong phương thức đã có `JdbcTemplate jdbcTemplate`**. `queryForObject` hữu ích cho function trả một giá trị scalar. `SimpleJdbcCall` cũng hỗ trợ `withFunctionName(...)` và `executeFunction(...)` khi database/driver hỗ trợ lời gọi function tương ứng.

Ở cấp JDBC, cú pháp escape cho function có thể đặt return value ở vị trí thứ nhất:

```java
try (CallableStatement statement =
         connection.prepareCall("{? = call add_tax(?, ?)}")) {
    statement.registerOutParameter(1, Types.DECIMAL);
    statement.setBigDecimal(2, new java.math.BigDecimal("100.00"));
    statement.setBigDecimal(3, new java.math.BigDecimal("0.10"));
    statement.execute();
    java.math.BigDecimal gross = statement.getBigDecimal(1);
}
```

Trong ví dụ function này, tham số **thứ nhất của CallableStatement** là vị trí **return** do cú pháp `{? = call ...}` tạo ra, không phải đối số `p_net`. Chú ý sự dịch chỉ số so với chữ ký SQL khi dùng cú pháp function call. Đoạn mã giả định đã có `Connection connection`.

## 7. Truyền NULL, kiểu dữ liệu và chuyển đổi kết quả

Các chế độ `IN/OUT/INOUT` độc lập với việc giá trị có nullable hay không. Hãy phân biệt **chế độ truyền** với **kiểu SQL**:

| Kiểu SQL | Java/JDBC thường dùng | Lưu ý |
| --- | --- | --- |
| `INTEGER` | `int`/`Integer`, `Types.INTEGER` | `getInt` cần `wasNull` để phân biệt NULL |
| `BIGINT` | `long`/`Long`, `Types.BIGINT` | Không ép kết quả lớn về `int` |
| `DECIMAL(p,s)` | `BigDecimal`, `Types.DECIMAL` | Bảo toàn độ chính xác tiền tệ, chú ý scale |
| `VARCHAR` | `String`, `Types.VARCHAR` | OUT có thể là `null` |
| `DATE` | `LocalDate` hoặc `java.sql.Date` | Kiểm tra hỗ trợ JDBC 4.2/driver |
| `TIMESTAMP` | `LocalDateTime` hoặc `Timestamp` | Phân biệt timestamp có/không timezone theo DB |

Với input nullable, truyền kiểu tường minh:

```java
statement.setNull(1, Types.INTEGER);
```

Đây là ví dụ `IN` (ở vị trí 1) khi routine cho phép giá trị null. Không dùng `setInt(1, 0)` thay cho `NULL`. Với output:

```java
int value = statement.getInt(2);
Integer nullableValue = statement.wasNull() ? null : value;
```

`wasNull()` phản ánh **lần đọc getter gần nhất**; phải gọi ngay sau `getInt` đó. Với `SimpleJdbcCall`, `output.get("p_double")` có thể là `null`; cần kiểm tra trước khi cast hoặc gọi `intValue()`.

Với tham số `INOUT`, null là giá trị đầu vào hợp lệ **chỉ khi routine được thiết kế để xử lý null**. Không có mặc định “INOUT tự lấy 0” hoặc “OUT tự sinh giá trị”.

## 8. Gọi từ Spring service với transaction

Một stored procedure có thể vừa cập nhật bảng, vừa trả `OUT`/`INOUT`. Kết quả output được đọc sau `CALL` nhưng **không phải bằng chứng toàn bộ transaction đã commit**. Trong Spring, nên tổ chức transaction ở tầng service khi nhiều thao tác database phải cùng thành công hoặc cùng rollback:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PointsService {
    private final PointsProcedureDao dao;

    public PointsService(PointsProcedureDao dao) {
        this.dao = dao;
    }

    @Transactional
    public int calculateAndPersist(int delta, int currentTotal) {
        int resultingTotal = dao.callAndReturnTotal(delta, currentTotal);
        if (resultingTotal < 0) {
            throw new IllegalStateException("Total must not be negative");
        }
        return resultingTotal;
    }
}
```

Đoạn trên **minh họa cấu trúc lớp service**, giả định đã có bean `PointsProcedureDao` thực thi lời gọi database và nghiệp vụ tương ứng; nó không phải chương trình chạy độc lập. Với routine `compute_points` ở mục 2, tên `calculateAndPersist` chỉ phù hợp nếu DAO còn thực hiện lưu dữ liệu; routine minh họa hiện tại **không ghi bảng**, chỉ tính giá trị tham số.

`@Transactional` chỉ có tác dụng khi phương thức được gọi qua cơ chế transaction của Spring (thường là qua Spring proxy) và dùng cùng `DataSource`/transaction manager phù hợp. Nếu gọi bằng `new PointsService(...)` ngoài Spring context thì annotation không tự mở transaction. Mặc định Spring rollback khi unchecked exception thoát khỏi transaction boundary; xử lý lỗi checked exception cần cấu hình rollback phù hợp với hợp đồng giao dịch.

**Các thực tiễn quan trọng:**

- Khi procedure làm DML, xác định rõ ai quản lý transaction; tránh lồng lệnh `COMMIT`/`ROLLBACK` vào routine nếu toàn bộ đơn vị công việc cần do Spring quản lý. Hành vi cụ thể còn phụ thuộc DB.
- Khi lỗi SQL xảy ra, `JdbcTemplate` dịch `SQLException` sang `DataAccessException`, giúp xử lý thống nhất ở tầng Spring.
- Kết quả OUT là dữ liệu do routine trả, không thay thế việc kiểm tra ràng buộc nghiệp vụ, trạng thái commit hay tính nhất quán.
- Không dựa vào việc biến `INOUT` đã đổi để suy ra một cột database cũng đã được cập nhật. Điều đó chỉ đúng nếu logic procedure thực sự ghi cột.
- Dùng tài khoản database có quyền tối thiểu cho các routine cần gọi; không chắp ghép tên procedure tùy ý từ input của client.

## 9. So sánh ngắn với JPA

Spring Data Access có hai nhánh phổ biến cho routine: Spring JDBC và JPA. Spring JDBC làm việc sát với JDBC và các kiểu `SqlParameter`/`SqlOutParameter`/`SqlInOutParameter`. Trong JPA, API chuẩn có `StoredProcedureQuery` và `ParameterMode.IN`, `OUT`, `INOUT`.

Ví dụ **đoạn trích trong repository/DAO JPA** có `EntityManager em` và transaction thích hợp:

```java
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

StoredProcedureQuery query = em.createStoredProcedureQuery("compute_points")
        .registerStoredProcedureParameter(1, Integer.class, ParameterMode.IN)
        .registerStoredProcedureParameter(2, Integer.class, ParameterMode.OUT)
        .registerStoredProcedureParameter(3, Integer.class, ParameterMode.INOUT);

query.setParameter(1, 5);
query.setParameter(3, 10);
query.execute();

int doubled = ((Number) query.getOutputParameterValue(2)).intValue();
int total = ((Number) query.getOutputParameterValue(3)).intValue();
```

Cần dependency/provider JPA thực tế (ví dụ Spring Data JPA + Hibernate), `EntityManager` được inject và hỗ trợ driver phù hợp; **không chạy đoạn này độc lập**. Vẫn thấy cùng quy luật: `IN` được set, `OUT` được đăng ký rồi đọc, `INOUT` được set **và** đọc. Khi provider/DB có giới hạn gọi bằng tên tham số, dùng vị trí có thể đơn giản hơn; thứ tự phải đúng routine. Spring Data JPA `@Procedure` là cách khác để ánh xạ routine vào repository method nhưng không thay đổi ý nghĩa ba chế độ.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Output luôn bằng `null`/`0` | Procedure không gán OUT, SQL null hoặc Java dùng `getInt` không kiểm tra `wasNull` | Đọc mã routine, kiểm tra input, dùng getter có nhận diện NULL |
| `SQLException` khi gọi `CALL` | Tên routine sai, không có quyền `EXECUTE`, sai số lượng/vị trí tham số | Kiểm tra schema, chữ ký routine, tài khoản và thông báo lỗi gốc |
| INOUT không nhận đầu vào | Chỉ `registerOutParameter` mà quên `set...`; khai báo Spring thành `SqlOutParameter` | Đặt giá trị input **và** đăng ký output/`SqlInOutParameter` |
| Output sai kiểu/cast exception | Nhầm `Types` hoặc mặc định object luôn là `Integer` | Đối chiếu kiểu cột SQL, dùng `Number`/`BigDecimal` thích hợp |
| Bị đảo kết quả giữa hai OUT | Thứ tự tham số trên JDBC lệch chữ ký SQL | So khớp index 1-based với thứ tự định nghĩa |
| Spring không tìm thấy metadata | Driver không hỗ trợ, quyền metadata, schema/catalog sai | Khai báo đủ bằng `declareParameters(...)` và `withoutProcedureColumnMetaDataAccess()` |
| Đọc output trước lúc thực thi | Chưa gọi `execute` | `set/register` trước, `execute`, rồi `get` |
| Nhầm return value của function là OUT parameter | Dùng sai cú pháp hoặc sai index `{? = call ...}` | Phân biệt `RETURNS/RETURN` với tham số `OUT` |
| OUT đúng nhưng thay đổi bảng bị rollback | Routine chạy trong transaction thất bại ở bước sau | Kiểm tra transaction boundary và lỗi gốc |
| INOUT giữ NULL ngoài dự kiến | Giá trị ban đầu NULL hoặc phép toán với NULL | Quy định chính sách NULL bằng `COALESCE`/validation |
| Code chạy được trên DB A nhưng lỗi DB B | Khác syntax `CREATE PROCEDURE`, mode của function, SQL type, metadata | Kiểm tra tài liệu DB/driver đúng phiên bản và viết integration test |

**Không nên:**

- Gán nhầm `SqlOutParameter` cho tham số cần gửi giá trị đầu vào.
- Dùng `statement.getInt(...) == 0` để kết luận routine trả số 0 khi chưa kiểm tra `wasNull()`.
- Giả định thứ tự phần tử của `Map` là thứ tự tham số SQL.
- Coi `execute() == false` là routine thất bại.
- Dùng `@Transactional` như thể nó bảo đảm mọi thao tác đã commit ngay tại thời điểm nhận OUT.
- Giả định MySQL, PostgreSQL, SQL Server và Oracle có cú pháp/function mode giống nhau.

## 11. Bài tập tự kiểm tra và kết quả mong đợi

Với `compute_points` được định nghĩa ở mục 2, hãy dự đoán và kiểm tra bằng các lệnh `CALL` trên database thử nghiệm:

| Input `p_delta` | Input ban đầu `p_total` | OUT `p_double` | INOUT `p_total` sau gọi |
| ---: | ---: | ---: | ---: |
| `5` | `10` | `10` | `15` |
| `-3` | `10` | `-6` | `7` |
| `0` | `10` | `0` | `10` |
| `5` | `NULL` | `10` | `NULL` |

Có thể tự kiểm bằng SQL:

```sql
SET @total = 10;
CALL compute_points(-3, @double, @total);
SELECT @double AS doubled, @total AS total;
```

Câu `SELECT` phải thể hiện `doubled = -6` và `total = 7`. Không có ảnh hưởng tích lũy giữa các lời gọi riêng biệt, vì routine ví dụ chỉ tính toán qua tham số và không ghi bảng.

**Checklist khi triển khai thật:**

1. Đọc chữ ký routine để ghi rõ từng tham số `IN`, `OUT`, `INOUT` và kiểu SQL.
2. Với JDBC, đánh chỉ số từ **1**, chỉ `set` cho IN, chỉ `register` cho OUT, **set + register** cho INOUT.
3. Với Spring, dùng đúng `SqlParameter`, `SqlOutParameter`, `SqlInOutParameter` và cung cấp đủ input.
4. Gọi routine xong mới đọc kết quả; xử lý `NULL` và type conversion cẩn thận.
5. Phân biệt `OUT` của procedure, `RETURN` của function và các `ResultSet` có thể trả kèm.
6. Kiểm thử bằng DB/driver thực tế, bao gồm NULL, giá trị biên, ngoại lệ, transaction và quyền gọi routine.

## Tài liệu tham khảo

- Spring Framework – Simple JDBC Classes, `SimpleJdbcCall` và định nghĩa tham số: https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html
- Spring Framework – `SqlInOutParameter` Java API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/SqlInOutParameter.html
- Java JDBC – `CallableStatement` và `registerOutParameter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/CallableStatement.html
- MySQL 8.4 – `CREATE PROCEDURE`/`CREATE FUNCTION`, chế độ tham số: https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html
- MySQL 8.4 – `CALL` và biến OUT/INOUT: https://dev.mysql.com/doc/refman/8.4/en/call.html
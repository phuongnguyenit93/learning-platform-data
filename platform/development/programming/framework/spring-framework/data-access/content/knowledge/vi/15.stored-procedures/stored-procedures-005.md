# Metadata tự động và cấu hình tham số tường minh khi gọi thủ tục và hàm trong Spring JDBC

`SimpleJdbcCall` giúp ứng dụng Spring Framework gọi **stored procedure** và **stored function** thông qua JDBC. Vấn đề cần quyết định là: để Spring **tự phát hiện chữ ký tham số từ metadata của database**, hay **khai báo rõ tên, chiều và kiểu SQL của từng tham số** trong mã Java?

Hai cách có thể tạo ra lời gọi và kết quả giống nhau khi chữ ký thủ tục/hàm phù hợp. Khác biệt nằm ở **nguồn thông tin mà Spring dựa vào để xây dựng lời gọi**, mức phụ thuộc vào JDBC driver và lượng cấu hình cần duy trì. Chọn đúng cách giúp tránh lỗi thiếu tham số `OUT`, sai thứ tự hoặc kiểu `IN`, lỗi nhận diện routine khi đổi schema, và các sự cố chỉ phát hiện khi chạy trên database thật.

## 1. Chữ ký của routine gồm những gì?

Một stored procedure hoặc function có **tên**, có thể thuộc một **schema/catalog**, và có **danh sách tham số**. Với procedure, một tham số có thể là:

| Chiều | Ý nghĩa | Lớp khai báo trong Spring JDBC |
| --- | --- | --- |
| `IN` | Ứng dụng đưa giá trị vào routine | `SqlParameter` |
| `OUT` | Routine ghi giá trị để trả lại ứng dụng | `SqlOutParameter` |
| `INOUT` | Ứng dụng đưa giá trị ban đầu vào và nhận giá trị đã thay đổi | `SqlInOutParameter` |

Mỗi tham số còn có **tên** và **SQL type** như `Types.INTEGER`, `Types.DECIMAL`, `Types.VARCHAR`, `Types.TIMESTAMP` hoặc loại riêng của database. Một **function** còn có giá trị trả về của chính hàm, khác với danh sách tham số đầu vào; Spring hỗ trợ `withFunctionName(...)` và `executeFunction(...)` cho kiểu gọi này.

Chẳng hạn, chữ ký giả định của một procedure:

~~~sql
quote_total(
    IN  p_price DECIMAL(12,2),
    IN  p_qty   INTEGER,
    OUT p_total DECIMAL(14,2)
)
~~~

Ứng dụng cung cấp `p_price` và `p_qty`, rồi đọc `p_total`. Nếu biết sai rằng `p_total` là `IN`, hoặc quên khai báo `OUT` trong chế độ không đọc metadata, lời gọi có thể thất bại hoặc không trả đúng dữ liệu.

**Cần phân biệt:** metadata tham số routine không phải metadata của dữ liệu kết quả truy vấn (`ResultSetMetaData`); nó chủ yếu là thông tin về cách gọi routine và các tham số của lời gọi.

## 2. Spring tự phát hiện metadata hoạt động như thế nào?

Với cấu hình tối giản:

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(jdbcTemplate)
        .withProcedureName("quote_total");
~~~

`SimpleJdbcCall` có thể lấy thông tin tham số từ **JDBC `DatabaseMetaData`** của kết nối, phối hợp với cơ chế hỗ trợ từng database của Spring. Khi được biên dịch (`compile()` hoặc tự compile trước lần thực thi đầu tiên), Spring xây dựng biểu diễn lời gọi `CallableStatement`: tên routine, số vị trí tham số, thứ tự, chiều `IN/OUT/INOUT` và kiểu SQL cần dùng.

Luồng khái quát:

~~~text
DataSource / JDBC Driver
       |
       v
DatabaseMetaData của connection
       |
       v
Spring tìm thông tin procedure/function + tham số
       |
       v
SimpleJdbcCall xây dựng/compile CALL
       |
       v
execute(input) -> JDBC CallableStatement -> Map kết quả OUT
~~~

Tùy database và driver, các phương thức JDBC liên quan có thể là `getProcedures`, `getProcedureColumns`, `getFunctions` và `getFunctionColumns`. Hỗ trợ **không đồng đều** theo database, driver, loại routine và quyền tài khoản. Spring có hỗ trợ metadata procedure trên một tập database được công bố; metadata function chỉ được hỗ trợ cho một tập hẹp hơn. Vì vậy **không suy ra mọi JDBC database đều có khả năng tự khám phá đầy đủ**.

Các lợi ích chính:

- Cấu hình Java gọn khi metadata của DB/driver **đầy đủ và đáng tin cậy**.
- Spring có thể suy ra tên, thứ tự, chiều và kiểu của các tham số thay vì buộc ta viết toàn bộ `SqlParameter` từ đầu.
- Khi chữ ký thay đổi, việc thử nghiệm trên database thật sẽ cho thấy metadata mới; tuy nhiên **điều này không có nghĩa thay đổi chữ ký sẽ tự tương thích ngược** với mọi mã gọi.

Các rủi ro chính:

- Driver trả thiếu/sai tham số hoặc diễn giải routine không đúng (thường thấy với overload, package, synonym, schema khác nhau).
- Tài khoản database thiếu quyền cần thiết để xem metadata.
- Khác biệt chữ hoa/chữ thường, catalog/schema hoặc cấu hình driver dẫn đến tên tham số không khớp.
- Lỗi chỉ xuất hiện khi compile/execute trên môi trường có metadata khác; hệ thống build Java thành công vẫn chưa chứng minh lời gọi chạy đúng.

### Khi nào metadata được đọc?

`SimpleJdbcCall` là đối tượng cấu hình **tái sử dụng**. Spring compile biểu diễn lời gọi một lần cho instance đã cấu hình (có thể gọi `compile()` chủ động hoặc để lần execute đầu tự compile). Sau khi compile, không nên tiếp tục sửa cấu hình của instance đó. Hãy tạo/cấu hình một instance trong vòng đời khởi tạo DAO/service và sử dụng lại cho các lần gọi; tránh tạo lại mỗi request nếu không có lý do cụ thể.

`compile()` giúp lộ vấn đề metadata/cấu hình sớm hơn nhưng **không phải là phép thử thực sự chạy procedure**. Việc routine có hoạt động đúng với dữ liệu thật vẫn cần một integration test.

## 3. Khai báo tham số tường minh và tắt metadata

Thay vì để Spring suy ra, ứng dụng có thể chỉ định từng tham số:

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(jdbcTemplate)
        .withProcedureName("quote_total")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(
                new SqlParameter("p_price", Types.DECIMAL),
                new SqlParameter("p_qty", Types.INTEGER),
                new SqlOutParameter("p_total", Types.DECIMAL)
        );
~~~

Ý nghĩa chính xác của hai lệnh:

- `declareParameters(...)` đăng ký những tham số đã biết. **Chỉ gọi phương thức này không có nghĩa tắt hoàn toàn metadata**: nếu metadata vẫn bật, Spring vẫn có thể dùng metadata cho các tham số không khai báo.
- `withoutProcedureColumnMetaDataAccess()` tắt **quá trình tra cứu metadata cột/tham số routine**. Khi ấy ứng dụng phải cung cấp đủ chữ ký cần thiết, đúng kiểu, đúng chiều và theo thứ tự phù hợp với cách gọi của database.

Khai báo tường minh phù hợp khi metadata của driver không hỗ trợ hoặc không đáng tin, khi yêu cầu kiểm soát chữ ký chặt chẽ, hoặc khi cần xử lý kiểu SQL đặc thù. Đổi lại, **định nghĩa procedure/function trong DB và khai báo Java phải được cập nhật đồng bộ**; Spring không tự sửa khai báo cũ khi routine đã thay chữ ký.

Ví dụ khai báo **một phần** (vẫn dựa vào metadata cho phần còn lại):

~~~java
SimpleJdbcCall partiallyDeclared = new SimpleJdbcCall(jdbcTemplate)
        .withProcedureName("quote_total")
        .declareParameters(new SqlOutParameter("p_total", Types.DECIMAL));
~~~

Ở đây `p_price` và `p_qty` vẫn phải được nhận diện từ metadata. Đây là lựa chọn có chủ đích khi chỉ một tham số cần ghi đè; nó **không phải** chế độ cấu hình tường minh hoàn toàn.

## 4. Ví dụ Java 17+ chạy với MySQL: hai cách gọi cùng một procedure

Ví dụ dùng MySQL để minh họa vì metadata procedure qua JDBC là trường hợp được Spring hỗ trợ. Mục tiêu là so sánh **cách lấy chữ ký tham số**, không phải so sánh hiệu năng hoặc transaction.

### 4.1. Tạo procedure trong MySQL

Yêu cầu: MySQL 8+, cơ sở dữ liệu `jdbc_demo`, tài khoản có quyền gọi routine và đọc metadata cần thiết. Trong MySQL command-line client, thực thi tệp SQL sau (đảm bảo đã tạo database và chọn đúng database):

~~~sql
USE jdbc_demo;

DROP PROCEDURE IF EXISTS quote_total;

DELIMITER //
CREATE PROCEDURE quote_total(
    IN  p_price DECIMAL(12,2),
    IN  p_qty   INT,
    OUT p_total DECIMAL(14,2)
)
BEGIN
    SET p_total = p_price * p_qty;
END//
DELIMITER ;
~~~

`DELIMITER` là chỉ thị của **MySQL CLI** để nhập phần thân routine nhiều câu lệnh; nó không phải câu SQL gửi trực tiếp qua `JdbcTemplate.execute(...)`. Procedure này chỉ tính toán, không thay đổi dữ liệu bảng. Với `p_price=12.50` và `p_qty=3`, kết quả mong đợi là `p_total=37.50`.

### 4.2. Tạo dự án Maven tối thiểu

Cấu trúc:

~~~text
simple-jdbc-call-demo/
├── pom.xml
└── src/main/java/example/MetadataVsExplicitDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>simple-jdbc-call-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.mysql</groupId>
            <artifactId>mysql-connector-j</artifactId>
            <version>9.3.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
                <configuration>
                    <mainClass>example.MetadataVsExplicitDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/example/MetadataVsExplicitDemo.java`:

~~~java
package example;

import java.math.BigDecimal;
import java.sql.Types;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class MetadataVsExplicitDemo {

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("com.mysql.cj.jdbc.Driver");
        dataSource.setUrl(requiredEnv("DEMO_DB_URL"));
        dataSource.setUsername(requiredEnv("DEMO_DB_USER"));
        dataSource.setPassword(requiredEnv("DEMO_DB_PASSWORD"));

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        // Chuẩn hóa việc truy xuất tên khóa OUT bất kể DB trả hoa/thường.
        jdbc.setResultsMapCaseInsensitive(true);

        // Cách A: dùng metadata của JDBC driver/database.
        SimpleJdbcCall automatic = new SimpleJdbcCall(jdbc)
                .withProcedureName("quote_total");

        // Cách B: tự khai báo đầy đủ, không dò metadata tham số.
        SimpleJdbcCall explicit = new SimpleJdbcCall(jdbc)
                .withProcedureName("quote_total")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("p_price", Types.DECIMAL),
                        new SqlParameter("p_qty", Types.INTEGER),
                        new SqlOutParameter("p_total", Types.DECIMAL)
                );

        MapSqlParameterSource input = new MapSqlParameterSource()
                .addValue("p_price", new BigDecimal("12.50"), Types.DECIMAL)
                .addValue("p_qty", 3, Types.INTEGER);

        // Có thể compile sớm; nếu bỏ đi, execute sẽ tự compile.
        automatic.compile();
        explicit.compile();

        Map<String, Object> autoOut = automatic.execute(input);
        Map<String, Object> explicitOut = explicit.execute(input);

        System.out.println("metadata total=" + autoOut.get("p_total"));
        System.out.println("explicit total=" + explicitOut.get("p_total"));
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment variable: " + name);
        }
        return value;
    }
}
~~~

Chạy sau khi procedure đã được tạo và thông tin kết nối đúng. Ví dụ trong PowerShell (thay bằng tài khoản của bạn; không đưa mật khẩu thật vào mã nguồn):

~~~powershell
$env:DEMO_DB_URL = "jdbc:mysql://localhost:3306/jdbc_demo"
$env:DEMO_DB_USER = "your_db_user"
$env:DEMO_DB_PASSWORD = "your_db_password"
mvn -q compile exec:java
~~~

Các dòng do chương trình in ra, với MySQL và routine trên:

~~~text
metadata total=37.50
explicit total=37.50
~~~

Giải thích:

1. `automatic` hỏi metadata của driver để biết chữ ký `quote_total`; ứng dụng chỉ khai báo tên routine.
2. `explicit` không dò metadata tham số; Spring dùng ba `SqlParameter`/`SqlOutParameter` do ta khai báo theo chữ ký SQL.
3. Cả hai nhận cùng `MapSqlParameterSource`. `execute(...)` trả `Map<String,Object>` chứa giá trị `OUT`. `setResultsMapCaseInsensitive(true)` giúp đọc khóa `p_total` dù cách viết hoa/thường trong kết quả do DB khác nhau.
4. `BigDecimal` và `Types.DECIMAL` phù hợp với dữ liệu tiền tệ trong ví dụ; ứng dụng thật cần xác định thêm scale, làm tròn và độ chính xác theo nghiệp vụ.

**Điều kiện của phép thử:** cần MySQL đang chạy, procedure được tạo và user có quyền truy cập. Nếu tài khoản không đọc được metadata, **cách A có thể lỗi dù cách B vẫn gọi được routine** khi quyền thực thi procedure và những điều kiện JDBC còn lại cho phép. Hai dòng output là kết quả kỳ vọng của cấu hình MySQL nêu trên, không phải kết quả phổ quát mọi DB/driver.

## 5. `Map` tham số không có nghĩa JDBC tự bind theo tên

Đây là khác biệt rất dễ nhầm:

~~~java
MapSqlParameterSource in = new MapSqlParameterSource()
        .addValue("p_price", new BigDecimal("12.50"), Types.DECIMAL)
        .addValue("p_qty", 3, Types.INTEGER);

Map<String, Object> out = automatic.execute(in);
~~~

`MapSqlParameterSource` liên kết **tên tham số logic** với giá trị đầu vào ở tầng Spring. `SimpleJdbcCall` có thể dựa vào tên từ metadata hoặc khai báo để sắp xếp giá trị theo vị trí của lời gọi JDBC. Điều đó **không nhất thiết** có nghĩa `CallableStatement` đang dùng binding theo tên do database/driver cung cấp.

`withNamedBinding()` là tùy chọn riêng:

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(jdbc)
        .withProcedureName("quote_total")
        .withNamedBinding();
~~~

Nó yêu cầu Spring dùng cách bind theo **tên** trong lời gọi, nhưng cú pháp/khả năng hỗ trợ phụ thuộc driver/database. **Không thêm `withNamedBinding()` chỉ để sử dụng `MapSqlParameterSource`**. Trong đa số trường hợp, map có khóa đúng cùng khai báo/metadata là đủ; cần kiểm thử thực tế nếu quyết định bật named binding.

Cách truyền `execute(Object... args)` theo vị trí càng cần thận trọng: thứ tự giá trị phải tương ứng thứ tự tham số `IN` đã xác lập. Dùng map tường minh thường giúp mã dễ đọc hơn, nhưng vẫn cần đúng tên, chiều và loại giá trị.

## 6. Cấu hình tên routine, schema và catalog

Khi có nhiều schema, tên routine ngắn có thể phân giải theo default schema/search path của connection. Để tránh gọi nhầm, Spring hỗ trợ:

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(jdbc)
        .withSchemaName("billing")
        .withProcedureName("quote_total");
~~~

Nếu hệ quản trị tổ chức routine qua catalog/package, có thể dùng `withCatalogName(...)` theo quy ước của database và Spring dialect. **Không coi schema, catalog và package là ba khái niệm giống nhau trên mọi DB.** Ở MySQL, database thường đóng vai trò schema; ở Oracle, package có thể liên quan cách Spring dùng catalog; tên và cấu hình cần đối chiếu với database cụ thể.

Khi có nhiều overload hoặc cùng tên routine ở các schema, phải kiểm tra chữ ký được chọn. `useInParameterNames(...)` xuất hiện trong API cho việc giới hạn tên tham số `IN` ở những tình huống chữ ký khác nhau, nhưng không nên xem đây là cơ chế giải quyết overload tự động cho mọi driver. Cách vững chắc là kiểm thử SQL call thực tế và khai báo tường minh khi metadata mơ hồ.

## 7. Function, OUT/INOUT và tập kết quả: không áp cùng một công thức

### Function: trả về giá trị riêng

Nếu database có function `double_amount`, lời gọi Spring cơ bản khác procedure ở **tên cấu hình** và **API lấy giá trị trả về**:

~~~java
SimpleJdbcCall functionCall = new SimpleJdbcCall(jdbc)
        .withFunctionName("double_amount");

BigDecimal doubled = functionCall.executeFunction(
        BigDecimal.class,
        new MapSqlParameterSource()
                .addValue("p_amount", new BigDecimal("12.50"))
);
~~~

Đây là đoạn minh họa trong ngữ cảnh JDBC đã cấu hình **và database có function đúng chữ ký**; không phải một chương trình thứ hai có thể chạy độc lập. Metadata cho function tùy database/driver và có thể kém đầy đủ hơn procedure. Với một function có nhiều kết quả OUT hoặc trường hợp đặc biệt, cần đọc contract cụ thể thay vì giả định `executeFunction` có thể thay thế mọi `execute` của procedure.

### INOUT: phải khai báo đúng chiều

Ví dụ procedure `increase_counter(INOUT p_count INT)` có thể được cấu hình:

~~~java
SimpleJdbcCall increment = new SimpleJdbcCall(jdbc)
        .withProcedureName("increase_counter")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(new SqlInOutParameter("p_count", Types.INTEGER));
~~~

Khi viết đoạn này trong Java thực, thêm import `org.springframework.jdbc.core.SqlInOutParameter`. Đầu vào của `SqlInOutParameter` được cung cấp qua `MapSqlParameterSource`; kết quả `OUT` xuất hiện trong map trả về. **Không thay `SqlInOutParameter` bằng `SqlOutParameter` rồi kỳ vọng nó tự nhận giá trị đầu vào.**

### Procedure trả `ResultSet` hoặc `REF CURSOR`

Một số procedure trả các dòng dữ liệu qua tập kết quả, không phải giá trị scalar OUT. Với `SimpleJdbcCall` có thể dùng `returningResultSet("items", rowMapper)`. Cách database trả tập kết quả **có thể khác nhau**: kết quả trực tiếp từ JDBC, hoặc cursor được đăng ký ở tham số OUT. Kiểu SQL cursor và quy tắc sắp xếp result set phụ thuộc database/driver. Đừng áp `Types.VARCHAR` hoặc chỉ đọc `Map.get("items")` trước khi xác nhận routine thực sự trả dạng gì.

Chủ đề metadata tự động/tường minh **vẫn áp dụng**: nếu driver không cung cấp chữ ký cursor đáng tin, phải khai báo tham số OUT và mapping thích hợp cho hệ quản trị đang dùng.

## 8. Chọn cách nào cho từng tình huống?

| Tình huống | Cách nên bắt đầu | Lý do |
| --- | --- | --- |
| Procedure đơn giản trên DB/driver mà Spring hỗ trợ metadata tốt | `withProcedureName(...)`, không khai báo đầy đủ | Ít cấu hình, thuận tiện khi chữ ký rõ ràng |
| Chỉ một OUT hoặc loại SQL cần ghi đè, metadata các tham số còn lại tốt | `declareParameters(...)` **một phần**, vẫn bật metadata | Giữ khả năng tự phát hiện nhưng sửa điểm cần kiểm soát |
| Database/driver không được hỗ trợ metadata hoặc metadata thiếu/sai | `withoutProcedureColumnMetaDataAccess()` + khai báo đầy đủ | Tự kiểm soát hợp đồng gọi |
| Routine overload, package/schema gây nhầm lẫn | Chỉ định schema/catalog phù hợp; cân nhắc khai báo đầy đủ | Giảm rủi ro chọn sai chữ ký |
| INOUT, custom SQL type, cursor hoặc giá trị NULL khó suy diễn | Khai báo chiều/kiểu SQL phù hợp; đăng ký SQL type ở nguồn input | Tránh suy luận sai kiểu hoặc chiều |
| Nhiều môi trường DB có driver/privilege khác nhau | Integration test trên từng DB/driver mục tiêu, chọn chế độ theo kết quả | Metadata hỗ trợ trên máy dev chưa chứng minh hỗ trợ ở production |

**Nguyên tắc:** cách `tự động` tiết kiệm cấu hình khi metadata đáng tin; cách `tường minh` mua lại sự chủ động bằng trách nhiệm bảo trì chữ ký. Không có cách nào tự loại bỏ nhu cầu kiểm thử với routine thực.

## 9. Các lỗi thực tế và cách chẩn đoán

| Triệu chứng | Nghi ngờ đầu tiên | Việc cần làm |
| --- | --- | --- |
| Procedure có thật nhưng Spring báo không tìm thấy hoặc sai số lượng tham số | Sai schema/catalog, quyền xem metadata, driver không hỗ trợ hoặc tên chữ hoa/thường | Xác minh routine và quyền bằng đúng tài khoản ứng dụng; chỉ rõ schema/catalog hoặc cấu hình explicit |
| Lỗi `Invalid column type`, `SQLException` khi đặt giá trị | `Types` không khớp, đầu vào `NULL` không có SQL type, custom DB type | Đối chiếu SQL signature; đăng ký kiểu trong `MapSqlParameterSource.addValue(name, value, sqlType)` |
| Kết quả `out.get("p_total")` là null trong khi DB đã tính | Trường OUT chưa được khai báo, tên khóa bị đổi hoa/thường, đang đọc nhầm tên | Xem khóa thực tế trong result map và chữ ký OUT; dùng `setResultsMapCaseInsensitive(true)` |
| Cách metadata chạy nhưng explicit lỗi | Thiếu OUT/INOUT, sai thứ tự khai báo hoặc kiểu SQL | Đối chiếu mọi tham số với routine trong DB theo cùng phiên bản migration |
| Cách explicit chạy, metadata lỗi | Metadata hoặc quyền truy cập metadata không đủ | Đọc `DatabaseMetaData`/log và quyền; giữ khai báo đầy đủ khi cần |
| Chỉ lỗi trên database khác hoặc sau deploy | Driver/version, routine/schema, quyền hoặc kiểu SQL giữa môi trường khác nhau | Kiểm thử trên môi trường sát production, ghi nhận driver và chữ ký thực |
| Gọi `execute` nhiều lần nhưng luôn thấy vấn đề cấu hình từ lần đầu | `SimpleJdbcCall` đã compile và lưu cấu hình trước đó | Tạo lại instance khi cấu hình/routine contract thay đổi; không sửa cấu hình sau compile |
| Có `withNamedBinding()` rồi thất bại ở runtime | Driver/database không hỗ trợ cách bind mong đợi | Bỏ tùy chọn nếu không cần; thử binding logic theo map và vị trí JDBC thông thường |

### NULL và kiểu SQL

`NULL` có thể là trường hợp driver không suy ra được SQL type:

~~~java
MapSqlParameterSource input = new MapSqlParameterSource()
        .addValue("p_note", null, Types.VARCHAR)
        .addValue("p_price", new BigDecimal("12.50"), Types.DECIMAL);
~~~

Đoạn này minh họa cách chỉ định kiểu đầu vào cho một routine **có tham số `p_note` phù hợp**, không phải đầu vào của `quote_total` trong ví dụ chạy trước. Gửi thừa `p_note` vào procedure không khai báo tham số đó là sai contract. Với giá trị OUT/INOUT và kiểu riêng của DB, có thể cần `SqlReturnType`, `SqlTypeValue` hoặc type name theo driver.

### Log và quyền

Có thể bật logging có kiểm soát cho Spring JDBC để xem tên routine, chữ ký được biên dịch và lỗi từ driver. Không log mật khẩu hoặc toàn bộ giá trị đầu vào nhạy cảm. Đối chiếu metadata trên **đúng JDBC URL, user và driver** của ứng dụng; dùng quyền tài khoản admin trong SQL client không chứng minh tài khoản service đọc được metadata.

## 10. Kiểm thử chức năng và contract giữa Java–database

Một bộ integration test hữu ích cho cả hai cách nên có:

1. **Schema thực:** chạy migration tạo procedure/function, xác nhận tên/schema và danh sách tham số thực tế.
2. **Happy path:** với đầu vào xác định như `12.50 × 3`, cả cấu hình metadata và explicit đều nhận `37.50` ở `p_total` (trên MySQL demo).
3. **Kiểu/NULL:** thử giá trị boundary và `NULL` khi routine cho phép; kiểm tra các SQL type được đăng ký đúng.
4. **Thay đổi chữ ký:** thay/rollback migration trong môi trường test và xác nhận Java không âm thầm gọi nhầm hoặc bỏ sót OUT.
5. **Quyền và môi trường:** kiểm tra bằng tài khoản DB dùng trong production, so phiên bản driver giữa dev/test/production.
6. **Function/cursor nếu có:** kiểm tra giá trị return của function và các tập kết quả bằng RowMapper đúng.
7. **Thất bại có kiểm soát:** quan sát exception và lỗi SQL gốc, không chỉ xác nhận Java đã compile.

Khi cần, gọi `compile()` tại lúc khởi tạo để lộ lỗi metadata sớm; vẫn phải thực hiện ít nhất một lần gọi **thật** để xác nhận SQL signature, kiểu tham số và result mapping.

Một số sai lầm cần tránh:

- Nghĩ `declareParameters` tự động tắt metadata: **không**, phải dùng `withoutProcedureColumnMetaDataAccess()` nếu muốn bỏ tra cứu tham số.
- Nghĩ tham số có tên trong `Map` là driver đã bind theo tên: **không nhất thiết**, `withNamedBinding()` là thiết lập riêng.
- Khai báo mọi tham số thành `SqlParameter`: các tham số `OUT`/`INOUT` cần đúng lớp.
- Dựa vào tên `OUT` đúng chính tả trong Java nhưng không xét quy tắc hoa/thường của DB.
- Tạo `SimpleJdbcCall` mới trong từng request hoặc sửa cấu hình đã compile.
- Coi việc metadata hoạt động trên một DB đồng nghĩa mọi dialect/driver đều hỗ trợ như nhau.
- Trộn việc chọn kiểu binding/metadata với quyết định transaction: hai vấn đề độc lập. Cách khai báo tham số **không tự mở transaction hay bảo đảm rollback** cho các cập nhật bên trong procedure.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Bạn đã gọi `declareParameters(new SqlOutParameter("result", Types.INTEGER))` nhưng không gọi `withoutProcedureColumnMetaDataAccess()`. Spring còn dùng metadata được không?

**Đáp án:** Có. Spring vẫn có thể dùng metadata để bổ sung những tham số chưa được khai báo. Nếu muốn khai báo tất cả theo mã Java, phải tắt tra cứu metadata tham số và khai báo trọn vẹn.

**Câu 2.** Bạn truyền `MapSqlParameterSource` có khóa `p_id`. Driver có bắt buộc sử dụng named binding không?

**Đáp án:** Không. Tên trong map là giao diện truyền giá trị tại tầng Spring. `withNamedBinding()` là tùy chọn riêng và phải phù hợp driver/database.

**Câu 3.** Một procedure có `IN p_id INTEGER, OUT p_name VARCHAR(100)` nhưng cấu hình explicit chỉ khai báo `SqlParameter("p_id", Types.INTEGER)`. Điều gì sai?

**Đáp án:** Thiếu khai báo `SqlOutParameter("p_name", Types.VARCHAR)`. Khi metadata đã tắt, Spring không tự bổ sung OUT đó; chữ ký lời gọi trở nên không đầy đủ.

**Câu 4.** Vì sao một cấu hình tự phát hiện chạy trên MySQL nhưng có thể lỗi khi đổi JDBC driver hoặc database khác?

**Đáp án:** Metadata và cách Spring xử lý nó không có mức hỗ trợ giống nhau giữa các DB/driver; quyền truy cập, schema/catalog và kiểu routine cũng có thể khác. Cần integration test với môi trường đích; khi cần, dùng khai báo tường minh.

## Tài liệu tham khảo

- [Spring Framework — Simplifying JDBC Operations with the SimpleJdbc Classes](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/simple.html)
- [Spring Framework — Common Problems with Parameter and Data Value Handling](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/parameter-handling.html)
- [Spring Framework API — SimpleJdbcCall](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/core/simple/SimpleJdbcCall.html)
- [MySQL Connector/J documentation](https://dev.mysql.com/doc/connector-j/en/)

# `SqlParameter`, `SqlOutParameter` và `SqlInOutParameter` trong Spring JDBC

## 1. Ba loại tham số giải quyết vấn đề gì?

Khi gọi **stored procedure** (thủ tục lưu trữ) hoặc **stored function** (hàm lưu trữ), JDBC cần biết tham số nào truyền vào, tham số nào nhận kết quả và tham số nào vừa nhận giá trị ban đầu vừa được thủ tục cập nhật. JDBC cấp thấp dùng `CallableStatement` với các thao tác như `setObject(...)`, `registerOutParameter(...)`, `execute()` và `getObject(...)`.

Spring JDBC biểu diễn mô tả đó bằng ba lớp thuộc package `org.springframework.jdbc.core`:

| Lớp Spring | Hướng theo SQL | Có giá trị đầu vào? | Có giá trị đầu ra? | Chức năng |
| --- | --- | --- | --- | --- |
| `SqlParameter` | `IN` | Có | Không | Khai báo tên và kiểu SQL của dữ liệu gửi vào |
| `SqlOutParameter` | `OUT` | Không, trong cách dùng thông thường với `SimpleJdbcCall` | Có | Khai báo kết quả do thủ tục trả về |
| `SqlInOutParameter` | `INOUT` | Có | Có | Khai báo tham số được gửi vào và nhận lại sau khi thay đổi |

Ba lớp này là **mô tả tham số** (metadata cho lời gọi), **không phải nơi chứa giá trị nghiệp vụ**. Giá trị thực được truyền bằng `Map` hoặc `SqlParameterSource` khi gọi `SimpleJdbcCall.execute(...)`. Kiểu SQL lấy từ `java.sql.Types`, ví dụ `Types.INTEGER`, `Types.VARCHAR`, `Types.DECIMAL`, `Types.DATE`.

**Phân biệt quan trọng:** `SqlParameter` (lớp *khai báo*) khác `SqlParameterSource` (interface *cung cấp giá trị*). Một đối tượng `MapSqlParameterSource` có thể khai báo kiểu cho giá trị đầu vào bằng `addValue(name, value, sqlType)` nhưng không thay thế `SqlOutParameter` trong việc đăng ký tham số đầu ra.

### Cơ chế ở mức JDBC

Đối chiếu một thủ tục có ba tham số theo đúng thứ tự `IN`, `OUT`, `INOUT`:

```java
// Fragment JDBC thuần; giả định đã có Connection connection.
try (java.sql.CallableStatement cs =
         connection.prepareCall("{call accumulate_invoice(?, ?, ?)}")) {
    cs.setBigDecimal(1, new java.math.BigDecimal("200.00")); // IN
    cs.registerOutParameter(2, java.sql.Types.DECIMAL);     // OUT
    cs.setBigDecimal(3, new java.math.BigDecimal("1000.00")); // INOUT: ghi đầu vào
    cs.registerOutParameter(3, java.sql.Types.DECIMAL);     // INOUT: đăng ký đầu ra

    cs.execute();

    java.math.BigDecimal tax = cs.getBigDecimal(2);
    java.math.BigDecimal total = cs.getBigDecimal(3);
}
```

`SimpleJdbcCall` giúp thực hiện các bước tương ứng từ những đối tượng khai báo. Thứ tự vị trí trong `CallableStatement` bắt đầu từ **1**, còn tên tham số và kiểu khai báo phải khớp thủ tục thực sự trên cơ sở dữ liệu.

## 2. Hiểu riêng từng lớp

### `SqlParameter` — đầu vào `IN`

```java
new SqlParameter("in_net", Types.DECIMAL)
```

Đây là mô tả tham số đầu tiên của thủ tục, mang số thập phân từ Java sang cơ sở dữ liệu. Spring nhận giá trị `in_net` từ nguồn đầu vào khi thực thi. Một số constructor cho phép bổ sung `scale` của số thập phân hoặc `typeName` cho kiểu do DBMS định nghĩa; không cần dùng chúng nếu kiểu cơ bản đã đủ.

**Lưu ý:** khai báo `SqlParameter` không có nghĩa Spring sẽ tự tìm được giá trị từ biến Java cùng tên. Phải truyền giá trị bằng `Map` hoặc `SqlParameterSource`.

### `SqlOutParameter` — đầu ra `OUT`

```java
new SqlOutParameter("out_tax", Types.DECIMAL)
```

Kết quả `out_tax` được lấy từ tham số đầu ra sau khi thủ tục thực thi và xuất hiện trong bản đồ kết quả trả về bởi `SimpleJdbcCall.execute(...)`. Không đưa `out_tax` vào nguồn dữ liệu đầu vào như một giá trị bắt buộc: nó là tham số để thủ tục ghi.

Khi DBMS trả về kiểu đặc biệt hoặc con trỏ `REF CURSOR`, `SqlOutParameter` còn hỗ trợ `RowMapper` hoặc `SqlReturnType` để tùy biến việc chuyển đổi đầu ra (chỉ cấu hình theo khả năng của driver/DBMS).

### `SqlInOutParameter` — hai chiều `INOUT`

```java
new SqlInOutParameter("inout_grand_total", Types.DECIMAL)
```

Spring phải **gán giá trị ban đầu** cho `inout_grand_total` rồi **đăng ký để đọc lại giá trị mới**. Sau khi gọi thủ tục, đầu vào trong Java không tự biến đổi theo kiểu tham chiếu; giá trị cập nhật phải được lấy từ `Map` đầu ra.

Ví dụ: `inout_grand_total` ban đầu là `1000.00`, thủ tục cộng thêm tiền hàng `200.00` và thuế `20.00`; đầu ra là `1220.00`. Nếu chỉ khai báo `SqlParameter`, Spring không lấy lại giá trị; nếu chỉ khai báo `SqlOutParameter` trong `SimpleJdbcCall`, Spring không gán giá trị ban đầu theo cơ chế `INOUT`.

Về kế thừa, `SqlInOutParameter` là lớp con của `SqlOutParameter`, còn `SqlOutParameter` cuối cùng kế thừa từ `SqlParameter`. **Kế thừa Java không đồng nghĩa ba kiểu có cùng vai trò khi bind dữ liệu.** Quy tắc Spring công bố: trong `SimpleJdbcCall`, các khai báo `SqlParameter` và `SqlInOutParameter` được dùng để cấp đầu vào. Lớp `StoredProcedure` cũ có ngoại lệ tương thích ngược cho phép đầu vào của `SqlOutParameter` trong một số trường hợp; không dùng ngoại lệ đó để mô hình hóa `INOUT` trong code mới.

## 3. Ví dụ hoàn chỉnh: một procedure dùng cả `IN`, `OUT`, `INOUT`

Ví dụ dưới dùng **MySQL 8.4**, **Java 17**, **Spring JDBC 6.2.x**. Thủ tục chỉ tính toán giá trị (không ghi bảng), nhằm làm rõ sự khác biệt của ba loại tham số. Cần có một MySQL chạy được và quyền tạo/thực thi routine.

### Bước 1: Tạo stored procedure và function

Mở MySQL CLI, chạy nội dung `setup.sql`:

```sql
CREATE DATABASE IF NOT EXISTS spring_parameter_demo;
USE spring_parameter_demo;

DROP PROCEDURE IF EXISTS accumulate_invoice;
DELIMITER //
CREATE PROCEDURE accumulate_invoice(
    IN in_net DECIMAL(12, 2),
    OUT out_tax DECIMAL(12, 2),
    INOUT inout_grand_total DECIMAL(12, 2)
)
BEGIN
    SET out_tax = ROUND(in_net * 0.10, 2);
    SET inout_grand_total = inout_grand_total + in_net + out_tax;
END //
DELIMITER ;

DROP FUNCTION IF EXISTS invoice_tax;
CREATE FUNCTION invoice_tax(p_net DECIMAL(12, 2))
RETURNS DECIMAL(12, 2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_net * 0.10, 2);
```

- `in_net`: số tiền hàng (đầu vào).
- `out_tax`: tiền thuế, do thủ tục tính (đầu ra).
- `inout_grand_total`: tổng tích lũy, có trước khi gọi và được thủ tục thay đổi.
- `invoice_tax`: hàm độc lập nhận một giá trị và trả về một giá trị vô hướng.

Lệnh `DELIMITER //` là **lệnh của MySQL CLI** để gửi toàn bộ khối `BEGIN ... END`, không phải câu SQL gửi trực tiếp bằng `JdbcTemplate.execute(...)`. Dùng cú pháp tương đương khi chạy bằng công cụ migration. Phần `INOUT` được minh họa **trong procedure**; MySQL stored function chỉ nhận tham số đầu vào và trả kết quả qua `RETURN`.

Đối với `200.00` tiền hàng, thuế 10% là `20.00`; tổng ban đầu `1000.00` chuyển thành `1220.00`.

### Bước 2: Cấu hình Maven (`pom.xml`)

Đặt tệp sau ở thư mục gốc dự án Maven; dùng Java 17 hoặc mới hơn. Hai phiên bản dependency dưới đây là ví dụ cụ thể để bài có thể chạy độc lập; trong Spring Boot nên để dependency management của dự án quản lý các phiên bản tương thích.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>stored-routine-parameters</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.mysql</groupId>
            <artifactId>mysql-connector-j</artifactId>
            <version>9.4.0</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### Bước 3: Viết `src/main/java/StoredRoutineParameterDemo.java`

Đây là **lớp Java hoàn chỉnh có `main`**. Phần kết nối lấy thông tin từ biến môi trường, không nhúng tài khoản vào mã nguồn.

```java
import java.math.BigDecimal;
import java.sql.Types;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlInOutParameter;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class StoredRoutineParameterDemo {
    private StoredRoutineParameterDemo() {}

    public static void main(String[] args) {
        var dataSource = new DriverManagerDataSource(
                requiredEnv("DB_URL"),
                requiredEnv("DB_USER"),
                requiredEnv("DB_PASSWORD"));

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setResultsMapCaseInsensitive(true);

        // Khai báo một lần trước khi thực thi: đúng thứ tự SQL của procedure.
        SimpleJdbcCall accumulate = new SimpleJdbcCall(jdbc)
                .withProcedureName("accumulate_invoice")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("in_net", Types.DECIMAL),
                        new SqlOutParameter("out_tax", Types.DECIMAL),
                        new SqlInOutParameter(
                                "inout_grand_total", Types.DECIMAL));

        // Chỉ IN và INOUT cần giá trị đầu vào.
        var inputs = new MapSqlParameterSource()
                .addValue("in_net", new BigDecimal("200.00"), Types.DECIMAL)
                .addValue("inout_grand_total",
                        new BigDecimal("1000.00"), Types.DECIMAL);

        Map<String, Object> outputs = accumulate.execute(inputs);

        // OUT và INOUT được lấy lại từ Map, theo tên khai báo.
        BigDecimal tax = (BigDecimal) outputs.get("out_tax");
        BigDecimal grandTotal =
                (BigDecimal) outputs.get("inout_grand_total");

        System.out.println("OUT out_tax = " + tax.toPlainString());
        System.out.println("INOUT inout_grand_total = "
                + grandTotal.toPlainString());

        // Stored function: với MySQL, Spring có thể tra metadata.
        SimpleJdbcCall taxFunction = new SimpleJdbcCall(jdbc)
                .withFunctionName("invoice_tax");
        BigDecimal functionTax = taxFunction.executeFunction(
                BigDecimal.class,
                new MapSqlParameterSource()
                        .addValue("p_net",
                                new BigDecimal("200.00"), Types.DECIMAL));

        System.out.println("FUNCTION invoice_tax = "
                + functionTax.toPlainString());
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing environment variable: " + name);
        }
        return value;
    }
}
```

Ví dụ này dùng `DriverManagerDataSource` cho chương trình học tập chạy ngắn. Trong ứng dụng phục vụ nhiều request, nên dùng `DataSource` có connection pool và cấu hình `SimpleJdbcCall` một lần ở tầng repository/service thay vì khởi tạo lại trong mỗi lần gọi.

### Bước 4: Chạy và đối chiếu kết quả

Tạo hai routine bằng `setup.sql` và cấp quyền phù hợp cho tài khoản kết nối. Thiết lập ba biến môi trường `DB_URL`, `DB_USER`, `DB_PASSWORD`; ví dụ `DB_URL` trỏ tới `jdbc:mysql://127.0.0.1:3306/spring_parameter_demo`. Tại thư mục chứa `pom.xml` chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=StoredRoutineParameterDemo
```

**Stdout dự kiến khi chạy đúng các routine và dữ liệu trong bài:**

```text
OUT out_tax = 20.00
INOUT inout_grand_total = 1220.00
FUNCTION invoice_tax = 20.00
```

Ba kết quả chỉ phụ thuộc phép tính của routine, không phụ thuộc dữ liệu bảng nào. Nếu account MySQL không có quyền `CREATE ROUTINE` hoặc `EXECUTE`, nếu sai schema/tên routine, hoặc nếu driver không kết nối được thì lệnh sẽ báo lỗi; không diễn giải lỗi kết nối thành lỗi của ba lớp tham số.

## 4. Đọc ví dụ theo đúng luồng xử lý

### Trước khi thực thi

1. `withProcedureName("accumulate_invoice")` xác định thủ tục sẽ gọi; đây không phải SQL `SELECT`.
2. `withoutProcedureColumnMetaDataAccess()` yêu cầu Spring **không dò metadata về danh sách tham số thủ tục** mà sử dụng các khai báo cung cấp.
3. `declareParameters(...)` định nghĩa đủ ba tham số theo **thứ tự signature trong DB**, với hướng và kiểu tương ứng.
4. `MapSqlParameterSource` cung cấp **hai** đầu vào: `in_net` và `inout_grand_total`. Không cung cấp `out_tax` làm đầu vào.

### Khi thực thi

Spring tạo lời gọi qua JDBC `CallableStatement`, bind các giá trị `IN` và `INOUT`, đăng ký kiểu đầu ra cho `OUT` và `INOUT`, rồi thực thi procedure. Sau đó Spring lấy kết quả và gắn các tên đầu ra vào `Map<String,Object>`.

### Sau khi thực thi

- `outputs.get("out_tax")` là giá trị mới do procedure tính, dù trước lời gọi không có biến Java tên `out_tax`.
- `outputs.get("inout_grand_total")` là **giá trị mới**; đối tượng `BigDecimal("1000.00")` ở đầu vào không bị sửa tại chỗ. Không đọc lại `inputs.getValue("inout_grand_total")` để kỳ vọng thấy `1220.00`.
- `executeFunction(BigDecimal.class, ...)` dành cho **kết quả trả về của stored function**, thay vì truy cập thủ công một key `OUT` trong kết quả `Map`. Với MySQL, function không khai báo đối số `OUT/INOUT`; một giá trị `RETURN` của function là khái niệm riêng.

Một cách hình dung nhanh:

```text
Java input Map:
    in_net = 200.00                 (SqlParameter: IN)
    inout_grand_total = 1000.00     (SqlInOutParameter: INOUT)
    [không có out_tax]              (SqlOutParameter: OUT)
             |
             v
  CALL accumulate_invoice(...)
             |
             v
Java result Map:
    out_tax = 20.00                 (OUT)
    inout_grand_total = 1220.00     (INOUT)
```

## 5. Tự động đọc metadata hay khai báo thủ công?

**Cách mặc định:** nếu driver và DBMS được hỗ trợ, `SimpleJdbcCall` có thể đọc metadata về tên/hướng/kiểu tham số. Ví dụ, có thể cấu hình ngắn hơn:

```java
// Fragment cấu hình; chạy khi driver cung cấp metadata đầy đủ.
SimpleJdbcCall procedure = new SimpleJdbcCall(jdbc)
        .withProcedureName("accumulate_invoice");
```

**Cách tường minh:** dùng `declareParameters(...)` để khai báo một phần hoặc toàn bộ tham số. Nếu **không** gọi `withoutProcedureColumnMetaDataAccess()`, Spring vẫn có thể dựa vào metadata cho các tham số chưa khai báo. Khi metadata driver thiếu, sai hoặc không nhất quán, nên khai báo **đầy đủ và đúng thứ tự** rồi tắt tra cứu metadata tham số như ví dụ chính.

Điều này giúp lời gọi dễ kiểm soát hơn, nhất là khi thủ tục có kiểu riêng hoặc metadata không nhất quán. Tuy nhiên, nó không đảm bảo DBMS/driver không bao giờ thực hiện bất kỳ thao tác metadata nào khác. Sau khi đổi signature stored procedure, **phải cập nhật khai báo Java**; Spring không tự phát hiện sự không khớp khi đã tắt metadata.

`useInParameterNames(...)` là tùy chọn bổ sung khi cần chỉ rõ tập tên đầu vào của một signature, ví dụ khi có nhiều biến thể lời gọi hàm. Nó không thay cho việc khai báo chính xác các tham số `OUT`, `INOUT` và kiểu SQL.

**Tên kết quả có thể khác chữ hoa/chữ thường tùy DBMS/driver.** Có thể cấu hình `JdbcTemplate.setResultsMapCaseInsensitive(true)` rồi đưa `JdbcTemplate` vào `SimpleJdbcCall` như ví dụ, đồng thời vẫn sử dụng tên SQL thật trong `declareParameters(...)`.

## 6. Kỹ thuật nâng cao có liên quan trực tiếp

### Đầu ra là `REF CURSOR` hoặc kiểu tùy biến

Một số cơ sở dữ liệu cho phép trả về cursor bằng tham số đầu ra. Khi driver và DBMS hỗ trợ, có thể khai báo `SqlOutParameter` cùng một `RowMapper`; đây là fragment khái niệm, **không phải routine MySQL của ví dụ**:

```java
// Fragment minh họa cho DBMS/driver hỗ trợ REF_CURSOR.
SqlOutParameter cursorParameter = new SqlOutParameter(
        "out_items",
        Types.REF_CURSOR,
        (rs, rowNum) -> rs.getString("item_name"));
```

Trong trường hợp này, tên `out_items` và JDBC type phải khớp giao thức cursor của DBMS. Một số driver yêu cầu constant hoặc xử lý vendor-specific. Với kiểu SQL phức tạp như `STRUCT`/`ARRAY`, Spring còn cung cấp `SqlReturnType` để xử lý giá trị OUT tùy chỉnh và `SqlTypeValue` cho dữ liệu IN đặc biệt.

Nếu thủ tục trả về **result set trực tiếp** (ví dụ một lệnh `SELECT` trong MySQL procedure) thay vì tham số `OUT REF CURSOR`, có thể dùng `SimpleJdbcCall.returningResultSet("items", rowMapper)`. Không khai báo tùy tiện một `SqlOutParameter` cho result set không có tên OUT tương ứng.

### Hàm trả về một giá trị so với procedure có một OUT

- `withFunctionName(...)` + `executeFunction(ExpectedClass.class, inputs)`: lấy **giá trị trả về của hàm**.
- `withProcedureName(...)` + `executeObject(ExpectedClass.class, inputs)`: tiện khi **procedure có một tham số OUT** thích hợp.
- `execute(inputs)`: phù hợp khi cần nhiều kết quả OUT, INOUT hoặc result set và muốn truy cập chúng bằng tên từ `Map`.

Không đánh đồng giá trị `RETURN` của function với tham số `OUT` của procedure. Nếu tự khai báo function return thay vì dùng metadata, quy ước vị trí/tên/kiểu của giá trị trả về tùy JDBC driver; nên dựa vào tài liệu driver và xác minh câu call thực tế.

### Giá trị `null` ở đầu vào hoặc đầu ra

Đối với `IN` hoặc `INOUT` có thể null, khai báo đúng `Types.X` và gán đầu vào bằng `MapSqlParameterSource.addValue(name, null, sqlType)` khi DBMS cho phép. Lưu ý phép cộng SQL với `NULL` có thể tạo kết quả `NULL`; routine phải quyết định rõ dùng `COALESCE` hay giữ `NULL`. Với `OUT`, map có thể chứa key mà giá trị là `null`: đừng ép kiểu hoặc gọi phương thức trên null mà chưa kiểm tra. Các kiểu `DECIMAL`, `NUMERIC` nên dùng `BigDecimal` thay cho `double` khi cần độ chính xác tiền tệ.

## 7. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Thiếu tham số đầu vào hoặc lỗi bind | Chỉ khai báo `SqlOutParameter` cho một tham số thực chất là `INOUT` | Đổi sang `SqlInOutParameter` và cung cấp giá trị đầu vào |
| Kết quả `OUT` bị thiếu trong `Map` | Chỉ khai báo `SqlParameter` hoặc dùng sai tên | Đối chiếu signature, khai báo `SqlOutParameter` và đọc đúng key |
| Lỗi số lượng/thứ tự tham số | Danh sách `declareParameters` không khớp thủ tục, đặc biệt khi tắt metadata | Đặt đúng thứ tự `IN`, `OUT`, `INOUT` và xác nhận kiểu |
| Lỗi chuyển đổi kiểu SQL | Dùng `Types.VARCHAR` cho `DECIMAL`, kiểu vendor-specific hoặc nhận dạng `null` sai | Tra schema/driver, dùng `Types` và converter thích hợp |
| `Map.get(...)` ra `null` dù gọi thành công | Tên key sai chữ hoa/thường hoặc procedure thực sự trả SQL `NULL` | Kiểm tra `keySet()` trong môi trường kiểm thử; cân nhắc result map không phân biệt chữ hoa/thường; kiểm tra logic SQL |
| Kết quả INOUT giữ giá trị cũ | Đọc lại input map hoặc procedure không gán lại tham số | Đọc result map; kiểm tra logic procedure |
| Procedure chạy nhưng dữ liệu không như mong đợi | Transaction, quyền, lỗi SQL hoặc kỳ vọng procedure tự COMMIT | Kiểm thử trên DB thật; quản lý transaction ở service khi phù hợp |
| Chạy ở DBMS khác bị lỗi | Cú pháp tạo routine, cách trả cursor/function và metadata khác MySQL | Viết SQL theo DBMS và xác nhận cách đăng ký kiểu OUT của driver |

**Checklist trước khi đưa vào sản phẩm:**

1. So sánh tên, thứ tự, hướng `IN/OUT/INOUT` và kiểu SQL với signature trong DB.
2. Với mỗi `IN` và `INOUT`, cung cấp giá trị đầu vào tương ứng; với mỗi `OUT` và `INOUT`, đọc đầu ra theo tên.
3. Kiểm thử các trường hợp giá trị bình thường, `null`, giới hạn `DECIMAL`, làm tròn và lỗi nghiệp vụ; không giả định mọi driver trả đúng cùng lớp Java cho mọi kiểu vendor-specific.
4. Kiểm tra quyền `EXECUTE`, schema/database, transaction và cấu hình connection pool; lỗi JDBC thường được Spring chuyển thành `DataAccessException`.
5. Nếu dùng khai báo thủ công để không lệ thuộc metadata, kiểm tra lại khi nâng cấp driver hoặc đổi signature routine. Chỉ log giá trị phù hợp với chính sách bảo mật.
6. Ưu tiên khởi tạo `SimpleJdbcCall` tại tầng data-access, tái sử dụng cấu hình và không sửa khai báo sau khi lời gọi được compile lần đầu.

## 8. Ghi nhớ

`SqlParameter` mô tả **dữ liệu đi vào**; `SqlOutParameter` mô tả **dữ liệu đi ra**; `SqlInOutParameter` mô tả **dữ liệu đi vào rồi đi ra với giá trị mới**. Ba lớp phối hợp với `SimpleJdbcCall.declareParameters(...)` để Spring JDBC biết cách thiết lập `CallableStatement`. `MapSqlParameterSource` mới là nơi chứa giá trị đầu vào, còn `Map` do `execute(...)` trả về chứa các đầu ra của procedure.

**Tài liệu chính thức:**

- [Spring Framework – Simplifying JDBC Operations with the SimpleJdbc Classes](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html): `SimpleJdbcCall`, khai báo tham số, metadata, procedure, function và cursor.
- [Spring Framework – SqlParameter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/SqlParameter.html): thuộc tính tên, SQL type, scale và phương thức liên quan.
- [Spring Framework – SqlOutParameter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/SqlOutParameter.html): khai báo đầu ra và cơ chế chuyển đổi kết quả.
- [Spring Framework – SqlInOutParameter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/SqlInOutParameter.html): tham số hai chiều.
- [MySQL 8.4 – CREATE PROCEDURE and CREATE FUNCTION](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html): quy tắc `IN`, `OUT`, `INOUT` và giá trị `RETURN`.

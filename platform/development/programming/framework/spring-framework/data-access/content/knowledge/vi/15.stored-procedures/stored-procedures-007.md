# Ánh xạ kết quả trả về bằng RowMapper khi gọi thủ tục và hàm

## 1. Bài toán và kết quả cần đạt

Trong **Spring Framework – Data Access**, một stored procedure (thủ tục lưu trữ) hoặc stored function (hàm lưu trữ) có thể nhận tham số, thực thi logic ở cơ sở dữ liệu và trả về dữ liệu. Khi đầu ra là **nhiều dòng, nhiều cột**, ứng dụng thường cần chuyển từng dòng của JDBC `ResultSet` thành đối tượng Java thay vì để tầng service xử lý `ResultSet` thô.

Spring JDBC cung cấp interface `RowMapper<T>` để định nghĩa phép chuyển đổi **một dòng → một đối tượng kiểu `T`**. Với kết quả của thủ tục/hàm, thường cấu hình `RowMapper` qua `SimpleJdbcCall.returningResultSet(...)` hoặc khai báo `SqlReturnResultSet`/tham số OUT cursor phù hợp.

Sau bài này, bạn có thể:
- Phân biệt đầu ra `ResultSet` thông thường, `REF_CURSOR` (con trỏ OUT), tham số OUT vô hướng và giá trị trả về của hàm.
- Viết `RowMapper<T>` đúng hợp đồng, dùng nhãn cột và kiểu dữ liệu JDBC an toàn.
- Gọi thủ tục bằng `SimpleJdbcCall`, ánh xạ thành `List<T>`, nhận đúng khóa trong kết quả `Map<String, Object>`.
- Xử lý nhiều `ResultSet`, giá trị `NULL`, lỗi nhầm tên cột, vấn đề driver/database và kiểm chứng kết quả.

**Giới hạn phạm vi:** các ví dụ dựa trên Spring JDBC và Java 17+. Không áp dụng máy móc cho JPA/Hibernate, R2DBC hay mọi kiểu trả về của stored function.

## 2. RowMapper hoạt động ở đâu trong chuỗi gọi thủ tục?

Một lời gọi điển hình:

~~~text
Mã Java (tham số đầu vào)
  -> SimpleJdbcCall.execute(...)
  -> JDBC CallableStatement
  -> PROCEDURE trong database
  -> JDBC ResultSet (hoặc REF_CURSOR được mở thành ResultSet)
  -> Spring duyệt từng dòng, gọi RowMapper.mapRow(rs, rowNum)
  -> List<EmployeeRow>
  -> output Map với khóa do cấu hình returningResultSet đặt ra
  -> Repository trả DTO cho Service
~~~

Hợp đồng:

~~~java
@FunctionalInterface
public interface RowMapper<T> {
    T mapRow(java.sql.ResultSet rs, int rowNum)
            throws java.sql.SQLException;
}
~~~

Đây là **chữ ký rút gọn để giải thích**, không phải mã cần tự khai báo: interface thật là `org.springframework.jdbc.core.RowMapper` của Spring JDBC. Một `mapRow` nhận **dòng hiện tại** của `ResultSet` và trả về đối tượng tương ứng. Spring di chuyển con trỏ và quản lý tài nguyên.

Quy tắc quan trọng:

1. **Không gọi `rs.next()` trong `mapRow`**: Spring đã chuyển đến dòng hiện tại. Gọi thêm làm mất dòng hoặc hỏng cơ chế lặp.
2. **Không đóng `ResultSet` hoặc connection**: Spring/JDBC quản lý vòng đời. Trả DTO/record đã copy dữ liệu ra khỏi result set.
3. **`rowNum` bắt đầu từ 0**, phục vụ logic phụ trợ như ghi nhận vị trí; không phải ID nghiệp vụ và không thay cho `ORDER BY`.
4. Giữ mapper **không trạng thái (stateless)** để tái sử dụng an toàn; tránh tích lũy danh sách, mở kết nối khác hoặc gây side effect bên trong callback.
5. `SQLException` từ đọc cột có thể truyền ra; Spring xử lý tại tầng truy cập dữ liệu. Đừng bắt và trả đối tượng giả khiến lỗi dữ liệu bị che giấu.

Ví dụ một mapper ngắn:

~~~java
RowMapper<EmployeeRow> mapper = (rs, rowNum) ->
    new EmployeeRow(
        rs.getLong("employee_id"),
        rs.getString("full_name"),
        rs.getBigDecimal("salary")
    );
~~~

Mỗi lần callback chạy, đối tượng `EmployeeRow` mới được tạo từ đúng một dòng. Với 0 dòng, kết quả tập hợp thường là danh sách rỗng; với 3 dòng, có 3 đối tượng.

## 3. Phân loại kiểu kết quả trước khi chọn RowMapper

Không phải mọi thủ tục hoặc hàm đều trả về danh sách.

| Kiểu kết quả từ database | Ví dụ | Cách xử lý trong Spring JDBC |
| --- | --- | --- |
| `ResultSet` xuất hiện khi thực thi thủ tục | MySQL procedure có `SELECT ...` | `SimpleJdbcCall.returningResultSet("employees", mapper)` |
| OUT parameter dạng `REF_CURSOR` / cursor | Thủ tục Oracle xuất cursor qua tham số OUT | `returningResultSet("tên_cursor_out", mapper)` khi được driver hỗ trợ và khai báo đúng |
| Một hoặc nhiều tham số OUT thông thường | `OUT total_count INT` | Khai báo `SqlOutParameter` và đọc giá trị trong `Map`; **không cần `RowMapper`** |
| Hàm trả giá trị vô hướng | Hàm trả `VARCHAR` hoặc `DECIMAL` | `withFunctionName(...).executeFunction(Type.class, ...)` |
| Hàm dạng tập hợp/bảng có thể truy vấn bằng `SELECT` | Một số table-valued/set-returning function | Có thể dùng `JdbcTemplate.query("SELECT ...", mapper, ...)` theo cú pháp DB |
| Nhiều `ResultSet` | Procedure phát nhiều lệnh `SELECT` | Khai báo nhiều `returningResultSet(...)` **theo đúng thứ tự** |

Tên ở `returningResultSet("employees", ...)` có **hai vai trò tùy database**:

- Với `ResultSet` không có tên được trả trực tiếp trong quá trình thực thi, `"employees"` là **khóa do ứng dụng đặt** để đọc danh sách trong output `Map`.
- Với `REF_CURSOR` là tham số OUT có tên, tên khai báo ở Java phải **khớp tên tham số cursor mà procedure dùng**; driver và cách khai báo tham số ảnh hưởng việc nhận cursor.

Vì vậy, không lấy tên bảng, tên DTO hay tên alias SQL rồi mặc định đó là tên cursor OUT. Xác nhận chữ ký routine và hành vi JDBC driver.

## 4. Ví dụ xuyên suốt: MySQL 8 trả ResultSet từ thủ tục

Giả sử cần liệt kê nhân viên của một phòng ban. Ví dụ này dùng **MySQL 8 + MySQL Connector/J + Spring JDBC**, vì MySQL procedure có thể trả kết quả `SELECT` trực tiếp. Các đoạn SQL dưới đây chạy trong môi trường MySQL có quyền tạo bảng/thủ tục; chúng không phải cú pháp dùng chung cho mọi DB.

### 4.1. Tạo dữ liệu

~~~sql
CREATE TABLE employees (
    id BIGINT PRIMARY KEY,
    department_id BIGINT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    salary DECIMAL(12, 2) NOT NULL
);

INSERT INTO employees (id, department_id, full_name, salary)
VALUES
    (101, 7, 'Lan', 2000.00),
    (102, 7, 'Minh', 2300.00),
    (103, 9, 'Hoa', 2800.00);
~~~

Thủ tục trả các dòng kèm **nhãn cột ổn định**. Với MySQL CLI, `DELIMITER` là chỉ thị của client để nhập thân procedure chứa dấu `;`; nó không phải lệnh SQL chuẩn gửi trực tiếp qua JDBC:

~~~sql
DELIMITER $$

CREATE PROCEDURE list_employees_by_department(
    IN p_department_id BIGINT
)
BEGIN
    SELECT
        id AS employee_id,
        full_name,
        salary
    FROM employees
    WHERE department_id = p_department_id
    ORDER BY id;
END$$

DELIMITER ;
~~~

Kiểm tra trước khi viết Java:

~~~sql
CALL list_employees_by_department(7);
~~~

Dữ liệu kỳ vọng:

| employee_id | full_name | salary |
| ---: | --- | ---: |
| 101 | Lan | 2000.00 |
| 102 | Minh | 2300.00 |

`ORDER BY id` giúp xác định thứ tự kết quả. Không dựa vào thứ tự tự nhiên của bảng, đặc biệt khi mapper hoặc business logic phụ thuộc vị trí.

### 4.2. DTO đầu ra bằng Java record

Tệp `EmployeeRow.java`:

~~~java
package example.data;

import java.math.BigDecimal;

public record EmployeeRow(
    long id,
    String fullName,
    BigDecimal salary
) {}
~~~

`record` là kiểu lưu dữ liệu phù hợp để chuyển ra khỏi tầng JDBC. Trong ví dụ này `id`, `full_name` và `salary` đều `NOT NULL`. Dùng `BigDecimal` cho `DECIMAL` để tránh sai số biểu diễn thập phân của `double` trong xử lý tiền tệ.

### 4.3. Repository gọi thủ tục và đăng ký RowMapper

Tệp `EmployeeProcedureRepository.java`:

~~~java
package example.data;

import java.sql.Types;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.stereotype.Repository;

@Repository
public class EmployeeProcedureRepository {

    private static final RowMapper<EmployeeRow> EMPLOYEE_MAPPER =
        (rs, rowNum) -> new EmployeeRow(
            rs.getLong("employee_id"),
            rs.getString("full_name"),
            rs.getBigDecimal("salary")
        );

    private final SimpleJdbcCall listEmployees;

    public EmployeeProcedureRepository(DataSource dataSource) {
        this.listEmployees = new SimpleJdbcCall(dataSource)
            .withProcedureName("list_employees_by_department")
            .withoutProcedureColumnMetaDataAccess()
            .declareParameters(
                new SqlParameter("p_department_id", Types.BIGINT)
            )
            .returningResultSet("employees", EMPLOYEE_MAPPER);
    }

    public List<EmployeeRow> findByDepartment(long departmentId) {
        Map<String, Object> out = listEmployees.execute(
            Map.of("p_department_id", departmentId)
        );

        Object raw = out.get("employees");
        if (!(raw instanceof List<?> rows)) {
            throw new IllegalStateException(
                "Procedure did not return the expected employees result set"
            );
        }
        return rows.stream().map(EmployeeRow.class::cast).toList();
    }
}
~~~

Đây là **mã thành phần Spring**, không phải một chương trình `main` có thể chạy chỉ với JDK. Cần ứng dụng có bean `DataSource` đã cấu hình, dependency `spring-jdbc`, Spring context và MySQL JDBC driver; chẳng hạn dự án Spring Boot có `spring-boot-starter-jdbc` cùng `mysql-connector-j` ở runtime. Không tạo hoặc đóng `DataSource` ở từng lời gọi.

Điểm cần hiểu:

1. `withProcedureName(...)` chọn thủ tục, không dùng `withFunctionName(...)` cho ví dụ này.
2. `withoutProcedureColumnMetaDataAccess()` tắt suy luận tham số từ JDBC metadata. Vì vậy ta **tự khai báo** IN parameter bằng `SqlParameter("p_department_id", Types.BIGINT)`. Cách này hữu ích khi metadata driver không ổn định, nhưng khai báo phải đúng chữ ký.
3. `returningResultSet("employees", EMPLOYEE_MAPPER)` đăng ký mapper cho result set trả trực tiếp; `employees` là khóa do Java chọn, **không phải** tham số trong thủ tục MySQL.
4. `execute(Map.of(...))` cung cấp tên và giá trị tham số IN. Đối với tham số có thể `null`, không dùng `Map.of` (nó không nhận `null`); chọn `MapSqlParameterSource` và khai báo SQL type tường minh.
5. Spring duyệt result set và gọi `EMPLOYEE_MAPPER.mapRow(...)` cho từng dòng. `out.get("employees")` trả danh sách đối tượng đã ánh xạ.
6. Đoạn kiểm tra `instanceof List<?>` giúp phát hiện cấu hình/driver không trả result set như dự kiến. `EmployeeRow.class::cast` kiểm tra kiểu phần tử khi tạo danh sách kết quả. Nếu hệ thống đã bảo đảm mapping, có thể dùng cast có kiểm soát với `@SuppressWarnings("unchecked")`.

Với dữ liệu SQL ở trên, gọi `findByDepartment(7L)` trả **hai** `EmployeeRow` theo ID 101, 102. Gọi `findByDepartment(99L)` thường trả **danh sách rỗng** nếu procedure đã thực thi và cho result set đúng cấu trúc nhưng không có dòng. Cần phân biệt danh sách rỗng với **thiếu khóa `"employees"`** do routine hoặc cấu hình không trả đúng kết quả.

Đối với thủ tục không có IN parameter, dùng `listEmployees.execute(Map.of())` nếu cấu hình và định nghĩa routine tương ứng. Không truyền một giá trị giả chỉ để gọi được method.

## 5. Tại sao ánh xạ theo nhãn cột?

Trong ví dụ, SQL trả `id AS employee_id`. Mapper phải lấy `rs.getLong("employee_id")` vì đó là **column label** của `ResultSet`. Nếu viết `rs.getLong("id")`, hành vi phụ thuộc driver và metadata; có thể lỗi `Column 'id' not found`.

Quy tắc thiết kế contract giữa procedure và Java:

| SQL output | Trường Java | Getter |
| --- | --- | --- |
| `id AS employee_id` | `id: long` | `rs.getLong("employee_id")` |
| `full_name` | `fullName: String` | `rs.getString("full_name")` |
| `salary` `DECIMAL(12,2)` | `salary: BigDecimal` | `rs.getBigDecimal("salary")` |

Nếu sửa câu `SELECT` bên trong procedure, phải xem đó là thay đổi **hợp đồng đầu ra**. Cần điều chỉnh mapper, integration test và các bên dùng DTO nếu tên hoặc kiểu cột thay đổi. Không dùng `SELECT *` cho contract ổn định.

### Xử lý NULL đúng nghĩa

Các getter cho kiểu nguyên thủy trả giá trị mặc định khi SQL `NULL`; ví dụ `rs.getLong("nullable_id")` trả `0` và chỉ `rs.wasNull()` ngay sau đó mới phân biệt được `NULL` với giá trị 0. Với dữ liệu nullable, cân nhắc:

~~~java
Long managerId = rs.getObject("manager_id", Long.class);
String nickname = rs.getString("nickname");
~~~

`managerId` có thể là `null` nếu driver hỗ trợ ánh xạ kiểu JDBC 4.2 tương ứng. Với driver cũ, dùng `getLong(...)` kết hợp `wasNull()` để xử lý rõ ràng. Không dùng primitive `long` cho trường hợp nghiệp vụ cần biểu diễn giá trị chưa có.

Với `DATE`/`TIMESTAMP`, chọn `LocalDate`/`LocalDateTime` hoặc `Instant` theo loại SQL và quy tắc múi giờ thực tế. Một số driver hỗ trợ `rs.getObject("created_date", LocalDate.class)`; giải pháp tương thích có thể phải chuyển từ `getDate(...)`. Không mặc định `TIMESTAMP WITHOUT TIME ZONE` có nghĩa là thời điểm UTC.

## 6. Một thủ tục trả nhiều ResultSet

Giả sử một procedure `department_report` thực thi theo thứ tự:

~~~sql
SELECT id AS employee_id, full_name, salary
FROM employees
WHERE department_id = p_department_id
ORDER BY id;

SELECT COUNT(*) AS employee_count
FROM employees
WHERE department_id = p_department_id;
~~~

**Đây là phần thân minh họa của procedure**, không phải file SQL độc lập để chạy; cần đặt vào cú pháp `CREATE PROCEDURE` theo database.

Khi driver trả **hai result set theo thứ tự**, có thể đăng ký:

~~~java
record DepartmentSummary(long employeeCount) {}

RowMapper<DepartmentSummary> summaryMapper =
    (rs, rowNum) ->
        new DepartmentSummary(rs.getLong("employee_count"));

SimpleJdbcCall reportCall = new SimpleJdbcCall(dataSource)
    .withProcedureName("department_report")
    .returningResultSet("employees", employeeMapper)
    .returningResultSet("summary", summaryMapper);

Map<String, Object> out = reportCall.execute(
    Map.of("p_department_id", 7L)
);
~~~

Ví dụ này là **mảnh mã Java trong một method/lớp đã có `dataSource` và `employeeMapper`**. Khi dùng metadata tự động, driver phải cung cấp metadata đủ để nhận `p_department_id`. Nếu tắt metadata, thêm khai báo `SqlParameter` như ví dụ đầy đủ ở mục 4.

Ý nghĩa:
- `out.get("employees")` là danh sách nhân viên từ `ResultSet` thứ nhất.
- `out.get("summary")` là danh sách `DepartmentSummary` từ `ResultSet` thứ hai (trong ví dụ, chỉ một phần tử chứa `employeeCount`).
- Thứ tự hai `returningResultSet(...)` **phải khớp** thứ tự result set mà driver công bố. Nếu routine đổi thứ tự hai lệnh `SELECT`, mapper có thể đọc sai cột và phát sinh lỗi.

Không suy diễn mỗi lệnh `SELECT` trong mọi routine luôn xuất hiện như một result set: một số DB/driver có semantics khác, có update counts xen kẽ hoặc tùy chọn driver ảnh hưởng chuỗi kết quả. Hãy kiểm tra trên database thực tế.

## 7. Trường hợp REF_CURSOR là tham số OUT

Một số hệ quản trị, đặc biệt Oracle, cho procedure mở cursor và đưa ra qua **OUT parameter**. Ở đây kết quả không chỉ là một result set vô danh. Tên cursor là thành phần của chữ ký procedure.

Khi driver và Spring JDBC hỗ trợ cách khai báo đó:

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(dataSource)
    .withProcedureName("find_employees")
    .returningResultSet("p_employees_cursor", employeeMapper);

Map<String, Object> out = call.execute(
    Map.of("p_department_id", 7L)
);
~~~

Đây là **mẫu cấu hình**, không phải chương trình độc lập hay cam kết tương thích mọi DB. Thủ tục giả định có OUT cursor thật sự tên `p_employees_cursor`. Với REF cursor, tham số phải được **đăng ký và xử lý theo driver**, và một số trường hợp cần cấu hình kiểu OUT tường minh bằng `SqlOutParameter` cùng `RowMapper`/kiểu SQL tương ứng. Nếu tắt metadata, hãy khai báo đủ IN/OUT và dùng loại cursor mà driver hỗ trợ; không áp dụng một hằng `Types` duy nhất cho mọi database.

Ngoài tên cursor, còn cần kiểm tra:
- Cursor có sống đủ lâu trong transaction hiện tại không? Một số cơ sở dữ liệu yêu cầu transaction đang mở khi đọc cursor.
- Driver trả cursor qua `CallableStatement.getObject(...)`, kiểu vendor riêng hay result set thường?
- Chữ ký procedure có ở schema/catalog nào, tên tham số có bị đổi chữ hoa/thường hay không?
- Có quyền `EXECUTE` và quyền truy cập dữ liệu bên dưới không?

**Không dùng `"employees"` tự đặt làm tên OUT cursor** nếu database thực sự khai báo `p_employees_cursor`; nếu muốn đổi tên logic ở service, đổi sau khi đã đọc đúng output của procedure.

## 8. Cách thấp hơn: JdbcTemplate.call và SqlReturnResultSet

`SimpleJdbcCall` thuận tiện cho các lời gọi cấu hình trước. Khi cần điều khiển `CallableStatement` trực tiếp, Spring JDBC có `JdbcTemplate.call(...)` và `SqlReturnResultSet`.

Ví dụ trên cùng thủ tục MySQL của mục 4 (một result set):

~~~java
List<SqlParameter> declared = List.of(
    new SqlParameter("p_department_id", Types.BIGINT),
    new SqlReturnResultSet("employees", EMPLOYEE_MAPPER)
);

Map<String, Object> out = jdbcTemplate.call(
    connection -> {
        CallableStatement cs = connection.prepareCall(
            "{call list_employees_by_department(?)}"
        );
        cs.setLong(1, departmentId);
        return cs;
    },
    declared
);
~~~

Đây là **mảnh mã đặt trong repository có sẵn `jdbcTemplate`, `departmentId` và `EMPLOYEE_MAPPER`**; cần imports `java.sql.CallableStatement`, `java.sql.Types`, `java.util.List`, `java.util.Map`, `org.springframework.jdbc.core.SqlParameter` và `org.springframework.jdbc.core.SqlReturnResultSet`.

`SqlReturnResultSet("employees", EMPLOYEE_MAPPER)` mô tả **result set trả từ thủ tục**, và Spring điền danh sách đã map vào `out` theo khóa `"employees"`. Đây không phải cách đọc một OUT integer hay scalar function. Với REF cursor OUT, cấu hình có thể là `SqlOutParameter("p_cursor", sqlCursorType, mapper)`, tùy database/driver.

Chọn một API phù hợp cho cùng một lời gọi; không cần vừa chạy `SimpleJdbcCall.execute(...)` vừa gọi lại `JdbcTemplate.call(...)` nếu chỉ muốn map kết quả một lần.

## 9. RowMapper thủ công và các mapper có sẵn

| Chiến lược | Khi nên dùng | Điều cần lưu ý |
| --- | --- | --- |
| Lambda hoặc lớp cài đặt `RowMapper<T>` | Cần kiểm soát tên cột, ép kiểu, default và domain DTO | Chữ ký cột phải đúng; tránh logic nghiệp vụ quá phức tạp |
| `BeanPropertyRowMapper<T>` | JavaBean có constructor không tham số, setter/getter phù hợp | Dựa vào tên property ↔ nhãn cột; không nên mặc định dùng trực tiếp cho immutable record |
| `DataClassRowMapper<T>` | Kiểu dữ liệu có constructor tham số/Java record với tên cột khớp | Cần constructor/property khớp tên và kiểu; kiểm tra chi phí reflection |
| `SingleColumnRowMapper<T>` | Result set một cột, mỗi dòng thành scalar | Không ánh xạ nhiều cột thành một DTO phức tạp |
| `ResultSetExtractor<T>` | Cần gom nhiều dòng thành một cấu trúc cha–con, map toàn bộ tập | Tự quyết định cách duyệt, không còn ánh xạ một dòng độc lập |
| `RowCallbackHandler` | Cần xử lý từng dòng với trạng thái/callback thay vì tạo List | Phải xem API procedure và chiến lược tài nguyên phù hợp |

Ví dụ, nếu muốn tự động map record `EmployeeRow(long id, String fullName, BigDecimal salary)`, output SQL nên có nhãn cột tương ứng với `id`, `full_name`, `salary`; khi đó cân nhắc `DataClassRowMapper.newInstance(EmployeeRow.class)`. Với ví dụ sử dụng nhãn `employee_id` nhưng property Java tên `id`, mapper thủ công trong mục 4 biểu đạt ánh xạ chính xác hơn.

Không ép mọi trường hợp sang mapper tự động: khi procedure có nhiều phép tính, cột tổng hợp, enum hay JSON, một mapper thủ công rõ ràng thường dễ review và kiểm tra.

## 10. Những điểm đặc biệt của stored function

**Stored function trả scalar** như tên, tổng tiền, số lượng: dùng API chuyên dụng:

~~~java
SimpleJdbcCall getName = new SimpleJdbcCall(dataSource)
    .withFunctionName("get_employee_name");

String name = getName.executeFunction(
    String.class,
    Map.of("p_employee_id", 101L)
);
~~~

Đây là **mảnh mã phụ thuộc chữ ký và metadata của hàm trong database**. Không nên dựng `RowMapper` nếu không có bảng kết quả nhiều dòng; dữ liệu chính là một giá trị trả về.

**Stored function trả một tập dòng:** một số DB có cú pháp phù hợp như `SELECT * FROM some_function(?)`, khi đó có thể dùng `JdbcTemplate.query(sql, rowMapper, args...)`. Cách khác là chức năng cursor OUT. Chọn dựa trên **cách driver phơi bày kết quả**, không dựa duy nhất vào từ khóa “function”.

Ví dụ bảng kết quả truy vấn được (cú pháp minh họa, chỉ dùng khi DB cho phép):

~~~java
List<EmployeeRow> rows = jdbcTemplate.query(
    "SELECT employee_id, full_name, salary " +
    "FROM some_set_returning_function(?)",
    EMPLOYEE_MAPPER,
    departmentId
);
~~~

Không lấy ví dụ `SELECT ... FROM function(?)` của một DB áp sang MySQL/Oracle/SQL Server mà chưa kiểm tra cú pháp function tương ứng.

## 11. Lỗi thường gặp và cách nhận biết

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `out.get("employees")` là `null` | Sai tên khóa, procedure không trả result set, hoặc đăng ký result set sai | Kiểm tra chữ ký procedure, output keys, thứ tự result sets và driver |
| Lỗi “column not found” | Mapper đọc `id` trong khi SQL alias là `employee_id` | Kiểm tra nhãn cột thực tế của result set và SQL `AS` |
| Thiếu hoặc đảo dữ liệu | Mapper dùng sai thứ tự `ResultSet` khi procedure trả nhiều tập | Kiểm tra thứ tự `SELECT` / `returningResultSet(...)` |
| Giá trị 0 thay cho thiếu dữ liệu | Getter primitive gặp SQL `NULL` | Dùng `wasNull()` hoặc kiểu wrapper |
| Không tìm được procedure / sai số tham số | Sai schema/catalog, chữ ký, kiểu SQL, metadata | Khai báo IN/OUT tường minh, cấu hình schema và kiểm tra tên |
| Kết quả không có sau khi đóng transaction | Cursor phụ thuộc vòng đời transaction hoặc tài nguyên bị đóng | Map dữ liệu **bên trong** phạm vi con trỏ còn hợp lệ |
| Khác nhau giữa môi trường dev/prod | DB, version driver, quyền hoặc metadata khác | Integration test trên cùng loại DB và driver |
| Bộ nhớ tăng mạnh | Procedure trả quá nhiều dòng rồi Spring gom toàn bộ thành `List` | Giới hạn kết quả, paging theo nghiệp vụ hoặc chọn cách xử lý stream phù hợp |

Với Spring JDBC, `SQLException` thường được dịch thành `DataAccessException`. Đừng chỉ catch `SQLException` quanh `SimpleJdbcCall.execute(...)`; hãy quan sát exception ở tầng Spring, truy nguyên cause để tìm SQLState/vendor code khi điều tra. Nếu ứng dụng dùng `@Transactional`, chú ý cách ngoại lệ truyền qua boundary và rollback.

**An toàn và hiệu năng:** gắn tham số đầu vào qua JDBC placeholders/`SqlParameterSource` thay vì nối chuỗi dữ liệu người dùng; không cho dữ liệu tùy ý trở thành tên thủ tục hoặc SQL identifier. Mapper nên thuần chuyển đổi, tránh gọi thêm query cho từng dòng (mẫu N+1) hoặc in log dữ liệu nhạy cảm. `RowMapper` không mặc định stream/lazy-load: danh sách do `returningResultSet` trả về thường đã được materialize.

## 12. Kiểm thử đúng điều cần bảo đảm

Ưu tiên **integration test** với cơ sở dữ liệu và driver thực tế, vì hành vi stored procedure/REF_CURSOR/metadata không thể được xác nhận chỉ bằng unit test cho `RowMapper`.

Những tình huống nên kiểm tra:

1. **Một dòng và nhiều dòng:** gọi `CALL list_employees_by_department(7)` trả hai dòng, mapper tạo hai `EmployeeRow` đúng ID, tên và `BigDecimal`.
2. **Không có dữ liệu:** gọi với phòng ban không tồn tại, nhận danh sách rỗng thay vì thiếu key hoặc `null` do sai cấu hình.
3. **Thay đổi column label:** tạm đổi alias trong môi trường test; chứng minh test bắt lỗi mapping thay vì âm thầm gán sai cột.
4. **Giá trị nullable:** thêm trường nullable nếu schema cho phép, xác minh phân biệt SQL `NULL` và 0/rỗng.
5. **Multiple result sets:** xác minh thứ tự, kiểu phần tử, khóa output và các update counts có thể xen giữa nếu procedure thực hiện DML.
6. **REF cursor và transaction:** với DB sử dụng OUT cursor, kiểm tra việc đọc trước khi transaction đóng, tên OUT, đăng ký kiểu và quyền truy cập.
7. **Lỗi database:** thủ tục không tồn tại, sai SQL type hoặc thiếu quyền phải tạo lỗi quan sát được; không chuyển thành danh sách rỗng.
8. **Tải lớn:** kiểm tra kích thước danh sách, thời gian, bộ nhớ và phương án phân trang khi result set có thể rất lớn.

Một phép kiểm thử độc lập cho mapper có thể tạo hoặc mock `ResultSet` với đúng nhãn cột, sau đó gọi `EMPLOYEE_MAPPER.mapRow(rs, 0)` và kiểm tra DTO. Cách này chứng minh logic ánh xạ **một dòng**, nhưng không chứng minh đường đi của stored procedure. Cần thêm integration test riêng cho cấu hình `SimpleJdbcCall` và driver.

Để chạy hai tệp Java ở mục 4 như thành phần ứng dụng, cần build của dự án Spring với thư viện và datasource tương ứng; **không thể dùng `javac EmployeeProcedureRepository.java` đơn độc mà thiếu Spring JDBC trên classpath**. Ví dụ không hứa một stdout cố định vì output phụ thuộc dữ liệu/database/driver. Có thể xác nhận dữ liệu bằng `CALL list_employees_by_department(7)` trước rồi so sánh các trường trả về trong assertion.

## 13. Checklist khi triển khai

- [ ] Đã xác định routine trả `ResultSet` trực tiếp, REF cursor hay scalar?
- [ ] Đã đăng ký đúng `withProcedureName`/`withFunctionName`, IN/OUT và schema?
- [ ] `returningResultSet(name, mapper)` dùng đúng **khóa logic** hoặc đúng **tên OUT cursor** theo trường hợp?
- [ ] Nếu nhiều result set, thứ tự mapper khớp thứ tự driver trả?
- [ ] Mapper lấy đúng column label, SQL type, `NULL` và timezone?
- [ ] Mapper không tự gọi `rs.next()`/`close()` và không tạo side effect?
- [ ] Danh sách rỗng được phân biệt với thiếu result set, và lỗi không bị nuốt?
- [ ] Có integration test trên đúng DB/driver, kể cả đường đi exception/transaction?
- [ ] Dữ liệu đầu ra có giới hạn hợp lý, không gây thiếu bộ nhớ?

## Tài liệu tham khảo

- [Spring Framework – SimpleJdbcCall, Stored Function, Returning ResultSet/REF Cursor](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/simple.html): cấu hình `SimpleJdbcCall`, `returningResultSet`, output `Map`, metadata và cách gọi function.
- [Spring Framework – RowMapper Javadoc (6.2)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/RowMapper.html): hợp đồng `mapRow(ResultSet, int)`, không gọi `next()`.
- [Spring Framework – SqlReturnResultSet Javadoc (6.2)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/SqlReturnResultSet.html): mô tả result set trả từ thủ tục và các cách mapping.
- [Spring Framework – JDBC Core](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html): `JdbcTemplate`, `RowMapper`, xử lý tài nguyên và exception.
- [Java SE 17 – ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): getter, `wasNull()`, con trỏ và nhãn cột.

# RowMapper ánh xạ một hàng thành đối tượng trong Spring JDBC

## 1. Từ hàng dữ liệu SQL đến đối tượng Java

Giả sử cơ sở dữ liệu có bảng `employees`, gồm các cột `id`, `full_name`, `salary`, `manager_id` và `hired_on`. Một câu `SELECT` trả về các hàng trong `ResultSet`, nhưng service Java lại muốn sử dụng đối tượng `Employee` có tên thuộc tính rõ ràng và kiểu dữ liệu phù hợp.

Trong JDBC thủ công, bạn thường phải tự duyệt `ResultSet` rồi gọi `rs.getLong(...)`, `rs.getString(...)`, `rs.getBigDecimal(...)` để tạo từng đối tượng. Spring JDBC đưa phần lặp và quản lý tài nguyên cho `JdbcTemplate`, còn phần chuyển **một hàng thành một đối tượng** cho `RowMapper<T>`.

`RowMapper<T>` là interface trong `org.springframework.jdbc.core`. Hợp đồng trung tâm của nó:

```java
@FunctionalInterface
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
```

Đây là **chữ ký rút gọn để học**, không phải mã sao chép nguyên vẹn từ file nguồn Spring (bản thực có các annotation/API documentation tùy phiên bản). `T` là kiểu đối tượng mà mỗi hàng sẽ được chuyển thành; ví dụ `RowMapper<Employee>` tạo `Employee`, `RowMapper<String>` tạo `String`.

Ba nguyên tắc cốt lõi:

1. **Một lần gọi `mapRow` xử lý một hàng hiện tại.** Spring đã đưa con trỏ `ResultSet` đến hàng đó trước khi gọi bạn.
2. **`mapRow` chỉ đọc hàng và tạo giá trị trả về.** Không gọi `rs.next()`, `rs.close()`, không cất `ResultSet` vào field để đọc sau.
3. **`JdbcTemplate` chịu trách nhiệm lặp các hàng và đóng tài nguyên JDBC mà nó quản lý.** Bạn cung cấp ánh xạ cột → đối tượng và xử lý các quy tắc chuyển đổi của ứng dụng.

### 1.1. Sơ đồ luồng xử lý

```text
Repository / DAO
    |
    | query(SQL, RowMapper<Employee>, parameters...)
    v
JdbcTemplate
    |  tạo/bind PreparedStatement, thực thi SQL
    v
ResultSet
    |  next() --> hàng 1 --mapRow(rs, 0)--> Employee 1
    |  next() --> hàng 2 --mapRow(rs, 1)--> Employee 2
    |  next() --> hàng 3 --mapRow(rs, 2)--> Employee 3
    |  next() --> hết dữ liệu
    v
List<Employee> (với query trả danh sách)
    |
    v
Service nhận dữ liệu Java, không nhận ResultSet
```

Hình trên mô tả trường hợp `JdbcTemplate.query(sql, rowMapper, ...)` trả về một danh sách. Các overload khác như `queryForObject` có hợp đồng số hàng khác, nhưng mỗi hàng vẫn được ánh xạ theo cùng ý tưởng. `RowMapper` không tự quyết định query phải trả một hàng hay nhiều hàng.

### 1.2. Vì sao phải tách RowMapper?

Tách mapper khỏi SQL giúp:

- Tái sử dụng một phép ánh xạ thống nhất cho `findAll`, `findById`, `search`.
- Giữ SQL/DAO chịu trách nhiệm chọn hàng, lọc, sort và bind tham số; mapper chịu trách nhiệm chuyển cột được trả về thành mô hình Java.
- Kiểm soát alias cột, kiểu số, ngày giờ, giá trị `NULL` và cách dựng object immutable.
- Tránh lặp code `new Employee(...)` tại mọi câu query.
- Kiểm thử riêng ánh xạ (đặc biệt với cột nullable hoặc schema thay đổi).

**Giới hạn:** `RowMapper` không tự tạo SQL, không ngăn SQL injection, không giữ transaction, không giải quyết N+1 query, không thay thế thiết kế mô hình dữ liệu. Nó là một điểm mở rộng hẹp nhưng rất quan trọng cho việc đọc từng hàng.

## 2. Hiểu chính xác `mapRow(ResultSet rs, int rowNum)`

### 2.1. `ResultSet rs` đã ở đúng hàng

Bộ phận thực hiện câu query (thường `JdbcTemplate`) điều khiển vòng lặp và gọi callback khi con trỏ đang trỏ vào một hàng hợp lệ. Mapper lấy giá trị từ **hàng hiện tại** bằng tên/nhãn cột hoặc vị trí cột.

```java
RowMapper<Employee> mapper = (rs, rowNum) ->
        new Employee(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getBigDecimal("salary"),
                rs.getObject("manager_id", Long.class),
                rs.getObject("hired_on", LocalDate.class));
```

Đây là **đoạn trích**, giả định record `Employee` đã được định nghĩa và các cột/alias có trong SQL. Mỗi lần thực thi lambda là một lần tạo đối tượng mới từ một hàng.

Không làm như sau:

```java
// SAI: JdbcTemplate đã gọi rs.next() trước khi chạy mapRow.
RowMapper<String> wrong = (rs, rowNum) -> {
    rs.next(); // Nhảy qua hàng kế tiếp; có thể bỏ sót và gây lỗi ở cuối.
    return rs.getString("full_name");
};
```

Tại cuối tập kết quả, `rs.next()` có thể trả `false`, và đọc cột khi không còn đứng trên hàng hợp lệ sẽ gây lỗi. Với các driver khác nhau, triệu chứng có thể khác, nhưng nguyên tắc luôn là **không điều khiển con trỏ trong `RowMapper`**.

### 2.2. `rowNum` không phải ID của bản ghi

Tham số thứ hai là số thứ tự ánh xạ do Spring cung cấp; thông thường bắt đầu từ **0** cho hàng đầu tiên của mỗi lần query và tăng theo số hàng đã duyệt.

```java
List<String> labels = jdbc.query(
        "SELECT id, full_name FROM employees ORDER BY id",
        (rs, rowNum) -> rowNum + ":" + rs.getString("full_name"));
```

Với các hàng `Lan`, `Minh`, `Hoa` theo thứ tự `id`, kết quả là:

```text
[0:Lan, 1:Minh, 2:Hoa]
```

Cần phân biệt:

- `rowNum` là vị trí hàng trong **kết quả của lần query**, bắt đầu từ 0.
- `rs.getLong("id")` là khóa do cơ sở dữ liệu lưu.
- Vị trí tham số JDBC trong `PreparedStatement.setXxx(index, ...)` bắt đầu từ **1**.
- Vị trí cột JDBC khi đọc `rs.getXxx(columnIndex)` cũng bắt đầu từ **1**.
- Nếu SQL không có `ORDER BY`, database không cam kết thứ tự hàng; `rowNum` không phải định danh ổn định để dùng trong cache, business key hoặc pagination.

`rowNum` hữu ích khi đánh số thứ tự hiển thị hoặc theo dõi lỗi ánh xạ trong một query, nhưng không nên biến nó thành khóa miền.

### 2.3. Mapper trả về gì?

`mapRow` có thể tạo record, POJO, DTO, một trường đơn lẻ hoặc kiểu chuyên biệt, tùy tham số generic `T`.

```java
RowMapper<String> titleMapper =
        (rs, rowNum) -> rs.getString("title");

RowMapper<BigDecimal> salaryMapper =
        (rs, rowNum) -> rs.getBigDecimal("salary");
```

Các đoạn trên dùng cột đã SELECT tương ứng và import `RowMapper`, `BigDecimal`. `RowMapper` API cho phép mapper trả `null` trong một số tình huống, nhưng với DTO nghiệp vụ nên nhất quán trả object hợp lệ, hoặc định nghĩa rõ ngữ nghĩa nullable. Đừng dùng `null` để che một lỗi SQL hoặc vi phạm dữ liệu.

### 2.4. Xử lý SQLException đúng cách

`mapRow` khai báo `throws SQLException`. Nếu driver báo sai tên cột, conversion thất bại hoặc phát sinh lỗi JDBC, bạn thường để `SQLException` đi ra ngoài callback. `JdbcTemplate` sẽ dịch lỗi JDBC theo `SQLExceptionTranslator` sang nhánh `DataAccessException` unchecked phù hợp khi có thể.

```java
RowMapper<Employee> mapper = (rs, rowNum) ->
        new Employee(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getBigDecimal("salary"),
                rs.getObject("manager_id", Long.class),
                rs.getObject("hired_on", LocalDate.class));
```

Không cần bao quanh từng `getXxx` bằng `try/catch(SQLException)` để trả object giả. Nếu logic trong mapper chủ động ném `IllegalArgumentException` (lỗi ứng dụng), đó không mặc nhiên là một `SQLException` được dịch. Cân nhắc hợp đồng lỗi và thông tin chẩn đoán của từng tầng.

## 3. Ánh xạ chính xác theo cột, alias và kiểu Java

### 3.1. Tên cột và alias là phần của hợp đồng query

Giả sử schema lưu `full_name` nhưng record Java có field `name`. Trong SQL ta đặt alias:

```sql
SELECT
    id,
    full_name AS display_name,
    salary,
    manager_id,
    hired_on
FROM employees
ORDER BY id
```

Trong mapper đọc nhãn `display_name`:

```java
String name = rs.getString("display_name");
```

`ResultSet.getString("display_name")` tìm **column label** trong kết quả (alias nếu có). Nếu câu SQL không chọn cột/alias đó, mapper sẽ gặp lỗi đọc cột. Điều này đặc biệt dễ xảy ra khi cùng mapper được dùng cho nhiều truy vấn nhưng một query lại thiếu trường cần thiết.

Khi query `JOIN` nhiều bảng đều có cột `id` hoặc `name`, đặt alias rõ ràng như `employee_id`, `department_name` để tránh mơ hồ. Đừng dựa vào thứ tự `SELECT *` hoặc ngầm định tên cột sau khi schema thay đổi.

### 3.2. Lấy đúng kiểu dữ liệu

Một số mapping thông dụng:

| SQL column | JDBC getter thường dùng | Java type | Cần lưu ý |
| --- | --- | --- | --- |
| `BIGINT NOT NULL` | `getLong` | `long`/`Long` | `getLong` với SQL `NULL` trả 0, cần `wasNull` nếu nullable |
| `VARCHAR` | `getString` | `String` | SQL `NULL` thường trả Java `null` |
| `DECIMAL(p,s)` | `getBigDecimal` | `BigDecimal` | Giữ độ chính xác tiền; scale theo dữ liệu và DB |
| `INTEGER` | `getInt` | `int`/`Integer` | Phân biệt 0 và SQL `NULL` |
| `BOOLEAN` | `getBoolean` | `boolean`/`Boolean` | Với nullable, cần kiểm tra `wasNull`/`getObject` |
| `DATE` | `getDate` rồi `toLocalDate` hoặc `getObject(..., LocalDate.class)` | `LocalDate` | Driver JDBC 4.2 và dialect cần hỗ trợ |
| `TIMESTAMP` | `getTimestamp` hoặc getter phù hợp | `LocalDateTime`/`Instant` theo hợp đồng | Múi giờ và diễn giải instant cần quy định rõ |
| `BINARY` / `VARBINARY` | `getBytes` | `byte[]` | Mutable array; kiểm soát kích thước dữ liệu |

Không nên ép giá trị tiền từ `DECIMAL` vào `double` rồi dùng phép cộng nhị phân nếu yêu cầu chính xác. Với ngày giờ, xác định rõ cơ sở dữ liệu lưu local datetime, UTC instant hay timezone-aware type; việc mapper trả đúng Java type chưa đủ để bảo đảm ý nghĩa thời gian.

### 3.3. SQL NULL và giá trị nguyên thủy

Đây là một lỗi có thể gây hỏng dữ liệu âm thầm:

```java
long managerId = rs.getLong("manager_id");
```

Nếu `manager_id` là SQL `NULL`, `getLong` trả giá trị mặc định `0`. Bạn cần gọi `rs.wasNull()` **ngay sau getter tương ứng**:

```java
long raw = rs.getLong("manager_id");
Long managerId = rs.wasNull() ? null : raw;
```

Hoặc, nếu driver hỗ trợ tốt chuyển kiểu JDBC 4.2, dùng:

```java
Long managerId = rs.getObject("manager_id", Long.class);
```

Với `NULL`, kết quả mong muốn là Java `null`, không phải mã người quản lý 0. Getter `rs.wasNull()` kiểm tra **lần đọc cột cuối cùng**; nếu đọc thêm cột khác rồi mới gọi, nó kiểm tra nhầm. Tránh kiểu nguyên thủy cho trường nullable nếu ứng dụng cần phân biệt thiếu giá trị và giá trị 0/false.

### 3.4. Bắt buộc và tùy chọn là hai hợp đồng khác nhau

Một cột được xác định `NOT NULL` trong DB có thể an toàn khi đọc bằng `getLong`/`getString` với giả định không null theo schema. Nhưng nếu dữ liệu từ view, `LEFT JOIN` hoặc query phức tạp có thể là `NULL`, phải đánh giá **hợp đồng của result set**, không suy luận từ bảng gốc.

Ví dụ với `LEFT JOIN`:

```sql
SELECT
    e.id,
    d.name AS department_name
FROM employees e
LEFT JOIN departments d ON d.id = e.department_id
```

`department_name` có thể `NULL` vì không có department, dù cột `departments.name` được khai báo NOT NULL. Nếu mapper cần trạng thái "chưa có phòng ban", dùng `String departmentName` nullable hoặc kiểu miền thể hiện rõ tình huống. Chỉ sinh giá trị mặc định như `"N/A"` khi đó thực sự là quy tắc nghiệp vụ.

## 4. Ví dụ chạy được: Java 17+, Spring JDBC và H2

Để nhìn rõ `RowMapper` vận hành, ta viết một chương trình **Spring Framework thuần** (không cần Spring Boot). Một mapper cho record immutable `Employee` được dùng trong nhiều query; phần SQL chọn hàng thay đổi nhưng cách chuyển một hàng thành `Employee` giữ nguyên.

Phiên bản ví dụ: Java 17+, Spring Framework 6.2.12, H2 2.3.232. Các phiên bản được **ghim để dễ tái lập**, không khẳng định là phiên bản mới nhất.

### 4.1. Cấu trúc project

```text
row-mapper-demo/
├── pom.xml
└── src/main/java/example/RowMapperDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>row-mapper-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/RowMapperDemo.java`:

```java
package example;

import java.math.BigDecimal;
import java.sql.Date;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class RowMapperDemo {
    // Immutable record: trường hợp phù hợp với ánh xạ qua constructor.
    record Employee(
            long id,
            String name,
            BigDecimal salary,
            Long managerId,
            LocalDate hiredOn) {}

    // Cùng bộ cột/alias cho tất cả query trả về Employee.
    private static final String SELECT_EMPLOYEE = """
            SELECT
                id,
                full_name AS display_name,
                salary,
                manager_id,
                hired_on
            FROM employees
            """;

    // Mapper stateless và có thể tái sử dụng.
    private static final RowMapper<Employee> EMPLOYEE_MAPPER =
            (rs, rowNum) -> new Employee(
                    rs.getLong("id"),
                    rs.getString("display_name"),
                    rs.getBigDecimal("salary"),
                    rs.getObject("manager_id", Long.class),
                    rs.getObject("hired_on", LocalDate.class));

    static final class EmployeeDao {
        private final JdbcTemplate jdbc;

        EmployeeDao(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        List<Employee> findAll() {
            return jdbc.query(
                    SELECT_EMPLOYEE + " ORDER BY id",
                    EMPLOYEE_MAPPER);
        }

        List<Employee> findAtLeast(long minId) {
            return jdbc.query(
                    SELECT_EMPLOYEE + " WHERE id >= ? ORDER BY id",
                    EMPLOYEE_MAPPER,
                    minId);
        }

        Optional<Employee> findOptional(long id) {
            List<Employee> rows = jdbc.query(
                    SELECT_EMPLOYEE + " WHERE id = ?",
                    EMPLOYEE_MAPPER,
                    id);
            return rows.stream().findFirst();
        }

        Employee requireOne(long id) {
            return jdbc.queryForObject(
                    SELECT_EMPLOYEE + " WHERE id = ?",
                    EMPLOYEE_MAPPER,
                    id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource source = new DriverManagerDataSource();
            source.setDriverClassName("org.h2.Driver");
            source.setUrl("jdbc:h2:mem:rowmapperdemo;DB_CLOSE_DELAY=-1");
            source.setUsername("sa");
            source.setPassword("");
            return source;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        EmployeeDao employeeDao(JdbcTemplate jdbc) {
            return new EmployeeDao(jdbc);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            EmployeeDao dao = context.getBean(EmployeeDao.class);

            jdbc.execute("""
                    CREATE TABLE employees (
                        id BIGINT PRIMARY KEY,
                        full_name VARCHAR(80) NOT NULL,
                        salary DECIMAL(12,2) NOT NULL,
                        manager_id BIGINT,
                        hired_on DATE NOT NULL
                    )
                    """);

            String insert = """
                    INSERT INTO employees (
                        id, full_name, salary, manager_id, hired_on
                    ) VALUES (?, ?, ?, ?, ?)
                    """;

            jdbc.update(insert, 1L, "Lan",
                    new BigDecimal("1000.50"), null,
                    Date.valueOf(LocalDate.of(2024, 1, 15)));
            jdbc.update(insert, 2L, "Minh",
                    new BigDecimal("1200.00"), 1L,
                    Date.valueOf(LocalDate.of(2024, 2, 2)));
            jdbc.update(insert, 3L, "Hoa",
                    new BigDecimal("900.25"), 1L,
                    Date.valueOf(LocalDate.of(2024, 3, 10)));

            System.out.println("All: " + dao.findAll());
            System.out.println("One: " + dao.requireOne(2L));
            System.out.println("Missing optional: " + dao.findOptional(99L));
            System.out.println("From id 2: " +
                    dao.findAtLeast(2L).stream()
                            .map(Employee::name)
                            .toList());

            List<String> rowNumbers = jdbc.query(
                    "SELECT full_name FROM employees ORDER BY id",
                    (rs, rowNum) ->
                            rowNum + ":" + rs.getString("full_name"));
            System.out.println("rowNum: " + rowNumbers);

            try {
                dao.requireOne(99L);
            } catch (EmptyResultDataAccessException ex) {
                System.out.println("Missing required: " +
                        ex.getClass().getSimpleName());
            }
        }
    }
}
```

Dùng Maven trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.RowMapperDemo
```

Các dòng do `System.out.println` của chương trình in ra (không bao gồm log nếu công cụ build có phát sinh):

```text
All: [Employee[id=1, name=Lan, salary=1000.50, managerId=null, hiredOn=2024-01-15], Employee[id=2, name=Minh, salary=1200.00, managerId=1, hiredOn=2024-02-02], Employee[id=3, name=Hoa, salary=900.25, managerId=1, hiredOn=2024-03-10]]
One: Employee[id=2, name=Minh, salary=1200.00, managerId=1, hiredOn=2024-02-02]
Missing optional: Optional.empty
From id 2: [Minh, Hoa]
rowNum: [0:Lan, 1:Minh, 2:Hoa]
Missing required: EmptyResultDataAccessException
```

### 4.2. Mỗi dòng output chứng minh điều gì?

- `All`: `findAll()` nhận một `List<Employee>` gồm ba bản ghi; mapper chạy ba lần, mỗi lần tạo một record mới từ hàng hiện tại. `ORDER BY id` xác định thứ tự trình bày.
- `One`: `queryForObject` gọi cùng mapper, nhưng hợp đồng của phương thức là **đúng một hàng**; `Employee[id=2,...]` được tạo từ hàng có `id = 2`.
- `Missing optional`: `query(...)` không tìm thấy hàng nên trả danh sách rỗng; `findOptional(...)` đổi sang `Optional.empty`. Mapper **không được gọi** khi không có hàng.
- `From id 2`: thay đổi điều kiện SQL không bắt buộc thay đổi mapper vì tập cột/alias vẫn đủ. `Employee::name` chỉ lấy tên sau khi đã có kết quả Java.
- `rowNum`: lambda đọc số thứ tự 0,1,2 do `JdbcTemplate` cung cấp, độc lập với giá trị `id` ở database.
- `Missing required`: cùng mapper nhưng gọi bằng `queryForObject` khi không có hàng sẽ ném `EmptyResultDataAccessException`, khác với hợp đồng `Optional`.
- `managerId=null` của `Lan`: getter typed `getObject("manager_id", Long.class)` giữ nguyên ý nghĩa SQL `NULL`. `BigDecimal` giữ số tiền ở dạng thập phân; `LocalDate` thể hiện cột DATE.

**Về tài nguyên:** `DriverManagerDataSource` không có connection pool; nó được dùng vì dễ chạy demo. Ứng dụng server nên sử dụng `DataSource`/pool phù hợp (ví dụ HikariCP), không suy ra từ demo rằng mở connection mới cho mỗi request là tối ưu. `DB_CLOSE_DELAY=-1` là tùy chọn H2 để dữ liệu bộ nhớ tồn tại qua các connection trong cùng tiến trình.

### 4.3. Vì sao mapper dùng chung được?

`EMPLOYEE_MAPPER` được khai báo `static final` để dùng chung cho mọi query. Điều khiến nó an toàn là **không giữ mutable state**: lambda chỉ đọc `ResultSet` hiện tại, tạo `Employee` mới và trả nó về. `final` chỉ cố định tham chiếu, không tự biến mapper có field mutable thành thread-safe.

Nếu mapper giữ `ArrayList` hay biến đếm chung rồi thay đổi mỗi lần gọi, hai request đồng thời có thể trộn dữ liệu. Mọi accumulator cần cho một query nên thuộc **mỗi lời gọi** hoặc do `JdbcTemplate` sở hữu thông qua danh sách kết quả.

## 5. RowMapper kết hợp các phương thức query như thế nào?

### 5.1. `query`: 0 đến nhiều hàng

```java
List<Employee> employees = jdbc.query(
        "SELECT id, full_name AS display_name, salary, manager_id, hired_on " +
        "FROM employees WHERE id >= ? ORDER BY id",
        EMPLOYEE_MAPPER,
        2L);
```

Đây là **đoạn trích**, cần các khai báo trong ví dụ chính. `query` thực hiện SQL, bind tham số và gọi mapper cho từng hàng. Nó trả một danh sách; không có hàng thì thường trả danh sách rỗng, **không ném lỗi “expected one result”**. Nếu SQL cho 100 hàng và không có limit, mapper chạy cho 100 hàng; danh sách có thể tiêu tốn bộ nhớ tương ứng.

### 5.2. `queryForObject`: chính xác một hàng

```java
Employee employee = jdbc.queryForObject(
        "SELECT id, full_name AS display_name, salary, manager_id, hired_on " +
        "FROM employees WHERE id = ?",
        EMPLOYEE_MAPPER,
        2L);
```

`queryForObject` kỳ vọng **chính xác một hàng**. Nếu không có hàng, Spring thường ném `EmptyResultDataAccessException`. Nếu có hơn một hàng, ném `IncorrectResultSizeDataAccessException` (hoặc subclass phù hợp). Những điều này là **hợp đồng cardinality của phương thức `queryForObject`**, không phải chức năng “lỗi” của `RowMapper`.

Ngay cả khi mapper có thể trả `null` cho một hàng, việc có một hàng vẫn khác với việc SQL trả **0 hàng**. Tránh dùng `queryForObject` cho tình huống “có thể thiếu” rồi bỏ qua ngoại lệ trong mọi đường đi; khi bài toán tự nhiên cho phép không có kết quả, dùng `query` rồi chuyển sang `Optional` hoặc một abstraction phù hợp.

### 5.3. `queryForList` không tự sinh DTO tùy ý

`JdbcTemplate.queryForList(sql)` thường trả `List<Map<String, Object>>` với mỗi hàng là map cột → giá trị, còn `queryForList(sql, SomeClass.class)` phục vụ kết quả một cột có thể chuyển sang kiểu đích. Nó không đồng nghĩa tự map mọi hàng nhiều cột thành `Employee`.

Để có kiểu miền, sử dụng `RowMapper<Employee>` qua `query`/`queryForObject` hoặc một mapper/converter phù hợp. Tách rõ “đọc dữ liệu” và “ánh xạ dữ liệu” giúp tránh cast map thủ công ở service.

### 5.4. Mapper có thể dùng cho `NamedParameterJdbcTemplate`

`NamedParameterJdbcTemplate` chỉ thay cách viết và bind tham số SQL, không thay bản chất ánh xạ hàng:

```java
NamedParameterJdbcTemplate named =
        new NamedParameterJdbcTemplate(jdbc.getDataSource());

List<Employee> employees = named.query(
        "SELECT id, full_name AS display_name, salary, manager_id, hired_on " +
        "FROM employees WHERE id >= :minId ORDER BY id",
        Map.of("minId", 2L),
        EMPLOYEE_MAPPER);
```

Đây là đoạn trích minh họa, cần `Map`, `NamedParameterJdbcTemplate` và `jdbc` đã cấu hình có `DataSource`. Tham số `:minId` được đưa về prepared statement JDBC; mapper vẫn đọc những cột như cũ. Đừng ghép dữ liệu người dùng vào SQL. Giá trị của `RowMapper` nằm ở hợp đồng cột → đối tượng, nên có thể dùng lại khi query style khác nhau.

## 6. RowMapper so với RowCallbackHandler và ResultSetExtractor

Ba API thường bị nhầm vì đều liên quan `ResultSet`.

| Interface | Mức xử lý | Ai gọi `rs.next()`? | Đầu ra mong đợi |
| --- | --- | --- | --- |
| `RowMapper<T>` | Một hàng → một giá trị `T` | `JdbcTemplate` | Một `T` cho mỗi hàng; template thường tập hợp thành `List<T>` |
| `RowCallbackHandler` | Thao tác trên từng hàng hiện tại, không bắt buộc trả `T` | `JdbcTemplate` | Có thể cập nhật bộ tích lũy/sink riêng |
| `ResultSetExtractor<T>` | Toàn bộ `ResultSet` → một giá trị `T` | **Bạn tự duyệt trong extractor** | Tổng hợp, nhóm nhiều hàng, dựng aggregate phức tạp |

### 6.1. Khi nào RowMapper là lựa chọn tự nhiên?

Dùng `RowMapper` khi quan hệ đúng là **mỗi hàng có thể tạo một đối tượng độc lập**, chẳng hạn:

- Hàng `employees` → `Employee`.
- Hàng `products` → `ProductSummary`.
- Hàng `orders` → `OrderRow` hoặc DTO hiển thị.
- Một dòng aggregate SQL như `COUNT(*)` → một số (nhiều trường hợp dùng `queryForObject(sql, Long.class)` còn đơn giản hơn).

Nếu SQL trả nhiều hàng JOIN cho cùng một đơn hàng với nhiều dòng sản phẩm, tạo một `Order` đầy đủ bằng **một row mapper cho từng hàng** có thể sinh nhiều bản sao đơn hàng. Khi cần **gom nhiều hàng thành một aggregate**, cân nhắc `ResultSetExtractor` hoặc map thành DTO hàng phẳng rồi nhóm ở service/DAO.

### 6.2. RowCallbackHandler khác RowMapper ở chỗ nào?

```java
List<Long> ids = new ArrayList<>();

jdbc.query(
        "SELECT id FROM employees ORDER BY id",
        (RowCallbackHandler) rs -> ids.add(rs.getLong("id")));
```

Đoạn này là minh họa, cần `ArrayList`, `RowCallbackHandler` và bean `jdbc`. `RowCallbackHandler` xử lý từng hàng, không trả về một đối tượng qua `mapRow`. `ids` phải được tạo mới mỗi lần gọi nếu có concurrency; không lưu list kết quả thành field shared trong singleton DAO. Nếu mục đích đơn thuần là lấy list ID, dùng `RowMapper<Long>` vẫn rõ ràng:

```java
List<Long> ids = jdbc.query(
        "SELECT id FROM employees ORDER BY id",
        (rs, rowNum) -> rs.getLong("id"));
```

### 6.3. ResultSetExtractor tự duyệt mọi hàng

```java
ResultSetExtractor<BigDecimal> sumExtractor = rs -> {
    BigDecimal sum = BigDecimal.ZERO;
    while (rs.next()) {
        sum = sum.add(rs.getBigDecimal("salary"));
    }
    return sum;
};
BigDecimal total = jdbc.query(
        "SELECT salary FROM employees",
        sumExtractor);
```

Đây cũng là đoạn minh họa, cần các import và bean liên quan. `ResultSetExtractor` có quyền gọi `rs.next()` vì hợp đồng yêu cầu xử lý toàn bộ tập kết quả. Nhưng với nhu cầu tính tổng, SQL `SELECT SUM(salary)` sẽ hiệu quả và ngắn hơn trong nhiều trường hợp; ví dụ chỉ để phân biệt vòng lặp của callback.

## 7. Các kiểu mapper có sẵn: viết tay hay ánh xạ tự động?

### 7.1. RowMapper tự viết

```java
RowMapper<Employee> explicit =
        (rs, rowNum) -> new Employee(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getBigDecimal("salary"),
                rs.getObject("manager_id", Long.class),
                rs.getObject("hired_on", LocalDate.class));
```

Ưu điểm: minh bạch alias, kiểu và quy tắc null; phù hợp DTO/record, kiểu miền riêng, chuyển đổi phức tạp, tối ưu hiệu năng khi profiling cho thấy cần thiết.

Nhược điểm: cập nhật mapper khi contract DTO/schema thay đổi; có thể lặp code nếu nhiều DAO viết cùng ánh xạ mà không trích ra một nơi chung.

### 7.2. BeanPropertyRowMapper

`BeanPropertyRowMapper<T>` tiện khi target là JavaBean với constructor không tham số và setter phù hợp, ví dụ:

```java
public class EmployeeBean {
    private long id;
    private String fullName;

    public EmployeeBean() {}

    public void setId(long id) { this.id = id; }
    public void setFullName(String fullName) { this.fullName = fullName; }
    // Getter có thể thêm theo nhu cầu sử dụng.
}
```

Đây là đoạn minh họa kiểu bean, không phải ứng dụng riêng. Với câu query chọn `id` và `full_name`, mapper có thể ghép tên cột dạng underscore với property camelCase tương ứng:

```java
RowMapper<EmployeeBean> mapper =
        BeanPropertyRowMapper.newInstance(EmployeeBean.class);
```

Import `org.springframework.jdbc.core.BeanPropertyRowMapper`. Cần cột phù hợp, setter public và kiểu chuyển đổi tương thích. Không mặc nhiên nhận mọi DB-specific type, constructor bất kỳ hoặc logic nghiệp vụ tùy ý.

### 7.3. DataClassRowMapper cho record và constructor

`DataClassRowMapper<T>` hỗ trợ Java records, Kotlin data classes và class có constructor mang tên tham số phù hợp tên cột. Ví dụ:

```java
record ProductView(long id, String productName) {}

RowMapper<ProductView> mapper =
        DataClassRowMapper.newInstance(ProductView.class);

// SELECT id, product_name FROM products ...
```

Đây là đoạn minh họa; cần import `DataClassRowMapper` và có bảng/SQL tương ứng. Mapper chọn constructor phù hợp; alias/tên cột phải khớp parameter/property theo quy tắc naming của mapper. Với mapping có logic đặc biệt hoặc hiệu năng nhạy cảm, Spring khuyến nghị cân nhắc `RowMapper` tùy chỉnh.

### 7.4. Chọn giải pháp theo độ phức tạp

| Tiêu chí | Custom RowMapper | BeanPropertyRowMapper | DataClassRowMapper |
| --- | --- | --- | --- |
| Dựng record immutable | Rõ ràng | Không phải lựa chọn ưu tiên cho constructor record | Phù hợp khi tên cột/constructor tương thích |
| JavaBean setter | Hoàn toàn làm được | Tiện, ít code | Cũng có thể dùng |
| Logic đổi kiểu phức tạp | Kiểm soát tốt | Phụ thuộc conversion mặc định/cấu hình | Phụ thuộc conversion và constructor |
| Cột nullable/alias tinh vi | Kiểm soát trực tiếp | Cần xem mapper tự động có xử lý như mong muốn | Cần kiểm tra constructor/nullability |
| Performance rất nhạy | Dễ tối ưu có chủ đích | Ưu tiên tiện dụng, cần đo thực tế | Ưu tiên tiện dụng, cần đo thực tế |

Đừng biến mapping tự động thành giả định “không cần test”. Thay tên cột, thiếu setter, cột SQL `NULL` vào primitive, sai scale hoặc thứ tự constructor có thể dẫn tới lỗi hoặc dữ liệu không đúng kỳ vọng. Trong các lớp DTO quan trọng, mapping minh bạch thường dễ review và debug.

## 8. Lỗi phổ biến khi xây dựng RowMapper

### 8.1. Gọi `rs.next()` trong `mapRow`

Lỗi: mất hàng, bỏ hàng đầu hoặc truy cập con trỏ ngoài phạm vi. Cách sửa: để `JdbcTemplate` duyệt; mapper chỉ đọc hàng đang có.

### 8.2. Đọc sai alias hoặc cột không được SELECT

SQL:

```sql
SELECT id, full_name AS employee_name FROM employees
```

Nhưng mapper:

```java
rs.getString("display_name"); // Không có alias này trong SELECT trên.
```

Kết quả thường là `SQLException` từ driver rồi được Spring chuyển thành lỗi data access. Sửa một cách nhất quán: query phải cung cấp alias mà mapper đọc, hoặc mapper phải đọc đúng column label.

### 8.3. Nhầm SQL NULL với 0/false

`rs.getLong("manager_id")` trả 0 khi SQL NULL. Sửa bằng `wasNull()` sau getter hoặc `getObject("manager_id", Long.class)` phù hợp driver; tránh đưa dữ liệu 0 giả vào mô hình miền.

### 8.4. Dùng `rowNum` làm khóa dữ liệu

`rowNum = 0` không mang nghĩa id 0. Khi SQL đổi sort/page/filter, thứ tự ánh xạ thay đổi. Luôn lấy khóa thật từ cột ID.

### 8.5. Mapper giữ mutable state dùng chung

```java
// Ví dụ phản diện: mapper được dùng lại giữa nhiều query/threads.
class UnsafeMapper implements RowMapper<Employee> {
    private final List<String> seen = new ArrayList<>();

    @Override
    public Employee mapRow(ResultSet rs, int rowNum) throws SQLException {
        seen.add(rs.getString("display_name"));
        return new Employee(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getBigDecimal("salary"),
                rs.getObject("manager_id", Long.class),
                rs.getObject("hired_on", LocalDate.class));
    }
}
```

Đây là đoạn minh họa sai, cần import các kiểu tương ứng. `ArrayList` được chia sẻ có thể bị ghi đồng thời; dù đồng bộ hóa, còn nguy cơ trộn dữ liệu giữa các request. Giữ mapper stateless hoặc tạo accumulator local cho từng query. Template thread-safe **không làm mọi callback mặc nhiên thread-safe**.

### 8.6. Thực hiện network call hoặc SQL N+1 trong mapper

Một mapper gọi HTTP API hoặc query thứ hai cho từng hàng làm kéo dài thời gian connection/statement còn mở và có thể tạo N+1 round trips. Ví dụ truy vấn 100 nhân viên rồi với mỗi nhân viên lại lấy phòng ban bằng một SQL mới thường tốn kém. Cân nhắc JOIN, fetch riêng theo batch, hoặc xử lý sau khi map; đo latency và lựa chọn hợp lý thay vì đặt I/O nặng bên trong `mapRow`.

### 8.7. Lưu ResultSet để đọc sau query

```java
ResultSet leaked = jdbc.query(
        "SELECT id FROM employees",
        (ResultSetExtractor<ResultSet>) rs -> rs);
```

Đây là **đoạn phản diện**: sau khi `JdbcTemplate.query(...)` kết thúc, `ResultSet` có thể đã bị đóng và tài nguyên không còn hợp lệ. `RowMapper` cũng không nên giữ `rs` trong DTO. Tạo đối tượng Java hoàn chỉnh bên trong callback.

### 8.8. Bỏ qua hợp đồng số lượng kết quả

Khi SQL không tìm thấy nhân viên, `query(...)` trả danh sách rỗng; `queryForObject(...)` báo lỗi thiếu hàng. Khi SQL có nhiều hàng nhưng gọi `queryForObject`, đó là lỗi cardinality. Đừng chữa bằng cách cho mapper bỏ qua hàng ngoài ý muốn: hợp đồng của API query và điều kiện SQL mới cần sửa.

### 8.9. Dựa vào SELECT * và thứ tự cột

`SELECT *` làm mapper phụ thuộc schema chưa được thể hiện rõ. Đọc `rs.getString(2)` dễ vỡ khi thay thứ tự cột. Dùng danh sách cột rõ ràng với alias ổn định, đặc biệt khi tái sử dụng mapper qua nhiều query.

### 8.10. Bắt SQLException rồi trả giá trị giả

Nếu không có cột hoặc conversion thất bại, việc trả `new Employee(0, "", BigDecimal.ZERO, null, ...)` che lỗi hạ tầng thành dữ liệu hợp lệ. Nên để lỗi JDBC đi lên và xử lý ở tầng có thể quyết định log/retry/trả mã lỗi phù hợp.

## 9. Thiết kế ánh xạ trong repository/DAO

Một repository điển hình có thể giữ mapper dưới dạng field dùng lại:

```java
@Repository
public class EmployeeRepository {
    private static final RowMapper<Employee> EMPLOYEE_MAPPER =
            (rs, rowNum) -> new Employee(
                    rs.getLong("id"),
                    rs.getString("display_name"),
                    rs.getBigDecimal("salary"),
                    rs.getObject("manager_id", Long.class),
                    rs.getObject("hired_on", LocalDate.class));

    private final JdbcTemplate jdbc;

    public EmployeeRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Employee> findAll() {
        return jdbc.query(
                "SELECT id, full_name AS display_name, salary, manager_id, " +
                "hired_on FROM employees ORDER BY id",
                EMPLOYEE_MAPPER);
    }
}
```

Đây là **đoạn minh họa trong một ứng dụng Spring**, cần các import `@Repository`, `RowMapper`, `JdbcTemplate`, `List` và kiểu `Employee`; không phải file có thể chạy riêng. `RowMapper` nhận trách nhiệm mapping; repository chọn SQL và hợp đồng trả về; service dùng `List<Employee>` mà không cần thấy `ResultSet`. Cần thay mapper khi schema/DTO đổi, nhưng service không phải lặp code JDBC.

Nếu nhiều câu query trả về những tập cột khác nhau, đừng ép tất cả dùng một mapper có getter cho cột không tồn tại. Có thể tạo DTO/mapper nhỏ hơn cho projection chỉ cần id/name:

```java
record EmployeeSummary(long id, String name) {}
RowMapper<EmployeeSummary> summaryMapper =
        (rs, rowNum) -> new EmployeeSummary(
                rs.getLong("id"),
                rs.getString("display_name"));
```

Việc tạo projection ít cột giảm dữ liệu truyền từ DB và phản ánh đúng nhu cầu use case. Tránh lấy mọi cột lớn rồi bỏ qua trong mapper.

## 10. Kiểm thử RowMapper đúng ngữ nghĩa

### 10.1. Những tình huống cần test

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Một hàng bình thường | Mọi field có đúng giá trị và kiểu |
| Không có hàng | `query` trả empty list, `queryForObject` ném lỗi thiếu kết quả |
| Nhiều hàng | Mapper chạy đúng mỗi hàng, thứ tự tương ứng `ORDER BY` |
| SQL `NULL` ở cột optional | Java wrapper/nullable field nhận `null`, không bị biến thành 0 |
| DECIMAL và DATE | Giữ ý nghĩa tiền/ngày, tránh mất precision hoặc timezone |
| Alias thay đổi | Query và mapper khớp tên cột; mismatch được phát hiện |
| JOIN và cột trùng tên | Alias riêng và DTO nhận đúng dữ liệu |
| Cột mới/cột bị loại | Mapper chỉ đòi các cột contract cần; sửa khi projection đổi |
| Mapper dùng chung đồng thời | Không giữ state mutable từ request khác |
| Nhiều bản ghi với khóa bất thường | Dùng `id` thực, không lấy `rowNum` làm khóa |
| Query dùng tham số người dùng | Bind vào prepared statement, không ghép SQL không kiểm soát |
| Kết quả lớn | Xem khả năng paging/streaming, đo memory và pool usage |

### 10.2. Ví dụ test JUnit 5 minh họa

Giả sử `EmployeeDao` và schema/dữ liệu trong ví dụ `RowMapperDemo` đã được khởi tạo ở fixture test:

```java
// Đoạn trích JUnit 5, không phải file test độc lập.
@Test
void mapsSqlNullAndDate() {
    Employee lan = dao.requireOne(1L);
    assertEquals("Lan", lan.name());
    assertNull(lan.managerId());
    assertEquals(new BigDecimal("1000.50"), lan.salary());
    assertEquals(LocalDate.of(2024, 1, 15), lan.hiredOn());
}

@Test
void optionalAndRequiredHaveDifferentCardinalityContracts() {
    assertTrue(dao.findOptional(999L).isEmpty());
    assertThrows(EmptyResultDataAccessException.class,
            () -> dao.requireOne(999L));
}
```

Đoạn này cần dependency JUnit Jupiter, các static import từ `org.junit.jupiter.api.Assertions`, `@Test`, `dao` fixture, và các kiểu record/DAO từ demo. Nó không phải một phần của main program Maven ở mục 4. Integration test với DB thật hoặc Testcontainers phù hợp khi SQL phụ thuộc PostgreSQL/MySQL/Oracle, đặc biệt với conversion, timezone hoặc alias behavior của driver.

### 10.3. Khi nào cần test riêng mapper?

Nếu ánh xạ có logic bất thường (giải mã JSON/enum, nullable relationship, fallback dựa trên nhiều cột, dùng constructor domain có validation), có thể test mapper bằng `ResultSet` mock hoặc integration query với DB. Với mapper đơn giản, một integration test DAO xác minh SQL + mapping thường có giá trị hơn test mock chỉ lặp lại `rs.getString(...)` mà không kiểm tra cột thật.

## 11. Checklist khi viết RowMapper mới

1. **Xác định một hàng đại diện điều gì?** Một DTO, entity summary, aggregate row hay scalar?
2. **Liệt kê cột/alias chính xác** trong SQL và map vào field nào; tránh giả định `SELECT *`.
3. **Chọn kiểu Java đúng** cho BIGINT, DECIMAL, DATE, TIMESTAMP; xác định quy tắc chuyển đổi.
4. **Xử lý SQL NULL rõ ràng**, nhất là primitive getter, `LEFT JOIN` và nullable value.
5. **Giữ một-hàng-một-đối-tượng**; không gọi `rs.next()`, không để `ResultSet` thoát callback.
6. **Tách mapper khỏi query logic** và dùng lại chỉ khi các truy vấn cùng trả đủ projection.
7. **Giữ mapper stateless**, đặc biệt nếu bean/template được dùng qua nhiều request.
8. **Chọn API query đúng cardinality:** `query` cho danh sách/có thể rỗng, `queryForObject` cho đúng một hàng.
9. **Đặt điều kiện lọc/sort và tham số ở SQL**, không để mapper phải lọc hoặc thay thế logic query.
10. **Kiểm thử với 0/1/nhiều hàng, null, alias và concurrency** theo dữ liệu thật của hệ quản trị.

### Câu hỏi tự kiểm tra

1. Vì sao `RowMapper.mapRow` không được gọi `rs.next()`?
2. `rowNum` bắt đầu từ bao nhiêu, và khác khóa `id` trong bảng thế nào?
3. Khi `manager_id` là SQL `NULL`, `rs.getLong("manager_id")` trả gì? Làm thế nào để phân biệt với 0?
4. `query` và `queryForObject` khác nhau ở trường hợp không tìm thấy hàng như thế nào?
5. Vì sao một mapper chỉ đọc `display_name` không thể tái dùng nguyên xi cho query không SELECT alias đó?
6. Khi nào nên dùng `DataClassRowMapper` thay vì mapper tự viết, và khi nào tự viết vẫn tốt hơn?
7. Nếu một JOIN trả nhiều hàng con cho một cha, vì sao `RowMapper<Order>` một hàng một object có thể không đủ để dựng aggregate?
8. Vì sao `JdbcTemplate` thread-safe không bảo đảm một `RowMapper` có field `ArrayList` dùng chung là an toàn?

**Điểm cần nhớ:** `RowMapper<T>` ánh xạ **đúng một hàng hiện tại** của `ResultSet` thành **một đối tượng `T`**. `JdbcTemplate` nắm vòng đời và duyệt kết quả; mapper tập trung vào alias, loại dữ liệu, `NULL` và constructor. Khi dùng đúng abstraction này, DAO rõ hơn, service nhận DTO/record thay vì JDBC API, và cùng một phép ánh xạ có thể được tái sử dụng có kiểm soát giữa nhiều truy vấn.

### Tài liệu tham khảo chính thức

- Spring Framework — JDBC Core (query với RowMapper): https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — RowMapper JavaDoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- Spring Framework — JdbcTemplate JavaDoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework — BeanPropertyRowMapper JavaDoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html
- Spring Framework — DataClassRowMapper JavaDoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html

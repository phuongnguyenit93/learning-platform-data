# queryForList(), queryForMap() và ánh xạ không định kiểu miền trong Spring JDBC

> **Nhóm kiến thức:** Truy vấn JDBC  
> **Bối cảnh:** Spring Framework – data-access

## 1. Mục tiêu và tư duy sử dụng

Khi sử dụng `JdbcTemplate` trong Spring Framework, đôi lúc chương trình chỉ cần lấy một bảng dữ liệu nhỏ, vài cột phục vụ báo cáo hoặc một giá trị cấu hình. Không phải truy vấn nào cũng cần tạo một class Java riêng và viết `RowMapper`. Spring JDBC cung cấp những lựa chọn dựa trên `Map<String, Object>`:

- `queryForList(sql, args...)` trả về **nhiều hàng**, mỗi hàng là một `Map<String, Object>`: tổng thể `List<Map<String, Object>>`.
- `queryForMap(sql, args...)` trả về **đúng một hàng** dưới dạng `Map<String, Object>`. Không có hàng hoặc có hơn một hàng đều là lỗi về số lượng kết quả.
- `queryForList(sql, elementType, args...)` trả về nhiều giá trị của **một cột**, với `elementType` chỉ kiểu của mỗi phần tử, chẳng hạn `List<String>` hoặc `List<Long>`. Nó không biến các cột thành domain object.

Ví dụ bảng `employee`:

~~~text
id | name | salary
---+------+-------
1  | An   | 120.50
2  | Binh | NULL
3  | Chi  | 200.00
~~~

Ba lời gọi dưới đây có **kiểu trả về khác nhau**:

~~~java
List<Map<String, Object>> rows = jdbcTemplate.queryForList(
    "SELECT id, name, salary FROM employee ORDER BY id");

Map<String, Object> one = jdbcTemplate.queryForMap(
    "SELECT id, name, salary FROM employee WHERE id = ?", 1L);

List<String> names = jdbcTemplate.queryForList(
    "SELECT name FROM employee ORDER BY id", String.class);
~~~

*Đây là đoạn minh họa bên trong phương thức có sẵn `jdbcTemplate` và bảng dữ liệu; dự án Java 17+ đầy đủ ở mục 9.*

Cụm **ánh xạ không định kiểu miền** ở đây có nghĩa không chuyển trực tiếp mỗi dòng thành `Employee`, `EmployeeSummary` hay một DTO domain cụ thể. Java vẫn có kiểu: khóa map là `String`, giá trị được khai báo `Object` và đối tượng thực tế có kiểu Java tùy SQL type, JDBC driver và mapper. Điểm đánh đổi chính là **ít code ánh xạ ban đầu** nhưng **giảm an toàn kiểu và khả năng kiểm soát hợp đồng dữ liệu**.

## 2. Chọn đúng API theo số hàng và số cột

| Nhu cầu | API thường dùng | Kiểu Java | Điều kiện số hàng/cột |
| --- | --- | --- | --- |
| Danh sách nhiều cột dùng linh hoạt | `queryForList(sql, args...)` | `List<Map<String, Object>>` | 0..n hàng, nhiều cột |
| Một bản ghi nhiều cột | `queryForMap(sql, args...)` | `Map<String, Object>` | **Đúng 1 hàng** |
| Danh sách một cột scalar | `queryForList(sql, String.class, args...)` hoặc kiểu thích hợp | `List<T>` | 0..n hàng, **đúng 1 cột** |
| Một giá trị scalar, ví dụ `COUNT(*)` | `queryForObject(sql, Integer.class, args...)` | `T` | Đúng 1 hàng, đúng 1 cột |
| Domain object nhiều trường | `query(sql, rowMapper, args...)` | `List<T>` | 0..n hàng; mỗi hàng do mapper tự tạo |
| Một domain object | `queryForObject(sql, rowMapper, args...)` | `T` | Đúng 1 hàng; mapper tự tạo đối tượng |

Từ `queryForList` **không** có nghĩa luôn trả list map: overload có `Class<T> elementType` trả list của một cột. Trong ví dụ Spring Framework 6.x, dấu `?` là placeholder cho **giá trị tham số**, được bind qua `JdbcTemplate`.

Đừng suy diễn cách xử lý 0 hàng theo cùng một quy tắc:

- `queryForList`: 0 hàng → **list rỗng**.
- `queryForMap`: 0 hàng → **`EmptyResultDataAccessException`**.
- `queryForMap`: nhiều hàng → **`IncorrectResultSizeDataAccessException`**.
- `queryForObject`: cũng yêu cầu số hàng phù hợp hợp đồng; một ô SQL NULL là tình huống khác với việc không có hàng.

## 3. `queryForList()` trả danh sách các map

### 3.1. Hình dạng dữ liệu

Giả sử:

~~~java
List<Map<String, Object>> employees = jdbcTemplate.queryForList(
    "SELECT id AS employee_id, name AS employee_name, salary " +
    "FROM employee WHERE id >= ? ORDER BY id",
    2L
);
~~~

Về mặt khái niệm, dòng đầu là:

~~~text
employee_id   -> 2
employee_name -> "Binh"
salary        -> null
~~~

Dòng thứ hai có ID 3, tên `"Chi"` và salary bằng 200.00. `JdbcTemplate` dùng `ColumnMapRowMapper` mặc định để tạo một map cho mỗi hàng, rồi tạo danh sách chứa các map đó.

Vòng lặp đọc dữ liệu:

~~~java
for (Map<String, Object> row : employees) {
    long id = ((Number) row.get("employee_id")).longValue();
    String name = (String) row.get("employee_name");
    Object salary = row.get("salary");
    System.out.println(id + ": " + name + ", salary=" + salary);
}
~~~

*Đây là đoạn minh họa trong method có biến `employees`.* Đọc ID qua `Number` giảm phụ thuộc vào việc SQL numeric được driver diễn giải thành `Integer`, `Long` hoặc một kiểu số tương thích; tuy nhiên conversion sang `long` vẫn phải phù hợp miền giá trị.

### 3.2. Khi kết quả không có hàng

~~~java
List<Map<String, Object>> rows = jdbcTemplate.queryForList(
    "SELECT id, name FROM employee WHERE id < ?", 0L);

System.out.println(rows.isEmpty()); // true
~~~

Danh sách rỗng là kết quả hợp lệ của truy vấn danh sách. Đối với màn hình tìm kiếm, 0 hàng có thể chỉ là “không có dữ liệu”. Không cần bắt `EmptyResultDataAccessException` khi dùng `queryForList` theo cách này.

### 3.3. Map không phải đối tượng miền

`Map<String, Object>` không đảm bảo `id` luôn tồn tại, `name` luôn không null hay `salary` luôn là `BigDecimal`. Nó không thực thi validation, không tự biểu diễn quan hệ của entity và không đưa invariant của nghiệp vụ vào constructor.

Nếu service ở nhiều chỗ đều phải viết `(String) row.get("employee_name")`, hoặc một đổi tên alias dễ làm hỏng nhiều phần, nên cân nhắc ánh xạ sang record/DTO có kiểu rõ ràng.

## 4. `queryForMap()`: một hàng có nhiều cột

~~~java
Map<String, Object> employee = jdbcTemplate.queryForMap(
    "SELECT id AS employee_id, name AS employee_name, salary " +
    "FROM employee WHERE id = ?",
    1L
);
~~~

Kết quả vẫn là map cột → giá trị, nhưng **chỉ có đúng một hàng** được chấp nhận.

### 4.1. Khi không có hàng

~~~java
try {
    Map<String, Object> missing = jdbcTemplate.queryForMap(
        "SELECT id, name FROM employee WHERE id = ?", 999L);
} catch (EmptyResultDataAccessException ex) {
    // Không có hàng tương ứng.
}
~~~

Không có hàng sẽ phát sinh `EmptyResultDataAccessException`, **không** trả map rỗng hoặc null. Đây là một subclass của `IncorrectResultSizeDataAccessException`.

### 4.2. Khi có nhiều hàng

~~~java
try {
    Map<String, Object> ambiguous = jdbcTemplate.queryForMap(
        "SELECT id, name FROM employee");
} catch (IncorrectResultSizeDataAccessException ex) {
    // Có nhiều hơn một hàng.
}
~~~

Phương thức không tự chọn dòng đầu. Nếu muốn nhiều dòng, dùng `queryForList`. Nếu kỳ vọng đúng một dòng, điều kiện WHERE nên dựa trên khóa chính hoặc ràng buộc uniqueness có thực ở database.

Dùng `LIMIT 1` chỉ khi nghiệp vụ **thực sự chấp nhận lấy một hàng bất kỳ/theo thứ tự xác định**; đừng dùng nó để che lỗi dữ liệu trùng bất hợp pháp. Nếu cần hàng mới nhất, quy tắc chọn phải có `ORDER BY` rõ ràng và xử lý trường hợp không tìm thấy.

### 4.3. “Không tìm thấy” có thể là trường hợp bình thường

Nếu tìm ID không tồn tại là tình huống hợp lệ, có thể dùng `queryForList` và kiểm tra size:

~~~java
List<Map<String, Object>> candidates = jdbcTemplate.queryForList(
    "SELECT id, name FROM employee WHERE id = ?", requestedId);

if (candidates.isEmpty()) {
    // Trả về Optional.empty() hoặc phản hồi phù hợp.
} else if (candidates.size() == 1) {
    Map<String, Object> value = candidates.get(0);
    // Xử lý một bản ghi.
} else {
    throw new IllegalStateException("ID không duy nhất");
}
~~~

*Đây là đoạn minh họa có biến `requestedId`; không phải chương trình độc lập.* Truy vấn theo khóa chính tốt sẽ không trả nhiều dòng. Đối với domain object có kiểu, dùng `query(..., RowMapper)` rồi `findFirst` sau khi đã kiểm chứng uniqueness thường diễn đạt nghiệp vụ rõ hơn.

### 4.4. Một giá trị nên dùng API scalar

Nếu chỉ cần một `String`, việc tạo map không tăng tính rõ ràng:

~~~java
String name = jdbcTemplate.queryForObject(
    "SELECT name FROM employee WHERE id = ?",
    String.class,
    1L
);
~~~

`queryForObject` yêu cầu một hàng và một cột trong overload scalar. Lúc này giá trị được trả về có kiểu mong đợi thay vì phải gọi `row.get("name")` và ép kiểu thủ công. Nó vẫn cần xử lý trường hợp không có hàng.

## 5. `queryForList(sql, Class<T>)` khác `queryForList(sql)` thế nào?

Dạng có `elementType` sử dụng `SingleColumnRowMapper`, lấy **một cột** ở mỗi hàng:

~~~java
List<String> names = jdbcTemplate.queryForList(
    "SELECT name FROM employee ORDER BY id",
    String.class
);

List<Long> ids = jdbcTemplate.queryForList(
    "SELECT id FROM employee ORDER BY id",
    Long.class
);
~~~

Dữ liệu ý niệm:

~~~text
names = [An, Binh, Chi]
ids   = [1, 2, 3]
~~~

Không nên nhầm `elementType` với class domain nhiều thuộc tính. Ví dụ:

~~~java
// SAI: SQL có hai cột; overload elementType chỉ nhận một cột.
List<Employee> employees = jdbcTemplate.queryForList(
    "SELECT id, name FROM employee", Employee.class);
~~~

`SingleColumnRowMapper` mong đúng **một cột**, do đó truy vấn nhiều cột thường dẫn đến `IncorrectResultSetColumnCountException`. Nó không biết tự gọi constructor `Employee(long, String)`.

**Ánh xạ domain đúng cách:**

~~~java
record Employee(long id, String name) {}

List<Employee> employees = jdbcTemplate.query(
    "SELECT id, name FROM employee ORDER BY id",
    (rs, rowNum) -> new Employee(
        rs.getLong("id"),
        rs.getString("name"))
);
~~~

*Đây là Java 17+ minh họa trong method có `jdbcTemplate`.* Lambda chính là `RowMapper<Employee>`: biết thứ tự và cách chuyển các cột thành record. Compiler có thể kiểm tra những nơi dùng `Employee`; map không cung cấp mức kiểm tra tĩnh tương đương.

**Chú ý:** SQL `DECIMAL` thường thích hợp với `BigDecimal` hơn `Double` cho dữ liệu cần chính xác; một cột có `NULL` có thể tạo phần tử null. Việc truyền `SomeClass.class` không đảm bảo driver/Spring có thể chuyển mọi kiểu vendor thành kiểu đó. Hãy chọn type phù hợp và kiểm tra dữ liệu.

## 6. Cách `ColumnMapRowMapper` tạo key

### 6.1. Tên cột khác nhãn cột

`ColumnMapRowMapper` dựa trên metadata JDBC của `ResultSet`, ưu tiên **column label** khi có alias `AS`. Ví dụ:

~~~sql
SELECT
    e.id AS employee_id,
    e.name AS employee_name,
    d.name AS department_name
FROM employee e
JOIN department d ON d.id = e.department_id
~~~

Truy cập theo key:

~~~java
Object id = row.get("employee_id");
Object employeeName = row.get("employee_name");
Object departmentName = row.get("department_name");
~~~

Đây là lý do nên khai báo alias rõ ràng khi map đóng vai trò hợp đồng cho báo cáo hoặc API. Nếu dùng `SELECT *`, thay đổi schema có thể vô tình thêm/đổi các key trong kết quả.

### 6.2. Chữ hoa/chữ thường

Mapper mặc định của Spring thường sử dụng `LinkedCaseInsensitiveMap` cho key, nên tra cứu có thể không phân biệt hoa/thường. Tuy vậy chữ hoa/thường *gốc được giữ khi duyệt key* và cách driver báo metadata có thể khác nhau.

Đừng phụ thuộc vào việc `map.toString()` có chính xác key `ID` hay `id` trong mọi database. Nếu cần một schema JSON/CSV ổn định, dùng alias rõ ràng, xác nhận key và chuẩn hóa tại nơi xuất dữ liệu.

Trong ví dụ H2 chạy được, SQL dùng alias có dấu ngoặc kép như `AS "employee_id"` để nhãn cột có chữ thường nhất quán. Một số cơ sở dữ liệu có quy tắc quoting identifier khác, cần điều chỉnh SQL theo dialect.

### 6.3. Trùng column label khi JOIN

Ví dụ dễ gây lỗi:

~~~sql
SELECT e.id, d.id
FROM employee e
JOIN department d ON d.id = e.department_id
~~~

Hai cột có thể cùng nhãn `id`. Map chỉ có một entry cho mỗi key; không thể diễn đạt hai cột khác nhau với cùng tên một cách rõ ràng. Hãy dùng:

~~~sql
SELECT e.id AS employee_id, d.id AS department_id
FROM employee e
JOIN department d ON d.id = e.department_id
~~~

Không sử dụng `map.values().toArray()[0]` làm hợp đồng thứ tự trường. Dù các map mặc định của Spring thường giữ thứ tự chèn, mã ứng dụng nên phụ thuộc vào **tên key** và projection tường minh.

## 7. `Object` trong Map chứa dữ liệu kiểu gì?

### 7.1. Các kiểu thường gặp

| SQL type | Java type thường thấy từ JDBC | Lưu ý |
| --- | --- | --- |
| `CHAR` / `VARCHAR` | `String` | Giá trị có thể null |
| `INTEGER` | `Integer` hoặc kiểu `Number` tương thích | Không ép thẳng `Long` trong mọi môi trường |
| `BIGINT` | `Long` hoặc kiểu số tương thích | Xem phạm vi và quy tắc conversion |
| `DECIMAL` / `NUMERIC` | `BigDecimal` | Tránh mất chính xác khi đổi sang double |
| `BOOLEAN` | `Boolean` hoặc biểu diễn khác tùy DB | Không giả định mọi database giống nhau |
| `DATE` / `TIMESTAMP` | Kiểu JDBC/date-time khác nhau tùy driver | Chú ý timezone và ánh xạ |
| `BLOB`, `ARRAY`, JSON hoặc loại vendor | `Blob`, `byte[]`, `Array`, `String`, kiểu vendor... | Không tự suy đoán type ở mọi driver |

Bảng này cho biết *thường gặp*, không phải cam kết cho mọi driver hay loại cột. Kiểu thực tế phụ thuộc JDBC type, driver và cách Spring đọc dữ liệu.

### 7.2. Đọc số an toàn hơn

~~~java
Object idValue = row.get("employee_id");
if (!(idValue instanceof Number number)) {
    throw new IllegalStateException("employee_id không phải số");
}
long id = number.longValue();
~~~

Cách này tránh cast cứng một kiểu số duy nhất nhưng vẫn cần xác minh rằng conversion không mất precision hoặc tràn miền. Với tiền tệ và decimal, ưu tiên `BigDecimal` và một hợp đồng conversion được kiểm thử.

### 7.3. SQL NULL và key không tồn tại

~~~java
Object salary = row.get("salary");
boolean salaryColumnIsPresent = row.containsKey("salary");
~~~

`row.get("salary") == null` có thể do:

1. SQL có cột `salary` nhưng giá trị hàng là `NULL`.
2. Kết quả không có key `salary` (ví dụ SELECT bỏ cột, hoặc alias khác).

Dùng `containsKey` khi phải phân biệt hai trường hợp. Map tự do cho phép cả hai, nhưng domain contract có thể yêu cầu một trường luôn hiện diện.

### 7.4. Đừng biến map thành “domain model ẩn”

Nếu logic ở nhiều nơi đều ép `(String) row.get("employee_name")`, thì chuỗi `"employee_name"` đã trở thành một hợp đồng *không được compiler kiểm tra*. Gõ nhầm `"employee_nmae"` vẫn biên dịch. Một `record EmployeeSummary(long id, String name, BigDecimal salary)` làm hợp đồng kiểu rõ ràng và dễ refactor hơn.

Map có giá trị trong dashboard động, bảng tùy chọn cột, truy vấn SQL ad hoc hoặc báo cáo không có model cố định. Với dữ liệu nghiệp vụ bền vững, nên tạo một lớp ánh xạ tường minh.

## 8. Lựa chọn map, scalar và DTO theo tình huống

| Tình huống | Lựa chọn | Lý do |
| --- | --- | --- |
| Danh sách kết quả động, nhiều cột | `queryForList` → `List<Map<String, Object>>` | Không phải cố định class cho từng projection |
| Đúng một hàng cấu hình theo khóa duy nhất | `queryForMap` | Rõ hợp đồng một hàng; cần xử lý 0 hàng |
| Danh sách tên/mã đơn cột | `queryForList(sql, String.class)` | Kết quả có type phần tử và ít overhead |
| Đếm số hàng bằng `COUNT(*)` | `queryForObject(sql, Integer.class)` | Một giá trị scalar |
| Danh sách entity/DTO được dùng nhiều tầng | `query(sql, RowMapper<Dto>)` | Compiler có thể kiểm tra các field và method |
| Một đối tượng miền | `queryForObject(sql, RowMapper<T>)` khi có đúng 1 hàng | Mapping domain có kiểu, rõ cardinality |
| Tổng hợp nhiều hàng thành cây/nhóm | `ResultSetExtractor` hoặc thuật toán grouping | Một hàng SQL có thể không là một object độc lập |

Không áp đặt một lựa chọn cho tất cả. `queryForList` dùng map không sai, nhưng nên được dùng có chủ đích. Khi kết quả thay đổi và không có cấu trúc bền vững, map thuận tiện; khi có hợp đồng API ổn định hoặc nhiều quy tắc nghiệp vụ, DTO dễ bảo trì hơn.

## 9. Demo đầy đủ chạy được: Spring JDBC 6.x + H2 + Java 17

Ví dụ console chạy với **Java 17+**, **Maven 3.9+**, **Spring JDBC 6.1.14** và **H2 2.2.224**. Mục đích là quan sát chính xác dạng trả về và ngoại lệ số lượng kết quả mà không cần cấu hình Spring Boot.

### 9.1. Cấu trúc

~~~text
jdbc-map-demo/
├── pom.xml
└── src/main/java/demo/
    └── JdbcMapDemo.java
~~~

### 9.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jdbc-map-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.3. `src/main/java/demo/JdbcMapDemo.java`

~~~java
package demo;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class JdbcMapDemo {

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:jdbc_map_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("CREATE TABLE employee (" +
                "id BIGINT PRIMARY KEY, " +
                "name VARCHAR(60) NOT NULL, " +
                "salary DECIMAL(10,2) NULL)");

        jdbc.update(
                "INSERT INTO employee(id, name, salary) VALUES (?, ?, ?)",
                1L, "An", new BigDecimal("120.50"));
        jdbc.update(
                "INSERT INTO employee(id, name, salary) VALUES (?, ?, ?)",
                2L, "Binh", (BigDecimal) null);
        jdbc.update(
                "INSERT INTO employee(id, name, salary) VALUES (?, ?, ?)",
                3L, "Chi", new BigDecimal("200.00"));

        String projection =
                "SELECT id AS \"employee_id\", " +
                "name AS \"employee_name\", " +
                "salary AS \"salary\" FROM employee";

        // Nhiều hàng, mỗi hàng là Map<String, Object>.
        List<Map<String, Object>> rows =
                jdbc.queryForList(projection + " ORDER BY id");
        System.out.println("Rows: " + rows.size());
        System.out.println("First: " + rows.get(0).get("employee_name"));

        long firstId =
                ((Number) rows.get(0).get("employee_id")).longValue();
        System.out.println("First id: " + firstId);

        // Nhiều hàng, một cột: List<String>.
        List<String> names = jdbc.queryForList(
                "SELECT name FROM employee ORDER BY id", String.class);
        System.out.println("Names: " + names);

        // Đúng một hàng với Map.
        Map<String, Object> one = jdbc.queryForMap(
                projection + " WHERE id = ?", 2L);
        System.out.println("One row: " + one.get("employee_name"));
        System.out.println("Null salary: " +
                (one.containsKey("salary") && one.get("salary") == null));

        // Danh sách không có hàng trả về size = 0.
        List<Map<String, Object>> empty =
                jdbc.queryForList("SELECT id FROM employee WHERE id < ?", 0L);
        System.out.println("No rows: " + empty.size());

        // queryForMap không tìm thấy: ngoại lệ.
        try {
            jdbc.queryForMap("SELECT id FROM employee WHERE id = ?", 999L);
        } catch (EmptyResultDataAccessException expected) {
            System.out.println("Missing: " +
                    expected.getClass().getSimpleName());
        }

        // queryForMap có nhiều hàng: ngoại lệ.
        try {
            jdbc.queryForMap("SELECT id FROM employee ORDER BY id");
        } catch (IncorrectResultSizeDataAccessException expected) {
            System.out.println("Multiple: " +
                    expected.getClass().getSimpleName());
        }
    }
}
~~~

Chạy tại thư mục `jdbc-map-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JdbcMapDemo
~~~

**Các dòng chương trình in ra** (không tính log công cụ build nếu có):

~~~text
Rows: 3
First: An
First id: 1
Names: [An, Binh, Chi]
One row: Binh
Null salary: true
No rows: 0
Missing: EmptyResultDataAccessException
Multiple: IncorrectResultSizeDataAccessException
~~~

### 9.4. Vì sao stdout như trên?

1. `JdbcTemplate` tạo bảng H2 in-memory và ghi ba hàng có ID 1, 2, 3. `DriverManagerDataSource` cung cấp connection mới mỗi lần, thích hợp demo, không có connection pool cho production.
2. `queryForList(projection + " ORDER BY id")` trả ba map. Alias được trích rõ trong dấu ngoặc kép của H2; truy xuất `employee_name` ở hàng đầu nhận `"An"`. `employee_id` là một giá trị số nên có thể chuyển qua `Number.longValue()` và in 1.
3. `queryForList(..., String.class)` chỉ lấy cột `name`, thứ tự bảo đảm do `ORDER BY id`, vì vậy danh sách in `[An, Binh, Chi]`.
4. `queryForMap(... WHERE id = 2)` tìm đúng một hàng. Key `employee_name` có giá trị `"Binh"`; key `salary` tồn tại nhưng value null vì SQL NULL.
5. `queryForList` với `id < 0` có 0 hàng nên list rỗng.
6. `queryForMap` với `id = 999` không có hàng và ném `EmptyResultDataAccessException`.
7. `queryForMap` không có `WHERE` trả ba hàng, trái hợp đồng đúng một hàng nên ném `IncorrectResultSizeDataAccessException`.

Ví dụ cố ý **không in trực tiếp `Map.toString()`** để tránh phụ thuộc vào kiểu numeric hoặc thứ tự/cách viết key do metadata JDBC/driver cung cấp.

### 9.5. Thử nghiệm để hiểu sâu

**Thử A:** Thay `queryForList("SELECT name ...", String.class)` bằng truy vấn hai cột `SELECT id, name` mà vẫn truyền `String.class`. Mapper một cột sẽ báo số cột không phù hợp.

**Thử B:** Đổi `SELECT id AS "employee_id"` thành `SELECT id AS "id"` nhưng vẫn gọi `get("employee_id")`. Không có key đúng, bạn có thể nhận null. Đây là lý do nên coi alias là một phần của hợp đồng dữ liệu.

**Thử C:** Bỏ `ORDER BY` nhưng vẫn dùng `rows.get(0)` như “nhân viên có ID nhỏ nhất”. Database không bảo đảm thứ tự hàng nếu không có ordering; cần khôi phục `ORDER BY` khi thứ tự có ý nghĩa.

**Thử D:** Đổi truy vấn duy nhất từ `WHERE id = 2` sang `WHERE salary IS NULL`. Nếu bảng có nhiều hàng salary null, `queryForMap` sẽ ném lỗi cardinality. Query phải phản ánh điều kiện nghiệp vụ thực sự unique.

**Thử E:** Truy vấn bỏ cột salary và kiểm tra `containsKey("salary")`. Kết quả khác với một hàng có cột salary nhưng SQL NULL; hai trường hợp không nên được gộp làm một lỗi.

## 10. Hiệu năng và an toàn khi dùng map

### 10.1. Không đọc vô hạn số hàng vào bộ nhớ

`queryForList` vật hóa tất cả hàng thành danh sách và mỗi hàng thành map. Nếu SQL trả 500.000 dòng với nhiều cột, bộ nhớ và allocation có thể lớn. Chọn `WHERE`, projection chỉ gồm các cột cần thiết và pagination/`LIMIT` tương ứng với database.

Với xử lý dữ liệu lớn hoặc streaming, cân nhắc `RowCallbackHandler`, `ResultSetExtractor`, cách đọc theo lô hoặc cursor phù hợp vòng đời connection và transaction. Không biến `queryForList` thành API streaming chỉ bằng việc dùng một iterator của list: dữ liệu đã được nạp trước.

### 10.2. SQL injection và parameter binding

Đúng:

~~~java
List<Map<String, Object>> found = jdbcTemplate.queryForList(
    "SELECT id, name FROM employee WHERE name = ?", suppliedName);
~~~

Sai:

~~~java
// Không nối dữ liệu người dùng trực tiếp vào SQL.
String sql = "SELECT id FROM employee WHERE name = '" +
        suppliedName + "'";
~~~

`?` dùng cho **giá trị**; không dùng để bind tên bảng/cột hoặc hướng `ORDER BY`. Với tên cột được người dùng chọn, dùng whitelist trong code thay vì ghép một chuỗi tùy ý.

### 10.3. Chọn transaction theo nghiệp vụ

`queryForList` và `queryForMap` là API truy vấn, không tự mở transaction bao trùm nhiều bước nghiệp vụ. Nếu service cần đọc rồi cập nhật theo các ràng buộc đồng thời, hãy cấu hình transaction boundary/isolation/locking phù hợp. Kiểu ánh xạ Map hay DTO không thay đổi semantics commit/rollback của database.

### 10.4. Không gửi map thẳng qua mọi tầng nếu schema cố định

Khi map được dùng để xây JSON/CSV hoặc DTO, cần quy định chuẩn tên key, nullability, kiểu ngày giờ/số tiền, chuyển kiểu và kiểm tra dữ liệu. Map rất phù hợp cho projection động; với cấu trúc sử dụng ổn định, tạo DTO/record và `RowMapper` giúp code dễ refactor và dễ test.

### 10.5. Query trả đúng số hàng quan trọng hơn việc “làm cho chạy”

Với `queryForMap`, việc ném lỗi nhiều hàng có thể chỉ ra SQL chưa đủ điều kiện hoặc database thiếu uniqueness constraint. Dùng `LIMIT 1` để che một vi phạm uniqueness có thể khiến dữ liệu nghiệp vụ âm thầm sai. Cần quyết định số hàng đúng theo use case rồi chọn API phù hợp.

## 11. Lỗi phổ biến và phương pháp chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `EmptyResultDataAccessException` từ `queryForMap` | 0 hàng | Kiểm tra điều kiện, xác định có chấp nhận không tìm thấy không |
| `IncorrectResultSizeDataAccessException` từ `queryForMap` | Nhiều hàng | Sửa uniqueness/WHERE hoặc chọn `queryForList` |
| `IncorrectResultSetColumnCountException` | `queryForList(sql, Class<T>)` nhận SQL nhiều cột | Chỉ SELECT một cột, hoặc chuyển sang `RowMapper` |
| `ClassCastException` khi đọc map | JDBC value có type khác giả định | Kiểm tra kiểu thực tế, chuyển đổi tường minh |
| `row.get("name")` là null | Tên alias sai, không SELECT cột, hoặc SQL NULL | Kiểm tra `containsKey` và projection |
| JOIN mất một cột `id` | Hai cột có label trùng | Đặt alias độc nhất |
| Hàng đầu không ổn định | Không có `ORDER BY` | Chọn ordering có tie-breaker khi cần |
| Truy vấn dùng quá nhiều RAM | List map quá lớn | Lọc, phân trang, giảm cột hoặc xử lý streaming |
| Truy vấn gặp `DataAccessException` | SQL, schema, connection hoặc conversion có lỗi | Đọc nguyên nhân gốc và SQL/parameter, tránh đoán do map |

**Quy trình debug thực tế:**

1. Chạy SQL với cùng tham số ở môi trường test để xác nhận **số hàng và số cột**.
2. Kiểm tra API: `queryForMap` cần đúng một dòng; `queryForList(sql, Class<T>)` cần một cột.
3. In/kiểm tra tên alias và kiểu runtime trong môi trường kiểm thử, không ghi dữ liệu nhạy cảm vào log production.
4. Kiểm tra SQL NULL khác với key không tồn tại.
5. Xem `ORDER BY`, phân trang và quy mô dữ liệu.
6. Nếu nhiều lớp dựa vào các key map cố định, chuyển sang DTO/`RowMapper` và kiểm thử mapping.

## 12. Tự kiểm tra kiến thức

**Câu 1:** `queryForList("SELECT id, name FROM employee")` có kết quả Java kiểu gì?  
**Đáp án:** `List<Map<String, Object>>`: mỗi dòng là một map của column label sang value.

**Câu 2:** `queryForList("SELECT name FROM employee", String.class)` có kết quả kiểu gì?  
**Đáp án:** `List<String>`, vì overload có `Class<T>` dùng mapper một cột.

**Câu 3:** `queryForMap` khi không có dòng có trả map rỗng?  
**Đáp án:** Không, nó ném `EmptyResultDataAccessException`.

**Câu 4:** `queryForMap` khi có ba dòng có lấy dòng đầu?  
**Đáp án:** Không, nó ném `IncorrectResultSizeDataAccessException`.

**Câu 5:** Vì sao `row.get("salary") == null` chưa chứng minh salary là SQL NULL?  
**Đáp án:** Key salary có thể vắng mặt. Dùng `containsKey` phân biệt hai trường hợp.

**Câu 6:** `queryForList(sql, Employee.class)` có thể ánh xạ hai cột `id` và `name` thành record Employee?  
**Đáp án:** Không. Hình thức đó yêu cầu một cột scalar; cần `RowMapper<Employee>`.

**Câu 7:** Hai bảng JOIN đều có cột `id`; làm sao tránh mất thông tin trong map?  
**Đáp án:** Chọn alias khác nhau như `employee_id` và `department_id`.

**Câu 8:** Vì sao ánh xạ map thiếu an toàn kiểu miền hơn DTO?  
**Đáp án:** Compiler không kiểm tra key dạng chuỗi và kiểu runtime `Object`, dễ gây sai alias/null/cast.

**Câu 9:** Khi dùng `queryForList` với hàng trăm nghìn kết quả, điều cần quan tâm?  
**Đáp án:** Bộ nhớ, pagination/projection, nhu cầu streaming và vòng đời tài nguyên.

**Câu 10:** `queryForMap` có tự quản lý transaction nghiệp vụ không?  
**Đáp án:** Không. Nó chọn/ánh xạ kết quả; transaction thuộc cấu hình và ranh giới giao dịch riêng.

## 13. Tài liệu tham khảo

- [Spring Framework – JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, bind tham số, map và typed query.
- [JdbcTemplate Javadoc – Spring Framework 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): overload của `queryForList`/`queryForMap`.
- [ColumnMapRowMapper Javadoc – Spring Framework 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/ColumnMapRowMapper.html): ánh xạ mỗi `ResultSet` row thành map.
- [SingleColumnRowMapper Javadoc – Spring Framework 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/SingleColumnRowMapper.html): ánh xạ từ một cột sang một Java scalar value.

**Ghi nhớ:** `queryForList` trả danh sách map khi không có `elementType`; `queryForMap` yêu cầu đúng một hàng; `queryForList` có `elementType` trả danh sách scalar một cột. Sử dụng map khi projection linh hoạt, và dùng `RowMapper`/DTO khi dữ liệu là hợp đồng miền ổn định.

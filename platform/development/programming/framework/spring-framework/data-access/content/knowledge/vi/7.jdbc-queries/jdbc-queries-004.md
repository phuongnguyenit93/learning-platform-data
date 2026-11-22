# Nhiều hàng khi chỉ mong một hàng và IncorrectResultSizeDataAccessException

Trong Spring JDBC, một truy vấn có thể chạy thành công ở cơ sở dữ liệu nhưng **kết quả vẫn vi phạm hợp đồng mà ứng dụng yêu cầu**. Trường hợp điển hình: code dùng `JdbcTemplate.queryForObject(...)` để lấy đúng **một hàng**, nhưng điều kiện `WHERE` thực tế khớp **hai hàng trở lên**. Spring khi đó ném `IncorrectResultSizeDataAccessException`. Đây là tín hiệu rằng **số hàng trả về không phù hợp với số hàng mong đợi**, không tự chứng minh SQL sai cú pháp hoặc database mất kết nối.

Bài học tập trung vào cơ chế cardinality (số lượng hàng), cách đọc và xử lý exception, nguyên nhân thực tế như dữ liệu trùng hay `JOIN` tạo thêm hàng, và cách chọn giữa `queryForObject`, `query`, lookup tùy chọn và ràng buộc duy nhất. Mọi ví dụ sử dụng Spring JDBC; `@Transactional` chỉ xuất hiện khi cần giải thích hậu quả xử lý lỗi trong giao dịch.

## 1. Hợp đồng của truy vấn “đúng một hàng”

Hãy phân biệt ba yêu cầu nghiệp vụ thường gặp:

- **Exactly one — đúng một:** Tìm tài khoản theo khóa chính đã biết chắc phải tồn tại; số hàng hợp lệ là **1**.
- **Zero or one — không hoặc một:** Tìm hồ sơ tùy chọn theo định danh duy nhất; số hàng hợp lệ là **0 hoặc 1**.
- **Zero or many — không hoặc nhiều:** Tìm tất cả đơn hàng của khách; số hàng hợp lệ là **0, 1, 2, ...**.

`queryForObject` diễn đạt **exactly one**, chứ không mang nghĩa “lấy hàng đầu tiên nếu có”. Hãy đọc bảng sau khi truy vấn sử dụng một overload `queryForObject` thông thường:

| Số hàng SQL trả về | Đối với `queryForObject` | Ý nghĩa |
| --- | --- | --- |
| 0 | `EmptyResultDataAccessException` | Mong 1 nhưng nhận 0; đây là subclass của `IncorrectResultSizeDataAccessException`. |
| 1 | Trả về đối tượng đã được ánh xạ (có thể `null` nếu nội dung hàng được map thành null) | Số hàng đúng; vẫn phải xét kiểu dữ liệu và số cột theo overload sử dụng. |
| 2 | `IncorrectResultSizeDataAccessException` | Mong 1 nhưng có 2. |
| 3 trở lên | `IncorrectResultSizeDataAccessException` | Mong 1 nhưng có nhiều hơn 1. |

Điểm mấu chốt là **đếm hàng trước khi quyết định trả về một object**. Dù hai hàng chứa cùng tên hoặc cùng giá trị, chúng vẫn là **hai hàng**. Ngay cả khi `RowMapper` tạo ra hai object bằng nhau theo `equals()`, điều kiện “một hàng” vẫn không đạt.

Ví dụ:

```sql
SELECT id, email
FROM customer
WHERE email = 'anna@example.test';
```

Nếu có hai bản ghi cùng email, câu SQL vẫn là truy vấn hợp lệ. `queryForObject` sẽ không âm thầm chọn hàng bất kỳ; nó báo lỗi cardinality để người gọi xử lý sai lệch kỳ vọng.

## 2. Exception biểu thị điều gì?

Class chính:

```java
org.springframework.dao.IncorrectResultSizeDataAccessException
```

Đây là một `DataAccessException` không kiểm tra (unchecked exception, thuộc nhánh `RuntimeException`). Một số thuộc tính đáng quan tâm:

- `getExpectedSize()`: số kết quả mà thao tác kỳ vọng, thông thường `1`.
- `getActualSize()`: số kết quả thực tế nếu đã biết. Trong một số cách tạo exception có thể là `-1` khi số thực tế không xác định; vì vậy đừng mặc định giá trị này luôn dương.
- Thông báo lỗi thường tương tự `Incorrect result size: expected 1, actual 2`; format chính xác có thể thay đổi theo API/version.

Subclass quan trọng:

```java
org.springframework.dao.EmptyResultDataAccessException
```

`EmptyResultDataAccessException` **kế thừa `IncorrectResultSizeDataAccessException`** và thường biểu thị trường hợp kỳ vọng ít nhất một hàng nhưng thực tế nhận **0**. Vì vậy nếu muốn phân biệt “không tìm thấy” với “dữ liệu không duy nhất”, phải bắt exception chuyên biệt **trước** exception cha:

```java
// Ví dụ tích hợp: jdbc là JdbcTemplate được cấu hình.
try {
    String status = jdbc.queryForObject(
        "SELECT status FROM customer WHERE id = ?",
        String.class,
        customerId
    );
    System.out.println(status);
} catch (EmptyResultDataAccessException noRow) {
    // Không tìm thấy.
} catch (IncorrectResultSizeDataAccessException tooManyRows) {
    // Có nhiều hàng trong khi chỉ mong một.
}
```

Đoạn mã trên không phải file Java chạy độc lập; cần import, biến `jdbc`, `customerId` và database. Nếu bắt lớp cha trước, nhánh `EmptyResultDataAccessException` phía sau sẽ không được đi tới (và việc bắt subclass sau superclass trong Java là không hợp lệ).

### Đây có phải lỗi của SQL/driver không?

Không nhất thiết. Nhiều lúc database trả kết quả **đúng theo SQL**, còn Spring phát hiện kết quả không đáp ứng giao kèo API. Ví dụ `WHERE department_id = 10` có thể hợp lệ và cố ý trả 20 nhân viên; lỗi nằm ở việc code dùng `queryForObject` thay vì API đọc danh sách.

Ngược lại, nếu domain khẳng định email phải duy nhất mà truy vấn trả hai hàng thì exception báo hiệu **bất biến dữ liệu hoặc câu truy vấn đang sai**. Không nên biến mọi trường hợp này thành “không tìm thấy” hoặc “lấy bản ghi đầu tiên”.

## 3. `queryForObject` hoạt động ra sao trong Spring JDBC?

Các overload thông dụng:

```java
// Một hàng, một cột, ánh xạ về kiểu đơn giản.
String name = jdbc.queryForObject(
    "SELECT name FROM customer WHERE id = ?",
    String.class,
    id
);

// Một hàng, nhiều cột, sử dụng RowMapper.
Customer customer = jdbc.queryForObject(
    "SELECT id, name FROM customer WHERE id = ?",
    (rs, rowNum) -> new Customer(
        rs.getLong("id"), rs.getString("name")
    ),
    id
);
```

Đây là ví dụ tích hợp; `Customer` là type của ứng dụng, còn `jdbc` và `id` cần được khai báo. Trong ví dụ hoàn chỉnh bên dưới sẽ có model dùng được.

Ở overload `queryForObject(sql, Class<T>, args...)`, Spring dùng cơ chế ánh xạ **một giá trị cột** sang type yêu cầu. Trong overload `queryForObject(sql, RowMapper<T>, args...)`, `RowMapper` được dùng để xây dựng một object từ **một hàng có thể có nhiều cột**.

Cả hai đều áp dụng kỳ vọng **một hàng**. `RowMapper` không có nghĩa là “tự gom nhiều hàng thành một object”; nó được gọi cho các hàng mà JDBC trả về, rồi Spring kiểm tra kích thước kết quả.

Ngoài ra, `JdbcTemplate.queryForMap(...)` cũng dùng kỳ vọng **một hàng**, mặc dù object trả về là `Map<String, Object>` ánh xạ các cột của hàng ấy. Đừng nhầm “nhiều cột” với “nhiều hàng”.

Nếu muốn **nhiều hàng**, nên dùng `query(...)` với `RowMapper`:

```java
List<Customer> customers = jdbc.query(
    "SELECT id, name FROM customer WHERE department_id = ? ORDER BY id",
    (rs, rowNum) -> new Customer(
        rs.getLong("id"), rs.getString("name")
    ),
    departmentId
);
```

`query` trong trường hợp dùng `RowMapper` trả `List<Customer>` và chấp nhận kết quả rỗng, một hàng hoặc nhiều hàng. Việc gom thành danh sách có chi phí bộ nhớ tương ứng số hàng; với tập dữ liệu lớn nên có pagination hoặc chiến lược xử lý tuần tự phù hợp.

## 4. Phân biệt lỗi **số hàng**, lỗi **số cột** và giá trị SQL NULL

Đây là ba chuyện độc lập.

### Sai số hàng: `IncorrectResultSizeDataAccessException`

```sql
SELECT name
FROM customer
WHERE email = 'anna@example.test';
```

Nếu có 2 hàng, `queryForObject` báo lỗi **số hàng** mặc dù chỉ chọn một cột.

### Đúng một hàng nhưng chọn nhiều cột bằng `String.class`

```java
// Truy vấn trả 1 hàng với 2 cột; overload kiểu đơn chỉ cần 1 cột.
String wrong = jdbc.queryForObject(
    "SELECT id, name FROM customer WHERE id = ?",
    String.class,
    1L
);
```

Trong trường hợp đúng một hàng nhưng nhiều cột, overload một-giá-trị có thể ném `IncorrectResultSetColumnCountException`. Để nhận object nhiều thuộc tính, dùng `RowMapper<Customer>` thay vì `String.class`.

### Một hàng có giá trị SQL NULL

```sql
SELECT MAX(score)
FROM exam_result
WHERE student_id = -1;
```

Với aggregate `MAX` không có `GROUP BY`, DB thường trả **một hàng** chứa `NULL` khi không có dữ liệu phù hợp. `queryForObject(..., Integer.class)` khi đó có thể trả `null` mà **không ném** `EmptyResultDataAccessException`: cardinality là **1**, giá trị là **NULL**.

Tương tự, `RowMapper` có thể chủ động trả null cho một hàng. Do đó kết quả `null` không luôn đồng nghĩa với “không có hàng”. Khi viết lớp truy cập dữ liệu, phải xác định cụ thể đang kiểm tra **sự tồn tại của hàng** hay **giá trị của cột**.

## 5. Vì sao một truy vấn tưởng duy nhất lại trả nhiều hàng?

### 5.1. Điều kiện tìm kiếm không phải khóa duy nhất

Nếu `customer.email` không có ràng buộc unique, hai bản ghi có thể cùng email:

| id | email | plan |
| ---: | --- | --- |
| 1 | anna@example.test | gold |
| 2 | anna@example.test | silver |
| 3 | bob@example.test | bronze |

`WHERE id = ?` trên khóa chính trả tối đa một hàng. `WHERE email = ?` không có unique constraint có thể trả nhiều hàng. Kiểm tra **schema**, không chỉ ý định của tác giả code.

Tương tự, tìm bằng `first_name`, `status`, `department_id`, khoảng thời gian, `LIKE` hoặc trường không duy nhất thường là thao tác trả **tập hợp**.

### 5.2. `JOIN` nhân số hàng (join fan-out)

Ngay cả khi bảng cha có một bản ghi duy nhất, join với bảng con có nhiều bản ghi có thể nhân bản **hàng kết quả**:

```sql
-- customer.id là PRIMARY KEY; customer_note có thể có nhiều note/customer.
SELECT c.id, c.name
FROM customer c
JOIN customer_note n ON n.customer_id = c.id
WHERE c.id = 3;
```

Nếu khách 3 có hai note, SQL trên trả **hai hàng có cùng c.id và c.name**. Đó không nhất thiết là hai customer trùng trong bảng cha; mỗi hàng kết quả tương ứng một cặp join.

Nếu mục tiêu chỉ là biết customer có note hay không, dùng `EXISTS` thay vì join phát sinh nhiều hàng:

```sql
SELECT c.id, c.name
FROM customer c
WHERE c.id = 3
  AND EXISTS (
      SELECT 1
      FROM customer_note n
      WHERE n.customer_id = c.id
  );
```

Nếu cần tất cả note, dùng API trả danh sách và map quan hệ rõ ràng. Nếu cần tổng số note, sử dụng `COUNT`/`GROUP BY` hoặc truy vấn con theo ý nghĩa nghiệp vụ. Không dùng `DISTINCT` một cách mù quáng để “dập lỗi” vì việc loại bỏ trùng từ phép chiếu có thể che giấu quan hệ thật.

### 5.3. Mất điều kiện lọc hoặc lọc không đúng

Truy vấn kỳ vọng unique có thể thiếu `tenant_id`, `version`, `locale`, `deleted_at IS NULL` hoặc một phần khóa ghép. Ví dụ, `external_id` chỉ duy nhất **trong mỗi tenant**, nên `WHERE external_id = ?` không đủ; cần `WHERE tenant_id = ? AND external_id = ?` cùng unique constraint phù hợp.

Cũng phải xét chuẩn hóa dữ liệu: chữ hoa/thường của email, khoảng trắng, collation và cách xử lý soft-delete. Một điều kiện `LOWER(email) = LOWER(?)` không chứng minh DB có unique constraint trên cùng biểu thức.

### 5.4. Truy vấn `GROUP BY` trả nhiều nhóm

```sql
SELECT department_id, COUNT(*)
FROM employee
GROUP BY department_id;
```

Câu SQL trên trả một hàng **cho mỗi department**, không phải một hàng tổng số. Nếu thực sự muốn một tổng số duy nhất, chọn `SELECT COUNT(*) FROM employee` (không `GROUP BY`). Ngược lại nếu cần thống kê từng nhóm, dùng `query` để lấy danh sách.

## 6. Vì sao `LIMIT 1` thường là cách sửa sai?

Phản ứng dễ gặp:

```sql
SELECT id, email, plan
FROM customer
WHERE email = ?
LIMIT 1;
```

Câu này ép kết quả về tối đa một hàng, nhưng nếu email đáng lẽ phải duy nhất, nó **che giấu dữ liệu sai**. Không có `ORDER BY`, không có cam kết ổn định về “hàng đầu tiên”; kết quả có thể đổi theo index, kế hoạch thực thi, bản DB hoặc thời điểm dữ liệu thay đổi.

Ngay cả thêm `ORDER BY id ASC LIMIT 1` cũng chỉ biến “bản ghi có id nhỏ nhất” thành quy tắc chọn, **không giải quyết được invariant duy nhất**.

`LIMIT 1` (hoặc `FETCH FIRST 1 ROW ONLY` theo dialect) là hợp lý khi yêu cầu nghiệp vụ thực sự là **chọn một bản ghi**: ví dụ đơn hàng gần nhất của khách, tin mới nhất hoặc phiên làm việc có thời điểm cao nhất. Khi đó phải diễn đạt thứ tự rõ ràng, có tie-breaker ổn định:

```sql
SELECT id, created_at, status
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 1;
```

Đây là truy vấn **zero or one after limiting**, không đồng nghĩa chắc chắn tồn tại một đơn. Nếu không có bản ghi, `queryForObject` vẫn ném `EmptyResultDataAccessException`. Nếu thứ tự không có tie-breaker duy nhất, hai bản ghi cùng thời điểm có thể được chọn không ổn định.

Khi điều tra dữ liệu trùng mà không cần tải hàng triệu bản ghi về Java, có thể truy vấn tối đa **hai hàng** để kiểm tra “hơn một”:

```sql
SELECT id
FROM customer
WHERE email = ?
ORDER BY id
LIMIT 2;
```

Nếu `queryForObject` dùng kết quả này và báo `actualSize=2`, ta biết chắc **có ít nhất hai hàng**, không biết tổng số hàng gốc thực tế. Cách kiểm tra này không thay thế unique constraint.

## 7. Ví dụ Java 17+ hoàn chỉnh: ba kích thước kết quả và một lỗi JOIN

Ví dụ dùng Spring JDBC và H2 trong bộ nhớ, **không cần Spring Boot hoặc server**. Sử dụng `JdbcTemplate`, tạo bảng dữ liệu mẫu rồi kiểm chứng:

1. Một hàng → `queryForObject` trả kết quả.
2. Không hàng → `EmptyResultDataAccessException`.
3. Hai hàng → `IncorrectResultSizeDataAccessException`.
4. Nhiều hàng hợp lệ → `query` trả danh sách.
5. `COUNT(*)` không có `GROUP BY` vẫn trả một hàng với số đếm 0.
6. `JOIN` một-nhiều khiến truy vấn theo khóa chính customer có thể trả hai hàng.
7. Truy vấn theo khóa chính của bảng cha không join trả đúng một object.

### Tạo Maven project

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>jdbc-one-row-demo</artifactId>
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
```

File `src/main/java/OneRowDemo.java`:

```java
import java.util.List;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class OneRowDemo {
    private record Customer(long id, String email, String plan) {}

    public static void main(String[] args) {
        DriverManagerDataSource source = new DriverManagerDataSource(
                "jdbc:h2:mem:one_row_demo;DB_CLOSE_DELAY=-1", "sa", "");
        JdbcTemplate jdbc = new JdbcTemplate(source);

        jdbc.execute(
            "CREATE TABLE customer (" +
            "id BIGINT PRIMARY KEY, " +
            "email VARCHAR(100) NOT NULL, " +
            "plan VARCHAR(20) NOT NULL)");
        jdbc.execute(
            "CREATE TABLE customer_note (" +
            "note_id INT PRIMARY KEY, " +
            "customer_id BIGINT NOT NULL, " +
            "body VARCHAR(100) NOT NULL)");

        jdbc.update(
            "INSERT INTO customer (id, email, plan) VALUES (?, ?, ?)",
            1L, "anna@example.test", "gold");
        jdbc.update(
            "INSERT INTO customer (id, email, plan) VALUES (?, ?, ?)",
            2L, "anna@example.test", "silver");
        jdbc.update(
            "INSERT INTO customer (id, email, plan) VALUES (?, ?, ?)",
            3L, "bob@example.test", "bronze");

        jdbc.update(
            "INSERT INTO customer_note (note_id, customer_id, body) " +
            "VALUES (?, ?, ?)", 10, 3L, "note A");
        jdbc.update(
            "INSERT INTO customer_note (note_id, customer_id, body) " +
            "VALUES (?, ?, ?)", 11, 3L, "note B");

        String one = jdbc.queryForObject(
            "SELECT plan FROM customer WHERE email = ?",
            String.class, "bob@example.test");
        System.out.println("One row: " + one);

        try {
            jdbc.queryForObject(
                "SELECT plan FROM customer WHERE email = ?",
                String.class, "missing@example.test");
        } catch (EmptyResultDataAccessException e) {
            System.out.println("No row: actual=" + e.getActualSize());
        }

        try {
            jdbc.queryForObject(
                "SELECT plan FROM customer WHERE email = ?",
                String.class, "anna@example.test");
        } catch (IncorrectResultSizeDataAccessException e) {
            System.out.println(
                "Multiple rows: expected=" + e.getExpectedSize() +
                ", actual=" + e.getActualSize());
        }

        List<String> matches = jdbc.query(
            "SELECT id, plan FROM customer " +
            "WHERE email = ? ORDER BY id",
            (rs, rowNum) ->
                rs.getLong("id") + ":" + rs.getString("plan"),
            "anna@example.test");
        System.out.println("All matching: " + matches);

        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM customer WHERE email = ?",
            Long.class, "missing@example.test");
        System.out.println("Count missing: " + count);

        try {
            jdbc.queryForObject(
                "SELECT c.plan FROM customer c " +
                "JOIN customer_note n ON n.customer_id = c.id " +
                "WHERE c.id = ?",
                String.class, 3L);
        } catch (IncorrectResultSizeDataAccessException e) {
            System.out.println(
                "Join produced: " + e.getActualSize() + " rows");
        }

        RowMapper<Customer> mapper = (rs, rowNum) ->
            new Customer(
                rs.getLong("id"),
                rs.getString("email"),
                rs.getString("plan"));

        Customer byId = jdbc.queryForObject(
            "SELECT id, email, plan FROM customer WHERE id = ?",
            mapper, 3L);
        System.out.println(
            "By primary key: " + byId.id() + "/" + byId.plan());
    }
}
```

Chạy trong thư mục có `pom.xml` bằng JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=OneRowDemo
```

Các dòng do chương trình `System.out.println` tạo ra:

```text
One row: bronze
No row: actual=0
Multiple rows: expected=1, actual=2
All matching: [1:gold, 2:silver]
Count missing: 0
Join produced: 2 rows
By primary key: 3/bronze
```

**Giải thích bằng dữ liệu của demo:**

- `bob@example.test` xuất hiện một lần → `queryForObject` trả `bronze`.
- `missing@example.test` không có hàng → subclass `EmptyResultDataAccessException` và `getActualSize() = 0`.
- `anna@example.test` xuất hiện hai lần → superclass `IncorrectResultSizeDataAccessException` với `expectedSize = 1`, `actualSize = 2`.
- `query` cho email Anna giữ đủ hai hàng và thứ tự `ORDER BY id` → `[1:gold, 2:silver]`.
- `SELECT COUNT(*)` không `GROUP BY` trả một hàng chứa 0 → không bị nhầm với “0 hàng”.
- Customer id 3 chỉ có một hàng, nhưng có hai `customer_note` → phép `JOIN` tạo hai hàng kết quả và `queryForObject` báo sai cardinality.
- Truy vấn customer bằng khóa chính và không join trả đúng một hàng, sau đó `RowMapper` xây dựng `Customer`.

`DriverManagerDataSource` trong ví dụ tạo kết nối mỗi lần cần và **không phải một pool**; không dùng cấu hình này làm mẫu hiệu năng production. Mục tiêu của demo là hành vi của truy vấn JDBC và hợp đồng kết quả.

## 8. Khi nào nên dùng `queryForObject`, `query`, `Optional`?

Hãy chọn API **sau khi xác định số hàng nghiệp vụ cho phép**.

| Kỳ vọng nghiệp vụ | API/cách dùng | Nếu nhận 0 | Nếu nhận trên 1 |
| --- | --- | --- | --- |
| Chính xác một hàng | `queryForObject(sql, RowMapper, args...)` | `EmptyResultDataAccessException` | `IncorrectResultSizeDataAccessException` |
| Chính xác một hàng, một cột | `queryForObject(sql, Class<T>, args...)` | `EmptyResultDataAccessException` | `IncorrectResultSizeDataAccessException` |
| Có thể không có, nhưng phải duy nhất nếu có | Bắt **riêng** `EmptyResultDataAccessException` rồi trả `Optional.empty()`, giữ nguyên lỗi >1 | `Optional.empty()` | Lỗi dữ liệu không duy nhất vẫn được giữ |
| Có thể không có hoặc nhiều | `query(sql, RowMapper, args...)` / `queryForList(...)` | List rỗng | List nhiều phần tử |
| Muốn tổng số hàng | `SELECT COUNT(*)` không `GROUP BY` + `queryForObject(..., Long.class)` | Số 0 | Truy vấn vẫn trả một hàng tổng |
| Muốn bản ghi mới nhất | `ORDER BY ... DESC` + giới hạn 1, đồng thời xử lý trường hợp không có | Không có → cần chính sách xử lý | Kết quả đã được chọn theo quy tắc, khác yêu cầu duy nhất |

### Ví dụ trả `Optional` khi 0 hàng là hợp lệ

```java
import java.util.Optional;
import org.springframework.dao.EmptyResultDataAccessException;

// Đoạn minh họa trong repository có JdbcTemplate jdbc.
public Optional<Customer> findOptionalById(long id) {
    try {
        return Optional.ofNullable(jdbc.queryForObject(
            "SELECT id, email, plan FROM customer WHERE id = ?",
            (rs, rowNum) -> new Customer(
                rs.getLong("id"),
                rs.getString("email"),
                rs.getString("plan")),
            id));
    } catch (EmptyResultDataAccessException notFound) {
        return Optional.empty();
    }
}
```

Đây là method tích hợp cần field `jdbc` và type `Customer`, không phải file Java độc lập. Nó **không nuốt** `IncorrectResultSizeDataAccessException` khi có nhiều hàng. Với khóa chính, nhiều hàng không nên xảy ra nếu schema đúng; nếu xảy ra ở một truy vấn phức tạp, cần tìm lỗi câu SQL hoặc quan hệ join.

`Optional.ofNullable` có thể cho `Optional.empty()` khi một `RowMapper` trả null dù SQL có một hàng. Vì vậy nếu cần phân biệt chính xác “không có hàng” với “một hàng có giá trị null”, hãy định nghĩa mapper trả object không-null đại diện cho hàng, hoặc dùng kiểu kết quả mang thông tin tồn tại rõ ràng.

### `DataAccessUtils` cho danh sách đã truy vấn

Spring có các helper cardinality, ví dụ:

```java
// Minh họa: customers là List<Customer> đã lấy từ jdbc.query(...).
Customer required = DataAccessUtils.requiredSingleResult(customers);
Customer maybe = DataAccessUtils.singleResult(customers);
Optional<Customer> optional = DataAccessUtils.optionalResult(customers);
```

Cần import `org.springframework.dao.support.DataAccessUtils` và `java.util.Optional`. Ví dụ là đoạn tích hợp, không có `customers` trong một file chạy riêng.

Với danh sách hợp lệ:

- `requiredSingleResult`: yêu cầu có đúng một phần tử; rỗng hoặc nhiều đều lỗi.
- `singleResult`: rỗng trả null, nhiều hơn một ném `IncorrectResultSizeDataAccessException`.
- `optionalResult`: rỗng trả `Optional.empty()`, nhiều hơn một ném exception; dùng khi muốn giao diện có/không rõ ràng.

Chỉ dùng các helper này **khi đã chủ động lấy danh sách**; chúng không khắc phục việc truy vấn trước đó đã trả quá nhiều hàng và có thể làm tăng chi phí nếu không giới hạn dataset. Với mapper có thể trả null, cần cân nhắc ý nghĩa của `null` theo hợp đồng helper và domain.

## 9. Xử lý dữ liệu trùng: sửa truy vấn hay sửa schema?

Khi nhận nhiều hàng mà chỉ mong một hàng, cần phân biệt **ba tình huống**.

### A. Truy vấn thực ra là truy vấn danh sách

Ví dụ: mọi hóa đơn của một khách, nhiều địa chỉ nhận hàng, nhiều quyền của một tài khoản. Đây là dữ liệu một-nhiều hợp lệ. Sửa repository sang `query` và để service quyết định cách dùng danh sách.

```java
List<Long> orderIds = jdbc.queryForList(
    "SELECT id FROM orders WHERE customer_id = ? ORDER BY id",
    Long.class,
    customerId
);
```

Đây là đoạn tích hợp vào JDBC repository, cần bảng `orders` và biến tương ứng. `queryForList(sql, Class<T>, args...)` trả một giá trị từ **mỗi hàng** và vẫn yêu cầu mỗi hàng có đúng một cột phù hợp; nếu cần nhiều cột hãy dùng `query` với `RowMapper`.

### B. Truy vấn vô tình nhân bản hàng do JOIN

Sửa dạng SQL theo mục đích: dùng `EXISTS` nếu chỉ cần điều kiện tồn tại ở bảng con; dùng group/aggregate khi cần tổng hợp; hoặc map một-nhiều thành collection nếu cần giữ toàn bộ quan hệ. `SELECT DISTINCT` chỉ phù hợp khi loại bỏ hàng trùng ở **phép chiếu** đúng là yêu cầu nghiệp vụ; nó có thể làm mất thông tin và không sửa được dữ liệu gốc.

### C. Domain thực sự yêu cầu giá trị duy nhất

Ví dụ: mã đăng nhập, số hóa đơn trong một tenant, external key theo provider. Khi đó:

1. Xác minh khóa nghiệp vụ đầy đủ, bao gồm tenant, trạng thái active/soft-delete và chuẩn hóa.
2. Tìm bản ghi trùng và đánh giá cách xử lý dữ liệu lịch sử; không tùy tiện xóa một trong hai.
3. Đặt `UNIQUE` constraint/index ở database cho đúng tổ hợp cột hoặc biểu thức nếu hệ quản trị hỗ trợ.
4. Giữ logic xử lý lỗi xung đột khi ghi. Không dựa riêng vào bước `SELECT` trước khi `INSERT` để bảo đảm duy nhất, vì hai transaction có thể cùng kiểm tra rồi cùng ghi.

Ví dụ schema minh họa khi email phải duy nhất toàn bảng:

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    CONSTRAINT uq_account_email UNIQUE (email)
);
```

Nếu dữ liệu đã có hai hàng cùng email, việc thêm ràng buộc có thể **thất bại** cho đến khi xử lý trùng. Nếu quy tắc chỉ duy nhất trong tenant, ràng buộc thường phải nằm trên cặp `(tenant_id, email)` thay vì `email` riêng lẻ. Kiểu đối chiếu chữ hoa/thường, khoảng trắng và soft-delete phụ thuộc thiết kế/domain và DB dialect.

Với dữ liệu đã được DB bảo vệ bằng unique constraint phù hợp, câu `SELECT ... WHERE unique_key = ?` có thể được thiết kế để trả tối đa một hàng. Khi đó `queryForObject` là lựa chọn hợp lý nếu record bắt buộc phải tồn tại.

## 10. Exception và giao dịch Spring

`IncorrectResultSizeDataAccessException` là unchecked exception thuộc `DataAccessException`. Nếu nó đi ra ngoài một phương thức `@Transactional` thực sự được Spring intercept và đang có transaction thích hợp, quy tắc rollback mặc định của Spring cho `RuntimeException` thường khiến transaction rollback.

```java
// Minh họa service tích hợp; repository có phương thức findExactlyOne.
@Transactional
public void registerPurchase(long customerId) {
    jdbc.update(
        "INSERT INTO purchase_audit (customer_id) VALUES (?)",
        customerId
    );

    Customer customer = repository.findExactlyOne(customerId);
    // Nếu phương thức trên ném IncorrectResultSizeDataAccessException,
    // transaction có thể rollback cả INSERT trước đó.
}
```

Code chưa độc lập vì thiếu class/field thực tế và schema. Nếu lỗi bị **bắt và nuốt** bên trong transaction, phương thức vẫn kết thúc bình thường thì Spring có thể commit phần thay đổi trước đó, trừ khi transaction đã được đánh dấu rollback-only vì lý do khác.

Không nên biến lỗi “có nhiều hàng nhưng lẽ ra một” thành một giá trị mặc định rồi tiếp tục workflow quan trọng. Nếu nghiệp vụ cho phép vắng record, chỉ bắt `EmptyResultDataAccessException`; nếu nhiều record là sai bất biến, để lỗi có ý nghĩa được ghi nhận hoặc chuyển thành exception domain rõ ràng mà vẫn bảo toàn chính sách transaction.

Lưu ý khi trả lỗi qua API: một ngoại lệ dữ liệu không duy nhất có thể là lỗi dữ liệu/configuration phía server, hoặc xung đột domain cần trình bày có kiểm soát; không tự mặc định mọi `IncorrectResultSizeDataAccessException` đều phải trả HTTP 404/409/500. Quyết định phụ thuộc hợp đồng API và nơi phát sinh sai lệch.

## 11. Cách chẩn đoán trong hệ thống thật

Khi thấy `IncorrectResultSizeDataAccessException: expected 1, actual 2`, một trình tự điều tra hữu ích là:

1. **Xác định chính xác call site:** overload `queryForObject` hay `queryForMap` nào? Query có đang thiết kế là exactly one không?
2. **Chép lại SQL và tham số ở môi trường kiểm thử an toàn:** tham số đã lọc đúng tenant, trạng thái, khoảng thời gian chưa? Không lộ dữ liệu cá nhân/secret trong log.
3. **Chạy câu SELECT dạng nhiều hàng:** kiểm tra các hàng thực tế, khóa chính và khóa nghiệp vụ. Đừng chỉ xem một hàng đầu tiên của UI database client.
4. **Kiểm tra các JOIN:** nhóm kết quả theo khóa gốc và đếm số dòng phía bảng con. Một customer gốc có thể tạo nhiều hàng join.
5. **Đối chiếu schema:** có `PRIMARY KEY`/`UNIQUE` trên đúng tổ hợp cột? Có dữ liệu lịch sử chưa xử lý? Unique có bị vô hiệu vì NULL hoặc điều kiện index không bao phủ?
6. **Quyết định hợp đồng mới cho repository:** exactly one, zero-or-one hay many? Thay SQL, API hoặc ràng buộc tương ứng.
7. **Thêm kiểm thử 0/1/2+ hàng và concurrency nếu liên quan:** kiểm tra exception loại nào và transaction rollback khi cần.

Một truy vấn điều tra bản ghi trùng theo email:

```sql
SELECT email, COUNT(*) AS occurrences
FROM customer
GROUP BY email
HAVING COUNT(*) > 1
ORDER BY occurrences DESC, email;
```

Kết quả thống kê cho biết email xuất hiện trên một hàng nhiều lần, nhưng **không** tự phân biệt trùng bất hợp lệ hay nhiều phiên bản hợp lệ. Cần nhìn khóa nghiệp vụ và schema thực tế.

Một truy vấn điều tra nhân số hàng từ `JOIN`:

```sql
SELECT c.id, COUNT(*) AS joined_rows
FROM customer c
JOIN customer_note n ON n.customer_id = c.id
GROUP BY c.id
HAVING COUNT(*) > 1
ORDER BY c.id;
```

Mỗi dòng ở đây thể hiện customer có hơn một hàng join từ note; không chứng minh bảng `customer` chứa duplicate.

## 12. Những cách xử lý sai thường gặp

| Cách xử lý sai | Vì sao có hại | Cách thay thế |
| --- | --- | --- |
| Dùng `queryForObject` cho trường một-nhiều | Nhiều bản ghi hợp lệ gây exception. | Dùng `query`/`queryForList`, map dữ liệu theo quan hệ. |
| Bắt `IncorrectResultSizeDataAccessException` chung rồi trả `null` | Nuốt luôn lỗi >1 và trường hợp 0, che giấu bất biến. | Bắt `EmptyResultDataAccessException` riêng nếu 0 được phép; lỗi >1 phải có chính sách rõ. |
| Thêm `LIMIT 1` không `ORDER BY` | Chọn hàng tùy kế hoạch chạy; che giấu duplicate. | Chỉ chọn top 1 nếu nghiệp vụ đòi hỏi, kèm order/tie-breaker. |
| Thêm `DISTINCT` vào mọi query JOIN lỗi | Có thể xóa thông tin quan hệ thật, không sửa dữ liệu nguồn. | Dùng `EXISTS`, aggregate, sửa join hoặc map collection theo mục đích. |
| Cho rằng `COUNT(*) = 0` nghĩa là không có hàng SQL | Aggregate không group vẫn trả một hàng chứa 0. | Phân biệt cardinality của result set và giá trị đếm trong một hàng. |
| Dùng `String.class` khi SELECT nhiều cột | Một hàng nhưng sai hợp đồng số cột. | Dùng `RowMapper` cho object nhiều thuộc tính. |
| Thấy hai object bằng nhau rồi coi là một hàng | Cardinality đếm hàng SQL, không đếm giá trị distinct sau mapping. | Xác minh ràng buộc hoặc thiết kế aggregate thật. |
| Chỉ check trùng bằng SELECT trước INSERT | Hai transaction song song có thể vượt qua check. | Dùng unique constraint của DB và xử lý race/write conflict. |
| Dùng `@Transactional` mà bắt/nuốt mọi lỗi kết quả | Có nguy cơ commit thao tác đã ghi trước khi phát hiện dữ liệu sai. | Bảo toàn tín hiệu lỗi và rollback policy phù hợp. |
| Ghi toàn bộ tham số truy vấn nhạy cảm vào log | Có thể lộ email, định danh cá nhân hoặc dữ liệu bảo mật. | Ghi tên câu truy vấn, mã lỗi, số hàng, ID an toàn hoặc tham số đã ẩn/mã hóa. |

## 13. Checklist chọn đúng mô hình kết quả

Trước khi viết `queryForObject`, tự trả lời:

1. **Có cơ sở nào bảo đảm nhiều nhất một hàng?** Khóa chính/unique constraint hay chỉ là giả định chưa được DB bảo vệ?
2. **Không có hàng có hợp lệ không?** Nếu có, repository nên dùng `Optional`/nullable contract một cách rõ ràng, thay vì bất ngờ báo lỗi.
3. **Nếu hai hàng xuất hiện thì hệ thống cần làm gì?** Báo lỗi dữ liệu, chuyển sang danh sách, hay chọn bản ghi theo thứ tự nghiệp vụ được chỉ định?
4. **SQL có JOIN/GROUP BY không?** Cardinality sau join/aggregate khác cardinality của bảng gốc.
5. **Đang lấy một cột hay một entity nhiều cột?** Overload `Class<T>` và `RowMapper<T>` có hợp đồng số cột khác nhau.
6. **Có NULL hoặc aggregate không?** Một hàng chứa NULL khác hoàn toàn không có hàng.
7. **Ràng buộc duy nhất có bao phủ tenant, soft-delete, normalization và concurrency không?**
8. **Exception có đang được bắt tại đúng tầng không?** Đặc biệt khi truy vấn nằm trong transaction có thao tác ghi trước đó.

### Ghi nhớ

- **`queryForObject` yêu cầu đúng một hàng SQL**; nó không phải API “lấy bản ghi đầu tiên”.
- **0 hàng** thường ném `EmptyResultDataAccessException`, là subclass của `IncorrectResultSizeDataAccessException`; **trên 1 hàng** ném `IncorrectResultSizeDataAccessException`.
- `getExpectedSize()`/`getActualSize()` hỗ trợ chẩn đoán, nhưng không thay thế việc xem SQL, tham số và schema.
- `JOIN` có thể nhân số hàng ngay cả khi bảng cha có khóa chính duy nhất. Giá trị trùng trong cột cũng không chứng minh duplicate của bảng cha.
- Dùng `query` cho danh sách; dùng `queryForObject` cho exactly one; dùng `Optional` có chủ đích cho zero-or-one và giữ lỗi >1.
- **`LIMIT 1` chỉ đúng khi nghiệp vụ yêu cầu lựa chọn có thứ tự**, không phải mẹo sửa dữ liệu vốn phải duy nhất.
- Nếu cần duy nhất thật sự, hãy thiết kế **unique constraint ở database**, không chỉ tin vào kiểm tra trong Java.

### Tài liệu tham khảo

- Spring Framework — `JdbcTemplate`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring — `IncorrectResultSizeDataAccessException`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/IncorrectResultSizeDataAccessException.html
- Spring — `EmptyResultDataAccessException`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/EmptyResultDataAccessException.html
- Spring — `DataAccessUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/support/DataAccessUtils.html
- Spring — JDBC querying: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html

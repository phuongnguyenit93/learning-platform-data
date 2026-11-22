# Truy vấn giá trị đơn bằng queryForObject() trong Spring JDBC

## 1. Mục tiêu bài học

Khi ứng dụng Spring cần lấy **chính xác một hàng** từ cơ sở dữ liệu quan hệ, `JdbcTemplate.queryForObject()` là API JDBC ngắn gọn nhưng có **hợp đồng số lượng kết quả chặt chẽ**. Với cách gọi trả về một giá trị đơn giản như `Long`, `String` hoặc `BigDecimal`, câu SQL còn phải tạo ra **chính xác một cột**. Khi cần một đối tượng từ nhiều cột, dùng phiên bản nhận `RowMapper<T>`.

Bài này giúp bạn:
- Nhận ra khi nào `queryForObject()` phù hợp hơn `query()`, `queryForList()` hoặc truy vấn nhiều hàng.
- Dùng các overload nhận `Class<T>` và `RowMapper<T>` đúng cách, có bind tham số an toàn.
- Hiểu khác biệt giữa **0 hàng**, **1 hàng có SQL NULL**, **1 hàng có giá trị**, **nhiều hàng**, **nhiều cột** và **lỗi database**.
- Xử lý `EmptyResultDataAccessException`, `IncorrectResultSizeDataAccessException` và `IncorrectResultSetColumnCountException` mà không che giấu lỗi.
- Viết code Java 17+/Spring Boot chạy được, tự kiểm chứng output và xây dựng test cho hợp đồng truy vấn.
- Thiết kế repository và service thể hiện rõ tra cứu “bắt buộc có” khác tra cứu “có thể không tồn tại”.

**Bối cảnh:** Spring Framework 6.x, `spring-jdbc` và `JdbcTemplate` theo lập trình JDBC blocking. Các ví dụ Spring Boot dùng Java 17+ và không cần JPA. Đây là bài về **truy vấn giá trị đơn bằng `queryForObject()`**, không phải hướng dẫn tổng quan về mọi hình thức SQL.

## 2. “Một giá trị” có hai cấp độ

Tên `queryForObject()` đôi khi gây hiểu lầm rằng SQL nào cũng lấy được “một thứ”. Thực tế phải hỏi hai câu:

1. **SQL trả bao nhiêu hàng?** API `queryForObject()` kỳ vọng **đúng một hàng**, bất kể là scalar hay object.
2. **SQL trả bao nhiêu cột?** Với overload `Class<T> requiredType`, cần **một cột**. Với overload `RowMapper<T>`, mapper có thể đọc **nhiều cột** của hàng đó để tạo object.

Ví dụ:

```sql
-- Đúng một hàng, một cột: phù hợp queryForObject(sql, Long.class)
SELECT COUNT(*) FROM customers;

-- Tối đa một hàng, một cột nếu id là PRIMARY KEY:
SELECT display_name FROM customers WHERE id = ?;

-- Tối đa một hàng, nhiều cột nếu id là PRIMARY KEY:
SELECT id, display_name, email FROM customers WHERE id = ?;

-- Có thể nhiều hàng: KHÔNG hợp đồng của queryForObject nếu không bảo đảm đúng một.
SELECT display_name FROM customers WHERE active = TRUE;
```

| Kết quả SQL | Overload `Class<T>` | Overload `RowMapper<T>` |
|---|---|---|
| 0 hàng | Ném `EmptyResultDataAccessException` | Ném `EmptyResultDataAccessException` |
| 1 hàng, 1 cột, giá trị không NULL | Trả giá trị đã chuyển sang kiểu T (nếu tương thích) | Trả object do mapper tạo |
| 1 hàng, 1 cột, SQL NULL | Có thể trả Java `null` | Do `RowMapper` quyết định |
| 1 hàng, nhiều cột | Ném `IncorrectResultSetColumnCountException` | Hợp lệ: mapper đọc cột cần dùng |
| Nhiều hơn 1 hàng | Ném `IncorrectResultSizeDataAccessException` | Ném `IncorrectResultSizeDataAccessException` |
| SQL sai, mất kết nối, vi phạm kiểu chuyển đổi... | Exception truy cập dữ liệu | Exception truy cập dữ liệu hoặc exception mapper |

`EmptyResultDataAccessException` là một nhánh của `IncorrectResultSizeDataAccessException` dành cho trường hợp **mong 1 nhưng nhận 0**. Không trộn “trả Java `null`” với “SQL không trả hàng”: chúng có cơ chế và ý nghĩa khác nhau.

## 3. Cơ chế hoạt động bên trong

`JdbcTemplate` dùng JDBC, nhưng che bớt mã lặp:

```text
Repository / Service
       |
       | jdbcTemplate.queryForObject(sql, requiredType, args...)
       v
JdbcTemplate
       |
       +-- lấy Connection qua DataSource theo context transaction
       +-- tạo PreparedStatement khi có bind arguments
       +-- bind '?' vào các giá trị, execute SQL
       +-- đọc tập kết quả
       |     +-- 0 row  → lỗi kích thước kết quả thiếu
       |     +-- 1 row  → map một giá trị/object
       |     +-- >1 row → lỗi kích thước kết quả dư
       +-- dọn tài nguyên JDBC do template sở hữu
       |
       v
Trả T / null, hoặc phát sinh DataAccessException
```

Trong overload nhận `Class<T>`, Spring dùng mapper kiểu **một cột** để lấy/chuyển giá trị JDBC sang kiểu Java phù hợp. Trong overload nhận `RowMapper<T>`, mapper được gọi trên từng row để dựng đối tượng; kết quả cuối cùng vẫn phải có đúng một row.

Các overload có tham số `?` thường dùng prepared statement. Không suy luận mọi overload đều dùng prepared statement: truy vấn SQL tĩnh qua overload không tham số có thể sử dụng JDBC `Statement` theo hợp đồng API.

`JdbcTemplate` quản lý vòng đời JDBC resources trong trường hợp thông thường và chuyển các `SQLException` thành nhánh `DataAccessException` của Spring. Điều này không có nghĩa nó tự biến kết quả thiếu thành `Optional.empty()`. Nếu dùng `queryForObject()`, **cardinality chính là một phần contract**.

## 4. Dùng Class<T> để lấy một giá trị đơn

Đây là dạng dễ đọc nhất cho các kết quả scalar.

### 4.1. Đếm bằng COUNT(*)

```java
// Trong class có field JdbcTemplate jdbc:
Long count = jdbc.queryForObject(
    "SELECT COUNT(*) FROM customers",
    Long.class
);
```

Vì `COUNT(*)` không có `GROUP BY` trả **một hàng** kể cả khi bảng trống, `queryForObject()` phù hợp. Giá trị khi không có hàng dữ liệu là **0**, không phải `null` hoặc `EmptyResultDataAccessException`.

Chọn `Long` cho count lớn để tránh giả định giá trị luôn nằm trong phạm vi `int`. Mapping của driver có thể hỗ trợ nhiều kiểu số, nhưng nếu cơ sở dữ liệu lớn, `Long` thường là lựa chọn an toàn hơn `Integer`.

### 4.2. Tra cứu một cột theo khóa duy nhất

```java
String displayName = jdbc.queryForObject(
    "SELECT display_name FROM customers WHERE id = ?",
    String.class,
    customerId
);
```

- `?` được bind từ `customerId`; không nối input thành SQL.
- Nếu `id` là khóa chính, tối đa một hàng khớp.
- Nếu không có ID đó: **ném `EmptyResultDataAccessException`**.
- Nếu cột được phép NULL và một hàng tồn tại: giá trị Java có thể là `null`.
- Nếu SQL trả hai cột trong overload `String.class`, đó là lỗi số cột, kể cả hai cột đều là String.

Một khóa chính bảo đảm **không có hơn một hàng**. Nó không bảo đảm **có đúng một hàng**. Với ID truyền từ người dùng, trường hợp 0 hàng vẫn phải được xử lý.

### 4.3. Các kiểu scalar phổ biến

```java
// Các method minh họa trong repository có field JdbcTemplate jdbc.
Long totalOrders = jdbc.queryForObject(
    "SELECT COUNT(*) FROM orders",
    Long.class
);

java.math.BigDecimal maxPrice = jdbc.queryForObject(
    "SELECT MAX(price) FROM products",
    java.math.BigDecimal.class
);

Boolean enabled = jdbc.queryForObject(
    "SELECT enabled FROM feature_flags WHERE flag_key = ?",
    Boolean.class,
    "new_checkout"
);
```

Lưu ý `MAX(price)` trên tập không có hàng có thể trả **một hàng với SQL NULL**. `maxPrice == null` trong ví dụ này không chứng minh SQL trả 0 hàng. Với tiền, thường dùng `BigDecimal` để giữ chính xác thập phân; tránh tự suy luận loại JDBC chính xác mà chưa kiểm tra schema/dialect.

Nếu nghiệp vụ quy định “không có sản phẩm thì giá tối đa mặc định 0”, có thể viết:

```sql
SELECT COALESCE(MAX(price), 0) FROM products;
```

Nhưng chỉ dùng `COALESCE` khi **0 đúng là ý nghĩa nghiệp vụ**, không phải để xóa bỏ thông tin “không có dữ liệu”.

## 5. Dùng RowMapper<T> để lấy một object từ nhiều cột

Ví dụ truy vấn một khách hàng có `id`, `display_name`, `email`. Nếu dùng `queryForObject(sql, Customer.class)` mà không có cơ chế mapping riêng phù hợp, `Class<T>` không phải lệnh tự động “biến nhiều cột thành entity”. Overload đó là **scalar one-column mapping**. Hãy cung cấp `RowMapper<Customer>`:

```java
// Customer.java
package example.jdbc;

public record Customer(long id, String name, String email) {}
```

```java
// CustomerJdbcRepository.java
package example.jdbc;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerJdbcRepository {

    private static final RowMapper<Customer> CUSTOMER_MAPPER =
        (rs, rowNum) -> new Customer(
            rs.getLong("id"),
            rs.getString("display_name"),
            rs.getString("email")
        );

    private final JdbcTemplate jdbc;

    public CustomerJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Customer requireById(long id) {
        return jdbc.queryForObject("""
                SELECT id, display_name, email
                FROM customers
                WHERE id = ?
                """, CUSTOMER_MAPPER, id);
    }
}
```

**Kết quả:**
- Đúng một hàng → mapper tạo `Customer` và method trả object.
- Không hàng → `EmptyResultDataAccessException`.
- Nhiều hàng → `IncorrectResultSizeDataAccessException`.
- Cột `email` có SQL NULL → `rs.getString("email")` trả Java `null`, nhưng **hàng vẫn tồn tại**.

`RowMapper` nên ánh xạ DTO/record tách khỏi `ResultSet`, không trả `ResultSet` ra ngoài method. Nếu mapper trả chính Java `null` cho một row, `queryForObject()` có thể trả `null`; vì vậy **đừng dùng `result == null` như phép thử phổ quát “không tìm thấy”**.

Trong Java 17, `record` phù hợp với DTO bất biến. Nếu cần mapping tên cột vào bean hoặc record qua mapper tổng quát, xem `BeanPropertyRowMapper` hoặc `DataClassRowMapper` theo Spring version, nhưng với ví dụ đơn giản, mapper tường minh giúp kiểm soát alias và nullability rõ nhất.

## 6. Hợp đồng đúng một hàng: 0, 1, nhiều hơn 1

### 6.1. Không có hàng là exception, không phải null

```java
try {
    String name = jdbc.queryForObject(
        "SELECT display_name FROM customers WHERE id = ?",
        String.class,
        999L
    );
    System.out.println(name);
} catch (org.springframework.dao.EmptyResultDataAccessException ex) {
    System.out.println("Không tìm thấy khách hàng");
}
```

Đây là snippet **trong method có field `jdbc`**, không phải một file Java độc lập. Chỉ bắt `EmptyResultDataAccessException` khi **không tìm thấy** thực sự là tình huống mong đợi.

Nếu use case bắt buộc phải có khách hàng, có thể chuyển thành lỗi miền. Nếu method dùng để kiểm tra khách hàng có thể tồn tại hoặc không, cân nhắc repository trả `Optional<Customer>` (cách triển khai ở phần sau). Không bắt toàn bộ `DataAccessException` để trả “không thấy”.

### 6.2. Nhiều hàng là vi phạm cardinality

```java
String name = jdbc.queryForObject(
    "SELECT display_name FROM customers WHERE active = ?",
    String.class,
    true
);
```

Nếu có nhiều khách hàng active, method sẽ ném `IncorrectResultSizeDataAccessException`. Điều này đúng theo contract: yêu cầu **một khách hàng** nhưng SQL lại tìm **mọi khách hàng active**.

Cách sửa phải dựa vào nghiệp vụ:
- Muốn **danh sách khách hàng active** → dùng `jdbc.query(...)`/`queryForList(...)` trả 0..N row.
- Muốn **khách hàng theo khóa duy nhất** → thêm điều kiện khóa và unique constraint thích hợp.
- Muốn **khách hàng mới nhất** → dùng `ORDER BY created_at DESC, id DESC LIMIT 1`, **chấp nhận có thể không có hàng**; khóa phụ `id` giúp thứ tự xác định.
- Muốn **xác minh duy nhất** → duy trì `PRIMARY KEY`/`UNIQUE` ở database và để duplicate là lỗi cần xử lý, **không che bằng `LIMIT 1`**.

### 6.3. Một hàng nhưng nhiều cột là lỗi của scalar overload

```java
// SAI: String.class yêu cầu một cột, SQL trả hai cột.
String invalid = jdbc.queryForObject(
    "SELECT display_name, email FROM customers WHERE id = ?",
    String.class,
    1L
);
```

Khi truy vấn trả đúng một hàng nhưng hai cột, overload `Class<T>` ném `IncorrectResultSetColumnCountException`. Nếu cần cả hai cột, dùng `RowMapper<Customer>` hoặc DTO projection; nếu chỉ cần tên, chọn **duy nhất `display_name`**.

## 7. SQL NULL khác với 0 hàng: bẫy quan trọng nhất

Hãy tưởng tượng dữ liệu:

| id | display_name | nickname |
|---:|---|---|
| 1 | An | NULL |
| 2 | Bình | Bi |

Truy vấn A:

```sql
SELECT nickname FROM customers WHERE id = 1;
```

Kết quả: **một hàng, một cột chứa SQL NULL**. `queryForObject(..., String.class, 1L)` có thể trả Java `null`.

Truy vấn B:

```sql
SELECT nickname FROM customers WHERE id = 999;
```

Kết quả: **không hàng nào**. `queryForObject(...)` ném `EmptyResultDataAccessException`.

Truy vấn C:

```sql
SELECT COUNT(*) FROM customers WHERE id = 999;
```

Kết quả: **một hàng**, giá trị `0`.

Truy vấn D:

```sql
SELECT SUM(amount) FROM payments WHERE customer_id = 999;
```

Nếu không có payment khớp, SQL aggregate `SUM` (không `GROUP BY`) thường trả **một hàng với NULL**, khác `COUNT(*)` trả `0`.

**Bảng phân biệt:**

| Tình huống | Số hàng | Nội dung một cột | Kết quả từ `queryForObject(..., Class<T>)` |
|---|---:|---|---|
| Không có bản ghi theo khóa | 0 | Không có | `EmptyResultDataAccessException` |
| Có bản ghi, cột nullable là NULL | 1 | SQL NULL | Java `null` có thể được trả |
| Đếm tập rỗng | 1 | 0 | Số 0 |
| Aggregate SUM/MAX tập rỗng | 1 | SQL NULL | Java `null` |
| SQL sai/lỗi connection | Không biết đáng tin | Không xác định | `DataAccessException` thích hợp |

Nếu contract thật sự cần phân biệt “không có hàng” với “có hàng chứa NULL”, hãy trả object có **khóa không NULL** cùng trường nullable, hoặc định nghĩa một kiểu kết quả rõ ràng. Chỉ `Optional.ofNullable(scalarValue)` không giữ được thông tin này.

### Null và kiểu nguyên thủy Java

`Long.class` trả về `Long` nullable. Nếu viết:

```java
long count = jdbc.queryForObject(
    "SELECT SUM(amount_cents) FROM orders",
    Long.class
);
```

Khi query trả SQL NULL, auto-unboxing có thể gây `NullPointerException`. Nếu muốn xử lý absent aggregate:

```java
Long sum = jdbc.queryForObject(
    "SELECT SUM(amount_cents) FROM orders",
    Long.class
);
long total = (sum == null) ? 0L : sum;
```

Chỉ áp dụng default 0 sau khi đã quyết định ý nghĩa nghiệp vụ. Với tiền có phần thập phân, ưu tiên kiểu `BigDecimal` thay vì chuyển sang `double`.

## 8. Tra cứu “có thể không tồn tại” bằng Optional

`queryForObject()` ưu tiên contract **đúng một hàng**. Muốn repository công bố 0..1, có vài hướng hợp lệ:

### 8.1. Bắt riêng EmptyResultDataAccessException

```java
// Method minh họa trong repository có field JdbcTemplate jdbc,
// và RowMapper<Customer> CUSTOMER_MAPPER luôn tạo non-null Customer.
public java.util.Optional<Customer> findById(long id) {
    try {
        Customer customer = jdbc.queryForObject(
            "SELECT id, display_name, email FROM customers WHERE id = ?",
            CUSTOMER_MAPPER,
            id
        );
        return java.util.Optional.of(customer);
    } catch (org.springframework.dao.EmptyResultDataAccessException ex) {
        return java.util.Optional.empty();
    }
}
```

Cách này làm rõ **không tìm thấy** là trường hợp bình thường. Những lỗi SQL, connection hoặc duplicate vẫn được truyền đi và phải được xử lý riêng.

`Optional.of(customer)` ở đây hợp lý vì mapper cụ thể luôn tạo object; nếu mapper của bạn được phép trả null thì phải định nghĩa contract rõ, không sử dụng tùy tiện `Optional.ofNullable(...)` để gộp trường hợp không có row với row null.

### 8.2. Dùng query() rồi quyết định cardinality

```java
// Method minh họa trong repository có CUSTOMER_MAPPER.
public java.util.Optional<Customer> findByIdViaList(long id) {
    java.util.List<Customer> rows = jdbc.query(
        "SELECT id, display_name, email FROM customers WHERE id = ?",
        CUSTOMER_MAPPER,
        id
    );
    if (rows.isEmpty()) {
        return java.util.Optional.empty();
    }
    if (rows.size() != 1) {
        throw new org.springframework.dao.IncorrectResultSizeDataAccessException(
            1, rows.size());
    }
    return java.util.Optional.of(rows.get(0));
}
```

Đây là cơ chế rõ về số lượng nhưng cần code bổ sung và không phù hợp khi SQL có thể trả hàng triệu row: phải giới hạn hoặc xem lại truy vấn. Với khóa duy nhất, database bảo đảm tối đa một row nên ứng dụng không cần tải tập lớn.

### 8.3. JdbcClient khi dùng Spring Framework 6.1+

`JdbcClient` có cú pháp fluent trên nền JDBC:

```java
// Method minh họa; JdbcClient được inject sẵn.
public java.util.Optional<Customer> findByIdViaClient(long id) {
    return jdbcClient.sql("""
            SELECT id, display_name, email FROM customers WHERE id = :id
            """)
        .param("id", id)
        .query(CUSTOMER_MAPPER)
        .optional();
}
```

`optional()` thể hiện 0..1, `single()` thể hiện đúng một, `list()` thể hiện 0..N. Các phương thức này thuộc `JdbcClient`, **không phải overload của `JdbcTemplate.queryForObject()`**. Chọn API theo contract và phiên bản Spring đang dùng; không cần đổi sang `JdbcClient` chỉ để “tránh ngoại lệ” nếu code hiện tại đã rõ ràng.

## 9. PreparedStatement và bind tham số

Không được nối input thành SQL:

```java
// SAI: tiềm ẩn SQL injection, escaping sai, khó reuse plan.
String sql = "SELECT email FROM customers WHERE display_name = '"
    + userInput + "'";
String email = jdbc.queryForObject(sql, String.class);
```

Đúng:

```java
String email = jdbc.queryForObject(
    "SELECT email FROM customers WHERE display_name = ?",
    String.class,
    userInput
);
```

`?` là vị trí bind; JDBC driver xử lý giá trị tương ứng, dữ liệu của người dùng không bị diễn giải như SQL syntax. Nếu có nhiều tham số, thứ tự truyền phải khớp `?`:

```java
Long count = jdbc.queryForObject("""
        SELECT COUNT(*)
        FROM customers
        WHERE active = ? AND display_name LIKE ?
        """,
    Long.class,
    true,
    prefix + "%"
);
```

`LIKE` và ký tự wildcard `%`/`_` có ý nghĩa tìm kiếm riêng. Nếu `prefix` là text người dùng và bạn muốn khớp literal (không muốn wildcard do người dùng nhập), cần escape wildcard theo SQL dialect/`ESCAPE` clause; bind tham số chỉ chống SQL injection, **không tự thay đổi semantics của LIKE**.

Tên bảng/cột và tên biểu thức `ORDER BY` không thể bind như dữ liệu scalar; nếu cần cho người dùng chọn sort, ánh xạ giá trị lựa chọn vào danh sách tên cột được phép thay vì chèn trực tiếp input.

### Dùng NamedParameterJdbcTemplate

Nếu nhiều tham số dễ nhầm thứ tự, `NamedParameterJdbcTemplate` cung cấp overload cùng nghĩa:

```java
// Method trong class có field NamedParameterJdbcTemplate namedJdbc.
public String requireEmail(long id) {
    return namedJdbc.queryForObject(
        "SELECT email FROM customers WHERE id = :id",
        java.util.Map.of("id", id),
        String.class
    );
}
```

Nó vẫn tuân theo “đúng một hàng, một cột” và có thể trả null nếu email trong DB là NULL. Named parameters không làm query tự động “optional” và không ngăn trường hợp nhiều row nếu SQL không đủ điều kiện duy nhất.

## 10. Bài demo Spring Boot chạy được với H2

Phần này cung cấp **một chương trình Spring Boot hoàn chỉnh** để quan sát chính xác các trạng thái: một giá trị count, một object, 0 row, nhiều row và SQL NULL. Chọn H2 embedded để chạy nhanh trên máy học; khi triển khai thực tế hãy kiểm thử lại với DB/driver sản phẩm.

### 10.1. Cấu trúc

```text
query-for-object-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jdbc/QueryForObjectDemoApplication.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'query-for-object-demo'
```

`build.gradle` (ví dụ Spring Boot 3.3.5, Java 17):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:querydemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    nickname VARCHAR(100),
    active BOOLEAN NOT NULL
);
```

`src/main/resources/data.sql`:

```sql
INSERT INTO customers (id, display_name, nickname, active)
VALUES (1, 'An', NULL, TRUE);

INSERT INTO customers (id, display_name, nickname, active)
VALUES (2, 'Binh', 'Bi', TRUE);

INSERT INTO customers (id, display_name, nickname, active)
VALUES (3, 'Chi', NULL, FALSE);
```

`src/main/java/example/jdbc/QueryForObjectDemoApplication.java`:

```java
package example.jdbc;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

@SpringBootApplication
public class QueryForObjectDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(QueryForObjectDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(JdbcTemplate jdbc) {
        return args -> {
            Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM customers",
                Long.class);
            System.out.println("count=" + count);

            RowMapper<Customer> mapper = (rs, rowNum) ->
                new Customer(
                    rs.getLong("id"),
                    rs.getString("display_name"));

            Customer customer = jdbc.queryForObject(
                "SELECT id, display_name FROM customers WHERE id = ?",
                mapper,
                1L);
            System.out.println("found=" + customer.name());

            try {
                jdbc.queryForObject(
                    "SELECT id, display_name FROM customers WHERE id = ?",
                    mapper,
                    999L);
            } catch (EmptyResultDataAccessException ex) {
                System.out.println("notFound=true");
            }

            try {
                jdbc.queryForObject(
                    "SELECT id, display_name FROM customers WHERE active = ?",
                    mapper,
                    true);
            } catch (IncorrectResultSizeDataAccessException ex) {
                System.out.println("notUnique=true");
            }

            String nickname = jdbc.queryForObject(
                "SELECT nickname FROM customers WHERE id = ?",
                String.class,
                1L);
            System.out.println("nicknameIsNull=" + (nickname == null));
        };
    }
}

record Customer(long id, String name) {}
```

**Chạy:** sử dụng Gradle 8.x tương thích với bản Spring Boot mẫu, rồi ở thư mục gốc dự án:

```bash
gradle bootRun
```

Hoặc dùng Gradle Wrapper của dự án nếu đã cấu hình: `./gradlew bootRun` trên Unix/macOS, `gradlew.bat bootRun` trên Windows.

Năm dòng **do chương trình in ra**, theo đúng thứ tự (Spring Boot/Gradle có thể in thêm startup/build log):

```text
count=3
found=An
notFound=true
notUnique=true
nicknameIsNull=true
```

Giải thích:
1. `COUNT(*)` sinh đúng một row, cột đếm = 3.
2. Query theo id=1 có một row chứa hai cột; `RowMapper` tạo record `Customer(1, "An")`.
3. id=999 không có row, nên `EmptyResultDataAccessException` được bắt và in `notFound=true`.
4. `active=TRUE` khớp An và Binh (hai row), nên `queryForObject` báo dư kết quả.
5. id=1 tồn tại nhưng `nickname` là SQL NULL; scalar query trả Java null, không ném `EmptyResultDataAccessException`.

Bài demo dùng dữ liệu cố định và H2 để dễ chạy. Nó **không** chứng minh hành vi của mọi PostgreSQL/MySQL driver hay mọi schema thực tế. Khi chuyển DB, kiểm thử kiểu dữ liệu, SQL dialect, index và exception translation trên môi trường gần production.

## 11. Thiết kế repository và service: ai quyết định “not found”?

Hãy tách rõ tầng dữ liệu khỏi nghiệp vụ. Repository có thể đặt tên `requireById` để nói “chính xác một row”, hoặc `findById` trả `Optional` nếu absence được cho phép. Service quyết định absence có được chấp nhận trong use case hay không.

Ví dụ một service bắt buộc tìm được khách hàng:

```java
// CustomerNotFoundException.java
package example.jdbc;

public final class CustomerNotFoundException extends RuntimeException {
    public CustomerNotFoundException(long id) {
        super("Customer not found: " + id);
    }
}
```

```java
// CustomerLookupService.java
package example.jdbc;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.stereotype.Service;

@Service
public class CustomerLookupService {
    private final CustomerJdbcRepository repository;

    public CustomerLookupService(CustomerJdbcRepository repository) {
        this.repository = repository;
    }

    public Customer getRequired(long id) {
        try {
            return repository.requireById(id);
        } catch (EmptyResultDataAccessException ex) {
            throw new CustomerNotFoundException(id);
        }
    }
}
```

Nếu method `CustomerJdbcRepository.requireById` là query theo khóa chính, có thể chuyển riêng lỗi 0 row thành lỗi miền. **Không** bắt `IncorrectResultSizeDataAccessException` chung để chuyển hết thành “không có khách hàng”, vì trường hợp >1 row là dấu hiệu query/constraint sai. Nếu cần bắt cả hai trong một khối, nhớ `EmptyResultDataAccessException` kế thừa `IncorrectResultSizeDataAccessException` nên đặt nhánh cụ thể trước.

Tầng HTTP sau đó có thể chuyển `CustomerNotFoundException` thành 404 (theo API policy). Không ép repository trả `ResponseEntity` vì JDBC repository có thể được gọi từ batch, message consumer hoặc service khác ngoài HTTP.

## 12. Cách xử lý lỗi cần giữ đúng ý nghĩa

| Tình huống | Hành vi thường gặp | Hướng giải quyết |
|---|---|---|
| Không có hàng, query bắt buộc đúng một | `EmptyResultDataAccessException` | Quyết định absence ở use case, có thể chuyển domain NotFound |
| Nhiều hơn một hàng | `IncorrectResultSizeDataAccessException` | Sửa query hoặc unique constraint, không lấy hàng đầu tùy tiện |
| Một hàng nhiều cột với `Class<T>` | `IncorrectResultSetColumnCountException` | Chỉ SELECT một cột hoặc dùng RowMapper |
| Một hàng SQL NULL | Java `null` ở scalar overload | Quy định nullability, dùng COALESCE nếu có ý nghĩa |
| SQL syntax sai hoặc không tồn tại cột | Nhóm `DataAccessException` về grammar | Sửa SQL/migration/mapping, không chuyển thành not-found |
| DB mất kết nối/pool timeout | Nhóm lỗi resource/data access | Log/monitor, response 5xx tùy policy, không trả empty |
| Trùng key khi INSERT | Constraint exception | Xử lý conflict nghiệp vụ, không liên quan 0 row của SELECT |
| Mapper đọc sai kiểu hoặc thiếu cột | Mapping/conversion/runtime error | Sửa mapper, alias, schema; test integration |

**Mẫu sai:**

```java
// SAI: mọi lỗi đều bị báo là khách hàng không tồn tại.
try {
    return jdbc.queryForObject(sql, CUSTOMER_MAPPER, id);
} catch (Exception ex) {
    return null;
}
```

Đây là đoạn minh họa trong class đã có `sql`, `jdbc`, `CUSTOMER_MAPPER`; không phải mã độc lập. Nó che SQL lỗi, mapping lỗi, DB outage và dữ liệu trùng thành Java null, làm hệ thống khó vận hành.

**Mẫu xử lý đúng:** chỉ bắt lỗi được phép chuyển thành một outcome nghiệp vụ, bảo toàn những exception khác. Thông tin lỗi kỹ thuật chi tiết nên được ghi trong log/trace nội bộ nhưng không lộ URL database, SQL chứa dữ liệu nhạy cảm, credentials hoặc stack trace ra API.

### Retry có giải quyết thiếu row hoặc duplicate row không?

Thông thường **không**:
- 0 row theo ID không tự biến thành 1 row nếu retry; chỉ retry khi có lý do về eventual consistency và policy rõ.
- Nhiều row vì thiếu unique constraint không nên retry vô hạn; cần sửa invariant dữ liệu.
- Lỗi mất connection/deadlock có thể có tính tạm thời, nhưng retry cần giới hạn, backoff, timeout và kiểm tra idempotency. Không retry mọi `DataAccessException`.
- Với write, timeout có thể đến sau khi DB đã thực thi thay đổi; việc retry không phải phần mặc định của `queryForObject()`.

## 13. Thời điểm không nên dùng queryForObject()

### 13.1. Kết quả 0..N

Truy vấn danh sách dùng `jdbc.query(sql, rowMapper, args...)`:

```java
// Method minh họa trong repository có CUSTOMER_MAPPER.
public java.util.List<Customer> findActive() {
    return jdbc.query("""
            SELECT id, display_name, email
            FROM customers
            WHERE active = ?
            ORDER BY id
            """, CUSTOMER_MAPPER, true);
}
```

Không có row → danh sách rỗng. N row → danh sách có N record. Nếu bảng lớn, dùng phân trang/`LIMIT`, thứ tự xác định và DTO projection, tránh tải toàn bộ kết quả vào heap.

### 13.2. Chỉ cần biết bản ghi có tồn tại

`COUNT(*)` có thể dùng `queryForObject`, nhưng nếu chỉ cần boolean tồn tại, một câu `SELECT EXISTS(...)` (tùy dialect) có thể thể hiện ý định tốt hơn:

```java
Boolean exists = jdbc.queryForObject("""
        SELECT EXISTS (
            SELECT 1 FROM customers WHERE id = ?
        )
        """, Boolean.class, customerId);
```

Truy vấn `EXISTS` trong hệ DB hỗ trợ sẽ trả **một hàng/một cột boolean**, bất kể customer có tồn tại hay không. Không xem kết quả `false` là thiếu row.

### 13.3. Muốn lấy “row đầu tiên” trong tập kết quả

`queryForObject()` kiểm tra chính xác một row. `ORDER BY` tự nó **không** giới hạn số row, nên nếu cần duy nhất một bản ghi mới nhất, áp dụng `LIMIT 1` (hoặc cơ chế tương đương theo DB) với thứ tự xác định:

```sql
SELECT id, display_name
FROM customers
WHERE active = TRUE
ORDER BY id DESC
LIMIT 1;
```

Truy vấn này có thể trả 0 hoặc 1 row; nếu 0 là hợp lệ, vẫn phải dùng API optional hoặc xử lý `EmptyResultDataAccessException` rõ ràng. Đừng thêm `LIMIT 1` để “sửa” truy vấn theo khóa lẽ ra phải unique: làm vậy có thể che lỗi dữ liệu.

### 13.4. Muốn map nhiều cột vào một Map

Nếu cần nhiều cột mà không có DTO, `queryForMap` là API có contract một hàng và map tên cột–giá trị; tuy nhiên DTO/RowMapper thường cung cấp type safety và contract rõ hơn. `queryForObject(sql, Class<T>)` **không** tự map nhiều cột thành `Map` hoặc entity.

### 13.5. Muốn truy vấn bất đồng bộ/reactive

`JdbcTemplate` là blocking JDBC API. Bọc nó trong `CompletableFuture` hoặc `Mono.fromCallable` không biến driver thành non-blocking. Nếu ứng dụng thật sự sử dụng R2DBC, `DatabaseClient.one()` là API khác với semantics riêng. Không dùng những API reactive để bỏ qua vấn đề cardinality của JDBC.

## 14. Kiểm thử chủ đề này một cách có ý nghĩa

Một bộ test tốt bao phủ **cả số row lẫn số cột**:

| Fixture/truy vấn | Expected |
|---|---|
| `SELECT COUNT(*)` trên bảng trống | Long `0`, không có exception |
| `SELECT name WHERE id = 1` có một hàng | Tên khách hàng |
| `SELECT name WHERE id = 999` | `EmptyResultDataAccessException` |
| `SELECT name WHERE active = TRUE` có hai hàng | `IncorrectResultSizeDataAccessException` |
| `SELECT name, email WHERE id = 1` với `String.class` | `IncorrectResultSetColumnCountException` |
| `SELECT nickname WHERE id = 1` với SQL NULL | Giá trị Java null |
| `SELECT id, name WHERE id = 1` với `RowMapper<Customer>` | Một `Customer` có đủ thuộc tính |
| SQL sai tên cột hoặc database ngắt kết nối | Lỗi kỹ thuật, không chuyển thành Optional.empty() |
| Parameter chứa dấu nháy hoặc chuỗi giống SQL | Vẫn được bind như dữ liệu; không đổi cấu trúc SQL |
| Method `findById()` với ID không có | `Optional.empty()`, nếu contract đã công bố 0..1 |

### JUnit test trong dự án Spring

Một ví dụ ngắn với JUnit 5, Spring Boot và database fixture đã tạo:

```java
// Snippet test trong class có JdbcTemplate jdbc, schema/fixture phù hợp.
@Test
void missingRowThrowsEmptyResult() {
    assertThatThrownBy(() ->
        jdbc.queryForObject(
            "SELECT display_name FROM customers WHERE id = ?",
            String.class,
            999L))
        .isInstanceOf(EmptyResultDataAccessException.class);
}
```

Cần import `org.junit.jupiter.api.Test`, `org.assertj.core.api.Assertions.assertThatThrownBy`, `EmptyResultDataAccessException` và khởi tạo/inject `jdbc` trong test. Đây là **test method minh họa**, không phải một file có thể chạy độc lập.

Trong Spring Boot, `@JdbcTest` giúp kiểm thử JDBC slice và quản lý transaction theo test, nhưng đối với hành vi SQL/driver đặc thù (đặc biệt PostgreSQL, MySQL), hãy chạy integration test với DB đúng loại, ví dụ Testcontainers. H2 chỉ chứng minh luồng đơn giản trong demo ở phần 10.

### Một số lỗi thường gặp ngay khi review code

1. **Viết `queryForObject()` để lấy “bất cứ một record nào”** dù SQL có thể trả 0 hoặc nhiều row. Sửa bằng contract 0..1/1/0..N rõ.
2. **Dùng `String.class` cho SQL hai cột** và tưởng Spring sẽ tự chọn cột đầu. Sửa SQL hoặc dùng RowMapper.
3. **Giả định không có dữ liệu trả `null`**; thực tế 0 row sẽ ném EmptyResult, còn SQL NULL có thể trả null.
4. **Đặt `Optional.ofNullable(queryForObject(...))` và tin rằng 0 row trả empty**; thực tế 0 row ném exception, chưa kịp tạo Optional.
5. **Dùng `LIMIT 1` để giấu duplicate** thay vì xây dựng unique constraint hoặc query đúng ngữ cảnh.
6. **Nối trực tiếp user input vào SQL** thay vì bind `?`.
7. **Bắt `Exception` rồi trả giá trị mặc định** khiến SQL lỗi bị xem là “không tìm thấy”.
8. **Unbox Long nullable vào long** khi SQL có thể trả NULL từ `SUM`/`MAX`.
9. **Bỏ qua kiểu và giá trị NULL của JDBC getter** trong RowMapper: `rs.getLong(...)` trả `0` cho SQL NULL, muốn phân biệt phải kiểm tra `rs.wasNull()` hoặc dùng `rs.getObject(..., Long.class)`.
10. **Không kiểm chứng unique constraint** và nghĩ một điều kiện `WHERE external_code = ?` luôn khớp tối đa một row.

## 15. Checklist áp dụng trước khi chọn queryForObject

- [ ] SQL được thiết kế cho **đúng một row**; nếu theo ID/natural key, database có constraint thích hợp.
- [ ] Nếu gọi overload `Class<T>`, SQL chỉ trả **một cột**, và kiểu Java tương thích JDBC type.
- [ ] Nếu SQL có nhiều cột, đã dùng `RowMapper<T>` và biết rõ nullability từng cột.
- [ ] Phân biệt **0 row**, **SQL NULL**, **COUNT(*) = 0**, và **nhiều row**.
- [ ] Nếu 0 row hợp lệ, method trả Optional hoặc xử lý riêng EmptyResult.
- [ ] Nếu >1 row là lỗi, không che bằng LIMIT 1 và có test/constraint bảo vệ.
- [ ] Giá trị đầu vào được bind bằng `?` hoặc named parameters; không ghép raw input vào SQL.
- [ ] Có test cho một hàng, không hàng, nhiều hàng, sai số cột, SQL NULL, và lỗi database.
- [ ] Không nuốt `DataAccessException` hoặc biến lỗi hạ tầng thành “không có dữ liệu”.
- [ ] Repository có contract được thể hiện trong tên hàm/kiểu trả về; service quyết định NotFound theo use case.

## 16. Ghi nhớ

**`JdbcTemplate.queryForObject()` là phép truy vấn đòi hỏi chính xác một hàng.** Dùng `Class<T>` cho kết quả **một cột** (COUNT, tên, số tiền, trạng thái), dùng `RowMapper<T>` khi một hàng chứa **nhiều cột** cần map thành object. Kết quả **0 hàng** là lỗi cardinality thiếu; kết quả **hơn 1 hàng** là lỗi cardinality dư; một hàng chứa **SQL NULL** có thể trả Java null mà không có lỗi “không tìm thấy”. Chọn API theo số lượng kết quả thật sự được phép, giữ tham số được bind và để lỗi kỹ thuật được truyền đúng đến tầng xử lý.

## Tài liệu chính thức

- Spring Framework — Using JDBC Core Classes, mục Querying (SELECT): https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — `JdbcOperations` Javadoc (hợp đồng `queryForObject`): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html
- Spring Framework — `JdbcTemplate` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework — `JdbcClient` API: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — JDBC Exceptions và SQLExceptionTranslator: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html

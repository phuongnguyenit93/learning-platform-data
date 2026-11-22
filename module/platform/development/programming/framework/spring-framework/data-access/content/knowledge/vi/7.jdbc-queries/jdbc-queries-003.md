# Không có hàng với EmptyResultDataAccessException

> **Quy tắc quan trọng:** Trong Spring JDBC, `JdbcTemplate.queryForObject(...)` được dùng khi ứng dụng **kỳ vọng truy vấn trả đúng một hàng**. Nếu kết quả thực tế là **0 hàng**, Spring ném `org.springframework.dao.EmptyResultDataAccessException`. Đây là lỗi **không đáp ứng hợp đồng số lượng kết quả**, không đồng nghĩa câu SQL sai hoặc database hỏng. Nếu "không tìm thấy" là tình huống bình thường của nghiệp vụ, hãy chọn API hoặc cách chuyển đổi phù hợp để biểu diễn sự vắng mặt.

Bài này tập trung vào ý nghĩa của `EmptyResultDataAccessException`, khi nào nó xuất hiện, cách phân biệt với SQL `NULL` hoặc nhiều hàng, và cách viết repository/service Spring JDBC có hợp đồng rõ ràng.

## 1. Khi nào xảy ra lỗi?

Ví dụ một bảng khách hàng:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    nickname VARCHAR(80)
);

INSERT INTO customers (id, name, nickname) VALUES (1, 'Lan', NULL);
INSERT INTO customers (id, name, nickname) VALUES (2, 'Minh', 'M');
```

Câu SQL này không có hàng tương ứng:

```sql
SELECT id, name, nickname
FROM customers
WHERE id = 99;
```

Nếu thực thi bằng `JdbcTemplate.query(...)`, ứng dụng nhận một `List` rỗng. Nhưng nếu dùng `queryForObject(...)` với `RowMapper`, Spring đòi hỏi đúng một hàng và ném `EmptyResultDataAccessException` khi kết quả là 0 hàng:

```java
Customer customer = jdbc.queryForObject(
    "SELECT id, name, nickname FROM customers WHERE id = ?",
    (rs, rowNum) -> new Customer(
        rs.getLong("id"),
        rs.getString("name"),
        rs.getString("nickname")
    ),
    99L
);
```

Ở đây `jdbc` là biến `JdbcTemplate` hoặc `JdbcOperations` được cấu hình trước; `Customer` là kiểu dữ liệu do ứng dụng định nghĩa. Đoạn code là lời gọi bên trong một method, không phải chương trình Java có thể chạy độc lập. Vì không có `id = 99` nên không tạo đối tượng `Customer` nào và exception xuất hiện.

### Điều kiện cụ thể

Một lời gọi "kỳ vọng một kết quả" có ba khả năng chính:

| Số hàng thực tế | `queryForObject(...)` | Ý nghĩa |
| --- | --- | --- |
| **0** | Ném `EmptyResultDataAccessException` | Không có hàng đáp ứng điều kiện, nhưng API yêu cầu một hàng |
| **1** | Ánh xạ hàng và trả object (có trường hợp trả `null`) | Hợp đồng số lượng hàng được đáp ứng |
| **2 trở lên** | Ném `IncorrectResultSizeDataAccessException` | Trả nhiều hơn một hàng khi API yêu cầu đúng một |

`EmptyResultDataAccessException` là subclass của `IncorrectResultSizeDataAccessException`. Vì vậy câu `catch (IncorrectResultSizeDataAccessException ex)` cũng bắt được lỗi 0 hàng, nhưng nếu nghiệp vụ phân biệt *không tìm thấy* và *dữ liệu trùng bất thường*, cần bắt đúng subclass hoặc sử dụng API diễn đạt rõ hơn.

**Không phải mọi truy vấn trả 0 hàng đều ném lỗi này.** Loại lỗi phụ thuộc vào phương thức Spring đang dùng và kỳ vọng của phương thức, không đơn thuần phụ thuộc vào trạng thái database.

## 2. Nguồn gốc và ý nghĩa của exception trong Spring

Tên đầy đủ:

```java
import org.springframework.dao.EmptyResultDataAccessException;
```

Chuỗi kế thừa liên quan trong Spring Framework:

```text
RuntimeException
  └─ DataAccessException
       └─ NonTransientDataAccessException
            └─ DataRetrievalFailureException
                 └─ IncorrectResultSizeDataAccessException
                      └─ EmptyResultDataAccessException
```

Lỗi này là unchecked exception: không bắt buộc khai báo `throws` trên chữ ký method Java. Nó thuộc nhóm lỗi truy cập dữ liệu của Spring, nên tầng service có thể nhận nó mà không cần xử lý `SQLException` thuần.

**Ý nghĩa "non-transient" không có nghĩa bản ghi sẽ vĩnh viễn không bao giờ xuất hiện.** Nó phản ánh loại lỗi không phù hợp để tự động khắc phục chỉ bằng retry lại cùng thao tác trong cùng giả định. Một bản ghi có thể được tạo sau đó; việc có retry hay không là quyết định nghiệp vụ, không phải phản ứng mặc định với `EmptyResultDataAccessException`.

Ngoại lệ có các thông tin về kích thước tập kết quả mong đợi và thực tế, thừa hưởng từ `IncorrectResultSizeDataAccessException`:

```java
try {
    // Gọi một truy vấn queryForObject có thể trả 0 hàng.
} catch (EmptyResultDataAccessException ex) {
    System.out.println(ex.getExpectedSize());
    System.out.println(ex.getActualSize());
}
```

Nếu kết quả mong đợi là 1 và thực tế 0, hai giá trị thường là `1` và `0`. Đây là **mảnh minh họa bên trong method**, không phải code hoàn chỉnh với một biến `jdbc` cụ thể. Đừng phụ thuộc vào chuỗi `ex.getMessage()` để đưa ra quyết định nghiệp vụ: thông điệp exception có thể thay đổi giữa phiên bản Spring.

### JdbcTemplate xử lý thế nào?

Ở mức khái niệm:

1. Spring lấy `Connection` phù hợp từ `DataSource`.
2. Chuẩn bị/thực thi SQL, duyệt `ResultSet` và gọi `RowMapper` khi có hàng.
3. Lựa chọn kết quả theo hợp đồng **một hàng** của `queryForObject`.
4. Nếu không có hàng, ném `EmptyResultDataAccessException`; nếu quá một hàng, ném `IncorrectResultSizeDataAccessException`.
5. Đóng các resource JDBC và trả connection theo chính sách Spring, kể cả khi exception xảy ra.

Do không có hàng, callback `RowMapper` thường **không được gọi lần nào**. Sửa phần ánh xạ từng hàng sẽ không biến truy vấn 0 hàng thành kết quả hợp lệ cho `queryForObject`. Nếu "không tìm thấy" được phép, nên sửa hợp đồng truy vấn hoặc quy tắc xử lý ở tầng repository.

## 3. Phân biệt 0 hàng, SQL NULL và giá trị bằng 0

Đây là nhóm nhầm lẫn phổ biến nhất.

### Trường hợp A: Không có hàng

```sql
SELECT nickname FROM customers WHERE id = 99;
```

Không tìm thấy `id = 99`. Với:

```java
String nickname = jdbc.queryForObject(
    "SELECT nickname FROM customers WHERE id = ?",
    String.class,
    99L
);
```

Spring ném `EmptyResultDataAccessException`, **không trả `null`** chỉ vì SQL không có hàng.

### Trường hợp B: Có một hàng, nhưng cột bằng SQL NULL

```sql
SELECT nickname FROM customers WHERE id = 1;
```

Bảng có khách hàng `id = 1`, còn cột `nickname` là `NULL`. Với:

```java
String nickname = jdbc.queryForObject(
    "SELECT nickname FROM customers WHERE id = ?",
    String.class,
    1L
);
```

Kết quả có thể là Java `null` vì **đã có đúng một hàng nhưng giá trị một cột là SQL `NULL`**. Không có `EmptyResultDataAccessException`. Tương tự, biến thể `queryForObject(sql, RowMapper<T>, args...)` có thể trả `null` nếu `RowMapper` chủ động trả `null` cho hàng hiện hữu.

Nếu phải phân biệt "không có hàng" với "có hàng mà một cột là NULL", **đừng chỉ lưu một giá trị nullable trong biến Java**. Hãy ánh xạ hàng thành object/record chứa ID (và thuộc tính nullable) rồi để việc "có bản ghi hay không" được biểu diễn bằng `Optional<Customer>`. Lúc này `Optional.empty()` biểu diễn thiếu bản ghi, còn `Optional.of(customer)` có thể chứa `customer.nickname() == null`.

### Trường hợp C: Một hàng với giá trị COUNT bằng 0

```sql
SELECT COUNT(*) FROM customers WHERE id = 99;
```

Với dạng `COUNT(*)` **không có `GROUP BY`** như trên, DB trả đúng **một hàng**, giá trị đếm là `0`. Vì vậy:

```java
Long count = jdbc.queryForObject(
    "SELECT COUNT(*) FROM customers WHERE id = ?",
    Long.class,
    99L
);
```

`count` bằng `0L` và không có `EmptyResultDataAccessException`. Đây là khác biệt giữa "không có hàng của dữ liệu nghiệp vụ" và "kết quả của phép tổng hợp đếm số hàng". Nếu thêm `GROUP BY` hoặc `HAVING`, truy vấn tổng hợp có thể không tạo ra nhóm nào, khi đó chính truy vấn tổng hợp lại có thể trả 0 hàng; không áp dụng quy tắc "COUNT luôn trả một hàng" một cách máy móc.

### Bảng so sánh

| SQL hoặc tình huống | Số hàng được trả | `queryForObject` |
| --- | ---: | --- |
| `SELECT name ... WHERE id = 99` | 0 | `EmptyResultDataAccessException` |
| `SELECT nickname ... WHERE id = 1`, giá trị SQL NULL | 1 | Java `null` (biến thể `String.class`) |
| `SELECT COUNT(*) ... WHERE id = 99` | 1 | Giá trị `0` |
| `SELECT name ... WHERE id = 2` | 1 | `"Minh"` |
| `SELECT id FROM customers` với hai khách hàng | 2 | `IncorrectResultSizeDataAccessException` |
| `UPDATE customers SET ... WHERE id = 99` qua `jdbc.update` | Không áp dụng số hàng SELECT | `update` trả `0`, không ném lỗi thiếu kết quả |

## 4. Không phải mọi API Spring JDBC đều kỳ vọng đúng một hàng

| API | Kết quả khi 0 hàng | Nên dùng khi |
| --- | --- | --- |
| `queryForObject(sql, rowMapper, args...)` | Ném `EmptyResultDataAccessException` | Hợp đồng yêu cầu đúng một object/hàng |
| `queryForObject(sql, requiredType, args...)` | Ném `EmptyResultDataAccessException` | Hợp đồng yêu cầu đúng một hàng, **một cột** có kiểu cụ thể |
| `queryForMap(sql, args...)` | Ném `EmptyResultDataAccessException` | Mong muốn đúng một hàng dạng `Map` |
| `query(sql, rowMapper, args...)` | Trả `List<T>` rỗng | Truy vấn cho phép 0..N hàng |
| `queryForList(...)` | Trả danh sách rỗng | Đọc danh sách các hàng/giá trị |
| `update(sql, args...)` | Trả `0` nếu không hàng nào bị cập nhật/xóa | Ghi dữ liệu và kiểm tra số hàng tác động |
| `JdbcClient` `.query(...).optional()` (Spring 6.1+) | `Optional.empty()` | API fluent khi 0 hoặc 1 hàng là hợp lệ |
| `JdbcClient` `.query(...).single()` (Spring 6.1+) | Ném lỗi số lượng kết quả không đúng | API fluent khi bắt buộc đúng một hàng |

Lưu ý với `queryForObject(sql, Class<T>, ...)`: một hàng nhưng **nhiều cột** không khớp yêu cầu một cột, có thể ném `IncorrectResultSetColumnCountException`; cần dùng `RowMapper<T>` để ánh xạ record có nhiều cột. Một hàng có `SQL NULL` trong cột được ánh xạ có thể trả Java `null`, nên ngay cả API "đúng một hàng" cũng không mặc nhiên hứa object không-null.

### Tại sao không sửa bằng LIMIT 1?

```sql
SELECT id, name FROM customers WHERE name = 'Lan' LIMIT 1;
```

`LIMIT 1` có thể ngăn truy vấn trả nhiều hơn một hàng, nhưng **không tạo hàng khi kết quả thực là 0**. Nó cũng che giấu dữ liệu trùng khi tên không duy nhất và không cho biết "bản ghi nào đầu tiên" nếu thiếu `ORDER BY` phù hợp.

Nếu nghiệp vụ yêu cầu duy nhất, hãy thiết kế constraint (ví dụ PRIMARY KEY hoặc UNIQUE phù hợp), truy vấn đúng khóa và xử lý thiếu bản ghi. Nếu nghiệp vụ yêu cầu "lấy bất kỳ/mới nhất một hàng", cần nêu rõ tiêu chí sắp xếp và quy tắc fallback.

## 5. Ba chiến lược xử lý "không tìm thấy"

### Chiến lược 1: Không tìm thấy là kết quả hợp lệ — trả Optional

Ví dụ API `findById` cho phép vắng mặt:

```java
public Optional<Customer> findById(long id) {
    List<Customer> rows = jdbc.query(
        "SELECT id, name, nickname FROM customers WHERE id = ?",
        CUSTOMER_MAPPER,
        id
    );
    return DataAccessUtils.optionalResult(rows);
}
```

Đây là **method nằm trong repository**, với `jdbc` có kiểu `JdbcOperations`, `CUSTOMER_MAPPER` có kiểu `RowMapper<Customer>` và các import `java.util.List`, `java.util.Optional`, `org.springframework.dao.support.DataAccessUtils`. Bản đầy đủ có thể chạy xem ở mục 6.

`DataAccessUtils.optionalResult(Collection<T>)` có từ Spring Framework **6.1**. Nó có hành vi:

- 0 phần tử: `Optional.empty()`.
- 1 phần tử: `Optional` chứa phần tử nếu khác `null`.
- Nhiều hơn 1 phần tử: `IncorrectResultSizeDataAccessException`.

Ưu điểm so với `rows.stream().findFirst()` là vẫn phát hiện dữ liệu bất thường nếu truy vấn đáng lẽ chỉ có một hàng. Trong ví dụ truy vấn theo primary key `id`, DB đã bảo đảm tính duy nhất; dùng `optionalResult` giúp chính hợp đồng trong Java cũng rõ ràng. Với hệ Spring cũ chưa có `optionalResult`, có thể kiểm tra kích thước `rows` và tự chuyển đổi, giữ trường hợp nhiều hàng là lỗi.

**Quan trọng:** Nếu `RowMapper` trả `null` cho một hàng có thật, `Optional.empty()` cũng có thể xuất hiện. Khi cần phân biệt bản ghi tồn tại với thuộc tính SQL NULL, hãy để mapper tạo object không-null và giữ các thuộc tính nullable ở bên trong object.

### Chiến lược 2: Bắt buộc phải tồn tại — dùng queryForObject

Khi hợp đồng là `getRequiredById`, thiếu bản ghi có thể là lỗi ở tầng truy cập dữ liệu:

```java
public Customer getRequiredById(long id) {
    return jdbc.queryForObject(
        "SELECT id, name, nickname FROM customers WHERE id = ?",
        CUSTOMER_MAPPER,
        id
    );
}
```

Nếu method chỉ dùng nội bộ, có thể để `EmptyResultDataAccessException` lan ra. Nếu business/service cần thông báo bằng ngôn ngữ miền nghiệp vụ, bắt riêng exception này rồi chuyển sang một domain exception như `CustomerNotFoundException`. Không chuyển mọi `DataAccessException` thành "không tồn tại", vì các lỗi khác như SQL syntax sai, database mất kết nối hoặc quá nhiều kết quả không có cùng ý nghĩa.

### Chiến lược 3: Bắt riêng exception và trả Optional

Khi một codebase đã dùng `queryForObject` và chưa thể thay đổi truy vấn:

```java
public Optional<Customer> findById(long id) {
    try {
        Customer result = jdbc.queryForObject(
            "SELECT id, name, nickname FROM customers WHERE id = ?",
            CUSTOMER_MAPPER,
            id
        );
        return Optional.ofNullable(result);
    } catch (EmptyResultDataAccessException ex) {
        return Optional.empty();
    }
}
```

Đây là phương án hợp lệ khi **chỉ có 0 hàng** được xem là tình huống bình thường. Nó giữ nguyên lỗi nhiều hàng, lỗi schema hay lỗi DB khác. Tuy nhiên, trên đường truy vấn thường xuyên không có dữ liệu, việc tạo và bắt exception là không cần thiết nếu có thể dùng `query(...)` trả danh sách. Với API cho phép thiếu bản ghi từ đầu, nên thiết kế `Optional` hoặc list ngay ở repository.

### Chọn thế nào?

- `findById`: thường trả `Optional<Customer>`, tùy hợp đồng của ứng dụng.
- `getRequiredById`: trả `Customer` hoặc ném lỗi khi thiếu.
- `searchByName`: trả `List<Customer>`, 0 hàng thường là danh sách rỗng.
- `countByStatus`: trả một số đếm; `0` là kết quả hợp lệ.
- `updateById` / `deleteById`: xem số hàng bị tác động (`0`/`1`), rồi quyết định xem thiếu bản ghi có phải lỗi nghiệp vụ hay không.

Cách đặt tên method nên giúp người đọc đoán được hợp đồng: `find` thường có thể vắng mặt, `require/getRequired` yêu cầu tồn tại, `list/search` có thể trả 0..N hàng. Đây là **quy ước thiết kế ứng dụng**, không phải Spring tự áp đặt tên method cho `JdbcTemplate`.

## 6. Ví dụ Spring Boot chạy được: quan sát cả 0 hàng, SQL NULL và 0 lần cập nhật

Ví dụ dưới đây dùng **Java 17+, Spring Boot 3.3+, Spring JDBC và H2 in-memory**. Nó cố tình tạo một hàng có `nickname = NULL` để chứng minh SQL NULL khác với không có hàng, và cố tình tìm `id = 99` để quan sát exception.

Tạo dự án Spring Boot Gradle chuẩn có plugin Spring Boot và dependency management. Trong phần `dependencies` của `build.gradle`, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Đây là **khối dependency trong dự án đã cấu hình Spring Boot**, không phải toàn bộ `build.gradle` có thể chạy độc lập.

**`src/main/resources/application.yml`:**

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:empty_result_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
```

**`src/main/java/example/Customer.java`:**

```java
package example;

public record Customer(long id, String name, String nickname) {}
```

`Customer` là record Java 17; trường `nickname` được phép nhận `null` để biểu diễn SQL NULL của cột tương ứng.

**`src/main/java/example/CustomerRepository.java`:**

```java
package example;

import java.util.List;
import java.util.Objects;
import java.util.Optional;

import org.springframework.dao.support.DataAccessUtils;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public final class CustomerRepository {
    private static final RowMapper<Customer> CUSTOMER_MAPPER =
        (rs, rowNum) -> new Customer(
            rs.getLong("id"),
            rs.getString("name"),
            rs.getString("nickname")
        );

    private final JdbcOperations jdbc;

    public CustomerRepository(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    // Hợp đồng: bắt buộc đúng một hàng.
    public Customer getRequiredById(long id) {
        return jdbc.queryForObject(
            "SELECT id, name, nickname FROM customers WHERE id = ?",
            CUSTOMER_MAPPER,
            id
        );
    }

    // Hợp đồng: có thể có 0 hoặc 1 khách hàng.
    public Optional<Customer> findById(long id) {
        List<Customer> rows = jdbc.query(
            "SELECT id, name, nickname FROM customers WHERE id = ?",
            CUSTOMER_MAPPER,
            id
        );
        return DataAccessUtils.optionalResult(rows);
    }

    // Có một hàng nhưng nickname SQL NULL -> Java null.
    public String nicknameFor(long id) {
        return jdbc.queryForObject(
            "SELECT nickname FROM customers WHERE id = ?",
            String.class,
            id
        );
    }

    // COUNT(*) không có GROUP BY trả một hàng kể cả khi đếm bằng 0.
    public long countById(long id) {
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM customers WHERE id = ?",
            Long.class,
            id
        );
        return Objects.requireNonNull(count);
    }

    // UPDATE 0 hàng trả 0, không phải EmptyResultDataAccessException.
    public int rename(long id, String newName) {
        return jdbc.update(
            "UPDATE customers SET name = ? WHERE id = ?",
            newName,
            id
        );
    }
}
```

Ở đây `JdbcOperations` là interface của Spring được `JdbcTemplate` hiện thực. Spring Boot tự cấu hình bean `JdbcTemplate` khi điều kiện auto-configuration phù hợp; repository dùng được qua constructor injection. `RowMapper<Customer>` tạo record không-null khi nhận một hàng, nhờ đó `Optional<Customer>` biểu diễn đúng sự tồn tại của hàng.

**`src/main/java/example/EmptyResultDemoApplication.java`:**

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcOperations;

@SpringBootApplication
public class EmptyResultDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EmptyResultDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo(
            JdbcOperations jdbc, CustomerRepository customers) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE customers (
                    id BIGINT PRIMARY KEY,
                    name VARCHAR(80) NOT NULL,
                    nickname VARCHAR(80)
                )
                """);

            jdbc.update(
                "INSERT INTO customers (id, name) VALUES (?, ?)",
                1L, "Lan"
            );
            jdbc.update(
                "INSERT INTO customers (id, name, nickname) VALUES (?, ?, ?)",
                2L, "Minh", "M"
            );

            System.out.println(
                "required=" + customers.getRequiredById(1L)
            );

            try {
                customers.getRequiredById(99L);
            } catch (EmptyResultDataAccessException ex) {
                System.out.println("missing=EmptyResultDataAccessException");
            }

            System.out.println(
                "optionalFound=" + customers.findById(2L)
            );
            System.out.println(
                "optionalMissing=" + customers.findById(99L)
            );
            System.out.println(
                "nicknameSqlNull=" + (customers.nicknameFor(1L) == null)
            );
            System.out.println(
                "countMissing=" + customers.countById(99L)
            );
            System.out.println(
                "updateMissing=" + customers.rename(99L, "Nobody")
            );
        };
    }
}
```

Chạy từ thư mục gốc của dự án Spring Boot:

```bash
./gradlew bootRun
```

Trên Windows có thể dùng `gradlew.bat bootRun`. Với H2 in-memory vừa tạo và không có script khởi tạo khác, các dòng **do chương trình tự in** là:

```text
required=Customer[id=1, name=Lan, nickname=null]
missing=EmptyResultDataAccessException
optionalFound=Optional[Customer[id=2, name=Minh, nickname=M]]
optionalMissing=Optional.empty
nicknameSqlNull=true
countMissing=0
updateMissing=0
```

Vì sao đúng?

1. `getRequiredById(1)` tìm được một hàng và `RowMapper` tạo một `Customer`. Trường `nickname` là `null` nhưng object `Customer` **vẫn tồn tại**.
2. `getRequiredById(99)` không có hàng, kích hoạt `EmptyResultDataAccessException`. Khối `catch` chỉ in tên tình huống đã quan sát, không phụ thuộc thông điệp exception.
3. `findById(2)` dùng `query` và `DataAccessUtils.optionalResult` nên trả `Optional` có dữ liệu. `findById(99)` trả `Optional.empty()`.
4. `nicknameFor(1)` nhận đúng một hàng và cột SQL NULL, nên giá trị `String` là Java `null`.
5. `COUNT(*)` trả một hàng với số đếm `0`, còn `UPDATE` không tác động hàng nào nên `jdbc.update(...)` trả `0`.

Ba tệp Java này tạo thành phần minh họa đầy đủ khi đặt trong **dự án Spring Boot có dependencies và cấu hình nêu trên**. Chúng không thể biên dịch bằng `javac` đơn thuần nếu thiếu Spring libraries; dùng Gradle/Maven của dự án để biên dịch và chạy. Nếu đổi H2 sang PostgreSQL, cần driver, cấu hình DB, và xét khác biệt dialect/khởi tạo schema.

## 7. Chuyển lỗi kỹ thuật thành hợp đồng nghiệp vụ

Một repository đôi khi có API bắt buộc tồn tại, nhưng service muốn biểu diễn một lỗi có ý nghĩa miền:

```java
public Customer requireCustomer(long id) {
    try {
        return customers.getRequiredById(id);
    } catch (EmptyResultDataAccessException ex) {
        throw new CustomerNotFoundException(id, ex);
    }
}
```

Đây là **mảnh method thuộc service** có biến `customers` kiểu `CustomerRepository` và import `EmptyResultDataAccessException`. Ví dụ một domain exception có thể dùng:

```java
public final class CustomerNotFoundException extends RuntimeException {
    public CustomerNotFoundException(long id, Throwable cause) {
        super("Customer " + id + " does not exist", cause);
    }
}
```

Class này cần nằm trong file `CustomerNotFoundException.java` nếu là public top-level class và có thể đặt trong package của ứng dụng. Việc chuyển lỗi để service/controller biết *không tìm thấy* không buộc tầng repository phải biết HTTP.

Trong một REST API, controller hoặc `@RestControllerAdvice` có thể ánh xạ `CustomerNotFoundException` thành HTTP **404 Not Found** cho đường dẫn đọc một tài nguyên theo ID. Nhưng không nên áp dụng 404 cho mọi truy vấn trả danh sách rỗng: endpoint tìm kiếm thường trả **200 OK** với `[]`; sự phân biệt đó tùy hợp đồng API.

### Không che giấu lỗi database

Đoạn sau có vấn đề:

```java
try {
    return customers.getRequiredById(id);
} catch (org.springframework.dao.DataAccessException ex) {
    return null;
}
```

Đây chỉ là ví dụ **code sai** trong một method trả `Customer`: bắt `DataAccessException` quá rộng rồi đổi mọi lỗi thành `null`. Nó có thể che cả mất kết nối database, SQL sai, permission denied hoặc dữ liệu bị trùng. Nếu muốn diễn đạt thiếu bản ghi, chỉ xử lý `EmptyResultDataAccessException` hoặc thiết kế truy vấn trả `Optional` ngay từ đầu.

Tương tự, không nên chuyển mọi `IncorrectResultSizeDataAccessException` thành `Optional.empty()`: lỗi nhiều hàng báo vi phạm kỳ vọng độc nhất; có thể là lỗi thiết kế SQL/schema hoặc dữ liệu cần điều tra.

### Không dùng exception để làm luồng điều khiển thường xuyên

Nếu một chức năng tra cứu thường xuyên không có dữ liệu, phiên bản `findById` trả `Optional` sẽ làm hợp đồng dễ đọc hơn và tránh tạo stack trace cho nhánh kết quả bình thường. Ngược lại, nếu thiếu dữ liệu là vi phạm tiền điều kiện quan trọng, phát sinh lỗi rõ ràng là phù hợp.

Điểm thiết kế nằm ở **nghĩa của "không tìm thấy"**, không phải ở mong muốn loại bỏ mọi exception.

## 8. Một số trường hợp ít rõ ràng hơn

### 8.1. `queryForObject` trả `null` dù có đúng một hàng

Có thể xảy ra khi giá trị cột trong SQL là `NULL` (với dạng `requiredType`) hoặc khi `RowMapper` do lập trình viên cung cấp trả `null`. Không đồng nhất "không ném exception" với "giá trị luôn khác null". Trong Java, nếu cần dữ liệu chắc chắn khác null, thể hiện ràng buộc bằng `NOT NULL` ở schema, kiểm tra dữ liệu và hợp đồng method rõ ràng.

### 8.2. Không có hàng vì filter, join hoặc quyền truy cập

Điều kiện `WHERE` sai, join loại bỏ hàng, tenant filter, soft-delete filter hoặc điều kiện phân quyền đều có thể khiến kết quả truy vấn là 0 hàng. Trước khi kết luận "database không có record", cần biết **SQL thực sự đã gửi**, các tham số bind, tenant/security context và database/schema nào đang được kết nối.

Không để log chứa mật khẩu, access token hoặc dữ liệu cá nhân nhạy cảm chỉ để debug một truy vấn thiếu hàng.

### 8.3. Gọi nhiều lần và dữ liệu đồng thời thay đổi

Giữa bước "kiểm tra bản ghi có tồn tại" và bước "đọc/cập nhật bản ghi", transaction khác có thể xóa hoặc thay đổi dữ liệu. Một truy vấn kiểm tra trước không bảo đảm truy vấn tiếp theo vẫn tìm thấy hàng. Khi thao tác ghi, thường nên dựa vào **số hàng tác động** và các ràng buộc DB; nếu cần bảo đảm tính nhất quán đặc biệt, thiết kế isolation, locking hoặc versioning phù hợp.

### 8.4. `UPDATE` không tìm thấy không tự ném EmptyResultDataAccessException

```java
int affected = jdbc.update(
    "UPDATE customers SET name = ? WHERE id = ?",
    "New name",
    99L
);
```

`affected` là `0` nếu không có hàng bị sửa. Nếu nghiệp vụ yêu cầu đúng một hàng được cập nhật, **ứng dụng tự kiểm tra**:

```java
if (affected == 0) {
    throw new CustomerNotFoundException(99L, null);
}
if (affected != 1) {
    throw new IllegalStateException(
        "Expected one updated customer, got " + affected
    );
}
```

Hai mảnh này nằm trong một method có `jdbc` và class exception đã định nghĩa ở trên. Thông thường, `UPDATE ... WHERE id = ?` với `id` là primary key có thể tác động tối đa một hàng. Nếu dùng `WHERE` theo thuộc tính không duy nhất, phải xét trường hợp nhiều hàng được cập nhật. `0` có thể do không tồn tại hoặc điều kiện bổ sung như version không còn khớp; tùy nghiệp vụ có thể là "conflict" thay vì "not found".

### 8.5. Một record có khóa duy nhất mới bảo đảm tối đa một hàng

Nếu `WHERE name = ?` là tiêu chí không unique, `queryForObject` có thể thất bại ở nhánh **nhiều hàng**, ngay cả khi test ban đầu chỉ có một tên trùng. Muốn bảo đảm dữ liệu tối đa một hàng, thiết kế constraint UNIQUE/PRIMARY KEY phù hợp hoặc làm rõ rằng thao tác chỉ cần "bản ghi mới nhất" và sắp xếp/giới hạn đúng cách.

Không dùng `LIMIT 1` để che giấu một lỗi về uniqueness mà nghiệp vụ cần phát hiện.

### 8.6. Lỗi số hàng khác lỗi số cột

`queryForObject(sql, String.class, ...)` cần một hàng **và một cột**. `SELECT id, name ...` có hai cột nên không khớp overload đó, kể cả truy vấn chỉ trả một hàng. Với kết quả nhiều cột, dùng `RowMapper<Customer>` để ánh xạ, hoặc chọn đúng một cột trong SQL.

## 9. Viết kiểm thử để phân biệt các nhánh

Bài kiểm thử có giá trị cần chứng minh các trường hợp **0 hàng**, **1 hàng với giá trị NULL**, **1 hàng bình thường**, **nhiều hàng**, và **UPDATE 0 hàng**.

Với dự án Spring Boot đã có `spring-boot-starter-test` và H2, có thể viết một bài test JDBC slice. Ví dụ này dùng cùng `CustomerRepository` và `Customer` ở mục 6.

**Bổ sung dependency test** trong build Gradle đã cấu hình:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

**`src/test/java/example/CustomerRepositoryTest.java`:**

```java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.core.JdbcOperations;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@Import(CustomerRepository.class)
class CustomerRepositoryTest {
    @Autowired
    JdbcOperations jdbc;

    @Autowired
    CustomerRepository customers;

    @BeforeEach
    void setUp() {
        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id BIGINT PRIMARY KEY,
                name VARCHAR(80) NOT NULL,
                nickname VARCHAR(80)
            )
            """);
        jdbc.update("DELETE FROM customers");
        jdbc.update(
            "INSERT INTO customers (id, name) VALUES (?, ?)",
            1L, "Lan"
        );
        jdbc.update(
            "INSERT INTO customers (id, name, nickname) VALUES (?, ?, ?)",
            2L, "Minh", "M"
        );
    }

    @Test
    void requiredLookupThrowsWhenZeroRows() {
        assertThrows(
            EmptyResultDataAccessException.class,
            () -> customers.getRequiredById(99L)
        );
    }

    @Test
    void optionalLookupReturnsEmptyWhenZeroRows() {
        assertTrue(customers.findById(99L).isEmpty());
        assertEquals("Minh", customers.findById(2L).orElseThrow().name());
    }

    @Test
    void existingRowWithNullColumnIsNotMissing() {
        assertNull(customers.nicknameFor(1L));
        assertTrue(customers.findById(1L).isPresent());
    }

    @Test
    void countAndUpdateUseZeroValueInsteadOfEmptyResultError() {
        assertEquals(0L, customers.countById(99L));
        assertEquals(0, customers.rename(99L, "Nobody"));
    }

    @Test
    void queryForObjectRejectsMultipleRows() {
        assertThrows(
            IncorrectResultSizeDataAccessException.class,
            () -> jdbc.queryForObject(
                "SELECT id FROM customers",
                Long.class
            )
        );
    }
}
```

Chạy:

```bash
./gradlew test
```

Trên Windows dùng `gradlew.bat test`. Spring Boot 3.3 với `@JdbcTest`, H2 và repository đã import sẽ chạy các kiểm tra với database embedded. Code test không cần khởi động toàn bộ ứng dụng qua `main`; `@JdbcTest` chỉ khởi tạo các thành phần JDBC liên quan.

Kết quả mong đợi: **5 bài test pass**. Điều kiện là không có schema khác xung đột bảng `customers`, H2 dependency/config test hợp lệ, và các phiên bản JUnit/Spring Boot tương thích. Vì `@JdbcTest` thường tạo transaction rồi rollback sau mỗi test, từng method được cách ly theo quy tắc kiểm thử Spring; vẫn nên tránh phụ thuộc thứ tự chạy test.

**Không viết test kỳ vọng nguyên văn thông điệp exception.** Nên kiểm tra *loại lỗi*, kiểu kết quả, số hàng và dữ liệu. Nếu muốn phân biệt thiếu hàng với nhiều hàng, nên có test riêng cho hai nhánh thay vì chỉ dùng `assertThrows(DataAccessException.class, ...)` quá rộng.

## 10. Cách chọn giao diện ở từng tầng

```text
GET /customers/99
      |
      v
Controller
      |
      v
Service: requireCustomer(99)
      |
      v
Repository: getRequiredById(99)
      |
      v
JdbcTemplate.queryForObject(...)
      |
      +-- 1 hàng  -> Customer
      |
      +-- 0 hàng  -> EmptyResultDataAccessException
      |                 |
      |                 v
      |          Service chuyển thành NotFound
      |                 |
      |                 v
      |          Controller trả 404 theo hợp đồng API
      |
      +-- >1 hàng -> IncorrectResultSizeDataAccessException
                        (vi phạm kỳ vọng cần điều tra)
```

Trong luồng lấy **danh sách**, repository dùng `query(...)` trả `List<Customer>` rồi controller có thể trả `200 OK` với `[]`. Trong luồng lấy **một tài nguyên cụ thể**, service có thể trả thông báo không tồn tại hoặc ánh xạ 404. Trong luồng chạy **job bắt buộc phải có dữ liệu tham chiếu**, "0 hàng" có thể là lỗi cấu hình nghiêm trọng; không nên tùy tiện bỏ qua.

Với HTTP, nên cân nhắc không làm lộ thông tin tồn tại của tài nguyên mà người gọi không có quyền xem. Quy tắc phản hồi còn phụ thuộc mô hình phân quyền và hợp đồng API, không thể suy ra trực tiếp chỉ từ `EmptyResultDataAccessException`.

### Giao dịch và rollback

`EmptyResultDataAccessException` là runtime exception. Nếu nó thoát khỏi method `@Transactional` được Spring quản lý, chính sách rollback mặc định thường đánh dấu rollback cho giao dịch. Nếu bạn bắt lỗi và trả `Optional.empty()` bên trong transaction, exception không còn thoát ra; vì vậy không nên coi "bắt exception" và "để exception lan ra" là tương đương về hậu quả transaction. Có thể cần áp dụng quy tắc nghiệp vụ hoặc rollback explicit khi cần.

Tuy nhiên, không phải cứ gặp "not found" là phải rollback: ví dụ một tra cứu tùy chọn trong transaction có thể hợp lệ khi không có hàng. Thiết kế transaction theo **ý nghĩa của toàn bộ tác vụ**, không theo mong muốn xử lý chung mọi lỗi 0 hàng.

## 11. Những lỗi dễ mắc

1. **"queryForObject trả null nếu không có hàng."** Sai: khi 0 hàng, nó ném `EmptyResultDataAccessException`. `null` chỉ có thể đến từ một hàng được ánh xạ sang giá trị null.
2. **"Không tìm thấy hàng nghĩa là SQL bị lỗi."** Sai: câu SQL có thể hoàn toàn hợp lệ và trả 0 hàng. Lỗi xuất hiện do contract "đúng một hàng" của API Spring.
3. **"Cứ catch DataAccessException rồi trả Optional.empty."** Sai: che cả lỗi DB/SQL khác. Chỉ xử lý trường hợp vắng mặt dự kiến.
4. **"COUNT(*) bằng 0 sẽ ném EmptyResultDataAccessException."** Sai với query count không nhóm: nó trả một hàng có giá trị 0.
5. **"UPDATE không tìm thấy sẽ ném EmptyResultDataAccessException."** Sai: `jdbc.update` thường trả số hàng tác động bằng 0.
6. **"Đã có RowMapper thì có thể xử lý zero rows trong callback."** Sai: callback không được gọi khi không có hàng để map.
7. **"Đặt LIMIT 1 là hết mọi vấn đề."** Sai: không xử lý 0 hàng và có thể che dữ liệu trùng; còn phải xét thứ tự.
8. **"Nếu query trả nhiều hàng thì cứ lấy phần tử đầu."** Không phù hợp khi business đòi uniqueness; `findFirst` có thể giấu lỗi dữ liệu.
9. **"SQL NULL và thiếu record giống nhau."** Sai: cần phân biệt sự tồn tại của hàng và giá trị cột.
10. **"EmptyResultDataAccessException là checked SQLException."** Sai: nó là unchecked exception trong hệ `DataAccessException` của Spring.
11. **"Bắt lỗi rồi dùng bất kỳ một đối tượng giả là an toàn."** Cẩn trọng: fallback phải là kết quả được business cho phép, không thay thế việc xác minh dữ liệu cần thiết.
12. **"Mọi API single-result của mọi thư viện đều cùng hành vi."** Sai: cần đọc hợp đồng chính xác của `JdbcTemplate`, `NamedParameterJdbcTemplate`, `JdbcClient`, JPA hay Spring Data repositories.

## 12. Tự kiểm tra

**Câu 1.** Truy vấn `SELECT name FROM customers WHERE id = 99` không có hàng. `jdbc.queryForObject(sql, String.class, ...)` trả gì?

**Đáp án:** Ném `EmptyResultDataAccessException`, không trả `null`.

**Câu 2.** Cột `nickname` của khách hàng `id = 1` là SQL `NULL`. Lời gọi `queryForObject` đọc duy nhất cột này trả gì?

**Đáp án:** Java `null` vì có đúng một hàng, giá trị cột là SQL NULL; không có lỗi thiếu hàng.

**Câu 3.** Khi tìm danh sách khách hàng theo tên mà có thể không ai khớp, nên chọn API nào?

**Đáp án:** `query(...)` trả `List<Customer>`, 0 hàng là danh sách rỗng. Không nên bắt lỗi từ một API yêu cầu đúng một hàng để mô phỏng chức năng tìm danh sách.

**Câu 4.** Nếu `queryForObject` nhận hai hàng thì đó có phải `EmptyResultDataAccessException` không?

**Đáp án:** Không. Trường hợp nhiều hàng vi phạm yêu cầu đúng một nhưng là `IncorrectResultSizeDataAccessException`. `EmptyResultDataAccessException` dành cho 0 hàng.

**Câu 5.** Làm sao biểu diễn "có customer nhưng nickname NULL" khác "không có customer"?

**Đáp án:** Ánh xạ một hàng sang `Customer` không-null rồi trả `Optional<Customer>`. `Optional.empty()` nghĩa là không có hàng; `Optional.of(customer)` có thể chứa thuộc tính nickname bằng `null`.

**Câu 6.** Nếu `jdbc.update("DELETE ... WHERE id = ?", 99L)` trả 0, ứng dụng có bắt `EmptyResultDataAccessException` không?

**Đáp án:** Không. Đây là kết quả số hàng tác động. Nếu business yêu cầu một hàng phải được xóa, hãy tự kiểm tra `affected == 0` và chuyển thành kết quả/lỗi miền phù hợp.

**Câu 7.** Vì sao nên dùng `DataAccessUtils.optionalResult` thay vì `stream().findFirst()` khi kỳ vọng 0 hoặc 1 hàng?

**Đáp án:** `optionalResult` giữ được quy tắc "nhiều hơn một là lỗi". `findFirst` âm thầm bỏ qua những hàng dư, che khuất vi phạm uniqueness.

## Tài liệu tham khảo

- [Spring Framework — EmptyResultDataAccessException](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/dao/EmptyResultDataAccessException.html): ý nghĩa lỗi thiếu hàng và quan hệ với `IncorrectResultSizeDataAccessException`.
- [Spring Framework — JdbcOperations, 6.2](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html): hợp đồng `queryForObject`, `query`, `queryForMap`, `update` và các overload.
- [Spring Framework — DataAccessUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/support/DataAccessUtils.html): `optionalResult`, `singleResult` và các quy tắc xử lý số lượng kết quả.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): cách `JdbcTemplate` truy vấn, ánh xạ hàng, xử lý resource và lỗi.
- [Spring Framework — JdbcClient](https://docs.spring.io/spring-framework/docs/6.1.0-M4/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html): API fluent `single()`/`optional()` có từ Spring 6.1.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): cấu hình `DataSource` và Spring JDBC.

**Ghi nhớ:** `EmptyResultDataAccessException` xuất hiện khi một API **yêu cầu có hàng** mà query trả **0 hàng**. Việc thiếu dữ liệu có thể là bình thường hoặc là lỗi nghiệp vụ; quyết định nằm ở hợp đồng repository/service. Dùng `Optional` hoặc `List` cho kết quả được phép vắng mặt, dùng `queryForObject` khi thực sự đòi hỏi đúng một hàng, và luôn phân biệt 0 hàng với một hàng chứa SQL NULL hoặc một phép `COUNT(*)` trả số đếm 0.
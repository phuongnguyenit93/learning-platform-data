# Liên kết tham số có tên bằng @Param và thông tin tên tham số

Khi viết SQL tùy chỉnh cho Spring Data JDBC, câu truy vấn thường cần nhận giá trị từ tham số của repository method. Thay vì nối chuỗi SQL với dữ liệu đầu vào, ta dùng **named parameter** như `:email` hoặc `:status` rồi liên kết tên đó với tham số Java bằng annotation **`@Param`**.

Cách làm này giúp câu SQL dễ đọc, tránh nhầm thứ tự tham số và cho phép JDBC bind giá trị an toàn. Spring Data cũng có thể khám phá tên tham số từ metadata của bytecode nếu project được biên dịch với thông tin tên tham số. Tuy nhiên, khi query là một phần quan trọng của contract persistence, khai báo `@Param` tường minh thường giúp code dễ hiểu và ít phụ thuộc cấu hình build hơn.

Bài học tập trung vào cách khai báo `@Query` và `@Param` trong Spring Data JDBC, cách tên tham số được khám phá, quy tắc đặt placeholder, cách kiểm tra lỗi binding và những giới hạn cần nhớ khi dùng named parameter.

## 1. Named parameter trong SQL tùy chỉnh

Giả sử repository cần tìm khách hàng theo email. SQL có thể viết:

```sql
SELECT id, name, email
FROM customers
WHERE email = :email
```

`:email` là một **named parameter**. Tên này được ánh xạ tới một giá trị Java khi Spring Data JDBC thực thi query.

Repository method:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :email
    """)
Optional<Customer> findByEmail(@Param("email") String email);
```

Ở đây:

- `:email` trong SQL là tên placeholder.
- `@Param("email")` chỉ rõ tham số Java nào cung cấp giá trị cho placeholder.
- `String email` là giá trị thực tế được bind khi gọi method.
- `Optional<Customer>` biểu diễn kết quả có thể không tìm thấy hàng.

Tên trong `@Param` phải khớp với tên placeholder trong SQL. Tên biến Java có thể khác nếu annotation chỉ rõ tên liên kết.

## 2. Các annotation và package cần dùng

Với Spring Data JDBC, import `@Query` từ package JDBC:

```java
import org.springframework.data.jdbc.repository.query.Query;
```

`@Param` được cung cấp bởi Spring Data Commons:

```java
import org.springframework.data.repository.query.Param;
```

Ví dụ repository đầy đủ:

```java
// Customer.java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
    @Id Long id,
    String name,
    String email,
    boolean active
) {}
```

```java
// CustomerRepository.java
import java.util.Optional;

import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.ListCrudRepository;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends ListCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, name, email, active
        FROM customers
        WHERE email = :email
        """)
    Optional<Customer> findByEmail(
        @Param("email") String email
    );
}
```

`@Query` nói rằng method sử dụng câu SQL do developer khai báo. `@Param` liên kết tham số method với named placeholder trong câu SQL đó.

Không nhầm `@Param` với `@PathVariable` của Spring MVC hoặc `@RequestParam` của controller. Các annotation web bind dữ liệu HTTP vào method controller; `@Param` ở đây bind tham số repository vào SQL query.

## 3. Vì sao nên dùng tên thay vì vị trí tham số?

Với một câu truy vấn có nhiều giá trị, named parameter làm rõ ý nghĩa từng giá trị:

```sql
SELECT id, name, email
FROM customers
WHERE status = :status
  AND city = :city
  AND created_at >= :createdAfter
```

Method tương ứng:

```java
List<Customer> search(
    @Param("status") CustomerStatus status,
    @Param("city") String city,
    @Param("createdAfter") Instant createdAfter
);
```

Người đọc có thể nhận ra ngay:

- `:status` lấy giá trị trạng thái.
- `:city` lấy thành phố.
- `:createdAfter` lấy mốc thời gian.

Nếu chỉ nhìn một danh sách tham số theo vị trí, cần nhớ tham số thứ nhất ứng với điều kiện nào, tham số thứ hai ứng với điều kiện nào. Khi SQL được chỉnh sửa hoặc thêm điều kiện, tên giúp giảm nguy cơ đảo nhầm giá trị.

Named parameter cũng thuận tiện khi một giá trị xuất hiện nhiều lần trong query. Cùng một tên placeholder có thể được dùng tại nhiều vị trí và nhận cùng giá trị bind.

## 4. @Param liên kết tên như thế nào?

`@Param` nhận một chuỗi là tên được dùng trong query:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :email
    """)
Optional<Customer> lookup(
    @Param("email") String address
);
```

Ở ví dụ này:

| Thành phần | Giá trị |
| --- | --- |
| Tên placeholder SQL | `:email` |
| Giá trị annotation | `"email"` |
| Tên biến Java | `address` |
| Giá trị được bind | Nội dung của biến `address` |

Tên biến Java không bắt buộc giống tên placeholder nếu `@Param` đã cung cấp mapping rõ ràng. Đây là một lợi ích quan trọng: query có thể giữ tên domain rõ nghĩa ngay cả khi method parameter dùng một tên khác.

Nếu đổi SQL thành `WHERE email = :customerEmail` nhưng vẫn giữ `@Param("email")`, mapping không còn khớp. Hãy cập nhật cả hai phía cùng nhau.

### 4.1. Một method có nhiều named parameter

Ví dụ:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE status = :status
      AND city = :city
      AND email <> :excludedEmail
    """)
List<Customer> search(
    @Param("status") CustomerStatus status,
    @Param("city") String city,
    @Param("excludedEmail") String excludedEmail
);
```

Mỗi placeholder có một tham số tương ứng. Tên placeholder không phụ thuộc thứ tự khai báo tham số Java.

### 4.2. Dùng một tham số nhiều lần

Ví dụ query cần tìm cùng một từ khóa trong tên hoặc email:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE name LIKE :pattern
       OR email LIKE :pattern
    """)
List<Customer> searchByPattern(
    @Param("pattern") String pattern
);
```

Khi gọi:

```java
repository.searchByPattern("%an%");
```

Cùng giá trị `pattern` được bind vào cả hai vị trí. Việc dùng lại placeholder giúp tránh phải khai báo hai tham số Java có cùng nội dung chỉ vì SQL sử dụng giá trị ở hai điều kiện.

## 5. Thông tin tên tham số trong bytecode

Spring Data có thể khám phá tên tham số method từ metadata reflection của Java. Tuy nhiên, tên biến viết trong source code không phải lúc nào cũng được giữ lại trong bytecode.

Với Java compiler, tùy chọn `-parameters` yêu cầu lưu thông tin tên tham số để reflection có thể đọc qua `Parameter.getName()`.

Ví dụ:

```java
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

Đây là cấu hình Gradle Groovy. Nếu project đã bật tùy chọn này trong convention plugin hoặc cấu hình chung, không cần thêm lần nữa.

Với Maven Compiler Plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Nếu không có metadata tên tham số, reflection có thể trả về tên tổng quát như `arg0`, `arg1` thay vì tên source như `email`. Khi đó Spring Data không thể dựa vào tên source để liên kết placeholder theo ý muốn.

### 5.1. Không bật -parameters thì @Param có hoạt động không?

`@Param` cung cấp tên liên kết tường minh ngay trên tham số, vì vậy code không phải dựa vào việc khám phá tên biến từ bytecode cho tham số đó.

Ví dụ:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :email
    """)
Optional<Customer> findByEmail(
    @Param("email") String email
);
```

Cách khai báo này làm rõ contract ngay tại source code. Dù vậy, cấu hình `-parameters` vẫn hữu ích cho các API/framework khác cần khám phá tên tham số và cho những method không sử dụng `@Param`.

### 5.2. Dùng tên tham số Java mà không có @Param

Trong những phiên bản Spring Data hỗ trợ parameter name discovery, có thể viết:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :email
    """)
Optional<Customer> findByEmail(String email);
```

Framework cần khám phá được tên tham số Java là `email` từ metadata. Nếu bytecode không giữ tên, việc binding có thể thất bại hoặc không tìm được tên tương ứng.

Do đó, khi method có SQL named parameter, có hai cách:

| Cách | Điều kiện | Đặc điểm |
| --- | --- | --- |
| Khai báo `@Param("email")` | Tên annotation khớp placeholder | Tường minh, dễ đọc, ít phụ thuộc compiler metadata. |
| Dùng trực tiếp tên tham số | Spring Data có thể khám phá tên từ bytecode, thường cần `-parameters` | Ít annotation hơn nhưng phụ thuộc build configuration. |

Đối với repository method có nhiều tham số hoặc SQL quan trọng, `@Param` tường minh thường là lựa chọn dễ bảo trì.

## 6. Binding an toàn và tránh SQL injection

Một lợi ích quan trọng của named parameter là giá trị được truyền riêng cho JDBC để bind vào câu SQL. Không nên ghép chuỗi dữ liệu người dùng trực tiếp vào SQL.

**Không an toàn:**

```java
String sql = "SELECT id, name FROM customers "
    + "WHERE email = '" + email + "'";

return jdbcTemplate.queryForList(sql);
```

Nếu `email` đến từ request và chứa nội dung SQL độc hại, câu truy vấn có thể bị thay đổi cấu trúc.

**Sử dụng parameter binding:**

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :email
    """)
Optional<Customer> findByEmail(
    @Param("email") String email
);
```

Spring Data JDBC chuyển giá trị tham số tới cơ chế JDBC binding thay vì coi nó là một phần cú pháp SQL. Điều này giúp ngăn SQL injection thông qua **giá trị** được bind đúng cách.

Lưu ý: parameter binding bảo vệ giá trị, nhưng không dùng để thay thế tên bảng, tên cột, từ khóa SQL hoặc đoạn ORDER BY tùy ý. Nếu người dùng được chọn cột sắp xếp, hãy ánh xạ input qua danh sách identifier được cho phép thay vì bind tên cột như một giá trị.

### 6.1. Tên parameter không phải nội dung SQL

Ví dụ:

```java
@Param("email") String email
```

`email` là tên liên kết. Giá trị thật có thể là `an@example.test`. Framework không thay chuỗi thô vào SQL như thao tác nối chuỗi; nó bind giá trị theo JDBC.

Khi log SQL, cần cẩn thận vì một số cấu hình logging có thể ghi cả parameter values và làm lộ dữ liệu cá nhân. Chỉ bật log chi tiết ở môi trường phù hợp và dùng dữ liệu thử nghiệm.

## 7. Ví dụ tìm kiếm với LIKE

Một trường hợp phổ biến là tìm kiếm chuỗi. Có thể chuẩn bị pattern ở Java rồi bind:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE name LIKE :pattern
    """)
List<Customer> findByNamePattern(
    @Param("pattern") String pattern
);
```

Service:

```java
public List<Customer> searchByName(String keyword) {
    String pattern = "%" + keyword + "%";
    return customers.findByNamePattern(pattern);
}
```

Ở đây ký tự wildcard `%` được thêm vào giá trị Java, sau đó bind như một giá trị thông thường. Điều này giúp SQL rõ ràng và tránh phải nối keyword vào câu query.

Nếu cần tìm kiếm không phân biệt hoa thường, cú pháp phụ thuộc database. Ví dụ PostgreSQL có `ILIKE`; các database khác có thể dùng collation hoặc hàm chuyển chữ hoa/thường. Hãy chọn cú pháp theo dialect của dự án.

Nếu keyword có thể chứa chính ký tự wildcard `%` hoặc `_` và nghiệp vụ muốn tìm literal, cần escape các ký tự đó theo quy tắc database và khai báo `ESCAPE` phù hợp. Parameter binding không tự vô hiệu hóa ý nghĩa wildcard của LIKE.

## 8. Binding giá trị null

Một named parameter có thể nhận giá trị null nếu kiểu Java và mapping cho phép. Tuy nhiên, SQL so sánh:

```sql
WHERE email = :email
```

khi `:email` là NULL không có nghĩa là “tìm các hàng có email NULL”. Trong SQL, phép so sánh `= NULL` cho kết quả UNKNOWN, không phải TRUE.

Muốn tìm hàng có cột NULL, dùng:

```sql
WHERE email IS NULL
```

Nếu query có điều kiện tùy chọn, có thể thiết kế rõ:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE (:status IS NULL OR status = :status)
    """)
List<Customer> findByOptionalStatus(
    @Param("status") String status
);
```

Ví dụ này minh họa ý tưởng SQL; khả năng bind giá trị null và suy luận kiểu SQL phụ thuộc driver/database. Một số database cần cast tường minh cho parameter null vì không suy luận được kiểu dữ liệu. Với truy vấn phức tạp, có thể tách hai query hoặc dùng custom repository để tránh biểu thức tùy chọn khó tối ưu.

Không nên xem `@Param` như một cơ chế tự biến phép so sánh null thành IS NULL.

## 9. Named parameter với kiểu dữ liệu khác nhau

Named parameter không chỉ dùng cho String. Có thể bind các kiểu Java phù hợp với mapping JDBC:

```java
@Query("""
    SELECT id, name, created_at
    FROM customers
    WHERE created_at >= :from
      AND created_at < :to
    """)
List<CustomerSummary> findCreatedBetween(
    @Param("from") Instant from,
    @Param("to") Instant to
);
```

Một số kiểu thường gặp:

| Kiểu Java | Dữ liệu SQL thường tương ứng |
| --- | --- |
| `String` | VARCHAR/TEXT |
| `Long`, `Integer` | BIGINT/INTEGER |
| `BigDecimal` | DECIMAL/NUMERIC |
| `Boolean` | BOOLEAN hoặc kiểu tương đương của database |
| `LocalDate` | DATE |
| `LocalDateTime` | TIMESTAMP |
| `Instant` | Timestamp/instant theo driver và mapping |
| `UUID` | UUID hoặc dạng lưu trữ tương ứng theo database |

Mapping chính xác phụ thuộc database, JDBC driver và conversion configuration của ứng dụng. Khi dùng kiểu thời gian hoặc UUID trong schema legacy, cần kiểm tra kiểu cột thực tế và conversion đã cấu hình.

## 10. Tên tham số phải khớp với placeholder

Một số lỗi thường xuất hiện khi đổi tên method hoặc sửa query.

### 10.1. Placeholder và @Param không khớp

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :customerEmail
    """)
Optional<Customer> findByEmail(
    @Param("email") String email
);
```

Query cần tên `customerEmail` nhưng method chỉ cung cấp tên `email`. Framework không thể tìm thấy giá trị bind cho placeholder đó.

Sửa một trong hai phía:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :customerEmail
    """)
Optional<Customer> findByEmail(
    @Param("customerEmail") String email
);
```

Hoặc đổi placeholder thành `:email` để khớp với annotation hiện tại.

### 10.2. Quên @Param trên một tham số

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE status = :status
      AND city = :city
    """)
List<Customer> search(
    @Param("status") CustomerStatus status,
    String city
);
```

Tham số `city` phụ thuộc vào khả năng khám phá tên tham số từ bytecode. Nếu build không có `-parameters` hoặc metadata không khả dụng, binding có thể thất bại.

Để nhất quán:

```java
List<Customer> search(
    @Param("status") CustomerStatus status,
    @Param("city") String city
);
```

### 10.3. Dùng tên property thay cho tên cột vật lý

Nếu domain có property `contactEmail` nhưng database column là `contact_email`, SQL viết tay phải dùng tên cột vật lý:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

// Mapping minh họa cho một schema khác với Customer ở trên.
@Table("customers")
public record Customer(
    @Id Long id,
    @Column("contact_email") String contactEmail,
    @Column("display_label") String displayName
) {}
```

```java
// CustomerRepository.java
import java.util.Optional;

import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.ListCrudRepository;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends ListCrudRepository<Customer, Long> {

@Query("""
    SELECT id, contact_email, display_label
    FROM customers
    WHERE contact_email = :email
    """)
Optional<Customer> findByContactEmail(
    @Param("email") String email
);
}
```

`@Param` liên kết tham số Java với placeholder; nó không chuyển tên property thành tên cột. Với `@Query` SQL tường minh, developer chịu trách nhiệm viết đúng tên bảng/cột theo schema và dialect.

## 11. Named parameter và query method được dẫn xuất

Không phải mọi repository method đều cần `@Query` và `@Param`.

Nếu truy vấn đơn giản theo quy tắc tên property, có thể dùng query derivation:

```java
Optional<Customer> findByEmail(String email);

List<Customer> findByStatusAndCity(
    CustomerStatus status,
    String city
);
```

Spring Data phân tích tên method và tạo query dựa trên domain property. Các tham số được liên kết theo thứ tự/metadata của method theo quy tắc query derivation; không cần viết placeholder SQL.

Dùng `@Query` và `@Param` khi cần:

- SQL đặc thù database.
- JOIN hoặc biểu thức SQL rõ ràng.
- Truy vấn tổng hợp.
- Cấu trúc SELECT hoặc điều kiện không thuận tiện biểu đạt bằng method name.
- Kiểm soát chính xác query được gửi tới database.

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Tìm theo một property đơn giản | `findByEmail(String email)` |
| Kết hợp một vài property theo quy tắc hỗ trợ | Query derivation |
| SQL JOIN hoặc aggregate/report query | `@Query` với named parameter |
| SQL phức tạp cần custom mapping | Custom repository và Spring JDBC operations |

## 12. Named parameter với custom repository

Khi query phức tạp hoặc cần kiểm soát mapping kết quả, có thể dùng `NamedParameterJdbcOperations` trực tiếp.

Ví dụ:

```java
@Repository
public class CustomerSearchRepository {

    private final NamedParameterJdbcOperations jdbc;

    public CustomerSearchRepository(
        NamedParameterJdbcOperations jdbc
    ) {
        this.jdbc = jdbc;
    }

    public List<CustomerSummary> search(String city, String keyword) {
        String sql = """
            SELECT id, name, email
            FROM customers
            WHERE city = :city
              AND name LIKE :pattern
            ORDER BY name
            """;

        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("city", city)
            .addValue("pattern", "%" + keyword + "%");

        return jdbc.query(sql, params, (rs, rowNum) ->
            new CustomerSummary(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getString("email")
            )
        );
    }
}
```

DTO kết quả có thể được khai báo riêng:

```java
public record CustomerSummary(Long id, String name, String email) {}
```

Ở đây vẫn dùng named parameter, nhưng việc bind và ánh xạ row do code custom thực hiện. Cách này phù hợp với query read model phức tạp, trong khi repository CRUD vẫn quản lý aggregate.

`@Param` của Spring Data repository và `MapSqlParameterSource` của Spring JDBC phục vụ cùng ý tưởng đặt tên cho giá trị SQL, nhưng thuộc hai API khác nhau.

## 13. Kiểm thử repository query có @Param

Một test repository nên xác nhận query trả đúng kết quả với giá trị tham số, đồng thời không phụ thuộc vào thứ tự ngầm định.

Ví dụ:

```java
@DataJdbcTest
class CustomerRepositoryQueryTest {

    @Autowired
    CustomerRepository customers;

    @Test
    void findsCustomerByEmailUsingNamedParameter() {
        customers.save(new Customer(
            null,
            "Lan",
            "lan@example.test",
            true
        ));

        Optional<Customer> found =
            customers.findByEmail("lan@example.test");

        assertThat(found).isPresent();
        assertThat(found.orElseThrow().email())
            .isEqualTo("lan@example.test");
    }
}
```

Test cần datasource test, schema và entity mapping phù hợp. Với custom SQL có cú pháp riêng của PostgreSQL/MySQL/SQL Server, hãy chạy test trên đúng database hoặc Testcontainers tương ứng thay vì chỉ dựa vào H2.

### 13.1. Kiểm thử giá trị chứa dấu nháy

Có thể dùng input:

```java
String email = "o'connor@example.test";
repository.findByEmail(email);
```

Nếu parameter binding đúng, dấu nháy là dữ liệu của giá trị, không làm thay đổi cú pháp SQL. Đây là một kiểm tra hữu ích để phát hiện code đang nối chuỗi SQL sai cách.

### 13.2. Kiểm tra build metadata

Nếu dự án bỏ `@Param` ở một số method và dựa vào tên tham số, test cần chạy với artifact được biên dịch đúng cấu hình. Một lần chạy trong IDE có thể khác với build CI nếu compiler arguments không đồng nhất.

Bật `-parameters` trong cấu hình build chung thường giúp giảm khác biệt giữa local và CI.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy giá trị cho named parameter | Placeholder và `@Param` khác tên. | Đối chiếu tên sau dấu `:` với giá trị annotation. |
| Tên tham số được nhận thành `arg0` | Bytecode không lưu parameter name metadata. | Dùng `@Param` tường minh hoặc bật `-parameters`. |
| Query chạy nhưng trả kết quả rỗng | Bind sai giá trị, tên cột/property sai hoặc dữ liệu không khớp. | Kiểm tra SQL, giá trị input và schema thực tế. |
| Giá trị có dấu nháy làm query lỗi | SQL đang nối chuỗi thay vì bind parameter, hoặc query có cú pháp khác. | Dùng named parameter binding. |
| Dùng parameter để thay tên bảng/cột | Bind parameter chỉ dành cho giá trị, không phải SQL identifier. | Chọn identifier từ allowlist và xây query có kiểm soát. |
| Truyền null nhưng muốn tìm cột NULL | So sánh `= NULL` không đúng semantics SQL. | Dùng `IS NULL` hoặc điều kiện tùy chọn có chủ đích. |
| LIKE không tìm thấy ký tự wildcard như literal | `%` và `_` có semantics wildcard. | Escape wildcard theo dialect và dùng `ESCAPE`. |
| Test H2 pass, production database fail | Cú pháp SQL, kiểu parameter hoặc dialect khác nhau. | Integration test trên database thực tế. |

## 15. Quy trình khai báo và bảo trì

Khi viết repository method có SQL tùy chỉnh:

1. Viết SQL với placeholder có tên, ví dụ `:email`, `:status`.
2. Khai báo tham số method với `@Param("...")` có cùng tên.
3. Chọn kiểu Java tương thích với kiểu cột và JDBC driver.
4. Không nối dữ liệu người dùng vào chuỗi SQL.
5. Dùng đúng tên bảng/cột vật lý trong SQL; `@Param` không thay thế mapping identifier.
6. Nếu bỏ `@Param`, bảo đảm compiler lưu tên tham số bằng `-parameters` và Spring Data có thể khám phá metadata.
7. Kiểm tra null, wildcard, collection và giới hạn database theo use case cụ thể.
8. Viết repository test trên database/dialect phù hợp.
9. Khi đổi placeholder, cập nhật annotation tương ứng trong cùng thay đổi.
10. Dùng custom repository với `NamedParameterJdbcOperations` khi query cần mức kiểm soát cao hơn `@Query`.

> **Named parameter giúp câu SQL diễn đạt rõ ý nghĩa của từng giá trị. `@Param("name")` liên kết tham số Java với placeholder `:name`; thông tin tên tham số trong bytecode có thể cho phép Spring Data khám phá tên mà không cần annotation, nhưng khai báo tường minh giúp repository contract ổn định và dễ đọc.**

### Tài liệu tham khảo

- [Spring Data JDBC — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): khai báo query tùy chỉnh trong repository JDBC.
- [Spring Data Commons — Repository Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): query methods và parameter binding.
- [Spring Data Commons — @Param API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/Param.html): annotation đặt tên tham số query.
- [Java Compiler — -parameters option](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): lưu tên tham số method/constructor vào class file.
- [Spring Framework — NamedParameterJdbcTemplate](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): named parameter khi sử dụng Spring JDBC trực tiếp.

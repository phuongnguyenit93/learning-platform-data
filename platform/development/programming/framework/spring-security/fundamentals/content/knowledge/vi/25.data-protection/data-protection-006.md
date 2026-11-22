# Kiểm tra dữ liệu đầu vào và truy vấn tham số hóa vẫn là trách nhiệm ứng dụng

> Phạm vi: bảo vệ dữ liệu trong ứng dụng Java 17+ dùng Spring Boot 3.x, Spring Security 6.x, Spring MVC và JDBC. Trọng tâm là **phân biệt bảo vệ truy cập với kiểm tra đầu vào và bảo vệ câu truy vấn**, thực hành Bean Validation, JDBC prepared statements, danh sách cho phép khi cấu trúc SQL cần thay đổi, cùng cách kiểm thử để giảm nguy cơ SQL injection. Spring Security là một lớp bảo vệ quan trọng nhưng **không tự kiểm tra tính hợp lệ của mọi tham số hoặc tự sửa những câu SQL mà ứng dụng xây dựng thiếu an toàn**.

## 1. Ba lớp kiểm soát khác nhau

Giả sử có API tìm khách hàng:

```http
GET /api/customers?nameContains=Ali&sort=NAME&limit=20
Authorization: Basic ...
```

Trước khi trả dữ liệu, ứng dụng phải giải quyết ba câu hỏi độc lập:

1. **Authentication và authorization — người gọi có được truy cập API không?** Spring Security kiểm tra credential, tạo `Authentication` và quyết định người gọi có role `READER` hay không. Không đăng nhập có thể bị yêu cầu xác thực; đã đăng nhập nhưng thiếu quyền có thể nhận HTTP 403.
2. **Input validation — dữ liệu được gửi có hợp lệ với hợp đồng API không?** `limit` phải là số trong khoảng cho phép; `sort` chỉ được nhận những tiêu chí hợp lệ; `nameContains` cần giới hạn độ dài. Những điều kiện này là trách nhiệm của ứng dụng, ở ranh giới nhận dữ liệu và ở tầng nghiệp vụ khi cần.
3. **Query safety — dữ liệu không đáng tin có thể thay đổi cú pháp truy vấn hay không?** Truy vấn SQL phải cố định cấu trúc, bind tham số bằng `PreparedStatement`/`JdbcTemplate` hoặc API tương đương. Nếu cho chọn tên cột sắp xếp, ứng dụng ánh xạ lựa chọn sang một tập từ khóa SQL **do mã nguồn định nghĩa**, không nối chuỗi do client gửi vào SQL.

Một request vượt qua kiểm tra `hasRole("READER")` **vẫn có thể chứa payload SQL injection hoặc dữ liệu sai kiểu**. Người dùng hợp lệ có thể cố ý gửi payload độc hại; ứng dụng cũng có thể nhận dữ liệu bẩn từ import, job, message queue hay dịch vụ khác. Không coi trạng thái “đã đăng nhập” là chứng chỉ tin cậy cho nội dung input.

| Cơ chế | Mục tiêu | Ví dụ | Chủ sở hữu chính |
| --- | --- | --- | --- |
| Spring Security authentication | Chứng minh danh tính | Mật khẩu HTTP Basic chính xác | Security filter, `AuthenticationManager`, provider |
| Spring Security authorization | Kiểm tra quyền | Chỉ `ROLE_READER` được gọi `GET /api/customers` | `SecurityFilterChain`, authorization policy |
| Bean Validation / request binding | Kiểm tra contract đầu vào | `1 <= limit <= 50`; `nameContains` dài tối đa 80 ký tự | Controller/DTO và validation boundary |
| Domain validation | Bảo vệ bất biến nghiệp vụ | Tổng tiền không âm; số lượng không vượt hạn mức | Service/domain |
| Parameterized SQL | Ngăn giá trị đầu vào trở thành mã SQL | `WHERE LOWER(name) LIKE LOWER(?)` | Repository/data access |
| Allow-list SQL identifiers | Hạn chế phần cú pháp không bind được | `NAME -> name ASC`, `CREATED -> created_at DESC` | Repository/query builder |
| Kiểm soát truy cập dữ liệu | Chỉ trả dòng thuộc tenant/chủ sở hữu được phép | `WHERE tenant_id = ?` với tenant tin cậy | Authorization + repository/data policy |

**Kết luận thiết kế:** Security filter quyết định *ai có quyền tiếp cận endpoint*; kiểm tra dữ liệu quyết định *input có hợp lệ*; tham số hóa quyết định *input được đưa vào SQL như giá trị dữ liệu, không phải mã lệnh*. Đây là các lớp bổ trợ, không thay thế nhau.

## 2. SQL injection xảy ra như thế nào?

SQL injection xuất hiện khi dữ liệu không đáng tin được **ghép vào cú pháp câu SQL**. Ví dụ dễ mắc lỗi dưới đây là **phản ví dụ**, không dùng trong ứng dụng thật:

```java
// Không an toàn: input của người dùng bị ghép vào cú pháp SQL.
String sql = "SELECT id, name FROM customers WHERE name = '"
        + nameFromRequest + "'";
List<CustomerRow> rows = jdbc.query(sql, rowMapper);
```

Nếu `nameFromRequest` là một chuỗi có dấu nháy và toán tử SQL, phần được ghép có thể thay đổi điều kiện `WHERE`, ví dụ:

```text
' OR '1'='1
```

Đoạn truy vấn dễ bị tổn thương có thể trở thành:

```sql
SELECT id, name FROM customers WHERE name = '' OR '1'='1'
```

Điều kiện `'1'='1'` luôn đúng; các bản ghi ngoài ý định có thể bị trả về. Hậu quả cụ thể phụ thuộc quyền database, câu truy vấn, dialect và môi trường; không phải mọi payload đều thực thi được, nhưng **không được xây dựng SQL theo cách có thể làm thay đổi cấu trúc bằng input**.

Cách đúng là giữ nguyên SQL và bind giá trị:

```java
String sql = "SELECT id, name FROM customers WHERE name = ?";
List<CustomerRow> rows = jdbc.query(sql, rowMapper, nameFromRequest);
```

Đây là **đoạn minh họa nằm trong repository**: `jdbc`, `rowMapper` và `nameFromRequest` cần được định nghĩa ở ngữ cảnh gọi. Dấu `?` là placeholder cho **giá trị**, không phải phép thay chuỗi văn bản trước khi chạy. `JdbcTemplate` sẽ sử dụng cơ chế tham số của JDBC cho lời gọi tương ứng. Lúc này chuỗi `' OR '1'='1` là **dữ liệu so sánh**, không biến thành mệnh đề SQL.

**Vì sao “lọc dấu nháy” không đủ?** Cách blacklist các ký tự như `'`, `;` hoặc từ khóa `SELECT` vừa dễ bỏ sót biến thể/encoding/dialect, vừa làm hỏng dữ liệu hợp lệ như tên `O'Reilly`. Prepared statements là hàng rào chính cho SQL **data values**. Input validation vẫn cần để bảo vệ contract, hiệu năng và business rules, nhưng **không được coi là thay thế cho bind parameters**.

## 3. Input validation: kiểm tra cái gì, ở đâu?

### 3.1. Kiểu dữ liệu, độ dài, phạm vi và tập giá trị

Các ví dụ:

- `limit` là số nguyên từ 1 đến 50 để giới hạn số bản ghi mỗi lần tìm.
- `nameContains` là chuỗi không vượt quá 80 ký tự; dấu nháy có thể là nội dung hợp lệ của tên, không mặc nhiên chặn chỉ vì nó giống một mảnh payload.
- `sort` phải thuộc một tập biết trước: `NAME` hoặc `CREATED`; tên cột SQL thực tế do ứng dụng tự chọn.
- Với API tạo mới khách hàng, `name` có thể phải `@NotBlank` và `@Size(max = 120)`; email có thể dùng `@NotBlank` cùng `@Email`. `@Email` chỉ kiểm tra hình thức, **không chứng minh địa chỉ email đang tồn tại hay người gửi sở hữu nó**.
- Giá tiền, ngày thanh toán và trạng thái quy trình còn cần domain validation ở service; input hợp lệ về cú pháp chưa chắc hợp lệ về nghiệp vụ.

Nếu người dùng gửi `limit=abc`, quá trình binding số nguyên sẽ thất bại trước khi truy vấn. Nếu gửi `limit=9999`, Bean Validation phải từ chối theo constraint `@Max(50)`. Nếu gửi `sort=PASSWORD`, lựa chọn không thuộc enum bị từ chối khi binding. Đây là những lỗi **request invalid**; không nên ném `AuthenticationException` để báo lỗi dữ liệu.

### 3.2. Bean Validation trên @ModelAttribute và @RequestBody

Spring Boot 3 dùng Jakarta Validation (`jakarta.validation.*`). Thêm `spring-boot-starter-validation` để có các constraint và implementation cần thiết.

- Đối với query/form parameters, một bean `@Valid @ModelAttribute SearchCriteria` cho phép Spring MVC bind và kiểm tra dữ liệu.
- Đối với JSON request body, dùng `@Valid @RequestBody CreateCustomerRequest` để kích hoạt kiểm tra object đã deserialize.
- `@NotNull` khác `@NotBlank`: `@NotNull` chỉ cấm `null`, còn `@NotBlank` yêu cầu chuỗi có nội dung không toàn khoảng trắng.
- `@Size` đo độ dài của chuỗi/collection; `@Min`/`@Max` giới hạn giá trị số; `@Pattern` biểu diễn cấu trúc chuỗi khi hợp đồng thực sự cần.
- Với input lồng nhau, cần `@Valid` ở thuộc tính nested để yêu cầu kiểm tra tiếp.
- Không dùng regex “chống SQL injection” cho mọi trường văn bản. Cho phép nội dung người dùng cần nhập và bảo vệ SQL tại tầng query.

Ví dụ minh họa cho một DTO dùng với POST:

```java
public record CreateCustomerRequest(
        @NotBlank @Size(max = 120) String name,
        @NotBlank @Email String email) {
}
```

Đoạn này không phải một phần của chương trình GET chạy ở mục 5; nó minh họa cách định nghĩa contract JSON. Nếu tạo POST thật, controller có thể nhận `@Valid @RequestBody CreateCustomerRequest request`, nhưng service vẫn phải kiểm tra quy tắc nghiệp vụ như email trùng, phân quyền ghi và xử lý transaction. Validation ở controller không bảo vệ các lối gọi service khác nếu domain invariant bị bỏ trống.

### 3.3. Không chỉ dữ liệu từ HTTP

Nguồn không đáng tin gồm query string, path variable, JSON body, HTTP header, file CSV/Excel nhập vào, message queue, database cũ, webhook và phản hồi dịch vụ đối tác. Việc một giá trị **đã được lưu trong database** không làm nó tự nhiên đáng tin khi được dùng để xây SQL động lần sau (second-order injection).

Nên áp dụng validation theo hai tầng:

1. **Boundary validation:** DTO/adapter kiểm tra format, kiểu, độ dài và các ràng buộc của API hoặc giao tiếp.
2. **Domain validation:** service/domain giữ các bất biến bắt buộc bất kể lời gọi đến từ REST, batch job, event consumer hay bài test.

Validation không có nghĩa luôn tự động “sanitize mọi đầu vào”. Đừng tự ý xóa ký tự hợp lệ hoặc âm thầm thay đổi ngữ nghĩa dữ liệu. Cách chuẩn hóa whitespace, Unicode và casing phải phù hợp yêu cầu nghiệp vụ, lưu trữ và tìm kiếm.

## 4. Truy vấn tham số hóa: điều làm được và giới hạn

### 4.1. JDBC, JdbcTemplate và NamedParameterJdbcTemplate

Với JDBC thô:

```java
String sql = "SELECT id, name FROM customers WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    try (ResultSet rs = ps.executeQuery()) {
        // Đọc ResultSet; không ghép customerId vào SQL.
    }
}
```

Đây là mảnh code cần `Connection`, `PreparedStatement`, `ResultSet` và `customerId` có sẵn. `PreparedStatement` là điểm chính: `setLong(1, customerId)` truyền **giá trị được bind** cho placeholder thứ nhất.

Với Spring JDBC:

```java
jdbc.query(
        "SELECT id, name FROM customers WHERE name = ?",
        rowMapper,
        nameFromRequest);
```

Với tham số đặt tên:

```java
String sql = "SELECT id, name FROM customers WHERE name = :name";
MapSqlParameterSource params =
        new MapSqlParameterSource("name", nameFromRequest);
namedJdbc.query(sql, params, rowMapper);
```

Hai đoạn Spring trên là **ví dụ repository**, yêu cầu biến và import tương ứng; `NamedParameterJdbcTemplate` hỗ trợ nhiều tham số có tên, dễ bảo trì khi câu query phức tạp. Dù dùng positional hay named binding, nguyên tắc là **SQL logic do mã ứng dụng kiểm soát, dữ liệu đầu vào luôn được bind**.

Spring Data JPA cũng cần nguyên tắc tương tự:

```java
@Query("select c from CustomerEntity c where c.email = :email")
List<CustomerEntity> findByEmail(@Param("email") String email);
```

Đây là chữ ký repository JPA minh họa, chỉ chạy trong dự án có entity/repository phù hợp; không phải mã độc lập. Tham số JPQL giúp không nối chuỗi email vào câu query. `EntityManager.createNativeQuery(...)` hoặc query string ghép thủ công từ input vẫn có thể chứa SQL injection dù ứng dụng dùng ORM.

### 4.2. Không bind tên cột, bảng hay từ khóa ORDER BY bằng dấu ?

Placeholder dùng cho **giá trị dữ liệu**, không phải cú pháp SQL:

```sql
-- Không có nghĩa là "sắp xếp theo cột người dùng chọn":
SELECT id, name FROM customers ORDER BY ?
```

Trong nhiều database, `ORDER BY ?` nếu được chấp nhận sẽ là một biểu thức giá trị, **không thay tên cột**. Tuyệt đối tránh `"ORDER BY " + sortFromRequest`.

Thay vào đó, ánh xạ input sang **đoạn SQL cố định, do ứng dụng sở hữu**:

```java
String orderBy = switch (sortField) {
    case NAME -> "name ASC, id ASC";
    case CREATED -> "created_at DESC, id ASC";
};
String sql = "SELECT id, name, created_at FROM customers ORDER BY "
        + orderBy
        + " LIMIT ?";
```

Đây là mảnh mã trong repository. `sortField` phải là enum hợp lệ, không phải chuỗi bất kỳ; `orderBy` chỉ có thể nhận một trong hai literal. Dù có nối chuỗi, dữ liệu không đáng tin **không được đưa thẳng vào cấu trúc SQL**. `LIMIT ?` vẫn bind như giá trị.

Tương tự, khi cần chọn tên bảng, cột, chiều sắp xếp `ASC`/`DESC`, toán tử hoặc phần query động, hãy dùng enum, allow-list hoặc query builder an toàn có kiểm soát; không coi prepared statements là cách “bind tất cả mọi loại token SQL”.

### 4.3. LIKE còn có wildcard: %, _ và escape

`LIKE` thường hiểu `%` là nhiều ký tự và `_` là đúng một ký tự. Bind parameter **ngăn sửa cú pháp SQL**, nhưng không tự làm cho `%` hay `_` trở thành chữ thường trong ngữ cảnh `LIKE`. Ví dụ người dùng muốn tìm tên có dấu gạch dưới đúng nghĩa, thì `nameContains=_` không nên trở thành “khớp với mọi tên có ít nhất một ký tự”.

Một chiến lược là dùng ký tự escape được quy định rõ trong câu SQL:

```sql
WHERE LOWER(name) LIKE LOWER(?) ESCAPE '!'
```

Và chuẩn bị pattern:

```java
static String literalContainsPattern(String raw) {
    String escaped = raw.replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
    return "%" + escaped + "%";
}
```

Ở đây `!` là escape character cho `LIKE`: `!%` biểu diễn dấu phần trăm literal, `!_` là gạch dưới literal và `!!` là ký tự chấm than literal. Cơ chế escape `LIKE` giải quyết **ngữ nghĩa tìm kiếm**, còn parameter binding giải quyết **SQL injection**. Một số dialect khác nhau về cú pháp `ESCAPE`; ví dụ chạy ở mục 5 dùng H2 có hỗ trợ cú pháp này.

### 4.4. IN, tìm kiếm phân trang và truy vấn nhiều tenant

Với tập ID, không viết `"... IN (" + idListFromClient + ")"`. Dùng `NamedParameterJdbcTemplate` có khả năng bind collection cho `IN (:ids)` hoặc tạo đúng số placeholder theo danh sách giới hạn, và xử lý trường hợp danh sách rỗng. Dữ liệu đầu vào vẫn cần giới hạn số phần tử.

Trong hệ thống nhiều tenant, parameterization **không tự giới hạn bản ghi thuộc tenant nào**. Ví dụ ý tưởng:

```sql
SELECT id, name FROM customers
WHERE tenant_id = ? AND LOWER(name) LIKE LOWER(?)
```

`tenant_id` phải được lấy từ ngữ cảnh danh tính/quyền đã xác thực và được hệ thống tin cậy, không mặc nhiên lấy từ query parameter tự khai. Thực thi least privilege cho tài khoản database, giới hạn dữ liệu trả về và dùng transaction/locking khi thao tác ghi để bảo vệ tính nhất quán.

## 5. Ví dụ Java 17+ chạy được: Spring Security + @Valid + JdbcTemplate

### 5.1. Chức năng và thiết kế

Ứng dụng cung cấp duy nhất endpoint đọc:

```http
GET /api/customers?nameContains=Ali&sort=NAME&limit=20
```

- Tài khoản `reader`/`reader-pass` có `ROLE_READER` được phép tìm khách hàng.
- Tài khoản `guest`/`guest-pass` có `ROLE_GUEST` đã xác thực nhưng không có quyền: 403.
- Anonymous hoặc sai credential: thường 401 theo HTTP Basic.
- `limit` nằm trong `1..50`; `nameContains` dài tối đa 80; `sort` chỉ `NAME` hoặc `CREATED`.
- SQL lọc tên qua bind parameter, limit được bind; `ORDER BY` đến từ enum allow-list.
- Tìm chuỗi có dấu nháy, `%` hoặc `_` không làm thay đổi logic query. Cách xử lý `LIKE` biến `%`/`_` thành ký tự literal của chuỗi tìm kiếm.
- Sử dụng H2 in-memory và các bản ghi demo; các API chỉ dùng GET nên không cần thay đổi cấu hình CSRF để thử bằng curl.

### 5.2. Khai báo dependency

Với dự án Spring Boot 3.x đã cấu hình Gradle plugin, phần `dependencies` của `build.gradle` cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **phần `dependencies`**, không phải toàn bộ Gradle build script. Dự án Maven sử dụng các starter tương ứng. Spring Boot auto-configure `DataSource` H2 trong bộ nhớ và `JdbcTemplate` khi các dependency này có sẵn.

### 5.3. File Java hoàn chỉnh

Tạo đúng `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Repository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demoData(JdbcTemplate jdbc) {
        return args -> {
            jdbc.execute(
                    "CREATE TABLE customers ("
                    + "id BIGINT PRIMARY KEY, "
                    + "name VARCHAR(120) NOT NULL, "
                    + "created_at TIMESTAMP NOT NULL)");

            jdbc.update(
                    "INSERT INTO customers(id, name, created_at) "
                    + "VALUES (?, ?, ?)",
                    1L, "Alice", Timestamp.valueOf("2025-02-01 10:00:00"));
            jdbc.update(
                    "INSERT INTO customers(id, name, created_at) "
                    + "VALUES (?, ?, ?)",
                    2L, "Bob", Timestamp.valueOf("2025-02-02 10:00:00"));
            jdbc.update(
                    "INSERT INTO customers(id, name, created_at) "
                    + "VALUES (?, ?, ?)",
                    3L, "O'Reilly Books",
                    Timestamp.valueOf("2025-02-03 10:00:00"));
            jdbc.update(
                    "INSERT INTO customers(id, name, created_at) "
                    + "VALUES (?, ?, ?)",
                    4L, "A_100", Timestamp.valueOf("2025-02-04 10:00:00"));
        };
    }
}

@Configuration
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password(encoder.encode("reader-pass"))
                        .roles("READER")
                        .build(),
                User.withUsername("guest")
                        .password(encoder.encode("guest-pass"))
                        .roles("GUEST")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/customers")
                        .hasRole("READER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

enum SortField {
    NAME,
    CREATED
}

class CustomerSearch {
    @Size(max = 80)
    private String nameContains = "";

    @NotNull
    @Min(1)
    @Max(50)
    private Integer limit = 20;

    @NotNull
    private SortField sort = SortField.NAME;

    public CustomerSearch() {
    }

    public String getNameContains() {
        return nameContains;
    }

    public void setNameContains(String nameContains) {
        this.nameContains = nameContains;
    }

    public Integer getLimit() {
        return limit;
    }

    public void setLimit(Integer limit) {
        this.limit = limit;
    }

    public SortField getSort() {
        return sort;
    }

    public void setSort(SortField sort) {
        this.sort = sort;
    }
}

record CustomerRow(long id, String name, LocalDateTime createdAt) {
}

@Repository
class CustomerRepository {
    private final JdbcTemplate jdbc;

    CustomerRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    List<CustomerRow> search(CustomerSearch request) {
        String orderBy = switch (request.getSort()) {
            case NAME -> "name ASC, id ASC";
            case CREATED -> "created_at DESC, id ASC";
        };

        String needle = request.getNameContains() == null
                ? ""
                : request.getNameContains().strip();
        String pattern = literalContainsPattern(needle);

        String sql = "SELECT id, name, created_at "
                + "FROM customers "
                + "WHERE LOWER(name) LIKE LOWER(?) ESCAPE '!' "
                + "ORDER BY " + orderBy + " LIMIT ?";

        return jdbc.query(
                sql,
                (rs, rowNum) -> new CustomerRow(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getTimestamp("created_at").toLocalDateTime()),
                pattern,
                request.getLimit());
    }

    private static String literalContainsPattern(String raw) {
        String escaped = raw.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
        return "%" + escaped + "%";
    }
}

@RestController
class CustomerController {
    private final CustomerRepository repository;

    CustomerController(CustomerRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/api/customers")
    List<CustomerRow> search(@Valid @ModelAttribute CustomerSearch criteria) {
        return repository.search(criteria);
    }
}
```

**Tại sao đây là chương trình chạy được:** một file chứa lớp `public DemoApplication` đúng tên; các lớp/enum/record khác cùng package `demo` và không khai báo `public`. `@SpringBootApplication` quét cùng package để tạo bean security/controller/repository. `CommandLineRunner` tạo bảng và bốn hàng dữ liệu khi ứng dụng khởi động trên H2 in-memory mới. `LocalDateTime` và `record` được Java 17 hỗ trợ.

**Chia trách nhiệm trong mã:**

- `SecurityConfig` xác thực HTTP Basic và bảo vệ URL bằng `hasRole("READER")`. Role này tương ứng authority `ROLE_READER`, được tạo từ tài khoản phía server.
- `CustomerSearch` mô tả contract query: tên tìm kiếm, limit và lựa chọn sort. Spring MVC bind vào bean, `@Valid` chạy Jakarta Bean Validation; lỗi kiểu và constraint thường tạo HTTP 400.
- `CustomerController` chỉ nhận DTO hợp lệ rồi gọi repository, không tự nối SQL hoặc giải mã mật khẩu.
- `CustomerRepository` tạo cấu trúc SQL tĩnh, bind `pattern` và `limit`, chỉ nối `orderBy` được tạo từ enum. Dữ liệu người dùng không được ghép thẳng vào query.
- `literalContainsPattern` giải quyết wildcard theo yêu cầu “contains literal”, không phải cách chống SQL injection. SQL injection được ngăn bằng các placeholder và JDBC binding.

**Giới hạn minh họa:** app demo dùng in-memory database, vài tài khoản mẫu trong code và BCrypt khởi tạo khi chạy. Production cần kho người dùng bền vững, xác thực qua HTTPS, kiểm soát quyền từng tenant/từng đối tượng, pool/timeout, giám sát và quản lý thông tin nhạy cảm. API tìm kiếm có thể cần pagination bằng cursor thay vì offset và chỉ trả các trường thật sự cần thiết.

### 5.4. Chạy trên máy và quan sát

Với Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Khi Boot lắng nghe tại `http://localhost:8080` (nếu chưa thay `server.port`), dùng curl trong terminal khác:

```bash
# Không credential: thường 401, có WWW-Authenticate Basic.
curl -i "http://localhost:8080/api/customers"

# Đã xác thực nhưng thiếu quyền READER: 403.
curl -i -u guest:guest-pass "http://localhost:8080/api/customers"

# Reader hợp lệ, tìm Alice: 200, một bản ghi.
curl -i -u reader:reader-pass \
  "http://localhost:8080/api/customers?nameContains=Ali&sort=NAME&limit=20"

# Input limit sai contract: 400, không chạy query như yêu cầu hợp lệ.
curl -i -u reader:reader-pass \
  "http://localhost:8080/api/customers?limit=999"

# Trường sắp xếp không thuộc enum: 400 do binding thất bại.
curl -i -u reader:reader-pass \
  "http://localhost:8080/api/customers?sort=UNSAFE"

# Dấu nháy đơn là dữ liệu, không phải cú pháp query: tìm O'Reilly.
curl -i -u reader:reader-pass -G \
  --data-urlencode "nameContains=O'Reilly" \
  "http://localhost:8080/api/customers"

# Chuỗi trông giống SQL injection vẫn là giá trị đã bind.
curl -i -u reader:reader-pass -G \
  --data-urlencode "nameContains=' OR 1=1 --" \
  "http://localhost:8080/api/customers"

# Gạch dưới được tìm như ký tự literal.
curl -i -u reader:reader-pass -G \
  --data-urlencode "nameContains=_" \
  "http://localhost:8080/api/customers"
```

Trong PowerShell, dùng `curl.exe` nếu `curl` là alias của `Invoke-WebRequest`. Các dòng kết thúc bằng `\` là cú pháp tiếp dòng của Bash; để chạy trong PowerShell, đặt mỗi lệnh `curl.exe` trên một dòng, hoặc dùng dấu tiếp dòng phù hợp.

| Yêu cầu | HTTP kỳ vọng | Kết quả/ý nghĩa |
| --- | --- | --- |
| Không credential | 401 | Spring Security yêu cầu authentication |
| `guest:guest-pass` | 403 | Credential đúng nhưng thiếu `ROLE_READER` |
| `reader` và `nameContains=Ali` | 200 | JSON array chứa `Alice` |
| `reader` và `limit=999` | 400 | `@Max(50)` từ chối input |
| `reader` và `sort=UNSAFE` | 400 | Không chuyển được sang enum `SortField` |
| `reader` tìm `O'Reilly` | 200 | Trả `O'Reilly Books`; dấu nháy không đổi cú pháp SQL |
| `reader` với chuỗi `' OR 1=1 --` | 200 | JSON array rỗng `[]`; không mở rộng kết quả thành toàn bộ bảng |
| `reader` tìm `_` | 200 | Trả `A_100` nhờ escape wildcard của `LIKE` |

Ví dụ body rút gọn cho `nameContains=Ali` (cấu trúc JSON thực tế chứa thêm `id` và `createdAt`):

```json
[
  {
    "id": 1,
    "name": "Alice",
    "createdAt": "2025-02-01T10:00:00"
  }
]
```

HTTP status/body có thể khác nếu bạn thêm handler, thay đổi cấu hình Spring Security hoặc có lỗi hạ tầng. Dữ liệu trong bảng được tạo bởi `CommandLineRunner` và chỉ tồn tại trong H2 demo, nên các kết quả trên phụ thuộc việc chạy đúng ứng dụng này.

## 6. Kiểm thử: chứng minh cả ba hàng rào hoạt động

Test tốt không chỉ gửi payload SQL injection và mong không thấy lỗi SQL. Cần kiểm tra song song: authentication/authorization, giới hạn input, an toàn query và ngữ nghĩa tìm kiếm literal.

Tạo file `src/test/java/demo/CustomerApiTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CustomerApiTest {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousIsNotAllowed() throws Exception {
        mvc.perform(get("/api/customers"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedGuestLacksRole() throws Exception {
        mvc.perform(get("/api/customers")
                        .with(httpBasic("guest", "guest-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void readerCanSearchAlice() throws Exception {
        mvc.perform(get("/api/customers")
                        .with(httpBasic("reader", "reader-pass"))
                        .param("nameContains", "Ali"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].name").value("Alice"));
    }

    @Test
    void limitOutsideRangeIsRejected() throws Exception {
        mvc.perform(get("/api/customers")
                        .with(httpBasic("reader", "reader-pass"))
                        .param("limit", "999"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void sortOutsideAllowListIsRejected() throws Exception {
        mvc.perform(get("/api/customers")
                        .with(httpBasic("reader", "reader-pass"))
                        .param("sort", "UNSAFE"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void quotesAreBoundAsData() throws Exception {
        mvc.perform(get("/api/customers")
                        .with(httpBasic("reader", "reader-pass"))
                        .param("nameContains", "' OR 1=1 --"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isEmpty());
    }

    @Test
    void likeUnderscoreIsLiteral() throws Exception {
        mvc.perform(get("/api/customers")
                        .with(httpBasic("reader", "reader-pass"))
                        .param("nameContains", "_"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].name").value("A_100"));
    }
}
```

Chạy:

```bash
./gradlew test
```

- Kiểm thử 401/403 xác nhận Spring Security đã được kết nối đúng với endpoint; chúng **không chứng minh** SQL được parameterize.
- Kiểm thử 400 chứng minh DTO validation/binding từ chối tham số ngoài contract; chúng **không chứng minh** SQL injection được chặn trong mọi nhánh.
- Kiểm thử với chuỗi có dấu nháy và wildcard chứng minh cách query này không biến input thành cú pháp SQL và giữ đúng ngữ nghĩa tìm kiếm.
- Trong code review, vẫn cần kiểm tra mọi câu SQL/raw query, đặc biệt truy vấn động, stored procedure có dynamic SQL, entity manager tự ghép chuỗi và các đường nhập dữ liệu ngoài HTTP.
- Khi bảo vệ dữ liệu nhạy cảm, thêm integration test với tenant A/B để bảo đảm role hợp lệ **không thể xem dữ liệu tenant khác**, kể cả khi ID được đoán đúng.

## 7. Sai lầm phổ biến và cách xử lý

### 7.1. “Có Spring Security rồi thì API đã an toàn trước SQL injection”

Sai. Spring Security chịu trách nhiệm đáng kể cho authentication, authorization, headers và các bảo vệ web; nó **không tự động phân tích và thay thế mọi SQL nguy hiểm** do ứng dụng viết. Một người dùng có quyền gọi API vẫn có thể gửi `nameContains` chứa SQL metacharacters. Repository phải parameterize.

### 7.2. “Đã validate chỉ cho chữ và số thì không cần PreparedStatement”

Sai. Blacklist/regex không phải cách chắc chắn ngăn SQL injection; nhiều trường hợp nghiệp vụ thực tế cần dấu nháy, Unicode, dấu câu. Bên cạnh đó, dữ liệu có thể đi vào SQL từ nguồn khác chưa qua cùng validator. Bind mọi **data value** theo API tương ứng dù dữ liệu có vẻ an toàn.

### 7.3. “Dùng ORM/JPA thì không thể có SQL injection”

Sai. Các method query an toàn của ORM giảm rủi ro nhưng JPQL/native SQL được ghép từ dữ liệu không đáng tin vẫn có thể bị injection. Dùng query parameters cho values, query builder có cấu trúc và allow-list cho phần cú pháp dynamic. Không biến một chuỗi request thành JPQL/SQL thô.

### 7.4. “Có PreparedStatement là đủ để thay tên cột”

Sai. Tên cột, bảng, keyword và SQL fragments không phải data values. `ORDER BY ?` không chọn cột từ input như mong muốn. Với phần cấu trúc cần chọn, ánh xạ lựa chọn thành literal trong code, hoặc dùng API builder có kiểm soát; từ chối trường hợp không thuộc allow-list.

### 7.5. “Dùng LIKE ? thì dấu % và _ được xử lý như chữ thường”

Sai về ngữ nghĩa tìm kiếm. Bind parameters bảo vệ cú pháp SQL nhưng `%`, `_` vẫn là wildcard của `LIKE`. Escape pattern khi contract yêu cầu substring literal, như ví dụ `ESCAPE '!'`; nếu contract cho phép wildcard, hãy định nghĩa và giới hạn hành vi ấy một cách rõ ràng.

### 7.6. “Validation ở frontend là đủ”

Sai. Client có thể bỏ qua UI, thay request, hoặc truy cập API qua script. Cần validation trên server; đồng thời giữ domain invariants trong service/domain để các luồng khác (batch, job, events) không bypass.

### 7.7. “Request có role là truy vấn nào cũng được”

Sai. Role `READER` trong ví dụ chỉ minh họa quyền **vào endpoint**. Nếu database thực tế lưu nhiều tenant hoặc hồ sơ riêng, mỗi truy vấn còn phải áp dụng chính sách ownership/tenant từ nguồn tin cậy. SQL an toàn về cú pháp vẫn có thể **rò rỉ dữ liệu do thiếu điều kiện phân quyền**.

### 7.8. “Escape HTML là cách chống SQL injection”

Sai tầng bảo vệ. Output encoding/HTML escaping xử lý rủi ro khi hiển thị dữ liệu trong HTML; nó không thay thế prepared statements. Tương tự, mã hóa password không sửa lỗi SQL, và kiểm tra CSRF không thay thế validate body. Mỗi rủi ro có cơ chế tương ứng.

### 7.9. “Một lỗi input thì trả 401/403”

Không nên trộn loại lỗi:

| Trường hợp | HTTP thường gặp | Nhóm trách nhiệm |
| --- | --- | --- |
| Chưa gửi credential khi endpoint yêu cầu | 401 với HTTP Basic | Authentication |
| Credential đúng nhưng thiếu role | 403 | Authorization |
| `limit` ngoài 1..50, sort không hợp lệ | 400 | Binding/validation |
| Request hợp lệ nhưng vi phạm bất biến domain | 400/409/422 tùy contract | Business |
| Tài nguyên không tồn tại sau kiểm tra quyền | 404 | Domain/data |
| DB unavailable hoặc lỗi lập trình | 5xx phù hợp; ghi log server | Hạ tầng/vận hành |

HTTP 400 không phải “đã ngăn mọi injection”, và HTTP 200 với array rỗng không tự đủ chứng minh toàn bộ ứng dụng an toàn; phải kiểm tra cách SQL được xây dựng.

## 8. Nâng chuẩn khi áp dụng vào hệ thống thực tế

1. **Schema và DTO:** xác định contract API rõ, giới hạn độ dài, số phần tử, kiểu, range, tập lựa chọn; dùng validation groups khi thực sự có nhiều ngữ cảnh, tránh tạo cấu hình quá phức tạp.
2. **Nhất quán giữa boundary và domain:** dữ liệu đi từ REST, messaging, import hay batch đều phải qua domain rules quan trọng; không coi `@Valid` trong controller là hàng rào duy nhất.
3. **Truy vấn:** code review tất cả `JdbcTemplate`, `NamedParameterJdbcTemplate`, JPA/JPQL, native query, stored procedure có dynamic SQL; bind values và allow-list identifiers.
4. **Giới hạn hiệu năng:** có `LIMIT` phù hợp, giới hạn filter và độ dài pattern; dùng index/plan theo nhu cầu. Query `LIKE '%term%'` có thể tốn chi phí quét bảng lớn; rate limit/timeout và chiến lược tìm kiếm cần phù hợp quy mô.
5. **Quyền dữ liệu:** xác thực caller, kiểm tra role/scope, lấy tenant/owner từ principal đã xác minh và enforce tại policy/query. Database account chỉ nên có quyền tối thiểu.
6. **Lỗi và nhật ký:** phản hồi validation đủ rõ cho người dùng nhưng không lộ câu SQL, stack trace, password hoặc bản ghi nhạy cảm. Log kỹ thuật dùng mã lỗi/correlation id và dữ liệu đã giảm nhạy cảm.
7. **Lưu trữ và xuất dữ liệu:** mã hóa dữ liệu nhạy cảm khi cần, quản lý secret, lưu audit, không trả toàn bộ cột/đối tượng entity nếu API chỉ cần vài trường; parameterization không thay thế kiểm soát dữ liệu xuất ra.
8. **Kiểm thử ở đúng tầng:** unit test validator/query builder, integration test SQL với H2 hoặc database thật theo yêu cầu, test truy cập nhiều tenant, fuzz input và kiểm thử công cụ bảo mật khi phù hợp.
9. **Tránh bỏ bảo vệ khác:** CSRF, CORS, authorization và HTML output encoding bảo vệ các đường khác nhau; không tắt/hoán đổi vì input validation hay SQL binding.

## 9. Bài tập tự kiểm tra

1. Người dùng có `ROLE_READER` và gửi chuỗi `' OR 1=1 --`. Spring Security có tự xóa hoặc chặn chuỗi này không? Thành phần nào phải bảo đảm chuỗi vẫn là **data value** của SQL?
2. Vì sao `@Size(max = 80)` chưa đủ để ngăn SQL injection, và vì sao prepared statement không kiểm tra `limit <= 50`?
3. Tại sao `ORDER BY ?` không thay thế được ánh xạ `SortField.NAME -> "name ASC"`? Khi nào phép nối chuỗi trong SQL có thể được chấp nhận?
4. Nếu API muốn tìm khách hàng tên `A_100` theo substring literal, `LIKE ?` có tự hiểu dấu `_` là gạch dưới không? Cách sửa?
5. Một user đăng nhập hợp lệ và gọi API lấy hồ sơ của tenant khác. Query dùng placeholder cho tất cả giá trị nhưng vẫn trả hồ sơ ấy. Rủi ro nằm ở SQL injection hay authorization?
6. `CreateCustomerRequest` có `@Email` và `@NotBlank`. Hai annotation này có bảo đảm email duy nhất, tồn tại và đã được người dùng xác minh không? Điều kiện nào thuộc domain/verification?
7. Data được lấy từ một bảng nội bộ trước đó rồi ghép vào một query dynamic. Vì sao vẫn có thể xảy ra second-order injection?
8. Nếu client gửi `sort=UNSAFE`, tầng nào nên từ chối? Nếu client gửi `limit=999`, tầng nào chịu trách nhiệm?
9. Bạn sẽ thêm những test nào để chứng minh đồng thời quyền truy cập, validation contract, parameterized SQL, LIKE escape và lọc theo tenant?

**Định hướng:** (1) Spring Security không thay thế query builder, bind ở repository; (2) validation và parameterization giải quyết rủi ro khác nhau; (3) placeholder chỉ đại diện values, phần cấu trúc lấy từ allow-list; (4) cần escape wildcard khi contract yêu cầu literal; (5) thiếu row-level/tenant authorization; (6) cần domain uniqueness và verification; (7) dữ liệu từng lưu vẫn có thể trở thành untrusted input khi ghép query; (8) binding/Bean Validation, không phải authentication; (9) viết các test đối lập cho từng hàng rào.

## Tài liệu chính thức và hướng dẫn bảo mật

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — JDBC Core và JdbcTemplate](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — NamedParameterJdbcTemplate](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html)
- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet)
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
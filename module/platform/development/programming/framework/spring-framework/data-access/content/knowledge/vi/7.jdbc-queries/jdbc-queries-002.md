# Truy vấn một đối tượng và yêu cầu về số hàng, số cột

## 1. Bài học giải quyết vấn đề gì?

Khi truy vấn cơ sở dữ liệu bằng **Spring JDBC**, câu hỏi “lấy một đối tượng” có thể mang nhiều ý nghĩa:

- Chắc chắn phải tìm thấy **đúng một hàng** (ví dụ: đọc đơn hàng bằng khóa chính đã được xác thực).
- Có thể tìm thấy **không hoặc một hàng** (ví dụ: tìm sản phẩm theo mã; không tồn tại là kết quả bình thường).
- Cần một **giá trị đơn** từ **một hàng, một cột** (ví dụ: `COUNT(*)`, tên sản phẩm hoặc giá).
- Cần một **object có nhiều thuộc tính**, ánh xạ từ **một hàng gồm nhiều cột**.

Các nhu cầu này **không tương đương**. Đặc biệt, `JdbcTemplate.queryForObject(...)` là API có ràng buộc về số hàng; biến thể nhận `Class<T>` còn có ràng buộc về số cột.

Mục tiêu sau bài học:

1. Phân biệt hai chiều của `ResultSet`: **số hàng** (cardinality) và **số cột** (shape).
2. Dùng đúng `queryForObject(sql, Class<T>, args...)`, `queryForObject(sql, RowMapper<T>, args...)` và `query(sql, RowMapper<T>, args...)`.
3. Phân biệt **không có hàng**, **một hàng chứa SQL NULL**, **nhiều hàng**, **nhiều cột** và **không ánh xạ được kiểu Java**.
4. Hiểu và xử lý `EmptyResultDataAccessException`, `IncorrectResultSizeDataAccessException`, `IncorrectResultSetColumnCountException` theo hợp đồng nghiệp vụ.
5. Áp dụng `Optional<T>` cho truy vấn có thể thiếu; bảo vệ tính duy nhất bằng constraint thay vì “lấy đại hàng đầu tiên”.
6. Viết, chạy và kiểm thử ví dụ Spring Boot/JDBC theo Java 17+ với kết quả xác định.

Đây là bài về **truy vấn JDBC**: trọng tâm là ý nghĩa hợp đồng dữ liệu của truy vấn, API mapping và ngoại lệ. Những lựa chọn HTTP, JPA hoặc transaction nâng cao chỉ được nhắc khi ảnh hưởng trực tiếp đến cách dùng kết quả.

## 2. Hai chiều của kết quả: hàng và cột

Một truy vấn SQL trả về `ResultSet` có **số hàng** và tập **cột** đã chọn. Ví dụ:

```sql
SELECT id, sku, name
FROM products
WHERE id = 10;
```

Nếu `id` là khóa chính và hàng tồn tại, kết quả có **một hàng, ba cột**. Đây là một đối tượng sản phẩm, nhưng **không** phải một giá trị scalar của một cột.

```sql
SELECT name
FROM products
WHERE id = 10;
```

Kết quả này có **một hàng, một cột**. Nó phù hợp để ánh xạ thành `String`.

| Hình dạng kết quả | Ý nghĩa | API gợi ý |
| --- | --- | --- |
| 0 hàng, một hay nhiều cột đã định nghĩa | Không có bản ghi thỏa điều kiện | `query(...).isEmpty()` / `Optional.empty()` nếu việc thiếu là hợp lệ |
| 1 hàng × 1 cột | Một giá trị đơn như tên, tổng đếm, giá | `queryForObject(sql, String.class, ...)` hoặc kiểu cần thiết |
| 1 hàng × nhiều cột | Một object gồm nhiều thuộc tính | `queryForObject(sql, rowMapper, ...)` |
| Nhiều hàng × 1 cột | Danh sách các giá trị cùng kiểu | `queryForList(sql, String.class, ...)` hoặc `query` với mapper |
| Nhiều hàng × nhiều cột | Danh sách object | `query(sql, rowMapper, ...)` |
| 1 hàng × 1 cột SQL NULL | **Có hàng**, giá trị của cột là NULL | `queryForObject(..., Class<T>, ...)` có thể trả Java `null` |

**Quan trọng:** “một object” trong ngôn ngữ lập trình **không có nghĩa** SQL chỉ được trả một cột. `RowMapper<Product>` có thể đọc sáu cột của một hàng để tạo một đối tượng `Product`.

Hình dung bằng ma trận:

```text
SELECT name FROM products WHERE id = 10
+----------------+
| name           |  1 hàng x 1 cột
+----------------+
| Java căn bản   |
+----------------+

SELECT id, sku, name FROM products WHERE id = 10
+----+-----------+---------------+
| id | sku       | name          |  1 hàng x 3 cột
+----+-----------+---------------+
| 10 | BOOK-JAVA | Java căn bản  |
+----+-----------+---------------+

SELECT id, name FROM products WHERE name = 'Java căn bản'
+----+---------------+
| id | name          |  2 hàng x 2 cột
+----+---------------+
| 10 | Java căn bản  |
| 30 | Java căn bản  |
+----+---------------+
```

## 3. Hai overload queryForObject cần nhớ

### 3.1. queryForObject(sql, requiredType, args...): đúng một hàng, đúng một cột

Với Spring Framework 6.x, dạng dùng phổ biến là:

```java
<T> T queryForObject(String sql, Class<T> requiredType, Object... args)
```

Ví dụ:

```java
String name = jdbcTemplate.queryForObject(
        "SELECT name FROM products WHERE id = ?",
        String.class,
        10L
);

Long total = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM products",
        Long.class
);
```

Trong ví dụ này, `jdbcTemplate` là bean `JdbcTemplate` được cấu hình từ `DataSource`; các lệnh cần bảng `products` tương ứng.

Hợp đồng thực tế:

- Kết quả phải có **chính xác một hàng**. Nếu không có hàng, phương thức ném `EmptyResultDataAccessException`, là lớp con của `IncorrectResultSizeDataAccessException`.
- Nếu có **hơn một hàng**, ném `IncorrectResultSizeDataAccessException`.
- Với hàng được đọc, truy vấn phải có **chính xác một cột**. Nếu có nhiều cột, ném `IncorrectResultSetColumnCountException`.
- Giá trị được chuyển sang `requiredType` theo khả năng của `SingleColumnRowMapper`/conversion và JDBC driver. Không phải mọi kiểu SQL đều chuyển được sang mọi `Class<T>`.
- Nếu hàng tồn tại nhưng cột chứa **SQL NULL**, giá trị Java được trả có thể là `null`, chứ **không** phải `EmptyResultDataAccessException`.

Hình dạng cột không tự thu hẹp vì bạn yêu cầu `String.class`. Nếu viết:

```java
String wrong = jdbcTemplate.queryForObject(
        "SELECT name, price FROM products WHERE id = ?",
        String.class,
        10L
);
```

thì không có quy tắc “lấy cột đầu tiên”: khi hàng được ánh xạ, Spring phát hiện hai cột và ném `IncorrectResultSetColumnCountException`.

Dạng `queryForObject(String sql, Class<T> requiredType, Object... args)` còn giúp bind parameter với `PreparedStatement`, tránh ghép giá trị user vào SQL. Không cần tự tạo `Connection` hay đóng `ResultSet` khi dùng `JdbcTemplate` theo đường gọi thông thường.

### 3.2. queryForObject(sql, rowMapper, args...): đúng một hàng, có thể nhiều cột

Dạng thứ hai:

```java
<T> T queryForObject(
        String sql, RowMapper<T> rowMapper, Object... args
)
```

Ví dụ `Product` được ánh xạ từ sáu cột:

```java
Product product = jdbcTemplate.queryForObject(
        """
        SELECT id, sku, name, price, description, active
        FROM products
        WHERE id = ?
        """,
        (rs, rowNum) -> new Product(
                rs.getLong("id"),
                rs.getString("sku"),
                rs.getString("name"),
                rs.getBigDecimal("price"),
                rs.getString("description"),
                rs.getBoolean("active")
        ),
        10L
);
```

`RowMapper` có thể lấy nhiều cột tùy ý, miễn SQL thật sự trả các cột cần thiết. Bất biến của `queryForObject` **vẫn là đúng một hàng**: 0 hàng ném `EmptyResultDataAccessException`; từ 2 hàng trở lên ném `IncorrectResultSizeDataAccessException`.

Trong JDBC, `rowNum` là chỉ số hàng khi mapper được gọi, bắt đầu từ 0. Nó không phải khóa chính và thường không cần để ánh xạ một object.

**Cạm bẫy:** trả `null` từ chính `RowMapper` làm `queryForObject` có thể trả `null` dù SQL đã trả một hàng. Hãy thiết kế mapper trả đối tượng hợp lệ hoặc ném lỗi rõ ràng. Không dùng `null` từ mapper để ngầm biểu thị “không có hàng”.

### 3.3. Không nhầm overload cũ

Bạn có thể gặp mã cũ:

```java
// Kiểu overload với Object[] đứng trước requiredType
// đã bị đánh dấu deprecated trong các phiên bản Spring 6.x.
jdbcTemplate.queryForObject(
        "SELECT name FROM products WHERE id = ?",
        new Object[] {10L},
        String.class
);
```

Với mã mới, ưu tiên đặt `requiredType` hoặc `RowMapper` trước các tham số bind như hai ví dụ đầu. Điều này giảm nhầm lẫn giữa overload và phù hợp tài liệu Spring Framework 6.x.

## 4. Bảng hành vi: 0, 1, nhiều hàng và 1, nhiều cột

Giả sử các truy vấn được thực thi bình thường, SQL đúng, kiểu Java phù hợp:

| Phương thức | 0 hàng | 1 hàng, 1 cột | 1 hàng, nhiều cột | Nhiều hàng |
| --- | --- | --- | --- | --- |
| `queryForObject(sql, Class<T>, args...)` | `EmptyResultDataAccessException` | Giá trị kiểu `T` hoặc `null` nếu SQL NULL | `IncorrectResultSetColumnCountException` khi mapper đọc hàng | `IncorrectResultSizeDataAccessException` |
| `queryForObject(sql, RowMapper<T>, args...)` | `EmptyResultDataAccessException` | Mapper tạo `T` | Mapper có thể dùng tất cả cột để tạo `T` | `IncorrectResultSizeDataAccessException` |
| `queryForMap(sql, args...)` | `EmptyResultDataAccessException` | Map 1 cặp key/value | Map cho các cột của **một** hàng | `IncorrectResultSizeDataAccessException` |
| `query(sql, RowMapper<T>, args...)` | `List.empty()` | Danh sách một object | Danh sách một object được map từ nhiều cột | Danh sách các object |
| `queryForList(sql, Class<T>, args...)` | Danh sách rỗng | Danh sách một scalar | Không phù hợp mapper một cột nếu có hàng | Danh sách scalar nếu mỗi hàng có một cột |

Bảng này là **hợp đồng API**, không phải bảng mã lỗi SQLSTATE của riêng PostgreSQL. `JdbcTemplate` dịch các lỗi JDBC cần thiết sang hệ `DataAccessException` của Spring; các ngoại lệ kiểm tra số hàng/cột ở trên phát sinh khi xử lý kết quả.

Về quan hệ kế thừa:

```text
DataAccessException
  +-- IncorrectResultSizeDataAccessException
  |     +-- EmptyResultDataAccessException
  +-- DataRetrievalFailureException
        +-- IncorrectResultSetColumnCountException
```

Chú ý `IncorrectResultSetColumnCountException` **không** là lớp con của `IncorrectResultSizeDataAccessException`. Nếu muốn log/chẩn đoán riêng lỗi sai số cột, đừng chỉ catch `IncorrectResultSizeDataAccessException`.

## 5. Dữ liệu mẫu: tự chạy được trên PostgreSQL

Tạo bảng trong **database học tập trống**. Lược đồ giữ ID cố định để minh họa ra kết quả xác định:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(60) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    description VARCHAR(250),
    active BOOLEAN NOT NULL
);

INSERT INTO products (id, sku, name, price, description, active)
VALUES
    (10, 'BOOK-JAVA', 'Java căn bản', 125000.00, NULL, TRUE),
    (20, 'BOOK-SPRING', 'Spring JDBC', 199000.00, 'Thực hành', TRUE),
    (30, 'BOOK-ADV', 'Java căn bản', 155000.00, NULL, FALSE);
```

Từ dữ liệu này, các trường hợp có kết quả xác định:

| SQL | Số hàng | Số cột | Giá trị / điểm quan trọng |
| --- | ---: | ---: | --- |
| `SELECT name FROM products WHERE id = 10` | 1 | 1 | `Java căn bản` |
| `SELECT id, sku, name FROM products WHERE id = 10` | 1 | 3 | Một hàng ánh xạ thành object |
| `SELECT name FROM products WHERE id = 999` | 0 | 1 | Không có hàng; không phải SQL NULL |
| `SELECT description FROM products WHERE id = 10` | 1 | 1 | Giá trị cột `NULL` |
| `SELECT id FROM products WHERE name = 'Java căn bản'` | 2 | 1 | Hai hàng, vì `name` không unique |
| `SELECT COUNT(*) FROM products WHERE id = 999` | 1 | 1 | Số `0` |
| `SELECT COUNT(*) FROM products WHERE active = TRUE` | 1 | 1 | Số `2` |
| `SELECT SUM(price) FROM products WHERE id = 999` | 1 | 1 | SQL `NULL` |
| `SELECT COUNT(*) FROM products GROUP BY active` | 2 | 1 | Hai nhóm: active và inactive |

Tất cả các truy vấn trên đều là SQL PostgreSQL hợp lệ theo schema đã nêu.

### 5.1. Không tìm thấy hàng khác hoàn toàn với tìm thấy NULL

Hai trường hợp sau nhìn có thể giống nhau trong Java nếu không phân biệt:

```sql
-- Không có sản phẩm id 999: 0 hàng.
SELECT description FROM products WHERE id = 999;

-- Có sản phẩm id 10, nhưng description là NULL: 1 hàng, 1 cột NULL.
SELECT description FROM products WHERE id = 10;
```

Đối với `jdbcTemplate.queryForObject(sql, String.class, id)`, trường hợp thứ nhất ném `EmptyResultDataAccessException`; trường hợp thứ hai trả `null`. Do đó không nên giả định “nhận null” luôn nghĩa là sản phẩm không tồn tại.

Nếu nghiệp vụ muốn biểu diễn hai trạng thái, có thể truy vấn **cả ID lẫn description** bằng một `RowMapper` tạo object, ví dụ `ProductDescription(long id, String description)`; khi đó `Optional<ProductDescription>` thể hiện hàng có/không, còn trường `description` có thể null khi hàng tồn tại.

### 5.2. COUNT(*) khác SELECT một bản ghi

```sql
SELECT COUNT(*) FROM products WHERE id = 999;
```

`COUNT(*)` không có `GROUP BY` thường trả **một hàng, một cột** chứa `0` ngay khi không có bản ghi thỏa điều kiện. Vì vậy:

```java
Long count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM products WHERE id = ?",
        Long.class, 999L
);
// count == 0L; không ném EmptyResultDataAccessException.
```

Trong PostgreSQL, `COUNT(*)` trả kiểu `BIGINT` nên `Long.class` là lựa chọn an toàn thông thường. Nếu application cần `int`, hãy xét nguy cơ tràn khi ép `long` xuống `int`; không giả định bảng sẽ mãi nhỏ.

Ngược lại, truy vấn aggregate có `GROUP BY` có thể trả **không hoặc nhiều hàng**. Với dữ liệu mẫu, `SELECT COUNT(*) FROM products GROUP BY active` trả hai hàng, nên không hợp với `queryForObject(..., Long.class)`. Nếu bạn cần tổng chung, bỏ `GROUP BY` hoặc dùng truy vấn aggregate đúng nghĩa.

### 5.3. SUM, AVG, MIN, MAX có thể trả NULL

Một hàng aggregate không nhất thiết mang giá trị không-null:

```sql
SELECT SUM(price) FROM products WHERE id = 999;
```

Theo ngữ nghĩa SQL, `SUM` không có giá trị đầu vào trả `NULL` (khác `COUNT` trả 0). Nếu muốn mặc định 0 theo quy tắc nghiệp vụ:

```sql
SELECT COALESCE(SUM(price), 0) FROM products WHERE id = 999;
```

Với tiền tệ, dùng `BigDecimal` cho `NUMERIC/DECIMAL`, không tự chuyển thành `double` rồi làm tròn không kiểm soát.

## 6. Ví dụ hoàn chỉnh: Spring Boot + JDBC + Java 17+

Đây là một ứng dụng Spring Boot 3.3.x/Spring Framework 6.1.x tối giản. Mã Java đặt trong package `demo.singlequery`. Cần PostgreSQL chạy được và biến môi trường datasource; ví dụ **không phải** chương trình Java thuần có thể chạy chỉ bằng `javac` mà không có Spring/JDBC dependency.

### 6.1. Gradle dependencies

Trong dự án Gradle Spring Boot đã có plugin Spring Boot, dependency management và Java 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.flywaydb:flyway-core'

    runtimeOnly 'org.flywaydb:flyway-database-postgresql'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Các dependency dùng BOM của dự án Spring Boot để chọn phiên bản tương thích. `spring-boot-starter-jdbc` cung cấp `JdbcTemplate` và tích hợp `DataSource`; driver PostgreSQL cho kết nối thật, Flyway để tạo dữ liệu thử nghiệm ổn định.

### 6.2. Migration và seed

Tệp `src/main/resources/db/migration/V1__create_products.sql`:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(60) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    description VARCHAR(250),
    active BOOLEAN NOT NULL
);
```

Tệp `src/main/resources/db/migration/V2__seed_products.sql`:

```sql
INSERT INTO products (id, sku, name, price, description, active)
VALUES
    (10, 'BOOK-JAVA', 'Java căn bản', 125000.00, NULL, TRUE),
    (20, 'BOOK-SPRING', 'Spring JDBC', 199000.00, 'Thực hành', TRUE),
    (30, 'BOOK-ADV', 'Java căn bản', 155000.00, NULL, FALSE);
```

Trong ứng dụng production, seed mẫu thường nên nằm riêng môi trường thử nghiệm; bài này đặt trong migration để người học tái lập ví dụ trên database mới. Không chạy migration tạo bảng đã có vào một schema đang chứa dữ liệu thật.

### 6.3. Một record thể hiện một hàng sản phẩm

Tệp `src/main/java/demo/singlequery/Product.java`:

```java
package demo.singlequery;

import java.math.BigDecimal;

public record Product(
        long id,
        String sku,
        String name,
        BigDecimal price,
        String description,
        boolean active
) {}
```

`description` có thể là Java `null` vì cột SQL cho phép NULL. `id` và `active` an toàn ánh xạ vào primitive trong schema này vì `PRIMARY KEY` và `NOT NULL`. Nếu cột nullable mà dùng `rs.getLong(...)`, JDBC có thể trả giá trị mặc định `0` khi SQL NULL; phải kiểm tra `rs.wasNull()` nếu cần phân biệt. Với cột nullable kiểu số, dùng `rs.getObject("column", Long.class)` hoặc kiểu boxed phù hợp khi driver hỗ trợ.

### 6.4. Repository chọn API dựa trên ý nghĩa truy vấn

Tệp `src/main/java/demo/singlequery/ProductJdbcRepository.java`:

```java
package demo.singlequery;

import java.util.List;
import java.util.Objects;
import java.util.Optional;

import org.springframework.dao.support.DataAccessUtils;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class ProductJdbcRepository {
    private static final RowMapper<Product> PRODUCT_ROW =
            (rs, rowNum) -> new Product(
                    rs.getLong("id"),
                    rs.getString("sku"),
                    rs.getString("name"),
                    rs.getBigDecimal("price"),
                    rs.getString("description"),
                    rs.getBoolean("active")
            );

    private final JdbcTemplate jdbc;

    public ProductJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Hợp đồng: phải có đúng 1 hàng; id là PRIMARY KEY.
    public Product requireById(long id) {
        return jdbc.queryForObject(
                """
                SELECT id, sku, name, price, description, active
                FROM products
                WHERE id = ?
                """,
                PRODUCT_ROW,
                id
        );
    }

    // Hợp đồng: không tìm thấy là bình thường; nhiều hàng là lỗi.
    public Optional<Product> findById(long id) {
        List<Product> rows = jdbc.query(
                """
                SELECT id, sku, name, price, description, active
                FROM products
                WHERE id = ?
                """,
                PRODUCT_ROW,
                id
        );
        return DataAccessUtils.optionalResult(rows);
    }

    // Hợp đồng: chính xác 1 hàng x 1 cột và name NOT NULL.
    public String requireNameBySku(String sku) {
        return jdbc.queryForObject(
                "SELECT name FROM products WHERE sku = ?",
                String.class,
                sku
        );
    }

    // Hợp đồng: hàng có thể tồn tại với description = SQL NULL.
    // Giá trị trả về có thể là Java null; 0 hàng vẫn ném ngoại lệ.
    public String descriptionById(long id) {
        return jdbc.queryForObject(
                "SELECT description FROM products WHERE id = ?",
                String.class,
                id
        );
    }

    // COUNT(*) không GROUP BY: luôn 1 hàng x 1 cột, giá trị không NULL.
    public long countActive() {
        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM products WHERE active = ?",
                Long.class,
                true
        );
        return Objects.requireNonNull(count, "COUNT(*) unexpectedly NULL");
    }

    public long countByName(String name) {
        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM products WHERE name = ?",
                Long.class,
                name
        );
        return Objects.requireNonNull(count, "COUNT(*) unexpectedly NULL");
    }
}
```

Tất cả tham số đầu vào được bind bằng `?` và arguments. Truy vấn mapper chọn rõ các cột cần đọc; không dùng `SELECT *` khiến mapping thay đổi ngoài ý muốn khi migration thêm/xóa cột.

`findById(...)` dùng `DataAccessUtils.optionalResult(Collection)` (Spring Framework 6.1+): danh sách rỗng thành `Optional.empty()`, đúng một phần tử thành `Optional.of(...)`, từ hai phần tử trở lên ném `IncorrectResultSizeDataAccessException`. `RowMapper` trong ví dụ không trả null, nên một hàng hợp lệ luôn có `Product`.

Nếu trường `sku` là `UNIQUE` ở database, `requireNameBySku(...)` có cơ sở để đòi tối đa một hàng. Nếu gọi với SKU không tồn tại, phương thức vẫn ném `EmptyResultDataAccessException`; caller cần quyết định “không tìm thấy” là lỗi hay trường hợp hợp lệ.

### 6.5. Chương trình chạy thử và stdout xác định

Tệp `src/main/java/demo/singlequery/SingleQueryApplication.java`:

```java
package demo.singlequery;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SingleQueryApplication {
    public static void main(String[] args) {
        SpringApplication.run(SingleQueryApplication.class, args);
    }

    @Bean
    CommandLineRunner showExamples(ProductJdbcRepository repository) {
        return args -> {
            System.out.println("active=" + repository.countActive());
            System.out.println("sku(10)=" + repository.requireById(10).sku());
            System.out.println(
                    "present(999)=" + repository.findById(999).isPresent()
            );
            System.out.println(
                    "description(10) is null="
                    + (repository.descriptionById(10) == null)
            );
        };
    }
}
```

Tệp cấu hình `src/main/resources/application.yml`:

```yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
```

Giả sử PostgreSQL đang chạy tại `localhost:5432`, database học tập mới có tên `jdbc_single_query`, user/password đã được tạo trong môi trường của bạn. Trong terminal hỗ trợ biến môi trường shell, cung cấp URL JDBC và credentials rồi chạy:

```bash
./gradlew bootRun
```

Trên Windows PowerShell, dùng `$env:DB_JDBC_URL = "jdbc:postgresql://localhost:5432/jdbc_single_query"`, tương tự với `DB_USER` và `DB_PASSWORD`, rồi `.\gradlew.bat bootRun`. Không đưa mật khẩu vào source code hay commit tệp chứa bí mật.

Sau khi Flyway chạy V1/V2 trên database mới, ngoài log khởi động Spring Boot, chương trình in chính xác bốn dòng:

```text
active=2
sku(10)=BOOK-JAVA
present(999)=false
description(10) is null=true
```

Ý nghĩa của bốn dòng: `COUNT(*)` trả 2, truy vấn PK id=10 có một object, truy vấn id=999 theo hướng optional trả empty, và id=10 tồn tại nhưng cột description là NULL.

## 7. Khi nào không dùng queryForObject?

### 7.1. Kết quả có thể thiếu: dùng Optional hoặc trả danh sách

Nếu API `findById` cần trả “không thấy” mà không coi là exception, có hai lựa chọn:

**Cách A: query + kiểm tra số hàng bằng DataAccessUtils**

```java
List<Product> rows = jdbcTemplate.query(
        """
        SELECT id, sku, name, price, description, active
        FROM products
        WHERE id = ?
        """,
        productRowMapper,
        id
);
Optional<Product> product = DataAccessUtils.optionalResult(rows);
```

`productRowMapper` là `RowMapper<Product>` đã định nghĩa trong repository. Cách này có hợp đồng **0..1 hàng** mà vẫn ném lỗi nếu thực tế >1, bảo vệ trường hợp truy vấn sai điều kiện hoặc join nhân bản hàng.

**Cách B: queryForObject rồi catch đúng một ngoại lệ**

```java
try {
    return Optional.ofNullable(
            jdbcTemplate.queryForObject(sql, productRowMapper, id)
    );
} catch (EmptyResultDataAccessException notFound) {
    return Optional.empty();
}
```

Đây là fragment bên trong phương thức trả `Optional<Product>`, với biến `sql` và `productRowMapper` đã định nghĩa. Cách B hợp lệ khi muốn xử lý tình huống zero row, nhưng không nên catch chung `DataAccessException` rồi coi mọi lỗi là “không tìm thấy”: lỗi DB, SQL sai hoặc nhiều hàng phải được phát hiện.

Với mã Spring 6.1+, cách A thường rõ ràng khi zero row là trường hợp bình thường. Nếu đang dùng `JdbcClient`, có thể dùng `optional()` trực tiếp (xem mục 10).

### 7.2. Cần nhiều object: dùng query thay vì queryForObject

```java
List<Product> products = jdbcTemplate.query(
        """
        SELECT id, sku, name, price, description, active
        FROM products
        WHERE active = ?
        ORDER BY id
        """,
        productRowMapper,
        true
);
```

Kết quả có thể 0, 1, hoặc nhiều phần tử. `query(...)` không áp đặt đúng một hàng; `RowMapper` chuyển từng hàng thành một object. Nếu nghiệp vụ thực sự cần danh sách, dùng `query(...)` là cách đúng thay vì bắt `IncorrectResultSizeDataAccessException` rồi xử lý như danh sách.

### 7.3. Cần một giá trị mỗi hàng: dùng queryForList

```java
List<String> skus = jdbcTemplate.queryForList(
        "SELECT sku FROM products WHERE active = ? ORDER BY id",
        String.class,
        true
);
```

Trong dữ liệu mẫu, `skus` gồm `BOOK-JAVA` và `BOOK-SPRING` theo thứ tự `id`. Mỗi hàng của câu SQL chỉ có một cột, nhưng **tổng số hàng có thể nhiều**. `queryForList(sql, Class<T>, ...)` có hợp đồng khác với `queryForObject(...)`.

### 7.4. queryForMap cũng đòi đúng một hàng

```java
Map<String, Object> row = jdbcTemplate.queryForMap(
        "SELECT sku, name FROM products WHERE id = ?",
        10L
);
```

Đây là **một map từ một hàng nhiều cột**. Đừng nhầm với `queryForList` trả nhiều hàng; nếu SQL trả 0 hoặc nhiều hàng, `queryForMap(...)` vẫn báo sai cardinality. Trả `Map` trực tiếp từ repository ra public HTTP API có thể làm lộ tên cột hoặc giá trị nhạy cảm; DTO/domain type rõ ràng thường an toàn hơn.

## 8. Tính duy nhất thật sự nằm ở đâu?

`queryForObject(...)` kiểm tra **kết quả truy vấn lúc chạy**, không tạo một ràng buộc duy nhất trong database. Nó không ngăn insert nhiều hàng có cùng khóa nghiệp vụ và không làm biểu thức `WHERE` trở thành unique.

Ví dụ với dữ liệu mẫu:

```sql
SELECT id, sku, name, price, description, active
FROM products
WHERE name = 'Java căn bản';
```

Có hai hàng: id=10 và id=30. Gọi `queryForObject(sql, productRowMapper, "Java căn bản")` sẽ ném `IncorrectResultSizeDataAccessException` vì `name` không unique. Không nên giải quyết bằng:

```sql
SELECT id, sku, name, price, description, active
FROM products
WHERE name = 'Java căn bản'
LIMIT 1;
```

`LIMIT 1` chỉ **che giấu** việc có hai hàng. Nếu không có `ORDER BY`, DB không cam kết bản ghi nào được chọn; ngay cả có `ORDER BY`, việc chọn bản ghi đầu tiên chỉ đúng khi nghiệp vụ thật sự cần “một bản ghi theo thứ tự ưu tiên”, không phải “đúng một bản ghi”.

Khi nghiệp vụ yêu cầu SKU duy nhất, dùng `UNIQUE (sku)` trong schema. Nếu thực sự đòi `name` duy nhất thì phải có constraint phù hợp; nếu tên được phép trùng, repository phải trả danh sách hoặc bổ sung điều kiện chọn một bản ghi theo yêu cầu.

### 8.1. JOIN có thể nhân bản hàng dù truy vấn theo PK

```sql
SELECT p.id, p.name, t.tag_name
FROM products p
JOIN product_tags t ON t.product_id = p.id
WHERE p.id = 10;
```

Đây là ví dụ SQL giả định có bảng `product_tags` với quan hệ một-nhiều. Một sản phẩm có ba tag sẽ tạo **ba hàng kết quả**. Mặc dù `products.id` unique, phép JOIN không đảm bảo còn một hàng.

Nếu chỉ cần product, query bảng product riêng; nếu cần danh sách tags, ánh xạ cấu trúc một-nhiều bằng `query(...)` và grouping/`ResultSetExtractor` thích hợp, hoặc thiết kế aggregate SQL đúng mục đích. Đừng tự đưa `DISTINCT` vào mọi câu SQL rồi cho rằng luôn giải quyết được vấn đề: `DISTINCT` xét tổ hợp mọi cột được chọn, và ba tag khác nhau vẫn cho ba hàng.

### 8.2. “Lấy bản ghi mới nhất” là bài toán khác

Nếu yêu cầu là “đơn hàng mới nhất của một khách”, kết quả 0..1 có thể dùng:

```sql
SELECT id, customer_id, created_at
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 1;
```

Trong tình huống này, `ORDER BY ... LIMIT 1` **có chủ đích**: chọn bản ghi ưu tiên, không giả định cơ sở dữ liệu chỉ có một đơn. Nếu không có đơn, `queryForObject` vẫn ném `EmptyResultDataAccessException`; API optional vẫn phù hợp.

Hãy phân biệt ba yêu cầu trước khi viết SQL: **duy nhất theo ràng buộc**, **có thể thiếu nhưng tối đa một**, và **lấy một đại diện theo thứ tự**.

## 9. Xử lý ngoại lệ đúng ngữ nghĩa

### 9.1. EmptyResultDataAccessException

Xảy ra khi phương thức **yêu cầu đúng một hàng** nhưng SQL trả 0 hàng. Đây thường là tình huống “not found” nếu truy vấn theo ID hoặc business key.

```java
try {
    Product product = repository.requireById(id);
    return product;
} catch (EmptyResultDataAccessException absent) {
    throw new ProductNotFoundException(id);
}
```

Ví dụ là fragment trong application service, `ProductNotFoundException` là exception nghiệp vụ cần định nghĩa. Nếu không tìm thấy hoàn toàn bình thường, trả `Optional<Product>` từ repository sẽ rõ hơn và tránh điều khiển luồng bằng exception.

Không catch `IncorrectResultSizeDataAccessException` trước rồi mặc định coi mọi trường hợp là “not found”: lớp này bao gồm cả trường hợp **nhiều hàng**.

### 9.2. IncorrectResultSizeDataAccessException

Một số overload `queryForObject(...)` ném lớp này khi không đúng số hàng; trường hợp zero row thường là lớp con `EmptyResultDataAccessException`. Khi có nhiều hàng mà ứng dụng nghĩ phải có đúng một, có thể là:

- SQL thiếu điều kiện `WHERE`.
- Dùng thuộc tính không có UNIQUE constraint.
- JOIN nhân số hàng.
- Dữ liệu đã bị ghi sai trước khi migration bổ sung constraint.
- Lỗi mô hình: use case thật sự có nhiều kết quả nhưng gọi phương thức lấy một.

Đây thường là **lỗi về giả định dữ liệu hoặc truy vấn**, không nên trả tùy tiện một hàng cho UI. Phải kiểm tra SQL, schema và yêu cầu nghiệp vụ. Để chẩn đoán, exception cung cấp thông tin expected/actual size theo hợp đồng API.

### 9.3. IncorrectResultSetColumnCountException

Xảy ra ở đường ánh xạ một cột khi số cột SQL không đúng. Ví dụ:

```java
// SQL một hàng nhưng hai cột => sai shape cho String.class.
jdbcTemplate.queryForObject(
        "SELECT name, price FROM products WHERE id = ?",
        String.class,
        10L
);
```

Đây là **lỗi cấu trúc truy vấn/mapping**. Cách sửa là chỉ chọn `name` nếu cần `String` hoặc dùng `RowMapper<ProductNameAndPrice>` nếu cần hai trường. Đừng che lỗi bằng việc bỏ qua cột thứ hai hay ép toàn bộ map thành `String`.

### 9.4. SQL NULL và chuyển đổi kiểu không hợp lệ

`SELECT description ... WHERE id=10` có một hàng chứa NULL; Spring có thể trả Java `null`. Nếu code viết:

```java
int length = jdbcTemplate.queryForObject(
        "SELECT description FROM products WHERE id = ?",
        String.class,
        10L
).length();
```

thì sẽ gây `NullPointerException` vì giá trị SQL NULL. Giải pháp là dùng kiểu Java có thể nullable, `Optional` theo ngữ nghĩa hoặc query trả object chứa cả thông tin hàng/cột; nếu nghiệp vụ cấm NULL, đặt `NOT NULL` trong DB và xử lý dữ liệu hiện có.

Nếu yêu cầu `Integer.class` cho cột text không chuyển đổi được, có thể gặp lỗi chuyển kiểu/`DataAccessException` khác. Chọn Java type tương ứng kiểu JDBC và tránh ép kiểu tùy tiện. `COUNT(*)` trong PostgreSQL phù hợp `Long.class` hơn giả định `Integer.class`.

## 10. Các API liên quan trong Spring 6.1+

### 10.1. NamedParameterJdbcTemplate

Khi có nhiều tham số, named parameter có thể tăng độ rõ ràng:

```java
String sql = """
        SELECT name
        FROM products
        WHERE sku = :sku
        """;

String name = namedJdbc.queryForObject(
        sql,
        java.util.Map.of("sku", "BOOK-JAVA"),
        String.class
);
```

`namedJdbc` là `NamedParameterJdbcTemplate` đã cấu hình. Hợp đồng **một hàng, một cột** vẫn giữ nguyên; named parameters chỉ thay cách bind giá trị. Với mapper cho object nhiều cột, dùng overload nhận `RowMapper<T>`.

### 10.2. JdbcClient: optional và single rõ ý nghĩa

Spring Framework 6.1 giới thiệu `org.springframework.jdbc.core.simple.JdbcClient`, facade fluent trên `JdbcTemplate`/`NamedParameterJdbcTemplate`:

```java
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;

JdbcClient client = JdbcClient.create(jdbcTemplate);

Optional<String> maybeName = client.sql(
        "SELECT name FROM products WHERE id = :id"
    )
    .param("id", 999L)
    .query(String.class)
    .optional();

String requiredName = client.sql(
        "SELECT name FROM products WHERE id = :id"
    )
    .param("id", 10L)
    .query(String.class)
    .single();
```

Đây là fragment trong phạm vi có sẵn `jdbcTemplate`. `optional()` biểu diễn **0..1 kết quả** và báo lỗi khi >1; `single()` đòi đúng một kết quả không-null. `query(String.class)` vẫn thể hiện mapping một cột, còn với object nhiều cột có thể dùng `query(RowMapper<T>)`.

Cách viết ngắn hơn không thay đổi bất biến của truy vấn: vẫn cần SQL đúng, unique constraint khi nghiệp vụ đòi duy nhất và kiểu kết quả đúng số cột.

### 10.3. DataAccessUtils: singleResult, optionalResult, requiredSingleResult

Khi đã có `List<T>` từ `query(...)`, Spring cung cấp tiện ích:

| Phương thức | Không có phần tử | Đúng một phần tử | Nhiều phần tử |
| --- | --- | --- | --- |
| `DataAccessUtils.singleResult(results)` | Trả `null` | Trả phần tử | Ném `IncorrectResultSizeDataAccessException` |
| `DataAccessUtils.optionalResult(results)` | Trả `Optional.empty()` | Trả `Optional` chứa phần tử nếu không-null | Ném `IncorrectResultSizeDataAccessException` |
| `DataAccessUtils.requiredSingleResult(results)` | Ném `EmptyResultDataAccessException` | Trả phần tử | Ném `IncorrectResultSizeDataAccessException` |

Đừng nhầm `uniqueResult(...)` với kiểm tra **một hàng**. Hàm này kiểm tra tính duy nhất của **đối tượng trong collection** theo cách riêng của utility; nó không phải cách đáng tin để xác nhận truy vấn SQL thực sự chỉ trả một hàng. Với yêu cầu cardinality, ưu tiên `singleResult`, `optionalResult` hoặc `requiredSingleResult`.

### 10.4. BeanPropertyRowMapper và RowMapper tự viết

`BeanPropertyRowMapper` ánh xạ cột sang JavaBean property theo quy ước tên; `DataClassRowMapper` hỗ trợ data class/record trong trường hợp phù hợp. Nhưng khi cần kiểm soát cột, giá trị nullable, conversion, domain invariants hoặc tối ưu mapping, `RowMapper` explicit như ví dụ thường rõ nhất.

Mọi lựa chọn mapper đều không biến hai hàng thành một hàng hợp lệ của `queryForObject`. Mapper chịu trách nhiệm **một hàng → một Java object**, còn `JdbcTemplate` chịu trách nhiệm xác nhận cardinality cho overload tương ứng.

## 11. Kiểm thử số hàng và số cột bằng JUnit 5

Các test dưới đây yêu cầu dự án Spring Boot ở mục 6, database PostgreSQL thử nghiệm với Flyway V1/V2, và datasource trỏ đúng database đó. Không chạy trực tiếp trên production. Tệp `src/test/java/demo/singlequery/ProductJdbcRepositoryTest.java`:

```java
package demo.singlequery;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.IncorrectResultSetColumnCountException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class ProductJdbcRepositoryTest {
    @Autowired
    ProductJdbcRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void exactlyOneRowWithMultipleColumnsMapsToProduct() {
        Product product = repository.requireById(10L);
        assertEquals(10L, product.id());
        assertEquals("BOOK-JAVA", product.sku());
        assertEquals("Java căn bản", product.name());
    }

    @Test
    void zeroRowsDistinguishesRequiredAndOptional() {
        assertThrows(
                EmptyResultDataAccessException.class,
                () -> repository.requireById(999L)
        );
        assertEquals(Optional.empty(), repository.findById(999L));
    }

    @Test
    void scalarCountAndSqlNullHaveDifferentMeanings() {
        assertEquals(2L, repository.countActive());
        assertEquals(0L, repository.countByName("Không tồn tại"));
        assertNull(repository.descriptionById(10L));
        assertEquals("Thực hành", repository.descriptionById(20L));
    }

    @Test
    void twoColumnsCannotBeMappedAsOneString() {
        assertThrows(
                IncorrectResultSetColumnCountException.class,
                () -> jdbc.queryForObject(
                        "SELECT name, price FROM products WHERE id = ?",
                        String.class,
                        10L
                )
        );
    }

    @Test
    void twoRowsViolateQueryForObjectCardinality() {
        assertThrows(
                IncorrectResultSizeDataAccessException.class,
                () -> jdbc.queryForObject(
                        "SELECT id, name FROM products WHERE name = ?",
                        (rs, rowNum) -> rs.getLong("id"),
                        "Java căn bản"
                )
        );
    }

    @Test
    void rowMapperMayReadManyColumns() {
        String name = jdbc.queryForObject(
                "SELECT id, name FROM products WHERE id = ?",
                (rs, rowNum) -> rs.getString("name"),
                10L
        );
        assertEquals("Java căn bản", name);
    }
}
```

Đây là integration test dùng **PostgreSQL thật**, vì Spring context lấy datasource từ môi trường và chạy migration. Có thể thay datasource thử nghiệm bằng Testcontainers PostgreSQL trong pipeline để đảm bảo tái lập. Việc chạy test cần cấu hình driver và DB đúng như mục 6.

Lệnh:

```bash
./gradlew test
```

Trên Windows dùng `gradlew.bat test`. Nếu migration, datasource và ví dụ khớp, cả sáu test phải thành công; nếu thất bại, đọc assertion và exception thực tế. Không suy đoán “test pass” khi chưa chạy trong môi trường cụ thể.

**Vì sao test thứ năm quan trọng?** SQL có hai cột nhưng dùng `RowMapper` chỉ đọc cột `id`, điều đó hợp lệ về column mapping. Tuy nhiên SQL có hai hàng, nên `queryForObject` vẫn ném `IncorrectResultSizeDataAccessException`. Test thứ sáu kiểm tra mặt đối lập: một hàng hai cột vẫn có thể map thành String với `RowMapper` chủ động chọn `name`, dù cách này thường nên đơn giản hóa SQL thành chỉ một cột khi không cần ID.

## 12. Lựa chọn API như một hợp đồng nghiệp vụ

Trước khi chọn `queryForObject`, trả lời các câu hỏi:

1. **Nếu không thấy hàng nào thì sao?** Nếu đó là lỗi, dùng truy vấn required và chuyển thành lỗi nghiệp vụ phù hợp. Nếu đó là kết quả bình thường, ưu tiên `Optional<T>`.
2. **Nếu thấy hai hàng thì sao?** Nếu không được phép, giữ nguyên lỗi cardinality để điều tra, có UNIQUE constraint và test. Nếu hai hàng hợp lệ, trả `List<T>`.
3. **Đầu ra là một scalar hay một object nhiều thuộc tính?** Một scalar dùng `Class<T>`/`SingleColumnRowMapper`; một object nhiều cột dùng `RowMapper<T>`.
4. **SQL có thực sự bảo đảm tối đa một hàng?** Khóa chính/UNIQUE bảo đảm ở bảng gốc, nhưng JOIN/GROUP BY có thể đổi cardinality.
5. **Cột có thể là NULL?** Dùng boxed/reference type, nullable DTO hoặc giá trị mặc định có chủ ý; tránh unbox null.
6. **Kết quả có thứ tự không?** Khi chọn hàng “đầu” của nhiều hàng, phải có `ORDER BY` và quy tắc nghiệp vụ; đừng nhầm với kiểm tra uniqueness.

Một bảng quyết định nhỏ:

| Nhu cầu | Phương thức | Lý do |
| --- | --- | --- |
| Lấy tổng số sản phẩm | `queryForObject(..., Long.class)` | `COUNT(*)` một hàng, một cột |
| Lấy tên từ SKU bắt buộc có | `queryForObject(..., String.class, sku)` | Một scalar, SKU unique |
| Lấy Product bằng ID bắt buộc có | `queryForObject(..., productMapper, id)` | Một object, nhiều cột, ID là PK |
| Tìm Product có thể không tồn tại | `query(..., productMapper, id)` + `optionalResult` | 0..1, thiếu là bình thường |
| Liệt kê sản phẩm theo nhóm | `query(..., productMapper, groupId)` | 0..N object |
| Danh sách SKU của một nhóm | `queryForList(..., String.class, groupId)` | N hàng, mỗi hàng một cột |
| Chọn đơn mới nhất | `ORDER BY ... LIMIT 1`, trả optional | Chọn theo thứ tự, không giả định unique |

Đừng quyết định chỉ dựa vào tên `queryForObject`. Hãy viết rõ hợp đồng cardinality trong repository method và test nó.

## 13. Những lỗi dễ mắc khi học JDBC

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `queryForObject("SELECT * ...", String.class)` | Một hàng có nhiều cột | Chọn đúng một cột hoặc dùng RowMapper |
| `queryForObject(..., RowMapper)` với WHERE không unique | Có nhiều hàng | Thêm điều kiện/constraint hoặc trả danh sách |
| Coi `NULL` là không tìm thấy | Nhầm giá trị cột với số hàng | Tách 0 hàng và 1 hàng NULL |
| Coi `COUNT(*) = 0` là zero-row exception | COUNT không GROUP BY vẫn tạo một hàng | Đọc giá trị 0 bằng Long |
| Dùng `Integer.class` cho mọi `COUNT(*)` | COUNT có thể là BIGINT và vượt int | Dùng Long, chuyển kiểu có kiểm tra |
| `LIMIT 1` để lờ dữ liệu trùng | Che lỗi cardinality; có thể không deterministic | Xác định đúng uniqueness; chỉ dùng LIMIT khi nghiệp vụ muốn chọn một hàng |
| Trả null khi catch mọi `DataAccessException` | Che cả lỗi SQL/kết nối/schema | Chỉ xử lý chính xác zero row nếu được phép |
| Không xét JOIN một-nhiều | Join có thể nhân bản hàng PK | Thiết kế lại mapping/aggregate hoặc trả danh sách |
| Dùng primitive cho cột nullable | JDBC getter có thể trả mặc định hoặc unboxing NPE | Boxed type, `wasNull()`, domain nullable |
| Không bind tham số | Ghép dữ liệu người dùng vào SQL, nguy cơ injection | Dùng `?` hoặc named parameters |
| `RowMapper` tùy tiện trả null | Một hàng tồn tại mà object lại null | Mapper trả object hợp lệ, ngoại lệ rõ ràng |
| Bắt nhiều hàng rồi lấy phần tử đầu | Giấu dữ liệu sai hoặc truy vấn sai | Giữ lỗi, kiểm tra ràng buộc DB |
| Nhầm `queryForMap` là danh sách map | `queryForMap` cũng đòi một hàng | Dùng `queryForList`/`query` khi cần nhiều hàng |

## 14. Bài tập thực hành

**Bài 1 — dự đoán kết quả.** Dựa vào bảng `products` ở mục 5, với mỗi câu SQL dưới đây hãy xác định số hàng/số cột và kết quả hoặc ngoại lệ khi gọi `queryForObject(sql, String.class)`:

```sql
SELECT name FROM products WHERE id = 20;
SELECT name FROM products WHERE id = 999;
SELECT description FROM products WHERE id = 10;
SELECT name, price FROM products WHERE id = 10;
SELECT name FROM products WHERE name = 'Java căn bản';
```

**Bài 2 — chọn overload.** Viết phương thức `Product requireBySku(String sku)`; dùng `RowMapper<Product>` vì cần nhiều thuộc tính. Sau đó viết `Optional<Product> findBySku(String sku)` mà không biến zero row thành lỗi hạ tầng.

**Bài 3 — aggregate.** Viết hai truy vấn đếm: tổng số hàng đang active, và số hàng có `name = 'Không tồn tại'`. Giải thích vì sao cả hai trả một hàng nhưng có thể trả các giá trị 2 và 0. Kiểm tra điều gì sẽ xảy ra nếu thêm `GROUP BY active`.

**Bài 4 — phát hiện vi phạm thiết kế.** Một repository dùng `SELECT id FROM products WHERE name = ? LIMIT 1` để “bảo đảm chỉ một sản phẩm có tên đó”. Chỉ ra lỗi mô hình và đề xuất hợp đồng đúng nếu tên được phép trùng hoặc nếu tên bắt buộc unique.

**Bài 5 — kiểm thử lỗi shape.** Thêm test `queryForObject("SELECT sku, name FROM products WHERE id = ?", String.class, 20L)` và kiểm tra `IncorrectResultSetColumnCountException`. Thử cùng câu SQL nhưng dùng `RowMapper` tạo record chứa `sku` và `name`.

**Gợi ý đáp án bài 1:** lần lượt (1) `Spring JDBC`; (2) `EmptyResultDataAccessException`; (3) Java `null`; (4) `IncorrectResultSetColumnCountException`; (5) `IncorrectResultSizeDataAccessException`. Các lỗi này không thể sửa bằng cách catch chung rồi luôn trả chuỗi rỗng.

## 15. Checklist cuối bài

- SQL trả **đúng số hàng** mà repository method công bố chưa?
- Với `Class<T>`, SQL có **đúng một cột** ở hàng được map chưa?
- Với object nhiều cột, đã dùng `RowMapper<T>` thay vì cố map qua `String.class` chưa?
- “Không tìm thấy” được biểu diễn bằng `Optional.empty()` hoặc lỗi nghiệp vụ có chủ ý chưa?
- Đã phân biệt zero row với SQL NULL và COUNT(*) = 0 chưa?
- Nếu truy vấn đòi duy nhất, DB có PK/UNIQUE thực sự bảo vệ không? JOIN/GROUP BY có làm thay đổi số hàng không?
- Nếu chọn hàng đầu tiên của tập nhiều hàng, có quy tắc `ORDER BY` rõ ràng không?
- Giá trị kiểu `BigDecimal`, `Long`, kiểu nullable và mapping JDBC có phù hợp schema không?
- Test đã bao phủ 0, 1, >1 hàng; 1, >1 cột; và NULL chưa?

**Điều cần nhớ:** `queryForObject` không có nghĩa “hãy lấy một hàng tùy ý”. Nó là lời **khẳng định** về kết quả. Với `Class<T>`, khẳng định là **đúng một hàng và một cột**; với `RowMapper<T>`, khẳng định là **đúng một hàng**, mapper được đọc nhiều cột để tạo object. Nếu nhu cầu thật là 0..1, dùng optional; nếu là 0..N, dùng list. Thiết kế đúng hợp đồng trước rồi để Spring báo lỗi khi dữ liệu vi phạm.

## Tài liệu tham khảo

- Spring Framework — JDBC Core, phần Querying: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework 6.1 — JdbcTemplate.queryForObject Javadoc: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework 6.1 — DataAccessUtils và optionalResult: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/dao/support/DataAccessUtils.html
- Spring Framework 6.1 — JdbcClient fluent API: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html
- Spring Framework 6.1 — JdbcClient.MappedQuerySpec: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html
- Spring Framework 6.1 — IncorrectResultSetColumnCountException: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/IncorrectResultSetColumnCountException.html

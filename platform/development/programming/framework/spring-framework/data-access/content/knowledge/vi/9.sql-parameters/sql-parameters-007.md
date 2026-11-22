# Kiểm soát danh sách tên cột sắp xếp bằng lựa chọn hợp lệ

Khi xây dựng API tìm kiếm/phân trang với Spring `JdbcTemplate`, người dùng có thể được phép chọn sắp xếp theo **tên**, **giá**, **ngày tạo** và hướng **tăng/giảm**. Tuy nhiên, tên cột và từ khóa trong `ORDER BY` là **cấu trúc SQL**, không phải giá trị dữ liệu có thể bind trực tiếp qua JDBC parameter.

Quy tắc nền tảng:

> **Không bao giờ nối tên cột hoặc hướng sắp xếp thô nhận từ client vào SQL.** Hãy xác thực lựa chọn qua danh sách **allow-list** (các khóa được cho phép) rồi ánh xạ từng khóa thành biểu thức SQL cố định do ứng dụng sở hữu. Vẫn dùng `PreparedStatement`/`JdbcTemplate` để bind tất cả giá trị dữ liệu trong `WHERE` và phân trang.

Ví dụ API nhận `sort=price&direction=DESC`. Backend nên dịch `price` thành một lựa chọn đã kiểm tra, ánh xạ nó tới `p.price` và dịch hướng thành keyword cố định `DESC`. Câu SQL cuối có thể là:

```sql
SELECT p.id, p.name, p.price
FROM products p
WHERE p.active = ? AND p.price >= ?
ORDER BY p.price DESC, p.id ASC
LIMIT ? OFFSET ?;
```

Chỉ các fragment `p.price` và `DESC` được ghép vào cấu trúc vì chúng đến từ **source code cố định**; các giá trị `active`, `minimumPrice`, `pageSize`, `offset` vẫn là tham số bind.

Bài học đi từ cơ chế JDBC, bảo mật đầu vào, thiết kế API, enum Java 17, ứng dụng Spring Boot/H2 chạy được, đến nhiều cột sắp xếp, phân trang ổn định và kiểm thử.

## 1. Phân biệt giá trị dữ liệu và cấu trúc SQL

`PreparedStatement` nhận SQL đã xác định cấu trúc rồi bind giá trị cho các dấu `?`:

```java
String sql = """
    SELECT id, name, price
    FROM products
    WHERE price >= ? AND active = ?
    """;
List<String> names = jdbc.query(
    sql,
    (rs, rowNum) -> rs.getString("name"),
    minPrice, true
);
```

Đây là snippet nằm trong class đã có `JdbcTemplate jdbc` và `BigDecimal minPrice`. Hai giá trị được driver coi là **dữ liệu**, kể cả khi một giá trị kiểu chuỗi chứa dấu quote hoặc cú pháp SQL.

Khác với `WHERE`, những phần sau là **identifier/keyword/expression**:

- Tên bảng `products`, tên cột `price`, alias `p`.
- Cấu trúc `ORDER BY p.price`.
- Hướng sắp xếp `ASC` hoặc `DESC`.
- Danh sách các tiêu chí ngăn bằng dấu phẩy.
- Những biểu thức như `LOWER(p.name)`, `CASE WHEN ...`, `NULLS LAST` và chỉ định collation.

Chúng **không thể được thay bằng một chuỗi bind**. Ví dụ sau sai về ngữ nghĩa:

```sql
-- Không biến "price" thành tên cột.
SELECT id, name, price
FROM products
ORDER BY ?;
```

Bind `"price"` qua `?` không khiến database tự hiểu đó là cột `price`: tùy DBMS có thể bị coi như giá trị hằng hoặc báo lỗi. Tương tự, không dùng `ORDER BY p.price ?` với `"DESC"` làm tham số. Vị trí bind đại diện cho **value**, không chèn được keyword vào SQL grammar.

| Đầu vào | Bản chất | Cách an toàn |
| --- | --- | --- |
| `minimumPrice` trong `WHERE price >= ?` | Data value | Validate kiểu/cận; bind bằng `?`. |
| `tenantId` trong `WHERE tenant_id = ?` | Data value | Lấy từ ngữ cảnh ủy quyền đáng tin cậy; bind. |
| `keyword` trong `LIKE ?` | Data value | Bind pattern; escape wildcard nếu cần tìm literal. |
| `size` và `offset` | Giá trị số | Validate giới hạn; bind khi DBMS hỗ trợ. |
| `sort=name` | Lựa chọn cột | Map `name` sang biểu thức cố định `p.name`. |
| `direction=desc` | Lựa chọn keyword | Enum/boolean sinh đúng `DESC`. |
| `sort=name,-price` | Danh sách cấu trúc | Parse từng phần, kiểm tra toàn bộ, giới hạn số mục. |
| `NULLS LAST`, `LOWER(...)` | Expression/keyword | Chỉ cho dùng fragment cố định được duyệt. |

## 2. Lỗ hổng khi nối raw sort input

**Anti-pattern:**

```java
// SAI: user có thể đổi cấu trúc SQL.
String sql = "SELECT id, name FROM products ORDER BY "
           + sortColumn + " " + direction;
return jdbc.query(sql, (rs, rowNum) -> rs.getString("name"));
```

Nếu client cung cấp `sortColumn="price DESC; DROP TABLE products; --"`, phần input đã nằm trong SQL text trước khi JDBC nhận truy vấn. Khả năng thực thi nhiều câu lệnh phụ thuộc driver/DBMS, nhưng cách tạo SQL này đã có nguy cơ injection hoặc cho phép biểu thức sort ngoài dự kiến. Chẳng hạn client có thể yêu cầu một hàm DB tốn tài nguyên, sắp xếp trên cột không được phép hoặc gây lỗi truy vấn.

**Vẫn sai dù có bind ở WHERE:**

```java
// minPrice được bind nhưng sortColumn chưa được kiểm soát.
String sql = "SELECT id, name FROM products "
           + "WHERE price >= ? ORDER BY " + sortColumn;
return jdbc.query(
    sql,
    (rs, rowNum) -> rs.getString("name"),
    minPrice
);
```

Dùng `PreparedStatement` hoặc `NamedParameterJdbcTemplate` không tự bảo vệ **những phần câu SQL đã ghép từ raw input**. Kiểm tra chuỗi chỉ gồm chữ cái bằng regex cũng không đủ: `internal_cost` hay `secret_token` có thể là tên cột hợp lệ về cú pháp nhưng không được phép trở thành tính năng API.

### 2.1. Escaping và quoting không thay thế allow-list

Đôi khi có đề xuất “thêm dấu quote quanh tên cột”, “escape dấu nháy đơn” hoặc “loại bỏ dấu chấm phẩy”. Những cách này không giải quyết được quyền lựa chọn **cột nào** và có thể phụ thuộc dialect, collation hay cấu hình driver. Identifier quoting giúp trình phân tích cú pháp nhận một tên identifier; nó **không đảm bảo tên đó được nghiệp vụ cho phép**.

Ví dụ `"secret_token"` được quote hợp lệ vẫn không phải một sort key mà API nên công khai. Vì thế, thứ cần xác nhận là **đúng một lựa chọn đã có sẵn trong chương trình**, không phải chuỗi nhìn có vẻ an toàn.

## 3. Thiết kế contract: khóa API khác cột vật lý

Giả sử màn hình sản phẩm có ba sort key:

| Khóa client | Nhãn giao diện | SQL fragment từ code |
| --- | --- | --- |
| `name` | Tên sản phẩm | `p.name` |
| `price` | Giá | `p.price` |
| `createdAt` | Ngày tạo | `p.created_at` |

Client **không được** gửi `p.name` hoặc `LOWER(p.name)` nếu hợp đồng công bố key `name`. Có lợi ích lớn khi tách biệt như vậy:

1. UI/API không bị phụ thuộc trực tiếp vào schema, cách đặt tên snake_case/camelCase hoặc SQL alias.
2. Khi migration đổi tên cột, chỉ mapping nội bộ thay đổi.
3. Endpoint có thể giới hạn cột được phép: không tự cấp quyền sort theo mọi cột có trong bảng.
4. Những biểu thức đặc biệt (ví dụ `LOWER(p.name)`) được review và kiểm thử trước khi đưa vào mapping.
5. Code có thể gắn chính sách index, giới hạn tài nguyên và quyền theo từng sort key.

**Xử lý input:**
- Không có tham số `sort`: dùng default rõ ràng do server chọn.
- Có `sort` nhưng không thuộc danh sách: từ chối, thường thành HTTP 400 ở API.
- `direction` thiếu: dùng hướng default đã công bố.
- Hướng không thuộc `ASC`/`DESC`: từ chối, không ghép chuỗi lạ.
- Nếu muốn cho phép `" desc "`, chuẩn hóa có chủ đích trước khi so sánh; không nhận mọi text gần giống.

Từ chối lựa chọn lạ thay vì âm thầm đưa nó vào SQL giúp phát hiện bug client và giảm bề mặt tấn công.

## 4. Java 17: enum cho tên cột và hướng sắp xếp

Dưới đây là lớp `SortPolicy.java` **độc lập, biên dịch bằng Java 17+**; nó chỉ tạo mệnh đề `ORDER BY` cho một query dùng alias `p`.

```java
import java.util.Locale;

public final class SortPolicy {
    private SortPolicy() {}

    public enum Field {
        NAME("name", "p.name"),
        PRICE("price", "p.price"),
        CREATED_AT("createdAt", "p.created_at");

        private final String key;
        private final String expression;

        Field(String key, String expression) {
            this.key = key;
            this.expression = expression;
        }

        static Field fromClient(String raw) {
            if (raw == null) {
                return CREATED_AT; // Default rõ ràng.
            }
            for (Field field : values()) {
                if (field.key.equals(raw)) {
                    return field;
                }
            }
            throw new IllegalArgumentException("Unsupported sort field");
        }
    }

    public enum Direction {
        ASC, DESC;

        static Direction fromClient(String raw) {
            if (raw == null) {
                return DESC;
            }
            String normalized = raw.strip().toUpperCase(Locale.ROOT);
            return switch (normalized) {
                case "ASC" -> ASC;
                case "DESC" -> DESC;
                default -> throw new IllegalArgumentException(
                    "Unsupported direction");
            };
        }
    }

    public static String orderBy(String rawField, String rawDirection) {
        Field field = Field.fromClient(rawField);
        Direction direction = Direction.fromClient(rawDirection);
        return "ORDER BY " + field.expression
             + " " + direction.name() + ", p.id ASC";
    }

    public static void main(String[] args) {
        System.out.println(orderBy("price", "desc"));
        System.out.println(orderBy(null, null));
        try {
            orderBy("price DESC; DROP TABLE products", "asc");
        } catch (IllegalArgumentException expected) {
            System.out.println("rejected=true");
        }
    }
}
```

Chạy:

```bash
javac SortPolicy.java
java SortPolicy
```

**Stdout:**

```text
ORDER BY p.price DESC, p.id ASC
ORDER BY p.created_at DESC, p.id ASC
rejected=true
```

Đoạn này không lấy `rawField` hay `rawDirection` để chèn thẳng vào SQL. Chúng **chỉ chọn enum**, còn text dùng cho SQL đến từ constant của enum.

**Một lưu ý:** `Field.fromClient(null)` áp default; chuỗi rỗng hoặc key lạ vẫn lỗi. `Direction.fromClient` dùng `Locale.ROOT` để tránh việc chuyển chữ hoa phụ thuộc locale máy chủ. Không cho người dùng gửi nguyên `"ASC NULLS LAST"` vì nó không phải một trong hai giá trị enum.

### 4.1. Bất biến cần giữ trong toàn ứng dụng

Khi đã parse thành `Field` và `Direction`, những tầng bên dưới nên nhận **kiểu dữ liệu đã validate** thay vì quay lại lấy chuỗi request raw. Nếu thêm mapping qua `Map<String,String>` thì map phải là bất biến, được tạo trong source code, và không có mục nào nhận expression do client cung cấp.

Cần tránh việc người khác mở rộng API theo cách vô tình:

```java
// SAI: "fallback" đưa input chưa được duyệt trở lại SQL.
String sqlColumn = known.getOrDefault(rawSort, rawSort);
```

Một fallback đúng là ném lỗi, hoặc dùng **một giá trị default cố định** chỉ cho trường hợp thiếu input theo contract; không bao giờ giữ nguyên input lạ.

## 5. Sắp xếp ổn định khi có phân trang

Với dữ liệu có nhiều hàng trùng giá:

```sql
SELECT id, name, price
FROM products
ORDER BY price DESC;
```

Nếu hai hàng cùng `price=25.00`, thứ tự tương đối của chúng không được bảo đảm. Hai request phân trang khác nhau có thể lấy những hàng chồng lấn hoặc bỏ sót nếu ranh giới trang trùng khóa sort.

Khi `id` là khóa duy nhất, thêm tie-breaker:

```sql
SELECT id, name, price
FROM products
ORDER BY price DESC, id ASC
LIMIT 20 OFFSET 40;
```

Truy vấn giờ có **thứ tự xác định cho một trạng thái dữ liệu**. Nếu dữ liệu bị chèn/xóa/cập nhật giữa những request, offset pagination vẫn có thể lệch trang: tie-breaker giúp thứ tự ổn định, không tạo snapshot. Khi yêu cầu cao hơn, xem xét transaction snapshot/keyset pagination.

### 5.1. Vì sao LIMIT/OFFSET cần kiểm soát riêng?

`page` và `size` đến từ client là **giá trị số**, không phải identifier. Nên:

- `page >= 0`, `size` nằm trong cận (ví dụ `1..100`).
- Tính `offset = page × size` có kiểm soát overflow.
- Bind `size`/`offset` bằng `?` khi dialect hỗ trợ, không nối raw input.
- Xem xét trần page, index và sức tải; offset lớn vẫn tốn tài nguyên DB.
- Không dùng `JdbcTemplate.setMaxRows` để thay toàn bộ thiết kế pagination.

Với keyset pagination theo `price DESC, id ASC`, mẫu điều kiện sau là một lựa chọn:

```sql
SELECT p.id, p.name, p.price
FROM products p
WHERE p.active = ?
  AND (p.price < ? OR (p.price = ? AND p.id > ?))
ORDER BY p.price DESC, p.id ASC
LIMIT ?;
```

Giá `lastPrice` xuất hiện hai lần và `lastId` đều phải được bind. Nếu người dùng đổi sort field/hướng, cần đổi điều kiện con trỏ cho phù hợp bằng một mẫu query **đã duyệt**, không dùng công thức keyset cũ cho mọi kiểu sort.

## 6. Spring JdbcTemplate: ghép cấu trúc tin cậy, bind dữ liệu

Mẫu truy vấn chuẩn:

```java
String safeOrderBy = SortPolicy.orderBy(sortKey, direction);
String sql = """
    SELECT p.id, p.name, p.price
    FROM products p
    WHERE p.active = ? AND p.price >= ?
    """ + safeOrderBy + " LIMIT ? OFFSET ?";

List<String> names = jdbc.query(
    sql,
    (rs, rowNum) -> rs.getString("name"),
    true, minimumPrice, pageSize, offset
);
```

Đây là **snippet trong repository đã có `JdbcTemplate jdbc`**. Phần duy nhất được ghép vào SQL là kết quả `SortPolicy.orderBy` từ enum cố định. Bốn giá trị lọc/phân trang đi qua `PreparedStatement`.

Cách sai khi chuyển sang `NamedParameterJdbcTemplate`:

```java
// :sort chỉ là giá trị, không biến thành identifier.
String sql = """
    SELECT p.id, p.name
    FROM products p
    WHERE p.active = :active
    ORDER BY :sort
    """;
```

`:active` là bind value, nhưng `:sort` không giúp tạo cấu trúc động. Named parameters chỉ tiện về cú pháp đặt tên dữ liệu; chúng không thay thế allow-list cho tên cột và SQL keyword.

## 7. Dự án Spring Boot + H2 hoàn chỉnh

Ví dụ Java 17+ sau có thể chạy trên Spring Boot 3.3.x với Spring JDBC và H2. Nó tạo bốn hàng, hai hàng trùng giá, chạy hai loại sort và từ chối một chuỗi chứa SQL không hợp lệ **trước khi gọi JDBC**.

### 7.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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

### 7.2. src/main/resources/application.properties

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:sort_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
```

### 7.3. src/main/java/example/ProductSortDemoApplication.java

```java
package example;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Locale;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@SpringBootApplication
public class ProductSortDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProductSortDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, ProductRepository repo) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE products (
                    id BIGINT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    price DECIMAL(10, 2) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    active BOOLEAN NOT NULL
                )
                """);

            jdbc.update("""
                INSERT INTO products(id, name, price, created_at, active)
                VALUES (?, ?, ?, ?, ?)
                """, 1L, "Pen", new BigDecimal("10.00"),
                Timestamp.valueOf("2026-01-01 08:00:00"), true);

            jdbc.update("""
                INSERT INTO products(id, name, price, created_at, active)
                VALUES (?, ?, ?, ?, ?)
                """, 2L, "Notebook", new BigDecimal("25.00"),
                Timestamp.valueOf("2026-01-02 08:00:00"), true);

            jdbc.update("""
                INSERT INTO products(id, name, price, created_at, active)
                VALUES (?, ?, ?, ?, ?)
                """, 3L, "Clip", new BigDecimal("25.00"),
                Timestamp.valueOf("2026-01-03 08:00:00"), true);

            jdbc.update("""
                INSERT INTO products(id, name, price, created_at, active)
                VALUES (?, ?, ?, ?, ?)
                """, 4L, "Ruler", new BigDecimal("8.00"),
                Timestamp.valueOf("2026-01-04 08:00:00"), false);

            BigDecimal minPrice = new BigDecimal("10.00");

            var byPrice = repo.find("price", "DESC", minPrice, 0, 10);
            System.out.println("priceDesc=" + byPrice.stream()
                .map(ProductRepository.ProductRow::name).toList());

            var byName = repo.find("name", "asc", minPrice, 0, 10);
            System.out.println("nameAsc=" + byName.stream()
                .map(ProductRepository.ProductRow::name).toList());

            boolean rejected = false;
            try {
                repo.find(
                    "price DESC; DROP TABLE products",
                    "DESC", minPrice, 0, 10);
            } catch (IllegalArgumentException expected) {
                rejected = true;
            }
            System.out.println("invalidRejected=" + rejected);

            Integer remaining = jdbc.queryForObject(
                "SELECT COUNT(*) FROM products", Integer.class);
            System.out.println("remaining=" + remaining);
        };
    }
}

@Repository
class ProductRepository {
    private final JdbcTemplate jdbc;

    ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record ProductRow(
        long id,
        String name,
        BigDecimal price,
        LocalDateTime createdAt
    ) {}

    private enum SortField {
        NAME("name", "p.name"),
        PRICE("price", "p.price"),
        CREATED_AT("createdAt", "p.created_at");

        private final String key;
        private final String sqlExpression;

        SortField(String key, String sqlExpression) {
            this.key = key;
            this.sqlExpression = sqlExpression;
        }

        static SortField fromClient(String raw) {
            if (raw == null) return NAME;
            for (SortField field : values()) {
                if (field.key.equals(raw)) return field;
            }
            throw new IllegalArgumentException(
                "Unsupported sort field");
        }
    }

    private enum SortDirection {
        ASC, DESC;

        static SortDirection fromClient(String raw) {
            if (raw == null) return ASC;
            String value = raw.strip().toUpperCase(Locale.ROOT);
            return switch (value) {
                case "ASC" -> ASC;
                case "DESC" -> DESC;
                default -> throw new IllegalArgumentException(
                    "Unsupported sort direction");
            };
        }
    }

    public List<ProductRow> find(
        String sortKey,
        String rawDirection,
        BigDecimal minPrice,
        int page,
        int size
    ) {
        SortField field = SortField.fromClient(sortKey);
        SortDirection direction = SortDirection.fromClient(rawDirection);

        if (minPrice == null || minPrice.signum() < 0)
            throw new IllegalArgumentException("Invalid minimum price");
        if (page < 0 || page > 10_000)
            throw new IllegalArgumentException("Invalid page");
        if (size < 1 || size > 100)
            throw new IllegalArgumentException("Invalid size");

        int offset = Math.multiplyExact(page, size);

        String sql = """
            SELECT p.id, p.name, p.price, p.created_at
            FROM products p
            WHERE p.active = ? AND p.price >= ?
            ORDER BY %s %s, p.id ASC
            LIMIT ? OFFSET ?
            """.formatted(field.sqlExpression, direction.name());

        return jdbc.query(
            sql,
            (rs, rowNum) -> new ProductRow(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getBigDecimal("price"),
                rs.getTimestamp("created_at").toLocalDateTime()
            ),
            true, minPrice, size, offset
        );
    }
}
```

**Lý do an toàn:** `SortField.fromClient` và `SortDirection.fromClient` trả enum hoặc ném exception. Chỉ `field.sqlExpression` và `direction.name()` từ hằng enum đi vào hai vị trí `%s` của `String.formatted`. Điều này khác căn bản với `.formatted(rawSortKey, rawDirection)`. Dữ liệu boolean, ngưỡng giá và số phân trang **vẫn bind qua `?`**. `p.id ASC` giải quyết tie-breaker cho hai sản phẩm cùng giá.

### 7.4. Chạy và kiểm tra kết quả

Trong project có Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Với Java 17+, Gradle và dependency tải được, H2 hoạt động theo cấu hình, **các dòng do `System.out` của ví dụ in ra** là:

```text
priceDesc=[Notebook, Clip, Pen]
nameAsc=[Clip, Notebook, Pen]
invalidRejected=true
remaining=4
```

Spring Boot có thể in thêm log. Hai sản phẩm Notebook (id=2) và Clip (id=3) cùng giá 25.00; `id ASC` phá hòa khiến Notebook đứng trước. Ruler không active nên bị loại khỏi cả hai danh sách nhưng vẫn tồn tại trong bảng (remaining = 4).

Lưu ý: ví dụ dùng cú pháp `LIMIT ? OFFSET ?` của H2, cũng có trong PostgreSQL. Khi chuyển sang SQL Server, Oracle hoặc DBMS khác, cú pháp phân trang và xử lý `NULL` có thể khác; cần thích nghi query **bằng các fragment do server kiểm soát**, không bằng cách cho user gửi SQL.

## 8. Controller và quy tắc trả lỗi

Ví dụ API:

```text
GET /products?sort=price&direction=DESC&page=0&size=20
```

Ngay cả khi UI chỉ hiển thị dropdown an toàn, endpoint vẫn phải xem URL/query params là **không đáng tin cậy**. Client có thể gọi trực tiếp bằng script hoặc sửa request.

Nên tách trách nhiệm:

1. **Controller:** parse tham số, kiểm tra kiểu/giới hạn, thống nhất default và HTTP status.
2. **Service:** quyết định người dùng nào được phép xem tập dữ liệu nào và sort theo field nào trong nghiệp vụ.
3. **Repository:** dùng allow-list để tạo SQL fragment và bind dữ liệu.
4. **DB:** thực thi phân quyền hàng/tenant, constraints, index và giới hạn tài nguyên.

Ví dụ method controller (không phải file standalone; giả định đã có các import Spring MVC, `ProductRepository repo`):

```java
@GetMapping("/products")
public List<ProductRepository.ProductRow> products(
        @RequestParam(required = false) String sort,
        @RequestParam(required = false) String direction,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    return repo.find(
        sort, direction, new BigDecimal("0.00"), page, size);
}
```

Đối với input sai, nên định nghĩa exception validation chuyên biệt và `@ExceptionHandler`/`@ControllerAdvice` để phản hồi 400. Tránh bắt **mọi** `IllegalArgumentException` của ứng dụng rồi coi đó là lỗi người dùng: nhiều lỗi lập trình nội bộ cũng có thể mang kiểu exception này.

Phản hồi minh họa:

```json
{
  "error": "INVALID_SORT",
  "allowed": ["name", "price", "createdAt"]
}
```

Đây là **khóa API công khai**, không phải danh sách đầy đủ tên cột vật lý. Đừng echo toàn bộ input đáng ngờ hoặc SQL nguyên văn kèm stack trace ra response/log.

**Phân quyền độc lập:** Sắp xếp an toàn không làm truy vấn tự động lọc đúng tenant hay user. Ví dụ `WHERE p.tenant_id = ?` phải được ràng buộc với tenant ID từ context xác thực đáng tin cậy, không tin chuỗi URL do client tự đặt. Ngay cả sort trên cột không được SELECT trả về cũng có thể làm rò rỉ thông tin qua thứ tự kết quả; việc cho phép cột nào là quyết định nghiệp vụ, không chỉ SQL parser.

## 9. Nhiều cột sắp xếp: parse từng lựa chọn

Một API có thể hỗ trợ danh sách:

```text
[("price", "DESC"), ("name", "ASC")]
```

Không nên lấy chuỗi `sort=price DESC,name ASC` rồi ghép thẳng vào SQL. Thay vào đó:

- Giới hạn số tiêu chí (ví dụ tối đa ba).
- Parse từng tên trường thành khóa đã nằm trong allow-list.
- Parse từng hướng thành `ASC` hoặc `DESC`.
- Từ chối tiêu chí trùng nhau, null/lỗi cú pháp.
- Giữ đúng thứ tự tiêu chí đã được chọn.
- Thêm khóa phá hòa duy nhất nếu chưa có.
- Không cho raw fragment như `COLLATE...`, `NULLS...` hoặc `LOWER(...)` lọt vào câu SQL.

Lớp `MultiSortBuilder.java` độc lập cho Java 17:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public final class MultiSortBuilder {
    private MultiSortBuilder() {}

    public record RequestedSort(String field, String direction) {}

    private static String sqlColumn(String field) {
        if (field == null)
            throw new IllegalArgumentException("Missing sort field");
        return switch (field) {
            case "name" -> "p.name";
            case "price" -> "p.price";
            case "createdAt" -> "p.created_at";
            case "id" -> "p.id";
            default -> throw new IllegalArgumentException(
                "Unsupported field");
        };
    }

    private static String sqlDirection(String raw) {
        if (raw == null)
            throw new IllegalArgumentException("Missing direction");
        String value = raw.strip().toUpperCase(Locale.ROOT);
        return switch (value) {
            case "ASC", "DESC" -> value;
            default -> throw new IllegalArgumentException(
                "Unsupported direction");
        };
    }

    public static String build(List<RequestedSort> sorts) {
        if (sorts == null || sorts.isEmpty())
            return "ORDER BY p.id ASC";
        if (sorts.size() > 3)
            throw new IllegalArgumentException("Too many sorts");

        List<String> clauses = new ArrayList<>();
        Set<String> seen = new HashSet<>();

        for (RequestedSort sort : sorts) {
            if (sort == null || !seen.add(sort.field()))
                throw new IllegalArgumentException(
                    "Missing or duplicate sort key");
            clauses.add(
                sqlColumn(sort.field()) + " "
                + sqlDirection(sort.direction())
            );
        }
        if (!seen.contains("id")) clauses.add("p.id ASC");
        return "ORDER BY " + String.join(", ", clauses);
    }

    public static void main(String[] args) {
        System.out.println(build(List.of(
            new RequestedSort("price", "DESC"),
            new RequestedSort("name", "ASC")
        )));
        System.out.println(build(List.of()));
    }
}
```

Lệnh:

```bash
javac MultiSortBuilder.java
java MultiSortBuilder
```

Stdout:

```text
ORDER BY p.price DESC, p.name ASC, p.id ASC
ORDER BY p.id ASC
```

`HashSet` chỉ để chống trùng, **không** điều khiển thứ tự (các fragment được thêm tuần tự vào `ArrayList`). Không xem `sort.split(",")` là đã được bảo vệ: nếu API nhận cú pháp gọn như `name,-price`, mỗi token sau khi split vẫn phải chuyển thành kiểu đã được validate, không bao giờ thành raw SQL.

Khi API hỗ trợ keyset pagination cho nhiều sort key, điều kiện so sánh con trỏ phải khớp **đúng thứ tự và hướng** của các trường. Không dùng một điều kiện cursor tổng quát cho mọi tổ hợp nếu chưa chứng minh tính đúng và hiệu năng.

## 10. Tình huống JOIN và biểu thức sắp xếp

Với truy vấn có nhiều bảng:

```sql
SELECT p.id, p.name, c.name AS category_name
FROM products p
JOIN categories c ON c.id = p.category_id
ORDER BY p.name ASC, p.id ASC;
```

Hai bảng đều có `name`, nên dùng `ORDER BY name` không có alias có thể gây ambiguous column hoặc ngữ nghĩa không như mong đợi. Mapping nên rõ ràng:

| API key | Fragment đúng với query JOIN |
| --- | --- |
| `productName` | `p.name` |
| `categoryName` | `c.name` |
| `createdAt` | `p.created_at` |

Mỗi query có thể có **allow-list riêng**. Không tái sử dụng mapping `name → p.name` cho mọi truy vấn nếu alias hoặc nghiệp vụ không khớp.

### 10.1. Sắp xếp theo biểu thức cố định

Ví dụ muốn sản phẩm còn hàng trước, sau đó giá thấp trước:

```sql
ORDER BY CASE WHEN p.stock_count > 0 THEN 0 ELSE 1 END ASC,
         p.price ASC,
         p.id ASC;
```

API có thể công bố khóa `availabilityThenPrice` và server map trực tiếp đến một **fragment đầy đủ cố định** như trên. Client không được đưa `CASE WHEN ...` tùy ý.

### 10.2. NULLS FIRST/LAST và collation

Một số dialect cho phép:

```sql
ORDER BY p.created_at DESC NULLS LAST, p.id ASC;
```

Nhưng sự hỗ trợ và thứ tự mặc định của `NULL` khác nhau theo DBMS. Collation ảnh hưởng cách xếp chuỗi có dấu, chữ hoa và Unicode. Nếu muốn sort không phân biệt hoa thường hoặc luôn đưa NULL xuống cuối, mapping cần chọn biểu thức/keyword cố định được kiểm thử theo dialect và index, không để người dùng nhập tên collation hoặc `NULLS ...` vào query.

## 11. Hiệu năng và giới hạn lựa chọn hợp lệ

Allow-list không chỉ chống injection; nó còn giới hạn các sort expression tốn tài nguyên:

- Sort theo index phù hợp (`created_at`, `id`) có thể có plan tốt.
- `LOWER(p.name)` có thể cần functional index/collation/index riêng.
- Sort theo cột thuộc bảng JOIN khác có thể tạo thao tác sort lớn.
- Sort sau filter thiếu index có thể phải scan nhiều hàng.
- `OFFSET` lớn có thể khiến DB bỏ qua nhiều dòng trước khi trả trang nhỏ.
- Tổ hợp nhiều trường trong `ORDER BY` cần đánh giá index và plan phù hợp.

Tối ưu bằng `EXPLAIN` và dữ liệu đại diện. Không cho client sort mọi cột chỉ vì chúng tồn tại hoặc parser có thể tạo câu hợp lệ. Cần cân nhắc cả **quyền dữ liệu**, **ý nghĩa UI** và **chi phí truy vấn**.

Một số ORM/framework có kiểu `Sort`/sort descriptor: chúng giúp biểu diễn cấu trúc, nhưng không tự quyết định business allow-list. Vẫn phải xác định **property nào endpoint được phép nhận** và tránh các unsafe expression do người dùng điều khiển.

## 12. Dùng các biến thể SQL hoàn toàn cố định khi số lựa chọn ít

Khi API chỉ có hai chế độ, có thể không cần xây phần `ORDER BY` bằng fragment riêng; thay vào đó chọn nguyên câu SQL theo enum:

```java
String sql = switch (mode) {
    case NAME_A_TO_Z -> """
        SELECT p.id, p.name
        FROM products p
        WHERE p.active = ?
        ORDER BY p.name ASC, p.id ASC
        """;
    case PRICE_HIGH_FIRST -> """
        SELECT p.id, p.name
        FROM products p
        WHERE p.active = ?
        ORDER BY p.price DESC, p.id ASC
        """;
};
```

Đây là snippet ở bên trong method có enum `mode`; không phải file độc lập. Phương pháp này dễ kiểm tra vì mọi query text đều cố định. Khi có nhiều trường/hướng, enum fragment mapper dễ mở rộng hơn. Chọn cách đơn giản nhất **không đưa raw input vào cú pháp**.

Có thể thấy giải pháp khác dùng `ORDER BY CASE WHEN ? = 'price' THEN price ...` để bind lựa chọn trong một query; cần thận trọng vì khác kiểu dữ liệu giữa các nhánh, thứ tự và ảnh hưởng index/plan. Không dùng nó như cách thay mặc định cho allow-list mà không phân tích truy vấn.

## 13. Kiểm thử an toàn và tính đúng

Cần kiểm tra cả mapper và dữ liệu trả về:

| Input/điều kiện | Kết quả kỳ vọng |
| --- | --- |
| `sort=price&direction=DESC` | `ORDER BY p.price DESC, p.id ASC` |
| `sort=name&direction=asc` | `ORDER BY p.name ASC, p.id ASC` |
| `sort=createdAt` | Chọn `p.created_at`, default direction đúng contract. |
| `sort` thiếu | Dùng sort mặc định. |
| `sort=unknown` | Validation error, không chạy query động. |
| `sort=p.price` | Từ chối nếu hợp đồng chỉ cho khóa `price`. |
| `sort=price DESC; DROP TABLE products` | Từ chối, không chèn payload vào SQL. |
| `sort=LOWER(name)` | Từ chối trừ khi có key riêng do server định nghĩa. |
| `direction=ASC NULLS LAST` | Từ chối vì hướng không thuộc hai enum. |
| `sort=name,price` với API single-sort | Từ chối; multi-sort phải parse riêng. |
| `size=1000000` hoặc `page=-1` | Từ chối theo giới hạn. |
| Hai hàng trùng giá | Thứ tự `id ASC` phá hòa ổn định. |
| Kết quả thuộc tenant khác | Không trả ra: ràng buộc tenant/permission trong `WHERE`. |

### 13.1. Unit test JUnit cho SortPolicy

Đoạn kiểm thử Java 17 dưới đây cần `junit-jupiter` trên test classpath và lớp `SortPolicy` ở mục 4:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class SortPolicyTest {
    @Test
    void acceptsKnownSort() {
        assertEquals(
            "ORDER BY p.price DESC, p.id ASC",
            SortPolicy.orderBy("price", "desc"));
    }

    @Test
    void rejectsUnknownSyntax() {
        assertThrows(IllegalArgumentException.class,
            () -> SortPolicy.orderBy(
                "price DESC; DROP TABLE products", "ASC"));
        assertThrows(IllegalArgumentException.class,
            () -> SortPolicy.orderBy(
                "name", "ASC NULLS LAST"));
    }
}
```

Unit test chỉ kiểm tra mapper. Cần integration test trên DBMS thật/H2 cho SQL hợp lệ, thứ tự, phân trang, duplicate values, quyền truy cập và các giới hạn. Có thể fuzz input bằng Unicode, quote, dấu chấm phẩy, khoảng trắng, dấu ngoặc, chuỗi rất dài, nhưng không log vô hạn payload.

Bất biến bảo mật cần bảo toàn:

> **Bất kỳ input chưa được cho phép đều không thể xuất hiện trong câu SQL cuối cùng như identifier, keyword hoặc expression.**

## 14. Lỗi thường gặp khi review code

| Lỗi | Vì sao sai | Sửa |
| --- | --- | --- |
| `"ORDER BY " + request.sort` | Đưa input thành SQL structure. | Map khóa API qua allow-list. |
| `ORDER BY ?` với bind `"price"` | `?` biểu diễn giá trị, không phải identifier. | Chọn fragment cố định, bind WHERE. |
| Regex `[A-Za-z_]+` thay allow-list | Cột nhạy cảm vẫn có thể khớp. | Enum/switch cho từng endpoint. |
| Escape dấu nháy ở sort key | Escape value không giải quyết grammar/permission. | Ánh xạ đến constant. |
| Allow-list field nhưng nối raw direction | Keyword `ASC/DESC` cũng cần validate. | Enum hướng/boolean. |
| Fallback `map.getOrDefault(key,key)` | Input sai lại đi thẳng vào SQL. | Ném lỗi hoặc default cố định cho input thiếu. |
| Dùng key DB như `p.price` ở API | Lộ implementation và tạo phụ thuộc schema. | Khóa công khai `price` → `p.price`. |
| Sort giá trùng thiếu `id` | Trang có thể không ổn định. | Thêm khóa phá hòa duy nhất. |
| Không validate LIMIT/OFFSET | Tải lớn, số âm/overflow. | Giới hạn và bind số. |
| Không ràng buộc tenant | Sort an toàn không đồng nghĩa query có phân quyền. | WHERE tenant/user đáng tin cậy. |
| Dùng mapping cùng tên cho mọi JOIN | Alias sai/ambiguous. | Mapping theo query/endpoint. |
| Cho sort các cột DB metadata tùy ý | Có thể lộ dữ liệu/ngốn tài nguyên. | Chọn tập cột theo nghiệp vụ. |

## 15. Hỏi đáp tự kiểm tra

**1.** Vì sao `ORDER BY ?` với bind `"p.price"` không tương đương `ORDER BY p.price`?

**Trả lời:** Placeholder biểu diễn một data value, không biến chuỗi thành tham chiếu identifier. DB có thể coi đó là hằng hoặc không chấp nhận.

**2.** Đã dùng `JdbcTemplate.query(sql, rowMapper, args...)` thì nối `sort` từ HTTP vào SQL có tự an toàn không?

**Trả lời:** Không. Chỉ những giá trị truyền trong `args` được bind. Text SQL tạo trước đó vẫn chứa phần input không được kiểm soát nếu bạn nối raw sort.

**3.** Regex chỉ cho chữ cái có thể thay allow-list không?

**Trả lời:** Không. Nó không biết cột nào được phép theo nghiệp vụ, quyền và chi phí truy vấn.

**4.** Hướng sắp xếp nên được xử lý thế nào?

**Trả lời:** Parse thành enum/boolean với đúng `ASC` và `DESC`; unknown phải bị từ chối. Không nối raw direction.

**5.** Tại sao phải thêm `id` làm khóa phụ?

**Trả lời:** Khi các hàng bằng nhau ở khóa sort chính, cần tie-breaker duy nhất để có thứ tự xác định và hỗ trợ phân trang ổn định hơn.

**6.** Với query JOIN có `p.name` và `c.name`, client gửi `sort=name` có thể dùng raw `ORDER BY name` không?

**Trả lời:** Không nên. Định nghĩa rõ tên khóa `productName`/`categoryName` rồi map thành `p.name`/`c.name` đúng context.

**7.** Nếu muốn hỗ trợ sort không phân biệt hoa thường hoặc `NULLS LAST` thì làm sao?

**Trả lời:** Đặt một lựa chọn riêng và map thành fragment cố định đã kiểm thử theo DBMS. Không nhận biểu thức SQL tùy ý từ client.

**8.** Nếu `page=0` và `size=20`, có cần bind `LIMIT` và `OFFSET` không?

**Trả lời:** Khi dialect/driver hỗ trợ, nên validate kiểu số/cận rồi bind. Đồng thời quản lý query plan, giới hạn số trang và quyền dữ liệu.

## 16. Checklist trước khi triển khai

- [ ] Khóa sort API được công bố rõ, tách khỏi SQL/schema.
- [ ] Mọi sort key được map sang fragment **cố định do server viết**.
- [ ] Hướng chỉ là `ASC`/`DESC` sau validation.
- [ ] Unknown không bao giờ rơi về raw input.
- [ ] Data values tiếp tục được bind qua `JdbcTemplate`.
- [ ] Query JOIN dùng alias phù hợp và allow-list theo query.
- [ ] Multi-sort giới hạn số mục, chống duplicate, validate từng tiêu chí.
- [ ] Sắp xếp có khóa phá hòa duy nhất; pagination xử lý biến động dữ liệu theo yêu cầu.
- [ ] Page/size và các filter có kiểu/cận; ngăn overflow và quá tải.
- [ ] Phân quyền hàng, tenant, cột được xử lý độc lập.
- [ ] Đã test trường hợp input độc hại, SQL expression, giá trùng, kết quả phân trang và lỗi.
- [ ] Đã đánh giá `EXPLAIN`, index, collation, NULL order trên DBMS triển khai.

## 17. Tài liệu tham khảo

- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet): parameterized data values và allow-list validation cho identifier/`ASC`/`DESC`.
- [Spring Framework — JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `query(String, RowMapper<T>, Object...)` và bind parameters.
- [Java SE — PreparedStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html): tham số JDBC là dữ liệu.
- [PostgreSQL — SELECT và ORDER BY](https://www.postgresql.org/docs/current/sql-select.html): cú pháp `ORDER BY`, nhiều tiêu chí, `ASC/DESC` và `NULLS FIRST/LAST`.
- [H2 — SQL Commands](https://h2database.com/html/commands.html): cú pháp query dùng cho chương trình mẫu.

**Kết luận:** Hãy cho client chọn **một trong các cách sắp xếp được ứng dụng hỗ trợ**, không cho client gửi SQL. Enum/allow-list quyết định tên cột và keyword; JDBC bind xử lý giá trị; khóa phá hòa, phân quyền và kiểm thử DBMS bảo đảm kết quả đúng và ổn định.

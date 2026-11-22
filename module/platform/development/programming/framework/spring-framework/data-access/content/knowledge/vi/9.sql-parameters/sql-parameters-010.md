# Giữ số lượng tham số và kiểu dữ liệu tương thích với câu lệnh

> **Nguyên tắc:** Khi dùng JDBC hoặc Spring `JdbcTemplate`, mỗi tham số đầu vào phải được gắn vào **đúng vị trí, đủ số lượng và bằng kiểu dữ liệu tương thích với biểu thức/cột SQL tương ứng**. Với dấu `?`, JDBC đánh số vị trí bắt đầu từ **1**, theo thứ tự xuất hiện trong câu SQL; với `NamedParameterJdbcTemplate`, giá trị được ghép theo **tên tham số** rồi Spring chuyển sang vị trí JDBC. Ghép đúng số lượng nhưng **đảo sai thứ tự** hoặc dùng **kiểu không tương thích** vẫn có thể gây exception hoặc, nguy hiểm hơn, ghi sai dữ liệu.

Trong Spring Framework Data Access, tham số SQL là một phần của **hợp đồng giữa câu lệnh và giá trị Java**. Bài này hướng dẫn đọc hợp đồng đó, kiểm tra tính nhất quán khi thêm điều kiện động, xử lý `NULL`, số/ngày/giờ, danh sách `IN`, batch, kiểm thử và cách chẩn đoán sai lệch.

## 1. Ba điều kiện phải đúng cùng lúc

Xét bảng đơn hàng đơn giản:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total DECIMAL(12, 2) NOT NULL,
    note VARCHAR(100) NULL
);
```

Câu cập nhật:

```sql
UPDATE orders
SET status = ?, total = ?
WHERE id = ?;
```

Câu lệnh có **ba vị trí cần bind**, theo thứ tự:

| Vị trí JDBC | Biểu thức SQL | Kiểu DB mong đợi | Giá trị Java phù hợp |
| ---: | --- | --- | --- |
| 1 | `status = ?` | `VARCHAR` | `String`, ví dụ `"PAID"` |
| 2 | `total = ?` | `DECIMAL(12,2)` | `BigDecimal`, ví dụ `new BigDecimal("129.50")` |
| 3 | `id = ?` | `BIGINT` | `long`/`Long`, ví dụ `10L` |

Lời gọi Spring JDBC đúng:

```java
int changed = jdbc.update(
    "UPDATE orders SET status = ?, total = ? WHERE id = ?",
    "PAID",
    new java.math.BigDecimal("129.50"),
    10L
);
```

`jdbc` ở đây là biến `JdbcOperations`/`JdbcTemplate` đã được cấu hình trong một method; đoạn code không phải ứng dụng độc lập. Chữ ký `update(String sql, Object... args)` nhận các giá trị theo thứ tự `?`. `changed` là **số hàng bị tác động**, không phải số tham số. Nếu không có đơn hàng `id=10`, kết quả có thể là 0 dù các tham số vẫn được bind đúng.

Ba chiều phải kiểm tra:

1. **Số lượng:** ba dấu `?` là ba giá trị, không phải hai hoặc bốn.
2. **Thứ tự/tên:** `"PAID"` thuộc cột status, `BigDecimal` thuộc cột total, `10L` thuộc điều kiện id. Tên biến Java không tự định vị tham số `?`.
3. **Tương thích kiểu:** Java `String` phù hợp với `VARCHAR`, `BigDecimal` phù hợp với `DECIMAL`, `Long` phù hợp với `BIGINT`; đồng thời giá trị phải thỏa chiều dài, độ chính xác, `NOT NULL`, `CHECK`, khóa ngoại và quy tắc miền nghiệp vụ.

Khớp một chiều chưa đủ. Truyền hai `String` đảo vị trí cho hai cột cùng `VARCHAR` có thể không gây lỗi SQL nhưng **làm sai dữ liệu**. Ngược lại, truyền `"one hundred"` vào `DECIMAL` có thể thất bại khi driver/DB cố chuyển kiểu. Một số DBMS tự ép chuỗi số thành số, nhưng **không nên dựa vào ép kiểu ngầm** để che code bind sai.

## 2. Dấu hỏi chấm trong PreparedStatement và vị trí bắt đầu từ 1

`java.sql.PreparedStatement` là API JDBC dùng câu SQL có parameter markers `?` và các setter như `setLong`, `setString`, `setBigDecimal`.

```java
String sql = "UPDATE orders SET status = ?, total = ? WHERE id = ?";
try (java.sql.PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "PAID");
    ps.setBigDecimal(2, new java.math.BigDecimal("129.50"));
    ps.setLong(3, 10L);
    int changed = ps.executeUpdate();
}
```

Đây là **mảnh code bên trong method** có `java.sql.Connection connection` đã được lấy đúng cách; `try-with-resources` đóng statement sau khi dùng. Chỉ số tham số là **1, 2, 3**, không phải 0, 1, 2. Điều này khác Java array/list thường bắt đầu ở 0.

### Khi thiếu hoặc thừa tham số

Câu SQL vẫn có ba `?` nhưng chỉ bind hai:

```java
ps.setString(1, "PAID");
ps.setBigDecimal(2, new java.math.BigDecimal("129.50"));
// Chưa bind tham số số 3.
ps.executeUpdate();
```

Thông thường driver báo lỗi tại lúc execute vì một parameter chưa được đặt. Nếu thử `ps.setLong(4, 10L)` trong khi chỉ có ba marker, driver có thể ném `SQLException` vì chỉ số không hợp lệ ngay tại setter. Thời điểm báo lỗi, SQLState, mã lỗi và thông điệp **phụ thuộc driver/DBMS**.

Với `JdbcTemplate`, khi Spring dịch `SQLException`, tầng gọi thường nhận một subclass của `DataAccessException`, nhưng không nên hứa một subclass cố định cho mọi lỗi đếm tham số hoặc lỗi chuyển kiểu. Cần xem root cause và SQL thực tế.

### Đếm tham số theo SQL đã chuẩn bị, không theo cảm giác

Trong ví dụ đơn giản, ba `?` tương ứng ba giá trị. Với SQL phức tạp hơn, dấu hỏi chấm có thể xuất hiện trong chuỗi literal, comment hoặc cú pháp operator đặc thù theo dialect. **Không tự viết thuật toán `sql.chars().filter(ch -> ch == '?')` để khẳng định số marker chuẩn cho mọi database.** Driver/JDBC parser mới là nơi quyết định cú pháp được hiểu. `PreparedStatement.getParameterMetaData().getParameterCount()` có thể hỗ trợ kiểm tra, nhưng việc cung cấp metadata và thông tin kiểu chính xác cũng phụ thuộc JDBC driver.

Một phần khác của hợp đồng: dấu `?` chỉ đại diện cho **giá trị SQL**, không phải tên bảng/cột hay toàn bộ mệnh đề SQL. `ORDER BY ?` không phải cách tham số hóa an toàn tên cột sắp xếp; nếu tên cột do người dùng chọn, ứng dụng cần whitelist các cột/sort mode được phép.

## 3. Khớp số nhưng sai thứ tự vẫn nguy hiểm

Với câu:

```sql
UPDATE orders SET status = ?, note = ? WHERE id = ?;
```

Mẫu sai:

```java
jdbc.update(
    "UPDATE orders SET status = ?, note = ? WHERE id = ?",
    "Called customer",
    "PAID",
    10L
);
```

Ở đây Java truyền đủ ba giá trị, tất cả đúng kiểu SQL (`VARCHAR`, `VARCHAR`, `BIGINT`), nên câu lệnh có thể chạy thành công. Nhưng nó đặt `status = "Called customer"` và `note = "PAID"`: **đúng về số lượng và kiểu, sai về nghĩa và thứ tự**. Nếu status có constraint, DB có thể chặn; nếu không, dữ liệu bị ghi sai lặng lẽ.

Sửa:

```java
jdbc.update(
    "UPDATE orders SET status = ?, note = ? WHERE id = ?",
    "PAID",
    "Called customer",
    10L
);
```

Thực hành review: đọc SQL từ trái qua phải, đánh số `?` và viết bảng mapping `1 → status`, `2 → note`, `3 → id`. Đừng tự động dựa vào thứ tự trường trong record/DTO nếu thứ tự cột SQL khác. Khi thêm một cột vào `SET` hoặc một điều kiện vào `WHERE`, phải cập nhật **đồng bộ** SQL và toàn bộ danh sách giá trị.

### Truy vấn có nhiều dấu hỏi giống nhau về kiểu

```sql
SELECT id, status, total
FROM orders
WHERE customer_id = ? AND id > ? AND total >= ?
ORDER BY id;
```

Ba giá trị nên là `customerId (Long)`, `lastId (Long)` và `minimumTotal (BigDecimal)`. Hai tham số đầu đều là `BIGINT` nhưng việc đổi chỗ có thể cho tập kết quả sai mà không báo exception. Đây là lý do **kiểm thử giá trị đầu ra** quan trọng hơn chỉ kiểm thử câu SQL chạy không lỗi.

## 4. Kiểu Java và SQL: ưu tiên tương thích rõ ràng

JDBC cung cấp các phương thức setter có kiểu. Bảng dưới chỉ là các mapping thông dụng; conversion thực tế còn tùy driver, DBMS, precision/scale và schema.

| SQL đích | Java nên cân nhắc | JDBC binding rõ ràng | Lưu ý |
| --- | --- | --- | --- |
| `BIGINT` | `Long`/`long` | `setLong`, `Types.BIGINT` | Không truyền tùy tiện String ID; tránh tràn số |
| `INTEGER` | `Integer`/`int` | `setInt`, `Types.INTEGER` | Dải giá trị phải hợp lệ |
| `SMALLINT` | `Short`/`short` | `setShort`, `Types.SMALLINT` | Không tự giả định DB ép mọi int thành smallint |
| `BOOLEAN`/`BIT` | `Boolean`/`boolean` | `setBoolean`, `Types.BOOLEAN` | DBMS có thể biểu diễn boolean khác nhau |
| `VARCHAR` | `String` | `setString`, `Types.VARCHAR` | Kiểm tra `NOT NULL` và độ dài |
| `DECIMAL`/`NUMERIC` | `BigDecimal` | `setBigDecimal`, `Types.DECIMAL` | Giữ độ chính xác và scale phù hợp |
| `DATE` | `LocalDate` / `java.sql.Date` | `setDate` hoặc typed `setObject` | Driver JDBC 4.2 có thể hỗ trợ `LocalDate` |
| `TIMESTAMP` | `LocalDateTime` / `Timestamp` | `setTimestamp` hoặc typed `setObject` | Xét precision, timezone và dialect |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` (nếu driver hỗ trợ) | typed `setObject` | Không nhầm local time với instant |
| `BINARY`/`VARBINARY` | `byte[]` | `setBytes` | Không truyền base64 String nếu schema không yêu cầu |
| `NULL` thuộc cột cụ thể | Java `null` + SQL type | `setNull(index, Types.XXX)` | Null không có kiểu Java tự mô tả |

Các nguyên tắc:

- **Số tiền:** dùng `new BigDecimal("129.50")` hoặc cách tạo chính xác tương đương. Tránh `new BigDecimal(129.50)` vì `double` là số nhị phân có thể không biểu diễn chính xác giá trị thập phân.
- **Ngày/giờ:** không tùy tiện truyền `String` có định dạng locale, ví dụ `"31/12/2026"`, vào cột `DATE`. Truyền kiểu thời gian tương thích và kiểm tra cách driver xử lý múi giờ.
- **Enum:** nếu schema lưu một chuỗi status, chuyển enum sang giá trị lưu trữ được định nghĩa rõ, ví dụ `OrderStatus.PAID.name()` khi contract bảo đảm tên enum khớp mã trong DB. Không hy vọng driver tự biết ý nghĩa domain enum.
- **Long/Integer:** mặc dù một số DB chuyển đổi được, hãy dùng kiểu tương ứng với schema và hạn chế conversion dựa vào may rủi.
- **NULL:** SQL type là một phần hợp đồng. `null` không thể được truyền bằng primitive Java. Dùng wrapper hoặc khai báo SQL type rõ ràng khi cần.
- **Giới hạn dữ liệu:** tương thích Java type chưa đủ; `"a very long string"` vẫn có thể vượt `VARCHAR(10)`, và `BigDecimal("999999999999.99")` có thể vượt `DECIMAL(12,2)`.

## 5. Trường hợp NULL: giữ SQL type dù Java không có giá trị

Cột `note VARCHAR(100) NULL` cho phép thiếu ghi chú. JDBC thuần có thể bind:

```java
if (note == null) {
    ps.setNull(1, java.sql.Types.VARCHAR);
} else {
    ps.setString(1, note);
}
```

Mảnh code này thuộc một method có `PreparedStatement ps` và `String note`, trong đó tham số số 1 tương ứng cột `note`. `setNull` yêu cầu chỉ rõ SQL type để driver biết đây là `NULL` của kiểu nào.

**Không thay SQL NULL bằng chuỗi `"null"`, chuỗi rỗng `""` hoặc số 0** chỉ để ép code chạy. Những giá trị đó mang nghĩa khác với SQL NULL và có thể làm sai truy vấn/filter về sau.

Spring thường xác định SQL type từ giá trị Java, nhưng việc suy luận khó hơn khi giá trị là `null`, nhất là với cột/biểu thức hoặc JDBC driver đặc thù. Spring cho phép dùng `SqlParameterValue`:

```java
import java.sql.Types;
import org.springframework.jdbc.core.SqlParameterValue;

int updated = jdbc.update(
    "UPDATE orders SET note = ? WHERE id = ?",
    new SqlParameterValue(Types.VARCHAR, null),
    10L
);
```

Ở đây `jdbc` là biến `JdbcOperations`/`JdbcTemplate` trong một method. Có **hai marker**: marker thứ nhất mang SQL type `VARCHAR` và giá trị null, marker thứ hai là khóa `BIGINT`. `SqlParameterValue` có thể truyền giá trị khác null với SQL type tường minh tương tự.

Spring `JdbcTemplate` còn có overload cung cấp mảng SQL types:

```java
Object[] args = {null, 10L};
int[] argTypes = {Types.VARCHAR, Types.BIGINT};

int changed = jdbc.update(
    "UPDATE orders SET note = ? WHERE id = ?",
    args,
    argTypes
);
```

Trong đoạn này `jdbc` cần là **`JdbcOperations` hoặc `JdbcTemplate` có overload `update(String, Object[], int[])`** và `Types` là `java.sql.Types`. Cả `args` và `argTypes` phải có **hai phần tử**, theo đúng hai vị trí SQL. Không được khai báo chỉ một SQL type rồi kỳ vọng Spring đoán type còn lại trong overload đó. `changed` vẫn là số hàng cập nhật.

Cách dùng `SqlParameterValue` có lợi khi chỉ một số tham số cần type tường minh; mảng `argTypes` giúp nhìn thấy toàn bộ bảng kiểu theo vị trí.

### Null và kiểu của mệnh đề

Đoạn SQL:

```sql
SELECT id FROM orders WHERE note = ?;
```

Nếu bind `null` vào `?`, biểu thức `note = NULL` theo logic SQL thông thường **không khớp bất kỳ hàng nào**, kể cả các hàng có `note IS NULL`. Đây là vấn đề **ngữ nghĩa SQL**, không phải lỗi số lượng parameter. Muốn tìm các hàng note là NULL, dùng:

```sql
SELECT id FROM orders WHERE note IS NULL;
```

Nếu chính sách truy vấn cho phép một filter có thể vắng mặt, cần chọn rõ: không thêm điều kiện, dùng `IS NULL`, hoặc dùng biểu thức có ý nghĩa cụ thể. Không gắn một giá trị null rồi mong `= ?` tự biến thành `IS NULL`.

## 6. Ví dụ Java 17+ dùng JDBC thuần: kiểm tra ba placeholder

Class sau chỉ dùng API chuẩn trong JDK, có thể biên dịch bằng Java 17. Nó cần một `Connection` đang mở và bảng `inventory_events(id BIGINT, note VARCHAR, quantity INTEGER NULL)` trong DB để thực thi; **không phải ứng dụng có `main` độc lập**.

**`ExplicitBinder.java`:**

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;

public final class ExplicitBinder {
    private ExplicitBinder() {}

    public static int insertEvent(
            Connection connection,
            long id,
            String note,
            Integer quantity) throws SQLException {

        String sql = """
            INSERT INTO inventory_events (id, note, quantity)
            VALUES (?, ?, ?)
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.setString(2, note);

            if (quantity == null) {
                statement.setNull(3, Types.INTEGER);
            } else {
                statement.setInt(3, quantity);
            }

            return statement.executeUpdate();
        }
    }
}
```

Kiểm tra biên dịch phần Java thuần này:

```bash
javac --release 17 ExplicitBinder.java
```

Khi gọi, phương thức bind **đúng ba marker** theo thứ tự `id`, `note`, `quantity`. Nó giải phóng `PreparedStatement` nhưng **không đóng `Connection` do bên gọi sở hữu**. Bên gọi phải tự quản lý connection và transaction, hoặc dùng một tầng Spring để quản lý.

`setString(2, null)` được JDBC định nghĩa có thể gửi SQL NULL ở một số trường hợp, nhưng để kiểm soát chính xác SQL type và tương thích driver, đặc biệt với null không có kiểu, dùng `setNull(index, Types.VARCHAR)` khi cần. Đối với tham số `quantity`, ví dụ đã xử lý tường minh.

## 7. Spring JdbcTemplate: một ví dụ đầy đủ về số lượng và kiểu tham số

Để thấy kết quả chạy thực tế, dùng **Java 17+, Spring Boot 3.3+**, `spring-boot-starter-jdbc` và H2 in-memory. Tạo dự án Spring Boot Gradle với plugin, repository và dependency management phù hợp.

Trong `build.gradle`, thêm dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Đây là **khối dependencies** thuộc build script đã cấu hình, chưa phải file Gradle độc lập.

**`src/main/resources/application.yml`:**

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:sql_params_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
```

### 7.1. Định nghĩa dữ liệu Java

**`src/main/java/example/Product.java`:**

```java
package example;

import java.math.BigDecimal;

public record Product(
    long id,
    String sku,
    String name,
    BigDecimal price,
    int stock,
    boolean active,
    BigDecimal discount
) {}
```

`price`/`discount` dùng `BigDecimal` vì cột database là `DECIMAL(12,2)`. `discount` được phép null, còn những trường khác trong ví dụ có ràng buộc `NOT NULL`.

### 7.2. Repository dùng JdbcOperations

**`src/main/java/example/ProductRepository.java`:**

```java
package example;

import java.math.BigDecimal;
import java.sql.Types;
import java.util.List;
import java.util.Optional;

import org.springframework.dao.support.DataAccessUtils;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.stereotype.Repository;

@Repository
public final class ProductRepository {
    private static final RowMapper<Product> MAPPER =
        (rs, rowNum) -> new Product(
            rs.getLong("id"),
            rs.getString("sku"),
            rs.getString("name"),
            rs.getBigDecimal("price"),
            rs.getInt("stock"),
            rs.getBoolean("active"),
            rs.getBigDecimal("discount")
        );

    private final JdbcOperations jdbc;

    public ProductRepository(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    public int insert(Product product) {
        String sql = """
            INSERT INTO products
                (id, sku, name, price, stock, active, discount)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """;

        return jdbc.update(
            sql,
            product.id(),       // 1: BIGINT
            product.sku(),      // 2: VARCHAR
            product.name(),     // 3: VARCHAR
            product.price(),    // 4: DECIMAL
            product.stock(),    // 5: INTEGER
            product.active(),   // 6: BOOLEAN
            new SqlParameterValue(Types.DECIMAL, product.discount()) // 7
        );
    }

    public int renameAndStock(long id, String newName, int newStock) {
        return jdbc.update(
            "UPDATE products SET name = ?, stock = ? WHERE id = ?",
            newName,  // 1
            newStock, // 2
            id        // 3
        );
    }

    public Optional<Product> findById(long id) {
        List<Product> rows = jdbc.query(
            "SELECT id, sku, name, price, stock, active, discount " +
            "FROM products WHERE id = ?",
            MAPPER,
            id
        );
        return DataAccessUtils.optionalResult(rows);
    }

    public List<Product> findActiveAtLeast(BigDecimal minimumPrice) {
        return jdbc.query(
            "SELECT id, sku, name, price, stock, active, discount " +
            "FROM products WHERE active = ? AND price >= ? ORDER BY id",
            MAPPER,
            true,
            minimumPrice
        );
    }

    public long countSku(String sku) {
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM products WHERE sku = ?",
            Long.class,
            sku
        );
        return java.util.Objects.requireNonNull(count);
    }

    public int setDiscount(long id, BigDecimal discount) {
        return jdbc.update(
            "UPDATE products SET discount = ? WHERE id = ?",
            new SqlParameterValue(Types.DECIMAL, discount),
            id
        );
    }
}
```

Điểm cần đọc kỹ:

- `insert` có **7 dấu `?` và đúng 7 giá trị**, theo thứ tự cột. `SqlParameterValue` ở vị trí 7 giúp truyền SQL `DECIMAL NULL` khi `discount` không có giá trị.
- `renameAndStock` có **3 dấu `?`**; dù `id` là tham số đầu tiên trong method Java, nó là vị trí **3** trong SQL vì điều kiện `WHERE id = ?` nằm sau hai phép gán.
- `findById` có **1 dấu `?`**, truyền `long id` phù hợp với `BIGINT`. `DataAccessUtils.optionalResult` có từ Spring Framework 6.1 và biến 0 hàng thành `Optional.empty()`; nếu nhiều hơn một hàng thì lỗi về số lượng kết quả.
- `findActiveAtLeast` có **2 dấu `?`**: boolean `true` và `BigDecimal minimumPrice`, không thể đảo thứ tự. `ORDER BY id` bảo đảm thứ tự đầu ra.
- `countSku` có **1 dấu `?`**. `COUNT(*)` không `GROUP BY` trả một hàng với số đếm (có thể 0), khác với việc một truy vấn bình thường trả 0 hàng.
- `setDiscount` có **2 dấu `?`**, có thể truyền một `BigDecimal` hoặc `null` với SQL type tường minh. Không ghi giá trị `0` thay thế null nếu nghiệp vụ chưa cho phép.

### 7.3. Ứng dụng khởi tạo schema và in kết quả

**`src/main/java/example/SqlParameterDemoApplication.java`:**

```java
package example;

import java.math.BigDecimal;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;

@SpringBootApplication
public class SqlParameterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SqlParameterDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcOperations jdbc, ProductRepository products) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE products (
                    id BIGINT PRIMARY KEY,
                    sku VARCHAR(20) NOT NULL UNIQUE,
                    name VARCHAR(100) NOT NULL,
                    price DECIMAL(12,2) NOT NULL,
                    stock INTEGER NOT NULL,
                    active BOOLEAN NOT NULL,
                    discount DECIMAL(12,2) NULL
                )
                """);

            Product notebook = new Product(
                7L, "BK-7", "Notebook",
                new BigDecimal("49.90"),
                5, true, null
            );

            System.out.println("insert=" + products.insert(notebook));
            System.out.println("changed=" +
                products.renameAndStock(7L, "Notebook Pro", 8));
            System.out.println("active=" +
                products.findActiveAtLeast(new BigDecimal("40.00")));
            System.out.println("found=" + products.findById(7L));
            System.out.println("missing=" + products.findById(999L));
            System.out.println("countSku=" + products.countSku("BK-7"));
        };
    }
}
```

Chạy trong thư mục dự án:

```bash
./gradlew bootRun
```

Trên Windows có thể chạy `gradlew.bat bootRun`. Trong H2 in-memory mới và không có schema/seed script khác, các dòng do ứng dụng in (ngoài log Spring/Hikari) là:

```text
insert=1
changed=1
active=[Product[id=7, sku=BK-7, name=Notebook Pro, price=49.90, stock=8, active=true, discount=null]]
found=Optional[Product[id=7, sku=BK-7, name=Notebook Pro, price=49.90, stock=8, active=true, discount=null]]
missing=Optional.empty
countSku=1
```

Giải thích:

1. `insert` bind 7 giá trị theo đúng 7 cột nên chèn một hàng; số hàng tác động là 1.
2. `renameAndStock` bind name mới, stock mới, rồi ID; thay đổi đúng sản phẩm `id=7`.
3. `findActiveAtLeast` bind `true` cho `active` và `40.00` cho ngưỡng `price`, lấy đúng sản phẩm đã chèn.
4. `findById(7)` trả record với `discount=null`; kiểu `BigDecimal` có thể giữ Java null. `findById(999)` trả `Optional.empty()` vì không có ID đó.
5. `COUNT(*)` theo SKU trả 1; `COUNT(*)` bằng 0 nếu SKU không tồn tại cũng là kết quả hợp lệ.

**Giới hạn biên dịch:** Các file Java này chạy khi nằm trong **dự án Spring Boot đã có build script và dependency tương ứng**, không thể chỉ `javac` với classpath JDK thuần vì có import Spring. Ví dụ sử dụng Java 17+, `@SpringBootApplication`, cấu hình H2 và `JdbcTemplate` được auto-configure trong điều kiện phù hợp. Nếu chuyển sang PostgreSQL/MySQL, cần JDBC driver, schema và dữ liệu phù hợp; không kết luận từ H2 rằng mọi conversion đều giống nhau.

## 8. NamedParameterJdbcTemplate: khớp theo tên, vẫn phải đúng kiểu

Khi một câu SQL có nhiều placeholder và dễ đảo vị trí, `NamedParameterJdbcTemplate` cho phép viết:

```sql
UPDATE orders
SET status = :status, total = :total
WHERE id = :id;
```

Dùng các tên `:status`, `:total`, `:id` rồi cung cấp map theo tên:

```java
import java.math.BigDecimal;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

int changed = namedJdbc.update(
    "UPDATE orders SET status = :status, total = :total WHERE id = :id",
    Map.of(
        "status", "PAID",
        "total", new BigDecimal("129.50"),
        "id", 10L
    )
);
```

`namedJdbc` là một instance `NamedParameterJdbcTemplate` đã được inject/cấu hình. Đoạn này là code trong method, không phải chương trình độc lập.

Một map không có thứ tự duyệt cố định **không phải vấn đề**: Spring ghép dữ liệu theo **tên tham số**, rồi chuyển thành JDBC positional placeholders để thực thi. Tên tham số **phải khớp**; nếu SQL có `:id` nhưng map chỉ có `"orderId"`, Spring có thể báo thiếu giá trị cho tên `id`.

Các lưu ý:

- Named parameters làm code dễ đọc, nhưng **không bỏ nhu cầu khớp kiểu**: `:total` vẫn cần giá trị tương thích `DECIMAL`, `:id` vẫn tương thích `BIGINT`.
- Một tên `:id` xuất hiện nhiều lần trong SQL có thể sử dụng cùng một giá trị từ map, nhưng dưới lớp Spring nó được áp vào từng marker cần thiết.
- `Map.of(...)` **không cho phép giá trị null**. Với một tham số nullable, hãy dùng `MapSqlParameterSource` hoặc map mutable cho phép null, và nên khai báo SQL type khi cần.
- Named parameters cũng chỉ đại diện cho **giá trị**; không dùng `:columnName` làm tên cột/identifier động.

### MapSqlParameterSource giúp vừa khớp tên vừa chỉ rõ SQL type

```java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("note", null, Types.VARCHAR)
    .addValue("id", 10L, Types.BIGINT);

int changed = namedJdbc.update(
    "UPDATE orders SET note = :note WHERE id = :id",
    params
);
```

Đây là đoạn trong một method có biến `namedJdbc` đã cấu hình. SQL có đúng hai tên cần bind và `MapSqlParameterSource` cung cấp đủ hai tên, giá trị lẫn SQL type; null của `note` không bị ép sang chuỗi `"null"`.

Khi chỉ đọc một phần đầu vào, không nhất thiết map phải chỉ có đúng các key xuất hiện trong câu SQL; nhưng **tất cả các tên SQL yêu cầu phải được cung cấp** và business nên tránh truyền các tham số thừa vì chúng khiến code khó review.

## 9. Danh sách IN (...): một collection không tự bằng nhiều marker

Giả sử muốn truy vấn ba ID `7`, `8`, `9`. SQL có ba placeholder positional:

```sql
SELECT id, name FROM products WHERE id IN (?, ?, ?);
```

Các tham số cần là **ba giá trị tách biệt**:

```java
List<Long> ids = List.of(7L, 8L, 9L);
List<Product> found = jdbc.query(
    "SELECT id, sku, name, price, stock, active, discount " +
    "FROM products WHERE id IN (?, ?, ?) ORDER BY id",
    MAPPER,
    ids.get(0), ids.get(1), ids.get(2)
);
```

`jdbc` và `MAPPER` là các thành phần trong `ProductRepository` hoặc method có mapper tương ứng. **Không** thay các đối số bằng một `List<Long>` truyền vào `IN (?)` và giả định `JdbcTemplate` mở rộng nó thành ba dấu `?`. Với `JdbcTemplate` thuần, một marker nhận một giá trị; collection có thể bị driver xem là object/array không tương thích với `BIGINT`.

Nếu `ids` có độ dài động, hai cách đúng phổ biến:

1. Sinh đúng `N` dấu `?` và đúng `N` giá trị khi dùng positional JDBC; nên đặt một method chuyên xử lý việc tạo placeholders và giữ danh sách args đồng bộ.
2. Dùng `NamedParameterJdbcTemplate` với `IN (:ids)`. Spring hỗ trợ mở rộng một `List` thành số placeholder tương ứng, với các lưu ý giới hạn của DBMS/driver.

Ví dụ cách thứ hai:

```java
import java.util.List;
import java.util.Map;

List<Long> ids = List.of(7L, 8L, 9L);
List<Product> found = namedJdbc.query(
    "SELECT id, sku, name, price, stock, active, discount " +
    "FROM products WHERE id IN (:ids) ORDER BY id",
    Map.of("ids", ids),
    MAPPER
);
```

Đây là đoạn code dùng `NamedParameterJdbcTemplate namedJdbc` và `RowMapper<Product> MAPPER` đã có. Spring có thể biến `:ids` thành `?, ?, ?` rồi bind đúng ba giá trị.

**Trường hợp danh sách rỗng:** SQL `IN ()` không portable và có thể sai cú pháp. Ứng dụng nên định nghĩa chính sách trước khi thực thi, ví dụ nếu danh sách ID trống thì trả `List.of()` không query. Với danh sách rất dài, giới hạn số bind parameters của DBMS/driver và hiệu năng câu SQL có thể trở thành vấn đề; cân nhắc chunk hoặc kỹ thuật đặc thù DB.

### Kích thước danh sách thay đổi thì số dấu hỏi cũng phải thay đổi

Việc ghép SQL động sai thường xảy ra khi code tạo chuỗi `"IN (?, ?)"` cố định nhưng truyền tập ID có ba phần tử. Cần bảo đảm SQL được sinh từ **cùng nguồn dữ liệu** dùng để sinh danh sách args. Đừng cắt bớt phần tử để tránh lỗi mà không có quy tắc nghiệp vụ.

## 10. WHERE động: xây SQL và args trong cùng một nhánh điều kiện

Nhu cầu thực tế: tìm sản phẩm theo `active` (có thể null nghĩa là không lọc) và giá tối thiểu (cũng có thể không lọc).

Một mẫu Spring JDBC rõ ràng:

```java
public List<Product> search(Boolean active, BigDecimal minimumPrice) {
    StringBuilder sql = new StringBuilder(
        "SELECT id, sku, name, price, stock, active, discount " +
        "FROM products WHERE 1=1"
    );
    List<Object> args = new java.util.ArrayList<>();

    if (active != null) {
        sql.append(" AND active = ?");
        args.add(active);
    }
    if (minimumPrice != null) {
        sql.append(" AND price >= ?");
        args.add(minimumPrice);
    }

    sql.append(" ORDER BY id");
    return jdbc.query(sql.toString(), MAPPER, args.toArray());
}
```

Đây là **method đặt trong `ProductRepository`** ở mục 7, nơi đã import `List`, `BigDecimal` và có `jdbc`/`MAPPER`. Vì mỗi nhánh thêm SQL và giá trị cùng lúc, số marker và số phần tử của args luôn đi đôi trong logic này.

Bốn trường hợp:

| `active` | `minimumPrice` | Marker | Danh sách args |
| --- | --- | ---: | --- |
| null | null | 0 | rỗng |
| true | null | 1 | `[true]` |
| null | 40.00 | 1 | `[BigDecimal("40.00")]` |
| false | 40.00 | 2 | `[false, BigDecimal("40.00")]` |

Nếu một nhánh chỉ thêm `AND price >= ?` mà không thêm giá trị vào args, lệnh bị thiếu bind. Nếu chỉ thêm args mà không thêm `?`, lệnh thừa bind. **Khi refactor điều kiện SQL động, luôn sửa cả hai phía trong cùng nhánh code và có test cho mọi tổ hợp filter.**

Cần tránh nối trực tiếp giá trị dữ liệu người dùng vào `StringBuilder`. Mẫu trên chỉ nối **đoạn SQL cố định do lập trình viên kiểm soát**, còn giá trị vẫn đi qua placeholder, giúp tránh SQL injection.

### LIKE và các ký tự đặc biệt

```java
List<Product> found = jdbc.query(
    "SELECT id, sku, name, price, stock, active, discount " +
    "FROM products WHERE name LIKE ? ORDER BY id",
    MAPPER,
    "Note%"
);
```

Chỉ có **một marker** và một giá trị Java `"Note%"`. Nếu cần match prefix từ input, mã có thể tạo pattern từ `prefix + "%"` rồi bind. Nhưng `%` và `_` trong giá trị người dùng có nghĩa wildcard của `LIKE`; nếu muốn tìm literal, cần escaping theo quy tắc SQL/dialect và có `ESCAPE` phù hợp. Bind parameter ngăn việc input đổi cấu trúc SQL, nhưng **không tự escape wildcard của LIKE**.

## 11. Batch update: cùng câu SQL, mỗi dòng phải có đủ tham số

Batch giúp gửi nhiều bộ tham số cho cùng một câu SQL. Điều kiện cơ bản là **mỗi bộ giá trị đều khớp cùng số marker và kiểu đích**.

Ví dụ trong một method đã có `JdbcOperations jdbc`:

```java
String sql = "UPDATE products SET stock = ? WHERE id = ?";

int[] counts = jdbc.batchUpdate(
    sql,
    List.of(
        new Object[] {4, 7L},
        new Object[] {9, 8L},
        new Object[] {0, 9L}
    )
);
```

Mỗi phần tử là mảng **hai giá trị**: stock `INTEGER` trước, id `BIGINT` sau. Nếu một phần tử chỉ có một giá trị, tương tác với driver có thể lỗi vì thiếu bind. Kết quả `int[] counts` chứa số hàng bị tác động (hoặc giá trị sentinel JDBC như `Statement.SUCCESS_NO_INFO`) cho từng phần batch theo quy tắc driver.

Nếu cần SQL types đặc biệt hoặc muốn bind chặt chẽ theo index, `JdbcTemplate.batchUpdate(String, BatchPreparedStatementSetter)` cho phép gọi các setter ở từng vị trí. Đây là ví dụ với một `JdbcTemplate jdbcTemplate` đã inject:

```java
List<Long> ids = List.of(7L, 8L);

int[] counts = jdbcTemplate.batchUpdate(
    "UPDATE products SET active = ? WHERE id = ?",
    new org.springframework.jdbc.core.BatchPreparedStatementSetter() {
        @Override
        public void setValues(java.sql.PreparedStatement ps, int i)
                throws java.sql.SQLException {
            ps.setBoolean(1, true);
            ps.setLong(2, ids.get(i));
        }

        @Override
        public int getBatchSize() {
            return ids.size();
        }
    }
);
```

Đây là đoạn trong method có biến `jdbcTemplate` kiểu **`JdbcTemplate`** (không chỉ interface `JdbcOperations` nếu dùng overload cụ thể), và `List` đã import. Chỉ số **`i` của danh sách Java bắt đầu từ 0**, còn chỉ số **tham số JDBC trong `PreparedStatement` bắt đầu từ 1**.

**Batch không tự bảo đảm một transaction nguyên tử.** Nếu cần tất cả update cùng commit/rollback, cần cấu hình Spring transaction manager và ranh giới `@Transactional` phù hợp; driver và cấu hình auto-commit quyết định hành vi khi không có transaction chủ động.

## 12. Các tình huống sai phổ biến và cách phân biệt lỗi

| Tình huống | Dấu hiệu có thể thấy | Cách sửa |
| --- | --- | --- |
| Câu SQL có 3 `?` nhưng truyền 2 giá trị | Driver báo tham số chưa bind khi execute | So số lượng và đánh dấu vị trí 1..N |
| Câu SQL có 2 `?` nhưng truyền 3 giá trị | Driver báo index/parameter vượt giới hạn | Xóa giá trị dư hoặc sửa SQL có chủ đích |
| `status` và `note` đảo giá trị, cùng `VARCHAR` | Có thể không có exception, dữ liệu bị ghi nhầm | Review mapping theo thứ tự SQL, test dữ liệu sau ghi |
| Truyền `String` không hợp lệ vào `DECIMAL` | Lỗi conversion hoặc constraint tùy DB | Dùng `BigDecimal` và validation |
| Truyền `null` mà driver không xác định được SQL type | SQL type inference/driver exception | `SqlParameterValue` hoặc `setNull(index, Types.XXX)` |
| Gán `id = ?` nhưng Java truyền ID vào vị trí khác | Query 0 hàng hoặc update sai record | Kiểm tra cả SQL và args, log có kiểm soát |
| `IN (?)` nhận một `List` | Lỗi conversion hoặc query không như ý | Mở rộng placeholders hoặc dùng named list |
| `LIKE ?` nhận chuỗi có `%`/`_` ngoài ý muốn | Kết quả rộng hơn mong muốn | Escape wildcard khi cần tìm literal |
| Dùng `?` cho tên bảng/cột | SQL không hoạt động như identifier động | Whitelist tên cột/tùy chọn được phép |
| `queryForObject` đúng tham số nhưng 0 hàng | `EmptyResultDataAccessException` | Xử lý hợp đồng "không tìm thấy" riêng |
| `update` đúng tham số nhưng 0 hàng tác động | `update` trả 0 | Kiểm tra khóa/WHERE và quy tắc nghiệp vụ |
| Java value đúng kiểu nhưng vượt `VARCHAR`/`DECIMAL` | Lỗi constraint/truncation hoặc behavior driver | Kiểm tra length, precision, scale, DB constraint |

**Phân biệt ba nhóm:** *lỗi bind*, *lỗi dữ liệu* và *kết quả nghiệp vụ hợp lệ*. Truy vấn trả danh sách rỗng không tự chứng minh bind thiếu tham số; có thể tất cả tham số đúng nhưng filter không khớp dữ liệu. Ngược lại, câu update trả 1 không tự chứng minh ghi đúng nghĩa nếu hai cột cùng kiểu bị đảo giá trị.

### Không đoán loại exception quá cụ thể

JDBC driver thường ném `SQLException` kèm SQLState và vendor error code. `JdbcTemplate` dịch nhiều lỗi sang `DataAccessException`. Tùy database và nguồn lỗi, có thể nhận `BadSqlGrammarException`, `DataIntegrityViolationException` hoặc subclass/`UncategorizedSQLException` khác. **Không mã hóa logic kinh doanh dựa trên một message lỗi hoặc subclass suy đoán cho "thiếu tham số"**. Cách chẩn đoán tốt hơn là so câu SQL, số bind, thứ tự giá trị, SQL types và underlying exception.

Tránh log trực tiếp mật khẩu, token, số thẻ hoặc thông tin nhạy cảm trong tham số. Với debug, ghi nhận operation, số parameter, tên trường (nếu dùng named params), kiểu dự kiến, và mã SQLState khi phù hợp; chỉ log giá trị khi chính sách bảo mật cho phép.

## 13. Test hợp đồng tham số bằng JDBC integration test

Test với mock có thể phát hiện một method gọi `update` sai số argument nếu dùng verify/captor, nhưng **chỉ integration test trên DB** mới chứng minh SQL, driver và schema chấp nhận conversion thực tế. H2 hữu ích cho thử nhanh; nếu production là PostgreSQL/MySQL, thêm test với driver và DB tương ứng (ví dụ Testcontainers).

Với dự án Spring Boot ở mục 7, thêm dependency test trong `build.gradle` đã có:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Test dùng `@JdbcTest` và `@Import(ProductRepository.class)` để có repository và Spring JDBC trong slice test.

**`src/test/java/example/ProductRepositoryTest.java`:**

```java
package example;

import java.math.BigDecimal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcOperations;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@Import(ProductRepository.class)
class ProductRepositoryTest {
    @Autowired
    JdbcOperations jdbc;

    @Autowired
    ProductRepository repo;

    @BeforeEach
    void setup() {
        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id BIGINT PRIMARY KEY,
                sku VARCHAR(20) NOT NULL UNIQUE,
                name VARCHAR(100) NOT NULL,
                price DECIMAL(12,2) NOT NULL,
                stock INTEGER NOT NULL,
                active BOOLEAN NOT NULL,
                discount DECIMAL(12,2) NULL
            )
            """);
        jdbc.update("DELETE FROM products");
    }

    @Test
    void positionalArgumentsKeepValuesInCorrectColumns() {
        Product original = new Product(
            7L, "BK-7", "Notebook", new BigDecimal("49.90"),
            5, true, null
        );

        assertEquals(1, repo.insert(original));
        assertEquals(1, repo.renameAndStock(7L, "Notebook Pro", 8));

        Product after = repo.findById(7L).orElseThrow();
        assertEquals("BK-7", after.sku());
        assertEquals("Notebook Pro", after.name());
        assertEquals(new BigDecimal("49.90"), after.price());
        assertEquals(8, after.stock());
        assertTrue(after.active());
        assertNull(after.discount());
    }

    @Test
    void nullableDecimalUsesAnExplicitSqlType() {
        Product original = new Product(
            8L, "BK-8", "Draft", new BigDecimal("30.00"),
            1, false, null
        );
        assertEquals(1, repo.insert(original));
        assertEquals(1,
            repo.setDiscount(8L, new BigDecimal("5.00")));
        assertEquals(new BigDecimal("5.00"),
            repo.findById(8L).orElseThrow().discount());
        assertEquals(1, repo.setDiscount(8L, null));
        assertNull(repo.findById(8L).orElseThrow().discount());
    }

    @Test
    void multipleQueryParametersKeepExpectedOrder() {
        repo.insert(new Product(
            9L, "BK-9", "Blue Pen", new BigDecimal("10.00"),
            3, true, null
        ));
        repo.insert(new Product(
            10L, "BK-10", "Notebook", new BigDecimal("50.00"),
            3, true, null
        ));
        repo.insert(new Product(
            11L, "BK-11", "Notebook Black", new BigDecimal("60.00"),
            3, false, null
        ));

        var found = repo.findActiveAtLeast(new BigDecimal("40.00"));
        assertEquals(1, found.size());
        assertEquals(10L, found.get(0).id());
    }
}
```

Chạy:

```bash
./gradlew test
```

Trên Windows dùng `gradlew.bat test`. Với Spring Boot 3.3+, JUnit 5 và H2 đã cấu hình, kỳ vọng **3 test pass** trong điều kiện không có schema/test configuration khác xung đột. `@JdbcTest` thông thường dùng embedded database và transaction rollback cho mỗi test; `@Import` cung cấp bean repository để Spring inject.

Test kiểm tra **giá trị trong các cột sau khi thực thi**, chứ không chỉ khẳng định code không ném exception. Test thứ ba đặc biệt có dữ liệu đủ khác nhau để phát hiện việc đảo thứ tự `active` và `minimumPrice` nếu SQL có thể được chuyển kiểu. Để kiểm tra lỗi thiếu/thừa marker, có thể viết thêm negative test trên đúng JDBC driver production và khẳng định có exception, nhưng không khóa cứng subclass nếu driver không bảo đảm.

### Checklist trước khi merge một thay đổi SQL

1. Đánh số tất cả parameter markers theo thứ tự xuất hiện, hoặc liệt kê tất cả tên `:param`.
2. Kiểm tra số giá trị bằng số marker/tên được yêu cầu và không bỏ sót.
3. Kiểm tra giá trị thứ `i` thuộc đúng biểu thức/cột `i` trong SQL.
4. Kiểm tra SQL type, nullable, precision, scale, độ dài và ràng buộc.
5. Với SQL động, xét mọi tổ hợp điều kiện được bật/tắt; SQL và args được xây trong cùng logic.
6. Với `IN`, xác minh danh sách rỗng và danh sách dài, số placeholders thực tế, giới hạn DBMS.
7. Với SQL chứa identifier động, chỉ lấy tên từ whitelist, không đưa trực tiếp input vào câu SQL.
8. Với batch, mọi phần tử phải theo cùng hợp đồng marker/type.
9. Có integration test kiểm tra **giá trị thực sau ghi/truy vấn**, kể cả tham số cùng kiểu nhưng dễ đảo.
10. Kiểm tra lỗi ở mức phù hợp, không nhầm "0 hàng"/"0 rows updated" với lỗi bind.
11. Không dùng log chứa dữ liệu nhạy cảm để chữa lỗi tham số.
12. Xem SQL/driver khi đổi môi trường; một câu chạy được trên H2 chưa chắc chạy trên DBMS khác.

## 14. Các câu hỏi tự kiểm tra

**Câu 1.** SQL `UPDATE orders SET status = ?, total = ? WHERE id = ?` cần bao nhiêu giá trị Java, theo thứ tự nào?

**Đáp án:** Ba giá trị: status (String/VARCHAR), total (BigDecimal/DECIMAL), id (Long/BIGINT). ID là vị trí 3 dù có thể là tham số đầu tiên trong chữ ký method nghiệp vụ.

**Câu 2.** Một câu SQL có ba `?` nhưng Java cung cấp đúng hai giá trị. `JdbcTemplate` có tự hiểu tham số còn thiếu là SQL NULL không?

**Đáp án:** Không. Phải bind đủ các vị trí. Thiếu giá trị thường khiến driver báo lỗi trước hoặc khi execute; muốn SQL NULL thì vẫn phải bind **một tham số** có giá trị null và SQL type thích hợp.

**Câu 3.** Nếu truyền `"129.50"` (String) thay vì `BigDecimal("129.50")` cho cột `DECIMAL`, có chắc luôn lỗi không?

**Đáp án:** Không. Một số DBMS/driver có thể ép kiểu ngầm và thành công, một số khác báo lỗi. Dựa vào ép kiểu ngầm là thiếu portable; chọn `BigDecimal` để rõ ràng và chính xác.

**Câu 4.** Tại sao đảo hai giá trị `status` và `note` đều là String lại nguy hiểm?

**Đáp án:** Câu lệnh có thể chạy thành công vì số lượng/SQL type đều hợp lệ, nhưng dữ liệu được ghi vào sai cột. Cần test giá trị thực, không chỉ test không exception.

**Câu 5.** Trong `IN (?)`, truyền `List.of(1L, 2L, 3L)` qua một tham số của `JdbcTemplate` có đương nhiên biến thành ba marker không?

**Đáp án:** Không. Với positional `JdbcTemplate`, cần ba marker/giá trị tách biệt; `NamedParameterJdbcTemplate` có cơ chế mở rộng danh sách cho `IN (:ids)`.

**Câu 6.** Khi filter `active` không được cung cấp, một truy vấn SQL động có thể bỏ điều kiện đó thế nào?

**Đáp án:** Không thêm `AND active = ?` và không thêm giá trị `active` vào args. Nếu có điều kiện, phải thêm **cả SQL fragment và giá trị** ở cùng nhánh.

**Câu 7.** Java `null` truyền cho cột `DECIMAL` có thể cần gì ngoài việc cung cấp một giá trị null?

**Đáp án:** SQL type tường minh, ví dụ `new SqlParameterValue(Types.DECIMAL, null)` hoặc `ps.setNull(index, Types.DECIMAL)`. Điều này giúp driver biết kiểu đích khi không thể tự suy luận từ giá trị Java.

**Câu 8.** Tại sao `jdbc.update(...)` trả 0 không tự chứng minh thiếu tham số?

**Đáp án:** Vì 0 là số hàng bị tác động. SQL có thể bind hoàn toàn đúng nhưng điều kiện `WHERE` không khớp hàng nào; lỗi bind sẽ có dấu hiệu riêng tại tầng driver/SQL.

**Câu 9.** Trong `BatchPreparedStatementSetter.setValues(PreparedStatement ps, int i)`, `i=0` và `ps.setLong(1, value)` có mâu thuẫn không?

**Đáp án:** Không. `i` là index danh sách Java bắt đầu từ 0; parameter index của JDBC bắt đầu từ 1.

**Câu 10.** Với named params, `Map.of("note", null)` có phải cách đúng để truyền SQL NULL không?

**Đáp án:** Không. `Map.of` không cho phép null. Dùng `MapSqlParameterSource` với `addValue("note", null, Types.VARCHAR)`, hoặc nguồn tham số khác hỗ trợ null và SQL type thích hợp.

## Tài liệu tham khảo

- [Java SE 21 — PreparedStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html): chỉ số parameter bắt đầu từ 1, các setter có kiểu, `setNull` và `getParameterMetaData`.
- [Java SE 21 — Types](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Types.html): mã kiểu SQL như `BIGINT`, `VARCHAR`, `DECIMAL`, `BOOLEAN` và `NULL`.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, positional/named params, query/update và xử lý callback.
- [Spring Framework — Parameter Handling](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): chỉ định SQL type bằng mảng `argTypes`, `SqlParameterValue` và `SqlParameterSource`, đặc biệt khi giá trị là null.
- [Spring Framework — JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): các overload `update`, `query`, `batchUpdate`.
- [Spring Framework — NamedParameterJdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html): cách thay named params bằng positional markers và mở rộng `List`.

**Ghi nhớ:** Mỗi placeholder phải có **đúng một giá trị ở đúng vị trí hoặc đúng tên, với kiểu SQL tương thích**. Khi code thay đổi điều kiện SQL, hãy thay đổi danh sách args cùng lúc. Khi gặp `NULL`, chỉ rõ SQL type khi cần. Với SQL động hoặc nhiều giá trị cùng kiểu, tích hợp test kiểm tra dữ liệu thực thay vì chỉ kiểm tra câu lệnh chạy không lỗi.
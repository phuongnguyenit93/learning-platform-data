# PreparedStatementCreator và PreparedStatementSetter trong JdbcTemplate

> **Chủ đề:** JdbcTemplate của Spring Framework. Bài này giải thích hai callback cốt lõi dùng với JDBC `PreparedStatement`: **`PreparedStatementCreator` tạo statement từ một `Connection` do Spring cung cấp**, còn **`PreparedStatementSetter` gắn giá trị tham số vào statement đã được tạo**. Cả hai giúp lập trình viên kiểm soát những chi tiết JDBC cần thiết mà vẫn để `JdbcTemplate` phụ trách việc thực thi, dịch ngoại lệ và giải phóng tài nguyên.

## 1. Bài toán: tại sao `JdbcTemplate` có hai callback?

Giả sử tầng dữ liệu cần lưu một sản phẩm gồm `sku`, `price` và `stock`, rồi đọc danh sách sản phẩm có tồn kho tối thiểu. SQL dùng dấu `?` để nhận các tham số:

~~~sql
INSERT INTO product (sku, price, stock) VALUES (?, ?, ?);

UPDATE product SET stock = ? WHERE id = ?;

SELECT id, sku, price, stock
FROM product
WHERE stock >= ?
ORDER BY id;
~~~

Có **hai trách nhiệm kỹ thuật** thường nằm cùng đoạn JDBC thuần:

1. **Tạo statement:** Dùng `Connection.prepareStatement(sql)`, hoặc biến thể có `Statement.RETURN_GENERATED_KEYS`, `ResultSet.TYPE_FORWARD_ONLY` hay các lựa chọn đặc biệt.
2. **Thiết lập statement:** Gọi `ps.setString(1, sku)`, `ps.setBigDecimal(2, price)`, `ps.setInt(3, stock)` và các phương thức setter phù hợp.

`PreparedStatementCreator` đại diện cho trách nhiệm thứ nhất, có thể kèm bind tham số nếu tự viết callback. `PreparedStatementSetter` tập trung vào trách nhiệm thứ hai, dùng khi cấu hình tạo statement mặc định của `JdbcTemplate` đã đủ. Phần lớn truy vấn CRUD thông thường còn có thể dùng overload ngắn `update(sql, args...)` hoặc `query(sql, rowMapper, args...)`; không nhất thiết viết callback mỗi lần.

**Điểm cốt lõi:** Callback là cách gửi hành vi vào `JdbcTemplate`, không phải tài nguyên JDBC người gọi tự mở rồi tự đóng.

## 2. Vai trò trong đường đi từ ứng dụng đến database

~~~mermaid
flowchart TD
    S["Service / Repository"] --> J["JdbcTemplate"]
    J --> C["DataSourceUtils: lấy Connection theo transaction"]
    C --> CN["JDBC Connection"]
    J --> P{"Cách tạo PreparedStatement?"}
    P -- "SQL thông thường" --> A["JdbcTemplate gọi Connection.prepareStatement(sql)"]
    P -- "Cần tùy chỉnh" --> B["PreparedStatementCreator.createPreparedStatement(conn)"]
    A --> PS["PreparedStatement"]
    B --> PS
    PS --> V["PreparedStatementSetter.setValues(ps) hoặc creator tự bind"]
    V --> E["executeQuery / executeUpdate"]
    E --> DB[("Database")]
    DB --> RM["RowMapper / ResultSetExtractor hoặc số dòng ghi"]
    RM --> J
    J --> R["Đóng Statement/ResultSet, release Connection đúng cách"]
    R --> S
~~~

Sơ đồ mô tả trách nhiệm. Đối với `update(PreparedStatementCreator)`, creator tự tạo và có thể tự bind tham số; không phải overload nào cũng chạy thêm một setter riêng. `JdbcTemplate` lấy kết nối qua hạ tầng Spring, quản lý JDBC statement/result set, dịch `SQLException` thành ngoại lệ `DataAccessException` và release kết nối theo transaction. Trong một giao dịch Spring đang hoạt động, release không đồng nghĩa đóng vật lý kết nối trước khi transaction kết thúc.

### So sánh với JDBC thuần

Với JDBC thuần, đoạn mã thường tự làm toàn bộ:

~~~java
// Fragment minh họa: dataSource và các biến đã được tạo trước đó.
try (Connection con = dataSource.getConnection();
     PreparedStatement ps = con.prepareStatement(
         "UPDATE product SET stock = ? WHERE id = ?")) {

    ps.setInt(1, newStock);
    ps.setLong(2, productId);
    int changed = ps.executeUpdate();
}
~~~

Với JdbcTemplate, có thể viết:

~~~java
// Fragment tương đương dùng Spring JdbcTemplate.
int changed = jdbcTemplate.update(
    "UPDATE product SET stock = ? WHERE id = ?",
    ps -> {
        ps.setInt(1, newStock);
        ps.setLong(2, productId);
    }
);
~~~

Trong ví dụ thứ hai, lambda mang kiểu `PreparedStatementSetter`, vì API nhận **SQL** và một callback nhận **`PreparedStatement`**. Không gọi `con.close()` hoặc `ps.close()` bên trong callback; `JdbcTemplate` phụ trách vòng đời đó. Nếu chỉ gắn hai giá trị đơn giản, `jdbcTemplate.update(sql, newStock, productId)` còn ngắn hơn.

## 3. Hợp đồng chính xác của hai functional interface

Hai interface thuộc package `org.springframework.jdbc.core` và đều tương thích với lambda trong Java 8+.

### 3.1. `PreparedStatementCreator`

Hình dạng cốt lõi:

~~~java
@FunctionalInterface
public interface PreparedStatementCreator {
    PreparedStatement createPreparedStatement(Connection connection)
        throws SQLException;
}
~~~

`Connection` do JdbcTemplate đưa vào đã gắn với DataSource và ngữ cảnh transaction thích hợp. Callback cần **trả một `PreparedStatement` sử dụng Connection được cung cấp**. Nó quyết định SQL và các lựa chọn tạo statement. Ví dụ:

~~~java
PreparedStatementCreator creator = connection -> {
    PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO product (sku, price, stock) VALUES (?, ?, ?)",
        Statement.RETURN_GENERATED_KEYS
    );
    ps.setString(1, sku);
    ps.setBigDecimal(2, price);
    ps.setInt(3, stock);
    return ps;
};
~~~

Creator **có thể bind tham số trong lúc tạo statement**, như trên, vì lời gọi `JdbcTemplate.update(creator, keyHolder)` không có tham số setter riêng. Nếu creator có thể cung cấp SQL qua interface `SqlProvider`, Spring có thể có thông tin SQL hữu ích hơn trong một số lỗi; đây là tùy chọn, không bắt buộc với lambda.

### 3.2. `PreparedStatementSetter`

Hình dạng cốt lõi:

~~~java
@FunctionalInterface
public interface PreparedStatementSetter {
    void setValues(PreparedStatement ps) throws SQLException;
}
~~~

Ở đây SQL **đã được truyền cho JdbcTemplate** để framework tạo statement. Setter chỉ cấu hình các tham số và, khi phù hợp, tùy chỉnh một số thuộc tính statement trước khi chạy:

~~~java
String sql = "UPDATE product SET stock = ? WHERE id = ?";
PreparedStatementSetter setter = ps -> {
    ps.setInt(1, newStock);
    ps.setLong(2, productId);
};
int affected = jdbcTemplate.update(sql, setter);
~~~

`setValues` không có quyền chọn SQL khác hoặc thay thế object statement. Nó cũng **không tự gọi `executeUpdate()`** khi sử dụng với `update(sql, setter)`: JdbcTemplate sẽ thực thi sau khi setter hoàn tất.

### 3.3. Điểm khác không thể bỏ qua

| Tiêu chí | `PreparedStatementCreator` | `PreparedStatementSetter` |
| --- | --- | --- |
| Tham số callback nhận | `Connection` | `PreparedStatement` |
| Giá trị trả về | `PreparedStatement` | `void` |
| Ai quyết định cách gọi `prepareStatement(...)`? | Chính creator | JdbcTemplate, từ SQL được truyền sẵn |
| Có thể đặt giá trị `?`? | Có, nếu tự bind trong creator hoặc phối hợp API thích hợp | Có, đây là mục tiêu chính |
| Tùy biến generated keys/result set mode khi tạo? | Phù hợp | Không chọn được overload `prepareStatement` đã xảy ra |
| Có thể dùng với truy vấn `SELECT`? | Có | Có |
| Có tự quản lý Connection/close? | Không | Không |
| Độ phức tạp thường gặp | Cao hơn, dành cho create options đặc biệt | Thấp hơn, dành cho parameter binding |

Tên “Creator” chỉ khâu **tạo đối tượng PreparedStatement**; nó **không có nghĩa** “tạo mới bản ghi trong DB”. Một `SELECT` cũng có thể dùng `PreparedStatementCreator`. Tương tự “Setter” là setter giá trị JDBC, không liên quan getter/setter của entity Java.

## 4. Thứ tự chạy và chủ sở hữu tài nguyên

Với một lời gọi `jdbcTemplate.update(sql, setter)` thông thường:

1. JdbcTemplate lấy `Connection` từ DataSource qua cơ chế Spring phù hợp.
2. JdbcTemplate tạo `PreparedStatement` từ SQL.
3. JdbcTemplate gọi `setter.setValues(ps)` để bind tham số.
4. JdbcTemplate gọi `ps.executeUpdate()` và lấy số hàng tác động.
5. JdbcTemplate dọn tài nguyên và release connection, tôn trọng transaction đang hoạt động.

Với `jdbcTemplate.update(creator, keyHolder)`:

1. JdbcTemplate lấy Connection.
2. Gọi `creator.createPreparedStatement(connection)`; creator thường gọi `connection.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)` và bind giá trị.
3. JdbcTemplate gọi `executeUpdate()`, lấy generated keys nếu driver hỗ trợ và đưa vào `KeyHolder`.
4. JdbcTemplate đóng Statement và release Connection theo ngữ cảnh.

Số lần thực thi callback là một chi tiết của API/operation, không nên dùng callback để thực hiện side effect nghiệp vụ như gửi email hoặc ghi lại thanh toán. Callback có thể chạy trong thời điểm khác với giả định của bên gọi nếu dùng một API phức tạp; giữ nó ngắn, chỉ thuần JDBC và an toàn với transaction.

**Không làm bên trong hai callback:** gọi `connection.commit()`, `connection.rollback()`, `connection.close()`, `statement.close()`, mở một DataSource khác hoặc âm thầm đổi kết nối hiện hành. Những thao tác này phá vỡ trách nhiệm tài nguyên và có thể đi ngược giao dịch Spring.

## 5. Chọn overload `JdbcTemplate` nào?

Các overload thường dùng trên Spring Framework 6.x:

| Mục tiêu | API | Khi nên chọn |
| --- | --- | --- |
| Ghi dữ liệu đơn giản | `update(String sql, Object... args)` | Đủ khi chỉ cần bind một vài giá trị theo thứ tự |
| Ghi với cách bind tường minh | `update(String sql, PreparedStatementSetter pss)` | Kiểm soát `setNull`, kiểu JDBC, setter đặc thù hoặc thuộc tính statement |
| Ghi với cách tạo statement đặc biệt | `update(PreparedStatementCreator psc)` | Cần gọi `Connection.prepareStatement` theo tùy chọn riêng |
| Ghi và lấy khóa sinh | `update(PreparedStatementCreator psc, KeyHolder holder)` | INSERT có identity/sequence khi driver hỗ trợ generated keys |
| Truy vấn theo RowMapper | `query(String sql, PreparedStatementSetter pss, RowMapper<T> rm)` | SQL có sẵn, cần bind tham số và map từng hàng |
| Truy vấn với creator | `query(PreparedStatementCreator psc, RowMapper<T> rm)` | Cần tùy chỉnh cách tạo `PreparedStatement` |
| Lấy dữ liệu qua extractor | `query(String sql, PreparedStatementSetter pss, ResultSetExtractor<T> rse)` | Muốn tổng hợp toàn bộ ResultSet thành một cấu trúc |
| Truy vấn đơn giản | `query(String sql, RowMapper<T> rm, Object... args)` | Phần lớn SELECT có bind tham số thông thường |

**Một bẫy API:** `JdbcTemplate` có phương thức nội bộ/protected `update(PreparedStatementCreator, PreparedStatementSetter)`. Không được giả định đó là public overload để gọi trực tiếp từ một Repository bên ngoài. Với public API, các trường hợp update phổ biến chọn **creator hoặc setter**, tùy dạng overload, hoặc dùng `PreparedStatementCreatorFactory`.

Với câu truy vấn nhận cả creator và setter, JdbcTemplate có một số overload `query(PreparedStatementCreator, PreparedStatementSetter, ResultSetExtractor<T>)`. Chúng cần thiết ít hơn trong mã ứng dụng hàng ngày; giữ API dễ đọc nếu không có nhu cầu thật sự.

## 6. Bind tham số đúng: vị trí, kiểu SQL, null và bảo mật

### Vị trí tham số bắt đầu từ 1

Trong JDBC, chỉ số `?` bắt đầu từ **1**, không phải 0. Ví dụ:

~~~sql
UPDATE product
SET price = ?, stock = ?
WHERE id = ?;
~~~

~~~java
PreparedStatementSetter setter = ps -> {
    ps.setBigDecimal(1, price);
    ps.setInt(2, stock);
    ps.setLong(3, id);
};
~~~

Nhầm thứ tự có thể không gây SQLException nếu các kiểu tương thích, nhưng dữ liệu sẽ sai; do đó nên đối chiếu từng placeholder và dùng tên biến có ý nghĩa.

### Gắn giá trị SQL NULL

`null` cần được bind phù hợp kiểu JDBC; khi cột có thể nhận `NULL`:

~~~java
// Fragment: bảng có cột nullable INTEGER tên discount_percent.
PreparedStatementSetter setter = ps -> {
    ps.setString(1, sku);
    if (discountPercent == null) {
        ps.setNull(2, java.sql.Types.INTEGER);
    } else {
        ps.setInt(2, discountPercent);
    }
};
~~~

Có thể dùng `ps.setObject(index, value, Types.INTEGER)` với driver hỗ trợ chuẩn JDBC; `setNull` nêu rõ SQL type và thường dễ hiểu khi cần kiểm soát. Với `JdbcTemplate.update(sql, args...)`, có thể dùng `SqlParameterValue` hoặc overload khai báo mảng `argTypes` để truyền kiểu SQL tường minh.

### Các kiểu dữ liệu khác

- Số tiền nên dùng `BigDecimal` và `ps.setBigDecimal(index, amount)`; tránh `double` cho số tiền khi độ chính xác thập phân quan trọng.
- Với ngày giờ, xác định múi giờ/kiểu database. JDBC 4.2 cho phép nhiều ánh xạ `java.time` qua `setObject`, nhưng hành vi cụ thể vẫn phụ thuộc driver và SQL type.
- Với stream hoặc dữ liệu lớn, cần hiểu vòng đời tài nguyên/parameter cleanup và tránh đóng stream quá sớm trước khi JdbcTemplate thực thi statement.
- Dùng `ps.setString` cho giá trị văn bản; **không** nối dữ liệu không tin cậy thành SQL.

### PreparedStatement không bind được tên bảng/cột

`?` chỉ đại diện cho **giá trị dữ liệu**. Không thể viết `SELECT * FROM ?` rồi bind tên bảng hoặc `ORDER BY ?` rồi mong driver biến thành tên cột. Với identifier động, chọn từ whitelist do ứng dụng kiểm soát và tạo SQL thích hợp; không đưa trực tiếp input người dùng vào cấu trúc câu SQL.

## 7. Ví dụ chạy độc lập: Spring Boot + H2 + JdbcTemplate

Ví dụ dùng **Java 21**, **Gradle**, **Spring Boot 3.3.5**, **Spring JDBC** và **H2**. Các file dưới đây đủ để chạy một app console với `JdbcTemplate` được Boot cung cấp; không cần PostgreSQL, Docker hay HTTP server.

Ví dụ sẽ chứng minh:

1. `PreparedStatementCreator` gọi overload `prepareStatement(sql, RETURN_GENERATED_KEYS)` và gắn tham số để INSERT.
2. `GeneratedKeyHolder` nhận khóa tự sinh từ H2.
3. `PreparedStatementSetter` bind dữ liệu khi UPDATE và SELECT.
4. `RowMapper` làm việc khác hai callback trên: chuyển một hàng ResultSet thành đối tượng Java.
5. Creator cũng có thể dùng cho SELECT; không chỉ INSERT.

### 7.1. Cấu trúc dự án

~~~text
prepared-statement-callbacks/
├── build.gradle
└── src/main/
    ├── java/com/example/jdbccallbacks/
    │   ├── JdbcCallbacksApplication.java
    │   └── ProductRepository.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

### 7.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

`spring-boot-starter-jdbc` đưa `JdbcTemplate` và pool JDBC vào ứng dụng; H2 là driver/database runtime. Đây là ứng dụng console, không cần `spring-boot-starter-web`.

### 7.3. `src/main/resources/application.properties`

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:callbacks;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

Spring Boot chạy `schema.sql` khi DataSource được khởi tạo. `DB_CLOSE_DELAY=-1` để database H2 in-memory không tự mất ngay khi kết nối cuối đóng, giúp ví dụ độc lập với chu kỳ kết nối của pool.

### 7.4. `src/main/resources/schema.sql`

~~~sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    price DECIMAL(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0)
);
~~~

Schema này tạo bảng trống và khóa `id` do H2 tự sinh; đầu ra mẫu giả định mỗi lần chạy dùng database `mem:callbacks` mới trong một JVM riêng. Cấu trúc bảng phù hợp cả INSERT, UPDATE và SELECT bên dưới.

### 7.5. `ProductRepository.java`

~~~java
package com.example.jdbccallbacks;

import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementCreator;
import org.springframework.jdbc.core.PreparedStatementSetter;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public final class ProductRepository {

    private static final String SELECT_COLUMNS =
        "SELECT id, sku, price, stock FROM product";

    private static final RowMapper<Product> PRODUCT_MAPPER =
        (rs, rowNum) -> new Product(
            rs.getLong("id"),
            rs.getString("sku"),
            rs.getBigDecimal("price"),
            rs.getInt("stock")
        );

    private final JdbcTemplate jdbc;

    public ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Creator: quyết định cách tạo statement để lấy generated key.
    public long insertWithCreator(
            String sku, BigDecimal price, int stock) {

        String sql =
            "INSERT INTO product (sku, price, stock) VALUES (?, ?, ?)";

        PreparedStatementCreator creator = connection -> {
            PreparedStatement ps = connection.prepareStatement(
                sql, Statement.RETURN_GENERATED_KEYS
            );
            ps.setString(1, sku);
            ps.setBigDecimal(2, price);
            ps.setInt(3, stock);
            return ps;
        };

        GeneratedKeyHolder keyHolder = new GeneratedKeyHolder();
        int affected = jdbc.update(creator, keyHolder);

        if (affected != 1) {
            throw new IllegalStateException(
                "Expected one INSERT row, got " + affected
            );
        }
        Number id = keyHolder.getKey();
        if (id == null) {
            throw new IllegalStateException(
                "Database did not return generated id"
            );
        }
        return id.longValue();
    }

    // Setter: SQL đã có, chỉ bind dấu ? theo thứ tự 1-based.
    public int changeStockWithSetter(long id, int newStock) {
        String sql = "UPDATE product SET stock = ? WHERE id = ?";

        PreparedStatementSetter setter = ps -> {
            ps.setInt(1, newStock);
            ps.setLong(2, id);
        };

        return jdbc.update(sql, setter);
    }

    // Setter cho SELECT; RowMapper xử lý từng dòng kết quả.
    public List<Product> findStockAtLeastWithSetter(int minimumStock) {
        String sql = SELECT_COLUMNS
            + " WHERE stock >= ? ORDER BY id";

        PreparedStatementSetter setter = ps ->
            ps.setInt(1, minimumStock);

        return jdbc.query(sql, setter, PRODUCT_MAPPER);
    }

    // Creator cũng có thể dùng cho SELECT và tự bind tham số.
    public List<Product> findBySkuWithCreator(String sku) {
        PreparedStatementCreator creator = connection -> {
            PreparedStatement ps = connection.prepareStatement(
                SELECT_COLUMNS + " WHERE sku = ?"
            );
            ps.setString(1, sku);
            return ps;
        };

        return jdbc.query(creator, PRODUCT_MAPPER);
    }

    public record Product(
        long id, String sku, BigDecimal price, int stock
    ) {}
}
~~~

Tại đây có bốn phương thức rõ vai trò. `insertWithCreator` cần API lấy generated keys; `changeStockWithSetter` chỉ bind `?` vào SQL chuẩn; `findStockAtLeastWithSetter` bind rồi ánh xạ kết quả; `findBySkuWithCreator` chứng minh creator không bị giới hạn ở INSERT. `RowMapper` nhận `(ResultSet, rowNum)`, hoàn toàn khác `PreparedStatementSetter`.

Lưu ý số hàng thay đổi: `JdbcTemplate.update(...)` trả số dòng UPDATE tác động, không phải ID. Với INSERT cần ID tự sinh, dùng `KeyHolder`; `GeneratedKeyHolder.getKey()` phù hợp khi driver trả đúng một khóa số. Nếu DB/driver trả nhiều cột generated keys hoặc khóa không phải số, cần kiểm tra `getKeys()`/`getKeyList()` thay vì giả định duy nhất một Number.

### 7.6. `JdbcCallbacksApplication.java`

~~~java
package com.example.jdbccallbacks;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JdbcCallbacksApplication {
    public static void main(String[] args) {
        SpringApplication.run(JdbcCallbacksApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ProductRepository repository) {
        return args -> {
            long id = repository.insertWithCreator(
                "JAVA-CORE", new BigDecimal("125.50"), 5
            );
            System.out.println("Generated id = " + id);

            int affected = repository.changeStockWithSetter(id, 7);
            System.out.println("Updated rows = " + affected);

            List<ProductRepository.Product> products =
                repository.findStockAtLeastWithSetter(3);
            System.out.println("Found = " + products.size());
            System.out.println("Stock = " + products.get(0).stock());

            int matchingSku = repository
                .findBySkuWithCreator("JAVA-CORE").size();
            System.out.println("By SKU = " + matchingSku);
        };
    }
}
~~~

### 7.7. Chạy và đọc đầu ra

Tại thư mục dự án có `build.gradle`:

~~~bash
# Nếu dự án đã có Gradle Wrapper:
./gradlew bootRun

# Nếu chưa có Wrapper nhưng đã cài Gradle tương thích:
gradle bootRun
~~~

Trên Windows PowerShell, với wrapper: `.\gradlew.bat bootRun`. Java 21 phải được cài hoặc Gradle được cấu hình provisioning toolchain. Các dòng **do chương trình in** (bỏ log khởi động Spring/HikariCP và thông báo Gradle) là:

~~~text
Generated id = 1
Updated rows = 1
Found = 1
Stock = 7
By SKU = 1
~~~

Các bước của ví dụ:

1. H2 tạo bảng trống; identity đầu tiên là 1 trong database mới.
2. `PreparedStatementCreator` tạo statement với cờ generated keys, bind ba tham số, trả statement cho JdbcTemplate; `KeyHolder` lấy ID = 1.
3. `PreparedStatementSetter` đặt `stock=7` và `id=1`; `UPDATE` tác động đúng một dòng.
4. Setter thứ hai bind ngưỡng 3; RowMapper đọc bản ghi có stock 7.
5. Creator SELECT tạo statement, gắn `sku` và trả danh sách chứa đúng một sản phẩm.

**Tại sao ví dụ không tự gọi `executeQuery` trong creator?** Vì creator chỉ phải **tạo statement**; `JdbcTemplate.query(...)` thực thi và tiêu thụ `ResultSet`. Cũng không gọi `ps.close()` trong creator. Nếu gọi execute hoặc close thủ công ở callback, trình tự quản lý tài nguyên của template không còn đúng ý định.

Trong ứng dụng thực, nên kiểm tra dữ liệu đầu vào và số hàng tác động ở tầng thích hợp, đặt ranh giới `@Transactional` theo nghiệp vụ khi có nhiều bước cần nguyên tử, kiểm soát concurrency và xử lý lỗi từ database như unique constraint.

## 8. Đọc sâu: tại sao creator hữu ích khi lấy generated keys?

Có một khác biệt JDBC quan trọng:

~~~java
connection.prepareStatement(sql);
connection.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS);
connection.prepareStatement(sql, new String[] { "ID" });
~~~

Các overload này tạo `PreparedStatement` với các lựa chọn khác nhau. Nếu dùng setter, statement đã được JdbcTemplate tạo từ `String sql`; không thể quay ngược lại chọn overload tạo statement.

Với H2, cách dùng `Statement.RETURN_GENERATED_KEYS` ở bài demo phù hợp. Một số driver/database đòi chỉ rõ tên cột generated key; khi đó creator có thể gọi `connection.prepareStatement(sql, new String[] { "id" })` (tên/casing theo driver). Cần xác nhận `DatabaseMetaData.supportsGetGeneratedKeys()` và hành vi driver thực tế.

Đầu ra của `GeneratedKeyHolder` không bảo đảm luôn là một khóa `long`. Nếu database có nhiều generated columns, `getKey()` có thể không phù hợp; đọc map/list và tên cột mong đợi. Điều quan trọng là dùng **creator kích hoạt lấy key**; truyền KeyHolder mà không tạo statement hỗ trợ key sẽ không tự ép DB trả khóa.

## 9. `PreparedStatementCreatorFactory`: giảm code creator lặp lại

Khi nhiều thao tác dùng cùng mẫu SQL và danh sách kiểu tham số, Spring có lớp `PreparedStatementCreatorFactory`. Nó biết SQL, khai báo kiểu JDBC và có thể tạo creator hoặc setter theo tham số.

Ví dụ sau là **fragment API**, không phải file Java độc lập; có thể dùng bên trong Repository đã có biến `jdbc`:

~~~java
String sql =
    "INSERT INTO product (sku, price, stock) VALUES (?, ?, ?)";

PreparedStatementCreatorFactory factory =
    new PreparedStatementCreatorFactory(
        sql, Types.VARCHAR, Types.DECIMAL, Types.INTEGER
    );
factory.setReturnGeneratedKeys(true);

PreparedStatementCreator creator =
    factory.newPreparedStatementCreator(
        new Object[] { "SPRING-BOOK", new BigDecimal("89.00"), 2 }
    );

GeneratedKeyHolder holder = new GeneratedKeyHolder();
int rows = jdbc.update(creator, holder);
~~~

Các import cần có khi đưa fragment vào code:

~~~java
import java.math.BigDecimal;
import java.sql.Types;
import org.springframework.jdbc.core.PreparedStatementCreator;
import org.springframework.jdbc.core.PreparedStatementCreatorFactory;
import org.springframework.jdbc.support.GeneratedKeyHolder;
~~~

Factory hữu ích khi muốn **khai báo kiểu SQL rõ ràng**, đồng bộ nhiều lần chạy hoặc cấu hình generated keys mà không tự viết lambda tạo PreparedStatement. Cũng có thể dùng `setGeneratedKeysColumnNames(...)`. Vì ví dụ trên không phải file độc lập, không có stdout riêng; `rows` là số dòng INSERT, thường bằng 1 khi thành công.

**Không nhầm lẫn API:** `PreparedStatementCreatorFactory.newPreparedStatementCreator(...)` tạo object callback; bản thân lời gọi này **chưa thực thi SQL**. SQL thực thi khi callback được chuyển cho JdbcTemplate.

## 10. `PreparedStatementSetter` còn làm được gì ngoài bind `?`?

Setter có một reference tới `PreparedStatement` đã tạo. Ngoài parameter binding, có thể điều chỉnh thuộc tính hợp lệ trên statement trước thực thi, ví dụ:

~~~java
// Fragment minh họa query; RowMapper 'mapper' đã có sẵn.
PreparedStatementSetter setter = ps -> {
    ps.setInt(1, minimumStock);
    ps.setFetchSize(100);
    ps.setMaxRows(500);
};

List<Product> result = jdbc.query(
    "SELECT id, sku, price, stock FROM product " +
    "WHERE stock >= ? ORDER BY id",
    setter,
    mapper
);
~~~

Những thuộc tính này phải phù hợp với driver và cấu hình `JdbcTemplate`. `setFetchSize` là **hint** giúp cách driver lấy dữ liệu; không có nghĩa DB luôn trả đúng từng khối 100 dòng hoặc mọi driver đều stream. `setMaxRows` hạn chế số dòng ResultSet theo JDBC, không thay thế phân trang và index ở SQL. Nếu cấu hình transaction timeout, Spring/JdbcTemplate có thể áp dụng statement timeout liên quan đến transaction; không tùy tiện ghi đè những cấu hình bảo vệ đã được thiết kế.

### Truy vấn streaming

Một số overload `queryForStream(...)` trả Java Stream cần được **đóng** sau khi duyệt:

~~~java
// Fragment minh họa; mapper là RowMapper<Product>.
try (var products = jdbc.queryForStream(
        "SELECT id, sku, price, stock FROM product",
        mapper
)) {
    products.limit(5).forEach(System.out::println);
}
~~~

Đây là trường hợp **tài nguyên kết quả có vòng đời khác một `List` đã materialize**. Dù JdbcTemplate quản lý statement, bên gọi stream phải đóng Stream theo hợp đồng của API. Đừng để stream thoát ra khỏi transaction scope rồi tiếp tục đọc tại nơi không còn kết nối phù hợp.

## 11. Quan hệ với `RowMapper`, `ResultSetExtractor` và `PreparedStatementCallback`

Hai callback của bài học chủ yếu thuộc **giai đoạn chuẩn bị statement**. Các callback khác thuộc **giai đoạn tiêu thụ kết quả hoặc thực thi tùy biến**:

| Callback | Chữ ký khái niệm | Công việc |
| --- | --- | --- |
| `PreparedStatementCreator` | `PreparedStatement createPreparedStatement(Connection)` | Tạo JDBC statement theo cách mong muốn |
| `PreparedStatementSetter` | `void setValues(PreparedStatement)` | Gắn tham số hoặc cấu hình statement đã có |
| `RowMapper<T>` | `T mapRow(ResultSet, int)` | Ánh xạ một hàng trong ResultSet thành một object |
| `ResultSetExtractor<T>` | `T extractData(ResultSet)` | Tự trích xuất/tổng hợp cả ResultSet |
| `PreparedStatementCallback<T>` | `T doInPreparedStatement(PreparedStatement)` | Chạy thao tác tùy biến trên statement |
| `BatchPreparedStatementSetter` | `setValues(ps, i)` + `getBatchSize()` | Bind một lần cho từng phần tử của batch |

Đừng gán nhiệm vụ map ResultSet cho setter: `setValues` chạy trước khi `executeQuery()` nên không được truyền ResultSet. Ngược lại RowMapper không phải nơi quyết định SQL hay điều chỉnh Connection.

### Khi nào dùng `PreparedStatementCallback`?

Nếu cần thực hiện một chuỗi thao tác đặc biệt với cùng PreparedStatement mà các overload phổ biến không thể biểu đạt gọn, JdbcTemplate có API dạng:

~~~java
// Fragment: biến jdbc là JdbcTemplate; sql và tham số đã xác định.
// Không phải ví dụ cần dùng cho truy vấn CRUD thông thường.
Integer affected = jdbc.execute(
    "UPDATE product SET stock = ? WHERE id = ?",
    ps -> {
        ps.setInt(1, newStock);
        ps.setLong(2, productId);
        return ps.executeUpdate();
    }
);
~~~

Lambda trong `execute(String, PreparedStatementCallback<T>)` tự thực thi `ps.executeUpdate()` vì nó là **callback thực thi**, khác với setter ở `update(String, PreparedStatementSetter)`. Chọn API này chỉ khi thực sự cần kiểm soát thao tác trên statement; thông thường `update(sql, setter)` thể hiện ý định rõ hơn.

## 12. Batch SQL: không nhầm setter thường với setter của batch

Một `PreparedStatementSetter` thông thường có chữ ký `setValues(PreparedStatement ps)` cho một statement operation. Nếu muốn chạy nhiều bộ giá trị trên cùng mẫu SQL, API chuyên biệt là `BatchPreparedStatementSetter`:

~~~java
// Fragment minh họa: updates là List<StockChange> đã được xác định.
int[] counts = jdbc.batchUpdate(
    "UPDATE product SET stock = ? WHERE id = ?",
    new BatchPreparedStatementSetter() {
        @Override
        public void setValues(PreparedStatement ps, int index)
                throws SQLException {
            StockChange change = updates.get(index);
            ps.setInt(1, change.stock());
            ps.setLong(2, change.id());
        }

        @Override
        public int getBatchSize() {
            return updates.size();
        }
    }
);
~~~

Ở đây `index` của **batch** bắt đầu từ **0**, còn vị trí bind tham số trong PreparedStatement vẫn bắt đầu từ **1**. Cũng có overload dùng `ParameterizedPreparedStatementSetter<T>` trong `batchUpdate(sql, collection, batchSize, setter)` với chữ ký `setValues(PreparedStatement ps, T argument)`.

**Lưu ý:** Batch thường giảm round trips, nhưng cách driver triển khai và giá trị `int[]` có thể khác nhau; JDBC cho phép các mã `Statement.SUCCESS_NO_INFO` hoặc `Statement.EXECUTE_FAILED`. Batch không tự tạo transaction nghiệp vụ bao toàn bộ các thao tác; để atomicity, vẫn cần transaction boundary thích hợp.

Batch hữu ích để đối chiếu **khác biệt trách nhiệm**, nhưng không thay mục tiêu của bài này: cách **tạo** PreparedStatement và cách **bind** parameter trên từng statement.

## 13. Giao dịch Spring và vòng đời JDBC trong callback

Sử dụng `JdbcTemplate` trong repository không tự bảo đảm toàn bộ use case gồm nhiều lệnh chạy nguyên tử. Khi cần một transaction bao nhiều lệnh SQL, thông thường Service được Spring quản lý đặt `@Transactional`:

~~~java
// Fragment minh họa kiến trúc; không phải file biên dịch độc lập.
@Service
public class InventoryService {
    private final ProductRepository products;

    public InventoryService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void applyAdjustment(long firstId, long secondId) {
        products.changeStockWithSetter(firstId, 7);
        products.changeStockWithSetter(secondId, 2);
    }
}
~~~

Các import `@Service`/`@Transactional` nằm trong Spring, cùng với `ProductRepository` từ ví dụ trên. Trong ứng dụng thật, thay vì ghi đè stock cố định, hãy tính toán điều kiện cập nhật đúng nghiệp vụ và kiểm tra affected rows. Fragment này chỉ cho thấy **vị trí đặt ranh giới transaction**.

Trong một transaction Spring, JdbcTemplate lấy Connection do transaction manager điều phối; creator nhận chính Connection trong ngữ cảnh đó. Vì thế **không được** viết creator kiểu:

~~~java
// PHẢN VÍ DỤ: không làm như sau.
PreparedStatementCreator wrong = ignoredConnection -> {
    Connection another = dataSource.getConnection();
    return another.prepareStatement("UPDATE product SET stock = 0");
};
~~~

Code phản ví dụ này cố ý không độc lập và sai ownership. Nó bỏ qua Connection Spring cấp, có nguy cơ dùng transaction khác, rò rỉ `another` và khiến JdbcTemplate đóng/release tài nguyên không đồng bộ. Đúng phải dùng `connection` nhận từ callback:

~~~java
PreparedStatementCreator correct = connection ->
    connection.prepareStatement("UPDATE product SET stock = 0");
~~~

**Không tự gọi commit/rollback trong callback** khi Spring đang quản lý transaction. Để Service và transaction manager quyết định ranh giới; callback chỉ chuẩn bị statement và bind giá trị. `SQLException` do callback ném sẽ được JdbcTemplate bắt và dịch thành dạng `DataAccessException` phù hợp khi có thể; code ứng dụng không cần bọc mọi setter bằng `try-catch SQLException` rồi nuốt lỗi.

## 14. Phân tích lỗi: callback nào sai?

| Dấu hiệu | Nguyên nhân dễ gặp | Vị trí cần kiểm tra |
| --- | --- | --- |
| `Parameter index out of range` | SQL có N dấu `?` nhưng bind sai chỉ số/bind thừa | `PreparedStatementSetter` hoặc phần bind trong creator |
| `No value specified for parameter` | Thiếu một placeholder | Đối chiếu thứ tự SQL và các `ps.setXxx` |
| INSERT thành công nhưng `KeyHolder` rỗng | Creator không bật generated keys hoặc driver không hỗ trợ | `prepareStatement(sql, RETURN_GENERATED_KEYS)`, driver metadata |
| `SQLSyntaxErrorException`/`BadSqlGrammarException` | SQL sai cú pháp/tên cột | SQL tạo trong creator hoặc truyền cho JdbcTemplate |
| `DataIntegrityViolationException` | Unique/foreign key/check constraint vi phạm | Input, quy tắc nghiệp vụ và schema/DB constraints |
| Kết quả SELECT đọc sai kiểu | RowMapper/ResultSet getter không tương thích | Mapper/SQL column aliases |
| Pool timeout hoặc connection leak | Giữ connection/stream lâu hoặc tự mở connection ngoài template | DataSource, transaction, queryForStream, callback ownership |
| Lệnh UPDATE tác động 0 dòng | WHERE không khớp hoặc bản ghi không tồn tại | Xem affected row count và điều kiện SQL |
| Transaction chỉ hoàn tất một phần | Các thao tác không cùng transaction manager/tài nguyên | Service transaction boundary, tránh tự mở Connection |

**Cách gỡ lỗi có hệ thống:** Đầu tiên in/log SQL ở mức thích hợp (không log bí mật), đối chiếu chính xác các placeholder với giá trị và JDBC type, kiểm tra số dòng tác động, sau đó xác nhận datasource/transaction cùng ngữ cảnh. SQL injection thường xuất phát từ nối chuỗi input vào SQL; PreparedStatement chỉ an toàn cho **giá trị được bind thật**.

### Debugging có ngữ cảnh từ SQL

Một `PreparedStatementCreator` viết bằng class riêng có thể triển khai thêm `SqlProvider` để cung cấp SQL cho framework trong một số đường dịch ngoại lệ. Nếu không có yêu cầu cụ thể, lambda đơn giản giúp code ít dòng; log hoặc lỗi database đã có thể đủ thông tin. Không tự viết wrapper duy trì global cache các PreparedStatement, vì mỗi PreparedStatement gắn với Connection và vòng đời riêng của nó.

## 15. Hiệu năng: “Prepared” có đồng nghĩa “nhanh hơn”?

`PreparedStatement` giúp tách SQL và dữ liệu đầu vào, dễ bind kiểu, thường hỗ trợ driver/database tối ưu việc xử lý SQL, nhưng **không đảm bảo mỗi SQL sẽ luôn có server-side plan được cache**. Cơ chế parse/prepare/cache cụ thể phụ thuộc JDBC driver, database, connection và cấu hình. Tạo `PreparedStatementCreator` trong Java **không** tự tạo một global statement cache.

Các yếu tố ảnh hưởng hiệu năng thực tế:

- **Round trip:** Một SELECT trong vòng lặp nhiều lần có thể chậm hơn một query lấy đủ dữ liệu cần dùng, dù mỗi lần dùng PreparedStatement.
- **Indexes và SQL:** `WHERE`, `JOIN`, số hàng trả về, plan truy vấn thường có tác động lớn.
- **Batches:** Gom nhiều giá trị qua `batchUpdate` khi phù hợp, cân nhắc giới hạn kích thước và transaction.
- **Pool/transaction:** Giữ Connection lâu ảnh hưởng throughput; callback không nên thực hiện mạng ngoài hoặc blocking work không liên quan JDBC.
- **Lấy dữ liệu lớn:** Cân nhắc fetch size, streaming và resource lifetime; không dùng callback như nơi chứa toàn bộ xử lý nghiệp vụ.

Hãy chọn callback vì **yêu cầu API và tính rõ ràng**, rồi đo hiệu năng theo workload thật. Tối ưu ít dòng Java bằng cách gộp mọi thứ vào creator không làm SQL nhanh hơn.

## 16. Khi nào không cần hai callback?

Mã CRUD đơn giản thường ngắn hơn với varargs:

~~~java
int rows = jdbc.update(
    "UPDATE product SET stock = ? WHERE id = ?",
    newStock, id
);
~~~

Nếu cần SQL có tên tham số dễ đọc, `NamedParameterJdbcTemplate` có thể phù hợp:

~~~java
// Fragment, namedJdbc đã được tạo từ cùng DataSource.
MapSqlParameterSource parameters = new MapSqlParameterSource()
    .addValue("stock", newStock)
    .addValue("productId", id);

int rows = namedJdbc.update(
    "UPDATE product SET stock = :stock WHERE id = :productId",
    parameters
);
~~~

Với ứng dụng Spring Framework 6.1+, `JdbcClient` cung cấp fluent API ở phía trên JdbcTemplate/NamedParameterJdbcTemplate cho nhiều trường hợp thông thường. Những lựa chọn đó **không làm callback sai hoặc bị loại bỏ**; callback vẫn hữu ích khi cần kiểm soát kiểu bind, generated keys, statement creation options và tương tác JDBC mức thấp.

**Tiêu chí lựa chọn nhanh:**

1. **Chỉ truyền vài tham số:** `update(sql, args...)` hoặc `query(sql, mapper, args...)`.
2. **Cần bind tùy biến nhưng cách tạo statement mặc định đủ:** `PreparedStatementSetter`.
3. **Cần tự chọn overload `Connection.prepareStatement(...)`:** `PreparedStatementCreator`.
4. **SQL/kiểu tham số ổn định, tạo nhiều creator hoặc cần generated keys theo cấu hình:** `PreparedStatementCreatorFactory`.
5. **Một mẫu SQL cho nhiều bộ giá trị:** `BatchPreparedStatementSetter` hoặc `ParameterizedPreparedStatementSetter`.
6. **Muốn API SQL tham số tên/fluent:** `NamedParameterJdbcTemplate` hoặc `JdbcClient`, khi chức năng đáp ứng yêu cầu.

## 17. Những hiểu lầm phổ biến

**“Creator chỉ dành cho INSERT, Setter chỉ dành cho UPDATE.”** Sai. Cả hai có thể dùng với SELECT, UPDATE hoặc INSERT tùy overload. Creator quyết định **cách tạo** statement, Setter quyết định **giá trị trên** statement.

**“Setter tạo statement trước khi setValues.”** Không. `JdbcTemplate` đã tạo statement; setter chỉ được nhận reference đến statement đã có.

**“Creator không thể bind tham số.”** Không đúng. Creator có thể vừa tạo vừa bind, vì nó trả một statement đã được cấu hình cho JdbcTemplate thực thi. Với thiết kế cần tái sử dụng kiểu bind, factory có thể giúp tránh lặp mã.

**“Phải tự close PreparedStatement trong callback để tránh leak.”** Sai với `JdbcTemplate`. Spring chịu trách nhiệm đóng statement/result set và release kết nối; đóng sớm khiến JdbcTemplate không còn thực thi được.

**“Một `PreparedStatementSetter` phải tự executeUpdate.”** Sai với `JdbcTemplate.update(sql, setter)`. Cần phân biệt với `PreparedStatementCallback` của `JdbcTemplate.execute(...)`, nơi callback chủ động thực thi.

**“Gắn bind tham số với `?` là SQL luôn an toàn.”** Chỉ đúng cho các **giá trị đã bind**; nếu tên bảng/cột/ORDER BY vẫn nối chuỗi input không kiểm soát, injection vẫn có thể xảy ra.

**“Muốn nhận generated keys chỉ cần tạo `GeneratedKeyHolder`.”** Chưa đủ. Statement/driver cần được tạo và cấu hình để trả generated keys, và cách đọc KeyHolder phải phù hợp cấu trúc khóa.

**“PreparedStatement trên mọi driver tự cache plan giống nhau.”** Không. Driver/database quyết định hiệu quả cache và thời điểm server-side prepare.

**“Mỗi setter là một record batch.”** Không. Setter thường không có index batch; API chuyên biệt `BatchPreparedStatementSetter` có `setValues(ps, int i)` và `getBatchSize()`.

## 18. Bài tập và câu hỏi tự kiểm tra

**Bài tập 1 — xác định API:** Bạn phải INSERT và lấy ID tự tăng từ JDBC driver. Dùng callback nào?  
**Đáp án:** Dùng `PreparedStatementCreator` với `prepareStatement(sql, RETURN_GENERATED_KEYS)` rồi `JdbcTemplate.update(creator, keyHolder)`; hoặc dùng factory tạo creator bật generated keys.

**Bài tập 2 — kiểm tra 1-based:** Với `UPDATE product SET price = ?, stock = ? WHERE id = ?`, `ps.setLong(0, id)` đúng không?  
**Đáp án:** Sai. JDBC param position bắt đầu từ 1. Tên cột đầu tiên không liên quan vị trí bind nếu thứ tự SQL khác.

**Bài tập 3 — query:** Với SELECT nhận `minimumStock` và trả danh sách Product, cần callback nào ngoài setter?  
**Đáp án:** `RowMapper<Product>`; setter chỉ bind giá trị, mapper đọc `ResultSet` sau thực thi.

**Bài tập 4 — typed null:** Nếu một giá trị tùy chọn ánh xạ tới SQL INTEGER nullable, tại sao `ps.setNull(index, Types.INTEGER)` đáng cân nhắc?  
**Đáp án:** Đưa SQL type tường minh cho driver, tránh suy luận không phù hợp ở một số trường hợp.

**Bài tập 5 — ownership:** Trong creator, có được gọi `dataSource.getConnection()` để thay Connection do Spring đưa vào không?  
**Đáp án:** Không nên. Creator phải dùng Connection được truyền để giữ resource và transaction lifecycle đúng.

**Bài tập 6 — batch:** Với 1000 bản ghi cùng mẫu UPDATE, có nên gọi `PreparedStatementSetter.setValues(ps)` 1000 lần thủ công trên một statement rồi kỳ vọng JdbcTemplate tự batch?  
**Đáp án:** Không. Dùng `batchUpdate` với `BatchPreparedStatementSetter` hoặc API batch thích hợp; phải xét transaction và driver.

**Bài tập triển khai:** Thêm phương thức `updatePriceWithSetter(long id, BigDecimal price)` vào repository ở phần 7, trả số hàng cập nhật. Viết thêm `findByPriceAtMostWithCreator(BigDecimal maximum)` dùng `query(PreparedStatementCreator, RowMapper)`. Xây integration test khởi chạy Spring context với H2, kiểm tra dữ liệu đọc lại đúng; thử giá trị âm để thấy DB CHECK constraint phản ứng. Nếu làm nhiều update cần nguyên tử, bọc ở một public Service method `@Transactional` và kiểm tra rollback bằng test có database thực.

## 19. Tài liệu tham khảo chính thức

- [`PreparedStatementCreator` — Spring Framework API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/PreparedStatementCreator.html): hợp đồng nhận Connection và trả PreparedStatement.
- [`PreparedStatementSetter` — Spring Framework API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/PreparedStatementSetter.html): hợp đồng nhận statement để gắn tham số.
- [`JdbcTemplate` — Spring Framework API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): các overload `update`, `query`, `execute` và batch.
- [`PreparedStatementCreatorFactory` — Spring Framework API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/PreparedStatementCreatorFactory.html): tạo creator/setter dựa trên SQL và kiểu tham số.
- [Spring Framework — JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html): cách dùng các callback dành riêng cho batch.

**Ghi nhớ:** `PreparedStatementCreator` quyết định **PreparedStatement được tạo như thế nào từ Connection**; `PreparedStatementSetter` quyết định **các tham số được gắn như thế nào vào statement đã có**. `JdbcTemplate` quyết định **khi nào thực thi và cách quản lý tài nguyên**, trong khi Service/transaction manager quyết định ranh giới nghiệp vụ và giao dịch. Chọn callback theo đúng trách nhiệm sẽ làm mã JDBC ngắn hơn, dễ kiểm thử và ít lỗi vòng đời tài nguyên.

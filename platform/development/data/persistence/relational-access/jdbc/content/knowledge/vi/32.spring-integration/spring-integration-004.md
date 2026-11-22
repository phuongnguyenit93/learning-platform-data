# Truy vấn tham số có tên với NamedParameterJdbcTemplate

> **Chương:** Tích hợp Spring  
> **Phạm vi:** Ứng dụng Java 17+ dùng **JDBC** để truy cập cơ sở dữ liệu quan hệ qua driver, `DataSource`, `PreparedStatement` và `ResultSet`. Bài này giới thiệu `NamedParameterJdbcTemplate` của **Spring JDBC** để viết SQL tham số hóa dễ đọc, kết hợp CRUD, batch và transaction. Ví dụ dùng Spring Framework 6.x / Spring Boot 3.x cùng PostgreSQL; cơ chế bind JDBC là nền tảng chung, còn cú pháp SQL và chi tiết driver phải kiểm thử theo DBMS mục tiêu.

Một hệ thống bán hàng cần tìm sản phẩm theo tenant, mã SKU, trạng thái và khoảng giá. Với `JdbcTemplate` thông thường, câu SQL nhiều dấu `?` có thể khó bảo trì: nếu đổi thứ tự điều kiện mà quên đổi thứ tự tham số Java, truy vấn vẫn chạy nhưng lọc sai dữ liệu. Spring cung cấp `NamedParameterJdbcTemplate` để biểu thị tham số bằng **tên có nghĩa**, như `:tenantId`, `:sku`, `:minPrice`.

`NamedParameterJdbcTemplate` **không thay thế JDBC driver hay database**. Nó phân tích các tham số có tên, ánh xạ giá trị tương ứng và sử dụng JDBC `PreparedStatement` phía dưới (thông qua cơ chế của Spring JDBC). Nhờ đó ứng dụng vẫn có SQL tường minh và kiểm soát transaction, đồng thời giảm lỗi do nhớ thứ tự tham số.

Sau bài học, người học có thể:

- Phân biệt tham số vị trí `?` của JDBC/`JdbcTemplate` với tham số có tên `:name`.
- Cấu hình `NamedParameterJdbcTemplate` từ `DataSource` và truy vấn theo `Map`, `MapSqlParameterSource` hoặc `BeanPropertySqlParameterSource`.
- Dùng `query()`, `queryForObject()`, `update()`, `batchUpdate()`, `RowMapper` và `KeyHolder` đúng ngữ nghĩa.
- Xử lý tham số lặp, tập giá trị trong `IN (:ids)`, danh sách rỗng, `NULL` và kiểu SQL.
- Kết hợp repository với `@Transactional` mà không tự mở/commit một connection thứ hai.
- Phòng tránh SQL injection khi người dùng chọn cột/sắp xếp và kiểm thử tích hợp với database thật.

## 1. Từ `?` đến `:name`: điểm khác nhau cốt lõi

Cùng một câu truy vấn có thể được viết theo hai cách.

**`JdbcTemplate` với tham số theo vị trí:**

```java
String sql = """
    SELECT id, sku, name, price
    FROM catalog_product
    WHERE tenant_id = ?
      AND sku = ?
      AND active = ?
    """;

List<ProductRow> products = jdbcTemplate.query(
    sql,
    productRowMapper,
    tenantId,
    sku,
    true
);
```

Thứ tự giá trị ở Java phải khớp chính xác các dấu `?`. Nếu một người sửa SQL và đổi `WHERE sku = ?` lên trước `WHERE tenant_id = ?` nhưng không cập nhật danh sách giá trị, kết quả có thể sai hoặc phát sinh lỗi kiểu dữ liệu.

**`NamedParameterJdbcTemplate` với tham số theo tên:**

```java
String sql = """
    SELECT id, sku, name, price
    FROM catalog_product
    WHERE tenant_id = :tenantId
      AND sku = :sku
      AND active = :active
    """;

Map<String, Object> params = Map.of(
    "tenantId", tenantId,
    "sku", sku,
    "active", true
);

List<ProductRow> products =
    namedJdbc.query(sql, params, productRowMapper);
```

`productRowMapper` và các biến đầu vào ở đây là những đối tượng ứng dụng đã khai báo; ví dụ repository hoàn chỉnh sẽ xuất hiện ở mục 6.

Tên tham số gắn ngữ nghĩa trực tiếp với giá trị. Việc thêm điều kiện hoặc đổi thứ tự hai điều kiện sẽ ít gây nhầm lẫn hơn, vì `:sku` vẫn được lấy từ khóa `"sku"`.

| Đặc điểm | `JdbcTemplate` với `?` | `NamedParameterJdbcTemplate` với `:name` |
|---|---|---|
| Cách định danh tham số | Theo vị trí `1, 2, 3, ...` | Theo tên `tenantId`, `sku`, `active` |
| Cần giữ đúng thứ tự ở Java | Có | Không, miễn tên đúng |
| Dùng lại cùng tham số nhiều lần | Phải truyền giá trị cho từng vị trí | Một giá trị theo tên có thể được dùng lại |
| Bind tập giá trị cho `IN` | Thường phải tạo đúng số `?` | Có cơ chế mở rộng collection/list cho danh sách |
| Ánh xạ kết quả JDBC | `RowMapper` và các cơ chế Spring JDBC | `RowMapper` và các cơ chế Spring JDBC |
| Connection và transaction | Dựa trên `DataSource` và transaction manager | Cùng cơ chế Spring JDBC |
| Phòng SQL injection cho **giá trị** | Có khi bind đúng | Có khi bind đúng |
| Bind tên bảng, cột hoặc `ORDER BY` tùy ý | Không | **Không** |

**Điểm mấu chốt:** tham số có tên giúp SQL dễ đọc hơn; nó không làm câu truy vấn “thông minh” hơn về authorization, index, transaction hoặc tính khả chuyển giữa các dialect.

## 2. Điều gì thực sự xảy ra khi Spring chạy SQL có tên?

Database và JDBC driver thường nhận một `PreparedStatement` với các vị trí bind. `NamedParameterJdbcTemplate` thực hiện bước chuyển đổi trước khi gửi câu SQL tới driver:

```text
SQL trong ứng dụng:
SELECT * FROM catalog_product
WHERE tenant_id = :tenantId AND (sku = :term OR name = :term)

                         |
                         v
Spring phân tích SQL và ánh xạ các tham số
                         |
                         v
SQL tương ứng cho JDBC:
SELECT * FROM catalog_product
WHERE tenant_id = ? AND (sku = ? OR name = ?)

Các giá trị bind:
  1 = tenantId
  2 = term
  3 = term
                         |
                         v
PreparedStatement + JDBC driver + DBMS
```

`:term` xuất hiện hai lần nhưng chỉ cần **khai báo một giá trị `term`** trong source. Spring sẽ bind nó tại các vị trí tương ứng. Đây là **tham số hóa giá trị**, không phải thay chuỗi tùy ý vào SQL.

Khi câu SQL dùng cấu trúc đặc thù DBMS (ví dụ toán tử PostgreSQL, cú pháp ép kiểu hoặc chuỗi JSON), phải kiểm thử khả năng phân tích named parameters trên phiên bản Spring và driver đang dùng. Với phần SQL bình thường, đừng tự viết trình thay thế chuỗi `.replace(":id", "...")`: tự ghép như vậy làm mất sự bảo vệ của prepared statement và dễ xử lý sai ký tự quote/comment.

### Vì sao có hai lớp API?

- **JDBC (`java.sql`, `javax.sql`):** `Connection`, `PreparedStatement`, `ResultSet`, `SQLException`, `DataSource`.
- **Spring JDBC (`org.springframework.jdbc`):** `JdbcTemplate`, `NamedParameterJdbcTemplate`, `RowMapper`, các lớp nguồn tham số và exception translation.

Spring giúp quản lý những mẫu lặp của JDBC như lấy/đóng connection và statement, bind giá trị, lặp result set, dịch lỗi. Database vẫn là nơi thực thi SQL và áp dụng constraint, isolation, transaction.

## 3. Cấu hình trong Spring Boot hoặc Spring thông thường

Trong dự án **Spring Boot có dependency management phù hợp**, những dependency phổ biến là:

```xml
<!-- Dùng trong một project có Spring Boot parent/BOM quản lý version. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

`spring-boot-starter-jdbc` cung cấp phần lớn hạ tầng Spring JDBC và kết nối với transaction/pool theo cấu hình của Boot. Driver PostgreSQL là dependency riêng; thay driver khi dùng DBMS khác.

Spring Boot có thể cấu hình `DataSource` từ các thuộc tính hoặc biến môi trường:

```text
SPRING_DATASOURCE_URL=jdbc:postgresql://localhost:5432/shop
SPRING_DATASOURCE_USERNAME=app_user
SPRING_DATASOURCE_PASSWORD=<secret-from-environment>
```

Các giá trị trên là **ví dụ cấu hình**, không phải thông tin để dùng nguyên trong production; quản lý password bằng môi trường/secret manager, tránh commit vào source control. Khi có một `DataSource`/`JdbcTemplate` phù hợp, các cấu hình Spring Boot JDBC hiện đại thường có thể cung cấp `NamedParameterJdbcTemplate` như một bean để inject.

Trong **Spring Framework thông thường** hoặc khi muốn cấu hình tường minh, có thể tạo bean:

```java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@Configuration
public class JdbcConfig {
    @Bean
    NamedParameterJdbcTemplate namedParameterJdbcTemplate(
            DataSource dataSource
    ) {
        return new NamedParameterJdbcTemplate(dataSource);
    }
}
```

Nếu Spring Boot đã tạo bean tương đương, **không cần tạo trùng**. Khi dự án có nhiều `DataSource`, cần xác định rõ bean nguồn nào được inject, dùng `@Qualifier`/cấu hình transaction manager tương ứng thay vì dựa vào lựa chọn mơ hồ.

Một repository nhận bean qua constructor:

```java
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class CatalogRepository {
    private final NamedParameterJdbcTemplate namedJdbc;

    public CatalogRepository(NamedParameterJdbcTemplate namedJdbc) {
        this.namedJdbc = namedJdbc;
    }
}
```

**Lợi ích kiến trúc:** repository không cần tự gọi `DriverManager.getConnection()`, không giữ một `Connection` dùng chung mọi request và không quản lý vòng đời connection pool. Spring JDBC lấy/trả connection theo `DataSource` và hợp đồng transaction hiện tại.

## 4. Chuẩn bị schema PostgreSQL cho các ví dụ

Dùng bảng sản phẩm theo tenant để minh họa tình huống truy vấn nhiều điều kiện và yêu cầu authorization. DDL sau thực hiện khi **chuẩn bị/migrate schema**, không nên chạy khi mỗi API request bắt đầu.

```sql
CREATE TABLE catalog_product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id UUID NOT NULL,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(180) NOT NULL,
    category_id BIGINT,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_catalog_tenant_sku UNIQUE (tenant_id, sku),
    CONSTRAINT uq_catalog_tenant_id UNIQUE (tenant_id, id)
);

CREATE INDEX idx_catalog_tenant_active_id
    ON catalog_product (tenant_id, active, id);

CREATE TABLE stock_reservation (
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),

    PRIMARY KEY (tenant_id, request_id),
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES catalog_product (tenant_id, id)
);
```

Các điểm quan trọng:

- `tenant_id` đi kèm đa số câu SQL. **Nó phải đến từ ngữ cảnh đã được authorization**, không chỉ từ query string do client tự chọn.
- `(tenant_id, sku)` là unique để tránh trùng SKU trong cùng tenant.
- `price NUMERIC` được Java ánh xạ qua `BigDecimal`; không đổi qua `double` cho tiền.
- `stock >= 0` được bảo vệ bằng SQL condition khi trừ hàng và `CHECK`.
- Bảng `stock_reservation` cho phép kiểm thử transaction nhiều bước và ràng buộc khóa ngoại ghép.
- `BIGINT GENERATED ... AS IDENTITY`, `UUID`, `TIMESTAMPTZ` là cú pháp/kiểu cần điều chỉnh nếu dùng MySQL, SQL Server hoặc Oracle.

Nạp dữ liệu trong môi trường thử nghiệm:

```sql
INSERT INTO catalog_product (
    tenant_id, sku, name, category_id, price, stock, active
) VALUES
    ('11111111-1111-1111-1111-111111111111',
     'JDBC-101', 'Nhập môn JDBC', 10, 129000.00, 20, TRUE),
    ('11111111-1111-1111-1111-111111111111',
     'JDBC-201', 'JDBC nâng cao', 10, 259000.00, 8, TRUE),
    ('22222222-2222-2222-2222-222222222222',
     'JDBC-101', 'JDBC của tenant B', 20, 199000.00, 5, TRUE);
```

Cùng `sku=JDBC-101` có thể xuất hiện ở hai tenant. Mọi ví dụ DAO cần bảo toàn phạm vi đã được cấp quyền; câu query theo SKU mà quên `tenant_id` là một lỗi nghiêm trọng.

## 5. Ba cách cấp named parameters

`NamedParameterJdbcTemplate` chấp nhận các cấu trúc tham số khác nhau. Nên chọn cách phù hợp với độ phức tạp, yêu cầu `NULL`/kiểu SQL và nguồn dữ liệu.

### 5.1. `Map<String, ?>`: ngắn gọn khi ít tham số, không có NULL

```java
Map<String, Object> params = Map.of(
    "tenantId", tenantId,
    "active", true
);

String sql = """
    SELECT COUNT(*)
    FROM catalog_product
    WHERE tenant_id = :tenantId
      AND active = :active
    """;

Integer count = namedJdbc.queryForObject(
    sql, params, Integer.class
);
```

`Map.of()` tạo Map bất biến và **không cho phép khóa hoặc giá trị `null`**. Với các giá trị tùy chọn, dùng `MapSqlParameterSource` hoặc một Map có thể chứa null, đồng thời khai báo SQL type nếu driver cần.

Không tạo một Map duy nhất mutable dùng chung mọi request và ghi đè `tenantId` theo thread. Tham số phải thuộc đúng phạm vi lời gọi; repository có thể là singleton, nhưng Map tham số nên được tạo mới cho mỗi truy vấn.

### 5.2. `MapSqlParameterSource`: rõ ràng và kiểm soát kiểu SQL

```java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("tenantId", tenantId)
    .addValue("sku", sku)
    .addValue("categoryId", optionalCategoryId, Types.BIGINT)
    .addValue("minPrice", new BigDecimal("100000.00"), Types.NUMERIC);
```

Đây là `SqlParameterSource`, cho phép khai báo tên, giá trị, SQL type, đôi khi thêm tên type phù hợp driver. `Types.BIGINT` và `Types.NUMERIC` là hằng của `java.sql.Types`.

Khi `optionalCategoryId == null`, thông tin kiểu có thể hữu ích để driver đặt tham số `NULL` đúng ngữ cảnh. Với PostgreSQL, việc ép kiểu/bind null ở một số biểu thức có thể phụ thuộc vào cách viết SQL; khai báo type rõ ràng giúp giảm sự mơ hồ nhưng **không thay thế SQL đúng kiểu**.

Lưu ý về `NULL` trong SQL:

```sql
-- KHÔNG dùng điều kiện này để tìm các giá trị NULL:
WHERE category_id = :categoryId

-- Nếu mục tiêu là các hàng category_id IS NULL:
WHERE category_id IS NULL
```

Bind giá trị `null` không làm toán tử `=` trở thành `IS NULL`. Nếu cần bộ lọc tùy chọn, có thể tạo hai câu SQL cố định hoặc viết điều kiện phù hợp và kiểm thử trên DBMS thật.

### 5.3. `BeanPropertySqlParameterSource`: bind từ JavaBean có getter

Spring có thể lấy tên tham số từ thuộc tính JavaBean:

```java
import java.math.BigDecimal;
import org.springframework.jdbc.core.namedparam.BeanPropertySqlParameterSource;

public final class PriceChange {
    private final long productId;
    private final BigDecimal newPrice;

    public PriceChange(long productId, BigDecimal newPrice) {
        this.productId = productId;
        this.newPrice = newPrice;
    }

    public long getProductId() {
        return productId;
    }

    public BigDecimal getNewPrice() {
        return newPrice;
    }
}

// Ở caller:
PriceChange change =
    new PriceChange(10L, new BigDecimal("149000.00"));

BeanPropertySqlParameterSource params =
    new BeanPropertySqlParameterSource(change);
```

SQL có thể dùng `:productId` và `:newPrice`. Tên tham số cần trùng tên property JavaBean (theo getter `getProductId()`, `getNewPrice()`), **không trùng tên field bất kỳ nếu không có accessor phù hợp**.

`BeanPropertySqlParameterSource` hữu ích với nhiều thuộc tính cùng tên trên DTO. Tuy nhiên, với đối tượng phức tạp, nested property hoặc Java record, phải xác nhận cách Spring nhận diện property trên phiên bản đang dùng; để tài liệu dễ kiểm chứng, ví dụ này dùng **JavaBean có getter chuẩn**. Nếu SQL cần kiểu đặc biệt hoặc tên khác property, `MapSqlParameterSource` thường minh bạch hơn.

### Bảng lựa chọn nhanh

| Cách cấp tham số | Phù hợp | Cần lưu ý |
|---|---|---|
| `Map.of(...)` | Ít giá trị không null | Không cho phép null; giữ nguyên tên key |
| `MapSqlParameterSource` | SQL phức tạp, NULL, cần SQL type | Viết tường minh mỗi tham số |
| `BeanPropertySqlParameterSource` | DTO/JavaBean với getter đúng tên | Tên property phải tương ứng tham số; xem vấn đề null/type |
| `SqlParameterSource[]` | Nhiều bộ tham số cùng một câu SQL | Dùng với `batchUpdate()` và kiểm tra update counts |

## 6. Repository thực tế: `RowMapper`, truy vấn và cập nhật

Đoạn code dưới đây minh họa một repository JDBC dùng `NamedParameterJdbcTemplate`; nó **không tự thao tác trực tiếp với connection**. Spring xử lý lifecycle JDBC resource và exception translation.

### 6.1. Định nghĩa record kết quả và `RowMapper`

```java
package edu.jdbc.catalog;

import java.math.BigDecimal;

public record ProductRow(
    long id,
    String sku,
    String name,
    BigDecimal price,
    int stock,
    boolean active
) {}
```

`RowMapper<T>` chuyển từng hàng `ResultSet` thành đối tượng Java:

```java
import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.jdbc.core.RowMapper;

private static final RowMapper<ProductRow> PRODUCT_MAPPER =
    (ResultSet rs, int rowNum) -> new ProductRow(
        rs.getLong("id"),
        rs.getString("sku"),
        rs.getString("name"),
        rs.getBigDecimal("price"),
        rs.getInt("stock"),
        rs.getBoolean("active")
    );
```

`rowNum` bắt đầu từ 0 theo hợp đồng Spring `RowMapper`; còn **chỉ số cột trong JDBC bắt đầu từ 1** nếu dùng `rs.getXxx(int columnIndex)`. Ở ví dụ này truy cập bằng **column label** để tránh phụ thuộc vào thứ tự `SELECT`.

Cột `price` là `NUMERIC NOT NULL` nên `BigDecimal` phù hợp. Với cột số có thể NULL, `rs.getInt()` trả `0` cho NULL và cần `rs.wasNull()` hoặc getter object thích hợp. Đừng làm mất phân biệt giữa giá trị 0 hợp lệ và SQL NULL.

### 6.2. Repository có query theo tenant và pagination

```java
package edu.jdbc.catalog;

import java.math.BigDecimal;
import java.sql.Types;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class CatalogRepository {
    private final NamedParameterJdbcTemplate namedJdbc;

    private static final RowMapper<ProductRow> PRODUCT_MAPPER =
        (rs, rowNum) -> new ProductRow(
            rs.getLong("id"),
            rs.getString("sku"),
            rs.getString("name"),
            rs.getBigDecimal("price"),
            rs.getInt("stock"),
            rs.getBoolean("active")
        );

    public CatalogRepository(NamedParameterJdbcTemplate namedJdbc) {
        this.namedJdbc = namedJdbc;
    }

    public List<ProductRow> listActive(
            UUID authorizedTenantId,
            long afterId,
            int pageSize
    ) {
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException(
                "pageSize must be between 1 and 100"
            );
        }

        String sql = """
            SELECT id, sku, name, price, stock, active
            FROM catalog_product
            WHERE tenant_id = :tenantId
              AND active = TRUE
              AND id > :afterId
            ORDER BY id
            LIMIT :pageSize
            """;

        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("tenantId", authorizedTenantId)
            .addValue("afterId", afterId, Types.BIGINT)
            .addValue("pageSize", pageSize, Types.INTEGER);

        return namedJdbc.query(sql, params, PRODUCT_MAPPER);
    }

    public Optional<ProductRow> findBySku(
            UUID authorizedTenantId,
            String sku
    ) {
        String sql = """
            SELECT id, sku, name, price, stock, active
            FROM catalog_product
            WHERE tenant_id = :tenantId
              AND sku = :sku
            """;

        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("tenantId", authorizedTenantId)
            .addValue("sku", sku);

        List<ProductRow> rows =
            namedJdbc.query(sql, params, PRODUCT_MAPPER);

        // UNIQUE(tenant_id, sku) bảo đảm tối đa một hàng.
        return rows.isEmpty()
            ? Optional.empty()
            : Optional.of(rows.get(0));
    }

    public int rename(
            UUID authorizedTenantId,
            long productId,
            String newName
    ) {
        String sql = """
            UPDATE catalog_product
            SET name = :newName
            WHERE tenant_id = :tenantId AND id = :productId
            """;

        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("newName", newName)
            .addValue("tenantId", authorizedTenantId)
            .addValue("productId", productId);

        return namedJdbc.update(sql, params);
    }
}
```

Từng phần:

- `namedJdbc.query(sql, params, PRODUCT_MAPPER)` thực thi SQL và trả `List<ProductRow>`; nó đọc tất cả các hàng được truy vấn theo mapper. Với tập kết quả quá lớn, hãy giới hạn `pageSize` hoặc dùng xử lý streaming/callback thích hợp.
- `findBySku()` dùng `Optional` để biểu thị không có bản ghi. Nó tránh việc coi truy vấn không có hàng là lỗi, nhưng **phải có unique constraint** để bảo đảm không có nhiều hàng.
- `update()` trả **số hàng bị ảnh hưởng**. Giá trị `0` có thể là không có bản ghi đúng tenant/ID, không nhất thiết là lỗi SQL; service quyết định xử lý nghiệp vụ.
- `tenant_id` được bind qua `:tenantId` ở mọi câu SQL. Tuy vậy, **repository không tự xác thực quyền**; tầng gọi phải cung cấp tenant đã qua kiểm tra authorization.
- Việc đóng `ResultSet`, `PreparedStatement` và trả `Connection` được Spring JDBC xử lý; repository không giữ những tài nguyên đó thành field sống lâu.

### Tại sao `NamedParameterJdbcTemplate` vẫn gọi được JDBC thật?

Spring giữ nguyên SQL như một câu lệnh cần database thực thi, chuyển các tham số có tên thành các vị trí bind phù hợp và gọi qua JDBC template. Các lỗi `SQLException` từ database sẽ được Spring dịch thành `DataAccessException`; transaction đang hoạt động được quản lý qua Spring transaction manager/DataSource liên quan.

Không phải mọi lỗi đều biến thành câu trả lời “không có dữ liệu”. Ví dụ thiếu bảng, sai cột, mất kết nối hay vi phạm ràng buộc phải đi qua nhánh lỗi phù hợp, không nên catch mọi `DataAccessException` rồi trả danh sách rỗng.

## 7. `queryForObject()` và các tình huống 0, 1, nhiều hàng

`queryForObject()` phù hợp khi hợp đồng truy vấn **đòi đúng một hàng**.

Ví dụ đếm sản phẩm:

```java
String sql = """
    SELECT COUNT(*)
    FROM catalog_product
    WHERE tenant_id = :tenantId
      AND active = TRUE
    """;

Long activeCount = namedJdbc.queryForObject(
    sql,
    new MapSqlParameterSource()
        .addValue("tenantId", authorizedTenantId),
    Long.class
);
```

`COUNT(*)` thường trả một hàng với số đếm, nên đây là trường hợp thích hợp. Chọn `Long.class` tránh giới hạn `int` khi tổng số bản ghi lớn.

Với truy vấn tìm theo khóa:

```java
String sql = """
    SELECT id
    FROM catalog_product
    WHERE tenant_id = :tenantId AND sku = :sku
    """;

Long id = namedJdbc.queryForObject(
    sql,
    new MapSqlParameterSource()
        .addValue("tenantId", authorizedTenantId)
        .addValue("sku", sku),
    Long.class
);
```

Nếu không có sản phẩm, Spring có thể ném `EmptyResultDataAccessException`. Nếu có nhiều hàng trong trường hợp hàm đòi một hàng, thường là `IncorrectResultSizeDataAccessException`. Khi DAO muốn biểu thị **không có hàng là bình thường**, dùng `query()` + `Optional` hoặc catch cụ thể `EmptyResultDataAccessException` rồi trả `Optional.empty()`.

**Không catch `DataAccessException` chung để trả `Optional.empty()`.** Như vậy sẽ biến lỗi mạng, lỗi quyền hoặc SQL syntax thành “không có sản phẩm”, làm che lỗi production.

### `queryForList()` dùng cho một cột hoặc nhiều cột

```java
List<String> skus = namedJdbc.queryForList(
    """
    SELECT sku
    FROM catalog_product
    WHERE tenant_id = :tenantId AND active = TRUE
    ORDER BY sku
    """,
    Map.of("tenantId", authorizedTenantId),
    String.class
);
```

Đây là overload trả danh sách **một cột được convert sang `String`**. Nếu cần nhiều cột kiểu rõ ràng, ưu tiên `query(..., RowMapper<T>)`. Một overload khác có thể trả `List<Map<String,Object>>` cho nhiều cột, nhưng kiểu dữ liệu của map khó kiểm soát hơn DTO và dễ mang trường không cần thiết lên API.

## 8. Tham số trùng tên và biểu thức tìm kiếm

Một tên tham số được dùng nhiều lần trong SQL:

```java
String sql = """
    SELECT id, sku, name, price, stock, active
    FROM catalog_product
    WHERE tenant_id = :tenantId
      AND (sku = :term OR name = :term)
    ORDER BY id
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("tenantId", authorizedTenantId)
    .addValue("term", term);

List<ProductRow> matches =
    namedJdbc.query(sql, params, PRODUCT_MAPPER);
```

`:term` dùng hai lần, chỉ cần `addValue("term", term)` một lần. Điều này giảm nguy cơ truyền hai giá trị không nhất quán vào cùng một điều kiện nghiệp vụ.

Nếu người dùng tìm kiếm gần đúng theo `LIKE`, bind mẫu:

```java
String sql = """
    SELECT id, name
    FROM catalog_product
    WHERE tenant_id = :tenantId
      AND name ILIKE :pattern
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("tenantId", authorizedTenantId)
    .addValue("pattern", "%" + searchText + "%");
```

`ILIKE` là toán tử PostgreSQL. Bind mẫu `:pattern` giúp tránh SQL injection do ghép raw SQL, nhưng ký tự `%` và `_` trong `searchText` vẫn mang **ngữ nghĩa wildcard của LIKE**. Nếu nghiệp vụ muốn tìm đúng chuỗi literal chứa các ký tự này, phải escape wildcard theo DBMS và khai báo `ESCAPE` phù hợp; SQL parameterization **không tự escape wildcard**.

Cũng cần giới hạn độ dài `searchText`, kết quả tối đa và tốc độ tìm kiếm. Một `ILIKE '%term%'` trên bảng lớn có thể làm scan tốn kém nếu không có chiến lược index phù hợp, dù câu SQL đã an toàn về tham số.

## 9. Tập giá trị trong `IN (:ids)`

Đây là một lợi ích thực dụng của `NamedParameterJdbcTemplate`: bind danh sách ID cho một `IN` mà không cần tự nối các dấu `?`.

```java
List<Long> ids = List.of(10L, 12L, 15L);

String sql = """
    SELECT id, sku, name, price, stock, active
    FROM catalog_product
    WHERE tenant_id = :tenantId
      AND id IN (:ids)
    ORDER BY id
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("tenantId", authorizedTenantId)
    .addValue("ids", ids);

List<ProductRow> rows =
    namedJdbc.query(sql, params, PRODUCT_MAPPER);
```

Spring mở rộng collection này thành một số vị trí bind tương ứng, về mặt ý tưởng:

```sql
-- Dạng JDBC sau khi mở rộng cho ba ID (minh họa):
WHERE tenant_id = ? AND id IN (?, ?, ?)
```

Giá trị từng ID vẫn được bind qua `PreparedStatement`; **không nối `ids.toString()` vào SQL**.

### 9.1. Danh sách rỗng phải có hợp đồng riêng

Không nên giả định `IN (:ids)` với `ids = List.of()` sẽ thành SQL hợp lệ trên mọi DBMS/driver. Một danh sách rỗng có thể dẫn tới `IN ()` hoặc hành vi không tương thích.

Nếu ý nghĩa nghiệp vụ là “chọn từ tập ID rỗng thì không có kết quả”, trả ngay:

```java
public List<ProductRow> findByIds(
        UUID authorizedTenantId,
        List<Long> ids
) {
    if (ids.isEmpty()) {
        return List.of();
    }
    if (ids.size() > 500) {
        throw new IllegalArgumentException(
            "Too many IDs in a single request"
        );
    }

    String sql = """
        SELECT id, sku, name, price, stock, active
        FROM catalog_product
        WHERE tenant_id = :tenantId
          AND id IN (:ids)
        ORDER BY id
        """;

    MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("tenantId", authorizedTenantId)
        .addValue("ids", ids);

    return namedJdbc.query(sql, params, PRODUCT_MAPPER);
}
```

Phương thức này có thể thêm vào `CatalogRepository` ở mục 6. Một số điểm cần lưu ý:

- Mốc `500` chỉ là giới hạn ví dụ của ứng dụng; số tham số tối đa và hiệu năng tùy driver/DBMS.
- Danh sách ID quá lớn có thể làm SQL sau mở rộng rất dài và tạo áp lực lên kế hoạch thực thi. Có thể chia chunk, dùng bảng tạm/temporary staging hoặc cơ chế array/`ANY` đặc thù PostgreSQL sau khi đã đo.
- SQL `ORDER BY id` **không bảo đảm** thứ tự output giống thứ tự `ids` từ client; nếu API cần giữ nguyên thứ tự input, phải có bước sắp xếp lại trong Java hoặc SQL chuyên biệt.
- Nếu `ids` có trùng, `IN` không trả một hàng nhiều lần chỉ vì một ID xuất hiện hai lần.

### 9.2. Không tự “nhồi” danh sách vào một tham số dạng chuỗi

```java
// SAI: id IN ('10,12,15') không tương đương ba ID số.
params.addValue("ids", "10,12,15");
```

Một chuỗi chứa dấu phẩy là **một giá trị**, không phải collection ba giá trị. Dùng `Collection` hoặc mảng đối tượng theo hỗ trợ của Spring, hoặc một kỹ thuật SQL của DBMS nếu yêu cầu xử lý tập lớn.

## 10. `INSERT` và lấy khóa được database tạo

`NamedParameterJdbcTemplate.update()` trả số hàng bị ảnh hưởng, không tự trả ID generated. Khi bảng tạo khóa bằng identity, dùng `KeyHolder` cùng `update(...)` nếu driver/DBMS hỗ trợ generated keys.

Ví dụ PostgreSQL:

```java
import java.math.BigDecimal;
import java.sql.Types;
import java.util.UUID;

import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

public long insertProduct(
        UUID authorizedTenantId,
        String sku,
        String name,
        Long categoryId,
        BigDecimal price,
        int stock
) {
    if (price.signum() < 0 || stock < 0) {
        throw new IllegalArgumentException(
            "Price and stock must not be negative"
        );
    }

    String sql = """
        INSERT INTO catalog_product (
            tenant_id, sku, name, category_id, price, stock, active
        ) VALUES (
            :tenantId, :sku, :name, :categoryId, :price, :stock, TRUE
        )
        """;

    MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("tenantId", authorizedTenantId)
        .addValue("sku", sku)
        .addValue("name", name)
        .addValue("categoryId", categoryId, Types.BIGINT)
        .addValue("price", price, Types.NUMERIC)
        .addValue("stock", stock, Types.INTEGER);

    KeyHolder keys = new GeneratedKeyHolder();

    int inserted = namedJdbc.update(
        sql, params, keys, new String[] {"id"}
    );

    if (inserted != 1) {
        throw new IllegalStateException(
            "Expected exactly one inserted product"
        );
    }

    Number id = keys.getKey();
    if (id == null) {
        throw new IllegalStateException(
            "Database did not return generated ID"
        );
    }
    return id.longValue();
}
```

Phương thức này đặt bên trong `CatalogRepository`. Các trường/kiểu tương ứng với bảng ở mục 4; `new String[]{"id"}` yêu cầu driver lấy khóa của **cột id**.

**Đừng suy ra từ `inserted == 1` rằng ID bằng 1.** `update count` biểu thị số hàng bị ảnh hưởng; `KeyHolder` giữ giá trị khóa được database trả về. Nếu driver không hỗ trợ hoặc trả nhiều cột/hàng keys, cần xử lý theo hợp đồng của driver thay vì giả định `getKey()` luôn có một giá trị.

Với PostgreSQL, một phương án khác là dùng `INSERT ... RETURNING id` và ánh xạ kết quả theo dialect. Nhưng câu SQL `RETURNING` không phải cú pháp phổ quát của mọi DBMS; `KeyHolder` phù hợp khi muốn dùng API generated keys mà driver hỗ trợ.

**Về retry:** nếu commit gặp lỗi mạng, có thể database đã tạo hàng dù Java chưa nhận kết quả chắc chắn. Không retry `INSERT` với SKU/ID mới một cách mù quáng; thiết kế unique key/idempotency key và tra cứu đối soát trước khi gửi lại.

## 11. `UPDATE`, `DELETE` và update counts

`namedJdbc.update(sql, params)` trả `int`: số hàng JDBC/driver báo đã bị ảnh hưởng. Ví dụ:

```java
String sql = """
    UPDATE catalog_product
    SET price = :price
    WHERE tenant_id = :tenantId
      AND id = :productId
    """;

int updated = namedJdbc.update(
    sql,
    new MapSqlParameterSource()
        .addValue("price", new BigDecimal("179000.00"))
        .addValue("tenantId", authorizedTenantId)
        .addValue("productId", productId)
);
```

- `updated == 1`: DB/driver báo một hàng được cập nhật.
- `updated == 0`: không có hàng phù hợp hoặc hành vi affected-row tùy DBMS; **không nhất thiết là lỗi SQL**.
- `updated > 1`: với `WHERE id = ...` và khóa chính, đây có thể là dấu hiệu sai hợp đồng nếu query không còn chỉ định duy nhất.
- `DataAccessException`: lỗi SQL/driver được Spring dịch, chẳng hạn vi phạm constraint hoặc mất kết nối.

**Không xóa tenant predicate khi UPDATE/DELETE**, vì truy vấn không có filter đúng phạm vi có thể gây truy cập chéo. `NamedParameterJdbcTemplate` chỉ bind giá trị; nó không tự thêm `tenant_id`.

Để phân biệt kết quả nghiệp vụ, service nên có quy tắc rõ: “đúng một sản phẩm phải được cập nhật” khác với “cập nhật nếu tồn tại”. Không catch lỗi SQL rồi trả `0`, vì như vậy che đi sự cố database.

## 12. Batch nhiều bộ tham số có tên

Khi cùng một câu SQL áp dụng cho nhiều sản phẩm, có thể dùng `batchUpdate()` với mảng `SqlParameterSource`. Ví dụ cập nhật giá một số sản phẩm:

```java
import java.math.BigDecimal;
import java.sql.Statement;
import java.util.List;
import java.util.UUID;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

record PriceUpdate(long productId, BigDecimal newPrice) {}

public int[] updatePrices(
        UUID authorizedTenantId,
        List<PriceUpdate> changes
) {
    if (changes.isEmpty()) {
        return new int[0];
    }

    SqlParameterSource[] batch =
        new SqlParameterSource[changes.size()];

    for (int i = 0; i < changes.size(); i++) {
        PriceUpdate change = changes.get(i);

        if (change.newPrice().signum() < 0) {
            throw new IllegalArgumentException("Negative price");
        }

        batch[i] = new MapSqlParameterSource()
            .addValue("tenantId", authorizedTenantId)
            .addValue("productId", change.productId())
            .addValue("newPrice", change.newPrice());
    }

    String sql = """
        UPDATE catalog_product
        SET price = :newPrice
        WHERE tenant_id = :tenantId
          AND id = :productId
        """;

    return namedJdbc.batchUpdate(sql, batch);
}
```

Phương thức này đặt bên trong repository. Spring thực hiện batch JDBC với các bộ giá trị theo thứ tự tương ứng. Mảng `int[]` cần được diễn giải theo ngữ nghĩa **JDBC update counts**:

| Giá trị `counts[i]` | Ý nghĩa |
|---|---|
| `0` | Lệnh chạy nhưng driver báo không có hàng bị ảnh hưởng |
| `1` hoặc số dương | Số hàng driver báo bị ảnh hưởng |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Thành công nhưng không biết số hàng cụ thể |
| `Statement.EXECUTE_FAILED` (`-3`) | Driver báo thất bại cho một lệnh trong một số cách thực thi batch |

Không cộng `-2` hoặc `-3` như số hàng âm; nếu nghiệp vụ yêu cầu mỗi ID ảnh hưởng đúng một hàng thì `SUCCESS_NO_INFO` chưa đủ bằng chứng. Khi batch bị lỗi, Spring có thể ném một `DataAccessException` chứa/có liên quan `SQLException`/`BatchUpdateException` của driver. Hành vi driver **dừng hay tiếp tục sau lỗi**, counts từng phần và trạng thái transaction phải được kiểm thử trên DBMS/driver đang dùng.

**Batch không tự tạo một transaction nghiệp vụ nguyên tử.** Nếu cần “tất cả giá được cập nhật hoặc không cập nhật gì”, gọi repository từ một service `@Transactional` và kiểm tra kết quả trước khi commit. Nếu muốn partial success, thiết kế transaction cho từng chunk và checkpoint một cách tường minh.

### Dùng `BeanPropertySqlParameterSource` cho batch

Với các JavaBean có getter chuẩn, có thể tạo mảng tham số bằng helper của Spring:

```java
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSourceUtils;

List<PriceChange> changes = List.of(
    new PriceChange(10L, new BigDecimal("110000.00")),
    new PriceChange(20L, new BigDecimal("220000.00"))
);

SqlParameterSource[] sources =
    SqlParameterSourceUtils.createBatch(changes);

int[] counts = namedJdbc.batchUpdate(
    """
    UPDATE catalog_product
    SET price = :newPrice
    WHERE id = :productId
    """,
    sources
);
```

**Chỉ là ví dụ API trong môi trường test một tenant.** Câu SQL này cố ý minh họa property `:newPrice` và `:productId` của `PriceChange` ở mục 5, nhưng **chưa có tenant predicate**. Trong hệ thống multi-tenant thật phải bổ sung `tenant_id = :tenantId` và bảo đảm mỗi nguồn tham số mang tenant đã được authorization, hoặc dùng `MapSqlParameterSource` như phương thức `updatePrices()` phía trên.

Việc viết ví dụ ngắn không được làm mất giới hạn quyền truy cập trong code production. Đừng dùng tên property từ một client DTO chưa xác thực để tự quyết định tenant của từng item.

## 13. Transaction với Spring: không tự `commit()` trong repository

Một lợi ích của việc dùng Spring JDBC đúng cách là repository có thể tham gia transaction do Spring quản lý qua **`DataSource` và transaction manager tương ứng**.

Ví dụ nghiệp vụ: trừ kho và ghi reservation **phải cùng thành công**.

### 13.1. Hai repository dùng cùng `NamedParameterJdbcTemplate`

Bổ sung phương thức trong `CatalogRepository`:

```java
public int decreaseStock(
        UUID authorizedTenantId,
        long productId,
        int quantity
) {
    String sql = """
        UPDATE catalog_product
        SET stock = stock - :quantity
        WHERE tenant_id = :tenantId
          AND id = :productId
          AND stock >= :quantity
        """;

    return namedJdbc.update(
        sql,
        new MapSqlParameterSource()
            .addValue("tenantId", authorizedTenantId)
            .addValue("productId", productId)
            .addValue("quantity", quantity)
    );
}
```

Repository lưu reservation:

```java
package edu.jdbc.catalog;

import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class ReservationRepository {
    private final NamedParameterJdbcTemplate namedJdbc;

    public ReservationRepository(
            NamedParameterJdbcTemplate namedJdbc
    ) {
        this.namedJdbc = namedJdbc;
    }

    public void insert(
            UUID authorizedTenantId,
            UUID requestId,
            long productId,
            int quantity
    ) {
        int rows = namedJdbc.update(
            """
            INSERT INTO stock_reservation (
                tenant_id, request_id, product_id, quantity
            ) VALUES (
                :tenantId, :requestId, :productId, :quantity
            )
            """,
            new MapSqlParameterSource()
                .addValue("tenantId", authorizedTenantId)
                .addValue("requestId", requestId)
                .addValue("productId", productId)
                .addValue("quantity", quantity)
        );

        if (rows != 1) {
            throw new IllegalStateException(
                "Reservation insert must affect one row"
            );
        }
    }
}
```

### 13.2. Service là chủ sở hữu ranh giới giao dịch

```java
package edu.jdbc.catalog;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class ReservationService {
    private final CatalogRepository products;
    private final ReservationRepository reservations;

    public ReservationService(
            CatalogRepository products,
            ReservationRepository reservations
    ) {
        this.products = products;
        this.reservations = reservations;
    }

    @Transactional
    public void reserve(
            UUID authorizedTenantId,
            UUID requestId,
            long productId,
            int quantity
    ) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be positive"
            );
        }

        int affected =
            products.decreaseStock(
                authorizedTenantId, productId, quantity
            );

        if (affected != 1) {
            throw new IllegalStateException(
                "Product not found or insufficient stock"
            );
        }

        reservations.insert(
            authorizedTenantId, requestId, productId, quantity
        );
    }
}
```

Với **Spring transaction manager được cấu hình trên cùng `DataSource`**, một lời gọi đi qua Spring proxy tới method `@Transactional` sẽ mở/tham gia transaction, các lời gọi repository dùng `NamedParameterJdbcTemplate` tham gia cùng connection transaction-bound, và Spring commit/rollback theo hợp đồng.

Khi insert reservation bị lỗi vì trùng `PRIMARY KEY (tenant_id, request_id)`:

1. Lệnh trừ kho có thể đã chạy trong transaction.
2. PostgreSQL ném lỗi trùng khóa.
3. Spring dịch SQLException thành một `DataAccessException` như `DuplicateKeyException` theo khả năng nhận diện driver.
4. Exception không được nuốt sẽ đi qua transaction interceptor.
5. Spring rollback **cả lần trừ kho và lần insert reservation**.

Đây là **local transaction JDBC**, không phải hai commit độc lập. `@Transactional` không có nghĩa “tự bảo đảm idempotency”: nếu commit thành công nhưng phản hồi mạng bị mất, client vẫn cần request ID ổn định và đối soát trước retry.

### Các bẫy của `@Transactional`

- **Phải có transaction manager phù hợp** và lời gọi đi qua cơ chế proxy hoặc aspect được cấu hình. Tự gọi `this.reserve(...)` từ method khác trong cùng bean thường **không đi qua proxy** ở chế độ proxy mặc định.
- **Mặc định** Spring rollback khi method thoát bằng `RuntimeException` hoặc `Error`; **checked exception** thường không gây rollback mặc định nếu không cấu hình `rollbackFor` hoặc quy tắc tương ứng. `DataAccessException` là unchecked nên phù hợp đường xử lý chuẩn này.
- Đừng catch `DataAccessException` rồi trả thành công hoặc nuốt exception khi transaction cần rollback. Nếu cần catch để trả lỗi nghiệp vụ, hãy ném exception phù hợp hoặc chủ động đánh dấu rollback theo cơ chế Spring.
- Không tạo `new JdbcTemplate(otherDataSource)` hoặc `dataSource.getConnection()` riêng để tự `commit()` giữa một transaction đang được quản lý. Điều đó có thể phá tính nguyên tử.
- `@Transactional(readOnly = true)` có thể hỗ trợ tối ưu/ý định read-only, nhưng **không phải cơ chế authorization** và không phải bảo đảm DB chặn mọi câu ghi trên tất cả driver.
- Với nhiều `DataSource`/transaction manager, phải chỉ rõ transaction manager và routing để tránh một repository tham gia transaction A trong khi repository khác dùng connection B.
- Không giữ transaction mở qua HTTP call chậm, upload lớn hoặc thao tác đợi người dùng.

### Cơ chế kết nối khi đang có transaction

`NamedParameterJdbcTemplate` dựa trên `JdbcTemplate`, sử dụng cách lấy connection tương thích Spring transaction (thông qua `DataSourceUtils` ở phía Spring). Vì vậy repository **không cần** nhận đối tượng `Connection` thủ công khi hoạt động trong một Spring-managed transaction.

Nếu viết phần JDBC thuần trong cùng service, cần dùng cách lấy connection **tham gia transaction của Spring** (hoặc `JdbcTemplate.execute(ConnectionCallback)`/cơ chế tương đương), không tự `getConnection()` một cách độc lập rồi kỳ vọng tự động gắn vào transaction hiện tại.

## 14. Exception translation: `DataAccessException` không đồng nghĩa dữ liệu không tồn tại

Spring JDBC chuyển nhiều `SQLException` thành các subclass thuộc họ `org.springframework.dao.DataAccessException`. Điều này giúp tầng service ít phụ thuộc vào mã lỗi vendor.

| Tình huống | Exception Spring thường gặp | Hành động |
|---|---|---|
| `queryForObject()` không có hàng | `EmptyResultDataAccessException` | Có thể chuyển thành `Optional.empty()` nếu nghiệp vụ chấp nhận |
| Truy vấn cần một hàng nhưng có nhiều | `IncorrectResultSizeDataAccessException` | Điều tra dữ liệu/query; đừng tùy tiện chọn hàng đầu |
| Trùng khóa unique/PK | `DuplicateKeyException` | Xử lý conflict/idempotency có chủ đích |
| Vi phạm constraint khác | `DataIntegrityViolationException` | Sửa payload hoặc mapping lỗi nghiệp vụ |
| SQL sai cú pháp | `BadSqlGrammarException` | Sửa SQL/schema; không retry ngay |
| Lỗi kết nối/tài nguyên | Các `DataAccessException` khác tùy translation | Quan sát DB/pool/network; không retry write mù |

**Không đảm bảo mọi DBMS/driver đều dịch một SQLState thành đúng cùng một subclass.** Cần test trên DBMS đích; khi cần chẩn đoán, xem `cause` hoặc `SQLException` lồng bên dưới để biết SQLState/vendor code, đồng thời tránh phụ thuộc thông điệp lỗi thay đổi theo phiên bản.

Ví dụ bắt lỗi có chủ đích:

```java
try {
    reservations.insert(
        authorizedTenantId, requestId, productId, quantity
    );
} catch (DuplicateKeyException duplicate) {
    // Trùng request ID: áp dụng quy trình idempotency/đối soát.
    // Nếu đang trong @Transactional và muốn rollback,
    // phải ném exception hoặc đánh dấu rollback phù hợp.
    throw duplicate;
}
```

Không làm:

```java
try {
    repository.rename(tenantId, productId, newName);
} catch (DataAccessException ignored) {
    return 0; // SAI: lỗi database bị biến thành "không có bản ghi".
}
```

Nếu nghiệp vụ cho phép cập nhật 0 hàng thì xử lý **giá trị trả về từ update()**; nếu JDBC/Spring báo lỗi, giữ đường lỗi riêng.

### Thông tin SQLException gốc vẫn quan trọng

Khi điều tra lỗi:

- `SQLException.getSQLState()`: mã phân loại SQL nếu driver cung cấp.
- `getErrorCode()`: mã vendor.
- `getNextException()`: chuỗi lỗi SQL liên kết.
- `getCause()` và `getSuppressed()`: nguyên nhân và lỗi cleanup.

Spring có thể giữ SQLException như root cause trong `DataAccessException`. Dùng logging có cấu trúc, giới hạn kích thước và tránh đưa password hoặc giá trị nhạy cảm vào log. Chỉ ghi message không đủ để phân tích lỗi rollback/connection.

## 15. Bảo mật: chỉ **giá trị** mới được bind qua tên

Giả sử API cho phép sắp xếp theo giá hoặc tên. Dòng này **không** làm điều ứng dụng mong muốn:

```java
String sql = """
    SELECT id, sku, name, price, stock, active
    FROM catalog_product
    WHERE tenant_id = :tenantId
    ORDER BY :column
    """;

params.addValue("column", requestedColumn);
```

`:column` được bind như **một giá trị**, không phải định danh cột SQL. Tùy DBMS, câu trên có thể lỗi hoặc sắp xếp theo hằng giá trị mà không có tác dụng mong muốn. **`PreparedStatement` và `NamedParameterJdbcTemplate` không cho phép bind tên bảng, tên cột, toán tử hoặc cả đoạn `ORDER BY` tùy ý.**

### 15.1. Allowlist cho sort

```java
String orderBy = switch (requestedSort) {
    case "nameAsc" -> "name ASC, id ASC";
    case "priceAsc" -> "price ASC, id ASC";
    case "priceDesc" -> "price DESC, id ASC";
    default -> "id ASC";
};

String sql = """
    SELECT id, sku, name, price, stock, active
    FROM catalog_product
    WHERE tenant_id = :tenantId AND active = TRUE
    ORDER BY
    """ + orderBy + " LIMIT :pageSize";

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("tenantId", authorizedTenantId)
    .addValue("pageSize", pageSize);
```

`requestedSort` chỉ được map sang các **chuỗi SQL cố định do developer kiểm soát**; không nối trực tiếp input client. `id ASC` ở cuối giúp tạo thứ tự ổn định khi nhiều sản phẩm có cùng tên/giá, nhưng phân trang keyset cho sort theo giá/tên cần cursor và điều kiện tuple tương ứng; không thể tái sử dụng `WHERE id > :afterId` với mọi thứ tự sắp xếp.

### 15.2. Phạm vi tenant cần xác thực trước khi truy vấn

Tên `:tenantId` chỉ làm tham số dễ đọc; **nó không chứng minh tenant đã được phép truy cập**. Phải kiểm tra authentication/authorization và truyền tenant đã được xác nhận. Với hệ thống nhiều tenant, có thể bổ sung PostgreSQL RLS, composite foreign key và database privileges để giảm hậu quả khi query mới quên tenant predicate.

Tương tự, một repository update có `WHERE id = :productId` nhưng không có tenant condition là vấn đề bảo mật dù SQL có tham số hóa đầy đủ.

### 15.3. Không đưa nguyên SQL của người dùng vào repository

Không chấp nhận một chuỗi `WHERE` hoặc tên bảng do client gửi rồi nối vào SQL. Nếu UI cung cấp các filter tùy chọn, xây truy vấn từ **các nhánh SQL cố định/allowlist**, còn giá trị mỗi filter vẫn bind bằng `MapSqlParameterSource`.

`NamedParameterJdbcTemplate` làm giảm rủi ro injection **ở vị trí dữ liệu được bind**; nó không tự xử lý mọi điểm nối SQL động.

## 16. Hiệu năng và giới hạn khi dùng tên tham số

Phần chuyển đổi `:name` sang JDBC placeholder có chi phí ở phía Spring, nhưng trong nhiều ứng dụng thời gian database/network lớn hơn đáng kể. Tuy nhiên **không nên khẳng định mọi workload đều nhanh/chậm tương đương**; cần đo trong môi trường đại diện.

Các câu hỏi quan trọng hơn khi tối ưu:

1. **Số query:** có N+1 query vì gọi một query cho mỗi item không? Có thể dùng `IN (:ids)` hoặc batch không?
2. **Số hàng:** có giới hạn qua `WHERE`, keyset/`LIMIT` hoặc pagination không?
3. **Số cột:** có đang `SELECT *` rồi bỏ hầu hết kết quả không?
4. **Index:** câu `WHERE tenant_id = :tenantId AND id > :afterId` có index phù hợp không?
5. **Transaction:** Spring-managed transaction có giữ connection qua thao tác mạng bên ngoài không?
6. **Pool:** `DataSource` có pool được cấu hình phù hợp không, có timeout/connection leak không?
7. **Batch:** số item/chunk vừa phải? Có xử lý `SUCCESS_NO_INFO` và rollback khi lỗi không?
8. **Dynamic collection:** `IN (:ids)` với hàng nghìn ID có vượt giới hạn tham số hay làm query plan kém không?
9. **Memory:** `query()` trả cả `List`; đọc hàng triệu hàng có cần streaming/callback thay vì gom hết vào heap không?
10. **Metric:** đã đo latency p50/p95, SQL time, GC, connection occupancy và network bytes chưa?

### So sánh bằng integration benchmark thay vì phỏng đoán

Có thể chạy cùng truy vấn/driver/data qua `JdbcTemplate` và `NamedParameterJdbcTemplate`, với cùng số hàng và mapper:

```java
// Positional parameters:
List<ProductRow> a = jdbcTemplate.query(
    """
    SELECT id, sku, name, price, stock, active
    FROM catalog_product
    WHERE tenant_id = ? AND active = ?
    ORDER BY id LIMIT ?
    """,
    PRODUCT_MAPPER,
    tenantId, true, 50
);

// Named parameters:
List<ProductRow> b = namedJdbc.query(
    """
    SELECT id, sku, name, price, stock, active
    FROM catalog_product
    WHERE tenant_id = :tenantId AND active = :active
    ORDER BY id LIMIT :limit
    """,
    Map.of(
        "tenantId", tenantId,
        "active", true,
        "limit", 50
    ),
    PRODUCT_MAPPER
);
```

Đoạn mã là phép so sánh minh họa, giả định `jdbcTemplate`, `namedJdbc`, `PRODUCT_MAPPER` và `tenantId` đã được tạo trong scope test. Nếu dùng nó để benchmark, cần warm-up, nhiều lần chạy, thay đổi thứ tự đo, kiểm tra dữ liệu trả về giống nhau và không để test bị chi phối bởi cache ngoài ý muốn.

**Không làm benchmark bằng cách đổi đồng thời SQL, driver, pool và kích thước dữ liệu.** Nên tách chi phí parse/bind ở ứng dụng khỏi chi phí database thực thi SQL.

## 17. Kiểm thử tích hợp `NamedParameterJdbcTemplate` trên database thật

Mock `NamedParameterJdbcTemplate` giúp test logic điều phối của service, nhưng **không xác minh** câu SQL sau chuyển đổi thực thi đúng trên PostgreSQL, việc bind UUID/`NUMERIC`, ràng buộc PK/FK hoặc transaction rollback.

Một integration test có thể dùng PostgreSQL thật trong Testcontainers để xác nhận:

- Named params được ánh xạ đúng, kể cả tham số lặp và `IN (:ids)`.
- `NULL` có kiểu SQL thích hợp, kết quả `RowMapper` đúng.
- `update()` trả count như mong đợi.
- Generated keys qua `KeyHolder` phù hợp driver.
- `@Transactional` rollback toàn use case khi insert reservation bị duplicate key.
- Tenant A không đọc hay sửa được bản ghi tenant B bằng DAO đã có predicate.
- Một tên sort không nằm trong allowlist không được đưa vào SQL.

### 17.1. JUnit + PostgreSQLContainer + Spring JDBC (ví dụ độc lập)

Đoạn test sau dùng **JUnit Jupiter và Testcontainers 1.x**, tự tạo `PGSimpleDataSource` và `NamedParameterJdbcTemplate`. Khi chạy trong dự án thật cần các dependency `spring-jdbc`, `postgresql`, `testcontainers-postgresql` và JUnit tương thích, cùng container runtime.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;

class NamedParametersPostgresTest {

    @Test
    void bindsNamedParametersAndEnforcesConstraints() {
        try (PostgreSQLContainer<?> postgres =
                 new PostgreSQLContainer<>("postgres:16-alpine")
                     .withDatabaseName("jdbc_it")
                     .withUsername("it_user")
                     .withPassword("it_password")) {

            postgres.start();

            PGSimpleDataSource source = new PGSimpleDataSource();
            source.setServerNames(
                new String[] { postgres.getHost() }
            );
            source.setPortNumbers(
                new int[] { postgres.getMappedPort(5432) }
            );
            source.setDatabaseName(postgres.getDatabaseName());
            source.setUser(postgres.getUsername());
            source.setPassword(postgres.getPassword());

            DataSource dataSource = source;
            NamedParameterJdbcTemplate named =
                new NamedParameterJdbcTemplate(dataSource);

            named.getJdbcTemplate().execute("""
                CREATE TABLE test_items (
                    tenant_id UUID NOT NULL,
                    item_id BIGINT NOT NULL,
                    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
                    PRIMARY KEY (tenant_id, item_id)
                )
                """);

            UUID tenant = UUID.randomUUID();
            MapSqlParameterSource first = new MapSqlParameterSource()
                .addValue("tenantId", tenant)
                .addValue("itemId", 1L)
                .addValue("price", new BigDecimal("19.50"));

            int inserted = named.update(
                """
                INSERT INTO test_items (tenant_id, item_id, price)
                VALUES (:tenantId, :itemId, :price)
                """,
                first
            );

            assertEquals(1, inserted);

            Long count = named.queryForObject(
                """
                SELECT COUNT(*)
                FROM test_items
                WHERE tenant_id = :tenantId
                  AND item_id IN (:ids)
                """,
                new MapSqlParameterSource()
                    .addValue("tenantId", tenant)
                    .addValue("ids", List.of(1L, 2L)),
                Long.class
            );

            assertEquals(1L, count.longValue());

            assertThrows(
                DuplicateKeyException.class,
                () -> named.update(
                    """
                    INSERT INTO test_items (
                        tenant_id, item_id, price
                    ) VALUES (
                        :tenantId, :itemId, :price
                    )
                    """,
                    first
                )
            );

            Long otherTenantCount = named.queryForObject(
                """
                SELECT COUNT(*)
                FROM test_items
                WHERE tenant_id = :tenantId
                """,
                Map.of("tenantId", UUID.randomUUID()),
                Long.class
            );

            assertEquals(0L, otherTenantCount.longValue());
        }
    }
}
```

**Giới hạn của test này:** nó xác nhận named binding, collection expansion, PK conflict và tenant predicate trên PostgreSQL thật. Nó **chưa** kiểm tra cơ chế `@Transactional` vì không có Spring application context hoặc transaction manager được cấu hình; phần tiếp theo đề xuất cách test transaction riêng. Không dùng một lần test thành công để khẳng định mọi câu SQL/driver đã được kiểm chứng.

Trong production dự án thường dùng version khác của Testcontainers; **Testcontainers 2.x có thể thay package/module**, vì vậy hãy pin và dùng import theo bộ dependency thực tế thay vì cố trộn 1.x/2.x.

### 17.2. Kiểm thử rollback của Spring transaction manager

Có thể dùng `TransactionTemplate` để kiểm tra transaction mà không cần dựng toàn bộ HTTP application. Với cùng `DataSource` đã cấu hình, khởi tạo `DataSourceTransactionManager` và `TransactionTemplate`, rồi thực hiện hai câu SQL có chủ đích:

```java
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

TransactionTemplate tx = new TransactionTemplate(
    new DataSourceTransactionManager(dataSource)
);

// Điều kiện fixture: có hàng test_items(tenant_id, item_id=1, price=19.50).
assertThrows(DuplicateKeyException.class, () ->
    tx.executeWithoutResult(status -> {
        named.update(
            """
            UPDATE test_items
            SET price = :newPrice
            WHERE tenant_id = :tenantId AND item_id = :itemId
            """,
            new MapSqlParameterSource()
                .addValue("tenantId", tenant)
                .addValue("itemId", 1L)
                .addValue("newPrice", new BigDecimal("99.00"))
        );

        // INSERT trùng PK để buộc rollback cả UPDATE phía trên.
        named.update(
            """
            INSERT INTO test_items (tenant_id, item_id, price)
            VALUES (:tenantId, :itemId, :newPrice)
            """,
            new MapSqlParameterSource()
                .addValue("tenantId", tenant)
                .addValue("itemId", 1L)
                .addValue("newPrice", new BigDecimal("99.00"))
        );
    })
);
```

Sau exception, dùng `named.queryForObject(...)` **ngoài transaction đã lỗi** và xác nhận giá vẫn là `19.50`. Phần trên là đoạn test thêm vào method có sẵn biến `named`, `dataSource`, `tenant`, không phải đoạn Java tự chạy độc lập.

Với `@Transactional`, test phải khởi tạo Spring context và **gọi service qua Spring proxy**. Không tạo `new ReservationService(...)` bằng tay rồi mong annotation tự kích hoạt transaction. Nếu integration test có `@Transactional` ở chính test method, có thể che việc service đã commit sai phạm vi; hãy chủ động kiểm chứng **dữ liệu sau khi transaction thật sự kết thúc**.

## 18. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `:tenantId` trong SQL nhưng Map ghi `tenantID` | Không tìm được tham số đúng tên | Thống nhất tên, integration test các nhánh |
| `Map.of("x", null)` | Ném lỗi từ Map factory trước khi SQL chạy | Dùng `MapSqlParameterSource` và kiểu SQL khi cần |
| Viết `WHERE category_id = :nullValue` để tìm `NULL` | SQL `= NULL` không có ý nghĩa bằng `IS NULL` | Dùng SQL `IS NULL` hoặc điều kiện tùy chọn rõ |
| Dùng `ORDER BY :column` | Bind thành giá trị chứ không thành identifier | Allowlist chuỗi SQL cố định |
| Nối `:ids` thành chuỗi `"1,2,3"` | Không phải collection ba phần tử | Bind `List<Long>`/collection thực |
| Không xử lý danh sách rỗng trong `IN (:ids)` | SQL có thể không hợp lệ | Trả kết quả rỗng hoặc chọn câu SQL khác |
| `queryForObject()` để lấy bản ghi tùy chọn | Không có hàng gây exception | Dùng `query()` + `Optional` hoặc bắt đúng exception |
| Dùng một `Map` mutable chung cho mọi request | Dữ liệu tenant/tham số chồng chéo | Tạo nguồn tham số theo từng invocation |
| Quên điều kiện tenant của `UPDATE`/`DELETE` | Nguy cơ ghi dữ liệu tenant khác | Bind tenant đã qua authorization, thêm RLS/constraint khi cần |
| Catch mọi `DataAccessException` rồi trả `null` | Lỗi DB bị che thành “không thấy dữ liệu” | Phân biệt error và empty result |
| Dùng `@Transactional` nhưng tự gọi method cùng bean | Proxy có thể không chạy interceptor | Gọi qua Spring-managed bean/transaction mechanism đúng |
| Repository tự `commit()` khi service dùng `@Transactional` | Phá transaction chung | Để transaction manager sở hữu commit/rollback |
| Cho `batchUpdate()` tự đồng nghĩa all-or-nothing | Có thể commit một phần nếu không có transaction phù hợp | Bao transaction và xử lý update counts |
| Lấy `KeyHolder.getKey()` mà không xét driver | Có thể thiếu/multiple keys | Kiểm thử generated key trên DBMS thật |
| Đưa `SELECT *` lên mapper card | Truyền thừa cột/LOB và tăng gắn kết schema | Projection chỉ chọn cột cần dùng |
| Dựa vào H2 để chứng minh cú pháp PostgreSQL | SQLState/dialect/behavior có thể khác | Integration test bằng PostgreSQL thật |

## 19. Bài thực hành

1. **Đổi tham số vị trí sang có tên:** viết lại một `JdbcTemplate.query()` có năm dấu `?` thành `NamedParameterJdbcTemplate.query()` với `MapSqlParameterSource`. Thay đổi thứ tự điều kiện và chứng minh kết quả không bị lệch tham số.
2. **Tạo project:** thêm Spring JDBC starter và driver phù hợp, cấu hình `DataSource` bằng biến môi trường; inject `NamedParameterJdbcTemplate` vào repository. Giải thích vì sao nó vẫn dùng JDBC thật.
3. **CRUD theo tenant:** tạo bảng `catalog_product` và cài `listActive()`, `findBySku()`, `rename()`. Kiểm tra tenant A không đọc được SKU của B khi ID/SKU trùng nhau.
4. **`NULL` và kiểu SQL:** cho `category_id` rỗng, dùng `MapSqlParameterSource.addValue(..., Types.BIGINT)`; thử tìm hàng `IS NULL` và so với `= :categoryId`.
5. **`queryForObject()`:** truy vấn `COUNT(*)`, truy vấn một ID có tồn tại và một ID không có; ghi lại exception hoặc kết quả `Optional` từ mỗi cách.
6. **Tên lặp:** viết `WHERE sku = :term OR name = :term`; bind `term` một lần và kiểm tra hai nhánh đều dùng cùng giá trị.
7. **Collection:** thử `id IN (:ids)` với 3 ID, một ID không tồn tại và danh sách rỗng. Tự đặt giới hạn số ID mỗi request và giải thích vì sao cần giới hạn.
8. **Generated keys:** dùng `KeyHolder` để chèn sản phẩm; kiểm tra id được trả từ PostgreSQL, không nhầm với update count.
9. **Batch:** dùng `batchUpdate()` sửa giá 3 sản phẩm, trong đó một ID không tồn tại; diễn giải `0`, `1`, `SUCCESS_NO_INFO`. Thử lỗi unique/CHECK và rollback theo transaction.
10. **JavaBean binding:** dùng `BeanPropertySqlParameterSource` với `PriceChange` có getter; cố ý đổi `:newPrice` thành `:price` để xem hành vi thiếu property.
11. **Transaction nhiều repository:** gọi `ReservationService.reserve()` trong Spring context, tạo duplicate request ID ở bước ghi reservation; xác minh stock được rollback. Lặp lại test bằng cách tự `new ReservationService(...)` để giải thích vai trò proxy.
12. **SQL injection:** thiết kế tham số sort có allowlist `nameAsc`/`priceAsc`; chứng minh input tuỳ ý không bị nối trực tiếp vào SQL. Thử chuỗi chứa dấu nháy trong `:name` và kiểm tra bind vẫn hoạt động.
13. **Integration test:** chạy PostgreSQL thật trong container, kiểm tra SQLState/constraint, collection expansion, khóa sinh và transaction rollback. Không dùng riêng mock để kết luận driver đã hỗ trợ.

### Checklist trước khi đưa vào production

- [ ] Đã xác định đúng `DataSource`/driver và transaction manager cho `NamedParameterJdbcTemplate`.
- [ ] Repository nhận `NamedParameterJdbcTemplate` qua DI thay vì mở connection độc lập không kiểm soát.
- [ ] Mọi giá trị từ input được bind bằng tên; không ghép trực tiếp chuỗi SQL từ dữ liệu người dùng.
- [ ] Tên cột/bảng/sort động đều đến từ allowlist/registry đáng tin cậy.
- [ ] Tên `:parameter` khớp key/property, không có typo hoặc nguồn tham số chia sẻ mutable.
- [ ] `NULL`, kiểu SQL, UUID, `BigDecimal` và xử lý kết quả rỗng được kiểm thử.
- [ ] `IN (:ids)` có nhánh xử lý danh sách rỗng và giới hạn số lượng phần tử.
- [ ] Query chỉ chọn cột/hàng cần dùng, có phân trang và thứ tự ổn định.
- [ ] `queryForObject()` chỉ dùng khi hợp đồng thật sự đòi đúng một hàng.
- [ ] `update()` và `batchUpdate()` được diễn giải đúng, không nhầm update count với generated key.
- [ ] Các thao tác nhiều repository được bao trong transaction Spring đúng scope/proxy.
- [ ] Không nuốt `DataAccessException`; phân biệt lỗi DB với “không có bản ghi”.
- [ ] Tenant/authorization được kiểm tra trước query; `:tenantId` không thay thế authorization.
- [ ] Có integration test trên DBMS/driver production-like, bao gồm lỗi, rollback và concurrent access quan trọng.
- [ ] Log SQL/exception có giới hạn và không lộ password, dữ liệu nhạy cảm.

**Tiêu chí hoàn thành:** người học hiểu `NamedParameterJdbcTemplate` là lớp tiện ích Spring JDBC chuyển tham số có tên thành các bind vị trí cho `PreparedStatement`; biết sử dụng `Map`, `MapSqlParameterSource` và `BeanPropertySqlParameterSource`, đọc dữ liệu bằng `RowMapper`, xử lý `queryForObject()`, `IN (:ids)`, CRUD, `KeyHolder` và batch; phối hợp repository trong transaction `@Transactional` đúng cách, phân biệt `DataAccessException` với không có dữ liệu, dùng allowlist cho SQL động và kiểm chứng các hành vi bằng integration test trên database thật.

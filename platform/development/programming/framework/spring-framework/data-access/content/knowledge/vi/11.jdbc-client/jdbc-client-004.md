# JdbcClient: Liên kết tham số vị trí hoặc tham số có tên

> **Chủ đề:** Spring Framework → data-access → **JdbcClient**. Bài học giải thích cách sử dụng hai kiểu parameter binding trong cùng API fluent: **tham số vị trí** viết bằng dấu `?` và **tham số có tên** viết dưới dạng `:name`. Người học sẽ biết cách chọn đúng overload `param`/`params`/`paramSource`, xác định thứ tự bind, khai báo kiểu SQL/NULL, truyền danh sách vào `IN`, hiểu vai trò của JdbcTemplate và NamedParameterJdbcTemplate bên dưới, và thực hành với Java 21, Spring Boot, Spring JDBC, H2.

## 1. Vấn đề: một câu SQL, hai cách khai báo giá trị

Giả sử một hệ thống bán sách cần truy vấn sản phẩm theo **loại hàng** và **giá tối thiểu**. Với JDBC, SQL nên tách cấu trúc truy vấn khỏi dữ liệu nhận từ ứng dụng để tránh nối chuỗi nguy hiểm.

**Cách A — tham số vị trí:**

~~~sql
SELECT id, sku, category, price, stock
FROM inventory_item
WHERE category = ?
  AND price >= ?
ORDER BY id;
~~~

~~~java
// Fragment: jdbcClient là org.springframework.jdbc.core.simple.JdbcClient.
// Chỉ minh họa cú pháp; project chạy hoàn chỉnh ở phần 10.
List<Item> items = jdbcClient.sql("""
        SELECT id, sku, category, price, stock
        FROM inventory_item
        WHERE category = ? AND price >= ?
        ORDER BY id
        """)
    .param("BOOK")
    .param(new BigDecimal("80.00"))
    .query(ITEM_MAPPER)
    .list();
~~~

**Cách B — tham số có tên:**

~~~sql
SELECT id, sku, category, price, stock
FROM inventory_item
WHERE category = :category
  AND price >= :minPrice
ORDER BY id;
~~~

~~~java
List<Item> items = jdbcClient.sql("""
        SELECT id, sku, category, price, stock
        FROM inventory_item
        WHERE category = :category AND price >= :minPrice
        ORDER BY id
        """)
    .param("minPrice", new BigDecimal("80.00"))
    .param("category", "BOOK")
    .query(ITEM_MAPPER)
    .list();
~~~

Hai câu truy vấn diễn tả **cùng một điều kiện dữ liệu**. Với cách A, `param(value)` đăng ký các giá trị **theo thứ tự dấu `?`** trong SQL. Với cách B, `param("name", value)` đăng ký giá trị **theo tên**; thứ tự gọi `param` có thể khác thứ tự tên xuất hiện trong SQL.

`JdbcClient` xuất hiện từ **Spring Framework 6.1**. Nó cung cấp một **facade fluent** cho các thao tác JDBC query/update thông dụng, thống nhất hai kiểu tham số mà trước đây lập trình viên thường dùng tách biệt qua `JdbcTemplate` và `NamedParameterJdbcTemplate`. Hai framework/template ở dưới vẫn đảm nhiệm công việc thực thi, không có một kiểu JDBC placeholder thứ ba.

### Mục tiêu của bài

Sau bài này, bạn có thể:

1. Đọc một câu SQL và xác định nên dùng `param(Object)`, `param(int, Object)` hay `param(String, Object)`.
2. Dùng `params(Object...)`/`params(List<?>)` cho vị trí và `params(Map<String, ?>)` cho tên một cách chính xác.
3. Dùng `paramSource(Object)`/`paramSource(SqlParameterSource)` khi có DTO, record hoặc dữ liệu có khai báo SQL type.
4. Hiểu lặp tên `:discount` và danh sách `IN (:categories)` biến thành bao nhiêu dấu `?`.
5. Biết vì sao không trộn named với indexed parameters trong **cùng một câu lệnh**.
6. Kiểm soát kiểu `NULL`, số hàng cập nhật, SQL injection và vòng đời JDBC.

## 2. Nhìn vào luồng xử lý bên dưới JdbcClient

~~~mermaid
flowchart TD
    A["Repository gọi jdbcClient.sql(sql)"] --> B["JdbcClient.StatementSpec"]
    B --> C{"SQL và tham số thuộc loại nào?"}
    C -- "Vị trí ?" --> D["JdbcTemplate / JDBC indexed parameters"]
    C -- "Có tên :name" --> E["NamedParameterJdbcTemplate"]
    E --> F["Parse SQL, đổi tên thành ?, mở rộng IN nếu cần"]
    F --> D
    D --> G["PreparedStatement trên Connection do Spring quản lý"]
    G --> H["Bind giá trị + SQL type"]
    H --> I["Thực thi SQL qua JDBC driver / DBMS"]
    I --> J["update count hoặc ResultSet → query mapping"]
~~~

**Điểm cần nhớ:** Có tên hay không chỉ khác nhau ở **cách diễn đạt và chuẩn bị tham số trước khi JDBC thực thi**. Cuối cùng, cả hai cách phổ biến đều đi qua PreparedStatement, với placeholder `?` ở tầng JDBC.

- **`JdbcClient.sql(sql)`** tạo một mô tả thao tác, chưa chạy SQL ngay.
- Các lời gọi **`param`, `params`, `paramSource`** bổ sung giá trị và metadata.
- **`query(...)`** chọn cách đọc/mapping kết quả; `list()`, `single()`, `optional()` (tùy QuerySpec) thực hiện thao tác khi cần kết quả.
- **`update()`** thực thi DML và trả **số hàng tác động**.
- Spring chịu trách nhiệm lấy/release Connection qua DataSource, tạo và dọn Statement, dịch `SQLException`, tham gia transaction do tầng trên quản lý.

Đừng nhầm giai đoạn **binding** với **commit**: dùng `JdbcClient` không tự tạo ranh giới transaction cho toàn bộ use case nhiều truy vấn. Transaction vẫn cần được tổ chức ở application service khi nghiệp vụ đòi hỏi.

## 3. API quan trọng: `JdbcClient.StatementSpec`

`jdbcClient.sql("...")` trả về một `JdbcClient.StatementSpec`. Những overload cốt lõi trong Spring Framework 6.1/6.2:

| API | Kiểu bind | Ý nghĩa |
| --- | --- | --- |
| `param(Object value)` | Vị trí ngầm định | Thêm giá trị tiếp theo theo thứ tự dấu `?` |
| `param(int jdbcIndex, Object value)` | Vị trí tường minh | Đặt giá trị ở vị trí JDBC cụ thể, bắt đầu từ **1** |
| `param(int jdbcIndex, Object value, int sqlType)` | Vị trí + SQL type | Ví dụ bind `NULL` kiểu `VARCHAR` tại vị trí 2 |
| `params(Object... values)` | Nhiều vị trí | Bind các giá trị positional theo thứ tự |
| `params(List<?> values)` | Nhiều vị trí | Mỗi phần tử List là một giá trị cho một dấu `?` |
| `param(String name, Object value)` | Có tên | Gắn value vào placeholder `:name` |
| `param(String name, Object value, int sqlType)` | Có tên + SQL type | Chỉ rõ kiểu JDBC nếu cần |
| `params(Map<String, ?> paramMap)` | Nhiều tên | Thêm tập key-value cho named placeholders |
| `paramSource(Object namedParamObject)` | Nguồn tên | Lấy property/record component hoặc Map từ object |
| `paramSource(SqlParameterSource source)` | Nguồn tên + type | Dùng `MapSqlParameterSource` và metadata SQL types |

Các method đó trả lại StatementSpec để có thể chain. `JdbcClient` bản thân có thể được tiêm như một bean dùng lại; ngược lại, mỗi lần gọi `sql(...)` nên tạo một specification phù hợp với **một thao tác cụ thể**, không giữ mutable StatementSpec dùng chung như biến toàn cục giữa các request.

**Nhìn chữ ký để phân biệt:** `param("category", "BOOK")` có **hai đối số** và đối số đầu là `String`, nên là named parameter. `param(2, "BOOK")` cũng có **hai đối số** nhưng đối số đầu là `int`, nên là **vị trí JDBC thứ 2**. Hai overload gần giống nhau về hình dạng nhưng hoàn toàn khác nghĩa.

## 4. Tham số vị trí: `?` và cách bind theo thứ tự

### 4.1. `param(value)`: dùng cho 1–vài tham số

~~~java
int changed = jdbcClient.sql(
        "UPDATE inventory_item SET stock = ? WHERE id = ?"
    )
    .param(9)
    .param(2L)
    .update();
~~~

SQL có `?` thứ nhất cho `stock` và `?` thứ hai cho `id`. Do đó:

| JDBC index | Cột/điều kiện SQL | Giá trị |
| --- | --- | --- |
| 1 | `SET stock = ?` | `9` |
| 2 | `WHERE id = ?` | `2L` |

Nếu gọi `.param(2L).param(9)` mà các kiểu cho phép, câu SQL vẫn có thể chạy nhưng ghi giá trị sai. API positional **không nhìn tên biến Java** để tự sửa thứ tự.

### 4.2. `params(Object...)`: đăng ký nhiều giá trị một lần

~~~java
int changed = jdbcClient.sql(
        "UPDATE inventory_item SET stock = ? WHERE id = ?"
    )
    .params(9, 2L)
    .update();
~~~

Về ý nghĩa, hai lần `param(value)` ở trên tương đương một lần `params(9, 2L)`. Với SQL có nhiều placeholder, hãy giữ chúng cạnh nhau theo đúng thứ tự thay vì lặp các giá trị không có chú thích ở nhiều nơi.

### 4.3. `params(List<?>)`: vẫn là **nhiều vị trí**, không phải tự động `IN`

~~~java
List<Object> values = List.of("BOOK", new BigDecimal("80.00"));

List<String> skus = jdbcClient.sql("""
        SELECT sku FROM inventory_item
        WHERE category = ? AND price >= ?
        ORDER BY id
        """)
    .params(values)
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

**Một List có hai phần tử sẽ bind vào hai dấu `?` theo thứ tự.** Không nhầm method này với `.param("ids", List.of(...))` của named parameters, vì cách sau có thể làm mở rộng danh sách bên trong SQL `IN (:ids)`.

Đặc biệt, `Map.of`/`List.of` không chấp nhận giá trị `null`; khi cần bind NULL hãy dùng API typed param hoặc collection phù hợp với nhu cầu.

### 4.4. `param(jdbcIndex, value)`: đăng ký vị trí tường minh

Ở JDBC, vị trí **bắt đầu từ 1**, không phải 0:

~~~java
int changed = jdbcClient.sql(
        "UPDATE inventory_item SET stock = stock + ? WHERE id = ?"
    )
    .param(2, 2L)  // Vị trí 2: id
    .param(1, 3)   // Vị trí 1: lượng tăng tồn kho
    .update();
~~~

Dù các method được gọi theo thứ tự **2 rồi 1**, kết quả bind vào PreparedStatement vẫn đúng: `?` thứ nhất nhận 3, `?` thứ hai nhận 2L. Đây là sự khác biệt giữa **thứ tự gọi method** và **vị trí explicit được chỉ định**. Chỉ dùng cách này khi làm rõ intent; với SQL rất ngắn, `params(3, 2L)` có thể gọn hơn.

**Không dùng `param(0, ...)`.** Chỉ số 0 không phải vị trí JDBC hợp lệ. Nếu dùng explicit index, đảm bảo mọi dấu `?` bắt buộc đều có giá trị, và không bind thừa vị trí không tồn tại.

## 5. Tham số có tên: `:name`

### 5.1. Cách viết

~~~java
List<String> skus = jdbcClient.sql("""
        SELECT sku FROM inventory_item
        WHERE category = :category
          AND price >= :minPrice
        ORDER BY id
        """)
    .param("minPrice", new BigDecimal("80.00"))
    .param("category", "BOOK")
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

Tên `category` và `minPrice` trong lời gọi Java **không chứa dấu `:`**. Giá trị được tra theo tên, không theo thứ tự `param(...)`. Mô hình này dễ bảo trì hơn khi có nhiều điều kiện hoặc câu SQL dài.

### 5.2. Spring chuyển named parameter sang `?`

Với SQL:

~~~sql
UPDATE inventory_item
SET price = price - :discount
WHERE id = :id AND price >= :discount;
~~~

Và:

~~~java
jdbcClient.sql(sql)
    .param("id", 1L)
    .param("discount", new BigDecimal("20.00"))
    .update();
~~~

Bộ xử lý named parameters thay cả hai lần `:discount` và một lần `:id` thành dấu `?` theo **thứ tự xuất hiện trong SQL**:

~~~sql
UPDATE inventory_item
SET price = price - ?
WHERE id = ? AND price >= ?;
~~~

| Vị trí JDBC | Tên ban đầu | Giá trị |
| --- | --- | --- |
| 1 | `discount` | `20.00` |
| 2 | `id` | `1L` |
| 3 | `discount` | `20.00` |

Có **2 tên duy nhất nhưng 3 vị trí JDBC**. Spring phải bind `discount` vào cả vị trí 1 lẫn 3. Đây là một lợi ích của named parameter khi một value được dùng nhiều lần: lập trình viên chỉ khai báo **một key**.

### 5.3. Đừng coi named binding là thay thế văn bản SQL

`NamedParameterJdbcTemplate` dùng parser để phân biệt placeholder và phần SQL thuộc literal/comment. Framework không lấy tên rồi ghép giá trị thành SQL, ví dụ **không** chuyển `:category` thành raw `'BOOK'` bằng String.replace. Thay vào đó, SQL JDBC cuối cùng có dấu `?`, còn value và SQL type được bind riêng. Các câu SQL chứa dấu hai chấm trong literal, comment hoặc cú pháp như PostgreSQL `::` cần được xử lý đúng theo parser/driver, không nên tự viết regex replace.

Named parameters trong Spring JDBC tương tự về hình thức với JPA/JPQL `:name`, nhưng **không phải cùng API/parser**. Bài này đề cập `JdbcClient` và Spring JDBC.

## 6. `params(Map<String, ?>)`, `paramSource(Object)` và `SqlParameterSource`

### 6.1. Truyền Map nhiều tên

~~~java
Map<String, ?> values = Map.of(
    "category", "BOOK",
    "minPrice", new BigDecimal("80.00")
);

List<String> skus = jdbcClient.sql("""
        SELECT sku FROM inventory_item
        WHERE category = :category AND price >= :minPrice
        ORDER BY id
        """)
    .params(values)
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

Dù Map lưu key theo thứ tự nào, Spring vẫn bind theo vị trí placeholder xuất hiện trong SQL. `params(Map)` dành cho **named** parameters, còn `params(List)` hoặc `params(Object...)` dành cho **positional** parameters.

### 6.2. `paramSource(Object)` từ record

Giả sử một record biểu diễn điều kiện lọc:

~~~java
public record PriceFilter(String category, BigDecimal minPrice) {}
~~~

Có thể dùng:

~~~java
PriceFilter filter = new PriceFilter(
    "BOOK", new BigDecimal("80.00")
);

long count = jdbcClient.sql("""
        SELECT COUNT(*) FROM inventory_item
        WHERE category = :category AND price >= :minPrice
        """)
    .paramSource(filter)
    .query(Long.class)
    .single();
~~~

Trong Spring JDBC 6.1+, cơ chế property source của JdbcClient có thể lấy **record components** như `category`, `minPrice`. Đây là lựa chọn hữu ích nếu application đã có object đầu vào với property names khớp named placeholders. Tên record component phải phù hợp; một object bất kỳ không tự được biến thành mọi tham số nếu field/property không truy cập được.

`paramSource(Object)` chỉ **đọc giá trị**, không bắt bạn dùng entity/JPA hoặc đưa đối tượng miền xuống lớp SQL. Nên đặt trách nhiệm SQL trong Repository/DAO và dùng DTO/query object khi cần.

### 6.3. `paramSource(SqlParameterSource)` với SQL type

`MapSqlParameterSource` triển khai `SqlParameterSource`, cho phép gắn `java.sql.Types` cùng giá trị:

~~~java
MapSqlParameterSource source = new MapSqlParameterSource()
    .addValue("id", 2L, Types.BIGINT)
    .addValue("note", null, Types.VARCHAR);

int updated = jdbcClient.sql(
        "UPDATE inventory_item SET note = :note WHERE id = :id"
    )
    .paramSource(source)
    .update();
~~~

Đây là cách rõ ràng khi nhiều named parameters cần SQL type riêng hoặc có giá trị SQL `NULL`. Với một NULL duy nhất, method `param("note", null, Types.VARCHAR)` thường ngắn hơn.

**Không làm:** `Map.of("note", null)`, vì `Map.of` ném lỗi với giá trị null. Cũng không đồng nhất “thiếu key `note`” với “key `note` tồn tại và có value null”: hai trạng thái đó khác nhau khi Spring chuẩn bị binding.

## 7. Danh sách `IN (:categories)` và sự khác biệt quan trọng

Named parameter hỗ trợ cung cấp một Collection cho placeholder trong điều kiện `IN`:

~~~java
List<String> categories = List.of("BOOK", "DEVICE");

List<String> skus = jdbcClient.sql("""
        SELECT sku FROM inventory_item
        WHERE category IN (:categories)
          AND price >= :minPrice
        ORDER BY id
        """)
    .param("categories", categories)
    .param("minPrice", new BigDecimal("80.00"))
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

Vì `categories` có hai phần tử, phần điều kiện được mở rộng về SQL JDBC tương đương:

~~~sql
WHERE category IN (?, ?)
  AND price >= ?
~~~

Ba vị trí cuối cùng nhận lần lượt `"BOOK"`, `"DEVICE"`, `80.00`. Một **named placeholder** chứa list có thể tạo **nhiều dấu `?`**. Đây là khác biệt so với `.params(List.of("BOOK", "DEVICE"))` dùng cho SQL positional có sẵn hai dấu `?`; phương thức `params(List)` không tự viết lại chuỗi SQL.

### Danh sách rỗng là quyết định của nghiệp vụ

`IN ()` không hợp lệ ở nhiều SQL dialect. Nếu một bộ lọc categories rỗng có nghĩa “không loại hàng nào được chọn”, trả danh sách rỗng ngay:

~~~java
public List<String> findByCategories(List<String> categories) {
    if (categories.isEmpty()) {
        return List.of();
    }
    return jdbcClient.sql(
            "SELECT sku FROM inventory_item " +
            "WHERE category IN (:categories) ORDER BY id"
        )
        .param("categories", categories)
        .query((rs, rowNum) -> rs.getString("sku"))
        .list();
}
~~~

Không bỏ điều kiện `WHERE category IN (...)` một cách ngầm định khi danh sách rỗng, vì điều đó có thể trả **toàn bộ bảng** trái yêu cầu. Với list rất dài, chú ý giới hạn bind variables/SQL length của driver/DBMS, hiệu năng truy vấn và giới hạn các phần tử `IN`; cân nhắc chunking, temporary table hoặc giải pháp vendor-specific nếu có nhu cầu.

### Named list không phải SQL array

Một `List` trong `IN (:categories)` được Spring mở rộng thành nhiều placeholder; nó không đồng nghĩa truyền một SQL ARRAY duy nhất kiểu PostgreSQL `ANY(?)`. Nếu thật sự cần JDBC array, cần API và SQL type phù hợp với driver. Đừng trộn hai khái niệm.

## 8. Một câu SQL: chọn **một** cách bind, không trộn

`JdbcClient` là facade hỗ trợ **hai phong cách**, nhưng đó không có nghĩa mỗi câu SQL nên trộn cả hai. Phản ví dụ:

~~~java
// PHẢN VÍ DỤ: không trộn ? với :category trong cùng SQL.
jdbcClient.sql(
        "SELECT sku FROM inventory_item " +
        "WHERE category = :category AND price >= ?"
    )
    .param("category", "BOOK")
    .param(new BigDecimal("80.00"))
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

Cách viết này không có một ánh xạ named-to-indexed nhất quán cho cùng StatementSpec; tùy đường xử lý, Spring sẽ từ chối việc trộn named và truyền thống `?`. Chọn một phiên bản rõ ràng:

**Chỉ positional:**

~~~java
jdbcClient.sql(
        "SELECT sku FROM inventory_item " +
        "WHERE category = ? AND price >= ?"
    )
    .params("BOOK", new BigDecimal("80.00"))
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

**Chỉ named:**

~~~java
jdbcClient.sql(
        "SELECT sku FROM inventory_item " +
        "WHERE category = :category AND price >= :minPrice"
    )
    .params(Map.of(
        "category", "BOOK",
        "minPrice", new BigDecimal("80.00")
    ))
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

**Quy tắc thực hành:** Với một `jdbcClient.sql(...)`, chọn SQL dạng `?` **hoặc** SQL dạng `:name`, rồi dùng đúng các method bind tương ứng. Những lần gọi khác nhau trong **cùng Repository** có thể chọn các phong cách khác nhau; hạn chế chỉ áp dụng **trong một statement/query**.

## 9. Binding kiểu SQL, NULL, BigDecimal và dữ liệu đầu vào

### 9.1. Typed `NULL` cho vị trí

~~~java
int updated = jdbcClient.sql(
        "UPDATE inventory_item SET note = ? WHERE id = ?"
    )
    .param(1, null, Types.VARCHAR)
    .param(2, 1L, Types.BIGINT)
    .update();
~~~

Ở đây `Types.VARCHAR` hướng dẫn JDBC về kiểu SQL của NULL. Dù một số driver có thể suy luận kiểu, việc khai báo rõ thường hữu ích với cột nullable, procedure/driver đặc biệt hoặc dữ liệu không đủ thông tin.

### 9.2. Typed `NULL` cho tên

~~~java
int updated = jdbcClient.sql(
        "UPDATE inventory_item SET note = :note WHERE id = :id"
    )
    .param("note", null, Types.VARCHAR)
    .param("id", 1L, Types.BIGINT)
    .update();
~~~

Hai ví dụ tương đương về mục đích, nhưng cách chọn overload khác nhau. Không dùng `param("note", "null")` nếu muốn SQL NULL: chuỗi `"null"` là dữ liệu text, không phải giá trị NULL.

### 9.3. Giá và số tiền

Giá sản phẩm thường được mô hình bằng `BigDecimal` và cột SQL `DECIMAL(12,2)`:

~~~java
BigDecimal price = new BigDecimal("89.50");

jdbcClient.sql(
        "UPDATE inventory_item SET price = :price WHERE id = :id"
    )
    .param("price", price)
    .param("id", 2L)
    .update();
~~~

Hạn chế dùng `double` nếu phép tính cần đúng độ chính xác thập phân tiền tệ. Đối với `LocalDate`, `Instant`, `OffsetDateTime` hay SQL ARRAY/JSON/UUID, hãy kiểm tra mapping của driver và SQL type thực tế; named parameter không tự giải quyết timezone/vendor-specific data types.

### 9.4. Giá trị không đồng nghĩa identifier

Placeholder đại diện cho **giá trị dữ liệu**, không thể bind tên bảng/cột hoặc cú pháp `ORDER BY`:

~~~sql
-- KHÔNG dùng :tableName để đại diện cho identifier SQL:
SELECT * FROM :tableName;

-- :column chỉ là một giá trị, không phải tên cột để sắp xếp:
SELECT sku FROM inventory_item ORDER BY :column;
~~~

Nếu người dùng được chọn cột sort, dùng whitelist trong mã nguồn để tạo phần identifier SQL một cách có kiểm soát, còn giá trị điều kiện vẫn phải bind:

~~~java
String column = switch (sortBy) {
    case "price" -> "price";
    case "sku" -> "sku";
    default -> "id";
};

String sql =
    "SELECT id, sku FROM inventory_item " +
    "WHERE category = :category ORDER BY " + column;
~~~

Đây là fragment; `sortBy` đến từ input đã được kiểm soát bằng switch, **không** nối chuỗi bất kỳ từ request. Bind `:category` vẫn làm nhiệm vụ tránh SQL injection đối với **value**, không bảo vệ phần SQL bạn tự ghép không qua whitelist.

## 10. Ví dụ chạy hoàn chỉnh: Java 21, Spring Boot 3.3.5, JdbcClient, H2

Ví dụ dưới đây chứa cả hai phong cách trong **một Repository** để thấy mỗi statement có thể chọn cách bind phù hợp. Mọi class/file được đưa đủ để tự tạo project. Ứng dụng console không cần HTTP server, Docker hay PostgreSQL. Với Spring Boot 3.3.5 có một `DataSource` được cấu hình, `JdbcClient` có thể được auto-configure và inject trực tiếp.

### 10.1. Tổ chức file

~~~text
jdbc-client-binding/
├── build.gradle
└── src/main/
    ├── java/com/example/jdbcclient/
    │   ├── JdbcClientBindingApplication.java
    │   └── InventoryRepository.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
~~~

### 10.2. `build.gradle`

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

`spring-boot-starter-jdbc` mang Spring JDBC và connection pool cần thiết; H2 cung cấp database/driver trong bộ nhớ. `JdbcClient` thuộc package `org.springframework.jdbc.core.simple`. Ví dụ pin phiên bản để dễ tái hiện; khi xây hệ thống mới hãy chọn bộ phiên bản Spring Boot còn được hỗ trợ và kiểm tra compatibility.

### 10.3. `src/main/resources/application.properties`

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:client_binding;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

### 10.4. `src/main/resources/schema.sql`

~~~sql
CREATE TABLE inventory_item (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    category VARCHAR(30) NOT NULL,
    price DECIMAL(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    note VARCHAR(100)
);
~~~

### 10.5. `src/main/resources/data.sql`

~~~sql
INSERT INTO inventory_item (id, sku, category, price, stock, note)
VALUES (1, 'JAVA-17', 'BOOK', 120.00, 5, 'first');

INSERT INTO inventory_item (id, sku, category, price, stock, note)
VALUES (2, 'SPRING-CORE', 'BOOK', 89.50, 3, 'second');

INSERT INTO inventory_item (id, sku, category, price, stock, note)
VALUES (3, 'MOUSE', 'DEVICE', 40.00, 8, NULL);
~~~

### 10.6. Repository: `InventoryRepository.java`

~~~java
package com.example.jdbcclient;

import java.math.BigDecimal;
import java.sql.Types;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryRepository {

    public record Item(
        long id, String sku, String category,
        BigDecimal price, int stock
    ) {}

    public record PriceFilter(String category, BigDecimal minPrice) {}

    private static final RowMapper<Item> ITEM_MAPPER =
        (rs, rowNum) -> new Item(
            rs.getLong("id"),
            rs.getString("sku"),
            rs.getString("category"),
            rs.getBigDecimal("price"),
            rs.getInt("stock")
        );

    private final JdbcClient jdbc;

    public InventoryRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    // Positional implicit binding: hai dấu ?, hai giá trị theo thứ tự SQL.
    public List<Item> booksAtLeast(BigDecimal minPrice) {
        return jdbc.sql("""
                SELECT id, sku, category, price, stock
                FROM inventory_item
                WHERE category = ? AND price >= ?
                ORDER BY id
                """)
            .params("BOOK", minPrice)
            .query(ITEM_MAPPER)
            .list();
    }

    // Positional explicit binding: chọn index JDBC 1-based.
    public int addStockIndexed(long id, int delta) {
        if (delta <= 0) {
            throw new IllegalArgumentException("delta must be positive");
        }

        return jdbc.sql("""
                UPDATE inventory_item
                SET stock = stock + ?
                WHERE id = ?
                """)
            .param(2, id)
            .param(1, delta)
            .update();
    }

    // Named binding: :discount xuất hiện 2 lần nhưng chỉ khai báo một lần.
    public int discountNamed(long id, BigDecimal discount) {
        if (discount.signum() <= 0) {
            throw new IllegalArgumentException("discount must be positive");
        }

        return jdbc.sql("""
                UPDATE inventory_item
                SET price = price - :discount
                WHERE id = :id AND price >= :discount
                """)
            .param("id", id)
            .param("discount", discount)
            .update();
    }

    // Named list expansion cho điều kiện IN (:categories).
    public List<String> availableSkus(
            List<String> categories, BigDecimal minPrice) {

        if (categories.isEmpty()) {
            return List.of();
        }

        return jdbc.sql("""
                SELECT sku FROM inventory_item
                WHERE category IN (:categories)
                  AND price >= :minPrice AND stock > 0
                ORDER BY id
                """)
            .params(Map.of(
                "minPrice", minPrice,
                "categories", categories
            ))
            .query((rs, rowNum) -> rs.getString("sku"))
            .list();
    }

    // Một record làm nguồn named parameters.
    public long countWithFilter(PriceFilter filter) {
        return jdbc.sql("""
                SELECT COUNT(*) FROM inventory_item
                WHERE category = :category AND price >= :minPrice
                """)
            .paramSource(filter)
            .query(Long.class)
            .single();
    }

    // Named NULL với SQL type tường minh.
    public int clearNote(long id) {
        return jdbc.sql(
                "UPDATE inventory_item " +
                "SET note = :note WHERE id = :id"
            )
            .param("note", null, Types.VARCHAR)
            .param("id", id)
            .update();
    }

    public int stockBySku(String sku) {
        return jdbc.sql(
                "SELECT stock FROM inventory_item WHERE sku = :sku"
            )
            .param("sku", sku)
            .query(Integer.class)
            .single();
    }

    public BigDecimal priceBySku(String sku) {
        return jdbc.sql(
                "SELECT price FROM inventory_item WHERE sku = :sku"
            )
            .param("sku", sku)
            .query(BigDecimal.class)
            .single();
    }
}
~~~

### 10.7. Ứng dụng: `JdbcClientBindingApplication.java`

~~~java
package com.example.jdbcclient;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JdbcClientBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(JdbcClientBindingApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstration(InventoryRepository repository) {
        return args -> {
            List<String> bookSkus = repository
                .booksAtLeast(new BigDecimal("80.00"))
                .stream()
                .map(InventoryRepository.Item::sku)
                .toList();
            System.out.println("Positional books = " + bookSkus);

            int indexedUpdated = repository.addStockIndexed(2L, 2);
            System.out.println("Indexed updated = " + indexedUpdated);
            System.out.println(
                "SPRING-CORE stock = " +
                repository.stockBySku("SPRING-CORE")
            );

            int namedUpdated = repository.discountNamed(
                1L, new BigDecimal("20.00")
            );
            System.out.println("Named updated = " + namedUpdated);
            System.out.println(
                "JAVA-17 price = " +
                repository.priceBySku("JAVA-17")
            );

            List<String> available = repository.availableSkus(
                List.of("BOOK", "DEVICE"), new BigDecimal("80.00")
            );
            System.out.println("Named IN SKUs = " + available);

            long count = repository.countWithFilter(
                new InventoryRepository.PriceFilter(
                    "BOOK", new BigDecimal("80.00")
                )
            );
            System.out.println("Record filter count = " + count);

            int cleared = repository.clearNote(1L);
            System.out.println("Typed null updated = " + cleared);
        };
    }
}
~~~

### 10.8. Chạy thử

Tại thư mục project có `build.gradle`, dùng Gradle Wrapper nếu đã có:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell: `.\gradlew.bat bootRun`. Nếu chưa có wrapper nhưng đã cài Gradle tương thích: `gradle bootRun`. Java 21 cần được cài hoặc Gradle toolchain được cấu hình để tải/cấp JDK. Chương trình chạy trên H2 in-memory mới và in ra các dòng sau (không tính log Spring, HikariCP, Gradle):

~~~text
Positional books = [JAVA-17, SPRING-CORE]
Indexed updated = 1
SPRING-CORE stock = 5
Named updated = 1
JAVA-17 price = 100.00
Named IN SKUs = [JAVA-17, SPRING-CORE]
Record filter count = 2
Typed null updated = 1
~~~

**Giải thích từng kết quả:**

1. Truy vấn positional `category = ?`, `price >= ?` với `"BOOK"` và `80.00` chọn đúng hai sách: 120.00 và 89.50.
2. `addStockIndexed(2, 2)` gắn `id` vào JDBC index 2, `delta` vào index 1. Stock của SPRING-CORE tăng từ 3 lên 5; đúng một dòng bị tác động.
3. `discountNamed(1, 20.00)` dùng cùng tên `:discount` ở hai vị trí: giảm giá JAVA-17 từ 120.00 xuống 100.00; điều kiện `price >= :discount` hợp lệ.
4. Danh sách categories `["BOOK", "DEVICE"]` được mở rộng thành hai placeholder. Điều kiện giá từ 80.00 loại MOUSE giá 40.00; còn JAVA-17 và SPRING-CORE.
5. `PriceFilter` là record có `category` và `minPrice`, nên `paramSource(filter)` cung cấp đúng hai named parameters. COUNT = 2.
6. `clearNote(1L)` dùng typed SQL NULL cho `note` và cập nhật đúng một hàng.

Lưu ý: Demo này giải thích binding, không xây dựng đầy đủ lớp Service, authorization, quản lý cạnh tranh đồng thời và nghiệp vụ giảm giá. Trong ứng dụng thật, cần kiểm soát idempotency, số hàng cập nhật, transaction boundary và quyền của caller. **Các đoạn code đã được kiểm tra tĩnh về API/chữ ký; đầu ra phía trên là kết quả dự kiến từ dữ liệu và SQL được nêu, không phải kết quả một lượt chạy test trong tài liệu này.**

## 11. Phân tích trực tiếp việc chuyển đổi: positional và named

| Trường hợp | SQL viết trong Java | Giá trị ứng dụng cung cấp | SQL JDBC cuối cùng | Thứ tự bind |
| --- | --- | --- | --- | --- |
| Hai vị trí | `category = ? AND price >= ?` | `params("BOOK", 80.00)` | Không đổi | `BOOK, 80.00` |
| Index explicit | `stock = stock + ? WHERE id = ?` | `param(2, 2L), param(1, 3)` | Không đổi | `3, 2L` |
| Hai tên | `category = :category AND price >= :min` | `param("min", 80), param("category","BOOK")` | `category = ? AND price >= ?` | `BOOK, 80` |
| Lặp một tên | `price = price - :d WHERE price >= :d` | `param("d", 5)` | `price = price - ? WHERE price >= ?` | `5, 5` |
| Named list | `category IN (:cats) AND price > :min` | `cats=[BOOK,DEVICE], min=80` | `category IN (?, ?) AND price > ?` | `BOOK, DEVICE, 80` |

Các dòng trong bảng mô tả **giá trị và thứ tự logic**, không phải chuỗi SQL literal mà Spring chèn trực tiếp. Ký hiệu `80.00` đại diện giá trị số phù hợp kiểu SQL, không bắt buộc JDBC driver nhận một Java `double`.

### Tại sao điều kiện named lặp phải bind nhiều vị trí?

JDBC PreparedStatement chỉ biết **vị trí `?`**. Khi Spring chuyển `:d` xuất hiện ở hai chỗ thành hai dấu `?`, bộ bind phải đưa giá trị d vào **cả hai index**. Tương tự, Map chỉ có hai key không có nghĩa câu SQL sau mở rộng chỉ có hai placeholder.

### Thứ tự quan trọng trong thực tế

Trong code positional, nếu đảo ngược `params(80.00, "BOOK")`, driver có thể báo lỗi kiểu hoặc query không trả kết quả. Trong code named, `params(Map.of("min", 80.00, "category", "BOOK"))` không bị ảnh hưởng bởi thứ tự key của Map. Vì vậy SQL nhiều tham số nên cân nhắc named binding cho tính dễ đọc.

## 12. Kết quả query và lựa chọn mapping

Sau khi bind, bạn còn phải quyết định hình dạng kết quả. Cú pháp kết thúc thao tác thường dùng:

### Một giá trị chắc chắn có đúng một hàng

~~~java
long count = jdbcClient.sql(
        "SELECT COUNT(*) FROM inventory_item WHERE category = :category"
    )
    .param("category", "BOOK")
    .query(Long.class)
    .single();
~~~

`COUNT(*)` luôn trả một hàng trong truy vấn như trên, nên `single()` là lựa chọn rõ nghĩa. Dữ liệu có thể là `Long`/`Integer` tùy mapping/class yêu cầu; `query(Long.class)` cho kết quả kiểu Long theo mapping được Spring hỗ trợ.

### Không tìm thấy có thể là tình huống bình thường

~~~java
Optional<String> sku = jdbcClient.sql(
        "SELECT sku FROM inventory_item WHERE id = ?"
    )
    .param(999L)
    .query(String.class)
    .optional();
~~~

Nếu không có hàng, `optional()` trả `Optional.empty()`; nếu có hơn một hàng, đây là sai kỳ vọng “0 hoặc 1 hàng” và có thể phát sinh lỗi kích thước kết quả. `single()` thường đòi chính xác một hàng; phân biệt rõ giữa “không tìm thấy” và “lỗi database”.

### Danh sách object

~~~java
List<InventoryRepository.Item> items = jdbcClient.sql("""
        SELECT id, sku, category, price, stock
        FROM inventory_item
        WHERE category = :category ORDER BY id
        """)
    .param("category", "BOOK")
    .query((rs, rowNum) -> new InventoryRepository.Item(
        rs.getLong("id"),
        rs.getString("sku"),
        rs.getString("category"),
        rs.getBigDecimal("price"),
        rs.getInt("stock")
    ))
    .list();
~~~

Ở đây `RowMapper<T>` tách logic mapping `ResultSet` khỏi logic bind parameter. Nếu ứng dụng muốn tự map vào record/class phù hợp theo tên cột, `query(Item.class)` có thể dùng trong các điều kiện mapping được Spring hỗ trợ; với mapper tường minh, kết quả và cách chuyển type ít phụ thuộc quy ước hơn.

### DML và số hàng cập nhật

~~~java
int affected = jdbcClient.sql(
        "UPDATE inventory_item SET stock = stock + :delta WHERE id = :id"
    )
    .param("delta", 1)
    .param("id", 2L)
    .update();

if (affected != 1) {
    throw new IllegalStateException(
        "Expected one item updated, found " + affected
    );
}
~~~

`update()` trả **số hàng** SQL INSERT/UPDATE/DELETE tác động theo semantics JDBC; không tự trả record mới hoặc ID. Nếu cần generated key, `JdbcClient` cũng hỗ trợ overload `update(KeyHolder)` và `update(KeyHolder, String... keyColumnNames)` trong dòng Spring 6.1; cách đọc key phải tương thích driver và số lượng khóa sinh.

## 13. So sánh JdbcClient với hai template cơ bản

| Nhu cầu | JdbcTemplate | NamedParameterJdbcTemplate | JdbcClient |
| --- | --- | --- | --- |
| Bind `?` theo thứ tự | Có | Không phải mục tiêu chính | Có: `param(value)`/`params(Object...)` |
| Bind `:name` | Không trực tiếp | Có | Có: `param("name", value)` |
| SQL type/typed NULL | Qua `argTypes`, setter hoặc `SqlParameterValue` | Qua `MapSqlParameterSource` | Qua overload `param(..., sqlType)`/`paramSource` |
| Tham số list `IN` | Cần tạo số `?` phù hợp | Có expansion named Collection | Có qua tuyến named |
| Query và mapping | `query(sql, mapper, args...)` | `query(sql, source, mapper)` | `sql(sql).param(...).query(...).list()` |
| Update | `update(sql, args...)` | `update(sql, source)` | `sql(sql).param(...).update()` |
| Thao tác JDBC rất đặc thù | API callback rộng | Kế thừa delegation | Facade đơn giản cho tác vụ phổ biến |

`JdbcClient` không thay thế mọi chức năng tầng thấp. Ví dụ các API batch phức tạp, callback JDBC tùy biến và stored procedures có thể thích hợp hơn với `JdbcTemplate`, `SimpleJdbcInsert` hoặc `SimpleJdbcCall`. Tính năng của những phiên bản Spring mới hơn có thể thay đổi; khi dùng Spring Boot 3.3.x (Framework 6.1), nên dựa vào đúng Javadoc phiên bản mình cài.

### Cách tạo JdbcClient

Một ứng dụng Spring Framework thuần có thể tạo từ DataSource:

~~~java
JdbcClient jdbcClient = JdbcClient.create(dataSource);
~~~

Hoặc tạo từ `JdbcOperations`/các template đã được cấu hình qua overload `create(...)` thích hợp. Với **Spring Boot 3.3** và một `NamedParameterJdbcTemplate` auto-configured phù hợp, `JdbcClient` thường được auto-configured để có thể inject qua constructor như trong project phần 10. Không tự tạo `new DataSource` riêng trong mỗi Repository chỉ để có JdbcClient, vì sẽ làm mất cấu hình pool và transaction đang dùng.

## 14. Giao dịch Spring không phụ thuộc hình thức parameter

Hai lời gọi:

~~~java
jdbcClient.sql("UPDATE inventory_item SET stock = ? WHERE id = ?")
    .params(4, 1L)
    .update();

jdbcClient.sql("UPDATE inventory_item SET stock = :stock WHERE id = :id")
    .param("stock", 5)
    .param("id", 2L)
    .update();
~~~

đều là thao tác JDBC; việc chọn `?` hay `:name` **không quyết định transaction**. Nếu cả hai phải cùng commit hoặc rollback, application service nên xác định transaction boundary:

~~~java
// Fragment kiến trúc, cần import @Service và @Transactional.
// InventoryRepository là bean Spring thật; không phải file độc lập.
@Service
public class InventoryService {
    private final InventoryRepository items;

    public InventoryService(InventoryRepository items) {
        this.items = items;
    }

    @Transactional
    public void adjustTwoItems(long firstId, long secondId) {
        int first = items.addStockIndexed(firstId, 2);
        int second = items.addStockIndexed(secondId, 3);

        if (first != 1 || second != 1) {
            throw new IllegalStateException("Inventory adjustment failed");
        }
    }
}
~~~

Khi method public được gọi qua Spring proxy, transaction manager phù hợp với DataSource có thể điều phối hai thao tác. Một exception unchecked theo mặc định làm transaction được rollback. Trong ứng dụng thật cần chống self-invocation không qua proxy, kiểm soát concurrent updates, transaction isolation và validation/authorization.

**Không gọi `connection.commit()` hoặc `dataSource.close()` trong code bind parameter.** JdbcClient/JdbcTemplate cùng DataSource/transaction manager chịu trách nhiệm vòng đời tài nguyên; Service chịu trách nhiệm cho sự nhất quán của use case.

## 15. Các lỗi thường gặp và cách gỡ

| Vấn đề | Nguyên nhân | Cách giải quyết |
| --- | --- | --- |
| SQL có hai `?` nhưng chỉ truyền một `param` | Thiếu tham số vị trí | Đếm placeholder và bind đầy đủ |
| Gọi `param(0, value)` | JDBC index là 1-based | Bắt đầu từ index 1 |
| `params(minPrice, category)` nhưng SQL là `category = ? AND price >= ?` | Sai thứ tự | Bind theo thứ tự SQL hoặc đổi sang named |
| Dùng `param(":id", 5)` | Tên trong Java chứa dấu hai chấm | Dùng `param("id", 5)` |
| SQL dùng `:minPrice`, map chứa `minprice` | Tên không khớp/case | Đồng bộ chính xác tên SQL và key |
| Trộn `?` và `:id` trong một statement | Hai cơ chế bind không nhất quán | Chọn một style cho từng SQL |
| Nhầm `params(List)` với `IN (:ids)` | List positional và named expansion khác nhau | Dùng `param("ids", ids)` cho named IN |
| `IN (:ids)` với List rỗng | Có thể sinh SQL không hợp lệ | Định nghĩa nhánh rỗng rõ ràng |
| `Map.of("note", null)` | Java Map.of không cho NULL | Dùng `param(..., null, Types.X)` hoặc `MapSqlParameterSource` |
| `WHERE note = :note` với SQL NULL | Trong SQL, `= NULL` không true | Dùng `IS NULL` khi tìm giá trị NULL |
| Bind tên cột qua `ORDER BY :column` | Param chỉ biểu đạt data value | Whitelist identifier |
| SQL bị lỗi trong literal/comment có dấu `:` | Tự thay bằng regex hoặc cú pháp đặc thù | Để Spring parse, kiểm tra SQL/dialect cụ thể |
| Mong `update()` trả ID mới | Nhầm affected rows với generated keys | Dùng `KeyHolder` và overload phù hợp |
| Một update 0 rows nhưng vẫn coi thành công | WHERE không tìm thấy hoặc điều kiện chặn | Kiểm tra số hàng, phân loại not-found/conflict |
| Câu lệnh nhiều bước chưa atomic | Không có transaction boundary | Dùng `@Transactional` tại application service |
| Xây mới JdbcClient/DataSource mỗi request | Lifecycle/pool không đúng | Dùng bean singleton và dependency injection |
| Quá nhiều phần tử `IN` | Driver/DB có giới hạn placeholders | Giới hạn/cắt lô/temp table hoặc join phù hợp |

### Dò lỗi theo ba lớp

1. **SQL shape:** Có đúng số vị trí `?` hoặc đúng named placeholders `:name` không? Có đang cố bind tên cột/bảng không?
2. **Values/types:** Giá trị đúng thứ tự (positional) hay đúng key (named)? Có `NULL` hoặc `BigDecimal`/`SQL type` đặc biệt không?
3. **DB/transaction:** SQL thực thi trên database nào? Số hàng tác động là bao nhiêu? Constraint, quyền truy cập, timeout và transaction có đúng không?

Thông tin log SQL/parameter phải tránh in mật khẩu, mã xác thực, dữ liệu thanh toán và PII. Đừng tự xây logger nối literal values trực tiếp vào SQL rồi đem câu SQL đó đi thực thi.

## 16. SQL injection và ý nghĩa thực sự của binding

Không nên ghép input từ người dùng thành SQL:

~~~java
// PHẢN VÍ DỤ: có nguy cơ SQL injection.
String sql =
    "SELECT sku FROM inventory_item WHERE category = '" +
    userCategory + "'";
~~~

Thay bằng:

~~~java
List<String> result = jdbcClient.sql(
        "SELECT sku FROM inventory_item WHERE category = :category"
    )
    .param("category", userCategory)
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

Trong bản đúng, `userCategory` được gửi như **data value của PreparedStatement**. Nó không được nối thành một phần ngữ pháp SQL. Nếu userCategory chứa ký tự nháy, keyword SQL hay comment marker, nó vẫn được coi là **giá trị**, không đổi cấu trúc truy vấn.

Nhưng binding **không giải quyết mọi dạng injection**. Những đoạn SQL động như tên bảng, tên cột, chiều sắp xếp hoặc fragment `WHERE` vẫn phải đến từ whitelist hoặc DSL tin cậy. Dù dùng positional hay named, các placeholder chỉ bảo vệ dữ liệu thực sự được bind.

Với `LIKE`, đặt `%` trong pattern value khi muốn tìm wildcard:

~~~java
String pattern = "%" + keyword + "%";

jdbcClient.sql(
        "SELECT sku FROM inventory_item WHERE sku LIKE :pattern"
    )
    .param("pattern", pattern)
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

Nếu cần tìm nguyên văn ký tự `%` hoặc `_` do user nhập, phải escape wildcard theo SQL dialect. Bind value giúp chống injection, nhưng không tự thay đổi ngữ nghĩa wildcard của `LIKE`.

## 17. Khả năng đọc code, bảo trì và hiệu năng

Khi quyết định giữa positional và named, ưu tiên **tính rõ ràng của SQL**, không chỉ số ký tự Java:

- SQL có một hoặc hai dấu `?`: `params(...)` thường ngắn và dễ đọc.
- SQL có nhiều điều kiện, cùng một giá trị xuất hiện lặp lại: named `:name` giúp tránh nhầm thứ tự và nhân đôi value.
- Input đã có record/filter object: `paramSource(filter)` có thể bớt mã map thủ công.
- Điều kiện `IN` nhận List thay đổi số phần tử: named parameter expansion thuận tiện nhưng cần kiểm soát danh sách rỗng và giới hạn DB.
- Cần các lựa chọn statement/phương thức JDBC đặc thù: dùng API tầng thấp tương ứng thay vì ép mọi thứ vào fluent client.

**Không kết luận named chậm hơn hay nhanh hơn positional một cách tuyệt đối.** Named parameter cần parse/chuyển đổi SQL trong framework, nhưng Spring có cơ chế cache parsed SQL; hiệu năng thực tế thường chịu ảnh hưởng lớn hơn bởi network round-trips, SQL plan, index, lượng dữ liệu trả về, transaction và JDBC driver. Với `IN` list có kích thước khác nhau, SQL JDBC cuối cùng có số dấu `?` khác nhau, nên kế hoạch cache của driver/DB có thể khác nhau.

Trong code review, nên kiểm tra SQL và param ở gần nhau, tên tham số có ý nghĩa, không bind dữ liệu theo thứ tự tưởng tượng, và không phân tán cùng câu SQL qua nhiều method khó theo dõi.

## 18. Kiểm thử binding: cái gì chứng minh bằng unit test, cái gì cần database?

Một unit test của Repository có thể mock `JdbcClient`, nhưng việc mock một chain fluent khá dài đôi khi làm test mong manh. Với binding JDBC, một **integration test dùng H2** hoặc database thực thường đáng giá hơn vì xác minh được SQL, bind values/types và mapping.

### Các tình huống cần có

| Tình huống | Dữ liệu kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Positional đúng thứ tự | `category=BOOK, minPrice=80` | Có hai sách |
| Positional explicit index | Bind index 2 trước index 1 | Update đúng id và delta |
| Named đảo thứ tự đăng ký | `param("minPrice", ...).param("category", ...)` | Vẫn lấy đúng kết quả |
| Named lặp giá trị | `:discount` hai vị trí | Hai vị trí được bind cùng value |
| Named List trong IN | 2 categories | SQL thực thi và trả đúng dòng |
| Named List rỗng | `List.of()` | Theo chính sách, không query/không trả hàng |
| Typed NULL | `note = :note` với null VARCHAR | DB lưu SQL NULL |
| Thiếu key | SQL đòi `:id` nhưng không cung cấp | Báo lỗi bind rõ ràng |
| Case sensitivity | `:minPrice` nhưng key `minprice` | Không âm thầm bind sai |
| Injection-like input | Chuỗi chứa `' OR 1=1 --` | Chỉ là data value, không đổi truy vấn |
| SQL UPDATE 0 row | id không tồn tại | Trả 0, caller nhận biết |
| Transaction hai update | Update thứ hai ném exception | Rollback cả hai khi cùng transaction |

### Ví dụ kiểm tra logic có thể bổ sung

Trong project của phần 10, có thể thêm dependency `testImplementation 'org.springframework.boot:spring-boot-starter-test'` và dùng `@SpringBootTest` (context thật), tạo fixture/rollback phù hợp với từng bài test. Hãy tách logic test khỏi `CommandLineRunner` tạo dữ liệu/ghi dữ liệu trong demo nếu cần chạy test nhiều lần. Test chỉ kiểm tra `RowMapper` không chứng minh cách bind tham số; test integration phải gọi thực tế một method Repository và đọc lại hàng database để xác nhận.

**Quan trọng với transaction test:** Nếu test tự mở một transaction và rollback cuối test, hãy bảo đảm điều đó không che giấu sai lầm ở transaction boundary của application service. Với tình huống concurrent update hoặc database production, dùng driver/database phù hợp thay vì suy luận toàn bộ từ H2.

## 19. Bài tập tự kiểm tra

**Câu 1.** SQL `WHERE category = ? AND price >= ?` được gọi bằng `params(new BigDecimal("80"), "BOOK")` có đúng không?  
**Đáp án:** Sai thứ tự. `?` đầu tương ứng category, `?` sau tương ứng price. Phải gọi `params("BOOK", new BigDecimal("80"))`.

**Câu 2.** Với `.param(2, id).param(1, stock)`, JDBC index bắt đầu từ đâu?  
**Đáp án:** Từ **1**; giá trị gắn theo số index tường minh, không theo thứ tự method invocation.

**Câu 3.** SQL `WHERE category = :category AND price >= :minPrice` có thể đăng ký minPrice trước category không?  
**Đáp án:** Có. Spring tra tham số theo **tên**, sau đó bind vào SQL theo thứ tự placeholder được parse.

**Câu 4.** SQL có `price = price - :d WHERE price >= :d`; có mấy tên duy nhất và mấy vị trí JDBC?  
**Đáp án:** Một tên duy nhất `d` nhưng hai lần xuất hiện, nên có **hai vị trí `?`**.

**Câu 5.** `params(List.of("BOOK", "DEVICE"))` có tự động biến `IN (?)` thành `IN (?, ?)` không?  
**Đáp án:** Không; overload `params(List)` dùng cho **danh sách các tham số vị trí**. Muốn named list expansion, dùng `IN (:categories)` và `param("categories", List.of("BOOK", "DEVICE"))`.

**Câu 6.** `Map.of("note", null)` có bind NULL trong named SQL được không?  
**Đáp án:** Không. Java `Map.of` không chấp nhận null. Dùng `param("note", null, Types.VARCHAR)` hoặc `MapSqlParameterSource`.

**Câu 7.** `ORDER BY :sortColumn` có khiến SQL sắp xếp theo một cột có tên user chọn không?  
**Đáp án:** Không. Placeholder bind một **value**, không bind identifier. Chọn identifier qua whitelist trong code.

**Câu 8.** Có thể dùng positional ở một method Repository, named ở method khác không?  
**Đáp án:** Có. Không nên trộn hai kiểu binding trong **một câu SQL/StatementSpec**, nhưng các thao tác độc lập được chọn kiểu phù hợp.

**Bài tập thực hành:** Thêm `updatePricePositional(long id, BigDecimal price)` dùng `params(price, id)`, và `updatePriceNamed(long id, BigDecimal price)` dùng `:price`/`:id`. Viết integration tests kiểm tra hai method cho cùng kết quả. Sau đó thêm `findByCategoriesAndMinStock(List<String> categories, int minStock)` với `IN (:categories)`, guard list rỗng, typed SQL NULL cho cột note. Thử chuỗi SKU đặc biệt chứa dấu nháy để kiểm tra binding vẫn xem chuỗi là data value.

## 20. Tài liệu chính thức

- [Spring Framework 6.1 — JdbcClient](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html): khái niệm fluent facade cho positional/named JDBC.
- [Spring Framework 6.1 — JdbcClient.StatementSpec](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.StatementSpec.html): các overload `param`, `params`, `paramSource`, `query`, `update`.
- [Spring Framework — JDBC Core & JdbcClient](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html): ví dụ `JdbcClient.create(dataSource)`, positional và named binding, map/record parameter source.
- [Spring Framework — Named Parameters và IN clause](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): SQL types, danh sách tham số và các giới hạn.
- [Spring Boot — JdbcClient auto-configuration](https://docs.spring.io/spring-boot/docs/3.3.5/reference/html/data.html): bối cảnh dùng JdbcClient trong ứng dụng Boot có DataSource/NamedParameterJdbcTemplate.

## 21. Kết luận

**JdbcClient thống nhất API fluent, không làm biến mất hai mô hình binding:**

- **Positional:** SQL dùng `?`; `param(value)`/`params(values...)` theo thứ tự, hoặc `param(jdbcIndex, value)` với index **1-based**.
- **Named:** SQL dùng `:name`; `param("name", value)`, `params(Map)` hoặc `paramSource(...)`; Spring parse, mở rộng danh sách khi cần và bind các vị trí JDBC tương ứng.
- **Không trộn** hai phong cách trong cùng statement. Tùy tác vụ, mỗi method Repository có thể chọn một kiểu để dễ đọc nhất.
- **Binding an toàn** áp dụng cho dữ liệu, không áp dụng cho tên bảng/cột/SQL fragment tự ghép.
- **SQL type, transaction, vòng đời tài nguyên và semantics kết quả** vẫn phải hiểu đúng — dù cú pháp Java có gọn hơn.

Cách suy nghĩ thực tế: **“SQL của tôi đang mô tả dữ liệu qua vị trí hay qua tên?”** Từ đó chọn đúng API bind, rồi để JdbcClient/JdbcTemplate thực thi bằng PreparedStatement theo cấu hình Spring.

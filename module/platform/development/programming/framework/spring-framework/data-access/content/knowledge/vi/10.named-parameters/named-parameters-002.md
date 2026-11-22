# Cú pháp :name và cách chuyển về tham số vị trí trong Spring JDBC

> **Bối cảnh:** Spring Framework → data-access → **Tham số có tên**. Bài này tập trung vào cú pháp **`:name`** trong `NamedParameterJdbcTemplate`, cách Spring phân tích SQL rồi **chuyển tên tham số sang các placeholder JDBC `?` theo đúng thứ tự xuất hiện**, và cách giá trị cùng kiểu SQL được bind vào `PreparedStatement`. Nội dung cũng giải thích tham số được dùng lặp lại, danh sách `IN (:ids)`, ngoại lệ khi SQL có dấu hai chấm và các lỗi khi hiểu sai quá trình chuyển đổi.

## 1. Vì sao cần tham số có tên?

JDBC chuẩn phổ biến nhất dùng **tham số vị trí**: mỗi dấu `?` đứng ở vị trí thứ 1, 2, 3, ... trong một `PreparedStatement`. Ví dụ truy vấn sản phẩm:

~~~sql
SELECT id, sku, price
FROM product
WHERE category = ?
  AND price >= ?
  AND stock > ?
ORDER BY id;
~~~

Java phải truyền tham số đúng thứ tự:

~~~java
// Fragment minh họa: jdbc là JdbcTemplate; mapper là RowMapper<Product>.
jdbc.query(sql, mapper, "BOOK", new BigDecimal("70.00"), 0);
~~~

Khi có nhiều điều kiện, SQL thay đổi thứ tự cột hoặc một điều kiện sử dụng cùng một giá trị ở nhiều nơi, việc nhớ “`?` thứ 2 nghĩa là gì?” dễ gây lỗi. Bằng **tham số có tên**, câu SQL tự mô tả ý nghĩa hơn:

~~~sql
SELECT id, sku, price
FROM product
WHERE category = :category
  AND price >= :minPrice
  AND stock > :minStock
ORDER BY id;
~~~

Và truyền giá trị theo tên:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("category", "BOOK")
    .addValue("minPrice", new BigDecimal("70.00"))
    .addValue("minStock", 0);

namedJdbc.query(sql, params, mapper);
~~~

Trong mã trên, biến `namedJdbc` có kiểu `NamedParameterJdbcTemplate`. Tên `category`, `minPrice` và `minStock` trong Java **không có dấu `:`**; dấu `:` chỉ là phần của cú pháp placeholder trong chuỗi SQL. Spring nhận ra `:minPrice` và tra giá trị dưới khóa `"minPrice"`.

**Cần phân biệt:** SQL có tên tham số này là cách viết được Spring hỗ trợ **trước khi gửi câu lệnh đến JDBC driver**. JDBC driver thông thường không tự nhận biết `:category` dưới dạng placeholder tiêu chuẩn. Spring chuyển nó về **SQL chứa `?` và các giá trị theo vị trí** rồi mới thực thi.

## 2. So sánh hai kiểu tham số

| Khía cạnh | `JdbcTemplate` với `?` | `NamedParameterJdbcTemplate` với `:name` |
| --- | --- | --- |
| Viết SQL | `WHERE id = ? AND status = ?` | `WHERE id = :id AND status = :status` |
| Truyền giá trị | Theo **vị trí** trong SQL | Theo **tên** trong nguồn tham số |
| Lặp cùng một giá trị | Phải cung cấp lại đúng từng vị trí | Có thể lặp lại cùng một tên |
| Truy vấn dài | Dễ nhầm vị trí | Dễ đọc hơn khi đặt tên có ý nghĩa |
| Danh sách `IN` | Phải có số `?` phù hợp | Có cơ chế mở rộng `List` thành nhiều `?` |
| Cơ chế cuối cùng | PreparedStatement JDBC | Vẫn dùng PreparedStatement JDBC sau chuyển đổi |
| An toàn SQL injection | An toàn cho **giá trị được bind** | Tương tự; tên tham số không tự cho phép nối SQL động |
| Khi nào phù hợp | SQL rất ngắn, ít tham số | SQL nhiều điều kiện, dùng tên lặp lại hoặc danh sách `IN` |

Không có việc loại bỏ `JdbcTemplate`: `NamedParameterJdbcTemplate` **bọc và ủy quyền cho một JdbcTemplate cổ điển** sau giai đoạn chuyển đổi tham số. Spring giữ lợi ích quản lý Connection, Statement/ResultSet, transaction và dịch `SQLException` thành `DataAccessException`.

## 3. Cú pháp `:name` và các thành phần của một SQL named parameter

Hãy đọc ví dụ:

~~~sql
UPDATE product
SET price = :newPrice
WHERE id = :productId
  AND category = :category;
~~~

- Ký tự `:` báo cho bộ phân tích của Spring vị trí bắt đầu một placeholder có tên.
- `newPrice`, `productId` và `category` là tên tham số mà ứng dụng dùng để cấp giá trị.
- Tên sau dấu `:` phải khớp **chính xác** với key/cách truy cập của nguồn tham số (có phân biệt chữ hoa và chữ thường đối với `MapSqlParameterSource`).
- Những dấu `:` trong literal SQL, comment hoặc cú pháp riêng của database **không mặc nhiên** là tên tham số; Spring sử dụng parser thay vì thay chuỗi tất cả dấu hai chấm.
- Tên tham số **không đồng nghĩa tên cột**. `:newPrice` chỉ là chỗ đặt **giá trị dữ liệu** dùng cho cột `price`.

Ví dụ giá trị:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("newPrice", new BigDecimal("49.90"))
    .addValue("productId", 12L)
    .addValue("category", "BOOK");
~~~

Spring về mặt khái niệm chuyển thành:

~~~sql
UPDATE product
SET price = ?
WHERE id = ?
  AND category = ?;
~~~

Và JDBC bind theo thứ tự:

| Vị trí `?` (1-based) | Tên ban đầu | Giá trị |
| --- | --- | --- |
| 1 | `newPrice` | `49.90` |
| 2 | `productId` | `12` |
| 3 | `category` | `"BOOK"` |

Dù bạn gọi `addValue("category", ...)` trước `addValue("newPrice", ...)`, thứ tự JDBC cuối cùng vẫn dựa trên **vị trí xuất hiện trong SQL**, không dựa vào thứ tự chèn key trong Map.

### `:name` không phải cú pháp gán chuỗi

`:name` **không** được thay bằng dữ liệu text đã quote rồi nối vào chuỗi SQL như `'BOOK'`. Câu SQL cuối cùng ở phía PreparedStatement chứa `?`, còn dữ liệu được bind riêng bằng API JDBC. Đây là điểm then chốt của parameter binding, giúp chống SQL injection cho **giá trị** và giữ thông tin kiểu dữ liệu.

## 4. Quá trình chuyển sang tham số vị trí: từng bước

Giả sử câu SQL có hai placeholder cùng tên:

~~~sql
UPDATE product
SET stock = stock + :delta
WHERE id = :id AND stock + :delta >= 0;
~~~

Nguồn tham số:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("id", 2L)
    .addValue("delta", 4);
~~~

Mặc dù `id` được thêm **trước** `delta`, Spring phải đọc các placeholder theo **thứ tự SQL**:

~~~text
Tên gặp theo thứ tự: delta, id, delta
SQL JDBC:
UPDATE product SET stock = stock + ?
WHERE id = ? AND stock + ? >= 0

Giá trị theo vị trí (1-based): [4, 2, 4]
~~~

Vì `:delta` xuất hiện **hai lần**, nó biến thành **hai dấu `?`**, và cùng giá trị 4 được bind tại cả vị trí 1 lẫn vị trí 3. **Không** chỉ gửi một giá trị 4 rồi yêu cầu JDBC dùng chung ở hai vị trí.

Quá trình xử lý khái niệm:

~~~mermaid
flowchart TD
    A["SQL chứa :name và SqlParameterSource"] --> B["Spring parseSqlStatement: tìm tên, vị trí"]
    B --> C["Tạo SQL mới: thay :name bằng ?"]
    B --> D["Xác định từng tên theo thứ tự xuất hiện"]
    D --> E["Tra giá trị/SQL type theo tên"]
    C --> F["PreparedStatement JDBC"]
    E --> F
    F --> G["Bind từng tham số từ 1 đến N"]
    G --> H["JDBC driver thực thi trên DBMS"]
~~~

**Cụ thể hơn trong Spring JDBC:**

1. `NamedParameterJdbcTemplate` nhận chuỗi SQL và `Map<String, ?>` hoặc `SqlParameterSource`.
2. Spring dùng hạ tầng `NamedParameterUtils` và `ParsedSql` để tìm các named parameter hợp lệ trong câu SQL. Việc phân tích có thể được **cache theo SQL string** ở cấp template.
3. `NamedParameterUtils.substituteNamedParameters(...)` tạo SQL có placeholder JDBC, kể cả mở rộng danh sách `IN` khi có giá trị `Iterable` phù hợp.
4. `NamedParameterUtils.buildValueArray(...)` kết hợp thứ tự tên với giá trị/kiểu tham số. Đối với danh sách `IN`, khâu bind nội bộ tiếp tục mở rộng các phần tử thành vị trí JDBC tương ứng.
5. Spring tạo `PreparedStatement` theo SQL đã chuyển đổi, bind từng vị trí bằng API JDBC rồi thực thi; `JdbcTemplate` thực hiện quản lý vòng đời tài nguyên.

Trên đường đi, framework có thể sử dụng `PreparedStatementCreatorFactory` và `PreparedStatementSetter` nội bộ. Điều quan trọng với code ứng dụng là **SQL và giá trị không bị ghép text một cách thiếu an toàn**.

### Không nhầm đếm tên duy nhất với đếm vị trí

Trong truy vấn lặp `:delta`, có **2 tên duy nhất** (`delta`, `id`) nhưng **3 vị trí bind**. Khi có một list dài 3 phần tử trong `IN (:ids)`, một tên `ids` còn có thể sinh ra **3 vị trí `?`**. Vì thế không thể lấy `map.size()` rồi kết luận chắc chắn số dấu `?` trong SQL sau chuyển đổi.

## 5. Kiểm chứng trực tiếp bằng `NamedParameterUtils`

Spring công khai utility API để quan sát cơ chế parse và substitute. Đoạn Java sau phù hợp với Spring JDBC 6.x:

~~~java
import java.util.Arrays;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterUtils;
import org.springframework.jdbc.core.namedparam.ParsedSql;

String sql =
    "UPDATE product SET stock = stock + :delta " +
    "WHERE id = :id AND stock + :delta >= 0";

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("id", 2L)
    .addValue("delta", 4);

ParsedSql parsed = NamedParameterUtils.parseSqlStatement(sql);
String positionalSql =
    NamedParameterUtils.substituteNamedParameters(parsed, params);

Object[] positionalValues =
    NamedParameterUtils.buildValueArray(parsed, params, null);

System.out.println("SQL = " + positionalSql);
System.out.println("Args = " + Arrays.toString(positionalValues));
~~~

Đây là một **fragment**; phần 11 cung cấp project chạy được hoàn chỉnh. Trong ví dụ fragment, `buildValueArray` với tham số không khai báo kiểu SQL trả các giá trị tương ứng cho các **lần xuất hiện của tên**, do đó in danh sách `[4, 2, 4]`. Nếu đăng ký kiểu SQL tường minh, một số giá trị có thể được bọc bằng `SqlParameterValue`; không nên giả định mọi `Object[]` đều chứa raw `Integer`/`Long`.

**Lưu ý kỹ thuật quan trọng:** `buildValueArray` không phải API để tự tạo một mảng giá trị phẳng cuối cùng cho mọi trường hợp, đặc biệt là `IN (:ids)`. Với danh sách, hãy để `NamedParameterJdbcTemplate`/factory nội bộ bind từng phần tử; utility phù hợp để học cú pháp, debug hoặc xây hạ tầng thật sự có lý do.

## 6. Cấp giá trị bằng Map, MapSqlParameterSource và BeanPropertySqlParameterSource

### 6.1. `Map<String, ?>` — ngắn gọn cho CRUD

~~~java
String sql =
    "SELECT COUNT(*) FROM product WHERE category = :category";

Integer count = namedJdbc.queryForObject(
    sql,
    Map.of("category", "BOOK"),
    Integer.class
);
~~~

`Map.of(...)` trong Java 9+ không chấp nhận key/value `null`. Khi cần giá trị NULL SQL hoặc nhiều kiểu dữ liệu, dùng `MapSqlParameterSource` để rõ ràng hơn.

### 6.2. `MapSqlParameterSource` — phù hợp với typed NULL

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("id", 2L, java.sql.Types.BIGINT)
    .addValue("note", null, java.sql.Types.VARCHAR);

int changed = namedJdbc.update(
    "UPDATE product SET note = :note WHERE id = :id",
    params
);
~~~

`MapSqlParameterSource` triển khai `SqlParameterSource`; nó quản lý tên, giá trị và khi cần có thể kèm **mã kiểu JDBC** (`java.sql.Types`) và type name. Khi SQL có NULL hoặc driver khó suy luận kiểu, khai báo kiểu tường minh giúp bind đúng và dễ debug.

Với `SqlParameterSource`, `hasValue(name)` phân biệt **không có key** với **có key nhưng value = null**. `NamedParameterJdbcTemplate` yêu cầu tên cần thiết xuất hiện trong parameter source; “thiếu tên” không giống “SQL NULL”.

### 6.3. `BeanPropertySqlParameterSource` — lấy theo JavaBean property

Ví dụ một JavaBean có getter đúng tên:

~~~java
public class ProductFilter {
    private final String category;
    private final java.math.BigDecimal minPrice;

    public ProductFilter(String category, java.math.BigDecimal minPrice) {
        this.category = category;
        this.minPrice = minPrice;
    }

    public String getCategory() {
        return category;
    }

    public java.math.BigDecimal getMinPrice() {
        return minPrice;
    }
}

// Fragment dùng trong Repository:
SqlParameterSource source =
    new BeanPropertySqlParameterSource(
        new ProductFilter("BOOK", new BigDecimal("70.00"))
    );

namedJdbc.query(
    "SELECT id, sku FROM product " +
    "WHERE category = :category AND price >= :minPrice",
    source,
    (rs, rowNum) -> rs.getString("sku")
);
~~~

Nguồn tham số truy cập các **JavaBean properties** `category` và `minPrice` qua getters. Điều này không có nghĩa BeanPropertySqlParameterSource luôn nhận được field private bất kỳ hoặc mọi object có tên tương tự. Với Java record, cần xét phiên bản Spring và chọn nguồn hỗ trợ record (ví dụ `SimplePropertySqlParameterSource` trong các bản hỗ trợ) hoặc dùng Map để tránh lệ thuộc quy ước JavaBean.

**Tư duy lựa chọn:** `Map` cho 1–3 tham số ngắn; `MapSqlParameterSource` khi cần typed null/SQL types hoặc nhiều giá trị; `BeanPropertySqlParameterSource` khi có JavaBean sẵn với tên property khớp SQL. Không có loại nào làm thay đổi bản chất chuyển đổi `:name` → `?`.

## 7. Tên xuất hiện lặp lại: một key, nhiều vị trí

Ví dụ tìm sản phẩm theo hai thuộc tính cùng chứa keyword:

~~~sql
SELECT id, sku, category
FROM product
WHERE sku LIKE :pattern OR category LIKE :pattern
ORDER BY id;
~~~

Trong Java:

~~~java
String pattern = "%" + keyword + "%";

List<Product> rows = namedJdbc.query(
    sql,
    Map.of("pattern", pattern),
    mapper
);
~~~

Nếu `keyword = "BO"`, Spring tạo SQL tương đương:

~~~sql
SELECT id, sku, category
FROM product
WHERE sku LIKE ? OR category LIKE ?
ORDER BY id;
~~~

Và bind `"%BO%"` **hai lần**, tương ứng hai vị trí `?`. Không thể thay một lần SQL rồi quên bind vị trí thứ hai. Cũng không cần tạo hai key `pattern1`, `pattern2` chỉ vì cùng một giá trị được dùng hai nơi.

**Lưu ý về `LIKE`:** Bind cả mẫu `%keyword%` dưới dạng giá trị như trên. Ký tự `%` và `_` do người dùng nhập có thể tự trở thành wildcard; nếu sản phẩm yêu cầu **tìm literal** thì cần escape các wildcard theo cú pháp `ESCAPE` của database. Bind parameter ngăn SQL injection ở mức value nhưng không tự “escape nghĩa LIKE”.

## 8. Danh sách `IN (:ids)` mở rộng thành nhiều dấu `?`

JDBC không cho phép một placeholder duy nhất tự đại diện cho số phần tử thay đổi trong một SQL `IN`. Đây là lý do named parameter support **có thêm bước SQL expansion**.

SQL nguồn:

~~~sql
SELECT id, sku
FROM product
WHERE id IN (:ids)
ORDER BY id;
~~~

Tham số:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("ids", List.of(1L, 2L, 3L));
~~~

SQL sau mở rộng:

~~~sql
SELECT id, sku
FROM product
WHERE id IN (?, ?, ?)
ORDER BY id;
~~~

Lúc bind, các phần tử **1, 2, 3** lần lượt đi vào các vị trí JDBC 1, 2, 3. Spring **không** chuyển list thành chuỗi `"1,2,3"` rồi nối vào SQL; cách đó vừa dễ sai kiểu vừa có nguy cơ injection.

Một ví dụ kết hợp list và giá trị đơn:

~~~sql
SELECT id, sku
FROM product
WHERE category IN (:categories)
  AND price >= :minPrice
ORDER BY id;
~~~

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("minPrice", new BigDecimal("70.00"))
    .addValue("categories", List.of("BOOK", "DEVICE"));

List<String> skuList = namedJdbc.query(
    sql,
    params,
    (rs, rowNum) -> rs.getString("sku")
);
~~~

Nếu có hai categories, SQL JDBC sẽ có **3** dấu `?`: hai cho list, một cho `:minPrice`. Mặc dù Java thêm `minPrice` trước `categories`, thứ tự JDBC vẫn là **BOOK, DEVICE, 70.00** vì SQL gặp `:categories` trước.

### Vì sao `IN (:ids)` khác `= :ids`?

`IN (:ids)` có cú pháp SQL cho **một danh sách phần tử** sau khi expanded thành `IN (?, ?, ?)`. Ngược lại `id = :ids` với một List nhiều phần tử sẽ tạo dạng SQL không hợp lệ hoặc ngữ nghĩa không phù hợp; bạn không thể mong một giá trị list hoạt động như một scalar trong toán tử `=`.

### Trường hợp danh sách rỗng

Nếu `ids` rỗng, nhiều database không chấp nhận `IN ()`; đừng mặc định Spring tự biến danh sách trống thành điều kiện luôn sai trên mọi SQL dialect. Chủ động xác định ngữ nghĩa:

~~~java
public List<Long> findIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }

    return namedJdbc.query(
        "SELECT id FROM product WHERE id IN (:ids) ORDER BY id",
        Map.of("ids", ids),
        (rs, rowNum) -> rs.getLong("id")
    );
}
~~~

Nếu nghiệp vụ muốn “không lọc” khi danh sách trống, phải thiết kế nhánh SQL khác một cách tường minh và bảo vệ cấu trúc SQL. Không lén thay điều kiện `IN` thành bỏ lọc khi người dùng yêu cầu danh sách rỗng, vì có thể vô tình trả **toàn bộ dữ liệu**.

### Danh sách rất dài và giới hạn DBMS

JDBC/DBMS có giới hạn số placeholder hoặc phần tử trong `IN`. Spring lưu ý tính tương thích giữa các database khác nhau, nên **đừng mặc định hàng chục nghìn ID trong một `IN (:ids)`** sẽ hoạt động hoặc có hiệu năng tốt. Giải pháp có thể là giới hạn đầu vào, chia truy vấn thành nhóm hợp lý, batch processing, bảng tạm, join hoặc cơ chế array/table-valued parameter riêng của database. Khi chia nhóm cần xác định ngữ nghĩa thứ tự/kết quả trùng lặp và giao dịch.

### Danh sách tuple nhiều cột

Với database hỗ trợ cú pháp so sánh tuple như `(id, category) IN ((?, ?), (?, ?))`, Spring hỗ trợ truyền danh sách mảng object để mở rộng biểu thức list. Nhưng **SQL dialect và driver phải hỗ trợ**. Đây là kỹ thuật nâng cao, không cần áp dụng cho truy vấn `IN` một cột thông thường.

## 9. Khi SQL chứa dấu `:` nhưng không phải tên tham số

Không được thay văn bản theo `sql.replace(":id", "?")`. Thao tác đó có thể phá các trường hợp hợp lệ như:

~~~sql
SELECT ':id' AS sample_label
FROM product
WHERE id = :id;

-- Ghi chú :id là mô tả, không phải tham số.
SELECT id FROM product WHERE sku = :sku;

/* Comment :category không phải tham số */
SELECT sku FROM product WHERE category = :category;
~~~

Trong literal được trích dẫn `':id'` và comment, `:id` **không phải named parameter**, còn `id = :id` ở ngoài là placeholder cần bind. Bộ phân tích của Spring nhận diện SQL quotes/comments để tránh thay nhầm.

### PostgreSQL cast `::`

PostgreSQL có cú pháp cast như `'123'::integer`. Với bộ phân tích Spring JDBC, `::` không nên bị coi thành hai named parameters. Tuy vậy các extension hoặc operator riêng của một DBMS có thể tạo tình huống lexical khó; hãy kiểm thử những SQL thực tế trên đúng Spring/driver/database, thay vì dựa vào bộ replace chuỗi do tự viết.

### Chỉ dùng `:name` ở chỗ mong đợi giá trị

`SELECT * FROM :table` và `ORDER BY :sortColumn` không dùng được để bind tên bảng/tên cột như identifier. Placeholder đại diện cho **value**, không phải **cấu trúc SQL**. Nếu phải chọn cột sort theo input, dùng whitelist:

~~~java
String sortColumn = switch (sortBy) {
    case "price" -> "price";
    case "sku" -> "sku";
    default -> "id";
};

String sql =
    "SELECT id, sku, price FROM product WHERE category = :category " +
    "ORDER BY " + sortColumn;
~~~

Đây là fragment minh họa; `sortBy` đã được ứng dụng nhận vào và phải kiểm tra theo whitelist. **Không** lấy trực tiếp bất kỳ chuỗi request nào chèn vào vị trí identifier. Dù dùng named parameter, ứng dụng vẫn phải bảo vệ **SQL fragment do mình tự nối**.

## 10. Chuyển đổi tên tham số diễn ra ở đâu trong ứng dụng?

Một Repository Spring JDBC thường có dạng:

~~~text
Controller / Job
   -> Application Service
       -> ProductRepository
           -> NamedParameterJdbcTemplate
               -> parse SQL + substitute :name -> ?
               -> PreparedStatementCreatorFactory / binding
               -> JdbcTemplate / DataSource
                   -> JDBC Driver / Database
~~~

Repository chỉ cần biết cách lấy một danh sách kết quả, cập nhật hoặc insert bản ghi. Service không cần tự tạo placeholder JDBC. Các trường hợp SQL lớn có thể dùng multiline text block Java để câu SQL dễ đọc:

~~~java
String sql = """
    SELECT id, sku, price
    FROM product
    WHERE category = :category
      AND price >= :minPrice
    ORDER BY id
    """;
~~~

**Text block là cú pháp Java**, không thay đổi quy tắc parse named parameters. Nội dung SQL vẫn được Spring phân tích mỗi khi cần, hoặc lấy `ParsedSql` đã cache khi SQL string trùng khớp.

### Không nhầm với JPA/Hibernate named parameters

JPA/JPQL cũng dùng cú pháp `:name`, nhưng đây là **API/parser khác** và vòng đời query khác. `NamedParameterJdbcTemplate` là Spring JDBC, xử lý SQL thực tế và ủy quyền cho JdbcTemplate/PreparedStatement. Không dùng JPA Query API hoặc giả định hành vi collection expansion của hai hệ thống hoàn toàn giống nhau.

## 11. Ví dụ chạy độc lập: nhìn SQL và giá trị sau chuyển đổi

Ví dụ này dùng **Java 21**, **Spring Boot 3.3.5**, **Gradle**, **Spring JDBC** và **H2**. Mục tiêu là vừa chạy truy vấn thực tế với `NamedParameterJdbcTemplate` vừa **in ra SQL `?` và thứ tự tham số tương ứng** nhờ `NamedParameterUtils`.

### 11.1. Cấu trúc dự án

~~~text
named-parameters-lesson/
├── build.gradle
└── src/main/
    ├── java/com/example/namedparams/
    │   ├── NamedParamsApplication.java
    │   └── ProductRepository.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
~~~

### 11.2. `build.gradle`

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

Starter JDBC cung cấp JdbcTemplate, DataSource (thường HikariCP) và tích hợp auto-configuration cho `NamedParameterJdbcTemplate` khi điều kiện của Boot được đáp ứng. Không cần Spring Web để chạy chương trình console.

### 11.3. `src/main/resources/application.properties`

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:named_params_lesson;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

### 11.4. `src/main/resources/schema.sql`

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    category VARCHAR(24) NOT NULL,
    price DECIMAL(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    note VARCHAR(120)
);
~~~

### 11.5. `src/main/resources/data.sql`

~~~sql
INSERT INTO product (id, sku, category, price, stock, note)
VALUES (1, 'J-BOOK', 'BOOK', 120.00, 3, NULL);

INSERT INTO product (id, sku, category, price, stock, note)
VALUES (2, 'S-BOOK', 'BOOK', 75.00, 0, NULL);

INSERT INTO product (id, sku, category, price, stock, note)
VALUES (3, 'MOUSE', 'DEVICE', 40.50, 6, NULL);
~~~

Ba hàng được khởi tạo theo ID cố định để stdout của ví dụ không phụ thuộc cách database sinh khóa. Sản phẩm `S-BOOK` ban đầu hết hàng; câu UPDATE theo tên tham số sẽ tăng stock lên 4.

### 11.6. Repository: `ProductRepository.java`

~~~java
package com.example.namedparams;

import java.math.BigDecimal;
import java.sql.Types;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {
    public static final String RESTOCK_SQL =
        "UPDATE product SET stock = stock + :delta " +
        "WHERE id = :id AND stock + :delta >= 0";

    private final NamedParameterJdbcTemplate jdbc;

    public ProductRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // ':delta' có hai lần xuất hiện trong SQL nhưng chỉ một key.
    public int restock(long id, int delta) {
        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("id", id)
            .addValue("delta", delta);

        return jdbc.update(RESTOCK_SQL, params);
    }

    // Một tên :categories có thể mở rộng thành nhiều dấu '?'.
    public List<String> availableSkus(
            List<String> categories, BigDecimal minPrice) {

        if (categories.isEmpty()) {
            return List.of();
        }

        String sql = """
            SELECT sku FROM product
            WHERE category IN (:categories)
              AND price >= :minPrice
              AND stock > 0
            ORDER BY id
            """;

        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("minPrice", minPrice)
            .addValue("categories", categories);

        return jdbc.query(
            sql,
            params,
            (rs, rowNum) -> rs.getString("sku")
        );
    }

    // Tên tham số nằm trong SQL, key 'sku' trong Map không có ':'.
    public int stockBySku(String sku) {
        Integer stock = jdbc.queryForObject(
            "SELECT stock FROM product WHERE sku = :sku",
            Map.of("sku", sku),
            Integer.class
        );
        if (stock == null) {
            throw new IllegalStateException("Stock is SQL NULL");
        }
        return stock;
    }

    // NULL được khai báo kiểu JDBC tường minh.
    public int clearNote(long id) {
        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("id", id, Types.BIGINT)
            .addValue("note", null, Types.VARCHAR);

        return jdbc.update(
            "UPDATE product SET note = :note WHERE id = :id",
            params
        );
    }
}
~~~

Ở đây Repository không trực tiếp gọi `PreparedStatement.setInt`, nhưng **Spring vẫn dùng PreparedStatement ở bên dưới**. Hàm `restock` cố tình thêm key `id` **trước** `delta` để chứng minh thứ tự của Map không quyết định thứ tự bind.

`stockBySku` minh họa overload `queryForObject(String, Map, Class)`. Nếu không có hàng, Spring có thể ném `EmptyResultDataAccessException`; ví dụ chỉ tra một SKU chắc chắn tồn tại. Kiểm tra `stock == null` biểu diễn trường hợp cột trả SQL NULL, dù schema ví dụ đặt `stock NOT NULL`.

Trong một hệ thống thực, hãy kiểm tra `restock` trả số hàng cập nhật, vì 0 hàng có thể do ID không tồn tại hoặc điều kiện `stock + delta >= 0` không thỏa. Không coi 0 hàng là thành công chỉ vì không có exception.

### 11.7. Ứng dụng: `NamedParamsApplication.java`

~~~java
package com.example.namedparams;

import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterUtils;
import org.springframework.jdbc.core.namedparam.ParsedSql;

@SpringBootApplication
public class NamedParamsApplication {
    public static void main(String[] args) {
        SpringApplication.run(NamedParamsApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(ProductRepository products) {
        return args -> {
            MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("id", 2L)
                .addValue("delta", 4);

            ParsedSql parsed = NamedParameterUtils
                .parseSqlStatement(ProductRepository.RESTOCK_SQL);

            String sqlWithQuestions = NamedParameterUtils
                .substituteNamedParameters(parsed, params);

            Object[] argsByPosition = NamedParameterUtils
                .buildValueArray(parsed, params, null);

            System.out.println("SQL = " + sqlWithQuestions);
            System.out.println(
                "Args = " + Arrays.toString(argsByPosition)
            );

            int updated = products.restock(2L, 4);
            System.out.println("Updated rows = " + updated);
            System.out.println(
                "S-BOOK stock = " + products.stockBySku("S-BOOK")
            );

            List<String> skus = products.availableSkus(
                List.of("BOOK", "DEVICE"), new BigDecimal("70.00")
            );
            System.out.println("Available SKUs = " + skus);

            // Mở rộng danh sách :categories ra hai dấu ?.
            String inSql =
                "SELECT sku FROM product " +
                "WHERE category IN (:categories) AND price >= :minPrice";

            MapSqlParameterSource inParams = new MapSqlParameterSource()
                .addValue("minPrice", new BigDecimal("70.00"))
                .addValue("categories", List.of("BOOK", "DEVICE"));

            System.out.println("IN SQL = " +
                NamedParameterUtils.substituteNamedParameters(
                    inSql, inParams
                )
            );
        };
    }
}
~~~

**Không cần** import JdbcTemplate vào class Application vì Boot inject Repository và NamedParameterJdbcTemplate qua Spring context. `NamedParameterUtils` chỉ được dùng trong demo để **quan sát SQL biến đổi**; Repository thật không cần tự parse rồi bind array, vì `NamedParameterJdbcTemplate` đã làm việc đó.

### 11.8. Chạy chương trình

Ở thư mục chứa `build.gradle`:

~~~bash
# Nếu project đã có Gradle wrapper:
./gradlew bootRun

# Nếu chưa có wrapper nhưng đã cài Gradle tương thích:
gradle bootRun
~~~

Trên Windows PowerShell, wrapper chạy bằng `.\gradlew.bat bootRun`. Java 21 phải được cài, hoặc Gradle toolchain được cấu hình để cung cấp Java 21.

Với database H2 in-memory mới, các dòng **do ứng dụng chủ động in** (bỏ qua log Spring/HikariCP và Gradle) là:

~~~text
SQL = UPDATE product SET stock = stock + ? WHERE id = ? AND stock + ? >= 0
Args = [4, 2, 4]
Updated rows = 1
S-BOOK stock = 4
Available SKUs = [J-BOOK, S-BOOK]
IN SQL = SELECT sku FROM product WHERE category IN (?, ?) AND price >= ?
~~~

**Giải thích stdout theo từng bước:**

1. `:delta` xuất hiện ở vị trí đầu và cuối, `:id` đứng giữa ⇒ SQL có ba dấu `?` và giá trị theo thứ tự `[4, 2, 4]`.
2. `products.restock(2, 4)` cập nhật bản ghi ID=2 từ stock 0 thành 4; điều kiện không âm hợp lệ ⇒ 1 row updated.
3. Truy vấn theo SKU cho `S-BOOK` trả stock 4.
4. Trong danh sách `categories` có BOOK và DEVICE, nhưng giá tối thiểu 70.00 và stock phải dương, nên chỉ `J-BOOK` (120.00, 3) và `S-BOOK` (75.00, 4) thỏa; `MOUSE` giá 40.50 bị loại.
5. Khi chuyển `IN (:categories)` với hai phần tử, Spring tạo đúng hai placeholder trong `IN (?, ?)` và một placeholder nữa cho `:minPrice`.

Chương trình có thể được chạy lại ở **JVM mới** để nhận cùng kết quả; cùng một database được khởi tạo lại từ `schema.sql` và `data.sql`. Nếu cố ý gọi run logic hai lần trong cùng một context và không reset dữ liệu, số stock sẽ khác vì UPDATE được thực hiện thêm một lần.

## 12. Tham số SQL NULL, kiểu JDBC và dữ liệu thời gian

Một phương thức `addValue("name", null)` giúp biểu thị SQL NULL nhưng **driver/database có thể cần biết kiểu JDBC**. Ví dụ:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("id", 1L, java.sql.Types.BIGINT)
    .addValue("description", null, java.sql.Types.VARCHAR);

namedJdbc.update(
    "UPDATE product SET note = :description WHERE id = :id",
    params
);
~~~

`NamedParameterJdbcTemplate` còn phải chuyển tên tham số sang `?`, đồng thời bảo toàn **metadata loại SQL** khi bind. Với SQL `DECIMAL(12,2)`, sử dụng `BigDecimal` thay cho `double` để tránh lỗi nhị phân khi xử lý tiền tệ. Với `LocalDate`, `Instant` hoặc `OffsetDateTime`, việc ánh xạ và múi giờ cần được kiểm tra theo driver/schema thay vì xem tên tham số là đủ để chọn kiểu chính xác.

Có thể dùng `MapSqlParameterSource.registerSqlType(...)` hoặc `addValue(name, value, sqlType)` để khai báo type. Với SQL thông thường, nhiều driver suy luận đúng kiểu từ giá trị Java, nhưng các trường hợp NULL, array và kiểu đặc thù vendor có thể cần khai báo tường minh.

### Không viết `WHERE col = :value` khi giá trị có thể NULL

Khi `value = null`, SQL `col = NULL` không là true theo ba giá trị logic SQL. Nếu nghiệp vụ muốn tìm các dòng thiếu giá trị, dùng `IS NULL`:

~~~sql
SELECT id FROM product WHERE note IS NULL;
~~~

Hoặc tạo các nhánh SQL rõ ràng phù hợp với điều kiện optional. Bind một SQL NULL không làm toán tử `=` tự đổi thành `IS NULL`.

## 13. Thiếu tên, nhầm chính tả và thứ tự parameter

Ví dụ SQL:

~~~sql
SELECT id, sku FROM product
WHERE category = :category AND price >= :minPrice;
~~~

Nếu source chỉ có `category` mà **không có `minPrice`**, Spring không có đủ giá trị để bind và sẽ báo lỗi khi chuẩn bị thao tác. Không tự dùng `null` cho bất kỳ tên nào bị thiếu. Cần phân biệt:

- **Thiếu tên:** `hasValue("minPrice") == false`, source không cung cấp value.
- **Có tên nhưng value null:** `hasValue("minPrice") == true`, cần xử lý SQL semantics của NULL và kiểu tương ứng.
- **Sai chính tả/case:** `"minprice"` không tự khớp với `:minPrice` trong một MapSqlParameterSource case-sensitive.
- **Thừa tên không dùng trong SQL:** Map có một key khác ngoài những tên SQL sử dụng. Thông thường key đó không trở thành placeholder; dễ là dấu hiệu refactor bỏ sót hoặc dữ liệu thừa cần dọn.

**Không tự giải quyết thiếu tham số bằng nối chuỗi SQL từ input.** Nếu điều kiện là optional, hãy thiết kế SQL rõ ràng bằng cách xây whitelist các phần điều kiện được phép hoặc dùng builder/query layer phù hợp; các **giá trị** vẫn phải bind.

### Có thể trộn named và positional trong cùng SQL không?

Tránh trộn `:id` với `?` trong cùng một truy vấn `NamedParameterJdbcTemplate`. Cơ chế này được thiết kế để chuyển các tên thành các vị trí JDBC nhất quán; các tổ hợp vừa named vừa unnamed có thể bị từ chối khi xây mảng giá trị hoặc tạo ra tình huống không có mapping rõ. Chọn **một kiểu tham số nhất quán cho mỗi SQL**.

## 14. Parser của Spring không phải một phép `String.replace`

Các trường hợp parser phải phân biệt:

| Văn bản SQL | Nên xử lý thế nào? | Giải thích |
| --- | --- | --- |
| `WHERE id = :id` | Đổi `:id` thành `?` | Placeholder có tên hợp lệ |
| `WHERE x = :x AND y = :x` | Hai dấu `?`, cùng giá trị `x` | Hai lần xuất hiện |
| `IN (:ids)` với 3 id | `IN (?, ?, ?)` | List expansion |
| `SELECT ':id' AS label` | Giữ `':id'` | Chuỗi literal SQL |
| `-- :id` | Giữ nguyên comment | Không phải placeholder |
| `/* :id */` | Giữ nguyên comment | Không phải placeholder |
| PostgreSQL `'42'::integer` | Giữ nguyên cast `::` | Cú pháp database-specific |
| `ORDER BY :sortBy` | Không biến value thành tên cột | SQL identifier không bind được qua `?` |

Viết parser SQL an toàn **khó hơn** thay tất cả `:name` bằng `?` bằng regex. Với một số ngữ pháp vendor đặc thù (JSON operators, cast, quoted identifiers, escaped syntax), cần kiểm thử đúng câu SQL và phiên bản Spring/driver. Nếu cú pháp vendor không thể diễn đạt an toàn qua abstraction, cân nhắc `JdbcTemplate` ở một truy vấn chuyên biệt hoặc điều chỉnh SQL rõ ràng; không âm thầm nối giá trị raw.

## 15. Hiệu năng và cache phân tích SQL

`NamedParameterJdbcTemplate` có thể cache kết quả **phân tích cấu trúc SQL** nhằm tránh phải parse lại cùng một SQL string trên mỗi lần chạy. Cấu hình liên quan là `setCacheLimit(int)` và `getCacheLimit()`. Cần hiểu chính xác các loại cache:

- **Parsed SQL cache:** Lưu thông tin vị trí/nhận diện named parameters cho một SQL string. Không giữ kết quả SELECT.
- **JDBC PreparedStatement/plan cache:** Được quản lý bởi driver/database/pool theo cấu hình riêng, không đồng nghĩa với parsed SQL cache.
- **Ứng dụng cache dữ liệu nghiệp vụ:** Một vấn đề khác hoàn toàn; NamedParameterJdbcTemplate không tự cache kết quả query.

Nếu cùng một SQL dùng các giá trị `:ids` có số lượng phần tử khác nhau, câu SQL JDBC sau mở rộng có thể chứa **số dấu `?` khác nhau**, ảnh hưởng cách driver/DBMS cache statement/plan, dù SQL nguồn dùng cho parser cache không đổi.

**Không lạm dụng việc ghép literal vào SQL để “tối ưu cache”.** Ghép `WHERE id = 123` vào SQL cho mỗi request tạo nhiều SQL string khác nhau và dễ phát sinh injection. Giữ SQL template ổn định và bind dữ liệu giúp đọc mã và bảo mật tốt hơn.

## 16. Đặt ranh giới giao dịch và lỗi đúng tầng

Những câu SQL có tên tham số vẫn chạy thông qua cùng DataSource và transaction manager phù hợp như `JdbcTemplate` cổ điển. Một Service có use case nhiều bước có thể dùng `@Transactional`:

~~~java
// Fragment kiến trúc — class và bean phải được khai báo đầy đủ trong ứng dụng.
@Service
public class InventoryService {
    private final ProductRepository products;

    public InventoryService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void addStockForTwoItems(long firstId, long secondId) {
        int first = products.restock(firstId, 3);
        int second = products.restock(secondId, 5);
        if (first != 1 || second != 1) {
            throw new IllegalStateException("Restock not applied");
        }
    }
}
~~~

Đoạn này cần import `@Service` và `@Transactional` từ Spring. Hai UPDATE có thể thuộc cùng transaction khi public method được gọi qua Spring proxy, transaction manager điều phối cùng DataSource và không có cấu hình trái ngược.

**Named parameter không tạo transaction mới.** Nếu hai lần gọi `update` không nằm trong một transaction bao ngoài, có thể mỗi câu UPDATE hoạt động theo autocommit của database. Conversion `:name` → `?` là quá trình **chuẩn bị SQL**, không phải chính sách commit/rollback.

### Lỗi có thể xuất hiện ở ba giai đoạn

1. **Parse/bind:** Thiếu key, sai tên, kiểu SQL không phù hợp, `IN` rỗng hoặc SQL không thể chuyển được.
2. **JDBC execute/DBMS:** Sai cột/bảng, constraint violation, deadlock, lock timeout, network failure.
3. **Result mapping:** Mã đọc cột hoặc kiểu dữ liệu không đúng (RowMapper/ResultSetExtractor).

Spring thường chuyển `SQLException` ở tầng JdbcTemplate sang hệ phân cấp `DataAccessException`. Không nên bắt chung mọi `DataAccessException` rồi trả “không tìm thấy”, vì lỗi query, conflict và mất kết nối rất khác nhau.

## 17. Bảng đối chiếu lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `No value supplied for SQL parameter 'x'` | Thiếu key `x` | Dò tên `:x` và nguồn tham số |
| Giá trị bind nhầm dù Map đúng | Thứ tự SQL và suy luận thủ công khác nhau | Để template xử lý; dùng utility để kiểm tra thứ tự |
| Dùng `addValue(":id", 2)` | Key chứa dấu `:`, SQL đòi tên `id` | Truyền key `"id"` |
| SQL `WHERE id IN (:ids)` lỗi khi ids rỗng | `IN ()` không hợp lệ ở nhiều DB | Guard list rỗng trước khi query |
| Dùng list lớn hàng chục nghìn phần tử | Giới hạn placeholders/vendor, parse/bind overhead | Giới hạn, chia batch, temp table hoặc kỹ thuật đặc thù DB |
| Dùng `ORDER BY :column` | Placeholder chỉ bind value | Whitelist identifier và tạo SQL fragment có kiểm soát |
| `:foo` trong text literal bị tự thay bằng regex | Tự viết parser ngây thơ | Dùng NamedParameterJdbcTemplate/NamedParameterUtils |
| Tưởng `:delta` lặp lại chỉ bind một vị trí | Nhầm tên duy nhất với số vị trí | Gắn value cho mọi lần xuất hiện |
| `col = :value` với NULL không khớp | SQL dùng 3-valued logic | Dùng `IS NULL` nếu đúng nghiệp vụ |
| Gọi `Map.of("note", null)` | Map.of không chấp nhận null | Dùng MapSqlParameterSource |
| Trộn `?` và `:id` | Kết hợp mapping không rõ | Chọn một kiểu parameter trong một SQL |
| Ghi literal input trực tiếp vào SQL | Injection / lỗi quote và plan cache | Bind giá trị bằng `:name` |
| Nhầm Spring named parameters với JPA `Query` | Hai parser/API và quy tắc khác nhau | Xác định công nghệ truy cập đang dùng |
| Kỳ vọng converted SQL có giá trị đã interpolate | Nhầm prepared statement với string substitution | SQL chứa `?`; giá trị gửi riêng qua JDBC |

## 18. Kiểm thử cơ chế chuyển đổi đúng cách

**Test cấp utility** giúp xác nhận parse tên lặp và đổi SQL về các placeholder chuẩn. Ví dụ:

~~~java
// Fragment JUnit 5 minh họa, cần thêm dependency spring-boot-starter-test
// trong project test và các import JUnit.
@Test
void repeatedNameExpandsToThreePositions() {
    String sql =
        "UPDATE product SET stock = stock + :delta " +
        "WHERE id = :id AND stock + :delta >= 0";

    MapSqlParameterSource source = new MapSqlParameterSource()
        .addValue("id", 2L)
        .addValue("delta", 4);

    ParsedSql parsed = NamedParameterUtils.parseSqlStatement(sql);

    assertEquals(
        "UPDATE product SET stock = stock + ? " +
        "WHERE id = ? AND stock + ? >= 0",
        NamedParameterUtils.substituteNamedParameters(parsed, source)
    );

    assertArrayEquals(
        new Object[] { 4, 2L, 4 },
        NamedParameterUtils.buildValueArray(parsed, source, null)
    );
}
~~~

Test này **chứng minh hình dạng SQL và thứ tự giá trị**, nhưng chưa chứng minh DB chấp nhận cú pháp hoặc transaction hoạt động. Để làm điều đó, integration test với H2 hoặc database production-compatible cần chạy `NamedParameterJdbcTemplate.update/query` thật rồi đọc lại dữ liệu.

**Test cho `IN`** có thể kiểm tra `IN (:ids)` với 1, 2, 3 phần tử tạo SQL có số `?` tương ứng. Cần thêm test list rỗng theo **ngữ nghĩa nghiệp vụ đã chọn**; test với PostgreSQL/MySQL/Oracle nếu có giới hạn hoặc operator đặc thù.

**Test bảo mật** nên truyền chuỗi có dấu nháy, dấu gạch chéo, unicode, và chuỗi giống SQL injection như `"BOOK' OR 1=1 --"` dưới dạng value, rồi xác nhận nó chỉ được xử lý như **dữ liệu**, không phá query. Không cần in những giá trị nhạy cảm ra log.

## 19. `JdbcClient` và NamedParameterJdbcTemplate có gì khác?

Spring Framework 6.1 giới thiệu `JdbcClient` theo phong cách fluent API; nó dùng `JdbcOperations` và `NamedParameterJdbcOperations` bên dưới để thực thi query/update. Ví dụ:

~~~java
// Fragment minh họa: client là JdbcClient được tạo từ DataSource.
long count = client.sql(
        "SELECT COUNT(*) FROM product WHERE category = :category"
    )
    .param("category", "BOOK")
    .query(Long.class)
    .single();
~~~

Đây vẫn là **named parameter binding**; cách viết fluent chỉ thay đổi API bên ngoài. Bạn vẫn cần hiểu quá trình chuyển `:category` sang `?` để debug SQL và tránh nhầm tên với vị trí. Ngoài ra `JdbcTemplate` cổ điển vẫn hữu ích với các operation chuyên biệt; `NamedParameterJdbcTemplate.getJdbcOperations()` cho phép truy cập classic `JdbcOperations` khi cần.

Không cần đổi toàn bộ dự án sang `JdbcClient` chỉ để dùng named parameters; các công nghệ có thể cùng tồn tại nếu codebase nhất quán.

## 20. Bài tập thực hành

**Bài tập 1 — điền thứ tự bind.** Với câu SQL:

~~~sql
SELECT id FROM product
WHERE price >= :minPrice
  AND category = :category
  AND price <= :maxPrice
  AND category <> :blockedCategory;
~~~

Cho `params` được thêm theo thứ tự `blockedCategory`, `maxPrice`, `category`, `minPrice`. Hãy viết SQL JDBC và dãy giá trị theo vị trí.

**Gợi ý đáp án:** SQL có bốn `?` theo thứ tự `minPrice`, `category`, `maxPrice`, `blockedCategory`. Thứ tự thêm key vào Map không quyết định thứ tự JDBC.

**Bài tập 2 — tham số lặp.** Câu `WHERE sku = :term OR category = :term` có bao nhiêu `?`?  
**Đáp án:** Hai; cùng giá trị `term` bind tại cả hai vị trí.

**Bài tập 3 — danh sách.** `WHERE id IN (:ids) AND stock > :minStock` với `ids=[2,5,9]` có bao nhiêu placeholder?  
**Đáp án:** Bốn; ba cho list, một cho `minStock`.

**Bài tập 4 — danh sách rỗng.** Khi người dùng lọc theo danh sách IDs rỗng, có nên tự bỏ `WHERE id IN (...)` không?  
**Đáp án:** Không mặc định. Nếu nghiệp vụ hiểu tập ID rỗng nghĩa là không có kết quả, trả list rỗng mà không query; bỏ điều kiện có thể làm lộ mọi hàng.

**Bài tập 5 — NULL.** Dùng `WHERE note = :note`, `note=null` có tìm các dòng `note IS NULL` không?  
**Đáp án:** Không. SQL NULL dùng phép so sánh ba giá trị; hãy viết `IS NULL` khi đúng mục đích.

**Bài tập 6 — SQL identifier.** `ORDER BY :field` có thay được tên cột do user chọn không?  
**Đáp án:** Không. Bind là value; tên cột phải chọn bằng whitelist mã nguồn.

**Bài tập mở rộng:** Viết một phương thức `discountPrices(List<Long> ids, BigDecimal discount)` để giảm giá các sản phẩm được chọn nhưng giá mới không âm. Dùng `IN (:ids)`, bind `:discount` lặp ở `SET price = price - :discount` và `WHERE price >= :discount`. Guard list rỗng, kiểm tra updated rows, dùng Service `@Transactional` nếu đây là một phần của use case gồm nhiều thao tác. Tự gọi `NamedParameterUtils` để dự đoán số vị trí bind với danh sách 2 IDs, rồi xác minh bằng integration test H2.

## 21. Tài liệu chính thức

- [Spring Framework — Using NamedParameterJdbcTemplate](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html): khác nhau giữa tham số tên và `?`, cách dùng `MapSqlParameterSource`, JavaBean source, và việc ủy quyền cho JdbcTemplate.
- [NamedParameterJdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html): contract, các overload `query`/`update`, cache parse và `getJdbcOperations()`.
- [NamedParameterUtils API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterUtils.html): `parseSqlStatement`, `substituteNamedParameters`, `buildValueArray` và mở rộng danh sách.
- [Spring Framework — Passing in Lists of Values for IN Clause](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): cách list biến thành nhiều placeholder và lưu ý giới hạn DBMS.
- [SqlParameterSource API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/namedparam/SqlParameterSource.html): hợp đồng tra cứu value và SQL type theo tên.
- [Spring Framework — JdbcClient](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html): fluent API kết hợp thao tác named và indexed parameters.

## 22. Ghi nhớ cuối bài

1. **`:name` là cú pháp của Spring JDBC**, không phải placeholder chuẩn của JDBC driver. Spring chuyển SQL sang các **`?`** trước khi PreparedStatement thực thi.
2. Mỗi **lần xuất hiện** của `:name` thường tạo một vị trí bind riêng, dù nhiều lần dùng cùng một key.
3. **Thứ tự SQL** quyết định thứ tự JDBC; **thứ tự chèn key vào Map không quyết định** thứ tự bind.
4. `IN (:ids)` với list được mở rộng thành số `?` tương ứng; phải xử lý list rỗng và giới hạn số phần tử.
5. **Tên tham số chỉ thay dữ liệu**, không thể thay tên bảng/cột hoặc SQL fragment. Luôn bind value để bảo vệ chống injection.
6. `MapSqlParameterSource` bổ sung metadata SQL type/typed null; `BeanPropertySqlParameterSource` dùng JavaBean properties khi phù hợp.
7. `NamedParameterJdbcTemplate` hỗ trợ cú pháp dễ đọc hơn nhưng vẫn dựa vào `JdbcTemplate`, JDBC driver, DataSource và Spring transaction.

**Kết luận:** Đọc `:name` như “**điền value tương ứng vào từng vị trí của PreparedStatement**”, không phải “thay text để tạo SQL mới có literal”. Khi hiểu rõ chuỗi **parse → đổi placeholder → xác định thứ tự/kiểu → bind → execute**, bạn sẽ viết, kiểm tra và gỡ lỗi các truy vấn Spring JDBC có tên tham số một cách chính xác và an toàn.

# Chọn kiểu kết quả hoặc RowMapper trong Spring JdbcClient

## 1. Vấn đề: khi nào chỉ định Class, khi nào tự viết RowMapper?

`JdbcClient` là API fluent được giới thiệu từ **Spring Framework 6.1**, thuộc package `org.springframework.jdbc.core.simple`. Nó giúp viết truy vấn, bind tham số và chọn kết quả trên nền tảng Spring JDBC. Sau `sql(...)` và các lời gọi `param(...)`, bạn thường gặp hai cách ánh xạ:

```java
// Ánh xạ tự động theo class/record:
List<Product> products = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        ORDER BY id
        """)
    .query(Product.class)
    .list();

// Ánh xạ rõ ràng bằng callback RowMapper:
List<Product> products2 = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        ORDER BY id
        """)
    .query((rs, rowNum) -> new Product(
        rs.getLong("id"),
        rs.getString("product_name"),
        rs.getInt("quantity")))
    .list();
```

Hai đoạn trên **chỉ là snippet minh họa**: giả định có `JdbcClient jdbcClient` và Java record/class `Product` phù hợp. Chương trình Java 17 chạy độc lập ở phần 9 sử dụng tên file, import và cấu trúc hoàn chỉnh.

**Câu hỏi chính của bài:** nên dùng `query(Class<T>)` để Spring tự map, hay `query(RowMapper<T>)` để bạn quyết định từng cột? Câu trả lời phụ thuộc vào **hình dạng kết quả**, **mức độ khớp giữa tên cột và Java property**, **quy tắc chuyển đổi giá trị** và **trách nhiệm kiểm thử** — không phải cách nào “mới hơn” hoặc “chạy nhanh hơn” theo cảm tính.

Sau bài, bạn phải:

1. Giải thích pipeline `sql(...).param(...).query(...).list()/single()/optional()`.
2. Phân biệt `query(Integer.class)` cho một cột scalar với `query(MyRecord.class)` cho một dòng nhiều cột.
3. Dùng `query(MyClass.class)` cho JavaBean, record, field holder có tên/kiểu tương thích.
4. Dùng `query(RowMapper<T>)` khi alias khác tên, cần logic chuyển đổi, NULL handling, enum, JOIN hoặc cấu trúc kết quả riêng.
5. Chọn `list()`, `set()`, `single()`, `optional()`, `stream()` đúng cardinality và lifecycle; biết lỗi khi 0 hoặc nhiều dòng.
6. Phân biệt `query()` không mapper (Map, column, rowSet) với `query(Class)` và `query(RowMapper)`.
7. Chạy ví dụ Java 17 + Spring JDBC + H2, kiểm tra stdout, và tự làm bài tập mở rộng.

**Phạm vi:** ánh xạ kết quả của `JdbcClient`. Việc mở transaction, quản lý pool, batch và stored procedure chỉ đề cập khi giúp xác định ranh giới của API.

## 2. Hình dung ba bước xử lý

```text
JdbcClient.sql(SQL)
       │
       ├─ .param(name, value), .param(value), .paramSource(...)
       │        → định nghĩa bind values
       ▼
 .query(Class<T>)            .query(RowMapper<T>)         .query()
       │                           │                        │
       │ tự chọn mapper             │ callback tự đọc rs      │ không chọn kiểu DTO
       │ cho scalar / property      │ cho từng dòng           │ trả row map / column / rowSet
       ▼                           ▼                        ▼
 MappedQuerySpec<T>          MappedQuerySpec<T>           ResultQuerySpec
       │                           │                        │
       ├─ list()                   ├─ list()                 ├─ listOfRows()
       ├─ single()                 ├─ single()               ├─ singleRow()
       ├─ optional()               ├─ optional()             ├─ singleColumn()
       ├─ set()                    ├─ set()                  ├─ singleValue()
       └─ stream()                 └─ stream()               └─ rowSet()
```

Phân biệt **hai quyết định độc lập**:

- **Ánh xạ một dòng sang kiểu nào?** Được quyết định ở `query(Class<T>)` hoặc `query(RowMapper<T>)`.
- **Trả về bao nhiêu dòng và dưới cấu trúc nào?** Được quyết định ở `list()`, `single()`, `optional()`, `set()` hoặc `stream()`.

Vì thế `query(Product.class).list()` và `query(Product.class).single()` dùng cùng cách chuyển một dòng thành `Product`, nhưng khác **hợp đồng số lượng dòng**. `query(Product.class)` không tự động chọn một dòng đầu tiên; method terminal mới quyết định.

`JdbcClient` không phải ORM: nó không tự tạo `SELECT` cho entity, không theo dõi trạng thái đối tượng, không lazy-load association, không tự tính join hoặc persist object. Bạn vẫn viết SQL và chịu trách nhiệm chọn cột, alias, WHERE, ORDER BY và ranh giới nghiệp vụ.

## 3. query(Class<T>): ánh xạ tự động theo lớp kết quả

### 3.1. Một cột scalar

Với SQL đúng **một cột và một dòng**:

```java
int total = jdbcClient.sql("SELECT COUNT(*) FROM products")
        .query(Integer.class)
        .single();
```

`Integer.class` là một **kiểu giá trị đơn**. `JdbcClient` dùng cơ chế ánh xạ một cột (tương ứng `SingleColumnRowMapper`) để chuyển kết quả JDBC thành kiểu được yêu cầu. Bạn cũng có thể chọn `Long.class`, `String.class`, `BigDecimal.class` hoặc kiểu được Spring/driver hỗ trợ phù hợp, nhưng không giả định mọi kiểu có thể được chuyển từ mọi SQL type.

Ví dụ một giá trị chuỗi:

```java
String sku = jdbcClient.sql("""
        SELECT sku
        FROM products
        WHERE id = :id
        """)
    .param("id", 11L)
    .query(String.class)
    .single();
```

Đây là snippet trong class đã có `JdbcClient` và bảng `products`. Nếu SQL trả **hai cột**, `query(String.class)` không phải cách lấy một dòng vào String; các mapper scalar thường yêu cầu đúng một cột và sẽ báo lỗi khi shape không tương thích.

### 3.2. Nhiều cột vào record

Giả sử record:

```java
public record Product(
        long id,
        String productName,
        int quantity) {}
```

SQL xuất column labels tương ứng:

```sql
SELECT id,
       product_name,
       quantity
FROM products
ORDER BY id;
```

Khi gọi:

```java
List<Product> items = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        ORDER BY id
        """)
    .query(Product.class)
    .list();
```

Spring JDBC có thể dùng cơ chế **`SimplePropertyRowMapper`** để ánh xạ cột vào record/class. Mapper này hỗ trợ constructor có parameter names thích hợp, bean setter và các trường (field) tương ứng, không chỉ JavaBean có setter. Spring có hỗ trợ quy ước đối chiếu `product_name` với `productName`; tuy nhiên bạn phải **kiểm tra bằng integration test với đúng SQL/driver/type** thay vì tin rằng mọi alias đều được suy ra.

Yêu cầu quan trọng:

- Tên label cột phải khớp tên parameter/property theo quy tắc mapper; alias là cách rõ nhất để điều chỉnh.
- Constructor và field types cần tương thích với giá trị JDBC thực tế.
- Class được map nên là class top-level hoặc `static` nested, không phải non-static inner class yêu cầu enclosing instance.
- Record là immutable; mapper tạo object mới cho từng dòng, không cập nhật lại bản ghi khi database thay đổi.
- Không có bảo đảm tự xử lý cấu trúc nested object, collection, one-to-many hay object graph như ORM.

### 3.3. JavaBean và field holder

Không bắt buộc dùng record. Ví dụ JavaBean:

```java
public static class ProductBean {
    private Long id;
    private String productName;

    public ProductBean() {}

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getProductName() { return productName; }
    public void setProductName(String productName) {
        this.productName = productName;
    }
}
```

SQL `SELECT id, product_name FROM products` có thể ánh xạ sang `ProductBean.class`. `SimplePropertyRowMapper` cũng hỗ trợ trường tương ứng trong một field holder phù hợp; đó là một điểm khác với `BeanPropertyRowMapper` thuần thường dựa trên JavaBean setters.

**Thứ tự ưu tiên** khi cùng đối tượng có constructor property, setter và field phù hợp: constructor argument được ưu tiên, sau đó setter, rồi field mapping. Không dựa vào những đường fallback phức tạp để che một class không rõ contract; nếu DTO có nhiều cách tạo/ghi cùng field, cần test chính xác.

### 3.4. Alias là hợp đồng, không phải phép thuật

Một SQL:

```sql
SELECT p.id AS product_id,
       p.name AS display_name,
       p.stock_quantity AS quantity
FROM products p;
```

record dự kiến:

```java
record ProductView(long productId, String displayName, int quantity) {}
```

Tên alias `product_id`, `display_name`, `quantity` cho phép mapper liên hệ đến components `productId`, `displayName`, `quantity` theo quy ước. Ngược lại, nếu SQL xuất `p.name AS title` nhưng record chỉ có `displayName`, mapper sẽ không tự hiểu `title` đồng nghĩa với `displayName`.

**Cách sửa:** đổi alias thành tên có thể map, đổi DTO, hoặc viết `RowMapper` thủ công. Với JOIN hoặc query aggregate, luôn đặt alias rõ/duy nhất thay vì `SELECT *`.

## 4. query(RowMapper<T>): tự quyết định cách map một dòng

`RowMapper<T>` là callback với phương thức `mapRow(ResultSet rs, int rowNum)`. Spring đã đưa con trỏ `ResultSet` đến dòng hiện tại trước khi gọi callback; mapper chỉ cần đọc các cột và trả về đối tượng.

```java
RowMapper<ProductView> mapper = (rs, rowNum) -> {
    long id = rs.getLong("product_id");
    String title = rs.getString("display_name");
    int quantity = rs.getInt("quantity");
    return new ProductView(id, title, quantity);
};

List<ProductView> products = jdbcClient.sql("""
        SELECT p.id AS product_id,
               p.name AS display_name,
               p.stock_quantity AS quantity
        FROM products p
        ORDER BY p.id
        """)
    .query(mapper)
    .list();
```

Đây là snippet độc lập về ý tưởng, cần record `ProductView` và bảng tương ứng. Khi bạn cần kiểm soát:

- Cột nào đọc (tên label hay vị trí 1-based).
- Kiểu Java: `getBigDecimal`, `getObject(..., LocalDate.class)` hoặc mapping driver-specific.
- Logic chuyển đổi như `"A" → Status.ACTIVE`, số tiền cent → đơn vị tiền nghiệp vụ, ghép/hủy định dạng có chủ đích.
- Giá trị null: `rs.wasNull()` hoặc getter object nullable.
- Alias/kiểu không tương ứng 1-1 với property Java.
- Ánh xạ một hàng phức tạp nhưng vẫn giữ DTO immutable.

thì `RowMapper` thường dễ đọc, dễ test và rõ trách nhiệm hơn một loạt alias đặc thù chỉ để ép mapper tự động.

### 4.1. Không làm gì trong RowMapper?

**Không** gọi `rs.next()`, `rs.close()` hoặc đóng connection/statement do Spring cấp. `JdbcClient` sử dụng hạ tầng `JdbcTemplate`/`NamedParameterJdbcTemplate` để điều phối tài nguyên. `rowNum` bắt đầu từ 0 và là **số thứ tự hàng**; `rs.getString(1)` lại dùng index **cột** bắt đầu từ 1.

```java
// SAI: đây chỉ là minh họa anti-pattern, không được chạy.
(rs, rowNum) -> {
    rs.next();              // Template đã di chuyển ResultSet.
    return rs.getString(rowNum); // rowNum=0 ở dòng đầu; column index bắt đầu 1.
}
```

Không trả `ResultSet`, `InputStream` gắn cursor hoặc `PreparedStatement` ra khỏi mapper. Nếu cần dữ liệu sau lời gọi `list()` hoặc `single()`, hãy chuyển thành object Java độc lập **trong callback**.

### 4.2. Tránh side effect và N+1 query trong mapper

Không nên:

- Gọi một truy vấn khác cho mỗi dòng chỉ để điền thêm property (N+1 query).
- Ghi dữ liệu vào database hoặc gọi HTTP endpoint trong mapper.
- Dùng mutable state dùng chung giữa nhiều thread/request.
- Nuốt `SQLException` rồi trả object thiếu dữ liệu.
- Thực hiện business rule nặng khiến callback giữ tài nguyên JDBC rất lâu.

Nếu một DTO cần dữ liệu từ hai bảng, cân nhắc JOIN/projection thích hợp và map một hàng rõ ràng; nếu cần nhóm nhiều hàng thành một cấu trúc phức tạp, `ResultSetExtractor` có thể phù hợp hơn `RowMapper`.

## 5. Bảng quyết định: class hay RowMapper?

| Tình huống | Nên bắt đầu với | Lý do |
| --- | --- | --- |
| `SELECT COUNT(*)`, một giá trị số | `query(Integer.class).single()` | Mapping scalar một cột |
| `SELECT name ...`, một String | `query(String.class)` | Không cần DTO/mapper riêng |
| Record có tên/kiểu khớp column labels | `query(MyRecord.class)` | Ít code, constructor mapping |
| JavaBean đơn giản có setters | `query(MyBean.class)` | Tận dụng property mapping |
| Class chỉ có fields với tên phù hợp | `query(MyClass.class)` nếu hỗ trợ constructor/field hợp lệ | SimplePropertyRowMapper xử lý cấu trúc đơn giản |
| JOIN có alias ổn định và DTO trùng | `query(MyDto.class)` | Mapping tự động nếu contract khớp |
| JOIN nhiều id trùng, alias không thống nhất | `query(RowMapper<T>)` sau khi alias hóa SQL | Kiểm soát rõ cột đọc |
| SQL NULL phải phân biệt với 0/false | `query(RowMapper<T>)` hoặc wrapper DTO thích hợp | Kiểm soát semantics |
| Decimal tiền tệ / enum / chuyển đổi nghiệp vụ | `query(RowMapper<T>)` | Chuyển kiểu tường minh |
| Một hàng cần ghép nhiều trường thành giá trị mới | `query(RowMapper<T>)` | Tách SQL projection khỏi transformation |
| Nhiều dòng gom thành một aggregate phức tạp | `query(ResultSetExtractor<T>)` | Điều khiển toàn bộ ResultSet |
| Chỉ cần Map/rowset để inspect linh hoạt | `query().listOfRows()` / `rowSet()` | Không cần DTO cố định |

Tốc độ của một phương án phụ thuộc truy vấn, driver, số dòng, cấu trúc DTO, conversion và môi trường. **Không kết luận mapper thủ công luôn nhanh hơn** hoặc mapper tự động luôn an toàn hơn. Hãy đo nếu throughput là yêu cầu; mặc định ưu tiên cách rõ, ổn định và có test.

## 6. Chọn số lượng kết quả: list, single, optional, set, stream

Sau `query(Class<T>)` hoặc `query(RowMapper<T>)`, bạn nhận `JdbcClient.MappedQuerySpec<T>`. Có các cách terminal quan trọng:

### 6.1. list(): 0..N dòng

```java
List<Product> products = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        ORDER BY id
        """)
    .query(Product.class)
    .list();
```

- Trả `List<T>` đã được map; không có dòng thì danh sách rỗng.
- Các dòng giữ thứ tự mà database trả về. Nếu thứ tự có ý nghĩa, **SQL phải có `ORDER BY`**.
- `list()` materialize tất cả dòng vào bộ nhớ; không nên đọc bảng rất lớn không giới hạn khi chỉ cần vài trang.

### 6.2. single(): đúng một giá trị đối tượng, không null ở Spring 6.2

```java
Product product = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        WHERE id = :id
        """)
    .param("id", 10L)
    .query(Product.class)
    .single();
```

Hợp đồng cần nhớ:

- **Đúng một** đối tượng được yêu cầu.
- **Không có dòng** thường dẫn tới `EmptyResultDataAccessException`.
- **Nhiều hơn một dòng** dẫn tới `IncorrectResultSizeDataAccessException` (hoặc subtype phù hợp).
- Từ Spring **6.2**, `single()` yêu cầu giá trị map **không null**; nếu callback trả null, đừng coi đây là cách nhận optional nullable. Hãy thiết kế mapper/DTO tương ứng.

`WHERE id = :id` chỉ bảo đảm tối đa một dòng nếu cột `id` là unique/primary key. Không dùng `single()` trên query không unique rồi kỳ vọng Spring âm thầm lấy dòng đầu.

### 6.3. optional(): 0 hoặc 1 đối tượng

```java
Optional<Product> found = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        WHERE id = :id
        """)
    .param("id", 999L)
    .query(Product.class)
    .optional();
```

- Không có kết quả → `Optional.empty()`.
- Có đúng một object không null → `Optional.of(object)`.
- Có nhiều kết quả → **lỗi**, không âm thầm lấy một dòng.
- Nếu mapper trả null thì Optional không biểu diễn được “có dòng nhưng giá trị null” khác biệt rõ ràng; với truy vấn nullable scalar, chọn wrapper/contract dữ liệu rõ ràng.

**Khi nào chọn?** Repository tìm theo unique key mà “không tồn tại” là trạng thái bình thường: dùng `Optional<T>`. Khi không tồn tại là lỗi nghiệp vụ/hợp đồng, dùng `single()` và xử lý exception phù hợp.

### 6.4. set(): tập không trùng phần tử

```java
Set<String> categories = jdbcClient.sql("""
        SELECT category
        FROM products
        ORDER BY category
        """)
    .query(String.class)
    .set();
```

Theo Javadoc, `set()` trả set có thứ tự theo thứ tự kết quả, thường dựa vào `LinkedHashSet`. **Không** nhầm với SQL `SELECT DISTINCT`:

- SQL có thể trả nhiều hàng trùng; `Set` khử trùng theo `equals()/hashCode()` của object Java **sau mapping**.
- Hai record khác nhau về một field là hai phần tử khác nhau.
- Nếu cần distinct tại database vì hiệu năng, sử dụng `SELECT DISTINCT` hoặc `GROUP BY` phù hợp.
- Dù set duy trì thứ tự đã đọc, không có `ORDER BY` thì thứ tự nguồn vốn không được bảo đảm.

### 6.5. stream(): lazy, phải đóng

```java
try (Stream<Product> stream = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        ORDER BY id
        """)
    .query(Product.class)
    .stream()) {

    long lowStock = stream.filter(p -> p.quantity() < 5).count();
    System.out.println(lowStock);
}
```

`Stream<T>` từ Spring JDBC có thể giữ JDBC `ResultSet`, `Statement`, `Connection` đến khi stream được đóng. Người gọi **phải dùng `try-with-resources` hoặc đóng rõ ràng** kể cả khi đã gọi terminal operation `count()`, `findFirst()`, hoặc pipeline dừng giữa chừng.

**Không trả JDBC stream qua ranh giới service/request rồi quên giao trách nhiệm đóng.** Với workload lớn, kết hợp paging/cursor và transaction phù hợp theo khả năng driver; `stream()` không tự giải quyết toàn bộ vấn đề bộ nhớ hoặc locks.

### Ma trận cardinality

| Kết quả thực của SQL | `list()` | `single()` | `optional()` | `set()` |
| --- | --- | --- | --- | --- |
| 0 dòng | Empty list | Lỗi không tìm thấy | `Optional.empty()` | Empty set |
| 1 dòng, object khác null | List 1 phần tử | Trả object | `Optional.of(object)` | Set 1 phần tử |
| Nhiều dòng | List nhiều phần tử | Lỗi không đúng số dòng | Lỗi không đúng số dòng | Set, loại trùng theo Java equality |
| 1 dòng, mapped object null | Phụ thuộc contract mapper và nullability | Không chấp nhận như required value (6.2) | Optional không phân biệt được row-null và no row | Cần tránh/định nghĩa null semantics rõ |

Bảng đề cập hợp đồng chung, không có nghĩa nên cố tình map hàng thành null. Trong mã nghiệp vụ, row mapper nên trả object có nghĩa; với SQL NULL scalar, chọn wrapper/`optionalValue()` hoặc cách xử lý riêng sau khi xác định semantics.

## 7. query() không truyền mapper: các dạng kết quả khác

`jdbcClient.sql(...).query()` trả `ResultQuerySpec`, không phải `MappedQuerySpec<T>`. Nó có các phương thức khác:

```java
// Các snippet riêng, giả sử đã có biến jdbcClient và bảng products.
List<Map<String, Object>> rows = jdbcClient.sql("""
        SELECT id AS product_id, product_name
        FROM products
        ORDER BY id
        """)
    .query()
    .listOfRows();

Map<String, Object> row = jdbcClient.sql("""
        SELECT id AS product_id, product_name
        FROM products
        WHERE id = :id
        """)
    .param("id", 10L)
    .query()
    .singleRow();

Object count = jdbcClient.sql("SELECT COUNT(*) FROM products")
    .query()
    .singleValue();
```

**Một số lựa chọn từ `ResultQuerySpec`:**

| API | Kết quả | Thích hợp |
| --- | --- | --- |
| `listOfRows()` | `List<Map<String,Object>>` | Dữ liệu động/đọc nhanh, không cần DTO |
| `singleRow()` | `Map<String,Object>` | Một hàng, nhiều cột |
| `singleColumn()` | `List<Object>` | Một cột, nhiều hàng |
| `singleValue()` | `Object` | Một hàng, một cột, giá trị bắt buộc |
| `optionalValue()` (Spring 6.2+) | `Optional<Object>` | Giá trị đơn có thể vắng |
| `rowSet()` | `SqlRowSet` detached | Truy cập kiểu rowset không cần tự cầm JDBC ResultSet |

**Lưu ý:** Map result dùng key theo column label, thường có khả năng tra cứu không phân biệt hoa/thường, nhưng nên tránh alias trùng và không tự đoán kiểu Java của `Object`. Nếu API công khai cần kiểu mạnh, class hoặc RowMapper thường rõ hơn.

Đừng nhầm `query().singleValue()` với `query(Integer.class).single()`: cái đầu trả `Object` cần xác định kiểu, cái sau dùng scalar mapper typed. Cũng đừng nhầm `singleRow()` (Map một hàng) với `single()` (object kiểu `T`). Các phương thức ở phần này **không đồng thời tồn tại trên cùng một spec**; viết đúng đường gọi.

## 8. Trường hợp query(RowCallbackHandler) hoặc query(ResultSetExtractor)

`JdbcClient.StatementSpec` còn có các overload nhận callback:

```java
// Xử lý lần lượt từng dòng, không phải ánh xạ ra List<T>.
jdbcClient.sql("SELECT id, sku FROM products ORDER BY id")
    .query((RowCallbackHandler) rs ->
        System.out.println(rs.getString("sku")));

// Tổng hợp toàn bộ ResultSet thành một kết quả tùy ý.
Long sum = jdbcClient.sql("SELECT quantity FROM products")
    .query((ResultSetExtractor<Long>) rs -> {
        long total = 0;
        while (rs.next()) {
            total += rs.getLong("quantity");
        }
        return total;
    });
```

Đây là snippet minh họa, cần import `RowCallbackHandler` và `ResultSetExtractor` tương ứng.

- **`RowMapper`**: template gọi mỗi lần **một dòng**, mapper đọc dòng hiện tại, trả một `T`.
- **`RowCallbackHandler`**: template gọi mỗi lần một dòng, callback xử lý side effect có kiểm soát; template quản lý `rs.next()`.
- **`ResultSetExtractor<T>`**: callback xử lý **toàn bộ ResultSet**, tự gọi `rs.next()` và trả một kết quả tổng hợp duy nhất.
- **Không** tự đóng `ResultSet` được template đưa vào các callback tiêu chuẩn.

Nếu chỉ cần DTO theo từng hàng, đừng chọn `ResultSetExtractor` vì “linh hoạt hơn”: nó tăng trách nhiệm manual iteration. Chọn callback đúng với **hình dạng dữ liệu trả về**, không chỉ với cú pháp ngắn nhất.

## 9. Bài thực hành Java 17 chạy độc lập với H2

Ví dụ dùng **Java 17+**, **Spring Framework 6.2.14**, **H2 2.3.232** và Gradle. Chương trình sử dụng Spring Framework thuần, **không cần Spring Boot** hay database cài ngoài. Version được cố định để người học biết contract đang dựa trên bản nào.

### 9.1. Cấu trúc

```text
jdbc-client-result-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/JdbcClientResultDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'jdbc-client-result-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.JdbcClientResultDemo'
}
```

`src/main/java/demo/JdbcClientResultDemo.java`:

```java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Stream;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class JdbcClientResultDemo {

    record InventoryItem(long id, String sku, int quantity) {}

    record InventoryBadge(String sku, String status) {}

    @Configuration
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:client_result;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        JdbcClient jdbcClient(JdbcTemplate jdbcTemplate) {
            // Tái sử dụng cấu hình của JdbcTemplate hiện có.
            return JdbcClient.create(jdbcTemplate);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            JdbcClient client = context.getBean(JdbcClient.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE inventory (
                        id BIGINT PRIMARY KEY,
                        sku VARCHAR(40) NOT NULL,
                        quantity INTEGER NOT NULL
                    )
                    """);

            client.sql("""
                    INSERT INTO inventory(id, sku, quantity)
                    VALUES (:id, :sku, :quantity)
                    """)
                .param("id", 1L)
                .param("sku", "PEN")
                .param("quantity", 12)
                .update();

            client.sql("""
                    INSERT INTO inventory(id, sku, quantity)
                    VALUES (:id, :sku, :quantity)
                    """)
                .param("id", 2L)
                .param("sku", "NOTE")
                .param("quantity", 0)
                .update();

            client.sql("""
                    INSERT INTO inventory(id, sku, quantity)
                    VALUES (:id, :sku, :quantity)
                    """)
                .param("id", 3L)
                .param("sku", "BAG")
                .param("quantity", 5)
                .update();

            // 1) Tự map các cột vào Java record.
            List<InventoryItem> typed = client.sql("""
                    SELECT id, sku, quantity
                    FROM inventory
                    ORDER BY id
                    """)
                .query(InventoryItem.class)
                .list();
            System.out.println("typed=" +
                    typed.stream().map(InventoryItem::sku).toList());

            // 2) RowMapper thủ công tạo cùng model.
            RowMapper<InventoryItem> explicit = (rs, rowNum) ->
                    new InventoryItem(
                            rs.getLong("id"),
                            rs.getString("sku"),
                            rs.getInt("quantity"));
            List<InventoryItem> manual = client.sql("""
                    SELECT id, sku, quantity
                    FROM inventory
                    ORDER BY id
                    """)
                .query(explicit)
                .list();
            System.out.println("manualEqual=" + typed.equals(manual));

            // 3) Mapper thủ công biến quantity thành trạng thái.
            List<InventoryBadge> badges = client.sql("""
                    SELECT sku, quantity
                    FROM inventory
                    ORDER BY id
                    """)
                .query((rs, rowNum) -> new InventoryBadge(
                        rs.getString("sku"),
                        rs.getInt("quantity") > 0
                                ? "READY" : "EMPTY"))
                .list();
            System.out.println("badges=" +
                    badges.stream()
                          .map(x -> x.sku() + ":" + x.status())
                          .toList());

            // 4) Scalar result: một hàng, một cột.
            Integer total = client.sql("SELECT COUNT(*) FROM inventory")
                    .query(Integer.class)
                    .single();
            System.out.println("total=" + total);

            String firstSku = client.sql("""
                    SELECT sku FROM inventory WHERE id = ?
                    """)
                .param(1L)
                .query(String.class)
                .single();
            System.out.println("firstSku=" + firstSku);

            // 5) Required single và Optional: khác khi không có dòng.
            InventoryItem required = client.sql("""
                    SELECT id, sku, quantity
                    FROM inventory
                    WHERE id = :id
                    """)
                .param("id", 2L)
                .query(InventoryItem.class)
                .single();
            System.out.println("required=" + required.sku());

            Optional<InventoryItem> missing = client.sql("""
                    SELECT id, sku, quantity
                    FROM inventory
                    WHERE id = :id
                    """)
                .param("id", 999L)
                .query(InventoryItem.class)
                .optional();
            System.out.println("missingPresent=" + missing.isPresent());

            // 6) list() cho 0..N dòng có tham số tên.
            List<InventoryItem> lowStock = client.sql("""
                    SELECT id, sku, quantity
                    FROM inventory
                    WHERE quantity <= :maxQty
                    ORDER BY id
                    """)
                .param("maxQty", 3)
                .query(InventoryItem.class)
                .list();
            System.out.println("lowStock=" +
                    lowStock.stream().map(InventoryItem::sku).toList());

            // 7) Không truyền mapper: nhận các map của cột SQL.
            List<Map<String, Object>> rows = client.sql("""
                    SELECT id AS item_id, sku AS item_sku
                    FROM inventory
                    WHERE id = :id
                    """)
                .param("id", 1L)
                .query()
                .listOfRows();
            System.out.println("rowMaps=" + rows.size());

            // 8) Stream giữ JDBC resources nên phải close.
            long inStock;
            try (Stream<InventoryItem> stream = client.sql("""
                    SELECT id, sku, quantity
                    FROM inventory
                    ORDER BY id
                    """)
                .query(InventoryItem.class)
                .stream()) {
                inStock = stream.filter(item -> item.quantity() > 0).count();
            }
            System.out.println("streamAvailable=" + inStock);
        }
    }
}
```

### 9.2. Chạy

Ở thư mục có `build.gradle`, chạy bằng Gradle với Java 17 toolchain:

```bash
gradle run
```

Nếu đã tạo Gradle Wrapper: Linux/macOS dùng `./gradlew run` và Windows dùng `gradlew.bat run`. Các dòng **do chính chương trình in bằng `System.out`** (bỏ qua log Gradle/Spring) được dự kiến là:

```text
typed=[PEN, NOTE, BAG]
manualEqual=true
badges=[PEN:READY, NOTE:EMPTY, BAG:READY]
total=3
firstSku=PEN
required=NOTE
missingPresent=false
lowStock=[NOTE]
rowMaps=1
streamAvailable=2
```

### 9.3. Vì sao kết quả như vậy?

- Ba `INSERT` tạo các sản phẩm `PEN(12)`, `NOTE(0)` và `BAG(5)`, `ORDER BY id` giữ thứ tự đọc. `typed=[PEN, NOTE, BAG]` cho thấy record được map qua `InventoryItem.class`.
- `manualEqual=true` chứng minh với projection này, việc tự đọc ba cột bằng `RowMapper` cho cùng các record (Java record có value equality theo components).
- `badges` cho thấy lý do cần mapper thủ công: SQL không có cột `status` nhưng callback **tính** `READY` hoặc `EMPTY` từ `quantity`.
- `COUNT(*)` trả một scalar nên `query(Integer.class).single()` là đủ; `total=3`.
- `firstSku=PEN` sử dụng `?` positional binding, khác với `:id` named binding ở lệnh khác. Hai kiểu binding đều được `JdbcClient` hỗ trợ.
- Query `WHERE id=2` khớp đúng một dòng nên `single()` trả `NOTE`; query `id=999` không có dòng nên `optional().isPresent()` là false.
- `lowStock` lọc `quantity <= 3` nên chỉ có `NOTE`.
- `query().listOfRows()` cho truy vấn `id=1` trả một map hàng, nên `rowMaps=1`.
- Stream đọc ba dòng, lọc số lượng lớn hơn 0 được hai dòng, và được **đóng trong `try-with-resources`**.

### 9.4. Giới hạn của bản demo

Ví dụ dùng `DriverManagerDataSource` **không pooling** để giảm số dependency; đây không phải lựa chọn mặc định cho production chịu tải. H2 in-memory giúp thao tác nhanh, nhưng khả năng chuyển kiểu, precision, SQL dialect và naming có thể khác PostgreSQL/MySQL/Oracle. Đối với dịch vụ thật, dùng connection pool được quản lý tốt, cấu hình secrets ngoài mã nguồn và chạy integration test với database tương thích production.

Bài demo là **console application**, không có `@Transactional`. `JdbcClient` tái sử dụng hạ tầng quản lý connection/exception của Spring JDBC nhưng không tự biến nhiều lệnh `update()` thành một transaction nghiệp vụ.

## 10. Những lỗi phổ biến khi chọn Class<T>

### 10.1. Scalar nhưng SQL có nhiều cột

```java
// SAI: kết quả là 2 cột, không thể đọc toàn bộ vào String.
String value = jdbcClient.sql(
        "SELECT sku, quantity FROM inventory WHERE id = 1")
    .query(String.class)
    .single();
```

Sửa bằng cách chỉ `SELECT sku`, dùng DTO `InventoryItem/InventoryBadge` hoặc RowMapper phù hợp.

### 10.2. Class property không khớp tên cột

```java
record ProductCard(long productId, String displayName) {}
```

SQL `SELECT id, sku FROM inventory` không có label `product_id` hay `display_name`. Mapper không thể tự hiểu `id` là `productId` và `sku` là `displayName`. Sửa bằng alias:

```sql
SELECT id AS product_id, sku AS display_name
FROM inventory;
```

Hoặc viết RowMapper và truyền chính xác vị trí/label của từng cột. **Không dựa vào cách đặt tên tình cờ được driver suy luận.**

### 10.3. SQL NULL vào primitive

`int quantity` không biểu diễn “chưa biết số lượng” khác với 0. Nếu `quantity` cho phép NULL, chọn `Integer` và mapping phù hợp hoặc xử lý trong RowMapper:

```java
int raw = rs.getInt("quantity");
Integer quantity = rs.wasNull() ? null : raw;
```

Kiểm tra `wasNull()` **ngay sau** getter primitive, vì nó phản ánh lần đọc giá trị gần nhất. Tránh đặt default 0 nếu nghiệp vụ phân biệt SQL NULL và 0 thật.

### 10.4. Enum, JSON và kiểu không phổ biến

Không giả định `query(MyRecord.class)` tự deserialize JSON string thành class phức tạp, tự hiểu enum code, hoặc đổi tiền `BigDecimal` sang kiểu domain đặc biệt. Đối với trường hợp chuyển đổi cần quy tắc nghiệp vụ, viết `RowMapper` riêng (hoặc conversion service được cấu hình đúng theo API và phiên bản đang dùng).

### 10.5. Nhiều bảng có cột trùng tên

`SELECT a.id, b.id` tạo column label trùng; mapper theo tên/alias có thể đọc nhầm. Đặt alias `a.id AS account_id`, `b.id AS owner_id` và ánh xạ rõ. Nếu vẫn dùng `query(Class)`, alias phải tương ứng DTO; nếu logic phức tạp, RowMapper thường rõ hơn.

### 10.6. Chỉ đổi .list thành .single

`single()` không phải `limit(1)`. Nếu query trả nhiều dòng, method này phải phát hiện lỗi cardinality, không lấy đại một dòng. Khi business muốn một dòng “mới nhất”, SQL phải có `ORDER BY ... LIMIT 1` (hoặc cú pháp tương ứng database) và xử lý thiếu dòng.

## 11. Những lỗi phổ biến khi tự viết RowMapper

| Triệu chứng | Nguyên nhân | Sửa |
| --- | --- | --- |
| `ResultSet closed` / thiếu dòng | Mapper gọi `rs.next()` hoặc `rs.close()` | Chỉ đọc dòng hiện tại, để Spring quản lý |
| Đọc nhầm id khi JOIN | Cột cùng label `id` | Alias riêng, đọc theo alias |
| `Column not found` | SQL đổi alias nhưng mapper chưa đổi | Kiểm tra select-list và `ResultSetMetaData.getColumnLabel` |
| Dữ liệu mất dấu phân biệt NULL | `getInt` trả 0 cho SQL NULL | `wasNull()` hoặc wrapper |
| DTO sai dù query chạy | Getter đọc sai index (JDBC index 1-based) | Ưu tiên label, hoặc đồng bộ ordinal |
| Chậm khi nhiều dòng | Query con trong từng `mapRow` | JOIN/batch/paging thay vì N+1 |
| Rò tài nguyên | Trả `ResultSet`/stream gắn cursor ra ngoài | Materialize DTO trong callback; close stream terminal |
| Map trả dữ liệu sai | Bỏ qua lỗi `SQLException` và trả default | Để Spring dịch exception, test trên DB thật |

Nếu mapper cần ghép nhiều hàng thành một object, `ResultSetExtractor` có thể phù hợp hơn: nó tự duyệt `rs.next()` trong callback. `RowMapper` dùng khi **mỗi hàng tương ứng một object**.

## 12. Kiểm thử chọn kết quả theo contract

Đừng chỉ kiểm tra rằng truy vấn “không ném exception”. Hãy kiểm tra cả **shape** và **semantics**:

| Trường hợp test | Cách dựng | Kỳ vọng |
| --- | --- | --- |
| Scalar 1 cột | `SELECT COUNT(*)` | `query(Integer.class).single()` đúng số |
| Scalar nhiều cột | `SELECT sku, quantity` rồi `query(String.class)` | Phát hiện shape không tương thích |
| Record khớp | `SELECT id, sku, quantity` | `query(InventoryItem.class).list()` đủ ba field |
| Record alias khác | `SELECT sku AS item_code` | Mapper/record phải được sửa hoặc dùng RowMapper |
| Tương đương hai mapper | Query cùng select-list | Auto và custom tạo object bằng nhau |
| Custom transform | Số lượng 0 và >0 | Trạng thái `EMPTY`/`READY` đúng |
| Không có dòng | `WHERE id=999` | `optional()` empty, `single()` báo lỗi |
| Nhiều dòng | Query không unique | `single()` và `optional()` đều báo lỗi |
| NULL | Cột nullable + wrapper | Phân biệt null và giá trị mặc định |
| Nhiều dòng lớn | Query có paging/stream | Không tiêu thụ quá nhiều bộ nhớ, stream đóng |
| JOIN | Hai bảng có cột `id` | Alias riêng, không nhầm khóa |
| Database thật | Chạy với driver production | Xác minh alias/case/types/NULL |

### Snippet test cardinality

```java
// Snippet sử dụng trong test có JdbcClient và bảng inventory.
// Đây là hành vi cần assert bằng JUnit/AssertJ, không phải chạy ở main demo.
Optional<InventoryItem> missing = client.sql("""
        SELECT id, sku, quantity
        FROM inventory WHERE id = :id
        """)
    .param("id", -1L)
    .query(InventoryItem.class)
    .optional();

// Assert: missing.isEmpty() == true.
// Cùng query nếu gọi .single() sẽ gặp EmptyResultDataAccessException.
```

Trong kiểm thử integration, sử dụng `assertThatThrownBy` hoặc `assertThrows` của framework test với loại exception phù hợp. Không dùng Java `assert` trong production validation vì mặc định JVM có thể tắt assertions.

## 13. Tổ chức mã repository để dùng bền vững

Ví dụ một repository có `JdbcClient` được constructor-inject:

```java
@Repository
public class InventoryRepository {
    private final JdbcClient client;

    public InventoryRepository(JdbcClient client) {
        this.client = client;
    }

    public Optional<InventoryItem> findById(long id) {
        return client.sql("""
                SELECT id, sku, quantity
                FROM inventory
                WHERE id = :id
                """)
            .param("id", id)
            .query(InventoryItem.class)
            .optional();
    }

    public List<InventoryBadge> findBadges() {
        return client.sql("""
                SELECT sku, quantity
                FROM inventory
                ORDER BY id
                """)
            .query((rs, rowNum) -> new InventoryBadge(
                    rs.getString("sku"),
                    rs.getInt("quantity") > 0 ? "READY" : "EMPTY"))
            .list();
    }
}
```

Đây là **snippet minh họa**, chưa tự biên dịch độc lập: cần `@Repository` import, DTO/record thích hợp, component scan hoặc bean registration, và một bean `JdbcClient`. Chương trình đầy đủ nằm ở mục 9.

**Gợi ý thiết kế:** nếu SQL có contract DTO đơn giản, giữ `query(Class)` gần câu SQL. Nếu mapping cần chuyển đổi, tách `RowMapper` riêng khi logic lặp nhiều nơi hoặc cần unit test riêng. Đừng nhét logic nghiệp vụ phức tạp trong một lambda dài.

### Có cần tạo JdbcClient mới cho mỗi lời gọi?

Không. Có thể định nghĩa một bean singleton `JdbcClient` dùng chung, như demo. Client là facade lên các thao tác JDBC của Spring; không tự giữ một `Connection` dùng chung giữa request. `JdbcClient.create(jdbcTemplate)` tái sử dụng cấu hình `JdbcTemplate` hiện có. Với Spring Boot, có thể có auto-configuration khi các điều kiện và phiên bản tương thích; không tự giả định mọi dự án đã có bean mà không kiểm tra context.

### Giao dịch và lỗi

- `JdbcClient` dùng cơ sở hạ tầng Spring JDBC để lấy/release connection và xử lý `DataAccessException`; có thể tham gia Spring transaction khi được cấu hình.
- `query(Class)` hoặc `query(RowMapper)` chỉ quyết định ánh xạ, **không** quyết định bắt đầu transaction.
- `RowMapper` nên để `SQLException` được Spring xử lý; đừng nuốt lỗi trả DTO giả.
- Với service transaction và nhiều lệnh ghi, dùng `@Transactional` hoặc `TransactionTemplate` theo hạ tầng đã cấu hình.
- Nếu không cần tính năng fluent của JdbcClient hoặc cần callback/batch/stored procedure nâng cao, `JdbcTemplate`/`NamedParameterJdbcTemplate`, `SimpleJdbcInsert`/`SimpleJdbcCall` vẫn là lựa chọn phù hợp.

## 14. Bài tập vận dụng có hướng dẫn

**Bài 1 — Chọn mapper không viết code dư.** Từ bảng `inventory(id,sku,quantity)`, lấy tất cả sku theo id. Dùng `query(String.class).list()` và giải thích vì sao không cần record.

```java
List<String> skus = client.sql("""
        SELECT sku FROM inventory ORDER BY id
        """).query(String.class).list();
```

**Bài 2 — Tạo DTO bằng class.** Định nghĩa `record InventoryItem(long id, String sku, int quantity)`, query ba cột `id, sku, quantity` và gọi `query(InventoryItem.class).list()`. Thử đổi `sku AS product_code`, quan sát contract không còn khớp và sửa lại bằng alias `sku` hoặc một RowMapper rõ ràng.

**Bài 3 — Logic trạng thái.** Với `quantity=0` trả `OUT`, từ 1 đến 4 trả `LOW`, từ 5 trở lên trả `OK`. Viết `RowMapper<InventoryBadge>` và test các ngưỡng 0/1/4/5. Không cố dùng `query(InventoryBadge.class)` khi SQL không có cột status thích hợp.

**Bài 4 — Cardinality.** Gọi `single()` trên query không có bản ghi rồi trên query trả ba bản ghi; ghi nhận exception. Thay bằng `optional()` cho trường hợp zero-or-one và `list()` cho zero-or-many.

**Bài 5 — SQL NULL.** Thêm `discount_percent INTEGER NULL` vào projection; viết record dùng `Integer` và row mapper xử lý `rs.getInt` + `wasNull()`. Nếu dùng tự động `query(Class)`, kiểm tra output/null trên driver thực tế.

**Bài 6 — Stream lifecycle.** Lấy `stream()` rồi `findFirst()`. Giải thích vì sao dù pipeline dừng sớm vẫn phải `close()` stream. Sửa code bằng `try-with-resources`.

**Bài 7 — Map hay DTO?** Cho một query admin có tập cột động, cân nhắc `query().listOfRows()`; cho API public có schema cố định, chọn record/RowMapper và giải thích kiểm soát kiểu/alias.

## 15. Checklist review code trước khi merge

1. Truy vấn có trả **một cột** hay **nhiều cột**? Có đang dùng scalar class cho nhiều cột không?
2. Class/record có property/constructor name khớp column labels không? `snake_case`/`camelCase` có được test?
3. Nếu SQL JOIN/aggregate, các alias có duy nhất và ý nghĩa rõ không?
4. Query có đúng cardinality kỳ vọng của `single()`/`optional()` không?
5. Nếu cần 0..N kết quả, có dùng `list()`/`set()` và `ORDER BY` khi thứ tự quan trọng không?
6. Nếu dùng `stream()`, caller có đóng stream kể cả đường exception/short-circuit không?
7. Nếu dùng RowMapper, callback có tránh `next()`/`close()`/side effect không?
8. Kiểu SQL NULL và Java primitive/wrapper có tương thích không?
9. SQL params có bind qua `param(...)` thay vì nối chuỗi input không đáng tin?
10. Kết quả dạng Map có alias trùng hoặc Java type chưa được kiểm tra không?
11. Có test **chạy SQL thật** với trường hợp 0/1/nhiều dòng, nullable, alias và conversion không?
12. Nếu code phức tạp đến mức mapper nặng, có nên tách thành class/hàm riêng hoặc đổi projection không?

## 16. Tài liệu chính thống

- Spring Framework 6.2 — Unified JDBC Query/Update Operations (`JdbcClient`): https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html
- Spring Framework 6.2 — `JdbcClient` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html
- Spring Framework 6.2 — `JdbcClient.MappedQuerySpec` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html
- Spring Framework 6.2 — `JdbcClient.ResultQuerySpec` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.ResultQuerySpec.html
- Spring Framework 6.2 — `RowMapper` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- Spring Framework 6.2 — `SimplePropertyRowMapper` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/SimplePropertyRowMapper.html

**Kết luận:** `query(Class<T>)` phù hợp khi cấu trúc dữ liệu đơn giản và tên cột tương ứng với kiểu đích. `query(RowMapper<T>)` phù hợp khi cần tự kiểm soát cột, NULL hoặc chuyển đổi giá trị. Chọn `list()`, `single()`, `optional()`, `set()` hay `stream()` theo số dòng và vòng đời dữ liệu; đó là quyết định **khác** với việc chọn mapper.
# Phạm vi từ khóa được JDBC hỗ trợ và giới hạn truy cập quan hệ lồng nhau

Trong **Spring Data Relational JDBC**, repository có thể tạo truy vấn từ tên method bằng cơ chế **derived query**. Bạn viết điều kiện bằng các từ khóa như `IsNull`, `IsNotNull`, `Between`, `Like`, `In`, `True`, `False`, `And` và `Or`; Spring Data phân tích tên method rồi tạo SQL phù hợp với database.

Tuy nhiên, phạm vi query derivation của Spring Data JDBC có giới hạn quan trọng: **điều kiện derived query tập trung vào các property của aggregate root và không tự đi xuyên qua các quan hệ lồng nhau như một ORM có khả năng tự tạo join**. Ví dụ, việc một đơn hàng có danh sách dòng hàng hoặc tham chiếu tới khách hàng không có nghĩa bạn có thể tùy ý viết `findByLinesSku(...)` hay `findByCustomerName(...)`.

Bài học trình bày các nhóm từ khóa thường dùng, cách đọc tên method, những giới hạn khi truy vấn embedded object/child collection/aggregate reference, và các lựa chọn khi cần SQL join hoặc truy vấn dữ liệu lồng nhau.

## 1. Derived query hoạt động như thế nào?

Derived query là truy vấn được suy ra từ tên phương thức repository. Spring Data đọc tên method, xác định property trong domain type, nhận diện operator và xây dựng câu SQL.

Ví dụ:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByLastName(String lastName);

    List<Customer> findByActiveTrue();

    List<Customer> findByEmailIsNull();
}
```

Tên method có thể được phân tích thành các phần:

- **Subject:** mô tả loại thao tác hoặc kết quả, ví dụ `find`, `count`, `exists`, `delete`.
- **`By`:** đánh dấu điểm bắt đầu của predicate.
- **Property path:** tên property trong domain model.
- **Keyword/operator:** điều kiện như `IsNull`, `Between`, `Like`, `In`, `True`.
- **Kết hợp/sắp xếp/giới hạn:** `And`, `Or`, `OrderBy`, `First`, `Top` và các tham số như `Sort`/`Pageable` khi được module hỗ trợ.

Ví dụ `findByLastName(String lastName)` tìm các aggregate root có property `lastName` bằng giá trị truyền vào. Property trong method là tên Java property; nó không nhất thiết trùng tên cột SQL.

Nếu domain có:

```java
@Column("last_name")
private String lastName;
```

thì method vẫn viết `findByLastName(...)`, không viết `findByLast_name(...)`.

### 1.1. Derived query không phải tên SQL được viết tắt

Tên method là một ngôn ngữ khai báo theo quy ước Spring Data. Nó không cho phép đặt bất kỳ tên SQL nào vào method.

```java
List<Customer> findByLastName(String lastName);
```

là hợp lệ nếu `lastName` là persistent property và kiểu truy vấn được hỗ trợ.

Nhưng tên như `findByLastNameAndJoinOrders(...)` không có nghĩa Spring sẽ tự hiểu `JOIN orders`. `JoinOrders` không phải một chỉ dẫn join tổng quát trong query derivation.

**Chỉ dùng property và keyword mà Spring Data JDBC có thể phân giải từ domain model.** Khi yêu cầu vượt quá phạm vi đó, hãy chuyển sang SQL tường minh hoặc repository tùy chỉnh.

## 2. Các subject thường gặp

Phần đứng trước `By` thường cho biết loại kết quả hoặc thao tác:

| Subject | Ví dụ | Ý nghĩa |
|---|---|---|
| `find…By` | `findByLastName(...)` | Tìm một hoặc nhiều aggregate |
| `read…By` | `readByActiveTrue()` | Đọc aggregate theo điều kiện |
| `get…By` | `getByEmail(...)` | Đọc theo điều kiện |
| `query…By` | `queryByStatus(...)` | Truy vấn theo điều kiện |
| `count…By` | `countByActiveTrue()` | Đếm số hàng phù hợp |
| `exists…By` | `existsByEmail(...)` | Kiểm tra có hàng phù hợp |
| `delete…By` | `deleteByExpiredTrue()` | Xóa theo điều kiện theo cơ chế repository |
| `remove…By` | `removeByStatus(...)` | Biến thể tên cho thao tác xóa |

Đây là các dạng thường gặp trong hệ sinh thái Spring Data. Subject cụ thể được hỗ trợ và cách xử lý return type cần khớp với phiên bản Spring Data JDBC đang dùng. Với thao tác xóa, cần đọc kỹ kiểu trả về và semantics của repository method; không nên coi một derived delete như câu SQL tùy ý có thể xóa qua mọi quan hệ.

`find`, `read`, `get` và `query` thường được dùng thay nhau cho truy vấn đọc. Hãy chọn một quy ước đặt tên thống nhất trong codebase.

## 3. Các nhóm predicate thường dùng trong Spring Data JDBC

Các từ khóa dưới đây là những nhóm phổ biến khi tạo derived query cho property của aggregate root. Cú pháp và khả năng hỗ trợ chi tiết có thể phụ thuộc phiên bản module; không suy rộng sang những keyword đặc thù của JPA, MongoDB hoặc Elasticsearch.

### 3.1. So sánh bằng và khác

| Keyword | Ví dụ | Ý nghĩa |
|---|---|---|
| Không ghi keyword | `findByStatus(status)` | So sánh bằng |
| `Is` | `findByStatusIs(status)` | So sánh bằng |
| `Equals` | `findByStatusEquals(status)` | So sánh bằng |
| `Not` | `findByStatusNot(status)` | Khác giá trị truyền vào |

Ví dụ:

```java
List<Order> findByStatus(OrderStatus status);

List<Order> findByStatusIs(OrderStatus status);

List<Order> findByStatusNot(OrderStatus status);
```

Ngữ nghĩa SQL minh họa:

```sql
SELECT *
FROM orders
WHERE status = ?;
```

và:

```sql
SELECT *
FROM orders
WHERE status <> ?;
```

Với property nullable, cần nhớ SQL có logic ba giá trị. `status <> 'CANCELLED'` không tự bao gồm hàng có `status IS NULL`, vì phép so sánh với NULL cho kết quả UNKNOWN. Nếu muốn bao gồm null, hãy biểu diễn điều kiện đó riêng bằng `Or...IsNull`.

### 3.2. So sánh khoảng và thứ tự

| Keyword | Ví dụ | Ý nghĩa |
|---|---|---|
| `Between` | `findByPriceBetween(min, max)` | Nằm trong khoảng |
| `LessThan` | `findByPriceLessThan(max)` | Nhỏ hơn |
| `LessThanEqual` | `findByPriceLessThanEqual(max)` | Nhỏ hơn hoặc bằng |
| `GreaterThan` | `findByPriceGreaterThan(min)` | Lớn hơn |
| `GreaterThanEqual` | `findByPriceGreaterThanEqual(min)` | Lớn hơn hoặc bằng |
| `Before` | `findByCreatedAtBefore(time)` | Trước thời điểm |
| `After` | `findByCreatedAtAfter(time)` | Sau thời điểm |

Ví dụ:

```java
List<Product> findByPriceBetween(long minimum, long maximum);

List<Order> findByCreatedAtAfter(LocalDateTime start);

List<Order> findByCreatedAtBefore(LocalDateTime end);
```

SQL tương ứng về ý nghĩa:

```sql
SELECT *
FROM products
WHERE price BETWEEN ? AND ?;
```

`BETWEEN` thường bao gồm cả hai biên. Nếu nghiệp vụ cần khoảng nửa mở như `[start, end)`, có thể viết hai điều kiện `GreaterThanEqual` và `LessThan`, hoặc dùng `@Query` khi cách biểu diễn rõ hơn.

`Before` và `After` thường phù hợp với ngày/giờ hoặc kiểu có thứ tự. Hãy chọn kiểu Java tương thích với cột SQL và quy tắc timezone của ứng dụng.

### 3.3. Kiểm tra NULL

| Keyword | Ví dụ | SQL |
|---|---|---|
| `IsNull` / `Null` | `findByDeletedAtIsNull()` | `deleted_at IS NULL` |
| `IsNotNull` / `NotNull` | `findByDeletedAtIsNotNull()` | `deleted_at IS NOT NULL` |

Ví dụ:

```java
List<Order> findByDeletedAtIsNull();

List<Order> findByDeletedAtIsNotNull();
```

Các method này không nhận tham số vì predicate chỉ kiểm tra trạng thái null của cột.

### 3.4. Điều kiện boolean

| Keyword | Ví dụ | Ý nghĩa |
|---|---|---|
| `True` / `IsTrue` | `findByEnabledTrue()` | Property boolean là true |
| `False` / `IsFalse` | `findByEnabledFalse()` | Property boolean là false |

Ví dụ:

```java
List<UserAccount> findByEnabledTrue();

List<UserAccount> findByEnabledFalse();
```

Nếu property dùng kiểu `Boolean` và database cho phép NULL, có ba trạng thái: `TRUE`, `FALSE`, `NULL`. `findByEnabledFalse()` chỉ tìm FALSE; muốn lấy FALSE hoặc NULL phải viết điều kiện kết hợp.

### 3.5. Điều kiện chuỗi

| Keyword | Ví dụ | Ý nghĩa |
|---|---|---|
| `Like` | `findByNameLike(pattern)` | Dùng pattern LIKE do caller cung cấp |
| `NotLike` | `findByNameNotLike(pattern)` | Phủ định điều kiện LIKE |
| `StartingWith` | `findByNameStartingWith(prefix)` | Chuỗi bắt đầu bằng giá trị |
| `EndingWith` | `findByNameEndingWith(suffix)` | Chuỗi kết thúc bằng giá trị |
| `Containing` | `findByNameContaining(part)` | Chuỗi chứa đoạn giá trị |
| `IgnoreCase` | `findByNameIgnoreCase(name)` | So sánh không phân biệt hoa/thường khi được hỗ trợ |

Ví dụ:

```java
List<Customer> findByNameStartingWith(String prefix);

List<Customer> findByNameEndingWith(String suffix);

List<Customer> findByNameContaining(String fragment);

List<Customer> findByNameLike(String pattern);
```

`Like` thường nhận pattern có ký tự wildcard SQL như `%` và `_`. `StartingWith`, `EndingWith` và `Containing` diễn đạt mục tiêu cụ thể hơn; Spring Data xây dựng pattern phù hợp theo keyword.

Ví dụ SQL về ý nghĩa:

```sql
-- Bắt đầu bằng "An"
WHERE name LIKE 'An%'

-- Kết thúc bằng "son"
WHERE name LIKE '%son'

-- Có chứa "min"
WHERE name LIKE '%min%'
```

Hành vi phân biệt hoa/thường phụ thuộc keyword, dialect, cách tạo biểu thức và collation của database. `IgnoreCase` không phải lời hứa rằng mọi database đều có cùng quy tắc Unicode/collation. Với tìm kiếm tiếng Việt, cần kiểm tra collation và dữ liệu thực tế.

### 3.6. Tập giá trị

| Keyword | Ví dụ | Ý nghĩa |
|---|---|---|
| `In` | `findByStatusIn(statuses)` | Giá trị thuộc tập |
| `NotIn` | `findByStatusNotIn(statuses)` | Giá trị không thuộc tập |

Ví dụ:

```java
List<Order> findByStatusIn(Collection<OrderStatus> statuses);

List<Order> findByStatusNotIn(Collection<OrderStatus> statuses);
```

SQL tương ứng về ý nghĩa:

```sql
SELECT *
FROM orders
WHERE status IN (?, ?, ?);
```

Đầu vào `In`/`NotIn` thường là collection hoặc array phù hợp. Cần xử lý collection rỗng rõ ràng trong nghiệp vụ; SQL `IN ()` không phải cú pháp portable và cách framework xử lý collection rỗng có thể phụ thuộc phiên bản/dialect.

Cũng cần thận trọng khi collection chứa NULL: logic `IN`/`NOT IN` chịu ảnh hưởng của SQL three-valued logic. Nếu cần bao gồm null, hãy thêm predicate `IsNull` rõ ràng.

### 3.7. Kết hợp predicate

`And` và `Or` kết hợp các điều kiện:

```java
List<Order> findByStatusAndCustomerId(
        OrderStatus status,
        Long customerId
);

List<Order> findByStatusOrPriority(
        OrderStatus status,
        int priority
);
```

SQL tương đương về ý nghĩa:

```sql
WHERE status = ?
  AND customer_id = ?;
```

hoặc:

```sql
WHERE status = ?
   OR priority = ?;
```

Với method có cả AND và OR, hãy đặc biệt chú ý cách parser nhóm predicate. Nếu biểu thức có nhiều nhóm ngoặc, nên dùng `@Query` để nhìn thấy cấu trúc SQL trực tiếp thay vì tạo một method name rất dài và khó kiểm chứng.

### 3.8. Sắp xếp và giới hạn kết quả

Có thể biểu diễn thứ tự trong method:

```java
List<Order> findByStatusOrderByCreatedAtDesc(OrderStatus status);

List<Product> findTop10ByActiveTrueOrderByNameAsc();

Optional<Order> findFirstByOrderCode(String orderCode);
```

- `OrderBy...Asc` sắp xếp tăng dần.
- `OrderBy...Desc` sắp xếp giảm dần.
- `First` và `Top` giới hạn số kết quả theo cú pháp method.
- Có thể dùng `Sort` hoặc `Pageable` ở các query method/repository API mà phiên bản Spring Data JDBC hỗ trợ.

Nếu cần phân trang, hãy chọn return type và method signature phù hợp với API của phiên bản đang dùng. Không phải mọi query có `Pageable` đều tự động có cùng chi phí hoặc cùng kiểu count query. Với truy vấn phức tạp, hãy xem SQL và kế hoạch thực thi của database.

## 4. Ví dụ repository sử dụng các nhóm keyword

Giả sử có aggregate root `Order`:

```java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @Column("order_code")
    private String orderCode;

    private OrderStatus status;

    @Column("customer_id")
    private Long customerId;

    private Integer priority;

    @Column("created_at")
    private LocalDateTime createdAt;

    @Column("deleted_at")
    private LocalDateTime deletedAt;

    // Constructor, getters và domain methods...
}
```

Repository:

```java
public interface OrderRepository
        extends CrudRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);

    List<Order> findByStatusNot(OrderStatus status);

    List<Order> findByPriorityGreaterThanEqual(Integer priority);

    List<Order> findByCreatedAtBetween(
            LocalDateTime start,
            LocalDateTime end
    );

    List<Order> findByDeletedAtIsNull();

    List<Order> findByDeletedAtIsNotNull();

    List<Order> findByStatusIn(Collection<OrderStatus> statuses);

    List<Order> findByStatusAndCustomerId(
            OrderStatus status,
            Long customerId
    );

    List<Order> findByStatusOrderByCreatedAtDesc(OrderStatus status);

    List<Order> findTop20ByDeletedAtIsNullOrderByCreatedAtDesc();

    long countByStatus(OrderStatus status);

    boolean existsByOrderCode(String orderCode);
}
```

Những method trên đều truy vấn property của aggregate root `Order`. Chúng không cần truy cập object quan hệ hoặc tạo join tự động.

Tên method nên phản ánh ý nghĩa domain. Nếu method dài tới mức phải đọc nhiều lần mới hiểu, chuyển điều kiện phức tạp sang `@Query` hoặc custom repository có thể dễ bảo trì hơn.

## 5. Giới hạn quan trọng: không tự truy cập quan hệ lồng nhau

Spring Data JDBC tập trung vào aggregate root và không cung cấp cơ chế query derivation tự động đi xuyên qua object graph để tạo join như cách người dùng có thể quen từ JPA.

Giả sử model:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private Long customerId;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;

    @Embedded(prefix = "shipping_")
    private ShippingAddress shippingAddress;
}
```

Các property `customerId`, `lines` và `shippingAddress` có ý nghĩa khác nhau:

- `customerId` là giá trị scalar được lưu trên hàng root.
- `lines` là collection child thuộc aggregate, lưu ở bảng khác.
- `shippingAddress` là value object được làm phẳng thành các cột trong bảng root.

Không nên suy luận rằng vì Java có thể gọi `order.getLines()` hoặc `order.getShippingAddress()` thì derived query cũng tự truy cập được các property sâu bên trong.

### 5.1. Không dựa vào findByLinesSku(...)

Ví dụ sau thể hiện một ý định truy vấn phổ biến nhưng không thuộc phạm vi derived query đơn giản của Spring Data JDBC:

```java
// Không dựa vào khả năng này trong Spring Data JDBC:
List<PurchaseOrder> findByLinesSku(String sku);
```

Lý do: `lines` là collection child trong aggregate. Để tìm root có ít nhất một dòng hàng với SKU cụ thể, database cần truy vấn bảng `order_lines` và liên kết với bảng `orders`.

Đó là một phép join/exists trên bảng child, không phải phép so sánh một property scalar trực tiếp của root.

Nếu cần truy vấn này, dùng SQL tường minh hoặc custom repository.

### 5.2. Không dựa vào findByCustomerName(...)

Nếu aggregate chỉ lưu ID tham chiếu:

```java
@Column("customer_id")
private Long customerId;
```

thì `Customer` là aggregate root khác. Derived query của `PurchaseOrderRepository` không tự đi tới `Customer.name` chỉ vì domain có thể mô tả quan hệ bằng ID hoặc `AggregateReference`.

Method như:

```java
// Không phải join traversal tổng quát của Spring Data JDBC:
List<PurchaseOrder> findByCustomerName(String name);
```

đòi hỏi join `orders.customer_id = customers.id`, sau đó lọc `customers.name`. Hãy viết SQL rõ ràng hoặc thực hiện truy vấn riêng cho Customer rồi dùng ID phù hợp.

### 5.3. Không giả định findByShippingAddressCity(...) luôn được hỗ trợ

Embedded object được làm phẳng vào các cột cùng bảng root. Về mặt SQL, điều kiện trên `shipping_city` là đơn giản. Tuy vậy, property path lồng nhau trong derived query không phải khả năng nên mặc định dựa vào cho Spring Data JDBC.

Nếu cần lọc theo cột embedded, cách tường minh là dùng `@Query` với tên cột đã mapping:

```java
@Query("""
    SELECT *
    FROM orders
    WHERE shipping_city = :city
    """)
List<PurchaseOrder> findOrdersByShippingCity(@Param("city") String city);
```

Đây là SQL trên bảng root. Kiểm tra tên cột thật, prefix và naming strategy của embedded mapping.

**Phân biệt hai việc:** object mapping có thể dựng nested object từ các cột root; query derivation không vì thế mà hỗ trợ mọi property path lồng nhau.

## 6. Vì sao giới hạn nested path quan trọng?

Spring Data JDBC thiết kế persistence quanh aggregate, không duy trì persistence context và không tự tạo graph join cho mọi quan hệ.

Một derived query đơn giản có thể ánh xạ trực tiếp:

```java
findByStatus(OrderStatus status)
```

thành điều kiện trên cột root:

```sql
SELECT *
FROM orders
WHERE status = ?;
```

Nhưng query nested cần biết thêm:

- Bảng nào chứa property cần lọc?
- Quan hệ nối bằng foreign key nào?
- Có phải một-nhiều hay nhiều-một?
- Một root có thể khớp nhiều child rows không?
- Kết quả có bị trùng root do join không?
- Có cần DISTINCT, EXISTS, GROUP BY hoặc pagination không?
- Nếu trả về aggregate root, child collection có cần được load và map tiếp không?

Một ORM có query model riêng có thể cung cấp cú pháp để diễn đạt các quan hệ này. Derived query của Spring Data JDBC giữ phạm vi nhỏ hơn; khi cần join, bạn phải nói rõ SQL và hình dạng kết quả.

## 7. Cách truy vấn quan hệ lồng nhau bằng @Query

Spring Data JDBC cho phép khai báo SQL trực tiếp bằng `@Query`. Đây là lựa chọn phù hợp khi cần join hoặc điều kiện trên bảng child.

### 7.1. Tìm đơn hàng có dòng hàng theo SKU

Ví dụ:

```java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT DISTINCT o.*
        FROM orders o
        JOIN order_lines l ON l.order_id = o.id
        WHERE l.sku = :sku
        """)
    List<PurchaseOrder> findOrdersContainingSku(
            @Param("sku") String sku
    );
}
```

SQL:

```sql
SELECT DISTINCT o.*
FROM orders o
JOIN order_lines l
    ON l.order_id = o.id
WHERE l.sku = ?;
```

`DISTINCT` giúp tránh trả cùng một root nhiều lần nếu nhiều child rows của cùng order thỏa điều kiện. Tên bảng/cột trong SQL phải khớp schema thực tế.

### 7.2. Dùng EXISTS khi chỉ cần kiểm tra child

Có thể diễn đạt cùng ý định bằng `EXISTS`:

```java
@Query("""
    SELECT o.*
    FROM orders o
    WHERE EXISTS (
        SELECT 1
        FROM order_lines l
        WHERE l.order_id = o.id
          AND l.sku = :sku
    )
    """)
List<PurchaseOrder> findOrdersHavingSku(@Param("sku") String sku);
```

`EXISTS` thể hiện rõ rằng chỉ cần có ít nhất một child phù hợp. Tùy database và dữ liệu, optimizer có thể chọn kế hoạch thực thi khác join; hãy xem execution plan khi hiệu năng quan trọng.

### 7.3. Query join không tự động có nghĩa là aggregate graph đầy đủ

Nếu `@Query` trả về `PurchaseOrder`, Spring Data JDBC cần map kết quả SQL vào kiểu trả về. Một query join trả về các cột của `orders` không có nghĩa framework tự động dùng các cột join để dựng toàn bộ `lines` giống một ORM fetch join.

Hãy chọn rõ mục tiêu:

- Trả aggregate root với các cột root cần thiết.
- Trả projection/DTO chỉ chứa dữ liệu màn hình cần.
- Trả child DTO qua repository/custom JDBC riêng.
- Chạy các query có chủ đích để lấy root và child khi nghiệp vụ cần cả hai.

Không nên `SELECT *` từ nhiều bảng rồi kỳ vọng mọi cột tự được gắn đúng vào nested object. Tên cột trùng, mapping metadata và số hàng join có thể làm kết quả mơ hồ.

### 7.4. SQL phải là SQL của database

`@Query` trong Spring Data JDBC nhận câu SQL, không phải JPQL. Không dùng cú pháp entity name hoặc association path kiểu JPA.

Ví dụ JPQL không phải cú pháp cho Spring Data JDBC:

```text
SELECT o FROM PurchaseOrder o JOIN o.lines l WHERE l.sku = :sku
```

Trong JDBC, viết tên bảng và điều kiện join thực tế:

```sql
SELECT DISTINCT o.*
FROM orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.sku = :sku;
```

Điều này cho phép dùng SQL mà database hỗ trợ, nhưng cũng có nghĩa query có thể phụ thuộc dialect/schema và cần được kiểm thử với database thật.

## 8. Khi nào dùng custom repository hoặc JdbcTemplate?

`@Query` phù hợp với một truy vấn SQL tường minh có kết quả ánh xạ rõ. Nếu cần truy vấn phức tạp hơn, nhiều bảng, projection đặc biệt hoặc command SQL có kiểm soát, custom repository là lựa chọn tốt.

Ví dụ repository tùy chỉnh trả về DTO:

```java
public record OrderLineSummary(
        Long orderId,
        String orderCode,
        String sku,
        int quantity
) {
}
```

Implementation dùng `NamedParameterJdbcTemplate`:

```java
@Repository
public class OrderSearchRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSearchRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderLineSummary> findLineSummaries(String sku) {
        String sql = """
            SELECT o.id AS order_id,
                   o.order_code,
                   l.sku,
                   l.quantity
            FROM orders o
            JOIN order_lines l ON l.order_id = o.id
            WHERE l.sku = :sku
            ORDER BY o.id
            """;

        var parameters = new MapSqlParameterSource("sku", sku);

        return jdbc.query(sql, parameters, (rs, rowNum) ->
                new OrderLineSummary(
                        rs.getLong("order_id"),
                        rs.getString("order_code"),
                        rs.getString("sku"),
                        rs.getInt("quantity")
                )
        );
    }
}
```

Đây là ví dụ projection: mỗi hàng kết quả được map thành `OrderLineSummary`. Nó không cố dựng aggregate `PurchaseOrder` từ một result set join có thể lặp root.

### 8.1. Lựa chọn giữa derived query, @Query và JdbcTemplate

| Cách làm | Phù hợp khi | Điểm cần lưu ý |
|---|---|---|
| Derived query | Điều kiện đơn giản trên property root | Giới hạn keyword và property path |
| `@Query` | SQL join/exists/aggregate expression cụ thể, kết quả map được vào return type | Phải quản lý SQL, schema và mapping |
| Custom repository + `JdbcTemplate` | DTO/projection phức tạp, nhiều query, logic truy cập dữ liệu riêng | Tự kiểm soát RowMapper và transaction participation |
| Nhiều repository calls | Dữ liệu đến từ các aggregate độc lập và có thể đọc riêng | Cần cân nhắc số query và consistency |
| Database view | Một phép đọc phức tạp được dùng lặp lại | View thuộc schema/database; mapping vẫn cần rõ ràng |

## 9. Truy vấn từng loại quan hệ

### 9.1. Embedded object

Embedded property được lưu thành cột của bảng root. Nếu query derivation không xử lý nested property theo yêu cầu, dùng `@Query` với cột đã flatten.

Ví dụ:

```java
@Query("""
    SELECT *
    FROM orders
    WHERE shipping_city = :city
    """)
List<PurchaseOrder> findByShippingCity(@Param("city") String city);
```

Không cần join vì các cột địa chỉ nằm cùng bảng `orders`.

### 9.2. Child collection

Với `@MappedCollection`, child rows ở bảng riêng. Nếu muốn lọc root theo child property, viết join hoặc EXISTS:

```sql
SELECT o.*
FROM orders o
WHERE EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.id
      AND l.quantity > 5
);
```

Nếu muốn lấy chính các child rows, trả DTO/child projection thay vì giả định derived query trên root có thể trả một child path tùy ý.

### 9.3. Aggregate reference

Nếu order lưu `customer_id`, query theo ID là query trên property scalar của root:

```java
List<PurchaseOrder> findByCustomerId(Long customerId);
```

Nhưng query theo tên khách hàng cần join:

```sql
SELECT o.*
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE c.display_name = ?;
```

Có thể viết câu SQL này bằng `@Query` hoặc custom repository. Khi chỉ cần danh sách customer, truy vấn `CustomerRepository` riêng có thể đơn giản hơn; sau đó dùng ID để tìm order nếu số lượng ID phù hợp.

### 9.4. Nhiều quan hệ lồng nhau

Một truy vấn như “tìm tất cả đơn hàng của khách hàng ở thành phố X có dòng hàng thuộc SKU Y” cần kết hợp bảng `orders`, `customers`, `order_lines`. Đây là query nhiều bảng, không nên cố biểu diễn bằng một method name dài.

SQL có thể viết:

```sql
SELECT DISTINCT o.*
FROM orders o
JOIN customers c
    ON c.id = o.customer_id
JOIN order_lines l
    ON l.order_id = o.id
WHERE c.city = ?
  AND l.sku = ?;
```

Nếu cần thêm phân trang, sort hoặc projection, hãy thiết kế query/return type rõ ràng và kiểm tra execution plan.

## 10. Phân biệt truy vấn quan hệ với lưu aggregate

Một giới hạn query derivation không có nghĩa Spring Data JDBC không thể lưu hoặc đọc aggregate có nested object.

Ví dụ:

- `@Embedded` cho phép object value được làm phẳng vào cột root.
- `@MappedCollection` cho phép lưu/đọc child collection thuộc aggregate.
- `AggregateReference` biểu diễn tham chiếu tới aggregate root khác.

Các annotation này điều khiển **object mapping và aggregate persistence**. Chúng không tự mở rộng ngôn ngữ derived query thành một query builder có thể join mọi quan hệ.

| Nhu cầu | Mapping/persistence | Truy vấn |
|---|---|---|
| Lưu địa chỉ cùng order | `@Embedded` | Query cột root, dùng `@Query` nếu nested path không được hỗ trợ |
| Lưu order lines | `@MappedCollection` | Join/EXISTS hoặc custom query để lọc theo line |
| Tham chiếu Customer | ID/`AggregateReference` | Query theo ID trên root; join khi lọc theo thuộc tính Customer |
| Tải aggregate | Repository aggregate | Repository đọc aggregate theo mapping |
| Báo cáo nhiều bảng | Không nhất thiết là aggregate | DTO/projection, SQL hoặc view |

Đừng nhầm khả năng dựng object khi đọc aggregate với khả năng truy vấn mọi property sâu trong object graph.

## 11. Keyword nào không nên mang từ module khác sang JDBC?

Spring Data Commons cung cấp nền tảng query method dùng chung, nhưng mỗi Spring Data module có khả năng riêng. Không phải keyword của một store đều có nghĩa trong Spring Data JDBC.

Một số ví dụ không nên mặc định dùng trong JDBC:

| Tính năng thường thấy ở module khác | Vì sao không nên giả định JDBC hỗ trợ |
|---|---|
| JPA association traversal/fetch join | JDBC derived query không tự tạo join từ object relationship |
| JPQL entity path | `@Query` của JDBC nhận SQL, không nhận JPQL |
| MongoDB `Regex`/document operators | Cú pháp và ngữ nghĩa thuộc MongoDB query model |
| Geospatial `Near`/`Within` | Phụ thuộc store có hỗ trợ kiểu dữ liệu và operator địa lý |
| Elasticsearch full-text/search operators | Thuộc search engine, không phải query derivation relational thông thường |
| JPA `EntityGraph`/fetch strategy | Spring Data JDBC không có persistence context và fetch graph semantics như JPA |
| Collection association operators tùy store | Không thể suy ra rằng collection child có thể được query như property scalar |

Nếu một keyword có trong bảng keyword chung của Spring Data, vẫn cần kiểm tra Spring Data JDBC version và dialect có hỗ trợ cách dịch tương ứng không. Không dựa vào việc IDE autocomplete hoặc tên method biên dịch được để kết luận query sẽ chạy đúng.

## 12. Tên method và property path: những lỗi dễ gặp

### 12.1. Dùng tên cột thay cho tên property

Domain:

```java
@Column("created_at")
private LocalDateTime createdAt;
```

Đúng:

```java
List<Order> findByCreatedAtAfter(LocalDateTime time);
```

Sai về ý định property parsing:

```java
List<Order> findByCreated_atAfter(LocalDateTime time);
```

### 12.2. Truy vấn property không persistent

Nếu property được đánh dấu `@Transient`, hoặc chỉ là giá trị tính toán không có cột mapping, derived query không thể tạo điều kiện SQL thông thường cho nó.

Ví dụ:

```java
@Transient
private String displayLabel;
```

Không thể kỳ vọng `findByDisplayLabel(...)` hoạt động như truy vấn cột nếu `displayLabel` không được lưu. Hãy truy vấn các property persistent cấu thành nó hoặc dùng projection/tính toán ở tầng ứng dụng.

### 12.3. Dùng tên nested property

Method như `findByAddressCity(...)`, `findByLinesSku(...)` hoặc `findByCustomerName(...)` thể hiện property path lồng nhau. Spring Data JDBC không nên được giả định sẽ tự traverse và join các quan hệ đó.

Hãy chuyển sang `@Query` hoặc custom repository khi điều kiện nằm ở bảng khác hoặc trong nested object mà derived query không hỗ trợ.

### 12.4. Method name quá dài

Ví dụ:

```java
findByStatusAndCustomerIdAndCreatedAtAfterAndDeletedAtIsNullOrderByPriorityDesc(...)
```

Method dài không nhất thiết sai, nhưng khi có nhiều nhánh `And`/`Or`, rất khó đọc và dễ nhầm logic. Nếu query cần nhóm biểu thức, join, subquery hoặc projection, SQL tường minh thường dễ review hơn.

## 13. Hiệu năng và tính đúng đắn của query

Derived query tạo SQL thuận tiện, nhưng không tự bảo đảm query nhanh. Hãy xét các yếu tố database:

- **Index:** cột dùng trong predicate/join/sort có thể cần index.
- **Selectivity:** điều kiện `IS NOT NULL` trên cột có hầu hết hàng đều có giá trị có thể không lọc được nhiều.
- **LIKE pattern:** `Containing` thường tạo pattern có wildcard ở đầu và có thể không dùng B-tree index thông thường hiệu quả.
- **IN list:** collection rất lớn có thể làm câu SQL dài và ảnh hưởng kế hoạch thực thi.
- **Join duplicates:** join một-nhiều có thể trả nhiều hàng cho cùng root; cân nhắc `DISTINCT` hoặc `EXISTS`.
- **Pagination:** join với dữ liệu một-nhiều có thể làm phân trang theo hàng join thay vì theo root nếu query không được thiết kế đúng.
- **Null semantics:** `Not`, `NotIn` và so sánh thông thường không tự bao gồm SQL NULL.

Ví dụ index:

```sql
CREATE INDEX idx_orders_status
    ON orders(status);

CREATE INDEX idx_orders_customer_id
    ON orders(customer_id);

CREATE INDEX idx_order_lines_order_id_sku
    ON order_lines(order_id, sku);
```

Index phù hợp phụ thuộc tần suất truy vấn, phân bố dữ liệu và database. Không tạo index cho mọi cột một cách máy móc; index cũng làm tăng chi phí INSERT/UPDATE/DELETE.

### 13.1. Xem execution plan

Với PostgreSQL có thể dùng:

```sql
EXPLAIN
SELECT DISTINCT o.*
FROM orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.sku = 'BOOK-01';
```

Dùng `EXPLAIN ANALYZE` trong môi trường phù hợp khi muốn đo thực thi thật; câu lệnh đó chạy query và có thể gây tác động nếu query nặng. Kế hoạch tối ưu cần dựa trên dữ liệu và database thực tế, không chỉ nhìn tên method.

## 14. Kiểm thử derived query và nested query

### 14.1. Test derived query trên root property

```java
@DataJdbcTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository orders;

    @Test
    void findsOrdersByStatus() {
        assertThat(orders.findByStatus(OrderStatus.NEW))
                .allMatch(order -> order.getStatus() == OrderStatus.NEW);
    }
}
```

Test cần fixture và schema tương ứng. Nó kiểm tra derived query được phân tích và thực thi đúng trên database thử nghiệm.

### 14.2. Test custom join query

Với query tìm order có SKU:

```java
@Test
void findsOrdersContainingSku() {
    List<PurchaseOrder> result =
            orders.findOrdersContainingSku("BOOK-01");

    assertThat(result)
            .extracting(PurchaseOrder::getId)
            .contains(orderId);
}
```

Nên thêm trường hợp một order có nhiều dòng cùng SKU để xác nhận kết quả không lặp root nếu method dùng `DISTINCT`/`EXISTS`.

### 14.3. Test projection cho child rows

Nếu repository trả `OrderLineSummary`, test nên xác nhận các alias SQL map đúng DTO:

- `order_id` → `orderId`
- `order_code` → `orderCode`
- `sku` → `sku`
- `quantity` → `quantity`

Với custom `RowMapper`, tên alias và kiểu JDBC phải khớp mapping do bạn viết.

### 14.4. Test NULL và collection rỗng

Nếu query có `Not`, `NotIn`, `IsNull` hoặc `In`, hãy kiểm tra dữ liệu NULL và collection rỗng. Đây là những trường hợp dễ có khác biệt giữa kỳ vọng Java và logic SQL.

## 15. Bảng quyết định: chọn công cụ truy vấn nào?

| Yêu cầu | Cách tiếp cận nên cân nhắc |
|---|---|
| So sánh một property scalar của aggregate root | Derived query |
| `IS NULL`, boolean, khoảng, chuỗi, `IN` trên root | Derived query với keyword phù hợp |
| Sắp xếp/giới hạn đơn giản | `OrderBy`, `First`/`Top`, `Sort`/`Pageable` nếu phiên bản hỗ trợ |
| Lọc root theo property của child collection | `@Query` với `EXISTS`/join hoặc custom repository |
| Lọc root theo tên của aggregate được tham chiếu | SQL join hoặc truy vấn riêng theo ID |
| Lọc theo cột embedded | `@Query` dùng tên cột đã flatten nếu derived nested path không phù hợp |
| Trả dữ liệu từ nhiều bảng thành DTO | Custom query/projection/RowMapper |
| Báo cáo nhiều phép tổng hợp | SQL tường minh, view hoặc reporting repository |
| Cập nhật/xóa hàng theo lệnh SQL đặc biệt | Custom repository/JdbcTemplate với transaction và invariant rõ ràng |

## 16. Nguyên tắc ghi nhớ

- Derived query của Spring Data JDBC dùng tên property Java và các keyword mà module hỗ trợ để tạo SQL.
- Các nhóm predicate phổ biến gồm so sánh bằng/khác, khoảng, NULL, boolean, chuỗi, `IN`/`NOT IN`, `And`/`Or`, sắp xếp và giới hạn kết quả.
- Không mang nguyên khả năng query của JPA, MongoDB hoặc search engine sang Spring Data JDBC.
- Spring Data JDBC tập trung vào property của aggregate root; không giả định method name có thể tự đi xuyên `@MappedCollection`, `AggregateReference` hoặc nested object để tạo join.
- Embedded/child/reference là các khái niệm mapping và aggregate persistence; chúng không tự mở rộng query derivation.
- Khi cần truy vấn bảng child hoặc aggregate khác, dùng `@Query` SQL, custom repository, `JdbcTemplate`, projection hoặc view.
- Với join một-nhiều, chú ý duplicate root, `DISTINCT`/`EXISTS`, pagination và mapping kết quả.
- Kiểm tra SQL, dialect, index và dữ liệu NULL trên database thật khi tính đúng đắn hoặc hiệu năng quan trọng.

Hãy dùng derived query cho điều kiện đơn giản, dễ đọc trên aggregate root. Khi điều kiện cần truy cập quan hệ lồng nhau, hãy mô tả rõ bảng, khóa nối và hình dạng kết quả bằng SQL hoặc custom repository. Cách phân chia này giữ repository dễ hiểu và giúp bạn không nhầm khả năng object mapping của Spring Data JDBC với khả năng tự động truy vấn toàn bộ object graph.

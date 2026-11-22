# Giới hạn Criteria với JOIN và quan hệ trong aggregate

Trong **Spring Data Relational JDBC**, `Criteria` và `Query` cung cấp API Java để xây dựng điều kiện truy vấn động. Bạn có thể tạo predicate theo property, kết hợp `AND`/`OR`, kiểm tra `NULL`, so sánh khoảng, lọc theo tập giá trị và bổ sung sắp xếp hoặc giới hạn kết quả.

Tuy nhiên, API này có phạm vi hẹp hơn một query builder SQL tổng quát hoặc JPA Criteria API. **Criteria không tự suy ra JOIN chỉ vì aggregate có `@MappedCollection` hoặc `AggregateReference`.** Khi điều kiện nằm trong bảng child hoặc thuộc tính của một aggregate root khác, bạn cần mô tả quan hệ SQL tường minh bằng `@Query`, custom repository hoặc `JdbcTemplate`.

Để dùng Criteria đúng, hãy phân biệt ba loại dữ liệu:

- **Property của aggregate root:** nằm trên bảng root và là mục tiêu tự nhiên của Criteria.
- **Embedded value object:** các field được làm phẳng vào cùng bảng root; không tạo quan hệ JOIN tới bảng khác.
- **Child collection hoặc aggregate reference:** dữ liệu nằm ở bảng khác; lọc theo các field đó thường cần JOIN hoặc `EXISTS` được viết rõ.

Bài học giải thích cách xây dựng truy vấn động bằng Criteria, giới hạn với quan hệ lồng nhau, cách thay thế bằng SQL và những lưu ý về mapping kết quả.

## 1. Criteria trong Spring Data JDBC là gì?

`Criteria` thuộc Spring Data Relational và mô tả các điều kiện lọc trên dữ liệu relational. `Query` kết hợp predicate với những thành phần truy vấn như sort, limit và offset mà API hỗ trợ.

Các kiểu thường dùng:

- `org.springframework.data.relational.core.query.Criteria`
- `org.springframework.data.relational.core.query.Query`
- `org.springframework.data.jdbc.core.JdbcAggregateTemplate`
- `org.springframework.data.domain.Sort`

Ví dụ, thay vì khai báo nhiều method repository cho từng tổ hợp điều kiện, service có thể dựng Criteria từ các tham số tìm kiếm:

```java
Criteria criteria = Criteria.where("status").is(OrderStatus.NEW)
        .and("createdAt").greaterThanOrEquals(from)
        .and("deletedAt").isNull();

Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.desc("createdAt")))
        .limit(50);

List<PurchaseOrder> orders =
        aggregateTemplate.findAll(query, PurchaseOrder.class);
```

Ví dụ minh họa một truy vấn theo các property của aggregate root. Tên property trong Criteria là tên Java property được mapping, ví dụ `createdAt`; không nhất thiết là tên cột vật lý `created_at`.

Tên package, method overload và API chi tiết có thể thay đổi theo phiên bản Spring Data Relational. Hãy dùng đúng phiên bản dependency của ứng dụng khi triển khai.

### 1.1. Criteria không phải JPA Criteria API

Hai API có tên gần giống nhau nhưng mục tiêu và khả năng khác nhau.

| Tiêu chí | Spring Data Relational `Criteria` | JPA Criteria API |
|---|---|---|
| Package tiêu biểu | `org.springframework.data.relational.core.query` | `jakarta.persistence.criteria` |
| Đối tượng query | Predicate relational dùng cùng `Query`/template | Query model của JPA |
| Root/path/join graph | Không cung cấp mô hình association join tổng quát như JPA | Có `Root`, `Path`, `Join` |
| Quan hệ entity | Theo aggregate mapping của Spring Data JDBC | Theo association mapping của JPA |
| Persistence context | Không có session managed entity như JPA | Có persistence context |
| Mục đích | Xây dựng điều kiện SQL phù hợp với mapping relational | Xây dựng query trên entity model và association |

Không thể chuyển nguyên đoạn JPA Criteria có `root.join("lines")` sang Spring Data JDBC rồi mong nó hoạt động. Spring Data JDBC có cách mô hình hóa aggregate và truy vấn riêng.

### 1.2. Criteria phù hợp với truy vấn động

Criteria đặc biệt hữu ích khi số lượng điều kiện phụ thuộc input:

- Người dùng có thể lọc theo trạng thái hoặc bỏ trống bộ lọc đó.
- Màn hình có khoảng thời gian tùy chọn.
- Có thể chọn một hoặc nhiều giá trị enum.
- Một số điều kiện chỉ áp dụng khi checkbox được bật.
- Cần kết hợp predicate với sort/limit.

Ví dụ, service chỉ thêm điều kiện khi người dùng cung cấp giá trị:

```java
List<Criteria> predicates = new ArrayList<>();

if (status != null) {
    predicates.add(Criteria.where("status").is(status));
}

if (createdAfter != null) {
    predicates.add(Criteria.where("createdAt").greaterThanOrEquals(createdAfter));
}

if (includeDeleted == false) {
    predicates.add(Criteria.where("deletedAt").isNull());
}
```

Các predicate có thể được kết hợp thành một điều kiện cuối cùng theo API `Criteria` của phiên bản đang dùng. Cách ghép điều kiện cần giữ đúng ngữ nghĩa `AND`/`OR`; không nên dùng một biểu thức duy nhất nếu điều kiện có nhóm logic phức tạp.

## 2. Các predicate Criteria thường gặp

Criteria cung cấp các phép so sánh quen thuộc cho property relational. Ví dụ:

| Nhóm | Cách biểu diễn | Ý nghĩa |
|---|---|---|
| Bằng | `.is(value)` | Bằng giá trị |
| Khác | `.not(value)` | Khác giá trị |
| Null | `.isNull()` | Cột là SQL NULL |
| Not null | `.isNotNull()` | Cột khác SQL NULL |
| Lớn hơn | `.greaterThan(value)` | `>` |
| Lớn hơn hoặc bằng | `.greaterThanOrEquals(value)` | `>=` |
| Nhỏ hơn | `.lessThan(value)` | `<` |
| Nhỏ hơn hoặc bằng | `.lessThanOrEquals(value)` | `<=` |
| Trong khoảng | `.between(from, to)` | Nằm trong khoảng |
| Thuộc tập | `.in(values)` | Giá trị nằm trong tập |
| Không thuộc tập | `.notIn(values)` | Giá trị không nằm trong tập |
| Chuỗi LIKE | `.like(pattern)` | So khớp pattern |
| Boolean | `.isTrue()` / `.isFalse()` | Giá trị boolean true/false |

Tên method cụ thể có thể khác theo phiên bản. Hãy tham chiếu Javadoc của Spring Data Relational mà dự án đang sử dụng khi cần một operator ít phổ biến.

Ví dụ:

```java
Criteria criteria = Criteria.where("totalAmount")
        .greaterThanOrEquals(minimum)
        .and("status")
        .in(List.of(OrderStatus.NEW, OrderStatus.PAID));
```

Predicate có thể được kết hợp thêm:

```java
Criteria criteria = Criteria.where("status").is(OrderStatus.PAID)
        .and("createdAt").between(start, end)
        .and("deletedAt").isNull();
```

Ngữ nghĩa SQL tương đương về ý định:

```sql
SELECT *
FROM orders
WHERE status = ?
  AND created_at BETWEEN ? AND ?
  AND deleted_at IS NULL;
```

Criteria mô tả điều kiện; template chịu trách nhiệm chuyển điều kiện đó thành SQL theo mapping và dialect.

## 3. Dùng Query để thêm sort và giới hạn

`Query` bao bọc Criteria và có thể mang thêm thông tin sắp xếp, offset hoặc giới hạn tùy API của phiên bản.

Ví dụ:

```java
Criteria criteria = Criteria.where("status").is(OrderStatus.NEW);

Query query = Query.query(criteria)
        .sort(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("orderCode")
        ))
        .limit(25)
        .offset(0);

List<PurchaseOrder> result =
        aggregateTemplate.findAll(query, PurchaseOrder.class);
```

Điểm cần lưu ý:

- Sort dùng property được mapping, ví dụ `createdAt`.
- Limit giới hạn số hàng root được chọn theo truy vấn.
- Offset bỏ qua số hàng đầu tiên theo thứ tự sort.
- Luôn dùng sort ổn định khi phân trang, thường thêm một khóa duy nhất như ID để tránh thứ tự không xác định giữa các trang.

Ví dụ sort chỉ theo thời gian có thể tạo thứ tự không ổn định nếu nhiều đơn hàng có cùng `createdAt`. Thêm `id` làm tiêu chí phụ giúp thứ tự nhất quán hơn:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);
```

`Query` không phải nơi mô tả JOIN tùy ý. Việc thêm `.sort(...)` hoặc `.limit(...)` không mở rộng Criteria thành một query builder có thể nối mọi bảng.

## 4. Criteria truy vấn property của aggregate root

Giả sử aggregate root `PurchaseOrder` có các property scalar:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_code")
    private String orderCode;

    private OrderStatus status;

    @Column("created_at")
    private LocalDateTime createdAt;

    @Column("deleted_at")
    private LocalDateTime deletedAt;

    // Constructor, getters và domain methods...
}
```

Các property này được lưu trong bảng `orders`, nên phù hợp với điều kiện root-level Criteria:

```java
Criteria criteria = Criteria.where("status").is(OrderStatus.NEW)
        .and("createdAt").greaterThanEqual(from)
        .and("createdAt").lessThan(to)
        .and("deletedAt").isNull();

Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.desc("createdAt")));
```

SQL tương đương về ngữ nghĩa:

```sql
SELECT *
FROM orders
WHERE status = ?
  AND created_at >= ?
  AND created_at < ?
  AND deleted_at IS NULL
ORDER BY created_at DESC;
```

### 4.1. Tạo Criteria từ bộ lọc tùy chọn

Một bộ lọc tìm kiếm có thể có nhiều trường optional:

```java
public record OrderFilter(
        OrderStatus status,
        LocalDateTime createdFrom,
        LocalDateTime createdTo,
        String orderCode
) {
}
```

Service có thể xây dựng predicate theo từng trường được cung cấp. Một cách viết rõ ràng là khởi tạo Criteria đầu tiên rồi nối các điều kiện còn lại:

```java
Criteria criteria = Criteria.empty();

if (filter.status() != null) {
    criteria = criteria.and("status").is(filter.status());
}

if (filter.createdFrom() != null) {
    criteria = criteria.and("createdAt")
            .greaterThanOrEquals(filter.createdFrom());
}

if (filter.createdTo() != null) {
    criteria = criteria.and("createdAt")
            .lessThan(filter.createdTo());
}

if (filter.orderCode() != null && !filter.orderCode().isBlank()) {
    criteria = criteria.and("orderCode").like("%" + filter.orderCode() + "%");
}

Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.desc("createdAt")))
        .limit(100);
```

Cách tạo Criteria rỗng và cách gọi `and(...)` phụ thuộc API version; có thể thay bằng danh sách predicate rồi kết hợp nếu phiên bản không có factory tương ứng. Mục tiêu là chỉ đưa điều kiện đã được cung cấp vào query, không truyền giá trị null vào một phép so sánh bằng.

Với chuỗi tìm kiếm do người dùng nhập, hãy kiểm tra cách API xử lý wildcard và escape ký tự `%`/`_`. Nếu muốn tìm chuỗi literal thay vì pattern, cần escape wildcard theo quy tắc của database.

### 4.2. Không nhầm SQL NULL với giá trị rỗng

`isNull()` kiểm tra SQL NULL. Nó không tương đương với chuỗi rỗng, số 0 hoặc Boolean false.

Ví dụ:

- `orderCode IS NULL`: chưa có mã.
- `orderCode = ''`: có chuỗi nhưng chuỗi rỗng.
- `deletedAt IS NULL`: chưa có thời điểm xóa.
- `enabled = FALSE`: cờ có giá trị false.

Nếu domain cần gộp nhiều trạng thái, hãy thêm predicate rõ ràng và kiểm tra SQL three-valued logic.

## 5. Vì sao Criteria không tự tạo JOIN?

Criteria mô tả predicate trên một phạm vi mapping mà Spring Data JDBC có thể phân giải. Nó không cung cấp đầy đủ mô hình `Root`/`Join` để bạn điều hướng quan hệ entity như JPA Criteria API.

Giả sử aggregate có các thành phần:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines = new ArrayList<>();

    @Embedded(prefix = "shipping_")
    private ShippingAddress shippingAddress;
}
```

Ba property có mapping khác nhau:

| Property | Cách lưu | Bảng liên quan |
|---|---|---|
| `customerId` | Scalar ID trên root | `orders` |
| `lines` | Collection child | `order_lines` |
| `shippingAddress` | Field được flatten | Các cột `shipping_*` trong `orders` |

Criteria trên `customerId` là predicate root-level:

```java
Criteria.where("customerId").is(customerId);
```

Nhưng việc truy vấn `lines.sku` cần kiểm tra bảng `order_lines`, nối `order_lines.order_id` với `orders.id`. Việc truy vấn `customer.displayName` cần nối `orders.customer_id` với `customers.id`.

Chỉ tên property lồng nhau không đủ để mô tả:

- Bảng nào phải JOIN.
- Cột nào là khóa nối.
- JOIN loại INNER hay LEFT.
- Cần loại bỏ root trùng lặp hay không.
- Có cần EXISTS hoặc aggregate function không.
- Kết quả cần là root, child hay DTO.

Do đó, không nên giả định Criteria tự xây dựng JOIN chỉ vì domain model có field object hoặc collection.

## 6. Giới hạn với @MappedCollection và child entities

`@MappedCollection` biểu diễn collection entity con thuộc aggregate root. Child được lưu ở bảng riêng, có cột liên kết về root.

Ví dụ:

```java
@Table("order_lines")
public class OrderLine {

    @Id
    private Long id;

    private String sku;
    private int quantity;

    // Constructor và getters...
}
```

Aggregate root:

```java
@MappedCollection(idColumn = "order_id", keyColumn = "line_index")
private List<OrderLine> lines = new ArrayList<>();
```

DDL:

```sql
CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    line_index INTEGER NOT NULL,
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL
);
```

Nếu muốn tìm các đơn hàng có ít nhất một dòng với `sku = 'BOOK-01'`, điều kiện nằm trên bảng child. Không thể coi `lines` như một cột scalar của bảng `orders`.

Không dựa vào một Criteria như:

```java
// Không phải cú pháp JOIN tổng quát cho collection child.
Criteria.where("lines.sku").is("BOOK-01");
```

Đây không phải cách diễn đạt đáng tin cậy để yêu cầu JOIN `orders` với `order_lines`. Hãy viết SQL có JOIN/EXISTS hoặc dùng một custom repository.

### 6.1. Dùng EXISTS để lọc root theo child

SQL:

```sql
SELECT o.*
FROM orders o
WHERE EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.id
      AND l.sku = ?
);
```

`EXISTS` phù hợp khi mục tiêu là lấy mỗi root một lần nếu có ít nhất một child thỏa điều kiện.

Với Spring Data JDBC, có thể dùng `@Query` hoặc custom repository. Nếu kết quả cần chỉ là dữ liệu hiển thị, DTO projection thường rõ ràng hơn trả aggregate root:

```java
public record OrderMatch(
        Long orderId,
        String orderCode,
        String status
) {
}
```

### 6.2. Dùng JOIN khi cần dữ liệu từ cả root và child

Nếu màn hình cần từng dòng hàng cùng mã đơn hàng:

```sql
SELECT
    o.id AS order_id,
    o.order_code AS order_code,
    l.id AS line_id,
    l.sku AS sku,
    l.quantity AS quantity
FROM orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.sku = ?
ORDER BY o.id, l.line_index;
```

Một hàng result set ở đây biểu diễn một cặp order/line. DTO phù hợp:

```java
public record OrderLineResult(
        Long orderId,
        String orderCode,
        Long lineId,
        String sku,
        Integer quantity
) {
}
```

Đừng cố map result set nhiều hàng này thành một aggregate root duy nhất nếu chưa có logic gom child rows. Mỗi dòng join có thể lặp lại thông tin root.

## 7. Giới hạn với AggregateReference và aggregate root khác

Một aggregate có thể tham chiếu root khác bằng ID hoặc `AggregateReference`.

Ví dụ:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private AggregateReference<Customer, Long> customer;
}
```

Reference biểu diễn ID của `Customer`; nó không phải object customer đã được load. Criteria có thể lọc theo giá trị ID được lưu trên root nếu mapping/property path phù hợp:

```java
Criteria.where("customer").is(AggregateReference.to(customerId));
```

Hoặc ứng dụng có thể lưu một property scalar `customerId` và lọc trực tiếp theo ID.

Nhưng nếu yêu cầu là “tìm đơn hàng theo tên khách hàng”, điều kiện nằm ở bảng `customers`:

```sql
SELECT o.*
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE c.display_name = ?;
```

Criteria của `PurchaseOrder` không tự tải `Customer` và không tự tạo join chỉ vì có `AggregateReference<Customer, Long>`.

### 7.1. Khi nào truy vấn Customer riêng?

Nếu truy vấn đơn giản và tập ID nhỏ, có thể:

1. Tìm customer theo điều kiện ở `CustomerRepository`.
2. Lấy danh sách ID customer.
3. Tìm orders theo `customerId` hoặc `customerId IN (...)`.

Cách này dùng nhiều repository query nhưng có thể dễ hiểu. Cần cân nhắc kích thước tập ID, số round trip và giới hạn tham số `IN` của database.

Nếu truy vấn cần phân trang trên tập đơn hàng theo customer name, JOIN/EXISTS trong một SQL thường phù hợp hơn vì database lọc và phân trang trên cùng tập kết quả.

## 8. Embedded object khác với quan hệ JOIN

`@Embedded` làm phẳng property của value object thành các cột trong bảng root. Vì vậy, embedded object không yêu cầu JOIN tới một bảng riêng.

Ví dụ:

```java
public record ShippingAddress(
        String street,
        String city,
        String postalCode
) {
}
```

Trong aggregate:

```java
@Embedded(prefix = "shipping_")
private ShippingAddress shippingAddress;
```

Schema có thể chứa:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    order_code VARCHAR(40) NOT NULL,
    shipping_street VARCHAR(180),
    shipping_city VARCHAR(100),
    shipping_postal_code VARCHAR(20)
);
```

Điều kiện `shipping_city = ?` nằm trên cùng bảng `orders`; không có bảng `shipping_addresses` để JOIN.

Tuy vậy, khả năng Criteria phân giải một nested property như `shippingAddress.city` phụ thuộc mapping và API version. Không nên mặc định property path Java lồng nhau luôn được hỗ trợ. Nếu cần truy vấn ổn định theo cột đã flatten, dùng SQL tường minh:

```sql
SELECT *
FROM orders
WHERE shipping_city = ?;
```

Hoặc dùng property path mà phiên bản mapping của ứng dụng hỗ trợ và xác nhận bằng integration test.

**Embedded là mapping nhiều field vào cùng hàng; `@MappedCollection` và `AggregateReference` liên quan tới bảng/aggregate khác.** Chỉ hai trường hợp sau mới cần xem xét JOIN hoặc EXISTS khi lọc theo dữ liệu ở bảng khác.

## 9. Dùng @Query khi cần JOIN

Spring Data JDBC hỗ trợ khai báo SQL tường minh bằng `@Query`. Đây là lựa chọn phù hợp khi query cần join hoặc subquery.

Ví dụ repository trả DTO:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT
            o.id AS order_id,
            o.order_code AS order_code,
            o.status AS status
        FROM orders o
        WHERE EXISTS (
            SELECT 1
            FROM order_lines l
            WHERE l.order_id = o.id
              AND l.sku = :sku
        )
        """)
    List<OrderMatch> findOrdersContainingSku(
            @Param("sku") String sku
    );
}
```

Ví dụ trên giả định mapping DTO constructor/record và alias của phiên bản dự án hỗ trợ kiểu kết quả này. Nếu module hoặc version hiện tại không hỗ trợ trực tiếp DTO đó, dùng custom repository với `JdbcTemplate` và `RowMapper`.

### 9.1. Không dùng JPQL

`@Query` trong Spring Data JDBC nhận SQL, không phải JPQL.

JPQL mô tả entity và association:

```text
SELECT o FROM PurchaseOrder o JOIN o.lines l WHERE l.sku = :sku
```

SQL của JDBC mô tả bảng và cột:

```sql
SELECT DISTINCT o.id, o.order_code, o.status
FROM orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.sku = :sku;
```

Dùng tên bảng/cột thực tế, bao gồm prefix và naming strategy mà schema đang sử dụng.

### 9.2. Chọn cột tường minh và alias rõ

Khi join, nhiều bảng thường có cột trùng tên như `id`, `status`, `created_at`. Tránh `SELECT *` vì column label có thể trùng và mapping DTO khó đoán.

Viết:

```sql
SELECT
    o.id AS order_id,
    c.id AS customer_id,
    o.status AS order_status,
    c.display_name AS customer_name
FROM orders o
JOIN customers c ON c.id = o.customer_id;
```

Sau đó ánh xạ vào DTO có tên component tương ứng:

```java
public record OrderCustomerView(
        Long orderId,
        Long customerId,
        String orderStatus,
        String customerName
) {
}
```

Alias phải tương thích với naming strategy/constructor mapping của ứng dụng. Kiểm tra column labels thực tế nếu database chuẩn hóa casing.

## 10. Dùng custom repository và JdbcTemplate

Với query nhiều bảng, DTO đặc thù hoặc kết quả cần chuyển đổi rõ ràng, custom repository là cách kiểm soát tốt.

Ví dụ DTO:

```java
public record OrderLineSearchResult(
        Long orderId,
        String orderCode,
        String customerName,
        String sku,
        Integer quantity
) {
}
```

Custom repository:

```java
@Repository
public class OrderSearchRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSearchRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderLineSearchResult> searchByCustomerAndSku(
            String customerName,
            String sku
    ) {
        String sql = """
            SELECT
                o.id AS order_id,
                o.order_code AS order_code,
                c.display_name AS customer_name,
                l.sku AS sku,
                l.quantity AS quantity
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            JOIN order_lines l ON l.order_id = o.id
            WHERE c.display_name = :customerName
              AND l.sku = :sku
            ORDER BY o.id, l.line_index
            """;

        var parameters = new MapSqlParameterSource()
                .addValue("customerName", customerName)
                .addValue("sku", sku);

        return jdbc.query(sql, parameters, (rs, rowNum) ->
                new OrderLineSearchResult(
                        rs.getLong("order_id"),
                        rs.getString("order_code"),
                        rs.getString("customer_name"),
                        rs.getString("sku"),
                        rs.getObject("quantity", Integer.class)
                )
        );
    }
}
```

Cách này cho phép:

- Dùng JOIN giữa nhiều bảng.
- Chọn chính xác cột kết quả.
- Trả DTO theo từng hàng result set.
- Điều khiển kiểu chuyển đổi và xử lý NULL.
- Không phải dựng aggregate graph nếu use case chỉ cần dữ liệu báo cáo.

`NamedParameterJdbcTemplate` vẫn có thể tham gia transaction Spring khi dùng cùng DataSource và transaction manager. Tuy nhiên, nó không tự áp dụng aggregate lifecycle hoặc tự tải child collection.

## 11. Cẩn thận với kết quả JOIN một-nhiều

JOIN giữa root và child có thể trả nhiều hàng cho một root.

Ví dụ một order có ba order lines:

| order_id | order_code | line_id | sku |
|---:|---|---:|---|
| 101 | PO-101 | 1001 | BOOK-01 |
| 101 | PO-101 | 1002 | PEN-02 |
| 101 | PO-101 | 1003 | BAG-03 |

Nếu truy vấn chỉ nhằm lấy danh sách order, kết quả join có thể lặp `PO-101` ba lần. Có hai cách thường dùng:

- `SELECT DISTINCT` trên cột root cần trả.
- `WHERE EXISTS (...)` để kiểm tra có child phù hợp mà không nhân bản root rows.

Nếu cần từng child, lặp root information trong DTO mỗi hàng có thể là đúng ý định.

### 11.1. Pagination trên JOIN

Phân trang trên query join một-nhiều có thể phân trang theo hàng join, không phải theo aggregate root. Ví dụ limit 20 có thể trả 20 dòng hàng thuộc 3 đơn hàng, thay vì 20 đơn hàng.

Nếu mục tiêu là phân trang root:

1. Viết query chọn ID root phù hợp bằng `EXISTS` hoặc subquery.
2. Sắp xếp và phân trang danh sách ID.
3. Lấy dữ liệu root/DTO cho các ID đó.
4. Nếu cần child collection, tải theo một query riêng có kiểm soát.

Hoặc dùng SQL với CTE/subquery để phân trang root trước khi JOIN child. Cách viết phụ thuộc database.

Ví dụ PostgreSQL:

```sql
WITH page_of_orders AS (
    SELECT o.id
    FROM orders o
    WHERE EXISTS (
        SELECT 1
        FROM order_lines l
        WHERE l.order_id = o.id
          AND l.sku = :sku
    )
    ORDER BY o.created_at DESC, o.id DESC
    LIMIT :limit OFFSET :offset
)
SELECT o.id, o.order_code, l.sku, l.quantity
FROM page_of_orders p
JOIN orders o ON o.id = p.id
LEFT JOIN order_lines l ON l.order_id = o.id
ORDER BY o.created_at DESC, o.id DESC, l.line_index;
```

Đây là một truy vấn báo cáo cụ thể. Nó cho thấy cần xác định rõ đơn vị phân trang trước khi nối collection.

## 12. Truy vấn JOIN có tải aggregate child tự động không?

Không nên giả định một `@Query` join trả về aggregate root sẽ tự động dựng toàn bộ object graph như JPA fetch join.

Spring Data JDBC quản lý aggregate qua mapping của repository/template. Một SQL query tùy chỉnh cần được thiết kế để trả đúng hình dạng kết quả mà mapper có thể xử lý. Các cột JOIN thêm vào không tự động trở thành child object chỉ vì tên bảng có quan hệ foreign key.

Khi cần DTO báo cáo, trả DTO/projection trực tiếp thường phù hợp hơn. Khi cần aggregate đầy đủ để thực hiện domain behavior:

- Tìm root ID phù hợp bằng query chuyên biệt.
- Tải aggregate qua repository/template theo mapping.
- Thực hiện domain method.
- Lưu aggregate bằng đường persistence tương ứng.

Nếu tải nhiều root rồi gọi repository một lần cho từng root, có thể tạo N+1 query. Hãy cân nhắc batch load, query đọc chuyên biệt hoặc một read model DTO.

## 13. Vì sao không nên dùng Criteria để mô phỏng mọi loại JOIN?

Có thể cố gắng tạo một method hoặc Criteria property path trông giống quan hệ:

```java
// Không phải mô hình JOIN tổng quát:
Criteria.where("customer.displayName").is("Lan");

// Không phải cách truy vấn child collection đáng tin cậy:
Criteria.where("lines.sku").is("BOOK-01");
```

Các biểu thức này không nói rõ join table, join condition, multiplicity hoặc kết quả cần map. Dù một property path có thể được phân giải trong một mapping cụ thể, điều đó không biến Criteria thành query builder quan hệ tổng quát.

Khi cần lọc theo bảng khác, hãy viết quan hệ SQL một cách tường minh. Điều này giúp người đọc nhìn thấy:

- Điều kiện nối khóa ngoại.
- Loại JOIN.
- Điều kiện lọc.
- Khả năng duplicate.
- Đơn vị pagination.
- Kiểu dữ liệu kết quả.

## 14. Lựa chọn cách truy vấn phù hợp

| Nhu cầu | Công cụ phù hợp | Lý do |
|---|---|---|
| Predicate động trên root scalar properties | `Criteria` + `Query` | Tạo điều kiện linh hoạt theo input |
| Root query cần sort/limit | `Query` + `Sort` | Gắn thứ tự và giới hạn vào truy vấn |
| Lọc theo cột embedded đã flatten | Criteria nếu mapping/version hỗ trợ; hoặc `@Query` | Cùng bảng root, không cần JOIN |
| Lọc root theo child collection | SQL `EXISTS` hoặc JOIN | Cần truy cập bảng child |
| Lọc root theo thuộc tính aggregate reference | SQL JOIN hoặc query riêng theo ID | Cần truy cập bảng aggregate đích |
| Trả dữ liệu nhiều bảng cho màn hình | DTO/record projection | Kết quả đọc có hình dạng riêng |
| Báo cáo một hàng cho mỗi child | JOIN + DTO/RowMapper | Mỗi result row biểu diễn một child |
| Truy vấn SQL phức tạp hoặc vendor-specific | Custom repository + `JdbcTemplate` | Kiểm soát SQL và mapping |
| Thay đổi aggregate | Repository/`JdbcAggregateTemplate` | Giữ aggregate lifecycle và invariant |

### 14.1. Một quy tắc quyết định nhanh

Hãy tự hỏi: **cột cần lọc nằm ở bảng nào?**

- Nếu nằm ở bảng aggregate root, thử Criteria.
- Nếu nằm trong embedded value object đã flatten vào root, xác định cột vật lý và kiểm tra khả năng mapping; SQL tường minh là lựa chọn rõ ràng khi cần tính ổn định.
- Nếu nằm ở bảng child hoặc aggregate root khác, dùng JOIN/EXISTS bằng SQL.
- Nếu kết quả cần dữ liệu từ nhiều bảng, trả DTO/projection thay vì cố ép thành aggregate.
- Nếu cần sửa domain state, tải aggregate và lưu qua repository/template.

## 15. Kiểm thử Criteria và JOIN

Criteria và SQL join cần được kiểm tra với database thực tế hoặc database test có cùng dialect/schema.

### 15.1. Test Criteria trên root

```java
@DataJdbcTest
class PurchaseOrderCriteriaTest {

    @Autowired
    JdbcAggregateTemplate template;

    @Test
    void findsNewOrdersCreatedInRange() {
        Criteria criteria = Criteria.where("status").is(OrderStatus.NEW)
                .and("createdAt").greaterThanOrEquals(
                        LocalDateTime.parse("2026-01-01T00:00:00")
                );

        Query query = Query.query(criteria);

        List<PurchaseOrder> result =
                template.findAll(query, PurchaseOrder.class);

        assertThat(result)
                .allMatch(order -> order.getStatus() == OrderStatus.NEW);
    }
}
```

Test cần fixture và schema tương ứng. Nó kiểm tra predicate trên root property, không kiểm tra JOIN qua child.

### 15.2. Test EXISTS theo child

Tạo hai đơn hàng:

- Order A có dòng `BOOK-01`.
- Order B chỉ có dòng `PEN-02`.

Chạy query `EXISTS` với `sku = BOOK-01`, xác nhận chỉ Order A được trả về. Thêm trường hợp Order A có hai dòng `BOOK-01` để xác nhận root không bị lặp.

### 15.3. Test DTO cho JOIN

Nếu query trả `OrderLineSearchResult`, xác nhận:

- Alias của mỗi cột khớp DTO mapping.
- Số result row đúng theo số child thỏa điều kiện.
- Root có nhiều child tạo nhiều DTO nếu đó là mục tiêu.
- Giá trị nullable được map vào wrapper type.
- Sort có tie-breaker ổn định.

### 15.4. Test pagination

Nếu query phân trang root qua JOIN một-nhiều, tạo một root có nhiều child và nhiều root khác nhau. Xác nhận mỗi trang có số root như mong đợi, không phải số row JOIN. Nếu pagination đang áp dụng lên row child, hãy sửa query để phân trang root trước.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Criteria không tìm thấy property | Dùng tên cột thay vì property Java hoặc property không persistent | Kiểm tra mapping và dùng property name |
| `Criteria.where("lines.sku")` không hoạt động | Child collection nằm ở bảng khác; Criteria không tự JOIN | Dùng `EXISTS`/JOIN trong SQL |
| Criteria không lọc được theo tên Customer | Root chỉ lưu customer ID/reference | JOIN `customers` hoặc query Customer riêng |
| Dùng Criteria như JPA `root.join(...)` | Nhầm hai API | Dùng SQL hoặc custom repository |
| JOIN trả cùng order nhiều lần | Một root khớp nhiều child rows | Dùng `EXISTS`, `DISTINCT` hoặc DTO theo từng child |
| Pagination trả ít order hơn mong đợi | Limit áp dụng lên hàng JOIN | Phân trang root trước rồi JOIN |
| `@Query` trả root nhưng child collection rỗng/không như mong đợi | SQL tùy chỉnh không tự tạo aggregate graph đầy đủ | Tải aggregate qua repository hoặc trả DTO |
| Alias DTO không map | Column label không khớp naming strategy | Đặt alias rõ, kiểm tra ResultSet metadata |
| Nested embedded path không được phân giải | Khác biệt mapping/version hoặc property path không được hỗ trợ | Dùng tên cột flattened trong SQL và integration test |
| Query chậm sau khi thêm JOIN | Thiếu index hoặc join cardinality lớn | Xem execution plan và index FK/filter |
| Dùng `SELECT *` bị trùng column labels | Nhiều bảng có cột cùng tên | Chọn cột cụ thể và alias riêng |

## 17. Nguyên tắc ghi nhớ

- `Criteria` và `Query` của Spring Data Relational là công cụ xây dựng predicate và các tùy chọn truy vấn; chúng không phải JPA Criteria API.
- Criteria phù hợp nhất với điều kiện trên property được mapping trong phạm vi aggregate root.
- `@MappedCollection` lưu child ở bảng riêng; Criteria không tự JOIN bảng child chỉ vì có collection trong Java.
- `AggregateReference` giữ ID tham chiếu; Criteria không tự tải aggregate đích hoặc join theo thuộc tính của nó.
- `@Embedded` flatten value object vào cột root; đó là mapping cùng hàng, không phải quan hệ JOIN.
- Khi lọc theo child hoặc aggregate khác, viết `JOIN`/`EXISTS` bằng `@Query` SQL hoặc custom repository.
- Khi JOIN một-nhiều, xác định rõ muốn một hàng cho mỗi root hay một hàng cho mỗi child; dùng `EXISTS`, `DISTINCT` hoặc DTO tương ứng.
- Pagination cần áp dụng đúng đơn vị dữ liệu; phân trang root trước khi join collection nếu mục tiêu là danh sách aggregate.
- Query join trả DTO thường dễ kiểm soát hơn việc kỳ vọng custom SQL tự dựng toàn bộ aggregate graph.
- Kiểm tra mapping, alias, SQL dialect, index và pagination bằng integration test.

Criteria giúp xây dựng truy vấn động gọn gàng khi bộ lọc nằm trên các property của aggregate root. Khi điều kiện đi qua bảng child hoặc aggregate root khác, hãy chuyển sang SQL tường minh để mô tả join key, cardinality và hình dạng kết quả. Phân biệt rõ object mapping với query planning sẽ giúp thiết kế truy vấn đúng và tránh kỳ vọng sai về khả năng tự động JOIN của Spring Data JDBC.

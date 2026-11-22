# CriteriaBuilder, CriteriaQuery, Root và Predicate

## 1. Vì sao cần Criteria API khi đã có HQL?

Giả sử ứng dụng quản lý đơn hàng cung cấp màn hình tìm kiếm với nhiều điều kiện tùy chọn:

- Chỉ hiển thị đơn có trạng thái `PAID` hoặc `SHIPPED`.
- Có thể nhập một phần mã đơn hàng.
- Có thể lọc theo khách hàng, số tiền tối thiểu/tối đa.
- Có thể chọn khoảng thời gian tạo.
- Có thể sắp xếp theo ngày hoặc tổng tiền.
- Phải trả dữ liệu có phân trang cùng tổng số kết quả.

Nếu dùng HQL, lập trình viên có thể lắp chuỗi query tùy theo bộ lọc:

```java
String hql = "select o from PurchaseOrder o where 1 = 1";
if (status != null) {
    hql += " and o.status = :status";
}
if (minAmount != null) {
    hql += " and o.totalAmount >= :minAmount";
}
```

Cách viết trên có thể hoạt động, nhưng khi số điều kiện, nhóm `AND`/`OR`, association join và sort tăng lên, việc quản lý cú pháp, alias và tham số trở nên khó bảo trì. Nối trực tiếp giá trị từ người dùng vào query còn tạo nguy cơ injection.

**Jakarta Persistence Criteria API** cho phép mô tả truy vấn bằng **cây biểu thức Java**. Thay vì tạo chuỗi HQL, ta xây dựng cấu trúc thể hiện lựa chọn dữ liệu, đường dẫn thuộc tính, điều kiện lọc và kiểu kết quả.

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Predicate paid = cb.equal(order.get("status"), OrderStatus.PAID);
Predicate enough = cb.greaterThanOrEqualTo(
    order.get("totalAmount"),
    new BigDecimal("100000")
);

cq.select(order).where(cb.and(paid, enough));

List<PurchaseOrder> result =
    entityManager.createQuery(cq).getResultList();
```

Đoạn code ngắn này cho thấy bốn thành phần cốt lõi:

| Thành phần | Vai trò | Hình dung tương ứng trong HQL |
|---|---|---|
| `CriteriaBuilder` | Nhà máy tạo query và biểu thức, phép so sánh, hàm, điều kiện | Cú pháp `=`, `AND`, `SUM`, `LIKE`... |
| `CriteriaQuery<T>` | Bản mô tả truy vấn SELECT và kiểu kết quả `T` | Toàn bộ `SELECT ... FROM ... WHERE ...` |
| `Root<X>` | Entity gốc trong mệnh đề FROM, làm điểm xuất phát cho đường dẫn thuộc tính | `from PurchaseOrder o` |
| `Predicate` | Biểu thức điều kiện boolean có thể ghép với nhau | `o.status = ... and o.totalAmount >= ...` |

Bài học này hướng tới Hibernate ORM qua Jakarta Persistence Criteria API. Ví dụ sử dụng `jakarta.persistence.*`, thích hợp với Jakarta Persistence 3.x/Hibernate ORM 6.x. Dự án dùng Hibernate 5.x hoặc JPA 2.x thường cần namespace `javax.persistence.*`; không đổi namespace mà không kiểm tra dependency và phiên bản.

## 2. Mô hình ví dụ xuyên suốt

Để thấy Criteria API trong một tình huống thực tế, ta sử dụng hệ thống quản lý đơn hàng:

```text
Customer (1) -------- (N) PurchaseOrder (1) -------- (N) OrderLine
   id                        id                         id
   name                      orderNumber                quantity
   email                     status                     unitPrice
                             totalAmount
                             createdAt
                             customer_id (FK)
```

### 2.1. Enum trạng thái

```java
package com.example.orders;

public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
```

### 2.2. Customer

```java
package com.example.orders;

import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    protected Customer() {}

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

### 2.3. PurchaseOrder

```java
package com.example.orders;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false,
            precision = 18, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public String getOrderNumber() { return orderNumber; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public Instant getCreatedAt() { return createdAt; }
    public Customer getCustomer() { return customer; }
    public List<OrderLine> getLines() { return lines; }
}
```

### 2.4. OrderLine

```java
package com.example.orders;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal unitPrice;
}
```

Các ví dụ sau giả định những entity trên đã được mapping và database có dữ liệu thích hợp. Những đoạn Java độc lập bên dưới có thể cần import `jakarta.persistence.criteria.*`, `jakarta.persistence.*` và các kiểu `java.util` tương ứng.

## 3. CriteriaBuilder: nhà máy tạo biểu thức

Đầu tiên lấy `CriteriaBuilder` từ `EntityManager`:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
```

`CriteriaBuilder` tạo những đối tượng Criteria như:

```java
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

CriteriaQuery<Long> countQuery =
    cb.createQuery(Long.class);

CriteriaQuery<Tuple> tupleQuery =
    cb.createTupleQuery();
```

Nó cũng tạo predicate:

```java
Predicate equalStatus = cb.equal(
    order.get("status"),
    OrderStatus.PAID
);

Predicate enoughAmount = cb.ge(
    order.get("totalAmount"),
    new BigDecimal("100000")
);
```

Và nhiều loại biểu thức khác:

- So sánh: `equal`, `notEqual`, `greaterThan`, `lessThan`, `between`.
- Boolean: `and`, `or`, `not`, `conjunction`, `disjunction`.
- Null: `isNull`, `isNotNull`.
- String: `like`, `lower`, `upper`, `concat`, `length`.
- Toán học: `sum`, `avg`, `prod`, `diff`, `count`.
- Aggregate: `countDistinct`, `min`, `max`.
- Sort: `asc`, `desc`.
- Projection: `construct`, `array`, `tuple`.
- Parameter: `parameter`.
- Expression: `coalesce`, `selectCase` và các hàm hỗ trợ khác.

**`CriteriaBuilder` không tự chạy SQL.** Nó xây các nút trong cây truy vấn. SQL chỉ được Hibernate chuẩn bị/thực thi khi tạo `TypedQuery` và gọi phương thức như `getResultList()` hoặc `getSingleResult()`.

## 4. CriteriaQuery<T>: bản thiết kế của một SELECT

`CriteriaQuery<T>` mang kiểu kết quả `T`:

```java
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
```

Nó nhận các thành phần như:

- `from(...)` — nguồn entity để truy vấn.
- `select(...)` hoặc `multiselect(...)` — chọn dữ liệu trả về.
- `where(...)` — điều kiện lọc.
- `groupBy(...)` và `having(...)` — gom nhóm.
- `orderBy(...)` — sắp xếp.
- `distinct(true)` — loại trùng theo semantics truy vấn.
- `subquery(...)` — tạo truy vấn con.

Ví dụ:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> query =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root = query.from(PurchaseOrder.class);

query.select(root);
query.where(cb.equal(root.get("status"), OrderStatus.PAID));
query.orderBy(cb.desc(root.get("createdAt")));

TypedQuery<PurchaseOrder> typedQuery =
    entityManager.createQuery(query);

List<PurchaseOrder> orders = typedQuery.getResultList();
```

Tương đương HQL về ý nghĩa:

```hql
select o
from PurchaseOrder o
where o.status = :status
order by o.createdAt desc
```

`CriteriaQuery` mô tả câu SELECT; nó **khác** `TypedQuery`:

| Kiểu | Công việc |
|---|---|
| `CriteriaQuery<T>` | Xây cấu trúc query |
| `TypedQuery<T>` | Đặt parameter, phân trang, timeout và thực thi query |
| `CriteriaUpdate<T>` | Mô tả bulk UPDATE, không phải SELECT |
| `CriteriaDelete<T>` | Mô tả bulk DELETE, không phải SELECT |

Không nhầm tạo `CriteriaQuery` với hành động gửi SQL. Trước `entityManager.createQuery(...)` và thực thi, đây vẫn là cấu trúc mô tả truy vấn.

## 5. Root<X>: điểm xuất phát của đường dẫn thuộc tính

Tạo root:

```java
Root<PurchaseOrder> order =
    query.from(PurchaseOrder.class);
```

Root tương ứng với alias `o` trong:

```hql
from PurchaseOrder o
```

Từ root, ta điều hướng tới thuộc tính:

```java
Path<Long> idPath = order.get("id");
Path<OrderStatus> statusPath = order.get("status");
Path<BigDecimal> amountPath = order.get("totalAmount");
```

Với cách dùng string `get("fieldName")`, compiler Java không thể bảo đảm tên field đúng. Nếu đổi `totalAmount` thành `grandTotal`, những string cũ có thể chỉ lỗi khi query được xây/biên dịch bởi provider lúc chạy.

### Root khác object entity đang được tải

`Root<PurchaseOrder>` **không phải** một PurchaseOrder object với dữ liệu thực tế. Nó là biểu thức đại diện cho những hàng sẽ được SELECT:

```text
Root<PurchaseOrder>
  |
  +-- get("id")          -> Path<Long>
  +-- get("status")      -> Path<OrderStatus>
  +-- get("totalAmount") -> Path<BigDecimal>
  +-- get("customer")    -> Path<Customer>/joinable association
```

Không gọi `order.get("status")` rồi chờ nhận `OrderStatus.PAID`. Kết quả chỉ là `Path`, dùng để ghép predicate và selection.

### Có thể có nhiều root

Criteria API cho phép:

```java
Root<PurchaseOrder> order = query.from(PurchaseOrder.class);
Root<Customer> customer = query.from(Customer.class);
```

Nhưng nhiều root độc lập có thể tạo **Cartesian product** trước khi áp predicate liên kết. Nếu đã có association `PurchaseOrder.customer`, thường nên dùng `join` thay vì tạo root độc lập.

## 6. Predicate: một điều kiện có thể ghép với điều kiện khác

`Predicate` thuộc `jakarta.persistence.criteria.Predicate`, không phải `java.util.function.Predicate` trong Java Streams.

Ví dụ:

```java
Predicate isPaid = cb.equal(
    order.get("status"),
    OrderStatus.PAID
);

Predicate bigOrder = cb.greaterThan(
    order.get("totalAmount"),
    new BigDecimal("500000")
);

Predicate condition = cb.and(isPaid, bigOrder);
```

Ý nghĩa logic:

\[
(\text{status}=\text{PAID}) \land
(\text{totalAmount}>500000)
\]

HQL tương đương:

```hql
where o.status = :status
  and o.totalAmount > :minimum
```

`Predicate` là một đối tượng đại diện biểu thức boolean trong cây Criteria. Các phép `cb.and(...)`, `cb.or(...)`, `cb.not(...)` tạo thêm biểu thức trong cây; không thực thi SQL ngay.

### Những phương thức nền tảng

| API | Ví dụ | Ý nghĩa |
|---|---|---|
| `cb.equal(a, b)` | `cb.equal(order.get("status"), PAID)` | Bằng nhau |
| `cb.notEqual(a, b)` | `cb.notEqual(order.get("status"), CANCELLED)` | Khác nhau |
| `cb.greaterThan(a, b)` | So sánh `Instant` hoặc số có `Comparable` | Lớn hơn |
| `cb.greaterThanOrEqualTo(a, b)` | `createdAt >= from` | Lớn hơn hoặc bằng |
| `cb.lessThan(a, b)` | `createdAt < until` | Nhỏ hơn |
| `cb.between(a, low, high)` | Khoảng đóng hai đầu | Từ low đến high, bao gồm biên |
| `cb.isNull(a)` | `customer == NULL` theo SQL | Là NULL |
| `cb.isNotNull(a)` | Không NULL | Có giá trị |
| `cb.like(a, pattern)` | `%ABC%` | Khớp mẫu |
| `a.in(values)` | `status IN (...)` | Thuộc tập |
| `cb.and(p1, p2)` | `p1 AND p2` | Tất cả cùng đúng |
| `cb.or(p1, p2)` | `p1 OR p2` | Ít nhất một đúng |
| `cb.not(p)` | `NOT p` | Phủ định |

## 7. AND, OR và dấu ngoặc logic: nguồn lỗi phổ biến

Giả sử yêu cầu:

> Đơn có trạng thái PAID **hoặc** SHIPPED, **và** tổng tiền từ 500.000 trở lên.

Biểu thức cần là:

\[
(\text{PAID} \lor \text{SHIPPED}) \land
(\text{amount} \ge 500000)
\]

Criteria:

```java
Predicate allowedStatuses = cb.or(
    cb.equal(order.get("status"), OrderStatus.PAID),
    cb.equal(order.get("status"), OrderStatus.SHIPPED)
);

Predicate amountThreshold = cb.ge(
    order.get("totalAmount"),
    new BigDecimal("500000")
);

query.where(cb.and(allowedStatuses, amountThreshold));
```

Nếu viết:

```java
query.where(cb.or(
    cb.equal(order.get("status"), OrderStatus.PAID),
    cb.and(
        cb.equal(order.get("status"), OrderStatus.SHIPPED),
        amountThreshold
    )
));
```

logic trở thành:

\[
\text{PAID} \lor
(\text{SHIPPED} \land \text{amount}\ge500000)
\]

Điều này cho phép **mọi** đơn PAID, kể cả dưới 500.000, lọt qua. Criteria không tự hiểu ý nghĩa nghiệp vụ; cấu trúc cây `and/or` quyết định dấu ngoặc.

### Cách viết rõ

Tạo các nhóm predicate với tên phản ánh nghiệp vụ:

```java
Predicate matchingStatus = cb.or(paid, shipped);
Predicate matchingAmount = cb.ge(amount, minimum);
Predicate finalFilter = cb.and(matchingStatus, matchingAmount);
```

Tên biến rõ giúp bảo trì tốt hơn so với một biểu thức lồng `cb.and(cb.or(...), ...)` quá dài.

## 8. Hai predicate đặc biệt: conjunction và disjunction

CriteriaBuilder có:

```java
Predicate alwaysTrue = cb.conjunction();
Predicate alwaysFalse = cb.disjunction();
```

Theo ngữ nghĩa API:

- `cb.conjunction()` là predicate không điều kiện với giá trị **TRUE**.
- `cb.disjunction()` là predicate không điều kiện với giá trị **FALSE**.
- `cb.and()` với **0 predicate** có kết quả TRUE.
- `cb.or()` với **0 predicate** có kết quả FALSE.

Điều này hữu ích khi xây bộ lọc động:

```java
List<Predicate> predicates = new ArrayList<>();

if (status != null) {
    predicates.add(cb.equal(
        order.get("status"), status
    ));
}

Predicate combined =
    cb.and(predicates.toArray(Predicate[]::new));

query.where(combined);
```

Nếu không có filter nào, `combined` mang ngữ nghĩa TRUE, nghĩa là không loại thêm hàng.

### Không nhầm AND rỗng với OR rỗng

Giả sử người dùng chọn một danh sách status, nhưng danh sách rỗng:

- Nếu **rỗng nghĩa là bỏ qua lọc status**, không thêm predicate.
- Nếu **rỗng nghĩa là không có status nào hợp lệ**, thêm `cb.disjunction()` để trả kết quả rỗng.

Đây là **quyết định nghiệp vụ**, không phải lỗi cú pháp. Phải định nghĩa ý nghĩa của tập rỗng trước khi tạo Criteria.

## 9. where() thay thế điều kiện trước đó: không gọi liên tiếp để cộng dồn

Một lỗi thường thấy:

```java
query.where(cb.equal(order.get("status"), OrderStatus.PAID));
query.where(cb.ge(order.get("totalAmount"), minimum));
```

Trong Criteria API, lời gọi `where(...)` sau sẽ **thay thế tập restriction trước**, không tự động nối AND. Kết quả có thể chỉ còn lọc số tiền.

Hãy tích lũy predicate trước:

```java
List<Predicate> conditions = new ArrayList<>();

conditions.add(
    cb.equal(order.get("status"), OrderStatus.PAID)
);
conditions.add(
    cb.ge(order.get("totalAmount"), minimum)
);

query.where(cb.and(conditions.toArray(Predicate[]::new)));
```

Hoặc gộp một lần:

```java
query.where(
    cb.equal(order.get("status"), OrderStatus.PAID),
    cb.ge(order.get("totalAmount"), minimum)
);
```

Overload `where(Predicate...)` có thể kết hợp nhiều predicate bằng AND. Khi dùng `where` với mảng rỗng, nó có thể xóa restrictions đang có; vì vậy một pipeline build query nên xây **toàn bộ** điều kiện trước rồi thiết lập một lần.

## 10. Bộ lọc động: ví dụ từ yêu cầu người dùng

Thiết kế command tìm kiếm:

```java
public record OrderSearch(
    String orderNumberContains,
    OrderStatus status,
    Long customerId,
    BigDecimal minAmount,
    BigDecimal maxAmount,
    Instant createdFromInclusive,
    Instant createdUntilExclusive
) {}
```

Điều kiện nghiệp vụ:

- `null` ở một field nghĩa là **không áp dụng filter**.
- Chuỗi rỗng hoặc toàn khoảng trắng được xem như không nhập.
- `minAmount > maxAmount` là input không hợp lệ, nên từ chối trước khi chạy query.
- `createdFromInclusive >= createdUntilExclusive` là khoảng không hợp lệ nếu yêu cầu khoảng thời gian có độ dài dương.

### 10.1. Bản triển khai đơn giản

```java
public List<PurchaseOrder> search(
        EntityManager em,
        OrderSearch search) {

    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<PurchaseOrder> cq =
        cb.createQuery(PurchaseOrder.class);
    Root<PurchaseOrder> order =
        cq.from(PurchaseOrder.class);

    List<Predicate> predicates = new ArrayList<>();

    if (search.status() != null) {
        predicates.add(cb.equal(
            order.get("status"),
            search.status()
        ));
    }

    if (search.customerId() != null) {
        predicates.add(cb.equal(
            order.get("customer").get("id"),
            search.customerId()
        ));
    }

    if (search.minAmount() != null) {
        predicates.add(cb.ge(
            order.get("totalAmount"),
            search.minAmount()
        ));
    }

    if (search.maxAmount() != null) {
        predicates.add(cb.le(
            order.get("totalAmount"),
            search.maxAmount()
        ));
    }

    if (search.createdFromInclusive() != null) {
        predicates.add(cb.greaterThanOrEqualTo(
            order.get("createdAt"),
            search.createdFromInclusive()
        ));
    }

    if (search.createdUntilExclusive() != null) {
        predicates.add(cb.lessThan(
            order.get("createdAt"),
            search.createdUntilExclusive()
        ));
    }

    cq.select(order).where(
        cb.and(predicates.toArray(Predicate[]::new))
    );
    cq.orderBy(
        cb.desc(order.get("createdAt")),
        cb.desc(order.get("id"))
    );

    return em.createQuery(cq).getResultList();
}
```

Đây là khuôn mẫu cốt lõi:

1. Tạo một `CriteriaBuilder`, `CriteriaQuery` và `Root`.
2. Tạo `List<Predicate>`.
3. Chỉ thêm các điều kiện được người dùng cung cấp và hợp lệ.
4. Ghép một lần bằng `cb.and(...)`.
5. Chọn dữ liệu, thứ tự, rồi thực thi.

### 10.2. Bộ lọc chuỗi LIKE

Thêm tìm kiếm mã đơn hàng:

```java
String fragment = search.orderNumberContains();

if (fragment != null && !fragment.isBlank()) {
    String term = fragment.strip().toLowerCase(Locale.ROOT);

    predicates.add(cb.like(
        cb.lower(order.get("orderNumber")),
        "%" + term + "%"
    ));
}
```

Đây là **pattern matching**. Nếu input có `%` hoặc `_`, chúng có thể được database hiểu là wildcard thay vì ký tự thông thường.

Nếu yêu cầu **tìm chuỗi con nguyên văn**, phải escape wildcard theo dialect hoặc dùng overload `cb.like(expression, pattern, escapeChar)` và xây pattern đã escape đúng. Ví dụ SQL LIKE phổ biến dùng dấu `\` làm escape character, nhưng khả năng và cách diễn giải tùy database/collation. Không cần tự nối input vào SQL; input vẫn phải được bind hoặc biểu diễn như giá trị trong Criteria.

### 10.3. Case-insensitive search không đồng nghĩa chuẩn hóa Unicode

`cb.lower(...)` là cách phổ biến, nhưng hành vi chữ hoa/chữ thường phụ thuộc DB collation và hàm LOWER. Với dữ liệu đa ngôn ngữ, các cách dấu, normalization và locale có thể cần chiến lược tìm kiếm riêng (collation, normalized column, full-text search).

Nếu bộ lọc thường dùng trên bảng lớn, áp dụng `LOWER(column)` có thể cần functional index hoặc một giải pháp tìm kiếm được DB hỗ trợ; đừng chỉ nhìn số dòng Java để đánh giá hiệu năng.

## 11. Khoảng thời gian: BETWEEN hay nửa mở?

`between` bao gồm cả hai biên trong SQL:

```java
Predicate inRange = cb.between(
    order.get("createdAt"),
    from,
    until
);
```

Tương đương ý tưởng:

```sql
created_at BETWEEN :from AND :until
```

Với thời gian, nhiều API dùng khoảng **nửa mở**:

\[
\text{from} \le \text{createdAt} < \text{until}
\]

Criteria:

```java
Predicate timeWindow = cb.and(
    cb.greaterThanOrEqualTo(
        order.get("createdAt"), from
    ),
    cb.lessThan(
        order.get("createdAt"), until
    )
);
```

Khoảng nửa mở giúp tránh tình huống một mốc thời gian chính xác nằm trong **hai** khung báo cáo liên tiếp khi biên cuối của khung trước cũng là biên đầu của khung sau.

Nếu filter đến từ ngày theo timezone của người dùng, cần chuyển khoảng ngày thành `Instant` đúng timezone trước khi bind, không so sánh tùy tiện string ngày với timestamp.

## 12. So sánh với NULL phải dùng isNull()/isNotNull()

SQL không xem `column = NULL` là một so sánh boolean bình thường. Hãy dùng:

```java
Predicate noCustomer = cb.isNull(
    order.get("customer")
);

Predicate hasCustomer = cb.isNotNull(
    order.get("customer")
);
```

Không dựa vào:

```java
cb.equal(order.get("customer"), null);
```

rồi giả định mọi provider/dialect luôn dịch đúng giống `IS NULL`. Ngữ nghĩa SQL NULL cần được thể hiện rõ ràng bằng `isNull` và `isNotNull`.

### NULL và NOT trong SQL

Đặc biệt với cột nullable:

```java
cb.not(cb.equal(order.get("status"), OrderStatus.PAID))
```

không có nghĩa cột `status = NULL` sẽ tự thỏa điều kiện. SQL sử dụng **three-valued logic**: TRUE, FALSE và UNKNOWN. Điều kiện WHERE chỉ giữ hàng khi biểu thức là TRUE.

Nếu muốn bao gồm cả giá trị NULL:

```java
Predicate notPaidOrNull = cb.or(
    cb.notEqual(order.get("status"), OrderStatus.PAID),
    cb.isNull(order.get("status"))
);
```

Trong mô hình ví dụ `status` không nullable, nhưng nguyên tắc này quan trọng cho các field optional khác.

## 13. IN và tập giá trị động

Giả sử API nhận danh sách trạng thái:

```java
Set<OrderStatus> statuses =
    Set.of(OrderStatus.PAID, OrderStatus.SHIPPED);
```

Có thể viết:

```java
Predicate statusIn = order.get("status").in(statuses);
```

Ý nghĩa:

```sql
status IN (?, ?)
```

Hoặc dùng CriteriaBuilder:

```java
CriteriaBuilder.In<OrderStatus> in = cb.in(
    order.<OrderStatus>get("status")
);

for (OrderStatus status : statuses) {
    in.value(status);
}

Predicate statusIn = in;
```

### Nếu danh sách rỗng

Không mặc định tạo câu SQL `IN ()` vì tính hợp lệ và semantics của tập rỗng khác nhau giữa database/provider.

Quy định rõ:

- Rỗng = **không lọc status**: bỏ qua predicate.
- Rỗng = **không có status hợp lệ**: dùng `cb.disjunction()`, tương đương FALSE.
- Input rỗng là không hợp lệ: từ chối tại validation layer.

Không dùng `IN` trên danh sách cực lớn mà không đo tác động. Database có thể giới hạn số bind parameters; batch, bảng tạm hoặc join với danh sách ID có thể phù hợp hơn.

## 14. Kiểu an toàn hơn với static metamodel

Khi dùng tên thuộc tính dạng chuỗi:

```java
order.get("totalAmount");
```

Java compiler không phát hiện typo:

```java
order.get("totlaAmount");
```

Jakarta Persistence Static Metamodel cho phép tham chiếu thuộc tính đã được sinh:

```java
order.get(PurchaseOrder_.totalAmount);
order.get(PurchaseOrder_.status);
order.get(PurchaseOrder_.createdAt);
```

Metamodel class có thể mang hình thức:

```java
@StaticMetamodel(PurchaseOrder.class)
public abstract class PurchaseOrder_ {
    public static volatile SingularAttribute<
        PurchaseOrder, BigDecimal> totalAmount;

    public static volatile SingularAttribute<
        PurchaseOrder, OrderStatus> status;

    public static volatile SingularAttribute<
        PurchaseOrder, Instant> createdAt;
}
```

Đây là minh họa cấu trúc, **không phải class nên viết thủ công**. Thực tế, annotation processor (chẳng hạn Hibernate JPA Metamodel Generator theo phiên bản phù hợp) có thể sinh metamodel từ entity source.

Ưu điểm:

- Trình biên dịch phát hiện tên thuộc tính không còn tồn tại.
- IDE có autocompletion và refactoring tốt hơn.
- Kiểu của Path thường rõ hơn so với `get("field")`.

Đổi lại:

- Phải cấu hình annotation processing/build đúng.
- Có thêm source generated theo phiên bản framework.
- Không phải mọi kiểu query động đều cần static metamodel; một số dự án chọn DSL khác.

Trong bài này tiếp tục dùng tên string ở nhiều ví dụ cho dễ đọc, nhưng với dự án lớn có nhiều Criteria, metamodel typed là lựa chọn đáng cân nhắc.

## 15. ParameterExpression: khai báo tham số thay vì nhúng giá trị

Criteria API cho phép tạo parameter:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

ParameterExpression<OrderStatus> statusParam =
    cb.parameter(OrderStatus.class, "status");

cq.select(order).where(
    cb.equal(order.get("status"), statusParam)
);

TypedQuery<PurchaseOrder> query = em.createQuery(cq);
query.setParameter("status", OrderStatus.PAID);

List<PurchaseOrder> result = query.getResultList();
```

Hoặc:

```java
query.setParameter(statusParam, OrderStatus.PAID);
```

`ParameterExpression` có ý nghĩa khi cần phân biệt **query shape** và **giá trị truyền vào**. Provider quyết định cách tạo bind parameters cho những giá trị khác được dùng trong Criteria.

### Không nối dữ liệu không tin cậy thành field name

Cho dù Criteria API giúp tránh việc ghép SQL từ **giá trị**, nó vẫn có thể bị lạm dụng:

```java
order.get(userSuppliedPropertyName);
```

Không cho người dùng chọn tùy ý path/attribute nội bộ. Nếu cần sort/filter field từ API, dùng **allow-list** và ánh xạ field public sang thuộc tính entity được phép truy vấn.

## 16. Join từ Root: điều hướng association có chủ đích

Giả sử muốn tìm đơn thuộc những khách hàng có tên chứa “Nguyen”.

Có thể tạo join:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.INNER);

Predicate customerName = cb.like(
    cb.lower(customer.get("name")),
    "%nguyen%"
);

cq.select(order).where(customerName);
```

Tương đương HQL:

```hql
select o
from PurchaseOrder o
join o.customer c
where lower(c.name) like :customerName
```

### JoinType.INNER và LEFT khác gì?

| Join type | Ý nghĩa |
|---|---|
| `INNER` | Chỉ giữ root có association khớp |
| `LEFT` | Có thể giữ root không có association khớp; thuộc tính join phía phải là NULL |
| `RIGHT` | Được mô tả trong Criteria API nhưng khả năng hỗ trợ có thể khác giữa provider/dialect |

Trong mô hình ví dụ, customer bắt buộc. Với các association optional, INNER JOIN có thể vô tình loại root; hãy chọn join type theo yêu cầu nghiệp vụ.

### Root và Join đều cung cấp đường dẫn

`root.get("status")` đi từ entity Order.

`customer.get("name")` đi từ Customer được join.

Đừng tạo nhiều Join giống hệt một cách không cần thiết trong các helper predicates, vì SQL có thể có thêm join hoặc biến đổi cardinality. Có thể truyền cùng `Join` hoặc quản lý join theo tên/path khi xây query phức tạp.

## 17. INNER JOIN và LEFT JOIN: bẫy WHERE làm mất hàng

Giả sử Order có voucher tùy chọn:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Voucher voucher;
```

Ứng dụng muốn lấy **mọi** đơn, kèm thông tin voucher nếu có:

```java
Join<PurchaseOrder, Voucher> voucher =
    order.join("voucher", JoinType.LEFT);
```

Nếu thêm:

```java
Predicate activeVoucher = cb.isTrue(
    voucher.get("active")
);
cq.where(activeVoucher);
```

thì những Order không có Voucher có `voucher.active` là NULL và sẽ **không** vượt qua WHERE. Về kết quả, truy vấn có thể hành xử tương tự inner join đối với điều kiện ấy.

Nếu cần giữ cả đơn không có voucher, phải biểu đạt logic:

```java
Predicate noVoucher = cb.isNull(
    voucher.get("id")
);

Predicate allowed = cb.or(
    noVoucher,
    cb.isTrue(voucher.get("active"))
);
```

Hoặc đặt predicate phù hợp vào `Join#on(...)` khi mục tiêu chỉ hạn chế những hàng join, không lọc root:

```java
voucher.on(cb.isTrue(voucher.get("active")));
```

Vị trí predicate tại `ON` và `WHERE` có semantics khác nhau đối với LEFT JOIN. Không nên dùng một builder helper chung rồi tùy tiện chuyển điều kiện giữa hai vị trí.

## 18. Join to-many và trùng lặp kết quả

Tìm các Order có ít nhất một OrderLine với SKU “SKU-A”:

```java
Join<PurchaseOrder, OrderLine> line =
    order.join("lines", JoinType.INNER);

cq.select(order).where(
    cb.equal(line.get("sku"), "SKU-A")
);
```

Nếu một đơn có **hai** line cùng SKU-A, join SQL có thể trả hai hàng của cùng đơn. Tùy selection/provider, kết quả query có thể lặp entity reference hoặc Hibernate xử lý dedup trong một số trường hợp; không nên dựa vào hành vi tự loại trùng khi không diễn đạt rõ nhu cầu.

Có thể dùng:

```java
cq.select(order).distinct(true);
```

để yêu cầu kết quả DISTINCT theo semantics Criteria.

### Đừng chỉ bật distinct rồi quên query plan

`DISTINCT` có thể làm database sort/hash nhiều hàng, hoặc Hibernate thực hiện xử lý kết quả theo cách phụ thuộc phiên bản và query shape. Nếu chỉ cần xác nhận một order **tồn tại ít nhất một line phù hợp**, một `EXISTS` subquery có thể phù hợp hơn vì không nhân số hàng root:

```hql
select o
from PurchaseOrder o
where exists (
    select 1
    from OrderLine l
    where l.order = o and l.sku = :sku
)
```

Tiếp theo sẽ xây cùng ngữ nghĩa bằng Criteria subquery.

## 19. EXISTS subquery bằng Criteria API

Ví dụ tìm Order có ít nhất một line với SKU cần tìm:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Subquery<Long> sq = cq.subquery(Long.class);
Root<OrderLine> line = sq.from(OrderLine.class);

sq.select(cb.literal(1L));
sq.where(
    cb.equal(line.get("order"), order),
    cb.equal(line.get("sku"), "SKU-A")
);

cq.select(order).where(cb.exists(sq));

List<PurchaseOrder> result =
    em.createQuery(cq).getResultList();
```

`order` được tham chiếu từ query ngoài trong predicate của subquery, tạo **correlated condition** về mặt logic.

Nếu cần biểu diễn correlation bằng API tường minh, `Subquery#correlate(...)` có overload cho root/join phù hợp. Có thể dùng nó khi query con cần đường dẫn từ root/join của query cha và muốn diễn đạt correlation rõ.

### Tại sao EXISTS hay hơn JOIN trong trường hợp này?

Ta chỉ cần biết **có hay không** ít nhất một matching line, không cần trả từng dòng line. `EXISTS` thể hiện ý nghĩa đó và tránh nhân số hàng Order trong result shape. Database optimizer vẫn quyết định SQL plan hiệu quả; hãy đo trên dữ liệu thật.

## 20. ORDER BY động: không nhận tên cột tùy ý từ client

Ví dụ yêu cầu sort theo `createdAt` hoặc `totalAmount`, tăng hoặc giảm:

```java
public enum OrderSortField {
    CREATED_AT,
    TOTAL_AMOUNT,
    ORDER_NUMBER
}

public enum SortDirection {
    ASC,
    DESC
}
```

Hàm ánh xạ allow-list:

```java
private Path<?> sortPath(
        Root<PurchaseOrder> order,
        OrderSortField field) {
    return switch (field) {
        case CREATED_AT -> order.get("createdAt");
        case TOTAL_AMOUNT -> order.get("totalAmount");
        case ORDER_NUMBER -> order.get("orderNumber");
    };
}
```

Áp dụng:

```java
Path<?> selected = sortPath(order, sortField);

jakarta.persistence.criteria.Order sort =
    direction == SortDirection.ASC
        ? cb.asc(selected)
        : cb.desc(selected);

cq.orderBy(
    sort,
    cb.desc(order.get("id"))
);
```

Lưu ý `jakarta.persistence.criteria.Order` là biểu thức sắp xếp, **không phải entity nghiệp vụ PurchaseOrder**.

### Vì sao cần sort phụ theo ID?

Nếu nhiều đơn có cùng `createdAt` hoặc `totalAmount`, chỉ sort theo field đó có thể cho thứ tự không xác định giữa các hàng bằng nhau. Bổ sung unique ID như một tie-breaker giúp việc phân trang ổn định hơn.

Với phân trang qua nhiều request trong môi trường dữ liệu thay đổi liên tục, offset pagination vẫn có thể bị trượt hàng dù sort xác định. Khi cần độ ổn định cao và dữ liệu lớn, cân nhắc keyset pagination theo khóa sort phù hợp.

## 21. Phân trang: setFirstResult và setMaxResults

CriteriaQuery quyết định **query shape**; phân trang thường được áp lên `TypedQuery`:

```java
TypedQuery<PurchaseOrder> typed = em.createQuery(cq);

int page = 0;
int size = 25;

typed.setFirstResult(page * size);
typed.setMaxResults(size);

List<PurchaseOrder> rows = typed.getResultList();
```

`page` được tính từ 0 trong ví dụ. Code production cần validate:

- `page >= 0`.
- `size` dương và không vượt giới hạn API.
- `page * size` không overflow số nguyên.
- Có ORDER BY có chủ đích.

### Tránh collection fetch join khi phân trang root

`root.fetch("lines", JoinType.LEFT)` có thể tạo một result set với nhiều dòng trên một Order. Khi kết hợp với `setMaxResults()`, Hibernate có thể không áp pagination theo root entity một cách đơn giản ở database, có phiên bản/cấu hình cảnh báo hoặc áp phân trang trong bộ nhớ.

Nếu cần trả 25 Order và danh sách lines:

1. Phân trang **IDs/root** trước.
2. Truy vấn batch lấy lines cho tập Order của trang.
3. Xây DTO trong transaction.

Đừng cố chữa N+1 bằng cách fetch join mọi collection trong một page query.

## 22. COUNT query phải được xây riêng

Một trang dữ liệu thường cần:

```text
Page<OrderSummary>
  - items: 25 đơn hiện tại
  - totalElements: tổng đơn phù hợp filter
```

Criteria lấy dữ liệu:

```java
CriteriaQuery<PurchaseOrder> dataQuery =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> dataRoot =
    dataQuery.from(PurchaseOrder.class);
```

Count query:

```java
CriteriaQuery<Long> countQuery =
    cb.createQuery(Long.class);
Root<PurchaseOrder> countRoot =
    countQuery.from(PurchaseOrder.class);

countQuery.select(cb.count(countRoot));
```

### Không dùng lại Predicate/Root từ query dữ liệu

Một `Predicate` tham chiếu `dataRoot` không nên được gắn thẳng sang `countQuery` có root `countRoot` khác. Expression tree gắn với query structure cụ thể; tái sử dụng các node sai context có thể tạo semantic error hoặc SQL không mong muốn.

Hãy xây bộ lọc qua một helper nhận đúng `CriteriaBuilder` và `Root`:

```java
private List<Predicate> buildPredicates(
        CriteriaBuilder cb,
        Root<PurchaseOrder> order,
        OrderSearch filter) {

    List<Predicate> result = new ArrayList<>();

    if (filter.status() != null) {
        result.add(cb.equal(
            order.get("status"), filter.status()
        ));
    }

    if (filter.minAmount() != null) {
        result.add(cb.ge(
            order.get("totalAmount"), filter.minAmount()
        ));
    }

    if (filter.customerId() != null) {
        result.add(cb.equal(
            order.get("customer").get("id"),
            filter.customerId()
        ));
    }

    return result;
}
```

Dùng helper một lần cho mỗi root:

```java
dataQuery.where(cb.and(
    buildPredicates(cb, dataRoot, filter)
        .toArray(Predicate[]::new)
));

countQuery.select(cb.count(countRoot));
countQuery.where(cb.and(
    buildPredicates(cb, countRoot, filter)
        .toArray(Predicate[]::new)
));
```

**Đây là ví dụ xây dựng query đúng phạm vi**, chưa phải cách tối ưu count cho mọi trường hợp. Nếu helper thêm join to-many, có thể phải dùng `cb.countDistinct(countRoot.get("id"))` hoặc thiết kế `EXISTS` để tránh đếm lặp.

### Không fetch association trong count query

`fetch` association để nạp entity thường không có ý nghĩa với `count(...)`. Join fetch trên query count có thể bị Hibernate từ chối vì owner của fetched association không nằm trong select list.

Giữ count query đơn giản: FROM, predicates/joins cần lọc, và COUNT. Không copy `orderBy` hoặc collection fetch từ data query vào count query.

## 23. Projection: chọn DTO thay vì entity graph

Không phải truy vấn nào cũng cần trả managed entity. Nếu màn hình chỉ hiển thị mã đơn, trạng thái và số tiền:

```java
public record OrderSummary(
    Long id,
    String orderNumber,
    OrderStatus status,
    BigDecimal totalAmount
) {}
```

Dùng `cb.construct`:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<OrderSummary> cq =
    cb.createQuery(OrderSummary.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

cq.select(cb.construct(
    OrderSummary.class,
    order.get("id"),
    order.get("orderNumber"),
    order.get("status"),
    order.get("totalAmount")
));

cq.where(cb.equal(
    order.get("status"), OrderStatus.PAID
));

List<OrderSummary> results =
    em.createQuery(cq).getResultList();
```

Hibernate/JPA tìm constructor phù hợp thứ tự và kiểu của các selections; Java record có canonical constructor nên có thể dùng cho projection khi kiểu khớp.

### Tuple projection

Khi cần báo cáo linh hoạt:

```java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

cq.multiselect(
    order.get("id").alias("id"),
    order.get("totalAmount").alias("amount")
);

List<Tuple> rows = em.createQuery(cq).getResultList();

for (Tuple row : rows) {
    Long id = row.get("id", Long.class);
    BigDecimal amount = row.get("amount", BigDecimal.class);
}
```

DTO thường thích hợp cho API có schema ổn định; `Tuple` hữu ích cho report động nhưng yếu hơn về refactoring/compile-time typing.

### Vì sao projection giúp tối ưu?

Projection có thể tránh hydrate các field/association không cần, tránh đưa entity proxy sang tầng JSON và giảm dữ liệu chuyển về. Nhưng nếu projection join nhiều bảng hoặc chọn nhiều giá trị, vẫn phải xem SQL plan; bản thân DTO không tự bảo đảm truy vấn nhanh.

## 24. Aggregate, GROUP BY và HAVING

Thống kê tổng tiền theo trạng thái:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Path<OrderStatus> status =
    order.get("status");

Expression<BigDecimal> total =
    cb.sum(order.<BigDecimal>get("totalAmount"));

cq.multiselect(
    status.alias("status"),
    cb.count(order).alias("numberOfOrders"),
    total.alias("totalAmount")
);

cq.groupBy(status);
cq.having(cb.greaterThan(
    total,
    new BigDecimal("1000000")
));

List<Tuple> summary = em.createQuery(cq).getResultList();
```

HQL tương đương về ý nghĩa:

```hql
select o.status, count(o), sum(o.totalAmount)
from PurchaseOrder o
group by o.status
having sum(o.totalAmount) > :minimumTotal
```

### Phân biệt WHERE và HAVING

- `WHERE` lọc **hàng nguồn** trước khi gom nhóm.
- `HAVING` lọc **nhóm** sau khi aggregate.

Ví dụ chỉ thống kê đơn đã tạo trong tháng rồi chọn những nhóm có tổng trên một ngưỡng:

```java
cq.where(cb.and(
    cb.greaterThanOrEqualTo(order.get("createdAt"), from),
    cb.lessThan(order.get("createdAt"), until)
));
cq.groupBy(status);
cq.having(cb.greaterThan(total, threshold));
```

SQL aggregate có thể cần index và query plan phù hợp; không nên lấy toàn bộ PurchaseOrder vào RAM rồi Java `groupingBy` khi database làm việc này tốt hơn.

## 25. Function, COALESCE và CASE

CriteriaBuilder có các phép biểu thức giúp xử lý null hoặc phân loại:

### 25.1. COALESCE

Giả sử một field `discountAmount` nullable. Muốn xem NULL như 0:

```java
Expression<BigDecimal> discount =
    cb.coalesce(
        order.<BigDecimal>get("discountAmount"),
        BigDecimal.ZERO
    );
```

Ví dụ giả định entity có mapped field `discountAmount`. Khi dữ liệu nullable, `COALESCE` chọn giá trị đầu tiên khác NULL.

### 25.2. CASE

Phân loại đơn theo tổng tiền:

```java
Expression<String> category =
    cb.<String>selectCase()
        .when(
            cb.ge(order.get("totalAmount"),
                new BigDecimal("1000000")),
            "LARGE"
        )
        .when(
            cb.ge(order.get("totalAmount"),
                new BigDecimal("300000")),
            "MEDIUM"
        )
        .otherwise("SMALL");
```

Biểu thức tương đương một `CASE WHEN ... THEN ... ELSE ... END`. Các ngưỡng được xét theo thứ tự; nếu đảo thứ tự MEDIUM trước LARGE, đơn hàng lớn có thể bị phân loại MEDIUM vì đã khớp điều kiện trước đó.

### 25.3. Hàm database-specific

`cb.function("function_name", ReturnType.class, args...)` cho phép biểu đạt database function, nhưng khả năng portability và cách khai báo return type phụ thuộc dialect/provider.

Không dùng database function trong `WHERE` nếu nó khiến index không còn được khai thác hiệu quả mà chưa kiểm tra query plan.

## 26. Predicate dùng trong Spring Data JPA Specifications

Một thư viện sử dụng Criteria API phổ biến là **Spring Data JPA** với `Specification<T>`. Đây là một lớp abstraction tùy chọn, **không phải một phần bắt buộc của Jakarta Persistence**.

Ví dụ:

```java
import org.springframework.data.jpa.domain.Specification;

public final class OrderSpecifications {

    private OrderSpecifications() {}

    public static Specification<PurchaseOrder> hasStatus(
            OrderStatus status) {
        return (root, query, cb) ->
            status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }

    public static Specification<PurchaseOrder> minAmount(
            BigDecimal amount) {
        return (root, query, cb) ->
            amount == null
                ? cb.conjunction()
                : cb.ge(root.get("totalAmount"), amount);
    }
}
```

Đây là cấu trúc minh họa của Specification ở những phiên bản Spring Data JPA có API tương ứng. Nó nhận `Root`, `CriteriaQuery` và `CriteriaBuilder`, rồi trả về `Predicate`.

Có thể ghép các specification bằng API của Spring Data JPA:

```java
Specification<PurchaseOrder> filter =
    OrderSpecifications.hasStatus(status)
        .and(OrderSpecifications.minAmount(minimum));
```

### Vì sao nên hiểu Criteria API trước khi dùng Specification?

Khi một Specification tạo join, gọi `distinct` hoặc thay đổi `query.orderBy`, nó có thể ảnh hưởng tới count query hoặc các Specification khác. Hiểu `Root`, `Predicate` và vòng đời query giúp debug các vấn đề do composability, joins và pagination.

Phiên bản Spring Data JPA có thể thay đổi API và cách hỗ trợ null specifications; đừng bê nguyên ví dụ từ version khác mà không kiểm tra.

## 27. Bulk UPDATE và DELETE không dùng CriteriaQuery

`CriteriaQuery<T>` chỉ dành cho truy vấn SELECT. Nếu cần bulk UPDATE:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaUpdate<PurchaseOrder> update =
    cb.createCriteriaUpdate(PurchaseOrder.class);

Root<PurchaseOrder> root =
    update.from(PurchaseOrder.class);

update.set("status", OrderStatus.CANCELLED);
update.where(cb.equal(
    root.get("status"), OrderStatus.NEW
));

int affected = em.createQuery(update).executeUpdate();
```

Bulk DELETE:

```java
CriteriaDelete<PurchaseOrder> delete =
    cb.createCriteriaDelete(PurchaseOrder.class);

Root<PurchaseOrder> root =
    delete.from(PurchaseOrder.class);

delete.where(cb.equal(
    root.get("status"), OrderStatus.CANCELLED
));

int affected = em.createQuery(delete).executeUpdate();
```

### Quan trọng: bulk DML không giống cập nhật managed entity

- Bulk UPDATE/DELETE thực hiện ở mức database, không dirty check từng entity.
- Những managed entity đã tải có thể giữ state cũ trong Persistence Context.
- Entity lifecycle callback không nên được giả định chạy cho từng hàng.
- `@Version` không tự được cập nhật theo mọi quy tắc cập nhật entity thông thường.
- Foreign key, cascade và constraint phải được xem xét ở database.
- Cần transaction hợp lệ để chạy DML.

Sau bulk operation, cân nhắc `clear()`, `refresh()` hoặc chạy trong Persistence Context riêng để tránh dùng dữ liệu cũ. Đừng dùng bulk DML trong cùng context rồi tin rằng mọi managed object đã đồng bộ.

## 28. Criteria API và HQL: chọn công cụ theo độ phức tạp

| Tình huống | Criteria API | HQL |
|---|---|---|
| 8–12 bộ lọc tùy chọn | Dễ ghép predicate có điều kiện | Cần xây chuỗi hoặc nhiều query variants |
| Query ngắn, cố định | Dài dòng hơn | Thường dễ đọc hơn |
| Static metamodel/type safety | Có thể mạnh hơn | Chủ yếu kiểm tra ở runtime |
| Report có join/aggregate phức tạp | Có thể verbose | HQL thường gọn và rõ |
| Cấu trúc query từ UI filter builder | Thuận tiện | Cần template/DSL riêng |
| Debug SQL được Hibernate sinh | Đều cần SQL logging | Đều cần SQL logging |
| Tính portable giữa provider | Dùng phần Criteria chuẩn | HQL có thể có extension Hibernate |

Criteria API **không nhất thiết nhanh hơn HQL**. Cả hai thường được Hibernate chuyển thành mô hình query và SQL do cùng engine xử lý. Hiệu năng chủ yếu phụ thuộc query shape, index, lượng dữ liệu, fetch plan, plan caching và database.

Nếu truy vấn cố định và ngắn, HQL thường là lựa chọn tốt. Nếu yêu cầu động phức tạp, Criteria giúp giảm lỗi nối chuỗi và tạo abstraction rõ ràng hơn.

## 29. Lỗi thường gặp và cách nhận biết

### 29.1. Gọi where() nhiều lần để “thêm điều kiện”

```java
cq.where(p1);
cq.where(p2);
```

Lời gọi thứ hai có thể thay thế điều kiện trước. Hãy gom `List<Predicate>` rồi gọi `where(...)` một lần.

### 29.2. Dùng java.util.function.Predicate

Java Streams có `java.util.function.Predicate<T>`, còn Criteria yêu cầu `jakarta.persistence.criteria.Predicate`. Đây là hai kiểu không thể thay thế cho nhau.

### 29.3. Truy cập field sai tên

`root.get("total_amout")` có thể thất bại vì Criteria dùng **tên thuộc tính entity**, không nhất thiết là tên cột database. Với field Java `totalAmount` ánh xạ cột `total_amount`, cần dùng `root.get("totalAmount")`.

### 29.4. Dùng tên cột SQL thay vì tên thuộc tính entity

```java
root.get("customer_id"); // Sai nếu entity chỉ có field customer.
```

Criteria xây từ object mapping; nên dùng `root.get("customer").get("id")` hoặc join `customer`. SQL column name do provider quyết định.

### 29.5. Không xử lý tập IN rỗng

`in(emptyList)` có thể tạo query không hữu ích hoặc khác giữa DB. Định nghĩa ý nghĩa của tập rỗng trước rồi tạo predicate phù hợp.

### 29.6. So sánh với NULL bằng equal()

SQL NULL cần `isNull`/`isNotNull`. Đừng coi NULL như một giá trị bằng nhau thông thường.

### 29.7. Không nhóm AND/OR

Sai dấu ngoặc logic có thể trả nhiều hàng hơn yêu cầu. Đặt tên nhóm predicate và viết test truth table.

### 29.8. Dùng join to-many mà không xử lý trùng

Một root có nhiều child matching có thể bị nhân hàng. Cân nhắc `distinct(true)`, `countDistinct` hoặc EXISTS.

### 29.9. Reuse Predicate giữa hai CriteriaQuery khác root

Expression tree thuộc query context cụ thể. Xây lại điều kiện theo root của data/count query; không chuyển nguyên Predicate trỏ root cũ sang query mới.

### 29.10. Fetch join collection trong query phân trang

Result set nhân hàng có thể khiến pagination theo root không được áp dụng như mong muốn. Tách bước lấy page roots/IDs và tải collection.

### 29.11. Cho client chọn field bất kỳ

`root.get(userInput)` không phải SQL injection theo cách nối SQL values, nhưng có thể cho phép lọc/sort trên field nội bộ hoặc làm query lỗi. Dùng allow-list.

### 29.12. Dùng CriteriaQuery như một object thread-safe tái sử dụng

CriteriaQuery là cấu trúc có thể thay đổi trong giai đoạn xây query; không nên giữ một instance mutable dùng chung giữa request/threads. EntityManager cũng không thread-safe. Tạo query mới theo mỗi unit of work hoặc dùng abstraction sinh Criteria theo request.

### 29.13. Gọi toString() trên CriteriaQuery để tìm SQL

`CriteriaQuery.toString()` không có hợp đồng portable trả về SQL hoàn chỉnh. Hãy bật Hibernate SQL logging hoặc dùng StatementInspector khi cần quan sát câu SQL thực tế.

### 29.14. Nghĩ Criteria giúp tránh mọi lỗi database

Criteria có thể giúp cấu trúc query và bind values, nhưng không sửa được missing index, sai transaction isolation, N+1 do fetch plan hay constraint violation.

## 30. Mẫu repository cho trang tìm kiếm

Một cấu trúc thực tế có thể tách bộ lọc và truy vấn:

```java
public record OrderPage(
    List<OrderSummary> items,
    long totalElements,
    int page,
    int size
) {}
```

Repository dùng một hàm predicate builder cho từng root:

```java
public class OrderSearchRepository {

    private final EntityManager em;

    public OrderSearchRepository(EntityManager em) {
        this.em = em;
    }

    public OrderPage findOrders(
            OrderSearch filter,
            int page,
            int size) {

        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid page");
        }

        CriteriaBuilder cb = em.getCriteriaBuilder();

        // Data query: select DTO, not full entity graph.
        CriteriaQuery<OrderSummary> data =
            cb.createQuery(OrderSummary.class);
        Root<PurchaseOrder> dataRoot =
            data.from(PurchaseOrder.class);

        data.select(cb.construct(
            OrderSummary.class,
            dataRoot.get("id"),
            dataRoot.get("orderNumber"),
            dataRoot.get("status"),
            dataRoot.get("totalAmount")
        ));
        data.where(cb.and(
            conditions(cb, dataRoot, filter)
                .toArray(Predicate[]::new)
        ));
        data.orderBy(
            cb.desc(dataRoot.get("createdAt")),
            cb.desc(dataRoot.get("id"))
        );

        List<OrderSummary> items = em.createQuery(data)
            .setFirstResult(Math.multiplyExact(page, size))
            .setMaxResults(size)
            .getResultList();

        // Count query: a fresh root and freshly built predicates.
        CriteriaQuery<Long> count =
            cb.createQuery(Long.class);
        Root<PurchaseOrder> countRoot =
            count.from(PurchaseOrder.class);

        count.select(cb.count(countRoot));
        count.where(cb.and(
            conditions(cb, countRoot, filter)
                .toArray(Predicate[]::new)
        ));

        long total = em.createQuery(count)
            .getSingleResult();

        return new OrderPage(items, total, page, size);
    }

    private List<Predicate> conditions(
            CriteriaBuilder cb,
            Root<PurchaseOrder> root,
            OrderSearch filter) {

        List<Predicate> predicates = new ArrayList<>();

        if (filter.status() != null) {
            predicates.add(cb.equal(
                root.get("status"), filter.status()
            ));
        }
        if (filter.customerId() != null) {
            predicates.add(cb.equal(
                root.get("customer").get("id"),
                filter.customerId()
            ));
        }
        if (filter.minAmount() != null) {
            predicates.add(cb.ge(
                root.get("totalAmount"), filter.minAmount()
            ));
        }
        if (filter.maxAmount() != null) {
            predicates.add(cb.le(
                root.get("totalAmount"), filter.maxAmount()
            ));
        }
        if (filter.createdFromInclusive() != null) {
            predicates.add(cb.greaterThanOrEqualTo(
                root.get("createdAt"),
                filter.createdFromInclusive()
            ));
        }
        if (filter.createdUntilExclusive() != null) {
            predicates.add(cb.lessThan(
                root.get("createdAt"),
                filter.createdUntilExclusive()
            ));
        }

        String searchTerm = filter.orderNumberContains();
        if (searchTerm != null && !searchTerm.isBlank()) {
            predicates.add(cb.like(
                cb.lower(root.get("orderNumber")),
                "%" + searchTerm.strip().toLowerCase(Locale.ROOT) + "%"
            ));
        }

        return predicates;
    }
}
```

**Phạm vi ví dụ:** Đây là repository mẫu thể hiện kết nối giữa data/count queries và helper. Nó chưa bao gồm toàn bộ input validation, escaping wildcard, tối ưu count khi join to-many, keyset pagination hoặc quyết định về isolation. Các phần đó cần được xử lý theo contract và workload thực tế.

### Vì sao không tái sử dụng query object?

Data query và count query có:

- Kiểu kết quả khác nhau (`OrderSummary` và `Long`).
- Root khác nhau.
- Projection khác nhau.
- ORDER BY chỉ có ý nghĩa ở data query.
- Predicate được xây lại cho root tương ứng.

Chia sẻ **logic xây điều kiện** là hữu ích; chia sẻ cùng instance Root/Predicate giữa hai cây query thì không phù hợp.

## 31. SQL có thể được Hibernate sinh ra như thế nào?

Ví dụ filter:

```text
status = PAID
minAmount = 100000
createdFromInclusive = 2026-01-01T00:00:00Z
createdUntilExclusive = 2026-02-01T00:00:00Z
```

Criteria:

```java
Predicate p = cb.and(
    cb.equal(root.get("status"), OrderStatus.PAID),
    cb.ge(root.get("totalAmount"), new BigDecimal("100000")),
    cb.greaterThanOrEqualTo(root.get("createdAt"), from),
    cb.lessThan(root.get("createdAt"), until)
);
```

SQL minh họa:

```sql
SELECT
    o.id,
    o.order_number,
    o.status,
    o.total_amount
FROM purchase_orders o
WHERE o.status = ?
  AND o.total_amount >= ?
  AND o.created_at >= ?
  AND o.created_at < ?
ORDER BY o.created_at DESC, o.id DESC
OFFSET ? ROWS
FETCH FIRST ? ROWS ONLY;
```

Đây là **minh họa**. SQL thực tế phụ thuộc Hibernate version, dialect, database và fetch/query options. Một dialect khác có thể dùng `LIMIT/OFFSET`, `ROW_NUMBER` hoặc cú pháp phân trang riêng.

Điều quan trọng là:

- Criteria dùng tên entity property, Hibernate ánh xạ sang tên cột SQL.
- Provider chọn cú pháp và bind parameters.
- Query execution vẫn phụ thuộc index, filter selectivity và optimizer.
- Criteria không làm SQL “tự động tối ưu” chỉ vì code typed.

## 32. Kiểm tra SQL, tham số và hiệu năng

Ví dụ logging Hibernate ORM 6 trong Spring Boot:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Khi cần so sánh Criteria với HQL, hãy chạy cùng bộ lọc và quan sát:

1. Số SQL được thực thi.
2. Loại join và số hàng trung gian.
3. Số bind parameters.
4. Có query count bổ sung không?
5. Có secondary select/N+1 khi truy cập association lazy không?
6. Có ORDER BY và LIMIT/OFFSET đúng yêu cầu không?
7. Query plan có dùng index phù hợp không?
8. Số hàng thực tế, thời gian và byte truyền có phù hợp không?

Có thể dùng `EXPLAIN`/`EXPLAIN ANALYZE` trên database mục tiêu khi cần. Cẩn thận vì `ANALYZE` có thể thực thi statement tùy hệ quản trị.

**Không bật bind logging chi tiết tùy tiện trong production**, vì các giá trị tham số có thể chứa dữ liệu cá nhân hoặc thông tin nhạy cảm.

### Criteria và N+1

Việc dùng Criteria thay cho HQL **không tự giải quyết N+1**. Nếu query trả 100 Order và code đọc `order.getCustomer().getName()` khi customer là LAZY, vẫn có thể phát secondary select. Phải chọn fetch plan hoặc DTO projection phù hợp.

## 33. Bài thực hành 1: tạo query từ bốn thành phần

Cho entity PurchaseOrder đã nêu, hãy viết query lấy các Order:

- Trạng thái `PAID`.
- Tổng tiền từ 200.000 trở lên.
- Tạo trong 30 ngày gần nhất.
- Sắp xếp theo ngày mới nhất rồi ID giảm dần.

Gợi ý:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Instant from = clock.instant().minus(30, ChronoUnit.DAYS);

Predicate criteria = cb.and(
    cb.equal(order.get("status"), OrderStatus.PAID),
    cb.ge(order.get("totalAmount"),
        new BigDecimal("200000")),
    cb.greaterThanOrEqualTo(order.get("createdAt"), from)
);

cq.select(order);
cq.where(criteria);
cq.orderBy(
    cb.desc(order.get("createdAt")),
    cb.desc(order.get("id"))
);

List<PurchaseOrder> rows =
    em.createQuery(cq).getResultList();
```

`clock` là một `java.time.Clock` do ứng dụng cung cấp để có thể kiểm thử thời gian ổn định. Bài tập này tập trung cấu trúc Criteria, không yêu cầu phụ thuộc vào giờ hệ thống một cách ngầm định.

### Tự trả lời

- `CriteriaBuilder` tạo những thành phần nào?
- `CriteriaQuery<PurchaseOrder>` quyết định điều gì?
- `Root<PurchaseOrder>` có phải một entity đã tải không?
- `Predicate` diễn đạt điều kiện gì?
- Tại sao phải gọi `entityManager.createQuery(cq)` rồi `getResultList()`?

## 34. Bài thực hành 2: bộ lọc động với nhiều trường hợp

Tạo một API nhận:

```text
status: optional
customerId: optional
minAmount: optional
maxAmount: optional
createdFrom: optional
createdUntil: optional
orderNumberContains: optional
```

Yêu cầu:

1. Không có filter nào: trả mọi Order trong phạm vi quyền truy cập ứng dụng.
2. Chỉ có status: lọc đúng enum status.
3. Có minAmount và maxAmount: điều kiện AND.
4. Có khoảng thời gian: dùng nửa mở.
5. Có search term: xử lý ký tự `%` và `_` theo quy tắc LIKE được thống nhất.
6. Nếu minAmount > maxAmount: trả lỗi validation, không chạy query.
7. Không nhận tùy ý tên field từ client để ghép `root.get(...)`.

### Test truth table

| Status filter | Amount filter | Kết quả mong đợi |
|---|---|---|
| NULL | NULL | Không loại Order vì hai filter này |
| PAID | NULL | Chỉ Order PAID |
| NULL | >= 100000 | Order đủ ngưỡng |
| PAID | >= 100000 | PAID **và** đủ ngưỡng |
| [PAID, SHIPPED] | >= 100000 | (PAID **hoặc** SHIPPED) **và** đủ ngưỡng |

Nếu query trả toàn bộ PAID dù chưa đủ ngưỡng, kiểm tra vị trí `cb.or` và `cb.and`.

## 35. Bài thực hành 3: JOIN, EXISTS và đếm

Mục tiêu: tìm các PurchaseOrder có ít nhất một OrderLine với SKU-A.

### Cách A — JOIN

```java
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);
Join<PurchaseOrder, OrderLine> line = order.join("lines");

cq.select(order).distinct(true);
cq.where(cb.equal(line.get("sku"), "SKU-A"));
```

### Cách B — EXISTS

```java
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Subquery<Long> subquery = cq.subquery(Long.class);
Root<OrderLine> line = subquery.from(OrderLine.class);

subquery.select(cb.literal(1L));
subquery.where(
    cb.equal(line.get("order"), order),
    cb.equal(line.get("sku"), "SKU-A")
);

cq.select(order).where(cb.exists(subquery));
```

So sánh:

- Kết quả khi một Order có hai line SKU-A.
- SQL và query plan.
- Count query tương ứng.
- Tốc độ với số line lớn.

Không mặc định EXISTS luôn nhanh hơn; tối ưu thực tế thuộc về database query planner, index và dữ liệu.

## 36. Bài thực hành 4: phân trang DTO và count

Viết method trả:

```java
OrderPage findOrders(OrderSearch filter, int page, int size);
```

Yêu cầu:

1. Trang dữ liệu dùng `CriteriaQuery<OrderSummary>` và `cb.construct(...)`.
2. Count dùng `CriteriaQuery<Long>` với root riêng.
3. Cả hai dùng cùng logic build predicates nhưng **không reuse Root/Predicate instances**.
4. Sắp xếp ổn định theo `createdAt` rồi `id`.
5. Validate `page`, `size` và overflow.
6. Không thêm `fetch("lines")` vào count query.
7. Kiểm tra tổng số sau khi thêm filter customer/status.
8. Với to-many filter, tránh đếm trùng bằng EXISTS hoặc count distinct.

## 37. Câu hỏi tự kiểm tra

1. `CriteriaBuilder` khác `CriteriaQuery<T>` như thế nào?
2. `Root<PurchaseOrder>` có phải một entity instance chứa dữ liệu chưa?
3. `Predicate` trong Criteria khác `java.util.function.Predicate` ra sao?
4. Nếu gọi `where(p1)` rồi `where(p2)`, có tự sinh `p1 AND p2` không?
5. `cb.conjunction()` có giá trị gì? `cb.disjunction()` thì sao?
6. `cb.or()` với danh sách rỗng có cùng nghĩa `cb.and()` rỗng không?
7. Tại sao `root.get("total_amount")` có thể sai dù database dùng cột ấy?
8. `isNull` và `equal(path, null)` khác nhau về ý định và tính rõ ràng thế nào?
9. Vì sao LIKE với input chứa ký tự `%` và `_` cần xử lý nếu muốn tìm literal?
10. Vì sao INNER JOIN association optional có thể loại Order?
11. Vì sao join to-many có thể làm đếm trùng root?
12. Khi nào dùng EXISTS thay vì join?
13. Vì sao không reuse Predicate của data query cho count query khác Root?
14. `setFirstResult` và `setMaxResults` thuộc CriteriaQuery hay TypedQuery?
15. Vì sao không nên fetch join collection trong query phân trang?
16. Static metamodel giúp phát hiện lỗi gì sớm hơn?
17. Predicate động có ngăn N+1 không?
18. CriteriaQuery có nên là singleton mutable dùng chung threads không?

**Đáp án gợi ý:** (1) nhà máy biểu thức và bản thiết kế query; (2) không, nó là query root; (3) hai interface thuộc hai package/mục đích; (4) không, where sau thay thế; (5) TRUE và FALSE; (6) không; (7) Criteria dùng entity property name; (8) dùng IS NULL rõ ràng; (9) chúng là wildcard; (10) không có association khớp; (11) nhiều child cùng match; (12) khi chỉ cần kiểm tra tồn tại; (13) nodes gắn root/query khác; (14) TypedQuery; (15) nhân hàng ảnh hưởng pagination; (16) typo/kiểu thuộc tính; (17) không; (18) không.

## 38. Nguyên tắc quan trọng cần ghi nhớ

1. **`CriteriaBuilder` tạo các node biểu thức; `CriteriaQuery` mô tả SELECT; `Root` đại diện FROM; `Predicate` mô tả điều kiện.** Bốn đối tượng này tạo nền tảng của Criteria API.
2. **Criteria là cây biểu thức chứ không phải một truy vấn đã chạy.** SQL được Hibernate sinh và gửi khi thực thi TypedQuery.
3. **Bộ lọc động nên được gom vào `List<Predicate>`**, chỉ thêm những điều kiện được áp dụng và gọi `where` một lần.
4. **`where` không tự cộng dồn qua nhiều lần gọi.** Mỗi lần thiết lập restriction có thể thay thế điều kiện cũ.
5. **`cb.and()` rỗng tương ứng TRUE, `cb.or()` rỗng tương ứng FALSE.** Phải định nghĩa nghiệp vụ cho filter rỗng.
6. **Đặt dấu ngoặc logic bằng cấu trúc `and/or`**, không dựa vào suy đoán về thứ tự ưu tiên.
7. **Root/Path dùng tên thuộc tính entity, không phải tên cột SQL.** Static metamodel giúp type safety và refactoring.
8. **JOIN và EXISTS có cardinality khác nhau; join to-many có thể tạo kết quả/COUNT trùng.**
9. **Data query, count query và DTO projection có shape khác nhau.** Tạo root và predicates mới cho mỗi query, tránh fetch join trong count.
10. **Criteria không tự sửa hiệu năng hoặc N+1.** Cần quan sát SQL, query plan, index, pagination và fetch strategy.
11. **Dữ liệu từ client phải được validate và giới hạn field được phép filter/sort.** Criteria giúp xây giá trị có cấu trúc nhưng không thay thế authorization.
12. **Chọn HQL hay Criteria theo use case.** HQL dễ đọc cho query cố định; Criteria thường thích hợp khi yêu cầu ghép nhiều điều kiện động.

Khi xây một chức năng tìm kiếm thực tế, hãy bắt đầu từ **entity root và kiểu kết quả**, sau đó mô tả từng điều kiện nghiệp vụ bằng `Predicate`, ghép chúng đúng nhóm bằng `CriteriaBuilder`, cuối cùng hoàn thiện `CriteriaQuery` và thực thi thông qua `TypedQuery`. Sự rõ ràng của cây query là giá trị chính của Criteria API, không phải việc dùng Java code dài hơn để tạo cùng một SQL.

### Tài liệu tham khảo chính thức

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API — CriteriaBuilder](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/criteria/criteriabuilder)
- [Jakarta Persistence API — CriteriaQuery](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/criteria/criteriaquery)
- [Jakarta Persistence API — Root](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/criteria/root)
- [Jakarta Persistence API — Predicate](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/criteria/predicate)
- [Hibernate ORM User Guide — Criteria](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#criteria)
- [Hibernate ORM Query Language](https://docs.jboss.org/hibernate/orm/current/querylanguage/html_single/Hibernate_Query_Language.html)
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)

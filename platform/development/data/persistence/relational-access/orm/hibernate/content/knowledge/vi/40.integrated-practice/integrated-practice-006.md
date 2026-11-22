# So sánh HQL, Criteria, DTO projection và native SQL cho cùng nhu cầu đọc

Khi cần đọc dữ liệu từ Hibernate, có nhiều cách viết query: HQL/JPQL, Criteria API, DTO projection và native SQL. Chúng thường được đặt cạnh nhau như bốn lựa chọn ngang hàng, nhưng thực tế chúng giải quyết những phần khác nhau của bài toán.

- **HQL** là ngôn ngữ truy vấn hướng entity của Hibernate; JPQL là phần chuẩn hóa trong Jakarta Persistence.
- **Criteria API** là API Java để xây dựng query bằng object và expressions thay vì ghép chuỗi query.
- **DTO projection** mô tả hình dạng kết quả mà ứng dụng muốn nhận, thường chỉ gồm các fields cần thiết.
- **Native SQL** cho phép viết SQL trực tiếp theo database.

DTO projection có thể được tạo bằng HQL, Criteria hoặc native SQL. Vì vậy, so sánh đúng cần dùng cùng một nhu cầu đọc, giữ nguyên filters, sort, pagination và fields trả về, rồi xem mỗi cách biểu đạt query và kết quả ra sao.

Bài thuộc chương **Thực hành tổng hợp** của module *Data Persistence Relational Access ORM Hibernate*. Ta sẽ dùng một use case thống nhất: tìm danh sách đơn hàng theo trạng thái, tên khách hàng và khoảng thời gian; sắp xếp theo ngày tạo; phân trang; trả về một dòng dữ liệu gọn cho màn hình danh sách.

## 1. Bài toán đọc chung

Giả sử ứng dụng bán hàng có hai bảng chính:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(160) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    total NUMERIC(18, 2) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE INDEX idx_orders_status_created
    ON orders(status, created_at, id);

CREATE INDEX idx_orders_customer
    ON orders(customer_id);
~~~

Một trang danh sách cần hiển thị:

| Field | Nguồn |
| --- | --- |
| Order ID | `orders.id` |
| Customer name | `customers.name` |
| Created at | `orders.created_at` |
| Total | `orders.total` |
| Status | `orders.status` |

Người dùng có thể lọc theo:

- Trạng thái đơn hàng, ví dụ `PAID`.
- Một phần tên khách hàng, ví dụ `an`.
- Thời gian tạo từ `from` đến trước `to`.
- Trang và kích thước trang.
- Thứ tự mới nhất trước; khi ngày giống nhau, ID lớn hơn đứng trước.

Kết quả không cần toàn bộ `Order`, `Customer`, `OrderLine` hoặc `Payment` entities. Chỉ cần năm giá trị cho mỗi dòng.

Một DTO phù hợp:

~~~java
public record OrderReadRow(
    Long id,
    String customerName,
    Instant createdAt,
    BigDecimal total,
    OrderStatus status
) {
    // Constructor bổ sung cho native result mapping dùng JDBC types.
    public OrderReadRow(
            Long id,
            String customerName,
            Timestamp createdAt,
            BigDecimal total,
            String status) {
        this(
            id,
            customerName,
            createdAt.toInstant(),
            total,
            OrderStatus.valueOf(status)
        );
    }
}
~~~

Các ví dụ giả định `Order.createdAt` được map với kiểu Java phù hợp với database timestamp và Hibernate version đang dùng. Có thể dùng `LocalDateTime` thay `Instant` nếu đó là mô hình thời gian của ứng dụng; cần thống nhất timezone semantics ở JDBC/database.

## 2. Bốn khái niệm không cùng một tầng

| Cách gọi | Bản chất | Trả lời câu hỏi |
| --- | --- | --- |
| HQL | Query language | Viết query bằng cú pháp nào? |
| Criteria API | Query-building API | Xây query động và có cấu trúc ra sao? |
| DTO projection | Result shape | Chỉ lấy dữ liệu nào và trả về object nào? |
| Native SQL | SQL trực tiếp | Khi nào cần quyền kiểm soát SQL/database? |

Ví dụ:

- HQL có thể trả về `List<Order>` hoặc `List<OrderReadRow>`.
- Criteria API cũng có thể trả về entity, scalar hoặc `OrderReadRow`.
- Native SQL có thể trả về `Object[]`, scalar, entity mapping hoặc DTO qua result-set mapping.
- DTO projection không bắt buộc phải đi cùng một loại query language.

Để so sánh công bằng, bài sẽ phân biệt hai câu hỏi:

1. Query được biểu đạt bằng HQL, Criteria hay SQL?
2. Kết quả được materialize thành entity hay DTO?

Với màn hình danh sách, DTO thường là lựa chọn hợp lý vì nó tránh hydrate entity graph không cần thiết.

## 3. Entity mapping tối thiểu

Ví dụ entity:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {}

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 24)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal total;

    protected Order() {}

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Enum:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

Các entity trên chỉ là mô hình để minh họa. Tên field trong HQL/Criteria là tên thuộc tính Java (`createdAt`, `customer`), còn native SQL dùng tên bảng/cột (`created_at`, `customer_id`).

## 4. Các điều kiện chung cần giữ nguyên

Để bốn cách đọc có thể so sánh được, phải giữ cùng semantics:

~~~text
Input:
  status = PAID
  customerPrefix = "an"
  from = 2026-01-01T00:00:00Z
  to   = 2026-02-01T00:00:00Z
  page = 0
  size = 20

Filter:
  order.status = status
  lower(customer.name) starts with customerPrefix
  createdAt >= from
  createdAt < to

Sort:
  createdAt DESC, id DESC

Output:
  OrderReadRow(id, customerName, createdAt, total, status)
~~~

Dùng khoảng thời gian nửa mở `[from, to)` giúp tránh lỗi ở ranh giới cuối ngày và dễ nối tiếp các khoảng thời gian liền nhau. Nếu input là ngày địa phương, cần chuyển đổi sang timezone nghiệp vụ trước khi truyền query.

Tên khách hàng được so sánh không phân biệt hoa thường trong ví dụ. Việc database có index hỗ trợ `lower(name)` hay không phụ thuộc database và functional index/collation; cần xem execution plan.

## 5. Cách 1: HQL với constructor projection

HQL (Hibernate Query Language) truy vấn entity và thuộc tính entity thay vì tên bảng/cột. HQL gần với JPQL, nhưng có thể cung cấp thêm các tính năng Hibernate-specific tùy version.

Ví dụ dùng constructor expression để trả DTO:

~~~java
String hql = """
    select new com.example.orders.OrderReadRow(
        o.id,
        c.name,
        o.createdAt,
        o.total,
        o.status
    )
    from Order o
    join o.customer c
    where o.status = :status
      and lower(c.name) like :customerPattern
      and o.createdAt >= :from
      and o.createdAt < :to
    order by o.createdAt desc, o.id desc
    """;

TypedQuery<OrderReadRow> query =
    entityManager.createQuery(hql, OrderReadRow.class);

query.setParameter("status", status);
query.setParameter("customerPattern", customerPrefix.toLowerCase() + "%");
query.setParameter("from", from);
query.setParameter("to", to);

query.setFirstResult(page * size);
query.setMaxResults(size);

List<OrderReadRow> rows = query.getResultList();
~~~

Jakarta Persistence constructor expression dùng tên class đầy đủ của DTO. Constructor của DTO phải khớp số lượng, thứ tự và kiểu dữ liệu của các biểu thức được chọn.

### Điểm mạnh của HQL

- Cú pháp gần với cách nghĩ về entity và association.
- Dễ đọc khi query có cấu trúc ổn định.
- Có thể dùng constructor projection để không tạo managed entities.
- Parameter binding rõ ràng.
- Có thể join theo association mapping thay vì tự viết FK.
- Hỗ trợ query result typed qua `TypedQuery`.

### Giới hạn

- Ghép HQL string động có thể trở nên khó quản lý khi nhiều filters tùy chọn.
- Tên thuộc tính/class trong string không được compiler kiểm tra đầy đủ.
- Một query string dài có thể khó refactor khi đổi tên field.
- Tính năng HQL ngoài JPQL có thể làm giảm portability.
- HQL không tự đảm bảo SQL sinh ra tối ưu; vẫn phải đo.

## 6. HQL với filters tùy chọn

Trong ứng dụng thực tế, customer prefix hoặc khoảng thời gian có thể không bắt buộc. Có thể dựng danh sách predicates:

~~~java
StringBuilder hql = new StringBuilder("""
    select new com.example.orders.OrderReadRow(
        o.id, c.name, o.createdAt, o.total, o.status
    )
    from Order o
    join o.customer c
    where o.status = :status
    """);

Map<String, Object> parameters = new HashMap<>();
parameters.put("status", status);

if (customerPrefix != null && !customerPrefix.isBlank()) {
    hql.append(" and lower(c.name) like :customerPattern");
    parameters.put(
        "customerPattern",
        customerPrefix.trim().toLowerCase() + "%"
    );
}

if (from != null) {
    hql.append(" and o.createdAt >= :from");
    parameters.put("from", from);
}

if (to != null) {
    hql.append(" and o.createdAt < :to");
    parameters.put("to", to);
}

hql.append(" order by o.createdAt desc, o.id desc");

TypedQuery<OrderReadRow> query =
    entityManager.createQuery(hql.toString(), OrderReadRow.class);

parameters.forEach(query::setParameter);
query.setFirstResult(page * size);
query.setMaxResults(size);

List<OrderReadRow> rows = query.getResultList();
~~~

Ở đây chỉ nối các đoạn query do chương trình kiểm soát. Giá trị người dùng luôn được truyền qua named parameters.

Không làm:

~~~java
hql.append(" and c.name like '%" + customerPrefix + "%'");
~~~

Ghép trực tiếp input vào query có thể dẫn đến injection, sai escaping và lỗi khi giá trị chứa dấu nháy. Parameter binding áp dụng cho **giá trị**, không áp dụng cho tên cột hoặc keyword sort.

### Dynamic sort

Không nối sort field do client gửi trực tiếp vào HQL. Dùng allowlist:

~~~java
String sortExpression = switch (sortKey) {
    case "total" -> "o.total";
    case "createdAt" -> "o.createdAt";
    case "id" -> "o.id";
    default -> throw new IllegalArgumentException("Unsupported sort");
};

String direction = descending ? "desc" : "asc";

hql.append(" order by ")
   .append(sortExpression)
   .append(' ')
   .append(direction)
   .append(", o.id desc");
~~~

`sortExpression` và `direction` được chọn từ các giá trị cố định trong code, không lấy nguyên văn từ request.

## 7. HQL trả entity thay vì DTO

HQL cũng có thể trả entity:

~~~java
List<Order> orders = entityManager.createQuery(
    """
    select o
    from Order o
    join fetch o.customer
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """,
    Order.class
)
.setParameter("status", status)
.getResultList();
~~~

Lựa chọn này phù hợp khi nghiệp vụ cần thao tác entity managed, thay đổi state hoặc dùng lifecycle/cascade trong transaction.

Với màn hình chỉ đọc năm fields, entity result có thể tốn hơn cần thiết:

- Hibernate tạo managed entity instances.
- Persistence context giữ identity/state.
- Associations có thể được lazy-load ngoài dự kiến.
- Mapping sang DTO phải diễn ra trong transaction.
- Fetch join collection có thể làm tăng rows.

HQL không đồng nghĩa DTO, và HQL không đồng nghĩa entity. Result shape phụ thuộc phần `select`.

## 8. Count query cho pagination bằng HQL

Nếu API cần tổng số trang, query lấy page và query đếm phải dùng cùng điều kiện lọc.

~~~java
String countHql = """
    select count(o.id)
    from Order o
    join o.customer c
    where o.status = :status
      and lower(c.name) like :customerPattern
      and o.createdAt >= :from
      and o.createdAt < :to
    """;

Long total = entityManager.createQuery(countHql, Long.class)
    .setParameter("status", status)
    .setParameter("customerPattern", customerPrefix.toLowerCase() + "%")
    .setParameter("from", from)
    .setParameter("to", to)
    .getSingleResult();
~~~

Count query thường không cần `order by` và không cần fetch join. Nếu joins làm nhân root rows, có thể cần `count(distinct o.id)` thay `count(o.id)`.

Không đếm trên query có collection fetch join rồi giữ nguyên mọi joins; count query cần được thiết kế riêng để phản ánh số root records.

## 9. Cách 2: Criteria API

Criteria API xây query bằng Java objects: `CriteriaBuilder`, `CriteriaQuery`, `Root`, `Join`, `Predicate`, `Order` và selections.

Cùng bài toán đọc:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaQuery<OrderReadRow> cq =
    cb.createQuery(OrderReadRow.class);

Root<Order> order = cq.from(Order.class);
Join<Order, Customer> customer =
    order.join("customer", JoinType.INNER);

List<Predicate> predicates = new ArrayList<>();

predicates.add(
    cb.equal(order.get("status"), status)
);

if (customerPrefix != null && !customerPrefix.isBlank()) {
    predicates.add(
        cb.like(
            cb.lower(customer.get("name")),
            customerPrefix.trim().toLowerCase() + "%"
        )
    );
}

if (from != null) {
    predicates.add(
        cb.greaterThanOrEqualTo(order.get("createdAt"), from)
    );
}

if (to != null) {
    predicates.add(
        cb.lessThan(order.get("createdAt"), to)
    );
}

cq.select(cb.construct(
    OrderReadRow.class,
    order.get("id"),
    customer.get("name"),
    order.get("createdAt"),
    order.get("total"),
    order.get("status")
));

cq.where(predicates.toArray(Predicate[]::new));

cq.orderBy(
    cb.desc(order.get("createdAt")),
    cb.desc(order.get("id"))
);

TypedQuery<OrderReadRow> query = entityManager.createQuery(cq);
query.setFirstResult(page * size);
query.setMaxResults(size);

List<OrderReadRow> rows = query.getResultList();
~~~

Đây cũng là DTO projection: Criteria diễn đạt query, còn `cb.construct` tạo `OrderReadRow`.

### Điểm mạnh của Criteria

- Dễ thêm/bỏ predicates theo input.
- Không phải ghép HQL string.
- Có thể tái sử dụng predicate builders.
- Java compiler kiểm tra nhiều kiểu dữ liệu và biểu thức hơn string query.
- Hợp với search screens có nhiều filters tùy chọn.
- Có thể tạo cả data query và count query từ cùng bộ điều kiện.

### Giới hạn

- Verbose hơn HQL.
- Query dài có thể khó đọc vì nhiều object variables.
- Dùng string attribute names vẫn có rủi ro rename không được compiler phát hiện.
- Criteria không tự tạo SQL tốt hơn HQL.
- Người đọc cần hiểu Criteria API và query object graph.

## 10. Criteria với static metamodel

Nếu dự án sinh JPA static metamodel, có thể thay tên thuộc tính dạng string bằng metamodel attributes:

~~~java
Root<Order> order = cq.from(Order.class);

Join<Order, Customer> customer =
    order.join(Order_.customer, JoinType.INNER);

Path<Instant> createdAt = order.get(Order_.createdAt);
Path<OrderStatus> orderStatus = order.get(Order_.status);
Path<String> customerName = customer.get(Customer_.name);
~~~

Static metamodel tăng khả năng phát hiện lỗi khi rename entity attributes và giữ type information. Đổi lại, build phải cấu hình annotation processor tương thích Jakarta Persistence/Hibernate version.

Nếu project không dùng metamodel generator, string-based Criteria vẫn hợp lệ; cần có tests và refactor cẩn thận.

## 11. Tái sử dụng predicates trong Criteria

Một pattern hữu ích là tách logic điều kiện:

~~~java
private List<Predicate> buildOrderPredicates(
        CriteriaBuilder cb,
        Root<Order> order,
        Join<Order, Customer> customer,
        OrderSearchFilter filter) {

    List<Predicate> predicates = new ArrayList<>();

    if (filter.status() != null) {
        predicates.add(
            cb.equal(order.get("status"), filter.status())
        );
    }

    if (filter.customerPrefix() != null
            && !filter.customerPrefix().isBlank()) {
        predicates.add(
            cb.like(
                cb.lower(customer.get("name")),
                filter.customerPrefix().trim().toLowerCase() + "%"
            )
        );
    }

    if (filter.from() != null) {
        predicates.add(
            cb.greaterThanOrEqualTo(
                order.get("createdAt"),
                filter.from()
            )
        );
    }

    if (filter.to() != null) {
        predicates.add(
            cb.lessThan(order.get("createdAt"), filter.to())
        );
    }

    return predicates;
}
~~~

Bộ predicates có thể được áp dụng cho data query và count query. Tuy nhiên, mỗi query vẫn cần tạo Root/Join riêng thuộc CriteriaQuery đó; không tái sử dụng một Path/Predicate gắn với query object khác.

## 12. Criteria count query

Count query cần cùng filters nhưng selection là count:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaQuery<Long> countCq = cb.createQuery(Long.class);
Root<Order> countOrder = countCq.from(Order.class);
Join<Order, Customer> countCustomer =
    countOrder.join("customer", JoinType.INNER);

List<Predicate> countPredicates =
    buildOrderPredicates(
        cb, countOrder, countCustomer, filter
    );

countCq.select(cb.count(countOrder.get("id")));
countCq.where(countPredicates.toArray(Predicate[]::new));

Long total = entityManager.createQuery(countCq)
    .getSingleResult();
~~~

Nếu join một collection để lọc và một Order có nhiều rows phù hợp, dùng `countDistinct` khi semantics cần đếm mỗi Order một lần:

~~~java
countCq.select(cb.countDistinct(countOrder.get("id")));
~~~

Đừng dùng `countDistinct` một cách tự động; nó có thể tốn thêm sort/hash work. Thiết kế joins và count semantics đúng theo quan hệ thực tế.

## 13. Criteria dynamic sorting

Có thể map sort key thành expression allowlist:

~~~java
Path<?> sortPath = switch (filter.sortBy()) {
    case "total" -> order.get("total");
    case "createdAt" -> order.get("createdAt");
    case "id" -> order.get("id");
    default -> throw new IllegalArgumentException("Unsupported sort");
};

jakarta.persistence.criteria.Order sortOrder = filter.descending()
    ? cb.desc(sortPath)
    : cb.asc(sortPath);

cq.orderBy(sortOrder, cb.desc(order.get("id")));
~~~

Ví dụ trên dùng tên type Criteria `Order` đầy đủ để phân biệt với entity `Order` trong domain model. Nếu project đã chuyển sang Jakarta Persistence, import type tương ứng là `jakarta.persistence.criteria.Order`.

Sort key luôn phải được kiểm tra trước khi đưa vào query. Nếu muốn giữ compile-time type mạnh hơn, có thể tạo từng nhánh switch với expression type tương ứng.

## 14. Criteria có phải luôn type-safe không?

Criteria object model cung cấp type information, nhưng mức type safety phụ thuộc cách viết:

- `root.get("createdAt")` dùng string; compiler không biết attribute đó có tồn tại.
- `root.get(Order_.createdAt)` dùng metamodel; compiler kiểm tra tốt hơn.
- `cb.equal` và comparison expressions có generic typing nhưng một số API vẫn cho phép kiểu rộng.
- DTO constructor qua `cb.construct` cần constructor khớp runtime; Java compiler không phải lúc nào cũng xác minh đầy đủ selection list.

Criteria làm query có cấu trúc và ít phụ thuộc string hơn, nhưng không thay thế compile/test/runtime validation.

## 15. Cách 3: DTO projection là result shape

DTO projection có nghĩa query trả về object chỉ chứa dữ liệu ứng dụng cần. Nó tránh việc tạo full managed entity graph cho một read model.

Ví dụ DTO:

~~~java
public record OrderReadRow(
    Long id,
    String customerName,
    Instant createdAt,
    BigDecimal total,
    OrderStatus status
) {}
~~~

Có thể tạo DTO bằng:

| Query technique | Cách tạo DTO |
| --- | --- |
| HQL/JPQL | `select new ...(...)` |
| Criteria | `cb.construct(...)` |
| Spring Data interface projection | Getter interface được map từ selected values |
| Native SQL | `@SqlResultSetMapping`, Hibernate result mapping hoặc manual mapping |

Vì thế DTO projection không phải một query language riêng. Khi người ta nói “dùng DTO projection thay HQL”, cần làm rõ: có thể ý họ là dùng DTO thay entity result, nhưng query vẫn có thể là HQL.

## 16. DTO constructor projection bằng HQL

Đây là ví dụ đã dùng ở phần HQL:

~~~java
TypedQuery<OrderReadRow> query = entityManager.createQuery(
    """
    select new com.example.orders.OrderReadRow(
        o.id,
        c.name,
        o.createdAt,
        o.total,
        o.status
    )
    from Order o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """,
    OrderReadRow.class
);
~~~

Ưu điểm là query và result shape nằm cạnh nhau. Developer nhìn vào `select` biết chính xác DTO nhận những values nào.

Một constructor projection thường không đưa DTO vào persistence context như managed entity. Nếu DTO có field là entity reference thay vì scalar/value, cần hiểu rõ kiểu kết quả và tránh biến DTO thành một graph entity ngoài ý muốn.

## 17. DTO projection bằng Spring Data interface

Spring Data JPA hỗ trợ projection interface trong nhiều repository query patterns:

~~~java
public interface OrderSummaryView {
    Long getId();
    String getCustomerName();
    Instant getCreatedAt();
    BigDecimal getTotal();
}
~~~

Repository có thể khai báo query aliases tương ứng:

~~~java
@Query("""
    select
        o.id as id,
        c.name as customerName,
        o.createdAt as createdAt,
        o.total as total
    from Order o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
List<OrderSummaryView> findSummaries(OrderStatus status);
~~~

Interface projection có thể được Spring Data triển khai bằng projection proxy/tuple mapping tùy query và provider. Alias phải khớp property names mong muốn.

### Interface projection hay record DTO?

| Interface projection | Constructor/record DTO |
| --- | --- |
| Dễ khai báo getter view | Kiểu kết quả cụ thể |
| Hữu ích cho repository projections | Hữu ích cho service/API contracts |
| Có thể dùng projection proxy | Tạo object DTO rõ ràng |
| Nested projection cần cẩn thận | Constructor types/order phải khớp |
| Mapping phụ thuộc Spring Data | JPQL constructor expression chuẩn JPA |

Không phải mọi projection interface đều tối ưu như scalar DTO; nested projections hoặc association getters có thể kích hoạt thêm loads. Kiểm tra SQL thực tế.

## 18. DTO projection không đồng nghĩa query luôn nhanh

DTO có thể giảm entity hydration và L1 cache, nhưng query vẫn có thể chậm nếu:

- Filter không dùng được index.
- Join cardinality lớn.
- Sort phải dùng disk/temp files.
- Query trả quá nhiều rows.
- Count query đắt.
- Database đang lock-wait hoặc bão hòa.
- Driver phải chuyển lượng dữ liệu lớn.
- DTO chứa nhiều columns không cần thiết.

Đánh giá cả execution plan, rows scanned/returned, transfer size và application mapping time. DTO là cách kiểm soát result shape; nó không tự tối ưu database query plan.

## 19. Cách 4: native SQL

Native SQL dùng trực tiếp bảng/cột và cú pháp database:

~~~sql
select
    o.id as order_id,
    c.name as customer_name,
    o.created_at,
    o.total,
    o.status
from orders o
join customers c on c.id = o.customer_id
where o.status = :status
  and lower(c.name) like :customer_pattern
  and o.created_at >= :from_time
  and o.created_at < :to_time
order by o.created_at desc, o.id desc
~~~

Có thể thực thi qua JPA:

~~~java
Query query = entityManager.createNativeQuery(sql);

query.setParameter("status", status.name());
query.setParameter("customer_pattern", prefix.toLowerCase() + "%");
query.setParameter("from_time", from);
query.setParameter("to_time", to);
query.setFirstResult(page * size);
query.setMaxResults(size);

List<?> rawRows = query.getResultList();
~~~

Với native query không khai báo result mapping, JPA thường trả scalar hoặc `Object[]` cho nhiều selected columns. Không nên để application phụ thuộc vào các index và cast rải rác trong nhiều nơi.

## 20. Mapping native SQL thành DTO

Một cách chuẩn của Jakarta Persistence là khai báo `@SqlResultSetMapping` với `@ConstructorResult`:

~~~java
@SqlResultSetMapping(
    name = "OrderReadRowMapping",
    classes = @ConstructorResult(
        targetClass = OrderReadRow.class,
        columns = {
            @ColumnResult(name = "order_id", type = Long.class),
            @ColumnResult(name = "customer_name", type = String.class),
            @ColumnResult(name = "created_at", type = Timestamp.class),
            @ColumnResult(name = "total", type = BigDecimal.class),
            @ColumnResult(name = "status", type = String.class)
        }
    )
)
@Entity
@Table(name = "orders")
public class Order {
    // Entity mapping
}
~~~

Sau đó:

~~~java
@SuppressWarnings("unchecked")
List<OrderReadRow> rows = entityManager
    .createNativeQuery(sql, "OrderReadRowMapping")
    .setParameter("status", status.name())
    .setParameter("customer_pattern", prefix.toLowerCase() + "%")
    .setParameter("from_time", from)
    .setParameter("to_time", to)
    .setFirstResult(page * size)
    .setMaxResults(size)
    .getResultList();
~~~

Constructor của DTO cần nhận đúng các Java types được mapping. Ví dụ trên minh họa mapping `created_at` thành `Timestamp` và `status` thành `String`. Constructor bổ sung trong `OrderReadRow` chuyển chúng sang `Instant` và `OrderStatus`. Trong ví dụ đầy đủ, cần import `java.sql.Timestamp`. Nếu database/driver trả kiểu khác, hãy điều chỉnh constructor/result mapping theo Java type thực tế.

Column labels phải khớp chính xác với `@ColumnResult`. Chú ý database có thể chuẩn hóa alias theo quy tắc chữ hoa/thường; hãy kiểm tra behavior của dialect/driver.

### Mapping native result là một phần công việc

Khi dùng native SQL, developer phải quan tâm:

- Column aliases.
- JDBC types và Java types.
- Enum conversion.
- Temporal conversion/timezone.
- Nullability.
- Numeric precision/scale.
- Constructor signature.
- Mapping behavior theo database/driver.

Đây là mức kiểm soát cao hơn, nhưng cũng tạo thêm code cần bảo trì.

## 21. Native SQL với entity result

Native SQL cũng có thể trả entity nếu result columns đủ để Hibernate hydrate entity:

~~~java
List<Order> orders = entityManager
    .createNativeQuery(
        "select * from orders where status = :status",
        Order.class
    )
    .setParameter("status", status.name())
    .getResultList();
~~~

Query phải trả columns phù hợp entity mapping, bao gồm fields/identifiers cần thiết. Associations và inheritance mappings có thể làm native entity result phức tạp hơn.

Nếu chỉ đọc một view/list, DTO result thường rõ ràng hơn entity mapping. Nếu trả entity, hiểu persistence context, managed state và synchronization semantics của native query.

## 22. Native SQL có thể tận dụng tính năng database-specific

Native SQL đáng cân nhắc khi cần:

- Window functions.
- Common Table Expressions (CTE), recursive queries.
- Vendor-specific JSON/array operators.
- Full-text search operators.
- Lateral joins.
- Hints hoặc optimizer-specific features.
- Stored procedures.
- Database-specific date/time or analytic functions.
- Query plans cần cấu trúc khó diễn đạt bằng JPQL/HQL portable.

Ví dụ window function để xếp hạng đơn hàng theo khách hàng:

~~~sql
select
    o.id,
    o.customer_id,
    o.total,
    row_number() over (
        partition by o.customer_id
        order by o.created_at desc, o.id desc
    ) as row_num
from orders o
~~~

Nếu database hỗ trợ tốt và query cần tính năng đó, native SQL có thể là lựa chọn hợp lý. Đổi lại, query gắn chặt hơn với dialect/database và schema names.

## 23. Count query cho native SQL

Với native pagination, cần count query riêng nếu API cần total:

~~~sql
select count(*)
from orders o
join customers c on c.id = o.customer_id
where o.status = :status
  and lower(c.name) like :customer_pattern
  and o.created_at >= :from_time
  and o.created_at < :to_time
~~~

Trong Spring Data, native paged query thường cần khai báo count query rõ ràng cho SQL phức tạp:

~~~java
@Query(
    value = """
        select
            o.id as order_id,
            c.name as customer_name,
            o.created_at,
            o.total,
            o.status
        from orders o
        join customers c on c.id = o.customer_id
        where o.status = :status
        order by o.created_at desc, o.id desc
        """,
    countQuery = """
        select count(*)
        from orders o
        join customers c on c.id = o.customer_id
        where o.status = :status
        """,
    nativeQuery = true
)
Page<Object[]> findNativePage(OrderStatus status, Pageable pageable);
~~~

Đây là skeleton minh họa. Với query có nhiều optional filters, cả `value` và `countQuery` phải dùng đúng cùng predicates. Một số database/dialect có giới hạn pagination syntax; Spring Data/provider sẽ cần tạo hoặc áp dụng pagination theo khả năng tương ứng.

Nếu API chỉ cần `hasNext` hoặc cursor pagination, có thể thiết kế query lấy `size + 1` rows và tránh count tổng thể, nếu nghiệp vụ cho phép.

## 24. So sánh cùng một nhu cầu: bốn phiên bản

| Tiêu chí | HQL | Criteria | DTO projection | Native SQL |
| --- | --- | --- | --- | --- |
| Bản chất | Query language | Query-building API | Result shape | SQL trực tiếp |
| Biểu đạt filters | String/parameters | Predicate objects | Phụ thuộc query nguồn | SQL/parameters |
| Dynamic query | Có thể ghép string có kiểm soát | Rất phù hợp | Không tự quyết định | Có thể dựng SQL động an toàn |
| Type safety | Một phần, chủ yếu runtime cho query string | Tốt hơn với static metamodel | Constructor/interface contract | Thấp hơn, phụ thuộc mapping |
| Entity awareness | Có | Có | Có thể không cần entity | Không tự hiểu mapping trừ result mapping |
| Portability | JPQL subset portable; HQL extensions riêng | JPA Criteria portable | Tùy cách triển khai | Thấp hơn, phụ thuộc DB |
| SQL control | Provider sinh SQL | Provider sinh SQL | Không quyết định SQL | Cao |
| DTO support | Constructor projection | `cb.construct` | Chính là mục tiêu | Result mapping/manual mapping |
| Maintainability | Tốt cho query ổn định | Tốt cho filter phức tạp, nhưng verbose | Tốt cho read contracts | Cần kỷ luật alias/type/schema |
| Best fit | Query rõ, ít biến thể | Search/filter động | Read models/API/list/report | DB-specific/SQL phức tạp |

Không có lựa chọn nào luôn nhanh nhất. HQL và Criteria thường đi qua cùng Hibernate query engine và có thể sinh SQL tương đương nếu biểu đạt cùng query. Native SQL cho quyền kiểm soát SQL cao hơn nhưng không tự động nhanh hơn.

## 25. So sánh độ dễ đọc và bảo trì

### HQL

Query thường ngắn và gần với domain:

~~~java
select new OrderReadRow(...)
from Order o
join o.customer c
where o.status = :status
~~~

Người đọc thấy entity và association trực tiếp. Đây thường là lựa chọn dễ tiếp cận cho query có hình dạng ổn định.

### Criteria

Query được biểu diễn thành nhiều Java objects:

~~~java
cb.equal(order.get("status"), status);
cb.lessThan(order.get("createdAt"), to);
~~~

Nhiều code hơn nhưng thuận lợi khi số lượng filters thay đổi theo request và cần tái sử dụng predicate builders.

### DTO projection

Làm rõ contract của read model:

~~~java
public record OrderReadRow(...) {}
~~~

Nó giúp API không phụ thuộc entity graph và tránh trả fields ngoài nhu cầu.

### Native SQL

Rất rõ khi developer hiểu schema và SQL, nhưng cần bảo trì aliases, types, dialect differences và migrations khi đổi database.

## 26. So sánh hiệu năng đúng cách

Không thể kết luận bằng một benchmark query đơn giản rằng HQL nhanh hơn Criteria hay native SQL nhanh hơn HQL. Nếu cùng logic, Hibernate thường chuyển HQL/Criteria thành SQL rồi gửi qua cùng JDBC driver/database.

Các yếu tố thường quyết định hiệu năng hơn cú pháp:

- Execution plan và index.
- Số rows database phải đọc.
- Join cardinality và row multiplication.
- Số columns trả về.
- Số SQL round trips.
- Count query cost.
- Driver fetch behavior.
- Entity hydration so với DTO materialization.
- Persistence context size.
- Cache state.
- Transaction isolation/lock waits.
- Network latency.

Một HQL query DTO có thể nhanh hơn HQL query trả entity vì nó không hydrate entity graph; nhưng đó là khác biệt result shape/fetch behavior, không phải HQL string tự nhanh hơn.

## 27. Đọc query plan và SQL thực tế

Với HQL/Criteria, cần xem SQL Hibernate sinh ra. Với native SQL, cần xem chính câu SQL đã viết. Trong cả hai trường hợp, database execution plan mới cho biết cách DB thực thi.

Quy trình:

1. Bật SQL logging hoặc datasource query capture trong môi trường kiểm thử.
2. Xác nhận SQL và bind parameter types.
3. Chạy `EXPLAIN` hoặc công cụ execution plan của database.
4. Kiểm tra index scan/seek, sequential scan, joins, sort và estimates.
5. So sánh estimated rows với actual rows nếu DB hỗ trợ.
6. Đo execution time, rows returned và network payload.
7. Đo cả endpoint latency và application-side mapping time.

Không bật bind-value TRACE rộng rãi trên production nếu values chứa thông tin nhạy cảm. Dùng sampling/redaction và môi trường an toàn.

## 28. Pagination: offset, keyset và stable ordering

Cả HQL, Criteria và native SQL đều có thể phân trang, nhưng pagination semantics phải được thiết kế giống nhau.

Offset pagination:

~~~text
page = 0, size = 20 -> rows 1..20
page = 1, size = 20 -> rows 21..40
~~~

Ưu điểm là dễ dùng cho UI có số trang. Nhược điểm là offset lớn có thể tốn chi phí và dữ liệu thay đổi giữa requests có thể làm lặp/bỏ sót rows.

Sort phải có tie-breaker ổn định:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Nếu chỉ sort `created_at`, nhiều rows có cùng timestamp có thể đổi thứ tự giữa các lần query.

Keyset pagination dùng cursor cuối cùng:

~~~sql
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
ORDER BY created_at DESC, id DESC
FETCH FIRST :size ROWS ONLY
~~~

Cú pháp giới hạn rows khác nhau theo database; Hibernate/JPA có thể dùng `setMaxResults` với query phù hợp. Keyset thường hiệu quả hơn cho dữ liệu lớn nhưng cần cursor gồm đủ sort keys và filter ổn định.

## 29. Count query có thể là bottleneck riêng

Một API trả `Page<T>` thường thực hiện:

1. Query lấy content.
2. Query `count(*)` để tính tổng.

Với filter có joins, count query có thể đắt ngang hoặc đắt hơn query lấy page. Nếu người dùng không cần tổng số trang chính xác, cân nhắc `Slice`, `hasNext` hoặc cursor pagination.

Không copy nguyên query data rồi đổi `select` thành `count` mà giữ fetch joins, ordering hoặc projection phức tạp. Count query cần được thiết kế theo số root rows cần đếm.

## 30. Filter tùy chọn và SQL plan

Một cách viết query thường gặp:

~~~sql
WHERE (:status IS NULL OR o.status = :status)
  AND (:from IS NULL OR o.created_at >= :from)
~~~

Nó tiện vì chỉ cần một query string, nhưng predicate kiểu `parameter is null OR column = parameter` có thể làm optimizer khó dùng index hoặc chọn plan kém tùy database/statistics.

Có hai hướng:

- Dựng predicates động chỉ khi filter được cung cấp.
- Dùng query cố định nếu database optimizer xử lý tốt và workload đã đo.

HQL string builder và Criteria đều hỗ trợ predicates động. Native SQL cũng có thể dựng fragments, nhưng chỉ nối fragments/identifiers do code kiểm soát và bind toàn bộ values.

## 31. Null, case sensitivity và thời gian phải giống nhau

Khi so sánh các query implementations, cùng input không đủ; semantics cũng phải giống nhau.

### Null semantics

`column = NULL` không tương đương `column IS NULL`. Dùng parameter predicates có chủ đích và quyết định null input có nghĩa “bỏ filter” hay “tìm rows có null”.

### Case sensitivity

`lower(name) like ...` có thể cho kết quả khác collation-specific `ILIKE`, case-insensitive collation hoặc accent folding. HQL/Criteria/native phải áp dụng cùng quy tắc nghiệp vụ.

### Timezone

`Instant`, `OffsetDateTime`, `LocalDateTime` và SQL timestamp không có cùng semantics. Xác định timezone chuẩn và chuyển input trước khi query. Dùng khoảng nửa mở `[from, to)` nếu phù hợp.

### Decimal

`BigDecimal` precision/scale và rounding cần được giữ nhất quán. Đừng cast total sang floating point trong native query nếu nghiệp vụ yêu cầu tiền tệ chính xác.

## 32. Join và association mapping

HQL/Criteria có thể join theo association:

~~~java
join o.customer c
~~~

Điều này dùng mapping `Order.customer` để xác định join condition.

Native SQL cần viết join condition:

~~~sql
join customers c on c.id = o.customer_id
~~~

Lợi ích của association join:

- Tên thuộc tính phản ánh domain model.
- FK mapping được quản lý tại entity.
- Ít lặp lại chi tiết schema.
- Dễ thay tên cột nếu mapping thay đổi.

Lợi ích của native join:

- Có thể join bảng/view không được map thành entity.
- Có thể dùng database-specific join syntax.
- Kiểm soát chính xác điều kiện và optimizer hints nếu DB hỗ trợ.

Association join không tự đảm bảo query tối ưu; mapping sai hoặc cardinality không phù hợp vẫn tạo SQL đắt.

## 33. HQL/Criteria query cache và Hibernate cache

HQL và Criteria có thể tham gia các cơ chế query cache của Hibernate nếu được cấu hình và đánh dấu phù hợp. Native query cũng có hỗ trợ cache-specific theo Hibernate/provider configuration, nhưng cần hiểu query spaces và invalidation.

Đừng bật query cache chỉ vì query là read-only. Cache phù hợp khi:

- Query lặp lại thường xuyên.
- Kết quả ít thay đổi.
- Cache provider được cấu hình có giới hạn.
- Invalidation behavior rõ.
- Hit/miss metrics cho thấy lợi ích.

DTO projection không tự bật query cache và không tự bảo đảm kết quả cacheable. Cache là một quyết định riêng với query/result semantics.

## 34. Read-only transaction và entity state

Với read use case, có thể dùng:

~~~java
@Transactional(readOnly = true)
public List<OrderReadRow> search(...) {
    // execute read query
}
~~~

Read-only transaction giúp thể hiện ý định và một số framework/provider có thể tối ưu flush behavior. Nhưng nó không tự biến query thành DTO, không tự giảm columns và không đảm bảo database cấm writes.

DTO projection thường giảm managed entity state vì result không phải entity. Nếu query trả entities, chúng có thể được managed trong persistence context dù method là read-only; behavior tối ưu phụ thuộc Spring/Hibernate configuration.

## 35. Security: parameter binding và tenant/authorization filters

Cả HQL, Criteria và native SQL phải kiểm soát input.

- Bind giá trị qua parameters.
- Allowlist sort columns/directions.
- Không nối raw user input vào query string.
- Kiểm tra quyền truy cập trước khi chạy query.
- Nếu dữ liệu phân tenant, áp tenant restriction theo architecture đã chọn.
- Không giả định native SQL tự kế thừa mọi Hibernate filters hoặc entity-level restrictions.
- Test cả đường query native và ORM.

Ví dụ parameter binding:

~~~java
query.setParameter("status", status);
~~~

Không an toàn:

~~~java
String sql = "select * from orders where status = '" + input + "'";
~~~

Criteria giảm nguy cơ ghép chuỗi query, nhưng không thay authorization và input validation.

## 36. Spring Data repository: chọn cách viết theo độ phức tạp

Một repository có thể kết hợp nhiều style:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Query("""
        select new com.example.orders.OrderReadRow(
            o.id, c.name, o.createdAt, o.total, o.status
        )
        from Order o
        join o.customer c
        where o.status = :status
        order by o.createdAt desc, o.id desc
        """)
    List<OrderReadRow> findReadRows(OrderStatus status);
}
~~~

Với filter phức tạp và nhiều tổ hợp:

- Spring Data `Specification` có thể dựng Criteria predicates.
- Custom repository implementation có thể dùng Criteria API.
- HQL `@Query` phù hợp query ổn định, dễ đọc.
- Native `@Query` phù hợp khi cần SQL-specific behavior.
- Projection interface/DTO quyết định shape của kết quả.

Không cần ép toàn bộ repository vào một phong cách. Hãy chọn cách dễ hiểu và kiểm thử nhất cho từng query.

## 37. Pattern Criteria với data query và count query

Khi cùng bộ filter cần dùng hai lần, tạo helper để dựng predicates nhưng tạo query roots riêng:

~~~java
private Predicate[] predicatesFor(
        CriteriaBuilder cb,
        Root<Order> order,
        Join<Order, Customer> customer,
        OrderSearchFilter filter) {

    List<Predicate> result = new ArrayList<>();

    if (filter.status() != null) {
        result.add(cb.equal(order.get("status"), filter.status()));
    }

    if (filter.customerPrefix() != null
            && !filter.customerPrefix().isBlank()) {
        result.add(cb.like(
            cb.lower(customer.get("name")),
            filter.customerPrefix().trim().toLowerCase() + "%"
        ));
    }

    if (filter.from() != null) {
        result.add(cb.greaterThanOrEqualTo(
            order.get("createdAt"), filter.from()
        ));
    }

    if (filter.to() != null) {
        result.add(cb.lessThan(order.get("createdAt"), filter.to()));
    }

    return result.toArray(Predicate[]::new);
}
~~~

Data query và count query đều gọi helper nhưng truyền `Root`/`Join` của chính query đó. Criteria nodes gắn với query tree; không chia sẻ một `Predicate` instance giữa hai CriteriaQuery độc lập.

## 38. Kiểm thử bốn cách đọc trên cùng fixture

Tạo fixture nhỏ có:

- Customer Alice và An.
- Customer Bob.
- Một số Orders thuộc trạng thái PAID/NEW.
- Hai Orders có cùng `createdAt` để kiểm tra tie-breaker.
- Orders nằm đúng trước/sau `from` và `to`.
- Một customer name có chữ hoa/thường khác nhau.

Với cùng `OrderSearchFilter`, chạy:

1. HQL constructor projection.
2. Criteria constructor projection.
3. DTO projection qua Spring Data (hoặc HQL/Criteria).
4. Native SQL result mapping.

So sánh:

- Cùng IDs và cùng thứ tự.
- Cùng customer names.
- Cùng decimal totals.
- Cùng time boundaries.
- Cùng total count.
- Cùng behavior khi filter optional/null.
- Cùng page boundary và tie-breaker.

Đây là cách phát hiện khác biệt semantics trước khi benchmark.

## 39. Kiểm tra số SQL statements

Có thể bật Hibernate Statistics trong integration test:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Sau khi reset statistics và chạy query:

~~~java
Statistics statistics = sessionFactory.getStatistics();
statistics.clear();

List<OrderReadRow> rows = orderReader.search(filter);

long statements = statistics.getPrepareStatementCount();
~~~

Với native SQL, Hibernate statistics có thể đếm statements được thực hiện qua Hibernate; nếu dùng JDBC trực tiếp ngoài SessionFactory, cần datasource-level instrumentation để quan sát đầy đủ.

Đừng chỉ so số statements. Một query có thể trả hàng triệu rows trong khi ba queries nhỏ hơn lại nhanh hơn. Ghi cả rows, execution plan, payload, p95/p99 và application mapping time.

## 40. Benchmark công bằng

Để so sánh:

- Dùng cùng database và cùng dataset.
- Dùng cùng indexes/statistics.
- Dùng cùng bind values và result shape.
- Warm up JVM, connection pool và database cache.
- Chạy nhiều vòng, không kết luận từ một lần.
- So sánh cold-cache và warm-cache nếu production có cả hai tình huống.
- Đo content query và count query riêng.
- Ghi throughput, p50/p95/p99 và allocations.
- Không bật SQL TRACE cho một implementation nhưng tắt cho implementation khác.
- Kiểm tra execution plans để hiểu khác biệt.

Nếu HQL và Criteria tạo cùng SQL, performance thường gần nhau. Nếu native SQL nhanh hơn đáng kể, tìm khác biệt thực sự ở SQL plan, hints, selected columns, joins hoặc bind types thay vì quy kết chỉ do query language.

## 41. Troubleshooting theo dấu hiệu

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| HQL báo unknown entity/property | Dùng table/column name thay entity/attribute name | Kiểm tra mapping và HQL path |
| Criteria compile nhưng runtime lỗi attribute | Dùng string path sai | Dùng static metamodel và integration test |
| DTO constructor không khớp | Sai thứ tự/type/constructor | So khớp select expressions và DTO constructor |
| Native trả `Object[]` | Chưa khai báo result mapping | Dùng `@SqlResultSetMapping` hoặc mapping phù hợp |
| Native temporal type khác dự kiến | JDBC driver/dialect mapping | Kiểm tra `ColumnResult` và conversion |
| HQL/Criteria có N+1 | Truy cập lazy associations hoặc eager secondary selects | DTO/fetch plan/batch fetching |
| Native query thiếu tenant restriction | Native SQL không tự thêm mọi ORM filters | Thêm predicate/policy phù hợp |
| Page content đúng, total sai | Count query thiếu hoặc thừa joins/filters | Đồng bộ count semantics |
| Page lặp/mất rows | Sort không unique hoặc data thay đổi | Thêm tie-breaker/keyset |
| Filter optional làm query chậm | OR-null predicates hoặc plan không tốt | Dynamic predicates/EXPLAIN |
| Native SQL chạy trên DB A nhưng lỗi DB B | Vendor-specific syntax/types | Tách dialect hoặc giữ query portable |
| Criteria quá dài | Quá nhiều builder fragments | Tách predicate/query factory có kiểm soát |

## 42. Những anti-patterns cần tránh

**1. Dùng native SQL cho mọi query vì nghĩ nó luôn nhanh hơn.**

Native SQL có thể kiểm soát tốt, nhưng tăng coupling với schema/database và mapping burden. Hãy chứng minh lợi ích bằng execution plan và benchmark.

**2. Dùng Criteria cho query tĩnh rất đơn giản.**

Một query vài dòng có thể dễ đọc hơn bằng HQL/JPQL. Criteria hữu ích khi query cần composition/dynamic predicates.

**3. Gọi DTO projection là một query language.**

DTO là result shape. Hãy chỉ rõ query được viết bằng HQL, Criteria, Spring Data hoặc native SQL.

**4. Trả entity cho một read endpoint chỉ cần vài fields.**

Có thể hydrate nhiều state và khiến serializer trigger lazy loading. Dùng DTO khi phù hợp.

**5. Ghép input vào HQL/SQL.**

Bind values; allowlist identifiers/sort expressions.

**6. Dùng cùng một data query làm count query bằng cách thay SELECT.**

Fetch joins, distinct và joins có thể khiến count sai hoặc đắt.

**7. Paginate collection fetch join.**

SQL rows có thể nhân theo collection; page root entities không còn đơn giản.

**8. So sánh performance bằng thời gian một lần chạy.**

JIT, caches, DB load và network variance có thể làm kết quả sai lệch.

**9. Giả định native SQL kế thừa toàn bộ Hibernate behavior.**

Native SQL không tự hiểu mọi mapping filters, entity graph, dirty checking hoặc tenant restrictions.

## 43. Bảng chọn nhanh theo nhu cầu

| Nhu cầu | Điểm bắt đầu hợp lý |
| --- | --- |
| Query đơn giản, cố định, đọc entity | HQL/JPQL |
| Query đơn giản, chỉ lấy một số fields | HQL/JPQL DTO projection |
| Nhiều filters tùy chọn | Criteria hoặc HQL builder có kiểm soát |
| Search API có sort/filter động | Criteria + DTO projection |
| Report cần aggregates/joins rõ ràng | HQL/Criteria projection; native nếu cần DB feature |
| Dùng window functions/CTE/vendor operators | Native SQL |
| Cần portability giữa databases | JPQL/Criteria và portable functions |
| Query plan phải kiểm soát chi tiết | Native SQL sau khi benchmark |
| API read model ổn định | DTO projection qua query phù hợp |
| Cần entity lifecycle/cascade để cập nhật | Entity query trong transaction |

Đây là điểm bắt đầu, không phải luật cứng. Query nhỏ, dễ hiểu và được đo tốt quan trọng hơn việc dùng một công nghệ duy nhất cho toàn module.

## 44. Quy trình ra quyết định

~~~text
Bắt đầu từ nhu cầu đọc
        |
        v
Cần managed entity lifecycle?
   |                  |
  Có                 Không
   |                  |
HQL/Criteria       Chỉ cần fields cụ thể?
entity query          |
                  DTO projection
                      |
                      v
             Query tĩnh hay động?
                |           |
              Tĩnh         Động
                |           |
             HQL/JPQL    Criteria hoặc
                         HQL builder
                \           /
                 \         /
                  v       v
            Có cần tính năng DB-specific?
                  |          |
                 Có         Không
                  |          |
             Native SQL   ORM query
                  \          /
                   v        v
              Test semantics + SQL
                       |
                       v
              Benchmark cùng workload
~~~

Một quy trình thực tế:

1. Viết rõ fields/filter/sort/page cần thiết.
2. Chọn result shape: entity, scalar, DTO hay aggregate.
3. Chọn HQL/Criteria/native theo độ động và yêu cầu SQL.
4. Viết data query và count query có semantics tương đương.
5. Kiểm tra parameter binding, null, timezone và ordering.
6. Chạy integration tests với cùng fixture.
7. Xem SQL và execution plan.
8. Benchmark cùng workload.
9. Chọn giải pháp dễ bảo trì đáp ứng latency/throughput mục tiêu.

## 45. Bài tập thực hành

**Bài 1 — HQL entity result**

Viết HQL lấy Orders trạng thái PAID và Customer, trả `List<Order>`. Kiểm tra associations nào được load và query count khi duyệt danh sách.

**Bài 2 — HQL DTO**

Chuyển query trên sang `OrderReadRow`. Chỉ select ID, customer name, created time và total. So sánh entity load count và SQL payload.

**Bài 3 — Criteria filters**

Cho phép status, customer prefix, from và to đều optional. Viết helper tạo predicates và count query tương ứng.

**Bài 4 — DTO projection**

Tạo `OrderSummaryView` interface hoặc record DTO. Kiểm tra serializer không cần truy cập entity associations.

**Bài 5 — Native SQL**

Viết native query cùng filters. Dùng result-set mapping để trả DTO; không trả `Object[]` ra service/API.

**Bài 6 — Pagination**

Tạo hai Orders có cùng timestamp. Xác nhận sort `(createdAt DESC, id DESC)` tạo thứ tự ổn định. Thử offset và keyset.

**Bài 7 — Query plan**

Chạy EXPLAIN cho HQL-generated SQL và native SQL tương đương. Ghi index, join strategy, estimated/actual rows và execution time.

**Bài 8 — Count query**

Tạo customer có nhiều Orders. Xác nhận count đếm Orders, không bị nhân bởi joins/collections.

**Bài 9 — Security**

Thử customer prefix có ký tự nháy và chuỗi giống SQL. Xác nhận parameter binding không làm thay đổi query structure.

**Bài 10 — Portability**

Chạy query trên hai databases nếu hệ thống hỗ trợ. Ghi lại khác biệt về timestamp, case-insensitive matching, pagination và native result types.

## 46. Checklist khi đưa query đọc vào production

- Query có đúng filters và null semantics?
- Có parameter binding cho tất cả values?
- Sort key được allowlist và có tie-breaker ổn định?
- Page content và count dùng cùng điều kiện?
- Có chọn đúng fields cần trả?
- Có tạo entity graph không cần thiết?
- Có nguy cơ N+1 hoặc row multiplication?
- DTO constructor/result mapping khớp Java/JDBC types?
- Native SQL có đúng dialect và authorization predicates?
- Tenant/soft-delete/security restrictions có áp dụng ở mọi query path?
- Có test boundary timestamps và decimal precision?
- Có integration test trên database/driver mục tiêu?
- Đã xem SQL và execution plan?
- Đã đo query count, rows, p95/p99 và memory?
- Đã benchmark trong cùng điều kiện?
- Có thể giải thích lý do chọn query technique?

## 47. Tổng kết

HQL, Criteria API, DTO projection và native SQL không phải bốn đối thủ cùng giải quyết một tầng của bài toán. HQL và Criteria là cách biểu đạt query; native SQL là cách viết SQL trực tiếp; DTO projection là cách định hình kết quả đọc. Một DTO có thể được tạo bởi cả HQL, Criteria hoặc native SQL.

Với cùng nhu cầu tìm và phân trang Orders:

1. **HQL** dễ đọc cho query ổn định, hướng entity và có thể constructor-project thẳng sang DTO.
2. **Criteria API** phù hợp khi nhiều filters/sorts tùy chọn cần được compose bằng Java objects; static metamodel tăng type safety.
3. **DTO projection** giúp trả đúng fields cần, giảm entity hydration và tránh phụ thuộc lazy graph trong read endpoints.
4. **Native SQL** phù hợp khi cần database-specific features hoặc kiểm soát SQL chính xác, đổi lại phải quản lý dialect, aliases, JDBC types và result mapping.
5. Không có query language nào tự bảo đảm hiệu năng; index, execution plan, cardinality, rows, round trips và transaction mới quyết định phần lớn chi phí.
6. Data query và count query phải giữ cùng semantics; pagination cần sort ổn định và có thể dùng keyset cho tập dữ liệu lớn.
7. Cùng một fixture và workload là cách đáng tin cậy để so sánh kết quả và hiệu năng.

Hãy bắt đầu từ **read model và nhu cầu của use case**, chọn query technique phù hợp, rồi xác nhận bằng integration tests, SQL và execution plan. Cách đó giúp ứng dụng vừa dễ bảo trì vừa có hiệu năng có thể đo lường.

## Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide — HQL and query language](https://docs.hibernate.org/orm/6.6/querylanguage/html_single/)
- [Hibernate ORM 7.2 Query Language Guide](https://docs.hibernate.org/orm/7.2/querylanguage/html_single/)
- [Hibernate ORM 6.6 User Guide — Native SQL](https://docs.hibernate.org/orm/6.6/userguide/html_single/)
- [Hibernate ORM 7.2 Javadocs — NativeQuery](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/query/NativeQuery.html)
- [Jakarta Persistence 3.2 Specification — Query Language and Criteria API](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2)
- [Jakarta Persistence 3.2 API — CriteriaBuilder](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/criteria/criteriabuilder)
- [Jakarta Persistence 3.2 API — SqlResultSetMapping](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/sqlresultsetmapping)
- [Spring Data JPA — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Data JPA — Query methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)

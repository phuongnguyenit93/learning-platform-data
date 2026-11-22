# Join, fetch, truy vấn con và điều kiện tồn tại

Jakarta Persistence Criteria API cho phép xây dựng truy vấn bằng Java object thay vì ghép chuỗi JPQL/HQL. Khi bộ lọc của màn hình tìm kiếm thay đổi theo đầu vào người dùng, Criteria API giúp tạo các điều kiện có kiểm soát, phối hợp **join**, **fetch plan**, **subquery**, `exists` và `not exists`, đồng thời sử dụng parameter binding và metadata entity.

Điểm quan trọng không phải chỉ học cách gọi `root.join()` hoặc `query.subquery()`, mà là phân biệt những ý định:

- **Join**: nối bảng/association để lọc, chọn, sắp xếp hoặc nhóm dữ liệu.
- **Fetch**: chỉ định association nào cần được khởi tạo khi entity được trả về, tránh lazy load không mong muốn.
- **Subquery**: biểu diễn một truy vấn lồng bên trong truy vấn khác.
- **`EXISTS` / `NOT EXISTS`**: kiểm tra sự tồn tại hoặc không tồn tại của hàng thỏa điều kiện, thường không cần đưa các hàng con vào kết quả.
- **Dynamic predicates**: chỉ thêm điều kiện khi người dùng thực sự cung cấp bộ lọc, thay vì tạo nhiều query string khác nhau.

Một `Join` và một `Fetch` không phải cùng một loại Java object trong Criteria API. Một `LEFT JOIN` cũng không tự bảo đảm giữ mọi entity gốc nếu sau đó `WHERE` có điều kiện loại `NULL`. Khi join collection, một order có thể xuất hiện trên nhiều SQL rows; khi fetch collection cùng pagination, kết quả có thể không còn phân trang hiệu quả ở database. Bài học đi từ mô hình cơ sở đến các tổ hợp truy vấn và kiểm thử để tránh những lỗi này.

## 1. Mô hình ví dụ: đơn hàng, khách hàng và dòng hàng

Giả sử hệ thống bán hàng có:

```text
Customer 1 ───── 0..* PurchaseOrder
                       |
                       | 1 ───── 0..* OrderLine
                       |
                    optional customer
```

Quy tắc nghiệp vụ:

- Một `PurchaseOrder` có thể chưa gán `Customer`; `customer_id` được phép `NULL`.
- Một order có nhiều `OrderLine`.
- Mỗi `OrderLine` thuộc một order.
- Màn hình tìm kiếm có thể lọc theo trạng thái, khoảng ngày, tên khách hàng, sản phẩm, tổng tiền và việc có/không có dòng hàng phù hợp.

Entity mẫu:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

enum OrderStatus {
    DRAFT, CONFIRMED, PAID, CANCELLED
}

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    protected Customer() {}

    public Long getId() { return id; }
    public String getName() { return name; }
    public String getEmail() { return email; }
}

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal total;

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(name = "customer_id", nullable = true)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public OrderStatus getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public BigDecimal getTotal() { return total; }
    public Customer getCustomer() { return customer; }
    public List<OrderLine> getLines() { return lines; }
}

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public Long getId() { return id; }
    public PurchaseOrder getOrder() { return order; }
    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
}
```

Các code fragment về query phía dưới giả định có `EntityManager em` đang mở trong phạm vi transaction hoặc unit of work phù hợp. Ví dụ không bao gồm toàn bộ bootstrapping `EntityManagerFactory`, migration hay dữ liệu seed.

## 2. Dữ liệu mẫu để phân tích kết quả

Giả sử database có:

**customers**

| id | name | email |
| --- | --- | --- |
| 1 | An | an@example.org |
| 2 | Bình | binh@example.org |

**purchase_orders**

| id | status | customer_id | total |
| --- | --- | --- | ---: |
| 10 | PAID | 1 | 120.00 |
| 11 | DRAFT | NULL | 0.00 |
| 12 | CONFIRMED | 2 | 300.00 |
| 13 | PAID | NULL | 75.00 |

**order_lines**

| id | order_id | sku | quantity |
| --- | --- | --- | ---: |
| 101 | 10 | SKU-A | 2 |
| 102 | 10 | SKU-B | 1 |
| 103 | 12 | SKU-A | 4 |
| 104 | 13 | SKU-C | 3 |

Khi hỏi “tất cả order”, kỳ vọng có bốn bản ghi: 10, 11, 12, 13.

Khi hỏi “order có ít nhất một dòng SKU-A”, kỳ vọng có order 10 và 12.

Khi hỏi “order không có dòng hàng”, kỳ vọng order 11.

Khi hỏi “order không có khách hàng”, kỳ vọng order 11 và 13.

Dữ liệu này giúp phát hiện các sai lệch về `INNER JOIN`, `LEFT JOIN`, `WHERE`, row duplication và điều kiện tồn tại.

## 3. Cấu trúc nền tảng của một CriteriaQuery

Một query lấy tất cả order:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Root;

CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root = cq.from(PurchaseOrder.class);

cq.select(root)
  .orderBy(cb.asc(root.get("id")));

List<PurchaseOrder> result = em.createQuery(cq).getResultList();
```

Các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `CriteriaBuilder` | Factory tạo `Predicate`, `Expression`, query và các phép toán |
| `CriteriaQuery<T>` | Mô tả query trả kiểu `T` |
| `Root<T>` | Entity gốc trong `FROM` |
| `Path<T>` | Đường dẫn thuộc tính từ root hoặc join |
| `Expression<T>` | Biểu thức có kiểu kết quả |
| `Predicate` | Điều kiện boolean/logic query |
| `Join<Z, X>` | Association join từ `Z` sang `X` |
| `Fetch<Z, X>` | Yêu cầu fetch một association |
| `Subquery<T>` | Truy vấn con trả biểu thức kiểu `T` |
| `TypedQuery<T>` | Query có thể bind parameter và thực thi |

Tương đương JPQL:

```jpql
select o
from PurchaseOrder o
order by o.id
```

Trong Criteria, `root.get("id")` trỏ đến tên **property Java**, không phải bắt buộc là tên cột SQL.

### 3.1. Dynamic query không có nghĩa SQL miễn phí

Criteria API vẫn được Hibernate phân tích và dịch sang SQL. Nếu ứng dụng tạo một query có 20 joins và vài correlated subqueries, database vẫn phải thực hiện các phép nối/lọc đó. Criteria cung cấp cách xây dựng và type model; nó không tự tối ưu mọi query.

## 4. `Join` tường minh trong Criteria

Để nối `PurchaseOrder.customer`:

```java
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.JoinType;

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.INNER);

cq.select(order)
  .where(cb.equal(customer.get("name"), "An"));

List<PurchaseOrder> result = em.createQuery(cq).getResultList();
```

JPQL tương đương:

```jpql
select o
from PurchaseOrder o
join o.customer c
where c.name = 'An'
```

SQL minh họa:

```sql
select o.*
from purchase_orders o
join customers c on c.id = o.customer_id
where c.name = ?;
```

`JoinType.INNER` loại các order không có customer row phù hợp.

### 4.1. Chọn loại join

Jakarta Criteria định nghĩa `JoinType.INNER`, `JoinType.LEFT` và `JoinType.RIGHT`.

```java
order.join("customer", JoinType.INNER);
order.join("customer", JoinType.LEFT);
```

`RIGHT` được API mô tả nhưng tính portable và mức hỗ trợ không đồng đều giữa provider; trong query nghiệp vụ thường dễ thay bằng việc đổi root hoặc dùng `LEFT JOIN`.

Để join một collection:

```java
Join<PurchaseOrder, OrderLine> line =
    order.join("lines", JoinType.INNER);
```

Mỗi hàng line được nối tới owner tương ứng, vì thế một order có nhiều lines có thể xuất hiện trên nhiều SQL result rows.

### 4.2. `root.join("customer")` mặc định là inner

```java
Join<PurchaseOrder, Customer> customer =
    order.join("customer");
```

Theo Criteria API, overload không chỉ định `JoinType` dùng **inner join**.

Nếu association có thể null và yêu cầu giữ các order không có customer, phải yêu cầu `JoinType.LEFT` một cách tường minh.

## 5. Association tùy chọn và `LEFT JOIN`

Mapping:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
private Customer customer;
```

cho phép một order không có customer. Nhưng query cần quyết định có giữ nó hay không.

```java
Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.LEFT);

cq.multiselect(order, customer);
```

Đoạn code `multiselect` phù hợp khi `CriteriaQuery` được khai báo với kiểu tuple/`Object[]` tương ứng; với `CriteriaQuery<PurchaseOrder>` chỉ cần:

```java
cq.select(order);
```

Một ví dụ đầy đủ trả `Tuple`:

```java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.LEFT);

cq.multiselect(
    order.alias("order"),
    customer.alias("customer")
);

List<Tuple> rows = em.createQuery(cq).getResultList();

for (Tuple row : rows) {
    PurchaseOrder o = row.get("order", PurchaseOrder.class);
    Customer c = row.get("customer", Customer.class); // Có thể null.
}
```

Với dữ liệu mẫu, bốn order đều có thể xuất hiện. Order 11 và 13 có `customer = null`.

**`optional = true` không tự chọn `LEFT JOIN` trong mọi Criteria query.** Nó mô tả khả năng association bị thiếu; query phải biểu đạt có giữ root row hay không.

## 6. Bẫy `LEFT JOIN` kết hợp `WHERE`

Giả sử cần trả tất cả order, nhưng chỉ gắn thông tin customer nếu customer tên “An”.

Viết:

```java
Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.LEFT);

cq.select(order)
  .where(cb.equal(customer.get("name"), "An"));
```

Dù join là LEFT, `WHERE c.name = 'An'` loại những hàng mà c.name null hoặc khác “An”. Kết quả chỉ còn order 10.

SQL tương đương:

```sql
select o.*
from purchase_orders o
left join customers c on c.id = o.customer_id
where c.name = 'An';
```

Các order không customer tạo row có `c.name = NULL`; biểu thức `NULL = 'An'` cho UNKNOWN, nên bị `WHERE` loại.

### 6.1. Đặt điều kiện vào `ON` nếu muốn giữ root

```java
Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.LEFT);

customer.on(cb.equal(customer.get("name"), "An"));

cq.multiselect(order, customer);
```

Với `CriteriaQuery<Tuple>` thích hợp, kết quả có thể là:

| Order | Customer alias |
| --- | --- |
| 10 | An |
| 11 | null |
| 12 | null (Bình không thỏa điều kiện ON) |
| 13 | null |

SQL minh họa:

```sql
select o.*, c.*
from purchase_orders o
left join customers c
  on c.id = o.customer_id
 and c.name = 'An';
```

**Phân biệt hai yêu cầu nghiệp vụ:**

- “Chỉ lấy order có customer tên An” → `INNER JOIN` hoặc `LEFT JOIN` + `WHERE` (nếu cố ý).
- “Lấy mọi order, nhưng chỉ nối customer tên An” → `LEFT JOIN` + điều kiện `ON`.

Không chuyển mọi predicate từ WHERE sang ON theo thói quen; phải xác định điều kiện lọc **root** hay điều kiện lọc **phía phải của join**.

### 6.2. `OR customer IS NULL` không hoàn toàn tương đương ON

```java
cq.where(cb.or(
    cb.equal(customer.get("name"), "An"),
    cb.isNull(customer.get("id"))
));
```

Câu này giữ order không có customer và order có customer An, nhưng **không giữ order có customer Bình**. Ngược lại, `ON c.name = 'An'` vẫn giữ order Bình, chỉ không nối customer alias đó.

## 7. Join nhiều tầng

Giả sử Customer có `Address address` tùy chọn:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
private Address address;
```

Muốn giữ mọi order, bất kể thiếu customer hoặc address:

```java
Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.LEFT);

Join<Customer, Address> address =
    customer.join("address", JoinType.LEFT);
```

Nếu viết:

```java
Join<Customer, Address> address =
    customer.join("address", JoinType.INNER);
```

thì phép inner join ở tầng sau có thể làm những order không có address bị loại. Một left join ở tầng đầu không tự khiến những join tiếp theo thành left join.

### 7.1. Điều hướng path có thể tạo join ngầm định

```java
order.get("customer").get("name")
```

là điều hướng qua association. Hibernate/JPA có thể cần tạo implicit join để truy cập thuộc tính `name`. Đường dẫn đó có thể mang inner semantics, nên không phải cách phù hợp nếu cần kiểm soát rõ optional association.

Khi null behavior quan trọng, ưu tiên explicit `join("customer", JoinType.LEFT)` và dùng alias `customer.get("name")`.

### 7.2. Đọc khóa ngoại không luôn cần join bảng đích

Để so với một customer entity hoặc identifier, Hibernate có thể tận dụng FK được ánh xạ mà không phải join đầy đủ tới bảng customers:

```java
cq.where(cb.equal(order.get("customer"), customerEntity));
```

Kết quả SQL phụ thuộc mapping, dialect và provider. Đừng suy số JOIN từ số dấu chấm trong source; xem SQL thực tế khi cần tối ưu.

## 8. Join collection và hiện tượng trùng root

Một order có hai lines. Khi join:

```java
Join<PurchaseOrder, OrderLine> line =
    order.join("lines", JoinType.INNER);

cq.select(order)
  .where(cb.equal(line.get("sku"), "SKU-A"));
```

Nếu một order có nhiều lines cùng thỏa điều kiện, SQL có thể trả **nhiều rows cho cùng order**.

Với dữ liệu mẫu:

```sql
select o.*
from purchase_orders o
join order_lines l on l.order_id = o.id
where l.sku = 'SKU-A';
```

kỳ vọng có order 10 và 12. Nếu order 10 có hai dòng SKU-A, SQL result có thể lặp order 10.

### 8.1. `distinct(true)`

Khi chỉ muốn root entity duy nhất:

```java
cq.select(order)
  .distinct(true)
  .where(cb.equal(line.get("sku"), "SKU-A"));
```

`distinct(true)` yêu cầu query result loại trùng theo semantics Criteria. Hình dạng SQL, cơ chế lọc trùng khi fetch entity và tác động pagination phụ thuộc provider, query shape và version.

Không hiểu `distinct(true)` như bảo đảm “database không bao giờ xử lý row trùng”. Join to-many vẫn có thể tạo nhiều SQL rows trước khi được rút gọn.

### 8.2. `countDistinct` cho count query

Khi cần tổng số order thỏa điều kiện join collection:

```java
CriteriaQuery<Long> countQuery = cb.createQuery(Long.class);
Root<PurchaseOrder> order = countQuery.from(PurchaseOrder.class);

Join<PurchaseOrder, OrderLine> line =
    order.join("lines", JoinType.INNER);

countQuery.select(cb.countDistinct(order.get("id")))
          .where(cb.equal(line.get("sku"), "SKU-A"));
```

`cb.count(order)` sau join có thể đếm **số rows đã join**, không phải số order duy nhất. Nếu một order có nhiều lines, tổng số sẽ sai cho pagination.

### 8.3. Đếm distinct không miễn phí

`COUNT(DISTINCT ...)` có thể khiến database phải deduplicate. Nếu câu hỏi chỉ là “order có tồn tại một line phù hợp không?”, correlated `EXISTS` thường biểu đạt đúng ý định và tránh làm phình root rows.

## 9. `Join` và `Fetch` là hai API khác nhau

Một điểm hay gây nhầm lẫn:

```java
Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.LEFT);
```

và:

```java
Fetch<PurchaseOrder, Customer> customerFetch =
    order.fetch("customer", JoinType.LEFT);
```

không tương đương về API và ý nghĩa.

- `Join` là một phần **query từ đó có thể điều hướng thuộc tính**, dùng trong predicate, selection và order.
- `Fetch` biểu diễn **fetch plan**: yêu cầu association được khởi tạo cùng entity owner khi query trả về.
- Interface `Fetch` **không kế thừa `Path`** và không có API `.get("name")` giống `Join`.
- Không dùng cast `((Join<?, ?>) root.fetch(...))` như giải pháp portable; đó là phụ thuộc implementation.
- Một join thông thường không phải cam kết `customer` đã được fetched; còn fetch join có mục tiêu tải association.

### 9.1. Ví dụ `fetch()` cho to-one

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);
order.fetch("customer", JoinType.LEFT);

cq.select(order)
  .where(cb.equal(order.get("status"), OrderStatus.PAID));

List<PurchaseOrder> orders = em.createQuery(cq).getResultList();
```

HQL tương đương về ý nghĩa:

```hql
select o
from PurchaseOrder o
left join fetch o.customer
where o.status = :status
```

Order không có customer vẫn được giữ. Với order có customer, association được fetch theo kế hoạch; không cần lazy SELECT riêng chỉ để đọc `customer.name` trong kịch bản bình thường.

### 9.2. Không fetch khi chỉ dùng association để lọc

```java
Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.INNER);

cq.where(cb.equal(customer.get("email"), emailParam));
```

Nếu query chỉ cần lọc theo email nhưng trả DTO không dùng các field customer, `join()` thường đủ. Fetch thêm có thể tốn băng thông/heap.

### 9.3. Không coi `fetch()` là `join()` để lọc

Một số code cố:

```java
Join<PurchaseOrder, Customer> customer =
    (Join<PurchaseOrder, Customer>) order.fetch("customer");
```

Việc cast có thể hoạt động hoặc không tùy provider implementation, nhưng **không phải hợp đồng chuẩn của Criteria API**. Để lọc, dùng `join`. Để fetch, dùng `fetch`. Nếu cần cả hai, có thể cần hai cấu trúc hoặc chọn giải pháp khác như `EntityGraph`/query thiết kế lại; kiểm tra SQL để tránh join trùng.

## 10. Fetch collection và N+1

Giả sử lấy 50 order, sau đó lặp:

```java
List<PurchaseOrder> orders = em.createQuery(cq).getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getLines().size());
}
```

Nếu `lines` là LAZY và chưa được initialized, Hibernate có thể gửi thêm SELECT cho từng order: **N+1**.

Có thể fetch collection:

```java
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);
order.fetch("lines", JoinType.LEFT);

cq.select(order).distinct(true);
```

HQL tương đương:

```hql
select distinct o
from PurchaseOrder o
left join fetch o.lines
```

Fetch collection giúp nạp dữ liệu con trong query ban đầu, nhưng có trade-off:

- Một order có nhiều lines có thể tạo nhiều SQL rows.
- Fetch nhiều collections cùng lúc có thể gây Cartesian multiplication.
- `distinct(true)` giúp xử lý duplicate root result, không làm giảm mọi row truyền qua network.
- Pagination trực tiếp trên fetch collection có thể bị xử lý trong memory/cảnh báo/exception tùy Hibernate setting và version.
- Với collection lớn, hydrate toàn bộ lines chỉ để đếm có thể rất tốn.

### 10.1. Fetch to-one khác fetch to-many

Fetch một to-one như `customer` thường không làm nhân số rows theo một owner, nên dễ kết hợp pagination hơn.

Fetch to-many như `lines` tạo nhiều rows cho mỗi order; phải cân nhắc cardinality và phân trang.

### 10.2. Không dùng fetch để thay thế mọi query projection

Nếu API chỉ cần:

```text
orderId, orderNumber, customerName, lineCount
```

thì một query DTO/projection có `LEFT JOIN`, aggregate/grouping hoặc subquery có thể rẻ hơn việc fetch toàn bộ entity graph.

## 11. Fetch plan bằng EntityGraph

Ngoài `root.fetch(...)`, Jakarta Persistence có `EntityGraph` để chỉ định association cần tải.

Ví dụ:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> orders = em.createQuery(cq)
    .setHint("jakarta.persistence.fetchgraph", graph)
    .getResultList();
```

Entity graph và Criteria predicates có thể kết hợp: Criteria chọn **bản ghi nào**, graph gợi ý/yêu cầu **association nào cần fetch**.

Lợi ích:

- Không cần ép `Fetch` thành `Join`.
- Fetch plan có thể được chọn theo use case.
- Có thể tái sử dụng một Criteria query với các graph khác nhau.

Tuy vậy, không giả định mọi graph luôn tạo SQL JOIN duy nhất; provider có thể lựa chọn secondary select hoặc chiến lược fetch phù hợp. Hãy xem SQL trên đúng Hibernate version.

## 12. Pagination: vì sao join fetch collection là bẫy

Giả sử màn hình hiển thị 20 order mỗi trang. Nếu viết:

```java
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);
order.fetch("lines", JoinType.LEFT);

List<PurchaseOrder> page = em.createQuery(cq)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

Một order có thể tương ứng nhiều SQL rows. Nếu database `LIMIT 20` theo SQL rows, một order với 30 lines có nguy cơ chiếm quá số dòng và làm thiếu collection hoặc thiếu số root mong muốn. Hibernate có thể tránh làm hỏng graph bằng cách xử lý pagination trong memory hoặc theo hành vi/version-specific khác.

**Không nên dùng fetch collection trực tiếp trong pageable query mà không xác minh behavior thực tế.**

### 12.1. Cách hai pha: phân trang IDs rồi fetch dữ liệu

**Pha 1:** tìm ID order trong page, chỉ join những gì cần để lọc/sắp xếp.

```java
CriteriaQuery<Long> idQuery = cb.createQuery(Long.class);
Root<PurchaseOrder> order = idQuery.from(PurchaseOrder.class);

idQuery.select(order.get("id"))
       .orderBy(
           cb.desc(order.get("createdAt")),
           cb.desc(order.get("id"))
       );

List<Long> ids = em.createQuery(idQuery)
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
```

**Pha 2:** fetch order và lines theo tập IDs:

```java
if (ids.isEmpty()) {
    return List.of();
}

CriteriaQuery<PurchaseOrder> dataQuery =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order = dataQuery.from(PurchaseOrder.class);
order.fetch("lines", JoinType.LEFT);

dataQuery.select(order)
         .distinct(true)
         .where(order.get("id").in(ids));

List<PurchaseOrder> pageData =
    em.createQuery(dataQuery).getResultList();
```

Pha hai không tự giữ thứ tự của danh sách `ids`; nếu UI cần đúng thứ tự page, hãy reorder các kết quả trong Java theo vị trí ID từ pha một hoặc tạo ORDER BY phù hợp.

Ngoài ra, cần áp dụng bộ lọc nghiệp vụ, quyền truy cập và tenant conditions nhất quán giữa các pha, sử dụng transaction/isolation phù hợp nếu yêu cầu snapshot nhất quán giữa query ID và query dữ liệu.

### 12.2. Batch fetching cũng là lựa chọn

Nếu không muốn fetch toàn bộ collection ngay:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@org.hibernate.annotations.BatchSize(size = 16)
private List<OrderLine> lines;
```

Batch fetching có thể gom các lazy collection cùng role trong persistence context, giảm N+1 mà không đưa collection vào SQL của query phân trang root.

## 13. Dynamic predicates: chỉ thêm bộ lọc khi được cung cấp

Giả sử màn hình có các bộ lọc:

```java
public record OrderFilter(
    OrderStatus status,
    Instant createdFrom,
    Instant createdTo,
    String customerName,
    BigDecimal minimumTotal,
    String sku,
    Boolean hasLines
) {}
```

Các trường có thể null, nghĩa là người dùng không bật bộ lọc đó.

Cách xây:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

List<Predicate> predicates = new ArrayList<>();

if (filter.status() != null) {
    predicates.add(
        cb.equal(order.get("status"), filter.status())
    );
}

if (filter.createdFrom() != null) {
    predicates.add(
        cb.greaterThanOrEqualTo(
            order.<Instant>get("createdAt"),
            filter.createdFrom()
        )
    );
}

if (filter.createdTo() != null) {
    predicates.add(
        cb.lessThan(
            order.<Instant>get("createdAt"),
            filter.createdTo()
        )
    );
}

if (filter.minimumTotal() != null) {
    predicates.add(
        cb.greaterThanOrEqualTo(
            order.<BigDecimal>get("total"),
            filter.minimumTotal()
        )
    );
}

cq.select(order)
  .where(cb.and(predicates.toArray(Predicate[]::new)))
  .orderBy(
      cb.desc(order.get("createdAt")),
      cb.desc(order.get("id"))
  );

List<PurchaseOrder> result = em.createQuery(cq).getResultList();
```

Đây là nền tảng của dynamic Criteria query. Các điều kiện join và subquery sẽ được thêm khi cần.

### 13.1. `cb.conjunction()` và `cb.disjunction()`

- `cb.conjunction()` là predicate luôn TRUE khi chưa có điều kiện con.
- `cb.disjunction()` là predicate luôn FALSE khi chưa có điều kiện con.
- `cb.and()` với mảng rỗng có semantics TRUE theo JPA.
- `cb.or()` với mảng rỗng có semantics FALSE.

Khi người dùng chưa chọn bộ lọc nào, `cb.and(empty)` cho phép trả tất cả bản ghi **nếu business policy cho phép**. Với màn hình cần tenant isolation, phải luôn bổ sung tenant predicate bắt buộc, không được mặc định query toàn hệ thống.

### 13.2. `NULL` và “không có bộ lọc” khác nhau

Nếu `filter.customerName() == null`, có thể hiểu là **không lọc theo tên**.

Nếu người dùng muốn tìm order **không có customer**, cần một lựa chọn lọc riêng, ví dụ:

```java
predicates.add(cb.isNull(order.get("customer")));
```

Không dùng cùng một `null` parameter vừa đại diện “bỏ qua filter” vừa đại diện “IS NULL”, vì hai ý định truy vấn khác nhau.

## 14. Dynamic join khi có bộ lọc theo khách hàng

Khi người dùng cung cấp `customerName`, query cần join Customer:

```java
if (filter.customerName() != null
        && !filter.customerName().isBlank()) {

    Join<PurchaseOrder, Customer> customer =
        order.join("customer", JoinType.INNER);

    predicates.add(
        cb.equal(customer.get("name"), filter.customerName())
    );
}
```

Ở đây dùng `INNER` vì yêu cầu là **chỉ lấy order có customer đúng tên**. Order không có customer đương nhiên không match.

Nếu UI muốn giữ mọi order và chỉ hiển thị customer name khi phù hợp, đó là projection join với `LEFT + ON`, không phải predicate lọc root.

### 14.1. Không join nếu không cần

Nếu `filter.customerName()` rỗng, không nhất thiết tạo `join("customer")`. Một query nhỏ hơn sẽ dễ hiểu hơn và có thể tiết kiệm chi phí DB.

Một query builder tốt không tạo mọi association join sẵn rồi mới quyết định có dùng hay không, trừ khi fetch/projection thực sự cần.

### 14.2. Với LIKE cần phân biệt wildcard và input nguyên văn

```java
ParameterExpression<String> namePattern =
    cb.parameter(String.class, "namePattern");

predicates.add(
    cb.like(cb.lower(customer.get("name")), namePattern)
);
```

Sau đó bind:

```java
query.setParameter(
    "namePattern",
    "%" + filter.customerName().toLowerCase(Locale.ROOT) + "%"
);
```

Đây là tìm kiếm chứa chuỗi, trong đó `%` và `_` là wildcard SQL. Nếu muốn coi `%`/`_` trong input là ký tự bình thường, cần escape theo quy tắc `LIKE`/dialect và overload escape character phù hợp. Parameter binding ngăn injection qua giá trị nhưng không tự escape wildcard semantics.

## 15. Tái sử dụng join thay vì tạo trùng

Một câu query có thể cần nhiều điều kiện trên cùng association:

```java
Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.INNER);

predicates.add(cb.equal(customer.get("name"), name));
predicates.add(cb.equal(customer.get("email"), email));
```

Đây là cùng một join có alias được tái sử dụng.

Nếu mỗi helper lại gọi:

```java
order.join("customer", JoinType.INNER);
```

thì Criteria tree có thể chứa nhiều joins của cùng association. Hibernate có thể tối ưu một số trường hợp, nhưng không nên phụ thuộc vào việc provider luôn hợp nhất những join có semantics khác nhau.

Một query builder lớn có thể truyền `Join` qua helper hoặc lưu map theo association path + join type + ON-condition policy. Không tái sử dụng một `INNER` join cho nhu cầu `LEFT` nếu điều đó làm sai null semantics.

### 15.1. Join cùng collection với nhiều điều kiện có thể thay đổi ý nghĩa

Giả sử muốn order có:

- Một line SKU-A.
- Một line quantity lớn hơn 3.

Một join duy nhất:

```java
Join<PurchaseOrder, OrderLine> line =
    order.join("lines", JoinType.INNER);

predicates.add(cb.equal(line.get("sku"), "SKU-A"));
predicates.add(cb.greaterThan(line.get("quantity"), 3));
```

yêu cầu **cùng một line** vừa có SKU-A vừa quantity trên 3.

Nếu nghiệp vụ cho phép hai điều kiện nằm ở **hai line khác nhau**, một join duy nhất là sai. Cần hai joins độc lập hoặc hai EXISTS subqueries với ngữ nghĩa rõ ràng.

Đây là điểm đặc biệt quan trọng khi xây filter động theo nhiều thuộc tính collection.

## 16. Subquery trong Criteria API

Subquery là một truy vấn lồng trong query lớn. Nó có thể trả scalar hoặc được dùng trong `EXISTS`, `IN`, `ANY`, `ALL` và biểu thức khác theo quy tắc JPA/provider.

Ví dụ: tìm order có tổng tiền lớn hơn **trung bình của tất cả order**.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Subquery<Double> avgSubquery = cq.subquery(Double.class);
Root<PurchaseOrder> avgOrder =
    avgSubquery.from(PurchaseOrder.class);

avgSubquery.select(cb.avg(avgOrder.get("total")));

cq.select(order)
  .where(cb.greaterThan(
      order.<BigDecimal>get("total"),
      avgSubquery.as(BigDecimal.class)
  ));
```

Đây là **minh họa về scalar subquery và type conversion**; `AVG` đối với `BigDecimal` thường được CriteriaBuilder thể hiện qua `Expression<Double>`, nhưng database/Hibernate type derivation và cast có thể khác. Với phép so tiền tệ cần giữ precision, có thể dùng subquery tính ngưỡng với kiểu phù hợp hoặc truyền ngưỡng `BigDecimal` đã được xác định trước. Không dùng ví dụ này như công thức tài chính bắt buộc.

Subquery được khai báo từ `CriteriaQuery` hoặc một subquery cha:

```java
Subquery<Long> sub = cq.subquery(Long.class);
```

Nó có root, joins, selection, predicates và có thể tham chiếu/correlate root của query ngoài theo API phù hợp.

### 16.1. Subquery trong JPQL/Criteria có giới hạn vị trí

Jakarta Persistence truyền thống hỗ trợ subquery chủ yếu trong `WHERE` và `HAVING`; các khả năng subquery trong `SELECT`/`FROM` có thể được HQL/Hibernate mở rộng nhưng không portable cho mọi provider.

Nếu cần bảng dẫn xuất trong FROM hoặc lateral join, hãy kiểm tra Hibernate version/query language, hoặc dùng native SQL có mapping phù hợp thay vì giả định Criteria JPA chuẩn luôn hỗ trợ.

## 17. `EXISTS`: tìm order có ít nhất một dòng hàng phù hợp

Yêu cầu: tìm mọi order có ít nhất một line với `sku = :sku`.

Có thể join collection, nhưng join tạo một row cho mỗi line match. `EXISTS` tập trung đúng câu hỏi **“có tồn tại không?”**.

Cách 1: dùng root độc lập trong subquery và so FK/association với root ngoài:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Subquery<Integer> sub = cq.subquery(Integer.class);
Root<OrderLine> line = sub.from(OrderLine.class);

ParameterExpression<String> skuParam =
    cb.parameter(String.class, "sku");

sub.select(cb.literal(1))
   .where(
       cb.equal(line.get("order"), order),
       cb.equal(line.get("sku"), skuParam)
   );

cq.select(order)
  .where(cb.exists(sub))
  .orderBy(cb.asc(order.get("id")));

List<PurchaseOrder> results = em.createQuery(cq)
    .setParameter("sku", "SKU-A")
    .getResultList();
```

HQL tương đương:

```hql
select o
from PurchaseOrder o
where exists (
    select 1
    from OrderLine l
    where l.order = o
      and l.sku = :sku
)
order by o.id
```

SQL minh họa:

```sql
select o.*
from purchase_orders o
where exists (
    select 1
    from order_lines l
    where l.order_id = o.id
      and l.sku = ?
)
order by o.id;
```

Kết quả với dữ liệu mẫu: order 10 và 12.

### 17.1. Vì sao dùng `select 1`?

Trong `EXISTS`, database chỉ cần biết subquery có trả ít nhất một hàng hay không. Giá trị của biểu thức select thường không quan trọng. `cb.literal(1)` là cách viết ngắn gọn, rõ ý định.

`EXISTS` không yêu cầu trả từng `OrderLine` ra kết quả chính. Database optimizer có thể sử dụng chiến lược semi-join hoặc dừng tìm sau match đầu tiên, nhưng kế hoạch thực tế phụ thuộc DBMS, index, thống kê và query shape.

### 17.2. `EXISTS` không tự làm query nhanh hơn trong mọi trường hợp

Trong một số database, `JOIN + DISTINCT`, `IN` và `EXISTS` được optimizer biến đổi thành kế hoạch tương đương. Đừng khẳng định `EXISTS` luôn nhanh hơn; lợi thế đầu tiên của nó là **đúng semantics và không nhân root result theo số child match**.

## 18. Correlated subquery bằng `correlate()`

Criteria API có thể **correlate** root hoặc join từ query ngoài vào subquery:

```java
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Subquery<Integer> sub = cq.subquery(Integer.class);

Root<PurchaseOrder> correlatedOrder =
    sub.correlate(order);

Join<PurchaseOrder, OrderLine> line =
    correlatedOrder.join("lines", JoinType.INNER);

sub.select(cb.literal(1))
   .where(
       cb.equal(line.get("sku"), "SKU-A")
   );

cq.select(order)
  .where(cb.exists(sub));
```

Mô hình:

```text
Outer query:
  FROM PurchaseOrder order
           │
           │ correlate(order)
           ▼
Subquery:
  correlated PurchaseOrder order
           │
           └─ JOIN order.lines line
                   WHERE line.sku = 'SKU-A'
```

Cách này biểu đạt trực tiếp “với từng order ở query ngoài, có một line phù hợp không?”.

### 18.1. Correlate không phải copy query độc lập

`sub.correlate(order)` tạo correlated root trong phạm vi subquery, liên kết với outer root. Không đồng nghĩa “copy toàn bộ result list order vào subquery” ở Java. Hibernate dịch nó thành SQL correlated predicate/join theo semantics cần thiết.

Có thể correlate các thành phần như `Root`, `Join`, `CollectionJoin`, `SetJoin`, `ListJoin`, `MapJoin` qua overload tương ứng trong Criteria API.

### 18.2. Khi nào dùng `correlate()`?

Dùng khi subquery cần đi theo association bắt đầu từ một root/join đã có ở query ngoài. Nó giúp code phản ánh cấu trúc domain mà không phải tự so hai root bằng `cb.equal(line.get("order"), order)`.

Hai cách thường có thể đạt semantics giống nhau, nhưng SQL shape/optimization có thể khác theo provider.

## 19. `NOT EXISTS`: tìm order không có dòng hàng

Yêu cầu: tìm order chưa có `OrderLine`.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Subquery<Integer> sub = cq.subquery(Integer.class);
Root<OrderLine> line = sub.from(OrderLine.class);

sub.select(cb.literal(1))
   .where(cb.equal(line.get("order"), order));

cq.select(order)
  .where(cb.not(cb.exists(sub)));
```

HQL tương đương:

```hql
select o
from PurchaseOrder o
where not exists (
    select 1
    from OrderLine l
    where l.order = o
)
```

Kết quả dữ liệu mẫu: order 11.

### 19.1. `NOT EXISTS` khác `NOT IN` khi có null

Trong SQL, `NOT IN (subquery)` có thể tạo kết quả không mong đợi nếu tập giá trị chứa `NULL`, do logic ba giá trị.

Ví dụ:

```sql
where o.id not in (select l.order_id from order_lines l)
```

nếu `order_id` có null (trong schema khác), kết quả có thể bị ảnh hưởng khác với trực giác.

`NOT EXISTS` với predicate tương quan thường biểu đạt rõ ý định “không có hàng con match” và ít gặp bẫy null hơn.

Tuy nhiên, vẫn phải xác định đúng correlation; một `NOT EXISTS` subquery **không correlate** có thể trả cùng một boolean cho mọi order, làm sai hoàn toàn bộ lọc.

### 19.2. Left join + `IS NULL` là lựa chọn khác

```java
Join<PurchaseOrder, OrderLine> line =
    order.join("lines", JoinType.LEFT);

cq.where(cb.isNull(line.get("id")));
```

Có thể biểu đạt order không có lines, nhưng với điều kiện join bổ sung hoặc schema phức tạp cần thận trọng. `NOT EXISTS` thường rõ hơn khi điều kiện là absence của **một tập child rows thỏa tiêu chí**.

## 20. Tìm order không có dòng SKU bị cấm

Yêu cầu: không có line nào dùng SKU thuộc danh sách cấm.

```java
Subquery<Integer> sub = cq.subquery(Integer.class);
Root<OrderLine> line = sub.from(OrderLine.class);

sub.select(cb.literal(1))
   .where(
       cb.equal(line.get("order"), order),
       line.get("sku").in(bannedSkus)
   );

Predicate noBannedSku = cb.not(cb.exists(sub));
```

Điểm quan trọng: `NOT EXISTS` kiểm tra toàn bộ các child rows có thuộc tính phù hợp. Nó **khác**:

```java
Join<PurchaseOrder, OrderLine> line =
    order.join("lines", JoinType.INNER);

cb.notEqual(line.get("sku"), "SKU-X");
```

Một order có cả SKU-X và SKU-A vẫn có line SKU-A thỏa `<> SKU-X`, nên query với join và `notEqual` có thể **trả order chứa SKU-X**, sai ý định.

Muốn phủ định “tồn tại bất kỳ line xấu nào”, dùng `NOT EXISTS` trên tập line xấu.

### 20.1. Danh sách `IN` rỗng

Nếu `bannedSkus` rỗng, application nên xác định semantics:

- Không có SKU nào bị cấm → bỏ qua filter, mọi order đều hợp lệ.
- Nếu UI coi danh sách trống là input lỗi → trả validation error.

Không truyền collection rỗng vào `IN` rồi mặc định mọi DBMS/provider xử lý giống nhau; SQL `IN ()` có thể không hợp lệ ở một số dialect/version.

## 21. Hai điều kiện tồn tại trên hai line khác nhau

Yêu cầu: order có ít nhất một line SKU-A **và** ít nhất một line SKU-B.

Một join duy nhất với:

```java
cb.and(
    cb.equal(line.get("sku"), "SKU-A"),
    cb.equal(line.get("sku"), "SKU-B")
)
```

không thể đúng cho một line có một giá trị `sku` duy nhất.

Cách dùng hai subqueries độc lập:

```java
Subquery<Integer> hasA = cq.subquery(Integer.class);
Root<OrderLine> lineA = hasA.from(OrderLine.class);

hasA.select(cb.literal(1))
    .where(
        cb.equal(lineA.get("order"), order),
        cb.equal(lineA.get("sku"), "SKU-A")
    );

Subquery<Integer> hasB = cq.subquery(Integer.class);
Root<OrderLine> lineB = hasB.from(OrderLine.class);

hasB.select(cb.literal(1))
    .where(
        cb.equal(lineB.get("order"), order),
        cb.equal(lineB.get("sku"), "SKU-B")
    );

cq.where(
    cb.and(
        cb.exists(hasA),
        cb.exists(hasB)
    )
);
```

Như vậy hai điều kiện có thể được thỏa bởi **hai dòng hàng khác nhau**.

Nếu nghiệp vụ muốn một line duy nhất thỏa cả hai điều kiện khác nhau, dùng một join/một EXISTS kết hợp predicates trên cùng alias mới đúng.

## 22. So sánh `EXISTS`, join và `COUNT`

Ba cách diễn đạt một nhu cầu tồn tại:

**Join + DISTINCT:**

```java
Join<PurchaseOrder, OrderLine> line =
    order.join("lines", JoinType.INNER);

cq.select(order).distinct(true)
  .where(cb.equal(line.get("sku"), sku));
```

**Correlated EXISTS:**

```java
Subquery<Integer> sub = cq.subquery(Integer.class);
Root<OrderLine> line = sub.from(OrderLine.class);

sub.select(cb.literal(1))
   .where(
       cb.equal(line.get("order"), order),
       cb.equal(line.get("sku"), sku)
   );

cq.select(order).where(cb.exists(sub));
```

**Correlated COUNT:**

```java
Subquery<Long> sub = cq.subquery(Long.class);
Root<OrderLine> line = sub.from(OrderLine.class);

sub.select(cb.count(line))
   .where(
       cb.equal(line.get("order"), order),
       cb.equal(line.get("sku"), sku)
   );

cq.where(cb.greaterThan(sub, 0L));
```

`EXISTS` thường biểu đạt ý định tốt nhất nếu chỉ cần boolean có/không. `COUNT` phù hợp khi cần **bao nhiêu** phần tử; join phù hợp khi cần **truy xuất thuộc tính của child** hoặc lọc/sắp xếp theo child.

Database có thể tối ưu các dạng này thành kế hoạch gần nhau. Chọn semantics đúng trước, đo performance sau.

## 23. Truy vấn con với scalar aggregate

Yêu cầu: tìm order có tổng tiền **lớn hơn giá trị trung bình đơn hàng**.

Ví dụ với query scalar trên kiểu số:

```java
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Subquery<Double> avgSub = cq.subquery(Double.class);
Root<PurchaseOrder> other = avgSub.from(PurchaseOrder.class);

avgSub.select(cb.avg(other.<BigDecimal>get("total")));

cq.select(order)
  .where(cb.gt(
      order.<BigDecimal>get("total"),
      avgSub
  ));
```

`cb.gt(Expression<? extends Number>, Expression<? extends Number>)` thích hợp cho numeric expressions. Hàm `AVG` trong Criteria trả `Expression<Double>`, dù cột tiền dùng `BigDecimal`; nếu nghiệp vụ tài chính nhạy với precision, cần cân nhắc cách tính ngưỡng/kiểu số ở DB. Không chuyển tùy tiện toàn bộ money fields sang `double`.

### 23.1. Subquery theo từng customer

Yêu cầu: tìm order có tổng tiền lớn nhất trong các order của cùng customer.

Một dạng correlated query so sánh tổng tiền với `max(total)`:

```java
Subquery<BigDecimal> maxSub =
    cq.subquery(BigDecimal.class);

Root<PurchaseOrder> other =
    maxSub.from(PurchaseOrder.class);

maxSub.select(
    cb.greatest(other.<BigDecimal>get("total"))
).where(
    cb.equal(other.get("customer"), order.get("customer"))
);

cq.where(
    cb.equal(order.get("total"), maxSub)
);
```

Cần cân nhắc:

- Order có `customer = NULL` không nên vô tình bị gộp thành một nhóm customer giả.
- Nếu có hai order cùng tổng tiền lớn nhất, query có thể trả cả hai.
- Nếu cần đúng một order mới nhất theo customer, cần tie-breaker như `createdAt`/`id`, hoặc dùng window function phù hợp.
- Database optimizer cần index theo customer/total nếu query chạy trên dữ liệu lớn.

Đây là ví dụ so sánh aggregate tương quan; không phải lời hứa một SQL plan tối ưu cho mọi DBMS.

## 24. Subquery với `IN`

Yêu cầu: lấy order có customer thuộc tập khách hàng có email theo domain.

```java
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Subquery<Long> customerIds =
    cq.subquery(Long.class);
Root<Customer> customer =
    customerIds.from(Customer.class);

customerIds.select(customer.get("id"))
           .where(
               cb.like(
                   customer.get("email"),
                   "%@example.org"
               )
           );

cq.select(order)
  .where(order.get("customer").get("id").in(customerIds));
```

Ví dụ mang tính minh họa. Điều hướng `order.get("customer").get("id")` có thể được provider tối ưu theo FK, nhưng cũng có thể có semantics join. Với association nullable, order không customer không match tập ID.

Nếu cần chắc chắn về join semantics và portability, dùng explicit join hoặc so sánh association với subquery/entity IDs theo mapping phù hợp.

### 24.1. `IN` hay `EXISTS`?

- `IN`: biểu đạt membership trong tập giá trị.
- `EXISTS`: biểu đạt có ít nhất một hàng thỏa tương quan.
- `JOIN`: đưa entity liên quan vào query và có thể chọn/sắp xếp thuộc tính của nó.

Kết quả có thể tương đương trong nhiều trường hợp nhưng `NULL` và duplicate semantics khác nhau. Đừng thay `NOT EXISTS` bằng `NOT IN` mà không xét null.

## 25. Các hàm collection chuẩn: `isEmpty`, `isMember`, `size`

CriteriaBuilder có các biểu thức cho collection association:

```java
cb.isEmpty(order.get("lines"))
cb.isNotEmpty(order.get("lines"))
cb.size(order.get("lines"))
```

Tùy overload/typing, với static metamodel sẽ dễ type-check hơn:

```java
cb.isEmpty(order.get(PurchaseOrder_.lines));
```

Trong Criteria string-based, nếu compiler không suy luận được kiểu `Expression<Collection<E>>`, cần khai báo path có generic type phù hợp hoặc dùng join/subquery.

Ví dụ:

```java
cq.where(cb.isEmpty(order.get("lines")));
```

ý định là tìm order không có lines. Provider có thể dịch thành `NOT EXISTS` hoặc SQL tương đương.

### 25.1. `isMember`

Nếu có entity `OrderLine targetLine`:

```java
cb.isMember(targetLine, order.get("lines"))
```

biểu đạt phần tử thuộc collection. Nhưng phải hiểu semantics của managed/detached entity identity và kiểu collection. Trong nhiều trường hợp, query theo FK/order ID hoặc `EXISTS` sẽ rõ hơn.

### 25.2. Khi nào dùng collection function thay subquery?

`isEmpty` rất gọn để kiểm tra collection rỗng. `EXISTS` hữu ích khi cần predicate trên child, ví dụ line có SKU-A và quantity trên 2. `size` hữu ích khi cần số lượng nhưng có thể tạo correlated count; nếu cần paging/count/aggregate trên nhiều hàng, hãy xem SQL và query plan.

## 26. Static Metamodel giúp kiểm tra tên thuộc tính lúc biên dịch

String-based Criteria:

```java
order.get("customer")
order.get("status")
order.join("lines")
```

dễ lỗi nếu rename field Java mà quên sửa string.

Jakarta Persistence Static Metamodel có thể được sinh bởi annotation processor:

```java
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Join<PurchaseOrder, Customer> customer =
    order.join(PurchaseOrder_.customer, JoinType.LEFT);

Predicate paid =
    cb.equal(order.get(PurchaseOrder_.status), OrderStatus.PAID);

Join<PurchaseOrder, OrderLine> line =
    order.join(PurchaseOrder_.lines, JoinType.INNER);
```

Các class `PurchaseOrder_`, `Customer_`, `OrderLine_` là metamodel được generate, không xuất hiện tự nhiên nếu project chưa cấu hình annotation processor.

Ví dụ với Hibernate annotation processor, artifact và cấu hình Gradle/Maven phải tương thích đúng phiên bản Hibernate/Jakarta Persistence. Không yêu cầu ai cũng phải dùng static metamodel, nhưng trong codebase có nhiều dynamic queries nó giúp refactor an toàn hơn.

### 26.1. Static metamodel không đổi SQL semantics

Ngay cả với type-safe join:

```java
order.join(PurchaseOrder_.customer, JoinType.LEFT);
```

đặt predicate lên thuộc tính customer trong WHERE vẫn có thể loại hàng null. Type safety không bảo đảm đúng ý định nghiệp vụ.

## 27. Composition bằng `Specification` trong Spring Data JPA

Spring Data JPA có interface `Specification<T>` giúp đóng gói Criteria predicates thành những phần tái sử dụng:

```java
import org.springframework.data.jpa.domain.Specification;

public final class OrderSpecs {

    private OrderSpecs() {}

    public static Specification<PurchaseOrder> hasStatus(
            OrderStatus status) {

        return (root, query, cb) ->
            status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }

    public static Specification<PurchaseOrder> customerNamed(
            String name) {

        return (root, query, cb) -> {
            if (name == null || name.isBlank()) {
                return cb.conjunction();
            }

            Join<PurchaseOrder, Customer> customer =
                root.join("customer", JoinType.INNER);

            return cb.equal(customer.get("name"), name);
        };
    }

    public static Specification<PurchaseOrder> hasSku(
            String sku) {

        return (root, query, cb) -> {
            if (sku == null || sku.isBlank()) {
                return cb.conjunction();
            }

            Subquery<Integer> sq =
                query.subquery(Integer.class);
            Root<OrderLine> line =
                sq.from(OrderLine.class);

            sq.select(cb.literal(1))
              .where(
                  cb.equal(line.get("order"), root),
                  cb.equal(line.get("sku"), sku)
              );

            return cb.exists(sq);
        };
    }
}
```

Kết hợp:

```java
Specification<PurchaseOrder> spec =
    Specification.where(OrderSpecs.hasStatus(status))
        .and(OrderSpecs.customerNamed(customerName))
        .and(OrderSpecs.hasSku(sku));
```

**Cảnh báo phiên bản:** Một số API composition như `Specification.where(...)` đã thay đổi/deprecate qua các phiên bản Spring Data JPA. Với version hiện tại, có thể dùng `Specification.allOf(...)` hoặc cách composition được tài liệu version đó khuyến nghị.

Một ví dụ Spring Data JPA mới hơn:

```java
Specification<PurchaseOrder> spec =
    Specification.allOf(
        OrderSpecs.hasStatus(status),
        OrderSpecs.customerNamed(customerName),
        OrderSpecs.hasSku(sku)
    );
```

`Specification` thuộc Spring Data JPA, không phải phần của Jakarta Persistence chuẩn. Nó đóng gói Criteria predicate nhưng vẫn chịu mọi quy tắc JOIN, DISTINCT, fetch, count và SQL của JPA/Hibernate.

### 27.1. Chú ý count query của Spring Data

Khi gọi repository pagination, Spring Data có thể tạo query đếm riêng. Một `Specification` vừa thêm `root.fetch("lines")` vừa phục vụ count query có thể gây lỗi semantic:

```text
query count không select owner entity
nhưng lại fetch association của owner
```

Hướng tốt hơn:

- Để `Specification` chủ yếu mô tả **điều kiện lọc**.
- Tách fetch plan của data query bằng EntityGraph hoặc query riêng.
- Dùng count query riêng khi join collection làm trùng root rows.
- Kiểm tra API `findAll(spec, countSpec, pageable)` nếu phiên bản Spring Data JPA đang dùng hỗ trợ.
- Tránh cast `Fetch` sang `Join` trong Specification.

## 28. `Predicate` động, AND, OR và dấu ngoặc logic

Giả sử filter yêu cầu:

```text
status = PAID
AND
(
    customer.name = 'An'
    OR
    total >= 500
)
```

Criteria:

```java
Predicate paid =
    cb.equal(order.get("status"), OrderStatus.PAID);

Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.LEFT);

Predicate byCustomer =
    cb.equal(customer.get("name"), "An");

Predicate highTotal =
    cb.greaterThanOrEqualTo(
        order.<BigDecimal>get("total"),
        new BigDecimal("500.00")
    );

cq.where(
    cb.and(
        paid,
        cb.or(byCustomer, highTotal)
    )
);
```

Dùng cấu trúc `cb.and`/`cb.or` đúng nhóm, không giả định Java boolean operator precedence khi ghép các Predicate theo danh sách.

### 28.1. Null semantics trong OR

Với order không có customer:

```text
customer.name = 'An' → UNKNOWN
total >= 500        → TRUE hoặc FALSE
```

Nếu total trên 500, biểu thức OR có thể TRUE và order được giữ. Nếu total thấp hơn 500, UNKNOWN OR FALSE cho UNKNOWN, bị WHERE loại. Đây là semantics mong muốn nếu bộ lọc là “customer An hoặc total cao”.

Nếu business yêu cầu giữ mọi order không có customer, phải thêm điều kiện `isNull(customer)` rõ ràng, không chỉ dùng LEFT JOIN.

## 29. Sort theo thuộc tính association tùy chọn

Muốn sắp order theo tên khách hàng nhưng giữ order không customer:

```java
Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.LEFT);

cq.orderBy(
    cb.asc(customer.get("name")),
    cb.asc(order.get("id"))
);
```

LEFT JOIN giữ root. Tuy nhiên vị trí của `NULL` trong ORDER BY có thể khác nhau giữa DBMS/dialect.

Nếu UI cần null cuối cùng, có thể dùng `CASE`:

```java
Expression<Integer> nullRank =
    cb.<Integer>selectCase()
      .when(cb.isNull(customer.get("id")), 1)
      .otherwise(0);

cq.orderBy(
    cb.asc(nullRank),
    cb.asc(customer.get("name")),
    cb.asc(order.get("id"))
);
```

Điều này biểu đạt:

```text
Có customer → rank 0
Không customer → rank 1
```

Cột `id` là tie-breaker để pagination có thứ tự xác định, tránh bản ghi thay đổi vị trí giữa page do cùng tên.

## 30. DTO projection từ join và aggregate

Không phải truy vấn nào cũng cần entity graph managed.

Ví dụ màn hình tổng quan chỉ cần ID order, tên customer và tổng tiền:

```java
public record OrderRow(
    Long orderId,
    String customerName,
    BigDecimal total
) {}
```

Criteria constructor projection:

```java
CriteriaQuery<OrderRow> cq =
    cb.createQuery(OrderRow.class);

Root<PurchaseOrder> order =
    cq.from(PurchaseOrder.class);

Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.LEFT);

cq.select(
    cb.construct(
        OrderRow.class,
        order.get("id"),
        customer.get("name"),
        order.get("total")
    )
);
```

Nếu customer null, `customerName` có thể null trong record.

`cb.construct` yêu cầu constructor phù hợp với types và thứ tự các expressions. Với record, canonical constructor có thể được Hibernate gọi theo mapping tương ứng. Nếu kiểu DB/JPA của aggregate không khớp constructor, query có thể lỗi runtime.

### 30.1. Không fetch association trong DTO projection nếu không cần

Một query projection đã chọn cụ thể cột customer name:

```java
customer.get("name")
```

không cần `order.fetch("customer")`. Fetch join liên quan tới khởi tạo association của owner entity được trả về; DTO projection không sử dụng managed root entity theo cùng cách.

## 31. Grouping, HAVING và count line

Yêu cầu: lấy các order có từ hai lines trở lên.

Một cách dùng join + group:

```java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<PurchaseOrder> order =
    cq.from(PurchaseOrder.class);

Join<PurchaseOrder, OrderLine> line =
    order.join("lines", JoinType.INNER);

cq.multiselect(
      order.get("id").alias("orderId"),
      cb.count(line).alias("lineCount")
  )
  .groupBy(order.get("id"))
  .having(cb.ge(cb.count(line), 2L));
```

Kết quả với dữ liệu mẫu: order 10 (hai lines).

Nếu chỉ cần tìm root entity thỏa số lượng, correlated count subquery hoặc `cb.size(collection)` có thể gọn hơn, tránh `GROUP BY` toàn bộ các thuộc tính entity.

### 31.1. `HAVING` khác `WHERE`

- `WHERE` lọc individual joined rows trước grouping.
- `HAVING` lọc groups theo aggregate.

Ví dụ “order có ít nhất hai lines SKU-A” khác với “order có ít nhất hai lines bất kỳ và có một line SKU-A”. Phải đặt predicate SKU và aggregate count ở đúng nơi.

## 32. Security: tenant filter và dữ liệu người dùng

Dynamic query có thể chứa các bộ lọc tùy chọn, nhưng **tenant/security scope không được tùy chọn**.

```java
Predicate tenantScope =
    cb.equal(order.get("tenantId"), currentTenantId);

List<Predicate> predicates = new ArrayList<>();
predicates.add(tenantScope);
```

Nếu filter `status`, `sku`, `customerName` không được cung cấp, tenant scope vẫn phải áp dụng.

Một subquery trên `OrderLine` cũng cần bảo đảm rằng nó không vô tình truy cập dữ liệu cross-tenant theo một association/mapping không an toàn. Nếu `OrderLine` liên kết chặt tới order qua FK và tenant isolation được đảm bảo ở mapping/database, vẫn nên test boundary; trong hệ thống multi-tenant phức tạp có thể cần explicit tenant predicate trong subquery.

**Parameter binding** bảo vệ giá trị đầu vào, nhưng không tự thực hiện authorization. Một query đúng cú pháp vẫn có thể trả dữ liệu không được phép nếu thiếu predicate quyền truy cập.

### 32.1. Không dùng tên attribute do user gửi trực tiếp

Nếu một endpoint cho phép sort/filter tùy ý:

```java
order.get(requestedField)
```

mà `requestedField` đến trực tiếp từ client, có thể dẫn tới truy vấn không mong muốn, lỗi runtime hoặc lộ metadata.

Dùng whitelist:

```java
String sortProperty = switch (requestedSort) {
    case "date" -> "createdAt";
    case "total" -> "total";
    default -> "id";
};
```

Dù Criteria API không ghép SQL literal dễ dàng như chuỗi, nó không thay thế việc kiểm soát field mà user được phép query.

## 33. Performance: chọn JOIN hay EXISTS bằng query plan

Một query có thể được viết bằng nhiều dạng SQL. Hiệu năng phụ thuộc:

- Số lượng order và lines.
- Cardinality của association.
- Index trên `order_lines.order_id`, `sku`, status, date.
- Độ chọn lọc của predicates.
- Thống kê/cost model của database.
- SQL optimizer có biến `EXISTS` thành semi-join hay không.
- Số rows phải sort/deduplicate và fetch.
- Pagination và phương án kế hoạch truy vấn.

Chỉ số nên xem:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Số SQL statements | N+1 hoặc query lặp |
| Tổng SQL rows | Join to-many có nhân dữ liệu không |
| Execution plan | Index scan, nested-loop, hash/semi-join, sort |
| Actual row counts | Ước lượng optimizer có sát thực tế không |
| DB execution time | Cost truy vấn thật |
| JVM heap/GC | Fetch entity graph có tạo nhiều object không |
| Connection/transaction duration | Có giữ tài nguyên DB lâu không |

Ví dụ index PostgreSQL phù hợp với EXISTS SKU:

```sql
CREATE INDEX idx_order_lines_order_sku
ON order_lines (order_id, sku);
```

Với truy vấn chủ yếu lọc SKU trước rồi tìm owner, thứ tự cột `(sku, order_id)` có thể phù hợp hơn. Phải kiểm tra workload/query plan thực tế, không áp một index cứng cho mọi hệ thống.

### 33.1. Tránh dùng function trên cột lọc một cách vô ý

```java
cb.equal(cb.lower(customer.get("email")), normalizedEmail)
```

có thể làm index thường trên email kém hiệu quả. Cân nhắc normalized column, expression index, collation hoặc kiểu dữ liệu case-insensitive tùy DBMS.

## 34. Logging và đo SQL

Bật logging trong môi trường phát triển:

```properties
hibernate.show_sql=true
hibernate.format_sql=true
```

Với Spring Boot:

```properties
logging.level.org.hibernate.SQL=DEBUG
```

Có thể bật Hibernate Statistics:

```properties
hibernate.generate_statistics=true
```

Ví dụ:

```java
org.hibernate.SessionFactory sf =
    em.getEntityManagerFactory()
      .unwrap(org.hibernate.SessionFactory.class);

org.hibernate.stat.Statistics stats =
    sf.getStatistics();

System.out.println(stats.getPrepareStatementCount());
System.out.println(stats.getEntityFetchCount());
System.out.println(stats.getCollectionFetchCount());
```

Statistics ở phạm vi SessionFactory có thể bị ảnh hưởng bởi các test chạy song song. Nếu cần biết SQL cho một use case cụ thể, hãy cô lập test hoặc dùng `StatementInspector`/datasource proxy.

Không bật bind parameter logging ở production khi dữ liệu có thể chứa thông tin riêng tư, email, token hoặc số tiền nhạy cảm.

## 35. Integration test: JOIN, EXISTS và kết quả cụ thể

Một integration test đúng phải seed những trường hợp biên:

- Order có customer và không có customer.
- Customer match và không match điều kiện ON.
- Order không có line.
- Order có một line phù hợp.
- Order có nhiều line cùng phù hợp.
- Order có line bị cấm và line hợp lệ.
- Hai điều kiện lọc đòi hỏi hai line khác nhau.
- Nhiều order có cùng ngày/total để kiểm tra sort và pagination.

### 35.1. Test LEFT JOIN giữ order null

```java
@Test
void leftJoinRetainsOrdersWithoutCustomer() {
    try (EntityManager em = emf.createEntityManager()) {
        CriteriaBuilder cb = em.getCriteriaBuilder();

        CriteriaQuery<PurchaseOrder> cq =
            cb.createQuery(PurchaseOrder.class);
        Root<PurchaseOrder> order =
            cq.from(PurchaseOrder.class);

        order.join("customer", JoinType.LEFT);
        cq.select(order).orderBy(cb.asc(order.get("id")));

        List<Long> ids = em.createQuery(cq).getResultList()
            .stream()
            .map(PurchaseOrder::getId)
            .toList();

        assertEquals(List.of(10L, 11L, 12L, 13L), ids);
    }
}
```

Test body giả định `emf` đã được fixture tạo, database được seed đúng dữ liệu mẫu và các import JUnit/Jakarta đã có. Nếu test chỉ assert `size() == 4`, một tập kết quả sai tình cờ cũng có thể có bốn rows; so ID cụ thể đáng tin cậy hơn.

### 35.2. Test EXISTS tránh duplicate root

```java
@Test
void existsFindsOrdersContainingSku() {
    try (EntityManager em = emf.createEntityManager()) {
        CriteriaBuilder cb = em.getCriteriaBuilder();
        CriteriaQuery<PurchaseOrder> cq =
            cb.createQuery(PurchaseOrder.class);

        Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

        Subquery<Integer> sq = cq.subquery(Integer.class);
        Root<OrderLine> line = sq.from(OrderLine.class);

        sq.select(cb.literal(1)).where(
            cb.equal(line.get("order"), order),
            cb.equal(line.get("sku"), "SKU-A")
        );

        cq.select(order)
          .where(cb.exists(sq))
          .orderBy(cb.asc(order.get("id")));

        List<Long> ids = em.createQuery(cq).getResultList()
            .stream()
            .map(PurchaseOrder::getId)
            .toList();

        assertEquals(List.of(10L, 12L), ids);
    }
}
```

Nếu thêm một line SKU-A khác cho order 10, kết quả EXISTS vẫn chỉ có order 10 một lần. Đây là một kiểm thử quan trọng cho semantics semi-join.

### 35.3. Test NOT EXISTS tìm collection rỗng

```java
Subquery<Integer> sq = cq.subquery(Integer.class);
Root<OrderLine> line = sq.from(OrderLine.class);

sq.select(cb.literal(1))
  .where(cb.equal(line.get("order"), order));

cq.where(cb.not(cb.exists(sq)));
```

Kỳ vọng chỉ order 11.

### 35.4. Test ON khác WHERE

Với dữ liệu mẫu:

- `LEFT JOIN` + `ON customer.name = 'An'` giữ bốn order, customer alias của order 12 là null.
- `LEFT JOIN` + `WHERE customer.name = 'An'` chỉ giữ order 10.

Kiểm tra cả `orderId` và `customerId`/alias để không nhầm hai semantics.

## 36. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Order không customer biến mất | Dùng inner join hoặc điều hướng association ngầm | `JoinType.LEFT` khi cần giữ root |
| Đã dùng LEFT nhưng order null vẫn mất | Predicate phía phải nằm trong WHERE | Đưa điều kiện lọc join sang ON nếu đúng nghiệp vụ |
| `Root.fetch()` không `.get()` được | `Fetch` không phải `Path` | Dùng `Join` để lọc; fetch riêng/EntityGraph nếu cần |
| Cast Fetch sang Join hoạt động cục bộ nhưng lỗi provider khác | Dựa vào implementation | Tránh cast, tách fetch/filter rõ |
| Kết quả có order lặp | Join collection one-to-many | `distinct(true)` hoặc EXISTS |
| Count page lớn hơn số order thật | `count(root)` sau to-many join | `countDistinct(id)` hoặc count bằng EXISTS |
| Pagination collection fetch chậm | Nhân SQL rows/in-memory pagination | Tách page IDs rồi fetch, hoặc batch fetching |
| `exists` trả toàn bộ hoặc không row nào | Quên correlation tới outer root | `sub.correlate(root)` hoặc predicate `line.order = root` |
| `NOT IN` cho kết quả lạ | NULL trong tập con | Cân nhắc `NOT EXISTS` với correlation rõ |
| Chỉ một line phải thỏa hai filter độc lập | Tái sử dụng cùng Join khi nghiệp vụ cần hai child | Dùng hai EXISTS hoặc hai joins có semantics riêng |
| Subquery scalar type lỗi | `AVG`, `MAX`, cast và type inference không khớp | Kiểm tra Java/SQL type, dùng generic đúng |
| `Specification` chạy data query được nhưng count lỗi | Fetch join trong Specification | Tách fetch plan và count logic |
| Sort theo customer làm mất order null | Inner join khi sort | LEFT join và xử lý NULL order |
| SQL nhiều join trùng | Helper tạo lại join cùng path | Tái sử dụng join đã tạo, xem SQL |
| Truy vấn rất chậm dù Criteria ngắn | DB plan/index/cardinality không phù hợp | `EXPLAIN`, đo rows và indexes |
| Query trả dữ liệu tenant khác | Scope filter bị coi là optional | Thêm tenant/security predicate bắt buộc |
| Query chạy với H2 nhưng lỗi production DB | Dialect/isolation/SQL optimization khác | Integration test trên DBMS thật |

## 37. Quy trình thiết kế một Criteria query động

**Bước 1 — Chốt tập root cần trả.** Root là `PurchaseOrder` hay `OrderLine`? Nếu cần một hàng mỗi order, ưu tiên truy vấn bắt đầu từ order.

**Bước 2 — Phân loại điều kiện.** Điều kiện scalar trên root, điều kiện trên to-one, điều kiện tồn tại child, điều kiện aggregate hay điều kiện vắng mặt child?

**Bước 3 — Xác định join type.** Association optional có phải giữ root khi null không? Nếu có, dùng LEFT và kiểm tra vị trí ON/WHERE.

**Bước 4 — Tách join khỏi fetch.** Join để lọc/projection; fetch để khởi tạo association. Không ép `Fetch` sang `Join` vì tiện tay.

**Bước 5 — Kiểm tra nhân row.** Nếu join to-many, có cần `distinct(true)`, count distinct hoặc EXISTS?

**Bước 6 — Xây predicate động.** Chỉ thêm filter khi được cung cấp, nhưng luôn thêm tenant/security scope bắt buộc. Nhóm AND/OR chính xác.

**Bước 7 — Dùng EXISTS/NOT EXISTS cho điều kiện tồn tại.** Đảm bảo subquery correlate theo root; khi cần hai child khác nhau, dùng hai điều kiện tồn tại riêng.

**Bước 8 — Chọn fetch plan.** Nếu trả entity cần to-one, fetch join có thể hợp lý. Nếu collection lớn và có pagination, cân nhắc hai pha hoặc batch fetching.

**Bước 9 — Viết count query riêng.** Đừng tái sử dụng fetch joins trong count; nếu to-many join, đếm distinct root hoặc đổi điều kiện sang EXISTS.

**Bước 10 — Xác định thứ tự pagination.** Thêm tie-breaker unique, ví dụ `createdAt DESC, id DESC`; không phụ thuộc thứ tự tự nhiên của database.

**Bước 11 — Bind parameter và kiểm soát field.** Không ghép raw user input thành tên property/query string; dùng whitelist và validation.

**Bước 12 — Kiểm thử và đo.** Seed optional/null, empty collections, duplicate children, filters chồng nhau, nhiều tenant, pagination và dữ liệu lớn. Xem generated SQL cùng `EXPLAIN`.

## 38. Bài tập tình huống

### Bài 1 — Inner hay left?

Một order có `customer = null`. Query:

```java
order.join("customer");
```

có giữ order đó không?

**Đáp án:** Không. Overload không nêu `JoinType` mặc định INNER, nên order không có customer match bị loại.

### Bài 2 — LEFT join và WHERE

```java
Join<PurchaseOrder, Customer> c =
    order.join("customer", JoinType.LEFT);

cq.where(cb.equal(c.get("name"), "An"));
```

Order không customer có xuất hiện không?

**Đáp án:** Không. WHERE loại các rows có `c.name` null.

### Bài 3 — ON

Muốn lấy mọi order nhưng chỉ nối customer nếu tên “An”. Viết thế nào?

**Đáp án:**

```java
Join<PurchaseOrder, Customer> c =
    order.join("customer", JoinType.LEFT);
c.on(cb.equal(c.get("name"), "An"));
```

Chọn projection `(order, c)` để quan sát alias customer có thể null.

### Bài 4 — Join hay fetch?

Muốn lọc theo email customer: dùng `join` hay `fetch`?

**Đáp án:** Dùng `join` để lấy `customer.get("email")` tạo predicate. Chỉ dùng fetch nếu kết quả entity cần association được khởi tạo.

### Bài 5 — Vì sao `Fetch` không có `.get()`?

**Đáp án:** `Fetch` mô tả fetch plan, không phải subtype `Path`. Không cast sang `Join` theo implementation; dùng `root.join(...)` hoặc EntityGraph/fetch riêng.

### Bài 6 — Duplicate root

Một order có ba line cùng SKU-A. `join("lines")` kết hợp `where sku = 'SKU-A'` có thể tạo mấy SQL rows cho order đó?

**Đáp án:** Ba. Nếu chỉ cần order duy nhất, dùng `distinct(true)` hoặc correlated EXISTS.

### Bài 7 — NOT EXISTS

Muốn tìm order không có bất kỳ line nào. Viết điều kiện?

**Đáp án:** Correlated subquery trên `OrderLine` với `line.order = order`, rồi `cb.not(cb.exists(sub))`.

### Bài 8 — Hai SKU độc lập

Muốn order có cả SKU-A và SKU-B trên **hai line có thể khác nhau**. Có dùng một join và AND hai equality được không?

**Đáp án:** Không. Một line không thể có hai SKU khác nhau. Dùng hai EXISTS subqueries hoặc cấu trúc joins riêng có semantics tương ứng.

### Bài 9 — Count pagination

Dùng join lines, một order có năm lines. `cb.count(order)` đếm được bao nhiêu contribution cho order đó?

**Đáp án:** Có thể năm SQL joined rows. Dùng `cb.countDistinct(order.get("id"))` hoặc count bằng EXISTS nếu mục tiêu là số order.

### Bài 10 — Specification fetch

`Specification` gọi `root.fetch("lines")`, sau đó Spring Data chạy count query và báo lỗi. Nguyên nhân?

**Đáp án:** Fetch join yêu cầu owner entity trong selection, nhưng count query không select owner. Tách fetch plan và count predicate.

### Bài 11 — Page IDs

Tại sao tách query trang ID rồi query fetch collections?

**Đáp án:** Pagination được thực hiện ở mức root rows trước, tránh collection fetch join nhân SQL rows làm lệch page hoặc buộc Hibernate phân trang trong memory.

### Bài 12 — Security

Filter của user trống, builder dùng `cb.conjunction()` và trả tất cả orders mọi tenant. Sai ở đâu?

**Đáp án:** Tenant/security predicate bắt buộc đã bị bỏ qua. Dynamic filters có thể trống, nhưng scope truy cập dữ liệu không được trống.

### Bài 13 — Correlation

Subquery EXISTS không tham chiếu outer order. Điều gì xảy ra?

**Đáp án:** Nó có thể trả cùng một điều kiện “có bất kỳ line nào trong hệ thống” cho mọi root, thay vì kiểm tra line của từng order.

### Bài 14 — Null sort

Muốn sort theo customer name và giữ order không có customer. Dùng loại join nào?

**Đáp án:** LEFT JOIN, sau đó xác định NULL ordering/tie-breaker theo yêu cầu.

### Bài 15 — Count hay EXISTS?

Chỉ cần biết một order có ít nhất một line quantity trên 10. Nên ưu tiên cách biểu đạt nào?

**Đáp án:** EXISTS với correlated predicate `line.quantity > 10`; nó nêu đúng ý định boolean và không cần nhân root rows.

## 39. Tài liệu tham khảo chính thức

- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): Criteria API, joins, subqueries, outer join semantics, entity graphs, grouping và query execution.
- [Jakarta Persistence 3.2 — `CriteriaBuilder`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/criteria/CriteriaBuilder.html): tạo predicates, `exists`, `countDistinct`, `isEmpty`, `like`, `construct`.
- [Jakarta Persistence 3.2 — `CriteriaQuery`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/criteria/CriteriaQuery.html): `select`, `multiselect`, `where`, `groupBy`, `having`, `distinct`, `orderBy`.
- [Jakarta Persistence 3.2 — `From`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/criteria/From.html): tạo root joins và typed joins.
- [Jakarta Persistence 3.2 — `Join`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/criteria/Join.html): `on` và join type.
- [Jakarta Persistence 3.2 — `Fetch`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/criteria/Fetch.html): fetch association, khác `Join`.
- [Jakarta Persistence 3.2 — `Subquery`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/criteria/Subquery.html): correlated roots/joins và query con.
- [Hibernate ORM User Guide — Criteria](https://docs.hibernate.org/stable/orm/userguide/html_single/#criteria): ví dụ Hibernate Criteria, typed queries, joins, subqueries và query semantics.
- [Hibernate ORM User Guide — Fetching](https://docs.hibernate.org/stable/orm/userguide/html_single/#fetching): N+1, join fetching, batch fetching và collection loading.
- [Hibernate ORM HQL Reference — Subqueries](https://docs.hibernate.org/stable/orm/querylanguage/html_single/#hql-subqueries): EXISTS, correlated subquery, lateral và derived-table features của HQL.
- [Spring Data JPA Reference — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html): `Specification`, composition, Criteria và repository queries.
- [PostgreSQL Documentation — Subquery Expressions](https://www.postgresql.org/docs/current/functions-subquery.html): `EXISTS`, `IN`, `NOT IN`, `ANY`, `ALL` và null semantics.

**Phạm vi phiên bản:** Ví dụ dùng `jakarta.persistence.criteria.*` và Hibernate/JPA hiện đại. Một số API mở rộng như HQL lateral joins, derived roots, `Specification` composition overloads hoặc SQL rendering của `JOIN FETCH` phụ thuộc phiên bản Hibernate/Spring Data/DBMS. Hãy đối chiếu đúng stack và generated SQL của dự án.

## Kết luận

**Join, fetch, subquery và `EXISTS` giải quyết những câu hỏi khác nhau** trong Criteria API. `Join` nối association để lọc/chọn dữ liệu; `Fetch` quy định association nào cần được tải cùng entity; subquery biểu đạt một truy vấn lồng; `EXISTS`/`NOT EXISTS` biểu đạt điều kiện có hoặc không có hàng con phù hợp mà không buộc nhân root result.

Khi association tùy chọn, chọn INNER hay LEFT theo việc cần giữ root, và nhớ rằng predicate ở WHERE có thể loại hàng null dù đã LEFT JOIN. Khi join to-many, chú ý duplicate roots/count; khi fetch collection, tránh pagination trực tiếp không kiểm soát. Với filter động, chỉ tạo join/predicate cần thiết, tái sử dụng join đúng semantics, luôn giữ tenant/security scope và phân biệt điều kiện trên **cùng một child** với điều kiện trên **những child khác nhau**.

Trong ứng dụng thực, cách viết Criteria tốt không phải cách có ít dòng Java nhất, mà là cách biểu đạt đúng invariant và tập kết quả, tạo SQL có thể đo/giải thích, và có integration tests kiểm chứng null associations, empty collections, tương quan subquery, số lượng root, thứ tự phân trang và hiệu năng.

# Phân biệt tối ưu khả chuyển và tối ưu phụ thuộc provider trong JPA

Ứng dụng dùng **Jakarta Persistence (JPA)** thường bắt đầu với những API tiêu chuẩn như `EntityManager`, JPQL, Criteria API, `@Entity` và `@ManyToOne`. Khi dữ liệu tăng lên, nhóm phát triển cần tối ưu số câu SQL, thời gian đọc/ghi, lượng entity được nạp, bộ nhớ và khả năng mở rộng. Lúc đó xuất hiện một lựa chọn kiến trúc quan trọng:

- **Tối ưu khả chuyển** (*portable optimization*): tận dụng tính năng trong đặc tả Jakarta Persistence/JPA, thiết kế query và cấu trúc xử lý mà nhiều provider có thể thực hiện theo cùng một hợp đồng chức năng.
- **Tối ưu phụ thuộc provider** (*provider-specific optimization*): dùng API, annotation, query hint, configuration hoặc extension riêng của Hibernate, EclipseLink hay một JPA provider khác để khai thác khả năng triển khai cụ thể.

Ví dụ, JPQL constructor projection là một kỹ thuật JPA tiêu chuẩn:

```java
List<OrderSummary> summaries = em.createQuery(
    """
    SELECT new com.example.shop.dto.OrderSummary(
        o.id, o.reference, c.name
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.status = :status
    ORDER BY o.id
    """,
    OrderSummary.class
)
.setParameter("status", OrderStatus.SUBMITTED)
.setMaxResults(50)
.getResultList();
```

Ngược lại, cấu hình:

```properties
hibernate.default_batch_fetch_size=32
hibernate.jdbc.batch_size=50
```

là hai ví dụ **tối ưu riêng của Hibernate**, không phải thuộc tính tiêu chuẩn của Jakarta Persistence. Chúng có thể mang lại hiệu năng đáng kể, nhưng cách hoạt động, mức hỗ trợ và tên cấu hình gắn với provider/version.

> **Nguyên tắc chính:** Ưu tiên **API chuẩn và thiết kế dữ liệu hợp lý** khi chúng đáp ứng mục tiêu. Dùng extension riêng khi có **bằng chứng đo lường** cho thấy lợi ích thực tế lớn hơn chi phí phụ thuộc, có phạm vi sử dụng rõ ràng và có phương án kiểm thử khi nâng cấp provider.

Không nên diễn giải “khả chuyển” thành “SQL giống nhau hoặc tốc độ giống nhau trên mọi database”. JPA chuẩn hóa một phần **hợp đồng lập trình và ngữ nghĩa**; SQL được sinh, execution plan, batching, caching và giới hạn của từng database vẫn có thể khác nhau. Một kỹ thuật JPA hoàn toàn chuẩn vẫn cần kiểm thử trên provider và DBMS thật.

Bài học thuộc chương **Hiệu năng** của module **Data Persistence Relational Access ORM JPA**. Nội dung giải thích các mức độ phụ thuộc, kỹ thuật tối ưu chuẩn, extension thường gặp, trade-off và các ví dụ đo lường, kiểm thử, tổ chức mã nguồn để có thể thay provider, và nguyên tắc ra quyết định trong dự án thực tế.

---

## 1. Trước hết: “khả chuyển” nghĩa là gì?

Tính khả chuyển có nhiều mức, không phải một biến đúng/sai duy nhất.

| Mức độ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **API JPA chuẩn** | Source dựa trên hợp đồng Jakarta Persistence | `EntityManager`, JPQL, Criteria API |
| **Metadata chuẩn** | Dùng annotation/XML theo đặc tả | `@Entity`, `@JoinColumn`, `orm.xml` |
| **JDBC chuẩn** | Dùng API JDBC chung | `PreparedStatement`, `setFetchSize` |
| **SQL tương đối phổ biến** | SQL có thể chạy trên nhiều DBMS với ít khác biệt | SELECT/JOIN/GROUP BY cơ bản |
| **Provider extension** | Phụ thuộc Hibernate/EclipseLink/... | Hibernate `@BatchSize` |
| **Database-specific** | Phụ thuộc PostgreSQL/Oracle/MySQL/... | PostgreSQL `jsonb`, `DISTINCT ON` |
| **Hạ tầng-specific** | Phụ thuộc driver/pool/runtime/cloud | Driver cursor settings, pool behaviors |

### 1.1. API chuẩn không bảo đảm tối ưu tương đương

Hai JPA providers có thể thực thi:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
```

theo các cách khác nhau về SQL aliases, select columns, hydration, cache và statement preparation. Query vẫn dùng **ngôn ngữ chuẩn** dù kết quả hiệu năng không giống nhau.

### 1.2. Một optimization có thể vừa chuẩn vừa kém portable về hiệu năng

`setFirstResult(1000)` và `setMaxResults(50)` là API chuẩn. Nhưng DBMS có thể sử dụng các dạng SQL pagination khác nhau, và truy vấn ở offset sâu có thể chậm trên nhiều hệ quản trị.

Do đó phải phân biệt:

- **Source portability**: code biên dịch/chạy với các provider theo chuẩn.
- **Semantic portability**: cùng kết quả đúng về dữ liệu và transaction trong phạm vi đặc tả.
- **Performance portability**: hiệu năng tương đương khi đổi provider/DBMS — **không được bảo đảm**.

### 1.3. Vendor lock-in không chỉ đến từ annotation

Một ứng dụng không dùng bất kỳ `org.hibernate.*` nào vẫn có thể phụ thuộc vào PostgreSQL vì native SQL, column types, indexes, stored procedures hoặc database locking.

Ngược lại, một cấu hình Hibernate riêng được cô lập ở một module nhỏ có thể là phụ thuộc quản lý được và đem lại lợi ích đáng kể.

### 1.4. Mục tiêu đúng: phụ thuộc có chủ đích

Không nhất thiết phải loại bỏ mọi phụ thuộc. Quan trọng là biết **phụ thuộc ở đâu, để làm gì, được đo thế nào và chi phí khi thay đổi là bao nhiêu**.

## 2. Một ma trận lựa chọn nhanh

| Nhu cầu | Hướng khả chuyển nên thử trước | Hướng riêng có thể cân nhắc |
| --- | --- | --- |
| Danh sách chỉ cần vài cột | JPQL/Criteria DTO projection | Native SQL/projection tối ưu riêng DB |
| N+1 khi đọc to-one | `JOIN FETCH` hoặc `EntityGraph` | Hibernate `@BatchSize`, batch fetch tuning |
| N+1 khi đọc to-many | Query riêng có chủ đích, fetch plan phù hợp | Hibernate `@Fetch(SUBSELECT)`/batch fetching |
| Phân trang | `setFirstResult`, `setMaxResults` | Keyset/scroll API riêng hoặc SQL đặc thù |
| Ghi hàng loạt | Chunking, transaction, JPQL bulk DML | Hibernate JDBC batch settings, `StatelessSession` |
| Read-only màn hình báo cáo | Scalar/constructor projection | Hibernate query read-only settings |
| Giảm entity materialization | DTO projection | Provider-specific read-only/stream APIs |
| Kiểm soát graph tải | `JOIN FETCH`, `EntityGraph` | Provider-specific fetch profiles |
| Cache entity | `@Cacheable`, `Cache`, cache modes | Hibernate/EclipseLink cache regions, query cache |
| Query timeout | `jakarta.persistence.query.timeout` | Driver/vendor timeout tuning |
| Đo số entity được nạp | Đo application-level + JDBC | Hibernate Statistics |
| Tối ưu SQL plan | Thêm điều kiện, projection, indexing qua migration | DB hints, specialized indexes, optimizer extensions |

Bảng không quy định tối ưu riêng luôn là “bước cuối cùng”. Với ứng dụng chạy cố định Hibernate và PostgreSQL, một kỹ thuật provider-specific có thể là lựa chọn thực dụng ngay từ đầu **nếu đã có nhu cầu và bằng chứng rõ ràng**.

## 3. Mô hình dữ liệu ví dụ

Ta dùng hệ thống bán hàng:

```text
Customer
  id, name
    |
    | 1
    v
PurchaseOrder
  id, reference, status, createdAt
    |
    | 1
    v
OrderLine (*)
  id, quantity, unitPrice
    |
    v
Product
  id, sku, name
```

### 3.1. Entity minh họa

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String reference;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    public Long getId() { return id; }
    public String getReference() { return reference; }
    public OrderStatus getStatus() { return status; }
    public Customer getCustomer() { return customer; }
    public List<OrderLine> getLines() { return lines; }
}
```

Các classes `Customer`, `OrderLine` và `OrderStatus` được giả định có mapping và members phù hợp; ví dụ tập trung vào query và optimization, không phải một project đầy đủ.

### 3.2. Yêu cầu nghiệp vụ

Endpoint:

```text
GET /orders?status=SUBMITTED&limit=50
```

cần:

- ID và mã đơn.
- Tên Customer.
- Trạng thái.
- Không cần mọi dòng hàng hoặc toàn bộ graph.
- Trả tối đa 50 kết quả với thứ tự ổn định.

Đây là bài toán điển hình mà **giảm lượng dữ liệu được tải** thường quan trọng hơn “bật mọi cache” ngay từ đầu.

## 4. Bước tối ưu khả chuyển đầu tiên: lấy đúng dữ liệu cần thiết

Một triển khai chưa tối ưu:

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.status = :status
    ORDER BY o.id
    """,
    PurchaseOrder.class
)
.setParameter("status", OrderStatus.SUBMITTED)
.setMaxResults(50)
.getResultList();

List<OrderSummary> result = orders.stream()
    .map(o -> new OrderSummary(
        o.getId(),
        o.getReference(),
        o.getCustomer().getName()
    ))
    .toList();
```

Nếu `customer` LAZY và chưa được load, vòng `map` có thể phát sinh secondary selects.

### 4.1. JPQL DTO projection

```java
public record OrderSummary(
    Long id,
    String reference,
    String customerName
) {}
```

Query:

```java
List<OrderSummary> result = em.createQuery(
    """
    SELECT new com.example.shop.dto.OrderSummary(
        o.id, o.reference, c.name
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.status = :status
    ORDER BY o.id
    """,
    OrderSummary.class
)
.setParameter("status", OrderStatus.SUBMITTED)
.setMaxResults(50)
.getResultList();
```

**Ưu điểm:**

- Dùng JPQL constructor expression theo JPA.
- Chỉ chọn fields cần thiết.
- Không phải materialize toàn bộ `PurchaseOrder` và `Customer` thành managed entities chỉ để render danh sách.
- Không tạo đường truy cập LAZY ngoài ý muốn trong bước DTO mapping.
- Dễ định nghĩa số lượng kết quả và output contract.

### 4.2. Những giới hạn của projection

- DTO constructor phải tương thích kiểu/thứ tự dữ liệu được chọn.
- Query và DTO phải được cập nhật cùng nhau.
- Không có dirty checking với DTO như với entity managed.
- Một query phức tạp vẫn có thể chậm dù dùng projection.
- JPQL constructor expression có syntax chuẩn, nhưng SQL thực tế và query plan do provider/DBMS quyết định.

### 4.3. Khi nào nên giữ entity query?

Khi use case cần thay đổi entity trong transaction, lock/version, cascade hoặc domain behavior dựa trên managed state, entity loading có thể đúng hơn DTO projection.

**Không thay entity query bằng DTO một cách cơ học nếu làm mất lifecycle semantics cần thiết.**

## 5. Dùng Criteria API như một lựa chọn chuẩn

Nếu bộ lọc thay đổi động, Criteria API là phần của Jakarta Persistence.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<OrderSummary> cq =
    cb.createQuery(OrderSummary.class);

Root<PurchaseOrder> order =
    cq.from(PurchaseOrder.class);

Join<PurchaseOrder, Customer> customer =
    order.join("customer");

cq.select(cb.construct(
    OrderSummary.class,
    order.get("id"),
    order.get("reference"),
    customer.get("name")
));

cq.where(cb.equal(
    order.get("status"),
    OrderStatus.SUBMITTED
));

cq.orderBy(cb.asc(order.get("id")));

List<OrderSummary> result = em.createQuery(cq)
    .setMaxResults(50)
    .getResultList();
```

Imports JPA tương ứng gồm `jakarta.persistence.criteria.*`.

### 5.1. Tính khả chuyển ở đâu?

- Builder API, Criteria expressions, joins và typed queries thuộc chuẩn JPA.
- Không gắn code với một query implementation cụ thể của Hibernate.

### 5.2. Criteria không mặc nhiên nhanh hơn JPQL

Cùng một query logic có thể tạo SQL tương tự. Lợi ích chính của Criteria thường nằm ở **composability**, type model và khả năng xây điều kiện động.

Không chuyển JPQL sang Criteria chỉ để “tối ưu CPU” khi chưa có số đo.

### 5.3. Static metamodel

`PurchaseOrder_.status` có thể giúp giảm rủi ro string field names nếu project hỗ trợ generated static metamodel. Việc sinh metamodel là một vấn đề tooling riêng; không tự biến query chạy nhanh hơn.

## 6. JOIN FETCH: tối ưu chuẩn để kiểm soát N+1

Nếu cần trả các entity và truy cập Customer, `JOIN FETCH` là cú pháp JPQL chuẩn:

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    JOIN FETCH o.customer
    WHERE o.status = :status
    ORDER BY o.id
    """,
    PurchaseOrder.class
)
.setParameter("status", OrderStatus.SUBMITTED)
.setMaxResults(50)
.getResultList();
```

### 6.1. Ý nghĩa

JPA được yêu cầu fetch quan hệ `customer` cùng query theo fetch join semantics, nhằm tránh secondary selects cho association đó trong tình huống phù hợp.

### 6.2. Những gì chuẩn không bảo đảm

- SQL text giống nhau giữa Hibernate và EclipseLink.
- Execution plan giống nhau giữa PostgreSQL và Oracle.
- Mọi quan hệ khác cũng được fetch.
- Query sẽ nhanh hơn DTO projection.
- To-many fetch join luôn kết hợp đúng với pagination.
- Cache, flush hoặc lock behaviors hoàn toàn giống ở mọi provider.

### 6.3. Giới hạn đáng chú ý của fetch join

Với JPQL chuẩn, phía được fetch trong `JOIN FETCH` không được khai báo identification variable theo cách dùng alias tự do như ordinary join để lọc chính association đó.

Khi cần lọc dựa trên association, có thể dùng một join thông thường riêng hoặc thiết kế query khác theo semantics cho phép; tránh phụ thuộc cú pháp mở rộng của provider rồi gọi đó là JPQL chuẩn.

### 6.4. LEFT JOIN FETCH

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.customer
WHERE o.status = :status
```

Có ích khi association optional và cần giữ root rows không có association. Với `optional=false`, inner join thường phù hợp theo model.

## 7. EntityGraph: tối ưu fetch plan không sửa mapping toàn cục

`EntityGraph` là API chuẩn Jakarta Persistence. Nó giúp mô tả attributes cần fetch theo use case.

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.status = :status
    ORDER BY o.id
    """,
    PurchaseOrder.class
)
.setParameter("status", OrderStatus.SUBMITTED)
.setHint("jakarta.persistence.fetchgraph", graph)
.setMaxResults(50)
.getResultList();
```

### 7.1. Lợi ích portability

- `EntityGraph` và `jakarta.persistence.fetchgraph` là cơ chế chuẩn.
- Có thể giữ `@ManyToOne(fetch=LAZY)` trong mapping và chọn eager graph ở endpoint cần sử dụng.
- Không buộc mọi use case luôn tải Customer.

### 7.2. fetchgraph và loadgraph

Hai hints chuẩn:

- `jakarta.persistence.fetchgraph`: các attributes được chỉ định được xem là eager; những attributes không chỉ định được xem là lazy theo ngữ nghĩa fetch graph, với những quyền linh hoạt cho provider phù hợp đặc tả.
- `jakarta.persistence.loadgraph`: attributes trong graph được xem là eager; những attributes khác dùng fetch type quy định trong mapping.

Trong thực tế, provider **có thể fetch thêm state** ngoài graph. Không coi graph là cam kết SQL shape chính xác hoặc cam kết chỉ có một query.

### 7.3. NamedEntityGraph

Có thể định nghĩa:

```java
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomer",
    attributeNodes = @NamedAttributeNode("customer")
)
@Entity
public class PurchaseOrder {
    // ...
}
```

Sử dụng:

```java
EntityGraph<?> graph =
    em.getEntityGraph("PurchaseOrder.withCustomer");
```

Cấu hình này mang tính JPA chuẩn. Cần tránh đặt tên graph không rõ phạm vi hoặc gắn quá nhiều attributes gây over-fetching.

### 7.4. Khi nào EntityGraph không đủ?

Nếu query cần nhiều to-many collections, cách provider thực thi fetch graph vẫn có thể phát sinh nhiều selects hoặc row multiplication. Có thể cần chia queries/projection thay vì ép graph ngày càng lớn.

## 8. Phân trang là tối ưu khả chuyển, nhưng không giải quyết mọi thứ

JPA chuẩn hóa:

```java
query.setFirstResult(offset);
query.setMaxResults(pageSize);
```

Ví dụ:

```java
List<PurchaseOrder> page = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    ORDER BY o.id
    """,
    PurchaseOrder.class
)
.setFirstResult(100)
.setMaxResults(50)
.getResultList();
```

### 8.1. Lợi ích

Không nạp hàng chục nghìn entities rồi chia trang trong Java.

### 8.2. Offset sâu vẫn có thể chậm

`setFirstResult(100000)` có thể khiến database phải xét/bỏ qua nhiều rows trước khi trả 50 rows. Ngôn ngữ JPA chuẩn vẫn không xóa chi phí offset pagination.

### 8.3. Keyset pagination

Một hướng khả chuyển về ý tưởng là dùng điều kiện trên sort key:

```java
List<PurchaseOrder> nextPage = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.id > :lastSeenId
    ORDER BY o.id
    """,
    PurchaseOrder.class
)
.setParameter("lastSeenId", lastSeenId)
.setMaxResults(50)
.getResultList();
```

Đây là một JPQL query chuẩn cho trường hợp sort theo một key thích hợp. Với composite sort keys hoặc nullable fields, predicate cursor phải được thiết kế đúng semantics.

Một số providers có scrolling/keyset APIs riêng giúp triển khai trường hợp phức tạp; lúc đó phần tối ưu đi từ **ý tưởng query portable** sang **API provider-specific**.

### 8.4. Fetch join collection với pagination

```jpql
SELECT o FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
ORDER BY o.id
```

kết hợp `setMaxResults(50)` dễ gây duplicate rows, pagination sai hoặc in-memory pagination tùy provider.

Lối đi thường an toàn hơn:

1. Page root IDs.
2. Query chi tiết cho những IDs đó.
3. Gắn kết kết quả theo thứ tự page.
4. Đo SQL count, rows và entity loads.

Đây là chiến lược tổ chức query khả chuyển, không cần dựa vào một flag Hibernate để sửa một query đã có cấu trúc không phù hợp.

## 9. Điều chỉnh truy vấn JPQL cũng là tối ưu khả chuyển

Nhiều cải tiến quan trọng không cần provider extension:

- Tránh chọn entities khi chỉ cần scalar/DTO.
- Đưa bộ lọc vào database thay vì filter danh sách lớn trong Java.
- Dùng `JOIN` khi cần dữ liệu liên quan, thay vì truy cập LAZY trong vòng lặp.
- Dùng `COUNT` ở DB thay vì lấy mọi row rồi gọi `size()`.
- Dùng `EXISTS` khi chỉ cần biết có bản ghi thỏa điều kiện.
- Chọn sort có index phù hợp.
- Giới hạn số rows bằng pagination.
- Tách truy vấn một-nhiều theo workload có chủ đích.
- Dùng update/delete bulk khi semantics cho phép.

### 9.1. Ví dụ kiểm tra tồn tại bằng EXISTS

Thay vì tải toàn bộ lines:

```java
List<OrderLine> lines = ...;
boolean hasLines = !lines.isEmpty();
```

Có thể dùng JPQL:

```jpql
SELECT COUNT(l)
FROM OrderLine l
WHERE l.order.id = :orderId
```

và kiểm tra count > 0, hoặc một JPQL predicate `EXISTS` trong query phù hợp.

Về mặt SQL plan, `EXISTS` có thể hiệu quả khi database có thể dừng ở row đầu tiên, nhưng phải đo trên DBMS/indices thật. Không có công thức “EXISTS luôn nhanh hơn COUNT” cho mọi query shape.

### 9.2. Ưu tiên đúng kết quả trước

Khi đổi query, phải kiểm tra:

- Phạm vi tenant và authorization.
- Điều kiện trạng thái.
- Độ duy nhất của kết quả.
- Sort ổn định.
- Null semantics.
- Pagination correctness.
- Transaction snapshot/isolation phù hợp.

Một query nhanh nhưng làm thiếu điều kiện truy cập không phải tối ưu thành công.

## 10. JPQL bulk DML: chuẩn và nhanh, nhưng đổi semantics

JPA chuẩn hỗ trợ bulk UPDATE/DELETE:

```java
int changed = em.createQuery(
    """
    UPDATE Product p
    SET p.active = false
    WHERE p.discontinued = true
    """
).executeUpdate();
```

### 10.1. Vì sao nó có thể nhanh?

Thay vì:

```text
Load 50,000 Products
    -> change each managed entity
    -> dirty checking
    -> many UPDATE operations
```

một JPQL bulk update có thể chuyển thành một hoặc ít DML operations tại database.

### 10.2. Vì sao không thể thay thế mặc định?

Bulk JPQL DML:

- Không thực hiện vòng đời update của **từng managed entity** giống dirty checking.
- Không kích hoạt entity callbacks của từng row bị cập nhật theo cách `@PreUpdate` thông thường.
- Không tự đồng bộ state của các managed entities đã có trong persistence context.
- Không bảo đảm optimistic version tăng giống managed update theo mặc định.
- Có thể ảnh hưởng cache consistency cần xem theo provider.
- Không hỗ trợ JPQL UPDATE/DELETE joins theo cùng cách select tùy đặc tả; có thể cần subquery hoặc cách khác.

### 10.3. Mẫu flush, bulk, clear

```java
em.flush();

int updated = em.createQuery(
    """
    UPDATE Product p
    SET p.active = false
    WHERE p.discontinued = true
    """
).executeUpdate();

em.clear();
```

Mẫu này minh họa một chiến lược khi **đã chủ động chấp nhận detach toàn bộ managed entities** sau bulk DML. Không gọi `clear()` tùy tiện nếu transaction còn pending changes khác chưa được flush hoặc caller cần tiếp tục dùng managed instances.

### 10.4. Portability ở API, không ở mọi tương tác

Cú pháp JPQL bulk DML là chuẩn JPA. Nhưng SQL được sinh, row counts, locks, triggers và caching vẫn chịu DB/provider semantics. Nên coi đây là **tối ưu có thay đổi lifecycle contract**, không chỉ tối ưu số SQL.

## 11. Chunking, flush và clear: tối ưu phần lớn qua API chuẩn

Với batch import, có thể dùng `EntityManager.persist`, `flush` và `clear` của JPA.

```java
int chunkSize = 100;
int index = 0;

for (ImportRow row : rows) {
    Product product = toProduct(row);
    em.persist(product);

    if (++index % chunkSize == 0) {
        em.flush();
        em.clear();
    }
}

em.flush();
em.clear();
```

### 11.1. Tại sao giúp?

Một persistence context lưu rất nhiều managed entities có thể tăng:

- Memory.
- Dirty checking overhead.
- Flush time.
- GC pressure.

Chunking giúp giới hạn số managed entities được giữ đồng thời, tùy mô hình transaction và công việc.

### 11.2. Nó không tự bật JDBC batching

`flush()/clear()` là API chuẩn nhưng **không tự bảo đảm provider gom 100 INSERTs thành một JDBC batch**.

Đây chính là ranh giới quan trọng:

```text
Portable EntityManager chunking
                 |
                 v
Provider-specific JDBC batching settings
                 |
                 v
Driver + database batch execution
```

### 11.3. Cẩn thận với @GeneratedValue(strategy=IDENTITY)

Với Hibernate, `IDENTITY` thường làm khó hoặc hạn chế batching insert vì provider cần ID sau mỗi insert. Những tối ưu batching cần xét ID strategy; không chỉ tăng `hibernate.jdbc.batch_size` rồi kỳ vọng mọi INSERT đều được batch.

### 11.4. Clear làm detach các entities

Sau `em.clear()`, những instances đang giữ không còn managed. Không tiếp tục sửa chúng rồi kỳ vọng dirty checking tự flush. Cần merge/reload hoặc thiết kế loop không cần sửa lại entity cũ.

### 11.5. Transaction boundary là vấn đề khác

Chunking persistence context không tự chia một transaction lớn thành nhiều commit. Nếu nghiệp vụ yêu cầu commit theo chunks, application service phải thiết kế transaction boundaries, error recovery và idempotency riêng.

## 12. Hibernate JDBC batching: một ví dụ provider-specific rõ ràng

Hibernate cung cấp những properties ví dụ:

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
```

Trong một ứng dụng Spring Boot dùng Hibernate có thể đi qua:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

Đây là **Hibernate configuration**, không phải property tiêu chuẩn của Jakarta Persistence.

### 12.1. Tác dụng tổng quát

- `hibernate.jdbc.batch_size`: kích thước JDBC batch tối đa theo provider.
- `hibernate.order_inserts`: có thể sắp xếp INSERTs giúp batching hiệu quả hơn.
- `hibernate.order_updates`: có thể sắp xếp UPDATEs để batching hiệu quả hơn và hỗ trợ ổn định thứ tự lock trong một số tình huống.

### 12.2. Không đồng nghĩa “50 rows trong một SQL”

JDBC batching có thể gửi nhiều statement executions theo batch protocol, không nhất thiết chuyển thành một `INSERT ... VALUES (...), (...)` SQL text.

Cần phân biệt:

- JDBC batch invocations.
- Số DML entries.
- Số round-trips.
- Số rows affected.
- Tổng latency.

### 12.3. Mặt trái và giới hạn

- Tăng kích thước batch có thể tăng memory/driver buffers.
- Có thể đổi thứ tự SQL và behavior liên quan constraints/triggers.
- Lỗi giữa batch cần rollback/error handling cẩn trọng.
- Một số DML không batch được vì ID generation hoặc driver limitations.
- Một số version/settings có thể tương tác khác với optimistic locking.
- Đo thật trên DBMS và workload đích, đặc biệt khi thao tác nhiều bảng.

### 12.4. Chọn ngưỡng theo dữ liệu

Không có giá trị `batch_size=50` tốt cho mọi ứng dụng. So sánh các mức phù hợp như 20, 50, 100 trong môi trường tương đương và ghi:

- Throughput.
- p95 commit time.
- DB CPU/waits.
- Batch execution count.
- Memory/GC.
- Deadlocks và error rate.

## 13. Hibernate batch fetching: giảm N+1 quan hệ

Hibernate hỗ trợ:

```properties
hibernate.default_batch_fetch_size=32
```

và annotation riêng:

```java
import org.hibernate.annotations.BatchSize;

@Entity
@BatchSize(size = 32)
public class Customer {
    // ...
}
```

Đây không phải `jakarta.persistence.*` API.

### 13.1. Cơ chế minh họa

Không batch:

```text
SELECT ... FROM purchase_orders
SELECT ... FROM customers WHERE id=1
SELECT ... FROM customers WHERE id=2
...
SELECT ... FROM customers WHERE id=100
```

Batch fetching có thể giúp provider nạp nhiều targets một lúc:

```sql
SELECT ...
FROM customers
WHERE id IN (?, ?, ...);
```

### 13.2. Lợi ích

Giảm số secondary SELECTs khi nhiều associations LAZY cần được tải. Tối ưu này hữu ích nếu không muốn hoặc không thể viết fetch join/projection cho mọi use case.

### 13.3. Giới hạn

- SQL shape và batch membership phụ thuộc Hibernate.
- Cache/L1 state có thể làm count khác dự đoán.
- Batch size lớn có thể gây câu `IN` rất dài.
- Không giảm số Customer entities cần materialize nếu use case thực sự cần tất cả.
- Đổi provider có thể mất annotation/configuration hoặc semantics.

### 13.4. Portable alternative

Khi biết trước danh sách IDs, một query JPA sử dụng `IN :ids` có thể chủ động tải các targets theo nhóm.

```java
List<Customer> customers = em.createQuery(
    """
    SELECT c
    FROM Customer c
    WHERE c.id IN :ids
    """,
    Customer.class
)
.setParameter("ids", customerIds)
.getResultList();
```

Tuy nhiên phương án này **không đồng nghĩa tự kích hoạt mọi LAZY relationship của Orders**; service phải xây/tiêu thụ kết quả theo nhu cầu. Nó phù hợp khi application có thể điều phối query chủ động, còn `@BatchSize` là một tiện ích fetch orchestration ở tầng provider.

## 14. Hibernate SUBSELECT fetch và những trade-off

Một extension khác:

```java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@OneToMany(mappedBy = "order")
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines;
```

### 14.1. Mục tiêu

Khi nhiều Orders đã được tải, Hibernate có thể dùng một secondary subselect để tải collections liên quan thay vì một SELECT cho từng Order, tùy context và provider behavior.

### 14.2. Khi có lợi

- Một use case thường cần lines của nhiều Orders đã load.
- Fetch join collection gây row multiplication hoặc vấn đề pagination.
- Dữ liệu phân bố phù hợp subselect strategy.

### 14.3. Những rủi ro

- Secondary query có thể tải collections cho nhiều owners hơn dự kiến trong persistence context.
- Với batch lớn, có thể tạo payload lớn.
- Query shape phụ thuộc Hibernate.
- Không phải cú pháp portable JPA.
- Cần xem chính xác Hibernate version đang dùng.

### 14.4. So sánh với `JOIN FETCH`

| Hướng | Chuẩn JPA? | Điểm mạnh | Nguy cơ |
| --- | --- | --- | --- |
| To-one `JOIN FETCH` | Có | Giảm secondary loads | Over-fetch entity state |
| To-many `JOIN FETCH` | Có | Dễ dùng cho một aggregate | Row multiplication, pagination |
| Query children bằng `IN :ids` | Có | Control scope, dễ batch theo page | Cần code điều phối |
| Hibernate `@BatchSize` | Không | Giảm N+1 khi lazy access | Gắn với Hibernate |
| Hibernate `@Fetch(SUBSELECT)` | Không | Gom collection fetch | Tải ngoài ý định/large secondary query |

Không thể chọn chỉ dựa trên số SQL ít nhất; phải đo rows, bytes, p95 và heap.

## 15. Read-only optimization: projection chuẩn và Hibernate extension

Read-only query có thể được tối ưu bằng cách **không tạo managed entity khi không cần**.

### 15.1. Portable: DTO projection

```jpql
SELECT new com.example.shop.dto.OrderSummary(
    o.id, o.reference, c.name
)
FROM PurchaseOrder o
JOIN o.customer c
```

Các DTOs không được JPA quản lý như entity; không có nhu cầu dirty checking cho những DTO đó.

### 15.2. Provider-specific: Hibernate read-only query

Ví dụ, khi **cần entity results nhưng không muốn Hibernate theo dõi thay đổi với semantics read-only riêng**:

```java
jakarta.persistence.TypedQuery<PurchaseOrder> jpaQuery =
    em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    );

org.hibernate.query.Query<PurchaseOrder> hibernateQuery =
    jpaQuery.unwrap(org.hibernate.query.Query.class);

hibernateQuery.setReadOnly(true);

List<PurchaseOrder> orders =
    hibernateQuery.getResultList();
```

Đây là code dành cho Hibernate; dùng raw/type cast tùy compiler/generics API version có thể cần điều chỉnh.

### 15.3. Cảnh báo quan trọng

Read-only trong Hibernate có thể thay đổi dirty checking/snapshot behavior; **không coi đó là một chế độ lock read-only hoặc bằng chứng dữ liệu sẽ không bao giờ bị ghi**.

Không dùng `setReadOnly(true)` trên query nếu cùng transaction cần sửa những entity được trả về và mong JPA tự flush như thông thường.

### 15.4. Chọn theo contract

Nếu màn hình chỉ cần ba cột, projection đơn giản và ít phụ thuộc hơn. Chỉ dùng provider read-only entity mode khi có lý do thật sự cần entities, đã hiểu semantics và đã đo lợi ích.

## 16. JDBC fetch size: API chuẩn, hiệu quả không portable

JDBC có API chuẩn:

```java
PreparedStatement statement =
    connection.prepareStatement(sql);

statement.setFetchSize(100);
```

Đó là một hint đối với JDBC driver về số rows nên lấy ở mỗi lượt fetch, không phải cam kết provider/driver buộc thực hiện đúng.

Trong Hibernate có thể dùng cấu hình riêng như:

```properties
hibernate.jdbc.fetch_size=100
```

### 16.1. Vùng giao nhau

- `PreparedStatement.setFetchSize` là JDBC API chuẩn.
- Việc provider tự đặt fetch size lên statements do JPA tạo là vấn đề integration/cấu hình.
- Hiệu quả thực tế phụ thuộc driver, cursor mode, transaction, DBMS và result shape.

### 16.2. Fetch size khác page size

- **Page size**: số kết quả logic application muốn trả.
- **Fetch size**: hint về số rows driver lấy theo các đợt.

Một query trả 100.000 rows với fetch size 100 vẫn có thể đưa 100.000 rows vào JVM nếu application duyệt toàn bộ.

### 16.3. Không bật streaming để giữ connection quá lâu

Stream/cursor có thể giúp giảm peak memory nhưng giữ database connection và transaction mở lâu. Cần quản lý resources, timeouts và workload thật.

## 17. L2 cache: phần chuẩn và phần riêng

JPA có những thành phần cache tiêu chuẩn:

- `@Cacheable`.
- `SharedCacheMode` trong cấu hình persistence unit.
- `EntityManagerFactory.getCache()`.
- `Cache.contains()`, `evict()`, `evictAll()`.
- `CacheRetrieveMode` và `CacheStoreMode` cùng query hints tương ứng.

### 17.1. Cấu hình cache qua chuẩn

Ví dụ entity:

```java
@Entity
@Cacheable
public class Product {
    // ...
}
```

Trong `persistence.xml` có thể khai báo:

```xml
<shared-cache-mode>ENABLE_SELECTIVE</shared-cache-mode>
```

Hành vi thực tế của shared/L2 cache phụ thuộc việc provider có hỗ trợ và được cấu hình cache backend phù hợp.

### 17.2. Standard query cache modes

```java
query.setHint(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

query.setHint(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.BYPASS
);
```

Các hint này liên quan chính sách truy xuất/lưu shared entity cache khi được hỗ trợ, không đồng nghĩa một **query result cache** portable.

### 17.3. Provider-specific L2 cache

Hibernate có provider-specific cache region annotations/configuration và cache provider integrations. EclipseLink có shared cache settings, cache coordination và invalidation riêng.

Chi phí phụ thuộc tăng khi application dựa vào:

- Tên cache regions.
- Concurrency strategy.
- Query cache configuration.
- Distributed cache invalidation.
- Provider-specific fetch/cache hints.
- Cache metrics API.

### 17.4. Query cache không phải JPA standard feature chung

Nếu bật Hibernate query cache bằng cấu hình/hints riêng, không tự coi mọi provider sẽ hiểu cùng properties. Query cache còn có consistency/invalidations và cache-key considerations riêng.

### 17.5. Cache không thay correctness

Một Product từ cache có thể là dữ liệu cũ nếu external writer hoặc bulk DML cập nhật DB không có invalidation thích hợp. Đo cache hit rate phải đi cùng stale-data policy và consistency requirements.

## 18. Standard query hints và provider hints

JPA có `Query.setHint(String, Object)`, nhưng **cơ chế set hint chuẩn không biến mọi hint name thành portable**.

### 18.1. Ví dụ hint chuẩn

```java
query.setHint(
    "jakarta.persistence.query.timeout",
    3000
);
```

Timeout hint thường được diễn đạt bằng milliseconds theo contract; nhưng khả năng hỗ trợ, cách enforced và exception timing phụ thuộc provider/DBMS.

Một số hints chuẩn khác liên quan cache và fetch graphs như đã đề cập.

### 18.2. Hint riêng được truyền qua cùng API

```java
query.setHint("some.provider.option", value);
```

Dù `setHint` là phương thức JPA, chuỗi `some.provider.option` có thể là extension. Nếu provider không nhận, hint có thể không được áp dụng hoặc được xử lý theo quy tắc implementation.

### 18.3. Query timeout không phải một phép tối ưu latency

Timeout giúp giới hạn thời gian chờ trong những điều kiện có thể thực thi; nó **không làm SQL tự chạy nhanh hơn**. Khi timeout xảy ra, request thất bại hoặc bị hủy theo semantics từng tầng.

### 18.4. Lock hints cũng cần cân nhắc

`jakarta.persistence.lock.timeout` và lock modes thuộc JPA, nhưng database lock behavior, NOWAIT/WAIT/SKIP LOCKED support và dialect SQL có thể khác.

Đổi `PESSIMISTIC_WRITE` chỉ để “đỡ retry” có thể tăng lock contention và throughput giảm. Locking là quyết định correctness/concurrency trước, performance sau.

### 18.5. Xác nhận hint có hiệu lực

Không dừng ở code compile hoặc `Query.setHint()` không ném exception. Đo lại SQL behavior, timeout, cache statistics hoặc provider logs theo scenario phù hợp.

## 19. Native SQL: API chuẩn, nội dung SQL có thể phụ thuộc DB

JPA chuẩn có:

```java
Query query = em.createNativeQuery(
    "SELECT id, sku FROM products WHERE active = true"
);
```

**`createNativeQuery()` là API chuẩn**, nhưng nội dung SQL được gửi xuống database và có thể phụ thuộc SQL dialect.

### 19.1. Trường hợp dùng SQL portable subset

Một `SELECT ... WHERE ...` cơ bản có thể chạy trên nhiều DBMS, với những khác biệt về boolean literals, functions, quoting và data types.

Không vì gọi `createNativeQuery()` mà tự động kết luận mọi SQL đều vendor-locked; cũng không vì API chuẩn mà kết luận query portable.

### 19.2. Trường hợp database-specific rõ ràng

PostgreSQL:

```sql
SELECT id, payload
FROM events
WHERE payload @> '{"type":"payment"}'::jsonb;
```

Syntax `@>` và cast `::jsonb` phụ thuộc PostgreSQL.

### 19.3. Vì sao dùng native SQL?

- Cần window function hoặc cú pháp mà JPQL version hiện tại không biểu đạt đủ.
- Cần recursive CTE đặc thù.
- Cần JSON/array/full-text operators.
- Cần vendor optimizer hints hoặc execution plan features.
- Cần một báo cáo aggregate rất phức tạp.
- Cần truy cập view/materialized view hoặc database features.

Một số phiên bản JPQL/HQL/provider đã hỗ trợ thêm những tính năng này; phải phân biệt standard JPQL version và provider extension.

### 19.4. Chi phí phụ thuộc

- Phải viết SQL theo DBMS.
- Các cột trả về và result mapping phải được bảo trì.
- Dễ bị phụ thuộc tên bảng/cột hơn JPQL.
- Đổi naming strategy không tự sửa native SQL.
- Unit tests với in-memory DB khác production có thể không chạy.

### 19.5. Đừng cấm native SQL vì khẩu hiệu portability

Nếu truy vấn báo cáo chỉ chạy trên PostgreSQL và native SQL được đo nhanh hơn nhiều, rõ ràng hơn, có test và nằm trong repository boundary, đó có thể là lựa chọn kỹ thuật phù hợp.

## 20. Hibernate HQL extension và SQL dialect features

Hibernate thường cung cấp HQL có phạm vi biểu thức/tính năng rộng hơn JPQL chuẩn tương ứng. Một query chạy trong Hibernate `createQuery` không chắc là portable JPQL nếu nó dùng HQL-specific constructs.

### 20.1. Cảnh báo

Một ứng dụng có thể viết:

```java
em.createQuery("... HQL-specific syntax ...");
```

vẫn sử dụng `EntityManager` chuẩn ở entrypoint, nhưng **query string không còn được bảo đảm portable**.

### 20.2. Cách kiểm soát

- Tài liệu hóa query nào là JPQL chuẩn và query nào là Hibernate HQL extension.
- Test với provider khác nếu portability là yêu cầu.
- Giữ những queries đặc thù ở repository/adapter riêng.
- Không để một extension cú pháp rò khắp application services.

### 20.3. Đổi provider phải xét nhiều hơn Java imports

Một migration Hibernate → EclipseLink có thể cần xem:

- HQL-specific syntax.
- Cache config/hints.
- Lazy-loading/enhancement behavior.
- Flush ordering.
- ID generation.
- SQL dialect assumptions.
- Entity graph execution.
- Lock timeout support.
- Native SQL result mappings.
- Statistics/tracing integration.

## 21. EclipseLink-specific optimization cũng tồn tại

Không chỉ Hibernate mới có extensions.

EclipseLink có những tối ưu và query hints riêng, ví dụ batch reading/prefetching, cache usage và statement/query tuning. Một ví dụ dạng annotation provider-specific là:

```java
import org.eclipse.persistence.annotations.BatchFetch;
import org.eclipse.persistence.annotations.BatchFetchType;

@BatchFetch(BatchFetchType.IN)
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

### 21.1. Tinh thần của extension

Một use case có thể được hưởng lợi từ việc EclipseLink nhóm queries để tải các relationship targets theo chiến lược nó hỗ trợ.

### 21.2. Khả năng chuyển đổi

Hibernate `@BatchSize` và EclipseLink `@BatchFetch` **không phải cùng annotation** hoặc cùng hợp đồng API. Chúng có thể hướng tới vấn đề tương tự, nhưng runtime SQL và cache behavior cần kiểm chứng.

### 21.3. Không đưa annotation của hai providers lên cùng một entity một cách vô thức

Việc classpath chứa cả `org.hibernate.annotations.*` và `org.eclipse.persistence.annotations.*` không tạo một giải pháp portable. Nó dễ làm metadata phức tạp và khó dự đoán mỗi provider xử lý gì.

Nếu thật sự cần hỗ trợ nhiều providers, ưu tiên:

- JPA mappings chuẩn ở entity.
- Provider-specific properties trong bootstrap/config module.
- Provider adapter hoặc repository riêng cho các tối ưu chuyên biệt.
- Tests trên từng provider.

### 21.4. Kiểm tra version và supported hints

Các extension provider thay đổi theo version. Không copy một query hint từ blog cũ rồi cho rằng nó còn hiệu lực trên phiên bản đang chạy.

## 22. Hibernate StatelessSession: đánh đổi lớn hơn batching

Trong một số workload nhập/xuất khối lượng lớn, Hibernate cung cấp `StatelessSession` — API riêng không thuộc `EntityManager` chuẩn.

### 22.1. Vì sao có thể nhanh?

Một stateless session giảm một số overhead liên quan persistence context, automatic dirty checking, entity lifecycle và caching behavior so với Session thông thường.

### 22.2. Giá phải trả

Không được áp các giả định của managed JPA entities vào stateless operations:

- Không có persistence context/identity map thông thường.
- Không có automatic dirty checking theo JPA entity lifecycle.
- Cascades, callbacks, collection handling và interceptor behaviors có thể khác.
- Cần quản lý insert/update/delete và transaction semantics rõ.
- Có thể tạo aliasing hoặc stale-state issues nếu chuyển đổi giữa session types thiếu kiểm soát.

### 22.3. Khi nào hợp lý?

- ETL/batch import có dữ liệu độc lập.
- Khối lượng rất lớn, measured bottleneck là persistence context overhead.
- Workload đơn giản, không cần đầy đủ entity lifecycle.
- Có dedicated integration tests và recovery strategy.

### 22.4. Khi nào không nên dùng?

Nếu use case cần đầy đủ cascade/orphanRemoval, entity listeners, optimistic version handling và domain aggregate semantics, đừng dùng `StatelessSession` chỉ vì muốn “nhanh hơn”.

### 22.5. Tư duy lựa chọn

Nếu JPA chunking + Hibernate JDBC batching đủ nhanh và đơn giản, chưa có lý do chuyển sang một API khác hẳn lifecycle semantics.

## 23. @DynamicUpdate và các extension ánh xạ khác

Hibernate có những annotations như:

```java
import org.hibernate.annotations.DynamicUpdate;

@Entity
@DynamicUpdate
public class Product {
    // ...
}
```

### 23.1. Ý tưởng

Hibernate có thể tạo SQL UPDATE chỉ chứa những cột bị thay đổi thay vì một mẫu UPDATE cố định theo entity, tùy state và configuration.

### 23.2. Không phải lúc nào cũng lợi

- Có thể giảm dữ liệu ghi với entity nhiều cột.
- Nhưng có thể sinh nhiều SQL statement shapes hơn.
- Driver/DB statement caching có thể kém hiệu quả.
- Cần dirty state phù hợp, detached workflows và mapping semantics rõ.
- Không tự thay thế optimistic locking.

### 23.3. Lựa chọn portable thay thế

Một số use cases nên tránh update nguyên entity không cần thiết bằng cách:

- Dùng domain methods chỉ thay fields cần sửa.
- Đặt fetch plan phù hợp.
- Dùng JPQL bulk update khi semantics cho phép.
- Tách aggregate hoặc write model nếu entity quá lớn.
- Thiết kế DTO update command tránh merge partial graph.

Không có một annotation provider-specific nào sửa được một domain model có responsibilities quá rộng.

## 24. Indexes và physical schema: tối ưu vượt khỏi JPA provider

Một ứng dụng có thể dùng JPA chuẩn:

```java
@Table(
    name = "products",
    indexes = @Index(
        name = "idx_product_status_created",
        columnList = "status, created_at"
    )
)
```

`@Index` cung cấp metadata cho schema generation. Nhưng database production thường được quản lý bằng migrations.

### 24.1. Portable ở mức ý định

“Có index phục vụ filter status và sort created_at” là một **ý định thiết kế chung**.

### 24.2. Phụ thuộc database ở mức thực hiện

Mỗi DBMS có thể khác về:

- B-tree/Hash/GiST/GIN/index types.
- Partial/filtered indexes.
- Expression/function indexes.
- INCLUDE columns.
- Clustering/partitioning.
- Index visibility.
- Lock impact khi build index online.
- Execution plan và cardinality estimates.

### 24.3. Không coi mọi index là provider-specific JPA optimization

Một index PostgreSQL được tạo bằng Flyway không phải “Hibernate optimization” dù Hibernate hưởng lợi khi query chạy. Nó là **database-specific physical optimization**.

### 24.4. Lựa chọn tối ưu theo bottleneck

Nếu một SQL query chậm vì thiếu index, đổi `JOIN FETCH` thành Hibernate `@BatchSize` không chắc giải quyết nguyên nhân.

Hãy dùng `EXPLAIN`/`EXPLAIN ANALYZE` theo DBMS trong môi trường phù hợp để xem plan, rows scanned, buffers và waits.

## 25. Chuẩn hóa đo lường trước khi quyết định phụ thuộc

Một quyết định “bật extension hay không” phải dựa vào số liệu.

### 25.1. Thiết lập baseline

Ví dụ môi trường test cố định:

```text
DBMS: PostgreSQL (cùng major version mục tiêu)
JPA provider: Hibernate (version đã pin)
Dataset: 10,000 Orders / 10,000 Customers
Page size: 50
Cache state: cold L1; L2 disabled
Concurrency: 20 virtual users
Measurements: 2 min warm-up, 10 min observation
```

Đây là **mẫu thiết kế benchmark**, không phải số đo thực tế.

### 25.2. Chỉ số tối thiểu

| Metric | Vì sao quan trọng |
| --- | --- |
| SQL execution count/request | Phát hiện round-trip/N+1 |
| p50/p95/p99 request latency | Hiểu phản hồi của user và tail |
| JDBC total duration/request | Phân biệt SQL time với ORM/app time |
| SQL rows/bytes returned | Phát hiện row multiplication |
| Entity/collection loads | Đánh giá hydration/persistence context |
| Heap allocation/GC | Phát hiện over-fetching |
| DB CPU/IO/waits | Không tối ưu app bằng cách đẩy nặng lên DB |
| Connection pool utilization | Biết contention do connection |
| Error/timeout rate | Không đánh đổi correctness/reliability |

### 25.3. Cẩn thận với Hibernate Statistics

`org.hibernate.stat.Statistics` có các counters như `getEntityLoadCount()` và `getPrepareStatementCount()`. Đây là công cụ hữu ích, nhưng **prepare count không luôn bằng SQL executions**; global counters cũng có thể chứa hoạt động của những requests khác.

Khi cần exact JDBC execute count theo request, dùng JDBC/DataSource instrumentation phù hợp hoặc tracing per-request.

### 25.4. Đo thời gian đúng phạm vi

Một timer quanh `getResultList()` có thể bỏ sót:

- LAZY access khi DTO mapping.
- JSON serialization sau repository.
- Flush/commit của write transaction.
- Pool wait hoặc retry ngoài đoạn timer.

Đo cả operation-level và end-to-end để tránh chẩn đoán sai.

### 25.5. So sánh đồng thời nhiều hướng

Nên chạy:

1. Baseline mapping/query.
2. Portable JPQL projection.
3. Portable fetch join.
4. Portable EntityGraph.
5. Hibernate batch fetching.
6. Native SQL/DB extension nếu cần.

**Không cần dùng mọi bước trên một production path.** Mục tiêu là chứng minh hướng nào đạt SLO và chi phí chấp nhận được.

## 26. Bảng kết quả minh họa

Giả sử một API trả 50 Orders + Customer name, dataset gồm nhiều Customers khác nhau và cache lạnh.

| Phương án | SQL executions* | Managed entities loaded* | p95 latency* | Khả chuyển |
| --- | ---: | ---: | ---: | --- |
| LAZY N+1 | 51 | ~100 | 240 ms | API chuẩn, query pattern kém |
| `JOIN FETCH` | 1 | ~100 | 46 ms | JPA chuẩn |
| `EntityGraph` | 1–vài | ~100 | 50 ms | JPA chuẩn; SQL tùy provider |
| DTO projection | 1 | ~0 cho Order/Customer scalar DTO | 32 ms | JPA chuẩn |
| Hibernate batch fetch 16 | ~5 | ~100 | 76 ms | Hibernate-specific |
| Native DB-optimized query | 1 | ~0 nếu scalar DTO | 25 ms | SQL/DB-specific |

*Các số hoàn toàn **minh họa**, không phải benchmark đã chạy. Thực tế thay đổi theo dataset, cache, SQL, provider, DBMS và load.*

### 26.1. Cách diễn giải

Nếu DTO projection 32 ms đã đáp ứng SLO p95 dưới 100 ms, native SQL 25 ms có thể chưa đáng đánh đổi portability, test và maintenance.

Nếu một báo cáo chạy hàng triệu lần mỗi giờ, chênh lệch nhỏ có thể tạo tiết kiệm đáng kể; khi đó extension có thể hợp lý.

### 26.2. Đừng chọn bằng chênh lệch ngẫu nhiên

Một lần chạy 25 ms và 32 ms chưa chứng minh hơn nhau. Cần nhiều samples, warm-up, variation estimates, tải đại diện và validation kết quả business.

### 26.3. Hiệu năng không phải thước đo duy nhất

Một hướng nhanh hơn nhưng sai tenant authorization, bypass optimistic locking hoặc gây stale cache là **không đạt yêu cầu**.

## 27. Quy trình ra quyết định: ưu tiên chuẩn khi đủ tốt

Dùng trình tự:

```text
Có bottleneck đo được?
       |
       +-- Chưa
       |     -> Bổ sung metrics, SQL tracing,
       |        representative benchmark
       |
       +-- Có
             |
             v
      Xác định nguyên nhân
        /        |         \
       /         |          \
  N+1/overfetch  Slow SQL   Write throughput
       |             |            |
       v             v            v
  Projection/      Filter/index    Chunking/bulk
  fetch plan       and plan        DML/batch design
       \             |            /
        \            |           /
         v           v          v
       Đo lại cùng workload
                 |
        +--------+--------+
        |                 |
      Đạt SLO          Chưa đạt
        |                 |
        v                 v
    Giữ portable      Cân nhắc extension
                          |
                          v
                  Lợi ích đủ lớn?
                   /          \
                 Không         Có
                  |            |
             Giữ đơn giản  Cô lập phụ thuộc,
                           benchmark, test,
                           upgrade/fallback
```

### 27.1. Chẩn đoán trước khi chọn extension

| Triệu chứng | Điều cần kiểm tra trước |
| --- | --- |
| SQL count tăng theo số Orders | N+1, LAZY access, DTO mapping |
| SQL count thấp nhưng chậm | SQL plan, missing index, row volume |
| Loads quá nhiều entities | Projection, page size, graph breadth |
| Insert batch chậm | JDBC batching, ID strategy, transaction size |
| GC tăng sau report | Object hydration, collections, streaming |
| p99 request tăng đột biến | DB locks, pool waits, cache misses |
| L2 hit thấp | Cache working set, expiry, invalidation |
| Data stale | Bulk DML/external writers, cache consistency |

### 27.2. Câu hỏi cần trả lời để phê duyệt extension

1. Bottleneck nào được xác nhận?
2. Portable alternatives đã được thử chưa?
3. Lợi ích đo được là bao nhiêu ở p95, throughput và DB load?
4. Feature riêng thuộc provider/version nào?
5. Chi phí khi nâng major version?
6. Có fallback hoặc implementation khác không?
7. Có correctness tests cho transaction/cache/locking không?
8. Có observability sau deploy không?
9. Có tài liệu ghi rõ phụ thuộc không?
10. Quyết định này có lan rộng trên bao nhiêu entities/services?

## 28. Cô lập provider-specific code ở ranh giới adapter

Một lỗi thiết kế là đặt Hibernate API trực tiếp trong mọi application service:

```java
public class OrderService {

    void process() {
        org.hibernate.Session session = ...;
        // Toàn bộ workflow phụ thuộc Hibernate internals.
    }
}
```

Nếu sau này đổi provider, phạm vi sửa rất lớn.

### 28.1. Tách contract nghiệp vụ và persistence implementation

```text
Application Service
       |
       v
OrderReadRepository (interface)
       |
       +---------------------------+
       |                           |
       v                           v
JpaOrderReadRepository      HibernateOptimizedRepository
(JPA standardized query)    (provider extension)
       |                           |
       +-------------+-------------+
                     |
                Database
```

### 28.2. Interface không nhắc tới provider

```java
public interface OrderReadRepository {

    List<OrderSummary> findSummaries(
        OrderStatus status,
        int limit
    );
}
```

### 28.3. Implementation mặc định chỉ dùng chuẩn

```java
public final class JpaOrderReadRepository
        implements OrderReadRepository {

    private final EntityManager em;

    public JpaOrderReadRepository(EntityManager em) {
        this.em = em;
    }

    @Override
    public List<OrderSummary> findSummaries(
            OrderStatus status,
            int limit) {

        return em.createQuery(
            """
            SELECT new com.example.shop.dto.OrderSummary(
                o.id, o.reference, c.name
            )
            FROM PurchaseOrder o
            JOIN o.customer c
            WHERE o.status = :status
            ORDER BY o.id
            """,
            OrderSummary.class
        )
        .setParameter("status", status)
        .setMaxResults(limit)
        .getResultList();
    }
}
```

Trong ứng dụng thực tế, validate `limit` (không âm, có ngưỡng tối đa) và kiểm tra tenant/authorization. Ví dụ tập trung vào ranh giới phụ thuộc.

### 28.4. Implementation riêng nếu thật sự cần

Một adapter Hibernate có thể dùng `Query.unwrap(...)`, `Session` hoặc provider hints bên trong module riêng, nhưng vẫn trả `List<OrderSummary>` như contract.

**Không cố viết một generic abstraction cho mọi option của mọi provider** nếu abstraction trở nên phức tạp hơn implementation. Chỉ tách đúng những extension đang dùng.

### 28.5. Tách cấu hình

```text
application-common.properties:
  JPA datasource/transaction config

application-hibernate.properties:
  hibernate.jdbc.batch_size=50
  hibernate.default_batch_fetch_size=32

application-eclipselink.properties:
  EclipseLink-specific options (khi dùng)
```

Đây là sơ đồ tổ chức; tên file và profile semantics phụ thuộc framework. Không nạp đồng thời những cấu hình provider không tương thích.

## 29. Dependency management và nâng cấp provider

Một extension riêng có thể hoạt động rất tốt hôm nay nhưng đổi behavior khi nâng version.

### 29.1. Các nhóm rủi ro khi upgrade

- Annotation/hint bị đổi tên hoặc deprecated.
- Default query behavior thay đổi.
- JDBC batching implementation thay đổi.
- SQL generation thay đổi.
- L2 cache region handling thay đổi.
- Lazy loading/bytecode enhancement thay đổi.
- Native query result type mapping thay đổi.
- Hibernate Statistics API version khác.
- Behavior với IDENTITY/SEQUENCE khác.
- Tên properties thay đổi từ `javax.persistence` sang `jakarta.persistence` khi nâng stack.

### 29.2. Vì sao phải pin versions?

Một performance regression có thể do nâng provider, JDBC driver, DB dialect, JVM hoặc DB version. Ghi versions trong benchmark và release notes giúp xác định nguyên nhân.

### 29.3. Tests trước upgrade

- Contract tests cho repository output.
- Query/fetch-plan tests.
- N+1 regression SQL budgets.
- Entity lifecycle/cascade tests.
- Optimistic locking tests.
- Cache consistency tests.
- Batch insert/update throughput tests.
- SQL plan inspection với DBMS đích.
- Performance baseline với workload đại diện.

### 29.4. Không dựa vào H2 để chứng minh đổi provider

H2 test có ích, nhưng PostgreSQL/Oracle/MySQL có SQL dialect/locks/indexes khác. Khi portability là yêu cầu thực sự, cần ít nhất một tập integration tests trên các provider/DBMS được cam kết hỗ trợ.

## 30. Portability test suite: kiểm tra lời hứa khả chuyển

Nếu sản phẩm tuyên bố hỗ trợ cả Hibernate và EclipseLink, phải có **test matrix** tương ứng.

### 30.1. Test theo chức năng trước

Ví dụ cùng `OrderReadRepository` phải thỏa:

- Trả đúng Orders.
- Không lộ Orders khác tenant.
- Có order đúng.
- Paging đúng.
- Null/optional relation behavior đúng.
- Mapping values/enum/version đúng.

### 30.2. Test khả năng thay provider

```text
               Same JPA repository tests
                         |
              +----------+----------+
              |                     |
              v                     v
         Hibernate PU          EclipseLink PU
              |                     |
              v                     v
       DBMS test target       DBMS test target
```

Không cần sản phẩm nào cũng chạy hai providers. Chỉ làm nếu **provider portability là yêu cầu được cam kết**; nếu không, giữ dependency rõ và test trên stack thực tế có thể hiệu quả hơn.

### 30.3. Hiệu năng là mục tiêu riêng

Một query đúng trên hai providers không có nghĩa cùng SLO. Cần performance profile của từng tổ hợp provider/DBMS.

### 30.4. Provider-specific optimization cần alternative

Nếu implementation Hibernate dùng `@Fetch(SUBSELECT)`, test trên EclipseLink không thể giả định annotation đó có hiệu lực.

Có thể:

- Dùng repository alternative bằng JPQL queries.
- Định nghĩa cấu hình provider-specific qua deployment.
- Chọn common portable strategy thay vì phụ thuộc.
- Hoặc giới hạn chính thức supported provider list.

### 30.5. Không gắn nhãn portable chỉ vì import jakarta.persistence

Một code path có thể dùng:

- `EntityManager` chuẩn.
- Query HQL extension không chuẩn.
- `setHint` với Hibernate hint.
- Native SQL PostgreSQL.
- Mappings phụ thuộc naming conventions Hibernate.

**Portability phải được đánh giá trên toàn đường thực thi**, không chỉ những import đầu file.

## 31. Transaction, cache và consistency khi tối ưu

Một tối ưu hiệu năng chỉ thành công khi không phá semantics nghiệp vụ.

### 31.1. Bulk update vs dirty checking

Thay managed updates bằng JPQL bulk UPDATE có thể giảm SQL, nhưng bỏ qua entity callbacks theo từng row và không tự cập nhật managed instances đã nạp.

### 31.2. Read-only mode vs writes

Một provider read-only optimization có thể thay dirty checking behavior. Nếu caller sau đó sửa entity mà mong tự flush, sẽ xuất hiện lỗi khó nhận diện.

### 31.3. Native SQL vs L1/L2 state

SQL native update database có thể làm persistence context không đồng bộ. Application phải quản lý flush/clear/reload và cache invalidation phù hợp.

### 31.4. Batching vs failure recovery

Một batch DML lỗi có thể rollback toàn transaction; cần retry/idempotency và phương án khoanh vùng dòng lỗi nếu business yêu cầu.

### 31.5. Fetch join vs dữ liệu phân trang

To-many join fetch với paging có thể trả thiếu/duplicate roots hoặc khiến provider phân trang trong memory. Không hy sinh tính đúng vì muốn một SQL.

### 31.6. Cache vs freshness

L2/query cache nhanh hơn nhưng có thể phục vụ stale data nếu invalidation không tương thích với external writers. Cần cache TTL/invalidation policy phù hợp với nghiệp vụ.

### 31.7. Locking vs throughput

Pessimistic lock có thể giảm một loại race nhưng tăng lock waits. Không chọn lock mode chỉ như một performance hack.

## 32. Những sai lầm thường gặp

### Sai lầm 1 — Đồng nhất JPA API chuẩn với SQL giống nhau

JPA portable source không có nghĩa mọi DBMS nhận cùng SQL hay đạt cùng latency.

### Sai lầm 2 — Coi tất cả native SQL là không thể quản lý

Có thể giới hạn SQL riêng trong adapter có tests; dependency có chủ đích không đồng nghĩa thiết kế sai.

### Sai lầm 3 — Tối ưu trước khi đo

Không có baseline thì không biết extension có giúp hay chỉ làm phức tạp.

### Sai lầm 4 — Dùng một annotation Hibernate rồi gọi giải pháp portable

`@BatchSize`, `@Fetch(SUBSELECT)` không thuộc JPA standard.

### Sai lầm 5 — Nghĩ Hibernate jdbc.batch_size là JPA property

Nó là Hibernate-specific configuration, không phải một phần `jakarta.persistence.*`.

### Sai lầm 6 — Nghĩ flush/clear tự JDBC batch

Chunking persistence context và JDBC driver batching là hai cơ chế khác nhau.

### Sai lầm 7 — Nghĩ saveAll luôn tạo một SQL INSERT nhiều rows

Số INSERTs, batching và semantics phụ thuộc provider/configuration/ID strategy.

### Sai lầm 8 — Bật EAGER toàn bộ để tránh N+1

Có thể tạo secondary selects hoặc over-fetching trên các use cases khác.

### Sai lầm 9 — Dùng JOIN FETCH nhiều collections rồi paginate

Dễ row multiplication hoặc in-memory paging.

### Sai lầm 10 — Nghĩ EntityGraph là cam kết chính xác một SQL

Provider có quyền lựa chọn execution strategy theo spec.

### Sai lầm 11 — Dùng DTO projection ở nơi cần managed entity lifecycle

DTO không có dirty checking hoặc cascade như entity.

### Sai lầm 12 — Dùng query read-only rồi sửa entity

Provider-specific read-only semantics có thể ngăn/đổi dirty checking dự kiến.

### Sai lầm 13 — Dùng bulk DML mà không xử lý persistence context

Managed entities có thể stale, callbacks/version semantics có thể khác.

### Sai lầm 14 — Cho rằng L2 entity cache cũng là query cache chuẩn

Query cache là tính năng provider-specific, không phải API portable chung.

### Sai lầm 15 — Bật cache mà không có consistency policy

External writes có thể làm dữ liệu cache lỗi thời.

### Sai lầm 16 — Coi query.timeout là cách làm query nhanh

Timeout giới hạn thời gian chờ, không tối ưu execution plan.

### Sai lầm 17 — Không xem database index/plan

Một SQL chậm vì index có thể không cần thay fetch strategy.

### Sai lầm 18 — Chỉ đo SQL count

Một SQL join khổng lồ có thể tốn nhiều CPU/IO/memory hơn vài SQL có chọn lọc.

### Sai lầm 19 — Test chỉ trên dataset nhỏ

N+1/row multiplication có thể bị che dưới 10 rows.

### Sai lầm 20 — So sánh cold cache với warm cache

Kết luận không công bằng khi môi trường khác nhau.

### Sai lầm 21 — Dùng global Hibernate Statistics cho concurrent requests

Counters bị trộn hoạt động của các workloads khác.

### Sai lầm 22 — Quên JDBC prepare count khác execute count

Statement preparation và execution là hai thước đo khác nhau.

### Sai lầm 23 — Đo method nhưng không đo commit

Trong Spring transaction interceptor, flush/commit có thể diễn ra sau method body.

### Sai lầm 24 — Gắn SQL/IDs vào metric tags

Tạo high-cardinality và có thể lộ dữ liệu nhạy cảm.

### Sai lầm 25 — Không kiểm thử provider upgrade

Tuning hints, SQL generation và cache behavior có thể thay đổi.

### Sai lầm 26 — Bật mọi Hibernate optimization cùng lúc

Không biết cải thiện do đâu, khó kiểm soát interactions và regressions.

### Sai lầm 27 — Dùng StatelessSession như EntityManager bình thường

Lifecycle/dirty checking/cascade assumptions có thể không đúng.

### Sai lầm 28 — Xem @DynamicUpdate là tối ưu vô điều kiện

Thêm SQL shapes và chi phí statement cache có thể lớn hơn lợi ích giảm columns.

### Sai lầm 29 — Tự suy một index sẽ giúp query

Cần xem DB execution plan và workload; index còn có write overhead.

### Sai lầm 30 — Tuyên bố portability chỉ bằng việc không có import Hibernate

SQL, hint strings, XML mappings và DB indexes vẫn có thể vendor-dependent.

## 33. Bài tập thực hành

### Bài 1 — Phân loại giải pháp

```java
query.setMaxResults(50);
```

**Đáp án:** JPA API chuẩn. Khả chuyển ở contract; execution plan phụ thuộc provider/DBMS.

### Bài 2 — Phân loại Hibernate annotation

```java
@BatchSize(size = 32)
private List<OrderLine> lines;
```

**Đáp án:** Provider-specific. Tối ưu lazy collection batching theo Hibernate.

### Bài 3 — Chọn giữa projection và fetch join

API chỉ cần Order ID, reference và Customer name.

**Gợi ý:** Thử JPQL DTO projection trước; không cần load managed Orders/Customers nếu không có tác vụ cập nhật entity.

### Bài 4 — Vẫn cần managed entity

Service cần sửa `PurchaseOrder` và dựa vào `@Version`/dirty checking.

**Gợi ý:** Dùng entity query với fetch plan cần thiết; DTO projection không thay thế managed lifecycle.

### Bài 5 — Batch import

Team đã gọi `flush()/clear()` mỗi 100 records nhưng SQL vẫn nhiều.

**Đáp án:** Đó là chunking API chuẩn, không chứng minh JDBC batching. Kiểm tra Hibernate batch configuration, ID strategy và driver metrics.

### Bài 6 — IDENTITY và batching

500 Products dùng `GenerationType.IDENTITY`, team kỳ vọng `hibernate.jdbc.batch_size=50` gom toàn bộ INSERTs.

**Đáp án:** Hibernate có hạn chế batching insert với IDENTITY trong nhiều cấu hình. Cần đo và cân nhắc ID strategy nếu schema/DB cho phép.

### Bài 7 — Tối ưu số SQL

Một JOIN FETCH lớn tạo 300.000 rows, so với 3 SQL trả tổng 10.000 rows.

**Đáp án:** Ba SQL có thể tốt hơn; đo rows, bytes, p95 và memory thay vì chỉ count.

### Bài 8 — EntityGraph

```java
query.setHint("jakarta.persistence.fetchgraph", graph);
```

**Đáp án:** Hint chuẩn JPA; không đảm bảo một SQL giống nhau ở mọi provider.

### Bài 9 — Native SQL PostgreSQL

Query dùng `jsonb @>`.

**Đáp án:** `createNativeQuery()` là JPA chuẩn nhưng SQL operator phụ thuộc PostgreSQL.

### Bài 10 — Query timeout

```java
query.setHint("jakarta.persistence.query.timeout", 2000);
```

**Đáp án:** Đây là hint chuẩn về timeout, không tự làm SQL có plan nhanh hơn; việc enforcement cần kiểm chứng.

### Bài 11 — Chuyển provider

Project dùng Hibernate `@Fetch(SUBSELECT)`, giờ muốn chuyển EclipseLink.

**Gợi ý:** Không mong annotation chạy tương đương; thiết kế JPQL fetching/query batching phù hợp hoặc thay bằng EclipseLink-specific adapter có tests.

### Bài 12 — Cache

Project bật Hibernate query cache và `@Cacheable`.

**Đáp án:** `@Cacheable` thuộc JPA; Hibernate query cache là provider-specific. Cần đo hit/miss và freshness.

### Bài 13 — Index

Query lọc theo `status` và sắp xếp `created_at` chậm.

**Gợi ý:** Kiểm tra query plan và indexes; SQL index có thể được quản lý bằng migration thay vì tối ưu JPA-level.

### Bài 14 — Đánh giá trade-off

Phương án JPA projection đạt p95=80 ms, native SQL đạt p95=77 ms, SLO là 150 ms.

**Gợi ý:** Nếu chênh lệch không đáng kể và chi phí maintenance lớn, giữ portable projection là hợp lý. Đây là số giả định cần benchmark đúng.

### Bài 15 — Batch fetch không giảm entity count

Hôm trước 100 Customer được nạp bằng 100 SELECTs; batch fetch còn 4 SELECTs nhưng vẫn nạp 100 Customers.

**Đáp án:** Đúng kỳ vọng. Batching giảm SQL round-trips, không tự giảm số entities phải materialize.

### Bài 16 — Bulk update

Đổi 10.000 managed updates thành một JPQL bulk UPDATE.

**Đáp án:** Có thể nhanh hơn nhưng phải xử lý version, callbacks, stale persistence context và cache theo yêu cầu nghiệp vụ.

### Bài 17 — Không dùng extension lan rộng

Một application service trực tiếp gọi Hibernate Session ở 50 methods.

**Gợi ý:** Cô lập vào repository/adapter, giữ interface nghiệp vụ không phụ thuộc provider.

### Bài 18 — Kiểm thử portability

JPA query chạy trên Hibernate với H2; team tuyên bố hỗ trợ EclipseLink với PostgreSQL.

**Đáp án:** Chưa đủ. Cần kiểm thử trên provider/DBMS được tuyên bố hỗ trợ.

### Bài 19 — Thống kê

`getPrepareStatementCount() == 5`.

**Đáp án:** Không thể khẳng định chính xác 5 JDBC executions trong mọi trường hợp; phải kiểm tra công cụ đo.

### Bài 20 — Thay đổi provider version

Sau nâng Hibernate major version, p95 tăng 30%.

**Gợi ý:** So sánh SQL shapes, fetch behavior, cache settings, JDBC batching, query plans và workload trước–sau; kiểm tra extension API và defaults.

## 34. Câu hỏi tự kiểm tra

**1. Tối ưu khả chuyển là gì?**

Tối ưu dựa trên hợp đồng chuẩn JPA hoặc thiết kế dữ liệu/query ít phụ thuộc provider, với điều kiện hiệu năng vẫn phải đo trên runtime thật.

**2. Tối ưu phụ thuộc provider là gì?**

Tối ưu dùng API, annotation, config, query hint hoặc behavior riêng của một provider.

**3. JPA chuẩn hóa tốc độ query không?**

Không. Nó chuẩn hóa các API/semantics nhất định, không bảo đảm cùng SQL plan hoặc latency.

**4. `EntityManager` thuộc nhóm nào?**

JPA chuẩn.

**5. JPQL constructor projection thuộc nhóm nào?**

JPA chuẩn.

**6. Criteria API thuộc nhóm nào?**

JPA chuẩn.

**7. `JOIN FETCH` thuộc nhóm nào?**

JPQL chuẩn.

**8. `EntityGraph` thuộc nhóm nào?**

JPA chuẩn.

**9. `hibernate.jdbc.batch_size` thuộc nhóm nào?**

Hibernate-specific configuration.

**10. `@BatchSize` có portable giữa Hibernate và EclipseLink không?**

Không, đó là annotation riêng Hibernate.

**11. `@Fetch(SUBSELECT)` có thuộc JPA chuẩn không?**

Không.

**12. `@Cacheable` có thuộc JPA chuẩn không?**

Có, nhưng cache backend/performance phụ thuộc provider.

**13. Hibernate query cache có thuộc chuẩn JPA chung không?**

Không.

**14. `setHint` là chuẩn thì hint tên `org.hibernate.*` có portable không?**

Không. API nhận hint là chuẩn, còn nội dung/tên hint có thể riêng.

**15. `jakarta.persistence.query.timeout` có tăng tốc SQL không?**

Không. Nó kiểm soát timeout trong phạm vi hỗ trợ.

**16. `createNativeQuery` có phải JPA chuẩn không?**

Có, nhưng SQL string có thể vendor-specific.

**17. `jsonb @>` có portable SQL không?**

Không, đây là cú pháp riêng PostgreSQL.

**18. `flush()/clear()` có tự kích hoạt JDBC batching không?**

Không.

**19. Hibernate JDBC batching và Hibernate batch fetching khác nhau ra sao?**

Một bên nhóm thao tác ghi DML, bên kia nhóm tải associations/entities.

**20. `GenerationType.IDENTITY` có thể ảnh hưởng batching không?**

Có, đặc biệt với một số chiến lược insert batching của Hibernate.

**21. Dùng `JOIN FETCH` to-many với paging cần lưu ý gì?**

Row multiplication, duplicate results và nguy cơ in-memory pagination.

**22. DTO projection có thay thế dirty checking entity không?**

Không.

**23. Hibernate `StatelessSession` có cùng lifecycle semantics với JPA `EntityManager` không?**

Không.

**24. Tại sao `@DynamicUpdate` không luôn tốt hơn?**

Nó có trade-off về SQL shapes, statement caching và dirty checking.

**25. Một query 1 SQL có luôn nhanh hơn 3 SQL không?**

Không; rows/bytes/plan và materialization có thể làm một SQL tốn hơn.

**26. Index database có phải một Hibernate-only optimization không?**

Không; nó là physical schema/database optimization, có thể rất DBMS-specific.

**27. Tại sao cần benchmark trước khi dùng extension?**

Để chứng minh bottleneck và lợi ích vượt chi phí phụ thuộc.

**28. Những metrics quan trọng nhất?**

SQL count, latency p95/p99, rows/bytes, entity loads, memory/GC và DB load.

**29. Hibernate Statistics có thuộc JPA API chuẩn không?**

Không.

**30. Có thể dùng global Hibernate counter để đo chính xác riêng một request concurrent không?**

Không nếu không cô lập hoặc có attribution bổ sung.

**31. Tại sao cache state quan trọng?**

L1/L2 hits làm SQL count và latency thay đổi đáng kể.

**32. Vì sao cần kiểm tra kết quả nghiệp vụ trước khi tối ưu?**

Giải pháp nhanh nhưng sai dữ liệu, transaction hoặc authorization là không hợp lệ.

**33. Làm sao giảm chi phí khi đổi provider?**

Dùng interfaces, tách adapter/configuration, không để extension rò rỉ vào domain/application layer.

**34. Khi nào extension riêng là lựa chọn đúng?**

Khi có bottleneck đo được, lợi ích đáng kể, được hỗ trợ trên stack mục tiêu và có tests/maintenance plan.

**35. Chỉ không import `org.hibernate.*` có bảo đảm portable không?**

Không; HQL extension, native SQL, hint strings và schema dependencies vẫn có thể làm code phụ thuộc.

## 35. Kịch bản tổng hợp: chọn giải pháp cho hệ thống 1 triệu Orders

Một hệ thống thương mại đang chạy Hibernate + PostgreSQL:

- Bảng `purchase_orders` có 1 triệu rows.
- API hiển thị 50 Orders mỗi trang.
- Mỗi Order có Customer và trung bình 12 Lines.
- API cần reference, Customer name, số Lines và tổng tiền.
- SLO p95 dưới 200 ms.
- Team muốn giữ khả năng đổi JPA provider nhưng chưa có kế hoạch bắt buộc đổi.

### 35.1. Hiện trạng giả định

Implementation:

```text
Load Page<PurchaseOrder>
    |
    +-- for each Order:
    |       Customer.name -> lazy load
    |       Lines.size() -> lazy load
    |       calculateTotal() -> materialize Lines
    |
    v
Map DTO -> JSON
```

Khi page size 50, SQL count có thể tăng mạnh, heap allocation cao và thời gian mỗi request dao động theo số Lines.

### 35.2. Bước 1 — Đo baseline

Thu thập:

- Per-request SQL execution count.
- SQL fingerprints.
- p50/p95/p99.
- DB execution plan của queries chậm.
- Entity/collection loads.
- Rows returned.
- Cache hit/miss.
- Heap/GC.
- Correctness của totals.

### 35.3. Bước 2 — Thiết kế hướng portable

Thay vì fetch mọi Lines, dùng:

1. Query lấy page Order IDs và Customer name.
2. Một JPQL aggregate query tính `COUNT(l)` và `SUM(l.quantity * l.unitPrice)` theo danh sách Order IDs.
3. Một count query cho tổng trang nếu cần.
4. DTO mapping trong service.
5. Giữ predicates tenant/authorization tại từng query.
6. Dùng indexes phù hợp trong migrations.

JPQL aggregate minh họa:

```jpql
SELECT
    l.order.id,
    COUNT(l),
    SUM(l.quantity * l.unitPrice)
FROM OrderLine l
WHERE l.order.id IN :orderIds
GROUP BY l.order.id
```

Cần xử lý Orders không có Lines, null aggregate values, kiểu của `SUM` và số tiền/currency policy ở service. Query này chỉ là một phần của workflow.

### 35.4. Bước 3 — Đo lại

Nếu p95 đạt SLO và SQL count ổn định với page size, giữ thiết kế portable. Không có lý do phải thêm Hibernate `@Fetch(SUBSELECT)` khi query aggregate đã đáp ứng nhu cầu.

### 35.5. Bước 4 — Khi portable chưa đủ

Nếu aggregate query vẫn chậm trên PostgreSQL do workloads/plan, cân nhắc:

- Database indexes và cập nhật statistics.
- Materialized aggregation hoặc persisted totals với consistency policy.
- Native SQL PostgreSQL-specific query tối ưu.
- Query/cache strategy phù hợp workload.
- Provider-specific hints ở adapter.
- Tối ưu kết nối/pool, không chỉ JPQL.

Mỗi hướng phải được benchmark và có correctness tests.

### 35.6. Bước 5 — Cô lập lựa chọn vendor

```text
OrderSummaryService
       |
       v
OrderSummaryRepository
       |
       +-- JpaOrderSummaryRepository
       |
       +-- PostgresOptimizedOrderSummaryRepository
```

Service không biết SQL dialect. Chỉ adapter được thay khi cần một provider hoặc DBMS khác.

### 35.7. Bước 6 — Regression guard

Trong CI:

- Dữ liệu đại diện có nhiều distinct Customers.
- Orders có phân phối Lines khác nhau (0, 1, 12, 200).
- Query budget cho page size 50.
- Test cùng kết quả business giữa implementations.
- Integration test trên DBMS gần production.
- Performance test đủ samples cho p95/p99.
- Test optimistic locking/caching nếu implementation có state.

### 35.8. Khi nào chấp nhận vendor lock-in lâu dài?

Nếu PostgreSQL-specific query giảm chi phí hạ tầng đáng kể, đáp ứng SLO, đã có DB specialists và không có kế hoạch thay DB, lựa chọn đó có thể hợp lý. Điều quan trọng là **ghi nhận rõ dependency và giới hạn phạm vi**, không giả vờ rằng query vẫn portable.

## 36. Kết luận

Trong JPA, tối ưu khả chuyển và tối ưu phụ thuộc provider **không đối lập tuyệt đối**. Chúng là hai cấp độ công cụ phục vụ cùng mục tiêu: dữ liệu đúng, phản hồi nhanh và chi phí vận hành hợp lý.

Các nguyên tắc đáng nhớ:

1. **Phân biệt portability của API, semantics và hiệu năng.** Một JPQL query chuẩn vẫn có execution plan và latency khác theo DB/provider.
2. **Ưu tiên giảm dữ liệu thừa:** projection, pagination, fetch plan theo use case, query aggregation và thiết kế object graph phù hợp.
3. **Dùng JPA chuẩn trước khi thêm extension nếu đã đủ đáp ứng nhu cầu**, đặc biệt `JOIN FETCH`, `EntityGraph`, JPQL/Criteria và `setMaxResults`.
4. **Nhận diện rõ extension:** Hibernate `@BatchSize`, `@Fetch(SUBSELECT)`, `hibernate.jdbc.batch_size`, `StatelessSession` và EclipseLink batch fetching đều không phải JPA portable APIs.
5. **Đừng nhầm JPA query hint API chuẩn với một hint nội dung chuẩn.** Tên hint quyết định mức portability.
6. **Đừng nhầm JDBC API chuẩn với behavior đồng nhất ở mọi driver.** Fetch size/batching vẫn cần đo.
7. **Một native SQL query có thể là lựa chọn phù hợp** khi nó đem lại lợi ích đáng kể và được cô lập/test với DBMS đích.
8. **Không chỉ tối ưu SQL count:** theo dõi p95/p99, rows, entity loads, heap, pool waits và DB CPU/IO.
9. **Mọi tối ưu phải bảo toàn transaction, cache, version và authorization semantics**, đặc biệt bulk DML, read-only modes và caching.
10. **Cô lập mã provider-specific ở repository/adapter**, giữ domain/application APIs ít phụ thuộc.
11. **Khi nâng provider/version, chạy lại performance và correctness tests** thay vì mặc định mọi extension hoạt động giống cũ.
12. **Ra quyết định từ bottleneck và chi phí sở hữu**, không từ khẩu hiệu “portable luôn tốt nhất” hay “provider-specific luôn nhanh nhất”.

Một hệ thống có thể sử dụng **90% JPA chuẩn và 10% extensions được đo lường, tài liệu hóa, kiểm thử** mà vẫn có kiến trúc dễ bảo trì. Thành công không được đo bằng việc có bao nhiêu import `org.hibernate.*`, mà bằng việc **những phụ thuộc được chọn có lý do, nằm đúng ranh giới và tạo lợi ích rõ ràng mà không làm suy giảm tính đúng đắn của dữ liệu**.

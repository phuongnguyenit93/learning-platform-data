# Giảm N+1 bằng kế hoạch đọc theo trường hợp sử dụng trong JPA

Một ứng dụng Java dùng JPA có thể chỉ gọi một repository method nhưng tạo ra hàng chục hoặc hàng trăm truy vấn SQL. Hiện tượng phổ biến nhất là **N+1 query**: một truy vấn tải danh sách `N` entities, sau đó mỗi entity hoặc association lại kích hoạt một truy vấn khác khi application truy cập dữ liệu liên quan.

Giả sử trang quản trị hiển thị **50 đơn hàng**, mỗi dòng gồm tên khách hàng:

```java
List<SalesOrder> orders =
    em.createQuery(
        "select o from SalesOrder o order by o.createdAt desc",
        SalesOrder.class
    ).getResultList();

for (SalesOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

Nếu `SalesOrder.customer` là lazy association và mỗi đơn có một customer khác nhau, hành vi có thể giống:

```sql
-- Truy vấn 1: lấy 50 orders.
SELECT ... FROM sales_order ORDER BY created_at DESC;

-- Truy vấn 2 đến 51: lấy từng customer.
SELECT ... FROM customer WHERE id = ?;
SELECT ... FROM customer WHERE id = ?;
-- ...
```

Chỉ đọc 50 dòng nhưng có thể cần **51 lần round-trip** tới database. Nếu code còn đọc `order.getLines()` rồi `line.getProduct().getName()`, vấn đề có thể lồng nhiều tầng.

Một cách sửa thường được nhắc đến là dùng `JOIN FETCH`. Nhưng một `JOIN FETCH` cho mọi quan hệ ở mọi nơi sẽ dẫn đến vấn đề mới:

- Join nhiều collection gây **nhân bản dòng dữ liệu** và tăng dữ liệu truyền qua JDBC.
- Fetch join collection với pagination có thể khiến phân trang không đúng hoặc provider phân trang trong memory.
- Fetch quá nhiều associations làm tăng memory, thời gian mapping entity và thời gian transaction.
- Dữ liệu không cần thiết vẫn được đọc, kể cả màn hình chỉ dùng vài cột.
- Các mối quan hệ khác nhau có cardinality và vòng đời khác nhau, không nên có một chiến lược chung.

Vì thế, kỹ năng quan trọng không phải “hễ thấy N+1 thì thêm `fetch join`”, mà là:

> **Thiết kế kế hoạch đọc theo từng use case:** xác định response cần trường nào, cần bao nhiêu bản ghi, có phân trang không, dữ liệu có cần sửa trong transaction không, association nào có cardinality lớn, rồi chọn fetch join, entity graph, DTO projection, batch fetching hoặc nhiều truy vấn có kiểm soát.

Bài này thuộc chương **Hiệu năng** của module *Data Persistence Relational Access ORM JPA*. Các ví dụ dùng Jakarta Persistence, JPQL, Spring Data JPA và một số extension Hibernate được đánh dấu rõ. Trọng tâm là **tránh N+1 mà vẫn giữ SQL, phân trang, bộ nhớ và tính đúng đắn nghiệp vụ trong tầm kiểm soát**.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích N+1 query và cách nhận diện từ SQL log, statistics, trace.
2. Phân biệt N+1 do `@ManyToOne`, `@OneToOne`, `@OneToMany` và nested associations.
3. Hiểu `LAZY`/`EAGER` là mapping fetch behavior, không phải đầy đủ kế hoạch đọc cho từng use case.
4. Dùng JPQL `JOIN FETCH` đúng cho single entity detail, to-one relationships và collections được kiểm soát.
5. Biết vì sao fetch join collection kết hợp `setFirstResult`/`setMaxResults` rất nguy hiểm.
6. Thiết kế **phân trang hai bước: lấy IDs → fetch graph cho chính những IDs đó**.
7. Dùng `EntityGraph` với `fetchgraph`/`loadgraph` hoặc Spring Data `@EntityGraph`.
8. Dùng DTO/record projections để tránh hydrate nguyên entity khi chỉ cần một bảng danh sách.
9. Hiểu batch fetching/`@BatchSize`/`FetchMode.SUBSELECT` là các chiến lược provider-specific.
10. Phân tích row multiplication, Cartesian product và nhiều collection fetch.
11. Giải quyết N+1 trong nested collections, mapping từ entity sang DTO và JSON serialization.
12. Thiết kế kế hoạch riêng cho list, detail, search, export, background job và write workflow.
13. Đánh giá tác động của cache, transaction, isolation, tenant filtering và authorization.
14. Đo số SQL statements, round-trips, số dòng thực tế, latency, memory và query plan.
15. Viết regression tests ngăn N+1 quay trở lại khi thêm field vào API.

## 2. N+1 thực chất là gì?

Cách đếm đơn giản:

```text
1 query:       SELECT danh sách 40 orders
40 queries:    SELECT customer theo từng order
---------------------------------------------
41 SQL queries
```

N+1 là **một mẫu truy cập dữ liệu**, không phải một câu SQL cụ thể. Cùng một entity model có thể có N+1 ở một endpoint nhưng hoàn toàn không có ở endpoint khác.

### 2.1. N không nhất thiết bằng số entity rows

Giả sử 40 orders thuộc 5 customers. Nếu customers đã được quản lý trong cùng persistence context, provider có thể chỉ tải 5 customers thay vì 40. Nếu L2 cache có các customers, còn có thể ít SQL hơn.

Vì vậy, số queries thực tế phụ thuộc **distinct association keys, L1/L2 cache, mapping, provider và đường đi của code**.

### 2.2. N+1 có thể là nested N+M+1

```text
Order list:         1 query
Order.customer:    40 queries
Order.lines:       40 queries
Each Line.product: 100 queries
--------------------------------
Possible total:    181 queries
```

Số lượng trên chỉ minh họa; provider có thể tái sử dụng managed Product, dùng batch fetching hoặc cache. Nhưng cấu trúc vòng lặp cho thấy **điểm có nguy cơ mở rộng cùng số orders/lines**.

### 2.3. N+1 không chỉ ở code repository

Nó có thể xuất hiện trong:

- Mapper chuyển entity sang response DTO.
- JSON serializer gọi getters.
- Template engine render view.
- GraphQL resolver đọc associations từng object.
- Logger/`toString()` hoặc debug inspection.
- Authorization logic truy cập relation.
- Business rule lặp lại trên collections.
- Background export tạo CSV/PDF.

### 2.4. N+1 có luôn nghiêm trọng không?

Không phải mọi trường hợp tải thêm một association đều là lỗi hiệu năng nghiêm trọng. Nếu một detail screen chỉ đọc một Order và một Customer, 2 queries có thể phù hợp.

Vấn đề là **số round-trips tăng tỷ lệ với số rows** mà use case cho phép tải, đặc biệt khi network latency, connection pool và database load lớn.

---

## 3. Mô hình dữ liệu sử dụng xuyên suốt

Ứng dụng bán hàng có:

```text
Customer (1) -------- (N) SalesOrder
                            |
                            | (1)
                            |
                            v
                      (N) OrderLine
                            |
                            | (N) -------- (1) Product
```

Một Order:

- Thuộc một Customer.
- Có nhiều OrderLines.
- Mỗi OrderLine tham chiếu một Product.
- Chứa summary fields như tổng tiền và trạng thái.

### 3.1. Schema SQL minh họa

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    customer_name VARCHAR(200) NOT NULL
);

CREATE TABLE product (
    product_id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    sku VARCHAR(80) NOT NULL,
    product_name VARCHAR(200) NOT NULL
);

CREATE TABLE sales_order (
    order_id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    customer_id BIGINT NOT NULL,
    order_status VARCHAR(32) NOT NULL,
    total_amount DECIMAL(16, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    row_version BIGINT NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(customer_id)
);

CREATE TABLE order_line (
    line_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(16, 2) NOT NULL,
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id)
        REFERENCES sales_order(order_id),
    CONSTRAINT fk_line_product
        FOREIGN KEY (product_id)
        REFERENCES product(product_id)
);

CREATE INDEX idx_order_tenant_created
ON sales_order(tenant_id, created_at, order_id);

CREATE INDEX idx_line_order
ON order_line(order_id);
```

SQL chỉ mô tả mô hình ví dụ. Cú pháp/precision/index strategy cần phù hợp database dùng thật; không sao chép DDL này thành một production migration mà chưa review.

### 3.2. Entities: Customer và Product

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @Column(name = "customer_id")
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "customer_name", nullable = false)
    private String name;

    protected Customer() {
    }

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

```java
@Entity
@Table(name = "product")
public class Product {

    @Id
    @Column(name = "product_id")
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Column(name = "product_name", nullable = false)
    private String name;

    protected Product() {
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
}
```

### 3.3. SalesOrder

```java
@Entity
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    @Column(name = "order_id")
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "customer_id",
        nullable = false
    )
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected SalesOrder() {
    }

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public Customer getCustomer() { return customer; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public Instant getCreatedAt() { return createdAt; }
    public List<OrderLine> getLines() { return lines; }
}
```

### 3.4. OrderLine

```java
@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @Column(name = "line_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private SalesOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false)
    private BigDecimal unitPrice;

    protected OrderLine() {
    }

    public Long getId() { return id; }
    public Product getProduct() { return product; }
    public int getQuantity() { return quantity; }
    public BigDecimal getUnitPrice() { return unitPrice; }
}
```

Enum ví dụ:

```java
public enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}
```

Các snippets dùng imports `java.time.Instant`, `java.math.BigDecimal`, `java.util.List`/`ArrayList` tương ứng. Demo tập trung truy vấn; code tạo entity/transaction và migrations ở ứng dụng thật phải hoàn chỉnh thêm.

### 3.5. Vì sao chủ động dùng LAZY cho to-one?

`@ManyToOne` mặc định là `EAGER` theo JPA. Nếu không khai báo `LAZY`, việc load danh sách Orders có thể kéo Customers theo nhiều cách, kể cả secondary SELECT, tạo số SQL lớn. Đặt LAZY thể hiện rằng **không buộc tải Customer ở mọi use case**, sau đó quyết định ở query cụ thể có cần đọc nó hay không.

`LAZY` là chiến lược trì hoãn/khuyến nghị đối với một số mappings; provider và runtime enhancement có thể ảnh hưởng khả năng lazy load thực tế. Không suy luận rằng chỉ cần thêm LAZY thì N+1 tự biến mất.

---

## 4. Ba trường hợp sử dụng, ba kế hoạch đọc khác nhau

Xét ba màn hình cùng dùng SalesOrder:

| Use case | Dữ liệu thật sự cần | Quy mô | Hướng phù hợp |
|---|---|---|---|
| **Danh sách đơn hàng** | Order ID, status, total, createdAt, customer name | 20–100 orders mỗi trang | DTO projection với join to-one |
| **Chi tiết một đơn hàng** | Order, Customer, tất cả Lines và tên Product | 1 Order, số lines có kiểm soát | Fetch join/EntityGraph hoặc 2 truy vấn |
| **Xuất báo cáo** | Hàng chục nghìn rows và vài columns | Nhiều dữ liệu | DTO/stream/chunks, không hydrate toàn entity graph |

Nếu ép cả ba dùng repository `findAll()` rồi map entities, rất dễ bị N+1 hoặc over-fetch.

### 4.1. Hỏi rõ response contract

Trước khi chọn query, ghi ra:

```text
GET /orders:
  id, customerName, status, total, createdAt

GET /orders/{id}:
  id, customer details, status, total,
  lines[].{productId, sku, productName, qty, unitPrice}

POST /orders/{id}/ship:
  current status, version, authorization, transition rules
```

Trang list **không cần collection Lines**. Trang detail cần Lines nhưng chỉ một Order. Write workflow cần managed entity để thay đổi state và xử lý concurrency; không nên dùng cùng DTO projection như read-only list.

### 4.2. Đơn vị thiết kế không phải chỉ entity class

Một entity có thể tham gia nhiều flows với yêu cầu dữ liệu khác nhau. Vì vậy “fetch strategy của SalesOrder” không có một đáp án tối ưu chung.

---

## 5. N+1 thường ẩn ở mapper hơn là repository

Repository:

```java
public List<SalesOrder> findRecentOrders(String tenant) {
    return em.createQuery(
        """
        select o
        from SalesOrder o
        where o.tenantId = :tenant
        order by o.createdAt desc, o.id desc
        """,
        SalesOrder.class
    )
    .setParameter("tenant", tenant)
    .setMaxResults(50)
    .getResultList();
}
```

Mapper:

```java
List<OrderListRow> rows = orders.stream()
    .map(o -> new OrderListRow(
        o.getId(),
        o.getCustomer().getName(),
        o.getStatus(),
        o.getTotalAmount(),
        o.getCreatedAt()
    ))
    .toList();
```

Chính `o.getCustomer().getName()` tạo rủi ro secondary queries. Khi mapper được gọi trong transaction, lazy loading chạy “thành công” nhưng tốn SQL. Khi mapper chạy sau khi EntityManager đóng, có thể gặp exception lazy initialization của provider.

### 5.1. Vì sao test nhỏ không thấy?

Nếu fixture chỉ có 2 Orders và 1 Customer, có thể chỉ phát sinh 2 SELECT. Production có 100 Orders với 100 Customers mới lộ 101 SELECT.

### 5.2. Mở persistence context xuyên web view không giải quyết N+1

Một cấu hình như Open Session/EntityManager in View (OSIV) có thể cho phép lazy loads trong serializer; nó không làm vòng lặp trở nên hiệu quả. Thậm chí có thể gây nhiều SQL ngoài transaction service rõ ràng.

### 5.3. Các dòng log cũng có thể kích hoạt lazy loading

Tránh `toString()` tự động in toàn graph. `log.debug("Order: {}", order)` có thể khiến Lombok-generated `toString` truy cập `customer`/`lines` tùy code, làm tăng SQL ngoài chủ đích.

---

## 6. Cách phát hiện N+1 bằng SQL log

Trong môi trường phát triển, bật logging phù hợp với provider để xem các SQL queries được phát.

Ví dụ Hibernate/Spring config mang tính minh họa:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
```

Bind-parameter logging có tên category phụ thuộc Hibernate version và có thể chứa dữ liệu nhạy cảm. Chỉ bật có kiểm soát ở dev/test.

### 6.1. Mẫu SQL đáng nghi

```text
SELECT ... FROM sales_order WHERE tenant_id = ?
SELECT ... FROM customer WHERE customer_id = ?
SELECT ... FROM customer WHERE customer_id = ?
SELECT ... FROM customer WHERE customer_id = ?
...
```

Nếu số SELECT customer tăng cùng số Order trả về, rất đáng nghi.

### 6.2. Đếm truy vấn chưa đủ

Một query join quá lớn có thể tệ hơn 5 queries nhỏ. Cần đo:

- Query count và DB round-trips.
- Dữ liệu đọc từ DB (rows, bytes).
- Latency p50/p95/p99.
- CPU và memory của Java khi hydrate entities.
- Database CPU/I/O và execution plan.
- Connection pool time/wait.
- Object allocations/GC.

### 6.3. Thử với dataset đủ lớn

Một test 1 Order/1 Line không phát hiện bùng nổ 1+N. Seed 30–100 Orders, nhiều Customers, nhiều Lines, một số Product trùng để quan sát cache hiệu ứng.

### 6.4. Không dùng log từ context đã warm để kết luận

L1/L2 cache có thể che số SQL. Khi đo query behavior, kiểm soát persistence context và cache configuration. Không nhất thiết tắt mọi cache trong production, nhưng cần biết số đo đến từ điều kiện nào.

---

## 7. Giải pháp thứ nhất: JPQL JOIN FETCH cho to-one

Khi cần managed Orders và luôn dùng Customer trong cùng use case:

```java
List<SalesOrder> orders = em.createQuery(
    """
    select o
    from SalesOrder o
    join fetch o.customer
    where o.tenantId = :tenant
    order by o.createdAt desc, o.id desc
    """,
    SalesOrder.class
)
.setParameter("tenant", authorizedTenant)
.setMaxResults(50)
.getResultList();
```

Với association `customer` bắt buộc, `join fetch` có thể tạo SQL join để tải Order và Customer trong cùng truy vấn, tránh từng `SELECT customer WHERE id=?` khi sau đó đọc `getCustomer().getName()`.

### 7.1. Join fetch khác join thông thường

```jpql
select o
from SalesOrder o
join o.customer c
where c.name like :prefix
```

`join o.customer c` phục vụ predicate/query path; **không tự bảo đảm Customer entity đã được fetch đầy đủ** cho use case.

```jpql
select o
from SalesOrder o
join fetch o.customer
where o.tenantId = :tenant
```

`join fetch` chỉ thị association được tải cùng owner theo fetch-join semantics.

### 7.2. Inner vs left fetch join

Nếu relation optional và muốn giữ Orders không có Customer:

```jpql
select o
from SalesOrder o
left join fetch o.customer
where o.tenantId = :tenant
```

`join fetch` là inner join, có thể loại bỏ owners không có relationship. Trong demo `customer` là required nên inner join có thể phù hợp.

### 7.3. To-one join thường không nhân số dòng parent

Một SalesOrder có tối đa một Customer; join to-one thông thường không nhân mỗi Order thành nhiều rows. Vì vậy **phân trang với chỉ to-one fetch joins** thường an toàn hơn trường hợp fetch join to-many collection.

Vẫn cần kiểm tra các trường hợp inheritance/joins/filters cụ thể và query execution plan.

### 7.4. Khi nào nên dùng?

- Service logic cần managed Order và Customer.
- Page list cần Entity làm input cho domain processing.
- Order detail hoặc batch nhỏ với vài to-one associations.

Nếu trang list chỉ cần DTO, projection có thể còn hiệu quả hơn vì không cần hydrate hai managed entities.

---

## 8. Giải pháp thứ hai: DTO projection cho danh sách

Một Order list chỉ cần 5 fields. Thay vì lấy `SalesOrder` rồi lấy `Customer` từ lazy association, có thể **chọn đúng columns cần hiển thị**.

DTO:

```java
package com.example.shop.api;

public record OrderListRow(
    Long id,
    String customerName,
    OrderStatus status,
    BigDecimal total,
    Instant createdAt
) {
}
```

JPQL:

```java
List<OrderListRow> rows = em.createQuery(
    """
    select new com.example.shop.api.OrderListRow(
        o.id,
        c.name,
        o.status,
        o.totalAmount,
        o.createdAt
    )
    from SalesOrder o
    join o.customer c
    where o.tenantId = :tenant
    order by o.createdAt desc, o.id desc
    """,
    OrderListRow.class
)
.setParameter("tenant", authorizedTenant)
.setMaxResults(50)
.getResultList();
```

### 8.1. Không hydrate toàn entity graph

Query có thể đọc trực tiếp selected scalar fields qua join; không tạo managed Order+Customer objects theo cùng cách entity result query. Dùng DTO phù hợp cho read-only responses.

### 8.2. Vẫn cần join, nhưng không phải fetch join

`join o.customer c` là đủ khi chỉ cần `c.name` trong projection. Viết `join fetch` ở DTO query thường không phù hợp vì fetch join hướng đến association của entity được trả về.

### 8.3. Record constructor phải khớp

JPQL constructor expression yêu cầu fully qualified type và constructor signature phù hợp select expressions. Với Java record, canonical constructor thường đáp ứng nếu types đúng.

### 8.4. Khi nào DTO tốt hơn entity graph?

- Search results.
- Admin lists.
- Read-only dashboards.
- API trả subset fields.
- Export có cấu trúc cố định.
- Màn hình cần dữ liệu từ nhiều entities nhưng không chỉnh sửa chúng.

### 8.5. Khi nào không dùng DTO?

Nếu service cần thay đổi aggregate state dưới transaction và dựa vào dirty checking, managed entity có thể thích hợp hơn. Không dùng một DTO rồi tưởng JPA tự phát hiện thay đổi trên DTO.

---

## 9. DTO projection có giúp phân trang không?

Có. Khi query chỉ join to-one và chọn scalar fields theo từng Order, có thể phân trang ở database:

```java
List<OrderListRow> page = em.createQuery(
    """
    select new com.example.shop.api.OrderListRow(
        o.id,
        c.name,
        o.status,
        o.totalAmount,
        o.createdAt
    )
    from SalesOrder o
    join o.customer c
    where o.tenantId = :tenant
    order by o.createdAt desc, o.id desc
    """,
    OrderListRow.class
)
.setParameter("tenant", tenant)
.setFirstResult(pageIndex * pageSize)
.setMaxResults(pageSize)
.getResultList();
```

### 9.1. Sắp xếp ổn định

`order by createdAt desc` không đủ nếu nhiều Orders có cùng createdAt. Thêm `id desc` làm tie-breaker giúp thứ tự ổn định hơn:

```jpql
order by o.createdAt desc, o.id desc
```

### 9.2. Offset pagination có chi phí khi page sâu

OFFSET lớn có thể yêu cầu DB scan/sort nhiều rows trước khi trả page. Với feed dài, cân nhắc keyset/cursor pagination.

### 9.3. Count query riêng

Để trả total elements:

```java
Long count = em.createQuery(
    """
    select count(o)
    from SalesOrder o
    where o.tenantId = :tenant
    """,
    Long.class
)
.setParameter("tenant", tenant)
.getSingleResult();
```

Count không nên fetch join Customer/Lines chỉ để đếm. Nếu search có filters, count phải dùng cùng filter semantics.

### 9.4. Đừng “tối ưu count” bằng cách đếm rows sau join collection

Join to-many có thể nhân rows, khiến `count(o)` không còn tương đương số distinct orders. Cần count distinct hoặc truy vấn theo parent predicate phù hợp khi joins là bắt buộc.

---

## 10. Giải pháp thứ ba: fetch join collection cho chi tiết một Order

Khi endpoint chỉ load **một Order** và cần tất cả Lines:

```java
SalesOrder order = em.createQuery(
    """
    select distinct o
    from SalesOrder o
    left join fetch o.customer
    left join fetch o.lines
    where o.id = :id
      and o.tenantId = :tenant
    """,
    SalesOrder.class
)
.setParameter("id", orderId)
.setParameter("tenant", authorizedTenant)
.getSingleResult();
```

Một SQL join có thể trả:

```text
order_id | customer_name | line_id | product_id
------------------------------------------------
42       | Alice         | 1001    | 501
42       | Alice         | 1002    | 502
42       | Alice         | 1003    | 503
```

Database có **3 rows**, nhưng JPQL trả về **một SalesOrder entity** với collection gồm 3 Lines.

### 10.1. Vì sao dùng distinct?

Join to-many làm parent xuất hiện lặp trong row set. `select distinct o` diễn đạt mong muốn một root entity trong JPQL result. Cách provider khử trùng ở memory/SQL và có cần explicit distinct ở từng Hibernate version hay không có thể khác; với portable JPQL, hiểu rõ cardinality vẫn quan trọng.

### 10.2. Query này đã giải quyết Product name chưa?

Chưa chắc. `OrderLine.product` vẫn LAZY. Nếu DTO mapper tiếp tục gọi:

```java
line.getProduct().getName()
```

có thể tạo thêm queries.

### 10.3. Fetch nested to-one nếu cần

```java
SalesOrder order = em.createQuery(
    """
    select distinct o
    from SalesOrder o
    left join fetch o.customer
    left join fetch o.lines
    left join fetch o.lines.product
    where o.id = :id
      and o.tenantId = :tenant
    """,
    SalesOrder.class
)
.setParameter("id", orderId)
.setParameter("tenant", authorizedTenant)
.getSingleResult();
```

*Lưu ý portability:* Với strict JPQL grammar, điều hướng fetch join lồng nhau thường cần một identification variable/alias cho fetched association nhưng fetch-join aliases không portable trong mọi JPQL versions; provider như Hibernate có hỗ trợ mở rộng. Vì vậy câu query nested ở trên chỉ mang tính mô hình ý tưởng và không nên được mặc định coi là JPQL portable. Cách portable/an toàn hơn là dùng **EntityGraph subgraph** hoặc **hai truy vấn** được thiết kế rõ ở các phần sau.

### 10.4. Đừng load collection khổng lồ chỉ vì detail view

Nếu một Order có 100.000 Lines, endpoint detail cần **page Lines**, không fetch toàn bộ collection. Fetch join một collection chỉ hợp lý khi cardinality được giới hạn về mặt nghiệp vụ hoặc dữ liệu.

---

## 11. Cách tải detail với hai truy vấn có kiểm soát

Nếu muốn tránh provider-specific nested fetch join syntax, một phương án rõ:

**Query 1:** Order + Customer.

```java
SalesOrder order = em.createQuery(
    """
    select o
    from SalesOrder o
    join fetch o.customer
    where o.id = :id
      and o.tenantId = :tenant
    """,
    SalesOrder.class
)
.setParameter("id", orderId)
.setParameter("tenant", authorizedTenant)
.getSingleResult();
```

**Query 2:** OrderLines + Product, trả trực tiếp rows.

```java
List<OrderLine> lines = em.createQuery(
    """
    select l
    from OrderLine l
    join fetch l.product
    where l.order.id = :orderId
      and l.order.tenantId = :tenant
    order by l.id
    """,
    OrderLine.class
)
.setParameter("orderId", orderId)
.setParameter("tenant", authorizedTenant)
.getResultList();
```

Sau đó map DTO dùng `order` và `lines`, **không gọi lại `order.getLines()` nếu điều đó sẽ kích hoạt thêm lazy-load query**.

### 11.1. Vì sao 2 queries có thể tốt hơn 1?

- Query 1 không nhân root Order theo số Lines.
- Query 2 đọc đúng Line rows và Product to-one data.
- Dễ đặt pagination trên Lines nếu số lượng rất lớn.
- Không phụ thuộc collection initialization semantics từ fetch join lớn.
- Dễ profile từng SQL.

### 11.2. Vẫn có nhất quán transaction cần cân nhắc

Hai queries ở READ COMMITTED có thể nhìn data ở hai thời điểm khác nhau nếu writer khác commit giữa chúng. Nếu business cần snapshot nhất quán, cần isolation/read model phù hợp. N+1 optimization không thay transaction semantics.

### 11.3. Đừng khởi tạo collection bằng cách đoán

Nếu response DTO chỉ cần `lines` từ Query 2, không nhất thiết phải gắn chúng vào `order.lines`. Tự chỉnh managed collection để “đánh dấu đã load” có thể gây dirty-checking/cascade effects ngoài ý muốn.

---

## 12. Fetch join collection và bài toán phân trang

Một truy vấn nguy hiểm:

```java
List<SalesOrder> page = em.createQuery(
    """
    select distinct o
    from SalesOrder o
    left join fetch o.lines
    where o.tenantId = :tenant
    order by o.createdAt desc, o.id desc
    """,
    SalesOrder.class
)
.setParameter("tenant", tenant)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
```

### 12.1. Vì sao không thể LIMIT thẳng SQL rows?

Nếu Order#1 có 15 Lines và Order#2 có 10 Lines, join result có 25 rows cho **hai Orders**. `LIMIT 20` trên SQL rows có thể cắt ngang Lines của Order#2.

JPA cần trả collections nhất quán theo fetched owners; áp database LIMIT lên joined rows không tương đương “20 Orders đầy đủ”.

### 12.2. Hậu quả phụ thuộc provider

Một số providers có thể:

- Warn và phân trang trong memory sau khi tải nhiều rows.
- Từ chối kết hợp pagination với collection fetch.
- Có cơ chế xử lý đặc biệt tùy version/dialect.
- Trả behavior khó đoán nếu truy vấn không được kiểm soát.

**Không xây correctness trên giả định collection fetch join + setMaxResults luôn phân trang DB đúng như mong muốn.**

### 12.3. Hibernate fail-fast hữu ích

Hibernate hỗ trợ cấu hình provider-specific (tên chính xác theo version):

```properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
```

Mục tiêu là chuyển một lỗi thiết kế có thể chỉ warning thành failure dễ phát hiện ở test/dev. Đây không phải Jakarta Persistence standard property.

### 12.4. Cần chiến lược khác

Đối với trang Orders có pagination và cần Lines, xem **two-step ID pagination** ở phần tiếp theo.

---

## 13. Phân trang hai bước: lấy root IDs trước, fetch associations sau

Đây là một mẫu rất quan trọng khi muốn **trang chính xác theo root entities** nhưng vẫn tránh N+1 cho collection.

### 13.1. Bước 1: page IDs

```java
List<Long> pageIds = em.createQuery(
    """
    select o.id
    from SalesOrder o
    where o.tenantId = :tenant
      and o.status = :status
    order by o.createdAt desc, o.id desc
    """,
    Long.class
)
.setParameter("tenant", tenant)
.setParameter("status", OrderStatus.PAID)
.setFirstResult(pageIndex * pageSize)
.setMaxResults(pageSize)
.getResultList();
```

Query này chỉ chọn root Order IDs, không join collection, nên database pagination áp trên **Orders** chứ không phải duplicated join rows.

### 13.2. Bước 2: fetch graph cho những IDs đó

```java
List<SalesOrder> fetched = pageIds.isEmpty()
    ? List.of()
    : em.createQuery(
        """
        select distinct o
        from SalesOrder o
        left join fetch o.customer
        left join fetch o.lines
        where o.id in :ids
          and o.tenantId = :tenant
        """,
        SalesOrder.class
    )
    .setParameter("ids", pageIds)
    .setParameter("tenant", tenant)
    .getResultList();
```

Đây là **một truy vấn SQL có scope tối đa một trang Orders**, tránh tải Lines cho toàn bộ bảng.

### 13.3. Bước 3: khôi phục thứ tự trang

SQL `IN (:ids)` **không bảo đảm giữ thứ tự của `pageIds`**. Sắp xếp ở Java:

```java
Map<Long, SalesOrder> byId = fetched.stream()
    .collect(Collectors.toMap(
        SalesOrder::getId,
        Function.identity()
    ));

List<SalesOrder> ordered = pageIds.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
```

Imports ví dụ: `java.util.*`, `java.util.function.Function`, `java.util.stream.Collectors`.

### 13.4. Tại sao có thể thiếu ID trong bước 2?

Giữa hai queries, một Order có thể bị xóa, chuyển tenant/status hoặc thay đổi vì concurrent transaction. Nếu cần đúng snapshot, dùng transaction isolation thích hợp hoặc read model/consistency strategy rõ. Đừng âm thầm giả “hai queries là atomic snapshot” dưới mọi DB isolation.

### 13.5. Với nested Product relations

Bước 2 có thể dùng entity graph với subgraph Product hoặc Query 3 lấy Products theo distinct IDs theo batch. Không bắt buộc join một graph khổng lồ nếu Lines nhiều.

### 13.6. Count query vẫn riêng

Để trả Page metadata cần:

```jpql
select count(o)
from SalesOrder o
where o.tenantId = :tenant
  and o.status = :status
```

Dùng cùng filters như bước page IDs, không dùng fetch join trong count.

---

## 14. Keyset/cursor pagination cho list lớn

Offset pagination:

```sql
OFFSET 100000 ROWS FETCH NEXT 50 ROWS ONLY
```

có thể kém hiệu quả khi page sâu. Với sorting theo `createdAt desc, id desc`, có thể dùng keyset predicate:

```java
List<Long> nextIds = em.createQuery(
    """
    select o.id
    from SalesOrder o
    where o.tenantId = :tenant
      and (
          o.createdAt < :cursorTime
          or (
              o.createdAt = :cursorTime
              and o.id < :cursorId
          )
      )
    order by o.createdAt desc, o.id desc
    """,
    Long.class
)
.setParameter("tenant", tenant)
.setParameter("cursorTime", lastCreatedAt)
.setParameter("cursorId", lastId)
.setMaxResults(pageSize)
.getResultList();
```

Với trang đầu, query bỏ cursor predicate. Sau đó lấy associations cho page IDs giống `two-step`.

### 14.1. Tie-breaker ID là bắt buộc cho ordering ổn định

Nếu chỉ dùng createdAt mà nhiều orders có timestamp giống nhau, cursor có thể bỏ sót/trùng rows.

### 14.2. Index phù hợp

Composite index theo `tenant_id, created_at, order_id` có thể giúp DB lọc/sắp xếp. Tối ưu thật phụ thuộc dialect, selectivity và actual plan.

### 14.3. Keyset không tự làm transaction nhất quán

Orders mới hoặc thay đổi timestamp/status giữa các requests có thể ảnh hưởng feed. Business cần định nghĩa cursor snapshot/cutoff và cách xử lý concurrent writes.

### 14.4. Không dùng unbounded IN list

Bước hai của two-step pagination dùng page IDs hữu hạn (ví dụ 50–100 IDs). Nếu export hàng trăm nghìn Orders, phải chunk, không tạo `IN` với hàng trăm nghìn placeholders.

---

## 15. Nhiều collection fetch join và Cartesian explosion

Giả sử Order có:

- 20 Lines.
- 15 Payments.
- 10 Comments.

Nếu cùng fetch join cả ba collections:

```jpql
select distinct o
from SalesOrder o
left join fetch o.lines
left join fetch o.payments
left join fetch o.comments
where o.id = :id
```

về mặt quan hệ, có nguy cơ tạo:

```text
20 × 15 × 10 = 3,000 SQL joined rows
```

chỉ để dựng **một Order** với 45 child objects.

### 15.1. DISTINCT không làm biến mất mọi nhân bản dữ liệu

`DISTINCT` có thể giúp root objects không lặp trong result list; nó **không nhất thiết ngăn DB phải tạo/xử lý các joined rows lớn**. Không gọi `select distinct o` là lời giải toàn diện cho Cartesian product.

### 15.2. Hibernate MultipleBagFetchException

Một số Hibernate versions/configurations có thể từ chối đồng thời fetch nhiều bag collections (ví dụ nhiều unordered `List`) và ném `MultipleBagFetchException`. Đây là hành vi **Hibernate-specific**, không phải một exception chuẩn JPA.

### 15.3. Đổi List thành Set không chữa mọi vấn đề

Dùng `Set` có thể thay collection semantics và tránh một số hạn chế bag handling, nhưng Cartesian row multiplication vẫn xảy ra. Đừng thay model domain chỉ để che vấn đề query.

### 15.4. Hướng đúng

- Fetch một collection chính.
- Đọc collection thứ hai bằng query riêng có giới hạn.
- Dùng batch/subselect fetching.
- DTO projection theo từng section.
- Tách endpoint detail nếu các collections rất lớn.

### 15.5. Cách ước lượng nhanh

Nếu mỗi root có `a` lines và `b` payments, join cả hai tạo tối đa khoảng `a × b` rows per root. Hai SQL queries riêng thường xử lý khoảng `a+b` rows cộng phần root, đôi khi rẻ hơn rất nhiều.

---

## 16. EntityGraph: định nghĩa fetch plan theo use case

Entity Graph là API chuẩn JPA cho việc chỉ định những attributes/associations muốn fetch theo từng thao tác.

### 16.1. Đặt @NamedEntityGraph trên entity

```java
@NamedEntityGraph(
    name = "SalesOrder.withCustomer",
    attributeNodes = {
        @NamedAttributeNode("customer")
    }
)
@Entity
@Table(name = "sales_order")
public class SalesOrder {
    // ...
}
```

Sau đó:

```java
EntityGraph<?> graph =
    em.getEntityGraph("SalesOrder.withCustomer");

SalesOrder order = em.find(
    SalesOrder.class,
    orderId,
    Map.of(
        "jakarta.persistence.fetchgraph",
        graph
    )
);
```

### 16.2. Graph là kế hoạch thuộc tính, không phải câu SQL cố định

Provider có quyền chọn join, secondary SELECT hoặc các cơ chế tải phù hợp với graph và mapping. Graph giúp khai báo những association cần được fetch, **không hứa chắc chỉ một SQL statement**.

### 16.3. Query-scoped graph

```java
List<SalesOrder> orders = em.createQuery(
    """
    select o
    from SalesOrder o
    where o.tenantId = :tenant
    """,
    SalesOrder.class
)
.setParameter("tenant", tenant)
.setHint(
    "jakarta.persistence.fetchgraph",
    graph
)
.getResultList();
```

### 16.4. Lợi ích so với đổi @ManyToOne thành EAGER

Cùng `SalesOrder` class, một query có thể chỉ tải root Order, query khác tải Customer, và query detail tải Lines. Không phải ép mọi use case dùng cùng EAGER graph.

---

## 17. fetchgraph và loadgraph: hiểu khác nhau

Jakarta Persistence hỗ trợ hai graph hint modes:

| Hint | Ý nghĩa chủ đạo |
|---|---|
| `jakarta.persistence.fetchgraph` | Các attributes được chỉ định trong graph được xử lý theo fetch graph; những attributes không có trong graph được xem theo lazy semantics ở phần graph áp dụng, với những ngoại lệ/chi tiết theo spec/provider |
| `jakarta.persistence.loadgraph` | Attributes trong graph được yêu cầu fetch; attributes không có trong graph giữ fetch behavior theo mapping/default |

### 17.1. fetchgraph không phải “cấm mọi extra SQL”

Provider có thể tải thêm state theo yêu cầu nội bộ/implementation và mappings. JPA graph không phải network filter cấm mọi field/relationship nằm ngoài graph trong tất cả tình huống.

### 17.2. loadgraph giúp bổ sung fetch cho một use case

Nếu mapping một association đã EAGER, `loadgraph` thường không nhằm hạ nó thành LAZY. Nó yêu cầu thêm graph attributes, còn phần còn lại theo mapping semantics.

### 17.3. Nếu muốn kiểm soát tối ưu từ đầu

Một convention thực dụng:

- To-one mà không luôn cần: `LAZY`.
- To-many: `LAZY`.
- Mỗi repository method định nghĩa fetch plan riêng.
- Dùng `fetchgraph`/DTO khi cần hạn chế over-fetch.
- Test SQL vì provider có thể phát hành secondary selects.

### 17.4. Không nhầm graph với query projection

EntityGraph vẫn trả entities và có thể hydrate nhiều columns/relations. DTO projection trả đúng shape mong muốn cho read-only use case. Đừng dùng graph cho dashboard chỉ cần 3 scalars nếu DTO đơn giản hơn.

---

## 18. EntityGraph với subgraph cho nested associations

Một Order detail cần:

```text
SalesOrder
  -> Customer
  -> Lines[]
       -> Product
```

Named graph:

```java
@NamedEntityGraph(
    name = "SalesOrder.details",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode(
            value = "lines",
            subgraph = "line-product"
        )
    },
    subgraphs = {
        @NamedSubgraph(
            name = "line-product",
            attributeNodes = {
                @NamedAttributeNode("product")
            }
        )
    }
)
@Entity
public class SalesOrder {
    // ...
}
```

### 18.1. Subgraph là nested fetch plan

Graph mô tả rằng khi tải `lines`, provider cần xem xét `product` của mỗi line theo graph semantics.

### 18.2. Không có bảo đảm một SQL

Provider có thể chọn fetch strategy khác nhau, đặc biệt với collections. Đo actual query count và rows.

### 18.3. Không áp graph lớn lên mọi list endpoint

Graph detail tốt cho Order#42 nhưng có thể quá nặng với 100 Orders. Sử dụng tên graph và repository method gắn với use case rõ.

### 18.4. Named graph là metadata của entity

Graph được đăng ký tại JPA bootstrap. Muốn linh hoạt hơn, có thể xây dynamic EntityGraph ở runtime, không cần đổi annotation cho từng tổ hợp fields.

---

## 19. Dynamic EntityGraph

Ví dụ:

```java
EntityGraph<SalesOrder> graph =
    em.createEntityGraph(SalesOrder.class);

graph.addAttributeNodes("customer");

Subgraph<OrderLine> lineGraph =
    graph.addSubgraph("lines");

lineGraph.addAttributeNodes("product");

SalesOrder result = em.find(
    SalesOrder.class,
    orderId,
    Map.of(
        "jakarta.persistence.fetchgraph",
        graph
    )
);
```

### 19.1. Khi nào dùng dynamic graph?

- Một vài kết hợp graph hiếm dùng.
- Service xây fetch plan theo use case (không để client tùy ý yêu cầu graph vô hạn).
- Tests muốn so sánh có/không fetch một association.

### 19.2. Hạn chế độ sâu và bề rộng

Không chuyển thẳng JSON `include=customer,lines,lines.product,payments,...` thành EntityGraph tùy ý không giới hạn. Người gọi có thể yêu cầu graph khổng lồ, dẫn tới quá tải.

### 19.3. Graph cũng không thay authorization

Không dùng graph làm kiểm soát quyền. Entity đã có permission boundary riêng. Nested associations có thể chứa PII; service phải chỉ trả trường người dùng được phép xem.

---

## 20. Spring Data JPA @EntityGraph

Một repository method dùng Spring Data:

```java
public interface SalesOrderRepository
        extends JpaRepository<SalesOrder, Long> {

    @EntityGraph(attributePaths = {"customer"})
    List<SalesOrder> findByTenantIdAndStatus(
        String tenantId,
        OrderStatus status
    );
}
```

### 20.1. Đặt graph ở method cụ thể

Method list chỉ cần Customer, không dùng graph Lines/Products trừ khi response thực sự cần.

### 20.2. Graph type

Spring Data JPA `@EntityGraph` cho phép định nghĩa FETCH/LOAD semantics theo annotation attributes và version. Kiểm tra cú pháp của Spring Data version dự án; đây là framework annotation, còn `jakarta.persistence.EntityGraph` là API chuẩn.

### 20.3. @EntityGraph và Page

Nếu graph chứa **collection to-many** mà repository trả `Page<SalesOrder>`, có thể gặp pagination-over-fetch issue. `@EntityGraph` không tự bảo đảm pagination root đúng với một joined collection.

### 20.4. Query methods và filters

`@EntityGraph` chỉ điều chỉnh fetch plan, không tự thêm tenant/authorization predicates. Đừng dùng `findById(id)` rồi hi vọng graph sẽ bảo vệ tenant.

### 20.5. Named query và @EntityGraph

Có thể phối hợp Spring Data query methods, `@Query` và graph; quan trọng là biết entity query nào đang chạy và count query có fetch join hay không.

---

## 21. Batch fetching: giải pháp khi không muốn một join lớn

Nếu nhiều Orders có lazy `customer` hoặc `lines`, provider có thể **gom tải nhiều associations bằng batches**, giảm N+1.

Hibernate extension:

```java
import org.hibernate.annotations.BatchSize;

@Entity
@BatchSize(size = 32)
public class Customer {
    // ...
}
```

Trên collection:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderLine> lines = new ArrayList<>();
```

### 21.1. Batch fetching hoạt động theo ý tưởng nào?

Thay vì:

```sql
SELECT ... FROM customer WHERE id = ?;
SELECT ... FROM customer WHERE id = ?;
SELECT ... FROM customer WHERE id = ?;
```

provider có thể gom:

```sql
SELECT ...
FROM customer
WHERE customer_id IN (?, ?, ?, ...);
```

Đối với collection:

```sql
SELECT ...
FROM order_line
WHERE order_id IN (?, ?, ?, ...);
```

### 21.2. Công thức ước lượng

Nếu có 100 Orders và batch size 25, tải collections có thể cần khoảng `ceil(100/25)=4` queries thay vì 100. Đây là **ước lượng lý tưởng**; query count thật phụ thuộc context state/provider/caches.

### 21.3. BatchSize không thuộc Jakarta Persistence standard

`@BatchSize` là Hibernate-specific. EclipseLink và providers khác có cơ chế tương đương với APIs/settings khác. Không viết tài liệu như thể mọi JPA provider đều nhận `org.hibernate.annotations.BatchSize`.

### 21.4. Batch size càng lớn không luôn càng tốt

Quá lớn có thể tạo SQL `IN` dài, tăng số bind parameters, vượt giới hạn dialect, tăng memory và plan cost. Thử các giá trị theo workload, ví dụ 16/32/64 thay vì “1000 là tốt nhất”.

### 21.5. Batch fetching phù hợp với gì?

- Nhiều lazy to-one entities được truy cập sau một root query.
- Một vài collections trên nhiều parents.
- Graph cần nhiều collections nhưng join tất cả gây row explosion.
- Use case có số parents hữu hạn và không yêu cầu một SQL duy nhất.

---

## 22. Hibernate default_batch_fetch_size

Có thể đặt một mức batch fetch mặc định qua Hibernate:

```properties
hibernate.default_batch_fetch_size=32
```

### 22.1. Lợi ích

Giảm nhu cầu gắn `@BatchSize` lên từng mapping khi nhiều lazy associations hưởng lợi.

### 22.2. Không thay query fetch plan

Nó giúp giảm số secondary queries khi associations được access, nhưng vẫn không có nghĩa application chỉ gửi 1 SQL hoặc chỉ đọc đúng columns cần thiết.

### 22.3. Đo sự khác biệt

Benchmark trước/sau với:

- 100 Orders/100 Customers.
- 100 Orders/500 Lines.
- Product repeats và Product distinct keys.
- L1/L2 cache on/off theo tình huống.

### 22.4. Provider/version assumptions

Property và behavior thuộc Hibernate. Kiểm tra target version, dialect, batching strategy và statistics.

---

## 23. SUBSELECT fetching cho collections

Hibernate có `@Fetch(FetchMode.SUBSELECT)` (provider extension) cho một số collection mappings.

```java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines = new ArrayList<>();
```

### 23.1. Ý tưởng

Khi cần initialize collection của một parent, provider có thể tải collections cho một nhóm parents đã được load bằng truy vấn dùng subselect/scope của owner query.

### 23.2. Vì sao nó có thể giảm N+1?

Một secondary query có thể tải Lines của nhiều Orders thay vì một query per Order.

### 23.3. Rủi ro

- Có thể load Lines cho nhiều Orders hơn use case đang hiển thị.
- Cách chọn owner scope phụ thuộc context/query/provider.
- Có thể gây memory spike với context chứa rất nhiều parents.
- Không tự giải quyết pagination/cross-collection fetch issues.

### 23.4. Khi nào cân nhắc?

Khi collection access pattern rõ ràng, owner batch vừa phải và benchmark cho thấy subselect hiệu quả. Không bật global chỉ vì log có N+1 mà chưa xem query scope.

---

## 24. JOIN FETCH, EntityGraph, batch fetch và DTO: chọn thế nào?

| Kỹ thuật | Điểm mạnh | Rủi ro chính | Phù hợp |
|---|---|---|---|
| JPQL to-one `JOIN FETCH` | Tải association cùng root query | Over-fetch nếu không cần | Small list, managed write/detail |
| Collection `JOIN FETCH` | Tải một collection trong query | Root row multiplication, pagination | Bounded single aggregate |
| EntityGraph | Khai fetch plan theo use case | Provider chọn SQL; graph lớn | Reusable entity read plans |
| DTO projection | Chỉ tải fields cần | Không managed; cần mapping DTO | Read-only lists/search/export |
| Batch fetching | Giảm nhiều secondary queries | Vendor-specific, vẫn nhiều SQL | Several lazy associations/collections |
| SUBSELECT fetching | Có thể gom collections | Fetch quá rộng/memory | Bounded group parents |
| Two-step ID paging | Page đúng root rồi fetch graph | 2+ SQL, ordering/snapshot | Paginated roots + collections |
| Explicit multiple queries | Kiểm soát từng dataset | Phải ghép DTO, consistency | Detail nhiều collections, exports |
| L2 cache | Giảm DB loads cho repeats | Staleness/invalidation | Stable reference data |
| Read model/denormalization | Phù hợp query shape đặc thù | Đồng bộ dữ liệu/ETL | Analytics/high-volume UI |

### 24.1. Không tối ưu duy nhất theo số statements

Một giant join trả 500.000 duplicated rows có thể tốn hơn 4 bounded queries trả tổng 5.000 rows.

### 24.2. Không tắt LAZY để “chữa” mọi N+1

EAGER có thể tạo join/secondary selects ngay khi user không cần association. Fetch plan theo use case thường linh hoạt hơn.

### 24.3. Không dùng EntityGraph để mô tả response shape vô hạn

Graph vẫn có thể tải full entities; với API read-only chỉ cần vài fields, DTO thường tiết kiệm memory/data transfer hơn.

---

## 25. Vấn đề khi đặt EAGER toàn cục

Một mapping:

```java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;
```

không có nghĩa mọi SELECT root Order sẽ tự động biến thành một SQL JOIN duy nhất. Provider có thể dùng secondary SELECT để thỏa EAGER fetching, nên N+1 vẫn có thể xuất hiện.

### 25.1. EAGER là nghĩa vụ tải, không phải query plan cụ thể

Khi dùng entity results, EAGER association phải được fetch theo semantics mapping, nhưng provider quyết định cách thực hiện phù hợp. Thêm EAGER không chứng minh giảm số round-trips.

### 25.2. EAGER có thể rất tốn trong list

Nếu Order có EAGER Lines và mỗi Order có 20 Lines, một list 100 Orders có thể tải 2.000 child entities dù UI không dùng chúng.

### 25.3. Khả năng override EAGER xuống LAZY bị giới hạn

Dù `fetchgraph` có semantics riêng, provider có thể vẫn fetch thêm state. Một kiến trúc dựa vào EAGER ở mapping khó điều chỉnh theo từng use case hơn.

### 25.4. Convention được khuyến nghị

Dùng LAZY cho associations không phải lúc nào cũng cần, thiết kế query-specific fetch plans, và kiểm tra SQL bằng integration tests. Tuy nhiên phải hiểu LAZY support của provider, đặc biệt với to-one/inheritance/bytecode enhancement.

---

## 26. Vấn đề khi trả thẳng JPA entities qua REST

Controller:

```java
@GetMapping("/orders")
public List<SalesOrder> getOrders() {
    return orderRepository.findRecent();
}
```

JSON serializer có thể gọi:

```text
getCustomer()
getLines()
line.getProduct()
...
```

Hậu quả:

- N+1.
- Lazy initialization exceptions.
- Cyclic serialization với bidirectional relationships.
- Lộ fields không muốn trả.
- Response size không kiểm soát.
- SQL phát sinh ngoài service layer.

### 26.1. Dùng response DTO rõ ràng

```java
public record OrderDetailResponse(
    Long id,
    String customerName,
    OrderStatus status,
    BigDecimal totalAmount,
    List<OrderLineRow> lines
) {
}
```

```java
public record OrderLineRow(
    Long id,
    String sku,
    String productName,
    int quantity,
    BigDecimal unitPrice
) {
}
```

### 26.2. Map trong transaction với kế hoạch đọc đúng

```text
Service transaction
  -> execute query/query pair
  -> map DTO from fetched state
  -> return DTO
Commit/close context
Controller serializes DTO, không lazy-load entity.
```

### 26.3. Không bật Open Session In View như giải pháp hiệu năng

OSIV có thể che LazyInitializationException bằng việc cho phép SQL muộn, nhưng không giảm round-trips và có thể làm latency/connection usage khó kiểm soát.

### 26.4. Vòng lặp DTO mapper cũng cần được profile

Nếu mapper gọi nested getters cho mỗi line, dù controller đã trả DTO, N+1 vẫn xảy ra **trong lúc mapping** nếu fetch plan chưa đủ.

---

## 27. Spring Data projections

Spring Data JPA có thể hỗ trợ interface-based projections và DTO projections.

Ví dụ interface projection:

```java
public interface OrderSummaryView {
    Long getId();
    OrderStatus getStatus();
    BigDecimal getTotalAmount();
}
```

Tùy query/repository method, framework có thể trả projection thay vì full entity.

### 27.1. Projection không phải magic no-join guarantee

Nested interface projections có thể khiến framework join hoặc hydrate dữ liệu liên quan nhiều hơn mong đợi, tùy version/query method. Kiểm tra generated SQL.

### 27.2. Explicit JPQL constructor dễ kiểm soát

Khi performance quan trọng, một `select new ...` với selected columns rõ ràng giúp reviewer thấy shape gần với SQL.

### 27.3. Dynamic projection

Spring Data có dynamic projections cho cùng method theo type được truyền, nhưng cần kiểm soát query shape và không mở quá nhiều tổ hợp response gây khó test.

### 27.4. Đọc entity để update khác projection để display

Không cố sửa fields trên projection interface/DTO rồi chờ JPA flush. Muốn ghi domain state, load entity managed và xử lý transaction/concurrency.

---

## 28. Nested DTO: hai truy vấn và ghép dữ liệu

Một dashboard có 30 Orders và hiển thị mỗi Order vài Lines. Không nhất thiết hydrate toàn entity graphs.

**Query 1:** order headers:

```java
List<OrderHeaderRow> headers = em.createQuery(
    """
    select new com.example.shop.api.OrderHeaderRow(
        o.id, o.status, o.totalAmount
    )
    from SalesOrder o
    where o.id in :ids
      and o.tenantId = :tenant
    """,
    OrderHeaderRow.class
)
.setParameter("ids", pageIds)
.setParameter("tenant", tenant)
.getResultList();
```

**Query 2:** flattened line DTO rows:

```java
List<OrderLineFlatRow> lines = em.createQuery(
    """
    select new com.example.shop.api.OrderLineFlatRow(
        o.id,
        l.id,
        p.sku,
        p.name,
        l.quantity,
        l.unitPrice
    )
    from OrderLine l
    join l.order o
    join l.product p
    where o.id in :ids
      and o.tenantId = :tenant
    order by o.id, l.id
    """,
    OrderLineFlatRow.class
)
.setParameter("ids", pageIds)
.setParameter("tenant", tenant)
.getResultList();
```

Sau đó group:

```java
Map<Long, List<OrderLineFlatRow>> linesByOrder =
    lines.stream().collect(
        Collectors.groupingBy(
            OrderLineFlatRow::orderId
        )
    );
```

### 28.1. Vì sao cách này mạnh?

- Không có managed collection proxy cần initialize.
- Query chọn đúng fields cần trả.
- Hai SQL cho cả page thay vì 1+N cho từng Order.
- Dễ kiểm soát lines ordering và grouping.

### 28.2. Vẫn cần giới hạn tổng số Lines

Nếu 30 Orders mỗi Order có 50.000 Lines, query 2 vẫn quá lớn. Hãy page Lines riêng hoặc chỉ trả summary/preview.

### 28.3. Chú ý duplicate row do join thêm associations

Nếu DTO query join nhiều to-many relations cùng lúc, vẫn có Cartesian multiplication. Projection không tự cứu một JOIN sai cardinality.

### 28.4. Records/classes cần constructor phù hợp

`OrderHeaderRow` và `OrderLineFlatRow` là DTO types do ứng dụng định nghĩa với constructor signature khớp query, chẳng hạn Java records.

---

## 29. Chỉ cần COUNT/SUM: đừng load toàn collection

Sai:

```java
int lineCount = order.getLines().size();
```

Nếu collection chưa loaded, provider có thể initialize nhiều entities chỉ để lấy size; một số extra-lazy optimizations có behavior riêng, không portable.

Nếu chỉ cần số Lines cho 50 Orders, dùng aggregate query:

```java
List<Object[]> counts = em.createQuery(
    """
    select l.order.id, count(l)
    from OrderLine l
    where l.order.id in :ids
    group by l.order.id
    """,
    Object[].class
)
.setParameter("ids", pageIds)
.getResultList();
```

### 29.1. Tránh count từng Order trong vòng lặp

Sai:

```java
for (Long id : pageIds) {
    long count = countLinesForOrder(id);
}
```

Đó cũng là một dạng N+1, dù không dùng lazy associations.

### 29.2. Truy vấn tổng hợp theo nhóm

Một query `GROUP BY l.order.id` có thể trả counts cho cả page. Map thành `Map<Long, Long>`; Orders không có Lines lấy default 0.

### 29.3. Tenant filtering

Nếu IDs không bảo đảm đến từ authorized scope hoặc có nguy cơ bị thay đổi, join/filter theo `order.tenantId` trong aggregate query. Không dựa vào client-supplied IDs đơn thuần.

### 29.4. Counter cache/denormalization

Nếu count là thông tin nóng, có thể duy trì `lineCount` trên Order/read model, nhưng cần atomic updates và reconciliation; không áp dụng chỉ vì query group hơi chậm.

---

## 30. Lọc theo children: tránh fetch toàn collection để tìm một điều kiện

Một cách kém:

```java
for (SalesOrder order : orders) {
    boolean hasExpensiveLine = order.getLines().stream()
        .anyMatch(
            l -> l.getUnitPrice().compareTo(
                new BigDecimal("1000")
            ) > 0
        );
}
```

Nếu chỉ cần tìm Orders có ít nhất một Line giá cao, dùng query predicate:

```jpql
select o
from SalesOrder o
where o.tenantId = :tenant
  and exists (
      select l.id
      from OrderLine l
      where l.order = o
        and l.unitPrice > :minPrice
  )
order by o.id
```

### 30.1. Vì sao EXISTS thường có lợi?

DB có thể áp predicate/index mà không phải load mọi child entity vào Java. Nó giữ cardinality theo Orders trong root query.

### 30.2. Đừng fetch join collection đã bị filter và coi nó đầy đủ

Một query join children theo condition có thể chỉ biểu diễn subset. Nếu cố map subset như một initialized full collection, business code có thể hiểu sai “Order chỉ có từng này Lines”.

### 30.3. Tách predicate join và fetch plan

Filter root Orders bằng EXISTS, sau đó chọn DTO/entitygraph cho dữ liệu thực sự cần hiển thị. Đừng dùng một fetch join có predicate ràng buộc collection làm cả hai nhiệm vụ nếu semantics không rõ.

---

## 31. Sorting theo field liên quan

Trang danh sách cần order by Customer.name. Có thể join to-one:

```jpql
select new com.example.shop.api.OrderListRow(
    o.id, c.name, o.status, o.totalAmount, o.createdAt
)
from SalesOrder o
join o.customer c
where o.tenantId = :tenant
order by c.name asc, o.id desc
```

### 31.1. Join để sort không bắt buộc fetch cả entity

Projection chọn `c.name` là đủ. Nếu chỉ load entity roots, một query join Customer để sort chưa chắc làm Customer association initialized.

### 31.2. Sorting theo collection field là chuyện khác

Sắp xếp Orders theo `OrderLine.product.name` mà mỗi Order có nhiều Lines đặt ra câu hỏi: lấy MIN/MAX, line đầu tiên, hay aggregate? Nếu không định nghĩa root-level sort key, join có thể nhân rows và gây pagination errors.

### 31.3. Count query phải giữ filter, không cần order

Count không cần `ORDER BY`; bỏ sorting/irrelevant joins khi chúng không ảnh hưởng filter semantics.

### 31.4. Index phù hợp

Với join/ORDER BY to-one, database có thể cần indexes trên FK và fields sort, tùy plan. Fetch strategy đúng nhưng thiếu indexes vẫn chậm.

---

## 32. Transaction boundary và N+1

Khi mapper chạy trong transaction:

```java
@Transactional(readOnly = true)
public List<OrderListRow> listOrders(String tenant) {
    // Load entities, map DTO.
}
```

Một transaction rõ giúp quản lý EntityManager scope, nhưng **không tự giảm số queries**. Nếu mapper duyệt lazy associations, vẫn có N+1.

### 32.1. @Transactional(readOnly=true) không tối ưu query shape

Nó có thể là hint/optimization theo transaction manager/provider. SQL access pattern vẫn phải được thiết kế.

### 32.2. Isolation ảnh hưởng độ nhất quán của kế hoạch nhiều queries

Two-step pagination/explicit multi-query DTO ở READ COMMITTED có thể thấy commits khác nhau giữa statements. Nếu response cần snapshot nhất quán, cân nhắc isolation/read model/versions phù hợp.

### 32.3. Transaction càng lâu, nguy cơ contention càng lớn

Không giữ transaction mở khi render template, gọi remote API hoặc stream response rất lâu mà không có chủ đích. Tách read phase và serialization/streaming phù hợp.

### 32.4. Một query không đảm bảo mọi business invariant

Một SELECT JOIN FETCH trả graph chỉ là snapshot read theo database isolation. Nếu sau đó update inventory/order trạng thái, vẫn cần optimistic/pessimistic locking và DB constraints.

---

## 33. First-level cache có làm biến mất N+1 không?

Persistence context (L1) giữ managed instances theo identity. Nếu 100 Orders cùng tham chiếu một Customer, có thể chỉ cần tải Customer một lần.

### 33.1. Đây là cải thiện tình cờ theo data distribution

Nếu tuần sau có 100 distinct Customers, query count tăng. Không thiết kế endpoint hot path dựa trên giả định customers luôn trùng ID.

### 33.2. EntityManager scope ảnh hưởng

Mỗi request/transaction có persistence context mới thường có L1 “cold”. Benchmark dùng một EM lâu, loaded mọi Customers trước, có thể cho kết luận quá lạc quan.

### 33.3. L2 cache có thể che N+1 trong warm runs

Shared L2 có thể giảm SQL to-one fetches, nhưng vẫn có overhead cache lookup/object hydration; invalidation/staleness strategy phải được hiểu.

### 33.4. Không bật L2 chỉ để sửa N+1

Nếu query plan thiếu, L2 không bảo đảm query count/latency ổn định trong cold starts, cache misses và khi dữ liệu cập nhật liên tục. Sửa access pattern trước khi dùng cache như thêm một optimization.

---

## 34. Fetch plan có ảnh hưởng tính đúng đắn domain không?

Có, nếu code vô tình coi “đã fetch” là “toàn bộ quan hệ”.

### 34.1. Partially loaded collection

Nếu query chỉ chọn ACTIVE Lines rồi gắn vào Order.lines, một domain method như `order.totalLineCount()` có thể trả kết quả sai vì collection không đại diện toàn bộ DB rows.

### 34.2. Entity graph không thay authorization

Nếu Customer chứa private fields và graph tải Customer, response DTO vẫn phải whitelist attributes. Không serialize nguyên Customer entity chỉ vì đã fetch sẵn.

### 34.3. Soft delete/tenant filters

Nếu use case chỉ muốn active Lines, cần filter semantics rõ. Đừng tưởng `JOIN FETCH` mặc định hiểu soft delete/status nếu mapping/provider filter không được cấu hình và test.

### 34.4. Version và locking

EntityGraph có thể load versioned entities; không tự kiểm tra business version của response hoặc lock row khi có concurrent write. Fetch plan và concurrency plan là hai thiết kế khác nhau.

---

## 35. Một bản thiết kế repository theo use case

Thay vì chỉ:

```java
interface SalesOrderRepository {
    List<SalesOrder> findAll();
}
```

có thể đặt methods rõ hơn:

```java
interface SalesOrderReadRepository {

    List<OrderListRow> findListRows(
        String tenant,
        OrderStatus status,
        int pageSize
    );

    Optional<OrderDetailResponse> findDetail(
        String tenant,
        long orderId
    );

    List<Long> findPageIds(
        String tenant,
        OrderStatus status,
        int offset,
        int limit
    );

    List<SalesOrder> fetchPageGraph(
        String tenant,
        List<Long> orderIds
    );
}
```

### 35.1. Tên method phản ánh expected fetch plan

`findListRows` gợi ý DTO-only, `findDetail` gợi ý complete detail response, `fetchPageGraph` nêu rõ graph fetch theo một tập IDs có hạn.

### 35.2. Repository không nhất thiết trả entities

Read repository có thể trả DTO projections. Write repository có thể ưu tiên managed aggregates. Đây là một phân tách hữu ích khi use cases khác nhau.

### 35.3. Không expose unbounded graph fetch

`fetchPageGraph(ids)` nên kiểm soát maximum IDs/tenant scope, không nhận arbitrary 100.000 IDs từ user.

### 35.4. Tests đi cùng method-level contract

Mỗi read method cần regression test: data returned, filters/authorization, SQL budget và pagination ordering.

---

## 36. Một service list dùng DTO projection hoàn chỉnh về luồng

```java
@Service
public class OrderQueryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public List<OrderListRow> listRecent(
            String authorizedTenant,
            int pageSize
    ) {
        int safeSize = Math.min(
            Math.max(pageSize, 1),
            100
        );

        return em.createQuery(
            """
            select new com.example.shop.api.OrderListRow(
                o.id,
                c.name,
                o.status,
                o.totalAmount,
                o.createdAt
            )
            from SalesOrder o
            join o.customer c
            where o.tenantId = :tenant
            order by o.createdAt desc, o.id desc
            """,
            OrderListRow.class
        )
        .setParameter("tenant", authorizedTenant)
        .setMaxResults(safeSize)
        .getResultList();
    }
}
```

### 36.1. Không có loop lazy loading

DTO được dựng từ query results; code không phải đi qua `order.getCustomer()` với từng Order.

### 36.2. Giới hạn page size

Nếu client gửi `pageSize=1000000`, API vẫn chỉ trả tối đa 100. Performance phải có budget ở cả UI và backend.

### 36.3. Authorized tenant server-side

Giá trị `authorizedTenant` phải đến từ security context/validated scope, không tin một header tùy ý. Query plan tốt không được đánh đổi data isolation.

### 36.4. Khi danh sách cần thêm customer email?

Sửa DTO/query `c.email` và kiểm tra authorization. Không chuyển nguyên Customer entity vào response chỉ để thêm một field.

---

## 37. Một service detail đọc graph có kiểm soát

```java
@Service
public class OrderDetailService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public OrderDetailResponse getDetail(
            String authorizedTenant,
            long orderId
    ) {
        SalesOrder order = em.createQuery(
            """
            select o
            from SalesOrder o
            join fetch o.customer
            where o.id = :id
              and o.tenantId = :tenant
            """,
            SalesOrder.class
        )
        .setParameter("id", orderId)
        .setParameter("tenant", authorizedTenant)
        .getSingleResult();

        List<OrderLine> lines = em.createQuery(
            """
            select l
            from OrderLine l
            join fetch l.product
            where l.order.id = :id
              and l.order.tenantId = :tenant
            order by l.id
            """,
            OrderLine.class
        )
        .setParameter("id", orderId)
        .setParameter("tenant", authorizedTenant)
        .getResultList();

        List<OrderLineRow> lineRows = lines.stream()
            .map(l -> new OrderLineRow(
                l.getId(),
                l.getProduct().getSku(),
                l.getProduct().getName(),
                l.getQuantity(),
                l.getUnitPrice()
            ))
            .toList();

        return new OrderDetailResponse(
            order.getId(),
            order.getCustomer().getName(),
            order.getStatus(),
            order.getTotalAmount(),
            lineRows
        );
    }
}
```

### 37.1. Hai queries cố định

Một query Order+Customer, một query Lines+Products: không tăng thêm một Product query cho mỗi line nếu fetch join hoạt động đúng trên target provider.

### 37.2. Nếu detail rất lớn

Thay `List<OrderLineRow>` bằng paginated Lines endpoint; Order detail trả summary/count thay vì toàn collection.

### 37.3. Không trả managed entities

Service trả DTO sau khi mapping trong transaction, tránh serializer lazy loading.

### 37.4. Exception khi không tìm được Order

`getSingleResult()` có thể ném `NoResultException`; service/controller cần map thành 404 theo policy, không trả 500. Quan trọng là authorization filter không bị bỏ.

---

## 38. Một service dùng two-step pagination

Code ý tưởng:

```java
@Transactional(readOnly = true)
public List<SalesOrder> pageWithLines(
        String tenant,
        int pageIndex,
        int pageSize
) {
    int limit = Math.min(Math.max(pageSize, 1), 100);
    int offset = Math.multiplyExact(
        Math.max(pageIndex, 0),
        limit
    );

    List<Long> ids = em.createQuery(
        """
        select o.id
        from SalesOrder o
        where o.tenantId = :tenant
        order by o.createdAt desc, o.id desc
        """,
        Long.class
    )
    .setParameter("tenant", tenant)
    .setFirstResult(offset)
    .setMaxResults(limit)
    .getResultList();

    if (ids.isEmpty()) {
        return List.of();
    }

    List<SalesOrder> fetched = em.createQuery(
        """
        select distinct o
        from SalesOrder o
        left join fetch o.customer
        left join fetch o.lines
        where o.id in :ids
          and o.tenantId = :tenant
        """,
        SalesOrder.class
    )
    .setParameter("ids", ids)
    .setParameter("tenant", tenant)
    .getResultList();

    Map<Long, SalesOrder> byId = fetched.stream()
        .collect(Collectors.toMap(
            SalesOrder::getId,
            Function.identity()
        ));

    return ids.stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .toList();
}
```

### 38.1. Code này chỉ load Order+Customer+Lines

Nếu response cần Product name, thêm fetch strategy cho Product bằng subgraph/query riêng/batch. Không mặc định Lines fetch đồng nghĩa Products fetched.

### 38.2. Dùng long cho offset nếu cần?

JPA `setFirstResult` nhận `int`. Với pagination quá sâu, chuyển sang keyset/cursor thay vì số học offset không giới hạn. `Math.multiplyExact` phát hiện overflow thay vì âm thầm wrap.

### 38.3. Không nên public return entities cho REST

Ví dụ trả entities để minh họa fetch. Production service có thể map DTO ngay trong transaction.

### 38.4. Trong cùng transaction chưa chắc cùng snapshot

READ COMMITTED có thể thấy concurrent changes giữa page IDs query và fetch graph query. Cần xác định consistency requirement và chọn isolation/lock/read model phù hợp.

---

## 39. Query count budget theo use case

Một cách biến N+1 thành regression test là định nghĩa **ngân sách SQL**:

| Use case | Dữ liệu fixture | Ngân sách gợi ý | Lưu ý |
|---|---|---|---|
| List 50 Orders + Customer names bằng DTO | 50 Orders, 50 Customers | Gần 1 SELECT + count nếu có | Không nên tăng tuyến tính theo N |
| Detail 1 Order + 30 Lines + Products | 1 Order, 30 Lines | 1–3 SELECT có kiểm soát | Tùy fetch strategy |
| Paginated Orders + Lines, 50 roots | 50 Orders, 200 Lines | 2–4 SELECT + count | Dùng two-step, batch hoặc graph |
| Summary counts cho 50 Orders | 50 Orders | 1 aggregate query | Không query count trong loop |
| Export 20.000 Orders | 20.000 Orders | Queries theo chunks | Không một EntityManager graph khổng lồ |

Các con số là **mục tiêu thiết kế ví dụ**, không phải giới hạn chuẩn JPA. Khi caching/flush/query execution khác nhau, test phải đo đúng phạm vi operation.

### 39.1. Đừng chỉ test “query count <= 1”

Với 2-phase pagination, 2 SELECT có thể tốt hơn 1 join rất lớn. Budget nên xuất phát từ shape và business target.

### 39.2. Xem xét fetch strategy của nested references

Nếu detail Query 2 fetch Line.product, số Product loads không nên tăng theo số Lines. Nếu không fetch, batch size có thể cho 2–4 queries tùy N và distinct Products.

### 39.3. Đừng dùng performance assertions quá mong manh

Exact SQL count có thể thay theo Hibernate minor version, schema checks hoặc extra flush. Giới hạn theo operation scope và regression trend có thể bền hơn.

---

## 40. Kiểm thử Hibernate statistics

Một ví dụ Hibernate-specific:

```java
SessionFactory sessionFactory =
    emf.unwrap(SessionFactory.class);

Statistics statistics =
    sessionFactory.getStatistics();

statistics.setStatisticsEnabled(true);
statistics.clear();

List<OrderListRow> rows =
    orderQueryService.listRecent("shop-a", 50);

long sqlCount =
    statistics.getPrepareStatementCount();

assertTrue(sqlCount <= 2);
```

Imports:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
```

### 40.1. Đây không phải API Jakarta Persistence portable

`SessionFactory` và `Statistics` thuộc Hibernate. Provider khác cần metrics/interceptors/test tooling tương ứng.

### 40.2. Statistics cấp factory có thể lẫn SQL của threads khác

Trong parallel tests, `SessionFactory` statistics thường tổng hợp toàn factory. Nếu test nhiều threads chạy đồng thời, assertion global count có thể không ổn định. Dùng isolated test scope hoặc per-request SQL interceptor/datasource proxy khi cần.

### 40.3. Clear persistence context khi test cold loads

`em.clear()` có thể giúp loại L1 managed instances, nhưng nếu L2 vẫn warm, query behavior có thể khác. Chọn cache state rõ trước test.

### 40.4. Chỉ reset statistics sau fixture/setup

Đừng tính SQL tạo fixtures vào budget của method đang đo.

### 40.5. Kiểm tra dữ liệu, không chỉ đếm statements

Query có thể chỉ 1 SELECT nhưng trả thiếu Lines hoặc duplicate Orders. Test phải assert đúng IDs, thứ tự, Lines count, Customer/Product fields và tenant filtering.

---

## 41. Đo SQL bằng datasource proxy và tracing

Một cách khác là instrument JDBC `DataSource` để đếm query per request/test.

### 41.1. Ưu điểm

- Không phụ thuộc trực tiếp Hibernate Statistics.
- Có thể phân loại SQL theo request/span/transaction.
- Đo thời gian JDBC và DB round-trips.
- Có thể phối hợp tracing.

### 41.2. Hạn chế

- Proxy có overhead.
- SQL executed ngoài request scope có thể bị tính nhầm.
- Prepared statements có thể reuse/execute nhiều lần.
- Connection pool và batching ảnh hưởng đếm execution vs statement preparation.

### 41.3. Thông tin hữu ích trong trace

```text
HTTP GET /orders
  DB SELECT orders + customers        12 ms
  DB SELECT lines for order #1         3 ms
  DB SELECT lines for order #2         3 ms
  ...
```

Trace cho thấy một web request phát nhiều spans DB giống nhau.

### 41.4. Bảo mật

Không đưa nguyên SQL bind parameters chứa PII/payment/token vào tracing không được kiểm soát. Logs/telemetry phải có retention/access policy.

---

## 42. Kiểm thử hồi quy khi page size tăng

Một test tốt không chỉ kiểm tra page size 2. Hãy dùng data sizes:

```text
N=1
N=10
N=50
N=100
```

Đo `queryCount(N)`.

### 42.1. Mẫu N+1

```text
N=1    -> 2 queries
N=10   -> 11 queries
N=50   -> 51 queries
N=100  -> 101 queries
```

### 42.2. Mẫu có kế hoạch đọc phù hợp

```text
N=1    -> 1–3 queries
N=10   -> 1–3 queries
N=50   -> 1–3 queries
N=100  -> 1–5 queries
```

Số thực tế tùy batch size/fetch plan. Điểm quan trọng là **không tăng gần tuyến tính một SELECT per entity**.

### 42.3. Dataset phải đa dạng

- Một Customer có nhiều Orders.
- Nhiều distinct Customers.
- Một Order không có Lines.
- Một Order có 50 Lines.
- Nhiều Lines dùng cùng Product.
- Nhiều distinct Products.
- Một hoặc nhiều relations optional nếu mapping cho phép.

### 42.4. Đừng để L2 cache che regression

Có thể chạy cold-cache scenario và warm-cache scenario riêng. Production có traffic hỗn hợp; một test warm-only có thể không phát hiện N+1 khi cache miss.

---

## 43. Indexing và query plans vẫn quan trọng

Một query:

```sql
SELECT ...
FROM sales_order o
JOIN customer c ON c.customer_id = o.customer_id
WHERE o.tenant_id = ?
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 50;
```

có thể tốt hoặc chậm tùy database statistics/indexes.

### 43.1. Các indexes thường cần xem xét

- `sales_order(tenant_id, created_at, order_id)`.
- `sales_order(customer_id)` nếu có query theo Customer.
- `order_line(order_id)` cho load Lines của Order/page.
- `order_line(product_id)` cho query theo Product nếu cần.
- PK indexes trên Customer/Product IDs.

### 43.2. Không tạo mọi index “cho chắc”

Indexes tăng write overhead, disk usage và maintenance cost. Cần xem actual EXPLAIN/ANALYZE hoặc kế hoạch thực thi tương ứng với database.

### 43.3. Query count thấp vẫn có thể chậm

Một fetch join to-many 100.000 rows có thể nhiều bytes/CPU hơn 3 queries nhỏ có indexes tốt.

### 43.4. Sắp xếp và DISTINCT có chi phí

`DISTINCT` + ORDER BY + joins có thể buộc DB sort/hash lớn. Phải quan sát execution plan, không chỉ nhìn số statements.

---

## 44. N+1 và pagination trong Spring Data Page

Một repository:

```java
Page<SalesOrder> findByTenantId(
    String tenantId,
    Pageable pageable
);
```

Có thể trả root Orders đúng page. Nhưng khi mapper gọi `order.getLines()` cho từng Order, vẫn có N+1.

### 44.1. Không sửa bằng fetch join collection trong Page một cách máy móc

`Page<SalesOrder>` thường yêu cầu page results và count query. Fetch join collection có thể gây pagination-memory fallback/exception, duplicate root complications và count query invalid.

### 44.2. Với list row đơn giản

Dùng projection query với Pageable hoặc custom query rõ ràng, không collection fetch.

### 44.3. Với page cần nested children

Sử dụng page IDs rồi query Lines/Products cho toàn page bằng batch projection, hoặc two-phase fetch graph. Ghép vào DTO và giữ order.

### 44.4. total count có thể tốn

Nếu giao diện chỉ cần “còn trang tiếp không?”, `Slice`/cursor có thể giảm nhu cầu count toàn tập. Nhưng lựa chọn phụ thuộc UX/API contract.

---

## 45. Không serialize entity graph để “tiết kiệm viết DTO”

Một vấn đề thường xuất hiện:

```java
@Entity
public class SalesOrder {
    @ManyToOne(fetch = LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines;
}
```

Nếu Jackson thấy bidirectional fields, nó có thể tiếp tục:

```text
Order -> Lines -> Order -> Lines -> ...
```

Ngoài N+1, còn cyclic serialization hoặc payload quá lớn.

### 45.1. @JsonIgnore không thay fetch planning

Bỏ một field khỏi JSON có thể giúp không traverse nó nhưng không sửa các lazy loads do mapper/business code khác thực hiện. Domain entities cũng có thể được dùng ngoài HTTP.

### 45.2. DTO contract rõ hơn

Một OrderDetailResponse chỉ có fields được phép và đã fetch, giữ API ổn định dù entity mapping thay đổi.

### 45.3. Không để client quyết định mọi nested depth

Một GraphQL/REST include parameter không giới hạn có thể gây “unbounded graph fetch”. Dùng query cost/depth budgets và normalized resolvers/batching.

---

## 46. GraphQL DataLoader và N+1

N+1 không chỉ ở REST. GraphQL resolvers có thể:

```text
orders resolver:
  load 50 Orders

customer resolver for each Order:
  repository.findById(customerId)
  repeated 50 times
```

### 46.1. Batch-by-IDs

DataLoader pattern gom customer IDs:

```text
customer IDs = [1, 2, 3, ..., 50]
SELECT ... FROM customer WHERE id IN (...)
```

Map results trở lại đúng request keys.

### 46.2. Chú ý authorization/tenant

Batch resolver phải giữ tenant scope/security context. Không dùng một global DataLoader cache chia sẻ giữa requests/users nếu nó khiến lộ customer từ tenant khác.

### 46.3. GraphQL nested depth

Nếu client yêu cầu Orders → Lines → Products → Categories, có thể cần nhiều batch layers; kiểm soát complexity và query budgets.

### 46.4. Không bắt buộc dùng EntityGraph cho GraphQL

Có thể dùng DataLoader + DTO projections/explicit queries nếu graph phụ thuộc query shape và cost dễ quản lý hơn.

---

## 47. Background export: tránh N+1 và tránh memory explosion

Một batch export:

```java
List<SalesOrder> orders =
    repository.findAll();

for (SalesOrder order : orders) {
    writeCsvLine(
        order.getCustomer().getName(),
        order.getTotalAmount()
    );
}
```

Có thể:

- Load toàn bảng vào memory.
- Kích hoạt N+1 khi đọc Customer.
- Giữ persistence context quá lớn.
- Gây GC và out-of-memory.
- Mở transaction kéo dài.

### 47.1. Tốt hơn: chunked DTO query

Đọc từng chunk 500–2.000 rows tùy workload, chọn columns trực tiếp:

```jpql
select new com.example.shop.api.OrderExportRow(
    o.id, c.name, o.totalAmount, o.createdAt
)
from SalesOrder o
join o.customer c
where o.tenantId = :tenant
order by o.id
```

### 47.2. Keyset/cursor cho export lớn

Dùng `where o.id > :lastId order by o.id` (nếu ID monotonic phù hợp) thay vì OFFSET sâu.

### 47.3. Không giữ toàn bộ kết quả

Ghi chunk ra output/sink theo streaming contract. Cần xử lý backpressure, retry, security và transaction consistency.

### 47.4. Nếu cần snapshot report

Cần định nghĩa cutoff/snapshot ID và isolation/read model, không chỉ “đọc đến hết bảng”. Concurrent writes có thể làm records xuất hiện/biến mất giữa chunks.

### 47.5. External output không rollback cùng DB

Nếu export ghi file/cloud storage trong lúc transaction và lỗi, cần resumable/idempotent export flow. Query planning chỉ giải quyết phần data access performance.

---

## 48. Write workflow khác read-only projection

Một service chuyển trạng thái Order:

```java
@Transactional
public void shipOrder(
        long orderId,
        String tenant
) {
    SalesOrder order = em.createQuery(
        """
        select o
        from SalesOrder o
        where o.id = :id
          and o.tenantId = :tenant
        """,
        SalesOrder.class
    )
    .setParameter("id", orderId)
    .setParameter("tenant", tenant)
    .getSingleResult();

    order.ship(); // Domain method giả định, có state checks.
}
```

Nếu domain method chỉ cần `status` và `version`, không cần fetch `lines`/`customer` chỉ vì detail view cũng dùng SalesOrder.

### 48.1. N+1 ở write workflow

Nếu xử lý batch 100 Orders và `ship()` đọc Products/Lines của từng Order, cần batch query/fetch plan tương ứng. Nhưng phải cân nhắc transaction size, locks và optimistic conflicts.

### 48.2. Fetch join không thay lock

Một `join fetch` tải data, không đồng nghĩa lấy `PESSIMISTIC_WRITE` trên mọi rows liên quan. Nếu cần cập nhật inventory, phải bảo vệ invariant trong transaction.

### 48.3. Không dùng DTO để ghi trực tiếp

Projection có thể xác minh status nhưng không tự được managed. Thao tác update phải load entity/atomic DML theo đúng business contract.

### 48.4. Đọc ít hơn để giữ transaction ngắn hơn

Giảm over-fetch trong write operations có thể giảm latency và thời gian giữ DB resources. Nhưng đừng bỏ đọc dữ liệu cần thiết để kiểm tra invariant.

---

## 49. N+1 phát sinh từ entity callbacks hoặc validators

Một custom entity listener/`@PreUpdate` gọi relation:

```java
@PreUpdate
void audit() {
    String customerName = customer.getName();
    // ...
}
```

Nếu batch update 100 Orders mà mỗi callback lazy-load Customer, có thể tạo N+1 **trong flush**.

### 49.1. Tránh database-heavy callbacks

Lifecycle callbacks nên làm công việc cục bộ, dự đoán được. Không truy vấn nhiều associations hoặc external services trong flush callback.

### 49.2. Bean Validation cascading

`@Valid` trên associations có thể kéo việc traverse object graph tùy state/lazy rules. Đừng assume every cascade validation luôn fetch toàn bộ DB relations; kiểm tra provider-specific behavior.

### 49.3. Entity listeners khó thấy trong service code

Khi SQL log cho thấy queries phát sinh ở flush/commit mà service không có loop rõ ràng, kiểm tra listeners, converters, validation và provider callbacks.

### 49.4. Giải quyết ở thiết kế

Tách audit payload khỏi lazy relationships, lưu IDs/values đã có hoặc chuẩn bị dữ liệu rõ trước flush theo transaction policy.

---

## 50. Kiểm soát cache khi đo N+1

### 50.1. L1 cache

Trong một EntityManager, cùng Customer ID được load rồi có thể không cần SQL lại.

### 50.2. L2 cache

Nếu provider shared cache chứa Product, lazy access có thể ít DB round-trips hơn. Nhưng cold start/cache miss vẫn có N+1 structure.

### 50.3. Query cache

Một số provider có cache kết quả query (không thuộc một portable JPA API chung). Query cache có thể ảnh hưởng số SQL root queries nhưng không tự loại secondary lazy loads.

### 50.4. Benchmark theo nhiều tình huống

- Cold L1 / cold L2.
- New EM per request / long-lived EM.
- L2 warm reference data.
- High cardinality unique customers/products.
- Large and small collections.

### 50.5. Cache không sửa cardinality explosion

L2 hit không biến một SQL join 1.000.000 duplicated rows thành join ít rows. Query design vẫn cần đánh giá row multiplication.

---

## 51. Multi-tenancy và bảo mật khi fetch

Một query to-one fetch join:

```jpql
select o
from SalesOrder o
join fetch o.customer
where o.tenantId = :authorizedTenant
```

chỉ áp tenant filter lên Order. Nếu dữ liệu bị mapping/authorization sai, có thể vẫn có foreign key trỏ Customer thuộc tenant khác.

### 51.1. Domain/DB constraints cần nhất quán

Nếu thiết kế multi-tenant shared schema, có thể cần composite FK theo tenant, validation/service rules hoặc provider tenant isolation support. Không dựa vào fetch join để tự ngăn cross-tenant references.

### 51.2. DTO trả ít fields giảm nguy cơ lộ dữ liệu

Nếu API chỉ cần Customer.name, DTO projection không hydrate/send cả email/address.

### 51.3. DataLoader/cache key phải gồm tenant scope

Với GraphQL/application-level caches, key như `Customer#42` có thể không đủ khi IDs scoped theo tenant. Cần namespace và authorization.

### 51.4. Query budget không thay security checks

Đừng bỏ tenant predicate chỉ để SQL dùng index tốt hơn. Cải thiện index/schema phù hợp để vừa bảo vệ quyền vừa đạt hiệu năng.

---

## 52. Anti-pattern: giải pháp “đơn giản” nhưng trả giá lớn

### 52.1. Đổi mọi relation sang EAGER

Có thể làm N+1 chuyển sang over-fetch/secondary queries. Không phù hợp mọi use case.

### 52.2. Join fetch tất cả to-many collections

Dễ gây Cartesian multiplication, memory spike và multiple-bag limitations.

### 52.3. Fetch join collection kèm Pageable

Có thể phân trang trong memory hoặc fail; dùng ID paging/two-step.

### 52.4. Chỉ thêm DISTINCT

Không làm DB join rows biến mất theo cách thần kỳ.

### 52.5. Dùng DTO nhưng mapper vẫn gọi lazy getters

DTO không tự ngăn N+1 nếu dựng nó bằng lặp entity associations.

### 52.6. Để JSON serializer tự chạm entity graph

Rủi ro SQL muộn, N+1, cyclic graph và data leakage.

### 52.7. Bật OSIV để “sửa” LazyInitializationException

Có thể khiến N+1 âm thầm chạy ngoài service transaction.

### 52.8. Bật L2 để che N+1

Cold-cache behavior vẫn xấu; thêm consistency cost.

### 52.9. Đặt BatchSize cực lớn

Dễ có IN list quá dài, giới hạn parameters và memory overhead.

### 52.10. Dùng subselect collection fetching cho unbounded context

Có thể kéo nhiều collections ngoài phạm vi cần hiển thị.

### 52.11. Dùng count queries trong loop

`countLines(orderId)` cho 100 Orders là 100 round-trips; group aggregate tốt hơn.

### 52.12. Đọc hết collection chỉ để gọi size()

Có thể hydrate hàng nghìn children; cân nhắc COUNT query.

### 52.13. Filter fetch join collection rồi coi nó đầy đủ

Nguy cơ business logic dùng partial collection state.

### 52.14. Pagination thiếu tie-breaker

Có thể nhận trang trùng/mất rows khi sort values bằng nhau.

### 52.15. Tin IN query giữ thứ tự IDs

SQL không bảo đảm; reorder in memory hoặc ORDER BY expression thích hợp.

### 52.16. Đo một fixture duy nhất

1 Order/1 Customer không phát hiện N+1 ở scale.

### 52.17. Chỉ đo SQL count

Một giant join có thể tệ hơn vài queries đúng scope.

### 52.18. Đưa mọi associations vào một EntityGraph global

Graph quá rộng và không phù hợp từng endpoint.

### 52.19. Dùng query entity khi chỉ cần scalar values

Over-fetch và managed object allocation không cần thiết.

### 52.20. Thay đổi domain List thành Set chỉ để tránh MultipleBagFetchException

Có thể che một provider error nhưng không giải quyết row explosion.

### 52.21. Trộn persistence contexts khi map DTO

Chuyển entities ra ngoài transaction rồi truy cập lazy associations có thể fail hoặc tạo SQL ngoài kế hoạch.

### 52.22. Dùng một EM chia sẻ nhiều threads

Không thread-safe và có thể gây lỗi state/transaction, không phải optimization.

### 52.23. Dùng fetch join như lock

Fetch plan không thay optimistic/pessimistic concurrency control.

### 52.24. Quên indexes của FK/ORDER BY

Query đúng N+1 pattern nhưng vẫn chậm vì table scan/sort.

### 52.25. Không xét database row count/transfer size

10.000 duplicated joined rows cho một Order rất tốn network và hydration.

### 52.26. Query graph bỏ tenant filter

Có thể vượt authorized scope và lộ dữ liệu.

### 52.27. Thay đổi repository method không update SQL regression tests

Endpoint có thể quay lại N+1 khi thêm trường mới.

### 52.28. Giữ EntityManager mở suốt export rất dài

Memory/persistence context lớn, transaction duration và resources khó kiểm soát.

### 52.29. Thêm field cho API bằng cách bật EAGER trên entity

Một endpoint mới có thể làm mọi endpoint cũ chậm theo.

### 52.30. Nghĩ @BatchSize là chuẩn Jakarta Persistence

Đây là extension Hibernate và cần config/test theo version.

---

## 53. Lộ trình điều tra một endpoint đang chậm

Một trình tự thực dụng:

**Bước 1 — Ghi rõ use case.** Endpoint trả gì, page size bao nhiêu, filters và permissions nào?

**Bước 2 — Lấy trace/SQL trong một request.** Đếm SELECT theo bảng và round-trips; tìm mẫu lặp `WHERE child_id=?`.

**Bước 3 — Xác định dòng Java gây lazy access.** Có thể ở mapper, serializer, listener hoặc GraphQL resolver.

**Bước 4 — Đo cardinality.** Bao nhiêu root Orders, distinct Customers, Lines/order, Products/line?

**Bước 5 — Chọn query plan đúng shape.**
- List ít fields → DTO projection.
- Detail nhỏ → fetch join/EntityGraph.
- Page roots + collection → two-step IDs.
- Nhiều collections → vài queries/batch fetch.
- Export lớn → chunked projections/keyset.

**Bước 6 — Kiểm tra correctness.** Không thiếu Lines, không duplicate roots, đúng thứ tự/trang và đúng tenant.

**Bước 7 — Đo lại trên dataset đủ lớn.** Query count, rows, bytes, latency, memory, plan.

**Bước 8 — Thêm regression test.** Assert SQL budget thích hợp cùng data shape đa dạng.

**Bước 9 — Quan sát production.** P95/P99, DB load, cache hit/miss, pool wait và anomaly sau deploy.

**Bước 10 — Tinh chỉnh.** Indexes, batch size, graph depth, page size, DB execution plans.

---

## 54. Thực hành: thiết kế fetch plan cho sáu use cases

### Use case A — Admin list 20 Orders

**Cần:** ID, status, customer name, total.

**Đề xuất:** DTO projection join Customer, không Lines. Phân trang tại DB theo createdAt/id.

**Vì sao:** Chi phí đọc gần với số rows hiển thị, không hydrate collections.

### Use case B — Detail một Order có tối đa 20 Lines

**Cần:** Order, Customer, Lines, Product names.

**Đề xuất:** Một fetch graph có kiểm soát hoặc hai queries Order+Customer và Lines+Product.

**Vì sao:** Cardinality nhỏ, dễ tránh N+1 lồng nhau.

### Use case C — List 100 Orders kèm 5 Lines preview mỗi Order

**Cần:** Paged root Orders, mỗi Order tối đa 5 Lines.

**Đề xuất:** Page Order IDs; query preview Lines bằng DB window function/native SQL hoặc read model phù hợp. Không fetch toàn bộ Lines rồi cắt ở Java nếu nhiều Lines.

**Vì sao:** “5 Lines mỗi Order” là **top-N per group**, không đơn giản là collection join fetch.

### Use case D — Export 100.000 Order headers

**Cần:** Vài scalars per Order.

**Đề xuất:** DTO projections theo chunk/keyset, không full entities.

**Vì sao:** Giảm memory và không phát N+1 với Customer.

### Use case E — Chuyển trạng thái 1 Order sang SHIPPED

**Cần:** status, version và rule checks; có thể cần ShippingInfo.

**Đề xuất:** Managed Order với đúng to-one/embedded state cần; transaction/optimistic version.

**Vì sao:** Không fetch Lines nếu không tham gia invariant.

### Use case F — GraphQL Orders → Customer → Product recommendations

**Cần:** Shape phụ thuộc query client.

**Đề xuất:** DataLoader/batch-by-IDs và query complexity budget, không cho client đòi graph vô hạn.

**Vì sao:** Query shape biến đổi và nhiều resolver layers có thể tạo nested N+1.

---

## 55. Bài tập thực hành có gợi ý

### Bài 1 — Nhận diện 1+N

Query lấy 40 Orders, sau đó đọc 40 Customers qua lazy access.

**Gợi ý:** Nếu distinct customers và cold cache, có thể khoảng 41 SELECT.

### Bài 2 — Không phải N bằng số Orders

40 Orders cùng một Customer. Có chắc 41 queries không?

**Đáp án:** Không; L1 identity map/L2 có thể giảm Customer loads.

### Bài 3 — Mapping LAZY

`@ManyToOne` mặc định có phải LAZY không?

**Đáp án:** Không; default của `@ManyToOne` là EAGER.

### Bài 4 — EAGER và SQL

Đổi `customer` thành EAGER có chắc load Orders+Customers trong một JOIN không?

**Đáp án:** Không. Provider có thể dùng secondary queries.

### Bài 5 — N+1 trong mapper

Repository chỉ có một query, mapper gọi `o.getCustomer().getName()` trong loop.

**Gợi ý:** N+1 có thể xuất hiện ở mapper thay vì repository.

### Bài 6 — N+1 trong serializer

Controller trả Entity trực tiếp.

**Gợi ý:** JSON getters có thể lazy-load, nên dùng DTO.

### Bài 7 — JOIN vs JOIN FETCH

`join o.customer c` có bắt buộc initialize Customer association không?

**Đáp án:** Không; join phục vụ query semantics, fetch join mới yêu cầu fetch.

### Bài 8 — INNER và LEFT

Orders có thể không có Customer. Dùng `join fetch` hay `left join fetch` để giữ owner?

**Gợi ý:** LEFT phù hợp với optional association.

### Bài 9 — Projection

Viết DTO gồm id, customer name, total mà không load toàn entity graph.

**Gợi ý:** `select new ... from SalesOrder o join o.customer c`.

### Bài 10 — DTO record

Vì sao constructor expression báo không tìm được constructor?

**Gợi ý:** Kiểm tra FQCN và constructor parameter types/order.

### Bài 11 — Pagination root

Page 20 Orders cần Customers nhưng không Lines.

**Gợi ý:** To-one fetch join hoặc DTO projection thường phù hợp với DB pagination.

### Bài 12 — One-to-many multiplication

Một Order có 10 Lines. SQL fetch join to-many có thể tạo bao nhiêu rows?

**Đáp án:** Có thể 10 joined rows cho Order đó.

### Bài 13 — DISTINCT

`select distinct o` có tự làm SQL không còn tạo nhiều joined rows không?

**Đáp án:** Không bảo đảm; root de-duplication khác row multiplication.

### Bài 14 — Fetch join collection + limit

Vì sao LIMIT 20 rows không tương đương 20 Orders?

**Gợi ý:** Một Order có nhiều Lines chiếm nhiều SQL rows.

### Bài 15 — Hibernate fail-on-pagination

Một property giúp phát hiện collection fetch pagination misuse?

**Gợi ý:** `hibernate.query.fail_on_pagination_over_collection_fetch=true` (Hibernate-specific).

### Bài 16 — Two-step page

Bước đầu của two-step pagination chọn gì?

**Đáp án:** Root Order IDs theo filter/order/page.

### Bài 17 — Bước thứ hai

Bước 2 chọn gì?

**Gợi ý:** Fetch associations cho chính page IDs, có tenant predicate.

### Bài 18 — IN ordering

Vì sao phải reorder bằng page ID order?

**Gợi ý:** SQL `IN` không bảo đảm thứ tự đầu vào.

### Bài 19 — Count

Có nên fetch join Lines trong count query?

**Đáp án:** Không; count theo root/filter semantics.

### Bài 20 — Keyset

Sort `createdAt desc` cần tie-breaker gì?

**Gợi ý:** `id desc` và cursor predicate theo cả hai fields.

### Bài 21 — Many collections

Order có 20 Lines và 15 Payments; join cả hai có thể có bao nhiêu rows?

**Đáp án:** Khoảng 300 rows cho một Order trước filters.

### Bài 22 — MultipleBagFetchException

Đây là API chuẩn JPA hay Hibernate-specific?

**Đáp án:** Hibernate-specific.

### Bài 23 — List vs Set

Chuyển List sang Set có chữa Cartesian multiplication không?

**Đáp án:** Không.

### Bài 24 — EntityGraph

Một graph chỉ cần Customer được khai bằng gì?

**Gợi ý:** `@NamedEntityGraph` với `@NamedAttributeNode("customer")`.

### Bài 25 — Query hint

Tên hint Jakarta fetch graph?

**Đáp án:** `jakarta.persistence.fetchgraph`.

### Bài 26 — loadgraph

Không chỉ định Lines trong loadgraph. Nó dùng behavior gì?

**Gợi ý:** Mapping/default fetch semantics cho phần ngoài graph.

### Bài 27 — Graph SQL count

EntityGraph có đảm bảo duy nhất một SQL không?

**Đáp án:** Không; provider chọn loading plan.

### Bài 28 — Subgraph

Order detail cần Line.product.

**Gợi ý:** Dùng `@NamedSubgraph` ở `lines` attribute hoặc dynamic `addSubgraph("lines")`.

### Bài 29 — Spring Data @EntityGraph

Dùng @EntityGraph chứa collection với repository Page có luôn an toàn không?

**Đáp án:** Không, cần xét collection pagination.

### Bài 30 — BatchSize

`@BatchSize` thuộc namespace nào?

**Gợi ý:** `org.hibernate.annotations.BatchSize`, extension provider.

### Bài 31 — Batch query count

100 Orders, batch size 25. Số collection queries lý tưởng khoảng bao nhiêu?

**Đáp án:** Khoảng 4, phụ thuộc provider/context state.

### Bài 32 — Batch size cực lớn

Tại sao không đặt batch size 10.000?

**Gợi ý:** IN list/parameter limits, memory và plan cost.

### Bài 33 — SUBSELECT

SUBSELECT fetching có thể có rủi ro gì?

**Gợi ý:** Load nhiều owners/collections hơn use case thực sự cần.

### Bài 34 — Count lines

Muốn số Lines cho 50 Orders, không muốn load collections.

**Gợi ý:** `GROUP BY l.order.id` cho toàn page.

### Bài 35 — Filter lines

Cần Orders có Line.unitPrice > 1000.

**Gợi ý:** `EXISTS` subquery theo root Order.

### Bài 36 — Filter fetched collection

Tại sao không filter fetch join Lines rồi coi `order.lines` là toàn bộ Lines?

**Gợi ý:** Partial collection có thể bị hiểu sai trong domain logic.

### Bài 37 — Sorting by Customer

Sort Orders theo Customer.name.

**Gợi ý:** Join to-one và order by `c.name`; không cần fetch toàn Customer nếu DTO.

### Bài 38 — Sorting by Lines

Sort Order theo Product.name của “một Line” là ambiguous?

**Gợi ý:** Định nghĩa MIN/MAX/first line hoặc aggregate sort key trước.

### Bài 39 — Transaction

`@Transactional(readOnly=true)` có tự giảm N+1 không?

**Đáp án:** Không.

### Bài 40 — Isolation

Two-step pagination ở READ COMMITTED có mặc định cùng snapshot không?

**Đáp án:** Không; cần định nghĩa consistency.

### Bài 41 — L2 cache

L2 warm làm SQL ít đi, có chứng minh query plan không có N+1 không?

**Gợi ý:** Không; cold-cache scenario có thể lộ ra.

### Bài 42 — Hibernate Statistics

Lấy số prepared statements bằng API nào?

**Gợi ý:** `SessionFactory.getStatistics().getPrepareStatementCount()`.

### Bài 43 — Parallel test metrics

Global SessionFactory statistics dùng cho parallel integration tests có ổn định không?

**Đáp án:** Không nhất thiết; metrics có thể lẫn threads khác.

### Bài 44 — Regression data sizes

Nên thử N=1 hay N=100 để phát hiện N+1?

**Gợi ý:** Cả hai và so sánh queryCount(N).

### Bài 45 — Index

OrderLines được load theo `order_id`. Cân nhắc index nào?

**Gợi ý:** `order_line(order_id)`, kiểm chứng query plan.

### Bài 46 — DTO API security

DTO chỉ chứa Customer.name. Có nên trả nguyên Customer entity vì đã fetch?

**Gợi ý:** Không; có thể lộ email/PII/fields khác.

### Bài 47 — GraphQL

GraphQL resolver load Customer từng Order gây N+1.

**Gợi ý:** DataLoader/batch fetch by IDs, scope theo request/tenant.

### Bài 48 — Export

Xuất 100.000 Orders mà `findAll` toàn entities.

**Gợi ý:** Chunked DTO projections/keyset/cursor và output streaming phù hợp.

### Bài 49 — Domain write

Service ship Order chỉ cần status/version.

**Gợi ý:** Không fetch Lines/Products nếu domain invariant không dùng.

### Bài 50 — Production incident

SQL statements đã giảm từ 100 xuống 1, nhưng p95 latency tăng.

**Gợi ý:** Kiểm tra row multiplication, bytes, sorting, execution plan và Java hydration cost.

---

## 56. Checklist triển khai

Khi xây một truy vấn JPA cho endpoint/repository method, kiểm tra:

- [ ] Đã xác định use case: list/detail/search/export/write.
- [ ] Đã liệt kê chính xác fields và associations response cần.
- [ ] Có giới hạn page size/row count không?
- [ ] Có to-one LAZY/EAGER mappings ảnh hưởng query không?
- [ ] Có to-many collections, số children/parent ước tính bao nhiêu?
- [ ] Mapper/serializer có truy cập lazy getters trong loop không?
- [ ] Có to-one `JOIN FETCH` phù hợp cho managed entity query không?
- [ ] Nếu chỉ read-only scalars, DTO projection có phù hợp hơn không?
- [ ] Nếu detail cần Lines, collection có bounded cardinality không?
- [ ] Có nested Line.product và fetch plan tương ứng không?
- [ ] Có nguy cơ Cartesian multiplication khi fetch nhiều collections không?
- [ ] Có dùng collection fetch join cùng pagination không?
- [ ] Nếu cần page + Lines, đã dùng two-step ID paging/alternative chưa?
- [ ] Bước 2 có giữ tenant/authorization predicate không?
- [ ] Có khôi phục thứ tự IDs vì IN không giữ order không?
- [ ] Count query có giữ filter và tránh over-fetch không?
- [ ] Sorting có tie-breaker ổn định không?
- [ ] Có thể dùng keyset/cursor cho page sâu không?
- [ ] EntityGraph có đúng use case và độ sâu không?
- [ ] Có phân biệt fetchgraph với loadgraph không?
- [ ] Nếu dùng `@BatchSize`/SUBSELECT đã ghi rõ Hibernate-specific chưa?
- [ ] Batch size có phù hợp dialect/IN parameter limits không?
- [ ] Filter child collections có tạo partial state nguy hiểm không?
- [ ] Query aggregate/group có tránh COUNT per row không?
- [ ] Transaction scope và isolation có phù hợp multi-query plan không?
- [ ] Có cache hoặc replica ảnh hưởng benchmark/consistency không?
- [ ] Có SQL query-count test với 20–100 roots không?
- [ ] Có assert correctness, tenant scope và ordering không?
- [ ] Có đo rows/bytes/latency/memory, không chỉ SQL count không?
- [ ] Database FK/order/filter indexes có phù hợp không?
- [ ] Có p95/p99, connection pool và database tracing ở production không?
- [ ] Có test sau khi thêm field hoặc association vào response DTO không?
- [ ] Có tránh việc serialize JPA entities trực tiếp ra API không?

## 57. Bảng tra cứu nhanh

| Nhu cầu | Cách tiếp cận |
|---|---|
| 1 + N customer SELECT | To-one `JOIN FETCH` hoặc DTO projection |
| To-one used only in list field | JPQL `select new DTO(..., c.name, ...)` |
| Need managed Order + Customer | `join fetch o.customer` |
| Need one Order + bounded Lines | Collection `join fetch o.lines` hoặc EntityGraph |
| Need Lines + Product | Subgraph, fetch Line.product, hoặc explicit query |
| Root page + collection | Page IDs rồi fetch associations cho page IDs |
| Keep page order | Reorder fetched roots theo ordered IDs |
| Avoid collection pagination issue | Không áp limit trực tiếp lên collection fetch join |
| Deep cursor list | Keyset pagination với stable tie-breaker |
| Two to-many collections | Split queries/batch, tránh Cartesian product |
| Lazy to-ones in batches | Hibernate batch fetching hoặc provider tương đương |
| Batch collections | `@BatchSize`/`default_batch_fetch_size` (Hibernate) |
| Fetch collections by owner group | `@Fetch(FetchMode.SUBSELECT)` (Hibernate) |
| Declarative per-use-case fetch | `EntityGraph` / `@NamedEntityGraph` |
| Spring repository fetch plan | Spring Data `@EntityGraph` |
| Query result only few scalars | DTO/record projection |
| COUNT children for many roots | Group aggregate query |
| Filter parents by child condition | JPQL `EXISTS` |
| Measure SQL in Hibernate | `SessionFactory.getStatistics()` |
| Measure JDBC per request | Datasource proxy/tracing |
| Prevent N+1 regressions | Query budget tests at N=10,50,100 |
| Avoid serializer lazy loads | Map DTO inside transaction |
| Reduce export memory | Chunked projection/keyset |
| Preserve tenant isolation | Authorized predicates and scoped caches |
| Diagnose one giant query slow | Count joined rows, bytes, EXPLAIN, memory |
| Fetching vs locking | Fetch plan không thay transaction/lock rules |

## 58. Tổng kết

Những điểm quan trọng nhất:

1. **N+1 là một access pattern**, thường bắt đầu từ một root query rồi phát thêm SQL theo từng entity/association được truy cập.
2. **Không phải mọi N+1 đều lộ trong repository code**: mapper, serializer, listeners, GraphQL resolvers và exports đều có thể kích hoạt.
3. **`LAZY` không tự giải quyết N+1**, còn `EAGER` không bảo đảm một SQL JOIN và có thể tạo over-fetch.
4. **To-one JOIN FETCH** thường hiệu quả khi cần managed entities và related to-one data trong cùng use case.
5. **DTO projection** thường thích hợp cho list/search/report chỉ cần vài fields, tránh hydrate toàn entity graph.
6. **Collection fetch join** phù hợp với một aggregate có bounded cardinality, nhưng có row multiplication.
7. **Không dùng pagination trực tiếp trên to-many fetch join như một mặc định an toàn**; cần two-step ID paging hoặc chiến lược tương đương.
8. **Fetch nhiều to-many collections cùng lúc có thể tạo Cartesian explosion**, dù đã dùng DISTINCT.
9. **EntityGraph giúp định nghĩa fetch plan theo use case**, nhưng không phải cam kết một SQL cụ thể; phải đo trên provider/database thật.
10. **Batch fetching/SUBSELECT** có thể giảm secondary queries khi join lớn không phù hợp, nhưng thường provider-specific.
11. **COUNT/GROUP/EXISTS queries** giúp tránh tải collections hoặc query per parent chỉ để tính một điều kiện/aggregate.
12. **L2 cache, OSIV và transaction readOnly không thay kế hoạch đọc đúng**; chúng có các trách nhiệm khác nhau.
13. **Query count không phải metric duy nhất**. Cần xem SQL rows, network bytes, latency, memory, execution plan và DB connection pool.
14. **Fetch plan không thay authorization hoặc concurrency control**; tenant predicates, transaction isolation và locking vẫn cần thiết.
15. **Regression tests phải dùng dataset đủ lớn và đa dạng**, kiểm tra cả SQL budget lẫn correctness/pagination/order.

**Kết luận:** Giảm N+1 trong JPA là quá trình **thiết kế đường đọc đúng với từng trường hợp sử dụng**, không phải bật EAGER hoặc JOIN FETCH ở mọi entity. Trang danh sách nên ưu tiên selected columns/DTO; trang chi tiết có thể dùng graph có giới hạn; trang phân trang kèm collections cần two-step hoặc batch; export nên chunk và stream. Khi SQL được đo trong điều kiện thực, fetch plans có giới hạn, transaction và authorization được giữ đúng, ứng dụng có thể giảm round-trips mà không chuyển N+1 thành vấn đề lớn hơn về memory, pagination hay tính nhất quán dữ liệu.

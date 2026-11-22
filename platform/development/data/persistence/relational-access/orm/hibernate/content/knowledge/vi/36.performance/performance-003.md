# Giảm N+1 bằng kế hoạch tải có chủ đích trong Hibernate

## 1. N+1 là gì và vì sao một vòng lặp Java có thể tạo ra hàng trăm truy vấn?

Một trang quản trị cần hiển thị 50 đơn hàng cùng tên khách hàng và tên sản phẩm trong từng dòng hàng. Repository tải danh sách đơn hàng bằng một truy vấn. Sau đó mapper đọc các quan hệ LAZY để tạo DTO:

```java
List<PurchaseOrder> orders = orderRepository.findRecentOrders();

return orders.stream()
    .map(order -> new OrderRowDto(
        order.getId(),
        order.getCustomer().getName(),
        order.getLines().stream()
            .map(line -> line.getProduct().getName())
            .toList()
    ))
    .toList();
```

Code trông gọn, nhưng các getter có thể kích hoạt truy vấn database. Nếu Hibernate phải tải từng Customer, từng collection OrderLine và từng Product riêng lẻ, số SQL statements tăng theo số bản ghi.

Đó là vấn đề **N+1 selects**:

- Một truy vấn đầu tiên lấy N entity gốc.
- Sau đó có thêm N truy vấn (hoặc nhiều nhóm truy vấn) để lấy dữ liệu liên quan.
- Khi có association lồng nhau, số truy vấn có thể tăng theo số parent và child, không chỉ theo N.

Ví dụ đơn giản:

```text
SELECT ... FROM purchase_orders;                 -- 1 query

SELECT ... FROM customers WHERE id = ?;          -- query cho Order 1
SELECT ... FROM customers WHERE id = ?;          -- query cho Order 2
SELECT ... FROM customers WHERE id = ?;          -- query cho Order 3
...
SELECT ... FROM customers WHERE id = ?;          -- query cho Order N

Tổng: 1 + N SELECT
```

N+1 không phải lỗi cú pháp hay lỗi transaction. Ứng dụng vẫn trả đúng dữ liệu, nhưng có thể phải thực hiện nhiều round trips tới database. Độ trễ mạng, connection pool, database CPU và số lượng records khiến chi phí tăng rõ rệt khi dữ liệu lớn.

**Cách giải quyết là thiết kế kế hoạch tải (fetch plan) theo use case.** Trước khi truy vấn, xác định màn hình/API cần những thuộc tính và quan hệ nào; sau đó chọn JOIN FETCH, EntityGraph, DTO projection, batch fetching, subselect fetching hoặc nhiều truy vấn có kiểm soát.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận diện N+1 ở quan hệ to-one, to-many và association lồng nhau.
2. Phân biệt fetch type LAZY/EAGER với cách Hibernate thực thi SQL.
3. Thiết kế fetch plan riêng cho trang danh sách, trang chi tiết và báo cáo.
4. Dùng HQL/JPQL JOIN FETCH và Spring Data JPA @EntityGraph.
5. Dùng DTO projection khi không cần entity graph.
6. Dùng @BatchSize, hibernate.default_batch_fetch_size và FetchMode.SUBSELECT đúng trường hợp.
7. Tránh Cartesian product, MultipleBagFetchException và phân trang sai khi fetch collection.
8. Dùng hai pha truy vấn để phân trang parent rồi tải children.
9. Đo query count bằng Hibernate Statistics và integration tests.
10. Không dựa vào OSIV, EAGER toàn cục hoặc cache để che N+1.

## 2. N+1 thường phát sinh ở đâu?

### 2.1. To-one LAZY: nhiều parent, mỗi parent một association

Entity:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    public Long getId() { return id; }
    public Customer getCustomer() { return customer; }
}
```

Query gốc:

```java
List<PurchaseOrder> orders = em.createQuery(
        "select o from PurchaseOrder o order by o.id",
        PurchaseOrder.class
    )
    .getResultList();
```

Khi chỉ gọi `order.getId()`, Hibernate không cần tải Customer. Nhưng khi gọi `order.getCustomer().getName()`, proxy có thể được khởi tạo và cần SELECT để lấy state của Customer.

Nếu 50 Orders tham chiếu 50 Customers khác nhau, có thể xuất hiện 1 query lấy Orders cộng 50 queries lấy Customers. Nếu nhiều Orders cùng tham chiếu một Customer, persistence context có thể tái sử dụng cùng entity đã load nên số query thấp hơn. Dù vậy, không nên phụ thuộc vào mức độ trùng lặp dữ liệu để có hiệu năng ổn định.

### 2.2. To-many LAZY: mỗi parent có một collection

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
```

Khi truy cập:

```java
for (PurchaseOrder order : orders) {
    int lineCount = order.getLines().size();
}
```

Hibernate có thể chạy một SELECT cho collection của từng Order. Với 50 orders, đó có thể là 1 query gốc + 50 queries collection.

Ngay cả khi không duyệt từng phần tử, các thao tác như `size()`, `iterator()`, `stream()` hoặc logging collection cũng có thể khởi tạo collection tùy cách sử dụng và provider.

### 2.3. Association lồng nhau

Ví dụ Order → OrderLine → Product:

```java
for (PurchaseOrder order : orders) {
    for (OrderLine line : order.getLines()) {
        System.out.println(line.getProduct().getName());
    }
}
```

Có thể có:

- 1 query lấy Orders.
- N queries lấy collection OrderLines.
- M queries lấy Product của các lines, trong đó M là số Product proxy cần khởi tạo và chưa có trong persistence context/cache.

Với 50 orders, mỗi order 10 lines, số SQL có thể vượt xa 51. Đây là lý do cần nhìn toàn bộ graph mà response sử dụng, không chỉ association đầu tiên.

### 2.4. EAGER cũng có thể tạo N+1

Một hiểu nhầm phổ biến: đổi association thành `FetchType.EAGER` sẽ loại bỏ N+1.

EAGER có nghĩa provider phải cung cấp association khi entity được truy xuất theo semantics mapping. Nó **không bắt buộc Hibernate phải dùng JOIN trong cùng một SQL**. Với một query root không có fetch join, Hibernate có thể tải EAGER association bằng các SELECT phụ.

Vì vậy EAGER có thể khiến query gốc cộng N truy vấn phụ, hoặc tải nhiều dữ liệu hơn use case cần. EAGER không phải chiến lược tối ưu N+1 đáng tin cậy.

## 3. FetchType LAZY/EAGER và fetch plan là hai khái niệm khác nhau

### 3.1. FetchType mô tả mặc định mapping

Các mặc định JPA thường gặp:

| Association | FetchType mặc định |
|---|---|
| @OneToMany | LAZY |
| @ManyToMany | LAZY |
| @ManyToOne | EAGER |
| @OneToOne | EAGER |

Có thể khai báo rõ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
```

Với to-one, JPA cho phép LAZY như một hint; Hibernate hỗ trợ lazy proxies/bytecode enhancement theo mapping và trường hợp cụ thể. Cần kiểm tra behavior thực tế của phiên bản và kiểu association, đặc biệt với inverse one-to-one.

### 3.2. Fetch plan mô tả dữ liệu một use case cần

Ví dụ:

- Trang danh sách: order ID, number, customer name, line count.
- Trang chi tiết: order header, customer, lines và product của từng line.
- Trang báo cáo: tổng tiền theo tháng và trạng thái.
- Trang chỉnh sửa: entity managed cùng một số association cần thay đổi.

Một mapping có thể dùng LAZY làm mặc định, nhưng mỗi use case chọn fetch plan riêng. Nhờ vậy một trang không cần Product description sẽ không kéo toàn bộ Product graph chỉ vì association từng được khai báo EAGER.

### 3.3. Không đổi mọi association thành EAGER để “chữa” N+1

Ví dụ:

```java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;

@OneToMany(fetch = FetchType.EAGER)
private List<OrderLine> lines;
```

Cách này có thể:

- Tải dữ liệu dư ở use case không cần.
- Tạo nhiều secondary selects.
- Tạo graph lớn và khó kiểm soát.
- Gây Cartesian product nếu nhiều collection cùng được join.
- Làm query count thay đổi khi thêm association mới.

Thông thường nên giữ mapping LAZY cho association và chỉ fetch những gì use case cần bằng query hoặc graph cụ thể.

### 3.4. Lazy không có nghĩa “không bao giờ tải”

LAZY có nghĩa association chưa được tải ngay tại thời điểm load entity. Khi code truy cập nó trong persistence context, Hibernate có thể tải. Nếu Session đã đóng, truy cập có thể gây `LazyInitializationException`. Nếu Session còn mở, truy cập nhiều lần có thể gây N+1.

Do đó, lazy loading là một công cụ quản lý thời điểm tải; nó không tự chọn thời điểm tối ưu cho toàn bộ use case.

## 4. Đầu tiên phải xác định dữ liệu mà response cần

Giả sử API danh sách đơn hàng trả:

```java
public record OrderListDto(
    Long id,
    String orderNumber,
    String customerName,
    long lineCount
) {}
```

Nó chỉ cần:

- Scalar fields từ PurchaseOrder.
- Một scalar từ Customer.
- Một aggregate count của OrderLine.

Không cần tải từng OrderLine entity rồi đếm trong Java. Một DTO projection với JOIN và COUNT thường là lựa chọn tốt hơn.

Ngược lại, API chi tiết trả danh sách từng line:

```java
public record OrderLineDto(
    Long id,
    String productSku,
    String productName,
    int quantity,
    BigDecimal unitPrice
) {}

public record OrderDetailDto(
    Long id,
    String orderNumber,
    String customerName,
    List<OrderLineDto> lines
) {}
```

Nó cần dữ liệu con; có thể dùng một query header và một query lines/product, hoặc fetch join cho một order duy nhất nếu kích thước collection hợp lý.

**Không nên chọn JOIN FETCH chỉ vì có thể.** Chọn theo shape của response và cardinality của quan hệ.

## 5. Cách 1 — JOIN FETCH cho association cần tải ngay

### 5.1. To-one association

HQL:

```hql
select o
from PurchaseOrder o
join fetch o.customer
where o.createdAt >= :fromTime
order by o.createdAt desc
```

Repository:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.createdAt >= :fromTime
    order by o.createdAt desc
    """)
List<PurchaseOrder> findRecentWithCustomer(
    @Param("fromTime") Instant fromTime
);
```

`join fetch o.customer` vừa tham gia lấy dữ liệu vừa yêu cầu association Customer được khởi tạo cùng kết quả Order. Khi mapper gọi `o.getCustomer().getName()`, không cần một SELECT riêng cho mỗi Order.

Nếu association có thể null và vẫn muốn giữ Order không có Customer, dùng `left join fetch`:

```hql
select o
from PurchaseOrder o
left join fetch o.customer
order by o.id
```

### 5.2. Phân biệt JOIN và JOIN FETCH

```hql
select o
from PurchaseOrder o
join o.customer c
where c.active = true
```

Query trên JOIN Customer để lọc Order, nhưng không nhất thiết khởi tạo association `o.customer` trong entity result. Nếu code sau đó đọc `o.getCustomer().getName()`, Hibernate vẫn có thể tải association riêng.

Còn:

```hql
select o
from PurchaseOrder o
join fetch o.customer
where o.customer.active = true
```

thể hiện rõ mục tiêu fetch association. Có thể dùng alias join tùy HQL/JPQL syntax, nhưng JPQL portable có giới hạn đối với alias trên fetch join; ví dụ đơn giản ở đây tránh phụ thuộc cú pháp alias không portable.

### 5.3. To-many collection

Với một trang chi tiết cho **một order** có số lines vừa phải:

```hql
select o
from PurchaseOrder o
left join fetch o.lines
where o.id = :id
```

Có thể tải Order và các OrderLine trong một SQL. Nếu mỗi line còn cần Product:

```hql
select o
from PurchaseOrder o
left join fetch o.lines l
left join fetch l.product
where o.id = :id
```

Đây là cú pháp HQL Hibernate hỗ trợ cho nested fetch join. Nếu cần tính portable JPQL giữa các provider, kiểm tra grammar của JPA và cân nhắc query tách riêng.

### 5.4. Kết quả lặp root entity

JOIN collection làm một Order xuất hiện trên nhiều SQL rows: mỗi line có một row kết hợp. Khi materialize entity result, Hibernate 6 tự loại trùng root entity trong một số fetch-join entity queries; SQL result set vẫn có nhiều rows và chi phí truyền dữ liệu vẫn tồn tại.

Không nhầm “Java list chỉ có một Order” với “database chỉ trả một row”. Hãy quan sát cả số rows, bytes và execution plan.

### 5.5. Không fetch nhiều collection lớn trong một JOIN

Nếu Order có cả:

- `lines`: 10 rows.
- `payments`: 3 rows.
- `shipments`: 4 rows.

JOIN cả ba collection có thể tạo tích Descartes lên tới 10 × 3 × 4 = 120 rows cho một Order, trước khi xét các quan hệ khác. Dữ liệu root và các collection bị lặp trên nhiều rows, làm tăng memory, network và CPU hydrate.

Nếu nhiều collection có bag semantics (ví dụ các List không có index/order column phù hợp), Hibernate có thể ném `MultipleBagFetchException` khi cố fetch nhiều bags đồng thời.

**Không đổi List thành Set chỉ để né exception.** Set vẫn có thể tạo Cartesian product và thay đổi semantics thứ tự/duplicate của domain. Hãy dùng nhiều truy vấn có kiểm soát, batch fetching hoặc DTO projections.

## 6. Cách 2 — @EntityGraph trong JPA và Spring Data

EntityGraph cho phép chỉ định association cần fetch cho một lần load, mà không phải sửa FetchType toàn cục.

### 6.1. Annotation @EntityGraph trên Spring Data repository

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer"})
    Optional<PurchaseOrder> findWithCustomerById(Long id);
}
```

Khi gọi method, Spring Data JPA yêu cầu provider tải graph gồm Customer. Hibernate quyết định cách thực thi phù hợp với mapping/query/dialect; thường có thể dùng JOIN hoặc secondary selects tùy graph và query shape.

### 6.2. Nested paths

Với Order detail cần Customer, Lines và Product của từng Line:

```java
@EntityGraph(attributePaths = {
    "customer",
    "lines",
    "lines.product"
})
Optional<PurchaseOrder> findDetailById(Long id);
```

Đây là cách khai báo graph dễ đọc cho một use case. Tuy nhiên graph lớn có thể làm SQL rộng và nhiều rows. EntityGraph **không đảm bảo đúng một SELECT** và không miễn phí.

### 6.3. NamedEntityGraph

Có thể định nghĩa graph trên entity:

```java
@Entity
@NamedEntityGraph(
    name = "PurchaseOrder.detail",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode(
            value = "lines",
            subgraph = "lines-with-product"
        )
    },
    subgraphs = {
        @NamedSubgraph(
            name = "lines-with-product",
            attributeNodes = {
                @NamedAttributeNode("product")
            }
        )
    }
)
public class PurchaseOrder {
    // ...
}
```

Repository dùng graph đã đặt tên:

```java
@EntityGraph(
    value = "PurchaseOrder.detail",
    type = EntityGraph.EntityGraphType.FETCH
)
Optional<PurchaseOrder> findById(Long id);
```

Tên method thực tế phải tránh xung đột với method kế thừa từ JpaRepository; ví dụ có thể đặt `findDetailById`. Đây là minh họa graph, cần điều chỉnh method theo repository đang có.

### 6.4. FETCH graph và LOAD graph

JPA định nghĩa hai kiểu:

- **FETCH graph:** thuộc tính được chỉ định trong graph được xem là eager cho lần operation; thuộc tính không chỉ định được xử lý như lazy theo semantics graph.
- **LOAD graph:** thuộc tính được chỉ định được eager; thuộc tính không chỉ định giữ fetch behavior mặc định trong mapping.

Hibernate có thể lựa chọn cách thực thi SQL khác nhau. Không suy luận FETCH graph luôn tạo JOIN, hoặc LOAD graph luôn dùng SELECT. Hãy đọc SQL và đo.

### 6.5. Khi nên dùng EntityGraph?

- Một method repository có fetch shape tương đối ổn định.
- Muốn tái sử dụng named graph.
- Cần giữ query method đơn giản.
- Muốn tránh thay đổi mapping EAGER toàn cục.

Với aggregate/reporting phức tạp, query DTO hoặc các truy vấn riêng có thể rõ ràng và hiệu quả hơn.

## 7. Cách 3 — DTO projection: chỉ tải đúng cột cần dùng

Nếu use case chỉ đọc dữ liệu, không cần sửa entity, DTO projection có thể tránh hydrate cả graph.

### 7.1. Constructor expression trong JPQL

DTO:

```java
public record OrderListDto(
    Long id,
    String orderNumber,
    String customerName,
    long lineCount
) {}
```

Repository:

```java
@Query("""
    select new com.example.orders.api.OrderListDto(
        o.id,
        o.orderNumber,
        c.name,
        count(l.id)
    )
    from PurchaseOrder o
    join o.customer c
    left join o.lines l
    where o.createdAt >= :fromTime
    group by o.id, o.orderNumber, c.name
    order by o.createdAt desc, o.id desc
    """)
List<OrderListDto> findOrderSummaries(
    @Param("fromTime") Instant fromTime
);
```

Hibernate chỉ cần chọn các trường và aggregate phục vụ DTO. Nó không cần tạo entity graph PurchaseOrder → Customer → OrderLine.

### 7.2. Page<DTO> cần count query đúng

Với phân trang:

```java
@Query(
    value = """
        select new com.example.orders.api.OrderListDto(
            o.id,
            o.orderNumber,
            c.name,
            count(l.id)
        )
        from PurchaseOrder o
        join o.customer c
        left join o.lines l
        where o.createdAt >= :fromTime
        group by o.id, o.orderNumber, c.name
        """,
    countQuery = """
        select count(o.id)
        from PurchaseOrder o
        where o.createdAt >= :fromTime
        """
)
Page<OrderListDto> findSummaryPage(
    @Param("fromTime") Instant fromTime,
    Pageable pageable
);
```

Count query ở đây phù hợp với giả định Customer bắt buộc và không có filter trên child. Nếu thêm filter theo lines hoặc HAVING, count query phải đếm đúng số root groups phù hợp. Không copy một count query đơn giản sang query có semantics khác.

### 7.3. DTO projection không tự tạo nested collections

Một constructor expression thường tạo một DTO cho mỗi SQL row. Nó không tự gom nhiều OrderLine rows thành một `List<OrderLineDto>` lồng trong OrderDetailDto.

Với nested DTO, có thể:

1. Lấy header DTO/ID bằng một query.
2. Lấy tất cả line DTO của tập IDs bằng một query.
3. Group lines theo order ID trong Java.
4. Compose parent DTO theo thứ tự đã lấy.

Đây thường là kế hoạch đơn giản, tránh N+1 và không hydrate entity graph.

### 7.4. Interface projection của Spring Data

```java
public interface OrderSummaryView {
    Long getId();
    String getOrderNumber();
    String getCustomerName();
}
```

Query:

```java
@Query("""
    select o.id as id,
           o.orderNumber as orderNumber,
           c.name as customerName
    from PurchaseOrder o
    join o.customer c
    where o.id = :id
    """)
Optional<OrderSummaryView> findSummary(@Param("id") Long id);
```

Interface projection tiện với scalar fields và aliases rõ ràng. Nested projection hoặc open projection dùng SpEL có thể kéo thêm associations; kiểm tra SQL thực tế và tránh giả định mọi projection đều chỉ chọn một vài cột.

### 7.5. Projection phù hợp với read model, không thay write model

DTO projection không phải entity managed. Sửa một field trong DTO không làm database update. Với use case cập nhật, thường tải entity managed, validate/mutate trong transaction, rồi tạo DTO response theo fetch plan cần thiết.

## 8. Cách 4 — Batch fetching: gom nhiều lazy loads vào một truy vấn

JOIN FETCH không phải lúc nào cũng phù hợp, đặc biệt khi nhiều root entities có collection. Hibernate hỗ trợ batch fetching để khi một lazy proxy/collection được khởi tạo, provider có thể tải **một nhóm** các keys thay vì một key.

### 8.1. Cấu hình mặc định toàn SessionFactory

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

Khi nhiều association lazy cùng loại được truy cập trong một persistence context, Hibernate có thể gom keys vào các câu SELECT dùng `IN (...)`. Giá trị 32 chỉ là ví dụ; cần benchmark theo database, số rows và workload.

### 8.2. @BatchSize trên entity

```java
import org.hibernate.annotations.BatchSize;

@Entity
@BatchSize(size = 32)
public class Customer {
    @Id
    private Long id;
    // ...
}
```

Khi một số proxy Customer đang chờ khởi tạo trong Session, Hibernate có thể tải nhiều Customer trong cùng batch.

### 8.3. @BatchSize trên collection

```java
@OneToMany(mappedBy = "order")
@BatchSize(size = 32)
private List<OrderLine> lines = new ArrayList<>();
```

Khi khởi tạo một collection, Hibernate có thể tải collection cho một nhóm owner IDs, giảm số truy vấn so với tải từng collection một.

### 8.4. Ví dụ giảm số query

Không batch:

```text
1 query: SELECT orders
50 queries: SELECT customer WHERE id = ?
Tổng khoảng 51 queries
```

Batch size 16:

```text
1 query: SELECT orders
4 queries: SELECT customer WHERE id IN (...)
Tổng khoảng 5 queries
```

Số cụ thể tùy keys đã có trong persistence context, cache, dialect, batch queue và cách truy cập. Batch fetching giảm N+1 từ tuyến tính theo từng entity xuống một số nhóm, nhưng không biến mọi use case thành một SELECT duy nhất.

### 8.5. Khi batch fetching phù hợp?

- Một danh sách parent đã được tải và code cần truy cập nhiều to-one proxies.
- Cần tải nhiều collections cùng role theo nhóm.
- JOIN collection tạo row explosion hoặc không phù hợp với query shape.
- Không muốn viết một query riêng cho từng use case nhưng vẫn có thể chấp nhận lazy access trong transaction.

### 8.6. Giới hạn batch size

Batch quá lớn có thể tạo:

- SQL với nhiều bind parameters.
- Vượt giới hạn số bind variables của database/dialect.
- Query plan kém hoặc packet lớn.
- Memory pressure do tải quá nhiều entities/collections cùng lúc.
- Tải dư nếu code chỉ truy cập vài association.

Chọn batch size bằng benchmark; 16, 32 hoặc 64 chỉ là điểm bắt đầu thường gặp, không phải giá trị tối ưu chung.

## 9. Cách 5 — SUBSELECT fetching cho collection

Hibernate có fetch mode `SUBSELECT`, hữu ích khi một query đã tải một tập parent entities và sau đó cần collection cùng role của nhiều parent.

Ví dụ:

```java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order")
    @Fetch(FetchMode.SUBSELECT)
    private List<OrderLine> lines = new ArrayList<>();
}
```

Khi collection của một parent trong tập kết quả được khởi tạo, Hibernate có thể dùng một subselect dựa trên query đã tải các owner để tải collection cho nhiều owner trong tập đó.

### 9.1. Mô hình SQL khái niệm

Query gốc:

```sql
SELECT o.id, o.order_number
FROM purchase_orders o
WHERE o.status = ?;
```

Khi cần lines, thay vì N SELECT theo từng order, Hibernate có thể phát một truy vấn collection với điều kiện owner IDs được xác định từ query gốc:

```sql
SELECT l.id, l.order_id, l.product_id, l.quantity
FROM order_lines l
WHERE l.order_id IN (
    SELECT o.id
    FROM purchase_orders o
    WHERE o.status = ?
);
```

SQL thực tế tùy Hibernate version, dialect và query shape; ví dụ trên chỉ diễn tả ý tưởng.

### 9.2. Khi nào dùng SUBSELECT?

- Một use case tải một tập parent từ cùng một query.
- Thường cần collection cùng role của nhiều parent.
- Muốn giảm số SELECT mà không join collection vào query gốc.
- Tập parent có kích thước được kiểm soát.

### 9.3. Hạn chế

- Có thể tải collection của toàn bộ parent trong tập query ban đầu khi chỉ cần một phần.
- Nếu query gốc trả rất nhiều parents, collection subselect có thể lớn.
- Không phù hợp với mọi phân trang và mọi query.
- Có thể tạo tải dư khi collection lớn hoặc chỉ một vài parent được truy cập.
- Không thay thế DTO projection cho báo cáo chỉ cần aggregate.

So sánh `@BatchSize` và `FetchMode.SUBSELECT` bằng workload thực, không chỉ số câu SQL.

## 10. Fetch profile và kế hoạch tải theo ngữ cảnh

Hibernate hỗ trợ fetch profiles để định nghĩa các association được fetch trong một profile rồi bật profile trong Session.

Ví dụ minh họa:

```java
@Entity
@FetchProfile(
    name = "order.withCustomer",
    fetchOverrides = {
        @FetchProfile.FetchOverride(
            entity = PurchaseOrder.class,
            association = "customer",
            mode = FetchMode.JOIN
        )
    }
)
public class PurchaseOrder {
    // ...
}
```

Bật trong Session:

```java
Session session = entityManager.unwrap(Session.class);
session.enableFetchProfile("order.withCustomer");

PurchaseOrder order = session.find(PurchaseOrder.class, orderId);
```

Fetch profile là Hibernate-specific. Cần xác nhận annotation/API và semantics của Hibernate version đang dùng. Với Spring Data repository đơn giản, `@EntityGraph` hoặc query-specific JOIN FETCH thường dễ nhìn thấy hơn; fetch profile hữu ích khi có một fetch policy cần tái sử dụng trong các Session operations phù hợp.

**Không bật profile toàn cục** rồi quên rằng query khác cũng chịu tác động. Hãy giới hạn profile theo use case và kiểm tra generated SQL.

## 11. Kế hoạch tải cho từng use case

### 11.1. Trang danh sách phẳng

Response cần order ID, number, customer name, line count.

**Ưu tiên:** DTO projection + JOIN/COUNT/GROUP BY.

Lý do: không cần entity graph hoặc collection. Database thực hiện aggregate, ứng dụng nhận dữ liệu đúng shape.

### 11.2. Trang chi tiết một order

Response cần order header, customer và 5–20 lines cùng Product.

**Lựa chọn:** một query header + Customer, một query lines + Product; hoặc một JOIN FETCH có kiểm soát nếu số lines nhỏ và không có nhiều collections khác.

Lý do: tránh N+1 mà vẫn kiểm soát kích thước result set.

### 11.3. Trang phân trang nhiều orders, mỗi order có lines

**Ưu tiên:** phân trang root IDs trước, sau đó tải headers và children theo tập IDs. Batch fetching có thể là lựa chọn thay thế khi thích hợp.

Tránh JOIN FETCH collection cùng Pageable trên query root vì SQL rows bị nhân theo số children.

### 11.4. Báo cáo tổng hợp

**Ưu tiên:** DTO projection với COUNT/SUM/AVG/GROUP BY hoặc read model/materialized view phù hợp. Không tải hàng nghìn entities rồi duyệt collection để tính tổng trong Java nếu database có thể làm việc đó hiệu quả hơn.

### 11.5. Use case cập nhật

Tải entity managed cùng association thực sự cần để validate/mutate. Đừng fetch toàn bộ graph chỉ để thay một scalar field. Khi tạo response, chỉ fetch thêm dữ liệu cần hoặc dùng projection sau write nếu cần.

## 12. JOIN FETCH collection và pagination: vì sao nguy hiểm?

Giả sử có 20 orders mỗi order 10 lines. SQL join trả khoảng 200 rows. Khi database áp `LIMIT 20`, nó giới hạn **rows sau JOIN**, không phải 20 Order objects.

Kết quả có thể chỉ chứa vài orders đầu tiên và collection chưa đầy đủ. Hibernate có thể phải bỏ giới hạn SQL và phân trang trong memory để bảo đảm semantics, gây tải toàn bộ result set rồi mới cắt page.

### 12.1. Cấu hình cảnh báo/fail sớm

Trong Hibernate 6, có thể bật:

```properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
```

Cấu hình này giúp fail khi phát hiện pagination trên query có collection fetch trong các trường hợp Hibernate hỗ trợ phát hiện, thay vì âm thầm thực hiện in-memory pagination.

### 12.2. Hai pha: page parent IDs rồi tải dữ liệu liên quan

Pha 1 lấy ID theo thứ tự ổn định:

```java
@Query("""
    select o.id
    from PurchaseOrder o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Long> findPageIds(
    @Param("status") OrderStatus status,
    Pageable pageable
);
```

Pha 2 lấy headers cùng Customer:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.id in :ids
    """)
List<PurchaseOrder> findHeadersWithCustomer(
    @Param("ids") Collection<Long> ids
);
```

Pha 3 lấy lines cùng Product:

```java
@Query("""
    select l
    from OrderLine l
    join fetch l.product
    where l.order.id in :ids
    order by l.order.id, l.id
    """)
List<OrderLine> findLinesWithProduct(
    @Param("ids") Collection<Long> ids
);
```

Service group child DTO theo order ID rồi tạo response theo thứ tự IDs từ pha 1.

### 12.3. Vì sao phải khôi phục thứ tự?

SQL `WHERE id IN (...)` không bảo đảm trả records theo thứ tự danh sách ID bind. Giữ danh sách IDs đã phân trang và map kết quả theo thứ tự đó để response page ổn định.

### 12.4. Xử lý trang rỗng

Nếu `ids` rỗng, trả page rỗng ngay; không gọi query `IN :ids` với collection rỗng rồi phụ thuộc provider/dialect.

### 12.5. Tập IDs quá lớn

Với page size thông thường, tập IDs nhỏ. Nếu cần tải hàng nghìn IDs, chia thành chunks theo giới hạn bind parameters của database hoặc dùng temporary table/array parameter/DB-specific technique phù hợp.

### 12.6. Count query và consistency

Page IDs thường có data query và count query. Nếu query có filters phức tạp, count query phải đếm đúng root entities. Các truy vấn pha 1/2/3 nằm trong một transaction nhưng snapshot consistency phụ thuộc isolation level/database. Nếu cần snapshot nhất quán mạnh, xác định isolation phù hợp.

## 13. Cartesian product và MultipleBagFetchException

### 13.1. Cartesian product do nhiều collection

Một Order có:

- 8 OrderLines.
- 3 Payments.
- 2 Shipments.

Nếu JOIN FETCH cả ba collections, số rows có thể là 8 × 3 × 2 = 48 rows cho cùng một order. Với nhiều orders, result set tăng rất nhanh.

### 13.2. MultipleBagFetchException

Hibernate có thể từ chối fetch đồng thời nhiều bag collections và ném `MultipleBagFetchException`. Một bag thường là List không có index column/semantics phân biệt phần tử theo vị trí.

Ví dụ dễ gặp:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;

@OneToMany(mappedBy = "order")
private List<Payment> payments;
```

Nếu cùng fetch join hai collection bag trong một query, Hibernate có thể không biết cách phân biệt duplicates một cách an toàn.

### 13.3. Đừng đổi List thành Set như một cách sửa máy móc

`Set` thay đổi semantics collection:

- Không còn bảo đảm thứ tự như List.
- Phụ thuộc equals/hashCode.
- Không cho phép duplicate theo equality.
- SQL vẫn có thể tạo Cartesian product.
- Không làm giảm số rows do các JOIN kết hợp.

Chỉ dùng Set khi domain thực sự cần set semantics. Cách sửa query thường là tách collection thành nhiều truy vấn có kiểm soát hoặc dùng DTO/read model.

### 13.4. Nhiều query có thể nhanh hơn một query lớn

Ví dụ:

1. Query Order + Customer.
2. Query OrderLine + Product cho các order IDs.
3. Query Payments cho cùng IDs.

Số statements cố định theo page, nhưng result sets không nhân chéo giữa ba collection. Đây thường là trade-off tốt hơn một JOIN khổng lồ.

## 14. Filtering collection và nguy cơ collection không đầy đủ

Một fetch join vừa fetch vừa lọc child có thể làm association được khởi tạo chỉ với một phần dữ liệu:

```hql
select o
from PurchaseOrder o
join fetch o.lines l
where l.status = :status
```

Nếu collection `o.lines` được đánh dấu initialized với chỉ các lines thỏa predicate, code sau có thể tưởng đó là **toàn bộ lines của order**.

Với entity aggregate, đây là nguy cơ correctness. Nếu cần danh sách line đã lọc, hãy trả DTO riêng hoặc query child repository độc lập; không gắn một collection partial vào entity graph như thể nó đầy đủ.

Có thể dùng query root với EXISTS để lọc Order mà không fetch partial collection:

```hql
select o
from PurchaseOrder o
where exists (
    select 1
    from OrderLine l
    where l.order = o
      and l.status = :status
)
```

Sau đó fetch collection đầy đủ theo nhu cầu riêng nếu use case thực sự cần.

## 15. Batch fetching và SUBSELECT so với JOIN FETCH

| Tiêu chí | JOIN FETCH | @BatchSize | SUBSELECT | DTO projection |
|---|---|---|---|---|
| Cách tải | JOIN trong query cụ thể | Nhiều IDs trong một batch | Tải collection cho tập owners bằng subselect | SELECT đúng scalar/aggregate fields |
| Phù hợp to-one | Rất tốt | Tốt khi nhiều proxies | Không phải lựa chọn chính | Rất tốt cho read model |
| Phù hợp to-many | Một collection nhỏ/kiểm soát | Nhiều collections cần khởi tạo theo nhóm | Một role collection của tập owners | Nested DTO qua nhiều query |
| Pagination parent | To-many fetch nguy hiểm | Có thể phù hợp | Cần đo theo query shape | Rất phù hợp với DTO page |
| Dữ liệu dư | Có thể nhiều rows lặp | Có thể tải proxies không dùng | Có thể tải mọi collection trong tập | Thường ít nhất |
| N+1 | Tránh nếu fetch đúng association | Giảm số nhóm SELECT | Giảm số collection SELECT | Tránh bằng query thiết kế đúng |
| Complexity | Query cụ thể, dễ thấy | Cấu hình mapping/provider | Hibernate-specific | DTO/query/count cần khớp |

Không có một kỹ thuật thắng trong mọi trường hợp. Hãy lựa chọn theo cardinality, số association, pagination và response shape.

## 16. @Transactional và Open Session in View không phải giải pháp N+1

### 16.1. Transaction giữ persistence context hoạt động

Một service:

```java
@Transactional(readOnly = true)
public List<OrderDto> listOrders() {
    List<PurchaseOrder> orders = repository.findAll();

    return orders.stream()
        .map(order -> new OrderDto(
            order.getId(),
            order.getCustomer().getName()
        ))
        .toList();
}
```

Lazy association có thể được tải trong transaction. Nhưng nếu không có fetch plan, mỗi Customer có thể vẫn cần SELECT riêng. `@Transactional` giải quyết lifecycle/transaction boundary, không tự giảm query count.

### 16.2. OSIV có thể che LazyInitializationException

Spring Boot có thể giữ EntityManager qua web request. Khi controller hoặc JSON serializer chạm lazy association sau khi service transaction kết thúc, SQL vẫn chạy.

Điều này có thể che lỗi lifecycle nhưng làm query phát sinh ngoài nơi repository/service dự định, khiến N+1 khó phát hiện. Cân nhắc:

```properties
spring.jpa.open-in-view=false
```

sau khi chuyển endpoint sang trả DTO hoàn chỉnh và test với OSIV tắt.

### 16.3. DTO hoàn chỉnh trước khi rời service boundary

Controller nên nhận DTO:

```java
@GetMapping("/{id}")
public OrderDetailDto detail(@PathVariable Long id) {
    return queryService.getDetail(id);
}
```

Không trả entity để serializer tự duyệt associations. Dù OSIV bật hay tắt, response DTO thuần giúp ranh giới truy vấn rõ hơn.

## 17. L1/L2 cache không thay fetch plan

### 17.1. First-level cache

Persistence context đảm bảo cùng entity identity trong một Session được quản lý thống nhất. Nếu nhiều Orders tham chiếu cùng Customer, lần đầu có thể tải Customer, lần sau tái sử dụng object trong L1 và không thêm SELECT.

Điều đó có thể làm N+1 ít rõ trong test nếu fixture có nhiều references trùng nhau. Hãy test cả trường hợp mỗi parent tham chiếu một target khác nhau.

### 17.2. Second-level cache

L2 cache có thể giảm SELECT cho entity/collection đã cache, nhưng:

- Cache có thể cold, expired hoặc bị evict.
- Nhiều cache misses vẫn tạo nhiều queries.
- Cache không giảm row explosion của JOIN.
- Query result cache có semantics riêng.
- Cache hit không phải cam kết hiệu năng cho mọi node.

Không thiết kế fetch plan chỉ dựa vào cache warm-up.

### 17.3. Đo cả cold-cache và warm-cache

Integration/performance test nên có kịch bản context mới và cache được làm sạch hoặc không bật L2 cho fixture test, để phát hiện query count thực sự. Sau đó có thể đo riêng warm-cache behavior như một workload khác.

## 18. Những điểm đặc biệt của @OneToOne

@OneToOne có thể khó lazy hơn to-many/to-one proxy trong một số mapping, nhất là association inverse side không có FK trong bảng entity hiện tại. Hibernate có thể cần biết target có tồn tại không trước khi quyết định tạo proxy.

Các lựa chọn:

- Kiểm tra SQL thực tế với mapping/version.
- Cân nhắc bytecode enhancement nếu ứng dụng đã hỗ trợ và có lý do.
- Dùng EntityGraph hoặc JOIN FETCH cho use case cần target.
- Thiết kế DTO projection nếu chỉ cần một vài fields.

Không giả định ghi `fetch = LAZY` trên mọi OneToOne luôn trì hoãn mọi SELECT trong mọi provider/version.

## 19. Fetch plan theo query thay vì mapping toàn cục

Một entity có thể được dùng bởi nhiều use cases:

```text
PurchaseOrder
  ├── Order list: id, number, customer name, line count
  ├── Order detail: customer, lines, product
  ├── Finance report: totals grouped by month
  └── Update status: status + version
```

Một mapping EAGER toàn cục không thể tối ưu cả bốn use cases. Tách query methods hoặc read services:

```java
Page<OrderListDto> findOrderList(...);

Optional<PurchaseOrder> findDetailWithCustomer(...);

List<OrderLine> findLinesWithProduct(...);

List<MonthlyOrderTotalDto> findMonthlyTotals(...);
```

Tên method thể hiện rõ fetch shape, giúp reviewer nhìn ra một query được thiết kế cho màn hình nào.

## 20. Ví dụ hoàn chỉnh: Order detail không N+1 bằng hai truy vấn

Entity rút gọn:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}

@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY)
    private Product product;

    private int quantity;
    private BigDecimal unitPrice;
}
```

Repositories:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        join fetch o.customer
        where o.id = :id
        """)
    Optional<PurchaseOrder> findDetailHeader(@Param("id") Long id);
}

public interface OrderLineRepository
        extends JpaRepository<OrderLine, Long> {

    @Query("""
        select l
        from OrderLine l
        join fetch l.product
        where l.order.id = :orderId
        order by l.id
        """)
    List<OrderLine> findDetailLines(@Param("orderId") Long orderId);
}
```

DTO:

```java
public record OrderLineDto(
    Long id,
    String sku,
    String productName,
    int quantity,
    BigDecimal unitPrice
) {}

public record OrderDetailDto(
    Long id,
    String orderNumber,
    String customerName,
    List<OrderLineDto> lines
) {}
```

Service:

```java
@Service
public class OrderQueryService {
    private final PurchaseOrderRepository orders;
    private final OrderLineRepository lines;

    public OrderQueryService(
            PurchaseOrderRepository orders,
            OrderLineRepository lines) {
        this.orders = orders;
        this.lines = lines;
    }

    @Transactional(readOnly = true)
    public OrderDetailDto getDetail(Long orderId) {
        PurchaseOrder order = orders.findDetailHeader(orderId)
            .orElseThrow(() -> new EntityNotFoundException(
                "Order not found"
            ));

        List<OrderLineDto> lineDtos =
            lines.findDetailLines(orderId).stream()
                .map(line -> new OrderLineDto(
                    line.getId(),
                    line.getProduct().getSku(),
                    line.getProduct().getName(),
                    line.getQuantity(),
                    line.getUnitPrice()
                ))
                .toList();

        return new OrderDetailDto(
            order.getId(),
            order.getOrderNumber(),
            order.getCustomer().getName(),
            lineDtos
        );
    }
}
```

Trong mapping và use case đơn giản này, hai truy vấn chính đủ để lấy header/customer và tất cả lines/product, không tăng số SELECT theo số lines. Mapper chạy trong transaction nhưng không tự gây N+1 vì association đã được fetch có chủ đích.

Nếu query này được gọi cho nhiều orders cùng lúc, hãy dùng page IDs + bulk lines thay vì gọi `getDetail` N lần trong vòng lặp.

## 21. Ví dụ phân trang parent rồi tải children

DTO:

```java
public record OrderListItemDto(
    Long id,
    String orderNumber,
    String customerName,
    List<OrderLineDto> lines
) {}
```

Pha 1:

```java
@Query("""
    select o.id
    from PurchaseOrder o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Long> findIds(
    @Param("status") OrderStatus status,
    Pageable pageable
);
```

Pha 2:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.id in :ids
    """)
List<PurchaseOrder> findHeaders(@Param("ids") Collection<Long> ids);
```

Pha 3:

```java
@Query("""
    select l
    from OrderLine l
    join fetch l.product
    where l.order.id in :ids
    order by l.order.id, l.id
    """)
List<OrderLine> findLines(@Param("ids") Collection<Long> ids);
```

Service grouping:

```java
@Transactional(readOnly = true)
public Page<OrderListItemDto> listWithLines(
        OrderStatus status, Pageable pageable) {

    Page<Long> idPage = orders.findIds(status, pageable);
    List<Long> ids = idPage.getContent();

    if (ids.isEmpty()) {
        return new PageImpl<>(
            List.of(), pageable, idPage.getTotalElements()
        );
    }

    Map<Long, PurchaseOrder> headerById =
        orders.findHeaders(ids).stream()
            .collect(Collectors.toMap(
                PurchaseOrder::getId,
                Function.identity()
            ));

    Map<Long, List<OrderLineDto>> linesByOrder =
        lines.findLines(ids).stream()
            .collect(Collectors.groupingBy(
                line -> line.getOrder().getId(),
                LinkedHashMap::new,
                Collectors.mapping(
                    line -> new OrderLineDto(
                        line.getId(),
                        line.getProduct().getSku(),
                        line.getProduct().getName(),
                        line.getQuantity(),
                        line.getUnitPrice()
                    ),
                    Collectors.toList()
                )
            ));

    List<OrderListItemDto> content = ids.stream()
        .map(id -> {
            PurchaseOrder order = headerById.get(id);
            return new OrderListItemDto(
                id,
                order.getOrderNumber(),
                order.getCustomer().getName(),
                linesByOrder.getOrDefault(id, List.of())
            );
        })
        .toList();

    return new PageImpl<>(
        content, pageable, idPage.getTotalElements()
    );
}
```

Imports cần thiết gồm `Map`, `List`, `Collection`, `Collectors`, `Function`, `LinkedHashMap`, `PageImpl`. Ví dụ giả định mọi ID trong page đều còn tồn tại giữa các query; nếu có concurrent deletes và yêu cầu consistency nghiêm ngặt, cần xác định isolation/snapshot behavior và xử lý header bị thiếu.

Đây là một số truy vấn cố định theo page thay vì một truy vấn collection fetch join có nguy cơ pagination sai hoặc N+1 theo từng parent.

## 22. Kiểm tra SQL và phát hiện N+1

### 22.1. SQL logging

Trong môi trường phát triển/test:

```properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
```

SQL log cho thấy query shape và số statement. Chỉ bật bind-value TRACE khi có lý do cụ thể và dùng dữ liệu synthetic; không cần giá trị thật để nhận diện N+1.

### 22.2. Hibernate Statistics

Bật:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Lấy thống kê:

```java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.setStatisticsEnabled(true);
statistics.clear();

OrderDetailDto dto = queryService.getDetail(orderId);

long statements = statistics.getPrepareStatementCount();
long entityLoads = statistics.getEntityLoadCount();
long queryExecutions = statistics.getQueryExecutionCount();
```

Các số liệu đo các khía cạnh khác nhau:

- Prepared statement count: số prepared statements được thống kê.
- Entity load count: số entity được load.
- Query execution count: số query executions Hibernate thống kê.

Không đồng nhất chúng với số network round trips trong mọi driver/batch/cache configuration. Statistics ở SessionFactory có thể bị nhiễu nếu test chạy song song.

### 22.3. Đo trên cold persistence context

Trước khi đo:

- Seed dữ liệu trong transaction riêng và commit.
- Dùng EntityManager/Session mới.
- Clear Statistics ngay trước use case.
- Tránh test method có outer transaction giữ persistence context đã warm.
- Nếu dùng L2 cache, cân nhắc test riêng khi cache disabled/cold và khi cache warm.
- Dùng fixture có nhiều target entities khác nhau để không bị L1 reuse che N+1.

### 22.4. Query count không phải metric duy nhất

Một JOIN FETCH có thể giảm statements từ 51 xuống 1 nhưng trả 20.000 rows lặp. Vì vậy cần quan sát:

- Số SQL statements.
- Rows returned.
- Bytes transferred.
- Execution plan và DB time.
- Hibernate hydration/CPU.
- Memory allocation.
- Request latency p95/p99.
- Connection pool wait time.

Mục tiêu là giảm chi phí toàn hệ thống, không phải đạt con số “một query” bằng mọi giá.

## 23. Integration test chứng minh fetch plan

Ví dụ test Spring Boot:

```java
@SpringBootTest(properties = {
    "spring.jpa.open-in-view=false",
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
class OrderQueryServiceIT {

    @Autowired
    private OrderQueryService queryService;

    @Autowired
    private EntityManagerFactory emf;

    @Test
    void detailQueryCountDoesNotGrowWithLineCount() {
        Long orderId = seedOrderInCommittedTransaction(50);

        SessionFactory sf = emf.unwrap(SessionFactory.class);
        Statistics stats = sf.getStatistics();
        stats.clear();

        OrderDetailDto dto = queryService.getDetail(orderId);

        assertThat(dto.lines()).hasSize(50);
        assertThat(stats.getPrepareStatementCount())
            .isLessThanOrEqualTo(3);
    }
}
```

`seedOrderInCommittedTransaction` là helper do test tự triển khai. Ngưỡng 3 là mục tiêu minh họa cho hai truy vấn chính cộng overhead có thể có, không phải cam kết cho mọi cấu hình.

### 23.1. Test cardinality khác nhau

Chạy cùng use case với:

- Một Order có 1 line.
- Một Order có 50 lines.
- Một Order có 500 lines.

Nếu số prepared statements tăng từ 2 lên 51 rồi 501, có dấu hiệu N+1. Nếu statements giữ gần như ổn định nhưng rows/latency tăng, đó có thể là chi phí dữ liệu thực tế chứ không phải N+1.

### 23.2. Test list page có children

Tạo 20 orders với số lines khác nhau; gọi page endpoint. Xác nhận:

- Có đúng 20 parent IDs theo page.
- Thứ tự giống sort key.
- Mỗi parent có đầy đủ lines.
- Không duplicate parent DTO.
- Count query đúng.
- Query count không tăng theo số parent/child.
- Không xảy ra in-memory pagination trên collection fetch.

### 23.3. Không chỉ mock repository

Unit test mapper với entity Java thuần không thể tái hiện lazy proxy và SQL. Cần integration test với Hibernate và database tương thích để chứng minh fetch plan.

## 24. Những anti-pattern phổ biến

### 24.1. EAGER mọi quan hệ

Tăng dữ liệu tải ở các use case không cần và không đảm bảo JOIN. Dùng LAZY mặc định hợp lý rồi chỉ định fetch plan theo query.

### 24.2. Một JOIN FETCH khổng lồ

Nhiều collection nhân chéo rows và có thể gây MultipleBagFetchException. Tách thành vài truy vấn có kiểm soát.

### 24.3. JOIN FETCH collection cùng Pageable

Giới hạn SQL rows không tương đương giới hạn parent entities. Page root IDs trước, tải children theo tập IDs.

### 24.4. Mapper chạm lazy association trong controller

Có thể gây LazyInitializationException khi OSIV tắt hoặc N+1 khi OSIV bật. Hoàn tất DTO trong read service hoặc dùng projection.

### 24.5. @Transactional được coi là thuốc chữa N+1

Transaction giữ Session mở nhưng không thay fetch plan. Đo số statements và thiết kế cách tải.

### 24.6. Dựa vào L2 cache

Cache miss/eviction/cold start có thể làm N+1 xuất hiện lại. Fetch plan phải hiệu quả khi cache không giúp.

### 24.7. Fetch partial collection rồi coi là đầy đủ

Lọc child trong fetch join có thể tạo collection đã initialized nhưng chỉ chứa subset. Dùng DTO query riêng cho danh sách đã lọc.

### 24.8. Đổi List thành Set để tránh MultipleBagFetchException

Có thể thay đổi semantics mà Cartesian product vẫn tồn tại. Tách query theo collection.

### 24.9. @BatchSize quá lớn

SQL IN có thể quá rộng, tải dư dữ liệu và tăng memory. Đo batch sizes theo database và workload.

### 24.10. Không đo query count khi thêm association mới

Một field DTO mới như `customer.address.city` có thể kích hoạt thêm một chuỗi lazy loads. Mỗi thay đổi response shape cần xem lại fetch plan và query budget.

## 25. Checklist thiết kế fetch plan theo use case

Trước khi triển khai endpoint đọc, trả lời:

1. Root entity là gì? Có bao nhiêu records tối đa?
2. DTO cần scalar fields nào?
3. Association nào là to-one, association nào là to-many?
4. Có nested associations không?
5. Có cần entity managed để mutate không, hay chỉ cần read DTO?
6. Có thể dùng constructor/interface projection không?
7. Nếu dùng entity, query nào sẽ fetch to-one?
8. Collection nào sẽ tải bằng JOIN, batch hoặc subselect?
9. Có pagination trên root không?
10. Có nguy cơ Cartesian product hoặc multiple bags không?
11. Có collection filtering làm entity graph partial không?
12. Mapper chạy trong transaction không?
13. Có OSIV không? Endpoint có hoạt động khi OSIV tắt không?
14. Có L2 cache khiến test query count sai lệch không?
15. Query budget theo 1/10/100 parents là bao nhiêu?
16. Có cần snapshot consistency giữa nhiều queries không?
17. Authorization/tenant filters đã nằm trong các query chưa?
18. Query plan/index đã được đo trên database gần production chưa?

Checklist này là công cụ thiết kế; không thay integration/performance tests.

## 26. Bảng chọn chiến lược nhanh

| Nhu cầu | Lựa chọn nên cân nhắc đầu tiên | Lý do |
|---|---|---|
| Một Order + Customer | JOIN FETCH to-one hoặc EntityGraph | Dữ liệu gọn, tránh SELECT phụ |
| Một Order + một collection nhỏ | JOIN FETCH collection | Một detail entity, không phân trang parent |
| Một page Orders + customer name | DTO projection | Chỉ tải field cần |
| Một page Orders + line counts | Aggregate DTO projection | COUNT trong DB, không load collection |
| Một page Orders + tất cả lines | Page IDs rồi bulk query lines | Tránh pagination collection fetch |
| Nhiều proxy to-one trong một Session | @BatchSize/default batch fetch size | Gom keys theo nhóm |
| Nhiều collections cùng role cho tập parent | SUBSELECT hoặc batch fetching | Giảm collection N+1 |
| Nhiều collections lớn | Nhiều query riêng/DTO projections | Tránh Cartesian product |
| Báo cáo tổng hợp lớn | SQL/JPQL aggregate projection hoặc read model | Không hydrate entity graph |
| Dynamic read graph | Criteria/EntityGraph/fetch plan có chủ đích | Điều chỉnh theo use case |
| Một use case cần graph dùng lại | NamedEntityGraph/fetch profile | Tái sử dụng có kiểm soát |

## 27. Lỗi thường gặp và hướng điều tra

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| 1 query orders + N query customers | To-one lazy được truy cập từng parent | JOIN FETCH, EntityGraph, DTO projection hoặc batch |
| 1 query orders + N query collections | To-many lazy được khởi tạo từng owner | BatchSize, SUBSELECT hoặc bulk child query |
| EAGER vẫn có nhiều SELECT | EAGER không bắt buộc JOIN | Query-specific fetch plan |
| JOIN FETCH một collection nhanh nhưng response chậm | Row duplication/collection quá lớn | Đo rows/bytes, tách queries |
| MultipleBagFetchException | Fetch nhiều bag collections | Không fetch nhiều bags trong một query |
| Page chỉ có vài parent hoặc cảnh báo memory pagination | Collection fetch kết hợp Pageable | Page IDs trước |
| DTO mapper gây SQL | Mapper truy cập lazy getter | Fetch trước, map trong boundary |
| Chỉ nhanh khi L2 warm | Fetch plan dựa vào cache | Test cold cache, sửa N+1 |
| @EntityGraph không giảm số SELECT như mong muốn | Provider chọn secondary fetch hoặc graph chưa đúng | Đọc SQL và kiểm tra nested paths |
| BatchSize không có tác dụng | Không có proxies/collections cùng role chờ load hoặc context đóng | Kiểm tra access pattern/Session và generated SQL |
| SUBSELECT tải quá nhiều rows | Tập parent gốc lớn | BatchSize/chunking hoặc DTO query |
| Collection thiếu phần tử | Fetch join đã filter child | Tách query child DTO |
| Count query sai | Data query group/filter khác count query | Viết count query tương đương root semantics |
| Test không phát hiện N+1 | Fixture reuse entities/L2 cache/outer transaction | Cold context, unique targets, statistics |
| Query count ít nhưng latency cao | Query join quá rộng hoặc DB plan kém | Đo rows, plan, DB time và memory |
| N+1 trong JSON serialization | Entity trả ra ngoài service, OSIV mở | DTO materialized, OSIV off |
| LazyInitializationException | Mapper ngoài Session | Đặt read boundary và fetch plan |
| Hai pha đọc dữ liệu không cùng snapshot | Isolation không đủ theo yêu cầu | Xác định consistency và transaction isolation |

## 28. Bài tập thực hành

**Bài 1 — Tái hiện N+1 to-one.** Tạo 30 Orders tham chiếu 30 Customers khác nhau. Load Orders rồi đọc Customer.name. Dùng SQL logs hoặc Statistics đếm statements.

**Bài 2 — Sửa bằng JOIN FETCH.** Thêm query fetch Customer. So số statements và response data.

**Bài 3 — Tái hiện N+1 collection.** Load 30 Orders rồi gọi `getLines().size()` cho từng Order. Quan sát SQL.

**Bài 4 — Sửa bằng @BatchSize.** Thử batch size 8, 16 và 32. So số statements, SQL parameter count và thời gian.

**Bài 5 — SUBSELECT.** Đặt `@Fetch(FetchMode.SUBSELECT)` trên collection; tải tập parent và khởi tạo collection của vài parent. Quan sát phạm vi collection được tải.

**Bài 6 — EntityGraph.** Tạo named graph cho Order detail gồm Customer, Lines và Product. So SQL với JOIN FETCH.

**Bài 7 — DTO projection.** Viết Page<OrderListDto> gồm Customer name và line count. Đảm bảo count query đúng.

**Bài 8 — Multiple bags.** Tạo Order có hai List collections và thử fetch join đồng thời. Quan sát lỗi hoặc row explosion; sửa bằng nhiều query.

**Bài 9 — Pagination.** Tạo 20 Orders mỗi order 10 lines; thử Pageable + fetch join collection. Bật fail-on-pagination-over-collection-fetch và sửa bằng hai pha IDs/children.

**Bài 10 — Collection filtering.** Fetch join chỉ lines có status OPEN; kiểm tra collection đã initialized có đầy đủ lines hay không. Thay bằng DTO query riêng.

**Bài 11 — Cache.** Chạy use case với L2 disabled, cold và warm; phân tích vì sao cache hit không thay fetch plan.

**Bài 12 — OSIV.** Tắt `spring.jpa.open-in-view` rồi gọi endpoint trả entity. Chuyển sang DTO và xác nhận serialization không query thêm.

**Bài 13 — Query budget.** Viết integration test đo prepared statement count cho 1, 10, 100 parent records.

**Bài 14 — Cartesian product.** Thử JOIN hai collections có cardinality 8 và 5; ước tính rows và đo result set thực tế.

**Bài 15 — Consistency.** Trong hai pha đọc, cập nhật child từ transaction khác giữa các queries. Phân tích isolation level và yêu cầu snapshot của API.

**Bài 16 — Authorization.** Thêm tenant filter vào query parent và child; chứng minh pha tải children không thể lấy records của tenant khác.

## 29. Câu hỏi tự kiểm tra

**1. N+1 là gì?**

Một query lấy tập root entities, sau đó nhiều query phụ được phát khi truy cập association/collection của từng root hoặc child.

**2. Vì sao EAGER không bảo đảm hết N+1?**

EAGER là yêu cầu fetch state, không bắt buộc provider JOIN tất cả association vào một SQL; Hibernate có thể dùng secondary selects.

**3. JOIN và JOIN FETCH khác nhau thế nào?**

JOIN tham gia query/filter/join condition; JOIN FETCH còn yêu cầu association được khởi tạo cùng entity result.

**4. Khi nào nên dùng DTO projection?**

Khi use case chỉ cần scalar fields/aggregates và không cần entity managed graph.

**5. Vì sao không fetch nhiều collection lớn cùng lúc?**

JOIN nhân rows theo tích cardinality, tăng dữ liệu lặp và có thể gây MultipleBagFetchException với bags.

**6. @BatchSize làm gì?**

Gom việc khởi tạo các proxies/collections cùng loại thành các nhóm SELECT, giảm số queries theo từng key.

**7. SUBSELECT khác batch fetch thế nào?**

SUBSELECT có thể tải collection cho tập owners từ query ban đầu; batch fetch gom một nhóm owner keys theo batch size.

**8. @EntityGraph có bảo đảm một SELECT không?**

Không. Nó mô tả graph cần fetch; provider quyết định cách thực thi.

**9. Vì sao collection fetch join nguy hiểm với Pageable?**

Database giới hạn SQL rows sau JOIN, không phải số root entities; Hibernate có thể phải phân trang trong memory.

**10. Vì sao đổi List thành Set không phải giải pháp mặc định cho MultipleBagFetchException?**

Set thay semantics nhưng không loại bỏ Cartesian product.

**11. @Transactional có tự sửa N+1 không?**

Không. Nó cung cấp transaction/persistence context; fetch plan quyết định query count.

**12. OSIV có thể che vấn đề gì?**

Lazy access trong controller/serializer có thể chạy SQL sau service transaction, che LazyInitializationException nhưng vẫn tạo N+1.

**13. Hibernate Statistics có đo network round trips chính xác không?**

Không nhất thiết; nó đo các counters ORM, cần kết hợp JDBC/database instrumentation.

**14. L2 cache có thay thế fetch plan không?**

Không. Cache miss, cold start và eviction có thể làm N+1 xuất hiện lại.

**15. Khi nào page IDs rồi tải children là phù hợp?**

Khi cần phân trang root entities nhưng response còn chứa to-many collections, tránh collection fetch join trực tiếp trên query page.

## 30. Ghi nhớ

- **N+1 là vấn đề của kế hoạch tải**, thường xuất hiện khi code truy cập lazy association theo từng entity.
- LAZY/EAGER mô tả fetch behavior của mapping; **không đồng nghĩa** với một JOIN hay một SELECT cụ thể.
- Giữ association LAZY làm mặc định hợp lý và chọn fetch plan theo use case.
- Dùng **JOIN FETCH** cho association cần tải ngay, đặc biệt to-one và collection nhỏ/không phân trang.
- Dùng **@EntityGraph** để mô tả graph theo repository operation; graph không cam kết số SELECT.
- Dùng **DTO projection** cho list/report scalar data, aggregate và page phẳng; tránh hydrate entity graph không cần thiết.
- **@BatchSize/default_batch_fetch_size** giảm lazy loads theo nhóm; **FetchMode.SUBSELECT** có thể tải collection cho tập parent. Cả hai cần đo batch size và lượng dữ liệu.
- Không JOIN FETCH nhiều collections lớn vì Cartesian product và MultipleBagFetchException.
- Không phân trang trực tiếp query fetch collection; hãy page root IDs rồi tải headers/children theo tập IDs.
- Đừng filter collection trong fetch join rồi coi kết quả là collection đầy đủ của aggregate.
- @Transactional và OSIV chỉ ảnh hưởng persistence context/lifecycle; chúng không tự chữa N+1.
- L2 cache không thay fetch plan. Test cả cold context/cache và warm cache.
- Đo **query count, rows, bytes, execution plan, memory và latency**; một SQL khổng lồ không mặc nhiên tốt hơn vài SQL nhỏ.
- Dùng integration tests với cardinality 1/10/100 để bảo đảm query count không tăng tuyến tính theo số parent.

### Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide — Fetching](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Hibernate ORM 6.6 User Guide — Batch fetching](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#fetching-batch)
- [Hibernate ORM 6.6 User Guide — Fetch profiles](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#fetching-profiles)
- [Hibernate ORM 6.6 JavaDoc — @BatchSize](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/BatchSize.html)
- [Hibernate ORM 6.6 JavaDoc — @Fetch](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/Fetch.html)
- [Hibernate ORM 6.6 JavaDoc — FetchMode](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/FetchMode.html)
- [Jakarta Persistence 3.1 Specification — Entity Graphs](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1)
- [Spring Data JPA Reference — Entity Graphs](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA Reference — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)


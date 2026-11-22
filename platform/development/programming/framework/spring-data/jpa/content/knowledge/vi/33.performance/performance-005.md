# Giảm N+1 bằng fetch plan hoặc projection phù hợp

Trong Spring Data JPA, một truy vấn lấy danh sách entity có thể trông rất gọn nhưng lại tạo ra nhiều câu SQL khi ứng dụng truy cập các quan hệ lazy. Đây là vấn đề N+1: một truy vấn lấy N bản ghi gốc, sau đó phát sinh thêm nhiều truy vấn để lấy dữ liệu liên quan.

Cách xử lý tốt không phải là bật `EAGER` cho mọi quan hệ. Hãy xác định dữ liệu mà từng use case thực sự cần, sau đó chọn fetch plan để tải entity và quan hệ phù hợp, hoặc dùng projection để chỉ lấy các cột cần hiển thị. Việc chọn đúng chiến lược giúp giảm số lần round trip đến database, lượng dữ liệu truyền và chi phí tạo entity.

## 1. N+1 là gì?

Giả sử màn hình danh sách đơn hàng hiển thị mã đơn, ngày tạo và tên khách hàng. Entity `PurchaseOrder` có quan hệ `ManyToOne` đến `Customer`:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    // getter và các thành phần khác
}
```

Repository tải danh sách đơn:

```java
List<PurchaseOrder> findByStatus(OrderStatus status);
```

Nếu service duyệt danh sách và đọc `order.getCustomer().getName()`, Hibernate có thể thực hiện:

```sql
SELECT ... FROM purchase_order WHERE status = ?;

SELECT ... FROM customer WHERE id = ?;
SELECT ... FROM customer WHERE id = ?;
SELECT ... FROM customer WHERE id = ?;
-- tiếp tục cho các customer chưa có trong persistence context
```

Với một truy vấn lấy danh sách và N truy vấn lấy customer, tổng số truy vấn có thể là (1 + N). Đây là nguồn gốc tên gọi N+1.

Nếu nhiều đơn hàng cùng tham chiếu một customer, first-level cache có thể giảm số truy vấn trùng theo ID. Tuy vậy, số truy vấn vẫn có thể tăng theo số customer khác nhau trong kết quả. Với quan hệ collection như `@OneToMany`, việc truy cập từng collection có thể tạo thêm một truy vấn cho mỗi parent.

N+1 thường xuất hiện khi:

- Service duyệt danh sách entity rồi truy cập quan hệ lazy.
- Mapper hoặc serializer gọi getter của quan hệ mà tầng service không dự kiến.
- Controller trả trực tiếp entity và JSON serializer đi qua các quan hệ.
- Một vòng lặp gọi repository để lấy dữ liệu con cho từng entity cha.
- Một truy vấn lấy entity nhưng không khai báo rõ dữ liệu liên quan mà use case cần.

## 2. Nhận diện N+1 qua SQL thực tế

Không nên kết luận chỉ từ annotation `LAZY` hoặc `EAGER`. Cần quan sát SQL được phát ra trong use case cụ thể.

Ví dụ, với 50 đơn hàng có 50 customer khác nhau, log có thể cho thấy một câu truy vấn đơn hàng và 50 câu truy vấn customer. Một cách kiểm tra đơn giản trong môi trường phát triển:

```properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind parameter logging có thể hiển thị dữ liệu nhạy cảm; chỉ bật khi cần trong môi trường phát triển và tắt hoặc kiểm soát chặt ở production.

Có thể bật Hibernate statistics để quan sát số lần prepare statement, entity load và collection fetch:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
logging.level.org.hibernate.stat=DEBUG
```

Trong integration test, có thể lấy `SessionFactory` statistics hoặc dùng công cụ như datasource-proxy, p6spy để đếm câu SQL. Khi đo, hãy:

1. Dùng dữ liệu đủ lớn và có nhiều giá trị quan hệ khác nhau.
2. Xóa hoặc làm mới persistence context giữa các lần đo để cache không che khuất N+1.
3. Không chỉ đo số truy vấn; kiểm tra cả số hàng trả về và kích thước dữ liệu.
4. So sánh cùng một use case trước và sau khi đổi fetch plan.
5. Kiểm tra cả trường hợp danh sách rỗng, ít bản ghi và nhiều bản ghi.

SQL log rất hữu ích để xác nhận giả thuyết. Một truy vấn ít hơn chưa chắc nhanh hơn nếu nó tạo ra phép join lớn và trả về nhiều dữ liệu trùng lặp.

## 3. Vì sao không nên bật EAGER cho mọi quan hệ?

`FetchType.LAZY` cho phép trì hoãn việc tải quan hệ cho đến khi ứng dụng truy cập. `FetchType.EAGER` yêu cầu provider phải tải quan hệ eager khi entity được lấy, nhưng không bắt buộc provider phải dùng một câu SQL join duy nhất.

Với một danh sách entity, provider có thể tải danh sách trước rồi phát thêm các truy vấn riêng để thỏa mãn quan hệ eager. Do đó, `EAGER` vẫn có thể tạo N+1.

Bật EAGER rộng rãi còn có các vấn đề:

- Use case chỉ cần một vài trường vẫn có thể tải cả object graph lớn.
- Nhiều quan hệ eager kết hợp có thể tạo nhiều truy vấn hoặc join phức tạp.
- Dữ liệu được tải thêm làm tăng bộ nhớ, thời gian hydrate entity và lượng dữ liệu truyền.
- Các truy vấn khác nhau có nhu cầu dữ liệu khác nhau nhưng cùng phải chịu fetch plan cố định.

Thường nên giữ quan hệ ở `LAZY` và khai báo dữ liệu cần tải ngay tại query hoặc repository method của từng use case. Với `@ManyToOne` và `@OneToOne`, hãy khai báo `fetch = FetchType.LAZY` một cách tường minh khi phù hợp; cần nhớ việc lazy loading cho to-one có thể phụ thuộc provider, bytecode enhancement và cấu hình mapping.

## 4. Fetch plan là gì?

Fetch plan mô tả những quan hệ nào cần được tải cùng entity trong một lần thực hiện use case. Trong JPA, có thể thể hiện fetch plan bằng:

- JPQL `JOIN FETCH`.
- JPA `EntityGraph`, dùng qua annotation hoặc API.
- Cơ chế batch fetching của Hibernate để gom việc tải lazy association thành các nhóm.
- Một số truy vấn riêng để lấy collection hoặc dữ liệu liên quan khi không phù hợp join trong cùng query.

Fetch plan phù hợp khi ứng dụng cần làm việc với entity và hành vi domain của chúng. Nó cho phép giữ entity managed trong transaction để cập nhật theo dirty checking.

## 5. Dùng JOIN FETCH cho quan hệ cần thiết

Nếu danh sách đơn hàng luôn cần tên customer, có thể fetch join quan hệ customer:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        join fetch o.customer
        where o.status = :status
        order by o.createdAt desc
        """)
    List<PurchaseOrder> findWithCustomerByStatus(
            @Param("status") OrderStatus status);
}
```

`JOIN FETCH` yêu cầu JPA tải quan hệ được chỉ định cùng entity gốc. Khi service gọi `getCustomer().getName()`, Hibernate không cần phát một truy vấn riêng cho mỗi customer đã được fetch.

Dùng `LEFT JOIN FETCH` khi quan hệ có thể null và vẫn muốn giữ entity gốc không có quan hệ:

```java
@Query("""
    select o
    from PurchaseOrder o
    left join fetch o.customer
    where o.status = :status
    """)
List<PurchaseOrder> findWithOptionalCustomer(
        @Param("status") OrderStatus status);
```

Khác biệt:

- `JOIN FETCH` tương đương inner join; entity gốc không có quan hệ phù hợp có thể bị loại khỏi kết quả.
- `LEFT JOIN FETCH` giữ entity gốc ngay cả khi quan hệ không tồn tại.

### Fetch nhiều quan hệ

Có thể fetch thêm quan hệ to-one:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    left join fetch o.shippingAddress
    where o.id = :id
    """)
Optional<PurchaseOrder> findDetailedById(@Param("id") Long id);
```

Cần thận trọng khi fetch collection:

```java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.items
    where o.status = :status
    """)
List<PurchaseOrder> findWithItemsByStatus(
        @Param("status") OrderStatus status);
```

Một đơn hàng có nhiều item sẽ tạo nhiều hàng SQL cho cùng một đơn hàng. `distinct` giúp yêu cầu kết quả entity gốc không bị lặp theo ngữ nghĩa JPQL; Hibernate 6 cũng tự loại trùng entity gốc trong một số trường hợp fetch join collection. Dù vậy, join vẫn có thể làm tập kết quả SQL phình to.

Tránh fetch join nhiều collection cùng lúc nếu chúng tạo tích Descartes lớn. Với Hibernate, fetch đồng thời nhiều bag collection còn có thể phát sinh `MultipleBagFetchException`. Hãy cân nhắc truy vấn collection riêng, batch fetching hoặc projection.

## 6. Dùng @EntityGraph để khai báo fetch plan

JPA EntityGraph mô tả thuộc tính cần tải mà không phải viết join fetch trong JPQL. Spring Data JPA hỗ trợ `@EntityGraph` trên repository method.

Ví dụ chỉ cần customer:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer"})
    List<PurchaseOrder> findByStatus(OrderStatus status);
}
```

Ví dụ cần customer và các item:

```java
@EntityGraph(attributePaths = {"customer", "items"})
List<PurchaseOrder> findDetailedByStatus(OrderStatus status);
```

Có thể chỉ rõ tên graph đã khai báo trên entity:

```java
@Entity
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomer",
    attributeNodes = @NamedAttributeNode("customer")
)
public class PurchaseOrder {
    // ...
}
```

Repository:

```java
@EntityGraph(
    value = "PurchaseOrder.withCustomer",
    type = EntityGraph.EntityGraphType.FETCH
)
Optional<PurchaseOrder> findWithCustomerById(Long id);
```

Hai loại graph:

- `FETCH`: thuộc tính được chỉ định được xem là eager cho query này; thuộc tính không chỉ định được xử lý theo fetch graph semantics.
- `LOAD`: thuộc tính được chỉ định được tải eager, còn các thuộc tính khác giữ fetch behavior được khai báo trên mapping.

EntityGraph là cách diễn đạt fetch plan theo use case. Nó không bảo đảm mọi provider sẽ tạo chính xác một câu SQL; hãy kiểm tra SQL thực tế, nhất là khi graph có collection.

## 7. Dùng projection khi chỉ cần dữ liệu đọc

Nếu màn hình chỉ cần một vài trường, không nhất thiết phải tải entity đầy đủ và các quan hệ của nó. Projection giúp truy vấn trực tiếp dữ liệu cần dùng, giảm lượng cột, số entity được hydrate và nguy cơ lazy loading ngoài dự kiến.

### Interface projection

Khai báo projection:

```java
public interface OrderSummary {
    Long getId();
    String getOrderNumber();
    String getCustomerName();
}
```

Repository truy vấn đúng các trường:

```java
@Query("""
    select o.id as id,
           o.orderNumber as orderNumber,
           c.name as customerName
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc
    """)
List<OrderSummary> findSummariesByStatus(
        @Param("status") OrderStatus status);
```

Tên alias trong query phải khớp tên property accessor của interface projection. Spring Data tạo projection từ các giá trị được trả về. Đây là lựa chọn phù hợp cho danh sách hoặc báo cáo chỉ đọc.

### DTO class hoặc record projection

Với Java 17+, có thể dùng record làm DTO:

```java
package com.example.orders;

import java.math.BigDecimal;

public record OrderListItem(
        Long id,
        String orderNumber,
        String customerName,
        BigDecimal total) {
}
```

JPQL dùng constructor expression:

```java
@Query("""
    select new com.example.orders.OrderListItem(
        o.id, o.orderNumber, c.name, o.total
    )
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc
    """)
List<OrderListItem> findOrderItems(
        @Param("status") OrderStatus status);
```

Tên class trong constructor expression phải là tên đầy đủ (fully qualified class name). Thứ tự và kiểu tham số phải khớp constructor của DTO/record. Các trường được chọn phải tương thích kiểu dữ liệu của thuộc tính entity.

DTO projection có ưu điểm là kết quả là object độc lập, không phải entity managed. Nó phù hợp cho API response, bảng danh sách, dashboard và báo cáo.

### Closed và open projection

Closed projection chỉ khai báo các property cần lấy, giúp Spring Data biết tập thuộc tính đầu ra. Open projection có thể dùng `@Value` và SpEL để tính property từ target entity; do cần truy cập target, nó có thể khiến provider tải nhiều dữ liệu hơn dự kiến.

Nested projection có thể làm Spring Data phải join và materialize quan hệ. Đừng giả định nested projection luôn chỉ chọn đúng một cột; hãy xem SQL phát ra. Với truy vấn tối ưu rõ ràng, JPQL constructor projection thường dễ kiểm soát hơn.

## 8. Fetch plan hay projection: chọn theo use case

| Nhu cầu | Cách phù hợp | Lý do |
|---|---|---|
| Cần cập nhật entity và gọi domain method | Fetch join hoặc EntityGraph | Entity được tải managed trong persistence context. |
| Màn hình chỉ đọc vài trường | DTO hoặc interface projection | Chỉ lấy dữ liệu cần thiết, tránh hydrate cả entity graph. |
| Cần một entity và một quan hệ to-one | JOIN FETCH hoặc EntityGraph | Tránh truy vấn lazy riêng khi truy cập quan hệ. |
| Cần collection lớn hoặc nhiều collection | Projection hoặc nhiều query có chủ đích | Tránh join làm nhân số hàng và tốn bộ nhớ. |
| Cần phân trang danh sách lớn | Projection hoặc query ID rồi fetch dữ liệu cần thiết | Tránh phân trang trực tiếp trên collection fetch join. |
| Một số quan hệ lazy được truy cập theo nhóm | Batch fetching | Giảm số truy vấn mà không cần join tất cả dữ liệu. |

Không nên áp dụng cùng một fetch plan cho mọi method. Một màn hình danh sách có thể cần projection gọn, trong khi màn hình chi tiết cần entity graph đầy đủ hơn.

## 9. N+1 khi phân trang và collection fetch

Fetch join một quan hệ to-one thường an toàn hơn với pagination vì mỗi entity gốc thường tương ứng một hàng kết quả. Nhưng fetch join collection làm một entity gốc xuất hiện trên nhiều hàng SQL. Điều này khiến giới hạn `LIMIT/OFFSET` ở database không còn tương ứng trực tiếp với số entity gốc.

Hibernate có thể phải lấy nhiều hàng rồi phân trang trong bộ nhớ nếu query vừa phân trang vừa fetch collection. Với tập dữ liệu lớn, điều này rất tốn kém. Có thể cấu hình để Hibernate báo lỗi thay vì âm thầm phân trang trong bộ nhớ:

```properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
```

### Chiến lược hai bước

Một cách phổ biến là phân trang ID của entity gốc trước, rồi tải quan hệ cho các ID trong trang:

```java
Page<Long> findIdsByStatus(
        OrderStatus status, Pageable pageable);
```

Query ID:

```java
@Query(
    value = """
        select o.id
        from PurchaseOrder o
        where o.status = :status
        order by o.createdAt desc, o.id desc
        """,
    countQuery = """
        select count(o)
        from PurchaseOrder o
        where o.status = :status
        """
)
Page<Long> findPageIds(
        @Param("status") OrderStatus status,
        Pageable pageable);
```

Sau đó tải các entity và quan hệ cần thiết:

```java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.customer
    left join fetch o.items
    where o.id in :ids
    """)
List<PurchaseOrder> findPageDetails(@Param("ids") Collection<Long> ids);
```

Service cần xử lý trường hợp trang rỗng và sắp xếp kết quả theo thứ tự ID đã phân trang, vì câu lệnh `IN` không bảo đảm giữ thứ tự đầu vào:

```java
@Transactional(readOnly = true)
public Page<OrderListItem> list(
        OrderStatus status, Pageable pageable) {

    Page<Long> idPage = repository.findPageIds(status, pageable);
    if (idPage.isEmpty()) {
        return new PageImpl<>(List.of(), pageable, idPage.getTotalElements());
    }

    Map<Long, PurchaseOrder> byId = repository
            .findPageDetails(idPage.getContent())
            .stream()
            .collect(Collectors.toMap(
                    PurchaseOrder::getId,
                    Function.identity()));

    List<OrderListItem> content = idPage.getContent().stream()
            .map(byId::get)
            .filter(Objects::nonNull)
            .map(OrderListItem::from)
            .toList();

    return new PageImpl<>(content, pageable, idPage.getTotalElements());
}
```

Đoạn service giả định có factory `OrderListItem.from(PurchaseOrder)` và repository phù hợp. Nếu có thể dùng DTO projection cho danh sách, cách đó thường đơn giản hơn vì không cần tải collection entity.

## 10. Batch fetching là phương án giảm N+1

Nếu không thể hoặc không muốn fetch join toàn bộ quan hệ, Hibernate có thể tải lazy association theo nhóm bằng batch fetching.

Có thể đặt trên association:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderItem> items = new ArrayList<>();
```

Hoặc cấu hình mặc định:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

Khi ứng dụng truy cập một collection lazy, Hibernate có thể tải nhiều collection chưa khởi tạo trong cùng một câu SQL bằng điều kiện `IN`. Số truy vấn có thể giảm từ N truy vấn xuống khoảng số nhóm cần tải.

Batch fetching là tối ưu của Hibernate, không phải cách chọn cột dữ liệu. Nó vẫn tải entity và association theo cơ chế lazy; số truy vấn phụ thuộc số association, kích thước batch và dữ liệu thực tế. Hãy đo SQL để xác nhận hiệu quả.

## 11. Tránh lazy loading ngoài service

Một nguồn N+1 khó phát hiện là controller hoặc JSON serializer truy cập entity sau khi service đã trả về.

Ví dụ:

```java
@GetMapping("/orders")
public List<PurchaseOrder> list() {
    return service.findOrders();
}
```

Nếu JSON serializer gọi `getCustomer()` hoặc `getItems()`, nó có thể kích hoạt nhiều truy vấn. Nếu persistence context đã đóng, ứng dụng có thể gặp `LazyInitializationException`.

Cách thiết kế tốt hơn là chuyển entity thành DTO ngay trong transaction của service:

```java
@Transactional(readOnly = true)
public List<OrderListItem> findOrderItems(OrderStatus status) {
    return repository.findByStatus(status).stream()
            .map(OrderListItem::from)
            .toList();
}
```

Trong ví dụ này, `OrderListItem.from()` chỉ được phép truy cập các thuộc tính đã fetch phù hợp. Với danh sách lớn, nên truy vấn thẳng DTO projection để tránh tải entity không cần thiết.

Open Session in View có thể khiến lazy loading tiếp tục hoạt động trong thời gian render response, nhưng nó dễ che giấu N+1 và làm truy vấn phát sinh ở tầng web. Không nên dựa vào OSIV để giải quyết fetch plan. Hãy kiểm soát dữ liệu cần thiết ở tầng repository/service.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Bật EAGER cho mọi quan hệ | Tải thừa, có thể vẫn phát sinh N+1. | Giữ mapping phù hợp và khai báo fetch plan theo use case. |
| Fetch join nhiều collection | Nhân số hàng, tăng bộ nhớ hoặc gặp MultipleBagFetchException. | Chia query, dùng batch fetching hoặc projection. |
| Phân trang trực tiếp với collection fetch join | Hibernate có thể phân trang trong bộ nhớ hoặc trả kết quả không như mong đợi. | Phân trang ID trước rồi tải dữ liệu chi tiết, hoặc dùng DTO projection. |
| Trả entity trực tiếp từ controller | Serializer có thể kích hoạt lazy loading và N+1. | Map DTO trong service transaction. |
| Dùng projection nhưng không kiểm tra SQL | Nested/open projection có thể tải nhiều dữ liệu hơn dự kiến. | Kiểm tra query và ưu tiên DTO constructor projection khi cần kiểm soát. |
| Chỉ nhìn số câu SQL | Một query join lớn vẫn có thể rất chậm. | Đo số hàng, payload, execution plan và thời gian. |
| Dùng một fetch plan cho mọi màn hình | Có thể tải quá ít hoặc quá nhiều dữ liệu. | Thiết kế repository method theo nhu cầu use case. |

## 13. Checklist tối ưu N+1

Trước khi tối ưu:

- Xác định endpoint hoặc nghiệp vụ nào phát sinh nhiều SQL.
- Đọc SQL log và xác định quan hệ bị tải lặp.
- Xác định màn hình cần những trường và association nào.
- Kiểm tra dữ liệu có bị lazy load trong mapper, serializer hoặc vòng lặp không.

Khi chọn giải pháp:

- Dùng JOIN FETCH hoặc EntityGraph cho entity cần quan hệ cụ thể.
- Dùng DTO/interface projection cho truy vấn chỉ đọc.
- Dùng batch fetching khi muốn gom lazy load thành nhóm.
- Tránh fetch join collection trực tiếp cùng pagination.
- Không bật EAGER toàn cục chỉ để che N+1.

Sau khi thay đổi:

- Đo lại số truy vấn với dữ liệu đại diện.
- Kiểm tra kết quả có đầy đủ và đúng thứ tự.
- Kiểm tra kích thước dữ liệu trả về và execution plan.
- Kiểm thử danh sách rỗng, một bản ghi và nhiều bản ghi.
- Xác nhận không có lazy loading ngoài transaction hoặc tại tầng web.

N+1 là vấn đề về cách tải dữ liệu theo use case. Fetch plan giúp entity có sẵn các quan hệ cần thiết; projection giúp lấy đúng dữ liệu cần hiển thị. Chọn giữa hai cách dựa trên việc nghiệp vụ cần entity managed hay chỉ cần dữ liệu đọc, sau đó xác nhận bằng SQL và phép đo thực tế.
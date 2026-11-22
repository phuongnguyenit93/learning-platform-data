# Phân trang với quan hệ tập hợp và rủi ro xử lý trong bộ nhớ

Một màn hình danh sách thường hiển thị từng đơn hàng cùng vài thông tin liên quan như khách hàng, dòng hàng hoặc nhãn. Trong Java, các quan hệ `@OneToMany` và `@ManyToMany` khiến việc tải danh sách trở nên phức tạp: một hàng cha có thể tương ứng với nhiều hàng con. Nếu dùng truy vấn fetch collection rồi áp dụng `Pageable`, phép nối có thể nhân bản hàng cha ở kết quả SQL. Một số ORM, đặc biệt Hibernate trong các trường hợp fetch collection có phân trang, có thể tải toàn bộ kết quả phù hợp rồi cắt trang trong bộ nhớ ứng dụng.

Khi dữ liệu còn nhỏ, vấn đề có thể khó nhận ra. Khi bảng tăng lên, database phải đọc và truyền nhiều hàng hơn cần thiết, ứng dụng giữ nhiều entity và collection trong heap, garbage collection tăng, thời gian phản hồi kéo dài và có thể hết bộ nhớ. Một giải pháp đúng cần phân trang trên tập thực thể gốc ở database, sau đó tải quan hệ cho đúng tập ID của trang.

Trong module **DATABASE_PERFORMANCE**, nội dung này kết nối cách ứng dụng Java/JPA tải quan hệ với chi phí truy vấn, kế hoạch thực thi, I/O và bộ nhớ. Bạn sẽ học vì sao phân trang trên collection fetch dễ sai hoặc đắt, cách nhận biết phân trang trong bộ nhớ, cách dùng truy vấn hai pha, DTO projection, batch fetching và count query đúng nghĩa, cùng cách kiểm chứng bằng SQL log, execution plan và số liệu heap.

## 1. Vấn đề bắt đầu từ quan hệ một-nhiều

Giả sử mô hình đơn hàng có một khách hàng và nhiều dòng hàng:

```java
@Entity
public class Order {
    @Id
    private Long id;

    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();
}

@Entity
public class OrderItem {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Order order;

    private String productName;
    private int quantity;
}
```

Một đơn hàng có thể có 1, 5 hoặc 100 dòng hàng. Nếu truy vấn nối `Order` với `OrderItem`, kết quả quan hệ ở mức SQL có một hàng cho mỗi tổ hợp đơn hàng và dòng hàng. Đơn hàng có 5 dòng hàng sẽ xuất hiện 5 lần ở tập hàng sau join.

### Ví dụ SQL bị nhân bản

```sql
SELECT o.order_id, o.created_at,
       i.order_item_id, i.product_name, i.quantity
FROM orders AS o
LEFT JOIN order_item AS i
  ON i.order_id = o.order_id
WHERE o.status = 'OPEN'
ORDER BY o.created_at DESC, o.order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Giới hạn 20 áp dụng cho hàng kết quả sau join, không phải 20 đơn hàng. Nếu 3 đơn hàng đầu tiên lần lượt có 10, 8 và 6 dòng hàng, 20 hàng SQL đầu có thể chỉ chứa một phần của ba đơn hàng. Nếu ORM cố gắng dựng entity graph đầy đủ, nó phải xử lý dữ liệu đã bị cắt ở ranh giới collection; kết quả có thể thiếu các phần tử của collection hoặc buộc provider thay đổi chiến lược truy vấn.

Đây là điểm cốt lõi: **đơn vị phân trang phải trùng với đơn vị nghiệp vụ cần hiển thị**. Nếu màn hình phân trang theo đơn hàng, database phải chọn trang đơn hàng trước. Nếu màn hình phân trang theo dòng hàng, khóa phân trang phải xác định từng dòng hàng.

## 2. Vì sao fetch collection kết hợp Pageable có rủi ro?

Trong JPQL, truy vấn thường được viết như sau:

```java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Order> findOrdersWithItems(
        @Param("status") OrderStatus status,
        Pageable pageable);
```

Ý định có vẻ hợp lý: tải đơn hàng và collection `items` trong một lần truy vấn, tránh N+1, rồi dùng `Pageable` để lấy trang. Nhưng `JOIN FETCH` trên quan hệ collection tạo nhiều hàng SQL cho một entity gốc. SQL `OFFSET`/`LIMIT` hoặc `FETCH FIRST` không thể đơn giản giới hạn theo số entity cha nếu mỗi entity có số hàng con khác nhau.

### Cách ORM có thể xử lý

Với Hibernate, khi query có collection fetch join và pagination, Hibernate có thể bỏ giới hạn hàng ở SQL, tải tất cả hàng phù hợp, dựng entity/collection trong bộ nhớ rồi mới cắt danh sách theo page. Hành vi này giúp tránh cắt cụt collection, nhưng chi phí có thể tăng theo toàn bộ tập dữ liệu thay vì kích thước trang.

Tùy phiên bản Hibernate và cấu hình, log có thể xuất cảnh báo dạng `HHH90003004: firstResult/maxResults specified with collection fetch; applying in memory`. Đây là dấu hiệu cần xử lý. Không nên xem việc trả đúng số entity trong `Page` là bằng chứng database chỉ đọc đúng số entity của trang.

### DISTINCT không giải quyết được phân trang theo entity

`distinct` trong JPQL có thể giúp loại entity gốc trùng trong kết quả ORM. Tuy nhiên, ở SQL, các cột của `OrderItem` khác nhau nên các hàng join vẫn khác nhau. `SELECT DISTINCT` trên cả cột cha và con không thể gộp nhiều dòng hàng thành một hàng đơn hàng duy nhất.

Một số provider có thể khử trùng entity sau khi đọc. Việc khử trùng ở Java không làm giảm số hàng database đã tạo, truyền qua mạng và ORM đã xử lý. Vì vậy, `distinct` không thay thế chiến lược phân trang đúng cấp thực thể.

### Rủi ro về tài nguyên

- Database có thể scan/join toàn bộ tập phù hợp thay vì chỉ lấy một trang.
- Số hàng trung gian có thể bằng tổng số dòng con của mọi thực thể phù hợp.
- JDBC driver phải chuyển nhiều hàng qua network.
- Hibernate phải materialize entity, quản lý identity map và collection trong persistence context.
- Heap tăng, allocation tăng và garbage collection hoạt động nhiều hơn.
- Request có thể chậm dù response chỉ chứa 20 đơn hàng.
- Khi dữ liệu tăng, nguy cơ `OutOfMemoryError` hoặc timeout tăng theo.

## 3. Phân biệt quan hệ to-one và to-many

Fetch join trên `@ManyToOne` hoặc `@OneToOne` thường không nhân bản hàng gốc theo cùng cách vì mỗi hàng gốc tham chiếu tối đa một hàng liên quan. Ví dụ, tải `Order.customer` thường có thể kết hợp với phân trang nếu quan hệ và mapping bảo đảm cardinality to-one.

```java
@Query("""
    select o
    from Order o
    join fetch o.customer
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Order> findPageWithCustomer(
        @Param("status") OrderStatus status,
        Pageable pageable);
```

Truy vấn này thường an toàn hơn collection fetch vì mỗi đơn hàng chỉ có một khách hàng. Tuy vậy, cần xác nhận quan hệ thật sự là to-one, không có mapping sai hoặc join khác làm nhân bản hàng. Provider, dialect và cách sinh count query vẫn cần được kiểm tra.

Với `@OneToMany` hoặc `@ManyToMany`, số hàng liên quan có thể không giới hạn ở một. Đây là trường hợp cần tránh kết hợp collection fetch trực tiếp với phân trang database nếu provider có thể áp dụng pagination trong bộ nhớ.

Nếu truy vấn có nhiều collection fetch, số hàng SQL có thể tăng theo tích số lượng phần tử. Ví dụ một đơn hàng có 5 dòng hàng và 4 nhãn, join đồng thời cả hai collection có thể tạo tới 20 tổ hợp hàng cho một đơn hàng trước khi tính thêm các đơn hàng khác.

## 4. Nhận biết phân trang trong bộ nhớ

Không chỉ nhìn vào annotation `Pageable`. Hãy kiểm tra SQL thực tế và hành vi runtime.

### Dấu hiệu trong log

- Hibernate phát cảnh báo `firstResult/maxResults specified with collection fetch; applying in memory` hoặc thông báo tương đương của phiên bản.
- SQL sinh ra không có giới hạn trang tương ứng dù repository nhận `Pageable`.
- Truy vấn trả về số hàng rất lớn trong khi API chỉ trả một số entity nhỏ.
- Thời gian đọc JDBC và materialize entity lớn hơn nhiều thời gian serialize response.

### Dấu hiệu trong metric

- Heap used tăng mạnh trong request phân trang.
- Allocation rate và GC pause tăng theo số bản ghi phù hợp.
- Số entity/collection trong persistence context lớn hơn page size nhiều lần.
- Database rows returned và bytes received tăng theo tổng dữ liệu, không theo kích thước trang.
- p95/p99 tăng nhanh khi bảng hoặc collection lớn lên.

### Bật kiểm tra fail-fast trong Hibernate

Với Hibernate hỗ trợ thuộc tính này, có thể cấu hình để biến tình huống collection fetch pagination thành lỗi thay vì âm thầm phân trang trong bộ nhớ:

```yaml
spring:
  jpa:
    properties:
      hibernate.query.fail_on_pagination_over_collection_fetch: true
```

Tên thuộc tính Hibernate dạng đầy đủ là `hibernate.query.fail_on_pagination_over_collection_fetch`. Cách đặt trong Spring Boot là truyền thuộc tính qua `spring.jpa.properties`. Hãy kiểm tra đúng phiên bản Hibernate đang dùng; bật fail-fast ở môi trường kiểm thử giúp phát hiện truy vấn nguy hiểm sớm.

Không bật cấu hình này rồi chỉ bỏ qua lỗi. Hãy sửa truy vấn để phân trang ở database trước, sau đó tải collection cho đúng trang.

## 5. Chiến lược hai pha: phân trang ID trước, tải quan hệ sau

Một cách phổ biến và dễ kiểm soát là thực hiện hai truy vấn:

1. Truy vấn thứ nhất chọn ID của các thực thể gốc theo filter, thứ tự và giới hạn trang.
2. Truy vấn thứ hai tải entity cùng collection cho đúng danh sách ID đó.

Vì truy vấn thứ nhất chỉ đọc bảng gốc hoặc join dùng để lọc, nó có thể áp dụng `LIMIT/OFFSET` ở database mà không nhân bản thực thể do collection fetch. Truy vấn thứ hai chỉ xử lý một tập ID có kích thước bằng page size.

### Pha 1: lấy trang ID

```java
@Query("""
    select o.id
    from Order o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Long> findOrderIds(
        @Param("status") OrderStatus status,
        Pageable pageable);
```

Truy vấn không fetch collection nên database có thể phân trang theo hàng `Order`. Thứ tự có tie-breaker `o.id` để tránh các đơn hàng cùng `createdAt` đổi vị trí không xác định giữa các trang.

### Pha 2: tải entity và collection theo ID

```java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.id in :ids
    """)
List<Order> findOrdersWithItemsByIdIn(
        @Param("ids") Collection<Long> ids);
```

Truy vấn thứ hai có thể trả nhiều hàng SQL vì collection, nhưng chỉ cho số đơn hàng đã giới hạn ở pha một. Không đặt `Pageable` ở pha này. Kích thước tập cha bị giới hạn bởi số ID đầu vào, nên lượng collection cần dựng có phạm vi rõ ràng.

### Ghép kết quả và giữ đúng thứ tự trang

SQL `IN (:ids)` không bảo đảm giữ thứ tự của danh sách ID truyền vào. Vì vậy, cần sắp xếp kết quả theo thứ tự ID ở pha một:

```java
public Page<Order> findOrderPageWithItems(
        OrderStatus status,
        Pageable pageable) {

    Page<Long> idPage = orderRepository.findOrderIds(status, pageable);
    List<Long> ids = idPage.getContent();

    if (ids.isEmpty()) {
        return new PageImpl<>(List.of(), pageable, idPage.getTotalElements());
    }

    List<Order> loaded = orderRepository.findOrdersWithItemsByIdIn(ids);
    Map<Long, Order> byId = loaded.stream()
            .collect(Collectors.toMap(Order::getId, Function.identity()));

    List<Order> ordered = ids.stream()
            .map(byId::get)
            .filter(Objects::nonNull)
            .toList();

    return new PageImpl<>(ordered, pageable, idPage.getTotalElements());
}
```

Đoạn mã minh họa giả định ID duy nhất và dữ liệu không bị xóa giữa hai pha. Nếu có thể xóa hoặc thay đổi filter giữa hai truy vấn, cần xác định hành vi mong muốn và transaction isolation phù hợp. Việc lọc `null` tránh lỗi khi một hàng đã biến mất, nhưng có thể làm page chứa ít phần tử hơn page size; không được âm thầm giả định tổng số vẫn chính xác trong mọi isolation level.

### Giới hạn kích thước IN

Một số database có giới hạn số bind parameter hoặc kích thước câu lệnh. Page size nhỏ thường không gặp vấn đề, nhưng truy vấn batch tải nhiều ID có thể cần chia chunk. Không nên lấy hàng chục nghìn ID chỉ để tải một trang. Với ID ghép hoặc composite key, cách biểu diễn điều kiện `IN` có thể khác theo dialect.

## 6. Count query phải đếm thực thể gốc

`Page<T>` thường cần tổng số phần tử để tính tổng trang. Spring Data JPA có thể sinh hoặc chạy count query riêng. Khi truy vấn chính có join collection, count có thể đếm số hàng sau join thay vì số thực thể cha nếu không được viết đúng.

Ví dụ đơn hàng có 4 dòng hàng. `COUNT(*)` trên join có thể đếm 4 hàng cho một đơn hàng. Nếu cần đếm số đơn hàng, phải đếm distinct ID hoặc dùng truy vấn chỉ trên bảng cha.

```java
@Query(
    value = """
        select o.id
        from Order o
        where o.status = :status
        order by o.createdAt desc, o.id desc
        """,
    countQuery = """
        select count(o.id)
        from Order o
        where o.status = :status
        """
)
Page<Long> findOrderIds(
        @Param("status") OrderStatus status,
        Pageable pageable);
```

Vì count query không join collection, mỗi đơn hàng chỉ được đếm một lần. Nếu điều kiện lọc cần bảng con, có thể dùng `EXISTS` để giữ cardinality của bảng cha:

```java
@Query(
    value = """
        select o.id
        from Order o
        where o.status = :status
          and exists (
              select 1
              from OrderItem i
              where i.order = o
                and i.quantity > 0
          )
        order by o.createdAt desc, o.id desc
        """,
    countQuery = """
        select count(o.id)
        from Order o
        where o.status = :status
          and exists (
              select 1
              from OrderItem i
              where i.order = o
                and i.quantity > 0
          )
        """
)
Page<Long> findOrderIdsWithPositiveItems(
        @Param("status") OrderStatus status,
        Pageable pageable);
```

`EXISTS` kiểm tra có ít nhất một dòng hàng phù hợp mà không nhân bản đơn hàng trong tập kết quả. Cần index trên khóa ngoại `order_item.order_id` và các cột lọc liên quan nếu execution plan cho thấy có lợi.

### Page, Slice và List

- `Page<T>` thường cần tổng số phần tử, vì vậy có thể phát sinh count query.
- `Slice<T>` chỉ cần biết còn trang tiếp theo hay không; framework thường lấy thêm một hàng để xác định `hasNext`, tránh count toàn bộ nếu query được thiết kế phù hợp.
- `List<T>` với `Pageable` có thể lấy một đoạn dữ liệu nhưng không cung cấp tổng số trang.

Nếu giao diện chỉ cần nút “Xem thêm”, `Slice` hoặc cursor-based response có thể tránh chi phí count lớn. Nếu cần tổng số chính xác, count query phải được tối ưu riêng và được đo như một phần của request.

## 7. Dùng DTO projection khi không cần entity graph

Nếu màn hình chỉ hiển thị một số cột, không cần dựng toàn bộ entity và collection. DTO projection cho phép database trả đúng cột cần thiết, giảm bytes, hydration, persistence context và heap.

```java
public record OrderSummary(
        Long id,
        Instant createdAt,
        String customerName,
        BigDecimal totalAmount) {}
```

```java
@Query("""
    select new com.example.api.OrderSummary(
        o.id, o.createdAt, c.displayName, o.totalAmount)
    from Order o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<OrderSummary> findOrderSummaries(
        @Param("status") OrderStatus status,
        Pageable pageable);
```

Đây là truy vấn chỉ lấy dữ liệu cần cho màn hình danh sách. Khi người dùng mở chi tiết một đơn hàng, ứng dụng mới tải collection `items` theo ID. Cách này tránh giữ entity graph lớn trong persistence context và giảm rủi ro lazy loading ngoài transaction.

### Khi cần tổng hợp dữ liệu con

Nếu danh sách chỉ cần số lượng dòng hàng hoặc tổng số lượng, không cần tải toàn bộ `OrderItem`. Có thể tổng hợp ở database:

```sql
SELECT o.order_id,
       o.created_at,
       COUNT(i.order_item_id) AS item_count,
       COALESCE(SUM(i.quantity), 0) AS total_quantity
FROM orders AS o
LEFT JOIN order_item AS i
  ON i.order_id = o.order_id
WHERE o.status = 'OPEN'
GROUP BY o.order_id, o.created_at
ORDER BY o.created_at DESC, o.order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Truy vấn tổng hợp phải nhóm đúng theo thực thể cha và được kiểm tra kế hoạch. Nếu join thêm nhiều quan hệ một-nhiều, aggregate có thể bị nhân chéo; khi đó cần tổng hợp từng quan hệ riêng hoặc dùng subquery/CTE phù hợp.

## 8. Batch fetching và subselect fetching

Nếu không muốn fetch collection ngay trong truy vấn phân trang, có thể để quan hệ lazy rồi tải theo batch khi cần. Hibernate hỗ trợ các chiến lược như `@BatchSize` hoặc cấu hình batch fetching để gom nhiều lần truy cập association thành ít truy vấn hơn.

Ví dụ:

```java
@Entity
public class Order {
    @Id
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    @BatchSize(size = 32)
    private List<OrderItem> items = new ArrayList<>();
}
```

Khi ứng dụng truy cập `items` của nhiều đơn hàng trong một persistence context, provider có thể tải collection theo nhóm thay vì một truy vấn riêng cho từng đơn hàng. Kết quả thường giảm N+1 nhưng vẫn cần kiểm soát số lượng collection được khởi tạo.

### Batch fetching không phải phân trang collection

Batch fetching giảm số round trip khi tải association, nhưng nếu ứng dụng duyệt toàn bộ collection của mọi đơn hàng, tổng số dòng con vẫn có thể rất lớn. Nó không thay thế page size hợp lý, DTO projection hoặc truy vấn chi tiết theo nhu cầu.

### Subselect fetching

Một số cấu hình Hibernate có thể tải collection của các entity đã được truy vấn trong cùng persistence context bằng một truy vấn con hoặc truy vấn nhóm. Cách này có thể giảm N+1, nhưng số entity cha được quản lý trong context vẫn ảnh hưởng số dữ liệu tải. Hãy kiểm tra SQL sinh ra và số hàng thực tế; không giả định subselect luôn có giới hạn bằng trang nếu query gốc không giới hạn đúng.

### Tránh lazy loading sau khi đóng session

Nếu DTO được chuyển đổi sau khi transaction kết thúc nhưng vẫn truy cập collection lazy, ứng dụng có thể gặp `LazyInitializationException` hoặc vô tình kích hoạt truy vấn trong một session mở rộng. Hãy tải dữ liệu cần thiết trong transaction ở service layer và chuyển thành DTO trước khi trả response. Tránh bật Open Session in View như cách che giấu việc truy cập association thiếu kiểm soát.

## 9. Dùng EXISTS để lọc quan hệ con mà không nhân bản cha

Nếu yêu cầu chỉ là “đơn hàng có ít nhất một dòng hàng thuộc nhóm X”, không cần join collection để lấy từng dòng hàng. Có thể dùng `EXISTS`:

```java
@Query("""
    select o.id
    from Order o
    where o.status = :status
      and exists (
          select 1
          from OrderItem i
          where i.order = o
            and i.productCategory = :category
      )
    order by o.createdAt desc, o.id desc
    """)
Page<Long> findOrderIdsByItemCategory(
        @Param("status") OrderStatus status,
        @Param("category") String category,
        Pageable pageable);
```

`EXISTS` giữ mỗi đơn hàng một lần về mặt logic, dù có nhiều dòng hàng phù hợp. Sau khi lấy trang ID, pha hai mới tải collection hoặc dữ liệu con cần thiết.

Nếu cần dữ liệu từ một dòng hàng cụ thể, hãy xác định rõ có cần tất cả dòng hàng hay chỉ một bản ghi đại diện. Dùng join và projection phù hợp thay vì mặc định fetch toàn bộ collection.

## 10. Thứ tự ổn định và phân trang sâu

Mọi phân trang cần `ORDER BY` xác định. Nếu sắp xếp chỉ theo `createdAt` nhưng nhiều đơn hàng có cùng timestamp, thứ tự giữa chúng không được đảm bảo. Thêm khóa duy nhất làm tie-breaker:

```sql
ORDER BY created_at DESC, order_id DESC
```

Điều này đặc biệt quan trọng khi truy vấn pha một lấy ID. Nếu hai lần gọi trang có thứ tự không ổn định, ứng dụng có thể thấy bản ghi lặp hoặc thiếu ở ranh giới trang.

### OFFSET pagination

`Pageable` thường tạo truy vấn có offset và limit. Với trang sâu, database có thể phải đi qua nhiều hàng trước khi trả page hiện tại. Chi phí tăng theo offset, tùy access path và index.

Index ứng viên cho truy vấn lọc theo tenant và sắp xếp theo thời gian:

```sql
CREATE INDEX ix_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, order_id DESC);
```

Thứ tự cột phải dựa trên filter, độ chọn lọc, sort và workload khác. Kiểm tra actual plan xem database có thể seek/range scan và tránh sort hay không.

### Keyset pagination

Với danh sách lớn chủ yếu đi tiếp từng trang, keyset pagination có thể tránh offset sâu. Với thứ tự `created_at DESC, order_id DESC`, điều kiện tiếp tục sau cursor là:

```sql
WHERE tenant_id = :tenant_id
  AND status = :status
  AND (
      created_at < :last_created_at
      OR (created_at = :last_created_at
          AND order_id < :last_order_id)
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Cursor phải chứa đủ `created_at` và `order_id`, giữ đúng độ chính xác timestamp. Keyset phù hợp với “trang tiếp theo”; nhảy trực tiếp đến trang số bất kỳ khó hơn. Nếu trường sắp xếp có thể thay đổi, bản ghi có thể di chuyển qua cursor giữa các lần gọi.

## 11. Tính nhất quán giữa truy vấn lấy ID và truy vấn tải quan hệ

Chiến lược hai pha tạo ra hai lần đọc. Nếu dữ liệu thay đổi giữa hai truy vấn, pha hai có thể không còn khớp hoàn toàn với kết quả pha một.

Ví dụ:

- Đơn hàng bị xóa sau khi ID được chọn.
- Trạng thái đơn hàng thay đổi và không còn thỏa filter.
- Dòng hàng mới được thêm hoặc bị xóa giữa hai pha.
- Một quan hệ được cập nhật trong khi trang đang được dựng.

### Chọn isolation phù hợp

Nếu cần trang phản ánh cùng một snapshot, thực hiện cả hai truy vấn trong cùng transaction với isolation level cung cấp snapshot nhất quán theo hệ quản trị. Cần hiểu semantics cụ thể: `READ COMMITTED` ở một số hệ quản trị có thể lấy snapshot mới cho mỗi statement; `REPEATABLE READ` hoặc snapshot isolation có thể giữ snapshot ổn định hơn nhưng có chi phí và hành vi khác nhau.

Giữ transaction quá lâu có thể làm tăng version retention, lock hoặc áp lực tài nguyên. Vì vậy, không nên mở transaction kéo dài qua nhiều lần người dùng nhấn “trang tiếp theo”. Mỗi request phân trang thường là một transaction ngắn; nếu nghiệp vụ cần snapshot xuyên nhiều request, cần thiết kế snapshot token hoặc tập ID được lưu rõ ràng.

### Xử lý hàng biến mất

Nếu pha hai không trả đủ ID, có thể:

- Chấp nhận page có ít hàng hơn và giữ total theo snapshot phù hợp.
- Chạy lại truy vấn ID trong cùng chính sách nhất quán nếu nghiệp vụ cho phép.
- Dùng isolation phù hợp để ngăn thay đổi nhìn thấy giữa hai pha.

Không tự thêm hàng khác vào trang mà không cập nhật cursor và total một cách nhất quán. Hành vi cần được xác định rõ ở API.

## 12. Giới hạn bộ nhớ trong ứng dụng Java

Mỗi entity được Hibernate quản lý có thể cần đối tượng Java, entry trong persistence context, proxy, collection wrapper và quan hệ tham chiếu. Khi tải hàng nghìn entity cùng hàng chục nghìn child, heap sử dụng có thể lớn hơn nhiều so với kích thước dữ liệu SQL.

### Persistence context giữ entity

Trong một persistence context, Hibernate thường duy trì identity map để một hàng database tương ứng với một entity instance được quản lý. Điều này giúp nhất quán trạng thái nhưng cũng giữ tham chiếu đến các entity đã tải. Nếu truy vấn materialize quá nhiều entity, chúng có thể tồn tại đến khi context được clear hoặc transaction kết thúc.

### Collection có thể lớn hơn page cha

Page size 20 không bảo đảm chỉ tải 20 hoặc vài chục đối tượng. Nếu mỗi đơn hàng có trung bình 200 dòng hàng, trang 20 đơn hàng có thể tạo 4.000 `OrderItem`, cộng thêm sản phẩm, nhãn hoặc quan hệ lồng nhau. Giới hạn page cha vẫn cần kết hợp giới hạn dữ liệu con.

### Không tải toàn bộ rồi cắt bằng subList

Mẫu nguy hiểm:

```java
List<Order> all = repository.findAllByStatus(OrderStatus.OPEN);
List<Order> page = all.subList(start, end);
```

Database đã trả toàn bộ tập phù hợp. `subList` chỉ tạo view trên danh sách trong Java, không làm giảm SQL rows, network bytes, entity hydration hoặc heap đã tiêu thụ. Với dữ liệu lớn, cách này có thể gây OOM.

Hãy truyền giới hạn vào truy vấn database bằng `Pageable`, `LIMIT/FETCH`, keyset hoặc cơ chế cursor phù hợp. Chỉ dùng xử lý trong bộ nhớ cho tập dữ liệu đã được giới hạn và có kích thước được chứng minh.

### Cẩn thận với Java Stream

`repository.findAll().stream()` không biến truy vấn đã tải toàn bộ thành streaming database. Nó chỉ stream qua collection đã nằm trong heap. Một số repository hỗ trợ `Stream<T>` hoặc JDBC cursor có thể đọc theo luồng, nhưng phải giữ transaction/connection mở trong suốt quá trình tiêu thụ, đóng stream đúng cách và kiểm soát fetch size. Streaming giảm peak memory nhưng giữ connection lâu hơn và không tự cung cấp phân trang theo nghiệp vụ.

## 13. Quản lý kích thước collection con

Ngay cả khi trang cha đúng, collection con có thể không có giới hạn. Nếu một đơn hàng có hàng chục nghìn dòng hàng, tải toàn bộ `items` cho trang cha vẫn có thể quá lớn.

Các lựa chọn:

- Chỉ hiển thị số lượng hoặc tổng tiền bằng aggregate query.
- Tải một số phần tử gần nhất hoặc nổi bật theo truy vấn riêng có giới hạn.
- Tạo endpoint phân trang riêng cho `OrderItem` theo `orderId`.
- Dùng DTO projection thay entity collection.
- Giới hạn số quan hệ được mở rộng trong một response.

Ví dụ endpoint chi tiết dòng hàng:

```java
Page<OrderItemSummary> findByOrderId(
        Long orderId,
        Pageable pageable);
```

Index trên `(order_id, order_item_id)` hoặc `(order_id, created_at, order_item_id)` có thể hỗ trợ lọc và sắp xếp tùy truy vấn. Không nên trả toàn bộ collection chỉ vì mapping JPA đã khai báo `List<OrderItem>`.

## 14. Tránh N+1 mà không tải toàn bộ collection

N+1 xảy ra khi truy vấn danh sách cha rồi mỗi entity lại kích hoạt một truy vấn riêng để tải quan hệ. Cách chữa N+1 không nhất thiết là fetch join collection trong truy vấn phân trang.

Có thể kết hợp:

1. Phân trang ID cha ở database.
2. Tải dữ liệu to-one cần thiết trong truy vấn pha một hoặc pha hai.
3. Tải collection của đúng các ID trang bằng batch fetch hoặc truy vấn riêng.
4. Dùng DTO để trả kết quả mà không giữ entity graph không cần thiết.

Ví dụ tải tất cả dòng hàng cho một trang ID bằng một truy vấn:

```java
@Query("""
    select i
    from OrderItem i
    join fetch i.product
    where i.order.id in :orderIds
    order by i.order.id, i.id
    """)
List<OrderItem> findItemsForOrders(
        @Param("orderIds") Collection<Long> orderIds);
```

Sau đó nhóm theo `orderId` trong bộ nhớ. Vì `orderIds` đã bị giới hạn theo page size, tập con được tải có phạm vi rõ ràng. Tuy nhiên, nếu một đơn hàng có rất nhiều dòng hàng, vẫn cần giới hạn hoặc phân trang riêng cho collection con.

## 15. Kiểm tra SQL và execution plan

Để xác nhận truy vấn thực sự phân trang ở database, hãy kiểm tra SQL do Hibernate sinh ra và execution plan của database.

### Những điều cần xác nhận

- Truy vấn pha một có `LIMIT`, `OFFSET`, `FETCH FIRST` hoặc cú pháp tương ứng của dialect.
- Số hàng trả về ở pha một không vượt page size (ngoại trừ `Slice` có thể lấy thêm một hàng để xác định `hasNext`).
- Truy vấn pha hai có điều kiện `WHERE id IN (...)` đúng với ID của trang.
- Không có collection fetch pagination gây cảnh báo hoặc bị chuyển sang xử lý trong bộ nhớ.
- Count query đếm đúng số thực thể cha.
- Index hỗ trợ filter và sort của pha một.
- Actual rows và logical reads phù hợp với kích thước trang và độ chọn lọc.
- Không có sort/hash spill hoặc scan lớn ngoài dự kiến.

### Công cụ quan sát

| Lớp | Công cụ/metric | Mục tiêu |
|---|---|---|
| Hibernate/JPA | SQL logging, statistics, cảnh báo pagination | Nhìn truy vấn thực và số entity/collection được tải |
| JDBC | Query duration, rows fetched, bytes và fetch size nếu driver cung cấp | Đo thời gian và lượng dữ liệu qua driver |
| Database | `EXPLAIN ANALYZE`, actual execution plan, logical reads | Xác minh index, row count và chi phí join/sort |
| Java runtime | Heap usage, allocation rate, GC pause, live objects | Phát hiện materialize quá nhiều entity |
| API | p50/p95/p99, response size, page size, timeout | Đo trải nghiệm người dùng và xu hướng theo dữ liệu |

Không bật SQL bind parameter logging có dữ liệu nhạy cảm trong production nếu chưa có kiểm soát. Log truy vấn và tham số cần tuân thủ chính sách bảo vệ dữ liệu.

## 16. Thiết kế index cho truy vấn phân trang cha

Truy vấn pha một thường có filter và sort. Ví dụ:

```sql
SELECT order_id
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Một index ứng viên:

```sql
CREATE INDEX ix_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, order_id DESC);
```

`tenant_id` và `status` là điều kiện bằng, tiếp theo là các cột sắp xếp. Index có thể giúp database tìm vùng dữ liệu phù hợp và đọc theo thứ tự cần thiết. Thứ tự cột cần được xác minh bằng selectivity, các truy vấn khác và actual plan.

Đối với pha hai, index trên `order_item.order_id` hỗ trợ tìm collection theo danh sách ID cha. Nếu truy vấn còn sắp xếp theo `id`, index ghép `(order_id, id)` có thể hữu ích.

Không thêm mọi cột hiển thị vào index một cách máy móc. Index quá rộng làm tăng dung lượng, cache footprint và chi phí insert/update/delete. Nếu cần DTO projection, database có thể dùng covering index trong một số tình huống, nhưng phải cân bằng chi phí ghi.

## 17. Những mẫu truy vấn nên tránh

### Fetch collection và phân trang trực tiếp

```java
// Rủi ro: collection fetch có thể làm Hibernate phân trang trong bộ nhớ.
@Query("select distinct o from Order o left join fetch o.items")
Page<Order> findAllWithItems(Pageable pageable);
```

### Tải toàn bộ rồi cắt ở Java

```java
// Rủi ro: database và JVM đã xử lý toàn bộ tập phù hợp.
List<Order> orders = repository.findAll();
return orders.subList(0, Math.min(20, orders.size()));
```

### Đếm hàng join thay vì đếm thực thể cha

```sql
-- COUNT(*) có thể đếm nhiều dòng con cho cùng một đơn hàng.
SELECT COUNT(*)
FROM orders o
JOIN order_item i ON i.order_id = o.order_id;
```

Nếu cần đếm đơn hàng có dòng hàng, dùng `COUNT(DISTINCT o.order_id)` hoặc `EXISTS` phù hợp; ưu tiên count query chỉ trên bảng cha khi có thể.

### Dùng collection fetch nhiều nhánh

```sql
SELECT ...
FROM orders o
LEFT JOIN order_item i ON i.order_id = o.order_id
LEFT JOIN order_tag t ON t.order_id = o.order_id;
```

Nếu mỗi đơn hàng có nhiều dòng hàng và nhiều tag, join có thể tạo tích số hàng. Tải từng collection theo truy vấn riêng cho trang ID thường dễ kiểm soát hơn.

## 18. Quy trình triển khai một endpoint phân trang an toàn

1. **Xác định đơn vị trang:** đơn hàng, dòng hàng hay một DTO tổng hợp?
2. **Liệt kê quan hệ cần hiển thị:** phân biệt to-one và to-many; xác định collection nào thực sự cần ở trang danh sách.
3. **Viết truy vấn trang gốc:** chỉ chọn ID hoặc DTO cha, không fetch collection.
4. **Tạo thứ tự toàn phần:** thêm khóa duy nhất làm tie-breaker.
5. **Tạo count query phù hợp:** đếm thực thể cha và tránh join nhân bản.
6. **Tải quan hệ theo ID trang:** dùng truy vấn thứ hai, batch fetching hoặc truy vấn DTO riêng.
7. **Giữ thứ tự:** sắp xếp kết quả pha hai theo danh sách ID pha một vì `IN` không bảo đảm thứ tự.
8. **Giới hạn collection con:** aggregate, phân trang riêng hoặc chỉ tải khi người dùng mở chi tiết.
9. **Xác định consistency:** chọn transaction isolation phù hợp với yêu cầu dữ liệu thay đổi giữa hai pha.
10. **Đo tải:** kiểm tra SQL, plan, rows, logical reads, heap, GC, response size và p95/p99.
11. **Bật fail-fast:** nếu Hibernate hỗ trợ, bật `hibernate.query.fail_on_pagination_over_collection_fetch` trong môi trường kiểm thử.
12. **Kiểm thử dữ liệu biên:** cha không có con, cha có nhiều con, collection rất lớn, trang cuối và dữ liệu thay đổi đồng thời.

## 19. Ví dụ service hoàn chỉnh với Page ID và collection

Một cấu trúc service có thể tách repository query và việc dựng kết quả:

```java
@Service
public class OrderQueryService {
    private final OrderRepository orderRepository;

    public OrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public Page<OrderView> findOpenOrders(Pageable pageable) {
        Page<Long> idPage = orderRepository.findOrderIds(
                OrderStatus.OPEN, pageable);

        if (idPage.isEmpty()) {
            return new PageImpl<>(List.of(), pageable,
                    idPage.getTotalElements());
        }

        List<Order> loaded = orderRepository.findOrdersWithItemsByIdIn(
                idPage.getContent());

        Map<Long, Order> byId = loaded.stream()
                .collect(Collectors.toMap(Order::getId, Function.identity()));

        List<OrderView> content = idPage.getContent().stream()
                .map(byId::get)
                .filter(Objects::nonNull)
                .map(OrderView::from)
                .toList();

        return new PageImpl<>(content, pageable,
                idPage.getTotalElements());
    }
}
```

`@Transactional(readOnly = true)` giúp hai pha chạy trong cùng transaction và cho phép database/provider áp dụng tối ưu đọc phù hợp. Nó không tự bảo đảm snapshot nhất quán ở mọi isolation level. Nếu yêu cầu cần cả hai pha nhìn cùng snapshot, cấu hình isolation phải được chọn theo semantics của hệ quản trị.

DTO được dựng bên trong transaction khi collection cần thiết còn có thể truy cập. Sau khi trả `OrderView`, tầng web không cần giữ entity hoặc persistence context mở để serialize.

### Lưu ý về Page total

`idPage.getTotalElements()` phản ánh count query của pha một. Nếu pha hai bỏ mất ID do dữ liệu bị xóa hoặc filter thay đổi, số phần tử thực trả có thể ít hơn tổng trang. Đây là lý do cần định nghĩa consistency và isolation. Nếu không cần tổng chính xác, `Slice<Long>` hoặc cursor response có thể giảm chi phí count.

## 20. Những sai lầm thường gặp

1. **Dùng `JOIN FETCH` collection cùng `Pageable`:** có thể buộc Hibernate tải toàn bộ hàng phù hợp rồi phân trang trong bộ nhớ.
2. **Cho rằng `DISTINCT` làm giảm số hàng SQL:** các cột con khác nhau vẫn tạo các hàng join riêng.
3. **Chỉ kiểm tra số entity trả về:** page có 20 entity không chứng minh database chỉ đọc 20 entity.
4. **Đếm `COUNT(*)` sau join:** có thể đếm số dòng con thay vì số thực thể cha.
5. **Dùng hai pha nhưng quên giữ thứ tự:** `WHERE id IN (...)` không bảo đảm thứ tự ID đầu vào.
6. **Tải collection rất lớn cho mỗi entity của trang:** page cha nhỏ vẫn có thể tạo heap lớn.
7. **Dùng batch fetch như giới hạn dữ liệu:** batch giảm round trip, không giới hạn tổng số phần tử được tải.
8. **Dùng `findAll().stream()` như database streaming:** dữ liệu có thể đã được materialize toàn bộ trong heap.
9. **Cắt `subList` sau khi tải toàn bộ:** chỉ cắt danh sách Java, không giảm database I/O hoặc heap đã dùng.
10. **Bỏ qua count query:** `Page` có thể chạy count riêng và count cũng có thể trở thành bottleneck.
11. **Không có tie-breaker:** các hàng có cùng sort key có thể đổi vị trí giữa các trang.
12. **Không xác định consistency giữa hai pha:** hàng có thể bị xóa hoặc đổi trạng thái giữa hai truy vấn.
13. **Tải entity graph rồi serialize sau transaction:** có thể gây lazy loading ngoài dự kiến hoặc `LazyInitializationException`.
14. **Chỉ đo database:** heap, GC, JDBC bytes và thời gian dựng DTO cũng ảnh hưởng p95/p99.

## 21. Danh sách kiểm tra trước khi triển khai

- [ ] Đã xác định đơn vị phân trang là thực thể cha, con hay DTO tổng hợp.
- [ ] Đã phân biệt quan hệ to-one với collection to-many.
- [ ] Không dùng collection fetch trực tiếp trong truy vấn `Pageable` nếu provider có thể phân trang trong bộ nhớ.
- [ ] Đã kiểm tra SQL sinh ra có giới hạn trang ở database.
- [ ] Đã dùng truy vấn hai pha hoặc DTO projection khi phù hợp.
- [ ] Count query đếm đúng thực thể gốc và không bị nhân bản bởi join.
- [ ] Đã giữ thứ tự kết quả pha hai theo danh sách ID pha một.
- [ ] Đã giới hạn collection con hoặc phân trang riêng cho dữ liệu con lớn.
- [ ] Đã kiểm tra N+1 và cân nhắc batch fetching mà không tải quá nhiều dữ liệu.
- [ ] Đã xác định transaction isolation cho tính nhất quán giữa hai pha.
- [ ] Đã tạo index phù hợp với filter, sort và khóa ngoại của truy vấn.
- [ ] Đã theo dõi SQL rows, logical reads, heap, allocation, GC và response size.
- [ ] Đã kiểm thử trang đầu, trang sâu, collection rỗng, collection rất lớn và cập nhật đồng thời.
- [ ] Đã bật fail-fast cho collection fetch pagination nếu phiên bản Hibernate hỗ trợ.

Phân trang với quan hệ tập hợp cần được thiết kế theo đơn vị thực thể mà API muốn trả về. Fetch join collection có thể nhân bản hàng SQL và khiến ORM áp dụng giới hạn trong bộ nhớ, làm tăng I/O, hydration và heap dù response chỉ có một trang nhỏ. Hãy phân trang ID hoặc DTO của thực thể gốc trước, tải quan hệ cho đúng tập ID sau đó, viết count query đúng cardinality, giữ thứ tự và xác định consistency giữa các pha. Kết hợp giới hạn collection con, index phù hợp và giám sát cả database lẫn JVM để bảo đảm hiệu năng ổn định khi dữ liệu tăng.

# Fetch join, entity graph, DTO projection và chi phí tải dữ liệu thừa

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích cách fetch strategy trong JPA/Hibernate quyết định số câu SQL, số hàng truyền về và lượng object được tạo trong ứng dụng Java.
- Nhận diện N+1 query, tải thiếu dữ liệu và tải thừa dữ liệu từ quan hệ entity.
- Chọn `JOIN FETCH`, `EntityGraph`, DTO projection hoặc batch fetching theo nhu cầu của từng use case.
- Tránh nhân bản hàng, Cartesian multiplication và các vấn đề khi phân trang collection.
- Đo query count, rows returned, bytes truyền, thời gian JDBC, execution plan, heap allocation và p95/p99.
- Thiết kế fetch plan để giảm round trip mà vẫn giữ đúng ngữ nghĩa nghiệp vụ và giới hạn bộ nhớ.

## 1. Vì sao fetch strategy ảnh hưởng hiệu năng?

JPA/Hibernate giúp ứng dụng Java thao tác với entity và quan hệ đối tượng, nhưng mỗi lần truy cập association có thể dẫn đến SQL. Cách lấy dữ liệu ảnh hưởng trực tiếp đến số lần round trip, số hàng database phải trả, kích thước kết quả truyền qua mạng, số entity được hydrate và lượng bộ nhớ ứng dụng sử dụng.

Một repository method có thể trông ngắn nhưng tạo ra hàng trăm câu SQL. Ngược lại, một câu JOIN lớn có thể trả về hàng nghìn hàng lặp lại và tải nhiều cột mà màn hình chỉ cần một vài trường.

Trong module DATABASE_PERFORMANCE, fetch strategy là một phần của đường truy cập dữ liệu giữa Java và database. Cần đánh giá cả hai đầu: execution plan và lượng dữ liệu database phải đọc, cùng số round trip, số object, allocation và GC ở JVM.

Ba câu hỏi cần trả lời trước khi chọn cách tải:

- Use case thực sự cần những thuộc tính nào?
- Cần những association nào, và cần bao nhiêu hàng từ mỗi association?
- Có thể lấy dữ liệu cần thiết bằng một truy vấn có cardinality hợp lý, hay nên dùng một số truy vấn theo batch?

## 2. Mô hình ví dụ và hai loại chi phí

Giả sử hệ thống thương mại điện tử có `Customer`, `Order` và `OrderItem`:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String name;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<Order> orders = new ArrayList<>();
}

@Entity
public class Order {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();

    private Instant createdAt;
    private BigDecimal totalAmount;
}
```

Đây là ví dụ rút gọn; entity thực tế cần constructor, getter, setter hoặc access strategy phù hợp.

Fetch strategy tạo ra hai nhóm chi phí chính:

1. **Chi phí truy vấn và truyền dữ liệu:** số round trip, thời gian server, số hàng đọc/trả, số byte trên network, logical/physical reads.
2. **Chi phí phía JVM:** tạo entity/proxy/collection, dirty checking, persistence context, mapping, allocation, garbage collection và giữ connection/transaction.

Giảm query count chưa chắc giảm tổng chi phí. Một JOIN có thể giảm 50 round trip nhưng nhân một customer thành 200 hàng do nhiều order và item; database, network và JVM đều phải xử lý phần dữ liệu lặp.

## 3. Lazy và eager loading

JPA định nghĩa hai kiểu fetch cơ bản:

- `FetchType.LAZY`: association hoặc thuộc tính được tải khi ứng dụng truy cập, thông qua proxy, collection wrapper hoặc cơ chế provider.
- `FetchType.EAGER`: provider phải cung cấp dữ liệu association khi entity được tải theo yêu cầu mapping, nhưng không có nghĩa bắt buộc phải dùng một SQL JOIN duy nhất.

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
private List<Order> orders;
```

Với `LAZY`, ứng dụng có thể chỉ tải Customer trước. Khi gọi `customer.getOrders()`, Hibernate có thể phát truy vấn bổ sung. Với `EAGER`, provider phải đảm bảo association sẵn sàng theo hợp đồng fetch, nhưng có thể dùng JOIN hoặc các SELECT riêng tùy query và provider.

### Vì sao nên thận trọng với EAGER?

Fetch type là mặc định của mapping, không phải kế hoạch tối ưu cho mọi màn hình hoặc API. Một association được đặt EAGER có thể bị tải trong use case chỉ cần vài trường của entity. Khi nhiều association EAGER kết hợp, lượng dữ liệu và số truy vấn có thể tăng khó dự đoán.

Trong nhiều ứng dụng, đặt association LAZY rồi chọn fetch plan cụ thể tại query/repository theo từng use case giúp kiểm soát tốt hơn. Tuy nhiên, LAZY cũng cần transaction/session phù hợp và fetch plan rõ ràng trước khi serialize hoặc rời khỏi persistence context.

### Lazy loading và lỗi ngoài transaction

Nếu ứng dụng truy cập association LAZY sau khi EntityManager/Session đã đóng, provider có thể ném `LazyInitializationException` trong Hibernate hoặc lỗi tương ứng. Bật Open Session in View có thể làm lỗi biến mất nhưng cũng có thể khiến truy vấn phát sinh ở tầng web/serialization và khó quan sát.

Hãy tải dữ liệu cần thiết trong transaction/service boundary, sau đó trả DTO đã hoàn chỉnh. Không để quá trình serialize JSON vô tình kích hoạt hàng loạt truy vấn.

## 4. N+1 query: biểu hiện và chi phí

N+1 xảy ra khi ứng dụng chạy một truy vấn lấy N entity, rồi phát thêm một truy vấn cho mỗi entity để lấy association hoặc thuộc tính liên quan.

Ví dụ:

```java
List<Customer> customers = customerRepository.findAllActive();

for (Customer customer : customers) {
    System.out.println(customer.getOrders().size());
}
```

Nếu có 100 customer, ứng dụng có thể chạy:

- 1 query lấy danh sách customer.
- 100 query lấy orders của từng customer.

Tổng số query là 101. Nếu mỗi query phụ mất 3 ms round trip, riêng phần gọi lặp có thể cộng thêm khoảng 300 ms trong trường hợp tuần tự; thời gian thực tế còn phụ thuộc cache, batching, network và server.

N+1 có thể xuất hiện khi:

- Duyệt collection LAZY trong vòng lặp.
- Gọi getter của association trong mapper hoặc serializer.
- Dùng `toString()`, `equals()` hoặc `hashCode()` truy cập association.
- Mapping entity sang DTO bằng thư viện tự động chạm vào nhiều quan hệ.
- Truy vấn một danh sách entity rồi gọi repository cho từng khóa.

### Cách phát hiện

- Ghi query count theo request hoặc transaction.
- Theo dõi cùng query fingerprint xuất hiện lặp lại với tham số khác nhau.
- Đếm số câu SQL trên mỗi API call và số hàng trả về mỗi câu.
- Bật Hibernate statistics hoặc datasource instrumentation trong môi trường kiểm thử.
- Viết integration test xác nhận số query không tăng tuyến tính theo số entity.

Không phải mọi query lặp đều là N+1. Một workload có thể cố ý đọc theo batch hoặc xử lý từng khóa; cần đối chiếu số lần gọi với kích thước tập dữ liệu và mục tiêu nghiệp vụ.

## 5. JOIN FETCH: tải association trong cùng truy vấn

JPQL `JOIN FETCH` yêu cầu provider lấy association cùng với entity gốc trong truy vấn đó. Đây là cách phổ biến để tránh N+1 khi cần association ngay.

Ví dụ lấy đơn hàng cùng khách hàng:

```java
@Query("""
    select o
    from Order o
    join fetch o.customer
    where o.createdAt >= :from
    """)
List<Order> findRecentWithCustomer(@Param("from") Instant from);
```

Vì `Order.customer` là quan hệ to-one, JOIN thường tạo tối đa một hàng kết hợp cho mỗi order nếu khóa đích duy nhất. Nếu cần giữ order không có customer (trong mô hình cho phép null), dùng `left join fetch` để giữ hàng bên trái.

### Fetch collection

Ví dụ lấy Customer cùng danh sách Order:

```java
@Query("""
    select distinct c
    from Customer c
    left join fetch c.orders
    where c.id in :ids
    """)
List<Customer> findCustomersWithOrders(@Param("ids") Collection<Long> ids);
```

`LEFT JOIN FETCH` giữ customer chưa có order. `distinct` thể hiện mong muốn nhận mỗi root entity một lần trong kết quả JPQL; cách provider loại trùng và SQL được sinh ra có thể khác nhau theo phiên bản.

Quan trọng: dù danh sách Java có thể chỉ có một Customer cho mỗi ID, database vẫn có thể trả một hàng cho mỗi cặp customer/order. Nếu một customer có 100 orders, thông tin cột customer có thể lặp trên 100 hàng mạng. `DISTINCT` ở tầng SQL không nhất thiết giảm các hàng này vì cột order khác nhau.

### JOIN FETCH không phải lúc nào cũng tốt

JOIN FETCH có thể gây:

- Nhân bản hàng gốc khi fetch collection.
- Tăng bytes truyền do cột entity gốc lặp lại.
- Tăng memory và công việc hydrate entity.
- Tạo Cartesian multiplication khi fetch nhiều collection.
- Làm phân trang không chính xác hoặc phải phân trang trong bộ nhớ tùy provider.

Hãy dùng JOIN FETCH cho association cần thiết và cardinality phù hợp. Đừng thêm mọi quan hệ vào một query chỉ để giảm query count.

## 6. To-one và to-many có đặc tính khác nhau

Fetch join quan hệ to-one như `ManyToOne` hoặc `OneToOne` thường dễ kiểm soát hơn vì mỗi hàng gốc có tối đa một hàng liên quan nếu ràng buộc dữ liệu đúng.

Fetch join quan hệ to-many như `OneToMany` hoặc `ManyToMany` làm số hàng kết quả tăng theo số phần tử collection. Nếu một customer có 10 orders và mỗi order có 5 items, JOIN đồng thời hai tầng có thể tạo đến 50 hàng cho customer đó.

Ví dụ:

```jpql
select distinct c
from Customer c
left join fetch c.orders o
left join fetch o.items
where c.id = :id
```

Truy vấn có thể trả một hàng cho mỗi tổ hợp order/item. Dữ liệu Customer và Order lặp lại trên nhiều hàng. Với collection lớn, chi phí network, sort/hash và hydrate object có thể vượt lợi ích giảm round trip.

### Cartesian multiplication

Nếu một Customer có 8 orders và 6 addresses độc lập, JOIN fetch cả hai collection có thể tạo 48 tổ hợp hàng cho customer đó. Nếu các collection tăng, số hàng trung gian tăng theo tích cardinality.

Với Hibernate, fetch đồng thời nhiều bag collection có thể dẫn đến `MultipleBagFetchException`. Đây là hành vi riêng của Hibernate, không phải thuật ngữ chung của JPA. Đổi List thành Set chỉ để né exception không giải quyết chi phí Cartesian multiplication.

Chiến lược thường tốt hơn là fetch một collection chính trong query, còn collection khác tải bằng batch hoặc truy vấn riêng theo tập ID.

## 7. Phân trang cùng collection fetch join

Phân trang entity gốc bằng `LIMIT/OFFSET` trong SQL không đơn giản khi JOIN một collection. Một root entity có thể chiếm nhiều hàng SQL, nên giới hạn hàng SQL có thể cắt giữa collection và không tương đương giới hạn số root entity.

Ví dụ không nên mặc định rằng query sau phân trang đúng và hiệu quả:

```java
@Query("""
    select distinct c
    from Customer c
    left join fetch c.orders
    order by c.id
    """)
Page<Customer> findPageWithOrders(Pageable pageable);
```

Tùy provider và cấu hình, Hibernate có thể cảnh báo, bỏ giới hạn SQL rồi phân trang trong bộ nhớ, hoặc có hành vi khác theo phiên bản. Điều này có thể tải toàn bộ tập kết quả trước khi cắt page, gây memory pressure và latency lớn.

### Mẫu hai bước: lấy ID rồi fetch dữ liệu

Bước 1: phân trang root ID bằng truy vấn gọn:

```java
@Query("""
    select c.id
    from Customer c
    where c.active = true
    order by c.id
    """)
Page<Long> findActiveCustomerIds(Pageable pageable);
```

Bước 2: lấy các customer trong page cùng association cần thiết:

```java
@Query("""
    select distinct c
    from Customer c
    left join fetch c.orders
    where c.id in :ids
    """)
List<Customer> findWithOrdersByIdIn(@Param("ids") Collection<Long> ids);
```

Ứng dụng giữ thứ tự ID từ bước 1 khi dựng kết quả cuối, vì `IN (:ids)` không bảo đảm thứ tự giống danh sách đầu vào. Nếu cần sắp xếp theo trường khác, có thể sắp xếp lại theo page IDs hoặc dùng query phù hợp.

Đối với trang rỗng, bỏ qua bước 2 để tránh `IN ()`. Cả hai bước nên chạy trong transaction/read consistency phù hợp nếu dữ liệu có thể thay đổi giữa hai truy vấn.

### Count query

Truy vấn đếm tổng số root entity không nên vô tình fetch collection. Dùng count query riêng với predicate tương ứng, không thêm `JOIN FETCH` vào count. Với Spring Data, có thể khai báo `countQuery` rõ ràng khi query phức tạp.

## 8. EntityGraph: mô tả fetch plan theo use case

JPA EntityGraph cho phép mô tả association hoặc thuộc tính cần được fetch khi thực hiện một truy vấn, mà không phải viết JOIN FETCH trong JPQL.

Ví dụ Spring Data JPA:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {
    @EntityGraph(attributePaths = {"customer"})
    List<Order> findByStatus(OrderStatus status);
}
```

EntityGraph ở đây yêu cầu association `customer` được fetch trong use case này. Provider quyết định cách triển khai vật lý, có thể dùng JOIN hoặc chiến lược khác. Cần xem SQL thực tế và execution plan.

### Named EntityGraph

```java
@Entity
@NamedEntityGraph(
    name = "Order.withCustomerAndItems",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode(value = "items", subgraph = "items.product")
    },
    subgraphs = {
        @NamedSubgraph(
            name = "items.product",
            attributeNodes = @NamedAttributeNode("product")
        )
    }
)
public class Order {
    // fields
}
```

Áp dụng graph bằng repository hoặc EntityManager:

```java
@EntityGraph(value = "Order.withCustomerAndItems")
Optional<Order> findWithDetailsById(Long id);
```

Ví dụ minh họa cách khai báo graph có subgraph. Tên graph, attribute path và cú pháp cần khớp với mapping entity thực tế.

### fetchgraph và loadgraph

JPA định nghĩa hai loại hint:

- `jakarta.persistence.fetchgraph`: thuộc tính có trong graph được xem là EAGER cho lần fetch này; thuộc tính không có trong graph được xem là LAZY theo ngữ nghĩa graph.
- `jakarta.persistence.loadgraph`: thuộc tính có trong graph được xem là EAGER; thuộc tính không có trong graph giữ fetch behavior mặc định của mapping.

Provider vẫn có thể fetch thêm dữ liệu theo quyền của đặc tả hoặc giới hạn triển khai; EntityGraph mô tả yêu cầu fetch, không bảo đảm một hình dạng SQL cụ thể hay số câu SQL chính xác.

Ví dụ dùng EntityManager:

```java
EntityGraph<Order> graph = entityManager.createEntityGraph(Order.class);
graph.addAttributeNodes("customer", "items");

Order order = entityManager.find(
    Order.class,
    orderId,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
```

EntityGraph phù hợp khi muốn tái sử dụng một query predicate nhưng thay đổi dữ liệu association cần lấy theo use case. Tuy nhiên, graph chứa collection vẫn có thể làm tăng số hàng hoặc khiến provider phát nhiều query; luôn đo SQL thực tế.

## 9. DTO projection: chỉ lấy cột cần thiết

DTO projection phù hợp khi API hoặc màn hình chỉ cần một tập trường cố định, không cần toàn bộ entity và association được quản lý.

Ví dụ:

```java
public record OrderSummary(
    Long orderId,
    String customerName,
    Instant createdAt,
    BigDecimal totalAmount
) {}
```

JPQL constructor projection:

```java
@Query("""
    select new com.example.api.OrderSummary(
        o.id,
        c.name,
        o.createdAt,
        o.totalAmount
    )
    from Order o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc
    """)
List<OrderSummary> findSummaries(@Param("status") OrderStatus status);
```

JPQL constructor expression yêu cầu tên lớp đầy đủ và constructor tương thích với kiểu/thứ tự biểu thức. Java record có canonical constructor nên có thể dùng nếu provider hỗ trợ constructor projection theo đặc tả và phiên bản đang chạy.

DTO projection chỉ chọn các cột cần dùng, không cần hydrate toàn bộ entity graph. Điều này thường giảm bytes truyền, object allocation, dirty checking và áp lực persistence context.

### Interface projection trong Spring Data

```java
public interface OrderListRow {
    Long getId();
    Instant getCreatedAt();
    BigDecimal getTotalAmount();
    String getCustomerName();
}
```

Spring Data JPA có thể tạo projection từ query phù hợp, nhưng cách SQL được sinh phụ thuộc loại projection, query method và provider. Kiểm tra SQL để bảo đảm chỉ các cột cần thiết được chọn.

### DTO projection không phải entity

DTO không được quản lý như entity trong persistence context. Thay đổi field DTO không tự động được dirty checking và lưu xuống database. Nếu cần cập nhật, ứng dụng phải gọi command/update rõ ràng hoặc tải entity trong transaction tương ứng.

DTO projection đặc biệt hữu ích cho:

- Danh sách và trang tìm kiếm.
- Báo cáo tổng hợp.
- API chỉ đọc.
- Màn hình dashboard.
- Export dữ liệu với số lượng lớn.

## 10. So sánh JOIN FETCH, EntityGraph và DTO projection

| Cách tải | Mục tiêu | Ưu điểm | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| JOIN FETCH | Lấy entity và association trong query JPQL/HQL | Kiểm soát trực tiếp join và phù hợp use case cụ thể | Nhân hàng, Cartesian multiplication, vấn đề phân trang collection |
| EntityGraph | Khai báo fetch plan tách khỏi predicate query | Tái sử dụng query, có thể đặt graph theo repository method/use case | Provider quyết định SQL; graph không bảo đảm một JOIN hay ít hàng hơn |
| DTO projection | Lấy đúng cột cần cho output | Giảm entity hydration, dirty checking, bytes và memory | Không có entity management; cần mapping/constructor rõ ràng |
| Batch fetching | Tải nhiều association theo nhóm ID | Tránh N+1 mà không JOIN mọi collection vào một result set | Vẫn có nhiều query; batch size cần đo |
| Truy vấn riêng theo tập ID | Tách dữ liệu gốc và collection thành các query có kiểm soát | Tránh Cartesian multiplication và hỗ trợ phân trang | Cần ghép kết quả và quản lý transaction/consistency |

Không có phương án tốt nhất cho mọi use case. Chọn theo cardinality, số cột cần, kích thước collection, yêu cầu cập nhật entity và kiểu truy vấn.

## 11. Batch fetching và subselect fetching

Khi cần collection nhưng JOIN tạo quá nhiều hàng, batch fetching là một lựa chọn trung gian. Thay vì một query cho mỗi entity, provider gom nhiều ID rồi tải association bằng một câu IN.

Ví dụ cấu hình Hibernate:

```java
@BatchSize(size = 32)
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
private List<Order> orders = new ArrayList<>();
```

Hoặc cấu hình mặc định:

```properties
hibernate.default_batch_fetch_size=32
```

`@BatchSize` là annotation riêng của Hibernate, không thuộc JPA chuẩn. Khi truy cập collection của một số Customer đã được load, Hibernate có thể tải collection của một nhóm customer bằng một query thay vì từng query riêng.

Batch size là tham số cần benchmark. Giá trị quá nhỏ vẫn tạo nhiều round trip; quá lớn tạo danh sách IN dài, result lớn và có thể vượt giới hạn tham số hoặc tạo memory spike.

### Subselect fetching

Hibernate có cơ chế subselect fetching cho một số association collection: khi một collection được truy cập, provider có thể tải collection cho các owner đã được truy vấn trước đó bằng một truy vấn phụ dựa trên truy vấn gốc. Cơ chế và điều kiện áp dụng phụ thuộc Hibernate và context của persistence session.

Subselect có thể hữu ích khi ứng dụng tải một tập root entity rồi cần cùng loại collection cho phần lớn root. Tuy nhiên, nếu root query phức tạp hoặc tập kết quả lớn, query phụ có thể cũng rất nặng. Hãy kiểm tra SQL và số hàng.

## 12. Chi phí overfetching

Overfetching là tải dữ liệu nhiều hơn use case cần. Nó có thể xảy ra khi:

- Dùng `SELECT entity` trong khi chỉ cần 3 cột.
- Fetch cả collection lớn cho màn hình chỉ hiển thị số lượng.
- Đặt EAGER cho association được dùng ở rất ít use case.
- JOIN nhiều collection và lặp lại dữ liệu root.
- Tải BLOB, JSON lớn hoặc trường văn bản dài trong danh sách.
- Lấy toàn bộ kết quả rồi lọc hoặc phân trang ở Java.

Chi phí overfetching gồm:

1. **Database work:** đọc thêm page, join thêm bảng, sort/hash thêm dữ liệu.
2. **Network:** truyền thêm hàng và byte, tăng round trip nếu cách tải gây N+1.
3. **Driver:** buffer, decode và chuyển đổi thêm giá trị.
4. **JVM:** tạo entity/proxy/collection/DTO, tăng heap allocation và GC.
5. **Persistence context:** giữ entity managed, snapshot và trạng thái dirty checking.
6. **Connection/transaction:** giữ connection và snapshot lâu hơn khi stream hoặc duyệt tập lớn.

Ví dụ danh sách đơn hàng chỉ hiển thị mã đơn, ngày và tổng tiền nhưng lại fetch toàn bộ `items`, `product`, `customer.address` và ảnh sản phẩm. Màn hình có thể chỉ cần một DTO với bốn trường; fetch entity graph đầy đủ làm tăng dữ liệu và object mà không tạo giá trị cho người dùng.

### Ước lượng dữ liệu truyền

Nếu 500 đơn hàng, mỗi đơn trung bình có 8 item, JOIN collection có thể tạo khoảng 4.000 hàng kết quả. Nếu mỗi hàng lặp 300 byte dữ liệu order và thêm 150 byte item, lượng payload logic xấp xỉ 4.000 × 450 byte = 1,8 MB trước overhead giao thức. Con số này chỉ minh họa; kích thước thực phụ thuộc kiểu cột, encoding, null, protocol và compression.

DTO chỉ lấy mã đơn, ngày, tổng tiền và tên khách có thể trả 500 hàng hẹp hơn nhiều. Nhưng nếu màn hình cần item detail, DTO summary sẽ thiếu dữ liệu; cần chọn fetch plan theo đúng use case.

## 13. Tránh lọc collection fetch join như thể đó là collection đầy đủ

Khi cần một tập con của association, cần cẩn thận với việc fetch một phần collection rồi để entity manager coi collection đó đã được tải đầy đủ.

Ví dụ nghiệp vụ muốn hiển thị các đơn PAID của customer. Một query JOIN để lấy các cặp customer/order đã lọc có thể phù hợp cho DTO:

```java
@Query("""
    select new com.example.api.CustomerPaidOrderRow(
        c.id, c.name, o.id, o.totalAmount
    )
    from Customer c
    join c.orders o
    where o.status = :status
    """)
List<CustomerPaidOrderRow> findPaidOrders(@Param("status") OrderStatus status);
```

Không nên mặc định gán tập con này vào `customer.getOrders()` như thể đó là toàn bộ association. Entity collection được quản lý có ngữ nghĩa là quan hệ đã load theo mapping; partial initialization có thể gây nhầm lẫn trong code và cập nhật.

Nếu cần collection đầy đủ, tải đầy đủ theo fetch plan. Nếu chỉ cần subset để hiển thị, dùng DTO projection hoặc query riêng trả về các hàng phù hợp.

## 14. Index và execution plan vẫn quan trọng

Fetch join và EntityGraph quyết định dữ liệu cần lấy, nhưng không bảo đảm truy vấn có access path tốt. Database vẫn cần index cho predicate và join key.

Ví dụ query lấy order theo status và ngày, đồng thời join customer:

```sql
SELECT o.id, o.created_at, o.total_amount, c.name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = ?
  AND o.created_at >= ?
ORDER BY o.created_at DESC;
```

Những điểm cần xem:

- `orders.customer_id` có index hoặc được hỗ trợ bởi khóa phù hợp không?
- Predicate `status` và `created_at` có thể tận dụng composite index nào không?
- Join có ước lượng cardinality hợp lý không?
- Có sort lớn do ORDER BY không?
- Có scan nhiều hàng rồi mới loại bỏ không?
- Số hàng thực tế có phù hợp với estimated rows không?
- Projection có lấy cột rộng không cần thiết không?

Index có thể giúp filter và join nhưng cũng làm tăng chi phí ghi. Thiết kế theo workload đọc/ghi tổng thể, không tạo index chỉ vì thấy một association.

## 15. Đo SQL thực tế từ Hibernate/JPA

Để kiểm chứng fetch plan, cần quan sát SQL được phát ra chứ không chỉ đọc annotation.

Các metric nên thu thập:

- Số câu SQL trên mỗi request hoặc transaction.
- Query fingerprint và số lần lặp.
- Thời gian execute-call và tổng thời gian tiêu thụ kết quả.
- Số hàng trả về, số hàng examined và bytes truyền nếu có.
- Số entity/collection được hydrate.
- Kích thước persistence context hoặc số entity managed.
- Heap allocation, GC pause và peak heap.
- Connection acquisition, transaction duration và lock wait.

### Hibernate statistics

Có thể bật statistics trong môi trường kiểm thử hoặc khi điều tra:

```properties
hibernate.generate_statistics=true
```

Ví dụ lấy thống kê qua SessionFactory:

```java
Statistics statistics = sessionFactory.getStatistics();

long queryCount = statistics.getQueryExecutionCount();
long entityFetches = statistics.getEntityFetchCount();
long collectionFetches = statistics.getCollectionFetchCount();
long preparedStatements = statistics.getPrepareStatementCount();
```

API statistics và tên metric có thể thay đổi theo Hibernate version. Các bộ đếm thường là tích lũy ở phạm vi SessionFactory; cần chụp snapshot trước/sau cửa sổ hoặc dùng công cụ telemetry phù hợp khi có nhiều request đồng thời.

Statistics có thể thêm overhead và không phải lúc nào cũng cho biết query nào thuộc request nào. Kết hợp datasource proxy, JDBC instrumentation hoặc tracing để có tương quan theo request.

### SQL logging

Có thể bật log SQL trong môi trường phát triển để xem câu lệnh, nhưng không nên ghi toàn bộ SQL và bind value nhạy cảm ở production mà không có kiểm soát. Log quá nhiều cũng làm tăng I/O và ảnh hưởng latency.

Ưu tiên query fingerprint, sampling và công cụ thống kê câu lệnh. Nếu cần xem bind parameter, dùng dữ liệu thử nghiệm hoặc che thông tin nhạy cảm.

## 16. Đo execution plan và số hàng ở database

JDBC metrics cho biết thời gian phía ứng dụng. Cần đối chiếu với server-side plan để xác định database có đọc quá nhiều hàng hoặc tạo kết quả trung gian lớn không.

### PostgreSQL

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, o.created_at, o.total_amount, c.name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'PAID'
  AND o.created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
ORDER BY o.created_at DESC;
```

Xem actual rows, loops, buffers, sort, join algorithm và chênh lệch estimated/actual rows. `EXPLAIN ANALYZE` thực thi truy vấn nên cần chọn môi trường và dữ liệu phù hợp.

### MySQL

`EXPLAIN ANALYZE` ở các phiên bản hỗ trợ cung cấp actual rows, loops và thời gian của iterator. Kết hợp Performance Schema statement digest để xem số lần gọi, rows examined, rows sent và thời gian tích lũy.

### SQL Server

Actual execution plan, `SET STATISTICS IO, TIME ON` và Query Store giúp xem operator, logical reads, CPU, elapsed time và plan regression.

Không chỉ xem tổng thời gian. Một query có server execution 15 ms nhưng trả 50.000 hàng có thể mất nhiều thời gian ở network, driver và mapping. Ngược lại, query trả 10 hàng nhưng server scan hàng triệu hàng có thể cần tối ưu index/predicate.

## 17. Thiết kế fetch plan theo từng use case

Không nên tạo một fetch plan dùng chung cho mọi màn hình. Hãy phân loại use case:

| Use case | Dữ liệu cần | Chiến lược thường cân nhắc |
| --- | --- | --- |
| Trang danh sách đơn | ID, ngày, trạng thái, tổng tiền, tên khách | DTO projection; JOIN to-one |
| Trang chi tiết một đơn | Đơn, khách, danh sách item và sản phẩm | JOIN FETCH hoặc EntityGraph cho to-one và collection nhỏ; batch cho collection lớn |
| Trang danh sách khách có số đơn | ID, tên, count | DTO projection với GROUP BY/aggregate |
| API trả nhiều customer và orders | Root page và collection có giới hạn | Page IDs trước, rồi fetch theo batch hoặc query riêng |
| Export hàng triệu dòng | Một tập cột cố định, xử lý streaming | DTO/scalar projection, fetch size/cursor theo driver, chia key range |
| Cập nhật entity | Entity và trường cần thay đổi | Load entity tối thiểu trong transaction, tránh fetch graph không liên quan |

Ví dụ trang danh sách chỉ cần tổng số đơn của khách:

```java
public record CustomerOrderCount(Long customerId, String name, Long orderCount) {}

@Query("""
    select new com.example.api.CustomerOrderCount(
        c.id, c.name, count(o)
    )
    from Customer c
    left join c.orders o
    where c.active = true
    group by c.id, c.name
    """)
List<CustomerOrderCount> findCustomerOrderCounts();
```

Projection aggregate tránh hydrate toàn bộ `Order` chỉ để đếm. Cần kiểm tra index trên khóa ngoại và plan aggregate.

## 18. Kết hợp EntityGraph và DTO projection đúng chỗ

EntityGraph phù hợp khi cần entity managed với một số association cụ thể. DTO projection phù hợp khi chỉ cần dữ liệu đọc và muốn kiểm soát chính xác cột đầu ra.

Ví dụ:

- Luồng chỉnh sửa đơn cần load entity `Order` cùng `Customer` để áp dụng quy tắc domain: EntityGraph có thể phù hợp.
- API danh sách 50 đơn chỉ hiển thị mã, ngày và tên khách: DTO projection thường phù hợp hơn.
- Trang chi tiết đơn có 5 item: fetch join hoặc EntityGraph có thể đủ.
- Báo cáo có hàng triệu item: projection streaming hoặc truy vấn theo batch thường phù hợp hơn tải entity graph.

Không nên dùng DTO projection để thay thế entity trong mọi tình huống nếu cần domain behavior, cascade hoặc dirty checking. Ngược lại, không nên hydrate entity đầy đủ chỉ để xuất một bảng báo cáo.

## 19. Cache không phải cách sửa fetch plan

First-level cache của persistence context có thể tránh tải lại cùng một entity trong một Session, nhưng không ngăn N+1 trên các association khác nhau. Second-level cache hoặc query cache có thể giảm database access trong một số workload, nhưng vẫn có chi phí lookup, invalidation và đồng bộ.

Cache có thể làm benchmark N+1 trông nhanh hơn nếu dữ liệu đã nóng, nhưng cold cache hoặc nhiều key khác nhau vẫn tạo nhiều query. Hãy đo cả cache hit/miss và query count; không dùng cache để che một fetch plan tạo round trip không cần thiết.

Cache cũng không giảm overfetching nếu ứng dụng vẫn hydrate hàng nghìn entity và giữ chúng trong persistence context. Cần chọn đúng dữ liệu ngay từ query.

## 20. Benchmark so sánh các fetch strategy

Để so sánh JOIN FETCH, EntityGraph, DTO và batch fetching, dùng cùng dữ liệu và cùng use case.

Chuẩn bị:

- Cùng số root entity và phân bố cardinality của association.
- Có cả trường hợp collection rỗng, nhỏ, trung bình và rất lớn.
- Cùng điều kiện lọc, thứ tự và giới hạn page.
- Cùng database, index, driver, pool và network.
- Tách warm-up, cold cache và warm cache nếu cả hai đều quan trọng.
- Chạy cùng concurrency và số lượng request.

Đo:

- Query count và round trip.
- Rows returned, rows examined và bytes truyền.
- Execute-call, result-consume và tổng request latency.
- Database CPU, logical/physical reads và temp spill.
- Heap allocation, GC pause và số entity managed.
- Connection acquisition và transaction duration.
- p50/p95/p99, throughput và error rate.

Ví dụ kết quả minh họa:

| Fetch plan | SQL/query count | Rows trả về | p95 request | Heap allocation/request |
| --- | ---: | ---: | ---: | ---: |
| Lazy N+1 cho 50 customer | 51 | 50 customer + collection queries | 420 ms | 8 MB |
| JOIN FETCH một collection | 1 | 600 hàng join | 180 ms | 5 MB |
| DTO projection summary | 1 | 50 hàng hẹp | 55 ms | 0,8 MB |
| Batch fetching size 25 | 3 | 50 root và collection theo batch | 130 ms | 3 MB |

Các con số chỉ minh họa. DTO projection nhanh hơn trong ví dụ vì use case chỉ cần dữ liệu summary; nó không tương đương về dữ liệu với truy vấn tải toàn bộ collection. So sánh công bằng phải bảo đảm các phương án trả cùng kết quả nghiệp vụ.

## 21. Quy trình tối ưu fetch strategy

1. **Xác định use case.** Ghi rõ response cần trường nào và association nào.
2. **Đo hiện trạng.** Thu query count, query fingerprint, acquisition, execute, result consume, rows và latency.
3. **Phát hiện N+1/overfetch.** Tìm query lặp, collection được tải không dùng, payload rộng và entity count bất thường.
4. **Chọn cách tải.** JOIN FETCH cho quan hệ cần join và cardinality phù hợp; EntityGraph cho fetch plan entity; DTO cho read model; batch cho collection lớn hoặc nhiều root.
5. **Kiểm tra phân trang.** Không áp dụng collection fetch join với page root mà chưa xác minh SQL và hành vi provider.
6. **Kiểm tra SQL thực tế.** Xem số câu lệnh, select list, join, số hàng, index và execution plan.
7. **Đo chi phí hai phía.** Database reads/CPU/network và JVM allocation/GC/persistence context.
8. **Kiểm tra tính đúng.** Bao gồm root không có association, collection rỗng, cardinality lớn, dữ liệu đồng thời thay đổi và thứ tự page.
9. **Benchmark lại.** Chạy cùng dữ liệu và concurrency, so sánh p95/p99, throughput và bytes.
10. **Theo dõi sau triển khai.** Kiểm tra query count, pool, GC và plan regression theo thời gian.

## 22. Những sai lầm thường gặp

- **Đổi mọi association sang EAGER.** Có thể tải thừa dữ liệu và tạo SQL khó dự đoán.
- **Dùng JOIN FETCH cho mọi collection.** Có thể nhân hàng, tạo Cartesian multiplication và tăng memory.
- **Cho rằng EntityGraph luôn tạo một JOIN.** Provider quyết định cách thực thi; phải xem SQL thực tế.
- **Dùng collection fetch join với pagination mà không kiểm tra.** Có thể phân trang sai ở mức SQL hoặc tải toàn bộ rồi cắt trong memory.
- **Nghĩ `DISTINCT` luôn giảm bytes truyền.** Entity có thể được khử trùng ở ORM trong khi các hàng SQL vẫn được truyền đầy đủ.
- **Fetch hai bag collection cùng lúc trong Hibernate.** Có thể gặp `MultipleBagFetchException` và/hoặc Cartesian multiplication.
- **Dùng DTO projection nhưng kỳ vọng dirty checking.** DTO không phải entity managed.
- **Để serializer truy cập LAZY association.** Có thể phát sinh query ngoài service transaction hoặc lỗi lazy initialization.
- **Chỉ đo query count.** Một JOIN có ít query nhưng có thể trả quá nhiều hàng và byte.
- **Dựa vào cache để che N+1.** Cold cache hoặc key khác nhau vẫn có thể tạo nhiều round trip.
- **Không kiểm tra query count trong test.** Thay đổi mapping hoặc mapper có thể đưa N+1 trở lại.
- **Fetch dữ liệu rồi lọc ở Java.** Có thể chuyển filter, projection và limit xuống database để giảm truyền dữ liệu.

## 23. Danh sách kiểm tra trước khi triển khai

- [ ] Đã xác định các trường và association use case thực sự cần.
- [ ] Mapping LAZY/EAGER phù hợp và không dựa vào EAGER như fetch plan chung.
- [ ] Không còn N+1 không chủ đích trên request chính.
- [ ] JOIN FETCH chỉ áp dụng cho association có cardinality phù hợp.
- [ ] Đã đánh giá số hàng lặp và bytes của collection fetch join.
- [ ] Không fetch nhiều collection gây Cartesian multiplication.
- [ ] Pagination root được thực hiện an toàn, có thể dùng page IDs trước rồi fetch theo batch.
- [ ] Count query không chứa fetch join không cần thiết.
- [ ] EntityGraph được kiểm tra SQL thực tế và không bị hiểu nhầm là cam kết một JOIN.
- [ ] DTO projection chỉ lấy cột cần thiết và không bị kỳ vọng dirty checking.
- [ ] Batch size và fetch size được đo theo cardinality và network latency.
- [ ] Lazy loading không vô tình xảy ra trong serializer ngoài transaction.
- [ ] Đã đo query count, rows, bytes, p50/p95/p99 và throughput.
- [ ] Đã đo heap allocation, GC, persistence context và database execution plan.
- [ ] Integration test kiểm tra số query và kết quả nghiệp vụ với dữ liệu biên.

## Kết luận

Fetch join, EntityGraph, DTO projection và batch fetching là các cách xây dựng fetch plan cho từng use case Java. JOIN FETCH và EntityGraph có thể giảm N+1 khi association cần thiết và cardinality phù hợp, nhưng fetch collection có thể nhân hàng, tăng bytes và làm phân trang phức tạp. DTO projection giúp chỉ lấy các cột cần cho read model, giảm hydrate entity và chi phí JVM; batch fetching là lựa chọn trung gian khi collection lớn. Hãy chọn chiến lược theo dữ liệu thực sự cần, xem SQL và execution plan được sinh ra, rồi đo query count, rows, bytes, JDBC stage timings, heap/GC và p95/p99. Mục tiêu là giảm round trip và dữ liệu thừa mà vẫn giữ đúng kết quả nghiệp vụ.

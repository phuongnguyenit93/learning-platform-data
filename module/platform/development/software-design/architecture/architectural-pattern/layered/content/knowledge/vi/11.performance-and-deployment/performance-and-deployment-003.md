# Nhận diện N+1, lazy loading và tải dữ liệu dư thừa

*Chương: Hiệu năng và triển khai*

Bài học này thuộc module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED`, có mục tiêu **Học tổ chức phần mềm theo kiến trúc phân tầng**. Trong ứng dụng Java/Spring, tầng truy cập dữ liệu thường dùng JPA/Hibernate để chuyển đổi giữa đối tượng và bản ghi database. ORM giúp làm việc với quan hệ đối tượng thuận tiện, nhưng fetch strategy không phù hợp có thể tạo ra nhiều truy vấn hơn dự kiến hoặc tải nhiều dữ liệu hơn một ca sử dụng thực sự cần.

Hai vấn đề thường gặp là **N+1 query** và **overfetching**. N+1 xảy ra khi một truy vấn ban đầu lấy danh sách N đối tượng, sau đó ứng dụng phát sinh thêm truy vấn cho từng đối tượng hoặc từng quan hệ. Overfetching xảy ra khi truy vấn tải thừa cột, bản ghi hoặc quan hệ. Lazy loading trì hoãn việc tải quan hệ; nó giúp tránh tải dữ liệu không cần thiết, nhưng nếu truy cập quan hệ lặp lại trong vòng lặp, nó có thể kích hoạt N+1.

Mục tiêu không phải tải mọi quan hệ ngay từ đầu hay biến mọi truy vấn thành một câu SQL lớn. Cần chọn dữ liệu theo từng ca sử dụng, quan sát SQL thực tế và cân bằng giữa số truy vấn, lượng dữ liệu truyền, bộ nhớ, độ phức tạp truy vấn và khả năng bảo trì.

## 1. N+1 query là gì?

Giả sử trang quản trị hiển thị 20 đơn hàng gần đây. Ứng dụng chạy một truy vấn lấy danh sách đơn hàng, sau đó với mỗi đơn hàng lại truy vấn danh sách dòng hàng:

- 1 truy vấn lấy 20 đơn hàng.
- 20 truy vấn lấy dòng hàng của từng đơn.

Tổng cộng có 1 + 20 = 21 truy vấn. Đây là mẫu N+1: một truy vấn ban đầu cộng N truy vấn phát sinh khi duyệt kết quả.

Nếu mỗi dòng hàng lại truy cập sản phẩm và mỗi sản phẩm được tải riêng, số truy vấn có thể tăng thêm. Khi đó luồng thực tế có thể gần với 1 + N + M, trong đó M là số lần cần tải sản phẩm chưa có trong persistence context hoặc cache. Con số thực tế phụ thuộc quan hệ, cache, fetch strategy và dữ liệu cụ thể.

N+1 không có nghĩa luôn luôn có đúng N truy vấn bổ sung. Tên gọi mô tả cấu trúc vấn đề: truy vấn gốc trả về một tập kết quả, rồi một thao tác lặp theo từng phần tử tạo thêm truy vấn.

Ví dụ, mô hình đơn hàng có quan hệ một-nhiều:

```java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    private UUID id;

    private Instant createdAt;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    // Constructor, getter và các hành vi khác được lược bớt.
}

@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Order order;

    @ManyToOne(fetch = FetchType.LAZY)
    private Product product;

    private int quantity;
}
```

Repository có thể lấy danh sách đơn hàng:

```java
public interface OrderRepository extends JpaRepository<Order, UUID> {
    List<Order> findTop20ByOrderByCreatedAtDesc();
}
```

Một mapper hoặc service truy cập quan hệ trong vòng lặp:

```java
public List<OrderSummary> listRecentOrders() {
    return orders.findTop20ByOrderByCreatedAtDesc()
            .stream()
            .map(order -> new OrderSummary(
                    order.getId(),
                    order.getLines().size()
            ))
            .toList();
}
```

Truy vấn đầu tiên lấy các đơn hàng. Khi gọi `getLines()`, Hibernate có thể tải collection lazy riêng cho từng đơn hàng. Nếu danh sách có 20 đơn, số truy vấn có thể là 21. Một dòng mã ngắn có thể ẩn nhiều lần truy cập database.

## 2. Vì sao N+1 dễ bị bỏ sót?

N+1 thường không xuất hiện rõ trong unit test với một đối tượng hoặc một bộ dữ liệu nhỏ. Khi chỉ có một đơn hàng, một truy vấn ban đầu và một truy vấn quan hệ trông không đáng kể. Khi production có hàng trăm đơn hàng, số truy vấn tăng theo số bản ghi và thời gian phản hồi tăng rõ rệt.

Một số vị trí thường kích hoạt N+1:

- Mapper chuyển entity thành DTO và gọi getter của quan hệ lazy.
- Vòng lặp trong application service truy cập từng collection hoặc đối tượng liên quan.
- Serializer JSON đọc getter để tạo response khi entity còn được quản lý.
- Template hoặc view truy cập quan hệ mà tầng trình bày không chủ động tải trước.
- Một truy vấn danh sách tải entity, sau đó từng entity lại gọi repository để lấy thông tin liên quan.

Ví dụ, một mapper tưởng như chỉ chuyển đổi dữ liệu:

```java
OrderResponse toResponse(Order order) {
    List<OrderLineResponse> lines = order.getLines().stream()
            .map(line -> new OrderLineResponse(
                    line.getProduct().getName(),
                    line.getQuantity()
            ))
            .toList();

    return new OrderResponse(order.getId(), lines);
}
```

Nếu danh sách đơn hàng được tải mà không có fetch plan phù hợp, việc đọc `getLines()` và `getProduct().getName()` có thể kích hoạt truy vấn bổ sung. Mapper không trực tiếp gọi repository nhưng vẫn có thể là nơi phát sinh N+1.

Vì vậy, cần xem SQL thực tế được phát ra trong toàn bộ luồng xử lý, không chỉ đọc câu truy vấn repository ban đầu. Việc bật log SQL trong môi trường phát triển hoặc dùng công cụ quan sát truy vấn giúp phát hiện những truy vấn ẩn do lazy loading.

## 3. Lazy loading hoạt động như thế nào?

Lazy loading trì hoãn việc tải quan hệ cho đến khi ứng dụng thực sự truy cập quan hệ đó. Với JPA, có thể khai báo:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
```

Khi truy vấn đơn hàng, ORM có thể chỉ tải dữ liệu của bảng `orders`. Collection `lines` được biểu diễn bằng proxy hoặc collection được ORM quản lý. Khi gọi `order.getLines()`, ORM mới tải các dòng hàng nếu chúng chưa được nạp.

Lợi ích là một màn hình chỉ hiển thị mã đơn và ngày tạo không cần tải tất cả dòng hàng, sản phẩm, ảnh hoặc thông tin vận chuyển. Lazy loading có thể giảm dữ liệu truyền và bộ nhớ nếu quan hệ không được sử dụng.

Nhưng lazy loading có các điều kiện:

- Đối tượng hoặc proxy cần còn gắn với persistence context phù hợp khi quan hệ được truy cập.
- Truy cập quan hệ có thể phát sinh truy vấn database, dù mã gọi chỉ là getter.
- Truy cập cùng một quan hệ nhiều lần trên cùng entity thường không tạo truy vấn lặp nếu collection đã được tải trong persistence context.
- Truy cập quan hệ trên nhiều entity khác nhau có thể tạo nhiều truy vấn riêng, dẫn đến N+1.

Nếu truy cập một quan hệ lazy sau khi persistence context đã đóng, ứng dụng có thể gặp `LazyInitializationException`. Lỗi này cho thấy dữ liệu cần thiết không còn được tải trong phạm vi quản lý hiện tại. Không nên xử lý bằng cách bật tải EAGER toàn bộ quan hệ; cách đó có thể tạo overfetching và không đảm bảo loại bỏ N+1.

### Lazy và eager không phải lựa chọn toàn cục

JPA có các fetch type phổ biến:

| Fetch type | Ý nghĩa | Điểm cần lưu ý |
|---|---|---|
| LAZY | Trì hoãn tải quan hệ đến khi truy cập | Có thể tạo N+1 nếu truy cập lặp theo từng entity |
| EAGER | Yêu cầu provider tải quan hệ sớm theo ngữ nghĩa mapping | Provider có thể dùng join hoặc truy vấn riêng; không đảm bảo luôn chỉ có một SQL |

Với quan hệ to-one, mặc định JPA thường là EAGER; với to-many, mặc định thường là LAZY. Có thể khai báo rõ fetch type để thể hiện ý định. Tuy nhiên, EAGER không đồng nghĩa luôn join trong một truy vấn. Provider có thể phát thêm truy vấn để đáp ứng yêu cầu eager, đặc biệt khi tải nhiều entity trong một truy vấn.

Một thực hành thường hữu ích là giữ mapping ở mức LAZY cho những quan hệ có thể lớn, rồi xác định fetch plan theo từng use case. Với quan hệ to-one, hãy đánh giá kích thước và nhu cầu sử dụng trước khi chọn. Không nên đổi toàn bộ sang EAGER chỉ để tránh một lỗi lazy loading.

## 4. Nhận diện overfetching

Overfetching là tải nhiều dữ liệu hơn nhu cầu thực tế. Nó có thể xảy ra dù chỉ có một truy vấn SQL.

Ví dụ, trang danh sách chỉ cần mã đơn, ngày tạo, tên khách và tổng tiền nhưng truy vấn tải toàn bộ entity đơn hàng, toàn bộ dòng hàng, sản phẩm, ảnh, địa chỉ giao hàng và lịch sử thanh toán. Dữ liệu thừa làm tăng:

- Số byte đọc từ database và truyền qua mạng.
- Số đối tượng được tạo trong heap JVM.
- Chi phí mapping, serialization và garbage collection.
- Khả năng khóa hoặc giữ persistence context lâu hơn cần thiết.
- Độ phức tạp của truy vấn join và nguy cơ nhân số dòng kết quả.

Overfetching có thể xuất hiện theo hai hướng:

1. **Overfetching theo chiều rộng:** tải nhiều cột hoặc trường không được sử dụng, chẳng hạn tải mô tả sản phẩm dài và ảnh nhị phân cho một bảng chỉ hiển thị tên sản phẩm.
2. **Overfetching theo chiều sâu:** tải nhiều quan hệ hoặc nhiều cấp đối tượng, chẳng hạn từ đơn hàng tải dòng hàng, sản phẩm, tồn kho, nhà cung cấp và lịch sử thay đổi dù màn hình chỉ cần tổng số dòng hàng.

N+1 và overfetching có thể cùng xuất hiện. N+1 tạo quá nhiều lần round trip; một fetch join quá rộng có thể giảm số truy vấn nhưng tải quá nhiều dữ liệu hoặc tạo nhiều dòng kết quả trùng lặp. Tối ưu đúng cần xem cả số truy vấn lẫn lượng dữ liệu.

## 5. Chẩn đoán bằng SQL và số lượng truy vấn

Hãy bắt đầu bằng việc quan sát truy vấn trong một luồng cụ thể:

- Đếm số SQL statement cho một request hoặc một use case.
- Nhìn xem có một mẫu truy vấn lặp lại với tham số khác nhau hay không.
- So sánh số truy vấn khi dữ liệu có 1, 10, 50 hoặc 100 entity.
- Xem số dòng kết quả và số cột được tải.
- Kiểm tra thời gian database, thời gian chờ connection pool và thời gian mapping ở ứng dụng.

Ví dụ N+1 có thể tạo log dạng:

```sql
select o.id, o.created_at
from orders o
order by o.created_at desc
fetch first 20 rows only;

select l.id, l.order_id, l.product_id, l.quantity
from order_lines l
where l.order_id = ?;

select l.id, l.order_id, l.product_id, l.quantity
from order_lines l
where l.order_id = ?;

-- Lặp lại truy vấn tương tự cho các đơn hàng còn lại.
```

Dấu hiệu đáng chú ý là cùng một câu SQL được thực thi nhiều lần, chỉ khác giá trị khóa ngoại. Có thể dùng log Hibernate SQL, datasource proxy, APM hoặc metric của database để quan sát. Khi cần tối ưu truy vấn cụ thể, hãy xem execution plan và index; chỉ đếm số truy vấn không cho biết toàn bộ chi phí.

Một truy vấn join có thể thực thi nhanh hơn nhiều truy vấn nhỏ, nhưng cũng có thể trả về hàng triệu dòng trung gian nếu join nhiều collection. Cần đo với kích thước dữ liệu gần thực tế.

## 6. Cách xử lý N+1 bằng fetch join

Với JPQL, fetch join tải quan hệ trong cùng truy vấn:

```java
public interface OrderRepository extends JpaRepository<Order, UUID> {
    @Query("""
           select distinct o
           from Order o
           left join fetch o.lines l
           left join fetch l.product
           where o.createdAt >= :from
           order by o.createdAt desc
           """)
    List<Order> findWithLinesAndProductsSince(
            @Param("from") Instant from);
}
```

`join fetch` yêu cầu ORM tải quan hệ cùng lúc với entity gốc. `left join` giữ lại đơn hàng ngay cả khi chưa có dòng hàng. `distinct` diễn đạt kết quả entity gốc không trùng lặp khi join một quan hệ to-many; hành vi loại trùng ở kết quả entity còn phụ thuộc phiên bản provider, nhưng câu truy vấn nên thể hiện rõ ý định.

Cách này phù hợp khi màn hình hoặc use case thực sự cần dữ liệu của các quan hệ được fetch. Không nên fetch join mọi quan hệ chỉ để chắc chắn không còn truy vấn bổ sung.

Một lưu ý quan trọng: join một collection làm số dòng SQL tăng theo số phần tử collection. Nếu một đơn có 10 dòng hàng, dữ liệu của phần đơn có thể lặp lại trên 10 dòng kết quả. Join nhiều collection to-many cùng lúc có thể tạo tích Descartes, làm dữ liệu trả về phình lớn hoặc khiến Hibernate báo lỗi với một số kiểu collection như multiple bag fetch. Hãy chọn quan hệ cần fetch và đo số dòng thực tế.

## 7. Dùng EntityGraph để khai báo fetch plan

Spring Data JPA hỗ trợ khai báo các quan hệ cần tải qua `@EntityGraph`:

```java
public interface OrderRepository extends JpaRepository<Order, UUID> {

    @EntityGraph(attributePaths = {
            "lines",
            "lines.product"
    })
    List<Order> findByStatusOrderByCreatedAtDesc(
            OrderStatus status);
}
```

EntityGraph mô tả những thuộc tính cần được tải cho truy vấn này mà không phải viết trực tiếp join fetch trong JPQL. Provider quyết định cách thực hiện theo mapping và khả năng của nó. EntityGraph có thể giúp repository method diễn đạt fetch plan theo use case và giữ query dễ đọc.

Có thể dùng named entity graph trong mapping hoặc dynamic entity graph trên repository method. Dù chọn cách nào, hãy kiểm tra SQL phát sinh; khai báo graph không phải lời cam kết rằng provider luôn tạo đúng một câu SQL hoặc luôn tải dữ liệu tối thiểu.

## 8. Batch fetching khi join không phù hợp

Trong một số trường hợp, fetch join collection không phù hợp, chẳng hạn khi cần phân trang hoặc không muốn nhân số dòng kết quả. Hibernate hỗ trợ batch fetching để tải quan hệ lazy của nhiều entity bằng một truy vấn dùng danh sách khóa.

Có thể cấu hình ở collection:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderLine> lines = new ArrayList<>();
```

Hoặc cấu hình mặc định batch fetch cho Hibernate qua thuộc tính cấu hình tương ứng, chẳng hạn `hibernate.default_batch_fetch_size`.

Thay vì phát một truy vấn cho từng order, Hibernate có thể gom các order id thành nhóm rồi chạy dạng:

```sql
select l.id, l.order_id, l.product_id, l.quantity
from order_lines l
where l.order_id in (?, ?, ?, ...);
```

Nếu có 100 đơn và batch size là 32, số truy vấn tải collection có thể giảm xuống khoảng 4 thay vì 100, tùy provider, số quan hệ thực sự được truy cập và giới hạn của database. Batch fetching giảm round trip nhưng vẫn tải toàn bộ collection được yêu cầu; nó không phải cách loại bỏ overfetching nếu mỗi collection chứa quá nhiều dữ liệu.

Chọn batch size dựa trên kích thước dữ liệu, giới hạn bind parameter của database và kết quả đo. Một giá trị quá lớn có thể tạo câu SQL dài hoặc tải nhiều dữ liệu cùng lúc.

## 9. Dùng DTO projection khi chỉ cần một phần dữ liệu

Nếu màn hình chỉ cần một vài trường, không nhất thiết phải tải entity đầy đủ và sau đó truy cập quan hệ. Projection có thể lấy trực tiếp dữ liệu cần thiết.

Ví dụ, danh sách đơn hàng chỉ hiển thị mã đơn, thời điểm tạo và tên khách hàng:

```java
public record OrderListItem(
        UUID id,
        Instant createdAt,
        String customerName) {
}
```

Repository dùng JPQL constructor expression:

```java
public interface OrderRepository extends JpaRepository<Order, UUID> {

    @Query("""
           select new com.example.orders.OrderListItem(
               o.id,
               o.createdAt,
               c.name
           )
           from Order o
           join o.customer c
           where o.status = :status
           order by o.createdAt desc
           """)
    Page<OrderListItem> findListItems(
            @Param("status") OrderStatus status,
            Pageable pageable);
}
```

Truy vấn lấy đúng ba trường cần hiển thị và trả thẳng DTO. Nó không cần tải collection dòng hàng hay entity sản phẩm. Projection đặc biệt hữu ích cho trang danh sách, báo cáo và truy vấn chỉ đọc.

DTO projection có trade-off: câu truy vấn gắn với hình dạng dữ liệu của màn hình, và có thể cần một query khác khi use case khác yêu cầu dữ liệu khác. Đây là điều bình thường nếu truy vấn được đặt tên theo mục đích rõ ràng. Không nên ép mọi use case dùng một DTO quá rộng chỉ để giảm số lớp.

Với truy vấn thống kê, có thể dùng aggregate như `count`, `sum` hoặc `group by` để database tính toán thay vì tải từng entity về JVM rồi cộng trong Java. Hãy đảm bảo phép tính trong SQL có cùng ngữ nghĩa làm tròn, null và đơn vị với quy tắc nghiệp vụ.

## 10. N+1 và phân trang collection

Một lỗi thường gặp là kết hợp phân trang với fetch join collection to-many:

```java
@Query("""
       select distinct o
       from Order o
       left join fetch o.lines
       where o.status = :status
       order by o.createdAt desc
       """)
Page<Order> findPageWithLines(
        @Param("status") OrderStatus status,
        Pageable pageable);
```

Khi một đơn hàng có nhiều dòng hàng, phân trang ở cấp SQL có thể cắt các dòng join thay vì cắt đúng số đơn hàng. Một số phiên bản Hibernate có thể cảnh báo và thực hiện phân trang trong bộ nhớ khi collection fetch được kết hợp với pagination. Điều đó có nguy cơ tải rất nhiều dữ liệu và làm mất lợi ích phân trang. Không nên dựa vào hành vi này cho tập dữ liệu lớn.

Một chiến lược thường dùng là hai bước:

1. Truy vấn trang các ID đơn hàng theo điều kiện và thứ tự ổn định.
2. Dùng danh sách ID đó tải entity cùng quan hệ cần thiết bằng fetch join hoặc EntityGraph.
3. Giữ thứ tự của trang ID ban đầu khi ghép kết quả, vì truy vấn `IN` không đảm bảo thứ tự nếu không có `ORDER BY`.

Ví dụ:

```java
@Query("""
       select o.id
       from Order o
       where o.status = :status
       order by o.createdAt desc, o.id desc
       """)
Page<UUID> findPageIds(
        @Param("status") OrderStatus status,
        Pageable pageable);

@Query("""
       select distinct o
       from Order o
       left join fetch o.lines
       where o.id in :ids
       """)
List<Order> findWithLinesByIdIn(
        @Param("ids") Collection<UUID> ids);
```

Application service lấy trang ID, gọi truy vấn thứ hai rồi sắp xếp kết quả theo thứ tự ID ban đầu. Nếu cần tổng số trang, query count của trang ID phải phản ánh đúng điều kiện lọc. Với trang chỉ đọc, một DTO projection có phân trang thường đơn giản và hiệu quả hơn.

## 11. Tránh để serialization và mapper vô tình tải dữ liệu

Trong ứng dụng Spring MVC, nếu controller trả thẳng JPA entity, Jackson có thể gọi getter để serialize quan hệ. Nếu persistence context còn mở, việc này có thể kích hoạt truy vấn lazy trong quá trình tạo JSON. Khi đó, truy vấn phát sinh ở tầng trình bày và khó nhận ra từ code controller.

Open Session in View (OSIV) có thể giữ persistence context mở trong suốt request web, giúp tránh một số lỗi lazy initialization. Nhưng nó cũng cho phép truy vấn database phát sinh muộn trong quá trình render response, làm ranh giới truy cập dữ liệu khó quan sát và có thể kéo dài thời gian giữ tài nguyên. OSIV không tự giải quyết N+1.

Một cách kiểm soát tốt là:

- Controller trả DTO response thay vì entity JPA.
- Application service hoặc query service lấy dữ liệu theo fetch plan phù hợp.
- Mapper chỉ đọc các trường đã được tải theo hợp đồng của use case.
- Không để tầng trình bày tự truy cập repository hoặc điều hướng quan hệ ORM.
- Nếu dự án dùng OSIV, hiểu rõ nơi phát sinh truy vấn và cân nhắc tắt hoặc giới hạn theo kiến trúc của ứng dụng.

Tắt OSIV có thể làm lộ các chỗ đang phụ thuộc vào lazy loading ngoài transaction qua `LazyInitializationException`. Đây là tín hiệu để xác định dữ liệu nào cần được tải trong use case và chuyển thành DTO trước khi persistence context đóng. Không nên chỉ bật OSIV để che lỗi mà không kiểm tra truy vấn.

## 12. Kiểm thử và đo lường để ngăn N+1 quay lại

Một tối ưu chỉ có ý nghĩa khi được kiểm chứng bằng dữ liệu và truy vấn thực tế. Hãy tạo integration test có nhiều entity và quan hệ, vì dữ liệu một bản ghi thường không bộc lộ N+1.

Ví dụ kiểm thử repository với `@DataJpaTest`:

```java
@DataJpaTest
class OrderRepositoryQueryTest {
    @Autowired
    private OrderRepository orders;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void loadsLinesForPageWithoutOneQueryPerOrder() {
        for (int i = 0; i < 5; i++) {
            Order order = OrderTestData.orderWithLines(2);
            entityManager.persist(order);
        }
        entityManager.flush();
        entityManager.clear();

        List<Order> result =
                orders.findWithLinesForTest();

        assertEquals(5, result.size());
        assertTrue(result.stream()
                .allMatch(order -> order.getLines().size() == 2));
    }
}
```

Đoạn mã minh họa cách tạo dữ liệu và buộc persistence context tải lại từ database. Để kiểm tra số lượng SQL, có thể dùng Hibernate Statistics, datasource proxy hoặc công cụ kiểm thử truy vấn. Cần bật thống kê phù hợp, reset bộ đếm trước khi chạy use case và tính cả query do setup nếu chưa reset.

Không nên khẳng định test trên đã chứng minh không có N+1 nếu chỉ kiểm tra kết quả. Cần thêm assertion về số lần prepare/execute query hoặc kiểm tra số lượng truy vấn trong trace. Khi kiểm tra, hãy cân nhắc truy vấn phụ như sequence, count query, cache và các statement phục vụ transaction. Mục tiêu là xác nhận số truy vấn được giới hạn hợp lý khi số entity tăng, thay vì khóa cứng một con số dễ vỡ trước thay đổi vô hại.

Trong môi trường phát triển và production, theo dõi:

- Số SQL query trên mỗi request hoặc use case.
- Những câu SQL lặp lại cùng mẫu và khác tham số.
- Thời gian truy vấn và số dòng trả về.
- Số connection đang dùng, thời gian chờ pool và transaction duration.
- Kích thước response và thời gian serialization.

APM có thể giúp gắn các câu SQL với request cụ thể. Slow query log và execution plan giúp tìm truy vấn tốn thời gian. Query count và query duration là hai chỉ số khác nhau: N+1 thường làm tăng round trip; một truy vấn đơn lẻ vẫn có thể chậm do thiếu index hoặc join không phù hợp.

## 13. Chọn chiến lược theo use case

Không có một kỹ thuật fetch duy nhất phù hợp cho mọi tình huống. Có thể dùng bảng sau như hướng dẫn ban đầu:

| Nhu cầu | Cách tiếp cận có thể phù hợp | Điều cần kiểm tra |
|---|---|---|
| Chi tiết một đơn hàng và các dòng hàng | Fetch join hoặc EntityGraph | Số dòng join, quan hệ nhiều cấp |
| Danh sách nhiều đơn, chỉ hiển thị vài trường | DTO projection | Truy vấn và kiểu dữ liệu trả về |
| Nhiều entity cần truy cập collection lazy | Batch fetching | Batch size và lượng dữ liệu mỗi collection |
| Phân trang danh sách có quan hệ to-many | DTO query hoặc tải ID rồi fetch theo lô | Thứ tự, count query, không phân trang trên join collection |
| Màn hình chỉ cần tổng số hoặc thống kê | Aggregate query | Null, làm tròn, đơn vị và điều kiện group |
| Tải một entity nhưng không dùng quan hệ | Giữ lazy và không truy cập quan hệ | Mapper/serializer không được vô tình đọc quan hệ |

Một quy trình tối ưu thực tế:

1. Xác định dữ liệu mà use case thực sự cần trả về.
2. Tạo dữ liệu đủ lớn để tái hiện luồng sử dụng.
3. Quan sát SQL và số lượng truy vấn.
4. Chọn fetch join, EntityGraph, batch fetching hoặc projection phù hợp.
5. Đo lại số query, số dòng, thời gian và bộ nhớ.
6. Viết kiểm thử hoặc thiết lập giám sát để phát hiện hồi quy.

Đừng tối ưu chỉ để giảm số SQL statement. Một join lớn có thể tốn hơn vài truy vấn nhỏ nếu nó tạo nhiều dòng trùng lặp và tải nhiều cột. Ngược lại, giảm dữ liệu truyền bằng projection có thể mang lại lợi ích lớn dù vẫn có một vài truy vấn. Hãy đánh giá theo tổng chi phí của use case.

## 14. Các nguyên tắc cần duy trì

N+1 và overfetching thường xuất hiện khi fetch strategy không được thiết kế theo nhu cầu của ca sử dụng hoặc khi việc truy cập quan hệ bị ẩn trong mapper và serializer. Lazy loading là công cụ hữu ích để trì hoãn dữ liệu, nhưng phải hiểu rằng getter có thể tạo truy vấn. Eager loading cũng cần được kiểm soát vì có thể tải dư thừa hoặc phát thêm truy vấn.

Khi làm việc với tầng truy cập dữ liệu trong kiến trúc phân tầng, hãy giữ những nguyên tắc sau:

- Xem SQL được thực thi là bằng chứng; không suy đoán chỉ từ annotation hoặc tên repository method.
- Xác định fetch plan theo từng use case thay vì đặt mọi quan hệ thành EAGER.
- Dùng projection khi chỉ cần một phần dữ liệu.
- Dùng fetch join hoặc EntityGraph khi cần tải một nhóm quan hệ xác định.
- Cân nhắc batch fetching khi truy cập nhiều collection lazy mà join không phù hợp.
- Tránh fetch join collection trực tiếp với pagination nếu provider không thể phân trang đúng ở database.
- Chuyển entity thành DTO trước khi tầng trình bày serialize response.
- Kiểm thử và quan sát số truy vấn với dữ liệu có quy mô thực tế.

Một thiết kế dữ liệu hiệu quả không phải là thiết kế tải tất cả dữ liệu trong một lần. Nó tải đúng phần dữ liệu mà use case cần, với số lần truy cập hợp lý và ranh giới rõ ràng giữa tầng ứng dụng, nghiệp vụ, trình bày và truy cập dữ liệu. Khi kết hợp fetch strategy phù hợp với đo lường và kiểm thử, nhóm có thể giảm độ trễ và tải database mà vẫn giữ mã nguồn dễ hiểu, dễ thay đổi.


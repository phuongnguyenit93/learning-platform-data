# Tải dữ liệu trì hoãn và rủi ro truy cập từ View

Trong ứng dụng web theo mô hình **Model–View–Controller (MVC)**, Controller thường lấy dữ liệu qua dịch vụ hoặc repository rồi đưa dữ liệu cần thiết sang View. Với ORM như JPA/Hibernate, một số quan hệ giữa entity có thể được tải trì hoãn (lazy loading): dữ liệu liên quan chỉ được truy vấn khi chương trình thực sự truy cập đến nó.

Lazy loading giúp tránh tải những quan hệ không cần thiết trong mọi trường hợp. Tuy nhiên, nó cũng tạo ra một rủi ro dễ bị bỏ qua: View có thể vô tình truy cập thuộc tính của entity và kích hoạt truy vấn cơ sở dữ liệu trong lúc render. Khi đó, template không còn chỉ trình bày dữ liệu; nó gián tiếp điều khiển việc đọc dữ liệu, tạo truy vấn lặp, phụ thuộc vào persistence context và có thể gây lỗi khi session ORM đã đóng.

Bài học này giải thích cách hoạt động của lazy loading, các lỗi thường gặp khi View truy cập entity, và cách chuẩn bị dữ liệu ở tầng ứng dụng trước khi render. Mục tiêu là để View nhận một hợp đồng dữ liệu rõ ràng, không phụ thuộc vào việc ORM còn mở hay không.

## 1. Lazy loading là gì?

Lazy loading là chiến lược trì hoãn việc tải một đối tượng hoặc một quan hệ cho đến khi ứng dụng cần truy cập dữ liệu đó. Thay vì tải toàn bộ đồ thị entity ngay khi truy vấn đối tượng gốc, ORM có thể tạo proxy hoặc collection đặc biệt để đại diện cho dữ liệu chưa được tải.

Ví dụ, một đơn hàng có quan hệ với khách hàng và nhiều dòng hàng:

~~~java
@Entity
public class Order {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();
}
~~~

Khi truy vấn một `Order`, ORM có thể chỉ tải các cột của đơn hàng. Quan hệ `customer` và collection `items` được đại diện bằng proxy hoặc wrapper chưa tải đầy đủ. Khi code gọi `order.getCustomer().getName()` hoặc duyệt `order.getItems()`, ORM mới có thể phát sinh truy vấn bổ sung nếu persistence context vẫn còn hoạt động.

Lazy loading là một cách kiểm soát thời điểm tải dữ liệu, không phải cam kết rằng quan hệ sẽ luôn được tải bằng đúng một truy vấn riêng. ORM có thể kết hợp cache, batch fetching, join hoặc chiến lược khác tùy mapping và fetch plan.

### 1.1. Lazy và eager

| Chiến lược | Ý nghĩa | Hệ quả cần cân nhắc |
|---|---|---|
| LAZY | Quan hệ được tải khi được truy cập | Tránh tải dữ liệu không dùng, nhưng cần quản lý thời điểm truy cập |
| EAGER | Quan hệ phải có sẵn khi entity được tải theo yêu cầu của mapping | Có thể tải dữ liệu thừa hoặc tạo truy vấn bổ sung tùy ORM và truy vấn |

Với JPA, mặc định phổ biến là:

- `@ManyToOne` và `@OneToOne`: EAGER.
- `@OneToMany` và `@ManyToMany`: LAZY.

Có thể khai báo rõ chiến lược trong mapping. Tuy nhiên, không nên giải quyết mọi lỗi lazy loading bằng cách đổi tất cả quan hệ sang EAGER. Việc đó có thể làm đồ thị dữ liệu lớn lên, tải các quan hệ không cần thiết và gây ra truy vấn khó dự đoán. Fetch plan nên được quyết định theo từng use case.

## 2. Persistence context và proxy

JPA quản lý entity thông qua persistence context. Đây là phạm vi theo dõi các entity đã được tải hoặc quản lý trong một đơn vị làm việc. Trong ứng dụng Spring, persistence context thường gắn với EntityManager và được điều phối bởi transaction hoặc cơ chế mở rộng phạm vi của framework.

Khi một quan hệ lazy chưa được tải, entity có thể giữ proxy thay cho đối tượng thực hoặc một collection wrapper. Proxy biết cách yêu cầu ORM tải dữ liệu khi có thao tác truy cập.

Ví dụ:

~~~java
Order order = entityManager.find(Order.class, orderId);

// Quan hệ customer có thể chưa được tải tại thời điểm này.
String customerName = order.getCustomer().getName();
~~~

Nếu persistence context còn mở, thao tác đọc tên khách hàng có thể kích hoạt truy vấn. Nếu persistence context đã đóng trước khi truy cập, ORM không còn môi trường để tải quan hệ.

Điều này dẫn đến một nguyên tắc quan trọng: **khả năng truy cập thuộc tính Java không đồng nghĩa dữ liệu đã có sẵn trong bộ nhớ**. Một lời gọi getter trong View có thể là một thao tác I/O tới cơ sở dữ liệu.

## 3. Vì sao View truy cập entity lại nguy hiểm?

View thường được xem là lớp trình bày. Tuy nhiên, nếu Controller đưa entity ORM trực tiếp vào model, template có thể truy cập các quan hệ lazy mà không nhận ra đang kích hoạt truy vấn.

Ví dụ Controller:

~~~java
@GetMapping("/orders/{id}")
public String detail(@PathVariable Long id, Model model) {
    Order order = orderRepository.findById(id).orElseThrow();
    model.addAttribute("order", order);
    return "orders/detail";
}
~~~

Template Thymeleaf:

~~~html
<h1 th:text="${order.customer.name}">Tên khách hàng</h1>

<ul>
    <li th:each="item : ${order.items}"
        th:text="${item.product.name}">
        Sản phẩm
    </li>
</ul>
~~~

Controller chỉ thực hiện một lần truy vấn lấy đơn hàng. Nhưng khi render:

- `order.customer.name` có thể tải khách hàng.
- `order.items` có thể tải collection dòng hàng.
- `item.product.name` có thể tải sản phẩm cho từng dòng hàng.

Template nhìn như đang đọc dữ liệu đơn giản, nhưng thực tế có thể kích hoạt nhiều truy vấn. Số lượng truy vấn phụ thuộc vào mapping, cache, số dòng hàng và cách ORM tải quan hệ.

Việc truy cập entity từ View còn tạo ra các rủi ro:

- View phụ thuộc vào cấu trúc entity và quan hệ ORM.
- Template có thể tải dữ liệu ngoài dự kiến.
- Hiệu năng phụ thuộc vào số phần tử và cách người dùng xem trang.
- Lỗi chỉ xuất hiện khi render, dù Controller đã chạy xong.
- View có thể vô tình hiển thị trường nội bộ hoặc dữ liệu không dành cho người dùng.
- Kiểm thử View cần cơ sở dữ liệu hoặc persistence context nếu dữ liệu chưa được tải trước.

## 4. LazyInitializationException

Một lỗi phổ biến với Hibernate là `LazyInitializationException`. Lỗi này xảy ra khi code truy cập một proxy hoặc collection chưa được khởi tạo trong khi persistence context cần thiết đã đóng.

Ví dụ:

~~~java
public Order findOrder(Long id) {
    return orderRepository.findById(id).orElseThrow();
}
~~~

Controller gọi dịch vụ lấy entity, sau đó template truy cập:

~~~html
<span th:text="${order.customer.name}"></span>
~~~

Nếu transaction và persistence context đã kết thúc trước khi template đọc `customer`, Hibernate không thể tải quan hệ lazy và có thể ném `LazyInitializationException`.

Lỗi này không có nghĩa mapping lazy luôn sai. Nó cho thấy ứng dụng đang cố truy cập dữ liệu chưa được tải sau khi phạm vi quản lý entity đã kết thúc. Cần xác định dữ liệu nào View thực sự cần và tải dữ liệu đó trong phạm vi phù hợp.

## 5. N+1 query problem khi View duyệt collection

Một vấn đề hiệu năng khác là N+1 query. Giả sử trang danh sách hiển thị 30 đơn hàng và tên khách hàng của mỗi đơn.

Truy vấn đầu tiên lấy danh sách 30 đơn hàng. Sau đó, khi View truy cập `order.customer.name` cho từng đơn, ORM có thể phát thêm một truy vấn cho mỗi khách hàng chưa có trong cache.

Khi đó tổng số truy vấn có thể gần:

\[
1 + N
\]

Với 30 đơn, ứng dụng có thể thực hiện 1 truy vấn lấy đơn hàng và 30 truy vấn lấy khách hàng. Nếu template tiếp tục truy cập sản phẩm hoặc các quan hệ khác, số truy vấn có thể tăng thêm.

~~~mermaid
flowchart TD
    V[Render danh sách đơn hàng] --> Q1[Query 1: lấy N đơn hàng]
    Q1 --> L[View duyệt từng đơn]
    L --> Q2[Query 2: tải customer của đơn 1]
    L --> Q3[Query 3: tải customer của đơn 2]
    L --> Q4[Query N+1: tải customer của đơn N]
~~~

Vấn đề có thể không xuất hiện khi dữ liệu thử nghiệm chỉ có một hoặc hai bản ghi. Khi dữ liệu thật tăng lên, thời gian render và tải cơ sở dữ liệu tăng theo số phần tử.

Không nên chỉ dựa vào cảm nhận rằng trang đang nhanh. Hãy đo số truy vấn, thời gian SQL và kích thước kết quả trên dữ liệu đại diện.

## 6. Open Session in View che giấu điều gì?

Một số ứng dụng web dùng cơ chế **Open Session in View (OSIV)**: persistence context được giữ mở trong phần lớn hoặc toàn bộ vòng đời request, bao gồm cả lúc render View. Với Spring, cấu hình Open EntityManager in View có thể cho phép truy cập lazy relation sau khi service transaction đã kết thúc.

OSIV có thể khiến ví dụ ở trên không ném `LazyInitializationException`, vì View vẫn truy cập được persistence context. Nhưng điều đó không tự giải quyết vấn đề kiến trúc:

- Template vẫn có thể phát sinh truy vấn cơ sở dữ liệu.
- N+1 query vẫn có thể xảy ra.
- Truy vấn được kích hoạt bởi cách template truy cập thuộc tính, khiến hiệu năng khó dự đoán.
- Việc render có thể phụ thuộc vào database dù use case đã hoàn thành.
- Lỗi SQL có thể xuất hiện muộn trong quá trình render response.

OSIV không phải lúc nào cũng sai. Nó có thể là lựa chọn có chủ đích trong một số ứng dụng hoặc giai đoạn phát triển. Tuy nhiên, nếu mục tiêu là giữ View chỉ trình bày dữ liệu, nên cân nhắc đóng persistence context ở ranh giới service và chuẩn bị dữ liệu cần thiết trước khi trả kết quả.

Với Spring Boot, cấu hình thường gặp để tắt Open EntityManager in View là:

~~~properties
spring.jpa.open-in-view=false
~~~

Tên và hành vi cấu hình cần được xác minh theo phiên bản và cấu hình ứng dụng. Sau khi tắt OSIV, các trường hợp View đang dựa vào lazy loading sẽ lộ ra dưới dạng lỗi; cần chuyển chúng sang fetch plan hoặc DTO phù hợp thay vì chỉ bật lại OSIV để che lỗi.

## 7. Xác định dữ liệu View thực sự cần

Trước khi thay đổi fetch strategy, hãy bắt đầu từ màn hình và use case cụ thể.

Ví dụ trang chi tiết đơn hàng chỉ cần:

- Mã đơn và thời điểm tạo.
- Tên khách hàng.
- Danh sách tên sản phẩm, số lượng và đơn giá.
- Tổng tiền và trạng thái đơn.

View không cần toàn bộ entity Customer, Product hoặc OrderItem. Nó cũng không cần địa chỉ nội bộ, thông tin thanh toán hoặc các quan hệ khác không được hiển thị.

Một hợp đồng dữ liệu dành cho View có thể là:

~~~java
public record OrderItemView(
        String productName,
        int quantity,
        BigDecimal unitPrice
) {}

public record OrderDetailView(
        String orderNumber,
        String customerName,
        List<OrderItemView> items,
        BigDecimal total,
        String statusLabel,
        Instant createdAt
) {}
~~~

View nhận `OrderDetailView` và không cần biết các quan hệ ORM. Đây là một dạng View Model hoặc DTO trình bày. Nó chỉ chứa dữ liệu cần thiết cho màn hình.

## 8. Cách 1: Tải quan hệ cần thiết bằng fetch join

Với JPQL, có thể dùng `JOIN FETCH` để tải một quan hệ trong cùng truy vấn:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Query("""
        select o
        from Order o
        join fetch o.customer
        where o.id = :id
        """)
    Optional<Order> findDetailById(@Param("id") Long id);
}
~~~

Sau khi gọi phương thức này trong transaction, `customer` đã được tải. Nếu View cũng cần `items` và `product`, có thể mở rộng fetch plan:

~~~java
@Query("""
    select distinct o
    from Order o
    join fetch o.customer
    left join fetch o.items item
    left join fetch item.product
    where o.id = :id
    """)
Optional<Order> findCompleteDetailById(@Param("id") Long id);
~~~

`distinct` giúp loại trùng entity gốc trong kết quả JPQL khi join collection. Tuy nhiên, fetch nhiều collection cùng lúc có thể tạo tích Descartes lớn, làm số hàng SQL tăng mạnh hoặc gặp giới hạn của Hibernate với nhiều bag collection. Không nên thêm mọi quan hệ vào một fetch join chỉ để tránh lazy exception.

Fetch join phù hợp khi màn hình có một fetch plan rõ ràng và số lượng dữ liệu được giới hạn hợp lý. Với collection lớn hoặc danh sách có phân trang, cần chọn chiến lược khác.

## 9. Cách 2: Dùng EntityGraph để khai báo fetch plan

JPA EntityGraph cho phép chỉ định các thuộc tính cần tải cho một truy vấn mà không phải viết toàn bộ JPQL fetch join.

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = {
            "customer",
            "items",
            "items.product"
    })
    Optional<Order> findWithDetailsById(Long id);
}
~~~

EntityGraph mô tả các thuộc tính cần được tải cho use case này. Cách ORM thực hiện có thể khác nhau theo provider và truy vấn; hãy kiểm tra SQL thực tế để xác nhận số truy vấn và dữ liệu được tải.

EntityGraph giúp tránh thay đổi fetch type mặc định toàn cục chỉ vì một màn hình cần thêm dữ liệu. Mỗi phương thức repository có thể khai báo fetch plan phù hợp với use case.

## 10. Cách 3: Dùng DTO projection để chỉ lấy dữ liệu cần thiết

Nếu View chỉ cần một số trường, DTO projection thường là cách rõ ràng và tiết kiệm hơn việc tải cả entity graph.

Ví dụ dùng constructor projection trong JPQL:

~~~java
public record OrderListRow(
        Long id,
        String orderNumber,
        String customerName,
        BigDecimal total,
        OrderStatus status
) {}

public interface OrderRepository extends JpaRepository<Order, Long> {

    @Query("""
        select new com.example.orders.OrderListRow(
            o.id,
            o.number,
            c.name,
            o.total,
            o.status
        )
        from Order o
        join o.customer c
        order by o.createdAt desc
        """)
    List<OrderListRow> findOrderListRows();
}
~~~

Truy vấn chỉ chọn các cột cần cho danh sách. Kết quả không phải entity được quản lý, nên View không thể kích hoạt lazy loading từ các quan hệ ORM của đối tượng này.

DTO projection đặc biệt hữu ích cho:

- Trang danh sách có nhiều bản ghi.
- Dashboard chỉ cần một số chỉ số.
- API response có hợp đồng rõ.
- Màn hình không cần cập nhật trực tiếp entity.

Nếu cần phân trang, có thể dùng projection cùng `Pageable` và kiểm tra truy vấn count được tạo ra có phù hợp không.

## 11. Chuyển entity thành View Model trong transaction

Một cách tổ chức thường dùng là application/query service tải dữ liệu và ánh xạ thành DTO trước khi transaction kết thúc.

~~~java
@Service
public class OrderQueryService {
    private final OrderRepository orderRepository;

    public OrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public OrderDetailView getDetail(Long id) {
        Order order = orderRepository.findCompleteDetailById(id)
                .orElseThrow(() -> new OrderNotFound(id));

        List<OrderItemView> items = order.getItems().stream()
                .map(item -> new OrderItemView(
                        item.getProduct().getName(),
                        item.getQuantity(),
                        item.getUnitPrice()
                ))
                .toList();

        return new OrderDetailView(
                order.getNumber(),
                order.getCustomer().getName(),
                items,
                order.getTotal(),
                order.getStatus().getDisplayLabel(),
                order.getCreatedAt()
        );
    }
}
~~~

Các quan hệ cần thiết đã được tải bởi repository method. Service đọc chúng trong transaction rồi trả một đối tượng độc lập với persistence context.

Controller chỉ chuyển DTO sang View:

~~~java
@GetMapping("/orders/{id}")
public String detail(@PathVariable Long id, Model model) {
    OrderDetailView detail = orderQueryService.getDetail(id);
    model.addAttribute("order", detail);
    return "orders/detail";
}
~~~

Template lúc này chỉ đọc dữ liệu thuần:

~~~html
<h1 th:text="${order.orderNumber}">Mã đơn</h1>
<p th:text="${order.customerName}">Khách hàng</p>

<ul>
    <li th:each="item : ${order.items}">
        <span th:text="${item.productName}">Sản phẩm</span>
        <span th:text="${item.quantity}">1</span>
        <span th:text="${item.unitPrice}">0</span>
    </li>
</ul>
~~~

View không cần biết `Order` có quan hệ lazy nào hoặc persistence context đang mở hay đóng. Dữ liệu được chuẩn bị trước theo nhu cầu của màn hình.

## 12. Vì sao không nên chỉ đổi mọi quan hệ sang EAGER?

Khi gặp `LazyInitializationException`, cách sửa nhanh có thể là đổi quan hệ sang EAGER. Nhưng điều này có thể tạo ra vấn đề mới:

- Mỗi truy vấn entity luôn yêu cầu quan hệ EAGER, kể cả khi màn hình không dùng.
- Một danh sách đơn hàng có thể kéo theo nhiều khách hàng, địa chỉ hoặc collection không cần thiết.
- ORM có thể tải quan hệ bằng nhiều truy vấn bổ sung tùy cách thực hiện.
- Entity graph lớn khiến bộ nhớ và thời gian xử lý tăng.
- Những màn hình khác nhau có nhu cầu dữ liệu khác nhau nhưng bị buộc dùng chung một chiến lược.

Thay vì đặt fetch type toàn cục theo một màn hình, hãy định nghĩa fetch plan theo use case bằng fetch join, EntityGraph hoặc projection. EAGER vẫn có thể phù hợp với quan hệ nhỏ, luôn cần thiết và có vòng đời rõ, nhưng không nên dùng như cách chữa chung cho lỗi truy cập từ View.

## 13. Phân trang và collection fetch join

Một lỗi thiết kế thường gặp là dùng fetch join cho collection đồng thời phân trang danh sách entity:

~~~java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    order by o.createdAt desc
    """)
Page<Order> findAllWithItems(Pageable pageable);
~~~

Join một đơn hàng với nhiều dòng hàng làm một đơn hàng xuất hiện trên nhiều hàng kết quả SQL. Điều này khiến việc áp dụng limit/offset ở cấp database trở nên phức tạp. Một số ORM có thể cảnh báo hoặc phải phân trang trong bộ nhớ, gây tải dữ liệu quá lớn.

Các hướng xử lý thường dùng:

1. Phân trang danh sách bằng DTO projection chỉ chứa trường cần hiển thị.
2. Nếu cần entity, phân trang ID trước rồi tải chi tiết cho tập ID đó bằng truy vấn riêng.
3. Dùng batch fetching để giảm số truy vấn khi truy cập các quan hệ lazy.
4. Chọn một trang có kích thước giới hạn và fetch plan được đo đạc.

Ví dụ truy vấn hai bước:

~~~java
@Query(
        value = "select o.id from Order o order by o.createdAt desc",
        countQuery = "select count(o) from Order o"
)
Page<Long> findOrderIds(Pageable pageable);

@EntityGraph(attributePaths = {"customer"})
List<Order> findByIdIn(Collection<Long> ids);
~~~

Service lấy ID theo trang, tải các đơn hàng cần thiết rồi sắp xếp lại theo thứ tự ID của trang nếu truy vấn thứ hai không bảo đảm thứ tự. Với danh sách lớn, DTO projection thường đơn giản và hiệu quả hơn.

## 14. Batch fetching và các chiến lược giảm N+1

Nếu cần entity và quan hệ lazy, batch fetching có thể gom nhiều lần tải quan hệ thành ít truy vấn hơn. Hibernate hỗ trợ cấu hình batch size ở một số cấp, ví dụ:

~~~java
@BatchSize(size = 50)
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderItem> items = new ArrayList<>();
~~~

Khi nhiều collection cùng loại được truy cập, Hibernate có thể tải theo nhóm thay vì một truy vấn cho mỗi collection. Cấu hình cụ thể phụ thuộc phiên bản và loại association; cần xem SQL thực tế.

Các lựa chọn phổ biến:

| Chiến lược | Phù hợp khi | Cần chú ý |
|---|---|---|
| Fetch join | Màn hình cần một số quan hệ xác định | Tránh join quá nhiều collection |
| EntityGraph | Muốn khai báo fetch plan theo truy vấn | Kiểm tra cách provider thực hiện |
| DTO projection | Chỉ cần một số trường để hiển thị | Cần duy trì hợp đồng DTO |
| Batch fetching | Nhiều entity cần cùng loại quan hệ lazy | Vẫn có truy vấn bổ sung; đo batch size |
| Subselect fetching | Một nhóm collection cùng nguồn được tải theo truy vấn nhóm | Phụ thuộc Hibernate và mẫu truy cập |

Không có một chiến lược tối ưu cho mọi màn hình. Hãy đo số truy vấn, dữ liệu trả về và thời gian thực thi với dữ liệu đại diện.

## 15. Tránh serialize entity trực tiếp thành JSON

Rủi ro tương tự xuất hiện khi Controller trả entity trực tiếp từ REST endpoint:

~~~java
@GetMapping("/api/orders/{id}")
public Order detail(@PathVariable Long id) {
    return orderRepository.findById(id).orElseThrow();
}
~~~

JSON serializer có thể gọi getter để duyệt quan hệ. Điều này có thể:

- Kích hoạt lazy loading và N+1.
- Gặp lỗi khi persistence context đã đóng.
- Tạo vòng tham chiếu giữa Order và OrderItem.
- Vô tình lộ trường nội bộ không thuộc hợp đồng API.
- Làm API thay đổi khi entity hoặc mapping ORM thay đổi.

Hãy trả DTO response:

~~~java
public record OrderResponse(
        String orderNumber,
        String customerName,
        BigDecimal total,
        String status
) {}
~~~

DTO giúp API có hợp đồng ổn định, giới hạn dữ liệu công khai và không phụ thuộc proxy ORM.

## 16. Kiểm thử để phát hiện truy vấn phát sinh từ View

Kiểm thử không nên chỉ xác minh trang có hiển thị đúng. Cần kiểm tra dữ liệu đã được chuẩn bị ở tầng phù hợp và số truy vấn không tăng bất thường.

### 16.1. Kiểm thử query service

- Dữ liệu DTO chứa đủ trường View cần.
- Mapping entity sang DTO diễn ra trong transaction.
- Không truy cập quan hệ không thuộc fetch plan.
- Khi entity không tồn tại, lỗi được biểu diễn đúng.

### 16.2. Kiểm thử View độc lập

Render View với DTO hoặc dữ liệu mẫu thuần, không cần persistence context. Nếu template chỉ nhận DTO, test có thể chạy mà không mở database session.

### 16.3. Kiểm thử số lượng truy vấn

Có thể bật thống kê Hibernate hoặc dùng datasource proxy để đếm SQL. Với một trang danh sách, số truy vấn nên ổn định hoặc tăng theo batch có kiểm soát, không tăng tuyến tính bất ngờ theo từng dòng.

Không nên gắn một con số truy vấn cố định nếu dữ liệu hoặc cache làm thay đổi kế hoạch hợp lệ. Hãy đặt ngưỡng theo use case và kiểm tra cả loại truy vấn được thực thi.

### 16.4. Kiểm thử khi persistence context đã đóng

Một cách kiểm tra ranh giới là lấy DTO từ service, kết thúc transaction rồi render View. Nếu View vẫn hoạt động, nó không phụ thuộc lazy proxy của entity.

Đây là một kiểm thử hữu ích khi ứng dụng tắt OSIV hoặc muốn bảo đảm template không truy cập database.

## 17. Quy trình chẩn đoán khi trang tải chậm hoặc phát sinh LazyInitializationException

Khi gặp lỗi hoặc hiệu năng bất thường:

1. **Xác định nơi truy cập dữ liệu:** tìm biểu thức trong template hoặc serializer đang gọi getter của entity.
2. **Kiểm tra mapping:** xác định quan hệ LAZY/EAGER và cách ORM tạo proxy.
3. **Xác định phạm vi persistence context:** transaction kết thúc ở đâu, OSIV có bật không.
4. **Đo truy vấn thực tế:** bật SQL logging hoặc thống kê để tìm N+1 và truy vấn thừa.
5. **Liệt kê dữ liệu View cần:** xác định các trường và quan hệ thực sự được hiển thị.
6. **Chọn fetch plan:** fetch join, EntityGraph, DTO projection hoặc batch fetching.
7. **Ánh xạ thành DTO trong service/query layer:** kết thúc việc truy cập entity trước khi View render.
8. **Kiểm thử lại:** render View sau transaction và đo số truy vấn trên dữ liệu đại diện.
9. **Đánh giá OSIV:** nếu tắt, kiểm tra mọi màn hình đã chuẩn bị đủ dữ liệu; nếu giữ, ghi rõ lý do và giám sát truy vấn khi render.

Không nên sửa bằng cách thêm truy vấn tùy tiện trong template hoặc đổi mọi quan hệ sang EAGER mà chưa hiểu nguyên nhân.

## 18. Checklist review tầng View và persistence

- [ ] Controller không đưa entity graph lớn trực tiếp vào View khi không cần thiết.
- [ ] View nhận DTO/View Model với các trường cần hiển thị.
- [ ] Template không gọi repository hoặc dịch vụ truy cập dữ liệu.
- [ ] Getter trong View không kích hoạt lazy loading ngoài dự kiến.
- [ ] Fetch plan được chọn theo use case cụ thể.
- [ ] Không đổi toàn bộ quan hệ sang EAGER chỉ để che LazyInitializationException.
- [ ] Các truy vấn danh sách được kiểm tra nguy cơ N+1.
- [ ] Collection fetch join được cân nhắc cẩn thận khi phân trang.
- [ ] OSIV có quyết định cấu hình rõ và được hiểu về trade-off.
- [ ] DTO được tạo trong phạm vi transaction cần thiết.
- [ ] REST API không serialize entity ORM trực tiếp nếu điều đó làm lộ cấu trúc hoặc kích hoạt lazy loading.
- [ ] View có thể được kiểm thử bằng dữ liệu thuần sau khi transaction kết thúc.
- [ ] Có đo truy vấn và thời gian render trên dữ liệu đại diện.

## Kết luận

Lazy loading giúp trì hoãn việc tải quan hệ ORM cho đến khi cần, nhưng nếu View truy cập entity trực tiếp, một biểu thức trong template có thể kích hoạt truy vấn, tạo N+1 hoặc gây LazyInitializationException khi persistence context đã đóng. Open Session in View có thể che lỗi vòng đời nhưng không loại bỏ truy vấn ngoài dự kiến. Hãy xác định dữ liệu màn hình cần, chọn fetch plan theo use case và ánh xạ entity thành DTO/View Model trong tầng dịch vụ trước khi render. Khi View chỉ đọc dữ liệu thuần, ranh giới MVC rõ hơn, hiệu năng dễ đo và kiểm thử không phụ thuộc vào persistence context.

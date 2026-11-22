# Tránh mở rộng đồ thị quan hệ chỉ để thuận tiện truy vấn trong JPA

Trong ứng dụng dùng Spring Data JPA, một nhu cầu phổ biến là: “Từ khách hàng, làm sao lấy danh sách đơn hàng?”, “Từ sản phẩm, làm sao biết đơn hàng nào đã mua?”, hoặc “Làm sao trả về một màn hình gồm dữ liệu của nhiều bảng?”. Phản xạ dễ gặp là thêm quan hệ hai chiều, thêm các collection vào entity, rồi đi theo chuỗi getter để lấy dữ liệu. Cách này có vẻ thuận tiện lúc viết code, nhưng có thể khiến mô hình miền bị phình to, làm tăng điểm phát sinh truy vấn, tạo vòng tham chiếu và đưa trách nhiệm truy vấn vào những entity vốn không cần sở hữu quan hệ đó.

Nguyên tắc thiết kế Repository là: **chỉ mở rộng quan hệ trong entity khi quan hệ đó phục vụ mô hình nghiệp vụ, bất biến dữ liệu hoặc vòng đời đối tượng; nếu chỉ cần lấy dữ liệu để đọc, hãy thiết kế truy vấn phù hợp ở Repository**. Database vẫn có khóa ngoại và có thể JOIN bình thường dù entity không khai báo collection ngược chiều.

## 1. Phân biệt bốn loại “đồ thị”

Không nên xem các khái niệm sau là một:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Quan hệ trong cơ sở dữ liệu** | Xác định khóa ngoại và ràng buộc toàn vẹn | Cột `purchase_orders.customer_id` tham chiếu `customers.id` |
| **Đồ thị đối tượng JPA** | Các tham chiếu giữa entity mà ứng dụng có thể điều hướng | `PurchaseOrder.customer`, có thể có hoặc không có `Customer.orders` |
| **Đồ thị dữ liệu được tải** | Những thuộc tính/association được lấy cho một thao tác cụ thể | Truy vấn lấy đơn hàng cùng khách hàng bằng `JOIN FETCH` hoặc `@EntityGraph` |
| **Hình dạng kết quả trả về** | Các trường API, báo cáo, danh sách thực sự cần | DTO gồm mã đơn hàng, thời gian đặt, tổng tiền, tên khách hàng |

Một foreign key trong database **không bắt buộc** phải có mapping JPA theo cả hai chiều. Truy vấn SQL/JPQL cũng không bắt buộc phải tải toàn bộ object graph. Và một API cần thông tin từ nhiều bảng không có nghĩa entity phải chứa tất cả các collection nối tới những bảng ấy.

Ví dụ, nếu đơn hàng lưu `customer_id`, ta có thể tìm tất cả đơn hàng của khách hàng bằng `PurchaseOrderRepository`. Việc thêm `List<PurchaseOrder> orders` vào `Customer` chỉ để gọi `customer.getOrders()` thường không tạo thêm giá trị nghiệp vụ.

## 2. Ví dụ: không thêm collection ngược chiều chỉ để hiển thị danh sách

Giả sử hệ thống có khách hàng và đơn hàng. Mỗi đơn hàng thuộc một khách hàng; màn hình khách hàng cần hiển thị 20 đơn hàng gần nhất.

Thiết kế entity theo chiều thực sự cần thiết:

~~~java
package com.example.sales.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {}

    public Long getId() { return id; }
    public String getName() { return name; }
}

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(nullable = false)
    private Instant orderedAt;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal totalAmount;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public Instant getOrderedAt() { return orderedAt; }
    public BigDecimal getTotalAmount() { return totalAmount; }
}
~~~

Với hai entity này:

- Đơn hàng biết khách hàng mà nó thuộc về.
- Khách hàng không cần giữ collection đơn hàng.
- Khóa ngoại `purchase_orders.customer_id` vẫn bảo đảm tính liên kết ở database nếu schema có ràng buộc tương ứng.
- Repository có thể lọc, sắp xếp và phân trang đơn hàng theo mã khách hàng.

Một cách truy vấn trực tiếp:

~~~java
package com.example.sales.repository;

import com.example.sales.domain.PurchaseOrder;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        where o.customer.id = :customerId
        order by o.orderedAt desc, o.id desc
        """)
    List<PurchaseOrder> findRecentByCustomerId(
        @Param("customerId") Long customerId,
        Pageable pageable
    );
}
~~~

Gọi với `PageRequest.of(0, 20)` để giới hạn 20 kết quả. Ở đây `Pageable` được dùng để giới hạn truy vấn; do JPQL đã có `ORDER BY`, nên sắp xếp được xác định tại truy vấn. Cặp `orderedAt, id` giúp thứ tự ổn định khi nhiều đơn có cùng thời điểm.

Nếu dùng Spring Data query derivation, có thể khai báo `findByCustomer_Id(Long customerId, Pageable pageable)` để duyệt thuộc tính `customer.id` mà không cần `Customer.orders`. Chọn cách nào tùy yêu cầu lọc, thứ tự và quy ước dự án.

### Cách dễ viết nhưng không phù hợp với nhu cầu này

~~~java
@Entity
public class Customer {
    @Id
    private Long id;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();
}

// Ở một service khác:
Customer customer = customerRepository.findById(customerId).orElseThrow();
List<PurchaseOrder> allOrders = customer.getOrders();
List<PurchaseOrder> recentOrders = allOrders.stream()
    .sorted(Comparator.comparing(PurchaseOrder::getOrderedAt).reversed())
    .limit(20)
    .toList();
~~~

Cách trên đẩy việc lọc và lấy 20 phần tử sang bộ nhớ sau khi collection được khởi tạo. Với khách hàng có hàng chục nghìn đơn, đây có thể là truy vấn/tải dữ liệu lớn không cần thiết. Collection lazy vẫn có thể bị khởi tạo khi truy cập, và tải collection không đồng nghĩa với phân trang ở database.

Thay bằng truy vấn Repository có điều kiện và giới hạn kết quả. **Nhu cầu đọc một phần dữ liệu không phải lý do để mở rộng khả năng điều hướng của toàn bộ entity.**

## 3. Thiết kế API đọc bằng projection hoặc DTO

Với trang danh sách, thường không cần cả đối tượng `PurchaseOrder` đang được JPA quản lý. DTO cho phép chọn đúng trường cần hiển thị, giảm nguy cơ vô tình truy cập lazy association ở controller hoặc lúc serialize JSON.

Ví dụ DTO dùng Java record:

~~~java
package com.example.sales.api;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderSummary(
    Long id,
    Instant orderedAt,
    BigDecimal totalAmount
) {}
~~~

Repository trả về dữ liệu ngay trong truy vấn:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            select new com.example.sales.api.OrderSummary(
                o.id, o.orderedAt, o.totalAmount
            )
            from PurchaseOrder o
            where o.customer.id = :customerId
            """,
        countQuery = """
            select count(o)
            from PurchaseOrder o
            where o.customer.id = :customerId
            """
    )
    Page<OrderSummary> findSummariesByCustomerId(
        @Param("customerId") Long customerId,
        Pageable pageable
    );
}
~~~

Trong ví dụ này, `Pageable` có thể mang `Sort.by(DESC, "orderedAt").and(Sort.by(DESC, "id"))` để phân trang ổn định. `Page` có thể phát sinh truy vấn đếm; nếu UI chỉ cần “còn trang tiếp theo không”, cân nhắc `Slice` để tránh yêu cầu tổng số bản ghi. Với dữ liệu lớn và thao tác cuộn liên tục, cân nhắc keyset pagination nếu yêu cầu cho phép.

Dịch vụ đọc:

~~~java
@Service
public class OrderQueryService {
    private final PurchaseOrderRepository orders;

    public OrderQueryService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public Page<OrderSummary> listCustomerOrders(
            Long customerId, int page, int size) {
        Pageable request = PageRequest.of(
            page,
            Math.min(Math.max(size, 1), 100),
            Sort.by(Sort.Order.desc("orderedAt"), Sort.Order.desc("id"))
        );
        return orders.findSummariesByCustomerId(customerId, request);
    }
}
~~~

Trong dự án thực tế cần bổ sung kiểm tra quyền truy cập và phạm vi tenant ngay trong truy vấn hoặc ở tầng dịch vụ phù hợp. Không được coi một `customerId` hợp lệ về kiểu dữ liệu là bằng chứng người gọi có quyền xem đơn hàng đó.

### Nhiều bảng vẫn đọc được khi không có quan hệ ngược chiều

Giả sử màn hình cần tên khách hàng cùng thông tin đơn hàng:

~~~java
public record OrderRow(
    Long id,
    String customerName,
    Instant orderedAt,
    BigDecimal totalAmount
) {}

@Query("""
    select new com.example.sales.api.OrderRow(
        o.id, c.name, o.orderedAt, o.totalAmount
    )
    from PurchaseOrder o
    join o.customer c
    where o.orderedAt >= :fromTime
    """)
Page<OrderRow> findOrderRows(
    @Param("fromTime") Instant fromTime,
    Pageable pageable
);
~~~

JPQL có thể JOIN theo mapping `PurchaseOrder.customer`. Không cần khai báo `Customer.orders`. Đối với màn hình tổng hợp không cần quản lý entity, cũng có thể dùng native SQL, Spring Data projection, Criteria API hoặc Querydsl theo độ phức tạp truy vấn. Tiêu chí lựa chọn là khả năng diễn đạt điều kiện, giới hạn dữ liệu và khả năng bảo trì.

## 4. Phân biệt mapping quan hệ với chiến lược fetch

Một số vấn đề hiệu năng thường bị xử lý sai bằng cách thêm association:

**N+1 queries.** Khi lặp qua một danh sách đơn hàng và gọi `order.getCustomer().getName()`, nếu `customer` đang lazy và chưa được tải, ORM có thể thực hiện nhiều truy vấn phụ. Thêm `Customer.orders` không giải quyết nguyên nhân. Hãy lấy đúng dữ liệu bằng DTO projection, hoặc dùng fetch theo từng use case.

**Truy vấn lấy chi tiết cần một quan hệ to-one.** Khi thực sự cần entity đơn hàng cùng khách hàng trong cùng thao tác, có thể dùng:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.id = :orderId
    """)
Optional<PurchaseOrder> findDetailWithCustomer(
    @Param("orderId") Long orderId
);
~~~

Hoặc dùng `@EntityGraph(attributePaths = "customer")` trên một phương thức truy vấn phù hợp. Hai cách này chọn dữ liệu tải cho **một thao tác đọc**; chúng không buộc mọi truy vấn khác đều đi theo mối quan hệ ấy.

**Lazy/Eager.** Theo mặc định JPA, `@ManyToOne` và `@OneToOne` là EAGER, trong khi `@OneToMany` và `@ManyToMany` là LAZY. Vì vậy nên xét rõ nhu cầu và thường khai báo `fetch = FetchType.LAZY` cho to-one khi phù hợp. Tuy nhiên lazy chỉ trì hoãn việc tải; nó không tự bảo đảm truy vấn tối ưu. EAGER cũng không đồng nghĩa sẽ luôn dùng một câu SQL JOIN duy nhất.

**Phân trang cùng collection.** `JOIN FETCH` một collection to-many trong truy vấn phân trang có thể gây nhân bản hàng SQL và khiến ORM phải xử lý phân trang không đúng kỳ vọng hoặc trong bộ nhớ; hành vi cụ thể tùy provider và phiên bản. Với danh sách, ưu tiên DTO hoặc phân trang ID trước rồi lấy chi tiết cần thiết theo nhóm. Không giải bài toán bằng việc biến mọi quan hệ thành EAGER.

## 5. Khi nào `@OneToMany` thực sự có lý do tồn tại?

Không phải cứ có collection là thiết kế sai. Collection phù hợp khi đối tượng cha thật sự quản lý **tập con như một phần của nghiệp vụ**, chẳng hạn:

- `PurchaseOrder` quản lý các dòng hàng của chính đơn đó; thao tác thêm/xóa dòng phải kiểm tra bất biến tổng tiền hoặc trạng thái đơn.
- Một aggregate root chịu trách nhiệm thay đổi và kiểm soát vòng đời của các thực thể con.
- Nghiệp vụ thường xuyên thao tác nhất quán trên cả nhóm con trong một transaction và quan hệ có phạm vi rõ ràng, thường có kích thước có thể quản lý.

Ví dụ về quan hệ trong aggregate:

~~~java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<PurchaseOrderItem> items = new ArrayList<>();

    public void addItem(PurchaseOrderItem item) {
        items.add(item);
        item.assignTo(this);
    }

    public void removeItem(PurchaseOrderItem item) {
        if (items.remove(item)) {
            item.assignTo(null);
        }
    }
}

@Entity
public class PurchaseOrderItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    void assignTo(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

Đây là minh họa việc đồng bộ hai đầu quan hệ, không phải một mô hình nghiệp vụ hoàn chỉnh. Trong thực tế còn cần constructor, kiểm tra trạng thái đơn, giá trị tiền, quy tắc tạo/xóa dòng và ràng buộc nullable tương ứng. **`orphanRemoval = true` có thể khiến bản ghi con bị xóa khi bị loại khỏi quan hệ**, nên chỉ dùng nếu vòng đời con thật sự thuộc cha. `CascadeType.REMOVE` hoặc `CascadeType.ALL` không nên sao chép tùy tiện sang quan hệ chia sẻ như `Customer`–`PurchaseOrder`, `OrderItem`–`Product`.

Một điểm quan trọng: trong quan hệ hai chiều `@OneToMany(mappedBy = "order")` và `@ManyToOne`, phía `PurchaseOrderItem.order` là phía sở hữu khóa ngoại. Chỉ thêm phần tử vào collection mà không cập nhật phía sở hữu có thể không tạo ra liên kết như mong muốn. Helper method duy trì hai đầu giúp giảm lỗi.

Nếu “lấy toàn bộ đơn hàng của khách hàng” là mục đích duy nhất, trường hợp đó khác với “đơn hàng quản lý dòng hàng theo bất biến nghiệp vụ”. Hai nhu cầu nên dẫn đến hai quyết định mapping khác nhau.

## 6. Rủi ro khi mở rộng đồ thị quá mức

### 6.1. Tăng số đường đi có thể vô tình khởi tạo dữ liệu

Khi `Customer.orders`, `PurchaseOrder.items`, `PurchaseOrderItem.product` và `Product.orders` đều tồn tại, code rất dễ điều hướng nhiều cấp. Một mapper, debugger, logger hay serializer có thể truy cập getter và kích hoạt truy vấn ngoài dự tính. Với collection lớn, chi phí tăng đáng kể.

### 6.2. Vòng tham chiếu và rò rỉ cấu trúc domain ra API

Trả entity trực tiếp từ REST controller có thể gây vòng tham chiếu khi serialize (khách hàng → đơn hàng → khách hàng), gặp lazy-loading exception khi persistence context đã đóng, hoặc để lộ trường không thuộc hợp đồng API. Annotation chặn JSON recursion chỉ xử lý một triệu chứng. DTO giúp API có cấu trúc rõ ràng và độc lập với mapping của ORM.

### 6.3. Cascade và xóa dữ liệu ngoài ý định

Khi thêm quan hệ ngược chiều, lập trình viên có thể thêm `cascade = ALL` để thao tác “đơn giản hơn”. Nhưng cascade có ý nghĩa về **lan truyền trạng thái persistence**, không phải tối ưu truy vấn. Nếu nhiều aggregate cùng liên quan đến một entity, lựa chọn cascade/remove sai có thể làm mất dữ liệu hoặc tạo thao tác ngoài phạm vi mong muốn.

### 6.4. Khó giữ ranh giới aggregate

Entity có quá nhiều đường đi dễ khiến service thay đổi dữ liệu của aggregate khác qua getter, làm mờ ranh giới transaction và trách nhiệm kiểm tra bất biến. Với các quan hệ chỉ phục vụ báo cáo, query service và DTO thường là ranh giới rõ ràng hơn.

### 6.5. Hành vi `equals`, `hashCode`, `toString` khó kiểm soát

Nếu các phương thức được sinh tự động bao gồm association/collection, chúng có thể kích hoạt lazy load, đệ quy hoặc trở nên không ổn định. Hạn chế đưa quan hệ vào các phương thức này, đặc biệt với entity có ID được cấp sau persist. Cần có quy tắc định danh rõ ràng của dự án.

## 7. Thiết kế Repository quanh thao tác sử dụng dữ liệu

Repository nên diễn đạt câu hỏi nghiệp vụ và hỗ trợ lọc ngay tại database.

| Nhu cầu | Cách thiết kế nên cân nhắc | Có cần collection ở entity cha? |
| --- | --- | --- |
| Liệt kê 20 đơn gần nhất của khách hàng | Truy vấn theo `customerId`, `ORDER BY`, giới hạn số dòng | Không |
| Tìm đơn hàng theo trạng thái, ngày và người mua | Repository query/specification trả DTO có phân trang | Không |
| Hiển thị tên khách hàng trong danh sách đơn | Projection JOIN qua `order.customer` | Không |
| Thống kê số đơn hoặc tổng doanh thu theo khách hàng | Query `COUNT`, `SUM`, `GROUP BY` | Không |
| Đổi số lượng một dòng hàng và tính lại tổng đơn | Thao tác qua aggregate root `PurchaseOrder` và items | Có thể có |
| Xóa một dòng mà vòng đời hoàn toàn thuộc đơn | Collection có helper, cân nhắc `orphanRemoval` | Có thể có |
| Hiển thị số sản phẩm từng được mua cùng nhau | Query phân tích/aggregate chuyên biệt | Không |
| Phân quyền theo khách hàng hoặc tenant | Predicate trong query và tầng ứng dụng | Không |

Một Repository không nên trả toàn bộ entity rồi dựa vào `stream().filter(...)` cho điều kiện vốn có thể đưa xuống SQL, nhất là với dữ liệu tăng trưởng. Với truy vấn có nhiều tiêu chí tùy chọn, sử dụng Specification/Criteria/Querydsl để dựng predicate rõ ràng, thay vì thêm association chỉ để tạo các chuỗi getter.

## 8. Quan hệ ở database và chỉ mục vẫn rất quan trọng

Không khai báo `Customer.orders` **không có nghĩa bỏ foreign key**. Phải giữ ràng buộc và chỉ mục theo nhu cầu truy vấn. Ví dụ, với hệ quản trị hỗ trợ cú pháp tương ứng:

~~~sql
ALTER TABLE purchase_orders
    ADD CONSTRAINT fk_order_customer
    FOREIGN KEY (customer_id) REFERENCES customers(id);

CREATE INDEX idx_orders_customer_time_id
    ON purchase_orders (customer_id, ordered_at DESC, id DESC);
~~~

Chỉ mục kết hợp ở trên có thể hỗ trợ lọc đơn theo khách hàng và duyệt theo thời gian. Cần kiểm chứng bằng execution plan và khối lượng dữ liệu thực tế; thiết kế index phụ thuộc hệ quản trị, tần suất ghi và loại truy vấn. Không tạo trùng index đã có.

Một truy vấn cơ bản có thể có dạng:

~~~sql
SELECT id, ordered_at, total_amount
FROM purchase_orders
WHERE customer_id = :customer_id
ORDER BY ordered_at DESC, id DESC
LIMIT 20;
~~~

Cú pháp giới hạn kết quả tùy database; Spring Data `Pageable` để ORM sinh cú pháp phân trang tương thích dialect. Việc ràng buộc, lọc và JOIN ở database là một bài toán khác với việc Java entity có collection hai chiều hay không.

## 9. Quy trình ra quyết định trước khi thêm association

Khi có đề nghị thêm `@OneToMany`, `@ManyToMany` hoặc quan hệ ngược chiều, hãy trả lời theo thứ tự:

1. **Nghiệp vụ có cần điều hướng và thay đổi con từ cha không?** Nếu chỉ đọc danh sách/báo cáo, bắt đầu bằng Repository query.
2. **Ai sở hữu vòng đời và bất biến dữ liệu?** Nếu con thuộc aggregate root và được chỉnh sửa thông qua root, mapping collection có thể hợp lý.
3. **Kích thước quan hệ có bị chặn không?** Collection có thể tăng không giới hạn là tín hiệu mạnh cần query phân trang.
4. **Màn hình thực sự cần trường nào?** Nếu chỉ cần vài trường, ưu tiên DTO/projection thay vì tải entity graph.
5. **Fetch plan nào phù hợp từng thao tác?** Lựa chọn `JOIN FETCH`, `@EntityGraph`, batch fetching hoặc query DTO theo access pattern thực tế, không mặc định fetch tất cả.
6. **Có hệ quả về cascade, orphan removal, serialize và equality không?** Chỉ thêm mapping khi đã hiểu trách nhiệm và tác dụng phụ.
7. **Điều kiện lọc, quyền truy cập, index, thứ tự và phân trang đã được xác định chưa?** Những yếu tố này thường quyết định chất lượng truy vấn hơn số lượng association.

### Minh họa quyết định

Yêu cầu: “Trong trang chi tiết khách hàng, hiển thị năm đơn gần nhất cùng tổng số đơn”.

Thiết kế phù hợp:

- `CustomerRepository.findById(customerId)` để lấy thông tin khách hàng.
- `PurchaseOrderRepository.findRecentByCustomerId(customerId, PageRequest.of(0, 5))` để lấy đúng năm dòng, hoặc phiên bản DTO.
- `PurchaseOrderRepository.countByCustomer_Id(customerId)` (hoặc aggregate query phù hợp) để lấy số lượng.
- Service kết hợp thành `CustomerDetailResponse` gồm thông tin khách hàng, năm đơn và `totalOrders`.

Không cần thêm `Customer.orders`, tải toàn bộ các đơn rồi đếm bằng `getOrders().size()` và cắt năm phần tử. Với `LAZY` và các cấu hình tối ưu collection, `size()` có thể có hành vi truy vấn khác nhau theo provider; cách an toàn, rõ ý định là query đếm riêng.

Yêu cầu khác: “Khi xác nhận đơn, kiểm tra từng dòng hàng, tính lại tổng tiền và cấm sửa dòng sau khi đã giao”. Lúc này dòng hàng thuộc nghiệp vụ của đơn. Việc để aggregate root `PurchaseOrder` quản lý collection `items` có lý do thiết kế rõ ràng, miễn là quy mô và lifecycle được kiểm soát.

## 10. Các nhầm lẫn thường gặp

**“Có foreign key thì bắt buộc có mapping hai chiều.”** Không đúng. FK là quan hệ dữ liệu; JPA mapping chỉ thể hiện những hướng điều hướng mà model cần.

**“Thêm `@OneToMany` sẽ làm JOIN nhanh hơn.”** Không đúng. Mapping không tạo tối ưu hiệu năng tự động; tốc độ phụ thuộc truy vấn SQL, chỉ mục, số dòng trả về, fetch strategy và execution plan.

**“Đặt collection là LAZY thì không lo tốn tài nguyên.”** Không đủ. Truy cập collection vẫn có thể tải hàng loạt bản ghi; lặp qua nhiều entity dễ tạo N+1.

**“Tất cả entity phải trả trực tiếp qua REST để đỡ viết DTO.”** Cách này trộn cấu trúc database, trạng thái persistence và API contract. Projection/DTO thường rõ ràng hơn cho các use case đọc.

**“Không dùng quan hệ ngược chiều thì không thể truy vấn từ phía cha.”** Có thể lọc theo FK ở repository của entity con, dùng JPQL/SQL, projection và các truy vấn aggregate. Nhu cầu tra cứu không đồng nghĩa phải có khả năng điều hướng trong bộ nhớ.

**“Mọi collection đều là anti-pattern.”** Cũng không đúng. Collection được dùng đúng khi thể hiện ownership, invariant hoặc tương tác nghiệp vụ thực sự; vấn đề là thêm collection *chỉ để tiện lấy dữ liệu*.

## Kết luận

**Thiết kế quan hệ entity theo nghĩa vụ nghiệp vụ; thiết kế Repository theo nhu cầu đọc và cập nhật dữ liệu.** Một màn hình cần danh sách bản ghi không phải lý do đủ mạnh để thêm quan hệ hai chiều hay mở rộng object graph. Khi có thể mô tả nhu cầu bằng điều kiện lọc, JOIN, projection, phép tổng hợp hoặc phân trang, hãy để database và Repository làm việc đó. Chỉ đưa collection vào entity khi nó giúp thể hiện ranh giới aggregate, quy tắc nhất quán hoặc vòng đời của các đối tượng liên quan.

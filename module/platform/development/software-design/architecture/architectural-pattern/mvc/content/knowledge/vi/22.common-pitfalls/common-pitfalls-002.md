# Model bị thu hẹp thành thực thể cơ sở dữ liệu

Trong ứng dụng MVC, một sai lầm phổ biến là xem Model chỉ là tập hợp các lớp ánh xạ với bảng cơ sở dữ liệu. Mỗi bảng có một Entity, mỗi Entity có getter/setter, Controller nhận Entity từ form, Service cập nhật các trường rồi Repository lưu lại. Cách làm này có thể hoạt động với CRUD đơn giản, nhưng khi quy tắc nghiệp vụ, nhiều loại giao diện và yêu cầu bảo mật phát triển, mô hình ứng dụng dần bị chi phối bởi cấu trúc lưu trữ.

Một thực thể cơ sở dữ liệu mô tả cách dữ liệu được lưu. Model của ứng dụng còn phải diễn đạt ý nghĩa của dữ liệu, hành vi hợp lệ, trạng thái, quan hệ và cách thông tin được trình bày cho từng người dùng. Nếu chỉ có ORM Entity, các quy tắc thường trôi sang Controller hoặc Service, API vô tình công khai cấu trúc bảng, dữ liệu nhạy cảm dễ bị binding/serialization, và thay đổi schema có thể làm ảnh hưởng trực tiếp đến giao diện.

Bài học này phân tích vì sao thu hẹp Model thành database entity là một vấn đề, nhận diện các triệu chứng thường gặp và cách tổ chức lại mô hình theo trách nhiệm. Trọng tâm là giữ đúng ranh giới giữa nghiệp vụ, persistence và presentation mà không tạo thêm lớp một cách máy móc.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao Model trong MVC rộng hơn thực thể ORM hoặc bảng database.
- Phân biệt Domain Model, Persistence Entity, Request DTO, Response DTO và View Model.
- Nhận diện dấu hiệu schema-first và Anemic Domain Model.
- Phân tích rủi ro khi bind request trực tiếp vào JPA Entity.
- Tránh lộ dữ liệu và lỗi serialization do quan hệ ORM.
- Đặt hành vi và bất biến vào đúng nơi.
- Tách read model khỏi write model khi nhu cầu hiển thị khác nghiệp vụ ghi.
- Chọn mức độ mapping phù hợp với độ phức tạp của ứng dụng.
- Refactor một Controller CRUD đang thao tác trực tiếp trên database entity.

## 2. Model trong MVC không đồng nghĩa với database entity

Trong MVC, Model là phần biểu diễn dữ liệu và trạng thái mà ứng dụng làm việc cùng, bao gồm cả quy tắc và hành vi liên quan đến nghiệp vụ. Trong Spring MVC, org.springframework.ui.Model lại là một abstraction cụ thể để Controller đưa thuộc tính sang View. Nó không phải Domain Model. Cùng một từ Model có thể chỉ những thứ khác nhau, vì vậy cần làm rõ ngữ cảnh khi thiết kế.

| Loại mô hình | Trách nhiệm | Ví dụ |
|---|---|---|
| Domain Model | Biểu diễn khái niệm, hành vi và bất biến nghiệp vụ | Order, Money, OrderLine |
| Persistence Entity | Biểu diễn dữ liệu theo cách ORM lưu/đọc | OrderJpaEntity |
| Request DTO / Form | Nhận dữ liệu theo hợp đồng đầu vào | CreateOrderRequest |
| Response DTO | Trả dữ liệu qua API | OrderResponse |
| View Model | Chuẩn bị dữ liệu cho một màn hình cụ thể | OrderDetailView |
| Query / Read Model | Tối ưu dữ liệu để đọc và tìm kiếm | OrderSummaryRow |
| Spring MVC Model | Chuyển thuộc tính từ Controller sang template | model.addAttribute(...) |

Một lớp có thể đảm nhiệm nhiều vai trò trong ứng dụng nhỏ, nhưng các vai trò đó vẫn khác nhau về mục đích. Khi một lớp bắt đầu phải đáp ứng nhiều hợp đồng cùng lúc, đó là dấu hiệu nên xem xét tách mô hình.

### 2.1. Mô hình nghiệp vụ trả lời câu hỏi khác mô hình lưu trữ

Giả sử nghiệp vụ có khái niệm đơn hàng:

- Đơn hàng chỉ được xác nhận khi có ít nhất một dòng.
- Đơn đã xác nhận không được tùy ý sửa giá.
- Đơn đã giao không thể bị hủy theo quy trình thông thường.
- Tổng tiền phải được tính từ dòng hàng, thuế và giảm giá theo chính sách.

Domain Model phải diễn đạt các quy tắc đó.

Database entity có thể chứa các cột như id, customer_id, status, total_amount, created_at, updated_at và version. Những cột này cho biết dữ liệu được lưu ra sao. Chúng không tự mô tả đầy đủ hành vi xác nhận, hủy hoặc tính tổng tiền. Cột status là một giá trị; quy tắc chuyển trạng thái phải được bảo vệ ở nơi có ngữ nghĩa nghiệp vụ.

## 3. Dấu hiệu Model đang bị thu hẹp thành database entity

Một hoặc nhiều dấu hiệu sau thường xuất hiện khi mô hình bị thiết kế xoay quanh schema.

### 3.1. Mỗi bảng tương ứng đúng một lớp và lớp chỉ có getter/setter

Các lớp chỉ chứa field, getter, setter và annotation ORM. Service thực hiện mọi phép tính và chuyển trạng thái.

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private UUID id;

    private UUID customerId;
    private String shippingAddress;
    private String status;
    private BigDecimal totalAmount;

    public String getShippingAddress() {
        return shippingAddress;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public void setShippingAddress(String shippingAddress) {
        this.shippingAddress = shippingAddress;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }
}
~~~

Lớp này không diễn đạt đơn hàng có thể làm gì. Bất kỳ đoạn code nào có tham chiếu đến entity đều có thể gọi setter và đưa nó vào trạng thái không hợp lệ.

### 3.2. Controller biết tên cột và tự cập nhật trạng thái

Nếu Controller tự gán status = "CONFIRMED" hoặc tự tính totalAmount, giao diện đã biết quá nhiều về cách nghiệp vụ được lưu.

### 3.3. Form và API dùng trực tiếp entity

Một form sửa hồ sơ có thể bind thẳng vào JPA Entity. Khi entity thêm trường mới, trường đó có thể vô tình trở thành dữ liệu client được phép gửi lên. Đây là nguy cơ over-posting/mass assignment.

### 3.4. Response API serialize toàn bộ object graph ORM

Một entity có thể có quan hệ hai chiều như Order -> Customer -> Orders. Serialize trực tiếp có thể gây vòng lặp, tải lazy relation, truy vấn N+1 hoặc lộ trường nội bộ.

### 3.5. Thay đổi schema kéo theo thay đổi giao diện

Một cột kỹ thuật được thêm, đổi tên hoặc chuẩn hóa có thể làm vỡ form và response vì cùng một class đang được dùng ở tất cả các tầng.

### 3.6. Quy tắc bị lặp ở nhiều điểm vào

HTML Controller, REST Controller và job nền tự kiểm tra trạng thái hoặc tự tính giá. Vì không có mô hình nghiệp vụ bảo vệ quy tắc, mỗi điểm vào có thể cho kết quả khác nhau.

### 3.7. Test phải khởi động database để kiểm tra quy tắc đơn giản

Nếu muốn kiểm tra một đơn rỗng không thể xác nhận mà phải chạy cả Spring context và database, logic nghiệp vụ có thể đang gắn quá chặt với persistence.

## 4. Vì sao cách thiết kế này gây vấn đề?

### 4.1. Database trở thành ngôn ngữ của ứng dụng

Schema được tạo để lưu trữ hiệu quả và bảo đảm tính toàn vẹn dữ liệu. Nó có thể chứa khóa ngoại, cột audit, mã trạng thái, cờ kỹ thuật hoặc cấu trúc chuẩn hóa. Người dùng và nghiệp vụ không nhất thiết suy nghĩ bằng những khái niệm đó.

Nếu class name và method name chỉ phản chiếu bảng/cột, code thường nói về cách lưu thay vì hành vi mà hệ thống cần thực hiện.

Ví dụ, updateOrderStatus(String status) mô tả thao tác ghi một giá trị. confirm() diễn đạt hành động nghiệp vụ và có thể bảo vệ điều kiện xác nhận.

### 4.2. Bất biến không có nơi sở hữu

Nếu bất kỳ nơi nào cũng có thể thay đổi status, totalAmount hoặc quantity, quy tắc bị phân tán. Một luồng cập nhật có thể kiểm tra trước khi ghi; luồng khác có thể quên. Khi quy tắc thay đổi, nhóm phải tìm mọi chỗ đã tự triển khai nó.

### 4.3. Giao diện bị khóa vào schema

Form có thể chỉ cần tên hiển thị và một số trường được phép chỉnh sửa. API có thể cần hợp đồng ổn định cho client. Màn hình quản trị có thể cần thêm thông tin tổng hợp. Database entity lại chứa các cột phục vụ lưu trữ.

Dùng cùng một lớp cho tất cả khiến thay đổi ở một mục đích tác động tới những mục đích khác.

### 4.4. Tăng rủi ro bảo mật

Entity thường chứa trường không nên nhận từ client hoặc không nên trả ra ngoài. Nếu binding và serialization trực tiếp, việc thêm trường có thể làm mở rộng bề mặt tấn công mà không có thay đổi rõ ràng trong Controller.

### 4.5. Phụ thuộc ORM lan sang nghiệp vụ

Lazy loading, proxy, transaction, annotation và lifecycle callback có thể ảnh hưởng cách dùng đối tượng. Nếu Domain Model phụ thuộc các chi tiết này, việc kiểm thử hoặc thay đổi persistence trở nên khó khăn hơn.

### 4.6. Hiệu năng khó kiểm soát

Một entity graph được serialize có thể kéo theo nhiều truy vấn. Màn hình chỉ cần ba trường nhưng ứng dụng tải cả quan hệ Customer, Items, Payments và AuditHistory. Query model hoặc projection giúp tải đúng dữ liệu cần đọc.

## 5. Một ví dụ sai: bind trực tiếp JPA Entity

Giả sử endpoint cho phép cập nhật địa chỉ giao hàng. Một cách triển khai rủi ro:

~~~java
@PostMapping("/orders/{id}")
public String update(
        @PathVariable UUID id,
        @ModelAttribute OrderEntity form) {

    OrderEntity order = orderRepository.findById(id)
        .orElseThrow();

    order.setShippingAddress(form.getShippingAddress());
    order.setStatus(form.getStatus());
    order.setTotalAmount(form.getTotalAmount());

    orderRepository.save(order);
    return "redirect:/orders/" + id;
}
~~~

Vấn đề:

- form được tạo từ request và có cùng cấu trúc với entity.
- Client có thể gửi thêm status hoặc totalAmount.
- Controller phải tự biết trường nào được phép sửa.
- Không có hành vi domain xác định khi địa chỉ thay đổi.
- Việc thêm trường vào entity có thể tạo thêm khả năng bind.
- Không có sự phân biệt giữa dữ liệu client đề xuất và dữ liệu server đã xác minh.

Chỉ kiểm tra các trường bị cấm bằng một danh sách blocklist không bền vững. Khi thêm thuộc tính mới, lập trình viên có thể quên cập nhật danh sách.

## 6. Tách hợp đồng đầu vào khỏi thực thể lưu trữ

Request DTO xác định rõ client được phép gửi gì:

~~~java
public record ChangeShippingAddressRequest(
    @NotBlank String recipientName,
    @NotBlank String phoneNumber,
    @NotBlank String addressLine,
    @NotBlank String city
) {}
~~~

Controller nhận DTO và gọi application use case:

~~~java
@PostMapping("/orders/{id}/shipping-address")
public String changeAddress(
        @PathVariable UUID id,
        @Valid @ModelAttribute ChangeShippingAddressRequest request) {

    changeShippingAddress.handle(
        new ChangeShippingAddressCommand(
            new OrderId(id),
            request.recipientName(),
            request.phoneNumber(),
            request.addressLine(),
            request.city()
        )
    );

    return "redirect:/orders/" + id;
}
~~~

Application Service tải aggregate và gọi hành vi:

~~~java
public class ChangeShippingAddressService {
    private final OrderRepository orders;

    public ChangeShippingAddressService(OrderRepository orders) {
        this.orders = orders;
    }

    public void handle(ChangeShippingAddressCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        ShippingAddress address = new ShippingAddress(
            command.recipientName(),
            command.phoneNumber(),
            command.addressLine(),
            command.city()
        );

        order.changeShippingAddress(address);
        orders.save(order);
    }
}
~~~

Domain Model tự bảo vệ quy tắc:

~~~java
public void changeShippingAddress(ShippingAddress address) {
    Objects.requireNonNull(address);

    if (status != OrderStatus.DRAFT
            && status != OrderStatus.CONFIRMED) {
        throw new OrderRuleViolation(
            "Shipping address cannot be changed in this state"
        );
    }

    this.shippingAddress = address;
}
~~~

Đoạn mã là phần hành vi của Order Aggregate: Order sở hữu trường shippingAddress kiểu ShippingAddress và chỉ cho phép thay đổi khi trạng thái phù hợp.

Nhờ đó, một client không thể thay đổi trạng thái hoặc tổng tiền chỉ bằng cách thêm field vào request. DTO là allowlist của dữ liệu đầu vào; Domain Model quyết định hành động đó có hợp lệ hay không.

Ví dụ trên giả định các kiểu OrderId, OrderRepository, ShippingAddress, command và exception đã được định nghĩa. Trong hệ thống thật, phone number và địa chỉ cần được chuẩn hóa theo quy tắc nghiệp vụ, còn quyền sửa đơn cần được kiểm tra ở application policy.

## 7. Tách Domain Model khỏi Persistence Entity khi cần

Persistence Entity là adapter của mô hình lưu trữ. Nó có thể dùng annotation JPA, quan hệ ORM, version và các trường phục vụ database.

~~~java
@Entity
@Table(name = "orders")
public class OrderJpaEntity {
    @Id
    private UUID id;

    @Column(name = "customer_id", nullable = false)
    private UUID customerId;

    @Column(name = "status", nullable = false)
    private String status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    protected OrderJpaEntity() {}

    public UUID getId() { return id; }
    public void setId(UUID id) { this.id = id; }
    public UUID getCustomerId() { return customerId; }
    public void setCustomerId(UUID customerId) { this.customerId = customerId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }
}
~~~

Domain Model có thể tập trung vào hành vi:

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private OrderStatus status;
    private Money total;

    private Order(
            OrderId id,
            CustomerId customerId,
            OrderStatus status,
            Money total) {
        this.id = id;
        this.customerId = customerId;
        this.status = status;
        this.total = total;
    }

    public static Order reconstitute(
            OrderId id,
            CustomerId customerId,
            OrderStatus status,
            Money total) {
        return new Order(id, customerId, status, total);
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new OrderRuleViolation(
                "Only a draft order can be confirmed"
            );
        }
        status = OrderStatus.CONFIRMED;
    }

    public OrderId id() {
        return id;
    }

    public CustomerId customerId() {
        return customerId;
    }

    public OrderStatus status() {
        return status;
    }

    public Money total() {
        return total;
    }
}
~~~

Các đoạn ví dụ dùng những kiểu domain như OrderId, CustomerId, Money, OrderStatus và OrderRuleViolation. Money cung cấp amount() để adapter đọc giá trị lưu trữ; các import được lược bỏ để tập trung vào ranh giới giữa hai mô hình.

Persistence adapter chuyển đổi giữa hai mô hình:

~~~java
public interface SpringDataOrderRepository
        extends JpaRepository<OrderJpaEntity, UUID> {}

@Component
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderRepository data;

    public JpaOrderRepository(SpringDataOrderRepository data) {
        this.data = data;
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return data.findById(id.value())
            .map(this::toDomain);
    }

    @Override
    public void save(Order order) {
        data.save(toEntity(order));
    }

    private Order toDomain(OrderJpaEntity entity) {
        return Order.reconstitute(
            new OrderId(entity.getId()),
            new CustomerId(entity.getCustomerId()),
            OrderStatus.valueOf(entity.getStatus()),
            new Money(entity.getTotalAmount(), Currency.getInstance("VND"))
        );
    }

    private OrderJpaEntity toEntity(Order order) {
        OrderJpaEntity entity = new OrderJpaEntity();
        entity.setId(order.id().value());
        entity.setCustomerId(order.customerId().value());
        entity.setStatus(order.status().name());
        entity.setTotalAmount(order.total().amount());
        return entity;
    }
}
~~~

Đây là ví dụ minh họa; factory reconstitute thuộc Domain Model, còn getter/setter và repository Spring Data thuộc persistence adapter. Ví dụ lược bỏ optimistic locking để tập trung vào ranh giới mô hình; hệ thống có cập nhật đồng thời cần thiết kế version hoặc cơ chế khóa phù hợp và ánh xạ conflict thành kết quả rõ ràng.

Không phải lúc nào cũng cần tách hai class. Với ứng dụng CRUD nhỏ, ít quy tắc, dùng cùng một class có thể là lựa chọn hợp lý. Việc tách đáng giá khi domain có hành vi, schema thay đổi độc lập với nghiệp vụ, nhiều giao diện dùng chung quy tắc hoặc ORM làm mô hình khó kiểm soát.

## 8. Domain Model không phải View Model

Một Domain Model thể hiện ý nghĩa nghiệp vụ; View Model được thiết kế theo nhu cầu hiển thị. Một màn hình chi tiết đơn hàng có thể cần:

- Mã đơn đã định dạng.
- Tên khách hàng.
- Nhãn trạng thái bằng ngôn ngữ giao diện.
- Tổng tiền đã định dạng.
- Số lượng sản phẩm.
- Các thao tác người dùng hiện có quyền thực hiện.

View Model có thể được định nghĩa:

~~~java
public record OrderDetailView(
    String orderNumber,
    String customerName,
    String statusLabel,
    String formattedTotal,
    List<OrderLineView> lines,
    boolean canCancel
) {}
~~~

Một View Model không cần giống cấu trúc Domain Model. Nó có thể gộp dữ liệu từ nhiều aggregate hoặc dịch vụ đọc, và có thể chứa các trường chỉ phục vụ hiển thị.

Không đưa formattedTotal vào Domain Model vì định dạng phụ thuộc locale và giao diện. Domain giữ Money; presenter hoặc mapper chuyển thành chuỗi theo ngôn ngữ và định dạng phù hợp.

### 8.1. Dữ liệu hiển thị không phải trạng thái nghiệp vụ

Trường canCancel trong View Model có thể được tính từ policy để giao diện ẩn/hiện nút. Đây chỉ là gợi ý trải nghiệm. Application Service vẫn phải kiểm tra quyền và Domain Model vẫn phải kiểm tra trạng thái khi nhận lệnh hủy.

## 9. Read Model và Write Model có thể khác nhau

Một truy vấn danh sách thường cần dữ liệu đã tổng hợp, trong khi thao tác cập nhật cần aggregate có hành vi. Ép cả hai dùng cùng một entity graph có thể gây tải thừa và mapping phức tạp.

Ví dụ read model:

~~~java
public record OrderSummaryRow(
    UUID orderId,
    String customerName,
    String status,
    BigDecimal totalAmount,
    Instant createdAt
) {}
~~~

Query service có thể dùng projection trực tiếp:

~~~java
public interface OrderQueries {
    Page<OrderSummaryRow> search(OrderSearchCriteria criteria);
    OrderReadData getById(UUID id);
}
~~~

Write use case vẫn tải Domain Aggregate qua repository:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Cách tách read/write model không bắt buộc phải triển khai CQRS đầy đủ. Có thể chỉ dùng DTO projection cho truy vấn và Domain Model cho lệnh ghi trong cùng một ứng dụng, cùng database.

Chỉ áp dụng CQRS tách biệt hoặc read store riêng khi độ phức tạp truy vấn, tải đọc hoặc nhu cầu mở rộng thực sự cần đến. Không nên thêm message broker, eventual consistency và nhiều database chỉ để tránh một DTO mapping đơn giản.

## 10. Tránh serialize trực tiếp ORM Entity

Trả JPA Entity trực tiếp từ REST Controller có thể tạo ra một số vấn đề.

### 10.1. Lộ trường nội bộ

Entity có thể chứa:

- Password hash hoặc token.
- Cờ nội bộ.
- Trạng thái phê duyệt.
- Khóa ngoại hoặc thông tin tenant.
- Ghi chú vận hành.
- Version và metadata persistence.

Một field mới được thêm vào entity có thể xuất hiện trong JSON mà không có quyết định API rõ ràng.

### 10.2. Vòng lặp quan hệ hai chiều

Ví dụ:

~~~java
@Entity
public class CustomerEntity {
    @OneToMany(mappedBy = "customer")
    private List<OrderEntity> orders;
}

@Entity
public class OrderEntity {
    @ManyToOne
    private CustomerEntity customer;
}
~~~

Serialize Customer có thể đi sang orders, mỗi order lại serialize customer và tiếp tục lặp. Annotation JSON để bỏ một phía có thể giải quyết một vòng lặp cụ thể nhưng không tạo ra API contract ổn định.

### 10.3. Lazy loading và N+1

Serializer có thể gọi getter của quan hệ lazy sau khi Controller đã trả object. Tùy transaction và cấu hình Open Session in View, việc này có thể gây:

- LazyInitializationException.
- Truy vấn phát sinh trong lúc serialize.
- N+1 query khi serialize danh sách.
- Response latency khó dự đoán.

### 10.4. Hợp đồng API bị phụ thuộc ORM

Thay đổi FetchType, tên quan hệ hoặc cấu trúc entity có thể thay đổi JSON. API client không nên phụ thuộc vào cấu trúc nội bộ của JPA.

Cách xử lý là query đúng dữ liệu cần thiết, map sang Response DTO và kiểm soát rõ field công khai.

~~~java
public record OrderResponse(
    UUID id,
    String status,
    BigDecimal totalAmount
) {}

public record OrderReadData(
    UUID id,
    String status,
    BigDecimal totalAmount
) {}

@GetMapping("/api/orders/{id}")
public OrderResponse get(@PathVariable UUID id) {
    OrderReadData order = orderQueries.getById(id);

    return new OrderResponse(
        order.id(),
        order.status(),
        order.totalAmount()
    );
}
~~~

## 11. Không để schema database quyết định hợp đồng form

Một form cập nhật hồ sơ có thể chỉ cho phép đổi tên hiển thị và múi giờ. Persistence Entity có thể còn có role, locked, passwordHash, createdAt và tenantId.

Không nên dùng entity làm form object. Dùng request DTO chỉ chứa trường được phép nhận, kiểm tra quyền ở server và lấy các trường quản trị từ nguồn đáng tin cậy.

| Dữ liệu | Nguồn phù hợp |
|---|---|
| Tên hiển thị người dùng nhập | Request DTO |
| Vai trò tài khoản | Policy/quy trình quản trị phía server |
| Tenant đang hoạt động | Security context đã xác thực |
| Thời điểm tạo | Server/clock |
| Tổng tiền đơn hàng | Domain calculation hoặc pricing policy |
| Trạng thái duyệt | Hành vi nghiệp vụ được phép |
| ID bản ghi | Path hoặc command, sau đó kiểm tra scope |

Không coi hidden field là dữ liệu đáng tin cậy. Người dùng có thể sửa mọi giá trị client gửi lên.

## 12. Validation không chỉ là kiểm tra cột NOT NULL

Ràng buộc database như NOT NULL, UNIQUE, foreign key và check constraint rất quan trọng, nhưng không thay thế mô hình nghiệp vụ.

Các tầng validation có mục đích khác nhau:

| Tầng | Ví dụ | Mục đích |
|---|---|---|
| Request binding | JSON đúng kiểu, trường bắt buộc | Hợp đồng giao thức |
| DTO validation | Chuỗi không rỗng, độ dài hợp lệ | Phản hồi lỗi đầu vào |
| Value Object | Money không âm, EmailAddress hợp lệ | Bảo vệ giá trị có ý nghĩa |
| Domain Entity/Aggregate | Đơn rỗng không thể xác nhận | Bảo vệ bất biến nghiệp vụ |
| Application policy | Actor có quyền thay đổi đơn | Bảo vệ use case |
| Database constraint | Khóa ngoại, unique, version | Bảo vệ tính toàn vẹn lưu trữ |

Không nên đặt mọi quy tắc vào annotation trên JPA Entity rồi cho rằng domain đã được bảo vệ. Một tác vụ nền có thể tạo entity mà không đi qua Controller validation; một rule trạng thái cần được thực thi bởi hành vi Domain.

Database vẫn cần constraint vì ứng dụng có thể có nhiều process, nhiều request đồng thời hoặc lỗi ở tầng trên. Domain rule và database constraint bổ trợ nhau.

## 13. Không biến Service thành nơi chứa toàn bộ Model

Khi entity chỉ có setter, Service thường phải tự chứa mọi hành vi:

~~~java
public void confirm(UUID id) {
    OrderEntity order = repository.findById(id).orElseThrow();

    if (!"DRAFT".equals(order.getStatus())) {
        throw new IllegalStateException("Invalid state");
    }

    if (order.getTotalAmount().signum() <= 0) {
        throw new IllegalStateException("Invalid total");
    }

    order.setStatus("CONFIRMED");
    repository.save(order);
}
~~~

Một rich Domain Model có thể biểu diễn hành vi:

~~~java
public void confirm() {
    if (status != OrderStatus.DRAFT) {
        throw new OrderRuleViolation("Only draft orders can be confirmed");
    }

    if (total.amount().signum() <= 0) {
        throw new OrderRuleViolation("An order must have a positive total");
    }

    status = OrderStatus.CONFIRMED;
}
~~~

Application Service vẫn cần tồn tại để tải aggregate, gọi confirm(), lưu kết quả và điều phối transaction cùng các port bên ngoài. Điểm khác biệt là nó gọi hành vi nghiệp vụ thay vì tự thao tác từng cột.

Không cần đẩy mọi dòng logic vào Entity. Quy tắc liên quan đến nhiều đối tượng hoặc không có chủ thể tự nhiên có thể thuộc Domain Service. Việc chọn vị trí cần dựa trên ngôn ngữ và quyền sở hữu của quy tắc.

## 14. Khi nào nên dùng chung một class?

Tách Domain Model và Persistence Entity có chi phí: mapping, nhiều file, constructor/factory và nguy cơ đồng bộ hai mô hình không đúng. Không nên biến việc tách lớp thành quy tắc tuyệt đối.

| Tình huống | Hướng phù hợp |
|---|---|
| CRUD nhỏ, ít quy tắc, một giao diện | Có thể dùng chung entity và DTO đơn giản |
| Form chỉ cập nhật một tập field nhỏ | Dùng request DTO riêng |
| API cần hợp đồng ổn định | Dùng Response DTO riêng |
| Domain có trạng thái và bất biến phức tạp | Domain Model có hành vi |
| ORM relation/lazy loading gây vấn đề | Query projection hoặc DTO |
| Nhiều giao diện dùng chung nghiệp vụ | Tách use case và Domain Model |
| Schema thay đổi độc lập với nghiệp vụ | Cân nhắc tách persistence model |
| Báo cáo tổng hợp lớn | Read Model/projection |

Một class dùng chung có thể vẫn là lựa chọn hợp lý nếu các mục đích thực sự trùng nhau, không có dữ liệu nhạy cảm, không có mass assignment và không làm rò rỉ chi tiết ORM. Điều quan trọng là hiểu trade-off và có ranh giới bảo vệ.

## 15. Cách refactor khi Model đã bị thu hẹp

Không cần viết lại toàn bộ ứng dụng cùng lúc. Có thể chuyển dần một use case có quy tắc rõ ràng.

### Bước 1: Chọn một hành động nghiệp vụ

Ví dụ: xác nhận đơn hàng. Tránh bắt đầu bằng việc tách mọi entity và repository cùng lúc.

### Bước 2: Ghi lại quy tắc

Xác định trạng thái hợp lệ, điều kiện xác nhận, dữ liệu được thay đổi và các trường hợp bị từ chối.

### Bước 3: Tạo DTO đầu vào

Chỉ nhận những trường mà client được phép gửi. Không nhận status hoặc totalAmount nếu chúng do server quyết định.

### Bước 4: Đưa hành vi vào Domain Model

Tạo phương thức confirm() để kiểm tra trạng thái và bất biến. Giới hạn setter hoặc không cung cấp setter cho các trường quan trọng.

### Bước 5: Tạo Application Service

Service tải aggregate, gọi confirm(), lưu kết quả và điều phối event/port nếu cần.

### Bước 6: Giữ persistence adapter

Ban đầu có thể dùng cùng database và Spring Data JPA. Chỉ tách ORM Entity khi có lý do cụ thể; không cần thay database để cải thiện Domain Model.

### Bước 7: Tạo Response/View Model

Chọn đúng dữ liệu cho màn hình hoặc API. Không trả object graph ORM.

### Bước 8: Viết test theo ranh giới

Unit test Domain xác nhận quy tắc; application test xác nhận điều phối; integration test xác nhận mapping và transaction; MVC test xác nhận binding và response.

~~~mermaid
flowchart TD
    A["Controller thao tác trực tiếp Entity"]
    B["Xác định use case và bất biến"]
    C["Tạo Request DTO / Command"]
    D["Đưa hành vi vào Domain Model"]
    E["Application Service điều phối"]
    F["Persistence Adapter lưu aggregate"]
    G["Response DTO / View Model"]

    A --> B --> C --> D --> E --> F --> G
~~~

Refactor theo từng use case giúp giữ thay đổi nhỏ, có thể kiểm tra và triển khai dần.

## 16. Kiểm thử khi đã tách mô hình

### 16.1. Unit test Domain

Kiểm tra hành vi mà không cần database:

~~~java
@Test
void confirmedOrderCannotChangeShippingAddress() {
    Order order = aConfirmedOrder();

    assertThrows(
        OrderRuleViolation.class,
        () -> order.changeShippingAddress(aNewAddress())
    );
}
~~~

### 16.2. Test DTO binding và mass assignment

Gửi request có thêm trường không nằm trong DTO, ví dụ status, role hoặc totalAmount. Xác nhận các trường đó không thể thay đổi trạng thái server.

Tùy framework và cấu hình JSON/form binding, trường không biết có thể bị bỏ qua hoặc bị từ chối. Dù hành vi nào được chọn, dữ liệu ngoài DTO không được tác động đến entity.

### 16.3. Test Response DTO

Xác nhận response chỉ chứa field công khai và không lộ password hash, internal flag, tenant metadata hoặc quan hệ ORM không cần thiết.

### 16.4. Test query và số lượng truy vấn

Với màn hình danh sách, xác nhận query chỉ tải dữ liệu cần thiết và không phát sinh N+1 khi map/serialize. Có thể dùng integration test với SQL statistics hoặc công cụ quan sát query phù hợp.

### 16.5. Test persistence mapping

Nếu Domain Model tách khỏi JPA Entity, kiểm tra round-trip mapping: lưu domain object, tải lại và xác nhận identity, state, value object và aggregate invariant vẫn được giữ.

## 17. Những lỗi thường gặp khi sửa sai lầm này

### Tách mọi class thành ba bản sao

Tạo Domain Entity, JPA Entity và DTO giống hệt nhau cho mọi bảng có thể tăng mapping mà không tăng giá trị. Chỉ tách khi có khác biệt trách nhiệm thực sự.

### Chỉ đổi tên Entity thành Domain Model

Đổi tên không làm lớp có hành vi. Cần xác định bất biến, hành vi và quyền sở hữu trạng thái.

### Đưa logic vào Controller để tránh anemic entity

Controller vẫn là adapter giao thức. Đưa quy tắc vào use case và Domain Model để có thể dùng chung qua HTML, API và job.

### Dùng DTO nhưng vẫn tin dữ liệu client

DTO giới hạn field được bind, nhưng giá, owner, tenant, role và trạng thái vẫn cần được xác định hoặc kiểm tra ở server.

### Dùng View Model làm Domain Model

View Model có thể chứa chuỗi định dạng, cờ hiển thị hoặc dữ liệu tổng hợp. Không dùng nó để thay đổi trạng thái nghiệp vụ.

### Tách persistence rồi để mapper quyết định nghiệp vụ

Mapper chỉ chuyển đổi dữ liệu. Không đặt quy tắc xác nhận, tính giá hoặc quyền truy cập trong mapper.

### Trả entity rồi dùng annotation để che field

Annotation serialization có thể hữu ích trong trường hợp cụ thể nhưng không thay thế API DTO. Quan hệ và lazy loading vẫn có thể gây vấn đề.

### Quên transaction và concurrency

Domain Model trong bộ nhớ không tự bảo vệ hai request đồng thời. Dùng transaction, optimistic locking hoặc cơ chế phù hợp để bảo vệ cập nhật và bất biến liên quan.

## 18. Quy trình lựa chọn mô hình cho một chức năng MVC

Trước khi tạo class, hãy trả lời các câu hỏi:

1. **Ai sử dụng dữ liệu này?** Domain, persistence, form, API hay một màn hình?
2. **Dữ liệu có ý nghĩa nghiệp vụ gì?** Có hành vi hoặc bất biến nào phải được bảo vệ?
3. **Client được phép gửi trường nào?** Có trường nào chỉ server được quyết định?
4. **Màn hình cần dữ liệu gì?** Có cần tổng hợp hoặc định dạng riêng không?
5. **ORM cần cấu trúc nào?** Có quan hệ hoặc lifecycle nào không nên rò ra ngoài?
6. **Các điểm vào có dùng chung quy tắc không?** HTML, API, job và message có gọi cùng use case không?
7. **Mức độ phức tạp có biện minh cho mapping không?** Tách lớp có tạo ranh giới hữu ích hay chỉ thêm boilerplate?
8. **Kiểm thử ở đâu?** Quy tắc có thể test độc lập với database không?

Một bảng quyết định ngắn:

| Nếu câu trả lời chủ yếu là... | Hãy cân nhắc... |
|---|---|
| “Lưu và tải dữ liệu” | Persistence Entity/Repository |
| “Nhận dữ liệu client” | Request DTO/Form |
| “Bảo vệ quy tắc và trạng thái” | Domain Model |
| “Hiển thị cho một màn hình” | View Model |
| “Truy vấn tổng hợp hiệu quả” | Read Model/Projection |
| “Điều phối một hành động” | Application Service |

## 19. Kết luận

Model trong MVC không nên bị đồng nhất với thực thể cơ sở dữ liệu. ORM Entity mô tả cách lưu trữ; Domain Model diễn đạt ý nghĩa, hành vi và bất biến; Request/Response DTO xác định hợp đồng giao tiếp; View Model phục vụ một màn hình; Read Model tối ưu cho truy vấn. Những mô hình này có thể dùng chung class khi trách nhiệm thực sự trùng nhau, nhưng không nên bị ép dùng chung chỉ vì chúng có các field giống nhau.

Khi Controller bind trực tiếp vào entity và Service tự sửa từng cột, quy tắc dễ phân tán, API dễ lộ schema và hệ thống khó thay đổi. Tách DTO đầu vào, đưa hành vi vào Domain Model, dùng Application Service điều phối và trả View Model phù hợp giúp giữ ranh giới rõ ràng. Hãy áp dụng mức tách vừa đủ với độ phức tạp thực tế: bảo vệ nghiệp vụ và hợp đồng giao tiếp trước, rồi chỉ tách persistence khi nó đem lại lợi ích cụ thể.


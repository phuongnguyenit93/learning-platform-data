# Nghiệp vụ nhiều repository và nhu cầu điều phối ở tầng service trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể nhận biết khi một thao tác nghiệp vụ cần phối hợp nhiều repository; tổ chức logic đó ở application/service layer; xác định transaction boundary để các thay đổi dữ liệu cùng thành công hoặc cùng rollback; và công bố một thao tác nghiệp vụ qua Spring Data REST hoặc custom REST endpoint mà không để controller tự điều phối persistence.

## 1. Vì sao một nghiệp vụ có thể cần nhiều repository?

Một repository thường tập trung vào việc truy cập một aggregate hoặc một nhóm entity. Tuy nhiên, một use case thực tế có thể phải đọc và cập nhật nhiều loại dữ liệu.

Ví dụ tạo đơn hàng có thể cần:

- Tìm Customer và kiểm tra trạng thái khách hàng.
- Tìm các Product và kiểm tra giá hoặc trạng thái kinh doanh.
- Kiểm tra và giảm số lượng tồn kho.
- Tạo Order cùng các OrderLine.
- Ghi nhận lịch sử hoặc audit event.

Nếu controller gọi từng repository để thực hiện các bước này, logic nghiệp vụ sẽ bị dàn trải ở tầng HTTP. Một controller khác hoặc một job nền có thể phải sao chép cùng quy tắc, khiến hành vi khó nhất quán và khó kiểm thử.

Application/service layer cung cấp một điểm điều phối cho use case. Service nhận dữ liệu đầu vào, kiểm tra quy tắc, gọi các repository cần thiết và xác định ranh giới giao dịch. Controller chỉ chuyển request sang service và chuyển kết quả thành HTTP response.

## 2. Phân chia trách nhiệm giữa repository, service và controller

Có thể chia trách nhiệm như sau:

| Thành phần | Trách nhiệm chính |
| --- | --- |
| Repository | Truy vấn, lưu và xóa dữ liệu của aggregate; cung cấp các query cần thiết |
| Domain model | Giữ trạng thái và các invariant thuộc về entity/aggregate |
| Application service | Điều phối use case, gọi nhiều repository, áp dụng transaction và phối hợp các domain operation |
| REST controller | Nhận HTTP request, kiểm tra định dạng đầu vào, gọi service và tạo HTTP response |
| Infrastructure integration | Giao tiếp với message broker, payment provider, email service hoặc hệ thống ngoài |

Repository không nên trở thành nơi điều phối toàn bộ use case. Ví dụ, `OrderRepository` không nên tự gọi `CustomerRepository`, `InventoryRepository` và `PaymentGateway` để hoàn tất một đơn hàng. Service hiểu toàn bộ luồng nghiệp vụ và gọi từng collaborator theo đúng thứ tự.

Một service có thể dùng nhiều repository:

```java
@Service
public class OrderApplicationService {

    private final CustomerRepository customers;
    private final ProductRepository products;
    private final InventoryRepository inventory;
    private final OrderRepository orders;

    public OrderApplicationService(
            CustomerRepository customers,
            ProductRepository products,
            InventoryRepository inventory,
            OrderRepository orders) {
        this.customers = customers;
        this.products = products;
        this.inventory = inventory;
        this.orders = orders;
    }

    // Các phương thức use case được triển khai ở đây
}
```

Constructor injection làm rõ service phụ thuộc vào repository nào và giúp thay thế collaborator trong unit test.

## 3. Đặt transaction boundary ở service layer

Khi nhiều repository cùng thay đổi dữ liệu trong một use case, transaction boundary thường nên nằm ở phương thức service điều phối. Với các repository dùng chung một relational database và transaction manager, có thể dùng `@Transactional`:

```java
@Service
public class OrderApplicationService {

    private final CustomerRepository customers;
    private final InventoryRepository inventory;
    private final OrderRepository orders;

    public OrderApplicationService(
            CustomerRepository customers,
            InventoryRepository inventory,
            OrderRepository orders) {
        this.customers = customers;
        this.inventory = inventory;
        this.orders = orders;
    }

    @Transactional
    public Order createOrder(CreateOrderCommand command) {
        Customer customer = customers.findById(command.customerId())
            .orElseThrow(() -> new CustomerNotFoundException(
                command.customerId()));

        customer.requireActive();

        inventory.reserve(
            command.productId(),
            command.quantity());

        Order order = Order.create(
            customer,
            command.productId(),
            command.quantity());

        return orders.save(order);
    }
}
```

Trong ví dụ, `@Transactional` tạo một transaction bao quanh lời gọi service. Các thao tác repository tham gia transaction hiện hành nếu dùng cùng transaction manager. Khi phương thức kết thúc bình thường, transaction được commit. Khi có exception thuộc quy tắc rollback, transaction được rollback để các thay đổi trong cùng transaction không bị lưu một phần.

Đây là lợi ích quan trọng của service layer: transaction mô tả toàn bộ use case, thay vì chỉ bao quanh từng lệnh `save` riêng lẻ.

### Rollback và loại exception

Theo mặc định của Spring, `@Transactional` rollback khi có unchecked exception (`RuntimeException` hoặc `Error`); checked exception không tự động kích hoạt rollback theo quy tắc mặc định. Nếu checked exception cũng phải rollback, cấu hình rõ:

```java
@Transactional(rollbackFor = Exception.class)
public Order createOrder(CreateOrderCommand command) throws Exception {
    // Các bước của use case
}
```

Có thể dùng `noRollbackFor` cho trường hợp đặc biệt, nhưng cần thiết kế cẩn thận để tránh commit một trạng thái nghiệp vụ chưa hoàn chỉnh. Hãy để exception biểu diễn lỗi có ý nghĩa và thống nhất rollback policy ở service boundary.

Một lưu ý kỹ thuật: Spring thường áp dụng transaction qua proxy. Gọi một phương thức `@Transactional` khác trong cùng instance bằng self-invocation có thể bỏ qua proxy và không kích hoạt transaction như mong đợi. Đặt transaction ở public service entry point được gọi từ bean khác, hoặc dùng cách tổ chức transaction phù hợp với ứng dụng.

## 4. Ví dụ use case tạo đơn hàng với nhiều repository

Giả sử hệ thống có Customer, Product, Inventory và Order. Một request tạo đơn hàng gồm customer ID, product ID và quantity. Service cần kiểm tra khách hàng, giữ hàng và lưu đơn.

Có thể tách phần dữ liệu đầu vào thành command:

```java
public record CreateOrderCommand(
        Long customerId,
        Long productId,
        int quantity) {
}
```

Service điều phối:

```java
@Service
public class OrderApplicationService {

    private final CustomerRepository customers;
    private final ProductRepository products;
    private final InventoryRepository inventory;
    private final OrderRepository orders;

    public OrderApplicationService(
            CustomerRepository customers,
            ProductRepository products,
            InventoryRepository inventory,
            OrderRepository orders) {
        this.customers = customers;
        this.products = products;
        this.inventory = inventory;
        this.orders = orders;
    }

    @Transactional
    public Order createOrder(CreateOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new InvalidOrderException(
                "Quantity must be greater than zero");
        }

        Customer customer = customers.findById(command.customerId())
            .orElseThrow(() -> new CustomerNotFoundException(
                command.customerId()));

        Product product = products.findById(command.productId())
            .orElseThrow(() -> new ProductNotFoundException(
                command.productId()));

        customer.requireActive();
        product.requireSellable();

        inventory.reserve(product.getId(), command.quantity());

        Order order = Order.create(
            customer,
            product,
            command.quantity(),
            product.getCurrentPrice());

        return orders.save(order);
    }
}
```

Ví dụ đã lược bỏ constructor và chi tiết persistence để làm rõ luồng. Giá được chụp vào Order tại thời điểm tạo để lịch sử đơn hàng không thay đổi khi giá Product được cập nhật sau đó.

Nếu `inventory.reserve(...)` ném exception do không đủ hàng, transaction có thể rollback thay đổi tồn kho và không lưu Order. Điều này chỉ đúng khi thao tác tồn kho và Order thực sự tham gia cùng transaction manager và cùng transaction resource. Nếu chúng nằm ở database hoặc dịch vụ khác, cần chiến lược nhất quán phân tán riêng.

## 5. Không để controller tự điều phối nhiều repository

Spring Data REST tự động tạo endpoint cho repository được export. Cách này phù hợp với thao tác CRUD đơn giản. Nhưng nếu tạo một resource đòi hỏi nhiều bước nghiệp vụ, gọi trực tiếp repository endpoint có thể không thể hiện đầy đủ use case.

Có thể tạo một custom REST endpoint gọi application service:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderCommandController {

    private final OrderApplicationService orderService;

    public OrderCommandController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        Order order = orderService.createOrder(
            new CreateOrderCommand(
                request.customerId(),
                request.productId(),
                request.quantity()));

        URI location = URI.create("/api/orders/" + order.getId());

        return ResponseEntity.created(location)
            .body(OrderResponse.from(order));
    }
}
```

Controller nhận DTO đầu vào, gọi một phương thức use case và trả response. Nó không trực tiếp gọi nhiều repository, không quyết định thứ tự persistence và không tự quản lý commit/rollback.

Trong ứng dụng Spring Data REST, có thể dùng `@BasePathAwareController` nếu muốn custom controller hoạt động dưới base path Spring Data REST. Nếu dùng `@RestController` thông thường, cần thiết kế mapping và base path rõ ràng để tránh xung đột với repository resources. Chọn một URL command riêng, ví dụ `/api/orders/commands` hoặc `/api/orders` nếu repository collection endpoint không chiếm cùng route.

## 6. Repository endpoint và application service endpoint có thể cùng tồn tại

Spring Data REST vẫn hữu ích cho CRUD đơn giản và resource navigation. Một ứng dụng có thể công bố:

- Repository resource để đọc danh sách Order, xem item và thực hiện thao tác CRUD được phép.
- Custom command endpoint để tạo đơn hàng, hủy đơn hoặc xác nhận thanh toán.
- Service layer dùng chung cho cả HTTP controller, scheduled job hoặc message consumer.

Điểm quan trọng là mọi đường gọi thực hiện cùng một nghiệp vụ nên đi qua cùng application service. Nếu custom controller tạo Order qua service nhưng một endpoint repository khác cho phép ghi Order trực tiếp, client có thể đi vòng qua bước kiểm tra tồn kho hoặc quy tắc nghiệp vụ. Hãy giới hạn repository methods và REST exposure để không tạo đường ghi bỏ qua use case.

Có thể ẩn thao tác ghi repository bằng cấu hình Spring Data REST phù hợp, ví dụ `@RestResource(exported = false)` trên method hoặc `@RepositoryRestResource(exported = false)` trên repository khi cần. Việc ẩn endpoint phải đi cùng thiết kế API và authorization; nó không thay thế service validation.

## 7. Nhiều repository có thực sự nằm trong cùng transaction không?

`@Transactional` không tự biến nhiều hệ thống lưu trữ độc lập thành một transaction nguyên tử. Cần xác định:

- Các repository dùng cùng database hay khác database?
- Có cùng transaction manager hay mỗi datasource có transaction manager riêng?
- Có dùng JPA và JDBC trên cùng datasource với transaction integration tương thích không?
- Có thao tác gọi HTTP, gửi email hoặc publish message trong transaction không?

Với nhiều repository cùng một database và transaction manager, Spring thường có thể điều phối chúng trong một transaction. Với nhiều datasource, mỗi transaction manager quản lý resource riêng. Một transaction cục bộ không tự rollback transaction đã commit ở database khác.

Nếu một use case phải cập nhật hai database độc lập, cần cân nhắc XA/JTA khi môi trường hỗ trợ và yêu cầu nguyên tử thực sự phù hợp. Nhiều hệ thống hiện đại chọn eventual consistency bằng outbox, saga hoặc quy trình bù trừ thay vì transaction phân tán đồng bộ.

## 8. Xử lý side effect ngoài database bằng Outbox hoặc Saga

Gửi email, gọi payment provider hoặc publish message đến broker là side effect bên ngoài transaction database. Nếu gọi hệ thống ngoài giữa transaction rồi database rollback, hệ thống ngoài có thể đã thực hiện hành động mà database không ghi nhận. Ngược lại, database commit nhưng message publish thất bại cũng có thể khiến các hệ thống lệch trạng thái.

Một cách phổ biến là **Transactional Outbox**:

1. Trong cùng transaction database, lưu Order và một OutboxEvent.
2. Commit cả hai cùng nhau.
3. Một publisher nền đọc các outbox record chưa gửi và publish message.
4. Đánh dấu message đã gửi hoặc xử lý retry theo chính sách.
5. Consumer xử lý idempotent để một message được giao lại không tạo tác dụng lặp.

Ví dụ service ghi outbox:

```java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = createAndSaveOrder(command);

    outboxRepository.save(
        OutboxEvent.orderCreated(order.getId()));

    return order;
}
```

Outbox bảo đảm Order và ý định phát event được lưu cùng transaction. Nó không bảo đảm message được giao đúng một lần; publisher/consumer cần retry, deduplication và idempotency.

**Saga** phù hợp với quy trình dài gồm nhiều bước qua các service hoặc database độc lập. Mỗi bước commit cục bộ và phát event/command cho bước tiếp theo. Nếu một bước thất bại, saga chạy hành động bù trừ đã thiết kế, ví dụ giải phóng hàng đã giữ hoặc hoàn tiền. Hành động bù trừ là nghiệp vụ riêng và không phải rollback database theo nghĩa ACID.

## 9. Concurrency: tránh hai request cùng sử dụng một tài nguyên

Transaction bảo vệ tính nguyên tử, nhưng không tự giải quyết mọi race condition. Ví dụ hai request cùng đọc tồn kho là 1, cả hai đều thấy đủ hàng và cùng tạo Order. Nếu chỉ đọc rồi giảm số lượng bằng setter, có thể xảy ra overselling.

Một số giải pháp:

- Dùng optimistic locking với `@Version` để phát hiện cập nhật đồng thời và retry/return conflict theo nghiệp vụ.
- Dùng pessimistic lock cho thao tác cần khóa hàng tồn kho trong transaction, ví dụ query có `@Lock(LockModeType.PESSIMISTIC_WRITE)`.
- Dùng câu lệnh cập nhật có điều kiện như `UPDATE inventory SET quantity = quantity - :n WHERE product_id = :id AND quantity >= :n`, sau đó kiểm tra số hàng được cập nhật.
- Dùng unique constraint hoặc database constraint cho invariant cần được bảo vệ ở tầng lưu trữ.

Ví dụ optimistic locking:

```java
@Entity
public class InventoryItem {

    @Id
    private Long productId;

    private int availableQuantity;

    @Version
    private long version;

    public void reserve(int quantity) {
        if (quantity <= 0 || availableQuantity < quantity) {
            throw new InsufficientStockException();
        }
        availableQuantity -= quantity;
    }
}
```

Khi hai transaction cùng cập nhật một version, một transaction có thể nhận optimistic locking failure. Ứng dụng cần quyết định có retry hay trả conflict cho client. Không retry vô hạn; chỉ retry lỗi tạm thời và bảo đảm command có tính idempotent khi có thể.

## 10. Kết hợp điều phối với auditing

Khi service điều phối nhiều repository, audit metadata cần phản ánh đúng người dùng và thời điểm thực hiện use case. Spring Data auditing có thể tự động ghi `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy` và `@LastModifiedDate` cho entity được cấu hình auditing.

Ví dụ:

```java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Order {

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
```

Bật auditing:

```java
@Configuration
@EnableJpaAuditing
class JpaAuditingConfiguration {
}
```

Cung cấp `AuditorAware` để Spring biết người dùng hiện tại:

```java
@Bean
AuditorAware<String> auditorAware() {
    return () -> Optional.ofNullable(
        SecurityContextHolder.getContext().getAuthentication())
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
}
```

Ví dụ trên cần xử lý trường hợp anonymous/system user theo chính sách của ứng dụng. Với job nền hoặc message consumer, security context HTTP có thể không tồn tại; hãy cung cấp auditor riêng như `system` hoặc tên service để audit record vẫn có nguồn rõ ràng.

Auditing entity tự động ghi metadata khi persistence lifecycle phù hợp diễn ra. Nếu cần audit một nghiệp vụ tổng hợp như “đơn hàng được tạo từ kênh nào” hoặc “ai đã duyệt toàn bộ đơn”, có thể ghi thêm domain event hoặc audit record trong cùng use case. Không nên chỉ dựa vào `@LastModifiedBy` để thay thế lịch sử nghiệp vụ.

## 11. Kiểm thử service điều phối nhiều repository

Service layer có thể kiểm thử độc lập bằng unit test với mock repository, tập trung vào quyết định nghiệp vụ:

- Customer không tồn tại: không tạo Order.
- Customer không active: từ chối use case.
- Product không thể bán: không reserve inventory.
- Tồn kho không đủ: không lưu Order.
- Mọi điều kiện hợp lệ: reserve inventory và lưu Order với giá tại thời điểm đặt.
- Lỗi khi lưu Order: transaction integration test xác nhận thay đổi tồn kho rollback.
- Auditor hiện tại: entity được ghi nhận đúng người tạo/cập nhật.

Mock unit test xác nhận thứ tự và tương tác nhưng không chứng minh transaction thực sự rollback. Với rollback, optimistic locking, database constraints và auditing JPA, cần integration test chạy với Spring context và database phù hợp.

Ví dụ kiểm tra rollback nên đặt trong test transaction riêng hoặc gọi service qua Spring proxy. Tránh gọi trực tiếp method nội bộ trên object test tự tạo rồi kết luận `@Transactional` đã hoạt động.

## 12. Các lỗi thiết kế thường gặp

**Controller gọi nhiều repository trực tiếp**

Logic use case nằm rải rác, khó tái sử dụng và kiểm thử. Chuyển điều phối vào application service.

**Mỗi repository tự mở transaction riêng**

Các bước có thể commit độc lập, dẫn đến dữ liệu chỉ được lưu một phần. Đặt transaction boundary ở service entry point cho use case cần tính nguyên tử.

**Cho rằng mọi repository đều thuộc cùng transaction**

Kiểm tra datasource và transaction manager. Nhiều database hoặc hệ thống ngoài cần distributed consistency strategy.

**Gọi payment/email/message broker bên trong transaction và coi đó là nguyên tử**

Database rollback không thể hoàn tác side effect đã xảy ra ở hệ thống ngoài. Dùng outbox, saga hoặc cơ chế bù trừ phù hợp.

**Repository REST cho phép ghi bỏ qua service**

Giới hạn REST exposure hoặc chuyển thao tác ghi nhạy cảm sang command endpoint gọi service. Bảo đảm authorization được kiểm tra trên mọi đường ghi.

**Dùng transaction thay cho concurrency control**

Transaction không tự ngăn mọi lost update hoặc overselling. Dùng optimistic/pessimistic locking hoặc atomic conditional update cho invariant cần bảo vệ.

**Auditing chỉ dựa vào HTTP user**

Job nền và message consumer không có HTTP security context. Xác định auditor cho từng loại execution context.

## Tóm tắt

- Repository tập trung vào persistence; application service điều phối use case có nhiều repository; controller chỉ xử lý giao thức HTTP.
- Đặt `@Transactional` tại service boundary để các repository dùng chung transaction manager cùng commit hoặc rollback.
- Mặc định Spring rollback với unchecked exception; cấu hình `rollbackFor` khi checked exception cũng phải rollback.
- Nhiều datasource hoặc hệ thống ngoài không tự trở thành một transaction ACID; cân nhắc outbox, saga hoặc bù trừ.
- Dùng optimistic/pessimistic locking hoặc atomic update để bảo vệ dữ liệu trước concurrency.
- Dùng Spring Data auditing và `AuditorAware` để ghi nhận người tạo/cập nhật; bổ sung audit event cho lịch sử nghiệp vụ.
- Giới hạn repository REST write exposure khi thao tác cần đi qua application service; kiểm thử transaction bằng integration test.

## Tài liệu tham khảo

- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data REST — Repository events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Jakarta Persistence — Locking and version attributes](https://jakarta.ee/specifications/persistence/)

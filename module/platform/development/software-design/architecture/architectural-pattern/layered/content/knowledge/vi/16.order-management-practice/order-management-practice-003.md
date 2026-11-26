# Thực hành hệ thống đơn hàng

## Triển khai luồng tạo đơn hàng từ API qua nghiệp vụ đến lưu trữ

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — **Học tổ chức phần mềm theo kiến trúc phân tầng** — luồng tạo đơn hàng là ví dụ thực tế để thấy các tầng phối hợp mà vẫn giữ trách nhiệm riêng. API tiếp nhận yêu cầu và xác thực dữ liệu giao thức; tầng ứng dụng điều phối ca sử dụng; mô hình miền bảo vệ quy tắc nghiệp vụ; tầng truy cập dữ liệu chuyển mô hình sang cấu trúc lưu trữ.

Bài học đi theo một request `POST /api/orders` từ lúc client gửi danh sách sản phẩm đến khi đơn hàng được commit vào cơ sở dữ liệu và API trả `201 Created`. Ví dụ dùng Java và Spring Boot, Spring Data JPA cùng một cơ sở dữ liệu quan hệ. Các kiểu và tên package là minh họa; điểm quan trọng là ranh giới và thứ tự xử lý.

## 1. Xác định hành vi và dữ liệu đầu vào

Một yêu cầu tạo đơn hàng tối thiểu có danh sách sản phẩm và số lượng. Client không được tự quyết định giá cuối cùng hoặc trạng thái đơn. Giá phải được lấy từ nguồn dữ liệu đáng tin cậy của hệ thống, còn trạng thái ban đầu do nghiệp vụ quyết định.

Ví dụ JSON:

```json
{
  "items": [
    { "productId": "7a13c5c0-8f62-4c3c-9b36-1dfe82fca101", "quantity": 2 },
    { "productId": "d8c6c52a-7d84-4b5d-9e1c-0d85f9f19f02", "quantity": 1 }
  ]
}
```

Danh tính khách hàng nên lấy từ principal đã được xác thực, thay vì tin một `customerId` tùy ý trong body. Request chỉ chứa dữ liệu mà client được phép đề xuất; server chịu trách nhiệm xác định giá, tên sản phẩm, định danh đơn và trạng thái.

Trước khi viết code, hãy xác định các điều kiện cơ bản:

- Request phải có ít nhất một dòng hàng.
- Mỗi dòng phải có `productId` hợp lệ và `quantity` lớn hơn 0.
- Sản phẩm phải tồn tại và đang được phép bán.
- Giá và thông tin mô tả được lấy từ nguồn dữ liệu phía server.
- Đơn hàng lưu snapshot các thông tin cần thiết tại thời điểm đặt, chẳng hạn tên sản phẩm và đơn giá.
- Tổng tiền và trạng thái được tạo theo quy tắc miền, không nhận trực tiếp từ client.

## 2. Nhìn toàn bộ luồng trước khi đi vào từng tầng

```text
Client
  |
  | POST /api/orders + JSON
  v
OrderController (Presentation)
  |  deserialize, validate request, lấy customer từ principal
  |  Request DTO -> Command
  v
PlaceOrderService (Application)
  |  tải thông tin sản phẩm qua port
  |  điều phối ca sử dụng và transaction
  v
Order / OrderLine / Money (Domain)
  |  kiểm tra bất biến, tạo trạng thái PLACED
  v
OrderRepository (port)
  |
  v
JpaOrderRepositoryAdapter (Data Access)
  |  Domain -> JPA Entity
  v
Spring Data JPA -> Database
  |
  | transaction proxy commit sau khi handle() trả về
  v
Controller nhận OrderId sau commit
  |
  v
OrderController -> 201 Created + Location
```

Sơ đồ thể hiện luồng gọi chính. Trong mã nguồn, application service phụ thuộc vào hợp đồng repository/port; adapter JPA triển khai hợp đồng đó. Vì vậy, application không cần biết bảng, câu SQL hoặc class JPA cụ thể.

## 3. Tầng trình bày: nhận request và chuyển thành command

### Request DTO và validation ở biên API

Request DTO phản ánh hợp đồng HTTP. Bean Validation kiểm tra cấu trúc và dữ liệu đầu vào cơ bản trước khi gọi use case:

```java
public record CreateOrderRequest(
    @NotEmpty List<@Valid CreateOrderItemRequest> items
) {}

public record CreateOrderItemRequest(
    @NotNull UUID productId,
    @Positive int quantity
) {}
```

`@NotEmpty` bảo đảm danh sách có phần tử; `@Valid` kích hoạt kiểm tra từng dòng; `@Positive` yêu cầu số lượng lớn hơn 0. Đây là kiểm tra dữ liệu ở ranh giới HTTP. Domain vẫn cần bảo vệ bất biến của mình vì có thể được gọi từ job, message consumer hoặc một use case khác không đi qua controller này.

### Controller chỉ làm nhiệm vụ giao tiếp

Controller chuyển request thành command và trả response HTTP. Nó không tự truy vấn JPA, tính giá hoặc sửa trạng thái đơn.

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final PlaceOrderService placeOrder;

    OrderController(PlaceOrderService placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    ResponseEntity<CreateOrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request,
            @AuthenticationPrincipal AuthenticatedCustomer principal) {

        var items = request.items().stream()
            .map(item -> new PlaceOrderItem(
                new ProductId(item.productId()), item.quantity()))
            .toList();

        var command = new PlaceOrderCommand(principal.customerId(), items);
        OrderId orderId = placeOrder.handle(command);

        URI location = URI.create("/api/orders/" + orderId.value());
        return ResponseEntity.created(location)
            .body(new CreateOrderResponse(orderId.value()));
    }
}

public record CreateOrderResponse(UUID orderId) {}
```

`AuthenticatedCustomer` là kiểu principal của ứng dụng, được Spring Security cung cấp sau khi xác thực; tên và cách cấu hình cụ thể tùy dự án. Nếu API dùng một cơ chế xác thực khác, controller vẫn cần lấy định danh người dùng từ ngữ cảnh đã tin cậy. Không nên cho client gửi `customerId` rồi mặc nhiên xem đó là danh tính đã xác thực.

Controller trả `201 Created` sau khi lời gọi application service hoàn tất. `Location` chỉ tới tài nguyên đơn hàng vừa tạo. Nếu commit transaction thất bại, lời gọi qua Spring transaction proxy ném lỗi về controller và response thành công không được gửi.

## 4. Tầng ứng dụng: điều phối ca sử dụng tạo đơn

Tầng ứng dụng nhận command có ý nghĩa với use case. Command không phụ thuộc JSON, HTTP status hay JPA entity:

```java
public record PlaceOrderCommand(
    CustomerId customerId,
    List<PlaceOrderItem> items
) {}

public record PlaceOrderItem(ProductId productId, int quantity) {}
```

Application service chịu trách nhiệm điều phối:

1. Xác định tập sản phẩm cần dùng.
2. Lấy thông tin sản phẩm đang được phép bán qua một port.
3. Tạo các dòng đơn hàng với snapshot tên và đơn giá từ server.
4. Gọi domain model để tạo đơn và kiểm tra bất biến.
5. Yêu cầu repository lưu đơn.
6. Trả về định danh của đơn hàng.

Hợp đồng mà application cần có thể được khai báo như sau:

```java
public interface ProductCatalogPort {
    Map<ProductId, ProductSnapshot> findActiveProducts(Set<ProductId> ids);
}

public record ProductSnapshot(
    ProductId id,
    String name,
    Money unitPrice
) {}

public interface OrderRepository {
    void save(Order order);
}
```

Ví dụ application service:

```java
@Service
class PlaceOrderService {
    private final ProductCatalogPort catalog;
    private final OrderRepository orders;
    private final Clock clock;

    PlaceOrderService(
            ProductCatalogPort catalog,
            OrderRepository orders,
            Clock clock) {
        this.catalog = catalog;
        this.orders = orders;
        this.clock = clock;
    }

    @Transactional
    public OrderId handle(PlaceOrderCommand command) {
        if (command.items().isEmpty()) {
            throw new EmptyOrderException();
        }

        Set<ProductId> productIds = command.items().stream()
            .map(PlaceOrderItem::productId)
            .collect(Collectors.toSet());

        Map<ProductId, ProductSnapshot> products =
            catalog.findActiveProducts(productIds);

        List<OrderLine> lines = command.items().stream()
            .map(item -> {
                ProductSnapshot product = products.get(item.productId());
                if (product == null) {
                    throw new ProductNotAvailableException(item.productId());
                }
                return new OrderLine(
                    product.id(), product.name(),
                    product.unitPrice(), item.quantity());
            })
            .toList();

        Order order = Order.place(command.customerId(), lines, clock.instant());
        orders.save(order);
        return order.id();
    }
}
```

Đây là ví dụ cấu trúc; các kiểu định danh, ngoại lệ và adapter cần được định nghĩa trong ứng dụng thực tế. `ProductCatalogPort` trong ví dụ được giả định là truy cập dữ liệu nội bộ hoặc nguồn dữ liệu tham gia cùng ranh giới transaction. Nếu việc lấy giá gọi một dịch vụ từ xa, không nên mặc nhiên giữ transaction database mở trong lúc chờ mạng; hãy xác định hợp đồng báo giá/quote và thời điểm chốt giá riêng.

Application service điều phối, nhưng không tự đặt giá từ request và không tự sửa các trường nội bộ của `Order`. Nó yêu cầu domain tạo một đơn hợp lệ và repository lưu đơn đó.

## 5. Tầng miền: bảo vệ bất biến của đơn hàng

Domain model biểu diễn khái niệm nghiệp vụ và bảo vệ những điều kiện phải luôn đúng, bất kể lời gọi đến từ HTTP, job nền hay message consumer.

Ví dụ một dòng hàng lưu snapshot thông tin tại thời điểm đặt:

```java
public record OrderLine(
    ProductId productId,
    String productName,
    Money unitPrice,
    int quantity
) {
    public OrderLine {
        Objects.requireNonNull(productId);
        Objects.requireNonNull(productName);
        Objects.requireNonNull(unitPrice);
        if (quantity <= 0) {
            throw new InvalidOrderQuantityException(quantity);
        }
    }

    public Money subtotal() {
        return unitPrice.multiply(quantity);
    }
}
```

Đơn hàng kiểm tra danh sách dòng hàng và khởi tạo trạng thái ban đầu:

```java
public class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines;
    private final Instant placedAt;
    private OrderStatus status;

    private Order(
            OrderId id,
            CustomerId customerId,
            List<OrderLine> lines,
            Instant placedAt) {
        this.id = id;
        this.customerId = customerId;
        this.lines = List.copyOf(lines);
        this.placedAt = placedAt;
        this.status = OrderStatus.PLACED;
    }

    public static Order place(
            CustomerId customerId,
            List<OrderLine> lines,
            Instant placedAt) {
        if (lines == null || lines.isEmpty()) {
            throw new EmptyOrderException();
        }
        return new Order(
            OrderId.newId(), customerId, lines, placedAt);
    }

    public OrderId id() { return id; }
}
```

Đoạn mã đã lược bỏ getter và chi tiết tính tổng. Trong domain đầy đủ, tổng tiền có thể được tính từ `subtotal()` của các dòng bằng `Money` để giữ quy tắc làm tròn và đơn vị tiền nhất quán. Nếu một đơn chỉ được dùng một loại tiền, domain cần kiểm tra các dòng cùng currency trước khi cộng.

Các điểm cần giữ:

- Giá đơn vị được lấy từ catalog phía server, không lấy từ giá client gửi.
- `OrderLine` giữ snapshot tên và giá để đơn cũ không thay đổi khi catalog cập nhật sản phẩm.
- Số lượng phải dương và đơn phải có ít nhất một dòng.
- Trạng thái ban đầu được tạo bởi domain, ví dụ `PLACED` hoặc `PENDING_PAYMENT` tùy chính sách.
- Định danh đơn được tạo ở phía server.

Không phải mọi kiểm tra đều thuộc domain. Kiểm tra JSON có parse được UUID hay không thuộc presentation; kiểm tra sản phẩm có tồn tại/được bán có thể cần port của application; bất biến của đơn và dòng hàng thuộc domain.

## 6. Tầng truy cập dữ liệu: lưu aggregate qua repository adapter

Application chỉ biết hợp đồng `OrderRepository`. Adapter dữ liệu chuyển `Order` thành persistence entity và dùng Spring Data JPA để lưu:

```java
@Repository
class JpaOrderRepositoryAdapter implements OrderRepository {
    private final SpringDataOrderRepository repository;

    JpaOrderRepositoryAdapter(SpringDataOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void save(Order order) {
        repository.save(OrderEntity.fromDomain(order));
    }
}

interface SpringDataOrderRepository
        extends JpaRepository<OrderEntity, UUID> {
}
```

Persistence entity phản ánh schema và quan hệ ORM:

```java
@Entity
@Table(name = "orders")
class OrderEntity {
    @Id
    private UUID id;

    @Column(name = "customer_id", nullable = false)
    private UUID customerId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(name = "placed_at", nullable = false)
    private Instant placedAt;

    @OneToMany(cascade = CascadeType.ALL, orphanRemoval = true)
    @JoinColumn(name = "order_id")
    private List<OrderLineEntity> lines = new ArrayList<>();

    protected OrderEntity() { }

    static OrderEntity fromDomain(Order order) {
        // Ánh xạ id, customerId, status, placedAt và từng dòng hàng.
        // Chi tiết chuyển đổi được lược bỏ.
        return new OrderEntity();
    }
}
```

Đoạn entity minh họa cách ORM ánh xạ đơn và các dòng hàng; phương thức mapping được lược bỏ để tập trung vào ranh giới. Trong implementation thật, cần ánh xạ đầy đủ trường, cấu hình khóa ngoại, precision/scale của tiền và constraint phù hợp. Có thể dùng `@EmbeddedId`, `@Embeddable` hoặc mapping khác tùy schema.

Repository adapter là nơi xử lý chi tiết JPA. Không trả `OrderEntity`, `HibernateProxy` hoặc kiểu của driver database lên application/controller. Tách domain model khỏi persistence entity giúp thay schema hoặc ORM mà không buộc hợp đồng HTTP thay đổi.

## 7. Transaction: lúc nào đơn hàng thực sự được lưu?

`@Transactional` thường đặt trên application service vì nó xác định phạm vi dữ liệu của ca sử dụng. Trong ví dụ, việc đọc sản phẩm nội bộ, tạo đơn và lưu aggregate tham gia cùng transaction database nếu chúng dùng cùng transaction manager và datasource.

Trình tự cơ bản:

1. Spring transaction proxy mở transaction trước khi gọi thân `handle()`.
2. Application service đọc dữ liệu cần thiết, tạo domain object và gọi repository.
3. JPA có thể đưa entity vào persistence context; câu `save()` không nhất thiết đã phát toàn bộ SQL ngay tại dòng đó.
4. Khi phương thức `handle()` kết thúc bình thường, transaction interceptor thực hiện commit trước khi trả quyền điều khiển về controller.
5. Nếu flush/commit thành công, controller nhận `OrderId` và tạo response `201 Created`.
6. Nếu lỗi xảy ra trước commit hoặc trong flush/commit, transaction rollback theo cấu hình và lỗi được chuyển lên tầng xử lý HTTP.

Với Spring mặc định, unchecked exception (`RuntimeException`) và `Error` làm transaction rollback; checked exception không tự động rollback trừ khi cấu hình `rollbackFor` hoặc quy tắc tương ứng. Nếu một ngoại lệ nghiệp vụ cần rollback, hãy dùng loại exception và cấu hình nhất quán, không chỉ giả định mọi exception đều có cùng hành vi.

`@Transactional` hoạt động qua proxy trong cách cấu hình Spring phổ biến. Lời gọi nội bộ cùng object (self-invocation) không đi qua proxy như lời gọi từ bean khác, nên annotation trên phương thức được gọi nội bộ có thể không tạo ranh giới transaction như mong đợi. Đặt ranh giới ở phương thức public của bean được gọi qua Spring proxy và kiểm tra propagation khi có transaction sẵn.

Transaction database chỉ bảo vệ các thao tác tham gia cùng transaction manager/datasource. Nếu application service gọi Payment Service hoặc Inventory Service qua HTTP, transaction JPA hiện tại không thể rollback thay đổi đã commit ở dịch vụ kia. Khi quy trình tạo đơn cần giữ chỗ hoặc thanh toán ở dịch vụ ngoài, hãy thiết kế workflow có trạng thái trung gian, idempotency, outbox/saga và hành động bù trừ; không coi một annotation là distributed transaction.

## 8. Xử lý lỗi và phản hồi API

Mỗi tầng có thể phát hiện một loại lỗi khác nhau. API nên chuyển lỗi nội bộ thành phản hồi ổn định, không làm lộ SQL, tên bảng hoặc stack trace.

| Tình huống | Nơi phát hiện thường gặp | Phản hồi API có thể dùng |
| --- | --- | --- |
| JSON sai định dạng hoặc thiếu trường | Deserialize/Bean Validation ở presentation | `400 Bad Request` |
| Sản phẩm không tồn tại hoặc không được bán | Application khi gọi catalog port | `404 Not Found` hoặc `422 Unprocessable Content`, theo hợp đồng API |
| Quy tắc nghiệp vụ không cho phép tạo đơn | Domain/application | `409 Conflict` hoặc `422`, tùy ngữ nghĩa lỗi |
| Lỗi constraint hoặc lỗi lưu trữ | Adapter/database khi flush hoặc commit | `409` nếu là xung đột nghiệp vụ đã biết; nếu không, lỗi server phù hợp |
| Database hoặc dependency tạm thời không sẵn sàng | Infrastructure | `503 Service Unavailable` khi phù hợp, có thể kèm hướng dẫn retry |

`@RestControllerAdvice` có thể ánh xạ exception đã định nghĩa sang `ProblemDetail` hoặc response lỗi thống nhất. Việc ánh xạ cần dựa trên loại lỗi nghiệp vụ/kỹ thuật đã phân loại; không nên trả mọi lỗi thành `400` hoặc bắt `Exception` rồi che mất nguyên nhân.

Ví dụ rút gọn:

```java
@RestControllerAdvice
class ApiExceptionHandler {
    @ExceptionHandler(ProductNotAvailableException.class)
    ResponseEntity<ProblemDetail> productUnavailable(
            ProductNotAvailableException exception) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.UNPROCESSABLE_ENTITY);
        problem.setTitle("Sản phẩm không khả dụng");
        problem.setDetail("Một hoặc nhiều sản phẩm không thể được đặt.");
        return ResponseEntity.unprocessableEntity().body(problem);
    }
}
```

Thông báo trả về client không nên chứa thông tin nội bộ nhạy cảm. Log kỹ thuật có thể ghi correlation ID và nguyên nhân gốc để đội vận hành điều tra.

## 9. Các điểm nhất quán cần quyết định rõ

### Giá tại thời điểm tạo đơn

Đơn hàng thường lưu snapshot giá tại thời điểm đặt. Cần xác định chính xác thời điểm chốt giá và cách xử lý khi giá thay đổi đồng thời. Nếu giá đến từ cùng database, transaction và isolation quyết định snapshot mà truy vấn nhìn thấy; nếu cần bảo đảm giá báo trước còn hiệu lực, có thể dùng quote có thời hạn hoặc phiên bản giá. Không dùng giá client gửi làm nguồn sự thật.

### Trùng request khi client thử lại

Client có thể gửi lại `POST /api/orders` vì timeout hoặc mất response dù server đã commit đơn. Nếu mỗi lần gửi tạo đơn mới, khách hàng có thể bị đặt trùng. Với API cần bảo vệ tình huống này, dùng idempotency key do client tạo cho một ý định đặt hàng; lưu key cùng kết quả trong database với unique constraint để hai request đồng thời không tạo hai đơn. Khi nhận lại key đã xử lý, trả kết quả của lần trước theo hợp đồng API.

### Bất biến phải được bảo vệ ở nơi phù hợp

Domain kiểm tra các quy tắc trong một đối tượng; database constraint bảo vệ dữ liệu trước cạnh tranh và lỗi ở nhiều đường ghi. Ví dụ, khóa ngoại bảo vệ quan hệ khách hàng, `NOT NULL` bảo vệ trường bắt buộc, unique constraint bảo vệ mã đơn hoặc idempotency key. Không nên chỉ dùng câu `if` trong Java để bảo vệ một điều kiện duy nhất trên toàn hệ thống khi nhiều transaction có thể ghi đồng thời.

## 10. Kiểm thử toàn bộ luồng tạo đơn

Kiểm thử nên bao phủ từng ranh giới và một số luồng tích hợp:

- **Controller test:** request hợp lệ tạo response `201`, có `Location`; request thiếu dòng hàng hoặc số lượng không hợp lệ nhận `400`; customer ID lấy từ principal đã xác thực.
- **Domain unit test:** đơn rỗng bị từ chối; quantity không dương bị từ chối; tổng tiền và snapshot dòng hàng đúng; trạng thái ban đầu đúng.
- **Application service test:** tải sản phẩm cần thiết; từ chối sản phẩm không khả dụng; không lấy giá từ client; gọi repository lưu đúng aggregate.
- **Repository integration test:** lưu đơn cùng các dòng hàng, đọc lại giữ đúng định danh, trạng thái, thời điểm và giá snapshot.
- **Transaction integration test:** lỗi trong quy trình khiến thay đổi database rollback; lỗi tại flush/commit không trả response thành công.
- **Concurrency/idempotency test:** hai request cùng idempotency key không tạo hai đơn; constraint và xử lý xung đột hoạt động đúng.

Một số kiểm thử tích hợp cần chạy trên cùng loại database với môi trường triển khai vì hành vi constraint, locking, precision và transaction có thể khác database thay thế. Unit test domain không cần khởi động Spring hoặc database.

## 11. Checklist review luồng tạo đơn

Trước khi đưa endpoint vào sử dụng, hãy kiểm tra:

1. Controller chỉ xử lý HTTP, validation đầu vào và chuyển request thành command.
2. Danh tính khách hàng đến từ ngữ cảnh xác thực, không tin giá hoặc customer ID do client tự khai báo.
3. Application service điều phối đúng thứ tự và phụ thuộc vào port/hợp đồng.
4. Domain model bảo vệ bất biến về dòng hàng, số lượng, tiền và trạng thái.
5. Giá và thông tin sản phẩm được lấy từ nguồn đáng tin cậy, snapshot được lưu theo chính sách.
6. Repository adapter chịu trách nhiệm mapping domain sang persistence entity và lưu aggregate.
7. Transaction bao trùm đúng các thao tác database cần nhất quán; không giả định nó bao trùm dịch vụ từ xa.
8. Commit hoàn tất trước khi controller trả response thành công.
9. Lỗi được ánh xạ theo hợp đồng API và không làm lộ chi tiết nội bộ.
10. Có chiến lược cho request trùng, lỗi đồng thời và kiểm thử trên database phù hợp.

## Tự kiểm tra

1. Vì sao controller không nên nhận đơn giá do client gửi rồi lưu trực tiếp vào đơn hàng?
2. Request DTO và `PlaceOrderCommand` khác nhau ở mục đích nào?
3. Những bất biến nào nên được `Order` hoặc `OrderLine` bảo vệ, và kiểm tra nào thuộc tầng presentation?
4. Vì sao `repository.save()` chưa chắc đồng nghĩa dữ liệu đã commit vào database?
5. Khi nào `@Transactional` rollback theo mặc định trong Spring và điều gì xảy ra với checked exception?
6. Nếu tạo đơn cần gọi một dịch vụ tồn kho qua HTTP, vì sao transaction JPA không thể bảo đảm cả hai dịch vụ cùng rollback?
7. Idempotency key giúp xử lý tình huống client gửi lại request sau timeout như thế nào?


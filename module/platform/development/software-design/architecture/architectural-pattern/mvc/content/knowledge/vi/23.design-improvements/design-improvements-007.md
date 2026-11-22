# Thay phụ thuộc trực tiếp bằng ranh giới trừu tượng cần thiết

Trong ứng dụng MVC, Controller tiếp nhận request và gọi application service; application service điều phối ca sử dụng và có thể gọi repository hoặc dịch vụ bên ngoài; View nhận dữ liệu đã được chuẩn bị để trình bày. Các lời gọi trực tiếp này không tự động là sai. Chúng trở thành rủi ro khi một thành phần phải biết chi tiết triển khai của thành phần khác, hoặc khi thay đổi ở một chi tiết buộc nhiều phần không liên quan phải thay đổi theo.

Ranh giới trừu tượng giúp consumer phụ thuộc vào **hợp đồng về điều nó cần**, thay vì phụ thuộc vào cách provider thực hiện điều đó. Use case tạo đơn hàng cần khả năng lưu đơn; nó không cần biết ứng dụng dùng PostgreSQL, JPA hay một API lưu trữ từ xa. Controller cần khả năng thực hiện use case; nó không cần biết service được tạo bằng class cụ thể nào.

Tuy vậy, không phải mọi lời gọi trực tiếp đều cần thay bằng interface. Abstraction có chi phí: thêm kiểu dữ liệu, mapping, cấu hình, điểm điều hướng khi đọc mã và một hợp đồng cần duy trì. Mục tiêu là đặt ranh giới ở nơi có sự thay đổi độc lập hoặc nơi cần bảo vệ một chính sách ổn định.

## 1. Phụ thuộc trực tiếp là gì?

Một lớp có phụ thuộc trực tiếp khi nó tham chiếu đến kiểu hoặc chi tiết cụ thể của thành phần mà nó gọi. Trong Java, dependency thường xuất hiện qua trường, tham số constructor, lời gọi method, kế thừa, import framework hoặc truy cập global state.

Ví dụ Controller phụ thuộc trực tiếp vào service:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final CreateOrderService service;

    public OrderController(CreateOrderService service) {
        this.service = service;
    }

    @PostMapping
    public OrderResponse create(@RequestBody CreateOrderRequest request) {
        OrderCreated result = service.create(request);
        return new OrderResponse(result.orderId(), result.orderNumber());
    }
}
~~~

Đây không nhất thiết là thiết kế sai. Nếu CreateOrderService ổn định, chỉ có một implementation và không có lý do thay thế, phụ thuộc cụ thể có thể phù hợp. Nhưng nếu Controller cần được kiểm thử độc lập, use case có nhiều adapter gọi đến hoặc cách thực thi có khả năng thay đổi, một hợp đồng nhỏ có thể bảo vệ ranh giới tốt hơn.

### 1.1. Khi nào phụ thuộc trực tiếp trở thành vấn đề?

- Controller phải biết class triển khai cụ thể của application service.
- Application service import thư viện của nhà cung cấp bên ngoài.
- Quy tắc nghiệp vụ phụ thuộc trực tiếp vào HTTP client hoặc JPA implementation.
- Một thay đổi công nghệ buộc sửa nhiều module không liên quan.
- Test cần khởi tạo database chỉ để kiểm tra một quy tắc nhỏ.
- Một module gọi sâu vào package nội bộ của module khác thay vì dùng hợp đồng công khai.

Cần xem cả hướng phụ thuộc và tác động của thay đổi. Một class phụ thuộc vào class khác không tự động tạo coupling xấu; coupling trở thành vấn đề khi nó vượt qua ranh giới trách nhiệm hoặc làm thay đổi lan rộng.

## 2. Abstraction là hợp đồng về khả năng cần dùng

Abstraction mô tả điều một thành phần cần từ bên ngoài, không mô tả toàn bộ cách bên ngoài hoạt động.

Ví dụ, use case tạo đơn chỉ cần khả năng lưu đơn hàng:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Hợp đồng này không nói database nào, có bao nhiêu bảng, ORM nào hoặc câu SQL ra sao. Một implementation có thể dùng JPA; implementation khác có thể dùng JDBC, in-memory store cho test hoặc một dịch vụ lưu trữ khác.

### 2.1. Abstraction phải diễn đạt nhu cầu của bên gọi

Một interface hữu ích phản ánh ngôn ngữ và nhu cầu của consumer. Application service cần OrderRepository, không cần interface tổng quát có hàng chục method quản lý transaction, entity manager, query builder và cache. Hợp đồng càng nhỏ, bên gọi càng ít biết về bên triển khai.

### 2.2. Abstraction không phải chỉ là interface

Có thể tạo ranh giới bằng interface, abstract class, command/query, DTO ổn định, function/callback, message contract hoặc module API được giới hạn ở build. Interface là công cụ phổ biến trong Java, nhưng một kiểu dữ liệu cụ thể, ổn định cũng có thể là hợp đồng. Không cần tạo interface cho mọi record hoặc DTO.

### 2.3. Phân biệt abstraction và indirection

Abstraction có ý nghĩa khi nó bảo vệ hợp đồng hoặc che giấu chi tiết có khả năng thay đổi. Indirection chỉ thêm một bước chuyển tiếp.

~~~java
public interface OrderService {
    OrderResult create(CreateOrderCommand command);
}

public class DefaultOrderService implements OrderService {
    // Chỉ chuyển tiếp tới CreateOrderManager
}
~~~

Nếu DefaultOrderService không có trách nhiệm, chính sách hoặc khả năng thay thế riêng, interface và lớp triển khai này có thể chỉ làm người đọc phải mở thêm file. Hãy tạo abstraction vì có ranh giới thực sự cần bảo vệ, không phải vì mọi class đều phải có một interface cùng tên.

## 3. Dependency Inversion trong ứng dụng MVC

Dependency Inversion Principle (DIP) nói rằng chính sách cấp cao không nên phụ thuộc vào chi tiết cấp thấp; cả hai nên phụ thuộc vào abstraction. Chi tiết triển khai phụ thuộc vào abstraction mà chính sách cần.

~~~mermaid
flowchart TB
    Web[Web Controller]
    UseCase[Application Use Case]
    Port[Application Port / Contract]
    Domain[Domain Model]
    Adapter[Infrastructure Adapter]
    DB[(Database)]

    Web --> UseCase
    UseCase --> Port
    UseCase --> Domain
    Adapter -. implements .-> Port
    Adapter --> DB
~~~

Application use case định nghĩa port mà nó cần. Adapter persistence triển khai port đó. Controller gọi application use case qua hợp đồng. Domain không cần biết database hoặc framework web.

DIP không có nghĩa mọi dependency phải đi qua interface. Nó yêu cầu hướng phụ thuộc tôn trọng chính sách và ranh giới. Một module có thể dùng trực tiếp kiểu cụ thể bên trong chính nó nếu kiểu đó thuộc cùng trách nhiệm và không tạo ràng buộc không mong muốn.

### 3.1. Dependency Injection không đồng nghĩa với Dependency Inversion

- **Dependency Inversion:** nguyên tắc thiết kế về hướng phụ thuộc giữa chính sách và chi tiết.
- **Dependency Injection (DI):** kỹ thuật cung cấp dependency từ bên ngoài, thường qua constructor, setter hoặc method.

~~~java
public class CreateOrderService {
    private final OrderRepository orders;

    public CreateOrderService(OrderRepository orders) {
        this.orders = orders;
    }
}
~~~

Nếu OrderRepository là abstraction được thiết kế sai hoặc chỉ phản chiếu implementation, dùng DI chưa chắc đã tạo ra ranh giới tốt. Ngược lại, abstraction đúng nhưng được lấy qua static global locator vẫn có thể khó kiểm thử và che giấu dependency. Thiết kế hợp đồng và cách cung cấp dependency là hai quyết định liên quan nhưng riêng biệt.

## 4. Đặt abstraction ở phía sở hữu nhu cầu

Một nguyên tắc hữu ích là đặt port gần thành phần cần khả năng đó. Application service cần lưu đơn, vì vậy application có thể định nghĩa OrderRepository. Infrastructure triển khai interface này.

~~~text
order/
  application/
    port/
      in/
        CreateOrderUseCase.java
      out/
        OrderRepository.java
    service/
      CreateOrderService.java
    model/
      CreateOrderCommand.java
      OrderCreated.java
  domain/
    Order.java
    OrderId.java
  infrastructure/
    persistence/
      JpaOrderRepositoryAdapter.java
      SpringDataOrderJpaRepository.java
  web/
    OrderController.java
    CreateOrderRequest.java
    OrderResponse.java
~~~

- CreateOrderUseCase là khả năng ứng dụng công bố cho adapter đầu vào.
- OrderRepository là khả năng application cần từ persistence.
- JpaOrderRepositoryAdapter là chi tiết triển khai.
- OrderController là adapter HTTP.

Có kiến trúc đặt repository interface trong domain thay vì application, nhất là khi repository được xem là một phần của ngôn ngữ domain. Cả hai cách đều có thể hợp lý. Hãy đặt hợp đồng ở nơi sở hữu ý nghĩa và chính sách của nó, không chọn package chỉ theo thói quen.

## 5. Tách inbound port và outbound port

Trong Ports and Adapters (Hexagonal Architecture):

- **Inbound port:** use case mà ứng dụng cho phép bên ngoài gọi.
- **Inbound adapter:** Controller, message listener hoặc CLI chuyển yêu cầu bên ngoài thành lời gọi use case.
- **Outbound port:** khả năng mà ứng dụng cần từ hệ thống bên ngoài.
- **Outbound adapter:** JPA repository, HTTP client, message publisher hoặc file adapter triển khai khả năng đó.

~~~mermaid
flowchart LR
    Browser[Browser / API Client] --> Controller[MVC Controller]
    Controller --> InPort[CreateOrderUseCase]
    InPort --> App[CreateOrderService]
    App --> Domain[Order Domain]
    App --> OutPort[OrderRepository Port]
    Jpa[JpaOrderRepositoryAdapter] -. implements .-> OutPort
    Jpa --> DB[(Database)]
~~~

Controller không cần biết CreateOrderService là implementation nào. Application service không cần biết JpaOrderRepositoryAdapter hoặc Spring Data. Các adapter được nối với nhau ở composition root khi ứng dụng khởi động.

### 5.1. Không tạo port cho mọi lời gọi nội bộ

Nếu CreateOrderService gọi OrderNumberFormatter ổn định trong cùng module, dependency cụ thể có thể dễ hiểu hơn một interface không có mục đích thay thế. Port có giá trị hơn khi có ranh giới giữa module/tầng, bên triển khai có thể thay đổi độc lập, cần cô lập hệ thống ngoài, cần kiểm thử chính sách mà không khởi động hạ tầng hoặc hợp đồng thể hiện một năng lực có ý nghĩa.

## 6. Ví dụ: MVC gọi use case qua abstraction

### 6.1. Application contract

~~~java
public interface CreateOrderUseCase {
    OrderCreated handle(CreateOrderCommand command);
}

public record CreateOrderCommand(
    CustomerId customerId,
    UserId actorId,
    List<OrderLineInput> lines
) {}

public record OrderLineInput(ProductId productId, int quantity) {}

public record OrderCreated(OrderId orderId, String orderNumber) {}
~~~

Command mô tả yêu cầu nghiệp vụ, không phụ thuộc HTTP. Không đưa HttpServletRequest, ResponseEntity, Model hoặc CreateOrderRequest của Spring MVC vào application contract.

### 6.2. Outbound port

~~~java
public interface OrderRepository {
    void save(Order order);
}
~~~

Port chỉ có method cần cho ca sử dụng. Nếu một use case khác cần tìm đơn theo ID, có thể mở rộng hợp đồng hoặc tạo query port phù hợp. Tránh tạo repository interface khổng lồ chỉ vì mọi thao tác đều liên quan đến Order.

### 6.3. Implementation của application service

~~~java
public class CreateOrderService implements CreateOrderUseCase {

    private final OrderRepository orders;
    private final OrderPricing pricing;

    public CreateOrderService(
            OrderRepository orders,
            OrderPricing pricing) {
        this.orders = orders;
        this.pricing = pricing;
    }

    @Override
    public OrderCreated handle(CreateOrderCommand command) {
        Order order = Order.create(
            command.customerId(),
            command.actorId(),
            command.lines(),
            pricing
        );

        orders.save(order);
        return new OrderCreated(order.id(), order.number());
    }
}
~~~

OrderPricing là dependency được truyền vào. Nếu nó là policy domain ổn định, có thể dùng kiểu cụ thể. Nếu giá được lấy từ dịch vụ bên ngoài hoặc có nhiều nguồn độc lập, có thể định nghĩa port riêng. Không cần trừu tượng hóa trước khi có lý do.

### 6.4. Controller phụ thuộc inbound port

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final CreateOrderUseCase createOrder;
    private final OrderHttpMapper mapper;
    private final CurrentUserProvider currentUser;

    public OrderController(
            CreateOrderUseCase createOrder,
            OrderHttpMapper mapper,
            CurrentUserProvider currentUser) {
        this.createOrder = createOrder;
        this.mapper = mapper;
        this.currentUser = currentUser;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        CreateOrderCommand command = mapper.toCommand(
            request,
            currentUser.requireUserId()
        );

        OrderCreated result = createOrder.handle(command);
        OrderResponse response = mapper.toResponse(result);
        URI location = URI.create("/api/orders/" + response.id());

        return ResponseEntity.created(location).body(response);
    }
}
~~~

Controller phụ thuộc vào hợp đồng CreateOrderUseCase. Nó không biết implementation là CreateOrderService và cũng không cần biết dữ liệu được lưu bằng JPA hay adapter khác.

### 6.5. Persistence adapter triển khai outbound port

~~~java
@Repository
public class JpaOrderRepositoryAdapter implements OrderRepository {

    private final SpringDataOrderJpaRepository jpaRepository;
    private final OrderPersistenceMapper mapper;

    public JpaOrderRepositoryAdapter(
            SpringDataOrderJpaRepository jpaRepository,
            OrderPersistenceMapper mapper) {
        this.jpaRepository = jpaRepository;
        this.mapper = mapper;
    }

    @Override
    public void save(Order order) {
        OrderJpaEntity entity = mapper.toEntity(order);
        jpaRepository.save(entity);
    }
}
~~~

Adapter biết Spring Data và Entity JPA. Application service chỉ biết OrderRepository. Mapper persistence chuyển đổi giữa domain model và persistence entity.

### 6.6. Nối implementation khi khởi động

~~~java
@Configuration
public class OrderModuleConfiguration {

    @Bean
    CreateOrderUseCase createOrderUseCase(
            OrderRepository orders,
            OrderPricing pricing) {
        return new CreateOrderService(orders, pricing);
    }
}
~~~

Nếu dùng cấu hình tường minh, implementation JpaOrderRepositoryAdapter cần được đăng ký thành bean, chẳng hạn qua @Repository. Composition root là nơi biết cả abstraction lẫn implementation để nối chúng; lõi application không tự tìm implementation.

## 7. Abstraction giúp kiểm thử độc lập

Một use case phụ thuộc vào port có thể được kiểm thử với fake hoặc stub mà không cần database thật.

~~~java
class InMemoryOrderRepository implements OrderRepository {
    private final List<Order> saved = new ArrayList<>();

    @Override
    public void save(Order order) {
        saved.add(order);
    }

    List<Order> savedOrders() {
        return List.copyOf(saved);
    }
}
~~~

Unit test có thể tạo CreateOrderService với fake repository và pricing policy cố định. Test xác nhận use case tạo đúng đơn và yêu cầu lưu dữ liệu.

### 7.1. Fake, stub và mock có mục đích khác nhau

- **Stub:** trả về dữ liệu định sẵn để điều khiển tình huống kiểm thử.
- **Fake:** implementation đơn giản nhưng có hành vi đủ dùng trong test, ví dụ in-memory repository.
- **Mock:** ghi nhận tương tác để xác nhận lời gọi hoặc thứ tự cụ thể khi điều đó là một phần hợp đồng.

Không nên mock mọi class chỉ vì đã tạo interface. Nếu test chỉ kiểm tra implementation gọi đúng method của mock mà không xác nhận kết quả hoặc hành vi có ý nghĩa, test có thể bị gắn chặt với cấu trúc nội bộ.

### 7.2. Kiểm thử Controller với use case giả

Controller test có thể cung cấp implementation giả của CreateOrderUseCase, sau đó kiểm tra request binding, command mapping, lời gọi use case, response DTO, HTTP status và Location header. Không cần khởi động database để kiểm tra hợp đồng HTTP. Integration test riêng xác nhận wiring thật và adapter persistence hoạt động.

## 8. Abstraction tại ranh giới dịch vụ bên ngoài

Khi application cần gọi cổng thanh toán, dịch vụ email hoặc hệ thống vận chuyển, không nên để domain/application phụ thuộc trực tiếp vào SDK của nhà cung cấp.

~~~java
public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
}

@Component
public class AcmePaymentGatewayAdapter implements PaymentGateway {

    private final AcmePaymentClient client;

    public AcmePaymentGatewayAdapter(AcmePaymentClient client) {
        this.client = client;
    }

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        AcmePaymentResponse response = client.authorize(
            request.amount(),
            request.currency(),
            request.reference()
        );
        return mapResult(response);
    }
}
~~~

Application chỉ nhận PaymentResult theo hợp đồng của mình. Các mã lỗi, exception và kiểu dữ liệu riêng của nhà cung cấp được chuyển đổi trong adapter.

### 8.1. Adapter bảo vệ mô hình nội bộ

Nếu SDK dùng VendorTransaction, VendorStatus hoặc exception riêng, không nên để các kiểu này lan vào domain. Adapter chuyển chúng thành kiểu nội bộ như PaymentReference, PaymentStatus hoặc PaymentDeclined. Đây là một dạng anti-corruption layer: nó giữ cho mô hình nội bộ không bị định hình bởi mô hình của hệ thống ngoài.

### 8.2. Hợp đồng phải phản ánh lỗi và thời gian

Port gọi dịch vụ ngoài cần xác định timeout, lỗi có thể retry, idempotency key, kết quả từ chối nghiệp vụ, kết quả không xác định khi timeout xảy ra sau khi provider đã xử lý, và cách tra cứu/đối soát khi trạng thái chưa rõ.

Một interface chỉ có authorize() nhưng không có quy ước về timeout và kết quả bất định vẫn có thể là hợp đồng chưa đủ. Abstraction cần diễn đạt semantics mà consumer cần, không chỉ ẩn tên SDK.

## 9. Chọn mức trừu tượng phù hợp

| Tình huống | Cách làm thường phù hợp | Lý do |
|---|---|---|
| Helper thuần, ổn định trong cùng module | Dùng class cụ thể | Không có ranh giới thay đổi độc lập |
| Application gọi persistence | Repository port | Tách chính sách khỏi công nghệ lưu trữ |
| Controller gọi use case | Inbound port khi cần bảo vệ application boundary | Adapter không phụ thuộc implementation |
| Application gọi nhà cung cấp thanh toán | Gateway port | SDK và nhà cung cấp có thể thay đổi |
| Dữ liệu HTTP vào/ra | DTO cụ thể | DTO là hợp đồng dữ liệu, không cần interface |
| ViewModel của một màn hình | Class/record cụ thể | Là mô hình trình bày, không phải provider thay thế |
| Thuật toán nội bộ ổn định | Class cụ thể hoặc interface nhỏ nếu có nhiều chiến lược thực | Tránh indirection không cần thiết |

### 9.1. Đánh giá theo khả năng thay đổi

Hãy hỏi:

1. Thành phần nào sở hữu chính sách hoặc nhu cầu?
2. Thành phần được gọi có thể thay đổi độc lập không?
3. Có nhiều implementation thực tế hoặc một ranh giới hạ tầng không?
4. Thay đổi implementation có nên buộc consumer thay đổi không?
5. Hợp đồng có thể được mô tả bằng một số method nhỏ và ổn định không?
6. Có thể kiểm thử consumer mà không dựng provider thật không?

Nếu hai thành phần thay đổi cùng nhau và thuộc cùng một trách nhiệm, abstraction có thể chưa đem lại lợi ích. Nếu chúng có vòng đời hoặc lý do thay đổi khác nhau, một port rõ ràng có thể giảm coupling.

### 9.2. Không dự đoán mọi biến thể tương lai

Đừng tạo StorageProviderFactory, RepositoryStrategyResolver hoặc AbstractOrderPersistenceCoordinator chỉ vì có thể một ngày nào đó đổi database. Hãy tạo ranh giới dựa trên thay đổi đã có khả năng xảy ra hoặc ranh giới kiến trúc thực tế như database, message broker hay dịch vụ bên ngoài.

Thiết kế tốt cho phép thay đổi có kiểm soát mà không buộc phải xây sẵn mọi cơ chế mở rộng.

## 10. Thiết kế interface nhỏ và đúng ngữ nghĩa

### 10.1. Interface Segregation

Consumer không nên bị buộc phụ thuộc vào method mà nó không dùng. Một repository tổng quát với hàng chục method có thể khiến mọi use case phụ thuộc vào một hợp đồng quá rộng.

~~~java
public interface SaveOrder {
    void save(Order order);
}

public interface LoadOrder {
    Optional<Order> findById(OrderId id);
}
~~~

Không nhất thiết phải tách mọi method thành một interface. Nếu các thao tác cùng thuộc một hợp đồng repository hợp lý và được cùng consumer sử dụng, một interface nhỏ có thể dễ hiểu hơn.

### 10.2. Không để interface phản chiếu API của thư viện

Tránh tạo interface bao trùm toàn bộ EntityManager rồi truyền nó vào application. Consumer không cần mọi khả năng của EntityManager; nó cần một hành vi như lưu đơn hoặc tải đơn theo ID.

Tương tự, không tạo HttpClientPort với mọi method của thư viện HTTP nếu use case chỉ cần reserveInventory. Port nên dùng ngôn ngữ của nghiệp vụ hoặc nhu cầu ứng dụng.

### 10.3. Tránh kiểu tổng quát làm mất ngữ nghĩa

Interface GenericProcessor có thể dùng ở nhiều nơi nhưng không thể hiện rõ điều gì được xử lý. Nếu consumer cần khả năng ReserveInventory, một interface mang đúng ý nghĩa đó thường dễ hiểu và dễ kiểm thử hơn.

### 10.4. Hợp đồng phải có semantics rõ

Ngoài chữ ký method, cần định nghĩa method có thể trả về rỗng không, exception nào có thể phát sinh, thao tác có idempotent không, có bảo đảm transaction không, có thể chạy đồng thời không, kết quả có phản ánh dữ liệu đã commit không và timeout có thể để lại trạng thái không xác định không.

Một interface ngắn nhưng semantics mơ hồ vẫn tạo coupling vì consumer phải hiểu implementation để dùng an toàn.

## 11. Abstraction không được làm rò rỉ framework

Một ranh giới trừu tượng không còn hữu ích nếu interface vẫn chứa kiểu của framework mà nó muốn che giấu.

~~~java
public interface CreateOrderUseCase {
    ResponseEntity<OrderResponse> create(
        HttpServletRequest request
    );
}
~~~

Hợp đồng này buộc application biết Spring MVC và HTTP. Thay vào đó:

~~~java
public interface CreateOrderUseCase {
    OrderCreated handle(CreateOrderCommand command);
}
~~~

Controller chuyển HTTP request thành command và chuyển kết quả thành status/response. Application không biết request đến từ trình duyệt, REST client hay message listener.

Tương tự, outbound port không nên trả JpaRepository, EntityManager, RestClientResponseException hoặc kiểu response của nhà cung cấp. Adapter chịu trách nhiệm chuyển đổi chúng.

## 12. Dependency Injection và composition root

Sau khi tạo port và adapter, ứng dụng cần nối chúng lại. Điểm nối này thường được gọi là composition root. Trong Spring, composition root thường nằm ở cấu hình Configuration, component scanning và bean definitions. Đây là nơi được phép biết cả interface lẫn class triển khai.

~~~mermaid
flowchart TB
    Config[Composition Root / Spring Configuration]
    Port[OrderRepository]
    Adapter[JpaOrderRepositoryAdapter]
    UseCase[CreateOrderService]
    Controller[OrderController]

    Config -->|inject adapter| UseCase
    Config -->|inject use case| Controller
    Adapter -. implements .-> Port
    UseCase --> Port
~~~

### 12.1. Constructor injection

~~~java
public class CreateOrderService {
    private final OrderRepository orders;

    public CreateOrderService(OrderRepository orders) {
        this.orders = Objects.requireNonNull(orders);
    }
}
~~~

Constructor injection làm dependency rõ ràng, cho phép trường final, giúp unit test truyền fake và tránh tạo object ở trạng thái thiếu dependency.

### 12.2. Tránh Service Locator

~~~java
OrderRepository repository =
    ApplicationContextHolder.getBean(OrderRepository.class);
~~~

Cách này che giấu dependency và khiến test phải cấu hình global state. Hãy để composition root tạo object và truyền dependency vào constructor.

### 12.3. Không đưa container vào application

Application service không nên nhận ApplicationContext, BeanFactory hoặc service locator để tự tìm implementation theo tên. Nếu cần chọn chiến lược, hãy định nghĩa abstraction có ngữ nghĩa rõ, ví dụ PaymentMethodResolver, rồi inject nó.

## 13. Abstraction và transaction boundary

Một port có thể mô tả thao tác lưu dữ liệu, nhưng không nên khiến consumer hiểu sai phạm vi transaction. OrderRepository.save() không tự chứng minh rằng toàn bộ use case tạo đơn đã nguyên tử.

Transaction thường được đặt ở application service hoặc decorator phù hợp:

~~~java
@Service
public class TransactionalCreateOrderService
        implements CreateOrderUseCase {

    private final CreateOrderService delegate;

    public TransactionalCreateOrderService(CreateOrderService delegate) {
        this.delegate = delegate;
    }

    @Transactional
    @Override
    public OrderCreated handle(CreateOrderCommand command) {
        return delegate.handle(command);
    }
}
~~~

Đây là cách minh họa decorator; trong Spring, có thể đặt @Transactional trực tiếp trên implementation của use case nếu cấu trúc và proxy phù hợp. Không cần tạo decorator riêng nếu annotation trên application service đã đáp ứng yêu cầu.

Với nhiều service độc lập, một port HTTP không thể biến các database transaction thành một transaction ACID chung. Hợp đồng cần phản ánh timeout, retry, idempotency và trạng thái quy trình thay vì che giấu sự khác biệt phân tán.

## 14. Lỗi thiết kế khi tạo abstraction

- **Interface cho mọi class:** tạo interface và implementation song song dù chỉ có một class ổn định làm code dài, khó lần theo. Hãy hỏi abstraction bảo vệ điều gì.
- **Interface quá rộng:** consumer phụ thuộc vào nhiều khả năng hơn nó cần. Tách theo nhóm hành vi có ngữ nghĩa.
- **Interface quá nhỏ:** tách mỗi method thành interface riêng khiến constructor có quá nhiều dependency. Nhóm hành vi có cùng capability và lý do thay đổi.
- **Rò rỉ kiểu bên ngoài:** port trả exception hoặc DTO của provider khiến consumer vẫn phụ thuộc provider. Adapter phải chuyển đổi kiểu và semantics.
- **Mock mọi thứ:** test chỉ xác nhận cách implementation được viết, thay vì hành vi. Dùng fake hoặc integration test khi phù hợp.
- **Trừu tượng hóa quá sớm:** interface tổng quát được thiết kế từ giả định có thể không khớp nhu cầu thực. Bắt đầu từ consumer hiện tại.
- **Né thiết kế module:** interface public không có nghĩa module đã có ranh giới tốt nếu consumer vẫn phải import sâu vào nội bộ.

## 15. Quy trình refactor từ phụ thuộc trực tiếp sang abstraction

Giả sử Controller phụ thuộc trực tiếp vào implementation và implementation đó truy cập JPA.

1. **Xác định consumer và nhu cầu.** Controller cần khả năng tạo đơn; nó không cần biết service dùng repository nào.
2. **Xác định ranh giới thay đổi độc lập.** Application cần lưu dữ liệu; database adapter có thể thay đổi mà không nên làm đổi quy tắc tạo đơn.
3. **Thiết kế hợp đồng nhỏ.** Tạo CreateOrderUseCase cho Controller và OrderRepository cho application service.
4. **Chuyển kiểu dữ liệu qua ranh giới.** Tạo CreateOrderCommand và OrderCreated; không để HTTP request/response hoặc JPA entity đi vào application contract.
5. **Di chuyển chi tiết vào adapter.** Đưa Spring Data/JPA và mapping persistence vào infrastructure; mapping HTTP vào web adapter.
6. **Nối dependency ở composition root.** Cấu hình Spring inject implementation vào port và use case vào Controller.
7. **Kiểm thử từng ranh giới.** Unit test application bằng fake repository; Controller test bằng fake use case; integration test adapter persistence; architecture test bảo vệ hướng phụ thuộc.
8. **Xóa đường phụ thuộc cũ.** Sau khi caller dùng hợp đồng mới, xóa dependency trực tiếp không còn cần thiết.

## 16. Kiểm thử và bảo vệ ranh giới

| Kiểm thử | Xác nhận |
|---|---|
| Use case unit test với fake port | Chính sách và điều phối không phụ thuộc database |
| Controller test với fake use case | HTTP adapter không phụ thuộc implementation cụ thể |
| Adapter integration test | JPA/HTTP client thực hiện đúng hợp đồng |
| Contract test | Các implementation và consumer thống nhất semantics |
| Architecture test | Hướng phụ thuộc được giữ đúng |
| End-to-end test | Toàn bộ luồng MVC hoạt động khi wiring thật |

### 16.1. Architecture test với ArchUnit

~~~java
@AnalyzeClasses(packages = "com.example.shop")
class DependencyRulesTest {

    @ArchTest
    static final ArchRule application_must_not_depend_on_web =
        noClasses()
            .that().resideInAPackage("..application..")
            .should().dependOnClassesThat()
            .resideInAnyPackage(
                "..web..",
                "jakarta.servlet..",
                "org.springframework.web.."
            );
}
~~~

Quy tắc cần điều chỉnh theo package thực tế. Nếu application dùng annotation framework như @Transactional, cần quyết định rõ dự án chấp nhận dependency đó hay muốn đặt transaction ở adapter/decorator riêng. Không nên cấm toàn bộ Spring một cách máy móc nếu kiến trúc đã chọn cho phép một số annotation ở application layer.

### 16.2. Kiểm tra implementation thay thế được

Nếu có nhiều implementation của port, nên chạy contract test chung trên từng implementation. Repository adapter cần thống nhất cách xử lý ID không tồn tại, lưu entity và transaction semantics.

Nếu chỉ có một implementation, không cần tạo thêm implementation giả trong production chỉ để chứng minh interface có thể thay thế. Fake cho test là đủ nếu hợp đồng được kiểm thử đúng.

## 17. Checklist quyết định có cần abstraction hay không

- [ ] Consumer có phụ thuộc vào chi tiết triển khai mà nó không cần biết không?
- [ ] Provider có thể thay đổi độc lập với consumer không?
- [ ] Đây có phải ranh giới giữa tầng, module hoặc hệ thống ngoài không?
- [ ] Hợp đồng có thể mô tả bằng ngôn ngữ của consumer không?
- [ ] Interface có nhỏ và ổn định không?
- [ ] Kiểu framework/nhà cung cấp đã được giữ bên trong adapter chưa?
- [ ] Composition root có thể nối implementation mà không đưa container vào lõi không?
- [ ] Consumer có thể được kiểm thử bằng fake hoặc stub có ý nghĩa không?
- [ ] Abstraction có giảm coupling thực tế nhiều hơn chi phí thêm indirection không?
- [ ] Có quy tắc kiến trúc hoặc test bảo vệ hướng phụ thuộc quan trọng không?

Nếu chưa có lý do thay đổi độc lập hoặc hợp đồng rõ, giữ dependency trực tiếp có thể là lựa chọn đơn giản và đúng hơn.

## Kết luận

Thay phụ thuộc trực tiếp bằng abstraction có ích khi nó bảo vệ một ranh giới thực: Controller gọi use case mà không biết implementation, application dùng repository port mà không biết JPA, hoặc domain/application dùng gateway mà không phụ thuộc SDK của nhà cung cấp. Hãy đặt hợp đồng ở phía sở hữu nhu cầu, giữ interface nhỏ và diễn đạt đúng ngữ nghĩa, để adapter chuyển đổi chi tiết ở ranh giới, rồi nối dependency tại composition root. Không tạo interface cho mọi class; chỉ trừu tượng hóa khi nó giúp các phần thay đổi và kiểm thử độc lập hơn mà không làm kiến trúc khó đọc thêm.


# MVC tại ranh giới của một dịch vụ

MVC thường được giới thiệu như cách tổ chức một ứng dụng web: Model biểu diễn dữ liệu và quy tắc, View trình bày, Controller tiếp nhận tương tác. Khi nhìn ở cấp kiến trúc hệ thống, MVC còn có một vai trò quan trọng hơn: nó tạo ra một ranh giới giao tiếp giữa bên ngoài và một dịch vụ. Controller nhận request từ HTTP, chuyển dữ liệu bên ngoài thành lệnh mà ứng dụng hiểu, gọi ca sử dụng, rồi chuyển kết quả thành HTML hoặc response API.

Ranh giới này giúp dịch vụ giữ quyền kiểm soát đối với dữ liệu và quy tắc của mình. Client chỉ biết hợp đồng HTTP đã công bố; nó không cần biết Entity, Repository, cấu trúc package hoặc cách dịch vụ lưu dữ liệu. Bên trong, application service điều phối ca sử dụng, domain model bảo vệ bất biến, còn các adapter hạ tầng thực hiện truy cập database hoặc dịch vụ khác.

Cần phân biệt hai cách dùng từ “service”: một dịch vụ có thể là một ứng dụng được triển khai độc lập (ví dụ Order Service), còn application service là thành phần bên trong ứng dụng thực hiện một ca sử dụng. MVC nằm ở ranh giới giao tiếp của ứng dụng; Controller không thay thế application service và cũng không quyết định toàn bộ kiến trúc triển khai.

## 1. MVC ở cấp giao diện và ở cấp kiến trúc

Ở cấp giao diện, MVC giúp phân chia trách nhiệm trình bày:

- **Model:** dữ liệu và trạng thái mà màn hình cần.
- **View:** HTML hoặc giao diện được tạo từ dữ liệu đó.
- **Controller:** nhận thao tác, gọi xử lý và chọn View phù hợp.

Ở cấp kiến trúc dịch vụ, có thể nhìn MVC như một adapter đầu vào và một cơ chế trình bày đầu ra:

- Controller là điểm tiếp nhận request từ bên ngoài.
- Request DTO là hợp đồng dữ liệu đầu vào.
- Application service thực thi ca sử dụng.
- Response DTO hoặc ViewModel là hợp đồng dữ liệu đầu ra.
- View hoặc message converter tạo representation gửi về client.

Vì vậy, Controller thuộc lớp giao tiếp (delivery/web adapter). Nó không nên trở thành nơi chứa toàn bộ quy tắc nghiệp vụ hoặc truy cập trực tiếp mọi chi tiết hạ tầng.

### 1.1. MVC không đồng nghĩa với kiến trúc microservice

MVC là mẫu tổ chức phần giao tiếp và trình bày. Microservice là một lựa chọn kiến trúc triển khai, trong đó một dịch vụ có ranh giới trách nhiệm và vòng đời triển khai riêng.

Một ứng dụng monolith có thể dùng MVC. Một microservice cũng có thể dùng MVC để cung cấp HTTP API hoặc giao diện quản trị. Ngược lại, một service chạy nền chỉ nhận message có thể không có View hoặc Controller MVC theo nghĩa web.

Điều quan trọng là xác định ranh giới của service trước, rồi dùng MVC làm một adapter phù hợp để cung cấp giao diện HTTP cho ranh giới đó.

### 1.2. Các ranh giới cần phân biệt

| Ranh giới | Câu hỏi chính | Trách nhiệm điển hình |
|---|---|---|
| HTTP/web | Request nào được chấp nhận và phản hồi có dạng gì? | Routing, binding, authentication, HTTP status, serialization |
| Application | Ca sử dụng nào được thực thi? | Điều phối, transaction, gọi domain và port |
| Domain | Quy tắc nào phải luôn đúng? | Entity, value object, invariant, domain service |
| Infrastructure | Dữ liệu và dịch vụ ngoài được truy cập ra sao? | Repository adapter, database, message broker, HTTP client |
| Deployment/service | Thành phần nào có thể triển khai và vận hành độc lập? | API công khai, dữ liệu sở hữu, cấu hình, scale, observability |

Không nên gộp tất cả các ranh giới này vào một lớp Controller hoặc một package mang tên service. Mỗi ranh giới giải quyết một loại thay đổi khác nhau.

## 2. Luồng request qua ranh giới của một dịch vụ

Giả sử một ứng dụng Order Service cung cấp endpoint tạo đơn hàng. Client gửi HTTP request; ứng dụng cần xác thực người gọi, kiểm tra dữ liệu đầu vào, thực thi quy tắc tạo đơn, lưu dữ liệu và trả kết quả.

~~~mermaid
sequenceDiagram
    actor Client
    participant HTTP as MVC / HTTP Adapter
    participant App as Application Service
    participant Domain as Domain Model
    participant Port as Repository Port
    participant DB as Database Adapter

    Client->>HTTP: POST /api/orders
    HTTP->>HTTP: Xác thực, bind và validate request
    HTTP->>App: CreateOrderCommand
    App->>Domain: Tạo và kiểm tra Order
    Domain-->>App: Order hợp lệ
    App->>Port: Lưu đơn hàng
    Port->>DB: INSERT / transaction
    DB-->>Port: Kết quả lưu
    Port-->>App: Order đã lưu
    App-->>HTTP: OrderResult
    HTTP->>HTTP: Map response và HTTP status
    HTTP-->>Client: 201 Created + JSON
~~~

Luồng trên thể hiện một cách tổ chức phổ biến. Một số ứng dụng có thể đặt bước kiểm tra quyền trong application service, security filter hoặc policy; điều quan trọng là request không được phép bỏ qua kiểm soát truy cập. Transaction thường do application boundary điều phối để bao trùm những thay đổi cần tính nguyên tử.

### 2.1. Controller là adapter, không phải nơi thực thi toàn bộ use case

Controller nên làm những việc sát với giao thức:

- Khai báo route và HTTP method.
- Bind path variable, query parameter, header và request body.
- Kích hoạt validation ở cấp đầu vào.
- Lấy danh tính đã xác thực từ security context.
- Chuyển request DTO thành command/query.
- Gọi application service.
- Chuyển kết quả thành View, response DTO, redirect và status code.

Controller không nên:

- Tự viết truy vấn SQL hoặc thao tác EntityManager.
- Chứa quy trình nghiệp vụ nhiều bước.
- Tự quyết định các bất biến của domain.
- Gọi trực tiếp nhiều hệ thống ngoài rồi tự điều phối transaction.
- Trả Entity nội bộ như một hợp đồng API.
- Tự tạo thông điệp lỗi kỹ thuật chứa stack trace cho client.

Khi Controller mỏng, cùng một ca sử dụng có thể được gọi từ một HTTP endpoint khác, một message handler hoặc một tác vụ nền mà không phải sao chép nghiệp vụ.

### 2.2. Application service sở hữu ca sử dụng

Application service điều phối một hành động mà hệ thống cung cấp, ví dụ tạo đơn, hủy đơn hoặc xem chi tiết. Nó có thể kiểm tra quyền ở cấp use case, tải domain object qua repository port, gọi hành vi domain và lưu thay đổi.

Application service không nhất thiết phải là một lớp Spring có annotation @Service. Annotation chỉ là cơ chế wiring. Điều quan trọng là hợp đồng và trách nhiệm của ca sử dụng độc lập với HTTP.

Ví dụ:

~~~java
public interface CreateOrderUseCase {
    OrderResult handle(CreateOrderCommand command);
}
~~~

Command là dữ liệu đầu vào của ca sử dụng, không phải request object gắn với HTTP:

~~~java
public record CreateOrderCommand(
    UserId actorId,
    CustomerId customerId,
    List<OrderLineCommand> lines
) {}

public record OrderLineCommand(
    ProductId productId,
    int quantity
) {}
~~~

Nếu sau này có một message handler cần tạo đơn, nó có thể chuyển message thành cùng command và gọi use case. Domain không cần biết request ban đầu đến từ trình duyệt hay message broker.

## 3. Thiết kế hợp đồng ở ranh giới HTTP

HTTP API là hợp đồng giữa service và client. Hợp đồng cần mô tả rõ dữ liệu đầu vào, dữ liệu đầu ra, lỗi, xác thực, phân trang và quy tắc tương thích.

### 3.1. Request DTO là hợp đồng bên ngoài

Ví dụ request tạo đơn:

~~~java
public record CreateOrderRequest(
    @NotNull UUID customerId,
    @NotEmpty List<@Valid OrderLineRequest> lines
) {}

public record OrderLineRequest(
    @NotNull UUID productId,
    @Min(1) int quantity
) {}
~~~

Request DTO phản ánh dữ liệu client được phép gửi. Nó không nên là Entity JPA hoặc domain object vì client không được phép quyết định mọi trường nội bộ.

Ví dụ, client không nên gửi:

- Trạng thái đơn hàng cuối cùng.
- Người tạo được tin cậy.
- Tổng tiền do client tự tính.
- Thời điểm duyệt.
- Cờ bỏ qua kiểm tra tồn kho.
- Trường version nội bộ nếu API không công bố cơ chế đó.

Máy chủ cần tự xác định những dữ liệu có thẩm quyền như người dùng hiện tại, giá được áp dụng, trạng thái ban đầu và quyền thao tác.

### 3.2. Response DTO không làm lộ mô hình nội bộ

Ví dụ:

~~~java
public record OrderResponse(
    UUID id,
    String orderNumber,
    String status,
    BigDecimal total,
    String currency
) {}
~~~

Response chỉ công bố các trường cần cho client. Khi Entity đổi cấu trúc, hợp đồng bên ngoài vẫn có thể giữ nguyên bằng mapper.

Không nên trả trực tiếp Entity từ Controller. Điều đó có thể làm lộ trường nội bộ, kéo theo quan hệ lazy, tạo vòng lặp serialization hoặc khiến client phụ thuộc vào cấu trúc persistence.

### 3.3. Mapper đặt ở ranh giới

Mapper chuyển request DTO thành command và kết quả application thành response DTO:

~~~java
@Component
public class OrderHttpMapper {

    public CreateOrderCommand toCommand(
            CreateOrderRequest request,
            UserId actorId) {

        List<OrderLineCommand> lines = request.lines().stream()
            .map(line -> new OrderLineCommand(
                new ProductId(line.productId()),
                line.quantity()
            ))
            .toList();

        return new CreateOrderCommand(
            actorId,
            new CustomerId(request.customerId()),
            lines
        );
    }

    public OrderResponse toResponse(OrderResult result) {
        return new OrderResponse(
            result.orderId().value(),
            result.orderNumber(),
            result.status().name(),
            result.total().amount(),
            result.total().currency().getCurrencyCode()
        );
    }
}
~~~

Mapper không nên chứa quy tắc như “khách hàng có được mua sản phẩm này không” hoặc “đơn hàng có được chuyển sang trạng thái đã xác nhận không”. Đó là trách nhiệm của application/domain. Mapper chỉ chuyển đổi cấu trúc và kiểu dữ liệu giữa các ranh giới.

## 4. Ví dụ Controller tại ranh giới của Order Service

Controller nhận request HTTP, dùng principal đã xác thực để xác định người thực hiện, chuyển request thành command và trả response.

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

        UserId actorId = currentUser.requireUserId();
        CreateOrderCommand command =
            mapper.toCommand(request, actorId);

        OrderResult result = createOrder.handle(command);
        OrderResponse response = mapper.toResponse(result);

        URI location = URI.create("/api/orders/" + response.id());

        return ResponseEntity.created(location).body(response);
    }
}
~~~

Ví dụ tập trung vào luồng thành công. Trong ứng dụng thật, use case có thể trả Result hoặc ném exception theo quy ước xử lý lỗi; ControllerAdvice hoặc một mapper lỗi ở HTTP boundary sẽ chuyển kết quả đó thành status code và error body.

Điểm quan trọng là Controller không truyền Authentication object vào domain. Nó lấy danh tính đã được xác thực rồi chuyển thành UserId hoặc kiểu định danh của ứng dụng. Domain không cần phụ thuộc Spring Security.

### 4.1. Đường đi của dữ liệu

| Dữ liệu | Nơi tạo/chuyển đổi | Mục đích |
|---|---|---|
| HTTP body | Client | Dữ liệu bên ngoài gửi đến |
| CreateOrderRequest | Web adapter | Bind và validate payload |
| CreateOrderCommand | Mapper | Hợp đồng ca sử dụng |
| Order / value objects | Domain | Trạng thái và quy tắc nghiệp vụ |
| OrderResult | Application | Kết quả của use case |
| OrderResponse | Web adapter | Hợp đồng HTTP gửi ra |

Mỗi kiểu có một lý do tồn tại. Không cần tạo thêm kiểu trung gian nếu nó không bảo vệ một ranh giới hoặc diễn đạt một ý nghĩa khác.

## 5. Một dịch vụ có thể có nhiều adapter đầu vào

Một service có thể nhận yêu cầu từ nhiều loại client:

- Trình duyệt qua MVC HTML Controller.
- Ứng dụng mobile qua REST Controller.
- Service khác qua HTTP API.
- Message broker qua message listener.
- Tác vụ quản trị qua command line hoặc job scheduler.

Các adapter này có giao thức và hợp đồng khác nhau nhưng có thể dùng chung application use case nếu ý nghĩa nghiệp vụ giống nhau.

~~~mermaid
flowchart LR
    Browser[Trình duyệt] --> HTML[HTML Controller]
    Mobile[Ứng dụng mobile] --> REST[REST Controller]
    Partner[Service đối tác] --> API[API Adapter]
    Broker[Message Broker] --> Listener[Message Listener]

    HTML --> UseCase[Application Use Cases]
    REST --> UseCase
    API --> UseCase
    Listener --> UseCase

    UseCase --> Domain[Domain Model]
    UseCase --> Ports[Outbound Ports]
    Ports --> DB[Database Adapter]
    Ports --> External[External Service Adapter]
~~~

### 5.1. HTML Controller và REST Controller

HTML Controller có thể trả tên View và đưa ViewModel vào Model. REST Controller thường trả DTO để framework serialize thành JSON.

~~~java
@Controller
@RequestMapping("/orders")
public class OrderPageController {

    private final GetOrderDetailUseCase getOrderDetail;
    private final OrderViewMapper viewMapper;

    @GetMapping("/{id}")
    public String detail(
            @PathVariable UUID id,
            Model model) {

        OrderDetail result = getOrderDetail.handle(new OrderId(id));
        model.addAttribute("order", viewMapper.toView(result));

        return "orders/detail";
    }
}
~~~

REST Controller có thể gọi cùng use case nhưng trả representation khác:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderQueryController {

    private final GetOrderDetailUseCase getOrderDetail;
    private final OrderApiMapper apiMapper;

    @GetMapping("/{id}")
    public OrderDetailResponse detail(@PathVariable UUID id) {
        OrderDetail result = getOrderDetail.handle(new OrderId(id));
        return apiMapper.toResponse(result);
    }
}
~~~

Hai adapter có thể dùng chung application service vì cùng yêu cầu dữ liệu chi tiết. Tuy nhiên, ViewModel HTML và API response không bắt buộc giống nhau. Trang HTML có thể cần nhãn đã dịch và cờ hiển thị nút; API có thể cần mã trạng thái ổn định và kiểu dữ liệu có thể tích hợp.

### 5.2. Không nhân bản use case trong từng Controller

Nếu HTML Controller và REST Controller đều tự kiểm tra quyền, cập nhật trạng thái và ghi repository, quy tắc nghiệp vụ sẽ bị nhân đôi. Khi thay đổi chính sách, các adapter có thể hành xử khác nhau.

Đưa quy tắc vào application/domain, để adapter chỉ chuyển đổi giao thức. Nếu hai luồng thực sự có ngữ nghĩa nghiệp vụ khác nhau, hãy biểu diễn thành hai use case riêng thay vì ép chúng vào một phương thức chung quá nhiều tham số.

## 6. Một service không có nghĩa mọi thứ phải nằm trong một Controller

Một ứng dụng có thể có nhiều Controller theo tài nguyên hoặc nhóm use case:

- OrderQueryController cho đọc dữ liệu.
- OrderCommandController cho thao tác thay đổi.
- OrderPageController cho HTML.
- AdminOrderController cho chức năng quản trị.

Chia Controller theo trách nhiệm giúp route và hợp đồng rõ ràng. Tuy nhiên, không cần tạo một Controller cho mỗi phương thức Service. Cách phân chia nên phản ánh nhóm endpoint và client, không phản chiếu máy móc cấu trúc class bên trong.

Controller có thể được chia theo bounded context hoặc module nghiệp vụ. Nếu một service có nhiều module nội bộ, hãy giữ các adapter gần module mà chúng phục vụ và kiểm soát phụ thuộc giữa các module.

## 7. MVC và kiến trúc Ports and Adapters

Trong kiến trúc Hexagonal (Ports and Adapters), ứng dụng có lõi bên trong và các adapter bên ngoài:

- Inbound adapter chuyển yêu cầu bên ngoài thành lệnh/query của ứng dụng.
- Application port mô tả ca sử dụng mà adapter có thể gọi.
- Outbound port mô tả khả năng mà ứng dụng cần từ bên ngoài.
- Outbound adapter triển khai port bằng database, message broker hoặc HTTP client.

MVC web Controller là một inbound adapter. View hoặc response mapper là phần trình bày của adapter đó. Repository interface có thể là outbound port; implementation JPA là outbound adapter.

~~~mermaid
flowchart TB
    subgraph Outside[Thế giới bên ngoài]
        Browser[Browser / API Client]
        Database[(Database)]
        Payment[Payment Provider]
    end

    subgraph Service[Order Service]
        subgraph Adapters[Adapters]
            MVC[MVC Controller + View/API Mapper]
            Jpa[JPA Repository Adapter]
            Http[Payment HTTP Adapter]
        end

        subgraph Core[Application Core]
            UseCases[Application Use Cases]
            Domain[Domain Model]
            InPort[Inbound Use Case Port]
            OutPort[Repository / Payment Ports]
        end

        MVC --> InPort
        InPort --> UseCases
        UseCases --> Domain
        UseCases --> OutPort
        Jpa --> OutPort
        Http --> OutPort
    end

    Browser --> MVC
    Jpa --> Database
    Http --> Payment
~~~

Sơ đồ chỉ ra hướng phụ thuộc quan trọng: lõi ứng dụng định nghĩa những gì nó cần; adapter bên ngoài triển khai các hợp đồng đó. Controller có thể phụ thuộc vào application port, nhưng domain không nên phụ thuộc vào Spring MVC, Servlet API hoặc template engine.

### 7.1. MVC không phải là toàn bộ kiến trúc

MVC trả lời cách xử lý request và trình bày kết quả. Nó không tự quyết định:

- Service có sở hữu database riêng hay không.
- Module có được triển khai độc lập hay không.
- Giao tiếp giữa các service dùng HTTP hay message.
- Transaction phân tán được điều phối thế nào.
- Domain được chia thành bounded context ra sao.
- Hệ thống quan sát và mở rộng quy mô như thế nào.

Những câu hỏi này thuộc phạm vi kiến trúc ứng dụng và hệ thống. MVC cần được đặt đúng vị trí trong bức tranh lớn hơn.

## 8. Ranh giới service và quyền sở hữu dữ liệu

Nếu một ứng dụng được chia thành nhiều service, mỗi service cần có trách nhiệm và quyền sở hữu dữ liệu rõ ràng. Controller của service chỉ nên cung cấp những thao tác được công bố qua hợp đồng.

Ví dụ, Order Service có thể sở hữu:

- Đơn hàng và dòng đơn hàng.
- Trạng thái đơn hàng.
- Quy tắc xác nhận hoặc hủy đơn.
- Tổng tiền theo chính sách giá đã áp dụng.
- Lịch sử thay đổi trạng thái.

Inventory Service có thể sở hữu số lượng tồn kho và quy tắc giữ hàng. Order Service không nên truy vấn trực tiếp bảng nội bộ của Inventory Service chỉ vì hai service cùng dùng một loại database.

### 8.1. Gọi service khác qua hợp đồng

Application service có thể phụ thuộc vào một port:

~~~java
public interface InventoryReservationPort {
    ReservationResult reserve(ReservationRequest request);
}
~~~

Một adapter triển khai port bằng HTTP client hoặc message. Domain/application không cần biết endpoint URL, header xác thực hoặc thư viện HTTP cụ thể.

Khi gọi service khác, cần thiết kế rõ:

- Timeout và giới hạn retry.
- Xử lý lỗi không khả dụng.
- Idempotency cho thao tác có thể gửi lại.
- Correlation ID để truy vết.
- Version của hợp đồng.
- Cách xử lý kết quả một phần hoặc bù trừ.

Không nên giữ database transaction của Order Service mở trong khi chờ một HTTP request kéo dài nếu không cần thiết. Transaction cục bộ không tự bao trùm transaction của service khác. Quy trình nhiều service có thể cần saga hoặc trạng thái trung gian.

### 8.2. Không để HTTP contract rò rỉ mô hình nội bộ

Không công bố tên bảng, Entity class hoặc cấu trúc repository như hợp đồng API. Những chi tiết này có thể thay đổi theo cách lưu trữ mà không nên buộc client thay đổi theo.

Một API tốt công bố ngữ nghĩa nghiệp vụ: tạo đơn, xem đơn, hủy đơn, lấy danh sách. Nó không yêu cầu client biết hệ thống lưu Order trong bao nhiêu bảng hoặc dùng ORM nào.

## 9. Validation, xác thực và phân quyền ở ranh giới

Ranh giới HTTP là nơi dữ liệu không đáng tin cậy đi vào hệ thống. MVC cần phối hợp validation và bảo mật theo nhiều lớp.

### 9.1. Validation ở adapter

Controller có thể dùng Bean Validation để kiểm tra cấu trúc và giới hạn đầu vào:

- Trường bắt buộc.
- Định dạng UUID/email.
- Số lượng dương.
- Danh sách không rỗng.
- Kích thước payload và độ dài chuỗi.

Validation ở adapter giúp từ chối request sai cấu trúc sớm. Nó không thay thế quy tắc domain. Ví dụ quantity lớn hơn 0 chưa chứng minh sản phẩm còn hàng hoặc người mua được phép đặt số lượng đó.

### 9.2. Xác thực và phân quyền

Authentication xác định ai đang gọi. Authorization xác định người đó có được phép thực hiện hành động trên tài nguyên cụ thể không.

Có thể cấu hình quyền route bằng Spring Security, nhưng quyền ở cấp đối tượng và quy tắc nghiệp vụ thường cần được kiểm tra trong application service hoặc policy. Không tin user ID, tenant ID hoặc role do client gửi trong body nếu chúng phải đến từ danh tính đã xác thực.

### 9.3. CSRF, CORS và cookie

Nếu MVC dùng session cookie, các request thay đổi trạng thái cần CSRF protection. CORS kiểm soát việc trình duyệt cho phép JavaScript từ origin khác đọc response; nó không phải cơ chế xác thực hoặc phân quyền.

Với API dùng bearer token, cần bảo vệ token, giới hạn scope và kiểm tra issuer/audience/expiry theo cơ chế xác thực. Cách bảo vệ phụ thuộc phương thức xác thực, không chỉ phụ thuộc Controller trả JSON hay HTML.

## 10. Lỗi ở ranh giới dịch vụ

Application/domain có thể biểu diễn lỗi bằng Result hoặc exception. HTTP adapter chịu trách nhiệm chuyển lỗi đó thành status và cấu trúc response phù hợp.

Ví dụ quy ước:

| Loại kết quả | HTTP status thường dùng | Ý nghĩa |
|---|---:|---|
| Tạo tài nguyên thành công | 201 | Có tài nguyên mới, có thể kèm Location |
| Request không hợp lệ | 400/422 | Payload hoặc dữ liệu không đạt hợp đồng |
| Chưa xác thực | 401 | Cần xác thực |
| Không đủ quyền | 403 | Đã xác thực nhưng bị từ chối |
| Không tìm thấy | 404 | Tài nguyên không tồn tại hoặc bị che theo chính sách |
| Xung đột trạng thái | 409 | Trạng thái hiện tại không cho phép thao tác |
| Precondition không đạt | 412 | ETag/version condition không khớp |
| Lỗi tạm thời | 503 | Dịch vụ hiện không sẵn sàng |
| Lỗi không dự kiến | 500 | Lỗi máy chủ |

Dùng một error code ổn định trong response để client có thể xử lý mà không phụ thuộc thông điệp đã dịch. Không trả stack trace, SQL hoặc chi tiết nội bộ qua HTTP.

### 10.1. Xử lý lỗi tập trung

Trong Spring MVC, ControllerAdvice có thể ánh xạ các exception đã biết thành response API hoặc trang HTML. Nên giữ một quy tắc nhất quán cho toàn service và cho phép module cung cấp xử lý chuyên biệt khi cần.

Không catch mọi Exception trong Controller rồi trả 400. Lỗi database, timeout và bug không phải lỗi đầu vào của client. Cần giữ log/cause ở phía server và chỉ trả thông tin an toàn.

## 11. Hợp đồng, versioning và khả năng tương thích

Service có thể có nhiều client với chu kỳ phát hành khác nhau. Thay đổi response có thể làm hỏng client cũ ngay cả khi code service vẫn chạy.

Những nguyên tắc quan trọng:

- Giữ ngữ nghĩa của trường đã công bố.
- Thêm trường tùy chọn theo cách client cũ có thể bỏ qua.
- Không đổi đơn vị, timezone hoặc ý nghĩa enum mà không có kế hoạch.
- Quy định rõ null, field vắng mặt và giá trị mặc định.
- Version hóa khi thay đổi phá vỡ tương thích.
- Công bố mã lỗi, pagination và quy tắc retry.
- Không dùng class nội bộ làm schema công khai.

Có thể quản lý schema bằng OpenAPI hoặc một định dạng hợp đồng tương đương. Hợp đồng nên được review cùng code vì nó ảnh hưởng trực tiếp đến người tiêu thụ API.

### 11.1. Consumer contract testing

Khi một service được nhiều client sử dụng, contract test có thể xác nhận provider vẫn đáp ứng những kỳ vọng đã công bố của consumer. Kiểm thử này hữu ích cho tên field, status code, header và cấu trúc lỗi.

Contract test không thay thế integration test cho database hoặc kiểm thử nghiệp vụ. Nó kiểm tra sự tương thích giữa bên cung cấp và bên tiêu thụ ở ranh giới giao tiếp.

## 12. Transaction và tính nhất quán ở cấp service

Application service thường là nơi điều phối transaction cục bộ cho một ca sử dụng. Controller không nên mở transaction kéo dài quanh toàn bộ request nếu không có lý do rõ ràng.

Ví dụ, tạo đơn có thể cần lưu đơn và các dòng đơn trong cùng transaction. Nếu phát sinh lỗi trước commit, dữ liệu phải rollback theo chính sách. Nhưng nếu cần gọi Inventory Service hoặc Payment Service, transaction database cục bộ không thể tự rollback thay đổi đã được service kia commit.

Với quy trình nhiều bước:

1. Xác định trạng thái của quy trình.
2. Ghi nhận command hoặc sự kiện cần xử lý.
3. Gọi service khác với timeout và idempotency phù hợp.
4. Lưu kết quả từng bước.
5. Khi thất bại, retry có kiểm soát hoặc chạy hành động bù trừ.
6. Cung cấp trạng thái nhất quán cho client.

Đây có thể là một quy trình saga. Không nên giả định HTTP request đồng bộ cùng một transaction ACID xuyên qua nhiều service.

## 13. Kiểm thử MVC tại ranh giới service

Cần kiểm thử cả adapter HTTP và application use case. Mỗi lớp kiểm thử xác nhận một loại hợp đồng.

| Tầng kiểm thử | Nội dung | Công cụ/cách làm |
|---|---|---|
| Controller unit/standalone | Route, binding, View/status, mapper | MockMvc standalone, Mockito |
| Application service | Quy tắc điều phối, quyền, transaction intent | JUnit, fake ports |
| Domain | Invariant và chuyển trạng thái | Unit test |
| MVC integration | Filter, security, resolver, serialization | SpringBootTest + MockMvc |
| Persistence integration | Repository, transaction, locking | Testcontainers hoặc database test |
| API contract | Schema, status, headers, compatibility | OpenAPI/contract tests |
| End-to-end | Hành trình client qua service | Browser/API E2E |

### 13.1. Kiểm thử Controller không cần database

Mock application port để kiểm tra Controller chuyển đúng request thành command và phản hồi đúng status. Test này nên tập trung vào adapter, không cần khởi động toàn bộ hạ tầng.

### 13.2. Kiểm thử application service không cần HTTP

Gọi trực tiếp use case với fake repository hoặc fake outbound port. Điều này xác nhận nghiệp vụ không phụ thuộc vào Servlet request, HTTP status hoặc template engine.

### 13.3. Kiểm thử tích hợp ở ranh giới thật

Dùng MockMvc với ApplicationContext để kiểm tra filter, authentication, exception mapping và serialization. Nếu service cung cấp HTML, cần kiểm tra ViewResolver và template engine. Nếu service cung cấp JSON, kiểm tra schema và Content-Type.

### 13.4. Kiểm thử lỗi khi service khác không khả dụng

Với outbound adapter, cần kiểm tra timeout, retry, circuit breaker nếu có, và mapping lỗi về kết quả application. Không để exception của thư viện HTTP rò trực tiếp qua API công khai.

## 14. Quan sát và vận hành tại ranh giới

Ranh giới dịch vụ là vị trí tốt để gắn thông tin quan sát xuyên suốt request:

- Request ID hoặc correlation ID.
- HTTP method, route template và status.
- Thời gian xử lý tổng.
- Kết quả use case ở mức mã ổn định.
- Trace context khi gọi service khác.
- Thông tin xác thực ở mức định danh phù hợp, không ghi credential.

Không ghi session ID, access token, password hoặc toàn bộ request body nhạy cảm vào log. Cần tránh log dữ liệu cá nhân vượt mức cần thiết.

Metric nên dùng route template thay vì URL có ID cụ thể để tránh cardinality quá cao. Trace giúp theo dõi request qua nhiều service, nhưng không nên chứa dữ liệu nhạy cảm trong span attribute.

## 15. Những dấu hiệu ranh giới MVC và service bị trộn lẫn

Một số dấu hiệu thường gặp:

- Controller chứa hàng trăm dòng quy tắc nghiệp vụ.
- Controller gọi Repository trực tiếp cho mọi thao tác.
- Entity JPA được trả trực tiếp cho client.
- Domain import Spring MVC hoặc Servlet API.
- Application service nhận HttpServletRequest hoặc ResponseEntity.
- Client cần biết tên bảng hoặc trạng thái persistence nội bộ.
- Nhiều Controller lặp lại cùng quy tắc quyền và chuyển trạng thái.
- Service A truy cập database nội bộ của Service B.
- Lỗi kỹ thuật bị chuyển thành 400 hoặc thông báo chung không có mã.
- Một thay đổi nội bộ buộc tất cả client phải thay đổi cùng lúc.

Khi thấy những dấu hiệu này, hãy xác định phần nào thuộc giao thức, phần nào thuộc ca sử dụng, phần nào thuộc domain và phần nào thuộc hạ tầng. Di chuyển trách nhiệm về đúng ranh giới và giữ hợp đồng giữa chúng nhỏ, rõ ràng.

## 16. Quy trình thiết kế một MVC adapter cho service

1. Xác định service sở hữu năng lực nghiệp vụ nào và dữ liệu nào.
2. Xác định client và giao thức mà service cần hỗ trợ.
3. Định nghĩa request/response DTO và error contract.
4. Tạo Controller làm inbound adapter, chỉ xử lý HTTP và mapping.
5. Định nghĩa application use case độc lập với framework web.
6. Đặt quy tắc và invariant trong domain model hoặc domain service.
7. Định nghĩa outbound port cho database và dịch vụ ngoài.
8. Triển khai adapter hạ tầng theo port.
9. Đặt authentication, authorization và validation đúng ranh giới.
10. Xác định transaction và hành vi khi service phụ thuộc không khả dụng.
11. Kiểm thử từng lớp và kiểm thử hợp đồng HTTP.
12. Theo dõi request bằng log, metric và trace an toàn.

Không cần áp dụng đầy đủ mọi tầng cho một CRUD nhỏ. Nhưng khi service có nhiều client, nhiều quy tắc hoặc nhiều tích hợp, ranh giới rõ ràng sẽ giúp thay đổi từng phần mà không làm lan rộng phụ thuộc.

## Kết luận

MVC tại ranh giới của một dịch vụ là cách tổ chức adapter HTTP để chuyển request bên ngoài thành command/query của ứng dụng và chuyển kết quả thành HTML hoặc response API. Controller chịu trách nhiệm giao thức và trình bày; application service điều phối ca sử dụng; domain model bảo vệ quy tắc; outbound adapter kết nối database và hệ thống khác. MVC không đồng nghĩa với microservice và không thay thế kiến trúc tổng thể. Khi hợp đồng HTTP ổn định, dữ liệu nội bộ không bị lộ và phụ thuộc hướng vào lõi ứng dụng, một service có thể phục vụ nhiều loại client mà vẫn giữ được quyền sở hữu nghiệp vụ và khả năng thay đổi độc lập.


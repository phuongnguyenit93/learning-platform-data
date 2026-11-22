# Tách mô-đun giao diện khỏi mô-đun nghiệp vụ

Trong ứng dụng MVC, giao diện tiếp nhận thao tác và trình bày kết quả; nghiệp vụ quyết định dữ liệu nào hợp lệ và hành động nào được phép. Khi hai trách nhiệm này bị trộn trong cùng một mô-đun, thay đổi giao diện có thể làm ảnh hưởng quy tắc nghiệp vụ, còn một nghiệp vụ mới dễ bị sao chép vào nhiều Controller.

Tách mô-đun giao diện khỏi mô-đun nghiệp vụ tạo ra ranh giới rõ ràng: phần giao diện biết cách tiếp nhận và trình bày dữ liệu; phần nghiệp vụ biết cách thực hiện một mục tiêu của ứng dụng. Hai phần trao đổi qua các hợp đồng có chủ đích, chẳng hạn command, query và DTO. Nhờ vậy, cùng một nghiệp vụ có thể được gọi từ trang HTML, API, tác vụ nền hoặc một kênh giao tiếp khác.

Bài học này trình bày cách xác định ranh giới mô-đun, tổ chức phụ thuộc, thiết kế hợp đồng giữa các phần và triển khai bằng Java trong ứng dụng MVC web.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích lý do cần tách mô-đun giao diện khỏi mô-đun nghiệp vụ.
- Phân biệt trách nhiệm của presentation, application, domain và infrastructure.
- Thiết kế chiều phụ thuộc để quy tắc nghiệp vụ không phụ thuộc framework giao diện.
- Định nghĩa hợp đồng đầu vào và đầu ra giữa Controller và ca sử dụng.
- Tổ chức package hoặc module Java theo trách nhiệm và theo tính năng.
- Nhận biết các dấu hiệu của phụ thuộc ngược và sự trộn lẫn trách nhiệm.
- Kiểm thử riêng giao diện, ca sử dụng và quy tắc nghiệp vụ.

## 2. Vì sao cần tách giao diện khỏi nghiệp vụ?

Hãy xem xét một hệ thống quản lý đơn hàng. Khách hàng có thể tạo đơn qua trang web, ứng dụng di động hoặc API dành cho đối tác. Dù điểm vào khác nhau, các quy tắc vẫn cần được áp dụng thống nhất:

- Đơn hàng phải có ít nhất một dòng trước khi xác nhận.
- Số lượng của mỗi dòng phải là số dương.
- Giá được lấy từ nguồn dữ liệu đáng tin cậy.
- Người dùng chỉ được thao tác trên đơn hàng mà họ có quyền truy cập.
- Đơn đã xác nhận không được sửa theo cách làm sai lệch lịch sử giao dịch.

Nếu các quy tắc này được viết trực tiếp trong Controller của trang web, API mới có thể phải sao chép chúng. Một thay đổi trong cách trình bày hoặc framework cũng có thể buộc phải sửa logic đặt hàng dù nghiệp vụ không thay đổi.

Tách mô-đun giúp giải quyết các vấn đề đó:

1. **Giảm lan truyền thay đổi.** Sửa template hoặc route không làm thay đổi quy tắc đặt hàng.
2. **Tái sử dụng nghiệp vụ.** Nhiều điểm vào có thể gọi cùng một ca sử dụng.
3. **Kiểm thử tập trung.** Quy tắc nghiệp vụ có thể được kiểm thử mà không dựng web server hoặc giao diện.
4. **Kiểm soát hợp đồng.** Chỉ dữ liệu cần thiết được phép đi qua ranh giới.
5. **Quản lý phụ thuộc.** Framework web và ORM nằm ở phần ngoài, không chi phối mô hình nghiệp vụ.
6. **Dễ phân chia công việc.** Nhóm giao diện và nhóm nghiệp vụ có thể phát triển theo hợp đồng đã thống nhất.

Tách mô-đun không có nghĩa là mọi lớp phải nằm trong một dự án riêng. Một mô-đun có thể là package trong cùng ứng dụng, Gradle subproject, Maven module hoặc một dịch vụ độc lập. Mức tách cần phù hợp với quy mô, vòng đời phát hành và nhu cầu triển khai.

## 3. Phân biệt các trách nhiệm trong ứng dụng MVC

Một ứng dụng MVC có thể được tổ chức thành nhiều lớp hoặc mô-đun. Cách chia phổ biến gồm presentation, application, domain và infrastructure.

| Phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Presentation / Web | Tiếp nhận request, binding, validation giao tiếp, trình bày và tạo response | Controller, request DTO, View Model, template |
| Application | Điều phối mục tiêu người dùng và các bước nghiệp vụ ở cấp ứng dụng | CreateOrderUseCase, command, query |
| Domain | Biểu diễn khái niệm, trạng thái và quy tắc cốt lõi | Order, OrderLine, Money, OrderPolicy |
| Infrastructure | Kết nối hệ thống bên ngoài và triển khai các cổng truy cập | JPA repository adapter, email gateway, HTTP client |

### 3.1. Mô-đun giao diện (Presentation)

Mô-đun giao diện chịu trách nhiệm giao tiếp với người dùng hoặc client. Trong ứng dụng web server-rendered, nó thường chứa:

- Controller và cấu hình route.
- Request DTO hoặc form model.
- Binding và validation cấu trúc đầu vào.
- Mapper từ request sang command hoặc query.
- View Model và response DTO.
- Template HTML, tài nguyên CSS và JavaScript.
- Cách chuyển lỗi ứng dụng thành phản hồi HTTP hoặc thông báo trên View.

Presentation cần biết HTTP, HTML, JSON và framework web vì đó là trách nhiệm của nó. Tuy nhiên, nó không nên tự quyết định các quy tắc cốt lõi như giá bán, điều kiện xác nhận đơn hoặc cách chuyển trạng thái nghiệp vụ.

Trong Spring MVC, tham số org.springframework.ui.Model của Controller là nơi đặt thuộc tính để template sử dụng. Nó là đối tượng phục vụ View, không phải Domain Model chứa quy tắc nghiệp vụ. Cần phân biệt hai ý nghĩa này khi đặt tên package và kiểu dữ liệu.

### 3.2. Mô-đun ứng dụng (Application)

Mô-đun application biểu diễn các mục tiêu mà hệ thống hỗ trợ, thường gọi là use case hoặc application service. Ví dụ:

- Tạo đơn hàng.
- Hủy đơn hàng.
- Đăng ký khách hàng.
- Tính báo cáo doanh thu.
- Tra cứu chi tiết đơn hàng.

Ca sử dụng điều phối các bước cần thiết: nhận command, kiểm tra quyền hoặc chính sách, lấy dữ liệu cần thiết, gọi Domain Model, lưu thay đổi và trả kết quả.

Application không cần biết yêu cầu đến từ biểu mẫu HTML hay JSON. Nó nhận dữ liệu đã được chuẩn hóa qua một hợp đồng ổn định.

### 3.3. Mô-đun nghiệp vụ (Domain)

Domain chứa các khái niệm và quy tắc có ý nghĩa độc lập với giao diện. Ví dụ:

- Entity như Order và Customer.
- Value object như Money và Address.
- Quy tắc chuyển trạng thái.
- Domain service hoặc policy khi quy tắc không thuộc riêng một entity.
- Domain event khi cần biểu đạt một sự kiện nghiệp vụ đã xảy ra.

Domain không nên import Controller, Servlet API, Thymeleaf, Jackson hoặc annotation ORM chỉ để biểu diễn nghiệp vụ. Khi Domain bị phụ thuộc vào các chi tiết này, thay đổi framework có thể lan vào phần cần ổn định nhất.

### 3.4. Mô-đun hạ tầng (Infrastructure)

Infrastructure triển khai những kết nối cụ thể mà application hoặc domain cần. Ví dụ:

- Đọc và ghi dữ liệu bằng JPA hoặc JDBC.
- Gửi email qua nhà cung cấp bên ngoài.
- Gọi dịch vụ thanh toán.
- Đọc tệp hoặc lưu đối tượng vào storage.
- Nhận thông điệp từ message broker.

Application có thể định nghĩa interface mô tả điều nó cần, còn Infrastructure cung cấp implementation. Nhờ đó, ca sử dụng không phụ thuộc trực tiếp vào một thư viện hoặc nhà cung cấp cụ thể.

## 4. Chiều phụ thuộc giữa các mô-đun

Điểm cốt lõi của việc tách mô-đun là kiểm soát chiều phụ thuộc. Mô-đun giao diện có thể phụ thuộc vào hợp đồng application để gọi nghiệp vụ; application có thể phụ thuộc vào Domain; infrastructure triển khai các interface mà application hoặc domain yêu cầu.

Một sơ đồ khái quát:

~~~mermaid
flowchart TB
    Web["Presentation / Web"]
    App["Application / Use Cases"]
    Domain["Domain Model"]
    Infra["Infrastructure Adapters"]
    DB[("Database")]
    External["Dịch vụ bên ngoài"]

    Web -->|"Command / Query / Result"| App
    App -->|"Quy tắc và mô hình"| Domain
    Infra -->|"Triển khai port"| App
    Infra --> DB
    Infra --> External
~~~

Trong cách tổ chức này:

- Web gọi application qua command hoặc query.
- Application điều phối domain và các port mà nó cần.
- Infrastructure phụ thuộc vào các interface ở phía trong để triển khai adapter.
- Domain không phụ thuộc vào web, template, database driver hoặc framework hạ tầng.

Mũi tên trong sơ đồ biểu diễn phụ thuộc mã nguồn hoặc lời gọi theo hợp đồng, không nhất thiết là hướng dữ liệu chạy trong mọi trường hợp. Ví dụ, application gọi một interface repository; implementation nằm trong infrastructure được framework hoặc composition root kết nối vào lúc chạy.

### 4.1. Dependency Inversion

Dependency Inversion Principle (DIP) khuyến khích phần chính sách cấp cao không phụ thuộc trực tiếp vào chi tiết cấp thấp. Cả hai nên phụ thuộc vào abstraction phù hợp.

Ví dụ, ca sử dụng đặt hàng cần lưu đơn. Nếu nó trực tiếp tạo JPA EntityManager hoặc gọi lớp repository cụ thể của framework, logic ứng dụng đã bị gắn với hạ tầng. Thay vào đó, application định nghĩa một port:

Các đoạn Java trong bài là trích đoạn minh họa; import và những kiểu phụ trợ không liên quan trực tiếp đến ranh giới đang giải thích có thể được lược bỏ.

~~~java
public interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(OrderId id);
}
~~~

Infrastructure triển khai port đó bằng JPA:

~~~java
@Repository
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderRepository springDataRepository;
    private final OrderPersistenceMapper mapper;

    public JpaOrderRepository(
            SpringDataOrderRepository springDataRepository,
            OrderPersistenceMapper mapper) {
        this.springDataRepository = springDataRepository;
        this.mapper = mapper;
    }

    @Override
    public void save(Order order) {
        springDataRepository.save(mapper.toEntity(order));
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return springDataRepository.findById(id.value())
            .map(mapper::toDomain);
    }
}
~~~

Tên interface và kiểu domain ở đây là ví dụ minh họa. Điều cần giữ là interface được đặt ở phía sở hữu nhu cầu, còn adapter cụ thể nằm ở phía hạ tầng.

### 4.2. Composition root kết nối các mô-đun

Các thành phần cần được kết nối khi ứng dụng khởi động. Composition root là nơi cấu hình object graph: implementation repository nào được đưa vào use case, service nào được cung cấp cho Controller, và các adapter nào được sử dụng.

Trong ứng dụng Spring, dependency injection container thường thực hiện việc kết nối thông qua constructor injection và cấu hình bean. Controller không cần tự khởi tạo repository hoặc tạo một JPA adapter.

~~~java
public class CreateOrderService implements CreateOrderUseCase {
    private final OrderRepository orders;
    private final ProductCatalog products;
    private final OrderIdGenerator ids;

    public CreateOrderService(
            OrderRepository orders,
            ProductCatalog products,
            OrderIdGenerator ids) {
        this.orders = orders;
        this.products = products;
        this.ids = ids;
    }

    // Triển khai ca sử dụng.
}
~~~

Constructor injection làm rõ phụ thuộc bắt buộc và giúp thay thế implementation trong kiểm thử. Lớp application không cần annotation Spring; mô-đun khởi động có thể đăng ký nó bằng cấu hình bean. Nếu đặt @Service trực tiếp ở đây, mô-đun application sẽ phải phụ thuộc Spring Context.

Ví dụ cấu hình ở composition root:

~~~java
@Configuration
public class ApplicationConfiguration {
    @Bean
    CreateOrderUseCase createOrderUseCase(
            OrderRepository orders,
            ProductCatalog products,
            OrderIdGenerator ids) {
        return new CreateOrderService(orders, products, ids);
    }
}
~~~

## 5. Thiết kế hợp đồng giữa giao diện và nghiệp vụ

Mô-đun giao diện và mô-đun nghiệp vụ cần trao đổi dữ liệu, nhưng không nên chia sẻ mọi đối tượng nội bộ. Hợp đồng rõ ràng giúp hai bên thay đổi độc lập hơn.

### 5.1. Request DTO và Form Model thuộc ranh giới giao tiếp

Request DTO mô tả dữ liệu client được phép gửi. Form Model có thể bổ sung các quy tắc binding và validation phục vụ biểu mẫu. Ví dụ:

~~~java
public record CreateOrderRequest(
    String productCode,
    Integer quantity
) {}
~~~

Mô-đun web có thể kiểm tra dữ liệu cấu trúc bằng Bean Validation:

~~~java
public record CreateOrderForm(
    @NotBlank String productCode,
    @NotNull @Min(1) @Max(100) Integer quantity
) {}
~~~

Các kiểu này phản ánh hợp đồng giao tiếp. Nếu API đổi tên trường hoặc form có thêm thông tin trợ giúp, không nhất thiết phải đổi Domain Model.

Không nên nhận trực tiếp Domain Entity từ request. Client có thể gửi thêm trường không được phép như ownerId, status, unitPrice hoặc approvedBy. Một DTO chuyên biệt giới hạn dữ liệu có thể được binding và giảm nguy cơ mass assignment.

### 5.2. Command và Query thuộc hợp đồng application

Sau khi kiểm tra cấu trúc và chuẩn hóa dữ liệu, Controller chuyển request thành command hoặc query mà application hiểu.

~~~java
public record CreateOrderCommand(
    CustomerId customerId,
    ProductCode productCode,
    int quantity
) {}
~~~

Command biểu đạt ý định thay đổi trạng thái, chẳng hạn tạo hoặc hủy đơn. Query biểu đạt nhu cầu đọc dữ liệu mà không yêu cầu thay đổi trạng thái.

Hợp đồng application không nên chứa HttpServletRequest, HttpSession, ResponseEntity, Model của Spring MVC hoặc kiểu giao diện. Nếu command cần danh tính người gọi, hãy truyền một định danh hoặc ngữ cảnh đã được xác thực theo hợp đồng application phù hợp.

### 5.3. Kết quả trả về không nhất thiết là Domain Entity

Ca sử dụng có thể trả về một kết quả gọn:

~~~java
public record CreateOrderResult(
    OrderId orderId,
    OrderStatus status
) {}
~~~

Controller ánh xạ kết quả này thành response DTO hoặc View Model. Không cần trả toàn bộ Domain Entity ra ngoài chỉ để hiển thị một vài trường.

Với trang chi tiết, application có thể cung cấp một query result riêng, chứa các trường mà màn hình cần. Với API, response DTO có thể được version hóa theo hợp đồng công khai. Hai loại kết quả có thể giống nhau một phần nhưng không bắt buộc phải dùng chung.

### 5.4. Lỗi qua ranh giới

Domain và application nên biểu đạt lỗi theo ngôn ngữ nghiệp vụ hoặc kiểu kết quả có cấu trúc. Ví dụ:

- Sản phẩm không tồn tại.
- Số lượng không hợp lệ.
- Đơn hàng không thể hủy ở trạng thái hiện tại.
- Người dùng không có quyền thực hiện hành động.

Controller hoặc lớp trình bày ánh xạ lỗi sang phản hồi thích hợp: hiển thị lỗi cạnh trường, thông báo chung, trang 404, HTTP 409 hoặc mã lỗi API theo hợp đồng.

Không để Domain Model quyết định mã HTTP hoặc tạo HTML. Cùng một lỗi nghiệp vụ có thể được trình bày khác nhau trên trang web, API và tác vụ nền.

## 6. Ví dụ: tách luồng tạo đơn hàng

Giả sử khách hàng gửi biểu mẫu tạo đơn. Luồng có thể được tổ chức như sau:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Web as Web Controller
    participant App as CreateOrderUseCase
    participant Domain as Domain Model
    participant Port as OrderRepository port
    participant Adapter as JPA Adapter
    participant DB as Database

    User->>Web: POST /orders
    Web->>Web: Binding và validation request
    Web->>App: CreateOrderCommand
    App->>Domain: Tạo và xác nhận Order
    Domain-->>App: Order hợp lệ
    App->>Port: save(order)
    Port->>Adapter: Gọi implementation
    Adapter->>DB: Persist entity
    DB-->>Adapter: Hoàn tất
    Adapter-->>App: Kết quả lưu
    App-->>Web: CreateOrderResult
    Web-->>User: Redirect / response
~~~

### 6.1. Domain Model bảo vệ quy tắc

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines;
    private OrderStatus status;

    public Order(
            OrderId id,
            CustomerId customerId,
            List<OrderLine> lines) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException(
                "Order must contain at least one line"
            );
        }

        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.lines = new ArrayList<>(lines);
        this.status = OrderStatus.DRAFT;
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
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

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }

    public OrderStatus status() {
        return status;
    }
}
~~~

Domain Model không cần biết đơn hàng được tạo từ trang HTML hay API. Nó chỉ bảo vệ các quy tắc của đơn hàng.

### 6.2. Application điều phối ca sử dụng

~~~java
public interface CreateOrderUseCase {
    CreateOrderResult handle(CreateOrderCommand command);
}
~~~

Implementation có thể lấy giá sản phẩm từ một port, tạo Domain Model và lưu đơn:

~~~java
public class CreateOrderService implements CreateOrderUseCase {
    private final ProductCatalog products;
    private final OrderRepository orders;
    private final OrderIdGenerator ids;

    public CreateOrderService(
            ProductCatalog products,
            OrderRepository orders,
            OrderIdGenerator ids) {
        this.products = products;
        this.orders = orders;
        this.ids = ids;
    }

    @Override
    public CreateOrderResult handle(CreateOrderCommand command) {
        Product product = products.findByCode(command.productCode())
            .orElseThrow(ProductNotFoundException::new);

        Order order = new Order(
            ids.next(),
            command.customerId(),
            List.of(new OrderLine(
                product.code(),
                command.quantity(),
                product.price()
            ))
        );

        order.confirm();
        orders.save(order);

        return new CreateOrderResult(order.id(), order.status());
    }
}
~~~

Các port mà use case cần có thể được khai báo trong mô-đun application:

~~~java
public interface ProductCatalog {
    Optional<Product> findByCode(ProductCode code);
}

public interface OrderIdGenerator {
    OrderId next();
}
~~~

Trong ví dụ, các kiểu CustomerId, ProductCode, Product, OrderLine, OrderIdGenerator và exception được lược bỏ phần khai báo. Các đoạn code là trích đoạn nên import và một số kiểu phụ trợ cũng được lược bỏ. Kiểu dữ liệu và chính sách thực tế cần phù hợp với miền nghiệp vụ của ứng dụng. Lớp CreateOrderService không mang annotation Spring; composition root đăng ký implementation này như đã minh họa ở trên.

Application không biết giá sản phẩm được lấy từ JPA, REST API hay một dịch vụ khác. Nó chỉ phụ thuộc vào port ProductCatalog.

### 6.3. Controller chỉ chuyển đổi và điều phối

~~~java
@Controller
@RequestMapping("/orders")
public class OrderController {
    private final CreateOrderUseCase createOrder;

    public OrderController(CreateOrderUseCase createOrder) {
        this.createOrder = createOrder;
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("form") CreateOrderForm form,
            BindingResult errors,
            @AuthenticationPrincipal AppPrincipal principal) {

        if (errors.hasErrors()) {
            return "orders/new";
        }

        CreateOrderCommand command = new CreateOrderCommand(
            new CustomerId(principal.customerId()),
            new ProductCode(form.productCode()),
            form.quantity()
        );

        CreateOrderResult result = createOrder.handle(command);
        return "redirect:/orders/" + result.orderId().value();
    }
}
~~~

Controller không tự tính tổng tiền hoặc cập nhật trạng thái đơn. Nó nhận dữ liệu, kiểm tra hợp đồng đầu vào, lấy danh tính từ ngữ cảnh xác thực, tạo command và gọi use case.

Trong ứng dụng hoàn chỉnh, Controller cần nạp lại dữ liệu phụ trợ cho form khi có lỗi validation, xử lý lỗi nghiệp vụ có thể trình bày và ánh xạ sang View hoặc response phù hợp.

### 6.4. Infrastructure triển khai các port

Ví dụ JPA adapter:

~~~java
@Repository
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderRepository dataRepository;
    private final OrderPersistenceMapper mapper;

    public JpaOrderRepository(
            SpringDataOrderRepository dataRepository,
            OrderPersistenceMapper mapper) {
        this.dataRepository = dataRepository;
        this.mapper = mapper;
    }

    @Override
    public void save(Order order) {
        dataRepository.save(mapper.toEntity(order));
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return dataRepository.findById(id.value())
            .map(mapper::toDomain);
    }
}
~~~

Adapter chịu trách nhiệm chuyển đổi giữa Domain Model và cấu trúc lưu trữ. Domain không cần biết tên bảng, annotation JPA hoặc kiểu entity của Spring Data.

## 7. Tổ chức package và module Java

Có nhiều cách tổ chức source code. Điều quan trọng là cấu trúc thư mục thể hiện được ranh giới và giúp người đọc tìm đúng trách nhiệm.

### 7.1. Tổ chức theo tầng trong một ứng dụng

Một ứng dụng nhỏ có thể dùng một module Gradle hoặc Maven và phân chia package:

~~~text
src/main/java/com/example/shop/
├── web/
│   ├── order/
│   │   ├── OrderController.java
│   │   ├── CreateOrderForm.java
│   │   └── OrderViewMapper.java
│   └── customer/
├── application/
│   ├── order/
│   │   ├── CreateOrderUseCase.java
│   │   ├── CreateOrderService.java
│   │   ├── CreateOrderCommand.java
│   │   └── CreateOrderResult.java
│   └── port/
│       ├── OrderRepository.java
│       ├── ProductCatalog.java
│       └── OrderIdGenerator.java
├── domain/
│   ├── order/
│   │   ├── Order.java
│   │   ├── OrderLine.java
│   │   └── OrderStatus.java
│   └── shared/
│       └── Money.java
└── infrastructure/
    ├── persistence/
    │   ├── JpaOrderRepository.java
    │   └── OrderEntity.java
    └── catalog/
        └── HttpProductCatalog.java
~~~

Cấu trúc này dễ bắt đầu và phù hợp với ứng dụng vừa hoặc nhỏ. Tuy nhiên, package chỉ tạo ranh giới về tổ chức. Java không tự ngăn một lớp trong package web import trực tiếp lớp JPA nếu không có quy tắc hoặc công cụ kiểm tra phụ thuộc.

### 7.2. Tổ chức theo tính năng và giữ ranh giới bên trong

Khi ứng dụng có nhiều nghiệp vụ, có thể gom các thành phần liên quan theo feature:

~~~text
com/example/shop/
├── order/
│   ├── web/
│   │   ├── OrderController.java
│   │   ├── CreateOrderForm.java
│   │   └── OrderViewMapper.java
│   ├── application/
│   │   ├── CreateOrderUseCase.java
│   │   ├── CreateOrderService.java
│   │   └── CreateOrderCommand.java
│   ├── domain/
│   │   ├── Order.java
│   │   ├── OrderLine.java
│   │   └── OrderRepository.java
│   └── infrastructure/
│       ├── JpaOrderRepository.java
│       └── OrderEntity.java
├── customer/
│   ├── web/
│   ├── application/
│   ├── domain/
│   └── infrastructure/
└── shared/
    └── ...
~~~

Package-by-feature giúp mã của một nghiệp vụ nằm gần nhau và giảm việc phải di chuyển qua nhiều thư mục tầng. Bên trong mỗi feature vẫn cần giữ chiều phụ thuộc hợp lý.

Không nên tạo một package shared khổng lồ rồi chuyển mọi lớp khó phân loại vào đó. Chỉ chia sẻ kiểu hoặc dịch vụ khi chúng có ý nghĩa thực sự chung; nếu không, hãy để chúng thuộc feature sở hữu khái niệm đó.

### 7.3. Tách thành nhiều module build

Khi cần ranh giới mạnh hơn, có thể dùng nhiều module Gradle hoặc Maven:

~~~text
shop/
├── shop-domain/
├── shop-application/
├── shop-web/
├── shop-infrastructure/
└── shop-boot/
~~~

Một sơ đồ phụ thuộc build điển hình:

~~~mermaid
flowchart TD
    Boot["shop-boot / Composition root"]
    Web["shop-web"]
    App["shop-application"]
    Domain["shop-domain"]
    Infra["shop-infrastructure"]

    Boot --> Web
    Boot --> Infra
    Web --> App
    App --> Domain
    Infra --> App
    Infra --> Domain
~~~

Trong cấu trúc này, module khởi động ứng dụng kết nối các thành phần. Module web gọi application; application dùng domain; infrastructure triển khai port mà application hoặc domain công bố.

Mô-đun build giúp compiler kiểm tra một phần ranh giới phụ thuộc. Nếu shop-domain không khai báo dependency đến Spring Web, lớp domain sẽ không thể vô tình import Controller hoặc annotation web từ dependency đó.

Tách module cũng làm tăng cấu hình build, quản lý version và thời gian biên dịch. Chỉ nên tạo nhiều module khi lợi ích về ranh giới, tái sử dụng hoặc phát hành độc lập đủ rõ.

## 8. Package-by-layer và package-by-feature

Hai cách tổ chức thường gặp có ưu và nhược điểm khác nhau.

| Tiêu chí | Package-by-layer | Package-by-feature |
|---|---|---|
| Cách nhóm | Gom Controller, service, repository theo tầng | Gom các thành phần theo nghiệp vụ |
| Dễ thấy kiến trúc tổng thể | Thường dễ nhìn các tầng | Cần xem cấu trúc bên trong từng feature |
| Tìm toàn bộ mã một tính năng | Có thể phải đi qua nhiều package | Thường tập trung hơn |
| Phù hợp | Ứng dụng nhỏ, nhóm quen tổ chức theo tầng | Ứng dụng có nhiều nghiệp vụ và nhóm phát triển theo feature |
| Rủi ro | Package service hoặc controller quá lớn | Lặp lại cấu trúc hoặc chia feature thiếu ranh giới |
| Kiểm soát phụ thuộc | Cần quy ước hoặc công cụ bổ sung | Vẫn cần quy ước hoặc công cụ bổ sung |

Có thể kết hợp hai cách: nhóm theo feature ở mức cao, rồi chia web, application, domain và infrastructure bên trong từng feature. Cách chọn nên dựa vào cách nhóm làm việc và độ phức tạp của nghiệp vụ.

## 9. Những điều không nên đưa qua ranh giới

Tách mô-đun chỉ có ích khi hợp đồng giữa các phần được kiểm soát.

### 9.1. Không đưa kiểu framework web vào application

Ví dụ không phù hợp:

~~~java
public interface CreateOrderUseCase {
    ResponseEntity<?> create(HttpServletRequest request);
}
~~~

Application giờ phụ thuộc vào Spring MVC và Servlet API. Nó khó được gọi từ tác vụ nền hoặc một adapter khác. Hãy để Controller chuyển request thành command và ánh xạ kết quả thành response.

### 9.2. Không trả Domain Entity trực tiếp cho View hoặc API

Trả entity trực tiếp có thể làm lộ trường nội bộ, khiến cấu trúc API phụ thuộc vào mô hình lưu trữ và tạo vòng tham chiếu khi serialization. Dùng View Model hoặc Response DTO để công bố đúng dữ liệu cần thiết.

### 9.3. Không để template thực hiện nghiệp vụ

Template nên tập trung trình bày. Không tính giá, kiểm tra quyền hoặc quyết định trạng thái đơn trong biểu thức template. Những quy tắc đó cần được thực thi ở application hoặc domain; View chỉ nhận dữ liệu đã chuẩn bị.

### 9.4. Không để application phụ thuộc vào implementation repository

Nếu use case gọi trực tiếp JpaOrderRepository, phần nghiệp vụ bị gắn với JPA. Định nghĩa port phù hợp ở phía application hoặc domain, sau đó đặt implementation trong infrastructure.

### 9.5. Không dùng DTO làm Domain Model chỉ vì các trường giống nhau

DTO mô tả hợp đồng giao tiếp, còn Domain Model bảo vệ quy tắc và trạng thái. Một thay đổi trong API có thể không nên làm thay đổi entity nghiệp vụ. Việc trùng tên hoặc trùng trường không có nghĩa là hai lớp có cùng trách nhiệm.

### 9.6. Không tạo interface cho mọi lớp

Tách mô-đun không yêu cầu mọi service đều có interface. Interface có giá trị khi nó thể hiện một ranh giới, một port, một hợp đồng được nhiều implementation sử dụng hoặc một điểm thay thế có ý nghĩa. Nếu interface chỉ lặp lại một implementation và không tạo ra ranh giới hữu ích, nó có thể làm mã phức tạp hơn.

## 10. Kiểm thử theo ranh giới mô-đun

Khi mô-đun giao diện và nghiệp vụ được tách rõ, mỗi phần có thể được kiểm thử với phạm vi phù hợp.

### 10.1. Kiểm thử Domain

Domain test tập trung vào hành vi và bất biến:

- Không tạo được đơn rỗng nếu nghiệp vụ cấm.
- Không xác nhận đơn ở trạng thái không hợp lệ.
- Tổng tiền được tính từ các dòng hợp lệ.
- Không cho phép phép toán tiền tệ không tương thích.

Các test này không cần Spring context, HTTP server hoặc cơ sở dữ liệu.

### 10.2. Kiểm thử Application

Dùng fake hoặc mock cho các port như OrderRepository và ProductCatalog. Kiểm tra:

- Use case gọi đúng port.
- Dữ liệu được lấy từ nguồn tin cậy.
- Quy tắc được thực hiện theo đúng trình tự.
- Không lưu đơn khi bước nghiệp vụ thất bại.
- Kết quả trả về đúng hợp đồng.

Không nên mock Domain Model đến mức test chỉ xác nhận các lời gọi đã lập trình sẵn. Domain nên được kiểm thử bằng hành vi thực của nó.

### 10.3. Kiểm thử Presentation

Controller test tập trung vào giao tiếp:

- Route và HTTP method được ánh xạ đúng.
- Request DTO được binding và validation đúng.
- Request hợp lệ tạo command phù hợp.
- Lỗi được chuyển thành View hoặc response đúng.
- Response không làm lộ trường nội bộ.
- Danh tính và quyền truy cập được xử lý theo chính sách.

Với Spring MVC, MockMvc có thể kiểm tra request mapping và response mà không cần chạy server HTTP thật.

### 10.4. Kiểm thử Infrastructure và tích hợp

Adapter test kiểm tra việc ánh xạ và giao tiếp thực tế với cơ sở dữ liệu hoặc dịch vụ ngoài. Integration test xác nhận dependency injection kết nối đúng implementation và giao dịch hoạt động theo kỳ vọng.

Không cần mọi unit test đều khởi tạo toàn bộ ứng dụng. Tách ranh giới giúp chọn đúng mức kiểm thử, giảm thời gian chạy và làm lỗi dễ định vị hơn.

### 10.5. Kiểm tra quy tắc phụ thuộc

Khi dự án lớn, có thể dùng ArchUnit hoặc module system của Java để kiểm tra quy tắc kiến trúc. Ví dụ, package domain không được phụ thuộc vào package web hoặc infrastructure; application không được import Spring Web.

Một quy tắc kiến trúc có thể được kiểm tra tự động:

~~~java
@AnalyzeClasses(packages = "com.example.shop")
class ArchitectureTest {
    @ArchTest
    static final ArchRule domainMustNotDependOnWeb =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage("..web..", "org.springframework.web..");
}
~~~

Đây là ví dụ theo cú pháp ArchUnit; dự án cần khai báo dependency test tương ứng. Quy tắc thực tế nên phản ánh cấu trúc package và các ngoại lệ đã được thống nhất.

## 11. Lộ trình tách mô-đun từ ứng dụng hiện có

Không nhất thiết phải viết lại toàn bộ ứng dụng để có ranh giới tốt hơn. Có thể tách dần theo một feature hoặc một luồng nghiệp vụ.

1. **Chọn một luồng có phạm vi rõ.** Ví dụ tạo đơn hàng hoặc cập nhật hồ sơ.
2. **Đánh dấu quy tắc nghiệp vụ hiện nằm trong Controller.** Xác định phần nào là binding, phần nào là điều phối, phần nào là quy tắc domain.
3. **Tạo form model hoặc request DTO.** Chỉ nhận những trường mà client được phép gửi.
4. **Tạo command và use case.** Đưa trình tự nghiệp vụ ra khỏi Controller.
5. **Di chuyển quy tắc vào Domain Model hoặc policy.** Bảo đảm mọi điểm gọi đều đi qua cùng quy tắc.
6. **Định nghĩa port cho phụ thuộc bên ngoài.** Ví dụ repository hoặc product catalog.
7. **Chuyển implementation sang infrastructure.** Controller và application không tạo trực tiếp adapter.
8. **Giữ Controller mỏng.** Controller binding, kiểm tra cấu trúc, gọi use case và ánh xạ kết quả.
9. **Viết test theo ranh giới.** Domain, application, controller và adapter có test phù hợp.
10. **Thêm kiểm tra kiến trúc.** Ngăn phụ thuộc ngược quay trở lại trong các thay đổi sau.

Khi tách dần, có thể giữ nguyên URL, response và hành vi bên ngoài để tránh làm gián đoạn client. Sau mỗi bước, chạy các test phù hợp với phần đã thay đổi.

## 12. Khi nào nên tách thành module riêng?

Không phải ứng dụng nào cũng cần bốn module build riêng biệt. Có thể bắt đầu bằng package rõ ràng trong một ứng dụng và tách mạnh hơn khi xuất hiện các nhu cầu cụ thể.

Nên cân nhắc module riêng khi:

- Nhiều nhóm cùng phát triển và cần ranh giới compile-time.
- Domain cần được tái sử dụng ở nhiều adapter hoặc ứng dụng.
- Một phần có vòng đời build hoặc phát hành riêng.
- Framework web hoặc persistence thay đổi độc lập với nghiệp vụ.
- Số lượng phụ thuộc tăng và package convention không đủ ngăn vi phạm.
- Muốn áp dụng quy tắc kiến trúc bằng module dependency thay vì chỉ dựa vào review.

Giữ chung module có thể phù hợp khi ứng dụng còn nhỏ, nhóm ít người, nghiệp vụ đơn giản và chưa có nhu cầu tái sử dụng. Ranh giới package, hợp đồng và chiều phụ thuộc vẫn cần được duy trì ngay cả khi chưa tách build module.

Tách thành microservice là quyết định lớn hơn nhiều so với tách module trong một codebase. Microservice thêm giao tiếp qua mạng, triển khai độc lập, xử lý lỗi phân tán, quan sát hệ thống và quản lý dữ liệu riêng. Không nên chuyển một package thành dịch vụ riêng chỉ để đạt mục tiêu phân tách giao diện và nghiệp vụ.

## 13. Checklist thiết kế

Trước khi hoàn thành một feature MVC, hãy kiểm tra:

- Controller có tập trung vào HTTP, binding và điều phối không?
- Request DTO có chỉ chứa trường client được phép gửi không?
- Application có thể được gọi mà không cần khởi tạo web framework không?
- Domain có phụ thuộc vào template, HTTP hoặc ORM không?
- Các port có nằm ở phía sở hữu nhu cầu sử dụng chúng không?
- Infrastructure có triển khai port qua adapter rõ ràng không?
- View Model và Response DTO có công bố đúng dữ liệu cần thiết không?
- Lỗi nghiệp vụ có được ánh xạ ở ranh giới giao tiếp không?
- Có test độc lập cho domain và application không?
- Có cách ngăn phụ thuộc ngược quay trở lại không?

## 14. Kết luận

Tách mô-đun giao diện khỏi mô-đun nghiệp vụ giúp ứng dụng MVC giữ được ranh giới trách nhiệm khi giao diện, giao thức hoặc framework thay đổi. Presentation tiếp nhận và trình bày dữ liệu; application điều phối ca sử dụng; domain bảo vệ quy tắc nghiệp vụ; infrastructure kết nối các hệ thống bên ngoài qua adapter.

Các mô-đun nên trao đổi qua command, query, result và port có ý nghĩa rõ ràng. Khi chiều phụ thuộc hướng về chính sách nghiệp vụ, cùng một ca sử dụng có thể được gọi từ nhiều điểm vào và kiểm thử độc lập với giao diện. Mức độ tách package hay build module nên theo nhu cầu thực tế, nhưng hợp đồng và chiều phụ thuộc cần được giữ nhất quán từ đầu.


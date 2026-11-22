# Quan hệ giữa MVC và Clean Architecture

MVC và Clean Architecture thường xuất hiện cùng nhau trong ứng dụng web, nhưng chúng giải quyết những vấn đề khác nhau. MVC tổ chức cách ứng dụng tiếp nhận tương tác, điều phối request và trình bày kết quả. Clean Architecture tổ chức các ranh giới của hệ thống, đặt quy tắc phụ thuộc hướng vào chính sách nghiệp vụ và giữ các quy tắc cốt lõi độc lập với framework, cơ sở dữ liệu hoặc giao diện.

Vì vậy, MVC không phải là kiến trúc cạnh tranh với Clean Architecture. Một ứng dụng có thể dùng Spring MVC làm cơ chế giao tiếp HTTP ở vòng ngoài, đồng thời tổ chức use case, domain model và các cổng truy cập dữ liệu theo Clean Architecture. Controller, View và các lớp ánh xạ dữ liệu trở thành adapter giao tiếp với thế giới bên ngoài; chúng không quyết định cấu trúc của toàn bộ hệ thống.

Điểm dễ nhầm là từ “Model” trong MVC có thể được dùng cho nhiều thứ: domain model, dữ liệu đưa vào template, DTO hoặc đối tượng Model của Spring MVC. Những đối tượng này không nhất thiết là một. Hiểu rõ vai trò của từng loại giúp tránh việc entity JPA, form object hoặc Spring Model trở thành nơi chứa toàn bộ nghiệp vụ.

## 1. Hai cách nhìn, hai câu hỏi khác nhau

MVC trả lời câu hỏi: một tương tác của người dùng đi qua những thành phần nào để tạo ra kết quả?

- Controller nhận đầu vào và điều phối xử lý.
- Model đại diện dữ liệu và hành vi liên quan đến ứng dụng.
- View trình bày kết quả cho người dùng.

Clean Architecture trả lời câu hỏi: các chính sách và quy tắc của hệ thống được đặt ở đâu, và thành phần nào được phép phụ thuộc vào thành phần nào?

- Domain entities giữ các quy tắc nghiệp vụ cốt lõi.
- Use case điều phối một mục tiêu nghiệp vụ cụ thể.
- Interface adapters chuyển đổi dữ liệu giữa use case và các cơ chế bên ngoài.
- Frameworks và drivers cung cấp HTTP, database, message broker, file system hoặc giao diện cụ thể.

| Khía cạnh | MVC | Clean Architecture |
|---|---|---|
| Trọng tâm | Luồng tương tác và trình bày | Ranh giới, chính sách và hướng phụ thuộc |
| Thành phần tiêu biểu | Model, View, Controller | Entity, Use case, Port, Adapter |
| Câu hỏi chính | Request được xử lý và hiển thị thế nào? | Quy tắc cốt lõi phụ thuộc vào điều gì? |
| Phạm vi | Thường tập trung vào giao diện hoặc delivery flow | Có thể bao quát toàn bộ ứng dụng |
| Quan hệ với framework | Framework MVC thường cung cấp Controller, binding, View resolver | Framework nằm ở vòng ngoài và không được chi phối quy tắc bên trong |

Một ứng dụng có thể sử dụng MVC mà không áp dụng đầy đủ Clean Architecture. Ví dụ, Controller gọi trực tiếp repository, thao tác entity và trả entity ra JSON. Cách đó vẫn có thể là MVC ở mức tổ chức request/response, nhưng ranh giới nghiệp vụ và hướng phụ thuộc chưa được tách rõ.

Ngược lại, một ứng dụng theo Clean Architecture có thể có nhiều adapter đầu vào: MVC cho HTML, REST API, command line hoặc message consumer. Không phải mọi adapter đều phải dùng MVC.

## 2. MVC nằm ở đâu trong Clean Architecture?

Trong mô hình vòng tròn của Clean Architecture, các quy tắc càng quan trọng càng nằm gần trung tâm. Những thành phần bên ngoài có thể phụ thuộc vào thành phần bên trong; thành phần bên trong không được phụ thuộc ngược vào framework hoặc chi tiết bên ngoài.

Một cách đặt các thành phần MVC vào kiến trúc này:

| Thành phần MVC hoặc web | Vai trò trong Clean Architecture | Vị trí thường gặp |
|---|---|---|
| Spring Controller | Input adapter | Interface adapters |
| Request DTO / Form object | Dữ liệu đầu vào của adapter | Interface adapters |
| Presenter / Response mapper | Output adapter hoặc presentation adapter | Interface adapters |
| ViewModel | Dữ liệu dành cho View | Interface adapters |
| Thymeleaf/JSP template | Cơ chế hiển thị | Frameworks and drivers |
| Application service / Use case | Điều phối mục tiêu nghiệp vụ | Application business rules |
| Domain entity / Value object | Quy tắc và trạng thái cốt lõi | Enterprise business rules |
| Repository interface / Gateway port | Hợp đồng truy cập dữ liệu | Thường được định nghĩa ở lớp trong |
| JPA repository adapter | Hiện thực truy cập database | Interface adapters / infrastructure |
| Spring, Hibernate, Servlet container | Framework và cơ chế chạy | Frameworks and drivers |

~~~mermaid
flowchart TB
    subgraph OUTER["Frameworks and drivers"]
        HTTP[Servlet / HTTP]
        DB[(Database)]
        TEMPLATE[Thymeleaf / JSON Serializer]
    end
    subgraph ADAPTER["Interface adapters"]
        CTRL[Spring MVC Controller]
        PRES[Presenter / Response Mapper]
        REPO[JPA Repository Adapter]
        VM[ViewModel / Response DTO]
    end
    subgraph APP["Application business rules"]
        UC[Use Case / Application Service]
        PORT[Repository Port]
    end
    subgraph DOMAIN["Enterprise business rules"]
        ENT[Domain Entity / Value Object]
        POLICY[Domain Policy]
    end
    HTTP --> CTRL
    CTRL --> UC
    UC --> PORT
    REPO -. implements .-> PORT
    REPO --> DB
    UC --> ENT
    ENT --> POLICY
    CTRL --> PRES
    PRES --> VM
    VM --> TEMPLATE
~~~

Sơ đồ thể hiện vị trí khái quát. Mũi tên nét liền mô tả luồng dữ liệu hoặc lời gọi trong ví dụ; quan hệ phụ thuộc mã nguồn phải tuân theo quy tắc hướng vào trong. Cụ thể, use case định nghĩa interface của repository port; adapter JPA phụ thuộc vào interface đó để hiện thực nó. Database không được gọi ngược vào use case.

Controller và View vẫn có thể thuộc một ứng dụng MVC. Điểm thay đổi là Controller không phải nơi chứa nghiệp vụ, View không truy vấn database, và domain không import annotation của Spring MVC hoặc JPA chỉ để hoạt động.

## 3. Quy tắc phụ thuộc hướng vào trong

Quy tắc quan trọng nhất của Clean Architecture là mã nguồn ở vòng ngoài có thể biết và gọi vòng trong, nhưng vòng trong không biết chi tiết của vòng ngoài.

Ví dụ hướng phụ thuộc phù hợp:

- Spring Controller phụ thuộc vào interface của use case.
- Use case phụ thuộc vào domain entity và các port do lớp trong định nghĩa.
- JPA adapter hiện thực repository port.
- Presenter chuyển kết quả use case thành ViewModel hoặc response DTO.
- Template nhận ViewModel và render HTML.

Ví dụ hướng phụ thuộc không phù hợp:

- Domain entity import HttpServletRequest để đọc user hiện tại.
- Use case trả về ModelAndView hoặc Model của Spring MVC.
- Quy tắc nghiệp vụ phụ thuộc trực tiếp vào JpaRepository.
- Domain gọi MessageSource để lấy nhãn trạng thái tiếng Việt.
- Controller tự tạo câu SQL hoặc tính quy tắc giá, tồn kho và quyền.

Một cách kiểm tra đơn giản là hỏi: nếu đổi Spring MVC thành một framework HTTP khác, hoặc thay JPA bằng một database adapter khác, những quy tắc nghiệp vụ có cần sửa theo không? Nếu có, ranh giới phụ thuộc có thể đang bị đảo chiều.

Không phải mọi lớp đều phải có interface. Interface có giá trị khi nó xác định một ranh giới ổn định, cho phép thay adapter hoặc cô lập một chính sách. Tạo interface cho từng class nhỏ không tự động làm kiến trúc sạch hơn.

## 4. Đừng đồng nhất MVC Model với Domain Model

Từ “Model” có nhiều cách dùng trong các framework:

1. **Domain Model:** entity, value object và domain service biểu diễn quy tắc nghiệp vụ.
2. **Application model/result:** dữ liệu đầu vào hoặc đầu ra của một use case.
3. **Spring MVC Model:** vùng dữ liệu Controller đưa vào template để View render.
4. **ViewModel:** cấu trúc dữ liệu được thiết kế riêng cho một màn hình.
5. **Persistence entity:** đối tượng được ORM ánh xạ với bảng hoặc tài liệu lưu trữ.

Trong một ứng dụng nhỏ, một class có thể kiêm nhiều vai trò mà vẫn dễ quản lý. Nhưng khi các trách nhiệm khác nhau về vòng đời hoặc mục đích, nên tách chúng.

| Dữ liệu | Trường có thể chứa | Không nên chịu trách nhiệm |
|---|---|---|
| Order domain entity | Trạng thái, dòng hàng, hành vi hủy đơn, tính tổng | Tạo HTML hoặc đọc HTTP header |
| PlaceOrderCommand | Sản phẩm, số lượng, người đặt | Định dạng tiền theo locale |
| PlaceOrderResult | ID đơn, mã trạng thái, tổng tiền | Biết template nào sẽ render |
| OrderViewModel | Nhãn trạng thái, mã hiển thị, số tiền để trình bày | Quyết định có được hủy đơn |
| Spring Model | Các thuộc tính truyền cho template | Lưu trạng thái nghiệp vụ lâu dài |
| JPA OrderEntity | Trường lưu trữ và quan hệ ORM | Là hợp đồng JSON công khai mặc định |

Không nên truyền Spring Model vào application service chỉ vì Controller đã có sẵn đối tượng đó. Application service không cần biết dữ liệu sẽ được render bằng Thymeleaf, JSP hay trả qua REST.

## 5. Luồng request từ MVC qua Clean Architecture

Xét yêu cầu tạo đơn hàng từ một biểu mẫu HTML. Luồng có thể diễn ra như sau:

1. Trình duyệt gửi POST request.
2. Spring MVC Controller nhận form object, kiểm tra cấu trúc đầu vào và thông tin xác thực.
3. Controller chuyển form thành command của use case.
4. Use case kiểm tra quy tắc nghiệp vụ và gọi các port cần thiết.
5. Domain model bảo vệ bất biến, ví dụ số lượng phải dương và đơn phải có dòng hàng hợp lệ.
6. Repository port được gọi; adapter JPA thực hiện lưu trữ.
7. Use case trả application result.
8. Presenter chuyển result thành ViewModel.
9. Controller đưa ViewModel vào Spring Model và chọn template.
10. View render HTML rồi trả về trình duyệt.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant C as MVC Controller
    participant U as PlaceOrder Use Case
    participant D as Domain Model
    participant P as Order Repository Port
    participant A as JPA Adapter
    participant V as Presenter
    participant H as HTML View
    B->>C: POST /orders
    C->>C: Bind form và kiểm tra đầu vào
    C->>U: PlaceOrderCommand
    U->>D: Tạo và kiểm tra Order
    U->>P: Lưu Order
    P->>A: Port được adapter hiện thực
    A-->>U: Order đã lưu
    U-->>C: PlaceOrderResult
    C->>V: Chuyển result thành ViewModel
    V-->>C: OrderCreatedViewModel
    C->>H: Model + tên template
    H-->>B: HTML Response
~~~

Trong thực tế, Controller có thể gọi một input port, use case có thể phát sự kiện hoặc gọi nhiều output port, và transaction có thể được đặt ở application service. Sơ đồ là luồng khái niệm để nhận diện ranh giới, không bắt buộc mọi ứng dụng phải có đúng từng class riêng.

## 6. Ví dụ Spring MVC: Controller gọi use case

Giả sử một cửa hàng cho phép khách hàng đặt sản phẩm. Controller chỉ xử lý HTTP và chuyển dữ liệu đầu vào sang command.

Request form:

~~~java
public record PlaceOrderForm(
        @NotNull @Positive Long productId,
        @Min(1) int quantity
) {
}
~~~

Command thuộc application layer:

~~~java
public record PlaceOrderCommand(
        long customerId,
        long productId,
        int quantity
) {
}
~~~

Input port của use case:

~~~java
public interface PlaceOrderUseCase {
    PlaceOrderResult execute(PlaceOrderCommand command);
}
~~~

Controller phụ thuộc vào input port:

~~~java
@Controller
@RequestMapping("/orders")
public class OrderController {
    private final PlaceOrderUseCase placeOrder;
    private final OrderPresenter presenter;

    public OrderController(
            PlaceOrderUseCase placeOrder,
            OrderPresenter presenter
    ) {
        this.placeOrder = placeOrder;
        this.presenter = presenter;
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("form") PlaceOrderForm form,
            BindingResult errors,
            @AuthenticationPrincipal CurrentUser user,
            Locale locale,
            Model model
    ) {
        if (errors.hasErrors()) {
            return "orders/new";
        }

        PlaceOrderCommand command = new PlaceOrderCommand(
                user.id(),
                form.productId(),
                form.quantity()
        );

        PlaceOrderResult result = placeOrder.execute(command);
        model.addAttribute("order", presenter.toViewModel(result, locale));
        return "orders/created";
    }
}
~~~

Controller không gọi trực tiếp JpaRepository và không tạo domain entity. Nó chuyển thông tin từ giao thức HTTP thành command có ý nghĩa với use case. CurrentUser được lấy từ ngữ cảnh xác thực phía máy chủ; không lấy customerId có thẩm quyền từ form do client gửi.

Trong một ứng dụng dùng PRG, handler có thể lưu thông báo hoặc kết quả vào flash attribute rồi redirect đến GET trang chi tiết. Lựa chọn trả trực tiếp template hay redirect là quyết định của adapter web, không phải quy tắc của domain.

## 7. Use case và domain model không phụ thuộc MVC

Use case điều phối một mục tiêu nghiệp vụ. Nó không nên nhận Model, HttpServletRequest, ModelAndView hoặc đối tượng form của Spring MVC.

Kết quả use case:

~~~java
public record PlaceOrderResult(
        long orderId,
        String orderNumber,
        BigDecimal totalAmount,
        String currency,
        String statusCode
) {
}
~~~

Port truy cập dữ liệu được định nghĩa ở lớp trong:

~~~java
public interface OrderRepository {
    Order save(Order order);
}

public interface ProductCatalog {
    Product findAvailableProduct(long productId);
}
~~~

Use case triển khai:

~~~java
@Service
public class PlaceOrderService implements PlaceOrderUseCase {
    private final ProductCatalog catalog;
    private final OrderRepository orders;

    public PlaceOrderService(
            ProductCatalog catalog,
            OrderRepository orders
    ) {
        this.catalog = catalog;
        this.orders = orders;
    }

    @Override
    @Transactional
    public PlaceOrderResult execute(PlaceOrderCommand command) {
        Product product = catalog.findAvailableProduct(command.productId());
        Order order = Order.place(
                command.customerId(),
                product,
                command.quantity()
        );

        Order saved = orders.save(order);
        Money total = saved.total();

        return new PlaceOrderResult(
                saved.id(),
                saved.orderNumber(),
                total.amount(),
                total.currency(),
                saved.status().name()
        );
    }
}
~~~

Đoạn mã giả định Order.place kiểm tra các bất biến nghiệp vụ và ProductCatalog chỉ trả sản phẩm có thể đặt. Trong ứng dụng thực tế, cần xác định rõ transaction boundary, kiểm tra tồn kho đồng thời và xử lý xung đột. Annotation @Service và @Transactional là chi tiết tích hợp Spring; nếu muốn domain/application hoàn toàn độc lập framework, có thể đặt annotation transaction ở cấu hình adapter hoặc dùng decorator/proxy ở vòng ngoài.

Một số đội chấp nhận annotation Spring ở application service để giảm cấu hình. Đây là lựa chọn thực dụng, nhưng cần hiểu rằng nó tạo phụ thuộc framework ở lớp đó. Mức độ độc lập mong muốn phụ thuộc quy mô và yêu cầu thay thế framework của dự án.

## 8. Repository port và JPA adapter

Use case phụ thuộc vào interface OrderRepository. Adapter bên ngoài hiện thực interface này bằng Spring Data JPA:

~~~java
@Repository
public class JpaOrderRepositoryAdapter implements OrderRepository {
    private final SpringDataOrderJpaRepository jpa;
    private final OrderPersistenceMapper mapper;

    public JpaOrderRepositoryAdapter(
            SpringDataOrderJpaRepository jpa,
            OrderPersistenceMapper mapper
    ) {
        this.jpa = jpa;
        this.mapper = mapper;
    }

    @Override
    public Order save(Order order) {
        OrderJpaEntity entity = mapper.toEntity(order);
        OrderJpaEntity saved = jpa.save(entity);
        return mapper.toDomain(saved);
    }
}
~~~

Spring Data repository và entity JPA nằm ở adapter/persistence. Domain và use case không cần biết bảng tên gì, khóa ngoại ra sao hoặc Hibernate dùng proxy thế nào.

Với ứng dụng đơn giản, domain object và JPA entity có thể dùng chung một class để giảm mapping. Khi làm vậy, cần đánh giá mức phụ thuộc vào ORM, lazy loading, annotation và vòng đời persistence. Nếu các chi tiết ORM làm domain khó kiểm thử hoặc khó thay đổi, tách persistence model sẽ có lợi.

## 9. Presenter và ViewModel là adapter đầu ra

Use case trả kết quả nghiệp vụ hoặc application result. Presenter chuyển kết quả đó thành cấu trúc phù hợp với giao diện.

ViewModel:

~~~java
public record OrderCreatedViewModel(
        String orderNumber,
        String total,
        String statusLabel
) {
}
~~~

Presenter cho HTML:

~~~java
@Component
public class OrderPresenter {
    private final MessageSource messages;

    public OrderPresenter(MessageSource messages) {
        this.messages = messages;
    }

    public OrderCreatedViewModel toViewModel(
            PlaceOrderResult result,
            Locale locale
    ) {
        String statusKey = "order.status."
                + result.statusCode().toLowerCase(Locale.ROOT);
        String statusLabel = messages.getMessage(statusKey, null, locale);

        NumberFormat moneyFormat =
                NumberFormat.getCurrencyInstance(locale);
        Currency currency = Currency.getInstance(result.currency());
        moneyFormat.setCurrency(currency);
        int fractionDigits = currency.getDefaultFractionDigits();
        if (fractionDigits >= 0) {
            moneyFormat.setMinimumFractionDigits(fractionDigits);
            moneyFormat.setMaximumFractionDigits(fractionDigits);
        }

        String total = moneyFormat.format(result.totalAmount());
        return new OrderCreatedViewModel(
                result.orderNumber(),
                total,
                statusLabel
        );
    }
}
~~~

Đây là presenter thiên về HTML, vì nó tạo chuỗi tiền và nhãn theo locale. Với JSON API, nên có response DTO riêng giữ giá trị số, mã tiền tệ và mã trạng thái ổn định. Không dùng chuỗi đã định dạng cho người dùng làm giá trị để client tính toán.

Ví dụ API response:

~~~java
public record PlaceOrderResponse(
        String orderNumber,
        BigDecimal totalAmount,
        String currency,
        String status
) {
}
~~~

Một presenter khác có thể ánh xạ PlaceOrderResult sang PlaceOrderResponse. Hai adapter có thể dùng chung application result nhưng tạo hợp đồng đầu ra khác nhau.

## 10. Output port và các cách tổ chức presenter

Trong cách trình bày Clean Architecture cổ điển, use case có thể định nghĩa output boundary (output port), còn presenter bên ngoài hiện thực boundary đó. Interactor gọi output port để gửi kết quả đã xử lý.

Ví dụ interface:

~~~java
public interface PlaceOrderOutputPort {
    void present(PlaceOrderOutput output);
}
~~~

Có nhiều cách nối output port với request:

- Use case trả về application result bất biến; Controller gọi presenter để tạo ViewModel.
- Use case nhận output port theo lần thực thi; Controller tạo presenter cho request đó rồi truyền vào.
- Một presenter được tạo theo request scope hoặc qua factory để tránh giữ kết quả của request trước.

Điều cần bảo đảm là output port được định nghĩa ở lớp trong, còn presenter cụ thể thuộc adapter ngoài. Nếu presenter lưu kết quả vào field và bean là singleton, dữ liệu của các request có thể bị trộn. Hãy dùng đối tượng bất biến theo lần gọi hoặc vòng đời request được kiểm soát.

Với ứng dụng Spring MVC thông thường, cách use case trả result bất biến và Controller gọi mapper/presenter thuần dữ liệu thường đơn giản, dễ hiểu. Không cần triển khai output boundary riêng nếu nó chỉ tạo thêm ceremony mà không đem lại lợi ích rõ.

## 11. REST API cũng là một adapter của cùng use case

Một use case có thể được gọi từ HTML Controller, REST Controller hoặc message consumer. Mỗi adapter chuyển dữ liệu đầu vào theo giao thức riêng rồi gọi cùng input port.

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderApiController {
    private final PlaceOrderUseCase placeOrder;
    private final OrderApiPresenter presenter;

    public OrderApiController(
            PlaceOrderUseCase placeOrder,
            OrderApiPresenter presenter
    ) {
        this.placeOrder = placeOrder;
        this.presenter = presenter;
    }

    @PostMapping
    public ResponseEntity<PlaceOrderResponse> create(
            @Valid @RequestBody PlaceOrderRequest request,
            @AuthenticationPrincipal CurrentUser user
    ) {
        PlaceOrderCommand command = new PlaceOrderCommand(
                user.id(),
                request.productId(),
                request.quantity()
        );

        PlaceOrderResult result = placeOrder.execute(command);
        PlaceOrderResponse response = presenter.toResponse(result);

        URI location = URI.create("/api/orders/" + result.orderId());
        return ResponseEntity.created(location).body(response);
    }
}
~~~

HTML adapter có thể trả template; REST adapter trả JSON. Cả hai dùng cùng use case nên quy tắc đặt hàng không bị nhân đôi trong hai Controller.

Không có nghĩa là mọi giao diện phải chia sẻ một DTO. Request form, request JSON, application command, ViewModel HTML và response DTO có thể khác nhau vì chúng thuộc các hợp đồng khác nhau.

## 12. Xử lý validation và lỗi ở đúng lớp

Validation có nhiều loại và nên được đặt theo ý nghĩa:

| Loại kiểm tra | Ví dụ | Vị trí phù hợp |
|---|---|---|
| Cú pháp giao thức | JSON parse được, query parameter là số | HTTP adapter/framework |
| Cấu trúc đầu vào | Trường bắt buộc, chuỗi không rỗng, số lượng tối thiểu | Request DTO và Bean Validation |
| Quy tắc use case | Người dùng có thể đặt sản phẩm này không? | Application service/policy |
| Bất biến miền | Số lượng phải dương, tổng tiền hợp lệ | Domain entity/value object |
| Quy tắc lưu trữ | Unique constraint, khóa ngoại | Database adapter và database |

Controller có thể dùng @Valid để phát hiện form sai cấu trúc trước khi gọi use case. Tuy nhiên, use case vẫn cần bảo vệ quy tắc nghiệp vụ vì nó có thể được gọi từ REST, message consumer hoặc tác vụ nền.

Domain không nên trả lỗi dưới dạng HTTP status. Nó có thể ném domain exception hoặc trả kết quả thất bại có kiểu. Adapter chuyển lỗi đó thành HTTP 400, 403, 404, 409 hoặc trang lỗi phù hợp với hợp đồng.

Với Spring MVC, @ControllerAdvice và @ExceptionHandler là một cách đặt bộ chuyển lỗi ở adapter web. Không để application service trả ModelAndView hoặc ResponseEntity chỉ để thuận tiện cho Controller.

## 13. Transaction và ranh giới use case

Clean Architecture thường đặt ranh giới transaction quanh một use case hoặc một đơn vị công việc nghiệp vụ. MVC Controller không nên tự quản lý transaction bằng cách mở/đóng session database.

Một luồng tạo đơn có thể gồm:

1. Đọc sản phẩm và giá có thẩm quyền.
2. Kiểm tra quy tắc đặt hàng.
3. Giữ chỗ tồn kho.
4. Lưu đơn.
5. Ghi outbox event nếu cần phát sự kiện sau commit.

Nếu các bước cần nguyên tử trong cùng database, application service có thể xác định transaction boundary. Nếu tồn kho hoặc thanh toán nằm ở dịch vụ khác, một transaction database không thể tự bao trùm toàn bộ hệ thống; cần thiết kế saga, reservation, idempotency hoặc cơ chế bù trừ phù hợp.

Không giữ transaction mở trong khi chờ người dùng nhập form hoặc chờ một request HTTP khác. Mỗi request thường bắt đầu và kết thúc transaction trong thời gian xử lý của use case.

## 14. Cấu trúc package gợi ý

Một cấu trúc package theo hướng Clean Architecture có thể đặt adapter MVC và persistence ở vòng ngoài:

~~~text
com.example.shop
  domain
    order
      Order.java
      OrderLine.java
      OrderStatus.java
    shared
      Money.java
  application
    port
      in
        PlaceOrderUseCase.java
      out
        OrderRepository.java
        ProductCatalog.java
    usecase
      PlaceOrderService.java
    model
      PlaceOrderCommand.java
      PlaceOrderResult.java
  adapter
    in
      web
        OrderController.java
        OrderApiController.java
        PlaceOrderForm.java
        PlaceOrderRequest.java
        OrderPresenter.java
        OrderApiPresenter.java
        OrderViewModel.java
    out
      persistence
        JpaOrderRepositoryAdapter.java
        SpringDataOrderJpaRepository.java
        OrderJpaEntity.java
        OrderPersistenceMapper.java
  infrastructure
    config
      WebConfig.java
      PersistenceConfig.java
~~~

Tên package không quyết định kiến trúc. Một dự án có thể dùng package theo feature như order, bên trong mỗi feature chia domain, application, adapter. Điều quan trọng là import và dependency thực tế tuân thủ hướng vào trong.

Không nên tạo một package common hoặc shared quá lớn chứa mọi kiểu DTO và helper. Những kiểu dữ liệu dùng chung cần có chủ sở hữu rõ; nếu không, các tầng sẽ phụ thuộc chéo vào một vùng mã không có ranh giới.

## 15. Kiểm thử khi kết hợp MVC và Clean Architecture

Tách ranh giới giúp mỗi loại test tập trung vào một trách nhiệm:

| Lớp | Loại test | Nội dung cần xác nhận |
|---|---|---|
| Domain | Unit test | Bất biến, phép tính, chuyển trạng thái |
| Application use case | Unit test | Điều phối, gọi port, kết quả và lỗi |
| Input adapter MVC | MVC slice test | Binding, validation, authentication, HTTP contract |
| Presenter | Unit test | Ánh xạ result sang ViewModel/response |
| Persistence adapter | Integration test | Mapping ORM, truy vấn, transaction, constraint |
| Toàn luồng | Component/E2E test | Một hành trình người dùng qua các adapter thật |

Domain test không cần khởi tạo Spring. Use case test có thể dùng fake repository hoặc mock port. MVC test dùng MockMvc để kiểm tra status, response và View. Persistence test dùng database phù hợp để kiểm tra hành vi ORM thật.

Ví dụ kiểm thử use case qua port:

~~~java
@Test
void createsOrderAndReturnsApplicationResult() {
    Product product = anAvailableProduct(9L);
    given(catalog.findAvailableProduct(9L)).willReturn(product);
    given(orders.save(any(Order.class)))
            .willAnswer(invocation -> {
                Order order = invocation.getArgument(0);
                return order.withId(42L);
            });

    PlaceOrderResult result = service.execute(
            new PlaceOrderCommand(7L, 9L, 2)
    );

    assertThat(result.orderId()).isEqualTo(42L);
    assertThat(result.statusCode()).isEqualTo("PLACED");
    verify(orders).save(any(Order.class));
}
~~~

Test không cần biết service được gọi từ Spring Controller hay REST adapter. Nó kiểm tra mục tiêu nghiệp vụ qua input port.

Ví dụ MVC slice test tập trung vào HTTP:

~~~java
@WebMvcTest(OrderApiController.class)
class OrderApiControllerTest {
    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    PlaceOrderUseCase placeOrder;

    @Test
    void rejectsQuantityBelowMinimum() throws Exception {
        mockMvc.perform(post("/api/orders")
                        .with(csrf())
                        .with(authentication(authenticationFor(7L)))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "productId": 9,
                                  "quantity": 0
                                }
                                """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(placeOrder);
    }
}
~~~

Đây là ví dụ khái niệm; cấu hình bảo mật và kiểu principal cần khớp ứng dụng cụ thể. Test xác nhận adapter từ chối đầu vào không hợp lệ trước khi gọi use case. Quy tắc nghiệp vụ vẫn phải được test riêng ở domain/application.

Hàm authenticationFor là fixture tạo Authentication có principal kiểu CurrentUser mà Controller yêu cầu. Với ứng dụng không dùng Spring Security, bỏ phần authentication và cấu hình MockMvc tương ứng.

## 16. Khi nào nên áp dụng Clean Architecture quanh MVC?

Không phải ứng dụng nào cũng cần đầy đủ vòng port/adapter. Quy mô, vòng đời và độ phức tạp của nghiệp vụ quyết định mức tách phù hợp.

Clean Architecture hữu ích khi:

- Nghiệp vụ có nhiều quy tắc, trạng thái và luồng xử lý.
- Cùng use case được gọi từ HTML, REST, message hoặc batch.
- Có nhiều tích hợp bên ngoài hoặc khả năng thay đổi persistence.
- Cần kiểm thử nghiệp vụ nhanh mà không khởi động framework.
- Nhiều nhóm phát triển song song và cần ranh giới phụ thuộc rõ.
- Hệ thống có vòng đời dài, yêu cầu thay đổi adapter nhưng giữ quy tắc cốt lõi.

Một cấu trúc MVC đơn giản có thể phù hợp khi:

- Ứng dụng CRUD nội bộ nhỏ, ít quy tắc.
- Dữ liệu và màn hình gần như một-một.
- Chỉ có một giao thức và một nguồn dữ liệu ổn định.
- Chi phí tạo thêm interface, mapper và package vượt lợi ích.

Ngay cả ứng dụng nhỏ vẫn nên giữ một số nguyên tắc cơ bản: Controller mỏng, validation rõ, không đưa dữ liệu nhạy cảm ra View, không để View truy vấn dữ liệu và không nhân đôi quy tắc nghiệp vụ. Có thể bắt đầu đơn giản rồi tách port/use case khi có lý do cụ thể.

## 17. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| MVC và Clean Architecture là hai lựa chọn loại trừ nhau | MVC có thể là adapter giao diện bên ngoài của Clean Architecture |
| MVC Model luôn là domain entity | Model trong framework MVC có thể chỉ là dữ liệu cho View |
| Controller phải chứa toàn bộ luồng nghiệp vụ | Controller nên chuyển request thành input của use case |
| Clean Architecture bắt buộc mọi class phải có interface | Interface hữu ích ở ranh giới cần đảo chiều phụ thuộc |
| Repository luôn thuộc domain | Port thường được định nghĩa ở application/domain; adapter JPA ở vòng ngoài |
| ViewModel là domain model | ViewModel phục vụ trình bày và có thể thay đổi độc lập |
| Dùng Spring annotation nghĩa là không thể áp dụng Clean Architecture | Có thể giữ phần lớn quy tắc độc lập; mức framework coupling là lựa chọn có chủ đích |
| Cần tách entity JPA khỏi domain trong mọi dự án | Tách khi lợi ích về độc lập, vòng đời hoặc mapping lớn hơn chi phí |
| Một use case phải trả ModelAndView | Use case trả kết quả ứng dụng; adapter quyết định HTTP hoặc View |
| Nhiều lớp hơn đồng nghĩa kiến trúc tốt hơn | Chất lượng đến từ ranh giới rõ và dependency đúng, không phải số lượng class |

## 18. Lộ trình chuyển một ứng dụng MVC hiện có

Không cần viết lại toàn bộ ứng dụng để cải thiện ranh giới. Có thể tiến hành từng bước theo use case:

1. Chọn một luồng có nghiệp vụ rõ, ví dụ tạo đơn hoặc hoàn tiền.
2. Ghi lại request, kết quả và các quy tắc hiện đang nằm trong Controller.
3. Tách command và result khỏi form object hoặc Spring Model.
4. Di chuyển quy tắc nghiệp vụ vào domain object hoặc application service.
5. Định nghĩa input port cho use case nếu cần tách adapter.
6. Đưa truy cập database sau một repository port do lớp trong sở hữu.
7. Tạo adapter JPA hiện thực port và kiểm thử tích hợp.
8. Giữ Controller làm nhiệm vụ bind request, gọi use case và chọn response.
9. Tạo presenter/mapper nếu ViewModel khác application result.
10. Chuyển các luồng khác khi có nhu cầu, không nhân bản cấu trúc máy móc.

Sau mỗi bước, kiểm tra hợp đồng HTTP và quy tắc nghiệp vụ. Refactor nên giữ hành vi hiện tại trừ khi có yêu cầu thay đổi riêng.

## 19. Checklist đánh giá ranh giới MVC và Clean Architecture

Khi review một module web, hãy kiểm tra:

- Controller có phụ thuộc vào use case/input port thay vì chi tiết persistence không?
- Request DTO có được chuyển thành command phù hợp trước khi vào application layer không?
- Use case có tránh phụ thuộc HttpServletRequest, ModelAndView và template không?
- Domain entity có giữ quy tắc cốt lõi mà không cần Spring MVC không?
- Repository port được định nghĩa ở lớp trong và adapter JPA hiện thực port đó không?
- Presenter có chuyển application result thành ViewModel/response DTO theo hợp đồng không?
- View có chỉ render dữ liệu, không gọi repository hoặc quyết định quy tắc nghiệp vụ không?
- Lỗi domain/application có được adapter ánh xạ thành HTTP response phù hợp không?
- Transaction boundary có đặt quanh use case và không kéo dài qua thời gian người dùng tương tác không?
- Các test có thể kiểm tra domain/use case mà không khởi động toàn bộ web stack không?
- Có interface hoặc mapper nào được tạo chỉ vì hình thức mà không bảo vệ ranh giới thực tế không?
- Việc thay framework web hoặc database có buộc sửa quy tắc cốt lõi không?

MVC và Clean Architecture bổ sung cho nhau khi mỗi mô hình được dùng đúng mục đích. MVC giúp tổ chức tương tác và trình bày; Clean Architecture giữ quy tắc nghiệp vụ ở trung tâm và hướng phụ thuộc về phía trong. Khi kết hợp, Controller trở thành input adapter, presenter và ViewModel trở thành output adapter, còn use case và domain model giữ vai trò quyết định hành vi. Mức độ tách lớp có thể tăng dần theo độ phức tạp, miễn là ranh giới quan trọng luôn rõ và có lý do.

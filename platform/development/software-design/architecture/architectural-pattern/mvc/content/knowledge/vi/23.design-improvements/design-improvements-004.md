# Rút ca sử dụng ra dịch vụ ứng dụng

Trong ứng dụng MVC, Controller tiếp nhận HTTP request, chuyển dữ liệu đầu vào thành lời gọi nghiệp vụ và chọn phản hồi. Khi ứng dụng còn nhỏ, một Controller có thể xử lý khá nhiều bước mà vẫn dễ hiểu. Nhưng khi nghiệp vụ phát triển, các method Controller thường bắt đầu truy vấn nhiều repository, kiểm tra điều kiện, thay đổi trạng thái, gọi dịch vụ ngoài, phát sự kiện và điều phối transaction. Lúc đó, Controller không còn chỉ là adapter HTTP mà đã trở thành nơi thực thi use case.

**Rút ca sử dụng ra dịch vụ ứng dụng** là cách chuyển phần điều phối nghiệp vụ của một hành động người dùng sang application service (dịch vụ ứng dụng). Controller vẫn chịu trách nhiệm nhận request, binding, validation ở ranh giới web và tạo response; application service chịu trách nhiệm thực hiện một use case; domain model bảo vệ quy tắc và bất biến của nghiệp vụ.

Với ứng dụng **Model–View–Controller (MVC)**, cách tách này giúp cùng một use case có thể được gọi từ web page, REST API, tác vụ nền hoặc message consumer mà không phải sao chép quy trình nghiệp vụ vào nhiều adapter. Bài học này trình bày dấu hiệu cần refactor, cách xác định ranh giới use case, thiết kế input/output, quản lý transaction và kiểm thử dịch vụ ứng dụng.

## 1. Use case là gì?

Use case mô tả một mục tiêu mà actor muốn đạt được khi tương tác với hệ thống. Nó thường thể hiện một hành động có ý nghĩa nghiệp vụ, ví dụ:

- Tạo đơn hàng.
- Hủy đơn hàng.
- Đăng ký tài khoản.
- Phê duyệt yêu cầu hoàn tiền.
- Đặt lại mật khẩu.
- Tạo báo cáo doanh thu.
- Xác nhận thanh toán.

Use case không nhất thiết tương ứng với một URL hoặc một method CRUD. Một endpoint có thể thực hiện một use case; ngược lại, nhiều endpoint có thể cùng gọi một use case. Ví dụ giao diện web và API mobile có thể cùng gọi hành vi tạo đơn hàng, dù request và response của chúng khác nhau.

Ranh giới use case thường được nhận diện bằng:

- Mục tiêu nghiệp vụ mà actor muốn hoàn thành.
- Dữ liệu đầu vào cần thiết để thực hiện mục tiêu.
- Các quy tắc phải được kiểm tra.
- Các trạng thái hoặc tác dụng phụ có thể xảy ra.
- Kết quả hoặc lỗi mà bên gọi cần biết.
- Ranh giới transaction hoặc bước xử lý có ý nghĩa.

Một use case nên có tên thể hiện hành động nghiệp vụ, chẳng hạn CreateOrder, CancelOrder hoặc ApproveRefund. Tên này dễ hiểu hơn một service tổng quát chứa các method như process, handle hoặc executeAction.

## 2. Vai trò của Controller, Application Service và Domain Model

Ba thành phần phối hợp với nhau nhưng có trách nhiệm khác nhau.

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| Controller | HTTP routing, binding, validation đầu vào, chọn View/status/response | Nhận POST /orders |
| Application Service | Điều phối use case, tải dữ liệu cần thiết, gọi domain, lưu kết quả, điều phối port | CreateOrderService |
| Domain Model | Bảo vệ quy tắc, bất biến và chuyển trạng thái nghiệp vụ | Order.place(), Order.cancel() |

Application service thường điều phối một kịch bản, nhưng không nên trở thành nơi chứa mọi quy tắc. Quy tắc gắn với một entity hoặc value object nên nằm trong chính domain object đó. Quy tắc nghiệp vụ không thuộc riêng một entity có thể nằm trong domain service hoặc policy phù hợp.

~~~mermaid
flowchart TD
    R[HTTP Request] --> C[Controller]
    C --> V[Bind và validate request]
    V --> A[Application Service / Use Case]
    A --> D[Domain Model]
    A --> P[Repository và các Port]
    P --> I[Infrastructure Adapters]
    D --> A
    I --> A
    A --> C
    C --> O[View hoặc HTTP Response]
~~~

Controller biết HTTP. Application service biết use case. Domain model biết quy tắc nghiệp vụ. Infrastructure adapter biết chi tiết database, HTTP client, message broker hoặc file system.

## 3. Dấu hiệu nghiệp vụ đang nằm quá nhiều trong Controller

Không phải mọi Controller có vài dòng điều kiện đều cần tách service. Nên xem xét refactor khi xuất hiện một hoặc nhiều dấu hiệu:

- Method Controller có nhiều bước nghiệp vụ liên tiếp.
- Controller gọi nhiều repository hoặc nhiều dịch vụ bên ngoài.
- Một thao tác cần kiểm tra quyền sở hữu, trạng thái, hạn mức và điều kiện liên quan.
- Logic tương tự xuất hiện ở Controller khác, API khác hoặc tác vụ nền.
- Test Controller phải mock quá nhiều dependency để kiểm tra một hành động.
- Transaction được mở ở tầng web hoặc có nhiều thao tác ghi dữ liệu.
- Controller tự quyết định thứ tự lưu, phát sự kiện, gửi email và gọi thanh toán.
- Một thay đổi nghiệp vụ buộc phải sửa nhiều endpoint.

Ví dụ Controller bắt đầu phình to:

~~~java
@PostMapping("/orders")
public String create(
        @Valid @ModelAttribute("form") CreateOrderForm form,
        BindingResult errors,
        Principal principal
) {
    if (errors.hasErrors()) {
        return "orders/create";
    }

    User user = userRepository.findByUsername(principal.getName())
            .orElseThrow(UserNotFoundException::new);
    Product product = productRepository.findById(form.productId())
            .orElseThrow(ProductNotFoundException::new);

    if (!product.isSellable()) {
        throw new ProductUnavailableException();
    }
    if (form.quantity() <= 0) {
        throw new InvalidQuantityException();
    }

    BigDecimal total = product.getPrice()
            .multiply(BigDecimal.valueOf(form.quantity()));

    Order order = new Order(user, product, form.quantity(), total);
    orderRepository.save(order);
    inventoryRepository.reserve(product.getId(), form.quantity());
    emailService.sendOrderConfirmation(user.getEmail(), order.getId());

    return "redirect:/orders/" + order.getId();
}
~~~

Method này đang làm nhiều việc:

1. Nhận và kiểm tra form.
2. Xác định người dùng.
3. Tải sản phẩm và kiểm tra khả năng bán.
4. Tính tổng tiền.
5. Tạo đơn hàng.
6. Lưu đơn và giữ tồn kho.
7. Gửi email.
8. Chọn redirect.

Một số bước là trách nhiệm HTTP; phần lớn còn lại thuộc use case hoặc domain. Khi cần tạo đơn từ REST API hoặc worker, nhóm sẽ phải sao chép logic này nếu không có dịch vụ ứng dụng.

## 4. Không tách service chỉ bằng cách chuyển nguyên method

Một refactor máy móc có thể chuyển toàn bộ code sang một class khác nhưng vẫn giữ nguyên cách trộn trách nhiệm:

~~~java
public class OrderService {
    public String createOrder(
            CreateOrderForm form,
            Principal principal,
            Model model
    ) {
        // Binding, đọc Principal, thao tác repository,
        // chọn tên View và redirect...
    }
}
~~~

Đây chưa phải application service có ranh giới tốt. Nó vẫn phụ thuộc vào Servlet/MVC API, View và kiểu form của giao diện.

Application service nên nhận dữ liệu ứng dụng độc lập với HTTP, chẳng hạn command hoặc input DTO. Nó trả kết quả nghiệp vụ hoặc application result, không trả tên template, redirect URL hay đối tượng HttpServletRequest.

## 5. Thiết kế input cho use case

Một command thể hiện ý định của actor và chứa các dữ liệu cần thiết để thực hiện use case.

~~~java
public record CreateOrderCommand(
        String customerId,
        String productId,
        int quantity
) {}
~~~

Command nên:

- Chứa dữ liệu cần cho use case, không chứa toàn bộ request HTTP.
- Có kiểu dữ liệu và đơn vị rõ ràng.
- Không nhận các trường client không được phép quyết định như role, ownerId hoặc trạng thái nội bộ.
- Không mang đối tượng framework như Model, BindingResult hoặc HttpServletRequest.
- Được tạo ở adapter phù hợp sau khi xác thực và kiểm tra dữ liệu đầu vào.

Nếu danh tính người dùng cần lấy từ security context, Controller hoặc một adapter ứng dụng có thể chuyển principal đã xác thực thành actor ID. Không lấy customerId từ form nếu use case phải thao tác trên tài khoản hiện tại.

Ví dụ command không cho client chọn chủ sở hữu:

~~~java
public record CreateMyOrderCommand(
        String productId,
        int quantity
) {}
~~~

Application service nhận customer ID từ actor context đáng tin cậy hoặc một tham số actor được adapter cung cấp. Cách truyền actor nên nhất quán với chính sách bảo mật của ứng dụng.

## 6. Thiết kế output của use case

Application service có thể trả về ID, một result object hoặc DTO phù hợp với nhu cầu của bên gọi.

~~~java
public record CreateOrderResult(
        String orderId,
        String orderNumber,
        OrderStatus status
) {}
~~~

Không nên trả một entity JPA đang được quản lý nếu bên gọi chỉ cần một vài trường. Entity có thể chứa quan hệ lazy, trạng thái nội bộ và chi tiết persistence. Result object tạo hợp đồng ổn định hơn giữa application layer và adapter.

Một use case có thể trả cùng application result cho nhiều adapter:

- Web Controller chuyển result thành View Model.
- REST Controller chuyển result thành response DTO.
- Message consumer ghi nhận kết quả hoặc phát event tiếp theo.

Nếu hai client có nhu cầu trình bày khác nhau, mỗi adapter có thể ánh xạ cùng result sang representation riêng.

## 7. Rút use case tạo đơn hàng ra application service

Ví dụ service sau điều phối use case tạo đơn. Các quy tắc như sản phẩm có được bán và số lượng có hợp lệ không cần được đặt ở đúng domain/policy tương ứng; đoạn mã minh họa gọi domain method để thực hiện việc đó.

~~~java
@Service
public class CreateOrderService {
    private final CustomerRepository customerRepository;
    private final ProductRepository productRepository;
    private final OrderRepository orderRepository;
    private final InventoryPort inventoryPort;

    public CreateOrderService(
            CustomerRepository customerRepository,
            ProductRepository productRepository,
            OrderRepository orderRepository,
            InventoryPort inventoryPort
    ) {
        this.customerRepository = customerRepository;
        this.productRepository = productRepository;
        this.orderRepository = orderRepository;
        this.inventoryPort = inventoryPort;
    }

    @Transactional
    public CreateOrderResult execute(CreateOrderCommand command) {
        Customer customer = customerRepository.findById(command.customerId())
                .orElseThrow(CustomerNotFoundException::new);
        Product product = productRepository.findById(command.productId())
                .orElseThrow(ProductNotFoundException::new);

        Order order = Order.create(
                customer,
                product,
                command.quantity()
        );

        inventoryPort.reserve(
                product.getId(),
                command.quantity(),
                order.getId()
        );

        orderRepository.save(order);

        return new CreateOrderResult(
                order.getId().toString(),
                order.getOrderNumber(),
                order.getStatus()
        );
    }
}
~~~

Đây là ví dụ minh họa cho việc gom điều phối vào một use case. Trong hệ thống thực tế, nếu Inventory là dịch vụ ngoài hoặc có transaction riêng, không nên giả định lời gọi reserve và lưu Order cùng rollback nguyên tử. Khi đó cần thiết kế trạng thái trung gian, idempotency, outbox hoặc Saga phù hợp.

## 8. Controller sau khi refactor

Controller trở nên ngắn hơn và chỉ giữ trách nhiệm web:

~~~java
@Controller
@RequestMapping("/orders")
public class OrderController {
    private final CreateOrderService createOrderService;

    public OrderController(CreateOrderService createOrderService) {
        this.createOrderService = createOrderService;
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("form") CreateOrderForm form,
            BindingResult errors,
            @AuthenticationPrincipal AppPrincipal principal,
            RedirectAttributes redirect
    ) {
        if (errors.hasErrors()) {
            return "orders/create";
        }

        CreateOrderCommand command = new CreateOrderCommand(
                principal.customerId(),
                form.productId(),
                form.quantity()
        );
        CreateOrderResult result = createOrderService.execute(command);

        redirect.addFlashAttribute("notice", "Đã tạo đơn hàng.");
        return "redirect:/orders/" + result.orderId();
    }
}
~~~

Controller không cần biết đơn hàng được lưu bằng JPA hay repository khác. Nó cũng không cần biết InventoryPort được triển khai bằng lời gọi nội bộ, HTTP hay message. Controller chỉ chuyển request thành command, gọi use case và chuyển result thành phản hồi web.

## 9. Cùng use case có thể được gọi từ REST API

Một REST Controller có thể dùng cùng application service:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderApiController {
    private final CreateOrderService createOrderService;

    public OrderApiController(CreateOrderService createOrderService) {
        this.createOrderService = createOrderService;
    }

    @PostMapping
    public ResponseEntity<CreateOrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request,
            @AuthenticationPrincipal AppPrincipal principal
    ) {
        CreateOrderResult result = createOrderService.execute(
                new CreateOrderCommand(
                        principal.customerId(),
                        request.productId(),
                        request.quantity()
                )
        );

        URI location = URI.create("/api/orders/" + result.orderId());
        return ResponseEntity.created(location)
                .body(new CreateOrderResponse(
                        result.orderId(),
                        result.orderNumber(),
                        result.status()
                ));
    }
}
~~~

Web Controller và REST Controller có thể có form, validation message và response khác nhau nhưng dùng chung use case. Nếu logic nghiệp vụ chỉ tồn tại trong application service, hai adapter không phải sao chép quy trình tạo đơn.

## 10. Tách command use case và query service

Một số ứng dụng có thể tổ chức application layer theo hai nhóm:

- **Command use case:** thực hiện hành động làm thay đổi trạng thái.
- **Query service:** đọc và trả dữ liệu cho màn hình hoặc API.

Ví dụ:

~~~java
public interface CancelOrderUseCase {
    void execute(CancelOrderCommand command);
}

public interface OrderQueries {
    OrderDetailView getDetail(String orderId, String actorId);
    Page<OrderRowView> search(OrderSearchCriteria criteria);
}
~~~

Command và query có yêu cầu khác nhau. Command cần bảo vệ bất biến, kiểm tra quyền và quản lý tác dụng phụ. Query thường tối ưu cho việc đọc, projection, phân trang và lọc.

Không bắt buộc phải áp dụng CQRS đầy đủ với hai database hoặc hai mô hình dữ liệu riêng. Tách command/query ở mức interface hoặc class là một cách tổ chức application code đơn giản; CQRS nâng cao là một quyết định kiến trúc rộng hơn.

## 11. Application Service khác Domain Service

Hai loại service có mục tiêu khác nhau:

| Loại | Vai trò | Ví dụ |
|---|---|---|
| Application Service | Điều phối use case và ranh giới giao tiếp | CreateOrderService |
| Domain Service | Thực hiện quy tắc domain không thuộc tự nhiên về một entity/value object | PricingPolicy |
| Infrastructure Service/Adapter | Tích hợp công nghệ hoặc hệ thống ngoài | SmtpEmailAdapter |

Application service thường:

- Tải aggregate hoặc dữ liệu cần thiết.
- Gọi hành vi trên domain object.
- Điều phối repository, gateway hoặc port.
- Quản lý transaction ở mức use case.
- Trả application result.

Domain service thường:

- Chứa quy tắc nghiệp vụ thuần túy.
- Không phụ thuộc HTTP, database hoặc Spring.
- Phối hợp các đối tượng domain khi quy tắc không thuộc riêng một đối tượng.

Không nên đưa mọi method vào một class có tên Service. Hãy đặt trách nhiệm theo bản chất của hành vi.

## 12. Transaction nên nằm ở đâu?

Application service thường là ranh giới phù hợp để khai báo transaction vì một use case có thể gồm nhiều thao tác repository cần commit hoặc rollback cùng nhau.

~~~java
@Transactional
public CreateOrderResult execute(CreateOrderCommand command) {
    // Tải dữ liệu, gọi domain behavior và lưu aggregate.
}
~~~

Controller không nên mở transaction chỉ vì nó nhận request. View rendering cũng không nên giữ transaction mở để tải dữ liệu trong template.

Một số lưu ý:

- Transaction nên ngắn, gắn với một use case rõ.
- Không giữ transaction mở trong khi chờ một API bên ngoài lâu nếu có thể tránh.
- Transaction database cục bộ không bao trùm message broker hoặc dịch vụ thanh toán độc lập.
- Với lỗi cần rollback, kiểm tra quy tắc rollback của framework và loại exception.
- Với thao tác nhiều hệ thống, thiết kế state transition và hành động bù trừ thay vì giả định rollback phân tán.

Nếu application service gọi domain method và repository trong cùng transaction, domain vẫn không cần biết transaction framework. Annotation có thể đặt ở application layer hoặc được điều khiển qua decorator/interceptor tùy kiến trúc.

## 13. Không để application service phụ thuộc vào HTTP hoặc View

Application service không nên nhận:

- HttpServletRequest hoặc HttpServletResponse.
- Model, ModelMap hoặc ModelAndView.
- BindingResult.
- RedirectAttributes.
- MultipartFile trực tiếp nếu đây chỉ là chi tiết của Servlet/web layer.
- Tên template hoặc URL redirect.

Thay vào đó, adapter chuyển dữ liệu sang kiểu ứng dụng:

~~~java
public record UploadDocumentCommand(
        String ownerId,
        String originalFileName,
        String contentType,
        byte[] content
) {}
~~~

Trong trường hợp file lớn, không nên luôn đọc toàn bộ vào byte array. Có thể dùng một input port/stream abstraction phù hợp để tránh tiêu thụ bộ nhớ quá mức. Điểm quan trọng là application contract mô tả nội dung nghiệp vụ cần xử lý, không buộc use case phụ thuộc vào Servlet MultipartFile.

## 14. Đặt authorization ở đúng ranh giới

Controller có thể được bảo vệ bằng security filter hoặc method security, nhưng application service vẫn cần bảo đảm use case không bị gọi trái phép từ adapter khác.

Ví dụ:

~~~java
@Transactional
public void cancel(CancelOrderCommand command) {
    Order order = orderRepository.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

    authorizationPolicy.checkCanCancel(
            command.actorId(),
            order
    );

    order.cancel();
}
~~~

Ở đây quyền được kiểm tra trên đối tượng cụ thể. Việc người dùng có role CUSTOMER không tự động cho phép hủy mọi đơn. Nếu use case chỉ được gọi từ một ranh giới đã xác thực, actor ID vẫn phải đến từ security context đáng tin cậy, không nhận tùy tiện từ payload.

Security filter bảo vệ endpoint; application/domain policy bảo vệ hành động nghiệp vụ. Hai lớp này bổ sung cho nhau.

## 15. Xử lý lỗi ở application service và ánh xạ ở Controller

Application service nên biểu diễn lỗi theo ngữ nghĩa ứng dụng hoặc domain, chẳng hạn:

- OrderNotFoundException.
- ProductUnavailableException.
- OrderCannotBeCancelled.
- CreditLimitExceeded.
- DuplicateRequestException.

Controller hoặc global exception handler ánh xạ lỗi thành phản hồi web:

| Lỗi ứng dụng | HTML response có thể dùng | REST response có thể dùng |
|---|---|---|
| Không tìm thấy đơn | Trang 404 | 404 Not Found |
| Dữ liệu đầu vào không hợp lệ | Render lại form với lỗi | 400 Bad Request |
| Không có quyền | Trang 403 hoặc 404 theo chính sách | 403 hoặc 404 |
| Xung đột trạng thái | Trang thông báo xung đột | 409 Conflict |
| Dependency tạm thời không sẵn sàng | Trang lỗi có mã hỗ trợ | 503 Service Unavailable |

Không nên để application service trả về chuỗi tên View hoặc mã HTTP. Các giá trị đó thuộc adapter web. Đồng thời, không trả exception message nội bộ hoặc stack trace cho người dùng.

## 16. Gửi email, phát sự kiện và tác dụng phụ

Application service có thể điều phối các port cho tác dụng phụ, nhưng cần phân biệt tác dụng phụ có thể tham gia transaction cục bộ với tác dụng phụ ở hệ thống ngoài.

Ví dụ, nếu gửi email ngay trước khi transaction commit, email có thể được gửi nhưng dữ liệu đơn hàng sau đó rollback. Nếu gửi sau commit, tiến trình có thể dừng giữa commit và gửi email.

Các lựa chọn:

- Ghi event/outbox cùng transaction với thay đổi dữ liệu.
- Worker đọc outbox và gửi email hoặc publish message.
- Thiết kế consumer idempotent để xử lý message lặp.
- Lưu trạng thái gửi và retry theo chính sách.

Không nên đặt logic SMTP hoặc chi tiết message broker vào Controller. Application service có thể phát một application event hoặc ghi outbox thông qua port; adapter infrastructure xử lý giao tiếp thực tế.

## 17. Thiết kế application service nhỏ và tập trung

Một class service lớn với hàng chục method không tự động tốt hơn một Controller lớn. Mỗi use case nên có phạm vi rõ.

Ví dụ:

~~~text
ordering/
├── application/
│   ├── CreateOrderService.java
│   ├── CancelOrderService.java
│   ├── ConfirmOrderService.java
│   ├── GetOrderDetailService.java
│   ├── command/
│   └── result/
├── domain/
│   ├── Order.java
│   ├── OrderLine.java
│   └── OrderPolicy.java
├── port/
│   ├── OrderRepository.java
│   └── InventoryPort.java
└── web/
    ├── OrderController.java
    └── OrderApiController.java
~~~

Không bắt buộc mỗi use case phải có một class riêng trong mọi dự án. Với nhóm use case nhỏ, có thể gom theo capability nếu trách nhiệm vẫn rõ và class không trở thành một service tổng hợp quá rộng. Hãy tối ưu khả năng hiểu và thay đổi, không chạy theo số lượng class.

## 18. Kiểm thử Application Service độc lập với MVC

Khi use case được tách khỏi Controller, có thể kiểm tra hành vi ứng dụng mà không cần khởi động Spring MVC hoặc MockMvc.

~~~java
@ExtendWith(MockitoExtension.class)
class CancelOrderServiceTest {

    @Mock
    OrderRepository orderRepository;

    @Mock
    AuthorizationPolicy authorizationPolicy;

    @InjectMocks
    CancelOrderService service;

    @Test
    void cancelsOrderWhenActorIsAllowed() {
        Order order = Order.confirmed();
        given(orderRepository.findById("ORD-42"))
                .willReturn(Optional.of(order));

        service.execute(new CancelOrderCommand("ORD-42", "CUSTOMER-7"));

        then(authorizationPolicy).should()
                .checkCanCancel("CUSTOMER-7", order);
        assertThat(order.getStatus()).isEqualTo(OrderStatus.CANCELLED);
        then(orderRepository).should().save(order);
    }
}
~~~

Test tập trung vào use case: tải đơn, kiểm tra quyền, gọi hành vi domain và lưu kết quả. Tên method và các dependency cần điều chỉnh theo implementation thật.

Nên có các trường hợp:

- Use case thành công.
- Dữ liệu không tồn tại.
- Actor không có quyền.
- Trạng thái domain không cho phép hành động.
- Dependency trả lỗi hoặc timeout.
- Không lưu hoặc không phát event khi bước kiểm tra thất bại.
- Kết quả và tác dụng phụ đúng theo hợp đồng.

Không mock domain object nếu mục tiêu là kiểm tra quy tắc của nó. Dùng domain object thật và mock các port bên ngoài khi phù hợp.

## 19. Kiểm thử Controller sau khi tách use case

Controller test giờ chỉ cần xác minh HTTP adapter:

- Route và HTTP method đúng.
- Binding/validation hoạt động.
- Command được tạo đúng từ form hoặc request DTO.
- Use case được gọi.
- Result được ánh xạ thành View, redirect hoặc JSON.
- Lỗi được ánh xạ theo hợp đồng HTTP.

Ví dụ:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    CreateOrderService createOrderService;

    @Test
    void validFormCallsUseCaseAndRedirects() throws Exception {
        given(createOrderService.execute(any()))
                .willReturn(new CreateOrderResult(
                        "42", "ORD-42", OrderStatus.PENDING
                ));

        mockMvc.perform(post("/orders")
                        .param("productId", "P-10")
                        .param("quantity", "2"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/orders/42"));

        then(createOrderService).should().execute(argThat(command ->
                command.productId().equals("P-10")
                        && command.quantity() == 2
        ));
    }
}
~~~

Test Controller không cần lặp lại mọi quy tắc tạo đơn đã được kiểm tra trong application/domain test. Nó tập trung vào mapping giữa HTTP và use case.

## 20. Kiểm thử tích hợp và transaction

Unit test service không chứng minh transaction manager, ORM mapping hoặc database constraint hoạt động đúng. Nên bổ sung integration test cho các hành vi phụ thuộc hạ tầng:

- Lưu aggregate và đọc lại từ database.
- Rollback khi một bước persistence thất bại.
- Unique constraint và optimistic locking.
- Transactional event/outbox được ghi cùng dữ liệu.
- Repository query lọc đúng actor hoặc tenant.
- Adapter tích hợp chuyển lỗi và response theo hợp đồng.

Một test tích hợp có thể gọi application service thật với repository thật và database test. Không cần thông qua Controller nếu mục tiêu là kiểm tra transaction/use case.

Với quy trình nhiều hệ thống, test cần xác minh trạng thái trung gian, retry và hành động bù trừ. Không thể chỉ assert rằng một method service đã được gọi.

## 21. Refactor từng bước mà không làm thay đổi hành vi

Không cần viết lại Controller và toàn bộ tầng nghiệp vụ cùng lúc. Có thể chuyển dần:

1. Chọn một Controller method có use case rõ.
2. Ghi lại hành vi hiện tại: input, điều kiện, thay đổi dữ liệu, event và response.
3. Xác định bước nào là HTTP binding/validation, bước nào là nghiệp vụ.
4. Tạo command/result không phụ thuộc framework web.
5. Chuyển điều phối use case vào application service.
6. Đưa quy tắc gắn với domain object vào domain model hoặc policy phù hợp.
7. Giữ Controller làm adapter, chuyển form thành command và result thành response.
8. Viết unit test cho use case và MVC test cho Controller.
9. Thêm integration test cho persistence/transaction nếu hành vi phụ thuộc hạ tầng.
10. Sau khi hành vi được xác minh, loại bỏ code cũ trùng lặp.

~~~mermaid
flowchart TD
    A[Controller chứa use case] --> B[Chọn hành vi và ghi nhận hợp đồng]
    B --> C[Tạo Command và Result]
    C --> D[Tạo Application Service]
    D --> E[Chuyển orchestration sang service]
    E --> F[Giữ Controller làm HTTP adapter]
    F --> G[Unit test use case]
    G --> H[MVC test và integration test]
    H --> I[Xóa logic cũ trùng lặp]
~~~

Nếu có nhiều Controller cùng thực hiện một quy trình, hãy xác định một use case dùng chung và chuyển từng adapter sang gọi nó. Tránh thay đổi tất cả endpoint trong một lần nếu không cần thiết.

## 22. Những sai lầm thường gặp khi rút use case ra service

### Chuyển nguyên method Controller sang service

Nếu service vẫn nhận Model, HttpServletRequest hoặc trả tên View, nó vẫn phụ thuộc MVC. Hãy tạo command/result ở application boundary.

### Đưa mọi quy tắc vào Application Service

Service trở thành một transaction script khổng lồ. Hãy để entity/value object bảo vệ bất biến và dùng domain service cho quy tắc phù hợp.

### Tạo một God Service

Một OrderService có hàng chục method không liên quan khiến trách nhiệm khó hiểu. Nhóm theo use case hoặc capability.

### Trả entity persistence ra Controller

Điều này làm web layer phụ thuộc mapping và lifecycle ORM. Ưu tiên result DTO/View Model.

### Để Controller tự mở transaction

Transaction nên theo use case và thường nằm ở application boundary.

### Dùng command chứa toàn bộ form hoặc HTTP request

Command cần phản ánh input nghiệp vụ, không phải mọi trường giao diện. Không đưa trường nội bộ hoặc framework object vào command.

### Bỏ qua authorization vì endpoint đã được bảo vệ

Use case có thể được gọi từ adapter khác. Kiểm tra quyền trên actor và tài nguyên ở application/domain boundary khi chính sách yêu cầu.

### Kiểm thử chỉ ở Controller

Controller test mock service không chứng minh quy tắc nghiệp vụ đúng. Cần test application service và domain độc lập.

### Dùng event để né việc thiết kế use case

Phát event không tự làm cho nghiệp vụ rõ hơn. Xác định ai sở hữu trạng thái, ai điều phối và cách xử lý lỗi trước khi chọn giao tiếp bất đồng bộ.

## 23. Checklist review dịch vụ ứng dụng

- [ ] Mỗi use case có mục tiêu và ranh giới nghiệp vụ rõ.
- [ ] Controller tập trung vào HTTP, binding, validation và response.
- [ ] Application service không phụ thuộc Model, View, Servlet hoặc RedirectAttributes.
- [ ] Command chỉ chứa input cần thiết cho use case.
- [ ] Actor ID đến từ security context đáng tin cậy khi cần.
- [ ] Application result không để lộ entity persistence hoặc chi tiết framework.
- [ ] Quy tắc gắn với entity/value object nằm trong domain model.
- [ ] Application service điều phối repository và port qua hợp đồng rõ.
- [ ] Transaction gắn với use case và có failure policy phù hợp.
- [ ] Lời gọi dịch vụ ngoài có timeout, idempotency và xử lý lỗi khi cần.
- [ ] Tác dụng phụ như email/event có chiến lược nhất quán với commit.
- [ ] Authorization được kiểm tra ở endpoint và trên đối tượng theo chính sách.
- [ ] Có unit test cho use case thành công và thất bại.
- [ ] Có MVC test cho binding, command mapping và response.
- [ ] Có integration test cho persistence, transaction và adapter cần thiết.
- [ ] Logic cũ trùng lặp đã được loại bỏ sau khi refactor.

## Kết luận

Rút ca sử dụng ra dịch vụ ứng dụng giúp Controller trở lại đúng vai trò adapter HTTP. Controller nhận và xác thực dữ liệu đầu vào ở ranh giới web, chuyển thành command, gọi application service và ánh xạ kết quả thành View hoặc response. Application service điều phối một mục tiêu nghiệp vụ, quản lý ranh giới transaction và gọi các port cần thiết; domain model bảo vệ quy tắc và bất biến. Khi command/result không phụ thuộc MVC, cùng một use case có thể được tái sử dụng từ HTML Controller, REST API hoặc worker. Kết hợp unit test cho use case, MVC test cho adapter và integration test cho persistence giúp refactor từng bước mà vẫn giữ được hành vi của ứng dụng.

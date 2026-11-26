# Thiết kế application service theo ca sử dụng và mục tiêu người dùng

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED** — **Học tổ chức phần mềm theo kiến trúc phân tầng**, trong chương **Tầng ứng dụng**. Trọng tâm là thiết kế application service quanh một ca sử dụng và kết quả mà người dùng cần đạt được. Application service điều phối các bước để hoàn thành công việc đó, kết nối presentation với domain và các cổng truy cập dữ liệu hoặc hệ thống bên ngoài.

## 1. Bắt đầu từ mục tiêu người dùng

Một ca sử dụng (use case) mô tả một mục tiêu có ý nghĩa đối với người dùng hoặc một hệ thống khác. Nó nêu rõ tác nhân khởi tạo, điều kiện đầu vào, kết quả mong muốn và những tình huống thất bại quan trọng. Ví dụ:

- Khách hàng **đặt một đơn hàng** gồm các sản phẩm và số lượng.
- Nhân viên **hủy một đơn hàng** khi đơn hàng còn ở trạng thái cho phép hủy.
- Người dùng **xem lịch sử giao dịch** trong một khoảng thời gian.

Mỗi mục tiêu có thể đi qua nhiều đối tượng domain, repository hoặc dịch vụ bên ngoài. Application service tổ chức các bước đó thành một luồng xử lý có ý nghĩa. Vì vậy, thiết kế nên bắt đầu bằng câu hỏi “người dùng muốn hoàn thành việc gì?” thay vì chỉ bắt đầu từ danh sách bảng dữ liệu hoặc tên entity.

Ví dụ, “đặt đơn hàng” có thể bao gồm kiểm tra khách hàng, lấy thông tin và giá sản phẩm, tạo đơn hàng, lưu kết quả rồi trả về mã đơn hàng. Đây là một hành động của ứng dụng. Nó khác với thao tác CRUD chung chung như **saveOrder**, vốn chỉ mô tả kỹ thuật ghi một đối tượng.

Một use case thường có thể mô tả bằng cấu trúc sau:

| Thành phần | Câu hỏi cần trả lời | Ví dụ đặt hàng |
|---|---|---|
| Tác nhân | Ai yêu cầu thực hiện? | Khách hàng đã đăng nhập |
| Mục tiêu | Muốn đạt kết quả nào? | Tạo một đơn hàng hợp lệ |
| Đầu vào | Cần thông tin gì? | Khách hàng, sản phẩm, số lượng |
| Quy tắc | Điều kiện nào phải được giữ? | Khách hàng được phép đặt; số lượng dương |
| Kết quả | Ứng dụng trả lại điều gì? | Mã đơn hàng và tổng tiền |
| Thất bại | Điều gì có thể ngăn thao tác? | Không tìm thấy sản phẩm, khách hàng bị khóa |

Không phải mọi chức năng đều cần một tài liệu use case dài. Với chức năng nhỏ, một mô tả ngắn về mục tiêu, đầu vào, kết quả và quy tắc quan trọng đã đủ để định hướng thiết kế.

## 2. Application service đứng ở đâu trong kiến trúc phân tầng?

Trong cách phân tầng thường gặp, presentation nhận yêu cầu và trình bày kết quả; application điều phối ca sử dụng; domain mô hình hóa khái niệm và quy tắc nghiệp vụ; data access hoặc infrastructure kết nối cơ sở dữ liệu và dịch vụ bên ngoài. Số lượng layer và cách đặt interface có thể thay đổi theo quy mô, framework và quy tắc kiến trúc của dự án.

Application service có trách nhiệm:

1. Nhận dữ liệu đầu vào của ca sử dụng qua một hợp đồng ổn định.
2. Phối hợp việc lấy dữ liệu cần thiết từ repository hoặc cổng dịch vụ.
3. Gọi các hành vi của entity, aggregate hoặc domain service để áp dụng quy tắc nghiệp vụ.
4. Điều phối các bước tiếp theo theo kết quả của bước trước.
5. Xác định ranh giới giao dịch và phối hợp các tác động phụ thuộc vào hạ tầng.
6. Trả về kết quả phù hợp với ca sử dụng, không để presentation phải tự ghép nhiều thao tác.

Application service **không phải nơi chứa tất cả quy tắc nghiệp vụ**. Nó quyết định thứ tự và phạm vi phối hợp. Những bất biến như “mỗi dòng hàng phải có số lượng dương” hoặc “đơn hàng đã giao không thể bị hủy” nên được bảo vệ bởi mô hình domain, nơi có đủ ngữ cảnh để giữ trạng thái hợp lệ. Kiểm tra định dạng request như trường bắt buộc, chuỗi đúng mẫu hoặc JSON hợp lệ thường thuộc presentation hoặc ranh giới đầu vào của application.

Application service cũng không nên biết chi tiết HTTP, câu SQL, tên bảng hoặc cách một ORM ánh xạ entity. Những chi tiết đó thuộc presentation và infrastructure. Service có thể phụ thuộc vào interface hoặc port biểu đạt nhu cầu của use case, còn adapter cụ thể được cấu hình ở composition root.

### Phân biệt trách nhiệm giữa các layer

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| Presentation | Chuyển giao thức đầu vào thành yêu cầu của ứng dụng; định dạng phản hồi | Controller đọc JSON và trả HTTP 201 |
| Application | Điều phối một use case, ranh giới giao dịch và kết quả | Service đặt hàng, lưu đơn và trả mã đơn |
| Domain | Bảo vệ bất biến và thực hiện hành vi nghiệp vụ | **Order.place(...)**, **order.cancel()** |
| Infrastructure / Data access | Thực thi truy cập dữ liệu và tích hợp kỹ thuật | JPA adapter, HTTP client, message broker |

Một dự án nhỏ có thể gộp package hoặc lớp để giảm chi phí tổ chức. Dù vậy, trách nhiệm vẫn cần phân biệt được: ai tiếp nhận giao thức, ai điều phối công việc, ai sở hữu quy tắc nghiệp vụ và ai thực hiện thao tác kỹ thuật.

## 3. Thiết kế một application service theo use case

Xét use case đặt hàng. Người dùng gửi danh sách sản phẩm và số lượng. Ứng dụng cần xác nhận khách hàng tồn tại và được phép đặt hàng, lấy giá hiện tại của từng sản phẩm, tạo đơn hàng theo các quy tắc domain, lưu đơn rồi trả về mã đơn.

Một hợp đồng đầu vào có thể dùng command:

~~~java
public record PlaceOrderCommand(
        String customerId,
        List<OrderLineInput> lines
) {}

public record OrderLineInput(
        String productId,
        int quantity
) {}
~~~

Command chứa dữ liệu cần cho use case. Nó không phải entity JPA và không nên mang các chi tiết HTTP như **HttpServletRequest**. Đối tượng này có thể được tạo từ request DTO ở presentation.

Application service phụ thuộc vào các hợp đồng mà use case cần:

~~~java
public interface PlaceOrderUseCase {
    PlaceOrderResult handle(PlaceOrderCommand command);
}

public record PlaceOrderResult(
        String orderId,
        BigDecimal total
) {}

public interface CustomerRepository {
    Optional<Customer> findById(CustomerId id);
}

public interface ProductCatalog {
    ProductSnapshot getRequired(ProductId id);
}

public interface OrderRepository {
    void save(Order order);
}
~~~

Ví dụ service:

~~~java
@Service
public class PlaceOrderService implements PlaceOrderUseCase {
    private final CustomerRepository customers;
    private final ProductCatalog products;
    private final OrderRepository orders;

    public PlaceOrderService(
            CustomerRepository customers,
            ProductCatalog products,
            OrderRepository orders) {
        this.customers = customers;
        this.products = products;
        this.orders = orders;
    }

    @Override
    @Transactional
    public PlaceOrderResult handle(PlaceOrderCommand command) {
        CustomerId customerId = new CustomerId(command.customerId());
        Customer customer = customers.findById(customerId)
                .orElseThrow(() -> new CustomerNotFoundException(customerId));

        customer.ensureCanPlaceOrder();

        List<PricedOrderLine> lines = command.lines().stream()
                .map(input -> {
                    ProductId productId = new ProductId(input.productId());
                    ProductSnapshot product = products.getRequired(productId);
                    return new PricedOrderLine(
                            product.id(),
                            product.name(),
                            product.price(),
                            input.quantity());
                })
                .toList();

        Order order = Order.place(customer.id(), lines);
        orders.save(order);

        return new PlaceOrderResult(
                order.id().value(),
                order.total().amount());
    }
}
~~~

Đây là ví dụ minh họa; các kiểu **Customer**, **Order**, **ProductSnapshot**, value object và exception được giả định đã được định nghĩa trong các package tương ứng. Các interface repository và catalog có thể được đặt trong application hoặc domain tùy quy tắc phụ thuộc mà dự án lựa chọn. Điều quan trọng là application service dùng hợp đồng thể hiện nhu cầu của use case, không phụ thuộc trực tiếp vào adapter JPA hay client HTTP cụ thể.

Đoạn service trên điều phối việc lấy khách hàng, kiểm tra khả năng đặt hàng, lấy thông tin sản phẩm, yêu cầu domain tạo đơn hàng và lưu kết quả. Nó không tự tính tổng tiền bằng cách thao tác tùy tiện trên dữ liệu, cũng không tự gán trạng thái đơn hàng bằng một chuỗi. Những hành vi và bất biến thuộc về **Order** và các kiểu domain liên quan.

Ví dụ, domain có thể bảo vệ điều kiện của đơn hàng:

~~~java
public static Order place(
        CustomerId customerId,
        List<PricedOrderLine> lines) {
    if (lines == null || lines.isEmpty()) {
        throw new EmptyOrderException();
    }

    for (PricedOrderLine line : lines) {
        if (line.quantity() <= 0) {
            throw new InvalidOrderQuantityException();
        }
    }

    return new Order(
            OrderId.newId(),
            customerId,
            List.copyOf(lines),
            OrderStatus.NEW);
}
~~~

Như vậy, nếu một ca sử dụng khác cũng tạo đơn hàng, nó vẫn phải đi qua hành vi domain để giữ cùng bất biến. Không nên sao chép quy tắc số lượng hợp lệ vào nhiều application service.

## 4. Luồng xử lý từ request đến kết quả

Controller chỉ chuyển đổi dữ liệu giao thức và gọi use case:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final PlaceOrderUseCase placeOrder;

    public OrderController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> place(
            @Valid @RequestBody PlaceOrderRequest request) {
        PlaceOrderCommand command = new PlaceOrderCommand(
                request.customerId(),
                request.lines().stream()
                        .map(line -> new OrderLineInput(
                                line.productId(), line.quantity()))
                        .toList());

        PlaceOrderResult result = placeOrder.handle(command);
        URI location = URI.create("/orders/" + result.orderId());
        return ResponseEntity.created(location)
                .body(new OrderResponse(result.orderId(), result.total()));
    }
}
~~~

Luồng xử lý khái quát:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant P as OrderController
    participant A as PlaceOrderService
    participant C as CustomerRepository
    participant PC as ProductCatalog
    participant D as Order domain
    participant R as OrderRepository

    User->>P: POST /orders
    P->>A: handle(command)
    A->>C: findById(customerId)
    C-->>A: Customer
    A->>A: ensureCanPlaceOrder()
    loop Mỗi dòng hàng
        A->>PC: getRequired(productId)
        PC-->>A: ProductSnapshot
    end
    A->>D: Order.place(customerId, lines)
    D-->>A: Order
    A->>R: save(order)
    R-->>A: Hoàn tất
    A-->>P: PlaceOrderResult
    P-->>User: HTTP 201 + OrderResponse
~~~

Controller không cần biết phải gọi repository nào trước, cách lấy giá hay cách tạo aggregate. Nó biết hợp đồng **PlaceOrderUseCase** và chuyển kết quả sang định dạng HTTP. Nhờ đó, cùng một use case có thể được gọi từ REST API, giao diện dòng lệnh, message consumer hoặc một giao diện khác mà không phải sao chép toàn bộ luồng điều phối.

Trong hệ thống khách hàng tự đặt hàng, mã khách hàng nên được lấy từ danh tính đã xác thực (principal hoặc security context), không tin một trường tùy ý do client gửi lên. Trường **customerId** trong command biểu đạt dữ liệu mà use case cần; nguồn dữ liệu đó phải phù hợp với quyền của tác nhân. Nếu nghiệp vụ cho phép nhân viên tạo đơn thay khách hàng, quyền chọn khách hàng cần được kiểm tra theo chính sách tương ứng.

## 5. Đặt ranh giới giao dịch và tác động phụ

Application service thường là nơi phù hợp để xác định ranh giới giao dịch vì một use case có thể gồm nhiều thao tác đọc và ghi cần được xem như một đơn vị công việc. Với Spring, **@Transactional** trên phương thức application service là một cách phổ biến để biểu đạt ranh giới đó. Phạm vi thực tế còn phụ thuộc transaction manager, propagation, isolation và cách các adapter tham gia giao dịch.

Trong ví dụ đặt hàng, nếu việc đọc khách hàng, tạo đơn và ghi đơn dùng cùng một cơ sở dữ liệu, một transaction có thể bảo đảm các thao tác ghi liên quan cùng commit hoặc rollback. Tuy nhiên, không nên mặc định một transaction cơ sở dữ liệu có thể bao trùm một lời gọi HTTP đến cổng thanh toán hoặc một hệ thống khác. Giao dịch phân tán qua nhiều hệ thống có các rủi ro timeout, retry và kết quả không chắc chắn.

Đoạn mã đặt hàng giả định việc tra cứu **ProductCatalog** là thao tác đọc có thời gian đáp ứng phù hợp với transaction đang mở. Nếu port này gọi một dịch vụ từ xa, lời gọi HTTP không tự tham gia transaction cơ sở dữ liệu; cần cân nhắc thời gian giữ transaction, timeout, retry và tính nhất quán của giá. Có thể tách bước lấy dữ liệu từ xa khỏi transaction ghi, đồng thời lưu snapshot giá đã dùng để tạo đơn.

Khi use case cần phối hợp với hệ thống bên ngoài, có thể cân nhắc:

- Lưu trạng thái nghiệp vụ và một bản ghi outbox trong cùng transaction; một tiến trình khác gửi sự kiện từ outbox.
- Dùng saga hoặc quy trình bù trừ khi nhiều bước độc lập đã hoàn thành và một bước sau thất bại.
- Thiết kế thao tác có tính idempotent để retry không tạo ra đơn hàng hoặc khoản thanh toán trùng.
- Ghi nhận trạng thái trung gian rõ ràng thay vì giả định mọi bước hoàn tất tức thời.

Không phải use case nào cũng cần outbox hay saga. Chọn cơ chế theo ranh giới dữ liệu, yêu cầu nhất quán, độ tin cậy của hệ thống ngoài và mức độ phức tạp chấp nhận được.

## 6. Phân biệt validation, authorization và business rule

Các loại kiểm tra thường nằm ở những nơi khác nhau:

| Loại kiểm tra | Ví dụ | Vị trí phù hợp |
|---|---|---|
| Định dạng đầu vào | JSON thiếu trường, email sai định dạng, số lượng không phải số nguyên | Presentation hoặc lớp kiểm tra đầu vào |
| Quyền truy cập | Người gọi có quyền thao tác trên đơn hàng này không? | Security/presentation và application policy tùy cơ chế |
| Điều kiện nghiệp vụ | Đơn đã giao không thể hủy; khách hàng bị khóa không thể đặt | Domain, có thể được application phối hợp kiểm tra |
| Điều kiện phối hợp | Có tìm thấy khách hàng hoặc sản phẩm để tiếp tục use case không? | Application service và các port được gọi |

Phân chia này không có nghĩa một quy tắc chỉ được kiểm tra đúng một lần trong toàn hệ thống. Ranh giới đầu vào có thể kiểm tra sớm để trả lỗi dễ hiểu, trong khi domain vẫn phải bảo vệ bất biến để mọi caller đều không thể tạo trạng thái sai. Ví dụ, **@Min(1)** ở request DTO giúp phản hồi HTTP rõ ràng, nhưng **Order.place** vẫn cần bảo vệ số lượng dương vì domain có thể được gọi từ message consumer hoặc tác vụ nền.

Application service cũng có thể phối hợp kiểm tra quyền dựa trên danh tính hiện tại hoặc một authorization port. Nếu quyền phụ thuộc vào trạng thái nghiệp vụ, chẳng hạn chỉ người sở hữu đơn hàng mới được hủy, domain hoặc policy nghiệp vụ cần giữ điều kiện đó ở nơi có thể áp dụng nhất quán. Cần tránh để controller là nơi duy nhất bảo vệ một quy tắc mà nhiều luồng có thể gọi.

## 7. Thiết kế API theo use case thay vì CRUD tổng quát

Một application service thường dễ hiểu khi tên phương thức diễn tả hành động hoặc truy vấn mà caller muốn thực hiện:

- **PlaceOrder** — đặt đơn hàng.
- **CancelOrder** — hủy đơn hàng.
- **ConfirmPayment** — xác nhận thanh toán.
- **GetOrderDetails** — xem chi tiết đơn hàng.

Các tên này giúp lộ rõ mục tiêu, đầu vào và kết quả của từng thao tác. Không bắt buộc phải tạo một lớp riêng cho từng use case trong mọi dự án. Ứng dụng nhỏ có thể nhóm một số thao tác liên quan; hệ thống lớn có thể tách handler/service riêng để dễ phân quyền, kiểm thử và thay đổi. Tiêu chí là ranh giới của thao tác phải rõ ràng, không phải số lượng class.

Một **GenericCrudService<T>** có thể hữu ích cho thao tác dữ liệu thật sự đơn giản, nhưng thường không đủ để biểu đạt các ca sử dụng như hủy đơn, hoàn tiền hoặc xác nhận giao hàng. Những thao tác này có điều kiện, thay đổi trạng thái và tác động phụ riêng. Đẩy chúng thành **save(entity)** khiến caller phải biết quá nhiều về trình tự nghiệp vụ.

Với truy vấn chỉ đọc, application service có thể phối hợp repository hoặc query port rồi trả về read model phù hợp. Không cần tải cả aggregate nếu use case chỉ cần một số trường để hiển thị. Trong một số hệ thống, đường đọc và đường ghi có thể được tổ chức khác nhau (ví dụ CQRS); đây là lựa chọn thiết kế tùy nhu cầu, không phải yêu cầu bắt buộc của kiến trúc phân tầng.

## 8. Kiểm thử application service

Vì application service điều phối các hợp đồng, có thể kiểm thử nó bằng unit test với fake hoặc mock cho các port. Một số tình huống quan trọng của use case đặt hàng:

1. Khách hàng hợp lệ và sản phẩm tồn tại: domain được yêu cầu tạo đơn, repository nhận đơn để lưu và kết quả chứa đúng mã đơn.
2. Không tìm thấy khách hàng: service trả lỗi phù hợp và không gọi lưu đơn.
3. Khách hàng không đủ điều kiện đặt hàng: thao tác dừng trước khi tạo đơn.
4. Không tìm thấy một sản phẩm: use case thất bại theo hợp đồng đã chọn và không lưu đơn chưa hoàn chỉnh.
5. Domain từ chối dữ liệu vi phạm bất biến: lỗi được truyền hoặc chuyển đổi theo chính sách lỗi của application.

Ví dụ kiểm thử bằng Mockito có thể xác nhận tương tác quan trọng:

~~~java
@ExtendWith(MockitoExtension.class)
class PlaceOrderServiceTest {
    @Mock CustomerRepository customers;
    @Mock ProductCatalog products;
    @Mock OrderRepository orders;

    @InjectMocks PlaceOrderService service;

    @Test
    void savesOrderForEligibleCustomer() {
        Customer customer = Customer.active(new CustomerId("C-10"));
        when(customers.findById(new CustomerId("C-10")))
                .thenReturn(Optional.of(customer));
        when(products.getRequired(new ProductId("P-20")))
                .thenReturn(new ProductSnapshot(
                        new ProductId("P-20"), "Bàn phím", Money.of("50.00")));

        PlaceOrderResult result = service.handle(
                new PlaceOrderCommand(
                        "C-10",
                        List.of(new OrderLineInput("P-20", 2))));

        assertNotNull(result.orderId());
        verify(orders).save(any(Order.class));
    }
}
~~~

Đây là mã minh họa; constructor và factory của các kiểu domain cần được điều chỉnh theo mô hình thực tế. Unit test kiểm tra điều phối và kết quả ở application boundary. Cần có thêm integration test cho adapter persistence, cấu hình transaction và các tích hợp bên ngoài; mock không chứng minh được câu SQL, mapping hoặc transaction thực sự hoạt động.

## 9. Những dấu hiệu thiết kế chưa tốt

- **Controller chứa toàn bộ workflow:** controller truy vấn nhiều repository, tự kiểm tra trạng thái, thay đổi entity rồi lưu. Khi đó nhiều giao diện dễ sao chép luồng nghiệp vụ.
- **Application service trở thành “god service”:** một lớp xử lý quá nhiều use case không liên quan, chứa cả quy tắc domain và chi tiết kỹ thuật. Có thể tách theo mục tiêu hoặc nhóm năng lực.
- **Service chỉ chuyển tiếp vô nghĩa:** lớp application chỉ gọi một phương thức cùng tên trên một lớp khác mà không tạo ranh giới hay điều phối hữu ích. Hãy cân nhắc liệu abstraction đó có thực sự cần thiết.
- **Dùng CRUD để thay thế mọi hành động:** caller phải tự thực hiện nhiều thao tác theo đúng thứ tự, dễ bỏ sót quy tắc hoặc lưu trạng thái dở dang.
- **Application phụ thuộc trực tiếp framework hoặc adapter:** service dùng **HttpServletRequest**, **EntityManager** hoặc lớp JPA cụ thể khiến use case khó tái sử dụng và kiểm thử độc lập.
- **Đưa quy tắc nghiệp vụ vào DTO hoặc mapper:** mapper nên chuyển đổi dữ liệu; bất biến của đơn hàng phải được bảo vệ bởi domain.

## 10. Checklist khi thiết kế

Trước khi hoàn thành một application service, hãy tự kiểm tra:

- Tên và hợp đồng có diễn tả một mục tiêu hoặc truy vấn cụ thể không?
- Đầu vào có chứa đúng dữ liệu cần thiết, không mang phụ thuộc giao thức HTTP hay ORM không?
- Trình tự điều phối có rõ ràng và có xử lý các trường hợp thất bại quan trọng không?
- Quy tắc nghiệp vụ và bất biến có được giao cho domain bảo vệ không?
- Service có phụ thuộc vào abstraction cần thiết thay vì implementation hạ tầng không?
- Ranh giới transaction có bao phủ đúng các thao tác dữ liệu cần nhất quán không?
- Tác động phụ đến hệ thống ngoài có chính sách retry, idempotency hoặc bù trừ phù hợp không?
- Có thể kiểm thử use case mà không cần khởi động toàn bộ ứng dụng không?

Application service được thiết kế tốt khi nó thể hiện rõ một mục tiêu của người dùng, điều phối đủ các bước để đạt mục tiêu đó và giữ cho mỗi layer làm đúng phần việc của mình. Hãy dùng use case để định hình API của tầng ứng dụng, để domain bảo vệ quy tắc nghiệp vụ, và để infrastructure thực hiện các chi tiết kỹ thuật. Cách tổ chức cụ thể có thể thay đổi theo hệ thống; sự rõ ràng của mục tiêu, trách nhiệm và ranh giới mới là tiêu chí quan trọng.

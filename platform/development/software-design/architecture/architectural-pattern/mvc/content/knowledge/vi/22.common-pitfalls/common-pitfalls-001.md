# Controller chứa toàn bộ quy tắc nghiệp vụ

Trong module **MODEL_VIEW_CONTROLLER**, Controller là điểm tiếp nhận tương tác từ bên ngoài và điều phối request đến phần xử lý phù hợp. Với ứng dụng web, Controller thường làm việc với HTTP: nhận path/query parameter, binding form hoặc JSON, lấy danh tính đã xác thực, gọi use case và trả View hay response. Một sai lầm phổ biến là để Controller thực hiện luôn mọi quy tắc nghiệp vụ, truy vấn dữ liệu, cập nhật trạng thái, kiểm tra quyền và định dạng thông báo.

Khi đó, Controller trở thành nơi chứa gần như toàn bộ hành vi của ứng dụng. Lớp này phình to, khó kiểm thử, khó tái sử dụng qua nhiều giao diện và dễ tạo ra quy tắc không nhất quán giữa các endpoint. Cách tổ chức bền vững hơn là giữ Controller tập trung vào ranh giới HTTP, chuyển việc điều phối một hành động nghiệp vụ vào tầng ứng dụng (application service/use case), và đặt các bất biến cùng hành vi thuộc về đối tượng nghiệp vụ trong Model.

Một Controller mỏng không có nghĩa là Controller không làm gì. Nó vẫn phải chuyển đổi dữ liệu đầu vào, xử lý kết quả ở mức giao thức, chọn response và ánh xạ lỗi phù hợp. Điều cần tránh là để nó trở thành nơi quyết định nghiệp vụ của hệ thống.

## 1. Nhận biết Controller đang ôm quá nhiều trách nhiệm

Một Controller có thể bắt đầu đơn giản với vài handler. Theo thời gian, mỗi handler lại thêm một điều kiện, một truy vấn, một phép tính hoặc một thao tác cập nhật. Dấu hiệu thường gặp:

- Một phương thức handler có nhiều nhánh if/else mô tả trạng thái nghiệp vụ.
- Controller trực tiếp gọi nhiều repository để phối hợp một hành động.
- Controller tự tính giá, phí, hạn mức, trạng thái hoặc điều kiện được phép chuyển trạng thái.
- Cùng một quy tắc được lặp lại ở nhiều Controller hoặc endpoint.
- Controller tự mở transaction hoặc quản lý nhiều bước cập nhật dữ liệu.
- Controller chứa mã gửi email, phát sự kiện, gọi thanh toán hoặc tích hợp dịch vụ ngoài.
- Controller phải biết quá nhiều chi tiết của entity và quan hệ database.
- Unit test cho quy tắc nghiệp vụ buộc phải khởi tạo Spring MVC, request hoặc mock nhiều thành phần web.
- Thay đổi một quy tắc làm nhiều handler phải sửa theo.

Một handler dài chưa chắc đã sai nếu phần lớn mã chỉ là ánh xạ request/response. Ngược lại, một handler ngắn vẫn có thể sai trách nhiệm nếu nó tự quyết định một quy tắc quan trọng. Hãy xem nội dung mà Controller quyết định, thay vì chỉ đếm số dòng.

## 2. Ví dụ Controller phình to

Giả sử một endpoint tạo đơn hàng. Controller nhận request, tìm khách hàng và sản phẩm, kiểm tra trạng thái bán, tính tiền, kiểm tra hạn mức, tạo đơn, cập nhật tồn kho rồi gửi email:

~~~java
@PostMapping("/orders")
public String createOrder(
        @ModelAttribute OrderForm form,
        Authentication authentication,
        Model model) {

    User user = userRepository.findByUsername(authentication.getName())
            .orElseThrow();
    Product product = productRepository.findById(form.getProductId())
            .orElseThrow();

    if (!product.isActive()) {
        model.addAttribute("error", "Sản phẩm không còn được bán.");
        return "orders/new";
    }

    if (form.getQuantity() <= 0 || form.getQuantity() > product.getStock()) {
        model.addAttribute("error", "Số lượng không hợp lệ.");
        return "orders/new";
    }

    BigDecimal total = product.getPrice()
            .multiply(BigDecimal.valueOf(form.getQuantity()));

    if (total.compareTo(user.getCreditLimit()) > 0) {
        model.addAttribute("error", "Vượt hạn mức.");
        return "orders/new";
    }

    Order order = new Order(user, product, form.getQuantity(), total);
    orderRepository.save(order);
    product.decreaseStock(form.getQuantity());
    productRepository.save(product);
    emailService.sendOrderConfirmation(user, order);

    return "redirect:/orders/" + order.getId();
}
~~~

Đoạn mã có thể chạy trong một ứng dụng nhỏ, nhưng nhiều quyết định quan trọng đang gắn chặt với giao thức và framework web. Nếu một ứng dụng di động, API khác hoặc tác vụ nền cũng cần tạo đơn, chúng có thể phải sao chép các điều kiện này. Khi quy tắc thay đổi, các bản sao có thể không được cập nhật đồng bộ.

Ngoài ra, việc lưu đơn và giảm tồn kho cần có ranh giới transaction và xử lý đồng thời rõ ràng. Gửi email trong cùng luồng request cũng khiến độ trễ và lỗi của dịch vụ email ảnh hưởng trực tiếp đến response. Những vấn đề này thuộc thiết kế use case và hạ tầng ứng dụng, không nên giải quyết bằng cách thêm nhiều nhánh vào Controller.

## 3. Phân biệt trách nhiệm của các lớp

Một cách phân chia phổ biến trong ứng dụng MVC:

| Thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| Controller | Tiếp nhận HTTP, binding, lấy principal, gọi use case, chọn View/status/redirect | Nhận OrderForm và trả trang xác nhận |
| Request DTO/Form | Mô tả dữ liệu client được phép gửi và validation cấu trúc | productId, quantity, địa chỉ giao hàng |
| Application service / Use case | Điều phối một hành động nghiệp vụ, quản lý transaction, gọi domain và cổng phụ thuộc | CreateOrderUseCase |
| Domain Model | Bảo vệ bất biến và hành vi nghiệp vụ thuộc về đối tượng | Order xác nhận hoặc hủy đơn theo trạng thái |
| Domain service | Chứa quy tắc nghiệp vụ cần phối hợp nhiều đối tượng nhưng không thuộc tự nhiên về một entity | Chính sách định giá nhiều yếu tố |
| Repository | Cung cấp khả năng lưu và truy xuất aggregate/entity | Tìm sản phẩm, lưu đơn |
| View / Response DTO | Trình bày dữ liệu đã được chuẩn bị cho người nhận | OrderConfirmationView |

Không phải dự án nào cũng cần đủ mọi lớp. Một use case đơn giản có thể chỉ gọi một repository; một quy tắc nhỏ có thể nằm trực tiếp trong entity. Điều quan trọng là đặt quyết định vào nơi có đủ ngữ cảnh và trách nhiệm để bảo vệ nó.

## 4. Controller mỏng hơn sau khi tách use case

Controller chỉ xử lý đầu vào và đầu ra HTTP:

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
            @Valid @ModelAttribute("form") OrderForm form,
            BindingResult bindingResult,
            @AuthenticationPrincipal AppPrincipal principal,
            RedirectAttributes redirectAttributes) {

        if (bindingResult.hasErrors()) {
            return "orders/new";
        }

        OrderId orderId = createOrder.execute(
                principal.userId(),
                new CreateOrderCommand(form.productId(), form.quantity())
        );

        redirectAttributes.addFlashAttribute(
                "message", "Đơn hàng đã được tạo."
        );
        return "redirect:/orders/" + orderId.value();
    }
}
~~~

Controller vẫn thực hiện các việc thuộc HTTP: nhận form, kiểm tra lỗi binding/validation, lấy danh tính từ security context, chuyển dữ liệu sang command và chọn redirect. Nó không tự quyết định sản phẩm có được bán, giá tính thế nào hoặc tồn kho được trừ ra sao.

Use case điều phối hành động:

~~~java
public record CreateOrderCommand(long productId, int quantity) {}

public class CreateOrderUseCase {
    private final UserRepository users;
    private final ProductRepository products;
    private final OrderRepository orders;
    private final OrderPricing pricing;

    public CreateOrderUseCase(
            UserRepository users,
            ProductRepository products,
            OrderRepository orders,
            OrderPricing pricing) {
        this.users = users;
        this.products = products;
        this.orders = orders;
        this.pricing = pricing;
    }

    @Transactional
    public OrderId execute(UserId userId, CreateOrderCommand command) {
        User user = users.findById(userId)
                .orElseThrow(UserNotFoundException::new);
        Product product = products.findById(command.productId())
                .orElseThrow(ProductNotFoundException::new);

        Money total = pricing.calculate(product, user, command.quantity());
        Order order = Order.create(user, product, command.quantity(), total);
        product.reserve(command.quantity());
        Order savedOrder = orders.save(order);
        products.save(product);

        return savedOrder.id();
    }
}
~~~

Đây là ví dụ cấu trúc minh họa. Trong ứng dụng thực tế, kiểu ID, tiền tệ, transaction và cách xử lý cạnh tranh tồn kho cần phù hợp với domain và database. Use case giữ trình tự nghiệp vụ trong một nơi; entity hoặc domain service vẫn là nơi bảo vệ quy tắc cụ thể.

## 5. Đặt quy tắc vào đúng nơi: Application Service hay Domain Model?

Tách code khỏi Controller chưa đủ. Nếu chuyển tất cả điều kiện vào một service lớn, vấn đề chỉ đổi tên từ Fat Controller thành God Service.

Hãy phân biệt:

### Application service điều phối use case

Application service mô tả một hành động mà hệ thống cung cấp. Nó thường:

- Xác định dữ liệu cần tải.
- Gọi domain method hoặc domain service.
- Quản lý ranh giới transaction.
- Gọi repository và các cổng tích hợp.
- Điều phối sự kiện hoặc tác vụ phụ sau khi nghiệp vụ hoàn tất.
- Trả kết quả ở mức phù hợp với caller.

Application service thường không nên chứa mọi phép tính và điều kiện chi tiết của domain. Nó điều phối các đối tượng có trách nhiệm thực hiện quy tắc.

### Entity/Aggregate bảo vệ bất biến của chính nó

Ví dụ, đơn hàng chỉ được xác nhận khi đang ở trạng thái chờ:

~~~java
public class Order {
    private OrderStatus status;

    public void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new InvalidOrderStateException(
                    "Chỉ đơn hàng đang chờ mới được xác nhận."
            );
        }
        status = OrderStatus.CONFIRMED;
    }
}
~~~

Quy tắc này thuộc về Order vì nó bảo vệ trạng thái hợp lệ của chính đơn hàng. Nếu Controller tự kiểm tra trạng thái trước khi gọi setter, một caller khác có thể bỏ qua điều kiện đó.

### Domain service xử lý quy tắc liên quan nhiều đối tượng

Một số quy tắc không thuộc tự nhiên về một entity. Ví dụ, chính sách định giá phụ thuộc sản phẩm, phân khúc khách hàng, thời điểm và chương trình khuyến mại. Có thể biểu diễn bằng domain service hoặc policy:

~~~java
public interface OrderPricing {
    Money calculate(Product product, User customer, int quantity);
}
~~~

Domain service nên biểu diễn một quy tắc nghiệp vụ có ý nghĩa, không phải nơi gom các hàm tiện ích không liên quan.

## 6. Phân biệt validation đầu vào và quy tắc nghiệp vụ

Một lý do khiến Controller phình to là mọi loại kiểm tra đều được viết trong handler. Hãy tách ít nhất ba nhóm:

| Nhóm kiểm tra | Ví dụ | Vị trí phù hợp |
| --- | --- | --- |
| Cấu trúc/định dạng request | Trường bắt buộc, số lượng là số nguyên dương, email đúng định dạng | Request DTO, Bean Validation hoặc form validator |
| Quy tắc nghiệp vụ | Không thể đặt đơn khi sản phẩm ngừng bán; đơn đã giao không thể hủy | Domain Model, domain policy hoặc use case |
| Quyền truy cập | Người dùng chỉ xem hoặc sửa đơn thuộc phạm vi được phép | Security layer và use case/policy ở server |

Bean Validation giúp phát hiện dữ liệu đầu vào sai định dạng trước khi gọi use case:

~~~java
public record OrderForm(
        @NotNull Long productId,
        @NotNull @Positive Integer quantity
) {}
~~~

Nhưng @Positive không chứng minh số lượng còn trong kho. Trạng thái tồn kho có thể thay đổi sau khi form được hiển thị; use case/domain phải kiểm tra lại trong lúc xử lý. Tương tự, việc một form có productId hợp lệ không có nghĩa người dùng có quyền thao tác trên mọi sản phẩm.

Không đặt quy tắc nghiệp vụ quan trọng chỉ ở JavaScript hoặc HTML validation. Client có thể bị bỏ qua hoặc thay thế; server phải bảo vệ quy tắc.

## 7. Đặt ranh giới transaction tại use case

Controller thường không nên điều khiển transaction cho một quy trình nghiệp vụ. Ranh giới transaction phù hợp thường nằm ở application service/use case vì đây là nơi biết những thao tác dữ liệu nào cần nhất quán cùng nhau.

Ví dụ tạo đơn có thể cần:

1. Tải khách hàng và sản phẩm.
2. Xác minh điều kiện đặt hàng.
3. Giữ hoặc giảm tồn kho.
4. Tạo đơn hàng và các dòng đơn.
5. Ghi nhận sự kiện nghiệp vụ cần phát ra.

Nếu các thay đổi trong database phải thành công hoặc thất bại cùng nhau, use case có thể chạy trong transaction. Tuy nhiên, không nên giữ transaction mở trong lúc gọi dịch vụ ngoài chậm như email hoặc thanh toán. Với tích hợp cần độ bền, cân nhắc outbox hoặc quy trình saga phù hợp.

Khi nhiều request có thể đặt đơn cùng lúc, kiểm tra tồn kho đơn thuần trong Controller hoặc đọc rồi ghi không khóa có thể gây bán vượt số lượng. Cần cơ chế nhất quán phù hợp như cập nhật có điều kiện, optimistic/pessimistic locking hoặc reservation theo domain.

## 8. Xử lý lỗi mà không nhồi thêm nhánh vào Controller

Controller phình to thường có nhiều đoạn lặp để xử lý không tìm thấy dữ liệu, trạng thái không hợp lệ, lỗi quyền hoặc lỗi tích hợp. Có thể để use case phát ra các kết quả/lỗi nghiệp vụ có ý nghĩa, rồi ánh xạ chúng sang HTTP ở ranh giới web.

Ví dụ:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(ProductNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm."));
    }

    @ExceptionHandler(InvalidOrderStateException.class)
    ResponseEntity<ApiError> handleConflict(InvalidOrderStateException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "INVALID_ORDER_STATE",
                        "Đơn hàng không thể chuyển sang trạng thái này."
                ));
    }
}
~~~

Đối với HTML form, có thể dùng ControllerAdvice hoặc cơ chế xử lý lỗi theo form để trả trang phù hợp. Không nên biến mọi lỗi thành HTTP 200 hoặc hiển thị thông tin nội bộ như SQL, stack trace hay token. Mã lỗi và thông báo công khai cần ổn định, còn chi tiết kỹ thuật được ghi log có kiểm soát.

Không phải ngoại lệ nào cũng nên dùng cùng cách. Lỗi validation của form thường cần trả lại View với lỗi theo trường; lỗi không tìm thấy tài nguyên có thể là 404; xung đột trạng thái có thể là 409; lỗi hệ thống ngoài dự kiến cần được xử lý tập trung và ghi nhận.

## 9. Phân quyền không nên phụ thuộc vào giao diện hoặc Controller duy nhất

Controller là ranh giới thích hợp để yêu cầu xác thực và có thể áp dụng kiểm tra quyền theo endpoint. Tuy nhiên, một quy tắc truy cập tài nguyên quan trọng không nên chỉ tồn tại trong một nút bấm hoặc một handler duy nhất nếu cùng use case có thể được gọi từ API, job nền hoặc một adapter khác.

Ví dụ, thao tác xem đơn của người dùng hiện tại nên nhận UserId từ principal đã xác thực và truy vấn trong phạm vi đó:

~~~java
@GetMapping("/my/orders/{id}")
public OrderDetailView detail(
        @PathVariable long id,
        @AuthenticationPrincipal AppPrincipal principal) {
    return orderQuery.getForOwner(new OrderId(id), principal.userId());
}
~~~

Use case/query phải tiếp tục giới hạn dữ liệu theo chủ sở hữu hoặc tenant. Không tin ownerId do client gửi. Nếu một vai trò quản trị được phép xem đơn của người khác, đó là một chính sách riêng cần kiểm tra rõ.

## 10. Kiểm thử khi tách trách nhiệm

Khi nghiệp vụ nằm trong Controller, test thường phải dựng request context, mock repository và xác minh nhiều chi tiết framework. Sau khi tách use case và domain behavior, có thể kiểm thử từng lớp theo trách nhiệm:

| Loại test | Điều cần xác minh |
| --- | --- |
| Unit test domain | Bất biến, chuyển trạng thái và phép tính nghiệp vụ |
| Unit test use case | Trình tự điều phối, gọi repository/gateway và kết quả |
| Controller test | Route, binding, validation, principal, status, redirect và ViewModel |
| Repository/integration test | Truy vấn, transaction và cập nhật dữ liệu thực |
| End-to-end test | Luồng người dùng qua giao diện và các thành phần chính |

Ví dụ unit test cho bất biến của Order:

~~~java
@Test
void deliveredOrderCannotBeCancelled() {
    Order order = OrderFixture.delivered();

    assertThrows(
            InvalidOrderStateException.class,
            order::cancel
    );
}
~~~

Ví dụ này kiểm tra quy tắc mà không cần khởi tạo Spring MVC. Một test Controller riêng có thể xác nhận POST hợp lệ gọi use case với user ID lấy từ principal và command được tạo từ form.

Không nên chỉ kiểm tra rằng Controller gọi một service. Hãy kiểm tra hành vi và kết quả ở lớp sở hữu quy tắc, ví dụ tồn kho không âm, đơn không chuyển trạng thái sai hoặc người dùng không thể xem tài nguyên ngoài phạm vi.

## 11. Refactor Controller lớn theo từng bước

Không cần viết lại toàn bộ module cùng lúc. Có thể refactor dần theo luồng:

1. **Khoanh vùng một use case:** chọn handler có nhiều nhánh nghiệp vụ hoặc được nhiều endpoint cần dùng.
2. **Ghi lại hành vi hiện tại:** đầu vào, quyền, điều kiện, thay đổi dữ liệu, lỗi và response.
3. **Tách request DTO/form:** chỉ giữ các trường mà client được phép gửi.
4. **Tạo command/query rõ ràng:** biểu diễn hành động mà tầng ứng dụng cần thực hiện.
5. **Chuyển điều phối sang use case:** tải dữ liệu, gọi domain behavior, quản lý transaction và trả kết quả.
6. **Chuyển bất biến về Model:** để entity/domain policy tự bảo vệ trạng thái hợp lệ.
7. **Giữ Controller làm adapter HTTP:** binding, lấy principal, gọi use case và ánh xạ response.
8. **Bổ sung test theo ranh giới:** unit test domain/use case và controller test cho giao thức.
9. **Xóa mã cũ:** bỏ truy vấn, phép tính và nhánh nghiệp vụ đã chuyển để không duy trì hai nguồn quy tắc.
10. **Lặp lại với use case tiếp theo:** chỉ tách thêm lớp khi có trách nhiệm rõ.

Một cách an toàn là giữ nguyên route và response contract trong lần refactor đầu. Như vậy, thay đổi tập trung vào cấu trúc bên trong và có thể so sánh hành vi trước/sau dễ hơn.

## 12. Ví dụ cấu trúc thư mục theo use case

Một cấu trúc đơn giản có thể tổ chức theo chức năng:

~~~text
orders/
  web/
    OrderController.java
    OrderForm.java
    OrderViewMapper.java
  application/
    CreateOrderUseCase.java
    CreateOrderCommand.java
    GetOrderQuery.java
  domain/
    Order.java
    OrderItem.java
    OrderPricing.java
    InvalidOrderStateException.java
  persistence/
    JpaOrderRepository.java
~~~

Tên và cách chia package phụ thuộc quy mô dự án. Dự án nhỏ có thể không cần nhiều package con; dự án lớn có thể chia theo bounded context hoặc feature. Điều cần duy trì là hướng phụ thuộc: lớp web biết application contract; application điều phối domain và port; domain không phụ thuộc Spring MVC, HTTP hoặc template engine.

## 13. Những cách sửa sai thường gặp

| Cách sửa | Vấn đề có thể phát sinh | Cách làm phù hợp |
| --- | --- | --- |
| Chuyển toàn bộ mã Controller sang một service lớn | Chỉ đổi tên lớp, service vẫn ôm mọi trách nhiệm | Chia use case và domain behavior theo trách nhiệm |
| Tạo một service cho mỗi dòng code | Quá nhiều lớp chuyển tiếp, khó lần theo luồng | Tách khi có ranh giới nghiệp vụ hoặc lý do kiểm thử/tái sử dụng rõ |
| Đưa mọi quy tắc vào entity | Entity có thể phụ thuộc dịch vụ ngoài hoặc phối hợp quá nhiều aggregate | Dùng application/domain service cho quy tắc phù hợp |
| Đưa validation vào Controller hết | Quy tắc bị trùng và không áp dụng cho caller khác | Tách request validation khỏi domain invariants |
| Để View quyết định quyền | Có thể bị bỏ qua bằng request trực tiếp | Kiểm tra authorization phía server |
| Dùng repository trực tiếp ở mọi handler | Quy trình dữ liệu bị phân tán | Use case điều phối truy cập dữ liệu |
| Giữ transaction trong Controller | Ranh giới nghiệp vụ khó tái sử dụng và kiểm thử | Đặt transaction theo use case |
| Bắt mọi exception rồi trả trang lỗi chung | Mất ngữ nghĩa lỗi và che lỗi lập trình | Ánh xạ lỗi có chủ đích ở adapter |

## 14. Checklist nhận diện Controller mỏng và rõ trách nhiệm

Khi review một Controller, có thể tự hỏi:

- Handler có chủ yếu nhận dữ liệu, gọi một use case và tạo response không?
- Dữ liệu đầu vào có form object/DTO riêng thay vì bind thẳng vào entity không?
- Danh tính người dùng được lấy từ security context đã xác thực không?
- Quy tắc nghiệp vụ có thể được gọi từ một adapter khác mà không sao chép không?
- Domain Model có tự bảo vệ các chuyển trạng thái và bất biến quan trọng không?
- Transaction có nằm ở ranh giới use case thích hợp không?
- Lỗi nghiệp vụ có thể được ánh xạ sang HTTP/View mà không lặp ở mọi handler không?
- Unit test cho quy tắc nghiệp vụ có chạy mà không cần web framework không?
- Controller có tránh phụ thuộc trực tiếp vào quá nhiều repository và dịch vụ ngoài không?
- Việc tách lớp có làm luồng xử lý rõ hơn, hay chỉ thêm các lớp chuyển tiếp?

Không cần ép mọi Controller chỉ có đúng một lời gọi. Một handler có thể phối hợp vài thao tác giao thức như binding, flash message, redirect hoặc tạo header. Tiêu chí là quy tắc nghiệp vụ có một nơi sở hữu rõ ràng và có thể kiểm thử độc lập.

## 15. Quy trình thiết kế một request MVC có ranh giới rõ

Khi triển khai một chức năng mới, hãy đi theo luồng:

1. Xác định request và response contract.
2. Xác định dữ liệu client được phép gửi và tạo DTO/form phù hợp.
3. Xác thực request, lấy principal và kiểm tra quyền ở server.
4. Chuyển dữ liệu thành command hoặc query có ý nghĩa nghiệp vụ.
5. Gọi use case để điều phối quy trình.
6. Để Model/domain policy bảo vệ bất biến và thực hiện hành vi nghiệp vụ.
7. Dùng repository và gateway qua ranh giới ứng dụng đã định.
8. Quản lý transaction và side effect tại use case.
9. Ánh xạ kết quả/lỗi thành ViewModel hoặc response DTO ở adapter web.
10. Kiểm thử domain, use case, Controller và luồng tích hợp theo đúng trách nhiệm.

Với cách tổ chức này, Controller vẫn là cửa vào của ứng dụng MVC nhưng không trở thành nơi duy nhất hiểu nghiệp vụ. Tầng ứng dụng có thể phục vụ nhiều adapter; Model bảo vệ quy tắc; View chỉ nhận dữ liệu phù hợp để trình bày.

## Kết luận

Controller chứa toàn bộ quy tắc nghiệp vụ khiến ứng dụng khó thay đổi, khó kiểm thử và dễ có hành vi không nhất quán giữa các endpoint. Hãy giữ Controller ở vai trò adapter HTTP: nhận và kiểm tra cấu trúc request, lấy danh tính đã xác thực, gọi use case rồi trả View hoặc response. Tầng ứng dụng điều phối hành động và transaction; Model hoặc domain policy bảo vệ bất biến; repository quản lý truy cập dữ liệu. Tách trách nhiệm theo use case và kiểm thử ở đúng ranh giới giúp ứng dụng MVC dễ bảo trì mà không tạo thêm lớp một cách máy móc.

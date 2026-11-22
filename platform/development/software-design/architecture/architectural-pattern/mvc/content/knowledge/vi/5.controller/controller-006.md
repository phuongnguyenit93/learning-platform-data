# Phân biệt điều phối và thực thi quy tắc nghiệp vụ

Trong mô hình **Model–View–Controller (MVC)**, Controller tiếp nhận tương tác từ người dùng, chuyển dữ liệu request thành đầu vào phù hợp, gọi chức năng cần thiết và chọn phản hồi cho View hoặc client. Controller có trách nhiệm điều phối luồng HTTP, nhưng không nên trở thành nơi quyết định mọi quy tắc của ứng dụng.

Một điểm dễ nhầm là Controller thường chứa các câu lệnh điều kiện, gọi nhiều dịch vụ và xử lý nhiều nhánh kết quả. Nhìn bề ngoài, những thao tác đó có thể giống như đang thực thi nghiệp vụ. Cần phân biệt hai việc:

- **Điều phối** là sắp xếp thứ tự gọi các thành phần, chuyển dữ liệu giữa chúng, chọn nhánh xử lý và chuyển kết quả thành phản hồi phù hợp.
- **Thực thi quy tắc nghiệp vụ** là xác định điều gì được phép xảy ra, điều kiện nào phải thỏa mãn, giá trị nào là hợp lệ và trạng thái nào được phép thay đổi.

Ví dụ, Controller nhận request tạo đơn hàng, kiểm tra dữ liệu biểu mẫu có đúng định dạng, gọi dịch vụ tạo đơn và chuyển hướng đến trang chi tiết. Nhưng việc khách hàng có được mua sản phẩm không, giá cuối cùng là bao nhiêu, mã giảm giá có hợp lệ không và tồn kho được cập nhật thế nào là các quyết định nghiệp vụ.

Bài học này làm rõ ranh giới đó trong ứng dụng web Java, từ cách tổ chức Controller, application service và Model đến xử lý biểu mẫu, lỗi, quyền truy cập, giao dịch và kiểm thử.

## 1. Hai loại công việc có mục đích khác nhau

### 1.1. Điều phối request và phản hồi

Controller làm việc ở ranh giới giao tiếp giữa client và ứng dụng. Các trách nhiệm thường gặp gồm:

- Ánh xạ URL và phương thức HTTP đến thao tác phù hợp.
- Nhận tham số đường dẫn, query parameter, header hoặc body.
- Binding dữ liệu request vào form object hoặc DTO.
- Kiểm tra định dạng đầu vào ở ranh giới request.
- Lấy danh tính đã xác thực từ ngữ cảnh bảo mật.
- Chuyển dữ liệu thành command hoặc tham số có ý nghĩa với use case.
- Gọi application service hoặc chức năng nghiệp vụ phù hợp.
- Chuyển kết quả thành view model, HTTP status, JSON hoặc redirect.
- Ánh xạ lỗi phù hợp với giao thức và trải nghiệm của client.

Những công việc này trả lời câu hỏi: **Request này cần được tiếp nhận, chuyển đến đâu và phản hồi bằng cách nào?**

### 1.2. Thực thi quy tắc nghiệp vụ

Quy tắc nghiệp vụ thuộc về Model, domain object, domain service hoặc thành phần nghiệp vụ mà ứng dụng sử dụng. Ví dụ:

- Chỉ cho phép hủy đơn khi đơn đang ở trạng thái có thể hủy.
- Không cho phép đặt số lượng lớn hơn số lượng có thể cung cấp.
- Áp dụng mã giảm giá theo điều kiện, thời hạn và giới hạn của chính sách.
- Tính thuế và tổng tiền theo quy tắc tài chính.
- Chỉ cho phép chuyển trạng thái thanh toán theo các trạng thái hợp lệ.
- Xác định khách hàng có đủ điều kiện nhận quyền lợi hay không.

Những công việc này trả lời câu hỏi: **Ứng dụng có cho phép hành động này không và kết quả đúng theo quy tắc là gì?**

| Tiêu chí | Điều phối | Thực thi quy tắc nghiệp vụ |
|---|---|---|
| Mục tiêu | Kết nối request, use case và phản hồi | Bảo vệ quy tắc và trạng thái của ứng dụng |
| Dữ liệu quan tâm | URL, HTTP method, header, request DTO, response | Trạng thái miền nghiệp vụ, chính sách và dữ liệu liên quan |
| Quyết định điển hình | Chọn service, view, redirect hoặc HTTP status | Hành động có hợp lệ không, giá trị nào phải được tính |
| Phụ thuộc phù hợp | Framework web, hợp đồng request/response, application service | Domain object, policy và các cổng truy cập dữ liệu cần thiết |
| Cách kiểm thử | Request được bind, service được gọi, phản hồi được chọn đúng | Quy tắc đúng với các trạng thái và dữ liệu đầu vào khác nhau |

Một câu lệnh `if` không tự động là quy tắc nghiệp vụ. Ví dụ, `if (errors.hasErrors()) return "orders/new";` là điều phối lỗi biểu mẫu. Nhưng `if (order.getStatus() == CANCELLED) ...` để quyết định có cho phép hủy đơn hay không là quy tắc nghiệp vụ, dù nó chỉ có một điều kiện.

## 2. Phân biệt Controller và application service

Trong ứng dụng MVC, Controller và application service có thể cùng tham gia điều phối nhưng ở hai phạm vi khác nhau.

- **Controller điều phối giao tiếp web:** nhận request, chuyển đổi dữ liệu, gọi use case và chọn phản hồi HTTP hoặc View.
- **Application service điều phối use case:** phối hợp các bước nghiệp vụ cần thiết, gọi domain object, repository hoặc cổng dịch vụ, quản lý phạm vi giao dịch theo thiết kế.
- **Domain model thực thi quy tắc:** bảo vệ bất biến, kiểm tra điều kiện và quyết định hành vi nghiệp vụ.

Application service không phải là một vai trò thứ tư của MVC. Đây là cách tổ chức tầng ứng dụng thường dùng để Controller không phải tự điều phối nhiều bước nghiệp vụ. Trong ứng dụng nhỏ, một số bước có thể được thực hiện trực tiếp bởi domain object; không cần tạo service nếu nó không làm rõ trách nhiệm.

~~~mermaid
flowchart TD
    U[Client / Trình duyệt] --> C[Controller]
    C -->|Command| A[Application Service]
    A --> D[Domain Model / Policy]
    A <--> R[Repository]
    D -->|Kết quả nghiệp vụ| A
    A -->|Use case result| C
    C -->|View model / HTTP response| V[View hoặc Client]
~~~

Ví dụ với thao tác hủy đơn:

1. Controller nhận `POST /orders/{id}/cancel`.
2. Controller lấy người dùng đã xác thực, tạo command và gọi `CancelOrderService`.
3. Application service tải đơn hàng và phối hợp thao tác hủy.
4. Domain model kiểm tra trạng thái hiện tại có cho phép hủy hay không.
5. Repository lưu trạng thái mới trong phạm vi giao dịch phù hợp.
6. Controller nhận kết quả và chuyển hướng đến trang chi tiết hoặc trả JSON.

Controller biết đây là request POST và cần redirect. Domain model biết trạng thái nào có thể hủy. Mỗi phần trả lời một loại câu hỏi khác nhau.

## 3. Dấu hiệu Controller đang thực thi nghiệp vụ

Controller có thể cần vài dòng điều kiện để xử lý request. Nhưng nếu nó trở thành nơi sở hữu chính sách hoặc bất biến của ứng dụng, ranh giới đã bị mờ.

### 3.1. Controller tự tính giá hoặc quyền lợi

Ví dụ không phù hợp:

~~~java
@PostMapping("/orders")
public String create(OrderForm form) {
    Product product = productRepository.findById(form.getProductId())
            .orElseThrow();

    BigDecimal total = product.getPrice()
            .multiply(BigDecimal.valueOf(form.getQuantity()));

    if ("SAVE10".equals(form.getCouponCode())) {
        total = total.multiply(new BigDecimal("0.90"));
    }

    Order order = new Order(product, form.getQuantity(), total);
    orderRepository.save(order);
    return "redirect:/orders/" + order.getId();
}
~~~

Controller vừa truy cập dữ liệu, vừa tính giá, áp dụng mã giảm giá, tạo trạng thái đơn và lưu dữ liệu. Nếu API hoặc tác vụ nền cũng tạo đơn, chúng có thể phải sao chép công thức.

### 3.2. Controller tự quyết định chuyển trạng thái

~~~java
if (order.getStatus() == OrderStatus.PENDING) {
    order.setStatus(OrderStatus.CANCELLED);
    orderRepository.save(order);
}
~~~

Nếu quy tắc hủy đơn chỉ nằm trong Controller, một điểm vào khác có thể thay đổi trạng thái mà không tuân theo cùng điều kiện. Quy tắc nên được bảo vệ trong hành vi của domain object hoặc dịch vụ nghiệp vụ.

### 3.3. Controller truy cập sâu vào lưu trữ

Các dấu hiệu thường gặp:

- Controller tự viết SQL hoặc xây dựng câu truy vấn phức tạp.
- Controller mở connection và tự quản lý transaction cho một use case.
- Controller biết chi tiết bảng, quan hệ ORM hoặc cơ chế lưu trữ.
- Nhiều Controller lặp lại cùng một chuỗi truy vấn và cập nhật.

Truy cập dữ liệu thường nên đi qua repository hoặc một abstraction phù hợp. Application service điều phối use case và transaction; repository xử lý việc đọc/ghi. Không phải ứng dụng nào cũng cần repository riêng nếu framework đã cung cấp một abstraction phù hợp, nhưng Controller không nên bị buộc vào chi tiết lưu trữ.

### 3.4. Controller chứa nhiều nhánh quy tắc

Một phương thức Controller dài với nhiều nhánh theo loại khách hàng, trạng thái đơn, chính sách giảm giá, khu vực giao hàng và phương thức thanh toán là dấu hiệu cần điều tra. Một số nhánh có thể là điều phối, nhưng các điều kiện quyết định quyền lợi hoặc trạng thái thường thuộc nghiệp vụ.

### 3.5. Controller khó kiểm thử nếu thiếu toàn bộ hạ tầng

Nếu muốn kiểm tra một quy tắc tính phí nhưng phải khởi động web server, session, cơ sở dữ liệu và template engine, có thể quy tắc đã bị gắn vào ranh giới web. Quy tắc nên có thể được kiểm tra bằng đầu vào và trạng thái miền nghiệp vụ.

## 4. Những điều kiện được phép xử lý trong Controller

Không nên hiểu ranh giới này theo cách cực đoan rằng Controller không được có bất kỳ điều kiện nào. Controller cần kiểm tra một số điều kiện để quản lý giao tiếp.

| Điều kiện hoặc thao tác | Thường thuộc Controller | Lý do |
|---|---:|---|
| Request thiếu tham số bắt buộc hoặc sai định dạng | Có | Kiểm tra hợp đồng đầu vào |
| Binding lỗi, số lượng không chuyển được thành số nguyên | Có | Lỗi tiếp nhận dữ liệu |
| Chọn View khi biểu mẫu có lỗi | Có | Điều phối phản hồi |
| Chọn redirect sau khi tạo đơn thành công | Có | Điều phối luồng HTTP |
| Ánh xạ lỗi nghiệp vụ thành trang lỗi hoặc HTTP status | Có | Chuyển kết quả sang giao thức |
| Số lượng phải lớn hơn 0 theo quy tắc đặt hàng | Nghiệp vụ cần bảo vệ | Đây là điều kiện của hành động tạo đơn |
| Số lượng không được vượt tồn kho khả dụng | Nghiệp vụ | Phụ thuộc trạng thái tồn kho |
| Mã giảm giá còn hiệu lực và áp dụng được | Nghiệp vụ | Phụ thuộc chính sách và thời hạn |
| Đơn hàng chỉ được hủy ở một số trạng thái | Nghiệp vụ | Bảo vệ vòng đời đơn hàng |
| Tổng tiền phải được tính theo chính sách thuế | Nghiệp vụ | Ảnh hưởng nghĩa vụ tài chính |

Một quy tắc có thể được kiểm tra sớm ở nhiều tầng để cải thiện trải nghiệm, nhưng phải có nơi nghiệp vụ chịu trách nhiệm cuối cùng. Ví dụ, form validation có thể từ chối số lượng bằng 0, nhưng Model vẫn phải bảo vệ điều kiện số lượng hợp lệ vì use case có thể được gọi từ API hoặc tác vụ nền.

## 5. Ví dụ tốt: Controller điều phối, nghiệp vụ quyết định

Ta có thể chia chức năng tạo đơn hàng thành form object, command, Controller, application service và domain model. Đây là ví dụ theo phong cách Spring MVC; các lớp và annotation cần được điều chỉnh theo phiên bản framework thực tế.

### 5.1. Form object xác định hợp đồng của biểu mẫu

~~~java
public class CreateOrderForm {
    @NotBlank
    private String productId;

    @NotNull
    @Positive
    private Integer quantity;

    private String couponCode;

    // Getter và setter
}
~~~

Form object mô tả dữ liệu client được phép gửi. Binding và validation có thể phát hiện trường thiếu, sai kiểu hoặc số lượng không dương trước khi gọi use case. Không nên bind trực tiếp mọi trường của entity đơn hàng từ client vì client có thể gửi các trường như giá, trạng thái, người tạo hoặc quyền hạn mà họ không được phép quyết định.

### 5.2. Command mô tả ý định nghiệp vụ

~~~java
public record CreateOrderCommand(
        String customerId,
        String productId,
        int quantity,
        String couponCode
) {}
~~~

Command không mang chi tiết HTTP. Nó mô tả thông tin cần thiết để thực hiện use case tạo đơn hàng. `customerId` được lấy từ danh tính đã xác thực ở máy chủ, không tin một giá trị tùy ý do biểu mẫu gửi lên.

### 5.3. Controller tiếp nhận, gọi và phản hồi

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
            @AuthenticationPrincipal CurrentUser currentUser
    ) {
        if (errors.hasErrors()) {
            return "orders/new";
        }

        CreateOrderCommand command = new CreateOrderCommand(
                currentUser.customerId(),
                form.getProductId(),
                form.getQuantity(),
                form.getCouponCode()
        );

        OrderReceipt receipt = createOrderService.create(command);
        return "redirect:/orders/" + receipt.orderId();
    }
}
~~~

Controller thực hiện các việc thuộc ranh giới web:

- Nhận form và kiểm tra lỗi binding/validation.
- Lấy danh tính người dùng từ ngữ cảnh xác thực.
- Chuyển form thành command.
- Gọi use case tạo đơn.
- Chọn URL chuyển hướng sau khi thành công.

Controller không tự tính giá, kiểm tra mã giảm giá hoặc cập nhật tồn kho. Nếu có lỗi nghiệp vụ, nó có thể được ánh xạ thành thông báo phù hợp bằng exception handler hoặc cơ chế xử lý lỗi của ứng dụng.

Trong Spring MVC, `BindingResult` cần đặt ngay sau tham số được kiểm tra bằng `@Valid` hoặc `@Validated` để nhận lỗi binding tương ứng. Ví dụ trên giả định người dùng đã được xác thực và `CurrentUser` là principal do ứng dụng cung cấp.

### 5.4. Application service điều phối use case

~~~java
@Service
public class CreateOrderService {
    private final ProductRepository products;
    private final OrderRepository orders;
    private final PricingPolicy pricingPolicy;

    public CreateOrderService(
            ProductRepository products,
            OrderRepository orders,
            PricingPolicy pricingPolicy
    ) {
        this.products = products;
        this.orders = orders;
        this.pricingPolicy = pricingPolicy;
    }

    @Transactional
    public OrderReceipt create(CreateOrderCommand command) {
        Product product = products.getRequired(command.productId());
        product.reserve(command.quantity());

        Money total = pricingPolicy.calculate(
                product,
                command.quantity(),
                command.couponCode()
        );

        Order order = Order.create(
                command.customerId(),
                product,
                command.quantity(),
                total
        );

        products.save(product);
        orders.save(order);
        return new OrderReceipt(order.getId());
    }
}
~~~

Application service điều phối các bước của use case: tải sản phẩm, gọi chính sách giá, tạo đơn và lưu đơn trong transaction. Nó không nên trở thành một lớp tiện ích chứa mọi quy tắc. Những bất biến thuộc về đơn hàng hoặc sản phẩm nên được domain object bảo vệ; chính sách độc lập có thể được biểu diễn bằng domain service hoặc policy.

Trong ví dụ này, `product.reserve(quantity)` là hành vi nghiệp vụ của sản phẩm: nó phải từ chối số lượng không hợp lệ hoặc vượt lượng có thể cung cấp và cập nhật lượng hàng được giữ. Khi nhiều request có thể giữ cùng một sản phẩm đồng thời, repository cần hỗ trợ khóa hoặc cập nhật có điều kiện/version để tránh hai giao dịch cùng đọc một lượng tồn rồi cùng đặt vượt tồn kho.

Annotation `@Transactional` trong ví dụ minh họa ranh giới giao dịch. Cách cấu hình transaction thực tế phụ thuộc framework, kho dữ liệu và các thao tác cần nhất quán. Nếu có giữ tồn kho đồng thời, chỉ đọc số lượng rồi mới lưu đơn có thể gặp race condition; cần cơ chế cập nhật nguyên tử, khóa hoặc chiến lược nhất quán phù hợp.

### 5.5. Domain model thực thi quy tắc

~~~java
public class Order {
    private OrderStatus status;

    public void cancel() {
        if (status != OrderStatus.PENDING) {
            throw new OrderRuleViolation(
                    "Only pending orders can be cancelled"
            );
        }

        status = OrderStatus.CANCELLED;
    }
}
~~~

Quy tắc hủy đơn được đặt tại nơi sở hữu trạng thái đơn hàng. Controller không cần biết mọi chi tiết về vòng đời đơn; nó chỉ gọi use case. Application service tải entity, gọi `order.cancel()` và lưu kết quả trong transaction phù hợp.

## 6. Điều phối nhiều bước mà không biến Controller thành nơi chứa nghiệp vụ

Một use case có thể cần phối hợp nhiều bước. Ví dụ xác nhận đơn hàng có thể:

1. Tải đơn hàng.
2. Kiểm tra người yêu cầu có quyền thao tác trên đơn.
3. Kiểm tra điều kiện xác nhận.
4. Giữ tồn kho hoặc xác nhận thanh toán.
5. Chuyển trạng thái đơn.
6. Lưu thay đổi và phát sự kiện.

Các bước này không nhất thiết nằm trong Controller. Controller chỉ nhận yêu cầu và gọi một use case như `ConfirmOrderService.confirm(command)`. Application service sắp xếp các cộng tác cần thiết; domain object hoặc policy quyết định điều kiện nghiệp vụ.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant C as OrderController
    participant A as ConfirmOrderService
    participant O as Order Model
    participant P as Payment Gateway
    participant R as OrderRepository

    User->>C: POST /orders/{id}/confirm
    C->>C: Kiểm tra request và lấy principal
    C->>A: confirm(command)
    A->>R: Tải đơn hàng
    R-->>A: Order
    A->>O: Kiểm tra / xác nhận trạng thái
    O-->>A: Kết quả quy tắc
    A->>P: Xác nhận thanh toán (nếu use case yêu cầu)
    P-->>A: Kết quả thanh toán
    A->>R: Lưu thay đổi
    A-->>C: Kết quả use case
    C-->>User: Redirect hoặc HTTP response
~~~

Sơ đồ là một ví dụ khái quát. Trong hệ thống thực tế, không nên giữ transaction cơ sở dữ liệu mở trong thời gian dài chỉ để chờ một dịch vụ bên ngoài. Thanh toán, phát sự kiện và cập nhật trạng thái có thể cần thiết kế nhất quán riêng như outbox, saga hoặc quy trình bù trừ tùy yêu cầu. Điểm quan trọng của bài học là Controller không nên tự chứa chuỗi chính sách nghiệp vụ này.

## 7. Xử lý lỗi: Controller ánh xạ, nghiệp vụ phát hiện

Lỗi có nhiều nguồn và không nên trộn chúng thành một loại.

| Loại lỗi | Ví dụ | Nơi phát hiện chính | Phản hồi có thể có |
|---|---|---|---|
| Binding / định dạng | Số lượng không phải số nguyên | Ranh giới request, Controller | Trả biểu mẫu với lỗi hoặc HTTP 400 |
| Validation đầu vào | Thiếu mã sản phẩm, số lượng không dương | Form DTO và validation | Trả biểu mẫu hoặc HTTP 400 |
| Quy tắc nghiệp vụ | Đơn đã giao nên không thể hủy | Model / domain service | Thông báo nghiệp vụ hoặc HTTP 409 |
| Không tìm thấy tài nguyên | Không có đơn hàng với ID đã gửi | Application service / repository | HTTP 404 hoặc trang không tìm thấy |
| Không đủ quyền | Người dùng không được xem đơn này | Cơ chế phân quyền / use case | HTTP 403 hoặc phản hồi phù hợp |
| Lỗi kỹ thuật | Cơ sở dữ liệu không khả dụng | Hạ tầng | HTTP 500 với thông báo an toàn và log nội bộ |

Model hoặc dịch vụ nghiệp vụ có thể trả về kết quả thất bại hoặc ném exception mang ý nghĩa nghiệp vụ. Controller hoặc exception handler chuyển kết quả đó thành phản hồi theo giao thức. Không nên để Model trả trực tiếp `HttpServletResponse`, mã HTTP hoặc HTML.

Ví dụ ánh xạ lỗi tập trung:

~~~java
@ControllerAdvice
public class WebExceptionHandler {
    @ExceptionHandler(OrderRuleViolation.class)
    public String handleOrderRuleViolation(
            OrderRuleViolation exception,
            Model model
    ) {
        model.addAttribute("message", exception.getMessage());
        return "orders/error";
    }

    @ExceptionHandler(OrderNotFound.class)
    public ResponseEntity<Void> handleOrderNotFound() {
        return ResponseEntity.notFound().build();
    }
}
~~~

Đây là ví dụ rút gọn; một ứng dụng thường cần phân biệt handler cho HTML và API, dùng mã lỗi ổn định hoặc thông điệp đã dịch, đồng thời tránh đưa stack trace hoặc chi tiết nội bộ ra client.

## 8. Phân quyền không đồng nghĩa với quy tắc nghiệp vụ

Controller hoặc security filter có thể tham gia xác thực và phân quyền ở ranh giới request. Tuy nhiên, cần phân biệt:

- **Xác thực (authentication):** Ai đang gửi request?
- **Phân quyền (authorization):** Chủ thể đó có được phép truy cập tài nguyên hoặc thực hiện thao tác không?
- **Quy tắc nghiệp vụ:** Ngay cả khi có quyền, thao tác này có hợp lệ theo trạng thái và chính sách nghiệp vụ không?

Ví dụ, nhân viên có quyền hủy đơn nhưng chỉ được hủy khi đơn chưa giao. Quyền hủy là chính sách truy cập; điều kiện trạng thái đơn là quy tắc nghiệp vụ. Cả hai đều cần được bảo vệ ở máy chủ.

Không được dựa vào việc View đã ẩn nút hủy để kết luận request không thể xảy ra. Client có thể gọi endpoint trực tiếp. Tương tự, không nên tin `customerId`, `role` hoặc `isAdmin` do form gửi lên; hãy lấy danh tính và quyền từ ngữ cảnh xác thực đáng tin cậy.

## 9. Các câu hỏi giúp xác định một đoạn mã thuộc điều phối hay nghiệp vụ

Khi xem một đoạn mã trong Controller, hãy tự hỏi:

1. Đoạn mã đang chuyển dữ liệu giữa request, service và response, hay đang quyết định điều gì hợp lệ trong miền nghiệp vụ?
2. Quyết định này có cần giống nhau khi được gọi từ Web, API, batch hoặc một use case khác không?
3. Nếu đổi URL, HTTP method hoặc template, quy tắc này có cần thay đổi không?
4. Nếu chính sách nghiệp vụ thay đổi, có phải sửa nhiều Controller không?
5. Đoạn mã có thể kiểm thử bằng trạng thái miền nghiệp vụ mà không cần dựng request HTTP không?
6. Đoạn mã có phụ thuộc vào trạng thái hiện tại, chính sách, quyền lợi hoặc bất biến của entity không?

Nếu mục tiêu là chuyển đổi dữ liệu và chọn phản hồi, đoạn mã thường thuộc điều phối. Nếu mục tiêu là xác định hành động có được phép xảy ra, tính giá trị nghiệp vụ hoặc bảo vệ trạng thái, đoạn mã thuộc Model hoặc thành phần nghiệp vụ.

Một số đoạn mã cần cả hai loại công việc. Khi đó, hãy tách chúng: Controller thực hiện binding và gọi use case; Model kiểm tra quy tắc và trả kết quả; Controller ánh xạ kết quả thành phản hồi.

## 10. Kiểm thử riêng từng trách nhiệm

Ranh giới rõ giúp lựa chọn loại kiểm thử phù hợp.

### 10.1. Unit test cho quy tắc nghiệp vụ

Kiểm thử domain object hoặc policy với các trường hợp:

- Đơn ở trạng thái `PENDING` có thể hủy.
- Đơn ở trạng thái `SHIPPED` không thể hủy.
- Mã giảm giá hết hạn bị từ chối.
- Số lượng vượt tồn kho không thể đặt.
- Giá cuối cùng được tính đúng theo chính sách.

Các test này không cần HTTP request, Controller hoặc template engine.

### 10.2. Unit test cho application service

Kiểm tra service gọi đúng repository, policy và cộng tác viên cần thiết; xử lý kết quả và lỗi theo use case. Có thể dùng fake hoặc mock cho các dependency bên ngoài, nhưng vẫn cần test tích hợp cho transaction và lưu trữ thật.

### 10.3. Web test cho Controller

Kiểm tra:

- URL và HTTP method ánh xạ đúng handler.
- Form được bind và validation lỗi được trả về đúng View.
- Command được tạo từ dữ liệu đã xác thực.
- Application service được gọi với dữ liệu mong đợi.
- Kết quả thành công tạo redirect hoặc response phù hợp.
- Lỗi nghiệp vụ được ánh xạ thành phản hồi đúng.

### 10.4. Integration test cho use case

Kiểm tra luồng đầy đủ với cơ sở dữ liệu thử nghiệm, transaction và các adapter cần thiết. Đặc biệt chú ý các thao tác đồng thời như giữ tồn kho hoặc cập nhật trạng thái để xác minh ứng dụng không tạo dữ liệu sai khi có nhiều request.

## 11. Những ngộ nhận thường gặp

### “Controller không được có logic”

Controller cần logic điều phối. Việc kiểm tra lỗi binding, chọn View, tạo redirect hoặc ánh xạ lỗi là công việc hợp lệ. Điều cần tránh là để Controller sở hữu chính sách nghiệp vụ.

### “Mọi điều kiện đều phải đưa vào Model”

Điều kiện về giao thức như thiếu tham số, sai kiểu dữ liệu hoặc lỗi binding thuộc ranh giới request. Không cần đưa các chi tiết HTTP này vào Model. Quy tắc nghiệp vụ cần được bảo vệ trong Model ngay cả khi Controller có kiểm tra sơ bộ.

### “Application service và domain model là một”

Application service điều phối một use case và cộng tác viên. Domain model giữ trạng thái, hành vi và bất biến của miền nghiệp vụ. Một số ứng dụng dùng domain service hoặc policy cho quy tắc không thuộc riêng một entity.

### “Chuyển code sang Service là đã giải quyết vấn đề”

Nếu một lớp `OrderService` chỉ là Controller thứ hai với toàn bộ điều kiện, truy vấn và định dạng trộn lẫn, tên lớp không làm ranh giới tốt hơn. Hãy xác định rõ phần điều phối use case, quy tắc miền, truy cập dữ liệu và phản hồi.

### “Validation ở Controller đủ để bảo vệ nghiệp vụ”

Client có thể gọi use case qua nhiều điểm vào. Validation biểu mẫu giúp phản hồi sớm, nhưng Model vẫn phải bảo vệ bất biến và điều kiện nghiệp vụ.

## 12. Checklist review Controller

- [ ] Controller chỉ xử lý chi tiết request/response và điều phối giao tiếp.
- [ ] Dữ liệu request được bind vào form object hoặc DTO có trường phù hợp.
- [ ] Danh tính người dùng được lấy từ ngữ cảnh xác thực, không tin giá trị client tự gửi.
- [ ] Controller chuyển dữ liệu thành command hoặc tham số use case rõ ràng.
- [ ] Quy tắc giá, quyền lợi, trạng thái và điều kiện được thực thi trong thành phần nghiệp vụ.
- [ ] Application service điều phối use case và transaction khi cần.
- [ ] Controller không tự viết truy vấn hoặc quản lý chi tiết lưu trữ.
- [ ] Lỗi binding, lỗi nghiệp vụ và lỗi kỹ thuật được phân biệt.
- [ ] Kết quả được ánh xạ thành View, redirect hoặc HTTP response phù hợp.
- [ ] Có kiểm thử riêng cho quy tắc nghiệp vụ và điều phối HTTP.

## Kết luận

Controller chịu trách nhiệm điều phối giao tiếp: nhận request, kiểm tra hợp đồng đầu vào, lấy ngữ cảnh xác thực, gọi use case và chọn phản hồi. Application service điều phối các bước của use case; Model và các thành phần nghiệp vụ quyết định điều gì hợp lệ, tính kết quả và bảo vệ trạng thái. Khi ranh giới này rõ ràng, cùng một quy tắc có thể được dùng từ Web, API và tác vụ nền, lỗi được ánh xạ phù hợp với từng kênh, còn các phần có thể được kiểm thử độc lập. Hãy đánh giá đoạn mã theo câu hỏi nó đang chuyển dữ liệu hay đang ra quyết định nghiệp vụ để đặt trách nhiệm vào đúng nơi.

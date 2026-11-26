# Gọi ca sử dụng và ánh xạ kết quả sang phản hồi hoặc mô hình hiển thị

Trong kiến trúc phân tầng, tầng trình bày (Presentation) là điểm tiếp xúc giữa người dùng hoặc hệ thống bên ngoài với ứng dụng. Một nhiệm vụ cốt lõi của tầng này là nhận dữ liệu đầu vào, chuyển dữ liệu đó thành yêu cầu phù hợp với ca sử dụng (use case), gọi ca sử dụng và chuyển kết quả nhận được thành phản hồi HTTP hoặc mô hình dữ liệu để hiển thị trên giao diện.

Tầng trình bày chịu trách nhiệm về cách giao tiếp. Nó cần hiểu request, response, mã trạng thái HTTP, biểu mẫu và cấu trúc dữ liệu hiển thị. Nó không nên tự quyết định quy tắc nghiệp vụ hoặc truy cập cơ sở dữ liệu để hoàn thành một ca sử dụng. Trong module **Học tổ chức phần mềm theo kiến trúc phân tầng**, ranh giới này giúp giữ cho phần giao tiếp có thể thay đổi mà không làm xáo trộn cách ứng dụng thực hiện nghiệp vụ.

## 1. Vai trò của tầng trình bày trong một ca sử dụng

Một request đi qua tầng trình bày thường gồm bốn việc:

1. **Tiếp nhận và kiểm tra dữ liệu giao tiếp:** đọc path, query parameter, request body, thông tin xác thực và kiểm tra định dạng cơ bản.
2. **Chuyển đổi đầu vào:** ánh xạ dữ liệu bên ngoài thành command, query hoặc input model mà ca sử dụng hiểu.
3. **Gọi ca sử dụng:** chuyển quyền xử lý cho Application và nhận kết quả.
4. **Ánh xạ đầu ra:** chuyển kết quả thành HTTP status, response body, redirect hoặc view model.

Ví dụ, với chức năng đặt hàng, tầng trình bày nhận thông tin sản phẩm và số lượng từ trình duyệt. Nó chuyển request thành lệnh đặt hàng, gọi use case PlaceOrder, sau đó chuyển kết quả thành phản hồi cho client. Quy tắc như sản phẩm có được phép bán hay đơn hàng có thể chuyển sang trạng thái đã đặt hay không thuộc nghiệp vụ được thực hiện trong Application/Domain.

~~~mermaid
sequenceDiagram
    actor Client as Trình duyệt / Client
    participant P as Presentation Controller
    participant A as Application Use Case
    participant D as Domain
    participant I as Infrastructure
    Client->>P: HTTP request
    P->>P: Parse và kiểm tra dữ liệu giao tiếp
    P->>A: Command / Query
    A->>D: Thực hiện quy tắc nghiệp vụ
    D-->>A: Kết quả nghiệp vụ
    A->>I: Gọi cổng cần thiết
    I-->>A: Dữ liệu / kết quả lưu trữ
    A-->>P: Use case output
    P->>P: Ánh xạ sang response hoặc view model
    P-->>Client: HTTP response / HTML
~~~

Sơ đồ mô tả trách nhiệm khái quát. Một use case có thể gọi domain object và các cổng lưu trữ hoặc tích hợp theo trình tự khác nhau. Điểm quan trọng là controller giao việc cho Application rồi định dạng kết quả theo giao thức bên ngoài.

## 2. Phân biệt request DTO, command và kết quả use case

Các kiểu dữ liệu ở những ranh giới khác nhau phục vụ những mục đích khác nhau:

| Kiểu dữ liệu | Thuộc ranh giới nào? | Mục đích |
|---|---|---|
| Request DTO | Presentation / giao thức bên ngoài | Mô tả dữ liệu client gửi lên |
| Command hoặc Query | Application | Diễn đạt yêu cầu thực hiện một hành động hoặc truy vấn |
| Domain object | Domain | Biểu diễn trạng thái, hành vi và quy tắc nghiệp vụ |
| Use case output/result | Application | Cung cấp kết quả cần thiết cho bên gọi |
| Response DTO hoặc View Model | Presentation | Mô tả dữ liệu trả về API hoặc đưa vào giao diện |

Không phải dự án nào cũng cần tạo một lớp riêng cho tất cả các kiểu trên. Có thể dùng cùng một kiểu ở hai ranh giới khi cấu trúc và ý nghĩa của chúng thực sự giống nhau. Tuy nhiên, dùng trực tiếp một DTO HTTP làm command nghiệp vụ hoặc trả thẳng entity miền ra API thường khiến hai ranh giới bị gắn chặt với nhau.

Ví dụ, client có thể gửi tên trường là **productId** và **quantity**. Use case có thể nhận **PlaceOrderCommand** với những trường mang ý nghĩa rõ ràng hơn, cùng mã người dùng lấy từ ngữ cảnh xác thực. Kết quả use case có thể chứa mã đơn hàng, tổng tiền và trạng thái đã xác nhận. Controller quyết định những trường nào sẽ xuất hiện trong response công khai.

## 3. Ví dụ REST API với Spring Boot

Giả sử API cung cấp chức năng đặt hàng. Request body có thể được biểu diễn bằng một DTO:

~~~java
public record PlaceOrderRequest(
        @NotNull UUID productId,
        @Positive int quantity
) {}
~~~

Command và kết quả thuộc hợp đồng của Application:

~~~java
public record PlaceOrderCommand(
        UUID customerId,
        UUID productId,
        int quantity
) {}

public record PlaceOrderResult(
        UUID orderId,
        BigDecimal total,
        String status
) {}

public interface PlaceOrderUseCase {
    PlaceOrderResult execute(PlaceOrderCommand command);
}
~~~

Controller chuyển đổi request, gọi use case và ánh xạ kết quả thành response DTO:

~~~java
public record PlaceOrderResponse(
        UUID orderId,
        BigDecimal total,
        String status
) {}

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final PlaceOrderUseCase placeOrder;

    public OrderController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    public ResponseEntity<PlaceOrderResponse> place(
            @Valid @RequestBody PlaceOrderRequest request,
            @AuthenticationPrincipal AppPrincipal principal) {

        var command = new PlaceOrderCommand(
                principal.customerId(),
                request.productId(),
                request.quantity()
        );

        var result = placeOrder.execute(command);

        var response = new PlaceOrderResponse(
                result.orderId(),
                result.total(),
                result.status()
        );

        URI location = URI.create("/api/orders/" + result.orderId());
        return ResponseEntity.created(location).body(response);
    }
}
~~~

Ví dụ trên minh họa cách phân chia công việc:

- Spring MVC đọc JSON và tạo **PlaceOrderRequest**.
- Bean Validation kiểm tra điều kiện đầu vào ở mức giao tiếp, chẳng hạn productId phải có giá trị và quantity phải dương.
- Controller lấy danh tính khách hàng từ principal đã được xác thực, rồi tạo **PlaceOrderCommand**.
- **PlaceOrderUseCase** thực hiện ca sử dụng và trả về **PlaceOrderResult**.
- Controller chuyển kết quả sang **PlaceOrderResponse** và trả mã HTTP 201 Created cùng header Location.

Controller không tự tính giá, kiểm tra tồn kho, quyết định giảm giá hay ghi đơn hàng. Những quyết định đó thuộc use case và mô hình nghiệp vụ. Việc lấy customerId từ principal cũng giúp ứng dụng không phải tin một customerId tùy ý do client gửi trong body.

Các kiểu **AppPrincipal**, use case và kết quả trong ví dụ là hợp đồng minh họa; dự án thực tế cần định nghĩa chúng theo mô hình xác thực và nghiệp vụ của mình. Nếu ứng dụng không có danh tính người dùng, command có thể lấy thông tin định danh từ một nguồn đầu vào phù hợp khác.

## 4. Ánh xạ kết quả sang phản hồi HTTP

Kết quả use case và phản hồi HTTP không phải lúc nào cũng có quan hệ một-một. Một use case có thể được gọi từ REST API, giao diện web, tác vụ nền hoặc một giao thức khác. Mỗi bên gọi có thể trình bày cùng kết quả theo cách riêng.

Với REST API, controller thường quyết định:

| Tình huống | Cách phản hồi thường gặp |
|---|---|
| Tạo tài nguyên thành công | 201 Created, có thể kèm Location và response body |
| Thực hiện thành công, có nội dung trả về | 200 OK |
| Thực hiện thành công, không cần body | 204 No Content |
| Dữ liệu request sai định dạng hoặc không vượt qua validation ở biên | 400 Bad Request |
| Chưa xác thực hoặc không đủ quyền | 401 Unauthorized hoặc 403 Forbidden |
| Không tìm thấy tài nguyên | 404 Not Found |
| Xung đột với trạng thái hiện tại hoặc điều kiện nghiệp vụ | Thường là 409 Conflict, tùy hợp đồng API |

Bảng này là quy ước thường gặp, không phải phép ánh xạ cứng cho mọi API. Mã trạng thái phải phản ánh hợp đồng đã công bố và ngữ nghĩa của tình huống. Ví dụ, một lỗi nghiệp vụ có thể được biểu diễn bằng 409 Conflict nếu request xung đột với trạng thái hiện tại; một lỗi khác có thể cần mã hoặc cấu trúc lỗi riêng theo API.

Không nên để Application phụ thuộc vào **ResponseEntity**, **HttpServletRequest** hay mã HTTP. Application nên trả kết quả mang ý nghĩa của ca sử dụng hoặc phát ra lỗi ứng dụng có thể nhận diện. Presentation chuyển những kết quả đó thành ngữ nghĩa giao thức. Nhờ vậy, cùng một use case có thể được gọi từ REST controller và một giao diện MVC mà không cần biết mã HTTP hay HTML.

## 5. Xử lý lỗi tại ranh giới trình bày

Một ca sử dụng có thể thất bại vì nhiều lý do: đầu vào không hợp lệ, tài nguyên không tồn tại, trạng thái nghiệp vụ không cho phép hành động hoặc một dịch vụ ngoài tạm thời không khả dụng. Tầng trình bày cần chuyển lỗi thành phản hồi phù hợp mà không làm mất ý nghĩa của lỗi.

Có thể phân biệt:

- **Lỗi cú pháp hoặc định dạng request:** thiếu trường bắt buộc, UUID sai định dạng, số lượng không phải số dương. Framework và validation ở Presentation có thể phát hiện trước khi gọi use case.
- **Lỗi nghiệp vụ:** khách hàng không thể đặt sản phẩm đã ngừng bán hoặc đơn hàng không thể được xác nhận ở trạng thái hiện tại. Application/Domain quyết định và trả lỗi có ý nghĩa nghiệp vụ.
- **Lỗi kỹ thuật:** database timeout hoặc dịch vụ thanh toán không phản hồi. Infrastructure và Application xử lý theo chính sách retry, timeout hoặc chuyển lỗi; Presentation trả thông báo phù hợp với hợp đồng API.

Với Spring, có thể tập trung ánh xạ lỗi bằng **@RestControllerAdvice**:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> handleNotFound(
            OrderNotFoundException exception) {
        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Order not found");
        problem.setDetail(exception.getMessage());
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(OrderStateConflictException.class)
    ResponseEntity<ProblemDetail> handleConflict(
            OrderStateConflictException exception) {
        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.CONFLICT);
        problem.setTitle("Order state conflict");
        problem.setDetail(exception.getMessage());
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
~~~

Đây là ví dụ đơn giản về ánh xạ lỗi đã được nhận diện sang phản hồi HTTP. Trong hệ thống thật, nên tránh đưa stack trace, câu SQL, thông tin bí mật hoặc thông báo nội bộ nhạy cảm vào response. Có thể bổ sung mã lỗi ổn định, trường dữ liệu gây lỗi và correlation ID để client hoặc nhóm vận hành tra cứu.

Không nên bắt mọi **Exception** trong controller rồi trả về 200 OK hoặc một thông báo chung. Cách đó làm sai ngữ nghĩa HTTP và che giấu lỗi. Hãy ánh xạ các trường hợp đã biết một cách nhất quán; lỗi không dự kiến cần được ghi log và xử lý theo chính sách lỗi chung của ứng dụng.

## 6. Ánh xạ kết quả sang mô hình hiển thị cho giao diện

Với ứng dụng web render HTML phía máy chủ, tầng trình bày có thể chuyển kết quả use case thành View Model rồi đưa vào template. View Model chứa dữ liệu mà trang cần hiển thị, chẳng hạn mã đơn hàng, tên sản phẩm, tổng tiền và nhãn trạng thái.

~~~java
public record OrderConfirmationViewModel(
        String orderNumber,
        String formattedTotal,
        String statusLabel
) {}

@Controller
public class OrderPageController {
    private final GetOrderConfirmationUseCase getConfirmation;

    public OrderPageController(
            GetOrderConfirmationUseCase getConfirmation) {
        this.getConfirmation = getConfirmation;
    }

    @GetMapping("/orders/{orderId}/confirmation")
    public String confirmation(
            @PathVariable UUID orderId,
            Model model) {

        var result = getConfirmation.execute(
                new GetOrderConfirmationQuery(orderId)
        );

        var viewModel = new OrderConfirmationViewModel(
                result.orderNumber(),
                formatCurrency(result.total()),
                toDisplayLabel(result.status())
        );

        model.addAttribute("order", viewModel);
        return "orders/confirmation";
    }

    private String formatCurrency(BigDecimal amount) {
        return NumberFormat.getCurrencyInstance(
                Locale.forLanguageTag("vi-VN")
        ).format(amount);
    }

    private String toDisplayLabel(OrderStatus status) {
        return switch (status) {
            case CONFIRMED -> "Đã xác nhận";
            case PENDING -> "Đang xử lý";
            case CANCELLED -> "Đã hủy";
        };
    }
}
~~~

Trong ví dụ này, use case trả dữ liệu cần thiết để hiển thị xác nhận đơn hàng. Controller định dạng số tiền theo locale và chuyển trạng thái kỹ thuật thành nhãn phù hợp với giao diện. Template **orders/confirmation** chỉ cần đọc thuộc tính của View Model để hiển thị.

Cần phân biệt việc trình bày với việc quyết định nghiệp vụ. Chuyển số tiền thành chuỗi theo locale hoặc chuyển trạng thái thành nhãn là công việc hiển thị. Quyết định đơn hàng có đủ điều kiện xác nhận hay không vẫn thuộc nghiệp vụ. Nếu giao diện cần nhiều dữ liệu từ nhiều nguồn, use case truy vấn có thể tổng hợp dữ liệu cần thiết hoặc Application có thể cung cấp một output model phù hợp; controller không nên tự thực hiện hàng loạt truy vấn repository để ghép trang.

Đối với giao diện SPA hoặc ứng dụng di động, response DTO thường đóng vai trò tương tự View Model: nó trình bày dữ liệu theo hợp đồng mà client cần. Tuy nhiên, định dạng hiển thị cuối cùng như cách căn chỉnh, màu sắc hoặc cách sắp xếp thành phần giao diện thường thuộc client.

## 7. Những ranh giới cần giữ khi viết controller

Controller dễ trở thành nơi chứa quá nhiều logic nếu mọi thao tác đều được thêm vào phương thức xử lý request. Một số dấu hiệu cho thấy trách nhiệm đang đặt sai chỗ:

- Controller tự tính giá, áp dụng chính sách giảm giá hoặc quyết định chuyển trạng thái đơn hàng.
- Controller gọi repository trực tiếp để lấy nhiều bảng rồi tự ghép thành kết quả nghiệp vụ.
- Controller tự quản lý một quy trình gồm nhiều bước và nhiều nhánh nghiệp vụ.
- Domain entity được trả thẳng ra JSON khiến cấu trúc API phụ thuộc vào mô hình lưu trữ hoặc quan hệ object.
- Application phải nhận các kiểu dữ liệu gắn với HTTP, template hoặc framework giao diện.

Khi gặp các dấu hiệu đó, hãy chuyển phần điều phối và quy tắc về Application/Domain, để controller giữ nhiệm vụ chuyển đổi ở biên. Không cần tạo thêm lớp mapper riêng cho mọi DTO nếu phép ánh xạ chỉ có một vài trường đơn giản. Có thể đặt phép ánh xạ nhỏ ngay trong controller hoặc dùng mapper chuyên biệt khi số lượng trường, quy tắc định dạng hay số nơi sử dụng đủ lớn để việc tách ra có lợi.

Tương tự, không phải mọi kết quả use case đều cần một lớp response riêng. Hãy tách kiểu dữ liệu khi hợp đồng bên ngoài cần ổn định độc lập, khi cần che giấu dữ liệu nội bộ hoặc khi nhiều client cần những hình dạng kết quả khác nhau. Quyết định này nên dựa trên ranh giới thay đổi và nhu cầu thực tế.

## 8. Kiểm thử việc gọi use case và ánh xạ đầu ra

Có thể kiểm thử controller mà không cần khởi động toàn bộ hệ thống. Trong Spring MVC Test, cung cấp một use case giả để xác minh controller chuyển request đúng và tạo phản hồi đúng:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    PlaceOrderUseCase placeOrder;

    @Test
    void createsOrderAndMapsUseCaseResultToResponse() throws Exception {
        UUID orderId = UUID.randomUUID();
        UUID productId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();

        given(placeOrder.execute(any(PlaceOrderCommand.class)))
                .willReturn(new PlaceOrderResult(
                        orderId, new BigDecimal("125000"), "CONFIRMED"
                ));

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "productId": "%s",
                                  "quantity": 2
                                }
                                """.formatted(productId)))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        "Location", "/api/orders/" + orderId
                ))
                .andExpect(jsonPath("$.orderId").value(orderId.toString()))
                .andExpect(jsonPath("$.status").value("CONFIRMED"));

        then(placeOrder).should().execute(any(PlaceOrderCommand.class));
    }
}
~~~

Tên annotation và cách cấu hình mock có thể khác theo phiên bản Spring Boot và Mockito đang dùng; ví dụ tập trung vào cấu trúc kiểm thử MVC. Nên có các kiểm tra bổ sung để xác minh command được tạo với đúng dữ liệu request và danh tính người dùng, validation trả lỗi khi dữ liệu sai, cũng như lỗi use case được ánh xạ thành status và body phù hợp.

Kiểm thử được chia theo trách nhiệm:

- **Presentation test:** xác minh route, parsing, validation, chuyển request thành command/query, gọi use case và ánh xạ response hoặc view model.
- **Application test:** xác minh use case điều phối đúng quy trình và trả kết quả có ý nghĩa.
- **Domain test:** xác minh quy tắc và bất biến nghiệp vụ.
- **Integration test:** xác minh việc kết nối các thành phần thật như Spring configuration, adapter và database khi cần.

Mock use case trong controller test giúp tập trung vào hợp đồng giao tiếp. Nó không chứng minh nghiệp vụ đặt hàng hoạt động đúng; phần đó cần được kiểm thử ở Application và Domain.

## 9. Tự kiểm tra trách nhiệm của tầng trình bày

Khi hoàn thành một endpoint hoặc một trang, có thể tự hỏi:

1. Request đã được chuyển thành command/query rõ nghĩa trước khi gọi use case chưa?
2. Controller có gọi đúng ca sử dụng và chuyển dữ liệu cần thiết, bao gồm danh tính đã xác thực nếu có, không?
3. Response DTO hoặc View Model có chỉ chứa dữ liệu cần công khai hoặc hiển thị không?
4. Mã HTTP, redirect và cách biểu diễn lỗi có nhất quán với hợp đồng giao tiếp không?
5. Quy tắc nghiệp vụ, truy vấn lưu trữ và điều phối nhiều bước có đang nằm ngoài controller không?
6. Có thể kiểm thử riêng phần ánh xạ request/response bằng một use case giả không?

Tầng trình bày hoàn thành tốt vai trò khi nó biến dữ liệu của giao thức bên ngoài thành yêu cầu mà Application hiểu, chuyển giao cho use case và diễn đạt kết quả theo nhu cầu của client. Giữ rõ ranh giới này giúp API, giao diện web hoặc một kênh giao tiếp mới có thể thay đổi cách nhận và trình bày dữ liệu mà không phải viết lại quy tắc nghiệp vụ.


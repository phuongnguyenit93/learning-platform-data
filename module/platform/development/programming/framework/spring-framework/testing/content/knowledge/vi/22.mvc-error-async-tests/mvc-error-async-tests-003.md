# Lỗi chuyển đổi, thiếu tham số và validation

Trong Spring MVC, request HTTP được chuyển thành tham số Java trước khi controller thực thi nghiệp vụ. Spring đọc path, query parameter, header, body và form data; sau đó chuyển kiểu, bind dữ liệu và chạy validation theo cấu hình. Nếu một bước thất bại, controller có thể chưa được gọi. Hiểu đúng bước nào phát sinh lỗi giúp chọn status HTTP, định dạng lỗi và cách kiểm thử phù hợp.

Ba nhóm lỗi thường gặp là:

- **Thiếu dữ liệu bắt buộc:** client không gửi request parameter, header hoặc body mà endpoint yêu cầu.
- **Lỗi chuyển đổi/binding:** dữ liệu có mặt nhưng không chuyển được sang kiểu Java, chẳng hạn gửi `page=abc` trong khi controller nhận `Integer page`.
- **Lỗi validation:** dữ liệu đã được đọc và bind thành công nhưng vi phạm quy tắc đầu vào, chẳng hạn số lượng bằng 0 hoặc tên khách hàng để trống.

Các lỗi này thường được trả về dưới dạng 4xx. Mục tiêu của controller và exception handler là giải thích lỗi đủ rõ để client sửa request, đồng thời giữ cấu trúc phản hồi ổn định để client có thể xử lý tự động.

## 1. Spring xử lý request theo những bước nào?

Một request đi qua nhiều thành phần trước khi đến phần thân controller:

~~~text
HTTP request
    |
    v
HandlerMapping tìm endpoint
    |
    v
HandlerMethodArgumentResolver đọc từng tham số
    |
    +--> Path variable / query parameter / header / cookie
    |
    +--> HttpMessageConverter đọc request body
    |
    v
ConversionService / data binding chuyển kiểu
    |
    v
Bean Validation kiểm tra ràng buộc (nếu được yêu cầu)
    |
    v
Controller method
    |
    v
Service / nghiệp vụ
~~~

Ví dụ, với method sau:

~~~java
@PostMapping("/api/orders")
public OrderResponse create(
        @RequestParam String source,
        @RequestHeader("X-Client-Version") String clientVersion,
        @Valid @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

Spring phải tìm request parameter `source`, đọc header `X-Client-Version`, chuyển body sang `CreateOrderRequest` và chạy validation trước khi gọi method. Nếu tham số bắt buộc bị thiếu, JSON không đọc được hoặc object vi phạm validation, phần thân method có thể chưa chạy.

Không nên gộp mọi lỗi thành một khái niệm “validation error”. Lỗi chuyển đổi cho biết dữ liệu không đúng kiểu; lỗi validation cho biết dữ liệu có kiểu hợp lệ nhưng vi phạm quy tắc. Cách khắc phục phía client khác nhau và mã lỗi nên phản ánh được sự khác biệt đó.

## 2. Thiếu request parameter và header

### 2.1. Request parameter bắt buộc

Với `@RequestParam`, thuộc tính `required` mặc định là `true`:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> findByStatus(
        @RequestParam("status") OrderStatus status) {
    return orderService.findByStatus(status);
}
~~~

Request hợp lệ:

~~~http
GET /api/orders?status=PAID
~~~

Nếu client gửi `GET /api/orders` mà không có tham số `status`, Spring ném `MissingServletRequestParameterException`. Theo xử lý mặc định của Spring MVC, đây là request không hợp lệ và thường được trả về HTTP 400 Bad Request.

Nếu tham số thực sự tùy chọn, khai báo điều đó trong chữ ký method:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> find(
        @RequestParam(name = "status", required = false)
        OrderStatus status) {
    return orderService.find(status);
}
~~~

Với kiểu tham chiếu, giá trị có thể là `null` khi client không gửi tham số. Có thể dùng `Optional` để biểu đạt rõ trạng thái có/không:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> find(
        @RequestParam Optional<OrderStatus> status) {
    return orderService.find(status.orElse(null));
}
~~~

Không nên dùng `required = false` chỉ để làm test hết lỗi nếu nghiệp vụ thực sự cần giá trị đó. Khi dữ liệu bắt buộc, giữ hợp đồng bắt buộc và kiểm tra phản hồi 400.

### 2.2. Giá trị mặc định

Nếu endpoint có giá trị mặc định hợp lý, dùng `defaultValue`:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> search(
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    return orderService.search(page, size);
}
~~~

Khi có `defaultValue`, Spring coi tham số là không bắt buộc và dùng giá trị mặc định khi tham số vắng mặt hoặc có giá trị rỗng. Điều này hữu ích cho phân trang hoặc bộ lọc có mặc định rõ ràng. Không nên đặt mặc định tùy tiện cho dữ liệu định danh hoặc dữ liệu có ý nghĩa nghiệp vụ bắt buộc, vì request thiếu thông tin sẽ bị biến thành một request khác mà client không chủ ý gửi.

Nếu muốn phân biệt “không gửi” với “gửi chuỗi rỗng”, đừng dùng `defaultValue` một cách máy móc; hãy xác định chính sách của endpoint và kiểm thử riêng hai trường hợp.

### 2.3. Header bắt buộc

`@RequestHeader` cũng có thuộc tính `required`:

~~~java
@GetMapping("/api/profile")
public ProfileResponse profile(
        @RequestHeader("X-Tenant-Id") String tenantId) {
    return profileService.findForTenant(tenantId);
}
~~~

Thiếu header `X-Tenant-Id` thường dẫn đến HTTP 400. Nếu header tùy chọn, có thể đặt `required = false` hoặc `defaultValue` khi có mặc định hợp lệ. Header xác thực, tenant hoặc correlation theo hợp đồng hệ thống không nên được thay bằng query parameter hoặc body chỉ để tiện kiểm thử.

## 3. Lỗi chuyển đổi kiểu dữ liệu

### 3.1. Query parameter và path variable

Spring thường chuyển giá trị dạng chuỗi trong URL sang kiểu tham số Java:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> search(
        @RequestParam int page,
        @RequestParam int size) {
    return orderService.search(page, size);
}
~~~

Request `?page=1&size=20` có thể được chuyển thành hai số nguyên. Nhưng request `?page=first&size=20` không thể chuyển `first` thành `int`. Spring phát sinh lỗi chuyển đổi, thường biểu hiện qua `MethodArgumentTypeMismatchException` và được xử lý như HTTP 400.

Path variable cũng cần chuyển kiểu:

~~~java
@GetMapping("/api/orders/{orderId}")
public OrderResponse get(@PathVariable UUID orderId) {
    return orderService.get(orderId);
}
~~~

Nếu path khớp route nhưng giá trị không phải UUID hợp lệ, Spring không thể bind tham số và request thường nhận 400. Trường hợp path không khớp route là tình huống khác, thường dẫn đến 404.

### 3.2. Enum

Với enum:

~~~java
public enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}
~~~

Controller có thể nhận:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> find(
        @RequestParam OrderStatus status) {
    return orderService.findByStatus(status);
}
~~~

Giá trị `status=PAID` được chuyển thành `OrderStatus.PAID` theo converter mặc định. Giá trị `status=paid` hoặc `status=UNKNOWN` không tự động hợp lệ; nếu không có converter tùy chỉnh, chúng thường gây lỗi chuyển đổi và trả về 400.

Hãy xác định hợp đồng có phân biệt chữ hoa/chữ thường hay không. Nếu API chấp nhận chữ thường, tạo converter rõ ràng và kiểm thử cả giá trị hợp lệ lẫn không hợp lệ. Không nên bắt exception rồi mặc định một enum bất kỳ, vì việc đó biến request sai thành một hành động nghiệp vụ khác.

### 3.3. Ngày, giờ và số có định dạng

Với query parameter hoặc form field, có thể khai báo định dạng bằng `@DateTimeFormat`:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> findCreatedAfter(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {
    return orderService.findCreatedAfter(date);
}
~~~

Client gửi `?date=2026-11-13` theo định dạng ISO date. Chuỗi không đúng định dạng hoặc ngày không hợp lệ có thể gây lỗi chuyển đổi. Với số cần định dạng theo locale, `@NumberFormat` có thể hữu ích cho form hoặc ứng dụng web; API công khai thường nên dùng định dạng máy đọc ổn định, tránh phụ thuộc dấu phân cách hàng nghìn/thập phân theo locale.

Đối với JSON body, việc đọc ngày giờ thường do Jackson và các module tương ứng thực hiện, không phải cùng cơ chế chuyển đổi query parameter. Vì vậy, định dạng của query parameter và JSON body có thể được cấu hình ở các lớp khác nhau. Test phải gửi đúng định dạng theo từng vị trí.

### 3.4. Không dùng kiểu primitive khi cần phân biệt thiếu và giá trị mặc định

Một field JSON kiểu số nguyên có thể được bind vào:

~~~java
public record CreateOrderRequest(int quantity) {
}
~~~

Nếu property `quantity` bị bỏ khỏi JSON, giá trị primitive có thể trở thành `0`. Khi đó ứng dụng không còn phân biệt rõ field bị thiếu với client chủ động gửi số 0. Nếu cần phân biệt, dùng kiểu tham chiếu:

~~~java
public record CreateOrderRequest(
        @NotNull @Positive Integer quantity
) {
}
~~~

`@NotNull` bắt buộc field phải có giá trị; `@Positive` yêu cầu số lớn hơn 0. Với kiểu tham chiếu, request thiếu field hoặc gửi `null` sẽ được validation báo lỗi theo hợp đồng. Chú ý rằng phần lớn constraint Bean Validation coi `null` là hợp lệ trừ khi có thêm `@NotNull`; không nên giả định `@Positive` tự bắt lỗi null.

## 4. Validation với Jakarta Bean Validation

### 4.1. Định nghĩa ràng buộc trên request DTO

Spring MVC tích hợp Jakarta Bean Validation. Với Spring Boot 3.x, các annotation nằm trong package `jakarta.validation.*`:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank
        @Size(max = 80)
        String customerName,
        @NotBlank
        String sku,
        @NotNull
        @Positive
        Integer quantity,
        @Email
        String contactEmail
) {
}
~~~

Một số constraint thường dùng:

| Constraint | Ý nghĩa |
|---|---|
| `@NotNull` | Giá trị không được là null |
| `@NotBlank` | Chuỗi không null, không rỗng và có ít nhất một ký tự không phải khoảng trắng |
| `@NotEmpty` | Chuỗi/collection/map/array không null và không rỗng |
| `@Size(min, max)` | Giới hạn độ dài hoặc số phần tử |
| `@Positive` / `@PositiveOrZero` | Số dương hoặc không âm |
| `@Min` / `@Max` | Giới hạn số nguyên |
| `@DecimalMin` / `@DecimalMax` | Giới hạn số thập phân |
| `@Email` | Kiểm tra hình dạng địa chỉ email |
| `@Pattern` | Kiểm tra theo regular expression |
| `@Past` / `@Future` | Ràng buộc thời điểm trong quá khứ/tương lai |

Các constraint phải phản ánh quy tắc đầu vào thực sự. Ví dụ, `@Email` kiểm tra hình dạng địa chỉ chứ không chứng minh hộp thư tồn tại; `@Pattern` không nên dùng thay cho parser chuyên biệt nếu định dạng phức tạp.

### 4.2. Kích hoạt validation bằng @Valid

Với request body:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);
        return ResponseEntity
                .created(URI.create("/api/orders/" + created.id()))
                .body(created);
    }
}
~~~

`@Valid` yêu cầu Spring validate object sau khi body được chuyển thành DTO. Nếu có constraint vi phạm và không có tham số `Errors` hoặc `BindingResult` ngay sau tham số cần kiểm tra, Spring ném `MethodArgumentNotValidException`. Controller method chưa được gọi nên service chưa được thực thi.

Đối với `@ModelAttribute`, Spring bind request parameter vào object rồi thực hiện validation khi có `@Valid` hoặc `@Validated`. Lỗi bind kiểu dữ liệu và lỗi constraint có thể cùng được ghi vào `BindingResult`.

### 4.3. Validation lồng nhau và collection

Nếu DTO chứa object con, thêm `@Valid` để kích hoạt validation theo tầng:

~~~java
public record AddressRequest(
        @NotBlank String line1,
        @NotBlank String city,
        @NotBlank String postalCode
) {
}

public record CreateCustomerRequest(
        @NotBlank String name,
        @Valid @NotNull AddressRequest address,
        @NotEmpty List<@Valid ContactRequest> contacts
) {
}
~~~

Không có `@Valid` ở thuộc tính lồng nhau thì constraint bên trong object con có thể không được chạy theo cascade validation. Với collection, có thể dùng container element constraint như `List<@NotBlank String>` để kiểm tra từng phần tử, và `List<@Valid ContactRequest>` để kiểm tra từng object.

### 4.4. @Valid và @Validated

`@Valid` là annotation chuẩn Jakarta để kích hoạt cascade validation. `@Validated` là annotation của Spring, ngoài việc kích hoạt validation còn hỗ trợ chỉ định validation group:

~~~java
public interface Create {}
public interface Update {}

public record UserRequest(
        @NotBlank(groups = {Create.class, Update.class})
        String name,
        @NotBlank(groups = Create.class)
        String initialPassword
) {
}
~~~

Có thể đặt `@Validated(Create.class)` ở vị trí tham số để chạy group tương ứng. Chỉ thêm group khi quy tắc create và update thực sự khác nhau; nếu không, cấu hình group làm test và DTO phức tạp hơn cần thiết.

## 5. Validation trên tham số method và Spring Framework 6.1

Ngoài validation DTO bằng `@Valid @RequestBody`, Spring MVC còn có thể validate trực tiếp tham số controller:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> search(
        @RequestParam @Min(0) int page,
        @RequestParam @Min(1) @Max(100) int size) {
    return orderService.search(page, size);
}
~~~

Spring Framework 6.1 bổ sung hỗ trợ method validation tích hợp trong Spring MVC. Khi tham số hoặc giá trị trả về của handler method có constraint, Spring có thể ném `HandlerMethodValidationException` nếu vi phạm. Điều này khác với lỗi chuyển đổi `page=abc`: trường hợp đó thất bại trước khi giá trị số được tạo ra; còn `page=-1` chuyển đổi thành công nhưng vi phạm `@Min(0)`.

Với controller chạy trên Spring MVC 6.1 trở lên, tránh đặt class-level `@Validated` lên controller nếu muốn dùng cơ chế method validation tích hợp của Spring MVC. `@Validated` ở cấp class có thể kích hoạt method validation qua AOP proxy và thay đổi đường xử lý lỗi. Hãy chọn một cơ chế có chủ đích, phù hợp phiên bản Spring và kiểm thử đúng exception thực tế.

Validation ở service layer là một ranh giới khác. Nếu service dùng method validation qua proxy, lỗi có thể là `ConstraintViolationException`. Không nên xử lý mọi `ConstraintViolationException` như thể nó luôn đến từ request HTTP; exception đó cũng có thể phát sinh từ lời gọi nội bộ.

## 6. BindingResult và xử lý lỗi ngay trong controller

Khi controller cần tự quyết định cách xử lý lỗi binding/validation, đặt `BindingResult` ngay sau tham số được kiểm tra:

~~~java
@PostMapping("/web/orders")
public String submit(
        @Valid @ModelAttribute("form") OrderForm form,
        BindingResult bindingResult,
        Model model) {

    if (bindingResult.hasErrors()) {
        return "orders/create";
    }

    orderService.create(form);
    return "redirect:/web/orders";
}
~~~

Spring chỉ gắn lỗi vào `BindingResult` khi tham số này đứng ngay sau object tương ứng. Nếu đặt một tham số khác ở giữa, lỗi có thể được ném ra ngoài và chuyển tới exception resolver.

Với REST API, nhiều ứng dụng để exception thoát khỏi controller và xử lý tập trung bằng `@RestControllerAdvice`. Cách này giữ controller tập trung vào nghiệp vụ và giúp nhiều endpoint có cùng cấu trúc lỗi. Với form MVC trả về HTML, việc trả lại view cùng dữ liệu lỗi trong model thường phù hợp hơn.

## 7. Phân biệt các exception thường gặp

| Tình huống | Exception thường gặp | Status HTTP mặc định thường thấy |
|---|---|---|
| Thiếu `@RequestParam(required=true)` | `MissingServletRequestParameterException` | 400 |
| Thiếu `@RequestHeader(required=true)` | `MissingRequestHeaderException` | 400 |
| Giá trị query/path/header không chuyển được kiểu | `MethodArgumentTypeMismatchException` | 400 |
| JSON sai cú pháp, body rỗng khi bắt buộc hoặc không đọc được | `HttpMessageNotReadableException` | 400 |
| DTO `@Valid` có constraint vi phạm | `MethodArgumentNotValidException` | 400 |
| Binding/validation của `@ModelAttribute` thất bại | `BindException` hoặc lỗi validation tương ứng | 400 |
| Constraint trực tiếp trên tham số handler trong Spring MVC 6.1+ | `HandlerMethodValidationException` | 400 cho lỗi đầu vào |
| Content-Type không được endpoint hỗ trợ | `HttpMediaTypeNotSupportedException` | 415 |
| Accept không có representation phù hợp | `HttpMediaTypeNotAcceptableException` | 406 |

Đây là các trường hợp phổ biến, không phải bảng thay thế cho cấu hình thực tế. Controller advice, custom converter, exception resolver và phiên bản Spring có thể thay đổi exception hoặc response body. Khi cần chẩn đoán, hãy xem exception gốc và cấu hình MVC hiện hành thay vì suy luận chỉ từ status.

Một số khác biệt quan trọng:

- Thiếu một query parameter bắt buộc khác với gửi giá trị sai kiểu cho query parameter đó.
- JSON sai cú pháp khác với JSON hợp lệ nhưng field vi phạm constraint.
- Field JSON bị thiếu thường không phải `MissingServletRequestParameterException`; nó có thể trở thành giá trị null/default trong DTO rồi được validation kiểm tra.
- `404 Not Found` thường biểu thị không tìm thấy route hoặc tài nguyên, không phải cách chuẩn để báo mọi lỗi chuyển đổi.
- `415` là định dạng body gửi lên không được hỗ trợ; `406` là server không thể tạo representation phù hợp với `Accept`.

## 8. Thiết kế response lỗi ổn định với @RestControllerAdvice

Nếu mỗi endpoint tự tạo một JSON lỗi khác nhau, client phải viết nhiều nhánh xử lý và rất dễ phụ thuộc vào thông tin nội bộ. Một error contract thống nhất có thể gồm mã lỗi ổn định, thông điệp có thể hiển thị và danh sách lỗi theo field.

Ví dụ DTO lỗi:

~~~java
public record ApiError(
        String code,
        String message,
        String path,
        List<FieldViolation> violations
) {
}

public record FieldViolation(
        String field,
        String code,
        String message
) {
}
~~~

Advice có thể ánh xạ lỗi phổ biến:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MissingServletRequestParameterException.class)
    ResponseEntity<ApiError> missingParameter(
            MissingServletRequestParameterException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "MISSING_PARAMETER",
                "A required request parameter is missing.",
                request.getRequestURI(),
                List.of(new FieldViolation(
                        ex.getParameterName(),
                        "REQUIRED",
                        "This parameter is required."))
        );
        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<ApiError> typeMismatch(
            MethodArgumentTypeMismatchException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "INVALID_PARAMETER",
                "A request parameter has an invalid value.",
                request.getRequestURI(),
                List.of(new FieldViolation(
                        ex.getName(),
                        "TYPE_MISMATCH",
                        "The value has an unsupported format."))
        );
        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> validationFailed(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {

        List<FieldViolation> violations =
                ex.getBindingResult().getFieldErrors().stream()
                        .map(error -> new FieldViolation(
                                error.getField(),
                                error.getCode(),
                                error.getDefaultMessage()))
                        .toList();

        ApiError body = new ApiError(
                "VALIDATION_FAILED",
                "One or more request fields are invalid.",
                request.getRequestURI(),
                violations
        );
        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> unreadableBody(
            HttpMessageNotReadableException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "INVALID_REQUEST_BODY",
                "The request body is missing or cannot be read.",
                request.getRequestURI(),
                List.of()
        );
        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Đây là ví dụ tối giản để minh họa cách ánh xạ. Ứng dụng thực tế cần thống nhất mã lỗi, nội dung message, localization và cách xử lý cho mọi loại exception mà API công bố. Với lỗi validation, có thể lấy field error từ `BindingResult`; không nên đưa nguyên rejected value vào response vì giá trị đó có thể là mật khẩu, token hoặc dữ liệu cá nhân.

Nếu muốn tùy chỉnh các exception chuẩn của Spring MVC mà vẫn giữ đầy đủ hành vi xử lý mặc định, có thể kế thừa `ResponseEntityExceptionHandler` và override các hook tương ứng như xử lý validation, missing parameter hoặc type mismatch. Lưu ý class này đã xử lý nhiều exception MVC; không khai báo handler trùng lặp cho cùng exception theo cách gây xung đột mapping. Với Spring hỗ trợ `ProblemDetail`, có thể dùng cấu trúc problem detail để chuẩn hóa response lỗi theo định dạng mà hệ thống chọn.

Không trả stack trace, tên class nội bộ, SQL, đường dẫn file hoặc thông tin cấu hình trong response công khai. Chi tiết kỹ thuật nên được ghi log ở server cùng correlation id để đội vận hành tra cứu.

## 9. Kiểm thử thiếu tham số và lỗi chuyển đổi bằng MockMvc

MockMvc cho phép gửi request thiếu hoặc sai dữ liệu như client thật:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsBadRequestWhenRequiredStatusIsMissing() throws Exception {
        mockMvc.perform(get("/api/orders/by-status"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.violations[0].field")
                        .value("status"));

        then(orderService).shouldHaveNoInteractions();
    }

    @Test
    void returnsBadRequestWhenPageCannotBeConverted() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .param("page", "first"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PARAMETER"))
                .andExpect(jsonPath("$.violations[0].field")
                        .value("page"));

        then(orderService).shouldHaveNoInteractions();
    }
}
~~~

Tên endpoint và cấu trúc response trong ví dụ phải khớp với controller/advice của ứng dụng. Nếu ứng dụng dùng response lỗi khác, điều chỉnh JSONPath theo hợp đồng đó. Điều quan trọng là test xác nhận status, mã lỗi, field bị lỗi và việc controller không gọi service khi request chưa hợp lệ.

Với ngày hoặc enum, test giá trị không hợp lệ tương tự:

~~~java
mockMvc.perform(get("/api/orders")
        .param("date", "31-31-2026"))
    .andExpect(status().isBadRequest());

mockMvc.perform(get("/api/orders/by-status")
        .param("status", "UNKNOWN"))
    .andExpect(status().isBadRequest());
~~~

Không nên chỉ kiểm tra status 400. Nếu error contract là một phần của API, hãy kiểm tra cả mã lỗi và field. Điều này giúp phát hiện khi ai đó thay đổi exception mapping làm client không còn nhận dạng được lỗi.

## 10. Kiểm thử validation của request body

Một test có thể gửi JSON đúng cú pháp nhưng vi phạm constraint:

~~~java
@Test
void rejectsInvalidOrderFields() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerName": "   ",
                              "sku": "COFFEE-01",
                              "quantity": 0,
                              "contactEmail": "not-an-email"
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[*].field",
                    hasItems("customerName", "quantity", "contactEmail")));

    then(orderService).shouldHaveNoInteractions();
}
~~~

Phân biệt test này với JSON sai cú pháp:

~~~java
@Test
void rejectsMalformedJson() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"quantity\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_REQUEST_BODY"));
}
~~~

Test đầu tiên chứng minh Jackson đọc được JSON thành DTO nhưng Bean Validation từ chối dữ liệu. Test thứ hai chứng minh body không thể parse thành object. Hai lỗi có thể cùng status 400 nhưng nên có mã lỗi hoặc thông tin khác nhau để client biết cách sửa.

Với field bắt buộc, hãy kiểm thử ít nhất ba trường hợp: field vắng mặt, field là `null` và field có giá trị rỗng. Tùy DTO và cấu hình Jackson, kết quả bind có thể khác nhau. Với kiểu primitive, kiểm tra thêm giá trị mặc định có thể che giấu việc field bị thiếu.

## 11. Kiểm thử BindingResult trong form MVC

Với form controller, có thể kiểm tra cả trang hiển thị lại và lỗi trong model:

~~~java
@WebMvcTest(OrderFormController.class)
class OrderFormControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void redisplaysFormWhenQuantityCannotBeConverted() throws Exception {
        mockMvc.perform(post("/web/orders")
                        .param("sku", "COFFEE-01")
                        .param("quantity", "many"))
                .andExpect(status().isOk())
                .andExpect(view().name("orders/create"))
                .andExpect(model().attributeHasFieldErrors(
                        "form", "quantity"));
    }
}
~~~

Ở đây Spring không thể chuyển chuỗi `many` thành kiểu số của field `quantity`. Lỗi được ghi vào BindingResult và controller trả lại view để người dùng sửa. Nếu form controller không có BindingResult ngay sau model attribute, exception có thể đi qua exception resolver và trả về error page thay vì render form như mong đợi.

Với REST API, không nên trả về view name. Hãy dùng response JSON có cấu trúc và status phù hợp.

## 12. Lỗi trong MVC asynchronous request

Trong Spring MVC, controller có thể trả về `Callable`, `DeferredResult` hoặc `CompletionStage` để hoàn tất response sau khi xử lý bất đồng bộ. Cần phân biệt lỗi đầu vào với lỗi xảy ra trong tác vụ bất đồng bộ:

~~~text
HTTP request
    |
    v
Bind tham số + đọc body + validation
    |
    +--> lỗi đầu vào: exception resolver trả response lỗi
    |
    v
Controller trả Callable / DeferredResult
    |
    v
Tác vụ async chạy
    |
    +--> thành công: async dispatch để ghi response
    |
    +--> exception: async dispatch, exception resolver xử lý lỗi
~~~

Ví dụ:

~~~java
@GetMapping("/api/reports")
public Callable<ReportResponse> report(
        @RequestParam
        @Pattern(regexp = "daily|weekly|monthly")
        String period) {

    return () -> reportService.generate(period);
}
~~~

Validation của `period` được thực hiện khi Spring chuẩn bị gọi controller method. Nếu giá trị sai, controller không tạo `Callable` và không bắt đầu công việc nền. Nếu method trả về Callable hợp lệ nhưng `reportService.generate(...)` ném exception trong lúc chạy, Spring MVC hoàn tất async cycle rồi dispatch lại request để exception handling xử lý lỗi. Error handler cần có thể ánh xạ cả lỗi xảy ra sau khi controller đã trả về.

Nếu dùng method validation tích hợp Spring MVC 6.1, lỗi constraint trực tiếp trên tham số handler có thể được biểu diễn bằng `HandlerMethodValidationException`. Nếu chỉ dùng `@Valid @RequestBody`, lỗi DTO thường là `MethodArgumentNotValidException`. Hãy kiểm thử exception thực tế theo chữ ký controller và phiên bản framework.

### 12.1. Kiểm thử async dispatch

Với MockMvc, lần gọi đầu tiên có thể chỉ xác nhận request đã bắt đầu xử lý bất đồng bộ. Cần lấy `MvcResult` rồi dùng `asyncDispatch(...)` để kiểm tra response cuối:

~~~java
MvcResult result = mockMvc.perform(get("/api/reports")
                .param("period", "daily"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(result))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.period").value("daily"));
~~~

Khi muốn kiểm tra lỗi từ tác vụ nền, cấu hình service ném exception rồi xác nhận status và error contract sau async dispatch:

~~~java
given(reportService.generate("daily"))
        .willThrow(new ReportGenerationException("report unavailable"));

MvcResult result = mockMvc.perform(get("/api/reports")
                .param("period", "daily"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(result))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("REPORT_UNAVAILABLE"));
~~~

Test này giả định application advice ánh xạ `ReportGenerationException` thành 503. Với lỗi validation đầu vào, không mong đợi `asyncStarted()` vì controller chưa trả về tác vụ async; hãy kiểm tra trực tiếp status 400 ở request đầu tiên.

## 13. Khi nào dùng 400, 404, 409, 415 và 422?

Status phải thể hiện loại vấn đề theo hợp đồng API:

| Status | Dùng khi | Ví dụ |
|---|---|---|
| 400 Bad Request | Request thiếu dữ liệu bắt buộc, sai cú pháp, sai kiểu hoặc vi phạm validation đầu vào | page=abc, thiếu status, quantity không dương |
| 404 Not Found | Không tìm thấy route hoặc tài nguyên được yêu cầu | Không có order với id đó |
| 409 Conflict | Request hợp lệ về cú pháp nhưng xung đột với trạng thái hiện tại | Mã đơn đã tồn tại hoặc trạng thái không cho phép cập nhật |
| 415 Unsupported Media Type | Content-Type không được endpoint hỗ trợ | Gửi XML vào endpoint chỉ nhận JSON |
| 406 Not Acceptable | Server không tạo được response theo Accept | Client chỉ chấp nhận representation không được cung cấp |
| 422 Unprocessable Content | API chọn dùng để phân biệt nội dung có cú pháp hợp lệ nhưng không thể xử lý theo quy tắc nghiệp vụ | Một số API dùng cho lỗi domain validation |

Không có một quy tắc bắt buộc rằng mọi lỗi validation phải là 422. Spring MVC thường dùng 400 cho lỗi binding và Bean Validation. Nếu sản phẩm chọn 422 cho một nhóm lỗi nghiệp vụ, hãy ghi rõ trong API contract và dùng nhất quán. Đừng thay đổi status chỉ vì một test mong đợi con số khác.

## 14. Những lỗi thiết kế và kiểm thử thường gặp

- **Bắt mọi exception rồi trả 400:** lỗi database, lỗi lập trình hoặc sự cố phụ thuộc không phải request sai. Ánh xạ sai status khiến client khó phân biệt cần sửa request hay thử lại.
- **Trả message exception nguyên gốc:** message có thể chứa tên class, rejected value, SQL hoặc thông tin nội bộ. Tạo message an toàn cho client và log chi tiết ở server.
- **Dùng primitive cho field cần phân biệt thiếu và 0:** field vắng mặt có thể thành giá trị mặc định. Dùng wrapper cùng constraint phù hợp.
- **Cho rằng @Positive cũng bắt null:** nhiều Bean Validation constraint cho phép null. Kết hợp với @NotNull nếu field bắt buộc.
- **Nhầm conversion error với validation error:** `page=abc` không thể bind thành số; `page=-1` bind được nhưng vi phạm giới hạn.
- **Quên @Valid:** constraint trên DTO không tự chạy chỉ vì DTO có annotation. Đảm bảo controller kích hoạt validation.
- **Đặt BindingResult sai vị trí:** phải đứng ngay sau tham số được bind/validate.
- **Kiểm thử chỉ status code:** error code, field và cấu trúc response cũng là một phần hợp đồng API.
- **Dùng defaultValue để che dữ liệu bắt buộc bị thiếu:** chỉ đặt mặc định khi nghiệp vụ thực sự có giá trị mặc định.
- **Chỉ kiểm thử đường đi đồng bộ:** exception trong Callable/DeferredResult cần được kiểm tra qua async dispatch.
- **Đưa rejected value vào error response:** có thể làm lộ dữ liệu nhạy cảm; chỉ trả tên field và thông điệp phù hợp.

## 15. Quy trình kiểm thử cho mỗi loại lỗi

Khi thêm hoặc sửa endpoint, có thể xây dựng nhóm test theo trình tự:

1. Gửi request hợp lệ để xác nhận endpoint hoạt động.
2. Bỏ một tham số/header bắt buộc và kiểm tra mã lỗi thiếu dữ liệu.
3. Gửi giá trị không chuyển đổi được, ví dụ chuỗi thay cho số hoặc enum không tồn tại.
4. Gửi JSON sai cú pháp hoặc body rỗng để kiểm tra message converter.
5. Gửi JSON đúng cú pháp nhưng vi phạm constraint.
6. Kiểm tra field error, error code và status theo hợp đồng.
7. Xác nhận service không được gọi khi lỗi xảy ra trước controller/service.
8. Với endpoint async, kiểm tra cả lỗi trước khi bắt đầu async và exception sau khi async dispatch.
9. Kiểm tra response không để lộ rejected value hoặc chi tiết nội bộ.

Một test tốt cho lỗi request không chỉ chứng minh Spring trả về 400. Nó cho biết dữ liệu nào bị từ chối, lỗi xuất hiện ở bước nào, client cần sửa điều gì và ứng dụng có ngăn nghiệp vụ chạy với dữ liệu không hợp lệ hay không.

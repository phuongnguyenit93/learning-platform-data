# Jakarta Bean Validation và ràng buộc trên DTO

## 1. Vì sao REST API cần xác thực dữ liệu ngay tại biên?

Client REST có thể gửi JSON thiếu trường, số lượng âm hoặc dữ liệu lồng nhau sai. **Jakarta Bean Validation** khai báo ràng buộc cho DTO; **Spring MVC** kích hoạt kiểm tra ở biên và trả lỗi HTTP có cấu trúc.

Trong module **INTEGRATION_API_REST**, đây là điểm nối giữa hợp đồng, HTTP status, bảo mật và kiểm thử Java/Spring.

Ví dụ người mua đặt hai cuốn sách:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json

{
  "customerId": "cus-17",
  "items": [{"sku": "BOOK-01", "quantity": 2}]
}
~~~

Một request lỗi:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customerId": " ",
  "items": [{"sku": "", "quantity": 0}]
}
~~~

Nó có thể bị từ chối bằng **400 Bad Request** trước khi tạo đơn, với các lỗi gắn vào trường. Tuy nhiên, kiểm tra rằng **customerId tồn tại và thuộc người gọi**, **SKU còn tồn kho**, **giá do server tính** hoặc **đơn không bị tạo hai lần** phải được thực thi ở tầng phù hợp khác, không được nhầm là trách nhiệm duy nhất của Bean Validation.

Sau bài học, người học sẽ biết: khai báo constraints, dùng @Valid/@Validated, xử lý nested DTO và request parameters, trả Problem Details nhất quán, bảo vệ dữ liệu nhạy cảm và thiết kế unit/MockMvc/integration tests.

> **Ghi nhớ:** Bean Validation trả lời “dữ liệu có thỏa các ràng buộc đã khai báo không?”, **không** tự trả lời “người gọi có quyền không?”, “nghiệp vụ có cho phép không?” hay “transaction có an toàn khi hai request chạy cùng lúc không?”.

## 2. Các thành phần và trách nhiệm

**Jakarta Validation API** định nghĩa annotation/Validator, còn **provider** như Hibernate Validator thực thi. **Spring MVC** bind request và kích hoạt validation ở điểm vào; **Jackson** parse JSON trước đó. **Service/domain** kiểm quyền, nghiệp vụ và transaction; **database** giữ invariant unique/FK/concurrency. **OpenAPI** ghi lại schema/status để client hiểu hợp đồng; không tự thực thi ràng buộc.

### 2.1. Phụ thuộc phù hợp

Với dòng Spring Boot sử dụng Jakarta Validation (ví dụ Spring Boot 3.x), thường thêm starter:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Các phiên bản dependency nên do **BOM của dòng Spring Boot đã chọn** quản lý. Khi lên Boot major khác, kiểm tra tên starter, compatibility matrix và Jakarta API tương ứng, không tự ghép các JAR phiên bản mới nhất. Với Spring Boot hiện đại, dùng import **jakarta.validation.\***; không dùng javax.validation.\* từ thời Java EE cũ trong một ứng dụng Jakarta nếu thư viện không hỗ trợ.

**Lưu ý:** Chỉ thêm annotation mà không có provider/validation integration phù hợp có thể khiến constraint không được thực thi. Cần test hành vi invalid request thực tế thay vì suy từ dependency có mặt trên classpath.

## 3. Nhận diện các ràng buộc cơ bản

| Annotation | Áp dụng điển hình | Ngữ nghĩa |
|---|---|---|
| **@NotNull** | Object, wrapper Integer, enum, collection | Không cho null; chuỗi rỗng vẫn hợp lệ |
| **@NotEmpty** | String, collection, map, array | Không null và không rỗng; chuỗi chỉ dấu cách vẫn có thể hợp lệ |
| **@NotBlank** | CharSequence/String | Không null, không rỗng và phải có ký tự không phải khoảng trắng |
| **@Size(min, max)** | String/collection/array/map | Giới hạn độ dài hoặc số phần tử, không mặc định cấm null |
| **@Min/@Max** | Kiểu số thích hợp | Giới hạn cận dưới/trên dạng nguyên |
| **@Positive/@PositiveOrZero** | Number | Dương hoặc không âm |
| **@DecimalMin/@DecimalMax** | BigDecimal/kiểu số tương thích | Cận dạng chuỗi để biểu diễn decimal chính xác |
| **@Email** | Chuỗi email | Kiểm hình dạng địa chỉ theo provider; **không xác minh hộp thư tồn tại** |
| **@Pattern** | Chuỗi | Phải phù hợp regular expression; không tự chặn mọi Unicode/đường dẫn nguy hiểm |
| **@Past/@Future** | Kiểu ngày/giờ hỗ trợ | So với ClockProvider của validator |
| **@AssertTrue/@AssertFalse** | Boolean/property method | Kiểm một bất biến boolean đơn giản |
| **@Valid** | Object/collection element có constraint bên trong | Kích hoạt **cascaded validation**, bản thân không cấm null |

### 3.1. Những phân biệt hay nhầm

~~~java
@NotNull  String a; // "" và "   " vẫn vượt qua @NotNull
@NotEmpty String b; // "   " vượt qua @NotEmpty
@NotBlank String c; // "   " vi phạm @NotBlank

@Min(1) Integer qty; // null không vi phạm @Min
@NotNull @Min(1) Integer requiredQty; // null hoặc 0 đều vi phạm
~~~

**Không coi primitive int là đủ để phát hiện trường JSON bị thiếu.** Khi deserialization tạo giá trị mặc định 0, bạn có thể không phân biệt được “không gửi” với “gửi 0”. Với trường phải hiện diện, dùng wrapper Integer + @NotNull và constraint số phù hợp, kết hợp schema/hợp đồng JSON.

**@Size không phải giới hạn byte của request body.** Một chuỗi Unicode 100 ký tự có thể có kích thước UTF-8 khác 100 byte. Cần giới hạn payload ở HTTP gateway/server và khi đọc stream để chống lạm dụng tài nguyên.

### 3.2. Ràng buộc luôn tương ứng một thông điệp hợp đồng

Với mã sản phẩm, ví dụ:

~~~java
@NotBlank
@Size(max = 40)
@Pattern(regexp = "[A-Z0-9][A-Z0-9_-]*")
String sku;
~~~

Hợp đồng này chấp nhận SKU bắt đầu bằng chữ hoa hoặc chữ số, tiếp theo là chữ hoa, chữ số, gạch dưới hoặc gạch ngang. Nó **không** chứng minh SKU tồn tại, thuộc danh mục được đặt hay đang được phép bán. Nếu hệ thống cho phép Unicode hoặc cấu trúc SKU khác, phải thay rule theo nghiệp vụ, không sao chép regex như chuẩn chung.

## 4. DTO đầu vào: khai báo ràng buộc ở nơi client có thể hiểu

### 4.1. Dùng Java record và constraint trên component

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

record OrderItemInput(
        @NotBlank @Size(max = 40) String sku,
        @NotNull @Min(1) @Max(100) Integer quantity) {}

record CreateOrderRequest(
        @NotBlank @Size(max = 64) String customerId,
        @NotEmpty @Size(max = 50)
        List<@NotNull @Valid OrderItemInput> items) {}
~~~

Các trường hợp:

| Dữ liệu | Kết quả |
|---|---|
| customerId = "cus-17", items có sku BOOK-01 và quantity 2 | Đạt constraint DTO |
| customerId = "   " | Vi phạm @NotBlank |
| items = null hoặc [] | Vi phạm @NotEmpty |
| items có hơn 50 phần tử | Vi phạm @Size(max = 50) |
| Một phần tử items = null | Vi phạm @NotNull trên element |
| items[0].quantity = 0 | Vi phạm @Min qua @Valid lồng nhau |
| items[0].sku dài hơn 40 ký tự | Vi phạm @Size |

**Vì sao cả @NotEmpty và @Valid?** @NotEmpty kiểm tra collection phải có ít nhất một phần tử; @Valid kiểm tra các constraint **bên trong từng OrderItemInput**. Nếu thiếu @Valid, kiểm tra cấu trúc của collection vẫn có thể đạt dù quantity = 0. Container element constraints như List<@NotNull @Valid OrderItemInput> cần provider hỗ trợ khả năng đó.

### 4.2. Tách request DTO, domain model và response DTO

**Không bind @RequestBody trực tiếp thành JPA entity:** client có thể ghi tenantId, price, status hoặc flags nội bộ (**mass assignment**). Dùng request DTO với allowlist field, mapper rõ ràng; server tự tính giá và xác định tenant/owner từ danh tính đã xác thực. @NotBlank chỉ kiểm format của customerId, **không cấp quyền** hay thay DB unique/transaction.

### 4.3. Create và Update có thể có contract khác nhau

POST tạo đơn bắt buộc customerId/items, còn PATCH có thể chỉ sửa một field; **DTO riêng** thường dễ hiểu hơn group phức tạp. Khi cần **validation groups**, dùng @Validated(Group.class) và test từng entrypoint: constraint thuộc nhóm Create **không tự chạy trong Default group**.

## 5. Kích hoạt validation trong Spring MVC

### 5.1. @Valid @RequestBody ở controller

~~~java
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record OrderCreated(String id, String status) {}

interface CreateOrderUseCase {
    // Kiểm tra tenant, customer, SKU, tồn kho và idempotency trong service.
    OrderCreated create(
            Authentication caller,
            String idempotencyKey,
            CreateOrderRequest request);
}

@RestController
@RequestMapping("/api/orders")
class OrdersController {
    private final CreateOrderUseCase service;

    OrdersController(CreateOrderUseCase service) {
        this.service = service;
    }

    @PostMapping(consumes = "application/json", produces = "application/json")
    ResponseEntity<OrderCreated> create(
            @Valid @RequestBody CreateOrderRequest request,
            @RequestHeader("Idempotency-Key") String key,
            Authentication caller) {

        OrderCreated created = service.create(caller, key, request);
        return ResponseEntity.created(
                URI.create("/api/orders/" + created.id()))
                .cacheControl(CacheControl.noStore())
                .body(created);
    }
}
~~~

Đây là **fragment minh họa**, cần implementation CreateOrderUseCase, security, xử lý ngoại lệ và database. Khi body JSON parse được nhưng vi phạm constraint của DTO, cơ chế Spring MVC thường ném **MethodArgumentNotValidException** trước khi gọi service (với cách dùng @Valid @RequestBody này và không có BindingResult xử lý trực tiếp).

**Quan trọng:** Nếu quên @Valid trên request object, các annotation bên trong DTO **không mặc nhiên được chạy ở điểm vào đó**. Ngược lại, @Valid trên controller **không tự kiểm tra** idempotency, authorization hoặc giao dịch. Nếu thiếu header Idempotency-Key trong ví dụ, Spring xử lý lỗi header bắt buộc theo hợp đồng; hãy phân biệt lỗi transport/header với lỗi constraint trên DTO.

### 5.2. Phân biệt parse lỗi với validation lỗi

**JSON sai cú pháp/không chuyển được kiểu** thường gây HttpMessageNotReadableException → **400**; **DTO parse được nhưng quantity = 0** thường gây MethodArgumentNotValidException → **400**. Content-Type không hỗ trợ → **415**; request vượt hạn mức → **413**. Customer khác tenant, key lũy đẳng bị dùng cho payload khác và unique constraint tranh chấp thuộc **authorization/service/DB**, thường mang status **403/404/409** theo contract, không phải lỗi hình dạng DTO.

Spring MVC thường trả **400** cho @Valid không đạt. Chỉ dùng **422** theo một contract chủ động phân biệt dữ liệu hợp lệ cú pháp nhưng không xử lý được về nghiệp vụ, kèm mapping và tests.

### 5.3. @RequestParam, @PathVariable và method validation

Ràng buộc không chỉ nằm trong JSON body. Ví dụ đọc tập hợp đơn:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/orders")
PageResult list(
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(100) int limit) {
    return query.findPage(limit);
}

@GetMapping("/api/orders/{id}")
OrderView get(
        @PathVariable
        @Pattern(regexp = "ord-[A-Za-z0-9_-]{1,40}")
        String id) {
    return query.findVisible(id);
}
~~~

Đây là **hai handler fragment**, cần query và DTO tương ứng, không phải class độc lập. Spring MVC từ Spring Framework 6.1 có cơ chế **built-in method validation** cho các trường hợp phù hợp; constraint đặt trực tiếp lên method parameter có thể dẫn đến **HandlerMethodValidationException**. Nếu dùng @Validated ở cấp controller/class để kích hoạt AOP method validation trong một số cấu hình, đường đi/loại exception có thể khác. **Hãy kiểm tra phiên bản Spring Framework cụ thể và test lỗi HTTP thực tế**, thay vì đoán mọi violation đều thành MethodArgumentNotValidException.

Chọn đúng loại constraint: limit là tham số số; id chỉ kiểm tra **hình dạng**, không chứng minh resource tồn tại hoặc người gọi có quyền. Nếu converter không đọc được limit=abc, đó là lỗi binding/kiểu dữ liệu, không phải vi phạm @Min.

### 5.4. @Valid và @Validated khác nhau thế nào?

- **@Valid** thuộc Jakarta Validation, kích hoạt validation/cascade và dùng **Default group** trừ khi có group conversion.
- **@Validated** thuộc Spring, hỗ trợ truyền nhóm validation và trong một số bối cảnh kích hoạt method validation qua AOP.
- Với **@Valid @RequestBody** thông thường không cần rải @Validated trên mọi controller. Đặc biệt, class-level @Validated có thể khiến một phần method validation đi qua proxy khác với built-in MVC.

Nếu endpoint có yêu cầu update riêng, ưu tiên DTO riêng hoặc chỉ sử dụng groups khi rule đã được tài liệu hóa rõ và được kiểm thử toàn bộ method entrypoints.

## 6. Validation lồng nhau và ràng buộc phụ thuộc nhiều trường

### 6.1. Cascaded validation

Nếu yêu cầu có nested object:

~~~java
record ShippingAddress(
        @NotBlank String recipient,
        @NotBlank String city,
        @NotBlank String street) {}

record ShipmentInput(
        @NotBlank String orderId,
        @NotNull @Valid ShippingAddress address) {}
~~~

Một address = null bị @NotNull phát hiện; address hiện diện nhưng street = "" bị @Valid truyền validation vào ShippingAddress. Không nên gắn @Valid vào mọi field scalar; nó dành cho đối tượng lồng nhau có constraint và container elements.

Đường dẫn lỗi có thể là **address.street** hoặc **items[0].quantity**, tùy quy tắc mapping của framework. Hợp đồng lỗi phải dùng đường dẫn ổn định, không buộc client giải mã tên class Java nội bộ.

### 6.2. Khi một field chỉ hợp lệ trong ngữ cảnh field khác

Giao tại nhà (SHIP) cần address; nhận tại quầy (PICKUP) cần pickupPointId. Hai @NotBlank độc lập sẽ bắt buộc cả hai, nên cần **cross-field validation**. Với điều kiện đơn giản:

~~~java
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

enum DeliveryMode { SHIP, PICKUP }

record DeliveryChoice(
        @NotNull DeliveryMode mode,
        String address,
        String pickupPointId) {

    @AssertTrue(message = "Invalid delivery selection")
    public boolean isValidConfiguration() {
        if (mode == null) return true; // @NotNull xử lý riêng
        return switch (mode) {
            case SHIP -> address != null && !address.isBlank();
            case PICKUP -> pickupPointId != null
                           && !pickupPointId.isBlank();
        };
    }
}
~~~

Đây là ràng buộc trên **property boolean**, thường cho lỗi ở validConfiguration. Nếu cần lỗi gắn trực tiếp vào address/pickupPointId, hãy viết **custom class-level @Constraint** với **ConstraintValidator** và **ConstraintValidatorContext.addPropertyNode(...)**; test đường dẫn lỗi. Cần thêm @NotNull @Valid khi nhúng DeliveryChoice trong DTO cha.

Không gọi DB/network trong validator để kiểm tồn kho, quyền hoặc xác minh điểm pickup: những kiểm tra này cần service/domain, transaction và authorization. Quy tắc ví dụ chỉ kiểm độ đầy đủ của trường, không xác minh địa chỉ thực hay tình trạng kinh doanh.

## 7. Trả lỗi validation nhất quán với Problem Details

Một response hữu ích cần cho client biết **request không hợp lệ vì đâu**, nhưng không làm lộ dữ liệu nhạy cảm, class Java, stack trace hoặc thông tin database. Một hợp đồng theo **Problem Details (RFC 9457)**:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "One or more request fields are invalid",
  "code": "VALIDATION_FAILED",
  "invalidParams": [
    {"name": "customerId", "reason": "must not be blank"},
    {"name": "items[0].quantity", "reason": "must be greater than or equal to 1"}
  ]
}
~~~

**type, title, status, detail, instance** là những thành viên Problem Details có ngữ nghĩa chuẩn; **code và invalidParams** là *extension members* do API tự định nghĩa. Tránh để frontend dựa vào chuỗi reason có thể được dịch/ngữ cảnh hóa; code ổn định và đường dẫn field có hợp đồng rõ sẽ đáng tin hơn. Không echo toàn bộ rejectedValue trong response lỗi.

### 7.1. Spring MVC xử lý lỗi @Valid @RequestBody

Ví dụ một global handler cho **MethodArgumentNotValidException** trong Spring Framework 6.x:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler;

@RestControllerAdvice
class ApiValidationAdvice extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<Map<String, String>> errors =
            ex.getBindingResult().getFieldErrors().stream()
                .map(e -> Map.of(
                    "name", e.getField(),
                    "reason", Objects.toString(
                        e.getDefaultMessage(), "Invalid field")))
                .toList();

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        problem.setType(URI.create(
                "https://api.example.test/problems/invalid-request"));
        problem.setTitle("Invalid request");
        problem.setDetail("One or more request fields are invalid");
        problem.setProperty("code", "VALIDATION_FAILED");
        problem.setProperty("invalidParams", errors);

        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

Ví dụ trên tập trung **field errors**; các **global/object errors** từ class-level constraints không gắn field phải được bổ sung vào mapper thực tế (hoặc dùng cách tạo property node như mục 6). Nếu default constraint message có dữ liệu nhạy cảm do validator tự tạo, phải **mask** trước khi gửi. Khi build dự án Spring Boot phiên bản khác, xác minh chữ ký override tương ứng với Spring Framework đang được Boot quản lý.

Trong môi trường đa ngôn ngữ, provider có thể nội suy message qua MessageSource và locale. **Thông điệp dịch** phục vụ con người; **machine-readable code** phải ổn định, không dùng text tiếng Việt/tiếng Anh làm điều kiện rẽ nhánh nghiệp vụ.

### 7.2. Method validation và lỗi khác cần xử lý riêng

- DTO @Valid @RequestBody không đạt thường gây **MethodArgumentNotValidException → 400**; JSON không parse được thường gây **HttpMessageNotReadableException → 400**.
- Ràng buộc trực tiếp trên tham số method có thể gây **HandlerMethodValidationException** với built-in method validation của Spring MVC hiện đại: **400 cho input, 500 cho return value**.
- Với class-level @Validated/AOP hoặc validation trong service/JPA, có thể gặp **ConstraintViolationException** hay exception khác; phải xác định nguồn trước khi map status.

**Không bắt mọi ConstraintViolationException rồi trả 400**: vi phạm invariant trên dữ liệu nội bộ hoặc return value là lỗi server cần ghi nhận/alert. Chữ ký exception và cách kích hoạt method validation phải được xác minh bằng test theo Spring version cụ thể.

### 7.3. Khi nào nên dùng 422, 409, 412?

- **400 Bad Request:** JSON request hợp lệ cú pháp nhưng không đạt constraint đầu vào theo contract phổ biến; cũng là status thông dụng cho parse/binding error.
- **422 Unprocessable Content:** API có thể chọn cho yêu cầu đúng syntax/media type nhưng không thỏa một điều kiện xử lý đã định nghĩa; phải tài liệu hóa ranh giới.
- **409 Conflict:** trạng thái resource/command xung đột, ví dụ cùng idempotency key gắn hai payload khác nhau.
- **412 Precondition Failed:** If-Match không đạt khi cập nhật có điều kiện.
- **401/403/404:** xác thực, phân quyền hoặc chính sách che giấu tồn tại resource.

Tránh trả 400 cho mọi thứ chỉ vì “có thể tạo error JSON thống nhất”. **HTTP status chính xác** giúp retry policy, SDK, gateway metrics và client xử lý đúng.

## 8. Bảo mật và hiệu năng của validation

### 8.1. Ba ranh giới không thể thay thế nhau

**HTTP/gateway** chặn size, media type và rate (413/415/429); **Bean Validation DTO** kiểm cấu trúc/trường; **service/domain/DB** kiểm quyền, state, uniqueness/concurrency. @Size(max=50) không chặn một JSON hàng trăm MB **trước khi deserialize**, nên phải giới hạn body tại gateway/server; multipart có các hạn mức riêng.

### 8.2. Không để regex và validator thành điểm tấn công

- Tránh regex có **catastrophic backtracking** khi chạy trên chuỗi dài; luôn kết hợp giới hạn độ dài.
- Đừng gọi HTTP/DB để kiểm quyền hoặc tồn kho trong ConstraintValidator chạy trên từng item.
- Không dùng @Email hay @Pattern thay cho xác minh danh tính, quyền truy cập hoặc chống injection.
- Tránh thông báo lỗi chứa password, access token, số thẻ, stack trace, SQL hoặc tên bảng nội bộ.
- Dùng allowlist DTO cho các trường client được sửa; không bind trực tiếp JPA entity.
- Giới hạn số lỗi được trả/log nếu payload có nhiều item, đồng thời giữ khả năng chỉ ra lỗi đủ để client sửa.

SQL injection cần **parameterized queries** và quyền DB tối thiểu; XSS cần encoding/output policy; Bean Validation không thay các biện pháp này.

### 8.3. Quyền truy cập trước khi xử lý nghiệp vụ

Với POST /api/orders, security filter cần xác thực token và scope. Service phải xác minh **customerId thuộc phạm vi người gọi**. Nếu user gửi một customerId đúng format nhưng là của tenant khác, validation hình thức có thể đạt; **service vẫn phải từ chối** và không tạo order.

Một request không hợp lệ có thể bị chặn trước service nên controller test validation không chứng minh authorization. Ngược lại, test chỉ dùng @Valid mà không thiết lập Spring Security sẽ không chứng minh 401/403. Cần **hai nhóm test tách biệt và integration test kết hợp**.

## 9. Ghi ràng buộc và lỗi vào OpenAPI

OpenAPI giúp client biết field bắt buộc, giới hạn và mã lỗi. Ví dụ **fragment OAS 3.1**:

~~~yaml
paths:
  /api/orders:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201': {description: Order created}
        '400':
          description: Invalid request
          content:
            application/problem+json:
              schema: {type: object}
        '401': {description: Authentication required}
        '403': {description: Forbidden}
        '409': {description: Conflict}
components:
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerId, items]
      properties:
        customerId: {type: string, minLength: 1, maxLength: 64}
        items:
          type: array
          minItems: 1
          maxItems: 50
          items:
            type: object
            required: [sku, quantity]
            properties:
              sku: {type: string, minLength: 1, maxLength: 40}
              quantity: {type: integer, minimum: 1, maximum: 100}
~~~

Đoạn này cố ý giản lược **info, securitySchemes, Problem Details schema và response metadata**; API thực phải khai báo đủ theo OAS version. **minLength: 1 không loại chuỗi chỉ có dấu cách giống @NotBlank**; hãy giải thích rõ ngữ nghĩa và test. Annotation không bảo đảm schema OpenAPI tự động chính xác.

Khi tạo OpenAPI từ Java annotation, phân biệt **ràng buộc HTTP công khai** với constraint chỉ dùng cho lưu trữ/nội bộ; không phơi bày entity constraints hoặc trường không được phép sửa trong request schema.

## 10. Kiểm thử từ constraint đến HTTP

### 10.1. Unit test Validator không cần server

~~~java
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderValidationTest {
    @Test
    void rejectsNestedInvalidItem() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            var dto = new CreateOrderRequest(
                    "cus-17", List.of(new OrderItemInput("BOOK-01", 0)));
            var errors = factory.getValidator().validate(dto);
            assertTrue(errors.stream().anyMatch(e ->
                    e.getPropertyPath().toString()
                            .contains("quantity")));
        }
    }
}
~~~

Test này chứng minh **cascaded validation** và ràng buộc số. Bổ sung case items=null/empty, element=null, quá 50 phần tử, customerId chỉ khoảng trắng, quantity=null, các boundary 1/100 và custom constraint giao hàng. Không dùng một test hợp lệ duy nhất để kết luận mọi nhánh constraint hoạt động.

### 10.2. MockMvc kiểm status và Problem Details

Fragment bên trong test có MockMvc, Spring Security test configuration và controller/advice ở trên:

~~~java
mockMvc.perform(post("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.write")))
        .header("Idempotency-Key", "test-order-001")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"customerId":" ",
             "items":[{"sku":"","quantity":0}]}
            """))
    .andExpect(status().isBadRequest())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
    .andExpect(jsonPath("$.invalidParams").isArray());
~~~

Cần static imports cho MockMvc, Spring Security Test, result matchers; service được mock và phải **không bị gọi** khi DTO invalid. Dùng **jwt() test postprocessor** chỉ kiểm chuỗi xử lý Authentication/authority giả lập, **không chứng minh chữ ký JWT, issuer/audience hoặc tenant isolation** của production.

### 10.3. Ma trận integration/negative tests

| Tình huống | Điều phải xác minh |
|---|---|
| JSON sai cú pháp/kiểu trường | 400 MALFORMED_JSON, không 500/stack trace |
| JSON hợp lệ nhưng vi phạm @Valid | 400 VALIDATION_FAILED, chỉ ra field đúng |
| GET list limit=0 hoặc 101 | Method parameter validation hoạt động trên đúng Spring version |
| @Valid bị bỏ ở controller | Regression test phải thất bại |
| Token thiếu/hết hạn hoặc scope sai | 401/403, không lọt vào tạo đơn |
| customerId của tenant khác dù format đúng | Service từ chối, không tạo bản ghi |
| request rất lớn hoặc nhiều item | Gateway/server và @Size bảo vệ đúng tầng |
| Hai POST cùng business key | Transaction/unique constraint chặn trùng, không chỉ DTO |

Thêm test response schema trong OpenAPI, DB rollback/constraint và trường hợp nhiều lỗi cùng lúc; **không assert nguyên văn message đã dịch** làm contract máy đọc.

## 11. Bài tập thực hành

**Bài 1 — Chọn constraint.** Field quantity bắt buộc, chỉ nhận giá trị từ 1 đến 100. **Đáp án:** Dùng Integer với @NotNull, @Min(1), @Max(100); không dùng int nếu cần phát hiện thiếu trường.

**Bài 2 — Vì sao @NotEmpty chưa đủ?** customerId = "   " vẫn qua @NotEmpty. **Đáp án:** Dùng @NotBlank (cộng @Size cho giới hạn) khi không được phép chỉ có khoảng trắng.

**Bài 3 — Nested validation.** DTO có List<OrderItemInput> items; items[0].quantity=0 không bị bắt lỗi dù bên trong đã có @Min(1). **Đáp án:** Bổ sung @Valid trên container element hoặc field/collection để cascade, đồng thời @NotEmpty và @NotNull khi cần.

**Bài 4 — 400 hay 403?** Người gọi gửi customerId đúng format nhưng thuộc tenant khác. **Đáp án:** Bean Validation không cấp quyền; service phải kiểm tra ACL và trả 403/404 theo policy, không coi đó chỉ là 400 hình dạng.

**Bài 5 — Lỗi server bị map sai.** Một return DTO vi phạm constraint nội bộ, advice đang bắt mọi ConstraintViolationException rồi trả 400. **Đáp án:** Phân loại nguồn lỗi. Vi phạm invariant/return của server cần được xử lý như lỗi server và alert; không đổ cho client.

## 12. Checklist và kết luận

- [ ] DTO request tách khỏi JPA entity/response; chỉ chứa field caller được gửi?
- [ ] @NotNull/@NotEmpty/@NotBlank và số cận dùng đúng ngữ nghĩa, kể cả null?
- [ ] @Valid cascade vào object và collection elements, có giới hạn kích thước?
- [ ] Create/PATCH contract khác nhau được dùng DTO/group có chủ đích?
- [ ] Controller kích hoạt validation và trả lỗi HTTP ổn định theo contract?
- [ ] JSON parse, method validation, business conflict, auth và server error không bị đánh đồng?
- [ ] Problem Details có field path/code nhưng không lộ rejectedValue, PII hay stack trace?
- [ ] Body size/rate limit và query DB/authorization được bảo vệ ở đúng tầng?
- [ ] OpenAPI/MockMvc/unit/integration tests kiểm cả boundary, dữ liệu lồng nhau và chéo tenant?

**Kết luận:** Dùng Jakarta Bean Validation trên request DTO, @Valid/@Validated và Problem Details nhất quán để chặn dữ liệu sai. Quyền, nghiệp vụ, transaction và giới hạn tài nguyên cần được bảo vệ riêng, có kiểm thử HTTP và DB.

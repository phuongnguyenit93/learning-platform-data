# Phân biệt lỗi binding, conversion, validation và nghiệp vụ

## 1. Vì sao cần phân loại lỗi trước khi trả HTTP status?

Trong Spring MVC, một endpoint có thể nhận dữ liệu sai ở nhiều tầng. Ví dụ:

~~~http
POST /v1/orders?notify=true HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{"productId":"SKU-21","quantity":2}
~~~

Client có thể gửi JSON không hợp lệ, truyền `notify=maybe`, bỏ trống `productId`, đặt `quantity=0` hoặc yêu cầu mua sản phẩm đã ngừng bán. Kết quả đều là “không tạo được đơn”, nhưng **nguyên nhân, nơi kiểm tra, cách sửa và HTTP status** không giống nhau.

Trong chương **Dữ liệu và lỗi Spring** thuộc module **INTEGRATION_API_REST**, trọng tâm là bốn nhóm:

1. **Binding:** ánh xạ dữ liệu request vào tham số hoặc object Java.
2. **Conversion/deserialization:** biến giá trị đầu vào thành kiểu Java thích hợp.
3. **Validation:** kiểm tra ràng buộc hình thức và dữ liệu đầu vào sau khi đã tạo được object.
4. **Business/domain rules:** kiểm tra một thao tác **được phép thực hiện theo trạng thái hệ thống và quy tắc nghiệp vụ** hay không.

**Điểm mấu chốt:** đây là các *nguồn lỗi theo tầng*, không phải exception loại trừ nhau. Conversion thường nằm **trong binding**; hãy phân biệt theo **điều kiện thất bại và trách nhiệm**, không chỉ tên exception.

## 2. Đường đi của một request trong Spring MVC

~~~mermaid
flowchart TD
    A["HTTP request"] --> S["Security filters: xác thực/ủy quyền sơ bộ"]
    S --> H["Handler mapping: path + method + consumes"]
    H --> B["Argument resolution: path/query/header/body"]
    B --> C["Conversion, JSON deserialization"]
    C --> V["Bean Validation / method validation"]
    V --> D["Service: quyền resource, quy tắc nghiệp vụ"]
    D --> T["Repository, transaction, DB constraints"]
    T --> O["HTTP response / exception mapping"]
    S --> O
    H --> O
    B --> O
    C --> O
    V --> O
    D --> O
~~~

Thứ tự thực tế phụ thuộc cấu hình. Security thường chạy trước controller; JSON qua `HttpMessageConverter` khác form/query binding; validation có thể qua MVC hoặc AOP. Trả status **theo nguyên nhân**, không mặc định mọi lỗi là `400` hay `500`.

### 2.1. Ma trận nhận diện nhanh

| Nhóm | Ví dụ | Thành phần phát hiện | HTTP status thường phù hợp |
|---|---|---|---|
| **Routing/media type** | `POST` tới URL không có handler; gửi XML tới endpoint chỉ nhận JSON | Handler mapping, message converter | 404/405/415; không phải lỗi validation của DTO |
| **Binding: thiếu dữ liệu** | Thiếu `@RequestParam("page")` bắt buộc | MVC argument resolver | **400 Bad Request** |
| **Conversion** | `page=abc` cho `int`; UUID sai | `ConversionService`, argument resolver | **400** |
| **JSON deserialization** | JSON sai cú pháp, `quantity: "abc"` cho `int` | Jackson qua `HttpMessageConverter` | **400** |
| **Validation** | `@Min(1)` bị vi phạm; `@NotBlank` trống | Bean Validation / method validation | **400** theo hợp đồng thông dụng |
| **Business** | Mua sản phẩm đã ngừng bán; đơn đã PAID không được sửa | Domain service/state machine | **409 Conflict**, đôi khi **422** theo hợp đồng |
| **Đồng thời** | `If-Match` cũ, version đã đổi | HTTP precondition + transaction/CAS | **412 Precondition Failed** |
| **Authorization** | Resource ngoài tenant, user thiếu quyền | Spring Security + service policy | **401/403/404** theo ngữ nghĩa |
| **Infrastructure** | Database mất kết nối, storage timeout | Repository/driver/downstream | **500/503** phù hợp, không mặc định 400/409 |

`422 Unprocessable Content` có thể phù hợp với một số lỗi ngữ nghĩa, nhưng **Spring không tự gán mọi Bean Validation thành 422**. Bài dùng **400** cho input/validation, **409** cho domain conflict, **412** cho precondition.

## 3. Binding: gắn nguồn HTTP với tham số Java

### 3.1. Thiếu tham số, sai tên và sai cấu trúc

~~~java
@GetMapping("/v1/orders")
Page<OrderView> list(
    @RequestParam("page") int page,
    @RequestParam(name = "size", defaultValue = "20") int size
) {
    return orderService.findPage(page, size);
}
~~~

Với `GET /v1/orders?size=20`, request thiếu `page` bắt buộc. Spring MVC thường ném `MissingServletRequestParameterException`, dẫn tới **400** qua cơ chế xử lý lỗi mặc định hoặc handler tương ứng. Nếu API thiết kế `page` là optional thì **sửa hợp đồng** bằng `defaultValue`/`required=false`/`Optional`, không nên bắt mọi lỗi thiếu tham số rồi lén áp một default không có trong tài liệu.

`@RequestHeader`, `@CookieValue` và `@PathVariable` có quy tắc thiếu giá trị riêng. Riêng path variable được lấy từ URI template; **route không match** thường là **404**, còn handler đã match nhưng tham số bị thiếu do cấu hình mapping nội bộ có thể là lỗi cấu hình phía server, không thể coi tất cả là input sai.

### 3.2. Binding một form object

~~~java
record OrderFilter(
    String status,
    Integer page,
    Integer size
) {}

@GetMapping("/v1/orders/search")
List<OrderView> search(@ModelAttribute OrderFilter filter) {
    return orderService.search(filter);
}
~~~

`@ModelAttribute` bind query/form vào object. `?page=abc` gây **field error** khi chuyển sang `Integer`; tùy Spring version và signature, lỗi có thể qua `MethodArgumentNotValidException`, `BindException` hoặc `BindingResult`.

Có thể đặt `BindingResult` **ngay sau** model attribute; REST API thường dùng `@RestControllerAdvice` để chuẩn hóa lỗi tập trung.

**Cẩn trọng mass assignment:** không bind trực tiếp entity có `role`, `price`, `tenantId` hay `approved` từ các field do client đặt. Dùng DTO riêng có những field được phép sửa, whitelist và kiểm quyền. Binding thành công chỉ chứng minh **đã đưa giá trị vào object**, hoàn toàn không chứng minh **người dùng được thay đổi giá trị đó**.

## 4. Conversion và JSON deserialization

### 4.1. Chuyển query/path/header sang kiểu Java

~~~java
@GetMapping("/v1/orders/{orderId}")
OrderView get(
    @PathVariable("orderId") UUID orderId,
    @RequestParam(name = "includeItems", defaultValue = "false")
        boolean includeItems
) {
    return orderService.get(orderId, includeItems);
}
~~~

| Input | Cố chuyển thành | Kết quả |
|---|---|---|
| `/v1/orders/not-a-uuid` | `UUID` | `MethodArgumentTypeMismatchException` hoặc lỗi conversion tương ứng; thường 400 |
| `?includeItems=maybe` | `boolean` | 400 nếu không nằm trong giá trị boolean được converter chấp nhận |
| `?from=2026-13-40` | `LocalDate` với `@DateTimeFormat` | 400 vì ngày không hợp lệ |
| `?sort=invalidValue` | enum `SortMode` | 400 nếu enum converter không nhận |

Spring dùng `ConversionService`/formatter; custom `Converter<String,T>` thay đổi giá trị được phép nên phải test. **Path conversion sai không mặc định là 404**; nhưng regex trong route có thể làm request không match, khi ấy trả 404.

### 4.2. JSON body có đường xử lý khác

~~~java
record CreateOrderRequest(
    @NotBlank String productId,
    @NotNull @Min(1) Integer quantity
) {}

@PostMapping(path = "/v1/orders",
             consumes = MediaType.APPLICATION_JSON_VALUE)
ResponseEntity<OrderView> create(
    @Valid @RequestBody CreateOrderRequest request
) {
    OrderView created = orderService.create(request);
    return ResponseEntity
        .created(URI.create("/v1/orders/" + created.id()))
        .body(created);
}
~~~

| Body | Giai đoạn lỗi | Ngoại lệ thường gặp |
|---|---|---|
| `{"productId":` | JSON không đúng cú pháp | `HttpMessageNotReadableException` |
| `{"productId":"SKU","quantity":"abc"}` | Jackson không convert sang `Integer` | `HttpMessageNotReadableException` với cause Jackson |
| Body vắng khi `@RequestBody` required | Không có nội dung có thể đọc | `HttpMessageNotReadableException` |
| `{"productId":" ","quantity":0}` | Deserialize được object, nhưng constraint không đạt | `MethodArgumentNotValidException` |
| `Content-Type: text/plain` cho endpoint chỉ nhận JSON | Content type không hỗ trợ | `HttpMediaTypeNotSupportedException`, thường **415** |

Sai kiểu trong JSON thường thành `HttpMessageNotReadableException`, **khác** `MethodArgumentTypeMismatchException` của query/path. Phản hồi thông tin field/kiểu đủ sửa lỗi, không lộ raw body hay stack trace.

### 4.3. Deserialization thành công chưa nói gì về nghiệp vụ

Jackson có thể tạo object `quantity=10` và Bean Validation thấy `@Min(1)` đạt, nhưng sản phẩm chỉ cho mua tối đa 5 đơn vị do chính sách phân phối hoặc tồn kho. Đây là **quy tắc nghiệp vụ phụ thuộc dữ liệu hệ thống**, phải được service/repository kiểm tra trong transaction, không cố nhét toàn bộ vào `@Min` cố định.

## 5. Validation: object hợp kiểu nhưng vi phạm hợp đồng dữ liệu

### 5.1. Bean Validation bảo đảm điều gì?

Khi `@Valid @RequestBody CreateOrderRequest` được xử lý, Spring MVC có thể gọi Bean Validation sau khi Jackson tạo object. Các constraint phổ biến:

| Constraint | Dùng cho | Ví dụ không đạt |
|---|---|---|
| `@NotNull` | Bắt buộc có giá trị khác null | `quantity=null` |
| `@NotBlank` | Chuỗi không chỉ có whitespace | `productId="   "` |
| `@Min(1)`, `@Max(100)` | Giới hạn số | `quantity=0` |
| `@Size(min=...,max=...)` | Độ dài/size collection | Note quá dài |
| `@Pattern(regexp=...)` | Cú pháp chuỗi có quy ước | Mã tham chiếu sai format |
| `@Email` | Cú pháp email ở mức kiểm tra thường dùng | `email="not-an-email"` |
| `@Valid` trên object con | Validation lồng nhau | `address.city` trống |

Validation dạng này phù hợp với **hợp đồng dữ liệu độc lập trạng thái database**, không kiểm tra quyền truy cập. `@NotNull` với `int` primitive ít ý nghĩa khi cần phân biệt “không gửi” và số 0; nên dùng `Integer` + `@NotNull` để có lỗi dễ hiểu.

~~~java
record ShippingAddress(
    @NotBlank String city,
    @NotBlank String street
) {}

record NewOrderRequest(
    @NotBlank String productId,
    @NotNull @Min(1) @Max(100) Integer quantity,
    @Valid @NotNull ShippingAddress address
) {}
~~~

Nếu `address=null`, `@NotNull` trên address phát lỗi. Nếu `address.city=""`, `@Valid` giúp kiểm tra trường lồng nhau. Nếu không có `@Valid` ở property nested, không nên tự cho rằng mọi constraint của object con đều được chạy.

### 5.2. DTO validation khác method validation

Hai trường hợp cần phân biệt:

~~~java
// DTO/body validation: MethodArgumentNotValidException thường gặp.
ResponseEntity<OrderView> create(
    @Valid @RequestBody NewOrderRequest body
) { /* ... */ }

// Constraint trực tiếp trên method parameter:
List<OrderView> list(
    @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit
) { /* ... */ }
~~~

Với Spring Framework **6.1+**, MVC có hỗ trợ **method validation tích hợp**; constraint trực tiếp trên method parameter có thể dẫn tới `HandlerMethodValidationException`. Ở cấu hình khác, `@Validated`/AOP có thể làm phát sinh exception khác, như `ConstraintViolationException`. Khi bắt các loại này, cần bám đúng **phiên bản Framework và cơ chế validation thực tế**.

Annotation chưa đủ: cần Bean Validation provider (thường `spring-boot-starter-validation`), cấu hình method validation đúng và test `limit=1000`. Trên Spring MVC 6.1+, class-level `@Validated` có thể chuyển đường validation sang AOP.

### 5.3. Kiểm tra liên trường và thứ tự xử lý

Ví dụ `startDate <= endDate` là validation phụ thuộc **hai trường trong cùng request**; có thể dùng class-level constraint/custom validator. Nhưng “ngày kết thúc phải trước thời gian đóng sổ hiện hành của tenant” đụng tới trạng thái nghiệp vụ; giữ kiểm tra này trong service cùng dữ liệu authoritative.

Không dùng exception message của annotation (có thể chứa tên class nội bộ hoặc giá trị nhạy cảm) làm body lỗi thẳng. Trả **field/path và mã lỗi ổn định**, bản dịch thông báo phù hợp, nhưng không trả toàn bộ đối tượng request.

## 6. Lỗi nghiệp vụ: dữ liệu hợp lệ nhưng thao tác không hợp lệ

### 6.1. Một thao tác có thể bị từ chối sau validation

Client gửi:

~~~http
POST /v1/orders HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "productId": "SKU-21",
  "quantity": 2,
  "address": {"city":"Hà Nội","street":"10 Phố Huế"}
}
~~~

JSON hợp lệ, object tạo thành công và mọi constraint của DTO đều đạt. Service vẫn phải kiểm tra:

- Principal có quyền tạo đơn cho tenant đang hoạt động không?
- Product `SKU-21` có tồn tại **trong phạm vi được phép nhìn thấy** không?
- Product có đang bán, trong hạn mức hoặc đủ tồn kho không?
- Giỏ/checkout session đã được xử lý trước đó chưa?
- Cùng một `Idempotency-Key` có phải retry cùng ý định hay bị dùng lại cho payload khác?

Những câu hỏi này không thể giải quyết bằng conversion hay `@NotBlank`. Service phải đọc trạng thái **đáng tin cậy tại thời điểm thực thi**, dùng transaction/constraint để xử lý race. Không kiểm tra tồn kho một lần ở controller rồi khẳng định nó còn đúng sau khi transaction khác đã mua hết.

### 6.2. Định nghĩa domain exception theo ý nghĩa

~~~java
public class ProductUnavailableException extends RuntimeException {
    public ProductUnavailableException() {
        super("Product cannot be ordered now");
    }
}

public class OrderAlreadySubmittedException extends RuntimeException {
    public OrderAlreadySubmittedException() {
        super("Order already submitted");
    }
}
~~~

Tránh ném `IllegalArgumentException` cho mọi lỗi domain: nó dễ bị nhầm với lỗi lập trình hoặc input conversion và khó ánh xạ đúng status. **Exception riêng hoặc kết quả domain có kiểu rõ ràng** giúp giữ hợp đồng ổn định, đồng thời không để controller phụ thuộc message tùy ý.

### 6.3. 409, 422, 404 và 403: chọn theo ngữ nghĩa

| Tình huống | Status hợp lý | Lý do |
|---|---|---|
| Dữ liệu JSON/constraint không hợp lệ theo hợp đồng đầu vào | **400** | Client cần sửa cú pháp/giá trị |
| Đơn đang `PAID`, yêu cầu chuyển lại `DRAFT` | **409 Conflict** | Xung đột với **trạng thái hiện tại** |
| Sản phẩm trong giỏ đã hết hàng sau khi client đọc | **409** hoặc **422** theo API contract | Quy tắc nghiệp vụ không thể thỏa; mô tả cách khắc phục |
| Yêu cầu có nội dung hiểu được nhưng vi phạm quy tắc bất biến độc lập trạng thái | **422** nếu API chọn và tài liệu hóa | Không phải lỗi deserialize; không có quy tắc bắt buộc cho mọi domain |
| Resource không tồn tại hoặc không được tiết lộ | **404 Not Found** | Không để ID ngoài tenant trở thành oracle |
| User đã xác thực, có thể biết resource nhưng không được sửa | **403 Forbidden** | Thiếu quyền |
| Không có credential hợp lệ | **401 Unauthorized** | Thường kèm `WWW-Authenticate` phù hợp |
| `If-Match` được gửi nhưng stale | **412 Precondition Failed** | Thất bại của **điều kiện HTTP** |
| API yêu cầu `If-Match` nhưng request không gửi | **428 Precondition Required** | Policy bắt buộc precondition |

**409 không dành cho mọi lỗi DB.** Unique constraint có thể tương ứng 409 khi là xung đột nghiệp vụ; foreign key do bug hoặc schema lệch, deadlock và DB outage phải xử lý theo nguyên nhân, không map mù thành 409.

### 6.4. Lỗi đồng thời phải được bắt ở điểm ghi

Ví dụ hai transaction cùng đọc đơn version 7, cùng đổi trạng thái. Cả hai có thể vượt qua kiểm tra `if (status == DRAFT)` tại service, nhưng **chỉ một** được commit nếu dùng `@Version`, lock hoặc câu SQL CAS phù hợp.

~~~sql
UPDATE orders
SET status = 'SUBMITTED',
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND status = 'DRAFT'
  AND version = :expectedVersion;
~~~

Nếu số row cập nhật bằng 0, cần kiểm tra lại **trong phạm vi được phép** để phân biệt resource không thấy, sai version và trạng thái domain. Nếu client thực sự dùng `If-Match` và điều kiện sai, **412** thường phù hợp; nếu dùng lệnh nghiệp vụ không có HTTP precondition và state không cho phép, **409** thường phù hợp. `ObjectOptimisticLockingFailureException` từ Spring Data/JPA không nên được map cứng một status cho mọi endpoint: nó còn phụ thuộc contract precondition.

### 6.5. Lỗi từ database không nên bị lộ nguyên văn

Đừng trả tên bảng/constraint, SQL, stack trace hoặc thông báo driver như “duplicate key violates unique index ...” tới client. Map thành `code` nghiệp vụ có nghĩa, ví dụ `ORDER_REFERENCE_ALREADY_EXISTS`, sau khi xác định đúng constraint có thể xử lý. Log nội bộ cần correlation ID và đủ ngữ cảnh phi nhạy cảm để điều tra, không log raw token hay toàn bộ payload cá nhân.

## 7. Chuẩn hóa lỗi HTTP với Problem Details

Thay vì mỗi controller trả body lỗi khác nhau, API có thể dùng **RFC 9457 Problem Details** với media type `application/problem+json`. Các trường chuẩn gồm `type`, `title`, `status`, `detail`, `instance`; ứng dụng có thể bổ sung extension như `code` và `invalidParams`.

### 7.1. Hai lỗi khác nguyên nhân, cùng 400

**Lỗi conversion của query parameter:**

~~~http
GET /v1/orders?page=abc HTTP/1.1

HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/invalid-parameter",
  "title": "Invalid parameter",
  "status": 400,
  "code": "INVALID_PARAMETER",
  "detail": "Tham số page phải là số nguyên."
}
~~~

**Lỗi Bean Validation của request body:**

~~~http
POST /v1/orders HTTP/1.1
Content-Type: application/json

{"productId":" ","quantity":0}

HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "invalidParams": [
    {"name":"productId","code":"NotBlank"},
    {"name":"quantity","code":"Min"}
  ]
}
~~~

Hai response cùng status **400** nhưng `code` giúp client biết nên sửa **cú pháp/kiểu tham số** hay **giá trị trường dữ liệu**. Tên field trong `invalidParams` phải là tên public contract, không phải đường dẫn nhạy cảm nội bộ. `detail` có thể dịch sang ngôn ngữ người dùng; client **không nên parse text** để xác định loại lỗi.

### 7.2. Spring @RestControllerAdvice

Mã sau minh họa một cách ánh xạ theo **Spring Boot 3 / Spring Framework 6.1+**. Các import thông thường được lược bớt. Đây là handler độc lập, **không extends `ResponseEntityExceptionHandler`** để tránh xung đột giữa handler tùy biến và các handler sẵn có của superclass.

~~~java
@RestControllerAdvice
class ApiProblemHandler {

    @ExceptionHandler(MissingServletRequestParameterException.class)
    ResponseEntity<ProblemDetail> missingQuery(
            MissingServletRequestParameterException ex) {
        return error(HttpStatus.BAD_REQUEST, "MISSING_PARAMETER",
            "Thiếu tham số bắt buộc: " + ex.getParameterName());
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<ProblemDetail> conversion(
            MethodArgumentTypeMismatchException ex) {
        return error(HttpStatus.BAD_REQUEST, "INVALID_PARAMETER",
            "Kiểu dữ liệu không hợp lệ cho: " + ex.getName());
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ProblemDetail> unreadableBody(
            HttpMessageNotReadableException ex) {
        return error(HttpStatus.BAD_REQUEST, "INVALID_JSON_BODY",
            "Không thể đọc request body theo schema yêu cầu.");
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> invalidBody(
            MethodArgumentNotValidException ex) {
        ProblemDetail pd = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        pd.setTitle("Validation failed");
        pd.setType(URI.create(
            "https://api.example.com/problems/validation-failed"));
        pd.setProperty("code", "VALIDATION_FAILED");
        pd.setProperty("invalidParams",
            ex.getBindingResult().getFieldErrors().stream()
                .map(f -> Map.of(
                    "name", f.getField(),
                    "code", String.valueOf(f.getCode())))
                .toList());
        return ResponseEntity.badRequest()
            .contentType(MediaType.parseMediaType("application/problem+json"))
            .cacheControl(CacheControl.noStore())
            .body(pd);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<ProblemDetail> invalidMethodArgument(
            HandlerMethodValidationException ex) {
        return error(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED",
            "Một hoặc nhiều tham số không đạt ràng buộc.");
    }

    @ExceptionHandler(OrderAlreadySubmittedException.class)
    ResponseEntity<ProblemDetail> orderConflict(
            OrderAlreadySubmittedException ex) {
        return error(HttpStatus.CONFLICT, "ORDER_ALREADY_SUBMITTED",
            "Đơn đã được gửi và không thể gửi lại.");
    }

    private ResponseEntity<ProblemDetail> error(
            HttpStatus status, String code, String detail) {
        ProblemDetail pd =
            ProblemDetail.forStatusAndDetail(status, detail);
        pd.setType(URI.create(
            "https://api.example.com/problems/"
            + code.toLowerCase(Locale.ROOT).replace('_', '-')));
        pd.setProperty("code", code);
        return ResponseEntity.status(status)
            .contentType(MediaType.parseMediaType("application/problem+json"))
            .cacheControl(CacheControl.noStore())
            .body(pd);
    }
}
~~~

`HandlerMethodValidationException` là lựa chọn cho MVC method validation trên Spring Framework 6.1+. Nếu project dùng Boot/Framework cũ hoặc AOP validation, loại lỗi có thể khác; phải điều chỉnh handler theo phiên bản và test. Cần import `ProblemDetail`, `HttpStatus`, `ResponseEntity`, `URI`, `Locale`, `Map`, Spring MVC exceptions và các domain exception đã định nghĩa.

Handler trên chưa bao phủ `MissingRequestHeaderException`, `HttpMediaTypeNotSupportedException`, `BindException`, lỗi security, optimistic locking hay lỗi hạ tầng; **đó là những đường cần bổ sung theo hợp đồng thực**. Không viết catch-all tự động trả 400 vì nó che bug/lỗi hạ tầng.

### 7.3. Error taxonomy và log nội bộ

Thống nhất **HTTP status** (400/403/404/409/412/500) với **application code** (`INVALID_PARAMETER`, `VALIDATION_FAILED`...). Có thể thêm `requestId`/`traceId` đã chuẩn hóa để tra cứu; lỗi hệ thống phải trả thông báo trung tính, giữ SQL/stack trace trong log được bảo vệ.

## 8. Bảo mật: validation không thay authorization

Ví dụ người dùng gửi `GET /v1/orders/{uuid}` với UUID hợp lệ: đó là **conversion thành công**, không có nghĩa họ được xem đơn. Tương tự `@NotBlank String tenantId` chỉ xác nhận tenant ID không rỗng, không chứng minh tenant ấy thuộc principal.

**Thứ tự suy luận an toàn:** xác thực principal; xác định tenant/scope từ nguồn đáng tin; truy vấn resource trong phạm vi đó; kiểm tra quyền và business state; chỉ khi được phép mới phản hồi lỗi có thể tiết lộ trạng thái resource. Nếu một ID thuộc tenant khác, API thường trả **404 trung tính** thay vì 409 “đơn đã thanh toán”, vì thông báo 409 sẽ tiết lộ đơn tồn tại.

Security filter có thể từ chối trước controller. `@RestControllerAdvice` không tự định nghĩa body `401/403` từ filter; cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` nếu cần Problem Details thống nhất. Không mở `permitAll` để “sửa” lỗi.

Đối với body dữ liệu không tin cậy, hạn chế kích thước upload, độ sâu JSON, trường lạ và rate limit ở gateway/app. Không bind entity database trực tiếp; validate DTO, nhưng **check authorization lại khi ghi**. Đặc biệt, uniqueness/inventory/state phụ thuộc transaction: Bean Validation không thể ngăn hai request đua nhau ghi cùng một resource.

## 9. Kiểm thử: phải chứng minh từng nhánh lỗi

### 9.1. Ma trận kiểm thử HTTP

| Test | Request/tình huống | Kỳ vọng |
|---|---|---|
| E01 | Thiếu `page` bắt buộc | **400**, `MISSING_PARAMETER` |
| E02 | `page=abc` khi Java cần `int` | **400**, `INVALID_PARAMETER` |
| E03 | `/orders/not-a-uuid` | **400** nếu route khớp và UUID conversion lỗi |
| E04 | `Content-Type: text/plain` tới JSON-only endpoint | **415 Unsupported Media Type** |
| E05 | JSON bị thiếu dấu ngoặc | **400**, `INVALID_JSON_BODY` |
| E06 | `quantity="xyz"` khi DTO cần `Integer` | **400**, lỗi deserialization |
| E07 | `quantity=0`, `productId=" "` | **400**, `VALIDATION_FAILED` và field errors |
| E08 | `limit=1000` vi phạm method constraint | **400** sau khi cấu hình method validation đúng |
| E09 | Payload hợp lệ nhưng đơn đã SUBMITTED | **409**, `ORDER_ALREADY_SUBMITTED` |
| E10 | `If-Match` stale trên PATCH | **412**; không có side effect |
| E11 | User tenant B gọi order tenant A | **404** trung tính, không tiết lộ status |
| E12 | Token thiếu/hết hạn; quyền không đủ | **401/403** qua Spring Security |
| E13 | DB outage khi xử lý | **5xx** phù hợp, không bị ánh xạ thành validation 400 |
| E14 | Hai request cùng tranh chấp cập nhật | Không có lost update; status theo precondition/domain contract |

### 9.2. MockMvc với dữ liệu sai ở ba tầng

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ApiErrorContractTest {
    @Autowired MockMvc mvc;

    @Test
    void wrongQueryTypeIsConversionError() throws Exception {
        mvc.perform(get("/v1/orders").param("page", "abc")
                .with(jwt()))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"));
    }

    @Test
    void malformedJsonIsNotBeanValidationError() throws Exception {
        mvc.perform(post("/v1/orders")
                .with(jwt())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"productId\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON_BODY"));
    }

    @Test
    void validJsonWithBadFieldsTriggersValidation() throws Exception {
        mvc.perform(post("/v1/orders")
                .with(jwt())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"productId\":\" \",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.invalidParams").isArray());
    }
}
~~~

Test dùng Spring Security Test `jwt()`, chỉ mô phỏng principal có quyền phù hợp; nó **không kiểm chứng chữ ký/issuer/audience JWT thật**. Cần fixture service/repository, import JUnit/MockMvc và các DTO/handler như ví dụ. Nếu API yêu cầu `Idempotency-Key`, test phải thêm header hợp lệ để **chạm đúng tầng cần đo**. Với lỗi nghiệp vụ, dùng fixture trạng thái domain rõ ràng; ngoài HTTP status hãy assert **database không đổi** và response không lộ thông tin nhạy cảm.

### 9.3. Kiểm thử ranh giới transaction và bảo mật

Test lost update/unique constraint bằng hai transaction đồng thời trên database tương tự production; kiểm tra rollback và outcome. Test `401/403` từ filter riêng, so sánh response runtime với OpenAPI để phát hiện drift.

## 10. Bài tập phân loại lỗi

**Đề bài:** endpoint `PATCH /v1/orders/{orderId}` nhận JSON `{"quantity":...}`, dùng `@Valid`, `If-Match` và kiểm tra trạng thái đơn là DRAFT. Hãy xác định **tầng lỗi và status** cho từng trường hợp:

1. `orderId=hello`, controller nhận `UUID`.
2. Body `{"quantity":"two"}` với field `Integer`.
3. Body `{"quantity":0}`, DTO có `@Min(1)`.
4. Body `{"quantity":2}` hợp lệ, nhưng đơn đã PAID.
5. Body hợp lệ, đơn DRAFT, nhưng `If-Match` đã cũ.
6. UUID hợp lệ nhưng là đơn thuộc tenant khác.

**Đáp án tham khảo:**

| Ca | Tầng nguyên nhân | Kết quả |
|---|---|---|
| 1 | Path **conversion** | **400** nếu route khớp |
| 2 | JSON **deserialization/conversion** | **400** |
| 3 | **Bean Validation** | **400** theo hợp đồng ví dụ |
| 4 | **Domain state conflict** | **409** |
| 5 | **HTTP precondition** | **412** |
| 6 | **Authorization/visibility** | **404 trung tính** theo chính sách, không trả 409 làm lộ trạng thái |

**Câu hỏi nâng cao:** nếu hai request cùng pass validation rồi cùng giảm tồn kho, có thể ngăn âm kho bằng `@Min` không? **Không.** Đó là invariant phụ thuộc trạng thái shared; cần kiểm tra ở database/transaction, CAS hoặc lock phù hợp, đồng thời ánh xạ conflict có nghĩa.

## 11. Checklist thiết kế và tài liệu tham khảo

- [ ] Phân biệt **route/binding**, **conversion/deserialization**, **validation** và **domain rule** trong code lẫn tài liệu.
- [ ] Thiếu tham số, sai kiểu, JSON sai cú pháp và constraint fail có `code` riêng, status thống nhất.
- [ ] Không nhầm lỗi JSON type với `MethodArgumentTypeMismatchException` của query/path.
- [ ] `@Valid` và method validation được kích hoạt/test theo đúng Spring version.
- [ ] Domain exception có ngữ nghĩa rõ; không map mọi `DataIntegrityViolationException` thành 409.
- [ ] HTTP precondition 412/428 được tách khỏi business conflict 409.
- [ ] `ProblemDetail` dùng schema ổn định, không lộ SQL, token, raw body hay stack trace.
- [ ] Authentication/authorization và tenant isolation có test riêng; không dùng Bean Validation làm kiểm soát quyền.
- [ ] Transaction/CAS/unique constraint chống race, không chỉ kiểm tra trước ở service.
- [ ] OpenAPI document response/errors thực tế; MockMvc test thành công, lỗi và side effect.

**Đọc thêm:** [Spring MVC validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html), [Method arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html), [Spring MVC exception handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html), [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457), [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).

**Kết luận:** binding đưa input HTTP vào tham số/object; conversion và JSON deserialization tạo kiểu dữ liệu; validation kiểm tra ràng buộc; còn domain service quyết định thao tác có hợp lệ với **trạng thái và quyền hiện tại** không. Đặt kiểm tra đúng tầng, map HTTP status/Problem Details nhất quán và kiểm chứng với MockMvc lẫn database concurrency tests sẽ tạo API dễ sử dụng, an toàn và dễ bảo trì.

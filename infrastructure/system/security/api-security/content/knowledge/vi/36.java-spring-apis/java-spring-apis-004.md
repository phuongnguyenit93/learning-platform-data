# Bean Validation và request size limit

## 1. Vì sao validation và giới hạn request phải đi cùng nhau?

API nhận dữ liệu từ client, partner hoặc service khác. Dữ liệu có thể thiếu field, sai kiểu, vượt miền giá trị, chứa cấu trúc lồng nhau quá lớn hoặc có kích thước đủ để làm cạn bộ nhớ và CPU. Một request được xác thực thành công vẫn có thể gây lỗi nghiệp vụ, làm hỏng dữ liệu hoặc tiêu tốn tài nguyên nếu server không kiểm tra đầu vào.

Trong Java và Spring, Bean Validation giúp diễn đạt các ràng buộc trên DTO, method parameter và object graph. Các annotation như `@NotBlank`, `@Size`, `@Positive` hoặc custom constraint giúp phát hiện dữ liệu không hợp lệ sớm và nhất quán.

Tuy nhiên, validation ở DTO thường chạy sau khi HTTP body đã được đọc và deserialize thành object. Vì vậy, `@Size(max = 100)` trên một `String` không ngăn một client gửi body JSON hàng trăm megabyte trước khi validator được gọi. Cần có giới hạn kích thước ở gateway/proxy, servlet container và tầng xử lý ứng dụng phù hợp với từng loại endpoint.

Hai lớp kiểm soát giải quyết hai vấn đề khác nhau:

- **Bean Validation:** dữ liệu đã parse có đúng cấu trúc, miền giá trị và quy tắc nghiệp vụ đầu vào không?
- **Request size/resource limits:** server có chấp nhận đọc, parse và xử lý lượng dữ liệu này không?

Đừng dùng validation thay authorization, sanitization hoặc rate limiting. Một request hợp lệ về kiểu dữ liệu vẫn có thể không được phép thực hiện; một request nhỏ vẫn có thể gây lạm dụng nếu được gửi liên tục.

## 2. Thêm Bean Validation vào Spring Boot

Với Spring Boot, thêm starter validation vào build để có provider triển khai Jakarta Bean Validation:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
```

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Spring MVC kích hoạt validation trên request DTO khi parameter được đánh dấu `@Valid` hoặc `@Validated` theo cách dùng phù hợp. Hãy validate request DTO riêng thay vì bind trực tiếp request vào JPA entity/domain entity; DTO cho phép xác định chính xác field nào client được gửi.

## 3. Các constraint cơ bản thường dùng

| Constraint | Mục đích | Lưu ý |
|---|---|---|
| `@NotNull` | Giá trị không được là `null`. | Không cấm chuỗi rỗng hoặc list rỗng. |
| `@NotBlank` | Chuỗi phải có ít nhất một ký tự không phải whitespace. | Chỉ dùng cho `CharSequence`. |
| `@NotEmpty` | Chuỗi, collection, map hoặc array không được rỗng. | Chuỗi toàn dấu cách vẫn có thể qua; dùng `@NotBlank` nếu cần. |
| `@Size(min, max)` | Giới hạn độ dài/kích thước chuỗi, collection, map hoặc array. | Không giới hạn số byte của toàn HTTP body. |
| `@Positive`, `@PositiveOrZero` | Giới hạn số dương hoặc không âm. | Chọn theo miền giá trị nghiệp vụ. |
| `@Min`, `@Max`, `@DecimalMin`, `@DecimalMax` | Giới hạn miền số. | Với tiền, dùng `BigDecimal` và scale/precision phù hợp. |
| `@Email` | Kiểm tra định dạng email cơ bản. | Không chứng minh địa chỉ tồn tại hoặc người gửi sở hữu địa chỉ. |
| `@Pattern` | Kiểm tra chuỗi theo regular expression. | Tránh regex có backtracking quá lớn gây ReDoS. |
| `@Past`, `@Future` | Kiểm tra quan hệ thời gian. | Cần cân nhắc timezone và clock source. |

Các constraint phải phù hợp với kiểu dữ liệu. Ví dụ `@NotBlank` không thay thế `@NotNull` cho mọi loại field; `@Size` trên chuỗi không giới hạn byte sau UTF-8 encoding; `@Email` không phải xác minh danh tính.

## 4. Validate request bằng DTO

Ví dụ API tạo đơn hàng chỉ nhận những field client được phép cung cấp:

```java
public record CreateOrderRequest(
    @NotBlank
    @Size(max = 80)
    String reference,

    @NotNull
    @DecimalMin(value = "0.01")
    @Digits(integer = 10, fraction = 2)
    BigDecimal amount,

    @NotEmpty
    @Size(max = 50)
    List<@NotNull @Valid CreateOrderLineRequest> items
) {}

public record CreateOrderLineRequest(
    @NotBlank
    @Size(max = 40)
    String productCode,

    @NotNull
    @Positive
    @Max(1000)
    Integer quantity
) {}
```

Controller kích hoạt validation:

```java
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
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

`@Valid` trên list element khiến từng line item được kiểm tra, không chỉ kiểm tra list có rỗng hay không. Nếu thiếu `@Valid`, các constraint bên trong `CreateOrderLineRequest` có thể không chạy theo object graph như mong đợi.

DTO không có các field như `tenantId`, `ownerId`, `role`, `paymentStatus` hoặc `approvedBy` nếu caller không được phép đặt chúng. Những giá trị đó phải lấy từ principal, policy hoặc workflow server-side. Validation kiểm tra dữ liệu được phép gửi; nó không biến field đặc quyền thành field hợp lệ chỉ vì giá trị đúng kiểu.

## 5. Validate object lồng nhau và collection

Request có thể chứa object nhiều cấp hoặc collection lớn. Cần kiểm tra từng phần tử và giới hạn số phần tử tối đa.

```java
public record CreateBatchRequest(
    @NotBlank
    @Size(max = 60)
    String batchReference,

    @NotEmpty
    @Size(max = 100)
    List<@NotNull @Valid BatchItemRequest> items
) {}

public record BatchItemRequest(
    @NotNull UUID resourceId,
    @NotBlank @Size(max = 30) String action
) {}
```

`@Size(max = 100)` giới hạn số item sau khi collection được tạo. Nó không thay thế body byte limit vì một item có thể chứa chuỗi rất lớn, JSON lồng sâu hoặc field dư trước khi object được validate. Đặt giới hạn đồng thời cho:

- Tổng số byte của HTTP body.
- Số phần tử trong mỗi collection/batch.
- Độ dài từng chuỗi và số field được phép.
- Độ sâu JSON hoặc cấu trúc lồng nhau nếu parser hỗ trợ giới hạn.
- Tổng chi phí xử lý, query và downstream call của một batch.

Không nhận `Map<String, Object>` hoặc JSON động không giới hạn nếu nghiệp vụ không cần. Cấu trúc linh hoạt cần schema allowlist, giới hạn số key, key length, value type và nesting depth.

## 6. Cross-field validation và quy tắc nghiệp vụ

Một số điều kiện không thể kiểm tra bằng constraint trên một field, ví dụ `startDate` phải trước `endDate`, hoặc `discount` không được lớn hơn `subtotal`.

Có thể tạo class-level constraint:

```java
@ValidDateRange
public record BookingRequest(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {}
```

Annotation và validator minh họa:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "Invalid date range";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}

public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingRequest> {
    @Override
    public boolean isValid(
            BookingRequest value,
            ConstraintValidatorContext context) {
        if (value == null || value.startDate() == null || value.endDate() == null) {
            return true; // Field-level @NotNull reports missing values.
        }
        return value.startDate().isBefore(value.endDate());
    }
}
```

Validator trả `true` khi field bắt buộc còn thiếu để lỗi `@NotNull` được báo đúng vị trí; nếu trả false đồng thời, response có thể có lỗi trùng lặp. Có thể dùng `ConstraintValidatorContext` để gắn violation vào property cụ thể nếu cần.

Các quy tắc phụ thuộc dữ liệu hiện tại, ví dụ tồn kho đủ hay user còn thuộc tenant, thường cần kiểm tra trong service/domain layer và transaction. Không truy vấn database trong mọi annotation một cách tùy tiện vì có thể gây N+1 query, race condition hoặc làm validator khó kiểm thử. Ràng buộc cuối cùng phải được bảo vệ ở domain/database khi có concurrency.

## 7. Method validation trong service layer

Validation tại controller bảo vệ HTTP boundary. Service có thể được gọi từ queue consumer, scheduler hoặc service khác, vì vậy các invariant quan trọng không nên chỉ phụ thuộc controller.

Ví dụ dùng method validation:

```java
@Service
@Validated
public class TransferService {
    public TransferResult transfer(
            @NotNull UUID sourceAccountId,
            @NotNull UUID destinationAccountId,
            @NotNull @Positive BigDecimal amount) {

        if (sourceAccountId.equals(destinationAccountId)) {
            throw new IllegalArgumentException("Accounts must differ");
        }
        return performTransfer(sourceAccountId, destinationAccountId, amount);
    }
}
```

Method validation cần được kích hoạt qua Spring proxy và cấu hình phù hợp; self-invocation trong cùng bean có thể không đi qua proxy. Hãy kiểm tra hành vi thực tế với test. `@NotNull`/`@Positive` không thay thế authorization: service vẫn phải xác minh caller được chuyển tiền từ account đó và nghiệp vụ có đủ điều kiện.

## 8. Validation groups cho create và update

Một DTO có thể có yêu cầu khác nhau giữa create và update. Bean Validation groups cho phép chọn tập constraint theo operation, nhưng nên dùng có chủ đích để tránh policy khó đọc.

```java
public interface Create {}
public interface Update {}

public record ProfileRequest(
    @NotBlank(groups = Create.class)
    @Size(max = 80, groups = {Create.class, Update.class})
    String displayName,

    @NotNull(groups = Create.class)
    @Email(groups = {Create.class, Update.class})
    String email
) {}
```

Controller có thể kích hoạt group tương ứng bằng `@Validated(Create.class)` hoặc `@Validated(Update.class)` theo cách Spring MVC được cấu hình. Với PATCH, cần định nghĩa rõ khác biệt giữa field bị bỏ qua, field `null` và field rỗng; Bean Validation đơn thuần không quyết định semantics của partial update.

Không dùng validation group để biểu diễn role hoặc quyền truy cập. Role là authorization concern; validation group chỉ chọn tập ràng buộc dữ liệu. Cùng một DTO không nên cho phép caller tự chọn group qua request field.

## 9. Kiểm tra enum, identifier và format

Với enum, nên dùng kiểu Java enum hoặc custom parser từ allowlist. Không nhận chuỗi tùy ý rồi dùng reflection/class name để tạo type.

Với identifier:

- Kiểm tra format/length trước khi truy vấn.
- Không coi UUID khó đoán là authorization.
- Không cho client tự đặt tenant/owner identity nếu policy yêu cầu server xác định.
- Không log raw identifier nhạy cảm nếu không cần.

Với regex:

- Dùng pattern đơn giản, có giới hạn input length.
- Tránh nested quantifier hoặc cấu trúc backtracking có thể gây ReDoS.
- Test với chuỗi dài và input bất thường.
- Nếu có thư viện parser chuyên biệt cho format phức tạp, ưu tiên parser đó.

`@Email` chỉ kiểm tra cú pháp theo provider, không xác minh mailbox. `@Pattern` chỉ xác nhận chuỗi khớp biểu thức, không làm HTML/SQL/shell trở nên an toàn. Encode theo output context và dùng parameterized query/allowlist ở đúng tầng.

## 10. Trả lỗi validation an toàn và nhất quán

Spring MVC thường ném `MethodArgumentNotValidException` khi `@Valid @RequestBody` không đạt constraint. Tùy phiên bản Spring Framework và cách khai báo parameter, method validation có thể dùng `HandlerMethodValidationException` hoặc `ConstraintViolationException`.

Response nên cho client biết field nào không hợp lệ và mã lỗi ổn định, nhưng không trả rejected value, stack trace, class name, SQL hoặc dữ liệu nội bộ.

Ví dụ với `ProblemDetail`:

```java
@RestControllerAdvice
public class ApiValidationAdvice {
    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> handleValidation(
            MethodArgumentNotValidException exception) {

        List<Map<String, String>> errors = exception.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> Map.of(
                "field", error.getField(),
                "code", safeCode(error.getCode())
            ))
            .toList();

        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        problem.setTitle("Request validation failed");
        problem.setDetail("One or more fields are invalid.");
        problem.setProperty("errors", errors);

        return ResponseEntity.badRequest().body(problem);
    }

    private String safeCode(String code) {
        return switch (code == null ? "" : code) {
            case "NotNull", "NotBlank", "NotEmpty", "Size",
                 "Positive", "PositiveOrZero", "Email", "Pattern",
                 "DecimalMin", "DecimalMax", "Digits" -> code;
            default -> "InvalidValue";
        };
    }
}
```

`ProblemDetail` có trong các phiên bản Spring Framework hiện đại. Với phiên bản cũ hơn, dùng error response DTO theo contract. Không đưa `FieldError.getRejectedValue()` vào response hoặc log vì nó có thể chứa password, token, PII hay nội dung lớn. `getDefaultMessage()` cũng nên được kiểm soát để tránh lộ chi tiết implementation.

Quy ước status thường gặp:

| Tình huống | Status thường dùng |
|---|---:|
| JSON/field không hợp lệ | `400 Bad Request` |
| Request body vượt giới hạn | `413 Content Too Large` (còn được gọi là Payload Too Large) |
| Content-Type không được endpoint hỗ trợ | `415 Unsupported Media Type` |
| Thiếu/sai authentication | `401 Unauthorized` |
| Đã xác thực nhưng không đủ quyền | `403 Forbidden` hoặc `404` theo policy che giấu resource |
| Vượt rate limit | `429 Too Many Requests` |

Không dùng `400` cho mọi loại lỗi vì client và monitoring cần phân biệt validation với body size, authentication và rate limit.

## 11. Vì sao `@Size` không phải request body size limit?

Giả sử DTO có:

```java
public record SearchRequest(
    @Size(max = 100) String query
) {}
```

Constraint này kiểm tra độ dài `query` sau khi JSON đã được đọc và deserialize. Nó không giới hạn:

- Tổng số byte HTTP body.
- Số field dư mà DTO không dùng.
- JSON nesting depth hoặc cấu trúc parser phải duyệt.
- Số phần tử trong một collection khác nếu không có constraint tương ứng.
- Số byte đã được giải nén khi request dùng content encoding.
- Thời gian CPU hoặc số truy vấn database phát sinh từ dữ liệu hợp lệ.

Độ dài chuỗi Java cũng không đồng nghĩa với số byte UTF-8 truyền qua mạng. Ví dụ ký tự Unicode có thể chiếm nhiều byte. Vì vậy cần kiểm tra ở cả tầng transport và tầng DTO/domain.

## 12. Đặt giới hạn request theo nhiều lớp

Không có một property Spring duy nhất áp dụng đồng nhất cho mọi HTTP body và mọi servlet container. Hãy đặt giới hạn ở các lớp có thể từ chối request sớm:

1. **CDN/WAF/API gateway/reverse proxy:** giới hạn body trước khi request vào application, áp theo route/content type và chặn traffic quá lớn.
2. **Servlet container:** cấu hình giới hạn header, form parsing, multipart và connection theo container đang dùng.
3. **Application:** kiểm tra `Content-Length` khi có, giới hạn bytes thực tế khi streaming, giới hạn collection/parser và số phần tử.
4. **Business/service:** giới hạn cost, số operation, số downstream calls, thời gian và concurrency.

Ví dụ Nginx ở reverse proxy:

```nginx
server {
    client_max_body_size 1m;

    location /api/search {
        proxy_pass http://api_backend;
    }

    location /api/files {
        client_max_body_size 10m;
        proxy_pass http://api_backend;
    }
}
```

Ví dụ chỉ minh họa cách đặt limit theo location. Nginx có thể trả `413` trước khi request tới Spring. Cần cấu hình tương ứng trên mọi ingress path; nếu một route có thể đi vòng qua proxy hoặc gọi thẳng backend, giới hạn ở edge không đủ.

Chọn mức giới hạn dựa trên contract. Endpoint tìm kiếm JSON có thể chỉ cần vài trăm KB; endpoint upload có thể cần lớn hơn nhưng phải có quota, streaming và file scanning. Không tăng limit toàn hệ thống chỉ để hỗ trợ một endpoint đặc biệt.

## 13. Giới hạn ở Spring Boot và servlet container

Với multipart, Spring Boot cung cấp các cấu hình thường dùng:

```properties
spring.servlet.multipart.max-file-size=10MB
spring.servlet.multipart.max-request-size=12MB
spring.servlet.multipart.file-size-threshold=0B
```

- `max-file-size` giới hạn kích thước một file multipart.
- `max-request-size` giới hạn tổng request multipart.
- `file-size-threshold` xác định ngưỡng nội dung được giữ trong memory trước khi ghi ra disk theo cách triển khai container/framework.

Đặt multipart temp directory ở vùng riêng có permission hạn chế nếu cần cấu hình `spring.servlet.multipart.location`. Theo dõi dung lượng disk, dọn file tạm và giới hạn số part/field theo khả năng của container và application.

Một số cấu hình Tomcat như `server.tomcat.max-http-form-post-size` liên quan tới kích thước dữ liệu form được parse thành request parameters; không được mặc định coi đây là giới hạn tổng byte cho mọi JSON body. `server.max-http-request-header-size` giới hạn header, không phải body. Đọc tài liệu đúng phiên bản container đang chạy và kiểm thử bằng request thật.

Đối với JSON body, cần một giới hạn tổng thể ở proxy/container hoặc request-reading layer có thể đếm bytes thực tế. Chỉ kiểm tra `Content-Length` là chưa đủ vì request có thể dùng chunked transfer và không khai báo độ dài trước. Nếu ứng dụng dùng custom servlet filter/wrapper để giới hạn stream, phải bảo đảm wrapper tương thích với async/non-blocking I/O, error handling và cách converter đọc body; kiểm thử vượt ngưỡng khi body được stream từng phần.

Không dùng `ContentCachingRequestWrapper` như một body-size limiter. Wrapper này phục vụ cache body để logging/inspection và có thể giữ dữ liệu trong bộ nhớ; bản thân nó không phải cơ chế từ chối body vượt giới hạn.

## 14. Fast-fail theo Content-Length và giới hạn bytes thực tế

Có thể từ chối sớm khi header `Content-Length` cho biết body lớn hơn giới hạn:

```java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class DeclaredContentLengthFilter extends OncePerRequestFilter {
    private static final long MAX_JSON_BYTES = 1_048_576;

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        long declaredLength = request.getContentLengthLong();
        if (declaredLength > MAX_JSON_BYTES) {
            response.sendError(413, "Request body too large");
            return;
        }
        chain.doFilter(request, response);
    }
}
```

Đây chỉ là fast-fail minh họa, không phải biện pháp đầy đủ cho mọi request. `getContentLengthLong()` có thể trả `-1` khi độ dài không biết; filter này không đếm bytes thực tế của chunked body. Phải kết hợp với gateway/container limit và bounded stream reader có khả năng dừng khi tổng bytes vượt ngưỡng. Không đọc toàn bộ body vào `byte[]` chỉ để đếm vì cách đó có thể tạo đúng memory exhaustion mà ta muốn ngăn.

Một bounded reader cần đếm bytes trong khi đọc, dừng ngay khi vượt giới hạn, không buffer toàn bộ không cần thiết và trả lỗi `413` nhất quán. Với upload, dùng streaming sang file tạm/object storage có quota thay vì nạp toàn bộ file vào heap. Cần tính cả decompressed bytes nếu ứng dụng chấp nhận compressed request body.

## 15. Multipart và file upload limits

Multipart có nhiều thành phần: tổng body, kích thước từng file, số part, field text, filename metadata và dung lượng tạm. Chỉ đặt `max-file-size` không đủ nếu request có hàng nghìn part nhỏ hoặc nhiều field text lớn.

Hãy xác định:

- Tổng request bytes tối đa.
- Kích thước mỗi file tối đa.
- Số file và số multipart part tối đa.
- Độ dài tên field, filename và text field.
- Dung lượng quota theo user/tenant/ngày.
- Thời gian upload và tốc độ tối thiểu nếu gateway hỗ trợ.
- Vùng quarantine, scan và lifecycle cleanup.

Không tin MIME type, extension hoặc filename do client gửi. Sau khi nhận file, phát hiện loại nội dung từ bytes, quét malware theo policy và giữ trạng thái quarantine cho tới khi xử lý xong. Giới hạn archive expansion, số entry, nesting và decompression ratio để chống zip bomb.

Với upload rất lớn, cân nhắc upload trực tiếp tới private object storage bằng pre-signed URL có key do server tạo, giới hạn method/size/expiry, sau đó backend xác minh object và quyền trước khi chuyển sang trạng thái khả dụng.

## 16. Giới hạn header, query và content encoding

Body không phải phần duy nhất có thể gây lạm dụng tài nguyên:

- **Headers:** giới hạn tổng kích thước header và số lượng header; tránh Authorization/Cookie quá lớn.
- **Query string:** giới hạn URL length, số parameter, độ dài mỗi value và độ phức tạp filter.
- **Path:** giới hạn số segment và độ dài identifier; không log raw path nếu chứa dữ liệu nhạy cảm.
- **JSON:** giới hạn nesting depth, string length, number length, token count và collection size nếu parser hỗ trợ.
- **Content encoding:** nếu nhận gzip/br hoặc encoding khác, giới hạn cả compressed bytes và expanded bytes; kiểm tra ratio và thời gian giải nén.
- **Multipart:** giới hạn file, part, field và tổng dung lượng.

Không bật request compression chỉ vì tiết kiệm băng thông mà không có decompression limit. Một payload nhỏ sau nén có thể mở rộng rất lớn trong memory/CPU. Nếu không cần compressed request, có thể từ chối content encoding không hỗ trợ.

## 17. Giới hạn chi phí xử lý sau validation

Một request nhỏ và hợp lệ vẫn có thể gây chi phí lớn. Ví dụ batch 100 item, mỗi item kích hoạt 20 query và 5 downstream calls có thể tạo tải lớn dù body chỉ vài KB.

Áp dụng thêm:

- Max page size và max batch item count.
- Query complexity/depth limit cho GraphQL hoặc filter DSL.
- Timeout và cancellation cho truy vấn, parser và downstream call.
- Concurrency limit cho export, report, upload và tác vụ tốn tài nguyên.
- Rate limit theo principal, client, tenant và route.
- Quota theo chu kỳ cho storage, API calls hoặc compute.
- Idempotency cho operation có side effect để retry không nhân đôi tác động.
- Circuit breaker/bulkhead để một dependency hoặc tenant không chiếm toàn bộ worker pool.

Validation kiểm tra một request có đúng contract hay không; resource budget kiểm tra request đó có được phép tiêu thụ mức tài nguyên hiện tại hay không. Hai quyết định cần được thiết kế riêng.

## 18. Chọn response khi request vượt giới hạn

Khi body vượt giới hạn, trả `413` và response ngắn, ổn định. Không trả giới hạn nội bộ chi tiết nếu điều đó làm lộ cấu hình không cần thiết; có thể công bố mức tối đa theo API contract.

Ví dụ:

```http
HTTP/1.1 413 Content Too Large
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/request-too-large",
  "title": "Request body too large",
  "status": 413,
  "detail": "The request exceeds the maximum size allowed for this endpoint."
}
```

Validation error có thể trả danh sách field và code, nhưng không trả rejected value. Không phản chiếu nguyên nội dung input vào response. Nếu proxy từ chối request trước application, response có thể khác format; hãy cấu hình error mapping ở edge nếu contract yêu cầu thống nhất.

Ghi log event có route, declared/observed size nếu có, status, request ID và policy limit ID. Không log body hoặc filename/field content nhạy cảm. Có metric cho số request bị `413` để phân biệt client gửi nhầm với hành vi abuse.

## 19. Ví dụ cấu hình tổng hợp

Một cấu hình minh họa có thể chia giới hạn theo endpoint:

```yaml
api-limits:
  routes:
    search:
      max-body-bytes: 262144
      max-items: 50
      timeout: 2s
    batch-update:
      max-body-bytes: 524288
      max-items: 100
      timeout: 5s
    file-upload:
      max-request-bytes: 12582912
      max-file-bytes: 10485760
      max-files: 3
      concurrency-per-tenant: 2
```

Đây là schema ví dụ cho policy của ứng dụng, không phải property mặc định của Spring Boot. Cần map các giá trị này vào gateway, servlet container, multipart resolver và service limit tương ứng. Kiểm tra rằng limit thấp nhất có chủ đích và các tầng không mâu thuẫn khiến một endpoint bị từ chối bất ngờ.

## 20. Kiểm thử Bean Validation

Kiểm thử constraint ở cấp DTO và API:

| Ca kiểm thử | Input | Kết quả mong đợi |
|---|---|---|
| Required string | `null`, `""`, chỉ whitespace. | `@NotBlank` từ chối. |
| String length | Đúng max và vượt max. | Biên hợp lệ được chấp nhận; vượt ngưỡng bị từ chối. |
| Numeric range | 0, số âm, min/max và vượt max. | Khớp miền nghiệp vụ đã định nghĩa. |
| Decimal precision | Quá số chữ số hoặc scale. | Bị từ chối theo `@Digits`/domain rule. |
| Nested object | Một line item thiếu field bắt buộc. | `@Valid` kích hoạt lỗi ở item đó. |
| Collection size | 0, max item và max + 1. | Đúng giới hạn `@NotEmpty`/`@Size`. |
| Cross-field | Start sau end hoặc hai field mâu thuẫn. | Class-level constraint từ chối. |
| Enum/format | Giá trị ngoài allowlist hoặc identifier sai format. | Bị từ chối trước business operation. |
| Validation group | Create thiếu field bắt buộc; update bỏ qua field theo contract. | Constraint group chạy đúng operation. |
| Unknown property | Client gửi field không nằm trong DTO. | Hành vi strict/ignore được định nghĩa; không mass-assign. |
| Error response | Trigger nhiều lỗi validation. | Có field/code ổn định; không chứa rejected value/stack trace. |

Test cả unit validator lẫn API integration. Một validator unit test pass không chứng minh Spring MVC đã kích hoạt `@Valid` trên endpoint thật.

## 21. Kiểm thử request size và resource limits

Test body size ở ngay dưới, đúng bằng và vượt giới hạn. Dùng nhiều cách truyền body để phát hiện giới hạn chỉ dựa vào header:

- Có `Content-Length` nhỏ, bằng và lớn hơn limit.
- Chunked transfer hoặc stream không khai báo length trước.
- JSON body có một string rất lớn.
- JSON có nhiều field dư hoặc nesting sâu.
- Multipart có một file lớn, nhiều file nhỏ hoặc nhiều part/field.
- Gzip body có compressed size nhỏ nhưng expanded size lớn.
- Upload chậm, client ngắt giữa chừng và request đồng thời.
- Batch đúng max item và vượt max item.

Kết quả cần xác minh:

- Request vượt ngưỡng bị dừng trước khi gây memory/CPU exhaustion.
- Status `413` được trả nhất quán theo contract.
- Không có partial business side effect hoặc file `AVAILABLE` khi upload thất bại.
- Temporary file, multipart part và object tạm được cleanup.
- Metric/log có request ID và size metadata cần thiết nhưng không chứa payload.
- Một tenant gửi request lớn không làm cạn tài nguyên của tenant khác.

Không chỉ test qua MockMvc nếu giới hạn nằm ở reverse proxy hoặc servlet container. Cần integration test qua ingress/container thật trong môi trường test vì MockMvc thường không tái hiện đầy đủ HTTP chunking, proxy buffering và container parser limits.

## 22. Ví dụ MockMvc cho validation và request error

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderValidationTest {
    @Autowired MockMvc mvc;

    @Test
    void rejectsBlankReference() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "reference": "   ",
                      "amount": 12.50,
                      "items": [{
                        "productCode": "SKU-1",
                        "quantity": 1
                      }]
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field").value("reference"));
    }

    @Test
    void rejectsTooManyItems() throws Exception {
        // Fixture tạo max + 1 items; không cần hard-code body lớn.
        String body = requestWithItemCount(51);

        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isBadRequest());
    }
}
```

Ví dụ dùng `jsonPath` và helper minh họa; cần khớp response schema của ứng dụng. Đối với `413`, tạo integration test qua gateway/container đã cấu hình giới hạn thay vì giả định MockMvc sẽ thực thi limit ở hạ tầng.

## 23. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách khắc phục |
|---|---|---|
| Chỉ dùng `@Size` để giới hạn request | Validation chạy sau khi body được parse; không ngăn body quá lớn. | Giới hạn bytes ở edge/container và bounded streaming. |
| Chỉ kiểm tra `Content-Length` | Chunked/unknown-length body có thể vượt ngưỡng. | Đếm bytes thực tế khi đọc và enforce ở proxy/container. |
| Dùng `ContentCachingRequestWrapper` như limiter | Có thể cache body lớn trong memory mà không từ chối đúng ngưỡng. | Dùng request-size enforcement chuyên biệt. |
| Dùng JPA entity làm `@RequestBody` | Client có thể bind field server-owned/mass assignment. | DTO riêng với allowlist field. |
| Quên `@Valid` ở nested list | Constraint của từng item không chạy như mong đợi. | Dùng container element constraint và `@Valid`. |
| Dùng regex phức tạp không giới hạn input | Có thể tạo ReDoS. | Regex đơn giản, giới hạn độ dài và test worst-case. |
| Trả rejected value trong lỗi | Có thể phản chiếu password, token, PII hoặc body lớn. | Chỉ trả field và error code đã chuẩn hóa. |
| Một body limit cho mọi route | Upload bị chặn hoặc JSON endpoint nhận quá nhiều dữ liệu. | Limit theo route/content type/use case. |
| Chỉ giới hạn một file multipart | Nhiều part nhỏ hoặc field lớn vẫn gây cạn tài nguyên. | Giới hạn tổng request, file count, part count và field size. |
| Bỏ qua decompression size | Payload nén nhỏ mở rộng rất lớn. | Giới hạn compressed và expanded bytes/ratio. |
| Không giới hạn batch/query cost | Body nhỏ vẫn tạo nhiều query/downstream work. | Max items, complexity, timeout, concurrency và quota. |
| Chỉ test bằng MockMvc | Không kiểm tra ingress/container thực tế. | Integration test qua proxy và servlet container. |

## 24. Checklist triển khai

- [ ] Có `spring-boot-starter-validation` và DTO riêng cho request?
- [ ] Required, length, range, format và nested collection constraints được khai báo?
- [ ] `@Valid` được áp dụng cho object lồng nhau và từng collection element?
- [ ] Cross-field/domain invariants được kiểm tra ở đúng tầng?
- [ ] Method validation được kích hoạt và có test qua Spring proxy?
- [ ] Validation groups chỉ dùng cho create/update semantics, không dùng thay authorization?
- [ ] Client không thể bind `tenantId`, `ownerId`, role hoặc field server-owned?
- [ ] Error response không lộ rejected value, stack trace hoặc dữ liệu nhạy cảm?
- [ ] Có body byte limit ở gateway/proxy và enforcement phù hợp ở application/container?
- [ ] Chunked/unknown-length body được giới hạn bằng bytes thực tế?
- [ ] Multipart có max file, total request, file count/part count và temp storage policy?
- [ ] Header, query, JSON depth, compressed/expanded bytes được giới hạn?
- [ ] Có page/batch/query complexity, timeout, concurrency, rate limit và quota?
- [ ] Request vượt ngưỡng trả `413` và không tạo partial side effect?
- [ ] Có test ngay dưới/đúng/vượt limit, chunked, multipart, gzip và concurrent requests?
- [ ] Có integration test qua reverse proxy và servlet container thực tế?
- [ ] Log/metric chỉ ghi metadata cần thiết, không ghi body hoặc secret?

Bean Validation giúp Spring API từ chối dữ liệu sai contract và giảm lỗi ở tầng nghiệp vụ, còn request size limit bảo vệ tài nguyên trước khi dữ liệu được parse hoặc xử lý. Thiết kế tốt kết hợp DTO allowlist, nested/cross-field constraints, validation ở service boundary, giới hạn bytes thực tế tại edge/container/application và budget cho batch/downstream work. Luôn kiểm tra cả response lẫn trạng thái dữ liệu sau request bị từ chối; một lỗi validation hoặc `413` chỉ có ý nghĩa khi request không để lại side effect ngoài ý muốn.

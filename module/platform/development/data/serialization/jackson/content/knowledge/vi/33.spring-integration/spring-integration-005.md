# Phân biệt lỗi đọc JSON và lỗi Bean Validation

Trong ứng dụng Spring MVC dùng Jackson, một request JSON đi qua ít nhất hai giai đoạn kiểm tra khác nhau. Trước tiên, Spring dùng HTTP message converter và Jackson để đọc JSON rồi tạo Java object. Sau khi object được tạo thành công, Bean Validation mới kiểm tra các constraint như bắt buộc, độ dài, định dạng email hoặc giới hạn số. Hai giai đoạn có mục đích và exception khác nhau.

Lỗi cú pháp JSON, sai kiểu token hoặc không thể tạo DTO thường được Spring báo qua HttpMessageNotReadableException. JSON có thể đọc được nhưng dữ liệu vi phạm annotation validation thường dẫn đến MethodArgumentNotValidException khi controller dùng @Valid hoặc @Validated phù hợp. Từ Spring Framework 6.1, method validation tích hợp của Spring MVC còn có thể báo HandlerMethodValidationException. Validation ở service qua method-validation proxy có thể báo ConstraintViolationException hoặc MethodValidationException tùy cấu hình.

Phân biệt các lỗi này giúp API trả status và error body nhất quán, log đúng nguyên nhân, đồng thời tránh nhầm lỗi binding với lỗi nghiệp vụ. Bài này tập trung vào Spring MVC, Jackson Databind và Bean Validation; cuối bài có ghi chú riêng cho WebFlux.

## 1. Pipeline từ JSON đến controller

Với endpoint nhận JSON, luồng xử lý thường là:

```text
HTTP request body
       |
       v
Spring HttpMessageConverter
       |
       v
Jackson parser + databinding
       |
       +---- JSON syntax / token / type / creator error
       |                  |
       |                  v
       |       HttpMessageNotReadableException
       |
       v
Java request DTO created
       |
       v
Bean Validation (@Valid / @Validated)
       |
       +---- constraint violations
       |                  |
       |                  v
       |       MethodArgumentNotValidException
       |       or HandlerMethodValidationException
       |
       v
Controller method
       |
       v
Application service / domain rules
```

Jackson phải tạo được DTO trước khi Bean Validation kiểm tra các field trên DTO đó. Nếu JSON bị hỏng hoặc một property không thể chuyển thành kiểu Java, controller thường chưa được gọi và Bean Validation trên DTO không chạy.

Ví dụ request DTO:

```java
public record CreateUserRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @NotBlank
    @Email
    String email,

    @NotNull
    @Min(18)
    Integer age
) {}
```

Các input sau thuộc những tầng khác nhau:

| Request body | Tầng lỗi | Nguyên nhân |
|---|---|---|
| {"displayName":"An" | JSON parsing | Thiếu dấu đóng hoặc cấu trúc JSON sai |
| {"age":"many"} | Jackson databinding | String không chuyển được thành Integer theo cấu hình |
| {"email":"not-an-email"} | Bean Validation | JSON hợp lệ, nhưng email vi phạm @Email |
| {"displayName":" ","email":"a@example.test","age":17} | Bean Validation | JSON bind thành công, nhưng vi phạm @NotBlank/@Min |

Lỗi đầu tiên trong pipeline thường quyết định exception mà API nhận được. Nếu JSON không bind được, ứng dụng không thể thu thập đầy đủ các Bean Validation violations trên DTO.

## 2. Lỗi đọc JSON: HttpMessageNotReadableException

Trong Spring MVC, @RequestBody được đọc qua HttpMessageConverter. Khi converter không thể đọc body thành kiểu tham số, Spring thường ném HttpMessageNotReadableException.

Các nguyên nhân phổ biến:

- JSON sai cú pháp: thiếu dấu ngoặc, dấu phẩy thừa, chuỗi không đóng.
- Body rỗng trong khi request body là bắt buộc.
- Token không phù hợp kiểu đích: string gửi vào integer, object gửi vào string.
- Giá trị không thể chuyển đổi: số vượt range, enum không biết giá trị, date sai format.
- Creator property bắt buộc bị thiếu hoặc null theo cấu hình.
- Unknown property bị từ chối khi FAIL_ON_UNKNOWN_PROPERTIES bật.
- Custom deserializer hoặc constructor/factory từ chối input.
- Body bị cắt, sai encoding hoặc không khớp content type/converter.

Ví dụ JSON sai cú pháp:

```json
{
  "displayName": "An",
  "email": "an@example.test"
```

Ví dụ sai kiểu:

```json
{
  "displayName": "An",
  "email": "an@example.test",
  "age": "twenty"
}
```

Ví dụ giá trị không hợp lệ cho enum:

```json
{
  "status": "WAITING_FOR_APPROVAL"
}
```

Nếu enum Java không có constant tương ứng và mapper không được cấu hình xử lý unknown enum value, Jackson không thể tạo DTO.

### 2.1. Các exception Jackson bên trong

HttpMessageNotReadableException là exception ở tầng Spring. Cause bên trong có thể là exception Jackson như:

| Jackson exception | Ý nghĩa thường gặp |
|---|---|
| JsonParseException | Parser không đọc được cú pháp JSON |
| MismatchedInputException | Token không phù hợp kiểu dữ liệu đích |
| InvalidFormatException | Giá trị có hình thức không chuyển được sang kiểu đích |
| UnrecognizedPropertyException | JSON có property không được chấp nhận |
| ValueInstantiationException | Constructor/factory tạo object thất bại |
| JsonMappingException | Lỗi tổng quát trong quá trình mapping |

Những exception này hữu ích khi chẩn đoán nguyên nhân, nhưng API không nên phụ thuộc quá sâu vào message nội bộ hoặc tên class của mọi phiên bản Jackson. Spring đã cung cấp một exception boundary ổn định hơn cho controller advice: HttpMessageNotReadableException.

### 2.2. JSON hợp lệ về cú pháp vẫn có thể lỗi đọc

Không phải mọi HttpMessageNotReadableException đều là JSON syntax error. Ví dụ:

```json
{"age": "twenty"}
```

JSON này hợp lệ theo grammar JSON. Lỗi xảy ra khi Jackson cố chuyển token string thành Integer. Vì vậy, trong API response nên dùng tên như REQUEST_BODY_UNREADABLE hoặc REQUEST_BODY_INVALID thay vì luôn gọi là MALFORMED_JSON.

### 2.3. Cấu hình Jackson ảnh hưởng kết quả binding

Cùng một JSON có thể bind thành công hoặc thất bại tùy mapper:

- FAIL_ON_UNKNOWN_PROPERTIES quyết định field lạ có bị từ chối hay không.
- Coercion rules quyết định string/number/boolean có được chuyển đổi giữa các token type không.
- DeserializationFeature quyết định cách xử lý null cho primitive, enum unknown và creator property.
- @JsonFormat và Java Time module quyết định cách đọc ngày giờ.
- Custom deserializer có thể thêm quy tắc parsing.

Test cần dùng ObjectMapper thực tế của ứng dụng. Không dựa vào kết quả từ new ObjectMapper() nếu production có cấu hình khác.

## 3. Lỗi Bean Validation: MethodArgumentNotValidException

Khi Jackson tạo DTO thành công, Spring có thể gọi Bean Validation nếu tham số controller được đánh dấu @Valid hoặc @Validated:

```java
@RestController
@RequestMapping("/users")
public class UserController {

    @PostMapping
    public UserView create(
            @Valid @RequestBody CreateUserRequest request) {
        return userService.create(request);
    }
}
```

Nếu DTO có constraint violations và không có BindingResult/Errors được khai báo ngay sau tham số cần kiểm tra, Spring MVC thường ném MethodArgumentNotValidException.

Ví dụ JSON:

```json
{
  "displayName": " ",
  "email": "not-an-email",
  "age": 17
}
```

JSON bind được thành CreateUserRequest. Sau đó validator phát hiện:

- displayName vi phạm @NotBlank.
- email vi phạm @Email.
- age vi phạm @Min(18).

Đây không phải lỗi đọc JSON. Jackson đã làm xong nhiệm vụ của nó; dữ liệu có kiểu Java hợp lệ nhưng không thỏa các constraint được khai báo.

### 3.1. FieldError và ObjectError

MethodArgumentNotValidException cung cấp BindingResult:

```java
BindingResult result = exception.getBindingResult();

List<FieldError> fieldErrors = result.getFieldErrors();
List<ObjectError> objectErrors = result.getGlobalErrors();
```

- FieldError đại diện cho constraint trên một field, ví dụ email hoặc age.
- ObjectError đại diện cho constraint cấp object, ví dụ hai field startDate/endDate không nhất quán.

Thông tin thường hữu ích cho response:

- Field hoặc object path.
- Validation code ổn định.
- Message đã resolve/localize.

Không nhất thiết phải trả rejected value. Field có thể chứa password, token, email cá nhân hoặc dữ liệu nhạy cảm.

### 3.2. @Valid và @Validated

@Valid là annotation Jakarta Bean Validation dùng để kích hoạt cascade validation cho object và nested object. @Validated là annotation của Spring, hỗ trợ validation groups và được dùng trong một số cơ chế method validation.

Ví dụ nested DTO:

```java
public record AddressRequest(
    @NotBlank String city,
    @NotBlank String country
) {}

public record CreateCustomerRequest(
    @NotBlank String name,
    @Valid @NotNull AddressRequest address
) {}
```

@Valid trên address yêu cầu validator đi tiếp vào AddressRequest. Nếu thiếu @Valid, constraint trong AddressRequest có thể không được cascade kiểm tra dù object con đã được Jackson tạo.

@Valid không tự định nghĩa constraint. Nó chỉ yêu cầu cascade validation; các field vẫn cần @NotNull, @NotBlank hoặc constraint phù hợp.

### 3.3. Validation groups

Một DTO có thể có các constraint khác nhau theo thao tác create/update:

```java
public interface OnCreate {}
public interface OnUpdate {}

public record UserCommand(
    @NotNull(groups = OnUpdate.class)
    Long id,

    @NotBlank(groups = {OnCreate.class, OnUpdate.class})
    String username
) {}
```

Controller có thể chọn group:

```java
@PostMapping
public UserView create(
        @Validated(OnCreate.class) @RequestBody UserCommand command) {
    return userService.create(command);
}

@PutMapping("/{id}")
public UserView update(
        @PathVariable Long id,
        @Validated(OnUpdate.class) @RequestBody UserCommand command) {
    return userService.update(id, command);
}
```

Khi dùng group, test phải xác nhận đúng group được kích hoạt. Nếu không chỉ định group, Bean Validation mặc định dùng Default group; các constraint chỉ gắn với group khác sẽ không tự chạy.

## 4. Spring MVC method validation từ Spring 6.1

Từ Spring Framework 6.1, Spring MVC có cơ chế method validation tích hợp cho constraint đặt trực tiếp trên các tham số hoặc giá trị trả về của controller method. Khi method-level validation được kích hoạt, exception có thể là HandlerMethodValidationException.

Ví dụ:

```java
@GetMapping("/{id}")
public UserView get(
        @PathVariable @Positive Long id,
        @RequestParam @Min(0) int revision) {
    return userService.get(id, revision);
}
```

Nếu id hoặc revision vi phạm constraint, Spring MVC có thể ném HandlerMethodValidationException. Đây là validation ở cấp method argument; nó khác với lỗi Jackson khi đọc request body.

Trong một controller method có cả @Valid request body và constraint trực tiếp trên tham số khác, method validation tích hợp có thể tổng hợp các kết quả validation. Do đó, ở Spring 6.1+, không nên giả định mọi lỗi validation của controller đều luôn là MethodArgumentNotValidException.

### 4.1. Không nhầm method validation với conversion error

Ví dụ:

```http
GET /users/abc
```

Nếu path variable id có kiểu Long, chuỗi abc không chuyển được thành Long. Đây thường là lỗi conversion của Spring, ví dụ MethodArgumentTypeMismatchException, không phải Bean Validation.

Ngược lại:

```http
GET /users/-1
```

Giá trị -1 chuyển thành Long thành công. Sau đó @Positive mới từ chối nó qua method validation.

Sự khác biệt:

| Input | Kết quả |
|---|---|
| abc cho tham số Long | Conversion/type mismatch |
| -1 cho tham số @Positive Long | Bean Validation |
| JSON age là "many" | Jackson databinding failure |
| JSON age là 17 với @Min(18) | Bean Validation |

### 4.2. @Validated ở controller và Spring MVC 6.1

Trong các ứng dụng cũ, @Validated ở cấp class controller thường được dùng để kích hoạt method validation thông qua AOP proxy. Spring MVC 6.1 có method validation tích hợp riêng. Tài liệu Spring khuyến nghị tránh đặt @Validated ở cấp controller nếu muốn dùng cơ chế tích hợp mới, vì class-level @Validated có thể khiến việc kiểm tra đi qua AOP thay vì cơ chế MVC native.

Chọn một cơ chế phù hợp với Spring version và cấu hình của ứng dụng. Kiểm tra exception thực tế bằng MockMvc; đừng viết advice chỉ bắt một exception validation rồi bỏ sót exception còn lại.

## 5. Validation trong service và ConstraintViolationException

Validation cũng có thể chạy ở application service, không chỉ ở controller. Với method validation dựa trên proxy, service thường được đánh dấu @Validated và các tham số/return value có constraint:

```java
@Service
@Validated
public class TransferService {

    public TransferReceipt transfer(
            @NotNull @Valid TransferCommand command) {
        // Application use case
        return execute(command);
    }
}
```

Khi Spring method validation được cấu hình qua MethodValidationPostProcessor, constraint violation ở method có thể được báo bằng ConstraintViolationException. Với cấu hình adaptation của Spring Framework 6.1+, ứng dụng có thể dùng MethodValidationException để nhận cấu trúc lỗi theo method-validation result.

Không coi mọi ConstraintViolationException là lỗi đọc JSON. Nó có thể đến từ service method, scheduled job hoặc bất kỳ điểm nào có gọi validator. Nếu exception xảy ra sau khi controller đã bind request thành công, nguyên nhân thuộc validation ở tầng service/domain boundary.

### 5.1. Phân biệt validation đầu vào với business rule

Bean Validation phù hợp cho constraint cục bộ:

- Field bắt buộc.
- Độ dài chuỗi.
- Range số.
- Format email hoặc mã.
- Quan hệ giữa field trong cùng DTO.

Business rule thường cần trạng thái ngoài DTO:

- User có quyền sửa tài nguyên không?
- Tài khoản có đang hoạt động không?
- Số dư hiện tại có đủ không?
- Username đã được người khác sử dụng chưa?
- Đơn hàng đã chuyển trạng thái chưa?

Không chuyển mọi business rule thành Bean Validation chỉ để có một kiểu exception. Quy tắc cần database, actor hoặc transaction nên được kiểm tra trong application/domain service với exception nghiệp vụ riêng.

## 6. BindingResult: xử lý lỗi validation ngay trong controller

Nếu controller cần tự xử lý validation errors, khai báo BindingResult hoặc Errors ngay sau tham số cần kiểm tra:

```java
@PostMapping
public ResponseEntity<?> create(
        @Valid @RequestBody CreateUserRequest request,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return ResponseEntity.badRequest()
            .body(toValidationResponse(bindingResult));
    }

    return ResponseEntity.ok(userService.create(request));
}
```

Khi Bean Validation thất bại, Spring có thể chuyển lỗi vào BindingResult để controller quyết định response. Vị trí tham số quan trọng: BindingResult phải nằm ngay sau argument cần kiểm tra.

BindingResult không xử lý lỗi parse/binding của Jackson. Nếu body sai cú pháp hoặc sai kiểu khiến DTO không thể tạo, HttpMessageNotReadableException vẫn được ném trước khi có BindingResult để controller kiểm tra.

Vì vậy, kể cả khi dùng BindingResult, ứng dụng vẫn cần exception handler cho HttpMessageNotReadableException. Nếu không cần xử lý validation tại từng endpoint, @RestControllerAdvice thường giúp giữ controller gọn và response đồng nhất.

## 7. Tạo error response ổn định bằng @RestControllerAdvice

Không nên trả stack trace hoặc exception message nội bộ trực tiếp cho client. Tạo response contract có mã lỗi ổn định, message an toàn và danh sách field violations khi phù hợp.

Ví dụ record:

```java
public record FieldViolation(
    String field,
    String code,
    String message
) {}
```

Có thể dùng ProblemDetail của Spring Framework 6+:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ProblemDetail> handleUnreadableBody(
            HttpMessageNotReadableException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "Request body is missing or cannot be read."
        );
        problem.setTitle("Invalid request body");
        problem.setProperty("code", "REQUEST_BODY_UNREADABLE");

        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> handleBeanValidation(
            MethodArgumentNotValidException exception) {

        List<FieldViolation> violations =
            exception.getBindingResult().getFieldErrors().stream()
                .map(error -> new FieldViolation(
                    error.getField(),
                    Objects.toString(error.getCode(), "invalid"),
                    Objects.toString(error.getDefaultMessage(),
                        "Invalid value.")
                ))
                .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "One or more request fields are invalid."
        );
        problem.setTitle("Validation failed");
        problem.setProperty("code", "VALIDATION_FAILED");
        problem.setProperty("errors", violations);

        return ResponseEntity.badRequest().body(problem);
    }
}
```

Response lỗi đọc JSON có thể có dạng:

```json
{
  "type": "about:blank",
  "title": "Invalid request body",
  "status": 400,
  "detail": "Request body is missing or cannot be read.",
  "code": "REQUEST_BODY_UNREADABLE"
}
```

Response Bean Validation có thể có dạng:

```json
{
  "type": "about:blank",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "email",
      "code": "Email",
      "message": "must be a well-formed email address"
    },
    {
      "field": "age",
      "code": "Min",
      "message": "must be greater than or equal to 18"
    }
  ]
}
```

Các message cụ thể phụ thuộc validation provider, message bundle và locale. Nếu API cần contract lâu dài, hãy dùng error code do ứng dụng kiểm soát; message có thể được localize hoặc thay đổi mà không làm client phải parse nội dung văn bản.

### 7.1. Xử lý HandlerMethodValidationException

Với Spring MVC 6.1+, thêm handler riêng nếu controller dùng method validation tích hợp:

```java
@ExceptionHandler(HandlerMethodValidationException.class)
ResponseEntity<ProblemDetail> handleMethodValidation(
        HandlerMethodValidationException exception) {

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "One or more method arguments are invalid."
    );
    problem.setTitle("Validation failed");
    problem.setProperty("code", "METHOD_ARGUMENT_VALIDATION_FAILED");

    return ResponseEntity.badRequest().body(problem);
}
```

Ví dụ này trả response tổng quát để không gắn chặt error contract với API nội bộ của Spring. Nếu cần danh sách field/parameter, có thể duyệt getAllValidationResults() và getResolvableErrors() hoặc dùng visitor API của HandlerMethodValidationException. Cách trích xuất phụ thuộc Spring version; viết test cho cả request parameter, path variable và cascaded request body.

### 7.2. Xử lý ConstraintViolationException ở service boundary

Nếu service method validation được bật, có thể ánh xạ ConstraintViolationException thành response validation phù hợp khi nó phát sinh từ input người dùng:

```java
@ExceptionHandler(ConstraintViolationException.class)
ResponseEntity<ProblemDetail> handleConstraintViolation(
        ConstraintViolationException exception) {

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "One or more supplied values are invalid."
    );
    problem.setTitle("Validation failed");
    problem.setProperty("code", "CONSTRAINT_VIOLATION");

    return ResponseEntity.badRequest().body(problem);
}
```

Không nên mặc định mọi ConstraintViolationException đều là lỗi client. Một số violation có thể do bug nội bộ hoặc dữ liệu không hợp lệ từ hệ thống khác. Hãy xác định nguồn phát sinh và error contract; nếu service validation không trực tiếp phản ánh request, có thể cần log/response khác thay vì luôn trả 400.

### 7.3. Xử lý BindException và lỗi tham số khác

BindException thường liên quan đến binding/validation của @ModelAttribute. MethodArgumentTypeMismatchException thường liên quan đến conversion của query parameter hoặc path variable. MissingRequestParameterException và MissingRequestHeaderException là những lỗi request khác.

Không gom tất cả vào HttpMessageNotReadableException. Hãy xử lý theo boundary để response code chính xác:

| Exception | Ví dụ | Phân loại |
|---|---|---|
| HttpMessageNotReadableException | JSON body sai cú pháp hoặc sai kiểu | Body parsing/binding |
| MethodArgumentNotValidException | DTO JSON vi phạm @NotBlank | DTO Bean Validation |
| HandlerMethodValidationException | @Positive trên path/query/body method argument ở Spring MVC 6.1+ | Method validation |
| ConstraintViolationException | Service method validation qua proxy | Method/service validation |
| BindException | @ModelAttribute binding/validation | Model binding |
| MethodArgumentTypeMismatchException | /users/abc với Long id | Parameter conversion |
| MissingServletRequestParameterException | Thiếu query parameter bắt buộc | Request contract |

## 8. Không trả rejected value hoặc raw JSON cho client

FieldError có getRejectedValue(), nhưng không nên đưa giá trị đó vào response một cách mặc định. Nó có thể chứa:

- Password hoặc password reset token.
- Access token, API key hoặc secret.
- Email, số điện thoại hoặc thông tin cá nhân.
- Nội dung tài liệu hoặc dữ liệu nghiệp vụ nhạy cảm.

Tương tự, không trả exception.getMessage() của Jackson nguyên văn cho client. Message có thể chứa giá trị input, tên class nội bộ, đường dẫn Java hoặc chi tiết cấu hình. Dùng message tổng quát và error code ổn định; ghi chi tiết có chọn lọc trong log nội bộ.

Log nên có correlation/request ID, HTTP route, exception category và path/property nếu an toàn. Tránh log toàn bộ body ở production, nhất là endpoint nhận thông tin xác thực hoặc dữ liệu cá nhân.

### 8.1. Có nên trích field path từ Jackson exception?

Jackson JsonMappingException có path reference giúp xác định property gây lỗi, ví dụ age hoặc items[2].price. Thông tin này có thể hữu ích cho log và diagnostic response.

Tuy nhiên:

- Không phải mọi cause đều là JsonMappingException.
- Path có thể phản ánh tên property Java hoặc metadata nội bộ.
- Parser syntax error có thể không có field path.
- Message/path có thể thay đổi giữa Jackson versions.
- Trả path chỉ khi nó không tiết lộ cấu trúc nội bộ nhạy cảm.

Nếu API cần field path nhất quán, tạo mapping riêng từ exception category và kiểm thử trên version Jackson được quản lý. Đừng parse chuỗi message bằng regex để xác định field.

## 9. Thứ tự xử lý và điều gì không chạy khi binding thất bại

Giả sử body:

```json
{
  "displayName": "An",
  "email": "wrong",
  "age": "many"
}
```

Nếu age không thể chuyển thành Integer, Jackson không tạo được CreateUserRequest hoàn chỉnh. Spring ném HttpMessageNotReadableException. Validator không chạy trên DTO này, vì vậy API không trả danh sách @Email và các constraint khác trong cùng request.

Nếu age được gửi là 17:

```json
{
  "displayName": "An",
  "email": "wrong",
  "age": 17
}
```

Jackson có thể tạo DTO. Bean Validation chạy và có thể trả nhiều violations cùng lúc: email sai định dạng, age nhỏ hơn 18.

Đây là lý do test phải tách:

1. Body không thể deserialize.
2. Body deserialize thành công nhưng vi phạm validation.
3. Body deserialize và validation thành công.

Không viết một test duy nhất chỉ assert status 400 cho cả ba trường hợp; test đó không chứng minh ứng dụng phân loại đúng nguyên nhân.

## 10. Kiểm thử bằng MockMvc

MockMvc giúp kiểm tra toàn bộ đường đi của Spring MVC: HTTP request, message converter/Jackson, Bean Validation, controller advice và response. Đây là nơi phù hợp để xác nhận hai nhóm lỗi có mã lỗi khác nhau.

Ví dụ test slice:

```java
@WebMvcTest(UserController.class)
@Import(ApiExceptionHandler.class)
class UserControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    UserService userService;

    @Test
    void malformedJsonReturnsUnreadableBodyCode() throws Exception {
        mockMvc.perform(post("/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("REQUEST_BODY_UNREADABLE"));

        verifyNoInteractions(userService);
    }

    @Test
    void wrongJsonTypeReturnsUnreadableBodyCode() throws Exception {
        mockMvc.perform(post("/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "displayName": "An",
                      "email": "an@example.test",
                      "age": "many"
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("REQUEST_BODY_UNREADABLE"));

        verifyNoInteractions(userService);
    }

    @Test
    void beanValidationFailureReturnsValidationCode() throws Exception {
        mockMvc.perform(post("/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "displayName": " ",
                      "email": "not-an-email",
                      "age": 17
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.errors").isArray())
            .andExpect(jsonPath("$.errors.length()").value(3));

        verifyNoInteractions(userService);
    }
}
```

Ví dụ dùng @MockBean theo cách phổ biến trong Spring Boot test. Với các phiên bản Spring Boot mới hơn có thể dùng annotation mock bean tương ứng của Spring Test. Test chỉ minh họa contract; cần bổ sung fixture/service method và response của dự án.

### 10.1. Vì sao verifyNoInteractions quan trọng?

Với cả lỗi đọc JSON và lỗi Bean Validation, controller method không nên gọi application service. Assertion này xác nhận lỗi được xử lý trước side effect nghiệp vụ.

Nếu test chỉ kiểm tra status 400, service vẫn có thể đã được gọi trước khi lỗi được xử lý trong một custom flow sai thứ tự. Kiểm tra interaction giúp bảo vệ ranh giới giữa input validation và use case execution.

### 10.2. Kiểm tra field errors cụ thể

Ngoài code tổng quát, test có thể xác nhận field:

```java
mockMvc.perform(post("/users")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "displayName": "An",
              "email": "invalid",
              "age": 17
            }
            """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
    .andExpect(jsonPath("$.errors[*].field",
        hasItems("email", "age")));
```

Không phụ thuộc thứ tự của field errors nếu thứ tự đó không thuộc API contract. Nếu client cần thứ tự ổn định, sort theo field/code trước khi trả response và test quy tắc đó.

## 11. Kiểm thử riêng Jackson và Validator

MockMvc kiểm tra integration. Ngoài ra, test unit riêng giúp khoanh vùng lỗi.

### 11.1. Jackson test chỉ kiểm tra binding

```java
class CreateUserRequestBindingTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void readsValidJsonIntoDto() throws Exception {
        CreateUserRequest request = mapper.readValue(
            """
            {
              "displayName": "An",
              "email": "an@example.test",
              "age": 20
            }
            """,
            CreateUserRequest.class
        );

        assertEquals("An", request.displayName());
        assertEquals("an@example.test", request.email());
        assertEquals(20, request.age());
    }

    @Test
    void rejectsWrongTokenType() {
        assertThrows(JsonProcessingException.class, () ->
            mapper.readValue(
                """
                {
                  "displayName": "An",
                  "email": "an@example.test",
                  "age": "many"
                }
                """,
                CreateUserRequest.class
            )
        );
    }
}
```

Test Jackson không tự chạy Bean Validation chỉ vì DTO có annotation @NotBlank hoặc @Email. Nếu JSON hợp lệ nhưng email sai định dạng, readValue vẫn có thể trả DTO thành công; validator phải được gọi ở test riêng hoặc qua Spring MVC integration.

### 11.2. Validator test chỉ kiểm tra constraints

```java
class CreateUserRequestValidationTest {
    private final Validator validator =
        Validation.buildDefaultValidatorFactory().getValidator();

    @Test
    void reportsAllInvalidFields() {
        CreateUserRequest request =
            new CreateUserRequest(" ", "not-an-email", 17);

        Set<ConstraintViolation<CreateUserRequest>> violations =
            validator.validate(request);

        assertEquals(3, violations.size());
        assertTrue(violations.stream()
            .anyMatch(v -> v.getPropertyPath().toString()
                .equals("displayName")));
        assertTrue(violations.stream()
            .anyMatch(v -> v.getPropertyPath().toString()
                .equals("email")));
        assertTrue(violations.stream()
            .anyMatch(v -> v.getPropertyPath().toString()
                .equals("age")));
    }
}
```

Test này khởi tạo DTO trực tiếp nên không kiểm tra JSON parsing. Đó là chủ đích: nó kiểm tra validator độc lập với Jackson. Trong ứng dụng thực tế, có thể tái sử dụng Validator từ Spring context thay vì tạo factory mới trong từng test.

### 11.3. Integration test là nơi kiểm tra exception thực tế

Nếu cần xác nhận chính xác exception nào Spring MVC ném theo version, cấu hình message converter và method signature, dùng MockMvc. Unit test của Jackson không thể chứng minh Spring sẽ bọc lỗi ra sao; unit test của Validator cũng không thể chứng minh controller đã kích hoạt validation.

## 12. Các lỗi thường bị phân loại nhầm

Một số lỗi request không thuộc hai nhóm chính:

| Trường hợp | Exception Spring thường gặp | Ý nghĩa |
|---|---|---|
| Body JSON sai cú pháp | HttpMessageNotReadableException | Jackson parse failure |
| JSON đúng nhưng token sai kiểu | HttpMessageNotReadableException | Jackson binding failure |
| DTO vi phạm @NotBlank | MethodArgumentNotValidException hoặc HandlerMethodValidationException | Bean Validation |
| Path variable không chuyển được sang Long | MethodArgumentTypeMismatchException | Spring conversion |
| Query parameter bắt buộc bị thiếu | MissingServletRequestParameterException | Request contract |
| Content-Type không được hỗ trợ | HttpMediaTypeNotSupportedException | HTTP media type negotiation |
| Accept không có representation phù hợp | HttpMediaTypeNotAcceptableException | Response negotiation |
| @ModelAttribute bind/validate thất bại | BindException hoặc MethodArgumentNotValidException tùy flow | Model binding/validation |
| Service method parameter vi phạm constraint | ConstraintViolationException hoặc MethodValidationException | Method validation |

Đặc biệt, Content-Type không được hỗ trợ không phải JSON syntax error. Nếu client gửi XML đến endpoint chỉ nhận JSON, lỗi thường thuộc media type handling. Hãy để handler riêng hoặc cơ chế mặc định của Spring xử lý chính xác status 415.

## 13. Chọn HTTP status code

Spring MVC thường trả 400 Bad Request cho:

- HttpMessageNotReadableException.
- MethodArgumentNotValidException.
- HandlerMethodValidationException khi validation đầu vào thất bại.
- Nhiều lỗi request parameter conversion/binding.

400 là lựa chọn phổ biến vì request không thể được xử lý theo contract. Một số API chọn 422 Unprocessable Content cho dữ liệu đã parse được nhưng vi phạm semantic validation. Cả hai cách có thể dùng được nếu contract nhất quán và được tài liệu hóa.

Nếu chọn 422:

- Lỗi cú pháp JSON hoặc sai token type vẫn nên là 400.
- Bean Validation sau khi bind thành công có thể là 422.
- Client phải biết phân biệt và không dựa vào message text.
- Tất cả endpoint phải dùng cùng policy.

Không đổi status chỉ vì exception class khác nhau. Hãy căn cứ vào semantics mà API công bố cho client.

## 14. Xử lý lỗi parse chi tiết mà không làm rò dữ liệu

Có thể phân loại nguyên nhân trong log nội bộ:

```java
Throwable cause = exception;
while (cause.getCause() != null && cause.getCause() != cause) {
    cause = cause.getCause();
}

log.warn(
    "Unreadable request body: route={}, causeType={}",
    request.getRequestURI(),
    cause.getClass().getSimpleName()
);
```

Đoạn code trên chỉ minh họa việc xác định root cause type; code production nên có giới hạn độ sâu và logger/context phù hợp. Không log body thô hoặc exception message đầy đủ một cách mặc định.

Nếu muốn phân loại parser syntax error và databinding type mismatch để phục vụ metrics:

- Kiểm tra cause chain có JsonParseException hay không.
- Kiểm tra cause chain có MismatchedInputException/InvalidFormatException hay không.
- Giữ một nhóm fallback cho lỗi mapping khác.
- Không phụ thuộc việc cause chain luôn có cùng độ sâu hoặc cùng exception wrapper.

Các metric nên dùng nhãn có cardinality thấp, ví dụ parse, bind, validation, conversion. Không dùng raw field value, request ID hoặc message làm metric label.

## 15. Message localization và error code

Bean Validation cho phép message template:

```java
public record CreateUserRequest(
    @NotBlank(message = "{user.displayName.required}")
    String displayName,

    @Email(message = "{user.email.invalid}")
    String email
) {}
```

Resource bundle có thể cung cấp message theo locale:

```properties
user.displayName.required=Display name is required.
user.email.invalid=Email address is invalid.
```

Spring có thể resolve message qua MessageSource và locale của request. Nếu error response cần hỗ trợ đa ngôn ngữ, dùng message đã resolve thay vì tự nối chuỗi từ annotation.

Tuy vậy, message là nội dung trình bày. Client nên dựa vào code ổn định như USER_DISPLAY_NAME_REQUIRED hoặc VALIDATION_FAILED, không parse câu tiếng Anh. Có thể ánh xạ constraint code mặc định (NotBlank, Email, Min) sang code ứng dụng nếu API cần contract rõ hơn.

## 16. WebFlux có exception boundary khác

Bài này tập trung Spring MVC Servlet stack. Với Spring WebFlux, các exception thường gặp có tên khác:

- ServerWebInputException cho input không thể đọc/chuyển đổi trong WebFlux.
- WebExchangeBindException cho binding/validation errors của WebFlux.

Không copy nguyên handler MVC rồi kỳ vọng WebFlux dùng cùng exception type. Nếu ứng dụng có cả MVC và WebFlux, xây dựng error contract chung nhưng triển khai adapter/handler riêng cho từng stack, rồi test bằng MockMvc và WebTestClient tương ứng.

## 17. Những lỗi thường gặp khi cấu hình exception handling

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| JSON sai cú pháp trả response 500 | Chưa xử lý HttpMessageNotReadableException hoặc advice không được scan | Thêm handler ở @RestControllerAdvice và test MockMvc. |
| JSON sai kiểu bị gọi là Bean Validation | Gộp mọi lỗi request vào một handler chung | Phân loại HttpMessageNotReadableException riêng. |
| @NotBlank không chạy | Thiếu @Valid/@Validated hoặc thiếu cascade @Valid | Kiểm tra controller signature và validation provider. |
| Nested DTO không được validate | Thiếu @Valid trên property lồng | Thêm cascade validation và test nested violation. |
| Controller nhận DTO rồi vẫn gọi service dù invalid | BindingResult không được kiểm tra | Kiểm tra hasErrors trước khi gọi service. |
| Spring 6.1 trả exception validation khác dự kiến | Có method-level constraints hoặc controller @Validated qua AOP | Xác định cơ chế validation và xử lý HandlerMethodValidationException phù hợp. |
| Service ConstraintViolation bị trả như JSON parse error | Catch quá rộng hoặc phân loại theo status chung | Tách service/method validation khỏi message conversion. |
| Response lộ password/rejected value | Trả toàn bộ FieldError hoặc exception message | Chỉ trả field/code/message đã kiểm soát. |
| Content-Type sai trả lỗi không rõ | Gộp media type error vào body parse error | Giữ xử lý HttpMediaTypeNotSupportedException riêng. |
| Test chỉ assert status 400 | Không xác nhận đúng tầng lỗi | Assert error code và verify service không được gọi. |

## 18. Quy trình triển khai

1. Tạo request DTO riêng, khai báo kiểu field và Bean Validation constraints.
2. Đảm bảo Jackson mapper production có module/coercion/unknown-property policy được xác định.
3. Dùng @Valid hoặc @Validated trên @RequestBody; thêm @Valid cho nested DTO.
4. Xác định Spring version và method-validation mechanism đang dùng.
5. Xử lý HttpMessageNotReadableException như lỗi đọc/binding body.
6. Xử lý MethodArgumentNotValidException cho DTO validation.
7. Với Spring MVC 6.1+, cân nhắc HandlerMethodValidationException cho method argument validation.
8. Với service method validation, xác định ConstraintViolationException/MethodValidationException và phân loại nguồn phát sinh.
9. Dùng @RestControllerAdvice để chuẩn hóa error code, status và response shape.
10. Không trả raw exception message, rejected value hoặc request body.
11. Viết MockMvc test cho malformed JSON, wrong token type, Bean Validation failure và request hợp lệ.
12. Verify application service không được gọi khi binding hoặc validation thất bại.
13. Test riêng conversion error, media type error và các validation groups.
14. Giữ error contract nhất quán giữa endpoint và ghi rõ status code trong tài liệu API.

Lỗi đọc JSON và lỗi Bean Validation xảy ra ở hai giai đoạn khác nhau. HttpMessageNotReadableException cho biết Spring/Jackson không thể tạo object từ body; MethodArgumentNotValidException cho biết object đã được tạo nhưng vi phạm constraint. Spring MVC 6.1 bổ sung HandlerMethodValidationException cho method validation tích hợp, còn service method validation có exception boundary riêng. Khi phân loại theo đúng giai đoạn, API có thể trả lỗi an toàn, client biết cần sửa cú pháp/kiểu dữ liệu hay giá trị, và application service chỉ chạy sau khi request đã vượt qua các kiểm tra đầu vào cần thiết.

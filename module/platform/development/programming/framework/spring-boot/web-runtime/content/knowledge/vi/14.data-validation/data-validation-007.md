# WebExchangeBindException và lỗi kiểm tra dữ liệu trong Spring WebFlux

## 1. Vì sao cần hiểu WebExchangeBindException?

Một API Spring WebFlux thường nhận JSON từ HTTP request, giải mã thành DTO Java rồi kiểm tra dữ liệu trước khi thực thi nghiệp vụ. Khi DTO không đáp ứng các ràng buộc như @NotBlank, @Email, @Size hoặc @Min, Spring có thể báo lỗi **WebExchangeBindException**. Đây là tín hiệu quan trọng: dữ liệu client đã được đưa vào bước binding/validation nhưng không đạt hợp đồng mà endpoint yêu cầu.

Điểm cần nhớ ngay từ đầu:

- **WebExchangeBindException** thuộc package **org.springframework.web.bind.support**.
- Nó kế thừa **ServerWebInputException**, triển khai **BindingResult** và **ErrorResponse**.
- Trong trường hợp validation thông thường trên một argument DTO, lỗi này mặc định phù hợp với HTTP **400 Bad Request**.
- Nó có danh sách field errors, global/object errors, object name và metadata của quá trình binding.
- Nó **khác** MethodArgumentNotValidException thường được nhắc đến trong Spring MVC.
- Nó cũng **khác** HandlerMethodValidationException, thường xuất hiện khi Spring Framework 6.1 áp dụng **method validation** do constraint đặt trực tiếp lên tham số hoặc return value của controller.

Bài này dùng **Java 17+, Spring Boot 3.3.x, Spring Framework 6.1.x và Spring WebFlux**. Ví dụ hoàn chỉnh có các test HTTP bằng WebTestClient trên embedded Reactor Netty. Nếu dự án chỉ có starter-webflux mà **không** có starter-validation, không được mặc nhiên kỳ vọng Jakarta Bean Validation hoạt động đầy đủ.

Mục tiêu sau bài học:

1. Hiểu chính xác lỗi phát sinh ở đâu trong reactive request pipeline.
2. Biết những trường hợp tạo WebExchangeBindException và những trường hợp dùng exception khác.
3. Đọc field errors và global errors mà không làm lộ input nhạy cảm.
4. Thiết kế response HTTP 400 có hợp đồng ổn định.
5. Biết khi nào nên dùng @RestControllerAdvice, BindingResult, onErrorResume và ResponseEntityExceptionHandler.
6. Viết và chạy một ứng dụng WebFlux có validation với cả DTO đồng bộ và Mono<DTO>.
7. Phân biệt validation trên DTO với validation trên method parameters trong Spring 6.1.
8. Kiểm thử lỗi malformed JSON, dữ liệu thiếu, ràng buộc vi phạm, Content-Type và lỗi nghiệp vụ.

## 2. Vị trí validation trong luồng HTTP WebFlux

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    A["HTTP request / Reactor Netty"] --> B["HttpHandler + WebFilter chain"]
    B --> C["DispatcherHandler"]
    C --> D["HandlerMapping chọn method"]
    D --> E["WebFlux RequestMappingHandlerAdapter"]
    E --> F["HttpMessageReader / decode JSON"]
    F --> G["Argument binding"]
    G --> H{"@Valid / @Validated và constraint"}
    H -->|"Hợp lệ"| I["Controller method / reactive publisher"]
    H -->|"Lỗi một DTO"| J["WebExchangeBindException"]
    H -->|"Lỗi method validation"| K["HandlerMethodValidationException"]
    F -->|"JSON sai cú pháp"| L["HTTP decoding / input exception"]
    I --> M["Result handling / HTTP response"]
    J --> N["@ExceptionHandler / error handling"]
    K --> N
    L --> N
    N --> O["HTTP error response nếu chưa commit"]
~~~

Sơ đồ là đường đi **khái niệm**, không phải stack trace cứng. Với tham số @RequestBody Mono<T>, decoding/validation có thể diễn ra khi Publisher được subscribe, sau khi controller method đã trả về một pipeline. Với @RequestBody T đồng bộ, Spring phải resolve xong argument trước khi gọi method. Khi method validation áp dụng, thứ tự và exception được chọn có thể khác.

**Validation của dữ liệu không phải authentication hoặc authorization.** Việc email hợp lệ về cú pháp không chứng minh địa chỉ email tồn tại hoặc thuộc về người gọi. Một accountId hợp lệ không chứng minh user có quyền truy cập account đó.

### Các bước cần phân biệt

1. **Routing**: request có khớp @PostMapping và điều kiện consumes/produces?
2. **HTTP decoding**: Content-Type có phù hợp? JSON có parse được?
3. **Binding**: framework có tạo được giá trị Java/DTO?
4. **Validation**: DTO hoặc method có vi phạm constraint?
5. **Business logic**: entity có tồn tại, trạng thái có cho phép thao tác, user có quyền?
6. **Response**: mã HTTP và body lỗi được ghi thế nào trước khi response commit?

Nếu JSON sai cú pháp, quá trình xử lý có thể không đến bước validate DTO. Nếu Content-Type sai, request có thể nhận **415 Unsupported Media Type** trước khi Jackson chạy. Không nên quy mọi HTTP 400 hoặc 415 thành WebExchangeBindException.

## 3. Định nghĩa và API quan trọng của WebExchangeBindException

Trong Spring Framework 6.1, WebExchangeBindException có bản chất:

~~~java
package org.springframework.web.bind.support;

// Mô tả dạng class rút gọn, không phải source đầy đủ:
public class WebExchangeBindException
        extends ServerWebInputException
        implements BindingResult {
    // ...
}
~~~

Nó còn tham gia hợp đồng ErrorResponse của framework. Các API cần quan tâm:

| API | Ý nghĩa |
| --- | --- |
| getBindingResult() | Trả BindingResult được gói trong exception |
| getObjectName() | Tên đối tượng đang binding/validation |
| hasErrors() | Có lỗi binding/validation hay không |
| getErrorCount() | Tổng số lỗi field và global |
| getAllErrors() | Danh sách tổng hợp ObjectError/FieldError |
| getFieldErrors() | Tất cả lỗi gắn với field |
| getFieldErrors("email") | Các lỗi trên field email |
| getFieldError("email") | Một lỗi đầu tiên của field email nếu có |
| getGlobalErrors() | Lỗi liên quan toàn bộ object |
| getFieldValue("field") | Giá trị liên quan binding, có thể chứa thông tin client nhập |
| getStatusCode() | HTTP status do ErrorResponse/ServerWebInputException cung cấp |
| getBody() | ProblemDetail tương ứng với cơ chế ErrorResponse |

Trong error response công khai, thường chỉ cần **field name, error code/message được kiểm soát** và mã lỗi tổng quát; không nên tự động trả getFieldValue(), rejectedValue, exception stack trace hoặc toàn bộ BindingResult cho client.

### FieldError và ObjectError

- **FieldError** biểu thị một lỗi gắn với field cụ thể như name hoặc age.
- **ObjectError** có thể diễn đạt lỗi cấp object, ví dụ ràng buộc liên quan đồng thời startDate và endDate.

Một FieldError có thể chứa field name, rejectedValue, codes, arguments và defaultMessage. Không được mặc định rằng **defaultMessage** là bản dịch ổn định cho mọi ngôn ngữ; trong nhiều ứng dụng cần MessageSource và mã lỗi công khai ổn định.

## 4. WebExchangeBindException xuất hiện khi nào?

Theo cơ chế validation tích hợp Spring WebFlux:

- @Valid hoặc @Validated trên một **đối tượng tham số @RequestBody, @ModelAttribute, @RequestPart** có thể kích hoạt Bean Validation.
- Trường hợp **argument validation** cho một object, không có Errors/BindingResult ngay sau để tự xử lý và không bị method validation bao trùm, thường phát **WebExchangeBindException** khi có lỗi.
- Trường hợp có constraint trực tiếp trên method parameter hoặc return value được Spring 6.1 xử lý bằng method validation thường dùng **HandlerMethodValidationException**.
- Tham số không có constraint/annotation validation thì việc decode object thành công **không bảo đảm** các ràng buộc Bean Validation sẽ được kiểm tra.

Ví dụ:

~~~java
@PostMapping("/signup")
public Mono<String> signup(
        @Valid @RequestBody SignupRequest request) {
    return Mono.just("accepted");
}
~~~

Đây là method minh họa, không phải file Java độc lập. Với SignupRequest chứa @NotBlank trên name, request có name rỗng thường bị từ chối bằng WebExchangeBindException trước khi controller xử lý nghiệp vụ.

Lưu ý khi nói về @Valid:

- @Valid bản thân nó là annotation kích hoạt **nested/argument validation**, không phải một constraint trực tiếp như @Min hoặc @NotBlank.
- Một DTO kiểu Map hoặc Collection có cách validation khác object command chuẩn; không suy rằng chỉ thêm @Valid là mọi phần tử đều được kiểm tra theo cùng quy tắc.
- Có thể dùng các nhóm validation của @Validated khi thực sự cần các nhóm khác nhau giữa tạo và sửa; phải test cụ thể.
- Validator cần được cấu hình và có provider tương thích với Jakarta Validation.
- Bean Validation trên object chỉ kiểm tra những invariant được mô tả; quy tắc nghiệp vụ có thể cần service/database.

## 5. So sánh với các exception thường bị nhầm

| Exception | Stack/nguồn thường gặp | Ý nghĩa chính |
| --- | --- | --- |
| WebExchangeBindException | WebFlux; argument binding/validation | Một object argument không hợp lệ |
| HandlerMethodValidationException | Spring Framework 6.1; method validation | Một hoặc nhiều tham số/return value vi phạm method constraints |
| MethodArgumentNotValidException | Spring MVC/Servlet | DTO argument validation thất bại trong MVC |
| ServerWebInputException | Spring WebFlux | Một nhóm lỗi HTTP input; WebExchangeBindException là subclass |
| DecodingException | Codec/reactive decoding | Lỗi giải mã content, có thể được bọc thành lỗi HTTP input |
| UnsupportedMediaTypeStatusException | WebFlux content type handling | Request media type không được hỗ trợ; thường 415 |
| ResponseStatusException | Spring WebFlux/controller | Lỗi do code/framework chỉ định một HTTP status |
| ConstraintViolationException | Jakarta Validation/provider hoặc AOP method validation | Có thể phát sinh ngoài pipeline controller argument validation |
| NoSuchElementException / domain exception | Service logic | Có thể là lỗi nghiệp vụ, không phải validation argument |

**Không bắt mọi IllegalArgumentException hoặc Throwable rồi trả HTTP 400.** Cách đó có thể che các bug Java nghiêm trọng, lỗi hệ thống hoặc vi phạm authorization.

### Chỗ import dễ nhầm

~~~java
// WebFlux binding/validation exception:
import org.springframework.web.bind.support.WebExchangeBindException;

// Method-level controller validation in Spring 6.1:
import org.springframework.web.method.annotation.HandlerMethodValidationException;

// MVC-specific exception (không dùng để bắt WebFlux WebExchangeBindException):
import org.springframework.web.bind.MethodArgumentNotValidException;
~~~

Ba import này để phân biệt API, không có nghĩa phải dùng cả ba trong cùng một source file. Demo WebFlux đầy đủ bên dưới **không import** MethodArgumentNotValidException.

## 6. Cần những dependency nào?

Với Spring Boot 3.3 và Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

- starter-webflux: WebFlux, HTTP codecs và Reactor Netty server thông thường.
- starter-validation: hạ tầng Jakarta Bean Validation/Hibernate Validator phù hợp theo dependency management của Boot.
- starter-test: JUnit Jupiter, Spring Test, WebTestClient và những công cụ test tiêu chuẩn.

Nếu chỉ dùng starter-webflux nhưng quên starter-validation, các ràng buộc như @NotBlank, @Email có thể không được kích hoạt như dự kiến. Không đánh dấu một endpoint là “đã validate” chỉ vì source code có @Valid.

Java 17 dùng package **jakarta.validation**:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
~~~

Với Spring Boot 3.x không dùng javax.validation.* của các phiên bản cũ.

**Chú ý lựa chọn web stack:** Nếu thêm spring-boot-starter-web (MVC) cùng spring-boot-starter-webflux, Boot mặc định ưu tiên Servlet/MVC, ngoại trừ khi cấu hình web application type có chủ đích. Vì vậy ví dụ WebFlux chỉ dùng starter-webflux.

## 7. Thiết kế DTO rõ contract

Ví dụ form đăng ký chỉ có ba dữ liệu:

- name: bắt buộc và không được chỉ có whitespace.
- email: bắt buộc, có định dạng email cơ bản.
- age: ít nhất 18.

Java 17 record:

~~~java
public record SignupRequest(
        @NotBlank(message = "name is required")
        @Size(max = 40, message = "name is too long")
        String name,

        @NotBlank(message = "email is required")
        @Email(message = "email format is invalid")
        String email,

        @Min(value = 18, message = "age must be at least 18")
        int age) {
}
~~~

Đoạn này cần nằm trong file SignupRequest.java với package/import phù hợp; bản code hoàn chỉnh ở mục 16.

Kết quả validation cần phân biệt:

| Request input | Kỳ vọng | Vì sao |
| --- | --- | --- |
| {"name":"An","email":"an@example.org","age":21} | Hợp lệ | Các constraint đều đạt |
| {"name":"","email":"an@example.org","age":21} | Không hợp lệ | @NotBlank trên name |
| {"name":"An","email":"bad","age":21} | Không hợp lệ | @Email trên email |
| {"name":"An","email":"an@example.org","age":17} | Không hợp lệ | @Min trên age |
| {"name":"","email":"bad","age":16} | Không hợp lệ ở nhiều field | Có lỗi name, email và age |
| {"name":"An","email":"an@example.org"} | Không hợp lệ | int age mặc định 0 khi thiếu; @Min từ chối |
| {"name":null,"email":"an@example.org","age":22} | Không hợp lệ | @NotBlank từ chối null |
| {"name":"An","email":null,"age":22} | Không hợp lệ | @NotBlank từ chối null |
| {"name":"An","email":"an@example.org","age":"twenty"} | Lỗi decode/binding, thường 400 | JSON string không phù hợp với int age |

**@Email không xác minh email có tồn tại, có thể nhận thư hoặc thuộc về người dùng.** Nếu cần xác thực địa chỉ email, hãy xây bước xác minh riêng ngoài Bean Validation.

### int age và missing value

Khi dùng primitive int trong record, một field JSON không có có thể được mapper đặt thành 0, sau đó @Min bắt lỗi. Nếu bạn cần phân biệt **missing**, explicit null và giá trị 0 ở mức schema, dùng Integer kết hợp @NotNull/@Min hoặc cấu hình Jackson creator phù hợp rồi test cả ba trường hợp.

### Nested validation

Một DTO chứa object Address có thể khai báo:

~~~java
record Address(@NotBlank String street) {}

record OrderRequest(
        @NotNull @Valid Address shippingAddress) {}
~~~

Đoạn minh họa này cần imports; để validate sâu vào object con, @Valid trên property con là thành phần quan trọng. Nếu thiếu @Valid ở nested property, một số ràng buộc bên trong object đó có thể không được đánh giá. Đừng dùng một DTO quá sâu không giới hạn khiến việc đọc và kiểm thử validation trở nên khó kiểm soát.

## 8. @Valid trên @RequestBody DTO so với @RequestBody Mono<DTO>

Spring WebFlux hỗ trợ cả **đối số object trực tiếp** và **đối số reactive type**:

~~~java
@PostMapping("/sync-argument")
public Mono<String> syncArgument(
        @Valid @RequestBody SignupRequest request) {
    return Mono.just("accepted");
}
~~~

~~~java
@PostMapping("/reactive-argument")
public Mono<String> reactiveArgument(
        @Valid @RequestBody Mono<SignupRequest> request) {
    return request.map(value -> "accepted");
}
~~~

Cả hai snippet đều là method controller minh họa.

### Khác biệt thời điểm

- Với object trực tiếp, framework cần đọc, decode, tạo object và validate trước khi gọi handler method với argument hoàn chỉnh.
- Với Mono<SignupRequest>, method nhận Publisher; việc decode/validate có thể hoàn thành khi pipeline được subscribe.
- Khi validation gặp lỗi trong Mono<SignupRequest>, tín hiệu lỗi thường đi theo reactive Publisher, vì thế code trong handler **có thể** bắt nó bằng onErrorResume/onErrorMap nếu muốn.
- Một global @ExceptionHandler(WebExchangeBindException.class) có thể xử lý lỗi phù hợp khi nó được chuyển tới controller exception-handling framework.
- Không tự gọi subscribe() bên trong controller để ép validation chạy. Hãy **return** reactive chain cho framework quản lý completion và cancellation.

Ví dụ xử lý cục bộ một lỗi dưới dạng HTTP 400 bằng operator:

~~~java
@PostMapping("/local")
public Mono<ResponseEntity<String>> local(
        @Valid @RequestBody Mono<SignupRequest> input) {

    return input
            .map(value -> ResponseEntity.ok("accepted"))
            .onErrorResume(WebExchangeBindException.class,
                    ex -> Mono.just(
                            ResponseEntity.badRequest()
                                    .body("invalid signup data")));
}
~~~

Đây là method minh họa; cần imports tương ứng. Không return "accepted" với status 200 nếu validation đã fail. Nếu toàn hệ thống cần format lỗi thống nhất, global @RestControllerAdvice sẽ giảm lặp hơn so với onErrorResume trên mọi controller.

## 9. Method validation trong Spring Framework 6.1

Đây là điểm quan trọng nhất để không xử lý thiếu exception.

Spring Framework 6.1 có cơ chế **built-in method validation** cho controller methods. Khi bạn gắn constraint **trực tiếp** lên method parameter, framework có thể validate cả method arguments thay vì từng DTO riêng lẻ.

Ví dụ:

~~~java
@GetMapping("/pages")
public Mono<PageView> pages(
        @RequestParam(name = "page", defaultValue = "1")
        @Min(1) int page) {
    return Mono.just(new PageView(page));
}
~~~

Constraint @Min(1) nằm **trực tiếp trên tham số method**. Khi client gọi /pages?page=0 và method validation áp dụng, Spring có thể phát **HandlerMethodValidationException**, không phải WebExchangeBindException.

Điểm phân biệt:

| Tình huống | Cơ chế thường áp dụng | Exception khi lỗi |
| --- | --- | --- |
| @Valid @RequestBody SignupRequest request, không có trực tiếp @Constraint khác | Argument/object validation | WebExchangeBindException |
| @Valid @ModelAttribute Form form | Argument/object validation | WebExchangeBindException nếu không xử lý Errors tại chỗ |
| @Valid @RequestBody Mono<SignupRequest> request | Reactive argument validation | WebExchangeBindException trong error signal |
| @RequestParam @Min(1) int page | Method validation | HandlerMethodValidationException |
| @RequestHeader @NotBlank String token | Method validation khi điều kiện được thỏa | HandlerMethodValidationException |
| @Valid DTO **cùng** direct @Min trên một parameter khác | Method validation có thể bao trùm cả hai | HandlerMethodValidationException |
| Malformed JSON | Decoder/input processing | Lỗi input/codec, không mặc định WebExchangeBindException |
| Content-Type không hỗ trợ | Mapping/codec selection | Thường 415, không phải validation DTO |

Không có một exception duy nhất cho “mọi lỗi @Valid”.

### @Valid bản thân không phải constraint

Theo tài liệu Spring, @Valid phục vụ cascading/nested validation. Nó **không** phải cùng loại với @NotNull, @Min hoặc @NotBlank. Chỉ @Valid trên một object thường không buộc chọn method validation nếu không có các constraint trực tiếp khác.

### Tránh @Validated class-level khi học built-in validation

Nếu đặt @Validated lên class controller, Spring có thể sử dụng AOP method validation thay cho cơ chế controller method validation tích hợp. Khi muốn sử dụng built-in method validation của Spring 6.1, tài liệu khuyến nghị loại bỏ @Validated ở controller class level trong trường hợp phù hợp. @Validated vẫn có vai trò hợp lệ cho validation groups, service bean và AOP scenarios — không có nghĩa nó luôn sai.

### Return value validation

HandlerMethodValidationException có thể đại diện cả lỗi validation trên **return value**. Theo Javadoc Spring 6.1, status dành cho **input validation error** là 400; lỗi validation trên **return value** có thể là 500 vì đó là vấn đề phía server. Đừng map mọi HandlerMethodValidationException thành 400 một cách máy móc.

## 10. Truy cập field errors và global errors đúng cách

Để tạo lỗi JSON có cấu trúc, bạn có thể duyệt:

~~~java
for (FieldError error : exception.getFieldErrors()) {
    String field = error.getField();
    String message = error.getDefaultMessage();
    // Đưa field và thông báo an toàn vào response DTO.
}
~~~

~~~java
for (ObjectError error : exception.getGlobalErrors()) {
    String message = error.getDefaultMessage();
    // Dùng cho quy tắc cấp object.
}
~~~

Hai đoạn code trên là snippet, không phải class độc lập.

### Nhiều lỗi có thể xảy ra trên một field

Nếu một field vừa @NotBlank vừa @Size hoặc custom validator, một request có thể sinh **nhiều** FieldError trên cùng field. Vì vậy, thay vì:

~~~java
Map<String, String> errors;
~~~

nên cân nhắc:

~~~java
Map<String, List<String>> fieldErrors;
~~~

Cấu trúc danh sách thể hiện đầy đủ các lỗi. Trong ví dụ hoàn chỉnh, TreeMap giúp JSON có thứ tự key dễ đọc, nhưng client **không nên phụ thuộc thứ tự JSON object properties**.

### Global errors quan trọng khi nào?

Ví dụ một request có startDate và endDate; mỗi field hợp lệ nhưng tổng thể startDate phải trước endDate. Một custom class-level constraint có thể phát **ObjectError**. Nếu handler chỉ gọi getFieldErrors(), lỗi cấp object có thể bị bỏ qua. Hợp đồng error response nên hỗ trợ cả fieldErrors và globalErrors.

### Không trả rejectedValue cho mọi lỗi

FieldError có getRejectedValue(), nhưng giá trị bị từ chối có thể là password, token, địa chỉ, số điện thoại, email hoặc payload chứa dữ liệu riêng tư. Khi xây public API, **không** tự động serialize nguyên FieldError/BindingResult. Chỉ trả field name, mã lỗi và message đã kiểm soát.

## 11. HTTP status và error body

Khi validation không đạt, có hai quyết định tách biệt:

1. **HTTP status**: với input object không hợp lệ, thường là 400 Bad Request.
2. **Error representation**: JSON nào client nhận để biết phải sửa gì.

Một API có thể trả:

~~~json
{
  "code": "INVALID_REQUEST",
  "fieldErrors": {
    "age": ["age must be at least 18"],
    "email": ["email format is invalid"],
    "name": ["name is required"]
  },
  "globalErrors": []
}
~~~

Đây là **hợp đồng JSON do ứng dụng tự định nghĩa**. Nó không phải body mặc định bắt buộc của Spring Boot hoặc Spring WebFlux. Không giả định mọi phiên bản Boot tự trả fieldErrors như trên khi chưa có @ExceptionHandler.

Quy tắc thiết kế tốt:

- Dùng mã lỗi ổn định, ví dụ INVALID_REQUEST thay vì bắt client parse tiếng Việt/tiếng Anh của exception.
- Trả HTTP 400 cho input không đạt constraint; không trả 200 kèm error message.
- Không gửi Java class names, bean names hoặc raw rejected values không cần thiết.
- Có thể trả cả fieldErrors và globalErrors để bao phủ dữ liệu chéo field.
- Với method validation, có thể dùng mã METHOD_VALIDATION_FAILED hoặc thống nhất mã INVALID_REQUEST kèm nhóm parameterErrors.
- Khi đa ngôn ngữ, dùng MessageSource để resolve thông điệp theo Locale được tin cậy/định nghĩa.
- Chỉ gửi field names thuộc public contract; không để lộ property nội bộ không cần thiết.

## 12. Xử lý tập trung bằng @RestControllerAdvice

Trong WebFlux annotated controllers, @RestControllerAdvice có thể dùng @ExceptionHandler để chuyển WebExchangeBindException thành ResponseEntity.

Ví dụ rút gọn:

~~~java
@RestControllerAdvice
public class ApiErrors {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ValidationErrorResponse> invalid(
            WebExchangeBindException ex) {
        // Lấy ex.getFieldErrors() và ex.getGlobalErrors()
        // rồi tạo response với status 400.
        return ResponseEntity.badRequest()
                .body(/* public error DTO */);
    }
}
~~~

Đây là **pseudocode**, không biên dịch độc lập vì thiếu DTO/implementation. Mẫu hoàn chỉnh ở mục 16 sẽ có đủ imports và không có placeholder trong file Java thực.

Khi dùng advice:

- Class phải được component scan hoặc import vào context.
- Chọn exception types cụ thể, không bắt toàn bộ Throwable rồi biến bug thành lỗi client.
- Không đăng ký nhiều advice chồng nhau với cùng exception mà thiếu kiểm soát @Order.
- Tránh truy cập input chứa dữ liệu nhạy cảm chỉ để tạo response.
- Kiểm tra response đã commit chưa, đặc biệt với Flux/SSE streaming.
- Thực hiện mapping lỗi nhanh và non-blocking; không gọi database đồng bộ trong exception handler trên event loop.

### Vì sao không dùng ResponseStatusException cho mọi lỗi validate?

ResponseStatusException hữu ích để báo lỗi có HTTP status rõ trong nghiệp vụ. Nhưng Bean Validation đã cung cấp chi tiết các field errors qua WebExchangeBindException. Chuyển tất cả thành một ResponseStatusException("Invalid") có thể làm mất thông tin client cần để sửa form.

## 13. ResponseEntityExceptionHandler và ProblemDetail

Spring WebFlux còn cung cấp **org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler**, hỗ trợ xử lý nhiều exception framework thành response theo cơ chế ErrorResponse/ProblemDetail.

Có hai chiến lược hợp lệ:

- **Chiến lược A**: @RestControllerAdvice với các @ExceptionHandler cụ thể, trả response DTO do ứng dụng quản lý. Phù hợp khi API có contract lỗi riêng.
- **Chiến lược B**: kế thừa ResponseEntityExceptionHandler và override các hook thích hợp để tùy chỉnh ProblemDetail, status và message resolution. Phù hợp khi muốn chuẩn hóa theo Problem Details.

**Không kết hợp máy móc cả hai chiến lược rồi đăng ký handlers trùng nhau.** Ví dụ chính dùng A. Nếu muốn chuyển sang ProblemDetail, hãy test response body và các HTTP media type tương ứng; Spring Framework 6.1 cung cấp API để tùy chỉnh messages thông qua MessageSource.

Ví dụ payload theo phong cách Problem Details:

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Request validation failed"
}
~~~

Đây là ví dụ biểu diễn ý tưởng, không phải lời hứa rằng Spring Boot 3.3 sẽ tự xuất chính xác JSON này cho mọi WebExchangeBindException. Việc có thêm fieldErrors hay localized messages là lựa chọn của ứng dụng.

## 14. BindingResult/Errors ngay sau tham số

Trong một số annotated controller WebFlux, bạn có thể xử lý lỗi validation cục bộ bằng **Errors hoặc BindingResult** đặt **ngay sau** tham số cần validate.

Ví dụ khái niệm:

~~~java
@PostMapping("/form")
public Mono<ResponseEntity<String>> form(
        @Valid @ModelAttribute FormData input,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just(
                ResponseEntity.badRequest().body("invalid form"));
    }
    return Mono.just(ResponseEntity.ok("accepted"));
}
~~~

Đây là snippet trong controller, FormData phải được khai báo và import BindingResult. Khi có Errors/BindingResult đúng vị trí và framework hỗ trợ xử lý cục bộ, controller có thể tự quyết định status/response thay vì lỗi được phát ra thành WebExchangeBindException.

Điểm dễ sai:

- BindingResult không phải object trả về từ service.
- Với nhiều tham số cần validate, phải đặt BindingResult ngay sau tham số tương ứng; không gom một BindingResult cuối method rồi kỳ vọng nhận mọi lỗi.
- Với **@RequestBody Mono<T>**, không thể đơn giản đặt một BindingResult sau Mono<T> theo cùng cách đồng bộ; dùng reactive error operators hoặc global exception handling.
- Nếu method validation trên các tham số khác cũng fail, Spring có thể vẫn ném HandlerMethodValidationException khi không phải tất cả lỗi được gắn đúng Errors có thể xử lý cục bộ.
- Trả 200 OK khi errors.hasErrors() là một quyết định API có thể gây hiểu nhầm; thường chọn 400.

## 15. Xử lý reactive error signal trong Mono<DTO>

WebFlux cho phép đọc body dưới dạng Mono<SignupRequest>. Trong trường hợp này, validation exception có thể xuất hiện **sau khi** controller đã trả về Publisher. Vì vậy, hãy tư duy bằng tín hiệu Reactor:

~~~text
HTTP body publisher
  -> decode JSON
  -> validate SignupRequest
  -> Mono<SignupRequest>
       -> onNext(valid DTO) -> business mapping
       -> onError(WebExchangeBindException) -> error strategy
       -> onComplete
~~~

Các operator dùng phù hợp:

- **onErrorResume**: chuyển lỗi thành một Publisher dự phòng, ví dụ ResponseEntity.badRequest().
- **onErrorMap**: chuyển lỗi thành một exception khác, cần giữ nguyên nguyên nhân khi debug.
- **doOnError**: quan sát/log lỗi nhưng **không xử lý** hoặc thay nó.
- **checkpoint**: hỗ trợ debug Reactor assembly ở tình huống phù hợp.
- **retry**: **không** nên retry request body validation không hợp lệ một cách mù quáng; input sẽ không tự trở nên hợp lệ.

Sai lầm nghiêm trọng:

~~~java
// Không nên dùng trong controller WebFlux:
requestMono.subscribe(value -> service.save(value));
return Mono.empty();
~~~

Hành vi này làm side effect chạy ngoài Publisher HTTP được framework quản lý, khiến error/cancellation khó được trả cho client, dễ gây race. Hãy dùng flatMap/map và **return chain**, để WebFlux quản lý subscription.

## 16. Ứng dụng hoàn chỉnh: Spring Boot 3.3 WebFlux có validation

Ví dụ này phục vụ ba tình huống:

1. POST /api/signup dùng @Valid @RequestBody **SignupRequest** trực tiếp; lỗi từng DTO được đưa vào WebExchangeBindException.
2. POST /api/signup-async dùng @Valid @RequestBody **Mono<SignupRequest>**; cùng validation nhưng Publisher đi theo reactive pipeline.
3. GET /api/page?page=0 dùng **@Min trực tiếp trên method parameter**; minh họa HandlerMethodValidationException trong Spring 6.1.

Một @RestControllerAdvice xử lý riêng hai loại exception và tạo JSON lỗi có định dạng rõ ràng. Test dùng HTTP thật, không phải direct invocation của controller method.

### 16.1 Cấu trúc project

~~~text
webflux-validation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/validation/
    │   ├── ValidationDemoApplication.java
    │   ├── SignupRequest.java
    │   ├── SignupController.java
    │   ├── ValidationErrorResponse.java
    │   └── ApiErrorHandler.java
    └── test/java/com/example/validation/
        └── ValidationHttpTests.java
~~~

### 16.2 settings.gradle

~~~groovy
rootProject.name = 'webflux-validation-demo'
~~~

### 16.3 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chỉ có starter-webflux, không có starter-web. Java toolchain 17 đáp ứng Spring Boot 3.x và Java records. Các phiên bản dependency khác (Reactor, Netty, Hibernate Validator) do Spring Boot dependency management chọn đồng bộ; không tự ép version ngẫu nhiên.

### 16.4 ValidationDemoApplication.java

~~~java
package com.example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }
}
~~~

### 16.5 SignupRequest.java

~~~java
package com.example.validation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank(message = "name is required")
        @Size(max = 40, message = "name is too long")
        String name,

        @NotBlank(message = "email is required")
        @Email(message = "email format is invalid")
        String email,

        @Min(value = 18, message = "age must be at least 18")
        int age) {
}
~~~

Constraints trên Java record components được Bean Validation provider phù hợp đọc trong Spring Boot 3.3. Không có code xác thực email gửi được thư và không có database. Trong ứng dụng production, kiểm tra business policy và xác thực email là bước riêng.

### 16.6 SignupController.java

~~~java
package com.example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class SignupController {

    @PostMapping(
            path = "/signup",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<SignupResponse>> signup(
            @Valid @RequestBody SignupRequest request) {

        SignupResponse response = new SignupResponse(
                "accepted", request.name(), request.email());

        return Mono.just(ResponseEntity.status(HttpStatus.CREATED)
                .body(response));
    }

    @PostMapping(
            path = "/signup-async",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<SignupResponse> signupAsync(
            @Valid @RequestBody Mono<SignupRequest> request) {

        return request.map(value -> new SignupResponse(
                "accepted", value.name(), value.email()));
    }

    @GetMapping(path = "/page", produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<PageResponse> page(
            @RequestParam(name = "page", defaultValue = "1")
            @Min(value = 1, message = "page must be at least 1")
            int page) {

        return Mono.just(new PageResponse(page));
    }
}

record SignupResponse(String status, String name, String email) {
}

record PageResponse(int page) {
}
~~~

**Không** thêm @Validated ở cấp class controller trong ví dụ này. Ta muốn Spring Framework 6.1 built-in method validation xử lý @Min trên page; việc đặt @Validated ở class có thể thay đổi sang AOP validation và làm khó so sánh exception.

### 16.7 ValidationErrorResponse.java

~~~java
package com.example.validation;

import java.util.List;
import java.util.Map;

public record ValidationErrorResponse(
        String code,
        Map<String, List<String>> fieldErrors,
        List<String> globalErrors) {
}
~~~

Response DTO không chứa BindingResult, FieldError object gốc hoặc rejectedValue. Nó chỉ công bố mã lỗi, tên field và thông báo đã được ứng dụng chủ động đưa vào.

### 16.8 ApiErrorHandler.java

~~~java
package com.example.validation;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ValidationErrorResponse> invalidDto(
            WebExchangeBindException exception) {

        Map<String, List<String>> fields = new TreeMap<>();

        for (FieldError field : exception.getFieldErrors()) {
            String message = field.getDefaultMessage() == null
                    ? "invalid value"
                    : field.getDefaultMessage();

            fields.computeIfAbsent(
                    field.getField(),
                    key -> new ArrayList<>()
            ).add(message);
        }

        List<String> global = exception.getGlobalErrors()
                .stream()
                .map(error -> error.getDefaultMessage() == null
                        ? "invalid object"
                        : error.getDefaultMessage())
                .toList();

        return ResponseEntity.badRequest().body(
                new ValidationErrorResponse(
                        "INVALID_REQUEST", fields, global));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ValidationErrorResponse> invalidMethod(
            HandlerMethodValidationException exception) {

        ValidationErrorResponse error = new ValidationErrorResponse(
                "METHOD_VALIDATION_FAILED",
                Map.of(),
                List.of("method validation failed"));

        return ResponseEntity.status(exception.getStatusCode())
                .body(error);
    }
}
~~~

Giải thích:

- invalidDto tập hợp tất cả FieldError, bao gồm nhiều lỗi trên một field.
- TreeMap được dùng để response có key order ổn định hơn khi đọc log/test, nhưng client không nên dựa vào thứ tự JSON keys.
- global chứa các lỗi cấp object (nếu có).
- Method validation dùng exception.getStatusCode() thay vì hardcode 400, để không vô tình báo 400 cho lỗi return value vốn có thể là 500.
- Trong ví dụ, method validation response cố ý **không tiết lộ chi tiết nội bộ**; nếu API cần field-level detail thì đọc danh sách ParameterValidationResult theo contract riêng.
- Không có handler chung cho mọi Exception, vì HTTP decode errors hoặc lỗi hệ thống khác nên đi theo handler chuẩn nếu chưa định nghĩa chính sách riêng.

### 16.9 ValidationHttpTests.java

~~~java
package com.example.validation;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ValidationHttpTests {

    @LocalServerPort
    private int port;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @Test
    void validDtoReturnsCreated() {
        client().post()
                .uri("/api/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "name", "An",
                        "email", "an@example.org",
                        "age", 21))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.status").isEqualTo("accepted")
                .jsonPath("$.name").isEqualTo("An");
    }

    @Test
    void invalidDtoReturnsStructuredFieldErrors() {
        client().post()
                .uri("/api/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "name", "",
                        "email", "bad",
                        "age", 16))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_REQUEST")
                .jsonPath("$.fieldErrors.name[0]")
                    .isEqualTo("name is required")
                .jsonPath("$.fieldErrors.email[0]")
                    .isEqualTo("email format is invalid")
                .jsonPath("$.fieldErrors.age[0]")
                    .isEqualTo("age must be at least 18");
    }

    @Test
    void invalidReactiveDtoUsesSameValidationContract() {
        client().post()
                .uri("/api/signup-async")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "name", "",
                        "email", "bad",
                        "age", 16))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_REQUEST");
    }

    @Test
    void invalidMethodParameterHasDifferentErrorCode() {
        client().get()
                .uri("/api/page?page=0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("METHOD_VALIDATION_FAILED");
    }

    @Test
    void validMethodParameterWorks() {
        client().get()
                .uri("/api/page?page=2")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.page").isEqualTo(2);
    }

    @Test
    void malformedJsonIsStillBadRequest() {
        client().post()
                .uri("/api/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void unsupportedMediaTypeIsRejected() {
        client().post()
                .uri("/api/signup")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("invalid")
                .exchange()
                .expectStatus().isUnsupportedMediaType();
    }
}
~~~

Test dùng RANDOM_PORT để HTTP server lấy một cổng trống, WebTestClient.bindToServer() gọi **HTTP qua TCP thật**. So với direct unit invocation, test này đi qua JSON decoder, argument resolver, Bean Validation, exception handling và response encoder của WebFlux.

Không assert body lỗi mặc định cho malformed JSON vì nó không phải WebExchangeBindException theo cùng contract; test chỉ kiểm tra status HTTP 400. Nếu ứng dụng có global handler bổ sung cho ServerWebInputException, cần cập nhật test theo chính sách đó.

Các kết quả ở trên là **kỳ vọng suy ra từ source code**, không phải báo cáo đã chạy lệnh trong môi trường hiện tại. Với Spring Boot hoặc Spring Framework version khác, phải test lại exception types và default status.

## 17. Chạy project và gửi request

Tại thư mục webflux-validation-demo:

~~~bash
gradle clean test
~~~

Nếu có Gradle wrapper:

~~~bash
./gradlew clean test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

Sau khi test thành công, chạy:

~~~bash
gradle bootRun
~~~

Mặc định thông thường server dùng port 8080 nếu không cấu hình khác và port còn trống.

### 17.1 Request hợp lệ

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/signup' \
  -H 'Content-Type: application/json' \
  -d '{"name":"An","email":"an@example.org","age":21}'
~~~

Body kỳ vọng với HTTP 201:

~~~json
{"status":"accepted","name":"An","email":"an@example.org"}
~~~

### 17.2 Request sai ba field

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/signup' \
  -H 'Content-Type: application/json' \
  -d '{"name":"","email":"bad","age":16}'
~~~

HTTP status kỳ vọng: 400. Body ví dụ:

~~~json
{
  "code": "INVALID_REQUEST",
  "fieldErrors": {
    "age": ["age must be at least 18"],
    "email": ["email format is invalid"],
    "name": ["name is required"]
  },
  "globalErrors": []
}
~~~

Trong DTO, mỗi field trên có một constraint chắc chắn fail với input minh họa. Thứ tự array khi một field có **nhiều** errors vẫn không nên trở thành API contract nếu không có quy tắc sort riêng.

### 17.3 Method validation khác DTO validation

~~~bash
curl -i 'http://127.0.0.1:8080/api/page?page=0'
~~~

HTTP 400 với body tương đương:

~~~json
{
  "code": "METHOD_VALIDATION_FAILED",
  "fieldErrors": {},
  "globalErrors": ["method validation failed"]
}
~~~

Tình huống này không phải lỗi JSON body và không phải WebExchangeBindException theo cơ chế method validation của Spring Framework 6.1.

### 17.4 JSON body malformed

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/signup' \
  -H 'Content-Type: application/json' \
  -d '{"name":'
~~~

Thông thường HTTP 400 do JSON decoding thất bại. Không suy luận rằng custom handler invalidDto sẽ luôn chạy.

### 17.5 Content-Type không hỗ trợ

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/signup' \
  -H 'Content-Type: text/plain' \
  -d 'plain text'
~~~

Với endpoint chỉ consumes application/json, HTTP 415 là kết quả mong đợi. Không dùng việc đổi validation annotations để sửa 415: phải sửa Content-Type, codec hoặc contract của endpoint.

## 18. Binding error khác business validation error

Bean Validation thường xử lý:

- name rỗng;
- email sai format;
- tuổi ngoài min/max;
- độ dài và pattern;
- ràng buộc chéo field nếu có custom validator phù hợp.

Business validation thường xử lý:

- username đã tồn tại;
- không còn hạn mức đăng ký;
- user không có quyền vào một tenant;
- trạng thái đơn hàng không cho phép cập nhật;
- tài nguyên liên quan không tồn tại;
- điều kiện thị trường hoặc tồn kho thay đổi.

Không làm database lookup blocking trong ConstraintValidator rồi coi đó là non-blocking chỉ vì app chạy WebFlux. Với dữ liệu động, nên tách validation nghiệp vụ vào service/reactive repository, có status phù hợp như 409 Conflict, 404 Not Found hoặc 403 Forbidden theo nghĩa vụ API.

Ví dụ:

~~~java
return repository.existsByEmail(request.email())
        .flatMap(exists -> exists
                ? Mono.error(new ResponseStatusException(
                        HttpStatus.CONFLICT, "email already registered"))
                : repository.save(mapToEntity(request)));
~~~

Đây là pseudocode service có repository và mapper chưa định nghĩa; nó minh họa **ràng buộc dữ liệu động** và không phải class độc lập. Một HTTP 409 không đồng nghĩa WebExchangeBindException.

## 19. Validation groups và @Validated

Đôi khi cùng DTO có quy tắc khác nhau giữa tạo và cập nhật. Jakarta Bean Validation hỗ trợ **groups**, còn Spring có @Validated để chọn group cụ thể.

Ví dụ khái niệm:

~~~java
interface Create {}
interface Update {}

class Form {
    @NotBlank(groups = Create.class)
    private String password;

    // getters/setters theo yêu cầu binding
}
~~~

Đoạn code trên chỉ minh họa cơ chế groups. Khi dùng @Validated(Create.class) tại tham số DTO, validator có thể áp dụng group được chọn.

Cần tránh:

- Đặt @Validated ở controller class-level một cách tùy tiện nếu mục tiêu là built-in method validation Spring 6.1.
- Đổi groups mà quên Default group; những constraints không thuộc group hiện tại có thể không chạy.
- Trộn create/update request contract quá nhiều trong một DTO khiến người dùng API khó hiểu.
- Chỉ test happy path mà không test từng group và exception type.

Trong nhiều API, tách CreateRequest và UpdateRequest đơn giản, ít nhầm hơn dùng nhiều groups chồng nhau.

## 20. Custom constraints và global object errors

Nếu cần quy tắc như startDate <= endDate, có thể viết một class-level Jakarta constraint với ConstraintValidator. Việc đặt lỗi ở cấp object hoặc field phụ thuộc cách ConstraintValidatorContext tạo violations.

Ví dụ hợp đồng:

~~~text
BookingRequest:
  startDate: 2026-12-10
  endDate:   2026-12-09
Validation:
  startDate must not be after endDate
~~~

Nếu validator trả một object-level violation, WebExchangeBindException có thể có **globalErrors**. Nếu validator dùng addPropertyNode("endDate"), lỗi có thể xuất hiện trong **fieldErrors.endDate**. Hãy test chính xác nơi lỗi được đặt thay vì giả định mọi custom constraint đều là global error.

Trong môi trường reactive, ConstraintValidator thường thực hiện nhanh, đồng bộ và không blocking. Tránh query database hoặc gửi HTTP từ validator. Nếu cần thông tin bên ngoài, dùng reactive service ở tầng nghiệp vụ.

## 21. Quốc tế hóa thông báo validation

Các annotation ví dụ dùng message cố định bằng tiếng Anh:

~~~java
@NotBlank(message = "name is required")
~~~

Trong ứng dụng có nhiều ngôn ngữ, nên dùng message keys và resource bundles:

~~~java
@NotBlank(message = "{signup.name.required}")
~~~

Ví dụ key trong resource phù hợp:

~~~properties
signup.name.required=Tên không được để trống
~~~

Cách khai báo bundle, Locale resolution và tương tác Bean Validation MessageInterpolator/MessageSource phụ thuộc cấu hình Spring Boot. Không mặc định chỉ tạo một file properties là đủ cho toàn bộ locale. Hãy kiểm tra Accept-Language, fallback locale và mã lỗi ổn định mà client dùng.

Một số API chọn trả **error codes** như NOT_BLANK hoặc EMAIL_INVALID thay vì lời nhắn đã localized. Client có thể tự hiển thị bản dịch; trong trường hợp đó server phải document error codes.

### ErrorResponse và MessageSource

Spring Framework 6.1 cho phép điều chỉnh message arguments của ErrorResponse, trong đó WebExchangeBindException mang danh sách errors. Khi chuẩn hóa ProblemDetail, có thể cấu hình MessageSource để resolve message codes. Giữ lại địa chỉ để tra cứu Javadoc của phiên bản đúng; không nhúng toàn bộ nội dung exception.getMessage() trực tiếp ra client.

## 22. Ngăn lộ thông tin khi trả lỗi

Một lỗi binding có thể liên quan input như mật khẩu, token, địa chỉ hoặc dữ liệu cá nhân. Trong production:

- Không serialize **exception** hoặc **BindingResult** trực tiếp thành JSON công khai.
- Không trả getRejectedValue() hoặc getFieldValue() cho mọi field.
- Không đưa stack trace, bean name nội bộ hoặc package Java vào response.
- Không log full request body trừ khi có chính sách loại bỏ dữ liệu nhạy cảm rõ ràng.
- Giới hạn độ dài JSON request, giới hạn parser depth và codec buffering phù hợp.
- Không để client tự quyết định tên class được deserialize qua polymorphic default typing thiếu kiểm soát.
- Thông báo trả cho client nên an toàn và được kiểm soát bằng mã lỗi.
- Nếu có nhiều field errors, tránh response body tăng vô hạn với input bất thường; chọn giới hạn hợp lý trong API.

Lưu ý custom message của Bean Validation có thể chứa giá trị động trong một số thiết kế. Review message templates và custom validators để không vô tình phản chiếu payload nhạy cảm.

## 23. Kích thước body, decoding và những giới hạn khác

Spring WebFlux codec có thể buffer dữ liệu khi decode một object. Cấu hình Boot thường gặp:

~~~properties
spring.codec.max-in-memory-size=256KB
~~~

Thuộc tính này giới hạn một số thao tác aggregate body của codecs, **không** phải một giới hạn tuyệt đối cho mọi HTTP request/stream. Nếu client gửi JSON rất lớn, có thể gặp DataBufferLimitException hoặc lỗi HTTP input/codec trước khi Bean Validation bắt đầu.

Những tình huống cần phân biệt:

| Trường hợp | Giai đoạn lỗi thường gặp | Hành động phù hợp |
| --- | --- | --- |
| JSON không đúng cú pháp | Decoder | Sửa JSON/request body |
| Content-Type sai | Mapping/codec | Sửa media type |
| JSON quá lớn | Buffering/parser/gateway | Thiết lập size limits rõ |
| Giá trị JSON string cho int | Deserialize/binding | Sửa dữ liệu và schema |
| DTO có name="" | Bean Validation | Sửa input theo @NotBlank |
| @RequestParam @Min(1) page=0 | Method validation | Sửa query parameter |
| User không được phép | Authentication/authorization | Trả 401/403 theo security policy |
| Email trùng database | Business validation | Xử lý 409 hoặc API contract phù hợp |

Không dùng một @ExceptionHandler(WebExchangeBindException.class) để giải quyết toàn bộ các lỗi trên.

## 24. WebFlux và MVC: tránh nhầm vì annotation giống nhau

| Khía cạnh | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Front controller | DispatcherServlet | DispatcherHandler |
| Server thông thường trong starter | Tomcat | Reactor Netty |
| Đọc HTTP body | HttpMessageConverter | HttpMessageReader / reactive codecs |
| @Valid @RequestBody DTO | Có | Có |
| Lỗi DTO argument validation thông thường | MethodArgumentNotValidException | WebExchangeBindException |
| Method validation Spring 6.1 | HandlerMethodValidationException | HandlerMethodValidationException |
| Async request argument body | Servlet MVC có giới hạn/semantics khác | @RequestBody Mono<T> được hỗ trợ |
| Test phổ biến | MockMvc | WebTestClient |
| Cơ chế middleware | Servlet Filter / HandlerInterceptor | WebFilter / WebExceptionHandler |

Có Mono hoặc Flux trong return type **không** tự biến MVC thành WebFlux. Spring Boot thường chọn MVC nếu cả starter-web và starter-webflux xuất hiện. Để chẩn đoán exception không đúng mong đợi, hãy xác minh WebApplicationType, dependency tree và loại front controller trước.

Trong ứng dụng MVC, dùng @ExceptionHandler(MethodArgumentNotValidException.class) cho lỗi argument validation của MVC; trong ứng dụng WebFlux, dùng WebExchangeBindException. Spring Framework 6.1 method-level validation có thể dùng cùng class HandlerMethodValidationException ở cả hai, nhưng nội dung pipeline và argument resolution vẫn khác nhau.

## 25. Debug và quan sát các lỗi validation

### 25.1 Xác nhận validation dependency

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra spring-boot-starter-validation và Hibernate Validator trong runtime classpath. Nếu dependency bị exclude hoặc chỉ xuất hiện trong test, hành vi validation production có thể khác.

### 25.2 Bật logging theo mục tiêu

Ví dụ trong môi trường local:

~~~properties
logging.level.org.springframework.web.reactive.DispatcherHandler=DEBUG
logging.level.org.springframework.web.reactive.result.method.annotation=DEBUG
logging.level.org.springframework.web.server.adapter.HttpWebHandlerAdapter=DEBUG
~~~

Tùy version, các logger khác nhau có thể ghi ít hoặc nhiều thông tin. Đừng bật TRACE/raw request logging trên production chỉ để tìm một validation error nhỏ; hãy loại bỏ token hoặc thông tin riêng tư trước khi chia sẻ logs.

### 25.3 Breakpoint gợi ý

Trong IDE với source của Spring Framework tương ứng:

~~~text
RequestMappingHandlerAdapter.handle(...)
InvocableHandlerMethod.getMethodArgumentValues(...)
AbstractMessageReaderArgumentResolver.readBody(...)
ModelAttributeMethodArgumentResolver.resolveArgument(...)
HandlerMethodValidator.applyArgumentValidation(...)
WebExchangeBindException constructor/getBindingResult
ApiErrorHandler.invalidDto(...)
ApiErrorHandler.invalidMethod(...)
~~~

Đây là điểm quan sát gợi ý, method/overload có thể thay đổi theo patch version. Với request @RequestBody Mono<T>, đặt breakpoint ở reactive pipeline/decoder/validator và nhớ rằng Publisher có thể được subscribe muộn hơn so với lúc method trả về.

### 25.4 Theo dõi thứ tự xử lý

Đặt log/breakpoint ở:

1. HandlerMapping có match route chưa?
2. HTTP message reader có parse JSON không?
3. Bean Validation provider có thực sự chạy không?
4. Constraint nào fail, field hay global?
5. Spring đang dùng argument validation hay method validation?
6. Exception handler cụ thể nào được chọn?
7. Status/body đã được ghi và response đã commit chưa?
8. Client nhận đúng content type, status, body và field codes không?

## 26. Lỗi thiết kế thường gặp và cách sửa

### Lỗi 1: Chỉ dùng @Valid nhưng không có provider

Triệu chứng: name rỗng vẫn đi vào service.

Khắc phục: xác nhận spring-boot-starter-validation có trên runtimeClasspath và global validator được cấu hình hợp lệ; viết negative tests chứng minh constraint thật sự chạy.

### Lỗi 2: Bắt nhầm MethodArgumentNotValidException trong WebFlux

Triệu chứng: WebFlux endpoint trả lỗi validation nhưng @ExceptionHandler dành cho MVC không nhận.

Khắc phục: dùng WebExchangeBindException đúng package cho WebFlux; nếu có direct method constraints, thêm xử lý HandlerMethodValidationException.

### Lỗi 3: Chỉ bắt WebExchangeBindException, bỏ method validation

Triệu chứng: DTO invalid được trả JSON riêng, nhưng /api/page?page=0 có format lỗi khác.

Khắc phục: hiểu Spring Framework 6.1 method validation và xây error response nhất quán cho cả hai nguồn lỗi.

### Lỗi 4: Quên validate nested DTO

Triệu chứng: outer request hợp lệ dù inner Address.street rỗng.

Khắc phục: thêm @Valid cho nested property và test missing/null nested objects.

### Lỗi 5: Trả toàn bộ BindingResult

Triệu chứng: response chứa rejectedValue, objectName, stack metadata hoặc dữ liệu nhạy cảm.

Khắc phục: map FieldError/ObjectError sang public DTO, dùng error code/message được phép.

### Lỗi 6: Xử lý bằng Mono.error rồi tự subscribe

Triệu chứng: lỗi không đến HTTP client, response 200 rỗng, race condition.

Khắc phục: return reactive chain; dùng onErrorResume hoặc @RestControllerAdvice.

### Lỗi 7: Cho rằng malformed JSON là WebExchangeBindException

Triệu chứng: JSON sai cú pháp không đi qua invalidDto handler.

Khắc phục: phân biệt decoder exception với Bean Validation; viết test riêng cho cả hai.

### Lỗi 8: Hardcode 400 cho mọi method validation

Triệu chứng: return value của controller vi phạm constraint nhưng hệ thống gửi lỗi như client nhập sai.

Khắc phục: dùng ex.getStatusCode() hoặc chính sách phân loại rõ; lỗi return value thường thuộc trách nhiệm server.

### Lỗi 9: Quên BindingResult ngay sau tham số

Triệu chứng: code muốn xử lý lỗi local nhưng Spring vẫn ném exception.

Khắc phục: dùng đúng vị trí argument, hoặc chọn global advice; với Mono<T> dùng reactive error operators.

### Lỗi 10: Bật @Validated class-level và kỳ vọng built-in method validation

Triệu chứng: exception type khác dự kiến khi framework/AOP intercept method.

Khắc phục: hiểu AOP validation vs built-in Spring Framework 6.1; bỏ class-level @Validated khi muốn cơ chế built-in như tài liệu mô tả.

### Lỗi 11: Dùng constraint cho chính sách nghiệp vụ động

Triệu chứng: validator gọi database blocking từ Netty event loop, gây latency và timeout.

Khắc phục: tách validation cú pháp vào Bean Validation; kiểm tra nghiệp vụ dùng reactive service/repository.

### Lỗi 12: Không kiểm thử nhiều field lỗi

Triệu chứng: response chỉ trả một lỗi vì dùng getFieldError() thay getFieldErrors().

Khắc phục: dùng cấu trúc field → list errors, thêm integration test gửi request sai nhiều field cùng lúc.

### Lỗi 13: Cho rằng validation bảo đảm authorization

Triệu chứng: tenantId đúng format nhưng truy cập sai tenant vẫn được phép.

Khắc phục: Spring Security/reactive security chain và policy cấp service/resource mới xác minh quyền truy cập.

### Lỗi 14: Viết test gọi controller trực tiếp

Triệu chứng: new SignupController().signup(...) không hề chạy HTTP codec/validator.

Khắc phục: dùng WebTestClient với WebFlux context hoặc HTTP thật; test direct invocation chỉ phù hợp logic method riêng.

## 27. Checklist thực hành cuối

1. Xác nhận ứng dụng chạy Spring WebFlux reactive stack.
2. Có spring-boot-starter-validation và Jakarta Validation provider đúng version.
3. Request DTO có các constraint rõ ràng, test được.
4. @Valid/@Validated được dùng đúng ở method arguments.
5. Phân biệt @Valid trên object với direct @Min/@NotBlank trên method parameter.
6. Hiểu khi nào WebExchangeBindException và HandlerMethodValidationException xuất hiện.
7. Không coi malformed JSON, 415 hoặc 404 là Bean Validation error.
8. Duyệt cả fieldErrors và globalErrors khi xây error response.
9. Không trả rejected values, token, stack trace hoặc metadata nội bộ.
10. Dùng @RestControllerAdvice hoặc ResponseEntityExceptionHandler theo một contract nhất quán.
11. Giữ HTTP status hợp lý: 400 cho invalid input, 500 cho server return validation failure, 401/403 cho security khi thích hợp.
12. Với Mono<DTO>, để framework subscribe; không tự gọi subscribe()/block().
13. Khi dùng BindingResult, đặt đúng sau tham số sync được hỗ trợ.
14. Không làm blocking I/O trong custom constraint hoặc exception handler.
15. Test valid DTO, invalid DTO, invalid reactive DTO, method validation, malformed JSON và wrong Content-Type.
16. Kiểm tra null/missing/nested object/validation groups theo contract thực tế.
17. Đặt giới hạn body/codec và kiểm soát log nhạy cảm.
18. Kiểm tra API version và tài liệu trước khi đổi Spring Framework 6.x sang 7.x.

## 28. Tóm tắt

**WebExchangeBindException** là lỗi binding/validation ở mức **một object argument** trong Spring WebFlux, thường xuất hiện với @Valid @RequestBody, @ModelAttribute hoặc @RequestPart. Nó cung cấp BindingResult, field errors và global errors, giúp API trả HTTP 400 cùng thông tin client có thể sửa mà không cần expose raw input. Với Spring Framework 6.1, **HandlerMethodValidationException** là nhánh khác khi method-level constraints được áp dụng; một ứng dụng nên hiểu và kiểm thử cả hai loại thay vì bắt duy nhất WebExchangeBindException.

Từ góc nhìn thiết kế, validation phải được tách khỏi decoding, authentication/authorization và quy tắc nghiệp vụ động. Test HTTP WebFlux thật, error body có contract ổn định, không blocking reactive pipeline và không đưa rejected values nhạy cảm ra client là những nền tảng cho API có thể bảo trì.

## 29. Tài liệu tham khảo

- Spring Framework — WebFlux Validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html
- Spring Framework — WebFlux @RequestBody: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework — WebFlux @ModelAttribute: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework — WebFlux Error Responses: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Spring Framework 6.1 — WebExchangeBindException API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html
- Spring Framework 6.1 — HandlerMethodValidationException API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.1 — ResponseEntityExceptionHandler API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html
- Spring Boot 3.3 — Validation: https://docs.spring.io/spring-boot/3.3/reference/io/validation.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Jakarta Bean Validation Specification: https://jakarta.ee/specifications/bean-validation/

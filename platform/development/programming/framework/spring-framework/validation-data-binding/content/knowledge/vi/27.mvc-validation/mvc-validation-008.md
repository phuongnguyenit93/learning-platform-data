# HandlerMethodValidationException khi kiểm tra phương thức trong Spring MVC

Trong **Spring MVC từ Spring Framework 6.1**, controller có thể được kiểm tra **trực tiếp ở cấp phương thức** (*built-in handler method validation*) mà không cần tạo AOP proxy chỉ để validate controller. Khi một hoặc nhiều ràng buộc Jakarta Validation trên **tham số** hoặc **giá trị trả về** của handler không đạt, Spring có thể phát sinh **`HandlerMethodValidationException`**.

Ví dụ:

~~~java
@GetMapping("/items/{id}")
public ItemDto getItem(
        @PathVariable("id") @Min(1) long id,
        @RequestParam(name = "count", defaultValue = "1")
        @Min(1) @Max(10) int count) {
    return itemService.load(id, count);
}
~~~

Nếu request là `GET /items/0?count=0`, cả `id` và `count` đều được chuyển thành số Java thành công, nhưng cùng **vi phạm `@Min(1)`**. Với MVC method validation được cấu hình đúng, framework thu thập lỗi theo từng tham số và ném `HandlerMethodValidationException`; handler không chạy với bộ tham số không hợp lệ ấy.

Ngược lại, `GET /items/abc?count=2` thất bại **trong bước chuyển kiểu** từ `"abc"` sang `long`, trước khi validator đánh giá `@Min`. Lỗi này thường là `MethodArgumentTypeMismatchException`, **không phải** `HandlerMethodValidationException`.

Bài học tập trung vào tên exception, điều kiện kích hoạt, cấu trúc dữ liệu lỗi, xử lý HTTP, phân biệt với những loại lỗi khác và một ví dụ **Spring Boot 3.4+/Spring Framework 6.2, Java 17+** có thể chạy/kiểm thử. Trường hợp dùng Spring Framework 6.1 có cùng ý tưởng nền tảng nhưng cần đối chiếu chữ ký API cụ thể của phiên bản.

## 1. Định vị exception trong vòng đời Spring MVC

`HandlerMethodValidationException` thuộc package:

~~~java
import org.springframework.web.method.annotation.HandlerMethodValidationException;
~~~

Nó được Spring MVC ném trong cơ chế kiểm tra **handler method**, không phải exception mà Jakarta Validation provider luôn tự ném cho mọi phương thức Java. Dù quá trình kiểm tra sử dụng Jakarta Validation ở bên dưới, Spring trình bày kết quả qua mô hình **`MethodValidationResult` / `ParameterValidationResult`**.

Một request đi qua chuỗi khái quát:

~~~text
HTTP request
    |
    v
DispatcherServlet -> chọn @RequestMapping handler
    |
    v
HandlerMethodArgumentResolver
    |  đọc @PathVariable / @RequestParam / @RequestBody...
    |  bind dữ liệu, chuyển String -> Java type
    v
Spring MVC built-in method validation
    |  kiểm tra constraint trực tiếp trên parameters
    |  và @Valid cascade bên trong những đối số liên quan
    |
    +-- không vi phạm: gọi controller method
    |
    +-- có vi phạm, không được BindingResult xử lý đầy đủ:
    |          |
    |          v
    |     HandlerMethodValidationException (input -> HTTP 400)
    |
    v
Controller method chạy, tạo return value
    |
    v
Kiểm tra constraint trên return value nếu có
    |
    +-- vi phạm -> HandlerMethodValidationException
    |                (return value -> HTTP 500)
    |
    v
HTTP message conversion / rendering
~~~

Sơ đồ mô tả hành vi đồng bộ thông dụng. Nếu argument resolver không thể đọc JSON hoặc chuyển kiểu (`page=xyz` sang `int`), nó có thể ném một exception khác ngay **trước** method validation. Tương tự, lỗi nghiệp vụ trong body handler không tự biến thành validation exception.

**Quan trọng:** Spring MVC có method validation tích hợp từ **Spring Framework 6.1**. Nếu đặt `@Validated` ở **cấp class của controller**, Spring có thể kích hoạt **AOP-based method validation** thay vì nhánh built-in này. Tài liệu Spring khuyến nghị **bỏ class-level `@Validated` khỏi controller** nếu muốn dùng cơ chế MVC tích hợp.

## 2. Khi nào `HandlerMethodValidationException` xuất hiện?

Để có cơ chế built-in thông dụng cần:

1. Ứng dụng Spring MVC ở phiên bản hỗ trợ (Spring Framework 6.1+).
2. Có `jakarta.validation.Validator` phù hợp trong MVC configuration, chẳng hạn `LocalValidatorFactoryBean` được Spring Boot cấu hình khi có validation starter/provider.
3. Handler khai báo **constraint trực tiếp** trên một tham số như `@Min`, `@NotBlank`, `@Size`, `@Pattern` hoặc trên giá trị trả về của method như `@NotNull`.
4. Dữ liệu đã đi qua argument resolution/type conversion, và validation phát hiện ít nhất một vi phạm không được xử lý bởi cơ chế `Errors`/`BindingResult` đúng quy tắc.
5. Controller không bị chuyển sang cơ chế AOP validation khác bởi class-level `@Validated` nếu mục tiêu là built-in MVC.

Ví dụ tham số:

~~~java
@GetMapping("/search")
public String search(
        @RequestParam("q") @NotBlank String q,
        @RequestParam(defaultValue = "1") @Min(1) int page) {
    return "q=" + q + ",page=" + page;
}
~~~

`@NotBlank` trên `q` và `@Min` trên `page` là **các constraint trực tiếp**. Nếu `q` rỗng và `page=0`, method validation áp dụng ở cấp handler; hai đối số có thể đóng góp các lỗi riêng.

Ví dụ return value:

~~~java
@GetMapping("/current-code")
@NotNull
public String currentCode() {
    return null;
}
~~~

`@NotNull` trên method là **return-value constraint**. Nếu method thực thi và trả `null`, vi phạm được phát hiện **sau khi method chạy**. Đây thường là lỗi **hợp đồng của server**, do đó `HandlerMethodValidationException` cung cấp HTTP **500** thay vì 400.

> **Không đồng nhất “có `@Valid`” với “chắc chắn có method validation”.** `@Valid` bản thân là annotation yêu cầu cascade vào object lồng nhau, **không phải `@Constraint`**. Một đối số DTO chỉ mang `@Valid` thường đi theo đường validation riêng của argument resolver. Khi cùng handler có constraint trực tiếp ở đối số khác/return value, MVC method validation có thể bao quát cả constraint lồng trong DTO `@Valid`.

## 3. Ba trường hợp dễ nhầm: `@Valid`, constraint trực tiếp và lỗi chuyển kiểu

### 3.1. Chỉ có `@Valid @RequestBody`: thường là `MethodArgumentNotValidException`

~~~java
@PostMapping("/dto-only")
public String create(@Valid @RequestBody CreateRequest body) {
    return body.customerCode();
}
~~~

Giả sử `CreateRequest` là record:

~~~java
public record CreateRequest(
        @NotBlank String customerCode,
        @Min(1) int quantity) {
}
~~~

Cả hai snippet là minh họa; mã đầy đủ có ở phần 6. Nếu gửi JSON:

~~~json
{
  "customerCode": "",
  "quantity": 0
}
~~~

Jackson có thể deserialize object, sau đó `@Valid` yêu cầu Bean Validation kiểm tra DTO. Khi **không có constraint trực tiếp khác khiến method-level validation được yêu cầu**, lỗi thường đi theo `MethodArgumentNotValidException`. Exception này gắn với **một object argument** và `BindingResult` của object ấy.

### 3.2. Thêm constraint trực tiếp: trở thành validation cấp method

~~~java
@PostMapping("/checkout")
public Receipt checkout(
        @Valid @RequestBody CreateRequest body,
        @RequestParam("channel")
        @Pattern(regexp = "web|store") String channel) {
    return new Receipt(body.customerCode(), body.quantity(), channel);
}
~~~

`@Pattern` trên tham số `channel` là constraint **trực tiếp**. Trong MVC 6.1+, method validation có thể thay thế bước validation đơn lẻ của DTO để **đánh giá cả `channel` và constraint bên trong `body`**. Với body không hợp lệ và `channel=other`, `HandlerMethodValidationException` mang kết quả được nhóm theo các **method parameters** liên quan.

Điều này không có nghĩa Spring validate hai lần. Spring MVC phối hợp argument validation và method validation để tránh trùng lặp trong trường hợp method-level validation là đường đúng.

### 3.3. Parse không được: chưa tới Bean Validation

~~~text
GET /api/items/not-a-number?count=2
               |
               v
@PathVariable long id
               |
         Type conversion FAILED
               |
               v
MethodArgumentTypeMismatchException
               |
             HTTP 400
~~~

Một chuỗi không parse được thành `long` là lỗi **argument resolution / conversion**. Không nên test nó bằng cách chờ một `ConstraintViolation` của `@Min(1)`: Spring chưa có một giá trị kiểu `long` hợp lệ để đưa vào `@Min`.

| Tình huống | Cơ chế kiểm tra | Exception thường gặp |
|---|---|---|
| `@Valid @RequestBody Dto`, chỉ validate object | Argument-level Bean Validation | `MethodArgumentNotValidException` |
| `@Min(1) @RequestParam int page`, gửi `0` | Built-in handler method validation | `HandlerMethodValidationException` |
| `@NotBlank @RequestHeader String code`, gửi header rỗng | Built-in handler method validation | `HandlerMethodValidationException` |
| `@NotNull` trên return value, method trả `null` | Built-in handler return-value validation | `HandlerMethodValidationException` |
| `@RequestParam int page`, gửi `abc` | Type conversion | `MethodArgumentTypeMismatchException` |
| Thiếu required `@RequestParam` | Argument resolution | `MissingServletRequestParameterException` |
| Body JSON không parse được | HTTP message conversion | `HttpMessageNotReadableException` |
| Service `@Validated` đi qua AOP proxy | Spring AOP method validation | Thường `ConstraintViolationException` theo mặc định |

Bảng này mô tả **đường Spring MVC mặc định**. Application có thể thay đổi xử lý lỗi qua `@ControllerAdvice`, provider và AOP configuration. Vì vậy khi debug, luôn xác định **lỗi phát sinh ở pha nào**.

## 4. Cấu trúc `HandlerMethodValidationException`

`HandlerMethodValidationException` mở rộng `ResponseStatusException` và triển khai `MethodValidationResult` cùng `ErrorResponse`. Nhờ vậy exception vừa mang **HTTP status/problem details**, vừa mang **nhóm lỗi validation của từng parameter**.

Các API có ích trong Spring Framework 6.2:

| API | Ý nghĩa |
|---|---|
| `ex.getStatusCode()` | HTTP status: **400** khi input parameters vi phạm, **500** khi return value vi phạm |
| `ex.isForReturnValue()` | `true` nếu đây là vi phạm return value; `false` nếu là input |
| `ex.getMethod()` | Method Java được kiểm tra |
| `ex.getTarget()` | Target của method invocation |
| `ex.getParameterValidationResults()` | Danh sách `ParameterValidationResult`, được nhóm **theo tham số / return descriptor** có lỗi |
| `ex.getCrossParameterValidationResults()` | Lỗi cross-parameter, nếu có constraint đánh giá nhiều tham số cùng lúc |
| `ex.getAllErrors()` | Các lỗi validation dưới dạng `MessageSourceResolvable`/mô hình kết quả tương ứng |
| `ex.visitResults(visitor)` | Duyệt kết quả theo loại controller argument như `@RequestParam`, `@RequestHeader`, `@ModelAttribute` |
| `ex.getBody()` | `ProblemDetail` theo hợp đồng `ErrorResponse`; có thể được cấu hình/i18n |
| `ex.getDetailMessageArguments(...)` | Tham số nội suy thông báo lỗi, có biến thể nhận `MessageSource` và `Locale` |

**Số lượng `ParameterValidationResult` không nhất thiết bằng số violation.** Một DTO `@Valid` có hai field sai vẫn có thể xuất hiện như **một parameter result**, chứa hai field errors. Ngược lại, hai `@RequestParam` khác nhau bị sai thường tạo hai parameter results. Nếu cần hiển thị thông báo từng lỗi, duyệt vào sâu hơn thay vì chỉ gọi `size()`.

Ví dụ cách kiểm tra trạng thái:

~~~java
HandlerMethodValidationException ex = /* exception đã bắt */;

int status = ex.getStatusCode().value();
boolean isReturnFailure = ex.isForReturnValue();
int affectedParameters =
    ex.getParameterValidationResults().size();
~~~

Đây là một **snippet giải thích API** bên trong exception handler, không phải một class Java độc lập. Khi phát triển API cho client, nên để lộ **thông tin đầu vào nào sai** chứ không công khai mọi chi tiết internal Java method/provider.

### 4.1. `ParameterValidationResult` và `ParameterErrors`

`ParameterValidationResult` đại diện các lỗi gắn với **một tham số được validate**; từ đó có thể truy cập thông tin method parameter, giá trị argument và danh sách lỗi dạng `MessageSourceResolvable`. Khi đối số là bean được validate lồng nhau bằng `@Valid`, MVC có thể dùng `ParameterErrors` để biểu diễn **field/object errors** tương tự `Errors` của Spring.

Luồng ý nghĩa:

~~~text
HandlerMethodValidationException
├── ParameterValidationResult: @PathVariable id
│   └── @Min(1) không đạt
├── ParameterValidationResult: @RequestParam page
│   └── @Min(1) không đạt
└── ParameterErrors: @RequestBody CreateRequest (nếu có)
    ├── customerCode -> @NotBlank
    └── quantity -> @Min(1)
~~~

Đây là sơ đồ một **tình huống tổng hợp minh họa**, không phải khẳng định một handler cụ thể có cả ba input trên. Các result là dữ liệu validation có cấu trúc, không phải các dòng log hoặc `ConstraintViolationException` gốc cần parse từ chuỗi message.

### 4.2. `Visitor`: phân loại lỗi theo annotation của controller

Đối với API trả lỗi khác nhau cho query, header, model attribute..., Spring cung cấp visitor. Phần rút gọn, dùng như snippet trong handler:

~~~java
ex.visitResults(
    new HandlerMethodValidationException.Visitor() {

        @Override
        public void requestParam(
                RequestParam annotation,
                ParameterValidationResult result) {
            // Lỗi thuộc tham số @RequestParam.
        }

        @Override
        public void requestHeader(
                RequestHeader annotation,
                ParameterValidationResult result) {
            // Lỗi thuộc @RequestHeader.
        }

        @Override
        public void modelAttribute(
                ModelAttribute annotation,
                ParameterErrors errors) {
            // Lỗi field/object của @ModelAttribute.
        }

        @Override
        public void other(ParameterValidationResult result) {
            // Fallback cho loại argument không có callback riêng.
        }
    }
);
~~~

Đây là snippet minh họa, cần import `HandlerMethodValidationException`, `RequestParam`, `RequestHeader`, `ModelAttribute`, `ParameterValidationResult` và `ParameterErrors` nếu dùng trong code thật. Một số callback annotation nhận giá trị có thể `null` nên đừng tùy ý dereference annotation trong logic xử lý; kiểm tra signature theo phiên bản Spring đang dùng.

Spring còn hỗ trợ callback cho các loại parameter khác như path variable, request body và request part. Visitor giúp code không cần ép mọi method parameter về một loại field error cố định.

Nếu chỉ cần biết request không hợp lệ để trả response tối giản, không bắt buộc phải dùng visitor. `getParameterValidationResults()` là đủ để thống kê theo parameter; visitor hữu ích khi tạo messages/paths chuẩn hóa.

## 5. HTTP 400 và HTTP 500: không phải sự khác biệt tùy ý

Theo API contract của Spring Framework, `HandlerMethodValidationException.getStatusCode()`:

- **HTTP 400 Bad Request** khi **method input** vi phạm constraint.
- **HTTP 500 Internal Server Error** khi **method return value** vi phạm constraint.

Ví dụ:

~~~java
@GetMapping("/profiles/{id}")
@NotNull
public ProfileDto find(@PathVariable("id") @Min(1) long id) {
    return repository.findById(id).orElse(null);
}
~~~

Đây là method minh họa cần một `ProfileDto` và `repository` phù hợp; không thuộc demo runnable bên dưới. Hai luồng:

1. `id=0` → đầu vào vi phạm `@Min(1)`, handler không chạy → **400**.
2. `id=5` → đầu vào hợp lệ; handler chạy và trả `null`, vi phạm `@NotNull` ở return → **500**.

Lưu ý rằng lỗi **tài nguyên không tồn tại** thường nên xử lý bằng nghiệp vụ (chẳng hạn HTTP 404) thay vì chủ ý trả `null` rồi dựa vào `@NotNull` để tạo 500. Return-value validation diễn đạt **một hợp đồng server bị phá vỡ**. Một method đã có side effects không tự rollback chỉ vì return-value constraint sai: transaction/side-effect behavior còn phụ thuộc cấu hình giao dịch và điểm commit.

**Khi tùy chỉnh response**, không nên mã hóa mọi `HandlerMethodValidationException` thành HTTP 400. Phải tôn trọng `ex.getStatusCode()` hoặc trạng thái `status` được Spring cung cấp, vì nhánh return-value có ngữ nghĩa server error khác.

## 6. Ví dụ chạy được bằng Spring Boot 3.4+ và Java 17+

Ứng dụng minh họa:

- GET `/api/items/{id}` có `@Min` trên path variable và query parameter.
- POST `/api/dto-only` chỉ có `@Valid @RequestBody` để thấy `MethodArgumentNotValidException`.
- POST `/api/checkout?channel=...` có `@Valid @RequestBody` **và** constraint trực tiếp `@Pattern` để thấy `HandlerMethodValidationException`.
- GET `/api/broken` có return-value `@NotNull` nhưng cố tình trả `null` để chứng minh HTTP 500.
- Một `@RestControllerAdvice` thống nhất response JSON nhưng vẫn phân biệt loại exception và trạng thái.

Ví dụ được thiết kế cho **Spring Boot 3.4/3.5, Spring Framework 6.2, Java 17+** với dependency web/validation. Không dùng class-level `@Validated` trên controller. Các file được đặt trong cùng package `com.example.mvcmethodvalidation` để Spring component scan có thể tìm thấy.

### 6.1. Dependency Gradle

Trong project Spring Boot đã có Boot Gradle plugin và dependency management, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-web` cung cấp Servlet MVC/web server, còn starter validation cung cấp Jakarta Validation provider. Thiếu provider thì constraint annotation chỉ là metadata, không đủ cho demo method validation.

Chạy qua Gradle wrapper của một project Boot hợp lệ; **không thể dùng `javac` thuần từ JDK** cho những class import Spring/Jakarta nếu không cung cấp đầy đủ dependency classpath.

### 6.2. Tệp `MvcMethodValidationApplication.java`

Đường dẫn: `src/main/java/com/example/mvcmethodvalidation/MvcMethodValidationApplication.java`

~~~java
package com.example.mvcmethodvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcMethodValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcMethodValidationApplication.class, args);
    }
}
~~~

### 6.3. DTO `CheckoutRequest.java`

Đường dẫn: `src/main/java/com/example/mvcmethodvalidation/CheckoutRequest.java`

~~~java
package com.example.mvcmethodvalidation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CheckoutRequest(
    @NotBlank String customerCode,
    @Min(1) int quantity
) {
}
~~~

`customerCode` không được rỗng/trắng, `quantity` phải lớn hơn hoặc bằng 1. Java record đơn giản hóa deserialize JSON và validation; các constraint gắn vào record components/constructor/property theo Java annotation targets tương ứng.

### 6.4. Controller `DemoController.java`

Đường dẫn: `src/main/java/com/example/mvcmethodvalidation/DemoController.java`

~~~java
package com.example.mvcmethodvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/items/{id}")
    public ItemView findItem(
            @PathVariable("id") @Min(1) long id,
            @RequestParam(
                name = "count", defaultValue = "1")
            @Min(1) @Max(10) int count) {

        return new ItemView(id, count);
    }

    @PostMapping("/dto-only")
    public Receipt dtoOnly(
            @Valid @RequestBody CheckoutRequest request) {

        return new Receipt(
            request.customerCode(),
            request.quantity(),
            "direct");
    }

    @PostMapping("/checkout")
    public Receipt checkout(
            @Valid @RequestBody CheckoutRequest request,
            @RequestParam("channel")
            @Pattern(regexp = "web|store") String channel) {

        return new Receipt(
            request.customerCode(),
            request.quantity(),
            channel);
    }

    @GetMapping("/broken")
    @NotNull
    public String brokenReturnValue() {
        return null;
    }

    public record ItemView(long id, int count) {
    }

    public record Receipt(
        String customerCode,
        int quantity,
        String channel
    ) {
    }
}
~~~

Những khác biệt quan trọng:

1. `@Min(1)` trên `id`/`count` là constraint **trực tiếp trên method parameters**, nên kích hoạt MVC method validation.
2. `@Valid` trong `dtoOnly` yêu cầu validate DTO nhưng **không** tự tạo direct parameter constraint; trường hợp đó thường đi theo argument-level validation.
3. `@Pattern` ở `channel` khiến `checkout` cần **method validation**, có thể bao gồm cả cascade từ `@Valid CheckoutRequest`.
4. `@NotNull` trên `brokenReturnValue` là constraint **trên method return value**, được kiểm tra sau khi controller method chạy.
5. Không có `@Validated` cấp class, bởi mục tiêu là **Spring MVC built-in method validation** chứ không phải AOP service validation.

Nếu có Spring Security hoặc các advice/proxy được thêm bởi dự án thật, cần kiểm tra cấu hình của chúng; demo thuần chỉ dùng Spring Web + Validation.

### 6.5. Advice `ApiErrors.java`: xử lý riêng hai loại lỗi

Đường dẫn: `src/main/java/com/example/mvcmethodvalidation/ApiErrors.java`

~~~java
package com.example.mvcmethodvalidation;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiErrors extends ResponseEntityExceptionHandler {

    public record ApiError(
        String code,
        int status,
        boolean returnValue,
        int affectedParameters
    ) {
    }

    @Override
    protected ResponseEntity<Object>
            handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ApiError body = new ApiError(
            "METHOD_VALIDATION",
            status.value(),
            ex.isForReturnValue(),
            ex.getParameterValidationResults().size());

        return handleExceptionInternal(
            ex, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ApiError body = new ApiError(
            "ARGUMENT_VALIDATION",
            status.value(),
            false,
            1);

        return handleExceptionInternal(
            ex, body, headers, status, request);
    }
}
~~~

Đoạn này là **class hoàn chỉnh** cho demo Spring Framework 6.2. `ResponseEntityExceptionHandler` đã có một `@ExceptionHandler` trung tâm xử lý nhiều exception Spring MVC; ta **override các phương thức protected** để tùy chỉnh cách dựng body, không đăng ký một `@ExceptionHandler(HandlerMethodValidationException.class)` trùng lặp trong chính subclass đó.

Trường `affectedParameters` đếm **số đối số có nhóm lỗi**. Nó **không** đại diện số individual constraint violations: một `CheckoutRequest` có hai field sai vẫn là một parameter của method. Với `MethodArgumentNotValidException` trên một DTO, demo trả `1` vì đó là một object argument bị lỗi.

Ví dụ dùng status do framework cung cấp: nếu return-value validation thất bại, `status.value()` là **500**; nếu input thất bại, là **400**. Không “fix” giá trị 500 thành 400 chỉ vì cả hai đều liên quan đến validation.

Trong sản phẩm thực, body nên thêm thông tin an toàn cho người dùng, chẳng hạn path/field/messageCode, và correlation id. Demo cố ý chỉ đưa số nhóm lỗi để **không phụ thuộc vào ngôn ngữ của message interpolator** hay thứ tự lỗi.

### 6.6. Chạy chương trình và quan sát response

Từ root của project Spring Boot có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Ứng dụng dùng port 8080 mặc định nếu cấu hình không thay đổi. Với dữ liệu hợp lệ:

~~~bash
curl -i "http://localhost:8080/api/items/12?count=3"
~~~

Kỳ vọng **HTTP 200** và JSON (thứ tự property có thể khác):

~~~json
{
  "id": 12,
  "count": 3
}
~~~

Đầu vào có **hai parameter groups lỗi**:

~~~bash
curl -i "http://localhost:8080/api/items/0?count=0"
~~~

Kỳ vọng **HTTP 400** và JSON:

~~~json
{
  "code": "METHOD_VALIDATION",
  "status": 400,
  "returnValue": false,
  "affectedParameters": 2
}
~~~

Lỗi DTO đơn lẻ (không có direct method constraint khác):

~~~bash
curl -i -X POST "http://localhost:8080/api/dto-only" \
  -H "Content-Type: application/json" \
  -d '{"customerCode":"","quantity":0}'
~~~

Kỳ vọng **HTTP 400** và JSON:

~~~json
{
  "code": "ARGUMENT_VALIDATION",
  "status": 400,
  "returnValue": false,
  "affectedParameters": 1
}
~~~

Trường hợp trộn direct constraint và nested DTO:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/checkout?channel=other" \
  -H "Content-Type: application/json" \
  -d '{"customerCode":"","quantity":0}'
~~~

Kỳ vọng **HTTP 400** với:

~~~json
{
  "code": "METHOD_VALIDATION",
  "status": 400,
  "returnValue": false,
  "affectedParameters": 2
}
~~~

`CheckoutRequest` có **hai field violations** và `channel` có **một direct violation**; tuy nhiên `affectedParameters` là **2** vì có hai method parameters bị ảnh hưởng. Đây là điểm quan trọng khi thiết kế error contract.

Thử return-value violation:

~~~bash
curl -i "http://localhost:8080/api/broken"
~~~

Kỳ vọng **HTTP 500** với:

~~~json
{
  "code": "METHOD_VALIDATION",
  "status": 500,
  "returnValue": true,
  "affectedParameters": 1
}
~~~

Method `brokenReturnValue()` đã được gọi và trả `null`; lỗi thuộc **server contract** nên framework chọn 500. Đây là endpoint **cố tình sai** để học cơ chế, không phải mẫu thiết kế business API.

**Không diễn giải một response 400 từ `page=abc` là cùng đường xử lý với `@Min`.** Nó thường là type conversion exception; advice demo chỉ thay body của hai exception validation nên loại lỗi khác có thể được base `ResponseEntityExceptionHandler` xử lý theo default `ProblemDetail`.

## 7. Kiểm thử Spring MVC bằng MockMvc

Một unit test gọi trực tiếp `new DemoController().findItem(0, 0)` sẽ **không** kích hoạt argument resolution hay built-in MVC method validation. Cần test qua `MockMvc` hoặc HTTP thực.

Tệp: `src/test/java/com/example/mvcmethodvalidation/MethodValidationMvcTest.java`

~~~java
package com.example.mvcmethodvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodValidationMvcTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validInputPasses() throws Exception {
        mvc.perform(get("/api/items/12")
                .param("count", "3"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(12))
            .andExpect(jsonPath("$.count").value(3));
    }

    @Test
    void directConstraintsUseMethodValidation()
            throws Exception {
        mvc.perform(get("/api/items/0")
                .param("count", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("METHOD_VALIDATION"))
            .andExpect(jsonPath("$.affectedParameters")
                .value(2))
            .andExpect(result -> assertInstanceOf(
                HandlerMethodValidationException.class,
                result.getResolvedException()));
    }

    @Test
    void dtoOnlyUsesArgumentValidation()
            throws Exception {
        mvc.perform(post("/api/dto-only")
                .contentType("application/json")
                .content(
                    "{\"customerCode\":\"\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("ARGUMENT_VALIDATION"))
            .andExpect(result -> assertInstanceOf(
                MethodArgumentNotValidException.class,
                result.getResolvedException()));
    }

    @Test
    void directConstraintAlsoValidatesNestedDto()
            throws Exception {
        mvc.perform(post("/api/checkout")
                .param("channel", "other")
                .contentType("application/json")
                .content(
                    "{\"customerCode\":\"\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("METHOD_VALIDATION"))
            .andExpect(jsonPath("$.affectedParameters")
                .value(2))
            .andExpect(result -> assertInstanceOf(
                HandlerMethodValidationException.class,
                result.getResolvedException()));
    }

    @Test
    void invalidReturnValueIsServerError()
            throws Exception {
        mvc.perform(get("/api/broken"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code")
                .value("METHOD_VALIDATION"))
            .andExpect(jsonPath("$.returnValue").value(true))
            .andExpect(result -> assertInstanceOf(
                HandlerMethodValidationException.class,
                result.getResolvedException()));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

Với Spring Boot 3.4/3.5, Spring Framework 6.2, Validation starter và không có class-level `@Validated` trên controller, năm test kỳ vọng **PASS**. Các test xác nhận trực tiếp **exception class do MVC giải quyết** bên cạnh HTTP status/body; như vậy không bỏ qua trường hợp một exception khác vô tình tạo cùng mã 400.

Khi áp dụng vào dự án thật có Spring Security, custom filters, các `@ControllerAdvice` khác hoặc cấu hình AOP proxy, test có thể cần setup tương ứng. Nếu đang dùng Boot 4 / Spring Framework 7, kiểm tra imports/module test và compatibility của API trước khi copy.

## 8. `BindingResult`, `Errors` và quy tắc xử lý cục bộ

Không phải mọi vi phạm đều bắt buộc trở thành exception. Spring MVC cho phép kết hợp method validation với `Errors` hoặc `BindingResult` trên model/DTO argument.

Ví dụ:

~~~java
@PostMapping("/preview")
public String preview(
        @Valid @ModelAttribute("form") PreviewForm form,
        BindingResult errors,
        @RequestParam("priority") @Min(1) int priority) {

    if (errors.hasErrors()) {
        return "preview-form";
    }
    return "preview-result";
}
~~~

Đây là handler **minh họa trong một `@Controller` render view**, cần DTO `PreviewForm` và đúng imports; không thuộc project runnable ở phần 6. `BindingResult` nằm **ngay sau** `form` nên có thể nhận lỗi đối với object ấy.

Quy tắc của Spring MVC khi method validation được yêu cầu:

- Handler vẫn có thể được gọi nếu **tất cả validation errors** đều thuộc các method parameters có `Errors`/`BindingResult` **ngay sau** và được xử lý cục bộ.
- Nếu có lỗi trên **bất kỳ tham số nào khác** không có `Errors` tương ứng, framework ném `HandlerMethodValidationException` và handler không được gọi.
- `BindingResult` không phải giải pháp tổng quát cho một primitive `@RequestParam int`. Nó gắn với object argument cụ thể, không thu tất cả lỗi của những tham số trong chữ ký một cách tự động.

Trong snippet trên, nếu `form` sai nhưng `priority=2` hợp lệ, controller có thể đọc `errors` để render lại view. Nếu `priority=0`, direct constraint trên `priority` vi phạm, Spring có thể ném `HandlerMethodValidationException` dù `form` đã có `BindingResult` ngay sau nó.

Khi dùng `@RequestBody` hoặc `@ModelAttribute` cùng validation, luôn kiểm tra **vị trí `BindingResult`** và **các constraint trực tiếp khác** trên chữ ký handler. Đừng đoán exception class chỉ bằng cách nhìn `@Valid` ở một tham số.

## 9. `ResponseEntityExceptionHandler` và `@RestControllerAdvice`

Spring có sẵn `ResponseEntityExceptionHandler` để xử lý tập exception phổ biến của Spring MVC. Với Spring Framework 6.2, method dành riêng cho trường hợp này có chữ ký:

~~~java
protected ResponseEntity<Object>
    handleHandlerMethodValidationException(
        HandlerMethodValidationException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request)
~~~

Vì method là `protected` và class đã có `@ExceptionHandler` trung tâm, pattern extension đúng là:

~~~java
@RestControllerAdvice
public class GlobalErrors extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object>
            handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return handleExceptionInternal(
            ex,
            ex.getBody(),
            headers,
            status,
            request
        );
    }
}
~~~

Đây là ví dụ **thay thế** cho `ApiErrors.java` ở phần 6, không thêm hai class advice cùng override nếu không có chủ đích. Đoạn minh họa cần imports đầy đủ như trong `ApiErrors`. Nó giữ `ProblemDetail` chuẩn từ exception; trong project thật có thể thêm dữ liệu theo contract API nhưng phải tránh tiết lộ dữ liệu nhạy cảm.

### Vì sao không chỉ viết `@ExceptionHandler(Exception.class)`?

Một handler bao quát tất cả exception dễ che giấu khác biệt giữa:

- Input validation (400).
- Return-value contract violation (500).
- Argument type mismatch / malformed JSON (400 nhưng **khác loại**).
- Not-found domain error (thường 404 theo thiết kế).
- Lỗi nội bộ không liên quan validation (500).

Nếu luôn trả 200 hoặc 400 cho tất cả, client/observability khó phân biệt lỗi của người dùng với bug server. Tốt hơn là dùng cơ chế exception handling có cấu trúc và giữ đúng status.

### `ProblemDetail` và RFC 9457

`HandlerMethodValidationException` triển khai `ErrorResponse` và có `ProblemDetail`. `ResponseEntityExceptionHandler` hỗ trợ tạo response dạng **problem details** theo RFC 9457, bao gồm các trường nền tảng như `type`, `title`, `status`, `detail`, `instance` tùy cấu hình.

Nếu ứng dụng chọn contract riêng như demo `ApiError`, đó là **lựa chọn của ứng dụng**, không phải JSON mặc định mà Spring luôn trả. Không viết test dựa vào một chuỗi `detail` hoặc localized message cố định khi ứng dụng có `MessageSource` và thay đổi locale.

### Quốc tế hóa và message source

Các lỗi validation có thể chứa `MessageSourceResolvable` với message codes/arguments. Để hiển thị tiếng Việt/tiếng Anh, dùng `MessageSource` / cấu hình locale phù hợp thay vì parse `ex.getMessage()` rồi hiển thị nguyên chuỗi.

Với những constraint có message templates, kết quả nội suy có thể phụ thuộc Jakarta message interpolator và locale. Đừng đưa tên class, giá trị password/token hoặc stack trace trực tiếp vào response công khai. Khi log, giữ correlation id, đường dẫn request và nhóm lỗi an toàn thay vì log toàn bộ request body.

## 10. Trường hợp kiểm tra giá trị trả về

Input validation thường chặn trước khi handler body chạy, nhưng return validation xảy ra **sau khi handler tạo kết quả**. Ví dụ:

~~~java
@GetMapping("/inventory")
@NotEmpty
public List<String> inventory() {
    return List.of();
}
~~~

Nếu built-in MVC method validation được cấu hình, danh sách rỗng vi phạm return-value `@NotEmpty`. Method đã thực thi, exception có:

~~~java
ex.isForReturnValue() == true
ex.getStatusCode().value() == 500
~~~

Đây là snippet minh họa, không phải test độc lập. Với một phương thức truy cập DB/ghi dữ liệu, không giả định Spring MVC return validation tự động **rollback transaction** hoặc đảo ngược các side effects đã xảy ra.

**Không dùng return constraint thay cho logic trả 404 khi dữ liệu không tồn tại.** Hãy biểu đạt kết quả “not found” trong service/controller theo HTTP contract cụ thể. Return-value validation hữu ích để phát hiện một giả định nội bộ bị phá vỡ (ví dụ method cam kết non-null nhưng implementation trả null).

Các trường hợp như `ResponseEntity<T>`, streaming, async và reactive cần đặc biệt kiểm tra **đối tượng nào** đang được validate và khi nào dữ liệu thật được tạo/ghi ra response; không suy luận từ một ví dụ return `String` đơn giản sang mọi wrapper bất đồng bộ.

## 11. AOP method validation khác built-in MVC như thế nào?

Cùng các constraint Jakarta Validation, nhưng cơ chế thực thi khác nhau.

| Đặc điểm | Built-in Spring MVC (6.1+) | Spring AOP method validation |
|---|---|---|
| Đối tượng thường áp dụng | `@RequestMapping` controller handler | Service/Spring bean được cấu hình `@Validated` |
| Điểm chặn | Trong pipeline MVC handler invocation | Lời gọi qua Spring AOP proxy |
| Thành phần chính | `HandlerMethodValidator` / MVC infrastructure | `MethodValidationPostProcessor`, `MethodValidationInterceptor` |
| Có cần class-level `@Validated`? | **Không**; nên bỏ khỏi controller để dùng built-in | Thường **có** trên bean |
| Lỗi input thường gặp | `HandlerMethodValidationException` | `ConstraintViolationException` mặc định |
| Lỗi trả về | `HandlerMethodValidationException` có status **500** | Exception tùy interceptor configuration |
| Tích hợp `BindingResult`/argument resolver | Tự nhiên trong MVC pipeline | Không tương đương một cách tự động |
| Giới hạn self-invocation proxy | Không cần AOP proxy chỉ để validate handler | Gọi `this.method()` trong target thường bypass advice |

Ví dụ service AOP:

~~~java
@Service
@Validated
public class OrderService {

    public void place(@NotBlank String code) {
        // Business logic.
    }
}
~~~

Trong một cấu hình có `MethodValidationPostProcessor`, caller phải nhận bean/proxy Spring và gọi qua proxy để method validation được kích hoạt. Đây **không** phải `HandlerMethodValidationException` chỉ vì class nằm cùng ứng dụng web. Mặc định service AOP thường báo `jakarta.validation.ConstraintViolationException`, trừ khi cấu hình adapter đổi sang loại Spring tương ứng.

Một lỗi triển khai phổ biến là đặt `@Validated` ở cấp class của controller theo hướng dẫn cũ, rồi kỳ vọng HTTP lỗi luôn đi theo `HandlerMethodValidationException` của Spring MVC 6.1+. Hãy phân biệt mode AOP và built-in, chọn một đường có chủ đích, và test exception class thực tế.

## 12. `@Valid`, `@Validated`, `@NotNull` và nhóm validation

### `@Valid`

`jakarta.validation.Valid` yêu cầu cascade kiểm tra thuộc tính của object. Nó **không phải direct constraint** và không đủ để kích hoạt built-in method validation theo nghĩa một method constraint đứng riêng. Với DTO chỉ có `@Valid @RequestBody`, loại lỗi phổ biến vẫn là `MethodArgumentNotValidException`.

### `@NotNull`

`jakarta.validation.constraints.NotNull` là constraint thực sự. Khi đặt **trực tiếp** trên method argument cùng `@Valid`, `@NotNull` có thể khiến method validation áp dụng, đồng thời `@Valid` đưa validation đi vào nested object. Không thay thế `@NotNull` bằng `@Valid` để mong null bị xem là lỗi: cascade validation không tự báo vi phạm khi giá trị null.

### `@Validated`

`org.springframework.validation.annotation.Validated` là annotation của Spring có thể chỉ định validation groups. Dùng nó trên service bean là cách phổ biến để chọn target cho AOP method validation. Ở controller Spring MVC 6.1+, **tránh class-level `@Validated`** khi muốn cơ chế built-in handler method validation.

### Groups

Constraint có `groups` sẽ được chọn theo các quy tắc Jakarta Validation. Ví dụ:

~~~java
public interface CreateChecks {
}

public record NewOrder(
    @NotBlank(groups = CreateChecks.class)
    String code) {
}
~~~

Đây là hai kiểu Java riêng minh họa, không thuộc demo chính. Một handler có thể dùng `@Validated(CreateChecks.class)` trên **DTO argument** để yêu cầu group phù hợp. Tuy nhiên, group selection và việc bật AOP qua class-level `@Validated` là hai khía cạnh không nên trộn lẫn. Luôn test các trường hợp group `Default` và group tùy chỉnh để không vô tình bỏ sót ràng buộc.

## 13. Kiểm tra từng nhóm lỗi để tạo response có field/path

Nếu API muốn trả danh sách field errors thay vì chỉ số affected parameters, có thể xây cấu trúc:

~~~json
{
  "type": "https://example.com/problems/validation",
  "status": 400,
  "errors": [
    {
      "parameter": "count",
      "messageCode": "Min"
    }
  ]
}
~~~

Đây là **mô hình JSON do ứng dụng tự thiết kế**, không phải output mặc định của Spring. Thực tế bạn cần duyệt `ParameterValidationResult` và phần `MessageSourceResolvable`/`ParameterErrors` để suy ra:

- **Vị trí method argument**: query, path, header, model attribute, request body.
- **Tên field** trong DTO nếu là nested validation.
- **Message code/constraint** thay vì chỉ message đã nội suy, nếu client cần localization.
- **Trạng thái** tương ứng input/return value.
- **Giá trị cần che giấu**: không phản hồi password, token hoặc data private.

Với `@RequestParam`, có thể tham khảo annotation `name()` hoặc `value()` khi explicit; với không chỉ định, phải dùng method parameter metadata và đặt fallback. Đừng mặc định `MethodParameter.getParameterName()` luôn có giá trị nếu bytecode không giữ `-parameters`. Với `@ModelAttribute` và nested constraints, `ParameterErrors`/`FieldError` hữu ích hơn việc gán một tên field giả cho toàn bộ DTO.

Nếu chỉ cần response RFC 9457 theo chuẩn Spring, có thể bắt đầu từ `ex.getBody()`/`ResponseEntityExceptionHandler` và thêm extension properties đã được rà soát, tránh tự triển khai toàn bộ error serialization không cần thiết.

## 14. Lỗi thực tế thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Đặt `@Valid @RequestBody` nhưng exception là `MethodArgumentNotValidException` | Chỉ có validation một object, chưa cần method validation | Đây là hành vi đúng; xử lý cả hai exception |
| Thêm `@Min` trên query và thấy `HandlerMethodValidationException` | Constraint trực tiếp kích hoạt built-in method validation | Dùng handler exception tương ứng |
| Class controller có `@Validated` và nhận `ConstraintViolationException` | Method validation chạy qua Spring AOP proxy | Bỏ class-level `@Validated` nếu muốn built-in MVC 6.1+ |
| `@Min` không chạy | Thiếu validation provider/MVC validator hoặc phiên bản không hỗ trợ | Kiểm tra validation starter, Spring version và bean validator |
| Giá trị `page=abc` không có trong danh sách validation results | Thất bại ở bước type conversion | Bắt type mismatch riêng |
| HTTP status là 500 dù lỗi “liên quan validation” | Vi phạm constraint trên return value | Xem `isForReturnValue()`, sửa logic server |
| `getParameterValidationResults().size()` nhỏ hơn số thông báo lỗi | Một parameter có thể có nhiều field errors | Duyệt result và nested errors, đừng dùng size làm tổng violation |
| `@Valid` và `@NotNull` cho kết quả khác nhau | `@Valid` cascade, `@NotNull` là direct constraint | Khai báo rõ hai mục đích nếu cần |
| Handler có `BindingResult` nhưng vẫn ném exception | Có lỗi ở tham số khác không có `Errors` tương ứng | Đọc toàn bộ chữ ký và vị trí `BindingResult` |
| Advice custom luôn trả 400 | Không tôn trọng status return-value error | Dùng `ex.getStatusCode()` / tham số `status` |
| Trùng mapping `@ExceptionHandler` với base class | Tự gắn handler trùng khi đã extends `ResponseEntityExceptionHandler` | Override `handleHandlerMethodValidationException` |
| JSON body không parse được | Lỗi Jackson/HTTP message converter, không phải constraint | Xử lý `HttpMessageNotReadableException` |
| Test gọi method trực tiếp nhưng không thấy exception | Bỏ qua Spring MVC handler invocation | Dùng MockMvc/HTTP integration test |
| Ghi log toàn bộ rejected values | Có thể rò rỉ secret hoặc dữ liệu người dùng | Log mã lỗi, parameter/path an toàn, correlation ID |
| Message trả về khác khi thay locale | Nội suy thông báo qua MessageSource/validator | Test message code và i18n config, không hardcode text |
| Spring MVC/WebFlux trộn lẫn tài liệu | Hai web stacks có infrastructure/error types khác nhau | Chọn đúng tài liệu Servlet MVC của phiên bản đang dùng |

Một thứ tự debug hiệu quả:

1. Request có match controller handler không?
2. Argument resolution/type conversion đã thành công chưa?
3. Đã cài và cấu hình Jakarta Validation provider chưa?
4. Handler có **direct constraint** trên parameter/return value không, hay chỉ có `@Valid` trên DTO?
5. Controller có class-level `@Validated` đang chuyển validation qua AOP không?
6. Handler có `BindingResult`/`Errors` ngay sau object parameter và có lỗi ở những tham số khác không?
7. Exception thực tế là loại nào, status bao nhiêu, `isForReturnValue()` bằng gì?
8. Advice/error handler nào đã xử lý exception và có thay đổi status/body không?
9. Test end-to-end qua MockMvc với input sai dạng, sai constraint, DTO-only, mixed parameters và return value.

## 15. Bài tập tự kiểm tra

**Bài 1 — Phân biệt hai exception.** Với `@Valid @RequestBody CheckoutRequest request` không có constraint trực tiếp khác, gửi body có `customerCode=""`. Loại lỗi thông dụng là gì? — `MethodArgumentNotValidException`, vì validation áp trên một object argument.

**Bài 2 — Thêm direct constraint.** Cùng handler có thêm `@RequestParam("channel") @Pattern(...) String channel`. Điều gì thay đổi? — Method validation được yêu cầu và có thể kiểm tra cả direct constraint và nested DTO; lỗi có thể đi theo `HandlerMethodValidationException`.

**Bài 3 — Conversion.** Với `@RequestParam @Min(1) int page`, gửi `page=abc`. Đây là lỗi nào? — Conversion sang `int` thất bại trước validation, không phải `@Min` báo violation.

**Bài 4 — Hai parameter groups.** `@PathVariable @Min(1) long id` và `@RequestParam @Min(1) int count` đều nhận `0`. Tập `getParameterValidationResults()` thường có mấy nhóm? — Hai nhóm tương ứng hai method parameters, mỗi tham số có một vi phạm.

**Bài 5 — Nested DTO.** Một `@Valid CheckoutRequest` có hai field sai. Có thể suy ra `getParameterValidationResults().size() == 2` không? — Không; một parameter chứa nhiều field errors vẫn có thể chỉ là một result.

**Bài 6 — Return value.** Handler `@NotNull String code()` trả `null`. `isForReturnValue()` và HTTP status là gì? — `true` và **500**, vì server phá vỡ hợp đồng trả về.

**Bài 7 — `BindingResult`.** Nếu form DTO sai và `BindingResult` đứng ngay sau, handler luôn chạy phải không? — Không; chỉ khi mọi validation errors đều thuộc các parameters có `Errors` tương ứng; lỗi ở parameter khác vẫn gây exception.

**Bài 8 — AOP.** Vì sao controller cấp class gắn `@Validated` có thể không ném `HandlerMethodValidationException`? — Vì Spring có thể dùng đường AOP method validation thay cho built-in MVC.

**Bài 9 — Error response.** Có nên bắt `HandlerMethodValidationException` rồi luôn trả 400? — Không; return-value violation là server error 500 theo contract.

**Bài 10 — Kiểm thử.** Tại sao `new DemoController().findItem(0,0)` không đủ kiểm chứng? — Vì nó bỏ qua MVC argument resolver, validation infrastructure và exception handler. Phải dùng MockMvc/HTTP test.

## 16. Checklist triển khai trong ứng dụng thực

- [ ] Dùng Spring MVC 6.1+ và Jakarta Validation provider tương thích; với Spring Boot 3.4/3.5 thêm Validation starter.
- [ ] Chọn đúng annotation: `@Valid` cho cascade DTO; `@Min`/`@NotBlank`/`@Pattern`... cho direct constraint.
- [ ] Nếu muốn built-in MVC method validation, **không đặt class-level `@Validated` trên controller**.
- [ ] Hiểu rằng method validation có thể bao quát cả các DTO `@Valid` khi handler có direct constraint.
- [ ] Xử lý **cả** `MethodArgumentNotValidException` và `HandlerMethodValidationException`.
- [ ] Tách lỗi missing parameter/type conversion/JSON syntax khỏi constraint violations.
- [ ] Dùng `getParameterValidationResults()` đúng nghĩa: nhóm theo parameter, không mặc nhiên là số individual violations.
- [ ] Với nested DTO, xử lý `ParameterErrors` và field/object errors nếu cần error response chi tiết.
- [ ] Tôn trọng `getStatusCode()` và `isForReturnValue()`: input 400, return-value 500.
- [ ] Dùng `ResponseEntityExceptionHandler` override hoặc `@ExceptionHandler` có chủ đích, tránh mapping chồng chéo.
- [ ] Với `BindingResult`, đặt đúng vị trí ngay sau object argument và xem xét các lỗi trên tham số khác.
- [ ] Không xuất rejected secrets, stack trace, class internals hoặc message chưa kiểm soát cho client.
- [ ] Kiểm thử với MockMvc cho request hợp lệ, direct constraint sai, DTO-only sai, mixed DTO+direct sai và return-value sai.
- [ ] Nếu có Spring AOP trên controller/service, xác định cơ chế thực tế và loại exception được ném.
- [ ] Với đa ngôn ngữ, dùng message codes và `MessageSource`; kiểm tra response RFC 9457/ProblemDetail theo API contract.

**Ghi nhớ:** `HandlerMethodValidationException` là tín hiệu của **built-in Spring MVC handler method validation** khi kiểm tra cấp method thất bại. Nó nhóm kết quả theo tham số, có API visitor và cho phép phân biệt **400 cho dữ liệu đầu vào** với **500 cho giá trị trả về**. Đừng nhầm nó với `MethodArgumentNotValidException` của DTO validation đơn lẻ, `MethodArgumentTypeMismatchException` của chuyển kiểu hoặc `ConstraintViolationException` của AOP method validation trong service.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Validation trong Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring API 6.2 — HandlerMethodValidationException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring API 6.2 — HandlerMethodValidationException.Visitor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.Visitor.html)
- [Spring API 6.2 — ParameterValidationResult](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html)
- [Spring API 6.2 — ParameterErrors](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterErrors.html)
- [Spring API 6.2 — ResponseEntityExceptionHandler](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
